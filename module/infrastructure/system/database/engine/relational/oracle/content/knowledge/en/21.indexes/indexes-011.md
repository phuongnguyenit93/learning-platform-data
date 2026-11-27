# Invisible Indexes and Testing Execution Plan Changes in Oracle Database

An index can make some queries run faster while increasing `INSERT`, `UPDATE`, and `DELETE` costs. When a DBA wants to evaluate removing an index, dropping it immediately carries risk because SQL statements relying on it could switch execution plans and slow down. Oracle provides **invisible indexes** to test the impact of hiding an index from the optimizer while keeping the index in the database.

An invisible index still exists, consumes storage, and is maintained by DML. By default, the optimizer ignores this index when choosing execution plans. You can enable the session parameter `OPTIMIZER_USE_INVISIBLE_INDEXES` so the optimizer considers invisible indexes in a test session.

The question this technique helps answer is: **if the optimizer no longer uses this index, which plans will SQL statements choose and how does performance change?** If results are good and the workload is unaffected, the DBA can consider dropping the index after sufficient monitoring. If regressions occur, the index can be switched back to `VISIBLE`.

This lesson explains index visibility, how the optimizer handles invisible indexes, controlled testing workflows, inspecting execution plans and runtime statistics, restrictions when an index backs a constraint, DML impact, common interpretation errors, and a hands-on exercise on a demo table.

## 1. Visible Indexes vs. Invisible Indexes

### 1.1. Visible indexes

Normally, an index is created in the visible state. The optimizer can consider the index when generating execution plans if it matches predicates, joins, `ORDER BY`, or data access requirements.

Example:

```sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);
```

When a query filters on `CUSTOMER_ID`, the optimizer may choose `INDEX RANGE SCAN` if cost estimates are favorable. Having an index does not force Oracle to always use it; the optimizer can still choose a full table scan or another access path.

### 1.2. Invisible indexes

An invisible index is an index whose visibility metadata is set to `INVISIBLE`. The index remains in the schema, occupies storage, and continues to be maintained when data changes. However, the optimizer ignores it by default when building execution plans.

Create an index directly as invisible:

```sql
CREATE INDEX ix_orders_customer_test
ON orders(customer_id)
INVISIBLE;
```

Or alter an existing index to invisible:

```sql
ALTER INDEX ix_orders_customer INVISIBLE;
```

To make it visible again:

```sql
ALTER INDEX ix_orders_customer VISIBLE;
```

Changing visibility is DDL, so account for implicit commits and deployment procedures before running it in an environment with open business transactions.

### 1.3. Invisible does not mean disabled

Distinguish carefully:

| Status / Concept | Meaning |
| --- | --- |
| `VISIBLE` | The optimizer can consider the index based on cost and configuration |
| `INVISIBLE` | The optimizer ignores the index by default |
| `UNUSABLE` | The index is not ready for normal access operations until rebuilt or handled |
| `DROP` | The index is removed from the schema |
| `DISABLED` constraint | The constraint is disabled; this is a constraint state, not index visibility |

An invisible index is not a dropped index, not an unusable index, and not a disabled constraint.

### 1.4. Why not DROP immediately?

Suppose an index was created long ago and a DBA suspects it is no longer needed. If it is dropped, dependent queries might switch to full table scans or other access paths. You would then have to rebuild the index and re-verify plans.

Making the index invisible simulates removing the index from optimizer selection while retaining instant recovery via `ALTER INDEX VISIBLE`.

This is a controlled testing and rollout tool, not automatic proof that an index can be dropped safely.

## 2. How the Optimizer Handles Invisible Indexes

### 2.1. Default behavior

Under normal settings, the optimizer does not consider invisible indexes when building execution plans. Thus, after:

```sql
ALTER INDEX ix_orders_customer INVISIBLE;
```

newly parsed SQL statements will plan as if that index is unavailable to the optimizer. Other visible indexes can still be chosen.

Running SQL or previously parsed cursors do not necessarily switch plans at the instant `ALTER INDEX` runs. When testing, ensure the statement is parsed under the new condition and inspect the corresponding cursor plan.

### 2.2. OPTIMIZER_USE_INVISIBLE_INDEXES

The parameter `OPTIMIZER_USE_INVISIBLE_INDEXES` controls whether the optimizer may consider invisible indexes.

Check session value:

```sql
SHOW PARAMETER optimizer_use_invisible_indexes;
```

Or:

```sql
SELECT name, value
FROM   v$parameter
WHERE  name = 'optimizer_use_invisible_indexes';
```

The default is usually `FALSE`. You can enable it at the session level for testing:

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

The optimizer can then consider invisible indexes within that session. This parameter does not force the optimizer to pick a specific index; the cost-based optimizer still decides based on statistics, predicates, cardinality, system statistics, and other factors.

### 2.3. Turning it off after testing

When finished:

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Session-level settings affect only the current session. This is ideal for plan testing without altering optimizer behavior for other application sessions.

Do not set this parameter at the `SYSTEM` level just to test one SQL statement without a clear deployment rationale. Broad changes can cause other invisible indexes to be considered by the optimizer as well.

### 2.4. Setting TRUE does not make an index visible

Two independent concepts:

- `ALTER INDEX ... VISIBLE` changes the index's visibility metadata.
- `OPTIMIZER_USE_INVISIBLE_INDEXES = TRUE` allows the optimizer within that parameter's scope to consider invisible indexes.

The index remains marked `INVISIBLE` in the dictionary while a session has the parameter set to `TRUE`. Other sessions with `FALSE` continue ignoring it by default.

### 2.5. Hints and invisible indexes

Optimizer hints such as `INDEX` or `NO_INDEX` can influence access path selection, but should not replace standard visibility testing. If the goal is observing the optimizer's natural decision, keep SQL, binds, statistics, and environment identical and change only one variable: visibility or the session parameter.

Hints can be useful in a separate experiment to verify whether an access path is feasible. That result does not prove the optimizer will naturally select the index in real workloads.

## 3. Metadata and Checking Index Status

### 3.1. Viewing visibility in USER_INDEXES

In the current schema:

```sql
SELECT index_name,
       table_name,
       uniqueness,
       status,
       visibility,
       index_type
FROM   user_indexes
ORDER  BY table_name, index_name;
```

The `VISIBILITY` column displays `VISIBLE` or `INVISIBLE`. The `STATUS` column shows index state, such as `VALID` or `UNUSABLE`; do not confuse `STATUS` with `VISIBILITY`.

### 3.2. Viewing indexes for a specific table

```sql
SELECT index_name,
       uniqueness,
       status,
       visibility
FROM   user_indexes
WHERE  table_name = 'ORDERS'
ORDER  BY index_name;
```

Object names in the dictionary are normally stored in uppercase unless created with quoted identifiers.

### 3.3. Viewing columns in an index

```sql
SELECT index_name,
       column_position,
       column_name,
       descend
FROM   user_ind_columns
WHERE  table_name = 'ORDERS'
ORDER  BY index_name, column_position;
```

Know which columns an index covers and in what order before evaluating its impact. A composite index may serve multiple SQL statements via leading columns; looking at the index name alone is not enough to declare it redundant.

### 3.4. Viewing related constraints

```sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       c.index_name
FROM   user_constraints c
WHERE  c.table_name = 'ORDERS'
ORDER  BY c.constraint_name;
```

An index may be linked to a `PRIMARY KEY` or `UNIQUE` constraint. Oracle enforces restrictions on making indexes invisible when they enforce these constraints. Before altering visibility, verify whether the index supports a constraint; do not use invisible indexes as a way to disable PK/UK enforcement. If an index backs a constraint enforcing uniqueness, manage the constraint and index through supported Oracle procedures for your release rather than forcing visibility workarounds.

### 3.5. Viewing index DDL

```sql
SELECT DBMS_METADATA.GET_DDL('INDEX', 'IX_ORDERS_CUSTOMER')
FROM   dual;
```

`DBMS_METADATA` lets you inspect index definitions including columns, tablespace, storage, and related attributes. Appropriate privileges are required when reading metadata from another schema.

## 4. Invisible Indexes and Testing Execution Plan Changes

### 4.1. Experiment objectives

A well-designed test should answer:

1. When the index is visible, which plan does the optimizer choose?
2. When the index is invisible and defaults apply, how does the plan change?
3. When allowing invisible indexes in a test session, does the optimizer consider that index?
4. How does actual runtime change under identical data, binds, and load conditions?
5. Is the index used by other critical SQL statements?

Do not compare only a single `INDEX RANGE SCAN` line against `TABLE ACCESS FULL`. Inspect elapsed time, buffer gets, physical reads, actual rows, cardinality estimates, and overall workload impact.

### 4.2. Establishing a baseline

Before testing:
- Record the index name and initial state.
- Capture `SQL_ID`, plan hash value, and execution plans of critical SQL statements.
- Record bind values or representative bind distributions.
- Record table/index statistics and last gather timestamps.
- Measure elapsed time, CPU, logical reads, and physical reads.
- Test in a test/staging environment whenever possible.

Never change visibility on a production index without a monitoring plan and rollback procedure.

### 4.3. Testing with EXPLAIN PLAN

```sql
EXPLAIN PLAN FOR
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM   orders
WHERE  customer_id = 100;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the estimated plan for the SQL statement. It is helpful for observing how the optimizer plans in the current session, but does not replace the runtime plan of an executed cursor.

To test an invisible index, run `EXPLAIN PLAN` in a session with `OPTIMIZER_USE_INVISIBLE_INDEXES` set to `FALSE` and `TRUE`, holding all other conditions constant.

### 4.4. Viewing runtime plans with DBMS_XPLAN

You can collect execution statistics for a SQL statement:

```sql
SELECT /*+ gather_plan_statistics */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   orders
WHERE  customer_id = :customer_id;
```

After executing and fetching all rows, inspect the cursor plan:

```sql
SELECT *
FROM   TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
```

`ALLSTATS LAST` shows statistics for the most recent execution if Oracle captured them. Useful details include:
- `E-Rows`: estimated rows.
- `A-Rows`: actual rows.
- `Buffers`: logical reads.
- `Reads`: physical reads per displayed statistics.
- `Predicate Information`: access and filter predicates.
- `Operation`: steps in the execution plan.

Privileges to read performance views are required. If `ALLSTATS LAST` shows no metrics, verify the statement executed and had `gather_plan_statistics` or appropriate statistics collection enabled.

### 4.5. Why can EXPLAIN PLAN and runtime plans differ?

The actual execution plan can differ from `EXPLAIN PLAN` due to:
- Bind peeking and bind values.
- Adaptive cursor sharing.
- Statistics or histograms.
- Session parameters.
- SQL profiles, baselines, or patches.
- Adaptive plans.
- Environmental factors and optimizer settings.

Therefore, when assessing an invisible index's impact, collect actual cursors under production-like workloads rather than relying solely on a single `EXPLAIN PLAN`.

## 5. Hands-On Lab: Creating a Demo Table and Indexes

### 5.1. Create test data

Run in a learning schema or test environment:

```sql
CREATE TABLE demo_invisible_orders AS
SELECT LEVEL AS order_id,
       MOD(LEVEL, 1000) AS customer_id,
       CASE
           WHEN MOD(LEVEL, 20) = 0 THEN 'OPEN'
           ELSE 'CLOSED'
       END AS status,
       TRUNC(SYSDATE) - MOD(LEVEL, 365) AS order_date,
       MOD(LEVEL, 50000) / 100 AS total_amount
FROM   dual
CONNECT BY LEVEL <= 100000;
```

Create PK and indexes for demo queries:

```sql
ALTER TABLE demo_invisible_orders
ADD CONSTRAINT pk_demo_invisible_orders
PRIMARY KEY (order_id);

CREATE INDEX ix_demo_orders_customer
ON demo_invisible_orders(customer_id);

CREATE INDEX ix_demo_orders_status_date
ON demo_invisible_orders(status, order_date);
```

Data is generated deterministically for repeatability. This distribution is purely for learning and does not represent every real-world workload.

### 5.2. Gather statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'DEMO_INVISIBLE_ORDERS',
        cascade => TRUE
    );
END;
/
```

The optimizer needs accurate statistics to estimate cardinality and cost. If data or indexes change substantially, re-gather statistics before comparing.

### 5.3. Run baseline query with index visible

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;

SELECT /*+ gather_plan_statistics */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   demo_invisible_orders
WHERE  customer_id = 100;
```

After fetching all rows, inspect:

```sql
SELECT *
FROM   TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Record access path, `buffers`, `reads`, `A-Rows`, `E-Rows`, and elapsed time. Plan outcomes depend on statistics and environment, so never assume an index is guaranteed to be picked.

### 5.4. Hide the index and re-run

```sql
ALTER INDEX ix_demo_orders_customer INVISIBLE;
```

Verify:

```sql
SELECT index_name, visibility, status
FROM   user_indexes
WHERE  index_name = 'IX_DEMO_ORDERS_CUSTOMER';
```

In a session with `OPTIMIZER_USE_INVISIBLE_INDEXES = FALSE`, re-run the same query with a distinct comment to force/capture a separate parse:

```sql
SELECT /*+ gather_plan_statistics */ /* INVISIBLE_TEST_OFF */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   demo_invisible_orders
WHERE  customer_id = 100;
```

Inspect the runtime plan with `DBMS_XPLAN`. By default, the optimizer ignores the newly hidden index; it may choose another index or a full table scan depending on cost.

### 5.5. Allow the optimizer to consider invisible indexes in the test session

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
```

Run the query with the same filter and a different SQL tag:

```sql
SELECT /*+ gather_plan_statistics */ /* INVISIBLE_TEST_ON */
       order_id,
       customer_id,
       order_date,
       total_amount
FROM   demo_invisible_orders
WHERE  customer_id = 100;
```

Inspect the runtime plan. The optimizer is permitted to consider invisible indexes, though not forced to pick them. If another access path has a lower cost, the optimizer can continue using that alternative plan.

### 5.6. Restore state

At the end of the experiment, make the index visible again and reset the session parameter:

```sql
ALTER INDEX ix_demo_orders_customer VISIBLE;

ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Confirm:

```sql
SELECT index_name, visibility, status
FROM   user_indexes
WHERE  index_name = 'IX_DEMO_ORDERS_CUSTOMER';
```

Always record the initial state. If an index was originally invisible, do not arbitrarily switch it to visible after testing; restore the exact original state.

## 6. Reading and Comparing Execution Plans

### 6.1. Comparing access paths

Operations you may encounter:
- `TABLE ACCESS FULL`: reads the table via a full scan.
- `INDEX RANGE SCAN`: accesses a key range matching predicates.
- `INDEX UNIQUE SCAN`: locates a single unique key.
- `TABLE ACCESS BY INDEX ROWID`: fetches table rows using ROWIDs returned by an index.
- `INDEX FAST FULL SCAN`: reads an index as a standalone data structure without guaranteeing key order.

When an index becomes invisible, the optimizer may switch from an index range scan to a full scan. That is not automatically a regression; if the query returns most of the table, a full scan may be cheaper.

### 6.2. Estimated vs. actual cardinality

Compare `E-Rows` against `A-Rows`:
- `E-Rows` much higher than `A-Rows`: the optimizer may be overestimating rows.
- `E-Rows` much lower than `A-Rows`: the optimizer may be underestimating rows and picking an unsuitable plan.
- Large discrepancies can stem from statistics, histograms, column correlation, or bind values.

If the plan shifts after hiding an index, verify whether the shift came from losing that access path or from other session conditions changing.

### 6.3. Logical reads and physical reads

- **Buffers/logical reads:** block reads through the buffer cache; useful for comparing logical read work.
- **Physical reads:** blocks fetched from storage per runtime stats; depends heavily on cache state.
- **Elapsed time:** wall-clock time influenced by system load, I/O, CPU, and concurrency.
- **CPU time:** CPU time consumed by the statement.

One run may be faster simply because blocks were already cached. Execute multiple runs under equivalent conditions, track both logical reads and runtime, and never flush buffer caches on shared systems just to benchmark.

### 6.4. Plan hash value

Plan hash value identifies plan structure, making comparisons convenient. However:
- A different plan hash does not automatically mean worse performance.
- The same plan hash does not guarantee identical runtime.
- Always inspect operations, predicates, cardinalities, and actual runtime statistics.

### 6.5. Bind values and cursor sharing

If SQL uses bind variables, plans can be affected by bind peeking or adaptive cursor sharing. When comparing:
- Use identical representative bind values.
- Use identical bind datatypes.
- Record `child_number` and `SQL_ID`.
- Do not mix results across parses made under different conditions.
- Test multiple bind groups if selectivity varies.

An index can be great for a customer with few orders yet poor for a customer with very many orders. Never generalize from a single bind value.

## 7. Invisible Indexes in Production Environments

### 7.1. Workflow for evaluating whether an index can be dropped

A typical process:

1. Identify the index and why it is suspected unnecessary.
2. Verify whether the index backs a PK/UK constraint or another feature.
3. Collect the SQL workload referencing the table and index.
4. Capture baseline execution plans and runtime metrics.
5. Switch to `INVISIBLE` in a controlled change window.
6. Monitor the workload long enough to cover full business cycles.
7. If regressions occur, revert to `VISIBLE`.
8. If no regressions occur and solid evidence exists, schedule a separate `DROP`.
9. After dropping, continue monitoring as DML and storage savings take effect.

Do not remove an index merely because it was absent from a few sampled plans or a short-term usage report recorded zero hits.

### 7.2. Invisible indexes still incur DML cost

While an index is `INVISIBLE`:
- `INSERT` still updates the index.
- `DELETE` still updates the index.
- `UPDATE` of indexed columns still updates index entries.
- The index still consumes segment space and maintenance overhead.

Thus, an invisible index primarily tests plan-selection impact. It does not simulate the full DML performance and storage savings gained from dropping the index.

### 7.3. Index usage monitoring is not the same as invisible indexes

Oracle offers usage monitoring:

```sql
ALTER INDEX ix_demo_orders_customer MONITORING USAGE;
```

After a monitoring period:

```sql
SELECT index_name,
       monitoring,
       used,
       start_monitoring,
       end_monitoring
FROM   v$object_usage;
```

View availability and scope depend on Oracle version and privileges. Usage monitoring reports whether an index was recorded as used during the observation window; it does not change visibility or measure the index's full potential benefit. A short monitoring window or incomplete workload can miss rare monthly or quarterly SQL.

### 7.4. Watch out for seasonal or periodic workloads

An index might see little daily use yet be critical for:
- Month-end close.
- Quarter-end reporting.
- Annual reports.
- Batch reconciliation.
- Audit jobs.
- Peak traffic events.

Before dropping, observe across a representative cycle or analyze historical SQL workloads. Never assume a single regression-free day suffices for every system.

### 7.5. Rollback plan

If regressions appear after hiding an index:

```sql
ALTER INDEX ix_demo_orders_customer VISIBLE;
```

Restoring visibility is relatively fast. However, previously parsed cursors may need to be re-parsed so the optimizer considers the index under the restored state. Monitor `SQL_ID`/child cursors and confirm runtime plans return to normal.

Do not wait until SLAs are severely breached before rolling back. Define stop criteria in advance, such as agreed thresholds for response time or buffer gets.

## 8. Constraints and Limitations to Note

### 8.1. Indexes backing PRIMARY KEY or UNIQUE constraints

Indexes used by Oracle to enforce `PRIMARY KEY` or `UNIQUE` constraints have specific visibility restrictions. Never treat invisible indexes as a way to disable index enforcement while keeping the constraint active.

Before testing:

```sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.index_name
FROM   user_constraints c
WHERE  c.table_name = 'DEMO_INVISIBLE_ORDERS';
```

If an index belongs to a constraint, check release documentation and supported procedures. Do not disable a constraint merely to hide its index when your initial goal is plan evaluation.

### 8.2. An invisible index is not private to one session

Visibility is an index attribute in database metadata. `OPTIMIZER_USE_INVISIBLE_INDEXES` is the session setting permitting the optimizer to consider invisible indexes.

Consequently, a test session with `TRUE` can consider *any* eligible invisible index in the schema/database, not just the index under investigation. Inventory other invisible indexes before interpreting plans.

### 8.3. Turning TRUE on does not guarantee index usage

The optimizer still decides by cost. If the index has low selectivity, the query needs most of the table, or clustering factor is unfavorable, a full scan can be cheaper. `OPTIMIZER_USE_INVISIBLE_INDEXES = TRUE` merely makes the index eligible for consideration.

### 8.4. DDL and implicit commits

`ALTER INDEX` statements are DDL and issue implicit commits per Oracle rules. Never place them between DML steps where the application expects to `ROLLBACK` the entire transaction.

Schedule visibility changes separately, record the initial state, and coordinate deployment windows.

### 8.5. Versions and index types

Exact capabilities and limits can vary by release, index type, partitioning, constraints, and active features. Before applying in real environments, check the SQL Language Reference and Administrator's Guide for your exact Oracle version. Do not assume every index type behaves identically or can toggle visibility freely.

## 9. Distinguishing Invisible Indexes from Related Features

| Feature | Purpose | Removes or stops maintaining the index? |
| --- | --- | --- |
| Invisible index | Tests optimizer behavior when an index is hidden | No; DML still maintains the index |
| Unusable index | Marks an index unavailable for normal access | Does not serve normal reads; DML maintenance depends on attributes and operations |
| Index monitoring | Records whether an index was used | Does not alter plans or maintenance |
| `DROP INDEX` | Removes the index from the schema | Yes; eliminates maintenance cost for that index |
| SQL Plan Baseline | Manages/controls accepted plans | Does not directly alter index visibility |
| SQL Profile | Supplies optimizer adjustment info | Does not directly alter index visibility |

Invisible indexes test optimizer usage of an index. Index monitoring observes usage. SQL Plan Management governs plan stability. Do not conflate their purposes.

## 10. Controlled Experiment Workflow

### 10.1. Preparation

Before running:
- Choose an index not tied to a protected PK/UK constraint.
- Record initial visibility and DDL.
- Identify critical SQL referencing the table.
- Prepare representative bind values.
- Capture baseline statistics and runtime metrics.
- Use a test/staging environment or an approved change window.
- Prepare the rollback statement to restore visibility.

### 10.2. Execution

1. Run baseline SQL while the index is visible.
2. Record `SQL_ID`, plan hash, operations, `buffers`, `reads`, and elapsed time.
3. Alter the index to `INVISIBLE`.
4. Keep `OPTIMIZER_USE_INVISIBLE_INDEXES = FALSE` and run a newly parsed SQL execution.
5. Record the plan when the optimizer ignores the index.
6. Set `TRUE` in the test session and re-run.
7. Record the plan when the optimizer is allowed to consider the index.
8. Run across multiple bind values and multiple iterations.
9. Restore the index's original visibility state.

### 10.3. Evaluation

Do not inspect only plan text. Compare:
- Are query results identical?
- Does `A-Rows` match expectations?
- How much do `buffers` and physical `reads` change?
- Are elapsed/CPU times consistent across runs?
- Are other SQL statements on the same table affected?
- Did batch DML still pay index maintenance overhead while invisible?
- Were monthly/quarterly workloads covered?

### 10.4. Decision

- **Keep visible:** the index is still needed or hiding it caused regressions.
- **Keep invisible during extended observation:** more evidence from a full workload cycle is needed.
- **DROP after approval:** only when proven free of significant regressions and DML/storage cleanup is desired.
- **Restore visible:** if regressions appear or unassessed dependencies are discovered.

Making an index invisible is a reversible test step, while `DROP` remains a separate change requiring planning and control.

## 11. Common Misconceptions

**"An invisible index has been deleted."** False. The index still exists and is maintained by DML.

**"The optimizer always ignores invisible indexes in every situation."** It ignores them by default; a session with `OPTIMIZER_USE_INVISIBLE_INDEXES = TRUE` allows the optimizer to consider them.

**"Setting the parameter to TRUE forces Oracle to use the index."** False. The optimizer still selects based on cost and statistics.

**"Hiding an index reduces INSERT/UPDATE/DELETE overhead."** False. The index is still maintained. Only `DROP` eliminates that maintenance overhead.

**"One query not using an index means it can be dropped."** Insufficient. Rare SQL or periodic workloads may rely on the index.

**"EXPLAIN PLAN equals real performance."** False. Inspect runtime plans and execution statistics.

**"A different plan hash means the new plan is slower."** False. Compare operations and runtime metrics.

**"Invisible indexes disable UNIQUE constraints."** False. Never use visibility to bypass constraint enforcement; constraint-backing indexes have their own restrictions.

**"V$OBJECT_USAGE captures every possible usage."** False. It only reflects monitoring during the enabled scope/window and can miss rare workloads.

**"Switching an index back to VISIBLE guarantees every cursor immediately uses it again."** Not necessarily. Check cursor parses, child cursors, and runtime plans after the change.

## 12. Hands-On Exercises

Exercises use `DEMO_INVISIBLE_ORDERS` from Section 5. Run DDL only in a learning schema.

### Exercise 1 — Check index status

```sql
SELECT index_name,
       table_name,
       status,
       visibility,
       uniqueness
FROM   user_indexes
WHERE  table_name = 'DEMO_INVISIBLE_ORDERS';
```

Identify which indexes are visible and which are invisible.

### Exercise 2 — Switch an index to invisible

```sql
ALTER INDEX ix_demo_orders_customer INVISIBLE;
```

Check `USER_INDEXES.VISIBILITY`. Explain why the index still exists.

### Exercise 3 — Compare EXPLAIN PLAN

Run the same query with `OPTIMIZER_USE_INVISIBLE_INDEXES` set to `FALSE` and `TRUE`. Save both `DBMS_XPLAN.DISPLAY` outputs and explain the difference.

### Exercise 4 — Compare runtime plans

Run the query with `gather_plan_statistics`, fetch all rows, and inspect `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`. Compare `E-Rows`, `A-Rows`, `Buffers`, and `Reads`.

### Exercise 5 — Test different bind values

Pick two `CUSTOMER_ID` values with different order counts. Run the query with both binds and observe whether the optimizer chooses the same access path.

### Exercise 6 — Enable and disable the session parameter

```sql
ALTER SESSION SET optimizer_use_invisible_indexes = TRUE;
SHOW PARAMETER optimizer_use_invisible_indexes;

ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Explain why the session parameter does not alter index visibility metadata.

### Exercise 7 — Check whether an index backs a constraint

```sql
SELECT constraint_name,
       constraint_type,
       status,
       index_name
FROM   user_constraints
WHERE  table_name = 'DEMO_INVISIBLE_ORDERS';
```

Distinguish the PK index from secondary indexes used for queries.

### Exercise 8 — Observe DML while an index is invisible

While the index is invisible, `INSERT` a demo row and verify the index still exists and continues to be maintained. Explain why making an index invisible does not fully simulate `DROP`.

### Exercise 9 — Index usage monitoring

Enable usage monitoring, run a few representative SQL queries, and inspect `V$OBJECT_USAGE` if version and privileges permit. Compare the purpose of monitoring with invisible indexes.

### Exercise 10 — Restore state

```sql
ALTER INDEX ix_demo_orders_customer VISIBLE;
ALTER SESSION SET optimizer_use_invisible_indexes = FALSE;
```

Confirm visibility matches the initial state.

### Exercise 11 — Evaluate a DROP candidate index

Choose a secondary index in the demo schema. Write a plan to observe the workload over a sufficient cycle, listing critical SQL statements and runtime metrics to compare before proposing `DROP`.

### Exercise 12 — Read plans and make a decision

Suppose while invisible:
- One query increases `buffers` by 8x.
- Another query drops elapsed time by 10%.
- Batch `INSERT` shows no significant change because the index is still maintained.

Propose the next step. Explain why you cannot conclude an index should be dropped based on a single query.

## 13. Oracle Reference Documentation

- [Oracle Database SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): creating indexes and visibility attributes.
- [Oracle Database SQL Language Reference — ALTER INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-INDEX.html): altering index visibility and attributes.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, execution plans, and SQL performance analysis.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): displaying execution plans and runtime statistics.
- [Oracle Database Reference — USER_INDEXES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_INDEXES.html): index metadata and visibility.
- [Oracle Database Reference — V$OBJECT_USAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-OBJECT_USAGE.html): index usage monitoring information.

Invisible indexes let you test the impact of removing an index from optimizer selection while preserving the index and instant visibility recovery. Capture a baseline, change one variable at a time, compare runtime plans under identical binds and workloads, monitor across full business cycles, and only then decide to keep, restore, or drop. **An invisible index is still maintained by DML; visibility testing evaluates execution plan impact, not the full DML and storage savings of dropping the index.**

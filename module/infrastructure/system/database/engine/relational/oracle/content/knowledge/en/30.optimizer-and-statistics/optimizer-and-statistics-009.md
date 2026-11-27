# Dynamic Statistics, Cardinality Feedback, and Oracle Database Version Differences

When optimizing a SQL statement, Oracle does not know in advance exactly how many rows each step will return. The optimizer must **estimate cardinality** based on table, column, index, histogram, expression statistics, and related information. This estimate affects join order, join methods, access paths, parallelism, memory, and execution plan cost.

If an estimate is far off, the optimizer can pick a very expensive plan. For instance, the optimizer thinks a predicate returns only 10 rows when it actually returns 500,000 rows. A nested loops join chosen on the assumption of 10 rows can become costly when executing hundreds of thousands of lookups.

Oracle provides several mechanisms to improve cardinality information:

- **Dynamic statistics** (formerly dynamic sampling): samples data blocks during parse time to supplement estimates when existing statistics are missing or insufficient.
- **Statistics feedback** (formerly cardinality feedback): compares estimated cardinality against actual row counts after execution, then uses feedback to re-optimize subsequent runs.
- **SQL plan directives:** records predicate/expression patterns where the optimizer frequently misestimates, to apply dynamic statistics or assist in gathering extended statistics for structurally similar SQL statements.
- **Adaptive cursor sharing:** for SQL with bind variables whose selectivity varies widely by bind value, Oracle can create multiple child cursors with different plans.

These mechanisms are related but distinct. Dynamic statistics supplement information before selecting a plan; statistics feedback learns from prior execution; SQL plan directives store experience at the query expression level; adaptive cursor sharing handles the problem of identical SQL text with bind values of differing selectivities.

This document explains how they work, how to observe execution plans, key parameters and hints, and version differences from Oracle Database 11g through Oracle AI Database 26ai.

## 1. What Is Cardinality and Why Does It Matter?

An operation's cardinality is the number of rows that operation returns. In an execution plan, the optimizer displays estimated cardinality in the **Rows** or **E-Rows** column. When runtime statistics are available, actual row counts appear in the **A-Rows** column.

Example:

~~~text
| Id | Operation          | E-Rows | A-Rows |
|----|--------------------|-------:|-------:|
|  3 | TABLE ACCESS FULL  |     10 | 500000 |
|  2 | NESTED LOOPS       |     10 | 500000 |
|  1 | SELECT STATEMENT   |     10 | 500000 |
~~~

The optimizer expected only 10 rows, whereas reality produced 500,000 rows. This discrepancy can dramatically alter actual cost:

- Nested loops may perform far too many inner table/index lookups.
- Hash join may be chosen with mismatched build/probe sizes.
- Sorts or hash aggregations may require much more memory and spill to TEMP.
- Join order may place a large table in an unfavorable position.
- Parallel execution may choose a poor DOP or distribution method.

Wrong cardinality does not automatically prove the optimizer picked a wrong plan; inspect the whole plan, data, buffers, elapsed time, and actual operations. Still, a large gap between E-Rows and A-Rows is an important signal to investigate.

### 1.1 Selectivity and Cardinality

Selectivity is the fraction of rows satisfying a condition. A conceptual formula:

\[
\text{Cardinality} \approx \text{Table rows} \times \text{Selectivity}
\]

If a table has 1,000,000 rows and a predicate has selectivity 0.01 (1%), estimated cardinality is roughly 10,000 rows.

For an equality predicate on one column, when no histogram exists and distribution is assumed roughly uniform, the optimizer can approximate selectivity via:

\[
\text{Selectivity} \approx \frac{1}{NDV}
\]

Where NDV is the column's number of distinct values. For example, a column with NDV = 100 yields an estimated equality selectivity of around 1% if no other distribution data exists.

The uniform assumption can fail when data is skewed. One value may appear in 70% of rows while most others appear rarely. Histograms help the optimizer understand this skewed distribution.

### 1.2 What Do Optimizer Statistics Contain?

The optimizer uses multiple categories of statistics:

| Category | Examples | Impact |
|---|---|---|
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Estimate table size and scan cost |
| Column statistics | NDV, NUM_NULLS, LOW_VALUE, HIGH_VALUE | Estimate selectivity |
| Histogram | Frequency, top-frequency, hybrid, height-balanced | Describe skewed distributions |
| Extended statistics | Column group, expression statistics | Describe correlations between columns or expressions |
| Index statistics | LEAF_BLOCKS, BLEVEL, CLUSTERING_FACTOR | Estimate index access cost |
| System statistics | CPU and I/O characteristics | Compare CPU/I/O costs across plans |

Dynamic statistics and feedback supplement existing optimizer information. They are not a substitute for gathering baseline statistics with DBMS_STATS.

### 1.3 Correlation Between Multiple Columns

Suppose the CUSTOMERS table has two columns:

- CITY
- STATE_PROVINCE

In real data, Los Angeles belongs to California. The following two predicates are correlated:

~~~sql
WHERE city = 'Los Angeles'
  AND state_province = 'CA'
~~~

If the optimizer treats the two conditions as independent, it may multiply each column's selectivity and estimate far fewer rows than reality. Extended column-group statistics can model this correlation.

Dynamic statistics can sample to estimate better in certain cases; statistics feedback can detect discrepancies after execution; SQL plan directives can record query expressions needing extra info. Each mechanism addresses a different point in time and scope.

## 2. Dynamic Statistics (Dynamic Sampling)

Dynamic statistics is a technique where the optimizer executes a recursive SQL query to scan a small random sample of table blocks during parse/optimization. From this sample, the optimizer estimates predicate selectivity and cardinality to fill in missing information.

Prior to Oracle Database 12c Release 1 (12.1), this feature was called **dynamic sampling**. Starting in 12.1, the name changed to **dynamic statistics** to emphasize that these are statistics collected dynamically during optimization.

Dynamic statistics are not a full statistics gather into the data dictionary like DBMS_STATS.GATHER_TABLE_STATS. They provide the optimizer additional data for the SQL currently being parsed and can share/reuse results in appropriate scenarios.

### 2.1 When Does the Optimizer Consider Dynamic Statistics?

Common cases include:

- A table lacks optimizer statistics.
- Existing statistics are missing or insufficient for complex predicates.
- Predicates combine multiple AND/OR conditions on the same table.
- Predicates use expressions whose selectivity is hard for the optimizer to estimate.
- Columns have correlations or skewed data not adequately described by basic statistics.
- A SQL statement runs in parallel or has an applicable SQL plan directive.

The optimizer decides whether to sample based on existing statistics, dynamic statistics level, SQL structure, and other factors. Having a non-zero parameter does not mean every SQL statement performs sampling.

### 2.2 Operational Flow

~~~text
SQL statement is parsed
          |
          v
Optimizer reads object/column/index statistics
          |
          v
Evaluate if existing info is sufficient
          |
      +---+---+
      |       |
  Sufficient  Insufficient or directive exists
      |       |
      v       v
Estimate    Select eligible table/operation
via stats         |
                  v
          Recursive SQL samples blocks
                  |
                  v
          Estimate selectivity/cardinality
                  |
                  v
          Supplement info for optimizer
                  |
                  v
          Compare costs and choose execution plan
~~~

Sampling occurs during optimization. Sampling overhead typically increases parse time, in exchange for the optimizer potentially choosing a better execution plan. For long-running or frequently executed SQL, extra parse cost can be small relative to execution savings. For very short OLTP queries executed once, sampling can add to overall latency.

### 2.3 Dynamic Statistics Supplement Rather Than Replace Statistics

The optimizer still prefers standard statistics when they are sufficient. Dynamic statistics are used to supplement estimates not well described by current statistics, such as predicate cardinality, join cardinality, or GROUP BY cardinality where applicable.

When a table lacks statistics, dynamic sampling produces only a basic estimate within parse-time constraints; it is not necessarily as complete or accurate as controlled gathering via DBMS_STATS.

### 2.4 Costs and Limitations

- Recursive sampling adds work during parse/hard parse.
- Small samples may not accurately represent rare values or heavily skewed distributions.
- On workloads with heavy hard parsing, repeated sampling overhead can become significant.
- Results are not persistent table statistics replacing histograms/extended statistics.
- Dynamic statistics are not used for all SQL types; Oracle documents query-structure limitations, such as queries with an AS OF clause.
- Inspect execution plan notes to confirm whether the optimizer actually used dynamic statistics.

## 3. Dynamic Statistics Levels

The OPTIMIZER_DYNAMIC_SAMPLING parameter (the name is retained in modern Oracle Database) controls the conditions and sample size for dynamic statistics. It can be set at system, session, or statement-hint level.

Valid values are 0 through 11. The common default level is **2** when OPTIMIZER_FEATURES_ENABLE is 10.0.0 or higher.

### 3.1 Meaning of Each Level

The following table summarizes level behavior per the SQL Tuning Guide:

| Level | When the Optimizer Uses Dynamic Statistics | Sample Size |
|---:|---|---:|
| 0 | Do not use dynamic statistics | Not applicable |
| 1 | Nonpartitioned table lacks statistics, has no indexes, and meets block-count conditions | 32 blocks |
| 2 | At least one table in the statement lacks statistics; this is the default | 64 blocks |
| 3 | Level 2 conditions or an expression in a WHERE predicate | 64 blocks |
| 4 | Level 3 conditions or complex AND/OR predicates on the same table | 64 blocks |
| 5 | Same criteria as level 4, larger sample | 128 blocks |
| 6 | Same criteria as level 4, larger sample | 256 blocks |
| 7 | Same criteria as level 4, larger sample | 512 blocks |
| 8 | Same criteria as level 4, larger sample | 1,024 blocks |
| 9 | Same criteria as level 4, larger sample | 4,086 blocks |
| 10 | Same criteria as level 4, scan all blocks | All blocks |
| 11 | Adaptive dynamic sampling; optimizer decides when needed | Automatically determined |

Level 11 is not simply "take the largest sample." It lets the optimizer adaptively control dynamic statistics and determine an internal sampling budget when cardinality verification is needed. Exact conditions still depend on release and optimizer environment.

### 3.2 Level 0: Disabling Dynamic Statistics

~~~sql
ALTER SESSION SET OPTIMIZER_DYNAMIC_SAMPLING = 0;
~~~

This level can be useful when eliminating sampling overhead in a benchmark or when reliable statistics already exist and low parse latency is required. Do not disable it globally just because one query has high parse time; identify the statement and impact first.

### 3.3 Level 2: Common Default

At level 2, the optimizer uses dynamic statistics when at least one table in the statement lacks statistics and the level's conditions are met. Level 2 does not mean the optimizer samples every unanalyzed table in every statement type.

### 3.4 Level 4: Handling Complex Predicates

Level 4 expands sampling conditions to expressions and complex combined AND/OR predicates on the same table. For example:

~~~sql
SELECT *
FROM customers c
WHERE SUBSTR(c.last_name, 1, 3) = 'SMI'
  AND (c.city = 'Los Angeles' OR c.city = 'San Diego');
~~~

The optimizer may struggle to estimate expressions and relationships among conditions without appropriate expression/column-group statistics.

### 3.5 Level 11: Adaptive Dynamic Statistics

Level 11 lets the optimizer automatically decide when and at what sampling level dynamic statistics are needed. In supporting releases, adaptive dynamic sampling can also incorporate information from SQL plan directives and parallel execution.

Do not blindly raise every session to level 11 without measuring. Sampling incurs parse cost; on workloads with many short SQL statements, extra parse overhead can outweigh benefits.

## 4. Configuring Dynamic Statistics

### 4.1 Viewing Current Values

In SQL*Plus or SQLcl:

~~~sql
SHOW PARAMETER optimizer_dynamic_sampling;
SHOW PARAMETER optimizer_features_enable;
~~~

Or query:

~~~sql
SELECT name, value, isdefault, isses_modifiable, issys_modifiable
FROM v$parameter
WHERE name IN (
    'optimizer_dynamic_sampling',
    'optimizer_features_enable'
);
~~~

### 4.2 Setting at Session Level

To test a level in a test session:

~~~sql
ALTER SESSION SET optimizer_dynamic_sampling = 4;
~~~

Session-level changes allow comparing the same workload at different levels without altering instance-wide configuration.

### 4.3 Setting via SQL Hint

You can specify a level for one statement:

~~~sql
SELECT /*+ DYNAMIC_SAMPLING(4) */
       c.customer_id,
       c.city,
       c.state_province
FROM customers c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';
~~~

Or specify a table alias:

~~~sql
SELECT /*+ DYNAMIC_SAMPLING(c 4) */
       c.customer_id
FROM customers c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';
~~~

Hints are a narrow-scope testing method. Check the hint report and plan notes to see whether the hint was accepted by the optimizer or ignored due to alias, syntax, or inapplicable conditions.

### 4.4 Verifying in the Execution Plan

Example using EXPLAIN PLAN:

~~~sql
EXPLAIN PLAN FOR
SELECT /*+ DYNAMIC_SAMPLING(c 4) */
       c.customer_id
FROM customers c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

When dynamic statistics are used, the Note section of the plan may display text such as:

~~~text
Note
-----
 - dynamic statistics used: dynamic sampling (level=4)
~~~

Exact notes vary by version, statement, and active optimizer features.

### 4.5 Do Not Make High Levels the Default for Every SQL

Higher levels can improve estimates, yet also increase parse cost and risk repeated sampling in high-hard-parse workloads. Instead:

1. Collect plans and runtime statistics.
2. Locate predicates/operations with inaccurate estimates.
3. Inspect statistics, histograms, column group, and expression statistics.
4. Test hints or session levels in a controlled environment.
5. Compare parse time, execution time, buffers, and throughput.
6. Apply broadly only with evidence across the entire workload.

## 5. Cardinality Feedback and Statistics Feedback

**Cardinality feedback** was the name used for the feedback mechanism starting in Oracle Database 11g. In Oracle Database 12c documentation and newer releases, the standard name is **statistics feedback**.

Core idea: the optimizer creates an initial plan based on statistics and estimates. After the first execution, the database can compare predicted row counts against actual row counts at each row source. If the discrepancy is large enough and the statement qualifies, the optimizer saves feedback information to re-optimize on subsequent executions.

### 5.1 Statistics Feedback Lifecycle

~~~text
First execution
       |
       v
Optimizer builds plan with E-Rows
       |
       v
Statement executes and produces A-Rows
       |
       v
Compare estimate vs actual rows
       |
       v
Significant discrepancy and eligible?
       |
   +---+---+
   |       |
   No     Yes
   |       |
   v       v
No       Save statistics feedback
feedback          |
                  v
          Cursor marked eligible
          for reoptimization
                  |
                  v
          Next execution hard-parses /
          reoptimizes with new info
                  |
                  v
          May choose a different plan
~~~

Feedback does not mean Oracle directly modifies NUM_ROWS or histograms in the table's data dictionary. It is supplementary information for re-optimizing the statement. To update object statistics, still use DBMS_STATS.

### 5.2 Conditions That Commonly Trigger Feedback Monitoring

The optimizer may monitor statistics feedback in the shared SQL area for cases such as:

- Tables lacking statistics.
- A table with multiple conjunctive or disjunctive filter predicates.
- Predicates containing complex operators that make selectivity hard for the optimizer to compute.
- Initial estimates differing significantly from actual cardinality.

Not every SQL receives feedback. A statement executed only once has no opportunity to use feedback on a later run. Cursors can also age out, be invalidated, or no longer match subsequent runs.

### 5.3 E-Rows and A-Rows

To view estimated and actual row counts, run the statement with runtime plan statistics:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       oi.product_id
FROM orders o
JOIN order_items oi
  ON oi.order_id = o.order_id
WHERE o.order_date >= DATE '2025-01-01'
  AND o.status = 'SHIPPED';
~~~

After fetching all rows, view the cursor plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +NOTE +PREDICATE'
    )
);
~~~

Key columns to inspect:

| Column | Meaning |
|---|---|
| E-Rows | Row count estimated by the optimizer |
| A-Rows | Actual row count returned by the operation |
| Starts | Number of times the operation started |
| A-Time | Recorded execution time |
| Buffers | Logical reads |
| Reads | Recorded physical reads |

If A-Rows and E-Rows diverge sharply at an operation, find the cause in that predicate or operation. An error in an input row source can propagate into large errors in joins higher up.

### 5.4 Seeing Statistics Feedback in the Plan

After the subsequent run, the plan may show a Note:

~~~text
Note
-----
 - statistics feedback used for this statement
~~~

When feedback is used, E-Rows may align more closely with A-Rows and the optimizer may choose a different plan. Do not judge solely by plan hash; compare operations, E-Rows/A-Rows, buffers, and elapsed time.

### 5.5 Checking Cursors Eligible for Reoptimization

Oracle exposes the IS_REOPTIMIZABLE column in V$SQL:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       is_reoptimizable,
       plan_hash_value,
       sql_text
FROM v$sql
WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%';
~~~

Common values:

- Y: the next execution matching this child cursor may trigger reoptimization.
- R: the cursor has reoptimization information, but is in reporting-only mode and will not trigger plan changes.
- N: the cursor has no reoptimization information.

This is a child cursor state, not a promise that the next run is guaranteed to get a better plan.

### 5.6 Checking Hard Parses Caused by Feedback

V$SQL_SHARED_CURSOR includes the USE_FEEDBACK_STATS column. A value of Y indicates a hard parse was forced so the optimizer can re-optimize the query with better inputs such as cardinality estimates:

~~~sql
SELECT sql_id,
       child_number,
       use_feedback_stats,
       reason
FROM v$sql_shared_cursor
WHERE sql_id = :p_sql_id;
~~~

V$SQL_SHARED_CURSOR helps explain why a child cursor was not shared with an existing cursor. Inspect REASON alongside other mismatch columns, since not every new child cursor comes from statistics feedback.

## 6. SQL Plan Directives

A SQL plan directive (SPD) is supplementary information automatically created by the optimizer when it detects certain patterns of cardinality misestimation. Think of a directive as a note to the optimizer: "For this predicate/expression pattern, previous estimates were poor; next time gather extra information or collect appropriate extended statistics."

Directives are not tied to a single SQL_ID. Oracle can record directives on query expressions or predicate patterns so other structurally similar statements can also benefit.

### 6.1 When Are Directives Created?

Oracle automatically creates SQL plan directives based on data gathered from automatic reoptimization. For example:

- The optimizer significantly misestimates the cardinality of a predicate combining two columns.
- Two tables join on columns with data skew.
- The optimizer detects missing column-group statistics for correlated predicates.

Directives are created automatically; users do not manually create new directives with a SQL statement. Directives can be managed with the DBMS_SPD package.

### 6.2 How Are Directives Used?

When parsing a statement, the optimizer can:

1. Check whether an applicable directive exists for the table or query expression.
2. If required information is missing, use dynamic statistics to sample.
3. If a missing column group is detected and AUTO_STAT_EXTENSIONS is enabled, DBMS_STATS can create column-group statistics during the next gather.
4. Once appropriate extended statistics exist, the optimizer can use them instead of the directive where applicable.

Starting in Oracle Database 12c Release 2 (12.2), results of adaptive dynamic sampling can be persisted in the SQL plan directives store for reuse by other queries.

### 6.3 Column Groups and AUTO_STAT_EXTENSIONS

Example of two correlated columns:

~~~sql
WHERE city = 'Los Angeles'
  AND state_province = 'CA'
~~~

You can create column-group statistics explicitly:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CUSTOMERS',
           extension => '(CITY, STATE_PROVINCE)'
       ) AS extension_name
FROM dual;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        cascade => TRUE
    );
END;
/
~~~

When a workload relies on multiple correlated columns, extended statistics are usually a more durable solution than relying on dynamic sampling at every hard parse.

Oracle provides the AUTO_STAT_EXTENSIONS preference. By default, this preference is OFF in standard release documentation. When set to ON, SQL plan directives can trigger column-group statistics creation during the next statistics gather:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        pname   => 'AUTO_STAT_EXTENSIONS',
        pvalue  => 'ON'
    );
END;
/
~~~

Do not enable it database-wide before evaluating impact on workloads and statistics management workflows. You can configure the preference at table/schema scope to limit impact.

### 6.4 Viewing SQL Plan Directives

DBA_SQL_PLAN_DIRECTIVES provides information about directives:

~~~sql
SELECT directive_id,
       type,
       enabled,
       state,
       reason,
       created,
       last_used
FROM dba_sql_plan_directives
ORDER BY created DESC;
~~~

DBA_SQL_PLAN_DIR_OBJECTS shows related objects and subobjects:

~~~sql
SELECT directive_id,
       owner,
       object_name,
       subobject_name,
       object_type,
       num_rows
FROM dba_sql_plan_dir_objects
ORDER BY directive_id, owner, object_name;
~~~

Common states:

- USABLE: the directive can be used by the optimizer.
- SUPERSEDED: the issue has already been addressed by a histogram, extension/column group, or a more suitable directive.

### 6.5 Managing Directives

DBMS_SPD provides APIs to enable/disable, flush, export, or drop directives. For example, flushing directives from memory to persistent storage:

~~~sql
BEGIN
    DBMS_SPD.FLUSH_SQL_PLAN_DIRECTIVE;
END;
/
~~~

If a directive causes unacceptable sampling overhead, the DBA can investigate and manage that specific directive. Do not bulk-delete directives to fix a plan issue without understanding the root cause.

### 6.6 A SQL Plan Directive Is Not a SQL Plan Baseline

| Concept | Role |
|---|---|
| SQL plan directive | Reminds the optimizer of poor cardinality estimate patterns and the need for extra statistics |
| SQL plan baseline | Manages the set of accepted plans for a SQL statement to control plan evolution |
| SQL profile | Supplements auxiliary statistics so the optimizer estimates better |
| SQL patch | Attaches hints to a statement without modifying SQL text |

Directives do not lock plans. They can prompt the optimizer to gather extra info and thus choose a different plan. Baselines are a plan management mechanism aimed at stabilizing and governing which plans are used.

## 7. Distinguishing Statistics Feedback from Adaptive Cursor Sharing

These two mechanisms are frequently confused because both can produce additional child cursors or different plans.

### 7.1 Statistics Feedback

Statistics feedback addresses discrepancies between the optimizer's estimated cardinality and actual rows from executed runs. Its focus is:

- E-Rows vs. A-Rows.
- Misestimates due to missing/inaccurate statistics or complex predicates.
- Using execution feedback to re-optimize subsequent runs.

### 7.2 Adaptive Cursor Sharing

Adaptive cursor sharing (ACS) handles SQL with bind variables where different bind values produce vastly different selectivities. A single plan may be great for a bind value returning a few rows, yet terrible for a bind value returning hundreds of thousands of rows.

Example:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = :dept_id;
~~~

If department 10 has only 2 employees while department 50 has 100,000 employees, a plan suited to department 10 may be poor for department 50.

The optimizer can mark the cursor bind-sensitive, track bind value behavior, and then mark it bind-aware. Oracle can then create multiple child cursors with different plans for different selectivity ranges.

### 7.3 Comparison Table

| Criterion | Statistics Feedback | Adaptive Cursor Sharing |
|---|---|---|
| Primary Problem | E-Rows differs from A-Rows | Bind values have differing selectivities |
| Learning Input | Actual row counts from execution | Bind value/selectivity and execution behavior |
| Adaptation Target | Cardinality estimates of statement/row sources | Child cursors and plans by bind selectivity |
| Trigger | Significant cardinality discrepancy and eligible statement | Cursor exhibits bind-sensitive behavior and benefits from another plan |
| Observation | Statistics feedback Note, IS_REOPTIMIZABLE, USE_FEEDBACK_STATS | IS_BIND_SENSITIVE, IS_BIND_AWARE, V$SQL_CS_* |
| Goal | More accurate estimates on subsequent parses | Choose plans matched to each bind value group |

### 7.4 Viewing Bind-Sensitive and Bind-Aware Cursors

~~~sql
SELECT sql_id,
       child_number,
       executions,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable,
       plan_hash_value
FROM v$sql
WHERE sql_text LIKE '%FROM employees%'
  AND sql_text LIKE '%department_id = :%';
~~~

Additional views:

- V$SQL_CS_HISTOGRAM: distribution of execution counts in the internal cursor-sharing histogram.
- V$SQL_CS_SELECTIVITY: selectivity ranges for bound predicates.
- V$SQL_CS_STATISTICS: rows processed, buffer gets, and CPU time used to decide whether a cursor should become bind-aware.

### 7.5 Histograms Remain Important

ACS often needs the optimizer to recognize that binds can yield differing cardinalities. Histograms describe data skew and improve selectivity estimates during bind peeking. Do not treat ACS as a reason to drop histograms or skip gathering statistics.

## 8. How Do These Mechanisms Complement Each Other?

Suppose a multi-table join query has predicates on two correlated columns and uses bind variables:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status
  AND o.region = :region;
~~~

A sequence of events can unfold:

1. The optimizer uses table/column statistics and histograms to estimate cardinality.
2. If statistics are insufficient, dynamic statistics may sample at parse time.
3. After execution, statistics feedback may detect that E-Rows diverges sharply from A-Rows.
4. If the query expression causes recurring misestimates, a SQL plan directive can record the pattern.
5. If bind values have vastly different selectivities, adaptive cursor sharing can create child cursors with different plans.
6. If the workload needs plan stability after tuning, SQL plan management can govern an accepted baseline.

## 9. Oracle Database Version Differences

Terminology and parameters have evolved across releases. When reading older documentation or upgrading databases, distinguish feature names, parameter names, and defaults.

### 9.1 Oracle Database 11g

- Cardinality feedback was introduced so the optimizer could learn from discrepancies between estimated and actual rows.
- Dynamic sampling was the name used for block sampling during optimization.
- OPTIMIZER_DYNAMIC_SAMPLING controlled sampling level; common default was 2 when optimizer features corresponded to 10g or higher.
- Adaptive cursor sharing and bind-sensitive/bind-aware cursors were also mechanisms to consider for SQL using bind variables on skewed data.

In this release, the term cardinality feedback commonly appears in documentation and technical articles.

### 9.2 Oracle Database 12c Release 1 (12.1)

- Dynamic sampling was renamed dynamic statistics.
- Adaptive query optimization appeared, comprising adaptive plans and adaptive statistics.
- The term statistics feedback replaced cardinality feedback in newer documentation.
- SQL plan directives were used to store info on query expressions with cardinality misestimates and could direct the optimizer to use dynamic statistics or assist extended statistics.
- Adaptive features in 12.1 were grouped under OPTIMIZER_ADAPTIVE_FEATURES; keep this in mind when reading 12.1 configurations versus 12.2 onward.

Do not apply 12.2 defaults directly to 12.1. Verify the exact patch level and parameter values of your database.

### 9.3 Oracle Database 12c Release 2 (12.2)

This marked a major configuration change:

- OPTIMIZER_ADAPTIVE_FEATURES was removed/desupported.
- OPTIMIZER_ADAPTIVE_PLANS was split out separately, defaulting to TRUE.
- OPTIMIZER_ADAPTIVE_STATISTICS was split out separately, defaulting to FALSE.
- OPTIMIZER_ADAPTIVE_STATISTICS = TRUE enables adaptive statistics features such as SQL plan directives, statistics feedback for join cardinality, performance feedback, and adaptive dynamic sampling.
- Setting OPTIMIZER_ADAPTIVE_STATISTICS = FALSE still retains statistics feedback for single-table cardinality misestimates introduced in 11g.

Thus, "adaptive plans" and "adaptive statistics" are two separate configuration groups starting in 12.2. Do not disable adaptive plans just because you want to disable adaptive statistics.

### 9.4 Oracle Database 18c and 19c

The 12.2 configuration principles continue to apply:

| Parameter | Common Default | Role |
|---|---|---|
| OPTIMIZER_ADAPTIVE_PLANS | TRUE | Adaptive plans, e.g., switching nested loops/hash join or parallel distribution at runtime |
| OPTIMIZER_ADAPTIVE_STATISTICS | FALSE | Adaptive statistics: join statistics feedback, SQL plan directive usage, and adaptive dynamic sampling |
| OPTIMIZER_DYNAMIC_SAMPLING | 2 | Conditions and sample size for dynamic statistics |
| OPTIMIZER_ADAPTIVE_REPORTING_ONLY | FALSE | When TRUE, collects adaptive info without altering plans; reports viewable via DBMS_XPLAN |

Note: OPTIMIZER_ADAPTIVE_STATISTICS = FALSE does not disable all forms of statistics feedback. Single-table statistics feedback remains active. Reference documentation also clarifies that SQL plan directives can still be created, though when adaptive statistics is disabled they are not used to refine plans via dynamic sampling.

### 9.5 Oracle Database 21c

21c continues using the names statistics feedback and dynamic statistics. OPTIMIZER_ADAPTIVE_STATISTICS still defaults to FALSE; OPTIMIZER_ADAPTIVE_PLANS remains a separate setting. Default dynamic statistics level remains typically 2, unless OPTIMIZER_FEATURES_ENABLE or session/system settings are modified.

SQL plan directives, DBA_SQL_PLAN_DIRECTIVES, and DBMS_SPD continue to be documented in 21c. Inspect directive state, usage, and hard-parse costs rather than assuming every directive improves performance.

### 9.6 Oracle Database 23ai and Oracle AI Database 26ai

In 23ai/26ai documentation:

- Statistics feedback continues as the modern name for cardinality feedback.
- Dynamic statistics remains the active terminology; dynamic sampling is the pre-12.1 historical name.
- OPTIMIZER_ADAPTIVE_STATISTICS defaults to FALSE.
- OPTIMIZER_ADAPTIVE_PLANS remains a separate parameter and defaults to TRUE in current documentation.
- OPTIMIZER_DYNAMIC_SAMPLING still controls levels 0 through 11; level 11 enables adaptive dynamic sampling.
- Views V$SQL, V$SQL_SHARED_CURSOR, DBA_SQL_PLAN_DIRECTIVES, and DBMS_XPLAN remain key diagnostic tools.

26ai can introduce new optimizer features and alter plan selection compared to 19c/21c. Do not assume a SQL statement will always keep the exact same plan after an upgrade merely because adaptive statistics parameters share the same defaults.

### 9.7 Release Milestone Table

| Release | Notable Names/Changes | Configuration Notes |
|---|---|---|
| 11g | Cardinality feedback; dynamic sampling | Feedback starts learning from executions; dynamic sampling uses older name |
| 12.1 | Dynamic statistics; statistics feedback; adaptive query optimization; SQL plan directives | Adaptive features grouped under OPTIMIZER_ADAPTIVE_FEATURES |
| 12.2 | Split adaptive plans and adaptive statistics | OPTIMIZER_ADAPTIVE_FEATURES removed; ADAPTIVE_PLANS TRUE, ADAPTIVE_STATISTICS FALSE by default |
| 18c/19c | Continues statistics feedback, SQL plan directives, dynamic statistics | ADAPTIVE_STATISTICS FALSE by default; single-table feedback retained |
| 21c | Same 12.2+ model | Check views and plan notes |
| 23ai | Newer optimizer feature set, continues current mechanisms | Verify OFE and patch level |
| 26ai | Documentation titled Oracle AI Database; continues statistics feedback and dynamic statistics | Do not assume identical plans/optimizer feature defaults as older releases |

### 9.8 How Does OPTIMIZER_FEATURES_ENABLE Affect Behavior?

OPTIMIZER_FEATURES_ENABLE is an umbrella parameter enabling optimizer feature groups matching a release. After an upgrade, if a database retains an older OFE value, optimizer behavior may differ from a fresh installation using the new release's default OFE.

Check current values:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'optimizer_features_enable',
    'optimizer_adaptive_plans',
    'optimizer_adaptive_statistics',
    'optimizer_adaptive_reporting_only',
    'optimizer_dynamic_sampling'
)
ORDER BY name;
~~~

Do not use ALTER SYSTEM SET OPTIMIZER_FEATURES_ENABLE to fix a single slow query. OFE has broad impact on the optimizer and can change many execution plans. When testing old vs. new behavior, set it in a test session, record plans, and compare a representative workload.

## 10. Lab: Observing Cardinality Misestimates and Dynamic Statistics

The following lab creates a table with two strongly correlated columns. The goal is to illustrate why individual column statistics can fail to capture relationships between two columns.

### 10.1 Create Test Data Table

~~~sql
CREATE TABLE cardinality_lab AS
SELECT level AS id,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'Los Angeles'
           ELSE 'New York'
       END AS city,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'CA'
           ELSE 'NY'
       END AS state_province
FROM dual
CONNECT BY level <= 100000;
~~~

In this data:

- Roughly 1% of rows have CITY = Los Angeles and STATE_PROVINCE = CA.
- Roughly 99% of rows have CITY = New York and STATE_PROVINCE = NY.
- The two columns are almost completely correlated.

### 10.2 Gather Basic Statistics Without Histograms

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'CARDINALITY_LAB',
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade    => TRUE
    );
END;
/
~~~

SIZE 1 prevents creating histograms for the columns in this example. The purpose is to observe estimates built from single-column statistics, not a recommended configuration for all production tables.

### 10.3 Count Actual Rows

~~~sql
SELECT COUNT(*) AS actual_rows
FROM cardinality_lab
WHERE city = 'Los Angeles'
  AND state_province = 'CA';
~~~

Expected result is around 1,000 rows.

### 10.4 View Plan with Existing Statistics

~~~sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM cardinality_lab c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

The optimizer may treat the two predicates as independent and multiply each column's selectivity. E-Rows can then diverge noticeably from actual rows.

### 10.5 Test Dynamic Statistics via Hint

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS DYNAMIC_SAMPLING(c 4) */
       COUNT(*)
FROM cardinality_lab c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';
~~~

After executing, inspect the cursor:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +NOTE +PREDICATE'
    )
);
~~~

Observe E-Rows, A-Rows, and the Note on dynamic statistics. Sampled estimates may not match actual rows identically; the goal is to improve estimation and plan selection.

### 10.6 Test Extended Column-Group Statistics

Create column group:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CARDINALITY_LAB',
           extension => '(CITY, STATE_PROVINCE)'
       ) AS extension_name
FROM dual;
~~~

Re-gather statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'CARDINALITY_LAB',
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade    => TRUE
    );
END;
/
~~~

Re-run the query and inspect E-Rows. Column-group statistics provide a more durable model of the correlation between the two columns, helping the optimizer estimate well without relying on sampling on every parse.

### 10.7 Clean Up Lab Data

~~~sql
DROP TABLE cardinality_lab PURGE;
~~~

Run this cleanup command only if this is the lab table you just created and it holds no data that needs to be kept.

## 11. Adaptive Plans Are Not the Same as Statistics Feedback

Adaptive query plans and statistics feedback both use runtime information, but they adapt at different times.

### 11.1 Adaptive Plans

An adaptive plan contains pre-built alternative subplans within the plan. During the current execution, Oracle collects runtime statistics (such as rows passing through a row source) and picks the suitable branch among the pre-built choices.

For example, an adaptive plan may prepare both nested loops and hash join. During execution, runtime optimizer statistics can select one branch while the other branch becomes inactive.

### 11.2 Statistics Feedback / Automatic Reoptimization

Statistics feedback uses information collected from an execution to improve estimates when the statement is re-optimized on a subsequent run. It can result in a new plan generated on the next parse/reoptimization.

### 11.3 Comparing Adaptation Timing

| Mechanism | When Does It Adapt? | What Changes? |
|---|---|---|
| Adaptive plan | During the current execution | Selects a branch from pre-built plan options |
| Statistics feedback | On reoptimization after execution | Estimate/cardinality inputs and potentially the execution plan |
| Dynamic statistics | Before plan selection, during parse | Supplements estimates via sampling |
| Adaptive cursor sharing | Across executions with differing bind values | Child cursor/plan per selectivity range |

Do not use the word "adaptive" as if every mechanism works the same way. Clarify whether you mean adaptive plans, adaptive statistics, or adaptive cursor sharing.

## 12. Workflow for Diagnosing Cardinality Misestimates in Real Systems

When a SQL statement is slow, start from the actual execution plan and object statistics.

### 12.1 Step 1: Identify SQL_ID and Child Cursors

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       is_reoptimizable,
       is_bind_sensitive,
       is_bind_aware,
       sql_text
FROM v$sql
WHERE sql_text LIKE '%unique_fragment_of_query%';
~~~

If the SQL has multiple child cursors, do not look only at child 0. Children may differ in plan, bind peeking, optimizer environment, or non-sharing reasons.

### 12.2 Step 2: View Plan with Runtime Statistics

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +NOTE +PREDICATE +PEEKED_BINDS'
    )
);
~~~

Focus on:

- E-Rows and A-Rows at each operation.
- Starts: whether an operation ran multiple times.
- Buffers, Reads, A-Time.
- Predicate Information to identify filter/access predicates.
- Notes on dynamic statistics or statistics feedback.
- Peeked binds if the plan was generated using bind peeking.

Do not substitute EXPLAIN PLAN for the runtime plan when you need A-Rows. EXPLAIN PLAN only shows an explained plan in the current environment, not necessarily the actual plan/child cursor that ran in the session.

### 12.3 Step 3: Locate the First Divergent Operation

A plan may have several operations where E-Rows differs from A-Rows. Find the lowest operation in the tree where the discrepancy first appears. If an input row source is wrong, parent operations may simply reflect propagated error.

Example:

~~~text
TABLE ACCESS FULL CUSTOMERS
  E-Rows = 10
  A-Rows = 500000

HASH JOIN ORDERS/CUSTOMERS
  E-Rows = 100
  A-Rows = 480000
~~~

In this example, the discrepancy begins at TABLE ACCESS FULL CUSTOMERS. Focus on predicates, histograms, column groups, and data in CUSTOMERS before tuning the join above it.

### 12.4 Step 4: Check Table Statistics

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name IN ('CUSTOMERS', 'ORDERS');
~~~

Check:

- Do statistics exist?
- Is LAST_ANALYZED too old relative to data changes?
- Is STALE_STATS equal to YES?
- Are NUM_ROWS/BLOCKS reasonable relative to actual size?
- Are statistics locked or ungathered after a bulk load?

### 12.5 Step 5: Check Column Statistics and Histograms

~~~sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'CUSTOMERS'
ORDER BY column_name;
~~~

If data is skewed, a histogram may be needed. If two columns are correlated, separate single-column histograms may still fall short; check column-group statistics.

### 12.6 Step 6: Inspect Predicate Usage

DBMS_STATS.REPORT_COL_USAGE shows how columns are used in predicates, joins, group by, or expressions in the workload:

~~~sql
SELECT DBMS_STATS.REPORT_COL_USAGE(
           ownname => USER,
           tabname => 'CUSTOMERS'
       )
FROM dual;
~~~

This information helps decide whether column-group or expression statistics are needed. Create extended statistics based on actual workload needs rather than creating groups for every column combination.

### 12.7 Step 7: Check Dynamic Statistics and Feedback

Check plan Notes to see whether dynamic statistics or statistics feedback was used. If reoptimization is suspected:

~~~sql
SELECT sql_id,
       child_number,
       is_reoptimizable,
       plan_hash_value,
       executions
FROM v$sql
WHERE sql_id = :p_sql_id;
~~~

Check child cursor mismatches:

~~~sql
SELECT child_number,
       use_feedback_stats,
       bind_mismatch,
       optimizer_mismatch,
       stats_row_mismatch,
       reason
FROM v$sql_shared_cursor
WHERE sql_id = :p_sql_id;
~~~

Mismatch column names may vary by release. Query only columns present in your running version's data dictionary.

### 12.8 Step 8: Check SQL Plan Directives If Privileged

~~~sql
SELECT directive_id,
       type,
       enabled,
       state,
       reason,
       last_used,
       notes
FROM dba_sql_plan_directives
WHERE state = 'USABLE'
ORDER BY last_used DESC;
~~~

If a plan note mentions a SQL plan directive, use DIRECTIVE_ID and DBA_SQL_PLAN_DIR_OBJECTS to find related objects. One directive can apply across multiple statements sharing a query expression.

### 12.9 Step 9: Test Fixes by Scope

Prioritize fixes in order:

1. Gather or fix baseline optimizer statistics.
2. Add histograms if data is skewed and the workload needs them.
3. Add column-group/expression statistics if predicates have correlations or expressions.
4. Use dynamic statistics at session/statement level if sampling yields clear benefits.
5. Evaluate SQL plan directives and adaptive statistics settings.
6. Use SQL plan management if plan control is needed after tuning.

After each change, re-run with identical inputs/bind values and compare E-Rows/A-Rows, buffers, elapsed time, and parse time.

## 13. Best Practices for Dynamic Statistics and Feedback

### 13.1 Keep Baseline Optimizer Statistics Accurate

This is the foundation. Dynamic statistics and feedback are supplementary mechanisms; they should not be used to compensate for tables left without statistics gathers for long periods.

### 13.2 Handle Skew Properly with Histograms

If one value dominates a table, histograms help the optimizer estimate equality predicates accurately. Choose histograms based on workload and bind patterns; avoid creating too many histograms that make plans volatile.

### 13.3 Handle Correlations with Extended Statistics

When multiple columns always appear together under business rules, column-group statistics are more durable than waiting for statistics feedback. Dynamic sampling can help during parse, but does not replace deliberately modeling data relationships.

### 13.4 Assess Parse Overhead

Dynamic statistics run during parse. If an application hard-parses heavily or runs very short queries, sampling overhead can become substantial. Monitor parse time and hard-parse counts alongside execution time.

### 13.5 Do Not Set Adaptive Statistics TRUE Just to Fix One Query

OPTIMIZER_ADAPTIVE_STATISTICS affects multiple mechanisms at session/instance scope. When testing, start at session scope in a test environment and measure related workloads. Avoid system-wide changes based on a single execution plan.

### 13.6 Control Plan Changes During Upgrades

A new release can introduce different optimizer transformations, costing, and defaults. Before upgrading:

- Capture a representative SQL workload.
- Record SQL_ID, plan hashes, E-Rows/A-Rows, and runtime metrics.
- Check OPTIMIZER_FEATURES_ENABLE.
- Test in the target environment with production-like statistics and bind values.
- Use SQL plan baselines or plan management tools if the application requires risk control.

### 13.7 Do Not Force High Dynamic Sampling Levels on All Statements

The DYNAMIC_SAMPLING hint is helpful for verifying hypotheses on a single statement. If a hint is needed in production, document the reason, scope, measured results, and removal plan once baseline statistics are improved.

### 13.8 Do Not Mistake Feedback for Result Caching

Statistics feedback does not cache result rows and never returns stale query data. It is information for the optimizer to estimate cardinality and potentially pick a better plan on a subsequent parse. Query results are still read from data under standard transaction semantics.

### 13.9 Measure Both Initial and Subsequent Runs

Statistics feedback may take effect only after the first execution. Measuring only once can miss the reoptimization benefit or hide extra hard-parse costs. Measure multiple runs and distinguish cold cursors from warmed cursors.

## 14. Common Misconceptions

| Misconception | Reality |
|---|---|
| Dynamic statistics is gathering table statistics | Dynamic statistics samples during parse to supplement estimates; DBMS_STATS manages object statistics |
| Dynamic sampling level 11 always scans the whole table | Level 11 is adaptive; sample size is determined automatically by the optimizer |
| OPTIMIZER_DYNAMIC_SAMPLING is unrelated to dynamic statistics | That is the parameter name still used for dynamic statistics |
| Cardinality feedback edits NUM_ROWS in the dictionary | Feedback is info for reoptimization, not a replacement for DBMS_STATS |
| Statistics feedback runs for every SQL | Only eligible statements are monitored and use feedback |
| OPTIMIZER_ADAPTIVE_STATISTICS FALSE disables all feedback | Single-table statistics feedback from 11g remains active |
| Adaptive plans and adaptive statistics are the same thing | Since 12.2 they have separate parameters and distinct purposes |
| SQL plan directives lock execution plans | Directives record misestimate patterns and can trigger extra statistics |
| SQL plan directives apply to only one SQL_ID | Directives are defined by query expression and can apply to similar statements |
| Adaptive cursor sharing is the same as statistics feedback | ACS handles bind selectivity; statistics feedback handles estimate/actual discrepancies |
| E-Rows differing from A-Rows is always an optimizer bug | Can stem from starts, parallel execution, bind values, predicates, or plan reading; analyze per operation |
| Higher dynamic statistics levels are always better | Larger sampling can raise parse cost and does not benefit every workload |
| After an upgrade plans are always identical to the old release | Optimizer features, transformations, and costing can change across releases |

## 15. Common Diagnostic Issues

| Issue | Possible Cause | Resolution Direction |
|---|---|---|
| Plan still misestimates after stats gather | Correlated predicates, skew, expressions, or join cardinality | Check histograms, column groups, dynamic stats, and feedback |
| Dynamic statistics does not appear in plan | Level/conditions unmet, statistics already sufficient, or hint ignored | Check parameters, hint report, and plan Note |
| Parse time rises after enabling dynamic statistics | Extra sampling during hard parse | Measure parse overhead; limit hint/level by workload |
| First run slow, subsequent runs fast | Cache warm-up or statistics feedback | Separate cache effects from reoptimization; inspect V$SQL |
| Multiple child cursors exist | Bind selectivity, optimizer environment, feedback, or other mismatch | Inspect V$SQL_SHARED_CURSOR and ACS views |
| Statistics feedback is not used | Statement ineligible, not re-run, or cursor replaced | Check IS_REOPTIMIZABLE and USE_FEEDBACK_STATS |
| SQL plan directive exists but has no effect | Directive disabled/unusable or adaptive statistics usage disabled | Check ENABLED, STATE, parameters, and plan notes |
| Column group not auto-created | AUTO_STAT_EXTENSIONS is OFF or stats not gathered | Check preference and create extension explicitly if needed |
| New plan better for one bind but worse for another | Varying bind selectivities | Check histograms and adaptive cursor sharing |
| Test results differ from production | Different data volume/skew, binds, cache, or optimizer environment | Use representative inputs and conditions |

## 16. Checklist Before Changing Optimizer Parameters

Before modifying dynamic statistics or adaptive settings, confirm:

1. Did you retrieve the actual execution plan from the cursor cache?
2. Did you inspect E-Rows and A-Rows per row source?
3. Did you locate the first operation with a cardinality misestimate?
4. Are table statistics missing, stale, or locked?
5. Do histograms capture data skew?
6. Are predicates across multiple columns correlated?
7. Are expression predicates or functions complicating estimation?
8. Are there bind values with differing selectivities?
9. Did you check statistics feedback and adaptive cursor sharing?
10. Are there relevant SQL plan directives?
11. Were dynamic statistics actually used in the plan Note?
12. Did you measure parse time and hard-parse overhead?
13. Did you test session-level or statement-level before system-level?
14. Did you compare both the first run and subsequent runs?
15. Did you test on the exact release, patch level, and OPTIMIZER_FEATURES_ENABLE?
16. Are extended statistics needed instead of repeated sampling?
17. After improving a plan, did other bind values or workloads slow down?
18. Is there a rollback plan if the change causes a regression?

## 17. Summary

Dynamic statistics, cardinality feedback, and SQL plan directives are mechanisms helping Oracle improve cardinality information during optimization:

- **Dynamic statistics** sample blocks during parse to supplement estimates when optimizer statistics are missing or insufficient. Its pre-12.1 name was dynamic sampling.
- **Cardinality feedback**, currently named **statistics feedback**, compares estimates against actual rows after execution and can re-optimize the statement on subsequent runs.
- **SQL plan directives** remember query expressions with cardinality misestimates, directing the optimizer to use dynamic statistics or assisting column-group statistics collection.
- **Adaptive cursor sharing** addresses bind values with differing selectivities that may need separate child cursors/plans.
- **Adaptive plans** switch branches within the current plan; statistics feedback typically affects subsequent reoptimization.
- Starting in Oracle Database 12.2, OPTIMIZER_ADAPTIVE_FEATURES was split into OPTIMIZER_ADAPTIVE_PLANS (default TRUE) and OPTIMIZER_ADAPTIVE_STATISTICS (default FALSE). Single-table statistics feedback from 11g remains active when adaptive statistics is off.
- The default dynamic statistics level is typically 2; level 11 enables adaptive dynamic sampling. Do not raise levels globally without measuring parse overhead.
- When diagnosing, start with the actual plan, E-Rows/A-Rows, table/column statistics, bind values, plan notes, and V$SQL/V$SQL_SHARED_CURSOR views.

The goal is not to enable every adaptive feature. The goal is to pinpoint why an estimate was wrong, supply the right information to the optimizer, and verify execution plan improvements against a real workload.

## 18. Oracle Reference Documentation

- Oracle Database 19c SQL Tuning Guide, “Optimizer Statistics Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html
- Oracle Database 19c SQL Tuning Guide, “Configuring Options for Dynamic Statistics”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/options-for-optimizer-statistics-gathering.html
- Oracle Database 19c SQL Tuning Guide, “Query Optimizer Concepts / Statistics Feedback”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-optimizer-concepts.html
- Oracle Database 19c Database Reference, “OPTIMIZER_ADAPTIVE_STATISTICS”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/OPTIMIZER_ADAPTIVE_STATISTICS.html
- Oracle Database 19c Database Reference, “OPTIMIZER_DYNAMIC_SAMPLING”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/OPTIMIZER_DYNAMIC_SAMPLING.html
- Oracle Database 19c Database Reference, “V$SQL” and “V$SQL_SHARED_CURSOR”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html and https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_SHARED_CURSOR.html
- Oracle Database 21c SQL Tuning Guide, “Optimizer Statistics Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/21/tgsql/optimizer-statistics-concepts.html
- Oracle Database 21c SQL Tuning Guide, “Configuring Options for Dynamic Statistics”: https://docs.oracle.com/en/database/oracle/oracle-database/21/tgsql/options-for-optimizer-statistics-gathering.html
- Oracle AI Database 26ai SQL Tuning Guide, “Query Optimizer Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/26/tgsql/query-optimizer-concepts.html
- Oracle AI Database 26ai Database Reference, “OPTIMIZER_ADAPTIVE_STATISTICS” and “OPTIMIZER_DYNAMIC_SAMPLING”: https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/OPTIMIZER_ADAPTIVE_STATISTICS.html and https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/OPTIMIZER_DYNAMIC_SAMPLING.html

Not all mechanisms activate within the same statement. They have distinct conditions, parameters, and scopes.

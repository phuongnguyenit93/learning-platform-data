# SQL Plan Management, Baselines, and Plan Regression Control

A single SQL statement can have multiple valid execution plans. When statistics, data, bind values, indexes, optimizer parameters, or the Oracle version change, the optimizer may pick a different plan. Sometimes the new plan is better, yet it can also be much slower and cause a performance regression in the application. **SQL Plan Management (SPM)** helps control this change by preserving accepted plans for a SQL statement and steering the optimizer to favor plans known to be suitable.

The core component of SPM is the **SQL plan baseline**. A baseline is not a single frozen execution plan. It is a set of recorded and accepted plans for a SQL statement. The optimizer can use a plan in the baseline if it remains enabled and reproducible in the current environment. When a new plan emerges, SPM can hold it in an unaccepted state for verification/evolution before admitting it to the allowed plan set.

SPM works best when operated as a workflow: identify critical SQL, capture proven good plans, monitor changes, verify candidate plans, and only accept or fix plans backed by performance evidence. Baselines do not repair bad SQL, replace statistics/index tuning, or prove a plan works for all bind values.

This lesson belongs to the **SQL Tuning** group of Database Engine Relational Oracle. It focuses on SQL plan history and baselines, automatic/manual capture, accepted/enabled/fixed attributes, evolving, `DBMS_SPM` APIs, verification via the data dictionary and `DBMS_XPLAN`, regression control, baseline transport, and rollout procedures.

After this lesson, you will be able to:

- Explain SQL Plan Management and the role of SQL plan baselines.
- Distinguish SQL plan history, accepted plans, and unaccepted plans.
- Understand `ENABLED`, `ACCEPTED`, `FIXED`, `REPRODUCED`, and `AUTOPURGE` attributes.
- Enable/disable automatic plan capture and inspect SPM configuration.
- Load proven good plans from the cursor cache or supported sources.
- Use `DBMS_SPM` to inspect, evolve, enable/disable, fix, and drop baselines.
- Verify executed plans using `V$SQL` and `DBMS_XPLAN`.
- Distinguish differing plan hashes from real performance regressions.
- Identify why a baseline fails to reproduce or is not chosen by the optimizer.
- Evaluate candidate plans using representative workloads and bind values.
- Transport baselines across environments using staging tables.
- Design rollouts, rollbacks, and monitoring to curb plan regressions.

> **Example scope:** Examples primarily follow Oracle Database 19c. Certain views/APIs may require DBA privileges or appropriate licensing. Check documentation for your exact release/RU and your organization's licensing policy before using AWR, SQL Tuning Sets, or related performance management features.

## 1. Why can execution plans change?

The optimizer chooses how to access and combine data based on available metadata. The same SQL statement can execute under various plans:

- Full table scan or index range scan.
- Nested loops or hash join.
- Different join orders.
- Partition pruning or no pruning.
- Parallel execution or serial execution.
- Different subquery handling, view merging, or predicate pushdown.

### 1.1. Factors that cause plans to change

| Factor | Possible impact |
| --- | --- |
| Statistics re-gathered | Cardinality estimates and costs change |
| Data grows/shrinks or distribution shifts | Old plan may no longer fit |
| Indexes created, dropped, or rebuilt | Optimizer gains or loses access paths |
| Different bind values | Differing selectivity; may spawn different child cursors/plans |
| Optimizer parameters changed | Search space and costing change |
| Database upgrade/RU | Optimizer behavior or transformations change |
| Schema/object definitions changed | Old plan may no longer be reproducible |
| System load and resources changed | Runtime changes even under the exact same plan |

### 1.2. A new plan is not automatically a regression

Different plan hashes only show that the plan structure is represented differently. That is not enough to conclude the new plan is slower. A new plan might:

- Use a different index while reading fewer blocks.
- Use a hash join instead of nested loops and run faster on a larger dataset.
- Contain an extra operation while reducing elapsed time.
- Increase CPU slightly while cutting I/O and improving latency.

Conversely, the exact same plan hash can still run slower due to data growth, concurrency, I/O, cache state, bind values, or resource contention.

### 1.3. What is a performance regression?

A performance regression occurs when a change causes SQL to perform worse on key metrics, such as:

- Significant increase in elapsed time.
- Increased CPU time.
- Increased buffer gets or physical reads.
- Unexpected changes in execution count or rows processed.
- Reduced throughput or increased latency percentiles.
- SQL breaching SLAs or bottlenecking other workloads.

Do not compare plan hashes alone. Compare execution metrics under equivalent conditions.

## 2. What is SQL Plan Management?

SQL Plan Management is an Oracle mechanism that controls which plans the optimizer uses for a SQL statement by maintaining plan history and plan baselines.

### 2.1. Goals

- Reduce the risk of unverified new plans causing regressions.
- Preserve plans with proven good performance.
- Allow the optimizer to keep discovering new plans while governing acceptance.
- Support transporting verified plans across environments.
- Establish an observable and auditable process for plan changes.

### 2.2. SQL plan baseline

A SQL plan baseline is associated with a SQL statement and holds one or more accepted plans. The optimizer uses the baseline to restrict selection to permitted, reproducible plans.

A baseline typically stores:

- SQL handle identifying the statement.
- Plan name.
- Plan outline/hints used to reproduce the plan.
- Plan hash value and related metadata.
- `enabled`/`accepted`/`fixed` status.
- Origin, creation timestamp, last verification timestamp, and usage statistics.

### 2.3. Baselines are not absolute plan pins

A baseline does not guarantee Oracle will execute one exact plan under all circumstances:

- The plan must remain `ENABLED`.
- The plan must be `ACCEPTED` to be used as an approved plan.
- The plan must be `REPRODUCED` in the current environment.
- The SQL text must match the same statement under signature/matching rules.
- Optimizer settings and object metadata must permit reproducing the plan.

If an old plan cannot be reproduced after a schema/index change, the baseline cannot force Oracle to run a plan that is no longer valid.

## 3. Plan history and plan baselines

Plan history records observed plans for a SQL statement. The plan baseline is the subset of accepted plans eligible for optimizer consideration.

### 3.1. Accepted plans

A plan with `ACCEPTED = YES` has been admitted to the baseline. If `ENABLED = YES` and `REPRODUCED = YES`, the optimizer can consider it under SPM rules.

### 3.2. Unaccepted plans

A plan with `ACCEPTED = NO` has been recorded in history but not yet accepted. It is not used as an approved plan in normal baseline selection. It can be evaluated via the evolve process.

### 3.3. ENABLED

`ENABLED = YES` allows the plan to participate in selection. If `ENABLED = NO`, the plan is disabled and the optimizer will not use it from the baseline.

### 3.4. FIXED

`FIXED = YES` marks a fixed plan. When valid fixed plans exist, the optimizer prioritizes fixed plans under SPM rules instead of picking a non-fixed plan merely because of a lower estimated cost.

Do not set `FIXED = YES` on every baseline. Fixed plans curtail the optimizer's ability to switch among other plans in the baseline and can lock in an outdated plan even after workloads shift.

### 3.5. REPRODUCED

`REPRODUCED` indicates whether Oracle can reproduce the plan from the baseline in the current environment. If `REPRODUCED = NO`, investigate object, index, optimizer environment, or dependency changes preventing reproduction.

### 3.6. AUTOPURGE

`AUTOPURGE` controls whether the baseline is eligible for automatic purging under the SQL Management Base retention policy. Disabling autopurge retains baselines longer at the cost of extra space.

### 3.7. Attributes are not interchangeable

| Attribute | Question it answers |
| --- | --- |
| `ENABLED` | Is the plan allowed to participate in selection? |
| `ACCEPTED` | Has the plan been accepted into the baseline? |
| `FIXED` | Is the plan prioritized as a fixed plan? |
| `REPRODUCED` | Can the optimizer reproduce the plan? |
| `AUTOPURGE` | Can the plan be purged automatically by retention? |

## 4. Where does SPM store its data?

SQL Plan Management uses the SQL Management Base (SMB), located in the `SYSAUX` tablespace. SMB stores SQL management metadata including plan baselines and related administrative data.

### 4.1. Monitoring space

SPM enforces a space budget and management controls for the SQL Management Base. DBAs should monitor:

- Whether `SYSAUX` tablespace has sufficient free space.
- Number of SQL statements and plans currently stored.
- Whether plan history is growing abnormally fast.
- Whether retention/autopurge settings are appropriate.
- Which baselines require long-term retention due to critical SLAs or workloads.

### 4.2. SQL Management Base is not AWR

SMB and AWR are distinct concepts:

- SMB stores SQL management metadata, including plan baselines.
- AWR stores the workload repository and snapshot-based performance history.
- SPM can load plans from sources like the cursor cache, AWR, or SQL Tuning Sets via corresponding APIs, yet source data and licensing requirements remain separate.

Do not confuse baselines stored in SMB with SQL plan history stored in AWR.

## 5. How the optimizer uses SQL plan baselines

During SQL parse, the optimizer identifies the statement and looks up matching baselines.

High-level flow:

~~~text
SQL statement parsed
          |
          v
Find matching SQL plan baseline
          |
          v
Filter plans with ENABLED + ACCEPTED
          |
          v
Verify whether plans can be reproduced
          |
          v
Cost and select per SPM rules
          |
          v
Execute selected plan
~~~

If no matching baseline exists or no baseline plan can be reproduced, the optimizer optimizes normally. Thus, SPM does not block SQL execution when a baseline is unusable.

### 5.1. Multiple accepted plans

A baseline can hold multiple accepted plans. The optimizer can pick the lowest-cost plan among those that are accepted and reproducible.

### 5.2. Fixed plans and non-fixed plans

Fixed plans take priority under SPM rules. If multiple fixed plans exist, the optimizer compares costs among them. If no fixed plan is reproducible, the optimizer can fall back to valid non-fixed accepted plans.

### 5.3. Baselines do not guarantee identical runtime

Even when the exact same baseline plan is chosen:

- Different bind values can change actual row counts.
- Warm vs. cold cache alters physical I/O.
- Concurrent sessions can create contention.
- Growing data volumes can increase elapsed time.
- Storage, CPU, or Resource Manager behavior can change.

SPM governs plan selection; it does not pin execution time or system resources.

## 6. Automatic plan capture

Oracle can automatically capture SQL plans into SPM when enabled and statements meet capture criteria.

### 6.1. Checking parameters

~~~sql
SHOW PARAMETER optimizer_capture_sql_plan_baselines
SHOW PARAMETER optimizer_use_sql_plan_baselines
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'optimizer_capture_sql_plan_baselines',
    'optimizer_use_sql_plan_baselines'
)
ORDER BY name;
~~~

Typically:

- `OPTIMIZER_CAPTURE_SQL_PLAN_BASELINES` controls automatic capture.
- `OPTIMIZER_USE_SQL_PLAN_BASELINES` controls whether the optimizer uses baselines.

Check actual parameter values because settings may have been customized by DBAs.

### 6.2. Enabling automatic capture

~~~sql
ALTER SYSTEM SET optimizer_capture_sql_plan_baselines = TRUE
SCOPE = BOTH;
~~~

This is a system-wide change requiring DBA privileges and change approval. Never enable it in production just to test one SQL statement.

### 6.3. Disabling automatic capture

~~~sql
ALTER SYSTEM SET optimizer_capture_sql_plan_baselines = FALSE
SCOPE = BOTH;
~~~

Disabling capture does not disable using existing baselines. `OPTIMIZER_USE_SQL_PLAN_BASELINES` is an independent parameter.

### 6.4. Automatic capture does not store every SQL

Oracle applies capture criteria to avoid storing one-off or trivial SQL statements. Exact configuration and behavior depend on release. `DBMS_SPM.CONFIGURE` can configure supported capture/retention attributes.

### 6.5. Automatic capture and evolution

The first plan captured for a SQL statement may be accepted under capture rules; subsequent new plans are recorded as unaccepted for evolution. The evolve process evaluates whether a new plan outperforms accepted plans.

Do not assume enabling automatic capture automatically accepts every new plan immediately.

## 7. Manual capture from the cursor cache

In operations, a common practice is capturing an observed and verified good plan from the cursor cache.

### 7.1. Finding SQL_ID and plan hash

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    disk_reads,
    rows_processed,
    sql_plan_baseline,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%FROM ORDERS%'
  AND sql_text NOT LIKE '%v$sql%'
ORDER BY last_active_time DESC;
~~~

Refine filters to locate the exact statement. `SQL_TEXT` may be truncated; for long SQL, inspect `SQL_FULLTEXT` or query by known `SQL_ID`. One `SQL_ID` can have multiple child cursors and multiple plan hash values.

### 7.2. Verifying a good plan before capturing

Inspect the runtime plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => 'SQL_ID_VALUE',
        cursor_child_no => 0,
        format => 'ALLSTATS LAST +PEEKED_BINDS +OUTLINE +NOTE'
    )
);
~~~

Substitute actual `SQL_ID` and child number. `ALLSTATS LAST` is useful when the statement collected runtime plan statistics; without those stats, actual rows/starts columns may be omitted.

### 7.3. Loading a specific plan

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(
        sql_id          => 'SQL_ID_VALUE',
        plan_hash_value => 1234567890,
        fixed           => 'NO',
        enabled         => 'YES'
    );

    DBMS_OUTPUT.PUT_LINE('Plans loaded=' || l_loaded);
END;
/
~~~

The API returns the number of plans loaded. If you need to specify parsing schema or additional filters, check the overloads in the package specification for your exact release.

### 7.4. Do not capture a plan merely because it is in cache

The cursor cache can contain:

- Plans performing well.
- Plans generated for a single unusual bind value.
- Experimental plans.
- Child cursors from a different session environment.

Before loading, verify SQL text, parsing schema, plan hash, bind values, execution count, and runtime metrics.

## 8. Viewing baselines in the data dictionary

The primary view is `DBA_SQL_PLAN_BASELINES`. Users can query `USER_SQL_PLAN_BASELINES` or `ALL_SQL_PLAN_BASELINES` depending on privileges and scope.

### 8.1. Listing baselines

~~~sql
SELECT
    sql_handle,
    plan_name,
    origin,
    enabled,
    accepted,
    fixed,
    reproduced,
    autopurge,
    last_verified,
    last_executed,
    created,
    plan_hash_value,
    optimizer_cost
FROM dba_sql_plan_baselines
ORDER BY created DESC;
~~~

`DBA_SQL_PLAN_BASELINES` requires dictionary read privileges. Without DBA access, try `USER_SQL_PLAN_BASELINES`.

### 8.2. Finding baselines by SQL text

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    plan_hash_value,
    sql_text
FROM dba_sql_plan_baselines
WHERE UPPER(sql_text) LIKE '%ORDERS%'
ORDER BY sql_handle, plan_name;
~~~

Filtering by `SQL_TEXT` is only a preliminary search. In large environments, use the exact `SQL_HANDLE` or signature to avoid picking similar-looking statements.

### 8.3. Viewing a baseline's plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE'
    )
);
~~~

You can specify `plan_name` to view one specific plan using the supported overload. The output displays the plan outline and details for evaluating the baseline.

### 8.4. Finding which baseline a SQL statement is using

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    sql_plan_baseline,
    executions,
    elapsed_time,
    buffer_gets
FROM v$sql
WHERE sql_plan_baseline IS NOT NULL
ORDER BY last_active_time DESC;
~~~

Column names and availability can vary by view/release; check the `V$SQL` reference for your target database.

## 9. Inspecting runtime plans and baseline notes

### 9.1. DISPLAY_CURSOR

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_VALUE',
        0,
        'ALLSTATS LAST +OUTLINE +NOTE'
    )
);
~~~

The `NOTE` section indicates which SQL plan baseline was used or how the optimizer handled baselines.

### 9.2. DISPLAY_SQL_PLAN_BASELINE

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE',
        plan_name  => 'SQL_PLAN_NAME'
    )
);
~~~

This displays the plan stored in the baseline, not runtime statistics from the latest execution. For actual runtime behavior, cross-reference `DISPLAY_CURSOR` and `V$SQL`.

### 9.3. Plan hash value

`PLAN_HASH_VALUE` helps identify plan structure across views. However:

- It does not capture all runtime conditions.
- It does not guarantee two executions have identical elapsed times.
- It is not a unique key for every plan detail.
- A single `SQL_ID` can have multiple plan hash values.

## 10. Evolving baselines

Evolution is the process of evaluating unaccepted plans to decide whether they should be admitted into the baseline.

### 10.1. Why evolve?

After statistics or schemas change, the optimizer may discover a new plan. Never accept a new plan automatically merely because the optimizer estimates a lower cost. Evolution compares candidate plans against accepted plans using Oracle's verification process.

### 10.2. Evolving a SQL handle

~~~sql
SET LONG 100000
SET LONGCHUNKSIZE 100000

SELECT DBMS_SPM.EVOLVE_SQL_PLAN_BASELINE(
           sql_handle => 'SQL_HANDLE_VALUE',
           time_limit => 300,
           verify     => 'YES',
           commit     => 'NO'
       ) AS evolve_report
FROM dual;
~~~

The example uses `COMMIT = NO` to preview the report first. After reviewing the report and confirming results, re-run with `COMMIT = YES` or follow your organization's acceptance process. Verify exact parameters/overloads in your release's package reference.

### 10.3. Evolution can take time

Verification may execute the SQL statements to compare plans. Be sure to:

- Set a reasonable `time_limit`.
- Run during a maintenance window if the SQL is heavy.
- Use representative bind values.
- Ensure test data and workload reflect production.
- Monitor resource usage and any side effects of executed SQL.

Never run blanket evolution across all SQL without time and scope limits.

### 10.4. Reading the evolve report

The report can show:

- Which plans were verified.
- Which plans were accepted or rejected.
- Performance comparisons.
- Reasons verification did not complete.
- Timeouts or limits that halted the process.

Do not look solely at the word "accepted"; understand which plans were compared, whether tests were representative, and whether environment conditions matched.

### 10.5. Evolution does not replace business testing

Plan verification evaluates SQL performance via Oracle's internal criteria. It does not check whether business output is right. Before promoting a plan to production, applications still need regression tests and data correctness checks.

## 11. Managing baselines with DBMS_SPM

`DBMS_SPM` is the administration package for SQL Plan Management. Common APIs include:

- `LOAD_PLANS_FROM_CURSOR_CACHE`.
- `LOAD_PLANS_FROM_AWR`.
- `LOAD_PLANS_FROM_SQLSET`.
- `EVOLVE_SQL_PLAN_BASELINE`.
- `ALTER_SQL_PLAN_BASELINE`.
- `DROP_SQL_PLAN_BASELINE`.
- `CREATE_STGTAB_BASELINE`.
- `PACK_STGTAB_BASELINE`.
- `UNPACK_STGTAB_BASELINE`.

Overload names and parameters can vary by release; always check the matching package reference.

### 11.1. Enabling/disabling a baseline plan

~~~sql
DECLARE
    l_changed PLS_INTEGER;
BEGIN
    l_changed := DBMS_SPM.ALTER_SQL_PLAN_BASELINE(
        sql_handle      => 'SQL_HANDLE_VALUE',
        plan_name       => 'SQL_PLAN_NAME',
        attribute_name  => 'ENABLED',
        attribute_value => 'NO'
    );

    DBMS_OUTPUT.PUT_LINE('Changed=' || l_changed);
END;
/
~~~

Change `NO` to `YES` to re-enable. Check the return value and query `DBA_SQL_PLAN_BASELINES` afterward.

### 11.2. Setting FIXED

~~~sql
DECLARE
    l_changed PLS_INTEGER;
BEGIN
    l_changed := DBMS_SPM.ALTER_SQL_PLAN_BASELINE(
        sql_handle      => 'SQL_HANDLE_VALUE',
        plan_name       => 'SQL_PLAN_NAME',
        attribute_name  => 'FIXED',
        attribute_value => 'YES'
    );

    DBMS_OUTPUT.PUT_LINE('Changed=' || l_changed);
END;
/
~~~

Set `FIXED` only after verifying the plan performs well across representative workloads. To restore optimizer flexibility among accepted plans, set `FIXED = NO`.

### 11.3. Changing AUTOPURGE

~~~sql
DECLARE
    l_changed PLS_INTEGER;
BEGIN
    l_changed := DBMS_SPM.ALTER_SQL_PLAN_BASELINE(
        sql_handle      => 'SQL_HANDLE_VALUE',
        plan_name       => 'SQL_PLAN_NAME',
        attribute_name  => 'AUTOPURGE',
        attribute_value => 'NO'
    );
END;
/
~~~

Disabling autopurge prevents automatic cleanup of the baseline under this policy. Monitor SMB space and apply this only to plans genuinely needing retention.

### 11.4. Dropping baselines

~~~sql
DECLARE
    l_dropped PLS_INTEGER;
BEGIN
    l_dropped := DBMS_SPM.DROP_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE',
        plan_name  => 'SQL_PLAN_NAME'
    );

    DBMS_OUTPUT.PUT_LINE('Dropped=' || l_dropped);
END;
/
~~~

Omitting `plan_name` (in supported overloads) drops all baseline plans for that SQL handle. Before dropping, save details of plans to preserve and verify the exact SQL handle.

### 11.5. Verifying after every change

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    autopurge,
    last_verified
FROM dba_sql_plan_baselines
WHERE sql_handle = 'SQL_HANDLE_VALUE'
ORDER BY plan_name;
~~~

Do not treat a positive integer return value as complete proof. Inspect metadata after every change.

## 12. Loading plans from AWR or SQL Tuning Sets

Beyond the cursor cache, `DBMS_SPM` can load plans from other sources.

### 12.1. Loading from AWR

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_AWR(
        begin_snap   => 100,
        end_snap     => 120,
        basic_filter => q'[sql_id = 'abc123xyz4567']'
    );

    DBMS_OUTPUT.PUT_LINE('Plans loaded=' || l_loaded);
END;
/
~~~

The example filters by `SQL_ID` and snapshot range. Check the API signature and AWR views in your specific release.

### 12.2. AWR licensing

Accessing AWR and related features can fall under the Oracle Diagnostics Pack. Calling `DBMS_SPM.LOAD_PLANS_FROM_AWR` does not waive licensing requirements for the AWR source. Confirm your organization's contract/licensing before querying `DBA_HIST_*` or using pack-licensed features.

### 12.3. Loading from a SQL Tuning Set

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_SQLSET(
        sqlset_name => 'APP_SQLSET',
        basic_filter => q'[sql_id = 'abc123xyz4567']'
    );

    DBMS_OUTPUT.PUT_LINE('Plans loaded=' || l_loaded);
END;
/
~~~

A SQL Tuning Set can hold SQL statements, execution statistics, and plan metadata. Creating/managing STS and data sources carries its own privilege and licensing rules; check Oracle Tuning Pack/Diagnostics Pack applicability.

### 12.4. Choosing the right source

| Source | When appropriate | What to verify |
| --- | --- | --- |
| Cursor cache | Plan recently ran and was verified on the current database | `SQL_ID`, child, plan hash, binds, runtime metrics |
| AWR | Need to restore a historical plan from snapshots | Snapshot range, `SQL_ID`, licensing |
| SQL Tuning Set | Need to transport/collect SQL and plans across environments | STS contents, SQL profile/plan metadata, licensing |

## 13. Transporting baselines across environments

Baselines reside inside the database's SMB. To move plans from TEST to PROD, Oracle provides staging tables and pack/unpack APIs.

### 13.1. Creating a staging table

On the source database:

~~~sql
BEGIN
    DBMS_SPM.CREATE_STGTAB_BASELINE(
        table_name  => 'SPM_STGTAB',
        table_owner => 'SPM_ADMIN',
        tablespace_name => 'USERS'
    );
END;
/
~~~

The owner and tablespace must exist and the user must have proper privileges. The staging table holds exported baseline metadata for transport.

### 13.2. Packing baselines

~~~sql
DECLARE
    l_packed PLS_INTEGER;
BEGIN
    l_packed := DBMS_SPM.PACK_STGTAB_BASELINE(
        table_name  => 'SPM_STGTAB',
        table_owner => 'SPM_ADMIN',
        sql_handle  => 'SQL_HANDLE_VALUE'
    );

    DBMS_OUTPUT.PUT_LINE('Packed=' || l_packed);
END;
/
~~~

Use filters/`plan_name` per supported overloads to pack only the specific SQL/plans to migrate.

### 13.3. Exporting/importing the staging table

Use Data Pump or a DBA-approved method to move the staging table. Never copy internal SMB tables directly.

### 13.4. Unpacking on the target database

~~~sql
DECLARE
    l_unpacked PLS_INTEGER;
BEGIN
    l_unpacked := DBMS_SPM.UNPACK_STGTAB_BASELINE(
        table_name  => 'SPM_STGTAB',
        table_owner => 'SPM_ADMIN'
    );

    DBMS_OUTPUT.PUT_LINE('Unpacked=' || l_unpacked);
END;
/
~~~

After unpacking:

- Verify `SQL_HANDLE` and `PLAN_NAME`.
- Verify `ENABLED`/`ACCEPTED`/`FIXED`.
- Check `REPRODUCED`.
- Run the SQL with representative bind values.
- Confirm baseline usage via `DBMS_XPLAN`.

### 13.5. Baselines do not guarantee identical plans across two environments

TEST and PROD can differ in:

- Table/index definitions.
- Statistics and data distribution.
- Partitioning.
- Optimizer parameters.
- Database version/RU.
- Object privileges or parsing schema.

A plan packed from TEST might not reproduce in PROD. Always verify after unpacking; do not treat pack/unpack as a guarantee of identical runtime behavior.

## 14. Controlling regressions when statistics change

Statistics refreshes are a common trigger for optimizer plan flips.

### 14.1. Pre-statistics-gathering workflow

1. Identify critical SQL and `SQL_ID`s.
2. Record current plan hashes and runtime metrics.
3. Confirm plan baselines are enabled/accepted/reproduced.
4. Record representative bind values.
5. Run a workload benchmark before the change.

### 14.2. Gathering statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'APP_OWNER',
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

Statistics gathering must follow `DBMS_STATS` governance policies. If using pending statistics, understand your environment's publish/use pending stats workflow.

### 14.3. Post-statistics checks

- Did the SQL switch to a new plan hash?
- Was the plan selected from the baseline?
- Do actual rows diverge significantly from estimates?
- How did elapsed time, CPU, buffer gets, and physical reads change?
- Which bind values are affected?
- Did other SQL statements regress due to updated statistics?

### 14.4. Baselines are a safety net, not a reason to skip statistics

Do not stop gathering statistics merely because baselines exist. Statistics remain essential for the optimizer to choose well among accepted plans and optimize other SQL statements.

### 14.5. Statistics and plan evolution

After statistics update, the optimizer may discover a new plan. You can retain the old plan in the baseline while evolving the new plan against a representative workload. If the new plan is better, accept it; otherwise keep the old baseline.

## 15. Controlling regressions during Oracle upgrades

Database upgrades/RUs can alter optimizer behavior and plan selection.

### 15.1. Before the upgrade

- Capture critical SQL workloads.
- Capture current SQL plans.
- Create/verify baselines for high-SLA SQL.
- Record optimizer parameters.
- Identify SQL with bind-sensitive behavior.
- Build a list of SQL statements to compare post-upgrade.

### 15.2. After the upgrade

- Confirm baselines were preserved/migrated as planned.
- Verify `REPRODUCED`.
- Run representative workloads.
- Compare plan hashes and runtime metrics.
- Use SQL Plan Management to limit regressions where baselines fit.
- Evolve new plans when evidence shows improvements.

### 15.3. Do not force old baselines unconditionally

An old plan may not fit a new optimizer version or modified object metadata. If a plan fails to reproduce, investigate why. You may need to:

- Rebuild/recreate indexes or objects per design.
- Rewrite the SQL.
- Capture a suitable post-upgrade baseline from workload runs.
- Accept a verified new plan.

## 16. Bind variables and multiple child cursors

A single SQL statement using bind variables can spawn multiple child cursors due to bind metadata, bind sensitivity, optimizer environment, or other reasons.

### 16.1. Bind peeking

The optimizer can use bind values peeked at hard parse to estimate selectivity. With skewed data, a plan great for rare values can perform terribly for common values, or vice versa.

### 16.2. Adaptive Cursor Sharing

Adaptive Cursor Sharing can produce multiple child cursors/plans across different bind selectivity regions. SPM manages plans at the SQL statement level, but does not eliminate every bind-sensitivity issue.

### 16.3. Do not capture one single plan when workloads span multiple bind groups

Before capturing a baseline:

- Choose representative bind values.
- Inspect `V$SQL` child cursors.
- Compare executions, rows processed, and runtime.
- Determine whether multiple selectivity classes exist.
- Avoid pinning a plan that works for only one bind value.

### 16.4. Inspecting child cursors

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    elapsed_time,
    cpu_time,
    buffer_gets,
    is_bind_sensitive,
    is_bind_aware,
    sql_plan_baseline
FROM v$sql
WHERE sql_id = 'SQL_ID_VALUE'
ORDER BY child_number;
~~~

Bind-sensitive/aware columns depend on view/release. Check the `V$SQL` reference before querying.

## 17. Why might a baseline not be used?

Having a baseline does not mean the optimizer is actively using it.

### 17.1. OPTIMIZER_USE_SQL_PLAN_BASELINES = FALSE

If this parameter is disabled, the optimizer will not use SPM baselines under normal configuration. Check:

~~~sql
SHOW PARAMETER optimizer_use_sql_plan_baselines
~~~

### 17.2. Plan is disabled

`ENABLED = NO` excludes the plan from consideration.

### 17.3. Plan is not accepted

`ACCEPTED = NO` means the plan has not yet been admitted into the approved set. Run evolve/accept per procedure.

### 17.4. Plan cannot be reproduced

`REPRODUCED = NO` can happen because:

- An index was dropped or renamed.
- Object or partition structure changed.
- SQL text/signature no longer matches.
- Optimizer environment changed.
- Dependencies or privileges changed.

### 17.5. SQL does not match the baseline

SQL handle/signature relies on how Oracle identifies statements. Changing text, literals, whitespace/comments, or schema qualification can affect matching depending on signature/force-matching rules. Do not modify SQL text casually after creating a baseline.

### 17.6. Fixed vs. non-fixed baseline plan behavior

A non-fixed plan may be skipped if the optimizer estimates another accepted plan has lower cost. If your goal is pinning a plan, understand `FIXED` and its trade-offs before applying it.

## 18. Force matching and SQL signatures

Oracle identifies SQL statements by signature. SPM includes a force-matching mechanism to group certain SQL statements differing only in literals while sharing identical structure.

### 18.1. Exact matching

Exact matching binds the baseline to the exact SQL text/signature. Text changes can create a distinct statement identity in Oracle.

### 18.2. Force matching

Force matching can help when an application emits the same SQL template with varying literals. However, never enable force matching blindly:

- Two SQL statements with identical structure may differ in semantics or selectivity.
- A single plan may not suit all literals.
- Bind peeking/ACS considerations still apply.

### 18.3. Checking SQL handles and signatures

SPM views/APIs expose `SQL_HANDLE` and statement metadata. Use the handle returned from capture/load to manage the exact baseline. Never guess a `SQL_HANDLE` from a `SQL_ID`.

## 19. Measuring performance and confirming regressions

SPM controls plans, yet plan acceptance decisions must rest on metrics.

### 19.1. Key metrics

| Metric | Meaning |
| --- | --- |
| `ELAPSED_TIME` | Cumulative execution time |
| `CPU_TIME` | Cumulative CPU time |
| `BUFFER_GETS` | Logical reads |
| `DISK_READS` | Physical reads |
| `ROWS_PROCESSED` | Rows processed |
| `EXECUTIONS` | Execution count |
| `FETCHES` | Fetch calls |
| `END_OF_FETCH_COUNT` | Completed fetches |

`V$SQL` holds cumulative cursor metrics. When comparing, divide by executions or compute deltas between two timestamps rather than comparing raw cumulative totals.

### 19.2. Average metrics

~~~sql
SELECT
    sql_id,
    plan_hash_value,
    executions,
    ROUND(elapsed_time / NULLIF(executions, 0) / 1e6, 4)
        AS avg_elapsed_seconds,
    ROUND(cpu_time / NULLIF(executions, 0) / 1e6, 4)
        AS avg_cpu_seconds,
    ROUND(buffer_gets / NULLIF(executions, 0), 2)
        AS avg_buffer_gets,
    ROUND(disk_reads / NULLIF(executions, 0), 2)
        AS avg_disk_reads
FROM v$sql
WHERE sql_id = 'SQL_ID_VALUE'
ORDER BY plan_hash_value;
~~~

Values in `V$SQL` are cumulative cursor metrics. Averages hide latency distributions; for SLA percentiles, collect appropriate runtime telemetry.

### 19.3. Before/after comparison using deltas

Record metric snapshots at start and end, then calculate deltas:

~~~text
delta_elapsed = elapsed_after - elapsed_before
delta_execs   = executions_after - executions_before
avg_elapsed   = delta_elapsed / delta_execs
~~~

Compare only when the cursor was neither aged out nor reset between snapshots. If a new child cursor appeared, map the right child cursor/plan.

### 19.4. Plan hashes do not replace runtime metrics

Two differing plan hashes must be evaluated using:

- Actual rows vs. estimated rows.
- `Starts` and `A-Rows` per operation.
- Logical/physical reads.
- CPU and elapsed time.
- Bind values.
- Concurrency and wait events.

A plan with a different hash that runs faster is not a regression.

### 19.5. AWR/ASH and SQL Monitor

AWR/ASH and SQL Monitor aid in analyzing workloads and execution timing, subject to separate licensing and privilege requirements. Use them only per organizational licensing. Without Diagnostics/Tuning Pack licenses, rely on authorized views and tools such as `V$SQL`, `DBMS_XPLAN`, and SQL Trace/TKPROF per configuration.

## 20. SQL Plan Management and other tuning tools

SPM does not replace other optimization mechanisms.

| Tool | Role | How it differs from SPM |
| --- | --- | --- |
| SQL Plan Baseline | Manages set of accepted plans | Controls plan selection |
| SQL Profile | Supplies auxiliary statistics to improve cardinality estimates | Does not directly pin plans |
| SQL Patch | Attaches optimizer hints to SQL | Alters optimizer directives |
| SQL Tuning Advisor | Analyzes and recommends tuning actions | Advisory tool; licensing may apply |
| SQL Plan Directive | Assists optimizer with supplementary statistical info per release | Not a baseline |
| SQL Plan Control/Outline | Alternate or legacy mechanisms to influence plans | Should not be confused with SPM |

### 20.1. Baselines and SQL Profiles

A SQL Profile improves optimizer estimates. A baseline restricts eligible plans. The two mechanisms can coexist and address different problems.

### 20.2. Baselines and SQL Patches

A SQL Patch attaches hints to guide the optimizer. When addressing regressions, avoid layering overlapping patches and baselines without understanding precedence/interaction. Inspect SQL notes, outlines, and active SQL management objects.

### 20.3. Baselines and optimizer hints in SQL

Hints embedded in SQL influence the optimizer. Baselines also store outline directives. If SQL text introduces new hints or the schema changes, an old baseline may stop applying as expected. Inspect actual plans and notes.

## 21. Operating SPM in production

### 21.1. Identifying SQL to protect

Prioritize:

- SQL with strict SLAs/latency targets.
- High-frequency, high-resource SQL.
- SQL on critical payment/order/reporting paths.
- SQL with a history of regressions after stats refreshes or upgrades.
- SQL with diverse bind values and multi-plan behavior.

You do not need baselines for every SQL statement in the system.

### 21.2. Capturing good plans

1. Identify `SQL_ID` and SQL text.
2. Identify parsing schema/module/action.
3. Inspect child cursors and bind sensitivity.
4. Check the actual plan via `DBMS_XPLAN`.
5. Record runtime metrics across multiple runs.
6. Capture the plan via `DBMS_SPM`.
7. Verify the baseline appears in `DBA_SQL_PLAN_BASELINES`.

### 21.3. Post-capture monitoring

- Is the optimizer using the baseline?
- Is `REPRODUCED = YES`?
- Have new unaccepted plans appeared?
- Have elapsed time/CPU/I/O shifted?
- Did SQL text or parsing schema change?

### 21.4. Controlled evolution

1. Inspect candidate plans.
2. Determine source and time the plan appeared.
3. Verify representative bind values and workloads.
4. Run evolve with a time limit.
5. Read the report.
6. Accept the new plan if correctness and performance meet requirements.
7. Monitor production after enabling the plan.

### 21.5. Plan rollback

If a newly accepted plan causes a regression:

- Disable the new plan in the baseline.
- Re-enable the previously verified plan.
- If necessary, set the old plan `FIXED` after assessment.
- Inspect optimizer notes and plan hashes.
- Document SQL handle, plan name, and actions taken.

Do not drop the old plan immediately after accepting a new plan. Keep a rollback path per retention/change policy.

## 22. Workflow for handling a real regression

Suppose after gathering statistics, an order lookup endpoint's latency jumps from 100 ms to 2 seconds.

### Step 1 — Confirm SQL and scope

- Locate `SQL_ID` from application traces/logs or `V$SQL`.
- Identify module/action, parsing schema, and bind values.
- Check whether the SQL has multiple child cursors.

### Step 2 — Compare plans

- Record before/after plan hashes if available.
- Use `DBMS_XPLAN.DISPLAY_CURSOR` with `ALLSTATS LAST`.
- Compare join order, access paths, cardinality, and actual rows.

### Step 3 — Identify root cause

- Did statistics change?
- Is there bind value skew?
- Was an index dropped or marked invalid?
- Did an optimizer parameter change?
- Did SQL text or schema change?
- Is concurrency/resource contention slowing down the exact same plan?

### Step 4 — Check existing baselines

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    plan_hash_value
FROM dba_sql_plan_baselines
WHERE UPPER(sql_text) LIKE '%ORDER_ID%'
ORDER BY created;
~~~

If no baseline exists yet, check the cursor cache or historical sources for a proven good plan.

### Step 5 — Capture the good plan

Load the plan from cursor cache/AWR/SQL Tuning Set as appropriate. Verify it is loaded and reproducible.

### Step 6 — Test against the workload

Run with common and boundary bind values, comparing latency/CPU/reads. Never test with just one bind value.

### Step 7 — Roll out and monitor

Enable/accept the baseline per change management. Monitor SQL runtime and related statements. If the regression persists, a baseline will not solve the root cause; continue investigating statistics, data skew, I/O, locking, or SQL design.

## 23. Limitations and risks of SPM

### 23.1. Baselines can become stale

A plan captured when tables were small may perform poorly after data grows. Holding onto an old baseline indefinitely can prevent the optimizer from picking a better plan.

### 23.2. Fixed plans reduce flexibility

`FIXED = YES` can shield a proven plan, yet also blocks the optimizer from adopting superior new plans. Use `FIXED` with a time limit and periodic reviews.

### 23.3. Plans may fail to reproduce

Baselines rely on object metadata and optimizer environment. After schema migrations or upgrades, plans may become non-reproducible.

### 23.4. Unrepresentative bind values

Capturing a plan generated for a rare bind value can protect a plan poorly suited to most of the workload.

### 23.5. Baselines do not fix cardinality/data models

If a query has non-sargable predicates, missing indexes, broken joins, or row-by-row functions, a baseline can only pick among existing plan shapes. SQL rewrites or schema/index changes may be necessary.

### 23.6. Baselines do not prevent runtime resource issues

CPU saturation, I/O latency, lock contention, network waits, and storage problems will still slow SQL down even when the plan stays unchanged.

### 23.7. SMB capacity

Capturing too many plans and disabling autopurge indiscriminately can bloat the SQL Management Base. Enforce retention and housekeeping.

## 24. Common errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Baseline exists yet is not used | `USE_SQL_PLAN_BASELINES` off, plan disabled/unaccepted, or SQL mismatch | Check parameters, flags, SQL handle, and `DBMS_XPLAN` notes |
| New plan not accepted | Evolve verification failed or not run | Read evolve report, verify binds/workload, run controlled evolve |
| `REPRODUCED = NO` | Object/index/optimizer environment changed | Inspect plan outline and dependencies, verify schema |
| Loading from cursor cache returns 0 | Wrong `SQL_ID`/plan hash, plan aged out, or filter mismatch | Check `V$SQL` and current child cursors |
| Loaded baseline onto wrong SQL | Overly broad `SQL_ID` or text filter | Verify SQL text, parsing schema, and plan hash |
| Fixed plan becomes slow after data growth | Fixed plan no longer suits new workload | Evaluate alternate plans, evolve, and unfix when appropriate |
| Same plan hash yet latency spikes | Resources, binds, data volume, or concurrency changed | Analyze runtime metrics/waits |
| Different plan hash yet faster | Optimizer found a better plan | Do not call it a regression; benchmark and consider evolving |
| Unpacked baseline does not reproduce | Target differs in objects/indexes/stats/version | Sync required schema or capture a suitable plan on target |
| Evolve takes too long | Heavy SQL or large `time_limit` | Limit scope/duration, run in a suitable window |
| SMB grows too large | Excessive plan history or autopurge disabled | Review retention and purge unneeded baselines |
| Cannot access `DBA_SQL_PLAN_BASELINES` | Missing dictionary privileges | Use `USER_`/`ALL_` views or request read-only DBA grant |

## 25. Common misconceptions

| Misconception | Reality |
| --- | --- |
| Baselines freeze plans absolutely | Plans must be enabled, accepted, and reproducible |
| One SQL has only one baseline plan | One SQL can have multiple accepted/unaccepted plans |
| Different plan hash means regression | Must compare runtime metrics |
| Same plan hash means unchanged performance | Runtime can vary with data, binds, and resources |
| Enabling automatic capture stores every SQL | Capture uses criteria; not every statement is saved |
| Enabling capture automatically enables baseline use | Capture and use parameters are independent |
| Unaccepted plans are used automatically by optimizer | They must be accepted through the SPM process |
| `FIXED = YES` is always good | Can lock the optimizer into an outdated plan |
| Evolve only compares cost | Verification evaluates actual execution performance |
| Baselines replace statistics | Statistics remain essential |
| Baselines protect all bind values | Bind sensitivity and multiple child cursors still matter |
| Pack/unpack guarantees identical execution | Plans may fail to reproduce in another environment |
| SPM fixes bad SQL | SPM governs plan selection, not query design |
| AWR is a free unconditional source | AWR/pack usage carries licensing requirements |

## 26. SQL Plan Baseline management checklist

**Before capture**

- Is the SQL truly critical?
- Are SQL text, `SQL_ID`, and parsing schema confirmed?
- Have child cursors and bind sensitivity been inspected?
- Does the current plan show good, stable runtime metrics?
- Have actual rows vs. estimated rows been checked?

**During capture**

- Is the source cursor cache, AWR, or SQL Tuning Set?
- Is the exact right plan hash being loaded?
- Are enabled/accepted flags set as intended?
- Is `FIXED` needed?
- Are SQL handle and plan name recorded?

**After capture**

- Is the optimizer using the baseline?
- Is `REPRODUCED` equal to `YES`?
- Are runtime metrics stable?
- Are new unaccepted plans awaiting evolution?
- Is SMB space being monitored?

**When modifying**

- Was the report reviewed before committing evolve?
- Were representative bind values tested?
- Is the old plan kept for rollback?
- Is post-rollout monitoring in place?
- Was the rationale for enable/disable/fixed/drop documented?

## 27. Comprehensive practice lab

This lab demonstrates capturing a plan from the cursor cache and verifying the baseline. Run in a lab schema/database with `DBMS_SPM` execution privileges; never run in production without approval.

### Step 1 — Create table and data

~~~sql
CREATE TABLE spm_orders_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    order_total NUMBER(12,2)
);

INSERT INTO spm_orders_lab
SELECT
    LEVEL,
    MOD(LEVEL, 10000) + 1,
    CASE WHEN MOD(LEVEL, 5) = 0 THEN 'PAID' ELSE 'NEW' END,
    MOD(LEVEL, 50000) + 1
FROM dual
CONNECT BY LEVEL <= 100000;

CREATE INDEX ix_spm_orders_customer_lab
ON spm_orders_lab(customer_id);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SPM_ORDERS_LAB',
        cascade => TRUE
    );
END;
/
~~~

### Step 2 — Run SQL

~~~sql
SELECT /* SPM_ROW436_LAB */
       order_id, status, order_total
FROM spm_orders_lab
WHERE customer_id = 501;
~~~

### Step 3 — Find SQL_ID and plan hash

~~~sql
SELECT
    sql_id,
    child_number,
    plan_hash_value,
    executions,
    elapsed_time,
    buffer_gets,
    sql_text
FROM v$sql
WHERE sql_text LIKE '%SPM_ROW436_LAB%'
ORDER BY last_active_time DESC;
~~~

### Step 4 — Inspect runtime plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        'SQL_ID_VALUE',
        0,
        'ALLSTATS LAST +OUTLINE +NOTE'
    )
);
~~~

Substitute `SQL_ID_VALUE` and child number from actual results.

### Step 5 — Load plan into baseline

~~~sql
DECLARE
    l_loaded PLS_INTEGER;
BEGIN
    l_loaded := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(
        sql_id => 'SQL_ID_VALUE',
        plan_hash_value => 1234567890,
        fixed => 'NO',
        enabled => 'YES'
    );
    DBMS_OUTPUT.PUT_LINE('Loaded=' || l_loaded);
END;
/
~~~

### Step 6 — Verify baseline

~~~sql
SELECT
    sql_handle,
    plan_name,
    enabled,
    accepted,
    fixed,
    reproduced,
    plan_hash_value
FROM user_sql_plan_baselines
ORDER BY created DESC;
~~~

### Step 7 — View stored plan

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE'
    )
);
~~~

### Step 8 — Re-run SQL and check note

~~~sql
SELECT /* SPM_ROW436_LAB */
       order_id, status, order_total
FROM spm_orders_lab
WHERE customer_id = 501;
~~~

Then call `DBMS_XPLAN.DISPLAY_CURSOR` to check whether the optimizer used the baseline.

### Step 9 — Clean up baseline and lab table (optional)

~~~sql
DECLARE
    l_dropped PLS_INTEGER;
BEGIN
    l_dropped := DBMS_SPM.DROP_SQL_PLAN_BASELINE(
        sql_handle => 'SQL_HANDLE_VALUE'
    );
END;
/

DROP TABLE spm_orders_lab PURGE;
~~~

Drop only the SQL handle belonging to the lab. On a shared database, never delete another application's baselines.

## 28. Self-check questions

1. What problem does SQL Plan Management solve?
2. What is a SQL plan baseline?
3. How does plan history differ from a baseline?
4. How do `ACCEPTED` and `ENABLED` differ?
5. What effect does `FIXED` have on plan selection?
6. What does `REPRODUCED = NO` indicate?
7. What role does `AUTOPURGE` play?
8. Where are baselines stored?
9. How does `OPTIMIZER_CAPTURE_SQL_PLAN_BASELINES` differ from `OPTIMIZER_USE_SQL_PLAN_BASELINES`?
10. Does automatic capture store every SQL statement?
11. When should you capture a plan from the cursor cache?
12. Why check child cursors and bind values before capturing?
13. What is `DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE` used for?
14. What information does `DBA_SQL_PLAN_BASELINES` provide?
15. How does `DBMS_XPLAN.DISPLAY_CURSOR` differ from `DISPLAY_SQL_PLAN_BASELINE`?
16. Are differing plan hashes enough to conclude a regression occurred?
17. What does evolving a baseline do?
18. Why use `COMMIT = NO` when previewing an evolve report?
19. What risks can a fixed plan introduce?
20. From which sources besides the cursor cache can baselines be loaded?
21. What licensing considerations apply to AWR and SQL Tuning Sets?
22. Does packing/unpacking a baseline guarantee the plan reproduces on the target database?
23. Why must statistics still be gathered when baselines exist?
24. How do bind peeking and Adaptive Cursor Sharing affect plan selection?
25. What causes a baseline not to be used?
26. How does a SQL Profile differ from a SQL Plan Baseline?
27. When should a SQL Patch be used instead of a baseline?
28. Which metrics should be compared to identify regressions?
29. What can cause elapsed time to rise when the plan hash stays identical?
30. What steps belong in a rollback workflow when a new plan causes a regression?

**Answer hints:**

1. Manages known plans to reduce the risk of plan changes causing regressions.
2. A set of accepted plans for a SQL statement.
3. History records observed plans; baselines hold accepted plans eligible for optimizer consideration.
4. Accepted means approved into the baseline; enabled means currently allowed to be used.
5. Fixed plans are prioritized under SPM rules over non-fixed plans.
6. The optimizer cannot reproduce the plan from the baseline in the current environment.
7. Allows the baseline to be purged automatically under retention/SMB policy.
8. SQL Management Base inside `SYSAUX`.
9. One controls capturing plans; the other controls using baselines.
10. No; capture applies eligibility criteria.
11. When a recently executed plan is verified good via runtime metrics and representative binds.
12. Because the same SQL can have multiple plans/children across differing selectivities.
13. Loads plans currently in the cursor cache into a SQL plan baseline.
14. SQL handle, plan name, origin, status flags, plan hash, cost, and metadata.
15. `DISPLAY_CURSOR` views a runtime cursor plan; `DISPLAY_SQL_PLAN_BASELINE` views plans stored in a baseline.
16. No; runtime metrics must be compared.
17. Evaluates unaccepted candidate plans to decide whether to accept them.
18. To inspect the report before committing changes to the baseline.
19. Locks in an outdated plan and blocks the optimizer from picking a better new plan.
20. AWR and SQL Tuning Sets.
21. AWR/SQL Tuning features may require Diagnostics/Tuning Pack; confirm licensing.
22. No; differing schemas, indexes, statistics, or optimizer environments can prevent reproduction.
23. Statistics help the optimizer estimate and choose among accepted plans, and are needed by other SQLs.
24. Bind values can trigger different child cursors/plans by selectivity.
25. Baseline usage disabled, plan disabled/unaccepted, SQL mismatch, or plan fails to reproduce.
26. SQL Profiles assist cardinality estimation; baselines manage the set of allowed plans.
27. When specific optimizer hints must be attached and interactions with baselines are understood.
28. Elapsed time, CPU, buffer gets, disk reads, rows, executions, and latency distributions.
29. Resource contention, data growth, bind values, I/O, caching, or wait events.
30. Disable the new plan, enable the old plan, verify plan/runtime, log the change record, and monitor.

## Oracle references

- [Oracle Database SQL Tuning Guide — Managing SQL Plan Baselines](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/overview-of-sql-plan-management.html): SPM architecture and workflows.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_SPM](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SPM.html): APIs to capture, evolve, alter, drop, and transport baselines.
- [Oracle Database Reference — DBA_SQL_PLAN_BASELINES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_SQL_PLAN_BASELINES.html): SQL plan baseline metadata.
- [Oracle Database SQL Tuning Guide — Evolving SQL Plan Baselines](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/evolving-sql-plan-baselines.html): verification and evolution.
- [Oracle Database SQL Tuning Guide — Capturing SQL Plan Baselines](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/capturing-sql-plan-baselines.html): automatic and manual capture.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): displaying cursor plans and baseline plans.
- [Oracle Database Reference — V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html): runtime cursor statistics.
- [Oracle Database SQL Tuning Guide — SQL Tuning Sets](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-sql-tuning-sets.html): managing SQL Tuning Sets.

**Key principle to remember:** SQL Plan Management reduces regression risk by governing the set of accepted plans for a SQL statement. A plan can only be used when enabled, accepted, and reproducible in the current environment. Capture plans verified with runtime metrics and representative bind values; use evolve to evaluate new plans; use `FIXED` only with clear operational justification. Differing plan hashes alone do not prove regressions, and baselines never replace statistics, SQL tuning, or resource checks. After every change, verify baseline metadata, actual plans via `DBMS_XPLAN`, and performance in a production-like workload.

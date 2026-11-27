# Bind Peeking, Adaptive Cursor Sharing, and Multiple Child Cursors

## 1. Why Might One SQL Statement Need Multiple Execution Plans?

Applications often send the same SQL statement repeatedly while passing different bind values. For example:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status;
```

Suppose the `orders` table has a heavily skewed data distribution:

- Only a tiny fraction of orders have `status = 'CANCELLED'`.
- Most orders have `status = 'COMPLETED'`.

For the rare value, Oracle can read a few records via an index and then visit the table. For the popular value, reading many blocks with a full table scan may be cheaper. The predicate is the same, yet the amount of data to process differs, so an execution plan that is good for one value is not necessarily good for another.

Bind variables help applications reuse SQL statements and reduce hard parses. However, if all bind values had to share one plan, differences in data distribution could make some executions inefficient. Oracle addresses this with bind peeking and, starting in Oracle Database 11g, adaptive cursor sharing (ACS). The result can be a single parent cursor with multiple child cursors, each serving a suitable group of execution conditions.

## 2. Bind Variables and the Cursor Lifecycle

A bind variable is a placeholder in a SQL statement. The application passes values separately at execution time instead of concatenating values directly into the SQL string:

```sql
SELECT *
FROM employees
WHERE department_id = :department_id;
```

When bind variables are used properly:

- The SQL statement can be reused across many calls.
- Oracle reduces how often it must fully parse and optimize.
- The application avoids building a new SQL string for every data value.
- Passing data as binds helps prevent SQL injection for properly bound values.

In the library cache, distinguish two concepts:

| Component | Meaning |
|---|---|
| Parent cursor | Represents the identified SQL statement in the library cache. Corresponding child cursors are managed beneath the parent. |
| Child cursor | An executable version of the parent cursor, tied to specific environment details, bind metadata, and an execution plan. |

Consistently bound SQL text typically shares the same SQL ID. Under that SQL ID, Oracle can store multiple child cursors with different `CHILD_NUMBER` values. Each child can have its own `PLAN_HASH_VALUE`; in some cases multiple children still share the same plan hash but exist for compatibility or environment reasons.

### Hard Parse vs. Soft Parse

A **hard parse** occurs when Oracle must build or optimize a new cursor because no shareable child cursor matches. Work may include syntax parsing, privilege checks, object resolution, cardinality estimation, and execution plan selection.

A **soft parse** occurs when Oracle finds a suitable cursor in the library cache and can reuse it. A soft parse still incurs cursor lookup and validation overhead; it does not mean zero parse work.

Bind variables generally help repeated calls to the same SQL follow the cursor-reuse path. However, sharing only happens when compatibility conditions are met. Differences in bind data type, bind length, optimizer environment, privileges, or object state can prevent Oracle from sharing a single child cursor.

## 3. How Does Bind Peeking Work?

Bind peeking is the mechanism where Oracle inspects the bind values available at hard-parse time so the optimizer can use them when estimating selectivity and cardinality.

Example:

```sql
SELECT order_id
FROM orders
WHERE status = :status;
```

Suppose the application performs the initial hard parse with `:status = 'CANCELLED'`. If statistics and a histogram tell the optimizer this value is very rare, the optimizer may select an index range scan. The child cursor created from that optimization can then continue to be reused when the SQL runs with `:status = 'COMPLETED'`.

On subsequent executions, Oracle does not normally re-hard-parse just to look at new bind values. Thus, the plan chosen during the initial parse may no longer suit a value with vastly different selectivity.

### Role of Statistics and Histograms

The optimizer relies on statistics to estimate row counts and the cost of alternatives. Basic statistics describe row count, block count, distinct values, and nullity. Histograms add information about a column's value distribution, helping the optimizer distinguish popular and rare values.

When data is fairly uniformly distributed, a general selectivity estimate may suffice. When data is heavily skewed, a histogram helps the optimizer estimate more accurately for the peeked bind value.

You can instruct Oracle to evaluate histograms for a column with `DBMS_STATS`:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'ORDERS',
    method_opt => 'FOR COLUMNS SIZE AUTO STATUS',
    cascade    => TRUE
  );
END;
/
```

`SIZE AUTO` lets Oracle decide on histograms based on column usage information and statistics policy. The command above is an illustrative example; before refreshing statistics on a live system, assess collection schedules, data change volume, and the impact of updating statistics on current plans.

Histograms do not automatically make every query faster. They help the optimizer differentiate values with differing selectivities, but can also cause plans to change depending on which bind value is peeked. Evaluate histograms alongside the actual workload.

### Risks of Relying Only on Bind Peeking

With skewed data, the outcome can depend on which bind value appears during the hard parse:

| Value Peeked at Hard Parse | Plan That May Be Chosen | Risk When Reused |
|---|---|---|
| Rare value | Index range scan | Popular values may read far too many rows through index and table lookups. |
| Popular value | Full table scan | Rare values may scan many blocks even though very few rows are needed. |

This is why a SQL statement can sometimes be fast at one moment and slow at another even though the application only changed bind values. Do not immediately conclude an index is broken or that bind variables are the sole culprit; inspect actual plans, statistics, bind metadata, and hard parses.

## 4. Adaptive Cursor Sharing (ACS)

Adaptive cursor sharing was introduced in Oracle Database 11g to handle cases where a SQL statement has bind variables whose values produce significantly different selectivities.

ACS lets Oracle observe execution behavior and gradually recognize which cursors are sensitive to bind values. Once sufficient evidence shows that groups of values need different optimization, Oracle can create child cursors tailored to different selectivity ranges.

### Common States

Oracle exposes two key flags in `V$SQL`:

- `IS_BIND_SENSITIVE = 'Y'`: the cursor is monitored because bind values may affect selectivity or execution efficiency.
- `IS_BIND_AWARE = 'Y'`: Oracle has determined that distinct selectivity ranges may require separate child cursors.

These two flags are not a guarantee that every bind value will get its own plan. They indicate the cursor's processing state at the time of observation.

### High-Level Flow

1. The application submits a SQL statement with bind variables. Oracle hard-parses and may peek at the current bind values to pick an initial plan.
2. If predicates qualify, Oracle marks the cursor as bind-sensitive and monitors executions.
3. Oracle collects information about selectivity and execution efficiency across bind value groups.
4. Once it observes values behaving differently enough, Oracle can transition the cursor to bind-aware.
5. Oracle can create additional child cursors for different selectivity ranges. Subsequent executions are matched to the appropriate range to reuse the corresponding child.

This is an observation-driven adaptive mechanism, not an immediate creation of a child cursor for every bind value. State transitions and child creation depend on workload, statistics, version, optimizer configuration, and accumulated evidence. A bind-sensitive cursor will not necessarily become bind-aware in every scenario.

### Why Is ACS Helpful?

Returning to the query:

```sql
SELECT order_id
FROM orders
WHERE status = :status;
```

Oracle can gradually identify two selectivity ranges:

- Rare value group: returns only a few rows, suited to index access.
- Popular value group: returns many rows, suited to a full scan.

Once appropriate child cursors exist, bind values falling in the same selectivity range can share a child. Oracle does not need to create a new child for every distinct value. This balances two goals: cursor reuse and selecting plans suited to data distribution.

ACS does not guarantee every run gets the absolute optimal plan. It needs time and execution data to recognize behavior; an infrequently called query may not generate enough evidence. Changes in statistics or environment can also change plans and child cursors.

## 5. Why Does One SQL ID Have Multiple Child Cursors?

Multiple child cursors can appear for two main categories of reasons:

1. **Differences in selectivity and plan:** ACS creates or maintains child cursors to serve different bind ranges.
2. **Incompatibility during cursor sharing:** Oracle needs a separate child because metadata, environment, or execution state do not match.

Common causes include:

| Cause | Example | How to Check |
|---|---|---|
| Different bind metadata | Application sometimes binds `VARCHAR2` and other times `NVARCHAR2`; inconsistent bind lengths or data types. | Inspect how the driver declares binds and the `BIND_MISMATCH` flag. |
| Different optimizer environment | Sessions have different `OPTIMIZER_MODE`, optimizer parameters, or NLS settings. | Compare optimizer environments and `OPTIMIZER_MISMATCH`, `LANGUAGE_MISMATCH` flags. |
| Different privileges or schemas | Sessions resolve objects or validate privileges in different contexts. | Check parse schema, privileges, and authorization-related flags. |
| Object metadata or statistics changed | DDL, invalidation, or statistics updates rendered the old cursor unusable. | Check invalidations, loads, and object/statistics change history. |
| ACS needs another selectivity range | New bind value does not match the selectivity range of existing children. | Check `IS_BIND_SENSITIVE`, `IS_BIND_AWARE`, and `BIND_EQUIV_FAILURE` if your version includes this column. |

Therefore, **multiple child cursors are not automatically an error**. Multiple children with different plans can be expected ACS behavior. Conversely, dozens of children sharing the same plan hash but differing in bind metadata or optimizer environment may indicate the application is creating inconsistent parse contexts.

Persistently high child counts can increase library cache memory, parse overhead, and synchronization contention when many sessions access the cursor concurrently. Still, child count alone is not enough to decide to intervene; examine why children were created, execution frequency, plan hashes, and actual cost.

## 6. Observing Bind Peeking and Child Cursors

The following dynamic views are typically useful when investigating:

| View | Primary Information |
|---|---|
| `V$SQL` | One row per cached child cursor; includes SQL ID, child number, plan hash, executions, and bind-sensitive/bind-aware flags. |
| `V$SQLAREA` | Aggregated info per parent SQL, including `VERSION_COUNT` for child version counts. |
| `V$SQL_SHARED_CURSOR` | Flags explaining why a child cursor could not share with another child. |
| `V$SQL_CS_SELECTIVITY` | Selectivity ranges tracked by ACS for the cursor. |
| `V$SQL_CS_STATISTICS` | Execution statistics used by ACS when evaluating bind behavior. |
| `V$SQL_CS_HISTOGRAM` | Internal histogram information related to executions monitored by ACS. |
| `V$SQL_BIND_CAPTURE` | Bind values captured via sampling; not a complete log of every execution. |

`V$` views reflect the current instance and library cache state. Cursors can age out or be invalidated, so observable data is bounded by cache lifetime. In RAC environments, you may need `GV$` views and compare `INST_ID`; in multitenant environments, pay attention to `CON_ID`.

### Viewing Child Cursors of a SQL ID

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable
FROM   v$sql
WHERE  sql_id = :sql_id
ORDER BY child_number;
```

When reading the output:

- Compare `PLAN_HASH_VALUE` to see whether children use different plans.
- Compare `EXECUTIONS` and `PARSE_CALLS` to understand usage patterns.
- Check `IS_BIND_SENSITIVE` and `IS_BIND_AWARE` to see how Oracle handles bind sharing.
- Check `IS_SHAREABLE`; a non-shareable child may no longer be chosen for new executions.

You can check child version counts at the parent level:

```sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls
FROM   v$sqlarea
WHERE  sql_id = :sql_id;
```

A high `VERSION_COUNT` is a signal to investigate, not proof that the system has an error.

### Checking Reasons Child Cursors Do Not Share

```sql
SELECT child_number,
       bind_mismatch,
       optimizer_mismatch,
       auth_check_mismatch,
       language_mismatch,
       translation_mismatch
FROM   v$sql_shared_cursor
WHERE  sql_id = :sql_id
ORDER BY child_number;
```

Columns in `V$SQL_SHARED_CURSOR` can differ across Oracle versions. Verify against the data dictionary of your running version before hardcoding a fixed column list in operational scripts. Flag values help narrow down the cause; confirm alongside application bind info and session environments.

If your version provides `BIND_EQUIV_FAILURE`, that flag helps identify cases where bind values were not equivalent to the selectivity range served by the existing child cursor. This is an ACS-related signal, distinct from `BIND_MISMATCH`, which indicates differences in bind metadata.

### Viewing the Actual Execution Plan and Peeked Binds

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    :sql_id,
    :child_number,
    'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
  )
);
```

`DISPLAY_CURSOR` displays the plan of the cached child cursor. `+PEEKED_BINDS` requests showing the bind values peeked when the cursor was optimized, if available. These are not necessarily the bind values of the most recent execution.

`ALLSTATS LAST` is useful for comparing estimated rows and actual rows, but requires runtime plan statistics. You can collect them for a controlled run with `/*+ GATHER_PLAN_STATISTICS */` or appropriate statistics settings. Avoid enabling detailed collection broadly without evaluating overhead.

`V$SQL_BIND_CAPTURE` also does not record every value of every execution. It is sampled capture data, so do not use it as a complete audit log of bind variables. Bind values may contain sensitive data; restrict access and avoid placing live values into unprotected reports.

### Viewing ACS Information

When deeper investigation is needed, filter `V$SQL_CS_*` views by SQL ID and child number:

```sql
SELECT *
FROM   v$sql_cs_selectivity
WHERE  sql_id = :sql_id
ORDER BY child_number, range_id;

SELECT *
FROM   v$sql_cs_histogram
WHERE  sql_id = :sql_id
ORDER BY child_number, bucket_id;
```

These views show how Oracle tracks selectivity ranges and execution counts across buckets. This is diagnostic data for the adaptive mechanism; do not rely on a single bucket alone to judge which plan is better. Cross-check against actual rows, buffer gets, elapsed time, and workload.

## 7. Workflow for Investigating a Query That Runs Sometimes Fast and Sometimes Slow

When the same SQL ID has runtime varying by bind value, follow this sequence:

1. **Identify the exact SQL ID and instance scope.** Record the SQL, application module/action if present, execution timing, and representative bind values. Avoid logging unnecessary sensitive data.
2. **List child cursors.** Collect `CHILD_NUMBER`, `PLAN_HASH_VALUE`, execution counts, parse counts, and bind-sensitive/bind-aware flags.
3. **Compare actual plans.** Run `DBMS_XPLAN.DISPLAY_CURSOR` for each child. Inspect operations, predicates, access paths, estimated rows, and actual rows.
4. **Compare bind value groups.** Pick popular, rare, and intermediate values from the real workload. Check data types, lengths, and how the driver binds them.
5. **Check statistics.** Verify whether table/column/index statistics are fresh and representative of current data; determine whether histograms match data skew and predicates.
6. **Find why new children are created.** Read flags in `V$SQL_SHARED_CURSOR`; distinguish children created by ACS from children caused by incompatible bind metadata or optimizer environments.
7. **Evaluate cost across the workload.** Compare elapsed time, CPU, buffer gets, actual row counts, and frequency of each bind group. A plan with lower cost on one run does not necessarily improve the overall workload.
8. **Test fixes in a controlled environment.** Adjust statistics, bind metadata, or plan policies step by step; re-measure across representative bind groups before deploying.

For example, if child 0 uses an index range scan and performs well for rare values, while child 1 uses a full table scan and performs well for popular values, that may be a sound outcome of ACS. If dozens of children are created with identical plan hashes and `BIND_MISMATCH` flagged, prioritize fixing inconsistent application binding first.

## 8. Remedies and Things to Avoid

### Keep Bind Metadata Consistent

Applications should bind the same parameter with stable data types and length rules. For instance, avoid passing a string sometimes as `VARCHAR2` and other times as `NVARCHAR2` if business logic and schema do not require it. Avoid implicit conversions on filtered columns, because conversions can affect index usability and cardinality estimates.

### Maintain Appropriate Statistics

Gather statistics on a schedule and policy aligned with data change rates. Use histograms only when data distribution and workload show the optimizer needs them. After updating statistics, test critical queries across multiple bind value groups because plans can change.

### Let ACS Adapt Before Intervening Manually

ACS is designed to handle differing bind selectivities. Before disabling bind peeking, disabling ACS, or forcing a fixed plan, verify whether Oracle has already created suitable children and inspect the actual cost of each child. Hidden parameters are not standard tuning knobs; do not alter them just to fix a single slow SQL statement.

### Use SQL Plan Management When Plan Control Is Needed

If a system needs to constrain plan changes after upgrades or statistics updates, SQL Plan Management (SPM) helps govern and control accepted plans. However, baselines do not replace understanding bind selectivity. Evaluate how a baseline interacts with child cursors and specific workloads before applying it.

### Do Not Force Every Case onto One Plan

An index plan may excel for rare values yet be prohibitively expensive for popular values; a full scan can have the opposite profile. Forcing a single plan can speed up one bind group while slowing down another. Use hints, SQL Patches, baselines, or SQL rewrites only after measuring across representative cases and defining clear operational goals.

### Do Not Treat Child Cursor Count as a Standalone Health Metric

Multiple child cursors can be the proper result of ACS. What matters is why children were created, whether they are reused, whether plans match their respective binds, and whether parse/library cache overhead is significant. Simply purging cursors from the shared pool or flushing the shared pool rarely fixes the root cause and can trigger widespread hard parsing.

## 9. Distinguishing Commonly Confused Concepts

| Concept | What It Describes | What It Does Not Mean |
|---|---|---|
| Bind peeking | Optimizer inspects bind values at hard-parse time to estimate and choose a plan. | Oracle substitutes bind values into SQL text on every execution. |
| Bind-sensitive | Cursor has bind predicates whose selectivity may affect efficiency; Oracle monitors behavior. | The cursor definitely has multiple plans already. |
| Bind-aware | Oracle has recognized selectivity ranges that need handling via appropriate child cursors. | Every single bind value gets its own child cursor. |
| Child cursor | A specific cursor instance beneath a parent cursor. | Every child was created by ACS or has a different plan. |
| Bind capture | Selected bind values captured by Oracle via sampling. | A complete history of bind values for every execution. |
| Adaptive cursor sharing | Mechanism selecting and sharing child cursors by bind selectivity range. | Adaptive execution plans in general, or a guarantee that every query self-optimizes perfectly. |

## 10. Operational Checklist

- [ ] Verified the application uses bind variables and binds with matching data types.
- [ ] Identified the SQL ID, instance, and time window of the issue.
- [ ] Checked child cursor count, plan hashes, and bind-sensitive/bind-aware states.
- [ ] Compared execution plans along with actual rows and buffer gets for each child.
- [ ] Checked histograms, table/column/index statistics, and collection timestamps.
- [ ] Read non-sharing reasons in `V$SQL_SHARED_CURSOR`.
- [ ] Evaluated bind value groups representative of the real workload.
- [ ] Made statistics or plan policy changes only after before/after measurements.

## Conclusion

Bind peeking lets the optimizer use bind values at hard-parse time to make more informed plan choices. When data distributions are skewed, a plan picked for the first value may not fit all executions. Adaptive cursor sharing allows Oracle to observe selectivity and create multiple child cursors for distinct bind groups. Thus, multiple child cursors are sometimes a sign of adaptive optimization working properly.

When investigating, combine SQL ID, child number, plan hash, bind-sensitive/bind-aware flags, cursor non-sharing reasons, bind metadata, statistics, and runtime plan statistics. Only after identifying the root cause should you choose remedies such as standardizing binds, updating statistics, tuning SQL, or managing plans.

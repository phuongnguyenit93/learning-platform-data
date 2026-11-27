# SQL_ID, PLAN_HASH_VALUE, Child Cursors, and Plan Reuse Conditions

## 1. Why Distinguish SQL_ID, Plan Hash, and Child Cursor?

When investigating Oracle Database performance, a single SQL statement can appear multiple times in the shared pool, accumulate many executions, and even have multiple execution plans. To read views such as `V$SQL`, `V$SQLAREA`, and `V$SQL_SHARED_CURSOR` accurately, distinguish three concepts:

- **SQL_ID** identifies the SQL statement in the shared SQL area based on its SQL text.
- **PLAN_HASH_VALUE** is a hash value representing a cursor's execution plan structure.
- **Child cursor** is a specific cursor version beneath a parent cursor, holding a plan and execution context tailored to particular environment/metadata conditions.

One `SQL_ID` can have multiple child cursors. Those children may share the same `PLAN_HASH_VALUE` or have different plan hashes. Therefore, looking at `SQL_ID` or plan hash alone is not enough to conclude that a SQL statement has only one plan or that every run uses the same plan.

## 2. SQL_ID and Parent Cursors

### 2.1. What Does SQL_ID Identify?

When Oracle parses a SQL statement, it searches for or creates a cursor in the library cache within the shared pool. `SQL_ID` is a character identifier—typically 13 characters—derived from the SQL text and used to look up the statement in dynamic performance views.

Example:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE customer_id = 1001;
```

Oracle creates or locates the cursor corresponding to this SQL text. You can look up the statement via `V$SQL`:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls
FROM v$sql
WHERE sql_text LIKE 'SELECT order_id, customer_id, amount%'
ORDER BY sql_id, child_number;
```

In practice, capture `SQL_ID` from a known execution, from the application, or from monitoring tools, and use bind variables when querying. `SQL_ID` is an identifier for observing cursors in Oracle, not a business code or permanent identifier of an application feature.

### 2.2. What Is a Parent Cursor?

Oracle manages cursors in a parent-child hierarchy inside the library cache:

```text
SQL text
   |
   v
Parent cursor (SQL_ID)
   |
   +-- Child cursor 0  -> execution plan / execution context
   +-- Child cursor 1  -> execution plan / execution context
   +-- Child cursor 2  -> execution plan / execution context
```

The parent cursor represents the SQL statement and serves as the anchor for its child cursors. When incoming SQL text matches an existing parent cursor, Oracle checks whether an existing child cursor is compatible for reuse. If no compatible child exists, Oracle can create a new child cursor under the same parent.

If the SQL text differs, Oracle typically treats it as a different SQL statement and creates a separate parent cursor/`SQL_ID`. Differences in whitespace, letter casing, comments, or literals can prevent text matching. `CURSOR_SHARING` mechanisms can alter how literals are handled, though you should not rely on them to treat structurally similar SQL statements as the same cursor.

### 2.3. SQL_ID Does Not Mean a Single Execution

One `SQL_ID` can be invoked by an application thousands of times. Each execution does not necessarily create a new cursor. Many parses/executions can reuse the same child cursor as long as it remains in the shared pool, valid, and compatible with the call.

Columns such as `EXECUTIONS`, `PARSE_CALLS`, `LOADS`, and `INVALIDATIONS` in `V$SQL` provide observability into the cursor. They are cumulative metrics over the cursor's lifetime in the shared pool; if the cursor is aged out, invalidated, or evicted and reloaded, counters can reset with the new cursor.

## 3. PLAN_HASH_VALUE

### 3.1. Meaning

`PLAN_HASH_VALUE` is a numeric value representing the execution plan structure of a cursor. It allows quick plan comparisons for the same SQL across child cursors, observations, or environments.

Example query:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

If children of the same `SQL_ID` have different `PLAN_HASH_VALUE`s, that indicates they have different execution plans with respect to the structural elements hashed. Inspect each child in detail with `DBMS_XPLAN.DISPLAY_CURSOR`.

### 3.2. Does the Same PLAN_HASH_VALUE Guarantee Everything Is Identical?

No. A plan hash is a summary fingerprint identifying plan structure, not a complete specification of every execution attribute. Two cursors with the same plan hash typically have matching operation trees, yet from that alone you cannot conclude that:

- Bind values in the two executions are the same.
- Actual row counts, blocks read, or execution times are the same.
- Optimizer environments, runtime statistics, or every secondary plan attribute are identical.
- No differences exist in details omitted from the hash calculation.

Conversely, two distinct SQL statements can share the same `PLAN_HASH_VALUE` if their plan structures are identical. Hence, a plan hash is not a globally unique SQL identifier.

Oracle also provides `FULL_PLAN_HASH_VALUE` in supported releases. This covers more complete plan details, though you should not compare it directly across different Oracle versions. When comparing across environments or versions, compare the plan text and execution context.

### 3.3. SQL_ID and PLAN_HASH_VALUE Complement Each Other

| Attribute | SQL_ID | PLAN_HASH_VALUE |
|---|---|---|
| Represents | SQL statement / parent cursor | Execution plan structure |
| Value type | Identifier string | Hash number |
| One-to-many mapping? | One SQL_ID can have multiple plan hashes across child cursors | One plan hash can appear across multiple SQL_IDs |
| Used to | Locate a SQL statement and its child cursors | Quickly identify/compare plans |

When reporting a performance issue, record at least `SQL_ID`, `CHILD_NUMBER`, and `PLAN_HASH_VALUE`. Together, these three values pin down the cursor/plan observed at that point in time.

## 4. Child Cursors and Why One SQL_ID Has Multiple Children

### 4.1. What Does a Child Cursor Contain?

A child cursor is a concrete executable cursor beneath a parent cursor. It holds the execution plan and the attributes needed to execute the SQL statement in a compatible context. In `V$SQL`, each child cursor appears as a row distinguished by `CHILD_NUMBER` under the same `SQL_ID`.

For example, a `SQL_ID` might appear as:

| SQL_ID | CHILD_NUMBER | PLAN_HASH_VALUE | Illustrative Meaning |
|---|---:|---:|---|
| `abc...` | 0 | 1234567890 | First child, plan A |
| `abc...` | 1 | 1234567890 | Different child, yet same plan hash as A |
| `abc...` | 2 | 9876543210 | Different child, plan B |

This is illustrative data. A child number is a sequence index among the parent cursor's children at the moment of observation; do not treat it as a permanent identifier across shared pool reloads or instance restarts.

### 4.2. Common Reasons a New Child Cursor Is Created

Oracle reuses a child cursor only when relevant attributes are compatible. A new child may be created when significant differences arise, such as:

- **Incompatible bind metadata:** bind variable datatypes, lengths, or characteristics differ across parses.
- **Different optimizer environment:** optimizer or session parameters affecting optimization differ.
- **Different object resolution or authorization:** parsing schema, privileges, synonyms, editions, or name resolution contexts differ.
- **Object metadata changes:** table, column, index, or dependency definitions render the old child invalid or unsuitable.
- **Different statistics or feedback:** statistics updates, cardinality feedback, or adaptive optimization mechanisms yield a different child/plan.
- **Bind peeking and Adaptive Cursor Sharing:** groups of bind values with differing selectivity require different plans.

These are common categories; not every session difference automatically spawns a new child. Oracle evaluates many internal sharing checks, and exact rules vary by version.

### 4.3. VERSION_COUNT

`V$SQLAREA` aggregates data at the SQL statement/parent cursor level. The `VERSION_COUNT` column shows how many child cursor versions are currently tracked for that SQL in the shared pool.

```sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls
FROM v$sqlarea
WHERE sql_id = :sql_id;
```

A high `VERSION_COUNT` indicates a SQL statement has many child cursors. However, having multiple children is not automatically a bug. Multiple children may be desirable—for instance, when adaptive cursor sharing creates tailored plans for distinct bind selectivity ranges. Identify the cause and evaluate parse overhead before concluding there is a problem.

## 5. Hard Parse, Soft Parse, and Cursor Reuse

### 5.1. Basic Parse Flow

When an application submits a SQL statement, Oracle determines which cursor to execute:

```text
Application submits SQL
       |
       v
Search parent cursor by SQL text
       |
       +-- No matching parent
       |       -> hard parse
       |       -> create parent/child and choose execution plan
       |
       +-- Parent found
               |
               v
         Search compatible child
               |
               +-- Valid child found -> soft parse / reuse
               |
               +-- No compatible child
                       -> hard parse to create new child
```

The diagram shows the conceptual flow. Actual parsing is also affected by the session cursor cache, client statement cache, library cache state, and internal Oracle mechanisms.

### 5.2. Hard Parse

A hard parse occurs when Oracle must perform full parsing and optimization to build a new cursor/child instead of reusing a compatible child. This work can include:

- Syntax and semantic analysis.
- Checking object names, privileges, and dependencies.
- Resolving datatypes, bind metadata, and optimizer environment.
- Generating candidate execution plans, estimating costs, and choosing a plan.
- Creating the child cursor and storing it in the library cache if successful.

Hard parses are CPU-intensive and can put contention pressure on the library cache, particularly when applications continually submit varying SQL text or generate unnecessary child cursors.

### 5.3. Soft Parse

A soft parse occurs when Oracle locates a matching cursor and reuses it rather than creating a new cursor via hard parse. Oracle still performs necessary checks for the current parse call; a soft parse does not bypass parsing altogether.

Reusing cursors reduces optimization and plan-generation overhead. Nevertheless, applications should still manage statement lifecycles properly, close unused cursors, and avoid unnecessary repeated parse calls.

### 5.4. Cursor Remains in Shared Pool and Valid

To be reused, a child cursor must still reside in the library cache and remain valid for the new parse context. A cursor can become unusable if it:

- Ages out of the shared pool under memory pressure.
- Is invalidated by object or dependency changes, DDL operations, statistics-related invalidations, or other causes.
- Is incompatible with the new call's bind metadata, optimizer environment, privileges, or object resolution context.
- Has SQL text that no longer matches the existing parent cursor.

Once a cursor is evicted or invalidated, the next parse must reload it or create a new child. Seeing a `SQL_ID` in `V$SQL` at one point does not guarantee that the cursor will stay there permanently.

## 6. Bind Variables, Bind Peeking, and Adaptive Cursor Sharing

### 6.1. Why Do Bind Variables Support Reuse?

Compare two SQL statements:

```sql
SELECT * FROM orders WHERE customer_id = 1001;
SELECT * FROM orders WHERE customer_id = 1002;
```

If sent with different literals and without a suitable normalization mechanism, the SQL text differs, so Oracle may create two separate parent cursors. This increases cursor count and hard parse work.

Using a bind variable:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

The application binds `1001` and `1002` into the same SQL statement. The SQL text can be reused, reducing parent cursors and generally reducing hard parses when calls are compatible.

Bind variables also help mitigate SQL injection when bound properly by separating data from statement structure. However, using binds does not guarantee only one child cursor or one execution plan.

### 6.2. Bind Peeking

When hard-parsing a SQL statement with bind variables, Oracle can inspect ("peek") the bind value at parse time to estimate selectivity and choose a plan. This mechanism is called **bind peeking**.

Suppose `CUSTOMER_ID` has a skewed distribution:

- One major customer has millions of orders.
- Most other customers have only a few dozen orders.

A plan suited for a small customer may perform poorly for the major customer. If the initial plan was chosen based on a highly selective bind value, that plan can become inefficient when reused for a bind value returning massive row counts.

Bind peeking does not mean Oracle re-reads bind values and hard-parses on every execution. The value peeked at parse time shapes the plan stored in the child cursor, which is then reused on subsequent calls.

### 6.3. Adaptive Cursor Sharing

Adaptive Cursor Sharing (ACS) enables Oracle to recognize that a bind-sensitive SQL statement may need different plans for different selectivity ranges. Over repeated executions and monitoring, Oracle can mark the cursor as bind-aware and create or select child cursors suited to specific bind-value buckets.

Illustrative example:

```text
One SQL_ID with predicate CUSTOMER_ID = :customer_id
       |
       +-- Child 0: plan suited for low-volume customer group
       |
       +-- Child 1: plan suited for high-volume customer group
```

In `V$SQL`, `IS_BIND_SENSITIVE` and `IS_BIND_AWARE` reveal ACS status:

- `IS_BIND_SENSITIVE = 'Y'`: the cursor is monitored because bind values may affect selectivity.
- `IS_BIND_AWARE = 'Y'`: Oracle can select child cursors based on matching bind selectivity ranges.

ACS aims to improve plan choice across varying bind distributions. It does not guarantee a dedicated child per bind value, nor does every workload require multiple children. Actual child counts and plans depend on data, version, statistics, and workload behavior.

## 7. Views for Investigating Cursors and Plans

### 7.1. V$SQL: Inspecting Individual Child Cursors

`V$SQL` contains one row per child cursor currently in the shared SQL area. Query key columns:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       loads,
       invalidations,
       is_bind_sensitive,
       is_bind_aware
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Useful columns:

| Column | Meaning |
|---|---|
| `SQL_ID` | Identifier of the SQL statement in the shared SQL area |
| `CHILD_NUMBER` | Sequence number of the child cursor under its parent |
| `PLAN_HASH_VALUE` | Hash representing the execution plan |
| `EXECUTIONS` | Recorded executions for the child |
| `PARSE_CALLS` | Recorded parse calls |
| `LOADS` | Number of times the cursor was loaded into the shared pool per cursor counter |
| `INVALIDATIONS` | Number of times the cursor was invalidated per counter |
| `IS_BIND_SENSITIVE` | Bind sensitivity monitoring status |
| `IS_BIND_AWARE` | Adaptive cursor sharing status |

Exact columns and interpretations can vary by release. On RAC systems, query `GV$SQL` when aggregating cursors across instances, and include `INST_ID` in the output to distinguish instances.

### 7.2. V$SQLAREA: Parent Cursor Overview

`V$SQLAREA` summarizes information at the SQL statement/parent cursor level and is useful for checking `VERSION_COUNT`:

```sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls,
       loads,
       invalidations
FROM v$sqlarea
WHERE sql_id = :sql_id;
```

If `VERSION_COUNT` grows high, inspect individual children in `V$SQL` and investigate why multiple versions are being created. Do not flush the shared pool or purge cursors just to lower this count without understanding the cause and impact.

### 7.3. V$SQL_SHARED_CURSOR: Finding Why a Child Was Not Shared

`V$SQL_SHARED_CURSOR` provides information on why an existing child cursor could not be shared with a new parse, forcing Oracle to create another child. This view contains flag columns for many mismatch categories, such as bind, optimizer, authorization, or translation mismatches. Column names and sets expand across Oracle releases.

You can start with:

```sql
SELECT *
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Inspect columns with value `Y` and check their descriptions in the documentation for your exact release. Multiple reasons can appear together; correlate child numbers, parse timestamps, and session environments to isolate the real cause. Never conclude from a single flag without cross-checking bind metadata, optimizer environment, and the plan.

### 7.4. DBMS_XPLAN.DISPLAY_CURSOR: Viewing a Specific Child's Plan

Once you identify `SQL_ID` and `CHILD_NUMBER`, view the execution plan:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    :sql_id,
    :child_number,
    'TYPICAL +PREDICATE +ALIAS'
  )
);
```

If runtime statistics were collected, use a format like `ALLSTATS LAST` to view actual metrics:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    :sql_id,
    :child_number,
    'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
  )
);
```

`PEEKED_BINDS` shows bind information peeked at parse time to the extent Oracle retains it; it is not a complete log of all bind values across all runs. Handle output carefully because bind values may contain sensitive data.

If you lack privileges to read dynamic performance views or execute `DBMS_XPLAN`, ask a DBA for appropriate grants per system policy.

## 8. Conditions for Plan Reuse

Conditions for reusing a child cursor fall into four areas:

### 8.1. SQL Text Matches the Parent Cursor

Oracle must find a parent cursor matching the parsed SQL text. Differences in literals, comments, whitespace, or formatting produce different SQL text and lead to a different `SQL_ID`/parent. Using bind variables consistently lets repeated calls share the same SQL statement.

### 8.2. A Compatible Child Cursor Exists

An existing child must be compatible with the new parse. Bind datatypes/lengths, optimizer environment, schema and privileges, object metadata, editions, and related attributes must satisfy Oracle's sharing checks. Otherwise, Oracle creates a new child even under the same `SQL_ID`.

### 8.3. Cursor Remains in the Library Cache and Is Valid

The child must remain cached in the shared pool and must not be invalidated in a way that blocks reuse. Memory pressure, DDL, dependency changes, or statistics changes can evict or invalidate cursors. The next parse must then reload, hard-parse, or build a new child depending on state.

### 8.4. The Existing Plan Remains Acceptable for the New Context

Oracle must confirm the child/plan fits the bind values and optimization context. For bind-sensitive SQL, ACS may pick a different child for a different selectivity range. Thus, reusing a `SQL_ID` does not imply all bind values use the exact same child or plan hash.

## 9. SESSION_CACHED_CURSORS and Statement Caches

`SESSION_CACHED_CURSORS` controls session caching of cursors that are parsed and closed repeatedly, reducing parse overhead for frequently executed SQL in the same session. JDBC/OCI and other drivers also offer client-side statement caches.

These mechanisms reduce cursor lookup and re-parse work in suitable scenarios, yet they do not merge two different SQL texts into one parent cursor and do not bypass child cursor compatibility checks. Client-side statement caches do not replace the shared pool either: the client holds handles for reuse while Oracle still manages parent/child cursors on the server.

When optimizing applications, combine:

- Using bind variables with consistent datatypes and lengths.
- Reusing prepared statements or configuring statement caches properly.
- Avoiding repeated parsing of the same SQL within a workflow when statements can reasonably stay open.
- Monitoring hard parses, soft parses, child cursors, and `VERSION_COUNT`.
- Avoiding arbitrary optimizer parameter tweaks or shared pool flushes to mask symptoms.

## 10. Investigation Workflow When One SQL_ID Has Multiple Child Cursors or Plans

1. Obtain the actual `SQL_ID` from the application or monitoring tools.
2. Query `V$SQL` to list `CHILD_NUMBER`, `PLAN_HASH_VALUE`, `EXECUTIONS`, `PARSE_CALLS`, `LOADS`, and `INVALIDATIONS`.
3. Check `V$SQLAREA.VERSION_COUNT` to see how many child cursors are recorded at the parent level.
4. If multiple children exist, query `V$SQL_SHARED_CURSOR` for mismatch reasons; cross-check bind datatypes/lengths, parsing schema, privileges, optimizer environment, and object metadata.
5. Run `DBMS_XPLAN.DISPLAY_CURSOR` for each child number to compare operations, predicates, estimated rows, and runtime statistics.
6. If the SQL uses bind variables, check `IS_BIND_SENSITIVE`, `IS_BIND_AWARE`, and whether different bind groups have different selectivities.
7. Check whether cursors were invalidated or aged out, whether statistics changed, and whether the application is emitting varying SQL text via literals or dynamic generation.
8. Only change SQL, bind metadata, statistics, indexes, or cache settings after identifying the root cause; re-measure hard parses, child counts, plans, and performance afterward.

Do not default to flushing the shared pool, forcing one plan, or disabling bind peeking/ACS just because you see multiple child cursors. Multiple children may be the intended outcome of differing execution contexts; the goal is eliminating unnecessary children while keeping plans aligned with the workload.

## Oracle References

- [Oracle Database 19c Reference — V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html)
- [Oracle Database 19c Reference — V$SQLAREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQLAREA.html)
- [Oracle Database 19c Reference — V$SQL_SHARED_CURSOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_SHARED_CURSOR.html)
- [Oracle Database 19c SQL Tuning Guide — Adaptive Cursor Sharing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/improving-rwp-cursor-sharing.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html)

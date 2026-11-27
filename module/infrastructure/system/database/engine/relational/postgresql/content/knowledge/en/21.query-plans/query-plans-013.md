# Generic Plans, Custom Plans, and Prepared Statements in PostgreSQL

Applications frequently execute repeated SQL queries with the **same structure but different parameters**:

~~~sql
SELECT job_id, state, payload
FROM jobs
WHERE state = 'rare';

SELECT job_id, state, payload
FROM jobs
WHERE state = 'common';
~~~

Parameterized, that structure becomes a prepared statement:

~~~sql
PREPARE lookup_job(text) AS
SELECT job_id, state, payload
FROM jobs
WHERE state = $1;
~~~

The application then supplies different values on each execution:

~~~sql
EXECUTE lookup_job('rare');
EXECUTE lookup_job('common');
~~~

A seemingly simple question with major performance impact is: **should PostgreSQL build a dedicated plan for each set of parameter values, or reuse one shared plan for all values?**

- A **custom plan** is optimized using the **specific parameter values of that execution**. It can choose different access paths for `'rare'` vs. `'common'`, at the cost of repeated planning.
- A **generic plan** can be **reused across many parameter sets**, because it is built without binding specific runtime parameter values. It avoids repeated planning afterward, yet may perform poorly for outlier parameter values.

That is the core topic of **“Generic Plans, Custom Plans, and Prepared Statements”** in the **Query Plans** chapter of the **Database Engine Relational PostgreSQL** module.

This lesson explains the plan-selection mechanism, provides hands-on SQL examples, shows how to read `EXPLAIN EXECUTE`, examines skewed-distribution pitfalls, clarifies differences between server-side `PREPARE` and Java/JDBC `PreparedStatement`, and outlines safe diagnostic procedures before changing production settings.

## 1. Four Concepts to Keep Separate

| Concept | Question It Answers |
|---|---|
| **Parameterized SQL** | How are concrete values replaced with placeholders like `$1` or `?`? |
| **Prepared statement** | Does the server or client retain the parsed statement structure for reuse? |
| **Custom plan** | Is the query planned using the parameter values **of this execution**? |
| **Generic plan** | Can one shared plan be reused across **multiple runs with varying values**? |

A common misconception is:

> “Once you run `PREPARE`, PostgreSQL builds one plan once and every subsequent `EXECUTE` must reuse that exact plan.”

This is **false** in PostgreSQL. A single prepared statement may run with **distinct custom plans**, or switch to a **generic plan**, depending on configuration and the planner's selection heuristic.

Another misconception:

> “A Java app uses `PreparedStatement`, so PostgreSQL is definitely using a generic plan.”

Also **false**. `PreparedStatement` is a JDBC client API; whether the driver uses named server-side prepared statements and whether PostgreSQL picks a generic or custom plan are **two independent decisions**.

## 2. Why Does PostgreSQL Need a Query Plan?

SQL specifies **what result is requested**, not step-by-step physical data access.

For example:

~~~sql
SELECT job_id, payload
FROM jobs
WHERE state = 'rare';
~~~

PostgreSQL must decide whether to:

- Scan the entire table (`Seq Scan`).
- Probe a B-tree index (`Index Scan`).
- Combine index entries via `Bitmap Index Scan` + `Bitmap Heap Scan`.
- Perform sorting if `ORDER BY` is present.
- Pick join order, join algorithms, and indexes for joins.
- Estimate rows satisfying `WHERE`.
- Weigh I/O, CPU, parallelism, and other plan costs.

These choices form the **execution plan**, visible with:

~~~sql
EXPLAIN
SELECT job_id, payload
FROM jobs
WHERE state = 'rare';
~~~

The planner does not guess blindly; it evaluates metadata, table statistics, indexes, predicates, and its cost model.

### 2.1. Two Parameter Values Can Imply Very Different Workloads

Suppose a table has 1,000,000 rows:

~~~text
state = 'common': 999,000 rows
state = 'rare'  :   1,000 rows
~~~

For `state='common'`, a `Seq Scan` is typically cheaper than traversing an index for 99.9% of rows and fetching heap pages repeatedly.

For `state='rare'`, an `Index Scan` or `Bitmap Heap Scan` wins easily because only a tiny fraction of rows match.

Identical SQL structure plus **skewed parameter distributions** produces different optimal plans.

This is where custom plans shine.

## 3. Path from SQL to Execution Plan

A simplified pipeline:

~~~text
Application sends SQL statement
          |
          v
Syntax parsing (parse)
          |
          v
Semantic / type / relation analysis (analyze)
          |
          v
Query rewriting if applicable (rewrite)
          |
          v
Planning (plan)
          |
          v
Execution (execute)
          |
          v
Return results
~~~

Prepared statements let the server retain parse and rewrite structures to skip repeated parsing work. At the planning stage, a choice remains:

~~~text
Prepared statement exists
          |
          v
EXECUTE with new parameter values
          |
          +--> Custom plan:
          |      plans considering this execution's parameter values
          |
          +--> Generic plan:
                 uses a single plan independent of
                 specific parameter values
~~~

**Generic does not mean lacking `WHERE` filtering or indexes.** It simply means the planner did not optimize assuming specific constant parameter values when building the plan.

## 4. PREPARE, EXECUTE, and DEALLOCATE

PostgreSQL provides direct SQL syntax:

~~~sql
PREPARE statement_name (parameter_type, ...)
AS
sql_statement;
~~~

A self-contained example needing no table:

~~~sql
PREPARE plus_tax(numeric) AS
SELECT $1 + 10::NUMERIC AS total;

EXECUTE plus_tax(100);
EXECUTE plus_tax(250);

DEALLOCATE plus_tax;
~~~

Results:

~~~text
EXECUTE plus_tax(100) -> 110
EXECUTE plus_tax(250) -> 260
~~~

Components:

- `PREPARE` names the statement and declares parameter types.
- `$1` refers to the first parameter; `$2` to the second, etc.
- `EXECUTE` supplies concrete values.
- `DEALLOCATE` frees the named prepared statement in the current session.

### 4.1. Does PREPARE Execute the Query?

`PREPARE` registers the statement for later runs; **it does not return query rows from the prepared SELECT**.

~~~sql
PREPARE find_one(bigint) AS
SELECT $1 AS requested_id;
~~~

To retrieve results:

~~~sql
EXECUTE find_one(42);
~~~

### 4.2. You Cannot Prepare Two Statements with the Same Name in One Session

If `plus_tax` already exists, running `PREPARE plus_tax` again in the same session errors. Run `DEALLOCATE plus_tax` first or pick another name.

Never blindly run `DEALLOCATE ALL` in a shared application session executing unrelated features, as it drops **every prepared statement in the current session**.

### 4.3. How Long Does PREPARE Live?

A SQL `PREPARE` statement lives for the **current session** until explicitly deallocated via `DEALLOCATE` or until the session disconnects.

It is not shared across other connections and is not a persistent schema object like a `TABLE` or `VIEW`.

## 5. PostgreSQL's Distinct “Prepared” Layers

The phrase “prepared statement” appears at several layers:

| Layer | Example | Meaning |
|---|---|---|
| SQL server-side | `PREPARE name(text) AS ...` | Creates a named prepared statement inside the PostgreSQL session |
| Wire protocol | PostgreSQL extended query protocol: Parse/Bind/Execute | Driver sends SQL and parameter values using named or unnamed statements |
| JDBC | `connection.prepareStatement(sql)` | Application allocates a `PreparedStatement` object and binds values |
| Driver cache | Statement cache in driver/pool | Reuses parsed structures and cuts protocol round trips |
| Server plan cache | Generic vs. custom plan selection | PostgreSQL decides whether to replan per execution or reuse a cached plan |

These layers **relate to one another without being identical**.

For example, Java calling:

~~~java
PreparedStatement ps = connection.prepareStatement(
    "SELECT job_id FROM plan_lab.jobs WHERE state = ?"
);
~~~

does not automatically mean a SQL-level `PREPARE name` was issued, nor that a named server statement exists right away. The driver can use unnamed extended-protocol statements initially and switch to named statements only after crossing a threshold.

To determine whether PostgreSQL ran a generic or custom plan, observe the **database server**, not the JDBC API class name.

## 6. What Is a Generic Plan?

A **generic plan** is optimized **without depending on specific parameter values** for a particular invocation.

Example:

~~~sql
PREPARE find_by_state(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;
~~~

When building a generic plan, the server cannot assume `$1 = 'rare'` or `$1 = 'common'`. It must choose a general plan valid for any legal value.

Illustrative plan:

~~~text
Seq Scan on jobs
  Filter: (state = $1)
~~~

A plan referencing `$1` can be reused across calls:

~~~sql
EXECUTE find_by_state('rare');
EXECUTE find_by_state('common');
~~~

### 6.1. Advantages of Generic Plans

- Eliminates planner CPU overhead once the plan is cached.
- Ideal for tiny, high-frequency queries where planning time represents a large fraction of latency.
- Remains stable when row counts and access paths look similar across parameter values.
- Works well on uniform distributions where generic plans perform comparably to custom plans.

### 6.2. Limitations of Generic Plans

- Cannot tailor access paths to specific values known only at execute time.
- Relies on general average selectivity rather than per-value MCV skew.
- Often cannot prove predicates needed to qualify for partial indexes.
- Can select poor join orders, scan types, or sort strategies for outlier parameters.
- A plan good for dominant values can hurt tiny or massive tenants.

**Generic plans are not inherently slow.** Trouble arises when **one shared plan shape** clashes with extreme cost differences across parameter values.

## 7. What Is a Custom Plan?

A **custom plan** is generated when PostgreSQL knows **the concrete parameter values of the current execution**.

With the same prepared statement:

~~~sql
EXECUTE find_by_state('rare');
EXECUTE find_by_state('common');
~~~

Using custom plans, the optimizer can evaluate:

~~~text
Run 1: state='rare'
  -> few rows estimated
  -> may choose Index Scan

Run 2: state='common'
  -> huge number of rows estimated
  -> may choose Seq Scan
~~~

*(Conceptual illustration; real plans depend on actual data, indexes, and statistics.)*

### 7.1. Advantages of Custom Plans

- Exploits **actual parameter values** for accurate per-value selectivity estimation.
- Handles skewed distributions and wildly varying filter selectivity well.
- Unlocks value-dependent partial indexes and parameter-appropriate join strategies.
- Pays off on expensive queries where execution savings dwarf planning overhead.

### 7.2. Trade-Offs

- Plans repeatedly across executions, consuming CPU and adding planning latency.
- At hundreds of thousands of short calls per second, repeated planning becomes a major bottleneck.
- Still relies on statistics: knowing parameter values does not guarantee an optimal plan if stats are stale or incomplete.

**Custom plan = planned with current parameters, not an automatic guarantee of the optimal plan.**

## 8. Comparing Generic vs. Custom Plans

| Aspect | Generic Plan | Custom Plan |
|---|---|---|
| Knows concrete parameter values at planning time | No | Yes |
| Reuses exact plan across different values | Yes | Replanned per execution |
| Repeated planning overhead | Lower once cached | Higher |
| Sensitive to skewed distributions | Prone to fitting some values poorly | Adapts per parameter value |
| Uses parameter-dependent partial indexes | Limited if predicate cannot be proved | Possible when literal implies predicate |
| Plan shape across common vs. rare values | Fixed until invalidated | Can switch dynamically |
| Tiny statement executed at massive QPS | Often beneficial | Planning cost can become significant |
| Large scan/join with selective outliers | Risky | Usually worth evaluating |
| Inspection tools | `EXPLAIN EXECUTE`, `pg_prepared_statements` | Same |
| Testing controls | `force_generic_plan` | `force_custom_plan` |

This table compares mechanics—not an assertion that generic always saves total time or custom always scans fewer rows.

## 9. How Does PostgreSQL Automatically Choose Generic vs. Custom?

By default, PostgreSQL uses:

~~~sql
SHOW plan_cache_mode;
~~~

Normally returning:

~~~text
auto
~~~

For a **parameterized prepared statement** under `plan_cache_mode = auto`, PostgreSQL applies a documented cost heuristic:

1. Runs **custom plans for the first five executions**.
2. Tracks the **average estimated cost** of those custom plans.
3. Builds and estimates the cost of a **generic plan**.
4. If the generic plan's estimated cost (accounting for avoided planning overhead) is not significantly worse than the custom average, PostgreSQL switches to caching and reusing the generic plan.
5. If the generic plan looks substantially more expensive, PostgreSQL **continues using custom plans**.

These comparisons operate on planner cost estimates, not stopwatch timings of five executions.

### 9.1. “After Five Runs It Always Switches to Generic” Is False

**The first five runs are an evaluation phase**, not a rule that the sixth execution always turns generic.

If the generic plan appears clearly more expensive than custom plans, PostgreSQL sticks with custom plans.

### 9.2. Statements Without Parameters

For a prepared statement **with zero parameters**, per-value custom planning has no parameters to specialize on, so PostgreSQL normally builds and caches a generic plan directly.

### 9.3. The Heuristic Operates per Prepared Statement

Within one connection, two prepared statements behave independently:

- Statement A: generic plan wins.
- Statement B: custom plans keep running.

There is no session-wide “everything becomes generic” switch in `auto` mode.

## 10. Controlling Behavior with plan_cache_mode

PostgreSQL provides three settings:

| Value | Meaning |
|---|---|
| `auto` | Default PostgreSQL cost heuristic |
| `force_custom_plan` | Forces custom plans whenever prepared-plan caching applies |
| `force_generic_plan` | Forces generic plans whenever possible |

Check current value:

~~~sql
SHOW plan_cache_mode;
~~~

Set for the current session:

~~~sql
SET plan_cache_mode = force_custom_plan;

-- Run EXPLAIN EXECUTE or EXECUTE on the prepared statement.

RESET plan_cache_mode;
~~~

Or:

~~~sql
SET plan_cache_mode = force_generic_plan;

-- Compare plans.

RESET plan_cache_mode;
~~~

**Important:** PostgreSQL checks `plan_cache_mode` at **execution time** of a cached statement, rather than locking it permanently at `PREPARE` time. You can `PREPARE` once and toggle the mode to compare plans on the exact same statement.

### 10.1. Testing Safely Inside a Transaction with SET LOCAL

~~~sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

-- EXPLAIN EXECUTE prepared_statement(...);

ROLLBACK;
~~~

`SET LOCAL` applies strictly within the current transaction and reverts automatically when it ends, preventing forgotten test overrides on long-lived sessions.

### 10.2. Never Flip Mode Cluster-Wide by Reflex

Setting `force_custom_plan` server-wide can spike planning CPU across all queries. Setting `force_generic_plan` globally can cripple parameter-sensitive queries.

Diagnose individual statements and access paths before touching global or pool-wide settings.

## 11. Lab: Creating a Skewed Table

Let's construct a lab dataset where the same query encounters two drastically different selectivities.

**Run only in a lab database**, never production. Ensure schema/table names do not clash with unrelated data.

~~~sql
CREATE SCHEMA plan_lab;

CREATE TABLE plan_lab.jobs (
    job_id BIGINT PRIMARY KEY,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO plan_lab.jobs (
    job_id, state, created_at, payload
)
SELECT
    g::BIGINT,
    CASE
        WHEN g % 1000 = 0 THEN 'rare'
        ELSE 'common'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    repeat('x', 120) || g::TEXT
FROM generate_series(1, 200000) AS g;

CREATE INDEX idx_jobs_state
ON plan_lab.jobs(state);

ANALYZE plan_lab.jobs;
~~~

The table contains:

- 200,000 rows.
- 199,800 rows with `state='common'`.
- 200 rows with `state='rare'`.
- A B-tree index on `state`.
- A `payload` column not included in the index, ensuring multi-row reads incur real heap-fetch cost.

Verify distribution:

~~~sql
SELECT
    state,
    COUNT(*) AS row_count
FROM plan_lab.jobs
GROUP BY state
ORDER BY state;
~~~

Expected result:

| state | row_count |
|---|---:|
| common | 199800 |
| rare | 200 |

### 11.1. Why Make payload Moderately Wide?

If a query only touches indexed columns and heap pages are all-visible, PostgreSQL can satisfy it via an Index Only Scan. Including non-indexed `payload` forces heap fetches so the cost difference between reading 99.9% of the table vs. 0.1% stands out clearly.

Exact plans still depend on host hardware, cache state, planner parameters, and PostgreSQL version—never insist every environment produce the exact same scan node name.

## 12. Start by Checking Both Literal Queries

Measure the rare value:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = 'rare';
~~~

Measure the common value:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = 'common';
~~~

Key observations to check:

- `'rare'` matches few rows → planner **may** pick Index Scan or Bitmap Heap Scan.
- `'common'` spans almost the whole table → planner **may** pick Seq Scan.
- `actual rows` differs by roughly three orders of magnitude.
- Buffer hits/reads and execution times diverge accordingly.
- Compare planner `rows` against `actual rows`.

**No single plan output is hardcoded here** because plans vary across PostgreSQL versions and local statistics.

### 12.1. EXPLAIN ANALYZE Executes the Query

`EXPLAIN (ANALYZE, BUFFERS)` actually executes the SELECT to collect timings and buffer metrics, incurring real CPU/I/O work on large tables even though result rows aren't streamed to the client.

On a 200,000-row lab table this is harmless; in production, evaluate load and statement timeouts before running `ANALYZE` on heavy queries.

## 13. PREPARE the Lookup to Compare Generic vs. Custom

Prepare the statement:

~~~sql
PREPARE job_lookup(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;
~~~

This registers `job_lookup` in the current session.

Force custom plans:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('common');
~~~

With the same prepared statement, the two `EXECUTE` calls can receive **two completely different plans**.

Illustrative plan fragments (format demonstration, not guaranteed output):

~~~text
-- Rare value:
Index Scan using idx_jobs_state on jobs
  Index Cond: (state = 'rare'::text)
~~~

~~~text
-- Common value:
Seq Scan on jobs
  Filter: (state = 'common'::text)
~~~

The main takeaway is not the node name itself, but that custom planning sees the parameter literal of **each execution**.

## 14. Force Generic Plan and Compare Again

No need to recreate the prepared statement—just switch mode:

~~~sql
SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE job_lookup('common');
~~~

In generic mode, the plan tree stays structurally identical across calls, such as:

~~~text
Seq Scan on jobs
  Filter: (state = $1)
~~~

or an index scan showing `state = $1`.

If the generic plan chooses `Seq Scan`, `'rare'` pays the penalty of scanning 200,000 rows just to return 200.

If the generic plan chooses `Index Scan`, `'common'` pays heavy random/repeated heap fetch costs and performs worse than a `Seq Scan`.

This is the classic **parameter-sensitive plan** dilemma: one shared plan struggles to fit opposing selectivities.

Reset back to default when done:

~~~sql
RESET plan_cache_mode;
~~~

Never leave `force_generic_plan` or `force_custom_plan` lingering on an application session after measuring.

## 15. Reading EXPLAIN EXECUTE to Tell Plan Types Apart

In PostgreSQL `EXPLAIN EXECUTE` output:

- Under a **custom plan**, conditions usually display the **bound constant value**, e.g. `state = 'rare'::text`.
- Under a **generic plan**, conditions still display the **parameter placeholder**, e.g. `state = $1`.

Illustrative contrast:

~~~text
Custom:
  Index Cond: (state = 'rare'::text)

Generic:
  Filter: (state = $1)
~~~

This is a practical visual clue, though you should inspect the **entire plan** rather than relying solely on one sub-expression.

### 15.1. EXPLAIN EXECUTE Differs from EXPLAIN SELECT Literal

~~~sql
EXPLAIN SELECT ... WHERE state = 'rare';
~~~

gives the planner a hardcoded literal from the start.

~~~sql
EXPLAIN EXECUTE job_lookup('rare');
~~~

inspects the plan **PostgreSQL actually picks for the prepared statement** (generic or custom).

If a production incident happens on a prepared statement and you only inspect literal `EXPLAIN` runs, you may be measuring a **completely different scenario**.

### 15.2. Execution Time Alone Is Not Enough

Compare all metrics side-by-side:

- `Planning Time`.
- `Execution Time`.
- `actual rows` vs. estimated `rows`.
- `Buffers: shared hit/read`.
- Scan, join, and sort/aggregate methods.
- `Rows Removed by Filter`.
- Application call frequency and p95/p99 latency.

Generic planning saves planning time at the risk of inflated execution time; custom planning spends extra planning time to avoid disastrous execution plans on rare values.

**Optimize total latency and resource budget**, not planning time in isolation.

## 16. Auto Mode: Testing the Default Heuristic

After `RESET plan_cache_mode`, a fresh prepared statement illustrates how execution history steers the heuristic.

Using an aggregate query so output remains one row:

~~~sql
PREPARE job_payload_size(text) AS
SELECT SUM(length(payload)) AS total_chars
FROM plan_lab.jobs
WHERE state = $1;
~~~

Execute repeatedly with the common parameter:

~~~sql
SET plan_cache_mode = auto;

EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');
EXECUTE job_payload_size('common');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE job_payload_size('rare');
~~~

On this skewed table:

- When the initial five calls hit `'common'`, all five custom plans pay full-table scan cost.
- A generic plan priced on average selectivity may compare favorably against those expensive custom plans.
- A later call with `'rare'` may therefore inherit an unsuitable generic plan.

This illustrates **history-dependent plan selection**. Switching to generic after five runs is not guaranteed unconditionally, as it depends on **estimated planner cost per statement**.

### 16.1. Why Can Parameter Order Matter?

Early custom runs establish the average custom cost baseline used by the heuristic. If initial warmup calls hit an unrepresentative parameter skew compared to steady-state traffic, generic vs. custom pricing gets biased.

In operations:

~~~text
Application starts up
  |
  +--> First 5 runs hit a giant tenant
  |
  +--> Server may favor a generic plan
  |
  +--> Subsequent runs hit small tenants
         |
         +--> queries risk poor performance
~~~

Even so, treat this as a hypothesis to **measure and confirm**, not an assumption about every prepared statement.

## 17. Inspecting Prepared Statements in Your Session

PostgreSQL provides a system view:

~~~sql
SELECT
    name,
    statement,
    parameter_types,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
ORDER BY name;
~~~

Key fields:

| Field | Meaning |
|---|---|
| `name` | Prepared statement name |
| `statement` | Underlying SQL text |
| `parameter_types` | Array of declared/inferred parameter types |
| `from_sql` | Whether created via SQL `PREPARE` vs. wire protocol |
| `generic_plans` | Count of times a generic plan was used |
| `custom_plans` | Count of times a custom plan was used |

Filtered query:

~~~sql
SELECT
    name,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
WHERE name IN ('job_lookup', 'job_payload_size');
~~~

### 17.1. This View Is Session-Scoped Only

`pg_prepared_statements` lists **prepared statements in your current backend session**, not across all connections in the PostgreSQL cluster.

Opening a separate pgAdmin window opens a separate session that cannot see named prepared statements created by a JDBC application connection.

DBAs frequently open a fresh terminal, see an empty `pg_prepared_statements`, and wrongly conclude “the application isn't using prepared statements.”

### 17.2. Plan Counters Are Not Row Counts or HTTP Requests

`generic_plans` and `custom_plans` count how many times each plan type was selected for that prepared statement in the session—not rows returned, client API counts, or elapsed time.

With pooled connections across many backend sessions, inspect relevant connections or use appropriate telemetry rather than extrapolating one session's view cluster-wide.

## 18. Distinguishing the Two “5”s in PostgreSQL and JDBC

Two separate mechanisms often default near **5**, yet live at **different architectural layers**.

### 18.1. PostgreSQL Server: Five Initial Custom Plans

Under `plan_cache_mode = auto`, PostgreSQL runs initial custom plans for parameterized prepared statements to build a cost baseline against generic plans.

This is a **server-side planner heuristic**.

### 18.2. PostgreSQL JDBC: Driver prepareThreshold

In pgJDBC (depending on driver config and version), `prepareThreshold` controls how many times a `PreparedStatement` runs before the driver promotes it to a **named server-side prepared statement**. Its common default is **5**.

This is a **client driver wire-protocol lifecycle setting**, unrelated to the planner's generic/custom choice.

### 18.3. Both Thresholds Can Fire Sequentially

Conceptual sequence:

~~~text
Java PreparedStatement created
          |
          v
Driver executes repeatedly
          |
          v
Depending on prepareThreshold and cache:
driver may switch to named server-side prepared statement
          |
          v
PostgreSQL receives executions of the prepared statement
          |
          v
Under plan_cache_mode=auto:
server weighs custom vs. generic via heuristic
~~~

Never add them rigidly into “exactly 10 requests” or “25 requests” to predict when generic plans appear. Driver caches, pool connection rotation, statement lifecycle, and protocol mode all vary.

**Reliable approach:** inspect actual driver config and observe server behavior directly instead of relying on mental math over defaults.

## 19. What Does a PostgreSQL JDBC PreparedStatement Mean?

Java example:

~~~java
String sql = """
    SELECT job_id, state
    FROM plan_lab.jobs
    WHERE state = ?
    ORDER BY job_id
    LIMIT ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "rare");
    ps.setInt(2, 20);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long jobId = rs.getLong("job_id");
            String state = rs.getString("state");
        }
    }
}
~~~

This uses the **JDBC API** with `?` placeholders. The driver sends parameters via PostgreSQL wire protocol, corresponding to `$1`, `$2` server-side.

### 19.1. PreparedStatement Cannot Bind Arbitrary Column Names with ?

Broken usage:

~~~java
// Do not pass SQL column names as value parameters:
String sql = "SELECT job_id FROM plan_lab.jobs ORDER BY ?";
~~~

`?` binds a **data value**, never an identifier to dynamically swap `job_id` or `created_at`. To support dynamic sort columns safely, whitelist approved SQL templates in application code.

### 19.2. Injection Protection and Plan Caching Are Separate Goals

Bind parameters help prevent **SQL injection via untrusted data values**, because inputs are never concatenated as SQL syntax.

However:

- Bind parameters do not force PostgreSQL to pick generic plans.
- Generic plans do not guarantee high speed.
- Dynamic identifiers/`ORDER BY` still require strict allowlists.
- Broken business logic or missing authorization remains insecure even inside `PreparedStatement`.

Evaluate security and performance independently.

## 20. Java/JDBC Lab: Reusing One Physical Connection

To observe how driver prepare thresholds work in practice, execute the same `PreparedStatement` repeatedly over the same `Connection`.

Java 17+ snippet (assuming a `DataSource` is configured):

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JobQueryDemo {
    private final DataSource dataSource;

    public JobQueryDemo(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void run() throws SQLException {
        String sql = """
            SELECT job_id, state
            FROM plan_lab.jobs
            WHERE state = ?
            ORDER BY job_id
            LIMIT 10
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            for (int execution = 1; execution <= 8; execution++) {
                String state =
                    (execution % 2 == 0) ? "rare" : "common";

                statement.setString(1, state);

                try (ResultSet rs = statement.executeQuery()) {
                    while (rs.next()) {
                        long jobId = rs.getLong("job_id");
                        String returnedState = rs.getString("state");

                        // Illustrates reading results; log if needed,
                        // but avoid printing every row in a benchmark.
                    }
                }
            }
        }
    }
}
~~~

This demonstrates reusing one `PreparedStatement` cleanly without string concatenation.

### 20.1. Why Keep the Same Physical Connection?

Server-side prepared statements are **session-bound**. If every loop iteration checks out a different physical connection, you may fail to build continuous execution history on a single server prepared statement.

A connection pool reuses physical connections over time, yet each physical connection holds its own independent statement state.

### 20.2. This Java Query Is Not the Ideal Skew Benchmark

Because the Java example adds `LIMIT 10` and `ORDER BY job_id` to keep output small, its plan shape can differ from `SELECT job_id, state, payload WHERE state = $1` in the SQL lab.

Never use latency numbers from this `LIMIT 10` snippet to judge custom/generic behavior for a full scan query—benchmark matching SQL, data, and parameters.

## 21. What Does prepareThreshold=0 Mean?

In pgJDBC, setting `prepareThreshold=0` **disables automatic promotion to named server-side prepared statements** via threshold counting.

It does **not** mean:

- You stop using the `PreparedStatement` Java API.
- Parameter values get concatenated into SQL strings.
- Bind parameters vanish.
- Every query falls back to string concatenation.
- PostgreSQL is forced into one specific plan type everywhere.

Depending on driver mode, pgJDBC can still send parameterized queries via unnamed statements in the extended query protocol.

Consult the exact pgJDBC docs for your driver version and measure planning, execution, network round trips, CPU, and pool behavior before changing thresholds.

### 21.1. Raising the Threshold Does Not Make Generic Plans Smarter

`prepareThreshold` governs **client driver statement-preparation lifecycle**; it cannot change data distributions or make a single generic plan optimal for wildly skewed parameters.

Never treat driver thresholds as a blanket cure for slow generic plans.

## 22. Prepared Statements Are Scoped per Connection

SQL-level `PREPARE` and PostgreSQL named prepared statements live inside a **single backend connection/session**.

Example:

~~~text
Connection A:
  PREPARE job_lookup(text) ...
  EXECUTE job_lookup('rare') -> succeeds

Connection B:
  EXECUTE job_lookup('rare')
  -> may fail because the statement was not prepared on session B
~~~

In a pool of 20 physical connections, each connection independently has:

- Its own set of prepared statements.
- Its own `generic_plans` / `custom_plans` counters.
- Its own parameter execution history.
- Its own plan cache state.
- Different invalidation timing depending on traffic.

### 22.1. Why Can the Same Endpoint Exhibit Erratic Latency?

One HTTP request might check out an older pooled connection already running a generic plan after hundreds of executions, while another hits a freshly opened connection still using custom plans.

Beyond plan caching, buffer cache warmth, locks, CPU contention, network jitter, and server load also contribute—yet per-connection prepared statement state is well worth checking.

### 22.2. Restarting the Application Only Hides Symptoms

Restarting clears session prepared statements and resets plan history. Latency drops briefly during the early custom-plan phase, only to regress again once connections transition back to generic plans.

Never rely on pool restarts as a fix before resolving underlying selectivity, statistics, or plan caching issues.

## 23. Transaction Pooling and PgBouncer

In **session pooling**, each client session maps cleanly to one server session for its lifetime, keeping session-level objects straightforward.

In **transaction pooling**, clients can be multiplexed across different backend connections between transactions, requiring careful handling of any session-scoped state.

For prepared statements:

- SQL `PREPARE name AS ...` creates state on the **server backend session**, which does not automatically migrate across backends.
- **Protocol-level named prepared statements** may be tracked/supported by newer pooler versions and configurations, subject to explicit setup and testing.
- Do not assume SQL `PREPARE/EXECUTE/DEALLOCATE` shares identical guarantees with protocol-level prepared statement handling in a pooler.
- Session-level `SET plan_cache_mode` vanishes across backend switches in transaction pooling.
- Driver parameters must align with your pooler version and mode.

### 23.1. What to Check with a Pooler

1. Is the pooler running session pooling or transaction pooling?
2. Does your pooler version support protocol-level prepared statements for your driver?
3. Is prepared-statement support explicitly enabled in pooler configuration?
4. How does the driver configure `prepareThreshold` and caches?
5. Does application code issue raw SQL `PREPARE` across transaction boundaries?
6. When backend connections rotate, does the driver handle re-preparation or throw “prepared statement does not exist”?
7. Are you using `SET LOCAL` inside a transaction instead of session-level `SET` when testing settings?

Never disable prepared statements application-wide before verifying pooler mode and compatibility.

## 24. Statistics Determine Plan Quality

Both custom and generic plans rely on PostgreSQL statistics:

- `reltuples` and `relpages` in relation metadata.
- Most common values (`most_common_vals`).
- Their frequencies (`most_common_freqs`).
- Estimated distinct counts (`n_distinct`).
- Histogram bounds where applicable.
- `null_frac`.
- Extended statistics for multi-column correlations.

Inspect `state` column statistics:

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'plan_lab'
  AND tablename = 'jobs'
  AND attname = 'state';
~~~

In our lab, because `'common'` dominates overwhelmingly, MCV captures this skew clearly.

### 24.1. What Does ANALYZE Fix?

~~~sql
ANALYZE plan_lab.jobs;
~~~

`ANALYZE` updates distribution statistics. If stats are stale after heavy data changes, **both generic and custom plans** can choose poorly.

Never force custom plans when stale histograms/MCVs are the real culprit—refresh stats and re-measure first.

### 24.2. Custom Plans Still Need Accurate Statistics

Even knowing `state='rare'`, if statistics are outdated or miss the skew, the planner can still misestimate rows and pick a suboptimal plan.

Knowing the parameter value does not guarantee accurate cardinality estimation.

## 25. How Does a Generic Plan Estimate Parameter Selectivity?

With a literal:

~~~sql
WHERE state = 'rare'
~~~

the planner checks MCV and sees `'rare'` represents ~0.1% of lab rows.

With a generic plan for:

~~~sql
WHERE state = $1
~~~

the planner cannot tell whether `$1` will be rare or common. It falls back on general average selectivity rules derived from column statistics.

When one value holds 99.9% of rows and others hold 0.1%, an average estimate for an **unknown parameter** fits neither extreme well.

Consequences can include:

- Misestimated row counts.
- Wrong scan method vs. custom planning.
- Suboptimal join algorithms.
- Poorly sized sort/hash memory or unexpected spills.
- Wide p95/p99 latency variance between rare/small and dominant/large tenants.

Adding a random index without checking query shape, stats, and generic/custom plan selection will not solve this reliably.

## 26. Partial Indexes and Parameters: A Very Common Trap

Suppose queries frequently target rare jobs (`state='rare'`):

~~~sql
CREATE INDEX idx_jobs_rare
ON plan_lab.jobs(job_id)
WHERE state = 'rare';
~~~

This partial index stores only rows satisfying `state = 'rare'`.

A literal query:

~~~sql
EXPLAIN
SELECT job_id
FROM plan_lab.jobs
WHERE state = 'rare';
~~~

can use the partial index whenever the planner deems it cheapest.

Yet for a prepared statement:

~~~sql
PREPARE lookup_any_state(text) AS
SELECT job_id
FROM plan_lab.jobs
WHERE state = $1;
~~~

a **generic plan** cannot prove:

~~~text
$1 always equals 'rare'
~~~

Consequently, a generic plan generally **cannot use a partial index restricted to `state = 'rare'`**, since the cached plan must remain valid for any `$1`.

### 26.1. Custom Plans Behave Differently

When `$1 = 'rare'` is known during custom planning, the optimizer can prove the query condition matches the partial index predicate and consider using it.

Test in the lab:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE lookup_any_state('rare');

SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE lookup_any_state('rare');

RESET plan_cache_mode;
~~~

Compare `Index Scan` / `Index Only Scan` and the chosen index name. Being *eligible* for a partial index in custom mode does not force the planner to use it if another path looks cheaper.

### 26.2. When Should You Split SQL Templates?

If an endpoint **exclusively queries `state = 'rare'`** as a fixed server-side business rule, writing a safe literal filter lets PostgreSQL prove index eligibility directly:

~~~sql
SELECT job_id
FROM plan_lab.jobs
WHERE state = 'rare';
~~~

When the filter value is user-supplied, weigh prepared-statement vs. partial-index trade-offs carefully.

Never interpolate untrusted user strings into SQL just to “enable a partial index”; always keep untrusted inputs bound as parameters.

## 27. Optional Filters: One Query-For-Everything Can Hurt Plans

A common API pattern:

~~~sql
WHERE ($1 IS NULL OR state = $1)
~~~

Meaning:

- When `$1` is NULL → return all states.
- When `$1` is non-NULL → filter by `state`.

Example:

~~~sql
PREPARE list_jobs(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE ($1 IS NULL OR state = $1);
~~~

In a custom plan:

- If `$1` is `NULL`, the optimizer simplifies away the redundant check.
- If `$1` is `'rare'`, the optimizer simplifies to `state = 'rare'` and can use indexes.

In a generic plan, the optimizer must preserve **both paths simultaneously**, often forcing a full sequential scan even when `$1 = 'rare'`.

### 27.1. Two Dedicated Query Templates Are Usually Cleaner

Instead of cramming two drastically different workloads into one query:

~~~sql
-- Without filter:
SELECT job_id, state, payload
FROM plan_lab.jobs;
~~~

~~~sql
-- With filter:
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;
~~~

Application code picks one of **two static templates** depending on whether the filter was supplied, while still binding the parameter safely.

This gives the planner clear predicate structure and preserves index eligibility. Not every optional filter needs splitting—decide based on call frequency, filter combinations, and real execution plans.

## 28. Tenant Skew: Same SQL, Vastly Different Tenant Sizes

A classic production pattern:

~~~text
tenant_id = 1       -> 30 million rows
tenant_id = 2       -> 100 rows
tenant_id = 3       -> 5,000 rows
tenant_id = 4       -> 200,000 rows
~~~

Application SQL:

~~~sql
SELECT ...
FROM events
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 100;
~~~

With an index:

~~~sql
CREATE INDEX idx_events_tenant_created
ON events(tenant_id, created_at DESC);
~~~

Even with this helpful index, queries adding joins, extra filters, or broader ranges face huge row-count differences between giant and tiny tenants.

One generic plan might suit the giant tenant while wasting effort on tiny ones, or vice versa.

### 28.1. Never Benchmark Only One “Typical” Tenant

Test at least:

- A tiny tenant.
- A medium tenant.
- A giant tenant.
- Any tenant with unusual data distributions.

Measure the identical prepared SQL under both `force_custom_plan` and `force_generic_plan`. Benchmarking only a giant tenant hides p99 regressions on tiny tenants (and vice versa).

## 29. Multi-JOIN Queries: Beyond Just Choosing an Index Scan

Consider:

~~~sql
PREPARE tenant_report(bigint) AS
SELECT
    o.order_id,
    c.customer_name,
    o.total_amount
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.tenant_id = $1;
~~~

If tenant 1 has millions of orders while tenant 2 has 100:

- Small tenant: Nested Loop + index lookups fits well.
- Giant tenant: Hash Join or Merge Join fits far better.
- Sorting, aggregation, and parallelism decisions diverge too.

A generic plan cannot know which tenant is running at planning time, making one static join tree suboptimal across extremes.

*(Conceptual schema example; do not run directly on `plan_lab.jobs`. Apply this analysis to real application tables.)*

## 30. Prepared Parameters and Partition Pruning

On tables partitioned by timestamp or tenant, runtime parameters dictate which partitions actually hold matching rows.

Conceptual example:

~~~sql
PREPARE find_events(timestamptz, timestamptz) AS
SELECT event_id, created_at
FROM partitioned_events
WHERE created_at >= $1
  AND created_at < $2;
~~~

Two pruning stages apply:

- **Plan-time pruning:** the planner knows enough constant bounds to prune partitions before execution.
- **Execution-time pruning:** partitions are pruned dynamically once runtime parameters bind, even inside a generic plan.

### 30.1. Generic Plan Does Not Mean Scanning Every Partition

PostgreSQL supports **runtime (execution-time) partition pruning** in appropriate contexts. Seeing `$1` and `$2` in a generic plan does not automatically mean every partition gets scanned.

In `EXPLAIN (ANALYZE)` on partitioned queries, pruned subplans appear with `(never executed)` or `Subplans Removed` depending on the plan node.

Inspect the actual plan, PostgreSQL version, partitioning scheme, and `WHERE` expressions instead of guessing from placeholders.

### 30.2. Custom Plans Can Still Retain an Edge

Custom planning knows bounds upfront at planning time, allowing it to prune early and tune costs for remaining partitions specifically. Still, runtime pruning narrows the gap considerably for generic plans in many workloads.

Never repeat “generic plans can't use partition pruning” as an absolute rule.

## 31. Parameter Types Also Affect Plans

Bound parameter types must align cleanly with column types and index operator classes.

Good example:

~~~sql
PREPARE find_job_id(bigint) AS
SELECT job_id, state
FROM plan_lab.jobs
WHERE job_id = $1;
~~~

This compares `BIGINT = BIGINT`, matching the primary key index cleanly.

If the application binds text and casts the table column instead:

~~~sql
-- Pattern requiring careful evaluation:
WHERE job_id::TEXT = $1
~~~

wrapping the **indexed column** in a cast prevents a standard B-tree index on `job_id` from matching equality directly.

Cast or bind the **parameter** to match the column type instead:

~~~sql
WHERE job_id = $1::BIGINT
~~~

### 31.1. Declare Explicit Parameter Types When Needed

~~~sql
PREPARE find_job_id(bigint) AS
SELECT job_id
FROM plan_lab.jobs
WHERE job_id = $1;
~~~

PostgreSQL infers parameter types from context when omitted, though ambiguous expressions like `$1 IS NULL` can fail type resolution without explicit types.

In JDBC, use matching typed setters (`setLong`, `setBigDecimal`, `setObject` with explicit SQL types).

### 31.2. Minor SQL Text Differences Create Distinct Statements

Drivers and plan caches key statements on SQL text (plus parameter types). Even semantically identical queries differing in whitespace, column lists, or casts create separate cache entries.

Do not assume slightly different `SELECT` statements share one plan cache.

## 32. When Can a Generic Plan Be Replanned (Invalidated)?

A cached generic plan is not frozen forever.

PostgreSQL performs **plan invalidation and replanning** when relevant metadata changes:

- DDL alters referenced tables.
- Relevant indexes or constraints change.
- Planner statistics refresh (`ANALYZE`) on referenced relations.
- Relevant `search_path` changes alter object resolution.
- The session recreates the prepared statement or resets cache.

The prepared statement stays alive while its internal cached plan refreshes automatically as needed.

### 32.1. DDL and Prepared Statements

If a prepared statement executes:

~~~sql
SELECT * FROM some_table WHERE id = $1;
~~~

and schema migrations alter column types or the result column list (`SELECT *`), PostgreSQL attempts to reparse/replan—and may throw an error if the **output result descriptor** changes incompatibly for a cached prepared statement.

During frequent rolling migrations, validate `SELECT` column lists against prepared statements carefully.

### 32.2. Refreshing Statistics Can Switch Plans

Running:

~~~sql
ANALYZE plan_lab.jobs;
~~~

invalidates dependent cached plans so subsequent executions pick updated statistics, potentially changing `EXPLAIN` output.

Note that running `ANALYZE` does not synchronize plan caches uniformly across every connection at once—each backend manages its own session prepared statements and counters.

## 33. search_path and Schema Resolution

Prepared statements sometimes reference unqualified table names:

~~~sql
PREPARE find_jobs(text) AS
SELECT job_id
FROM jobs
WHERE state = $1;
~~~

Changing `search_path` forces PostgreSQL to re-resolve table bindings cleanly.

In multi-schema or multi-tenant setups relying on dynamic `search_path`:

- Avoid ambiguous duplicate table names across schemas.
- Prevent untrusted roles from creating objects in schemas appearing earlier in `search_path`.
- Use schema-qualified names like `plan_lab.jobs` wherever practical.
- Test `search_path` interactions carefully under connection pooling.
- Never concatenate unvalidated request values into `search_path` or schema SQL.

### 33.1. search_path Changes Are Not Parameter Binding

`search_path` alters **schema object name resolution**, unlike `$1` supplying a `WHERE` filter value.

Do not treat `search_path`-based tenant routing as interchangeable with parameterized data filtering.

## 34. DEALLOCATE, DISCARD PLANS, and Lifecycle Management

Drop one SQL-level prepared statement:

~~~sql
DEALLOCATE job_lookup;
~~~

Drop all SQL-level prepared statements in the session:

~~~sql
DEALLOCATE ALL;
~~~

Clear cached query plans in the session:

~~~sql
DISCARD PLANS;
~~~

`DISCARD PLANS` frees cached plans in the current session so they replan when next invoked. It is an administrative/lifecycle tool, not a “make the planner smarter” command to run on every request.

### 34.1. Why Not Clear Plans Constantly to Avoid Generic Mode?

Constantly flushing plans forces statements back to early custom planning at the cost of:

- Heavy repeated parse/plan CPU overhead.
- Plan cache thrashing.
- Fragile session lifecycle management.
- Losing the legitimate benefits of prepared statements.

If generic plans perform poorly under skew, fix the query template, indexes, stats, or statement-level mode based on evidence rather than nuking caches globally.

### 34.2. DISCARD ALL Differs from DISCARD PLANS

`DISCARD ALL` resets temporary tables, GUC settings, cursors, locks, and prepared statements—not only cached plans. Never execute `DISCARD ALL` inside application/pooler logic without understanding every session state side effect.

## 35. When Should You Favor Custom Plans?

Warning signs worth investigating:

- Identical prepared statement yields huge row-count swings across parameter values.
- Generic `EXPLAIN EXECUTE` picks poor scans/joins for rare outliers.
- Custom plans run vastly faster for affected parameters.
- A partial index qualifies only when concrete parameter values are visible.
- p99 latency degrades only after a statement runs repeatedly.
- One endpoint runs slow for a specific tenant segment while staying fast for others.
- Planning time is negligible relative to execution time saved.

Safe lab test:

~~~sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE job_lookup('rare');

RESET plan_cache_mode;
~~~

If custom wins decisively, rollout options include:

- Wrapping that statement's transaction/scope with `SET LOCAL plan_cache_mode = force_custom_plan`.
- Splitting distinct SQL templates for sharply different query modes.
- Refining indexes/statistics so generic plans behave acceptably.
- Tuning driver preparation settings only when justified by measurement.

Never alter cluster-wide `plan_cache_mode` because of one slow query.

## 36. When Are Generic Plans a Great Fit?

Strong indicators:

- High-QPS query with stable structure.
- Planning CPU accounts for a meaningful share of total latency.
- Uniform or predictable parameter selectivity.
- An index/access path fits virtually all parameter values well.
- Generic and custom show nearly identical execution times across representative inputs.
- No parameter-dependent partial indexes are needed.
- Join cardinalities stay stable across tenants/statuses.

Example primary-key lookup:

~~~sql
PREPARE by_primary_key(bigint) AS
SELECT job_id, state
FROM plan_lab.jobs
WHERE job_id = $1;
~~~

With a unique PK matching one row per ID, generic and custom produce virtually identical access paths, making cached generic reuse an easy win on planning overhead.

**Still verify with measurements:** query shapes, visibility map state, indexes, and cache effects differ across systems.

## 37. Do Query Hints Solve This?

Core PostgreSQL SQL does not provide built-in syntax like:

~~~text
USE INDEX(index_name)
FORCE PLAN(...)
~~~

to pin exact execution plan nodes directly inside standard queries.

Third-party extensions can add hint mechanisms, though that sits outside default core PostgreSQL.

Standard native levers to use first:

1. Write semantically clean `WHERE`/`JOIN` predicates.
2. Keep statistics fresh with `ANALYZE`.
3. Design appropriate indexes.
4. Compare `plan_cache_mode` custom vs. generic behavior.
5. Split templates when optional filters bridge incompatible workloads.
6. Benchmark with `EXPLAIN (ANALYZE, BUFFERS)`.

Avoid “fixing” production queries by setting `enable_seqscan = off` or `enable_nestloop = off` globally. Those planner GUCs exist for diagnostics and often regress unrelated queries.

## 38. Observing Planning Overhead in pg_stat_statements

When `pg_stat_statements` is installed and configured, inspect aggregated planning vs. execution stats:

~~~sql
SELECT
    queryid,
    calls,
    plans,
    ROUND(total_plan_time::NUMERIC, 2) AS total_plan_ms,
    ROUND(mean_plan_time::NUMERIC, 4) AS mean_plan_ms,
    ROUND(mean_exec_time::NUMERIC, 4) AS mean_exec_ms
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

This query works on PostgreSQL versions and setups where `pg_stat_statements` exposes `plans` and `*_plan_time`.

### 38.1. track_planning May Be Disabled

Planning stats collection depends on configuration:

~~~sql
SHOW pg_stat_statements.track_planning;
~~~

If the extension isn't loaded or configured, checking this parameter errors or returns missing metrics. Never conclude “planning time is zero” if `track_planning` is disabled.

### 38.2. Does pg_stat_statements Show Generic vs. Custom?

`pg_stat_statements` aggregates total calls, plans, planning time, and execution time, yet provides no direct “generic_plan=true/false for request X” flag.

Combine:

- `EXPLAIN EXECUTE` under matching prepared setup.
- `pg_prepared_statements` on the target session.
- Application telemetry segmented by parameter group.
- Controlled tracing/logging.
- `pg_stat_statements` to spot abnormal plan-to-call ratios or high latency.

### 38.3. Permissions and Sensitive Data

Extension views and logs can expose SQL patterns and table structures. Restrict access appropriately and avoid logging sensitive bind parameter values in production solely to debug one query.

## 39. How to Benchmark a Prepared Statement Properly

Hold everything constant except the variable under test:

1. Identical SQL text.
2. Same database and PostgreSQL version.
3. Same data snapshot (or track any churn).
4. Identical indexes and statistics.
5. Identical settings aside from `plan_cache_mode`.
6. Same connection/session setup.
7. Representative sample of parameter values.
8. Multiple trials—never trust a single run.
9. Measure both `Planning Time` and `Execution Time`.
10. Inspect `BUFFERS`/I/O alongside wall-clock time.

Sample test protocol:

~~~sql
-- 1. Refresh statistics and prepare the statement once.
ANALYZE plan_lab.jobs;

PREPARE benchmark_job(text) AS
SELECT job_id, state, payload
FROM plan_lab.jobs
WHERE state = $1;

-- 2. Test custom plan for rare vs. common.
SET plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('common');

-- 3. Test generic plan for the same parameters.
SET plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('rare');

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE benchmark_job('common');

-- 4. Restore default settings.
RESET plan_cache_mode;

DEALLOCATE benchmark_job;
~~~

### 39.1. Recording Results

Lay metrics side by side:

| Parameter | Mode | Scan/Join | Est Rows | Actual Rows | Planning ms | Execution ms | Buffers |
|---|---|---|---:|---:|---:|---:|---|
| rare | custom | Record from EXPLAIN | ... | ... | ... | ... | ... |
| rare | generic | Record from EXPLAIN | ... | ... | ... | ... | ... |
| common | custom | Record from EXPLAIN | ... | ... | ... | ... | ... |
| common | generic | Record from EXPLAIN | ... | ... | ... | ... | ... |

Never invent numbers ahead of time; fill in actual measurements from your test database.

### 39.2. Execution Order Can Bias Benchmarks

If the first run reads cold pages from disk while the second hits warmed caches, the second mode appears faster regardless of plan quality.

Run multiple rounds, alternate execution order, compare `BUFFERS`, and separate cold vs. warm runs. In production, concurrency and background I/O amplify variance further.

## 40. Total Latency: Planning Plus Execution

Conceptual model:

\[
T_{\mathrm{total}}
\approx T_{\mathrm{planning}} + T_{\mathrm{execution}} + T_{\mathrm{other}}
\]

where `T_other` captures network round trips, lock waits, client deserialization, and overhead.

**Synthetic** illustrative table (not measured PostgreSQL timings):

| Strategy | Planning | Execution | Approximate Total |
|---|---:|---:|---:|
| Custom for `rare` | 0.7 ms | 1.3 ms | 2.0 ms |
| Generic for `rare` | 0.05 ms | 80 ms | 80.05 ms |
| Custom for `common` | 0.7 ms | 40 ms | 40.7 ms |
| Generic for `common` | 0.05 ms | 40 ms | 40.05 ms |

If `'rare'` dominates or represents latency-sensitive requests, generic plans hurt badly despite tiny planning savings.

If execution times stay flat across inputs and planning time is substantial, generic plans win.

Weight decisions by **real parameter frequencies**, not unweighted averages. High throughput paired with catastrophic p99 tail latency for small tenants remains a serious production bug.

## 41. Generic Plans and “Parameter Sniffing”

Some database ecosystems refer to parameter-dependent plan issues as **parameter sniffing**. In PostgreSQL discussions, use exact terms:

- **Custom plan:** planned using current execution parameter values.
- **Generic plan:** planned without assuming specific runtime parameter values.
- **Auto heuristic:** PostgreSQL's cost comparison deciding whether to cache a generic plan.

Never apply SQL Server or Oracle plan-cache troubleshooting steps mechanically to PostgreSQL; cache invalidation, heuristics, and sniffing mechanics differ fundamentally.

## 42. Prepared Statements Inside PL/pgSQL

Beyond SQL `PREPARE` and JDBC, PostgreSQL caches internal SQL plans inside procedural languages like PL/pgSQL.

Function example:

~~~sql
CREATE OR REPLACE FUNCTION plan_lab.count_jobs(
    requested_state TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $function$
DECLARE
    total_jobs BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO total_jobs
    FROM plan_lab.jobs
    WHERE state = requested_state;

    RETURN total_jobs;
END;
$function$;
~~~

Repeated function invocations reuse internal SQL plan caching with generic/custom trade-offs similar to prepared statements.

### 42.1. Do Not Assume Functions Always Replan or Always Stay Generic

Static SQL inside PL/pgSQL caches parameterized statements internally rather than reparsing every call from scratch.

If a function lags for certain inputs, testing equivalent queries with `plan_cache_mode` and `EXPLAIN` helps diagnose whether generic planning is responsible—remembering to separate PL/pgSQL call overhead from the embedded SQL plan.

### 42.2. Dynamic EXECUTE Inside PL/pgSQL

PL/pgSQL also offers dynamic execution via `EXECUTE dynamic_sql USING ...`, distinct from SQL-level `EXECUTE prepared_name(...)`:

~~~sql
EXECUTE
    'SELECT COUNT(*) FROM plan_lab.jobs WHERE state = $1'
INTO total_jobs
USING requested_state;
~~~

*(PL/pgSQL function body snippet—not standalone SQL at a prompt.)*

Dynamic `EXECUTE` plans the generated string on invocation rather than reusing static-SQL generic plan caching. While occasionally useful for parameter-sensitive statements, it incurs repeated planning overhead and requires strict `USING` / `format` / allowlisting to prevent SQL injection.

Never rewrite every function into dynamic SQL based on “custom plans are better.”

## 43. DML Statements Can Be Prepared Too

Prepared statements are not restricted to `SELECT`.

Example:

~~~sql
PREPARE set_job_state(bigint, text) AS
UPDATE plan_lab.jobs
SET state = $2
WHERE job_id = $1;
~~~

Test safely inside a rolled-back transaction:

~~~sql
BEGIN;

EXECUTE set_job_state(1000, 'common');

ROLLBACK;
~~~

This runs a real `UPDATE` in the lab transaction and rolls back afterward.

### 43.1. Generic/Custom Selection Applies to DML Too

For parameterized `UPDATE`, `DELETE`, and `MERGE`, access-plan selection affects:

- How target rows are located.
- Source/target scan and join strategies.
- Rows scanned before modification.
- Lock scope and transaction duration.
- CPU/I/O resource usage.

Plan selection never bypasses `CHECK`/`UNIQUE`/`FK` constraints, row-level locks, or transaction semantics.

### 43.2. Running EXPLAIN ANALYZE on DML Is Dangerous

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE set_job_state(1000, 'rare');
~~~

without a protective rolled-back transaction **executes the `UPDATE`** and mutates data. In labs, wrap in `BEGIN ... ROLLBACK`; in production, never run it casually.

## 44. Investigating “Fast at First, Then Suddenly Slow” Incidents

Symptom timeline:

~~~text
After application startup:
  an endpoint responds quickly

After many requests:
  the endpoint slows down for certain parameters

Restarting connections:
  fast briefly, then slows down again
~~~

This pattern **suggests** a prepared statement transitioning into an ill-fitting generic plan—though buffer cache churn, stale stats, locks, or shifting data can look similar. Verify before concluding.

### 44.1. Investigation Steps

1. Capture the exact endpoint SQL (filters, joins, `ORDER BY`, `LIMIT`).
2. Identify slow vs. fast parameter segments.
3. Inspect pgJDBC `prepareThreshold` and driver modes if applicable.
4. Inspect connection pooler mode and session lifetimes.
5. Verify whether server-side prepared statements are actually created.
6. Compare `EXPLAIN EXECUTE` under `force_custom_plan` vs. `force_generic_plan`.
7. Check `pg_prepared_statements` on an active session if accessible.
8. Inspect selectivity, estimated vs. actual rows, index usage, and buffers.
9. Verify statistics freshness and last `ANALYZE` timestamp.
10. Pick the right fix: stats, indexes, split templates, localized `SET LOCAL`, or driver config.
11. Benchmark across multiple parameter groups in staging.
12. Monitor p95/p99 latency and planning CPU after rollout.

Never jump straight to global `force_custom_plan` simply because the symptom story sounds familiar.

## 45. Quick Diagnostic Questions

| Symptom | Question to Investigate |
|---|---|
| Literal query fast, prepared query slow | Is the prepared statement running generic or custom? |
| Only one tenant is slow | Does that tenant have drastically different row cardinality? |
| Partial index ignored | Can the generic planner prove the index predicate holds for `$1`? |
| Slows down after warmup | Did a session switch to generic plan caching after initial calls? |
| Plan flips after `ANALYZE` | Did refreshed statistics alter estimated costs? |
| Index ignored on ID lookup | Does a cast on the column disable index matching? |
| `PreparedStatement` used, yet `pg_prepared_statements` empty | Wrong session, or driver hasn't created a named prepared statement yet? |
| Pooler throws “prepared statement does not exist” | Incompatible transaction pooling or missing driver/pooler setup? |
| Generic plan on partitioned table | Is execution-time pruning skipping unused partitions? |
| `force_custom_plan` speeds query, spikes CPU | How heavy is planning overhead across full QPS? |
| `EXPLAIN` looks fast, API still slow | Network latency, locks, huge result transfer, N+1 loops, or different parameters? |
| Raising `prepareThreshold` did nothing | Is data skew or SQL shape causing poor plans anyway? |

## 46. Common Errors and Misconceptions

### Error 1 — Thinking PREPARE Locks One Permanent Plan

False. PostgreSQL chooses custom or generic dynamically per statement.

### Error 2 — Thinking the Sixth EXECUTE Always Turns Generic

False. Five custom runs serve a cost heuristic; PostgreSQL keeps using custom plans if generic looks much worse.

### Error 3 — Assuming Java PreparedStatement Means Generic Plan

False. Client JDBC API, protocol statement preparation, and server plan caching are distinct layers.

### Error 4 — Confusing pgJDBC prepareThreshold with PostgreSQL's Five Custom Runs

False. One is driver wire-protocol lifecycle; the other is PostgreSQL server cost estimation.

### Error 5 — Running Only Literal EXPLAIN SELECT

Literal `EXPLAIN` can diverge from parameterized execution plans. Compare with `EXPLAIN EXECUTE`.

### Error 6 — Benchmarking Only One Parameter Value

Hides tenant and status skew. Test representative parameter segments.

### Error 7 — Thinking Generic Plans Never Use Indexes

False. Generic plans happily use indexes whenever overall statistics favor them.

### Error 8 — Thinking Custom Plans Are Always Faster

False. Repeated planning costs CPU, and stale stats still fool custom plans.

### Error 9 — Thinking Generic Plans Always Scan All Partitions

False. Runtime (execution-time) partition pruning prunes irrelevant partitions once bounds bind.

### Error 10 — Assuming Partial Indexes Always Trigger with Parameters

A generic plan cannot prove `col = $1` implies `col = 'rare'`. Custom plans can when `'rare'` is bound.

### Error 11 — Thinking pg_prepared_statements Is Cluster-Wide

False. It displays prepared statements for the **current backend session only**.

### Error 12 — Changing plan_cache_mode Globally for One Query

Risks regressing unrelated queries. Scope tests and fixes per statement/transaction.

### Error 13 — Forgetting RESET After Forcing a Mode

Leaves subsequent statements in that session using test overrides.

### Error 14 — Casting Indexed Columns in Predicates

`job_id::text = $1` defeats standard B-tree matching, unlike `job_id = $1::bigint`.

### Error 15 — Using WHERE ($1 IS NULL OR col = $1) Everywhere

Forces generic plans to cover both filtered and unfiltered paths at once; split templates when helpful.

### Error 16 — Skipping ANALYZE After Skewed Data Loads

Even custom plans make bad choices with outdated statistics.

### Error 17 — Treating Connection Restarts as a Fix

Restarts merely clear session caches temporarily; the root cause soon recurs.

### Error 18 — Expecting SQL PREPARE to Persist Across Transaction-Pooled Backends

Session-bound objects do not follow transactions across multiplexed backend connections; configure pooler and driver support carefully.

### Error 19 — Thinking Disabling Server Prepare Enables SQL Injection

Security depends on bind parameters and avoiding string concatenation—not driver `prepareThreshold`.

### Error 20 — Optimizing Planning Time While Ignoring Execution Time

Saving 0.5 ms in planning is worthless if a poor generic plan adds 80 ms to execution. Measure total cost.

### Error 21 — Running EXPLAIN ANALYZE on Unchecked Production DML

`ANALYZE` executes the `UPDATE`/`DELETE`/`INSERT` against live data.

### Error 22 — Assuming Cached Generic Plans Never Invalidate

DDL, index changes, `ANALYZE`, and `search_path` updates trigger invalidation and replanning.

### Error 23 — Overlooking search_path in Multi-Schema Prepared Statements

Unqualified tables depend on session `search_path`; qualify names or manage resolution cleanly.

### Error 24 — Measuring Only Warm-Cache Order

Always alternate run order and verify `BUFFERS` so disk caching doesn't fake plan gains.

### Error 25 — Treating EXPLAIN as Authorization Enforcement

Query plans have nothing to do with API permissions, RLS, or tenant access checks.

## 47. Checklist for Designing High-Performance Prepared Queries

**Step 1 — Start with clean SQL.** Clarify `WHERE`, `JOIN`, `ORDER BY`, minimal columns, and authorization rules.

**Step 2 — Bind parameters cleanly.** Never concatenate untrusted input into SQL text.

**Step 3 — Match parameter types.** Avoid casting indexed columns unnecessarily.

**Step 4 — Separate incompatible query modes.** Split templates instead of packing contradictory optional filters into one query.

**Step 5 — Keep statistics fresh.** Maintain `ANALYZE` cadence aligned with data churn and skew.

**Step 6 — Build purposeful indexes.** Use B-tree, partial, or composite indexes justified by real plans and workloads.

**Step 7 — Identify representative parameter profiles.** Include rare, common, tiny/giant tenants, and `NULL` cases if valid.

**Step 8 — Compare modes safely in a lab session.** `force_custom_plan` vs. `force_generic_plan`.

**Step 9 — Read `EXPLAIN EXECUTE`.** Compare estimated vs. actual rows, scans/joins, buffers, `Planning Time`, and `Execution Time`.

**Step 10 — Verify prepared statement lifecycle.** SQL `PREPARE`, pgJDBC threshold, pooler mode, and per-session counters.

**Step 11 — Load-test in staging.** Track p50/p95/p99 latency, planning CPU, and throughput.

**Step 12 — Keep changes narrow in scope.** Prefer per-statement/per-template fixes with an easy rollback to `auto`.

**Step 13 — Monitor post-rollout.** Do not stop after one favorable `EXPLAIN` snapshot.

## 48. Practice Exercises

### Exercise 1 — Simple PREPARE

Write a prepared statement `add_two(bigint, bigint)` returning the sum of two parameters.

**Hint:** `PREPARE add_two(bigint, bigint) AS SELECT $1 + $2;`.

### Exercise 2 — EXECUTE and DEALLOCATE

Execute `add_two` with 10 and 20, then free the statement.

**Hint:** `EXECUTE add_two(10, 20); DEALLOCATE add_two;`.

### Exercise 3 — Custom vs. Generic Difference

Why can a custom plan pick Index Scan for `'rare'` and Seq Scan for `'common'`?

**Hint:** Parameter values are known at custom planning time, exposing contrasting selectivities.

### Exercise 4 — Generic Is Not Always Slow

Name a query pattern where all parameter values have nearly identical selectivity and generic plans fit well.

**Hint:** Primary-key point lookup.

### Exercise 5 — Five-Run Heuristic

Does `auto` mode always switch to generic on the sixth execution?

**Hint:** No; PostgreSQL compares estimated costs first.

### Exercise 6 — plan_cache_mode

Write SQL to inspect `plan_cache_mode`, force custom in a session, and reset it.

**Hint:** `SHOW`, `SET`, and `RESET plan_cache_mode`.

### Exercise 7 — SET LOCAL

Inside one transaction, force generic planning and roll back to restore defaults.

**Hint:** `BEGIN; SET LOCAL plan_cache_mode = force_generic_plan; ... ROLLBACK;`.

### Exercise 8 — EXPLAIN EXECUTE

Write SQL inspecting `job_lookup('rare')` under `force_custom_plan`.

**Hint:** `EXPLAIN (ANALYZE, BUFFERS) EXECUTE job_lookup('rare')`.

### Exercise 9 — Placeholders in Plan Output

When `EXPLAIN EXECUTE` displays `state = $1`, which plan type is that usually?

**Hint:** Generic plan.

### Exercise 10 — Source Data Skew

In our 200,000-row lab table, how many rows are `'rare'` vs. `'common'`?

**Hint:** 200 and 199,800.

### Exercise 11 — Reading pg_prepared_statements

Write a query selecting `name`, `generic_plans`, and `custom_plans` for the session.

**Hint:** `SELECT ... FROM pg_prepared_statements`.

### Exercise 12 — Session Visibility

Why can't a new terminal see prepared statements created by a Java app on another connection?

**Hint:** Prepared statements are scoped per session.

### Exercise 13 — Two Thresholds of 5

Distinguish pgJDBC's default `prepareThreshold` from PostgreSQL's `auto` custom-plan heuristic.

**Hint:** Driver wire-protocol prepare lifecycle vs. server-side plan selection.

### Exercise 14 — Partial Index

An index covers only `state = 'rare'`. Why does a generic plan for `WHERE state = $1` avoid it?

**Hint:** It cannot prove `$1` always equals `'rare'`.

### Exercise 15 — Partial Index Under Custom Mode

When `$1 = 'rare'` in a custom plan, can the planner consider the partial index?

**Hint:** Yes, provided the planner proves predicate implication and cost favors it.

### Exercise 16 — Optional Filters

Why is `WHERE ($1 IS NULL OR state = $1)` hard for a generic plan to optimize?

**Hint:** One plan must remain valid for both filtered and unfiltered runs.

### Exercise 17 — Parameter Types and Casts

Compare `job_id::text = $1` with `job_id = $1::bigint`.

**Hint:** Casting the indexed column often blocks direct B-tree usage.

### Exercise 18 — ANALYZE

If `'common'`/`'rare'` proportions shift sharply, what should you do before forcing custom plans?

**Hint:** Run `ANALYZE` and inspect `EXPLAIN` again.

### Exercise 19 — Partition Pruning

Does a generic plan with `$1` guarantee every partition gets scanned?

**Hint:** No; execution-time partition pruning can eliminate partitions dynamically.

### Exercise 20 — JDBC Connections

Does running the same `PreparedStatement` SQL across different physical connections share one server prepared statement?

**Hint:** No; prepared statements are connection/session-bound.

### Exercise 21 — PgBouncer Transaction Pooling

Why can raw SQL `PREPARE`/`EXECUTE` fail across transactions if backends rotate?

**Hint:** Server prepared statements live inside a specific backend session.

### Exercise 22 — Plan Invalidation

Does a cached generic plan stay immutable forever after `PREPARE`?

**Hint:** No; DDL, statistics updates, or `search_path` changes can trigger replanning.

### Exercise 23 — EXPLAIN ANALYZE UPDATE

Why must you never run this casually in production?

**Hint:** `ANALYZE` executes the `UPDATE` against real rows.

### Exercise 24 — Total Latency

Custom planning takes 1 ms + 2 ms execution; generic planning takes 0.05 ms + 40 ms execution. Under equal test conditions, which wins for that parameter?

**Hint:** Custom planning yields far lower total latency.

### Exercise 25 — p99 Latency

Why is inspecting only mean latency insufficient under tenant skew?

**Hint:** Small or outlier tenant groups can suffer extreme tail latency hidden by the mean.

### Exercise 26 — Query Templates

Design two SQL templates for unfiltered vs. `state`-filtered reads, binding values safely when filtered.

**Hint:** One query omitting `WHERE state`, one query with `WHERE state = $1`.

### Exercise 27 — Per-Query Tuning

Why is cluster-wide `force_custom_plan` rarely a good first fix?

**Hint:** Planning CPU can spike across unrelated high-QPS queries.

### Exercise 28 — Benchmark Design

List at least five variables to hold fixed when comparing generic vs. custom plans.

**Hint:** SQL text, dataset snapshot, statistics, indexes, config, parameter values, cache state, multiple trials.

### Exercise 29 — pg_stat_statements

Are `plans` and `total_plan_time` always populated whenever the extension is installed?

**Hint:** Depends on tracking settings; check `pg_stat_statements.track_planning`.

### Exercise 30 — Troubleshooting

An endpoint is fast right after connection restart yet slows down after repeated calls on small tenants. Name three checks before modifying code.

**Hint:** Check prepared statement lifecycle, compare custom vs. generic `EXPLAIN EXECUTE`, and check selectivity/stats/indexes.

## 49. Frequently Asked Questions

### Are bind parameters always faster than literal SQL?

No. Bind parameters protect against SQL injection and support statement reuse, yet speed depends on how drivers/servers prepare statements, generic vs. custom plans, and underlying data skew.

### Is a PREPARE statement planned only once?

No. PostgreSQL can generate custom plans per execution, switch to a generic plan, and invalidate/replan whenever schemas or statistics change.

### Does a generic plan know parameter values at runtime?

**Yes during execution** to evaluate predicates and return matching rows. However, it **does not know specific parameter values while building the plan** to optimize selectivity per value.

That is the core distinction: generic plans do not “ignore parameters”—they simply **are not planned around specific parameter literals**.

### Should we set force_custom_plan across the whole connection pool?

Not by default. Measure cluster-wide planning CPU overhead first and look at statement-level fixes or split templates.

### Can we inspect a Java session's generic/custom counts from another pgAdmin connection?

No—`pg_prepared_statements` only exposes the current session's prepared statements. Use session-side telemetry, logs, or controlled testing instead.

### Should we force generic plans just for “plan stability”?

A fixed plan shape does not guarantee stable execution times across skewed inputs. One shared plan can severely degrade tail latency when selectivity varies widely.

### Why did force_custom_plan still pick Seq Scan for 'rare'?

Possible reasons include stale stats, missing or mismatched indexes, queries requesting too many columns/rows where Seq Scan actually wins in cost, or `'rare'` not being rare enough in real data. Inspect `EXPLAIN (ANALYZE, BUFFERS)` rather than assuming custom mode forces an Index Scan.

### How do partial indexes work alongside fixed states and prepared queries?

If an endpoint strictly hardcodes `state='rare'` as a fixed condition, keeping `'rare'` as a trusted literal template lets the planner prove partial-index applicability. When values come from users, measure generic/custom and never interpolate untrusted strings into SQL.

### After running ANALYZE, must all applications reconnect?

Not automatically. PostgreSQL invalidates and replans cached plans when referenced statistics update. Only investigate connection resets if lifecycle bugs or pool state issues are confirmed.

## 50. Summary

- **Parameterized SQL** separates input data from SQL syntax; **prepared statements** allow reusing parsing and preparation work.
- PostgreSQL uses two main strategies: **custom plans** tailored to current parameter values and **generic plans** reusable across arbitrary values.
- **Custom plans** adapt indexes/joins/scans to skewed distributions at the cost of repeated planning.
- **Generic plans** eliminate repeated planning once cached, yet one shared plan can perform poorly across contrasting parameter selectivities.
- Under `plan_cache_mode = auto`, PostgreSQL uses **custom plans initially** and switches to generic only after cost comparisons—**never assuming execution #6 unconditionally turns generic**.
- `plan_cache_mode` supports `auto`, `force_custom_plan`, and `force_generic_plan`; use forced modes strictly for **scoped experiments**, then reset.
- `EXPLAIN EXECUTE` reveals what PostgreSQL actually plans for prepared statements: generic plans show `$1`, while custom plans show bound literals.
- `pg_prepared_statements` tracks `generic_plans` and `custom_plans` for the **current session only**, not across the entire instance.
- **JDBC `prepareThreshold` and PostgreSQL's five-run custom heuristic operate at different layers.** A Java `PreparedStatement` does not automatically imply a server generic plan.
- **Skewed data**, partial indexes, optional filters, tenant skew, and multi-way joins can trip up generic plans on outlier inputs.
- Generic plans still benefit from **execution-time partition pruning**; never assume generic means full-partition scans.
- Planner statistics, bound parameter types, indexes, and SQL structure govern **both generic and custom** plan quality.
- Prepared statements are **server-session scoped**; configure connection poolers (especially transaction pooling) cleanly for protocol-level/server-side preparation.
- Cached generic plans invalidate and replan when schemas, indexes, stats, or `search_path` change.
- Always measure **planning time + execution time + tail latency**, buffers, cardinality, and representative parameter profiles before applying production changes.

The right question is not **“are generic or custom plans always better?”**—it is **“how do planning cost and execution cost trade off across our real parameter distribution?”** Distinguishing application prepared statements from server plan caching, and benchmarking across realistic parameter segments, turns PostgreSQL plan tuning into something **measurable, explainable, and controllable**.

# JIT and Compilation Cost per Query Type in PostgreSQL

PostgreSQL can use Just-In-Time compilation (JIT) to convert certain expressions in an execution plan into machine code via LLVM. For queries reading many rows and spending CPU evaluating conditions, computing projections, or deforming tuples, compiled code can run faster than the standard interpreter.

In return, JIT must generate code, optionally inline functions, and run LLVM optimization passes before executing the query. Compilation time is added overhead on each execution requiring JIT. A short query can spend more time compiling than it saves during execution. Thus JIT fits specific workloads and query shapes, rather than serving as a universal speedup switch for every SQL statement.

PostgreSQL decides whether to use JIT based on configuration and the estimated cost of the execution plan. Thresholds such as `jit_above_cost`, `jit_inline_above_cost`, and `jit_optimize_above_cost` control when JIT, inlining, and expensive optimizations kick in. These cost values are planner estimate units, not milliseconds.

~~~text
                 SQL query
                     |
                     v
               Query planner
                     |
              Estimated plan cost
                     |
                     v
               JIT eligibility
             /                 \
            /                   \
      Below threshold       Above threshold
           |                      |
           v                      v
    Normal execution        JIT decision
                                  |
                         +--------+--------+
                         |        |        |
                         v        v        v
                    Expressions Inline  Optimize
                    / tuple       calls  LLVM IR
                    deforming
                         |
                         v
                  Native code emission
                         |
                         v
                  Execute query plan
                         |
                         v
                Compare saved CPU time
                with compilation cost
~~~

This lesson belongs to the **Resource Tuning** chapter of the *Database Engine Relational PostgreSQL* module, focusing on JIT mechanics, compilation cost, and selecting configurations per query type.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain JIT compilation in PostgreSQL and the role of LLVM.
2. Distinguish interpreted expression evaluation from JIT-generated native code.
3. Identify the parts of the execution engine that JIT can accelerate.
4. Distinguish expression compilation from tuple deforming.
5. Explain generation, inlining, optimization, and emission costs.
6. Understand why JIT can slow down short queries.
7. Distinguish planner cost from execution time and milliseconds.
8. Check JIT availability using `pg_jit_available()`.
9. Read and tune `jit`, `jit_above_cost`, and related thresholds.
10. Understand `jit_inline_above_cost` and `jit_optimize_above_cost`.
11. Control expression compilation and tuple deforming.
12. Analyze JIT for OLTP point lookups and short transactions.
13. Analyze JIT for sequential scans, aggregations, and analytical queries.
14. Evaluate JIT with joins, filters, projections, and complex expressions.
15. Identify queries bound by I/O, locks, network, or compilation.
16. Read the JIT section in `EXPLAIN ANALYZE`.
17. Combine `EXPLAIN` with `pg_stat_statements` to measure compilation cost.
18. Benchmark JIT on/off fairly.
19. Configure JIT by session, role, database, and workload class.
20. Monitor CPU, latency, throughput, and concurrency impacts.
21. Avoid drawing false conclusions from a single run or a single query plan.
22. Build a JIT policy and troubleshooting workflow.

## 2. What Is JIT Compilation?

JIT is the technique of compiling code at runtime. Instead of purely interpreting an expression through the execution engine, the system generates specialized machine code for that expression and executes it.

### 2.1. Standard Expression Evaluation

PostgreSQL builds an execution plan consisting of scan, join, aggregate, sort, and other plan nodes. When an expression must be evaluated, the executor uses PostgreSQL's expression evaluation engine.

Example:

~~~sql
SELECT
    order_id,
    quantity * unit_price * (1 - discount_rate) AS net_amount
FROM app.order_items
WHERE quantity * unit_price > 1000;
~~~

The executor must read the columns, compute the expressions, and check the predicate for processed rows.

### 2.2. JIT Expression Compilation

When JIT is enabled and the query qualifies, PostgreSQL can compile certain expression operations into native code via LLVM. That code is used while executing the current query.

### 2.3. LLVM

LLVM provides the compiler and optimizer infrastructure. PostgreSQL emits intermediate representation (IR), which LLVM optimizes and compiles into machine code for the host architecture.

### 2.4. JIT Does Not Compile Entire SQL into a Standalone Program

PostgreSQL still builds an execution plan and runs plan nodes as before. JIT focuses on specific parts of the executor, notably expression evaluation and tuple deforming.

### 2.5. JIT Does Not Replace the Query Planner

The planner still decides scans, join order, join algorithms, index usage, and other nodes. JIT does not pick better indexes or fix a poor execution plan.

### 2.6. JIT Does Not Replace Indexing and Statistics

If a query reads excessive pages due to missing indexes or stale statistics, fix those causes. JIT can lower CPU on some expressions, yet it cannot turn a bad access path into a good one.

## 3. Requirements for PostgreSQL to Use JIT

JIT requires PostgreSQL to be built with LLVM support and a compatible runtime/compiler provider.

### 3.1. Build with LLVM

PostgreSQL binaries must be compiled with LLVM support enabled. If the installation lacks JIT support, enabling JIT configuration will not conjure a compiler.

### 3.2. Checking Availability

~~~sql
SELECT pg_jit_available();
~~~

`true` indicates a JIT provider is usable in the current session. `false` means JIT is unavailable, even if the configuration parameter is turned on.

### 3.3. Checking Configuration

~~~sql
SHOW jit;
SHOW jit_provider;
SHOW jit_above_cost;
SHOW jit_inline_above_cost;
SHOW jit_optimize_above_cost;
SHOW jit_expressions;
SHOW jit_tuple_deforming;
~~~

Some parameters may differ by major version or build. Use `SHOW` on the live server to confirm.

### 3.4. PostgreSQL Version

JIT was introduced in PostgreSQL 11. Capabilities, defaults, providers, and statistics details depend on major version and packaging.

### 3.5. Provider Fails to Load

If the LLVM provider or shared libraries are missing, incompatible, or fail to load, JIT may be unavailable. Check startup logs and package dependencies.

### 3.6. JIT Enabled Yet Query Does Not Use It

`jit = on` merely permits JIT. A query can still skip JIT because its estimated cost is below threshold, the provider is unavailable, or the execution plan lacks compilable work.

## 4. Parts That JIT Can Accelerate

PostgreSQL JIT focuses on expression evaluation and tuple deformation.

### 4.1. Expression Evaluation

JIT can compile expressions such as:
- Comparisons and `WHERE` predicates.
- Arithmetic expressions.
- Boolean expressions and `CASE`.
- Projection expressions in `SELECT`.
- Certain expressions used in joins and aggregates.
- Expressions evaluated repeatedly by the executor across many rows.

### 4.2. Tuple Deforming

Tuple deforming extracts column values from the tuple representation for executor use. In workloads processing huge numbers of tuples, tuple decoding cost can be substantial.

### 4.3. Function Inlining

Inlining replaces eligible function calls with their body inside the compiled code. This reduces call overhead and opens further optimization opportunities.

### 4.4. LLVM Optimization

LLVM can optimize the intermediate representation, such as simplifying expressions and eliminating redundant computations. Deeper optimization generally increases compilation time.

### 4.5. Code Emission

After generating and optimizing IR, the compiler emits machine code. This is part of compilation overhead counted toward total query latency.

### 4.6. What JIT Does Not Solve by Itself

JIT does not automatically:
- Make storage faster or eliminate disk I/O.
- Reduce lock waits or deadlocks.
- Increase network throughput.
- Fix cardinality estimates.
- Create indexes or pick a different join order.
- Replace sort/hash algorithms with new algorithms.
- Compile every PL/pgSQL procedure or C extension into query native code.

### 4.7. JIT and Plan Nodes

A scan node can invoke compiled expressions to evaluate predicates or form outputs. For joins/aggregates, JIT can speed up expressions the node evaluates; it does not mean the entire join or aggregate algorithm is recompiled.

## 5. Costs of JIT

JIT lowers execution cost after code is generated, yet code generation itself consumes resources.

### 5.1. Generation Time

PostgreSQL builds the JIT context and IR/code structures. This work consumes CPU and memory.

### 5.2. Inlining Time

The compiler analyzes and inlines eligible functions. Inlining can produce larger code and slow down compilation.

### 5.3. Optimization Time

LLVM runs optimization passes. Queries with complex expressions can take extra time and resources during this phase.

### 5.4. Emission Time

LLVM emits machine code. Emission time is included in JIT compilation cost.

### 5.5. Compilation Memory

The compiler requires memory for IR, optimization passes, and generated code. Many concurrent JIT queries can raise memory pressure.

### 5.6. CPU Contention

If many backends compile complex queries simultaneously, CPU spent compiling competes with workload execution and other PostgreSQL processes.

### 5.7. Total Latency

A conceptual model:

\[
T_{\text{total}} =
T_{\text{planning}} +
T_{\text{JIT}} +
T_{\text{execution}} +
T_{\text{other}}
\]

Here JIT time comprises generation, inlining, optimization, and emission when those stages run. PostgreSQL can display several of these components separately in `EXPLAIN`.

### 5.8. When JIT Helps

JIT helps when CPU time saved during execution exceeds compilation overhead and associated resource costs.

### 5.9. When JIT Hurts

If a query runs in only a few milliseconds or mostly waits on I/O or locks, compilation time can increase total latency.

## 6. Planner Cost and JIT Thresholds

PostgreSQL uses estimated plan cost to decide when to activate JIT.

### 6.1. Cost Is Not Milliseconds

Planner cost is a relative unit computed from parameters like page cost, CPU tuple cost, and CPU operator cost. A plan cost of 100000 does not mean the query runs for 100000 milliseconds.

### 6.2. Estimated Total Cost

JIT thresholds are compared against the query plan's total estimated cost. This is a planner forecast based on statistics and cost settings.

### 6.3. jit_above_cost

`jit_above_cost` is the estimated cost threshold to start using JIT. If query cost exceeds the threshold and JIT is available, PostgreSQL can compile eligible parts.

~~~sql
SHOW jit_above_cost;
~~~

### 6.4. jit_inline_above_cost

`jit_inline_above_cost` is the cost threshold to enable inlining. Inlining adds compile cost and therefore has its own threshold.

~~~sql
SHOW jit_inline_above_cost;
~~~

### 6.5. jit_optimize_above_cost

`jit_optimize_above_cost` is the threshold to enable more expensive optimization passes.

~~~sql
SHOW jit_optimize_above_cost;
~~~

### 6.6. Independent Thresholds

A query can qualify for JIT yet fall below the thresholds for inlining or deep optimization. This lets compilation effort scale with expected workload weight.

### 6.7. Value -1

For thresholds supporting `-1`, that value disables the corresponding stage. For instance, `jit_above_cost = -1` prevents automatic JIT activation via cost threshold; `jit_inline_above_cost = -1` disables threshold-based inlining.

### 6.8. Bad Estimates

If statistics are stale or parameter estimates are inaccurate, planner cost may not match actual CPU time. A query may trigger JIT despite running briefly, or skip JIT despite being very CPU-heavy.

## 7. Key JIT Parameters

| Parameter | Role | Question to answer |
| --- | --- | --- |
| `jit` | Enables JIT | Is JIT allowed in the session? |
| `jit_provider` | Compiler provider | Which provider supplies JIT? |
| `jit_above_cost` | JIT activation threshold | Which queries have enough cost to compile? |
| `jit_inline_above_cost` | Inlining threshold | When is function inlining worthwhile? |
| `jit_optimize_above_cost` | Optimization threshold | When is deep optimization worthwhile? |
| `jit_expressions` | Compile expressions | Should expression evaluation be compiled? |
| `jit_tuple_deforming` | Compile tuple deformation | Should tuple decoding be compiled? |

### 7.1. jit

~~~sql
SHOW jit;
SET jit = off;
SET jit = on;
~~~

`jit = off` disables JIT in the session. This is useful for A/B benchmarking or disabling JIT for unsuitable workloads.

### 7.2. jit_expressions

~~~sql
SET jit_expressions = on;
~~~

Controls JIT compilation of expression evaluation.

### 7.3. jit_tuple_deforming

~~~sql
SET jit_tuple_deforming = on;
~~~

Controls JIT compilation of tuple deformation. Effectiveness depends on tuple count and schema/query shape.

### 7.4. Session-Level Changes

Use `SET` to test on a dedicated connection without affecting other sessions.

### 7.5. Transaction-Level Changes

~~~sql
BEGIN;
SET LOCAL jit = off;
SELECT count(*) FROM app.events;
COMMIT;
~~~

`SET LOCAL` lasts only for the current transaction. This helps when an application wants to control JIT for a specific group of queries.

### 7.6. Role/Database Defaults

Use `ALTER ROLE ... SET` or `ALTER DATABASE ... SET` to apply default policies to new sessions. Verify after reconnecting because session-level settings do not retroactively alter open sessions.

## 8. JIT Thresholds Are Not Query Timeouts

JIT thresholds decide whether to compile, not how long a query may run.

### 8.1. Not statement_timeout

`statement_timeout` caps how long a statement is allowed to execute. `jit_above_cost` uses estimated planner cost to decide on compilation.

### 8.2. Not a CPU Budget

JIT thresholds neither grant nor cap CPU milliseconds. A high-cost query may spend its time waiting on I/O; a low-cost query can still burn heavy CPU if estimates are wrong.

### 8.3. Not a Row Count Limit

A query processing many rows can have low or high cost depending on plan and cost settings. Do not use row count alone to infer whether JIT activates.

### 8.4. Not a Latency Threshold

If your target query latency is under 100 ms, do not set `jit_above_cost = 100`. Cost units do not map directly to milliseconds.

### 8.5. Use EXPLAIN to Confirm

Read the plan cost and JIT section of the query itself instead of guessing from parameters.

## 9. JIT with OLTP Point Lookups

OLTP typically consists of many short transactions touching a few rows with strict low-latency requirements.

### 9.1. Point Lookup Example

~~~sql
SELECT order_id, status, created_at
FROM app.orders
WHERE order_id = 9000123;
~~~

If a primary key index quickly locates one row, expression evaluation is tiny compared to planning, access, and returning the result.

### 9.2. Compilation Overhead Dominates

A query completing in a short duration lacks enough arithmetic/evaluation work to amortize code generation.

### 9.3. High Execution Frequency

OLTP may execute the same query thousands of times. If each execution incurs JIT generation, cumulative compile CPU can become substantial.

### 9.4. Prepared Statements

Prepared statements can reuse query plans, yet do not assume plan caching means native JIT code is cached and reused across all executions. Measure generation time relative to calls on your running version.

### 9.5. Typical Policy

For latency-sensitive OLTP workloads, test `jit=off` on the application role/database/session and benchmark. Do not disable it cluster-wide if analytical queries still benefit from JIT.

### 9.6. Exceptions

An OLTP query with CPU-intensive expressions processing many rows might benefit. Classify by query shape and actual work rather than the OLTP label alone.

## 10. JIT with Large Sequential Scans

Sequential scans can process huge numbers of tuples. When every tuple evaluates expressions, JIT has room to cut CPU.

~~~sql
SELECT
    sum(quantity * unit_price * (1 - discount_rate))
FROM app.order_items
WHERE extract(year FROM created_at) = 2025
  AND quantity * unit_price > 1000;
~~~

### 10.1. Many Rows

An expression evaluated across millions of tuples generates enough CPU work to amortize compilation.

### 10.2. Complex Predicates

Arithmetic, Boolean logic, `CASE`, and projection calculations are prime candidates for JIT compilation.

### 10.3. I/O Still Matters

If the table is not cached and the query mainly waits on storage, JIT may reduce some CPU without meaningfully improving elapsed time.

### 10.4. Non-Sargable Predicates

JIT does not turn an expression on a column into an index condition. Where an expression index, generated column, or predicate rewrite applies, evaluate the access path separately.

### 10.5. Measure CPU vs. Elapsed Time

If CPU time drops while elapsed time barely budges, the query may be bound by I/O or another wait event.

## 11. JIT with Aggregation

Aggregations can process large row sets and evaluate many expressions.

### 11.1. Aggregate Expression

~~~sql
SELECT
    customer_id,
    sum(quantity * unit_price) AS gross_amount,
    avg(quantity * unit_price) AS average_line_amount,
    count(*) FILTER (WHERE status = 'returned') AS returned_lines
FROM app.order_items
GROUP BY customer_id;
~~~

### 11.2. Expression Work

JIT can accelerate expression evaluation for inputs and projections. Benefit generally scales with tuple count and computation complexity.

### 11.3. Hash Aggregate

JIT does not replace the hash table algorithm. It can compile expressions evaluated by the executor when extracting keys, filtering, or computing aggregate inputs.

### 11.4. Sort Aggregate

If the plan sorts before aggregating, sort duration must still be evaluated separately. JIT does not eliminate sorting cost.

### 11.5. Aggregates Over Few Rows

An aggregate over a handful of rows rarely has enough work to offset compile overhead.

## 12. JIT with Joins

Joins can process many tuples and repeatedly evaluate join/filter expressions.

~~~sql
SELECT
    o.region_id,
    sum(oi.quantity * oi.unit_price) AS revenue
FROM app.orders AS o
JOIN app.order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.created_at >= DATE '2025-01-01'
  AND o.created_at < DATE '2026-01-01'
GROUP BY o.region_id;
~~~

### 12.1. Join Conditions

Join condition expressions can be part of the expression evaluation compiled by JIT.

### 12.2. Post-Join Filters

Filter expressions are evaluated on tuples flowing through plan nodes. With high tuple counts and rich expressions, JIT can reduce CPU.

### 12.3. Hash Join

JIT can assist expression evaluation around a hash join. It does not change hash table size, batch count, memory usage, or join algorithm.

### 12.4. Nested Loop

If a nested loop repeats the inner scan many times, expression work can be significant. Still, a poor join order must be fixed at the planner/index level.

### 12.5. Merge Join

JIT does not replace sorting/merge mechanics. Evaluate expression CPU separately from sort/access costs.

### 12.6. Cardinality Estimates

Wrong join estimates can skew both plan costs and JIT eligibility. Update statistics and compare estimated vs. actual rows.

## 13. JIT with Expressions and Functions

JIT targets expressions handled by the executor. Do not assume every function or procedural language gets compiled.

### 13.1. Arithmetic and Boolean

Numeric math, comparisons, and logic over many rows are classic cases where JIT shines when expression work dominates.

### 13.2. CASE

`CASE` expressions evaluated across many rows have good compilation potential.

### 13.3. Built-In Functions

Expressions may call built-in functions. JIT does not guarantee every function body is inlined or compiled; some calls still go through normal function dispatch.

### 13.4. PL/pgSQL

JIT does not compile an entire PL/pgSQL body into a native program. SQL statements and expressions executed inside may go through executor/JIT on their own terms.

### 13.5. C Extensions

JIT does not recompile C extension code. Extensions are compiled and loaded via their own mechanism.

### 13.6. Regex and JSON

Queries using regex or JSON spend time inside function implementations, parsing, and allocations. JIT may optimize surrounding expressions, yet should not be expected to erase internal costs of complex functions.

### 13.7. Function Volatility

Function volatility, strictness, and inlinability affect planner/executor behavior. Do not judge JIT suitability merely from the presence of function calls.

## 14. JIT with Sort, Window, and Analytic Queries

Analytical queries often contain many expressions, yet runtime can also be dominated by sorting, memory, and I/O.

### 14.1. Sort Keys

JIT can speed up expressions computing sort keys. The sort algorithm and data comparisons/movement still carry their own cost.

### 14.2. Window Functions

Input, filter, and projection expressions can be JIT compiled. Window framing and partition/order processing are not wholly replaced by JIT.

### 14.3. Wide Rows

Tuple deforming can become expensive when queries read many columns or tuples. Check projection pruning and select only needed columns.

### 14.4. Large Analytical Scans

This class is most likely to benefit when CPU expression evaluation is the bottleneck and queries run long enough.

### 14.5. Memory Spills

If sorts/hashes spill to temporary files, I/O and memory settings can dominate runtime. JIT is no substitute for tuning `work_mem`, query shape, or storage.

## 15. JIT and Parallel Queries

Parallel queries split work across leader and workers. JIT must still be evaluated alongside compilation and scheduling overhead.

### 15.1. Parallel Plans

A parallel query often processes large tuple volumes and heavy expression workloads, creating opportunities for JIT.

### 15.2. Compilation Overhead

Parallelism does not make compilation cost disappear. Measure JIT timings and total elapsed time under equivalent concurrency.

### 15.3. CPU Saturation

If workers already saturate CPU, extra compilation can raise contention. Compare whole-system throughput rather than single-query latency.

### 15.4. Worker Variability

Launched worker counts can differ from planned counts due to resource limits. Record plans and worker counts when benchmarking.

### 15.5. Evaluating Under Concurrency

An isolated query might benefit, yet when many JIT queries run simultaneously, compilation can elevate p95/p99 latency. Benchmark at production-like concurrency.

## 16. JIT and Prepared Statements

Prepared statements cut parse/plan overhead on repeated runs, yet JIT is a separate step.

### 16.1. Plan Reuse

A prepared statement can use a custom plan or a generic plan depending on execution history and planner heuristics.

### 16.2. JIT Eligibility

JIT uses the plan cost of the active execution plan. A generic plan has different cost estimates than a custom plan and can trigger different JIT decisions.

### 16.3. Parameter Sensitivity

Different parameter values can produce vastly different actual row counts. A generic plan does not reflect every specific parameter value.

### 16.4. JIT Code Lifetime

Do not assume native code is cached forever just because a prepared statement persists. Measure JIT generation time across executions and check version behavior.

### 16.5. EXPLAIN EXECUTE

Use `EXPLAIN EXECUTE` to inspect a prepared statement's plan. Benchmark custom vs. generic plans against realistic workloads if parameter sensitivity is high.

### 16.6. Connection Pools

Session-level `SET` may not behave as expected when connections are reused. Use role/database settings or controlled `SET LOCAL`.

## 17. Observing JIT with EXPLAIN ANALYZE

`EXPLAIN` is the primary tool to see whether a query used JIT and how much compilation cost.

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    customer_id,
    sum(quantity * unit_price * (1 - discount_rate))
FROM app.order_items
WHERE created_at >= DATE '2025-01-01'
GROUP BY customer_id;
~~~

### 17.1. Plan Cost

Inspect estimated cost and actual time at each node. Compare estimated rows vs. actual rows to check planner accuracy.

### 17.2. JIT Section

When a query uses JIT, the output includes a `JIT` section showing function count, options, and timings.

### 17.3. Functions

The JIT `Functions` count shows how many compiled functions were generated for the query. It does not correspond to the number of SQL functions called by the application.

### 17.4. Options

The output reports whether `Inlining`, `Optimization`, `Expressions`, and `Deforming` were active for that run.

### 17.5. Timing

Timings break down into:
- Generation.
- Inlining.
- Optimization.
- Emission.

Sum these phases to see total compilation overhead.

### 17.6. Execution Time

Overall Execution Time includes execution and JIT overhead as measured by `EXPLAIN`. Do not look only at scan node actual time and ignore JIT timing.

### 17.7. EXPLAIN ANALYZE Executes the Query

`EXPLAIN ANALYZE` genuinely runs the statement. Use caution with DML or side-effecting queries. For DML testing, you can wrap in a transaction and `ROLLBACK`, though sequence advances and external side effects do not roll back.

### 17.8. BUFFERS

`BUFFERS` distinguishes buffer-heavy queries from CPU expression-heavy queries. Combine with OS metrics to understand physical I/O.

## 18. Comparing JIT On vs. Off

To know whether JIT helps a specific query, run the exact same query on the same data and conditions.

### 18.1. JIT On Run

~~~sql
SET jit = on;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sum(amount * tax_rate)
FROM app.sales
WHERE region_id = 10;
~~~

### 18.2. JIT Off Run

~~~sql
SET jit = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sum(amount * tax_rate)
FROM app.sales
WHERE region_id = 10;
~~~

### 18.3. Hold Other Factors Constant

Keep dataset, parameter values, cache conditions, concurrency, plan settings, and measurement window constant. If the plan changes due to another setting, isolate that effect.

### 18.4. Warm Cache vs. Cold Cache

Test warm-cache and cold-cache workloads reproducibly. Never compare one cold-cache run against one warm-cache run.

### 18.5. Repeat Multiple Times

Run enough repetitions and compare median, p95/p99, variance, CPU, and throughput. Any single run can be skewed by OS cache, checkpoints, background workers, or background load.

### 18.6. Do Not Measure Only a Single Query

Test multiple concurrent sessions. JIT can speed up a single query yet lower throughput if compile overhead saturates CPU.

### 18.7. Keep Plans Consistent When Needed

If isolating pure JIT impact, verify plan shapes match. If plans differ, document the difference clearly.

## 19. pg_stat_statements and JIT Statistics

`pg_stat_statements` aggregates statistics by query identity and exposes JIT fields on supported versions.

### 19.1. Checking the Extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Configure the extension per version docs, typically requiring `shared_preload_libraries` and a server restart.

### 19.2. JIT Fields

On supported versions, the view provides:
- `jit_functions`
- `jit_generation_time`
- `jit_inlining_count`
- `jit_inlining_time`
- `jit_optimization_count`
- `jit_optimization_time`
- `jit_emission_count`
- `jit_emission_time`

### 19.3. Querying Statistics

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    jit_functions,
    jit_generation_time,
    jit_inlining_count,
    jit_inlining_time,
    jit_optimization_count,
    jit_optimization_time,
    jit_emission_count,
    jit_emission_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

If a column is absent on your running version, inspect the view schema before running this query.

### 19.4. Generation Time per Call

You can compute average compilation time per call when `calls > 0`. This helps locate queries paying heavy JIT costs.

### 19.5. Cumulative Statistics

Fields in `pg_stat_statements` are cumulative since stats reset. Compute deltas across intervals and track reset events.

### 19.6. Query Identity

`queryid` groups similar statements via the extension's fingerprinting. Never use raw query text as a metric label.

### 19.7. Do Not Confuse Total JIT Time with Latency

`jit_generation_time` and related columns are cumulative compile totals. To assess per-call cost, divide by `calls` and examine latency distributions with other tools.

## 20. Classifying Queries by JIT Benefit

| Query type | Likelihood of benefit | Primary reason |
| --- | --- | --- |
| Primary-key point lookup | Low | Few rows, minimal expression work |
| Short OLTP transaction | Low | Compilation overhead easily dominates |
| Large sequential scan | Medium to high | Many tuples and repeated expressions |
| CPU-heavy aggregation | Medium to high | Heavy calculations across many rows |
| Large join with filters | Medium to high | Many expression evaluations |
| Sort-dominated query | Usually limited | Sort mechanics are not replaced |
| I/O-bound scan | Usually limited | Storage wait time dominates |
| Lock-bound query | Low | JIT does not reduce lock waits |
| Complex projection over many rows | Potentially high | Substantial expression work |
| Few rows with expensive function | Depends | Function body is not necessarily JIT-compiled |
| Parallel analytical query | Depends | May cut CPU yet increase compile contention |
| Repeated prepared statement | Depends | Plan reuse does not guarantee zero JIT generation |

### 20.1. Short Queries Do Not Always Skip JIT

If planner cost exceeds threshold for some reason, JIT can still trigger. Measure actual work and JIT timings.

### 20.2. Long Queries Do Not Always Benefit

A query running long because it waits on I/O or locks will not see meaningful gains from expression compilation.

### 20.3. Classify by Bottleneck

Classify queries as CPU-bound, I/O-bound, lock-bound, network-bound, or compile-bound before changing JIT settings.

## 21. OLTP and OLAP Examples

### 21.1. OLTP Lookup

~~~sql
SELECT status
FROM app.orders
WHERE order_id = $1;
~~~

Usually a very short query. When an index lookup returns one row, JIT cost can exceed CPU savings.

### 21.2. OLTP Update

~~~sql
UPDATE app.inventory
SET available = available - $1
WHERE product_id = $2;
~~~

A single-row update rarely needs JIT. Furthermore, the query may be bound by locks and WAL work.

### 21.3. OLAP Aggregate

~~~sql
SELECT
    date_trunc('month', created_at) AS month,
    region_id,
    sum(quantity * unit_price),
    avg(quantity * unit_price)
FROM app.sales
WHERE created_at >= DATE '2024-01-01'
GROUP BY 1, 2;
~~~

When scanning and computing across many rows, JIT can reduce CPU expression overhead.

### 21.4. Mixed Workload

A single database may run both OLTP and OLAP. Configuring JIT per role or workload class often works better than one global threshold.

### 21.5. Reporting Role

Enable JIT for the reporting role when benchmarks confirm benefit, while disabling it for latency-sensitive application roles.

### 21.6. Query Routing

If analytical workloads run on a reporting replica, measure JIT and resource contention separately on that replica. JIT does not eliminate node CPU limits.

## 22. Tuning JIT per Workload

Do not start by lowering every threshold. Measure first.

### 22.1. Baseline

Record query latency, CPU usage, throughput, JIT generation time, plan cost, and resource contention before making changes.

### 22.2. Disable JIT for Short Workloads

~~~sql
ALTER ROLE app_runtime SET jit = off;
~~~

Applies to new sessions of that role after reconnecting. Verify policy against connection pool behavior.

### 22.3. Keep JIT for Reporting

~~~sql
ALTER ROLE reporting SET jit = on;
~~~

Still requires sensible thresholds and benchmarking. `jit = on` does not force every query of the role to compile.

### 22.4. Adjust Thresholds

~~~sql
SET jit_above_cost = 50000;
~~~

This example illustrates setting a threshold; do not copy it as a universal cluster default.

### 22.5. Disable Inlining While Keeping Expression JIT

~~~sql
SET jit_inline_above_cost = -1;
~~~

Test when inlining time is high while execution gains are minimal.

### 22.6. Disable Deep Optimization

~~~sql
SET jit_optimize_above_cost = -1;
~~~

Evaluate when optimization time is high or queries have tight latency budgets.

### 22.7. Disable Tuple Deforming

~~~sql
SET jit_tuple_deforming = off;
~~~

Benchmark to check whether tuple deforming helps your actual workload.

### 22.8. Do Not Apply Globally Without Measuring

A change that helps reporting may regress OLTP. Test per role/session first before considering broader policies.

## 23. Configuration by Role, Database, and Session

PostgreSQL allows setting these GUCs at multiple scopes.

### 23.1. Session

~~~sql
SET jit = off;
~~~

Affects only the current connection.

### 23.2. Transaction

~~~sql
BEGIN;
SET LOCAL jit = off;
SELECT count(*) FROM app.orders;
COMMIT;
~~~

Useful when the application knows a transaction's query class.

### 23.3. Role

~~~sql
ALTER ROLE app_runtime SET jit = off;
ALTER ROLE analytics_runtime SET jit = on;
~~~

Role settings apply to new sessions of that role.

### 23.4. Database

~~~sql
ALTER DATABASE appdb SET jit = on;
~~~

Database settings become the default for new sessions to that database unless overridden at another scope.

### 23.5. Role in Database

~~~sql
ALTER ROLE reporting IN DATABASE appdb
SET jit_above_cost = 50000;
~~~

Can be tailored per role/database pair where appropriate.

### 23.6. Precedence

Session-level `SET` overrides role/database defaults. When investigating, use `SHOW` or `current_setting()` inside the exact connection running the query.

### 23.7. Connection Pools

If a pool holds connections long-term, changing role/database defaults will not affect already-open sessions. Recycle connections under a controlled procedure.

## 24. JIT, Statistics, and Plan Quality

JIT eligibility depends on planner cost, so statistics quality directly influences JIT decisions.

### 24.1. ANALYZE

Stale statistics distort estimated rows and total cost. Run `ANALYZE` appropriately after major data changes.

### 24.2. Extended Statistics

If predicates involve correlated columns, extended statistics can improve estimates for those query patterns.

### 24.3. Estimated vs. Actual Rows

In `EXPLAIN ANALYZE`, compare estimated vs. actual rows. Large gaps can cause inaccurate threshold decisions.

### 24.4. Cost Parameters

`seq_page_cost`, `random_page_cost`, `cpu_tuple_cost`, and `cpu_operator_cost` affect planner costs. Never tweak them just to force JIT on/off because they also alter plan selection.

### 24.5. JIT Does Not Fix Bad Plans

If a plan uses a nested loop over millions of unexpected rows, investigate statistics/indexes/join order. JIT may speed up expressions, yet cannot fix an unsuitable plan shape.

### 24.6. Parameterized Queries

Different parameter values can produce different custom plans or share a generic plan. Benchmark across multiple representative values.

## 25. JIT and Resource Contention

JIT consumes CPU and memory on top of regular executor overhead.

### 25.1. CPU Usage

Monitor process CPU, system CPU, and total CPU during benchmarks. If CPU is saturated, extra compilation can lengthen queues.

### 25.2. Memory

LLVM compilation consumes memory. Under many concurrent JIT queries, watch process memory and host memory pressure.

### 25.3. Concurrency

Measure concurrent JIT queries, active sessions, and p95/p99 latency. One faster query does not guarantee the overall system is faster.

### 25.4. Connection Pools

Pools can generate bursts of concurrent queries. Cap concurrency for reporting workloads if compile load impacts OLTP.

### 25.5. Parallel Workers

Parallel workers and the leader contend for CPU. Measure worker counts, JIT timings, and throughput under realistic load.

### 25.6. Container CPU Quotas

Container CPU limits can inflate compile time when throttled. Compare JIT runs under stable quotas and monitor throttling metrics.

### 25.7. NUMA and CPU Architecture

Native code runs on the host architecture. When migrating workloads between differing hosts, re-benchmark rather than assuming identical compile costs and performance.

## 26. Monitoring JIT

Monitoring JIT requires combining query-level statistics, `EXPLAIN`, and host resource metrics.

### 26.1. EXPLAIN ANALYZE

Use for specific queries to read function counts and compilation timings.

### 26.2. pg_stat_statements

Track total JIT functions plus generation, inlining, optimization, and emission times where provided by the view.

### 26.3. Compile Time per Call

A helpful derived metric:

\[
\text{JIT generation per call} =
\frac{\text{jit generation time}}
{\text{calls}}
\]

This is a cumulative average, not a substitute for latency distributions.

### 26.4. Compilation Share

Compare total JIT time against total execution time for the same query group. If compilation takes a large share, test higher thresholds or disabling deeper compile stages.

### 26.5. JIT Function Count

Rising function counts are not automatically bad. Compare them against compilation time and execution savings.

### 26.6. CPU and Throughput

Correlate host CPU, run queue, query throughput, p95 latency, and database wait events.

### 26.7. Counter Resets

`pg_stat_statements` counters can reset. Compute deltas across scrape windows and record reset timestamps to avoid artificial spikes or negative rates.

## 27. Example JIT Monitoring Queries

### 27.1. Check JIT Availability and Settings

~~~sql
SELECT
    pg_jit_available() AS jit_available,
    current_setting('jit') AS jit_enabled,
    current_setting('jit_provider') AS jit_provider,
    current_setting('jit_above_cost') AS jit_above_cost,
    current_setting('jit_inline_above_cost') AS jit_inline_above_cost,
    current_setting('jit_optimize_above_cost') AS jit_optimize_above_cost;
~~~

### 27.2. Check pg_stat_statements Columns

In `psql`:

~~~text
\d+ pg_stat_statements
~~~

Or query `information_schema`/catalogs to verify which JIT columns exist on your version.

### 27.3. Top Queries by JIT Generation Time

On versions with corresponding columns:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    jit_functions,
    jit_generation_time,
    jit_inlining_time,
    jit_optimization_time,
    jit_emission_time,
    left(query, 200) AS query_sample
FROM pg_stat_statements
ORDER BY jit_generation_time DESC
LIMIT 20;
~~~

### 27.4. Average Generation Time per Call

~~~sql
SELECT
    queryid,
    calls,
    jit_generation_time,
    jit_generation_time / NULLIF(calls, 0) AS generation_ms_per_call
FROM pg_stat_statements
WHERE calls > 0
ORDER BY generation_ms_per_call DESC
LIMIT 20;
~~~

### 27.5. Read Carefully

JIT fields may not exist on older versions. Run a schema check before deploying queries into exporters or custom dashboards.

### 27.6. Exporting Metrics

When using custom `postgres_exporter` queries, export aggregated JIT counters from `pg_stat_statements`. Use `queryid` or stable groupings as labels; never export raw SQL or parameter values.

## 28. Benchmarking JIT Properly

A sound benchmark measures both compilation time and the accelerated execution portion.

### 28.1. Choose Representative Queries

Select short OLTP queries, large scans, aggregates, joins, and CPU-heavy queries from real workloads.

### 28.2. Prepare Dataset

Use data volumes, distributions, indexes, and statistics close to production. Overly simplistic synthetic data can skew estimates and expression behavior.

### 28.3. Keep Plans Equivalent

Save `EXPLAIN` plans for JIT on and off. If plan shapes differ, analyze planner changes separately.

### 28.4. Warm-Up

Perform warm-up runs to minimize cold-cache and library-loading effects. Explicitly state whether runs are cold or warm.

### 28.5. Repeat

Run multiple iterations, save every sample, and compare median, p95/p99, and dispersion. Never cherry-pick the fastest run.

### 28.6. Measure CPU

Use OS monitoring/performance tools to track CPU utilization and CPU time. JIT may cut elapsed time or simply shift how CPU is used.

### 28.7. Measure Compile Stages

Read JIT timings in `EXPLAIN` and `pg_stat_statements`. Identify whether generation, inlining, or optimization dominates.

### 28.8. Concurrency Testing

Run at representative concurrency. Watch throughput and tail latency, not just average latency.

### 28.9. Separate Query Classes

Keep separate result tables for OLTP, reporting, ETL, and background jobs. Never lump all classes into a single average.

### 28.10. Roll Back Changes

Save prior settings and test at session/role scope. If results regress, restore the recorded policy.

## 29. Interpreting Benchmark Results

| Observation | Likely Interpretation | Investigation Direction |
| --- | --- | --- |
| High JIT time, short query | Compile overhead dominates | Raise threshold or disable JIT for workload |
| Low JIT time, clear execution drop | JIT is likely beneficial | Verify concurrency and throughput |
| CPU drops, elapsed time unchanged | Query may be I/O/wait-bound | Inspect buffers, waits, and storage |
| JIT on faster alone, slower concurrently | Compile contention | Measure CPU saturation and concurrency |
| High inlining time | Expensive inlining work | Try raising `jit_inline_above_cost` or disabling inlining |
| High optimization time | High LLVM optimization overhead | Try raising `jit_optimize_above_cost` |
| Query lacks JIT section | Below threshold or JIT unavailable | Check `pg_jit_available`, settings, and plan cost |
| Query uses JIT with few functions | Little code compiled | Evaluate real gain instead of checking JIT flag alone |

### 29.1. Compare Proportions

Calculate compilation time as a share of total latency to see whether JIT is worthwhile for that query class.

### 29.2. Compare Throughput

If single-query latency drops yet queries/second drop, the policy may be unsuitable for production.

### 29.3. Compare Tail Latency

p95/p99 usually matters more than mean in OLTP. Compilation spikes can hurt tail latency.

### 29.4. Do Not Optimize for One Query Alone

Optimize the database for the overall workload. One faster report should not slow down thousands of OLTP requests without clear justification.

## 30. Common Tuning Strategies

### 30.1. JIT Off for OLTP

Use `jit=off` for latency-sensitive roles or sessions when benchmarks show compile overhead outweighs gains.

### 30.2. JIT On for Reporting

Keep JIT for CPU-bound analytical queries processing many rows, paired with appropriate thresholds.

### 30.3. Raise jit_above_cost

Raising the threshold compiles fewer queries, useful when short queries are getting JIT-compiled unnecessarily.

### 30.4. Tune Inlining and Optimization Separately

If generation helps yet inlining/optimization costs too much, adjust their thresholds individually to see which stage adds value.

### 30.5. Keep Tuple Deforming When Beneficial

Queries scanning many tuples/wide rows can benefit from tuple deforming. Benchmark separately before disabling.

### 30.6. Separate Workload Classes

Use distinct roles/databases/service endpoints for OLTP and reporting so different JIT policies apply cleanly.

### 30.7. Combine with Query Tuning

Proper indexes, narrow projections, good predicates, accurate statistics, and early row filtering usually deliver far larger gains than tuning JIT alone.

## 31. Troubleshooting JIT

### Issue 1. pg_jit_available() Returns false

Check whether the PostgreSQL build includes LLVM support, provider libraries, and package/runtime compatibility.

### Issue 2. jit=on Yet No JIT Section Appears

Check whether plan cost exceeds `jit_above_cost`, provider availability, and whether the query has eligible expression work.

### Issue 3. Query Is Slower with JIT Enabled

Read generation/inlining/optimization/emission times, compare against JIT off, and check whether the query is too short or I/O-bound.

### Issue 4. Inlining Slows Compilation

Raise `jit_inline_above_cost` or test disabling inlining in a session benchmark.

### Issue 5. Optimization Time Is High

Raise `jit_optimize_above_cost` or disable deep optimization based on workload tests.

### Issue 6. CPU Rises After Enabling JIT

Check concurrent JIT queries, compilation time, connection pools, and CPU saturation.

### Issue 7. p95 Rises Even Though Mean Query Time Improves

Compilation bursts or contention can elevate tail latency. Check concurrency and latency distribution.

### Issue 8. JIT Threshold Does Not Take Effect as Expected

Verify the active setting inside the actual query connection via `SHOW`/`current_setting`, check role/database defaults, and check connection pool reuse.

### Issue 9. pg_stat_statements Lacks JIT Columns

Check PostgreSQL major version, extension version, and the view schema.

### Issue 10. Low-Cost Query Uses High CPU

Check estimates, statistics, actual rows, and expression complexity. Cost is not a CPU budget.

### Issue 11. High-Cost Query Does Not Get Faster

Check whether the bottleneck is I/O, locks, sorts, hash spills, network, or non-JIT-compiled function implementations.

### Issue 12. Container Experiences CPU Throttling

Inspect CPU quota/throttling and repeat benchmarks under stable quota conditions.

### Issue 13. JIT Availability Differs Across Nodes

Compare PostgreSQL builds, LLVM packages, and configurations on each host. Do not assume every replica runs identical binaries.

### Issue 14. Prepared Query Compiles Repeatedly

Measure JIT generation time against calls. Do not assume plan caching preserves native code; consider disabling JIT for ultra-high-frequency query classes.

### Issue 15. Dashboard Shows Zero JIT Time

Check whether the metrics collector exports JIT columns, whether JIT is actually running, and whether statistics were reset.

## 32. Decision Workflow for Enabling JIT

~~~text
Identify query class
        |
        v
Is JIT available?
    |           |
   No          Yes
    |           |
Check build      v
and provider  Is query CPU-bound?
                 |          |
                No         Yes
                 |          |
             JIT likely     v
             low value  Does cost exceed threshold?
                            |           |
                           No          Yes
                            |           |
                       No JIT yet       v
                                 Measure compilation time
                                          |
                                          v
                                  Compare JIT on/off
                                          |
                                          v
                                  Test concurrency
                                          |
                                +---------+---------+
                                |                   |
                           Benefit stable       No benefit/
                                |               regression
                                v                   |
                         Apply by workload        v
                              class          Raise threshold
                                             or disable JIT
~~~

### 32.1. Identify the Workload

Group query classes by latency target, frequency, row volume, and CPU profile.

### 32.2. Check Availability

Confirm build/provider support and effective configuration.

### 32.3. Read Plan Cost

Verify whether thresholds will trigger JIT.

### 32.4. Measure Compilation

Use `EXPLAIN` and `pg_stat_statements` to record JIT overhead.

### 32.5. Compare Execution

Benchmark JIT on vs. off on identical workloads and data conditions.

### 32.6. Test Concurrency

Measure throughput, CPU, memory, and tail latency.

### 32.7. Apply with Scope

Use appropriate role/session/database policies, monitor, and keep rollback ready.

## 33. Practice Exercises

Run exercises in a PostgreSQL lab with a representative dataset. `EXPLAIN ANALYZE` executes real queries, so avoid testing side-effecting DML on production.

### Exercise 1. JIT

What is JIT compilation in PostgreSQL?

### Exercise 2. LLVM

How does LLVM participate in the JIT process?

### Exercise 3. Scope

Does JIT compile an entire SQL query into a standalone executable?

### Exercise 4. Expressions

Name four types of expressions that can be JIT-compiled.

### Exercise 5. Tuple Deforming

What is tuple deforming and why can it be CPU-intensive?

### Exercise 6. Compilation Stages

Name the four primary JIT timing components.

### Exercise 7. Availability

Write SQL to check whether JIT is available.

### Exercise 8. Build

Why is `jit=on` not sufficient on its own to guarantee JIT works?

### Exercise 9. Cost Units

Does `jit_above_cost` use milliseconds as its unit?

### Exercise 10. Threshold

Which parameter controls the threshold to start JIT?

### Exercise 11. Inlining

Which parameter controls the inlining threshold?

### Exercise 12. Optimization

Which parameter controls the deep optimization threshold?

### Exercise 13. Disable

Give two ways to disable JIT for a query/session.

### Exercise 14. OLTP

Why do point lookups usually gain little from JIT?

### Exercise 15. OLAP

Why can large analytical scans benefit?

### Exercise 16. I/O Bound

Why does JIT help little when a query is waiting on disk?

### Exercise 17. Join

Does JIT replace the hash join algorithm?

### Exercise 18. Sort

Does JIT eliminate sorting cost?

### Exercise 19. Function

Does JIT compile an entire PL/pgSQL function body into native code?

### Exercise 20. Prepared Statement

Does plan caching guarantee native JIT code is kept across all executions?

### Exercise 21. EXPLAIN

Write an `EXPLAIN` command to measure a query and its buffers.

### Exercise 22. JIT Section

List what information can appear in the `JIT` section of `EXPLAIN`.

### Exercise 23. pg_stat_statements

Name four JIT-related fields that may exist in `pg_stat_statements`.

### Exercise 24. Calls

Why compare `jit_generation_time` against `calls`?

### Exercise 25. Counter Reset

Why record statistics resets when comparing JIT metrics?

### Exercise 26. Threshold Too Low

What can happen if `jit_above_cost` is set too low?

### Exercise 27. Inlining Cost

When inlining time is large, which parameter can you try adjusting?

### Exercise 28. Optimization Cost

When optimization time is large, which parameter can you try adjusting?

### Exercise 29. Benchmark

Name five factors that must be held constant when comparing JIT on vs. off.

### Exercise 30. Concurrency

Why must you benchmark multiple concurrent sessions?

### Exercise 31. Role Policy

Write SQL to disable JIT by default for role `app_runtime`.

### Exercise 32. Reporting Policy

Write SQL to enable JIT by default for role `reporting`.

### Exercise 33. Session Scope

What is the difference between `SET jit=off` and `SET LOCAL jit=off`?

### Exercise 34. Plan Estimates

Why can inaccurate statistics lead to poor JIT decisions?

### Exercise 35. Query Classification

Classify point lookups, large aggregations, lock-bound queries, and I/O-bound scans by likelihood of benefiting from JIT.

### Exercise 36. Metrics

List the metrics to monitor when tuning JIT.

### Exercise 37. Container

How can CPU throttling affect JIT benchmark results?

### Exercise 38. Regression

A single query is faster yet cluster-wide throughput drops; what should you investigate?

### Exercise 39. Troubleshooting

List the first steps when a query lacks a `JIT` section even though `jit=on`.

### Exercise 40. Design

Propose a JIT policy for a database running both OLTP and reporting workloads.

## 34. Reference Solutions

### Exercises 1–8. Mechanics and Availability

JIT compiles certain expressions into native code at runtime. LLVM provides the IR optimizer and code generation. JIT does not compile an entire SQL query into a standalone executable; PostgreSQL still runs the execution plan. Expressions include arithmetic, comparisons, Boolean predicates, and projections/`CASE`. Tuple deforming extracts column values from tuple representations. Main timings are generation, inlining, optimization, and emission. Check availability with:

~~~sql
SELECT pg_jit_available();
~~~

`jit=on` is insufficient if the PostgreSQL build lacks LLVM support or the provider fails to load.

### Exercises 9–13. Thresholds and Configuration

`jit_above_cost` uses planner cost units, not milliseconds. `jit_above_cost` controls starting JIT; `jit_inline_above_cost` controls inlining; `jit_optimize_above_cost` controls deep optimization. Disable JIT with `SET jit=off` or `SET LOCAL jit=off` inside a transaction.

### Exercises 14–20. Query Classes

Point lookups process few rows, so compilation overhead exceeds CPU savings. Large analytical scans/aggregations evaluate many expressions across many rows and amortize compilation. I/O-bound queries mainly wait on storage, so JIT helps little. JIT can compile expressions around joins but does not replace hash join algorithms or entire sorts. JIT does not compile full PL/pgSQL bodies into native code. Prepared plan caches do not guarantee native JIT code is reused across all executions.

### Exercises 21–25. Measurement

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sum(amount) FROM app.sales;
~~~

The JIT section displays function count, options, and generation/inlining/optimization/emission timings. `pg_stat_statements` can provide `jit_functions`, `jit_generation_time`, `jit_inlining_time`, and `jit_optimization_time`. Dividing compilation time by calls estimates average compile cost per execution. Stats resets shift counter baselines, so reset timestamps must be recorded.

### Exercises 26–30. Benchmarking and Tuning

Setting the threshold too low compiles many short queries, raising CPU/latency. If inlining time is high, try raising `jit_inline_above_cost` or disabling inlining; if optimization time is high, try raising `jit_optimize_above_cost`. Hold data, parameter values, plan, cache state, concurrency, and resource limits constant. Concurrent benchmarks uncover compilation contention and tail latency hidden by single-query tests.

### Exercises 31–35. Policy and Plan Quality

~~~sql
ALTER ROLE app_runtime SET jit = off;
ALTER ROLE reporting SET jit = on;
~~~

`SET` applies to the current session; `SET LOCAL` lasts only until the end of the transaction. Inaccurate statistics distort planner cost/row estimates and can mis-trigger or skip JIT. Point lookups and lock-bound queries usually gain little; large CPU-heavy aggregations can benefit; I/O-bound scans are typically bottlenecked by storage.

### Exercises 36–40. Monitoring and Design

Monitor JIT generation/inlining/optimization/emission times, calls, total/mean execution time, CPU, memory, throughput, p95/p99, and query plans. CPU throttling inflates compile time and destabilizes benchmarks. If a single query speeds up yet throughput drops, inspect CPU saturation, concurrent compilations, worker counts, and connection pools.

When no JIT section appears despite `jit=on`, check `pg_jit_available()`, the provider, plan cost vs. threshold, effective session settings, and expression eligibility.

For mixed workloads, disable JIT for latency-sensitive `app_runtime` and enable it for the `reporting` role, then tune thresholds from benchmarks. Maintain dashboards/alerts for compilation overhead and a rollback policy if tail latency or throughput degrades.

## 35. Quick Reference Table

| Need | Tool / Parameter |
| --- | --- |
| Check JIT availability | `pg_jit_available()` |
| Enable/disable JIT | `jit` |
| Check provider | `jit_provider` |
| JIT activation threshold | `jit_above_cost` |
| Inlining threshold | `jit_inline_above_cost` |
| Deep optimization threshold | `jit_optimize_above_cost` |
| Compile expressions | `jit_expressions` |
| Compile tuple deforming | `jit_tuple_deforming` |
| Measure plan and execution | `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` |
| Query-level JIT stats | `pg_stat_statements` |
| Compile generation time | `jit_generation_time` |
| Inlining time | `jit_inlining_time` |
| Optimization time | `jit_optimization_time` |
| Emission time | `jit_emission_time` |
| Disable in session | `SET jit = off` |
| Disable in transaction | `SET LOCAL jit = off` |
| Policy per role | `ALTER ROLE ... SET` |
| Policy per database | `ALTER DATABASE ... SET` |
| Check effective settings | `SHOW` / `current_setting()` |
| Inspect cached plan execution | `EXPLAIN EXECUTE` |
| Check PostgreSQL build | `pg_config --configure` |
| Inspect query workload | `pg_stat_statements` |

## 36. JIT Tuning Checklist

1. Confirm PostgreSQL version and LLVM/JIT build support.
2. Check `pg_jit_available()` on the actual instance.
3. Record current `jit`, `jit_provider`, and threshold settings.
4. Classify queries into OLTP, reporting, ETL, and background workloads.
5. Pick representative queries for each class.
6. Read `EXPLAIN` plan cost and estimated/actual rows.
7. Identify whether queries are CPU-bound or I/O/lock/network-bound.
8. Measure JIT generation, inlining, optimization, and emission times.
9. Measure total execution time, CPU, and buffers.
10. Benchmark JIT on/off with identical data and parameters.
11. Repeat sufficiently and compare median and p95/p99.
12. Benchmark at production-like concurrency.
13. Check whole-system throughput and CPU saturation.
14. Raise `jit_above_cost` if short queries are compiled too often.
15. Tune `jit_inline_above_cost` if inlining overhead is high.
16. Tune `jit_optimize_above_cost` if optimization overhead is high.
17. Benchmark `jit_expressions` and `jit_tuple_deforming` separately when needed.
18. Use role/session policies to isolate workload classes.
19. Check whether connection pools retain old session settings.
20. Monitor `pg_stat_statements` JIT fields if supported by your version.
21. Track statistics resets and exporter metric gaps.
22. Never alter planner cost parameters just to force JIT.
23. Never treat JIT as a fix for bad plans or missing indexes.
24. Check container CPU quotas and host memory pressure.
25. Record baseline, new settings, and rollback procedure.
26. Monitor after rollout and adjust to real workloads.

## 37. Summary

JIT in PostgreSQL uses LLVM to compile parts of expression evaluation and tuple deformation into native code at runtime. This can reduce CPU for queries processing many tuples and heavy computations, while adding generation, inlining, optimization, and code emission overhead.

`jit_above_cost`, `jit_inline_above_cost`, and `jit_optimize_above_cost` operate in planner cost units, not milliseconds or query timeouts. Therefore, a high-cost query is not guaranteed to run long, and a query with high real CPU cost is not guaranteed to be estimated accurately by the planner. Statistics, plan quality, and query shape all drive JIT decisions.

OLTP point lookups and short transactions rarely benefit because compilation overhead easily dominates. CPU-bound large scans, joins, and aggregations can benefit when expression work repeats across many rows. Queries limited by disk, locks, network, sort spills, or non-JIT-compiled function implementations may see little improvement.

Use `pg_jit_available()`, `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)`, and `pg_stat_statements` to measure both compilation time and execution time. Benchmark JIT on/off on representative data and concurrency; compare median, tail latency, throughput, and CPU. For mixed workloads, role/session scoping can protect OLTP latency while letting reporting leverage JIT. Apply broad changes only with data, monitoring, and a clear rollback plan.

# Native Compilation, PL/SQL Tuning, and Measuring Before Changing

Effective PL/SQL tuning starts with measurement. A slow procedure may spend its time in PL/SQL loops, in SQL statements inside the procedure, waiting on I/O, contending on locks, or transferring data between the PL/SQL engine and the SQL engine. Native compilation affects only the PL/SQL execution portion; it does not automatically speed up embedded SQL statements and does not eliminate database wait time.

Therefore, the proper workflow is:

1. Measure execution time and resource usage of the current workload.
2. Identify whether the slowdown lies in PL/SQL or in SQL/database waits.
3. Choose the technique suited to the measured bottleneck.
4. Change one factor per experiment.
5. Re-measure on equivalent data and load.
6. Deploy only when results are correct, stable, and demonstrably beneficial.

This lesson covers native compilation, compiler parameters, profiling, SQL tracing, bulk processing, reducing context switches, and designing repeatable performance experiments. Examples use Oracle Database 19c syntax as a reference baseline; execution privileges and certain tool details vary by version and configuration.

## 1. First: Where Is PL/SQL Slow?

PL/SQL is a procedural language running inside Oracle Database. A PL/SQL program usually coordinates two engines:

- The PL/SQL engine handles variables, conditionals, loops, procedure/function calls, and procedural logic.
- The SQL engine parses, optimizes, and executes SELECT, INSERT, UPDATE, DELETE, and MERGE statements.

Example:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = rec.salary * 1.05
        WHERE employee_id = rec.employee_id;
    END LOOP;
END;
/
~~~

The block's elapsed time can include:

1. Executing the SELECT query to retrieve rows.
2. Transferring each row from the SQL engine to the PL/SQL engine.
3. Running PL/SQL logic on each loop iteration.
4. Invoking the SQL engine for each individual UPDATE.
5. Reading/writing blocks, generating undo/redo, and waiting on locks or I/O.

If most time is spent in UPDATE or waiting on I/O, native compilation does not address the root cause. If most time is spent in pure CPU-bound PL/SQL computation, native compilation or algorithmic optimization can help.

### 1.1 Three Bottleneck Categories

| Category | Symptoms | Investigation Path |
|---|---|---|
| PL/SQL CPU | Loops, string/numeric manipulation, CPU-intensive algorithms | DBMS_HPROF, DBMS_PROFILER, algorithm tuning, native compilation |
| SQL execution | SQL with high logical reads, physical reads, large joins/sorts | Actual execution plan, SQL trace, DBMS_XPLAN, statistics |
| Wait/concurrency | Waiting on I/O, locks, latches, network, or other resources | Session waits, SQL trace, ASH/AWR if licensed, concurrency review |

A single procedure can exhibit multiple bottleneck types simultaneously. Measure each component's contribution before selecting a solution.

### 1.2 Total Elapsed Time Is Insufficient to Find the Cause

If a procedure takes 20 seconds, that number alone does not tell you:

- Did PL/SQL spend 18 seconds of CPU or only 0.2 seconds?
- Did SQL consume 15 seconds due to a full table scan or lock waits?
- Did the procedure invoke a function 100,000 times?
- Did one single SQL statement consume nearly all the time?
- Did time increase due to repeated parsing or execution?

Combine end-to-end timing with profilers and SQL statistics.

## 2. Measurement Workflow Before Optimizing

A meaningful measurement requires a clear, repeatable baseline.

### 2.1 Define the Workload

Document:

- Procedure/package and actual call paths.
- Representative inputs: row counts, collection sizes, string lengths, business variants.
- Execution count.
- Execution frequency and concurrency level.
- Data state and optimizer statistics.
- Expected outputs to preserve.
- Transaction boundaries and commit behavior.

Do not benchmark solely on a tiny input if production routinely processes hundreds of thousands of rows. Equally, do not test only extreme peak inputs if most workloads are small.

### 2.2 Measure the Baseline Multiple Times

Run multiple iterations under equivalent conditions:

- Perform a warm-up run if caching or object loading affects startup.
- Run enough iterations to observe variance.
- Record the median and high percentiles such as p95 when running multiple trials.
- Keep bind patterns, data, session settings, and concurrency consistent.
- Exclude setup/test-data generation time from the measured region.
- Do not change multiple parameters between two test runs.

Never draw conclusions from a single run being a few milliseconds faster. Differences can stem from cache state, background activity, or system load.

### 2.3 Choose Metrics

At minimum, record:

| Metric | Question Answered |
|---|---|
| Elapsed time | How long must the caller wait? |
| CPU time | How much CPU did the database consume? |
| Logical reads/buffer gets | How many blocks in the buffer cache were accessed? |
| Physical reads | How many reads came from storage? |
| Rows processed | How many rows did the workload actually process? |
| Executions | How many times was the SQL/procedure invoked? |
| Parse calls | Is repeated parsing occurring? |
| Wait events | Where was time spent waiting? |
| Memory/collection size | Is there memory growth risk during bulk operations? |

Elapsed time reflects the caller's experience. CPU time and wait time explain why elapsed time changed.

### 2.4 Preserve Equivalent Business Results

After tuning, verify:

- Input/output row counts match.
- Numeric values, rounding rules, and processing order are accurate.
- Exceptions and error codes still honor the contract.
- Transaction/commit/rollback behavior did not change unintentionally.
- Side effects such as audits or messages are neither lost nor duplicated.

A faster version that drops rows or alters exception behavior is not a valid optimization.

## 3. Simple Timing in PL/SQL

### 3.1 Using SYSTIMESTAMP

`SYSTIMESTAMP` returns `TIMESTAMP WITH TIME ZONE`. You can capture start/end timestamps and subtract them to get an `INTERVAL`:

~~~sql
DECLARE
    l_start   TIMESTAMP WITH TIME ZONE;
    l_finish  TIMESTAMP WITH TIME ZONE;
    l_elapsed INTERVAL DAY TO SECOND;
BEGIN
    l_start := SYSTIMESTAMP;

    -- Place the workload to measure here.
    order_api.recalculate_order(p_order_id => 1001);

    l_finish := SYSTIMESTAMP;
    l_elapsed := l_finish - l_start;

    DBMS_OUTPUT.PUT_LINE(
        'Elapsed: ' || TO_CHAR(l_elapsed)
    );
END;
/
~~~

This measures wall-clock time from the session's perspective, not CPU time alone. It includes time spent waiting on SQL, I/O, locks, and other activity inside the measured block.

### 3.2 Using DBMS_UTILITY.GET_TIME

`DBMS_UTILITY.GET_TIME` returns centiseconds from an internal epoch:

~~~sql
DECLARE
    l_start_cs PLS_INTEGER;
    l_end_cs   PLS_INTEGER;
BEGIN
    l_start_cs := DBMS_UTILITY.GET_TIME;

    order_api.recalculate_order(p_order_id => 1001);

    l_end_cs := DBMS_UTILITY.GET_TIME;

    DBMS_OUTPUT.PUT_LINE(
        'Elapsed seconds: ' ||
        (l_end_cs - l_start_cs) / 100
    );
END;
/
~~~

`GET_TIME` is convenient for basic timing in PL/SQL. Centisecond resolution is unsuitable for comparing very short snippets; run many iterations or measure a sufficiently large batch.

### 3.3 Do Not Measure with DBMS_OUTPUT Inside Loops

`DBMS_OUTPUT` and logging operations alter execution time. Never print per-row output inside a benchmark region unless production does the same.

Instead of:

~~~sql
FOR i IN 1 .. 100000 LOOP
    DBMS_OUTPUT.PUT_LINE(i);
    l_total := l_total + i;
END LOOP;
~~~

limit output:

~~~sql
FOR i IN 1 .. 100000 LOOP
    l_total := l_total + i;
END LOOP;

DBMS_OUTPUT.PUT_LINE('Total=' || l_total);
~~~

Measure the exact workload the real application performs.

## 4. PL/SQL Profilers: Measuring Subprograms and Source Lines

Profilers pinpoint which code sections consume time rather than guessing from source length.

### 4.1 DBMS_PROFILER

`DBMS_PROFILER` collects data by PL/SQL unit and source line. It helps determine:

- Which procedures/functions consume time.
- Which lines execute most frequently.
- Which lines incur high execution time.
- Whether the actual execution path differs from expectations.

Profiler tables must be installed and granted per Oracle instructions in the target environment. Common table names are `PLSQL_PROFILER_RUNS`, `PLSQL_PROFILER_UNITS`, and `PLSQL_PROFILER_DATA`.

Example execution skeleton:

~~~sql
BEGIN
    DBMS_PROFILER.START_PROFILER(
        run_comment => 'Baseline order calculation'
    );

    order_api.recalculate_order(p_order_id => 1001);

    DBMS_PROFILER.STOP_PROFILER;
END;
/
~~~

If the workload raises an exception, ensure the profiler stops in the exception branch:

~~~sql
BEGIN
    DBMS_PROFILER.START_PROFILER(
        run_comment => 'Order calculation test'
    );

    BEGIN
        order_api.recalculate_order(p_order_id => 1001);
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_PROFILER.STOP_PROFILER;
            RAISE;
    END;

    DBMS_PROFILER.STOP_PROFILER;
END;
/
~~~

This snippet illustrates profiler management in tests. In a real harness, avoid calling `STOP_PROFILER` twice and handle `START_PROFILER` failures separately.

### 4.2 Reading Profiler Data

Once profiling finishes, data resides in the installed profiler tables. Join run, unit, and line data to locate lines with high execution counts and high total time.

Example query skeleton:

~~~sql
SELECT u.unit_name,
       d.line#,
       d.total_occur,
       d.total_time
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
WHERE d.runid = :run_id
ORDER BY d.total_time DESC;
~~~

Column names and time units depend on profiler installation and Oracle version. Inspect table metadata in your schema before running reporting queries; do not treat skeleton queries as universal deployment scripts across all versions.

### 4.3 DBMS_HPROF: Hierarchical Profiler

`DBMS_HPROF` collects timing along the hierarchical call tree. It helps identify whether time is spent in:

- Directly invoked subprograms.
- Child subprograms.
- SQL executed within the call flow.
- A branch called repeatedly from multiple callers.

High-level differences:

| Tool | Primary Focus |
|---|---|
| DBMS_PROFILER | Source lines and PL/SQL units |
| DBMS_HPROF | Call tree and timing per subprogram |
| SQL Trace/TKPROF | Parse, execute, fetch, waits, and SQL statistics |

To use `DBMS_HPROF`, a DBA must configure a directory object with appropriate read/write privileges. Skeleton example:

~~~sql
BEGIN
    DBMS_HPROF.START_PROFILING(
        location => 'PLSQL_PROF_DIR',
        filename => 'order_profile.trc'
    );

    order_api.recalculate_order(p_order_id => 1001);

    DBMS_HPROF.STOP_PROFILING;
END;
/
~~~

`PLSQL_PROF_DIR` is a database server directory object, not a client directory. The profile trace file is written on the server path mapped to that object. Analyzing traces and saving reports requires supporting packages/tables installed for your Oracle version.

### 4.4 Profilers Add Overhead

Profilers perform extra work to record metrics. Therefore:

- Use profilers to find relative hotspots.
- Never treat elapsed time from a profiled run as the final benchmark.
- After identifying bottlenecks, re-run end-to-end measurements with profiling disabled.
- Use identical workloads before and after for comparison.

## 5. Measuring SQL Inside PL/SQL

If a procedure is slow because of SQL, investigate the specific SQL statements.

### 5.1 Tagging Module and Action

`DBMS_APPLICATION_INFO` sets `MODULE` and `ACTION` on the session:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_API',
        action_name => 'RECALCULATE'
    );

    order_api.recalculate_order(p_order_id => 1001);

    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => NULL,
        action_name => NULL
    );
END;
/
~~~

`MODULE`/`ACTION` helps DBAs identify workloads in monitoring views and traces. If the application uses connection pooling, reset module/action across requests so activity is not misattributed to a previous request.

Use `SET_ACTION` to update the action across phases:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_ACTION('VALIDATE');
    -- Validate input.

    DBMS_APPLICATION_INFO.SET_ACTION('UPDATE_ORDER');
    -- Execute DML.

    DBMS_APPLICATION_INFO.SET_ACTION('WRITE_AUDIT');
    -- Write audit.
END;
/
~~~

### 5.2 Inspecting Actual Execution Plans

To inspect actual row counts and buffers in SQL, use `GATHER_PLAN_STATISTICS` in test environments:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id,
       salary
FROM employees
WHERE department_id = 10;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

In the plan, compare E-Rows vs. A-Rows, Starts, Buffers, Reads, and Predicate Information. If SQL inside a procedure uses bind variables, check the plan of the actual child cursor executed for those bind values.

### 5.3 SQL Trace and TKPROF

SQL Trace captures parse, execute, fetch, and wait details for a chosen session or workload. TKPROF formats the raw trace into a readable report.

Example enabling/disabling trace for the current session:

~~~sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        waits => TRUE,
        binds => FALSE
    );
END;
/

BEGIN
    order_api.recalculate_order(p_order_id => 1001);
END;
/

BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

Trace files are written on the database server. A DBA or authorized user runs TKPROF to analyze them. Bind tracing is disabled in the example to avoid logging input values; enable bind tracing only when necessary and after reviewing privacy/security requirements.

### 5.4 Do Not Confuse SQL Time with PL/SQL Time

A procedure may invoke a single SQL statement 10,000 times. SQL Trace reveals the high execution count and total elapsed/CPU time of that statement. `DBMS_HPROF` can pinpoint the subprogram containing the loop. Combining both identifies whether the cause is:

- Looping too many times in PL/SQL.
- Invoking SQL row by row.
- An expensive plan on each SQL execution.
- A PL/SQL function invoked repeatedly from SQL.

## 6. What Is Native Compilation?

PL/SQL can be compiled in two primary forms:

- INTERPRETED: PL/SQL compiles to intermediate bytecode executed by the PL/SQL engine.
- NATIVE: PL/SQL compiles to platform-native machine code for more direct execution.

The controlling compiler parameter is `PLSQL_CODE_TYPE`:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
~~~

or:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = NATIVE;
~~~

Native compilation aims to reduce execution overhead in the PL/SQL portion. It is best suited for CPU-bound programs heavy on calculations, loops, or in-memory data manipulation.

### 6.1 Native Compilation Does Not Compile SQL into PL/SQL Native Code

Inside a procedure:

~~~sql
BEGIN
    l_total := calculate_tax(l_amount);

    UPDATE orders
    SET tax_amount = l_total
    WHERE order_id = p_order_id;
END;
~~~

Native compilation can accelerate the PL/SQL portions such as function calls, arithmetic, and control flow. The `UPDATE` statement is still parsed, optimized, and executed by Oracle's SQL engine.

If `UPDATE` accounts for 95% of total runtime, native compilation is not the primary solution.

### 6.2 When Can Native Compilation Help?

Workloads likely to benefit:

- Arithmetic computation in PL/SQL with large iteration counts.
- String or in-memory data processing without constant SQL calls.
- Purely CPU-bound PL/SQL algorithms.
- Subprograms called heavily where PL/SQL execution overhead is significant.

Workloads typically seeing little benefit:

- Disk I/O waits.
- SQL with poor execution plans.
- Row lock waits or contention.
- Remote service calls.
- Heavy data transfers between client and database.
- Procedures mainly running a single already-fast set-based SQL statement.

### 6.3 Native Compilation Does Not Make Every Procedure Faster Automatically

Benefits depend on:

- Share of CPU time spent inside PL/SQL.
- Call frequency and workload size.
- Algorithms and datatypes used.
- Oracle version, architecture, and configuration.
- Compiler settings.
- Compilation and deployment overhead.

Always benchmark interpreted vs. native on the same workload. Never enable native system-wide solely because the name sounds faster.

## 7. Configuring PLSQL_CODE_TYPE

### 7.1 Checking Current Object Settings

The `USER_PLSQL_OBJECT_SETTINGS` view shows compiler settings for PL/SQL objects in the schema:

~~~sql
SELECT name,
       type,
       plsql_code_type,
       plsql_optimize_level,
       plsql_warnings
FROM user_plsql_object_settings
ORDER BY name, type;
~~~

Filter for a specific object:

~~~sql
SELECT name,
       type,
       plsql_code_type,
       plsql_optimize_level
FROM user_plsql_object_settings
WHERE name = UPPER('ORDER_API');
~~~

Object names are stored in uppercase unless created with quoted identifiers.

### 7.2 Changing Session Settings and Recompiling Objects

Example testing native compilation on a procedure in a test schema:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = NATIVE;

ALTER PROCEDURE recalculate_order COMPILE;
~~~

For a package, compile the appropriate part:

~~~sql
ALTER PACKAGE order_api COMPILE BODY;
~~~

Then re-query `USER_PLSQL_OBJECT_SETTINGS` to confirm the compiled object's code type. Changing `ALTER SESSION` does not retroactively convert previously compiled objects to native; objects must be recompiled under the desired setting.

### 7.3 System-Level Settings

A DBA can set `PLSQL_CODE_TYPE` at the system level to govern future compilations:

~~~sql
ALTER SYSTEM SET PLSQL_CODE_TYPE = NATIVE SCOPE = BOTH;
~~~

This is a database configuration change requiring administrative privileges and a deployment plan. It does not immediately recompile all existing PL/SQL objects automatically.

For experiments, prefer session-level settings in a test schema to avoid affecting compilation of other workloads.

### 7.4 Versions and Native Code Deployment

Details of native code generation and storage have evolved across Oracle releases. DBAs must follow version- and platform-specific documentation, verify compiler/runtime configuration, and check backup/upgrade procedures. Never apply directory or C-compiler instructions from older releases to newer databases without confirmation.

## 8. PLSQL_OPTIMIZE_LEVEL

`PLSQL_OPTIMIZE_LEVEL` controls PL/SQL compiler optimization intensity.

Common levels:

| Level | General Meaning |
|---:|---|
| 0 | Minimal/no standard compiler optimizations |
| 1 | Basic, conservative optimizations |
| 2 | Standard optimization level and common default |
| 3 | Higher optimization level; compiler may apply further transformations |

Check setting:

~~~sql
SHOW PARAMETER PLSQL_OPTIMIZE_LEVEL
~~~

In PL/SQL:

~~~sql
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
~~~

### 8.1 Level 2 Is the Usual Starting Point

Level 2 is the standard default for production code. The compiler performs standard optimizations such as eliminating dead work and transforming code safely.

Do not drop to level 0 just for debugging and forget to recompile for production. Do not raise to level 3 just because the number is higher; measure and regression-test.

### 8.2 Level 3 Requires Testing

Level 3 lets the compiler apply more aggressive optimizations. This can speed up certain workloads while altering how internal operations are ordered or inlined.

Test:

- Business results.
- Exceptions and observable error locations.
- Code relying on side effects or expression evaluation order.
- Performance across varying input sizes.

Never rely on an expression evaluation order not guaranteed by the language.

### 8.3 Compiler Settings Take Effect at Compile Time

`PLSQL_OPTIMIZE_LEVEL` is a compiler setting. Changing the session setting does not alter already-compiled objects. Recompile objects under the new setting and verify post-compile metadata.

## 9. PLSQL_WARNINGS and Code Quality

Compiler warnings catch potential issues before runtime, such as unused variables, unreachable code, or suspicious constructs.

Enable warnings:

~~~sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
~~~

Recompile:

~~~sql
ALTER PROCEDURE recalculate_order COMPILE;
~~~

Inspect errors/warnings:

~~~sql
SELECT name,
       type,
       line,
       position,
       attribute,
       message_number,
       text
FROM user_errors
WHERE name = UPPER('RECALCULATE_ORDER')
ORDER BY sequence;
~~~

In SQL*Plus or SQLcl, you can also run:

~~~sql
SHOW ERRORS PROCEDURE recalculate_order
~~~

Warnings do not replace unit tests, profilers, or code reviews. They serve as an additional feedback layer from the compiler.

### 9.1 Configuring Warnings by Policy

You can enable/disable specific warnings by warning number. Example:

~~~sql
ALTER SESSION SET PLSQL_WARNINGS =
    'ENABLE:ALL', 'DISABLE:06002';
~~~

Do not suppress warnings just to get a clean build without understanding the cause. Document the warning policy in build pipelines so all environments compile consistently.

## 10. PRAGMA INLINE and Subprogram Call Optimization

When a small subprogram is called many times, call overhead can become noticeable. The compiler can inline certain calls; `PRAGMA INLINE` lets you request that the compiler attempt inlining at a call site.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_batch AS
    FUNCTION add_tax(p_amount NUMBER)
        RETURN NUMBER
    IS
    BEGIN
        RETURN p_amount * 1.08;
    END;

    l_total NUMBER := 0;
BEGIN
    FOR i IN 1 .. 100000 LOOP
        PRAGMA INLINE(add_tax, 'YES');
        l_total := l_total + add_tax(i);
    END LOOP;
END;
/
~~~

`PRAGMA INLINE` is an optimization request; the compiler may decline to inline if impossible or unsuitable. Verify results on your target release and benchmark performance. Inlining can also increase code size or alter debugging behavior.

Do not force inlining on every function by default. Large or infrequently called functions rarely warrant forced inlining.

## 11. PRAGMA UDF for Functions Called from SQL

When SQL invokes a PL/SQL function for many rows, there is switching overhead between the SQL engine and PL/SQL engine. `PRAGMA UDF` hints that the function is primarily invoked from SQL and can reduce this overhead in supported releases.

Example:

~~~sql
CREATE OR REPLACE FUNCTION calculate_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    IF p_region_code = 'VN' THEN
        RETURN 0.10;
    ELSE
        RETURN 0.08;
    END IF;
END;
/
~~~

Query:

~~~sql
SELECT order_id,
       amount,
       amount * calculate_tax_rate(region_code) AS tax_amount
FROM orders;
~~~

`PRAGMA UDF` does not turn a function into a SQL macro, does not convert it into a pure SQL expression, and does not eliminate all PL/SQL call cost. If logic can be expressed directly in SQL, compare against pure SQL first.

Use it only when the function is actually invoked from SQL and profilers/benchmarks show meaningful overhead.

## 12. RESULT_CACHE and DETERMINISTIC

An expensive function returning identical results for identical inputs can be a caching candidate if data dependencies and semantics allow.

### 12.1 RESULT_CACHE

Function result caching stores function outputs and reuses them when matching inputs are called again. Oracle manages invalidation based on supported data dependencies.

Skeleton example:

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER
RESULT_CACHE
IS
BEGIN
    -- Query tax configuration table or compute appropriate value.
    RETURN 0.10;
END;
/
~~~

This example merely illustrates placement of the `RESULT_CACHE` clause. A real function must have cache-safe semantics, without unmanaged session state or side effects.

### 12.2 DETERMINISTIC Is Not a Cache

`DETERMINISTIC` declares that a function returns the same output for identical inputs. Oracle can leverage this assertion in certain optimizations, yet the keyword itself creates no shared result cache.

Never declare `DETERMINISTIC` if the function reads mutable data or depends on `SYSDATE`, package globals, session context, or state outside inputs without guaranteeing identical results.

### 12.3 When Is Caching Inappropriate?

- Inputs are almost always unique.
- Underlying data changes constantly.
- Function depends on NLS/session context.
- Function has side effects.
- Cache lookup overhead exceeds recomputation cost.
- Calculations require a specific business snapshot.

Measure hit rates and verify correctness before deploying caching to production.

## 13. Optimize SQL Before Optimizing PL/SQL Loops

A foundational rule is shifting work to set-based SQL whenever appropriate.

### 13.1 Row-by-Row Processing

Example processing each employee individually:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = rec.salary * 1.05
        WHERE employee_id = rec.employee_id;
    END LOOP;
END;
/
~~~

Each iteration executes an `UPDATE`. For 50,000 rows, the SQL engine receives 50,000 separate DML calls.

### 13.2 Use a Single Set-Based UPDATE

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

The SQL engine processes the entire row set in one statement. This is usually simpler and far more efficient when the logic applies across the whole set.

### 13.3 Use MERGE for Upserts

If you need to update existing rows and insert missing rows, consider `MERGE` instead of a loop running `SELECT` then `INSERT`/`UPDATE` per row:

~~~sql
MERGE INTO employee_summary target
USING employee_stage source
   ON (target.employee_id = source.employee_id)
WHEN MATCHED THEN
    UPDATE SET target.salary = source.salary
WHEN NOT MATCHED THEN
    INSERT (employee_id, salary)
    VALUES (source.employee_id, source.salary);
~~~

`MERGE` is not automatically faster in every case; inspect constraints, data sources, row counts, and execution plans. Still, it expresses set-level upserts in a single statement.

## 14. Context Switching Between PL/SQL and SQL

Every time PL/SQL calls SQL, control and data transfer between the two engines. One switch is small, but hundreds of thousands or millions of switches create substantial overhead.

Common pattern:

~~~text
PL/SQL loop
   |
   +--> SQL UPDATE one row
   |
   +--> SQL UPDATE one row
   |
   +--> SQL UPDATE one row
   |
   +--> ... repeated many times
~~~

Techniques to reduce context switches:

- Use a single set-based SQL statement whenever possible.
- Use `BULK COLLECT` to fetch many rows per call.
- Use `FORALL` to send many DML executions in one bulk bind.
- Avoid calling PL/SQL functions from SQL millions of times if an equivalent SQL expression exists.
- Avoid running `SELECT` inside a loop just to look up data that can be joined in one query.

## 15. BULK COLLECT and FORALL

### 15.1 BULK COLLECT

`BULK COLLECT` fetches multiple rows from SQL into collections:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Fetched=' || l_ids.COUNT);
END;
/
~~~

Instead of transferring row by row, bulk collect moves a batch of rows into PL/SQL memory.

### 15.2 Use LIMIT to Control Memory

Avoid `BULK COLLECT`ing an entire huge table into collections unnecessarily. Use a cursor with `LIMIT`:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 10;

    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_ids
        LIMIT 500;

        EXIT WHEN l_ids.COUNT = 0;

        DBMS_OUTPUT.PUT_LINE(
            'Batch size=' || l_ids.COUNT
        );
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
~~~

`LIMIT` caps rows per batch and bounds memory usage. The value 500 is illustrative; benchmark against real row widths, PGA, and workload.

### 15.3 FORALL

`FORALL` sends DML over collection indices:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);
END;
/
~~~

`FORALL` reduces switches between PL/SQL and SQL for repeated DML over collections. It is not a standard PL/SQL loop and does not allow arbitrary control structures inside it like `LOOP`.

### 15.4 SAVE EXCEPTIONS

If some DML iterations in `FORALL` may fail while you want remaining elements to proceed, use `SAVE EXCEPTIONS` and inspect `SQL%BULK_EXCEPTIONS`:

~~~sql
DECLARE
    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids := t_ids(1001, 1002, 999999);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', code=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;
END;
/
~~~

`SAVE EXCEPTIONS` alters how per-DML errors are surfaced. Design explicit handling for successful/failed elements, row counts, and transaction policy; never assume the entire batch rolled back automatically.

## 16. Choosing Batch Size

Too small a batch size increases fetch and bulk execution calls. Too large a batch size raises memory usage and can hurt PGA/concurrency.

Test representative sizes such as 100, 500, 1,000, and 5,000, without treating them as universal rules. Measure:

- Elapsed time.
- CPU.
- PGA/memory pressure.
- Batch count.
- Rows processed.
- Waits and impact on concurrent sessions.

Choose batch size based on your workload and environment memory limits, not a popular number from the internet.

## 17. Optimizing PL/SQL Algorithms

Native compilation cannot rescue an algorithm with excessive time complexity.

Example searching for matches via nested loops:

~~~sql
FOR i IN 1 .. l_left.COUNT LOOP
    FOR j IN 1 .. l_right.COUNT LOOP
        IF l_left(i) = l_right(j) THEN
            ...
        END IF;
    END LOOP;
END LOOP;
~~~

For two collections of N elements, this performs comparisons proportional to N squared.

If data can reside in SQL, `JOIN` or `EXISTS` lets the optimizer pick an appropriate join algorithm. If processing must stay in PL/SQL, consider a keyed lookup structure such as an associative array indexed by key.

Questions to ask when tuning:

- Is the same calculation repeated unnecessarily?
- Can loop-invariant values be computed outside the loop?
- Can nested loops be replaced by keyed lookups?
- Can parse calls or function calls be reduced?
- Can type conversions inside loops be eliminated?
- Can the entire set be processed in SQL instead of row by row?

## 18. Avoiding Unnecessary Work in PL/SQL

Targeted micro-adjustments help when profiling proves they sit on a hot path:

- Hoist invariant expressions out of loops.
- Avoid repeated `TO_CHAR`/`TO_NUMBER` conversions when data can stay in its native type.
- Avoid rebuilding large strings repeatedly via unnecessary concatenation.
- Reduce deeply nested function calls on hot paths.
- Use `PLS_INTEGER` for counters within the 32-bit integer range.
- Avoid re-querying data already held in variables or collections.
- Avoid using exceptions as normal control flow inside large loops.

Never change code just because it looks cleaner. Measure before and after.

## 19. Native Compilation and Bulk Processing Solve Different Problems

| Technique | Target Problem | Does Not Directly Solve |
|---|---|---|
| Native compilation | CPU-bound PL/SQL execution overhead | SQL plans, I/O, lock waits |
| PLSQL_OPTIMIZE_LEVEL | Compiler optimization | Poor algorithms or expensive SQL |
| BULK COLLECT | Frequent fetches across engine boundary | Insufficient PGA if batches are unbounded |
| FORALL | Collection-based DML / context switches | Complex per-row logic or poor SQL plans |
| Set-based SQL | Set processing inside the SQL engine | Procedural side effects not expressible in SQL |
| PRAGMA UDF | Overhead of PL/SQL functions called from SQL | Functions with already-expensive internal SQL/logic |
| PRAGMA INLINE | Small subprogram call overhead | I/O and SQL execution |
| RESULT_CACHE | Recomputing stable, repeated outputs | Unique inputs or continuously changing data |

Do not apply multiple techniques simultaneously in a single benchmark, or you will not know which change caused the difference.

## 20. A Native Compilation Benchmarking Process

### Step 1: Select a Representative Workload

Pick a CPU-bound procedure confirmed by a profiler. Record inputs, invocation counts, data, and expected outputs.

### Step 2: Record the INTERPRETED Baseline

Set:

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
~~~

Recompile the object in the session with these settings:

~~~sql
ALTER PROCEDURE calculate_commission COMPILE;
~~~

Confirm settings in `USER_PLSQL_OBJECT_SETTINGS`. Run warm-ups and benchmark trials without profiling enabled.

### Step 3: Capture Baseline Metrics

Record:

- Median/p95 elapsed time.
- CPU time if available.
- Business outputs.
- Invocation count.
- Input size.
- Relevant SQL metrics.
- Compiler settings.

### Step 4: Compile NATIVE

~~~sql
ALTER SESSION SET PLSQL_CODE_TYPE = NATIVE;
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;

ALTER PROCEDURE calculate_commission COMPILE;
~~~

Verify the object's code type is now `NATIVE` in the settings view.

### Step 5: Run the Exact Same Workload

Use identical inputs, session settings, and timing method. Do not run a profiler during the final benchmark runs if the baseline ran without one.

### Step 6: Compare and Validate

Compare elapsed time, CPU, outputs, errors, and concurrency impact. If gains are negligible or unstable, keep the simpler configuration.

### Step 7: Controlled Rollout

List objects to compile, verify `VALID` status, inspect dependent objects, and keep a rollback plan to the prior known settings. Never change `PLSQL_CODE_TYPE` database-wide without scoped impact analysis and planning.

## 21. Example Comparing Interpreted and Native

Example in-memory summation workload:

~~~sql
CREATE OR REPLACE PROCEDURE sum_values (
    p_iterations IN PLS_INTEGER,
    p_result OUT NUMBER
) AS
    l_total NUMBER := 0;
BEGIN
    FOR i IN 1 .. p_iterations LOOP
        l_total := l_total + SQRT(i);
    END LOOP;

    p_result := l_total;
END;
/
~~~

This procedure illustrates a CPU-bound workload, though `SQRT` is a numeric built-in whose characteristics vary by version. Test the same iteration count under both code types.

For better benchmarking:

- Run multiple trials with identical `p_iterations`.
- Do not print output inside the loop.
- Capture `p_result` to ensure work is not optimized away.
- Compare both CPU and elapsed time.
- Test separately across small, medium, and large inputs.
- Never extrapolate from one synthetic procedure that an entire application will speed up similarly.

## 22. Measuring and Tuning Functions Called from SQL

A PL/SQL function can be invoked once per row in SQL:

~~~sql
SELECT order_id,
       calculate_discount(customer_id, amount)
FROM orders;
~~~

If the query returns 1 million rows, the function can be invoked very many times. Evaluate:

1. Can the function be expressed as a SQL expression or `JOIN`?
2. Does the function run SQL inside each invocation?
3. Can `PRAGMA UDF` be used?
4. Can results be cached safely?
5. Does the function depend on session context or mutable data?

If the function runs a separate `SELECT` per row, the problem may be an N+1 SQL pattern. Native compilation will not eliminate those `SELECT` executions. Try `JOIN` or set-based SQL.

## 23. Dynamic SQL, Parsing, and Bind Variables

Constructing distinct SQL text for every input value increases hard parses and shared pool pressure.

Avoid:

~~~sql
l_sql := 'SELECT salary FROM employees WHERE employee_id = ' ||
         TO_CHAR(p_employee_id);
EXECUTE IMMEDIATE l_sql INTO l_salary;
~~~

Prefer binding:

~~~sql
l_sql := 'SELECT salary FROM employees WHERE employee_id = :id';

EXECUTE IMMEDIATE l_sql
INTO l_salary
USING p_employee_id;
~~~

Bind variables promote cursor sharing when SQL text is consistent and prevent concatenating input data into SQL. Table/column names cannot be bound as values; if dynamic object names are required, enforce an allowlist and validate properly.

## 24. Distinguishing Compile Time from Runtime

The following operations serve different roles:

| Operation | When It Takes Effect | Meaning |
|---|---|---|
| ALTER SESSION SET PLSQL_CODE_TYPE | At compile time in session | Chooses code type for subsequent compilations |
| ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL | At compile time in session | Chooses compiler optimization level |
| ALTER PROCEDURE ... COMPILE | Compile time | Recompiles the procedure |
| DBMS_HPROF/DBMS_PROFILER | Runtime | Collects execution profiles |
| SQL Trace | Runtime | Captures SQL activity and waits |
| DBMS_XPLAN.DISPLAY_CURSOR | After/during cursor execution | Displays execution plan and available runtime stats |

Changing compiler parameters without recompiling objects leaves previously compiled code unchanged. Conversely, a profiler does not alter code type; it observes execution and adds overhead.

## 25. Caution When Optimizing in Production

A compiler or source change can affect many dependent objects. Before deploying:

- Test in a production-like environment.
- Verify code type/optimize level per object.
- Compile during a controlled deployment window.
- Query `USER_OBJECTS`/`DBA_OBJECTS` to confirm objects are `VALID`.
- Check `USER_ERRORS`/`DBA_ERRORS`.
- Test application call flows.
- Monitor CPU, elapsed time, waits, and errors post-deployment.
- Have a plan to recompile with prior settings if outcomes degrade.

Never run `ALTER SYSTEM` just to experiment with one procedure. Never recompile an entire schema without understanding invalidation scope and workload impact.

## 26. Reading Optimization Results

Example benchmark table:

| Version | Median Elapsed | CPU | Buffers | Correct Output? |
|---|---:|---:|---:|---|
| Baseline interpreted | 8.2 s | 7.4 s | 120,000 | Yes |
| Native | 7.8 s | 7.0 s | 120,000 | Yes |
| Bulk DML | 2.1 s | 1.7 s | 35,000 | Yes |

These figures are illustrative examples, not actual Oracle benchmarks. If native trims time slightly while bulk DML slashes both CPU and buffers, the data indicates the main bottleneck was row-by-row/context switching or SQL work.

A solid result requires:

- Identical workload and conditions.
- Equivalent business results.
- Repeatable improvement.
- No regressions for other inputs.
- No sharp spikes in PGA, contention, or operational cost.

## 27. Optimization Technique Selection Flow

~~~mermaid
flowchart TD
    A["Measure elapsed, CPU, waits, and SQL metrics"] --> B{"Is time mainly in SQL?"}
    B -->|Yes| C["Inspect actual plan, buffers, rows, and waits"]
    C --> D["Optimize SQL, indexes, joins, or set-based DML"]
    B -->|No| E{"Is PL/SQL CPU-bound?"}
    E -->|Yes| F["Use profiler to locate hot subprograms/lines"]
    F --> G{"Many row-by-row SQL calls?"}
    G -->|Yes| H["Set-based SQL or BULK COLLECT/FORALL"]
    G -->|No| I["Optimize algorithms and computations"]
    I --> J{"Is PL/SQL overhead still significant?"}
    J -->|Yes| K["Benchmark NATIVE and compiler settings"]
    J -->|No| L["Keep implementation simple"]
    E -->|No| M["Investigate waits, locks, I/O, and concurrency"]
    D --> N["Re-measure and regression test"]
    H --> N
    K --> N
    L --> N
    M --> N
~~~

## 28. Common Optimization Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| Enabling NATIVE database-wide assuming universal speedup | Expands change blast radius without proven benefit | Test on CPU-bound objects and measure |
| Changing PLSQL_CODE_TYPE without recompiling | Object keeps running previously compiled code | Recompile and inspect object settings |
| Measuring only once | Results skewed by cache or transient load | Run multiple trials and compare median/p95 |
| Using elapsed time to diagnose a CPU bottleneck | Confuses waits with CPU consumption | Combine CPU, waits, and profiler |
| Tuning PL/SQL while SQL plan is poor | Primary bottleneck remains untouched | Inspect actual plan and SQL trace |
| Using unbounded BULK COLLECT on large tables | High PGA usage, potential out-of-memory errors | Fetch in batches |
| Using FORALL for logic expressible in one UPDATE | Extra complexity and still slower than set-based SQL | Try set-based SQL first |
| Raising PLSQL_OPTIMIZE_LEVEL without regression testing | Can expose behavioral shifts | Test thoroughly and benchmark |
| Marking non-pure functions DETERMINISTIC | Cached/optimized results become unreliable | Declare only when genuinely deterministic |
| Using RESULT_CACHE on rapidly changing data | Low hit rate or constant invalidation | Measure hit rate and dependencies |
| Leaving profiler enabled in final benchmarks | Instrumentation skews timing | Use profiler to find hotspots, benchmark without it |
| Benchmarking with per-row DBMS_OUTPUT | Measures logging overhead instead of logic | Minimize output inside measured scope |
| Changing multiple techniques at once | Cannot tell which change caused gain or regression | Test one change at a time |
| Comparing only EXPLAIN PLAN cost | Cost is an estimate, not runtime | Check actual rows, buffers, CPU, elapsed, and waits |

## 29. Hands-on Practice Exercises

Run exercises in a test schema using repeatable workloads.

### Exercise 1 — Baseline

Write a CPU-bound procedure and time it using `SYSTIMESTAMP` or `DBMS_UTILITY.GET_TIME`. Run multiple times, recording median, input size, and output.

### Exercise 2 — DBMS_PROFILER

Install profiler tables per DBA instructions. Run a procedure calling multiple helper functions. Find the unit and line with the highest time. Re-measure after disabling the profiler.

### Exercise 3 — DBMS_HPROF

Build a call tree A -> B -> C. Profile with the hierarchical profiler and identify which subprograms dominate inclusive/exclusive time.

### Exercise 4 — SQL Trace

Enable tracing for a session running a SQL-heavy procedure. Use TKPROF to inspect executions, parses, CPU, elapsed time, and waits. Identify SQL called repeatedly.

### Exercise 5 — Interpreted vs. Native

Compile the same procedure as `INTERPRETED`, then `NATIVE`. Check `USER_PLSQL_OBJECT_SETTINGS`, run the same workload multiple times, and compare CPU/elapsed time.

### Exercise 6 — Optimize Level

Compare levels 1, 2, and 3 in a test schema. Verify outputs/exceptions and measure across multiple input sizes. Do not alter database-wide settings.

### Exercise 7 — Row-by-Row vs. Set-Based

Write a row-by-row `UPDATE` loop, then replace it with a single `UPDATE`. Compare elapsed time, CPU, buffers, and SQL execution counts.

### Exercise 8 — BULK COLLECT LIMIT

Fetch data in batches with `LIMIT` 100, 500, 1,000, and 5,000. Compare elapsed time and memory usage.

### Exercise 9 — FORALL

Replace DML inside a loop with `FORALL`. Check `SQL%BULK_ROWCOUNT` and `SAVE EXCEPTIONS` when some inputs are invalid.

### Exercise 10 — PRAGMA UDF

Create a function invoked from SQL across many rows. Compare with `PRAGMA UDF` and an equivalent pure SQL expression if possible. Check outputs and call counts.

### Exercise 11 — Bind Variables

Compare dynamic SQL concatenating literals against dynamic SQL using bind variables. Monitor parse calls and executions.

### Exercise 12 — Single-Variable Experiment

Pick a hotspot confirmed by a profiler. Change exactly one factor, run regression tests, re-measure, and document the conclusion. State clearly why the change is accepted or rejected.

## 30. Pre-Deployment Optimization Checklist

**Measurement**

- Is there a baseline and representative workload?
- Were multiple trials run with median/p95 metrics?
- Were elapsed, CPU, and wait times separated?
- Were expensive SQL statements identified?
- Was the profiler used appropriately and disabled for final benchmarks?

**Compiler**

- What is the object's current `PLSQL_CODE_TYPE`?
- Was the object recompiled under the new settings?
- Is `PLSQL_OPTIMIZE_LEVEL` documented?
- Were compiler warnings reviewed?
- Were unnecessary system-wide setting changes avoided?

**Algorithms and SQL**

- Can row-by-row logic be replaced with set-based SQL?
- Can context switches be reduced using `BULK COLLECT`/`FORALL`?
- Does batch size bound memory usage?
- Are there repeated SQL calls or repeated parses?
- Are PL/SQL functions called repeatedly from SQL?

**Correctness**

- Do business outputs match the baseline?
- Are exception/error contracts preserved?
- Are transactions and commit/rollback behavior unchanged?
- Are side effects neither lost nor duplicated?
- Did regression tests run on small, medium, and large inputs?

**Deployment**

- Is the object `VALID` after compilation?
- Is there a rollback/recompile plan back to prior settings?
- Are CPU, waits, and errors monitored post-deployment?
- Are settings and benchmark results documented?

## 31. Key Takeaways

| Topic | Key Point |
|---|---|
| Measurement first | Measure and locate bottlenecks before changing code |
| PL/SQL engine | Executes control flow, variables, and procedural logic |
| SQL engine | Executes SQL statements and access paths |
| DBMS_PROFILER | Analyzes timing per PL/SQL source line |
| DBMS_HPROF | Analyzes timing across the call tree |
| SQL Trace/TKPROF | Analyzes parse, execute, fetch, and wait events |
| PLSQL_CODE_TYPE | INTERPRETED or NATIVE |
| Native compilation | Can reduce CPU-bound PL/SQL overhead; does not automatically optimize SQL |
| PLSQL_OPTIMIZE_LEVEL | Controls compiler optimization intensity; level 2 is the common default |
| PLSQL_WARNINGS | Detects potential issues at compile time |
| PRAGMA INLINE | Requests compiler inlining for eligible calls |
| PRAGMA UDF | Hints that a function is primarily called from SQL |
| RESULT_CACHE | Reuses results when semantics and dependencies allow |
| Set-based SQL | Usually the first choice for set processing |
| BULK COLLECT | Fetches multiple rows per round-trip |
| FORALL | Sends DML over collections, reducing context switches |
| Bind variables | Enable cursor reuse and avoid concatenating data into SQL |
| Regression tests | Optimizations must preserve outputs and contracts |

Native compilation is a targeted optimization tool, not a database-wide turbo switch. Use a profiler to find where PL/SQL truly burns CPU, use SQL trace and actual plans to find SQL costs, and choose the right technique. Set-based SQL and bulk processing typically yield the biggest gains when code processes row by row; native compilation should only be considered after measurements confirm PL/SQL execution overhead remains significant. Every change needs a baseline, repeated benchmarks, and regression tests before deployment.

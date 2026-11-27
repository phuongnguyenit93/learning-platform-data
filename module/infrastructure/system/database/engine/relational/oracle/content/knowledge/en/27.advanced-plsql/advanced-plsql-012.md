# DBMS_PROFILER, DBMS_HPROF, and Pinpointing Expensive Code

When a PL/SQL procedure or package runs slowly, measuring only the total duration of the call is rarely enough to find the root cause. Time may be spent inside a loop, a function called thousands of times, a rarely noticed branch, or a SQL statement embedded in the PL/SQL flow.

Oracle provides two key profiling tools:

- **DBMS_PROFILER:** measures execution counts and timings for every PL/SQL line with generated code. Results are saved in profiler tables for querying and locating hot lines.
- **DBMS_HPROF:** hierarchical profiler, recording the subprogram call tree. It separates time spent in the subprogram itself from time spent across the entire subtree, and distinguishes SQL execution from PL/SQL execution.

These two tools complement each other. DBMS_PROFILER helps locate expensive code lines; DBMS_HPROF reveals who calls a subprogram, how often, whether time lies inside the subprogram itself or its children, and what share belongs to SQL. Once slow SQL is spotted, investigate further at the SQL layer via execution plans or SQL trace.

## 1. What Is Profiling?

Profiling is the process of collecting runtime metrics while a program runs to pinpoint where time or resources are spent. For PL/SQL, profiling answers:

- Which procedure consumes the majority of time?
- Which function is invoked too many times?
- Which PL/SQL lines accumulate high total execution time?
- Is a subprogram expensive due to its own logic or because of subprograms it calls?
- How much time does SQL invoked from PL/SQL consume?
- Did a source change reduce time in the targeted section?

Profiling differs from benchmarking:

| Activity | Purpose |
|---|---|
| Benchmarking | Measures total duration and throughput of a workload |
| Profiling | Breaks a workload into parts to find bottlenecks |
| Tracing | Records event or call sequences to understand execution flow |
| Code coverage | Identifies which code paths executed during a test suite |

A profiling run does not replace a benchmark. Profilers introduce overhead, so results must be cross-checked against unprofiled measurements.

## 2. Choosing the Right Tool

Oracle offers multiple tools related to PL/SQL performance. Do not use a single tool for every question.

| Tool | Observation level | Answers the question |
|---|---|---|
| DBMS_PROFILER | PL/SQL lines | Which lines execute frequently or take the most time? |
| DBMS_HPROF | Subprogram call tree and SQL | Who calls the slow function, and what are self/subtree and SQL/PLSQL times? |
| DBMS_TRACE | Sequence of PL/SQL calls/events | Which subprograms run and in what order? |
| SQL Trace / TKPROF | SQL statements | Which SQL parses, executes, fetches heavily, or reads many blocks? |
| DBMS_XPLAN | Execution plan | Which access paths and join methods did the optimizer pick? |
| DBMS_APPLICATION_INFO | Session module/action | Which application task is currently running in the session? |

### 2.1 DBMS_PROFILER

DBMS_PROFILER collects execution count, total time, minimum time, and maximum time per line. Data is persisted into tables such as:

- PLSQL_PROFILER_RUNS
- PLSQL_PROFILER_UNITS
- PLSQL_PROFILER_DATA

It is a flat profiler (lacking a full call tree). It works well for finding hot lines inside a known unit.

### 2.2 DBMS_HPROF

DBMS_HPROF organizes results as a call tree. For each subprogram, you can inspect:

- Call count.
- Function time or self time: time inside the subprogram itself, excluding child subprograms.
- Subtree time: time of the subprogram plus all descendant subprograms.
- Parent-child relationships: which subprogram calls which.
- SQL statements executed from PL/SQL and their SQL timings.

This is usually the right starting point when you do not yet know which procedure in a deep call chain holds the bottleneck.

### 2.3 DBMS_TRACE

DBMS_TRACE records the execution sequence of subprograms according to the chosen trace level. It helps trace call flow, though it does not replace a timing profiler. Traces can grow very large if enabled broadly.

### 2.4 SQL Trace and DBMS_XPLAN

When HPROF shows SQL statements taking substantial time, investigate SQL at its own layer:

- Use SQL_ID to locate the SQL statement in the shared SQL area.
- Use DBMS_XPLAN.DISPLAY_CURSOR to inspect the plan and runtime statistics.
- Use SQL Trace/TKPROF when analyzing parse, execute, fetch, waits, and I/O.

Never conclude PL/SQL is slow merely because a line containing a SELECT appears hot in DBMS_PROFILER. A SQL statement is a single line in PL/SQL yet performs multi-step work inside the SQL engine.

## 3. A Repeatable Profiling Workflow

A practical workflow should run iteratively:

~~~text
Identify slow workload
        |
        v
Record unprofiled baseline
        |
        v
Warm up packages and data
        |
        v
Enable profiler for target session/workload
        |
        v
Run representative inputs
        |
        v
Stop profiler and persist results
        |
        v
Inspect hot lines / call tree / SQL time
        |
        v
Pick one evidence-backed bottleneck
        |
        v
Make one change and re-benchmark
        |
        v
Compare baseline, profile, and new results
~~~

### 3.1 Define a Representative Workload

Before starting the profiler, specify:

- Target procedure or transaction to analyze.
- Inputs matching production size and distribution.
- Iteration counts or row volumes.
- Business branches that must be exercised.
- Initial cache and data states.
- Package version and collection timestamp.

If a test exercises only a trivial branch, the profiler cannot reveal the cost of unexecuted branches.

### 3.2 Warm Up Before Measuring

The first call to a package can include loading PL/SQL bytecode, package initialization, reading metadata, or warming buffer caches. Oracle recommends running the workload once without the profiler before collecting data so startup overhead does not skew results.

Warm-up does not mean flushing caches arbitrarily. The goal is measuring the steady state typical of production. Record clearly whether a benchmark measures cold-start or steady-state performance.

### 3.3 Keep Measurement Conditions Stable

When comparing two runs:

- Use identical inputs and row counts.
- Use identical data and package versions.
- Minimize unrelated background workloads during measurement.
- Run multiple iterations if variance exists.
- Record elapsed time, CPU, logical reads, and physical reads when available.
- Never change multiple factors simultaneously.

### 3.4 Profile Only the Needed Scope

Enable the profiler only for the target session and only for the brief window required. Profiling an entire application or long-lived session generates massive data and adds overhead.

## 4. DBMS_PROFILER: How It Works

DBMS_PROFILER gathers data at the PL/SQL virtual machine level. Data shows:

- Which lines executed.
- How many times each line executed.
- Total time recorded for each line.
- Minimum and maximum time of a single execution of the line.

Time values in PLSQL_PROFILER_DATA and RUN_TOTAL_TIME are stored in nanoseconds. This is the profiler's reporting unit, not a promise that system clocks have true single-nanosecond hardware precision.

### 4.1 Installing Profiler Tables

DBMS_PROFILER writes results to profiler tables in the schema. Oracle's setup script is typically located at:

~~~sql
@?/rdbms/admin/proftab.sql
~~~

This script creates the tables and structures needed to store run, unit, and line statistics. **Note:** PROFTAB.SQL may DROP existing profiler tables before recreating them. Run it only in a fresh profiler schema or after backing up and confirming old data can be discarded. Never run this script blindly in a schema holding results you need to preserve.

From Oracle Database 10g onward, the DBMS_PROFILER package is installed automatically during database creation; PROFLOAD.SQL is no longer required in those versions. Creating the result tables remains a separate step.

### 4.2 Required Privileges

A user running the profiler needs:

- EXECUTE on DBMS_PROFILER.
- Privileges required to write to the profiler tables and associated sequences.
- CREATE privileges on profiled PL/SQL units per DBMS_PROFILER's security model.

EXECUTE-only privilege on a unit is insufficient to profile it. When packages belong to another schema, have the DBA design appropriate grants rather than granting overly broad privileges.

### 4.3 Compiling Units in DEBUG Mode

Oracle recommends compiling units to be profiled with DEBUG so the profiler captures richer metadata. Example:

~~~sql
ALTER PACKAGE profile_demo COMPILE DEBUG BODY;
~~~

DBMS_PROFILER does not strictly require every unit to compile with DEBUG to run, though DEBUG provides better detail. Units compiled in NATIVE mode do not produce DBMS_PROFILER output per Oracle's compilation/security rules; check compilation mode before concluding the profiler is broken.

## 5. Collecting Data with DBMS_PROFILER

### 5.1 Starting a Run

START_PROFILER begins collection in the current session. An overload returns the run number via an OUT parameter:

~~~sql
DECLARE
    l_run_id PLS_INTEGER;
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.START_PROFILER(
        run_comment  => 'profile_demo baseline input=10000',
        run_comment1 => 'Build 1.0, test scenario A',
        run_number   => l_run_id
    );

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Cannot start DBMS_PROFILER. Status=' || l_status
        );
    END IF;

    DBMS_OUTPUT.PUT_LINE('Profiler run id=' || l_run_id);
END;
/
~~~

A return value of 0 means success; any non-zero value indicates an error status. Save the run ID to query the data afterward.

### 5.2 Running the Target Program

After START_PROFILER succeeds, execute the target procedure or workload in the same session:

~~~sql
BEGIN
    profile_demo.run_workload(10000);
END;
/
~~~

The profiler records executed units in the session within the user's privilege scope.

### 5.3 Stopping the Profiler and Flushing Data

~~~sql
DECLARE
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.STOP_PROFILER;

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Cannot stop DBMS_PROFILER. Status=' || l_status
        );
    END IF;
END;
/
~~~

STOP_PROFILER ends the run and flushes collected data to the profiler tables. Data buffered in session memory is not automatically persisted simply on disconnect; always call STOP_PROFILER or FLUSH_DATA.

### 5.4 FLUSH_DATA, PAUSE_PROFILER, and RESUME_PROFILER

- FLUSH_DATA writes profiler data collected so far into tables and frees part of the in-memory structures.
- PAUSE_PROFILER temporarily suspends collection.
- RESUME_PROFILER resumes collection.

Example:

~~~sql
DECLARE
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.PAUSE_PROFILER;
    -- Perform work excluded from the profile.
    l_status := DBMS_PROFILER.RESUME_PROFILER;
END;
/
~~~

Check the return status of each call before continuing. When handling errors, never ignore failed flush or stop statuses because profiler data may be incomplete.

## 6. Reading DBMS_PROFILER Data

### 6.1 Three Core Tables

| Table | Contents |
|---|---|
| PLSQL_PROFILER_RUNS | One row per run: run ID, owner, start time, comment, total time |
| PLSQL_PROFILER_UNITS | PL/SQL library units profiled during the run |
| PLSQL_PROFILER_DATA | Execution counts and timings per line in each unit |

Key columns:

| Table/column | Meaning |
|---|---|
| RUNS.RUNID | Run identifier |
| RUNS.RUN_OWNER | User who ran the profiler |
| RUNS.RUN_DATE | Start timestamp |
| RUNS.RUN_COMMENT | Benchmark description |
| RUNS.RUN_TOTAL_TIME | Total elapsed time of the run, nanoseconds |
| UNITS.UNIT_NUMBER | Unit identifier within the run |
| UNITS.UNIT_OWNER / UNIT_NAME / UNIT_TYPE | Owner, name, and type of the unit |
| DATA.LINE# | Line number in the unit's source |
| DATA.TOTAL_OCCUR | Number of times the line executed |
| DATA.TOTAL_TIME | Total time recorded on the line, nanoseconds |
| DATA.MIN_TIME / MAX_TIME | Minimum/maximum time for a single execution of the line |

PLSQL_PROFILER_UNITS.TOTAL_TIME is provided for analysis tools, yet the profiler does not populate it automatically. When aggregating by unit, sum from PLSQL_PROFILER_DATA.

### 6.2 Viewing Recent Runs

~~~sql
SELECT runid,
       run_owner,
       run_date,
       run_comment,
       run_total_time / 1000000 AS total_elapsed_ms
FROM plsql_profiler_runs
ORDER BY runid DESC;
~~~

Divide nanoseconds by 1,000,000 to display milliseconds. Retain run IDs when comparing across versions.

### 6.3 Finding Lines with the Highest Total Time

~~~sql
SELECT u.unit_owner,
       u.unit_name,
       u.unit_type,
       d.line# AS line_no,
       d.total_occur,
       ROUND(d.total_time / 1000000, 3) AS total_ms,
       ROUND(d.min_time / 1000000, 3) AS min_ms,
       ROUND(d.max_time / 1000000, 3) AS max_ms
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
WHERE d.runid = :p_run_id
ORDER BY d.total_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

This is the starting point for locating hot lines. High total time can stem from slow individual runs or huge execution counts. Compare TOTAL_TIME against TOTAL_OCCUR and MAX_TIME.

### 6.4 Aggregating by Unit

~~~sql
SELECT u.unit_owner,
       u.unit_name,
       u.unit_type,
       SUM(d.total_occur) AS line_occurrences,
       ROUND(SUM(d.total_time) / 1000000, 3) AS total_ms
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
WHERE d.runid = :p_run_id
GROUP BY u.unit_owner, u.unit_name, u.unit_type
ORDER BY SUM(d.total_time) DESC;
~~~

Unit aggregation narrows scope before reading individual lines. A heavily called unit can rank at the top even if each single execution is fast.

### 6.5 Joining Line Statistics with Source Code

If the user has access to source via ALL_SOURCE:

~~~sql
SELECT u.unit_owner,
       u.unit_name,
       u.unit_type,
       s.line,
       s.text,
       d.total_occur,
       ROUND(d.total_time / 1000000, 3) AS total_ms
FROM plsql_profiler_data d
JOIN plsql_profiler_units u
  ON u.runid = d.runid
 AND u.unit_number = d.unit_number
JOIN all_source s
  ON s.owner = u.unit_owner
 AND s.name = u.unit_name
 AND s.type = u.unit_type
 AND s.line = d.line#
WHERE d.runid = :p_run_id
ORDER BY d.total_time DESC;
~~~

If source code changed after profiling, line numbers will no longer align with current source. Record unit timestamps/versions and inspect source matching the profiled run.

### 6.6 Interpreting TOTAL_OCCUR and TOTAL_TIME

Example:

| Line | TOTAL_OCCUR | TOTAL_TIME | Interpretation |
|---:|---:|---:|---|
| 20 | 1 | 500 ms | One execution was very expensive |
| 35 | 100,000 | 300 ms | Cheap per call, but huge call count |
| 50 | 10 | 250 ms | Likely heavy work inside a specific branch |

Do not sort solely by total time. A line with high MAX_TIME and tiny TOTAL_OCCUR may be an outlier; a line with huge TOTAL_OCCUR is a prime candidate for reducing calls or batching.

## 7. Limitations When Reading DBMS_PROFILER

### 7.1 Multi-Line SQL Statements May Map to One Line

PL/SQL passes a processed SQL statement to the SQL engine as one operation. Thus, a multi-line SQL statement typically maps to a single line in the profiler, usually the first line. Not every line inside the SQL block gets its own record.

### 7.2 Multiple Statements on One Line Are Merged

Putting multiple statements on a single source line merges their occurrences and timings. Combining IF/ELSE on one line obscures which branch ran. Place each statement on its own line when detailed analysis is desired.

### 7.3 Missing Records Do Not Always Mean Unexecuted Code

PLSQL_PROFILER_DATA records lines that have generated code. No record for a line can simply mean no executable code was generated for that line. A record with TOTAL_OCCUR = 0 means generated code for that line did not run. Always read source alongside metadata rather than inferring coverage solely from missing rows.

### 7.4 Compiler Optimization Affects Line Mapping

The compiler can optimize or fold code. For coverage purposes, Oracle notes setting `PLSQL_OPTIMIZE_LEVEL=1` to simplify interpreting coverage data; this does not mean lowering optimization levels in production just for performance profiling. Whenever compile settings change, record the configuration and measure separately because performance changes too.

### 7.5 DBMS_PROFILER Is Not a SQL Profiler

DBMS_PROFILER indicates that a PL/SQL line containing SQL took notable time, yet it does not break down operations inside the SQL engine. Use DBMS_HPROF to separate SQL time from PL/SQL time; then use SQL_ID, DBMS_XPLAN, or SQL Trace as needed.

## 8. DBMS_HPROF: Hierarchical Profiler

DBMS_HPROF captures call and return events to build a call tree. Results show not only which subprograms are expensive, but also where they were called from.

### 8.1 Self Time and Subtree Time

Two essential metrics:

- **Function elapsed time (self time):** time spent inside the subprogram itself, excluding descendant subprograms.
- **Subtree elapsed time:** time of the subprogram plus all descendant subprograms called beneath it.

Example:

~~~text
process_order                         subtree = 900 ms
  validate_order                      subtree = 100 ms
  calculate_price                     subtree = 600 ms
    load_price_rules                  subtree = 450 ms
      SQL statement                   subtree = 400 ms
  write_audit                         subtree = 150 ms
~~~

If `calculate_price` shows 600 ms subtree time yet only 150 ms self time, most time sits inside child calls. Optimizing `calculate_price` alone without examining `load_price_rules` will miss the real bottleneck.

### 8.2 HPROF Distinguishes SQL from PL/SQL

The hierarchical profiler separates two primary namespaces:

- PLSQL: subprogram calls, triggers, anonymous blocks, package initialization, etc.
- SQL: SQL statements executed from PL/SQL, including static SQL, dynamic SQL, and SQL fetches.

HPROF therefore highlights time spent in the SQL engine versus PL/SQL processing. SQL statements appear under special labels such as static SQL at line N, dynamic SQL at line N, or fetch at line N.

### 8.3 HPROF Does Not Measure Individual PL/SQL Lines

HPROF uses line numbers only to identify where a subprogram is declared in source and to distinguish overloads. It does not time individual executable lines like DBMS_PROFILER. Once you identify a hot function in HPROF, supplement with DBMS_PROFILER to locate hot lines inside it.

### 8.4 No Special Source Preparation or Compilation Needed

Per Oracle documentation, HPROF requires no special source preparation or compile-time flags to collect call profiles. This is convenient when inspecting a call graph without modifying source code.

## 9. Setup and Privileges for DBMS_HPROF

DBMS_HPROF supports two ways to store raw profiler data depending on version and API:

1. Writing raw trace to a file in a directory object, then analyzing the file.
2. Writing raw trace to profiler tables, then analyzing by trace ID.

### 9.1 HPROF Tables in Newer Releases

In releases supporting CREATE_TABLES, create profiler tables in the schema:

~~~sql
BEGIN
    DBMS_HPROF.CREATE_TABLES(force_it => FALSE);
END;
/
~~~

The primary analysis tables are:

- DBMSHP_RUNS
- DBMSHP_FUNCTION_INFO
- DBMSHP_PARENT_CHILD_INFO

In table-based raw trace mode, Oracle also manages the raw profiler data table and related structures.

Never pass `FORCE_IT = TRUE` in a schema containing data you want to keep: that option drops and recreates existing profiler tables.

### 9.2 DBMSHPTAB.SQL Script and Version Differences

In older releases, Oracle documented running:

~~~sql
@?/rdbms/admin/dbmshptab.sql
~~~

The DBMSHPTAB.SQL script was deprecated starting in Oracle Database 18c. On versions providing `DBMS_HPROF.CREATE_TABLES`, prefer the API per version-specific documentation. The legacy script may also drop existing profiler tables, so verify before running.

### 9.3 Required Privileges

Using DBMS_HPROF requires EXECUTE on the package. When using file mode:

- START_PROFILING requires WRITE on the directory object.
- ANALYZE on a file requires READ on the directory object.
- The physical OS path must exist on the database server and the Oracle OS user must have appropriate OS permissions.

Example DBA commands to create a directory object and grant privileges:

~~~sql
CREATE OR REPLACE DIRECTORY plshprof_dir
AS '/u01/app/oracle/plshprof';

GRANT READ, WRITE ON DIRECTORY plshprof_dir TO app_user;
~~~

A directory object is strictly a database alias; it does not create the OS directory itself. The OS account running Oracle must have read/write permissions on the physical folder.

## 10. DBMS_HPROF with Raw Trace Stored in Tables

This is the most convenient method on releases supporting the table-based API.

### 10.1 Starting Profiling

~~~sql
DECLARE
    l_trace_id NUMBER;
BEGIN
    l_trace_id := DBMS_HPROF.START_PROFILING(
        run_comment => 'profile_demo hierarchical run A'
    );

    DBMS_OUTPUT.PUT_LINE('Trace id=' || l_trace_id);
END;
/
~~~

START_PROFILING returns the trace ID for the raw data. Note that this is the trace ID, not yet the run ID in the analysis tables.

### 10.2 Running the Workload and Stopping Profiling

~~~sql
BEGIN
    profile_demo.run_workload(10000);
END;
/

BEGIN
    DBMS_HPROF.STOP_PROFILING;
END;
/
~~~

Stop profiling immediately after the target workload so unrelated operations do not pollute the trace.

### 10.3 Analyzing the Trace

~~~sql
DECLARE
    l_run_id NUMBER;
    l_trace_id NUMBER := :p_trace_id;
BEGIN
    l_run_id := DBMS_HPROF.ANALYZE(
        trace_id    => l_trace_id,
        run_comment => 'profile_demo analyzed run A'
    );

    DBMS_OUTPUT.PUT_LINE('Analyzed run id=' || l_run_id);
END;
/
~~~

ANALYZE reads the raw trace and populates the hierarchical profiler tables. It returns a run ID for querying DBMSHP_RUNS, DBMSHP_FUNCTION_INFO, and DBMSHP_PARENT_CHILD_INFO.

### 10.4 Distinguishing Trace ID from Run ID

| ID | Meaning |
|---|---|
| Trace ID | Identifies the raw profiler data just collected |
| Run ID | Identifies analyzed results stored in analysis tables by ANALYZE |

Never mix up the two IDs when querying data. Analyzing a trace ID generates its corresponding run ID.

## 11. DBMS_HPROF with Raw Trace Stored in Files

File mode appears frequently in legacy examples and older API versions. Exact calls depend on Oracle release.

### 11.1 Starting File Collection

~~~sql
BEGIN
    DBMS_HPROF.START_PROFILING(
        location => 'PLSHPROF_DIR',
        filename => 'profile_run_a.trc'
    );
END;
/
~~~

### 11.2 Running the Program and Stopping

~~~sql
BEGIN
    profile_demo.run_workload(10000);
END;
/

BEGIN
    DBMS_HPROF.STOP_PROFILING;
END;
/
~~~

### 11.3 Analyzing the File

~~~sql
DECLARE
    l_run_id NUMBER;
BEGIN
    l_run_id := DBMS_HPROF.ANALYZE(
        location    => 'PLSHPROF_DIR',
        filename    => 'profile_run_a.trc',
        run_comment => 'profile_demo file run A'
    );

    DBMS_OUTPUT.PUT_LINE('Run id=' || l_run_id);
END;
/
~~~

### 11.4 Oracle Versions

The file-based API taking location/filename is documented in earlier releases. Newer releases added the table-based API where START_PROFILING returns a trace ID and ANALYZE accepts that trace ID; DBMSHPTAB.SQL was deprecated in 18c. Before copying blocks into a live environment, check the package specification and documentation for your running database version. Never mix parameters from two distinct overloads in the same call.

## 12. Reading DBMS_HPROF Data

### 12.1 Analysis Tables

| Table | Contents |
|---|---|
| DBMSHP_RUNS | Summary metadata for each analyzed run |
| DBMSHP_FUNCTION_INFO | Metrics per subprogram or SQL operation in the run |
| DBMSHP_PARENT_CHILD_INFO | Call counts and timings between caller and callee |

Key columns in DBMSHP_FUNCTION_INFO:

| Column | Meaning |
|---|---|
| RUNID | Analyzed run identifier |
| SYMBOLID | Subprogram identifier within the run |
| OWNER / MODULE / TYPE | Schema, module, and unit type |
| FUNCTION | Subprogram name or special operation label |
| LINE# | Line where the subprogram is declared in the module |
| HASH | Signature hash distinguishing overloads |
| NAMESPACE | PLSQL or SQL |
| CALLS | Invocation count |
| FUNCTION_ELAPSED_TIME | Self time, microseconds |
| SUBTREE_ELAPSED_TIME | Inclusive time, microseconds |
| SQL_ID / SQL_TEXT | SQL identifier and leading SQL text for SQL operations |

DBMSHP_PARENT_CHILD_INFO stores call counts and timings for a child when invoked from a specific parent. This reveals whether a function is slow for all callers or only when invoked from one particular branch.

### 12.2 Viewing Recent Runs

~~~sql
SELECT runid,
       run_timestamp,
       run_comment,
       total_elapsed_time
FROM dbmshp_runs
ORDER BY runid DESC;
~~~

### 12.3 Finding Subprograms with High Subtree Time

~~~sql
SELECT owner,
       module,
       type,
       function,
       line# AS definition_line,
       namespace,
       calls,
       ROUND(function_elapsed_time / 1000, 3) AS self_ms,
       ROUND(subtree_elapsed_time / 1000, 3) AS subtree_ms,
       sql_id,
       sql_text
FROM dbmshp_function_info
WHERE runid = :p_run_id
ORDER BY subtree_elapsed_time DESC
FETCH FIRST 30 ROWS ONLY;
~~~

Timings in HPROF tables are in microseconds; divide by 1,000 for milliseconds. If subtree time is large while self time is small, inspect child functions. If self time is large, investigate that subprogram or SQL operation itself.

### 12.4 Viewing SQL Operations

~~~sql
SELECT function,
       line#,
       calls,
       ROUND(function_elapsed_time / 1000, 3) AS sql_time_ms,
       sql_id,
       sql_text
FROM dbmshp_function_info
WHERE runid = :p_run_id
  AND namespace = 'SQL'
ORDER BY function_elapsed_time DESC;
~~~

When SQL_ID is populated, look up the full SQL text and execution plan. SQL_TEXT in the HPROF table stores only the leading prefix, which is not always enough to identify the entire statement.

### 12.5 Viewing Caller and Callee

~~~sql
SELECT p.owner AS parent_owner,
       p.module AS parent_module,
       p.function AS parent_function,
       c.owner AS child_owner,
       c.module AS child_module,
       c.function AS child_function,
       pc.calls,
       ROUND(pc.function_elapsed_time / 1000, 3) AS child_self_ms,
       ROUND(pc.subtree_elapsed_time / 1000, 3) AS child_subtree_ms
FROM dbmshp_parent_child_info pc
JOIN dbmshp_function_info p
  ON p.runid = pc.runid
 AND p.symbolid = pc.parentsymid
JOIN dbmshp_function_info c
  ON c.runid = pc.runid
 AND c.symbolid = pc.childsymid
WHERE pc.runid = :p_run_id
ORDER BY pc.subtree_elapsed_time DESC;
~~~

This query reveals whether a child function is slow only when called from one specific parent or called excessively from one code path.

### 12.6 Distinguishing Overloaded Subprograms

Two procedures/functions sharing a name with different signatures appear as separate entries. Use LINE# and HASH to tell them apart. When source changes, line numbers can shift; signature hashes change when signatures change. Never group solely by FUNCTION name when a module has overloads.

## 13. Interpreting HPROF to Find Bottlenecks

### 13.1 High Subtree Time, Low Self Time

Example:

| Function | Calls | Self ms | Subtree ms |
|---|---:|---:|---:|
| process_invoice | 1 | 20 | 1,200 |
| load_tax_rules | 1 | 10 | 700 |
| execute_tax_query | 1 | 5 | 650 |

`process_invoice` itself does not burn 1,200 ms. Most time sits in descendant calls, especially the SQL query at the bottom.

### 13.2 High Self Time

When a function shows high self time, inspect:

- Loops and repeated calculations.
- Data conversions or string manipulation.
- Linear scans over large collections.
- Repeated function calls inside conditionals.
- Algorithms whose complexity grows rapidly with input size.

### 13.3 High Call Count with Low Mean Time

A function may be fast per call yet executed hundreds of thousands of times. Compute the mean:

\[
\text{Mean self time} =
\frac{\text{Function elapsed time}}{\text{Calls}}
\]

If a tiny function is called inside a huge loop, reduce overhead by precomputing, passing precomputed values, or batching data.

### 13.4 One SQL Statement Dominates Runtime

When HPROF shows the SQL namespace dominating total time:

1. Grab the SQL_ID.
2. Inspect the cursor and plan with DBMS_XPLAN.DISPLAY_CURSOR.
3. Compare E-Rows against A-Rows.
4. Inspect buffers, reads, waits, and bind values.
5. Check indexes, partition pruning, join methods, and statistics.
6. Tune the SQL or schema at the proper layer.

Never rewrite PL/SQL loops when the bulk of the time lies inside the SQL engine.

## 14. Example Package for Profiling Practice

Create a package with multiple call layers. The goal is creating a workload easily observed with both DBMS_PROFILER and DBMS_HPROF.

### 14.1 Create Package Specification

~~~sql
CREATE OR REPLACE PACKAGE profile_demo AS
    PROCEDURE run_workload(p_iterations IN PLS_INTEGER);
END profile_demo;
/
~~~

### 14.2 Create Package Body

~~~sql
CREATE OR REPLACE PACKAGE BODY profile_demo AS
    FUNCTION normalize_value(p_value IN PLS_INTEGER)
        RETURN PLS_INTEGER
    IS
    BEGIN
        RETURN MOD(p_value * 17 + 13, 100003);
    END normalize_value;

    FUNCTION calculate_value(p_value IN PLS_INTEGER)
        RETURN NUMBER
    IS
        l_result NUMBER := 0;
        l_value  PLS_INTEGER;
    BEGIN
        FOR i IN 1 .. 20 LOOP
            l_value := normalize_value(p_value + i);
            l_result := l_result + SQRT(l_value + 1);
        END LOOP;

        RETURN l_result;
    END calculate_value;

    PROCEDURE run_workload(p_iterations IN PLS_INTEGER)
    IS
        l_total NUMBER := 0;
    BEGIN
        FOR i IN 1 .. p_iterations LOOP
            l_total := l_total + calculate_value(i);
        END LOOP;

        DBMS_OUTPUT.PUT_LINE('Total=' || l_total);
    END run_workload;
END profile_demo;
/
~~~

The package has three layers: `run_workload` calls `calculate_value`, and `calculate_value` calls `normalize_value` repeatedly. This structure lets HPROF display a clear call tree while DBMS_PROFILER highlights the loop lines with high total time.

### 14.3 Compile with DEBUG If Needed

~~~sql
ALTER PACKAGE profile_demo COMPILE DEBUG BODY;
~~~

### 14.4 Warm Up

~~~sql
BEGIN
    profile_demo.run_workload(1000);
END;
/
~~~

### 14.5 Run DBMS_PROFILER

After creating profiler tables via PROFTAB.SQL in your lab schema:

~~~sql
DECLARE
    l_run_id PLS_INTEGER;
    l_status PLS_INTEGER;
BEGIN
    l_status := DBMS_PROFILER.START_PROFILER(
        run_comment => 'profile_demo line profile 1000',
        run_number  => l_run_id
    );

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Profiler start failed');
    END IF;

    profile_demo.run_workload(1000);

    l_status := DBMS_PROFILER.STOP_PROFILER;

    IF l_status <> 0 THEN
        RAISE_APPLICATION_ERROR(-20011, 'Profiler stop failed');
    END IF;

    DBMS_OUTPUT.PUT_LINE('Profiler run=' || l_run_id);
END;
/
~~~

Then run the hottest-lines query from Section 6.

### 14.6 Run DBMS_HPROF

On releases supporting the table-based API:

Create HPROF tables once beforehand with `DBMS_HPROF.CREATE_TABLES(force_it => FALSE)` if they do not exist yet. The block below assumes setup is already done; do not call CREATE_TABLES on every run.

~~~sql
DECLARE
    l_trace_id NUMBER;
    l_run_id   NUMBER;
BEGIN
    l_trace_id := DBMS_HPROF.START_PROFILING(
        run_comment => 'profile_demo hierarchical 1000'
    );

    profile_demo.run_workload(1000);

    DBMS_HPROF.STOP_PROFILING;

    l_run_id := DBMS_HPROF.ANALYZE(
        trace_id    => l_trace_id,
        run_comment => 'profile_demo analyzed 1000'
    );

    DBMS_OUTPUT.PUT_LINE('Trace id=' || l_trace_id);
    DBMS_OUTPUT.PUT_LINE('Run id=' || l_run_id);
END;
/
~~~

If HPROF tables already exist, calling CREATE_TABLES with FORCE_IT = FALSE raises an error instead of overwriting. Create tables once during schema setup; never treat CREATE_TABLES as a per-run step.

Query DBMSHP_FUNCTION_INFO and DBMSHP_PARENT_CHILD_INFO to inspect the call tree, self time, and subtree time.

## 15. Comparing Before and After Optimization

Profiling is valuable only when used to verify changes.

### 15.1 Record Baseline

Before making edits, save:

- Total unprofiled workload time.
- Run ID from DBMS_PROFILER or DBMS_HPROF.
- Inputs, iteration counts, and row counts.
- Package version and compilation timestamp.
- Key CPU, logical read, and elapsed metrics if available.

### 15.2 Fix One Evidence-Backed Bottleneck

For example, HPROF shows `normalize_value` called 20 times per `calculate_value`. Investigate whether outputs can be computed once, cached within scope, or called fewer times.

Never optimize solely because a function appears in a report. Weigh total time, call count, input scale, and business impact.

### 15.3 Re-Run the Exact Same Workload

After modifying code:

- Use identical inputs.
- Warm up again.
- Run the unprofiled benchmark.
- Capture a fresh profile if confirming the bottleneck shifted.
- Compare total duration, call counts, and targeted component times.

One optimization can speed up an old hotspot while making another function the new bottleneck. Repeat the cycle accordingly.

### 15.4 Never Compare Runs with Different Conditions

Two runs with different cache states, data volumes, DOP, or background system load are not directly comparable. Document conditions and run multiple trials when variance is high.

## 16. Overhead, Precision, and Limitations

### 16.1 Profilers Alter Execution Time

Profilers add work to record events and timings. Therefore:

- Elapsed time with profiling enabled can be higher than normal.
- Use profilers for relative shares and hotspot locations, then benchmark with profiling disabled.
- Never treat profiler timings as production SLA baselines.

### 16.2 Timer Resolution and Short Workloads

A line executing in a few microseconds may not rank stably if the workload is too brief or profiler overhead dominates. Increase iterations to produce a long enough sample while keeping inputs representative.

### 16.3 Warm-Up and Package Initialization

First-call timings include package initialization and metadata loading. If targeting steady-state performance, warm up before enabling the profiler. If targeting cold-start performance, measure and document cold-start explicitly as its own workload.

### 16.4 Inlining and Compiler Optimizations

HPROF may omit a subprogram inlined by the compiler or a deterministic call eliminated by optimization. That does not mean the source lacked the call; the call may simply have been optimized away in compiled code.

### 16.5 Source May Change After Profiling

Line numbers are meaningful only against the exact source version profiled. After recompiling packages or deploying new code, track timestamps/versions and never map old metrics onto new line numbers.

### 16.6 Profiling Does Not Replace Production Monitoring

Profilers fit controlled benchmarks or targeted sessions. Observing production continuously requires combining module/action instrumentation, SQL monitoring, tracing, and system-approved monitoring tools.

## 17. Combining DBMS_APPLICATION_INFO and SQL Tracing

DBMS_APPLICATION_INFO sets session MODULE and ACTION to identify active work:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CONFIRM_ORDER'
    );

    profile_demo.run_workload(1000);

    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => NULL,
        action_name => NULL
    );
END;
/
~~~

Module and action help DBAs and tracing tools isolate application activity. They do not time individual PL/SQL lines like DBMS_PROFILER.

When detailed SQL inspection is required, enable SQL Trace in a controlled session and format with TKPROF. SQL Trace reports parse/execute/fetch and wait details; DBMS_HPROF shows where SQL operations occur in the call tree. Both views complement one another.

## 18. Choosing DBMS_PROFILER vs. DBMS_HPROF

| Scenario | Recommended starting tool |
|---|---|
| Package already known; want hot lines | DBMS_PROFILER |
| Unsure which procedure in a call chain is slow | DBMS_HPROF |
| Want to know which callers invoke a function | DBMS_HPROF |
| Want to separate SQL time from PL/SQL time | DBMS_HPROF |
| Want exact execution count per source line | DBMS_PROFILER |
| Want slow SQL details and execution plans | SQL Trace / DBMS_XPLAN, optionally using SQL_ID from HPROF |
| Want exact call sequence of subprograms | DBMS_TRACE or HPROF |
| Want to verify executed code paths | DBMS_PROFILER or dedicated coverage tools |

An effective workflow starts with HPROF to pinpoint hot subprograms or call branches, then uses DBMS_PROFILER within that unit to inspect hot lines.

## 19. Common Profiling Pitfalls

| Issue | Cause | Remedy |
|---|---|---|
| No DBMS_PROFILER data recorded | Tables missing, missing grants, or unit compiled NATIVE | Check PROFTAB, privileges, and compilation mode |
| Run missing after disconnect | Forgot STOP_PROFILER or FLUSH_DATA | Stop or flush explicitly |
| PROFTAB.SQL wiped old data | Setup script may DROP existing profiler tables | Back up and run in an isolated schema |
| First run looks artificially slow | Includes package load/init and cache warm-up | Warm up before profiling steady state |
| HPROF lacks line-by-line timings | HPROF is hierarchical, not a line profiler | Use DBMS_PROFILER |
| Chased subtree time and tuned wrong function | Time sits in child subprograms | Compare self time and parent-child stats |
| Slow SQL mistaken for slow PL/SQL | DBMS_PROFILER does not break down SQL engine work | Use HPROF, SQL_ID, SQL Trace, and plans |
| Mixed up HPROF trace ID and run ID | One identifies raw trace; the other identifies analyzed run | Track both IDs separately |
| HPROF file not created | Missing WRITE grant or invalid OS path | Check directory object and OS permissions |
| ANALYZE cannot read trace file | Missing READ grant on directory object | Grant READ to the proper schema |
| CREATE_TABLES wiped HPROF tables | Passed FORCE_IT = TRUE | Never force on a schema holding data |
| Cannot distinguish overloaded functions | Grouped only by FUNCTION name | Include LINE# and HASH |
| Line numbers mismatch source | Package recompiled after profiling | Match timestamps and source versions |
| Metrics fluctuate across runs | Varying inputs, cache states, or background load | Standardize benchmarks and repeat trials |

## 20. Checklist Before Concluding a Bottleneck

Before editing code, confirm:

1. Does the profiled workload represent the real slow scenario?
2. Did you warm up, or explicitly document cold-start measurement?
3. Did profiling cover the exact target session and time window?
4. Did DBMS_PROFILER STOP/FLUSH succeed?
5. Did HPROF trace STOP and ANALYZE succeed?
6. Were run ID, trace ID, source version, and inputs recorded?
7. Did you distinguish total time from mean time per call?
8. In HPROF, did you compare self time against subtree time?
9. Did you inspect parent-child rows to see who calls the slow subprogram?
10. Does the SQL namespace account for most of the time?
11. If SQL is slow, did you inspect SQL_ID and the execution plan?
12. Do source line numbers match the profiled version?
13. Could compile mode, inlining, or warm-up skew the results?
14. Did you re-benchmark with profiling turned off?
15. After tuning, did the bottleneck shift somewhere else?

## 21. Summary

DBMS_PROFILER and DBMS_HPROF pinpoint expensive PL/SQL code from two complementary perspectives:

- **DBMS_PROFILER** records execution counts and line-level timings in PLSQL_PROFILER_RUNS, PLSQL_PROFILER_UNITS, and PLSQL_PROFILER_DATA, with timings stored in nanoseconds.
- **DBMS_HPROF** records the call hierarchy, call counts, self time, and subtree time while separating SQL execution time from PL/SQL execution time. Key analysis tables are DBMSHP_RUNS, DBMSHP_FUNCTION_INFO, and DBMSHP_PARENT_CHILD_INFO.
- DBMS_PROFILER excels at locating hot lines; HPROF excels at finding bottlenecks across call trees and separating SQL vs. PL/SQL cost.
- HPROF supports both file-based and table-based APIs depending on release. CREATE_TABLES creates tables on modern releases; DBMSHPTAB.SQL was deprecated in 18c.
- Profilers add overhead and depend on workload conditions. Warm-ups, representative inputs, stable environments, and unprofiled benchmarks are essential to interpret results accurately.
- When HPROF points to slow SQL, follow up with SQL_ID, DBMS_XPLAN, or SQL Trace. Never tune PL/SQL loops when the bottleneck sits inside the SQL engine.

Effective profiling is not about grabbing the biggest number and editing blindly. Define the right workload, read self/subtree or line timings in context, trace callers and embedded SQL, and validate every change with repeatable benchmarks.

## 22. Oracle Reference Documentation

- Oracle Database 26c PL/SQL Language Reference, “Profiling and Tracing PL/SQL Programs”: https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/profiling-and-tracing-pl-sql-programs.html
- Oracle Database 26c PL/SQL Packages and Types Reference, “DBMS_PROFILER”: https://docs.oracle.com/en/database/oracle/oracle-database/26/arpls/DBMS_PROFILER.html
- Oracle Database 26c Development Guide, “Using the PL/SQL Hierarchical Profiler”: https://docs.oracle.com/en/database/oracle/oracle-database/26/adfns/hierarchical-profiler.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_HPROF”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_HPROF.html

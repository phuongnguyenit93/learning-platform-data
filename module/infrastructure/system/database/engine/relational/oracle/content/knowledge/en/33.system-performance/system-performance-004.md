# SQL trace, DBMS_MONITOR and TKPROF

When a SQL statement runs slowly, the execution plan shows how Oracle organizes the operations, but it does not fully explain where time is being spent. SQL Trace adds a database call-level trace: parse, execute, fetch, and the associated wait events. DBMS_MONITOR enables or disables tracing by session, client identifier, service, module, and action. TKPROF reads the raw trace file and presents the metrics per SQL statement so operators can analyze them easily.

These three components address three different parts of the job:

- **SQL Trace:** records the execution and wait activity of a session/cursor.
- **DBMS_MONITOR:** determines the scope and timing of enabling/disabling tracing.
- **TKPROF:** formats and aggregates raw traces into a readable report.

Tracing is very useful when you need to know which CPU, I/O, parse, or wait time a SQL statement consumes. However, tracing introduces overhead and may contain SQL text, bind values, and sensitive data. You need to restrict the target scope, duration, and file access permissions properly.

## 1. What does SQL Trace record?

SQL Trace is a diagnostic mechanism of Oracle Database. It records SQL calls and certain related activities within the monitored session.

The main call types:

- **PARSE:** Oracle analyzes the SQL statement, checks syntax, objects, and privileges, and finds or creates a cursor.
- **EXEC:** the application requests execution of the cursor.
- **FETCH:** the application retrieves result rows from the cursor.
- **WAIT:** the session waits for an event such as reading a block, writing redo, a lock, or another resource.
- **STAT:** statistical information per operation/row source when plan statistics tracing is collected.
- **BINDS:** bind information can appear when appropriate bind tracing is enabled.

A SELECT statement can have one parse, one execute, and multiple fetches. If the application fetches page by page, the trace will show multiple fetch calls. If the application retrieves only part of the result, the total number of fetched rows may be lower than the number of rows the query could potentially return.

The trace can also record recursive SQL executed by the database on behalf of the application statement, such as dictionary operations, triggers, PL/SQL, or internal steps. The `dep` (depth) field in the raw trace helps distinguish some nested calls.

### 1.1 SQL Trace and wait events

When waits are enabled, the trace can record the times the session waits. Each wait typically includes the event name, duration, and several parameters describing the related object or block.

Examples of events you may encounter:

- **db file sequential read:** typically related to single-block reads, such as reading blocks via index/table access.
- **db file scattered read:** typically related to multiblock reads in certain scan types.
- **direct path read temp, direct path write temp:** TEMP access, which may be related to sort/hash spills.
- **log file sync:** the session waits for commit confirmation from redo.
- **enq: TX - row lock contention:** waiting on a row lock in certain transaction situations.
- **SQL*Net message from client:** the session is waiting for the client to send the next request; does not automatically mean the database is bottlenecked.

A wait event name is a clue, not a conclusion. You need to look at the wait count, total time, duration per wait, corresponding SQL/call, and application context.

### 1.2 Trace records by call, not just by SQL statement

A SQL statement can appear multiple times in a trace or have multiple cursors. You need to distinguish:

- A SQL statement.
- A parsed cursor.
- An execute call.
- Multiple fetch calls.
- Recursive SQL generated from the statement.
- Waits occurring within each call.

Therefore, you should not arbitrarily sum the times across lines. Use TKPROF to view call-level summaries, then return to the raw trace when you need to reconstruct the detailed sequence of events.

## 2. When should you use SQL Trace?

SQL Trace is suitable when you need to answer specific questions:

- Is the SQL consuming CPU or wait time?
- Is the time spent in parse, execute, or fetch?
- Does the SQL statement incur many parses or library cache misses?
- Are there many physical reads or consistent gets?
- Which event does the session wait on and for how long?
- Which SQL statements does an application request invoke?
- Do triggers, PL/SQL, or recursive SQL contribute significantly?
- How do two runs of the same SQL differ in call count, waits, or row count?

SQL Trace is especially useful when an issue occurs only for a specific session, user, service, or business flow. When you already have the SQL_ID and runtime statistics but still do not know the parse/execute/fetch sequence or detailed waits, a trace can provide additional evidence.

You should not enable tracing database-wide just because one application screen is slow. Identify a session, client identifier, or module/action narrow enough to collect data over a short period.

## 3. How does DBMS_MONITOR manage tracing?

DBMS_MONITOR is an Oracle package providing procedures to enable and disable SQL Trace by scope.

Commonly used scopes:

| Scope | How to identify | When appropriate |
|---|---|---|
| Session | SID and SERIAL# | Investigating a specific session |
| Client identifier | CLIENT_IDENTIFIER | Tracking a logical user/request across a connection pool |
| Service/module/action | Service, module, action | Tracking an application business flow |
| Database | Entire database/instance via the corresponding API | Controlled investigation when a broad scope is needed |

Common trace procedures:

- **DBMS_MONITOR.SESSION_TRACE_ENABLE** and **SESSION_TRACE_DISABLE**.
- **DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE** and **CLIENT_ID_TRACE_DISABLE**.
- **DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE** and **SERV_MOD_ACT_TRACE_DISABLE**.
- **DBMS_MONITOR.DATABASE_TRACE_ENABLE** and **DATABASE_TRACE_DISABLE**.

Parameter names and support capabilities may vary by release. Check the package specification of the running version before putting commands into an operational runbook.

## 4. Enabling trace for the current session

The simplest approach is to enable tracing in the very session reproducing the issue.

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    waits => TRUE,
    binds => FALSE
  );
END;
/
~~~

Then perform the exact operation or SQL statement you want to monitor. When finished, disable tracing:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE;
END;
/
~~~

In the example:

- **waits => TRUE** requests recording wait events.
- **binds => FALSE** does not record bind values; this is a safer default for many situations.
- You can enable binds in a controlled test if you truly need to analyze bind behavior and have handled data access permissions.

If you forget to disable tracing, the session continues generating trace files for subsequent activities. This makes the file larger and makes it harder to isolate the scope of the issue.

### 4.1 Enabling trace for another session

A DBA can enable tracing for a session using SID and SERIAL#:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    session_id => 123,
    serial_num => 456,
    waits      => TRUE,
    binds      => FALSE
  );
END;
/
~~~

After completion, disable tracing on the same session:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE(
    session_id => 123,
    serial_num => 456
  );
END;
/
~~~

A SID can be reused after a session ends. Therefore, check SERIAL# as well and confirm the exact session right before enabling tracing. In RAC, you need to identify the instance hosting the session and use the appropriate instance parameter if the release's package procedure supports it.

You can look up the session using dynamic views when you have privileges:

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       service_name,
       module,
       action,
       client_identifier
FROM v$session
WHERE username = 'APP_USER';
~~~

In a RAC environment, use GV$SESSION and add INST_ID to distinguish sessions across instances.

## 5. Tracing by client identifier

Applications using a connection pool often reuse a single database session across multiple requests. Enabling trace by SID may end up tracing the next request if the connection is returned to the pool and reused.

Client identifier helps identify a logical user or request independently of the physical session. The application needs to set the identifier on the connection before processing the request.

Example in the application session:

~~~sql
BEGIN
  DBMS_SESSION.SET_IDENTIFIER('ORDER_SUPPORT_501');
END;
/
~~~

The DBA enables tracing for that identifier:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
    client_id => 'ORDER_SUPPORT_501',
    waits     => TRUE,
    binds     => FALSE
  );
END;
/
~~~

When finished:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_DISABLE(
    client_id => 'ORDER_SUPPORT_501'
  );
END;
/
~~~

Client identifier can be used to group activities of the same logical client across multiple sessions, depending on how the application manages and assigns the identifier.

The application must set the identifier at the right time and clear or replace it when the connection is returned to the pool. If an old identifier remains, subsequent requests may be misattributed and the trace may include unrelated activity.

The SET_IDENTIFIER call in the example must run on the application session being identified. Running it in the DBA session does not cause other application sessions to automatically carry that identifier.

## 6. Tracing by service, module, and action

DBMS_APPLICATION_INFO allows the application to label a session with module and action. This is a useful way to distinguish business flows sharing the same service.

For example, the application sets module/action:

~~~sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'OrderService',
    action_name => 'CreateOrder'
  );
END;
/
~~~

When the action completes, the application can update to a new action or clear module/action according to the system's instrumentation conventions:

~~~sql
BEGIN
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => NULL,
    action_name => NULL
  );
END;
/
~~~

The DBA can enable tracing for the exact service, module, and action:

~~~sql
BEGIN
  DBMS_MONITOR.SERV_MOD_ACT_TRACE_ENABLE(
    service_name => 'APP_SERVICE',
    module_name  => 'OrderService',
    action_name  => 'CreateOrder',
    waits        => TRUE,
    binds        => FALSE
  );
END;
/
~~~

Disable tracing after collection:

~~~sql
BEGIN
  DBMS_MONITOR.SERV_MOD_ACT_TRACE_DISABLE(
    service_name => 'APP_SERVICE',
    module_name  => 'OrderService',
    action_name  => 'CreateOrder'
  );
END;
/
~~~

The service name must be the database service that the application actually uses. Module/action must match the values assigned by the application; a single character mismatch can cause no sessions to match.

This is often the right scope when an issue is tied to a specific endpoint or task. For example, you can trace CreateOrder while SearchOrders or CancelOrder actions continue running normally.

### 6.1 Instrumentation in the application

For service/module/action to be useful, the application must assign them consistently:

- Service identifies the connection group or workload.
- Module identifies the application component.
- Action identifies the operation being processed.
- Client identifier identifies the logical user or request when needed.

Instrumentation should be set at request or business boundaries and reset upon completion. With a connection pool, ensure the context of a previous request does not leak into the next request.

You can view the current values in V$SESSION:

~~~sql
SELECT sid,
       serial#,
       service_name,
       module,
       action,
       client_identifier
FROM v$session
WHERE username = 'APP_USER';
~~~

## 7. Getting the trace file path

Oracle stores diagnostic traces in the Automatic Diagnostic Repository (ADR). Trace files are usually located under the database or instance diagnostic directory.

In the session being traced, you can check the default path:

~~~sql
SELECT name, value
FROM v$diag_info
WHERE name IN ('Diag Trace', 'Default Trace File');
~~~

- **Diag Trace** indicates the ADR trace directory.
- **Default Trace File** indicates the default trace file of the current session.

If tracing was enabled for another session, the Default Trace File value in the DBA session is not the target session's file. In that case, you need to identify the corresponding process via session/instance information and locate the trace file in ADR. The ADRCI utility also supports listing and managing diagnostic files.

In RAC, each instance has its own ADR home. The trace of a session running on a given instance is written to that instance's corresponding ADR. Do not look for the file only in the directory of the currently connected instance if the target session is on another instance.

With parallel execution or certain multi-process operations, there may be multiple related trace files. You need to identify the relevant processes and sessions before concluding that a single file contains the entire trace.

## 8. How is a raw trace file structured?

A raw trace is detailed data and is not designed to be read as a final report. A file may contain records such as:

- PARSING IN CURSOR: cursor information and SQL text.
- PARSE: metrics for the parse call.
- EXEC: metrics for the execute call.
- FETCH: metrics for the fetch call.
- WAIT: wait event and wait duration.
- STAT: operation statistics when plan statistics are available.
- BINDS: bind information if bind tracing is enabled.

An illustrative WAIT line might look like:

~~~text
WAIT #140012345 nam='db file sequential read' ela=1250 p1=7 p2=12345 p3=1
~~~

This is only a simplified example to recognize the structure. The `ela` value in raw traces is typically recorded in microseconds in the corresponding wait records; check the trace format for your specific release and record type.

A PARSE/EXEC/FETCH record typically has fields representing CPU, elapsed, physical reads, consistent gets, current gets, row counts, and timestamps. Cursor IDs in the trace help link calls to the parsed SQL statement.

### 8.1 Reading the sequence of events

The raw trace preserves the timing and relative order of calls/waits. When you need to know what a session waited on between execute and fetch, the raw trace provides more detailed evidence than an aggregated report.

For example, a request might:

1. Parse cursor.
2. Execute SQL.
3. Wait to read blocks.
4. Fetch a batch of rows.
5. Wait for client.
6. Fetch the next batch.
7. Close cursor.

TKPROF can aggregate calls into one report section per SQL. If you need to build a detailed timeline or distinguish individual waits, go back to the raw trace.

### 8.2 Recursive SQL

A trace may contain SQL executed by the database inside a call. These statements can come from triggers, PL/SQL, dictionary access, or internal operations. The `depth` field in the trace helps identify nested relationships.

When running TKPROF with `sys=no`, statements issued by SYS can be excluded from the report. This does not mean all application recursive SQL disappears. When you need to analyze internal activity, keep the raw trace and consider how to filter it.

## 9. What does TKPROF do?

TKPROF is a utility included with Oracle Database/Oracle Client tools to convert raw SQL Trace files into text-based reports.

It helps:

- Group parse, execute, and fetch calls by SQL.
- Display call counts and CPU/elapsed metrics.
- Display physical reads, consistent gets, and current gets.
- Display the number of rows processed.
- Sort SQL by criteria such as elapsed or CPU.
- Display wait event summaries if the appropriate option is chosen.
- Optionally generate an execution plan via the EXPLAIN option, though this plan is not definitive proof of the original plan that ran.

TKPROF does not enable tracing. It only processes trace files already generated by SQL Trace.

## 10. Running TKPROF

General syntax:

~~~text
tkprof input_trace_file output_report_file [options]
~~~

Example on Windows:

~~~text
tkprof "D:\oracle\trace\orders_app.trc" "D:\oracle\trace\orders_app.prf" sort=exeela,fchela sys=no waits=yes
~~~

Example on Linux:

~~~bash
tkprof /u01/app/oracle/diag/rdbms/db/DB/trace/orders_app.trc \
       /tmp/orders_app.prf \
       sort=exeela,fchela sys=no waits=yes
~~~

TKPROF is usually located in the `bin` directory of the Oracle Home. Run it from an Oracle Home that includes the utility or configure `PATH` to point to the correct directory.

Some common options:

| Option | Meaning |
|---|---|
| sort=... | Sort SQL by one or more metrics |
| sys=yes/no | Whether to include SQL issued by SYS in the report |
| waits=yes/no | Whether to include the wait statistics section in the report |
| aggregate=yes/no | Whether to aggregate matching cursors/calls per TKPROF rules |
| print=n | Limit the number of statements printed after sorting |
| explain=user/password | Request TKPROF to explain SQL using the provided schema |
| table=... | Specify the plan table when using EXPLAIN, depending on environment |

Specific sort key names and options should be verified against the TKPROF documentation for the Oracle Home in use. For example, `exeela` typically sorts by execute elapsed time, while `fchela` sorts by fetch elapsed time.

### 10.1 Why sort by execute and fetch?

A query can spend most of its time in execute or fetch:

- Execute consumes significant CPU or waits before returning the first row.
- Fetch takes time because it has to read and transmit many rows.
- Parse takes time due to hard parsing or poor cursor sharing.

Sorting by `exeela` and `fchela` helps find statements with high elapsed time in the two main phases. You can sort by CPU, physical reads, or consistent gets when the investigation focuses on a specific resource.

There is no single best sort order for every incident. Choose the metric according to the hypothesis being tested.

### 10.2 Be cautious with the EXPLAIN option

The `explain=user/password` option instructs TKPROF to run `EXPLAIN PLAN` for the SQL using the provided schema at report generation time. That plan may differ from the actual plan that ran because statistics, binds, schema, optimizer environment, and parse time differ.

Do not use a plan generated by TKPROF's EXPLAIN option to claim it was the original execution plan during the trace. To verify the plan that actually ran, retrieve the cursor plan from DBMS_XPLAN or appropriate runtime plan sources.

In addition, do not pass plaintext passwords on the command line on multi-user systems where shell history or process lists may store/display parameters. You can omit the EXPLAIN option when you only need call statistics and retrieve the plan using a separate tool.

## 11. Understanding columns in a TKPROF report

A TKPROF report typically presents call lines such as Parse, Execute, and Fetch, with common columns:

| Column | Meaning |
|---|---|
| Count | Number of calls of that type |
| CPU | Total CPU time of the calls |
| Elapsed | Total elapsed time of the calls |
| Disk | Number of physical reads recorded |
| Query | Consistent gets |
| Current | Current-mode gets |
| Rows | Number of rows processed/returned in the corresponding call |

Each call type must be read in context:

- **Parse:** number of parses, CPU/elapsed, and library cache misses if reported.
- **Execute:** number of executions, CPU, elapsed, and I/O/gets metrics incurred during execute.
- **Fetch:** number of fetches, rows returned, and resources consumed during fetch.

A SELECT typically has multiple fetch calls. The Fetch Count can be high because the client retrieves data in batches. A high Count by itself does not prove an error; you must look at row count, time, and how the client fetches.

### 11.1 CPU and elapsed

CPU is the CPU time used for the calls. Elapsed is the wall-clock time elapsed during the calls. Elapsed generally includes wait time within the call.

If elapsed is much greater than CPU, the difference may relate to wait events or time not running on CPU. Check the wait statistics section and the raw trace to identify specific events.

Do not simply subtract CPU from elapsed and attribute the entire difference to a single wait event without checking. You need to consider recorded waits, scheduling time, nested calls, and how statistics are aggregated.

### 11.2 Disk, Query, and Current

- **Disk:** physical reads.
- **Query:** consistent gets, typically reflecting logical reads in consistent mode.
- **Current:** current-mode gets, typically involving blocks accessed in current mode to read/write current data.

A SQL statement with low Disk but high Query can still consume significant CPU and buffer activity. A SQL statement with high Current may relate to DML operations or activities requiring current block access.

Do not look only at Disk and conclude that a SQL statement causes no internal I/O load. Buffer gets are also a critical resource.

### 11.3 Rows

Rows indicates the number of rows processed or returned in the calls as reported by TKPROF. For SELECT, total rows fetched may depend on whether the client retrieved the entire result set. For DML, rows affected should be read alongside execute count and transaction behavior.

## 12. Reading the wait statistics section

When waits are enabled and TKPROF is run with `waits=yes`, the report can display a summary of wait events attached to the SQL/calls.

Examples of categories to watch:

- User I/O: waiting to read/write blocks.
- Concurrency: waiting on concurrent resource contention.
- Application: waits caused by the application or locks.
- Commit: waits related to commit/redo.
- Network: waiting on communication with the client or a database link.
- Configuration/Administrative: waits related to configuration or administration.

Do not look only at the event name. Look at the wait count and total time. An event occurring many times with very short duration each time may be less important than an event with a few long waits.

For example:

- Many `db file sequential read` waits may indicate many single-block reads, but you need to inspect total time and the access path.
- High `log file sync` may relate to overly frequent commits or redo latency; you need to analyze the transaction pattern and redo subsystem.
- `enq: TX - row lock contention` requires identifying the lock-holding session and related transactions.
- `SQL*Net message from client` usually indicates the database is waiting for the client to send more work; distinguish idle waits from SQL processing time.

The raw trace is useful for seeing whether a wait occurred before or after a given call. TKPROF helps summarize, but can lose timeline details.

## 13. Example end-to-end workflow for a single session

Suppose a support engineer can reproduce the order creation operation in a dedicated session.

### Step 1: Identify the session

~~~sql
SELECT sid, serial#, username, service_name, module, action
FROM v$session
WHERE username = 'APP_USER';
~~~

Record SID, SERIAL#, service, and instance if using RAC.

### Step 2: Enable trace with waits

In the DBA session:

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_ENABLE(
    session_id => 123,
    serial_num => 456,
    waits      => TRUE,
    binds      => FALSE
  );
END;
/
~~~

### Step 3: Reproduce the operation once

Have the application run the exact operation under investigation. Record the start/end timestamps and request identifier to correlate with the trace.

### Step 4: Disable trace immediately after reproduction

~~~sql
BEGIN
  DBMS_MONITOR.SESSION_TRACE_DISABLE(
    session_id => 123,
    serial_num => 456
  );
END;
/
~~~

### Step 5: Locate the trace file

Use ADR to find the file for the traced process/session. If you are in the traced session itself, you can query V$DIAG_INFO to get Default Trace File.

### Step 6: Generate the TKPROF report

~~~text
tkprof "D:\oracle\trace\session_123.trc" "D:\oracle\trace\session_123.prf" sort=exeela,fchela sys=no waits=yes
~~~

### Step 7: Read the report and return to the raw trace

Find statements with high elapsed, CPU, gets, or waits. For key statements, retrieve the relevant SQL_ID/plan, check the runtime plan using DBMS_XPLAN, and read the raw trace to understand the call/wait sequence.

This workflow keeps the trace scoped to one session and one reproduction, making it easy to tie the report to the actual event.

## 14. Example tracking a request across a connection pool

With a connection pool, SID can be reused. To track a logical request, the application should set a client identifier before processing.

In the application:

~~~sql
BEGIN
  DBMS_SESSION.SET_IDENTIFIER('SUPPORT_REQ_20261114_001');
  DBMS_APPLICATION_INFO.SET_MODULE(
    module_name => 'OrderApi',
    action_name => 'CreateOrder'
  );
END;
/
~~~

The DBA enables tracing by client identifier:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_ENABLE(
    client_id => 'SUPPORT_REQ_20261114_001',
    waits     => TRUE,
    binds     => FALSE
  );
END;
/
~~~

After the request completes, the DBA disables tracing:

~~~sql
BEGIN
  DBMS_MONITOR.CLIENT_ID_TRACE_DISABLE(
    client_id => 'SUPPORT_REQ_20261114_001'
  );
END;
/
~~~

The application must clear identifier/module/action before returning the connection to the pool, or update them for the next request according to a consistent convention. Otherwise, traces may accidentally merge requests or attribute activity to the wrong client.

This is a conceptual instrumentation example. In practice, the timing of enabling trace must be coordinated so as not to miss the portion of the request being measured; if enabled after the request has already finished, the trace cannot reconstruct calls that already occurred.

## 15. Trcsess when there are multiple trace files

Some situations, particularly RAC, parallel execution, or tracking a single client across multiple sessions, can produce multiple trace files. The `trcsess` utility can filter/merge trace files by session, client identifier, service, module, or action depending on supported options.

General syntax:

~~~text
trcsess [output=output_file] [session=...] [clientid=...] [service=...] [module=...] [action=...] trace_files
~~~

After creating the filtered/merged trace file, you can run TKPROF on that file:

~~~text
tkprof "D:\oracle\trace\request.trc" "D:\oracle\trace\request.prf" sort=exeela,fchela waits=yes sys=no
~~~

Check `trcsess` help in your specific Oracle Home to confirm how to specify filters and wildcards. Do not merge all database trace files if you only need one request, as the report will contain lots of unrelated activity.

## 16. Common mistakes when using SQL Trace and TKPROF

| Mistake | Consequence |
|---|---|
| Enabling trace database-wide for a single SQL | Generates massive trace volume and increases unnecessary overhead |
| Forgetting to disable trace | Session continues writing files and pollutes the data |
| Enabling trace only for SID in a connection pool | May trace the wrong request when the session is reused |
| Not recording both SID and SERIAL# | Risks tracing the wrong session if the SID is reused |
| Enabling binds by default for every session | Increases trace data and may expose sensitive information |
| Reading only TKPROF without keeping the raw trace | Loses timeline detail and some wait context |
| Treating EXPLAIN in TKPROF as the original plan | Plan explained at report time may differ from the plan that ran |
| Sorting only by elapsed | May miss SQL consuming high CPU or logical reads |
| Treating every wait as a database error | Some waits are normal states or caused by the client |
| Merging multiple requests into one trace | Hard to determine which statements belong to the investigated request |
| Not recording reproduction timestamps | Hard to correlate the trace with application logs |
| Sharing raw traces publicly | May expose SQL text, binds, and sensitive metadata |

## 17. Overhead, access permissions, and data protection

SQL Trace is a diagnostic tool and should not be left enabled indefinitely on all sessions. The level of overhead depends on call volume, amount of wait/bind data recorded, workload, and environment. Bind tracing typically generates additional data and can record sensitive values.

An operationally safe workflow:

1. Define the question to answer before enabling trace.
2. Choose the smallest scope: session, client identifier, or service/module/action.
3. Record timestamps and request identifiers.
4. Start the trace right before reproduction.
5. Stop the trace immediately after collecting enough data.
6. Check file size and generate the report.
7. Retain files according to your organization's retention policy.
8. Restrict who can read raw traces and reports.
9. Mask or remove bind values and sensitive data before sharing.
10. Delete diagnostic data once the approved retention period expires.

To trace other sessions or service/module/action, operators need appropriate privileges. Do not grant broad DBA privileges just so an application can enable tracing on arbitrary sessions itself. Use operational accounts and least privilege according to system policy.

## 18. SQL Trace compared to other observability tools

Different tools provide different perspectives:

| Tool | Primary perspective | When useful |
|---|---|---|
| DBMS_XPLAN | Execution plan structure and runtime row-source stats if available | Analyzing access paths, cardinality, and operations |
| SQL Trace | Parse/execute/fetch and waits by session/call | Investigating a specific execution or group of sessions |
| TKPROF | Aggregated report from raw trace | Ranking SQL and comparing call statistics |
| V$SQL | Statistics for cursors currently in the shared pool | Finding SQL consuming cumulative resources |
| SQL Monitor | Detailed execution progress of monitor-eligible SQL | Tracking long-running, parallel, or complex SQL operations |
| AWR/ASH | History and activity samples over time | Investigating regressions or historical workload when properly licensed |

No single tool replaces all the others. DBMS_XPLAN answers questions about the plan; trace shows calls and waits; TKPROF summarizes the trace; AWR/ASH helps look back at workload over a broader timeframe.

When investigating a specific request, SQL Trace often provides useful detail. When you need to find load-causing SQL across the whole system, starting from cursor statistics or workload-level tools can be more effective before tracing a representative case.

## 19. Operational checklist

Before enabling trace:

- [ ] Defined the investigation question and required trace scope.
- [ ] Identified the exact session or client identifier.
- [ ] If using SID, confirmed both SERIAL# and instance.
- [ ] If using service/module/action, verified matching instrumentation.
- [ ] Decided whether recording bind values is truly necessary.
- [ ] Identified who is authorized to read trace files.

During collection:

- [ ] Recorded start and end timestamps.
- [ ] Reproduced a single request or target operation group.
- [ ] Monitored trace file size.
- [ ] Disabled trace immediately after sufficient data was collected.

After collection:

- [ ] Located the correct trace file in ADR.
- [ ] Ran TKPROF with appropriate sort keys.
- [ ] Checked parse, execute, fetch, and wait statistics.
- [ ] Returned to the raw trace when a timeline was needed.
- [ ] Verified the execution plan using DBMS_XPLAN.
- [ ] Correlated with application logs and request identifiers.
- [ ] Protected bind values and sensitive data.
- [ ] Retained or deleted files according to the retention policy.

## 20. Conclusion

SQL Trace records the parse, execute, fetch, and wait activity of monitored sessions. DBMS_MONITOR helps limit tracing by session, client identifier, or service/module/action. TKPROF converts raw traces into reports showing call counts, CPU, elapsed, physical reads, consistent gets, current gets, rows, and wait events.

When investigating performance, start from a specific request or session, enable tracing for a short duration, disable it immediately after reproduction, and read TKPROF and the raw trace alongside the actual execution plan. Combining these sources helps distinguish SQL work, wait time, and application behavior, enabling changes backed by verifiable evidence.

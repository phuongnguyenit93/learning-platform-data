# sys Schema and Views for Diagnostics

In MySQL, the sys schema is a tooling layer that exposes operational data from Performance Schema and portions of INFORMATION_SCHEMA metadata through human-readable views, functions, and stored procedures. Instead of manually joining multiple event tables, operators can start with views such as statement_analysis, processlist, schema_table_statistics, schema_index_statistics, waits_global_by_latency, or innodb_lock_waits to locate areas needing investigation.

The sys schema is neither an independent monitoring agent nor a long-term historical repository. Most of its metrics are aggregated from Performance Schema, so diagnostic quality depends on whether Performance Schema is enabled and whether instruments and consumers are appropriately configured. Counters can also be reset or lost when the server restarts.

This lesson in the DATABASE_MYSQL scope covers understanding the sys schema architecture, selecting the right view for each operational question, reading query and I/O metrics, finding lock waits, evaluating indexes and the buffer pool, understanding access privileges and metric limitations, and building a repeatable diagnostic workflow.

## 1. What Problem Does the sys Schema Solve?

Performance Schema provides detailed event data on statements, stages, waits, mutexes, file I/O, table I/O, transactions, and threads. This data is powerful, though it often requires JOINs, filtering, and formatting.

The sys schema places a layer of views and routines on top of those data sources. Its goal is to quickly answer questions such as:

- Which SQL statements consume the most total time?
- Which SQL statements have high average or p95 latency?
- Which schemas or tables see heavy reads/writes?
- Which indexes show signs of low or no usage?
- Which sessions are long-running or waiting on locks?
- Which transactions are blocking other transactions?
- Which wait types account for the most time?
- Which files or tablespaces have high I/O?
- Which schemas/tables hold pages in the buffer pool?
- Which hosts or users generate the most load?

For example, instead of aggregating Performance Schema digest tables manually, you can start with:

~~~
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    rows_examined,
    rows_sent
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
~~~

This view helps identify statement groups worth investigating. It does not by itself prove an SQL statement is the sole cause of slowness; you must examine execution plans, input data, concurrency, and timing context.

## 2. Where Does the sys Schema Sit in the Observability Architecture?

The data flow can be visualized as follows:

~~~text
Application / client
       |
       v
MySQL server
       |
       +-----------------------------+
       |                             |
       v                             v
Performance Schema             INFORMATION_SCHEMA
(events, waits, counters,       (schema metadata,
threads, statements, I/O)        tables, columns, indexes)
       |                             |
       +--------------+--------------+
                      |
                      v
                  sys schema
        (views, functions, procedures)
                      |
                      v
         DBA / developer / monitoring
~~~

The sys schema mainly provides a more convenient reading layer. It does not replace Performance Schema; when deep investigation is needed, you can still query the underlying tables in performance_schema.

### 2.1. The sys Schema Does Not Generate Telemetry on Its Own

If statement instrumentation or its corresponding consumer is disabled, statement summary views may lack data. If file I/O instruments are disabled, I/O views cannot provide complete metrics.

Therefore, when a view returns empty results or zero values, do not hastily conclude the server has no activity. Check:
- Whether Performance Schema is enabled.
- Whether the required instruments are enabled.
- Whether the required consumers are enabled.
- Whether buffer/summary table sizes are sufficient.
- Whether the server recently restarted or counters were reset.
- Whether the current account has sufficient privileges to read the data.

### 2.2. Is the sys Schema Historical Data?

No. Most Performance Schema metrics are in-memory runtime counters, typically accumulated since server startup or the last reset. Upon restart, many summaries reinitialize. When summaries are reset, the observation window changes as well.

If you need daily/weekly/monthly history, scrape periodically from a monitoring platform or store snapshots in a separate telemetry system. Do not treat the sys schema as durable historical storage.

## 3. Checking the sys Schema and Version

Check the server version:

~~~
SELECT
    VERSION() AS mysql_version,
    @@version_comment AS distribution;
~~~

Check the schema:

~~~
SHOW DATABASES LIKE 'sys';
~~~

List views:

~~~
SHOW FULL TABLES FROM sys
WHERE Table_type = 'VIEW'
ORDER BY Tables_in_sys;
~~~

List routines:

~~~
SHOW PROCEDURE STATUS
WHERE Db = 'sys';

SHOW FUNCTION STATUS
WHERE Db = 'sys';
~~~

View a view's definition:

~~~
SHOW CREATE VIEW sys.statement_analysis;
~~~

View a procedure's definition:

~~~
SHOW CREATE PROCEDURE sys.diagnostics;
~~~

The sys schema is built into modern MySQL releases, but the exact set of views, columns, and routines can vary by version. Do not rely on view names from an old article and assume every server has the exact same schema. Before writing dashboards or scripts, verify objects and columns against your actual deployment version.

## 4. Key View Groups by Operational Question

| Question | Commonly Used Views |
|---|---|
| Which statements consume the most latency? | statement_analysis |
| Which statements have errors or warnings? | statements_with_errors_or_warnings |
| Which statements perform full table scans? | statements_with_full_table_scans |
| Which statements create temporary tables? | statements_with_temp_tables |
| Which statements have runtimes in the high percentile? | statements_with_runtimes_in_95th_percentile |
| Which sessions are active? | processlist, session |
| Which hosts generate the most load? | host_summary, host_summary_by_statement_latency |
| Which users generate the most load? | user_summary, user_summary_by_statement_latency |
| Which tables have heavy logical I/O? | schema_table_statistics |
| Which indexes have read/write activity? | schema_index_statistics |
| Which indexes show no recorded usage? | schema_unused_indexes |
| Which indexes appear redundant? | schema_redundant_indexes |
| Which InnoDB transactions are waiting on locks? | innodb_lock_waits |
| Which metadata/table locks are waiting? | schema_table_lock_waits |
| Which wait events have high latency? | waits_global_by_latency |
| Which files have heavy I/O? | io_global_by_file_by_bytes, io_global_by_file_by_latency |
| Which tables hold pages in the buffer pool? | innodb_buffer_stats_by_table |

This is a starting point, not an exhaustive list. Each view has its own aggregation logic and data criteria. Use SHOW CREATE VIEW to inspect the actual data sources and columns.

## 5. processlist and session: Who Is Running or Waiting?

sys.processlist provides a more detailed look at threads/sessions than a basic process list. sys.session focuses on foreground sessions.

Example:

~~~
SELECT
    conn_id,
    user,
    db,
    command,
    state,
    time,
    current_statement,
    statement_latency,
    lock_latency,
    rows_examined,
    rows_sent,
    tmp_tables,
    tmp_disk_tables,
    full_scan
FROM sys.processlist
ORDER BY statement_latency DESC;
~~~

These fields help answer:
- Which statement is the session running?
- How long has the statement been running?
- Is it waiting on locks?
- How many rows has it examined?
- Is it creating temporary tables on disk?
- Are there signs of a full scan?

Exact column names may vary by sys schema version. If a sample query reports an unknown column error, use DESCRIBE sys.processlist and SHOW CREATE VIEW to adjust for your version.

### 5.1. Distinguishing Connection ID and Thread ID

The MySQL connection ID is typically the processlist ID seen by clients. Performance Schema uses an internal THREAD_ID to link thread events.

A session can be mapped via performance_schema.threads:

~~~
SELECT
    PROCESSLIST_ID,
    THREAD_ID,
    NAME,
    TYPE,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE
FROM performance_schema.threads
WHERE PROCESSLIST_ID IS NOT NULL;
~~~

When joining data from sys with Performance Schema, use the matching ID type. Do not compare CONNECTION_ID() directly with THREAD_ID without mapping.

### 5.2. Sleeping Sessions Are Not Necessarily Errors

A connection in the Sleep state may belong to a connection pool waiting for the next request. What you should check is:
- Number of sleeping connections.
- Idle duration.
- Whether an idle session holds an open transaction.
- Whether the pool is keeping more connections than needed.
- Whether the connection holds metadata/row locks.

A Sleep session with an open transaction is far more concerning than an idle connection with no transaction.

## 6. statement_analysis: Finding the Most Time-Consuming SQL

The sys.statement_analysis view aggregates statements by digest, grouping multiple SQL queries with different literals into the same normalized statement form.

Example:

~~~
SELECT
    db,
    query,
    exec_count,
    err_count,
    warn_count,
    total_latency,
    avg_latency,
    max_latency,
    rows_sent,
    rows_examined,
    tmp_tables,
    tmp_disk_tables,
    rows_sorted,
    full_scan,
    first_seen,
    last_seen
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
~~~

Key metrics:

| Metric | Interpretation |
|---|---|
| exec_count | Aggregated execution count |
| total_latency | Cumulative total execution time |
| avg_latency | Average latency |
| max_latency | Maximum recorded latency |
| rows_examined | Rows read/examined |
| rows_sent | Rows returned to the client |
| tmp_tables | Number of temporary tables |
| tmp_disk_tables | Temporary tables spilled to disk |
| rows_sorted | Rows sorted |
| full_scan | Full scan indicator as aggregated by the view |

A statement with high total_latency may simply be called very frequently. A statement with high avg_latency can be slow even with low execution counts. Inspect total latency, execution count, average latency, max latency, and rows examined together.

### 6.1. Rows Examined vs. Rows Sent

If rows_examined is very large while rows_sent is small, the query may be reading large amounts of data to return few results. This is a signal to check:
- Whether predicates use an index.
- Whether index column ordering matches the query.
- Whether conditions wrap indexed columns in functions.
- Whether cardinality and statistics are accurate.
- Whether input data can be narrowed or a covering index used.

No single rows_examined/rows_sent threshold fits every query. Analytical reporting queries may legitimately read many rows; primary-key lookups usually should not.

### 6.2. Total Latency Is Not CPU Time

Latency in Performance Schema can include both wait time and execution time depending on instrumentation. It does not equal pure CPU time. High query latency can stem from:
- Lock waits.
- I/O waits.
- Metadata lock waits.
- Other resource waits.
- Heavy CPU execution.
- Transferring large result sets over the network.

Combine statement views with wait views, lock views, and OS metrics.

## 7. Finding Statements with Errors, Full Scans, and Temporary Tables

### 7.1. Errors and Warnings

~~~
SELECT *
FROM sys.statements_with_errors_or_warnings
ORDER BY last_seen DESC
LIMIT 20;
~~~

Use this view to find statement groups with errors or warnings recorded by Performance Schema. Then inspect the query digest, timestamps, and error counts. Not all application errors are fully represented if instrumentation or retention is insufficient.

### 7.2. Full Table Scans

~~~
SELECT *
FROM sys.statements_with_full_table_scans
ORDER BY rows_examined DESC
LIMIT 20;
~~~

Full scans are not always bad. If a table is small or a query reads most of the table, a table scan can be cheaper than index lookups. Compare:
- Table size.
- Estimated and actual row counts.
- Predicate selectivity.
- Random I/O cost.
- EXPLAIN plan.
- Execution frequency.

### 7.3. Temporary Tables

~~~
SELECT *
FROM sys.statements_with_temp_tables
ORDER BY disk_tmp_tables DESC
LIMIT 20;
~~~

In-memory temporary tables can be normal. Temporary tables spilling to disk can increase latency, especially when intermediate datasets are large or queries execute frequently.

Check whether queries use GROUP BY, DISTINCT, ORDER BY, UNION, or intermediate operations. Do not immediately increase every buffer limit; first inspect the query shape and intermediate data volume.

### 7.4. Runtimes in the High Percentile

~~~
SELECT *
FROM sys.statements_with_runtimes_in_95th_percentile
ORDER BY avg_latency DESC
LIMIT 20;
~~~

This percentile view helps uncover statement groups with high tail latency. Good average latency does not guarantee good p95/p99 latency; some requests may be slow due to locks, cache misses, large payloads, or contention.

## 8. Digests and Normalized Queries

Performance Schema normalizes statements into digests to aggregate SQL queries that share the same structure but differ in literals.

Example:

~~~
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 202;
~~~

These can be grouped into the same digest pattern, depending on statement normalization.

Digests are useful for:
- Identifying common query patterns.
- Estimating total cost by statement class.
- Finding high-frequency query shapes.
- Tracking workload shifts over time.
- Avoiding storing sensitive literals in dashboards.

Digests do not retain every detail of individual executions. If only a single parameter value causes data skew, digest aggregation can mask the outlier. When investigating parameter-sensitive queries, perform controlled sampling at the application layer or via the slow log.

### 8.1. Digest Capacity and Dropped Statements

Performance Schema limits the number of digests retained concurrently. If a workload has very many distinct query shapes, some digests may not be stored or may fall into fallback buckets depending on configuration.

Check related variables:

~~~
SHOW VARIABLES LIKE 'performance_schema_max_digest_length';
SHOW VARIABLES LIKE 'performance_schema_digests_size';
~~~

Do not increase capacity without estimating memory and workload impact. Changing sizing parameters may require a server restart depending on the variable.

## 9. Aggregating Load by Schema and Table

sys.schema_table_statistics aggregates read/write activity per table:

~~~
SELECT
    table_schema,
    table_name,
    rows_fetched,
    fetch_latency,
    rows_inserted,
    insert_latency,
    rows_updated,
    update_latency,
    rows_deleted,
    delete_latency,
    total_latency
FROM sys.schema_table_statistics
ORDER BY total_latency DESC
LIMIT 30;
~~~

This can be used to find:
- Heavily read tables.
- Tables with high read latency.
- Heavily written tables.
- Tables with high total latency.
- Tables with unusual operation ratios.

Metrics depend on table I/O instrumentation and accumulation duration. A large or heavily accessed table may rank at the top even when all its queries are optimal. Normalize by workload and request rate when comparing.

### 9.1. schema_table_statistics_with_buffer

This view adds buffer pool visibility to table activity. It can be used to examine pages in the buffer pool, hit/allocated ratios, or related information depending on version definitions.

~~~
SELECT *
FROM sys.schema_table_statistics_with_buffer
ORDER BY total_latency DESC
LIMIT 20;
~~~

Because column structures can differ by version, run DESCRIBE before adding it to a dashboard. A high overall buffer pool hit ratio does not guarantee every query is fast; a hot table may suffer misses while other tables hold unneeded pages.

## 10. schema_index_statistics: How Are Indexes Used?

~~~
SELECT
    table_schema,
    table_name,
    index_name,
    rows_selected,
    select_latency,
    rows_inserted,
    insert_latency,
    rows_updated,
    update_latency,
    rows_deleted,
    delete_latency
FROM sys.schema_index_statistics
ORDER BY rows_selected DESC
LIMIT 30;
~~~

This view helps observe index activity from Performance Schema metrics. Distinguish between:
- Indexes used for reads.
- Indexes maintained by INSERT/UPDATE/DELETE.
- Indexes incurring write overhead with few reads.
- Indexes supporting constraints or rare but critical queries.

### 10.1. schema_unused_indexes Is Not a DROP Command

~~~
SELECT *
FROM sys.schema_unused_indexes
ORDER BY object_schema, object_name, index_name;
~~~

This view lists indexes with no recorded usage within the currently accumulated data window. Never automatically DROP indexes from this list.

Before dropping an index, you must:
1. Observe across a full workload cycle, including periodic reports and month-end/quarter-end jobs.
2. Check whether the index backs a PRIMARY KEY, UNIQUE, FOREIGN KEY, or constraint.
3. Check rare but critical query plans.
4. Check batch, ETL, and backup/maintenance workloads.
5. Evaluate impacts on locking and access paths.
6. Test in staging and measure.
7. Prepare a DDL rollback plan.

Counters may have been reset after a restart; an index used once a month can appear unused if the observation window is too short.

### 10.2. schema_redundant_indexes

~~~
SELECT *
FROM sys.schema_redundant_indexes
ORDER BY table_schema, table_name;
~~~

This view identifies indexes that appear duplicated or whose leftmost prefix is covered by another index. However, two indexes sharing a leftmost prefix are not always operationally redundant:
- One index may be UNIQUE while the other is not.
- Collations, sort directions, or prefix lengths may differ.
- An index may enforce a different constraint.
- A narrower index can reduce I/O for specific workloads.
- Index visibility and optimizer behavior can differ.

Use this view as an investigation list, not an automated deletion decision.

## 11. Observing the InnoDB Buffer Pool

sys.innodb_buffer_stats_by_table aggregates buffer pool pages by schema/table:

~~~
SELECT
    object_schema,
    object_name,
    allocated,
    data,
    pages
FROM sys.innodb_buffer_stats_by_table
ORDER BY allocated DESC
LIMIT 20;
~~~

Verify exact column names with DESCRIBE as they may vary across sys schema versions. This view helps identify tables occupying significant buffer pool memory.

Keep in mind:
- The buffer pool caches data and index pages.
- Presence of pages does not mean queries are using them efficiently.
- A large table dominating the buffer pool may simply reflect a read-heavy workload.
- Buffer pool snapshots reflect state at query time, not history.
- This view can be expensive to aggregate on large buffer pools; do not poll it at high frequency.

### 11.1. Do Not Optimize Solely by Hit Ratio

A high hit ratio is a positive signal, not the sole objective. If a query reads vast numbers of pages even when all reside in memory, latency can still be high due to CPU, latches, row locks, or data volume processed.

Combine:
- Buffer pool read requests and physical reads.
- Statement rows_examined.
- Table/index statistics.
- Waits.
- OS memory and I/O.
- Application latency.

## 12. InnoDB Lock Waits

sys.innodb_lock_waits helps identify transactions waiting on row locks and the transactions blocking them.

~~~
SELECT
    waiting_pid,
    waiting_query,
    waiting_trx_started,
    waiting_trx_age,
    waiting_trx_rows_locked,
    blocking_pid,
    blocking_query,
    blocking_trx_started,
    blocking_trx_age,
    blocking_trx_rows_locked
FROM sys.innodb_lock_waits
ORDER BY waiting_trx_age DESC;
~~~

Questions to answer:
- Which session is waiting?
- Which session is blocking?
- When did the transaction start?
- How long has the transaction been open?
- How many rows are locked?
- What is the blocker's current query?
- Is there an idle transaction that has not committed?

### 12.1. Blocking Query Can Be NULL

A transaction can retain locks after its last SQL statement completes and the session returns to Sleep. In that case, blocking_query may no longer show an active statement. Inspect the blocking transaction, session, and recent statement history rather than concluding there is no blocker.

### 12.2. sql_kill_* Columns Are Only Suggested Commands

Some sys views provide columns containing SQL strings like KILL QUERY or KILL CONNECTION for convenience. Those are generated strings for reference; selecting from the view does not execute them.

Before issuing KILL:
- Verify the exact connection ID.
- Identify the owning application.
- Check whether the transaction could incur a large rollback.
- Assess impact on requests and data.
- Follow runbooks and operational authorization.

KILL CONNECTION can trigger a transaction rollback and have a broader impact than terminating only the active query.

## 13. Metadata Lock and Table Lock Waits

Row locks and metadata locks are two distinct categories. DDL such as ALTER TABLE can wait for a metadata lock while another session is using the table.

sys.schema_table_lock_waits helps observe certain table/metadata lock waits:

~~~
SELECT
    object_schema,
    object_name,
    waiting_pid,
    waiting_query,
    waiting_query_secs,
    blocking_pid,
    blocking_query,
    blocking_lock_type,
    sql_kill_blocking_connection
FROM sys.schema_table_lock_waits
ORDER BY waiting_query_secs DESC;
~~~

Column names can differ across versions. Verify using DESCRIBE sys.schema_table_lock_waits before use.

When DDL is waiting:
- Find the session holding the metadata lock.
- Check for long transactions or idle-in-transaction sessions.
- Determine whether the queued DDL is causing subsequent requests to pile up behind it.
- Choose an appropriate DDL window.
- Do not kill the blocker before understanding the impact.

Do not confuse this view with innodb_lock_waits. A transaction may hold no conflicting row locks yet still block DDL via a metadata lock.

## 14. Wait Events: What Is the Server Waiting On?

sys.waits_global_by_latency aggregates wait events by wait duration:

~~~
SELECT
    events,
    total,
    total_latency,
    avg_latency,
    max_latency
FROM sys.waits_global_by_latency
ORDER BY total_latency DESC
LIMIT 30;
~~~

Column formatting may differ across versions. This view shows which wait classes have the largest total latency.

Common groups include:
- File I/O.
- Table I/O.
- Locks.
- Mutexes.
- Conditions.
- Socket/network.
- Internal synchronization.

### 14.1. Total Latency vs. Wait Counts

A wait event with high total_latency can result from:
- Very high occurrence counts.
- Long duration per wait.
- A few extremely long waits.

Compare total, avg, and max. A rare wait with a very high max can cause tail latency; a frequent wait with low average can accumulate large total time.

### 14.2. Waits by User and Host

Views such as waits_by_user_by_latency and waits_by_host_by_latency help break down workload by source. If an account or host generates heavy waits, investigate its connection pool, query patterns, networking, and concurrency.

Do not blame a host for causing an error solely from total latency; that host may simply be the largest traffic source.

## 15. File I/O and Table I/O

sys.io_global_by_file_by_bytes:

~~~
SELECT *
FROM sys.io_global_by_file_by_bytes
ORDER BY total_allocated DESC
LIMIT 20;
~~~

sys.io_global_by_file_by_latency:

~~~
SELECT *
FROM sys.io_global_by_file_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

These views help identify files with heavy I/O volume or latency. Verify exact column names on the target server.

They can help find:
- Tablespaces with heavy reads/writes.
- Redo/undo or log files with high activity.
- Rising file I/O latency.
- Temporary files or files tied to specific workloads.

Do not immediately blame the storage hardware for all I/O latency. Correlate with OS metrics, filesystem behavior, queue depth, buffer pool, and workload.

## 16. Load by User and Host

sys.user_summary and sys.host_summary provide views grouped by workload source:

~~~
SELECT *
FROM sys.user_summary
ORDER BY statement_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.host_summary
ORDER BY statement_latency DESC
LIMIT 20;
~~~

You can drill down further by statement type or file I/O using sibling views in the same group.

Questions to explore:
- Which account generates the most statements?
- Which account experiences high latency?
- Which host causes the most rows examined?
- Is a batch client creating excessive temporary tables?
- Are there unexpected accounts or off-hours workloads?

User/host metrics are Performance Schema aggregations. Accounts/hosts may be normalized or grouped according to view definitions. Do not use them in place of security auditing; use dedicated logs/audits when tracing individual end-user actions.

## 17. sys Schema and Configuration Tables

sys.sys_config stores configuration settings for certain sys schema routines and views. Inspect it with:

~~~
SELECT *
FROM sys.sys_config
ORDER BY variable;
~~~

Configuration values can control limits or behavior of helper routines. Do not modify this table by guesswork; read comments and related object definitions first.

Common sys configuration variables used in routines include:
- diagnostics.allow_i_s_tables
- diagnostics.include_raw
- statement_performance_analyzer.limit
- statement_performance_analyzer.view
- statement_performance_analyzer.limit

The actual list depends on version. Check sys_config contents and SHOW CREATE PROCEDURE/FUNCTION. Do not assume every variable exists across all releases.

## 18. Useful Functions and Procedures

Beyond views, the sys schema provides helper functions for formatting and lookups.

Common functions:
- format_bytes(): formats byte counts into human-readable units.
- format_time(): formats picosecond durations into readable strings.
- format_path(): normalizes file paths.
- extract_schema_from_file_name(): extracts the schema from tablespace file names where supported.
- extract_table_from_file_name(): extracts the table name.
- ps_thread_id(): maps a processlist ID to a Performance Schema thread ID.
- ps_thread_account(): returns the thread's account by ID.
- ps_thread_trx_info(): provides thread transaction info in a supported structure.

Example:

~~~
SELECT
    sys.format_bytes(1048576) AS one_mib,
    sys.format_time(1000000000000) AS one_second;
~~~

Output formatting depends on the helper and version. Use helpers for human-facing dashboards, while keeping raw numeric values if further arithmetic is needed.

### 18.1. statement_performance_analyzer

sys.statement_performance_analyzer is a procedure supporting statement summary analysis. It can create or compare snapshots of statement statistics across supported modes.

Because parameters and behavior vary by version, before integrating into a runbook run:
~~~
SHOW CREATE PROCEDURE sys.statement_performance_analyzer;
~~~

Read the definition and documentation for your exact version. Never invoke the procedure in production for the first time without understanding whether it creates temporary tables, uses session variables, or requires specific privileges.

### 18.2. diagnostics

sys.diagnostics is a procedure that collects multiple diagnostic groups over a time window. It can query many views and generate large output.

Before using it:
- Inspect SHOW CREATE PROCEDURE.
- Check parameters and collection levels.
- Estimate overhead.
- Test in staging.
- Select only the needed detail level.
- Store output in incident systems according to data policies.

Do not run diagnostics continuously in a polling loop as a substitute for a monitoring platform.

## 19. Access Privileges and Security

The sys schema does not bypass MySQL's privilege system. Required privileges depend on the view/routine, SQL SECURITY, underlying data sources, and the type of information accessed.

An account restricted to partial visibility may not see all threads or statements. The PROCESS privilege affects visibility into other sessions' activity in certain interfaces. Read privileges on Performance Schema, sys views, and metadata must also be granted appropriately.

Inspect a view definition:

~~~
SHOW CREATE VIEW sys.processlist;
~~~

Inspect current privileges:

~~~
SHOW GRANTS FOR CURRENT_USER();
~~~

Principles:
- Create a dedicated account/role for observability.
- Grant SELECT only on required views.
- Review SQL SECURITY of views/procedures before granting access.
- Grant PROCESS or sensitive privileges only when required by the use case.
- Do not use root for dashboards.
- Do not grant KILL privileges to read-only accounts.
- Restrict exposure of query text containing sensitive literals.
- Protect endpoints/dashboards and logs containing SQL.

Some views can expose statement text, users, hosts, schemas, or file paths. This can be sensitive data. Share it only with personnel who have a legitimate operational need.

## 20. Reading Metrics: Counters, Latency, and Time Intervals

A common mistake is treating cumulative counters as instantaneous rates.

For example, rows_examined = 1,000,000 could mean:
- 1 million rows in 10 seconds.
- 1 million rows in 30 days.
- 1 million rows since the last reset.

These three scenarios have completely different operational meanings.

To compute a rate, take two snapshots at times t1 and t2:

\[
rate = \frac{counter(t2)-counter(t1)}{t2-t1}
\]

For example, if statement count rises from 10,000 to 16,000 over 60 seconds:

\[
rate = \frac{16000-10000}{60}=100
\]

That corresponds to roughly 100 statements per second during the measurement interval.

### 20.1. Handling Counter Resets

If the server restarts or a summary table is truncated/reset, the counter at t2 may be smaller than at t1. Direct subtraction is then invalid. Record server uptime, reset timestamps, and instance identity alongside snapshots.

Do not compare counters across two servers or across restarts as a continuous series without normalization.

### 20.2. Total Latency and Latency Rates

Views display cumulative total_latency. To measure latency over a specific interval, take two snapshots and compute deltas where the underlying counters permit. Average latency in a view may reflect the cumulative average since reset, not the average over the last minute.

For accurate time-windowed latency, use a monitoring system that periodically scrapes histograms/summaries at the application tier or via a database exporter.

## 21. Workflow for Diagnosing a Database Incident

### Step 1: Define Scope and Timeframe

Record:
- When the incident started.
- Which instance is affected.
- Which queries/APIs are slow.
- Error rates and p95/p99 latency.
- Recent deployments or configuration changes.
- Number of connections and open transactions.

### Step 2: Inspect Sessions and Locks

~~~
SELECT *
FROM sys.processlist
ORDER BY statement_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.innodb_lock_waits
ORDER BY waiting_trx_age DESC;
~~~

If a metadata lock is suspected, check sys.schema_table_lock_waits.

### Step 3: Find Time-Consuming Statements

~~~
SELECT
    query,
    exec_count,
    total_latency,
    avg_latency,
    max_latency,
    rows_examined,
    rows_sent,
    tmp_disk_tables,
    full_scan
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 20;
~~~

Determine whether a query digest correlates with the incident window. If needed, obtain a sample query and run EXPLAIN in a safe environment.

### Step 4: Inspect Tables and Indexes

~~~
SELECT *
FROM sys.schema_table_statistics
ORDER BY total_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.schema_index_statistics
ORDER BY rows_selected DESC
LIMIT 20;
~~~

Identify hot tables, heavily accessed indexes, and signs of scans.

### Step 5: Inspect Waits and I/O

~~~
SELECT *
FROM sys.waits_global_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

~~~
SELECT *
FROM sys.io_global_by_file_by_latency
ORDER BY total_latency DESC
LIMIT 20;
~~~

Correlate with OS metrics and storage telemetry.

### Step 6: Verify the Hypothesis

An indicator in a sys view is only initial evidence. Use EXPLAIN, EXPLAIN ANALYZE where appropriate, slow query logs, application traces, and OS metrics to verify.

### Step 7: Apply Controlled Changes

Modify indexes, queries, configuration, or concurrency only after identifying the root cause. Document the baseline, change, timestamp, and post-change results.

## 22. Practical Example: Investigating a Slow Reporting Query

Suppose the order reporting API is slow. Start with statement analysis:

~~~
SELECT
    query,
    exec_count,
    avg_latency,
    max_latency,
    rows_examined,
    rows_sent,
    tmp_disk_tables
FROM sys.statement_analysis
WHERE db = 'sales'
ORDER BY total_latency DESC
LIMIT 10;
~~~

Suppose one digest shows high rows_examined and low rows_sent. Next steps:
1. Retrieve a sample query from the slow log or application trace.
2. Run EXPLAIN.
3. Inspect indexes and predicates.
4. Check the corresponding table in schema_table_statistics.
5. Check waits to rule out locks/I/O.
6. Test query rewrites or indexes in staging.
7. Compare latency, rows examined, and write overhead.
8. Deploy with a rollback plan.

Do not create an index merely because rows_examined is high. If the report reads most of the table, a scan may be the right plan. If the query is stuck on a lock wait, a new index may not fix the root cause.

## 23. Limitations and Pitfalls of the sys Schema

- Metrics are not long-term history.
- Counters can reset on restart or summary truncation.
- Missing instrumentation leads to incomplete views.
- Digest aggregation merges different parameter values.
- Digest capacity is bounded.
- Some views can be resource-intensive to aggregate on large instances.
- Column and object names can change across versions.
- Privileges can restrict an account to partial visibility.
- A query with high total latency is not necessarily the slowest query in the current incident window.
- An unused index does not mean the index is safe to drop.
- A full scan is not always a bug.
- Buffer pool hit ratio does not reflect overall performance.
- KILL statements can trigger rollbacks or disrupt requests.
- Query text can contain sensitive information.
- Views only describe observations; they do not fix issues automatically.

## 24. Hands-On Exercises

### Exercise 1: Explore the sys Schema

List views, procedures, and functions in the sys schema. Pick five views, run SHOW CREATE VIEW, and document the Performance Schema/INFORMATION_SCHEMA sources they query.

### Exercise 2: Statement Analysis

Generate a SELECT/INSERT/UPDATE workload in a lab database. Query statement_analysis and rank by total_latency and avg_latency. Explain why the two rankings can differ.

### Exercise 3: Rows Examined

Create two queries that both return 10 rows where one scans significantly more rows than the other. Observe rows_examined/rows_sent and use EXPLAIN to explain the difference.

### Exercise 4: Temporary Tables

Run a GROUP BY/ORDER BY query over a large dataset. Inspect statements_with_temp_tables and disk temporary tables. Test a rewrite or index in staging.

### Exercise 5: Sessions and Connection Pools

Open several idle connections and one uncommitted transaction in the lab. Observe sys.processlist and sys.session. Distinguish normal Sleep from an idle transaction holding locks.

### Exercise 6: Lock Waits

Use two sessions to create a row lock wait. Observe sys.innodb_lock_waits, and identify waiting_pid and blocking_pid. Do not KILL any connection before identifying the transaction owner.

### Exercise 7: Metadata Locks

In the lab, open a transaction reading a table and then attempt DDL from another session. Observe sys.schema_table_lock_waits and explain how it differs from row locks.

### Exercise 8: Index Usage

Run a workload against a table with multiple indexes. Inspect schema_index_statistics and schema_unused_indexes. Compile a list of indexes to investigate, without dropping any solely based on the view.

### Exercise 9: Wait Events

Generate a read/write workload and inspect waits_global_by_latency. Compare total, avg, and max latency. Distinguish total wait time from CPU time.

### Exercise 10: Buffer Pool

Query innodb_buffer_stats_by_table and schema_table_statistics_with_buffer. Identify the table occupying the most buffer pool memory. Explain why you cannot conclude that table causes slowness solely from page volume.

### Exercise 11: Counter Deltas

Take two snapshots of statement_analysis or a Performance Schema summary 60 seconds apart. Calculate the per-second delta for exec_count and rows_examined. Repeat after a lab restart to observe the reset effect.

### Exercise 12: Dashboard Role

Create a read-only role for required sys views. Inspect SQL SECURITY and underlying privileges. Verify the account has neither KILL privileges nor write access to business data.

### Exercise 13: Incident Report

Simulate one query slow due to a missing index and one slow due to a lock wait. Use sys views to gather evidence, then write an incident report covering symptoms, hypotheses, evidence, root cause, and actions.

## 25. sys Schema Operational Checklist

- [ ] Verified MySQL version and available sys objects.
- [ ] Verified Performance Schema is enabled.
- [ ] Checked required instruments and consumers.
- [ ] Understood metrics are runtime counters, not long-term history.
- [ ] Checked restart/reset timestamps before comparing values.
- [ ] Used statement_analysis to locate query patterns.
- [ ] Reviewed rows_examined, rows_sent, and total/avg/max latency.
- [ ] Checked errors, warnings, full scans, and temporary tables.
- [ ] Used processlist/session to investigate sessions.
- [ ] Distinguished connection ID from Performance Schema THREAD_ID.
- [ ] Used schema_table_statistics and schema_index_statistics for the right questions.
- [ ] Did not DROP indexes solely because schema_unused_indexes lists them.
- [ ] Checked innodb_lock_waits and metadata lock waits separately.
- [ ] Inspected wait events and file I/O when needed.
- [ ] Understood buffer pool views are point-in-time snapshots.
- [ ] Verified column names with DESCRIBE/SHOW CREATE VIEW.
- [ ] Reviewed privileges and SQL SECURITY before granting dashboard access.
- [ ] Protected query text and account/host details.
- [ ] Measured deltas when time-based rates are needed.
- [ ] Verified hypotheses with EXPLAIN, application traces, and OS metrics.
- [ ] Did not treat the sys schema as an auto-remediation tool or historical repository.

## 26. Conclusion

The sys schema is a practical observation layer for diagnosing MySQL. It turns detailed Performance Schema and INFORMATION_SCHEMA data into readable views organized by statement, session, schema, index, wait, I/O, buffer pool, and lock. Starting from an operational question and choosing the matching view is far more effective than mechanically reading every view.

These views do not generate telemetry on their own; they depend on Performance Schema instruments, consumers, capacities, and privileges. Metrics are mostly runtime counters that can reset or disappear on restart, so take timed snapshots to compute rates and rely on a monitoring platform for long-term history.

Use the sys schema to form hypotheses, then verify them with execution plans, slow logs, application traces, lock diagnostics, and OS metrics. Never drop indexes solely from an unused list, never KILL a session from a single output row, and never grant broad privileges to dashboards. A sound observability workflow requires defined measurement windows, workload context, least-privilege access, and before/after evidence for every change.

## Official References

- [MySQL 8.4 Reference Manual – The sys Schema](https://dev.mysql.com/doc/refman/8.4/en/sys-schema.html)
- [MySQL 8.4 Reference Manual – sys Schema Reference](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-reference.html)
- [MySQL 8.4 Reference Manual – Statement Analysis](https://dev.mysql.com/doc/refman/8.4/en/sys-statement-analysis.html)
- [MySQL 8.4 Reference Manual – Processlist](https://dev.mysql.com/doc/refman/8.4/en/sys-processlist.html)
- [MySQL 8.4 Reference Manual – Schema Table Statistics](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-table-statistics.html)
- [MySQL 8.4 Reference Manual – Schema Index Statistics](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-index-statistics.html)
- [MySQL 8.4 Reference Manual – InnoDB Lock Waits](https://dev.mysql.com/doc/refman/8.4/en/sys-innodb-lock-waits.html)
- [MySQL 8.4 Reference Manual – Schema Table Lock Waits](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-table-lock-waits.html)
- [MySQL 8.4 Reference Manual – Waits Global by Latency](https://dev.mysql.com/doc/refman/8.4/en/sys-waits-global-by-latency.html)
- [MySQL 8.4 Reference Manual – I/O Global by File by Latency](https://dev.mysql.com/doc/refman/8.4/en/sys-io-global-by-file-by-latency.html)
- [MySQL 8.4 Reference Manual – InnoDB Buffer Stats by Table](https://dev.mysql.com/doc/refman/8.4/en/sys-innodb-buffer-stats-by-table.html)
- [MySQL 8.4 Reference Manual – sys Schema Functions](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-functions.html)
- [MySQL 8.4 Reference Manual – sys Schema Procedures](https://dev.mysql.com/doc/refman/8.4/en/sys-schema-procedures.html)
- [MySQL 8.4 Reference Manual – Performance Schema](https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html)
- [MySQL 8.4 Reference Manual – Performance Schema Statement Digests](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-statement-digests.html)

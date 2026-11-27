# Performance Schema: Instruments, Consumers, and Collection Overhead

Performance Schema is MySQL's built-in observability engine that records internal server activity such as SQL statements, execution stages, wait events, synchronization locks, I/O, transactions, threads, and memory. It is a foundational data source for finding time-consuming statements, pinpointing I/O bottlenecks, analyzing contention, and tracking resource usage.

To use Performance Schema effectively, you must distinguish two concepts. An **instrument** is the component that generates measurement events; a **consumer** is what receives and stores those events for querying. Enabling too many instruments, timing every operation, or retaining long histories can increase CPU, memory, and synchronization overhead. Conversely, disabling the wrong consumer can prevent needed diagnostic data from being recorded.

In the **DATABASE_MYSQL** module, this lesson explains the instrument/consumer architecture, setup tables, current/history/summary flows, timers, thread/object filters, collection overhead, and how to enable instrumentation selectively. Examples focus on MySQL 8.4; instrument names, consumers, and configuration variables can vary by version or storage engine, so verify directly against your running instance.

## 1. What Is Performance Schema Used For?

Performance Schema provides internal MySQL observability data. Commonly tracked activity groups include:

- Statement: SQL statements and execution metrics.
- Stage: internal phases during statement processing.
- Wait: wait times for I/O, mutexes, conditions, locks, and other resources.
- Transaction: transaction duration and state.
- File and table I/O: file read/write operations, table handles, and sockets.
- Memory: memory allocated per instrument.
- Thread: client foreground threads and server background threads.
- Metadata lock: metadata lock wait states.

Performance Schema helps answer operational questions such as:

- Which SQL statement consumes the most total time?
- Which statement runs unusually long or examines too many rows?
- Which resource type are threads waiting on?
- Is there significant wait time on file I/O, mutexes, or metadata locks?
- Which group of statements generates high call counts or errors?
- Which instrument is consuming the most memory?

Performance Schema is an in-memory instrumentation system, not a long-term historical store. Data in event and summary tables is generally reset when MySQL restarts; history tables have bounded capacity and older data can be overwritten. For long-term retention, periodically export metrics to an external monitoring or telemetry system.

### 1.1. Distinguishing Performance Schema from Other Tools

| Tool | Primary Purpose | Typical Data |
|---|---|---|
| Performance Schema | Observe internal MySQL activity | Statements, waits, stages, threads, memory, I/O |
| sys schema | Readable views and helpers built on Performance Schema | Top statements, wait latency, memory, lock waits |
| Slow query log | Log statements exceeding thresholds or criteria | SQL text, duration, row counts per configuration |
| General query log | Broadly record connections and statements | Query log in order received |
| Audit plugin | Record events for auditing requirements | Connections, access, and activity per audit policy |
| External metrics system | Track trends and alerts over time | CPU, RAM, disk, replication lag, latency |

Performance Schema complements the slow query log and external monitoring. Do not use it as an immutable audit log: history can be overwritten, data resides only in memory, and some SQL text may be truncated by configured limits.

## 2. Instrument and Consumer Architecture

The collection pipeline can be visualized as follows:

```text
Internal MySQL Activity
          |
          v
      Instrument
  (detects events,
   optionally times them)
          |
          v
       Consumer
 (selects event types and
  where data is stored)
          |
          v
  Current / History / Summary
          |
          v
 Performance Schema tables
          |
          v
   SQL query / sys views
          |
          v
 Dashboard, alerts, analysis
```

### 2.1. Instruments Are Event Sources

An instrument describes a measurable MySQL operation. For example:

| Instrument Group | Example Name | Meaning |
|---|---|---|
| Statement | statement/sql/select | Execution of a SELECT statement |
| Statement | statement/sql/insert | Execution of an INSERT statement |
| Stage | stage/sql/Opening tables | An SQL processing stage |
| File I/O | wait/io/file/sql/binlog | Waiting on binlog file I/O |
| Socket I/O | wait/io/socket/sql/client_connection | Client socket activity |
| Metadata lock | wait/lock/metadata/sql/mdl | Waiting on a metadata lock |
| Mutex | wait/synch/mutex/innodb/% | Waiting on an InnoDB mutex |
| Memory | memory/innodb/% | Memory allocation belonging to InnoDB |

Instrument names typically follow a hierarchical structure. You can filter with LIKE to select an entire group or a specific instrument.

Instruments usually have two key attributes:

- ENABLED: whether events from the instrument are collected.
- TIMED: whether event duration is measured.

When ENABLED=NO, the instrument does not generate corresponding events. When ENABLED=YES and TIMED=NO, MySQL can collect events without timing them; the corresponding timer columns may be NULL. When TIMED=YES, MySQL reads a timer to measure duration, adding measurement overhead.

### 2.2. Consumers Are Event Destinations

Consumers determine which types of events are written into Performance Schema tables. An instrument may be enabled without an appropriate consumer to store a particular event history; conversely, enabling a consumer does not generate events if the instrument or thread instrumentation is disabled.

Common consumers:

| Consumer | Role |
|---|---|
| global_instrumentation | Enables the global instrumentation collection layer |
| thread_instrumentation | Enables per-thread collection |
| events_waits_current | Currently active wait events |
| events_waits_history | Recent per-thread wait history |
| events_waits_history_long | Server-wide shared wait history |
| events_stages_current | Currently active stages |
| events_stages_history | Recent per-thread stage history |
| events_stages_history_long | Server-wide stage history |
| events_statements_current | Currently active statements |
| events_statements_history | Recent per-thread statement history |
| events_statements_history_long | Server-wide statement history |
| events_transactions_current | Currently active transactions |
| events_transactions_history | Recent per-thread transaction history |
| events_transactions_history_long | Server-wide transaction history |
| statements_digest | Collects and aggregates statement digests |

Actual consumer lists vary by version. Do not assume every name exists on every MySQL build; inspect the setup_consumers table before making changes.

### 2.3. Dependencies Between Consumers

Some consumers form a dependency hierarchy. Conceptual model:

```text
global_instrumentation
        |
        v
thread_instrumentation
        |
        +-----------------------------+
        |              |              |
        v              v              v
events_waits_current  events_stages_current  events_statements_current
        |              |              |
        v              v              v
history / history_long  history / history_long  history / history_long

statements_digest (separate digest aggregation consumer)
```

If the global or thread layer is disabled, enabling lower-level consumers does not mean data will be collected as expected. statements_digest is a separate consumer for digest aggregation; you do not need to enable history_long just to query digest summary tables.

Inspect the actual state instead of relying on memory of a fixed configuration:

```sql
SELECT
    NAME,
    ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
```

## 3. Main Configuration Tables

Performance Schema provides setup tables to control instruments, consumers, timers, and object/thread filters.

| Table | Role |
|---|---|
| setup_instruments | Enable/disable instruments and timing |
| setup_consumers | Enable/disable consumers |
| setup_timers | Select timers for event classes |
| setup_actors | Filter foreground threads by user/host/role |
| setup_objects | Filter instrumentation by object |
| threads | Thread details and instrument/history flags |
| performance_timers | Timers supported by the server |

### 3.1. Reading setup_instruments

Inspect statement instruments:

```sql
SELECT
    NAME,
    ENABLED,
    TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/sql/%'
ORDER BY NAME
LIMIT 30;
```

Inspect wait instruments:

```sql
SELECT
    NAME,
    ENABLED,
    TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/%'
ORDER BY NAME
LIMIT 30;
```

You can search for a specific group:

```sql
SELECT
    NAME,
    ENABLED,
    TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/lock/metadata/%';
```

Not every instrument is supported by every engine or build. Some instruments are enabled by default and others are disabled by default. Use the query output to decide rather than assuming a fixed list.

### 3.2. Reading setup_consumers

```sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
ORDER BY NAME;
```

This query shows which consumers are currently enabled. Save the output before making changes so you can restore the exact initial configuration after an investigation.

### 3.3. Reading setup_timers and performance_timers

Timers are used to measure wait, stage, and statement durations. Check the timer assigned to each event type:

```sql
SELECT *
FROM performance_schema.setup_timers;
```

View available timers:

```sql
SELECT *
FROM performance_schema.performance_timers;
```

Timer columns describe the timer name, frequency, resolution, and measurement overhead. The selected timer depends on the platform and MySQL build. Do not assume every server uses the same timer type or resolution.

### 3.4. setup_actors, setup_objects, and threads

setup_actors applies instrumentation settings to foreground threads by user, host, and role. It is useful when focusing monitoring on a specific application connection group or excluding traffic you do not need to measure.

setup_objects controls instrumentation for objects such as schemas, tables, stored programs, or events using the filter columns supported by the version.

The threads table lists MySQL threads and related flags. For example:

```sql
SELECT
    THREAD_ID,
    NAME,
    TYPE,
    PROCESSLIST_ID,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    INSTRUMENTED,
    HISTORY
FROM performance_schema.threads
ORDER BY TYPE, THREAD_ID;
```

- INSTRUMENTED indicates whether the thread is instrumented.
- HISTORY indicates whether event history is stored for the thread.
- Background and foreground threads may have filters applied differently.

Do not disable instrumentation on threads just because you do not need analysis yet. A broad change can cause critical data to disappear from history tables.

## 4. Current, History, and History_long Event Groups

Event tables generally come in three storage tiers:

| Tier | Scope | Interpretation |
|---|---|---|
| current | Currently active events | Current state of each thread/event |
| history | Bounded per-thread history | Recent events for each individual thread |
| history_long | Bounded server-wide shared history | Recent events across many threads |

Example for statements:

- events_statements_current
- events_statements_history
- events_statements_history_long

Wait, stage, and transaction groups follow a similar structure if provided by the version.

### 4.1. Current Is Not a Complete Log

Current tables show activity happening at the moment of the query. If a statement finishes before you query, it may no longer appear in current. To investigate recently completed events, use history or history_long if the corresponding consumer is enabled.

### 4.2. History Is Bounded

History tables are ring buffers. When capacity is reached, new events overwrite older ones. History is typically organized per thread, whereas history_long is shared across the whole server.

Because history_long is shared among all threads, high-event workloads can overwrite data quickly. Enabling history_long long-term can increase memory usage and event write overhead. Use it for targeted investigations rather than enabling all history by default on every system.

### 4.3. Summary Tables Store Aggregated Metrics

Summary tables aggregate counts, durations, errors, or data volumes along a dimension such as event name, thread, account, user, host, table, or digest.

Summary tables are generally suited for trend questions and top-workload ranking. History tables are suited for inspecting details of a recent event. The two serve different purposes.

## 5. Statement Digests and SQL Analysis

Digests normalize statements to group structurally identical queries together. For example, these two queries:

```sql
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 202;
```

can be grouped into the same digest because literals are normalized. Digests allow workload analysis by SQL pattern rather than individual parameter values.

The events_statements_summary_by_digest table provides aggregated metrics by digest. The statements_digest consumer must be enabled to collect digests.

### 5.1. Ranking SQL Statements by Total Time

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    SUM_ERRORS,
    SUM_WARNINGS
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 15;
```

Timers in Performance Schema TIMER_WAIT columns are expressed in picoseconds. Divide by 10^12 to convert to seconds. When comparing, distinguish total time from average time: a digest with high total time may simply execute very frequently, whereas a digest with high average time is an individually slow statement.

### 5.2. Finding Statements Examining Too Many Rows

```sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT,
    ROUND(
        SUM_ROWS_EXAMINED / NULLIF(SUM_ROWS_SENT, 0),
        2
    ) AS examined_to_sent_ratio,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds
FROM performance_schema.events_statements_summary_by_digest
WHERE DIGEST IS NOT NULL
ORDER BY SUM_ROWS_EXAMINED DESC
LIMIT 15;
```

A high examined/sent ratio can suggest queries scanning many rows to return few results. This is only a screening signal; aggregations, reports, or joins may legitimately need to examine many rows by design.

### 5.3. Reading Recent Statement History

```sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS duration_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    MYSQL_ERRNO
FROM performance_schema.events_statements_history_long
WHERE SQL_TEXT IS NOT NULL
ORDER BY TIMER_START DESC
LIMIT 20;
```

SQL_TEXT may be truncated in length and may contain client-sent literals. Do not treat history_long as a complete log or audit source. If the history_long consumer is disabled, the table will not capture new events.

TIMER_START is an internal timer value, not a wall-clock timestamp. When correlating with application logs, use actual timestamp columns provided by the table (if available) or match by thread/event and observation window; do not interpret TIMER_START directly as a calendar date/time.

## 6. Analyzing Waits and Stages

A slow SQL statement does not necessarily spend all its time on CPU. It may spend most of its time waiting on storage, mutexes, metadata locks, or networking.

### 6.1. Ranking Waits by Total Time

```sql
SELECT
    EVENT_NAME,
    COUNT_STAR,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

Wait groups with high total time point to areas needing investigation. Read the event name, count, and average duration together. A wait type with a massive count of very brief waits can still accumulate substantial total time.

### 6.2. Distinguishing Waits and Stages

- A wait represents a thread waiting for a resource or external operation.
- A stage represents a processing phase of a statement, such as opening tables, optimizing, sending data, or sorting.

A stage can contain multiple waits inside it. Do not sum stage time and wait time as independent quantities, as you may double-count overlapping intervals.

### 6.3. Using sys Schema for Quick Reading

The sys schema provides more readable views over Performance Schema data. For example:

```sql
SELECT *
FROM sys.statement_analysis
ORDER BY total_latency DESC
LIMIT 10;
```

View waits by latency:

```sql
SELECT *
FROM sys.waits_global_by_latency
LIMIT 20;
```

sys views can differ across versions. Check the view definition or documentation before relying on column names in custom dashboards.

## 7. Enabling Instrumentation Selectively

An essential rule is to start from the investigative question. If you need to find slow statements, you do not need to enable all mutex, file, memory, and socket instruments right away.

### 7.1. Checking Whether Performance Schema Is Active

```sql
SHOW VARIABLES LIKE 'performance_schema';
```

If Performance Schema was disabled at server startup, you cannot enable it via UPDATE setup_instruments or ordinary SET GLOBAL statements. You must configure the appropriate startup parameter and restart MySQL during a maintenance window.

If it is already enabled, inspect the required consumers and instruments before making changes.

### 7.2. Enabling Statement Instrumentation and Digests

Example enabling global/thread layers, statement current/history, and digests:

```sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long',
    'statements_digest'
);
```

Enable the statement instrument group and timing:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES',
    TIMED = 'YES'
WHERE NAME LIKE 'statement/sql/%';
```

This is an example for a statement investigation. Before running it, record the initial state of the rows you plan to modify. On systems with many connections and heavy workloads, enable history_long only when recent detailed event inspection is needed; digest summaries can satisfy aggregate ranking needs with a different cost and footprint profile.

### 7.3. Enabling Wait Instrumentation by Group

If your hypothesis involves contention or I/O, enable only the relevant group. For example, checking metadata locks:

```sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'wait/lock/metadata/%';
```

If you need wait events during an investigation window, first enable the required consumers:

```sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_waits_current',
    'events_waits_history',
    'events_waits_history_long'
);
```

Then enable the metadata lock instrument group:

```sql
UPDATE performance_schema.setup_instruments
SET ENABLED = 'YES',
    TIMED = 'YES'
WHERE NAME LIKE 'wait/lock/metadata/%';
```

Do not expand to all wait/synch or wait/io just to "get more data." Enable only the needed group, measure the cost, and disable it again once you have sufficient evidence.

When finished, restore the exact initial ENABLED/TIMED states you recorded. Only set a consumer or instrument back to NO if its pre-investigation state was NO; do not run a blanket disable statement that could accidentally turn off instrumentation already used by your monitoring system.

### 7.4. Enabling Does Not Provide Retroactive Data

When you enable an instrument or consumer, MySQL collects only events generated after the change. It does not reconstruct past events. Therefore, allow the workload to run long enough after enabling before querying summary/history tables.

## 8. Collection Overhead and Influencing Factors

Performance Schema is designed for low-overhead observability, but it is not free. Cost depends on the number of instruments, event types, timers, thread count, event frequency, consumers, and history buffer sizes.

### 8.1. Instrument Cost

The finer-grained the instrument, the more frequently MySQL must check state and emit events at instrumentation points. Very high-frequency event classes such as mutexes, conditions, sockets, or file I/O can generate enormous numbers of events.

Enabling an instrument does not necessarily cause noticeable overhead in every workload. Evaluate based on actual operation frequency and before/after measurements.

### 8.2. TIMED Cost

Timing requires reading a timer and recording the duration in the event. For high-frequency instruments, timing can add noticeably more CPU overhead than merely counting events.

If you only need occurrence counts or to detect activity types, consider ENABLED=YES with TIMED=NO for instruments that support this mode. In that case, duration metrics will not be available for latency ranking.

### 8.3. Consumer and History Cost

Current/history consumers increase the number of events written to their respective structures. history_long is shared server-wide; heavy workloads can fill and overwrite it rapidly. Increasing history size retains more events but increases allocated memory.

Variables sizing Performance Schema capacity are prefixed with performance_schema_events_..._history_size or performance_schema_max_.... Many sizing parameters are fixed at server startup. Check current values and mutability before tuning:

```sql
SHOW VARIABLES LIKE 'performance_schema%history%size';
SHOW VARIABLES LIKE 'performance_schema_max%';
```

Do not raise every maximum limit based on guesswork. Calculate your RAM budget and determine which historical data actually needs to be kept.

### 8.4. Per-Thread and Per-Object Cost

Instrumenting every user, host, and table can broaden collection scope beyond what is needed. setup_actors and setup_objects help narrow observation targets.

Filtering can omit necessary data if conditions are too strict. Before applying filters, identify which application threads, background threads, and objects are in investigation scope.

## 9. Measuring Performance Schema Overhead in a Controlled Manner

Do not conclude Performance Schema is "light" or "heavy" by intuition. Measure on a representative workload.

Recommended workflow:

1. Record the current Performance Schema configuration.
2. Select a repeatable workload.
3. Capture baseline CPU, throughput, p95/p99 latency, RAM, and disk I/O.
4. Enable one group of instruments/consumers targeting a specific question.
5. Re-run the same workload under comparable conditions.
6. Compare latency, throughput, CPU, memory, and event counts.
7. Expand scope incrementally if data is insufficient.
8. Disable groups no longer needed and record the final configuration.

Do not compare two runs if request volume, cache state, dataset, or background load differ significantly. Repeat runs if needed and use medians/percentiles to reduce the effect of random variance.

### 9.1. Monitoring Lost Events

Check status counters related to Performance Schema:

```sql
SHOW GLOBAL STATUS LIKE 'Performance_schema%lost';
```

Lost counters can indicate that a structure or instrumentation class lacks capacity for the current number of events/objects. Counter names vary by version and instrument type. If a counter rises, investigate the specific group before increasing sizing.

Not every overwritten event in a history ring buffer indicates a lost counter error. History buffers are designed to retain a recent window; replacing older entries when full is normal behavior.

### 9.2. Monitoring Memory Used by Performance Schema

If memory instrumentation is available and enabled, you can inspect the memory summary:

```sql
SELECT
    EVENT_NAME,
    CURRENT_NUMBER_OF_BYTES_USED,
    HIGH_NUMBER_OF_BYTES_USED
FROM performance_schema.memory_summary_global_by_event_name
ORDER BY CURRENT_NUMBER_OF_BYTES_USED DESC
LIMIT 20;
```

Or use the sys view:

```sql
SELECT *
FROM sys.memory_global_by_current_bytes
LIMIT 20;
```

These numbers reflect only allocations instrumented by MySQL. Do not equate this total to the process's full RSS; allocator overhead, shared libraries, buffers, and uninstrumented memory also exist.

## 10. Security and Observability Data Boundaries

Performance Schema can contain SQL_TEXT, usernames, hosts, object names, schemas, and workload characteristics. Some statements include sensitive literals in their text; normalized digests reduce exposure to literals but do not remove all identifying details.

Appropriate practices:

- Grant SELECT only on necessary tables/views; avoid broad administrative privileges for dashboards.
- Restrict who can UPDATE setup tables.
- Do not export SQL_TEXT or internal hostnames to unauthorized systems.
- Set retention and access controls for external monitoring data.
- Do not use Performance Schema as a substitute for an audit trail when full audit evidence is required.
- Consider that querying history tables can return sensitive data before granting read access.

When sharing investigation findings, scrub passwords, tokens, literals containing personal data, and unnecessary infrastructure details.

## 11. Workflow for Investigating a Slow SQL Query

Suppose the application reports that the orders listing endpoint is slow. A practical workflow:

**Step 1 — Identify the SQL statement or digest**

Use events_statements_summary_by_digest to find SQL patterns with high total time, average time, or rows examined.

**Step 2 — Inspect recent events**

If history_long is enabled, read SQL_TEXT, TIMER_WAIT, ROWS_EXAMINED, ROWS_SENT, and MYSQL_ERRNO. Check timestamps, threads, and execution counts.

**Step 3 — Inspect the execution plan**

Use EXPLAIN or EXPLAIN ANALYZE in a suitable environment to understand access paths, indexes, joins, and row counts. Performance Schema provides observational metrics only; it does not replace optimizer plans.

**Step 4 — Check waits**

If statement latency is high without matching CPU usage, inspect wait summaries and metadata locks to find time spent waiting on I/O, locks, or synchronization resources.

**Step 5 — Change one variable at a time**

You may adjust an index, query, transaction scope, or configuration. Change only one primary factor per measurement cycle so impact can be clearly attributed.

**Step 6 — Re-measure and document results**

Compare the same digest, workload, and observation window. Record throughput, p95/p99, rows examined, waits, and CPU before and after.

## 12. Common Misconceptions

| Misconception | Reality | Proper Approach |
|---|---|---|
| Instruments and consumers are the same | Instruments emit events; consumers choose where to store them | Inspect setup_instruments and setup_consumers separately |
| Enabling a consumer is enough | Also depends on global/thread layers and instruments | Verify the entire dependency chain |
| TIMED=YES has no cost | Reading timers and recording durations adds overhead | Enable timing only for groups you need to measure |
| History stores every event forever | History is a bounded buffer; old events get overwritten | Export periodically if long-term retention is needed |
| history_long is per-thread | It is a server-wide shared history buffer | Account for load and capacity |
| Digests replace SQL history | Digests aggregate SQL patterns without keeping individual runs | Use history when specific event details are required |
| Performance Schema is an audit log | Data is in-memory, bounded, and non-persistent | Use a dedicated audit mechanism |
| Every instrument is enabled by default | Defaults depend on version and configuration | Query setup tables directly |
| Enabling instrumentation yields past data | Only events occurring after enabling are collected | Wait for workload activity before querying |
| Rising lost counters mean history rollover | Two distinct mechanisms | Distinguish lost counters from ring buffer rollover |
| Memory summary equals process RSS | Includes only instrumented allocations | Compare against OS/container metrics |
| Enable all instruments "just in case" | Broad scope raises overhead and sensitive data exposure | Enable based on hypothesis and investigation window |

## 13. Performance Schema Configuration Checklist

**Before enabling:**

- Confirm performance_schema is ON.
- Save the current state of setup_instruments and setup_consumers.
- Define the investigative question: statement, wait, stage, memory, or lock.
- Select the smallest set of instruments and consumers needed to answer it.
- Check memory budget and history size variables.
- Verify Performance Schema read/write permissions.

**During collection:**

- Enable global/thread consumers if needed.
- Enable only relevant instrument groups.
- Enable TIMED only when latency measurements are required.
- Enable history_long only when server-wide detailed events are required.
- Wait for workload to run after enabling.
- Monitor CPU, latency, memory, and lost counters.

**After investigation:**

- Export metrics that need to be retained.
- Restore initial setup states that are no longer needed.
- Verify dashboards still receive expected data.
- Document changes, time window, and measured overhead.
- Do not leave expanded instrumentation enabled indefinitely without a clear operational goal.

## 14. Key Takeaways

- Performance Schema observes internal MySQL activity using in-memory data.
- Instruments generate events; consumers choose event types and storage destinations.
- setup_instruments controls ENABLED and TIMED; setup_consumers controls where events are stored.
- global_instrumentation and thread_instrumentation are critical layers in the collection flow.
- current shows ongoing activity; history is per-thread; history_long is shared server-wide.
- Summary tables and statement digests are suited for ranking workloads.
- Timers in TIMER_WAIT columns are expressed in picoseconds.
- TIMED=YES provides latency data at the cost of higher measurement overhead.
- History buffers have finite capacity; raising history size increases memory usage.
- setup_actors, setup_objects, and threads help scope collection.
- The sys schema provides readable views over Performance Schema.
- Enabling instruments/consumers collects only events generated after the change.
- Monitor Performance_schema%lost and memory summaries to assess collection limits.
- SQL_TEXT can contain sensitive information; grant read access following least privilege.
- Do not enable all instruments by default; start from an investigative question and measure before/after overhead.

Performance Schema is most effective when configured purposefully. Selecting the right instruments, consumers, and timing level provides sufficient evidence to diagnose workloads while keeping CPU overhead, memory usage, and data sensitivity under control.

## References

- MySQL 8.4 Reference Manual — Performance Schema: https://dev.mysql.com/doc/refman/8.4/en/performance-schema.html
- MySQL 8.4 Reference Manual — Performance Schema Quick Start: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-quick-start.html
- MySQL 8.4 Reference Manual — Performance Schema Instrument Naming Conventions: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-instrument-naming.html
- MySQL 8.4 Reference Manual — Performance Schema Event Consumers: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-consumer-config.html
- MySQL 8.4 Reference Manual — Performance Schema Event Timing: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-timing.html
- MySQL 8.4 Reference Manual — Performance Schema Statement Digests: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-statement-digests.html
- MySQL 8.4 Reference Manual — Performance Schema Memory Allocation: https://dev.mysql.com/doc/refman/8.4/en/performance-schema-memory-model.html
- MySQL 8.4 Reference Manual — The sys Schema: https://dev.mysql.com/doc/refman/8.4/en/sys-schema.html

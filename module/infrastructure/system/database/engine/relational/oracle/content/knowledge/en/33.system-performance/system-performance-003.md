# Choosing Measurement Windows, Computing Counter Deltas, and Avoiding Misinterpretation of Totals

When monitoring Oracle Database performance, many metrics are stored as **cumulative counters**. A value in a view such as V$SYSSTAT typically indicates the total count or volume accrued since a reset point, such as instance startup. A value at a single point in time does not by itself tell you whether the system has been fast or slow over the past few minutes.

To measure a time interval, capture values at two points in time, confirm that both samples belong to the same object and the same lifecycle, and calculate:

\[
\Delta C = C_{\text{end}} - C_{\text{start}}
\]

If a rate of generation is needed:

\[
\text{Rate} = \frac{\Delta C}{\text{Actual elapsed time between the two samples}}
\]

This simple formula only holds when the counter has not reset, the measured object has not been replaced, and both samples share the same scope. If the instance restarts, a session ends, a cursor is reloaded, or a counter decreases, subtraction may no longer be meaningful.

This lesson focuses on choosing measurement windows, identifying counter lifecycles, computing deltas/rates/ratios, reading metrics by instance, session, and SQL cursor, and avoiding wrong conclusions when summing totals or comparing differing intervals.

## 1. Distinguishing Counters, Gauges, and Ratios

Before performing calculations, you must know what type of data the column represents. Not every column named VALUE or COUNT is a cumulative counter.

### 1.1. Cumulative Counters

A counter increases as an event occurs or work is completed. Examples:

- Number of SQL executions.
- Number of commits.
- Number of blocks read logically.
- Number of blocks read physically.
- Bytes of redo generated.
- Total accumulated CPU time or wait time.
- Number of parses.

For instance, if V$SYSSTAT shows the statistic named `redo size` is 8,000,000,000 right now, that is the cumulative value for that statistic and instance scope. It does not mean the database generated 8 GB of redo in the current second.

To find out how much redo was generated in the past 10 minutes, subtract the start value from the end value for that exact 10-minute interval.

### 1.2. Instantaneous Measurements (Gauges)

A gauge represents state at the moment of reading and can rise or fall. Examples:

- Number of active sessions.
- Current number of processes.
- Number of waiting requests.
- Tablespace usage at query time.
- Number of open cursors.

Do not subtract the start value from the end value of a gauge and call it total activity. For example, active sessions dropping from 40 to 20 only shows the active session count at two points in time; a delta of -20 is not the number of sessions that ended during the interval.

For gauges, you typically need to store a series of samples to observe trends, min/max, percentiles, or duration spent in a high state.

### 1.3. Ratios and Averages

Some views provide ratios or averages derived from counters, such as average wait, hit ratio, or average elapsed time.

You cannot always subtract the start ratio from the end ratio. To find the average wait during a measurement window, divide the delta of total wait time by the delta of wait count:

\[
\text{Average wait} =
\frac{\Delta \text{Wait time}}{\Delta \text{Wait count}}
\]

To find the hit ratio for an interval, recalculate it from the deltas of the numerator and denominator. Do not take a simple arithmetic mean of per-snapshot hit ratios unless properly weighted.

### 1.4. Do Not Sum Every VALUE Column into One Total

Each statistic has its own unit and meaning. Examples:

| Statistic | Common unit | Meaning |
| --- | --- | --- |
| session logical reads | buffer/block | Number of logical block reads in the session |
| physical reads | block | Number of blocks read physically |
| redo size | byte | Volume of redo generated |
| execute count | executions | Number of executes |
| user commits | transaction commits | Number of user commits |
| DB time in time model | microsecond | Accumulated database call time per statistic definition |

Do not add 100 redo bytes with 20 executions and 5 block reads to produce one combined number. Addition is only meaningful when components share the same unit or are converted via a well-defined model.

## 2. Define the Measurement Question Before Selecting a Statistic

Do not start by picking a view with many columns. Phrase the performance question as a verifiable measurement.

Examples:

- How many bytes of redo per second does the database generate?
- How many physical blocks does a workload read over 5 minutes?
- How much does execution count increase per transaction?
- What is the average wait time of a wait event during the interval?
- How much CPU did a SQL_ID consume in the recent window?
- How many logical reads did a specific session generate during a request?

For each question, define six elements:

1. **Metric**: which statistic or event answers the question?
2. **Unit**: bytes, blocks, calls, waits, microseconds, or session count?
3. **Scope**: whole instance, one RAC instance, one PDB, session, or SQL cursor?
4. **Lifetime/reset point**: when does the counter start and when can it reset?
5. **Window**: what time interval needs measurement?
6. **Workload denominator**: should it be normalized per request, transaction, row, or execution?

For example, "redo is growing fast" is not specific enough. A better question is: "over the last 300 seconds, how many bytes of redo did instance 2 generate and what was the rate in bytes/second?" This question specifies metric, unit, scope, and window.

## 3. Choosing Measurement Scope in Oracle

Oracle has multiple layers of statistics. Picking the right layer prevents attributing one session's work to the entire database or vice versa.

### 3.1. Instance/System-Level Statistics

V$SYSSTAT provides cumulative system statistics for the current instance. This is commonly used to measure total instance activity between two timestamps.

~~~sql
SELECT name,
       value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
)
ORDER BY name;
~~~

The returned values are cumulative figures at query time. To get deltas, save results at the start and end timestamps.

Statistic names can change across versions or installed features. Check V$STATNAME and the documentation for your running Oracle version instead of hard-coding statistic numbers.

### 3.2. Session-Level Statistics

V$SESSTAT contains per-session statistics. Join with V$STATNAME to look up statistic names:

~~~sql
SELECT ss.sid,
       sn.name,
       ss.value
FROM v$sesstat ss
JOIN v$statname sn
  ON sn.statistic# = ss.statistic#
WHERE ss.sid = :sid
  AND sn.name IN (
      'session logical reads',
      'physical reads',
      'execute count'
  )
ORDER BY sn.name;
~~~

Session statistics are appropriate when you need to know how much work a session generated during its lifetime. They do not represent total activity of the entire database.

A SID can be reused after a session ends. When comparing two samples, verify it is the same session using SID and SERIAL#, and retain LOGON_TIME and INST_ID if needed. Comparing by SID alone can mistakenly pair two different sessions.

### 3.3. SQL Cursor Statistics

V$SQL contains statistics for child cursors currently in the shared SQL area. Common columns include EXECUTIONS, ELAPSED_TIME, CPU_TIME, BUFFER_GETS, and DISK_READS.

These values normally accumulate over the cursor's lifetime. A cursor can be invalidated, aged out, or reloaded; additional child cursors can also appear. Therefore, when comparing two samples, retain at least:

- INST_ID in RAC.
- SQL_ID.
- CHILD_NUMBER.
- PLAN_HASH_VALUE.
- CON_ID if a multitenant environment requires container-level scoping.
- Indicators that the cursor shares the same lifecycle, such as FIRST_LOAD_TIME and relevant identifying attributes.

Do not match solely by SQL_ID and assume two V$SQL rows represent the same counter. One SQL_ID can have multiple child cursors with different plans or environments.

### 3.4. Wait Event Statistics

V$SYSTEM_EVENT contains cumulative wait counts and wait times by event at the instance scope. V$SESSION_EVENT contains wait statistics per session.

~~~sql
SELECT event,
       total_waits,
       time_waited_micro
FROM v$system_event
WHERE wait_class <> 'Idle'
ORDER BY time_waited_micro DESC;
~~~

When computing average wait for an interval, divide the delta of `time_waited_micro` by the delta of `total_waits`. Do not read AVERAGE_WAIT at two timestamps and subtract them.

### 3.5. Time Model Statistics

V$SYS_TIME_MODEL and V$SESS_TIME_MODEL provide cumulative time metrics. Many time model values are measured in microseconds.

~~~sql
SELECT stat_name,
       value
FROM v$sys_time_model
ORDER BY stat_name;
~~~

Verify the unit of each statistic before converting to milliseconds or seconds. Do not assume every time column in every view uses the same unit.

### 3.6. Choosing Scope by Question

| Question | Starting scope |
| --- | --- |
| How much redo does the instance generate? | V$SYSSTAT |
| How many blocks does a session read? | V$SESSTAT |
| How much CPU does a SQL child cursor use? | V$SQL |
| Which events does the instance wait on most? | V$SYSTEM_EVENT |
| How much DB time does a session have? | V$SESS_TIME_MODEL |
| How much redo does the whole RAC cluster generate? | GV$SYSSTAT, compute deltas per instance first, then sum |

## 4. Choosing an Appropriate Measurement Window

Too short a window is easily skewed by sampling timing, background activity, and statistics query overhead. Too long a window can smooth out short slowdowns or blend disparate workloads into one number.

### 4.1. Measure According to the Phenomenon's Timescale

Select the window to match the question:

- Brief spikes lasting a few seconds: requires fine-grained sampling or per-request tracing; 15-minute snapshots will miss detail.
- Hourly load trends: 1–5 minute intervals may work depending on rate of change.
- Comparing a 30-minute batch: sample right before and right after the batch, and record actual timestamps.
- Comparing daily workloads: requires the same hour, similar data scale, same workload, and multiple runs.

These intervals are only starting points. No single sampling interval fits every system.

### 4.2. The Window Must Encompass the Evaluated Work

If measuring a batch, sample before the batch begins and after it completes. Do not capture the start sample after the batch is already underway or capture the end sample before related commits/flushes finish.

If you want to measure a specific request, it is better to tag the request with session/module/action/client identifier or tracing ID to isolate the exact scope. Instance-wide deltas can be affected by concurrent workloads.

### 4.3. Record Actual Timestamps, Do Not Assume Planned Duration

A job scheduled to run 300 seconds may actually take 327 seconds. When computing rates, use the actual elapsed time between the two samples—do not divide by 300 merely because that was the scheduled time.

Use SYSTIMESTAMP to capture timestamps with timezone:

~~~sql
SELECT SYSTIMESTAMP AS captured_at
FROM dual;
~~~

If two timestamps are TIMESTAMP WITH TIME ZONE, their difference yields an INTERVAL DAY TO SECOND. Compute elapsed seconds from that interval or use a verified expression. Do not mix application server timestamps with database timestamps without synchronizing timezones/clocks.

### 4.4. Sample in Steady State

When benchmarking:
1. Complete required startup and warm-up.
2. Wait for caches, connection pools, and workload to reach the target state.
3. Capture the start sample.
4. Run the defined workload.
5. Capture the end sample.
6. Repeat multiple times if comparing.
7. Record concurrency, data volume, plans, and relevant configuration.

Do not mix warm-up with steady-state if the question is steady-state performance. Conversely, if users truly care about startup/warm-up time, measure that phase separately.

### 4.5. Balancing Resolution and Overhead

Every query against statistics views has a cost. Polling too aggressively can create overhead and large volumes of monitoring data; polling too sparsely misses spikes. Pick a frequency sufficient to answer the question, and verify monitoring overhead does not materially alter the workload.

## 5. Delta, Elapsed Time, and Rate Formulas

For a counter C:

\[
\Delta C = C_1 - C_0
\]

Where C0 is the value at the start sample and C1 is the value at the end sample.

Elapsed seconds:

\[
T = t_1 - t_0
\]

Rate:

\[
R = \frac{\Delta C}{T}
\]

For example, `redo size` increases from 2,000,000,000 bytes to 2,600,000,000 bytes in 120 seconds:

\[
\Delta redo = 600{,}000{,}000\ bytes
\]

\[
redo\ rate = 600{,}000{,}000 / 120 = 5{,}000{,}000\ bytes/s
\]

You can convert to MB/s by dividing by 1,048,576 if using MiB, or 1,000,000 if using decimal MB. Explicitly state the unit convention in your report.

### 5.1. Delta Equals Zero

If C1 = C0, the delta is 0. This may mean:
- No events occurred during the window.
- The statistic is not updated by this workload.
- The sampling interval was too short or the statistic has coarser granularity.
- The scope/filter excluded the measured workload.

A delta of 0 does not automatically prove the system is idle.

### 5.2. Negative Delta

For cumulative counters expected never to decrease, a negative delta signals something to investigate:

- Instance restart or statistic reset.
- Session ended and SID was reused.
- SQL cursor was unloaded/reloaded or child cursor changed.
- The two samples belong to different instances/containers.
- The counter has special semantics or documented wraparound.
- Sampled data was paired incorrectly.

Do not apply `ABS(delta)`, do not coerce negative deltas to 0, and do not proceed to compute rates as if the data were valid. First identify why the counter decreased.

### 5.3. Counter Wraparound

Some systems or counters may have bit-width limits and wrap back around upon overflow. Only adjust for wraparound if the statistic's documentation clearly specifies the width and wrap behavior, and you have enough data to know how many wraps occurred in the window.

Do not assume an Oracle counter is 32-bit or 64-bit and apply modulo arithmetic blindly. When exact semantics are unknown, mark the interval invalid and collect a fresh window.

### 5.4. Percentage Change

Percentage change relative to baseline:

\[
\%\ change = \frac{C_1-C_0}{C_0}\times100
\]

If C0 equals 0, percentage change is undefined. In that case, report the absolute delta and rate rather than forcing the percentage to 0 or infinity.

A percentage increase in a counter also does not indicate by itself whether performance improved or degraded. Higher redo may stem from higher transaction volume; higher logical reads may reflect processing more requests or an inefficient query.

## 6. Sampling V$SYSSTAT with Explicit Identifiers

A good sample stores more than just statistic name and value. Record the timestamp, DBID, instance, startup time, and container context so you know whether two values are comparable.

### 6.1. Creating an Illustrative Sample Table

~~~sql
CREATE TABLE perf_counter_sample (
    sample_id        NUMBER NOT NULL,
    captured_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    dbid             NUMBER NOT NULL,
    instance_number  NUMBER NOT NULL,
    startup_time     DATE NOT NULL,
    container_name   VARCHAR2(128),
    statistic_name   VARCHAR2(64) NOT NULL,
    statistic_value  NUMBER NOT NULL,
    CONSTRAINT perf_counter_sample_pk
        PRIMARY KEY (
            sample_id,
            dbid,
            instance_number,
            container_name,
            statistic_name
        )
);
~~~

This is a sample table for practice exercises. In production, you can add host, service, PDB identity, run ID, workload label, build version, and operator. If CONTAINER_NAME can be NULL in a specific environment, adjust the primary/alternate key accordingly.

### 6.2. Capturing the Start Sample

~~~sql
INSERT INTO perf_counter_sample (
    sample_id,
    captured_at,
    dbid,
    instance_number,
    startup_time,
    container_name,
    statistic_name,
    statistic_value
)
SELECT
    1,
    SYSTIMESTAMP,
    d.dbid,
    i.instance_number,
    i.startup_time,
    SYS_CONTEXT('USERENV', 'CON_NAME'),
    s.name,
    s.value
FROM v$database d
CROSS JOIN v$instance i
CROSS JOIN v$sysstat s
WHERE s.name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
);

COMMIT;
~~~

Notes:
- `sample_id = 1` identifies the start sample in this example.
- Statistic name is human-readable, avoiding dependence on statistic numbers.
- Record `startup_time` to detect instance restarts.
- Record container context and only compare samples from the same container scope.
- In multitenant environments, verify the view semantics and CON_ID columns for your version; do not compare PDB metrics with CDB root without clearly defining the scope.

### 6.3. Capturing the End Sample

After the workload completes, capture the second sample with a different `sample_id`:

~~~sql
INSERT INTO perf_counter_sample (
    sample_id,
    captured_at,
    dbid,
    instance_number,
    startup_time,
    container_name,
    statistic_name,
    statistic_value
)
SELECT
    2,
    SYSTIMESTAMP,
    d.dbid,
    i.instance_number,
    i.startup_time,
    SYS_CONTEXT('USERENV', 'CON_NAME'),
    s.name,
    s.value
FROM v$database d
CROSS JOIN v$instance i
CROSS JOIN v$sysstat s
WHERE s.name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
);

COMMIT;
~~~

Do not reuse `sample_id` if you need to retain history. Each run should have its own ID and store both endpoints within the same measurement run.

## 7. Computing Deltas and Rates from Two Samples

The following query pairs the start sample with the end sample by database, instance, container, and statistic. It also detects missing end samples, instance restarts, or counter decreases.

~~~sql
WITH paired AS (
    SELECT
        b.statistic_name,
        b.statistic_value AS begin_value,
        e.statistic_value AS end_value,
        b.startup_time AS begin_startup,
        e.startup_time AS end_startup,
        b.captured_at AS begin_time,
        e.captured_at AS end_time,
        e.sample_id AS end_sample_id
    FROM perf_counter_sample b
    LEFT JOIN perf_counter_sample e
      ON e.sample_id = 2
     AND e.dbid = b.dbid
     AND e.instance_number = b.instance_number
     AND e.container_name = b.container_name
     AND e.statistic_name = b.statistic_name
    WHERE b.sample_id = 1
),
calculated AS (
    SELECT
        statistic_name,
        begin_value,
        end_value,
        CASE
            WHEN end_sample_id IS NULL THEN 'MISSING_END_SAMPLE'
            WHEN begin_startup <> end_startup THEN 'INSTANCE_RESTARTED'
            WHEN end_value < begin_value THEN 'COUNTER_DECREASED'
            ELSE 'OK'
        END AS validation_status,
        CASE
            WHEN end_time IS NOT NULL THEN
                EXTRACT(DAY FROM (end_time - begin_time)) * 86400
              + EXTRACT(HOUR FROM (end_time - begin_time)) * 3600
              + EXTRACT(MINUTE FROM (end_time - begin_time)) * 60
              + EXTRACT(SECOND FROM (end_time - begin_time))
        END AS elapsed_seconds,
        CASE
            WHEN end_sample_id IS NOT NULL
             AND begin_startup = end_startup
             AND end_value >= begin_value
            THEN end_value - begin_value
        END AS delta_value
    FROM paired
)
SELECT
    statistic_name,
    begin_value,
    end_value,
    validation_status,
    elapsed_seconds,
    delta_value,
    CASE
        WHEN validation_status = 'OK'
        THEN delta_value / NULLIF(elapsed_seconds, 0)
    END AS rate_per_second
FROM calculated
ORDER BY statistic_name;
~~~

If `validation_status` is not OK, do not use that delta/rate to draw conclusions. If a statistic is absent from the end sample, it appears as MISSING_END_SAMPLE rather than being silently dropped.

In this example, `sample_id` is fixed to 1 and 2. In practice, pass the run's ID via bind variable or a measurement run metadata table.

### 7.1. Reading Results in the Correct Units

| Statistic | Meaningful delta | Meaningful rate |
| --- | --- | --- |
| redo size | redo bytes generated in the window | bytes/second |
| physical reads | physical blocks read in the window | blocks/second |
| session logical reads | logical buffer reads in the window | buffers/second |
| execute count | executions in the window | executions/second |
| user commits | commits in the window | commits/second |

Do not label every rate as throughput without defining a business unit of work. For example, executions/second is not equivalent to requests/second if one request runs multiple SQL statements.

## 8. Reading Statistic Units and Definitions

A statistic name alone does not reveal the full unit or counting rules. Check Oracle documentation for your exact release and inspect V$STATNAME.

~~~sql
SELECT statistic#,
       name,
       class
FROM v$statname
WHERE name IN (
    'session logical reads',
    'physical reads',
    'redo size',
    'execute count',
    'user commits'
)
ORDER BY name;
~~~

V$STATNAME describes statistics present in the instance. The CLASS column is an internal classification; do not treat it as a unit of measurement.

Examples of common units:
- redo size: bytes.
- physical reads: blocks.
- consistent gets and db block gets: block/buffer operations.
- execute count: execution count.
- user commits: commit count.
- TIME_WAITED_MICRO: microseconds.
- ELAPSED_TIME in V$SQL: microseconds.

A statistic name may stay the same while its interpretation or scope has release-specific details. Do not convert to MB, GB, ms, or seconds until you have verified the unit.

### 8.1. Bytes, Blocks, and Rows Are Not Interchangeable

A physical read operation can read multiple blocks. A logical read counts buffer access operations per the statistic's definition. Rows returned do not necessarily equal blocks read. One SQL statement can perform many executions, or one execution can return many rows.

When reporting, always specify:
- Whether values are bytes or blocks.
- Block size if converting blocks to bytes.
- Whether counts represent executions, parses, fetches, commits, or requests.
- Whether time is in microseconds, milliseconds, or seconds.
- Whether the metric is instance-, session-, or SQL cursor-scoped.

### 8.2. Do Not Derive MB from Block Counts Without Knowing Block Size

If a statistic counts blocks, estimating bytes requires knowing the block size of the relevant tablespace/database and understanding whether the statistic spans multiple block types or special read paths. Never assume every block is 8 KB.

## 9. Computing Rates, Averages, and Ratios from Deltas

Deltas tell you how much occurred during a window. Rates and averages let you compare windows of different durations or different workloads.

### 9.1. Rate per Second

\[
R = \frac{\Delta counter}{elapsed\ seconds}
\]

Example:
- Delta redo size = 900 MB.
- Elapsed = 180 seconds.
- Rate = 5 MB/s using the same MB convention.

Rates let you compare a 3-minute window with a 5-minute window. However, an average rate hides spikes inside the window; sample more frequently if peak behavior matters.

### 9.2. Average Wait Time

Suppose you have deltas:
- time_waited_micro = 2,400,000,000 microseconds.
- total_waits = 120,000 waits.

Average wait:

\[
2{,}400{,}000{,}000 / 120{,}000 = 20{,}000\ microseconds
\]

That equals 20 ms per wait.

In SQL:

~~~sql
SELECT
    delta_time_waited_micro /
        NULLIF(delta_total_waits, 0) / 1000
        AS average_wait_ms
FROM interval_wait_delta;
~~~

If `delta_total_waits` equals 0, the average is undefined. Return NULL or write N/A; never divide by 0 and never force it to 0 ms.

### 9.3. Average Elapsed Time per Execution

Given delta elapsed time and delta executions:

\[
\text{Elapsed per execution} =
\frac{\Delta elapsed\_time}{\Delta executions}
\]

If `elapsed_time` is stored in microseconds, the result is microseconds/execution. Only compare when SQL_ID, child cursor, plan, and scope match. A SQL statement can have individual executions with vastly different durations; an average hides tail latency.

### 9.4. Computing Ratios from Summed Deltas

For example, parse-to-execute ratio over an interval:

\[
\text{Parse per execute} =
\frac{\Delta parse\ count}{\Delta execute\ count}
\]

Example of physical block reads ratio over total logical gets:

\[
\text{Physical read ratio} =
\frac{\Delta physical\ reads}
{\Delta db\ block\ gets + \Delta consistent\ gets}
\]

To express as a percentage, multiply by 100. A common buffer cache hit ratio formula is:

\[
\text{Illustrative hit ratio} =
\left(
1 - \frac{\Delta physical\ reads}
{\Delta db\ block\ gets + \Delta consistent\ gets}
\right)\times100
\]

This is only an indicative reference, not a universal database health score. Direct path reads, workload mix, large scans, and other access paths can make this ratio hard to interpret. Inspect waits, I/O latency, execution plans, and actual workloads as well.

### 9.5. Do Not Average Snapshot Ratios Directly

Suppose:
- Window A has 10 waits, average 1 ms.
- Window B has 1,000 waits, average 10 ms.

The unweighted mean of the two averages is 5.5 ms, but the true average across all 1,010 waits is:

\[
\frac{10\times1 + 1000\times10}{1010}
\approx 9.91\ ms
\]

The right way is to sum total wait time and total wait count, then divide. This is a weighted average by wait count.

## 10. Why Cumulative Totals Easily Mislead

A large number often looks alarming, but without context it does not answer a performance question.

### 10.1. Large Values May Simply Reflect Long Instance Uptime

An instance running for 200 days can have a larger `redo size` than a newly started instance even if its current redo generation rate is much lower.

Comparing cumulative values between two instances with different uptimes is invalid. Compare deltas over the same window or normalized rates.

### 10.2. System-Wide Totals Hide an Outlier Instance

In RAC, the total redo across 4 instances might look normal while one instance carries an abnormally heavy load. Inspect each instance individually before aggregating to the cluster level.

### 10.3. Summing Current Sessions Does Not Equal Total Workload

V$SESSTAT only contains sessions alive at query time. Ended sessions disappear from the view. If you sum currently existing sessions at the start and end samples, the set of sessions differs.

Do not use summed V$SESSTAT values at two timestamps as if they were a system counter with a continuous lifetime. For instance-wide total workload, use instance-level statistics or tracing/telemetry with request identifiers.

### 10.4. One SQL_ID Can Have Multiple Child Cursors

Summing child cursors can be useful when the goal is total activity for a SQL_ID over the same window, but you must first identify which child cursors existed at both endpoints and which appeared or vanished. If the plan changed, merging children can mask a regression in a specific plan.

### 10.5. Total Time Can Exceed Wall-Clock Time

Under concurrency, total DB time or total wait time across multiple sessions can exceed the actual duration of the window. For example, 100 sessions each consuming 1 second of CPU within the same wall-clock second generate approximately 100 seconds of total CPU time.

This is not necessarily a data error. Time counters accumulate across multiple workers/sessions; they do not represent a single system-wide wall clock.

### 10.6. Do Not Sum Consecutive Cumulative Snapshots

Suppose a counter has values:
- 10:00 = 1,000.
- 10:05 = 1,500.
- 10:10 = 1,900.

The sum 1,000 + 1,500 + 1,900 = 4,400 is not the work performed in 10 minutes. The delta for the entire interval is 1,900 - 1,000 = 900. For the two separate 5-minute intervals, the deltas are 500 and 400, respectively.

## 11. Reset Points and Counter Continuity

Every subtraction relies on one assumption: both values belong to the same counter within the same lifecycle.

### 11.1. Instance Restart

V$SYSSTAT contains instance statistics. When an instance restarts, many statistics reset to a fresh baseline. Therefore, always store STARTUP_TIME alongside samples.

~~~sql
SELECT instance_number,
       startup_time,
       status
FROM v$instance;
~~~

If STARTUP_TIME differs between two samples, do not take a delta across them as one continuous window. Split the measurement into two phases or capture a new baseline after the instance stabilizes.

### 11.2. Session Termination

Session-level counters exist per session. When a session disconnects, its statistics no longer refer to the same object for comparison.

When sampling V$SESSTAT, keep:
- INST_ID in RAC.
- SID.
- SERIAL#.
- LOGON_TIME.
- CON_ID or container identity when needed.

If a session disappears or its identifying key changes, mark the sample discontinuous. Never pair a new session merely because it reused an old SID.

### 11.3. SQL Cursor Replacement

V$SQL tracks statistics for cursors currently in the shared pool. Cursors can be aged out, invalidated, or spawn new children. When a cursor is reloaded, counters can start over for the new cursor.

Retain SQL_ID, CHILD_NUMBER, PLAN_HASH_VALUE, INST_ID, and cursor-identifying attributes. If a cursor is absent at the end sample, do not treat the missing value as 0 without an explicit policy.

### 11.4. Manual Resets or Environmental Changes

Certain administrative operations or object lifecycle changes can reset metrics or shift scope. Log events such as:
- Restart/shutdown/startup.
- Failover or switchover.
- RAC reconfiguration.
- PDB open/close or container switching.
- Cursor invalidation/shared pool flush.
- Service/session changes.
- Monitoring tool restarts or missed samples.

### 11.5. When Is a New Baseline Needed?

If a reset or missed sample is detected:
1. Mark the window as interrupted.
2. Do not compute rates across the reset boundary.
3. Document the cause if identifiable.
4. Capture a new baseline.
5. Resume measuring from the new baseline.

Do not attempt to "fix" data using absolute values or interpolation without knowing what actually occurred.

## 12. Measuring in Oracle RAC

In RAC, V$ views typically show data for the current instance. GV$ views provide data from multiple instances and add INST_ID.

~~~sql
SELECT inst_id,
       name,
       value
FROM gv$sysstat
WHERE name IN ('redo size', 'physical reads', 'execute count')
ORDER BY inst_id, name;
~~~

### 12.1. Computing Deltas per Instance

Each instance has its own startup time and lifecycle. The correct procedure:
1. Capture the start value for each INST_ID.
2. Save the startup time for each instance.
3. Capture the end value for each INST_ID.
4. Match on the exact instance, statistic, and container.
5. Verify startup time did not change.
6. Compute per-instance deltas separately.
7. Only then sum the deltas if the question asks for the cluster total.

### 12.2. Instances Joining or Leaving the Cluster

If an instance is missing at either endpoint, do not automatically assume the missing value is 0. The instance may have just started, been stopped, or been unreachable. Report the cluster total as incomplete or isolate the discontinuous instance.

### 12.3. Conditional Cluster Totals

Instance deltas can be summed if:
- Same database and same metric.
- Same unit.
- Same window or compatible elapsed times.
- Each instance has valid start/end samples.
- No restarts/resets occurred within the window.
- Container/workload scope is consistently defined.

Even when reporting a cluster total, retain the per-INST_ID delta breakdown to reveal load imbalances.

### 12.4. Do Not Arbitrarily Sum Rates Across Instances with Different Windows

If each instance has a different elapsed time, do not sum their rates and call it a cluster rate. Sum deltas and total elapsed time under an appropriate definition, or synchronize sampling times so all instances share the same window. When summing rates, understand that the result represents concurrent cluster throughput only when the intervals actually align.

## 13. Measuring by PDB/Container

In a CDB, a single database contains the root and multiple PDBs. Several dynamic performance views and historical views include CON_ID/CON_DBID columns to indicate container scope.

Do not compare:
- Counters at CDB root with counters of a PDB.
- Counters of PDB A with PDB B.
- Two samples captured in different containers.
- Instance-wide metrics with container-scoped metrics.

When using GV$ or DBA_HIST_* in multitenant environments, check which CON_ID/CON_DBID columns are available in your version and view. Match on the exact container identity if provided by the view. If scope cannot be verified, do not report a delta as if the two samples were equivalent.

## 14. Session Counters: Identifying the Exact Session

Example querying session statistics by SID and SERIAL#:

~~~sql
SELECT s.sid,
       s.serial#,
       s.logon_time,
       st.name,
       ss.value
FROM v$session s
JOIN v$sesstat ss
  ON ss.sid = s.sid
JOIN v$statname st
  ON st.statistic# = ss.statistic#
WHERE s.sid = :sid
  AND s.serial# = :serial_number
  AND st.name IN (
      'session logical reads',
      'physical reads',
      'execute count'
  )
ORDER BY st.name;
~~~

In RAC, use GV$SESSION, GV$SESSTAT, and GV$STATNAME, and join on INST_ID as well.

### 14.1. SID Can Be Reused

SID is an instance-local identifier that can be reused after a session ends. SERIAL# distinguishes different sessions reusing the same SID. LOGON_TIME provides additional lifecycle verification.

### 14.2. Session Pooling and Request Boundaries

A connection pool can reuse the same database session across many requests. Session counters accumulate across requests, so a session delta does not automatically equal one request's delta.

To measure a single request:
- Set MODULE/ACTION via DBMS_APPLICATION_INFO.
- Use CLIENT_IDENTIFIER or a tracing ID.
- Capture counters immediately before/after the request if the request holds the session exclusively during that interval.
- Or use SQL trace/telemetry with correlation IDs.
- Prevent other requests from sharing the session concurrently during measurement if accurate attribution is required.

## 15. SQL Cursor Counters: Preserving the Exact Child Cursor

V$SQL can return multiple rows for the same SQL_ID. One child cursor can differ from another due to bind metadata, optimizer environment, authorization, or other reasons.

~~~sql
SELECT inst_id,
       sql_id,
       child_number,
       plan_hash_value,
       executions,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads
FROM gv$sql
WHERE sql_id = :sql_id
ORDER BY inst_id, child_number;
~~~

### 15.1. Cursor Deltas

To compute deltas:
- Match the same INST_ID.
- Match the same SQL_ID and CHILD_NUMBER.
- Check PLAN_HASH_VALUE.
- Verify the cursor has not been replaced.
- Match the same container.
- Use aligned sample timestamps.

If a new child cursor appears in the end sample, it may be a newly created cursor rather than a counter rising from 0 within the old lifecycle. Report the new child separately.

### 15.2. SQL_ID Aggregation and Plan Regressions

If you want total activity for a SQL_ID, you can sum deltas across valid child cursors. However, if a child with a slow new plan appears, aggregation can hide the regression. Always inspect per child/plan first before aggregating.

### 15.3. V$SQLSTATS and AWR

V$SQLSTATS can provide SQL statistics by SQL_ID with a lifecycle helpful for monitoring, though you still need to understand view semantics and potential resets. For longer history, AWR can be used if licensed and configured; DBA_HIST_SQLSTAT provides per-snapshot delta columns. Those DELTA columns already represent the change within the snapshot interval; do not subtract them again as if they were cumulative values.

## 16. Using AWR Snapshots to Compute Historical Deltas

AWR stores many cumulative system statistics per snapshot. You can compare two snapshots with the same DBID and INSTANCE_NUMBER to compute historical deltas.

**Licensing note:** AWR and DBA_HIST_* views fall under the Oracle Diagnostics Pack per Oracle licensing terms. Only use them when your organization holds appropriate entitlements. If unlicensed, consider Statspack or capturing your own samples from authorized dynamic performance views.

### 16.1. Identifying the Snapshot Window

~~~sql
SELECT snap_id,
       dbid,
       instance_number,
       startup_time,
       begin_interval_time,
       end_interval_time
FROM dba_hist_snapshot
WHERE begin_interval_time >= :from_time
  AND end_interval_time <= :to_time
ORDER BY instance_number, snap_id;
~~~

Select snapshots covering the workload window to analyze. Actual snapshot times may not align exactly with the job's start/end times.

### 16.2. Computing Deltas from DBA_HIST_SYSSTAT

~~~sql
WITH snapshot_pair AS (
    SELECT
        b.dbid,
        b.instance_number,
        b.snap_id AS begin_snap_id,
        e.snap_id AS end_snap_id,
        b.startup_time AS begin_startup_time,
        e.startup_time AS end_startup_time,
        b.end_interval_time AS begin_time,
        e.end_interval_time AS end_time
    FROM dba_hist_snapshot b
    JOIN dba_hist_snapshot e
      ON e.dbid = b.dbid
     AND e.instance_number = b.instance_number
    WHERE b.snap_id = :begin_snap_id
      AND e.snap_id = :end_snap_id
)
SELECT
    n.stat_name,
    b.value AS begin_value,
    e.value AS end_value,
    e.value - b.value AS delta_value,
    p.begin_startup_time,
    p.end_startup_time,
    p.begin_time,
    p.end_time
FROM snapshot_pair p
JOIN dba_hist_sysstat b
  ON b.dbid = p.dbid
 AND b.instance_number = p.instance_number
 AND b.snap_id = p.begin_snap_id
JOIN dba_hist_sysstat e
  ON e.dbid = b.dbid
 AND e.instance_number = b.instance_number
 AND e.stat_id = b.stat_id
 AND e.snap_id = p.end_snap_id
JOIN dba_hist_stat_name n
  ON n.dbid = b.dbid
 AND n.stat_id = b.stat_id
WHERE p.begin_startup_time = p.end_startup_time
  AND n.stat_name IN ('redo size', 'physical reads', 'execute count')
ORDER BY n.stat_name;
~~~

If startup time differs, do not treat the two snapshots as a continuous counter series. The query above filters out restart pairs via the equal startup time condition.

In multitenant environments, add join conditions on CON_DBID/CON_ID if those columns exist in the view for your release. Do not join metrics across different containers.

### 16.3. AWR SQL Statistics Already Provide DELTAs

DBA_HIST_SQLSTAT typically provides columns such as EXECUTIONS_DELTA, ELAPSED_TIME_DELTA, CPU_TIME_DELTA, BUFFER_GETS_DELTA, and DISK_READS_DELTA. These represent the amounts changed within the snapshot interval.

Do not subtract start DELTA from end DELTA. To sum across a series of intervals, sum non-overlapping deltas; to evaluate one interval, read that exact snapshot row.

### 16.4. Snapshots Do Not Isolate a Single Request

AWR snapshots usually span a wider window than a single request or batch job. If a snapshot contains multiple concurrent workloads, its delta reflects all activity in that scope. Do not attribute an entire snapshot delta to one SQL statement or one application.

## 17. Aggregating Multiple Intervals Properly

When working across multiple windows, choose an aggregation method appropriate for the metric.

### 17.1. Summing Deltas of Non-Overlapping Intervals

Given three consecutive intervals, with the same scope and no resets:

\[
\Delta_{\text{total}} =
\Delta_1 + \Delta_2 + \Delta_3
\]

The sum of deltas must equal the end counter minus the start counter if the sample series is continuous with no missing intervals.

Never sum cumulative values across individual snapshots.

### 17.2. Overall Average Rate Across Intervals

If intervals have different durations:

\[
R_{\text{total}} =
\frac{\sum \Delta C_i}{\sum T_i}
\]

Do not take an unweighted average of per-interval rates when windows differ in length. The formula above is equivalent to a duration-weighted average.

### 17.3. Overall Average Wait

\[
W_{\text{total}} =
\frac{\sum \Delta wait\_time_i}
{\sum \Delta wait\_count_i}
\]

Do not average per-interval average waits when wait counts differ.

### 17.4. Overall Ratio

\[
Ratio_{\text{total}} =
\frac{\sum \Delta numerator_i}
{\sum \Delta denominator_i}
\]

Do not take a simple average of per-window percentages unless properly weighted and identically defined.

### 17.5. Percentiles Cannot Be Recovered from Totals

Total elapsed time and total execution count yield only an average. They are insufficient to calculate p95/p99 latency. To obtain percentiles, you need histograms, latency samples, or sufficiently detailed tracing data. Never infer tail latency from an aggregate counter.

## 18. Normalizing by Workload

Rates per second allow comparing intervals of different lengths, but can still mislead when work volume changes.

For instance, redo bytes/second may double because transactions/second also doubled. That is not necessarily a regression.

Supplement with metrics per unit of work:

- Redo bytes per transaction.
- Logical reads per execution.
- CPU time per request.
- Physical reads per report.
- Wait time per business operation.
- Rows processed per second.

Formula:

\[
\text{Work-normalized metric} =
\frac{\Delta resource}{\Delta workload}
\]

Example:

~~~sql
SELECT delta_redo_bytes /
       NULLIF(delta_transactions, 0) AS redo_bytes_per_transaction
FROM interval_metrics;
~~~

Use actual transaction counts or reliable business request counters. Do not assume `user commits` equals business requests: one request might commit multiple times, or multiple requests might share one transaction.

### 18.1. Apples-to-Apples Comparisons Require Matching Workloads

When comparing two application versions:
- Use the same dataset or equivalent scale.
- Use the same concurrency.
- Use the same parameters and execution plans unless testing plan changes.
- Separate warm-up from steady-state.
- Record completed requests/transactions.
- Compare resource per unit work alongside latency.

### 18.2. Rising Throughput Alongside Rising Latency

This can indicate the system is processing more requests while approaching resource saturation. Do not judge good/bad from one metric alone. Inspect throughput, p95/p99 latency, queueing, CPU, I/O, waits, and errors together.

## 19. Reading Time Correctly: CPU, DB Time, and Wall-Clock

Time statistics are frequently misinterpreted because they can accumulate across multiple sessions or workers.

### 19.1. Wall-Clock Time

Wall-clock time is the actual elapsed time between two timestamps. It serves as the denominator when computing counter rates over time.

### 19.2. CPU Time

CPU time is the amount of CPU time consumed per the statistic's definition. Total CPU time across multiple sessions can exceed wall-clock time because multiple sessions execute concurrently across multiple CPUs.

### 19.3. DB Time

DB time reflects database call time used by foreground sessions as defined by Oracle. Total DB time can exceed elapsed wall-clock time due to concurrency. Do not interpret 600 seconds of DB time in a 60-second window as an arithmetic bug; multiple sessions were active concurrently.

### 19.4. Wait Time

Total wait time accumulated across sessions can also exceed wall-clock time. Average wait divides total wait time by the corresponding wait count. Do not divide total wait time by the elapsed window and label the result as single-request average latency.

### 19.5. Do Not Arbitrarily Sum CPU Time and Wait Time

Certain time model metrics have specific definitional relationships. Do not blindly add every time column to form a "total time" unless you know whether the intervals overlap. Use well-defined Oracle metrics and document their scopes.

## 20. Common Aggregation and Interpretation Errors

| Mistake | Why it is wrong | Correct practice |
| --- | --- | --- |
| Reading current VALUE and calling it a rate | VALUE is cumulative | Take two samples and compute delta/time |
| Summing VALUE across multiple snapshots | Double-counts historical activity | Sum deltas of non-overlapping intervals |
| Taking ABS(delta) when a counter drops | Masks resets or bad pairing | Flag the interval invalid and investigate |
| Dividing by scheduled duration | Actual elapsed time may differ | Use actual timestamps |
| Comparing instances with different uptime via totals | Different reset baselines | Compare deltas/rates over the same window |
| Pairing sessions by SID alone | SID can be reused | Pair by SID, SERIAL#, LOGON_TIME, and INST_ID |
| Pairing SQL by SQL_ID alone | Multiple child cursors/plans exist | Pair by child, plan, instance, and lifecycle |
| Adding statistics with different units | Sum has no meaning | Keep metrics separate or convert on a valid basis |
| Unweighted mean of averages | Ignores sample weights | Sum numerators/denominators first, then divide |
| Unweighted mean of rates over unequal windows | Different window durations carry different weights | Sum deltas divided by sum elapsed time |
| Calling system delta a single app's delta | Other workloads run concurrently | Measure per session/request or via tracing |
| Using hit ratio as the sole criterion | Ratio ignores latency/load | Combine I/O, waits, latency, and workload |
| Treating DB time > wall-clock as wrong | Concurrency exists | Interpret as summed time across multiple sessions |
| Treating missing end sample as counter 0 | Object may have disappeared | Mark MISSING/UNKNOWN, do not force 0 |
| Treating AWR DELTA as cumulative | DELTA is already the interval change | Use directly or sum non-overlapping intervals |
| Summing cluster rates without aligned windows | Rates cover different intervals | Synchronize samples or compute total delta / total time |

## 21. Checklist for Reliable Measurements

Before publishing results, verify:

1. The measurement question is clearly stated.
2. The chosen statistic fits the question.
3. Statistic units are confirmed.
4. Counters, gauges, averages, and ratios are distinguished.
5. Scope is clearly instance, session, SQL cursor, PDB, or cluster.
6. Sample ID and timestamp are recorded for every point.
7. Both samples share the same DBID.
8. Both samples share the same INST_ID for instance measurements.
9. STARTUP_TIME is unchanged when using instance counters.
10. Session identity is unchanged when measuring sessions.
11. Cursor identity is unchanged when measuring V$SQL.
12. Container identity matches when measuring PDBs.
13. Both start and end samples exist.
14. Elapsed time is computed from actual timestamps.
15. Counters did not decrease or reset within the window.
16. Deltas were not wrapped in ABS or coerced to 0.
17. Rates use consistent units.
18. Ratios are calculated from delta numerators/denominators.
19. Averages are properly weighted.
20. Summed metrics share the same unit and scope.
21. Concurrent workloads are noted.
22. Concurrency and workload volume are recorded.
23. Sampling overhead does not distort the measurement.
24. If using AWR, licensing entitlements are verified.
25. Results are kept per instance/session/child before aggregating.

## 22. Practical Example: Measuring Redo and Execute Rates

Suppose two system statistic samples are collected:

| Checkpoint | Timestamp | Redo size | Execute count |
| --- | --- | ---: | ---: |
| Begin | 10:00:00 | 5,000,000,000 bytes | 8,000,000 |
| End | 10:02:30 | 5,450,000,000 bytes | 8,075,000 |

Elapsed = 150 seconds.

Redo delta:

\[
5{,}450{,}000{,}000 - 5{,}000{,}000{,}000 =
450{,}000{,}000\ bytes
\]

Redo rate:

\[
450{,}000{,}000 / 150 =
3{,}000{,}000\ bytes/s
\]

Execute delta:

\[
8{,}075{,}000 - 8{,}000{,}000 = 75{,}000
\]

Execute rate:

\[
75{,}000 / 150 = 500\ executes/s
\]

Do not conclude that the application processed 500 requests/second. One request can perform multiple executions. Nor conclude higher redo is bad if transaction workload grew. Measure redo per transaction or redo per business request to understand relative cost.

## 23. Practical Example: Detecting a Counter Reset

Suppose:

| Checkpoint | STARTUP_TIME | physical reads |
| --- | --- | ---: |
| Begin | 08:00 same day | 9,000,000 |
| End | 08:10 same day | 120,000 |

The raw delta is negative. Before concluding anything, check:
- Did the instance restart during the window?
- Do both samples have the same DBID and INST_ID?
- Was the wrong PDB or container queried?
- Was there a wrong sample ID or corrupted sample data?
- Does the statistic have special reset semantics?

If STARTUP_TIME differs, these belong to two different instance lifecycles. Do not compute rates across a restart. Capture a fresh baseline after the instance stabilizes.

## 24. Practical Example: Aggregating Two Windows of Different Durations

Suppose:

| Window | Elapsed | Redo delta | Rate |
| --- | ---: | ---: | ---: |
| A | 60 seconds | 120 MB | 2 MB/s |
| B | 300 seconds | 900 MB | 3 MB/s |

Average rate across the full 360 seconds:

\[
(120 + 900) / (60 + 300)
= 2.83\ MB/s
\]

The unweighted average of 2 and 3 is 2.5 MB/s, which is wrong because the two windows have different lengths.

Whether using decimal MB/s or MiB/s, use the same unit across both windows.

## 25. Practical Example: Computing Average Wait from Deltas

Suppose a wait event shows:

| Checkpoint | TOTAL_WAITS | TIME_WAITED_MICRO |
| --- | ---: | ---: |
| Begin | 100,000 | 2,000,000,000 |
| End | 130,000 | 2,750,000,000 |

Delta waits = 30,000.

Delta wait time = 750,000,000 microseconds.

Average wait:

\[
750{,}000{,}000 / 30{,}000
= 25{,}000\ microseconds = 25\ ms
\]

Do not subtract AVERAGE_WAIT at the start checkpoint from AVERAGE_WAIT at the end checkpoint. That is not the interval's average wait.

## 26. Recording Measurement Results and Documenting Limitations

A performance measurement report should store:
- Run ID and measurement objective.
- DBID, instance, container/PDB, service.
- Startup time and version.
- Start/end timestamps.
- Metric name and unit.
- Start value, end value, and delta.
- Elapsed seconds and rate.
- Validation status.
- Workload volume, concurrency, and business request count.
- SQL_ID/plan or session identity if applicable.
- Administrative events occurring during the window.
- Collection method and license/tools if AWR was used.

Example of a strong conclusion:

"During the 10:00:00–10:02:30 window, instance 2 did not restart. Redo size increased by 450 MB over 150 seconds, equivalent to 3 MB/s. Execute count increased by 75,000, equivalent to 500 executes/s. Both metrics are system-level; other workloads may have contributed. Correlate with transaction/request counts before attributing to a single application."

Example of a weak conclusion:

"Redo size is currently 5.45 GB, so the database is generating too much redo."

The second statement lacks a time window, baseline, workload denominator, and any measure of recent growth.

## 27. Self-Practice Exercises

1. Explain the difference between a cumulative counter and a gauge.
2. Why is V$SYSSTAT.VALUE not a rate?
3. Compute the delta when a counter increases from 1,200 to 1,950.
4. Compute the rate if the delta is 750 over 150 seconds.
5. Why should actual elapsed time be used?
6. Distinguish `session logical reads` from `physical reads`.
7. Identify the unit of `redo size`.
8. Why should redo bytes not be added to execute count?
9. List the identifiers that should be saved when measuring V$SYSSTAT.
10. Why must `startup_time` be checked?
11. Why is SID alone insufficient for pairing sessions?
12. List the identifiers that must be preserved when measuring V$SQL child cursors.
13. What causes can produce a negative delta?
14. Why should `ABS(delta)` not be used?
15. When is it valid to adjust for counter wraparound?
16. Compute average wait from delta wait time and delta total waits.
17. Why should you not take a simple average of two average waits with differing wait counts?
18. Compute redo per transaction from two deltas.
19. Why does `user commits` not always equal the business request count?
20. Distinguish DB time from wall-clock time.
21. Why can total DB time exceed the elapsed window?
22. Design a redo rate measurement for one RAC instance.
23. Why should each INST_ID be inspected before computing a cluster total?
24. How should you handle a RAC instance restarting mid-window?
25. State the risks of comparing counters in CDB root against a PDB.
26. DBA_HIST_SQLSTAT has DELTA columns. Do you subtract two DELTAs from each other?
27. Why does an AWR snapshot not necessarily represent a single request?
28. Aggregating a 30-second window and a 300-second window: how do you compute the overall average rate?
29. Why should hit ratio not be the sole metric for evaluating I/O?
30. Design a measurement report containing metric, scope, unit, timestamps, delta, rate, validation status, and workload denominator.

**A cumulative counter only becomes a meaningful performance measurement when backed by two checkpoints sharing the same scope and lifecycle.** Verify identities/reset points, use actual elapsed time, compute deltas before rates, averages, or ratios. Keep units and scopes separate; aggregate only when intervals are compatible. If a counter decreases, a session/cursor disappears, or an instance restarts, mark the window invalid and establish a fresh baseline instead of forcing the numbers into a plausible-looking result.

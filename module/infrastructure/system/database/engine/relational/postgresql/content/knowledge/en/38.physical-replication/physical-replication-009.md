# hot_standby_feedback and the Bloat Trade-off in PostgreSQL

## 1. The problem: queries on a standby can conflict with VACUUM on the primary

PostgreSQL supports hot standby so a replica server can serve read-only queries while receiving and replaying Write-Ahead Log (WAL) from the primary. This mechanism is useful for read scaling, reporting, analytical queries, and offloading read traffic from the primary.

However, the primary must still clean up old tuple versions via `VACUUM`. When `VACUUM` removes a tuple version, the cleanup action is recorded in WAL. The standby replays that WAL; if a query currently running on the standby still needs the removed tuple version, recovery can hit a conflict and PostgreSQL must choose between two goals:

- Keep the standby query running until completion.
- Replay WAL promptly so the standby does not fall too far behind the primary.

`hot_standby_feedback` is a mechanism that reduces an important class of conflicts: conflicts caused by `VACUUM` cleanup. The standby sends information about the oldest transaction snapshot it still needs back to the primary. The primary uses that information to defer removing tuple versions that standby queries may still need.

In return, the primary may have to retain dead tuples longer. If queries on the standby run long or frequently hold old snapshots, dead tuples accumulate on the primary, increasing table/index bloat and storage pressure. This is a trade-off between read query stability on the standby and data cleanup capability on the primary.

```text
                         PRIMARY
                 INSERT / UPDATE / DELETE
                           |
                           v
                    WAL records
                           |
                           v
                    STREAMING WAL
                           |
                           v
                         STANDBY
                    Read-only queries
                           |
             +-------------+-------------+
             |                           |
             v                           v
      Feedback OFF                Feedback ON
             |                           |
             v                           v
  VACUUM cleanup replay       Standby sends old xmin
  may conflict with query     to primary
             |                           |
             v                           v
  Query may be canceled       Primary retains old tuples
  after delay                 for longer
             |                           |
             v                           v
  Less primary retention      Fewer cleanup conflicts
  pressure                    More bloat risk
```

## 2. Learning objectives

After this lesson, you will be able to:

1. Explain why queries on a hot standby can conflict with WAL cleanup.
2. Describe how `hot_standby_feedback` sends `xmin` feedback from standby to primary.
3. Distinguish cleanup conflicts from lock, buffer pin, tablespace, and deadlock conflicts.
4. Understand the trade-off between query cancellation, replay lag, and bloat on the primary.
5. Enable/disable `hot_standby_feedback` on the right side and in the right way.
6. Read `pg_stat_replication.backend_xmin` on the primary.
7. Read `pg_stat_database_conflicts` on the standby.
8. Find long transactions and snapshots on the standby via `pg_stat_activity`.
9. Monitor dead tuple estimates, relation sizes, and `VACUUM` on the primary.
10. Distinguish the feedback horizon from replication slot retention.
11. Understand the role of `max_standby_streaming_delay` and `max_standby_archive_delay`.
12. Explain why low replication lag does not prove the `xmin` horizon is safe.
13. Identify standby queries holding `xmin` too long.
14. Evaluate the combined impact of multiple standbys on the vacuum horizon.
15. Design monitoring and alerts for feedback age, conflict counters, and bloat.
16. Choose configurations matching workloads and read requirements.
17. Handle cases where primary bloat grows after enabling feedback.
18. Run a lab observing query conflicts and feedback.
19. Write runbooks to investigate, reduce bloat, and restore replay progress.
20. Assess operational risks before changing production configuration.

## 3. Hot standby and recovery conflicts

### 3.1. Primary and standby perform different jobs

The primary accepts writes, generates WAL, and runs `VACUUM`. The standby receives WAL and replays it to update the data copy. In hot standby mode, the standby also allows clients to execute read-only queries.

WAL replay must apply changes in order. If a WAL record requires an action incompatible with a snapshot/query running on the standby, a recovery conflict can occur.

### 3.2. Cleanup conflict

Suppose a row on the primary is updated:

1. A transaction on the primary creates a new tuple version.
2. The old tuple version is retained because a snapshot might still need it.
3. Once the primary determines the old version is no longer needed, `VACUUM` can clean up that version.
4. WAL records the cleanup change.
5. The standby replays cleanup WAL.
6. If a query on the standby still needs the old version, replay and the query collide.

Without appropriate protection, PostgreSQL may cancel the standby query so WAL replay can continue.

### 3.3. Standby queries are read-only yet still hold snapshots

A `SELECT` query can hold a snapshot throughout its execution. The snapshot determines which tuple versions the query is allowed to see. Therefore, a query that writes no data can still block cleanup of old tuple versions on the primary when feedback is enabled.

### 3.4. Conflicts are not caused only by VACUUM

Recovery conflicts can also involve:

- Access-exclusive locks from DDL on the primary.
- Dropped or modified tablespaces.
- Buffer pins.
- Deadlocks during recovery.
- Snapshot conflicts from cleanup records.

`hot_standby_feedback` mainly avoids cleanup conflicts by retaining needed tuple versions. It does not guarantee every type of recovery conflict disappears.

### 3.5. Replay and queries must coordinate

If the standby cancels queries, replay can proceed. If the primary retains dead tuples, the standby can complete queries without hitting the corresponding cleanup conflict. No setting eliminates every cost: one side bears the cost of waiting, query cancellation, or retaining old data.

## 4. What is xmin feedback?

### 4.1. xmin and visibility horizon

In MVCC, `xmin` is the transaction ID that created a tuple version. An older snapshot may need to see tuple versions created prior to newer transactions.

PostgreSQL maintains a visibility horizon to track the oldest transaction that can still affect tuple version removal. `VACUUM` cannot clean up certain versions if a valid snapshot might still need them.

### 4.2. The standby sends xmin back to the primary

When `hot_standby_feedback` is enabled on the standby, the standby periodically sends feedback to the primary containing the oldest `xmin` that must be protected for transactions/snapshots on the standby.

The primary uses that feedback to defer cleaning up tuple versions that the standby might still need.

### 4.3. Feedback does not replicate data

Feedback transmits only visibility horizon information. It does not transmit rows, does not replace WAL streaming, does not replace replication slots, and does not replace backups.

### 4.4. Feedback does not turn standby queries into primary transactions

Transaction snapshots on the standby remain part of the standby's read-only workload. The primary receives only the `xmin` boundary to adjust cleanup.

### 4.5. Feedback changes with active snapshots

When queries/transactions holding snapshots end, `xmin` feedback can advance on subsequent status updates. The primary can then clean up more tuple versions during later `VACUUM` runs.

Do not expect dead tuples to vanish the exact instant a standby query finishes. Feedback intervals, `VACUUM` scheduling, and other visibility conditions still apply.

## 5. Enabling hot_standby_feedback

### 5.1. The setting lives on the standby

`hot_standby_feedback` is configured on the standby, since the standby knows which snapshots/queries are active.

Example in the standby's `postgresql.conf`:

```conf
hot_standby_feedback = on
```

Then reload configuration if the version's parameter context allows it:

```sql
SHOW hot_standby_feedback;
SELECT pg_reload_conf();
```

Verify the effective value:

```sql
SHOW hot_standby_feedback;
```

Do not just read the config file. Verify the runtime setting after reload and check logs for configuration errors.

### 5.2. Disabling feedback

```conf
hot_standby_feedback = off
```

When disabled, the standby does not send `xmin` feedback through this mechanism. The primary can clean up tuple versions earlier, though standby queries may be canceled if WAL replay needs to clean up those versions.

### 5.3. Parameter context and reload

`hot_standby_feedback` must be configured on the standby and can typically be applied via reload on supported versions. Check `pg_settings.context`, `source`, and `pending_restart` on the actual server:

```sql
SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name = 'hot_standby_feedback';
```

### 5.4. Do not enable on the primary

This setting belongs on the standby. Toggling it on the primary does not replace feedback from the standby. Edit the right instance and service configuration.

### 5.5. Requires hot standby

The standby must be in a mode supporting read-only queries during recovery. Check `hot_standby` and recovery status:

```sql
SHOW hot_standby;

SELECT pg_is_in_recovery();
```

`pg_is_in_recovery()` returns `true` on a standby replaying WAL.

## 6. The core trade-off: query cancellation or bloat?

### 6.1. When feedback is off

The primary can clean up dead tuples according to its normal vacuum horizon. If cleanup WAL conflicts with a query on the standby, the query may be canceled once the configured delay limit is reached.

Advantages:

- Primary is less likely to retain dead tuples due to standby feedback.
- Reduces one source of table/index bloat.
- Vacuum can advance sooner when standby queries finish or get canceled.

Disadvantages:

- Long analytical queries on the standby can be canceled.
- Clients must retry or split queries into smaller batches.
- Dashboards/reports can fail when replay needs cleanup.
- Operators must manage conflicts and query durations.

### 6.2. When feedback is on

The primary receives the `xmin` horizon from the standby and defers cleaning up tuple versions that may still be needed.

Advantages:

- Reduces cleanup conflicts on the standby.
- Long read-only queries have a chance to complete.
- Reduces errors from queries canceled due to `VACUUM` cleanup.
- Useful for reports/analytics needing stable snapshots.

Disadvantages:

- Dead tuples can remain longer on the primary.
- Heaps and indexes can grow in size/bloat.
- Autovacuum may run yet fail to reclaim tuples pinned by the horizon.
- Storage, I/O, and backup sizes can grow.
- If the horizon is held too long, transaction ID age pressure and vacuum progress require close monitoring.

### 6.3. There is no free configuration

Enabling feedback shifts part of the cost from standby query cancellations to primary tuple retention. Disabling feedback shifts the cost back to standby query cancellations and replay scheduling.

Choose based on query SLAs and primary storage/maintenance limits.

### 6.4. Comparison table

| Criterion | Feedback OFF | Feedback ON |
| --- | --- | --- |
| Cleanup conflict from VACUUM | Can cancel queries | Substantially reduced while feedback is active |
| Long standby queries | Risk being canceled | Have a chance to finish |
| Primary dead tuples | Not held by standby feedback | Can increase |
| Primary bloat | Less pressure from this source | Can grow with snapshot age |
| Vacuum cleanup | Can advance sooner | Can be delayed by `xmin` |
| Replay lag | Query cancellation lets replay proceed | Usually reduces cleanup conflicts, though WAL can still lag for other reasons |
| Best suited for | Standbys prioritizing replay freshness | Standbys prioritizing query continuity |

## 7. Feedback and max_standby_streaming_delay

`max_standby_streaming_delay` determines the maximum time a standby may delay replaying WAL when encountering a conflict in streaming replication before canceling the query.

Example:

```conf
max_standby_streaming_delay = '60s'
```

This is a replay delay limit in conflict contexts, not an absolute timeout per query. A query can run longer than this value if the delay budget has not been spent; conversely, a query can be canceled quickly if replay was already delayed by prior conflicts.

### 7.1. Low values

Low values prioritize replay freshness. Queries on the standby are more likely to be canceled when conflicts occur.

### 7.2. High values

High values give queries more time, while the standby can fall far behind the primary while waiting. If the WAL generation rate is high, lag can grow rapidly.

### 7.3. Value -1

On supported versions, `-1` lets the standby wait indefinitely for certain recovery conflicts. This can keep long queries alive at the cost of unbounded replay stalls. Do not set indefinite delays if SLAs require the replica to stay close to the primary.

### 7.4. Archive delay differs from streaming delay

`max_standby_archive_delay` applies when the standby replays WAL from an archive; `max_standby_streaming_delay` applies to streaming WAL. If a standby uses both WAL sources, configure both settings intentionally.

### 7.5. Feedback and delay are two distinct tools

- Feedback tries to prevent the primary from cleaning up tuple versions the standby still needs.
- Standby delay lets replay wait once a conflict has already occurred.
- Query cancellation lets replay proceed when the delay budget runs out.

Both can be combined, provided you measure bloat and lag to ensure the actual behavior fits.

## 8. Conflict types feedback does not solve

### 8.1. Lock conflicts

DDL on the primary may require `AccessExclusiveLock`. When WAL replay requests a lock conflicting with a standby query, `xmin` feedback cannot prevent that conflict.

### 8.2. Tablespace conflicts

If a tablespace is dropped on the primary while a standby query uses it, recovery may have to cancel the query. Feedback does not shield tablespace objects from that administrative action.

### 8.3. Buffer pin conflicts

A query holding a buffer pin can block replay of an action needing that buffer. This is not purely a cleanup horizon conflict.

### 8.4. Deadlock conflicts

Recovery and query workloads can create deadlock conditions. Feedback does not resolve deadlocks.

### 8.5. Operational takeaway

If `hot_standby_feedback` is enabled yet queries are still canceled, classify the conflicts via `pg_stat_database_conflicts` and logs. Do not assume the setting is broken just because a query was canceled.

## 9. Observing feedback on the primary

### 9.1. pg_stat_replication.backend_xmin

On the primary, `pg_stat_replication` displays information about directly connected standbys. The `backend_xmin` column shows the `xmin` reported by the standby.

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS feedback_xmin_age,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication
ORDER BY age(backend_xmin) DESC NULLS LAST;
```

### 9.2. Interpreting backend_xmin

- Non-NULL value: the standby is reporting an `xmin` horizon to protect.
- High age: old feedback horizon; locate the transaction/query on the standby holding the snapshot.
- NULL: at read time no `xmin` was reported in that row. Do not conclude from NULL alone that the setting is definitely off.

### 9.3. Comparing multiple standbys

With multiple replicas, each standby can report a different horizon. A single standby running a very long query can hold an older `xmin` than all other standbys. When evaluating cleanup, inspect all direct standbys and relevant replication paths.

### 9.4. backend_xmin differs from replay_lag

`replay_lag` reflects statistical replay delay; `backend_xmin` reflects the transaction horizon reported by the standby. A standby with low replay lag can still hold an old `xmin` due to a long transaction/query.

### 9.5. Feedback is not a dead tuple count

The age of `backend_xmin` does not tell you how many dead tuples or GB of bloat exist. Pair it with table statistics, relation sizes, and vacuum logs.

## 10. Finding queries holding snapshots on the standby

### 10.1. Long-running transactions

On the standby:

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    state,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    query_start,
    clock_timestamp() - query_start AS query_age,
    backend_xmin,
    CASE
        WHEN backend_xmin IS NOT NULL
        THEN age(backend_xmin)
    END AS backend_xmin_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

### 10.2. Idle in transaction

A client can `BEGIN`, read data, and leave the transaction open while the application waits. The snapshot can remain even though no query is currently executing.

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    xact_start,
    clock_timestamp() - xact_start AS xact_age,
    state,
    state_change,
    clock_timestamp() - state_change AS state_age,
    backend_xmin,
    left(query, 200) AS last_query
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start;
```

### 10.3. Long queries vs short transactions

Not every long query holds a snapshot across multiple transactions. Check `xact_start`, `query_start`, `state`, and `backend_xmin` together to understand snapshot lifetime.

### 10.4. Application_name

Set meaningful `application_name` values on connection pools and reporting jobs. That lets you pinpoint which service generates long queries instead of seeing only PIDs.

### 10.5. Do not terminate solely because age is high

A query may be a valid report or critical maintenance task. Identify the owner, business impact, cancellation policy, and whether the query can be batched before terminating.

## 11. Monitoring recovery conflicts on the standby

`pg_stat_database_conflicts` records queries canceled due to recovery conflicts.

```sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_catalog.pg_stat_database_conflicts
ORDER BY datname;
```

### 11.1. Counters

| Counter | Meaning |
| --- | --- |
| `confl_tablespace` | Queries canceled due to dropped/altered tablespaces |
| `confl_lock` | Queries canceled due to lock conflicts |
| `confl_snapshot` | Queries canceled due to snapshot/cleanup conflicts |
| `confl_bufferpin` | Queries canceled due to buffer pin conflicts |
| `confl_deadlock` | Queries canceled due to deadlocks during recovery |

### 11.2. Rising counters do not name the canceled query

This view is aggregated by database. To identify specific queries, combine PostgreSQL logs, application logs, and timestamps.

### 11.3. Counters can reset

Statistics resets clear counters. For long-term trends, scrape periodically and store history in an external monitoring system.

### 11.4. Read counters as rates

A database with rapidly rising `confl_snapshot` during reporting hours is likely hitting cleanup conflicts. Compare against query durations, feedback state, and replay lag to assess impact.

## 12. Measuring bloat and dead tuples on the primary

### 12.1. Table statistics

On the primary, inspect estimates:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    round(
        100.0 * n_dead_tup
        / NULLIF(n_live_tup + n_dead_tup, 0),
        2
    ) AS estimated_dead_pct,
    last_autovacuum,
    autovacuum_count,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_catalog.pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 50;
```

`n_dead_tup` is an estimate, not an exact physical count. Watch trends and sizes together.

### 12.2. Inspecting large relations

```sql
SELECT
    c.oid::regclass AS relation,
    pg_size_pretty(pg_relation_size(c.oid)) AS heap_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS index_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
WHERE c.relkind IN ('r', 'm')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 50;
```

### 12.3. Monitoring VACUUM

```sql
SELECT
    p.pid,
    a.datname,
    p.relid::regclass AS relation,
    p.phase,
    p.heap_blks_total,
    p.heap_blks_scanned,
    p.heap_blks_vacuumed,
    a.query_start,
    clock_timestamp() - a.query_start AS runtime,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

If `VACUUM` runs yet dead tuples do not drop, the feedback horizon is one candidate to inspect alongside long transactions, slots, and write workload.

### 12.4. pgstattuple

The `pgstattuple` extension can measure finer-grained tuple/free-space details:

```sql
SELECT *
FROM pgstattuple('public.orders'::regclass);
```

This function can scan the relation and generate significant I/O. Use selectively when diagnosing bloat; never poll all large tables continuously.

### 12.5. Dead tuple estimates do not equal exact bloat percentage

Dead tuples are one component of unreclaimed space. Bloat also depends on page fill, index structure, free space, and space reuse. Do not directly convert `n_dead_tup / n_live_tup` into an exact disk waste percentage.

## 13. Feedback and replication slots

### 13.1. Replication slots have their own purpose

A replication slot retains WAL needed by a consumer. Depending on slot type and state, a slot can also hold `xmin` or `catalog_xmin`, affecting vacuum cleanup.

### 13.2. Feedback horizon vs slot horizon

- `pg_stat_replication.backend_xmin`: `xmin` reported by the standby over the replication connection.
- `pg_replication_slots.xmin`: `xmin` held by the slot.
- `pg_replication_slots.catalog_xmin`: catalog horizon held by the slot.
- `restart_lsn`: WAL position the slot must retain from.

These are related signals, though they should not be collapsed into a single metric.

### 13.3. Inspecting slots on the primary

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    CASE WHEN xmin IS NOT NULL THEN age(xmin) END AS xmin_age,
    catalog_xmin,
    CASE
        WHEN catalog_xmin IS NOT NULL
        THEN age(catalog_xmin)
    END AS catalog_xmin_age,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY GREATEST(
    COALESCE(age(xmin), 0),
    COALESCE(age(catalog_xmin), 0)
) DESC;
```

Some columns apply only to specific slot types; check for NULLs and version differences.

### 13.4. Inactive slots

An inactive slot can still retain WAL or a transaction horizon. Do not drop a slot merely because it is inactive. Verify the consumer, owner, recovery path, and rebuild impact before making changes.

### 13.5. Disconnecting does not necessarily release all retention

A feedback connection disappears when the standby disconnects, yet a replication slot can hold retention state independently. Some configurations/versions also tie the feedback horizon to slots. Inspect `pg_replication_slots` after disconnects rather than guessing from connection state alone.

## 14. Multiple standbys and combined xmin

### 14.1. The oldest standby can hold back the primary

If a primary serves multiple standbys and one reports a very old `xmin`, cleanup can be constrained by that horizon. One replica running a long report can impact cleanup across the entire primary, even if all other replicas stay caught up.

### 14.2. Do not look only at the highest replica lag

A standby with low lag can still hold an old query snapshot. Conversely, a standby with high lag that does not hold an `xmin` may not be the direct cause stopping `VACUUM` from cleaning up tuple versions.

### 14.3. Ranking feedback horizons

```sql
SELECT
    application_name,
    client_addr,
    state,
    backend_xmin,
    age(backend_xmin) AS feedback_xmin_age,
    replay_lag
FROM pg_catalog.pg_stat_replication
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

### 14.4. Identify replica owners

Ensure `application_name` reflects actual roles: reporting, BI, analytics, HA standby, or disaster recovery. Clear ownership helps identify which replica can shorten queries or adjust policy.

### 14.5. Cascading replication

In cascading topologies, understand how feedback is propagated and applied across each replication hop per configuration/version. Observe each upstream connection and slot directly; never assume a query on a leaf standby cannot affect upstream nodes.

## 15. Relationship between feedback and autovacuum

### 15.1. Autovacuum can still run

Enabling feedback does not turn off autovacuum. Workers can still scan heaps, process eligible tuples, update statistics, and freeze what is safe.

### 15.2. Cleanup horizon limits removable tuples

If feedback `xmin` is older than tuple versions `VACUUM` wants to remove, some versions must be retained. `VACUUM` may finish yet leave dead tuple counts high or unchanged.

### 15.3. Repeated vacuuming cannot bypass the horizon

Running `VACUUM` repeatedly while a standby holds the same old `xmin` cannot delete tuples still needed by that snapshot. First identify and address the transaction/query holding the horizon.

### 15.4. Freeze age still needs monitoring

An old vacuum horizon can slow cleanup/freeze advancement in certain cases. Monitor `age(relfrozenxid)`, `age(datfrozenxid)`, and MultiXact age independently of dead tuple metrics.

### 15.5. Anti-wraparound remains critical

Never disable autovacuum or ignore XID age while investigating feedback. If age approaches dangerous thresholds, prioritize anti-wraparound runbooks and address blockers safely.

## 16. Lab: observing query conflicts and feedback

This lab requires two PostgreSQL instances: a primary and a physical standby configured with streaming replication. Do not run on production.

### 16.1. Prepare a table on the primary

```sql
CREATE SCHEMA IF NOT EXISTS hs_feedback_lab;

CREATE TABLE hs_feedback_lab.events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO hs_feedback_lab.events (payload)
SELECT 'event-' || g
FROM generate_series(1, 10000) AS g;

ANALYZE hs_feedback_lab.events;
```

### 16.2. Enable feedback on the standby

On the lab standby:

```conf
hot_standby_feedback = on
```

Reload if supported by your version and verify:

```sql
SHOW hot_standby_feedback;
SELECT pg_is_in_recovery();
```

### 16.3. Open a long query/transaction on the standby

On the standby, open a session:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*)
FROM hs_feedback_lab.events;

-- Keep this transaction open while performing the next steps.
```

In the lab, keep this session open intentionally. Never leave a test transaction like this running indefinitely.

### 16.4. Observe backend_xmin on the primary

```sql
SELECT
    application_name,
    state,
    backend_xmin,
    age(backend_xmin) AS feedback_xmin_age
FROM pg_catalog.pg_stat_replication;
```

Once snapshot feedback has been sent, you can see the reported `xmin`. Timing depends on the status update interval and replication activity.

### 16.5. Generate dead tuples on the primary

```sql
UPDATE hs_feedback_lab.events
SET payload = payload || '-changed'
WHERE id <= 5000;

DELETE FROM hs_feedback_lab.events
WHERE id BETWEEN 7001 AND 8000;
```

### 16.6. Run VACUUM on the primary

```sql
VACUUM (VERBOSE) hs_feedback_lab.events;
```

`VACUUM` must run outside a transaction block. Inspect verbose output and statistics:

```sql
SELECT
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_vacuum
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'hs_feedback_lab'
  AND relname = 'events';
```

With an old feedback horizon, `VACUUM` may have to retain tuple versions still needed by the standby snapshot.

### 16.7. End the transaction on the standby

```sql
COMMIT;
```

Wait for the feedback horizon to advance, then re-run `VACUUM` on the primary and observe the result. Statistics can lag; compare logs and multiple samples rather than a single read.

### 16.8. Test feedback OFF

In a separate lab or after resetting state:

1. Disable `hot_standby_feedback` on the standby.
2. Open a long snapshot query.
3. Generate a cleanup workload on the primary.
4. Monitor `pg_stat_database_conflicts` on the standby.
5. Observe whether the query is canceled when WAL cleanup replay hits a conflict and the delay budget expires.

Exact behavior depends on timing, query snapshot, WAL, and delay settings. Do not expect a short command sequence to reproduce identical conflicts across every version.

## 17. Tuning max_standby_streaming_delay and feedback

### 17.1. Define workload priorities

Before tuning, determine:

- Does the replica serve HA or reporting?
- What is the query duration SLA?
- What is the maximum acceptable replay lag?
- How much storage headroom does the primary have?
- What is the current dead tuple growth?
- Can queries be retried/canceled?

### 17.2. Reporting replicas

A replica dedicated to reporting can prioritize query completion. You can enable feedback and accept the primary retaining dead tuples longer, while bounding query durations, transaction lifetimes, and storage growth.

### 17.3. HA replicas

A standby primarily serving failover usually prioritizes staying close to the primary in replay. You can disable feedback or use shorter delays as needed so primary vacuum cleanup is less constrained by reporting snapshots.

### 17.4. Long delays are not free

Increasing `max_standby_streaming_delay` gives queries more time during conflicts, yet increases replay lag. When a standby lags heavily, both failover freshness and read freshness degrade.

### 17.5. Feedback does not control query lifetime

Enabling feedback does not replace query timeouts, idle-in-transaction timeouts, connection pool policies, or reporting workload management. An open transaction can pin `xmin` even when the application is doing no useful work.

## 18. Mitigating bloat when feedback is still needed

### 18.1. Bound query duration on the standby

Set an appropriate `statement_timeout` for reporting roles or application pools. This lowers the chance of a query pinning a snapshot for hours.

Example on a reporting role:

```sql
ALTER ROLE reporting_user
SET statement_timeout = '15min';
```

This is only an example. Pick timeouts based on query SLAs and how applications handle cancellation.

### 18.2. Avoid idle in transaction

Set an appropriate timeout:

```conf
idle_in_transaction_session_timeout = '2min'
```

Evaluate this timeout against application transaction patterns. On a standby, `idle in transaction` sessions can still hold snapshots.

### 18.3. Split reports into batches

Replace a multi-hour transaction scanning hundreds of millions of rows with queries scoped by clear time/key ranges, each batch holding a shorter snapshot. Ensure pagination and report consistency requirements are preserved.

### 18.4. Isolate reporting workloads

Use a dedicated reporting replica with tailored feedback policy and query timeouts. Do not let a critical HA replica carry long BI workloads if that compromises failover objectives.

### 18.5. Monitor indexes

Dead tuples and bloat affect both heaps and indexes. Track `pg_indexes_size`, index usage, and index health. If `REINDEX` is needed, plan for locking, disk headroom, and version-specific behavior.

### 18.6. Tune autovacuum for the workload

Per-table autovacuum settings can help `VACUUM` start sooner once the horizon advances. However, lowering thresholds cannot make `VACUUM` bypass a protected `xmin`.

## 19. Monitoring dashboard

A solid dashboard combines feedback, query duration, conflict counters, vacuum, and storage.

| Group | Metric | Where to observe |
| --- | --- | --- |
| Feedback | `backend_xmin`, `age(backend_xmin)` | Primary `pg_stat_replication` |
| Replica state | `state`, `sync_state`, `replay_lag` | Primary `pg_stat_replication` |
| Standby queries | xact age, query age, `backend_xmin` | Standby `pg_stat_activity` |
| Conflicts | `confl_snapshot`, `confl_lock`, ... | Standby `pg_stat_database_conflicts` |
| Table cleanup | `n_dead_tup`, `last_autovacuum` | Primary `pg_stat_user_tables` |
| Relation size | heap/index/total bytes | Primary catalogs/functions |
| Vacuum | phase, blocks, runtime | Primary `pg_stat_progress_vacuum` |
| Slots | `xmin`, `catalog_xmin`, `restart_lsn` | Primary `pg_replication_slots` |
| Freeze safety | XID/MXID age | Primary `pg_database`, `pg_class` |
| Storage | disk free, IOPS, latency | OS/storage monitoring |

### 19.1. Alert on feedback age

Alert when `age(backend_xmin)` exceeds baseline for a sustained period, especially when dead tuple estimates or relation sizes grow concurrently.

Do not apply one universal threshold to all clusters. XID consumption rates and transaction rates vary.

### 19.2. Alert on conflict rate

Track deltas of `confl_snapshot` and total conflicts over time. A large cumulative number accumulated over months does not necessarily reflect current state.

### 19.3. Alert on bloat trend

Combine:

- Dead tuple estimates.
- Heap/index size growth.
- `VACUUM` cadence and runtime.
- Feedback `xmin` age.
- Write rate.
- Disk free space.

### 19.4. Alert on replay lag separately

Replay lag is a separate freshness/HA metric. Do not substitute it for the feedback horizon metric.

### 19.5. Store metrics externally

Statistics counters can reset on restarts or stats resets. Scrape periodically and store history in a monitoring system to analyze trends.

## 20. Runbook: primary bloat grows after enabling feedback

### Step 1. Confirm the setting

On the standby, check `SHOW hot_standby_feedback`. On the primary, inspect `pg_stat_replication.backend_xmin`.

### Step 2. Identify the standby holding the old horizon

Rank `backend_xmin` by age and `application_name`. Identify the corresponding replica/consumer.

### Step 3. Find sessions holding snapshots

On that standby, inspect `pg_stat_activity`, especially:

- Oldest transactions.
- `idle in transaction`.
- Long-running analytics/reporting queries.
- Application name and user.
- `backend_xmin` and wait events.

### Step 4. Measure impact on the primary

Check:

- `n_dead_tup` and trends.
- Heap/index/total relation sizes.
- Autovacuum activity.
- XID/MXID age.
- Disk free space and storage latency.

### Step 5. Distinguish causes

Feedback is not the only cause of bloat. Also check write churn, long transactions on the primary, replication slots, prepared transactions, and autovacuum capacity.

### Step 6. Choose remediation

Options include:

- Terminate or split long queries on the standby.
- Cap transaction duration/`statement_timeout`.
- Disable feedback if primary storage/freeze risk outweighs query continuity.
- Adjust standby delay to balance replay and queries.
- Move BI workloads to another replica.
- Increase `VACUUM` capacity once the horizon advances.

### Step 7. Verify the horizon advances

Watch `backend_xmin` on the primary after the query ends. Wait for feedback updates and subsequent `VACUUM` runs. Check dead tuple trends and sizes across multiple samples.

### Step 8. Assess XID safety

If XID age climbs quickly, follow anti-wraparound runbooks. Do not just disable feedback and assume all tuples are reclaimed instantaneously.

### Step 9. Update policy

Document replica role, query SLAs, feedback policy, timeouts, alert thresholds, and owner.

## 21. When should feedback be enabled or disabled?

### 21.1. Consider enabling when

- Standby serves long queries with clear SLAs.
- Query cancellations from cleanup conflicts cause significant business impact.
- Primary has sufficient storage headroom and autovacuum capacity.
- Query lifetimes are bounded and monitoring is complete.
- You can identify which replica holds `xmin`.

### 21.2. Consider disabling when

- Standby prioritizes HA/failover freshness.
- Primary is accumulating bloat or running low on storage.
- XID horizon is pinned too long.
- Standby queries can be retried/batched.
- Reporting workloads can move to a separate replica.
- Monitoring is insufficient to manage retention risk.

### 21.3. Can be enabled per replica role

Not all standbys need the same policy. A reporting replica can enable feedback while an HA standby keeps feedback off, depending on architecture and version. Evaluate each replication path and their combined impact on the primary.

### 21.4. Never enable permanently without measuring

After enabling, baseline and alert on `backend_xmin` age, dead tuples, relation growth, and vacuum. Without measurement, bloat can grow for weeks before causing storage trouble.

### 21.5. Never disable blindly upon seeing one large table

Before disabling, identify which query/standby holds the horizon, the impact of query cancellations, and how reporting will recover. Follow runbooks with clear ownership.

## 22. Feedback and failover

### 22.1. Standby promotion

When a standby is promoted, it becomes primary on a new timeline. Feedback from that standby to the old primary no longer operates in the previous topology.

### 22.2. New replicas

After failover, inspect standbys connecting to the new primary, their feedback settings, and replication slots. Never assume configuration from the old topology automatically fits.

### 22.3. Feedback does not replace replication health

Even with feedback on, monitor WAL receive/replay, slot state, connection state, timeline, and failover readiness.

### 22.4. Standby disconnected

If a standby disconnects, the primary stops receiving new feedback over that connection. However, a replication slot can hold WAL or `xmin` state independently. Inspect slots before concluding the vacuum horizon is clear.

## 23. Common misconceptions

| Misconception | Reality |
| --- | --- |
| `hot_standby_feedback` runs on the primary | The setting is configured on the standby |
| Enabling feedback turns off `VACUUM` | `VACUUM` still runs, yet must keep needed tuples |
| Feedback prevents all recovery conflicts | It mainly reduces cleanup conflicts |
| Read-only queries cannot affect the primary | Their snapshots can pin `xmin` via feedback |
| With feedback on, the primary never bloats | The primary may retain dead tuples longer |
| With feedback off, the standby always cancels queries | Only when conflicts occur and delay policies trigger cancellation |
| `max_standby_streaming_delay` is a per-query timeout | It is a replay delay limit for conflicts |
| Low replay lag means fresh `xmin` | The two metrics measure different things |
| `backend_xmin` is a dead tuple count | It is transaction horizon feedback |
| Dead tuples must hit 0 after `VACUUM` finishes | The horizon may force keeping some versions |
| Adding workers bypasses the feedback horizon | Workers cannot remove tuples still needed by a snapshot |
| Feedback replaces replication slots | Slots and feedback have separate retention semantics |
| Inactive slots are definitely useless | Slots may still be needed or retain WAL/xmin |
| Primary reclaims space the instant a query finishes | Requires feedback update and a subsequent `VACUUM` |
| Disabling feedback shrinks files immediately | `VACUUM` usually reuses space; files may not shrink |
| Bloat happens only in heaps | Indexes can grow in size too |
| `pg_stat_database_conflicts` shows query text | It provides per-database counters |
| `pg_stat_replication` lists all leaf standbys | It shows only standbys connected directly to that server |
| `hot_standby_feedback` replaces backups | It is neither backup nor PITR |
| Every reporting replica needs feedback on | Must balance query SLAs and primary storage |
| Feedback has no effect on XID safety | An old horizon can hinder vacuum/freeze progress |

## 24. Practice exercises with answers

Exercises assume a lab primary and standby. Never toggle feedback or hold long transactions on production just to test.

### Exercise 1. What is hot_standby_feedback?

**Answer:** A mechanism for a standby to send `xmin` feedback to the primary to protect tuple versions that standby queries may still need.

### Exercise 2. Where is this setting configured?

**Answer:** On the standby.

### Exercise 3. Which conflict type does feedback help reduce?

**Answer:** Cleanup conflicts caused by `VACUUM` removing tuple versions that a standby snapshot still needs.

### Exercise 4. Does feedback prevent all recovery conflicts?

**Answer:** No. Lock, tablespace, buffer pin, and deadlock conflicts can still occur.

### Exercise 5. Why can a SELECT query on a standby affect the primary?

**Answer:** The query's snapshot can hold an `xmin`, and feedback makes the primary defer cleanup.

### Exercise 6. Where is xmin feedback observed on the primary?

**Answer:** The `backend_xmin` column in `pg_stat_replication`.

### Exercise 7. What does the age of backend_xmin measure?

**Answer:** The age of the transaction horizon reported by the standby, not the number of dead tuples.

### Exercise 8. What impact can feedback ON cause on the primary?

**Answer:** Retaining dead tuples longer, increasing bloat and storage pressure.

### Exercise 9. What impact can feedback OFF cause on the standby?

**Answer:** Queries can be canceled when cleanup WAL conflicts with snapshots and the delay budget expires.

### Exercise 10. What does max_standby_streaming_delay control?

**Answer:** The maximum time WAL replay can be delayed by recovery conflicts during streaming replication.

### Exercise 11. Is this an absolute timeout for each query?

**Answer:** No. It is a delay budget for WAL replay caused by conflicts.

### Exercise 12. When is max_standby_archive_delay used?

**Answer:** When replaying WAL from an archive on a standby.

### Exercise 13. What does -1 mean for max_standby_streaming_delay?

**Answer:** On supported versions, allows waiting indefinitely for certain conflicts, risking unbounded replay lag.

### Exercise 14. Which view records recovery conflict counters?

**Answer:** `pg_stat_database_conflicts` on the standby.

### Exercise 15. What does confl_snapshot reflect?

**Answer:** Queries canceled due to snapshot/cleanup conflicts.

### Exercise 16. What does confl_lock reflect?

**Answer:** Queries canceled due to lock conflicts.

### Exercise 17. What does confl_tablespace reflect?

**Answer:** Queries canceled due to tablespace conflicts.

### Exercise 18. What does confl_bufferpin reflect?

**Answer:** Queries canceled due to buffer pin conflicts.

### Exercise 19. What does confl_deadlock reflect?

**Answer:** Queries canceled due to deadlocks during recovery.

### Exercise 20. Which view finds queries holding old snapshots on the standby?

**Answer:** `pg_stat_activity`.

### Exercise 21. Why is idle in transaction dangerous?

**Answer:** A transaction can hold an old snapshot even when the session is not executing useful queries.

### Exercise 22. Does feedback replace WAL streaming?

**Answer:** No. WAL streaming delivers changes; feedback only reports the `xmin` horizon.

### Exercise 23. Does feedback replace backups?

**Answer:** No. It does not create recovery points or data copies.

### Exercise 24. Does low replay lag prove feedback xmin is fresh?

**Answer:** No. An old snapshot query can still hold `xmin` while WAL replay keeps up.

### Exercise 25. Can one old standby affect other standbys?

**Answer:** It can pin the primary's cleanup horizon and cause bloat on the primary, affecting the whole system.

### Exercise 26. Do dead tuples vanish immediately when a query ends?

**Answer:** No. Feedback must update and `VACUUM` must run again once tuples are safe to remove.

### Exercise 27. Can adding autovacuum workers delete tuples still needed by a snapshot?

**Answer:** No. Workers must respect the visibility horizon.

### Exercise 28. Can feedback cause autovacuum to run without reclaiming many tuples?

**Answer:** Yes. Workers still run yet must keep versions not yet safe to remove.

### Exercise 29. Which column on the primary shows the feedback horizon?

**Answer:** `pg_stat_replication.backend_xmin`.

### Exercise 30. Which column shows replay lag?

**Answer:** `pg_stat_replication.replay_lag`.

### Exercise 31. Are those two metrics identical?

**Answer:** No. One is a transaction horizon; the other is replay delay.

### Exercise 32. What vacuum-related info can a replication slot hold?

**Answer:** `xmin` and `catalog_xmin`; `restart_lsn` holds WAL position.

### Exercise 33. Can an inactive slot still have an impact?

**Answer:** Yes. It can hold WAL or transaction/catalog horizons depending on slot state/type.

### Exercise 34. Should an inactive slot be dropped immediately?

**Answer:** No. Verify owner, consumer, recovery path, and retention first.

### Exercise 35. Is enabling feedback on all standbys always good?

**Answer:** No. Each standby has different workloads and impacts; policies should match roles.

### Exercise 36. Why might a reporting replica need feedback?

**Answer:** To reduce query cancellations when long reports run and require stable snapshots.

### Exercise 37. Why might an HA replica prefer feedback OFF?

**Answer:** To reduce retention pressure on the primary and prioritize replay freshness, if queries can tolerate retries/cancellations.

### Exercise 38. How does a query timeout help?

**Answer:** Bounds how long a snapshot/query can hold `xmin`, lowering bloat risk.

### Exercise 39. How does splitting reports into batches help?

**Answer:** Each batch finishes its transaction sooner, letting the feedback horizon advance.

### Exercise 40. Why monitor heap and index sizes separately?

**Answer:** `VACUUM` cleanup and bloat can affect heaps and indexes differently.

### Exercise 41. Is n_dead_tup strictly exact?

**Answer:** No. It is an estimate in the statistics view.

### Exercise 42. What is pgstattuple used for?

**Answer:** Measuring detailed tuple and free-space information for a relation.

### Exercise 43. Why not run pgstattuple continuously?

**Answer:** It can scan the entire relation and generate heavy I/O.

### Exercise 44. Does enabling feedback stop VACUUM from running?

**Answer:** No. `VACUUM` still runs, yet cannot remove tuple versions still protected by the horizon.

### Exercise 45. Does feedback protect against DDL lock conflicts?

**Answer:** No. Lock conflicts must be handled separately.

### Exercise 46. Which parameter limits replay delay in streaming?

**Answer:** `max_standby_streaming_delay`.

### Exercise 47. Which parameter enables feedback?

**Answer:** `hot_standby_feedback`.

### Exercise 48. Where can you inspect a setting's context?

**Answer:** `pg_settings.context`, along with `source` and `pending_restart`.

### Exercise 49. When feedback age is high, what is the first investigative step?

**Answer:** Identify the standby via `application_name`/`backend_xmin` and locate the query/transaction holding the snapshot on that standby.

### Exercise 50. With multiple replicas, what should you inspect?

**Answer:** All `backend_xmin` values, query ages, replay lag, and each replica's role.

### Exercise 51. Does disabling feedback shrink relation files immediately?

**Answer:** No. The horizon must advance and `VACUUM` must run; `VACUUM` also usually favors reusing space.

### Exercise 52. Should XID age be monitored when feedback pins a horizon long?

**Answer:** Yes. Holding a horizon long can hinder vacuum/freeze advancement.

### Exercise 53. Does pg_stat_database_conflicts contain query text?

**Answer:** No. It holds per-database counters; use logs/activity/application logs to locate specific queries.

### Exercise 54. Can feedback eliminate all lag?

**Answer:** No. Network, WAL generation, replay throughput, and locks can still cause lag.

### Exercise 55. Does hot_standby_feedback require a reload on the standby?

**Answer:** The setting typically applies via reload on supported versions; verify parameter context and runtime value.

### Exercise 56. When a standby disconnects, is new feedback still sent?

**Answer:** Not over the lost connection; however, a replication slot may maintain separate retention state.

### Exercise 57. If feedback is ON yet queries still get canceled, what should you check?

**Answer:** Categorize conflict counters, check logs, and see whether they are lock/tablespace/bufferpin/deadlock conflicts.

### Exercise 58. Why shouldn't indefinite delay be the default?

**Answer:** Replay can stall indefinitely, degrading failover and read freshness.

### Exercise 59. After ending the query holding xmin, what must be verified?

**Answer:** `backend_xmin` advances, `VACUUM` runs again, dead tuple trends drop, and storage/freeze metrics stabilize.

### Exercise 60. Build a checklist for handling bloat caused by hot_standby_feedback

**Suggested answer:**

1. Verify `hot_standby_feedback` on the standby.
2. Rank `pg_stat_replication.backend_xmin` on the primary by age.
3. Identify the standby/application holding the old `xmin`.
4. Check query age, xact age, and idle-in-transaction on the standby.
5. Read `pg_stat_database_conflicts` to categorize cancellations.
6. Measure dead tuple estimates, heap/index sizes, and vacuum progress on the primary.
7. Check replication slots, `xmin`/`catalog_xmin`, and WAL retention.
8. Choose feedback policy and standby delay per query/replay SLAs.
9. Bound query/transaction durations or isolate reporting workloads.
10. Monitor horizon advancement, `VACUUM` reclamation, and XID safety after changes.

## 25. Production checklist

| Check | What to ensure |
| --- | --- |
| Feedback policy | Each standby has a clear goal |
| `hot_standby_feedback` | Verified on the right standby |
| `backend_xmin` | Monitored on the primary |
| Feedback `xmin` age | Has baseline and alerts |
| `replay_lag` | Monitored separately |
| `max_standby_streaming_delay` | Aligned with query/replay SLAs |
| `max_standby_archive_delay` | Reviewed if replaying archive |
| Standby query duration | Tracked on dashboard |
| Long transactions | Alerted on |
| Idle in transaction | Has timeout/runbook |
| `application_name` | Clearly distinguishes replicas/workloads |
| Conflict counters | Deltas tracked per database |
| Primary dead tuples | Estimates and trends monitored |
| Heap/index sizes | Monitored separately |
| Autovacuum progress | Phase/runtime observed |
| XID/MXID age | Anti-wraparound alerts configured |
| Replication slots | `xmin`/`catalog_xmin`/`restart_lsn` monitored |
| Slot ownership | Owner and recovery plan documented |
| Multiple standbys | Horizons inspected across all replicas |
| Reporting workload | Isolated and bounded appropriately |
| Query timeout | Policy set per role/service |
| Vacuum capacity | Sufficient once horizon advances |
| Storage headroom | Sized for bloat and WAL |
| Failover readiness | Not reliant on a single lag metric |
| Logs | Evidence preserved for query cancellations |
| Stats reset context | Recorded when analyzing counters |
| Restore/HA drills | Tested periodically |
| Configuration changes | Rollout and rollback plan prepared |
| Post-change verification | Feedback, conflicts, bloat, and lag stable |

## 26. Summary

`hot_standby_feedback` lets a standby communicate its `xmin` horizon to the primary to reduce recovery conflicts from `VACUUM` cleanup. It improves completion rates for read-only standby queries, at the cost of the primary potentially keeping dead tuples longer and accumulating bloat.

Key principles:

1. **Feedback is configured on the standby.** The standby knows which snapshots are needed and sends `xmin` back to the primary.
2. **Feedback mainly avoids cleanup conflicts.** Lock, tablespace, buffer pin, and deadlock conflicts can still happen.
3. **Read-only queries still hold xmin.** Long transaction snapshots can impact `VACUUM` on the primary.
4. **Enabling feedback shifts cost to primary retention.** Query cancellations drop while bloat risk rises.
5. **Disabling feedback can cancel queries.** Replay freshness takes priority when cleanup conflicts occur.
6. **backend_xmin and replay_lag are distinct metrics.** Monitor both.
7. **pg_stat_database_conflicts classifies cancellations.** Use logs to find specific queries.
8. **Replication slots have separate retention.** Check `xmin`, `catalog_xmin`, and `restart_lsn`.
9. **Autovacuum still runs when feedback is on.** It must preserve tuple versions protected by the horizon.
10. **Adding workers cannot bypass snapshot horizons.** Address the query/transaction holding `xmin` first.
11. **Bounding query lifetime reduces bloat.** Use statement timeouts, idle transaction timeouts, and batch reporting.
12. **Multiple standbys must be evaluated together.** One old replica can pin the primary's cleanup horizon.
13. **Never use feedback as a substitute for backups or HA monitoring.** It is a visibility-conflict control mechanism.
14. **Tuning must follow SLAs.** Reporting replicas and HA replicas may need different policies.
15. **Verify after changes.** `backend_xmin` should advance, `VACUUM` should reclaim safe tuples, and replay lag must stay within targets.

Decision model:

```text
Standby query canceled due to recovery conflict?
                 |
                 v
        Is it a cleanup conflict?
             /          \
           Yes           No
           |              |
           v              v
  Consider feedback   Investigate lock /
  or standby delay    tablespace / bufferpin
           |
           v
  Does feedback pin xmin too long?
           |
       +---+---+
       |       |
      Yes      No
       |       |
       v       v
 Shorten     Check conflict
 query       logs and delay
 lifetime
 or disable
 feedback
       |
       v
  Does VACUUM advance?
       |
       v
  Verify bloat, XID age,
  replay lag, and query SLA
```

**Final review question:** "If a reporting query on the standby runs for two hours, does the primary know the `xmin` it must preserve? Can we see which replica holds the horizon, how much bloat is growing, and whether `VACUUM` advances after the query ends? If feedback is turned off, are query cancellations and replay lag within acceptable SLAs?" A sound policy answers these questions using metrics from both the primary and the standby.

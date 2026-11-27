# Hot Standby, Read-Only Queries, and Recovery Conflicts in PostgreSQL

Hot standby allows a PostgreSQL standby server to serve read-only queries while continuously replaying WAL from the primary. As a result, a system can use standbys for reporting, lookups, analytics, and offloading read queries from the primary while keeping a replica ready for failover.

However, the standby must serve queries while applying changes recorded in WAL at the same time. A read query may hold a snapshot, lock, or buffer pin that replay operations need to proceed. When the two activities clash, PostgreSQL must balance query response against replay lag. This is a **recovery conflict**.

~~~text
                 Primary PostgreSQL
                 ------------------
                 INSERT / UPDATE / DELETE
                           |
                           v
                     WAL records
                           |
                  Streaming replication
                           |
                           v
                 Standby PostgreSQL
                 ------------------
                    WAL receiver
                           |
                           v
                    Startup process
                     replay WAL
                           |
              +------------+------------+
              |                         |
              v                         v
       Read-only queries          Recovery actions
       SELECT/reporting           VACUUM cleanup
       analytics                  DROP/TRUNCATE
              |                   AccessExclusive lock
              |                         |
              +------------+------------+
                           |
                     Conflict manager
                           |
              +------------+------------+
              |                         |
              v                         v
        Wait for query             Cancel query
        within delay               to replay WAL
              |
              v
       Replay continues
~~~

A standby may answer queries successfully most of the time yet still cancel a long query when WAL replay must advance. Consequently, applications reading from a standby must tolerate query cancellations, know how to retry safely, and monitor both replication lag and recovery conflicts.

This lesson belongs to the **Physical Replication** chapter of the *Database Engine Relational PostgreSQL* module, focusing on hot standby mode, read-only query restrictions, recovery conflict types, how PostgreSQL handles conflicts, and how to operate standbys for read workloads.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain hot standby and distinguish it from warm standby or non-queryable streaming replication.
2. Describe how a standby receives and replays WAL while serving queries.
3. Understand why a standby allows only read operations.
4. Check whether a server is in recovery using `pg_is_in_recovery()`.
5. Distinguish read-only transactions from database role `SELECT` privileges.
6. Explain snapshot, lock, buffer pin, and tablespace conflicts.
7. Recognize recovery conflict counters in `pg_stat_database_conflicts`.
8. Configure `max_standby_archive_delay` and `max_standby_streaming_delay`.
9. Understand why delay limits are not individual per-query maximum durations.
10. Balance query latency with WAL replay lag.
11. Explain `hot_standby_feedback` and the risk of table bloat on the primary.
12. Monitor receive LSN, replay LSN, and replication lag.
13. Read metrics from `pg_stat_replication`, `pg_stat_wal_receiver`, and `pg_stat_activity`.
14. Design query/reporting workloads to minimize recovery conflicts.
15. Handle the error `canceling statement due to conflict with recovery`.
16. Build a safe retry policy for applications reading from standbys.
17. Verify data consistency and latency when reading from a replica.
18. Prepare standbys for failover and perform post-promotion checks.
19. Design monitoring, alerts, and replication drills.
20. Select configurations aligned with RPO, RTO, and read query needs.

## 2. What is hot standby?

Hot standby is the state of a PostgreSQL standby server where the server continues replaying WAL received from the primary while simultaneously allowing clients to connect and execute read-only queries.

### 2.1. Streaming replication

The primary sends WAL to the standby. The standby writes the received WAL, and the startup process replays WAL to update the replica's data files and catalog state.

### 2.2. Hot standby

Once the standby has replayed enough WAL to reach a consistent state, it can accept client connections. Read transactions see the state already replayed on the standby.

### 2.3. Not a second primary

A standby in recovery does not accept normal write operations. It does not create an independent branch of data while still acting as a standby.

### 2.4. Main benefits

- Offload a portion of `SELECT`/reporting traffic to standbys.
- Reduce CPU, I/O, and buffer cache pressure on the primary.
- Allow certain long analytical queries to run without consuming primary query resources.
- Maintain a server actively replaying WAL and ready to be promoted if the primary fails.
- Separate read workloads and write workloads by role.

### 2.5. Operational costs

Standbys require their own CPU, memory, storage, network, and monitoring. Read queries on a standby can impede WAL replay; feedback to reduce conflicts can cause the primary to retain dead tuples longer.

## 3. Standby modes

Distinguish the ability to receive WAL from the ability to serve queries.

| State | Receives/replays WAL | Allows read queries |
| --- | --- | --- |
| Primary | Generates WAL | Yes, read and write per privileges |
| Warm standby | Replays WAL in recovery | Does not serve normal client queries |
| Hot standby | Replays WAL in recovery | Yes, read-only |
| Promoted standby | Becomes new primary | Yes, read and write |

### 3.1. Warm standby

A standby that only replays WAL and waits for failover, without enabling read query service.

### 3.2. Hot standby

A standby opens read connections once it reaches a consistency point and `hot_standby` is enabled.

### 3.3. Promotion

When promoted, the standby exits recovery and becomes a new primary. After promotion, read-only restrictions imposed by recovery no longer apply.

### 3.4. Hot standby is still recovery

`pg_is_in_recovery()` returns true while the server is replaying WAL in standby mode, even when clients are running `SELECT` queries successfully.

## 4. Processing architecture on a hot standby

A standby has key components:

- WAL receiver receives WAL from the primary via the replication protocol.
- WAL files are written to `pg_wal`.
- Startup process replays WAL and applies changes.
- Backend processes serve client queries.
- Recovery conflict manager coordinates queries with conflicting replay actions.

~~~text
Primary
  |
  | WAL stream
  v
WAL receiver
  |
  v
pg_wal on standby
  |
  v
Startup / recovery process
  |
  +----------------------------+
  |                            |
  v                            v
Replay record             Read-only backend
  |                            |
  v                            v
Need cleanup/lock          Holds snapshot/lock/pin
  |                            |
  +-------------+--------------+
                |
                v
          Recovery conflict
                |
       +--------+--------+
       |                 |
       v                 v
    Wait WAL          Cancel query
    replay delay
       |
       v
Replay proceeds
~~~

### 4.1. WAL receiver

The WAL receiver connects to the primary, receives the WAL stream, and writes it to WAL files on the standby. Receiver status can be viewed via `pg_stat_wal_receiver`.

### 4.2. Startup process

The startup process reads WAL and replays records. It must keep pace so the standby does not fall too far behind the primary.

### 4.3. Read-only backend

A backend executes queries using an appropriate snapshot over already-replayed data. Queries may hold an `AccessShareLock`, snapshot, or buffer pin during execution.

### 4.4. Recovery conflict manager

When a WAL record needs to perform an action conflicting with a running query, PostgreSQL can wait for a period of time. If the delay limit is exceeded, the query is canceled so replay can continue.

### 4.5. Replay is asynchronous to queries

Read queries can observe an older state than the primary because the standby only exposes replayed data. This is replication lag, not data corruption.

## 5. Conditions for enabling hot standby

Hot standby configuration depends on the replication setup and PostgreSQL version.

### 5.1. Primary wal_level

The primary needs `wal_level = replica` or `logical` to support physical streaming replication.

~~~conf
wal_level = replica
max_wal_senders = 10
~~~

### 5.2. Standby hot_standby

On the standby:

~~~conf
hot_standby = on
~~~

This is a server startup parameter; changing it requires a restart to take effect.

### 5.3. Standby signal

For PostgreSQL 12 and later, `standby.signal` inside `PGDATA` instructs the server to run in standby mode.

### 5.4. primary_conninfo

The standby needs connection settings pointing to the primary or upstream standby:

~~~conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_reports sslmode=verify-full'
~~~

Manage passwords via a secure mechanism such as a password file or secret store. Never put secrets in source control or logs.

### 5.5. Replication role

The primary needs a role with replication privileges and an appropriate `pg_hba` rule:

~~~sql
CREATE ROLE replicator WITH LOGIN REPLICATION PASSWORD 'replace-with-secret';
~~~

Example `pg_hba.conf`:

~~~conf
hostssl replication replicator 10.20.0.0/24 scram-sha-256
~~~

### 5.6. Checking standby state

~~~sql
SELECT
    pg_is_in_recovery() AS in_recovery,
    current_setting('transaction_read_only') AS transaction_read_only,
    current_setting('hot_standby') AS hot_standby;
~~~

`pg_is_in_recovery()` determines whether the server is still in recovery. `transaction_read_only` reflects the current transaction; `hot_standby` indicates configuration allowing queries during recovery.

## 6. Why does hot standby allow only reads?

The standby replays WAL generated by the primary. If clients modified data independently on the standby, those changes would not exist in the primary's WAL stream and would conflict with replay.

### 6.1. Standard SELECT

Standard `SELECT` queries are permitted once the hot standby is ready.

~~~sql
SELECT count(*) FROM app.orders;
~~~

### 6.2. DML is rejected

Write operations such as `INSERT`, `UPDATE`, `DELETE`, and `MERGE` are not allowed during recovery.

~~~sql
UPDATE app.orders
SET status = 'closed'
WHERE order_id = 100;
~~~

The command above will fail when run on a hot standby.

### 6.3. DDL is rejected

Database structure modifications such as `CREATE`, `ALTER`, and `DROP` cannot be executed on a hot standby.

### 6.4. SELECT FOR UPDATE/SHARE

Queries requiring row-level locking to protect rows from updates are not permitted as on a primary.

~~~sql
SELECT *
FROM app.orders
WHERE order_id = 100
FOR UPDATE;
~~~

### 6.5. Sequence changes

Functions that modify sequence state such as `nextval()` or `setval()` are incompatible with a read-only standby and are rejected in recovery.

### 6.6. Temporary objects

Do not design applications around creating or modifying temporary tables on a hot standby. Hot standby has specific DDL/DML restrictions; if temporary operations are needed, verify exact capabilities for your major version and run that workload on the primary or a separate writable environment.

### 6.7. Read-only transactions

You can explicitly mark a transaction read-only:

~~~sql
BEGIN READ ONLY;
SELECT count(*) FROM app.orders;
COMMIT;
~~~

This communicates application intent. On a hot standby, transactions are already restricted by recovery state even without writing `BEGIN READ ONLY`.

## 7. Checking transaction and server read-only state

### 7.1. Is the server in recovery?

~~~sql
SELECT pg_is_in_recovery();
~~~

- `true`: server is in recovery/standby.
- `false`: server is no longer in recovery, typically a primary or promoted standby.

### 7.2. Current transaction

~~~sql
SHOW transaction_read_only;
~~~

### 7.3. Default transaction mode

~~~sql
SHOW default_transaction_read_only;
~~~

This parameter can be used to default transactions to read-only at a session/role/database level, depending on configuration.

### 7.4. Checking the role

~~~sql
SELECT
    rolname,
    rolsuper,
    rolreplication,
    rolcreatedb,
    rolcreaterole
FROM pg_roles
WHERE rolname = current_user;
~~~

Role `SELECT` privileges must still be granted on databases/schemas/tables. Hot standby does not automatically grant permission to read all data.

### 7.5. Checking from the application

Applications should identify replicas via service discovery/connection metadata or check `pg_is_in_recovery()` when establishing connections. Do not infer roles from hostnames alone if failover can change server roles.

## 8. Reading data on a standby and replication lag

A hot standby serves only replayed state. A transaction just committed on the primary may not be immediately visible on the standby.

### 8.1. Read-after-write

If an application writes an order on the primary and immediately reads that order from a standby, the query may not find the row yet due to replay lag.

### 8.2. Eventual consistency

In asynchronous replication, the standby converges toward the primary's state as WAL is transmitted and replayed, though at any given moment it may lag behind.

### 8.3. Read routing

A common deployment pattern:
- `INSERT`/`UPDATE`/`DELETE` and transactions requiring read-your-writes go to the primary.
- Reports, dashboards, and queries tolerating stale reads go to standbys.
- Queries requiring the latest state can route to the primary or wait until the standby replays up to a recorded LSN.

### 8.4. LSN barrier

An application can obtain the LSN after committing on the primary and wait for the standby to replay up to that LSN before reading, within a timeout budget.

On the primary:

~~~sql
SELECT pg_current_wal_flush_lsn();
~~~

On the standby:

~~~sql
SELECT pg_last_wal_replay_lsn();
~~~

Compare both LSNs within the same timeline/cluster context. Once replay LSN reaches or exceeds the barrier, the corresponding transaction has been replayed up to that position.

### 8.5. Do not compare timestamps alone

`pg_last_xact_replay_timestamp()` can appear old when the primary has no new transactions. LSN is a more accurate progress measure for a specific barrier.

## 9. Types of recovery conflicts

PostgreSQL tracks five primary conflict categories in `pg_stat_database_conflicts`:

| Counter | Conflict group | Example |
| --- | --- | --- |
| `confl_tablespace` | Tablespace | WAL replay drops a tablespace a query is using |
| `confl_lock` | Lock | Replay needs a stronger lock than a query holds |
| `confl_snapshot` | Snapshot | `VACUUM` cleans up row versions a standby snapshot still needs |
| `confl_bufferpin` | Buffer pin | Replay needs to modify/reclaim a page pinned by a query |
| `confl_deadlock` | Deadlock | Recovery conflict creates a deadlock situation requiring resolution |

### 9.1. Tablespace conflict

The primary can drop a tablespace. If a standby query accesses objects in that tablespace, replaying the drop conflicts and the query must terminate so recovery can proceed.

### 9.2. Lock conflict

The primary runs DDL or an operation needing `AccessExclusiveLock`, while a standby query holds `AccessShareLock` on the relation. Recovery cannot wait forever when a delay limit is set.

### 9.3. Snapshot conflict

This is common with long read queries. A query holds a snapshot needing to see older row versions. Primary `VACUUM` can remove those row versions and WAL carries cleanup records. The standby must cancel the query or delay replay.

### 9.4. Buffer pin conflict

A query holds a buffer pin on a page that recovery needs to modify or reclaim. Recovery can wait for the pin to be released; if the limit is exceeded, the query is canceled.

### 9.5. Deadlock conflict

Recovery can encounter deadlocks involving locks/queries on the standby. PostgreSQL detects and resolves these; conflict statistics track this category.

### 9.6. Conflicts do not mean data corruption

PostgreSQL cancels queries to ensure replay progress and consistency. A canceled query is intentional coordination behavior, not automatically standby corruption.

## 10. Snapshot conflicts and VACUUM

Snapshot conflicts warrant close understanding because they frequently occur during long reporting queries on a standby.

### 10.1. MVCC on the primary

PostgreSQL retains multiple row versions so transactions see data consistent with their snapshots. `UPDATE`/`DELETE` create or obsolete row versions; `VACUUM` reclaims unneeded versions.

### 10.2. Snapshots on the standby

A long `SELECT` can hold a snapshot for an extended time. The query needs to read row versions visible to that snapshot.

### 10.3. Cleanup records in WAL

When primary `VACUUM` removes row versions, WAL carries records instructing the standby to perform equivalent cleanup. If a standby query still needs those versions, the two conflict.

### 10.4. Canceling the query or delaying replay

PostgreSQL can wait for the query to finish within the delay limit. Once exceeded, the query is canceled so WAL replay proceeds.

### 10.5. Long-running queries raise conflict probability

A report scanning billions of rows or a read-only transaction holding a snapshot too long widens the window where cleanup can collide.

### 10.6. Do not disable VACUUM on the primary

Never disable autovacuum on the primary just to avoid standby conflicts. That causes table bloat, transaction ID wraparound risk, and far larger operational problems.

## 11. Lock conflicts and DDL

### 11.1. AccessShareLock from SELECT

Normal `SELECT` statements acquire `AccessShareLock` on relations. This lock is compatible with many locks yet conflicts with `AccessExclusiveLock`.

### 11.2. DDL on the primary

Statements such as `DROP TABLE`, `TRUNCATE`, certain `ALTER TABLE` commands, and relation-altering operations require strong locks. When WAL replay applies those changes, standby queries holding locks can be affected.

### 11.3. DDL windows

When possible, run heavy DDL during low standby workload periods. Avoid running long reports simultaneously with migrations needing strong locks.

### 11.4. lock_timeout on the primary does not solve standby conflicts

`lock_timeout` on the primary controls lock wait times for primary sessions. It is not the mechanism governing recovery conflicts on standbys.

### 11.5. Monitoring queries holding locks

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY xact_start NULLS LAST;
~~~

This query helps spot long-running transactions/queries on the standby. Inspect query text carefully as it may contain sensitive data.

## 12. Buffer pin conflicts

A buffer pin is the mechanism by which a backend holds a page in shared buffers for safe access.

### 12.1. Why pins exist

A query needs a stable page while reading or processing data. A buffer pin prevents certain page reclaim/modification operations until the backend releases the pin.

### 12.2. Replay needs the page

The startup process may need to apply a WAL record to a page or perform cleanup. If a query holds a pin, replay must wait.

### 12.3. Large scan queries

Queries scanning many pages, running functions, or holding cursors for long periods can prolong buffer pin conflicts.

### 12.4. Not every buffer pin is an error

Buffer pins are normal. Only when replay needs a held page too long and the delay limit is exceeded can a conflict cause cancellation.

### 12.5. Reducing resource hold time

Split large queries, avoid long-lived cursors, materialize results in the application where appropriate, and avoid keeping transactions open while the client processes data.

## 13. max_standby_archive_delay

This parameter specifies the maximum time the standby may delay replaying WAL fetched from the archive when a recovery conflict occurs.

~~~conf
max_standby_archive_delay = 30s
~~~

### 13.1. Meaning

When replaying WAL from the archive conflicts with a query, the standby can wait up to the configured limit before canceling the query.

### 13.2. Default value

A common default is 30 seconds. Check the active value with:

~~~sql
SHOW max_standby_archive_delay;
~~~

### 13.3. Value -1

`-1` allows the standby to wait indefinitely on conflicts. This can stall WAL replay for a long time and increase replication lag.

### 13.4. Not a query timeout

This is not the maximum duration a single query is allowed to run. Wait time also depends on how long ago the WAL reached the standby and prior conflicts.

### 13.5. Archive replay

This parameter applies only to WAL fetched from an archive. Streaming WAL uses a separate parameter.

## 14. max_standby_streaming_delay

This parameter controls the maximum time the standby may delay replaying WAL received via streaming replication when a conflict occurs.

~~~conf
max_standby_streaming_delay = 30s
~~~

### 14.1. Meaning

When replaying streaming WAL encounters a recovery conflict, the standby can wait for the query to finish within this limit. If the conflict is not cleared in time, the query is canceled.

### 14.2. Value -1

`-1` allows indefinite waiting. Consider replication lag, WAL retention on the primary, and failover requirements.

### 14.3. Difference from archive delay

- `max_standby_archive_delay`: WAL fetched from archive.
- `max_standby_streaming_delay`: WAL received via streaming.

### 14.4. Checking

~~~sql
SHOW max_standby_streaming_delay;
~~~

### 14.5. Impact on standby lag

Larger delays give queries more time, while replay slows down. If the standby uses a replication slot, the primary may have to retain WAL longer and `pg_wal` usage grows.

## 15. Delay limit is not an individual per-query maximum duration

This is a very common point of confusion.

### 15.1. Time is measured relative to WAL

The delay limit bounds how long replay is delayed while processing WAL conflicts, measured from when the WAL was received/entered processing per the respective mechanism.

### 15.2. A new query may have little budget left

If the standby already spent most of the delay budget on a prior conflict within the same WAL window, a newly started query hitting a conflict may be canceled almost immediately.

### 15.3. A query can run longer than the delay

A query that does not encounter a conflict can run longer than the delay value. This parameter does not automatically cancel every query exceeding 30 seconds.

### 15.4. A short query can still be canceled

If WAL replay already waited on prior conflicts and the delay budget is nearly exhausted, a newly started short query may not get much extra time.

### 15.5. Design query SLAs separately

Use `statement_timeout` and application timeouts to bound query duration. Use standby delay settings to balance recovery progress. The two parameter groups solve different problems.

## 16. Configuring conflict delays

Parameters can be configured in `postgresql.conf` on the standby:

~~~conf
hot_standby = on
max_standby_archive_delay = 30s
max_standby_streaming_delay = 30s
log_recovery_conflict_waits = on
~~~

### 16.1. Changing delays

Delay parameters can be reloaded per version context:

~~~sql
SELECT pg_reload_conf();
~~~

Then verify:

~~~sql
SHOW max_standby_archive_delay;
SHOW max_standby_streaming_delay;
SHOW log_recovery_conflict_waits;
~~~

### 16.2. hot_standby

`hot_standby` requires a restart when changed. Do not assume a reload enables hot standby if the server started with it disabled.

### 16.3. log_recovery_conflict_waits

When enabled, PostgreSQL logs recovery conflicts that wait longer than the threshold tied to `deadlock_timeout`. This helps pinpoint prolonged conflicts.

### 16.4. Controlled adjustments

Test delay adjustments on one standby first while monitoring replay lag and query cancellations. Never increase limits indefinitely just to silence application errors.

## 17. hot_standby_feedback

`hot_standby_feedback` lets the standby send feedback about the `xmin` it needs to keep back to the upstream primary, helping the primary avoid `VACUUM` removing row versions that standby queries still need.

~~~conf
hot_standby_feedback = on
~~~

### 17.1. How it works

The standby reports the transaction horizon required to preserve active snapshots. The primary uses this feedback when deciding which tuples cannot yet be safely cleaned up.

### 17.2. Reducing snapshot conflicts

Feedback can reduce snapshot conflicts caused by `VACUUM` cleanup on the primary.

### 17.3. Does not eliminate all conflicts

Feedback does not resolve lock conflicts, tablespace conflicts, or buffer pin conflicts. DDL and other operations can still cancel queries.

### 17.4. Trade-off: bloat on the primary

The primary may have to retain dead tuples longer. If a standby holds an old `xmin` for a long time, `VACUUM` cannot reclaim certain row versions, increasing table/index bloat.

### 17.5. Feedback and replication lag

Feedback reflects the horizon needed by the standby. If the standby lags or queries hold snapshots long, the horizon ages. Monitor both reduced conflicts and dead tuple growth on the primary.

### 17.6. Not an absolute guarantee

Feedback does not guarantee no query will ever be canceled. It only helps avoid one category of conflicts caused by tuple cleanup.

## 18. Should hot_standby_feedback be enabled?

There is no single right choice for every system.

| Workload | Consideration |
| --- | --- |
| Short queries, fast replay required | Can keep off if conflicts are low |
| Long reports needing fewer query cancellations | Consider on and monitor bloat |
| Primary sensitive to table bloat | Be cautious with on |
| Standby prone to long lag | Evaluate feedback horizon and retained dead tuples |
| Multiple standbys | Assess combined impact across all standbys |

### 18.1. When to enable

Prefer enabling when long standby queries are important and snapshot conflicts frequently disrupt work.

### 18.2. When to disable

Prefer disabling when the primary needs `VACUUM` to reclaim tuples promptly, bloat is already an issue, or standby queries can be shortened/rescheduled.

### 18.3. Monitor the primary

Inspect `n_dead_tup`, vacuum progress, table sizes, and transaction horizons. Do not look only at standby query cancellation counts.

### 18.4. Time-scoped toggling

Some environments toggle feedback by workload/standby role. Changes must be controlled, as toggling does not replace clear retention and vacuum policies.

## 19. Where are recovery conflicts recorded?

The `pg_stat_database_conflicts` view provides per-database conflict counts on the standby.

~~~sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
~~~

### 19.1. confl_tablespace

Number of queries canceled due to tablespace conflicts.

### 19.2. confl_lock

Number of queries canceled due to lock conflicts.

### 19.3. confl_snapshot

Number of queries canceled due to snapshot conflicts.

### 19.4. confl_bufferpin

Number of queries canceled due to buffer pin conflicts.

### 19.5. confl_deadlock

Number of queries canceled due to recovery deadlock conflicts.

### 19.6. Counters are cumulative

Counters accumulate since the last statistics reset. Compare deltas across scrapes rather than looking only at absolute totals.

### 19.7. Resetting stats

Stats can be reset by administrative actions or server events. Account for reset timestamps when computing rates and alerts.

## 20. Combining pg_stat_database_conflicts with pg_stat_database

~~~sql
SELECT
    d.datname,
    d.numbackends,
    d.xact_commit,
    d.xact_rollback,
    d.deadlocks,
    c.confl_tablespace,
    c.confl_lock,
    c.confl_snapshot,
    c.confl_bufferpin,
    c.confl_deadlock
FROM pg_stat_database AS d
LEFT JOIN pg_stat_database_conflicts AS c
       ON c.datid = d.datid
ORDER BY d.datname;
~~~

### 20.1. Reading per database

Conflict counters are grouped by database. If one database sees rising snapshot conflicts, focus investigation on queries/reporting in that database.

### 20.2. Reading by delta

Sample counters periodically. Compute increments over each scrape interval and correlate with query cancellation timestamps.

### 20.3. Do not look only at totals

A high historical counter may not reflect a current issue. Alert on rate of increase and application impact.

### 20.4. Combining with logs

Counters identify the conflict category; logs reveal exact timestamps, queries/backends, and wait durations. Both are needed for root-cause investigation.

## 21. Monitoring replication lag from the primary

On the primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

### 21.1. sent_lsn

WAL position sent to the standby.

### 21.2. write_lsn

WAL position written by the standby to the filesystem.

### 21.3. flush_lsn

WAL position durably flushed by the standby.

### 21.4. replay_lsn

WAL position replayed by the standby into data state.

### 21.5. Lag fields

Lag fields are latency statistics over recent stages, not always an exact measurement of current distance. When the standby is idle, values may be null or not reflect lag intuitively.

### 21.6. LSN difference

You can compute byte differences between the primary's current flush LSN and the standby's replay LSN when both belong to the same replication history:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_behind
FROM pg_stat_replication;
~~~

The result is a WAL distance in bytes, not seconds. Converting to time requires WAL generation rate and workload context.

## 22. Monitoring on the standby

### 22.1. Recovery state

~~~sql
SELECT pg_is_in_recovery();
~~~

### 22.2. Receive and replay LSN

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn;
~~~

### 22.3. Replay lag in bytes

~~~sql
SELECT pg_wal_lsn_diff(
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn()
) AS received_not_replayed_bytes;
~~~

If either LSN is null, the standby has not yet received/replayed WAL in its current state or the function has no data to return.

### 22.4. Replay timestamp

~~~sql
SELECT pg_last_xact_replay_timestamp();
~~~

This timestamp is not a reliable lag clock when the primary is not generating transactions.

### 22.5. WAL receiver state

~~~sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    latest_end_time,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
~~~

This view usually contains one row when the WAL receiver is connected. Columns can vary by version.

## 23. Monitoring long queries on the standby

Long queries are a primary factor increasing recovery conflict probability.

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    xact_start,
    query_start,
    now() - query_start AS query_age,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY xact_start NULLS LAST;
~~~

### 23.1. Query age

Elapsed time since query start helps identify prolonged queries.

### 23.2. Transaction age

A transaction may stay open long even if the current query is short or the backend is `idle in transaction`. Snapshots may still be held.

### 23.3. Idle in transaction

An `idle in transaction` session can hold snapshots/locks longer than necessary. Set `idle_in_transaction_session_timeout` per appropriate policy.

### 23.4. Wait events

`wait_event_type` and `wait_event` help identify what resource a backend is waiting on. Wait event names vary by version; recovery conflicts can also cancel queries instead of waiting indefinitely.

### 23.5. Avoid logging sensitive queries

Query text may contain literal data. Restrict access permissions and align with logging policy.

## 24. log_recovery_conflict_waits

This parameter logs prolonged WAL replay waits caused by recovery conflicts.

~~~conf
log_recovery_conflict_waits = on
deadlock_timeout = 1s
~~~

### 24.1. Purpose

When the recovery process is delayed by a conflict longer than the threshold tied to `deadlock_timeout`, PostgreSQL logs an entry to aid investigation.

### 24.2. Does not replace conflict counters

`pg_stat_database_conflicts` counts canceled queries by category; `log_recovery_conflict_waits` exposes long waits. Both sources complement each other.

### 24.3. Log volume

If conflicts happen frequently, enabling logging can raise log volume. Configure proper log rotation and retention.

### 24.4. Investigating from logs

Correlate log timestamps with `query_start`/`xact_start`, DDL/`VACUUM` on the primary, and conflict counters on the standby.

## 25. Impact of delay settings on WAL retention

When a standby delays replay to wait for queries, received-but-unreplayed WAL accumulates.

### 25.1. Replay lag increases

Larger delays allow the standby to fall further behind the primary while queries hold conflicts.

### 25.2. Replication slots

If the standby uses a physical replication slot, the primary retains WAL the slot still needs. Prolonged replay or receiver lag can cause slots to retain large amounts of WAL.

### 25.3. Disk pressure on the primary

WAL retained by slots can cause `pg_wal` on the primary to grow. Without monitoring, the disk can fill and impact the entire cluster.

### 25.4. Without slots

If a standby falls too far behind and required WAL is recycled, the standby may be unable to resume streaming. A WAL archive may be needed to catch up, or the standby may need rebuilding.

### 25.5. Indefinite delay has a cost

`max_standby_streaming_delay = -1` protects queries from conflict cancellation yet can stall replay indefinitely. Evaluate storage, failover readiness, and RPO.

## 26. Designing read workloads for hot standby

### 26.1. Split large reports

Replace multi-hour full scans with smaller time-range or key-range queries when business logic allows.

### 26.2. Avoid long-open transactions

Do not keep read-only transactions open while users view results or await interaction. Fetch paginated data and close transactions promptly.

### 26.3. Use stable pagination

Keyset pagination typically avoids large offset scans and reduces query duration compared to deep `OFFSET` pagination.

### 26.4. Optimize indexes

Create appropriate indexes on the primary via migration procedures. Good indexes reduce pages scanned and the time snapshots/locks are held on the standby.

### 26.5. Materialized reporting

If reports are very heavy, consider materializing summary tables on the primary or via a separate ETL pipeline, then querying an analytical store. Hot standbys are not always suited for long OLAP workloads.

### 26.6. Query timeouts

Set `statement_timeout` per workload class. This protects the server against runaway queries; it is independent of recovery delay settings.

### 26.7. Pooling

Use connection pooling to bound backend counts, avoid `idle in transaction` sessions, and route read/write endpoints cleanly.

## 27. Routing queries between primary and standby

### 27.1. Primary endpoint

Use for writes, DDL, transactions needing read-your-writes, and queries requiring the freshest data.

### 27.2. Standby endpoint

Use for `SELECT` queries that tolerate replication lag and potential query cancellation.

### 27.3. Do not split a single transaction arbitrarily

A transaction that reads and then writes must stay on the primary. Never split statements of the same transaction across two different servers.

### 27.4. Session consistency

If a session writes to the primary and then reads from a standby, results may be stale. Tie routing policies to request consistency requirements.

### 27.5. Retry policy

When a query is canceled due to a recovery conflict, the application may retry on the standby or fall back to the primary depending on business rules. Retries must be bounded with backoff to avoid amplifying load.

### 27.6. Classifying queries

You can classify queries into:
- Strong read: needs latest data, route to primary.
- Eventual read: tolerates lag, route to standby.
- Long report: route to a dedicated reporting standby with timeouts and scheduling.
- Write transaction: always route to primary.

## 28. Handling canceling statement due to conflict with recovery

Typical message:

~~~text
ERROR: canceling statement due to conflict with recovery
DETAIL: User query might have needed to see row versions that must be removed.
~~~

The `DETAIL` message varies by conflict type.

### 28.1. This is query cancellation

PostgreSQL canceled the statement on the standby so recovery could continue replaying WAL.

### 28.2. Check counters

~~~sql
SELECT *
FROM pg_stat_database_conflicts
WHERE datname = current_database();
~~~

### 28.3. Identify the conflict type

- Rising `confl_snapshot`: inspect long queries and `VACUUM` cleanup on the primary.
- Rising `confl_lock`: inspect DDL/strong locks on the primary.
- Rising `confl_bufferpin`: inspect queries pinning pages/buffers too long.
- Rising `confl_tablespace`: inspect `DROP TABLESPACE` operations.
- Rising `confl_deadlock`: investigate lock/recovery interactions via logs.

### 28.4. Check query and transaction age

Use `pg_stat_activity` to locate sessions with old `xact_start`/`query_start`.

### 28.5. Check delays

Inspect `max_standby_streaming_delay` and `max_standby_archive_delay`. Determine whether conflicting WAL came via streaming or archive.

### 28.6. Choose remediation

Shorten queries, move queries to the primary, raise delays within bounds, enable feedback if appropriate, or isolate workloads to a dedicated standby.

### 28.7. Controlled retries

Never retry endlessly. Use exponential backoff, cap retry attempts, and distinguish conflict errors from other SQL errors.

## 29. Retrying queries safely

Read queries can usually be retried, though side effects still need checking.

### 29.1. Pure SELECT

A pure `SELECT` without application side effects can be retried on the same standby or the primary.

### 29.2. Functions with side effects

Do not assume every `SELECT` statement is state-free. Functions might call external services or create side effects outside the database. Verify function semantics before retrying.

### 29.3. Cursors and transactions

If a transaction/cursor was canceled, you normally must open a new transaction and rerun the query from the beginning. Do not keep using a failed cursor.

### 29.4. Retry budget

Set a maximum retry count and total duration. Once exhausted, return a meaningful error or fall back to the primary if policy permits.

### 29.5. Backoff

Use exponential backoff with jitter so multiple clients do not retry simultaneously after a wave of recovery conflicts.

### 29.6. Record metrics

Track retry counts, cancellation counts, query latency, and fallback routing to spot when a standby no longer fits the workload.

## 30. Interaction with autovacuum on the primary

Autovacuum on the primary generates cleanup records that are replayed on the standby.

### 30.1. Never disable autovacuum to appease standbys

Disabling autovacuum causes table bloat, higher query costs, and transaction ID wraparound risk.

### 30.2. Tune autovacuum purposefully

If `VACUUM` aggressively triggers conflicts, inspect table-level thresholds, workload churn, vacuum cost settings, and DDL schedules. Base adjustments on primary metrics.

### 30.3. hot_standby_feedback trade-off

Feedback reduces snapshot conflicts at the cost of retaining dead tuples on the primary. Measure bloat before and after enabling.

### 30.4. Multiple standbys

A single standby holding an old `xmin` affects cleanup on the primary. With multiple replicas, evaluate the combined horizon across all consumers and slots.

### 30.5. Inspecting dead tuples

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Numbers are statistical estimates, not exact live row counts.

## 31. Monitoring replication slots and retained WAL

On the primary:

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

### 31.1. restart_lsn

Oldest WAL position the slot still needs. If it remains old for long, large amounts of WAL may have to be retained.

### 31.2. wal_status

Status indicating whether the slot can continue receiving WAL, depending on version and retained WAL state.

### 31.3. safe_wal_size

On supported versions, shows how much more WAL can be generated before the slot risks exceeding the WAL retention limit.

### 31.4. max_slot_wal_keep_size

Caps the WAL a slot can retain. Limits protect disk space, though slow consumers may lose continuity and require rebuilding.

### 31.5. Never delete WAL manually

Never delete files inside `pg_wal` to free disk space. Manage slots, archives, and retention through PostgreSQL mechanisms.

## 32. Impact on failover readiness

Hot standbys often both serve reads and act as failover candidates.

### 32.1. Replay lag

Heavy standby lag can lose transactions committed on the primary when failing over to an asynchronous standby.

### 32.2. Conflict delays

Large delays give queries more runtime at the expense of slowing standby replay. This can leave the replica less up to date when promoted.

### 32.3. Synchronous replication

Synchronous replication reduces the risk of losing acknowledged transactions per configured sync level. `synchronous_commit` values such as `remote_write`, `on`, and `remote_apply` have distinct semantics.

### 32.4. remote_apply

With an eligible synchronous standby and `synchronous_commit = remote_apply`, commits on the primary wait until the transaction is replayed on the standby. This supports read-after-write when read queries start after commit with a fresh snapshot.

### 32.5. Does not eliminate all lag automatically

A standby can lag due to query conflicts, network, disk, or WAL receiver issues. Measure replay progress and define failover policy.

### 32.6. Promotion

Before promoting, evaluate timeline, replay LSN, fencing of the old primary, and procedures to reconfigure remaining replicas.

## 33. Sample configuration for a reporting standby

Example standby configuration serving reports with bounded delay:

~~~conf
hot_standby = on
max_standby_streaming_delay = 60s
max_standby_archive_delay = 60s
hot_standby_feedback = on
log_recovery_conflict_waits = on
~~~

### 33.1. Purpose

- Give queries more time before cancellation.
- Reduce snapshot conflicts via feedback.
- Log prolonged recovery waits.

### 33.2. Costs

- Replay lag can increase.
- Primary may retain dead tuples longer.
- Replication slots may retain more WAL.
- Disk usage and failover freshness require monitoring.

### 33.3. Do not copy templates blindly for every environment

60 seconds is only an example. Tune based on query SLAs, WAL rate, disk headroom, standby count, and RPO.

### 33.4. Standby dedicated to failover

If prioritizing failover freshness, use shorter delays, feedback off, or a dedicated standby with minimal query load. Long reporting workloads should be isolated onto a separate replica if resources permit.

## 34. Testing hot standby end-to-end in a lab

### Step 1. Create primary

Initialize an isolated lab PostgreSQL primary and configure `wal_level=replica`, WAL senders, and replication authentication.

### Step 2. Create standby

Use `pg_basebackup` with `-R` or an appropriate standby procedure, then start the standby.

### Step 3. Confirm recovery

On the standby:

~~~sql
SELECT pg_is_in_recovery();
~~~

Result must be `true` while the standby operates in recovery.

### Step 4. Run SELECT

~~~sql
SELECT now(), count(*) FROM app.orders;
~~~

Read queries are served on the hot standby once the server reaches a consistency point.

### Step 5. Test DML

~~~sql
INSERT INTO app.orders(order_id) VALUES (900001);
~~~

The statement must be rejected in recovery state.

### Step 6. Generate workload on the primary

Run `UPDATE`/`DELETE`/`VACUUM` in the lab to generate WAL records capable of conflicting with standby queries.

### Step 7. Run a long query on the standby

Use a `SELECT` holding a long snapshot in the lab. Observe whether the query gets canceled when replay hits a cleanup conflict.

### Step 8. Read conflict stats

~~~sql
SELECT *
FROM pg_stat_database_conflicts;
~~~

### Step 9. Test delay settings

Adjust `max_standby_streaming_delay` in the lab, reload configuration, and observe query cancellation/replay lag.

### Step 10. Test feedback

Toggle `hot_standby_feedback` in the lab and observe snapshot conflicts alongside dead tuple retention on the primary.

### Step 11. Compare LSNs

Measure receive/replay LSN on the standby and sent/replay LSN on the primary.

### Step 12. Record results

Record query latency, conflict counters, replay lag, primary bloat indicators, and impact on failover readiness.

## 35. Conflict handling checklist

When an application reports a canceled query:

1. Record `SQLSTATE`, message, timestamp, and `application_name`.
2. Identify which standby executed the query.
3. Read `pg_stat_database_conflicts` and compute counter deltas.
4. Identify which conflict group increased.
5. Check `query_start` and `xact_start`.
6. Check DDL/`VACUUM` on the primary around the same time.
7. Identify whether WAL arrived via streaming or archive.
8. Check `max_standby_streaming_delay` and `max_standby_archive_delay`.
9. Measure replay lag and WAL backlog.
10. Check replication slots and retained WAL on the primary.
11. Assess `hot_standby_feedback` and dead tuple growth.
12. Shorten queries or move workloads if possible.
13. Increase delays within bounds if read SLAs require it.
14. Configure retry budgets/backoff in the application.
15. Monitor conflict rates and replay freshness after changes.

## 36. Common mistakes

### Mistake 1. Assuming a standby always reads the latest data

A standby sees only replayed WAL. Use the primary or an LSN barrier for read-after-write.

### Mistake 2. Query canceled yet no SQL error appears on the primary

Recovery conflicts happen on the standby; inspect `pg_stat_database_conflicts` and standby logs.

### Mistake 3. Setting indefinite delays

Replay can stall for long periods, increasing lag and retaining WAL on the primary. Choose delays based on SLAs and capacity.

### Mistake 4. Enabling feedback without monitoring bloat

The primary may retain dead tuples longer. Monitor `n_dead_tup`, vacuum runs, and table/index growth.

### Mistake 5. Disabling autovacuum on the primary

This causes bloat and wraparound risks. Tune workloads/vacuum using metrics instead.

### Mistake 6. Confusing delay with statement_timeout

Delay governs recovery conflicts; `statement_timeout` bounds query duration. The two parameters are independent.

### Mistake 7. Confusing delay with maximum query runtime

Non-conflicting queries can run longer than the delay. Conflicting queries can be canceled sooner if the WAL delay budget is already spent.

### Mistake 8. Looking only at the replay timestamp

An idle primary makes the replay timestamp look old despite zero real lag. Use LSNs and workload context.

### Mistake 9. Not monitoring replication slots

Delays/lag cause slots to retain WAL longer and can fill the primary disk.

### Mistake 10. Unlimited retries

Many clients retrying simultaneously can trigger a retry storm. Use backoff, jitter, and retry budgets.

### Mistake 11. Running long transactions on the standby

Old snapshots increase snapshot conflicts. End transactions promptly and avoid `idle in transaction`.

### Mistake 12. Routing writes to a standby

DML/DDL are rejected during recovery. Route writes to the primary.

### Mistake 13. Thinking hot_standby_feedback solves all conflicts

Feedback mainly reduces cleanup-induced snapshot conflicts; lock, tablespace, and buffer pin conflicts can still occur.

### Mistake 14. Not distinguishing archive and streaming delays

Different WAL sources use two separate delay parameters.

### Mistake 15. Setting feedback on the primary

The parameter is configured on the standby sending feedback. Verify the right server and version.

### Mistake 16. Using a reporting standby as the sole failover replica

Heavy queries can push replay lag up. Consider separating reporting standbys from failover standbys.

### Mistake 17. Ignoring transaction age

An `idle in transaction` session still holds a snapshot even without an active long query.

### Mistake 18. Not checking role privileges

Hot standbys are read-only, yet roles still require proper `SELECT` privileges.

### Mistake 19. Not verifying consistency after failover

After promotion, verify timeline, archiving, replicas, and applications before considering failover complete.

### Mistake 20. Reading absolute conflict counters

Counters are cumulative; use deltas and reset timestamps to assess current state.

## 37. Practice exercises

Exercises use a PostgreSQL primary/standby in a lab environment. Never deliberately induce recovery conflicts on production.

### Exercise 1. Hot standby

What is a hot standby?

### Exercise 2. Warm vs hot

What is the main difference between warm standby and hot standby?

### Exercise 3. Recovery state

Write SQL to check whether a server is in recovery.

### Exercise 4. Read-only

Why does a standby disallow `INSERT`/`UPDATE`/`DELETE`?

### Exercise 5. Stale data

Why might a row just committed on the primary not appear on a standby yet?

### Exercise 6. Read-after-write

Name two ways to handle reads that must immediately see newly written data.

### Exercise 7. Recovery conflict

What is a recovery conflict?

### Exercise 8. Conflict types

List the five conflict categories in `pg_stat_database_conflicts`.

### Exercise 9. Snapshot conflict

Why can `VACUUM` on the primary cause a standby query to be canceled?

### Exercise 10. Lock conflict

Give an example of DDL causing a lock conflict.

### Exercise 11. Buffer pin

In what situation does a buffer pin conflict occur?

### Exercise 12. Tablespace

What operation on the primary can trigger a tablespace conflict?

### Exercise 13. Archive delay

Which parameter controls conflict delay when replaying WAL from an archive?

### Exercise 14. Streaming delay

Which parameter controls conflict delay when replaying streaming WAL?

### Exercise 15. Delay -1

What does `-1` mean and what risk does it carry?

### Exercise 16. Delay budget

Why is `max_standby_streaming_delay` not a per-query timeout?

### Exercise 17. hot_standby_feedback

Which conflict category does this parameter help reduce?

### Exercise 18. Bloat

What is the major trade-off of `hot_standby_feedback`?

### Exercise 19. Conflict stats

Write SQL to read conflict counters for the current database.

### Exercise 20. Replication lag

Write SQL to read sent/write/flush/replay LSNs from `pg_stat_replication`.

### Exercise 21. Standby replay

Write SQL to read receive LSN and replay LSN on a standby.

### Exercise 22. Replay timestamp

Why can `pg_last_xact_replay_timestamp` be misleading when the primary is idle?

### Exercise 23. Long transaction

Why can `idle in transaction` on a standby cause problems?

### Exercise 24. Logging

Which parameter logs prolonged recovery conflict waits?

### Exercise 25. Query retry

List three principles for retrying queries canceled due to recovery conflicts.

### Exercise 26. statement_timeout

What is the difference between `statement_timeout` and `max_standby_streaming_delay`?

### Exercise 27. Replication slot

Why can lag on a standby increase retained WAL on the primary?

### Exercise 28. Autovacuum

Why should autovacuum not be disabled to avoid snapshot conflicts?

### Exercise 29. Reporting standby

List two benefits and two costs of a reporting standby.

### Exercise 30. Failover

Why can standby lag affect data upon promotion?

### Exercise 31. remote_apply

How does `synchronous_commit=remote_apply` support read-after-write?

### Exercise 32. Read routing

Name which query types should route to the primary and which can route to standbys.

### Exercise 33. Query optimization

List three ways to reduce snapshot hold times on a standby.

### Exercise 34. Feedback monitoring

Name two metrics to monitor when `hot_standby_feedback` is enabled.

### Exercise 35. Conflict troubleshooting

List the initial steps when receiving `canceling statement due to conflict with recovery`.

### Exercise 36. Archive vs stream

Why must you distinguish the WAL source when tuning delays?

### Exercise 37. Promotion

What changes when a standby is promoted?

### Exercise 38. Conflict lab

Propose a way to trigger and observe a snapshot conflict in a lab.

### Exercise 39. Monitoring

List at least five metrics to monitor for a hot standby.

### Exercise 40. Design

Propose a configuration/operational design for a standby that both serves reports and must stay failover-ready.

## 38. Reference solutions

### Exercises 1–6. Hot standby and consistency

Hot standby is a standby replaying WAL while simultaneously serving read-only queries. Warm standby waits/replays WAL without serving read queries. Check recovery via:

~~~sql
SELECT pg_is_in_recovery();
~~~

Standbys do not accept writes because all changes must come from the primary's WAL to maintain the same history. Newly committed rows may not be replayed yet. Route read-after-write to the primary or wait for replay LSN to pass a post-commit barrier.

### Exercises 7–12. Recovery conflicts

A recovery conflict happens when WAL replay needs to perform an action conflicting with a standby query's snapshot/lock/page resource. The five groups are tablespace, lock, snapshot, buffer pin, and deadlock. `VACUUM` cleanup can remove row versions a standby snapshot still needs. `DROP`/`ALTER`/`TRUNCATE` can require strong locks. Buffer pin conflicts happen when recovery needs a page pinned by a backend. `DROP TABLESPACE` can trigger tablespace conflicts with queries using that tablespace.

### Exercises 13–18. Delay and feedback

`max_standby_archive_delay` applies to archive WAL; `max_standby_streaming_delay` applies to streaming WAL. `-1` allows indefinite waiting, though replay lag and retained WAL can grow. The delay budget is tied to WAL replay, not an individual timer starting when each query begins. `hot_standby_feedback` helps reduce cleanup-related snapshot conflicts. The trade-off is that the primary keeps dead tuples longer and may bloat.

### Exercises 19–22. Monitoring

~~~sql
SELECT *
FROM pg_stat_database_conflicts
WHERE datname = current_database();
~~~

~~~sql
SELECT
    application_name,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

On the standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
~~~

Replay timestamps can look old when the primary produces no transactions, so combine LSNs with workload activity.

### Exercises 23–26. Query behavior

`idle in transaction` sessions still hold snapshots/locks even when not actively executing a query. `log_recovery_conflict_waits` logs prolonged conflict waits. Retries must be bounded, use backoff/jitter, and confirm queries have no side effects. `statement_timeout` limits query runtime; `max_standby_*_delay` limits how long recovery waits on conflicts.

### Exercises 27–30. Storage and failover

Replication slots retain WAL from `restart_lsn`; standby lag leaves this position old and holds more WAL on the primary. Never disable autovacuum because of bloat and transaction ID wraparound risks. Reporting standbys offload reads yet consume resources and can raise replay lag. Standby lag at promotion time can lose transactions committed on the primary that the standby has not yet replayed.

### Exercises 31–34. Routing and feedback

With a synchronous standby and `synchronous_commit=remote_apply`, commits wait until transactions are replayed on the standby; new queries opening a fresh snapshot after commit can see that data. Route writes/strong reads to the primary; route eventual reads/reporting to standbys. Reduce query duration via indexes, pagination, batching, and closing transactions early. When feedback is enabled, monitor conflict counters alongside dead tuple/table growth and vacuum progress on the primary.

### Exercises 35–39. Operations

Start with `SQLSTATE`/message/time, identify the standby/database, read conflict counter deltas, find long queries/transactions, and correlate with DDL/`VACUUM` on the primary. Distinguish archive vs stream to tune the right delay parameter. Promotion ends recovery and starts a new timeline. In a lab, hold a `SELECT` snapshot open on the standby while running `DELETE`/`UPDATE` and `VACUUM` on the primary to observe a snapshot conflict. Key metrics include replay lag, receive/replay LSNs, conflict deltas, ready backlog, slot retained WAL, query age, primary dead tuples, and query cancellation/retry rates.

### Exercise 40. Design

Dedicate one standby prioritizing failover freshness with short queries and bounded delays; use a separate reporting standby for long reports. On the reporting standby, you can raise delays within limits and consider `hot_standby_feedback` while monitoring primary bloat. Applications route writes/strong reads to the primary, eventual reads to standbys, and retry cancellations within a budget. Monitor LSN lag, conflict counters, slot retention, disk usage, and run periodic restore/failover drills.

## 39. Quick reference table

| Need | Tool/parameter |
| --- | --- |
| Check recovery state | `pg_is_in_recovery()` |
| Enable queries on standby | `hot_standby = on` |
| Conflict delay for archive WAL | `max_standby_archive_delay` |
| Conflict delay for streaming WAL | `max_standby_streaming_delay` |
| Send `xmin` feedback to primary | `hot_standby_feedback` |
| Log prolonged conflict waits | `log_recovery_conflict_waits` |
| Recovery conflict statistics | `pg_stat_database_conflicts` |
| Replication state on primary | `pg_stat_replication` |
| WAL receiver state on standby | `pg_stat_wal_receiver` |
| Query/transaction age | `pg_stat_activity` |
| Receive LSN | `pg_last_wal_receive_lsn()` |
| Replay LSN | `pg_last_wal_replay_lsn()` |
| Replay timestamp | `pg_last_xact_replay_timestamp()` |
| WAL distance | `pg_wal_lsn_diff()` |
| Slot retained WAL | `pg_replication_slots` |
| Dead tuple estimates | `pg_stat_user_tables` |
| Vacuum progress | `pg_stat_progress_vacuum` |
| Read-only transaction | `SET TRANSACTION READ ONLY` |
| Statement duration limit | `statement_timeout` |
| Idle transaction limit | `idle_in_transaction_session_timeout` |

## 40. Hot standby operations checklist

1. Primary uses an appropriate `wal_level` for physical replication.
2. Standby has `hot_standby` enabled and was restarted when changes required restart.
3. Replication role, `pg_hba`, and TLS are securely configured.
4. `standby.signal` and `primary_conninfo` point to the right upstream.
5. Standby has reached a consistency point and accepts queries.
6. Applications send only read-only workloads to the standby.
7. Writes and strong read-after-write traffic route to the primary or wait for a replay barrier.
8. Long queries and idle-in-transaction sessions are monitored.
9. `max_standby_archive_delay` is configured for archive workloads.
10. `max_standby_streaming_delay` is configured for streaming workloads.
11. Delay settings are not confused with `statement_timeout`.
12. `hot_standby_feedback` is enabled/disabled based on measured trade-offs.
13. Primary dead tuples and vacuum progress are monitored when feedback is on.
14. Conflict counters are scraped and tracked by delta.
15. Recovery conflict waits are logged when needed for investigation.
16. Replication receive/replay LSNs and lag are monitored.
17. Replication slots and retained WAL are monitored.
18. Primary `pg_wal` disk usage has alerts.
19. Query cancellations are categorized and retried within limits.
20. Reporting queries are optimized/indexed/paginated.
21. Long queries are isolated onto a dedicated reporting standby when needed.
22. Failover standby maintains replay lag aligned with RPO.
23. Promotion includes fencing the old primary to avoid split brain.
24. Post-promotion checks verify timeline, archiving, and replicas.
25. Restore/failover drills are performed periodically and results recorded.

## 41. Summary

Hot standby allows PostgreSQL to replay WAL while serving read-only queries. It is an effective way to offload read traffic from the primary and provide read replicas, though data on a standby always reflects replayed state rather than necessarily the primary's latest state.

Recovery conflicts occur when WAL replay needs to clean up row versions, acquire strong locks, modify tablespaces, or use pages pinned by queries. PostgreSQL can delay replay within `max_standby_archive_delay` or `max_standby_streaming_delay`, then cancel queries if conflicts are not cleared. Counters in `pg_stat_database_conflicts` and recovery conflict wait logs help pinpoint root causes.

`hot_standby_feedback` can reduce snapshot conflicts by asking the primary to retain row versions the standby still needs. In return, the primary may retain dead tuples longer and accumulate bloat. Therefore monitor query cancellations, replay lag, replication slots, disk usage, and vacuum health together.

A stable hot standby deployment requires clear routing between primary and replicas, short optimized read queries, avoiding long-open transactions, bounded retries, SLA-aligned delay settings, and regular restore/failover drills. When long reports clash with fast failover requirements, separating reporting standbys from failover standbys lets each replica serve a clear purpose.

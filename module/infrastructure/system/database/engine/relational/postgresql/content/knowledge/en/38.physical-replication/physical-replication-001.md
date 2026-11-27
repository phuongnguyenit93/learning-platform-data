# Primary, standby, and streaming replication flow in PostgreSQL

**Streaming replication** is the mechanism by which PostgreSQL transmits WAL records from a server acting as **primary** to one or more **standby** servers. The standby receives WAL, writes WAL to its storage, and replays the records to update data pages. Thus, the standby maintains a physical copy of the cluster and can be used to serve read queries (hot standby) or promoted to primary when failover is required.

This model is the foundation of high availability (HA), disaster recovery, and read scaling. However, streaming replication alone does not create a complete HA system: it requires an initial base backup, WAL retention, lag monitoring, promotion/fencing procedures, appropriate synchronous/asynchronous configuration, and failover testing.

Overall flow:

```text
                 Application write/COMMIT
                         |
                         v
                   +-----------+
                   |  PRIMARY  |
                   | WAL sender|
                   +-----------+
                         |
                  Streaming protocol
                         |
              +----------+----------+
              |                     |
              v                     v
        +-----------+         +-----------+
        | STANDBY A |         | STANDBY B |
        | WAL recv  |         | WAL recv  |
        | WAL replay|         | WAL replay|
        +-----------+         +-----------+
              |                     |
           Read-only             Read-only
              |                     |
         Promote during failover per procedure
```

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish between primary, standby, WAL sender, and WAL receiver.
2. Explain why physical streaming replication transmits WAL instead of sending individual SQL statements/row changes.
3. Describe why a standby needs a base backup before starting streaming.
4. Configure the primary for physical replication using `wal_level`, `max_wal_senders`, replication role, and `pg_hba.conf`.
5. Create a standby using `pg_basebackup`, `-R`, a physical replication slot, and `primary_conninfo`.
6. Explain `standby.signal`, `primary_slot_name`, `restore_command`, and `hot_standby`.
7. Distinguish between asynchronous and synchronous replication.
8. Choose `synchronous_commit` appropriate for durability/latency requirements.
9. Monitor sent, write, flush, and replay LSNs as well as replication lag.
10. Manage WAL retention, physical replication slots, and the risk of disk exhaustion.
11. Understand hot standby queries, recovery conflicts, and `hot_standby_feedback`.
12. Design cascading replication and recognize the limitations of standby chains.
13. Perform safe promotion/failover, understand new timelines, and avoid split-brain.
14. Rejoin the old primary using `pg_rewind` or a new base backup.
15. Secure replication with network ACLs, TLS, least-privilege roles, and secrets.
16. Build monitoring, runbooks, recovery drills, and RPO/RTO for the system.

## 2. What are primary and standby?

### 2.1. Primary

The primary is the PostgreSQL instance currently holding the role that allows a read-write workload. It:

- Accepts connections from applications.
- Executes INSERT/UPDATE/DELETE/DDL and transaction commits.
- Generates WAL records describing changes.
- Runs WAL sender processes to send WAL to standbys.
- Manages replication slots if configured.

A primary cluster can have multiple standbys. In traditional physical streaming replication, only one active primary is allowed to accept writes for the same replication topology at a time.

### 2.2. Standby

A standby is an instance initialized from a physical base backup of the primary or a compatible physical backup. It:

- Connects to the primary or an upstream standby.
- Receives WAL via the WAL receiver process.
- Writes WAL to local `pg_wal`.
- Replays WAL to update data files.
- Can serve read-only queries if `hot_standby=on` and the recovery state permits.
- Can be promoted to become the primary.

A standby does not receive SQL statements and re-execute them like a logical replication subscriber. It applies physical WAL records to storage.

### 2.3. Physical replication copies at the cluster level

Physical streaming replication replicates WAL for the **entire PostgreSQL cluster**, not configured per database or per table. All databases, schemas, tables, indexes, and Large Objects in the cluster are updated via WAL.

If you only want to replicate a subset of tables or transform schemas/data between two systems, see logical replication. Do not use a physical standby to select only a single database.

### 2.4. Same PostgreSQL major version

A physical standby must be compatible with the primary/base backup in PostgreSQL major version and data file format. Typically, the primary and standby run the same major version; minor releases within the same major version are designed to be compatible for streaming replication, though supported patch levels should be maintained and upgrades tested.

You cannot use a physical standby to replicate directly from PostgreSQL 16 to PostgreSQL 17 as a normal physical copy. A major upgrade requires a separate procedure (for example `pg_upgrade` or logical migration).

### 2.5. Primary and standby do not hold two independent datasets

The standby is a physical replica updated via WAL. It is not a place for applications to arbitrarily write additional data. While in recovery, data modifications from clients are rejected; hot standby only allows read-only queries.

### 2.6. One primary, multiple standbys

Basic topology:

```text
                 +------------------+
                 |      PRIMARY     |
                 +------------------+
                    /      |      \
                   /       |       \
                  v        v        v
             Standby A  Standby B  Standby C
```

Each standby can serve its own purpose: HA near the primary, disaster recovery in another region, or read-only reporting. You must determine whether each node receives synchronous acknowledgement and define WAL retention for each node.

## 3. How does streaming replication work?

### 3.1. WAL is the replication data stream

When the primary modifies a page, PostgreSQL generates WAL records. The WAL sender reads WAL from the required position and transmits it over the replication protocol. The standby receives the stream and writes it to local WAL files.

Flow:

```text
Primary transaction
       |
       v
  WAL records generated
       |
       v
  WAL sender reads WAL
       |
       v
  TCP/TLS replication connection
       |
       v
  WAL receiver on standby
       |
       v
  Write local WAL / flush per progress
       |
       v
  Startup/recovery process replays WAL
       |
       v
  Standby data pages advance toward primary
```

### 3.2. WAL sender

The primary spawns a WAL sender process for each active replication connection. WAL senders serve:

- Physical standby streaming.
- Logical replication walsender/replication protocol connections.
- `pg_basebackup` when taking a base backup over the replication protocol.

Therefore, `max_wal_senders` must be sufficient for all standbys, backup sessions, and required replication consumers, plus headroom for failover/reconnect.

### 3.3. WAL receiver

The standby runs a WAL receiver to connect upstream. The receiver receives WAL, writes it to local WAL storage, and reports progress back to the primary. On the standby, the process can be observed via `pg_stat_wal_receiver`.

### 3.4. Replay

WAL receiver and WAL replay are two distinct steps:

- **Receive:** WAL bytes received from upstream.
- **Write/flush:** WAL written or flushed to local storage.
- **Replay:** The recovery process has applied WAL records to standby data files.

A standby may have received WAL without having replayed all of it yet. In that case, a read-only query may see older data compared to the primary.

### 3.5. Replication feedback

The standby sends feedback to the primary, including the WAL positions written/flushed/replayed and relevant transaction horizon information. The primary uses this feedback to track standby progress and, in synchronous replication, determine when a commit can be acknowledged.

### 3.6. Streaming protocol

Physical replication uses the replication protocol over a PostgreSQL connection. Clients typically connect with the appropriate replication parameter; `pg_hba.conf` has a `replication` entry for authentication.

Do not open the database port to the entire Internet just for the standby to connect. Restrict network source IPs, TLS, and the replication role.

### 3.7. The WAL stream is not a statement log

The standby does not re-run `UPDATE accounts SET ...` as SQL text. It receives physical WAL records and applies changes at the storage level. Thus, physical replication preserves the physical state of the cluster, but does not allow a subscriber to have independent schema/data transformations.

### 3.8. Streaming and WAL archive

Streaming typically transmits WAL in near real time over a connection. WAL archiving saves completed WAL segments to an archive destination. The two mechanisms complement each other:

- Streaming helps the standby keep up with the primary with low latency.
- The archive provides a source of WAL when a standby is disconnected longer than local WAL is retained.

A standby can use `restore_command` to fetch WAL from the archive and then continue streaming once the upstream connection is ready.

## 4. Prerequisites and deployment architecture

### 4.1. Two independent hosts/instances

Primary and standby should have:

- Separate data directories.
- Independent storage appropriate for the failure domain.
- Clearly defined hostnames/IPs and ports.
- A stable network route between standby and upstream.
- Clock synchronization so logs/metrics can be easily correlated.
- Sufficient disk capacity for data, WAL, temporary files, and growth.

Placing a standby on the same host or same storage failure domain as the primary can be useful for testing, but does not provide real host/storage fault tolerance.

### 4.2. Network and latency

Streaming replication requires sufficient network throughput for the WAL generation rate. With asynchronous replication, network lag can slow the standby down. With synchronous replication, standby latency/availability can directly affect commit latency or the ability to commit.

Measure:

- WAL bytes/sec on the primary.
- Network throughput and packet loss.
- Round-trip latency.
- Standby receive/flush/replay rate.
- Storage write latency on the standby.

### 4.3. Disk and WAL headroom

In addition to the data directory, account for:

- Active WAL segments.
- WAL retained by replication slots.
- WAL archive backlog.
- Base backup staging.
- Restore/rewind workspace.
- Log files and monitoring agents.

An inactive replication slot can retain WAL indefinitely and fill up the primary filesystem.

### 4.4. Replication account

Create a dedicated role with `REPLICATION` and `LOGIN` privileges. Do not use a shared superuser for the standby unless necessary.

### 4.5. Security baseline

- Only allow standby/backup hosts to connect.
- Use SCRAM-SHA-256 or appropriate authentication.
- Enable TLS with certificate validation when connecting over untrusted networks.
- Use a protected secret/passfile; do not record passwords in shell history.
- Monitor failed logins and replication disconnects.

## 5. Configuring the primary for physical streaming replication

The examples below assume the primary is PostgreSQL on host `db-primary`, port `5432`, and the standby has source address `10.20.0.12`. Replace addresses, roles, and paths according to your lab environment.

### 5.1. Check version and role

```sql
SELECT version();
SHOW server_version_num;
SELECT pg_is_in_recovery();
```

On the primary, `pg_is_in_recovery()` returns `false`.

### 5.2. Create the replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-managed-secret';
```

This is illustrative syntax for a lab. Production should generate passwords via a secret manager/passfile and follow a rotation policy. Do not commit secrets into repositories or backup scripts.

### 5.3. wal_level

```conf
wal_level = replica
```

`wal_level=replica` records enough WAL information for physical replication and PITR. `logical` records additional information needed for logical decoding; it still supports physical replication, with corresponding overhead/requirements.

`wal_level=minimal` is insufficient for a streaming standby.

### 5.4. max_wal_senders

```conf
max_wal_senders = 10
```

This is an example. Choose a value sufficient for all standbys, base backup sessions, and failover headroom. If slots run out, standbys/backups may fail to connect.

### 5.5. max_replication_slots

```conf
max_replication_slots = 10
```

The value must be sufficient for physical and logical slots used on the primary. Slot count does not equal the number of active connections; a slot can exist while its consumer is offline.

### 5.6. max_wal_size and wal_keep_size

```conf
max_wal_size = '4GB'
wal_keep_size = '1GB'
```

These numbers are examples only. `wal_keep_size` retains a minimum amount of WAL for streaming standbys; if a standby is offline longer, WAL may still be missing. Replication slots/archiving are separate retention mechanisms. `max_wal_size` is not a hard disk quota.

### 5.7. archive_mode and archive_command

If a standby needs to catch up after a long disconnect or PITR is needed, configure WAL archiving:

```conf
archive_mode = on
archive_command = 'test ! -f /archive/%f && cp %p /archive/%f'
```

This command is only illustrative for a lab filesystem; production must handle atomic copy, checksums, permissions, retries, archive monitoring, and storage failures. Do not use an archive directory on the same single disk as the primary as a failure-domain backup.

### 5.8. Apply configuration

`wal_level`, `max_wal_senders`, and `max_replication_slots` require restarting the primary to take effect (`postmaster` context). Some WAL retention parameters can be reloaded depending on version/context.

Verify:

```sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_wal_size',
    'archive_mode'
)
ORDER BY name;
```

Do not restart a live primary just to follow an example; use a change window and HA plan.

### 5.9. pg_hba.conf

Add a rule only for the standby:

```conf
# TYPE       DATABASE      USER        ADDRESS         METHOD
hostssl      replication   replicator  10.20.0.12/32   scram-sha-256
```

`replication` is a special database field for replication connections. `hostssl` requires TLS. If a lab environment does not have TLS configured yet, `host` can be used on an isolated network; production should enable TLS and verify certificates.

Reload HBA:

```sql
SELECT pg_reload_conf();
```

Check logs to confirm the rule is loaded. `pg_hba.conf` uses the first matching rule; a broad line placed earlier can prevent a narrower rule below it from ever being used.

### 5.10. Verify primary readiness

```sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;

SELECT * FROM pg_stat_replication;
```

Before the standby connects, `pg_stat_replication` may have no rows. Once the standby is streaming, check `application_name`/state and LSN progress.

## 6. Creating a standby with pg_basebackup

A standby must have an initial physical copy. You cannot simply install an empty PostgreSQL instance and enable `primary_conninfo` for it to download the entire database from the primary; a base backup is required first.

### 6.1. Stop the target instance and prepare the data directory

On the standby host, install the same PostgreSQL major version. Stop any auto-created service/instance if present. The target data directory must be empty or prepared according to the proper procedure; do not overwrite a data directory containing data you need to keep.

### 6.2. Run pg_basebackup

Example creating a standby with streaming WAL and a physical slot:

```bash
pg_basebackup \
  -h db-primary.example.net \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -F plain \
  -X stream \
  -C \
  -S standby_a \
  -R \
  -P
```

Meaning:

- `-h`, `-p`, `-U`: connect to the primary using the replication role.
- `-D`: standby data directory.
- `-F plain`: write the data directory in plain format.
- `-X stream`: stream required WAL during the base backup.
- `-C`: create the replication slot if it does not already exist.
- `-S standby_a`: physical replication slot name.
- `-R`: write recovery configuration for the standby.
- `-P`: show progress.

Verify the correct binary/version, directory permissions, connectivity, TLS, and disk capacity before running. For other PostgreSQL major versions, check the specific documentation for options.

### 6.3. What does `-R` create?

The `-R` option creates the `standby.signal` file in the data directory and writes upstream connection settings (such as `primary_conninfo`, `primary_slot_name`) into `postgresql.auto.conf` according to the options used.

`standby.signal` tells PostgreSQL on startup that this instance must enter standby/recovery mode.

### 6.4. Check the files

On the standby:

```bash
ls -l /var/lib/postgresql/17/main/standby.signal
grep -E 'primary_conninfo|primary_slot_name' \
  /var/lib/postgresql/17/main/postgresql.auto.conf
```

On Windows, use PowerShell `Get-Item`/`Get-Content` instead of `ls`/`grep`. Do not print passwords from configuration into shared tickets/logs.

### 6.5. primary_conninfo

Example configuration:

```conf
primary_conninfo = 'host=db-primary.example.net port=5432 user=replicator application_name=standby_a sslmode=verify-full sslrootcert=/etc/postgresql/certs/ca.crt'
primary_slot_name = 'standby_a'
```

`application_name` helps identify the standby in `pg_stat_replication`. `sslmode=verify-full` verifies the CA and hostname per TLS setup. Protect passwords with a passfile/secret management if password authentication is used.

### 6.6. primary_slot_name

When a slot is configured, the standby asks the primary to retain WAL from the slot's restart LSN so it can resume after disconnecting. If the slot does not exist or is invalidated, the standby may fail to connect/catch up.

Do not create slots for every standby without capacity/monitoring. An inactive slot can retain WAL indefinitely if no appropriate policy is set.

### 6.7. Start the standby

Start the standby instance via the service manager or `pg_ctl` with the correct data directory/port. PostgreSQL reads `standby.signal`, connects upstream, and begins receiving WAL.

### 6.8. Verify standby mode

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn;
```

On the standby, `pg_is_in_recovery()` returns `true` while in recovery/standby. If it returns `false`, the instance may have been promoted or did not start in standby mode.

### 6.9. Verify on the primary

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

An active standby normally has `state='streaming'`. `sync_state` may be async/sync/quorum depending on configuration. A row in `startup`/`catchup` state may appear while the node is catching up; check logs and LSN progress.

### 6.10. Verify with a read query

If `hot_standby=on`, test:

```sql
SELECT current_database(), pg_is_in_recovery();
SELECT count(*) FROM app.orders;
```

Do not run INSERT/UPDATE/DDL on the standby. Results may lag behind the primary if replication is asynchronous or replay is slow.

## 7. Standby configuration and recovery parameters

### 7.1. standby.signal

The presence of `standby.signal` causes PostgreSQL to start in standby mode and continue recovery. If the file is accidentally deleted, the server may start as an independent instance (depending on state/config), which is dangerous if the node still holds a copy of the primary.

Do not delete `standby.signal` to "fix replication" without a clear promotion procedure.

### 7.2. primary_conninfo

`primary_conninfo` contains the connection string for the WAL receiver to connect upstream. Typical components include:

- host/hostaddr and port.
- replication user.
- application_name for monitoring.
- sslmode, sslrootcert, and TLS options.
- passfile or password if policy permits.

Do not hard-code passwords in broadly readable files. `postgresql.auto.conf` may contain the connection string written by `pg_basebackup -R`; protect the file and control filesystem permissions.

### 7.3. primary_slot_name

If the standby uses a physical replication slot, configure `primary_slot_name` to point to the slot on upstream. The slot retains the WAL required by the standby even if the standby temporarily disconnects.

If no slot is used, the standby depends on `wal_keep_size` and/or the WAL archive to catch up. A standby offline longer than the retained WAL may require a new base backup.

### 7.4. restore_command

If a needed WAL segment is no longer in local `pg_wal` or not yet available via streaming, the standby can fetch the segment from the archive using `restore_command`.

```conf
restore_command = 'cp /archive/%f %p'
```

`%f` is the WAL filename to fetch; `%p` is the destination path requested by PostgreSQL. This example is only for a lab filesystem. Production must handle not-found, retries, integrity, credentials, and a proper archive backend.

### 7.5. hot_standby

```conf
hot_standby = on
```

Allows read-only connections while the standby replays WAL. This parameter must be enabled to use hot standby; some changes require a restart depending on context/version. Queries are only permitted in recovery states that allow them.

### 7.6. hot_standby_feedback

```conf
hot_standby_feedback = on
```

The standby can send feedback about its xmin horizon so the primary avoids vacuuming row versions still needed by standby queries. This reduces recovery conflicts, but can retain dead tuples on the primary and increase bloat.

Enable only after evaluating workload and vacuum impact. It does not resolve all conflict types and does not replace query timeouts/replication design.

### 7.7. max_standby_streaming_delay

This parameter sets the maximum duration a standby can delay WAL replay to let read queries finish when a recovery conflict occurs. If exceeded, the query may be canceled so the standby can continue replaying.

Increasing the value gives reporting queries more time, but increases replay lag and makes read data staler. A large value is not a cure for all query cancellations.

### 7.8. max_standby_archive_delay

Similarly, this parameter applies when the standby replays WAL fetched from the archive. Set a value appropriate for query SLAs and catch-up requirements.

### 7.9. wal_receiver_timeout and wal_sender_timeout

These timeouts help detect silent/unresponsive connections. Tuning should consider network latency, firewall idle timeouts, and workload. Too low a timeout can cause reconnect churn; too high can delay failure detection.

### 7.10. Check effective configuration

```sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'primary_conninfo',
    'primary_slot_name',
    'restore_command',
    'hot_standby',
    'hot_standby_feedback',
    'max_standby_streaming_delay',
    'max_standby_archive_delay',
    'wal_receiver_timeout'
)
ORDER BY name;
```

Some sensitive settings may be masked in output depending on privileges/version. Check WAL receiver logs to verify the actual connection.

## 8. Asynchronous streaming replication

Asynchronous replication is the common default mode for physical streaming replication. The primary does not have to wait for the standby to flush WAL before returning COMMIT success to the application.

### 8.1. Asynchronous commit flow

```text
Client                Primary                 Standby
  |                     |                        |
  |--- UPDATE/COMMIT -->|                        |
  |                     |-- flush local WAL      |
  |<-- COMMIT success --|                        |
  |                     |---- stream WAL ------->|
  |                     |                        |-- write/flush
  |                     |                        |-- replay
```

The standby may receive and replay after the client has already received COMMIT success. This reduces latency and prevents the primary from depending on standby confirmation for every commit.

### 8.2. Risk of data loss on failover

If the primary crashes right after acknowledging a transaction but before the standby receives/flushes the corresponding WAL, the standby may lack transactions the client saw succeed. When that standby is promoted, unreplicated commits may be lost.

The amount of potentially lost data depends on network, WAL generation, standby receive/flush progress, and the timing of the failure. Asynchronous replication therefore has an RPO that can be greater than zero.

### 8.3. Benefits and limitations

Benefits:

- Commit latency does not wait for a network round trip to the standby.
- A slow/disconnected standby does not directly block commits.
- Easy to scale out multiple standbys for reporting/DR purposes.

Limitations:

- Failover may lose a portion of unreceived/unflushed WAL.
- Read replicas can be stale.
- A standby can lag for a long time while the primary continues writing.
- Careful standby selection during failover is needed to minimize data loss.

### 8.4. Async does not mean WAL is not flushed on the primary

With `synchronous_commit=on` and no synchronous standby configured, COMMIT still waits for local WAL flush per normal durability behavior. The difference is that it does not wait for remote standby acknowledgement.

## 9. Synchronous streaming replication

Synchronous replication lets the primary wait for one or more standbys to confirm WAL before returning COMMIT success, according to `synchronous_standby_names` and `synchronous_commit`.

### 9.1. Configuring priority-based synchronous standbys

Example on the primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
```

The primary prioritizes the first eligible and active standby. If `standby_a` disconnects, `standby_b` can be chosen as the synchronous standby in priority order.

### 9.2. Quorum synchronous replication

Example:

```conf
synchronous_standby_names = 'ANY 1 (standby_a, standby_b, standby_c)'
```

The primary requires acknowledgement from any one standby in the group to satisfy a quorum of 1. A higher count can be used if confirmation from multiple replicas is required.

### 9.3. application_name must match

The `application_name` value in the standby's `primary_conninfo` is used to identify the node in `synchronous_standby_names`. If the name does not match, the standby may still stream but will not be chosen as a synchronous standby.

Check:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### 9.4. synchronous_commit

This parameter controls how far a transaction commit waits for acknowledgement:

| Value | How far does COMMIT wait? | Meaning |
| --- | --- | --- |
| `off` | Does not wait for local WAL flush per transaction. | Recently acknowledged commits may be lost on crash; database consistency is still maintained. |
| `local` | Waits for local WAL flush. | Does not wait for a remote synchronous standby. |
| `remote_write` | Waits for the synchronous standby to write WAL to OS, not necessarily durable fsync. | Data may be lost if the standby OS/storage crashes before flush. |
| `on` | Waits for the synchronous standby to flush WAL to durable storage. | Common setting to reduce the risk of losing committed transactions when failing over to an acknowledging standby. |
| `remote_apply` | Waits for the standby to replay WAL. | The transaction is already applied on the standby before COMMIT returns; useful for read-after-write on standby, but increases latency. |

Remote levels only take effect when a synchronous standby is configured/selected. If no synchronous standby exists, `on` does not automatically turn asynchronous replication into synchronous.

### 9.5. Synchronous configuration example

On the primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

On the standbys, configure `application_name=standby_a` or `standby_b`. Reload primary configuration if context permits; verify `pg_settings` and `pg_stat_replication.sync_state`.

### 9.6. Commit latency

Synchronous commit adds a network round trip and write/flush/replay time on the standby depending on the `synchronous_commit` level. With `remote_apply`, the primary waits for replay, which is typically slower than `on`.

If the standby is located in a distant geographic region, network latency can become a significant part of every commit.

### 9.7. Availability trade-off

If the primary requires a synchronous standby and no standby satisfies the requirement, transactions needing remote acknowledgement may wait. This is the trade-off: the system chooses not to acknowledge commits when no replica meets the durability policy.

You can set `synchronous_commit=local` for certain transactions so they do not wait on the remote standby, though those transactions then lack the same remote guarantee as transactions using `on`/`remote_apply`.

### 9.8. Synchronous does not automate failover

Synchronous replication only governs commit acknowledgement. It does not automatically detect a dead primary, fence the old primary, or promote a standby. A separate HA manager/orchestrator or failover runbook is required.

### 9.9. Synchronous does not mean zero data loss in every scenario

Safety also depends on which standby is promoted, the number of synchronous standbys, quorum, fencing, timelines, and whether any transactions used `local`/`off`. Promoting a standby outside the synchronous acknowledgement set or with a diverged history can still lose data.

### 9.10. Per-transaction synchronous_commit

Can be set per session or transaction:

```sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';

UPDATE app.orders
SET status = 'confirmed'
WHERE order_id = 1001;

COMMIT;
```

Only use `remote_apply` for transactions that need a read-after-write guarantee or specific durability requirement; not every query needs this cost.

## 10. Monitoring replication lag and WAL positions

Monitoring must distinguish WAL sent, received, written, flushed, and replayed.

### 10.1. pg_stat_replication on the primary

```sql
SELECT
    pid,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    reply_time
FROM pg_stat_replication
ORDER BY application_name;
```

Positions:

- `sent_lsn`: WAL sent to the standby.
- `write_lsn`: WAL written by the standby.
- `flush_lsn`: WAL flushed by the standby.
- `replay_lsn`: WAL replayed into data files by the standby.

The gap between these LSNs shows which stage is falling behind.

### 10.2. Calculate byte lag

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS bytes_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS bytes_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication
WHERE state = 'streaming';
```

Subtractions are only meaningful when LSNs are non-NULL and share the same WAL history. This is byte distance, not directly seconds of lag.

### 10.3. Calculate distance from primary to replay

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind_primary
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
```

On the primary, `pg_current_wal_lsn()` returns the current WAL position. Values can change immediately after the snapshot query.

### 10.4. pg_stat_wal_receiver on the standby

```sql
SELECT
    status,
    receive_start_lsn,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time,
    slot_name,
    sender_host,
    sender_port
FROM pg_stat_wal_receiver;
```

This view contains at most one row for the active WAL receiver. Some columns may vary by PostgreSQL major version; check the schema on the server.

### 10.5. Receive and replay LSN on the standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

If receive LSN is greater than replay LSN, the standby has received WAL but still has a replay backlog.

### 10.6. Timestamp lag can be misleading

`pg_last_xact_replay_timestamp()` is the commit timestamp of the last replayed transaction, not always an accurate measure of network lag. When the primary has no writes, an old timestamp can make a "lag" graph climb even though the standby is caught up on WAL.

Combine LSN distance, `pg_stat_replication` lag intervals, receive/replay rate, and workload rate for evaluation.

### 10.7. write_lag, flush_lag, replay_lag

These interval fields in `pg_stat_replication` describe the recent response delay of the standby for the corresponding WAL positions. They can be NULL when the standby is caught up or when there are no new transactions to measure. Do not treat a single NULL value as proof that a standby is broken.

### 10.8. Identifying streaming state

`state` commonly has values such as `startup`, `catchup`, `streaming`, `backup`, or `stopping` depending on connection type/version. For a caught-up standby, `streaming` is the expected state. Investigate logs and WAL progress when the state differs.

### 10.9. Monitor by delta

Statistics and LSNs change continuously. Store periodic snapshots and compute:

- WAL generated bytes/sec.
- Receive bytes/sec.
- Replay bytes/sec.
- LSN distance.
- Lag duration.
- Slot retained bytes.
- Archive backlog.

A single data point is insufficient to diagnose trends.

### 10.10. Wait events

You can inspect replication processes and wait events:

```sql
SELECT
    pid,
    backend_type,
    application_name,
    state,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE backend_type IN (
    'walsender',
    'walreceiver'
)
ORDER BY backend_type, pid;
```

The `backend_type` and wait events depend on version/role; visibility into details may be restricted by privileges.

## 11. WAL retention and replication slots

A standby can only continue streaming if the primary still retains the WAL segments the standby has not yet received. If required WAL has already been recycled/deleted and no archive fallback exists, the standby cannot catch up over the current stream.

### 11.1. Without a slot: wal_keep_size

`wal_keep_size` sets the minimum amount of WAL the primary tries to keep for standbys. This is a simple mechanism, but does not guarantee a standby offline arbitrarily long can still catch up.

If the standby needs WAL older than what is kept, it may receive an error requesting a nonexistent WAL segment and require restoring from archive or taking a new base backup.

### 11.2. Physical replication slot

A physical slot retains the WAL required for a specific standby based on the slot's restart LSN. The standby connects to the slot via `primary_slot_name`.

Create a slot manually:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
```

Or let `pg_basebackup -C -S standby_a` create the slot during backup creation. Do not create a slot with a name that already exists.

### 11.3. Inspect slots

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots;
```

The `wal_status` and `safe_wal_size` columns exist in newer major versions; adjust the query if running on an older server. `restart_lsn` indicates the oldest WAL the slot still needs to retain.

### 11.4. Inactive slots can fill the disk

If a standby disconnects while its slot still exists, the primary must keep WAL for the standby to resume. If the standby does not return for a long time, WAL can grow until the filesystem runs out of space.

Monitor:

- Slots inactive for too long.
- Old `restart_lsn`.
- Retained WAL bytes.
- Disk free space.
- Consumer/standby last seen time.

### 11.5. max_slot_wal_keep_size

`max_slot_wal_keep_size` can cap the amount of WAL retained by slots on supported versions. If the limit is exceeded, the slot may be invalidated or no longer guarantee enough WAL for the consumer to continue. The standby may then need a new base backup.

This is a disk protection measure, not a guarantee that the standby always catches up. Set the limit to fit outage durations and peak WAL generation.

### 11.6. Drop a slot

Only drop a slot after confirming the standby/consumer no longer needs it:

```sql
SELECT pg_drop_replication_slot('standby_a');
```

Do not drop an active or in-use slot in production without understanding the impact. If the standby returns after the slot is dropped and WAL has been recycled, it may need to be rebuilt.

### 11.7. WAL archive complements slots

Slots retain WAL on the primary; archiving stores WAL segments outside the primary. A standby can use `restore_command` to retrieve archived WAL if there is a stream gap. Archiving also serves PITR and DR.

### 11.8. max_wal_size is not a slot retention limit

`max_wal_size` is a soft checkpoint target. Replication slots/archiving can cause `pg_wal` to exceed that value. Setting `max_wal_size` low is not a way to control inactive slots.

### 11.9. Do not delete WAL manually

Do not delete files in `pg_wal` using OS commands to free disk space. Doing so can render the primary or standby unable to crash-recover/replicate. Address archive backlogs, slots, standby lag, and capacity using PostgreSQL procedures.

## 12. Hot standby and read-only queries

When `hot_standby=on`, the standby can serve SELECT queries while recovery replays WAL. This is a way to scale read workloads, but a query reading an older snapshot may conflict with changes that WAL replay needs to apply.

### 12.1. Read-only behavior

A standby in recovery does not allow normal writes:

- SELECT is supported.
- INSERT/UPDATE/DELETE are rejected.
- DDL and many administrative operations that modify the database are disallowed.
- Certain temporary table/read-only session features are supported within version limits.

Do not treat a standby as an independent read-write replica.

### 12.2. Read-after-write

In asynchronous replication, a client can COMMIT on the primary and immediately read from a standby without seeing the change yet. If read-after-write is required:

- Read again from the primary.
- Use synchronous replication with `synchronous_commit=remote_apply` for the relevant transaction.
- Or wait for the standby to replay up to the recorded commit LSN (wait-for-replay pattern).

Do not assume all standbys have replayed immediately after COMMIT.

### 12.3. Recovery conflicts

The standby must replay WAL to keep data files consistent with the primary. A long read query may hold a snapshot needing old row versions, while WAL replay needs to remove/alter those structures. This is a **recovery conflict**.

PostgreSQL can delay replay within configured limits, then cancel the query if the conflict persists.

### 12.4. Types of conflicts

Recovery conflicts can involve:

- Snapshots too old needing row versions already vacuumed on the primary.
- Locks on the standby conflicting with replayed locks.
- Tablespaces/databases/objects being dropped or altered.
- Buffer pins or other recovery conditions.

Not every query cancellation is a network error or application bug.

### 12.5. max_standby_streaming_delay

The `max_standby_streaming_delay` parameter sets the maximum time a standby can delay WAL replay to allow read queries to complete during a recovery conflict. If exceeded, the query may be canceled so the standby can resume replay.

Increasing the value gives reporting queries more time, but increases replay lag and makes read data staler. A large value is not a cure for all query cancellations.

### 12.6. hot_standby_feedback

`hot_standby_feedback` sends xmin feedback so the primary knows not to vacuum away certain row versions still needed by standby queries. This reduces some conflicts, but can retain dead tuples longer on the primary, causing bloat and increased storage usage.

Feedback does not resolve all conflicts, such as DDL/drop object or lock conflicts. Measure bloat and vacuum impact before enabling.

### 12.7. Query design on standby

- Limit report execution time and transaction duration.
- Avoid keeping read-only transactions open longer than necessary.
- Run batch/reporting jobs within controlled windows.
- Accept data staleness appropriate for business needs.
- Implement retry/route-to-primary for canceled queries if semantics permit.

### 12.8. Standby for reporting

A standby can be dedicated to analytics/reporting. However, heavy reporting workloads can slow replay due to I/O/CPU contention and create conflicts. Consider an additional dedicated replica or a logical replica if independent schemas/indexes are needed.

### 12.9. Query lag and consistency

A query on a standby sees a consistent snapshot at the current replay state, but that state may be older than the primary. Consistency of a query snapshot does not imply freshness relative to the primary.

## 13. Cascading replication

Cascading replication allows a standby to forward WAL to other standbys, rather than having every standby connect directly to the primary.

### 13.1. Topology

```text
             +-----------+
             | PRIMARY   |
             +-----------+
                  |
            streaming WAL
                  |
                  v
             +-----------+
             | STANDBY A |
             +-----------+
                  |
            streaming WAL
                  |
             +----+----+
             |         |
             v         v
        STANDBY B  STANDBY C
```

Standby A both replays WAL and acts as upstream for B/C.

### 13.2. Benefits

- Reduces direct replication connections to the primary.
- Allows placing standbys by region/site.
- Useful when WAN links or primary egress must be controlled.

### 13.3. Limitations

- B/C cannot receive WAL earlier than A receives it.
- Lag can accumulate across each hop.
- A becomes a dependency for downstream B/C.
- Slots/WAL retention must be managed on the respective upstream.
- Failover/promotion at one tier requires adjusting downstream topology.

### 13.4. Cascading standbys need WAL sender capacity

Standby A must have enough `max_wal_senders` for B/C and other connections. It also needs appropriate slots/retention to retain WAL for downstreams when they disconnect.

### 13.5. Standby as upstream

On standby A, configure it to allow streaming/cascading per the major version documentation and create replication slots if downstreams need them. Downstreams configure `primary_conninfo` pointing to standby A, not the primary.

### 13.6. Monitor every hop

Observe `pg_stat_replication` on each upstream and `pg_stat_wal_receiver` on each downstream. Do not just look at primary → A and conclude B/C are caught up.

### 13.7. Cascading and synchronous replication

Synchronous replication over a cascading topology must be designed carefully: primary acknowledgement depends on the selected synchronous standbys and the WAL/feedback path across hops. Do not assume all downstream standbys participate in quorum simply because they sit behind a cascading standby.

## 14. Promotion and failover

When the primary fails, a standby can be **promoted** to become the new primary. This is a cluster role change operation, not simply restarting a process.

### 14.1. What is promotion?

Promotion ends recovery on the standby, allowing it to accept writes and generate new WAL. PostgreSQL creates a **new timeline** to distinguish WAL history after promotion from the old primary's timeline.

### 14.2. Promote via SQL

On the selected standby:

```sql
SELECT pg_promote(true, 60);
```

The function returns true if promotion succeeds within the wait time. If it times out, check status/logs before retrying; do not promote multiple nodes in parallel.

### 14.3. Promote via pg_ctl

On the standby host:

```bash
pg_ctl -D /var/lib/postgresql/17/main promote
```

Use the correct data directory. With a service manager/HA orchestrator, follow the promotion mechanism of the tool managing the cluster.

### 14.4. Verify after promotion

```sql
SELECT pg_is_in_recovery();
SELECT pg_current_wal_lsn();
```

The new primary returns `pg_is_in_recovery() = false` and can accept writes. Check logs, timeline, and application connectivity before opening traffic.

### 14.5. Which standby to promote?

Prefer the node that:

- Has the most advanced WAL receive/flush/replay progress.
- Has a timeline matching the old primary.
- Has healthy storage/network/host.
- Can serve the workload and is provisioned with sufficient capacity.
- Meets the defined RPO.

Do not simply pick the geographically closest node or a preferred name if it is lagging significantly.

### 14.6. Asynchronous failover can lose commits

A standby whose replay LSN is behind the committed WAL on the primary may lack transactions already acknowledged to clients. Before promotion, assess the missing WAL gap and acceptable RPO.

### 14.7. Synchronous failover

If transaction commits waited for a synchronous standby flush under `synchronous_commit=on`, the acknowledging standby can durably hold those commits. However, you must promote the right standby that participated in the acknowledgement policy and ensure the old primary can no longer accept writes.

### 14.8. Fencing the old primary

**Fencing** ensures the old primary cannot continue serving writes after a standby is promoted. Methods include:

- Stopping/shutting down the old instance from the control plane.
- Revoking application network access.
- Fencing via cloud/hypervisor/storage orchestration.
- STONITH or an equivalent HA manager mechanism.

Do not rely solely on ping or lost connectivity from a single host to conclude the primary is dead. A network partition can leave the primary running and accepting writes from other clients.

### 14.9. Split-brain

Split-brain occurs when two nodes both accept writes as independent primaries. They create two different WAL timelines; writes after the divergence point do not automatically merge.

Consequences can include:

- Losing one branch of data when choosing the new primary.
- Duplicate business operations.
- Inconsistent external side effects.
- Difficulty rejoining the old primary.

Fencing and single-writer ownership are mandatory conditions for safe failover.

### 14.10. Do not promote two standbys

Only one standby may be promoted in a failover event. If multiple standbys self-promote due to uncoordinated health checks/network partitions, multiple independent timelines can be created. Use a single HA authority/quorum and an election/fencing procedure.

### 14.11. Timeline after promotion

After promotion, PostgreSQL switches to a new timeline. Other standbys must obtain the timeline history and follow the new primary properly. WAL segments at the same LSN but on different timelines cannot be treated as the same WAL stream.

### 14.12. Repoint remaining standbys

After the new primary stabilizes:

1. Identify the new primary and timeline.
2. Configure the remaining standbys to point to the new primary (or an appropriate cascading upstream).
3. Ensure replication slots/credentials/HBA are ready.
4. Verify they follow the new timeline and replay forward.
5. Monitor lag and WAL retention.

Do not merely edit the hostname; ensure data history is compatible and the node is not on a diverged branch.

## 15. Rejoining the old primary after failover

The old primary cannot simply be started back up as a primary alongside the new primary. It may contain WAL records belonging to the old timeline after the divergence point.

### 15.1. Why rewind or rebuild?

After promotion, the new primary continues generating WAL on the new timeline. The old primary may have written additional independent WAL before being fenced. The two data directories have diverged.

To bring the old node back as a standby, you must:

- Use `pg_rewind` if preconditions are met and sufficient WAL history exists.
- Or remove/recreate the data directory per procedure and take a new base backup from the new primary.

### 15.2. What does pg_rewind do?

`pg_rewind` compares the timeline/history of source and target to identify data files/blocks changed after the divergence point, then copies the needed parts from source to target. It is not a merge of two database histories.

### 15.3. pg_rewind preconditions

Key preconditions per PostgreSQL documentation:

- The target cluster was cleanly shut down.
- Source and target share an appropriate common ancestor timeline.
- Data checksums were enabled at initdb **or** `wal_log_hints=on` was enabled before divergence.
- `full_page_writes=on` was maintained.
- Required WAL from the divergence point is still available on target/source or via a configured archive/restore path.
- Same PostgreSQL major version and compatible binary tools.

If unmet, take a new base backup instead of forcing a rewind.

### 15.4. Pre-rewind checks

On the old target:

- Stop PostgreSQL and confirm no processes are using the data directory.
- Verify the correct PGDATA and source connection string.
- Check data checksums/`wal_log_hints` history.
- Ensure the WAL archive has sufficient WAL from the divergence point.
- Have a backup/snapshot of the target if needed for investigation/rollback.

### 15.5. pg_rewind example

On the stopped old target host:

```bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/17/old-primary \
  --source-server='host=new-primary.example.net port=5432 user=rewind_user dbname=postgres' \
  --write-recovery-conf
```

`--write-recovery-conf` writes recovery configuration so the target can start as a standby (including the appropriate signal/config per version). Slot/`primary_conninfo` and credential settings must be verified after rewind.

If needed WAL is in the archive, check `--restore-target-wal` and `restore_command` per version. Do not assume `pg_rewind` automatically locates WAL that was already deleted.

### 15.6. After rewind

Verify:

- `standby.signal` exists.
- `primary_conninfo` points to the new primary.
- `primary_slot_name` is correct if using a slot.
- HBA/network/TLS/credentials work.
- The standby starts and `pg_is_in_recovery()` returns true.
- The new primary sees the connection in `pg_stat_replication`.
- Replay LSN advances with no timeline errors.

### 15.7. Rebuild with a base backup

If rewind cannot be used or is unreliable:

1. Stop and isolate the old target.
2. Prepare a new data directory.
3. Run `pg_basebackup` from the new primary.
4. Create slot/standby config.
5. Start the standby and verify replay.

Rebuilding is often simpler and safer when the target has diverged significantly or lacks WAL, though it costs time/network/storage.

### 15.8. Do not start the old primary read-write to "see what data is there"

A diverged node must not be allowed to serve writes or application traffic. If forensics are needed, make an isolated copy and preserve evidence; do not bring that node back into the topology before rewinding/rebuilding.

## 16. Streaming replication does not replace backups

Replication keeps a standby close to the primary's state. Backups preserve independent recovery points in the past. The two mechanisms address different failure modes.

### 16.1. Mistakes are replicated to the standby

Valid changes at the PostgreSQL level are written to WAL and transmitted to the standby, including:

- A user accidentally running DELETE on data.
- DROP TABLE/SCHEMA.
- A bulk UPDATE affecting the wrong rows.
- An application writing business-invalid data.
- Certain forms of logical corruption written to pages.

The standby does not know which changes are mistakes. It replays WAL and reproduces those exact changes.

### 16.2. Replication does not provide long-term history

Standbys usually keep up with the primary and do not retain old versions of the database to roll back to last week. If a logical error is discovered hours later, the standby has likely already replicated the mistake.

### 16.3. Backup + WAL archive + replication

A sound strategy typically combines:

- Physical streaming standby for fast HA/failover.
- Periodic base backups.
- Continuous WAL archiving for PITR.
- Backup copies in an independent/immutable failure domain.
- Restore drills to verify recoverability.

### 16.4. Physical backup vs. standby data directory

A standby data directory is an active node participating in replication that can be promoted. A base backup is an independently stored artifact used to recreate a node/restore a cluster. Do not consider having a standby as having a backup.

### 16.5. RPO and asynchronous replication

An asynchronous standby can lack committed WAL when the primary fails. Actual RPO depends on lag at failover time and the ability to pick the standby with the furthest replay/flush progress.

### 16.6. Synchronous replication and RPO

Synchronous commit can reduce the risk of losing acknowledged transactions when failing over to the confirming standby per policy. It does not replace backups/PITR and does not protect against replicated accidental deletions.

### 16.7. RTO

A caught-up standby can be promoted faster than restoring a large base backup. However, RTO also depends on failure detection, fencing, promotion decision, application routing, consistency checks, and reconfiguring remaining standbys.

## 17. HA architecture and failover orchestration

### 17.1. Manual failover

Suitable for small environments or when operators are on call:

1. Detect that the primary is unavailable.
2. Verify the failure and fence the old primary.
3. Choose a standby matching RPO.
4. Promote exactly one standby.
5. Update endpoint/DNS/proxy/service discovery.
6. Verify writes and business invariants.
7. Repoint remaining standbys.

Manual failover is straightforward to understand, but depends on response time and runbook discipline.

### 17.2. Automated failover

An HA manager can monitor nodes, decide the leader, fence the old node, promote a standby, and update routing. Automation tools do not eliminate the need to understand quorum, network partitions, fencing, and timelines.

### 17.3. Health checks must be multi-dimensional

A node answering TCP or `SELECT 1` does not prove it is a primary that can safely accept writes. Health checks should examine:

- PostgreSQL process/service availability.
- `pg_is_in_recovery()` and current role.
- WAL receiver/replication state.
- Lag/LSN progress.
- Disk free space and WAL retention.
- Application connectivity/transaction test.
- Fencing/leader ownership.

### 17.4. Quorum and split-brain prevention

In an HA cluster, primary decisions require an authority/quorum to prevent both sides of a network partition from promoting. Having only two database nodes without a proper witness/quorum/fencing makes it hard to distinguish a truly dead primary from a network-isolated primary.

### 17.5. Fencing before promotion

The safe sequence is ensuring the old primary cannot accept writes before enabling writes on the new standby. If infrastructure supports STONITH/cloud instance fencing, integrate it into orchestration. A DNS change alone does not fence the old primary because clients may still connect via the old IP.

### 17.6. Client routing

Applications should connect via an endpoint/proxy/service discovery mechanism that can be updated during failover. Avoid hard-coding the primary IP across hundreds of services. Connection pools must detect stale connections and reconnect after a role change.

### 17.7. Retrying transactions after failover

When a connection drops during COMMIT, the client may not know whether the transaction committed. Applications must handle unknown outcomes using an idempotency key/business request ID or check state before retrying. Replication does not resolve duplicate side effects at the application layer.

### 17.8. Planned switchover

A switchover is a controlled primary transfer, typically waiting for the standby to catch up, shifting writes/role, and promoting the target node per procedure. Unlike failover, the old primary is still healthy and can be stopped/reconfigured as a standby cleanly.

### 17.9. Do not confuse switchover with failover

A switchover can prepare state and confirm WAL positions before switching roles. Failover occurs when the primary fails and final confirmation from the primary may be unavailable. RPO and uncertainty levels differ.

## 18. Securing physical replication

### 18.1. Least-privilege role

The replication role only needs replication connection privileges and permissions required for backup procedures. Do not use superuser unless necessary. Separate replication, backup, monitoring, and application roles.

### 18.2. Narrow pg_hba.conf

Example:

```conf
hostssl replication replicator 10.20.0.12/32 scram-sha-256
hostssl replication backup_user 10.20.0.20/32 scram-sha-256
```

Allow only the exact source IPs and roles. Check rule order because PostgreSQL uses the first matching rule.

### 18.3. TLS and certificates

If replication traverses an untrusted network, use TLS and verify the server certificate. With `sslmode=verify-full`, the hostname must match the certificate SAN/CN and the client must have the appropriate CA. Manage certificate rotation to avoid unexpected standby disconnects.

### 18.4. Passwords/passfile

Use a passfile or secret manager with restricted filesystem permissions. Avoid:

- Passwords on the shell command line.
- Passwords in Git.
- Printing connection strings to logs.
- Sharing a single password across all standbys.

### 18.5. Network segmentation

Replication traffic should stay on controlled private networks/VPNs/VPC routes. Firewalls should open only the required port from standby/backup hosts to the primary; do not expose to the public Internet.

### 18.6. Base backups contain all data

Anyone authorized to take a base backup can access nearly all cluster data, including sensitive records. Protect replication/backup privileges like system-wide data read access.

### 18.7. Encryption at rest and backup copies

TLS protects data in transit; it does not automatically encrypt data files/backups. Use encryption at rest, backup encryption, key management, and access auditing per organizational policy.

### 18.8. Controlling logs

Do not write passwords/secrets into PostgreSQL logs, orchestration logs, or tickets. Replication logs still contain hostnames, IPs, slot names, LSNs, and operational details that should be access-controlled.

## 19. Production monitoring and alerting

A replication dashboard must display each standby individually, not just a single "replication healthy" indicator.

### 19.1. Primary metrics

- Number of active WAL senders and state of each connection.
- `state`/`sync_state` and `application_name`.
- Sent/write/flush/replay LSN.
- Write/flush/replay lag.
- WAL generated bytes/sec.
- Inactive replication slots and retained WAL.
- Archive success/failure and backlog.
- Disk free space of the filesystem holding `pg_wal`.

### 19.2. Standby metrics

- WAL receiver status and upstream host.
- Receive LSN, replay LSN, and gap.
- Replay throughput.
- Last message receive time.
- Recovery conflicts and query cancellations.
- Disk free space, WAL/data write latency.
- `pg_is_in_recovery()` to confirm role.

### 19.3. Alert examples

Set thresholds based on workload and RPO, for example:

- No standby connection when HA policy requires one.
- Standby lag exceeds RPO budget.
- WAL slot retention growing continuously.
- Slot inactive beyond threshold.
- Archive command failing repeatedly.
- `pg_wal` filesystem nearly full.
- Standby replay not advancing while the primary has WAL writes.
- Synchronous standby unavailable and commits waiting.

Do not copy a single threshold across all systems; baselines and WAL rates differ.

### 19.4. Replication lag bytes and time

Byte lag indicates the WAL backlog; time lag indicates delay in time. With bursty workloads, the same 100 MB backlog may take seconds or minutes to replay depending on storage/CPU. Track both.

### 19.5. No-write periods

If the primary has no writes, the replay timestamp can look old even though the standby is caught up. Alerts should distinguish "no new WAL" from "standby not advancing despite new WAL."

### 19.6. Synchronous wait monitoring

Monitor sessions waiting on synchronous replication, wait events, and `pg_stat_replication.sync_state`. A slow sync standby can increase COMMIT latency or stall transactions.

### 19.7. Logs

Enable appropriate logging to investigate:

- WAL receiver/sender connections and disconnections.
- Requested WAL segment missing.
- Slot invalidation/retention.
- Recovery conflicts/query cancellations.
- Promotion/recovery timeline events.
- Archive command failures.

Log rotation and retention must be sufficient for incident analysis.

## 20. Runbook for setting up a new standby

The following runbook describes the order of operations for a new standby in an environment with an already stable primary.

### Step 1. Gather topology information

Record:

- Primary hostname/IP, port, PostgreSQL major version.
- Standby hostname/IP, data directory, and port.
- Replication role and authentication method.
- Standby `application_name`.
- Physical slot name.
- TLS certificate/CA and firewall rules.
- WAL retention, archive, and disk capacity.

### Step 2. Check the primary

Verify `pg_is_in_recovery()` returns false, `wal_level` is at least `replica`, sufficient `max_wal_senders`, `max_replication_slots`, HBA rules, and network connectivity.

### Step 3. Create role and slot

Create a least-privilege replication role. Choose one of two approaches:

- Let `pg_basebackup -C -S slot_name` create the slot.
- Create the slot beforehand with `pg_create_physical_replication_slot` and reuse that name.

Do not create duplicate slots.

### Step 4. Prepare the standby

Install the same major version, stop the default service, prepare an empty data directory, and verify owner/permissions and disk space.

### Step 5. Run base backup

Run `pg_basebackup` with `-X stream`, `-R`, slot name, and progress. Monitor exit code, logs, network, and disk. Do not start the instance while the base backup is incomplete.

### Step 6. Verify recovery config

Confirm `standby.signal`, `primary_conninfo`, `primary_slot_name`, `restore_command` (if used), and TLS credentials. Do not print secrets into logs.

### Step 7. Start the standby

Start with the correct data directory. Watch logs until the WAL receiver connects and state reaches `streaming`.

### Step 8. Verify both sides

On the primary: `pg_stat_replication` lists the standby with the right `application_name` and state.

On the standby: `pg_is_in_recovery()` is true, `pg_stat_wal_receiver` has a row, and receive/replay LSNs advance.

### Step 9. Test read-only behavior

Run a SELECT query to verify data on the standby. Verify writes are rejected and applications do not route write traffic to the standby.

### Step 10. Enable monitoring

Register the node in dashboards/alerts for connectivity, lag, slot retention, archive, recovery conflicts, and disk headroom.

### Step 11. Record baseline

Record WAL rate, network throughput, replay throughput, and lag during normal/peak workloads. Use these metrics to tune alerts and RPO.

## 21. Failover runbook

Failover changes primary ownership. All actions must follow a single authority to prevent split-brain.

### Step 1. Confirm the incident

Check the primary process, host/storage/network, and logs. Distinguish a truly down primary from a network partition from the monitor's perspective.

### Step 2. Fencing

Ensure the old primary cannot continue accepting writes: stop the instance, fence the host/storage, or revoke access via the HA control plane. Do not skip this step just because ping failed.

### Step 3. Choose a standby

Compare receive/flush/replay LSNs, lag, timeline, node health, and synchronous acknowledgement state. Pick a node meeting RPO and confirmed by fencing/authority.

### Step 4. Promote one node

Invoke `pg_promote` or `pg_ctl promote` on the chosen standby. Promote only one node.

### Step 5. Verify the new primary

Check `pg_is_in_recovery() = false`, logs, timeline, and read/write capability. Run business smoke tests before opening full traffic.

### Step 6. Shift traffic

Update proxy/service discovery/connection endpoints. Close old connections or require clients to reconnect. Ensure write requests no longer reach the old primary.

### Step 7. Assess data loss

Record LSN/standby lag at promotion time, estimate missing WAL, and evaluate uncertain transactions with the application. Handle unknown COMMIT outcomes using idempotency/business request IDs.

### Step 8. Reconfigure standbys

Repoint remaining standbys to the new primary and new timeline. Rejoin the old primary via rewind/rebuild after fencing.

### Step 9. Ensure backups

Once the system stabilizes, take/verify a new base backup per policy and confirm WAL archiving continues on the new primary.

### Step 10. Post-incident review

Document timeline, actual RTO/RPO, data loss/uncertainty, root cause, duration of each step, and needed topology changes.

## 22. Runbook when standby disconnects or cannot catch up

### 22.1. WAL receiver cannot connect

Check:

- Host/port/DNS/route/firewall.
- `pg_hba.conf` and replication role.
- TLS CA, hostname, and certificate expiry.
- Password/passfile permissions.
- Whether the primary has enough `max_wal_senders`.
- Whether the slot exists and is not invalidated.

Read both standby and primary logs to identify which side rejected the connection.

### 22.2. WAL segment no longer exists

If the standby requests a segment that was already recycled:

1. Check if the archive has that segment.
2. Verify `restore_command` and timeline history.
3. If the archive has it, fix the restore path and let the standby replay.
4. If required WAL is unavailable, take a new base backup from the primary.

Do not copy random segments or fabricate empty WAL files.

### 22.3. Slot retains too much WAL

Identify which slot is inactive, which standby uses it, last seen time, and restart LSN. Recover the standby or drop the slot only after confirming the node no longer needs it. Set alerts/capacity limits to prevent recurrence.

### 22.4. Receive advances but replay stalls

Check storage I/O, CPU, recovery conflicts, logs, long-running read queries, and the recovery process. If standby queries continually delay replay, review `max_standby_streaming_delay`/feedback policy.

### 22.5. Standby needs rebuild

If WAL history is missing or the timeline cannot be rejoined, stop the standby, preserve logs/metadata for investigation, prepare a new data directory, and run a base backup from the primary on the right timeline. Do not start a diverged node as an independent primary.

## 23. Lab 1: creating a primary and standby in an isolated environment

This lab requires two PostgreSQL instances of the same major version on two hosts or two separate data directories/ports. Do not use a production cluster.

### 23.1. Define addresses

Example:

| Component | Lab value |
| --- | --- |
| Primary host | `db-primary` |
| Primary port | `5432` |
| Standby host | `db-standby` |
| Standby source IP | `10.20.0.12` |
| Replication role | `replicator` |
| Application name | `standby_a` |
| Slot | `standby_a` |

Substitute the actual hostnames, IPs, ports, and paths of your lab environment.

### 23.2. Configure primary

In `postgresql.conf`:

```conf
wal_level = replica
max_wal_senders = 5
max_replication_slots = 5
wal_keep_size = '512MB'
hot_standby = on
```

Example values are only sufficient for a small lab. Restart the primary if changing parameters with `postmaster` context; reload parameters that allow reloading.

### 23.3. Create replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'lab-only-secret';
```

Only use a mock password in a disposable cluster. Never use this password in a real environment.

### 23.4. Configure pg_hba.conf

```conf
host replication replicator 10.20.0.12/32 scram-sha-256
```

The lab network must be isolated. Production should use `hostssl`/TLS and a firewall allowlist.

### 23.5. Prepare standby data directory

Stop the target PostgreSQL instance. Confirm the standby data directory is empty or newly created. Do not run `pg_basebackup` onto an active PGDATA.

### 23.6. Run base backup

```bash
pg_basebackup \
  -h db-primary \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/standby_a \
  -F plain \
  -X stream \
  -C \
  -S standby_a \
  -R \
  -P
```

If the slot was already created beforehand, omit `-C` and use the matching slot name. Supply the password via a passfile/secret mechanism rather than the command line.

### 23.7. Verify recovery configuration

Check `standby.signal`, `primary_conninfo`, and `primary_slot_name`. Ensure `application_name` is `standby_a` and `host` points to the right primary.

### 23.8. Start standby

Start the instance with its own data directory/port. Watch logs until the WAL receiver connects and begins streaming.

### 23.9. Check primary

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

Expect one row for the standby with the right `application_name` and state reaching `streaming`.

### 23.10. Check standby

```sql
SELECT pg_is_in_recovery();
SELECT * FROM pg_stat_wal_receiver;
SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn();
```

Expect `pg_is_in_recovery()` to return true, WAL receiver active, and LSNs advancing when the primary receives writes.

### 23.11. Test replicated data

On the primary:

```sql
CREATE TABLE public.replication_lab (
    id integer PRIMARY KEY,
    note text NOT NULL
);

INSERT INTO public.replication_lab
VALUES (1, 'written-on-primary');
```

On the standby:

```sql
SELECT *
FROM public.replication_lab;
```

The row will appear after WAL is received and replayed. Do not attempt INSERT on the standby.

### 23.12. Clean up lab

Only after completing testing, stop the lab instances and remove the data directories created specifically for the lab. Drop slots/roles only when no consumer uses them anymore. Never apply cleanup commands to production.

## 24. Lab 2: observing asynchronous replication lag

### 24.1. Confirm asynchronous mode

On the primary, leave `synchronous_standby_names` empty or do not select the standby for a synchronous policy in the lab. Verify the standby's `sync_state` is async.

### 24.2. Generate WAL workload

On the primary:

```sql
CREATE TABLE IF NOT EXISTS public.replication_load (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO public.replication_load(payload)
SELECT repeat(md5(g::text), 8)
FROM generate_series(1, 50000) AS g;
```

Actual volume depends on storage, network, and configuration. Ramp up gradually in the lab; avoid unbounded workloads.

### 24.3. Measure primary-to-standby lag

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind
FROM pg_stat_replication;
```

Take multiple snapshots over time to see whether the backlog grows or shrinks.

### 24.4. Measure receive and replay on the standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS received,
    pg_last_wal_replay_lsn() AS replayed,
    pg_wal_lsn_diff(
        pg_last_wal_receive_lsn(),
        pg_last_wal_replay_lsn()
    ) AS bytes_waiting_for_replay;
```

If receive advances quickly while replay lags, inspect storage/CPU/recovery conflicts.

### 24.5. Test reading stale data

Insert a row on the primary and read immediately from the standby. Depending on timing, the standby may not see the row yet until replay completes. This illustrates the eventual freshness of asynchronous replication.

### 24.6. Clean up lab data

```sql
DROP TABLE public.replication_load;
DROP TABLE public.replication_lab;
```

Drop only tables created by the lab.

## 25. Lab 3: synchronous replication in an isolated cluster

This lab requires a primary and a lab standby that is already streaming.

### 25.1. Set application_name

On the standby, configure in `primary_conninfo`:

```conf
primary_conninfo = 'host=db-primary port=5432 user=replicator application_name=standby_a'
```

Reconnect/restart the receiver appropriately so the new `application_name` takes effect.

### 25.2. Select synchronous standby

On the primary:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
synchronous_commit = on
```

Reload configuration and verify `pg_stat_replication.sync_state` becomes sync when the standby is selected.

### 25.3. Test COMMIT

```sql
BEGIN;
INSERT INTO public.replication_lab(id, payload)
VALUES (900001, 'sync-commit');
COMMIT;
```

COMMIT must wait for remote flush acknowledgement per policy while the sync standby is active.

### 25.4. Compare remote_apply

In the lab:

```sql
BEGIN;
SET LOCAL synchronous_commit = 'remote_apply';
INSERT INTO public.replication_lab(id, payload)
VALUES (900002, 'remote-apply-commit');
COMMIT;
```

`remote_apply` waits for the standby to replay WAL. Use a query on the standby to confirm the row is visible immediately after COMMIT.

### 25.5. Test standby disconnect

Disconnect the standby in the lab environment. Execute a transaction requiring synchronous acknowledgement and observe wait behavior. Use a controlled timeout/session cancel; then restore the standby.

Never run this experiment in production because it can block commits.

### 25.6. Return to asynchronous

After the lab, restore `synchronous_standby_names`/`synchronous_commit` to their initial settings and verify `sync_state`/commit behavior.

## 26. Lab 4: promotion in a disposable cluster

This lab turns a standby into a new primary. Only run it on an isolated disposable cluster.

### 26.1. Verify before promotion

On the standby:

```sql
SELECT pg_is_in_recovery();
SELECT pg_last_wal_replay_lsn();
```

Record the LSN and confirm the standby has caught up under lab conditions.

### 26.2. Stop/fence lab primary

Stop the lab primary and confirm no process/endpoint is accepting writes. In production, this step requires true control-plane fencing.

### 26.3. Promote standby

```sql
SELECT pg_promote(true, 60);
```

Or use `pg_ctl promote` on the right standby data directory.

### 26.4. Verify new primary

```sql
SELECT pg_is_in_recovery();
SELECT pg_current_wal_lsn();
```

Expect recovery to end and the instance to accept writes.

### 26.5. Inspect timeline

Use `pg_control_checkpoint()` or `pg_controldata` to observe timeline/checkpoint metadata. Record the new timeline per lab version.

### 26.6. Do not start the old primary read-write

The old primary may have diverged. Do not start it as a primary. To rejoin, test `pg_rewind` on a disposable copy with all preconditions met or take a new base backup from the new primary.

### 26.7. Clean up lab

Stop all instances and remove the isolated lab data directories after saving needed results.

## 27. Lab 5: recovery conflicts on hot standby

The goal is to observe how a read query can conflict with WAL replay.

### 27.1. Create table on primary

```sql
CREATE TABLE public.hot_standby_lab (
    id integer PRIMARY KEY,
    payload text NOT NULL
);

INSERT INTO public.hot_standby_lab
SELECT g, repeat('x', 100)
FROM generate_series(1, 10000) AS g;
```

### 27.2. Open a long read transaction on standby

On the standby:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT count(*) FROM public.hot_standby_lab;
-- Keep transaction open during the lab.
```

### 27.3. Modify data on primary

On the primary:

```sql
DELETE FROM public.hot_standby_lab
WHERE id BETWEEN 1 AND 5000;
VACUUM public.hot_standby_lab;
```

WAL replay on the standby may encounter a conflict with the older snapshot.

### 27.4. Observe logs and query

Depending on delay/feedback settings, the standby may delay replay or cancel the query. Inspect server logs, recovery conflict statistics, and replay LSN.

### 27.5. End lab

COMMIT/ROLLBACK the standby transaction. Drop the lab table on the primary if no longer needed. Restore modified parameters.

## 28. Lab 6: checking WAL slot retention

### 28.1. Identify slot

```sql
SELECT slot_name, active, restart_lsn
FROM pg_replication_slots;
```

### 28.2. Disconnect lab standby

Stop the disposable standby briefly while keeping the slot. Generate controlled WAL on the lab primary.

### 28.3. Observe retained WAL

```sql
SELECT
    slot_name,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS retained_distance
FROM pg_replication_slots;
```

LSN distance is an indicator; it is not an exact measure of retained disk bytes because segment recycling/other slots/archive conditions also affect it.

### 28.4. Restart standby

Start the standby and observe it catch up from the slot if the required WAL is still present. If the slot was invalidated or WAL is missing, the lab may need a new base backup.

### 28.5. Clean up slot

Only drop the slot after the lab standby has been stopped and is no longer using the slot.

## 29. Common mistakes

### 29.1. Enabling only primary_conninfo without a base backup

A standby requires a compatible physical data directory before replaying WAL. Creating an empty instance and configuring upstream does not replace a base backup.

### 29.2. Confusing physical replication with logical replication

Physical replication transmits WAL and copies the entire cluster. Logical replication transmits logical changes via publications/subscriptions, can select tables, and supports schema differences within limits.

### 29.3. Using different major versions

A physical data directory is not a shared format across major versions. Use the same major version or perform a major upgrade/migration via a separate procedure.

### 29.4. Forgetting wal_level

If `wal_level` is insufficient, the primary does not record enough WAL information for a streaming standby. Check the setting and `pending_restart` before creating a replica.

### 29.5. max_wal_senders too low

Standbys or `pg_basebackup` may fail to connect when WAL sender slots are exhausted. Account for standbys, backup sessions, logical consumers, and headroom.

### 29.6. Wrong or overly broad HBA rule

Replication connections use the special `replication` database field. Misordered rules or source IPs can reject connections or unintentionally grant broader access.

### 29.7. Forgetting standby.signal

If a standby does not start in recovery mode, it may not connect upstream or replay WAL. Verify the signal file after base backup and after rejoin operations.

### 29.8. No slot or insufficient retention

A standby offline for a long period may request a WAL segment that has already been recycled. Use appropriate physical slots/archiving or rebuild with a base backup when the gap is unrecoverable.

### 29.9. Unmonitored inactive slots

Slots retain WAL and can fill the primary filesystem. Configure alerts for inactive slots, old `restart_lsn`, and disk free space.

### 29.10. Thinking max_wal_size is a disk cap

Archive backlogs and replication slots can retain WAL beyond `max_wal_size`. Resolve retention blockers; do not delete files manually.

### 29.11. Thinking WAL received means WAL replayed

Receive/write/flush/replay are distinct stages. Read queries only see the replayed state.

### 29.12. Reading from standby right after COMMIT and concluding data is lost

An asynchronous standby may not have replayed the transaction yet. Route read-after-write to the primary or use `remote_apply`/wait-for-replay when needed.

### 29.13. Using replay timestamp as the sole lag metric

When the primary has no writes, the last timestamp can remain old even though the standby is caught up. Use LSN distances and workload rate alongside timestamps.

### 29.14. Increasing max_standby_streaming_delay indefinitely

This can keep queries running longer, but increases replay lag and bloats WAL retention. Review query duration, `hot_standby_feedback`, and workload routing.

### 29.15. Enabling hot_standby_feedback without monitoring bloat

Feedback can keep dead tuples on the primary so standby queries are not canceled. Monitor vacuum, dead tuples, and table bloat.

### 29.16. Using synchronous replication and forgetting application_name

A standby may stream without being selected as a synchronous standby if its name does not match `synchronous_standby_names`.

### 29.17. Thinking synchronous replication automates failover

Synchronous commit only controls acknowledgement. Fencing, leader election, promotion, and routing are still required separately.

### 29.18. Promoting before fencing the old primary

A network partition can leave the old primary still accepting writes. Two primaries create diverged timelines and split-brain.

### 29.19. Promoting multiple standbys

Multiple independent promotions create multiple WAL branches. Use one HA authority and promote only one node.

### 29.20. Ignoring timelines after promotion

Remaining standbys must follow the new timeline. Do not just change the hostname if data history has diverged.

### 29.21. Starting the old primary read-write after failover

The old node may have divergent WAL. It must be rewound/rebuilt before rejoining as a standby.

### 29.22. Using pg_rewind without meeting preconditions

The target must shut down cleanly, share a common timeline ancestor, have checksums or `wal_log_hints` properly enabled, and have the needed WAL. If insufficient, take a new base backup.

### 29.23. Thinking replication replaces backups

Accidental DELETE/DROP/logical corruption is replicated. Base backups, WAL archiving, PITR, and immutable backups are required.

### 29.24. Running heavy read workloads on standby without accounting for replay

Reporting queries can contend for CPU/I/O with WAL replay and cause recovery conflicts. Measure lag and isolate workloads when needed.

### 29.25. Not testing failover/rejoin

A standby streaming today does not prove promotion, fencing, client routing, and rewind work. Drill the full workflow in a production-like environment.

## 30. Practice exercises

The exercises use a lab topology or require configuration analysis. Promotion/fencing/rebuild exercises must only be performed on a disposable cluster.

### Exercise 1. Roles

Distinguish primary, physical standby, WAL sender, and WAL receiver.

### Exercise 2. Physical vs logical

Why does physical replication copy the entire cluster while logical replication can select tables?

### Exercise 3. Base backup

Why does a standby need a base backup before streaming WAL?

### Exercise 4. WAL stages

Distinguish WAL sent, write, flush, and replay. Which stage determines data visible to read queries on the standby?

### Exercise 5. Primary configuration

State the purpose of `wal_level`, `max_wal_senders`, and `max_replication_slots`.

### Exercise 6. Replication role

Write SQL to create a login role with REPLICATION privilege.

### Exercise 7. HBA

Write a `pg_hba.conf` rule for role `replicator` from standby IP `10.20.0.12`.

### Exercise 8. pg_basebackup

Explain the options `-X stream`, `-C`, `-S`, `-R`, and `-P`.

### Exercise 9. standby.signal

What does this file mean? Why should you not delete it to troubleshoot connection errors?

### Exercise 10. primary_conninfo

List typical components of the connection string and the role of `application_name`.

### Exercise 11. Replication slot

How does a slot retain WAL? What is the risk of an inactive slot?

### Exercise 12. wal_keep_size

Why does `wal_keep_size` not guarantee a standby offline for a long time can still catch up?

### Exercise 13. Async

A transaction commits successfully on the primary, but the standby has not received the WAL yet. If the primary crashes and the standby is promoted, what can happen?

### Exercise 14. Sync

Write a `synchronous_standby_names` configuration choosing `standby_a` as the first synchronous standby.

### Exercise 15. synchronous_commit

Distinguish `remote_write`, `on`, and `remote_apply`.

### Exercise 16. application_name

A standby is streaming, yet `sync_state` is async. What is a common configuration cause?

### Exercise 17. Monitoring

Write SQL to read `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn` from `pg_stat_replication`.

### Exercise 18. Byte lag

Write SQL to calculate bytes behind between the current WAL LSN and `replay_lsn` for each standby.

### Exercise 19. Standby receiver

Which view on the standby shows the WAL receiver connection? Name at least three fields you can inspect.

### Exercise 20. Replay timestamp

Why is `pg_last_xact_replay_timestamp` not the sole lag metric?

### Exercise 21. Hot standby

Does a hot standby allow UPDATE? Why can a read query be canceled?

### Exercise 22. hot_standby_feedback

State the benefit and trade-off of this parameter.

### Exercise 23. Cascading

Standby A acts as upstream for B and C. Name two benefits and three limitations.

### Exercise 24. Promotion

Write SQL to promote a standby and a query to verify it has exited recovery.

### Exercise 25. Fencing

Why must the old primary be fenced before promoting a standby?

### Exercise 26. Timeline

When is a new timeline created? Why can WAL at the same LSN on two different timelines not be treated as the same stream?

### Exercise 27. pg_rewind

List at least four important preconditions for using `pg_rewind`.

### Exercise 28. Rebuild

When should you take a new base backup instead of `pg_rewind`?

### Exercise 29. Backup

Why does physical streaming replication not replace backups and PITR?

### Exercise 30. HA design

Design a topology for an application needing low RPO, read scaling, and disaster recovery in another region. Specify synchronous/asynchronous choices, backups, WAL archive, monitoring, and failover steps.

## 31. Suggested solutions

### Solution 1. Roles

- Primary accepts writes, generates WAL, and sends WAL.
- Physical standby receives/replays WAL to maintain a physical copy.
- WAL sender runs on upstream and transmits WAL.
- WAL receiver runs on standby and receives WAL.

### Solution 2. Physical vs logical

Physical replication applies WAL to data files of the entire cluster, so it cannot select individual tables. Logical replication reads logical changes via publications/subscriptions and can select tables by design.

### Solution 3. Base backup

WAL only describes subsequent changes, not a complete copy of all data pages. The standby needs a base backup as a starting foundation before replaying subsequent WAL.

### Solution 4. WAL stages

- Sent: primary has sent it.
- Write: standby has written it to WAL storage.
- Flush: WAL has been durably flushed per feedback.
- Replay: recovery process has applied WAL to data files.

Read queries on the standby see the replayed state.

### Solution 5. Primary configuration

`wal_level` determines what kind of WAL information is written; `max_wal_senders` limits WAL sender connections; `max_replication_slots` limits the number of replication slots that can be created.

### Solution 6. Replication role

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'managed-secret';
```

In production, use a secret manager/passfile and avoid putting passwords in shell history or source control.

### Solution 7. HBA

```conf
hostssl replication replicator 10.20.0.12/32 scram-sha-256
```

The rule requires TLS; host/IP and role must match the actual standby.

### Solution 8. pg_basebackup

- `-X stream` streams WAL during the backup.
- `-C` creates the replication slot if it does not exist.
- `-S` specifies the slot name.
- `-R` creates `standby.signal` and recovery connection config.
- `-P` displays progress.

### Solution 9. standby.signal

This file causes PostgreSQL to start in standby/recovery mode. Deleting it can stop the node from following the primary; do not delete the file to fix a connection issue because it risks creating an independent/diverged instance.

### Solution 10. primary_conninfo

Contains host/port/user, `application_name`, TLS options, and passfile/password per policy. `application_name` identifies the standby in `pg_stat_replication` and is used to select synchronous standbys.

### Solution 11. Replication slot

A slot retains WAL from the oldest `restart_lsn` the consumer still needs. A long-inactive slot can retain large amounts of WAL and fill the primary filesystem.

### Solution 12. wal_keep_size

This is a minimum amount of WAL kept, not infinite retention. A standby offline longer than the retained WAL may require an archive or a new base backup.

### Solution 13. Async

The standby may lack the transaction already acknowledged by the primary. If that standby is promoted, the unreceived/unflushed/unreplayed transaction may be lost. RPO depends on lag at failover time.

### Solution 14. Sync

```conf
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

The name must match `application_name` on the standby.

### Solution 15. synchronous_commit

- `remote_write` waits for the standby to write WAL to the OS, not necessarily fsync.
- `on` waits for the standby to durably flush WAL.
- `remote_apply` waits for the standby to replay WAL before COMMIT returns.

### Solution 16. application_name

The name in `primary_conninfo` does not match the `synchronous_standby_names` list, so the standby is not selected as a synchronous standby.

### Solution 17. Monitoring

```sql
SELECT
    application_name,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### Solution 18. Byte lag

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS bytes_behind
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
```

This is a byte distance, not an exact lag duration.

### Solution 19. Standby receiver

The `pg_stat_wal_receiver` view. You can inspect `status`, `sender_host`, `sender_port`, `written_lsn`, `flushed_lsn`, `latest_end_lsn`, `latest_end_time`, and `slot_name` (columns depend on major version).

### Solution 20. Replay timestamp

If the primary has no writes, the last replay timestamp does not change even when the standby is caught up. Combine the timestamp with LSN distance, WAL generation rate, and receive/replay progress.

### Solution 21. Hot standby

No. Hot standby only permits read-only queries during recovery. A query can be canceled if it conflicts with WAL replay, such as an old snapshot needing row versions already vacuumed by the primary.

### Solution 22. hot_standby_feedback

It sends xmin feedback so the primary retains row versions needed by standby queries, reducing some recovery conflicts. The trade-off is that dead tuples can persist longer on the primary, increasing bloat.

### Solution 23. Cascading

Benefits: reduces direct connections to the primary and ships WAL across regions/sites. Limitations: downstreams cannot receive earlier than upstream, lag can accumulate, upstream becomes a dependency, and WAL retention is needed for downstreams.

### Solution 24. Promotion

```sql
SELECT pg_promote(true, 60);
SELECT pg_is_in_recovery();
```

After promotion, the second query returns false. Only run after fencing the old primary and selecting the right standby.

### Solution 25. Fencing

The old primary may still be running and accepting writes during a network partition. If a standby is promoted before fencing, two nodes accept writes and create split-brain/divergent timelines.

### Solution 26. Timeline

A new timeline is created when a standby promotes. It distinguishes the new WAL history from the old branch. The same LSN on two timelines can contain different records and cannot be concatenated arbitrarily.

### Solution 27. pg_rewind

Example preconditions:

1. Target cleanly shut down.
2. Source/target share a common timeline ancestor.
3. Data checksums enabled from initdb or `wal_log_hints` enabled before divergence.
4. `full_page_writes` enabled.
5. Required WAL from the divergence point still available.
6. Same PostgreSQL major version.

### Solution 28. Rebuild

When required WAL is missing, timeline history is incompatible, rewind preconditions are unmet, the target has diverged for a long time, or a simpler/more reliable option is desired. Take a new base backup from the current primary.

### Solution 29. Backup

Replication also replicates DELETE/DROP/logical corruption. It does not retain long-term history or provide PITR. Base backups, WAL archiving, and independent backup copies are needed.

### Solution 30. HA design

A possible design:

1. Primary in the main region.
2. Synchronous standby near the primary for durability/HA and low RPO; use an appropriate `synchronous_commit`.
3. Asynchronous standby in a DR region to avoid WAN latency slowing all commits, with an acceptable RPO and continuous WAL archiving.
4. Separate reporting standby if read scaling is needed; monitor replay lag and recovery conflicts.
5. Periodic base backups, WAL archive in an independent/immutable failure domain.
6. Monitor `pg_stat_replication`, `pg_stat_wal_receiver`, slots, archive backlog, disk, and lag.
7. Failover: detect incident, fence primary, pick standby per RPO, promote exactly one node, shift traffic, rejoin remaining nodes.
8. Periodically test restore/PITR and failover; record actual RTO/RPO.

Low RPO cannot be achieved merely by creating many standbys; synchronous acknowledgement, fencing, and selecting the right node during failover are required.



## 32. Streaming replication design and operations checklist

### 32.1. Topology and base backup

1. Are primary and standby on the same PostgreSQL major version?
2. Was the standby created from a compatible physical base backup?
3. Are PGDATA, tablespaces, and WAL storage inventoried?
4. Are primary/standby failure domains identified?
5. Did `pg_basebackup` fetch required WAL and was its exit code checked?
6. Are `standby.signal` and recovery configuration correct?

### 32.2. Primary configuration and security

7. Is `wal_level` at least `replica`?
8. Is `max_wal_senders` sufficient for standbys/backups/consumers plus headroom?
9. Is `max_replication_slots` sufficient for the slots in use?
10. Does the replication role have least privilege?
11. Does `pg_hba.conf` allow only the exact IPs/roles and authentication method?
12. Are TLS/hostname verification and secret management configured?
13. Is `application_name` unique and clear for each standby?

### 32.3. WAL retention and replication slots

14. Does each standby have a physical slot or an appropriate retention/archive policy?
15. Do inactive slots have alerts and an owner?
16. Has `max_slot_wal_keep_size` been considered to protect disk space?
17. Is the archive command monitored and is the WAL chain continuous?
18. Does the disk alert for `pg_wal` provide sufficient headroom?
19. Is manually deleting WAL files prohibited in the runbook?

### 32.4. Consistency, lag, and read scaling

20. Does monitoring distinguish sent/write/flush/replay LSN?
21. Are both byte lag and time lag measured?
22. Does alerting distinguish idle/no-WAL from a standby not replaying?
23. Is read-after-write routed correctly according to consistency requirements?
24. Do hot standby queries have duration limits and recovery conflict monitoring?
25. Has `hot_standby_feedback` been evaluated together with vacuum/bloat impact?
26. Does a cascading topology monitor every hop?

### 32.5. Synchronous replication

27. Does `synchronous_standby_names` match `application_name`?
28. Are quorum/priority aligned with the availability policy?
29. Is `synchronous_commit` chosen according to durability/latency?
30. Is it understood that transactions using `local`/`off` lack the same remote acknowledgement?
31. Are there alerts for synchronous standby unavailability and waiting commits?

### 32.6. Failover and recovery

32. Is there a single HA authority/quorum?
33. Is the old primary fenced before promotion?
34. Is only one standby promoted?
35. Are lag/RPO evaluated and an appropriate node selected?
36. Is there a timeline/repointing procedure for remaining standbys?
37. Is the old primary rewound/rebuilt before rejoining?
38. Are `pg_rewind` preconditions verified?
39. Are base backups and WAL archives independent of replication?
40. Are failover, switchover, rewind, PITR, and restore drills held regularly?

## 33. Summary

**Physical streaming replication** keeps one or more standbys close to the primary's state by transmitting WAL records. The primary generates WAL and the WAL sender transmits the stream; the standby uses the WAL receiver to receive, write, flush, and replay WAL onto physical data files. A base backup provides the initial foundation for the standby.

Key principles:

- Physical replication copies the entire cluster and requires PostgreSQL major version compatibility.
- A standby must have a base backup; `standby.signal` and `primary_conninfo` put the instance into recovery/streaming mode.
- `pg_basebackup -R -X stream` is the common way to create a standby; a physical slot helps retain required WAL, but retention must be monitored.
- Asynchronous replication reduces commit latency, but can lose acknowledged transactions on failover.
- Synchronous replication uses `synchronous_standby_names` and `synchronous_commit` to wait for remote write/flush/apply per policy, trading off latency and availability.
- Sent, write, flush, and replay LSN are distinct stages; read queries on a standby only see the replayed state.
- Hot standby serves read-only queries, but has recovery conflicts; `hot_standby_feedback` reduces some conflicts and can increase bloat on the primary.
- Cascading replication reduces direct connections to the primary, but lag/dependencies can accumulate across hops.
- Promotion creates a new timeline; fencing the old primary and single-writer ownership prevent split-brain.
- The old primary requires `pg_rewind` when eligible or a new base backup before rejoining.
- Replication does not replace backups: logical errors are replicated; base backups, WAL archiving, and PITR are required.
- Monitoring must cover lag, slots, archive, disk, recovery conflicts, synchronous waits, and role state.
- Failover is only complete once traffic is shifted, data consistency is verified, and standbys are reconfigured.

Guiding principle:

> **Design streaming replication together with WAL retention, fencing, backups, and recovery drills; only consider HA operational when failover and rejoin have been tested end-to-end.**

## 34. References

Official PostgreSQL documentation; select the exact major version of your primary/standby:

- [Warm Standby](https://www.postgresql.org/docs/current/warm-standby.html): streaming replication, standby modes, and cascading.
- [Streaming Replication Protocol](https://www.postgresql.org/docs/current/protocol-replication.html): replication protocol and WAL streaming.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION): WAL sender/receiver, base backup, and standby setup.
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION): `synchronous_standby_names` and `synchronous_commit` behavior.
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html): read-only queries, recovery conflicts, and feedback.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): `wal_level`, `wal_keep_size`, `max_wal_senders`, slots, and WAL settings.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html): primary/standby replication parameters.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html): creating physical base backups and recovery configuration.
- [Replication Functions](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-REPLICATION): `pg_create_physical_replication_slot`, `pg_drop_replication_slot`, `pg_promote`, and LSN functions.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_replication`, `pg_stat_wal_receiver`, and replication statistics.
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html): bringing a diverged cluster back onto the same timeline.
- [Continuous Archiving and Point-in-Time Recovery](https://www.postgresql.org/docs/current/continuous-archiving.html): base backups, WAL archive, and PITR.
- [pg_ctl](https://www.postgresql.org/docs/current/app-pg-ctl.html): start/stop/promote server.
- [Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html): `pg_hba.conf`, authentication methods, and TLS.

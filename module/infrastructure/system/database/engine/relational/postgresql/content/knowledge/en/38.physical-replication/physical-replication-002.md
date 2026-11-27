# WAL-Based Physical Replication and Compatibility Requirements in PostgreSQL

PostgreSQL physical replication maintains a standby by transferring **Write-Ahead Log (WAL)** records from the primary to the standby server, then replaying those records to reproduce changes on the data files. PostgreSQL does not send individual SQL statements or individual changed rows; it sends the WAL stream at the physical level. The standby therefore maintains a copy of the entire cluster in the same storage format.

A physical standby must be initialized from a **base backup** compatible with the primary. Afterward, the standby continuously receives WAL via streaming replication, via a WAL archive, or a combination of both. As the standby replays WAL, the data and physical structures are brought to the same state as the primary at a given LSN point.

Physical replication has strict compatibility constraints:

- Primary and standby must use the same major PostgreSQL version; the WAL and data format are not a major version upgrade protocol.
- Hardware architecture must be compatible; in particular, you cannot stream from a 32-bit system to a 64-bit system.
- Tablespace paths are transmitted as-is; if tablespaces exist, the standby needs corresponding mount paths.
- Build/data-format settings affecting layout must be compatible; you cannot arbitrarily pair clusters created with different block formats.
- The standby must start from a base backup of the right cluster/system identifier and have complete continuous WAL to replay.

```text
       PRIMARY                                  STANDBY
  +----------------+                       +----------------+
  | Transactions   |                       | WAL receiver   |
  | modify pages   |                       |                |
  +-------+--------+                       +--------+-------+
          |                                         |
          v                                         |
  +----------------+       WAL stream               |
  | WAL buffers    | ------------------------------>|
  | and pg_wal     |                                 v
  +----------------+                       +----------------+
          |                                | pg_wal         |
          v                                +--------+-------+
  +----------------+                                 |
  | WAL sender     |                                 v
  +----------------+                       +----------------+
                                           | Startup/replay |
                                           | process        |
                                           +--------+-------+
                                                    |
                                                    v
                                           +----------------+
                                           | Standby pages  |
                                           | (read-only if  |
                                           | hot_standby)   |
                                           +----------------+
```

This lesson belongs to the **Physical Replication** chapter of the *Database Engine Relational PostgreSQL* module. The goal is to understand the WAL-based physical synchronization mechanism, how to set up a standby, how to retain WAL long enough, and how to determine whether two servers are compatible to participate in the same physical replication stream.

After this lesson, you can:

1. Distinguish physical replication, logical replication, and file-based WAL archiving.
2. Explain the roles of the primary, walsender, walreceiver, and startup/recovery process.
3. Understand base backup, system identifier, LSN, and timeline.
4. Build a physical standby using pg_basebackup.
5. Configure the replication role, pg_hba.conf, wal_level, wal_senders, and replication slots.
6. Distinguish asynchronous and synchronous physical replication.
7. Monitor WAL receive/replay lag and identify why a standby falls behind.
8. State the compatibility conditions for major version, architecture, data format, and tablespace paths.
9. Handle WAL retention, archive recovery, cascading replication, and failover.
10. Identify when pg_rewind or a new base backup is required to return an old node as a standby.

> **Practice scope:** Commands to configure replication, create slots, take a base backup, promote, or rewind must only be run on a lab cluster or under an approved operational procedure. Do not run pg_basebackup into a data directory currently in use by PostgreSQL; do not promote a node while the old primary can still accept writes without fencing.

---

## 1. What is physical replication?

### 1.1. Replicating changes at the WAL level

PostgreSQL writes the required changes to WAL before data pages are written to data files. Physical replication sends these WAL records from the primary to the standby. The standby writes the received WAL to its own WAL area and replays it to update data pages.

This is replication at the physical level:

- Does not parse SQL statements to replay statements on the standby.
- Does not selectively choose an individual table or schema to stream.
- Does not require creating publications/subscriptions.
- The standby must have the same physical cluster format and receive valid WAL from the primary.

### 1.2. Primary

The primary is the server receiving normal read/write transactions. When data changes:

1. The backend creates WAL records.
2. WAL is written to WAL buffers and WAL files.
3. The WAL sender reads the WAL records that need to be transmitted.
4. The standby receives the stream and replays the records.

A primary can serve multiple physical standbys simultaneously, within configuration and resource limits.

### 1.3. Standby

A standby is a physical replica operating in recovery mode. It continuously reads WAL from the archive or the primary, then applies the records to keep up with the primary.

A standby does not accept direct write transactions like the primary. When hot standby is enabled, it can serve read-only queries while recovery continues.

### 1.4. Why not replicate row by row?

WAL reflects changes at the storage engine level, including changes needed for heaps, indexes, catalogs, and other components. Streaming WAL allows the standby to reproduce the physical state without re-executing SQL logic.

This also explains why physical replication is tightly coupled to the major version and data layout: the standby must understand the same WAL record format and storage structures as the primary.

### 1.5. One stream covers the entire cluster

Physical replication replicates the cluster, not an individual table. A physical standby receives WAL for every database in the same cluster, along with global catalogs and related objects.

If you only need to replicate certain tables or need a subscriber running a different major version, consider logical replication or an export/import pipeline. Physical replication is not a selective data filtering tool.

---

## 2. Distinguishing physical replication, logical replication, and WAL archiving

| Mechanism | Replication unit | How it is applied | Scope/characteristics |
|---|---|---|---|
| Physical streaming replication | Physical WAL records | Standby replays WAL | Whole cluster, physical standby must be compatible |
| File-based WAL shipping | WAL segment files | Standby restores each segment | Can lag by segment/archive cycle |
| Logical replication | Logical changes from publications | Subscriber applies changes | Table selection, can support major version upgrades |
| Base backup + WAL archive | Data directory snapshot and continuous WAL | Restore base backup then replay WAL | Physical recovery, PITR, and standby bootstrap |

### 2.1. Streaming replication

The primary streams WAL records over a replication connection. The standby can receive changes before a WAL segment fills up or is archived, so latency is typically lower than file shipping.

### 2.2. File-based log shipping

The primary archives WAL segments and the standby fetches each file via `restore_command`. This is an asynchronous mechanism: WAL is archived after it is generated, so there may be a period of time before it is transferred to the standby.

### 2.3. Combining archive and streaming

A standby can use the archive to catch up on older WAL segments, then stream newer records from the primary. Combining both helps the standby recover when a network outage lasts longer than the WAL retained on the primary.

### 2.4. Logical replication is not a physical standby

Logical replication transfers changes at the logical publication/subscription level. A subscriber can have its own schema and usually does not automatically synchronize all sequences, DDL, roles, or all cluster objects.

Physical replication has different semantics: the standby receives WAL and replays storage changes, so data layout/major version compatibility matters.

---

## 3. WAL, LSN, and the synchronization process

### 3.1. WAL records and WAL segments

WAL records are appended to the WAL stream. Records are stored in WAL segment files under the `pg_wal` directory. The segment size is typically 16 MB by default, though it can be changed at initdb time.

A standby does not have to wait for an entire segment to fill up before receiving WAL via streaming replication.

### 3.2. LSN

LSN (Log Sequence Number) is a byte position in the WAL stream. It increases monotonically as WAL records are generated. LSNs help compare progress:

- How far the primary has written WAL.
- How far the primary has sent WAL.
- How far the standby has received/flushed WAL.
- How far the standby has replayed WAL.

An LSN is a position in WAL, not a timestamp.

### 3.3. Checkpoints on the primary

```sql
SELECT
    pg_current_wal_lsn()        AS current_lsn,
    pg_current_wal_insert_lsn() AS insert_lsn,
    pg_current_wal_flush_lsn()  AS flush_lsn;
```

### 3.4. Checkpoints on the standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn()  AS replay_lsn,
    pg_is_in_recovery()       AS is_standby;
```

`pg_last_wal_receive_lsn()` is the last WAL position received and written by the standby; `pg_last_wal_replay_lsn()` is the last position replayed. These two positions can differ when the standby receives WAL faster than it can apply it.

### 3.5. Two stages: receive and replay

A standby can receive WAL first, write it to local WAL storage, and replay it later. Therefore, it is necessary to distinguish:

- **Receive lag:** WAL has not yet reached the standby.
- **Replay lag:** WAL has arrived but has not yet been applied to the database state.

If the receive LSN is close to the primary while the replay LSN lags far behind, the issue typically lies in replay capacity, recovery conflicts, I/O, or the standby workload.

### 3.6. Illustration

```text
Primary WAL:  [------------------------------- LSN 900]
                         |
                         | stream
                         v
Standby WAL:  [------------------------- LSN 850]  received
                         |
                         | replay
                         v
Standby data: [-------------------- LSN 820]       replayed

Receive gap = primary LSN - receive LSN
Replay gap  = receive LSN - replay LSN
```

### 3.7. WAL is not transaction SQL replay

The standby replays WAL records in the required order. It does not re-run INSERT/UPDATE statements from the client. Thus a query executes only on the primary and generates WAL; the standby does not need the same application code to replay physical changes, but still needs the same ability to read the storage/WAL format.

---

## 4. Components of streaming replication

### 4.1. WAL sender

On the primary, each streaming standby connection is served by a WAL sender process. The WAL sender transmits the WAL stream and processes feedback/status from the standby.

You can view WAL senders with:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_stat_replication;
```

### 4.2. WAL receiver

On the standby, the WAL receiver connects to the primary and receives the WAL stream. The `pg_stat_wal_receiver` view displays connection status and received WAL positions.

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
    latest_end_time
FROM pg_stat_wal_receiver;
```

Column names depend on the PostgreSQL version; check the view schema against the running version.

### 4.3. Startup/recovery process

The startup process reads WAL from the archive, local `pg_wal`, or the streaming receiver and replays records. It keeps the standby in recovery mode until promoted.

### 4.4. Walreceiver status feedback

The standby sends status feedback to the primary to report how far WAL has been written/flushed/replayed. The primary uses this information for monitoring, synchronous replication, and managing WAL retention/slots.

### 4.5. Replication protocol

The standby connects to the `replication` pseudo-database using a role with the REPLICATION privilege. The connection is authenticated via pg_hba.conf, typically using TLS and SCRAM/password or certificate authentication depending on the environment.

### 4.6. Replication role

Create a dedicated role:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-secret';
```

Do not use a superuser for the standby unless there is a specific operational reason. The REPLICATION privilege is very powerful because the WAL stream can contain sensitive data; grant it only to trusted hosts and protect the credentials.

---

## 5. Compatibility requirements for physical replication

### 5.1. Same major PostgreSQL version

Physical log shipping/streaming between two servers on different major versions is generally not supported. For example, a PostgreSQL 17 primary cannot have a PostgreSQL 16 or 18 physical standby simply by pointing primary_conninfo to the other server.

WAL format, system catalogs, and storage internals can change between major releases. To upgrade a major version, use a procedure such as pg_upgrade, dump/restore, or appropriate logical replication; do not treat physical replication as a major upgrade path.

### 5.2. Minor version

PostgreSQL does not intentionally change the disk format in minor release updates, so two different minor versions can likely work together. However, the PostgreSQL documentation does not provide a formal support guarantee for every combination of minor versions.

Safe practices:

- Keep primary and standby on the same minor release when possible.
- When updating a minor release, update the standby first and then the primary.
- Check release notes, extension compatibility, and restart procedures.
- Avoid maintaining mismatched versions long-term.

### 5.3. Same hardware architecture

Hardware architecture must be compatible. Physical log shipping from a 32-bit system to a 64-bit system does not work. The two machines do not need the exact same CPU model or RAM size, but they must share a compatible architecture capable of reading each other's data/WAL representation.

### 5.4. Operating system and binary build

Use a similar operating system and PostgreSQL build to reduce operational risk. Storage formats are platform/build-dependent, such as integer/float representations and compile-time options. Do not assume a data directory can be freely moved across arbitrary OSes or binary builds.

### 5.5. Block size and WAL block size

PostgreSQL has build-time settings that affect data layout, such as database block size (`BLCKSZ`) and WAL block size (`XLOG_BLCKSZ`). Changing these build values changes on-disk compatibility.

Primary and standby need compatible binary/data formats. Using the same PostgreSQL distribution/build configuration reduces risk; if building PostgreSQL from source with custom block sizes, verify matching values before creating a physical standby.

### 5.6. WAL segment size

WAL segment size is determined when initializing the cluster and may differ from the 16 MB default. A physical standby created from a base backup inherits the control/data state of the source cluster; do not independently initdb a cluster with a different WAL layout and expect to join the stream.

When setting up a standby, use pg_basebackup from the primary to obtain the right cluster layout. With custom backup/restore tools, preserve the required format parameters.

### 5.7. Tablespace paths

Tablespace paths are transmitted through WAL using their configured paths. If the primary has a tablespace mounted at `/data/pg_tblspc/fastspace`, the standby needs the corresponding path available.

When creating a new tablespace on the primary, prepare the mount point/path on every standby before running CREATE TABLESPACE. Otherwise, replay may fail due to a missing path or improper filesystem permissions.

### 5.8. System identifier

Primary and standby must belong to the same cluster lineage. A base backup taken from the primary preserves that cluster's system identifier. A separately initdb'd cluster has a different system identifier and cannot become a physical standby merely by adding standby.signal and primary_conninfo.

Check with:

```sql
SELECT system_identifier
FROM pg_control_system();
```

This function requires appropriate privileges and must be run on each server to compare.

### 5.9. Locale, collation, and extensions

A physical standby inherits the data directory and catalogs from the primary; you cannot create a new database cluster with a different locale/collation and attach WAL to it. Extension binaries must be compatible with the server build and present on the standby when extensions/libraries need to be loaded.

For a standby created via base backup, extension SQL objects and data already reside in the data directory. However, shared libraries, OS packages, custom modules, and configuration files outside the data directory must still be installed/synchronized separately.

### 5.10. Compatibility checklist

| Condition | Practical requirement | How to verify |
|---|---|---|
| Major version | Must match major version | `SHOW server_version` |
| Minor version | Should match release; mismatched minors lack formal support | `SELECT version()` and release notes |
| Hardware architecture | Must share compatible architecture | OS/CPU architecture |
| Data/WAL build format | Compatible block/layout settings | Build metadata, initdb/build options |
| WAL segment layout | Must come accurately from source cluster | Base backup/control data |
| System identifier | Same cluster lineage | `pg_control_system()` |
| Tablespace paths | Corresponding mount paths must exist | `pg_tablespace_location()` and filesystem |
| Extension binaries | Compatible builds present on standby | Installed packages/shared libraries |
| Replication protocol | Valid replication connection and auth | pg_hba.conf, role, logs |

---

## 6. Preparing the primary to send WAL

### 6.1. Enable an appropriate wal_level

On the primary, `wal_level` must be sufficient to generate WAL for physical replication:

```conf
wal_level = replica
```

`replica` is the level commonly used for a physical standby. `logical` also includes what is needed for physical replication and adds information for logical decoding. `minimal` is not suitable for a streaming standby.

### 6.2. Configure the number of WAL senders

```conf
max_wal_senders = 10
```

`max_wal_senders` limits the number of concurrent WAL sender connections. Account for:

- Physical standby connections.
- `pg_basebackup` using streaming WAL.
- WAL-receiving programs such as `pg_receivewal`.
- Spare connections needed during failover/rebuild.

Setting this value too low can prevent a standby or base backup from connecting.

### 6.3. Replication slots

If using physical replication slots, configure enough slots:

```conf
max_replication_slots = 10
```

Slots help the primary retain WAL that the standby has not yet received. They reduce the risk of required WAL being recycled when a standby is temporarily disconnected.

### 6.4. Fallback WAL retention

```conf
wal_keep_size = 2GB
```

`wal_keep_size` only sets a minimum amount of WAL retained so a standby has a chance to catch up. It is not a guarantee to keep all WAL needed for a standby that goes offline for a long time. If lag exceeds the retained WAL, the standby may need to fetch from an archive or be recreated from a base backup.

### 6.5. Limiting WAL retained by replication slots

```conf
max_slot_wal_keep_size = 20GB
```

This example value caps the amount of WAL retained by replication slots per checkpoint. If a slot falls too far behind and required WAL is removed, the standby may lose the ability to continue streaming via that slot and need the archive or reinitialization.

A value of `-1` means no limit is enforced by this parameter; an unconsumed slot can cause `pg_wal` to grow very large. Monitor disk usage closely.

### 6.6. Enable WAL archiving when needed

```conf
archive_mode = on
archive_command = 'test ! -f /archive/%f && cp %p /archive/%f'
```

This is an illustrative lab example. Production should use a durable archive destination, retry/error handling, checksum verification, and a retention policy. Do not use a simple copy command without ensuring permissions, atomic publish, and duplicate file handling.

### 6.7. listen_addresses

The primary must listen on an interface reachable by the standby:

```conf
listen_addresses = '*'
port = 5432
```

In production, restrict to specific interfaces and firewall rules instead of opening all interfaces unnecessarily.

### 6.8. pg_hba.conf

Allow the replication user from the standby address:

```conf
# TYPE  DATABASE      USER         ADDRESS         METHOD
hostssl replication   replicator   10.20.0.12/32   scram-sha-256
```

The database field must be the `replication` pseudo-database for replication connections. Use `hostssl` when TLS is required; combine with client certificate verification and firewall/network policy.

### 6.9. Reload or restart

Some replication settings require a restart; others can be reloaded. Check the context in `pg_settings`:

```sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_slot_wal_keep_size',
    'archive_mode',
    'listen_addresses'
)
ORDER BY name;
```

`wal_level`, `max_wal_senders`, `max_replication_slots`, `archive_mode`, and `listen_addresses` usually require a restart depending on context/version. Perform restarts in a controlled manner.

---

## 7. Creating the replication role and authenticating connections

### 7.1. Create a dedicated role

On the primary:

```sql
CREATE ROLE replicator
    WITH LOGIN REPLICATION PASSWORD 'replace-with-a-strong-secret';
```

A REPLICATION role is permitted to open a replication connection and read the WAL stream. Protect the role as a sensitive credential; WAL can contain data contents at the physical level.

### 7.2. Do not hardcode passwords in shared scripts

Avoid committing passwords into repositories or storing them in command history. You can use:

- A libpq password file with appropriate filesystem permissions.
- A secret manager.
- Certificate authentication.
- Protected service configuration.

### 7.3. Password file

On Unix-like systems, the `~/.pgpass` file has the format:

```text
hostname:port:replication:replicator:secret
```

Set file permissions so only the owner can read/write:

```bash
chmod 0600 ~/.pgpass
```

On Windows, the pgpass file uses the corresponding config location and ACL protection; `chmod` does not apply.

### 7.4. Verify privileges and connectivity

You can check the role:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper
FROM pg_roles
WHERE rolname = 'replicator';
```

Do not use a normal database connection to conclude that replication authentication works. Test with `pg_basebackup` or a replication protocol client from the standby host.

### 7.5. Firewall and TLS

Only allow standby hosts to connect to the PostgreSQL port. If traversing an untrusted network:

- Enable TLS on the primary.
- Use `sslmode=verify-full` when appropriate with your PKI.
- Verify the CA and hostname.
- Protect the passfile/certificate private key.
- Do not use `trust` for a production replication network.

---

---

## 8. Building a standby with pg_basebackup

### 8.1. Base backup as the starting point

A standby must have a consistent physical copy of the data directory. `pg_basebackup` takes a base backup from a running server and ensures enough WAL is included to restore the backup to a consistent state.

Do not manually copy a running data directory with ordinary file copy commands. File copies are not coordinated with checkpoints/WAL and can produce an inconsistent set of files.

### 8.2. Prepare the data directory

The target standby must:

- Run a compatible PostgreSQL major version.
- Have an empty target data directory or one prepared per the tool's instructions.
- Have appropriate owner/permissions for the OS account running PostgreSQL.
- Have sufficient disk space for data files, WAL, and tablespaces.
- Have corresponding tablespace mount paths if the primary uses tablespaces.

Do not overwrite a running cluster.

### 8.3. Plain-format base backup

Example run from the standby host:

```bash
pg_basebackup \
  --host=primary.example.net \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/main \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf
```

`--wal-method=stream` streams WAL in parallel with copying data files so the base backup has the required WAL. `--write-recovery-conf` (short flag `-R`) writes configuration for the server to start in standby mode, including `standby.signal` and the relevant connection settings.

### 8.4. Creating and using a physical replication slot

If you want `pg_basebackup` to create the slot:

```bash
pg_basebackup \
  --host=primary.example.net \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/main \
  --format=plain \
  --wal-method=stream \
  --create-slot \
  --slot=standby_a \
  --progress \
  --write-recovery-conf
```

`--create-slot` creates a slot with the specified name; `--slot` specifies the slot to use. If the slot already exists, do not pass `--create-slot` again; choose the right slot and ensure it does not belong to another standby.

### 8.5. WAL method

`pg_basebackup` supports WAL retrieval methods such as:

- `stream`: receives streaming WAL while the base backup runs.
- `fetch`: downloads required WAL segments from the primary at the end of the backup; those segments must still exist in `pg_wal` until fetched, requiring sufficient WAL retention.
- `none` on supported versions: the backup does not fetch WAL itself; only use when another process guarantees complete WAL.

For a new standby, `stream` is usually easier to operate, though it requires an extra WAL sender connection and network resources.

### 8.6. Directory format

`pg_basebackup` also supports tar or manifest/checksum options depending on version. Regardless of format, the goal remains creating a consistent base backup with enough WAL. Read `pg_basebackup --help` and the documentation for your exact major version.

### 8.7. After the base backup

Verify:

- The data directory contains cluster data and the control file.
- `standby.signal` was created by `-R`.
- `postgresql.auto.conf` contains `primary_conninfo`/slot if configured.
- Owner and permissions are correct.
- Tablespace symlinks/paths are valid.
- The WAL archive or streaming source is reachable.

### 8.8. Starting the standby

Start PostgreSQL using your environment's service manager/`pg_ctl`. On the standby:

```sql
SELECT pg_is_in_recovery();
```

A result of `true` indicates the server is in recovery/standby mode.

### 8.9. Do not run initdb first and mix files

If you already ran `initdb` on a different cluster in the target data directory, do not partially overwrite files to turn it into a standby. Use an empty data directory with `pg_basebackup`, or restore a base backup using an appropriate tool.

---

## 9. Configuring the standby to connect to the primary

### 9.1. standby.signal

PostgreSQL recognizes standby mode when the `standby.signal` file exists in the data directory at server startup.

`pg_basebackup -R` creates this file automatically. If configuring manually, create the signal file in the right data directory and ensure proper permissions.

### 9.2. primary_conninfo

In `postgresql.conf` or `postgresql.auto.conf`:

```conf
primary_conninfo = 'host=primary.example.net port=5432 user=replicator application_name=standby_a sslmode=verify-full'
```

`application_name` helps the primary identify the standby in `pg_stat_replication` and select synchronous standbys. Do not embed a plaintext password if you can use a passfile/secret management.

### 9.3. primary_slot_name

```conf
primary_slot_name = 'standby_a'
```

The slot must exist on the primary. The standby uses this slot so the primary retains needed WAL while the standby is offline or slow.

### 9.4. restore_command

If using a WAL archive:

```conf
restore_command = 'cp /archive/%f %p'
```

Production requires handling missing-file errors, retries, and archive verification. The `cp` example is only appropriate for a lab where the archive is on the same host/filesystem.

### 9.5. hot_standby

```conf
hot_standby = on
```

Hot standby allows read-only queries during recovery. Some configurations default `hot_standby` to `on`, so verify the value and version.

### 9.6. Connecting from the standby

The WAL receiver connects to the primary using a replication connection. On the primary, `pg_stat_replication` should show a row for the standby; on the standby, `pg_stat_wal_receiver` should show streaming status.

### 9.7. Tablespace paths

Verify every mount path used by the primary. If the base backup created symlinks under `pg_tblspc`, the symlink targets must exist with appropriate permissions on the standby.

---

## 10. Replication slots and WAL retention

### 10.1. The WAL recycling problem

The primary does not keep every WAL segment forever. After a checkpoint, old segments may be recycled or removed when no longer needed for recovery, archiving, or replication.

If a standby disconnects for a long time and the required WAL has already been recycled, the standby cannot resume from the old LSN via streaming alone. It must fetch WAL from the archive if complete, or be reinitialized from a new base backup.

### 10.2. Physical replication slots

A physical replication slot retains WAL needed for a standby. The standby sets `primary_slot_name` pointing to the slot on the upstream primary.

Create a slot manually:

```sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
```

Drop a slot when certain the standby no longer uses it:

```sql
SELECT pg_drop_replication_slot('standby_a');
```

Do not drop a slot just because it looks inactive; the standby might be paused or need the slot to catch up after maintenance.

### 10.3. Slot WAL retention and disk-full risk

An inactive slot can still retain WAL. If a standby stops running while its slot remains, the primary can accumulate a lot of WAL in `pg_wal`.

Monitor:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
```

Some columns only exist in newer PostgreSQL versions. For queries targeting multiple major versions, select only common columns such as `slot_name`, `slot_type`, `active`, and `restart_lsn`.

### 10.4. max_slot_wal_keep_size

`max_slot_wal_keep_size` limits the amount of WAL that replication slots are allowed to retain across checkpoints. If the limit is exceeded, the slot may lose its ability to guarantee the required WAL and the standby must retrieve WAL from the archive or be recreated.

A value of `-1` allows slots to retain WAL without a limit from this parameter. That helps standbys catch up after a long outage, but carries the risk of filling the filesystem.

### 10.5. wal_keep_size

`wal_keep_size` keeps a minimum amount of WAL in `pg_wal` so a standby has a chance to catch up without a slot. It is a minimum threshold, not an absolute guarantee that all needed WAL will remain.

### 10.6. Archive as a supplemental recovery path

If WAL segments are archived durably, a standby can use `restore_command` to retrieve missing segments and then return to streaming. The archive should be stored independently from primary storage so a primary failure does not simultaneously destroy the only WAL copy.

### 10.7. Choosing slots, wal_keep_size, or archive?

| Mechanism | Advantages | Risks/limitations |
|---|---|---|
| Replication slot | Retains the exact WAL needed by consumer | Inactive slots can fill the primary disk |
| wal_keep_size | Simple, no separate slot needed | Only keeps a minimum; long standby lag still loses WAL |
| WAL archive | Recovers WAL by segment from independent storage | Needs `archive_command`, retention, monitoring, and throughput |
| Slot + archive combined | More flexible catch-up paths | More components to monitor |

### 10.8. Do not leave orphan slots

Every slot needs a clear owner and purpose. When decommissioning a standby:

1. Confirm the node is stopped and no longer needs WAL.
2. Remove `primary_slot_name` from the node if still in use.
3. Inspect the slot on the primary.
4. Confirm the slot does not serve another node.
5. Drop the slot per the change procedure.
6. Monitor WAL disk usage after dropping the slot.

---

## 11. Asynchronous and synchronous physical replication

### 11.1. Asynchronous is the default

Streaming replication defaults to asynchronous. The primary does not wait for the standby to acknowledge WAL before returning a successful COMMIT to the client.

This reduces commit latency and avoids depending on standby availability to continue writes. On the flip side, if the primary fails abruptly, committed transactions whose WAL has not yet reached the standby may be lost if the standby is promoted.

### 11.2. Synchronous replication

Synchronous replication lets the primary wait for one or more synchronous standbys to acknowledge WAL according to policy. Primary configuration:

```conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
```

The `application_name` in the standby's `primary_conninfo` must match a name in the list. The selected standby must be in the `streaming` state in `pg_stat_replication`.

### 11.3. synchronous_commit levels

| Value | Standby-related ACK condition |
|---|---|
| `off` | Does not wait for local WAL flush per commit; does not wait for standby |
| `local` | Waits for local WAL flush, does not wait for standby |
| `remote_write` | Waits for standby to write WAL to OS, not yet flushed to durable storage |
| `on` | Waits for standby to flush WAL per synchronous replication policy |
| `remote_apply` | Waits for standby to replay WAL so transactions are visible to queries |

If no synchronous standby is configured, `on` still waits for local flush but does not automatically provide remote durability.

### 11.4. FIRST and ANY

```conf
# Select one standby by priority
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'

# Wait for any two standbys in the group
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

`FIRST` selects by priority in the list. `ANY` uses quorum: commits wait for the minimum number of acknowledgements from the group.

### 11.5. Availability tradeoff

If policy requires a synchronous standby and no eligible node is streaming, commits requiring synchronous acknowledgement can block. Synchronous replication increases protection for ACKed transactions under the failure model, but makes write availability dependent on standbys/network.

### 11.6. Synchronous standbys must connect directly

The primary selects synchronous standbys from standbys connected directly to it. The primary does not treat a downstream standby behind a cascading node as its direct synchronous standby.

If quorum or commit acknowledgement is needed across sites, topology design and synchronous policy must account for direct connections and actual latency.

### 11.7. Do not confuse synchronous replication with backup

A synchronous standby replays both valid changes and committed logical mistakes. It does not protect against `DROP TABLE`, accidental `DELETE`, ransomware with write privileges, or application bugs. Independent backups and WAL archives are required.

---

## 12. Timeline, promotion, and failover

### 12.1. What is a timeline?

Timelines mark branches of WAL history. When a standby is promoted to primary, PostgreSQL creates a new timeline to distinguish the new WAL history from the old primary's history.

Timeline history files describe the branching point. They help recovery understand which WAL branch belongs to the cluster's history after failover.

### 12.2. Promote a standby

When deciding to fail over:

```sql
SELECT pg_promote(wait => true);
```

Or use:

```bash
pg_ctl promote -D /path/to/standby-data
```

Promotion brings the standby out of recovery and allows it to accept writes. This is a cluster role change operation; you must verify the old primary has been fenced or cannot continue accepting writes.

### 12.3. Split brain

Split brain occurs when the old primary and the promoted standby both accept independent writes at the same time. The two WAL branches diverge; PostgreSQL does not automatically merge transactions written on two primaries.

Before promoting:

- Confirm the primary is truly down or isolated.
- Use fencing/STONITH or an equivalent infrastructure mechanism.
- Prevent clients from continuing to write to the old primary.
- Pick the standby with the most suitable WAL state per failover policy.
- Record timeline/LSN and RPO decision.

### 12.4. Automatic failover is not part of streaming replication core

Streaming replication transmits WAL and replays it on the standby. Detecting primary failure, leader election, fencing, endpoint updates, and promotion are typically orchestrated by an operator or HA manager.

Do not assume having a streaming standby automatically provides safe failover.

### 12.5. Rejoin the old primary

After a new standby is promoted, the old primary cannot simply be restarted as an independent primary. It has a different timeline history and may contain writes that do not exist on the new primary.

To bring the old node back into the topology:

- Use `pg_rewind` if conditions are met.
- Or remove/recreate the data directory from a new base backup.
- Reconfigure the node as a standby and verify it follows the new timeline.

### 12.6. recovery_target_timeline

A standby can choose which timeline to follow via:

```conf
recovery_target_timeline = 'latest'
```

`latest` tells the standby to follow the newest timeline it finds in WAL/archive. Keep timeline history files in the archive and verify the correct cluster lineage.

---

---

## 13. Cascading physical replication

### 13.1. Standby as upstream for another standby

Cascading replication lets a standby receive WAL from the primary and forward WAL to downstream standbys. This reduces direct WAL sender connections on the primary and can distribute WAL across sites.

```text
                 PRIMARY
                    |
              WAL streaming
                    |
                    v
                STANDBY A
                    |
              WAL streaming
                 /      \
                v        v
           STANDBY B  STANDBY C
```

### 13.2. Configuration requirements

The intermediate node must be configured to send WAL downstream, including an appropriate `wal_level` and a large enough `max_wal_senders`. Downstream standbys configure `primary_conninfo` pointing to the upstream standby.

### 13.3. Synchronous policy limits

The primary only knows about standbys connected directly to it. It does not directly pick standby B/C behind standby A as its synchronous standby.

If A lags or goes down, B/C can lose their WAL source even if the primary is still running. Design upstream failover and slots/archiving for each branch.

### 13.4. Replication slots per upstream

Downstream standbys can use physical slots on the upstream standby if configuration supports it. Slots must be managed on the node sending WAL to that downstream. Monitor slots at every tier to prevent any node from retaining WAL too long.

### 13.5. When to use cascading?

- There are many standbys and you want to reduce direct connections to the primary.
- Standbys are located in another site/region.
- You want to distribute read replicas across a topology.
- Bandwidth or connections from the primary need to be limited.

In trade-off, downstream lag can accumulate across tiers and depends on the health of each upstream.

---

## 14. Monitoring replication and measuring lag

### 14.1. On the primary: pg_stat_replication

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
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
```

Meaning:

- `sent_lsn`: last WAL sent to the standby.
- `write_lsn`: WAL written by the standby to the OS/file layer.
- `flush_lsn`: WAL flushed by the standby.
- `replay_lsn`: WAL replayed by the standby.
- `sync_state`: whether the standby is `async`, `potential`, `sync`, or `quorum` per configuration.

### 14.2. LSN distances on the primary

```sql
SELECT
    application_name,
    pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)
        AS bytes_not_sent,
    pg_wal_lsn_diff(sent_lsn, write_lsn)
        AS bytes_sent_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn)
        AS bytes_written_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn)
        AS bytes_flushed_not_replayed
FROM pg_stat_replication;
```

These are distances at query time. LSNs change continuously while the primary writes WAL; do not rely on a single snapshot to conclude a standby is broken.

### 14.3. On the standby: receive and replay

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit_time;
```

`pg_last_xact_replay_timestamp()` is the commit timestamp of the last replayed transaction, not an accurate measure of network lag across all workloads. If the primary has no writes, the timestamp can look old even when the standby is completely caught up.

### 14.4. WAL receiver

```sql
SELECT
    status,
    sender_host,
    sender_port,
    slot_name,
    written_lsn,
    flushed_lsn,
    received_tli,
    last_msg_send_time,
    last_msg_receipt_time
FROM pg_stat_wal_receiver;
```

If there is no row, the standby may be reading WAL from archive, not configured for streaming, already promoted, or encountering a connection failure. Inspect logs and `primary_conninfo`.

### 14.5. Measuring lag in time

You can use `write_lag`, `flush_lag`, and `replay_lag` from `pg_stat_replication` to inspect recent latency. These fields are time statistics reflecting how WAL is sent/written/flushed/replayed; they can be NULL when idle or without enough recent samples.

Do not treat `now() - pg_last_xact_replay_timestamp()` as absolute lag if the primary has no write traffic. Combine LSN gap, transaction activity, and WAL rate.

### 14.6. Replication state

`state` normally shows `streaming` when the standby is continuously receiving the stream; other states can reflect startup/catchup/backup. Use `state` together with logs, LSNs, and the receiver view to diagnose issues.

### 14.7. Replication conflicts on hot standby

On the standby:

```sql
SELECT
    datname,
    confl_tablespace,
    confl_lock,
    confl_snapshot,
    confl_bufferpin,
    confl_deadlock
FROM pg_stat_database_conflicts
ORDER BY datname;
```

These counters show standby queries canceled due to recovery conflicts. Column names/fields may vary across major versions; verify against the current schema.

### 14.8. Monitoring checklist

- Does the primary have a WAL sender in `streaming` state?
- Does the standby have an active WAL receiver?
- Is receive LSN advancing?
- Is replay LSN advancing?
- Is the receive/replay gap growing continuously?
- Are slots retaining excessive WAL?
- Does the archive have errors or a backlog?
- Are there recovery conflicts/canceled queries?
- Do storage/network have sufficient throughput?
- Does `sync_state` match the desired policy?

---

## 15. Bringing the old primary back via pg_rewind or base backup

### 15.1. Why not just restart the old node?

After failover, the new primary continues writing on a new timeline. The old primary may have WAL/data changes on the old timeline that the new primary lacks. If the old node starts in primary mode on its own, two branches diverge and cause split brain.

### 15.2. pg_rewind

`pg_rewind` synchronizes a diverged data directory with a source cluster by identifying blocks changed since the common point and copying only the needed blocks. It is usually faster than a full base backup when only a small fraction of data files changed.

### 15.3. Important preconditions

For `pg_rewind` to work:

- Target and source share a common cluster history before divergence.
- Target was cleanly shut down before rewinding.
- `wal_log_hints` was enabled on the cluster before divergence, or data checksums were enabled at initdb.
- `full_page_writes` must be enabled.
- Required WAL to determine block changes since the common checkpoint is available; if missing, a WAL archive must be available or a new base backup must be chosen.

Verify preconditions before running. Do not enable `wal_log_hints` after divergence and expect it to retroactively provide enough information for `pg_rewind`.

### 15.4. pg_rewind example

Example run on the stopped old node's host:

```bash
pg_rewind \
  --target-pgdata=/var/lib/postgresql/18/old-primary \
  --source-server='host=new-primary.example.net port=5432 user=rewind_user dbname=postgres'
```

The command requires the source server to have permissions to read the needed information and the target data directory to be shut down. Depending on version, configure `--restore-target-wal` or supply a WAL archive if required WAL is not present on the target.

### 15.5. After rewind

1. Configure `standby.signal`.
2. Update `primary_conninfo` to point to the current primary.
3. Configure the appropriate replication slot if used.
4. Verify tablespace paths, extension libraries, and permissions.
5. Start the node.
6. Verify `pg_is_in_recovery()` returns true.
7. Verify WAL receiver, sender, and replay LSN.

### 15.6. When is a new base backup needed?

Use a new base backup if:

- `pg_rewind` preconditions are not met.
- Required WAL is lost and no archive exists.
- The target has corruption or cluster lineage is uncertain.
- Major version/format is incompatible.
- You want to rebuild the node cleanly via standard procedure.

Do not force `pg_rewind` to run on two clusters that do not share the same lineage.

---

## 16. Compatibility requirements and major version upgrades

### 16.1. Physical replication is not a major upgrade

A PostgreSQL 17 primary and a PostgreSQL 18 standby cannot directly stream physical WAL like two minor releases of the same major version. WAL record formats and internal catalog/storage structures change across major versions.

### 16.2. Upgrade options

When upgrading a major version, consider:

- `pg_upgrade`: upgrades the data directory through the supported procedure.
- Dump/restore: creates a new cluster and loads a logical backup.
- Logical replication: syncs changes to a new major version cluster during migration.

Physical replication can be used once both nodes are on the same major version with matching cluster lineage.

### 16.3. Minor upgrades

Minor releases are designed to preserve disk format compatibility, though arbitrary mismatched minor versions should not be treated as formally supported. Updating standbys first is the safe approach recommended by the documentation, followed by updating the primary in a maintenance procedure.

### 16.4. Binary packages and extensions

Ensure:

- PostgreSQL binaries match the data directory's major version.
- Extension shared libraries are installed at matching versions/builds.
- Custom C modules, preload libraries, and background workers exist on the standby.
- OS packages, locale libraries, and collation providers are compatible.
- Configuration files outside PGDATA are managed separately.

### 16.5. Tablespace migration

If mount paths need to change between primary and standby, direct physical replication may not fit because WAL carries cluster tablespace paths. Design matching mount paths or choose a migration/restore method capable of explicitly remapping tablespaces.

### 16.6. Decision matrix

| Primary | Standby | Physical replication |
|---|---|---|
| PostgreSQL 18.x | PostgreSQL 18.x | Suitable when other format requirements match |
| PostgreSQL 18.x | PostgreSQL 18.y | May work, but minor releases should be aligned |
| PostgreSQL 17.x | PostgreSQL 18.x | Cross-major physical streaming is not supported |
| 32-bit | 64-bit | Incompatible |
| Same major, different data block/build format | Different format | Incompatible |
| Same cluster, valid base backup, tablespace paths ready | Standby | Suitable baseline conditions |

---

## 17. Troubleshooting physical replication

### 17.1. Standby cannot connect to primary

Check in order:

1. DNS/hostname and network route.
2. Whether firewall/security groups allow the PostgreSQL port.
3. Whether the primary is listening on the right interface/port.
4. Whether `pg_hba.conf` has a rule for the `replication` pseudo-database and the right client address.
5. Whether the role has `LOGIN` and `REPLICATION`.
6. Whether password/passfile/certificates are valid.
7. Whether `max_wal_senders` has available capacity.
8. Whether `primary_conninfo` has the right host, port, user, and `application_name`.

Read logs on both nodes; authentication failures, connection refused, and timeouts have different root causes.

### 17.2. FATAL: no pg_hba.conf entry for replication connection

The `pg_hba.conf` rule may be missing the `replication` database field, user, or standby IP address. Check rule ordering because PostgreSQL uses the first matching rule.

After editing, reload configuration:

```sql
SELECT pg_reload_conf();
```

### 17.3. requested WAL segment has already been removed

The standby needs a WAL segment that was recycled/deleted on the primary. Remediation steps:

- Check if the WAL archive has that segment and whether `restore_command` works.
- Check if the replication slot was invalidated or lost WAL.
- If continuous WAL is no longer available, take a new base backup.

Never copy an arbitrary segment from another cluster into `pg_wal`. WAL must belong to the right system identifier/timeline and be continuous in recovery history.

### 17.4. Standby receives WAL but replays slowly

If receive LSN advances while replay LSN falls behind:

- Check storage read/write latency on the standby.
- Check CPU and I/O contention.
- Check recovery conflicts and long queries on the hot standby.
- Check the WAL record rate from the primary.
- Check whether the standby has enough resources to replay the workload.

Increasing the WAL sender count will not fix a replay bottleneck.

### 17.5. Standby lag keeps growing

Compare:

- Primary current LSN.
- Sent/write/flush/replay LSN.
- Network throughput/packet loss.
- Standby storage throughput.
- WAL generation rate.

If the gap between current and sent grows, the primary/network sender may be the bottleneck. If sent is close to receive while replay lag is large, focus on standby apply.

### 17.6. pg_wal on the primary grows rapidly

Check:

- Inactive/lagging replication slots.
- Slot `restart_lsn`.
- `max_slot_wal_keep_size`.
- `archive_command` failures.
- Disconnected standbys.
- Other backup/replication consumers.

Never manually delete WAL files needed for recovery/replication.

### 17.7. Tablespace path missing

The standby can fail replay if a tablespace mount point does not exist or has wrong permissions. Cross-check `pg_tablespace_location()` on the primary, symlinks in `pg_tblspc` on the standby, and mount configuration.

### 17.8. Standby cancels queries due to recovery conflict

If hot standby queries are canceled:

- Check `pg_stat_database_conflicts`.
- Inspect query age and wait events.
- Evaluate `max_standby_streaming_delay` and `max_standby_archive_delay`.
- Consider `hot_standby_feedback` if appropriate.
- Monitor bloat on the primary if feedback is enabled.

Do not increase delays indefinitely without evaluating WAL replay lag and disk growth.

### 17.9. WAL receiver does not appear

Check:

- Whether `standby.signal` is in the right data directory.
- Whether `primary_conninfo` is being read.
- Whether the server started the right cluster.
- Whether the standby is still replaying archived WAL before starting streaming.
- Whether logs show authentication/network errors.

If the node has already been promoted, it is no longer a standby and has no WAL receiver under the old topology.

### 17.10. Base backup fails

Check:

- Whether the data directory is in the proper empty/target state.
- Whether the role has replication privileges.
- Whether `max_wal_senders` has enough slots for streaming backup.
- Whether the replication slot name conflicts.
- Destination disk space and tablespace mounts.
- Network timeouts and logs.

Clean up/move incomplete artifacts per procedure, then retry into a clean destination. Never start an incomplete base backup as a valid cluster.

---

## 18. Operating and maintaining physical standbys

### 18.1. Routine health monitoring

Set up alerts for:

- Standby no longer streaming.
- Receive/replay lag exceeding thresholds.
- WAL slots retaining too much space.
- Archive command failures.
- Filesystems nearly full.
- Abnormal increases in recovery conflicts.
- Standby restarts or timeline changes.

### 18.2. Check compatibility before changes

Before minor upgrades, OS upgrades, extension upgrades, tablespace changes, or storage swaps:

1. Check PostgreSQL major/minor versions.
2. Verify data/WAL build settings.
3. Verify hardware architecture.
4. Verify tablespace mount paths.
5. Verify extension libraries and preload modules.
6. Review release notes and compatibility notes.
7. Plan to update standbys before the primary for minor releases.

### 18.3. Adding a new standby

Procedure:

1. Prepare host, storage, and mount paths.
2. Install a compatible PostgreSQL major/build.
3. Create replication role/`pg_hba` rules.
4. Configure sender/slot capacity and retention.
5. Run `pg_basebackup`.
6. Configure `primary_conninfo`, slot, archive.
7. Start the standby.
8. Verify streaming, receive/replay, and system identifier.
9. Add to monitoring/alerting.

### 18.4. Decommissioning a standby

1. Shift read traffic to another node if applicable.
2. Stop the standby per procedure.
3. Confirm the slot is no longer needed.
4. Drop the slot on upstream once safe.
5. Remove HA/monitoring/DNS configuration.
6. Revoke replication credentials.
7. Handle the data directory per retention/security policy.

### 18.5. Backups for primary and standby

A standby does not replace backups. If both primary and standby receive an accidental DELETE or logical corruption, both can hold the corrupted state. Independent backups, WAL archives, and restore drills are needed.

### 18.6. Read scaling

Hot standbys can serve read-only queries, but:

- Reads from a standby can be stale relative to the primary.
- Long-running queries can conflict with recovery.
- Read workloads reduce resources available for WAL replay.
- Read-only transactions cannot write data to the standby.

Applications must tolerate replication lag and handle read-after-write routing explicitly.

### 18.7. Failover drills

Test periodically in lab/staging:

- Primary loss.
- Selecting a standby by LSN/policy.
- Fencing the old primary.
- Promoting the standby.
- Verifying data and application connectivity.
- Rewinding/rebuilding the old node.
- Measuring RTO and determining actual RPO.

Only once tested does a failover runbook reflect the real behavior of the deployed topology.

---

## 19. Common misconceptions

**1. "Physical replication sends SQL statements from primary to standby."** False. It transmits WAL records at the physical level.

**2. "You can physically replicate a single individual table."** No. A physical standby receives WAL for the entire cluster.

**3. "A standby can run a newer major version than the primary."** Not in normal physical streaming. Both nodes require the same major version.

**4. "Different minor versions are always formally supported."** No. Minor disk formats are kept compatible by policy, yet the documentation recommends matching release levels and does not formally guarantee every combination.

**5. "Both machines must have the exact same CPU model."** No. Hardware does not have to be identical, but hardware architecture must be compatible; 32-bit and 64-bit cannot physically log-ship to each other.

**6. "Different OSes always work because WAL is just bytes."** False. Data/WAL formats depend on architecture/build; a compatible environment is required and keeping OS/builds aligned is recommended.

**7. "Having the same major version is enough."** Not enough. You also need matching cluster lineage, data/WAL formats, tablespace paths, extension libraries, and other operational requirements.

**8. "An independently initialized cluster can join the primary."** No. A standby requires a base backup with the same system identifier/cluster lineage.

**9. "Copying the data directory with cp while the primary is running equals a base backup."** False. Ordinary file copies do not guarantee consistency; use `pg_basebackup` or a supported backup method.

**10. "Streaming replication is synchronous by default."** False. The default is asynchronous.

**11. "The primary always waits for the standby before returning COMMIT."** No. Only synchronous replication with an active matching policy waits for remote acknowledgement.

**12. "Synchronous replication automatically selects any standby in the topology."** No. The primary selects directly connected standbys according to `synchronous_standby_names`; cascading downstreams are not directly selected by the primary.

**13. "Replication slots make WAL retention risk-free."** False. An inactive slot can retain WAL until the filesystem fills up.

**14. "wal_keep_size retains all needed WAL indefinitely."** No. It only sets a minimum threshold.

**15. "If a standby lags, just increase max_wal_senders."** No. The bottleneck may be network, storage, or replay.

**16. "Receive LSN always equals replay LSN."** No. The standby can receive WAL faster than it can replay it.

**17. "pg_last_xact_replay_timestamp() always measures lag accurately."** No. When the primary is idle, an old timestamp does not mean the standby is lagging.

**18. "A streaming standby automatically fails over when the primary dies."** No. Promotion/fencing/endpoint orchestration requires an operator or HA manager.

**19. "You can just turn the old standby/primary back on as primary after failover."** Unsafe. Timelines may diverge; `pg_rewind` or a new base backup is required.

**20. "pg_rewind can always be run."** No. It has preconditions for common history, clean shutdown, WAL availability, `wal_log_hints`/data checksums, and `full_page_writes`.

**21. "WAL archiving replaces replication slots in every scenario."** No. Archiving requires complete continuous segments and the consumer must have a working `restore_command`.

**22. "A hot standby has no impact on the primary."** It can impact the primary via WAL retention, slots, and `hot_standby_feedback`.

**23. "A synchronous standby equals having a backup."** No. It replicates accidental deletions and logical corruption too.

**24. "Physical replication can be used for a major upgrade."** No. Use `pg_upgrade`, dump/restore, or logical replication.

**25. "Having a row in pg_stat_replication means the standby is healthy."** Not enough. Inspect `state`, LSN gaps, `sync_state`, logs, and disk/network.

---

## 20. Practice exercises and answers

### Exercise 1 — Physical replication

**Question:** What kind of data does physical replication transmit?

**Answer:** Physical-level WAL records so the standby can replay and reproduce data files.

### Exercise 2 — Scope

**Question:** Can you physically replicate only the `sales` schema?

**Answer:** No. Physical replication applies to the entire cluster.

### Exercise 3 — Version

**Question:** Can a PostgreSQL 17 primary and a PostgreSQL 18 standby stream WAL directly?

**Answer:** No. Physical replication requires the same major version.

### Exercise 4 — Architecture

**Question:** Can you stream from a 32-bit primary to a 64-bit standby?

**Answer:** No. Hardware architecture must be compatible.

### Exercise 5 — Tablespace

**Question:** Why does a standby need matching tablespace mount paths?

**Answer:** Tablespace paths are passed as-is in physical recovery; the standby needs those paths to exist with proper permissions.

### Exercise 6 — System identifier

**Task:** Check the system identifier.

```sql
SELECT system_identifier FROM pg_control_system();
```

### Exercise 7 — wal_level

**Question:** Which values are suitable for physical streaming replication?

**Answer:** `replica` or `logical`; `minimal` is insufficient for a standby.

### Exercise 8 — Replication role

**Task:** Create a replication role.

```sql
CREATE ROLE replicator LOGIN REPLICATION PASSWORD 'replace-with-secret';
```

### Exercise 9 — pg_hba

**Task:** Allow standby `10.20.0.12` to connect over TLS.

```conf
hostssl replication replicator 10.20.0.12/32 scram-sha-256
```

### Exercise 10 — Base backup

**Task:** Write a command to create a standby from the primary and stream WAL.

```bash
pg_basebackup \
  --host=primary.example.net \
  --username=replicator \
  --pgdata=/var/lib/postgresql/18/main \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf
```

### Exercise 11 — standby.signal

**Question:** Which file tells the server to start in standby mode?

**Answer:** `standby.signal` in the data directory.

### Exercise 12 — primary_conninfo

**Question:** What is `application_name` used for?

**Answer:** Identifying the standby on the primary and matching the name in `synchronous_standby_names`.

### Exercise 13 — Receive/replay

**Question:** Receive LSN advancing while replay LSN stays flat suggests what?

**Answer:** The standby is receiving WAL, but replay is slow or blocked; inspect I/O, CPU, recovery conflicts, and logs.

### Exercise 14 — Default streaming

**Question:** Is streaming replication synchronous or asynchronous by default?

**Answer:** Asynchronous.

### Exercise 15 — Replication slot

**Task:** Create a physical slot.

```sql
SELECT * FROM pg_create_physical_replication_slot('standby_a');
```

### Exercise 16 — Inactive slot

**Question:** Why can an inactive slot fill the disk?

**Answer:** The slot retains WAL needed by the consumer even when the consumer is disconnected.

### Exercise 17 — WAL retention

**Question:** Is `wal_keep_size` an exact WAL retention guarantee for each standby?

**Answer:** No. It is a minimum threshold; slots or an archive are needed to ensure longer catch-up.

### Exercise 18 — Synchronous commit

**Question:** What configuration does `synchronous_commit=on` require in order to wait for a remote standby?

**Answer:** `synchronous_standby_names` must specify an eligible streaming standby.

### Exercise 19 — FIRST/ANY

**Task:** Wait for two out of three standbys using quorum.

```conf
synchronous_standby_names = 'ANY 2 (standby_a, standby_b, standby_c)'
```

### Exercise 20 — Monitoring

**Task:** Check sender state and `sync_state`.

```sql
SELECT application_name, state, sync_state,
       sent_lsn, write_lsn, flush_lsn, replay_lsn
FROM pg_stat_replication;
```

### Exercise 21 — Standby receiver

**Task:** Check receiver state.

```sql
SELECT status, sender_host, written_lsn, flushed_lsn
FROM pg_stat_wal_receiver;
```

### Exercise 22 — Lag

**Question:** Why can the replay timestamp look old even when the standby is caught up?

**Answer:** If the primary has no new transactions, the last commit timestamp stays old; compare LSNs and WAL activity.

### Exercise 23 — Promote

**Task:** Promote a standby in a lab.

```sql
SELECT pg_promote(wait => true);
```

### Exercise 24 — Split brain

**Question:** What must be ensured before promoting?

**Answer:** The old primary must be fenced/isolated so it cannot continue accepting writes.

### Exercise 25 — Timeline

**Question:** Why does PostgreSQL create a new timeline after promotion?

**Answer:** To mark the new WAL history branch after the divergence point.

### Exercise 26 — pg_rewind

**Question:** State two important preconditions for `pg_rewind` to run.

**Answer:** Clean target shutdown and `wal_log_hints` enabled before divergence or data checksums enabled; `full_page_writes` must be on and required WAL must be available.

### Exercise 27 — Reinitialize

**Question:** When is a new base backup needed?

**Answer:** When required WAL is missing, `pg_rewind` preconditions are unmet, target corruption exists, or cluster lineage mismatches.

### Exercise 28 — Cascading

**Question:** Can the primary directly wait on a downstream standby behind a cascading standby?

**Answer:** No. The primary only selects directly connected synchronous standbys.

### Exercise 29 — Major upgrade

**Question:** Name three ways to upgrade a major version.

**Answer:** `pg_upgrade`, dump/restore, or logical replication.

### Exercise 30 — Backup

**Question:** Does a physical standby replace independent backups?

**Answer:** No. A standby replicates logical errors and accidental deletions as well; backups and restore tests are required.

---

## 21. Deployment and operations checklist

### Compatibility

1. Confirm primary and standby share the same major version.
2. Plan minor release updates and prioritize standbys first.
3. Confirm compatible hardware architecture.
4. Verify PostgreSQL build/data-format settings.
5. Prepare identical tablespace mount paths.
6. Confirm system identifier/cluster lineage from base backup.
7. Install matching extension libraries and custom modules.

### Primary

8. Set `wal_level=replica` or `logical`.
9. Configure `max_wal_senders` and `max_replication_slots`.
10. Design `wal_keep_size`, slots, and `max_slot_wal_keep_size`.
11. Configure `archive_mode`/`archive_command` if needed.
12. Configure `listen_addresses`, firewall, and `pg_hba.conf`.
13. Create a dedicated `REPLICATION` role and protect credentials.
14. Verify TLS/authentication from the standby.

### Standby

15. Take a base backup with `pg_basebackup`.
16. Choose the appropriate WAL method and ensure sufficient sender connections.
17. Create/assign a slot for the right node if used.
18. Verify `standby.signal` and `primary_conninfo`.
19. Verify tablespace paths and filesystem permissions.
20. Start and check `pg_is_in_recovery()`.
21. Verify `pg_stat_wal_receiver` and `pg_stat_replication`.

### Monitoring/HA

22. Monitor sent/write/flush/replay LSN.
23. Monitor receive/replay lag and WAL generation rate.
24. Monitor slot retention and disk usage.
25. Monitor archive failures and recovery conflicts.
26. Alert when a standby disconnects or lag exceeds thresholds.
27. Test failover, fencing, and promotion.
28. Rewind/rebuild the old node per runbook.
29. Test restoring independent backups.
30. Record actual RPO/RTO from failover drills.

---

## 22. Summary

Physical replication in PostgreSQL uses WAL to reproduce the physical state of the entire cluster on a standby. A base backup provides a consistent starting point; streaming or an archive delivers new WAL to the standby; the recovery process replays WAL to keep the replica up to date.

Points to remember:

- Physical replication copies WAL at the physical level, does not copy SQL, and does not filter individual tables.
- A standby needs a base backup of the exact cluster/system identifier.
- Primary and standby must have the same major version, compatible hardware architecture, and compatible data/WAL formats.
- Different minor releases may work, but should be aligned with standbys updated first.
- Tablespace mount paths are passed as-is and must be prepared on the standby.
- Replication slots retain WAL, but can fill the disk; combine retention limits with archive monitoring.
- Streaming defaults to asynchronous; synchronous replication increases durability, but can block commits when no standby qualifies.
- Receive lag and replay lag are two distinct issues.
- Promotion creates a new timeline; fencing prevents split brain.
- The old primary requires `pg_rewind` or a new base backup before returning as a standby.
- A standby does not replace independent backups, WAL archiving, or restore tests.

**Self-check question:** If the primary is running PostgreSQL 18 on a 64-bit machine and the standby runs PostgreSQL 17 on a 64-bit machine, why can a streaming connection still not create a physical replica? The major version requirement matters because WAL and storage formats must be interpreted identically; compatible hardware architecture cannot compensate for a major version difference. When building a new node, take a base backup from the right primary, check tablespace paths, and verify WAL receive/replay before placing the standby into the HA topology.

### Official PostgreSQL documentation

- [Log-Shipping Standby Servers — Planning and Standby Operation](https://www.postgresql.org/docs/current/warm-standby.html).
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION).
- [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION).
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html).
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html).
- [pg_rewind](https://www.postgresql.org/docs/current/app-pgrewind.html).
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html).
- [WAL Internals](https://www.postgresql.org/docs/current/wal-internals.html).
- [Monitoring Statistics — Replication Views](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Hot Standby](https://www.postgresql.org/docs/current/hot-standby.html).
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html).

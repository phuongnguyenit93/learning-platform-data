# Creating a standby via base backup and configuring connections

PostgreSQL physical streaming replication creates a standby server by copying the physical state of a PostgreSQL cluster and then continuously receiving and replaying WAL from the primary. A standby can serve read queries when hot standby is enabled, provide redundancy, offload read workloads, and serve as the foundation for failover/disaster recovery.

Creating a standby requires three coordinated parts: **a consistent base backup**, **an authenticated and encrypted replication connection**, and **a continuous WAL stream**. Running `pg_basebackup` alone is not enough if the primary does not allow replication connections, the standby does not know the primary's address, WAL is not retained long enough, or the service cannot read credentials.

This lesson walks through the process of creating a physical standby from a running primary, configuring the role and `pg_hba.conf`, preparing WAL senders/replication slots, running `pg_basebackup`, setting up `standby.signal`/`primary_conninfo`, starting the standby, and verifying replication status. Examples focus on PostgreSQL 12 and later, where recovery configuration lives in `postgresql.conf`/`postgresql.auto.conf` and the `standby.signal` file; older versions used a different `recovery.conf` mechanism.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain physical streaming replication and the roles of primary/standby.
2. Distinguish between base backup, WAL streaming, and WAL archiving.
3. Prepare the primary for replication with the required server settings.
4. Create a replication role with least privilege.
5. Configure `pg_hba.conf`, TLS, and a password file securely.
6. Choose an appropriate WAL method when running `pg_basebackup`.
7. Create and use a physical replication slot.
8. Understand the effects of `-R`, `-X stream`, `-S`, `-C`, `-P`, and `-D`.
9. Configure the standby connection using `primary_conninfo` and `primary_slot_name`.
10. Start the standby, verify recovery mode, and check the WAL receiver.
11. Monitor replication lag and troubleshoot connection/WAL errors.
12. Understand read-only queries, hot standby conflicts, and failover boundaries.

> **Version:** Main examples use PostgreSQL 12+. Option names and statistics views may differ across major versions. Physical replication requires servers to run the same PostgreSQL major version; cross-check the exact version documentation before deploying.

## 2. How do primary and standby work?

In physical streaming replication:

- **Primary** accepts writes from clients, generates WAL records, and serves transactions.
- **WAL sender** on the primary sends WAL to standbys over the replication protocol.
- **WAL receiver** on the standby receives and writes WAL into `pg_wal`.
- **Startup/recovery process** replays WAL to advance the standby's data files toward the primary's state.
- **Hot standby** allows clients to run read-only queries while the standby continues replaying WAL.

Diagram:

```text
Application writes
       |
       v
  PostgreSQL PRIMARY
       |
       +--> WAL records --> pg_wal
       |
       +--> walsender ======================+
                                            |
                                      network/TLS
                                            |
                                            v
                                  PostgreSQL STANDBY
                                            |
                                      walreceiver
                                            |
                                         pg_wal
                                            |
                                      startup/replay
                                            |
                                      read-only queries
```

### Does the standby accept writes?

A physical standby in recovery mode is read-only. It replays changes that originated on the primary; clients cannot arbitrarily run UPDATE/INSERT on the standby like an independent primary.

### Streaming replication is not logical replication

Physical replication transmits WAL to reproduce changes at the cluster/storage level. Logical replication transmits logical changes for selected publications/tables and can apply them to a different schema/database. This lesson focuses on physical standbys.

## 3. What is a base backup?

A base backup is a consistent physical copy of a PostgreSQL cluster over a time window. It includes data files and metadata needed for the server to begin recovery. For a physical standby, the base backup is the starting point for the standby to replay WAL and catch up with the primary.

A base backup can be created using:

- `pg_basebackup`.
- Backup tools such as pgBackRest or Barman.
- Storage snapshots properly orchestrated with PostgreSQL and WAL.

### Why not copy the data directory with cp?

While the primary is running, data files can change concurrently. Copying directories arbitrarily can yield an inconsistent state across files/pages. `pg_basebackup` uses PostgreSQL's replication protocol and backup coordination to produce a consistent physical backup.

### Base backups need WAL

During backup, pages may be copied at different points in time. WAL is required to bring the copy to a consistent state. `pg_basebackup` can stream or fetch WAL depending on the chosen WAL method.

## 4. Compatibility requirements between primary and standby

Before starting:

- Same PostgreSQL major version.
- Appropriate binary/extension compatibility.
- Compatible CPU/OS architecture and data directory format.
- Tablespaces have matching paths on the standby.
- Standby has sufficient disk space for the base backup, WAL, and growth.
- Network allows the standby to connect to the primary.
- Replication privileges and credentials are ready.

### Do not initialize the standby with initdb

For a physical standby created from a base backup, the data directory must hold the cluster copy from the primary. Do not run `initdb` on the same directory and overwrite files inconsistently. Use an empty data directory, the right backup destination, and point the service to the exact path.

### Minor versions

A physical standby generally requires the same major release; minor releases within the same major version are designed to be replication-compatible. However, keep primary/standby on supported minor releases and roll out security/bug-fix updates synchronously according to plan.

## 5. Example architecture

Assume:

| Component | Example |
|---|---|
| Primary host | `db-primary.internal` |
| Primary address | `10.20.0.10` |
| Standby host | `db-standby.internal` |
| Standby address | `10.20.0.20` |
| PostgreSQL port | `5432` |
| Replication role | `replicator` |
| Application name | `standby_a` |
| Physical slot | `standby_a_slot` |
| Data directory | `/var/lib/postgresql/17/main` |

These hostnames/IPs are documentation examples; substitute your system's real private/network addresses. Never expose the replication port to the public Internet without proper protection architecture.

## 6. Checking primary status before configuration

Connect to the primary with an appropriate administrative role:

```sql
SELECT version();
SHOW data_directory;
SHOW port;
SHOW listen_addresses;
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
SHOW hot_standby;
```

Verify the server is acting as primary:

```sql
SELECT pg_is_in_recovery();
```

A result of `false` means the instance is not currently in recovery mode. If `true`, the server is in recovery/standby and cannot be used as the writable primary in this example.

### Confirm the data directory

Record the data directory path and any tablespace locations. On the standby, `pg_basebackup` needs an empty destination and tablespaces must have valid target paths.

## 7. Configuring wal_level

On the primary:

```sql
SHOW wal_level;
```

Physical streaming replication requires `wal_level` to be at least `replica`.

In `postgresql.conf` or parameter group:

```ini
wal_level = replica
```

`wal_level=logical` also supports physical replication, but writes additional WAL information for logical decoding. Choose the lowest level that satisfies the full replication/CDC architecture.

### Restart requirement

`wal_level` is a setting that requires a server restart to take effect. After changing it, confirm with `SHOW wal_level;` before running the base backup.

## 8. Configuring WAL senders

The primary needs enough WAL sender processes for:

- Physical standbys.
- Logical replication connections.
- Running `pg_basebackup` sessions.
- Other backup/replication tools using the replication protocol.

Example:

```ini
max_wal_senders = 10
```

This is an illustrative value. Count concurrent connections and leave headroom for backups/reconnects/failover. If WAL sender slots run out, standbys or base backups may fail to connect.

`max_wal_senders` requires a restart. Verify the active value:

```sql
SHOW max_wal_senders;
```

## 9. Configuring replication slots capacity

If using physical replication slots:

```ini
max_replication_slots = 10
```

This setting determines the maximum number of replication slots. Size it sufficiently for physical/logical slots and backup workflows that require slots.

```sql
SHOW max_replication_slots;

SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn
FROM pg_catalog.pg_replication_slots;
```

`max_replication_slots` requires a restart when changed. Do not create many unowned slots; an inactive slot can retain WAL and cause `pg_wal` to grow.

## 10. Configuring wal_keep_size and archive

`wal_keep_size` instructs the primary to keep a minimum amount of WAL so a standby has time to reconnect in certain situations:

```ini
wal_keep_size = 2GB
```

This is an example, not a time-based retention guarantee. The higher the WAL rate, the shorter the time window corresponding to the same size.

If a standby needs to catch up after a longer outage, use a physical replication slot or an appropriate WAL archive. An archive can supply WAL when the standby needs a segment no longer present in local `pg_wal`.

### Distinction

- `wal_keep_size`: retains a minimum amount of WAL by size.
- Physical replication slot: retains needed WAL according to `restart_lsn`.
- WAL archive: stores WAL segments at an archive destination for recovery/standby retrieval.

These mechanisms complement each other in recovery design; they should not be viewed as complete replacements for one another.

## 11. Configuring listen_addresses and firewall

The primary must listen on an interface the standby can connect to:

```ini
listen_addresses = '10.20.0.10'
port = 5432
```

You can use a hostname/interface or `*` per network policy; avoid opening all interfaces unnecessarily.

Firewalls/security groups should allow only the standby host/network to connect on TCP 5432 to the primary. Also ensure routes, DNS, NAT, and network ACLs allow return traffic.

### Verify from the standby

On the standby host, check DNS and TCP reachability using appropriate OS tools. A successful TCP connection does not prove `pg_hba`/authentication/TLS are right; the `pg_basebackup` step will validate the full PostgreSQL connection path.

## 12. Creating the replication role

On the primary:

```sql
CREATE ROLE replicator
WITH LOGIN REPLICATION;
```

Set the password via an appropriate secret management process. For example, setting the password interactively via `\password` in `psql`:

```sql
\password replicator
```

Do not put real passwords into source code, tickets, command history, or documentation. A physical replication role needs `LOGIN` and `REPLICATION`; it does not need `SUPERUSER` just for streaming replication/`pg_basebackup` to work.

### Role privileges

A `REPLICATION` role is allowed to connect using the replication protocol and create slots within configuration/privilege limits. This is a sensitive privilege; restrict it to standby/backup hosts and audit its usage.

## 13. Configuring pg_hba.conf

Add a rule on the primary for the standby address:

```text
# TYPE     DATABASE      USER         ADDRESS          METHOD
hostssl    replication   replicator   10.20.0.20/32    scram-sha-256
```

The `replication` database token in `pg_hba.conf` is reserved for replication connections. Use `hostssl` to accept only TLS connections.

### Rule order

PostgreSQL uses the first matching rule. If a broader rule appears above, the narrower rule may never be reached. Review the file in order and avoid accidentally opening replication access to a wide CIDR.

### Reload configuration

After editing:

```sql
SELECT pg_reload_conf();
```

Or reload via `pg_ctl reload`/service manager per operational practice. `pg_hba.conf` changes normally require only a reload, not a restart. Check logs if a rule has a syntax error.

## 14. Verifying pg_hba.conf

You can inspect the parsed configuration:

```sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_catalog.pg_hba_file_rules
ORDER BY line_number;
```

If the `error` column is non-NULL, resolve the syntax/config issue before running the base backup.

### Connection rejected

Primary logs usually indicate no matching `pg_hba.conf` entry or authentication failed. Do not react by switching to `trust` in production. Check the actual source IP, the `replication` database token, username, TLS mode, and rule order.

## 15. TLS for replication connections

If using `hostssl`, the primary must have SSL enabled and a valid certificate/key:

```ini
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
```

The standby should verify the certificate chain and hostname, for example in the connection string:

```text
host=db-primary.internal
port=5432
user=replicator
application_name=standby_a
sslmode=verify-full
sslrootcert=/etc/postgresql/certs/ca.crt
```

### Certificate requirements

- The primary certificate must be valid for the hostname used.
- The standby trust store must contain the appropriate CA.
- Private keys must be protected by filesystem permissions.
- Certificate expiry/rotation must be monitored.
- Do not use `sslmode=disable` if policy requires TLS.

## 16. Password file and credentials

On Linux/Unix, libpq can use `.pgpass` or a file specified by `passfile`. A line has the format:

```text
hostname:port:database:username:password
```

For replication connections, the database field uses `replication`.

Illustrative example:

```text
db-primary.internal:5432:replication:replicator:REPLACE_WITH_SECRET
```

Place the file in the service account's home or a dedicated path; restrict read/write permissions, usually `0600` on Unix. If permissions are too broad, libpq may refuse to use the file.

### Escaping

In a passfile, `:` and `\` inside fields must be escaped according to libpq rules. Do not put secrets containing special characters without proper escaping.

### Windows

On Windows, use a passfile with ACLs restricted to the service account and necessary administrators. `chmod` does not apply on Windows; use NTFS permissions.

## 17. Whether to use a replication slot

A physical replication slot helps the primary retain WAL needed by the standby even if the standby temporarily disconnects.

### Advantages

- Reduces the risk of the standby losing WAL segments because the primary recycled them too early.
- The standby can reconnect after an outage and resume if the slot still holds enough WAL.
- Removes reliance on estimating retention solely via `wal_keep_size`.

### Risks

- An inactive slot can retain WAL indefinitely if uncapped.
- The `pg_wal` disk can fill up if a standby dies or lags for a long time.
- Slots require monitoring and a clear owner.

On supported versions, `max_slot_wal_keep_size` can cap WAL retained by a slot. If the limit is exceeded, the slot may be invalidated and the standby must be reinitialized/reseeded.

## 18. Creating a physical replication slot

Can be created beforehand on the primary:

```sql
SELECT *
FROM pg_catalog.pg_create_physical_replication_slot(
    'standby_a_slot'
);
```

Or let `pg_basebackup` create the slot using `-C -S` as shown in the example below.

Verify:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    wal_status,
    safe_wal_size
FROM pg_catalog.pg_replication_slots
WHERE slot_name = 'standby_a_slot';
```

The `wal_status`/`safe_wal_size` columns exist in newer major versions; on older servers, query only supported columns.

### Slot already exists

Do not recreate a slot with the same name. Check which standby owns the slot, whether it is active, and whether it must be kept. Avoid dropping a slot currently used by a standby/consumer.

## 19. Preparing the standby host

On the standby:

1. Install the same PostgreSQL major version as the primary.
2. Install required extensions/libraries if physical files depend on them.
3. Provision a filesystem/data volume with sufficient capacity.
4. Create the PostgreSQL service account.
5. Determine the exact data directory.
6. Open network access to the primary port.
7. Prepare the CA certificate and passfile.
8. Stop the PostgreSQL service if the package automatically created an empty cluster.
9. Move/remove the empty cluster via a controlled procedure; the base backup destination must be empty.

### Check the destination

`pg_basebackup -D` requires the target directory not to contain unrelated data. Never write a base backup into a data directory currently used by a running PostgreSQL instance.

### Ownership

The data directory and staging paths must be owned by the appropriate service account. Wrong owner/permissions can prevent PostgreSQL from starting or expose data files.

## 20. Basic pg_basebackup syntax

Example:

```sh
pg_basebackup \
  -h db-primary.internal \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -Fp \
  -X stream \
  -P \
  -R
```

Explanation:

| Option | Meaning |
|---|---|
| `-h` | Hostname/address of the primary |
| `-p` | PostgreSQL port |
| `-U` | Replication role |
| `-D` | Destination directory |
| `-Fp` | Plain directory format |
| `-X stream` | Stream WAL while the base backup runs |
| `-P` | Show progress |
| `-R` | Create `standby.signal` and write recovery connection settings |

Run from the standby/backup host using a `pg_basebackup` binary compatible with the cluster. You can add `-v` for verbose output.

## 21. -X stream, -X fetch, and -X none

`-X stream` opens a separate replication connection to stream WAL concurrently with the base backup. This is the common choice when creating a standby because required WAL is collected during the backup.

`-X fetch` retrieves the required WAL segments at the end of the backup. This method requires the primary to keep enough WAL for the entire backup duration; if a needed segment is recycled before fetching, the backup can fail.

`-X none` does not fetch WAL this way; the caller/tool must ensure required WAL is supplied by another mechanism.

### Choosing a method

- Use `stream` when you want a single base backup command that collects continuous WAL automatically.
- Use `fetch` when retention and workload guarantee required WAL remains until the end of the backup.
- Use `none` only when a well-designed backup/WAL orchestration handles WAL separately.

`-X stream` typically uses two replication connections while running: one for the base backup and one for WAL streaming. Ensure `max_wal_senders` has enough capacity.

## 22. -R creates standby configuration

On PostgreSQL 12+, `-R`/`--write-recovery-conf`:

- Creates `standby.signal` in the data directory.
- Writes connection settings to `postgresql.auto.conf`.
- If a slot is specified with `-S`, writes the matching `primary_slot_name`.

When the server starts and sees `standby.signal`, PostgreSQL enters standby mode and connects to the primary per `primary_conninfo`/recovery settings.

### Why use -R?

It reduces manual configuration errors and ensures the data directory after the base backup has the signal to start in standby mode. However, you must still verify the connection string, password file, TLS, and slot.

### PostgreSQL 11 and earlier

Older versions used `recovery.conf` with `standby_mode` and recovery parameters. Do not follow `standby.signal` instructions for older versions; consult the corresponding version documentation.

## 23. Creating a slot directly inside pg_basebackup

If you want both the base backup and standby to use a slot:

```sh
pg_basebackup \
  -h db-primary.internal \
  -p 5432 \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -Fp \
  -X stream \
  -P \
  -R \
  -C \
  -S standby_a_slot
```

- `-C` requests creating the replication slot before starting the backup.
- `-S` specifies the slot name.
- `-R` writes `primary_slot_name` into the recovery config so the standby keeps using that slot after starting.

### Notes

If the slot already exists, `-C` will report an error. When the slot was already created beforehand, pass `-S standby_a_slot` without `-C`.

If the command fails partway through, check whether the slot was created without an active consumer. An orphan slot can retain WAL; clean it up per owner/incident procedure.

## 24. Tablespaces and destination paths

A physical base backup can include tablespaces at paths outside the data directory. If the standby uses different paths, use `--tablespace-mapping`/`-T`:

```sh
pg_basebackup \
  -h db-primary.internal \
  -U replicator \
  -D /var/lib/postgresql/17/main \
  -X stream \
  -R \
  -T /primary/fast_ts=/standby/fast_ts
```

The mapping must match the exact source tablespace path and a prepared destination path. Multiple tablespaces may require multiple mappings.

### Do not let tablespaces overwrite data

Verify destination paths are empty and mounted on the right volumes. Incorrect mapping can cause the backup to fail or write onto an unintended filesystem.

## 25. Choosing format and compression

`pg_basebackup` supports plain format (`-Fp`) and tar format (`-Ft`) in corresponding versions. Plain format creates the directory structure directly, which is usually convenient for starting a standby right after backup. Tar format requires extraction/restoration before the server can use it.

Some versions support output compression with `-Z` and specific compression methods/levels. Compression reduces network/storage bytes, but uses CPU and must match how it will be restored.

### Choose by environment

- Use plain format for a direct standby data directory destination.
- Use tar format when a pipeline stores artifacts and extracts them during restore.
- Measure CPU, network throughput, backup duration, and restore duration.
- Do not assume compression options are identical across major versions.

## 26. Running pg_basebackup safely

Before running:

- Confirm primary role and settings.
- Confirm `pg_hba` rules are reloaded.
- Confirm TCP/TLS and authentication.
- Confirm slot name/ownership.
- Confirm destination is empty and has enough disk space.
- Confirm `max_wal_senders` has enough connections.
- Confirm password file/secret path.
- Confirm tablespace mappings.

While running:

- Watch progress.
- Watch primary WAL generation and sender activity.
- Watch disk/network throughput.
- Avoid deleting/moving the destination.
- Do not kill the process merely because progress pauses temporarily in a phase.

After running:

- Confirm a successful exit code.
- Confirm the data directory has `standby.signal`.
- Check `postgresql.auto.conf` for `primary_conninfo`/slot.
- Run manifest/backup validation if supported by the tool/version.
- Ensure credentials are readable by the service account.

## 27. Checking recovery configuration after -R

On the standby host, before starting PostgreSQL:

```sh
cat /var/lib/postgresql/17/main/postgresql.auto.conf
ls -l /var/lib/postgresql/17/main/standby.signal
```

These are illustrative Linux commands; use equivalent tools on other OSes. `standby.signal` is typically an empty file whose presence instructs PostgreSQL to start in standby mode.

In `postgresql.auto.conf`, check:

- Does `primary_conninfo` have the right host/port/user/`application_name`?
- Are `sslmode`/`sslrootcert` aligned with TLS policy?
- Does `primary_slot_name` have the right slot name if using a slot?
- No plaintext password was written into the file.

### Avoid configuring the same setting in multiple places

`postgresql.auto.conf` is used by `ALTER SYSTEM`/`pg_basebackup -R` to store settings. If `postgresql.conf` also defines `primary_conninfo`, understand precedence: `postgresql.auto.conf` is read after `postgresql.conf` and can override it. Keep one clear source of configuration.

## 28. Configuring primary_conninfo

If you need to configure manually or complete the connection string generated by `-R`, for example:

```ini
primary_conninfo = 'host=db-primary.internal port=5432 user=replicator application_name=standby_a sslmode=verify-full sslrootcert=/etc/postgresql/certs/ca.crt passfile=/var/lib/postgresql/.pgpass'
```

The connection string uses libpq parameters. `application_name` helps identify the standby in `pg_stat_replication`.

### Do not embed passwords

Do not put passwords directly in `primary_conninfo` if avoidable. Use a passfile protected by filesystem ACLs/permissions and the service account.

### primary_conninfo is not an app connection string

This is an internal connection from the standby to the primary to receive WAL. It needs the replication user, host/port, TLS/authentication, and an appropriate `application_name`.

## 29. Configuring primary_slot_name

If the standby uses a physical replication slot:

```ini
primary_slot_name = 'standby_a_slot'
```

The name must match an existing slot on the primary. If the slot does not exist or has been invalidated, the WAL receiver may fail to connect/continue.

When using `pg_basebackup` with `-R -S standby_a_slot`, this setting is usually written automatically. Check the config file and primary `pg_replication_slots` after the standby starts.

### Do not share one slot across multiple standbys

Each standby should have its own slot so the primary tracks WAL retention independently. Sharing a slot obscures consumer progress/ownership and is unsuitable for multiple independent physical standbys.

## 30. Standby signal and hot_standby

PostgreSQL 12+ uses the `standby.signal` file to indicate the server must continue in standby mode:

```text
PGDATA/
  postgresql.conf
  postgresql.auto.conf
  standby.signal
  base/
  global/
  pg_wal/
  ...
```

Setting:

```sql
SHOW hot_standby;
```

`hot_standby=on` allows read-only queries during recovery once the server reaches a consistent state. This is a standby-side setting; changing it requires a restart depending on the setting's context.

### If standby.signal is missing

A data directory containing a base backup without `standby.signal` may not keep running as a standby as intended. On PostgreSQL 12+, verify this file and recovery configuration before starting.

## 31. Starting the standby

Ensure the service is stopped and the data directory is the newly created base backup. Start using the service manager or `pg_ctl` matching your installation method.

Example:

```sh
pg_ctl -D /var/lib/postgresql/17/main -l /var/log/postgresql/standby.log start
```

If using systemd/package-managed clusters, use the corresponding service unit/cluster manager instead of running `pg_ctl` to spawn a second instance on the same data directory.

### Watch startup logs

Look for messages such as:

- entering standby mode/recovery.
- started streaming WAL from primary.
- consistent recovery state reached.
- database system is ready to accept read-only connections.

Wording varies by version. If the server fails to start, read the first `ERROR`/`FATAL` in the logs; never delete files in `pg_wal` to try to restart.

## 32. Confirming the standby is in recovery mode

Connect directly to the standby:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    current_setting('server_version') AS version,
    inet_server_addr() AS server_address;
```

Expected output:

- `is_standby = true`.
- Server version matches primary compatibility.
- Connected to the right standby host/port.

### Verify read-only behavior

Try a `SELECT` on a needed table. An `INSERT`/`UPDATE` on a hot standby will be rejected because the standby is in recovery/read-only mode.

## 33. Checking the WAL receiver on the standby

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
FROM pg_catalog.pg_stat_wal_receiver;
```

The view has one row when the WAL receiver is running; no row can mean not connected yet, reconnecting, server not in standby, or receiver stopped.

### Interpretation

- `status` is normally `streaming` while receiving WAL.
- `written_lsn` and `flushed_lsn` show received/written positions.
- `latest_end_lsn` is the latest reported WAL end position.
- `last_msg_receipt_time` helps check the most recent message receipt.
- `slot_name` shows the slot in use if any.

Columns can vary across versions; use `SELECT *` or `information_schema` to inspect the schema on your actual major version.

## 34. Checking the WAL sender on the primary

On the primary:

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
    sync_state,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_catalog.pg_stat_replication;
```

When the standby connects successfully, a row normally appears with `application_name` `standby_a` and `client_addr` as the standby host.

### States

- `startup`/`catchup`/`streaming` may appear depending on replication state/version.
- `streaming` indicates the WAL sender is continuously sending WAL.
- `sync_state` reflects synchronous replication status if configured; async standbys normally have `async`.

If no row appears, check standby logs, `pg_hba`, authentication, network, and slots.

## 35. Measuring receive lag and replay lag

On the standby:

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_last_wal_receive_lsn(),
            pg_last_wal_replay_lsn()
        )::bigint
    ) AS receive_replay_bytes;
```

The receive-to-replay distance indicates WAL received but not yet replayed, measured in LSN address distance.

On the primary, you can compare the current WAL LSN with the standby's `replay_lsn` from `pg_stat_replication`:

```sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            replay_lsn
        )::bigint
    ) AS primary_to_replay_bytes
FROM pg_catalog.pg_stat_replication;
```

### Timestamp lag caveat

`pg_last_xact_replay_timestamp()` gives the timestamp of the most recently replayed transaction. If the primary has no writes, the timestamp can look old even when the standby is completely caught up. Use LSN distance and message timestamps with workload context; do not alert solely on timestamp when the database is idle.

## 36. Checking active slot and WAL retention

On the primary:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
WHERE slot_name = 'standby_a_slot';
```

For a physical slot, `confirmed_flush_lsn` may be NULL/not meaningful as for a logical slot. Monitor `restart_lsn` and `active` state.

### Slot active yet standby lagging?

`active` only tells you a consumer is using the slot. It does not prove the standby has replayed up to the current LSN. Compare sent/write/flush/replay positions and standby receiver/replay state.

## 37. Standby read-only queries and hot standby conflicts

When `hot_standby` is enabled, the standby can serve `SELECT` queries. However, WAL replay can conflict with queries reading data that the primary has modified/vacuumed.

Conflicts can involve:

- `AccessExclusiveLock` locks from the primary.
- Cleanup records from `VACUUM` on the primary.
- Snapshot too old on the standby.
- Buffer pins or tablespace/database removal.

Check:

```sql
SELECT *
FROM pg_catalog.pg_stat_database_conflicts
WHERE datname = current_database();
```

### max_standby_streaming_delay

This setting limits how long the standby delays WAL replay to wait for conflicting queries. Increasing the delay can reduce query cancellations, but increases replay lag and WAL retention pressure.

### hot_standby_feedback

Enabling feedback helps the primary retain tuple versions to reduce cleanup conflicts on the standby, but can increase dead tuples/bloat on the primary. Enable only when you understand the trade-off and have monitoring.

## 38. Synchronous and asynchronous standby

Physical streaming replication defaults to asynchronous: the primary does not wait for standby replay to confirm commits.

Synchronous replication requires additional configuration on the primary, for example:

```ini
synchronous_standby_names = 'FIRST 1 (standby_a)'
```

`application_name` in `primary_conninfo` must match the configured name. Commit behavior also depends on `synchronous_commit` and `sync_state`.

### Trade-off

- Async: the primary can ACK commits before the standby receives/flushes WAL; there is a risk of losing some transactions if the primary is lost abruptly before the standby receives them.
- Sync: can reduce data loss risk according to the selected acknowledgement level, but commit latency depends on standby/network.

Do not enable synchronous replication merely by setting `synchronous_standby_names` without defining RPO policy, timeouts, quorum, and behavior when the standby is down.

## 39. Streaming replication and WAL archive coordination

The standby can use `restore_command` to fetch WAL from an archive when a segment is unavailable from the streaming source/primary. A standby configuration can combine:

- `primary_conninfo` to stream WAL.
- `primary_slot_name` to retain WAL on the primary.
- `restore_command` to fetch archived WAL.

### Order and purpose

The recovery process can fetch WAL from archive and streaming depending on mechanism/version. Specific configuration must ensure the archive path is right and the WAL timeline matches. Never point `restore_command` at a repository without proper permissions or segment verification.

### When is an archive useful?

- Standby disconnected longer than local WAL retention.
- Disaster recovery from a backup repository is needed.
- Separating WAL retention from primary local storage.

An archive does not replace monitoring replication slots or the backup chain.

## 40. Verifying backups with pg_verifybackup

PostgreSQL versions that support `pg_verifybackup` can verify the backup manifest and file checksums:

```sh
pg_verifybackup /var/lib/postgresql/17/main
```

This is an offline check on the backup directory; it does not replace starting the standby and verifying streaming. Capabilities/options depend on version and backup format.

### Limitations

- Does not prove the network connection still works.
- Does not prove continuous WAL archiving/streaming after the backup point.
- Does not replace a restore drill.
- Does not replace business-level data validation.

## 41. Multiple standbys

A single primary can serve multiple physical standbys. Each standby should have:

- Its own `application_name`.
- Its own replication slot if slots are used.
- A clear replication identity/connection policy.
- Network path and capacity.
- Individual monitoring for receive/replay lag.

### Capacity planning

Total up WAL sender connections, network egress, slot disk retention, and write load from archiving/backups. One severely lagging standby can retain more WAL than all remaining standbys.

### Cascading replication

A standby can serve as upstream for another standby if properly configured. This reduces connections/egress from the primary, but adds a failure/lag hop; monitor the chain and ensure sufficient WAL on the upstream standby.

## 42. Restart and reconnect behavior

When a standby restarts:

1. Reads `standby.signal`.
2. Loads `primary_conninfo`/`primary_slot_name`.
3. Initializes recovery.
4. Connects to the primary or fetches WAL from the archive.
5. Replays WAL to the latest available position.
6. Resumes streaming.

If the primary has already recycled needed WAL and no slot/archive holds that segment, the standby may be unable to catch up. In that case, you must rebuild the standby via a new base backup or supported reseed procedure.

### Do not delete pg_wal on the standby

Never manually delete files in `pg_wal` to "reset replication." Doing so can prevent recovery from continuing. Use standard stop/reseed procedures.

## 43. Failover and promotion

Creating a standby does not by itself create a complete HA system. Promotion is the operation of turning a standby into a new primary.

In a controlled failover procedure, you can use:

```sql
SELECT pg_promote();
```

Or:

```sh
pg_ctl -D /path/to/standby promote
```

### Preventing split brain

Before promoting, you must be certain the old primary has been fenced/guaranteed not to accept writes anymore. If two nodes are writable simultaneously, two diverging data histories can form and cause severe data loss.

### After promotion

- The new standby becomes primary and creates a new timeline.
- Update routing/service discovery.
- Reconfigure remaining standbys to follow the new primary.
- Evaluate whether the old primary can rewind/rejoin or needs a reseed.
- Update backup/archive configuration.

Failover orchestration typically requires Patroni/repmgr/managed-service control plane or a dedicated runbook; `pg_basebackup` only creates the initial replica.

## 44. Rebuilding a standby when WAL is lost

If logs report the standby needs a WAL segment that has already been removed/recycled:

1. Identify the missing LSN/WAL segment.
2. Check whether the archive has that segment.
3. Inspect the physical slot and `restart_lsn`.
4. Determine whether the standby can retrieve WAL from the archive.
5. If recovery cannot continue, plan a reseed.
6. Stop the standby per service procedure.
7. Take a new base backup into an empty destination.
8. Verify slot/credentials/connection settings.
9. Start and verify streaming/replay.

Never try to create fake WAL files or substitute a segment with another file of the same name.

## 45. Troubleshooting: connection refused

Possible causes:

- PostgreSQL primary is not running.
- `listen_addresses` does not include the needed interface.
- Wrong port.
- Firewall/security group blocking traffic.
- DNS pointing to the wrong IP.
- Primary listening only on localhost.

Check by layer:

1. DNS resolution.
2. TCP reachability.
3. PostgreSQL listening socket.
4. Network/firewall rules.
5. Server logs.

Connection refused differs from authentication failure; resolve network issues before changing credentials.

## 46. Troubleshooting: no pg_hba.conf entry

The error message usually prints the client address, user, and database/replication request. Check:

- Actual source IP of the standby.
- Whether the rule uses the `replication` database token.
- Exact username.
- Whether the rule is `hostssl` when TLS is required.
- Rule ordering so an earlier rule does not shadow it.
- Whether `pg_hba.conf` was reloaded.

Never add a `0.0.0.0/0 trust` rule as a quick fix. Restrict to the exact standby IP/CIDR and authentication method.

## 47. Troubleshooting: password authentication failed

Check:

- Password is set for the right role.
- User has `LOGIN` and `REPLICATION`.
- Passfile matches host/port/database/user.
- Passfile escaping is correct.
- Service account can read the passfile.
- No stale password in process/service environment.
- `pg_hba` authentication method matches the credential.

If changing the password, update the passfile/secret store on the standby and reload/restart the connection per procedure; do not print secrets to logs.

## 48. Troubleshooting: requested WAL segment has already been removed

The standby needs a WAL segment the primary no longer retains. Check:

- Was a slot used and does it still exist?
- Was the slot invalidated due to `max_slot_wal_keep_size`?
- How long was the standby disconnected?
- Is `wal_keep_size` sized for the WAL generation rate?
- Does the archive have the required WAL segment?
- Is `restore_command` working?

If the archive lacks the segment, reseed the standby from a new base backup. Increasing `wal_keep_size` after a segment is already gone cannot recreate that segment.

## 49. Troubleshooting: too many WAL senders

If the primary runs out of WAL sender slots:

- Count standbys, logical subscribers, and backup jobs.
- Check `pg_stat_replication` and `pg_stat_activity`.
- Identify hung/orphan connections.
- Plan an increase to `max_wal_senders` if capacity allows.
- Restart the primary if the setting requires it.

Do not terminate a WAL sender serving a healthy standby without understanding the impact. Ensure `max_wal_senders` includes headroom for `pg_basebackup -X stream` because it can use more than one replication connection.

## 50. Troubleshooting: inactive replication slot holding disk space

Inspect:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_size_pretty(
        pg_wal_lsn_diff(
            pg_current_wal_lsn(),
            restart_lsn
        )::bigint
    ) AS retained_distance
FROM pg_catalog.pg_replication_slots
WHERE restart_lsn IS NOT NULL;
```

Identify the slot owner before dropping. If the standby is lost, decide whether to reattach or reseed. An unowned slot can be cleaned up after approval; a still-needed slot may require retaining WAL.

## 51. Troubleshooting: standby starts as primary

If the standby accepts writes or `pg_is_in_recovery()` returns false:

- Confirm the service points to the right `PGDATA`.
- Verify `standby.signal` exists in the actual data directory.
- Inspect startup logs.
- Check that a different `initdb` cluster was not started by mistake.
- Check service unit/environment overrides for `PGDATA`.

Do not create `standby.signal` in a different data directory and assume the service is using it.

## 52. Troubleshooting: base backup destination not empty

`pg_basebackup` requires an empty destination for plain format. If the directory holds a default cluster:

1. Stop the right PostgreSQL service.
2. Confirm the path the service is using.
3. Back up/move old data if needed.
4. Confirm the new destination is empty.
5. Check mount/owner/permissions.
6. Re-run the base backup.

Never delete a data directory before confirming the right host/path and taking a copy if old data still matters.

## 53. Troubleshooting: tablespace mapping failure

If the backup reports a tablespace error:

- Retrieve source paths from `pg_tablespace`/`pg_tablespace_location`.
- Confirm destination mounts exist.
- Use an exact mapping matching the source path.
- Ensure destination has enough disk and permissions.
- Check symlinks/ownership.

Do not map multiple tablespaces to the same destination if the tool/cluster requires separate paths.

## 54. Securing replication connections

Checklist:

- Dedicated replication role; do not use `postgres` superuser.
- Password managed via secret manager/passfile.
- TLS with certificate validation.
- `pg_hba` restricted to standby IP/CIDR.
- Firewall opens only the required port.
- Dedicated service account and tight file permissions.
- Clear `application_name` for auditing/monitoring.
- Alerts on slot ownership/retention.
- Audit role changes, `pg_hba` edits, and replication connections.

Physical replication transmits cluster-wide data; replication privileges are sensitive and must be protected accordingly.

## 55. Standby and backups

A standby does not replace backups. Logical mistakes, accidental `DELETE`, replayed corruption, or ransomware can propagate to the standby via WAL.

Still required:

- Periodic base backups.
- WAL archiving for PITR.
- Offsite/immutable copies.
- Restore tests.
- Encryption/access control.

Standbys provide availability/failover; backups provide recovery to a point before an error or rebuilding a cluster. The two mechanisms complement each other.

## 56. End-to-end standby creation procedure

### On the primary

1. Check version, role, and data directory.
2. Set `wal_level=replica`.
3. Set `max_wal_senders` and `max_replication_slots` with sufficient capacity.
4. Configure `wal_keep_size`/archive/slot policy.
5. Configure `listen_addresses` and firewall.
6. Create the replication role.
7. Add the `hostssl replication` rule to `pg_hba.conf`.
8. Reload `pg_hba` and verify rules parse cleanly.
9. Prepare the slot or decide to use `-C -S`.

### On the standby

10. Install the same major version and prepare an empty data directory.
11. Configure TLS trust and passfile.
12. Run `pg_basebackup` with `-X stream`, `-R`, progress, and appropriate slot options.
13. Verify `standby.signal` and `postgresql.auto.conf`.
14. Verify `primary_conninfo`/`primary_slot_name` and ensure no plaintext password.
15. Start PostgreSQL.
16. Confirm `pg_is_in_recovery() = true`.
17. Check `pg_stat_wal_receiver` on the standby.
18. Check `pg_stat_replication` and active slot on the primary.
19. Measure receive/replay lag.
20. Test read-only queries and hot standby behavior.

### Post-deployment

21. Set up monitoring/alerts.
22. Verify archive/slot retention and disk headroom.
23. Test restarting the standby and confirm reconnection.
24. Document failover/fencing/reseed procedures.
25. Perform an independent restore test.

## 57. Practice exercises

### Exercise 1 — Primary and standby

Explain the roles of primary, walsender, walreceiver, and startup/recovery process in physical streaming replication.

### Exercise 2 — Base backup

Why can't you simply use `cp` to copy a running data directory? Conceptually, how does `pg_basebackup` ensure consistency?

### Exercise 3 — Version compatibility

A primary runs PostgreSQL 16 and a standby runs PostgreSQL 17. Why should you not use a physical base backup to create such a standby?

### Exercise 4 — wal_level

Explain why physical replication requires at least `wal_level=replica`. Does this setting require a restart?

### Exercise 5 — WAL senders

A primary has 3 physical standbys, 2 logical replication clients, and one `pg_basebackup` running with `-X stream`. Estimate the required `max_wal_senders` capacity and headroom to include.

### Exercise 6 — Replication slots

Explain `max_replication_slots` and the risk of creating an unowned slot.

### Exercise 7 — wal_keep_size

A primary generates 100 MB WAL/minute. Roughly how much time does `wal_keep_size=1GB` correspond to? Why is it not a retention time guarantee?

### Exercise 8 — Replication role

Create a `LOGIN REPLICATION` role named `replicator`. Why should `SUPERUSER` not be granted for physical streaming replication?

### Exercise 9 — pg_hba.conf

Write a `hostssl replication` rule for standby IP `10.20.0.20/32`, user `replicator`, and SCRAM. Explain the `replication` database token.

### Exercise 10 — Rule order

A broad `host` rule appears before a specific `hostssl` rule. Explain first-match behavior and how to verify via `pg_hba_file_rules`.

### Exercise 11 — TLS

Design `primary_conninfo` using `sslmode=verify-full` and a CA certificate. Why is `sslmode=require` not equivalent to hostname verification?

### Exercise 12 — Password file

Explain the `.pgpass` format and required permissions on Unix. What happens if the file does not match `database=replication`?

### Exercise 13 — pg_basebackup options

Explain `-h`, `-p`, `-U`, `-D`, `-Fp`, `-X stream`, `-P`, and `-R` in a standby creation command.

### Exercise 14 — WAL methods

Compare `-X stream`, `-X fetch`, and `-X none`. Under what scenario can `fetch` fail due to WAL recycling?

### Exercise 15 — -R

On PostgreSQL 12+, which files/settings does `-R` create? What is the role of `standby.signal`?

### Exercise 16 — Replication slot options

Explain combining `-C` and `-S` in `pg_basebackup`. If the slot already exists, how should the command be run?

### Exercise 17 — primary_conninfo

Write a connection string containing `host`, `port`, `user`, `application_name`, `sslmode`, `sslrootcert`, and `passfile`. Why not embed a password?

### Exercise 18 — primary_slot_name

Why should each standby have its own slot? How does a nonexistent slot name affect the WAL receiver?

### Exercise 19 — Tablespaces

The primary has a tablespace at `/primary/fast_ts`, whereas the standby mounts it at `/standby/fast_ts`. Write an appropriate `-T` mapping and list what must be verified.

### Exercise 20 — Destination directory

`pg_basebackup` reports `destination directory exists and is not empty`. Describe a safe procedure to inspect/clear the destination.

### Exercise 21 — Starting the standby

After the base backup completes, list the checks to perform before starting the service.

### Exercise 22 — Recovery mode

Query `pg_is_in_recovery()`. What do `true`/`false` mean on primary/standby?

### Exercise 23 — WAL receiver

Query `pg_stat_wal_receiver`. What do `status`, `flushed_lsn`, `latest_end_lsn`, `sender_host`, and `slot_name` indicate?

### Exercise 24 — WAL sender

Query `pg_stat_replication` on the primary. How do you recognize a streaming standby and identify `application_name`/`client_addr`?

### Exercise 25 — Replication lag

Use `pg_last_wal_receive_lsn`, `pg_last_wal_replay_lsn`, and `pg_wal_lsn_diff` to compute bytes waiting for replay.

### Exercise 26 — Timestamp lag

Why can `pg_last_xact_replay_timestamp` appear old when the primary is idle even if the standby has no lag? Suggest supplementary metrics.

### Exercise 27 — Slot retention

A slot is active yet retained WAL distance grows rapidly. Which metrics should you inspect to see whether the standby is receiving/replaying fast enough?

### Exercise 28 — Hot standby

Explain `hot_standby` and why a physical standby serves only read-only queries during recovery.

### Exercise 29 — Query conflicts

A long `SELECT` on the standby is canceled due to `VACUUM` cleanup from the primary. Explain `max_standby_streaming_delay` and the `hot_standby_feedback` trade-off.

### Exercise 30 — Synchronous replication

Explain `synchronous_standby_names` and `application_name` matching. Compare durability/latency trade-offs with asynchronous replication.

### Exercise 31 — WAL archive fallback

Design `restore_command` so the standby fetches WAL from the archive when streaming lacks a required segment. Why must the timeline and WAL chain be guaranteed intact?

### Exercise 32 — pg_verifybackup

What does `pg_verifybackup` prove and what does it not prove? Why are starting the standby and restore tests still necessary?

### Exercise 33 — Multiple standbys

A primary has 5 standbys. Design `application_name`, slots, sender capacity, and per-standby monitoring.

### Exercise 34 — Cascading replication

Explain how a cascading standby offloads the primary and how it introduces an additional failure/lag hop.

### Exercise 35 — Reconnect

A standby restarts after 10 minutes. Describe how it reads `standby.signal`, loads `primary_conninfo`, reconnects, and replays WAL.

### Exercise 36 — Missing WAL

A standby reports `requested WAL segment has already been removed`. Investigate the slot, `wal_keep_size`, archive, and decide on reseeding when needed.

### Exercise 37 — Connection refused

List the diagnostic layers from DNS, TCP, `listen_addresses`, and firewall to PostgreSQL logs.

### Exercise 38 — Authentication failure

A standby hits `password authentication failed`. Check role, passfile match, escaping, service permissions, and `pg_hba` method.

### Exercise 39 — Failover

Explain why creating a standby does not automatically create HA. Before `pg_promote`, how must the old primary be fenced to avoid split brain?

### Exercise 40 — End-to-end deployment design

A PostgreSQL primary has 2 TB of data, 3,000 writes/second, and peak WAL generation of 80 MB/s. Two physical standbys are needed:

- Standby A in the same region to serve read-only queries.
- Standby B in a DR region.
- Target RPO of 30 seconds.
- One standby runs long reporting queries.
- The DR network occasionally experiences 15-minute outages.
- Uncontrolled `pg_wal` volume growth must be avoided.

Design:

1. `wal_level`, `max_wal_senders`, and `max_replication_slots`.
2. Replication roles, `pg_hba` rules, TLS, and passfiles.
3. `pg_basebackup` command/options for each standby.
4. Slot strategy and `max_slot_wal_keep_size`/`wal_keep_size`.
5. WAL archive fallback for the DR standby.
6. `primary_conninfo`/`application_name` and `standby.signal`.
7. Monitoring for receive/replay lag, slot retention, and disk headroom.
8. Hot standby conflict policy for reporting queries.
9. Failover/fencing/rejoin procedure.
10. Rebuild/reseed runbook when a standby loses WAL.

## Conclusion

**Creating a physical standby begins with a consistent base backup and ends when the WAL receiver/recovery process connects, replays, and is stably monitored.** The primary needs an appropriate `wal_level`, sufficient WAL senders/slots, listen addresses, and `pg_hba` rules restricted to the exact standby. The replication role only needs `LOGIN`/`REPLICATION`; connections should use TLS with server identity verification, and credentials should be kept in a passfile/secret manager.

**`pg_basebackup -X stream -R` is the standard workflow for PostgreSQL 12+.** `-X stream` fetches WAL during backup, `-R` creates `standby.signal` and connection settings, and `-S`/`-C` enables the standby to use a physical replication slot. Confirm the destination is empty, tablespace mappings are accurate, the slot has an owner, and the service uses the right `PGDATA` before starting.

After startup, verify `pg_is_in_recovery()` on the standby, `pg_stat_wal_receiver` on the standby, and `pg_stat_replication` on the primary. Monitor receive/replay LSN, lag, slot retention, WAL archiving, and disk headroom. Standbys support read-only workloads and failover, but do not replace backups/PITR; query conflicts, WAL loss, credential expiry, and network outages all require runbooks.

Finally, **physical replication is a state-transfer mechanism, not a complete HA procedure**. Promotion requires fencing to prevent split brain, standbys must be reconfigured after failover, and the old primary must be rewound/reseeded according to timeline history. Sound deployment combines base backups, WAL continuity, security, monitoring, independent backups, and tested restore/failover drills.

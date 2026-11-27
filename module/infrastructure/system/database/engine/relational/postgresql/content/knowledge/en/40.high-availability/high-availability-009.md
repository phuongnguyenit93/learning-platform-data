# pg_rewind, Cluster Rejoin, and Usage Conditions in PostgreSQL

When a PostgreSQL primary fails over, the old primary may continue accepting writes for a period if it has not been fenced or does not yet know that a new primary has been promoted. The two servers can then produce two different WAL branches. Once a new primary is chosen, you cannot simply turn the old primary back on and let it continue writing as before: the two data histories have diverged.

`pg_rewind` brings the old server's data directory back to the same data state as the new server by locating the divergence point in the timeline, finding modified blocks, and copying the needed contents from source to target. Afterward, the target is started in standby mode to replay WAL from the new primary and rejoin the replication topology.

This is a key tool for failover/switchover workflows, but it only works when conditions regarding cluster identity, timeline, WAL history, data checksums or hint-bit logging, and shutdown state are satisfied. If prerequisites are missing, the safe approach is to rebuild the standby from a fresh base backup.

~~~text
                 Before incident
              Primary A (TLI 1)
                     |
              WAL timeline 1
                     |
           +---------+---------+
           |                   |
           v                   v
      Standby B            Standby C

                 Primary A fails
                     |
                     v
             Promote Standby B
               Primary B (TLI 2)
                     |
              WAL timeline 2
                     |
        +------------+-------------+
        |                          |
        v                          v
   New writes                 Old Primary A
                                diverged
                                   |
                                   v
                             pg_rewind
                                   |
                                   v
                         A becomes standby
                                   |
                                   v
                          Replay WAL from B
                                   |
                                   v
                          Rejoin replication
~~~

This lesson belongs to the **High Availability** chapter of the *Database Engine Relational PostgreSQL* module, focusing on `pg_rewind`, usage conditions, cluster rejoin after failover, and alternatives when rewind is not feasible.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why the old primary's timeline diverges after failover.
2. Distinguish between failover, switchover, promotion, and rejoin.
3. Describe how `pg_rewind` finds the common ancestor and divergence point.
4. Distinguish between source and target in the `pg_rewind` command.
5. List mandatory requirements for system identifier and major version.
6. Explain the data checksums or `wal_log_hints` requirement.
7. Understand the role of `full_page_writes` in identifying modified blocks.
8. Explain why the target must be cleanly shut down before rewinding.
9. Identify the target WAL required starting from the divergence point.
10. Use `--restore-target-wal` when WAL must be fetched from an archive.
11. Use `--dry-run` and `--progress` to check/observe the operation.
12. Use `--write-recovery-conf` to prepare the target as a standby on supported versions.
13. Configure `primary_conninfo`, `standby.signal`, and replication slots.
14. Verify tablespaces, configuration, and filesystem permissions after rewind.
15. Distinguish `pg_rewind` from `pg_basebackup` and physical restore.
16. Recognize scenarios where `pg_rewind` cannot be used.
17. Design fencing to prevent split-brain.
18. Monitor the target catching up to the source.
19. Handle rewind failures or missing target WAL.
20. Build a rejoin runbook and fallback to rebuilding the standby.

## 2. Why Is Cluster Rejoin Needed?

In physical streaming replication, standbys receive WAL from the primary and replay it to maintain a replica. When the primary fails, a standby can be promoted to become the new primary.

### 2.1. Timeline Before Failover

Initially, primary A writes WAL on timeline 1. Standbys receive the same WAL history.

### 2.2. Promotion Creates a New Timeline

When standby B is promoted, PostgreSQL starts a new timeline, such as timeline 2. Timeline 2 forks from timeline 1 and continues writing its own WAL.

### 2.3. The Old Primary May Have Written Additional Data

If primary A is not fenced in time, it can continue writing on timeline 1 past the fork point. Those transactions do not automatically appear on timeline 2.

### 2.4. Two Branches Do Not Merge Automatically

PostgreSQL physical replication does not merge two WAL branches like a version control tool. Once B is chosen as the new primary, A's history after the divergence point is not brought back simply by reconnecting replication.

### 2.5. Role of pg_rewind

`pg_rewind` brings A back to a state compatible with B's branch at the common point, after which A can replay new WAL from B. Changes existing only on A's branch after the fork are discarded from the target.

### 2.6. Not a Business Data Merge

If some writes existing only on the old primary must be preserved, they must be extracted and reconciled at the business level before or after the rejoin workflow. `pg_rewind` does not merge row changes from two branches.

## 3. Terminology: source and target

In `pg_rewind`, these two terms are critical:

| Term | Meaning in the operation |
| --- | --- |
| Source | Cluster whose data history is chosen as canonical, typically the new primary |
| Target | Cluster to be rewound to match the source, typically the old primary |
| Common ancestor | Shared WAL history point before the two branches diverged |
| Divergence point | Timeline fork location where histories began differing |
| Rejoin | Bringing the target back as a standby of the source |
| Rebuild | Creating a fresh target from a base backup of the source |

### 3.1. Source Is the Retained Branch

After failover, the source is typically the newly promoted primary currently accepting writes.

### 3.2. Target Is the Replaced Branch

The target is typically the old primary or an old standby that followed a timeline no longer chosen.

### 3.3. Never Swap the Two Roles

Picking the wrong source can revert the server holding canonical data back to an old branch. Before running, confirm topology, timelines, and the failover decision using independent information.

### 3.4. Target Is Overwritten

`pg_rewind` modifies the target's data directory. Treat this operation as destructive to the target's current state. If you need to preserve target-specific data, take a snapshot/backup before running.

## 4. How Does pg_rewind Work?

`pg_rewind` does not copy the entire data directory like a standard base backup. It identifies the parts of the target that need to change to match the source.

### 4.1. Reading Control Data

The tool inspects control information on source and target, including system identifier, checkpoint, and timeline history.

### 4.2. Finding the Divergence Point

Based on timeline history, `pg_rewind` identifies the common point and the location where the two branches began diverging.

### 4.3. Analyzing Target WAL

WAL after the divergence point helps identify which data blocks the target modified. This information builds the list of blocks that must be copied back.

### 4.4. Reading Data From Source

Needed blocks are fetched from the source. Files that cannot be handled via block-level copying may be copied per the tool's file-level rules.

### 4.5. Synchronizing Target

Required files and blocks on the target are replaced to reflect source state. Old WAL and obsolete files are handled according to the rewind workflow.

### 4.6. Recovery After Rewind

The target still needs to replay WAL to reach a consistent state and catch up to the source. When configured as a standby, it continues receiving WAL via streaming or archive.

### 4.7. Why Can It Be Faster Than a Base Backup?

If the amount of data changed since the divergence point is small relative to the whole cluster, `pg_rewind` only needs to copy the changed portions and related files. For large clusters, this can substantially cut rejoin time.

### 4.8. Not Always Faster

If the divergence lasted a long time, many blocks changed, required WAL is gone, or data layout changed heavily, `pg_rewind` can take a long time or be infeasible. Rebuilding from a base backup is sometimes simpler and more reliable.

## 5. Mandatory Prerequisites for Using pg_rewind

Before running, verify all of the following conditions.

### 5.1. Same PostgreSQL Cluster Identity

Source and target must share the same system identifier, meaning they originated from the same PostgreSQL cluster. Two independently `initdb`'d clusters cannot be joined with `pg_rewind` merely because they share a schema.

You can check the system identifier with:

~~~bash
pg_controldata /path/to/PGDATA
~~~

Look for the `Database system identifier` field.

### 5.2. Shared Timeline History

Source and target must have a common ancestor in timeline history and an identifiable divergence point. If the needed history is missing or the two clusters do not share lineage, rewind cannot determine the exact changed region.

### 5.3. Same Major Version

Use the `pg_rewind` binary matching the data directory's major version. Source and target must be on the same PostgreSQL major version. `pg_rewind` is not a major-version upgrade tool.

### 5.4. Required Block Change Tracking

One of the following two conditions must have been enabled before the WAL to be analyzed was generated:

- Data checksums enabled for the cluster.
- `wal_log_hints = on`.

### 5.5. full_page_writes Must Be Enabled

`full_page_writes` must be enabled so WAL contains the full-page images required by the rewind mechanism. This is usually the default, yet must be verified on the cluster and must not have been turned off during the relevant window.

### 5.6. Target Cleanly Shut Down

The target server must be cleanly shut down before running `pg_rewind`. If the target crashed, start it, let crash recovery finish, and then shut it down cleanly before rewinding.

### 5.7. Sufficient WAL From Target

Target WAL needed from the divergence point must still exist in target `pg_wal` or be retrievable from an archive. If required WAL is missing, `pg_rewind` cannot fully determine which blocks changed.

### 5.8. Source Reachable

If using `--source-server`, the source must be running and accepting appropriate connections. The connection role needs permissions to read the metadata and data required by `pg_rewind` per version.

### 5.9. Correct Target Path

Target `PGDATA` must be the stopped data directory of the server being rewound. Verify the path and cluster identity before executing.

## 6. Data Checksums and wal_log_hints

`pg_rewind` needs to identify which pages/blocks changed since the divergence point.

### 6.1. Data Checksums

Data checksums record checksums for database pages. When enabled, this mechanism provides the information `pg_rewind` needs to detect modified blocks.

### 6.2. Enabling Checksums at initdb

A common way is initializing the cluster with checksums:

~~~bash
initdb --data-checksums -D /var/lib/postgresql/17/data
~~~

Option names and management may vary across major versions. Check `initdb --help` for your PostgreSQL release.

### 6.3. Checking Checksums

Status can be inspected via control data:

~~~bash
pg_controldata /var/lib/postgresql/17/data
~~~

Look for the `Data page checksum version` field.

### 6.4. wal_log_hints

If not using data checksums, you can enable:

~~~conf
wal_log_hints = on
~~~

This parameter requires a restart and must be enabled prior to the divergence point so WAL records the necessary hint-bit/page changes.

### 6.5. Do Not Enable After the Incident and Rewind Immediately

Turning on `wal_log_hints` after two branches have already diverged does not retroactively add information to old WAL. The condition must exist before the WAL records `pg_rewind` must analyze are created.

### 6.6. full_page_writes

~~~conf
full_page_writes = on
~~~

Never disable this parameter to save WAL while still expecting `pg_rewind` to work properly.

### 6.7. Check Both Servers

Because source and target share cluster lineage, inspect actual configuration and parameter change history. Do not look only at the current `postgresql.conf` and ignore when the parameter was enabled.

## 7. Required WAL From the Target

`pg_rewind` uses the target's WAL to locate blocks changed after the divergence point.

### 7.1. WAL Range

If the two branches diverged at LSN X and the target kept writing up to LSN Y, `pg_rewind` needs the relevant WAL from just after X through Y.

### 7.2. WAL in pg_wal

If the segments still remain in the target's `pg_wal`, the tool can read them directly.

### 7.3. WAL Archive

If segments have already been archived and recycled out of `pg_wal`, they can be retrieved from the archive if properly configured.

### 7.4. --restore-target-wal

On supported versions, this option tells `pg_rewind` to use the target's `restore_command` to fetch missing WAL from the archive:

~~~bash
pg_rewind --restore-target-wal --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal dbname=postgres user=rewind_user"
~~~

The `restore_command` configuration must be able to access the archive and work under the OS permissions of the process running the tool.

### 7.5. Archive Continuity

The archive must contain the target's exact timeline/segments. A WAL file with the same name from another cluster cannot substitute.

### 7.6. Retention Policy

Retain WAL long enough for nodes to be rewound after failover. Retention must account for incident detection time, failover decision time, and rejoin preparation time.

### 7.7. When WAL Is Missing

If a required segment is absent from both `pg_wal` and the archive, halt the rewind plan and evaluate rebuilding from a fresh base backup. Never fabricate segments or skip gaps.

## 8. Preparation Before Running

`pg_rewind` makes deep modifications to the data directory. A preflight checklist prevents running on the wrong target.

### 8.1. Fence the Old Primary

Ensure the old primary can no longer accept writes. You can stop the service, block networking, revoke endpoints, or use infrastructure fencing.

### 8.2. Confirm the New Primary

Verify the server chosen as source is actually an active primary:

~~~sql
SELECT pg_is_in_recovery();
~~~

On the source primary, the expected result is `false`.

### 8.3. Stop the Target

Stop the target via `pg_ctl` or the service manager:

~~~bash
pg_ctl -D /var/lib/postgresql/17/old-primary stop -m fast
~~~

Wait for the command to finish and verify the process has stopped. Never run `pg_rewind` while the target is running.

### 8.4. If the Target Crashed

If the target crashed, start it against the right data directory so PostgreSQL completes crash recovery, then shut it down cleanly. Check logs to confirm recovery completed.

### 8.5. Back Up Target Before Rewind

Take an appropriate filesystem snapshot or backup if you need to preserve target state for investigation or extracting divergent data. Do not rely on automatic rollback from `pg_rewind`.

### 8.6. Check Disk Capacity

Ensure enough disk space for copy/temporary operations, WAL replay, and tablespaces. Also check space on source and archive.

### 8.7. Check Permissions

The OS user running `pg_rewind` must be able to read source/target files and write to the target directory. If using `--source-server`, the database role needs appropriate privileges.

### 8.8. Check Versions

~~~bash
pg_rewind --version
pg_ctl --version
~~~

Use binaries matching the major version of source/target.

### 8.9. Check Tablespaces

Verify every tablespace location exists and is accessible. Symlinks inside `pg_tblspc` must point to valid paths on the target host.

### 8.10. Plan Configuration Files

Record target-specific `postgresql.conf`, `pg_hba.conf`, SSL files, archive settings, port, `listen_addresses`, logging, memory settings, and replication connections. Some files inside `PGDATA` may be overwritten during copying; inspect and restore node-specific configs after rewind.

## 9. Checking Topology and Timelines

Before running, understand the WAL branches.

### 9.1. Check Recovery State

On the source:

~~~sql
SELECT pg_is_in_recovery();
~~~

The server chosen as the new primary normally returns `false`.

### 9.2. Check System Identifier

~~~bash
pg_controldata /var/lib/postgresql/17/new-primary
pg_controldata /var/lib/postgresql/17/old-primary
~~~

Compare `Database system identifier`.

### 9.3. Check Timeline

`pg_controldata` provides checkpoint timeline and control information. Read timeline history files in archive/`pg_wal` to locate the fork.

### 9.4. History Files

History filenames consist of 8 hexadecimal digits and the `.history` suffix, e.g., `00000002.history`. The file describes the parent timeline and switch point.

### 9.5. Do Not Rely Solely on Timeline ID

Two clusters can share the same timeline number without sharing a system identifier. Combine system identifier, timeline history, and backup lineage.

### 9.6. Select the Canonical Branch

Document the new primary, current timeline, old target, divergence point, and transactions on the old branch that will be discarded.

## 10. Invoking pg_rewind

There are two main ways to supply the source: connecting to a running server or reading a cleanly shut-down source data directory.

### 10.1. Running Source Server

Example:

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user sslmode=verify-full" --progress
~~~

Source is the new primary; target is the stopped data directory of the old primary.

### 10.2. Source Data Directory

If the source is cleanly shut down and on the same host/filesystem:

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/17/old-primary --source-pgdata=/var/lib/postgresql/17/new-primary --progress
~~~

This method is unsuitable while the source is serving writes; in typical failover environments, `--source-server` is the convenient choice.

### 10.3. Use Only One Source Mode

Provide either `--source-server` or `--source-pgdata` per version syntax. Never specify both.

### 10.4. --dry-run

Before the real operation, you can run:

~~~bash
pg_rewind --dry-run --progress --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal dbname=postgres user=rewind_user"
~~~

Dry run checks and previews the plan as supported by the version without modifying data. It does not replace preflight checks or backing up the target.

### 10.5. --progress

Displays copy progress, useful for large clusters. Do not treat progress as proof that the target has caught up on WAL.

### 10.6. --debug

Debug output can be used when investigating errors. Protect logs because command-line/connection metadata can contain sensitive information.

### 10.7. --no-sync

Some versions provide an option to skip fsync/sync after copying for speed. Never use it in routine production procedures because durability guarantees are lost on host crash/power loss.

### 10.8. --sync-method

Supported versions can choose how files are synced after copying. Use the default or a method tested on the target filesystem/OS.

## 11. Example pg_rewind Runbook

Assume:
- PostgreSQL major version 17.
- New primary is host `new-primary`.
- Old primary has `PGDATA` at `/var/lib/postgresql/17/old-primary`.
- Both nodes share the same system identifier.
- Target is cleanly shut down.
- Target's WAL archive is complete.

### Step 1. Confirm Source

On the source:

~~~sql
SELECT pg_is_in_recovery();
~~~

The result must be `false`.

### Step 2. Confirm Target Is Stopped

~~~bash
pg_ctl -D /var/lib/postgresql/17/old-primary status
~~~

No postmaster process may be using this `PGDATA`.

### Step 3. Check Prerequisites

Check checksums or `wal_log_hints`, `full_page_writes`, timeline ancestry, and WAL availability.

### Step 4. Dry Run

~~~bash
pg_rewind --dry-run --progress --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user sslmode=verify-full"
~~~

### Step 5. Execute Rewind

~~~bash
pg_rewind --progress --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user sslmode=verify-full"
~~~

If the target needs WAL from archive, add `--restore-target-wal` per version and configure `restore_command`.

### Step 6. Configure Standby

After rewind, configure `primary_conninfo` and `standby.signal`, or use `--write-recovery-conf` if supported by your version and the source connection string is appropriate.

### Step 7. Check Configuration

Verify port, HBA, SSL, archive, tablespaces, memory, and paths match the target host. Restore node-specific config files if they were overwritten.

### Step 8. Start Target

~~~bash
pg_ctl -D /var/lib/postgresql/17/old-primary start
~~~

### Step 9. Confirm Recovery

~~~sql
SELECT pg_is_in_recovery();
~~~

The target must return `true` while operating as a standby.

### Step 10. Confirm WAL Receiver

~~~sql
SELECT status, sender_host, sender_port, latest_end_lsn, latest_end_time FROM pg_stat_wal_receiver;
~~~

### Step 11. Confirm Source Sees Target

On the new primary:

~~~sql
SELECT application_name, client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn FROM pg_stat_replication;
~~~

### Step 12. Monitor Catch-Up

Track receive/replay LSN, lag, slot retention, and logs until the standby reaches normal health.

## 12. --write-recovery-conf and Standby Configuration

On supported versions, `--write-recovery-conf` (short `-R`) helps prepare the target to resume in standby mode.

~~~bash
pg_rewind --target-pgdata=/var/lib/postgresql/17/old-primary --source-server="host=new-primary.example.internal port=5432 dbname=postgres user=rewind_user" --write-recovery-conf
~~~

### 12.1. Signal File

For PostgreSQL 12 and newer, standby mode is requested via the `standby.signal` file inside `PGDATA`.

### 12.2. Connection Settings

The `-R` option writes necessary connection settings into auto-configuration per the version's mechanism. Inspect `postgresql.auto.conf` after running.

### 12.3. primary_conninfo

If configuring manually, for example:

~~~conf
primary_conninfo = 'host=new-primary.example.internal port=5432 user=replicator application_name=old_primary_rejoined sslmode=verify-full'
~~~

Use a passfile/secret manager to supply passwords; never store plaintext secrets in version-controlled files.

### 12.4. Replication Slot

If the standby uses a physical replication slot, configure `primary_slot_name` and create the matching slot on the new primary. The slot must exist and be active for the right node.

### 12.5. restore_command

If the standby needs archive access to catch up or support recovery, maintain an appropriate `restore_command`. Never leave an old recovery command pointing to an archive from a mismatched cluster.

### 12.6. PostgreSQL 11 and Earlier

Older versions use `recovery.conf` for standby settings. How recovery configuration files are generated and `pg_rewind` options vary by major version; consult `pg_rewind --help` and the documentation for your exact version.

### 12.7. Do Not Assume -R Completes All Configuration

Verify `primary_conninfo`, slot, `restore_command`, SSL, authentication, `application_name`, and target-specific settings after the option runs.

## 13. Configuring Replication on the New Primary

The target can only rejoin successfully if the new primary allows it to connect and streams WAL.

### 13.1. wal_level and Senders

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
~~~

Actual values depend on replica count, backup clients, and other consumers.

### 13.2. Replication Role

~~~sql
CREATE ROLE replicator WITH LOGIN REPLICATION;
~~~

Set credentials according to your secret management policy.

### 13.3. pg_hba.conf

~~~conf
hostssl replication replicator 10.20.0.0/24 scram-sha-256
~~~

Allow only valid node addresses and enforce TLS where appropriate.

### 13.4. Create a Physical Slot

If the design uses slots:

~~~sql
SELECT pg_create_physical_replication_slot('old_primary_rejoined');
~~~

Create the slot on the new primary before the standby connects with the matching `primary_slot_name`.

### 13.5. Slots Are Not Automatically Mandatory

Not every topology requires slots. Slots protect WAL from being recycled before a consumer receives it, yet a long-lagging consumer can retain WAL and fill disk. Monitor slot retention.

### 13.6. Verify Replication Connection

On the new primary, confirm the target's row appears in `pg_stat_replication` with a valid state.

## 14. Tablespaces, Configuration, and External Files

`pg_rewind` operates on the data directory, yet a PostgreSQL installation may depend on external paths.

### 14.1. Tablespace Symlinks

Inspect `pg_tblspc` and all target paths. Tablespace paths on the source may differ from desired paths on the target host.

### 14.2. Filesystem Ownership

Ensure owner/group and permissions of the data directory, WAL directory, tablespaces, and archive paths belong to the OS account running PostgreSQL.

### 14.3. Configuration Files

Files inside `PGDATA` may be overwritten when `pg_rewind` copies files from the source. After rewind, compare and restore configs specific to the rejoined node.

### 14.4. Config Outside PGDATA

If `postgresql.conf` or `pg_hba.conf` reside outside `PGDATA`, they may not be touched alongside data files. Verify all paths referenced by the configuration.

### 14.5. SSL and Secrets

Restore certificates/keys, password files, cloud credentials, and secret mounts. Verify private key file permissions.

### 14.6. Archive Command

Ensure `archive_command`/`restore_command` fit the standby role and new topology. Avoid letting the target archive into a namespace that conflicts with the new primary.

### 14.7. Ports and Service Discovery

The rejoined node may require specific ports, DNS, service names, or firewall rules. Never place the target back into the application's write endpoint.

## 15. pg_rewind vs. pg_basebackup: How Do They Differ?

| Criterion | pg_rewind | pg_basebackup |
| --- | --- | --- |
| Purpose | Bring a diverged cluster onto the source branch | Create a new physical backup |
| Data copied | Blocks/files needed to synchronize | Entire base backup |
| Common lineage required | Yes | Target lineage not required because a new data directory is created |
| Checksums/`wal_log_hints` required | Conditionally yes | Not a `pg_rewind` prerequisite |
| Target shutdown required | Yes, clean shutdown | Not applicable to a running target; writes backup to a new destination |
| Target WAL after fork | Needed to locate changed blocks | Not needed to create a new base backup |
| Transfer volume | Typically smaller if changes are few | Typically larger |
| When suitable | Rejoin an old node of the same cluster after failover | Rebuild a standby or take a base backup |

### 15.1. Choose pg_rewind

Use when the target shares cluster lineage, meets rewind prerequisites and WAL availability, and you want to reduce data transfer volume.

### 15.2. Choose pg_basebackup

Use when the target fails rewind prerequisites, WAL is missing, lineage is unclear, or you want a clean standby.

### 15.3. Never Use pg_rewind to Upgrade

To upgrade major versions, use `pg_upgrade` or an appropriate logical migration. `pg_rewind` does not convert data file formats.

### 15.4. Never Use pg_rewind to Merge

If both branches contain distinct writes that must be kept, extract and reconcile data before rewinding or from a snapshot backup.

## 16. When Can pg_rewind Not Be Used?

### 16.1. Two Clusters With Different System Identifiers

If source and target were `initdb`'d independently, they share no cluster identity. Rebuild target from a base backup of source.

### 16.2. No Common Timeline Ancestry

If timeline history cannot trace back to a shared ancestor, `pg_rewind` cannot determine the divergence point.

### 16.3. Neither Checksums Nor wal_log_hints Enabled

If both were off during the interval needing analysis, `pg_rewind` lacks the information needed to detect block changes.

### 16.4. full_page_writes Disabled

If `full_page_writes` was not active during the required period, rewind is unsafe/unsupported.

### 16.5. Target Still Running

Shut down the target cleanly before running. Never use `pg_rewind` to alter a data directory held open by a postmaster.

### 16.6. Target Crashed Without Recovery

Start the target and let crash recovery finish, then shut down cleanly.

### 16.7. Target WAL Lost

If required WAL is missing from both `pg_wal` and archive, rebuild with a base backup.

### 16.8. Major Version Mismatch

Use matching major versions and binaries. Use an upgrade tool for major-version transitions.

### 16.9. Source Unreachable

If the source server is unreachable or source data directory is not in a suitable state, fix connection/access or use a base backup.

### 16.10. Data Corruption or Storage Failure

If target/source shows signs of corruption, never treat `pg_rewind` as a corruption-repair tool. Restore from a verified backup and investigate storage.

## 17. Timeline History and Deep Divergence

~~~text
TLI 1:  A0 ---- A1 ---- A2 ---- A3
                         |
                         +---- fork
                                |
TLI 2:                          B0 ---- B1 ---- B2
                                              |
                                              +---- fork
                                                     |
TLI 3:                                               C0 ---- C1
~~~

### 17.1. Common Ancestor

If target is on TLI 2 and source is on TLI 3, the two branches may share a common ancestor at the TLI 2 fork point.

### 17.2. History Chain

PostgreSQL uses `.history` files to describe timeline relationships. Retain these files in the archive alongside WAL segments.

### 17.3. Multiple Promotions

If a node is rewound late and the topology has promoted again since then, verify the latest source timeline and history chain before acting.

### 17.4. Target on a Further Branch

If the target followed a separate branch that is not an ancestor of the chosen source, examine lineage carefully. Never guess fork points from WAL filenames.

### 17.5. Record Timeline Evidence

Log system identifier, timeline IDs, history files, divergence LSN, and the chosen canonical primary in the incident record.

## 18. What Happens to Divergent Data on the Old Primary?

`pg_rewind` aligns target to source. Transactions committed only on the target branch after the divergence point will not exist on the source branch.

### 18.1. No Automatic Merge

`pg_rewind` does not compare business rows and merge them. It operates at the level of physical files/blocks and WAL history.

### 18.2. Back Up Before Rewind

If there is any chance data on the old branch must be kept, snapshot/back up the target before the operation.

### 18.3. Extracting Divergent Data

You can restore the target snapshot into an isolated environment, read the needed data, and export via `pg_dump`/SQL. Then reconcile with the source.

### 18.4. Handling Duplicate IDs

Both branches may allocate identical sequence values after a fork. During business reconciliation, handle primary keys, unique constraints, foreign keys, and external references carefully.

### 18.5. Auditing and Business Decisions

Document potentially lost transactions, who authorized the canonical branch, and how data unique to the old branch was handled.

## 19. Protecting Against Split-Brain

Safe rejoin begins by guaranteeing only one primary has write authority.

### 19.1. Fencing

Fencing stops the old primary from continuing to write by powering down the machine, stopping the service, revoking storage/network access, or using cluster manager fencing.

### 19.2. Do Not Only Change DNS

DNS caches, connection pools, and client retries may continue hitting the old primary. Fencing must act at the server/infrastructure layer, not just endpoint updates.

### 19.3. Confirm a Single Writer

After failover, verify topology and connection routing so only the new primary receives writes.

### 19.4. Rewind Only After Fencing

The target must be stopped and serving no traffic. Never rewind a server that applications might still be writing to concurrently.

### 19.5. Rejoin Is Not Promotion

After rewind, the target must start in standby mode. Starting as an independent primary creates a new timeline and causes another divergence.

## 20. Verification After Rejoin

Once the target starts, verify both recovery state and replication progress.

### 20.1. Target in Recovery

~~~sql
SELECT pg_is_in_recovery();
~~~

Expected result is `true`.

### 20.2. WAL Receiver

~~~sql
SELECT status, sender_host, sender_port, receive_start_lsn, written_lsn, flushed_lsn, latest_end_lsn, latest_end_time FROM pg_stat_wal_receiver;
~~~

### 20.3. Replay Progress

~~~sql
SELECT pg_last_wal_receive_lsn() AS receive_lsn, pg_last_wal_replay_lsn() AS replay_lsn, pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

### 20.4. Primary Replication View

~~~sql
SELECT application_name, client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn, sync_state FROM pg_stat_replication;
~~~

### 20.5. Replication Slot

~~~sql
SELECT slot_name, slot_type, active, restart_lsn, wal_status FROM pg_replication_slots;
~~~

### 20.6. Logs

Look for messages about streaming connection, WAL replay, timeline switch, missing WAL, authentication errors, and recovery completion.

### 20.7. Catch-Up

Compare receive/replay LSN and lag over an interval. As the source keeps writing, the target must advance steadily rather than lagging without bound.

### 20.8. Do Not Open Read Traffic Until Ready

If the target serves as a reporting standby, confirm it reaches consistency, read permissions, and expected query behavior before adding it to the read pool.

## 21. Monitoring WAL Lag and Slot Pressure

### 21.1. Receive/Replay Gap

~~~sql
SELECT pg_wal_lsn_diff(pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()) AS bytes_received_not_replayed;
~~~

### 21.2. Primary Sent/Replay

~~~sql
SELECT application_name, pg_wal_lsn_diff(sent_lsn, replay_lsn) AS sent_not_replayed_bytes FROM pg_stat_replication;
~~~

### 21.3. Never Convert Bytes to Seconds Arbitrarily

WAL generation rate changes with workload. Measure WAL rate over a time window if you need to estimate lag duration.

### 21.4. Slot Retained WAL

Monitor `restart_lsn`, `wal_status`, and `pg_wal` disk usage on the primary. A target slow to catch up can cause a slot to retain WAL for a long time.

### 21.5. Disk Alerts

Alert on free space and `pg_wal` growth rate. Do not wait until the filesystem fills up to address a slot.

### 21.6. Archive Fallback

If streaming is interrupted while the WAL archive remains complete, the standby can use `restore_command` to catch up as configured. Verify archive path and retention.

## 22. Configuring the Target After Rewind

### 22.1. standby.signal

On PostgreSQL 12 and newer, the target needs `standby.signal` to start in standby mode.

### 22.2. primary_conninfo

Ensure the connection string points to the new primary. Use a distinct `application_name` for identification in `pg_stat_replication`.

### 22.3. primary_slot_name

If using a physical replication slot, specify the slot name created on the new primary.

### 22.4. restore_command

If using the WAL archive as a fallback source, configure `restore_command` for the right archive namespace and timeline.

### 22.5. archive_mode

Check `archive_mode`/archiving policy on the standby per topology. If multiple nodes archive to the same namespace, design to avoid overwrites/name collisions and follow PostgreSQL guidance.

### 22.6. recovery_target Settings

Remove old PITR recovery target settings if no longer appropriate. A normally rejoined standby must keep following the primary rather than stopping at an old historical target.

### 22.7. Node-Specific Configuration

Restore port, `listen_addresses`, memory, logging, SSL, HBA, and service identity for the new role.

## 23. Rejoin After Planned Switchover

Switchover differs from failover because shutdown and promotion are normally coordinated in a controlled manner.

### 23.1. Quiesce Writes

Pause or coordinate writes so the old primary flushes data and the standby catches up.

### 23.2. Planned Promote

Promote the chosen standby after verifying replay has reached the required position.

### 23.3. Old Primary Shutdown

Shut down the old primary cleanly before preparing it as a standby.

### 23.4. Divergence May Be Negligible

If the old primary shut down before the new branch accepted any writes, the two nodes may not have diverged in a way requiring rewind. It can be reused via the appropriate procedure or rebuilt for simplicity.

### 23.5. Do Not Assume pg_rewind Is Always Needed

Check actual timeline state. If the old node is aligned and can safely continue as standby, use the appropriate runbook; if it diverged, rewind or rebuild.

## 24. Rejoin After Unplanned Failover

### 24.1. Fence Old Primary

Immediately on failover, isolate the old primary to prevent parallel writes.

### 24.2. Promote New Node

Confirm the chosen standby has suitable replay progress and promote per failover procedure.

### 24.3. Evaluate Old Primary

When the old primary becomes accessible again, do not let applications connect to write. Check whether it crashed or kept running, along with its timeline and system identifier.

### 24.4. Clean Shutdown

If the target is still running, stop it per procedure. If it crashed, let crash recovery finish and then shut down cleanly.

### 24.5. Choose Rewind or Rebuild

Evaluate checksums/`wal_log_hints`, `full_page_writes`, WAL range, and lineage. If prerequisites are missing, use a fresh base backup.

### 24.6. Rejoin and Monitor

Once the target follows the new primary, monitor the WAL receiver, replay lag, slots, and logs before marking complete.

## 25. Handling pg_rewind Failures

### 25.1. Missing WAL

A missing WAL error indicates a required segment is absent from `pg_wal` and archive. Check `restore_command`, timeline, and archive retention.

### 25.2. Checksums/Hints Not Enabled

If block-tracking conditions are unmet, do not try to force ahead by enabling the setting after the incident. Rebuild the target from a base backup.

### 25.3. Timeline Mismatch

Compare history files and system identifiers. If the source is not the chosen branch or lineage is not shared, re-verify the topology.

### 25.4. Target Not Shut Down

Stop the postmaster and confirm a clean shutdown. Never re-run while the target is open.

### 25.5. Filesystem Permissions

Check owner, group, permissions, tablespace mounts, and disk space.

### 25.6. Source Connection Failure

Check `pg_hba`, TLS, role privileges, networking, and source server status.

### 25.7. Tablespace Path Errors

Verify symlinks and directories. Never delete tablespaces or symlinks without checking metadata.

### 25.8. Target Partially Modified

If a previous run failed after starting to modify the target, treat the target as untrustworthy. Restore from snapshot or rebuild from a base backup instead of assuming it can start safely.

### 25.9. Fallback

Take a fresh base backup from the current primary, restore into a clean `PGDATA`, configure standby, and verify replication. This is the general-purpose fallback when rewind conditions are not met.

## 26. Fallback With pg_basebackup

Example creating a fresh standby:

~~~bash
pg_basebackup -h new-primary.example.internal -p 5432 -U replicator -D /var/lib/postgresql/17/rebuilt-standby -F plain -X stream -R -P -v
~~~

### 26.1. Clean Data Directory

The destination must be empty or prepared under a controlled rebuild procedure. Never overwrite a running `PGDATA`.

### 26.2. -R

Generates appropriate standby configuration per version, typically including `standby.signal` and connection settings.

### 26.3. Slots

If using slots, ensure the slot is created and the connection string/slot settings match.

### 26.4. Tablespaces

Ensure tablespace destinations exist with proper mappings.

### 26.5. Time Comparison

A base backup copies all data so it can take longer than `pg_rewind`, yet it does not depend on the old target's WAL to detect block changes.

## 27. Protecting Data on the Old Branch Before Rewind

Some incidents leave transactions that existed only on the old primary.

### 27.1. Take a Snapshot

If investigation is needed, take a storage snapshot or copy the data directory after clean shutdown and before rewinding.

### 27.2. Isolated Restore

Bring up an isolated copy from the snapshot to extract divergent data. Never attach it to the replication topology.

### 27.3. Selective Extraction

Use `pg_dump` or SQL to extract tables/rows to keep. Handle schema dependencies and sequences as needed.

### 27.4. Reconciliation

Cross-check business keys, timestamps, unique constraints, and external events. Decide which records to keep, drop, or transform.

### 27.5. Avoid Replaying Old-Branch WAL Into Source

Never attempt to replay WAL from the old branch into the new primary after a fork. Reconciliation must happen at the logical/business data level.

## 28. Security During Rejoin

### 28.1. Replication Credentials

Use a dedicated role with required replication privileges and restrict source addresses.

### 28.2. TLS

Use an appropriate SSL mode and verify server identity. Never disable certificate verification just to make the connection work.

### 28.3. Password Files

Use `.pgpass`/a secret store with strict permissions. Check whether `pg_rewind -R` writes sensitive credentials into config files per version/client behavior.

### 28.4. OS Permissions

The data directory and tablespaces should be owned solely by the OS account running PostgreSQL. Never open broad write permissions.

### 28.5. Audit Trail

Log the operator, source/target, system identifier, timeline, command options, shutdown timestamp, rewind result, and rejoin completion timestamp.

## 29. Limitations and Risks to Understand

### 29.1. Does Not Merge Writes

All writes existing solely on the target branch after divergence are discarded when the target aligns with the source.

### 29.2. Does Not Fix General Corruption

`pg_rewind` is not a tool for fixing arbitrary data corruption, disk failures, or checksum mismatches.

### 29.3. Needs WAL History

If required target WAL is lost, rewind may fail even when recent archives contain plenty of files.

### 29.4. Same Cluster Lineage

Never use it to merge two independent PostgreSQL clusters or migrate across major versions.

### 29.5. Can Overwrite Target-Specific Config

Inspect config files inside `PGDATA` and paths outside `PGDATA` after copying. Never start the target with an incompatible source config.

### 29.6. Requires Target Downtime

The target must be shut down during rewind. Downtime depends on change volume and I/O speed.

### 29.7. Does Not Replace Backups

Take an appropriate backup/snapshot beforehand if investigation or rollback may be needed. `pg_rewind` is not a backup artifact.

### 29.8. Fallback Must Be Ready

The runbook needs a clear path to rebuild from a base backup if rewind fails or prerequisites are unmet.

## 30. Monitoring and Alerting for Rejoin

| Metric / event | Purpose |
| --- | --- |
| `pg_is_in_recovery()` | Confirm target remains a standby |
| WAL receiver status | Confirm streaming connection |
| Receive LSN | WAL reception progress |
| Replay LSN | WAL application progress |
| Replay lag | Measure catch-up |
| `pg_stat_replication` | Source sees target |
| Replication slot `restart_lsn` | WAL retained by slot |
| `pg_wal` disk usage | Prevent filesystem exhaustion |
| Archive failures | Detect WAL archiving errors |
| PostgreSQL logs | Spot missing WAL/auth/recovery errors |
| Timeline history | Confirm right branch |
| System identifier | Confirm shared cluster lineage |

### 30.1. Alert When Receiver Disconnects

If the target has no row in `pg_stat_wal_receiver` or status is not `streaming`, investigate network/auth/source.

### 30.2. Alert When Replay Lag Climbs

Steadily rising lag can stem from WAL volume, I/O, or query/recovery conflicts. Do not rely on a single snapshot metric.

### 30.3. Alert on Slot Retained WAL

Monitor `restart_lsn` and disk growth. Bound slot retention per policy and plan a rebuild if a slot is invalidated.

### 30.4. Alert on Archive Gaps

Verify continuity for the timeline and WAL range a standby may need.

### 30.5. Rejoin Completion

Mark rejoin complete only when the receiver is stable, replay advances steadily, the primary sees the standby, and logs show no recurring errors.

## 31. Standard Rejoin Runbook

1. Confirm the failover decision and new primary.
2. Fence the old primary so only one writer exists.
3. Record system identifier, timeline, and divergence context.
4. Check whether divergent data on the old primary needs extraction.
5. Take a target snapshot/backup if evidence preservation is needed.
6. Confirm source and target share the same system identifier.
7. Confirm same major version and matching binaries.
8. Confirm timeline ancestry and history files.
9. Confirm checksums or `wal_log_hints` were enabled before divergence.
10. Confirm `full_page_writes` was enabled during the required interval.
11. Confirm target WAL from the divergence point remains in `pg_wal`/archive.
12. Configure `restore_command` if WAL must be fetched from archive.
13. Cleanly shut down the target.
14. Check tablespaces, filesystem permissions, and disk space.
15. Run `pg_rewind --dry-run` if supported by your version.
16. Run `pg_rewind` with exact source/target and monitor progress.
17. Verify the result and configuration files after rewind.
18. Configure `standby.signal`/`primary_conninfo`/slot/`restore_command`.
19. Start the target.
20. Confirm `pg_is_in_recovery()` returns `true`.
21. Confirm `pg_stat_wal_receiver` and `pg_stat_replication`.
22. Monitor receive/replay LSN, slot retention, and disk space.
23. Confirm the target catches up to the source.
24. Add the target to the read pool if needed and permitted by policy.
25. Record outcome, duration, timelines, and any reconciled divergent data.

## 32. Practice Exercises

Perform exercises in an isolated PostgreSQL lab with primary/standby. Never run `pg_rewind` on production without a runbook and verified source/target.

### Exercise 1. pg_rewind

What problem does `pg_rewind` solve after failover?

### Exercise 2. Timeline

Why does promotion create a new timeline?

### Exercise 3. Split-Brain

When does split-brain happen?

### Exercise 4. Source and Target

In an old-primary rejoin scenario, which node is source and which is target?

### Exercise 5. Common Ancestor

What is the significance of the common ancestor to `pg_rewind`?

### Exercise 6. System Identifier

Why must source and target share the same system identifier?

### Exercise 7. Major Version

Can `pg_rewind` upgrade PostgreSQL 15 to 16?

### Exercise 8. Checksums

How do data checksums help `pg_rewind`?

### Exercise 9. wal_log_hints

If checksums are not enabled, what alternative condition is needed?

### Exercise 10. full_page_writes

Why must `full_page_writes` be enabled?

### Exercise 11. Timing

Can you enable `wal_log_hints` after divergence and immediately run rewind?

### Exercise 12. Target Shutdown

What state must the target be in before `pg_rewind`?

### Exercise 13. Crashed Target

If the target crashed, what must be done before rewinding?

### Exercise 14. WAL Range

Which WAL is needed for `pg_rewind` to identify changed blocks?

### Exercise 15. Archive

Which option allows `pg_rewind` to fetch target WAL from an archive?

### Exercise 16. Source Mode

What are the two main ways to specify the source?

### Exercise 17. Dry Run

What is `--dry-run` used for?

### Exercise 18. Progress

What information does `--progress` provide?

### Exercise 19. Destructive Rewind

Why is a target snapshot needed before rewinding in certain incidents?

### Exercise 20. Write Recovery Config

Which option can generate configuration for the target to resume as a standby on supported versions?

### Exercise 21. standby.signal

What is the role of `standby.signal` on PostgreSQL 12+?

### Exercise 22. primary_conninfo

After rewind, where must `primary_conninfo` point?

### Exercise 23. Replication Slot

When using `primary_slot_name`, on which server must the slot be created?

### Exercise 24. Fencing

Why must the old primary be fenced before rejoining?

### Exercise 25. Writes on the Old Branch

How does `pg_rewind` handle transactions present only on the old primary after the fork?

### Exercise 26. Merge

Does `pg_rewind` merge rows from two branches?

### Exercise 27. Fallback

When target WAL is missing, what is the standard alternative?

### Exercise 28. pg_basebackup

Name one major difference between `pg_rewind` and `pg_basebackup`.

### Exercise 29. Tablespaces

Why check tablespace paths after rewind?

### Exercise 30. Config Files

Why inspect target-specific configuration after rewind?

### Exercise 31. Source State

When using `--source-server`, what state should the source be in during a normal rejoin workflow?

### Exercise 32. Timeline History

How do `.history` files help determine ancestry?

### Exercise 33. WAL Retention

For what interval must the retention policy preserve target WAL?

### Exercise 34. Recovery State

Write SQL confirming the target is running as a standby.

### Exercise 35. Receiver

Write SQL inspecting the WAL receiver.

### Exercise 36. Primary View

Write SQL confirming the primary sees the target in `pg_stat_replication`.

### Exercise 37. Slot Pressure

Why can a slot fill `pg_wal` when the target catches up slowly?

### Exercise 38. Failure Handling

If `pg_rewind` partially modified the target and then failed, what should be done?

### Exercise 39. Divergent Data

If some rows existing solely on the old branch must be kept, how should they be handled?

### Exercise 40. Runbook

List the main steps to safely bring an old primary back as a standby.

## 33. Reference Solutions

### Exercises 1–5. Timelines and Roles

`pg_rewind` aligns a diverged node back onto the source branch so it can rejoin. Promotion creates a new timeline because WAL after the fork belongs to a separate history. Split-brain happens when multiple primaries accept writes simultaneously. For old primary rejoin, source is the new primary and target is the old primary. Common ancestor is the shared WAL history point before divergence.

### Exercises 6–11. Prerequisites

System identifier confirms shared cluster lineage. `pg_rewind` does not upgrade major versions. Data checksums help detect page changes; without checksums, `wal_log_hints=on` must be enabled before divergence. `full_page_writes` must be on so WAL contains required full-page images. Enabling `wal_log_hints` after divergence does not backfill older WAL.

### Exercises 12–15. Target and WAL

Target must be cleanly shut down. If crashed, start it to finish crash recovery and then shut down cleanly. Target WAL after the divergence point is needed to locate changed blocks. `--restore-target-wal` uses `restore_command` to fetch missing WAL from the archive on supported versions.

### Exercises 16–20. Tooling

The two source modes are `--source-server` and `--source-pgdata`. `--dry-run` checks the plan without modifying data; `--progress` shows copy progress. A target snapshot can preserve old-branch data for investigation/extraction. `--write-recovery-conf` or `-R` prepares standby configuration on supported versions.

### Exercises 21–24. Rejoin

`standby.signal` tells PostgreSQL 12+ to run in standby mode. `primary_conninfo` must point to the new primary. The slot is created on the new primary. Fencing prevents the old primary from continuing to write and creating further divergence.

### Exercises 25–30. Limitations

Writes existing solely on the old branch after the fork are discarded from target; `pg_rewind` does not merge rows. If WAL is missing, rebuild from a fresh base backup. `pg_rewind` copies changed parts, whereas `pg_basebackup` creates a full new physical copy. Tablespace paths must exist on the target. Node-specific configs must be verified because files inside `PGDATA` can be overwritten.

### Exercises 31–37. Monitoring

With `--source-server`, source is normally the running new primary. History files describe timeline ancestry. Retain target WAL from divergence until rewind completes. Verify standby with:

~~~sql
SELECT pg_is_in_recovery();
~~~

Receiver:

~~~sql
SELECT status, sender_host, latest_end_lsn FROM pg_stat_wal_receiver;
~~~

Primary:

~~~sql
SELECT application_name, state, sent_lsn, replay_lsn FROM pg_stat_replication;
~~~

A slot retains WAL from `restart_lsn` that the consumer still needs. If the consumer lags long enough, WAL accumulates and `pg_wal` can grow.

### Exercises 38–40. Recovery and Runbook

If rewind fails after modifying the target, treat the target as being in an untrustworthy state; restore from snapshot or rebuild cleanly. Divergent data on the old branch requires a snapshot, isolated restore, and logical reconciliation. The runbook includes fencing, verifying source/target/lineage, checking prerequisites/WAL, clean shutdown, backing up target, dry run, rewind, configuring standby, starting, verifying receiver/replay, and monitoring catch-up.

## 34. Quick Reference Table

| Need | Tool/parameter |
| --- | --- |
| Rewind target to a source server | `pg_rewind --source-server` |
| Rewind from a source data directory | `pg_rewind --source-pgdata` |
| Specify target PGDATA | `--target-pgdata` |
| Check before writing | `--dry-run` |
| Show progress | `--progress` |
| Fetch target WAL from archive | `--restore-target-wal` |
| Generate standby recovery config | `--write-recovery-conf` / `-R` |
| Inspect cluster identity | `pg_controldata` |
| Enable block hint logging | `wal_log_hints` |
| Enable full-page images | `full_page_writes` |
| Check checksum metadata | `pg_controldata` |
| Create fallback base backup | `pg_basebackup` |
| Verify standby state | `pg_is_in_recovery()` |
| Inspect receiver | `pg_stat_wal_receiver` |
| Inspect primary replication | `pg_stat_replication` |
| Inspect slots | `pg_replication_slots` |
| Measure WAL distance | `pg_wal_lsn_diff()` |
| Standby mode PG12+ | `standby.signal` |
| Standby connection | `primary_conninfo` |
| Standby slot | `primary_slot_name` |

## 35. pg_rewind Prerequisites and Operations Checklist

1. Select and record the new primary as source.
2. Old primary is fenced and accepting no writes.
3. Source and target share the same Database system identifier.
4. Source and target run the same PostgreSQL major version.
5. Timeline history shows a common ancestor and divergence point.
6. Data checksums or `wal_log_hints` were enabled before divergence.
7. `full_page_writes` was enabled throughout the required WAL interval.
8. Target was cleanly shut down.
9. If target crashed, crash recovery completed before clean shutdown.
10. Target WAL from the divergence point remains in `pg_wal` or archive.
11. `restore_command` works if using `--restore-target-wal`.
12. Source server is reachable with appropriate permissions.
13. Target `PGDATA` path is verified accurately.
14. Target snapshot/backup taken if old state must be preserved.
15. Disk space and tablespace mounts are ready.
16. `pg_rewind` binary matches the major version.
17. Dry run executed when supported by version.
18. Source/target parameters recorded in the incident log.
19. Rewind executed with appropriate progress/logging.
20. After rewind, inspect config files and tablespace paths.
21. `primary_conninfo` points to the new primary.
22. `standby.signal` created on PostgreSQL 12+.
23. Replication slot exists if the target uses a slot.
24. `restore_command`/archive path points to the right repository.
25. Target starts successfully and `pg_is_in_recovery()` returns `true`.
26. WAL receiver connects steadily.
27. Primary sees target in `pg_stat_replication`.
28. Receive/replay LSN advances and lag decreases.
29. Slot retained WAL and disk usage stay within bounds.
30. Read routing enabled only after the standby is ready.
31. Divergent data on the old branch reconciled separately if needed.
32. If rewind prerequisites are unmet, rebuild from a base backup.
33. After rejoin, verify archiving, backups, and failover policies.
34. Record commands, logs, timelines, LSNs, and completion timestamp.

## 36. Summary

`pg_rewind` lets you reuse a diverged PostgreSQL node after failover by finding the common ancestor, analyzing target WAL, and copying needed blocks/files from the source. When the volume of data changed since divergence is small, this operation can be faster than rebuilding an entire standby with `pg_basebackup`.

To rewind safely, source and target must belong to the same cluster lineage and major version; the target must be cleanly shut down; timeline history and target WAL from the divergence point must be intact; data checksums or `wal_log_hints` must have been enabled beforehand; and `full_page_writes` must satisfy requirements. Enabling these settings after an incident cannot reconstruct missing information in older WAL.

After rewind, the target must be configured to run again as a standby of the new primary: `standby.signal` on PostgreSQL 12+, `primary_conninfo`, a slot if used, and `restore_command` when needed. Inspect configuration, tablespaces, permissions, WAL receiver, replay LSN, and the primary replication view before adding the node to a read pool or considering rejoin complete.

`pg_rewind` does not merge writes from two branches. Transactions present solely on the old primary after the fork are discarded when the target aligns with the source. If you need to keep them, snapshot the old branch and reconcile data at a logical level. When WAL is missing, common lineage is absent, or prerequisites fail, rebuilding from a fresh base backup is the clear fallback.

A sound rejoin process always begins with fencing so only one writer exists, verifying source/target and timelines, checking every prerequisite, taking a target snapshot when needed, running rewind in a controlled manner, and monitoring catch-up. Maintain WAL retention, test `pg_rewind` in restore/failover drills, and always keep a rebuild path ready to minimize how long a node stays out of the cluster.

# Recovery Targets by Time, LSN, or Restore Point in PostgreSQL

## 1. What Is a Recovery Target?

Point-in-Time Recovery (PITR) allows PostgreSQL to restore a cluster from a physical base backup and then replay Write-Ahead Log (WAL) up to a chosen point in history. A recovery target defines where WAL replay must stop.

PostgreSQL supports three commonly used ways to specify the stopping point:

- **By time:** set `recovery_target_time` using a timestamp.
- **By LSN:** set `recovery_target_lsn` using a position in WAL.
- **By restore point:** set `recovery_target_name` using a marker name written into WAL by `pg_create_restore_point()`.

These three options describe the same goal from different perspectives. Timestamps are intuitive for operators; an LSN is an exact WAL position; a restore point is a named marker created before a critical operation.

A recovery target is not a backup. It only tells PostgreSQL where to stop replaying. For PITR to succeed, you still need a valid base backup, continuous WAL, and proper restore configuration.

```text
             Physical base backup
                      |
                      v
               Restore PGDATA
                      |
                      v
             Read archived WAL
                      |
                      v
              Replay WAL records
                      |
                      v
             Recovery target reached?
                 /           \
               No             Yes
               |               |
               v               v
          Replay next       Apply target action
          WAL segment       pause / promote / shutdown
                               |
                               v
                        Validate recovered data
                               |
                               v
                         Promote / cut over
```

## 2. Learning Objectives

After this lesson, you can:

1. Explain the role of recovery targets in PITR.
2. Distinguish recovery targets by timestamp, LSN, and restore point.
3. Understand the limits of time-based recovery and transaction commit timestamps.
4. Read and write LSNs in PostgreSQL format.
5. Create named restore points using `pg_create_restore_point()`.
6. Save markers and LSNs for use in incident recovery.
7. Understand `recovery_target_inclusive`.
8. Choose `recovery_target_action` suited to your verification workflow.
9. Select timelines when recovering from backups with failover history.
10. Configure `restore_command` and WAL archives.
11. Use `recovery.signal` on PostgreSQL 12 and newer.
12. Distinguish archive recovery from standby mode.
13. Perform recovery to a point prior to an erroneous operation.
14. Check recovery progress and the last replayed position.
15. Distinguish the last replay timestamp from the actual recovery target.
16. Investigate unreachable targets caused by missing WAL or wrong timelines.
17. Design a PITR procedure in an isolated environment.
18. Protect base backups, WAL archives, and restore point metadata.
19. Verify recoverability through restore drills.
20. Build a runbook for selecting and verifying recovery targets.

## 3. PITR Requires a Base Backup and Continuous WAL

### 3.1. Base Backups Provide the Starting Point

A base backup is a physical copy of the PostgreSQL cluster created via a supported method, such as `pg_basebackup` or a compatible physical backup tool. When restored, PostgreSQL gets the foundational data files needed to start recovery.

A base backup does not contain changes occurring after the backup finished. Those changes are recorded in WAL.

### 3.2. WAL Advances the Cluster to the Recovery Target

WAL contains records describing the changes needed for PostgreSQL to reconstruct database state. During archive recovery, PostgreSQL fetches WAL from the archive via `restore_command` and replays it in order.

To recover to a target, enough WAL must exist from the base backup's required start point up to the location containing the target.

### 3.3. A Single Missing Segment Can Break PITR

If the WAL archive is missing a required segment, PostgreSQL cannot replay past that gap. A recovery target lying after the missing segment may become unreachable.

Monitoring should track:

- Archive command failures.
- Un-uploaded WAL segments.
- Archive backlog.
- Missing segments or mismatched checksums.
- Whether retention deleted WAL still needed by a base backup.
- Whether timeline history files are completely stored.

### 3.4. Base Backup and WAL Must Belong to the Same History

Never arbitrarily combine a base backup with WAL from another cluster, an unrelated timeline, or a repository lacking matching metadata. Know the backup identity, timeline, WAL start/end, and tool version.

### 3.5. Recovery Targets Only Apply During Archive Recovery

`recovery_target_*` settings take effect when PostgreSQL is performing archive recovery. On PostgreSQL 12 and newer, `recovery.signal` instructs the server to start archive recovery. `standby.signal` is for continuous standby mode and has different semantics.

Do not configure a PITR target and assume a standby will automatically stop at that target across every mode.

## 4. Three Types of Recovery Targets

### 4.1. Time-Based Target

`recovery_target_time` selects a point by timestamp.

Example:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_time = '2026-11-14 10:32:00+07'
recovery_target_action = 'pause'
```

A timestamp with an explicit timezone prevents confusion between UTC, local time, and server timezone.

### 4.2. LSN-Based Target

`recovery_target_lsn` selects an exact WAL position:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_lsn = '0/16B6C50'
recovery_target_action = 'pause'
```

An LSN represents a position in WAL, not a timestamp. It fits when another system has recorded the exact WAL location associated with the event to recover.

### 4.3. Restore-Point Target

`recovery_target_name` selects a named restore point:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_release_2026_11_14'
recovery_target_action = 'pause'
```

This name must match a previously created marker, and the marker must reside inside the replayed WAL archive.

### 4.4. Specify Only One Primary Target

Primary recovery targets include time, XID, LSN, and name. Never configure multiple primary targets expecting PostgreSQL to pick the closest one or combine them. Choose one criterion per recovery run; `recovery_target_timeline` and `recovery_target_action` are complementary settings with distinct purposes.

### 4.5. Quick Comparison

| Criterion | Time | LSN | Restore point |
| --- | --- | --- | --- |
| How specified | Timestamp | WAL location | Marker name |
| Operator readability | High | Medium/low | High |
| Requires pre-incident capture | Not mandatory, though accurate timestamp needed | Usually requires LSN from logs/metrics | Yes, marker must be created |
| Precision | By transaction commit time in WAL | By WAL position | By marker in WAL |
| Best used when | Error time is known | WAL position is known | Pre/post-change milestone exists |
| Common risks | Wrong timezone/commit boundary | Wrong LSN or timeline | Unarchived marker or duplicate names |

## 5. Time-Based Recovery Targets

### 5.1. Timestamps Need an Explicit Timezone

Use ISO 8601 timestamps with an explicit UTC offset:

```conf
recovery_target_time = '2026-11-14 10:32:00+07'
```

Or use UTC:

```conf
recovery_target_time = '2026-11-14 03:32:00+00'
```

Both represent the exact same instant. Never rely on the default timezone of a shell, laptop, or on-call engineer.

### 5.2. Recovery Does Not Stop at an Arbitrary Nanosecond

PostgreSQL replays WAL by records and transaction boundaries. Time-based recovery stops when encountering a transaction commit record whose timestamp satisfies the target per `recovery_target_time` and `recovery_target_inclusive` semantics.

Thus, a target time does not capture physical changes at an arbitrary clock microsecond. It selects a transaction state matching commit records in WAL.

### 5.3. Stopping Before or After a Transaction

Suppose an erroneous transaction committed at 10:32:04 and you want the state right before it. You can set the target just before that commit time and use appropriate exclusion semantics. Still, verify the actual commit timestamp in logs/audits and test on a temporary cluster.

Never treat the moment a user clicked a UI button as the database commit timestamp. Requests can queue, retry, span multiple transactions, or commit later.

### 5.4. recovery_target_inclusive

`recovery_target_inclusive` controls whether the transaction at the recovery boundary is included or excluded for applicable targets such as time, XID, and LSN.

- `true`: stops after the target per boundary-inclusive semantics.
- `false`: stops before the transaction at the boundary per boundary-exclusive semantics.

The default is typically `true`. When aiming to revert before a bad transaction, clarify the boundary and verify the outcome. Never flip the flag blindly.

Example:

```conf
recovery_target_time = '2026-11-14 10:32:04+07'
recovery_target_inclusive = false
recovery_target_action = 'pause'
```

This is an illustrative configuration. Choose the timestamp and inclusive flag after identifying the exact commit record to exclude.

### 5.5. Transaction Commit Timestamps May Differ from Application Logs

Applications typically log request time, event time, or processing start time. PostgreSQL time-based recovery targets rely on commit timestamps recorded in WAL. Clock skew, timezones, queueing, and transaction duration can introduce offsets.

When high precision is required, use audit records, database logs, LSN markers, or intentional restore points.

### 5.6. When Is a Time Target Appropriate?

- The incident was recorded with a reliable timestamp.
- Clear commit or audit timestamps exist.
- No pre-recorded LSN/restore point is available.
- Recovery needs to align with an interpretable business timestamp.

## 6. What Is an LSN?

An LSN (Log Sequence Number) is an address in WAL. PostgreSQL displays LSNs as two hexadecimal numbers separated by `/`.

Examples:

```text
0/16B6C50
2/AF002D8
17/4A000120
```

LSNs increase with WAL position, but they are not clocks and should not be translated directly into wall-clock time.

### 6.1. LSN Is Not a Transaction ID

A Transaction ID (XID) identifies a transaction in MVCC. An LSN identifies a WAL location. A single transaction spans multiple WAL records; LSN and XID relate through WAL contents, yet are two separate identifier spaces.

### 6.2. Viewing the Current WAL LSN on the Primary

```sql
SELECT
    pg_current_wal_lsn() AS current_wal_lsn,
    pg_current_wal_insert_lsn() AS current_insert_lsn,
    pg_current_wal_flush_lsn() AS current_flush_lsn;
```

Exact functions depend on server version and state. These values describe WAL positions at the moment of invocation; they do not automatically identify which business transaction to roll back.

### 6.3. Viewing Replay LSN on a Standby/Recovering Server

```sql
SELECT
    pg_is_in_recovery() AS is_in_recovery,
    pg_last_wal_replay_lsn() AS last_replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_commit_time;
```

`pg_last_wal_replay_lsn()` reports the latest replayed position. `pg_last_xact_replay_timestamp()` reports the commit timestamp of the most recently replayed transaction, not the current wall clock and not necessarily equal to the recovery target.

### 6.4. Comparing Two LSNs

Use `pg_wal_lsn_diff()` to calculate the byte distance between two LSNs:

```sql
SELECT pg_wal_lsn_diff('0/16B6C50', '0/16B6000') AS wal_bytes;
```

This function helps analyze WAL volume distance, not elapsed time between two events.

### 6.5. Why Are LSN Targets Precise?

An LSN pinpoints an exact WAL location, useful when a marker or audit system recorded the exact WAL address. It avoids timezone and timestamp conversion issues.

Even so, picking the wrong LSN still brings the database to an unintended state. You must know which cluster/timeline the LSN belongs to and what occurred before and after that position.

## 7. Recording an LSN for a Critical Event

### 7.1. Using a Restore Point to Create an LSN Marker

A convenient practice is creating a restore point before a critical operation:

```sql
SELECT pg_create_restore_point(
    'before_release_2026_11_14'
) AS restore_lsn;
```

The function returns the LSN of the restore point in WAL. Record both the marker name and LSN in the change ticket or backup catalog.

### 7.2. Placing a Marker Before a Change

Example before a risky migration:

1. Confirm WAL archiving is working.
2. Create a restore point with a unique name.
3. Record the returned LSN and timestamp.
4. Wait for the WAL segment containing the marker to archive and verify the artifact.
5. Execute the migration.
6. If the migration causes logical corruption, restore the base backup and replay to the pre-migration marker.

### 7.3. Execution Privileges

`pg_create_restore_point()` is a sensitive administrative operation requiring elevated privileges, typically superuser. Never grant superuser to an application role just to create markers.

### 7.4. The Marker Must Exist in the WAL Archive

Writing a restore point to WAL does not mean the segment has already been uploaded to the archive. Only consider a marker usable for PITR once the segment containing it and all preceding required segments are stored, verified, and within retention.

You can call `pg_switch_wal()` to force switching to a new WAL segment when appropriate, then verify archiving. Switching alone does not replace verifying archive success.

### 7.5. Restore Point Names Should Be Unique

Use names reflecting the system, event, and timestamp, for example:

```text
before_schema_migration_20261114_103000
before_bulk_import_orders_20261114_153000
before_release_payments_v42_20261114
```

Avoid reusing generic names like `before_release` repeatedly. With duplicate names, recovery may hit an earlier marker with the same name in WAL history and stop at the first match.

## 8. Recovery Targets by Restore Point

### 8.1. Creating a Restore Point

```sql
SELECT pg_create_restore_point('before_bad_migration') AS restore_lsn;
```

Save the returned LSN, timestamp, database/cluster identity, and change ticket.

### 8.2. Configuring the Target Name

In the restore environment:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_bad_migration'
recovery_target_action = 'pause'
```

### 8.3. A Marker Is a Named WAL Record

A restore point is not a table, row, or SQL savepoint. It is a marker in WAL. When recovery replays up to the selected marker, PostgreSQL stops per `recovery_target_name`.

### 8.4. SQL Savepoints Are Not Restore Points

`SAVEPOINT` inside an SQL transaction only supports rolling back part of an active transaction. It does not create a persistent PITR marker and cannot replace `pg_create_restore_point()`.

### 8.5. Restore Points Do Not Replace Base Backups

A marker only defines a stopping point in WAL. If the base backup and required WAL archive were deleted, a marker cannot reconstruct the cluster on its own.

### 8.6. Store Metadata Outside the Database

Record the restore point name and returned LSN in an independent system: change management, backup catalog, or incident log. If the database is completely lost, you cannot query a table inside that same database to look up the marker.

## 9. Choosing the Right Recovery Target

### 9.1. When Exact Time Is Known

Use `recovery_target_time` when audits/logs provide a reliable commit time. Include an explicit timezone and consider inclusive semantics.

### 9.2. When an LSN Was Recorded

Use `recovery_target_lsn` when a change ticket, restore point metadata, or WAL tracking system recorded a specific LSN.

### 9.3. When Preparing for a Risky Change

Create a restore point before the change, then use `recovery_target_name`. This is easy to communicate to on-call responders because the marker name ties directly to the operation.

### 9.4. When Only XID Is Known

PostgreSQL also offers `recovery_target_xid`. This helps when you have identified the commit transaction ID to use as a boundary. However, XIDs have wraparound semantics and are not business IDs; verify the transaction belongs to the right cluster/timeline.

### 9.5. Decision Table

| Available information | Target to consider | Must verify |
| --- | --- | --- |
| Commit timestamp from DB logs | `recovery_target_time` | Timezone, commit boundary, inclusive |
| Exact LSN from WAL/audit | `recovery_target_lsn` | Cluster, timeline, WAL range |
| Pre-migration marker created | `recovery_target_name` | Marker archived, unique name |
| Offending transaction XID | `recovery_target_xid` | Exact transaction and boundary |
| Approximate time window only | Time target on temporary cluster | Verify actual data before cutover |

### 9.6. Never Guess a Target

If you only know "the error happened around 10 AM," restore multiple test trials around that window in a temporary environment, inspect business state, and narrow down the target. Never push an estimated target straight into production.

## 10. recovery_target_action: Shutdown, Pause, or Promote

When the recovery target is reached, PostgreSQL needs to know what action to take next.

### 10.1. pause

```conf
recovery_target_action = 'pause'
```

`pause` suspends WAL replay at the recovery target so a DBA can inspect state before deciding how to proceed. If `hot_standby` is enabled and supported by the version, read-only connections can inspect data while recovery is paused.

This is usually the best choice for restore drills and incident recovery requiring business data verification before opening writes.

### 10.2. promote

```conf
recovery_target_action = 'promote'
```

`promote` finishes recovery at the target and transitions the server to a primary able to accept writes. Only use this automatically when the target is verified, tested, and authorized by the cutover workflow.

Once promoted and accepting new writes, returning to the same prior recovery branch requires a separate workflow. Never promote before validation completes.

### 10.3. shutdown

```conf
recovery_target_action = 'shutdown'
```

`shutdown` stops the server once the target is reached. It is useful in workflows that preserve recovered state at the target for offline inspection. Understand restart behavior and recovery configuration for your version.

### 10.4. Defaults and Capabilities

The default is typically `pause`. Behavior and supported conditions depend on major version and `hot_standby`. Check documentation for your exact version before relying on an action in automation.

### 10.5. Distinguishing Pause from Promote

- Pause: recovery is still active in state; WAL replay is temporarily halted at the target.
- Promote: ends recovery and creates a new primary.
- Shutdown: stops the server after reaching the target.

Never mistake a paused server for a primary ready to accept writes.

## 11. recovery_target_timeline and Timeline History

### 11.1. What Is a Timeline?

When a PostgreSQL standby is promoted, the cluster creates a new timeline. Timeline IDs distinguish WAL history branches after promotions/failovers.

A system with multiple failovers can have multiple timeline files in the WAL archive.

### 11.2. Why Must Recovery Choose a Timeline?

A base backup taken on an older timeline may have multiple downstream WAL branches later. Recovery must know which branch of history to follow.

### 11.3. latest

```conf
recovery_target_timeline = 'latest'
```

`latest` tells PostgreSQL to pick the newest timeline discoverable in the archive per its rules. This is commonly used when following the most recent history branch.

### 11.4. current

```conf
recovery_target_timeline = 'current'
```

`current` restricts recovery to the timeline to which the base backup belongs. Use this when you want to stay on the backup's branch without following a newer branch.

### 11.5. Specific Timeline ID

You can specify a numeric timeline ID if you know the exact branch to recover. Store timeline metadata in the backup catalog and verify history files.

### 11.6. Timeline History Files

PostgreSQL uses timeline history files to know where a new branch forked from. The archive must protect history files alongside WAL segments. Missing history files can prevent recovery from finding the right branch.

### 11.7. latest Is Not Always Right

If the archive holds a newer branch from an unrelated failover, `latest` may pick a branch other than the incident target. When investigating complex histories, identify the timeline from the base backup and history files before choosing.

## 12. Configuring PITR on PostgreSQL 12 and Newer

PostgreSQL 12 and newer use signal files to control recovery.

### 12.1. Preparing the Base Backup

Restore the base backup into a new data directory isolated from the live production cluster. Ensure tablespaces are properly restored/mapped.

### 12.2. Configuring restore_command

Illustrative example:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
```

- `%f`: filename to retrieve from the archive.
- `%p`: destination path where PostgreSQL expects the file written.

The actual command depends on your archive tool. It must return success only when the complete file is provided and return an appropriate failure status when absent. Never let the command return success for a truncated or wrong file.

### 12.3. Configuring the Target

Example time target:

```conf
recovery_target_time = '2026-11-14 10:32:00+07'
recovery_target_inclusive = false
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

For an LSN or restore point target, substitute the corresponding primary target and do not leave `recovery_target_time` set simultaneously.

### 12.4. Creating recovery.signal

Create an empty `recovery.signal` file in PGDATA to request archive recovery:

```bash
touch "$PGDATA/recovery.signal"
```

On Windows, create an empty file in the data directory using an appropriate filesystem tool. Verify the path belongs to the restored cluster.

### 12.5. Starting and Monitoring Logs

Start PostgreSQL using the appropriate service/`pg_ctl`. Watch logs to confirm:

- Recovery starts.
- WAL segments are fetched from the archive.
- Timeline is selected.
- Target is recognized.
- Recovery target is reached.
- `pause`/`promote`/`shutdown` action runs.
- Any archive error or WAL gap.

### 12.6. Never Edit Production PGDATA to Test Targets

Test PITR on an isolated restore copy. Editing recovery settings or creating signal files inside a live production data directory can alter cluster startup/recovery behavior.

## 13. Configuring PITR on PostgreSQL 11 and Earlier

Versions prior to PostgreSQL 12 use `recovery.conf` for archive recovery. Target settings and `restore_command` go inside this file per that version's syntax.

Do not copy PostgreSQL 12+ `recovery.signal` setups into runbooks for PostgreSQL 11 and earlier.

When operating multiple major versions, maintain separate runbooks and verify:

- Recovery file semantics.
- Backup API names/versions.
- Recovery target settings.
- `restore_command` syntax.
- Timeline behavior.
- Available WAL monitoring functions.

Never rely on a single configuration template across all major versions.

## 14. Practice: Creating a Restore Point Before Migration

Suppose you are preparing a risky migration on a lab database.

### 14.1. Confirm Archiving Is Active

Check:

```sql
SHOW archive_mode;
SHOW archive_command;
```

Also inspect archive logs/metrics and confirm WAL segments exist in the archive. Config settings alone do not prove uploads succeed.

### 14.2. Create the Marker

```sql
SELECT pg_create_restore_point(
    'before_lab_migration_20261114_103000'
) AS restore_lsn;
```

Record the returned LSN in the change record.

### 14.3. Wait for the Marker to Archive

Verify the WAL segment holding the marker has been published to archive storage and is readable. Trigger a WAL switch if appropriate, then wait for archiving to complete.

### 14.4. Apply the Lab Change

```sql
CREATE TABLE IF NOT EXISTS recovery_lab_marker (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO recovery_lab_marker (note)
VALUES ('change after restore point');
```

In production, migrations require separate tickets, backup verification, and change procedures.

### 14.5. Restore to the Marker

Restore a suitable base backup onto a temporary cluster and configure:

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_lab_migration_20261114_103000'
recovery_target_action = 'pause'
```

After recovery, check whether the table/row created after the marker appears. Expected result: changes committed after the marker were not replayed.

### 14.6. Verify the Target

Check logs and recovery status functions. Do not conclude recovery stopped at the right point solely because the server started successfully.

## 15. Checking Recovery Status

### 15.1. Is the Server Still in Recovery?

```sql
SELECT pg_is_in_recovery();
```

- `true`: the server is still in recovery/standby state.
- `false`: the server has exited recovery and is operating as a primary.

### 15.2. Replay LSN

```sql
SELECT
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
```

Replay LSN is critical for cross-checking against target LSN. The last transaction timestamp may be older than wall-clock time and is not a clock for the recovery process.

### 15.3. Replay Pause State

Supported versions provide functions to inspect replay pause state. Consult your major version's docs and use `pg_wal_replay_pause()`/`pg_wal_replay_resume()` appropriately when controlling replay.

Never invoke resume casually after reaching a target; continuing replay can advance past the point you intended to preserve.

### 15.4. Logs Are Key Evidence

Look for the `recovery target reached` message and corresponding action. Record the timeline, target setting, replay position, and completion time in the incident report.

### 15.5. Verify Application Data

Run read-only queries confirming business state: row counts, IDs, timestamps, aggregates, constraints, and incident-related records. A technically accurate target is not automatically the right business target.

## 16. PITR Workflow When an Erroneous Transaction Committed

Suppose an application committed a transaction that accidentally deleted data. The goal is restoring state right before that transaction.

### Step 1. Prevent Further Damage

Pause or isolate the job/consumer/feature generating bad writes if needed. Preserve logs, request IDs, transaction timestamps, and audit records.

### Step 2. Identify the Recovery Boundary

Locate:

- Commit timestamp from database logs/audits.
- XID if recorded.
- LSN if a WAL/audit marker exists.
- Any restore point created prior to the operation.
- The timeline the primary was on when the event occurred.

### Step 3. Choose a Base Backup

Pick a base backup able to replay continuous WAL to the recovery target. Verify manifest, checksums, version, and tablespace mappings.

### Step 4. Verify the WAL Archive

Confirm all required WAL segments and timeline history files exist. Check for archive gaps and retention coverage.

### Step 5. Restore Into an Isolated Environment

Create a new data directory/volume, restore the base backup, and configure `restore_command`. Set the exact recovery target and `pause` action.

### Step 6. Start Recovery

Watch logs, confirm the server replays the right timeline, and verify the target is reached.

### Step 7. Verify Data

Cross-check data against audit/event logs. Confirm the bad transaction is excluded from the recovered state while valid earlier transactions remain intact.

### Step 8. Decide How to Bring Data Back

Options:

- Promote the recovered cluster and switch traffic to the new cluster.
- Dump/copy required objects from the recovered cluster back to production.
- Perform logical reconciliation to preserve valid writes made after the recovery target.

The choice depends on downtime allowance, new writes, and business consistency. Never automatically swap the production data directory without a cutover plan.

### Step 9. Preserve Evidence

Keep the restored cluster, logs, target settings, WAL metadata, and checksums for as long as incident review requires.

### Step 10. Update the Runbook

Document detection time, selected target, actual RPO/RTO, blockers, discrepancies, and lessons learned.

## 17. Why Might a Recovery Target Not Be Reached?

| Symptom | Possible cause | Check |
| --- | --- | --- |
| Recovery stops before target | Archive ran out of WAL or segment missing | Archive catalog, logs, WAL gaps |
| Restore point not found | Marker unarchived or wrong name | Restore point metadata, segment holding marker |
| Target time mismatch | Wrong timezone/commit timestamp | Log timezone, audit, clock sync |
| Target LSN not reached | LSN from wrong cluster/timeline or past available WAL | Backup manifest, timeline, archive range |
| Recovery follows wrong branch | Inappropriate `recovery_target_timeline` | History files and failover records |
| Restore command fails | Credentials, network, path, or missing object | Command logs, storage access |
| Server promotes too early | Unexpected action/config | Effective recovery settings and logs |
| Recovery repeats after restart | Signal/recovery settings still active | `recovery.signal`, service config, logs |
| Server fails to start | Base backup missing files or wrong mappings | `pg_verifybackup`, tablespaces, permissions |
| Data fails business state check | Target chosen by request time instead of commit boundary | Audit, commit timestamps, restore trials |

### 17.1. WAL Archive May End Before the Target

If PostgreSQL reads all available WAL while the target still lies ahead, the target cannot be reached. Check archive completeness and whether the target actually lies in the history of the chosen backup/timeline.

### 17.2. Wrong Timeline

An LSN or restore point only makes sense within a specific WAL history. Selecting the wrong timeline means the marker may not exist on the branch being replayed.

### 17.3. Wrong Marker Name

Restore point names must match exactly. Avoid duplicate names and record metadata when creating markers.

### 17.4. Archive Command Errors

PostgreSQL requires fetching the exact WAL file to the exact destination path. If the command misses the file, falsely returns success, or copies incomplete bytes, recovery may stall or fail.

### 17.5. Recovery Target Ignored Due to Config

Inspect startup logs and effective configuration. Verify exactly one primary target is set, the right signal file exists, and the cluster is actually in archive recovery.

## 18. Timezones and Clock Synchronization Notes

### 18.1. Application Clocks vs. Database Clocks

An application may log an event timestamp before the transaction commits. Database commit time and request time differ. During incidents, distinguish these timestamps.

### 18.2. UTC vs. Local Time

Log timestamps in UTC or with explicit offsets. When entering a target, convert once and double-check with a timezone-aware tool.

### 18.3. Clock Skew

If servers, application nodes, and monitoring systems lack NTP synchronization, timestamp correlation can drift. Make clock synchronization part of your operational baseline.

### 18.4. DST

Some timezones observe daylight saving time. Local timestamps without offsets can be ambiguous during DST transitions. Use UTC or explicit offsets.

### 18.5. Record Both UTC and Local Time

An incident ticket should record:

- Original event timestamp.
- Source system and timezone.
- UTC conversion.
- PostgreSQL commit timestamp if available.
- Exact recovery target string used.
- Target inclusive/exclusive setting.

## 19. Restore Points in Release and Migration Workflows

### 19.1. Before Schema Migrations

Create a marker before running migrations that drop/transform columns or rewrite data. If reverting is needed, use a base backup and WAL archive to replay up to the marker.

### 19.2. Before Bulk Imports

Markers establish the state prior to batch imports. If an import goes wrong, restore to the marker in a temporary cluster to extract/reconcile data.

### 19.3. Before Administrative Actions

Operations like data cleanups, role changes, or batch maintenance may warrant a marker when impact is broad and no simple rollback logic exists.

### 19.4. Do Not Substitute Markers for Change Control

A restore point does not guarantee instant rollback. PITR takes restore/replay, validation, and cutover time. You still need staging, transactional design, backup verification, and rollback plans.

### 19.5. Avoid Creating Excessive Meaningless Markers

Restore point records consume WAL and archive metadata. Create markers for meaningful events; enforce naming conventions and manifest retention.

## 20. PITR and Timelines After Failover

### 20.1. Promotion Creates a History Branch

When a standby is promoted, PostgreSQL starts a new timeline. WAL after promotion belongs to the new branch.

### 20.2. Base Backups Taken Before Failover

A base backup may come from an older timeline while the recovery target lies on a newer timeline. Both timeline history files and the WAL chain from the right branch are required.

### 20.3. latest

`recovery_target_timeline = 'latest'` is handy when following the newest timeline found in the archive. However, in incidents with multiple failovers, `latest` may not be the business branch you need to recover.

### 20.4. Choosing a Specific Timeline ID

If the backup catalog stores timeline IDs and history files, you can specify the exact ID to recover. Confirm the target exists on that timeline.

### 20.5. Never Mix WAL from Two Independent Primaries

Two independently forked or initialized clusters do not share WAL history simply because they share a database name. Verify system identifier, timeline, and backup provenance.

## 21. Recovery Targets and Transaction Boundaries

### 21.1. Transactions Are the Commit Unit

PostgreSQL never leaves a transaction half-committed during recovery. WAL replay and transaction status ensure transactions recover according to commit/abort semantics.

### 21.2. Targeting Mid-Transaction

If a target falls in the middle of a transaction's WAL records, recovery still enforces transaction commit/abort semantics. Never treat an arbitrary target LSN as a way to slice one transaction into two visible halves.

### 21.3. Inclusive Boundaries

Use `recovery_target_inclusive` to control which side of the target boundary is kept for supported targets. Verify actual state via logs and business queries.

### 21.4. Multi-Statement Transactions

A transaction may execute multiple statements and commit once. Commit-boundary PITR includes or excludes the entire transaction per semantics, never a single statement in isolation inside the transaction.

### 21.5. Subtransactions and Savepoints

Savepoints are not recovery targets. Subtransaction rollback/commit is managed internally within the transaction; PITR targets still follow WAL recovery semantics.

## 22. LSN Targets and Replication Monitoring Tools

LSNs appear frequently in replication monitoring. Key columns and functions:

| Function/column | Meaning |
| --- | --- |
| `pg_current_wal_lsn()` | Current WAL write location on primary |
| `pg_current_wal_insert_lsn()` | Current WAL insert location |
| `pg_current_wal_flush_lsn()` | WAL flush location |
| `pg_last_wal_receive_lsn()` | Last LSN received on standby |
| `pg_last_wal_replay_lsn()` | Last LSN replayed on standby |
| `sent_lsn` | Sent WAL location in replication stats |
| `write_lsn` | WAL location written by standby |
| `flush_lsn` | WAL location flushed |
| `replay_lsn` | WAL location replayed |

Exact column/function names may differ on older PostgreSQL versions. Check catalogs/views for your running major version.

### 22.1. Received LSN vs. Replayed LSN

A standby can receive WAL before finishing replay. Having `receive_lsn` ahead of `replay_lsn` is normal. When using an LSN target, interpret the target relative to replay position, not just receive position.

### 22.2. LSN Is Not Time

Never use `pg_wal_lsn_diff()` to directly infer "how many minutes." WAL generation rate fluctuates with workload.

### 22.3. Using LSN Markers in Change Records

If a migration ticket records a restore point LSN, DBAs can use that exact marker to configure the target or cross-check replay. This bridges change management and recovery.

## 23. Protecting Recovery Metadata

### 23.1. Backup Catalog

Store:

- Backup ID and base backup location.
- PostgreSQL version and system identifier.
- Timeline ID and history files.
- WAL start/end and archive locations.
- Restore point names/LSNs.
- Recovery targets used.
- `restore_command` version/config reference.
- Tablespace mappings.
- Checksums/manifests.
- Encryption key references.

### 23.2. Store Metadata Outside the Cluster

Never store restore point names solely inside a table in the database being protected. If the cluster is lost, that metadata disappears too.

### 23.3. Protect the WAL Archive

The WAL archive must have strict access controls, immutable retention, or equivalent protection. If an attacker can delete both base backups and the WAL archive, PITR fails.

### 23.4. Verify Restore Permissions

The backup operator needs read access to the archive and backup decryption permissions. Test credential/key access during restore drills instead of discovering expired keys during an incident.

## 24. Restore Drills for Each Target Type

### 24.1. Time Target Drill

1. Pick a base backup and WAL archive.
2. Pick a known commit timestamp in the lab.
3. Restore onto a temporary cluster.
4. Configure `recovery_target_time` with an explicit timezone.
5. Test inclusive/exclusive per scenario.
6. Verify rows/transactions on both sides of the boundary.
7. Save logs and replay LSN.

### 24.2. LSN Target Drill

1. Create a restore point or intentionally record an LSN.
2. Save the LSN in a manifest.
3. Confirm the WAL segment holding the LSN has archived.
4. Restore the base backup onto a temporary cluster.
5. Configure `recovery_target_lsn`.
6. Compare `pg_last_wal_replay_lsn()` and logs against the target.
7. Verify business state.

### 24.3. Named Restore Point Drill

1. Call `pg_create_restore_point()` before a lab change.
2. Save the name and returned LSN.
3. Confirm the WAL segment holding the marker has archived.
4. Commit a change after the marker.
5. Run PITR using `recovery_target_name`.
6. Confirm changes after the marker do not appear in the recovered state.
7. Write a restore report.

### 24.4. Drills Must Test Failure Paths Too

Test a missing WAL segment once in the lab to verify alerts and logs are clear. Never delete production WAL to simulate failures.

## 25. Sample Configurations for the Three Targets

### 25.1. Stopping Before an Erroneous Time

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_time = '2026-11-14 10:32:04+07'
recovery_target_inclusive = false
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

Use when the commit timestamp is known and you want to exclude the transaction at the boundary per version semantics.

### 25.2. Stopping at an LSN Recorded in a Change Ticket

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_lsn = '0/16B6C50'
recovery_target_action = 'pause'
recovery_target_timeline = 'current'
```

Use when the LSN has been verified for the exact backup/timeline. Pick `current` only when restricting recovery to the base backup's own timeline.

### 25.3. Stopping at a Pre-Migration Restore Point

```conf
restore_command = 'archive-tool fetch "%f" "%p"'
recovery_target_name = 'before_schema_migration_20261114_103000'
recovery_target_action = 'pause'
recovery_target_timeline = 'latest'
```

Use when the marker was created and WAL archived before the migration started.

### 25.4. These Examples Are Alternatives

Do not put all three primary targets in the same recovery configuration. Each example represents a separate restore with one selected target.

## 26. PITR Incident Handling Checklist

### Before Restoring

- Identify database/cluster and system identifier.
- Identify incident, commit time, XID, LSN, or restore point.
- Select the closest suitable base backup.
- Verify continuous WAL.
- Verify timeline history.
- Verify tablespaces and configuration.
- Verify encryption keys/credentials.
- Prepare an isolated target environment.

### During Restore

- Use the exact PostgreSQL major version.
- Restore all physical files completely.
- Set `restore_command`.
- Select exactly one primary recovery target.
- Specify accurate timezone/LSN/name.
- Create `recovery.signal` on PostgreSQL 12+.
- Monitor recovery logs.
- Verify target reached and action executed.

### After Reaching the Target

- Check `pg_is_in_recovery()`.
- Check replay LSN.
- Read recovery target logs.
- Run business queries.
- Check roles/extensions/constraints.
- Decide promotion/copy-back/cutover plan.
- Record actual RPO/RTO.
- Preserve evidence and update runbooks.

## 27. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| A recovery target is a type of backup | It is the stopping point for WAL replay |
| Having a base backup is enough for PITR | Continuous WAL up to the target is needed |
| Timestamp targets stop at the exact microsecond | Recovery honors transaction/WAL boundaries |
| Application timestamps are always commit times | Request/event time can differ from commit time |
| LSN is an XID | LSN is a WAL position; XID identifies a transaction |
| LSNs convert directly into timestamps | There is no simple conversion independent of workload |
| A restore point is an SQL SAVEPOINT | A restore point is a marker in WAL |
| Writing a marker means WAL is archived | You must verify the segment has been published |
| Restore point names can be reused freely | Unique names prevent stopping at an earlier marker |
| You can set time, LSN, and name simultaneously | Choose one primary target per recovery |
| `recovery_target_inclusive` does not matter | It governs boundary inclusion for applicable targets |
| Pause means the server is already primary | The server remains in recovery and rejects normal writes |
| Promote is the same as pause | Promote ends recovery |
| `latest` timeline is always right | You must verify the intended history branch |
| WAL receive LSN equals replay LSN | Standbys can receive ahead of replay |
| `pg_last_xact_replay_timestamp` is current time | It is the commit timestamp of the last replayed transaction |
| Restore points do not need base backups | Markers cannot replace base backups |
| Standby mode and archive recovery are identical | Signal files and semantics differ |
| Reaching the target means the app is ready | Business state validation and cutover are required |
| You can PITR a single table directly | Recovery targets apply cluster-wide; table recovery usually uses a temp cluster |
| A missing WAL segment can still replay normally | A gap can block PITR from crossing it |
| Only WAL archives are needed, not history files | Timeline history files may also be required |
| Choose targets using personal laptop time | Use timezone-aware timestamps and commit evidence |
| Resuming after pause is always safe | Replay may advance past the chosen target |
| A successful restore command proves the target is right | You must verify logs, replay LSN, and data |

## 28. Practice Exercises with Answers

Exercises assume you have a PostgreSQL lab with its own base backup and WAL archive. Never test PITR by changing recovery settings on a live production cluster.

### Exercise 1. What is a recovery target?

**Answer:** The point where PostgreSQL stops replaying WAL during archive recovery.

### Exercise 2. What are the three main recovery targets covered in this lesson?

**Answer:** `recovery_target_time`, `recovery_target_lsn`, and `recovery_target_name`.

### Exercise 3. What components does PITR require?

**Answer:** A valid base backup, continuous WAL up to the target, restore configuration, and an accurate target.

### Exercise 4. Setting to choose a timestamp?

**Answer:** `recovery_target_time`.

### Exercise 5. Setting to choose an LSN?

**Answer:** `recovery_target_lsn`.

### Exercise 6. Setting to choose a named restore point?

**Answer:** `recovery_target_name`.

### Exercise 7. What is an LSN?

**Answer:** A position in the Write-Ahead Log.

### Exercise 8. What format does an LSN usually take?

**Answer:** Two hexadecimal numbers separated by `/`, e.g., `0/16B6C50`.

### Exercise 9. Are LSN and XID the same?

**Answer:** No. An LSN is a WAL location; an XID is a transaction identifier.

### Exercise 10. Function to view current WAL LSN on the primary?

**Answer:** `pg_current_wal_lsn()`.

### Exercise 11. Function to view replay LSN on a recovering server?

**Answer:** `pg_last_wal_replay_lsn()`.

### Exercise 12. What does pg_last_xact_replay_timestamp() report?

**Answer:** The commit timestamp of the most recently replayed transaction, not the current clock time.

### Exercise 13. Function to compute the byte distance between two LSNs?

**Answer:** `pg_wal_lsn_diff()`.

### Exercise 14. Which function creates a restore point?

**Answer:** `pg_create_restore_point(name)`.

### Exercise 15. What does a restore point return?

**Answer:** The LSN of the marker written into WAL.

### Exercise 16. When should a restore point be created?

**Answer:** Before a migration, bulk operation, or risky change needing a clear recovery boundary.

### Exercise 17. Should restore point names be unique?

**Answer:** Yes. Unique names prevent matching an unintended marker in WAL history.

### Exercise 18. Does a restore point replace a base backup?

**Answer:** No. It is only a marker in WAL.

### Exercise 19. Why must you verify the WAL segment containing the marker is archived?

**Answer:** If the marker is unarchived, the restore environment may not be able to replay up to it.

### Exercise 20. Is an SQL SAVEPOINT a PITR restore point?

**Answer:** No. `SAVEPOINT` only supports rollback within the current transaction.

### Exercise 21. Does a timestamp target need a timezone?

**Answer:** Include an explicit UTC offset to avoid timezone confusion.

### Exercise 22. Does recovery_target_time stop at an arbitrary microsecond?

**Answer:** No. WAL replay follows commit records and transaction boundaries.

### Exercise 23. Does application request time always equal commit time?

**Answer:** No. Queueing, execution, and transaction duration introduce skew.

### Exercise 24. What does recovery_target_inclusive control?

**Answer:** Whether the transaction at the recovery boundary is included or excluded for applicable targets.

### Exercise 25. Typical default value of recovery_target_inclusive?

**Answer:** `true`.

### Exercise 26. To exclude the transaction at a time boundary, which setting should you review?

**Answer:** `recovery_target_inclusive = false`, along with a verified target timestamp.

### Exercise 27. Which action setting pauses replay for inspection?

**Answer:** `recovery_target_action = 'pause'`.

### Exercise 28. What does promote do?

**Answer:** Ends recovery and turns the server into a new primary capable of accepting writes.

### Exercise 29. What is the purpose of the shutdown action?

**Answer:** Stops the server once the recovery target is reached, useful in workflows preserving target state for offline inspection.

### Exercise 30. Does pause mean the server accepts writes?

**Answer:** No. The server remains in recovery state.

### Exercise 31. What is a timeline?

**Answer:** A branch of WAL history distinguished by a timeline ID, typically created after promotion.

### Exercise 32. What does recovery_target_timeline = latest mean?

**Answer:** Selects the newest timeline discoverable in the archive per PostgreSQL rules.

### Exercise 33. When is current timeline used?

**Answer:** When restricting recovery to the timeline to which the base backup belongs.

### Exercise 34. Why are timeline history files important?

**Answer:** They record timeline branches and fork points, enabling PostgreSQL to follow the right WAL history.

### Exercise 35. Is latest always the right choice?

**Answer:** No. There may be a newer branch from another failover unrelated to the incident target.

### Exercise 36. Which file starts archive recovery on PostgreSQL 12+?

**Answer:** `recovery.signal`.

### Exercise 37. Does standby.signal mean the same as recovery.signal?

**Answer:** No. It starts continuous standby mode.

### Exercise 38. What does restore_command do?

**Answer:** Fetches the requested WAL/archive file and places it at the destination path provided by PostgreSQL.

### Exercise 39. What do placeholders %f and %p mean?

**Answer:** `%f` is the filename to fetch; `%p` is the destination path.

### Exercise 40. How is recovery configured on PostgreSQL 11 and earlier?

**Answer:** Using `recovery.conf` per that version's semantics.

### Exercise 41. Why must the exact PostgreSQL major version be used?

**Answer:** Physical data formats and recovery semantics must be compatible with the base backup.

### Exercise 42. Function to check whether the server is in recovery?

**Answer:** `pg_is_in_recovery()`.

### Exercise 43. Does pg_last_wal_replay_lsn() show whether all WAL was received?

**Answer:** No. It reports replay position; receive position is separate.

### Exercise 44. Why can replay LSN be lower than receive LSN?

**Answer:** A standby may have received WAL that it has not finished replaying yet.

### Exercise 45. What happens if a WAL segment is missing?

**Answer:** Recovery may be unable to reach a target located after the gap.

### Exercise 46. What happens if the restore point name is wrong?

**Answer:** PostgreSQL fails to find the target marker in the replayed WAL history.

### Exercise 47. Why must history files be archived?

**Answer:** Recovery onto newer timelines may need history files to locate the right branch.

### Exercise 48. Can you set recovery_target_time and recovery_target_name together as a fallback?

**Answer:** No. Specify one primary recovery target per recovery run.

### Exercise 49. Can a target LSN from another cluster be used?

**Answer:** No. You must verify system identifier, timeline, and backup provenance.

### Exercise 50. What privilege does pg_create_restore_point require?

**Answer:** Appropriate administrative privilege, typically superuser.

### Exercise 51. Does pg_switch_wal() replace archive verification?

**Answer:** No. It can request a segment switch, yet you must still verify archive publishing succeeded.

### Exercise 52. Why restore into a temporary environment first?

**Answer:** To verify the target/business state and avoid disrupting or overwriting the production cluster.

### Exercise 53. Does "recovery target reached" prove business data is right?

**Answer:** No. Check rows, aggregates, audit records, and application behavior.

### Exercise 54. What can you do after pause?

**Answer:** Connect read-only if configuration allows, verify data, then decide on promotion or next runbook steps.

### Exercise 55. Why must you not resume replay casually?

**Answer:** Replay can advance past the chosen target and bring back post-target transactions.

### Exercise 56. Can you PITR a single table using recovery_target_time?

**Answer:** No. Recovery targets apply cluster-wide; usually restore a temporary cluster and export the needed table.

### Exercise 57. If only request time is known, what should you do?

**Answer:** Cross-check database commit logs/audits, test multiple targets on a temporary cluster, and verify business state.

### Exercise 58. What does actual RPO depend on?

**Answer:** Backup cadence, WAL archive lag, continuity, and accessibility of recovery artifacts.

### Exercise 59. What evidence should a restore drill preserve?

**Answer:** Backup ID, target, timeline, WAL range, logs, replay LSN, validation results, and elapsed time.

### Exercise 60. Build a recovery target selection checklist

**Suggested answer:**

1. Identify the offending transaction/event and commit time.
2. Locate timestamp, XID, LSN, or restore point metadata.
3. Identify the base backup and system identifier.
4. Check WAL continuity and timeline history files.
5. Select exactly one primary target.
6. Specify explicit timezone and inclusive semantics if using time.
7. Verify the LSN belongs to the right timeline if using LSN.
8. Verify the restore point was archived if using a name.
9. Use `recovery.signal`/`restore_command` matching the major version.
10. Pause, verify business data, and only then decide on promote/cutover.

## 29. Production Checklist

| Check | What to guarantee |
| --- | --- |
| Base backup | Valid and verified copy exists |
| WAL archive | Continuous from base backup to target |
| WAL gaps | Monitoring and alerting active |
| Timeline history | Archived and retained |
| Target source | Reliable timestamp/LSN/name available |
| Timezone | Explicit UTC offset or UTC |
| Commit time | Distinguished from request/event time |
| Inclusive semantics | Chosen intentionally |
| Restore point naming | Unique, tied to change/incident |
| Restore point archive | Segment holding marker verified |
| LSN provenance | Tied to exact cluster/timeline |
| `recovery_target_timeline` | Chosen per backup lineage |
| `restore_command` | Tested for archive reads and missing-file handling |
| Signal file | Right `recovery.signal`/`standby.signal` for the goal |
| PostgreSQL version | Runbook matches major version |
| `recovery_target_action` | Pause/promote/shutdown clearly understood |
| Recovery logs | Saved for audit |
| Replay LSN | Recorded post-recovery |
| `pg_is_in_recovery` | Checked |
| Business validation | Queries and owner defined |
| Restore environment | Isolated from production |
| Tablespaces | Completely restored/mapped |
| Encryption keys | Accessible during incidents |
| Archive retention | Long enough for recovery window |
| Restore drills | Time, LSN, and name targets tested |
| RPO/RTO | Measured in practice, not just targets |
| Cutover | Decision and rollback plan ready |
| Incident evidence | Retained per policy |

## 30. Summary

A recovery target defines where WAL replay stops in PostgreSQL PITR. Choose targets by time, LSN, or restore point depending on available evidence and required precision. Regardless of method, recovery is only trustworthy when the base backup, WAL chain, timeline, and restore procedure are all valid.

Key principles:

1. **A recovery target is not a backup.** It only selects where WAL replay stops.
2. **PITR requires a base backup and continuous WAL.** A single missing segment can make a target unreachable.
3. **Time targets rely on commit times in WAL.** Application timestamps can differ from commit timestamps.
4. **Use explicit timezones.** UTC or explicit offsets prevent drift.
5. **LSN is a WAL position, not an XID or timestamp.** Verify cluster and timeline provenance.
6. **A restore point is a marker in WAL.** Create it with `pg_create_restore_point()` before protected changes.
7. **Markers must be archived.** Writing a marker does not mean the WAL segment is already published.
8. **Marker names should be unique.** Store name, LSN, timestamp, and change ticket outside the database.
9. **Inclusive semantics matter.** Determine whether the boundary transaction is kept or excluded.
10. **Pause enables verification before promotion.** Promotion ends recovery and starts a new primary branch.
11. **Timelines must match backup lineage.** `latest` is not always the incident branch you want.
12. **PostgreSQL 12+ uses `recovery.signal` for archive recovery.** Older versions use `recovery.conf`.
13. **Replay LSN differs from receive LSN.** Read the right metric when verifying.
14. **Reaching the recovery target does not prove business state is valid.** Inspect audits and actual data.
15. **Restore into an isolated environment first.** Cut over only after validation and an operational decision.
16. **Restore drills must measure real elapsed time.** Include WAL replay, validation, and cutover.

Investigation flow:

```text
Erroneous change committed?
       |
       v
Pre-incident restore point exists?
       |                 \
      Yes                 No
       |                   |
       v                   v
Target name/LSN       Commit timestamp known?
       |                   |
       |              +----+----+
       |              |         |
       |             Yes        No
       |              |         |
       |              v         v
       |         Target time   Gather audit,
       |                       LSN, XID
       +------------+-----------+
                    |
                    v
            Base backup + WAL
            + valid timeline?
                    |
                    v
             Restore into lab
                    |
                    v
             Target reached?
                    |
                    v
             Validate business
                    |
                    v
             Pause -> promote/
                cutover plan
```

**Final review question:** "If a migration corrupts data at 10:32, do we know the exact commit timestamp, LSN, or pre-migration restore point? Are the base backup and WAL archive sufficient to replay up to that point on the right timeline? And once PostgreSQL reports target reached, who validates business state before promotion?" A complete PITR workflow answers all three questions using metadata, logs, WAL, and restore drills.

# Timelines, Promotion, and Recovery History in PostgreSQL

When a PostgreSQL standby is promoted to primary, or when a cluster is recovered to a point in time and resumes accepting new writes, the database starts a **new timeline**. Timelines tell PostgreSQL which history branch a WAL belongs to, where that branch originated, and which parent timeline WALs must be combined to recover data accurately.

Imagine a primary on timeline 1. A standby receives WAL and replays changes. After an incident, the standby is promoted at LSN X. From point X onward, it begins writing WAL on timeline 2. Timeline 2 inherits timeline 1's history up to the fork point, then records its own changes:

```text
Timeline 1:
Base backup ---- WAL ---- WAL ---- WAL ---- LSN X
                                            |
                                            | Promotion
                                            v
Timeline 2:                                 WAL ---- WAL ---- WAL
                                            |
                                            +-- New changes after failover
```

A timeline is not a backup, not a transaction ID, and not an audit log. It is an **identifier for a branch of WAL history**. PostgreSQL combines timelines, WAL segments, and timeline history files to select the exact log sequence during crash recovery, standby recovery, and Point-in-Time Recovery (PITR).

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Recovery** chapter, focusing on **"Timelines, Promotion, and Recovery History"**. The content explains how timelines form, how promotion creates a new WAL branch, how PITR selects a branch, how standbys follow the new timeline after failover, and how to bring an old primary back into the cluster safely.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain timelines in PostgreSQL and why WAL branches must be distinguished.
2. Distinguish timeline ID, LSN, transaction ID, checkpoint, and restore point.
3. Describe the tree-like history structure created when a standby is promoted.
4. Explain fork points and the relationship between parent and child timelines.
5. Recognize WAL segment filenames containing timeline IDs.
6. Explain timeline history files and the information inside `.history` files.
7. Describe when PostgreSQL creates a new timeline.
8. Distinguish normal crash recovery from promotion.
9. Use `pg_promote()` or `pg_ctl promote` in a promotion workflow.
10. Understand the roles of `recovery.signal` and `standby.signal` in modern PostgreSQL.
11. Explain `recovery_target_timeline` with options `current`, `latest`, and specific timeline IDs.
12. Distinguish archive recovery, standby recovery, and PITR.
13. Select the right timeline when restoring from a base backup and a multi-branch WAL archive.
14. Understand why timeline history files must be archived and retained.
15. Monitor primary/standby using LSNs, timelines, and replication statistics.
16. Explain how asynchronous and synchronous replication affect failover data loss.
17. Recognize split-brain and the role of fencing in failover.
18. Rejoin an old primary into the cluster using `pg_rewind` or by rebuilding a standby from a base backup.
19. State the prerequisites and limitations of `pg_rewind`.
20. Plan backups, archive retention, and PITR across multiple timelines.
21. Validate recovery via restore drills, row checks, and applications.
22. Design controlled runbooks for failover, promotion, rejoin, and rollback.

**Scope:** Modern PostgreSQL, particularly versions using `standby.signal` and `recovery.signal` (PostgreSQL 12 and later). Column names in statistics views, certain parameters, and tool options may vary across major versions. Always confirm documentation for your actual cluster before operating.

---

## 2. What Problem Do Timelines Solve?

WAL is an ordered sequence of changes. During normal operation, a primary continuously generates WAL. A standby receives and replays WAL to stay in sync with the primary.

When a standby is promoted, it can begin accepting writes independently. From that point onward, new WAL is no longer the sole continuation of the old primary. Two distinct history branches can exist.

For example:

- Primary A is on timeline 1, with WAL up to LSN `0/5000000`.
- Standby B has only replayed up to `0/4F00000`.
- A suffers an outage.
- B is promoted and begins writing new WAL on timeline 2.
- Old A restarts without being resynchronized to B's branch, and continues writing on timeline 1.

At this point, the two servers can hold divergent data after the fork point. Timelines help PostgreSQL and recovery tools identify these branches.

### 2.1. A Timeline Is a Label for WAL History

Each timeline has an integer ID. The initial timeline is usually timeline 1. When promotion creates a new branch, PostgreSQL assigns a new timeline ID and records the branch history.

### 2.2. A Timeline Is Not a Database Version

Timelines do not version schemas, transactions, or snapshots. They solely distinguish a cluster's WAL histories.

### 2.3. Timelines Do Not Automatically Resolve Conflicts

Timelines indicate distinct branches. They do not automatically merge data from two independent primaries and do not elect an authoritative primary for an HA system. That belongs to failover orchestration and operational procedures.

### 2.4. Timelines Do Not Replace Backups

If the entire data directory is lost and no suitable base backup exists, timeline history files and WAL alone cannot rebuild the database from scratch.

### 2.5. Timelines Are Not Audit Logs

Timeline history does not record SQL statements, users, or every business change. It describes relationships between WAL branches and fork locations.

---

## 3. Timeline ID, LSN, and Transaction ID

These concepts are frequently confused.

| Concept | Meaning | Example |
| --- | --- | --- |
| Timeline ID (TLI) | WAL branch identifier | 1, 2, 3 |
| LSN | Position in the WAL stream | `0/5000000` |
| Transaction ID (XID) | Transaction identifier in PostgreSQL's mechanism | XID of a transaction |
| Checkpoint | Synchronization point for recovery | Checkpoint record/redo location |
| Restore point | Named marker written into WAL | `before_release` |

### 3.1. LSN Continues Along WAL Position

When a new timeline begins, WAL continues from the fork point in terms of LSN position. The Timeline ID distinguishes bytes on the new branch from bytes on the old branch when both share similar positions/segment numbers.

### 3.2. XIDs Are Not Reset on Promotion

Promotion does not create a brand-new database with reset transaction IDs. It ends recovery and transitions the server to operate as primary on a new WAL branch.

### 3.3. Checkpoints Do Not Create New Timelines

Checkpoints establish recovery state on the current timeline. A normal checkpoint does not start a new WAL branch.

### 3.4. Restore Points Do Not Create Timelines

`pg_create_restore_point()` writes a named marker into WAL. It is useful as a named recovery target, yet calling it does not promote the server or allocate a new timeline.

Example:

```sql
SELECT pg_create_restore_point('before_schema_migration');
```

The return value is the LSN of the restore point. You can use that name as a recovery target in a PITR workflow.

---

## 4. Tree-Structured Timeline History

Timelines can be visualized as a tree with branches. A child timeline inherits its parent timeline's history up to the fork point, then records its own changes.

```text
                       Timeline 1
Base backup ---- WAL ---- WAL ----+---- Old WAL continues
                                  |
                                  | Fork point
                                  |
                                  +---------------- Timeline 2
                                  |                   New WAL
                                  |                   New WAL
                                  |
                                  +---------------- Timeline 3
                                                      WAL of another branch
```

In the diagram, timeline 2 and timeline 3 may descend from the same parent timeline yet originate at different times/branches. They cannot be combined into a single write stream after the fork point.

### 4.1. Parent Timeline

The timeline containing shared history prior to the fork point.

### 4.2. Child Timeline

The child timeline continues from the fork point and records its own WAL records from then on.

### 4.3. Fork Point

The fork point is the LSN where the child timeline diverges from the parent timeline. Before this point, both branches share identical WAL history.

### 4.4. Why Must You Know Ancestry?

A base backup created on timeline 1 can be recovered onto timeline 2 if the archive contains the required parent history, timeline 2's history file, and continuous WAL on the child branch.

### 4.5. Two Branches Cannot Automatically Merge

If timeline 2 and timeline 3 both have distinct transactions after the fork point, PostgreSQL does not automatically reconcile those transactions. Combining business data requires application-layer export/import or replication reconciliation logic.

---

## 5. WAL Segment Filenames Contain the Timeline ID

WAL segment filenames follow a three-part hexadecimal structure:

```text
TTTTTTTT LLLLLLLL SSSSSSSS
   |        |        |
   |        |        +-- Segment number
   |        +----------- Log number
   +-------------------- Timeline ID
```

Illustrative filenames:

```text
00000001000000000000005A
00000002000000000000005A
```

Both files share the same log/segment portion yet have different timeline prefixes. They belong to two different WAL branches and must not be treated as identical content.

### 5.1. The Timeline ID Is Encoded in the Filename

The leading portion of the WAL segment filename represents the TLI in hexadecimal. Archive tools must therefore preserve exact filenames and never alter prefixes.

### 5.2. Do Not Store Only the Segment Number

Storing only the segment number without the timeline prefix can cause the archive to overwrite one branch's data with a file from another branch.

### 5.3. The WAL Archive Must Preserve Full Filenames

The archive repository must preserve exact WAL segment filenames and timeline history files. Never rename segments by date/time if doing so loses original identity or causes confusion during restore.

### 5.4. Segment Size Does Not Determine Timeline

WAL segment size and timeline ID are separate properties. Segment size is usually fixed when building/initializing PostgreSQL; timeline solely distinguishes history branches.

---

## 6. Timeline History Files

When a new timeline is created, PostgreSQL generates a **timeline history file**, usually with a `.history` extension.

Example:

```text
00000002.history
```

This file records the relationship between the new timeline and parent history. Its contents include the parent timeline, fork LSN, and metadata describing the reason/source of the branch.

### 6.1. A History File Is Not a WAL Segment

WAL segments contain WAL records. History files describe the timeline tree and fork points.

### 6.2. A Single History File Can Describe Multiple Ancestors

If timeline 3 branched from timeline 2, and timeline 2 branched from timeline 1, timeline 3's history file enables recovery to trace the full ancestry chain.

### 6.3. History Files Must Be Archived

PostgreSQL's WAL archiving mechanism can also archive timeline history files. Archive tooling must preserve them to recover across timeline switches.

### 6.4. History Files Help Select the Right WAL

When recovery targets a child timeline, PostgreSQL uses the history file to know up to which fork point parent timeline WAL is needed, and then switches to reading the child timeline's WAL.

### 6.5. Never Edit History Files Manually

History files are critical recovery metadata. Never edit timeline IDs, fork LSNs, or file contents to force PostgreSQL onto a desired branch.

### 6.6. Auditing the Archive Inventory

An archive containing all WAL segments yet missing a history file may still lack the information needed to traverse a timeline switch properly.

---

## 7. When Does PostgreSQL Create a New Timeline?

A new timeline normally appears when a server finishes recovery and is promoted to resume operating as a primary.

Common scenarios:

- A standby is promoted after failover.
- A backup is recovered to a recovery target and then promoted.
- A server undergoing archive recovery exits recovery and begins accepting writes.
- A recovery branch is created after selecting a point in WAL history.

### 7.1. Promotion

Promotion ends recovery mode. The server transitions to primary, accepts new writes, and starts writing WAL on a new timeline.

### 7.2. Normal Crash Recovery Does Not Create a New Timeline

If a primary crashes, restarts, and recovers along the same history, it normally continues on its existing timeline. Restarting alone does not create a new branch.

### 7.3. Checkpoints Do Not Create New Timelines

Checkpoints only update recovery state on the current timeline.

### 7.4. Restarting a Standby Does Not Equal Promotion

A standby can restart and resume recovery/streaming on the upstream's timeline. It only becomes primary when promoted.

### 7.5. A New Timeline Does Not Mean All Prior Data Changes

History before the fork point is inherited. Differences appear in WAL after the fork point.

---

## 8. What Is Promotion?

**Promotion** is the process of taking a PostgreSQL server out of recovery/standby mode so it can operate as a primary.

Before promotion:

- The server replays WAL.
- For a physical standby, data is normally read-only.
- The WAL receiver may continue receiving WAL from upstream.
- The server does not accept regular primary writes.

After promotion:

- Recovery ends.
- The server can accept writes.
- WAL continues on a new timeline.
- A history file describing the new branch is created.
- The old standby no longer automatically follows the old primary.

### 8.1. Promotion Is Not Copying Data

Promotion does not create a fresh copy of the entire database. It changes recovery state and opens a new WAL branch from the data already replayed by the standby.

### 8.2. Promotion Does Not Automatically Sync Missing WAL

If the standby had not yet received/replayed the final WAL records from the old primary, promoting can leave those transactions absent on the new branch.

### 8.3. Promotion Is an HA Decision

You must verify the old primary is truly stopped or fenced before promoting a standby. If both servers accept writes simultaneously, the system suffers split-brain.

### 8.4. Promotion Can Be Planned

Promotion can occur during maintenance, planned switchover, or DR drills when procedures guarantee data consistency and node roles.

---

## 9. Promoting a Standby via SQL or pg_ctl

### 9.1. Using the SQL Function

On a standby in recovery:

```sql
SELECT pg_promote();
```

The function can wait for promotion to complete and returns a boolean result. An overload allows adjusting the wait timeout in supported versions. Execution privileges depend on role and version.

### 9.2. Using pg_ctl

On the host with access to the data directory:

```bash
pg_ctl promote -D /path/to/standby-data
```

This command signals the server to exit standby recovery and promote.

### 9.3. Choose One Appropriate Method

There is no need to invoke both the SQL function and `pg_ctl` for the same promotion. Use one method supported by your runbook and verify status afterward.

### 9.4. Confirming the Server Exited Recovery

```sql
SELECT pg_is_in_recovery();
```

- `true`: the server is still in recovery/standby mode.
- `false`: the server is no longer in recovery mode and can act as primary if other conditions permit.

### 9.5. Confirming the Current Timeline

You can read checkpoint/control file information using tools appropriate for your version and access level. OS-level example:

```bash
pg_controldata /path/to/standby-data
```

Look for the timeline/checkpoint fields in the output. Do not rely on a single output line as a substitute for verifying replication and application data.

---

## 10. Promotion and Standby Signal Files

Starting with PostgreSQL 12, recovery modes are controlled by signal files inside the data directory instead of the legacy `recovery.conf` configuration file.

### 10.1. standby.signal

The presence of `standby.signal` instructs the server to start in standby mode and continue recovery/streaming per configuration.

### 10.2. recovery.signal

`recovery.signal` requests archive recovery, commonly used in PITR workflows.

### 10.3. Do Not Confuse the Two Signal Files

- `standby.signal`: the server continues running as a standby and may wait for upstream WAL.
- `recovery.signal`: the server executes archive recovery per restore settings/recovery targets.

### 10.4. Promotion Ends Standby Mode

When a standby is promoted, PostgreSQL ends recovery and transitions to primary. Never manually create/delete signal files while the server is running to switch roles.

### 10.5. Older PostgreSQL Versions

Versions prior to PostgreSQL 12 use `recovery.conf`. Do not apply signal-file instructions to an older cluster if that major version's documentation requires a different mechanism.

---

## 11. Promotion After Failover: Two-Node Example

Suppose a system has:

- `db-primary`: primary.
- `db-standby`: physical standby.
- Streaming WAL is active.
- WAL archiving is enabled.

State prior to the incident:

```text
db-primary (timeline 1)
       |
       | streaming WAL
       v
db-standby (timeline 1)
  replayed up to LSN Y
```

The primary suffers an outage. The standby may have received/replayed up to LSN Y while the primary may have generated additional WAL up to LSN Z that the standby did not receive.

### 11.1. Assessing Standby State

Check:

- Whether the WAL receiver is active.
- Latest received and replayed LSNs.
- Synchronous vs. asynchronous replication.
- Whether the archive holds WAL past LSN Y.
- Whether the old primary can still accept writes.

### 11.2. Fencing the Old Primary

Before promoting, ensure the old primary cannot continue accepting writes. This may require stopping the instance, network isolation, revoking storage access, or using HA platform fencing.

### 11.3. Promoting the Standby

Once failover is decided and the old primary is fenced, promote the standby.

### 11.4. The New Timeline

The standby becomes primary on a new timeline. Transactions after the fork point are written to the new branch.

### 11.5. Updating the Topology

Replicas/clients must connect to the new primary. Remaining standbys must follow the new timeline or be rebuilt/rewound if stuck on the old branch.

### 11.6. Never Bring Up the Old Primary as a Second Primary

The old primary may hold WAL records on the old branch absent from the new branch. It must be rewound or recloned before rejoining.

---

## 12. How Synchronous and Asynchronous Replication Affect Failover

Timelines identify history branches; replication mode determines how many transactions the new branch might miss relative to the old primary.

### 12.1. Asynchronous Replication

The primary does not wait for standby WAL confirmation before returning `COMMIT`. When the primary fails suddenly, the standby may not have received/replayed the final WAL records.

Promoting the standby can lose transactions committed on the primary that had not yet reached the standby.

### 12.2. Synchronous Replication

The primary waits for synchronous standby acknowledgment per configuration and `synchronous_commit`. With remote flush, confirmed commits typically have WAL flushed on an eligible standby.

### 12.3. remote_apply

At the `remote_apply` level, the primary waits for the standby to replay the transaction before confirming commit. This supports read-after-write on the standby while increasing write latency.

### 12.4. Synchronous Replication Does Not Eliminate All Failover Risks

You must ensure the right standby is chosen, acknowledgment matches policy, promotion targets the right node, and no split-brain occurs. A misconfigured synchronous setup can still lose data or suffer unavailability.

### 12.5. Comparison

| Mechanism | What Does the Primary Wait For? | Impact on Failover |
| --- | --- | --- |
| Asynchronous | Does not wait for standby | May lose WAL not yet sent/received/replayed |
| Synchronous `remote_write` | Standby writes WAL to OS | Lower protection than remote flush against standby power loss |
| Synchronous `remote_flush` | Standby flushes WAL to disk | Stronger commit durability when promoting an eligible standby |
| Synchronous `remote_apply` | Standby replays WAL | Standby has already applied confirmed commits; higher latency |

### 12.6. RPO Must Be Verified

Do not claim RPO = 0 merely because synchronous replication is enabled. Verify topology, quorum, failover selection, storage guarantees, and test real primary-loss scenarios.

---

## 13. Timeline History Files and Recovery Paths

Suppose a base backup was created on timeline 1. Later, timeline 2 was created at fork point F.

To restore to a point on timeline 2, PostgreSQL needs:

1. A valid base backup.
2. Continuous timeline 1 WAL from the backup to fork point F.
3. The history file describing timeline 2 originating from timeline 1 at F.
4. Timeline 2 WAL from after F up to the recovery target.
5. Ancestor history files if multiple branches exist.

```text
Base backup (TLI 1)
       |
       v
WAL TLI 1 ----------------------+
                                |
                           Fork point F
                                |
History file TLI 2 -------------+
                                |
                                v
                         WAL TLI 2
                                |
                                v
                         Recovery target
```

### 13.1. Parent WAL Is Only Needed Up to the Fork Point for a Child Branch

After the fork point, the child branch has its own WAL. Never mix parent WAL from after the fork point into the child history.

### 13.2. History Files Link Ancestry

History files tell PostgreSQL the parent timeline and fork location so it picks the right WAL.

### 13.3. Missing History Files Can Prevent Recovery from Following the Right Branch

An archive may contain plenty of segments yet lack a history file, preventing recovery from identifying/following the desired new timeline.

### 13.4. Retain History Files as Long as Dependent Backups Exist

If base backups remain retained that might need that timeline, retain all history files and WAL segments they depend on.

---

## 14. recovery_target_timeline: Which Branch to Choose?

The `recovery_target_timeline` parameter controls which timeline recovery or a standby will follow.

Common options:

- `current`: uses the timeline determined from the base backup/cluster being restored.
- `latest`: follows the newest timeline found in the WAL archive.
- A specific timeline ID: selects the exact desired branch.

In modern versions, the default is typically `latest`; confirm the active value on your cluster.

### 14.1. Using latest

Suitable when you want a standby to follow the newest timeline branch in the archive after failover.

### 14.2. Using current

Suitable when you want to stay on the base backup's timeline history without automatically switching to a newer branch present in the archive.

### 14.3. Using a Specific Timeline ID

Suitable when the archive holds multiple branches and recovery must stop on/follow one specifically identified branch.

Illustrative example:

```conf
recovery_target_timeline = '2'
```

This is an illustrative value. Only choose an ID that actually exists in the cluster's history/archive.

### 14.4. latest Is Not Always the Desired Business Branch

If the archive contains multiple branches from past promotions, test restores, or old failovers, the newest timeline may not be the branch the application needs to recover. When determinism is required, choose a specific timeline and document it in the runbook.

### 14.5. The New Timeline Must Have Valid Ancestry

Setting TLI alone is not enough. Recovery still requires history files and continuous parent/child WAL across fork points.

---

## 15. PITR on a Specific Timeline

PITR typically uses a base backup and WAL archive to stop at a recovery target.

### 15.1. Recovery Target Can Be Time

```conf
recovery_target_time = '2026-11-14 10:30:00+07'
```

Timezone must be explicit. A timestamp without a timezone may be interpreted using the server's configured timezone.

### 15.2. Recovery Target Can Be LSN

```conf
recovery_target_lsn = '0/7A000120'
```

Illustrative LSN. Use an actual value recorded within the same WAL history.

### 15.3. Recovery Target Can Be Transaction ID

```conf
recovery_target_xid = '123456'
```

Use only an actual XID matching the cluster and version.

### 15.4. Recovery Target Can Be a Named Restore Point

```sql
SELECT pg_create_restore_point('before_bad_deploy');
```

Then configure:

```conf
recovery_target_name = 'before_bad_deploy'
```

### 15.5. Select Only One Primary Target

Recovery target settings are mutually exclusive. Never configure multiple target types simultaneously expecting PostgreSQL to pick the right one automatically.

### 15.6. recovery_target_inclusive

This parameter controls whether the transaction right at the target is included or recovery stops before it, depending on target type. The default is typically `true`. If business data demands an exact boundary, verify semantics via a restore drill.

### 15.7. Combining Target with Timeline

Time/LSN targets must be interpreted on the selected timeline branch. The same time window can hold entirely different transactions on two branches after a fork point.

---

## 16. recovery_target_action: Shutdown, Pause, or Promote

When the recovery target is reached, PostgreSQL executes the configured action.

### 16.1. pause

The server pauses replay at the target and enters recovery pause state. This is useful for inspecting data before deciding to promote.

### 16.2. promote

The server automatically ends recovery and promotes upon reaching the target. Promotion creates a new timeline for accepting writes.

### 16.3. shutdown

The server stops after reaching the target. Useful for recovery workflows requiring inspection before opening the server.

### 16.4. Defaults and Versions

The common default is `pause`, though confirm your major version's documentation and effective configuration.

### 16.5. Inspecting Before Promotion

While paused, you can connect read-only and verify data in the recovery environment. If everything checks out, promote per runbook.

### 16.6. Resuming Recovery

`pg_wal_replay_resume()` can resume replay after a pause. If the goal is continuing from the target and creating a new primary, understand clearly when to call resume versus when to promote; the two actions have different meanings.

---

## 17. Signal Files and PITR Workflow

On PostgreSQL 12 and newer, archive recovery normally uses `recovery.signal`.

### 17.1. Preparing the Base Backup

Restore the base backup into a dedicated data directory, ensuring proper ownership, permissions, tablespace paths, and capacity.

### 17.2. Configuring the Restore Command

```conf
restore_command = 'restore-helper %f %p'
```

`restore-helper` is a placeholder for a script retrieving files from the archive. It must return accurate exit codes when files exist or are missing, handle history files, and ensure integrity.

### 17.3. Configuring Timeline and Target

```conf
recovery_target_timeline = '2'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
```

Use only one appropriate recovery target; the example above illustrates a specific time target and timeline.

### 17.4. Creating recovery.signal

Create the signal file following a verified restore procedure for your PostgreSQL version. Never leave conflicting signals/configurations simultaneously.

### 17.5. Starting and Reading Logs

PostgreSQL reads the base backup, locates required WAL, follows timeline history, and replays to the target. Read startup logs to confirm the timeline and recovery target were recognized properly.

### 17.6. Verifying Status

Use SQL to check `pg_is_in_recovery()`, business data, replay LSN, and server logs. Do not rely solely on the process starting.

### 17.7. Promoting After Inspection

If `pause` was selected, promote after verifying the target and deciding to continue operating on the new branch. Once promotion finishes, the server accepts writes.

### 17.8. PostgreSQL Prior to 12

Older versions use `recovery.conf` and follow different configuration rules. Never apply the signal-file procedure to older releases.

---

## 18. Standbys Following the New Timeline After Failover

Remaining operational standbys need to follow the new primary after promotion. This is a key reason to understand `recovery_target_timeline='latest'`.

### 18.1. Remaining Standbys May Still Be on the Prior Timeline

If standby B is promoted from timeline 1 to timeline 2, a remaining standby C may still be following timeline 1.

### 18.2. The New Timeline's History File Is Needed

C requires the history file to learn at which fork point timeline 2 branched off timeline 1.

### 18.3. latest Helps Follow the New Branch

When configured to follow `latest`, a standby can discover the new timeline in the archive and switch to the new branch if sufficient WAL/ancestry exists.

### 18.4. Missing WAL Since the Fork Point

If standby C fell too far behind and required WAL is no longer on the primary/archive, it cannot catch up automatically via streaming. You may need `pg_rewind` or a fresh base backup.

### 18.5. Cascading Standbys

A standby can feed WAL to another standby. When upstream switches timelines, cascading topologies must also follow the new branch and retain matching history/WAL.

### 18.6. Do Not Just Change primary_conninfo

Changing the connection string without resolving timeline divergence can prevent the standby from resuming recovery. Check logs, timelines, and WAL availability.

---

## 19. The Old Primary After Promotion

When a standby is promoted, the old primary may come back once its issue is resolved. However, it cannot simply resume operating on the old branch as an independent primary.

### 19.1. Why Does the Old Primary Diverge?

The old primary may have generated WAL past the fork point that the new standby never received. The new primary also has its own WAL records after promotion.

### 19.2. Never Start the Old Primary to Accept Writes

If both the old primary and new primary accept writes, the system splits into two distinct histories. Timelines do not automatically merge them.

### 19.3. Choosing a Rejoin Method

Two common approaches:

- Use `pg_rewind` to bring the old data directory onto the new primary's branch when prerequisites are met.
- Rebuild the standby from a base backup of the new primary.

### 19.4. Preserve Data Before Acting

Rewinding/reinitializing overwrites or alters the target data directory. If you need to investigate the old branch, take a snapshot/copy beforehand.

### 19.5. Do Not Treat the Old Primary as the Primary Data Source

Once failover is confirmed, the new primary is the authoritative source. Data existing only on the old branch must be extracted and reconciled separately if business requirements demand it.

---

## 20. pg_rewind: Bringing the Old Primary Back to the New Branch

`pg_rewind` is a PostgreSQL utility that synchronizes a diverged data directory with a source cluster by identifying blocks changed since their common point.

### 20.1. Core Idea

- Find the common ancestor/fork point between target and source.
- Identify blocks modified on the source branch since the divergence point.
- Copy the required blocks from the source.
- Allow the target to continue along the source's history once configured as a standby.

### 20.2. Critical Prerequisites

Before running, confirm:

1. Target and source share the same PostgreSQL cluster lineage prior to divergence.
2. Target server was shut down cleanly as required by the tool.
3. Data checksums were enabled at `initdb` or `wal_log_hints` was already enabled on the target beforehand.
4. `full_page_writes` is enabled per `pg_rewind` requirements.
5. Required WAL from the divergence point is available locally or retrievable from the archive depending on version/invocation.
6. PostgreSQL binaries and tools match the cluster.
7. A backup/snapshot of the target exists prior to rewinding.

You cannot retroactively enable checksums on an existing cluster solely to run `pg_rewind` without performing a separate conversion procedure.

### 20.3. WAL Since the Divergence Point

`pg_rewind` needs enough WAL to identify changes on the target since the fork point. If required WAL was recycled, retrieving it from the archive may be needed. If unavailable, rewind may fail.

### 20.4. Command Example

```bash
pg_rewind --target-pgdata=/data/old-primary \
          --source-server="host=new-primary dbname=postgres user=rewind_user"
```

Replace paths, connection strings, and credentials with real values. Never run this on production without verifying the target is right, the server is cleanly stopped, backups are recoverable, and preconditions are met.

### 20.5. After Rewind

Configure the target as a standby following your cluster's workflow:

- Point connection to the new primary.
- Configure replication slot if used.
- Configure WAL archive/restore command if needed.
- Enable standby mode per version (e.g., `standby.signal` on PostgreSQL 12+).
- Start and inspect WAL receiver/replay.

### 20.6. pg_rewind Is Not a Backup

Rewind modifies the target data directory. Do not use it in place of a backup, and never skip taking a snapshot when data must be preserved for investigation.

### 20.7. When Should You Use a Base Backup Instead?

If the cluster fails rewind prerequisites, required WAL is missing, or you prefer a simpler/standardized workflow, rebuilding the standby from a base backup is usually the better choice.

---

## 21. Reinitializing a Standby with a Base Backup

When the old primary cannot be rewound safely, rebuild the standby data directory from the new primary.

### 21.1. Preparation

- Confirm the new primary is the authoritative source.
- Stop and preserve the old data directory if needed.
- Verify adequate capacity for the base backup.
- Prepare replication user, connectivity, and slot.
- Check archive/WAL retention.

### 21.2. Taking the Base Backup

You can use `pg_basebackup` or compatible backup tooling. Example:

```bash
pg_basebackup -h new-primary \
              -D /data/new-standby \
              -U replication_user \
              -R -X stream
```

This is an illustrative example. Choose flags, replication slots, WAL methods, compression, and tablespace mappings per version/operational policy.

### 21.3. The -R Option

On supported versions, `-R` writes the configuration needed for the server to continue as a standby, including connection details and the appropriate signal file. Still review the configuration before starting.

### 21.4. Starting the Standby

Ensure `primary_conninfo`, slot, restore command, archive settings, and standby signal are proper. Then start the instance per runbook.

### 21.5. Confirming Catch-Up

Check `pg_stat_wal_receiver`, receive/replay LSNs, primary `pg_stat_replication`, lag trends, and read queries.

### 21.6. Rebuilding Is Resource-Intensive

A base backup transfers substantial data, increasing network/storage I/O. Schedule carefully, verify capacity, and keep the primary stable while provisioning the standby.

---

## 22. Split-Brain and Fencing

**Split-brain** occurs when two servers are both treated as primary and accept writes on separate branches simultaneously.

### 22.1. Timelines Do Not Prevent Split-Brain

Timelines distinguish WAL branches after the fact. They do not lock the old server or coordinate write authority.

### 22.2. Fencing

Fencing ensures the old node can no longer accept writes when a new node is promoted. Depending on infrastructure, use:

- Powering off the old VM/instance.
- Network isolation at the infrastructure layer.
- Revoking storage access permissions.
- Fencing via cloud control plane.
- STONITH or equivalent HA manager mechanisms.

### 22.3. Do Not Rely Only on Ping

Losing monitor connectivity does not prove the primary is dead. A network partition may blind the monitor while applications continue writing to the primary.

### 22.4. Promotion Requires Quorum/Policy

HA systems need rules determining which node is eligible to promote based on quorum, fencing, and replication state.

### 22.5. Reconciling Data from the Old Branch

If split-brain occurred, data written solely on the old branch may require manual extraction and reconciliation. PostgreSQL does not automatically merge two timelines.

---

## 23. Monitoring Timelines and Recovery State

### 23.1. Is the Server in Recovery?

```sql
SELECT pg_is_in_recovery();
```

A simple check distinguishing a recovering server from one acting as primary.

### 23.2. Replay LSN on Standby

```sql
SELECT
    pg_last_wal_receive_lsn() AS receive_lsn,
    pg_last_wal_replay_lsn() AS replay_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_time;
```

### 23.3. Primary Replication Status

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    sync_state
FROM pg_catalog.pg_stat_replication;
```

### 23.4. WAL Receiver Status

```sql
SELECT *
FROM pg_catalog.pg_stat_wal_receiver;
```

View columns may change across versions. Use `SELECT *` for lab exploration, then write explicit column lists for production monitoring.

### 23.5. Archiver Status

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

### 23.6. Checking the Control File

`pg_controldata` provides checkpoint/timeline info from the control file. This is an OS-level tool requiring data directory access and should be run with full awareness of server state.

### 23.7. LSN Does Not Replace Timeline ID

When correlating logs, record both timeline and LSN. Identical LSNs on two branches after a fork point do not represent the same WAL history.

---

## 24. Checking WAL Filenames and Positions

WAL filename functions map LSNs to segments on the current timeline.

```sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_walfile_name(pg_current_wal_lsn()) AS current_wal_file;
```

### 24.1. LSN and WAL Files

An LSN resides inside a WAL segment. The segment filename helps identify the timeline prefix and segment location.

### 24.2. Filename on the Current Timeline

`pg_walfile_name()` uses the server's current timeline. When analyzing an archive holding multiple branches, cross-check timeline history and segment names rather than inferring from a single LSN.

### 24.3. pg_walfile_name_offset()

This function returns both the filename and byte offset inside the segment for a given LSN, depending on version.

### 24.4. Do Not Infer Timestamps from Filenames

WAL segment numbers are not timestamps. To know when transactions occurred, inspect timestamp/commit records or appropriate logs.

---

## 25. Archive Retention Across Multiple Timelines

Archive policies must preserve sufficient data for every supported base backup.

### 25.1. Retain Parent Timeline WAL

An older base backup may require parent timeline WAL prior to the fork point in order to reach a child timeline.

### 25.2. Retain Child Timeline WAL

After the fork point, child branch WAL is needed up to the recovery target.

### 25.3. Retain History Files

Each child timeline needs its history file describing ancestry. If multiple branching generations exist, retain all related history files.

### 25.4. Never Prune Archives Solely by File Age

An older WAL segment may still be needed by an older base backup still within its retention window. Deleting solely by age without checking backup dependencies can break PITR.

### 25.5. Backup-Catalog-Driven Retention

A safe cleanup workflow must know:

- Which base backups remain valid.
- Which timeline each backup started on.
- What WAL is needed from each backup to committed recovery targets.
- Which timeline history files lie along the ancestry path.
- Which WAL standby/logical consumers still need.

### 25.6. Archives Must Prevent Overwrites

Use full filenames and proper immutable/atomic publishing rules. If a file with the same name already exists, verify checksum/content; never silently overwrite a different archive segment.

### 25.7. Checking Archive Continuity

A manifest can record WAL segments/history files by timeline and checksum. Periodically verify continuous ranges required by the backup catalog.

---

## 26. PITR Across Multiple Promotions

Suppose the history is:

1. Timeline 1 was the initial primary.
2. A standby was promoted, creating timeline 2 at LSN A.
3. Timeline 2 ran and was backed up.
4. Another PITR/DR event created timeline 3 at LSN B on timeline 2.

To restore to a target on timeline 3, recovery must understand the ancestry:

```text
Timeline 1
   |
   | Fork A
   v
Timeline 2
   |
   | Fork B
   v
Timeline 3
```

### 26.1. Ancestor History Is Required

You do not need only `00000003.history`. You need the full ancestry information to traverse timeline 2 and timeline 1 if the base backup started on an older branch.

### 26.2. Each Timeline's WAL Has Boundaries

Timeline 1 WAL applies up to fork A; timeline 2 WAL applies up to fork B; timeline 3 WAL applies after fork B.

### 26.3. Targeting a Specific Branch

If the archive contains multiple descendants, specify the timeline ID explicitly when reconstructing a specific history.

### 26.4. Backups on the New Timeline Simplify Recovery

Taking a base backup after promotion on the new timeline reduces how much ancestor WAL must be replayed, yet subsequent WAL must still be kept for PITR.

### 26.5. Do Not Discard Old History Files

A new backup does not immediately invalidate all older backups. Retention must follow the catalog and recovery objectives.

---

## 27. Lab: Observing Timelines Before and After Promotion

This lab requires at least one primary and one physical standby in an isolated environment. Never promote a production cluster just to observe.

### 27.1. On Primary, Check LSN

```sql
SELECT
    pg_current_wal_lsn(),
    pg_current_wal_flush_lsn();
```

### 27.2. On Standby, Check Recovery State

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn();
```

As a standby, `pg_is_in_recovery()` must return `true`.

### 27.3. Write Test Data on Primary

```sql
CREATE TABLE IF NOT EXISTS public.timeline_lab (
    id BIGINT PRIMARY KEY,
    note TEXT NOT NULL
);

INSERT INTO public.timeline_lab(id, note)
VALUES (1, 'before-promotion')
ON CONFLICT (id) DO UPDATE SET note = EXCLUDED.note;
```

Wait for the standby to replay and verify the row.

### 27.4. Fencing and Promotion in the Lab

Stop the primary or isolate it per your test topology. Then promote the standby:

```sql
SELECT pg_promote();
```

Run this only after confirming you are connected to the right standby and the lab permits promotion.

### 27.5. Confirm

```sql
SELECT pg_is_in_recovery();
```

Expect `false` after promotion completes.

### 27.6. Write a Row After Promotion

```sql
INSERT INTO public.timeline_lab(id, note)
VALUES (2, 'after-promotion');
```

This row is written on the new timeline.

### 27.7. Inspect the WAL Archive

Locate the timeline history file and WAL segment carrying the new timeline prefix in the archive. Exact filenames depend on the cluster's timeline ID and WAL position.

### 27.8. Completing the Lab

Do not bring the old primary back as an independent primary. Use `pg_rewind` if prerequisites are met or rebuild the standby from a base backup per the rejoin section.

---

## 28. Lab: Creating a Restore Point and Timeline-Aware PITR

This lab requires a base backup, continuous WAL archiving, and a separate restore data directory.

### 28.1. Create the Marker

On the primary:

```sql
SELECT pg_create_restore_point('before_test_change');
```

Record the LSN and timestamp.

### 28.2. Make a Change After the Marker

```sql
INSERT INTO public.timeline_lab(id, note)
VALUES (100, 'after-restore-point');
```

### 28.3. Take a Base Backup

Use an appropriate backup tool to take a consistent base backup. Record timeline and backup timestamp metadata.

### 28.4. Prepare the Restore Copy

Restore into a separate data directory without overwriting any active primary or standby.

### 28.5. Configure Recovery

Illustrative configuration example:

```conf
restore_command = 'restore-helper %f %p'
recovery_target_name = 'before_test_change'
recovery_target_timeline = 'current'
recovery_target_action = 'pause'
```

The timeline must match the actual backup and archive history.

### 28.6. Start Recovery

Follow the version-specific procedure with `recovery.signal`. Watch logs until recovery pauses at the named restore point.

### 28.7. Verify Data

Rows written before the restore point must be present if covered by the base backup/WAL path. The `after-restore-point` row must not appear since recovery stopped before that transaction.

### 28.8. Promote If Continuing Writes

After inspection, promote the restored instance per runbook. This creates a new timeline from the recovery target point.

### 28.9. Retain the Original Archive

Do not delete WAL/history files used in the lab immediately after promotion if further analysis or reproducible restores are needed.

---

## 29. Lab: Inspecting Multiple Timelines in an Archive

An archive may contain files such as:

```text
00000001.history
00000002.history
00000003.history
000000010000000000000050
000000020000000000000050
000000030000000000000051
```

These are illustrative names, not an actual inventory.

### 29.1. Classifying Files

- `.history`: describes ancestry/fork points.
- WAL segment: contains WAL records belonging to the TLI in its prefix.

### 29.2. Reading History Files

Use a safe archive-reading tool to inspect parent timelines and fork LSNs. Never edit the files.

### 29.3. Building the Timeline Tree

Map parent/child timelines from each history file. Identify which WAL range each branch requires.

### 29.4. Cross-Checking the Base Backup

Note which timeline the backup belongs to and its start timestamp/LSN. From there, compute the segments needed to reach the target.

### 29.5. Checking Continuity

Confirm every WAL segment along the path exists with a valid checksum. Even one unreadable file can break recovery.

### 29.6. Selecting the Timeline

Set `recovery_target_timeline` to the identified TLI. Never default to `latest` when the archive holds branches unrelated to the recovery case.

---

## 30. Operational Timeline Scenarios

### 30.1. Primary Failover

A standby is promoted and a new timeline is created. Remaining replicas must follow the new timeline or be rebuilt/rewound.

### 30.2. Planned Switchover

You can halt writes on the primary, wait for the standby to replay to the target LSN, and promote the standby. This minimizes or eliminates data loss under verified synchronization.

### 30.3. PITR After Accidental Data Deletion

Restore a base backup to just before the erroneous transaction, verify data, then promote. The new branch forks from the old history at the target.

### 30.4. Restoring to Verify a Backup

You can restore a copy and pause at the target without promoting. For verification only, keep the copy isolated from production.

### 30.5. Standby Falling Too Far Behind

If WAL has already been recycled, a standby may be unable to catch up. Check the archive and slots; use `pg_rewind` or a base backup depending on divergence.

### 30.6. Two Branches Accepting Writes Simultaneously

This is split-brain. Stop/fence the non-authoritative branch, preserve data needed for investigation, and perform controlled reconciliation.

### 30.7. Archive Has a New Timeline Yet Lacks Parent WAL

A history file cannot substitute for parent WAL. Restore archive continuity or choose another backup with a complete WAL path.

---

## 31. Safe Failover Procedure

A failover workflow should follow clear stages.

### 31.1. Confirm the Incident

- Verify primary health via multiple signals.
- Distinguish a network partition from a process/storage failure.
- Gather the latest retrievable LSN and replication state.
- Identify eligible standbys and potential data loss.

### 31.2. Fence the Old Primary

Ensure the old primary can no longer accept writes. If fencing cannot be confirmed, do not promote solely on a single health check timeout.

### 31.3. Select the Standby

Choose the node with the best WAL receive/replay progress per policy. With synchronous replication, confirm the node is an eligible synchronous standby.

### 31.4. Promote

Use a tested promotion method. Wait for completion and verify `pg_is_in_recovery()` returns `false`.

### 31.5. Confirm the Timeline

Verify the new timeline, history file, and WAL generation. Record the TLI, fork point/LSN, and promotion timestamp in the incident log.

### 31.6. Shift Traffic

Update connection routing, service discovery, proxies, or load balancers so applications write to the new primary.

### 31.7. Verify Application Health

Run smoke tests, transaction checks, and verify critical data. Monitor write errors, commit latency, and replication status.

### 31.8. Rebuild Topology

Bring other standbys onto the new timeline. Rewind or rebuild nodes on the old branch.

### 31.9. Preserve Evidence

Record timeline history, LSNs, archive status, backup references, and failover decisions to support operational audits.

---

## 32. Planned Switchover Procedure

Switchover differs from failover because the old primary is still healthy and can coordinate role transfer.

### 32.1. Readiness Checks

- Standby streaming is stable.
- No WAL/archive backlog.
- Replication lag is low or zero per criteria.
- Adequate capacity and health on the standby.
- Application tolerates the brief write pause.

### 32.2. Stop or Drain Writes

Use appropriate application/DB mechanisms to stop new writes and wait for active transactions to finish.

### 32.3. Wait for Standby Replay

Compare primary and standby LSNs and confirm the standby has replayed up to the cutover point.

### 32.4. Promote the Standby

Promote the standby once synchronization criteria are met.

### 32.5. Shift Traffic

Point write endpoints to the new primary, verify the application, and confirm the old node has been converted to standby or stopped.

### 32.6. Prevent Two Primaries

Even a planned switchover requires proper role-transition sequencing and fencing. Never allow the old node to accept writes after the new node is promoted.

---

## 33. Moving Remaining Standbys to the New Timeline

When one standby is promoted, other standbys may still be on the old timeline.

### 33.1. Check Eligibility to Follow the New Timeline

If the node shares ancestry and required WAL from the fork point is available, configuring `recovery_target_timeline='latest'` with proper archive/streaming settings can let it follow the new branch.

### 33.2. If WAL Is Missing

If required WAL was recycled or the node has diverged data, evaluate `pg_rewind` or a fresh base backup.

### 33.3. Never Rename Timeline IDs in Filenames

Never rename WAL segments from the old timeline with the new timeline's prefix. They contain different records.

### 33.4. Check Replication Slots

Old standby slots may need updating for the new topology. Ensure slots exist and match the right consumers before starting streaming.

### 33.5. Confirm Replay

Monitor receive/replay LSNs and startup logs. A connected standby that is not replaying has not successfully rejoined.

---

## 34. Differences Between Crash Recovery, Archive Recovery, and Standby Recovery

| Recovery Type | Goal | Post-Recovery Behavior |
| --- | --- | --- |
| Crash recovery | Recover cluster after abnormal shutdown | Continues current timeline as primary if it was primary |
| Archive recovery/PITR | Replay archived WAL to a target | Can pause, shut down, or promote |
| Standby recovery | Follow WAL from primary/stream/archive | Remains read-only standby until promotion |
| Promotion | End recovery and start accepting writes | Creates a new timeline |
| Rewind/rejoin | Bring diverged data directory back to source branch | Reconfigures as standby |

### 34.1. Crash Recovery

Does not create a new timeline by default. It restores a consistent state for the same cluster on its current timeline.

### 34.2. Archive Recovery

Uses a base backup and WAL archive. Can stop at a recovery target.

### 34.3. Standby Recovery

Continuously receives WAL from upstream. When the upstream primary switches timelines, the standby needs the new history and WAL.

### 34.4. Promotion

Promotion is the boundary where roles switch and a new history branch begins.

### 34.5. Rewind

Rewind is not simple WAL replay. It modifies the target data directory to remove divergence and follow the source timeline.

---

## 35. Common Mistakes When Managing Timelines

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Not archiving `.history` files | Cannot trace ancestry properly | Check archive tooling and preserve history files |
| Keeping only segment number without TLI prefix | Overwrites/mixes up branches | Preserve full filenames |
| Using `latest` in a multi-branch archive | Restores wrong history | Identify and select specific TLI |
| Promoting before fencing old primary | Split-brain | Fence and enforce quorum before promotion |
| Restarting old primary as primary | Two branches accept writes | Rewind or reclone |
| Missing WAL from fork point | Cannot follow or rewind | Retrieve archive or take fresh base backup |
| Deleting archives by file age | Old backups lose PITR capability | Clean up based on backup dependencies |
| Confusing restore point with timeline | Wrong recovery target | Distinguish markers from branches |
| Confusing checkpoint with promotion | Wrong recovery mental model | Checkpoints do not create TLIs |
| Recording only LSN without TLI | Miscorrelates two branches | Record both timeline and LSN |
| Changing `primary_conninfo` while ignoring divergence | Standby fails to replay | Check history/WAL, rewind/reclone |
| Running `pg_rewind` without prerequisites | Failure or un-rewound target | Verify checksums/`wal_log_hints`/WAL |
| Using `pg_rewind` as a backup | Loses target data needed for forensics | Snapshot before rewinding |
| Letting standbys lag too long | WAL gets recycled | Plan slots, archiving, and capacity |
| Assuming sync replication auto-picks the right node | Failover may pick wrong node | Check quorum and sync state |
| Not testing PITR on child timelines | Unnoticed broken archive paths | Run restore drills across branches |
| Missing timeline history in offsite archive | DR restores onto wrong branch | Replicate history files |
| Two sites promoting together | Cross-region split-brain | Enforce topology-wide fencing/quorum |
| Assuming timelines merge two primaries | Data loss or business conflicts | Reconcile at the data layer |
| Omitting incident LSN/fork point records | Hard post-failover investigation | Log TLI, LSN, timestamp, and history |

---

## 36. Practice Exercises

### Exercise 1 — Timeline Concept

Explain what a timeline is and why PostgreSQL needs timelines when a standby is promoted.

### Exercise 2 — Timeline and LSN

Distinguish timeline ID and LSN. Why must both be recorded when investigating recovery?

### Exercise 3 — Fork Point

Draw a parent/child timeline and mark the fork point. Which WAL is used before and after this point?

### Exercise 4 — Timeline History File

What information does a `.history` file contain? Why does it not replace WAL segments?

### Exercise 5 — WAL Filenames

Break down the three parts of a WAL segment filename and point out the timeline ID portion.

### Exercise 6 — Promotion

Describe server state before and after promotion. Why does promotion create a new timeline?

### Exercise 7 — Crash Recovery

A primary crashes and restarts on the same data directory. Why does this usually not create a new timeline?

### Exercise 8 — Restore Points

Use `pg_create_restore_point()` to create a marker. Why is a marker not a timeline?

### Exercise 9 — pg_promote

Write SQL commands to check and promote a standby in a lab environment. What conditions must be verified before running?

### Exercise 10 — pg_ctl promote

Write the `pg_ctl promote` command and explain differences between the OS-level tool and the SQL function.

### Exercise 11 — Signal Files

Distinguish `standby.signal` and `recovery.signal`. Why does this differ from PostgreSQL prior to 12?

### Exercise 12 — recovery_target_timeline

Compare `current`, `latest`, and a specific TLI. When an archive contains multiple branches, which choice is easiest to control?

### Exercise 13 — PITR

Design a PITR workflow to a named restore point on timeline 2 from a timeline 1 base backup.

### Exercise 14 — Recovery Target Time

Explain the roles of timezone and `recovery_target_inclusive` when stopping by time.

### Exercise 15 — Recovery Target Action

Compare `pause`, `promote`, and `shutdown`. When should you pause to inspect data?

### Exercise 16 — Standby Following a Timeline

A third standby is still on timeline 1 after a second standby was promoted to timeline 2. Which files and WAL does it need to follow the new branch?

### Exercise 17 — Async Replication

The primary fails before the standby receives the final WAL. What can happen when promoting the standby?

### Exercise 18 — Synchronous Replication

Why can `remote_flush` protect commits better than async replication? What conditions must still be verified?

### Exercise 19 — Split-Brain

Describe a scenario where two primaries accept writes simultaneously. Do timelines automatically merge or prevent this?

### Exercise 20 — Fencing

Propose fencing mechanisms for VMs, bare metal, or cloud environments.

### Exercise 21 — Old Primary

After failover, the old primary comes back. Why must it not accept writes immediately?

### Exercise 22 — pg_rewind

Explain how `pg_rewind` finds the common ancestor and updates changed blocks.

### Exercise 23 — pg_rewind Prerequisites

State requirements regarding clean shutdown, data checksums or `wal_log_hints`, `full_page_writes`, and WAL availability.

### Exercise 24 — Base Backup Rejoin

When should you rebuild a standby with `pg_basebackup` instead of `pg_rewind`?

### Exercise 25 — Archive History

Why can a missing timeline history file break a recovery path even if WAL segments remain?

### Exercise 26 — Multi-Generation Timelines

Draw timeline 1 -> timeline 2 -> timeline 3. List the WAL ranges required for a base backup from timeline 1.

### Exercise 27 — Archive Retention

Design a cleanup policy that avoids deleting WAL/history files still needed by backups within the retention window.

### Exercise 28 — LSN Monitoring

Write queries to inspect receive/replay LSN on a standby and sent/write/flush/replay LSN on a primary.

### Exercise 29 — pg_controldata

Use `pg_controldata` to inspect checkpoint/timeline state. Why should this be combined with SQL and logs?

### Exercise 30 — Specific Timeline ID

An archive contains timeline 2 and timeline 3, where timeline 3 is a test branch. Why might `latest` be unsuitable for a production restore?

### Exercise 31 — Planned Switchover

Outline the sequence to drain writes, wait for replay, promote, and shift traffic to minimize data loss.

### Exercise 32 — Failover Runbook

Create a checklist covering failure detection, fencing, standby selection, promotion, traffic cutover, and replica rejoin.

### Exercise 33 — Restore Drill

Design a recovery test from a base backup traversing two timeline history files to a specific target.

### Exercise 34 — Archive Integrity

Propose ways to verify checksums, continuity, and immutable storage for WAL segments and `.history` files.

### Exercise 35 — Standby Lag

A standby cannot follow the new timeline because WAL is missing. State recovery options and selection criteria.

### Exercise 36 — pg_rewind Failure

`pg_rewind` reports missing WAL since the fork point. Where can you retrieve WAL from, and when is a fresh base backup needed?

### Exercise 37 — Ambiguous Failover

The monitor cannot reach the primary, yet cannot tell if the primary is still accepting writes. Why is fencing mandatory before promotion?

### Exercise 38 — Timeline and Auditing

A DBA wants to use timeline history to find out which user dropped a table. Why does timeline history not provide this information? What logging is needed?

### Exercise 39 — Reconciling Branches

Two primaries accepted writes on two separate branches. Propose how to preserve and reconcile business data.

### Exercise 40 — End-to-End Design

A multi-region PostgreSQL system has one primary, two synchronous standbys, and a 14-day WAL archive. Design promotion/failover, timeline selection, archive retention, PITR, `pg_rewind`/rebuild, fencing, and restore drills. Clearly explain trade-offs across RPO, RTO, availability, latency, and cost.

---

## 37. Timeline, Promotion, and Recovery History Operational Checklist

| Question | What to Confirm |
| --- | --- |
| What is the current timeline? | TLI in control/history |
| What are the current LSN and replay LSN? | Record alongside timeline |
| Are there any fork points? | Timeline history |
| Are history files archived? | Archive inventory |
| Do WAL segment filenames keep their TLI prefix? | Archive naming |
| Is WAL continuous from the base backup? | Backup/WAL manifest |
| Are there multiple branches in the archive? | Timeline tree |
| Does the recovery target select the right branch? | `recovery_target_timeline` |
| Does the target time have an explicit timezone? | Recovery config |
| Is the target action appropriate? | `pause`/`promote`/`shutdown` |
| Which timeline does the base backup belong to? | Backup metadata |
| Does the archive retain full ancestry? | Parent WAL/history |
| Does the standby follow `latest` properly? | `standby.signal`/config |
| What is the receive/replay lag? | LSNs and monitoring |
| Is the sync standby the right node? | `sync_state`/quorum |
| Is the old primary fenced? | HA control plane |
| Did promotion complete? | `pg_is_in_recovery()` |
| Was the new timeline created? | Control/history/archive |
| Has write traffic shifted? | Application routing |
| Have other replicas rejoined? | Receiver/replay state |
| Can `pg_rewind` be used? | Prerequisites |
| Was the target shut down cleanly? | `pg_rewind` requirement |
| Are checksums or `wal_log_hints` enabled? | Target cluster setup |
| Is `full_page_writes` configured properly? | Cluster setting |
| Is WAL from the fork point still sufficient? | Local/archive WAL |
| Is there a snapshot prior to rewind? | Recovery safety |
| If rewind fails, is a base backup available? | Rebuild plan |
| Are there no two primaries? | Fencing/quorum |
| Does archive cleanup follow backup dependencies? | Retention catalog |
| Are history files retained offsite? | DR archive |
| Has PITR been tested across multiple TLIs? | Restore drills |
| Was restored data verified? | Application checks |
| Were RPO/RTO measured? | DR evidence |
| Does the incident record include TLI/LSN? | Operational history |
| Is there a rollback/failback plan? | Rejoin runbook |
| Does the archive have checksums/immutability? | Integrity/security |
| Are slot/WAL retention alerts active? | Capacity alerts |

## Conclusion

Timelines are the mechanism PostgreSQL uses to manage WAL history branches after promotion or recovery. They tell the database where a branch originated, which WAL belongs to which branch, and which segments must be replayed to recover an exact state.

Key principles:

1. **Timelines identify WAL branches.** LSNs represent positions inside WAL; record both timeline and LSN when analyzing history.
2. **Promotion creates a new timeline.** A promoted standby begins accepting writes on a child branch starting from the fork point.
3. **Normal crash recovery does not create a new timeline.** Restarting a primary along the same history usually continues the current timeline.
4. **History files describe ancestry.** `.history` files record the parent timeline and fork point; they must be archived alongside WAL segments.
5. **WAL segment filenames contain the timeline ID.** Preserve full filenames to avoid confusing or overwriting branches.
6. **PITR requires a base backup and continuous WAL.** When multiple branches exist, set `recovery_target_timeline` explicitly to recover the right history.
7. **Standbys must follow the new primary's timeline.** They need history files, WAL from the fork point, and proper follow settings.
8. **Synchronous replication affects potential WAL loss during failover.** Verify sync policies, selected standbys, and replay/flush states.
9. **Fencing prevents split-brain.** Timelines distinguish branches yet do not stop two primaries from accepting writes simultaneously.
10. **The old primary requires rewind or rebuild.** Never let a node on an old branch accept writes as an independent primary after failover.
11. **`pg_rewind` has prerequisites.** It requires clean shutdown, checksums or `wal_log_hints`, `full_page_writes`, and sufficient WAL from the divergence point.
12. **Archive retention must account for the entire timeline tree.** Never delete history/WAL still needed by base backups and PITR within the retention window.
13. **Restore drills must test real branches.** A backup is only trustworthy when it can restore through history files, replay WAL, and verify data at the target.
14. **Preserve promotion evidence.** Record TLI, LSN, fork point, timestamp, history file, archive status, and the fenced node.

A reliable recovery workflow must answer three questions: which timeline the server is on, which parent branch that timeline inherited WAL from, and whether all data needed to recover to the target remains intact. When failover, promotion, PITR, and rejoin are managed along a single clear history, PostgreSQL can continue serving on the right branch without mixing changes from diverged branches.

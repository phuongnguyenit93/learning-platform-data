# Handling Data Loss or Storage Corruption Following a Rehearsed Neo4j Procedure

## 1. Goal: Verified Recovery, Not "Trial-and-Error Data Patching" Directly

In Neo4j, a property graph database stores **nodes**, **relationships**, **properties**, schema indexes/constraints, and transaction metadata. When data is accidentally deleted, a disk fails, or the database refuses to start, the first action **must not** be deleting suspected corrupt files, re-running `MERGE` scripts, or restarting repeatedly.

The goals of a sound recovery procedure are:

1. **Prevent further data loss** and avoid destroying technical evidence.
2. **Determine incident scope**, blast radius, and the latest point when data was still valid.
3. **Select a backup and recovery approach** matching the edition, cluster topology, and recovery targets.
4. **Restore into an isolated environment first**, checking both store consistency and business data integrity.
5. **Reopen the service in stages**, with a traffic cutover and rollback plan.
6. **Reconcile transactions at risk of loss**, document postmortems, and improve the next drill.

This topic belongs to the Neo4j **Backup and Recovery** chapter. Examples focus on operating databases used by Cypher, the Java Driver, and Spring Data Neo4j, not manipulating Neo4j's internal binary store files.

> **Safety boundary:** `restore`/`load` commands can replace an existing database when `--overwrite-destination` is used. This lesson deliberately uses **new test databases** in examples. Never run destructive or store-replacing commands in production without change approval, a verified source copy, and a rollback plan.

## 2. Classify the Incident Before Deciding to Restore

Two symptoms may both look like "data loss" yet require completely different responses.

| Symptom | Possible cause | First priority | Typical options to consider |
| --- | --- | --- | --- |
| Nodes/relationships deleted or wrongly updated | Faulty Cypher, script, app bug, or permissions | **Stop the faulty writer**, identify transaction/timestamp | Point-in-time recovery, stand up a copy to compare, controlled business repair |
| Database lost data after rollback or import/load | Wrong target, overwrite, faulty pipeline | Isolate the offending job; preserve logs and copies | Restore latest clean backup, recalculate delta changes |
| One cluster host/disk failed, others healthy | Hardware failure, node crash | Check quorum, leader, and member status | Failover/replacement/reseed per cluster procedure; **not necessarily a full graph restore** |
| Database not `ONLINE` or reports corruption | Store/index/log error, truncated storage, filesystem fault | Stop writes, preserve store/logs intact, inspect logs and health | Run offline check; restore a verified backup, or engage Neo4j Support |
| Storage volume/persistent disk lost | Disk/volume deleted or infrastructure failure | Halt tasks writing to target; preserve evidence | Re-provision storage, restore an independent backup |
| Missing file in a backup chain | Bad retention, incomplete copy, cloud object deleted | Halt cleanup/rotation jobs | Locate another intact chain or select another full backup |
| Signs of unauthorized data tampering | Compromised credentials, ransomware, anomalous access | Security incident: revoke access, protect backups, audit | Restore a **clean recovery point**, rotate secrets, verify no reinfection |
| App returns stale data yet DB is healthy | Cache, read-replica lag, bookmark/routing issue | Inspect authoritative data and sync lag | Fix consistency/cache; **do not restore blindly** |

**Never equate availability with data recoverability.** Clustering keeps serving when a member dies, yet transactionally valid `DELETE` operations replicate to other members. Clusters **do not replace independent backups**.

## 3. Establish RPO and RTO Before an Incident Strikes

### 3.1. Two Metrics You Cannot Trade Off Interchangeably

- **RPO — Recovery Point Objective:** maximum data time-window allowed to be lost after an incident. For example, a 15-minute RPO aims to restore to a state **no more than 15 minutes** before the incident.
- **RTO — Recovery Time Objective:** maximum duration from incident detection/declaration until the service recovers to an acceptable level, **including verification and reopening traffic**.

Example policy for an order service:

| Target | Illustrative value | Implication |
| --- | --- | --- |
| RPO | 15 minutes | Requires frequent, successful backup points/transaction logs |
| RTO | 90 minutes | Requires pre-verified backups, fast-enough restore, and a traffic cutover workflow |
| Verification bar | Store consistency + counts/constraints + sample orders | Never count "files restored" as service recovery |
| Scope | `orders` graph + service accounts + downstream connectors | Must verify privileges, drivers, and CDC/event integrations |

**RPO and RTO are targets, not automatic guarantees from setting a schedule.** Failed backups, a missing differential link, slow object-storage downloads, or unrehearsed restores can all produce far worse actuals.

### 3.2. Illustrative Timeline

```text
10:00    10:15    10:30    10:42       10:50
  |---------|--------|---------|-----------|
 FULL       DIFF     DIFF    Accidental   Detected
                              deletion
                             10:42:17
                                  |
                         Clean recovery target:
                            before 10:42:17
```

With a full/differential chain holding sufficient transaction logs, Enterprise can restore to an exact timestamp or transaction ID. **Never blindly pick the "newest backup"**: for an accidental deletion at 10:42, a later backup already containing that deletion is not the safest recovery point.

When restoring by timestamp, convert to **UTC** as required by `--restore-until`. If an incident is logged in Vietnam time (UTC+07), convert zones before picking the target. Both timestamp and transaction-ID recovery apply an **exclusive** boundary per documentation: only transactions committed **before** the specified timestamp or transaction ID are applied.

## 4. Available Tools by Edition and Environment

| Environment | Creating backups | Restoring/checking | Conditions |
| --- | --- | --- | --- |
| **Self-managed Neo4j Community** | `neo4j-admin database dump` while DBMS is offline | `neo4j-admin database load` while DBMS is offline; `neo4j-admin database check` offline | Lacks Enterprise online backup/differential backup |
| **Self-managed Neo4j Enterprise** | `neo4j-admin database backup` while DB is online (full/differential); `dump` offline | `restore`, `load`, `backup aggregate`, `database check` | Backup service, file permissions, compatible versions, and standalone/cluster procedures |
| **Enterprise cluster** | Online backup from an eligible server (dedicated backup client recommended) | Cluster-appropriate URI/seeder/recreate/copy workflows | **Never overwrite destination files directly on a cluster** like standalone |
| **Neo4j AuraDB** | Service-managed snapshots/backups per tier | Restore/export/create from snapshot or backup via authorized Aura Console/API | Cannot run `neo4j-admin database backup/restore` directly inside Aura |
| **Composite databases** | Back up **constituent databases** | Check/restore each constituent and related config | Admin backup/check commands do not apply directly to composite databases |

In AuraDB, capabilities and retention **vary by tier**. Per current Aura documentation:
- **Free:** no automated scheduled snapshots like paid tiers.
- **Professional:** typically daily full snapshots, retention per tier policy.
- **Business Critical:** more frequent full and differential snapshots.
- **Virtual Dedicated Cloud:** detailed policy depends on version line and service plan.

Do not rely on outdated retention tables to assume data is definitely still recoverable. **Inspect available restore points directly in the Aura Console** before committing to an RPO.

### 4.1. Distinguishing `backup/restore` from `dump/load`

**Enterprise online backup**:
- Supports full and differential modes.
- Produces backup artifacts with metadata such as database ID, timestamp, and transaction ID range.
- Can use `--restore-until` when the transaction log chain covers the desired recovery point.
- May require `aggregate` to merge the chain and prepare for consistency checking.

**Offline dump**:
- Produces an archive of a database stopped and dumped at a point in time.
- Fits Community Edition or planned maintenance windows, yet does not build a full+differential chain for arbitrary PITR replay.
- **Does not automatically include user/role metadata** like Enterprise backups with metadata options.

**Never copy `data/databases/<name>` and `data/transactions/<name>` via raw copy/paste while the database is running** and call it a valid backup. Neo4j does not support this as a backup substitute; it can yield inconsistent data.

## 5. Time-Boxed Incident Response Runbook

### 5.1. Minutes 0–5: Confirm and Stop Blast Radius Expansion

1. Record **Incident ID**, incident commander, detection timestamp, and affected services.
2. Identify the symptom: wrong reads, write errors, database `OFFLINE`, lost storage, single member down, or total cluster loss.
3. **Stop the faulty writer**: disable the offending job/script, block mutating APIs, put the application in maintenance mode if needed.
4. If intrusion is suspected, execute security protocol: isolate credentials, pause suspicious integrations, protect clean backups.
5. Pause automated jobs that could **delete, overwrite, or prune backups** during investigation.
6. **Never run restore/load/import or delete transaction logs** before knowing the target database and desired recovery point.

Stopping writes at the **application source** can be safer than merely shutting down one Neo4j cluster member; in a cluster, other members continue accepting writes. The incident commander must establish clear cutover boundaries.

### 5.2. Minutes 5–20: Gather Evidence and Set Recovery Boundaries

Collect at minimum:

| Source | What to record |
| --- | --- |
| App logs/tracing | Which request/job caused the mutation, timestamp, and correlation ID |
| Neo4j query/security logs | Involved Cypher/actor/transaction, pulling only authorized logs |
| Neo4j debug/neo4j logs | Startup errors, transaction logs, indexes, storage, and cluster events |
| OS/storage | Disk errors, filesystem alerts, OOMs, volume detachments, free disk |
| Cluster health | Which members are `ONLINE`, leader, lag, routing, replication |
| Backup inventory | Full/differential artifacts, checksums, timestamps, IDs, access rights |
| Business data | Order totals, line totals, high-water marks, event/outbox sources, keys |

To preserve forensic evidence, take infrastructure snapshots or copies **following procedures supported by operations/storage**, on isolated systems where necessary. **Filesystem snapshots do not automatically substitute for consistent Neo4j backups**; using one for recovery requires proving validity through verification.

### 5.3. Minutes 20–45: Decide the Resolution Branch

```text
Incident confirmed
        |
        +-- Only app/query bug, database healthy?
        |     +-- Yes --> stop faulty source, repair data via business workflow
        |
        +-- Only one cluster member failed, others healthy?
        |     +-- Yes --> failover/reseed runbook, check quorum and lag
        |
        +-- Store/log corrupt, database unusable?
        |     +-- Yes --> isolate, inspect copies, prepare clean restore
        |
        +-- Accidental deletion committed/replicated?
              +-- Yes --> choose clean recovery point,
                          assess loss of subsequent valid writes,
                          restore in an isolated environment
```

Which branch to take must rely on evidence and RPO/RTO targets. **Restoring the entire database when only one node or one transaction was wrong** can discard many valid transactions committed after the incident. Sometimes standing up a restored copy to diff and run reviewed repair queries is better; that approach still requires idempotency and business-boundary checks.

## 6. Investigating Database State Without Modifying Data

### 6.1. Check DBMS Status

Connect to the `system` database with an authorized admin account and check:

```cypher
SHOW DATABASES;
```

When inspecting a single database:

```cypher
SHOW DATABASE orders;
```

This reveals current/requested status and error messages if the DBMS is still reachable. It does not verify the integrity of every store record. If connections fail, gather logs from the host/pod and storage layer before deciding next steps.

### 6.2. Avoid Generating Extra Business Transactions

During investigation mode:
- Never run `CREATE`/`MERGE`/`SET`/`DELETE` to "test if the database works."
- Never run `PROFILE` on a write query; `PROFILE` **actually executes the query**.
- Never run `DROP INDEX` or delete index folders to "fix" corruption before knowing the scope of corruption.
- Never manually edit binary store contents or delete/rename transaction logs.
- Never run Neo4j Admin commands on stores currently in use by the DBMS when the tool requires offline access.

Pause Spring/Java jobs writing to the graph, including retries or CDC consumers capable of mutating data. If read verification is needed, use a read-only account and bounded queries.

### 6.3. Index Errors vs. Store Errors

Not every `Index ... FAILED` message means nodes/relationships are corrupt. Conversely, an `ONLINE` index does not prove the entire graph is error-free. Cross-check:
- Whether the database is `ONLINE`.
- `SHOW INDEXES` and index/constraint states.
- Neo4j logs and storage/transaction errors.
- `neo4j-admin database check` on an eligible **unused** store or archive.

**Never "fix" a failed index by dropping and recreating it until underlying disk or store faults are ruled out.**

## 7. Verifying Consistency with `neo4j-admin database check`

This tool inspects graph structure, relationships, properties, counts, and indexes per selected flags. It **cannot run on a live database in use**, so stop the database or inspect a **recovered backup artifact**.

### 7.1. Checking an Offline Database

Example **only on a stopped lab database**:

```bash
bin/neo4j-admin database check \
  --report-path=/srv/recovery-reports \
  orders_drill
```

Results:
- Exit code **0** and no error report: the requested checks detected no inconsistencies.
- **Non-zero** exit code and an `inconsistencies-....report` file: preserve, read, and investigate the report.
- If the command runs out of RAM/temp disk: that is a check failure, **not proof of a clean store**.

You can tune `--max-off-heap-memory`, `--threads`, and specific check flags for large datasets, yet **never disable hard checks and then declare a full integrity PASS**.

### 7.2. Checking a Backup/Dump Artifact

For a `.dump` or **recovered full backup**:

```bash
bin/neo4j-admin database check \
  --from-path=/srv/recovery/checked-archive/ \
  --report-path=/srv/recovery-reports \
  orders
```

**Limitation:** the tool cannot check a standalone differential backup or an **unrecovered** full backup directly. Run `neo4j-admin backup aggregate` to produce a full backup with replayed transaction logs before checking. When `--from-path` points to a directory, the tool may pick the **latest chain**; when targeting one exact copy, specify the artifact on supported versions. Never let tests accidentally check a backup from the wrong day.

### 7.3. Store Consistency Does Not Equal Business Data Correctness

The consistency checker can report clean results while:
- Every node of a tenant was deleted by a **valid** transaction.
- Relationships link wrong endpoints due to an app bug while storage remains structurally valid.
- Orders show `status = 'PAID'` with zero line items.
- Transactions committed after the recovery point are absent.

Therefore, **consistency PASS is only one acceptance gate**; pair it with schema, counts, business constraints, and upstream source reconciliation.

## 8. Verifying the Backup Chain Before Choosing a Recovery Point

### 8.1. Enterprise Backups: Full and Differential

Enterprise online backups can produce:
- **Full backup**: the base data anchor.
- **Differential backup**: subsequent deltas/transaction logs; depends on an intact parent chain.
- **Aggregated backup**: a full artifact with chain transaction logs already applied to cut restore-time replay cost.

Diagram:

```text
Full F0  ----> DIFF D1 ----> DIFF D2 ----> DIFF D3
  |             |              |             |
  +-------------+--------------+-------------+
           Valid chain requires all links
                             |
                      backup aggregate
                             |
                      Full recovered F3
                             |
                     database check/restore
```

You cannot guarantee recoverability merely because `D3.backup` exists; the full base and intermediate transaction logs are also required. A "every 15 minutes" backup schedule helps RPO only if **every run succeeds, artifacts stay secure, chains remain readable, and restores are tested**.

### 8.2. Inspecting Metadata with `inspect`

```bash
bin/neo4j-admin backup inspect \
  /srv/neo4j-backups/orders-2026-11-25T03-30-00.backup
```

**The filename above is illustrative.** `backup inspect` displays database name, database ID, UTC timestamp, full/differential status, lowest/highest transaction IDs, and recovered status. This clarifies:
- Which database the backup belongs to.
- Whether the `.backup` file is the intended link.
- Which transaction range the backup covers.
- Whether aggregate/recovery is needed before checking.

If command paths or options shift across versions, run `bin/neo4j-admin backup inspect --help` on your actual Neo4j installation to confirm.

### 8.3. Aggregating Without Destroying the Drill's Original Chain

Example on a **lab-dedicated copy of backups**:

```bash
bin/neo4j-admin backup aggregate \
  --from-path=/srv/recovery/backup-chain \
  --keep-old-backup=true \
  orders
```

`--keep-old-backup=true` preserves the source chain during aggregation. By default the command may prune/remove old artifacts after merging; therefore, **never run it on production backup folders during an investigation** unless retention policy and owners explicitly authorize it.

Starting in Neo4j 2025.01, the modern command syntax is `neo4j-admin backup aggregate`; the older `neo4j-admin database aggregate-backup` is deprecated.

## 9. Enterprise Online Backup Example for Drill Data

The command below illustrates **taking a backup before an incident occurs**, not repairing an already corrupt store:

```bash
bin/neo4j-admin database backup \
  --from=127.0.0.1:6362 \
  --to-path=/srv/neo4j-backups \
  --type=FULL \
  orders
```

Prerequisites:
- Neo4j Enterprise supporting online backup.
- Backup service configured with appropriate firewalls, TLS, and permissions. `127.0.0.1:6362` applies only locally or with a matching listener; remote backup clients must use an authorized address.
- Backup directory has proper permissions, sufficient disk, and no shared failure point with source data.
- Command runs under an identity with appropriate filesystem permissions, typically the `neo4j` user.
- In a cluster, you can specify multiple backup server addresses per docs to reduce risk if one member is unavailable.

For automated schedules after a full, `--type=AUTO` selects full/differential based on chain state. Specifying `--type=DIFF` requires understanding your chain and retained transaction logs. Starting in Neo4j 2026.02+, full and differential cadences can be scheduled independently; you must still measure **actual RPO and actual aggregate/restore duration**, not just configure cron.

**Never put backups and source data on the same disk** and expect to survive volume loss. Use off-host/cross-AZ storage as appropriate, isolated permissions, retention, and periodic download checks.

## 10. Enterprise Restore Drill into a New Database

### 10.1. Choose an Isolated Environment and Non-Production Target Name

Assumptions:
- Source database: `orders`.
- Valid backup artifact copied to lab path: `/srv/recovery/orders-clean.backup`.
- Drill Neo4j Enterprise instance is version-compatible with the backup.
- Target database **`orders_drill` does not exist yet**.
- Backup file actually contains a recovered full artifact or an intact restorable chain.

**Do not use `--overwrite-destination` in this example.** Choosing a new database name reduces the risk of wiping active data.

### 10.2. Check Help and Execute Restore

```bash
bin/neo4j-admin database restore --help
```

```bash
bin/neo4j-admin database restore \
  --from-path=/srv/recovery/orders-clean.backup \
  --temp-path=/srv/recovery/tmp \
  orders_drill
```

Here:
- `--from-path` can point to a specific backup artifact or a backup directory/chain.
- `--temp-path` specifies a **staging directory with ample free space**, especially when replaying logs; it must meet the tool's emptiness/permission requirements.
- `orders_drill` is the new target database name.
- Do not let applications connect or write to this target until checks complete.

The restore command needs permissions on Neo4j's data/transaction-log directories and must run where the target store is accessible. **Restoring from a newer Neo4j version to an older Neo4j version is unsupported**; verify the version/format compatibility matrix before restoring.

### 10.3. Offline Check Before Opening the Database

While `orders_drill` is not yet registered/mounted, run:

```bash
bin/neo4j-admin database check \
  --report-path=/srv/recovery-reports \
  orders_drill
```

If the consistency check detects errors, **do not declare the database recovered**. Log the output under the incident ID and either select another artifact/chain or escalate to Neo4j Support. Never ignore errors simply because a REST API responds.

### 10.4. Register the Database in the DBMS and Verify Status

Connect to `system` with admin rights on the **drill instance** and run:

```cypher
CREATE DATABASE orders_drill;
```

Check:

```cypher
SHOW DATABASE orders_drill;
```

Proceed only once the database is `ONLINE`. If the restored copy uses a new DB name, the Java Driver must target `orders_drill`; never point production frontends at it before approved cutover time.

**Restoring a database from a data backup does not automatically populate users/roles.** RBAC metadata must be restored/reapplied separately where needed; see Section 16.

## 11. Point-in-Time Recovery (PITR) Drill for Accidental Deletion

Typical incident:
- 03:15 UTC: a Cypher job accidentally deletes `PLACED` relationships.
- 03:20 UTC: the incident is detected.
- A prior full backup and differential/transaction logs **covering up to before the incident** exist.

To restore to before 03:15 UTC, use the selected backup chain and `--restore-until`:

```bash
bin/neo4j-admin database restore \
  --from-path=/srv/recovery/backup-chain/orders-last-diff.backup \
  --restore-until="2026-11-25 03:15:00" \
  --temp-path=/srv/recovery/tmp \
  orders_pitr_drill
```

**The filename and timestamp above are illustrative**, not existing artifacts.

Semantics:
- Timestamps must be **UTC**.
- Only transactions with commit times **before** the timestamp are applied.
- With a transaction ID: `--restore-until=12345` restores up to **before transaction 12345**.
- Requires a chain holding the corresponding transaction logs; you cannot conjure lost transactions by picking an arbitrary timestamp.
- If a single transaction deleted data and also updated multiple other entities, PITR excludes **that entire transaction**, not individual statements inside it.

### 11.1. Assessing Valid Writes Lost After the PITR Cutoff

PITR restores the graph to a clean pre-deletion state, yet **also discards valid writes committed after that point**. For example:

| Transaction | Timestamp | Nature | Under PITR to 03:15 UTC |
| --- | --- | --- | --- |
| T100 | 03:14:40 | Valid order | Kept |
| T101 | 03:15:01 | Accidental delete | Excluded |
| T102 | 03:15:30 | Another valid payment | Also excluded |
| T103 | 03:16:00 | Valid inventory update | Also excluded |

Therefore, the runbook must compile a **list of post-cutoff transactions** and reconcile them from authoritative business sources (outbox, event logs, payment systems, CDC, or audits) using **idempotent, reconciled** mechanisms. Never blindly replay all old commands, especially payment or notification calls with external side effects outside Neo4j.

If only a few nodes were damaged, you can stand up `orders_pitr_drill` to **compare** old vs. current data and write reviewed repair queries instead of rolling the entire service back to an older snapshot.

## 12. Recovering via `dump/load` Without Online Backups

### 12.1. Creating a Dump While the Database Is Offline

On Neo4j Community or an environment with planned downtime, for example:

```bash
bin/neo4j-admin database dump \
  neo4j \
  --to-path=/srv/dumps
```

Key requirements:
- Target database must be **offline/not mounted in use**.
- Community requires the DBMS to be offline for dump/load operations per docs.
- `/srv/dumps` must exist with proper permissions, never world-readable/world-executable.
- Dumps **exclude user/role metadata**; back up/reconstruct those separately per edition.
- This is a **point-in-time data archive at dump time**, not a differential chain for PITR.

### 12.2. Loading from a Dump in a Community Environment

Example on an **isolated, stopped Community instance with a matching default target database**:

```bash
bin/neo4j-admin database load \
  --from-path=/srv/dumps \
  neo4j
```

Both commands above consistently target the `neo4j` database: dump packages `neo4j` and load reads the matching archive. If your real database or archive name differs, verify exact naming/path rules in `load` docs; **never rename files arbitrarily and assume metadata remains compatible**.

To replace an **existing database** in an isolated drill, `load` requires the database to be stopped plus `--overwrite-destination=true`. Because that **can wipe destination data**, it is omitted from direct run examples. After loading, start the DBMS or register the database per edition and verify.

### 12.3. Using Enterprise When You Only Have a `.dump` File

`neo4j-admin database load` reads archives from `database dump`, and under certain conditions can read an Enterprise **full backup artifact**. However, **never use `load` to replace timestamp-based restoration of a differential chain**. When PITR is required, use `database restore` with an intact chain containing transaction logs under supported conditions.

## 13. Cluster Procedures: Failover Does Not Equal Restore

In a Neo4j Enterprise cluster, the first question is **whether the fault affects only one server or already corrupted the replicated/consensus graph state**.

### 13.1. One Member Fails, Other Members Hold Valid Data

Typically:
1. Check quorum and member statuses.
2. Confirm applications use `neo4j://` or `neo4j+s://` routing URIs and Drivers can refresh routing tables.
3. Isolate the failed member; prevent it from writing to untrusted stores.
4. Restore availability via the **add-member/reseed database workflow** for your exact version and topology.
5. Check transaction lag, leadership, read/write routing, and latency after resynchronization.

**Never blindly restore an old backup onto a failed member and let it rejoin the cluster.** Clusters maintain consensus state and dedicated metadata; improper restoration can make databases inconsistent.

### 13.2. The Entire Cluster Applied an Accidental Deletion Transaction

Replication will not "undo" this transaction: healthy members have likely all applied it. In that case:
- Stop the faulty writer across applications/systems.
- Select a clean recovery point from an independent backup.
- Follow official procedures for **restore into a new database**, **URI-based restore**, **designated seeder**, or `dbms.recreateDatabase()` as documented.
- Never run `neo4j-admin database restore --overwrite-destination` over an existing cluster database; Neo4j docs warn this is **unsafe** because extra cluster state may become incompatible.
- Verify routing, privileges, apps, and CDC before switching traffic.

In distributed topologies, the recovery timestamp, source of truth, and per-database restoration must be coordinated by the incident commander. Never `scp` one store directory across every member as a shortcut to rebuild a cluster.

### 13.3. Newer Version Capabilities

Starting in Neo4j 2026.03+, `neo4j-admin database copy` was added to recovery options from backups and can assist certain inconsistency-cleanup/space-reclamation workflows. **Never treat `copy` as magic that recovers data already missing from every backup**; it has distinct edition/version requirements, setup steps, and scope compared to `restore`.

## 14. AuraDB: Operating via Managed Snapshots/Backups

On AuraDB, users do not manage filesystems directly or run `neo4j-admin database restore` on service hosts. Valid workflow:

1. Open the **Aura Console** and identify the affected instance/database.
2. Check **Snapshots** (single-user-DB instances) or **Backups** (multi-DB instances) along with tier, retention, and available timestamps.
3. Choose a clean point prior to the incident; note the difference between **restoring into the existing instance** vs. **creating a new instance from a snapshot/export**.
4. Prefer **creating a separate recovery instance** for verification where tier/service permits.
5. Run business, schema, and privilege checks, then switch endpoints/credentials and traffic per change plan.
6. If overwriting the running instance, explicitly confirm **overwriting existing data** and which recent changes will be lost.
7. On multi-database instances, **instance-wide restore points** may apply; check per-database behavior, because Aura docs warn databases lacking a corresponding backup at the chosen timestamp may be **wiped clean** during an instance restore.

For downloaded backups/snapshots or `.dump/.backup` files, verify exact tier export/restore capabilities. **Never assume Aura supports loading split archives**: current docs state restoring from 2026.09 split backup archives is **not yet supported** on Aura.

### A Decision Example

An AuraDB Professional instance suffers an accidental deletion at 15:00, yet the latest available snapshot is from 00:00:
- You cannot assume 14:59 PITR exists just because self-hosted Neo4j Enterprise has `--restore-until`.
- Restoring the 00:00 snapshot risks losing **15 hours** of valid transactions.
- Check retention and new-instance creation options, then decide whether selective recovery from upstream business sources is possible or whether data loss within the agreed RPO must be accepted.

## 15. Verifying Graph Data Post-Restore: Three Testing Tiers

Successful file restoration only proves **the command finished**, not that the graph is fit for business use. Run checks in order.

### 15.1. Tier 1: Store and Database Health

- `neo4j-admin database check` on a stopped database or recovered artifact, saving exit code and report.
- Database boots `ONLINE`.
- No storage/index/transaction errors in fresh logs.
- `SHOW INDEXES`: required indexes are `ONLINE`; `SHOW CONSTRAINTS` shows expected structures.
- Verify version/edition, APOC/GDS plugin compatibility, and auth metadata where needed.

Example once `orders_drill` is online:

```cypher
SHOW INDEXES
YIELD name, type, state
RETURN name, type, state
ORDER BY name;
```

```cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
```

### 15.2. Tier 2: Counts and Business Integrity

Suppose the graph has:
- `(:Customer {customerId, tenantId})`.
- `(:Order {orderId, tenantId, status})`.
- `(:Customer)-[:PLACED]->(:Order)`.
- `(:Order)-[:HAS_LINE]->(:Product)`.

Verify counts:

```cypher
MATCH (o:Order)
RETURN count(o) AS orders;
```

```cypher
MATCH ()-[r:PLACED]->()
RETURN count(r) AS placedRelationships;
```

```cypher
MATCH ()-[r:HAS_LINE]->()
RETURN count(r) AS orderLines;
```

Verify relationships and tenants (assuming one customer owns each order):

```cypher
MATCH (o:Order)
WHERE NOT EXISTS {
  MATCH (:Customer)-[:PLACED]->(o)
}
RETURN count(o) AS ordersWithoutOwner;
```

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE c.tenantId <> o.tenantId
RETURN count(*) AS crossTenantOrderLinks;
```

If your model allows guest orders or cross-tenant workflows, **adjust acceptance rules to fit the domain**; do not automatically assume every non-zero count is corruption.

Reconcile against:
- Recoverable order counts and latest transaction ID.
- Payment/ERP/order event logs as independent sources of truth.
- Key canary customer/order IDs.
- Data changed right around incident time.

### 15.3. Tier 3: Real Application Behavior

- Java Driver connects to the restored database using the exact URI/database name.
- Read queries for DTOs and traversals return expected results.
- Spring Data Neo4j entity mapping works without errors from missing properties/relationships.
- Indexes/constraints and roles align; users read/write strictly within granted rights.
- `EXPLAIN`/`PROFILE` on controlled datasets show no anomalous plans.
- No webhooks, CDC, or event consumers fire spurious events as the service comes up.
- Tenant data cannot leak through an endpoint meant to enforce ownership.

### 15.4. Read-Only Java Driver Smoke Test

The Java snippet below assumes an **already-created Driver** targeting test database `orders_drill`:

```java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

static long countRecoveredOrders(Driver driver) {
    try (Session session = driver.session(
            SessionConfig.forDatabase("orders_drill"))) {

        return session.executeRead(tx ->
            tx.run("""
                MATCH (o:Order)
                RETURN count(o) AS total
                """)
              .single()
              .get("total")
              .asLong()
        );
    }
}
```

This is a count smoke test—**not sufficient to replace consistency checks or transaction reconciliation**. Never let production APIs automatically "patch missing counts" before the root cause is verified.

## 16. RBAC, the `system` Database, and Downstream Systems: Easily Forgotten Items

### 16.1. User/Role Metadata

Enterprise backups may include user/role metadata in the artifact depending on `--include-metadata` (typically included by default). However, **restoring data does not automatically apply all roles/users into `system`**.

Per Enterprise restore docs, the process can generate a `restore_metadata.cypher` script. To restore RBAC, **operators must intentionally review and execute it** against `system` with proper privileges after checking policies/name collisions without exposing credentials.

`neo4j-admin database dump` **contains no user/role metadata**. In Community Edition, access management differs from Enterprise; in multi-database Enterprise, plan backups for `system` too while recognizing that restoring `system` affects DBMS identities and control.

### 16.2. CDC, Kafka/Outbox, and External Systems

Restoring or loading a database alters graph state by replacing the store, **not by re-emitting individual events like live write transactions**. Per docs, Neo4j CDC does not capture changes introduced by `neo4j-admin database load`.

If downstream consumers already processed pre-incident events:
- Consumers may hold **offsets/bookmarks/change identifiers** no longer matching the graph after PITR.
- Valid writes after the recovery point may already have reached Kafka, payment gateways, or external systems.
- Restarting producers after restore can emit duplicate, missing, or out-of-order events.

Build a **reconciliation/snapshot rebuild** plan rather than expecting restoring Neo4j alone to rewind the entire distributed system to one unified instant.

### 16.3. Backups Must Be Independent of Compromised Credentials

Backups cannot stop ransomware if a compromised account can delete the backups too. Policies should enforce:
- Off-site storage, retention, and **immutable/object-lock** capabilities where supported.
- Backup credentials separated from application credentials.
- Encryption at rest and in transit, restricted access, and audit logs.
- Scheduled real download/read tests.
- Fallback access to backups if the primary control plane or IdP fails.

## 17. Cutover Approval and Rollback

Before cutting traffic over to the restored database, require a **go/no-go checklist**:

| Acceptance gate | Evidence | Owner |
| --- | --- | --- |
| Exact recovery point | Artifact/database ID, tx IDs, UTC timestamp | Database operator |
| Consistent store | Clean check report, error-free startup | DBA/SRE |
| Schema ready | Indexes `ONLINE`, constraints valid | DBA/Dev |
| Accurate data | Counts, canary keys, relationships, tenant invariants | Data/Business owner |
| Downstream synced | CDC/Kafka/payment/ERP reconciliation plan | Integration owner |
| App functional | Java Driver/SDN smoke tests, controlled read/write | Application owner |
| Security | Roles, secrets, certificates, network policies | Security |
| Operational stability | p95/p99, error rate, disk/CPU/heap, fresh backups active | SRE |
| Clear rollback | Pre-cutover state remains preserved | Incident commander |

**Suggested cutover sequence:**

1. Keep the service in maintenance/no-write mode.
2. Drain/close old connections and queues per app strategy; prevent retries from writing to the wrong target database.
3. Update database name/URI/routing config via controlled deployment.
4. Run end-to-end tests with test accounts, then open read traffic.
5. Open write traffic only after confirming duplicate-prevention logic and downstream reconciliation.
6. Monitor metrics and logs in real time; record traffic-reopen timestamp.
7. If critical failures appear, halt writes and **fall back to the pre-planned contingency**—never blindly flip DNS back to the old database if data diverged after cutover.

Rollback is not always just "reverting the old URL." If the restored copy and old system received **different transactions**, switching back without reconciliation can permanently split business data.

## 18. Periodic Drill Plan: Recovery Must Be Proven

A backup with exit code 0 is a **created backup**, not yet a **backup proven able to restore within RTO/RPO**. Organizations should drill under realistic failure conditions.

| Drill | Objective | Evidence to retain |
| --- | --- | --- |
| **D1: Standalone DB loss** | Restore full backup onto a new instance | Restore duration, check report, business smoke results |
| **D2: Corrupt differential** | Select intact chain and quantify RPO impact | Chain files/metadata, achieved recovery point |
| **D3: Accidental delete tx** | PITR before deletion; handle subsequent valid writes | Tx boundary, comparison data, reconciliation sheet |
| **D4: Cluster member loss** | Failover/reseed with zero committed data loss | Quorum/lag, driver routing, downtime |
| **D5: Volume/zone loss** | Restore from backup outside the failed zone | Backup reachability, actual RTO, checksums |
| **D6: Aura restore** | Pick right snapshot/tier, spin up test instance | Creation time, data/role verification, cost |
| **D7: Backup creds revoked** | Test break-glass backup access | Access recovery time, audit logs, recoverability |
| **D8: Downstream mismatch** | Re-sync Kafka/ERP/CDC | Offsets, reconciled order counts, duplicates/gaps |

### 18.1. Drill Scoring Criteria

Measure independently:
- **Actual recovery point** vs. incident time (actual data loss window).
- **Detection time** and runbook activation time.
- **Artifact retrieval time** from storage, decompression/log replay, and `database check`.
- **Time for indexes/constraints and application** to stabilize.
- **Total outage duration of core functions** vs. RTO.
- **Count of valid post-checkpoint transactions** requiring replay/backfill.
- **Test pass rate**, verified canary keys, and remaining privilege/CDC gaps.
- Resource cost, storage bandwidth, and impact if drilled near production.

### 18.2. Sample Drill Record

```yaml
drillId: neo4j-orders-restore-2026-11-25
sourceDatabase: orders
targetDatabase: orders_drill
scenario: accidental-delete-before-cutover
environment: isolated-staging
neo4jVersion: "<record actual version>"
backupArtifact: "<verified artifact path/ID>"
recoveryTargetUtc: "2026-11-25 03:15:00"
rpoTargetMinutes: 15
rtoTargetMinutes: 90
actualDataLossMinutes: null
actualRecoveryMinutes: null
consistencyCheck: NOT_RUN
businessValidation: NOT_RUN
securityValidation: NOT_RUN
downstreamReconciliation: NOT_RUN
approvedForCutover: false
```

This is a **record template**, not a mandatory file and not proof a drill already ran. In a real drill, replace `null`/`NOT_RUN` with actual measurements, and archive logs, checksums, and approval sign-offs in your incident management system.

## 19. Mistakes That Make Incidents Worse

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Deleting transaction logs upon seeing storage errors | Loses transaction recovery options, may worsen store corruption | Isolate, collect logs, preserve evidence, follow runbook |
| Copy/pasting a running database folder | Store may be inconsistent | Use supported backup/dump/snapshot mechanisms |
| Restoring the "latest backup" after accidental deletion | Backup may already contain the faulty delete transaction | Pick a clean recovery point by timestamp/tx ID |
| Checking only restore exit code | Misses corruption or business-data errors | Offline consistency + index/schema + business reconciliation |
| Running check on a mounted database | Unsupported by tool, risks mishandling | Stop the database or check an eligible artifact |
| Checking a single differential as if it were full | Cannot validate the entire chain | Aggregate/recover the chain first |
| Adding `--overwrite-destination` to "make it run" | Wipes target data, especially dangerous in clusters | Restore to a new database/follow cluster procedures |
| Entering local time into PITR without converting to UTC | Restores wrong point, drops valid transactions | Verify timezone and commit boundaries |
| Treating replication as backup | Accidental deletions propagate to every member | Maintain independent off-site backups |
| Opening write traffic right after restore | Writes onto unreconciled state | Multi-layer acceptance gates and controlled cutover |
| Forgetting `system`/role metadata | App loses permissions or gets over-privileged | Manage auth metadata and test roles |
| Restoring Neo4j only, forgetting Kafka/CDC/payments | Causes duplicate or missing events | Plan reconciliation/idempotency |
| Never testing cloud backup downloads | RTO blown by slow downloads or missing permissions | Drill download, staging, and disk sizing |
| Measuring RTO only until file restore finishes | App still broken, indexes still populating | Measure until service meets operational readiness |
| Keeping backups on the same failing volume | Backups are lost together with primary data | Separate failure domains, retention, and permissions |
| Rolling back after both sides took diverging writes | Business data split-brain | Stop writes and reconcile before switching back |

## 20. Practice Exercises

1. A three-member cluster loses one member's disk while the other two stay healthy. Explain how to decide between failover/reseed vs. restoring from an older backup.
2. An accidental `DETACH DELETE` runs at 10:42:17 (`Asia/Ho_Chi_Minh`). Compute the UTC timestamp to pass to PITR to exclude that transaction. Explain why you must target **before commit**, not merely detection time.
3. A chain `Full F0 → Diff D1 → D2 → D3` loses `D2`. Analyze whether `D3` can be used and how to pick a clean recovery point.
4. Design the command sequence to inspect metadata (`backup inspect`), aggregate, run offline check, and restore into `orders_drill`. Point out which commands must never run on a live database in use.
5. Why does `neo4j-admin database check` returning PASS still fail to prove an accidentally deleted order came back?
6. Write two Cypher queries checking total `Order` count and `Order` nodes missing a `PLACED` relationship after restore.
7. An AuraDB Professional instance has a latest snapshot 20 hours old while business RPO is 15 minutes. Propose options and state clearly what **cannot be guaranteed by snapshots alone**.
8. A Java service already published a Kafka message for order `o400`, yet Neo4j was PITR-restored to before `o400`'s creation transaction. Design reconciliation steps to prevent duplicate orders or events.
9. Why does restoring a user database backup not mean every role/user in `system` is also restored?
10. Draft a go/no-go cutover checklist after restore covering versions, indexes, RBAC, CDC, latency, and rollback mechanics.
11. A Community instance needs restoration from a dump. State the offline preconditions and why Enterprise full/differential PITR chains cannot be used.
12. Design a drill scenario for "complete volume loss at 01:00 UTC" with a 30-minute RPO and 2-hour RTO: which timestamps and evidence are required?

## 21. Key Takeaways

- **Recovery must follow a rehearsed runbook**, starting by stopping the faulty source, preserving evidence, and locking a clean recovery point.
- **RPO measures potential data loss; RTO measures time to service restoration.** A cron schedule alone guarantees neither.
- **Clustering/failover addresses availability faults, not undoing replicated accidental deletions.**
- **Enterprise** provides online full/differential backups, restore, and PITR when transaction log chains allow; **Community** relies primarily on offline dump/load.
- `neo4j-admin database check` requires an offline database or eligible archive; **store consistency PASS alone is insufficient** to confirm business correctness.
- **Never delete logs, copy live stores, or arbitrarily overwrite cluster databases.** Restore into an isolated database/instance to verify first.
- **`--restore-until` timestamps are UTC and exclusive of the commit boundary**; PITR can discard valid writes committed after the chosen point.
- **AuraDB** uses service-managed snapshots/backups limited by tier; never apply self-hosted `neo4j-admin database restore` commands directly to Aura.
- Post-restore checks must cover **indexes, constraints, tenant/relationship integrity, user/role metadata, Java Driver, Spring Data Neo4j, and CDC/downstream systems**.
- Declare recovery complete only once **technical integrity, business reconciliation, security, and cutover checks** all pass.
- **Regular drills, measured actual RPO/RTO, and off-failure-domain backups** are what make a plan dependable during a real outage.

### Official References

- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Backup and restore planning](https://neo4j.com/docs/operations-manual/current/backup-restore/planning/)
- [Neo4j Operations Manual — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/)
- [Neo4j Operations Manual — Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual — Back up an offline database](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/)
- [Neo4j Operations Manual — Aggregate a database backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/)
- [Neo4j Operations Manual — Restore a database backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)
- [Neo4j Operations Manual — Restore a database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/)
- [Neo4j Operations Manual — Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Operations Manual — Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/)
- [Neo4j Operations Manual — Backup/restore in Kubernetes](https://neo4j.com/docs/operations-manual/current/kubernetes/operations/backup-restore/)
- [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/)
- [Neo4j Java Driver Manual — Query the database](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)

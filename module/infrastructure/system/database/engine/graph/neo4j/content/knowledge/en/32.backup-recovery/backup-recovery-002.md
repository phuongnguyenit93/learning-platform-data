# Setting RPO, RTO Targets, and Retention Policies for Neo4j

## 1. Backups Only Matter When Tied to Recoverability

In Neo4j, business data is stored as a **property graph** consisting of nodes, relationships, labels, and properties. For example, a project management service has `:AppUser` and `:Project` nodes connected by `:MEMBER_OF` relationships. An incident can lose or corrupt the database, leaving a Java/Spring Data Neo4j application unable to query the graph. **The mere existence of a backup file does not prove the system can recover within target deadlines.**

A backup policy must answer three **distinct** questions:

1. **RPO — Recovery Point Objective:** If an incident occurs, how much data-update time at most can the business tolerate losing?
2. **RTO — Recovery Time Objective:** From the start of the incident until the service is restored to its committed operational level, how long at most may it take?
3. **Retention — retention policy:** Which copies, for how long, and in what locations must remain available to support operations, error investigation, information security, and archival obligations?

These three metrics are related but **not interchangeable**. Backing up every 15 minutes does not mean restoring in 15 minutes; retaining copies for 90 days does not mean being able to restore to **every single moment** within those 90 days.

### 1.1. Distinguishing Targets from Measured Actuals

| Concept | Common unit | Example | What must be verified |
| --- | --- | --- | --- |
| **Target RPO** | minutes/hours | 15 minutes | The recoverable data point is no older than 15 minutes relative to the incident |
| **Actual RPO** | minutes/hours | 12 minutes | The timestamp of the last committed transaction **actually recovered** |
| **Target RTO** | minutes/hours | 2 hours | The service meets readiness criteria no later than 2 hours after the incident |
| **Actual RTO** | minutes/hours | 1 hour 38 minutes | Measured from incident start until application and data pass acceptance checks |
| **Retention** | days/months/years | 35 days | At least one valid copy chain satisfies the required recovery window |

**RPO = 0** means zero loss of committed transactions is acceptable. This is a very demanding target that typically requires additional architectural guarantees beyond periodic backups. **RTO = 0** means zero downtime is tolerated; a traditional restore workflow alone cannot promise that.

Neo4j clusters, replication, failover, backups, and disaster recovery are **different mechanisms**. Clustering improves availability when one server fails; backups help roll back to valid data after accidental deletion, software bugs, ransomware, or incidents affecting the whole cluster. **Replication can copy erroneous deletions as well**, so it does not replace an independent backup history.

## 2. How to Calculate and Verify RPO

### 2.1. A Concrete Timeline

Suppose a Neo4j source continuously receives transactions updating nodes and relationships:

```text
10:00         10:15         10:30         10:42
  |-------------|-------------|-------------X  Incident
  FULL       DIFF 1        DIFF 2
                              ^
                     Latest recovery point
```

If `DIFF 2` completed successfully, contains all transactions up to **10:30**, and the entire chain from FULL through DIFF 2 is usable, then:

```text
Actual RPO = 10:42 - 10:30 = 12 minutes
```

With a **15-minute target RPO**, this case passes. However, if DIFF 2 failed and you can only restore up to **10:15**, then:

```text
Actual RPO = 10:42 - 10:15 = 27 minutes  ->  Breaches 15-minute RPO
```

**Job execution time is not necessarily the data recovery point.** A job starting at 10:30 and finishing at 10:36 may only include transactions up to a point recorded in metadata. To assess RPO accurately, inspect the **last commit timestamp/transaction ID actually present in the backup chain**, not just file timestamps or cron schedules.

### 2.2. Relationship Between Backup Frequency and RPO

If a differential backup runs every 15 minutes, under ideal conditions the age of the recovery point at an arbitrary incident can reach **approximately 15 minutes**. In practice, there are also:

- Latency from scheduled trigger time until the backup actually captures transactions.
- Long-running jobs, timeouts, out-of-disk conditions, or unreachable backup endpoints.
- Loss of part of the **backup chain** or required transaction logs.
- Lack of timely alerts when the most recent backup fails.
- Clock/metadata skew making "recovery point" determination inaccurate.

Therefore, a 15-minute schedule is only a **necessary condition** for a 15-minute RPO, not a guarantee. To build a safety margin, schedule, monitor, and test recovery adequately to stay within threshold even under single-run delays or failures.

In particular, **copy count** does not determine RPO: having 100 old full backups still might not recover the last 5 minutes of data.

### 2.3. The Graph Must Be Consistent, Not Just Have Enough Nodes

An application may execute within a single transaction:

```cypher
MATCH (u:AppUser {userId: $userId})
MATCH (p:Project {projectId: $projectId})
MERGE (u)-[m:MEMBER_OF]->(p)
SET m.role = $role;
```

Upon recovery, you need data in a **transactionally consistent state**: nodes and relationships created/updated within commit boundaries, not store files patched together from mismatched points in time. Manually copying data files of a **running** database is not a safe Neo4j backup procedure, even if file sizes look right.

RPO must be applied to the **data the application actually owns**: if a Neo4j transaction committed but an external service (such as a search index or message broker) has not yet synchronized, plan to rebuild or backfill derived systems after restore.

## 3. RTO Is Service Recovery Time, Not Just File Restore Time

### 3.1. Practical Formula

One way to measure RTO from a business perspective:

```text
Actual RTO =
  incident detection and triage time
  + deciding recovery scope and target point
  + provisioning infrastructure, credentials, and backup access
  + downloading/restoring/replaying transaction logs
  + verifying data, schema, and access permissions
  + reconnecting applications and switching traffic
  + end-to-end readiness verification
```

Stages can overlap, so this sum is a **planning model**, not an exact measurement formula when two tasks run in parallel. During drills, measure from **the incident start time as defined in the SLA** until **the service meets acceptance criteria**, rather than stopping the clock when `neo4j-admin database restore` reports success.

### 3.2. Example 120-Minute Target RTO

| Stage | Example budget |
| --- | ---: |
| Incident detection, owner identification | 10 minutes |
| Isolate fault source, select recovery point | 15 minutes |
| Provision infrastructure/decryption keys/download copy | 15 minutes |
| Restore and replay backup chain | 45 minutes |
| Verify graph, schema, and permissions | 20 minutes |
| Application switchover/user verification | 15 minutes |
| **Total** | **120 minutes** |

This is an **illustrative budget**, not a Neo4j benchmark. If the graph is large, the network is slow, or the DIFF chain is long, the restore stage alone may exceed 45 minutes. You must **measure via restore drills** using representative data scale and realistic standby infrastructure.

### 3.3. Factors Governing RTO

- **Full backup size**, object storage/disk read speed, and network bandwidth.
- **Differential chain length** to replay; many deltas can prolong recovery.
- Time to provision new VMs, volumes, Kubernetes workloads, or clusters.
- Missing container images, certificates, secrets, or required config/index/schema definitions.
- Approval workflows for DNS/router/load-balancer changes and connection pool refreshes.
- Time to restore **other databases and the `system` database** if the application depends on RBAC or multi-database setups.
- Post-restore checks on Cypher queries, uniqueness constraints, Java Driver flows, and Spring Data Neo4j.

RTO can be improved via more frequent full backups, **aggregating** differential chains, pre-warmed standby infrastructure, fast-access backup storage, documented runbooks, and regular drills. You will not improve RTO simply by increasing DIFF frequency if the system lacks time to replay them.

## 4. Choosing RPO/RTO by Service Criticality

Before designing a backup schedule, ask the product owner and operations:

- What does losing 5 minutes of graph updates mean? Can events be replayed from an upstream source?
- While Neo4j is down, can the frontend serve cached reads or must transactions halt?
- After an accidental deletion incident, do users need to roll back to **yesterday** or to a point within **30 days**?
- What is the financial/business impact per hour of downtime and per minute of data loss?
- Are there regulatory requirements, customer contracts, or data deletion rights affecting retention?

Illustrative tiering table (**proposed for discussion**, not Neo4j defaults):

| Data/service tier | Target RPO | Target RTO | Initial approach |
| --- | --- | --- | --- |
| A — critical transactions | 15 minutes | 2 hours | Frequent online full+DIFF, short chains, practiced restore drills |
| B — internal systems | 4 hours | 8 hours | Per-shift or multi-times-daily online backups, reconciliation |
| C — rebuildable reporting data | 24 hours | 48 hours | Nightly full/offline backup or rebuild from source |

If Tier A requires **zero loss of any committed transaction**, a 15-minute DIFF schedule still **does not meet it**. In that case, you need additional design measures such as verified synchronous mechanisms, independently persisted event/outbox logs, or a DR architecture targeting near-real-time data durability; you must re-evaluate consistency and full-region failure scenarios, and never label a system "RPO=0" merely because it has a cluster.

Classify at the **database or dataset level** rather than applying one number to every environment. Production, staging, and reproducible datasets normally require different levels of protection.

## 5. How Neo4j Backup Mechanisms Directly Affect RPO/RTO

### 5.1. Comparing the Tools

| Tool | Edition/conditions | Characteristics | Impact on targets |
| --- | --- | --- | --- |
| `neo4j-admin database backup` | **Enterprise**, running database; not used directly on Aura | Online full or differential, produces `.backup` artifacts | Suits frequent schedules, shorter RPO |
| `neo4j-admin database dump` | Community and Enterprise; **offline** database | Entire database into a `.dump` archive | Requires downtime; only full snapshots at dump times |
| `neo4j-admin backup aggregate` | Enterprise | Merges full + differential chain into a recovered full backup | Reduces replay work during restore, helps RTO |
| `neo4j-admin database restore` | Enterprise | Restores from artifact/backup chain; can target timestamp/transaction ID | Requires target DB planning, intact chain, and post-restore checks |
| `neo4j-admin database load` | Community/Enterprise per conditions | Loads `.dump` or compatible full backup artifact | Suits recovery from a full archive, does not replace arbitrary PITR |
| **Aura snapshot/backup** | Managed service, per tier | Scheduled or on-demand; restore via console/API | Frequency, retention, and restore behavior depend on plan |

Do not treat Docker volume snapshots, raw copies of open files, or ad-hoc CSV exports as an **equivalent substitute** for a Neo4j consistent backup. CSV exports also risk missing labels, properties, relationships, schema, permissions, and transaction boundaries if exported without a unified procedure.

### 5.2. Full and Differential: Keep the Chain Intact

```text
F0 (full) --> D1 --> D2 --> D3 --> D4
              |      |      |      |
         tx log    tx log  tx log  tx log

To recover after D4 you need F0 and contiguous
transaction parts matching dependency links; missing one link
can make subsequent points unrecoverable.
```

A **Full** contains the database store at a consistent point. A **Differential** contains transaction logs needed to advance a full (or prior deltas) to a newer point. A backup chain consists of artifacts usable together based on **transaction IDs/metadata**, not simply files with similar names.

Starting in **Neo4j 2026.02**, Enterprise Edition better supports **independent** scheduling of full and differential backups: the first DIFF after a FULL can overlap transaction IDs with the prior full; subsequent differentials must still follow their parent contiguously. In older versions, interleaving a FULL between DIFFs could break the expected chain, so follow the documentation for your **exact version**. Never copy a newer schedule pattern onto an older Neo4j cluster without verifying.

Neo4j defaults to `--type=AUTO`: on the first run it can create a FULL, and on subsequent runs it can generate DIFFs based on the existing chain. For an explicit DIFF schedule using `--type=DIFF`, you must **seed a FULL first**; if required transaction logs are no longer available, a DIFF backup may fail or in AUTO mode fall back to a full depending on conditions/version.

### 5.3. Enterprise Online Backup Command Example — Run Only in Authorized Environments

Suppose an Enterprise server has the backup service securely enabled; a dedicated backup host reaches `10.30.0.11:6362` over a private network, and `/secure-backups/neo4j` is owned by the backup execution user:

```bash
# Run on the appropriate backup/client host; this is not a Cypher query.
# Paths, TLS policy, and resources must be configured beforehand.
bin/neo4j-admin database backup \
  --from=10.30.0.11:6362 \
  --to-path=/secure-backups/neo4j \
  --type=AUTO \
  neo4j
```

When the destination path does not yet have a chain, the first run can create a full backup. On later runs, AUTO picks the appropriate mode. For an independent full schedule:

```bash
bin/neo4j-admin database backup \
  --from=10.30.0.11:6362 \
  --to-path=/secure-backups/neo4j \
  --type=FULL \
  neo4j
```

**Do not run both schedules without checking version compatibility and chain structure first.** Backups must run under an OS user/role with appropriate permissions; the backup service needs proper configuration, a dedicated port restricted to authorized backup hosts, and TLS for network transit. Running from a dedicated host limits CPU/memory impact on cluster members.

With multiple databases, schedule backups for every **physical database**, including the `system` database when restoring users, roles, and operational metadata is required. You cannot back up a database alias as a physical database. Options such as `--include-metadata` control which RBAC metadata is packaged; backing up business data **does not automatically ensure all external configs, secrets, and certificates outside Neo4j are saved**.

### 5.4. Community Edition or Environments Requiring Database Stop

When Neo4j lacks Enterprise online backup, you can use **offline dump**:

```bash
# Run after the target database is stopped per operational procedures.
bin/neo4j-admin database dump neo4j \
  --to-path=/secure-backups/offline
```

`dump` contains only database data; **users/roles metadata is not included**. To restore the full service, prepare separate metadata/backups of the `system` database and related configs/secrets as appropriate for your edition. Because dump requires the database to be offline, systems requiring continuous writes must schedule downtime or choose another solution.

### 5.5. Point-in-Time Recovery (PITR) Is Not Available in All Modes

With a compatible Enterprise backup chain, restore supports `--restore-until` by **transaction ID** or **UTC timestamp** to replay up to the requested point. With a timestamp, transactions committed **before** that timestamp are recovered; with a transaction ID, boundary rules are documented per Neo4j version (the specified ID is **exclusive** in current documentation).

PITR does **not** mean you can restore to an arbitrary point if the required differential logs are missing. A single offline full `.dump` can only restore the state at dump time; it cannot replay history it does not contain.

An illustrative command for **reading syntax only—do not run on production**:

```bash
# Target is a new lab database that does not yet exist.
# Verify version, backup source, and permissions/paths before running.
bin/neo4j-admin database restore \
  --from-path=/secure-backups/neo4j \
  --source-database=neo4j \
  --restore-until="2026-11-20 10:30:00" \
  recovery_lab
```

The timestamp in `--restore-until` is **UTC**, not local Vietnam time. The command may require the target to be offline, data directory configuration, and running `CREATE DATABASE recovery_lab` in `system` after restore (when not replacing an existing database). Never add `--overwrite-destination` just to bypass errors: overwriting can destroy newer data and is **unsafe for clusters** per Neo4j guidance.

## 6. Retention Policies: What to Keep, For How Long, and Where?

### 6.1. Two Retention Goals Distinct from RPO

**Retention** answers "how far **back in time** can we return?"; RPO answers "when an incident happens, **how much recent data** will be lost?". For example:

- 15-minute RPO with 7-day retention: requires recovery points close enough to the incident **plus** usable chains across the 7-day window.
- 4-hour RPO with 90-day retention: you may still lose up to ~4 hours of recent data on failure, while keeping valid copies/points per policy for 90 days.
- Keeping a 90-day-old full backup does **not** mean you can restore to any single minute over 90 days; point granularity depends on the retained schedule and contiguous logs.

Therefore, a policy must specify **artifact retention**, **recovery point granularity**, and the **PITR window** if committed.

### 6.2. Grandfather–Father–Son (GFS) Pattern

A reference policy (must be reviewed against data, legal, and storage constraints):

| Tier | Retention duration | Purpose |
| --- | --- | --- |
| Most recent/daily copies | 14 days | Recover from recently detected errors or test upgrades |
| Weekly checkpoints | 8 weeks | Roll back prior to faulty data changes |
| Monthly checkpoints | 12 months | Support longer investigations as required |
| Special archives | Only with legal/business basis | Legal hold, audit, or industry compliance |

This is a **policy framework**, not a schedule sufficient to satisfy a 15-minute RPO. If a 15-minute RPO is required, alongside GFS checkpoints you must retain **continuous full/differential chains and transaction coverage** for all committed recovery points.

When designing a GFS schedule, do not just create 14+8+12 arbitrary files and assume retention is met. A "weekly checkpoint" is only useful if it can be restored via an **independent full** or a complete chain reaching that exact point.

### 6.3. Three Copies, Two Storage Types, One Off-Site

The **3-2-1** rule is a preventive implementation guideline:

1. Maintain more than one copy of the data, in addition to live production data.
2. Avoid a single point of failure across storage locations; consider two media/storage systems or independent fault domains.
3. Keep at least one copy **off-site** in a different region/location from the running DBMS.

Measures to strengthen protection against ransomware and accidental deletion:

- **Immutable/object-lock/WORM** storage for critical copies and appropriate retention periods. "Neo4j backup artifacts are immutable files" **does not automatically mean** a cloud bucket enforces delete/modify protection.
- Separate backup store credentials from database credentials and application runtime accounts. Prevent an attacker who compromises the database from deleting backups too.
- Encrypt data in transit and at rest, managing keys per policy; **never store decryption keys where an attacker who can delete backups can also reach them**.
- Never leave backup directories world-readable or world-executable; enforce OS permissions and cloud IAM controls.
- Restrict the backup port (typically `6362/TCP`) strictly to trusted backup clients/hosts. Use TLS for online backups over the network.
- Build a recovery plan that **does not depend on the same identities/permissions compromised during an incident**; securely store runbooks and emergency contacts.

### 6.4. Deleting Copies Safely: Do Not Break the Backup Chain

Example chain:

```text
F-01 (full)
  +-- D-01 (diff)
  +-- D-02 (diff)
  +-- D-03 (diff)

F-02 (independent full, restore-tested)
  +-- D-04
  +-- D-05
```

If you need to retain the point at D-03, **you cannot delete F-01 or its intermediate dependencies** while they are still needed for recovery. Only after confirming F-02 and the new chain cover the full desired retention window should you consider pruning the old chain **according to the backup dependency graph**, not merely by file age.

A valid deletion policy should:

1. Rely on **commit coverage dates** and chain metadata, not only filenames/timestamps.
2. Retain every parent full and differential log required to restore every promised point.
3. Verify that a newer chain **has restored successfully** before deleting the only older chain.
4. Honor object-locks, legal holds, and personal data erasure requests; balance retention duties with deletion obligations.
5. Log who approved the deletion, which artifacts were removed, which checkpoints remain, and remaining recoverability.

**Never blindly apply "delete all files older than 30 days"** to a directory containing FULL + DIFF files without verifying dependencies between them.

### 6.5. Sizing Storage Capacity So the Policy Is Feasible

Suppose each compressed full backup is 400 GiB, each day adds 25 GiB of differentials, and you keep two independent fulls plus 14 days of deltas. A rough estimate:

```text
2 full × 400 GiB       = 800 GiB
14 days diff × 25 GiB  = 350 GiB
                          --------
Payload capacity         1,150 GiB
```

This is only **assumed payload size**, excluding off-site replicas, object metadata overhead, staging/aggregate space, compression variability, graph growth, legal-hold copies, and restore headroom. Measure against real data and budget for download/egress costs.

To reduce storage usage, never arbitrarily cut committed retention. Evaluate compression, storage tiers, aggregation, full backup cadence, or excluding *truly regenerable* data by business agreement.

## 7. A Copy "Existing" Differs from a Copy "Verified"

### 7.1. Inspecting Metadata and Chain Health

In current Neo4j Enterprise releases, `neo4j-admin backup inspect` reads artifact metadata: database name/ID, backup time, full/differential status, lowest and highest transaction IDs, and recovered state.

Example inspecting an authorized backup directory:

```bash
# Does not modify data; run on a host with read access to the backups.
bin/neo4j-admin backup inspect /secure-backups/neo4j
```

Inspect the chain ending at the latest backup:

```bash
bin/neo4j-admin backup inspect \
  --latest-chain \
  /secure-backups/neo4j
```

**Do not use file timestamps as the sole proof** of RPO. Check transaction IDs and relationships across artifacts. The two newest backup files may belong to **two different database IDs** even with the same database name after a drop/recreate; they do not form a valid recovery chain.

In older versions, option names for metadata inspection may differ; check `neo4j-admin backup inspect --help` for the deployed binary. When using cloud buckets, permissions and path syntax must also match version-specific tool documentation.

### 7.2. Aggregating to Reduce Incident-Time Work

For long differential chains, Neo4j Enterprise can **aggregate** into a single recovered full backup:

```bash
# Example strictly for preparation/verification on backup storage.
# Keep the old backup during trials so you do not lose fallback options.
bin/neo4j-admin backup aggregate \
  --from-path=/secure-backups/neo4j \
  --keep-old-backup=true \
  neo4j
```

Aggregation applies transaction logs to the store to produce a recovered artifact, **reducing recovery work at restore time** and the risk of losing a chain link. It does not remove the need to retain PITR history per policy: if you keep only the latest aggregated full and purge all old logs, **intermediate recovery points** can be lost.

Do not run aggregation concurrently with retention cleanup on the same backup directory without locking/coordination. Provision sufficient memory, CPU, disk, and temporary directory space because aggregation is also resource-intensive.

### 7.3. Consistency Check

Neo4j provides `neo4j-admin database check` to verify graph structure, property ownership, counts, and indexes on an offline database or compatible backup/dump artifact.

```bash
# Example when you have a recovered full backup or valid dump.
bin/neo4j-admin database check \
  --from-path=/secure-backups/recovered \
  neo4j
```

**Never run the consistency checker directly against a live running database** or a standalone differential artifact. Certain versions/options only check recovered fulls or dumps; aggregate the chain first when validating a chain. `--from-path` behavior and file/directory selection vary by version, so check `--help` for your exact binary.

Consistency checks are valuable, yet **they do not prove the application can recover within RTO**. You must still run a trial restore and execute business queries through Java Driver and Spring Data Neo4j in an isolated environment.

### 7.4. Four Levels of Backup Validation

| Level | Verification | What remains unproven? |
| --- | --- | --- |
| 1 | Job exits cleanly, artifact appears | Whether the artifact contains all transactions needed for recovery |
| 2 | Chain metadata is contiguous, matching database ID and point | Whether stored files are corrupt or missing decryption permissions |
| 3 | Consistency check/aggregate passes on suitable artifact | Whether the system and application work properly after restore |
| 4 | Actual restore into an isolated environment, checking Cypher, schema, RBAC, app, and duration | Ongoing monitoring is still required as data and infrastructure evolve |

**Operational rule:** never mark a backup policy healthy solely from "green" daily jobs. Each drill cycle must prove **at least one recovery point** is genuinely usable and measure its RTO.

## 8. Repeatable Recovery Drill Runbook

### 8.1. Ownership and Preparation

Before a drill, assign clear owners:

- **Incident commander:** determines severity, RTO clock start, and approved recovery point.
- **DBA/Neo4j operator:** selects the chain and runs restore tools, checks database/status/consistency.
- **Infrastructure/SRE:** provisions VMs/storage/secrets/certificates/networking, tracks timing and resources.
- **Java/SDN service owner:** verifies Bolt connectivity, permissions, business Cypher queries, connections, and routing.
- **Product/data owner:** signs off on actual data loss, compares critical IDs/relationships, and authorizes traffic reopening.

**Run drills only on test infrastructure and test databases—never overwrite production.** Restore commands can replace store files and wipe destination data; enforce safety checks before any destructive command.

### 8.2. Drill Steps

1. **Select scenario:** disk loss, accidental relationship deletion, database corruption, full-region loss, or compromised credentials. Each scenario implies different recovery points and network isolation.
2. **Preserve evidence:** record incident timestamp, Neo4j version, database ID, transaction metadata, and auxiliary systems. For security incidents, isolate the threat vector before restoring.
3. **Select backup:** identify the full and all required differentials, or matching dump/snapshot; check against expected RPO.
4. **Prepare isolated target:** provision a restore target with adequate disk, compatible software/version, and matching certs/secrets/permissions. Never share production URIs without explicit approval.
5. **Restore:** run restore/load tools per edition and version docs. For PITR, lock in a UTC timestamp/transaction ID **prior to the harmful event**.
6. **Start the database:** inspect online status and logs. For clusters, follow the version-specific cluster restore procedure rather than arbitrarily overwriting a member.
7. **Verify Neo4j:** schema/indexes, nodes/relationships, business keys, object counts, access permissions, and critical queries.
8. **Verify from the application:** Java Driver `verifyConnectivity()`, Spring Data Neo4j repositories/services, read account checks, and write account checks on an approved test transaction.
9. **Controlled traffic cutover:** update routing/URI/DNS and health checks, monitor connection pools, latency, and errors—only after product owner approval.
10. **Postmortem/review:** record actual RPO/RTO, note the slowest step and any errors, and update policy and runbook.

### 8.3. Cypher Queries to Use During Acceptance

The labels and IDs below are **domain examples**—adapt them to your application's graph:

```cypher
MATCH (u:AppUser)
RETURN count(u) AS totalUsers;
```

```cypher
MATCH (p:Project)
RETURN count(p) AS totalProjects;
```

```cypher
MATCH (:AppUser)-[r:MEMBER_OF]->(:Project)
RETURN count(r) AS totalMemberships;
```

```cypher
MATCH (u:AppUser {userId: $userId})-[r:MEMBER_OF]->
      (p:Project {projectId: $projectId})
RETURN u.userId AS userId,
       p.projectId AS projectId,
       r.role AS role;
```

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

Correct node/edge counts are necessary, **not sufficient**: compare key IDs, properties, and relationship directions. If the source database had heavy concurrent writes at backup time, base expectations on the **chosen recovery point**, not automatically against post-incident live production numbers.

For system RBAC, verify users/roles and corresponding grants when authorized. `SHOW CONSTRAINTS`/`SHOW INDEXES` help verify schema, but do not replace checking Neo4j configuration, TLS certificates, Java connection pools, secrets, and external jobs.

### 8.4. Measuring RPO/RTO During the Drill

Suppose:

```text
Simulated incident:       14:00 UTC
Last restored commit:     13:46 UTC
Service passes acceptance:15:25 UTC
```

Then:

- **Actual RPO:** 14 minutes.
- **Actual RTO:** 85 minutes.

If targets are 15-minute RPO and 120-minute RTO, this drill **meets both targets**. If restore only reaches 13:30 or the application is not operational until 16:10, mark the drill **failed**, even if backup/restore commands exited 0.

Do not use a single small-scale drill to commit to all future incidents. Practice multiple failure modes, realistic data growth, cross-region restores, and different operators to reduce "only one person knows how to restore" risk.

## 9. AuraDB: Retention Depends on Service Tier

**Neo4j Aura** is a managed service, so users do not run `neo4j-admin database backup` directly on Aura servers. Instead, Aura provides **snapshots/backups** via its console/API, with schedules and retention varying by tier/version.

Key points to remember:

- **Single-database instances:** Aura documentation refers to copies as **snapshots**, covering the user database and related `system` state.
- **Multi-database instances:** backups are managed per database, including `system`; restoring an entire instance follows specific procedures.
- **Scheduled vs. on-demand:** depends on tier. Current documentation notes AuraDB Professional has daily scheduled snapshots; Business Critical and Virtual Dedicated Cloud on latest versions offer daily fulls and hourly differentials; Free offers only on-demand snapshots.
- **Retention and exportability** differ. Not every snapshot is exportable, and differential snapshots may only support in-service restore.
- **Restores can overwrite** target instance/database data. To preserve the current version, evaluate creating a new instance from a snapshot or exporting first, per tier capabilities.
- Aura stores copies within the service's cloud infrastructure, typically in the same provider/region as the instance. If your organization requires independent recovery **outside the same provider/region**, evaluate supported export and separate storage options.

**Never hard-copy retention day counts from one tier to another.** Product policies can change across versions and plans. Before finalizing RPO/RTO/retention, verify the **Snapshot/backup details** table in Aura documentation and the options actually visible on your organization's instance.

### 9.1. Reading the Aura Details Table Properly

| Aura attribute | Question to ask when signing an SLA |
| --- | --- |
| Scheduled frequency | Daily, hourly, or no scheduled backups? |
| Full/differential | Which points can be restored—PITR or snapshot points only? |
| Restorable days | How far back can a restore point be selected? |
| Exportable days | For how long can a full snapshot be downloaded/cloned? |
| On-demand | Can snapshots be taken before migrations or releases? |
| Restore target | Does it overwrite the instance or create an independent clone? |
| Region/provider | Does it meet actual off-site/cross-region requirements? |

If business RPO is shorter than what your Aura tier supports, do not promise that RPO based on built-in backups alone. Upgrade tiers, adjust architecture, synchronize data externally, or revise targets after cost/risk review.

## 10. Monitoring Metrics and Alerts Aligned to RPO/RTO

A backup policy only operates reliably with **clear owners and telemetry**:

| Metric / check | Meaning | Alerting guidance |
| --- | --- | --- |
| Age of last verified recovery point | Staleness of the latest recoverable transaction | Warn when approaching RPO budget; page/incident if breached |
| Timestamp of last **successful** backup | Whether the schedule is running or stuck | Alert if no success within allowed window |
| Backup chain continuity | Whether Full and DIFFs have valid parents and transaction ranges | Broken chain, missing artifact, or mismatched database ID |
| Total backup size and growth | Ability to sustain retention | Approaching disk/quota limits or budget overrun |
| Age of latest off-site copy | Recoverability if the entire site is lost | Off-site replication falling behind schedule |
| Restore drill duration | Time from simulated incident to acceptance | P95/max exceeds RTO target or upward trend |
| Consistency/restore verification | Usability of the copies | Check job or restore test fails |
| Certificate/encryption key expiry | Ability to access copies during an incident | Key/CA nearing expiry or insufficient decryption access |
| Retention compliance | Expired or missing valid checkpoints | Premature deletion, over-retention, or legal-hold violation |

Set alerts **before** RPO is breached so operators have margin to react. For example, with a 15-minute target, if the recovery point is already 12 minutes old and the next scheduled job has not finished, alert early rather than waiting until minute 15.

**An RPO dashboard should not just read cron's `last_success_timestamp`**: it must track which transaction timestamp that backup actually covers. When a single backup fails or a chain breaks, a recoverability-based metric reflects actual risk far more accurately.

## 11. Policy Template Ready to Hand Off to Operations

This is a **policy document template**, not a configuration file automatically parsed by `neo4j-admin`. All values below are **illustrative** and must be agreed upon by the product owner, DBA, SRE, and security team:

```yaml
policyId: neo4j-production-business
owner: data-platform
scope:
  environment: production
  databases: [neo4j, system]
  edition: enterprise
objectives:
  rpoMinutes: 15
  rtoMinutes: 120
  pointInTimeWindowDays: 7
schedule:
  full: daily
  differential: every-10-minutes
  verifyChain: every-run
retention:
  nearTermDays: 14
  weeklyCopies: 8
  monthlyCopies: 12
storage:
  offSite: true
  encryptionAtRest: required
  immutableCopies: required
  restoreCredentialsSeparated: true
operations:
  metadataInspect: every-run
  consistencyCheck: weekly-on-recovered-full
  restoreDrill: monthly
  drSiteDrill: quarterly
  approvalForDeletion: required
```

**Note:** the 10-minute DIFF schedule in the example provides buffer for a 15-minute RPO, yet remains only a plan. Actual attainment must be proven via transaction-coverage metadata, timely alerting, backup latency tracking, and restore drills. GFS retention **does not automatically guarantee** a 7-day PITR window unless the corresponding log chains remain intact.

### 11.1. Policy Acceptance Criteria

A policy is only accepted when:

1. **Clear ownership and approved SLAs** exist per database/business group.
2. **Copies truly exist:** scheduled backup jobs run, recording metadata and execution logs.
3. **Copies are secure:** access control, encryption, off-site placement, immutability, and key/secret management.
4. **Retention is verifiable:** historical points and the chains needed to restore them can be listed; no accidental parent deletion.
5. **RPO is measurable:** the latest recoverable transaction timestamp stays within threshold or triggers alerts/incidents.
6. **RTO passes drills:** the Java/Spring Data Neo4j service genuinely resumes functioning correctly within the deadline.
7. **Runbooks can be executed by others**, not reliant on memory or a single individual's account.
8. **Regular reviews exist:** whenever Neo4j version, graph size, backup schedule, storage location, or SLA changes, the policy is re-evaluated.

## 12. Common Mistakes

| Mistake | Correct understanding |
| --- | --- |
| "It's a 3-node cluster so no backup is needed." | Clusters improve availability but replicate erroneous deletions and can suffer regional outages |
| "Backing up every 15 minutes = guaranteed 15-minute RPO." | Must account for job failures, lag, and contiguous transaction coverage |
| "Backup finished in 5 minutes so RTO is 5 minutes." | RTO includes triage, restore, data and app verification, and cutover |
| "There are 30 backup files so we have 30 days of retention." | Must check recoverable timestamps, full/DIFF dependencies, and actual coverage |
| "We can delete old fulls and keep recent DIFFs." | Can break the chain and make dependent points unrecoverable |
| "RPO 0 can be achieved with hourly backups." | No; periodic backups always leave a window of potential data loss |
| "Infrastructure snapshot = Neo4j backup." | Snapshots lack transactional consistency without supported tool/procedure coordination |
| "A full backup always includes roles, accounts, and all secrets." | Must explicitly cover `system` backup, `--include-metadata`, config files, and external secrets |
| "A dump file can do PITR to any minute." | Dumps contain only the state at dump time, with no transaction chain to replay |
| "Consistency check PASS means restore succeeded." | You must still actually restore and verify queries, indexes/constraints, permissions, and the app |
| "Object-lock is enabled so decryption keys don't matter." | Losing keys or access can render backups unrecoverable |
| "Any Aura snapshot point can always be exported." | Depends on tier, snapshot age, full/diff type, and service policy |
| "Any cluster member can be overwritten during restore." | Neo4j has specific cluster procedures; arbitrary store overwrites can corrupt cluster state |
| "Restoring pre-migration data doesn't depend on version." | Restoring into an **older** Neo4j version than the one that took the backup is unsupported |
| "User data erasure requests mean immediately deleting every backup." | Requires legal-compliant retention/deletion policy, encryption, and properly governed immutable copies |

## 13. Exercises and Real-World Scenarios

### Exercise 1 — Calculating RPO from Commit Coverage

Backups complete at 10:00, 10:15, and 10:30; an incident happens at **10:42**. The 10:30 artifact covers transactions up to 10:29. Then:

- Determine **actual RPO based on the 10:29 point**.
- If the 10:30 backup failed and the 10:15 backup only covers transactions up to 10:14, what is the new RPO?
- With a 15-minute target RPO, which case breaches it? When should an alert fire?

*Hint:* base your answer on transaction coverage, not file completion time.

### Exercise 2 — Designing a Feasible RTO

A graph has 300 GiB of nodes/relationships and 50 GiB of transaction logs to replay; the DR environment only has 100 MiB/s effective download bandwidth, infrastructure takes 30 minutes to provision, and verification plus cutover take another 40 minutes.

Estimate the **minimum lower bound** just for downloading ~350 GiB, and check how much time remains for actual restore under a 2-hour RTO. Explain why you cannot sign an SLA without factoring in CPU time for log replay, opening the database, and application testing.

### Exercise 3 — Does the Retention Policy Break the Chain?

You have F1 on day 1, D1…D20 from day 2 to day 20, F2 on day 21, and D21…D30 from day 22 to day 30. The policy requires keeping recoverability for a point on day 15 and a point on day 28.

- Which artifacts **must definitely not be deleted** before proving the recovery path for day 15?
- Once F2 has been successfully restore-tested, can it replace F1 for restoring day 15?
- Where can you add an aggregate step to reduce RTO while still keeping committed PITR checkpoints?

### Exercise 4 — Accidental Cypher Data Deletion Incident

An accidental `DETACH DELETE` deleted 30,000 `:Project` nodes and `:MEMBER_OF` relationships at 14:05. The latest full backup was at 00:00, the latest DIFF covers transactions up to 14:00, and valid new updates continued from 14:06 onward.

Propose how to choose a PITR point before 14:05, the workflow to **restore in an isolated environment**, how to reconcile IDs and relationships, and a plan to evaluate/replay subsequent valid updates. Never propose overwriting production immediately without approval from the incident commander and data owner.

### Exercise 5 — Can Aura Meet the SLA?

A company uses AuraDB Professional and requires a **5-minute RPO**, 30-minute RTO, and 90-day retention while relying solely on the tier's default snapshots. Check the actual schedule/capabilities of the current tier and conclude whether those three targets can be committed using default backups alone. Propose tier upgrades, architectural changes, or target adjustments if they cannot.

**Completion criteria:** learners can calculate RPO/RTO from **recovered data and time-to-service**, build retention rules that preserve backup chains, pick the right tools for their Neo4j edition/Aura plan, maintain a recovery drill schedule, and explain why an untested backup is not evidence of DR readiness.

## Official References

- [Neo4j Operations Manual — Backup and restore planning](https://neo4j.com/docs/operations-manual/current/backup-restore/planning/): assessing RPO/RTO, edition, cost, and off-site storage requirements.
- [Neo4j Operations Manual — Backup modes](https://neo4j.com/docs/operations-manual/current/backup-restore/modes/): full/differential and distinguishing online/offline.
- [Neo4j Operations Manual — Online backup](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/): full/DIFF schedules, 2026.02 behavior, backup chains, and parameters.
- [Neo4j Operations Manual — Offline backup](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/): using `neo4j-admin database dump`.
- [Neo4j Operations Manual — Inspect backup metadata](https://neo4j.com/docs/operations-manual/current/backup-restore/inspect/): transaction IDs, database IDs, and chain verification.
- [Neo4j Operations Manual — Aggregate backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/): preparing recovered artifacts and managing restore duration.
- [Neo4j Operations Manual — Restore backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/): restore, `--restore-until`, UTC timestamps, cluster warnings.
- [Neo4j Operations Manual — Consistency checker](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/): checking databases and compatible full backups.
- [Neo4j Aura — Backup, export, restore and upload](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/): snapshots/backups by tier, restore/export capabilities, and retention.

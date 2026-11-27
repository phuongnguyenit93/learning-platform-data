# RPO, RTO, and Choosing a Backup Strategy

A PostgreSQL system can create a successful backup every day and still fail to meet the business's recovery requirements. If an incident occurs at 16:00 and the latest backup is from 01:00, the business could lose nearly 15 hours of data. If restoring the database takes 8 hours while the service is only allowed 30 minutes of downtime, that strategy also fails to meet requirements even if the backup file is completely intact.

Two metrics that turn recovery requirements into numbers that can be designed and measured are **RPO (Recovery Point Objective)** and **RTO (Recovery Time Objective)**. RPO defines the acceptable amount of data loss measured in time; RTO defines the maximum time to restore the service to an operational state. They are business requirements, from which you select backup frequency, WAL archiving, replication, standby, storage, restore procedures, and operational resources.

No single backup type fits every system. Logical dumps are convenient for migrations and selective recovery; physical base backups combined with WAL support full-cluster recovery and PITR; replication increases availability but does not replace historical backups; offsite/immutable copies protect against loss or deletion of the entire source environment. A strong strategy typically combines multiple layers, tests against incident scenarios, and conducts regular drills.

This lesson belongs to the **Backup** chapter of the **Database Engine Relational PostgreSQL** module. It focuses on how to define RPO/RTO, evaluate trade-offs between cost and protection level, choose a backup/HA/DR strategy, and build verifiable recovery procedures.

## 1. Learning Objectives

After this lesson, you will be able to:

- Define RPO and RTO and distinguish them from backup duration, retention, and availability.
- Calculate RPO/RTO from an incident timeline.
- Determine requirements based on the criticality of data and services.
- Distinguish between logical backups, physical backups, WAL/PITR, snapshots, replication, and standby.
- Choose a strategy suited to small/large databases, write rates, downtime, and cost.
- Understand the trade-offs of synchronous/asynchronous replication and near-zero RPO.
- Design retention, offsite copies, immutability, encryption, and access permissions.
- Evaluate backup windows, restore throughput, network, disk, and application dependencies.
- Build a DR runbook, recovery tiers, and cutover plans.
- Measure actual RPO/RTO through restore drills and disaster recovery exercises.
- Differentiate RPO/RTO by scenario: host failure, accidental deletion, corruption, region loss, and ransomware.

## 2. What Is RPO?

**RPO — Recovery Point Objective** is the maximum amount of data an organization accepts losing during an incident, usually expressed as a time interval measured backward from the time of the incident to the recoverable data state.

For example, an RPO of 15 minutes means that when an incident occurs, the business accepts that the recovered database state may be at most about 15 minutes older than the data point immediately prior to the incident, according to the agreed measurement method.

### 2.1. RPO Is a Data Requirement

RPO answers the question: **"How much previously recorded data can we afford to lose before the incident?"**

It does not directly answer how long the database needs to start, or how long the application needs to resume operating.

### 2.2. Zero RPO

RPO = 0 is typically understood as accepting zero loss of any committed transaction under a defined failure model. This is a demanding requirement that requires an appropriate synchronous/acknowledgement architecture; it cannot be inferred merely from having a standby or a WAL archive.

You must specify what type of failure RPO 0 applies to: losing a single node, losing an availability zone, losing an entire region, or logical/application errors. A design may meet the target for some failure modes but not others.

### 2.3. RPO Is Not Backup Frequency

Running a backup every 15 minutes does not automatically prove a 15-minute RPO. A job may run late, fail, fail to upload durably, have inaccessible encryption keys, or fail to restore.

Conversely, a strategy of daily physical base backups combined with continuous WAL archiving can achieve a much lower RPO than the interval between two base backups, provided WAL is stored completely and can be replayed.

### 2.4. Actual RPO Must Be Measured

With WAL archiving, measure the lag from when a WAL segment is closed/archived until it is durably present in an accessible recovery location. With replication, measure commit acknowledgement and replication lag per failure mode. With logical dumps, the recovery point is typically the consistent snapshot of the dump run.

### 2.5. RPO Depends on the Scenario

- Losing a primary node: a standby can recover up to the data that has been replayed/acknowledged.
- Accidentally dropping a table: requires a recovery point before the drop operation, typically via PITR or a logical backup.
- Losing an entire region: requires backup/WAL copies in another region.
- Ransomware deleting backups: requires immutable/offline copies accessible using an independent identity.

## 3. What Is RTO?

**RTO — Recovery Time Objective** is the maximum duration an organization accepts to restore a service after an incident to a defined operational level.

RTO is not just the time it takes for the PostgreSQL process to start. It can include incident detection, recovery decision-making, infrastructure provisioning, downloading backups, decryption, restoring, replaying WAL, data verification, starting applications, routing traffic, and business validation.

### 3.1. RTO Is a Time Requirement

RTO answers the question: **"How long can the service remain down at most before it must return to a state that meets requirements?"**

You must define what "operational" means: read-only, full read/write, or all features and external integrations ready.

### 3.2. Database Start Does Not Equal Service Restored

PostgreSQL may accept connections while the application still fails due to missing roles, extensions, secrets, DNS, TLS certificates, migrations, queue consumers, or external services.

### 3.3. RTO Must Include Detection and Decision Time

If monitoring detects an incident after 20 minutes and operators need 30 minutes to identify the right backup, that time has already consumed RTO before restore even begins.

### 3.4. Measured RTO Differs from RTO on Paper

A runbook estimating a 30-minute restore that has never been tested is not evidence. Measure from the start of a simulated incident until business checks succeed.

### 3.5. RTO by Service Tier

A payment API may require an RTO of 15 minutes; an internal report may tolerate 8 hours. Do not set a single RTO for every database if their business impact differs.

## 4. Distinguishing RPO and RTO

| Attribute | RPO | RTO |
|---|---|---|
| Full name | Recovery Point Objective | Recovery Time Objective |
| Focus | Recoverable data point | Service recovery duration |
| Common unit | Minutes/hours | Minutes/hours |
| Question | How much data is lost? | How long is the outage? |
| Design impact | Backup frequency, WAL, replication durability | Restore speed, standby, automation, capacity |
| Evidence | Actual recovery point/time | Restore duration and service readiness |
| Example | Lose at most 5 minutes of data | Recover within 45 minutes |

### 4.1. Two Independent Metrics

You can have a very low RPO but a long RTO if restoring a large cluster from backup takes a long time. You can also have a low RTO thanks to a standby but a high RPO if the standby lags or data has not been replayed.

### 4.2. Do Not Substitute One Metric for the Other

Increasing backup frequency may reduce potential data loss but does not necessarily make restores faster. Adding a standby may reduce failover time but does not preserve enough history to roll back before an accidental DELETE.

### 4.3. A Solution Must Meet Both

When the business requires a 5-minute RPO and a 30-minute RTO, a daily `pg_dump`-only solution does not qualify merely because the dump file is small or the job finishes quickly.

## 5. Example Timeline: Calculating RPO and RTO

Suppose:

~~~text
01:00  Logical dump completes, consistent snapshot at 01:00
12:00  Next backup has not run yet
14:00  Incident renders the database inaccessible
17:00  Restore of dump into new cluster completes
17:20  Application passes business checks and receives traffic
~~~

- Actual RPO: about 13 hours (from 01:00 to 14:00).
- Actual RTO: 3 hours 20 minutes (from 14:00 to 17:20).

If the requirement is a maximum RPO of 15 minutes and a maximum RTO of 1 hour, the strategy above fails both.

### 5.1. Why Use the Service-Ready Timestamp?

The database finished restoring at 17:00, but the application was only ready at 17:20. If the goal is end-to-end service recovery, RTO ends at 17:20.

### 5.2. Snapshot Time Differs from File Completion Time

If `pg_dump` starts at 01:00 and finishes at 01:40, the logical snapshot does not necessarily represent the 01:40 state. Backup metadata must record accurate recovery point semantics.

### 5.3. Timestamps Need Explicit Timezones

In multi-region systems, record timestamps with timezone/UTC and standardize the clock source. Do not write "14:00" without knowing which timezone it refers to.

## 6. RPO/RTO, MTD, and Availability

Several related concepts:

- **MTD/MAO (Maximum Tolerable Downtime/Maximum Acceptable Outage):** the maximum outage duration the business can tolerate before consequences exceed acceptable thresholds.
- **WRT (Work Recovery Time):** the time required to recover backlogged work/tasks after the system is back online.
- **Availability/SLA/SLO:** the percentage or target duration the service is available within an observation window.

### 6.1. RTO Must Be Smaller Than the Business Downtime Limit

If the business can only tolerate 2 hours of downtime, a 4-hour RTO is unsuitable. In practice, there should be a buffer for uncertainty rather than designing right up to the hard edge.

### 6.2. WRT Can Extend Beyond RTO

The application may resume accepting traffic while event backlogs, reconciliation, or reports are not yet complete. Define WRT if the business requires clearing all backlogs.

### 6.3. Availability Does Not Measure Data Loss

A system with 99.99% uptime can still lose committed data if durability/backups are inadequate.

### 6.4. Backups Do Not Automatically Increase Availability

Backups serve post-incident recovery; they do not automatically provide instant failover like a properly operated standby.

### 6.5. HA and DR Complement Each Other

HA reduces downtime for node/instance failures; DR protects when an incident exceeds HA's scope, such as region loss, corruption, or accidental deletions propagating to replicas.

## 7. Defining RPO/RTO from Business Requirements

Do not start by picking a backup tool. Start by determining the consequences of losing data or having the service go down.

### 7.1. Classifying Data and Services

Example:

| Tier | Example | Impact Level |
|---|---|---|
| Tier 0 | Ledger, payment authorization | Very high |
| Tier 1 | Orders, inventory | High |
| Tier 2 | CRM, internal workflows | Medium |
| Tier 3 | Analytics, reproducible data | Lower |

Tier names are examples only; organizations should define them based on actual business needs and regulations.

### 7.2. Determining Acceptable Data Loss

For a ledger, losing a single transaction reported as successful can cause financial discrepancies. For a cache or reproducible summary table, an RPO of several hours may be acceptable.

### 7.3. Determining Outage Duration

Calculate downtime cost in terms of revenue, SLAs, customer experience, legal obligations, and dependencies of other services.

### 7.4. Identifying Failure Modes

Disk loss, host crashes, storage failures, availability zone loss, region loss, operator error, application bugs, corruption, and ransomware require different layers of protection.

### 7.5. Obtaining Business Owner Approval

DBAs/engineers can explain trade-offs, but RPO/RTO are business decisions. Record the approving owner and the review date.

## 8. RPO/RTO by Failure Mode

| Failure mode | RPO to examine | RTO to examine | Related strategy |
|---|---|---|---|
| PostgreSQL process crash | Usually very low thanks to WAL recovery | Restart/recovery time | WAL, storage durability |
| Primary host loss | Standby lag/acknowledged commits | Failover/provisioning | HA, streaming replication |
| Single disk loss | Backup/replica durability | Rebuild/restore | Redundancy, physical backup |
| Accidental table drop | Point prior to the bad operation | PITR + extract data | Base backup + WAL |
| Application bug writing bad data | Point prior to corruption | Clone/PITR/reconcile | Backup history |
| Region loss | Offsite copy/WAL replication | Cross-region restore | DR site, remote storage |
| Ransomware | Safe immutable point | Clean rebuild and restore | Immutable/offline backups |
| Logical data corruption | Recovery point before error | Data repair/copy back | PITR, logical exports |

### 8.1. HA Does Not Solve All Failure Modes

If a `DROP TABLE` statement is replayed on a standby, the standby loses the table too. You need backups/PITR to return to a point before the mistaken operation.

### 8.2. PITR Alone Does Not Solve OS/Infrastructure Failures

You need hosts, storage, networking, PostgreSQL binaries, extensions, keys, and a runbook to execute recovery.

### 8.3. Offsite Backups Do Not Automatically Have Low RTO

Downloading multiple terabytes over WAN can take many hours. Achieving a low RTO requires verifying restore bandwidth, compute capacity, and standby infrastructure provisioning capability.

### 8.4. One Incident Can Trigger Multiple Failure Modes

For example, ransomware may wipe both the primary and backup credentials. The design must evaluate blast radius and delete permissions, not just geographic distance.



## 9. Logical Backup: `pg_dump` and `pg_dumpall`

Logical backups represent schemas and data as SQL/logical objects. For PostgreSQL, the common tools are `pg_dump` for a single database and `pg_dumpall` for databases plus global objects depending on options.

### 9.1. Advantages

- Easy to select a database/schema/table or schema-only/data-only.
- Suitable for migrations and major version upgrades when objects/extensions are compatible.
- Can restore into a new database and selectively restore objects from a custom archive.
- Easy to extract partial data to recover an accidentally dropped table.
- Less tied to the physical data directory than physical backups.

### 9.2. Limitations

- Large restores can be slow because objects must be created, rows loaded, and indexes/constraints built.
- Dumping a single database does not automatically include all global roles/tablespaces.
- Dumps do not contain WAL history to replay transactions after the snapshot.
- Does not automatically back up server configuration files, extension binaries, secrets, or system data outside PostgreSQL.
- A single `pg_dumpall` run across multiple databases is not one atomic MVCC snapshot across the entire cluster.

### 9.3. Plain SQL and Archive Formats

`pg_dump -F p` produces plain SQL, typically restored with `psql`. Custom (`-F c`), directory (`-F d`), and tar (`-F t`) formats are restored with `pg_restore` with selective object restoration depending on the format.

### 9.4. When Is Logical Backup Suitable?

Small/medium databases, acceptable snapshot-based RPO, migrations, test clones, selective recovery, or environments that do not require PITR close to the incident time.

### 9.5. Do Not Judge Logical Backups by Size Alone

A 50 GB custom dump can take many hours to restore due to index builds, constraints, I/O, and concurrency. Measure actual restore throughput using production-equivalent data size and schema.

## 10. Physical Backup and Base Backup

Physical backups preserve the database cluster at the file/page level using a backup mechanism compatible with PostgreSQL. The foundational tool is `pg_basebackup`; specialized solutions can manage full/incremental/differential backups and catalogs.

### 10.1. Advantages

- Suitable for recovering large entire clusters.
- Can be combined with a WAL archive for PITR.
- Restores typically avoid recreating all logical objects and building every index from scratch.
- Suitable for disaster recovery strategies and standby bootstrapping.

### 10.2. Limitations

- Tied to compatible PostgreSQL major versions and physical formats.
- Usually restores the entire cluster rather than directly selecting a single table.
- Requires sufficient storage, permissions, tablespaces, and recovery configuration.
- PITR requires retaining the necessary WAL chain.
- Does not automatically recover external services outside PostgreSQL such as DNS, application secrets, or object storage.

### 10.3. A Base Backup Does Not Automatically Give Infinite PITR

A base backup may include enough WAL to start up to the consistent state of the backup. To recover to a later point, you need a continuous WAL archive from the backup point to the target.

### 10.4. Base Backup Schedule

Daily/weekly full base backups can be combined with WAL archiving. Frequency affects restore time, storage consumption, and the amount of WAL to replay; measure RTO accordingly.

### 10.5. Physical Backups Must Be Restorable

Do not treat copying the data directory while PostgreSQL is running as a safe backup. Use a backup protocol or snapshot strategy that guarantees consistency, including tablespaces and WAL as required.

## 11. WAL Archiving and Point-in-Time Recovery

WAL records the changes needed for PostgreSQL recovery and replication. When WAL segments are stored in an independent location, they can be replayed after restoring a base backup to bring the cluster to a recovery target.

~~~text
Base backup B0
     |
     +-- WAL segment 0001
     +-- WAL segment 0002
     +-- WAL segment 0003
     +-- WAL segment 0004
     |
     v
Recovery target (time / LSN / transaction)
~~~

### 11.1. Low RPO with WAL

Base backups may happen daily, but if the WAL archive is durably shipped continuously, the recovery point can be much closer to the incident time than with daily dumps.

### 11.2. Archive Lag Is RPO Exposure

If WAL has not been archived when a region is lost, the most recent transactions may not be present in the remote recovery set. Monitor `pg_stat_archiver`, archive failures, WAL backlog, and the timestamp of the last WAL confirmed in safe storage.

### 11.3. The WAL Chain Must Be Complete

Missing a single required segment can prevent replaying up to the target. You must manage timelines, segment naming, retention, and integrity.

### 11.4. Choosing a Recovery Target

PostgreSQL can recover to a timestamp, transaction ID/LSN, or named restore point depending on supported mechanisms/versions. Timestamps must specify an explicit timezone, and inclusive/exclusive semantics must be understood.

### 11.5. PITR Recovers Cluster State

PITR is not a single-row undo command. For logical errors, you typically spin up a secondary cluster at a point before the error, extract the needed data, and merge it back into the current system.

## 12. Replication and Standby: Reducing RTO Without Replacing Backups

Streaming replication sends WAL from the primary to a standby so the standby replays changes. If the primary fails, the standby can be promoted to continue serving.

### 12.1. Asynchronous Replication

The primary can confirm a commit before the standby receives/replays the WAL. Failover immediately after a commit can lose some transactions already confirmed on the primary that have not yet reached the standby.

- Advantages: typically lowers commit latency and reduces dependence on standby network conditions.
- Risk: replication lag creates a non-zero RPO.
- What to measure: write/flush/replay lag, LSN positions, and failure timing.

### 12.2. Synchronous Replication

The primary can wait for acknowledgement from a standby according to `synchronous_commit` / synchronous standby configuration. This can reduce the risk of losing confirmed transactions within an appropriate failure model.

- Advantages: stronger durability when the standby meets acknowledgement requirements.
- Cost: commit latency depends on the network and standby.
- Risk: standby/network outages can slow down or block writes depending on policy.
- Must understand acknowledgement levels: remote write, remote flush, and remote apply have different semantics.

### 12.3. Synchronous Does Not Solve Every Incident

If commits only wait for remote write/flush while the standby has not yet applied them, RTO and post-failover state must be understood according to the exact acknowledgement mode. If a logical error was committed, the standby can replay that error too.

### 12.4. A Standby Is Not a Backup History

Replication typically stays close to the current state. It does not retain older versions long enough to recover to before an erroneous DELETE/UPDATE.

### 12.5. A Delayed Standby Can Be an Additional Layer

A standby configured to intentionally delay replay can create a window to spot certain logical errors before they are applied. However, it does not replace offsite/immutable backups and requires separate management of lag, storage, and failover policy.

## 13. High Availability, Disaster Recovery, and Backup

| Mechanism | Primary Goal | Protects Well Against | Does Not Solve Alone |
|---|---|---|---|
| Local redundancy | Limit component loss | Single disk/device failure | Host/region loss, logical deletion |
| Streaming standby | HA/failover | Primary node failure | Replayed corruption/accidental deletion |
| Cross-zone standby | HA within a geographic region | Zone failure | Region-wide loss, ransomware |
| Cross-region replica | Geographic DR/HA | Region failure per topology | Logical corruption propagating to replica |
| Logical dump | Rebuild objects/data | Database loss up to snapshot | PITR after snapshot |
| Base backup + WAL | Physical recovery/PITR | Cluster loss, logical error before target | Dependencies outside DB |
| Immutable/offline backup | Prevent backup deletion/tampering | Ransomware/operator deletion | Low RTO if restore is slow |

### 13.1. HA Focuses on Continuity

The goal is to keep the service running or recover quickly when a component/node fails.

### 13.2. DR Focuses on Incidents Beyond HA Scope

The goal is to rebuild the service elsewhere when infrastructure is lost or a failure mode affects both the primary and replicas.

### 13.3. Backup Focuses on Returning to a Recovery Point

Backups must preserve historical states and be independently recoverable. A current replica does not replace that history.

### 13.4. Production Systems Usually Need All Three

HA for node failures, backup/PITR for logical errors, and offsite/immutable copies for region loss/ransomware. RPO/RTO must be defined per failure mode.

## 14. Storage/Cloud Snapshots

Storage snapshots can create fast recovery points if coordinated to guarantee PostgreSQL consistency.

### 14.1. Crash-Consistent Snapshots

A crash-consistent snapshot simulates storage state after a power outage; PostgreSQL may need WAL for crash recovery. Ensure volumes containing `PGDATA`, tablespaces, and WAL are snapshotted atomically per platform guidelines.

### 14.2. Application-Consistent Snapshots

Coordinated mechanisms/checkpoints/quiesce can be used to produce snapshots with clear consistency semantics. Do not assume snapshotting a single volume is sufficient.

### 14.3. Snapshots in the Same Storage Account Are Not Necessarily Offsite

If the account/region/identity is compromised or deleted, snapshots may be lost along with the primary. Copy/replicate them to a separate security boundary.

### 14.4. Snapshots Do Not Replace PITR

Snapshots provide discrete points in time. Recovering between snapshots requires WAL or an equivalent log mechanism.

### 14.5. Snapshot Retention

Manage lifecycles so snapshots required by a restore chain or retention policy are not deleted. Test restoring from snapshots rather than merely inspecting snapshot metadata.

## 15. Managed PostgreSQL Backups

Managed PostgreSQL services often provide automated backups, snapshots, retention, and point-in-time restore according to service tier.

### 15.1. Advantages

The provider can automate backup schedules, WAL retention, storage redundancy, PITR, encryption, and provisioning workflows.

### 15.2. Do Not Assume All Providers Are Identical

PITR window limits, RPO, RTO, cross-region copies, restore targets, export formats, and retention depend on provider/tier/region.

### 15.3. Restore Time Can Vary

A managed restore may provision a new instance and require time to provision/restore; clicking a button does not mean the database is instantly ready.

### 15.4. Quotas and Operational Dependencies

Check instance/storage/IP quotas, KMS/key availability, IAM permissions, networking, parameter groups, extensions, and application connectivity.

### 15.5. Verify Provider Exit Capability

Logical exports and independent restore documentation can be helpful for migrations or contingency plans. Avoid making every copy and encryption key depend solely on one account without evaluating blast radius.

## 16. Backup Strategy by Database Scale

| Characteristic | Reference Strategy | Risks to Measure |
|---|---|---|
| Small database, low writes | Periodic `pg_dump` + offsite copy | Restore duration, snapshot age |
| Medium database, low RPO | Base backup + WAL archive | Archive lag, replay time |
| Large database, low RTO | Physical backup, standby, automated provisioning | Restore throughput, failover, cost |
| Multi-TB database | Backup tool supporting parallel/incremental + WAL | Chain complexity, network/disk bandwidth |
| Multi-tenant | Per-database/schema strategy + cluster-level recovery | Cross-tenant scope, roles, consistency |
| Time-series | Physical backup/WAL + partition lifecycle | Retention, partition DDL, replay |
| Critical ledger | Appropriate synchronous durability + PITR + immutable backups | Commit semantics, independent recovery |

### 16.1. A Small Database Does Not Guarantee a Small RTO

A 5 GB database can still restore slowly if network, disk, indexes, or extension setup are poor.

### 16.2. Large Databases Need Realistic Throughput

With 4 TB of data and an effective restore throughput of 200 MB/s, ideal transfer time alone takes many hours; you must also account for decompression, WAL replay, index builds, provisioning, and validation.

### 16.3. Optimizing RTO May Require a Standby

If the RTO is shorter than physical restore time, a standby/HA setup may be necessary. Still maintain backups/PITR to handle logical errors and disasters.

### 16.4. Optimizing RPO May Require WAL/Replication

Daily logical dumps do not fit an RPO of a few minutes. Continuous WAL archiving and/or replication durability matching the failure model are required.

### 16.5. Costs Rise Quickly at Strict RPO/RTO Levels

Synchronous replicas, cross-region storage, immutable retention, standby capacity, and restore drills all incur costs. The business must approve a protection level commensurate with data value.


## 17. Choosing Backup Frequency from RPO

If only snapshot backups exist, the interval between recovery points is a major factor determining the maximum possible RPO.

### 17.1. Backup Every 24 Hours

With only daily backups, if an incident happens right before the next run, nearly 24 hours of data can be lost. Worst-case RPO is roughly the backup cycle, not counting job failures/lag.

### 17.2. Backup Every Hour

In theory, the gap between recovery points drops to nearly one hour, but the job must complete, the file must be durable, and restore must succeed.

### 17.3. Continuous WAL Archiving

Combining periodic base backups with a WAL archive produces denser recovery points. Actual RPO is affected by archive delay and WAL chain completeness.

### 17.4. Replication

A standby can lower RPO when WAL is transmitted/acknowledged appropriately. With asynchronous replication, transactions that have not yet reached the standby may be lost if the primary fails abruptly.

### 17.5. Set Alert Thresholds Lower Than RPO

If maximum RPO is 15 minutes, do not wait until archive lag hits 15 minutes to alert. Leave a buffer so operators can intervene before breaching the objective.

## 18. Choosing Architecture from RTO

RTO depends primarily on the recovery path and the execution speed of its steps.

### 18.1. Restoring from a Logical Dump

Duration can include schema creation, data loading, index builds, constraint validation, restoring permissions, and running checks. Large databases can take a long time to restore.

### 18.2. Restoring from a Physical Backup

This can be faster than logical rebuilding, but still depends on downloading data, decompression, WAL replay, storage throughput, and provisioning.

### 18.3. Warm Standby

A standby that is already provisioned and replaying WAL usually enables faster failover than rebuilding from backup. It requires automation, health checks, and promote/cutover procedures.

### 18.4. Hot Standby

Can serve read traffic and is ready for promotion as designed. Monitor replay lag, conflicts, replication slots, and capacity.

### 18.5. Pilot Light / Warm Site / Hot Site

- **Pilot light:** maintains minimal core infrastructure and scales up during an incident; lower cost, but provisioning/scaling increases RTO.
- **Warm site:** DR environment already has most components ready, requiring sync/cutover; balances cost and RTO.
- **Hot site:** infrastructure is nearly fully ready and can take traffic faster; high operating cost.

These terms describe the readiness level of the DR environment, not PostgreSQL backup types.

## 19. Measuring Restore Throughput and Estimating RTO

Suppose a database has 2 TB of physical data. Effective restore throughput is 250 MB/s:

~~~text
2 TB ≈ 2,000,000 MB (decimal estimate)
transfer time ≈ 2,000,000 / 250
              ≈ 8,000 seconds
              ≈ 2 hours 13 minutes
~~~

This is only the ideal transfer time.

### 19.1. The Remaining Time Components

- Provisioning compute/storage/network.
- Issuing credentials, certificates, and encryption keys.
- Downloading backups from remote storage.
- Decrypting/decompressing.
- Restoring base backups or logical objects.
- Replaying WAL to the target.
- Building indexes/constraints for logical restores.
- Running `ANALYZE`/required maintenance.
- Validating data and applications.
- Updating DNS/endpoints and connection pools.
- Opening traffic and monitoring.

### 19.2. Throughput Must Be Measured Under Similar Conditions

Same-region storage, cross-region bandwidth, compression ratios, concurrent workloads, and disk IOPS can drastically alter throughput.

### 19.3. Restores Can Bottleneck on CPU

Decompression, checksums, encryption, and index builds can saturate CPU before network/storage reaches maximum throughput.

### 19.4. WAL Replay Also Takes Time

If hours of WAL must be replayed after a base backup, RTO depends on write rate, WAL volume, CPU, and storage random I/O.

### 19.5. Do Not Treat Size/Bandwidth Division as a Commitment

That is only a lower-bound estimate. Official RTO commitments must come from end-to-end measured restore drills.

## 20. Retention Policy and Number of Recovery Points

Retention determines how far back into the past you can recover.

### 20.1. Short Retention

Reduces storage costs but lowers recoverability when corruption/ransomware is detected late.

### 20.2. Long Retention

Improves the ability to roll back before late-detected issues, but requires extra storage, metadata, catalog management, and key lifecycle planning.

### 20.3. Retention Must Account for WAL

If you keep base backups for 30 days but only keep the WAL chain for 2 days, PITR across most of those 30 days may be impossible. Retain the exact WAL needed for committed base backups/recovery targets.

### 20.4. A Recovery Point Is Not a Single Backup File

A physical recovery point may depend on a base backup, WAL segments, timeline history, configuration, and metadata. Manage retention by chain.

### 20.5. Storage Tiering

Recent backups require fast access; older backups can move to cold/archive storage if retrieval time still satisfies the recovery objectives for those scenarios.

## 21. The 3-2-1 Rule and the 3-2-1-1-0 Variant

The 3-2-1 rule is a common mnemonic:

- **3 copies:** keep at least three copies of the data (including the primary copy as defined by organizational policy).
- **2 media/storage domains:** use at least two independent storage types or domains.
- **1 offsite:** keep at least one copy at a location separate from the primary system.

The 3-2-1-1-0 variant typically adds:

- **1 immutable/offline copy:** maintain an immutable or offline copy to reduce the risk of modification/deletion alongside the primary.
- **0 errors:** test backups regularly, aiming for zero undetected errors.

### 21.1. This Is a Design Principle, Not a Certification

Not every workload requires the exact same copy count, but you must have a threat model explaining why your copy count, placement, and permissions mitigate your risks.

### 21.2. Two Copies in the Same Account May Share a Blast Radius

If one compromised identity has permission to delete both, they are not security-independent even if stored in two buckets.

### 21.3. Offsite Must Be Truly Separated

This could be a different region, a different account/subscription, an independent storage service, or a backup vault with protection policies. Evaluate admin permissions and key management as well.

### 21.4. Immutability Requires Lifecycle Testing

Object lock/retention lock can protect against deletion for a set period; you must know who can shorten policies, alter retention, or delete the account.

### 21.5. "0 Errors" Requires Restore Drills

Checksums and manifests help detect corruption, but only restore tests prove a backup is usable.

## 22. Protecting Backups: Encryption, Identity, and Secrets

Backups typically contain nearly all sensitive database data. Backup access can be equivalent to database read access.

### 22.1. Encryption at Rest and in Transit

Apply organizational encryption policies for object storage, disks, backup transfers, and dump files. Data transfer connections require appropriate TLS.

### 22.2. Key Management

Encrypted backups are only useful if encryption keys remain accessible during a disaster. Separate key recovery procedures and protect key material independently of the primary account/region.

### 22.3. Separated IAM

Separate identities allowed to create backups, read/restore backups, delete backups, and manage retention/keys. Never allow the application runtime identity to delete immutable backups.

### 22.4. Audit Access

Log who creates, reads, copies, restores, alters retention on, or deletes backups. Alert on anomalous behavior such as downloading full backups off-hours.

### 22.5. Secrets Inside Dumps

Logical dumps can contain password verifiers, tokens, or PII stored in tables; physical backups can contain the entire cluster's data. Both must be protected like production data.

## 23. Retention and Backup Catalog

A backup strategy needs to know which backup chain each artifact belongs to and up to what point it can restore.

### 23.1. Metadata to Record

- Backup ID and scope (database/cluster).
- Logical/physical/incremental type.
- PostgreSQL major/minor version and tool version.
- Job start/end timestamps.
- Snapshot/consistent point or LSN.
- WAL segment/timeline coverage.
- Storage URI and region/account.
- Encryption key reference (never record the key itself).
- Checksum/manifest.
- Retention expiry and chain dependencies.
- Most recent restore test, result, and duration.

### 23.2. Do Not Use File Modified Time as the Recovery Point

A file may finish writing long after the snapshot point. The recovery point must come from the backup tool's semantics.

### 23.3. The Catalog Also Needs Backup

If the backup catalog is lost, operators may not know restore order, dependencies, or encryption key references. Store metadata in an independent protection domain.

### 23.4. Backup Chains Need Dependency-Aware Cleanup

Do not delete a full/base backup while incremental backups or WAL recovery points still depend on it.

### 23.5. Inventory Checks

Periodically verify that the expected recovery points actually exist, retention policies are enforced, and artifacts are readable from the disaster recovery identity.

## 24. Choosing a Strategy by RPO/RTO Level

The table below is a guideline, not a default SLA. Actual outcomes depend on workload, provider, infrastructure, and drills.

| Illustrative Requirement | Commonly Considered Strategy | Prerequisites |
|---|---|---|
| RPO 24 hours, RTO 1 day | Daily logical dump + offsite | Restore tests fast enough |
| RPO 1 hour, RTO 4 hours | Frequent logical/physical backups + WAL as needed | Restore throughput and retention |
| RPO 15 minutes, RTO 1 hour | Base backup + continuous WAL archive; optionally add standby | Low WAL archive lag, automation |
| RPO a few minutes, RTO 15 minutes | Synchronous/near-sync standby + PITR backups | Network durability, failover drills |
| Near-0 RPO, RTO a few minutes | Synchronous HA architecture + independent backups | Strict failure model, cross-site design, operational readiness |
| Region loss, RTO a few hours | Cross-region backups/WAL and DR site | Capacity, keys, network, runbook |
| Accidental data deletion | PITR + isolated recovery environment | WAL chain, target selection, data merge |

### 24.1. Do Not Infer RPO Solely from Replication Mode

Understand `synchronous_commit`, `synchronous_standby_names`, quorum/priority behavior, standby state, and failure modes. A synchronous configuration does not automatically protect against every loss.

### 24.2. Do Not Infer RTO Simply Because a Standby Exists

A standby may be down, lagging, under-provisioned, or require a manual failover decision. Measure promotion, routing, and application readiness times.

### 24.3. RPO/RTO Should Be Divided by Service Tier

A system may have a high-tier primary transactional database and a low-tier analytics database. Their strategies will differ accordingly.

## 25. Selection Matrix: Logical, Physical, WAL, Replica, and Immutable

| Criterion | Logical dump | Physical base backup | WAL archive/PITR | Standby/replica | Immutable copy |
|---|---|---|---|---|---|
| Restore objects/data | Yes | Yes | Replay on base | Replay state | Depends on copy |
| Select a single table | More convenient | Not directly | Not directly | Not directly | Not directly |
| PITR | Not alone | Needs WAL | Yes with base backup | Not primary purpose | Protects artifacts |
| Low RTO | Can be slow for large DBs | Depends on throughput | Depends on replay | Usually better | Not automatically fast |
| Major version upgrade | Usually convenient | Not directly usable | Tied to physical chain | Tied to topology/version | Depends on content |
| Against logical corruption | Has recovery snapshot | Yes if target before error | Supports PITR | Usually replays error | Protects backup |
| Against region loss | Needs offsite | Needs offsite | Needs offsite archive | Cross-region if configured | Needs region independence |
| Against ransomware | Needs immutable copy | Needs immutable copy | WAL also needs protection | Replica can be affected | Primary purpose |

## 26. Choosing a Strategy for Production PostgreSQL

A reference architecture for a critical database may include:

~~~text
                         PostgreSQL Primary
                                 |
                    +------------+------------+
                    |                         |
                    v                         v
             Synchronous/async          WAL archive
                 Standby               remote storage
                    |                         |
                    v                         v
                HA failover              PITR recovery
                                              |
Primary/cluster -- base backup ---------------+
       |
       +-- logical dumps for selected objects/migration
       |
       +-- immutable/offsite backup copy
       |
       +-- backup catalog, keys, runbooks
~~~

### 26.1. Standby for Node Failures

Reduces RTO in applicable incidents; requires monitoring replication lag and promotion readiness.

### 26.2. Base Backup + WAL for PITR

Enables full-cluster recovery to a chosen target; must retain complete WAL and timeline history.

### 26.3. Logical Dumps for Selective Restore/Migration

Convenient for extracting a single table or moving objects to a new environment. Does not replace physical DR for large databases.

### 26.4. Immutable/Offsite for Large Blast Radius

Reduces the risk of backups being deleted or encrypted alongside the primary. Requires independent identities/keys and tested restore access.

### 26.5. Configuration and Application Dependencies

Store parameter settings, HBA/TLS configuration, extension inventories, secret references, DNS/routing, and deployment artifacts according to policy. Do not put plaintext secrets in runbooks.


## 27. RPO/RTO Calculation: Snapshot-Only Strategy

If only snapshot backups exist, the interval between recovery points is a major factor determining the maximum possible RPO.

### 27.1. Backup Every 24 Hours

With only daily backups, if an incident happens right before the next run, nearly 24 hours of data can be lost. Worst-case RPO is roughly the backup cycle, not counting job failures/lag.

### 27.2. Backup Every Hour

In theory, the gap between recovery points drops to nearly one hour, but the job must complete, the file must be durable, and restore must succeed.

### 27.3. Continuous WAL Archiving

Combining periodic base backups with a WAL archive produces denser recovery points. Actual RPO is affected by archive delay and WAL chain completeness.

### 27.4. Replication

A standby can lower RPO when WAL is transmitted/acknowledged appropriately. With asynchronous replication, transactions that have not yet reached the standby may be lost if the primary fails abruptly.

### 27.5. Set Alert Thresholds Lower Than RPO

If maximum RPO is 15 minutes, do not wait until archive lag hits 15 minutes to alert. Leave a buffer so operators can intervene before breaching the objective.

## 28. RPO with WAL Archive and Replication

With a physical base backup and a WAL archive, the recovery point can lie close to the incident time if the last WAL has been durably stored and the chain is complete.

### 28.1. Measuring Archive Delay

You can observe archiver status via the appropriate view:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Columns and behavior depend on version. This view is one signal; to calculate exact RPO, you need to know which WAL segment has been durably confirmed by remote storage.

### 28.2. What Does Archive Command Success Mean?

The archive mechanism must report success only after the WAL segment is fully persisted per the durability policy. If a script merely copies to local temp and returns success before remote upload, the server may treat the segment as archived even though the DR copy is not ready.

### 28.3. Unfilled WAL Segments May Not Be Archived Yet

WAL archiving typically processes segments via segment completion/timeout mechanisms; `archive_timeout` can help archive segments more frequently during low workloads, but does not replace durability confirmation.

### 28.4. RPO Based on Remote Durability

If remote object storage confirms a WAL segment after 4 minutes and an incident strikes right before the next segment is archived, RPO may exceed 4 minutes depending on write patterns, WAL generation, and archive behavior. Measure on a real timeline.

### 28.5. Replication Lag Measured Across Multiple Stages

Write, flush, and replay LSNs are distinct. A transaction received by a standby but not yet replayed does not mean read queries on the standby can see it; promotion/recovery behavior must be understood according to the replication mode.

## 29. RTO Calculation: Breaking Down the Phases

An end-to-end RTO can be modeled as:

~~~text
T_RTO =
  T_detect
+ T_decide
+ T_provision
+ T_retrieve
+ T_restore
+ T_replay
+ T_validate
+ T_cutover
~~~

Not all steps are sequential. Some can run in parallel, but only count parallelism when runbooks and tooling genuinely support it.

### 29.1. T_detect

Time from when the incident starts until monitoring/on-call becomes aware.

### 29.2. T_decide

Time to determine scope, failure mode, recovery point, and who holds approval authority.

### 29.3. T_provision

Creating compute, storage, networking, security groups, DNS, and database runtime.

### 29.4. T_retrieve

Downloading backups, WAL, configs, and dependencies from storage. Cold storage retrieval can prolong this step.

### 29.5. T_restore and T_replay

Logical restore, physical restore, and WAL replay have different bottlenecks. Measure each step separately.

### 29.6. T_validate and T_cutover

Running integrity/business checks, opening application connections, shifting traffic, and verifying health. Do not skip this part merely to report a lower RTO.

## 30. DR Runbook: From Incident to Recovery

A runbook can be divided into phases:

### Phase A — Detect and Declare

- Confirm the real incident and blast scope.
- Determine whether the primary is safe for writes or needs fencing.
- Assign an incident commander and technical recovery lead.
- Record start time, timezone, and failure mode.
- Notify stakeholders per incident policy.

### Phase B — Select Recovery Point

- Cross-check approved RPO.
- Identify the appropriate backup ID/base backup.
- Verify WAL chain/timeline if performing PITR.
- Pick a target before logical corruption if needed.
- Confirm remote copies, encryption keys, and catalog are accessible.

### Phase C — Provision Environment

- Provision a compatible PostgreSQL version.
- Prepare the data directory/tablespaces and permissions.
- Install extension binaries and configuration.
- Isolate the network to prevent applications from writing to an unverified cluster.
- Download/decrypt backups and WAL.

### Phase D — Restore and Recover

- Logical: create target database, restore globals/objects/data per runbook.
- Physical: restore base backup, configure WAL retrieval and recovery target.
- Check errors, logs, progress, and resource usage.
- Do not promote/cutover before verifying recovery target and cluster state.

### Phase E — Validate

- Check schema, constraints, indexes, and sequences.
- Check row counts, business invariants, and key aggregates.
- Check roles, ownership, grants, RLS, and extensions.
- Run read/write smoke tests in an isolated environment.
- Verify external dependencies and integration state.

### Phase F — Cutover

- Fence/disable the old primary if needed to avoid split-brain.
- Update DNS/service discovery/endpoints.
- Refresh connection pools and credentials.
- Open traffic gradually, monitoring error rates and replication.
- Record the recovered point and potential data loss relative to RPO.

### Phase G — Rebuild Protection

- Re-establish backup schedules and WAL archiving.
- Recreate standby/replication slots per runbook.
- Verify archive retention and offsite copies.
- Monitor until HA/backup protection returns to required levels.
- Conduct a post-incident review and update the runbook.

## 31. Recovery Point Selection and Logical Errors

When the fault is a SQL-valid operation that is wrong for the business (such as an accidental DELETE), the recovery point must precede the offending commit.

### 31.1. Identifying the Erroneous Timestamp

Use audit logs, application logs, transaction/event metadata, and operators to narrow down the timestamp. Clock synchronization is critical.

### 31.2. Spinning Up a Parallel Recovery Copy

Restore via PITR into an isolated cluster; do not immediately roll back all of production if production continued receiving valid transactions after the error.

### 31.3. Extracting Data to Rescue

Copy the necessary tables/rows/relations, verifying foreign keys and transactions that occurred after the recovery point.

### 31.4. Reconciling with Current State

You need conflict resolution rules: which rows were validly modified after the error, which transactions emitted messages, and which payments were processed externally.

### 31.5. Never Allow Two Primaries Accepting Writes Simultaneously

The secondary PITR cluster must be fenced/isolated until extraction completes or a clear cutover plan is executed.

## 32. RPO/RTO Across Multiple Databases and Related Services

An application may use multiple PostgreSQL databases, queues, object storage, caches, and payment services.

### 32.1. Snapshotting One Database Is Not a System-Wide Snapshot

Two databases may have logical dumps at different timestamps. If a business transaction spans both, the restored state may be inconsistent.

### 32.2. External Systems Need Separate Recovery Policies

Message brokers, object storage, search indexes, and payment providers have different backup/retention/consistency models than PostgreSQL.

### 32.3. Transactional Outbox and Idempotency

Patterns like transactional outbox help link database commits with event publishing in a retryable/reconcilable way. They do not automatically create distributed snapshots, but they support recovery semantics.

### 32.4. Recovery Ordering

The runbook must specify which service recovers first, which queues to pause, which consumers replay, and how to avoid duplicate event processing.

### 32.5. A Single Shared RPO Can Mislead

Define RPO for the database, event log, and external financial state; then define a business consistency objective for the overall workflow.

## 33. Cost Model: Stricter RPO/RTO Increases Cost

Backup/DR costs consist of multiple components:

- Storage for full/incremental backups and WAL.
- Cross-region replication/egress/network.
- Always-on standby compute and storage.
- Immutable retention and backup vaults.
- Encryption/KMS and identity administration.
- Monitoring, catalog, and orchestration.
- On-call staffing, drills, and post-incident recovery.
- Spare capacity for restore/rebuild.

### 33.1. Storage Cost

Long retention and multiple copies increase storage. Compression/deduplication can lower costs at the expense of CPU or dependencies.

### 33.2. Standby Cost

A hot standby can cost nearly as much in compute as the primary. Warm/pilot-light setups reduce cost but increase provisioning time/RTO.

### 33.3. Network Cost

Cross-region WAL/backup replication can incur egress and bandwidth charges. Measure write volume and peak bursts.

### 33.4. Operational Cost

An architecture using many backup tools may reduce RTO but increase complexity. If nobody can operate it during an incident, the design fails its purpose.

### 33.5. Business Impact Cost

Compare protection costs against expected losses from downtime/data loss. RPO/RTO are investment decisions, not just technical settings.

## 34. Recovery Tiers and Recovery Priority

When a disaster impacts multiple systems, you cannot restore everything simultaneously. Prioritization is required.

| Tier | Objective | Illustrative Examples |
|---|---|---|
| Tier 0 | Foundation required for recovery | Identity, network, key vault, DNS |
| Tier 1 | Critical transactional services | Payment/order ledger |
| Tier 2 | Dependent operational services | Inventory, customer workflow |
| Tier 3 | Reporting and analytics | Warehouse, dashboards |
| Tier 4 | Reproducible data | Cache, derived indexes |

### 34.1. Dependencies Determine Order

An application database cannot be recovered if key management, networking, or the identity provider is not ready yet.

### 34.2. Recovery Capacity Must Be Shared

Multiple databases restoring concurrently may contend for disk/network. Runbooks must define parallelism and ordering.

### 34.3. Lower Tiers Still Have RPO/RTO

An analytics system may accept a 24-hour RPO / 1-day RTO, but this must be documented explicitly rather than assuming no backup is needed.

### 34.4. Business Owners Approve the Order

Recovery ordering may vary by time of day, peak seasons, or regulatory obligations. Rehearse with the relevant teams.

### 34.5. Recovery Tiers Must Be Tested

Do not rely solely on documentation: test standing up identity/network, key access, and databases in the exact prescribed order.


## 35. Restore Drills and Exercises

A restore drill is a practical recovery exercise from real artifacts following the runbook, aimed at measuring recoverability and surfacing gaps before a real incident occurs.

### 35.1. Tabletop Exercise

Stakeholders walk through a scenario on paper: who declares an incident, who picks the recovery point, who approves cutover, and which dependencies must be ready. This is good for validating decisions and communication, though it does not prove technical restorability.

### 35.2. Technical Restore Test

Restore a backup into an isolated environment, run PostgreSQL, and verify schema/rows/permissions and the application. This provides more direct evidence of recoverability.

### 35.3. PITR Drill

Choose a timestamp, restore a base backup, replay WAL to the target, verify data before/after the target, and record timings. Perform this even on managed services offering a PITR button.

### 35.4. Region-Loss Exercise

Simulate the primary region being unreachable. Use only remote copies, identities, keys, and networking designed for DR. Do not pull files from the primary region during the test and then claim cross-region recovery is proven.

### 35.5. Ransomware/Immutable Exercise

Verify operators can access backups using a clean identity, that retention locks hold, and that encryption keys can be recovered after production credentials are disabled.

### 35.6. Drill Schedule

Frequency depends on criticality and rate of system change. Re-run drills after major changes to PostgreSQL version, backup tooling, storage, networking, IAM, or application dependencies.

## 36. Measuring and Recording Drill Results

Record a timeline comparable across runs:

| Milestone | Timestamp | Meaning |
|---|---|---|
| T0 | Incident declared | Start of RTO by convention |
| T1 | Recovery decision | Strategy/target selected |
| T2 | Infrastructure ready | Compute/network/storage ready |
| T3 | Backup accessible | Artifacts/keys downloadable |
| T4 | Database recovered | PostgreSQL reaches recovery target |
| T5 | Validation passed | Data and permission checks pass |
| T6 | Application ready | End-to-end smoke tests pass |
| T7 | Traffic cutover | Service re-opened per policy |

### 36.1. Which Milestone Does RTO Measure To?

If service-ready is defined at T6, RTO = T6 - T0. If the business requires live traffic reopened at T7, use T7 - T0. Lock down semantics before measuring.

### 36.2. Measuring RPO from Recovery Point

Record the snapshot time or recoverable transaction/LSN boundary compared to the data point immediately prior to the simulated incident.

### 36.3. Do Not Ignore Unreconciled Data

The database may open while outbox/queue/payment state remains inconsistent. Record both the recovery point and any business data gap.

### 36.4. Store Logs and Evidence

Keep command logs, backup IDs, manifests/checksums, version info, durations, errors, and business check results. Do not put credentials/PII into evidence.

### 36.5. Every Drill Must Produce Improvement Actions

For example, increasing bandwidth, preparing extension packages, fixing IAM, adding DNS steps, or updating runbooks. The next drill verifies those actions took effect.

## 37. Example Strategies by Service Tier

### 37.1. Tier 1 — Order/Payment Database

- Very low RPO per defined failure mode.
- Short RTO with standby/failover automation.
- Independent base backups and WAL archive.
- Immutable/offsite retention.
- Regular restore/PITR drills.
- Documented auditing, key recovery, and role dependencies.

### 37.2. Tier 2 — Inventory/Workflow

- May accept a 15–60 minute RPO depending on business needs.
- Base backup + WAL or managed PITR.
- Warm standby if required by RTO.
- Cross-region copies per risk level.
- Verify reconciliation with order/payment services.

### 37.3. Tier 3 — Analytics

- RPO of several hours or one day if data is reproducible.
- Logical/physical backups depending on size and restore time.
- Rebuild pipelines and source retention can be part of DR.
- Longer RTO can reduce standby costs.

### 37.4. Tier 4 — Cache/Derived Data

- Can be rebuilt from the source of truth.
- Must store configurations/schemas and pipeline artifacts.
- Quantify rebuild time and capacity instead of simply saying caches need no backup.

### 37.5. Do Not Assign Tiers by Database Size Alone

A small database containing a payment ledger can be more critical than a multi-terabyte warehouse.

## 38. Lab: Calculating RPO from a Backup Schedule

Suppose a database has only logical dumps, with the following backup schedule and incident:

~~~text
01:00  Dump A snapshot completes
07:00  Dump B snapshot completes
13:00  Dump C starts, but upload has not finished
14:30  Incident destroys host and source storage
~~~

### 38.1. Selecting the Recovery Point

If Dump A and B are both in offsite storage and restorable, Dump B is the latest recovery point. Incomplete Dump C does not count.

### 38.2. Calculating RPO

~~~text
RPO = 14:30 - 07:00
    = 7 hours 30 minutes
~~~

### 38.3. Comparing Against Requirements

If the business requires a maximum RPO of 1 hour, this snapshot-only strategy fails.

### 38.4. Improvements

You can increase logical/physical backup frequency, or use base backups + continuous WAL archiving. The choice depends on database size and RTO.

### 38.5. Model Worst-Case, Not Just Sunny Days

Include backup job failures, upload delays, and retention gaps in the model.

## 39. Lab: Calculating End-to-End RTO

Suppose a restore drill measures:

| Stage | Duration |
|---|---:|
| Detect/declare | 5 minutes |
| Select recovery point | 10 minutes |
| Provision infrastructure | 15 minutes |
| Download/decrypt backup | 20 minutes |
| Restore + WAL replay | 35 minutes |
| Validation | 15 minutes |
| Cutover/smoke tests | 10 minutes |

~~~text
RTO = 5 + 10 + 15 + 20 + 35 + 15 + 10
    = 110 minutes
    = 1 hour 50 minutes
~~~

### 39.1. Comparing Against Target

If the RTO objective is 1 hour, the current process fails.

### 39.2. Finding Bottlenecks

Restore + WAL replay takes 35 minutes and retrieval takes 20 minutes; provisioning and decision-making also consume time. You can optimize via pre-provisioned standbys, network throughput, parallel restores, or automation.

### 39.3. Do Not Skip Validation

Cutting validation from 15 minutes to 0 is not a sound optimization if it increases the risk of opening traffic onto corrupted data.

### 39.4. Measure Multiple Times

Durations depend on caches, storage load, networking, and database size. Use percentiles/peak conditions to design buffers.

### 39.5. Update Published RTO

If sufficient improvement is not yet possible, inform the business that actual RTO exceeds the target and obtain a decision to accept the risk or invest further.

## 40. Lab: Designing Strategies for Three Workloads

### Problem A — Blog Database

- 30 GB, moderate writes.
- Business accepts a 24-hour RPO.
- 8-hour RTO.
- Some data can be rebuilt from CMS exports.

A daily logical dump strategy with offsite copies and restore testing may be sufficient if measured restore times stay within RTO. Physical backups can be added when lower restore times are needed.

### Problem B — E-Commerce Orders

- 2 TB, continuous writes.
- 5-minute RPO.
- 45-minute RTO.
- Logical errors/accidental deletions require PITR.

Consider base backup + WAL archive with remote durability and monitored archive lag; a suitable standby to reduce RTO; immutable offsite copies to protect backups; PITR drills and a selective data recovery runbook.

### Problem C — Analytics Warehouse

- 8 TB, data reproducible from an event lake.
- 24-hour RPO.
- 24-hour RTO.
- Storage cost is important.

You can prioritize periodic backups and rebuild pipelines, choosing logical/physical depending on restore time. Verify event source retention, compute capacity, and actual RTO.

### 40.1. There Is No Single Right Answer

The strategies are starting points for analysis. Business impact, regulatory obligations, provider capabilities, and restore drills determine the final approach.

### 40.2. Extension Exercise

Add a region-loss or ransomware failure mode and observe how each strategy changes.


## 41. Common Mistakes When Designing RPO/RTO

1. Setting RPO equal to backup frequency without measuring job completion/remote durability.
2. Setting RTO equal to PostgreSQL startup time while ignoring application readiness.
3. Testing restores only on the same host/storage as the primary.
4. Having a standby without historical backups/PITR.
5. Having a WAL archive without verifying the WAL chain/timeline.
6. Keeping base backups while deleting WAL needed for recovery points.
7. Encrypting backups without rehearsing key recovery.
8. Having offsite copies where IAM allows the primary identity to delete offsite copies as well.
9. Choosing RPO 0 without defining the failure model/commit acknowledgement.
10. Choosing synchronous replication without evaluating network partitions and availability trade-offs.
11. Estimating RTO by dividing size by bandwidth without accounting for replay/validation.
12. Omitting incident declaration and decision times.
13. Lacking an accountable owner and cutover authority.
14. Failing to restore roles/extensions/configuration/dependencies.
15. Having no plan for external services and queues.
16. Only restoring full databases without testing selective recovery.
17. Failing to record recovery point/timeline/timezone.
18. Not checking backup retention and catalogs.
19. Failing to re-drill after version/infrastructure changes.
20. Using one universal RPO/RTO for all databases despite differing business impacts.

## 42. Practice Exercises

### Exercise 1 — Defining RPO

What does a 30-minute RPO mean?

**Answer:** The organization accepts recovering data up to roughly 30 minutes older than the time of the incident, according to the defined failure model and measurement method.

### Exercise 2 — Defining RTO

What does a 2-hour RTO mean?

**Answer:** The service must return to a defined operational state within at most 2 hours from the agreed incident start time.

### Exercise 3 — Snapshot-Only

Backup completed at 02:00, incident occurred at 11:00, no newer recovery point exists. RPO?

**Answer:** Approximately 9 hours.

### Exercise 4 — In-Progress Backup Job

A job started before the incident but did not finish/upload durably. Does it count as a recovery point?

**Answer:** No, unless the process proves the artifact is consistent and accessible.

### Exercise 5 — RTO Timeline

Incident at 09:00, application smoke test succeeds at 11:15. What is the end-to-end service-ready RTO?

**Answer:** 2 hours 15 minutes.

### Exercise 6 — Logical Dump

Can a standalone `pg_dump` recover to a point in time after the snapshot?

**Answer:** No; WAL history or another source is needed for changes after the snapshot.

### Exercise 7 — Physical Backup

What does a base backup need for PITR to a later point?

**Hint:** A complete WAL chain and recovery configuration/target.

### Exercise 8 — Standby

Does a standby replace historical backups?

**Answer:** No.

### Exercise 9 — Asynchronous Replication

What is the RPO risk if the primary fails right after a commit?

**Hint:** The transaction may not have reached/flushed/replayed on the standby.

### Exercise 10 — Synchronous Replication

What can synchronous replication trade off?

**Hint:** Commit latency and availability when the standby/network fails to acknowledge.

### Exercise 11 — RPO 0

Can you claim RPO 0 simply because a synchronous standby is configured?

**Answer:** No; acknowledgement semantics and the failure model must be specified.

### Exercise 12 — RTO and Standby

Why does a standby usually yield a shorter RTO than restoring from backup?

**Hint:** It is already provisioned and replaying close to the current state.

### Exercise 13 — Logical Corruption

Why does a standby not reliably protect against an accidental `DROP TABLE`?

**Answer:** The change can be replayed onto the standby.

### Exercise 14 — Immutable Copy

What risk does an immutable backup protect against?

**Hint:** Deletion/modification of backups by an attacker or operator within the retention period.

### Exercise 15 — Offsite

Can two buckets in the same account/region share the same blast radius?

**Answer:** Yes.

### Exercise 16 — Encryption Key

Is an encrypted backup recoverable if the key is no longer accessible?

**Answer:** No.

### Exercise 17 — Retention

Keeping base backups for 30 days but WAL for only 2 days can cause loss of what capability?

**Answer:** PITR to most recovery targets within the 30-day window.

### Exercise 18 — Archive Lag

Why does archive lag affect RPO?

**Hint:** The latest WAL does not yet have a durable copy at the DR location.

### Exercise 19 — RTO Calculation

Data restore 1 hour, WAL replay 20 minutes, validation 15 minutes, cutover 10 minutes; excluding detection/provisioning. Minimum total?

**Answer:** 1 hour 45 minutes, excluding the omitted steps.

### Exercise 20 — Throughput

A 1 TB database restores at 100 MB/s. Ideal transfer time using decimal TB?

**Answer:** About 10,000 seconds, or 2 hours 46 minutes 40 seconds; real-world restores include other overheads.

### Exercise 21 — MTD

Are a 4-hour MTD and a 6-hour RTO compatible?

**Answer:** No; RTO exceeds the maximum downtime accepted by the business.

### Exercise 22 — WRT

The database and application are running, but event backlogs take another 2 hours to process. What is this duration called?

**Answer:** Work Recovery Time (WRT), per the chosen operational definition.

### Exercise 23 — Tiering

Why might an analytics warehouse have a different RPO/RTO than a payment ledger?

**Hint:** Business impact and data reproducibility differ.

### Exercise 24 — Cross-Region DR

An offsite backup resides in another region, but KMS key access is missing. What happens?

**Answer:** Decryption/restore may fail.

### Exercise 25 — Backup Catalog

Why should the backup catalog be protected?

**Hint:** It records scope, version, recovery points, chains, key references, and artifact locations.

### Exercise 26 — Restore Drill

Does a tabletop exercise prove a backup restores successfully?

**Answer:** No; a technical restore test is required.

### Exercise 27 — PITR Drill

What must be verified beyond PostgreSQL starting up?

**Hint:** Target/timezone, WAL chain, schema/data, business invariants, and the application.

### Exercise 28 — Failure Modes

Do host loss and accidental table drop require identical strategies?

**Answer:** No; host loss can use failover, whereas logical deletion requires history/PITR.

### Exercise 29 — Multi-Database Consistency

Why can dumping two databases at two different times be business-inconsistent?

**Hint:** There is no shared distributed snapshot.

### Exercise 30 — Recovery Order

Why might key vault/network/identity need to be recovered before PostgreSQL?

**Hint:** They are dependencies for provisioning, decryption, and connectivity.

### Exercise 31 — Immutable Identity

Why should backup delete permissions be separated from the application identity?

**Hint:** To reduce blast radius if application credentials are compromised.

### Exercise 32 — WAL Archive Success

When should the archive command report success?

**Hint:** When the segment is durably stored per the durability contract, not merely copied to a local temporary path.

### Exercise 33 — Synchronous Semantics

Are remote write, remote flush, and remote apply identical?

**Answer:** No; they confirm different stages.

### Exercise 34 — Event-Based RPO

If the database recovers but the message queue has not replayed events, can there be a consistency gap?

**Answer:** Yes; reconciliation and idempotency are needed.

### Exercise 35 — Cost

What factors typically raise costs for a low RTO?

**Hint:** Standby capacity, cross-region infrastructure, automation, networking, and drills.

### Exercise 36 — Backup Schedule

If backups run every 6 hours, roughly how high can worst-case snapshot-only RPO be?

**Answer:** Nearly 6 hours plus job delays/failures if the latest recovery point is unavailable.

### Exercise 37 — Service-Ready

Why does RTO not end the moment the database accepts connections?

**Hint:** Validation, application startup, routing, and smoke tests remain.

### Exercise 38 — Ransomware

If an attacker has permission to delete both the primary and backup bucket, what protection layers need review?

**Hint:** Immutable/offline copies, separate accounts/identities, and key recovery.

### Exercise 39 — Business Approval

Who should approve RPO/RTO?

**Hint:** The business/service owner with input from engineering/operations/risk.

### Exercise 40 — Comprehensive Design

A 3 TB PostgreSQL database with a high write rate requires a 5-minute RPO, 30-minute RTO, and protection against region loss and accidental deletion. Propose protection layers and verification methods.

**Hint:** Physical base backups, continuous offsite WAL archive with lag alerts, an appropriate standby to lower RTO, immutable backup copies, IAM/key separation, PITR runbook and isolated restores, cross-region capacity, business validation, and restore drills measuring RPO/RTO plus reconciliation for external events.

## 43. RPO/RTO Definition and Approval Checklist

### 43.1. Business Requirements

- [ ] Is the service/database owner identified?
- [ ] Is the business impact of data loss/downtime described?
- [ ] Does RPO have clear numbers and a failure model?
- [ ] Does RTO have a clear service-ready definition?
- [ ] Have MTD/MAO and WRT been considered?
- [ ] Are external dependencies listed?
- [ ] Has an authorized stakeholder approved?

### 43.2. Backup/HA/DR Strategy

- [ ] Does the logical/physical strategy match database size?
- [ ] Are base backups and WAL archive sufficient for PITR if needed?
- [ ] Does the replication mode meet durability/RPO per failure mode?
- [ ] Does standby capacity meet RTO?
- [ ] Is there an offsite/cross-region copy?
- [ ] Is there an immutable/offline copy per the threat model?
- [ ] Are the backup catalog and configurations protected?
- [ ] Does retention keep sufficient base/WAL chains?

### 43.3. Security and Accessibility

- [ ] Encryption at rest/in transit?
- [ ] Has key recovery been tested?
- [ ] Are backup/restore/delete IAM permissions separated?
- [ ] Can the immutable retention policy not be deleted by the primary identity?
- [ ] Are audit logs retained?
- [ ] Can the disaster recovery identity access artifacts?

### 43.4. RTO and Capacity

- [ ] Has restore throughput been measured?
- [ ] Is network/storage/compute capacity sufficient?
- [ ] Is provisioning automated?
- [ ] Have WAL replay/index build/validation times been factored in?
- [ ] Are DNS, secrets, TLS, extensions, and app dependencies ready?
- [ ] Have connection pools and cutover procedures been tested?

### 43.5. Drills

- [ ] Logical restore drill?
- [ ] Physical restore/PITR drill?
- [ ] Failover/standby drill?
- [ ] Cross-region restore?
- [ ] Immutable/ransomware recovery exercise?
- [ ] Were actual RPO/RTO and action items recorded?
- [ ] Re-drilled after major changes?

## 44. Quick Reference Table

| Concept | Meaning |
|---|---|
| RPO | Maximum acceptable data loss measured in time |
| RTO | Maximum time for the service to return to a defined state |
| MTD/MAO | Maximum downtime the business can tolerate |
| WRT | Time to process backlogged work after restore |
| Availability | Level of service availability over a measurement window |
| Logical dump | Schema/data at the SQL level |
| Physical backup | Copy of cluster at the file/page level |
| Base backup | Physical baseline for recovery |
| WAL archive | WAL sequence stored for replay |
| PITR | Recovery to a recovery target |
| Async replication | Primary does not wait for full standby acknowledgement before commit response per configuration |
| Sync replication | Commit can wait for standby acknowledgement per mode |
| Standby | Server receiving/replaying WAL for HA/DR/read-only |
| HA | Maintaining continuity when certain faults occur |
| DR | Recovery after disasters exceeding HA scope |
| Offsite | Copy in an independent domain/location |
| Immutable | Copy that cannot be modified/deleted within the retention policy |
| 3-2-1-1-0 | Principle of multiple copies, storage media, offsite, immutable, verified |
| Restore drill | Practical recovery exercise |
| Recovery point | Recoverable data state |
| Archive lag | Delay for WAL to be stored in the archive destination |
| Replay lag | Delay for standby to apply WAL |
| Backup catalog | Metadata and dependencies of backups |
| Recovery tier | Service recovery priority level |
| Cutover | Shifting traffic to the recovered environment |

## 45. Conclusion

**RPO and RTO are distinct requirements that must be designed together.** RPO bounds how much data can be lost; RTO bounds how long the service may remain disrupted. A system with daily backups can have an RPO near 24 hours; a system with a standby can recover faster yet still not protect against erroneous operations that get replayed. No single tool solves all failure modes.

In PostgreSQL, logical dumps fit migrations and recovering objects/data at a snapshot; physical base backups combined with a WAL archive support cluster recovery and PITR; replication/standbys reduce RTO for applicable faults; offsite and immutable copies protect against region loss or destructive deletion. Retention, encryption keys, IAM, extension/configuration dependencies, and external systems must all be part of the plan.

**RPO/RTO only have value when measured through recovery drills.** Measure from genuinely accessible recovery points and the service-ready timestamp, including detection, decision, provisioning, retrieval, restore, replay, validation, and cutover. Record results, compare against targets, fix bottlenecks, and re-drill after major changes.

Final principle: **identify failure modes and business impact first, select backup/HA/DR layers to meet RPO/RTO, protect artifacts and keys independently, and then prove via restore tests that data and services can return within committed timelines.**


## 27. RPO Calculation with a Snapshot-Only Strategy

If only snapshot backups exist, the interval between recovery points is a major factor determining the maximum possible RPO.

### 27.1. Backup Every 24 Hours

With only daily backups, if an incident happens right before the next run, nearly 24 hours of data can be lost. Worst-case RPO is roughly the backup cycle, not counting job failures or upload lag.

### 27.2. Backup Every Hour

In theory, the gap between recovery points drops to nearly one hour, but the job must complete, the file must be durable, and restore must succeed.

### 27.3. Job Start Is Not a Recovery Point

A running backup job or a partially created file is not a valid recovery point.

### 27.4. Accessible in DR Only After Upload Completes

If the file resides only in the primary region, it may become unavailable after a region loss. Determine the timestamp when the remote copy is durable and readable.

### 27.5. Model Worst-Case, Not Just Sunny Days

With snapshots every 6 hours, worst-case RPO can approach 6 hours, plus job delays/failures and remote copy time if the recovery point is not yet ready. If one job fails undetected, the gap can double or worse.

## 28. RPO with WAL Archive and Replication

With a physical base backup and a WAL archive, the recovery point can lie close to the incident time if the last WAL has been durably stored and the chain is complete.

### 28.1. Measuring Archive Delay

You can observe archiver status via the appropriate view:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Columns and behavior depend on version. This view is one signal; to calculate exact RPO, you need to know which WAL segment has been durably confirmed by remote storage.

### 28.2. What Does Archive Command Success Mean?

The archive mechanism must report success only after the WAL segment is fully persisted per the durability policy. If a script merely copies to local temp and returns success before remote upload, the server may treat the segment as archived even though the DR copy is not ready.

### 28.3. Unfilled WAL Segments May Not Be Archived Yet

WAL archiving typically processes segments via segment completion/timeout mechanisms; `archive_timeout` can help archive segments more frequently during low workloads, but does not replace durability confirmation.

### 28.4. RPO Based on Remote Durability

If remote object storage confirms a WAL segment after 4 minutes and an incident strikes right before the next segment is archived, RPO may exceed 4 minutes depending on write patterns, WAL generation, and archive behavior. Measure on a real timeline.

### 28.5. Replication Lag Measured Across Multiple Stages

Write, flush, and replay LSNs are distinct. A transaction received by a standby but not yet replayed does not mean read queries on the standby can see it; promotion/recovery behavior must be understood according to the replication mode.

## 29. RTO Calculation: Breaking Down the Phases

An end-to-end RTO can be modeled as:

~~~text
T_RTO =
  T_detect
+ T_decide
+ T_provision
+ T_retrieve
+ T_restore
+ T_replay
+ T_validate
+ T_cutover
~~~

Not all steps are sequential. Some can run in parallel, but only count parallelism when runbooks and tooling genuinely support it.

### 29.1. T_detect

Time from when the incident starts until monitoring/on-call becomes aware.

### 29.2. T_decide

Time to determine scope, failure mode, recovery point, and who holds approval authority.

### 29.3. T_provision

Creating compute, storage, networking, security groups, DNS, and database runtime.

### 29.4. T_retrieve

Downloading backups, WAL, configs, and dependencies from storage. Cold storage retrieval can prolong this step.

### 29.5. T_restore and T_replay

Logical restore, physical restore, and WAL replay have different bottlenecks. Measure each step separately.

### 29.6. T_validate and T_cutover

Running integrity/business checks, opening application connections, shifting traffic, and verifying health. Do not skip this part merely to report a lower RTO.

## 30. DR Runbook: From Incident to Recovery

A runbook can be divided into phases:

### Phase A — Detect and Declare

- Confirm the real incident and blast scope.
- Determine whether the primary is safe for writes or needs fencing.
- Assign an incident commander and technical recovery lead.
- Record start time, timezone, and failure mode.
- Notify stakeholders per incident policy.

### Phase B — Select Recovery Point

- Cross-check approved RPO.
- Identify the appropriate backup ID/base backup.
- Verify WAL chain/timeline if performing PITR.
- Pick a target before logical corruption if needed.
- Confirm remote copies, encryption keys, and catalog are accessible.

### Phase C — Provision Environment

- Provision a compatible PostgreSQL version.
- Prepare the data directory/tablespaces and permissions.
- Install extension binaries and configuration.
- Isolate the network to prevent applications from writing to an unverified cluster.
- Download/decrypt backups and WAL.

### Phase D — Restore and Recover

- Logical: create target database, restore globals/objects/data per runbook.
- Physical: restore base backup, configure WAL retrieval and recovery target.
- Check errors, logs, progress, and resource usage.
- Do not promote/cutover before verifying recovery target and cluster state.

### Phase E — Validate

- Check schema, constraints, indexes, and sequences.
- Check row counts, business invariants, and key aggregates.
- Check roles, ownership, grants, RLS, and extensions.
- Run read/write smoke tests in an isolated environment.
- Verify external dependencies and integration state.

### Phase F — Cutover

- Fence/disable the old primary if needed to avoid split-brain.
- Update DNS/service discovery/endpoints.
- Refresh connection pools and credentials.
- Open traffic gradually, monitoring error rates and replication.
- Record the recovered point and potential data loss relative to RPO.

### Phase G — Rebuild Protection

- Re-establish backup schedules and WAL archiving.
- Recreate standby/replication slots per runbook.
- Verify archive retention and offsite copies.
- Monitor until HA/backup protection returns to required levels.
- Conduct a post-incident review and update the runbook.

## 31. Recovery Point Selection and Logical Errors

When the fault is a SQL-valid operation that is wrong for the business (such as an accidental DELETE), the recovery point must precede the offending commit.

### 31.1. Identifying the Erroneous Timestamp

Use audit logs, application logs, transaction/event metadata, and operators to narrow down the timestamp. Clock synchronization is critical.

### 31.2. Spinning Up a Parallel Recovery Copy

Restore via PITR into an isolated cluster; do not immediately roll back all of production if production continued receiving valid transactions after the error.

### 31.3. Extracting Data to Rescue

Copy the necessary tables/rows/relations, verifying foreign keys and transactions that occurred after the recovery point.

### 31.4. Reconciling with Current State

You need conflict resolution rules: which rows were validly modified after the error, which transactions emitted messages, and which payments were processed externally.

### 31.5. Never Allow Two Primaries Accepting Writes Simultaneously

The secondary PITR cluster must be fenced/isolated until extraction completes or a clear cutover plan is executed.

## 32. RPO/RTO Across Multiple Databases and Related Services

An application may use multiple PostgreSQL databases, queues, object storage, caches, and payment services.

### 32.1. Snapshotting One Database Is Not a System-Wide Snapshot

Two databases may have logical dumps at different timestamps. If a business transaction spans both, the restored state may be inconsistent.

### 32.2. External Systems Need Separate Recovery Policies

Message brokers, object storage, search indexes, and payment providers have different backup/retention/consistency models than PostgreSQL.

### 32.3. Transactional Outbox and Idempotency

Patterns like transactional outbox help link database commits with event publishing in a retryable/reconcilable way. They do not automatically create distributed snapshots, but they support recovery semantics.

### 32.4. Recovery Ordering

The runbook must specify which service recovers first, which queues to pause, which consumers replay, and how to avoid duplicate event processing.

### 32.5. A Single Shared RPO Can Mislead

Define RPO for the database, event log, and external financial state; then define a business consistency objective for the overall workflow.

## 33. Cost Model: Stricter RPO/RTO Increases Cost

Backup/DR costs consist of multiple components:

- Storage for full/incremental backups and WAL.
- Cross-region replication/egress/network.
- Always-on standby compute and storage.
- Immutable retention and backup vaults.
- Encryption/KMS and identity administration.
- Monitoring, catalog, and orchestration.
- On-call staffing, drills, and post-incident recovery.
- Spare capacity for restore/rebuild.

### 33.1. Storage Cost

Long retention and multiple copies increase storage. Compression/deduplication can lower costs at the expense of CPU or dependencies.

### 33.2. Standby Cost

A hot standby can cost nearly as much in compute as the primary. Warm/pilot-light setups reduce cost but increase provisioning time/RTO.

### 33.3. Network Cost

Cross-region WAL/backup replication can incur egress and bandwidth charges. Measure write volume and peak bursts.

### 33.4. Operational Cost

An architecture using many backup tools may reduce RTO but increase complexity. If nobody can operate it during an incident, the design fails its purpose.

### 33.5. Business Impact Cost

Compare protection costs against expected losses from downtime/data loss. RPO/RTO are investment decisions, not just technical settings.

## 34. Recovery Tiers and Recovery Priority

When a disaster impacts multiple systems, you cannot restore everything simultaneously. Prioritization is required.

| Tier | Objective | Illustrative Examples |
|---|---|---|
| Tier 0 | Foundation required for recovery | Identity, network, key vault, DNS |
| Tier 1 | Critical transactional services | Payment/order ledger |
| Tier 2 | Dependent operational services | Inventory, customer workflow |
| Tier 3 | Reporting and analytics | Warehouse, dashboards |
| Tier 4 | Reproducible data | Cache, derived indexes |

### 34.1. Dependencies Determine Order

An application database cannot be recovered if key management, networking, or the identity provider is not ready yet.

### 34.2. Recovery Capacity Must Be Shared

Multiple databases restoring concurrently may contend for disk/network. Runbooks must define parallelism and ordering.

### 34.3. Lower Tiers Still Have RPO/RTO

An analytics system may accept a 24-hour RPO / 1-day RTO, but this must be documented explicitly rather than assuming no backup is needed.

### 34.4. Business Owners Approve the Order

Recovery ordering may vary by time of day, peak seasons, or regulatory obligations. Rehearse with the relevant teams.

### 34.5. Recovery Tiers Must Be Tested

Do not rely solely on documentation: test standing up identity/network, key access, and databases in the exact prescribed order.

# Distinguishing Replication, Backup, and High Availability in PostgreSQL

Replication, backup, and High Availability (HA) all help a PostgreSQL system keep operating or recover when an incident occurs, but they solve different problems.

- **Replication** maintains one or more copies of data by streaming changes from a source to other nodes. It provides up-to-date copies for reads, role transitions, or node recovery.
- **Backup** creates a saved copy that can be used to restore data to a previous state. Backups must be kept independent of the ongoing failure and must be verified through restore testing.
- **High Availability** is the architecture and set of operational procedures that keep a service available when a component fails. HA includes replication in many designs, but it also requires failure detection, failover decisions, fencing, traffic routing, post-transition verification, and operational procedures.

A continuously replicated standby will also receive an accidental DELETE command from the primary. Therefore, replication does not replace backup. A good backup can recover data after a logical error, but it takes time to restore, so backup alone does not guarantee service continuity within seconds. An HA cluster can switch to a standby quickly, but if all replicas and backups reside in the same failure domain, a regional outage or destructive operation can wipe out everything.

```text
Replication:
Primary -- WAL / logical changes --> Replica
              |                       |
              +---- keeps up-to-date copy
                    for reads / failover

Backup:
Database -- base backup / dump / snapshot --> Backup repository
                                                |
                                                +--> restore / PITR

High Availability:
Health checks --> Failure decision --> Fence old primary
                                      --> Promote standby
                                      --> Route clients
                                      --> Verify service

Defense in depth:
Replication + HA + Backup + Restore drills
```

This lesson belongs to the **Database Engine Relational PostgreSQL** module, chapter **High Availability**, covering the topic **“Distinguishing Replication, Backup, and High Availability”**. The focus is on understanding the goals, limitations, and coordination of these three mechanisms in an operable and recoverable PostgreSQL design.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish replication, backup, durability, recoverability, and high availability.
2. Explain why replication is not a backup.
3. Explain why backup does not by itself create HA.
4. Recognize that HA is an architecture combining technology, processes, and operations.
5. Distinguish physical replication from logical replication.
6. Distinguish asynchronous from synchronous replication.
7. Understand the roles of WAL, WAL sender, WAL receiver, and standby replay.
8. Explain how logical errors propagate across replicas.
9. Distinguish base backup, logical dump, storage snapshot, and WAL archive.
10. Describe Point-in-Time Recovery (PITR).
11. Define Recovery Point Objective (RPO) and Recovery Time Objective (RTO).
12. Distinguish failover from switchover.
13. Explain failure detection, leader election, quorum, and fencing.
14. Recognize split brain and how to prevent two primaries from accepting writes simultaneously.
15. Understand the roles of load balancers, DNS, virtual IPs, and connection pools during a primary transition.
16. Design a replication topology for one primary and multiple standbys.
17. Distinguish intra-region HA from cross-region disaster recovery.
18. Design an independent backup repository with retention and deletion protection.
19. Schedule backups and WAL archiving according to RPO and RTO.
20. Identify failure domains across database, storage, network, control plane, and human operations.
21. Design monitoring for replication lag, backup freshness, archive health, and failover.
22. Build runbooks for failover, restore, PITR, and disaster recovery.
23. Test backups via restore drills and measure actual recovery times.
24. Evaluate trade-offs between durability, availability, latency, cost, and complexity.

**Scope:** Modern PostgreSQL, including physical streaming replication, logical replication, base backups, WAL archiving, and HA concepts. Specific parameters and statistics view columns may vary by major version and deployment platform. Configuration examples in this lesson are educational samples that must be adapted to your actual topology, security policy, and version.

---

## 2. Four Foundational Concepts to Separate

### 2.1. Availability

Availability answers the question: **can users continue using the service when a component fails?**

A system with HA typically has redundant nodes, a failure detection mechanism, and a way to reroute traffic. The goal is to minimize service downtime.

### 2.2. Durability

Durability answers the question: **does a transaction whose commit was acknowledged still survive after an incident?**

In PostgreSQL, WAL flush, fsync, `synchronous_commit`, and storage semantics affect durability. Synchronous replication can provide additional protection against losing the primary if a commit is acknowledged only after an eligible standby has flushed the WAL.

### 2.3. Recoverability

Recoverability answers the question: **can data be restored to a valid state after an error or data loss?**

Base backups, WAL archives, PITR, backup retention, and restore testing are essential components.

### 2.4. Replication

Replication answers the question: **how does another node receive changes from the source?**

Replication can support availability, read scaling, migration, and data distribution. However, a continuously updated copy does not necessarily retain history prior to an error.

### 2.5. Related but Non-Identical Goals

| Concept | Core Question | Common Mechanisms |
| --- | --- | --- |
| Availability | Is the service still accessible? | HA manager, standby, failover, routing |
| Durability | Is an acknowledged commit persistent? | WAL flush, fsync, synchronous replication |
| Recoverability | Can valid data be restored? | Backup, WAL archive, PITR |
| Replication | Does another node have an up-to-date copy? | Physical/logical replication |
| Consistency | Do data observations follow required rules? | Transaction isolation, replication semantics, application design |

A sound design must define each goal explicitly. Never use a single metric like replication lag to claim the entire system has good backups or good HA.

---

## 3. Replication in PostgreSQL

Replication maintains a copy of data on another node or system. PostgreSQL provides replication mechanisms with different goals and semantics.

### 3.1. Physical Streaming Replication

A physical standby receives WAL from the primary and replays changes at the physical level. The standby has a database structure matching the primary and is typically in read-only mode during recovery.

Conceptual flow:

```text
Application
    |
    v
Primary PostgreSQL
    |
    +--> WAL records
            |
            v
        WAL sender
            |
            v
        Network
            |
            v
        WAL receiver
            |
            v
        Standby pg_wal
            |
            v
        Startup / replay
            |
            v
        Standby data pages
```

Physical replication is commonly used for HA and read replicas because a standby can be promoted to primary when eligible.

### 3.2. Logical Replication

Logical replication streams logical changes of selected tables/publications to a subscriber. It is suited for specific data distribution use cases, synchronizing subsets of tables, or migrating between compatible systems.

Logical replication is not equivalent to a physical standby:
- Specific objects can be chosen for publication.
- Schemas and indexes must be managed through operational procedures.
- It does not automatically replicate all cluster-wide objects such as roles and tablespaces in the same way physical backup does.
- Sequence state and certain DDL operations must be handled separately.
- A subscriber can have a different layout from the source.

### 3.3. Replication Is Not a Versioned Backup

A standby typically reflects the latest state it has replayed. If data is accidentally deleted on the primary, that change is also replicated. If an application writes corrupted or wrong data, the replica usually receives that wrong data as well.

### 3.4. Replication Does Not Keep Infinite History

WAL is retained according to retention needs, checkpoint/recycling, archiving, and replication slots. A standby that stays offline for too long may no longer be able to fetch required WAL from the primary.

### 3.5. Replication Can Serve Multiple Goals

- HA: promote a standby when the primary is lost.
- Read scaling: offload some read-only queries to replicas.
- Disaster recovery: maintain a copy at another site.
- Migration: move data to a new cluster.
- Analytics: synchronize data to a dedicated reporting/read system.

A replica only serves the purpose for which it has been designed and tested. A read replica is not automatically a DR site if it shares the same failure domain as the primary.

---

## 4. Asynchronous and Synchronous Replication

### 4.1. Asynchronous Replication

The primary does not wait for a standby to acknowledge WAL before returning COMMIT. This reduces commit latency and avoids blocking transactions on network or standby delays.

In return, the primary can acknowledge a transaction that the standby has not yet received or flushed to WAL. If the primary fails suddenly and a standby is promoted, some of the most recent commits may be missing on the standby.

### 4.2. Synchronous Replication

With synchronous replication, the primary waits for one or more standbys to acknowledge according to policy before returning COMMIT. The wait level depends on `synchronous_commit` and `synchronous_standby_names`.

Common values of `synchronous_commit`:

| Value | General Meaning |
| --- | --- |
| off | Do not wait for local WAL flush for each commit |
| local | Wait for local WAL flush, do not wait for standby |
| on | Wait for local flush and remote acknowledgement per sync policy |
| remote_write | Wait for standby to write WAL to OS |
| remote_flush | Wait for standby to flush WAL |
| remote_apply | Wait for standby to replay WAL |

Consult your major version documentation and actual configuration to understand the exact semantics of sync standbys and quorum.

### 4.3. Synchronous Replication Is Not a Backup

If an accidental DELETE transaction is committed and acknowledged synchronously, the standby also receives the DELETE. Synchronous replication can protect commits from primary loss, but it provides no history prior to the erroneous operation.

### 4.4. Availability Trade-off

If the primary cannot reach the required synchronous standby, commits may wait indefinitely. This is a trade-off between durability and the ability to continue accepting writes during node or network failures.

### 4.5. Quorum Synchronous Replication

PostgreSQL can configure `synchronous_standby_names` using FIRST/ANY and the number of standbys required to acknowledge. Quorum helps select an eligible subset of nodes, but the design must account for failure domains and which nodes are allowed to be promoted.

### 4.6. Do Not Assume Synchronous = RPO of 0

Actual RPO depends on which node is chosen during failover, which semantics the standby acknowledged under, whether storage properly flushes writes, and whether fencing and HA orchestration work correctly. Failure scenarios must be tested.

---

## 5. What Is a Backup?

A backup is a saved copy of data kept for recovery after an incident. A good backup can be restored even if the primary and replicas are lost or data has been erroneously altered.

### 5.1. Purposes

- Recover from logical errors or accidental operations.
- Recover from storage or data directory loss.
- Recover from ransomware or accidental deletion when backups remain independent.
- Restore to a point in time before data corruption occurred.
- Rebuild a standby or spin up a new cluster.
- Support auditing and compliance retention requirements.

### 5.2. Backups Do Not Automatically Keep the Service Running

A restore can take many minutes or several hours. Backups ensure data recoverability through a documented procedure, not automatic traffic redirection to another node.

### 5.3. Backups Must Be Independent of the Source

If a backup resides on the same disk, same storage account, or shares the same deletion permissions as the primary, a single major incident can destroy both.

### 5.4. Backups Must Be Tested

The mere existence of a backup file does not prove it can be restored. You must verify integrity, WAL continuity, server startup, and application data after restoration.

---

## 6. Common Backup Types Used with PostgreSQL

### 6.1. Physical Base Backup

A base backup is a consistent physical copy of a PostgreSQL cluster. It can be taken with `pg_basebackup` or a compatible backup tool.

Characteristics:
- Copies data files and required metadata.
- Suitable for physical restore and PITR.
- Must be combined with required WAL to achieve consistency and replay to the target.
- Must match the major version/format and platform requirements.

Example:

```bash
pg_basebackup \
  -h db-primary \
  -U backup_user \
  -D /backup/base-2026-11-14 \
  -X stream \
  -P
```

This is an illustrative example. Choose permissions, slots, compression, tablespace mapping, WAL method, and destination according to your backup policy.

### 6.2. Logical Backup with pg_dump

`pg_dump` creates a logical dump of a single database, typically in custom or directory format. `pg_dumpall` can additionally export global objects as appropriate.

Example:

```bash
pg_dump -Fc -d appdb -f appdb.dump
pg_restore -d appdb_restore appdb.dump
```

Logical backups are useful for:
- Restoring a specific database or objects.
- Moving data between certain compatible versions.
- Migrating schemas/data.
- Selective recovery.

A logical dump is not a physical backup of the entire cluster and does not replace continuous WAL archiving for physical PITR.

### 6.3. Storage Snapshots

Volume/block storage snapshots can enable fast backups, but they must be coordinated to guarantee PostgreSQL consistency. You must understand crash-consistent, filesystem-consistent, and application-consistent snapshots.

An arbitrary snapshot taken while the database is writing may not be equivalent to a valid base backup without proper coordination mechanisms.

### 6.4. Continuous WAL Archiving

WAL archiving retains completed segments in a separate repository. Combined with a base backup, it supports PITR and recovery to a specific point in time or LSN.

### 6.5. Physical and Logical Backups Have Different Goals

| Criterion | Physical Base Backup | Logical Dump |
| --- | --- | --- |
| Scope | Cluster/physical database files per tool | Dumped database/objects |
| Restore | Restores data directory/cluster | Recreates objects and loads SQL/data |
| Continuous physical PITR | Combined with WAL archive | Does not replace physical WAL PITR |
| Object selection | More limited | More flexible |
| Restore speed | Often faster for large clusters with good storage | Can be slow due to recreate/load/index build |
| Building a physical standby | Suitable | Not directly suitable |
| Cross-major-version | Requires physical format compatibility | Can support migration depending on versions/features |

---

## 7. How Base Backups and WAL Archives Enable PITR

PITR (Point-in-Time Recovery) allows restoring a database to a point in time before an incident occurred.

```text
Base backup at T0
       |
       v
Restore data directory
       |
       v
Continuously replay WAL archive
       |
       +---- WAL transaction 1
       +---- WAL transaction 2
       +---- WAL transaction 3
       |
       v
Stop at recovery target T1
       |
       v
Verify data
       |
       v
Promote if resuming writes
```

### 7.1. Why Is a Base Backup Needed?

WAL describes changes relative to an existing database state. It cannot replace a full baseline copy to reconstruct a cluster from scratch.

### 7.2. Why Is Continuous WAL Needed?

If a single required segment is missing along the path from the base backup to the recovery target, PostgreSQL may not be able to continue replaying.

### 7.3. Recovery Target

You can specify a target by timestamp, LSN, transaction ID, or named restore point, depending on the PostgreSQL version and configuration.

### 7.4. PITR Is Not Fast Failover

PITR requires restoring a base backup and replaying WAL. It is typically slower than promoting an already-running standby, but it allows rolling back to before a logical error.

### 7.5. After PITR and Promotion

When a restored instance is promoted and begins accepting new writes, PostgreSQL creates a new timeline. The archive policy must preserve timeline history files and WAL for the new branch.

---

## 8. Why Replication Does Not Replace Backup

This is the most important distinction to remember.

### 8.1. Logical Errors Are Replicated

Example:

```sql
DELETE FROM orders;
COMMIT;
```

If this statement runs on the primary, WAL describing the change is sent to the physical standby. The standby replays the change and loses those rows as well.

### 8.2. DROP TABLE Is Also Replicated

Replication propagates database changes, including validly committed destructive operations. It has no way of knowing whether the user intended to run that command.

### 8.3. Ransomware or Credential Compromise

If an attacker gains database write access or backup deletion access through shared credentials, destructive changes can propagate to replicas and the backup repository if permissions and failure domains are not isolated.

### 8.4. Corruption Can Propagate via WAL

Certain logical errors or invalid modifications can be replicated. Physical corruption does not always propagate identically, but a replica must never be treated as a verified backup.

### 8.5. Replicas Do Not Retain Pre-Error History

Without a delayed standby, WAL archive, and backups, a replica typically has no way to roll back to before an erroneous transaction.

### 8.6. Delayed Standby Is Only a Supporting Layer

A standby configured with an intentional replay delay can provide a time window to catch logical errors, but it still does not replace an independent backup. It can be lost alongside the primary site, storage, or credentials.

---

## 9. Why Backup Does Not Replace Replication

Backups protect data recoverability, but they do not automatically provide an online node ready to serve traffic.

### 9.1. Restore Takes Time

Restoring a base backup, replaying WAL, starting PostgreSQL, verifying data, and switching the application over can exceed RTO if the system requires near-continuous availability.

### 9.2. Backups Do Not Serve Read Traffic

Backup files are not a running PostgreSQL server. To serve queries, they must first be restored into a running cluster and verified.

### 9.3. Backups Can Lag Behind the Primary

If the latest backup is several hours old, restoring it without continuous WAL archiving only recovers up to that point. Replication can keep a copy much closer to the current state.

### 9.4. Backup and Replication Complement Each Other

Replication keeps an up-to-date node ready; backup lets you return to a historical state and recover when replicas are also affected.

---

## 10. What Is High Availability?

HA is a system design intended to minimize downtime when one or more components fail.

HA is more than enabling streaming replication. An HA architecture requires:

- Redundant database nodes.
- Failure detection.
- Rules to determine which node is authorized to be primary.
- Fencing of the old node.
- Promotion/leader transition.
- Traffic rerouting and endpoint updates.
- Post-failover verification.
- Rejoining/rebuilding replicas.
- Monitoring, alerting, and runbooks.
- Backup and DR to handle failures beyond HA's scope.

### 10.1. HA Is End-to-End

The database may promote successfully while the application remains down if connection pools hold stale connections, DNS has not updated, secrets are inaccessible, or load balancers fail to switch endpoints.

### 10.2. HA Can Be Automatic or Manual

An HA manager can automatically detect failures and promote a standby. Other systems may require operator approval for failover. Automatic is not always better; you must evaluate the risk of false positives and split brain.

### 10.3. HA Does Not Guarantee Zero Data Loss

With asynchronous replication, a standby may lack the most recent WAL. HA primarily reduces downtime; RPO depends on the replication policy and which node is selected.

### 10.4. HA Does Not Replace Backup

If a logical error is committed, HA may fail over to a replica containing the exact same error. Only backup/PITR enables rolling back to before the error.

---

## 11. Components in a PostgreSQL HA Architecture

### 11.1. Primary

The node that accepts writes from applications and generates WAL.

### 11.2. Standby

A node that receives and replays WAL. It can become the primary via promotion.

### 11.3. HA Manager

Monitors node health and replication state, makes failover decisions, and orchestrates role transitions. Examples include Patroni, repmgr, `pg_auto_failover`, or cloud-provider managed solutions. Behavior and limitations depend on the tool.

### 11.4. DCS / Quorum Store

Some HA managers use a distributed configuration store or consensus system to hold leader state and coordinate primary authority. Quorum helps prevent multiple nodes from claiming leadership during a network partition.

### 11.5. Fencing

Fencing prevents the old primary from continuing to accept writes after a new node is promoted. It can use power fencing, cloud APIs, storage leases, or appropriate network isolation.

### 11.6. Load Balancer / Service Endpoint

Routes applications to the current primary or separates read/write endpoints. This can use proxies, service discovery, DNS, or virtual IPs.

### 11.7. Monitoring

Tracks database, host, network, replication lag, WAL retention, backup status, storage, and application health.

### 11.8. Backup Repository

Stores base backups, WAL archives, logical dumps, and metadata independently from database nodes.

---

## 12. Failover and Switchover

### 12.1. Failover

Failover is transferring the primary role to a standby because the old primary suffered an incident or is no longer safe to serve traffic.

General sequence:

1. Detect that the primary is unhealthy.
2. Determine whether the old primary can be contacted or fenced.
3. Select an eligible standby.
4. Promote the standby.
5. Switch endpoints/traffic.
6. Verify writes and data.
7. Rebuild or rewind old nodes.

### 12.2. Switchover

Switchover is a planned role transition while the old primary is still healthy and operating.

The procedure typically includes:
- Draining or stopping new writes.
- Waiting for in-flight transactions to complete.
- Waiting for the standby to replay to the required position.
- Switching roles and promoting the standby.
- Redirecting traffic.
- Reconfiguring the old primary as a standby.

### 12.3. Comparison

| Criterion | Failover | Switchover |
| --- | --- | --- |
| Trigger | Incident / unsafe primary | Planned maintenance or transition |
| Old primary | May be unreachable | Typically still operational |
| Ability to wait for replay | Limited by the failure | Can coordinate waiting |
| Data loss | Possible with async replication | Can be minimized with proper sync |
| Downtime | Depends on detection/promotion/routing | Scheduled and controlled |
| Rejoining old node | May require rewind/rebuild | Can be reconfigured as standby |

### 12.4. Promotion Is Not the Entire Failover

A successful promotion only changes the database role. Applications, proxies, DNS, monitoring, and remaining standbys still need to be updated.

---

## 13. Failure Detection and False Positive Risks

### 13.1. Health Checks

Health checks can inspect processes, SQL queries, WAL progress, disk, network, or write capability. An open TCP port alone does not prove the database is ready to accept writes.

### 13.2. Network Partition

The primary may still be running while monitors or standbys cannot reach it. If a standby is promoted while the old primary continues accepting writes, split brain occurs.

### 13.3. Detection Timeouts

Timeouts that are too short easily trigger false failovers due to network jitter or high load. Timeouts that are too long prolong downtime. Tune them based on your failure model and SLA.

### 13.4. Quorum

An HA system needs sufficient evidence/quorum to decide which node is leader. Never allow a node to declare itself primary solely because it lost connectivity to another node.

### 13.5. Operator Decision

In systems with few nodes or no consensus manager, manual failover requires a runbook and an authorized operator to verify the state of the old primary.

---

## 14. Fencing and Split Brain

Split brain is a situation where two nodes simultaneously act as primary and accept writes independently.

### 14.1. Why Is It Dangerous?

Two nodes generate WAL on divergent branches. PostgreSQL does not automatically merge two divergent histories. Applications can write conflicting results.

### 14.2. Timelines Do Not Prevent Split Brain

Timelines help distinguish WAL branches after divergence has occurred. They do not automatically lock out the old node.

### 14.3. Fencing Before Promotion

Before promoting a standby, ensure the old primary can no longer accept writes. Fencing can be implemented at the infrastructure, storage, network, or HA manager layer.

### 14.4. Do Not Rely Only on Ping

A node that does not respond to ping may still be running the database and serving applications. Independent signals and reliable fencing are required.

### 14.5. After Split Brain Occurs

- Stop/fence the non-authoritative node.
- Preserve data directories and logs from both branches.
- Select one branch as the authoritative source per policy.
- Rewind or rebuild nodes that need to rejoin.
- Extract and reconcile data that existed only on the old branch if required by the business.
- Investigate the HA control plane and fencing failure.

---

## 15. RPO and RTO

RPO and RTO turn recovery goals into measurable design criteria.

### 15.1. RPO - Recovery Point Objective

RPO is the maximum amount of data the business accepts losing during an incident, usually expressed as a time interval.

Examples:
- RPO 0: target of zero loss for committed transactions under the promised semantics.
- RPO 5 minutes: acceptable to recover to a point at most 5 minutes before the incident.
- RPO 24 hours: daily backups may be part of the plan, though WAL/archive frequency still determines whether the target is met.

Actual RPO depends on backup/WAL archiving, replication mode, storage, and failure scenarios.

### 15.2. RTO - Recovery Time Objective

RTO is the target time for the service to return to an acceptable operational level.

Examples:
- RTO 1 minute: requires a ready standby and very fast failover/routing.
- RTO 30 minutes: restoring from backup may meet this in some systems, but actual timing must be measured.
- RTO 8 hours: longer manual DR procedures may be acceptable.

### 15.3. RPO/RTO Are Not Guaranteed by Settings Alone

Enabling `archive_mode` does not prove a 5-minute RPO. Having a standby does not prove a 1-minute RTO. Actual performance must be measured in restore and failover drills.

### 15.4. Example Matrix

| Mechanism | Typical RPO Impact | Typical RTO Impact |
| --- | --- | --- |
| Async replication | May lose WAL not yet sent to standby | Fast promotion if standby is ready |
| Sync replication | Can protect commits per sync policy | May increase commit wait if standby is lost |
| Base backup | Data point of the backup | Copy/restore duration |
| WAL archive | Gap between archived WAL segments | Replay time to target |
| PITR | Can pick a point close to error if WAL is intact | Restore + replay can be slow |
| HA manager | Does not by itself ensure data durability | Reduces detection/promotion/routing time |
| Restore drill | Verifies achievable RPO | Measures actual RTO |

---

## 16. Failure Domains and Replica/Backup Placement

A failure domain is the scope of components that can be simultaneously affected by a single failure.

### 16.1. Process Failure

PostgreSQL process or OS service stops. Another standby on the same host does not help if the host goes down.

### 16.2. Host Failure

Physical machine or VM fails. Replicas on other hosts can continue.

### 16.3. Storage Failure

Disk/volume corruption or inaccessible filesystem. Replicas on independent volumes reduce risk.

### 16.4. Rack/Zone Failure

Power, network, or infrastructure outage in a rack or availability zone. A replica in another zone improves HA/DR.

### 16.5. Region Failure

Loss of an entire region or control plane. Replicas and backups in another region may be required.

### 16.6. Credential/Control-Plane Failure

A compromised admin account can delete the primary, replicas, and backups if all share the same credentials/permissions. Separate credentials, enforce MFA, use immutable backups, and retain audit logs.

### 16.7. Human/Logic Failure

Accidental DELETE/DROP statements, faulty migrations, application bugs, or bad data can replicate. Historical backups allow rolling back.

### 16.8. Placing Backups Alongside the Primary

A backup on the same volume does not protect against volume loss. An archive bucket with shared deletion rights in the same account can be wiped alongside the database.

---

## 17. Basic Architecture: Primary and Standby in the Same Region

```text
Application
    |
    v
Write endpoint
    |
    v
Primary (Zone A)
    |
    | Physical streaming replication
    v
Standby (Zone B)

Backup job
    |
    +--> Base backup repository
    +--> WAL archive repository
```

### 17.1. Benefits

- Primary transition when a host or zone fails.
- Standby can serve read-only workloads.
- Replication lag is typically lower than across distant regions.

### 17.2. Limitations

- A regional outage can still affect both zones.
- Logical errors are replicated.
- The backup repository still needs to be independent.
- An HA manager, routing, and fencing are still required.

### 17.3. Async or Sync?

Sync can reduce data loss but increases commit latency and adds dependency on the standby and network. Async lowers latency but may lose some WAL during failover.

### 17.4. Multiple Standbys

You can have one synchronous standby for durability and one or more asynchronous standbys for reads/DR. You must define which nodes are eligible for promotion and the selection policy.

---

## 18. HA Architecture Combined with Cross-Region DR

```text
                  Region A
             +----------------+
Application -> HA endpoint
             | Primary        |
             | Standby A2     |
             +-------+--------+
                     |
                     | WAL replication / archive
                     v
                  Region B
             +----------------+
             | DR standby     |
             | Backup copy    |
             | WAL archive    |
             +----------------+

Independent backup repository:
  - Base backups
  - WAL archives
  - Immutable/offsite copy
  - Restore metadata
```

### 18.1. Intra-Region HA

A standby in the same region or a different zone handles host/zone failures with low latency.

### 18.2. Cross-Region DR

A replica in another region addresses regional outages. High network latency often makes asynchronous replication more practical, depending on RPO.

### 18.3. Offsite Backups

Backups must reside in an independent failure domain with separate credentials and sufficient retention.

### 18.4. Cross-Region Failover Requires a Separate Runbook

Verify network partitions, DNS/routing, data lag, archive state, fencing of the old primary region, and the ability to return to the original region.

### 18.5. Failback Is Not Simply Reverting DNS

After a DR promotion, a new timeline is created. The old primary must be rewound or rebuilt and rejoined as a standby before considering switching the role back.

---

## 19. Backup Retention and Protection Against Logical Errors

### 19.1. Retention Window

Retain backups long enough to catch delayed error detection. If a logical error is discovered after 10 days while backup/WAL retention is only 3 days, a valid recovery target may no longer exist.

### 19.2. Base Backup Cadence

More frequent backups reduce the amount of WAL to replay and can lower RTO, at the cost of higher storage, network, and backup processing overhead.

### 19.3. WAL Archive Cadence

WAL segments are usually archived when completed; `archive_timeout` can force segment archiving during low-write workloads. Balance freshness against overhead.

### 19.4. Immutable Backups

Use object lock/immutability or a repository where the same credentials cannot delete or overwrite backups during the retention window if ransomware protection is required.

### 19.5. Credential Separation

Backup operators, database admins, and application users should have distinct permissions. Never use a single credential capable of wiping both the database and all backups.

### 19.6. Supplementary Logical Exports

Periodic logical dumps can help with object-level recovery and migrations. They supplement physical backups rather than replacing them.

### 19.7. Backup Catalog

Store metadata about:
- Backup start/end time.
- PostgreSQL version.
- System identifier.
- Timeline.
- WAL start/stop LSN.
- Tablespaces.
- Encryption/key references.
- Checksums/manifests.
- Retention expiry.
- Restore test results.

---

## 20. Backup Consistency and Restore Verification

### 20.1. Successful Backup Completion Is Not Enough

A tool may report backup completion even though the archive is missing WAL, file permissions are wrong, or the restore target fails to start.

### 20.2. Integrity Checks

Use checksums/manifests or backup tool verification features to confirm files were not corrupted during transfer or storage.

### 20.3. Restore into an Isolated Environment

Never test restores directly on production. Use a separate data directory/VM/cluster and prevent accidental connections to production.

### 20.4. Verify PostgreSQL Startup

Inspect logs, confirm recovery finishes cleanly, and verify there are no missing WAL or page errors.

### 20.5. Verify Business Data

Check key row counts, totals, foreign-key consistency, and business invariants. A server starting up does not alone prove data correctness.

### 20.6. Application Smoke Tests

Run appropriate queries and read checks. Ensure restore tests do not send real emails, trigger payments, or cause external side effects.

### 20.7. Measure RTO

Measure from incident/restore start per operational definition until the service reaches acceptable availability, including copy, replay, validation, routing, and application warm-up.

### 20.8. Measure RPO

Identify the latest recoverable timestamp/LSN and compare it to the incident timestamp. Record the evidence.

---

## 21. HA Is Not Just Database Failover

Some database systems promote successfully while the application remains down.

### 21.1. Connection Pools

Connection pools may hold stale connections to the old primary. They must detect connection failures, reconnect, and verify the new write endpoint.

### 21.2. DNS Caching

Clients may cache DNS longer than TTL. Updating DNS does not mean every client switches to the new endpoint immediately.

### 21.3. Load Balancers / Proxies

Proxies must know which node is primary. If a health check only tests TCP connectivity, it may route writes to a read-only standby.

### 21.4. Read/Write Routing

Clearly separate read endpoints and write endpoints. Prevent applications from mistakenly sending writes to a read replica.

### 21.5. Secrets and Certificates

The new primary must have access to the required secrets, TLS certificates, KMS, and network policies.

### 21.6. Background Jobs

Workers/cron jobs might run on multiple nodes after failover. Ensure jobs use leader locks or idempotency to avoid duplicate execution.

### 21.7. External Systems

Database HA does not automatically protect message queues, object storage, payment services, or caches. Assess dependencies across the entire application.

---

## 22. Read Replicas and Read Scaling

Replicas can handle part of the read workload to reduce load on the primary.

### 22.1. Stale Reads

Asynchronous standbys can lag. A query immediately following a write to the primary might not yet see the row on a standby.

### 22.2. Read-After-Write

If the application requires immediately reading newly written data, route the query to the primary or use appropriate synchronization mechanisms. `remote_apply` can support specific semantics at the cost of higher latency.

### 22.3. Not All Queries Are Suitable

Heavy queries on a standby can conflict with WAL replay, increasing replay lag or getting canceled. Balance reporting workloads against replication freshness.

### 22.4. Replicas Do Not Increase Write Capacity

Physical standbys cannot accept independent writes. Scaling writes requires a different architecture and handling consistency/sharding at the application or distributed layer.

### 22.5. Read Scaling Does Not Equal HA

Having multiple read replicas without failover, fencing, and routing policies is not complete HA.

---

## 23. Backup, Replication, and HA in Failure Scenarios

| Incident | How Replication Helps | How Backup Helps | How HA Helps |
| --- | --- | --- | --- |
| Primary process crash | Standby holds a copy | Restore if needed | Detects and promotes |
| Host power loss | Replica on another host | Recover when needed | Switches endpoint |
| Primary disk failure | Standby can serve traffic | Restore cluster from backup | Failover and rebuild |
| Zone outage | Replica in another zone | Backup outside the zone | Orchestrates node switch |
| Region outage | DR replica if present | Offsite backup | DR failover |
| Accidental DELETE | Usually replicates the error | PITR to before DELETE | Does not fix data automatically |
| DROP DATABASE | May replicate the change | Restore from backup | May switch to replica, but error remains |
| Ransomware / backup deletion | May be affected by shared credentials | Immutable/offsite backup | Failover is insufficient |
| WAL archive loss | Online replica may still retain data | Remaining backup has limited recovery | Does not automatically restore WAL |
| Standby disk failure | Primary keeps serving | Rebuild standby | Maintains service if primary is healthy |
| Both primary and standby zone lost | No copy left in same zone | Offsite backup / DR replica | DR plan |
| Two primaries accepting writes | Two branches diverge | Backup aids recovery | Fencing/quorum must prevent this |
| Application bug writes bad data | Corruption spreads to replicas | PITR/backup | HA does not remove the bug |
| Compromised credentials | Attacker can write/delete | Credential separation / immutable backup | Control plane must be protected |

### 23.1. One Mechanism Does Not Solve Every Failure Mode

The design must map each incident to prevention, detection, and recovery measures.

### 23.2. Failure Modes Can Compound

For example, a region outage combined with compromised credentials or backup repository issues. Testing a single-node crash does not represent all DR scenarios.

---

## 24. Tools and Deployment Options

### 24.1. Native PostgreSQL

PostgreSQL provides:
- Physical streaming replication.
- Synchronous replication.
- Replication slots.
- WAL archiving.
- Base backups via `pg_basebackup`.
- Recovery/PITR.
- Promotion and system views.

Native PostgreSQL provides the primitives; organizations must design orchestration, fencing, routing, and backup management.

### 24.2. Patroni

Patroni is an HA management solution for PostgreSQL, typically using a DCS to coordinate leader leases and failover. You still need to deploy the DCS, fencing/role checks, routing, and separate backups.

### 24.3. repmgr

repmgr provides tools to manage/monitor replication and assist with configured failover/switchover. Topologies and failure behaviors must be thoroughly tested.

### 24.4. pg_auto_failover

`pg_auto_failover` coordinates PostgreSQL nodes via a monitor and state machine. Designs still require understanding quorum, networking, and backups.

### 24.5. Managed PostgreSQL

Cloud providers may include built-in HA, backups, and PITR. Review SLAs, failover behavior, backup retention, regional limits, export/restore options, and access controls.

### 24.6. Do Not Choose a Tool Based Solely on the Label HA

Compare:
- Failure detection.
- Consensus/quorum.
- Fencing.
- Promotion safety.
- Synchronous replication support.
- Rejoin/rewind.
- Backup/PITR integration.
- Monitoring and auditing.
- Upgrades/maintenance.
- Operational complexity and support.

---

## 25. Designing a Three-Layer Coordinated Strategy

A sound design typically combines three complementary layers:

### 25.1. Replication Layer

- Primary and at least one standby.
- Decide between physical and logical.
- Choose async/sync based on RPO and latency.
- Configure replication slots and retention appropriately.
- Monitor WAL receive/flush/replay.

### 25.2. HA Layer

- Health checks.
- Leader/quorum policy.
- Fencing.
- Promotion.
- Write endpoint routing.
- Rejoin/rebuild.
- Runbooks and drills.

### 25.3. Backup/DR Layer

- Periodic base backups.
- Continuous WAL archiving.
- Supplementary logical dumps when needed.
- Offsite/immutable copies.
- Retention aligned with RPO/compliance.
- Restore drills and RTO/RPO measurement.

### 25.4. Coordination Diagram

```text
                    Application
                        |
                  Write endpoint
                        |
                        v
                 HA-managed primary
                    /        \
                   / WAL      \ WAL
                  v            v
            Standby A       Standby B
             (sync)          (async / DR)

Primary / standby backup source
              |
              +---- Base backup ------> Backup repository
              |
              +---- WAL archive ------> Offsite immutable storage
                                            |
                                            v
                                      PITR / DR restore

HA manager:
  health + quorum + fencing + promotion + routing
```

### 25.5. Separating Failure Domains

Place at least one backup outside the primary's host/zone/region, and separate backup deletion rights from database admin privileges.

### 25.6. Do Not Put Every Role on a Single Node

A standby can serve as both an HA candidate and a backup source, but backup load must be throttled and losing a single node must not strip away all protection layers.

---

## 26. Design Examples by RPO/RTO Requirements

### 26.1. Small Business System

Requirements:
- RPO 15 minutes.
- RTO 2 hours.
- Moderate workload.
- Manual DR is acceptable.

Design may include:
- Periodic base backups.
- Continuous WAL archiving to object storage.
- One asynchronous standby if needed to reduce recovery time.
- Quarterly restore drills.
- Alerts for archive lag and backup age.

Measure actual restore times; do not assume a 15-minute RPO just because a backup schedule exists.

### 26.2. Critical Transactional Application in One Region

Requirements:
- Very low RPO.
- RTO of a few minutes.
- Must not lose acknowledged commits when a single host fails.

Design may include:
- Primary and synchronous standby in different failure domains.
- HA manager with quorum/fencing.
- Failover-capable write endpoint.
- Independent base backup/WAL archive.
- Testing node failures and network partitions.
- Monitoring commit latency, sync state, and replay.

### 26.3. Multi-Region Service

Requirements:
- Survive a region outage.
- RPO of a few minutes.
- RTO under one hour.
- DR region can serve traffic after a transition procedure.

Design may include:
- Local HA in the primary region.
- Async physical standby in the DR region.
- Offsite WAL archives and base backups.
- DR runbook, fencing of old region, DNS/traffic switch.
- Testing network partitions and region outages.
- Failback plan using rewind/rebuild.

### 26.4. Do Not Copy One Configuration for Every System

Account for inter-zone latency, throughput, data size, backup windows, compliance, storage costs, and operational capacity.

---

## 27. Monitoring for Replication, Backup, and HA

### 27.1. Replication Monitoring

On the primary:

```sql
SELECT
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
FROM pg_catalog.pg_stat_replication;
```

Track state, LSN gaps, lag trends, and `sync_state`. Some columns depend on PostgreSQL version.

### 27.2. Standby Monitoring

```sql
SELECT
    pg_is_in_recovery(),
    pg_last_wal_receive_lsn(),
    pg_last_wal_replay_lsn(),
    pg_last_xact_replay_timestamp();
```

### 27.3. Slot Monitoring

```sql
SELECT *
FROM pg_catalog.pg_replication_slots;
```

Track inactive duration, `restart_lsn`, `wal_status`, and retained WAL where appropriate columns exist.

### 27.4. Archive Monitoring

```sql
SELECT *
FROM pg_catalog.pg_stat_archiver;
```

Track `archived_count`, `failed_count`, `last_archived_time`, and `last_failed_time`. Combine with repository inventory and checksums.

### 27.5. Backup Freshness

Track:
- Timestamp of the most recent successful base backup.
- Backup completion duration.
- WAL start/stop LSN.
- Archive continuity up to the present.
- Repository free space.
- Backup checksum/verification.
- Most recent restore test.

### 27.6. HA Monitoring

Track:
- Current leader.
- Quorum/DCS health.
- Fencing status.
- Failover events.
- Promotion duration.
- Write endpoint target.
- Replica rejoin status.
- Application connection errors.

### 27.7. Goal-Oriented Alerts

Examples:
- Backup age exceeds RPO threshold.
- Archive gap detected.
- Standby lag exceeds policy.
- Required synchronous standby is missing.
- Slot retention nears limit.
- WAL filesystem nearly full.
- HA manager loses quorum.
- Failover occurred but traffic has not switched.
- Restore drill is overdue.

---

## 28. Conceptual Failover Runbook

### 28.1. Confirm Primary Failure

Use multiple independent signals: database health, host health, storage, network, and application behavior. Distinguish a process crash from a network partition.

### 28.2. Identify Eligible Node for Promotion

Check standby state, timeline, receive/flush/replay LSN, sync status, and WAL archive. Assess potential data loss.

### 28.3. Fence the Old Primary

Ensure the old node can no longer accept writes. Use the HA manager/quorum and infrastructure fencing.

### 28.4. Promote the Standby

Execute via the HA manager or tested runbook. Confirm `pg_is_in_recovery()` returns false and the new primary accepts writes.

### 28.5. Switch Traffic

Update proxies/service discovery/DNS or endpoints. Refresh connection pools and background workers.

### 28.6. Verify Business Operations

Run smoke tests and verify critical transactions. Monitor commit errors, latency, and application logs.

### 28.7. Rejoin Old Nodes

Use `pg_rewind` when eligible or take a fresh base backup. Never start the old primary as a second primary.

### 28.8. Document the Incident

Record timeline ID, LSN, fork point, promoted node, fencing evidence, actual RPO, downtime, and rejoin method.

---

## 29. Restore and PITR Runbook

### 29.1. Identify the Point of Failure

Find the timestamp, transaction, restore point, or LSN prior to data corruption.

### 29.2. Select a Base Backup

Pick a valid backup matching the cluster/version with a WAL path reaching the recovery target.

### 29.3. Verify Archive Continuity

Confirm required WAL segments and timeline history files exist, pass checksums, and are accessible.

### 29.4. Restore into a Separate Environment

Do not overwrite the running primary. Restore the base backup into a separate data directory/host.

### 29.5. Configure Recovery

Set appropriate `restore_command`, `recovery_target_time`/LSN/name, and `recovery_target_timeline`. In PostgreSQL 12+, archive recovery typically uses `recovery.signal`.

### 29.6. Pause and Verify

You can configure `recovery_target_action=pause` to verify data before promoting.

### 29.7. Promote and Switch Applications

Promote only after confirming the correct data branch. Promotion creates a new timeline; update the archive and standby topology accordingly.

### 29.8. Preserve the Original State for Investigation

Keep the data directory/backup of the corrupted state per retention policy if root cause analysis is needed.

---

## 30. Disaster Recovery and Failback

### 30.1. DR Restores Service After Major Incidents

DR typically addresses region outages, site/storage loss, or security incidents. It can use a DR standby or restore from backups.

### 30.2. DR Failover

If promoting a DR standby, check received/replayed WAL and accept the resulting RPO. Fence the old region before opening writes in the DR region.

### 30.3. Backup Restore DR

If no usable standby exists, restore a base backup and replay the WAL archive. RTO depends on data size, network, storage, and replay volume.

### 30.4. Failback

When the old site recovers:
- Do not automatically accept writes.
- Rewind/rebuild as a standby from the current primary.
- Wait for catch-up and verify.
- Plan a controlled switchover if moving back to the original site.

### 30.5. DR Drills

Run scheduled drills. An untested runbook may lack permissions, network rules, DNS updates, KMS access, or capacity.

---

## 31. Common Design Mistakes

| Mistake | Consequence | Improvement |
| --- | --- | --- |
| Treating a standby as a backup | Logical errors propagate to standby | Maintain base backups + WAL archives |
| Backups only, no standby | Slow restore when primary fails | Add HA/replica if RTO demands it |
| Replication enabled without failover | Redundant node cannot safely take over | HA manager/runbook/fencing |
| Auto-failover without fencing | Split brain | Quorum and independent fencing |
| All nodes in one zone | Zone outage breaks HA | Distribute across failure domains |
| Backups on primary's volume | Lost together | Offsite/independent repository |
| Backups share deletion permissions | Compromised credentials wipe backups | Separate credentials / immutability |
| Never testing restores | Broken backups go undetected | Restore drills |
| Tracking only backup job success | Unknown WAL continuity/restorability | End-to-end restore verification |
| Claiming RPO 0 with async replication | Recent WAL may be lost | Use sync policy or revise RPO |
| Sync replication ignoring availability | Commits block when standby fails | Design quorum/failure policy |
| Not monitoring slot retention | `pg_wal` fills up | Slot/disk alerts |
| Not monitoring archiving | PITR chain breaks | Archive continuity alerts |
| Changing only DNS on failover | Client caches/pools stay on old endpoint | Proxy/service discovery/reconnect |
| No rejoin plan | Old primary diverged | `pg_rewind`/rebuild runbook |
| Not separating DR from HA | No recovery path on region loss | DR site and offsite backups |
| Ignoring restore bandwidth | RTO exceeds target | Capacity/restore testing |
| No dependency inventory | Restore lacks KMS/extensions/secrets | Backup catalog/runbook |
| Not testing logical errors | Unprepared for PITR | Practice restores before incidents |
| Not measuring RPO/RTO | SLAs are mere assumptions | Record evidence from drills |

---

## 32. Lab 1: Observing How Replication and Backup Differ

This lab requires a separate PostgreSQL primary and standby.

### 32.1. Create a Test Table on the Primary

```sql
CREATE TABLE IF NOT EXISTS public.ha_backup_lab (
    id BIGINT PRIMARY KEY,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO public.ha_backup_lab(id, note)
VALUES (1, 'before-backup')
ON CONFLICT (id) DO UPDATE
SET note = EXCLUDED.note;
```

### 32.2. Wait for Standby Replay

Check on the standby:

```sql
SELECT *
FROM public.ha_backup_lab
WHERE id = 1;
```

### 32.3. Create a Logical Dump

```bash
pg_dump -Fc -d appdb -f ha_backup_lab.dump
```

Run from a host with appropriate permissions and connection access. The command illustrates dumping the entire `appdb` database.

### 32.4. Simulate a Logical Error in the Lab

```sql
DELETE FROM public.ha_backup_lab
WHERE id = 1;
```

Wait for standby replay and observe that the row disappears on the standby as well.

### 32.5. Restore the Dump into a Separate Database

Create a target database and run `pg_restore`. Confirm the row prior to DELETE still exists in the backup.

### 32.6. Conclusion

The replica reflects the primary's latest state; the backup preserves the state at backup time. Both mechanisms serve different goals.

---

## 33. Lab 2: Observing RPO and Replication Modes

This lab requires a primary and standby, with synchronous replication configured appropriately if testing sync behavior.

### 33.1. Record Replication State

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

### 33.2. Write a Test Transaction

```sql
INSERT INTO public.ha_backup_lab(id, note)
VALUES (2, 'commit-test');
```

Record the commit timestamp and observe the LSN.

### 33.3. Compare Async and Sync in the Lab

Adjust configuration following the lab runbook, never in production. Measure commit latency and standby flush/replay progress.

### 33.4. Simulate Failover

Only after fencing the lab primary, promote the standby. Confirm the `commit-test` row exists on the promoted node.

### 33.5. Interpretation

Async can leave recent commits absent from the standby; sync remote flush can protect acknowledged commits per policy if the right standby is promoted. Do not extrapolate one test into a guarantee for every failure scenario.

---

## 34. Lab 3: Backup and PITR

### 34.1. Enable WAL Archiving

Configure `archive_mode` and `archive_command` on the lab primary. Verify the archive destination.

### 34.2. Take a Base Backup

Use `pg_basebackup` or a compatible backup tool. Record metadata and timeline.

### 34.3. Create a Restore Point

```sql
SELECT pg_create_restore_point('before_lab_delete');
```

Record the LSN/timestamp.

### 34.4. Write Data After the Restore Point

```sql
INSERT INTO public.ha_backup_lab(id, note)
VALUES (3, 'after-restore-point');
```

### 34.5. Restore to a Separate Copy

Use the base backup and WAL archive to recover to the restore point, with `recovery.signal` and recovery settings matching your version.

### 34.6. Verify

Rows before the target are present; rows after the target do not appear if recovery stops before them.

### 34.7. Measure Timing

Record time for copying the base backup, replaying WAL, validation, and application readiness. Use this to estimate actual RTO.

---

## 35. Lab 4: Failover and Routing

This lab requires an HA manager or a two-node environment with a controlled promotion procedure.

### 35.1. Record Initial State

Save primary identity, standby state, `sync_state`, LSN, endpoint, and application health.

### 35.2. Test Health Checks

Simulate a primary process failure or network partition in the lab. Observe whether the HA manager distinguishes the two cases.

### 35.3. Fencing

Verify the old primary can no longer accept writes before promotion.

### 35.4. Promote the Standby

Use the HA manager or runbook. Confirm `pg_is_in_recovery()` is false.

### 35.5. Switch Traffic

Update the write endpoint/proxy/service discovery. Verify new clients can connect and write.

### 35.6. Rejoin the Old Node

Use `pg_rewind` if eligible or a new base backup. Confirm it rejoins as a standby.

### 35.7. Measure Downtime

Record time spent on detection, fencing, promotion, routing, and application recovery. Do not measure `pg_promote` duration alone.

---

## 36. Lab 5: Backup Failure Domains

### 36.1. Draw the Topology

Label hosts, zones, regions, storage accounts, credentials, and backup repositories.

### 36.2. Identify Shared Points of Failure

Ask: if Zone A, the cloud account, KMS key, or admin credentials are lost, which primary, replica, and backups remain accessible?

### 36.3. Check Permissions

Verify whether the database admin can delete backups, whether the backup service can delete the database, and whether immutable retention is enforced.

### 36.4. Test Offsite Restore

Use an isolated environment to fetch the base backup/WAL from the offsite repository and restore.

### 36.5. Record RTO/RPO

Measure download, restore, replay, and validation times. Document any missing dependencies such as credentials, extensions, certificates, or network access.

---

## 37. Practice Exercises

### Exercise 1 — Definitions

Distinguish replication, backup, and HA using one operational question for each mechanism.

### Exercise 2 — Replication Is Not a Backup

Explain why an accidental DELETE on the primary also appears on a physical standby.

### Exercise 3 — Backup Is Not HA

Why doesn't a good base backup allow the application to keep writing immediately when the primary crashes?

### Exercise 4 — HA Is Not a Backup

Describe how a logical error can propagate across an HA cluster and how to recover to before the error.

### Exercise 5 — Durability and Recoverability

Distinguish these two goals and list the related PostgreSQL mechanisms.

### Exercise 6 — Physical Replication

Draw the WAL sender/receiver and startup replay path.

### Exercise 7 — Logical Replication

Compare logical and physical replication across scope, schemas, DDL, and cluster objects.

### Exercise 8 — Async Replication

Explain the scenario where the primary acknowledges COMMIT before the standby receives the WAL.

### Exercise 9 — Sync Replication

Compare `remote_write`, `remote_flush`, and `remote_apply`. State the latency trade-offs.

### Exercise 10 — Synchronous Availability

What can happen to commits when a synchronous standby loses connectivity?

### Exercise 11 — Base Backup

State the goal and components of a physical base backup.

### Exercise 12 — Logical Dump

When is `pg_dump` more suitable than a base backup? Why does it not replace physical PITR?

### Exercise 13 — WAL Archive

Explain why a WAL archive is needed for PITR from a base backup to a recovery target.

### Exercise 14 — Restore Drill

Design a test to restore a backup and verify application data.

### Exercise 15 — RPO

A business accepts losing at most 5 minutes of data. Which configurations and metrics must be examined?

### Exercise 16 — RTO

A service must be back online within 2 minutes. Why might restoring from backup be insufficient?

### Exercise 17 — Failure Domains

Draw the failure domains for the primary, standby, storage, zone, and backup repository.

### Exercise 18 — Failover

Describe the sequence of detecting primary failure, fencing, promotion, and routing.

### Exercise 19 — Switchover

Explain why a planned switchover usually reduces data loss more easily than an unexpected failover.

### Exercise 20 — Split Brain

Describe a network partition causing two primaries to accept writes and the role of fencing.

### Exercise 21 — HA Manager

What state does an HA manager need to store, and which actions does it coordinate?

### Exercise 22 — Quorum

Explain why quorum reduces the risk of two nodes being elected leader simultaneously.

### Exercise 23 — Connection Routing

After promotion, why might updating DNS alone be insufficient for applications to switch to the new primary?

### Exercise 24 — Read Replicas

A query reading immediately after a write does not see the row on a standby. Explain replication lag and routing options.

### Exercise 25 — DR Region

Design an async standby in another region and list the fencing/routing steps when the primary region fails.

### Exercise 26 — Backup Immutability

Propose a way to separate backup deletion privileges from the database administrator.

### Exercise 27 — Backup Retention

A logical error is discovered after 12 days. What must backup/WAL retention satisfy?

### Exercise 28 — Ransomware

Why can replicas be affected alongside the primary? Propose backup isolation and credential separation.

### Exercise 29 — Monitoring

Design a dashboard distinguishing replication lag, archive lag, backup freshness, and HA manager health.

### Exercise 30 — Disk Failure

The primary disk fails while the standby is healthy. Describe failover and how to create a new standby afterward.

### Exercise 31 — Logical Incident

A migration accidentally drops a table and replicates. Establish a PITR procedure to recover the table without losing subsequent valid writes.

### Exercise 32 — Synchronous Standby Down

Evaluate the trade-off between blocking commits, changing sync policy, and availability. State the risks of each choice.

### Exercise 33 — Multi-Zone

Design a primary, synchronous standby, and asynchronous DR standby across distinct failure domains.

### Exercise 34 — Restore Capacity

A 4 TB base backup must be restored within 45 minutes. Calculate the required average throughput and list other time components to measure.

### Exercise 35 — Backup Source on Standby

State the benefits and risks of taking a base backup from a standby instead of the primary.

### Exercise 36 — HA Without Backup

Assess the risks of a system with three replicas but no base backups or WAL archives.

### Exercise 37 — Backup Without HA

Assess the risks of a system with good backups but only a single primary and a 1-minute RTO.

### Exercise 38 — Failback

After a DR promotion, describe how to bring the old site back as a standby and then perform a planned switchover.

### Exercise 39 — Testing

Design a quarterly DR drill schedule covering host failure, network partition, logical error, and region loss.

### Exercise 40 — End-to-End Design

An order processing system requires RPO under 1 minute, RTO under 5 minutes, 14-day PITR, and cross-region DR. Propose a replication topology, synchronous/asynchronous policy, HA manager, fencing, backup repository, WAL archive, monitoring, failover/failback, and restore drills. Analyze trade-offs in latency, availability, cost, and complexity.

---

## 38. Design and Operations Checklist

| Question | What to Confirm |
| --- | --- |
| What goal does replication serve? | HA/read scaling/DR/migration |
| Physical or logical? | Scope and semantics |
| Async or sync? | RPO/latency |
| Is the standby in another failure domain? | Host/zone/region |
| Is WAL sender/receiver monitored? | Replication views |
| Receive/flush/replay lag? | LSN and time metrics |
| Do replication slots have capacity? | Slot retention |
| Is WAL archiving continuous? | Archive inventory/checksums |
| Latest base backup? | Backup catalog |
| Has the backup passed a restore test? | Restore evidence |
| Is the PITR target reachable? | WAL continuity |
| Is backup independent of primary? | Failure domain |
| Are backups immutable? | Delete/write protection |
| Are credentials separated? | Least privilege |
| Is RPO defined? | Business requirement |
| Is RTO defined? | Business requirement |
| Is RPO measured? | Latest recoverable point |
| Is RTO measured? | Restore/failover drill |
| Does the HA manager have quorum? | Leader state |
| Does fencing work? | Old primary isolation |
| Has failover been tested? | Promotion/routing |
| Has switchover been tested? | Planned transition |
| Does the write endpoint auto-update? | Proxy/DNS/service discovery |
| Do connection pools reconnect? | Application behavior |
| Are duplicate background jobs prevented? | Leader lock/idempotency |
| How does the old primary rejoin? | `pg_rewind`/base backup |
| Does the DR region have secrets/KMS? | Dependencies |
| Is restore capacity sufficient? | Network/storage throughput |
| Is archive retention long enough? | Backup dependency |
| Does monitoring alert on trends? | Capacity and freshness |
| Are incident runbooks updated? | Ownership/escalation |
| Are DR drills scheduled? | Evidence |
| Is data validated after restore? | Business invariants |
| Is there a failback plan? | Rejoin and switchover |

## Conclusion

Replication, backup, and High Availability are three related protection layers that cannot substitute for one another.

Key principles to remember:

1. **Replication keeps an up-to-date copy.** It supports read scaling, HA, and DR, but usually propagates erroneous changes and accidental deletions as well.
2. **Backups preserve a recoverable state.** Base backups combined with WAL archives enable PITR; logical dumps supplement object-level recovery and migrations.
3. **HA keeps the service running.** It requires standbys, failure detection, quorum, fencing, promotion, routing, monitoring, and runbooks.
4. **Synchronous replication can reduce RPO.** In return, commits may experience higher latency or block when standbys or networks are unavailable.
5. **Asynchronous replication may lose recent WAL on failover.** Actual RPO must be stated and tested.
6. **Backups must be in an independent failure domain.** Separate storage, credentials, and deletion rights; use immutable/offsite copies when required.
7. **PITR needs a base backup and continuous WAL.** Missing a single required segment in the archive can halt recovery before the target.
8. **Failover requires fencing.** Never promote a standby solely because the primary is unresponsive; a network partition can cause split brain.
9. **The application is part of HA.** Connection pools, DNS, proxies, background jobs, and secrets must all function after promotion.
10. **RPO/RTO must be measured.** Backup age, WAL lag, restore time, and failover time require evidence from drills.
11. **DR requires a separate failure domain.** A replica in another zone does not automatically protect against a full region outage or credential compromise.
12. **Restore drills prove backups are usable.** Periodically verify startup, business data, application behavior, and recovery duration.

A resilient PostgreSQL system combines an up-to-date copy for fast failover, independent backups to revert to a valid state, and HA mechanisms to detect failures, transition roles safely, and bring applications back into service. Only when all three layers are designed against the same RPO/RTO goals and tested under realistic failure scenarios can an organization rely on the service's availability and recoverability.

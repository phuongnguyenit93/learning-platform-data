# Defining RPO/RTO and Building a Recovery Verification Plan

## Objectives

After this lesson, you will be able to:

- Distinguish RPO, RTO, incident detection time, and service recovery time.
- Translate business requirements into measurable recovery objectives for each MySQL system.
- Choose a backup strategy, binary log retention, and point-in-time recovery approach aligned with RPO/RTO.
- Calculate expected recovery time from actual steps and dependencies.
- Design restore tests, incident drills, and evidence-backed acceptance criteria.
- Maintain the recovery plan, ownership, and update procedures as the system evolves.

## 1. Why Define RPO and RTO?

Backups only have operational value when an organization knows to what point in time data must be recovered and how quickly the service must be brought back online. Those two questions correspond to **Recovery Point Objective (RPO)** and **Recovery Time Objective (RTO)**.

- **RPO — Recovery Point Objective:** the maximum amount of data a business accepts losing, measured in time prior to the incident. An RPO of 15 minutes means that when recovering, the data can miss at most roughly the last 15 minutes of transactions.
- **RTO — Recovery Time Objective:** the maximum acceptable duration to restore a service to a defined operating level after an incident. An RTO of 2 hours means the service must meet operational criteria within 2 hours from the start milestone defined in the plan.

These two objectives are independent. A system may recover in 10 minutes yet lose data from the preceding 6 hours; a good RTO does not imply a good RPO. Conversely, it is possible to preserve data nearly up to the moment of the incident while taking an entire day to provision servers and verify the application.

For example, an online store might set targets as follows:

| Service Group | Target RPO | Target RTO | Rationale |
|---|---:|---:|---|
| Orders and payments | 5 minutes | 1 hour | Lost transactions directly impact customers and reconciliation |
| Inventory | 15 minutes | 2 hours | Needs fast recovery to avoid overselling stock |
| Internal reporting | 24 hours | 1 business day | Can be partially reconstructed from transactional data once core systems stabilize |

These numbers only illustrate how to group services. Business owners, operations, security, and risk management must agree on targets based on business impact, regulatory obligations, cost, and technical capability.

## 2. Getting the Timelines Right

To measure RPO/RTO, you must first agree on the start and end points. A plan may use the following milestones:

1. **T0 — Incident begins:** data is accidentally deleted, a disk fails, a server loses connectivity, or signs of compromise appear. Some incidents are only detected after a delay.
2. **T1 — Detection and confirmation:** monitoring or an operator detects the issue, classifies severity, and confirms recovery is required.
3. **T2 — Decision and plan activation:** an authorized person declares an incident, selects the recovery option, and assigns roles.
4. **T3 — Infrastructure ready:** servers, storage, networking, DNS, certificates, and required secrets are ready.
5. **T4 — Data recovered:** the backup is loaded, binary logs are replayed to the target point, and initial consistency checks are complete.
6. **T5 — Application verified:** functional, data, privilege, integration, and representative load checks pass.
7. **T6 — Service restored:** traffic is routed to the recovered system and stakeholders are notified.

An organization may define RTO from T0 or T1 to T6. What matters is explicitly recording which milestone is used for measurement, because incident detection time can also drag out and cause damage. RTO is often tracked alongside Mean Time to Detect (MTTD) and Mean Time to Recover (MTTR), though these metrics do not replace the RTO target.

RPO must also have a clear reference point. When an incident occurs at 14:00 and the best recovery contains committed transactions up to 13:54, the recovery point lag is 6 minutes. If the RPO is 5 minutes, that recovery missed the objective, even if the server came back online very quickly.

## 3. Turning Business Requirements into Measurable Objectives

Do not pick RPO/RTO simply because the backup tool can run hourly or because a server can restore in 30 minutes. Start from business impact.

### 3.1. Identifying Outage Impact

For each MySQL system, discuss with the business owner:

- Which functions stop working when the database is unavailable?
- How many users, orders, transactions, or internal processes are affected?
- Which data can be recreated from other sources, and which cannot?
- What are the consequences of losing 5 minutes, 1 hour, or 1 day of data?
- Which dependent systems must be operational before the application can reopen?
- Are there regulatory deadlines, audit requirements, reconciliation rules, or contractual commitments?

A Business Impact Analysis (BIA) helps classify services by priority level and acceptable downtime. Include cumulative impact over time in the assessment: a 10-minute outage might be acceptable, whereas an 8-hour outage could miss an entire daily processing cycle.

### 3.2. Choosing RPO Based on Data Loss Tolerance

Identify the types of data and how they can be recovered:

- Committed transactional data should be preserved as close to the incident time as possible.
- Data that can be recalculated from upstream sources can have a larger RPO, provided the rebuild process is tested.
- For data synchronized from other systems, clarify which source is the system of record and how to handle transactions sent without confirmed acknowledgment.

RPO is not simply equal to full backup frequency. With MySQL, a baseline backup combined with continuous binary log archiving can allow recovery close to the last moment logs were safely stored. Actual RPO depends on the latency of generating, transferring, confirming, and protecting those logs.

For example: a full backup runs nightly, and binary logs are shipped to storage every 2 minutes. If logs are only confirmed durably stored up to 13:56 when an incident strikes at 14:00, actual RPO is roughly 4 minutes—provided the baseline backup and the entire required log chain are readable. If log shipping is interrupted for 20 minutes, RPO has already exceeded a 5-minute target even though the nightly backup job still succeeded.

### 3.3. Choosing RTO Across the Entire Workflow

RTO must cover every step required for users to use the service, not just the runtime of the restore command. For example, recovery time may consist of:

| Stage | Estimated Time |
|---|---:|
| Detection, confirmation, and decision | 10 minutes |
| Server provisioning and storage configuration | 15 minutes |
| Fetching backup and restoring data | 25 minutes |
| Replaying binary logs | 15 minutes |
| Verifying data, privileges, and application | 20 minutes |
| Shifting traffic and monitoring | 10 minutes |
| **Total estimated** | **95 minutes** |

If the RTO is 90 minutes, the plan above fails, even if each individual stage seems fast. You must reduce time in one or more steps: pre-provision infrastructure, reduce the volume of logs to replay, improve backup read throughput, or streamline emergency approval workflows. You also need a buffer for secondary issues such as insufficient disk space, backup repository permission errors, or DNS issues.

## 4. Choosing a Backup Architecture Aligned with Objectives

No single backup type satisfies every RPO/RTO well. Combine methods and test recovering from the exact copies that will be used during an incident.

### 4.1. Logical Backup

A logical backup exports structure and data into SQL statements or a logical format. A common example is `mysqldump`:

```bash
mysqldump --host=db-primary.example.internal \
  --user=backup_user --password \
  --single-transaction --routines --events --triggers \
  --databases sales_app > sales_app.sql
```

`--single-transaction` creates a consistent snapshot for InnoDB tables within a single transaction; it does not guarantee a consistent snapshot for non-transactional tables. During the dump, DDL operations such as `ALTER TABLE`, `DROP TABLE`, or `RENAME TABLE` can affect consistency and must be controlled. Objects such as routines, events, and triggers must be explicitly included if they need to be restored.

The advantages of logical backup are portability across certain versions or server layouts and selective recovery. The drawback is that restore is often slow for large datasets because the server must execute many SQL statements, build indexes, and write rows one by one. Measure runtime on realistic data sizes.

### 4.2. Physical Backup

A physical backup copies data files, tablespaces, redo logs, and required InnoDB components using a tool's consistency mechanism. Tools may include MySQL Enterprise Backup or Percona XtraBackup; follow the documentation for the exact tool and MySQL Server versions.

Physical backups usually restore faster for large databases because they avoid reloading individual SQL statements. However, they carry version compatibility, storage layout, and specific prepare/restore requirements. You must never casually copy a running data directory with a regular copy command and treat it as a consistent backup.

### 4.3. Full, Incremental, and Snapshot

- **Full backup:** contains all data within the backup scope. Easy to understand and serves as the baseline for recovery, though it can be time- and space-intensive.
- **Incremental backup:** stores only changes since a previous backup checkpoint. Saves storage space and creation time, but restore must assemble the exact chain of full and incremental backups in order.
- **Storage snapshot:** captures volume state at the storage layer. Can be very fast, but is only safe if coordinated with MySQL's write state and backed by a consistency procedure.

Do not infer RTO from snapshot creation time. Measure the time to attach the snapshot, restore the volume, run InnoDB crash recovery, apply binary logs, verify, and return the service online.

### 4.4. Binary Logs and Point-in-Time Recovery

Binary logs record data and structure changes according to server configuration. When combined with a baseline backup, binary logs enable recovery to a specific point in time or position (point-in-time recovery — PITR), provided the necessary logs are stored completely and uncorrupted.

Check relevant configuration:

```sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW BINARY LOGS;
SHOW BINARY LOG STATUS;
```

`SHOW BINARY LOG STATUS` is available in newer MySQL versions; in some MySQL 8.0 releases, you may need `SHOW MASTER STATUS` depending on the exact version. Check the documentation for the version you operate. `log_bin` must be enabled to generate binary logs. `binlog_format=ROW` is typically preferred for recording consistent row changes across many replication and PITR scenarios.

Commit durability and log shipping must be designed together. For systems prioritizing transaction durability, `sync_binlog=1` alongside `innodb_flush_log_at_trx_commit=1` is commonly evaluated; these settings incur I/O overhead and require load testing. They do not replace shipping binary logs to an independent failure domain. If logs only reside on the same disk as the server, a disk failure can destroy both data and logs.

Example of replaying logs after restoring a baseline backup:

```bash
mysqlbinlog --start-datetime="2026-11-19 12:00:00" \
  --stop-datetime="2026-11-19 13:42:00" \
  /backup/binlog/mysql-bin.000123 \
  /backup/binlog/mysql-bin.000124 \
  | mysql --host=recovery-db.example.internal \
          --user=recovery_user --password
```

This is a syntax illustration. Before running, determine the exact log files, order, time zone, and stop point. Whenever possible, use a recorded log position or GTID to avoid timestamp ambiguity. Do not replay logs past the point where data was accidentally deleted or corrupted. Test the command on an isolated recovery host first.

## 5. Replication Does Not Replace Backup

Replication maintains a copy of data on another server and can reduce failover time when the primary suffers an infrastructure failure. However, erroneous operations replicate to replicas: an accidental table drop, wrong row updates, or malicious data can propagate. Replicas may also share accounts, networks, storage zones, or administrative permissions with the primary.

Therefore:

- Maintain backups independent of both primary and replicas.
- Store required binary logs outside the source server.
- Protect the backup repository with separate privileges, encryption, and protection against accidental modification/deletion.
- Test recovery when both primary and replicas are unavailable.
- If using a replica as the backup source, evaluate replication lag and ensure the backup tool creates a consistent snapshot.

Replicas can be part of a High Availability (HA) strategy; backups and PITR solve returning to an earlier data state. The two goals complement each other.

## 6. Calculating Actual RPO/RTO from Operational Data

An objective is only credible when measured regularly. Collect the following metrics:

| Metric | Meaning | Usage |
|---|---|---|
| Age of most recent valid backup | Time from snapshot timestamp to present | Estimate baseline point and verify backup schedule |
| Binary log archiving lag | Gap between newest log on source and log safely stored in independent repository | Estimate data potentially lost if source fails |
| Restore duration | Time to load backup onto recovery host | Evaluate read/write throughput and tool speed |
| Log replay duration | Time to apply post-backup changes | Evaluate log volume and execution speed |
| Verification duration | Time to run data and application checks | Ensure RTO includes quality verification |
| Restore test pass rate | Passed tests over total tests | Measure reliability of the process, not just backup jobs |

For example, a baseline backup finishes at 01:00, binary logs are shipped off-host continuously, and logs are confirmed up to 13:57. An incident occurs at 14:00. If both the backup and logs are readable, the closest recovery point is 13:57, so measured RPO is about 3 minutes. If restoring the backup takes 35 minutes, replaying logs takes 12 minutes, verification takes 15 minutes, and cutover takes 8 minutes, measured RTO is at least 70 minutes, excluding detection and decision time if the organization includes them in RTO.

For reliable numbers, measure on production-sized data, equivalent hardware and networking, while recording I/O load. A test on a 5 GB database does not reliably predict the recovery time of a 5 TB database.

## 7. Designing a MySQL Recovery Procedure

A recovery runbook must describe a clear sequence so on-call engineers can execute it under high pressure.

### 7.1. Pre-Incident Preparation

- Server inventory, MySQL versions, InnoDB settings, data paths, and expected storage sizes.
- Backup inventory, manifests, checksums, creation timestamps, backup types, and related incremental chains.
- Binary log locations, file ordering, GTID information, or log positions recorded at backup time.
- Recovery accounts, backup repository permissions, decryption keys, and emergency secret-retrieval procedures.
- Instructions for provisioning a host, installing a compatible version, and configuring networking and storage.
- List of applications, endpoints, DNS, proxies, certificates, and dependent services.
- Recovery decision maker, executor, data verifier, and traffic-reopening approver.

Credentials and decryption keys must be protected. The runbook should indicate where to retrieve secrets and who is authorized to access them, without writing passwords or private keys directly in the document.

### 7.2. Sample Recovery Sequence

1. **Contain:** stop further writes to the affected system; preserve logs and evidence needed for investigation. If compromise is suspected, isolate the host and verify backup repository integrity before use.
2. **Choose recovery point:** identify the last known good data time, when the incident began, and whether PITR before a specific transaction is needed.
3. **Build a clean environment:** provision a recovery host with a compatible MySQL version and configuration, sufficient CPU, RAM, IOPS, disk space, and permissions.
4. **Retrieve and verify backup:** verify manifests, checksums, signatures, or metadata provided by the backup system; decrypt in a controlled environment.
5. **Restore baseline backup:** follow the exact workflow of the logical or physical tool. For physical backups, run the prepare/recovery step per the tool documentation.
6. **Replay binary logs:** apply continuous logs from after the backup checkpoint to the chosen target point. Check ordering, gaps, and continuity of logs/GTIDs.
7. **Verify MySQL:** confirm the server starts, InnoDB completes recovery, required databases and tables are present, and accounts and privileges are correct.
8. **Verify application:** run representative queries, test transactions, perform controlled read/write checks, and verify queues and dependent integrations.
9. **Cut over service:** shift endpoints or traffic only after responsible owners confirm data and functionality meet criteria.
10. **Monitor and record:** watch connection errors, latency, locks, disk space, and incoming transactions; record timestamps to calculate actual RPO/RTO.

If recovering after an accidental user delete, do not overwrite production immediately. Recover onto an isolated host, replay logs up to before the delete operation, extract the needed data, and then plan a controlled re-import. This reduces the risk of overwriting valid transactions committed after the backup time.

## 8. Verifying Backups and Recovery

A backup job reporting `SUCCESS` only proves the tool reported completion by its own criteria. It does not prove the backup can be decrypted, restored, have logs replayed, and serve the application. Verification must occur at multiple layers.

### 8.1. Checks Immediately After Backup Creation

- Confirm job completion and record exit code, start/end timestamps, size, and data scope.
- Verify manifests, checksums, or the tool's integrity verification mechanism.
- Confirm files were transferred to an independent repository and are readable by the recovery account.
- Confirm binary logs after the backup checkpoint are stored completely, continuously, and are readable/decryptable.
- Check retention: backups and logs have not been deleted before their required retention window expires.

A checksum only proves file contents have not changed since the checksum was generated; it does not prove the contents represent the right backup or can be recovered. That is why restore tests remain necessary.

### 8.2. Periodic Restore Tests

Run recovery in an isolated environment to avoid impacting production. A test should include:

1. Downloading an actual backup from the archive repository, not using a copy still sitting on the backup host.
2. Verifying checksums and decrypting using the exact operational procedure.
3. Restoring onto a server with a supported version and configuration.
4. Replaying binary logs to a defined point in time.
5. Verifying tables, row counts, data relationships, and required database objects.
6. Starting the application or a representative query suite, checking privileges and transactions.
7. Timing each step, calculating RPO/RTO, and archiving evidence.

Frequency depends on system criticality and rate of change. A critical service may require weekly or monthly restore tests; a less critical system may run quarterly. Beyond scheduled runs, test after major changes such as MySQL upgrades, backup tool changes, encryption changes, storage migrations, or data structure changes.

### 8.3. Verifying Data Correctness

Seeing MySQL start successfully is not enough. Use checks aligned with the business domain:

- Count rows or aggregate data across time ranges on critical tables.
- Check logical foreign keys, order-to-payment relationships, balances, and offsetting entries.
- Compare checksums or aggregates against a source of truth if available.
- Inspect schema objects such as views, triggers, procedures, events, and application accounts.
- Run a test transaction that can roll back or execute on test data, confirming reads/writes work properly.

For financial systems, checking aggregate balances or transaction reconciliation can be more important than merely comparing row counts. Business owners must define data invariants and acceptance criteria.

## 9. Drills and Acceptance Criteria

A restore test verifies the technical viability of a backup. A recovery drill tests all the people, processes, access permissions, infrastructure, and decisions needed to bring the service back.

### 9.1. Scenarios to Drill

| Scenario | Verification Goal | Key Considerations |
|---|---|---|
| Accidental table or row drop | PITR prior to the erroneous operation and data extraction | Choose the exact stop point; preserve valid subsequent transactions |
| Server or volume failure | Recover onto new infrastructure from independent backup | Host provisioning speed, capacity, repository permissions, and binary logs |
| Missing or corrupted backup | Detect invalid copy and select an alternate copy | Retention, checksums, independent copies, and incremental chains |
| Storage region or account outage | Access backup in another failure domain | DNS, networking, decryption keys, permissions, and egress costs |
| Ransomware or unauthorized access | Recover from unmodified/undeleted copy | Immutability, separation of duties, verifying a clean environment |
| Failed upgrade or migration | Roll back prior to change and assess data loss | Version, schema, and application compatibility |

### 9.2. Acceptance Criteria

A drill passes when:

- Recovery succeeds using a backup fetched from the intended repository.
- Data is recovered to a point meeting the approved RPO.
- Service reaches operational status within the RTO limit.
- Data and application checks meet agreed business criteria.
- Access permissions, encryption, auditing, and monitoring work properly.
- Role holders know their duties, can locate the runbook, and can execute it without relying solely on a single individual.
- Evidence and step timings are recorded; deviations have an owner and remediation deadline.

If a test fails, document the exact root cause: missing permissions, inaccessible decryption keys, missing logs, insufficient disk space, restore time exceeding expectations, or failed business checks. Create remediation actions, set deadlines, and re-run the test to confirm the issue is resolved.

## 10. Protecting the Backup Repository and Security Incident Resilience

An RPO/RTO plan fails if an attacker or operational mistake can delete both primary data and backups. Design the backup repository as a separate security domain:

- Store at least one copy off-server and outside the primary failure domain; consider cross-region or separate administrative account copies.
- Use dedicated permissions for backup and restore tasks. The backup account should not have permission to delete the entire repository unless necessary.
- Enable encryption in transit and at rest. Manage decryption keys independently of the database server and test emergency access procedures.
- Use object lock, immutable storage, or deletion-resistant retention mechanisms where supported by the platform; also audit administrative permissions capable of altering retention.
- Monitor backup jobs, binary log gaps, latest backup age, capacity, and repository access errors.
- Keep a copy of the runbook and contact lists accessible even if primary identity systems or internal documentation platforms are down.
- Verify a backup is clean before restoring after a security incident; never return a compromised host to the production network without addressing the root cause.

The 3-2-1 rule (three copies, two storage media or domains, one off-site copy) is a useful starting point. For ransomware risk, add immutable copies and separate administrative privileges. Copy count alone does not guarantee recoverability if all copies share the same keys, accounts, or deletion paths.

## 11. Example: Building a Plan for an Order Service

Suppose a MySQL system storing orders has the following hypothetical characteristics:

- 1.2 TB database, growing by roughly 20 GB per day.
- Approved RPO is 5 minutes.
- Approved RTO is 90 minutes.
- Daily full physical backup takes 45 minutes.
- Binary logs are shipped to an independent repository every minute; alerting triggers if lag exceeds 2 minutes.
- Latest restore test took 38 minutes; log replay took 18 minutes; application verification and endpoint cutover took 22 minutes.

Measured total recovery time is 78 minutes, leaving 12 minutes of buffer against the RTO. This margin is quite tight. You must clarify whether detection, approval, and infrastructure provisioning times were included in the 78 minutes. If not, the plan has not yet proven it meets the 90-minute RTO.

To verify RPO, do not look only at the log-shipping schedule. The system must record the latest position or GTID on the source and the latest position safely stored in the independent repository. During a drill, select a committed test transaction, verify it is present after restore if it falls before the recovery point, and verify transactions after the stop point do not appear. Measure the gap between the simulated incident time and the last recoverable transaction.

An action plan may include:

1. Alert automatically when binary log archiving lag exceeds 2 minutes and when no valid backup exists in the expected window.
2. Pre-stage recovery host configurations and backup repository permissions to reduce infrastructure provisioning time.
3. Tune read/write throughput or use an appropriate physical restore method to cut data loading time.
4. Re-measure log replay time under representative load and set a threshold on maximum log volume.
5. Drill both primary loss and loss of access to primary accounts/repositories.
6. Maintain at least a 10–15 minute buffer after accounting for all milestones under the organization's RTO definition.

## 12. Recovery Plan Content Template

Each system should have a concise, approved plan linked to a detailed runbook. You can use the following template:

| Field | Details to Fill In |
|---|---|
| Service name / owner | System name, business team, and accountable owner |
| Data scope | Schemas, tables, routines, events, triggers, and related dependencies |
| MySQL version | Server version, engine, key settings, and backup tool |
| RPO / RTO | Values approved by the business owner, including measurement start/end milestones |
| Backup method | Logical/physical, full/incremental, snapshot, and execution schedule |
| Binary log / PITR | Storage location, how recovery points are identified, retention, and owner |
| Repository | Region, accounts, permissions, encryption, retention, and immutable copies |
| Restore procedure | Runbook, compatible versions, log replay steps, and cutover steps |
| Acceptance checks | Queries, business invariants, functional checks, and security criteria |
| Incident contacts | Incident commander, recovery executor, verifier, and fallback communication channels |
| Last test | Date, scenario, measured RPO/RTO, outcome, and open issues |

Review the plan whenever there are changes in data size, growth rate, MySQL version, topology, backup tooling, encryption, storage provider, or business requirements. A plan that once met a 1-hour RTO when the database was 100 GB may no longer hold when the database grows to 2 TB.

## 13. Self-Check Questions

1. A system restores in 10 minutes but only has a backup from 6 hours ago. What do the RTO and RPO of that setup reflect respectively?
2. Why is a nightly full backup schedule insufficient to prove a 5-minute RPO?
3. How must binary logs be protected to support PITR when the primary server or volume is lost?
4. Why can a replica not replace a backup when an operator accidentally runs `DROP TABLE`?
5. Which stages must be counted toward RTO besides data loading time?
6. Does a passing checksum prove a backup can be recovered? What additional verification steps are needed?
7. Propose a drill scenario and data/business criteria for acceptance.

## Conclusion

RPO defines acceptable data loss; RTO defines the time to bring the service back according to a clear measurement baseline. For MySQL, you must coordinate baseline backups, binary logs, PITR procedures, recovery infrastructure, and business verification to meet both goals. A plan is only considered trustworthy when the organization regularly pulls backups from the actual repository, restores in an isolated environment, measures RPO/RTO, drills roles, and resolves gaps until tests pass.

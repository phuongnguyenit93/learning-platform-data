# Backup, Data Guard, and High Availability on Exadata

## 1. Objectives and Context

Within the **Exadata and Cloud@Customer** chapter of the Oracle Cloud Infrastructure (OCI) track, this lesson explains how to combine backups, Oracle Data Guard, and Exadata availability mechanisms to protect databases. The focus is on an operable design: permissions, networking, monitoring, automation, recovery, and cost.

After completing this lesson, you will be able to:

- Distinguish single-site high availability from disaster recovery and historical data recovery.
- Translate business requirements into RPO, RTO, and concrete measurements.
- Choose backup locations and standby locations matching fault domains.
- Explain redo transport, redo apply, switchover, and failover.
- Build procedures for backup validation, role-transition drills, and bringing applications back into service.

The Oracle Database principles in this lesson apply across many Exadata environments. When deploying with OCI services, distinguish **Exadata Database Service on Cloud Infrastructure** from **Exadata Database Service on Cloud@Customer** located in the customer's data center. Configuration options via Console/API, backup destinations, and feature entitlements depend on the service, version, and contract. Do not treat a Cloud@Customer option as the default for every Exadata service.

## 2. Three Protection Layers Address Three Failure Groups

A system with multiple nodes and multiple data copies can still lose data or stop serving. You must identify what each mechanism actually protects against.

| Mechanism | Primary Role | Limit to Remember |
| --- | --- | --- |
| Exadata redundancy, ASM, and Oracle RAC | Absorbs certain hardware or instance faults; sustains cluster service when design and capacity allow | RAC instances access a single database; multiple instances do not create independent data history |
| Oracle Data Guard | Maintains a standby and performs role transition when the primary can no longer serve | Valid but business-erroneous changes can propagate to the standby |
| Backup and recovery | Restores files, databases, or data state to a protected point in time | Requires time to read backups, apply changes, and validate applications |
| Properly configured Flashback | Helps rewind to a prior state within retained recovery data | Does not replace backups isolated from production |

For example, an application mistakenly executes a DELETE against orders and commits. RAC keeps running; Data Guard may apply that exact change on the standby. Cluster survivability does not automatically recover deleted orders.

Conversely, if only one RAC instance fails, restoring the entire database from backup is usually disproportionate to the incident. Let cluster mechanisms and application services handle local faults before deciding to fail over to another site.

A practical architecture typically combines all three layers: **in-cluster availability, a standby in another fault domain, and backups with recovery history**.

## 3. Define RPO and RTO per Scenario

### 3.1. Two Distinct Objectives

**RPO — Recovery Point Objective** is the maximum acceptable data loss, typically expressed as a time interval. A 5-minute RPO means the business accepts losing at most roughly 5 minutes of data prior to an incident, within the agreed scope.

**RTO — Recovery Time Objective** is the maximum acceptable time to restore service after an outage. Agree on the start trigger and completion condition: is it when the database opens, or when users can successfully execute transactions again?

For a sales service, measure RTO until the order-creation flow works properly. A database promoted to primary while connection pools still point to the wrong endpoint has not met this objective.

Time-budget formula:

~~~text
Measured RTO =
    detection time
  + assessment and decision time
  + recovery/role-transition time
  + routing and reconnection time
  + business validation time
~~~

### 3.2. Example of a Recovery Data Point

Suppose an incident takes out the primary at 12:00:00. The standby has durably persisted all necessary redo up to 11:57:30; newer redo cannot be retrieved elsewhere.

Under this assumption, the window of data at risk is 2 minutes and 30 seconds. Simply having a standby does not prove RPO equals 0.

If redo up to 12:00:00 was durably saved on the standby but only applied up to 11:58:30, the unapplied portion does not mean data loss. Extra time may be needed to apply redo before opening the database after role transition. This scenario affects recovery time differently than redo never reaching the standby.

### 3.3. Do Not Use One Pair of Numbers for Every Incident Type

Example targets set by a hypothetical enterprise:

| Incident | Target RPO | Target RTO | Planned Response |
| --- | --- | --- | --- |
| Loss of one instance | Zero loss of committed transactions per configuration guarantees | A few minutes | RAC, role-based services, and application reconnect |
| Loss of entire primary site | At most 5 minutes | At most 30 minutes | Data Guard at a second site |
| Accidental deletion discovered after 2 hours | Recover state prior to the erroneous statement | At most 4 hours for the agreed data scope | Isolated restore, PITR, or Flashback if appropriate |
| Loss of both primary and standby | Per external backup protection point | Per restore volume and throughput | Backups in a third fault domain |

These are design targets, not Oracle SLAs. Actual timings must be proven through drills with representative data and load.

For business/logical errors, rolling the entire database back to before the error may discard valid changes made afterward. Therefore, evaluate both recovery scope and reconciliation methods rather than writing down one generic RPO.

## 4. Design Around Fault Domains

A fault domain is a set of components that can be affected together by a single cause: power, rack, Exadata infrastructure, data center, cloud region, network link, or administrative account.

Two different VM clusters on the same physical infrastructure can still share many risks. With Cloud@Customer, Oracle recommends placing production primary and standby databases on separate Exadata Cloud Infrastructures to increase fault isolation. [Data Guard Documentation for Cloud@Customer](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-using-data-guard.html).

An illustrative architecture:

~~~mermaid
flowchart LR
    APP["Application and connection pool"]
    SVC["Role-based PRIMARY database service"]

    subgraph A["Site A"]
        P["Primary on Exadata / RAC"]
        FA["Local recovery area"]
    end

    subgraph B["Site B: independent fault domain"]
        S["Physical standby on Exadata"]
    end

    subgraph C["Independent backup protection domain"]
        BK["Backup target and recovery history"]
        KEYS["Keys, configuration, and recovery permissions"]
    end

    OBS["Observer if using FSFO"]

    APP --> SVC
    SVC -->|"Active serving role"| P
    SVC -.->|"After role transition"| S
    P -->|"Redo transport"| S
    P --> FA
    P -->|"Backup"| BK
    S -.->|"Backup if plan is supported"| BK
    OBS -.-> P
    OBS -.-> S
    KEYS -.-> BK
~~~

The diagram shows a design plan and does not imply every combination of services or locations can be created via a single Console action. Before deployment, confirm supported topologies, database versions, service regions, and management methods.

When choosing locations, explicitly document:

- Which single failure could take out both primary and standby together?
- Does the backup remain accessible if the entire production infrastructure is unreachable?
- Can the recovery team obtain keys and credentials if the primary secrets management system is down?
- Is the network path used for restores independent of the network path that just failed?
- Does the standby have sufficient CPU, memory, I/O, and connectivity to absorb full production load?

Separate server rooms in the same building may mitigate certain localized faults; do not assume that layout protects against losing the entire building.

## 5. Design Backups for Recoverability

### 5.1. Restore, Recover, and Point-in-Time Recovery

Three concepts to distinguish:

- **Restore**: copying datafiles from backup back to the recovery location.
- **Recover**: applying necessary incremental backups and/or redo to bring files to a consistent target state.
- **Point-in-time recovery — PITR**: recovering to a selected timestamp or SCN, typically prior to an erroneous change.

Having backup files does not mean you can recover to any arbitrary point in time. Achievable targets depend on backup chains, retained redo, metadata, and decryption capability.

RMAN distinguishes incremental level 0, level 1 differential, and level 1 cumulative backups. Level 0 serves as the base for incrementals; differential captures blocks changed since the most recent level 0 or level 1 incremental, while cumulative captures changes since the most recent level 0. During recovery, RMAN can use appropriate incrementals and redo. [Oracle Database Backup and Recovery Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admqs/performing-backup-and-recovery.html).

A **standard full backup** does not automatically act as a level 0 base in an incremental strategy. When writing designs or reading logs, use the exact backup type rather than calling every complete data copy a "full."

### 5.2. Policies Must Cover Both Data and Redo

An illustrative policy for a self-managed environment:

| Component | Illustrative Plan | What Must Be Proven |
| --- | --- | --- |
| Incremental base | Periodic level 0 | A usable base backup exists for required recovery points |
| Data changes | Level 1 between level 0 runs | Needed backups in the chain are readable |
| Archived redo logs | Backed up frequently enough for RPO | Continuous redo exists up to the target recovery point |
| Recovery metadata | Control file, SPFILE, and database identifiers | Backups can be located and accessed if the source environment is lost |
| Encryption keys | Retain required keystore/keys per active key management mechanism | Data and backups can be decrypted at the recovery target |
| Validation | Validation and restore/recovery drills | Committed data point and recovery time are met |

This table is a design framework. Service-managed backup schedules may differ; do not manually alter schedules or override settings owned by service automation.

If data is backed up only nightly without required daytime redo backups, nightly backup frequency cannot be used as proof of a few-minute RPO.

Conversely, keeping vast amounts of archived logs while losing the base backup or encryption keys can still render recovery impossible.

### 5.3. Selecting Backup Destinations for Cloud@Customer

Cloud@Customer documentation describes destinations including OCI Object Storage, NFS, Zero Data Loss Recovery Appliance (ZDLRA), and local storage, depending on the backup method. Customer-managed NFS or ZDLRA targets must be configured so VM cluster nodes can access them. [Managing Backup and Recovery on Cloud@Customer](https://docs.oracle.com/en-us/iaas/exadata/doc/ecc-manage-db-backup-and-recovery.html).

Evaluate each choice by operational characteristics:

| Destination | Points to Evaluate |
| --- | --- |
| OCI Object Storage | Network path, DNS, access permissions, transfer duration, and agreed data residency scope |
| NFS | NFS server capacity, throughput, mount permissions, and independence from production infrastructure |
| ZDLRA | Appliance capacity, protection policies, connectivity, and restore workflows fitting the environment |
| Local storage/FRA where supported | Capacity, local recovery speed, and risk of loss alongside source infrastructure |

FRA — Fast Recovery Area — is a managed space for recovery-related files. An FRA sitting on the same storage system as production does not provide an independent copy against total loss of that system.

For OCI Object Storage, Cloud@Customer requires outbound connectivity to the Object Storage service under documented conditions. Placing the database in the customer's data center does not guarantee backups stay only on-site. [Managing Databases on Cloud@Customer](https://docs.oracle.com/en/engineered-systems/exadata-cloud-at-customer/ecccm/ecc-manage-databases.html).

### 5.4. Retention, Recoverability, and Deletion Policies

A recovery window describes the time span over which recovery capability is required; do not interpret it as "delete every file older than N days." A base backup older than the start of the window may still be required to recover a timestamp inside the window.

Three policies must stay aligned:

1. Backup retention policy to satisfy the recovery window.
2. Archived log retention or deletion policy serving both recovery and required standbys.
3. Lifecycle, retention, and deletion permissions at the backup storage destination.

Do not use OS age-based file deletion scripts in place of determining which files are still needed for recovery. In managed services, follow supported retention and cleanup mechanisms.

Also budget for multi-day backup failures, standby network outages, or heavy redo spikes. A system sized only for normal days easily enters a failure loop: backups fail, logs pile up, FRA fills, and service is impacted.

### 5.5. Keys and Configuration Are Part of Recoverability

The runbook must specify where to obtain and how to use:

- TDE keys/keystores needed for data and any still-referenced historical keys.
- Backup encryption keys or passwords if a separate mechanism is used.
- Connection settings, wallets, backup destination details, and required metadata.
- Database identifiers, matching Oracle home, and application service configuration.

Do not store all recovery secrets solely inside the protected database itself. Maintain a controlled, audited backup access path with clear ownership.

A backup retained longer than its key lifecycle may become unusable. When rotating keys, changing permissions, or switching backup destinations, re-validate the corresponding recovery path.

## 6. Verifying Backups with RMAN and Restore Drills

### 6.1. Distinguish Evidence Levels

| Verification Level | Evidence Provided | What Still Must Be Checked |
| --- | --- | --- |
| Backup job reports success | Job completed according to the tool | Data readability, complete recovery chain, key availability |
| RMAN validation | Detects certain file/block errors and verifies backup readability per command | Actual restore environment and business outcomes |
| Isolated restore and recover | Proves recovery to a selected point works | Full site-loss capacity and application redirection |
| Full service drill | Measures database, networking, applications, and reconciliation | Other untested failure scenarios |

RMAN provides validation commands for database files and backups; validation does not execute a full restore and application startup. [RMAN Validation Documentation](https://docs.oracle.com/en/database/oracle/oracle-database/19/bradv/validating-database-files-backups.html).

### 6.2. Inspection and Validation Examples

The example below is for an RMAN session connected to the right database with appropriate privileges:

~~~text
RMAN> SHOW ALL;
RMAN> LIST BACKUP SUMMARY;
RMAN> RESTORE DATABASE VALIDATE;
~~~

- `SHOW ALL` displays current RMAN configuration.
- `LIST BACKUP SUMMARY` displays backup metadata.
- `RESTORE DATABASE VALIDATE` checks the backups RMAN would choose for a database restore; it does not restore actual datafiles.

Do not infer arbitrary PITR capability from a single `RESTORE DATABASE VALIDATE` run. Archived logs, target point, keys, and the recovery environment must be validated separately.

Validation can read large volumes of data. Schedule it and monitor I/O rather than treating it as zero-impact.

### 6.3. What Must a Restore Drill Record?

Pick a target recovery timestamp inside the recovery window and execute in an isolated environment:

1. Record the target point with an explicit timezone timestamp or SCN.
2. Prepare compute, storage, software, access permissions, and keys.
3. Restore and recover using the service-supported method.
4. Open the test database following the appropriate procedure.
5. Verify required PDBs, application accounts, and business objects.
6. Inspect data at the target point and run test transactions on the restored copy.
7. Time each phase and record errors or manual steps.

The restored test copy must be isolated from production integrations: outbound email, payments, message queues, and scheduled jobs. This prevents tests from triggering unintended external transactions.

## 7. How Does Data Guard Work?

### 7.1. The Path of Redo

In a typical physical standby setup:

~~~text
Transaction on primary
    -> generates redo
    -> redo transport to standby
    -> redo persisted at standby
    -> redo apply updates standby datafiles
~~~

Data Guard maintains a separate database from the primary using redo. This differs from RAC, where multiple instances serve a single database.

**Standby redo logs — SRL** receive incoming redo; real-time apply can apply redo from SRLs without waiting for the entire log to be archived. With RAC, account for all potential redo threads and prepare both directions for after a role transition. Oracle documentation specifies SRL count and sizing rules relative to redo sources. [Redo Transport Services](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/oracle-data-guard-redo-transport-services.html).

When a service manages Data Guard creation, use the service-supported configuration workflow. Do not simultaneously modify configuration via Console, custom scripts, and database commands without knowing which component owns the state.

### 7.2. Transport Lag and Apply Lag

- **Transport lag**: how far redo persisted at the destination trails redo generated at the source.
- **Apply lag**: how far applied data state at the standby trails the source.

Low transport lag paired with rising apply lag suggests a bottleneck in apply, resources, or I/O. Rising transport lag points to networking, connectivity, target errors, or load exceeding transport capacity.

Check measurement freshness. `V$DATAGUARD_STATS` provides `TIME_COMPUTED` and `DATUM_TIME`; a `DATUM_TIME` that stops advancing across consecutive reads can indicate the standby is no longer receiving fresh metadata from the source. This view does not return the corresponding rows when queried on the primary. [V$DATAGUARD_STATS Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-DATAGUARD-STATS.html).

A dashboard showing zero lag from stale telemetry is not proof that DR is healthy.

### 7.3. SYNC, ASYNC, and Protection Modes

ASYNC avoids having commits wait for redo acknowledgment from the standby; in exchange, the primary can be lost before the newest redo reaches the destination. SYNC can increase commit latency due to waiting on remote acknowledgment.

| Protection Mode | Key Characteristics | Trade-off |
| --- | --- | --- |
| Maximum Performance | Typically uses ASYNC | Risk of losing redo not yet protected on the standby |
| Maximum Availability | Uses appropriate sync mechanism when standby meets conditions | Primary can continue if sync capability is lost, changing effective protection |
| Maximum Protection | Enforces strict synchronous protection requirements | Primary halts if no synchronous standby satisfies requirements |

With SYNC, distinguish **AFFIRM** — acknowledging after redo is written to storage — from **NOAFFIRM/FastSync** — not waiting for the same durable disk write. Do not treat the label "SYNC" alone as a zero-data-loss guarantee across every failure combination. [Data Guard Protection Modes](https://docs.oracle.com/en/database/oracle/oracle-database/19/sbydb/oracle-data-guard-protection-modes.html).

Choose a mode based on data-loss tolerance, application latency sensitivity, and link stability. Also verify which modes and options are supported by your specific service; not every Oracle Database capability is exposed through every cloud workflow.

### 7.4. Data Guard and Active Data Guard

A physical standby can satisfy DR goals without being queried by applications for reporting. Active Data Guard adds capabilities, including read-only queries while redo apply continues under supported configurations.

Usage rights depend on database edition, licensing model, and service. Before sending reporting queries to a standby, verify entitlements and test impacts on apply speed and DR failover capacity.

A standby busy serving reports must still be sized as the future production site. Under-sizing it to save cost until it cannot absorb load during role transition degrades RTO and service quality.

## 8. Network Capacity and Catch-Up Rate

Nominal link speed is not usable redo throughput. Measure after accounting for overhead, encryption, bandwidth contention, and endpoint processing limits.

Suppose during a relatively steady workload period:

- Primary generates 100 MB of redo per second.
- The link can deliver 140 MB/s of usable throughput.
- After an outage, a 120 GB backlog remains.
- Using decimal units in the calculation: 120 GB = 120,000 MB.

While new redo continues to be generated:

~~~text
Backlog drain rate = 140 - 100 = 40 MB/s

Minimum catch-up transfer time
    = 120,000 / 40
    = 3,000 seconds
    = 50 minutes
~~~

This is only a transfer-phase estimate. It omits archived log read limits, SRL writes, redo apply speed, workload spikes, and secondary disruptions.

If usable throughput is only 100 MB/s while redo generates at 100 MB/s, the backlog never shrinks under this model. If throughput drops below redo generation, the backlog keeps growing.

When designing networking in OCI or between Cloud@Customer and a DR site, check bidirectional routing, DNS, network rules, customer firewalls, and post-transition connectivity. A working primary-to-standby path does not guarantee the reverse path is ready.

With SYNC, also measure application commit latency at peak load. A large-file transfer test does not reflect the impact of redo acknowledgments on continuous small transactions.

## 9. Switchover, Failover, and Restoring Protection

### 9.1. Switchover

Switchover is a planned role reversal while databases can still coordinate: the primary becomes standby and the standby becomes primary.

Operational steps should include:

1. Confirm healthy configuration, sufficient redo, and target readiness for role transition.
2. Verify resources, services, and application network paths at the target site.
3. Coordinate transactions and background jobs per the application plan.
4. Execute switchover using the supported tool.
5. Verify the new roles and reversed redo direction.
6. Validate business transactions, backups, and alerts after transition.

Switchover is useful for maintenance and DR drills. It does not fully prove system behavior when the primary vanishes abruptly.

### 9.2. Failover

Failover promotes a standby to primary when the primary can no longer be used under normal procedures. Data loss depends on recoverable redo and protection state at the time of failure.

Before deciding to fail over, determine:

- Is the primary truly unable to serve, or was only a monitoring path lost?
- Does the standby have unapplied redo, and can more redo be retrieved from any source?
- Is the estimated data loss within authorized acceptance bounds?
- How will the old primary be prevented from accepting transactions when connectivity returns?
- How will applications, queues, and external integrations be coordinated?

Do not reopen the old primary for independent application writes after the standby has become primary. Establish isolation procedures and an authoritative source-of-truth declaration to prevent split-brain transaction streams.

### 9.3. Reinstate, Rebuild, and Returning to the Original Site

After failover, the old primary may need to be **reinstated** as a standby or rebuilt from scratch. Reinstate capability depends on prerequisites such as Flashback Database, required history, and configuration state; it does not always succeed.

Data Guard Broker documents role-transition and reinstate mechanisms, including Flashback prerequisites. [Switchover and Failover with Broker](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/using-data-guard-broker-to-manage-switchovers-failovers.html).

Getting applications running at site B does not finish the job. You must re-establish protection for the new primary: standby, backups, monitoring, permissions, and drill schedules.

When returning to site A, first rebuild protection and synchronization; then schedule a planned switchover. Do not treat "failback" as simply flipping DNS back to the old servers.

## 10. Data Guard Broker and Failover Automation

### 10.1. Inspecting via Broker

If the setup includes Data Guard Broker and service policy permits, you can inspect status with DGMGRL. In the example, `SALES_A` and `SALES_B` are hypothetical `DB_UNIQUE_NAME` values:

~~~text
DGMGRL> SHOW CONFIGURATION;
DGMGRL> SHOW DATABASE VERBOSE 'SALES_A';
DGMGRL> SHOW DATABASE VERBOSE 'SALES_B';
DGMGRL> VALIDATE DATABASE VERBOSE 'SALES_B';
~~~

Read errors, warnings, and readiness outputs rather than glancing only at the summary line. Verify exact commands, privileges, and options for your version. [DGMGRL Command Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/dgbkr/oracle-data-guard-broker-commands.html).

For services managing role transitions via Console/API, these commands illustrate the database layer only; they are not instructions to perform changes outside the service's management workflow.

### 10.2. Fast-Start Failover and the Observer

Fast-Start Failover — FSFO — uses Broker with an observer and configured conditions to automate failover in eligible situations.

The observer should have appropriate operational independence from both database sites. If the observer goes down alongside the primary, the architecture loses its decision-making component right when it is needed.

An FSFO design must explicitly specify:

- Failover target and entry conditions for promotion.
- Timeouts, lag limits, and health criteria in use.
- Handling of network partitions and fencing of the old primary.
- Monitoring of the observer, credentials, and connectivity.
- Application service redirection mechanism.
- Who intervenes if automation cannot complete.

Do not replace Broker with a script that promotes the standby when a ping fails. A single network probe cannot accurately determine database state or data protection posture.

FSFO also does not automatically resolve every application's connections, external system reconciliations, or decisions to recover erroneously modified business data.

## 11. Monitor to Detect Protection Gaps Before Disaster Strikes

### 11.1. Signals to Track

| Category | Signals | Operational Meaning |
| --- | --- | --- |
| Backup | Last success time, job failures, run duration, size | Detects gaps in backup protection |
| Recovery | Validation outcomes, latest restore drill, verified recovery point | Evaluates evidence-backed recoverability |
| Data Guard | Transport lag, apply lag, redo gaps, transport/apply errors | Detects a standby falling behind |
| Protection posture | Configured mode vs. actual protection level | Detects drift between intended and live protection |
| Capacity | FRA, ASM, backup target, archived log growth | Predicts bottlenecks or exhaustion |
| Infrastructure | Inter-site links, DNS, standby resources | Detects dependencies that could block DR |
| Application | Connection errors, timeouts, canary transactions | Measures serviceability beyond database status alone |

Every alert needs a recipient and a response procedure. In OCI, wire alarms and notifications to the appropriate operations group and retain history to audit protection gaps.

Illustrative threshold for a 5-minute RPO target: warn early when transport lag exceeds 60 seconds continuously or when telemetry becomes stale; escalate before lag approaches the 5-minute limit. These are hypothetical design values and must be tuned to workload and telemetry quality.

### 11.2. Read-Only Query Examples

On a database to check its role:

~~~sql
SELECT name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;
~~~

On a physical standby, check lag and source data timestamps:

~~~sql
SELECT name,
       value,
       unit,
       time_computed,
       datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag', 'apply finish time');
~~~

Appropriate read privileges on dynamic performance views are required. For multitenant databases, verify the target container and privilege scope before interpreting results.

These queries provide only part of the picture. Do not conclude a standby is ready for failover from a single column value; combine Broker output, logs, transport/apply status, and service checks.

## 12. Incident Handling Procedures by Root Cause

### 12.1. One Instance or Node Fails

First scope the failure and check the health of surviving instances. Verify resources, services, application sessions, and reconnection handling.

If the database continues serving properly within the cluster and meets requirements, do not automatically escalate to a DR site failover. Unnecessary site switches increase disruption and operational complexity.

While repairing the node, continue watching backups and the standby. A system temporarily lacking local redundancy requires closer monitoring.

### 12.2. Loss of the Entire Primary Site

A skeleton runbook:

1. Record onset timestamp, symptoms, and connectivity loss scope.
2. Verify primary status via remaining independent signals.
3. Identify the best standby, data currency, and recoverable redo.
4. Execute failover decision per authority or approved FSFO rules.
5. Ensure the old primary cannot continue accepting independent transactions.
6. Switch services/routing and refresh application connections.
7. Verify reads, writes, queues, and critical integrations.
8. Record actual measured RPO/RTO, unconfirmed data, and items requiring reconciliation.
9. Re-establish backups and a standby for the new primary.

When the primary is unreachable, a lag number alone may not tell you exactly which transactions are missing. Correlate database data with transaction logs and business identifiers for reconciliation.

### 12.3. Accidental Deletion or Data Corruption

First stop ongoing damage: halt the erroneous job or isolate the affected write path as needed.

Then:

1. Pinpoint the timestamp and scope of the erroneous change.
2. Check whether the standby already applied that change; never assume the standby still holds the clean data.
3. Choose Flashback, PITR, or isolated restore based on capability and blast radius.
4. If restoring in isolation, extract needed data and reconcile against production.
5. Plan how to reintroduce clean data without breaking other valid transactions.
6. Verify constraints, business totals, and integrations afterward.

A delayed-apply standby can be designed for certain user-error scenarios, though that delay also impacts data currency and role-transition time. Never replace backups with an intentionally delayed standby.

### 12.4. Backup Failures and Rapid FRA Growth

Do not immediately delete archived logs just to free space. Determine why they are still needed: unfinished backups, a standby that has not received/applied them per policy, or a broken recovery chain.

Remediation may include fixing the backup target, restoring connectivity, recovering background processes, expanding space in a controlled manner, and applying supported cleanup. Any deletion affecting recovery chains must be evaluated against remaining protected recovery points.

## 13. Java Applications Must Participate in Availability Design

For Java applications running on Compute, Kubernetes, or customer infrastructure, database role transition is only part of the recovery chain.

Design and test:

- Using role-appropriate database services instead of hardcoding a single node's hostname.
- Configuring sensible connect timeouts, read timeouts, and business deadlines.
- Allowing the connection pool to detect, evict, and recreate stale connections.
- Testing FAN, Application Continuity, or Transaction Guard where supported by the stack and licensing.
- Using business keys/idempotency keys when operations may be retried.
- Moving associated background jobs and integrations alongside the database service.

A critical edge case: the application sends a commit and the connection drops before receiving the response. The transaction may or may not have committed. Blindly retrying a payment debit or order creation can create duplicate transactions.

Therefore, DR tests must include in-flight transactions, not just SELECT queries after the database reopens. Measure the time until users can complete business actions again and verify final outcomes.

Example application evidence after role transition:

| Test | Pass Criterion |
| --- | --- |
| Create order with unique request ID | Exactly one order exists, no duplicates on reconnect |
| Read pre-incident order | Data matches the confirmed recovery point |
| Write new transaction | Writes to the new primary and reads back cleanly |
| Background jobs | Do not run unintentionally at both sites simultaneously |
| Post-transition backup | Policy continues protecting the active serving database |

## 14. Permissions, Automation, and Cost Control

### 14.1. Separation of Duties

OCI IAM permissions and Oracle Database privileges belong to separate layers. Permission to view Exadata resources does not grant permission to run RMAN or switch database roles.

A responsibility model can separate:

- Observers who check health and read logs.
- Operators managing backup schedules, retention, and targets.
- Operators executing recovery or role transitions.
- Key custodians.
- Administrators controlling backup deletion and retention-policy changes.

Permission to read backups can expose sensitive data. At the same time, a compromised production admin account should not be able to easily wipe both source data and all historical protection copies.

In Cloud@Customer, clearly document responsibilities across Oracle, customer infrastructure, networking, DBAs, and application teams. The provider managing infrastructure components does not replace the customer validating recovery goals and business outcomes.

### 14.2. Automation with Verification Gates

A periodic check job can collect:

~~~text
1. Identify the database and current role.
2. Fetch backup status and most recent protection point.
3. Fetch transport/apply lag along with measurement freshness.
4. Check storage capacity and growth rate.
5. Compare against configured targets.
6. Send alert with database, timestamp, and relevant evidence.
~~~

Operational scripts should enforce timeouts, logging, result checks, and idempotency. After a switchover, scripts must resolve the active role dynamically rather than assuming site A is always primary.

Infrastructure changes can be managed declaratively where supported by the service. Runtime states such as sync posture, unapplied redo, and business health still must be checked at execution time.

### 14.3. Costs Tied to Protection Targets

Include in estimates:

- Standby resources and capacity to handle full load during DR.
- Backup storage, archived logs, and recovery area capacity.
- Inter-site links, backup/restore throughput, and associated data transfer charges.
- Licensing entitlements for selected features.
- Drill environments, operational staffing, and evidence retention.

Do not cut costs by disabling monitoring or skipping restore drills. Instead, optimize by tiering databases by objective, setting evidence-based retention, and sizing standby resources using real load measurements.

Do not apply one fixed price figure or license checklist across every topology. Calculate based on the active service, region, subscription/BYOL model, and contract.

## 15. Lab: Designing and Proving a Protection Plan

### 15.1. Context and Conditions

A hypothetical sales system runs on Exadata Cloud@Customer at site A. The business requires:

- Loss of site A: RPO at most 5 minutes, RTO at most 30 minutes.
- Recover data prior to user errors discovered within 7 days.
- Backups covering full site loss must not depend on site A infrastructure.

Practice in an authorized test environment. You need a primary, a standby in a supported topology, accessible backups, and a test application or transaction client. If infrastructure is not yet provisioned, complete the design and calculations while clearly marking that RPO/RTO have not yet been proven.

### 15.2. Execution Sequence

1. **Map fault domains.** Record locations of primary, standby, backups, keys, observer if used, DNS, and applications.
2. **Build an objective matrix.** Separate node failure, site loss, and business data corruption.
3. **Inspect current configuration.** Check backups, retention, roles, transport mode, lag, and storage capacity.
4. **Validate backups.** Pick a target timestamp, perform an isolated restore/recover, and verify test data.
5. **Rehearse switchover.** Log timestamps, switch roles via the supported workflow, and run application transactions.
6. **Verify reverse direction.** Confirm redo, backups, and alerts work under the new roles.
7. **Rehearse failover separately if test scope allows.** Simulate the agreed failure, verify fencing of the old primary, and record recovered data currency.
8. **Restore protection posture.** Reinstate or rebuild the standby appropriately and validate before closing the drill.

Do not report switchover timings as failover RTO. The two scenarios involve different coordination conditions and decision times.

### 15.3. Result Recording Template

| Item | Details to Record |
| --- | --- |
| Scope | Database, version, topology, and simulated incident type |
| Data | Test transaction IDs, commit timestamps, and reconciliation result |
| Backup | Destination, recovery target point, restore duration, and recovery duration |
| Data Guard | Roles, mode, lag, and measurement freshness prior to test |
| RTO | Elapsed time from disruption to successful business transaction |
| RPO | Confirmed data point and measurement limitations |
| Post-test | Whether standby, backups, and monitoring now protect the new primary |
| Open issues | Manual steps, missing permissions, resource shortfalls, or routing errors |

### 15.4. Evaluation Example

Suppose a site-loss drill measures:

~~~text
Detection:                          2 minutes
Assessment and decision:            4 minutes
Role transition and DB service up:  7 minutes
Application reconnection:           3 minutes
Business verification:              4 minutes
Total:                             20 minutes
~~~

If the confirmed missing data window is 90 seconds, that drill satisfies the 30-minute RTO and 5-minute RPO targets for the tested scenario.

If the final committed transaction has not been verified at the target, you can only report service restoration time; you lack sufficient evidence to claim RPO. If backups have not been restore-tested, Data Guard results alone do not prove the 7-day user-error recovery requirement.

## 16. Core Principles to Apply

An operable Exadata protection design must answer four questions: **which failures are covered, what data could be lost, how long service stays down, and where the verification evidence resides**.

- RAC and storage redundancy absorb certain local faults; keep application availability intact across dropped connections.
- Data Guard provides recovery on a separate database; monitor redo, roles, and actual protection level.
- Backups provide recovery history; preserve the full chain of data, redo, metadata, and keys.
- Successful recovery must include database, applications, and business reconciliation.
- After every role transition, re-establish backups, standby, and monitoring for the active primary.

These principles connect OCI deployment to real-world operations: proper permissions, sufficient network capacity, owned alerts, and costs aligned with availability objectives.

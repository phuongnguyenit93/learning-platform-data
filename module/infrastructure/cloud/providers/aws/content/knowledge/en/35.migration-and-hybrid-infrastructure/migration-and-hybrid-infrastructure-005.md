# AWS DMS, Full Load, and Change Data Capture

## Lesson Objectives

Within the CLOUD_PROVIDERS_AWS ecosystem, database migration often must satisfy two requirements simultaneously: moving historical data to the target system while continuously capturing new changes until cutover. AWS Database Migration Service (AWS DMS) provides two primary mechanisms to address this: **Full load** reads and loads existing data; **Change Data Capture (CDC)** reads changes from the source database's transaction logs and applies them to the target.

Combining Full load with CDC lets an organization migrate databases without halting writes for the entire data copy duration. DMS loads each table while buffering ongoing source changes. Once a table finishes loading, DMS applies its cached changes and transitions to continuous replication. At cutover time, operators verify replication lag, stop or restrict writes at the source, wait for final changes to apply, and switch applications to the target database.

After completing this lesson, you will be able to:

- Distinguish Full load, CDC-only, and Full load + CDC.
- Explain how DMS captures transaction logs, caches changes, and applies them to the target.
- Prepare source endpoints, target endpoints, and a replication instance or DMS Serverless.
- Identify CDC prerequisites per engine such as MySQL, PostgreSQL, Oracle, and SQL Server.
- Configure table mappings, selection rules, filters, transformations, and LOB settings.
- Select appropriate `TargetTablePrepMode`, parallel load, and task settings.
- Enable data validation and analyze discrepancies between source and target.
- Monitor `FullLoadProgress`, `CDCLatencySource`, `CDCLatencyTarget`, and CloudWatch logs.
- Plan cutover, rollback, and post-migration verification.
- Troubleshoot common errors involving transaction logs, primary keys, networking, KMS, permissions, and replication capacity.

## 1. What Problem Does AWS DMS Solve?

AWS DMS is a service for migrating and replicating data between supported databases or data stores. Sources can be on-premises databases, self-managed databases on EC2, AWS managed databases, or certain external database platforms. Targets include Amazon RDS, Aurora, self-managed databases, S3, Redshift, DynamoDB, Kinesis, OpenSearch, and other supported targets.

A database migration typically includes these stages:

1. Prepare the target schema and environment.
2. Connect securely to source and target.
3. Load existing baseline data.
4. Capture and apply changes occurring during the load.
5. Validate data integrity and performance.
6. Switch applications to the target.
7. Monitor post-cutover and wrap up migration.

DMS focuses on data movement and replication. It does not automatically convert all schemas, stored procedures, triggers, views, functions, jobs, database permissions, or application logic. For heterogeneous migrations, use AWS DMS Schema Conversion or an appropriate schema conversion tool to analyze and convert database objects before running data tasks.

For example, an enterprise migrates on-premises MySQL to Amazon Aurora PostgreSQL. DMS can load row data and replicate supported changes, but SQL syntax, data types, stored procedures, triggers, and MySQL-specific features must be converted and tested separately.

## 2. Components of AWS DMS

A DMS architecture using a replication instance typically consists of:

- **Source endpoint:** connection details and read configuration for the source database.
- **Target endpoint:** connection details and write configuration for the target database.
- **Replication instance:** compute running the replication engine, managing cache, reading logs, and applying changes.
- **Replication subnet group:** group of subnets where the replication instance is deployed.
- **Replication task:** defines migration type, table mappings, task settings, and replication state.
- **CloudWatch:** stores logs and metrics for monitoring.

Diagram:

~~~mermaid
flowchart LR
    S[Source database] -->|Full load + transaction logs| D[AWS DMS replication]
    D -->|Full load rows and CDC events| T[Target database]
    D --> C[Amazon CloudWatch logs and metrics]
    D --> E[Endpoints, task settings and table mappings]
    V[IAM, KMS, Secrets Manager and VPC] --> D
~~~

The DMS replication instance runs inside a VPC. Security groups, route tables, subnets, NACLs, DNS, and firewalls for both source and target must allow connectivity from the replication instance. If the source is on-premises, use Site-to-Site VPN, Direct Connect, or another controlled network path.

AWS DMS offers two ways to provision replication compute:

| Option | Characteristics | When to Consider |
|---|---|---|
| Provisioned replication instance | Operator selects instance class, storage, and Multi-AZ | Predictable workloads needing explicit sizing and configuration control |
| AWS DMS Serverless | DMS automatically provisions and scales capacity within configured bounds | Variable workloads or desire to reduce replication compute management |

Serverless does not eliminate preparing endpoints, networking, permissions, task configurations, and performance testing. Verify that your migration path and required features are supported by the chosen replication type.

### 2.1. Replication Instance and Multi-AZ

The replication instance uses CPU, memory, and storage to execute tasks. Full load consumes resources reading the source and writing the target; CDC consumes resources reading transaction logs, buffering changes, and applying them to the target. An undersized instance can cause latency spikes, swapping, or spilling cached changes to disk.

A Multi-AZ deployment maintains a standby replication instance in another Availability Zone to support failover of the replication compute. It increases availability of the DMS replication instance itself, but it does not make the source or target database Multi-AZ, nor does it replace database backups. Evaluate cost and performance overhead when enabling Multi-AZ.

## 3. Distinguishing the Three Migration Types

DMS supports three common task modes:

| Migration Type | Behavior | Use Case |
|---|---|---|
| Migrate existing data (Full load) | Loads existing data to target and stops | Migrations with a downtime window or static datasets |
| Replicate data changes only (CDC) | Reads transaction logs and applies changes without baseline load | Target already has baseline data with a synchronized checkpoint |
| Migrate existing data and replicate ongoing changes (Full load + CDC) | Loads baseline, applies cached changes, then continues CDC | Migrations needing minimal downtime while keeping target near-sync |

Full load-only does not track ongoing changes after loading finishes. If the source continues accepting writes, the target quickly drifts out of sync. CDC-only assumes the target baseline already exists and aligns with the CDC start point; otherwise, data can be missing or duplicated.

Full load + CDC is the standard pattern for migrations requiring a short cutover. However, task completion of full load does not guarantee the application can switch immediately. You must wait for cached changes to apply, check CDC latency, run validation, and execute the cutover runbook.

## 4. How Full Load Works

Full load reads existing data from source and writes it to target. DMS identifies tables via table mappings and loads tables or table segments according to parallel load configuration.

One task can load multiple tables concurrently. The number of parallel tables and threads per table directly affect CPU, memory, network, I/O, and database load. Increasing parallelism can raise throughput, but can also overload the source, throttle the target, or exhaust replication instance memory.

Common settings:

| Setting | Meaning |
|---|---|
| `MaxFullLoadSubTasks` | Number of tables or table segments loaded concurrently |
| `ParallelLoadThreads` | Number of threads used to load data in parallel |
| `CommitRate` | Maximum number of records transferred in a single commit |
| `TransactionConsistencyTimeout` | Time to wait for open transactions before starting full load in CDC-enabled tasks |
| `CreatePkAfterFullLoad` | Creates primary keys after full load finishes if target prep and engine path support it |

`MaxFullLoadSubTasks` and `ParallelLoadThreads` multiply total concurrency. Raising both without measuring memory and CPU can exhaust the replication instance. Start conservatively, benchmark on representative data, and scale gradually.

### 4.1. TargetTablePrepMode

`TargetTablePrepMode` controls how DMS prepares target tables before full load:

| Mode | Behavior | Risks / Usage |
|---|---|---|
| `DO_NOTHING` | Does not delete or truncate target data or schema | Use when target is already prepared; ensure no stale data causes duplicates |
| `DROP_AND_CREATE` | Drops target table and recreates it | Can wipe out manually created indexes, constraints, or structures |
| `TRUNCATE_BEFORE_LOAD` | Deletes table rows while preserving metadata | Suitable for keeping table structure while reloading all rows |

Never select `DROP_AND_CREATE` on a production target without checking permissions, schemas, indexes, constraints, triggers, and existing data. When using `DO_NOTHING`, confirm the target is empty or holds the exact expected baseline state.

### 4.2. LOB Data

Large Objects such as `BLOB`, `CLOB`, or large binary fields require dedicated configuration. DMS supports options such as:

- **Limited LOB mode:** loads LOBs up to a configured max size; larger values may be truncated.
- **Full LOB mode:** loads complete LOBs in chunks; can be slower and consume more resources.
- **Inline LOB mode:** for supported cases and versions, loads small LOBs inline with row data and processes larger LOBs separately.

Measure actual LOB sizes, zero-loss requirements, and source/target limits. Choosing limited LOB mode without measuring maximum sizes can silently truncate data while the task keeps running. LOB replication typically requires a primary key or unique key to locate rows accurately.

## 5. CDC Reads Changes from Transaction Logs

CDC does not repeatedly run full-table `SELECT` queries to find new rows. Instead, DMS reads the source database's transaction log or change stream, parses committed changes, and applies them to the target.

Log sources vary by engine:

| Source Engine | Common CDC Mechanism | Key Prerequisites |
|---|---|---|
| MySQL / MariaDB / Aurora MySQL | Row-based binary log (binlog) | Enable automated backups / sufficient binlog retention; configure `binlog_format` and read grants |
| PostgreSQL / Aurora PostgreSQL | Logical replication slot and supported output plugin | Enable logical replication, replication and `SELECT` privileges; manage WAL/slots |
| Oracle | Redo logs via LogMiner or AWS DMS Binary Reader | `ARCHIVELOG`, supplemental logging, permissions to read redo/archived logs |
| SQL Server | MS-Replication or MS-CDC depending on configuration | Enable CDC/replication and appropriate log retention |
| Db2 and other engines | Engine-specific transaction log mechanism | Consult engine-specific documentation |

DMS requires logs to remain available until the task reads them. If the source purges or recycles logs before DMS reads them, the task may be unable to resume from its prior checkpoint. For RDS sources, AWS recommends enabling backups and retaining change logs sufficiently long; 24 hours is often a starting baseline, though workloads may need longer retention if tasks pause or backlogs grow.

### 5.1. MySQL and MariaDB

For MySQL-compatible sources, DMS reads row-based binary logs. Verify binlog format, retention, and endpoint user privileges. On Amazon RDS for MySQL/MariaDB, automated backups must be enabled for binary logging; on Aurora MySQL, configure `binlog_format` in the parameter group per engine requirements.

Example MySQL verification queries:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW BINARY LOGS;
~~~

DMS CDC generally requires row-based binlogs. Never purge binary logs manually while an active task depends on them. Monitor log retention, replication lag, and log storage consumption.

### 5.2. PostgreSQL

DMS uses a logical replication slot to read changes. For self-managed PostgreSQL, configure logical replication and required permissions; the DMS account needs read access to migrated tables and replication privileges per version guidelines. For RDS PostgreSQL / Aurora PostgreSQL, the endpoint user typically needs the `rds_replication` role and appropriate `SELECT` grants; do not grant superuser unnecessarily on managed services.

A logical replication slot retains WAL segments until its consumer reads them. If a DMS task stops for an extended period, the slot can accumulate large WAL volumes and fill storage. Monitor slot lag, retained WAL, and database free storage, and keep a runbook to handle failed tasks before disk exhaustion occurs.

### 5.3. Oracle

DMS can use Oracle LogMiner or AWS DMS Binary Reader to read redo logs. CDC requires `ARCHIVELOG`, supplemental logging, and appropriate privileges. Choosing between LogMiner and Binary Reader affects permissions, ASM configuration, and archive log access.

For self-managed Oracle, verify archive log retention is long enough and configure supplemental logging per AWS documentation. Never delete archive logs still needed by DMS. Run premigration assessments to validate `ARCHIVELOG`, retention, and access rights.

### 5.4. SQL Server

Depending on version and configuration, DMS uses MS-Replication or MS-CDC to capture changes from transaction logs. Verify whether your edition/version supports CDC for the migration path, database/table settings, permissions, and log retention. Some editions support full load without supporting ongoing CDC; never assume a source capable of full load automatically supports CDC.

## 6. Full Load + CDC: Cached Changes and Processing Flow

When a task uses Full load + CDC, DMS begins capturing changes from source logs while loading existing data. Ongoing changes are buffered in memory or disk cache. Once a table finishes full load, DMS applies its cached changes. After remaining cached changes are applied, the task enters ongoing CDC.

Diagram:

~~~mermaid
flowchart TD
    A[Start task] --> B[Initialize CDC capture point]
    B --> C[Read source transaction logs]
    C --> D[Cache changes in memory or disk]
    B --> E[Full load tables]
    E --> F[Table full load completed]
    D --> G[Apply cached changes to target]
    F --> G
    G --> H{Cached changes applied?}
    H -- No --> G
    H -- Yes --> I[Ongoing CDC]
    I --> J[Capture and apply new committed changes]
~~~

Distinguish the three stages:

1. **Full load:** loads baseline rows per table.
2. **Cached changes apply:** applies changes accumulated during full load.
3. **Ongoing CDC:** continues reading logs and applying new changes.

Cached changes are a critical part of Full load + CDC. If the source experiences heavy transaction volume during a long full load, the cache backlog grows large. When full load ends, DMS needs time to drain that backlog, and latency may spike before settling down.

With long-running transactions, DMS may have to wait for a commit before seeing changes per log semantics. Tasks can show elevated source latency while transactions remain uncommitted. Pick an appropriate full load window, reduce non-essential workload, and tune `TransactionConsistencyTimeout` per engine.

Full load + CDC does not mean every table is snapshotted at one global database instant. DMS loads tables on individual schedules while capturing logs in parallel; if applications enforce cross-table transactional invariants, evaluate transaction consistency, cutover timing, and validation instead of assuming all tables share an identical point-in-time snapshot.

## 7. Preparing Target Schemas and Databases

Before creating a task, prepare the target:

- Create databases/schemas and the DMS user.
- Convert data types and schemas if source and target engines differ.
- Check column lengths, precision, scale, time zones, collations, and character encodings.
- Identify primary keys or unique keys.
- Decide which indexes/constraints to create before vs. after full load.
- Handle LOBs and specialized data types.
- Check target capacity, connection limits, and storage.
- Define the target table preparation mode.

DMS can create basic target tables from metadata, but it does not replace a schema conversion tool and does not automatically migrate every database object. Indexes, foreign keys, triggers, stored procedures, views, sequences, users, roles, jobs, and grants require dedicated planning depending on source and target engines.

During full load, creating secondary indexes and foreign key constraints too early slows inserts down. Creating indexes after full load accelerates loading, but must finish before applications start using the target. For CDC, primary keys or unique keys help DMS locate rows for `UPDATE`/`DELETE`; tables without keys can suffer performance or apply limitations. Evaluate keyless tables separately.

## 8. Source Endpoints, Target Endpoints, and Networking

An endpoint defines database connectivity: engine, hostname, port, database name, credentials, and extra connection attributes.

Endpoint checklist:

| Component | Checks |
|---|---|
| Engine/type | Correct database engine and supported version |
| Server name/port | DNS resolves accurately and port is reachable |
| Credentials | DMS user has least-privilege permissions needed |
| SSL/TLS | Certificates and encryption settings properly configured |
| Extra connection attributes | Engine-specific CDC parameters declared properly |
| Secrets Manager | Secret and IAM role permissions configured to read secret |
| Network | Routes, security groups, NACLs, firewalls, and DNS allow connectivity |

The replication instance and endpoints require proper bidirectional network paths to establish sessions. Source/target security groups must allow inbound traffic from the replication instance's security group or IP address. Avoid exposing database ports to the public Internet when private routing is possible.

For on-premises databases, verify VPN/Direct Connect, routing between VPC and data center, firewalls, DNS, and MTU. For databases in another VPC, use VPC peering or Transit Gateway per network architecture.

If the replication instance sits in a private subnet and DMS connects to AWS services such as S3, DynamoDB, Kinesis, Redshift, OpenSearch, or Secrets Manager, corresponding VPC endpoints may be required. Starting with AWS DMS 3.4.7 in private networks, these VPC endpoints are mandatory for those services. Verify endpoint policies, routes, and DNS before running tasks.

## 9. IAM, KMS, and Protecting Connection Credentials

DMS requires distinct permissions for replication instances, endpoints, logging, and encrypted data.

Permission groups to review:

- IAM service roles allowing DMS to access required resources.
- Permissions to manage VPC resources and CloudWatch Logs.
- Permissions to read Secrets Manager secrets if endpoints reference secrets.
- KMS permissions to decrypt secrets or access encrypted data per configuration.
- Database privileges for endpoint users on source and target.
- Permissions for S3/Kinesis/Redshift or target services when migrating to those destinations.

Do not use database admin accounts unless strictly necessary. Create dedicated endpoint users with `SELECT`/replication privileges on source and required schema/write privileges on target. Revoke or tighten temporary privileges once migration concludes.

Never embed plaintext credentials in task settings files or logs. Use Secrets Manager, IAM roles, and TLS where supported by endpoints. If using a KMS customer managed key, ensure the key policy grants necessary permissions to the DMS principal or associated IAM roles.

## 10. Table Mappings: Selecting Tables and Transforming Data

Table mappings determine which schemas, tables, views, and filters a migration task processes. Three rule types are common:

- **Selection rules:** include or exclude schemas, tables, views, or collections.
- **Transformation rules:** rename schemas/tables/columns, add or drop columns, or change supported data types.
- **Table settings rules:** per-table overrides, such as LOB handling.

Example selecting all tables in the `sales` schema:

~~~json
{
  "rules": [
    {
      "rule-type": "selection",
      "rule-id": "1",
      "rule-name": "include-sales-tables",
      "object-locator": {
        "schema-name": "sales",
        "table-name": "%"
      },
      "rule-action": "include"
    }
  ]
}
~~~

You can add exclude rules for staging or audit tables that do not need migration. Selection rules support `%` wildcards, though schema/table name case sensitivity varies by source engine. Test table mappings on a small subset of tables first.

Transformations can rename schemas/tables, add prefixes, drop columns, or alter supported data types. Transformations that alter target schemas require careful validation; some changes require restarting the task to take effect properly. Do not use DMS transformations as an arbitrary rewrite layer for complex business logic.

Views have limitations: DMS only loads views during full load; it does not continuously replicate view changes like CDC tables. If views are needed, create and test them separately after base tables migrate.

## 11. Creating a Full Load + CDC Task

Before creating a task, ensure the source endpoint, target endpoint, and replication instance (or DMS Serverless replication configuration) are ready. Run endpoint connection tests to verify networking, credentials, and permissions.

Task settings and table mappings can be stored as JSON for review and version control. Condensed example task settings:

~~~json
{
  "TargetMetadata": {
    "SupportLobs": true,
    "LimitedSizeLobMode": true,
    "LobMaxSize": 64
  },
  "FullLoadSettings": {
    "TargetTablePrepMode": "DO_NOTHING",
    "CreatePkAfterFullLoad": true,
    "MaxFullLoadSubTasks": 8,
    "TransactionConsistencyTimeout": 600,
    "CommitRate": 10000
  },
  "Logging": {
    "EnableLogging": true
  },
  "ValidationSettings": {
    "EnableValidation": true,
    "ThreadCount": 5,
    "ValidationMode": "ROW_LEVEL"
  }
}
~~~

This is an illustrative example that must be tailored to source/target engines, DMS version, and schema. `LimitedSizeLobMode` truncates LOBs exceeding `LobMaxSize`; do not use it if full LOB preservation is required without first measuring max sizes. Use `CreatePkAfterFullLoad` only when appropriate for target and task.

Create a task using AWS CLI:

~~~bash
aws dms create-replication-task \
  --replication-task-identifier sales-full-load-cdc \
  --source-endpoint-arn arn:aws:dms:ap-southeast-1:111122223333:endpoint:SOURCE \
  --target-endpoint-arn arn:aws:dms:ap-southeast-1:111122223333:endpoint:TARGET \
  --replication-instance-arn arn:aws:dms:ap-southeast-1:111122223333:rep:REPLICATION \
  --migration-type full-load-and-cdc \
  --table-mappings file://table-mappings.json \
  --replication-task-settings file://task-settings.json \
  --region ap-southeast-1
~~~

ARNs and task identifiers above are placeholders. Once created, start the task:

~~~bash
aws dms start-replication-task \
  --replication-task-arn arn:aws:dms:ap-southeast-1:111122223333:task:TASK \
  --start-replication-task-type start-replication \
  --region ap-southeast-1
~~~

Common start types are `start-replication`, `resume-processing`, and `reload-target`. Choose the right behavior: `resume-processing` resumes from checkpoint; `reload-target` reloads tables according to task settings and may overwrite/truncate the target depending on `TargetTablePrepMode`. Never use `reload-target` as a harmless retry on a target containing production data.

## 12. Data Validation: Comparing Source and Target

DMS data validation compares source and target data to detect mismatches. When enabled on a task, DMS begins validating a table once its full load finishes; with CDC tasks, validation continues verifying replicated changes.

Validation adds read load to both source and target. For large tables, LOBs, or heavy workloads, measure performance impact before enabling across an entire production database.

Points to verify:

- Validation requires a suitable primary key or unique key to match rows.
- Certain data types, collations, LOBs, and engine combinations have limitations.
- If external applications write to source/target during validation, false mismatches may be reported.
- Validation only checks tables/columns in task scope and supported by DMS; it does not prove every database object or business rule migrated accurately.
- Validation-only tasks can compare data without migrating it, subject to specific configuration conditions.

Example enabling validation:

~~~json
{
  "ValidationSettings": {
    "EnableValidation": true,
    "ValidationMode": "ROW_LEVEL",
    "ThreadCount": 5,
    "PartitionSize": 10000,
    "FailureMaxCount": 10000,
    "TableFailureMaxCount": 1000,
    "SkipLobColumns": false
  }
}
~~~

DMS engine 3.5.4 and later may automatically select `GROUP_LEVEL` for certain supported migration paths to improve performance; other paths default to `ROW_LEVEL`. Check validation documentation for your exact engine version and migration path.

When mismatches occur, inspect validation failure tables, logs, and metrics; compare source/target row counts, primary keys, collations, data types, LOBs, concurrent writes, and CDC lag. Never declare a migration successful solely because task status shows `Load complete`.

## 13. Cutover: Switching Applications to the Target Database

Completing full load is not the automatic signal to switch traffic. With Full load + CDC, the target must catch up on source changes and pass verification.

Sample cutover runbook:

1. Confirm full load finished for all tables in scope.
2. Confirm the task is in ongoing CDC with zero unresolved table errors.
3. Verify `CDCLatencySource` and `CDCLatencyTarget` are stable within acceptable thresholds.
4. Run data validation and reconcile business-critical tables.
5. Announce the maintenance window and freeze or restrict schema changes.
6. Switch the application to read-only or stop writers on source.
7. Wait for open transactions to commit or resolve per plan.
8. Wait for DMS to capture and apply final changes; confirm latency drops near zero per criteria.
9. Run final reconciliation: row counts, monetary totals, order statuses, and business invariants.
10. Block writes to source to prevent split-brain.
11. Update application connection strings, secrets, or endpoints to point to target.
12. Start writers against target and run smoke tests.
13. Monitor errors, latency, connection pools, locks, and business transactions.
14. Keep source read-only for the policy-defined rollback window.

Never allow both source and target to accept writes during cutover without a dedicated multi-writer and conflict-resolution architecture. Unidirectional DMS CDC is not a bidirectional sync mechanism for merging concurrent writes.

## 14. Rollback and Limitations of Unidirectional CDC

If the application encounters issues on target after cutover, rollback is not simply switching connection strings back to source. Once the target accepts new writes, the source lacks those changes.

Before migration, choose a rollback strategy:

- Keep source read-only and roll back only before the target accepts new transactions.
- If the target has accepted writes, use reverse migration/CDC in the opposite direction or a controlled reconciliation process.
- For rollback with new target data, stop target writers, capture the ending checkpoint, sync necessary data back to source, and check for conflicts before reopening source.
- If safe reverse sync is infeasible, obtain a business decision to keep target authoritative or process delta transactions separately.

DMS does not automatically convert a unidirectional task into bidirectional replication. A CDC task has fixed source and target roles; reversing direction requires designing a new task and permissions in the reverse direction, plus validating engine support, schemas, and data. Practice rollback in rehearsals rather than waiting for a production incident.

## 15. Monitoring Tasks and CloudWatch Metrics

Monitor DMS across three layers: replication instance, task, and table statistics.

| Metric / State | Meaning | Usage |
|---|---|---|
| `FullLoadProgressPercent` | Overall full load completion | Track baseline load progress |
| `FullLoadThroughputRowsSource` | Row read rate from source | Detect slow source reads |
| `FullLoadThroughputRowsTarget` | Row write rate to target | Detect slow target applies |
| `FullLoadThroughputBandwidthSource/Target` | Full load bandwidth | Evaluate network and throughput |
| `CDCLatencySource` | Capture lag from source log to replication instance | Sustained high: inspect source, logs, or replication compute |
| `CDCLatencyTarget` | Apply lag applying changes to target | Much higher than source: inspect target, indexes, locks, or network |
| `CDCIncomingChanges` | Changes arriving from source | Compare arrival rate vs. apply rate |
| `CDCThroughputRowsSource/Target` | CDC row throughput in/out | Assess backlog trends |
| `CPUUtilization` | Replication instance CPU | Detect compute bottlenecks |
| `FreeableMemory` and `SwapUsage` | Memory/swap pressure | Identify undersized instance memory |
| `DiskQueueDepth` / `FreeStorageSpace` | I/O pressure and storage | Monitor cache and log space on replication instance |

Read `CDCLatencySource` and `CDCLatencyTarget` together. If both are high and similar, investigate capture/source first. If `CDCLatencySource` is low while `CDCLatencyTarget` is high, focus on the target, indexes/primary keys, locks, database capacity, networking, and apply settings.

Latency can temporarily rise during batch workloads or long transactions. A brief spike does not necessarily indicate service failure. What matters is a sustained trend or growing backlog that fails to drain after source/target load normalizes.

CloudWatch Logs captures task logs. Enable sufficient logging for diagnostics; enable debug logging only when needed since verbose logs increase storage and impact replication instance performance. DMS control tables can record task status, table statistics, and apply exceptions in the target database for Full load + CDC or CDC-only tasks.

## 16. Tuning Full Load and CDC Performance

Migration performance depends on source, target, replication compute, networking, schemas, indexes, LOBs, and transaction workloads. Tune one parameter group at a time and re-measure.

### Full Load

- Provision a replication instance with adequate CPU, memory, and storage.
- Adjust `MaxFullLoadSubTasks` and `ParallelLoadThreads` in a controlled manner.
- Increase target capacity and connection limits if needed.
- Consider creating secondary indexes after full load if target prep and cutover allow.
- Split workloads across schemas or table groups to reduce contention.
- Handle LOBs separately since large LOBs reduce throughput.
- Schedule migrations during low source-load windows.

### CDC

- Retain transaction logs long enough.
- Ensure source has sufficient resources for log reading.
- Ensure target has proper primary keys/indexes for updates and deletes.
- Monitor `CDCLatencySource` and `CDCLatencyTarget`.
- Scale up replication capacity if CPU/memory/disk is the bottleneck.
- Optimize target indexes, transaction apply, and batch apply per engine support.
- Avoid oversized transactions or unexpected DDL changes during migration.
- Check network throughput and packet loss between DMS and endpoints.

Never push parallelism solely to hit a throughput target if it degrades production workloads on the source database. The goal is stable migration, accurate data, and latency dropping to a safe cutover threshold.

## 17. Premigration Assessment and Pre-Flight Checks

AWS DMS premigration assessments analyze task configuration, source, target, and metadata to flag issues that could fail or impact migration. Run assessments before full load and CDC, review every finding, and resolve critical issues.

Pre-flight checklist:

- Source/target engine versions and migration path are supported.
- CDC prerequisites configured; transaction log retention sufficiently long.
- Tables have primary/unique keys or a handling plan exists for keyless tables.
- Source and target endpoint connection tests succeed.
- Replication instance or Serverless capacity fits the workload.
- VPC, routes, security groups, firewalls, and DNS tested.
- IAM roles, database permissions, Secrets Manager, and KMS operational.
- Target schemas and data types converted.
- LOB mode, table mappings, and `TargetTablePrepMode` reviewed.
- Pre-migration backups/snapshots and rollback runbook ready.
- CloudWatch logs/metrics and alarms configured.
- Cutover owner, maintenance window, and success criteria defined.

Premigration assessment does not replace a proof-of-concept or rehearsal. It catches missing configuration, but does not prove target capacity or application compatibility.

## 18. Troubleshooting Common Errors

| Symptom | Possible Cause | Troubleshooting Steps |
|---|---|---|
| Endpoint test fails | DNS, port, firewall, security group, or credentials | Check routes, SG/NACL, endpoint user, and TLS |
| Full load does not start | Missing metadata/table read grants or bad task mapping | Inspect task logs, table mappings, and database grants |
| Full load is slow | Source I/O, target indexes/constraints, LOBs, or undersized replication instance | Compare throughput metrics and CPU/memory |
| Table suspended | Data error, truncation, schema mismatch, or apply exception | Inspect table statistics and `awsdms_apply_exceptions` |
| CDC does not start after full load | Misconfigured log prerequisites, missing log grants, or pending cached changes | Check source log settings and task status |
| High `CDCLatencySource` | DMS cannot read logs fast enough, source resource limits, or long transactions | Check source workload, log access, and DMS CPU/memory |
| High `CDCLatencyTarget` with low source lag | Slow target, missing keys/indexes, locks, or network to target | Check target metrics, indexes, locks, and apply throughput |
| PostgreSQL WAL growing continuously | Logical replication slot unconsumed or task stopped | Check slot lag, task state, and retained WAL |
| MySQL missing required binlogs | Log retention shorter than task outage duration | Check binlog retention; recreate task from valid point if logs purged |
| Oracle CDC error | Misconfigured `ARCHIVELOG`, supplemental logging, or LogMiner/Binary Reader grants | Run assessment and verify source-specific prerequisites |
| SQL Server CDC error | MS-Replication/MS-CDC or log retention not configured | Check edition, database/table CDC, and SQL Agent |
| Validation mismatch | Concurrent writes, collation/data type/LOB, or CDC lag | Wait for lag to settle; inspect validation failures and schemas |
| Task out of disk | Cached changes, logs, or debug logging filling storage | Increase storage/capacity and reduce backlog; control log level |
| Resume task fails | Required transaction log position purged from source | Check available checkpoints; may require reload/recreate and target impact review |

When a task stops for an extended period, DMS may need to read a log backlog from an old checkpoint. If the source already purged those logs, the task cannot resume normally. Check log retention and checkpoints before pausing tasks for days.

Never delete a task or reload a target to troubleshoot an error without understanding the impact on target data. Some actions truncate/drop tables or erase checkpoints. Save the task ARN, table statistics, checkpoint, CloudWatch logs, and error messages before taking remediation steps.

## 19. Practical Lab: Migrating On-Premises MySQL to Amazon Aurora

An enterprise runs MySQL on-premises and wants to migrate to Aurora MySQL in `ap-southeast-1`. The application must continue accepting orders throughout most of the migration. The plan uses Full load + CDC, followed by cutover in a brief maintenance window.

### Design

| Component | Illustrative Configuration |
|---|---|
| Source | On-premises MySQL |
| Target | Amazon Aurora MySQL |
| DMS compute | Replication instance in private subnet |
| Network | Direct Connect or Site-to-Site VPN |
| Migration type | Full load and CDC |
| Source CDC | Row-based binlog with appropriate retention |
| Target prep | `DO_NOTHING` with pre-created schema |
| Table mapping | Include `sales` schema, exclude staging tables |
| Validation | Enabled for critical tables after load assessment |
| Monitoring | CloudWatch logs, `CDCLatencySource`/`Target`, table statistics |

### Implementation Steps

1. Verify compatibility between MySQL source and Aurora target.
2. Convert schemas and create databases/tables on Aurora.
3. Enable row-based binlogs and configure retention on source.
4. Create DMS replication instance, subnet group, security groups, and network path.
5. Create source/target endpoints and test connections.
6. Run premigration assessment and resolve findings.
7. Create table mappings for the `sales` schema.
8. Create a Full load + CDC task with validation and CloudWatch logging.
9. Monitor full load progress, table errors, and cached changes.
10. Wait for the task to enter ongoing CDC; measure `CDCLatencySource` and `CDCLatencyTarget`.
11. Compare data and business totals across source and target.
12. Open the maintenance window and stop source writers.
13. Wait for CDC latency to hit the cutover threshold and complete final validation.
14. Switch the application to the Aurora endpoint and run smoke tests.
15. Keep source read-only for the rollback window; close migration only after owner sign-off.

### Success Criteria

- All in-scope tables completed full load.
- Zero unaccepted table errors remain.
- CDC is active and latency stays within approved thresholds.
- Critical data passes validation and reconciliation.
- Application reads and writes against target succeed.
- Zero split-brain between source and target.
- Backups and a rollback/reverse sync plan exist.
- CloudWatch dashboards and runbooks are handed over.

## Conclusion

AWS DMS combines Full load and CDC to transfer existing data and continuously synchronize ongoing changes from transaction logs. Full load builds the baseline; cached changes catch newly loaded tables up to source state; ongoing CDC sustains replication until the organization is ready to cut over.

A safe migration requires preparing schemas, endpoints, networking, IAM, KMS, and log retention per database engine. Table mappings, LOB settings, target prep modes, and parallelism must be tested against realistic data. Data validation, CloudWatch metrics, and premigration assessments expose discrepancies and bottlenecks early. Cutover should proceed only after full load completes, CDC catches up, data is verified, and source writers are fenced.

DMS is one piece of a migration plan. Schema conversion, application testing, downtime management, rollback, and deciding when to enable target writes remain operational responsibilities owned by the engineering team and application owners.

## References

- [AWS Database Migration Service — User Guide](https://docs.aws.amazon.com/dms/latest/userguide/Welcome.html)
- [Working with AWS DMS tasks](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.html)
- [High-level view of AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Introduction.HighLevelView.html)
- [Creating tasks for ongoing replication using AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Task.CDC.html)
- [Full-load task settings](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TaskSettings.FullLoad.html)
- [AWS DMS data validation](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Validating.html)
- [Data validation task settings](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TaskSettings.DataValidation.html)
- [Monitoring AWS DMS tasks](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Monitoring.html)
- [Troubleshooting latency issues in AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Troubleshooting_Latency.html)
- [Using a MySQL database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.MySQL.html)
- [Using a PostgreSQL database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.PostgreSQL.html)
- [Using an Oracle database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.Oracle.html)
- [Using a Microsoft SQL Server database as a source for AWS DMS](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Source.SQLServer.html)
- [Setting up a network for a replication instance](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_ReplicationInstance.VPC.html)
- [AWS DMS components](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Introduction.Components.html)
- [Choosing an AWS DMS replication instance](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_ReplicationInstance.Types.html)
- [Using table mappings to specify task settings](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.html)
- [Selection rules and actions](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.SelectionTransformation.Selections.html)
- [Transformation rules and actions](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Tasks.CustomizingTasks.TableMapping.SelectionTransformation.Transformations.html)
- [AWS DMS Serverless](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Serverless.html)
- [AWS DMS Schema Conversion](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_SchemaConversion.html)
- [AWS DMS pricing](https://aws.amazon.com/dms/pricing/)

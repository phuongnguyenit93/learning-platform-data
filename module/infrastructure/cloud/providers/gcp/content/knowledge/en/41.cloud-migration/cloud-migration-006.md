# Database Migration Service and Database Synchronization

Migrating an application to Google Cloud is often easier than migrating a database under continuous writes. A Java API can be packaged and redeployed in minutes, whereas a database holding hundreds of gigabytes or multiple terabytes must move with data integrity, recoverability, and downtime aligned with business requirements. Simply copying a dump and swapping the JDBC URL can lose data written after the dump timestamp.

Google Cloud **Database Migration Service (DMS)** orchestrates database migrations to supported destinations such as Cloud SQL and AlloyDB for PostgreSQL. Depending on the source–destination pair, the service performs either a **one-time migration** or a **continuous migration**: loading initial data and then tracking and replicating subsequent changes via Change Data Capture (CDC). Once the target catches up to the source, operations execute **cutover** and switch applications to the new database.

This lesson belongs to the **Migrating to Google Cloud** chapter of **CLOUD_PROVIDERS_GCP**. The module guides selection and operation of services spanning projects, IAM, VPC, Compute Engine, GKE, Cloud Run, storage, and databases, integrating security, automation, reliability, and cost. This content focuses on selecting data migration flows, understanding synchronization mechanics, preparing PostgreSQL/MySQL sources, validating data, and safely cutting over Java/Spring applications.

## Learning Objectives

After this lesson, you will be able to:

- Explain DMS, migration jobs, connection profiles, initial load, CDC, and promote/cutover.
- Distinguish one-time, continuous, homogeneous, and heterogeneous database migrations.
- Check supported source–destination pairs, versions, features, and known limitations.
- Identify network connectivity, authentication, access permission, and replication configuration requirements.
- Prepare PostgreSQL or MySQL sources for continuous migration under matching scenarios.
- Create, test, monitor, and manage migration jobs in the Google Cloud Console.
- Evaluate replication lag and reconcile data before shifting traffic.
- Execute a cutover runbook, validate Java applications, and build a rollback plan.
- Recognize risks involving schemas, DDL, identities, sequences, sensitive data, and costs.

## 1. What Problem Does Database Migration Service Solve?

DMS is a managed service that moves data from a source database to a target database management system on Google Cloud. DMS streamlines connection setup, initial snapshot/load orchestration, change replication, and migration status tracking.

For example, a company runs PostgreSQL on a data center VM and wants to move to Cloud SQL for PostgreSQL. If the database serves multiple applications, restoring a backup from timestamp T0 misses transactions created after T0. Continuous migration reads the database's change stream to apply post-snapshot changes to the target, shrinking the write-freeze window needed at cutover.

DMS **does not replace** the following work:

- Surveying the source database and which applications read/write to it.
- Checking versions, extensions, stored procedures, schemas, and application compatibility.
- Provisioning or configuring network access for involved components.
- Validating RTO, RPO, downtime windows, and backup/restore strategies.
- Reconciling data, running integration tests, and evaluating query performance.
- Establishing a rollback procedure once applications start writing to the destination database.

In continuous migration, DMS maintains a **source → destination** data stream for migration purposes. The service **does not provide a bidirectional dual-write model** allowing apps to write simultaneously to both source and destination. After cutover, returning to the old source requires its own plan; never assume DMS will automatically replicate new transactions backward.

## 2. Four Easily Confused Concepts

### One-Time Migration

One-time migration takes a snapshot/dump and loads data into the destination once. There is no ongoing CDC stream. To avoid losing data during the copy, you usually must block new transactions at the source from the consistency point until applications switch over.

Pros: simple; fits small databases or systems with long maintenance windows.

Cons: downtime scales with data size, network throughput, and validation duration.

### Continuous Migration

Continuous migration starts with an **initial dump/load** and then applies changes recorded at the source. The goal is keeping the destination nearly synchronized while the source continues serving production.

Pros: the final write-freeze duration can be far shorter than total data transfer time.

Cons: requires logging/replication at the source, stable networking, adequate capacity, and lag monitoring. During migration, improper writes or schema changes at the destination can cause conflicts and break sync.

### Homogeneous Migration

Source and destination share the same database engine or DMS-supported compatible family—for example, MySQL → Cloud SQL for MySQL or PostgreSQL → Cloud SQL for PostgreSQL. Same-engine migration does not mean every version, extension, flag, and feature is compatible.

### Heterogeneous Migration

Source and destination use different database technologies—for example, Oracle → Cloud SQL for PostgreSQL or SQL Server → AlloyDB for PostgreSQL. Beyond moving data, you must convert schemas, data types, stored procedures, SQL dialects, and application logic. DMS provides conversion workspaces for supported scenarios; outputs still require DBA review and business testing.

| Aspect | One-Time | Continuous |
|---|---|---|
| Initial data | Snapshot/dump then load | Snapshot/dump then load |
| Post-snapshot changes | Not automatically replicated | CDC/replication via supported streams |
| Downtime | Typically spans transfer and validation | Concentrated in write freeze, catch-up, and cutover |
| Complexity | Lower | Higher: log retention, CDC, lag, promotion |
| Suitable workloads | Batches or data tolerating long write freezes | OLTP and systems minimizing disruption |

**Continuous does not mean zero downtime.** Switching the final writer to the destination database still requires a write-freeze window, catch-up wait, promotion, and application config updates.

## 3. Supported Sources and Destinations

DMS scenarios documented in current official guidance include:

| Type | Source | Example Destination |
|---|---|---|
| Homogeneous | Compatible MySQL | Cloud SQL for MySQL |
| Homogeneous | Compatible PostgreSQL | Cloud SQL for PostgreSQL |
| Homogeneous | Compatible PostgreSQL | AlloyDB for PostgreSQL |
| Homogeneous | Compatible SQL Server | Cloud SQL for SQL Server |
| Heterogeneous | Oracle | Cloud SQL for PostgreSQL or AlloyDB for PostgreSQL |
| Heterogeneous | SQL Server | Cloud SQL for PostgreSQL or AlloyDB for PostgreSQL |

Sources may live on-premises, on VMs in another cloud, or in DMS-supported managed database services. **Exact source types, versions, editions, topologies, networking, and features** depend on each migration scenario. Before designing, check the **Supported source and destination databases** and **Known limitations** pages for your scenario rather than treating the table above as a universal version guarantee.

Some options involve Pre-GA features, distinct connectivity methods, or specific constraints. For unlisted databases, evaluate alternatives such as native backup/restore, vendor tools, data replication pipelines, or fit-for-purpose migration services; do not try to force an unsupported engine into DMS.

### Tool Decision Examples

- Self-managed PostgreSQL → Cloud SQL for PostgreSQL: evaluate DMS continuous migration and replication constraints.
- MySQL on VM → Cloud SQL for MySQL: evaluate binlog-based CDC.
- Oracle → PostgreSQL: evaluate schema/code conversion before running migration.
- MongoDB or engines outside supported scenarios: survey alternative tooling and consistency requirements.
- Long-term bidirectional sync needs: design a dedicated replication architecture; **never use DMS as an active-active replication service**.

## 4. DMS Architecture and Sync Flow

A continuous migration typically comprises:

1. **Source database:** database currently serving transactions.
2. **Connection profile:** source connectivity details, endpoint, engine type, authentication, and security.
3. **Connectivity method:** network path enabling migration components and destination to reach the source.
4. **Migration job:** resource orchestrating snapshot, load, and CDC.
5. **Destination database:** Cloud SQL or AlloyDB provisioned per scenario.
6. **Metrics/logs:** job status, logs, errors, and replication lag used to gate cutover.

~~~mermaid
flowchart LR
  A[Java/Spring API writing to source] --> B[(Source DB)]
  B --> C[Initial dump / snapshot]
  B --> D[Change logs: binlog / WAL / CDC]
  C --> E[Database Migration Service job]
  D --> E
  E --> F[(Cloud SQL / AlloyDB destination)]
  E --> G[Migration job metrics and logs]
  F --> H[Validation: schema, rows, queries]
  G --> I{Lag near 0?}
  H --> I
  I -->|Not yet| J[Continue syncing]
  I -->|Ready| K[Stop source writes and promote]
  K --> L[Java/Spring API switches to destination]
~~~

This diagram illustrates logical flow. Depending on the engine and scenario, DMS coordinates connectivity between destination and source along the configured network path; not every byte necessarily passes through a single DMS proxy.

### Stage Statuses

| Stage | Description | What to Monitor |
|---|---|---|
| Job validation | Checks config, endpoints, privileges, and network | Test job passes |
| Initial load | Copies historical data via snapshot/dump | Throughput, disk space, import errors |
| CDC / replication | Applies ongoing changes | Replication delay/lag, log retention, backlog |
| Cutover preparation | Validates data and prepares to close source writes | Row counts, data checks, app readiness |
| Promotion | Stops replication stream and makes destination an independent primary | Promotion succeeds, source writes stopped |
| Post-cutover | App switches endpoints; monitoring and backups run | Error rate, latency, data integrity |

Exact state names in the Console/API vary by engine. Operate according to live job states and scenario-specific documentation.

## 5. Preflight: Surveying Databases and Related Workloads

Before creating a migration job, DBAs and application owners must align on:

| Item | Questions to Answer |
|---|---|
| Source | Engine, version, edition, hosting, topology, HA, replicas |
| Destination | Engine/version, region, CPU/RAM, storage, HA, networking |
| Data | Size, DB/schema count, tables, large objects, growth rate |
| Workload | TPS/QPS, connections, transaction duration, peak windows |
| Schema | Extensions, triggers, functions, stored procedures, collation, sequences |
| Security | TLS, encryption, account privileges, secret rotation, auditing |
| Dependencies | Read/write apps, ETL/BI, reporting, batch jobs, CDC consumers |
| Recovery | Backups, PITR, RTO/RPO, restore snapshots, DR |
| Cutover | Write-freeze duration, DNS/JDBC URLs, credentials, rollback |
| Validation | Row counts, checksums, functionality, query latency |
| Ownership | DBA, app, network, security, business owner, on-call |

**Never pick a target database solely because its name matches the source engine.** For instance, PostgreSQL extensions or Oracle stored procedures may lack exact equivalents on the target. When moving SQL Server/Oracle to PostgreSQL, assess SQL inside Java code, ORM mappings, and batch scripts as well.

### Building an Evidence Table

~~~csv
item,source,destination,check,owner,status
orders-db,postgresql-self-managed,cloud-sql-postgresql,version-and-extensions,dba,pending
orders-db,postgresql-self-managed,cloud-sql-postgresql,wal-and-replication,dba,pending
orders-db,postgresql-self-managed,cloud-sql-postgresql,network-and-tls,network,pending
orders-api,spring-boot,cloud-run,jdbc-and-pooling,app-team,pending
orders-db,postgresql-self-managed,cloud-sql-postgresql,cutover-and-rollback,sre,pending
~~~

This is an example checklist; sensitive details like internal hostnames, passwords, and customer data must be stored separately in protected systems.

## 6. Preparing a MySQL Source for Continuous Migration

DMS reads changes from the **binary log (binlog)** in many MySQL scenarios. To keep the source serving transactions during migration, configure binlog settings and retention properly.

### Read-Only Configuration Checks

On an authorized MySQL source:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
SHOW VARIABLES LIKE 'server_id';
SHOW VARIABLES LIKE 'gtid_mode';
~~~

Key checks:

- Binary logging must be enabled per scenario requirements.
- `binlog_format` must be `ROW` when DMS requires row-based binlogs.
- Retention must be long enough for DMS to catch up if the network slows or a job pauses.
- `server_id` must be validly configured.
- `GTID_MODE` must match a scenario-supported state; some targets with read replicas or manual dumps require GTID ON.
- The migration account must hold exact snapshot/replication privileges listed officially for that source.

**Do not** copy configuration commands or GRANT statements from another system without checking MySQL version, managed vs. on-premises hosting, and specific requirements. On Cloud SQL for MySQL sources, binlogs tie into PITR and database flags; on Amazon RDS/Aurora, retention and privileges are controlled differently from self-managed MySQL.

### Binlog Retention Risks

If initial load runs long or CDC lags for hours, the source may rotate/purge binlogs before DMS reads them. That can fail the job or force restarting migration from scratch. Therefore:

1. Estimate write rate and data copy duration.
2. Set retention generously for peaks, outages, and recovery.
3. Monitor log disk usage on the source.
4. Throttle heavy writes during peak windows if appropriate.
5. Rehearse recovery if DMS loses its CDC position.

### Migration Privileges

Create a **dedicated migration identity**, restrict privileges per DMS docs, and revoke/delete it afterward. Never reuse the application's root account or leak passwords into shell history; store secrets in an approved vault. Exact privileges depend on snapshot method, binlog mode, and database provider.

## 7. Preparing a PostgreSQL Source for Continuous Migration

For many PostgreSQL homogeneous flows, DMS uses the **Write-Ahead Log (WAL)** and logical replication to stream changes. Some scenarios rely on the `pglogical` extension, while newer methods may use native PostgreSQL logical replication. Check the exact scenario and version documentation rather than applying one recipe everywhere.

### Source Configuration Checks

Example read-only SQL checks:

~~~sql
SHOW server_version;
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
SHOW max_worker_processes;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Items to evaluate:

- Logical replication is enabled and server parameters are properly sized.
- Replication slots and WAL senders suffice for the migration job, table syncs, and other consumers.
- The migration account holds replication and schema/table read privileges per docs.
- Source extensions and data types are supported at the destination.
- Replication slots/WAL retention will not grow unbounded if the destination slows down.
- Disk space accommodates WAL spikes during large initial loads or network interruptions.

On Amazon RDS for PostgreSQL, inspect parameters such as `rds.logical_replication` alongside slot, worker, and timeout rules in DMS docs. On self-managed PostgreSQL, changing settings may require a reload or restart; file a change request given production impact.

### Replication Info and Lag

Reference SQL to inspect replication slots on a PostgreSQL source:

~~~sql
SELECT slot_name, plugin, slot_type, active,
       restart_lsn, confirmed_flush_lsn
FROM pg_replication_slots;
~~~

Exact columns and semantics vary by version and slot type. Never drop a replication slot used by DMS or another consumer simply because it retains WAL; identify the owner and job status first.

### Post-Migration Objects to Verify

For PostgreSQL, check:

- Extensions, custom types, functions, and procedures.
- Owners, roles, GRANTs, row-level security, and audit policies.
- Sequences, identity columns, and default values.
- Large objects and tables with primary keys/unique constraints.
- Materialized views, foreign tables, and external extensions.
- Scheduled jobs, background workers, and database client tools.

Never assume every DDL change during CDC replicates automatically. Certain schema changes may require manual steps or face scenario limitations. Enforce a **schema-change freeze** or formal review process before running migration.

## 8. Heterogeneous Migration: Converting Schemas and Application Logic

Moving Oracle or SQL Server to PostgreSQL can demand far more engineering than same-engine migration.

### Common Incompatibilities

| Area | Examples to Check |
|---|---|
| Data types | NUMBER/DECIMAL, timestamp with time zone, Unicode, LOBs |
| Schemas | Namespaces, quoted identifiers, collations, index types |
| Constraints | Primary/foreign keys, uniqueness, cascade behaviors |
| SQL | Dialects, pagination, join hints, proprietary functions |
| In-DB logic | Stored procedures, packages, triggers, jobs |
| Transactions | Isolation levels, locking, savepoints, retry semantics |
| Identity | Sequences, auto-increment, default values |
| Security | Users, roles, GRANTs, auditing, encryption |
| Application | JDBC drivers, Hibernate dialects, native queries, transaction mapping |

DMS includes a **conversion workspace** for supported heterogeneous migrations with schema/code conversion assistance. Tooling detects and converts many objects, yet it does not replace DBAs and functional application testing.

### Conversion Workflow

1. Extract schema DDL and object inventories from the source.
2. Run a conversion feasibility assessment and group objects.
3. Use a conversion workspace per scenario documentation.
4. Validate type mappings, indexes, constraints, and data semantics.
5. Review stored procedures, triggers, jobs, and application SQL.
6. Run integration tests against the target database.
7. Benchmark query plans and performance; runnable SQL does not guarantee equal speed.
8. Finalize a list of manual fixes with assigned owners.

Pay special attention to currency, timestamps/time zones, Unicode, and NULL semantics. A subtle data-type discrepancy might not fail the migration job while silently corrupting financial or business reports.

## 9. Networking, Authentication, and Access Permissions

DMS requires a supported network path between source and destination. Depending on engine and source location, this may involve allowlisted public connectivity, private connectivity, VPN/Interconnect, peering, or tunneling methods.

### Connectivity Checklist

- Can the source hostname/IP resolve from the connecting component?
- Are database ports allowed through firewalls from the right source IPs/networks?
- Are TLS certificates valid with matching hostnames?
- Do network routes follow the expected path without NAT or overlapping CIDR issues?
- Are bandwidth and RTT sufficient for initial load and CDC?
- Are proxies, bastions, or policies interrupting long-lived connections?
- Is the service inside a VPC Service Controls perimeter?
- Are matching DB and Cloud IAM accounts and permissions in place?

Never open a database to the Internet with `0.0.0.0/0` just to make a migration test pass. Prefer private or tightly scoped paths with TLS authentication. Protect all connection metadata as secrets.

### Distinguishing Three Permission Layers

| Layer | Examples | Consequence If Missing |
|---|---|---|
| Google Cloud IAM | Create/view migration jobs, connection profiles, destinations | Cannot create or manage jobs |
| Network | Firewalls, routes, DNS, TLS, private connectivity | Cannot reach the source |
| Database privileges | Replication, snapshots, reading schemas/data | Job connects but cannot dump or run CDC |

Never grant overly broad roles just to "make connection errors go away." Start from the DMS error message and inspect each layer separately.

## 10. Creating and Testing a Migration Job in the Console

Illustrative general workflow for PostgreSQL → Cloud SQL for PostgreSQL. Exact UI labels and fields vary by scenario and release.

### Step 1: Prepare the Target Project

1. Select an approved project and region.
2. Enable the Database Migration API and required destination APIs.
3. Verify billing, quotas, VPC, DNS, and IAM permissions.
4. Confirm source, destination, engine, database version, and downtime requirements.
5. Prepare a new or existing Cloud SQL destination per DMS-supported methods.

Example API enablement:

~~~bash
gcloud services enable datamigration.googleapis.com sqladmin.googleapis.com --project=PROJECT_ID
~~~

In some setups, you must also enable Service Networking API and configure private connectivity. Do not treat this single command as a substitute for scenario-specific setup steps.

### Step 2: Create a Connection Profile

In **Database Migration > Connection profiles**, create a source profile specifying:

- Source engine and version.
- Host/IP/port and database identifier.
- Migration user and credential protection mechanism.
- TLS/SSL parameters as required.
- Supported network path.

Test the connection profile per guidance. Secrets must never appear in screenshots, tickets, or training docs.

### Step 3: Create the Migration Job

1. Open **Database Migration > Migration jobs**.
2. Click **Create migration job**.
3. Set the job ID, region, source engine, and destination engine.
4. Select migration type (continuous or one-time if supported by the scenario).
5. Choose the source connection profile.
6. Select or create a supported destination.
7. Configure the connectivity method and database selection.
8. Review summary, region, accounts, schemas, and data-impacting options.
9. Run **Test job** to catch network/permission/config errors.
10. Only after tests pass and approvals are granted, choose **Create and start job** (or create first and start later).

DMS may create or modify destination database settings during setup. If the destination is managed by Terraform, migration adjustments can introduce **configuration drift**; do not blindly run `terraform apply` while a migration is active without consulting scenario guidance.

### Step 4: Monitor Status

In **Migration jobs**, inspect:

- Current job state.
- Initial load progress.
- CDC phase and replication delay.
- Error/diagnostic messages.
- Source/destination and network health.
- Disk storage, transaction logs, CPU, and connection counts.

Do not start cutover simply because the job says "running." Wait for data validation and confirmation that the target has caught up.

## 11. CDC and Limits You Must Understand

CDC tracks changes occurring after the initial snapshot. However, CDC is completely different from two independent databases accepting concurrent writes.

### Single Source Writer Until Cutover

Before cutover, treat the **source as the primary writer**. Avoid using the destination like an independent production DB by running INSERT/UPDATE/DELETE or DDL against migrating datasets. Doing so can cause replication conflicts or data corruption.

Even if a scenario's destination is not technically forced read-only, **operational procedures must forbid writes to replicated datasets** except for explicitly documented actions.

### Schema Changes During CDC

Do not assume every DDL change propagates automatically. Some scenarios restrict table alterations, extensions, triggers, or partition changes. Enforce change governance: review, test compatibility, and freeze schema changes ahead of cutover.

### Transaction Consistency

Understand the consistency point of initial load and the CDC stream. Matching row counts at T1 do not guarantee matching data at T2 if the source is still taking writes. When reconciling, align on a **common verification timestamp** or use an appropriate consistency mechanism.

### Replication Lag

**Replication lag** is the gap between source commits and destination application. It can grow when:

- Source write throughput exceeds destination apply speed.
- Network latency, packet loss, or intermittent database drops occur.
- Destination lacks CPU, memory, or I/O.
- Large transactions, batches, or schema locks run.
- CDC hits permission errors or missing logs.

Lag dropping near 0 is necessary but **not sufficient** to declare production readiness. You must still validate data, schemas, security, performance, and applications.

## 12. Observing Migrations and Setting Alert Thresholds

A production migration needs a dedicated dashboard and runbook. Monitor at minimum:

| Metric | Meaning | Action on Anomaly |
|---|---|---|
| Job state | Running, failed, stopped, or CDC | Inspect diagnostics and notify owner |
| Initial load progress | Historical data copy progress | Identify throughput bottlenecks |
| Replication delay | How far behind the target lags | Check source logs, network, destination |
| Source log growth | Increasing binlog/WAL retention | Protect disk space; check stalled sync |
| Destination CPU/I/O | Apply and query load | Adjust capacity per guidance |
| Source DB connections | Impact of replication accounts | Check connection limits |
| Storage used | Destination disk and logs | Check quotas and disk growth |
| Error logs | Auth, schema, timeout failures | Triage and remediate |

Exact metric names differ by engine and product. Consult the **Migration job metrics** documentation for your actual scenario rather than copying invalid filters across environments.

### Response Workflow When Lag Grows

1. Verify the job is still in CDC.
2. Measure current lag, growth rate, and duration.
3. Check the source for batch jobs or large transactions.
4. Check log retention and available disk space.
5. Check network health, SSL, retries, and destination status.
6. Determine whether capacity adjustments, batch rescheduling, or write throttling are needed.
7. Schedule cutover only once lag stabilizes within approved thresholds.

Never disable retention or drop replication slots/binlogs while a job relies on them; doing so can destroy the ability to resume syncing.

## 13. Data Reconciliation Before Cutover

A job reaching CDC does not mean business criteria are satisfied. DBAs and application owners must reconcile data.

### Layer 1: Schema

- Databases, schemas, tables, columns, and data types match expectations.
- Primary keys, unique indexes, foreign keys, and constraints are intact.
- Views, functions, procedures, triggers, and extensions are accounted for.
- Roles, grants, sequences, defaults, and encryption are verified.

### Layer 2: Data

- Row counts across large and business-critical tables.
- Checksums/hashes over selected datasets at a consistent point in time.
- Financial totals, order counts, and transaction statuses.
- Null counts, min/max timestamps, and unique constraints.
- Large objects, Unicode, time zones, and decimal precision.

Example PostgreSQL reconciliation queries once the source reaches a consistent verification point:

~~~sql
SELECT COUNT(*) AS order_count
FROM orders;

SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status
ORDER BY status;

SELECT MIN(created_at), MAX(created_at)
FROM orders;
~~~

On large tables, `COUNT(*)` can be expensive. Run queries in a DBA-approved window, using statistics, chunking, or optimized reconciliation methods—never run heavy full-table scans on production during peak hours.

### Layer 3: Application

- Java/Spring JDBC/Hibernate connects cleanly to the destination.
- Transactions and isolation levels behave properly.
- Query performance meets SLO targets.
- Critical business read/write flows succeed.
- Batches, ETL, reporting, and background workers operate properly.
- Time zone, collation, sequence, and transaction-retry behavior show no unintended regressions.

### Layer 4: Operations

- Backups/PITR and HA/DR are enabled per policy once destination becomes primary.
- Monitoring, logs, alerts, and on-call are established.
- Security controls/IAM, auditing, and secret rotation are verified.
- Test sign-off records and cutover approvers are documented.

## 14. Cutover Runbook for Continuous Migration

**Cutover** is the moment applications stop writing to the source and begin using the destination. The goal is guaranteeing **a single primary writer** at all times.

### Before the Cutover Window

1. Confirm the job is in CDC with stable replication delay.
2. Complete a rehearsal in staging or a production-like test environment.
3. Verify source backups/recovery and test restores if applicable.
4. Prepare configs, DNS/JDBC endpoints, secrets, firewalls, connection pools, and monitoring.
5. Approve downtime, owners, communications, and rollback criteria.
6. Close all critical open blockers.
7. List exact steps to freeze every writer—batches, ETL, cron, APIs, and admin scripts.

### During the Cutover Window

~~~mermaid
flowchart TD
  A[Announce cutover start] --> B[Stop all writes to source]
  B --> C[Drain app connections and batch jobs]
  C --> D[Wait for CDC backlog / lag near 0]
  D --> E{Validation passed?}
  E -->|No| F[Keep source as primary; resolve issues]
  E -->|Yes| G[Promote destination]
  G --> H[Update endpoints / secrets / routing]
  H --> I[Start app, test read/write]
  I --> J{SLOs and data valid?}
  J -->|Yes| K[Enhanced monitoring]
  J -->|No| L[Trigger designed incident / rollback runbook]
~~~

Execution steps:

1. Block ingress or place applications into maintenance mode.
2. Stop workers, schedulers, ETL, integrations, and any write-capable clients.
3. Let in-flight transactions finish or handle per runbook.
4. Measure replication lag until near 0 and confirm catch-up.
5. Run final reconciliation on critical tables.
6. **Promote** the migration job/destination per engine instructions.
7. Update JDBC connection strings, secrets, DNS, egress rules, and credentials.
8. Redeploy/restart or flush connection pools to drop old connections.
9. Test create/read/update and core business flows against the destination.
10. Monitor logs, error rate, latency, connection count, and new writes.

DMS may allow promoting while replication lag is non-zero, risking data loss or inconsistency. Never use that option as a shortcut to rush migration completion.

### Example `gcloud` Commands to Inspect Jobs

~~~bash
gcloud database-migration migration-jobs list --region=REGION --project=PROJECT_ID

gcloud database-migration migration-jobs describe MIGRATION_JOB_ID --region=REGION --project=PROJECT_ID
~~~

For promotion, use the Console or `gcloud database-migration migration-jobs promote` after verifying your `gcloud` version syntax and cutover gates. **Never run promote "just to test"** on a production job; promotion alters database roles and usually cannot be undone with a simple toggle.

## 15. Rollback: Why Must It Be Designed Ahead of Time?

Before promotion, rollback can usually stop the migration job and continue using the source, provided the source remained the primary writer without destructive changes.

**Once the destination accepts writes**, the old source is stale. DMS does not automatically sync new transactions backward from destination to source. Rollback therefore requires one of the following:

- Switching traffic back to the source **only when** certain zero new writes hit the destination.
- Running a separate, pre-tested reverse migration/replication pipeline.
- Restoring from backup and replaying eligible transactions.
- Pausing service and fixing issues forward on the destination instead of failing back.
- Performing a forward fix for defects that can be remediated safely.

Choose based on RPO, data types, and business impact. Define an explicit **point of no return**: the step after which returning to the source is unsafe without data reconciliation. Never write vaguely "roll back by changing the JDBC URL back."

### Minimum Rollback Runbook

| Requirement | Question |
|---|---|
| Trigger | Which failure forces rollback? |
| Decision maker | Who approves on the incident bridge? |
| Data | Have new writes hit the target, and how will they be preserved? |
| Routing | How are configs, DNS, credentials, pools, and networking reverted? |
| Recovery | Have backups, PITR, replicas, or reverse sync been tested? |
| Verification | Which business flows must be re-tested? |
| Communication | When are users and stakeholders notified? |

## 16. Impact on Java and Spring Boot Applications

After promotion, do not merely swap the hostname and declare victory. Review:

- JDBC driver compatibility with the destination engine/version.
- JDBC URL, SSL mode, certificate chains, and connection timeouts.
- HikariCP pool sizing and connection lifecycle.
- Transaction isolation/locking and retry policies.
- Schema migration tools such as Flyway/Liquibase.
- Hibernate dialects, native SQL, and data type mappings.
- Time zones/locales/collations and timestamp handling.
- Read replicas and read-only routing if applicable.
- Identity and Secret Manager integration for database credentials.
- Cloud SQL Connector/Auth Proxy or private IP per approved architecture.

Minimal Spring Boot configuration example (placeholders, no real passwords):

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://DB_HOST:5432/orders
    username: DB_USER
    password: DB_PASSWORD_FROM_SECRET
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
  jpa:
    open-in-view: false
~~~

Never commit `DB_PASSWORD_FROM_SECRET` with a real value. In production, load secrets from an approved environment/vault and use appropriate database authentication. Pool size is illustrative and must be sized against instance count and database connection limits.

### Cutover and Connection Pools

When the JDBC endpoint changes:

1. Ensure the application retains no open connections to the old source.
2. Redeploy or refresh pools via a tested method.
3. Run health checks executing real database operations, not merely returning HTTP 200.
4. Test read/write paths and transactions.
5. Watch connection counts on both destination and old source.
6. Check session/transaction timeouts and TLS errors.

If using DNS as a database alias, low TTL reduces caching in some components but **does not force every JVM or connection pool to refresh immediately**. Verify JVM DNS caching behavior and application lifecycle.

### Avoid Simultaneous Schema Changes Unless Required

When the primary goal is migrating database infrastructure, avoid combining a major version upgrade, ORM swap, large schema migrations, and business logic changes all at once. If schema changes are mandatory, maintain separate version compatibility plans and migration rehearsals.

## 17. Controlled Practice: PostgreSQL → Cloud SQL for PostgreSQL

This is a process lab; do not practice on production databases. Use a sandbox project, synthetic data, and controlled spend.

### Inputs

- PostgreSQL source on a DMS-supported version.
- A sample `orders` table containing test records.
- Source configured for logical replication per scenario.
- Compatible Cloud SQL for PostgreSQL destination.
- Network connectivity/TLS and a migration user.
- Google Cloud IAM permissions to create connection profiles/jobs.
- Runbook for creating/stopping jobs, cleanup, and checking billing.

### Steps

1. Seed initial data in the sandbox source.
2. Check version, extensions, replication parameters, and privileges.
3. Create the source connection profile.
4. Create the destination and connectivity method.
5. Create a continuous migration job and run **Test job**.
6. Start the job and observe initial load completion.
7. Insert/update/delete several test rows on the **source**.
8. Monitor CDC progress and replication delay.
9. Reconcile rows between both databases at a chosen verification point.
10. Stop all writes to the source.
11. Wait for lag near 0 and run final validation.
12. Promote the destination per scenario instructions.
13. Point a lab Spring Boot app to the destination and test reads/writes.
14. Review metrics/logs; record results and costs.
15. Delete the migration job, connection profile, and sandbox resources safely in order once done.

### PASS Criteria

- Connection tests and migration job report zero critical errors.
- Initial load captures complete data within selected scope.
- CDC replicates post-snapshot source changes to the destination.
- Replication lag drops within approved thresholds before promotion.
- Row counts and sample business totals reconcile cleanly.
- Java application connects and handles transactions properly.
- Backups, monitoring, and IAM are configured on the destination.
- No unnecessary lab resources remain after cleanup.

## 18. Common Migration Errors

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Test job cannot reach source | Wrong DNS, firewall, route, TLS, or port | Trace connectivity along the actual path |
| Authentication failed | Wrong user/password or privileges | Verify migration account and least-privilege grants |
| MySQL CDC fails to start | Binlog disabled, wrong format, or low retention | Check ROW binlog format and log retention |
| PostgreSQL CDC fails | Misconfigured logical replication, slots, or extensions | Cross-check scenario and source config |
| Initial load too slow | Insufficient throughput, network, or destination I/O | Measure bottleneck and adjust capacity |
| CDC lag grows continuously | High write rate, huge transactions, slow target | Inspect lag and resources on both ends |
| Source disk fills up | Binlog/WAL retained due to slow replication | Resolve lag; review retention/slots safely |
| Destination missing objects | Unsupported extensions, schema/DDL, or objects | Review known limitations; apply verified manual fixes |
| Row counts mismatch | Compared at different times, active writes, or sync error | Align on a consistent point and re-reconcile |
| Sequences out of sync after cutover | Sequences/identities not checked | Verify sequence values and grants post-promotion |
| App errors after pointing to target | JDBC/SSL/permissions/connection pool issues | Test driver, certs, secrets, network, and pool |
| Slow queries post-migration | Different indexes, stats, or query planner | Run ANALYZE/tuning and DBA benchmarks |
| Promoted with remaining backlog | Source writes not stopped; lag not near 0 | Never cut over until criteria pass |
| Rollback to source loses transactions | Target took writes without reverse sync | Follow rehearsed data rollback plan |
| Terraform drift | DMS modified destination during migration | Do not blindly re-apply; reconcile post-migration |

## 19. Security, Cost, and Long-Term Operations

### Security

- Scope DMS and IAM permissions to the exact project, region, and service.
- Use a dedicated DB account for migration and revoke/delete it afterward.
- Protect connection profiles, secrets, and TLS certificates.
- Prefer private connectivity or restricted networks whenever feasible.
- Never store dumps containing sensitive data in public buckets or shared folders.
- Record access permissions, audit logs, and firewall changes.
- Assess data residency, retention, and compliance rules before moving data.

### Cost

A migration can incur costs from:

- Cloud SQL/AlloyDB destinations provisioned and running during synchronization.
- Storage, network traffic, backups, and data egress from sources/other clouds.
- Migration service or feature charges per current pricing.
- Parallel operation of both source and destination systems.
- Logging/Monitoring and testing/reconciliation tooling.

Even before a migration job starts, a provisioned destination incurs charges. Track runtime and clean up resources after verification.

### Post-Cutover Operations

Once the destination becomes primary:

1. Verify backups, PITR, and HA per requirements.
2. Check database flags, maintenance windows, and storage autoscaling.
3. Configure monitoring, alerts, and auditing.
4. Update CMDB, diagrams, runbooks, and owners.
5. Confirm zero clients still write to the old source.
6. Decommission the source only after completing the observation window with formal approval.
7. Revoke migration privileges, close temporary firewalls, and rotate credentials.

## 20. Checklist Before Marking Migration Successful

- [ ] Source/destination pair is on the supported scenarios and versions list.
- [ ] Schemas, extensions, triggers, procedures, and compatibility are assessed.
- [ ] Least-privilege migration user/IAM and secure network paths are in place.
- [ ] Initial load succeeded and CDC runs stably where applicable.
- [ ] Zero replication errors and sufficient log retention.
- [ ] Dashboard monitors lag, job state, and disk usage.
- [ ] Data is reconciled using appropriate verification checks.
- [ ] Every write producer at the source has a documented stop plan.
- [ ] Downtime window, approvers, and communications plan are ready.
- [ ] Lag at cutover meets approved thresholds.
- [ ] Promotion succeeded and destination serves independently.
- [ ] Java/Spring apps switched endpoints and passed read/write tests.
- [ ] Destination backups/PITR, security, monitoring, and on-call are operational.
- [ ] Rollback/runbook explicitly addresses risks once destination takes new writes.
- [ ] Source is not deleted before formal decommission approval.

## Review Questions

1. Why does continuous migration still need a cutover window even though DMS copies changes via CDC?
2. Compare one-time migration vs. continuous migration when the source keeps accepting writes.
3. Is DMS suitable for operating two databases concurrently written by applications?
4. Why must you check `binlog_format=ROW` for continuous MySQL migrations?
5. In PostgreSQL, how do replication slots and WAL retention relate to disk growth?
6. Why is replication lag near 0 insufficient on its own to guarantee migration success?
7. When does a heterogeneous migration require a conversion workspace and application SQL testing?
8. Why shouldn't you write new data to the destination while CDC is still applying changes from the source?
9. If a Java API has already committed transactions to the destination before an issue is spotted, why is rolling back by pointing back to the old source unsafe?
10. After promotion, which operational capabilities must DBAs and SREs verify?

## Conclusion

Database Migration Service helps migrate databases to Cloud SQL and AlloyDB for PostgreSQL across supported scenarios, covering initial loads and continuous change synchronization where applicable. Continuous migration reduces downtime by maintaining CDC while the source continues serving, yet it never replaces **stopping writes, waiting for replication catch-up, reconciling data, promoting, and cutting over applications**.

For Java/Spring applications, migration is only complete when data is accurate, JDBC/transactions work, query performance meets targets, and operations teams have clear backups, IAM, monitoring, and rollback plans. The keys are thorough upfront discovery and validation, enforcing a single primary writer at any moment, and never mistaking DMS for a bidirectional active-active replication tool.

## References

- [Database Migration Service overview](https://cloud.google.com/database-migration/docs/overview)
- [Database Migration Service documentation](https://cloud.google.com/database-migration/docs)
- [Supported source and destination databases](https://cloud.google.com/database-migration/docs/supported-databases)
- [Known limitations by migration scenario](https://cloud.google.com/database-migration/docs/known-limitations)
- [Database Migration Service for PostgreSQL — Migration flow](https://cloud.google.com/database-migration/docs/postgres/migration-types)
- [Configure PostgreSQL source database](https://cloud.google.com/database-migration/docs/postgres/configure-source-database)
- [Configure MySQL source for continuous migrations](https://cloud.google.com/database-migration/docs/mysql/configure-source-database-continuous)
- [Create a PostgreSQL migration job](https://cloud.google.com/database-migration/docs/postgres/create-migration-job)
- [Promote a PostgreSQL migration job](https://cloud.google.com/database-migration/docs/postgres/promote-migration)
- [Cloud SQL for PostgreSQL documentation](https://cloud.google.com/sql/docs/postgres)
- [AlloyDB for PostgreSQL documentation](https://cloud.google.com/alloydb/docs)

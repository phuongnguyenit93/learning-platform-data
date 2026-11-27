# Managed MySQL Services and Operational/Backup Responsibility Boundaries

Managed MySQL services let development teams use a database without operating all servers, operating systems, storage, and infrastructure patching themselves. The provider typically handles a portion of tasks such as host provisioning, hardware replacement, platform monitoring, automated backups, or failover. However, the customer remains responsible for data, schemas, application accounts, access permissions, queries, retention policies, recoverability, and how applications behave during database disruptions.

Responsibility boundaries vary by product, tier, version, and purchased configuration. Never assume the word "managed" means the provider has already configured appropriate backups, guarantees every DBA operation is available, or assumes responsibility for recovering data to meet your organization's RPO/RTO. Read the service agreement, responsibility matrix, and technical limits clearly before promoting MySQL to production.

## 1. What Is Managed MySQL?

Managed MySQL is a database service in which the provider manages part or most of the infrastructure layer and operational lifecycle. Customers provision instances/clusters, choose versions, and configure resources via console, API, or infrastructure as code; applications connect via service-provided endpoints.

Common deployment models:

| Model | Provider typically manages | Customer still manages |
|---|---|---|
| Self-installed MySQL on VM | Virtual machine, partial networking, and storage per VM service | OS, MySQL, backups, patching, HA, DB security, and monitoring |
| Managed MySQL instance | Infrastructure, provisioning, partial patching/backups/monitoring, and platform operations | Schemas, users/grants, SQL, data, allowed config, backup/restore testing, and application |
| Managed MySQL cluster/compatible service | Cluster infrastructure, replication/failover, and platform-specific management features | Data model, permissions, queries, compatibility limits, backup policies, and DR as needed |
| Multi-tenant shared database platform | Database platform and tenant isolation | Tenant design, quotas, app permissions, data protection, and queries within granted scope |

A product name alone is insufficient to determine the model. Some services manage native MySQL; others are MySQL-compatible yet use proprietary storage/replication architectures. Verify compatibility for SQL syntax, storage engines, plugins, replication, backups, and operational tools your application depends on.

## 2. Provider vs. Customer Responsibility Matrix

Document who owns each layer explicitly rather than relying on a vague statement like "the provider manages the database." The matrix below is a starting point; adapt it to your actual contract and product.

| Area | Provider typically handles | Customer typically handles |
|---|---|---|
| Hardware, hosts, underlying storage | Provisioning, replacement, and platform maintenance | Selecting tier/capacity, evaluating deployment regions, and managing cost |
| Operating system | Patching and securing managed hosts | No direct OS access; expresses operational needs via service config |
| MySQL process | Process startup, monitoring, partial patching, and upgrades | Selecting versions, testing compatibility, allowed config, and tracking SQL behavior |
| HA/failover | Health checks, node switchover, or host replacement per tier | Choosing topology/tier, testing app reconnection, defining RTO, and post-failover handling |
| Platform backups | Running snapshots/backups per enabled features and retention | Enabling features, choosing retention, protecting delete permissions, testing restores, and meeting compliance |
| Data recovery | Providing restore tooling or contractual support | Choosing restore point, triggering restores, verifying data, cutover, and business reconciliation |
| Database users and privileges | Provisioning initial admin account or IAM integration | Managing users, roles, secrets, least privilege, and auditing |
| Schemas and queries | Providing engine and compatibility documentation | Designing schemas, indexes, transactions, migrations, and SQL tuning |
| Encryption and keys | Providing platform/KMS encryption options per service | Choosing key policies, managing key lifecycle, access control, and app-tier data protection |
| Monitoring | Exposing platform metrics/logs | Setting alerts, dashboards, SLOs, query analysis, and incident response |
| Data security | Securing infrastructure and tenant boundaries per commitment | Data classification, access controls, retention, masking, and incident response |

A provider may be responsible for running backup jobs while the customer remains responsible for verifying whether those backups meet recovery goals. A technically successful backup job does not prove the application can restore and resume normal operation.

## 3. DBA Privileges in Managed Services Are Limited

On self-managed MySQL, a DBA may have OS `root` access and nearly unrestricted MySQL privileges. In a managed service, the provider-supplied admin account usually holds broad database privileges without full MySQL `root` capabilities. Certain operations are restricted because they can affect the host, replication, backups, or other tenants.

Common restrictions:

- No direct access to the filesystem, processes, service manager, or host configuration files.
- No `sudo`, SSH to database hosts, or arbitrary file reads/writes via `LOAD DATA INFILE`/`SELECT ... INTO OUTFILE`.
- No full `SUPER`, `FILE`, `SHUTDOWN`, `RELOAD`, `PROCESS`, or permissions to modify system schemas; the service may substitute dynamic privileges or custom stored procedures.
- Cannot install arbitrary plugins, components, UDFs, or storage engines.
- Cannot directly control replication threads, binary log retention, or internal failover as on a self-managed server.
- Cannot modify all system variables; only variables permitted by the provider via parameter groups or APIs.

Therefore, never assume a runbook written for self-hosted MySQL runs verbatim on a managed service. Verify actual privileges and service documentation before executing DBA commands.

Inspect account privileges:

```sql
SELECT CURRENT_USER(), USER();
SHOW GRANTS;
```

`CURRENT_USER()` reports the MySQL account actually used for privilege checks; `USER()` reports the identity sent by the client when connecting. The two values can differ due to user/host matching rules.

Inspect privileges for a specific account:

```sql
SHOW GRANTS FOR 'orders_app'@'%';
```

Never read or update system grant tables directly to grant privileges. Use `CREATE USER`, `ALTER USER`, `GRANT`, `REVOKE`, or IAM/provider interfaces as supported.

## 4. Designing Least-Privilege Permissions

Never use the service's admin account for applications. Separate accounts by role and environment:

- Runtime account with read/write privileges only on required schemas and tables.
- Migration account with DDL privileges used during deployment windows, managed separately from runtime.
- Read-only reporting account, with resource limits or a dedicated reader endpoint if supported.
- Backup/export account with minimum privileges required by the backup tool and mechanism.
- Monitoring account allowed only to read required metrics or metadata.
- Break-glass account for emergencies, stored in a secret manager with every usage audited.

Example creating an application account and granting schema privileges:

```sql
CREATE USER 'orders_app'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';

GRANT SELECT, INSERT, UPDATE, DELETE
ON orders_db.*
TO 'orders_app'@'10.20.%';
```

The password in the example is a placeholder. Provision secrets securely; never commit them to source code or shared config files. Host patterns must match real network topologies and provider policies. If the service supports IAM database authentication, evaluate token mechanics, lifetimes, and how connection pools refresh credentials.

Migration accounts may need `CREATE`, `ALTER`, `INDEX`, `REFERENCES`, `DROP`, or additional privileges depending on migrations. Never grant DDL privileges to runtime accounts just because Hibernate uses `ddl-auto=update` in development. Production should manage schemas via controlled migration pipelines.

### Using Roles to Manage Privileges

MySQL supports roles on compatible versions:

```sql
CREATE ROLE 'orders_runtime';
GRANT SELECT, INSERT, UPDATE, DELETE
ON orders_db.* TO 'orders_runtime';

GRANT 'orders_runtime' TO 'orders_app'@'10.20.%';
SET DEFAULT ROLE 'orders_runtime' TO 'orders_app'@'10.20.%';
```

Verify default roles and effective grants after signing in with the application account. How providers handle admin accounts or IAM may differ; some services require creating users via console/API or restrict certain MySQL syntax.

## 5. Automated Backups Do Not Equal a Backup Strategy

Managed MySQL may offer one or more data protection mechanisms:

| Mechanism | Purpose | Limitations to understand |
|---|---|---|
| Automated backups | Periodic backups retained for a retention window | May need explicit enabling; retention, frequency, and scope vary by tier |
| Point-in-time recovery (PITR) | Restores to a timestamp within a supported window | Depends on base backups and retained transaction/binary logs; precision and limits are provider-defined |
| Manual snapshots | On-demand restore points before migrations or major changes | May share instance lifecycle; requires delete protection and retention governance |
| Cross-region/cross-account copies | Improves resilience if a region or account fails | Incurs lag, cost, regional restrictions, and encryption key dependencies |
| Logical exports | Schema/table/row-level copies for migration or archival | Time-consuming, requires privileges and storage; does not replace continuous PITR |
| Replicas | Serve reads or improve availability | Not independent backups; logical deletes/updates are replicated |

Verify that backups are enabled on the intended instance/cluster, check actual retention, latest backup timestamp, job status, and restore workflow. Never infer from a "Backups" button in the console that your data is protected.

## 6. Defining RPO and RTO

Two objectives must be aligned with the business:

- **RPO (Recovery Point Objective):** the maximum amount of data loss the business can tolerate, measured as the time window of data before an incident.
- **RTO (Recovery Time Objective):** the maximum acceptable time to restore the service to a usable state.

For example, a 5-minute RPO means the business tolerates losing at most roughly 5 minutes of data under defined scenarios; a 60-minute RTO means the service must be operational again within 60 minutes. These are targets, not automatic guarantees of every managed service tier.

Select backup frequency, PITR windows, HA topology, and DR regions according to RPO/RTO. A single daily snapshot cannot meet a 5-minute RPO without supplemental log/PITR mechanisms. A recoverable backup that takes 8 hours to restore, validate, and cut over cannot meet a 60-minute RTO.

Build a table per system:

| System | Target RPO | Target RTO | Planned mechanism | Required evidence |
|---|---:|---:|---|---|
| Orders | 5 minutes | 60 minutes | Automated backups + PITR, HA, and DR copy | Restore drills, transaction checks, and cutover timing |
| Reporting | 24 hours | 8 hours | Periodic snapshots or rebuild from source | Export/restore tests and data rebuild verification |
| Audit/ledger | Per business policy | Per business policy | Multi-layer backups, long retention, delete controls | Reconciliation, audit logs, and recovery evidence |

Values are illustrative only. Data and business owners must approve actual targets.

## 7. Point-in-Time Recovery and Transaction Logs

PITR restores a database to a specific timestamp within a supported recovery window. It typically combines a base backup with subsequent changes recorded via transaction logs or binary logs per the service architecture.

PITR is useful when:

- A faulty batch update was committed.
- A user accidentally deleted data.
- A migration caused unintended modifications.
- You need an environment reconstructed just before an incident for investigation.

PITR is not a single-table undo button. Many services restore into a brand-new instance/cluster at the chosen timestamp; DBAs must then verify, extract, or migrate the needed data before cutting over applications. Exact mechanics, granularity, and limits depend on the provider.

General workflow:

```text
Detect incident and freeze related mutations
                 |
                 v
Identify last known-good timestamp
                 |
                 v
Select base backup + PITR timestamp
                 |
                 v
Restore to an isolated instance/cluster
                 |
                 v
Verify schema, data, privileges, and integrity
                 |
                 v
Reconcile or extract data needing recovery
                 |
                 v
Approve cutover and switch applications
                 |
                 v
Monitor, reconcile, and archive recovery report
```

Never restore over a live production database without understanding service behavior and having a cutover plan. Keep the current instance for investigation when needed, while preventing two uncoordinated writers from accepting traffic concurrently.

## 8. Snapshots, Logical Backups, and Independent Copies

### Provider-Managed Snapshots

Snapshots are typically storage-layer copies or service-provided consistent backups. They work well for fast restore points or environment cloning. Verify whether snapshots are transactionally consistent, include full cluster/database metadata, completion times, retention, and cross-region/cross-account copying mechanics.

Snapshots stored in the same account and region remain exposed to admin privilege errors, accidental deletion, or account-level incidents. For critical data, consider independent copies, separated delete permissions, and immutable retention per organizational policy.

### Logical Backups

Logical backups export schemas and data as SQL or reloadable formats. They are useful for migrations, partial recovery, data inspection, and reducing lock-in to a single snapshot format. In return, exporting/importing large tables can be slow, generate read/write load, and require handling grants, routines, triggers, events, charsets, GTIDs, and non-table objects.

Example `mysqldump` for InnoDB tables:

```bash
mysqldump \
  --host=db.example.internal \
  --user=backup_user \
  --single-transaction \
  --quick \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  orders_db > orders_db.sql
```

This is a basic example; verify required privileges, client/server versions, GTID policies, and consistency options for your service. `--single-transaction` takes a consistent snapshot for transactional tables like InnoDB, yet does not protect against concurrent DDL altering structure mid-dump. Nor does it provide a consistent snapshot for non-transactional tables. Never put passwords directly on the command line; use login paths, secret injection, or your runtime environment's secure credential mechanism.

For large databases, evaluate parallel export tools such as MySQL Shell or provider-supported backup utilities. Check whether the service permits connecting to a replica to offload backups and whether the replica lags. Never run heavy dumps against production without measuring impact.

### Do Not Store the Only Backup Next to the Database

Backup copies should have independent access controls, lifecycles, and failure domains matching your threat model. Consider:

- Copying to a separate backup account or project.
- Copying to another region when DR requires protection from regional outages.
- Encrypting with keys having managed policies and lifecycles.
- Retention locks/immutability if supported by the service and required by policy.
- A dedicated restore account, separate from runtime credentials.
- Auditing backup creation, copying, restoration, and deletion operations.

## 9. HA, Read Replicas, and Backups Solve Different Problems

High availability and backups do not replace each other.

| Mechanism | Protects against | Does not fully protect against |
|---|---|---|
| Multi-zone/standby failover | Host or zone failures per service design | Accidental deletes, bad updates, ransomware, or valid-SQL logic bugs |
| Read replica | Read capacity scaling, some DR/failover scenarios | Replicated bad data; replicas can lag or share regional failures |
| Automated backups/PITR | Recovering historical data after logic bugs or data loss | Instantaneous outage masking; RTO can exceed HA failover |
| Independent snapshots | Restoring to a created point in time | Post-snapshot changes without PITR |
| Logical exports | Selective migration/recovery and portable storage | Fast recovery of very large databases unless optimized |

A replica helps with reads or speeds switchover when a primary fails, yet if a `DELETE` without `WHERE` replicates, the replica executes the delete too. You need backups and PITR to recover state prior to the erroneous operation.

Likewise, multi-zone failover keeps the service online when one node fails, yet cannot recover rows validly deleted via SQL. HA focuses on availability; backups focus on recoverability.

## 10. Restore Drills Prove Backups Are Usable

A green backup job in a dashboard only proves the provider reported job completion. It does not prove:

- The backup contains every needed database, schema, trigger, routine, event, and metadata.
- Encryption keys still exist and the restore account has permission to use them.
- The restored instance can boot with compatible MySQL versions/parameters.
- The application can connect, authenticate, and run critical queries.
- Recovered data meets RPO targets.
- Total time for restore, verification, and cutover meets RTO targets.

Run restore drills on schedule and after major changes:

1. Select a backup or PITR timestamp inside the retention window.
2. Restore into an isolated environment; never route production traffic to it.
3. Verify server version, schemas, accounts, grants, charsets/collations, and required parameters.
4. Run integrity checks: row counts, monetary totals, foreign keys, checksums, or business reconciliation.
5. Run application smoke tests and critical queries.
6. Measure elapsed time from restore initiation to service readiness.
7. Record the latest recoverable data timestamp and any gap against RPO.
8. Tear down the test environment per procedure and archive evidence.

Restore drills should also test operational permissions: can on-call engineers locate backups, request restores, access keys, and execute cutover using the runbook? Never let the process depend on a single individual holding special privileges.

## 11. Securing Backups and Encryption Keys

Backups typically contain all sensitive database data. Encryption at rest is insufficient if too many people hold permissions to restore, export, or read decrypted dumps.

Controls to enforce:

- Encrypt backups using provider capabilities and data requirements.
- Separate permissions for creating, reading, copying, restoring, and deleting backups.
- Separate backup key management from runtime permissions where appropriate.
- Define key rotation, disablement, revocation, and recovery policies.
- Verify cross-region/cross-account backup copies use keys accessible at the recovery destination.
- Encrypt logical dump files at rest and in transit; minimize temporary file lifetimes.
- Never send dumps via email, tickets, or public artifact repositories.
- Audit access and restore/export operations.
- Enforce retention and secure deletion per legal/business mandates.

If an encryption key is deleted or access is lost, encrypted backups may become permanently unrecoverable. Key lifecycle management is part of the backup strategy, not a separate security-team task.

## 12. Monitoring and Operations Within Granted Scope

Managed services typically expose metric dashboards or APIs. Key metrics:

- CPU, memory, storage used, storage growth, and I/O latency.
- Database connections, active sessions, connection errors, and pool saturation.
- Query latency, slow query logs, rows examined, and deadlocks.
- Buffer pool hit/miss ratio, temporary tables, and redo/log pressure if exposed.
- Replica lag, replication health, and failover status.
- Backup status, backup age, retention, and snapshot storage usage.
- Maintenance events, restarts, failovers, and version lifecycle notices.

Not every service exposes all InnoDB metrics or allows reading every Performance Schema table. When privileges or metrics are restricted, find equivalents via provider APIs, enhanced monitoring, or log exports. Never attempt to access hosts to extract metrics disallowed by the service.

Example status checks inside MySQL when privileges permit:

```sql
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Threads_running';
SHOW GLOBAL STATUS LIKE 'Aborted_connects';
SHOW GLOBAL STATUS LIKE 'Innodb_deadlocks';
SHOW FULL PROCESSLIST;
```

Combine provider metrics with query digests/slow logs to distinguish high CPU caused by SQL, oversized connection pools, slow storage, or sudden traffic spikes. Alert on SLOs and trends; a single CPU threshold is insufficient to diagnose incidents.

## 13. Parameter Groups and Configuration Changes

Managed services rarely allow direct editing of `my.cnf`. Instead, providers offer parameter groups or API-based configuration. Variables generally fall into categories:

- Dynamic: applied immediately or for new sessions.
- Static: requires an instance/cluster restart or maintenance window.
- Unsupported/locked: provider disallows changes.
- Provider-specific: naming or semantics differ from self-managed MySQL.

Before changing a setting:

1. Confirm the variable is supported on your current engine/version/tier.
2. Determine global/session scope and whether a restart is required.
3. Record current values and provider defaults.
4. Test in staging under a representative workload.
5. Assess impact on failover, replicas, and active sessions.
6. Schedule, notify stakeholders, and prepare a configuration rollback plan.

Never copy an entire `my.cnf` from a self-managed server into a parameter group. Some variables are provider-managed or incompatible with the service architecture. Changing variables such as `max_connections`, `innodb_buffer_pool_size`, or redo capacity may be capped by tier and memory budgets.

## 14. Maintenance, Patching, and Version Upgrades

Providers may perform host patching, MySQL patching, restarts, or failovers during maintenance windows. Customers must know:

- Whether maintenance windows are configurable or provider-scheduled.
- Advance notice lead times and notification channels.
- Whether the service restarts or fails over during maintenance.
- Whether minor/major version upgrades require explicit approval.
- How long maintenance can be deferred.
- Whether replicas, connectors, plugins, and migrations are compatible with the new version.

Applications must tolerate connection resets and reconnect gracefully. Never assume an endpoint always resolves to the same IP or that existing connections survive failover. Use provider-issued DNS/endpoints, properly configured connection pool lifecycles, and idempotent retries at transaction boundaries.

For major upgrades, test SQL modes, authentication plugins, collations, optimizer plans, deprecated/removed features, drivers, and stored programs. Run migrations on a production-like clone, measure duration, and prepare rollback/forward-fix plans within service limits. Some managed services do not support in-place downgrades; rollback may require restoring a backup to an older-version instance and shifting traffic.

## 15. Networking and Endpoints for Managed MySQL

Managed services usually expose DNS endpoints rather than fixed IP addresses. Multiple endpoints may exist:

- Writer/primary endpoint for write operations.
- Reader endpoint distributing connections across replicas.
- Instance endpoint to connect directly to a specific node during investigation.
- Private endpoint or private IP reachable only from linked networks.

Naming and semantics vary by provider. A reader endpoint may load-balance per connection rather than per query; long-lived connection pools can skew distribution. Replicas can lag, so applications must not read immediately from a reader endpoint when strict read-after-write is required without an explicit consistency mechanism.

Network security practices:

- Prefer private networks/private endpoints when architecture allows.
- Restrict security groups/firewalls to required source workloads and ports.
- Enable TLS and verify CA/hostnames per provider guidance.
- Never open MySQL ports to the public Internet merely for testing convenience.
- Manage DNS caching and connection pool lifetimes so applications follow failovers promptly.
- Separate network reachability from database privileges; reaching an endpoint does not imply SQL permissions.

## 16. Cost and Service Quotas

Managed services reduce infrastructure labor yet introduce costs and quotas that must be planned for:

- Instance/compute tiers and scale-up/scale-down flexibility.
- Provisioned storage, autoscaling, IOPS, and throughput.
- Automated backups, snapshot retention, and backup copies.
- Cross-region replication, network egress, and data transfer.
- Log exports, enhanced monitoring, and log retention duration.
- Read replicas, standbys, and DR environments.
- Support tiers, maintenance, and restore operations.

Storage autoscaling does not mean storage automatically shrinks when data is deleted. Some services only grow storage and prohibit shrinking it directly. Long backup retention can increase costs proportionally to change rates. Account for DR copy costs and legacy snapshot retention too.

Review service quotas such as max connections, max replicas, storage ceiling, IOPS caps, packet/statement limits, database counts, and import/export limits. Design applications around real production quotas; never mistake trial-tier limits for universal limits across all tiers.

## 17. Multi-Layer Backup and DR Plan

A production strategy can include:

1. Automated backups/PITR meeting daily operational RPO.
2. Manual snapshots before migrations, major changes, or risky operations.
3. Backup copies to an independent region/account when DR and accidental-deletion protection require them.
4. Periodic or on-demand logical exports for portability/selective recovery.
5. Read replicas or standbys for availability/reads, never counted as the sole backup.
6. Scheduled restore drills and re-testing after provider, version, key, or retention changes.
7. Recovery runbooks, owner rosters, break-glass access, and cutover approval procedures.

Not every system needs every layer. Choose based on data classification, RPO/RTO, cost, and risk. What is mandatory is that every chosen layer has an owner, retention policy, access controls, and recovery proof.

## 18. Recovery Runbook for Managed MySQL Incidents

During an incident, identify the failure class first:

| Scenario | Initial response |
|---|---|
| Instance/host failure while HA still functions | Monitor failover, endpoints, and app reconnection; do not initiate manual restore while the service is recovering |
| Accidental delete or erroneous data update | Stop the offending job, identify last good timestamp, use PITR/snapshot to spin up an isolated instance, and extract data |
| Region or account unreachable | Activate DR plan, verify backup copies, keys, DNS/networking, and permissions in the target region |
| Backup job failure | Assess protection gap, fix permissions/quotas/storage, rerun backup, and evaluate RPO exposure |
| Restore blocked by key/permissions | Engage key/IAM owners; never delete or rotate keys further until decryption capability is confirmed |
| Replica lag or applier error | Determine if the replica remains fit for reads/failover; never promote solely because the primary is slow |

Data recovery sequence:

1. Designate an incident commander and data owner.
2. Record incident start time, blast radius, and recent changes.
3. Halt or throttle offending writers if they could worsen damage.
4. Identify the restore target and matching backup source.
5. Provision an isolated restore target; preserve the current source for investigation if needed.
6. Verify permissions, keys, version, schema, and integrity.
7. Reconcile data and approve the cutover point.
8. Switch endpoints/traffic per runbook; verify connection pools and applications.
9. Monitor error rates, latency, replication, incoming writes, and complete reconciliation.
10. Document actual RPO/RTO, root cause, and preventive actions.

## 19. Practical Scenario

An e-commerce application uses a single-writer managed MySQL instance with one reader replica. The operations team assumed the provider backed everything up automatically and never tested a restore. A faulty migration accidentally deleted order data over a brief window; the replica applied the delete as well.

**Step 1 — Clarify responsibilities.** Check the service contract, whether automated backups are enabled, the retention window, PITR availability, who holds restore permissions, and where backup copies reside.

**Step 2 — Stop the bleeding.** Halt the faulty migration/job, restrict writers if necessary, and record when the erroneous operation started. Do not promote the reader replica because the deletion already replicated.

**Step 3 — Choose the restore point.** Determine the timestamp immediately before the delete statement. Use PITR to launch a new instance inside an isolated network; keep the live database intact for investigation.

**Step 4 — Verify data.** Reconcile order counts, monetary totals, statuses, foreign keys, and sample records. Confirm schemas, grants, and application read access against the restore target.

**Step 5 — Selective recovery.** If only a subset of orders was deleted, extract the affected records and child dependencies from the restore target and re-import them into production via an idempotent, reconciled workflow. If a full database rollback is necessary, plan cutover and reconcile valid transactions committed after the restore timestamp.

**Step 6 — Measure RPO/RTO.** Record the latest recovered data timestamp along with total time for restore, validation, and cutover. Compare against approved targets.

**Step 7 — Remediate.** Establish scheduled restore drills, pre-migration snapshots, separated backup-delete permissions, approval gates for destructive migrations, and alerts on overdue or failed backups.

This scenario demonstrates that HA and replicas do not shield against replicated logic errors. Only backups/PITR paired with rehearsed restore procedures deliver genuine data recoverability.

## 20. Pre-Production Managed MySQL Checklist

- [ ] Service model and actual MySQL compatibility verified.
- [ ] Provider/customer responsibility matrix documented for patching, HA, backups, restores, monitoring, and security.
- [ ] Restricted DBA privileges and provider API/console alternatives verified.
- [ ] Runtime, migration, reporting, backup, and monitoring use separate least-privilege accounts.
- [ ] Automated backups confirmed enabled, retention verified, and backup job status monitored.
- [ ] PITR window meets RPO and restore timestamp selection procedure is known.
- [ ] Snapshots/backups protected from accidental deletion, with independent copies if required by DR.
- [ ] Encryption keys verified available at the recovery destination and time; key permissions tested.
- [ ] Restore drill completed in an isolated environment with actual RTO/RPO measured.
- [ ] HA failover, read replicas, snapshots, and PITR clearly distinguished.
- [ ] Application handles connection resets, reconnects, and idempotent retries after failover.
- [ ] Private networking, firewalls, TLS, and appropriate endpoints configured.
- [ ] Parameter groups, maintenance windows, version lifecycles, and upgrade processes reviewed.
- [ ] Metrics/alerts configured for CPU, storage, connections, latency, replica lag, and backup status.
- [ ] Costs budgeted for compute, storage, backup retention, replicas, DR, and data transfer.
- [ ] Recovery runbooks, owners, break-glass access, and cutover procedures rehearsed.

Managed MySQL offloads part of infrastructure labor to a provider without transferring full responsibility for data. Customers must understand DBA privilege boundaries, design application permissions, verify backups/PITR, safeguard encryption keys, and rehearse restores against RPO/RTO targets. HA, replicas, and backups address distinct risks; only when responsibility boundaries, operational privileges, and recovery procedures are verified does a managed service meet production requirements.

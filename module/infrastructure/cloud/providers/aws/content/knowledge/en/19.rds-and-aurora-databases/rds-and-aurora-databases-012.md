# Maintenance, Version Upgrades, and Blue/Green Database Deployments

> **Chapter:** RDS and Aurora Databases  
> **Module:** `CLOUD_PROVIDERS_AWS` — explore AWS from Regions/AZs, IAM, VPC, compute, and storage to databases, integration, and serverless; practice selecting services, building secure systems, monitoring, recovery, and cost control.

A Java Spring Boot application is using PostgreSQL in **Amazon RDS**. The database has been running stably for months, but the engine version is approaching end of support, security patches need to be applied, and the application has constraints around JDBC libraries, extensions, and stored procedures. Simply clicking "Upgrade" in the Console can force the database to restart, drop connections in the pool, break SQL compatibility, or extend write downtime longer than expected.

**Amazon RDS** and **Amazon Aurora** reduce database infrastructure administration effort, but **do not eliminate the responsibility for maintenance planning, upgrade testing, version management, backups, and recovery**. One useful technique is **Blue/Green Deployments**: create a synchronized *green* environment from the production *blue* environment, test the new version/configuration on green, and perform a **safety-checked switchover** when ready.

This lesson presents the journey from **routine maintenance → minor/major upgrades → blue/green rehearsal → switchover → post-cutover verification → incident handling**. The content covers both **RDS DB instances** and **Aurora DB clusters**, clearly noting where they differ. Resource names, ARNs, endpoints, accounts, and numbers in the examples are all hypothetical; do not run commands that modify a production database without approval and a runbook.

**Note on timing and support:** Supported engines, versions, Regions, Aurora Global Database features, RDS Proxy support, replication methods, and Blue/Green limitations change over time. Always check the AWS documentation for the **exact engine, version, and Region** before deploying. Any downtime or timeout numbers mentioned are expectations/configurations, not immutable SLAs.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish between **system maintenance**, **engine minor/major version upgrades**, **parameter/option group changes**, and **DB instance class/storage changes**.
2. Explain **preferred maintenance window**, pending maintenance, `ApplyImmediately`, auto minor version upgrade, reboot, and the impact of **Multi-AZ**.
3. Plan an upgrade based on the compatibility matrix, extensions, JDBC driver, schema, performance baseline, and rollback/restore plan.
4. Describe Blue/Green Deployments: **blue serves production; green is synchronized staging**; explain replication lag, guardrails, switchover, and endpoint changes.
5. Recognize important limitations of **RDS for MySQL/MariaDB/PostgreSQL** and **Aurora MySQL/PostgreSQL**, especially that **PostgreSQL logical replication does not synchronize DDL/DCL like DML**.
6. Design a runbook for **preflight, rehearsal, switchover, post-cutover**, and recovery strategies when errors occur.
7. Use **read-only** AWS CLI commands to inspect database configuration, engine upgrade targets, pending maintenance, blue/green deployments, and CloudWatch.
8. Evaluate impacts on **RPO/RTO, PITR history, dual-environment cost, IAM, security, and Java applications**.

## 2. Why Does Database Maintenance Always Require a Plan?

A database is a **stateful** system: if there is a change to the engine or where data is written, you cannot recover simply by starting additional containers like many stateless web services.

~~~mermaid
flowchart LR
  USERS["Users"] --> ALB["ALB / API"]
  ALB --> APPS["Java Spring Boot\nECS / EKS / EC2"]
  APPS --> POOL["JDBC / HikariCP\nconnection pools"]
  POOL --> PROXY["RDS Proxy (if used)"]
  PROXY --> DB["RDS/Aurora writer"]
  DB --> ST["Persistent database data"]
  DB -.-> MON["CloudWatch / Database Insights"]
  DB -.-> BACK["Automated backup / snapshot"]
~~~

When the database restarts or the writer endpoint changes its target, the chain of impacts can include:

- Existing TCP connections are closed; in-flight transactions must retry or are rolled back depending on the engine.
- Connection pools hold stale connections; the application raises `SQLTransientConnectionException` or timeouts.
- DNS/JVM/client caches retain the old target address, so requests continue hitting the wrong node during the transition.
- Read replicas/replication lag, replication slots, CDC, or ETL jobs may need reconfiguration.
- An incompatible schema operation causes the current application release to read/write incorrectly.
- Backup/PITR or cross-account audits may reference **resource IDs** instead of the display name after switchover.

Therefore, the goal is not merely a "successful upgrade," but:

~~~text
New, supported, and secure database version
        + data integrity
        + application compatibility
        + interruption duration within SLO
        + recoverability and auditability
~~~

### 2.1. Four Questions to Ask Before Making a Change

| Question | Example Answer Required |
| --- | --- |
| **What is changing?** | Aurora PostgreSQL minor patch or major PostgreSQL upgrade? |
| **Blast radius?** | Single-AZ instance, RDS Multi-AZ instance, or Aurora cluster with writer/readers? |
| **Acceptable disruption?** | 5-minute RTO, write outage under 60 seconds, API p99 under 1 second after recovery |
| **How to revert/recover?** | Retain blue, snapshots, PITR, exports, restore tests, and a strategy for data written after cutover |

In particular, **you cannot define a true rollback without answering "where does data written after switchover go?"** This is the biggest difference between blue/green for stateless applications and stateful databases.

## 3. Types of Changes in Amazon RDS and Aurora

| Change | Examples | Can cause disruption? | Verification points |
| --- | --- | --- | --- |
| **System/host maintenance** | OS patch, security update, host replacement | May require reboot or failover | Pending maintenance, events, Multi-AZ |
| **Minor engine upgrade** | PostgreSQL 15.x → 15.y per supported target | Usually requires restart; may cause outage | Release notes, bug fixes, extensions |
| **Major engine upgrade** | PostgreSQL 15 → 16, Aurora major family | Has compatibility changes; downtime can be significant | Upgrade path, prechecks, app schema |
| **Parameter group** | `max_connections`, logging, extensions | Dynamic or pending-reboot | Parameter apply type, pending reboot |
| **Option group (applicable RDS engines)** | Engine-specific options | May have engine/OS impact | Option compatibility by engine/version |
| **Instance class** | Increase vCPU/RAM | May restart/failover | CPU, memory, EBS throughput, DNS |
| **Storage configuration** | IOPS, storage type, size | Depends on supported operation; may impact I/O | Limits and online modification support |
| **Certificate/CA rotation** | Update CA for database TLS | Client truststore may need updates; rotation method determines outage | Driver/JVM truststore, DB cert expiry |
| **Topology** | Multi-AZ/reader/add replica | May change endpoints/connection behavior | Quotas, replication, failover |

A set of changes can be processed in the same maintenance window, but **do not assume bundling multiple changes always reduces downtime or is safer**. When something fails, it is very hard to isolate the root cause if you upgrade the major version, change the instance class, rotate the CA, and update the ORM all in one batch.

## 4. Maintenance Windows, Pending Actions, and `ApplyImmediately`

### 4.1. What Is a Preferred Maintenance Window?

A **Preferred maintenance window** is the time interval during which RDS/Aurora prefers to **start** relevant maintenance activities, typically a window of at least about 30 minutes per service configuration. **Do not interpret this as AWS guaranteeing all work finishes within 30 minutes**; a major operation can take longer.

~~~mermaid
flowchart LR
  A["AWS announces maintenance"] --> P["Pending maintenance action"]
  P --> D{"Mandatory / optional?\nCan be deferred?"}
  D -->|"Proactively chosen"| NOW["Apply at scheduled time"]
  D -->|"Per service schedule"| W["Preferred maintenance window"]
  NOW --> I["Database maintenance\nmay reboot/failover"]
  W --> I
  I --> O["Verify engine / app / metrics"]
~~~

Things to keep in mind:

- **System updates and engine updates do not always share the same application mechanism**.
- Some maintenance is **required** with a deadline; deferring past the deadline may result in AWS applying it per policy.
- **The maintenance window is not "the only time the DB can restart"**: failover, infrastructure incidents, selecting `ApplyImmediately`, or manual actions can cause restarts outside that window.
- For **Aurora**, the **DB cluster** maintenance window, and for **RDS instances**, the **DB instance** maintenance window must be checked per resource type.
- **Pending modifications** differ from **pending maintenance actions**; inspect both.

### 4.2. `ApplyImmediately` vs. Selecting "Next Maintenance Window"

When modifying a database via the Console/API, you typically choose:

- **Apply immediately:** RDS begins applying eligible changes promptly, which may cause immediate disruption instead of waiting for the maintenance window.
- **Apply during next maintenance window:** stores changes in pending modifications and applies them according to the corresponding schedule.

**Do not assume "Apply immediately" always means zero downtime or finishes in a few seconds**. Depending on the operation, RDS may execute immediately, schedule the work, or combine multiple pending modifications; consult the impact matrix for each change type.

### 4.3. Pending-Reboot Does Not Clear Itself

Some **static parameters** require a **reboot** to take effect. When a parameter group shows **`pending-reboot`** status, do not assume the change will automatically apply during the next maintenance window; depending on the RDS/Aurora mechanism, an explicit reboot and planned outage/failover may be required.

| Parameter | Characteristics | Correct action |
| --- | --- | --- |
| **Dynamic** | Can be applied while the database is running as supported | Verify apply method and effective value |
| **Static** | Requires database engine restart | Record pending-reboot, schedule, and test |
| **Cluster parameter group** | Affects cluster/engine-level configuration | Check status across Aurora DB cluster/instances |
| **DB instance parameter group** | Affects a specific DB instance | Verify writer/readers all use the appropriate group |

### 4.4. Automatic Minor Version Upgrades

RDS provides the **`AutoMinorVersionUpgrade`** option for many supported engines/instance types. When enabled, the service can automatically schedule minor version upgrades **designated by the automatic mechanism**, which is not necessarily the latest minor version just released.

Change-controlled architectures should explicitly specify:

1. When automatic minor upgrades are permitted?
2. When prior testing on staging is required?
3. Are alerts configured for scheduled/mandatory upgrades?
4. Is engine/driver/extension compatibility cross-checked?
5. Are restore and failover practiced?

In Aurora, engine updates and auto-minor behavior must be checked against **cluster engine family/instance settings and current engine capabilities**; do not assume RDS PostgreSQL and Aurora PostgreSQL behave identically.

## 5. Minor Versions vs. Major Versions: Different Risk Profiles

### 5.1. Minor Upgrades

**Minor versions** typically consist mainly of security fixes, bug fixes, and stability/performance improvements. Although they have fewer breaking changes than major versions, they can still:

- Change the query planner and query performance.
- Affect extensions, drivers, or native clients.
- Require restart/failover, causing temporary connection interruptions.
- Alter behavior that the application unintentionally relied upon.

Do not skip integration tests just because the update label contains a minor version number.

### 5.2. Major Upgrades

**Major version upgrades** can alter system catalogs, data formats, feature support, SQL semantics, the query optimizer, and extension/plugin compatibility. In particular, PostgreSQL major upgrades require checking:

- Extensions: `pg_stat_statements`, `pg_cron`, `postgis`, and third-party extensions for the target version.
- Options/parameters that have been renamed or deprecated/removed.
- Stored functions, materialized views, logical replication, foreign data wrappers, and client drivers.
- Schema migrations: avoid introducing breaking DDL changes during windows with replication restrictions.
- **Valid upgrade path**: not every source version can upgrade directly to every target version.

For MySQL/Aurora MySQL, review charsets/collations, reserved keywords, authentication, SQL modes, indexes, and query plans in the corresponding engine release notes.

### 5.3. SQL Compatibility Does Not Equal Performance Compatibility

A SQL query may still run after an upgrade yet become slow because planner statistics or parameters changed. Therefore, a baseline requires:

~~~text
Before upgrade:
  p95/p99 query latency
  Queries per second, write throughput
  CPU / FreeableMemory / DB connections
  Top SQL by DB load
  Lock wait, deadlocks, replication lag
  Disk IOPS, read/write latency

After upgrade:
  Same workload, same connection pool
  Compare query plans and latency/throughput
  Check memory pressure and error logs
~~~

Merely seeing `SELECT version()` succeed **is not sufficient** to confirm an upgrade did not regress performance.

## 6. Multi-AZ, Backups, and Commonly Confused Concepts

| Mechanism | Solves best | Does **not** solve on its own |
| --- | --- | --- |
| **RDS Multi-AZ DB instance** | Redundancy/failover in another AZ with standby | Independently testing a new major version before release |
| **Aurora cluster with writer/readers** | Separating read workloads, topology failover by design | Schema rollback, accidentally deleted data |
| **Read replica** | Read scaling, certain DR or replication needs | Independent backup / zero data loss in all scenarios |
| **Automated backups/PITR** | Restoring data to a supported point in time | Instant production traffic shift with zero downtime |
| **Manual snapshot** | Explicit recovery point, retained longer when needed | Catching up writes made after the snapshot |
| **Blue/Green Deployment** | Testing version/config on a synced environment before cutover | Zero downtime / instant reversal after cutover |

### 6.1. Does Multi-AZ Make Upgrades Non-Disruptive?

No. Multi-AZ helps reduce the impact of certain failures and maintenance operations through standby/failover by design, but **there is no guarantee that all engine upgrades have zero disruption**. Major upgrades may require additional time; DB restarts, replication health, and DNS/caching can cause transient application errors.

### 6.2. Backups and RPO Before Upgrading

Before an operation that is not easily reversible:

- Check backup retention, `LatestRestorableTime`, and `Point-in-Time Restore` capability for the exact instance/cluster.
- Consider taking a **manual snapshot** before a major upgrade or when a specific recovery point must be retained.
- Do not consider a newly created snapshot sufficient for RTO without practicing a restore and measuring the actual duration.
- Ensure necessary IAM/KMS permissions exist to access snapshots/backups during recovery.
- For large datasets, evaluate restore duration, index/cache warming time, and the cost of provisioning a new environment.

**RPO = maximum acceptable data loss; RTO = time required to restore functionality.** Having a snapshot alone proves neither target is met.

## 7. Blue/Green Deployments: Concept and Lifecycle

**Blue/Green** is an approach to reducing database change risk by **separating the current production environment from the change-testing environment**, while keeping new data on green synchronized from blue via a service-supported replication mechanism.

~~~mermaid
flowchart TB
    APP["Application\nProduction DB endpoint"] --> BLUE["BLUE\nRDS / Aurora production\nwriter + readers per topology"]
    BLUE -->|"Managed replication\nBlue → Green"| GREEN["GREEN\nSynchronized staging\nnew version / parameters"]
    TEST["Read-only compatibility\nchecks & safe load tests"] -.-> GREEN
    HEALTH["CloudWatch / RDS monitoring\nReplication lag + DB health"] -.-> BLUE
    HEALTH -.-> GREEN
    GATE{"Go / No-Go\nGuardrails + approved window"} --> CUT["Managed switchover"]
    CUT -->|"Switches production endpoint target"| GREEN
~~~

**Consistent terminology throughout the workflow:**

- **Blue:** the production database **currently** serving the application.
- **Green:** the staging environment created from blue, kept in sync via service-supported replication.
- **Switchover:** a managed operation so that **green becomes the new production** after verifying synchronization and health.
- **Old blue:** the previous production database, retained after switchover per service rules and resource cleanup policy.

### 7.1. Phased Lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> Planning
    Planning --> Creating: Validate prerequisites
    Creating --> Replicating: Green created
    Replicating --> Testing: Sync healthy
    Testing --> Replicating: Fix / retest
    Testing --> Ready: Change approved
    Ready --> Switching: Switchover request
    Switching --> Complete: Guardrails pass and switch
    Switching --> Replicating: Switch failed/timed out; state recovered
    Complete --> PostCutover: Application validation
    PostCutover --> Retired: Retention and cleanup policy
    Retired --> [*]
~~~

*This diagram is an operational model, not an exact list of AWS API states. Actual state names come from `DescribeBlueGreenDeployments` and RDS/Aurora events.*

### 7.2. Changes Commonly Applied to Green

- **Minor/major engine version upgrades** along supported upgrade paths.
- Changing DB instance class or resource-compatible storage/cluster configuration.
- Adjusting **parameter groups**, verifying the impact of static parameters after reboot.
- Testing alternative configurations to lower risk when upgrading production.
- Testing SQL/JDBC/ORM compatibility and performance baselines.

Not every operation can be performed safely on green while replication is active. **Changing the schema on green** can conflict with replication; **writing data to green** can cause divergence from blue. Attempting schema upgrades via blue/green requires carefully reading **replication compatibility** for the engine/mode and using an appropriate migration pattern.

### 7.3. Fast Switchover Does Not Mean Zero Downtime

AWS describes Blue/Green switchover as typically completing **in under a minute** under suitable conditions and designed to avoid data loss during a valid switchover. However, the actual operation:

1. Runs guardrail checks.
2. Pauses **writes**, closes certain database connections, and blocks new connections during the transition.
3. Waits for green to catch up on replication.
4. Switches database names/endpoints accordingly so the production endpoint continues pointing to the new database.
5. Allows connections/writes to resume once the switch finishes.

The application must tolerate a **brief interruption**, reconnect, and retry safely. Duration can exceed expectations or switchover can be aborted if conditions are not met; never write "zero downtime" into an SLA merely because Blue/Green is used.

## 8. Which Engines Does AWS Support for Blue/Green?

| Service | Primary Support Scope | What to Check During Planning |
| --- | --- | --- |
| **RDS for MySQL** | Blue/Green Deployments in supported Regions/versions | Binlog/replication, parameter groups, option groups, replicas |
| **RDS for MariaDB** | Blue/Green Deployments in supported Regions/versions | Engine version, binary logs, topology, dependencies |
| **RDS for PostgreSQL** | Blue/Green depending on version/replication mode | Physical vs. logical replication, DDL/DCL, slots, sequences, extensions |
| **Aurora MySQL** | Aurora Blue/Green in supported versions/Regions | Cluster topology, engine upgrade path, binlog, and Aurora features |
| **Aurora PostgreSQL** | Aurora Blue/Green in supported versions/Regions | Logical replication caveats, cluster/reader behavior, statistics |
| **Aurora Global Database** | Blue/Green supported for **eligible versions and configurations** | Global topology, secondary Regions, specific characteristics and limits |
| **Other RDS engines** | Do not assume equivalent Blue/Green support | Check support matrix; consider snapshot/restore, DMS, or engine-specific techniques |

**Important:** RDS Blue/Green documentation and Aurora Blue/Green documentation are **two separate guides**. If you read a page stating only MySQL/MariaDB/PostgreSQL are supported for RDS, do not conclude Aurora is unsupported; Aurora has its own documentation, including Aurora Global Database under current eligibility rules.

### 8.1. Do Not Infer Support Solely from the Engine Name

For example, suppose an organization runs an older PostgreSQL major version with an incompatible extension. Even though **RDS for PostgreSQL** has the Blue/Green feature, a specific `PostgreSQL x → y` path may **not be supported**. You must verify:

- Exact source version/target version and the **`ValidUpgradeTarget`** list.
- Engine availability in the AWS Region.
- Instance/cluster topology, replicas, KMS/encryption, feature associations.
- Extension/parameter status and external data integrations.
- Which replication method is selected when the version changes.

If the support matrix does not fit, evaluate **AWS DMS**, logical export/import, snapshot restore/upgrade, or another migration strategy with its own cutover. Do not label it "native Blue/Green" if the workflow does not use the RDS/Aurora feature.

## 9. Replication Between Blue and Green: The Mechanism That Determines Risk

### 9.1. Replication Health and Replication Lag

**Replication lag** is the delay between a change committed on blue and the corresponding data appearing on green. If lag is high, switchover may have to wait longer or be rejected by guardrails.

~~~text
10:00:00  Blue receives order #900
10:00:02  Green has applied order #900
           → example replication lag is ~2 seconds

10:00:30  Blue writer bursts writes + long DDL
10:00:50  Green has only applied changes up to 10:00:32
           → high lag; do not switch merely because green is "Available"
~~~

These timestamps are illustrative; actual metrics depend on engine and replication type. Before cutover, monitor **replication status, lag trends, and write rate**, not just a single zero datapoint.

### 9.2. RDS PostgreSQL: Physical vs. Logical Replication

According to RDS PostgreSQL Blue/Green documentation, the replication method **depends on the source version and upgrade type**:

- **Physical replication:** typically used when **no major version upgrade** is involved, such as same major version or supported minor upgrades.
- **Logical replication:** used in eligible **major version upgrade** scenarios.

The critical point is that **logical replication does not automatically synchronize all PostgreSQL metadata and object changes**. For deployments using logical replication:

- **DDL** such as `CREATE TABLE`, `ALTER TABLE`, `CREATE SCHEMA`, and certain partition creation operations **are not automatically replicated from blue to green**.
- **DCL** such as `GRANT`, `REVOKE`, and `ALTER DEFAULT PRIVILEGES` is also restricted; RDS detects certain changes and **can put replication into `Replication degraded`, blocking switchover**.
- **Sequences** (`nextval`) do not emit events like row changes; supported sequence synchronization mechanisms run at switchover time, which can affect switchover duration.
- **Large objects** created/modified after B/G creation, **unlogged tables**, materialized views, and extensions have specific limitations.
- Tables receiving UPDATE/DELETE under logical replication require suitable identity, typically a **primary key** or an approved `REPLICA IDENTITY` configuration.
- Logical replication slots retain WAL; large backlogs and many databases can cause disk pressure if green falls behind.

**Do not jump from "DDL did not replicate" to "just run DDL on blue and manually reapply it on green."** With native B/G, unsupported DDL/DCL can degrade the deployment and require **deleting/recreating green**, not just patching a script.

### 9.3. PostgreSQL Upgrade Checklist by Replication Mode

| Item | Physical replication | Logical replication |
| --- | --- | --- |
| Major engine upgrade on green | Restricted, not supported by default | Used for certain source→target major paths |
| DDL/DCL on blue | Must follow current mechanism rules/restrictions | Avoid incompatible DDL/DCL; can block switchover |
| Sequences and identity | Follows physical copy/engine semantics | Review sequence sync at switchover |
| Extensions | Check version/restart behavior | Check extension support and DDL from background jobs |
| WAL/replication slot monitoring | Important depending on topology | Critical to prevent replication lag/storage pressure |
| Materialized views, large objects | Engine/feature dependent | Subject to specific update/replication limits |

Before a **major upgrade**, always read "PostgreSQL replication methods for blue/green deployments" and "Limitations and considerations," as AWS may add eligible versions or change behavior across releases.

### 9.4. MySQL/MariaDB and Aurora MySQL

MySQL/MariaDB environments typically involve **binary log/replication**, with requirements varying by version and topology:

- Verify binary logging, retention, replica lag, and GTID/binlog policies per AWS requirements.
- Avoid unsupported external replication/topologies.
- Check **event scheduler**, triggers, scheduled jobs, and background writes on green to prevent side effects or replication conflicts.
- Test character set/collation, SQL mode, reserved keywords, and JDBC behavior after major upgrades.
- Confirm parameter/option groups and engine extensions are copied/updated properly.

Do not assume every Aurora MySQL major upgrade shares the same path and duration as RDS MySQL.

### 9.5. Why Should You Not Write to Green?

Before switchover, green receives changes from blue. If an app or test tool simultaneously **writes its own data to green**, it can cause:

~~~text
Blue:  order_id=101 status=PAID
Green: order_id=101 status=TESTING  (written by QA)
Subsequent replication → conflict / data divergence
~~~

**Read-only** tests, metadata checks, and connection compatibility checks are low-risk choices. If you need **write-heavy** testing, it is better to spin up a **separate copy** outside the replication path, or use a testing approach approved by AWS and your DBA. Never use a syncing green environment to load test data and delete it afterward.

## 10. Blue/Green Limitations to Verify Before Creation

### 10.1. General Limitations

Key points highlighted in AWS documentation:

- **RDS** Blue/Green resources have constraints requiring the **same AWS account** as well as networking/topology constraints; cross-account B/G is not supported by default.
- **Multi-AZ DB instance** configurations may be supported in RDS B/G, whereas an **RDS Multi-AZ DB cluster** is a distinct resource type with its own support limitations — distinguish them accurately.
- **Cascading read replicas, cross-Region read replicas**, or other integrations may be incompatible with RDS B/G depending on engine/config.
- **Aurora Global Database** has dedicated support, but you must check the exact version/Region/topology; do not apply RDS DB instance rules verbatim to a global cluster.
- Managing the **master user password with Secrets Manager** in B/G has limitations per current documentation; plan secret rotation/storage accordingly.
- Attached **zero-ETL integrations with Amazon Redshift** or certain external replication features may require detaching before switchover and recreating afterward.
- **RDS Proxy** supports B/G integration under certain conditions, but the proxy must be configured at the right time and against the right source; do not assume every proxy/topology updates automatically.
- Do not arbitrarily put AWS CloudFormation in the middle of managing native B/G if the feature is unsupported; maintain an IaC strategy with drift checks and lifecycle management.

These limitations **can change** with AWS releases. The real verification criterion is the **support matrix for the exact resource** and preflight/guardrail results, not a memorized list.

### 10.2. RDS Proxy and JDBC Clients

RDS Proxy or smart drivers can improve reconnect/routing when the writer changes, but **they do not mean zero interruption**. RDS Proxy may close backend/proxy connections during switchover, requiring the application to reopen connections.

For Java:

- Do not hardcode the IP of an RDS endpoint.
- Configure appropriate DNS TTL/caching; never cache IPs indefinitely in the JVM, OS, connection pool, or external proxies.
- Use HikariCP/drivers that detect stale connections; set bounded connection timeouts and retry policies.
- Do not blindly retry **non-idempotent transactions** after a `connection reset` error when you do not know whether the database committed.
- Combine application-level retries with business idempotency keys/outbox for payment/order workflows.

### 10.3. Risks for Integrations Bound to Resource IDs

After switchover, the **DB instance/cluster identifier and endpoint name** may move to green, but each resource's **immutable resource ID** does not become the old resource's ID.

Components to check for resource ID dependencies:

| Integration | Risk After Switchover |
| --- | --- |
| **IAM database authentication** | `rds-db:connect` IAM policy ARN references the old DB resource ID |
| **CloudTrail/audit pipelines** | Resource ID filters point to the old DB |
| **Database Insights/Performance Insights** | Dashboards/APIs tied to the old resource identifier |
| **AWS Backup** | Backup selections/resources linked to the old resource |
| **DMS/CDC jobs** | Old checkpoints and replication streams do not automatically resume |
| **IAM roles associated with DB** | DB-associated roles may need reattachment on green |
| **Aurora Auto Scaling** | Some policies from blue are not copied to green |
| **Tags** | Changes made on green may be overwritten by blue's tags during switch |

**Keeping the same endpoint string does not mean every integration keeps the same identity**. Maintain a checklist of resource IDs and external integrations.

## 11. PITR and Backup History After Blue/Green Switchover

This is a very easy risk to overlook.

### 11.1. PITR History Does Not "Follow the DB Name"

According to RDS/Aurora Blue/Green documentation, **green retains its own resource ID and its earliest restorable time starts from when green was created**. Once green becomes production:

- By default, you cannot restore the **new production** to a point **before green was created**.
- **Blue's PITR history does not automatically become green's history**.
- Old blue retains its own history/automated backups until deleted or until retention expires per policy.
- To preserve recovery capability for earlier points in time, AWS recommends considering **retaining old blue for at least the required recovery window**, along with protecting snapshots per policy.

~~~mermaid
gantt
    title Illustrative Blue/Green Recovery History Boundaries
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section Blue
    History before Green     :active, a1, 2026-11-01, 14d
    Retain Blue for recovery :a2, 2026-11-15, 15d
    section Green
    Create Green / new PITR  :milestone, b1, 2026-11-15, 0d
    Switchover               :milestone, b2, 2026-11-20, 0d
    Green PITR window        :b3, 2026-11-15, 15d
~~~

*Dates are illustrative only to show two separate history timelines, not an actual maintenance schedule. The chart does not depict second-by-second WAL/backup continuity.*

### 11.2. Example RPO/RTO Check

A system requires **14-day** data recovery capability. Green is created on the 15th and switched on the 20th. If blue is deleted immediately on the 20th, attempting to restore production back to the 10th **cannot rely on green's PITR history**.

Plan:

1. Record **green creation date**, earliest restorable time, and actual backup retention.
2. Create/verify manual snapshots and retention per compliance requirements.
3. Retain old blue long enough to cover restore points prior to green creation, if needed and safe.
4. After cutover, update backup policies/resource IDs and run a restore test on the new production.
5. Schedule blue deletion once the history window and audit period have been satisfied.

**Retaining blue incurs costs** for compute/storage/backups; assign an owner/expiry date and monitor spend.

## 12. Switchover: Guardrails, Timeouts, DNS, and Post-Switch State

### 12.1. Switchover Guardrails

Before switching environments, RDS/Aurora performs **readiness checks** such as:

| Check | What It Verifies |
| --- | --- |
| **Green replication healthy** | Green is actively syncing with blue and not degraded |
| **Replication lag within threshold** | Catch-up and switchover can realistically complete within timeout |
| **No unauthorized writes on green** | Prevents data divergence |
| **No long-running writes/DDL on blue** | Avoids prolonging cutover or blocking the switch |
| **Valid external replication state** | No source/replica outside supported rules |
| **PostgreSQL logical replication constraints** | No unsupported DDL/DCL/large-object changes causing degradation |
| **DB/cluster instances available** | Environments meet service readiness state |
| **RDS Proxy readiness (if present)** | Proxy can route when writer/topology changes |

**Guardrails are a safety net, not a substitute for rehearsal**. They cannot inspect every Java application, stored procedure, business SLA, or JDBC code path in production.

### 12.2. Switchover Timeout

RDS and Aurora documentation describes a configurable timeout of **30–3,600 seconds**, defaulting to around **300 seconds**. If the timeout is exceeded, the service attempts to **roll back the incomplete switchover changes themselves**, leaving blue/green in their pre-switch state per service semantics.

**Distinguish two concepts:**

- **Rollback of a failing switchover operation:** part of AWS-managed behavior.
- **Rollback after switchover has completed and green has accepted production writes:** **not** a guaranteed zero-data-loss "undo" button. It requires a reverse database migration/cutover strategy accounting for new data.

### 12.3. DNS, Endpoints, and Open Connections

During switchover, AWS updates **identifiers/endpoints** so familiar production endpoint names point to the new environment, minimizing the need to change connection strings.

That **does not mean existing TCP connections migrate automatically**:

- Existing DB connections may be closed.
- RDS Proxy helps with routing, but connections active during the switch still need to re-establish.
- JVM DNS caching, OS resolvers, and high custom client/proxy TTLs can hold the old endpoint longer than the default (RDS docs advise against TTLs higher than RDS's DNS TTL, typically 5 seconds).
- Applications should retry **new connections** with exponential backoff + jitter; never retry non-idempotent transactions without knowing the commit outcome.

### 12.4. Verifying Cutover Completion

When AWS reports completed:

1. Confirm the **production endpoint** now points to the new green resource; record the new DB resource ID.
2. Verify the application is hitting the **new writer**, not the read-only old blue.
3. Run an approved canary read/write **on designated test data**, with cleanup.
4. Measure p95/p99 query latency, error rates, connection pools, deadlocks, replication lag, and business events.
5. Verify read replicas, RDS Proxy, IAM DB auth, Secrets Manager integrations, DMS/CDC, monitoring, and backup policies.
6. Record exact interruption duration and any warnings; do not treat AWS reporting "completed" as application sign-off.

### 12.5. Do Not Edit Tags Only on Green Expecting Them to Persist

During switchover, **tags on blue may overwrite tags on green** per AWS behavior. IAM/billing/backup/ownership tags must be reconciled to ensure **new production** carries the right tags after cutover.

## 13. End-to-End Runbook: Controlled Database Maintenance and Upgrades

A runbook must define **the operator, data verifier, application monitor, Go/No-Go criteria, write-pause timing, and incident communication channels**.

~~~mermaid
flowchart TD
    R["Upgrade request"] --> BASE["Capture baseline and define SLO"]
    BASE --> COMP["Check engine versions,\nreplication limits, extensions/app"]
    COMP --> BACK["Backup/restore rehearsal"]
    BACK --> GREEN{"Native Blue/Green supported?"}
    GREEN -->|"Yes"| CREATE["Create green / configure upgrade"]
    GREEN -->|"No"| ALT["Plan alternative:\nrestore, DMS, or rolling path"]
    CREATE --> TEST["Read-only / compatibility tests\nmeasure metrics + replication lag"]
    TEST --> GATE{"Go / No-Go"}
    GATE -->|"No"| FIX["Investigate, defer, recreate green if needed"]
    FIX --> TEST
    GATE -->|"Yes"| SWITCH["Switchover in approved window"]
    SWITCH --> POST["Validate new writer/app/PITR"]
    POST --> HOLD["Retain old blue per policy"]
    HOLD --> END["Audit, cleanup, postmortem"]
~~~

### 13.1. Phase A — Preflight: At Least 1–2 Release Cycles Before Cutover

The goal is not an exact rigid day count, but **enough lead time to validate everything before touching production**.

| Area | What to Record | Owner |
| --- | --- | --- |
| **Inventory** | Engine, version, Region/AZ, instance/cluster ARN, topology, Multi-AZ/readers | DBA/Cloud Engineer |
| **Upgrade path** | Source/target version, compatibility, extensions, release notes | DBA/App Lead |
| **Connections** | RDS endpoints, RDS Proxy, DNS resolver, JDBC URL, connection pools | App/SRE |
| **Data** | DB size, largest tables, write rate, transactions, replication lag baseline | DBA/Data Lead |
| **Backups** | Earliest/latest restore points, retention, manual snapshots, restore drill | DBA/SRE |
| **Security** | IAM roles, KMS, DB auth, Security Groups, subnet group, TLS certs | Security |
| **Dependencies** | CDC/DMS, zero-ETL, cron jobs, replicas, ETL, reporting engines | Data/Integration |
| **SLO** | Write outage budget, RTO/RPO, canary check, rollback criteria | Product/Operations |
| **Billing** | Green compute/storage, extra replicas, backups, metrics, old blue retention | FinOps |

Example sign-off sheet:

~~~text
Change ID:        DB-UPGRADE-2026-11-001 (illustrative)
Blue:             shop-db-prod / PostgreSQL 15.x
Green target:     new major version in valid upgrade targets
Maintenance:      00:00–01:00 in operational timezone
Expected outage:  target under 1 minute; maximum acceptable 5 minutes
Abort criteria:   replication degraded / lag not decreasing /
                  client test failure / guardrails fail
Owner:            DBA on-call + SRE + Application Lead
Backup:           snapshot/PITR + restore rehearsal PASSED
~~~

**Do not treat "under 1 minute" as an absolute guarantee**. That figure reflects an operational target; have a plan ready if the AWS switchover does not complete within the allowed window.

### 13.2. Phase B — Preparing the Staging/Green Environment

1. Verify **native Blue/Green support** for the exact engine/version/Region/topology.
2. Confirm backup/PITR before creating green, and take a recovery point if needed.
3. Create green with appropriate source configuration and monitor provisioning status.
4. Upgrade engine version and adjust parameter groups on green **via supported operations**.
5. Ensure replication is **healthy**, with no unsupported changes or conflicts.
6. Compare green against blue: instance class, storage, parameter groups, TLS, subnets, IAM roles, reader count, alarms.
7. Run controlled compatibility tests, avoiding writing test data into the synchronized green environment.
8. Save test logs, names/ARNs/resource IDs, metrics, and green creation timestamp for PITR planning.

**Do not modify the database schema directly on blue while using PostgreSQL logical replication B/G if the operation falls into an unsupported category.** A seemingly minor DDL change can force rebuilding green and delaying the release.

### 13.3. Phase C — Pre-Cutover Rehearsal

Test the following scenarios:

| Scenario | What to Observe |
| --- | --- |
| JDBC connection to target engine | Handshake, TLS, auth, driver compatibility |
| Critical queries | Correct results and latency within SLO |
| Active batch/cron jobs | No duplicate side effects running from green |
| Stored procedures/extensions | Load properly with no unintended behavior changes |
| Application reconnect | Reopens connections after restart/DNS switch; pool does not deadlock |
| DB/cluster replica behavior | Read replica lag/endpoint recovers cleanly |
| IAM DB auth/resource IDs | Policies grant required access on **green resource IDs** |
| Backup/PITR + restore | Restores a usable copy within acceptable time |
| DMS/CDC/zero-ETL | Post-cutover reconfiguration plan is ready |

**Performance testing on green must avoid write conflicts**. You can run read-only queries against masked production-like data per policy, or spin up a separate snapshot clone/test DB to run write-heavy benchmarks.

### 13.4. Phase D — Preparing Switchover Inside the Maintenance Window

Before an operation that can affect production:

- Notify users/engineering teams of the expected **write interruption**.
- Pause or drain background workers that write to the DB during cutover per the runbook.
- Stop long-running DDL/ETL/transactions if approved; wait for active work to finish.
- Verify **green replication is healthy**, lag is below threshold, and the trend is stable.
- Verify endpoints, RDS Proxy, DNS caching, connection pools, and dependent resources.
- Make the **Go/No-Go** decision based on **metrics, logs, and business SLOs**, not a gut feeling that "it looks fine."
- Update the communication channel and confirm who is authorized to press switch.

### 13.5. Phase E — Switchover

1. The authorized operator triggers **Switch over** in the RDS Console/API or CLI after approval.
2. AWS runs guardrails and transitions deployment state per workflow.
3. **Do not manually intervene** in endpoint names/renaming/promotion while switchover is in progress.
4. Watch RDS events, API/CloudWatch metrics, when the application sees errors, and how it reconnects.
5. If switchover fails/times out, stop new operations and investigate actual state; **do not retry blindly**.

### 13.6. Phase F — Post-Cutover Validation and Retaining Old Blue

When AWS reports switch completed:

- Verify **engine/version, resource ID, writer endpoint, reader endpoints**.
- Run an approved canary transaction; confirm data reads back from the **new writer**.
- Measure CPU, memory, query plans, DBLoad, network/IOPS, deadlocks, API p95/p99, and errors.
- Verify DMS/CDC, RDS Proxy, IAM database authentication, AWS Backup, alarms, tags, and secrets integrations.
- Record **actual switchover timestamp**, old/new resource IDs, and earliest restorable times.
- Retain old blue per RPO/PITR retention and data rollback plans; **do not delete immediately just to save money**.
- Only after the observation window and backup retention requirements are satisfied, delete the old environment via review, while avoiding leaving unused resources billed indefinitely.

## 14. Java Spring Boot Applications: Connection Checks and Safe Retries

### 14.1. Lifecycle of a JDBC Connection During a Writer Switch

~~~mermaid
sequenceDiagram
    participant API as Spring Boot
    participant POOL as HikariCP
    participant DNS as DNS/RDS Proxy
    participant DB as RDS writer (Blue → Green)
    API->>POOL: Borrow connection
    POOL->>DNS: Resolve endpoint / open socket
    DNS->>DB: Connect Blue
    DB-->>API: Transaction result
    Note over DB: Managed switchover
    DB--xPOOL: Connection closed/reset
    API->>POOL: New borrow / retry connection
    POOL->>DNS: Re-resolve endpoint
    DNS->>DB: Connect Green new writer
    DB-->>API: New session ready
~~~

Connections **already checked out from the pool** can fail during switchover; do not expect HikariCP to transparently "resume" an in-flight transaction.

### 14.2. Example Spring Boot / HikariCP Configuration (Illustrative)

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://shop-db-prod.example.rds.amazonaws.com:5432/shop
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 10000
      validation-timeout: 3000
      idle-timeout: 600000
      max-lifetime: 1800000
      keepalive-time: 120000
~~~

**This is not an "optimal configuration for every application."** The endpoint name is a placeholder, and values must be tuned for **DB `max_connections`, pod/task count, application concurrency, and network**. Never commit real passwords to YAML/Git; use Secrets Manager or an approved secret management mechanism. In the illustrative YAML, `${DB_USERNAME}` and `${DB_PASSWORD}` are Spring Boot placeholders reading credentials from the environment; production apps should manage secrets through an approved mechanism.

### 14.3. DNS Caching for Java

The JVM and OS have their own DNS caches. For RDS/Aurora endpoints, **do not configure infinite TTL**. Check:

- JVM security properties `networkaddress.cache.ttl` and `networkaddress.cache.negative.ttl` for your JDK version.
- Container/OS resolvers, CoreDNS in Kubernetes if used, corporate DNS, and sidecars/proxies.
- RDS Proxy or topology-aware driver endpoint routing.
- JDBC connection idle/maximum lifetime, health checks, and failover behavior.

Do not assume simply setting Java DNS cache TTL to 5 seconds migrates in-flight connections; the JDBC pool must open **new connections**. Avoid changing production JVM settings without testing.

### 14.4. Transaction Retries: Unknown Commit Semantics

A risky example:

~~~text
Application: INSERT payment then COMMIT
Network:     TCP reset before app receives response
App:         Does not know whether commit succeeded

If you immediately retry INSERT/charge without an idempotency key:
  → duplicate payment processing may occur.
~~~

Mitigation:

- Attach an **idempotency key** or unique business transaction ID to business transactions.
- Treat timeouts as **outcome unknown**; check state in the datastore or payment provider when needed.
- Separate retries **to open a new connection** from retries **re-executing business logic**.
- Persist an outbox record for external non-DB side effects when appropriate.
- Bound retries with backoff/jitter; avoid creating a retry storm against a freshly recovered DB.

### 14.5. JDBC Smoke Tests

PostgreSQL (read-only):

~~~sql
SELECT version();
SELECT current_database(), current_user, current_timestamp;
SHOW server_version;
SHOW default_transaction_read_only;
SELECT 1 AS connectivity_ok;
~~~

MySQL/Aurora MySQL (read-only):

~~~sql
SELECT VERSION();
SELECT DATABASE(), CURRENT_USER(), NOW();
SHOW VARIABLES LIKE 'read_only';
SELECT 1 AS connectivity_ok;
~~~

Read-only SQL checks confirm version/session state, **not** that the new writer allows a full business transaction. Write canaries should only run against **DBA-approved test tables/data** with cleanup and auditing.

## 15. Recovery and Rollback: Before or After Switchover?

### 15.1. Before Starting Switchover

If green hits a version or compatibility error, the simplest choice is usually **do not switch**:

1. Keep serving production from blue.
2. Investigate green and replication status.
3. If `Replication degraded` cannot be resolved per AWS guidance, delete/recreate green in a controlled manner.
4. Retest and reschedule cutover; there is no reason to impact production just to "keep the schedule."

### 15.2. Switchover Rejected by Guardrails or Timed Out

If guardrails block switchover, do not take "manual" shortcuts to force it through:

- Inspect `Replication degraded` state, lag, long transactions/DDL, and external replication restrictions.
- Check RDS events and the status of DB instances/clusters.
- Confirm the application is still using the proper blue production environment.
- If AWS rolls back the partially started switchover, verify the final state; never assume an API error immediately leaves everything normal.
- Only retry after identifying the root cause and obtaining approval from authorized owners.

### 15.3. After Switchover Has Completed

This is the harder scenario: **new green has become primary/writer and has accepted new data**.

~~~mermaid
flowchart TD
    PROBLEM["Issue detected after cutover"] --> CLASS{"Severity / scope?"}
    CLASS -->|"App/query issue but data intact"| APP["Rollback code/config\nor fix forward"]
    CLASS -->|"Engine/storage cannot continue"| DATA["DB recovery/migration plan"]
    DATA --> FLOW{"Can new data sync reliably back to old blue?"}
    FLOW -->|"No"| STOP["Do not flip endpoint directly\nAssess RPO & snapshot/PITR\nDesign reverse migration"]
    FLOW -->|"Yes, verified"| PLAN["Execute planned new cutover\nData consistency + downtime"]
    APP --> MON["Canary + metrics"]
    STOP --> MON
    PLAN --> MON
~~~

**Do not "point the endpoint back to old blue" right after cutover** if customers have already created new orders on green; old blue does not automatically receive those new writes. A hasty rollback can **lose committed transactions** or cause dual-write inconsistency.

Options a DBA must evaluate: fixing config/app, restoring via PITR/snapshot, verified data transfer, reverse CDC/DMS migration if feasible, or temporarily pausing writes while resolving. **There is no universal one-command rollback guaranteeing zero data loss once cutover completes**.

### 15.4. Rollback Criteria Must Be Defined Up Front

Example:

~~~text
Before Switch:
  replication lag not decreasing / health degraded → NO-GO
  SQL compatibility test fail → NO-GO
  missing IAM DB auth grants → NO-GO

During Switch:
  switchover timeout / AWS guardrails fail → STOP, VERIFY CURRENT STATE

After Switch:
  app p99 > SLO for 5 min → triage, fix forward / rollback app
  data integrity issues → freeze writes per playbook and investigate
  never revert to old blue without accounting for new writes
~~~

## 16. Observability Before, During, and After Cutover

### 16.1. RDS/Aurora Signals to Monitor

| Layer | Metrics / Signals | How to Use Them |
| --- | --- | --- |
| **Replication** | Replica lag / replication status per engine | Decide readiness and switchover gate |
| **CPU / Memory** | CPUUtilization, FreeableMemory | Detect higher load after version upgrade |
| **Connections** | DatabaseConnections, connection failures | Spot reconnect storms and pool exhaustion |
| **IOPS / latency** | ReadIOPS, WriteIOPS, ReadLatency, WriteLatency | Identify query plan shifts / I/O pressure |
| **Storage** | FreeStorageSpace or Aurora storage metrics | Monitor WAL/binlog, temp space, free space |
| **Performance** | Database Insights, top SQL/DB Load, locks, deadlocks | Find query regressions |
| **Availability** | RDS events, status/maintenance/pending-reboot | Verify lifecycle and post-switch health |
| **Backup/PITR** | Earliest/LatestRestorableTime, backup retention, snapshot status | Protect recovery window after cutover |
| **App** | HTTP error %, p95/p99, HikariCP active/pending connections | Measure real user experience |
| **Cost** | 2x DB instances, snapshots, backups, logs, replication | Budget for green and retaining old blue |

Not every metric appears identically on an **RDS instance**, **Aurora writer/reader**, or across engines; choose the right namespace/dimensions/units and measure before and after under comparable workloads.

### 16.2. Phased CloudWatch Alarms

Before switchover:

- Unhealthy replication or replication lag continuously exceeding the Go/No-Go threshold.
- Low free storage/memory; replica apply unable to keep up with the write rate.
- SQL errors or performance regressions compared to baseline.

During switchover:

- DB connection drops and API error spikes within acceptable bounds; alert if exceeding the outage budget.
- RDS events reporting switchover errors, timeouts, or invalid configuration.

After switchover:

- Elevated DBLoad/p95 query latency, connection pool pending queues lasting too long.
- Rising Java API error rates, stalled migration/CDC jobs.
- PITR/automated backups/alerts still bound to the old resource ID.

### 16.3. Properly Scoped Log Monitoring

Enable logs and retention per policy for:

- RDS/Aurora error logs, PostgreSQL logs, or MySQL slow query logs per engine.
- CloudWatch Logs integration and CloudTrail API calls.
- Java application logs with correlation IDs, JDBC exceptions, and circuit breaker metrics.
- Automation events/notifications for updates and cutover.

**Never log full SQL parameters, passwords, PII, or connection strings containing secrets**. Performance investigations must respect DBA/security data access controls.

## 17. Read-Only AWS CLI: Inspecting Existing Databases and Upgrade Paths

The commands below are **read-only**; they do not create, modify, reboot, switch, or delete databases. Names like `shop-db-prod`, `shop-aurora-prod`, account IDs, and Regions are **placeholders**; run them in an account/Region where you have read permissions and do not publish outputs containing sensitive endpoints or ARNs.

### 17.1. Inspect Caller Identity, DB Instances, and Pending Modifications

~~~bash
aws sts get-caller-identity

aws rds describe-db-instances \
  --region ap-southeast-1 \
  --query "DBInstances[].{Id:DBInstanceIdentifier,Engine:Engine,Version:EngineVersion,Status:DBInstanceStatus,MultiAZ:MultiAZ,Maintenance:PreferredMaintenanceWindow,AutoMinor:AutoMinorVersionUpgrade,Pending:PendingModifiedValues,ResourceId:DbiResourceId}" \
  --output json
~~~

In the output:

- `PendingModifiedValues` shows requested changes that have not yet been applied.
- `DBInstanceStatus` verifies current instance state, **not that application queries are healthy**.
- `DbiResourceId` is essential for tracking resource identity after a B/G switchover.
- If a DB instance belongs to an Aurora cluster, inspect **cluster information** as well, not just individual instances.

### 17.2. Inspect Aurora Clusters

~~~bash
aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --query "DBClusters[].{Id:DBClusterIdentifier,Engine:Engine,Version:EngineVersion,Status:Status,Endpoint:Endpoint,ReaderEndpoint:ReaderEndpoint,Maintenance:PreferredMaintenanceWindow,Members:DBClusterMembers,ResourceId:DbClusterResourceId}" \
  --output json
~~~

**Do not look at `Endpoint` and `ReaderEndpoint` and assume readers have zero lag**. In Aurora, replication lag/reader consistency still needs verification for your engine and workload.

### 17.3. List Pending Maintenance

~~~bash
aws rds describe-pending-maintenance-actions \
  --region ap-southeast-1 \
  --query "PendingMaintenanceActions[].{Resource:ResourceIdentifier,Actions:PendingMaintenanceActionDetails[].{Name:Action,AutoAfter:AutoAppliedAfterDate,Current:CurrentApplyDate,ForcedAfter:ForcedApplyDate,OptIn:OptInStatus}}" \
  --output json
~~~

Read `Action`, `CurrentApplyDate`, `AutoAppliedAfterDate`, and `ForcedApplyDate` if present. A forced apply date must be scheduled like any impactful change — do not assume every event waits for the team to click a button.

### 17.4. Check Engine Upgrade Targets

~~~bash
aws rds describe-db-engine-versions \
  --region ap-southeast-1 \
  --engine postgres \
  --engine-version 15.4 \
  --query "DBEngineVersions[].{Version:EngineVersion,Targets:ValidUpgradeTarget[].{Version:EngineVersion,Major:IsMajorVersionUpgrade}}" \
  --output json
~~~

`postgres`/`15.4` are illustrative engine and source version values. For Aurora PostgreSQL, change `--engine` to `aurora-postgresql` and use the actual source version; **do not assume version availability or upgrade paths match RDS**.

If a target does not appear, do not force it with `modify-db-instance`; check the release notes and supported intermediate upgrade steps.

### 17.5. Inspect Parameter Groups and Pending Reboots

~~~bash
aws rds describe-db-instances \
  --region ap-southeast-1 \
  --db-instance-identifier shop-db-prod \
  --query "DBInstances[0].DBParameterGroups" \
  --output json

aws rds describe-db-clusters \
  --region ap-southeast-1 \
  --db-cluster-identifier shop-aurora-prod \
  --query "DBClusters[0].DBClusterParameterGroup" \
  --output text
~~~

When checking for parameters requiring reboot, inspect parameter group apply type and instance/cluster status alongside engine docs. **Never use reboot as a harmless "refresh status" step** in production.

## 18. Read-Only AWS CLI: Observing Blue/Green Deployments and Events

### 18.1. List Deployments

~~~bash
aws rds describe-blue-green-deployments \
  --region ap-southeast-1 \
  --query "BlueGreenDeployments[].{Id:BlueGreenDeploymentIdentifier,Name:BlueGreenDeploymentName,Status:Status,Source:Source,Target:Target,Details:StatusDetails}" \
  --output json
~~~

Check the exact **`BlueGreenDeploymentIdentifier`** (API-returned ID), deployment status, `Source`/`Target`, and `StatusDetails`. Never assume a B/G deployment missing from one Region does not exist in another Region.

### 18.2. Inspect a Single Deployment by ID

~~~bash
aws rds describe-blue-green-deployments \
  --region ap-southeast-1 \
  --blue-green-deployment-identifier bgd-EXAMPLE123 \
  --output json
~~~

In real API responses, review resource mappings and switchover details if present. During switchover, monitor the status of **both the deployment and the underlying DB instances/clusters**, not just the initial response of the Switch API call.

### 18.3. View Relevant RDS Events

~~~bash
aws rds describe-events \
  --region ap-southeast-1 \
  --source-type db-instance \
  --duration 60 \
  --output json

aws rds describe-events \
  --region ap-southeast-1 \
  --source-type db-cluster \
  --duration 60 \
  --output json
~~~

`--duration 60` means **60 minutes** in the API, not 60 seconds. For Blue/Green, event categories and EventBridge notifications depend on resource type; monitor both source events and application telemetry.

### 18.4. Check Snapshot/Backup Settings

~~~bash
aws rds describe-db-snapshots \
  --region ap-southeast-1 \
  --db-instance-identifier shop-db-prod \
  --output json

aws rds describe-db-cluster-snapshots \
  --region ap-southeast-1 \
  --db-cluster-identifier shop-aurora-prod \
  --output json
~~~

These APIs list snapshots matching the filters provided. **Simply seeing a snapshot in `available` state does not prove you can restore within RTO**; you must run restore drills, verify IAM/KMS permissions, and validate the application.

### 18.5. Inspect RDS Proxy (If Used)

~~~bash
aws rds describe-db-proxies \
  --region ap-southeast-1 \
  --output json

aws rds describe-db-proxy-targets \
  --region ap-southeast-1 \
  --db-proxy-name shop-db-proxy \
  --output json
~~~

If using RDS Proxy, target listings after switchover may take time to reflect the change; monitor actual application traffic and database connections rather than relying on a single CLI snapshot.

## 19. Production-Modifying Commands: Learn the Syntax, Do Not Run Unapproved

**These operations can restart the database, halt writes, switch endpoints, or incur charges. They are runbook templates for review, not commands to execute during this lesson.**

### 19.1. In-Place RDS Instance Major Upgrade (Illustrative Example)

~~~bash
# DO NOT RUN without change approval, backups, and app compatibility testing.
# Replace TARGET_VERSION with a version verified in ValidUpgradeTarget.
aws rds modify-db-instance \
  --region ap-southeast-1 \
  --db-instance-identifier shop-db-prod \
  --engine-version TARGET_VERSION \
  --allow-major-version-upgrade \
  --no-apply-immediately
~~~

**`--no-apply-immediately` does not turn an upgrade into zero downtime**; it queues the pending modification to apply per RDS scheduling mechanisms. Plan a maintenance window, verify pending status, and validate after the upgrade completes.

### 19.2. Native Blue/Green Switchover (Illustrative Example)

~~~bash
# TEMPLATE ONLY — do not run outside an approved change window.
# Warning: drops/blocks connections and writes, and switches the production writer.
aws rds switchover-blue-green-deployment \
  --region ap-southeast-1 \
  --blue-green-deployment-identifier bgd-EXAMPLE123 \
  --switchover-timeout 600
~~~

`600` is a 10-minute **operation timeout** in this example, not a guarantee of a 10-minute downtime window. Before invoking this command, require DBA/SRE confirmation of **Go**, replication lag, app readiness, backups, and incident response channels.

### 19.3. Why Not Run "Promote Green"?

AWS distinguishes a **managed Blue/Green switchover** from a **manual promote** of green. **Manually promoting green** can break replication or leave the deployment in an invalid state, bypassing guardrails and endpoint orchestration. Always use **`switchover-blue-green-deployment`** or the Console **Switch over** button per procedure.

## 20. SQL Preflight and Version Comparison (Read-Only)

Run these SQL queries **only with authorized metadata read permissions on an approved database**. On production, never run full-table scans for a "quick check," as they can spike CPU/IO, cause lock waits, or expose customer data.

### 20.1. PostgreSQL / RDS PostgreSQL / Aurora PostgreSQL

~~~sql
-- Server version
SELECT version();
SHOW server_version;

-- Installed extensions and versions
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;

-- Long-running transactions (authorized metadata only)
SELECT pid, usename, application_name, state,
       clock_timestamp() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY transaction_age DESC
LIMIT 20;
~~~

Why check `pg_stat_activity`? **Long-running writes/DDL/transactions** can increase replication lag or block switchover. Before terminating any session, **confirm the owner/transaction**—never kill a production connection just because it sits at the top of the table.

### 20.2. MySQL / RDS MySQL / Aurora MySQL

~~~sql
SELECT VERSION();
SHOW VARIABLES LIKE 'version%';
SHOW VARIABLES LIKE 'read_only';
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

When the major version changes, verify SQL mode, collation, and driver behavior against application tests. Configuration queries show settings; **they do not replace data/performance validation**.

### 20.3. Comparing Data Between Blue and Green

Running a quick `SELECT COUNT(*)` across huge tables can be slow and add unnecessary load. For very large tables:

- Use **primary-key batching/sampling** with proper permissions.
- Check estimated row counts from catalog statistics where appropriate, recognizing they are estimates.
- Reconcile business records using known business IDs and time windows.
- While replication lag exists, do not compare the two systems at **two different points in time** and wrongly conclude there is data loss.
- If checksums are required, choose an appropriate tool/algorithm and bandwidth cap, and never run them concurrently against production and green right before cutover without approval.

## 21. Cost of Blue/Green: Two Parallel Environments

**Blue/Green reduces change risk, but it is not free.** While both exist simultaneously, green consumes its own resources.

| Item | Potential Cost Increase | Control Suggestion |
| --- | --- | --- |
| **Compute** | Green DB instances/clusters at equal or larger size | Document green retention time and owner |
| **Storage/IO** | New storage and replication writes; Aurora storage/IO billing varies by config | Monitor space, IOPS, buffer pressure |
| **Backups/snapshots** | Snapshots, retention, backup storage beyond free allowance | Track lifecycle/PITR window |
| **Read replicas** | Green copies of supported replica topology | Verify actual replica count |
| **Logs/insights** | Enhanced Monitoring, Database Insights, CloudWatch Logs | Set sensible retention and log verbosity |
| **Data transfer/replication** | Replication/transfer traffic per topology and billing rules | Check Region/engine/pricing |
| **Old blue post-cutover** | Continues billing while retained for PITR history protection | Set review/deletion date per policy |
| **Testing** | App staging workers, RDS Proxy, test Lambda/ECS, load generators | Clean up lab resources after completion |

Estimation model:

~~~text
Total change cost
  ≈ existing blue production cost
  + green cost (compute + storage + I/O)
  + incremental backups / monitoring / data transfer
  + cost of retaining old blue after switchover
  + engineering effort for testing and recovery if failures occur
~~~

**It is not always exactly 2× the bill across all configurations**, because Aurora pricing, DB instance classes, storage, backups, read replicas, and lifetimes vary. However, for production-sized staging, green compute/IO/storage is usually a significant line item requiring budget approval.

### 21.1. Optimizing Cost Without Compromising Safety

Best practices:

1. Create green close enough to your actual rehearsal/cutover schedule rather than leaving it running unnecessarily for months.
2. However, **never cut testing short** merely to save money.
3. Choose a right-sized green for accurate performance testing; avoid undersized instances that skew benchmarks.
4. Keep old blue long enough per the approved recovery window, then decommission it under change control.
5. Apply tags such as `Project`, `Environment`, and `ChangeId`, and track spend by actual resource IDs.

## 22. IAM, Security, and Change Authorization

### 22.1. Separating Read Access from Production-Modifying Permissions

| Group | Primary APIs/Actions | Who Should Hold It |
| --- | --- | --- |
| **Read-only inventory** | `rds:DescribeDBInstances`, `rds:DescribeDBClusters`, `rds:DescribeBlueGreenDeployments` | Authorized SRE/DBA/operators |
| **Maintenance decisions** | `rds:ApplyPendingMaintenanceAction`, Modify DB/cluster | DBA/Change approver |
| **Blue/Green create/modify** | `rds:CreateBlueGreenDeployment` and supporting resource permissions | DB platform operator |
| **Switchover** | `rds:SwitchoverBlueGreenDeployment` | Temporarily elevated change executor |
| **Delete resources** | `rds:DeleteBlueGreenDeployment`, `rds:DeleteDBInstance`/`rds:DeleteDBCluster` | Separately approved cleanup owner |
| **Backups/restore** | Snapshot/restore APIs, KMS | DBA/DR operator |
| **App DB credentials** | Database login/IAM DB auth bound to exact resource ID | Application service identity |

This is a permissions guideline; **exact API names and IAM actions must be verified against the AWS Service Authorization Reference** for your engine and current API. RDS Blue/Green also requires permissions for created/renamed resources and service-linked roles. Never grant broad `rds:*` or `AdministratorAccess` when only Describe is needed.

### 22.2. Preventing Out-of-Process Changes

- Enable MFA and CloudTrail auditing for RDS API calls.
- Enforce **separation of duties** between requester, approver, and switchover executor.
- Separate staging and production accounts/roles; never give testing scripts permission to alter production DBs.
- Keep KMS key policies, security groups, subnet groups, DB users/roles, and secrets aligned across resource identity switches.
- Attach change IDs and record source/target ARNs and resource IDs in operational records.
- Restrict access to green just like production; synchronized staging **contains real production data** and requires the same security/compliance controls.

### 22.3. Green Is Not a Public Data Sandbox

Green is typically a live synchronized copy of production data. Do not grant interns/developers open access to green just because it is labeled "staging." Testing code against real data can violate personal data regulations, leak sensitive parameters into logs, or disrupt replication.

## 23. Common Failure Modes and Investigation Guide

| Symptom | Common Cause | Recommended Action |
| --- | --- | --- |
| **Upgrade target not listed** | Engine/version/Region unsupported or intermediate step required | `describe-db-engine-versions`, release notes, support matrix |
| **Persistent `pending-reboot`** | Static parameter has not been applied via a restart | Check parameter apply type, schedule a reboot |
| **Maintenance exceeds window** | Window is only the start time; work ran longer than expected | Monitor RDS events and downtime budget, notify stakeholders |
| **Green creation failed** | Incompatible engine/version/feature/topology/permissions | Read error details, support matrix, IAM, and quotas |
| **Replication degraded (PG)** | Unsupported DDL/DCL, large objects, or logical replication changes | Do not switch; follow guidance to recreate green |
| **Continuously rising replication lag** | High write rate, WAL/binlog pressure, undersized green | Measure lag/CPU/IO, throttle non-essential writes, adjust capacity |
| **Switchover rejected** | Guardrails: lag, long transactions, active writes on green, external replication | Stop switchover, resolve unmet conditions |
| **Switchover timeout** | Slow replication catch-up, open connections/long DDL, outage | Verify state, switchover rollback status, contact AWS Support if needed |
| **App still connects to old writer** | JVM/OS DNS cache, hardcoded IP, stale pool, proxy mapping | Re-resolve endpoint, bounce pool/app per runbook |
| **JDBC read-only errors after switch** | Hitting old blue/read endpoint or stale app session state | Check resource IDs, writer endpoint, RDS Proxy, and sessions |
| **Slow p99 SQL after upgrade** | Changed planner/statistics/parameters/extensions | Run authorized EXPLAIN, ANALYZE where appropriate, compare baseline |
| **IAM DB auth failing** | `rds-db:connect` policy still references old resource ID | Update role/policy for new green resource ID |
| **DMS/CDC job stopped** | Source checkpoint/identity changed | Reconfigure/reinitialize replication per DMS documentation |
| **Backup policy misses new resource** | AWS Backup selection still references old ARN/resource ID | Update selection and verify snapshots/PITR |
| **Cannot PITR before green creation** | Green history does not cover earlier timestamps | Check retained blue backups, manual snapshots, and DR plan |
| **Old blue still incurs charges** | Instances/backups kept post-switch for recovery | Review retention and delete on schedule, not prematurely |
| **Green tags overwritten** | Blue/Green tag synchronization during switchover | Reconcile tags at source/post-cutover; verify IAM/billing |
| **Low downtime yet duplicate payments** | App retried non-idempotent unknown-commit transactions | Audit business logs, idempotency keys, and payment reconciliation |

### 23.1. Triage Order to Avoid Making Incidents Worse

1. Confirm exactly **whether blue or green is currently serving writes** and check deployment status.
2. Gather **RDS events, engine logs, application errors, and replication metrics**.
3. Classify the issue: **syntax/version**, **IAM/network**, **replication**, **data integrity**, **performance**, or **client reconnect**.
4. Consult the Runbook Go/No-Go criteria. Do not run ad-hoc schema edits/reboots/promotions while B/G is mid-operation.
5. If data loss risk exists, prioritize **protecting data and pausing writes** with approval rather than blindly restoring traffic over an arbitrary endpoint.
6. Log decisions, approvers, timestamps, endpoints, and resource IDs for post-incident review.

## 24. Case Study: PostgreSQL Major Upgrade for an Order System

### 24.1. Context

An e-commerce system:

~~~text
App:                   Java 21 / Spring Boot, ECS Fargate
DB:                    RDS PostgreSQL production, Multi-AZ DB instance
Workload:              300 reads/s, 80 writes/s (hypothetical)
Critical tables:       orders, payments, inventory_reservations
SLO:                   target write outage < 60 seconds
RPO:                   zero loss of confirmed orders acceptable
Target version:        new major version, verified in valid targets
Change window:         low-traffic hours
~~~

These figures frame the exercise; they do not guarantee Blue/Green will meet a 60-second target under real workloads.

### 24.2. Pre-Checks

The DBA/SRE team performs:

1. Reviews **`ValidUpgradeTarget`**, extension versions, and the RDS PostgreSQL Blue/Green support matrix.
2. Determines whether the major upgrade requires **logical replication** and enforces a policy **prohibiting DDL/DCL on blue** while B/G exists.
3. Verifies tables receiving UPDATE/DELETE have primary keys or suitable replica identity.
4. Audits `pg_cron` jobs, partition creation, large objects, sequences, and external replication integrations.
5. Practices restoring a snapshot and records the actual elapsed time.
6. Captures baseline query plans, API latency, and HikariCP pool metrics.

### 24.3. Creating Green and Rehearsing

- Create B/G via the RDS API/Console with a valid target version.
- Monitor replication lag, disk/WAL pressure, and any `Replication degraded` warnings.
- Test schema/version, JDBC connectivity, and top business queries **without writing to green**.
- Spin up an independent clone to run migration/write benchmarks as needed.
- Prepare IAM DB auth roles to accept the **green DB resource ID** and verify connection readiness.
- Check Aurora-specific requirements if the actual architecture is Aurora rather than an RDS instance.

### 24.4. Switchover and Post-Cutover Verification

~~~text
T-30 min   : review lag, long transactions, backups, app/DB health
T-10 min   : confirm approvals, safely drain long-running jobs
T-00 min   : authorized operator executes switchover
T+01 min   : verify AWS status, run canary read/write test
T+05 min   : compare API p95/p99, DB errors, connections, event logs
T+30 min   : verify business reconciliation and backups/PITR
T+24 hours : review performance/CDC/tags, confirm old blue retention plan
~~~

`T+01 min` is merely a target checkpoint; if the switch runs longer, **do not declare failure or success by the clock**—rely on service state and actual application behavior. After switching, new production is the source of truth; never flip back to old blue without accounting for new writes.

### 24.5. Architectural Lessons

RDS Blue/Green enables pre-cutover testing, managed cutovers, and lower risk. Yet the system still requires:

- Idempotent business writes.
- Proper JDBC reconnect handling and DNS caching.
- Replication-compatible schema migration patterns.
- Backups/DR protecting both historical and new data.
- Observability keyed by DB resource ID, not just endpoint strings.
- Approval workflows if halting or rolling back after cutover becomes necessary.

## 25. Practice Exercises and Review Questions

### Exercise 1 — Does a Maintenance Window Cap Downtime at 30 Minutes?

RDS has a preferred maintenance window of 01:00–01:30. An engine upgrade starts at 01:20 and finishes at 02:10. Explain why.

**Hint:** the window defines when eligible work **starts**, not a hard completion deadline. You need a separate outage budget and stakeholder communication plan.

### Exercise 2 — `ApplyImmediately` vs. Pending Maintenance

An engineer modifies a static DB parameter and selects "Apply during next maintenance window," yet days later the status still shows `pending-reboot`.

**Hint:** certain static parameter changes do not automatically trigger a restart during the maintenance window; check the parameter apply type and schedule an approved reboot/failover.

### Exercise 3 — Minor vs. Major Upgrade?

A team is upgrading PostgreSQL from 15.x to 15.y and from 15.x to 16.x. Which requires deeper compatibility analysis?

**Hint:** the 15→16 major upgrade carries higher risk, though minor upgrades still require testing drivers, extensions, performance, and downtime.

### Exercise 4 — How Do MySQL and PostgreSQL Differ in B/G Replication?

A team performs an RDS PostgreSQL major upgrade while a nightly cron job creates partition tables on blue.

**Hint:** PostgreSQL logical replication does not automatically replicate DDL/DCL from blue; creating partitions can put replication into `Replication degraded` and block switchover. Adjust migrations/cron schedules before creating B/G.

### Exercise 5 — Can Test Data Be Written to Green?

A QA engineer wants to run a script creating 100,000 test orders directly on the replicating green environment and delete them afterward.

**Hint:** inappropriate, as it risks replication conflicts or data divergence. Use an independent clone or a DBA-approved test strategy.

### Exercise 6 — Guardrail Alerting on Replica Lag

Before switching, lag rises from 2 seconds to 80 seconds due to 1,000 writes/s on blue. What should the DBA do?

**Hint:** **NO-GO** until the cause is understood and resolved; inspect apply throughput, WAL/binlog, green sizing, active transactions, and catch-up capacity. Never inflate the timeout to mask errors without evaluating SLOs.

### Exercise 7 — Does RDS Proxy Guarantee Zero Downtime?

An application uses RDS Proxy, yet several JDBC connections are reset during switchover.

**Hint:** expected behavior. Proxy/drivers assist with routing and reconnection but do not preserve in-flight transactions; applications still need safe retry logic.

### Exercise 8 — PITR After Cutover

Green is created on the 15th, switched on the 20th, and the team deletes blue on the 20th. On the 22nd, they need to restore to the 12th.

**Hint:** green's PITR history does not include points before green was created. Deleting blue too early breaks the recovery window; retain blue/history/snapshots per policy.

### Exercise 9 — Rollback After New Writes Have Arrived

After switching, customers place 500 new orders on green. The team wants to flip DNS back to old blue to investigate a query bug.

**Hint:** never switch back arbitrarily because old blue lacks those 500 orders. Evaluate fix-forward/application rollback first; if reverting the DB is unavoidable, reconcile/migrate new writes with a formal cutover/restore plan and defined RPO.

### Exercise 10 — IAM Database Authentication

The application hits the exact same endpoint, yet IAM DB auth logins fail after switchover.

**Hint:** inspect `rds-db:connect` policies referencing the old **DB resource ID**; update permissions for green's new resource ID rather than looking only at the DB identifier.

### Exercise 11 — RDS Instance vs. Aurora Cluster

An engineer checks only `describe-db-instances` before upgrading an Aurora DB cluster, skipping cluster parameter groups, reader topology, and writer endpoints.

**Hint:** incomplete inspection. Aurora requires reviewing cluster-level engine versions/maintenance/parameter groups and instance members, especially with readers or global topologies.

### Exercise 12 — Blue/Green Costing

Blue runs three DB instances. Green also runs three instances for two weeks, and old blue is retained for 14 days post-switch. What must be budgeted?

**Hint:** green and old blue compute/storage/I/O, read replicas, backups, logs/monitoring, data transfer, and engineering recovery effort—not just a "switchover fee."

### Exercise 13 — Why Is `SELECT version()` Insufficient?

Green runs the right major version and `SELECT 1` succeeds, yet production latency increases fivefold after switchover.

**Hint:** query plans, optimizer statistics, parameters, indexes, extensions, or pool behavior changed; run baselines, load tests, Database Insights, and p95/p99 checks on top SQL.

### Exercise 14 — Switchover Returns Timeout

The RDS API returns a timeout error. An engineer wants to keep clicking Switch until it succeeds.

**Hint:** first inspect deployment status, RDS events, writer identity, replication guardrails, and the rollback status of the timed-out operation. Never retry blindly while state is unclear.

## 26. Production Sign-Off Checklist

- [ ] Exact engine, source/target versions, Region, topology, and support matrix verified.
- [ ] Release notes, extensions, stored procedures, JDBC/ORM compatibility, and SQL modes tested.
- [ ] Preferred maintenance window and pending maintenance/parameter reboots documented.
- [ ] Backups/PITR/manual snapshots, retention, and restore rehearsal meet RPO/RTO.
- [ ] CloudWatch/Database Insights baselines, business p95/p99, and downstream capacity captured.
- [ ] Blue/Green supports exact configuration; no unsupported external replication/zero-ETL/feature constraints.
- [ ] PostgreSQL logical replication checked for DDL/DCL, sequences, large objects, partitions, WAL/slots.
- [ ] Green replication healthy, lag stable, no active test writes or replication conflicts.
- [ ] Green has adequate compute/storage/reader topology and is not undersized for accurate benchmarks.
- [ ] App JDBC/connection pools, DNS caching, RDS Proxy, and idempotent retries tested.
- [ ] Go/No-Go criteria, owners, approved window, max outage budget, and communication channels locked.
- [ ] Post-cutover checks prepared for new writer, canary read/write, business reconciliation, and performance regressions.
- [ ] Update plan ready for IAM DB auth, resource IDs, CloudTrail, DMS/CDC, AWS Backup, tags, and alarms.
- [ ] Confirmed understanding that old blue **receives no new writes after cutover**; DB rollback requires a separate data plan.
- [ ] Green PITR boundary and old blue retention window factored into deletion schedule.
- [ ] Budget approved for green, old blue retention, snapshots, monitoring, and engineering time.
- [ ] Abort/defer runbook, manual intervention policy, and postmortem process established if cutover fails.

## 27. Key Takeaways

**Database maintenance and upgrades are stateful changes, not merely Console clicks.**

1. **Maintenance windows** define when work prefers to start, not a 30-minute cap on outages. Minor/major upgrades, pending-reboot, and `ApplyImmediately` all have distinct semantics.
2. **RDS Multi-AZ and Aurora readers** improve fault tolerance, but **do not guarantee zero-downtime upgrades**; applications must handle reconnects.
3. **Blue/Green Deployments** provision a synchronized green environment to validate engine/parameter changes first. AWS **switchover guardrails** make switching to green safer, though a brief interruption to writes/connections still occurs.
4. **PostgreSQL major upgrades** may rely on logical replication with critical limits: DDL/DCL, sequences, large objects, extensions, and replication slots require strict validation.
5. **Keeping the DNS endpoint name does not preserve the resource ID**. IAM DB auth, metrics, backups/CDC/proxies/tags may require updates after cutover.
6. **Green's PITR history does not inherit points before green was created**. Retain old blue/snapshots per your recovery window and verify restores.
7. **A completed switchover has no one-button database rollback** once new production accepts writes. New data handling, idempotency, compensation, and DR plans govern recoverability.

A solid workflow always combines **preflight checks, compatibility testing, backup drills, replication monitoring, Go/No-Go gates, controlled cutover, and post-cutover verification**. The goal is accurate data and stable application availability—not merely bumping an engine version number.

### Official AWS Documentation

- [Maintaining a DB instance — Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.Maintenance.html) — maintenance windows, impacts, and pending actions.
- [Upgrading a DB instance engine version](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_UpgradeDBInstance.Upgrading.html) — minor/major upgrades, target versions, and `ApplyImmediately`.
- [Amazon Aurora updates](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Updates.html) — cluster maintenance and engine updates.
- [RDS Blue/Green Deployments overview](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-overview.html) — blue and green architecture.
- [RDS Blue/Green limitations and considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-considerations.html) — limitations, resource IDs, and PITR.
- [RDS Blue/Green best practices](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-best-practices.html) — staging and switchover preparation.
- [RDS Blue/Green switching](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-switching.html) — guardrails, endpoint cutover, and duration.
- [PostgreSQL replication methods for RDS B/G](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-replication-type.html) — physical/logical replication by version.
- [Aurora Blue/Green overview](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments-overview.html) — supported engines and Aurora Global Database.
- [Aurora Blue/Green limitations](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments-considerations.html) — cluster-specific constraints and PITR.
- [Aurora Blue/Green switching](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/blue-green-deployments-switching.html) — switchover, RDS Proxy, and validation.
- [Amazon RDS AWS CLI reference](https://docs.aws.amazon.com/cli/latest/reference/rds/index.html) — describe, modify, and switchover commands.
- [Amazon RDS Monitoring](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Monitoring.html) — CloudWatch, events, and logs.
- [Amazon RDS pricing](https://aws.amazon.com/rds/pricing/) and [Amazon Aurora pricing](https://aws.amazon.com/rds/aurora/pricing/) — cost control when running parallel environments.

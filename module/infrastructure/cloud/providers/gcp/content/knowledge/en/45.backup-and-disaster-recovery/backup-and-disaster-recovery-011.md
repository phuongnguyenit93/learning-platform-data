# Backup Verification and Periodic Recovery Drills

A system with a daily backup schedule is not automatically recoverable when an incident strikes. Backups may miss data, lack transactional consistency, lose decryption permissions, reside in the same failure domain as primary systems, or fail to restore within the timeframe required by the business. Even when data restores cleanly, the application can still remain down due to missing secrets, network configs, schemas, artifacts, or IAM permissions.

**Backup verification** is the process of confirming a copy is readable, complete, consistent, and usable for recovery. **Periodic recovery drills** are controlled exercises executing the recovery workflow, measuring duration, data loss, and application behavior upon returning to service. Outputs must be auditable evidence, not merely a SUCCESS status on a backup creation job.

This lesson belongs to the **Backup and Disaster Recovery** chapter of the **CLOUD_PROVIDERS_GCP** module. The module guides learners through Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, protect resources, automate releases, and track reliability and cost. Here, we apply those skills to design tests and recovery drills for Java/Spring applications and Google Cloud data services.

## Learning objectives

After this lesson, you will be able to:

- Distinguish backups, snapshots, replication, high availability, and disaster recovery.
- Use RPO and RTO to determine which verification tests must be executed.
- Design tests across levels: existence, integrity, data restoration, application recovery, and business recovery.
- Establish post-restore verification criteria: counts, checksums, transactions, schemas, functionality, and permissions.
- Choose appropriate verification methods for Cloud SQL, Compute Engine, Cloud Storage, Firestore, Spanner, BigQuery, and GKE.
- Organize recovery drills in isolated environments without impacting production.
- Automate recurring schedules, store evidence, track costs, and clean up post-drill resources.
- Write runbooks, measure actual RTO/RPO, and turn drill outcomes into action items.

## 1. Backup success does not equal restore success

Distinguish several common mechanisms:

| Mechanism | Primary goal | What is not automatically guaranteed |
|---|---|---|
| Backup | Store a data copy to recover to a point in time | Ability to restore within required time |
| Snapshot | Record resource state at a point in time per service capability | Consistency across all apps/dependencies |
| Replication | Maintain a continuous or near-continuous replica | Recovery after accidental deletes or bad writes |
| High availability (HA) | Reduce downtime when a component fails | Recovering records deleted by logical bugs |
| Disaster recovery (DR) | Restore service/business after severe incidents | Success without runbooks and drills |
| Point-in-time recovery (PITR) | Return to a timestamp within a supported recovery window | Rescuing data beyond retention or without matching logs |

For instance, database replicas typically receive erroneous DELETE statements as well. Failing over to a replica survives host faults, yet fails to recover deleted rows. Backups, PITR, or another suitable data protection mechanism are required.

A disk snapshot can succeed while an application writes across multiple files and transactions simultaneously. Unless the service guarantees application-consistent snapshots, coordinate the application or database to capture a recoverable state; never assume every snapshot is business-consistent by default.

### Three questions before trusting a backup

1. **What is protected?** Which data, configs, schema versions, and dependencies?
2. **How can it be restored?** Where to restore, what permissions/keys/secrets are needed, duration, and manual steps?
3. **How is accurate recovery proved?** What evidence proves data, functionality, integrity, timing, and monitoring?

## 2. RTO, RPO, recovery scope, and acceptance criteria

### Recovery Point Objective (RPO)

**RPO** is the maximum data loss permitted during an incident, typically measured as the interval from the last recoverable consistent data point. A 15-minute RPO does not mean taking snapshots every 15 minutes guarantees meeting RPO: it also depends on backup completion time, transaction logs, replication errors, and detection latency.

### Recovery Time Objective (RTO)

**RTO** is the maximum allowed duration to restore the service/business to an agreed state. RTO covers more than backup load time:

~~~text
Recovery elapsed time
  = detect and declare
  + authorize the recovery path
  + provision target infrastructure
  + restore data and configuration
  + validate consistency and application behavior
  + switch traffic and confirm service
~~~

For example, if Cloud SQL restore takes 12 minutes, yet networking takes 25 minutes, updating secrets takes 15 minutes, and smoke tests take 10 minutes, you cannot report a 12-minute RTO.

### Illustrative target table

| Workload | Target RPO | Target RTO | Drill required to prove |
|---|---:|---:|---|
| Orders DB | 15 minutes | 60 minutes | Restore DB + API order read/create |
| End-of-day reports | 24 hours | 8 hours | Restore input dataset and rerun job |
| App configuration | Approved release | 30 minutes | Rebuild service from IaC and artifacts |
| Object uploads | 1 hour | 4 hours | Recover object version and verify checksum |

These are examples only, not Google Cloud SLAs or defaults. For real systems, RPO/RTO must be accepted by business owners based on financial, data, and customer impact.

### Measurement boundaries

Before drilling, agree on:

- **T0:** incident start time, simulated or confirmed.
- **T_detect:** when alerts/on-call detect and log the incident.
- **T_recovery_start:** when recovery execution is authorized.
- **T_data_ready:** data restored and verified consistent.
- **T_service_ready:** critical business flows operate via the right endpoint.
- **T_close:** when the drill is closed, resources cleaned up, and reports completed.

RTO should typically measure until `T_service_ready` per organizational SLO/DR definitions, not merely when a restore command returns OK. Record every timestamp in UTC and note clearly when incident times are simulated.

## 3. Five levels of backup verification

A strong strategy builds confidence incrementally across verification levels:

| Level | Check | Evidence | What remains unproven |
|---|---|---|---|
| 1. Inventory | Backup exists and sits within retention | Backup ID, timestamp, size/status | Restore actually works |
| 2. Integrity | Data is readable; checksums/metadata valid | Hashes, manifests, file/object checks | App can read the data |
| 3. Restore | Restore into an isolated environment | Restore job and target ID | Business system operates |
| 4. Application | Schemas, APIs, transactions, permissions, and connectivity valid | SQL checks, smoke tests, logs | RTO/RPO in a full disaster scenario |
| 5. DR exercise | Rebuild infra, traffic, and operations timed end-to-end | Timeline, RTO/RPO, runbook, report | Any failure scenarios not yet drilled |

Never substitute backup scheduler notifications for level 3–5 tests. A backup labeled SUCCESS can still omit a critical table or lack decryption keys in the target environment.

### Pre-defined PASS/FAIL criteria

- Backup meets age and retention expectations.
- Restore finishes within the approved time window.
- Schemas, indexes, constraints, and key data metrics are valid.
- Zero failed transactions or business invariant violations beyond approved bounds.
- Restored application starts, connects, and completes test transactions.
- IAM, networking, Secret Manager, KMS, and DNS recover per plan.
- Measured RPO and RTO do not exceed targets.
- Evidence, logs, costs, and cleanup are fully recorded.

**A restore that recovers data yet fails business criteria must be marked FAIL or PARTIAL**, never reported complete just because the job succeeded.

## 4. Inventorying everything that must be recovered

A Spring Boot system may combine Cloud Run APIs, Cloud SQL PostgreSQL, Cloud Storage buckets, Pub/Sub, Secret Manager, container image artifacts, and IAM/VPC configs. Backing up only the database does not guarantee the system can recover.

~~~mermaid
flowchart TD
    A["Working orders flow"]
    A --> B["Orders API / worker"]
    A --> C["Cloud SQL and transaction data"]
    A --> D["Objects / documents in Cloud Storage"]
    B --> E["Artifact Registry image + deployment config"]
    B --> F["Service identity + IAM"]
    B --> G["Secret Manager and key access"]
    B --> H["VPC, DNS, ingress/egress"]
    B --> I["Pub/Sub topics, subscriptions, retry/DLQ"]
    C --> J["Backup/PITR and database restore"]
    D --> K["Object versions/soft delete/backup"]
~~~

### Dependency and owner matrix

| Component | Recovery source | Owner | Verification method |
|---|---|---|---|
| PostgreSQL | Cloud SQL backup + PITR per config | Database/SRE team | Queries, constraints, counts, transactions |
| Object Storage | Versioning/soft delete, suitable backup/export | Data owner | Object count, generation, checksum/content |
| Container image | Artifact Registry and provenance | Release team | Digest, image pull, startup |
| Service configuration | IaC, Git, or managed config exports | Platform team | Terraform plan/manifest review, smoke tests |
| Secrets | Secret Manager and dedicated recovery workflow | Security/app team | Runtime identity reads exact secret version |
| KMS keys | Key policies, IAM, lifecycle per DR plan | Security | Ability to decrypt backup within authorized scope |
| IAM/networking | Infrastructure as Code and policies | Platform/Security | Access tests, private connectivity, deny tests |
| Queues/subscriptions | IaC + event replay/runbook | Application team | Message routing, idempotency, DLQ |
| Monitoring | IaC, dashboard/alert definitions | SRE | Synthetic tests and alert routing |

Note: some components lack "backups" in the snapshot sense. For example, Pub/Sub messages are not retained indefinitely merely because a topic exists; retention, snapshots/seeks where supported, and replay logic must be explicitly designed. Infrastructure as Code likewise recreates configs only if sources, permissions, and execution tooling remain available during an incident.

## 5. Choosing drill patterns and safety levels

Backup/DR drills must have clear boundaries to avoid causing outages or corrupting live data.

| Drill type | Purpose | Production impact | Risk level |
|---|---|---|---|
| Tabletop | Walk through runbooks, simulate decisions and escalation | Zero production changes | Low |
| Backup inventory | Check catalog, age, permissions, retention | Mostly read-only | Low |
| Isolated restore | Restore backup to a separate test target | No production traffic shifted | Low to medium |
| Application validation | Boot app against restored data, blocking side effects | Within test environment | Medium |
| Controlled failover | Shift serving path or inject planned faults | Can impact prod if scoped poorly | High |
| Full DR drill | Recover business flows in standby site/region | Impact depends on design and test window | High |

**Start with isolated restores** to verify data readability and runbooks. Progress to controlled failover / full DR only with approval, an incident commander, rollback paths, staffing, and safeguards blocking unintended side effects.

### Isolated environment principles

1. Use dedicated projects, networks, and database targets for recovery tests where supported.
2. Never overwrite production databases or alter production traffic during routine tests.
3. Prevent test apps from sending real emails, charging payments, or firing partner webhooks/messages.
4. Block or replace external side effects with fakes/stubs, sandbox endpoints, or egress policies.
5. Use least-privilege, time-bound service accounts.
6. Set budget caps, expiration tags, run IDs, and cleanup owners.
7. Classify restored production data: test environments still require proper security, logging, and retention.

Putting "test" in a project name is not sufficient security. Always confirm exact project IDs and IAM/network boundaries before executing.

## 6. Cloud SQL: verifying backups, PITR, and transactions

Cloud SQL typically holds critical relational data: orders, customers, and payment states. For databases, the goal goes beyond recreating data files—you need transactionally consistent state, matching schemas, and working application connectivity.

### Recovery sources

- **Automated backups:** Cloud SQL-managed backups per configuration.
- **On-demand backups:** manual backups created on demand, e.g., before major changes.
- **Point-in-time recovery:** uses backups and logs within the engine/service's configured recovery window.
- **HA/failover:** handles instance/zone faults per configuration, but does not replace backups after bad data edits.

Verify backups, PITR, retention, storage location, and restore prerequisites per engine (PostgreSQL/MySQL/SQL Server), edition, version, and actual config. Never assume a new instance has PITR or target retention enabled merely because it runs on Cloud SQL.

### Step 1: read-only inventory

Example inspection commands (no restore triggered):

~~~bash
export PROJECT_ID="example-recovery-project"
export INSTANCE_ID="orders-db"

gcloud sql backups list \
  --instance="$INSTANCE_ID" \
  --project="$PROJECT_ID"

gcloud sql instances describe "$INSTANCE_ID" \
  --project="$PROJECT_ID" \
  --format="yaml(name,region,databaseVersion,settings.backupConfiguration)"
~~~

Record backup IDs, start/end timestamps, status, source instance, and retention policy. A `list` output alone is not enough to conclude a backup is restorable or meets RPO.

### Step 2: restore to an isolated target

Depending on engine and supported workflows, use Console/API/gcloud per Cloud SQL guidance to restore **a specific backup or PITR timestamp** into a drill target. Never run restore commands directly on production during exercises. Before running, document:

- Source project, instance, backup ID, and restore timestamp.
- Approved target project/instance, machine sizing, networking, and encryption/key access.
- Operator and automation permissions to execute the restore.
- Test window, budget, and cleanup policy.
- Expected application state at the chosen point.

Certain restore methods carry source/target, engine, and project restrictions. Use the workflow for your service version; if direct restore to a particular target is unsupported, adapt the plan and **never work around limits by operating on the production instance**.

### Step 3: verify schema and data

After the target recovers, run read-only queries using an appropriate test account:

~~~sql
-- Schema here is an example for an Orders application.
SELECT COUNT(*) AS total_orders
FROM orders;

SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;

SELECT MAX(created_at) AS newest_order_time
FROM orders;

SELECT COUNT(*) AS invalid_amounts
FROM orders
WHERE total_amount < 0;
~~~

Compare against the **expected manifest** at backup time, not necessarily the live production DB that keeps changing. For large datasets, verify by partition, targeted samples, counts, totals, foreign keys, and checksums over canonicalized data. When hashing multiple rows, fix row ordering, encoding, and canonical representation; never compare raw physical database file hashes and claim data differs.

### Step 4: verify the application

- Deploy a Spring Boot version compatible with the schema at the restore point.
- Run smoke tests reading orders, summing totals, querying by key, and paginating.
- If testing writes, run inside the isolated target with separate snapshots/cleanup.
- Verify JDBC URLs, SSL/TLS, IAM/database users, Secret Manager, and networking.
- Measure elapsed time from restore request until the API processes business flows properly.

Common failure: database restore finishes yet the app crashes because the schema belongs to an older/newer release than the container image, or DB secrets were rotated. Drills must test **compatibility across data, code, and configuration**.

### Example PITR evaluation

Suppose a bad operation occurred at 10:20 UTC, detected at 10:35. If PITR supports 10:19:59 with valid logs, the target can restore right before the error. Verify data restored to the exact point and reconcile valid post-10:20 transactions (if business rules permit).

**Never cite restoring to 10:19:59 as proof of achieving RPO 0.** Valid transactions committed after that timestamp may be missing in the restored copy; teams must measure/estimate and reconcile per business requirements.

## 7. Compute Engine: disk snapshots and instance recovery

For VMs, verification must cover boot disks, data disks, guest OS configs, and instance replacement workflows. Disk snapshots are usually suitable data recovery sources, yet do not automatically provide IAM, firewalls, external dependencies, or application consistency.

### Verification workflow

1. Inventory snapshots: source disk, timestamp, zone/region, retention, encryption key, and backup chain per service model.
2. Confirm snapshot capture suits the workload. For active databases or filesystems, use quiesce/flush/application-consistency mechanisms where supported and needed.
3. Create a **new disk** from the snapshot in an approved test project/scope.
4. Attach the disk to an isolated test VM, or boot a separate VM from a boot disk snapshot.
5. Verify filesystem integrity, directory layout, service configs, and business data.
6. Measure disk/VM provisioning, process startup, and health check timings.
7. Clean up test disks/VMs without deleting source snapshots within retention policy.

### Commonly overlooked details

- A single disk snapshot does not guarantee atomic consistency across multiple disks if the app spans disks.
- A restored VM may lack original network tags, service accounts, firewall rules, or IP addresses.
- Startup scripts may fetch artifacts or package repositories that are no longer reachable.
- Licensing, OS patches, architecture, and image versions can affect rebooting.
- Externally loaded secrets and certificates must exist in the DR environment.

For managed instance groups, drills should also test spinning up new instances from managed templates/images and passing load balancer health checks. Data snapshots and compute recreation are two halves of one runbook—they do not replace each other.

## 8. Cloud Storage: checksums, versioning, soft delete, and retention

Object Storage typically holds documents, images, exports, or batch inputs. Multiple mechanisms may be combined:

- **Object Versioning** when enabled: retains object generations per configuration and lifecycle.
- **Soft delete** per policy: recovers deleted objects within a configured window.
- **Retention policy / Bucket Lock** when required: prevents early deletion per configured constraints.
- **Backup/export to another location:** avoids shared faults or supports supplementary recovery strategies.
- **Replication or dual/multi-region storage:** serves availability/durability per config, but does not replace versioned recovery.

Verify which mechanisms are enabled, retention windows, and how they interact. Retention locks impose constraints that cannot be easily removed; never enable a lock just to try a lab exercise.

### Checking objects post-restore

A manifest can store:

| Attribute | Meaning |
|---|---|
| Bucket and object name | Identifies the object |
| Generation | Identifies the exact object data version |
| Size | Checks for truncation or missing bytes |
| CRC32C/MD5 metadata when present | Validates content via supported checksums |
| Content-Type and metadata | Verifies how applications interpret the object |
| Created/updated timestamp | Cross-checks retention and recovery source |
| Run ID / business key | Links to business verification tests |

Cloud Storage uses CRC32C for integrity validation; MD5 is not available for every object/scenario. Do not rely on ETag as a guaranteed MD5. When downloading to compare, use supported checksums or compute content hashes under an agreed convention.

Example read-only commands to inspect a test bucket:

~~~bash
gcloud storage ls gs://example-backup-verify/
gcloud storage objects describe \
  gs://example-backup-verify/fixtures/order-001.json
~~~

To test recovery, restore a deleted generation or object **within a test area using enabled features**, download and read it, and compare content and metadata. Never overwrite a production object just for verification.

### Retention and cost impact

Keeping many versions aids accidental-delete recovery but increases storage volume and cost. Lifecycle rules can prune older versions, yet overly short lifecycles can discard needed recovery points. Design retention around data classification, RPO, legal mandates, and growth rate.

## 9. Firestore, Spanner, BigQuery, and Backup for GKE

Never apply one backup pattern to every data system. Capabilities and recovery windows vary by service, version, and configuration.

### Firestore

Firestore supports backup/restore or export/import mechanisms and PITR per database capabilities/config. A drill should:

1. Identify databases, collections/documents needing protection, backup/export locations, and retention policies.
2. Pick a valid backup source or PITR timestamp per service support.
3. Restore/import into a separate test database or approved test area.
4. Check document counts, document IDs, subcollections, business fields, and required indexes/queries.
5. Verify security rules/IAM, index configs, and app connectivity post-recovery.

Do not confuse deleting a parent document with deleting all subcollections. Exporting/importing data and recreating security/index configs may be separate steps; verify anything omitted by exports.

### Spanner

Cloud Spanner provides backup and restore via supported service options. For transactional data:

- Record backup ID, database, timestamp, retention, and key/region.
- Restore into an authorized test database.
- Verify schemas, row counts, indexes, and business data constraints.
- Execute test transactions using an appropriate test account.
- Measure time until the database is usable by applications.

Even if multi-region topology was chosen for availability, drills must measure recovery time after logical corruption or accidental deletion, not merely infrastructure fault tolerance.

### BigQuery

BigQuery offers table snapshots, time travel, and table copies within supported limits/features. These serve different recovery cases; time travel has a bounded window and should not be treated as long-term backup for every dataset.

A BigQuery drill should:

- Verify protected datasets/tables and matching retention.
- Restore an overwritten table into a new test table.
- Compare row counts, schemas, partitions, key metrics, and query outputs.
- Verify policy tags, dataset/table access controls, authorized views, and required data lineage.
- Monitor query/restore costs and avoid large unplanned full scans.

### Backup for GKE

Backup for GKE protects Kubernetes configs and PersistentVolume data per backup/restore plans. However, never assume external databases, secrets, artifacts, and auxiliary services reside inside GKE backups.

During drills:

1. Confirm namespaces/resources/PersistentVolumes selected in the backup plan.
2. Target a restore plan into an approved test cluster/namespace.
3. Verify Deployments, Services, ConfigMaps, PVCs/PVs, and Pod states.
4. Verify image pull access, KSA/Workload Identity, Secret Manager, and networking.
5. Connect workloads to separately restored data stores.
6. Run smoke tests and confirm zero events or writes reach production.

**Never declare Kubernetes resource restoration equal to system recovery** while data in Cloud SQL, Spanner, or Cloud Storage remains unready.

## 10. Cloud Run and Java/Spring apps: recovering availability, not just data

Cloud Run services are typically stateless. Rebuilding services relies on container images in Artifact Registry and infrastructure configs via Infrastructure as Code. Still ensure all dependencies survive:

- Trusted image digests or build artifacts remain accessible.
- Service accounts, IAM invokers, Secret Manager, and KMS keys remain valid.
- Environment variables, min/max instances, CPU/memory, and concurrency match.
- VPC egress, DB connectivity, ingress, and DNS/custom domains are configured.
- Deployment order aligns with database migrations and schema versions.
- Alerts, logs, and traces operate to observe restoration.

### Post-recovery Spring Boot smoke test

| Check | Evidence | Notes |
|---|---|---|
| Readiness | `/actuator/health/readiness` returns expected status | Do not expose sensitive info publicly |
| Database | Read-only query plus one isolated test transaction | Never create real transactions |
| Storage | Read restored object by fixture ID | Check exact generation/content |
| Pub/Sub | Send sandbox message with correlation ID | Never publish to production topics |
| Authentication | Valid test account accepted | Also verify unauthorized requests are rejected |
| Monitoring | Metrics/logs/traces capture test events | Zero credentials/PII logged |

Spring Boot health endpoints must be enabled/configured properly; paths in the table are common examples and may differ across apps.

### Preventing restored environments from causing side effects

Restored production data may hold PENDING orders. Starting normal workers could re-send emails, charge cards, or publish duplicate messages. In isolated restores:

- Enable `DR_TEST` mode or equivalent config to disable external side effects.
- Use test credentials / sandbox partner endpoints.
- Isolate Pub/Sub topics/subscriptions and output test buckets.
- Test idempotency/replay; never use real customer data to execute payments.
- Reopen live traffic only after a formal production recovery decision per runbook.

## 11. Repeatable recovery drill runbooks

Runbooks must be clear enough for someone other than the author to execute, measure, and abort safely. A document saying "restore database then verify" is insufficient.

### Pre-drill preparation

| Element | What to prepare |
|---|---|
| Scope | Workloads, backup IDs, resources, data classification, test targets |
| Owners | Exercise lead, database operator, application owner, security reviewer |
| Permissions | Service accounts, temporary IAM bindings, KMS/secret access |
| Tooling | Runbook, CLI/API versions, IaC, artifacts, query/health checks |
| Networking | Projects, subnets, ingress/egress, DNS, and private connectivity |
| Safety | No production targets, block side effects, verify allowlists |
| Budget | Machine sizing, storage, networking, timeouts, cleanup deadlines |
| Evidence | Storage for logs, timestamps, dashboards, and report templates |
| Safe abort | Abort conditions and who holds authority to halt |

Run a tabletop session before attempting a major restore for the first time. Tabletops uncover missing permissions, missing owners, runbook conflicts, and hidden assumptions about rebuilding dependencies.

### Execution phases

~~~mermaid
flowchart TD
    A["Approve scope and test target"]
    B["Safety preflight + budget/quota"]
    C["Select backup and record recovery point"]
    D["Provision isolated target"]
    E["Restore data/config"]
    F["Verify integrity and business invariants"]
    G["Start test API/workers"]
    H["Smoke tests + measure RTO/RPO"]
    I{"Meets acceptance criteria?"}
    J["PASS + archive evidence"]
    K["FAIL/PARTIAL + analyze blockers"]
    L["Cleanup + verify clean state"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
    I -->|"Yes"| J --> L
    I -->|"No"| K --> L
~~~

If a wrong target or risk of writing to production is detected, **halt immediately before restoring or starting the application**. Never push through just to finish a scheduled drill.

### Example shell safety preflight

This example validates **target configuration** only without creating or deleting resources:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

TARGET_PROJECT="$(printenv TARGET_PROJECT || true)"
RUN_ID="$(printenv RUN_ID || true)"

test -n "$TARGET_PROJECT" || { echo "Missing target project" >&2; exit 2; }
test -n "$RUN_ID" || { echo "Missing run ID" >&2; exit 2; }

case "$TARGET_PROJECT" in
  example-dr-test-1|example-dr-test-2) ;;
  *) echo "Refusing unapproved target" >&2; exit 2 ;;
esac

case "$RUN_ID" in
  dr-*) ;;
  *) echo "RUN_ID must begin with dr-" >&2; exit 2 ;;
esac

echo "Approved target project: $TARGET_PROJECT"
echo "Exercise run: $RUN_ID"
echo "Preflight only: no restore or delete operation performed"
~~~

In real automation, load centrally managed project allowlists instead of hard-coding copies across scripts. Also check executing identity, resource labels/TTLs, networking, and approval state. This check alone cannot guarantee safety if a principal still holds broad production write access.

### Who holds decision authority?

- Exercise lead: starts/stops drills and maintains the timeline.
- Data owner: chooses recovery points and evaluates data loss.
- Infrastructure operator: runs scoped restores/provisioning.
- Security representative: reviews permissions, keys, data handling, and isolation.
- Application owner: validates business functionality.
- SRE/on-call: verifies monitoring, incident workflows, and RTO.

Depending on organization size, one person may wear multiple hats, yet accountability and approval for risky actions must be explicit.

## 12. Automating verification and scheduled drills

Manual drills remain essential for human coordination, while many repetitive checks can be automated:

- Daily: inventory backups and detect failed or overdue backup jobs.
- Weekly: inspect metadata, status, age, and a checksum subset where appropriate.
- Monthly: sample isolated restores into a dedicated test target.
- Quarterly: end-to-end application restore, IAM/network checks, and RTO/RPO measurement.
- Higher-risk cadence: tabletop/full DR drills, key recovery, and region-failure exercises.

These cadences are **examples**; select frequencies based on criticality, RTO/RPO, compliance, and actual budgets. High-value transactional systems may verify more often; low-churn archives may use another cadence.

### Automation architecture pattern

~~~mermaid
flowchart LR
    SCH["Cloud Scheduler"]
    WF["Workflows / orchestrator"]
    INV["Inventory + backup metadata"]
    REST["Isolated restore action"]
    VALID["Validation job"]
    REP["Evidence + result store"]
    CLEAN["Cleanup job"]
    ALERT["Monitoring / notification"]
    SCH --> WF
    WF --> INV
    INV --> REST
    REST --> VALID
    VALID --> REP
    REP --> CLEAN
    CLEAN --> ALERT
~~~

Cloud Scheduler can trigger Workflows or Cloud Run Jobs under configured permissions. Workflows orchestrates long-running wait steps; Cloud Run Jobs run SQL/API checks and generate reports. When restore APIs return long-running operations, the orchestrator must poll with deadlines and distinguish in-progress states from success/failure.

Automation should be:

1. **Idempotent:** rerunning with the same run ID never deletes or duplicates out-of-scope resources.
2. **Scoped:** accesses only authorized backup sources and test targets.
3. **Deadline-bounded:** caps restore, validation, and cleanup durations.
4. **Re-entrant:** resumes or handles timeouts/disconnects safely.
5. **Observable:** emits correlation IDs, step statuses, and timestamps.
6. **Fail-closed:** aborts restore if target/permission/approval checks fail.
7. **Cost-bounded:** caps target counts, machine sizes, TTLs, and cleanup sweepers.

### Early checks before provisioning resources

A verification job can run read-only preflight steps:

- List backups and filter for completed successful runs.
- Confirm the backup falls inside the desired recovery window.
- Verify backup source, project, region, and data classification.
- Confirm the test target is approved and distinct from production.
- Verify the job identity holds read-backup and scoped-target-provision permissions.
- Record pre-run state before starting cost-incurring steps.

Proceed to restore only after preflight passes. Never let a job triggered by untrusted users accept arbitrary project IDs that could restore or delete any resource.

## 13. Test data, manifests, and integrity reconciliation

A backup is hard to verify without knowing expected state. Maintain **verification manifests** or business invariants tied to data checkpoints.

### Dataset-level manifest

Example JSON format generated by a trusted job at checkpoint time:

~~~json
{
  "manifest_version": 1,
  "source": {
    "service": "orders-db",
    "project": "example-prod-project",
    "recovery_point_utc": "2026-11-19T02:00:00Z"
  },
  "datasets": [
    {
      "name": "orders",
      "checks": {
        "row_count": 125000,
        "negative_totals": 0,
        "invalid_status_values": 0
      }
    }
  ],
  "verification": {
    "method": "read-only SQL queries",
    "expected_schema_version": "V42"
  }
}
~~~

Values in this JSON are strictly illustrative. When generating real manifests, store data source, timestamp, schema version, and counting method together. If backup and manifest were captured at different times, never expect counts to match identically.

### Post-restore comparisons

**Structural checks:**

- Database has expected schemas, tables, indexes, constraints, and migration levels.
- Objects have expected content types, metadata, and generation numbers.
- Kubernetes/VM configs have exact resources, runtime identities, and endpoints.

**Data checks:**

- Row/object counts across critical partitions.
- Min/max timestamps per table.
- Financial totals, transaction counts by state, and business invariants.
- Hashes over canonicalized datasets or targeted samples.
- Referential integrity and uniqueness.

**Operational checks:**

- Application startup and readiness.
- Authentication/authorization with test principals.
- Dependency connections do not leak to production.
- Query/API latency and error rates within acceptable bounds.

**Never treat simple count tables as absolute proof of integrity.** Two different datasets can share identical row counts. Combine checksums, constraints, sample queries, and business tests proportional to risk.

### Should canary records be used?

Non-sensitive test records with fixed IDs can simplify locating recovery points. However, DR tests must not rely solely on one canary record; it might survive in a backup while most data is corrupted. Pair canaries with real checks on data, transaction boundaries, and schemas.

## 14. Archiving evidence and classifying outcomes

Every drill must produce a traceable report, even when it FAILS. Never include secrets or full customer payloads in reports.

| Field | Meaning |
|---|---|
| drill_id / run_id | Unique identifier of the drill execution |
| source_backup_id | Backup or PITR timestamp used |
| source_recovery_point | Intended data point |
| target_project/resource | Test recovery destination |
| scenario | Simulated incident: accidental delete, zone loss, region loss, etc. |
| start/detect/restore/ready timestamps | Used to compute RTO per definition |
| observed_RPO / observed_RTO | Actual measured results and calculation method |
| integrity_checks | Counts, checksums, constraints, and schema results |
| application_checks | Readiness, API, auth, and business flow results |
| security_checks | IAM, KMS, secrets, and network isolation checks |
| cleanup_status | Target cleaned up or still pending |
| cost_estimate / actual | Cost of target creation, storage, and test execution |
| owner and approval | Who executed, approved, and signed off |

### Outcome statuses

- **PASS:** every mandatory acceptance criterion met with evidence.
- **PARTIAL:** partially recovered, yet missing verification or leaving unmet goals.
- **FAIL:** data, application, or RPO/RTO missed criteria.
- **BLOCKED:** could not execute due to missing permissions, features, backups, or safe targets.
- **CANCELLED:** halted under safety rules; document exact reason.

Never upgrade PARTIAL to PASS just because the hardest step succeeded. A BLOCKED test often exposes a very real DR risk—such as nobody holding permissions to restore a key or database.

## 15. Calculating RTO/RPO from a drill

Suppose a drill simulates an Orders API incident at **10:00 UTC**:

| UTC time | Event |
|---|---|
| 09:55 | Latest consistent data point chosen for restore |
| 10:00 | T0: simulated incident begins |
| 10:04 | Alert or on-call detects issue |
| 10:10 | Coordinator approves restore |
| 10:14 | Target provisioning and restore begin |
| 10:34 | Database ready; integrity checks start |
| 10:43 | Test Spring Boot app Ready; business tests start |
| 10:49 | T_service_ready: critical business flow meets criteria |
| 11:03 | Test resource cleanup and report archiving complete |

By exercise convention:

~~~text
Observed RPO = T0 - last consistent recovery point
             = 10:00 - 09:55 = 5 minutes

Observed RTO = T_service_ready - T0
             = 10:49 - 10:00 = 49 minutes
~~~

If targets are RPO ≤ 15 minutes and RTO ≤ 60 minutes, this scenario **meets the timing thresholds**. Still, mark overall outcome PASS only when all integrity, business, security, and cleanup checks pass too.

These timestamps and figures are **hypothetical**. Achieving a 5-minute RPO in one drill does not prove the system always achieves 5 minutes in every incident. Test different backup schedules, log retention, alternative timestamps, and concurrent fault scenarios.

### Measuring time accurately

- Store UTC and consistent timezones.
- Use system timestamps and coordination logs, not memory.
- Separate time to detect, time to authorize, data restore time, and application recovery time.
- Never omit waiting time for IAM, quotas, DNS, or approvals from RTO just to look better.
- If a drill was pre-announced, note that pre-staged staffing can make RTO faster than a real surprise incident.
- If recovery requires worker startup or backlog replay, `T_service_ready` must include the business functionality genuinely needed.

## 16. Separating backup, restore, and verification permissions

Backups are sensitive targets for ransomware and accidental deletion. Never let a single identity create, read, modify, and delete all backups, KMS keys, and production data without an approved need.

| Functional role | Permissions needed in principle | What to restrict |
|---|---|---|
| Backup operator | Create and view scheduled backups | Must not arbitrarily delete protected copies |
| Restore operator | Read backups and restore to authorized targets | Must not overwrite prod outside process |
| Verification job | Read manifests, query test targets, write results | Must not modify production sources |
| Security/key administrator | Manage policies and keys per duty | Must not touch business data unnecessarily |
| Auditor | Read relevant logs/status/evidence | Zero backup deletion permissions |
| Cleanup sweeper | Clean expired test resources | Must never delete production backups/instances |

Exact IAM role names vary by service and action. Identify least-privilege permissions from official Cloud SQL, Compute Engine, Backup and DR, or Backup for GKE docs; never use Owner/Editor by default for automation.

### Protecting backups against accidental deletion or attack

- Use retention policies and immutability / backup vaults where supported and appropriate.
- Separate backup admin scope from production workloads to reduce common-mode failures.
- Protect service accounts, CI/CD triggers, and backup job credentials.
- Use IAM deny / organization policies where appropriate, testing effects in non-prod first.
- Ensure KMS keys and decrypt rights remain recoverable in DR scenarios.
- Monitor backup deletions, retention edits, permission changes, and audit logs.
- Constrain data locations to avoid violating data residency.

Strongly locked retention backups can be hard to clean up in tests; understand consequences and storage fees before enabling on buckets or vaults. Never test irreversible locks on production resources.

## 17. Cleanup, cost, and orphaned resources after drills

Restoring a test database, disk, or cluster incurs charges even with zero traffic. A drill ends operationally only once temporary resources are handled per policy.

### Classifying resources before cleanup

| Group | Examples | Deleted by job? |
|---|---|---|
| Protected source backups | Cloud SQL backups, source snapshots, backup vaults | No, except via dedicated retention policies |
| Isolated drill targets | Test databases, disks, VMs, namespaces, scratch objects | Yes, after verifying run ID and approval |
| Report data / evidence | Timelines, checksum summaries, RTO/RPO, logs | Kept per approved retention |
| Shared infra configs | Shared VPC, DNS, log buckets, repositories | No |
| Temporary credentials | Short-lived test IAM bindings or test secret versions | Revoked via proper workflow |

### Ordered cleanup

1. Stop test workloads and halt jobs/consumers generating more data.
2. Save required evidence without copying excessive sensitive payloads.
3. Confirm the target carries the drill's exact run ID / owner label.
4. Delete child resources such as test subscriptions, Pods, disks, or objects by dependency order.
5. Delete test services/instances/namespaces only after confirming they are not shared.
6. Revoke temporary access and test secrets.
7. Confirm zero billable resources remain for the run.
8. Record cleanup status, final cost, and any exceptions to resolve.

### Fallback sweeper

End-of-job cleanup is insufficient if CI runners are killed or jobs time out. Run a scoped, scheduled sweeper checking resource owner/run ID, `created_at`/`expires_at`, and run status. It must support dry-run, project allowlists, deletion caps, and audit logs.

**Never delete by empty prefix or overly broad rules** such as all VMs in a test project, because other drills or teams may share that project. When ownership is uncertain, flag cleanup pending and route to an owner for review.

### Managing drill costs

- Pick machines/instances small enough to test safely yet representative for RTO where required.
- Cap target runtime and set budget alerts.
- Track restored bytes, disk/storage, network transfer, and instance runtime.
- Separate **monthly verification cost** from **real DR deployment cost**.
- Never use tiny environments to claim production RTO is guaranteed; data volume, throughput, quotas, and networking differ.

A sample restore on a small dataset proves the workflow works, not that a multi-terabyte database restores in the same time. Supplement with full-scale rehearsals or validated extrapolations.

## 18. Common pitfalls in backup verification and DR drills

| Symptom | Common cause | Prevention / check |
|---|---|---|
| Backups exist yet restore fails | Corrupted backup or incompatible method/target | Periodic restore tests matching engine/version |
| Restore succeeds yet app fails | Schema mismatch, missing secrets/connections | Run release-matched smoke tests |
| Cannot reach target | Wrong IAM, VPC, DNS, or private endpoint | Safety preflight and network diagnostics |
| Wrong data despite matching row count | Backup from wrong time, logic bug, uncanonicalized hash | Recovery-point manifests, invariants, and checksums |
| RPO missed | Infrequent backups, PITR disabled, insufficient logs | Audit retention/windows and monitor lag |
| RTO missed | Waiting on approvals, quotas, restore throughput, manual steps | Time each phase and automate safe steps |
| Replicas hold corrupted data too | Logical corruption propagated to replicas | Keep backups/PITR separate from replication |
| Missing decrypt access | KMS key disabled or wrong key IAM | Drill key permissions and protect key lifecycle |
| Workers replay real transactions | DR environment lacked side-effect isolation | Sandbox APIs, fake endpoints, egress controls |
| PASS declared prematurely | Relied solely on restore job status | Acceptance criteria cover app and business flows |
| Sensitive data exposed in test project | Prod data copied to weakly secured env | Data classification, IAM, encryption, retention |
| Drills cause lingering high bills | Targets left behind after runner crashes | TTLs, cleanup jobs, owners, and budget alerts |
| Nobody can follow the runbook | Tribal knowledge held by one person, stale commands | Tabletops, cross-training, and versioned runbooks |
| Multi-region DR fails on one broken key | Common-mode failure in IAM/KMS/control plane | Dependency mapping and controlled fault injection |

### When a backup is missing or unrestorable

Never delete evidence and re-run to report prettier numbers. Instead:

1. Record backup ID, state, and error codes without sensitive payloads.
2. Check whether another valid backup or PITR window exists.
3. Assess RPO/RTO risk and notify the accountable owner.
4. Open an incident or risk item if required recovery capability was lost.
5. Fix configs, permissions, or workflows, then **re-drill** before closing the issue.

Drill failures are valuable information when documented honestly. An unsubstantiated PASS report is far more dangerous than a FAIL report that drives real improvements.

## 19. Complete example: Orders API recovery drill

Suppose Orders runs Spring Boot on Cloud Run, PostgreSQL on Cloud SQL, documents in Cloud Storage, and Pub/Sub event workers. The drill goal is confirming an accidental data deletion scenario recovers within agreed limits.

### Hypothetical requirements

- RPO: at most 15 minutes.
- RTO: at most 60 minutes from simulated incident start until test order lookup/creation flows work.
- Never send emails, charge payments, or publish Pub/Sub events to production.
- All test resources reside in an approved DR test project.
- Source backups remain untouched; cleanup removes only drill-created targets.

### Scenario and plan

| Phase | Action | Evidence |
|---|---|---|
| Preflight | Verify owner, target, IAM/KMS, budget, and isolation | Approval, allowlist, identity |
| Inventory | Select Cloud SQL backup/PITR and object generations | Backup IDs, timestamps |
| Restore | Restore test database and objects to target | Operation IDs, restore outputs |
| Rebuild app | Deploy test Cloud Run revision using exact image digest | Revision, config, IAM |
| Data validation | Query order counts, totals, constraints, object hashes | SQL and checksum reports |
| Business checks | Read/create sandbox orders blocking side effects | Test responses, correlation IDs |
| Measure | Record T0, recovery point, service ready | RPO/RTO calculation |
| Cleanup | Delete target and revoke temporary IAM; retain evidence | Post-cleanup resource inventory |

### Business assertions

1. A test customer can look up an order present at the recovery point.
2. Order value totals and payment states match the expected manifest.
3. Zero orders have negative amounts or invalid statuses.
4. Creating an order in sandbox does not duplicate on retry.
5. Document objects retain accurate content and metadata.
6. Unauthenticated requests are rejected as before.
7. Logs/traces include correlation IDs without passwords or sensitive data.

### Sample conclusion

A drill report might state: "DB and object restores passed, API operational after 49 minutes, measured RPO 5 minutes, but the runbook omitted how to bind the runtime service account on the target." Even if IAM binding was manual, timing targets passed, yet an action item is needed to remove manual steps. If any business assertion was skipped, mark the outcome PARTIAL instead of PASS.

### Post-drill action items

| Action | Goal | Owner | Verification method |
|---|---|---|---|
| Move Cloud Run/IAM config into IaC | Cut rebuild time | Platform | Provision target from IaC in next drill |
| Add recovery-point integrity manifest | Prevent false PASS | Data team | Counts/constraints/hashes compare cleanly |
| Enable overdue-backup alerts | Catch coverage drops early | SRE | Simulate missed backup event |
| Drill KMS permission rotation in test | Surface key dependencies | Security | Restore succeeds after test policy edit |
| Automate target cleanup by run ID | Reduce cost and risk | Platform | Sweeper leaves unrelated resources untouched |

Action items need concrete due dates and priorities in the organization's tracking system. Never leave plans stranded in a postmortem doc with no assigned owner.

## 20. Hands-on exercise: verify backups and run a safe DR drill

Context: you are an SRE supporting `orders-api`. The app deploys on Cloud Run, primary data lives in Cloud SQL PostgreSQL, and documents live in Cloud Storage. Prove the team can recover data and business flows with **30-minute RPO** and **90-minute RTO**. This lab uses a test environment with backups of synthetic data; never use real customer data or credentials.

### Part A — Requirements analysis

1. State the definitions of SLIs, RTO, RPO, and measurement start/stop timestamps.
2. Draw a dependency map covering API, database, bucket, images, IAM, secrets, KMS, and networking.
3. List backupable resources vs. configs rebuilt via IaC.
4. Pick at least one failure scenario: database loss, accidental record deletion, or VM/disk failure.
5. Propose PASS criteria for data, application, IAM, and cleanup.

### Part B — Create fixtures and test backups

1. Use an approved GCP test project.
2. Seed synthetic data: 20 orders with fixed statuses and totals.
3. Upload several small JSON objects into a dedicated bucket.
4. Record the recovery point and a manifest containing row counts, checksums, and schema version.
5. Create a backup per supported test service options or pick an existing valid test backup.
6. Confirm job completion and record the exact backup ID in inventory.

### Part C — Isolated restore

1. Run a safety preflight confirming target project and run ID.
2. Verify service accounts and required permissions without granting Owner to the pipeline.
3. Restore database/objects into a **separate test target** using supported workflows.
4. Record restore start time, end time, and operation ID.
5. Verify schema, business invariants, row counts, and checksums.
6. Run an app revision with `DR_TEST` mode and sandbox external endpoints.
7. Run read-order smoke tests and non-production test transactions.
8. Compute observed RPO/RTO, stating assumptions explicitly.

### Part D — Controlled failure

In the test target, test one of these scenarios:

- An invalid backup/version.
- A test service account lacking secret read permission.
- A missing object in the verification dataset.
- A schema incompatible with the app container image.

Mark the test FAIL or BLOCKED with the exact root cause. Verify logs show resource IDs and error codes without secret payloads. Never create a production incident to complete this exercise.

### Part E — Cleanup and reporting

1. Shut down test workloads and stop test subscribers/workers.
2. Delete only resources tagged with the run ID; keep source backups intact.
3. Revoke any temporary IAM bindings or secrets.
4. Confirm zero billable resources remain for the run.
5. Write a report with timeline, acceptance criteria, RPO/RTO, cost, and cleanup status.
6. Write at least three action items with owners, priority, deadlines, and verification steps.

### Completion criteria

| Item | Expected outcome |
|---|---|
| Safety | Zero edits to production sources or deletion of source backups |
| Recovery target | Test resources clearly named and labeled with owner |
| Data integrity | Counts, invariants, and samples/hashes match manifest |
| App recovery | Spring Boot reads data and passes appropriate smoke tests |
| Time targets | Observed RPO ≤ 30 minutes, observed RTO ≤ 90 minutes |
| Security | IAM, secrets, networking, and KMS verified |
| Evidence | Run ID, backup ID, timestamps, and verification records saved |
| Cleanup | Target cleaned up with no unexpected ongoing fees |

## 21. Backup verification and periodic drill checklist

- [ ] Workloads and owners identified for every dataset and resource.
- [ ] RPO, RTO, and PASS/FAIL criteria agreed upon.
- [ ] Backup, replication, HA, and PITR clearly distinguished.
- [ ] Backup types, retention, and recovery windows confirmed.
- [ ] Backup ID, source resource, status, and timestamp verified.
- [ ] Schema versions, image digests, and matching configs identified.
- [ ] Dependency map covers app, data, IAM, keys, network, and event queues.
- [ ] Safe DR test target configured with allowlists and approvals.
- [ ] Real email, payment, webhook, and message side effects blocked.
- [ ] Consistent restore point selected with expected manifest recorded.
- [ ] Restored into test target using service-supported workflows.
- [ ] Row/object counts, checksums, schemas, and business invariants verified.
- [ ] Startup, readiness, authentication, and business APIs tested.
- [ ] Duration measured from T0 to service ready, not merely restore job runtime.
- [ ] Observed RPO computed using actual recoverable point.
- [ ] Runtime permissions, Secret Manager, and KMS decrypt verified.
- [ ] Logs, alerts, dashboards, and escalation paths tested.
- [ ] PASS/PARTIAL/FAIL/BLOCKED recorded honestly.
- [ ] Runbook and owners assigned for every step.
- [ ] Next drill scheduled based on criticality.
- [ ] Time caps, budget alerts, and cleanup deadlines configured.
- [ ] Test resources cleaned up, temporary permissions revoked, and evidence archived.
- [ ] Action items created and tracked until verified complete.

## Self-check questions

**1. Why is a backup job's SUCCESS status insufficient to prove recoverability?**

Because the backup may be incomplete, inconsistent, missing decrypt permissions, or incompatible with the app version at restore time. At least one restore and data/functional verification test is required.

**2. How do RTO and RPO differ?**

RTO limits service recovery time for a scenario; RPO limits maximum acceptable data loss measured from the recovery point. Recovering quickly does not guarantee low data loss, and vice versa.

**3. Why does a database replica not replace backups?**

Because erroneous deletes or corrupted updates replicate to the replica too. Backups/PITR provide historical recovery points prior to the error within supported windows.

**4. Why must restores be tested in an isolated environment?**

To avoid overwriting production, emitting real side effects, and to constrain permissions, networking, and budgets. Production data used in verification must still be protected according to its classification.

**5. Why is a manifest tied to the backup timestamp necessary?**

Because live databases keep changing. Comparing today's live row counts against an older backup shows normal operational drift rather than restore errors.

**6. What can a Cloud Storage object checksum verify?**

It verifies object contents were not unexpectedly altered within the supported checksum algorithm and scope. It does not prove the app processes the data properly or that all needed objects exist.

**7. Why must a full DR drill recover IAM, secrets, and networking too?**

Because applications only operate when identity, access permissions, routing, DNS, and dependencies work. A restored database with an unreachable API fails business recovery.

**8. When should you use FAIL, PARTIAL, or BLOCKED?**

FAIL when mandatory criteria miss; PARTIAL when partially restored yet verification is incomplete; BLOCKED when prerequisites like permissions, source backups, or safe targets prevent execution.

**9. Why should drills include fallback cleanup?**

Because test teardown/finally blocks may fail to run if a runner crashes or disconnects. A sweeper using owner/run IDs and TTLs catches orphaned test resources.

**10. If a drill achieves a 5-minute RPO and 49-minute RTO once, can you guarantee those numbers always hold?**

No. You must test across different recovery points, data volumes, failure scenarios, load levels, and dependencies to gauge target reliability under real conditions.

## References

- [Google Cloud Architecture Framework: Reliability](https://docs.cloud.google.com/architecture/framework/reliability)
- [Google Cloud: Disaster recovery planning guide](https://docs.cloud.google.com/architecture/dr-scenarios-planning-guide)
- [Cloud SQL: Backups overview](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud SQL: Point-in-time recovery](https://docs.cloud.google.com/sql/docs/postgres/backup-recovery/pitr)
- [Compute Engine: Snapshots overview](https://docs.cloud.google.com/compute/docs/disks/snapshots)
- [Cloud Storage: Object Versioning](https://docs.cloud.google.com/storage/docs/object-versioning)
- [Cloud Storage: Soft delete](https://docs.cloud.google.com/storage/docs/soft-delete)
- [Cloud Storage: Object integrity](https://docs.cloud.google.com/storage/docs/data-validation)
- [Firestore: Backups](https://docs.cloud.google.com/firestore/native/docs/backups)
- [Firestore: Export and import](https://docs.cloud.google.com/firestore/native/docs/manage-data/export-import)
- [Spanner: Back up and restore databases](https://docs.cloud.google.com/spanner/docs/backup)
- [BigQuery: Time travel and fail-safe](https://docs.cloud.google.com/bigquery/docs/time-travel)
- [BigQuery: Table snapshots](https://docs.cloud.google.com/bigquery/docs/table-snapshots-intro)
- [Backup for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/add-on/backup-for-gke/concepts/backup-for-gke)
- [Cloud Run Jobs](https://docs.cloud.google.com/run/docs/create-jobs)
- [Google Cloud Workflows](https://docs.cloud.google.com/workflows/docs/overview)
- [Cloud Scheduler](https://docs.cloud.google.com/scheduler/docs/overview)
- [Secret Manager overview](https://docs.cloud.google.com/secret-manager/docs/overview)

## Conclusion

**Backups hold value only when they can be restored verifiably.** Creating a backup successfully is only the starting line; true recoverability depends on data consistency, backup/key access permissions, schema and app version alignment, networking, secrets, infrastructure provisioning, and incident procedures. Multi-level verification—from inventory and checksums to isolated restores, smoke tests, and full DR drills—exposes gaps before a real disaster strikes.

Define RTO/RPO from business impact, protect backup sources, drill in isolated environments, archive evidence by run ID, and measure until the **business flow** is truly ready. Automated verification schedules and cleanup make the process repeatable; tabletops, controlled failovers, and action items ensure the team possesses not merely backups, but genuine **recovery capability**.

# Maintenance, Version Upgrades, and Schema Changes on Cloud SQL and AlloyDB

A retail system stores orders in **Cloud SQL for PostgreSQL**, serving APIs on **Cloud Run** and workers on **GKE**. The platform team wants to receive security patches, upgrade PostgreSQL to a new major version, and add a delivery-status column without disrupting checkout sessions. On another analytical system, **AlloyDB for PostgreSQL** has a primary and read pools that need scheduled maintenance separately.

These three types of changes **are not the same**:

- **Maintenance:** Google Cloud updates managed software and underlying infrastructure. It may require switching over or restarting components, temporarily dropping connections.
- **Database engine upgrade:** changes the PostgreSQL compatibility version — especially a **major version** — which can alter query behavior, extensions, and downtime requirements.
- **Schema migration:** the application team changes tables, columns, indexes, constraints, or data. Even though Google manages the server, **code compatibility and DDL locking remain the application team's responsibility**.

This lesson belongs to the **Cloud SQL and AlloyDB** chapter in the **CLOUD_PROVIDERS_GCP** module. It connects project/IAM/VPC organization, Cloud Run, GKE, storage, and databases with release automation, resource protection, reliability, and cost. Examples focus on PostgreSQL because both products share that ecosystem; **never apply PostgreSQL commands verbatim to Cloud SQL MySQL or SQL Server**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish maintenance versions, PostgreSQL minor/major versions, and application schema versions.
2. Configure and inspect **maintenance windows**, rollout timing, notifications, and **deny periods** within Cloud SQL/AlloyDB limits.
3. Prepare application resilience against dropped connections: connection pooling, bounded retries, HA, read replicas, and SLO testing.
4. Plan major version upgrades via in-place upgrades or parallel migration, understanding that rollback **is not an in-place downgrade**.
5. Ship schema changes using **expand → backfill → switch → contract**, avoiding long DDL locks and breaking older code revisions.
6. Run migrations from CI/CD, monitor locks, rehearse restores, and evaluate RTO/RPO and cost.

## 2. Four Version Layers to Track

| What Is Updated | Primary Owner | Example | Impact to Assess |
| --- | --- | --- | --- |
| **Maintenance release** | Released by Google Cloud; user chooses supported schedule/timing. | OS/platform patches, engine components. | Brief connection drops, security fixes, schedule notices. |
| **PostgreSQL minor compatibility** | Managed by the service per product policy. | 16.3 → 16.4. | Bug fixes, extension/driver checks; may bundle with maintenance. |
| **PostgreSQL major version** | Operations team actively plans the upgrade. | 15 → 16, if a supported target. | Breaking changes, flags, extensions, downtime, rollback. |
| **Application schema version** | Development team / DBA. | Adding `orders.customer_note_v2`. | Locks, backfill load, multi-revision app compatibility. |

A **self-service maintenance** command does not upgrade the PostgreSQL major version. Likewise, an engine upgrade completing does not automatically run your app's Flyway/Liquibase migrations.

~~~mermaid
flowchart LR
    CODE["Cloud Run / GKE revisions"] --> DRIVER["DB drivers / pools"]
    DRIVER --> DB["Cloud SQL or AlloyDB"]
    MAINT["Maintenance release"] -. "Platform-managed patch" .-> DB
    ENGINE["Major version upgrade"] -. "Engine compatibility testing" .-> DB
    MIG["Schema/data migration"] -. "App-managed DDL + backfill" .-> DB
    CI["CI/CD + approval"] --> ENGINE
    CI --> MIG
    OBS["Monitoring + Audit Logs"] -. "End-to-end observability" .-> DB
~~~

## 3. Cloud SQL: Maintenance Windows and Deny Periods

### 3.1. A Maintenance Schedule Does Not Guarantee Zero Downtime

Cloud SQL provides a **maintenance window**: a preferred day and hour to **start** maintenance, within a one-hour scheduling window. You can choose rollout timing:

| Maintenance Timing | Meaning |
| --- | --- |
| `Any` | No specific week assigned; often early in the rollout wave. |
| `Week 1` (`preview`) | Roughly 7–14 days after notification. |
| `Week 2` (`production`) | Roughly 15–21 days after notification. |
| `Week 5` (`week5`) | Roughly 35–42 days after notification. |

**Staging-before-production pattern:** put staging on `Week 1` and production on `Week 2` or `Week 5`, running smoke and connection tests after staging maintenance before production updates. Pick low-traffic hours and check **time zones**: hours passed to `gcloud` are **UTC**, not the operator's local time zone.

A maintenance event can make the database unreachable for a period of time. Disruption depends on edition, topology, workload, and connection handling; **the maintenance window is not a hard cap on outage duration**. Even with a schedule configured, urgent security patches may still be applied out of band.

### 3.2. Deny Maintenance Periods

A **deny period** blocks scheduled maintenance during sensitive business windows. Cloud SQL permits **1–90 days** subject to product rules. Effective **August 15, 2025**, instances on a maintenance version **older than 12 months** cannot set a new deny period until updated to a sufficiently recent version.

For example, block scheduled maintenance during a flash-sale week, while actively scheduling patching afterward. Deny periods **do not block user-initiated operations**, cannot disable emergency security patches, and do not guarantee zero downtime from other causes.

Never chain deny periods back-to-back to defer patching indefinitely. On primaries with read replicas, check how deny periods apply to the replicas as well.

### 3.3. Reading Config and Adjusting Schedules with `gcloud`

The Bash commands below use **hypothetical resource names**. The `patch` command **writes real configuration** — run only in an approved test project:

~~~bash
PROJECT_ID="retail-lab"
SQL_INSTANCE="orders-db"

# READ-ONLY: inspect state, schedule, engine version, and maintenance.
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" --format=yaml

# WRITE: set Sunday 02:00 UTC window and Week 2.
gcloud sql instances patch "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --maintenance-window-day=SUNDAY \
  --maintenance-window-hour=2 \
  --maintenance-release-channel=production

# READ-ONLY: verify returned config rather than trusting the command blindly.
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --format="yaml(settings.maintenanceWindow,maintenanceVersion,availableMaintenanceVersions)"
~~~

For Vietnam (`Asia/Ho_Chi_Minh`), **02:00 UTC is 09:00 AM local time**, not 02:00 AM. To target 02:00 AM Sunday Vietnam time, convert it to **19:00 UTC Saturday**.

Subscribe the right **maintenance notifications** for the project and recipients; Cloud SQL does not automatically email every operator. Ahead of scheduled maintenance, verify instance status, release freezes, alerting, and runbooks.

### 3.4. Self-Service Maintenance and Current Versions

Cloud SQL can allow **proactively applying a maintenance version** ahead of the fleet schedule:

~~~bash
# READ-ONLY: verify maintenanceVersion and availableMaintenanceVersions
# in describe output before picking a value.
gcloud sql instances describe "$SQL_INSTANCE" \
  --project="$PROJECT_ID" --format=yaml

# WRITE, ILLUSTRATIVE ONLY: replace value with a real version from describe.
gcloud sql instances patch "$SQL_INSTANCE" \
  --project="$PROJECT_ID" \
  --maintenance-version="REPLACE_WITH_AVAILABLE_MAINTENANCE_VERSION"
~~~

Never guess a maintenance version string. Once updated, **you cannot simply patch back to an older maintenance version**. In replica topologies, follow the documented update order for primaries and replicas.

## 4. AlloyDB: Cluster-Level Maintenance

AlloyDB is also managed by Google Cloud, yet has a **primary/read pool model** and its own maintenance rules.

| Attribute | Cloud SQL for PostgreSQL | AlloyDB for PostgreSQL |
| --- | --- | --- |
| Typical config scope | Instance. | Cluster, covering primary and read pools. |
| Maintenance window | One-hour UTC day/hour window. | Preferred start hour; events can extend past the window. |
| Rollout timing | `Any`, `Week 1`, `Week 2`, `Week 5` supported. | Use maintenance windows, notifications, and staging clusters per AlloyDB guidance. |
| Deny period | Up to **90 days**, with stale-version restrictions. | Up to **30 days**, requires cluster on a sufficiently recent maintenance version. |
| Update order | Depends on maintenance mechanism and replica topology. | Per docs: read pools first, then primary during scheduled maintenance. |
| PostgreSQL minor | Managed per Cloud SQL policy. | AlloyDB applies minor compatibility updates automatically via maintenance. |
| Major version | In-place or migration depending on engine/version. | In-place cluster major upgrade or migration to a new cluster. |

**Deny periods do not block emergency maintenance** and have product limits. Never apply Cloud SQL's 90-day limit to AlloyDB.

### 4.1. Configuring an AlloyDB Window

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
ALLOY_CLUSTER="analytics-db"

# READ-ONLY: inspect maintenanceUpdatePolicy and maintenanceSchedule.
gcloud alloydb clusters describe "$ALLOY_CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" --format=yaml

# WRITE: prefer starting maintenance Sunday 02:00 UTC.
gcloud alloydb clusters update "$ALLOY_CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --maintenance-window-day=SUNDAY \
  --maintenance-window-hour=2

# READ-ONLY: confirm cluster saved the policy.
gcloud alloydb clusters describe "$ALLOY_CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format="yaml(maintenanceUpdatePolicy,maintenanceSchedule)"
~~~

To block a flash-sale period with an AlloyDB deny period, the update command takes `--deny-maintenance-period-start-date`, `--deny-maintenance-period-end-date`, and `--deny-maintenance-period-time`. **Never run placeholder values in production**; confirm the 30-day cap, current maintenance version, and UTC semantics first.

### 4.2. Staging Clusters and Read Pools

Maintain a **staging cluster matching production** in major version, extensions, and workload profile so it receives maintenance early enough for testing. During scheduled maintenance, AlloyDB may update read pools before the primary, creating **per-instance-type disruptions**. Therefore:

- Never assume read pool capacity remains uninterrupted throughout maintenance.
- Test connection retries, read routing, replica lag, and safe fallbacks.
- Monitor query performance, invalid connections, latency, and error rates per endpoint.
- Never treat primary/read pool high availability as proof of **zero-downtime** for every maintenance event or major upgrade.

## 5. Preventing Disruption at the Application Layer

### 5.1. Database Connections Are Ephemeral Resources

During maintenance, failover, or engine upgrades, **open TCP connections can be severed**. No IAM policy or backup keeps an in-flight transaction alive once its connection drops.

~~~mermaid
flowchart LR
    USER["Client"] --> APP["Cloud Run / GKE app"]
    APP --> POOL["Connection pool"]
    POOL --> DB["Cloud SQL / AlloyDB primary"]
    DB -. "Maintenance / failover" .-> LOST["Connection reset / timeout"]
    LOST --> RECON["Discard broken connection, reconnect"]
    RECON --> POOL
    APP --> CHECK["Idempotency + transaction boundaries"]
~~~

Put these safeguards in place:

1. **Connection pool** with sensible validation, idle timeouts, and max lifetimes so broken connections are evicted and sockets are refreshed.
2. Explicit **connection timeouts** and **statement timeouts**; never hang forever when the backend is unavailable.
3. **Retries with backoff + jitter** strictly for transient errors and **safe-to-retry** operations.
4. **Idempotency keys** or unique/transactional constraints for `POST` requests creating orders, recording invoices, or transferring funds.
5. **Circuit breakers / backpressure** so thousands of Cloud Run/GKE replicas do not stampede the database during recovery.
6. Readiness/liveness probes tuned so brief DB maintenance does not cause cascading Pod restarts.

**Never retry a transaction with side effects just because the client missed the response.** If the commit may have succeeded before the connection dropped, query status by operation ID or enforce idempotency before re-writing.

### 5.2. HA, Replicas, and PITR Solve Different Problems

| Component | What It Helps With | What It Does Not Replace |
| --- | --- | --- |
| **High availability / failover** | Cuts downtime on certain component faults. | App reconnect/retry logic; major upgrade downtime. |
| **Read replica / read pool** | Offloads reads, scales certain query classes. | Writable primary; not an automatic write target on failure. |
| **Automated backup / PITR** | Restores data to a pre-incident point within retention. | Instant RTO, zero-data-loss recovery, automatic schema/engine rollback. |
| **Maintenance window** | Picks lower-impact windows. | Zero-downtime guarantees; blocking urgent patches. |
| **Schema expand-contract** | Lets old and new app code coexist during rollouts. | Does not eliminate all DDL locks or bad data writes. |

**RTO** is acceptable recovery duration; **RPO** is acceptable data loss interval. Values like 15-minute RTO and 5-minute RPO are **illustrative business targets**, not default Google Cloud guarantees. Backups count only after **rehearsing restores and measuring real timings**.

## 6. Upgrading PostgreSQL Major Versions: Preparation and Options

### 6.1. Minor vs. Major

PostgreSQL minor updates mainly deliver bug and security fixes, whereas **major upgrades** can change SQL behavior, query planner plans, extensions, flags, or defaults. Cloud SQL and AlloyDB manage minor updates on their own schedules; **major upgrades must be planned as potentially disruptive changes**.

Before a major upgrade, inventory:

- Current version, **actually supported target versions**, and release lifecycle.
- JDBC/psycopg/ORM versions; Java/Spring Boot apps, migration tools, and client drivers.
- Extensions (`PostGIS`, `pg_stat_statements`, `pglogical`, etc.), deprecated SQL features, or changed defaults.
- Database flags, encoding/collations, roles, privileges, cron jobs, views, triggers, and logical replication slots.
- Primary/replica/read pool topology, replication lag, and external CDC/Datastream consumers.
- Acceptable downtime, backup/PITR strategy, deploy freezes, and cutover plan.

**Never pick a target just by incrementing the version number by one.** Inspect `upgradableDatabaseVersions` or the service's upgrade precheck output. Some extensions and replication topologies carry special restrictions.

### 6.2. In-Place Upgrade vs. Migrating to a New System

| Option | Pros | Risks / When to Consider |
| --- | --- | --- |
| **In-place major upgrade** | Keeps instance/cluster name, address, and most config; less endpoint rewiring. | DB becomes unavailable during upgrade; rollback is not an in-place downgrade. |
| **Migrate to new DB/cluster** | Parallel environment for pre-cutover testing and controlled cutover window. | Data sync, extensions/collations, replication, endpoint changes, parallel billing. |
| **Export/import** | Conceptually simple for small datasets or permitted downtime windows. | Downtime spans full export/import; very slow at scale; needs integrity checks. |
| **Database Migration Service** where source/target supported | Can cut over quickly using replication/CDC. | Check DDL, extension, network, replication slot, and lag constraints. |

For systems requiring **near-zero downtime**, evaluate parallel migration and controlled app cutover for your workload; **never claim an in-place major upgrade is zero-downtime**.

### 6.3. Cloud SQL for PostgreSQL: In-Place Major Upgrade

Cloud SQL runs a **precheck → pre-upgrade backup → upgrade → post-upgrade backup** workflow. It uses PostgreSQL upgrade tooling and can preserve instance ID and IP, yet the instance is **unavailable for a period of time**.

~~~bash
PROJECT_ID="retail-lab"
INSTANCE="orders-db"

# READ-ONLY: confirm source version, upgrade targets, and replicas.
gcloud sql instances describe "$INSTANCE" \
  --project="$PROJECT_ID" --format=yaml

# WRITE, ILLUSTRATIVE: run only after prechecks, backup, and change approval.
# Target enum must appear in the instance's upgradableDatabaseVersions.
gcloud sql instances patch "$INSTANCE" \
  --project="$PROJECT_ID" \
  --database-version=POSTGRES_16
~~~

If replicas exist, follow the **documented topology sequence**: upgrade replicas before the primary or use Cloud SQL's supported **include replicas** behavior, accounting for recreation rules and limits. Never silently bump the primary version while external replication or CDC consumers are unprepared. On Cloud SQL PostgreSQL, certain in-place major upgrades **drop logical replication slots**, so record and recreate them to resume streams per the docs.

**Rollback:** after a successful upgrade, running `--database-version=POSTGRES_15` is not a rollback. You may need to **restore a pre-upgrade backup to a brand-new recovery instance**, rewire endpoints/replicas, and reconcile writes committed after that backup. Verify version, target, and retention constraints on backups/PITR before relying on them.

### 6.4. AlloyDB: In-Place Major Upgrade

AlloyDB binds the PostgreSQL major version to the **cluster**, applying minor compatibility updates via maintenance. In-place major upgrades run prechecks and impact **both the primary and read pools**. Google Cloud docs note a full cluster upgrade can take **tens of minutes to several hours**, with primary downtime **typically around 20–60 minutes** depending on data size, schema, and topology — never treat those figures as a hard SLA for every cluster.

~~~bash
REGION="asia-southeast1"
PROJECT_ID="retail-lab"
CLUSTER="analytics-db"

# READ-ONLY: inspect cluster version, topology, and state.
gcloud alloydb clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" --region="$REGION" --format=yaml

# WRITE, ILLUSTRATIVE: target must be a supported major version.
# Never run without backup/restore drills, prechecks, and approval.
gcloud alloydb clusters upgrade "$CLUSTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --version=POSTGRES_16 \
  --async
~~~

Once a major upgrade finishes, **AlloyDB cannot downgrade the cluster in place**; returning to the prior version requires **restoring a pre-upgrade backup into a new cluster** and switching app traffic. During the upgrade, cancellation is only allowed at specific stages; never treat `--async` as harmless background execution with zero disruption. If your SLO allows only a few minutes of downtime, evaluate migration instead of defaulting to in-place.

### 6.5. Pre- and Post-Major-Upgrade Checklists

**Before:**

1. Freeze scope with an owner and change window, and halt unrelated schema migrations.
2. Rehearse on a **representative copy of data** with matching extensions, flags, replica topology, and query load.
3. Confirm backups succeeded, restores work, and RTO/RPO are measured.
4. Validate target version, drivers/ORMs, `pg_dump`/restore compatibility, and deprecated features.
5. Plan write quiescing/fencing, retries, health probes, migration/CDC slots, and fallback endpoints.

**After:**

1. Verify target engine version and primary/replica/read pool health.
2. Run end-to-end API tests: create order, read order, payments, reporting, and critical queries.
3. On PostgreSQL, consider running **`ANALYZE`** to refresh query planner statistics post-upgrade per docs.
4. Verify extensions, roles, database flags, logical replication/CDC streams, and fresh backups/PITR.
5. Watch p95/p99 query latency, locks, CPU/memory, error rates, connection pools, and billing throughout the agreed observation window.

## 7. Zero-Disruption Schema Changes: Expand → Migrate → Contract

### 7.1. Why `ALTER TABLE` Is Still Risky on Managed DBs

Cloud SQL and AlloyDB manage infrastructure, **not whether DDL statements block live traffic**. An `ALTER TABLE`, constraint validation, index rebuild, or massive data migration can:

- Wait on table locks or block concurrent transactions.
- Hold transactions open too long, spiking replication lag and WAL volume.
- Trigger I/O/CPU spikes that breach checkout SLOs.
- Break older app revisions if columns are renamed or dropped while old code still reads them.

On PostgreSQL, **never judge DDL cost by line count**. A one-line migration on a hundred-million-row table can carry far more risk than a dozen small migrations.

### 7.2. The Expand-Contract Strategy

Suppose `orders` has a `customer_note` column and you want to transition safely to `customer_note_v2`.

~~~mermaid
flowchart LR
    E["1. Expand: add new column"] --> W["2. Deploy: fallback reads / dual-write"]
    W --> B["3. Batch backfill"]
    B --> V["4. Verify + switch readers"]
    V --> C["5. Contract: drop old column after rollback window"]
~~~

| Phase | Database | Application |
| --- | --- | --- |
| **Expand** | Add nullable `customer_note_v2`. | Old code continues running normally. |
| **Dual write / read fallback** | Both columns coexist. | New code writes both, reads v2 with fallback to v1. |
| **Backfill** | Update historical rows in monitored batches. | Both revisions remain compatible. |
| **Switch** | Verify counts, nulls, correctness, and read replicas. | Gradually shift reads to v2 via feature flags/canary. |
| **Contract** | Drop old column once zero consumers depend on it. | Code rollback to old version must be replaced by controlled recovery. |

**Order matters:** add the new structure **first**, move apps onto it **second**, and drop the old structure **last**. Never run a direct `RENAME COLUMN` while Cloud Run serves traffic across multiple revisions still referencing the old name.

### 7.3. PostgreSQL SQL Examples

Assume `orders(id BIGINT PRIMARY KEY, customer_note TEXT, ...)` exists. Run in a lab with test data:

~~~sql
-- WRITE: EXPAND phase, adds column without breaking old code.
SET lock_timeout = '5s';
SET statement_timeout = '30s';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_note_v2 TEXT;
~~~

Timeouts curb infinite lock queues, **but do not make migrations safe on their own**. New app code writes both `customer_note` and `customer_note_v2` inside the same transaction rather than splitting dual-writes across separate HTTP calls.

Example **single backfill batch**, looped cleanly until no rows remain:

~~~sql
-- WRITE: at most 500 rows/batch, avoiding a single full-table UPDATE lock.
WITH batch AS (
  SELECT id
  FROM orders
  WHERE customer_note_v2 IS NULL AND customer_note IS NOT NULL
  ORDER BY id
  LIMIT 500
  FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET customer_note_v2 = o.customer_note
FROM batch
WHERE o.id = batch.id
  AND o.customer_note_v2 IS NULL;
~~~

To avoid races with live writes, **deploy dual-writes before starting the backfill**; when concurrent updates occur, define clear consistency rules. `SKIP LOCKED` helps batching **without replacing data verification**. Monitor updated row counts, errors, runtime, WAL/replication lag, and API p95 before increasing batch size.

Checking progress:

~~~sql
-- READ-ONLY: rows still waiting to be backfilled from old column.
SELECT count(*) AS remaining
FROM orders
WHERE customer_note IS NOT NULL
  AND customer_note_v2 IS NULL;

-- READ-ONLY: cross-check backfilled values.
SELECT count(*) AS mismatched
FROM orders
WHERE customer_note IS DISTINCT FROM customer_note_v2;
~~~

`mismatched = 0` **alone does not prove every business flow is right**; test creates/updates, null semantics, downstream consumers, indexes/queries, and spot samples. If `NULL` carries business meaning, never backfill `UNKNOWN` arbitrarily without product sign-off.

Only once every consumer has switched and the rollback window has elapsed should **contract** be considered:

~~~sql
-- DESTRUCTIVE: RUN ONLY after approval, backup, and zero-dependency confirmation.
ALTER TABLE orders DROP COLUMN customer_note;
~~~

**Dropping a column can instantly break an app code rollback.** It is never harmless "cleanup" — govern it as a high-risk change.

### 7.4. Indexing Large Tables

On a live PostgreSQL table serving traffic:

~~~sql
-- WRITE: example index build avoiding long write locks.
-- CREATE INDEX CONCURRENTLY MUST run outside an explicit transaction block.
CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

`CONCURRENTLY` still consumes CPU, I/O, time, and WAL, and can fail; if it fails, inspect index validity (an invalid index may remain) before retrying. Your Flyway/Liquibase runner must **support non-transactional statements**. For large constraints, consider PostgreSQL `NOT VALID`/`VALIDATE CONSTRAINT` where supported, rather than assuming it applies to every `UNIQUE` or `NOT NULL` case.

## 8. Migration Tooling and CI/CD

### 8.1. One Responsible Runner, Not Every Pod

A dangerous anti-pattern is having **every Cloud Run instance or GKE Pod run DDL on startup**. Rolling out 30 replicas makes dozens of processes fight over migration locks, inflates cold starts, harms API availability, and destabilizes deployment rollbacks.

Better design:

~~~text
PR: schema change
   → SQL review + static lint
   → test DB with representative data
   → take/verify backup & rollback plan
   → CI migration job (single runner with locking)
   → deploy canary app
   → verify + separate backfill job
   → full app rollout
   → contract cleanup in a later release
~~~

**Flyway/Liquibase** (or similar tools) manage versions, checksums, and migration history, yet **do not make every migration transactional or automatically rollbackable**. For non-transactional DDL, configure the runner properly and add separate validation.

### 8.2. Permissions and Credentials

- **Migration principal** needs DDL/ALTER rights in the target schema, not project Owner or PostgreSQL superuser by default.
- **Application runtime principal** usually needs only table-scoped SELECT/INSERT/UPDATE/DELETE, never schema-altering privileges.
- **CI/deployer** needs permission to invoke the migration job and `iam.serviceAccounts.actAs` where applicable, without leaking DB passwords in pipeline logs.
- Use **Secret Manager**, IAM database authentication, or another supported auth method, with key/password rotation.
- For private DB endpoints, the migration runner must have **VPC routing / Private Service Connect / Private Service Access** matching your topology; IAM without a network path still fails to connect.

If Cloud SQL/AlloyDB stores personal data, logs and SQL query texts can leak PII; redaction and log retention belong in the change plan too.

## 9. Monitoring Locks and Migration Health

### 9.1. Inspecting Long-Running Sessions

Read-only PostgreSQL examples (requires metadata viewing privileges):

~~~sql
SELECT pid, usename, state, wait_event_type, wait_event,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start ASC
LIMIT 20;
~~~

~~~sql
SELECT l.pid, l.locktype, l.mode, l.granted,
       c.relname AS relation_name
FROM pg_locks AS l
LEFT JOIN pg_class AS c ON c.oid = l.relation
WHERE l.relation IS NOT NULL
ORDER BY l.granted ASC, l.pid
LIMIT 50;
~~~

These outputs **do not show the exact blocker chain directly**; use `pg_blocking_pids(pid)` and observability tools to trace who blocks whom. Never run `pg_terminate_backend` blindly in production just because a session looks old — check whether it is a user transaction, backup, DDL, or rollback-critical process first.

### 9.2. Metrics to Watch During a Change Window

| Group | Example Signals | Action |
| --- | --- | --- |
| **Availability** | Connection errors, 5xx rates, downtime, failover events. | Check routing/reconnects; trigger runbook on SLO breach. |
| **Latency** | Query p95/p99, Cloud Run request p95, lock waits. | Pause or throttle backfill if contention rises. |
| **Capacity** | CPU, memory, disk usage/IOPS, connection counts, WAL. | Throttle migration, check pool sizing, verify quotas. |
| **Replication** | Replica/read pool health and lag. | Hold switching read traffic until data catches up. |
| **Correctness** | Rows migrated, mismatch counts, app business invariants. | Block contract phase if discrepancies remain. |
| **Recovery** | Backup status, PITR window, restore test duration. | Never start a major upgrade without a proven restore path. |
| **Cost** | Parallel DB runtime, backups/storage, logs, network transfer. | Forecast and set budget alerts. |

**A fast migration is not a good migration if checkout p99 spikes.** Measure business SLIs, not just DDL execution time.

## 10. Production Scenario: Retail System

### 10.1. Objectives

- `orders-db`: Cloud SQL for PostgreSQL primary/HA serving checkout; read replica for reporting.
- `analytics-db`: AlloyDB primary and read pool for analytics.
- Cloud Run runs `orders-api`; GKE runs billing workers.
- The team wants to add `customer_note_v2` and schedule an engine upgrade outside peak shopping hours.
- Checkout SLO: **99.95% availability** (assumed) with p95 under 300 ms; every change must be measurable and staged for rollback.

### 10.2. Safe Change Schedule

| Timing | Task | Gate to Proceed |
| --- | --- | --- |
| **T-14 days** | Inventory engine versions, extensions, replication/CDC, maintenance schedules, and workload. | Assigned owner, change ticket, rollback plan. |
| **T-10 days** | Restore backup to lab/staging; run migration and load tests. | Data correctness and stable p95. |
| **T-7 days** | Configure maintenance notifications; confirm off-peak window. | On-call SRE and live alerts ready. |
| **T-3 days** | Expand schema; deploy dual-write / read-fallback app code. | Both old and new code run cleanly. |
| **T-2 days** | Run throttled backfill; monitor WAL, locks, and replica lag. | Mismatches resolved, zero SLO breaches. |
| **T-1 day** | Switch readers, test business flows and app code rollback. | Zero remaining consumers on old column before later contract. |
| **Upgrade day** | Perform **major upgrade separately**, without bundling breaking DDL. | Backup/restore plan, maintenance window, and monitoring verified. |
| **Post-stabilization** | Run `ANALYZE`, acceptance tests, inspect lag/CDC, close change. | Zero errors and acceptable cost metrics. |

This is an **illustrative schedule**, not a guaranteed product maintenance SLA. Splitting schema rollouts and major engine upgrades into **two independent changes** makes root-cause isolation far easier if anything breaks.

### 10.3. Scenario: "Code Deployed Yet Migration Stuck on Lock"

Suppose an `ALTER TABLE` DDL statement waits on a lock during peak traffic:

1. **Halt further deployments** and record the migration ID/SQL and start time.
2. Inspect `pg_stat_activity`, `pg_locks`, `pg_blocking_pids`, and API 5xx/p95 impact.
3. If only **expanding a nullable column**, safely cancel the migration or shed traffic per plan rather than killing every session.
4. Revert the app to a compatible revision if needed; **never run `DROP COLUMN`** during an incident.
5. Reschedule off-peak with adjusted timeouts, batching, or DDL strategy.

### 10.4. Scenario: "Major Upgrade Succeeded Yet JDBC Fails"

If the DB major upgrade completes yet Java drivers or SQL queries throw errors:

- Check driver compatibility and changed PostgreSQL defaults/behaviors.
- Shed or pause traffic per runbook; test a compatible app build.
- If rapid remediation fails, evaluate **restoring the pre-upgrade backup to a new instance/cluster** and redirecting endpoints cleanly.
- Account for **writes committed after that backup**; never assume restoring to the old version preserves post-backup writes automatically.

**Returning to an older engine version is completely different from rolling back a Kubernetes Deployment.** Never attempt an unsupported in-place downgrade.

## 11. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Investigation Steps |
| --- | --- | --- |
| `connection reset` during maintenance | Connections severed during component switchover. | Logs, connection pool, retries/idempotency, maintenance events. |
| App 5xx stays high after DB shows READY | Pool holds stale sockets, DNS/route issue, or replica lag. | Pool metrics, DB connections, endpoints, replica status. |
| Cannot set Cloud SQL deny period | Maintenance version too old, invalid duration/format. | Check maintenance version, 90-day cap, update requirement. |
| AlloyDB 60-day deny period rejected | AlloyDB caps at 30 days or version too old. | Check cluster maintenance policy/docs. |
| Cloud SQL major upgrade precheck fails | Unsupported extensions/flags, incompatible replication/objects. | `upgradableDatabaseVersions`, upgrade logs, precheck items. |
| AlloyDB major upgrade takes hours | Large data/schema/read pools; precheck or upgrade phases. | Upgrade status, Cloud Logging, topology guidance. |
| Queries slow after major upgrade | Stale planner stats, changed flags/defaults, index/extension changes. | `ANALYZE`, `EXPLAIN (ANALYZE, BUFFERS)` in safe env, metrics. |
| Migration hangs for minutes | DDL lock blocked by long-running transactions. | `pg_stat_activity`, `pg_locks`, blocker chain, `lock_timeout`. |
| Old app revision fails with `column does not exist` | Dropped/renamed before all consumers shifted. | Schema history, active revisions, rollback compatibility. |
| `CREATE INDEX CONCURRENTLY` fails | Executed inside transaction, low disk, or conflict/timeout. | Runner config, index validity, logs; do not blindly retry. |
| Replica/CDC falls behind | WAL spike from backfill, logical slot, or post-upgrade topology. | Replication lag, slots, worker throughput. |
| Code rollback doesn't fix outage | Breaking schema change or completed major upgrade. | Identify point of no return, execute DB backup/recovery plan. |

## 12. Exercises

### Exercise 1 — Classifying Changes

Classify these four events: (a) Cloud SQL receives a maintenance patch; (b) PostgreSQL 15 → 16; (c) adding an index on `orders`; (d) upgrading the Java JDBC driver. Which can cause downtime? Which fall outside Cloud SQL's `maintenance window`?

### Exercise 2 — Maintenance Windows and Time Zones

The checkout team wants maintenance at **02:00 AM Sunday Vietnam time**. What day and hour is that in `gcloud` UTC flags? Distinguish Cloud SQL `Week 1` vs. `Week 2`, and explain why production should never take patches first.

**Hint:** 02:00 Sunday ICT = **19:00 UTC Saturday**, not 02:00 UTC Sunday.

### Exercise 3 — Deny Periods

A team wants a 45-day maintenance freeze during peak season across both Cloud SQL and AlloyDB. Can they apply the same config to both? Cite the 90/30-day limits, version prerequisites, and patching risks.

### Exercise 4 — Reconnects and Idempotency

Cloud SQL drops connections right after an order-creation transaction **may have committed**, before the app receives confirmation. The client retries `POST /orders`. Describe operation IDs, unique constraints, pre-retry status checks, and backoff so duplicate orders are never created.

### Exercise 5 — Major Upgrade

A Cloud SQL PostgreSQL 15 instance has read replicas and Datastream logical replication. Build a checklist covering prechecks, backups, extensions/slots, upgrade order, read replica lag, and post-upgrade validation on a supported target version. Why isn't rollback just patching the database version back down?

### Exercise 6 — Expand-Contract

Table `orders` has 100 million rows, and old app versions read `customer_note`. Design the steps to roll out `customer_note_v2`, covering dual-writes, batched backfill, mismatch verification, and when it is safe to drop the old column.

### Exercise 7 — `CREATE INDEX CONCURRENTLY`

Why consider `CREATE INDEX CONCURRENTLY` on a live PostgreSQL table? Can it run inside a transaction block? When it fails, why shouldn't you blindly retry?

### Exercise 8 — Runbooks and SLOs

An AlloyDB primary/read pool is preparing for a major version upgrade. The SLO caps write downtime at 5 minutes, yet staging took 30 minutes. Should you run an in-place upgrade on production? Propose parallel migration, change window, app cutover, and recovery plans instead.

## 13. Production Checklist and Official Documentation

| Area | What Must Be Verified |
| --- | --- |
| **Maintenance** | Correct product/instance/cluster, UTC window, rollout timing, notifications, valid deny period. |
| **Versions** | Current engine major/minor, supported target, extensions, flags, drivers, replication/CDC. |
| **Availability** | HA/read pools, connection pools, timeouts, reconnects, retries + idempotency, SLO. |
| **Backups** | Automated/on-demand backups and PITR scoped properly; restores rehearsed and RTO/RPO measured. |
| **Schema** | Expand-contract, SQL review, migration locks, batched backfill/validation, no premature DROPs. |
| **Release** | Single migration runner, schema history, IaC/change approval, canary and fallback app revision. |
| **IAM/network** | Least-privilege migration principal, separate runtime SA, VPC/PSC/PSA routes, safe secrets. |
| **Observability** | DB connections, locks, replica lag, CPU/IO, app 5xx/p95, audit/change logs. |
| **Recovery** | Clear distinction between code-rollbackable steps and DB restore + endpoint cutover. |
| **Cost** | Staging/parallel instances, backups, storage/WAL, replicas, logging, and downtime cost. |

Official documentation for version- and edition-specific limits:

- [Cloud SQL for PostgreSQL — Maintenance overview](https://cloud.google.com/sql/docs/postgres/maintenance)
- [Cloud SQL — View and set maintenance windows](https://cloud.google.com/sql/docs/postgres/set-maintenance-window)
- [Cloud SQL — Self-service maintenance](https://cloud.google.com/sql/docs/postgres/self-service-maintenance)
- [Cloud SQL — Major version upgrade in-place](https://cloud.google.com/sql/docs/postgres/upgrade-major-db-version-inplace)
- [Cloud SQL — Major upgrade by migration](https://cloud.google.com/sql/docs/postgres/upgrade-major-db-version-migrate)
- [Cloud SQL — Back up and recover](https://cloud.google.com/sql/docs/postgres/backup-recovery/backup-options)
- [AlloyDB — Maintenance overview](https://cloud.google.com/alloydb/docs/maintenance)
- [AlloyDB — Maintenance windows and deny periods](https://cloud.google.com/alloydb/docs/maintenance-windows)
- [AlloyDB — Database version policies](https://cloud.google.com/alloydb/docs/db-version-policies)
- [AlloyDB — Major version upgrade overview](https://cloud.google.com/alloydb/docs/major-version-upgrade-inplace-overview)
- [AlloyDB — Perform major version upgrade](https://cloud.google.com/alloydb/docs/upgrade-db-inplace-major-version)
- [AlloyDB — Backups and PITR](https://cloud.google.com/alloydb/docs/backup/overview)
- [PostgreSQL — Explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html)

**Key takeaway:** **Maintenance** is platform-managed patching where apps must still survive dropped connections; **major engine upgrades** require dedicated compatibility testing and recovery plans; **schema migrations** must stay compatible across app revisions, bound DDL locks, and backfill in batches. On Cloud SQL and AlloyDB, never equate HA with zero downtime or app code rollback with database downgrade. The goal is **verifiable upgrades, rehearsed recovery, and staying within both SLO and budget**.

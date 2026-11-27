# Deploying Database Changes Alongside Application Versions

A Spring Boot release often changes more than Java code alone. For example, an e-commerce application might rename the column **customer_name** to **display_name**, add an order status, and backfill existing rows to a new format. If the team alters the database schema and deploys the app **at the exact same instant** incompatibly, users hit HTTP 500 errors during a rolling deployment while old and new instances still serve concurrently. Conversely, deploying the code first before the new column exists can crash application startup immediately.

This is the **database change deployment** challenge, part of the **CI/CD and Software Supply Chain** chapter in the **CLOUD_PROVIDERS_AZURE** module. Across learning Azure from subscriptions, resource groups, and Microsoft Entra ID through virtual networking, compute, storage, data, security, monitoring, and cost, we must treat **database schema, data, application, migration scripts, and pipeline** as one governed unit of change. This lesson focuses on Azure SQL Database and Azure Database for PostgreSQL, Java/Spring Boot, Flyway/Liquibase, Azure App Service, Azure Container Apps, AKS, GitHub Actions, and Azure Pipelines. Most principles apply to other RDBMSs, though DDL statements, transaction semantics, locking, and rollback depend on the database engine.

**Key takeaway:** deploying **the same release** does not mean executing **DDL and swapping all application instances in the same second**. A safe release usually spans ordered steps that temporarily run **two application versions** against **one transitional schema**. Every intermediate state must keep working or use controlled traffic isolation.

Examples use **synthetic data**, a hypothetical ordering system, and SQL statements that must be verified against your real engine, version, and SKU. Endpoints, resource names, IAM roles, service limits, and pricing vary by region and plan. Never run sample migrations against production or real customer data without approvals, tested backups/restores, and a recovery plan.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **application version**, **schema version**, **data migration**, and **deployment state**.
2. Identify **backward-compatible**, **forward-compatible**, and **breaking** changes.
3. Design an **expand → migrate/backfill → switch → contract** plan to minimize downtime.
4. Use **Flyway** or **Liquibase** to manage migration scripts alongside code in version control.
5. Structure a **single migration runner** in CI/CD, avoiding multiple replicas racing to run DDL.
6. Write migrations with **safe constraints**, versioning, and schema/history validation.
7. Distinguish **schema migration, data backfill, and database restore**.
8. Coordinate database changes with **App Service slots, Container Apps revisions, and AKS rolling updates**.
9. Design **pre-deployment compatibility tests, staging rehearsals, approvals, and release gates**.
10. Manage **Microsoft Entra identities, data-plane permissions, private networking, Key Vault, and secrets**.
11. Know when **rolling back the app** is safe versus when you must **roll forward** the database.
12. Monitor lock waits, replication, errors, migration duration, and business invariants.
13. Build an **incident runbook and recovery plan** for failed migrations.
14. Analyze cost, downtime budgets, and operational ownership within a release.

## 2. A single release spans multiple states

Suppose you have:

~~~text
orders-api v1  <----> database schema S1
orders-api v2  <----> database schema S2
~~~

It looks like a simple switch **v1/S1 → v2/S2**. In reality:

~~~text
T0: all replicas run v1, database S1
T1: migration starts; app v1 still serves requests
T2: some instances run v2, some run v1
T3: all instances run v2
T4: legacy data continues backfilling/normalizing
T5: after a safe window, unused schema elements are removed
~~~

At every point, answer:

- **Can app v1 still read/write the current schema?**
- **Can app v2 run before legacy data finishes backfilling?**
- **Are older requests or workers still processing?**
- **If v2 rolls back to v1, is the schema still compatible?**
- **Are old-format messages or cron jobs still waiting in queues?**

Otherwise, a release reported as "successfully deployed" by CI/CD can still corrupt business operations.

## 3. Four version layers to manage

| Layer | Example | Critical question |
|---|---|---|
| **Application** | `orders-api` v1.8.0/v1.9.0 | Which code reads/writes which fields? |
| **Schema** | Flyway V15, V16 | Which tables, columns, indexes, and constraints exist? |
| **Data** | 60% of customers have `display_name` | How far has legacy data conversion progressed? |
| **Contract/API/event** | REST v2, Service Bus event schema 3 | Do older consumers/workers still accept old formats? |

### Schema version is not the application release number

An application release might:

- Include zero schema migrations.
- Include several consecutive SQL migrations.
- Read a new schema without writing to it yet.
- Simply flip a feature flag or backfill data.

Hence **orders-api v2.0.0 does not have to equal Flyway V2**. Never hardcode an "app version = schema version" rule when multiple services share a database.

### Migration history

Flyway/Liquibase track applied scripts in a history table per product mechanics—e.g., Flyway uses **flyway_schema_history**. That table proves which migrations the tool recorded; **it does not prove all data was transformed accurately** if backfills ran outside the migration.

## 4. Compatibility: the most important rule

Database changes fall into three categories:

| Change | Usually compatible with old app? | Notes |
|---|---|---|
| Add a **nullable** column without changing old code | Usually yes | Check triggers, ORM `SELECT *`, and write patterns |
| Add a new table | Usually yes | Check permissions and data model |
| Add an index | Usually yes logically | Can cause locks, IO, and cost |
| Add `NOT NULL` constraint immediately | Can break | Old rows and old writers omit the field |
| Rename a column | Usually breaks | Old app SQL/ORM queries the old name |
| Drop a column | Breaks if old app still uses it | Requires a contract phase |
| Change type/precision | Can break | Truncation, conversion, locking |
| Change enum/status semantics | Can break | Old app misinterprets new values |
| Drop table/foreign key | Can break | Audit readers/writers and business invariants |

**"Usually yes" is not an absolute guarantee.** An app running native **`SELECT *`** queries mapped by column position—or strict ORM schema validation—can break even on an additive column.

### Two compatibility directions

- **Backward compatibility:** the new schema still serves the older application version.
- **Forward compatibility:** the new application still handles legacy data and state during the transition.

Rolling updates, blue-green cutovers, and rollbacks demand both directions at different moments. Without explicit design, **passing staging with a single app version running** fails to test mixed-version compatibility in production.

## 5. Why "ALTER TABLE then deploy" is dangerous

Example:

~~~sql
-- Initial schema:
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

App v1:

~~~sql
SELECT id, customer_name
FROM customers
WHERE id = 1001;
~~~

If you deploy directly:

~~~sql
ALTER TABLE customers RENAME COLUMN customer_name TO display_name;
~~~

then **v1 still running** during migration or rollback fails because **customer_name** vanished. Conversely, if v2 expects **display_name** before the schema updates, v2 fails before migration finishes.

### Additional risks beyond SQL errors

- DDL acquires **schema/table locks**, blocking queries.
- Application connections cache prepared statements/execution plans.
- Connection pools may retain stale metadata mappings.
- Old worker messages still carry old fields.
- Deployments stalling mid-way leave a **half-migrated state**.
- Feature flags enabled before backfills finish.
- Mis-timed backup/restore operations wiping newly written rows.

The reliable fix is **splitting the change into compatible phases**, not merely "running SQL faster."

## 6. The Expand → Migrate → Contract model

~~~mermaid
flowchart LR
    A[App v1 + schema S1] --> B[Expand: add compatible schema elements]
    B --> C[Transitional app: reads/writes support both forms]
    C --> D[Backfill and verify]
    D --> E[Switch reads + complete rollout]
    E --> F[Observe and wait out rollback window]
    F --> G[Contract: remove legacy columns/code]
~~~

### Expand

Add new structures **without removing anything the old app still needs**—for example, adding a **nullable `display_name`**, a new index, or a new table. App v1 keeps running cleanly.

### Migrate

Update code to read/write the new form, backfill legacy data in batches, track progress, and check for discrepancies. Define the **source of truth** and how concurrent updates are reconciled during this window.

### Switch

Once data is sufficiently complete, shift read paths or feature flags to the new field. Run tests, monitor errors, and keep the ability to revert to old code while the schema remains compatible.

### Contract

Only after confirming **zero apps, workers, reports, queries, or ETL jobs** still use the legacy structure—and after the rollback window closes—drop old columns, indexes, triggers, or compatibility code. **Contract is a breaking change** and must be reviewed as its own release.

**All four phases do not belong in one single pipeline run.** For large datasets or multi-service setups, contraction may happen days or weeks later. In an initial release, safely deploying app v2 and expanded schema S2 already achieves the goal without rushing to drop the legacy column.

## 7. Running example: renaming `customer_name` to `display_name`

**Business goal:** modernize customer naming so the backend uses **display_name** without disrupting running `orders-api` v1 instances or legacy workers reading queued messages.

Initial schema:

~~~sql
-- Illustrative PostgreSQL:
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### Wrong plan

1. Rename the column.
2. Deploy v2.
3. If deploy fails, roll code back to v1.

**Problem:** step 1 immediately breaks v1; rolling back code does not restore the old column name. There is no safe intermediate state during rollout.

### Better plan

1. **Expand:** add nullable `display_name`; do not rename or drop.
2. **Transitional release:** app reads `display_name` if present, falling back to `customer_name`, while continuing to maintain legacy data.
3. **Backfill:** copy/transform existing rows in batches.
4. **Switch:** new readers prefer `display_name` with consistency checks enforced.
5. **Contract:** once old apps/workers are gone and the rollback window closes, drop `customer_name`.

**Note:** if both fields can be updated concurrently, a single backfill pass is insufficient. Use **controlled dual-writes, reviewed database triggers, or a single canonical source** synchronized throughout the transition.

## 8. Expand migration: adding a nullable column

In PostgreSQL:

~~~sql
-- Example Flyway V2026112001__add_display_name.sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(200);
~~~

### Why nullable?

If app v1 still inserts customers without supplying **display_name**, a **`NOT NULL` column without a default** breaks v1 `INSERT`s. Nullable columns let both versions coexist during transition.

### Does not mean lock-free DDL

PostgreSQL **`ALTER TABLE`** still acquires locks even for fast metadata-only changes. It can wait behind long-running transactions and queue subsequent queries while waiting. On busy systems, set a **`lock_timeout`** policy, rehearse, measure lock waits, and plan retries/approvals.

### Do not assume `IF NOT EXISTS` is always safe

~~~sql
-- Illustrates engine-supported syntax only:
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(200);
~~~

This syntax avoids errors on manual re-runs, yet **does not replace migration history and version checks**. It can mask drift—for example, a column already existing with the wrong type or constraints. With Flyway versioned migrations, prefer managed state and schema validation.

## 9. Transitional application: reading data safely

Read the new field first and fall back to the old field:

~~~sql
SELECT
    id,
    COALESCE(display_name, customer_name) AS effective_display_name
FROM customers
WHERE id = :id;
~~~

With Spring Data JPA, keep **entity mappings** compatible with the expanded schema:

~~~java
package com.example.orders;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class CustomerEntity {
    @Id
    private Long id;

    @Column(name = "customer_name", nullable = false)
    private String legacyName;

    @Column(name = "display_name")
    private String displayName;

    public String effectiveDisplayName() {
        return displayName != null ? displayName : legacyName;
    }

    // Constructors/getters/setters omitted for brevity.
}
~~~

This is an **entity skeleton** omitting repositories, validation, auditing, tenant checks, and accessors. Crucially, **transitional app v2 starts only after `display_name` exists**, yet cleanly handles unbackfilled legacy rows.

### What if migrations cannot deploy before the app?

You can deploy an intermediate bridge app that does not touch the new field yet, then run the migration afterward. Design an explicit compatibility matrix for that path. Never assume JPA/Hibernate will boot if an entity maps a column that does not exist yet.

## 10. Writing data while two versions coexist

During transition, **app v1** still writes `customer_name`. App v2 can write both:

~~~text
v1 writer -> customer_name only
v2 writer -> customer_name + display_name
v2 reader -> display_name if present, else customer_name
~~~

### A simple rule

While v1 and v2 coexist, treat **`customer_name` as the canonical write source** and maintain `display_name` as a mirror with explicit consistency rules. If v2 lets users update `display_name` while v1 updates `customer_name`, updates can overwrite each other out of order.

### Updating within one database transaction

~~~sql
UPDATE customers
SET customer_name = :new_name,
    display_name = :new_name,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :customer_id;
~~~

**Updating two columns in one `UPDATE`** is atomic inside that DB transaction, yet **does not ensure v1 legacy writes also update `display_name`**. To stay synchronized while v1 writers remain active:

1. Ensure each customer is edited only through upgraded writers, **or**
2. Add a **reviewed, tested trigger/compatibility layer**, **or**
3. Accept that the new field may lag and keep reading the canonical legacy field until all v1 writers upgrade and reconciliation completes.

In many systems, the safest path is **deploying dual-write code (still reading the legacy field) to all replicas first**, then backfilling, and only then switching reads.

## 11. Backfill migrations: never lock large tables

On huge tables, a single full-table `UPDATE` causes lock contention, WAL/transaction log bloat, replica lag, and cost spikes.

~~~sql
-- Illustrative for small tables / test data only:
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;
~~~

Large production tables need a **checkpointed backfill job** using small batches and load throttling.

### Keyset cursor backfill pattern

~~~text
Start cursor = 0
  |
  +-- Select next N IDs > cursor
  +-- Update only corresponding rows when safe
  +-- Commit one batch
  +-- Persist cursor and counts
  +-- Sleep/throttle on DB pressure
  +-- Repeat until no eligible rows
~~~

**Never build backfills using large `OFFSET` pagination** on mutating tables assuming every row is visited once. Persistent keyset/cursor pagination is easier to control, though you must still handle concurrent inserts, updates, and retries.

### Reconciliation

After each pass, verify:

~~~sql
SELECT COUNT(*) AS missing_new_name
FROM customers
WHERE display_name IS NULL;

SELECT COUNT(*) AS inconsistent_name
FROM customers
WHERE display_name IS NOT NULL
  AND display_name <> customer_name;
~~~

Both queries assume the **business rule** that both columns must match. If **display_name** allows nicknames distinct from `customer_name`, do not treat every difference as corruption; define domain-specific mapping and normalization checks instead.

## 12. When to switch and contract?

### Conditions to switch the read path

- All writers have upgraded or sync mechanisms are active.
- Backfill finished per acceptance thresholds.
- Missing and mismatch counts are stable.
- v2 reads `display_name` accurately across new and legacy records.
- API/event consumers understand the new field when enabled.
- Feature flags and rollback plans are verified.

### Contracting after the rollback window

~~~sql
-- Run only in an approved contract release;
-- never run immediately after expand:
ALTER TABLE customers
    DROP COLUMN customer_name;
~~~

**Logically, this is a breaking change.** Before executing, audit every SQL query, JPA mapping, reporting job, ETL pipeline, backup/restore script, older container revision, slot, and worker still referencing the legacy column.

### A safe release timeline

~~~text
R1: Expand schema + app compatible with both columns
R2: Complete writer rollout + backfill + verify
R3: Switch reads to new column + monitor
R4: Contract legacy column after rollback window
~~~

Do not hardcode exactly one week between releases; decide based on **telemetry, client inventory, and risk**, not calendar dates alone.

## 13. Flyway: versioned migrations under source control

**Flyway** tracks database migrations using versioned, named, checksummed scripts. In Spring Boot projects, SQL migrations typically reside at:

~~~text
src/main/resources/db/migration/
  V1__create_customers.sql
  V2__create_orders.sql
  V3__add_display_name.sql
  V4__add_order_status.sql
~~~

### Basic mechanics

1. Tool connects to the database with its assigned identity/credentials.
2. Inspects the schema history table (if managed by Flyway).
3. Reads versions and checksums of migration scripts.
4. Applies unapplied migrations in supported order.
5. Records migration status and errors in the history table.
6. Never arbitrarily reruns a previously succeeded versioned migration.

### Naming conventions

Examples:

~~~text
V2026112001__add_customers_display_name.sql
V2026112002__create_order_outbox.sql
V2026112003__add_order_status_index.sql
~~~

Separate version and description with a double underscore per Flyway convention. Standardize one versioning scheme across the team; **never edit a migration already applied to production**, as checksums and audit histories will mismatch. For follow-up changes, create a new versioned migration unless an approved repair/rebaseline procedure is explicitly invoked.

### Watch out for

- Flyway does not automatically verify **backward compatibility**.
- Migration history does not replace backups or data checks.
- Valid DDL can still hold blocking locks.
- Engine-specific SQL may fail across different database engines.
- Depending on Flyway version, database drivers/modules may require extra dependencies; check official docs.
- Never run **`clean`** against production simply because local tests use `clean`.

## 14. Flyway with Spring Boot: baseline configuration

Sample Maven dependencies using Spring Boot dependency management:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
  </dependency>
  <dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-core</artifactId>
  </dependency>
  <dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
  </dependency>
</dependencies>
~~~

In newer Flyway releases, PostgreSQL support lives in a dedicated module such as **flyway-database-postgresql**. If your project uses such a version, include the module matching your Flyway BOM:

~~~xml
<dependency>
  <groupId>org.flywaydb</groupId>
  <artifactId>flyway-database-postgresql</artifactId>
</dependency>
~~~

**Never copy dependencies blindly without verifying the Spring Boot–Flyway–JDBC compatibility matrix**, edition/license features, and actual Maven dependency management.

### Local Spring profile

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_lab
    username: orders_lab
    password: PLACEHOLDER_FROM_SECRET_PROVIDER
  flyway:
    enabled: true
    locations: classpath:db/migration
    validate-on-migrate: true
~~~

In production, **never commit real passwords**; use secret providers or secure runtime injection and separate local configs. Dedicated migration pipelines can set **`spring.flyway.enabled=false`** on the Spring Boot app to prevent multiple replicas from migrating concurrently, while a standalone runner executes the same Flyway scripts with dedicated schema privileges.

### Never let Hibernate auto-alter production schemas

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

With JPA/Hibernate, **`validate`** catches mapping/schema mismatches checked by Hibernate, **though it does not guarantee full compatibility** with native queries, triggers, or business invariants. Avoid **`ddl-auto=update/create/create-drop`** in production so migrations maintain explicit history, reviews, and deployment ordering.

## 15. Liquibase: changeSets, checksums, and rollbacks

**Liquibase** tracks changes via **changeSets** authored in XML, YAML, JSON, or SQL depending on version/support. Illustrative YAML changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: add-customer-display-name
      author: orders-team
      changes:
        - addColumn:
            tableName: customers
            columns:
              - column:
                  name: display_name
                  type: varchar(200)
      rollback:
        - dropColumn:
            tableName: customers
            columnName: display_name
~~~

**This is only a lab example of a rollback clause**, not a recommendation to auto-run `dropColumn` during production rollbacks. Once the column holds data, that rollback **deletes data** with no automatic recovery. In production, destructive reversals require separate impact reviews and backup/restore plans.

### Core concepts

- **DATABASECHANGELOG** records applied changeSets.
- **DATABASECHANGELOGLOCK** handles Liquibase coordination/locking.
- **Preconditions** validate assertions before running a changeSet.
- **Checksums** detect edits to previously applied changeSets.
- **Rollback definitions** help for certain changes, but do not make every migration safely reversible.

### Flyway or Liquibase?

| Criterion | Flyway | Liquibase |
|---|---|---|
| Familiar model | Versioned SQL scripts | Changelogs/changeSets in SQL or DSL |
| Database-specific SQL | Explicit, straightforward to review | Supports raw SQL and structured change types |
| Schema history | Schema history table | Changelog tables |
| Rollback | Forward migrations are usually the safe default | Supports rollback clauses per change type |
| Coordination | Migration locking per engine/version | Changelog lock |
| Operational needs | Requires credentials, pipeline, and testing | Requires credentials, pipeline, and testing |

Pick **one canonical tool per database/schema boundary** unless executing a planned tool migration; running Flyway and Liquibase independently on the same schema without clear ownership causes drift and race conditions.

## 16. Who is authorized to run migrations?

A common anti-pattern: **every Spring Boot replica runs Flyway on startup** concurrently during a rolling update.

~~~text
Old replicas: v1 v1 v1
                 |
Deploy v2:       +-- v2 Pod A -> Flyway migrate
                     v2 Pod B -> Flyway migrate
                     v2 Pod C -> Flyway migrate
~~~

Migration tools provide locking/tracking, yet **should not substitute for release orchestration**. Pods can block startup waiting on locks, HPA may spawn extra pods, health probes time out, and DDL permissions end up distributed to every app instance.

### Recommended model: a single migration runner

~~~mermaid
flowchart TD
    A[CI build + test] --> B[Migration artifact / scripts immutable]
    B --> C[Staging migrate + integration tests]
    C --> D[Production approval]
    D --> E[One-shot migration runner]
    E --> F{History + invariants PASS?}
    F -- No --> G[Stop app rollout + incident]
    F -- Yes --> H[Roll out app version]
    H --> I[Smoke + monitor]
~~~

**A single migration runner** can be a CI/CD deployment job with private network access, an AKS Kubernetes Job, an ACA Job, or an approved automation host—not necessarily an application pod. The runner holds schema privileges only while needed; the runtime app uses a **least-privileged DML identity**.

### When running Flyway on Spring startup is acceptable

Acceptable in a **managed lab/single-instance** setup or small low-risk systems, whereas multi-replica production requires analyzing startup contention and least privilege. For releases with breaking migrations, uncoordinated startup migrations are even riskier because timing is uncontrolled.

## 17. Are migrations truly exactly-once?

Migration frameworks enforce state and locking at their own level, but cannot guarantee **every SQL/data backfill inside** executes exactly-once across every engine and crash mode.

Example:

~~~text
Job starts
  -> ALTER TABLE succeeds
  -> Backfill writes 70% rows
  -> Process crashes
  -> Job retries
~~~

If DDL is non-transactional or backfills run outside migration transactions, state may be left partially applied.

### Why idempotency matters

- Migrations must detect which changes already applied.
- Rerunning a backfill must never duplicate data.
- Unique constraints prevent duplicates on retry.
- Checkpoints/sentinels must match committed durable writes.
- Partial failures require **reconciliation** and runbooks.

**Never reuse one migration version to blindly rerun non-idempotent `UPDATE`s** without understanding tool state. Large datasets warrant a dedicated backfill job with **job version, cursor, batched transactions, and monitoring**.

## 18. Transactional DDL: PostgreSQL vs. Azure SQL differ

**Azure Database for PostgreSQL – Flexible Server** follows PostgreSQL semantics: many DDL statements run inside transactions, though **not all**. **Azure SQL Database** uses SQL Server/T-SQL with different transaction/DDL rules, locking, and online operation support.

| Operation | PostgreSQL | Azure SQL Database |
|---|---|---|
| Add column | `ALTER TABLE ... ADD COLUMN` | `ALTER TABLE ... ADD ...` |
| Low-lock indexing | `CREATE INDEX CONCURRENTLY` where supported | Online/resumable index operations per tier/SKU/option |
| Transactional behavior | Many DDL statements transactional, with exceptions | Depends on statement/engine restrictions |
| Locking | Table/relation locks, MVCC, waits | Schema modification locks, transaction/log/lock waits |
| Monitoring | `pg_stat_activity`, `pg_locks`, metrics | `sys.dm_*` views, Query Store/metrics |
| Migration strategy | Batches, `lock_timeout`, transaction control | Batches, lock timeout/config, index options |

**Never copy PostgreSQL SQL straight onto Azure SQL**, or copy SQL Server **`WITH (ONLINE = ON)`** without verifying your actual SKU/features. Test migration scripts on the exact target engine, version, and production-like configuration.

### DDL can block application traffic

An **`ALTER TABLE`** finishing instantly on 100 local rows can stall for minutes in production behind long-running transactions or lock queues. Test **transaction duration, lock acquisition, WAL/transaction log growth, CPU/IO, and replica lag** under realistic conditions.

## 19. PostgreSQL: concurrent indexing

Suppose we add an index on `orders`:

~~~sql
-- PostgreSQL:
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON orders (customer_id, created_at);
~~~

### Why use `CONCURRENTLY`?

It avoids blocking normal reads and writes compared to standard index builds, though it **takes longer, uses more IO**, and has restrictions.

**Important:**

- PostgreSQL **`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block**.
- Flyway migrations normally run inside transactions by default; configure a non-transactional migration per Flyway version/settings.
- If concurrent index creation fails, it can leave an **invalid index** requiring catalog inspection and cleanup per runbook.
- **Never promise zero locks**: brief lock waits and performance impacts still occur.

### Inspecting indexes post-release

~~~sql
-- Illustrative PostgreSQL: inspect index state in pg_index
SELECT
    c.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
WHERE c.relname = 'idx_orders_customer_created';
~~~

This checks PostgreSQL catalog state; verify exact table/index names and query permissions. An index existing in the catalog **does not prove the query planner uses it**; verify with `EXPLAIN (ANALYZE)` in a safe environment and track query latency.

## 20. Azure SQL Database: adding columns, indexes, and Query Store

Illustrative T-SQL:

~~~sql
-- Azure SQL Database: SQL Server syntax, not PostgreSQL.
ALTER TABLE dbo.Customers
ADD DisplayName NVARCHAR(200) NULL;
~~~

Then, if an index is needed:

~~~sql
CREATE INDEX IX_Customers_DisplayName
ON dbo.Customers (DisplayName);
~~~

**Never execute immediately on large tables without evaluating locks, IO, and query plans.** On Azure SQL, inspect **Query Store**, wait statistics, DTU/vCore utilization, and online/resumable index support for your tier/SKU before deciding how to deploy.

### Do not treat `WITH (ONLINE = ON)` as a universal recipe

`ONLINE`/`RESUMABLE` options and supported index/operation types depend on engine tier and design constraints. A statement supported in one tier may fail in another. Check **current Azure SQL documentation + actual SKU** beforehand.

### Schema ownership

If Spring Boot queries **`dbo.Customers`**, the migration runner needs `ALTER` permissions on the schema, while **the application runtime user** does not need `ALTER TABLE`. Separating credentials/roles limits damage if the API is compromised.

## 21. Data backfills and semantic shifts

Renaming **`display_name`** is a simple example. Real data migrations may:

- Convert **money** from floating point to **DECIMAL/NUMERIC**.
- Normalize timestamps from local time to UTC.
- Split **address** strings into structured fields.
- Change status enums or merge legacy statuses.
- Add **tenant_id** for partitioning/multi-tenancy.
- Migrate data across two databases or storage services.

### Valid SQL execution is not enough

For currency:

~~~text
Old: total_amount_float = 19.999999
New: total_amount_minor_units = 2000
~~~

Define **rounding modes, currency exponents, and legal/accounting rules**, reconcile totals, and handle edge cases. A bare **`CAST(...)`** does not guarantee financial accuracy.

### New writes during backfill

Suppose backfilling 1 million rows takes 30 minutes while the app keeps creating records. Ensure you know:

- Are new rows written into the new schema?
- Can legacy writers overwrite already-migrated rows?
- Can cursor pagination skip rows inserted mid-job?
- Do triggers or dual-writes cause loops or conflicts?
- Does the backfill have proper retries and monitoring?

**Never treat "backfill job completed" as done without reconciling business invariants.**

## 22. Designing a checkpointed backfill job

An ideal job tracks:

~~~text
backfill_version = customer-display-name-v1
cursor           = last_committed_customer_id
batch_size       = 1000 (hypothetical; benchmark first)
status           = RUNNING / PAUSED / FAILED / DONE
rows_processed   = monotonic counter
rows_updated     = count of successful writes
error_count      = monitored
~~~

### Pseudocode

~~~text
repeat:
  if DB overloaded / maintenance window exceeded:
      pause safely

  begin transaction
      rows = fetch next batch by stable key > cursor
      update rows needing transformation, preserving concurrent writes
      persist committed cursor / counts
  commit

  emit metrics/logs with no sensitive payload
until no more eligible rows

re-run reconciliation over full eligible population
~~~

**Store the cursor and row updates in the same transaction** when within the same database and design permits, preventing the cursor from advancing ahead of writes. Across multiple services, implement explicit idempotency, sagas, and checkpoints.

### Large vs. small batches

Large batches lower round-trip overhead but increase lock duration, WAL/log pressure, and rollback cost. Small batches cut contention at the cost of more round-trips; size batches against **lock waits, replication lag, CPU/IO, and latency SLOs** in staging/load rehearsals.

## 23. `NOT NULL`, `UNIQUE`, and foreign key constraints

Adding constraints immediately during deployment can break existing rows or older app writers.

### Phased `NOT NULL`

1. Expand: add nullable column.
2. Upgraded writers begin populating the field.
3. Backfill historical rows.
4. Verify missing count = 0 and application logic.
5. Retire legacy writers and wait out the rollback window.
6. Add the `NOT NULL` constraint using your engine's lowest-lock supported approach.

### Phased `UNIQUE`

Before adding a unique index, check for duplicates first:

~~~sql
-- Illustrative PostgreSQL:
SELECT lower(email) AS normalized_email, COUNT(*) AS n
FROM customers
GROUP BY lower(email)
HAVING COUNT(*) > 1;
~~~

Decide business rules for **normalization, collation, and case sensitivity** before creating unique constraints/indexes. Never silently delete one of two colliding customers just to force a migration through.

### Foreign keys and referential integrity

If a new constraint requires every referenced row to exist, validate data beforehand. Engines differ on constraint validation and deferral modes. Adding a foreign key is rarely a harmless one-liner on tables with hundreds of millions of rows.

## 24. Migration scripts and the software supply chain

Migration SQL holds **authority to alter production data**, so govern it like a high-risk release artifact.

~~~text
Git commit
  |
  +-- Spring Boot application source
  +-- Migration SQL / changelog
  +-- Contract tests / verification queries
  +-- Deployment manifests / IaC
  |
  v
CI: tests + code review + policy checks
  |
  v
Immutable release artifact(s)
  |
  v
Approved migration runner + application rollout
~~~

### Controls required

- PR reviews by both app owner and database owner for destructive DDL.
- Never edit already-applied migration files; create a new version.
- **Checksums/manifests** verify scripts match the exact commit.
- SAST/secret scans ensuring no connection strings or passwords appear.
- Artifact provenance and pipeline identity controls.
- **Migration history** backed up and audited—never edited casually.
- Never let every developer run **`db_owner`** commands on production.

### A critical control

Suppose CI built the app from commit **ABC**, while the migration job checked out **`main`** later and ran scripts from commit **DEF**. Result: **schema and app versions drift even though every pipeline job is green**. Always **pin the same commit SHA / release manifest** for both the migration artifact and application artifact.

## 25. Release manifest: linking code, schema, and data

A **release manifest** can record:

~~~yaml
# Illustrative release descriptor; not a direct deploy schema.
release: orders-2026-11-20-r3
gitCommit: abcdef0123456789
app:
  image: myregistry.azurecr.io/orders-api
  digest: sha256:REPLACE_WITH_VERIFIED_DIGEST
database:
  engine: postgresql
  migrationTool: flyway
  expandThrough: V2026112001
  backfillJob: customer-display-name-v1
  contractDeferred: true
compatibility:
  oldApp: orders-api-1.8
  newApp: orders-api-1.9
environment: staging
approvedBy: RELEASE_APPROVER_PLACEHOLDER
~~~

Values are illustrative. **Digests must be real built/scanned digests**, never placeholders in production. Restrict edit access and version-control manifests, linking artifacts, CI runs, and approvals for full traceability.

### One artifact, multiple environments

~~~text
Commit ABC
  |
  +-- orders-api image digest D1
  +-- migration package checksum M1
          |
          +--> dev deploy D1/M1
          +--> staging deploy D1/M1
          +--> production deploy D1/M1 after approval
~~~

Separate **configuration, identities, and database endpoints** per environment without rebuilding source per environment when promoting verified binaries.

### Configuration drift

Staging might have a column added manually by an admin that production lacks. Flyway history and actual schema can diverge despite identical manifests. Run **migration validation, schema drift detection, and inventory checks** before deploying rather than trusting environment names.

## 26. Safe deployment sequencing in pipelines

A high-quality pipeline enforces these gates:

~~~mermaid
flowchart TD
    A[PR reviewed + commit pinned] --> B[Build, unit, integration tests]
    B --> C[Package app + migrations + SBOM]
    C --> D[Migration lint + compatibility tests]
    D --> E[Apply expand to staging clone/test DB]
    E --> F[Deploy both old/new apps, run mixed-version tests]
    F --> G[Load test + lock/latency assessment]
    G --> H{Security/DB owner approval}
    H -- Rejected --> STOP[Do not touch production]
    H -- Approved --> I[Preflight production/backup readiness]
    I --> J[One-shot expand migration]
    J --> K{Schema history and invariants PASS?}
    K -- No --> FIX[Stop app rollout + investigate]
    K -- Yes --> L[Canary new app]
    L --> M{SLO and business metrics PASS?}
    M -- No --> RB[Roll back app if schema remains compatible]
    M -- Yes --> N[Complete rollout + observe]
    N --> O[Backfill / reconcile / later contract]
~~~

### Ordering is not one-size-fits-all

Some releases must deploy a **bridge application** before the migration—for instance, stopping code from reading a legacy column before contracting it. Pipelines must choose **order from the compatibility matrix**, not blindly apply "always migrate first" for every change.

### What should approvals actually verify?

Approvals should verify the **SQL diff, lock/IO estimates, target database/resource IDs, backup/restore readiness, change window, owner, and rollback/roll-forward plan**. Clicking approve does not make an unvetted destructive migration safe.

## 27. GitHub Actions: job and environment structure

GitHub Actions can separate:

~~~text
build-and-test
       |
       v
staging-migration-rehearsal
       |
       v
production-migration (environment approval)
       |
       v
deploy-application-canary
       |
       v
post-deploy-verify
~~~

**Educational workflow skeleton**—not runnable as-is in production:

~~~yaml
name: orders-release
on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build and test
        run: ./mvnw -B clean verify
      # Build/push immutable image and migration artifact:
      # requires reviewed actions/scripts, scanning, and digest capture.

  migrate-production:
    needs: build
    environment: production-database
    runs-on: [self-hosted, linux, db-migration-runner]
    steps:
      - uses: actions/checkout@v4
      - name: Authenticate Azure via federated identity
        uses: azure/login@v2
        with:
          client-id: PLACEHOLDER_CLIENT_ID
          tenant-id: PLACEHOLDER_TENANT_ID
          subscription-id: PLACEHOLDER_SUBSCRIPTION_ID
      - name: Verify approved migration artifact and run migration
        run: |
          echo "REPLACE WITH REVIEWED RUNNER COMMAND"
          exit 1

  deploy-application:
    needs: migrate-production
    runs-on: ubuntu-latest
    steps:
      - name: Deploy verified image to canary
        run: |
          echo "REPLACE WITH APPROVED DEPLOY SCRIPT"
          exit 1
~~~

**This workflow intentionally fails** at placeholders so it cannot be mistaken for a production-ready pipeline. Pin action versions/SHAs per policy and enforce GitHub environment approvals, concurrency/release locks, artifact promotion/digests, Azure RBAC, log redaction, private networking, and reviewed scripts. Self-hosted runner labels are illustrative; runners must be managed by the platform team.

### OIDC does not grant SQL permissions automatically

GitHub Actions authenticating to Azure via **federated credentials/OIDC** acquires a Microsoft Entra identity for control-plane operations. However, **`az login` does not automatically turn a JDBC connection into a database principal with `ALTER TABLE`**.

To migrate a DB, configure a supported **data-plane authentication** path (Entra token auth for Azure SQL/PostgreSQL where supported, or short-lived credentials/Key Vault secrets) and grant **least-privilege schema permissions**. Never print database passwords into workflow YAML, environment outputs, or logs.

## 28. Azure Pipelines: stages and service connections

In **Azure DevOps Pipelines**, the same structure applies:

~~~text
Stage 1: Build
  -> tests, SBOM, artifact + image digest

Stage 2: Deploy to Staging
  -> run migrations on test/clone database
  -> deploy mixed-version apps + verify

Stage 3: Production DB Change
  -> environment approvals/checks
  -> run migration once, collect history/invariants

Stage 4: Production App Rollout
  -> canary/slot/revision/rolling update
  -> post-deployment gates, monitor
~~~

### Key components

- **Service connections** with workload identity federation where supported.
- **Approvals and checks** on production environments.
- **Variable groups / Key Vault integration** to supply config without secrets in YAML.
- **Secure agents** with network reachability to private databases.
- **Artifacts** with checksums from the same commit/release run.
- **Stage conditions** blocking app deployment when migrations fail.
- **Audit records** capturing approver and change timestamp.

Never assume a **Contributor service connection** suffices to run migrations. Azure control-plane rights and **database schema/data-plane** permissions are distinct mechanisms.

### Concurrency control

Even with approvals, two operators could approve two releases simultaneously. Use **deployment concurrency controls** on environments/resources alongside migration tool locks. If R3 and R4 run concurrently, scripts and app versions can interleave dangerously.

## 29. Migration runners in private networks

Many Azure Database for PostgreSQL and Azure SQL instances enforce **private access / private endpoints**. A public GitHub-hosted runner **cannot connect**, even after a successful Azure login.

~~~text
GitHub / Azure DevOps control plane
            |
            v
Secure self-hosted runner / approved Azure job
  in VNet or authorized network path
            |
            +-- Private DNS resolution
            +-- TLS to database endpoint
            +-- Entra/DB auth with schema permission
            |
            v
     Azure PostgreSQL / Azure SQL
~~~

### Verification checks

1. DNS resolution from the **actual runner host**, not just an operator's laptop.
2. Routes, firewalls, NSGs, private endpoints, and ports to the database.
3. TLS hostname validation and CA trust chain.
4. Principal granted **`CONNECT` and `ALTER`** strictly on target schemas.
5. Secrets/tokens do not expire mid-migration on long runs.
6. Database has capacity and is not undergoing maintenance or failover.
7. Runner egress to Azure control plane, registries, and telemetry as required.

**Never open public database access (`0.0.0.0/0`) to fix pipeline connectivity.** Fix network placement and identities under security approval instead.

## 30. Separating migration and runtime permissions

Production should maintain at least two distinct identities:

| Principal | Responsibility | Permissions |
|---|---|---|
| **Migration runner** | Apply schema changes | DDL permissions strictly on authorized schemas/tables |
| **Runtime Spring Boot** | Business reads/writes | `SELECT`/`INSERT`/`UPDATE`/`DELETE` or needed stored procedures |
| **Backfill job** (when separate) | Update historical data | Strictly tables/operations needed for backfill |
| **CI build job** | Build/test/scan artifacts | Zero production database access |
| **Operator/reviewer** | Review, approve, audit | No default data-write or DDL rights |

### Why not grant `dbo`/owner to runtime?

If the REST API is compromised, a DDL-capable principal can **`DROP TABLE` or `ALTER SCHEMA`**. Least privilege contains the blast radius. Meanwhile, migrations must manage object ownership and grants so runtime apps can still access newly created tables.

### Entra ID and database authentication

Azure SQL Database and Azure Database for PostgreSQL – Flexible Server support Microsoft Entra authentication when configured, though JDBC/token flows and role mappings differ. **Never assume a managed identity is automatically a database user.** You must:

- Configure the database Entra administrator and auth policy.
- Create and map database principals or roles explicitly.
- Grant only necessary DDL/DML privileges.
- Account for access token lifetime and refresh.
- Verify JDBC/Flyway/Liquibase libraries support the chosen token-injection flow.

If a runner must use a database password, store it in a secret manager, restrict access, rotate regularly, and never print it to CI logs.

## 31. Preflight checks before production migration

Syntactically valid SQL can still fail on the wrong environment. Preflight must confirm:

~~~text
Release ID / Git SHA / artifact checksum
Target subscription + resource group + server + database
Engine/version/service tier
Migration history + checksum + expected prior version
Database size / target table row count
Long-running transactions / lock wait risk
Backup/PITR/restore capability
Replication/HA state and maintenance events
Expected peak traffic and quiet window
Owner/approver + change ticket
Stop conditions / rollback or roll-forward runbook
~~~

**Never print database passwords or tokens in preflight reports.** Identify targets by explicit resource IDs and server/database identities—not ambiguous hostname aliases that could confuse staging and prod.

### Schema history failure = stop

If Flyway `validate` reports a checksum mismatch, missing migration, or a DB version newer than the artifact, halt and investigate **drift/version mismatch**. Never auto-run **`repair`** just to push a deployment through; `repair` can mask schema divergence.

### Capacity gate

If Azure SQL/PostgreSQL already shows saturated CPU/IO, long transactions, or high replication lag, heavy migrations may breach downtime budgets. Defer the release or split steps rather than forcing through merely because approval was granted.

## 32. Backups, PITR, and restore drills

Managed Azure SQL/PostgreSQL services offer backup/PITR depending on policy and tier, yet **retention, restore capabilities, RPO/RTO, and restore mechanics vary**.

### Before a destructive migration

1. Confirm active backup policies and retention.
2. Record the timestamp, snapshot, or restore point per service support.
3. **Test restoring into an isolated environment** and time the restore.
4. Verify the restored database has required schemas, data, and permissions.
5. Plan how applications will repoint to the restored database.
6. Plan how to handle writes **committed after the restore point**.

### Why PITR is not a simple schema rollback

If a migration starts at 10:00 and the app accepts 500 orders between 10:01 and 10:15, restoring to 09:59 **loses those new orders** unless safe replay or reconciliation exists.

~~~text
09:59  Restore point
10:00  DDL migration
10:01  New order #A created
10:15  Migration incident

PITR to 09:59:
  -> old schema returns
  -> order #A does not automatically appear in restored DB
~~~

Therefore, **rolling forward** or rolling back the app on a still-compatible schema is usually safer than **full-database PITR** under active write traffic. PITR is a **disaster recovery** tool, not a free release undo button.

## 33. Code rollback, schema rollback, and roll-forward

| Option | When viable | Risk |
|---|---|---|
| **Application rollback** | Expanded schema remains compatible with old app | Does old app understand new data/statuses? |
| **Database roll-forward** | Fault can be fixed via a subsequent migration | Requires testing and handling partial state |
| **Migration script rollback** | Safe inverse exists with minimal/zero data loss and tested | Not all DDL is cleanly reversible |
| **PITR / restore** | Severe data loss/corruption requiring DR | Loses newer writes, downtime/replay needed |
| **Pause feature flag** | New feature causes bug while schema remains compatible | Does the flag actually block faulty write paths? |

### Principles

- **Never auto-run `DROP COLUMN`** just because the app rolled back to an older version.
- If an expand migration added a nullable column and v2 fails, you can usually roll back **the app alone** to v1 while keeping the expanded schema.
- Once a migration drops a legacy column, rolling back to v1 is typically **unsafe**.
- When data semantics changed, plan **forward/backward data transformations**, not DDL alone.

### Roll-forward fixes

If a migration built a suboptimal index without breaking app behavior, ship a new versioned migration fixing the index safely. Never edit an already-applied Flyway version and rerun on production, which triggers checksum mismatches and drift.

## 34. Feature flags and application canaries

**Feature flags** decouple deploying code from activating reads/writes on new schema fields:

~~~text
Database: S1 + display_name nullable
orders-api v1.9: code understands both customer_name/display_name
Feature flag use_display_name_reads = false
          |
          v
Backfill + reconciliation
          |
          v
Flag enabled for 1% / internal tenants
          |
          v
Observe errors/data consistency
          |
          v
Gradually enable for all
~~~

### Safe flag requirements

- Fail-safe default values.
- Flag changes audited with clear ownership.
- Both old and new code paths handle unbackfilled rows.
- Never toggle new-field reads before writers are synchronized.
- Kill switches truly block **risky writes**, not merely UI elements.
- Never substitute client-side flags for server-side authorization.

### Never contract just because a flag reached 100%

Rollback windows, delayed queues, offline workers, scheduled reports, and BI/ETL consumers may still depend on the legacy schema. Inventory all database/code access before destructive migrations.

## 35. Post-deployment verification

A release is not complete when a CI job returns **exit 0**. After migration and rollout:

1. Verify **Flyway/Liquibase schema history** and expected checksums.
2. Verify columns, tables, indexes, and constraints in the engine catalog.
3. Confirm app instances are **Ready/healthy** on the exact image digest/release.
4. Smoke-test both a **read** and a **write** using an authorized synthetic/test tenant.
5. Check **data invariants**: missing, mismatched, and duplicate counts.
6. Monitor DB **CPU, IO, storage, locks, connections, and replication lag**.
7. Monitor app **5xx, p95/p99, SQL exceptions, retry counts, and queue age**.
8. Watch logs and alerts across a post-deploy observation window.
9. Obtain business owner confirmation.
10. Record release evidence and prerequisites for the future contract phase.

### Read-only smoke tests are insufficient

An app can **`SELECT`** from the new schema cleanly while an old worker **`INSERT`** fails on a `NOT NULL` constraint or bad default. Test both **old and new writers/readers**, including background jobs and low-traffic endpoints.

### Post-deploy gates

Set thresholds against real baselines/SLOs—never infer "zero errors" from 1 minute of idle traffic. On low-volume systems, run controlled synthetic transactions to build confidence.

## 36. App Service: deployment slots and shared schemas

**Azure App Service deployment slots** support testing and swapping app versions, yet **slot swaps do not create corresponding database snapshots**.

~~~text
Before:
  Slot production: orders-api v1 ─┐
                                  ├── Azure Database S1
  Slot staging:    orders-api v2 ──┘

After expand S2 (backward-compatible):
  Slot production: orders-api v1 ─┐
                                  ├── Azure Database S2
  Slot staging:    orders-api v2 ──┘

Swap:
  Production traffic -> orders-api v2
  Database remains S2; it is not swapped
~~~

### Safety requirements

- If staging shares the **production DB**, start the new app only after compatible S2 expansion; avoid unauthorized business-data writes during tests.
- If staging uses a **separate staging DB**, smoke tests do not prove v2 against the live shared DB schema; verify production schema/version explicitly.
- Mark slot-specific settings and Key Vault references properly per App Service rules.
- **Swap warm-up / Health Check** does not replace database migration gates.
- To roll back a swap after v2 fails, S2 must remain compatible with v1.

### Anti-pattern

~~~text
Slot swap v2 to production
  -> v2 starts
  -> Flyway auto-runs DROP COLUMN
  -> v1 staging slot cannot query old field
  -> Rollback slot fails
~~~

Always run **expand migrations before canary/swap**, isolate destructive contractions, and avoid uncontrolled auto-DDL inside every Web App instance.

## 37. Azure Container Apps: revisions sharing one database

**Azure Container Apps (ACA)** supports **revisions** and traffic splitting per mode/feature. Yet multiple revisions still point at the same Azure PostgreSQL or Azure SQL instance.

~~~text
Ingress
  |
  +-- 90% -> revision v1 -> DB S2
  |
  +-- 10% -> revision v2 -> DB S2
~~~

### Four questions before starting a canary

1. Does S2 serve both v1 and v2 cleanly?
2. Does v2 write data that v1 cannot interpret?
3. Are background workers from **revision v1** still active?
4. Do backfill/contract jobs run independently of replica lifecycles?

### ACA Jobs for migrations

If using a **Container Apps Job** as the runner, configure a finite job with an image holding migration scripts/CLI, scoped DB permissions, and network reachability to the DB.

~~~text
CI/CD:
  1. Trigger one-shot migration job
  2. Wait for completed state AND verify schema history
  3. Deploy revision v2
  4. Canary + monitor
  5. Complete rollout or rollback traffic
~~~

**Auto-scaling or retrying a job does not make scripts idempotent**; rely on Flyway/Liquibase history and stop conditions. Cap job executions/concurrency and run only upon release approval.

### Never treat scale-to-zero as migration locking

ACA APIs can scale replicas to zero and wake on demand. That has nothing to do with migration safety. **A cold-starting instance must never run `ALTER TABLE` automatically** when migration ownership belongs to a CI/CD runner.

## 38. AKS: dedicated migration Job and separate Deployment

**AKS** provides Kubernetes **Jobs** for finite tasks and **Deployments** for long-running Spring Boot APIs.

~~~mermaid
flowchart TD
    CI[Approved release pipeline] --> J[Kubernetes Job: migrate-schema]
    J --> D[(Azure PostgreSQL S2)]
    J --> V{History and invariants validated?}
    V -- No --> S[Stop rollout]
    V -- Yes --> DEP[Deployment: orders-api v2]
    DEP --> C[Canary / readiness checks]
    C --> M[Monitor / promote or roll back app]
~~~

Illustrative **Kubernetes Job skeleton**:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-schema-expand-r3
  namespace: orders-production
  labels:
    release: r3
spec:
  parallelism: 1
  completions: 1
  backoffLimit: 0
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      serviceAccountName: orders-db-migrator
      containers:
        - name: migrate
          image: myregistry.azurecr.io/orders-migration@sha256:REPLACE
          args: ["migrate"]
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "1024Mi"
~~~

**Not a production-deployable manifest yet.** Replace the digest and verify image entrypoint/args, workload identity/secret mounting, DB connectivity, namespace permissions, security contexts, resource sizing, timeouts, and observability. Here **`backoffLimit: 0`** intentionally forces operator inspection of partial state before retrying; not every migration requires zero retries.

### Do not rely solely on `Job Succeeded`

A Job can exit 0 if a shell script fails to propagate SQL exit codes. Verify **schema history, row counts, constraints/index status, and smoke tests** in a separate CI step. If migration fails, **halt the rollout**.

### Risks of Helm hooks

Helm pre-upgrade hooks can launch migration Jobs, though hook ordering, rollback behavior, and job cleanup follow Helm semantics. On a Helm rollback, **database schemas do not automatically revert**. For heavy migrations across multiple teams, explicit pipeline orchestration is usually clearer.

## 39. Azure Functions and background workers

A Spring Boot API often coexists with **Azure Functions (Java)**, Service Bus workers, or AKS CronJobs.

~~~text
orders-api v1/v2 -> Azure PostgreSQL S2
        |
        +-- Service Bus queue with old/new messages
                 |
                 +-- invoice-worker v1
                 +-- invoice-worker v2
                 +-- Azure Function consumer
~~~

### An often-overlooked risk

Even after API v2 finishes rolling out, **v1 workers** may still process messages enqueued hours or days earlier. If a contract migration drops a column used by worker v1, workers fail even though every new HTTP request succeeds.

### Consumer checklist

- Do we have an inventory of **all readers and writers** touching the database?
- Which worker versions are still deployed where?
- Do queue retention, dead-letter queues, or replays carry legacy event schemas?
- Are there weekly/monthly scheduled reports or ETL jobs?
- Do Function triggers have retry policies or delayed executions?
- Are there BI dashboards, ad-hoc queries, or integration partners?

**"All API pods are on v2" is not enough to drop a column.** Prove all legacy consumers have retired or migrated.

## 40. Multiple microservices sharing a schema

If **orders-api**, **billing-api**, and **reporting-worker** all read/write `customers`, a migration from `orders-api` can break `billing-api`.

~~~text
orders-api v2 ---------+
billing-api v1 --------+-- shared customers table
reporting-worker v1 ---+
~~~

### Ownership risks

- Two teams create conflicting migrations on the same table.
- Separate Flyway histories exist without clear schema ownership.
- One service adds a constraint that breaks another service's inserts.
- Unclear who is allowed to run destructive DDL.

### Designs to reduce risk

1. Designate a **schema owner / data contract owner**.
2. Share one migration repository or coordinated release gate across schema consumers.
3. Expose public APIs/events instead of shared table access where feasible.
4. Run contract tests across all consumers.
5. Never let two independent pipelines run DDL concurrently without coordination.
6. If splitting databases, design replication/outbox and consistency policies explicitly.

**Microservices do not automatically guarantee separate databases**, and shared schemas reduce deployment independence unless tightly governed.

## 41. Test matrix for two app versions and two schema states

Before releasing v2, test at minimum:

| Application | Schema S1 | Schema S2 expand | Schema S3 contract |
|---|---|---|---|
| **v1** | Must PASS | **Mandatory PASS** for rolling/rollback | FAIL acceptable only after v1 retired |
| **Transitional v2** | May FAIL if requiring new column | **Mandatory PASS** | PASS once legacy field unused |
| **v3 new-only** | FAIL | PASS | **Mandatory PASS** |
| **Worker v1** | PASS | **Mandatory PASS** while worker runs | FAIL only after worker retired |

This is a **design template matrix**; exact outcomes depend on code. Document which cells are **mandatory PASS** at every step.

### Test both reads and writes

Do not test only **`GET /customers`**. Test:

- Creating a customer with writer v1 and reading with reader v2.
- Creating a customer with writer v2 and reading with reader v1.
- Concurrent updates to the same row across versions within business rules.
- Transaction rollback/idempotency when processes restart mid-flight.
- Report/ETL queries referencing legacy fields.
- Null/default/constraint behavior for unbackfilled rows.

### Data migrations need canary data

Include representative test cases: Unicode/Vietnamese names, NULLs, long strings, normalized duplicates, large transactions, and timezone/currency edge cases. Never copy production data containing PII without authorization and proper data-protection controls.

## 42. Integration tests and rehearsals on real databases

**H2 in-memory databases** are convenient for unit tests, yet differ from PostgreSQL/Azure SQL in SQL dialect, constraints, transactions, collations, and locking.

### Test levels

| Level | Purpose | Environment |
|---|---|---|
| Unit tests | Business logic, DTO mappings | JVM / mocks |
| Migration syntax tests | Run scripts in order | Test DB on matching engine |
| Schema compatibility tests | v1/v2 read/write against S2 | Integration environment |
| Data backfill tests | Checkpoints, restarts, reconciliation | Representative synthetic data |
| Load/locking tests | Impact of DDL and backfills on live requests | Prod-like staging |
| Restore rehearsal | Measure RTO and data recovery | DB clone / isolated restore |
| Production canary | Verify SLOs on limited live traffic | Approved production rollout |

### Testcontainers

With Spring Boot and JUnit, **Testcontainers PostgreSQL** runs a real PostgreSQL container in CI instead of H2, yielding far more accurate SQL migration behavior. Even so, it **does not replicate** Azure networking, service tiers, HA, table scale, or concurrent production load—staging rehearsals remain mandatory.

### Sample test questions

- Does a **fresh install** migration from 0 to latest pass?
- Does an **upgrade** migration from the prior schema to latest pass?
- Does app v1 work on S2?
- Does app v2 handle remaining S1 rows right after expand?
- Does restarting a killed backfill avoid duplicate writes/counts?
- Can app v2 roll back to v1 without losing data?
- Does DDL block requests longer than the downtime SLO?

## 43. Locking, query latency, and database overload

A migration that succeeds technically while spiking API p95 latency from 100 ms to 12 seconds is still a **service quality incident**.

### Common causes

- DDL waiting on or holding blocking locks.
- Index builds/rebuilds causing CPU/IO spikes.
- Data backfills flooding WAL/transaction logs.
- Autovacuum, maintenance, or stale index statistics.
- Connection pool exhaustion.
- Read-replica lag.
- Execution plan regressions after schema/index changes.

### PostgreSQL lock investigation query (run with appropriate privileges)

~~~sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    LEFT(a.query, 120) AS query_sample
FROM pg_stat_activity a
WHERE a.datname = current_database()
ORDER BY a.query_start NULLS LAST;
~~~

**Never share raw `query_sample` strings containing sensitive data.** Querying `pg_stat_activity` depends on role permissions; never terminate backend sessions without incident owner authorization.

### Stop conditions

Example design:

~~~text
If p95 latency > approved SLO for sustained window
 OR lock wait exceeds approved threshold
 OR database CPU/IO saturation persists
 OR replica lag exceeds permitted budget:
    pause backfill / stop new migration stages
    escalate to DB/application owner
~~~

Thresholds must match your real workload rather than one fixed number across all deployments. **Never kill a running DDL command arbitrarily** without understanding your engine's rollback and partial-state behavior.

## 44. Versioning across schemas and event contracts

The new app may write to database S2 and emit **`order.v2`** events while old workers only understand **`order.v1`**.

~~~text
orders-api v1 + DB S1 -> event order.v1 -> worker v1

Expand DB S2
orders-api v2 -> event order.v1 + optional v2 fields
             -> worker v1/v2 both consume during transition

After consumer migration:
orders-api v3 -> event order.v2 -> worker v2
~~~

### Never emit incompatible events in the same migration step

Database schemas and event schemas are **separate contracts**. When API v2 introduces `display_name`, event consumer v1 may reject new required fields or unknown status values. Mitigations:

- Add **optional** fields first while preserving legacy fields.
- Version event schemas explicitly and configure consumers to tolerate unknown fields where appropriate.
- Run **schema compatibility tests** and delayed-message replay tests.
- Keep legacy event parsers until queue/DLQ/backup retention windows expire or migrate.
- Use outbox patterns to link DB commits to event publishing where business requires atomicity.

**A passing Flyway migration does not prove Service Bus workers are compatible.** Coordinate releases across DB, API, messages, and consumers.

## 45. Flyway runner: `migrate`, `validate`, and `info`

Using the Flyway CLI or configured Maven plugin, a standard workflow executes:

~~~text
validate -> info -> approved migrate -> info -> verify invariants
~~~

**Illustrative sandbox commands** with Flyway CLI installed and environment config supplied:

~~~bash
# Run only on a sandbox DB; inject variables securely.
flyway -locations=filesystem:./db/migration validate
flyway -locations=filesystem:./db/migration info
flyway -locations=filesystem:./db/migration migrate
flyway -locations=filesystem:./db/migration info
~~~

**Commands work only when Flyway CLI is installed with valid JDBC URL, driver, auth, and config**, and `db/migration` exists. Lesson examples carry no auto-deployment privileges. In production, migration runners must consume packages **built from an approved commit/digest**—never a floating branch—using secure secret injection, private DNS, and gates.

### What to avoid

- Never print passwords or token-bearing JDBC URLs in CI logs.
- Never run **`flyway clean`** in production.
- Never run **`repair`** blindly after a checksum mismatch without investigating.
- Never confuse **`validate` succeeded** with **schema/data compatibility verified**.
- Never launch **`migrate`** concurrently with another migration job ignoring locks.

### Using the Maven Flyway plugin

You can run **`mvn flyway:validate/info/migrate`** when configured; never assume having **`flyway-core`** makes the Maven plugin ready automatically. Pin the plugin version, configure drivers/credentials securely, and test in a sandbox.

## 46. Scenario A: new app runs before migration completes

**Context:** CI/CD deploys Spring Boot v2 first; v2 maps **`display_name`** via JPA while the database is still on S1.

### Symptoms

- Spring Boot startup fails with validation/missing-column errors.
- HTTP requests fail with SQL undefined-column errors.
- New pods stay unready / `CrashLoopBackOff`; old pods continue serving.
- Autoscaler spawns more v2 pods, flooding logs.

### Root cause

The pipeline lacked a **successful expand migration → deploy v2** dependency, or the migration job exited without verifying the live schema.

### Remediation

1. **Halt the v2 rollout** before corrupting data.
2. Inspect target DB identity and migration history.
3. Check whether the expand script ran against the **intended server, database, and schema**.
4. Keep serving on v1 if still compatible.
5. Review and apply expand with proper approvals and lock checks.
6. Validate schema S2 and run mixed-version integration tests.
7. Restart the v2 canary.

### Lesson

**Kubernetes/App Service readiness does not execute database migrations automatically.** Orchestration must enforce prerequisites and verification rather than merely placing two deploy steps adjacent.

## 47. Scenario B: Flyway reports checksum mismatch

**Context:** Migration **`V16__add_customer_name.sql`** already ran in staging/prod. A developer edits that file post-merge and deploys a new commit. Flyway `validate` reports a checksum mismatch.

### Root cause

Production history holds the checksum of the originally applied script, while the new artifact has different file contents.

### What NOT to do

~~~text
Flyway validation failed
  -> Automatically run flyway repair
  -> Retry migrate without reviewing changes
~~~

`repair` updates metadata history without executing the new SQL edits, giving the illusion of sync while schema and source diverge.

### Safe resolution

1. Inspect the exact originally applied script from release artifacts/history.
2. Diff the live database objects against Git history.
3. To add or modify behavior, author a **new migration version**.
4. If the mismatch came purely from approved formatting/normalization rules, follow an audited special-review process.
5. Never edit the schema history table manually to bypass the migration tool.
6. Add a CI check rejecting edits to already-released migration files.

**Migration history is an audit record**; any repair action must be documented in a change ticket.

## 48. Scenario C: `ALTER TABLE` blocked by a long-running transaction

**Context:** An **`ADD COLUMN`** migration on Azure Database for PostgreSQL stalls past 2 minutes. Requests begin waiting on locks and API p95 spikes.

### Possible causes

- A long-running transaction holds an incompatible lock.
- DDL sits in the lock queue, blocking subsequent queries behind it.
- DB lacks capacity or is undergoing failover/maintenance.
- The migration includes `UPDATE` or `INDEX` statements beyond `ADD COLUMN` alone.

### Runbook

1. Identify the active migration statement, start time, and lock wait state.
2. Inspect **`pg_stat_activity`/`pg_locks`** and Azure PostgreSQL metrics with authorized access.
3. Assess application latency, DB CPU/IO, and replication lag.
4. Determine whether the statement can be **canceled safely** under PostgreSQL transaction semantics.
5. If canceled, inspect migration history and schema state before retrying.
6. Reschedule during lower traffic or split into smaller steps.
7. Set appropriate lock timeouts based on benchmarks rather than raising timeouts blindly.

### Lesson

**Fast metadata DDL can still block production traffic via lock queues.** Never benchmark migrations solely on a 100-row laptop database.

## 49. Scenario D: backfill shows 99% yet data is still missing

**Context:** Backfill reports 99% of rows processed, yet enabling the `display_name` read flag leaves some customers blank.

### Hypotheses

- The cursor skipped rows inserted or updated while the job ran.
- Old writers continued updating `customer_name` without updating `display_name`.
- A batch partially failed and the checkpoint advanced prior to commit.
- Transformation logic mishandled NULLs, Unicode, or trailing whitespace.
- Archived or partitioned tenants were excluded by the query.

### Remediation

1. **Disable the read-new feature flag** or safely fall back to legacy reads.
2. Run business-invariant reconciliation instead of trusting a progress bar.
3. Quantify missing/mismatched rows by partition or tenant where authorized.
4. Audit legacy writers and concurrent updates.
5. Rerun idempotent batches or deploy a fixed transform version.
6. Confirm **zero or acceptable discrepancies** per definition.
7. Re-enable reads gradually via canary.

### Never run unscoped `COUNT(*)` checks

If the job targeted only active customers, a full-table `COUNT(*)` misreports progress; conversely, if business reports still read archived rows, checking only active customers misses real defects. Match reconciliation scope to business scope.

## 50. Scenario E: image rolled back, yet the old app still fails

**Context:** After releasing v2, the team hits errors and rolls the ACA revision / AKS Deployment back to v1. However, v1 continuously throws **`column customer_name does not exist`**.

### Root cause

The pipeline ran the contract migration **`DROP COLUMN customer_name`** in the same release as v2, breaking schema compatibility.

### Response

- Stop repeating futile image rollbacks.
- Halt risky traffic or write paths if data corruption threatens.
- Assess current schema, applied migrations, and affected rows.
- Evaluate **rolling forward v2** with an urgent fix or feature flag.
- If the column must be restored, design a proper data-semantics rebuild/backfill; **`ADD COLUMN` does not restore dropped data**.
- Use PITR/restore only after evaluating RPO/RTO and newer writes.
- Post-incident, enforce policy: **never contract in the initial release** while v1 rollback remains possible.

### Lesson

**Application rollback does not roll back the database.** Compatibility matrices and contract timing determine whether rolling back code remains viable.

## 51. Scenario F: right release migration ran on the wrong database

**Context:** The production pipeline inherited a staging environment variable. Migration succeeded, yet production Spring Boot still fails with missing columns while the staging DB gained the new column.

### Root cause

The target database came from an unverified alias or secret, or the runner identity held overly broad permissions across multiple databases.

### Prevention

1. Record exact environment and database resource IDs in the release manifest.
2. Before migrating, query **`current_database`/`current_schema`/server identity** per engine with proper permissions.
3. Scope the runner identity exclusively to the intended DB.
4. Enforce environment approvals and log target identity without secrets.
5. Isolate secret scopes and networking between staging and prod.
6. Verify schema history on the declared target post-migration.

**A migration job exiting 0 only proves it ran somewhere**—not on the intended production DB without target verification and scoped permissions.

## 52. End-to-end lab: migrating alongside a Spring Boot app

### Lab objective

Build **Orders Lab** with **Spring Boot + PostgreSQL** across two versions:

- **v1:** reads/writes **`customers.customer_name`**.
- **Transitional v2:** understands **`display_name`**, while still serving legacy data.
- **Schema S1:** only `customer_name`.
- **Schema S2:** both `customer_name` and `display_name`.
- **Backfill:** migrates legacy rows and verifies consistency.
- **Simulated pipeline:** build → expand → verify → canary v2 → app rollback → later contract.

You can run a **local PostgreSQL container / Testcontainers** and write out Azure deployment manifests. If you lack subscription permissions or budget, **no real Azure SQL/PostgreSQL instance needs to be created**; you can meet objectives via release simulation and an ADR. With an Azure sandbox, use isolated resources and never real customer data.

### Part A — Create schema S1 in a test database

**PostgreSQL** SQL:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO customers (customer_name)
VALUES
  ('Nguyễn An'),
  ('Trần Bình'),
  ('Lê Chi');

SELECT id, customer_name FROM customers ORDER BY id;
~~~

**Use a fresh test database or empty lab schema.** Never run `CREATE`/`INSERT` against a database holding real customers. When using Flyway, place these in `V1` rather than running them manually alongside Flyway on an unmanaged schema.

### Part B — Build app v1

Spring Boot v1 exposes:

~~~text
GET /customers/{id}
  -> return customer_name

POST /customers
  -> INSERT customer_name

Health endpoint
  -> /actuator/health
~~~

Repository SQL example:

~~~sql
SELECT id, customer_name
FROM customers
WHERE id = :id;

INSERT INTO customers (customer_name)
VALUES (:customer_name);
~~~

Use **prepared statements / JDBC bind parameters** or JPA rather than concatenating user input into SQL. Verify v1 reads all three rows and inserts a new test row.

### Part C — Create expand migration V2

Separate migration files, e.g.:

~~~text
src/main/resources/db/migration/
  V1__create_customers.sql
  V2__add_display_name.sql
~~~

Contents of V2:

~~~sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(200);
~~~

In real pipelines, source **migration artifacts from the exact release**; in the lab, let Flyway apply once against test PostgreSQL.

### Part D — Run Flyway and inspect

With Flyway and test DB configured, run the migration runner or Flyway CLI in the lab:

~~~bash
# Flyway CLI must be installed and receive secure JDBC config.
flyway -locations=filesystem:./db/migration validate
flyway -locations=filesystem:./db/migration migrate
flyway -locations=filesystem:./db/migration info
~~~

Then query:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'customers'
ORDER BY ordinal_position;

SELECT COUNT(*) AS missing_display_name
FROM customers
WHERE display_name IS NULL;
~~~

**Expected:** the new column exists and is initially NULL for older rows. **This is not a migration bug**; expansion permits backfilling next.

### Part E — Test app v1 against S2

Keep **v1 running** or rerun v1 tests against S2:

1. `GET` on existing customers must succeed.
2. `POST` for new customers must succeed without sending `display_name`.
3. Zero missing-column or `NOT NULL` errors from S2.
4. Schema history remains consistent.

If v1 fails against S2, **halt the release**: expansion is incompatible. Never proceed to v2 or backfill before fixing it.

### Part F — Build transitional app v2

Fallback read logic:

~~~java
public String effectiveDisplayName(
        String customerName,
        String displayName) {
    return displayName != null ? displayName : customerName;
}
~~~

In real code, the service layer reads both fields from the JPA/JDBC entity. For writes, preserve compatibility:

~~~sql
UPDATE customers
SET customer_name = :new_name,
    display_name = :new_name,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id;
~~~

**Illustrative SQL for a single row.** While v1/v2 coexist, keep v2 reading canonical `customer_name` until v1 writers retire. If switching reads to `display_name` early, remember v1 writers can leave `display_name` stale; use a compatibility bridge/trigger or wait until all v2 writers roll out.

### Part G — Backfill and reconciliation

On the small lab dataset:

~~~sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;

SELECT COUNT(*) AS remaining_nulls
FROM customers
WHERE display_name IS NULL;

SELECT COUNT(*) AS mismatches
FROM customers
WHERE display_name <> customer_name;
~~~

**Expected under identical-name rules:** `remaining_nulls = 0`, `mismatches = 0`. On large production data, replace a single `UPDATE` with **checkpointed backfill batches**, concurrent-write handling, and progress dashboards.

### Part H — Canary and app rollback

Simulate the rollout:

~~~text
Time T0: schema S1, app v1 all replicas
Time T1: schema S2 expand, app v1 all replicas
Time T2: app v1 90%, app v2 10%
Time T3: app v1 50%, app v2 50%
Time T4: app v2 100%
Time T5: simulate app v2 bug -> roll back app to v1 on S2
~~~

At each stage:

- Send `GET` and `POST` test requests.
- Confirm every version reads and writes properly.
- Check logs for SQL exceptions, 5xx errors, and DB connection errors.
- Inspect rows inserted by both v1 and v2.
- Verify feature-flag read paths and data consistency.

**Key milestone:** after T5, **v1 still works cleanly against S2** because expand never dropped `customer_name`.

### Part I — Controlled failure tests

In a sandbox only:

1. **Kill the backfill job** mid-batch, restart it, and verify checkpoint/idempotency.
2. **Run v2 before S2** to observe missing-column crashes and why gates are needed.
3. **Edit an already-applied Flyway migration in the lab** to observe checksum mismatch (never alter production history).
4. **Open a long-running transaction in the test DB**, run DDL with a lock timeout, and observe wait behavior.
5. **Trigger simulated concurrent deployments** to see why release concurrency locks matter.
6. **Target the wrong test DB intentionally** with a scoped principal and confirm preflight blocks it.

Never run these fault tests against shared databases or production. If fault injection is unavailable, write a tabletop runbook with expected outcomes.

### Part J — Deferred contract

Once **v1/worker v1** have retired, the rollback window closed, and zero-legacy-consumer checks pass, a contract migration *may*:

~~~sql
-- PostgreSQL; run only in test DB or dedicated contract release:
ALTER TABLE customers
    DROP COLUMN customer_name;
~~~

Before `DROP`, deploy **v3 using only `display_name`**, confirm full backfill, and apply constraints on a separate schedule. If reports, BI, or rollbacks still need the old column, **do not run contract**.

### Part K — Evidence to submit

~~~text
Release ID / commit / app version:
Database engine/version:
Schema S1 -> S2 migration ID/checksum:
Migration runner and permissions:
Schema history before/after:
Old app v1 on S2 result:
New app v2 on S2 result:
Read/write matrix outcomes:
Backfill processed/missing/mismatch counts:
Rollback app v2 -> v1 outcome:
Locks, p95 latency and DB load measurements:
Data backup/restore test summary:
Security: secret exposure NONE:
Cost/cleanup:
Remaining contract preconditions:
~~~

**Never fabricate measurements.** If the lab ran locally without Azure deployment, mark **local-only / not measured** for platform metrics and production SLOs.

### Part L — Cleanup

- Delete only **lab databases, containers, and resource groups** you own and are authorized to clean up.
- Never delete shared Azure SQL/PostgreSQL instances, backups, or production migration histories.
- Revoke/rotate test credentials if exposed.
- Check sandbox resources incurring charges: DB compute/storage, runners, AKS/ACA jobs, Log Analytics.
- Archive sanitized migration scripts, ADRs, and CI evidence per team policy.

## 53. Production release and incident runbook

### Before the change window

| Step | Evidence | Owner |
|---|---|---|
| Freeze release manifest | Approved commit/digest/checksum | Release engineer |
| DB preflight | Engine/target, schema history, data size, locks | DBA / DB owner |
| Security approval | Migration principal, networking, secret handling | Security / platform |
| Restore rehearsal | RTO, PITR validity, data recovery plan | DB / SRE |
| Compatibility tests | App v1/v2 + S1/S2 matrix | App team |
| Load rehearsal | Lock/IO/latency impact estimate | DBA / SRE |
| Rollback decision tree | App rollback vs. roll-forward | Incident commander |
| Stakeholder comms | Change ticket, user-impact window | Release owner |

### During migration

1. Re-verify **exact target database, release checksum, and principal**.
2. Block concurrent release pipelines.
3. Capture baseline latency, CPU/IO/locks, DB connections, and replication lag.
4. Run **expand migration once** via the approved runner.
5. Check status/errors, **Flyway/Liquibase history**, and schema objects.
6. On failure: **halt app rollout immediately**, assess partial state, and never retry blindly.
7. On success: start canary application rollout.
8. Monitor business invariants, old/new version reads/writes, and database health.
9. Run throttled backfills if scheduled in the plan.
10. Promote or roll back the app per decision tree; retain expanded schema if compatible.

### Post-release

- Confirm observed schema version, app image digest, and service versions.
- Run synthetic read/write checks with an authorized test tenant.
- Inspect worker/event backlogs and delayed messages.
- Record backfill/reconciliation counts, incidents, change duration, and SLOs.
- Schedule action items and a **contract gate** once data and consumers are clean.
- Watch DB log/WAL/storage growth and costs over subsequent cycles.

### Procedure when a migration stalls

~~~mermaid
flowchart TD
    A[Migration exceeds threshold] --> B[Freeze app rollout]
    B --> C[Check DB locks/CPU/IO and current SQL]
    C --> D{Safe to cancel?}
    D -- Unknown --> E[DB owner decides, preserve evidence]
    D -- Yes --> F[Cancel according to engine behavior]
    D -- No --> G[Coordinate risk mitigation / incident]
    F --> H[Inspect schema/history/partial data]
    G --> H
    H --> I{Database and app compatible?}
    I -- Yes --> J[Keep old app, plan roll-forward]
    I -- No --> K[Invoke tested recovery plan]
~~~

**Never kill a DB session or active job solely because a CI step timed out.** Check whether DDL is transactional, which batches committed, lock states, and data integrity first.

## 54. Checklist: releasing databases alongside applications

- [ ] A migration owner and schema owner are clearly designated.
- [ ] All apps, workers, reports, and ETL jobs touching the schema are mapped.
- [ ] SLO/downtime budgets, RTO/RPO, and change windows are defined.
- [ ] DDL is classified into **expand/migrate/contract** with destructive operations isolated.
- [ ] A compatibility matrix covers old/new apps against before/after schemas.
- [ ] Schema expansion does not break active older app instances.
- [ ] Transitional apps read legacy data and write new fields consistently.
- [ ] Reconciliation plans cover dual-writes, backfills, and concurrent updates.
- [ ] `NOT NULL`/`UNIQUE`/FK constraints are phased in with data checks.
- [ ] Index operations were assessed for locks, IO, and engine options.
- [ ] Migration scripts are versioned, checksummed, and reviewed in Git.
- [ ] Applied migrations are never edited; changes use new versions.
- [ ] Flyway/Liquibase/driver versions match the engine and Spring Boot.
- [ ] Runtime apps never run `ALTER TABLE` when a migration runner owns schema changes.
- [ ] One-shot runners enforce concurrency locks and partial-failure runbooks.
- [ ] Migration and app artifacts share one release manifest, commit, and digest.
- [ ] CI tests fresh installs, upgrades, and mixed-version read/write on expanded schemas.
- [ ] Load/locking tests run against the matching DB engine and representative data.
- [ ] Target server, schema, and region are verified from the real runner.
- [ ] Runner private DNS/VNet/TLS connects securely without opening public DB access.
- [ ] CI identities, managed identities, and DB principals follow least privilege.
- [ ] Zero passwords, tokens, or raw PII exist in repos, SQL scripts, or logs.
- [ ] Backup/PITR policies are verified and restore drills rehearsed.
- [ ] Plans exist to preserve newer writes if disaster recovery restore is ever required.
- [ ] Preflight schema history, engine, version, capacity, and lock checks pass.
- [ ] Pipelines halt if migration, schema verification, or compatibility gates fail.
- [ ] Concurrent releases cannot migrate the same schema simultaneously.
- [ ] App rollouts via slots, revisions, or rolling updates are controlled.
- [ ] Older apps remain functional on the expanded schema throughout the rollback window.
- [ ] Legacy workers, queued messages, and reports are audited before contraction.
- [ ] Feature flags include rollback/kill switches and audit logging.
- [ ] Synthetic read/write tests, business invariants, and SLO monitors pass.
- [ ] DB metrics track CPU/IO, waits, connections, storage, and replica lag.
- [ ] Migration audit records capture owner, start/end times, outcome, and SQL checksums.
- [ ] Decision tree defines **app rollback vs. DB roll-forward vs. PITR**.
- [ ] No destructive contraction runs before the rollback window closes.
- [ ] Incident runbooks and on-call owners cover migrations.
- [ ] Costs for staging clones, runners, indexes/backfills, and log retention are budgeted.
- [ ] Owned lab resources are cleaned up and evidence archived per policy.

## 55. Self-check questions

1. Why is changing the application version and database schema at the exact same second usually risky?
2. How many intermediate states can exist in a release between v1/S1 and v2/S2?
3. How do backward compatibility and forward compatibility differ?
4. Why is adding a nullable column usually safer than renaming directly?
5. What steps make up expand–migrate–contract?
6. Why is a bridge version needed for older writers and readers?
7. In the `customer_name` migration, why is a single backfill pass insufficient?
8. If app v1 keeps updating `customer_name`, how can `display_name` become stale?
9. When should you enable the feature flag reading the new column?
10. Why does rolling back an app to v1 require schema S2 to stay compatible?
11. What does Flyway schema history record, and what does it not prove?
12. Why should you never edit a Flyway script already applied to production?
13. What roles do Liquibase `changeSet`s and checksums play?
14. How can a Liquibase `dropColumn` rollback destroy data?
15. Why should every Spring Boot pod not run DDL migrations at startup?
16. How do a one-shot migration runner's permissions differ from the runtime app's?
17. Does Azure OIDC login automatically grant `ALTER TABLE` inside PostgreSQL?
18. Why might a GitHub-hosted runner fail to reach a private database?
19. What risks do Flyway `clean` and `repair` pose in production?
20. Which exceptions exist in PostgreSQL transactional DDL?
21. Why can't `CREATE INDEX CONCURRENTLY` run inside a transaction block?
22. Can a failed concurrent index build leave an invalid index behind?
23. How does Azure SQL Query Store help after an index migration?
24. Why shouldn't you copy PostgreSQL DDL verbatim into T-SQL?
25. How should a batched data backfill manage cursors and checkpoints?
26. Why must cursor updates commit alongside data writes?
27. Why can a full-table `UPDATE` cause downtime on large datasets?
28. Which data checks are required before adding `NOT NULL` or `UNIQUE` constraints?
29. Must schema versions match application semantic versions?
30. Why does a release manifest need both Git commit and image/migration digests?
31. Is Flyway `migrate` exiting 0 sufficient as a post-deploy gate?
32. Why doesn't stage approval replace a data recovery plan?
33. Does an App Service slot swap automatically roll back the database schema?
34. What risks arise when ACA revisions share one database?
35. How must AKS Kubernetes Job backoff/retries account for partial migrations?
36. Why doesn't Helm rollback automatically roll back the database?
37. When might an older queue consumer still read a dropped column?
38. How do you test both writer v1 and reader v2 against an expanded schema?
39. Why doesn't H2 replace PostgreSQL/Azure SQL integration tests?
40. How do long-running database transactions affect DDL?
41. How does PITR to a point before migration risk losing newer writes?
42. When should you roll forward instead of rolling back a schema?
43. If a migration accidentally targets the staging DB, which preflight check catches it?
44. Does turning off a read-path feature flag automatically stop risky writes?
45. After a release, which metrics confirm success?
46. What prerequisites must be satisfied before running contract `DROP COLUMN`?
47. How do database schema migrations differ from Service Bus event schema evolution?
48. How should ownership be governed across a shared release of API, workers, and database?
49. In the lab, why must v1 pass on S2 before deploying v2?
50. What evidence should a thorough release report contain?

## 56. References

- [Azure Database for PostgreSQL – Flexible Server documentation](https://learn.microsoft.com/azure/postgresql/flexible-server/) — managed PostgreSQL architecture, HA, networking, monitoring, and backups.
- [Azure SQL Database documentation](https://learn.microsoft.com/azure/azure-sql/database/) — T-SQL, scaling, backup/restore, and performance.
- [Azure SQL Query Store](https://learn.microsoft.com/azure/azure-sql/database/query-store-overview) — query and regression analysis.
- [Azure Database for PostgreSQL monitoring](https://learn.microsoft.com/azure/postgresql/flexible-server/concepts-monitoring) — PostgreSQL metrics and operations.
- [Spring Boot Flyway integration](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html#howto.data-initialization.migration-tool.flyway) — Spring Boot schema initialization and migrations.
- [Flyway documentation](https://documentation.red-gate.com/fd/) — versioned migrations, validation, CLI, history, and engine support.
- [Liquibase documentation](https://docs.liquibase.com/) — changelogs, changeSets, preconditions, and rollbacks.
- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — DDL semantics and locks.
- [PostgreSQL CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — `CONCURRENTLY`, restrictions, and invalid indexes.
- [PostgreSQL monitoring database activity](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity` and wait events.
- [GitHub Actions environments](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment) — approvals and environment protection.
- [Azure Login for GitHub Actions](https://github.com/Azure/login) — Entra/OIDC authentication for workflows.
- [Azure Pipelines environments](https://learn.microsoft.com/azure/devops/pipelines/process/environments) — deployment governance.
- [Azure Container Apps jobs](https://learn.microsoft.com/azure/container-apps/jobs) — one-shot, cron, and event-driven jobs.
- [Azure Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions) — staged app rollouts.
- [Azure App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots) — slot warm-up, swapping, and settings.
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) — completion, retries, and timeouts.
- [Kubernetes Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) — rolling updates.
- [Microsoft Entra managed identities](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview) — workload identities.
- [Azure Key Vault](https://learn.microsoft.com/azure/key-vault/general/overview) — secrets and keys.
- [Azure Monitor overview](https://learn.microsoft.com/azure/azure-monitor/overview) — metrics, logs, alerts, and release observation.
- [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/) — reliability, operational excellence, security, and cost.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — databases, compute, networking, and logs.

**Conclusion:** deploying database changes alongside application versions on Azure is a **multi-state compatibility and release orchestration problem**, not just executing one SQL file. Keep migrations in version control, bind them to **the same commit and release manifest** as the application, test both **old and new app versions** against expanded schemas, use a **least-privileged one-shot runner**, and verify history and data invariants before starting a canary. For breaking changes, use **expand → migrate/backfill → switch → contract** rather than direct renames or drops. Never treat **slot swaps, ACA revision rollbacks, Helm rollbacks, or PITR** as automatic schema undo buttons. A trustworthy release proves **the right database, right migration, right code, zero lost or duplicated data, backward-compatible old apps throughout the rollback window, and a rehearsed recovery plan ready when incidents strike**.

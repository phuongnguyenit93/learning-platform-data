# Handling Migration Failures and Limits of Rolling Back Data Changes

## 1. Why Is a Failed Migration a System Integration Incident?

In a Spring Boot application, migrations alter database structures or contents to serve a new application version. Flyway and Liquibase typically execute before database-dependent components become ready. If a migration fails, the application may fail to start; more seriously, part of the data may already have changed while older app versions, HTTP clients, caches, or message consumers continue operating.

For example, an ordering system converts statuses stored in **status_text** into **status_code**. After updating 600,000 out of 1 million orders, the migration encounters a legacy status lacking a mapping rule and halts. Even if you redeploy the previous application version, those 600,000 rows may still hold the new values. Reverting source code does not undo committed SQL statements.

This lesson focuses on three operational questions:

1. When a migration fails, **what state is the database currently in**?
2. Which operations can roll back transactionally, and which require forward fixes, compensation, or backup restoration?
3. How do you design migration workflows so partial failures remain verifiable, repeatable, and recoverable?

Scope covers Flyway/Liquibase, SQL transactions, batched data backfills, multi-version Spring Boot deployments, and integration flows spanning APIs, caches, and message brokers.

## 2. Distinguishing Transaction Rollback, Schema Rollback, and Data Recovery

These three operations address distinct problems:

| Concept | Meaning | Conditions and Limits |
| --- | --- | --- |
| **Transaction rollback** | Cancels **uncommitted** changes of the current transaction. | Applies only to operations supported by the database inside the same transaction; cannot undo already-committed transactions. |
| **Schema rollback** | Reverts structure to the prior shape, such as dropping a newly added column or reverting a data type. | Can destroy newly written data and may fail to reconstruct values lost during type conversion, column merging, or table drops. |
| **Data recovery/compensation** | Restores old values from backups, history, or audit logs; or executes compensating business actions. | Requires reliable authoritative data and must account for valid changes occurring after the migration. |

A migration often spans multiple steps: DDL changes, data updates, index creation, validation checks, application deployment, and downstream synchronization. **No single ACID transaction wraps all of these steps**, especially once messages are published, HTTP calls made, or caches cleared.

### Dependence on database engine and SQL statement type

| Environment | What Happens on Error | Recovery Implication |
| --- | --- | --- |
| PostgreSQL, DDL run inside a valid transaction | Most DDL and DML inside the **same uncommitted transaction** can roll back. | Still verify no prior transactions/batches committed. Statements like **CREATE INDEX CONCURRENTLY** cannot run inside a transaction block; failures can leave an invalid index behind. |
| MySQL, many DDL types | DDL typically triggers **implicit commits**. MySQL 8 *atomic DDL* keeps single DDL operations crash-consistent, yet **does not allow** operators to ROLLBACK a completed DDL statement. | Inspect physical tables, columns, and indexes; never assume based on a ROLLBACK command result. |
| Batched DML committing per batch | The failing batch may roll back while earlier batches remain committed. | Requires checkpoints, repeatable statements, and reconciliation queries. |
| Migrations calling HTTP, emitting events, or updating caches | Database transactions do not undo external side effects. | Use idempotency, outbox, corrective events, or controlled compensating actions. |

**Rule:** before choosing rollback, know your database engine, version, DDL/DML types, transaction boundaries, and what already committed. Never assume the migration tool guarantees full rollback.

## 3. Identifying Exact State After Failure

There are at least four distinct failure patterns:

- **Pre-change failure:** migration failed config checks, checksums, privileges, or syntax validation. The database may be untouched.
- **Failure inside a rollbackable transaction:** changes in the failing transaction rolled back, though earlier migrations or transactions remain committed.
- **Failure after partial commits:** non-transactional DDL, committed backfill batches, or halting halfway across multiple changesets. Schema and data are left in an intermediate state.
- **Technically successful yet semantically wrong migration:** SQL finished and the tool recorded success, yet data mapping was wrong or incompatible with the new app. This is still a migration incident despite zero SQL errors.

### Reading migration tool state

For **Flyway**, inspect migration logs, version lists, and statuses via:

~~~bash
flyway info
~~~

With read access to the history table, query:

~~~sql
SELECT installed_rank, version, description, success, installed_on
FROM flyway_schema_history
ORDER BY installed_rank DESC;
~~~

The history schema/table name may be customized. On databases supporting transactional DDL, a failed migration that rolled back may **not insert** a failed record in history; absence of a failed row does not prove nothing went wrong elsewhere.

For **Liquibase**, inspect change logs, executed changesets in **DATABASECHANGELOG**, and lock state in **DATABASECHANGELOGLOCK**. Each changeset can carry its own transaction boundary; multiple changesets in one update do not necessarily share a single transaction.

**Do not immediately run** Flyway **repair**, Liquibase **changelogSync**, manual history edits, or force-unlock locks at all costs. Metadata operations are safe only after verifying physical impact. For example, **flyway repair** adjusts history/checksum metadata in supported cases, yet **never undoes SQL**, recreates dropped columns, or fixes corrupted data.

### Reconciling against real database state

Run read-only queries to verify:

1. Which tables, columns, indexes, and constraints exist and whether they are valid.
2. Counts of processed rows, remaining rows, and rows violating business invariants.
3. The last committed migration or batch; whether any instance is still running migrations or mutating data.
4. Whether backups, transaction logs/PITR, audit logs, event logs, or source data suffice for recovery.
5. Which contract versions APIs, background jobs, and consumers are using, and whether new records arrived during the broken state.

Preserve the failure timestamp, app version, migration version, SQL error/SQLState, job logs, and reconciliation queries. Errors such as **duplicate key**, **NOT NULL violation**, **lock timeout**, **checksum mismatch**, and **disk full** call for different remediations.

## 4. Incident Response Workflow in Safe Order

~~~mermaid
flowchart TD
    A[Migration fails or validation checks fail] --> B[Isolate versions and stop failing write jobs]
    B --> C[Capture state: logs, history, schema, data, backups]
    C --> D{Changes committed?}
    D -->|No| E[Fix root cause and re-test migration]
    D -->|Partial or full| F{Can forward-fix preserve valid data?}
    F -->|Yes| G[Supplemental migration and idempotent backfill]
    F -->|No| H[Selective restore from backup/PITR or compensation]
    E --> I[Reconcile invariants and dry-run]
    G --> I
    H --> I
    I --> J[Verify app compatibility and resume in phases]
~~~

**Step 1 — Contain impact.** Halt the failing migration pipeline or backfill worker; determine whether related writes must pause or traffic must shift. If the system can continue serving safely on an expanded schema, preserve healthy service paths. Never launch multiple instances simultaneously to retry the same broken migration.

**Step 2 — Preserve evidence and recoverability.** Save logs, schema state, checkpoints, and affected row ranges. Verify existing backups and, where appropriate, take a snapshot before further edits. Never wipe migration history or drop broken tables before understanding their contents.

**Step 3 — Diagnose root cause.** Separate script bugs, legacy data violating assumptions, database privileges, disk exhaustion, long locks, network drops, or dual-version app conflicts. Fix the actual cause; never drop constraints just to "make the migration green" when constraints protect real invariants.

**Step 4 — Choose recovery strategy.**

| Investigation Finding | Usually Appropriate Action |
| --- | --- |
| Nothing changed; transaction rolled back cleanly | Fix unapplied migration and rerun after testing. |
| Column added cleanly; backfill incomplete and old column intact | Complete data using idempotent batches; keep app compatible during transition. |
| Wrong mapping overwrote old data, yet reliable audit/backup exists | Reconcile row-by-row from backup or write a forward-fix migration from authoritative source. |
| Column/table dropped or lossy conversion destroyed source info | Evaluate backup/PITR and post-error writes; exact recovery may be impossible without source data. |
| Tool logged failed migration after DDL already committed | Fix physical schema/data first; only then clean metadata via official tool commands. |

**Step 5 — Verify and reopen safely.** Run data reconciliation, migration validation, critical read/write tests, health checks, and producer/consumer compatibility tests. Monitor app errors, SQL latency, queue lag, and unmigrated row counts. Document root cause and remediation steps.

## 5. Example: Order Migration Halts Mid-Backfill

Suppose the **orders** table has:

- **id**: integer primary key.
- **status_text**: legacy values **new**, **paid**, **cancelled**.
- The new app expects **status_code** with values **NEW**, **PAID**, **CANCELLED**.
- Production data also contains unspecified rows with **refund_pending**.

Follow **expand → migrate → contract** to separate compatible changes from dropping data.

### Phase A — Expand: add structure without forcing immediate use

Example Flyway migration **V41__add_order_status_code.sql** on PostgreSQL:

~~~sql
ALTER TABLE orders
  ADD COLUMN status_code VARCHAR(20);
~~~

After this step, older code continues reading **status_text**. Deploy a Spring Boot app version aware of both columns: temporarily reading the old column while writing both old and new values inside **the same database transaction**. During rolling deployment, account for older instances still writing only the old column.

### Phase B — Migrate: update in repeatable batches

Example batch handling IDs **100001–110000**:

~~~sql
BEGIN;

UPDATE orders
SET status_code = CASE status_text
    WHEN 'new'       THEN 'NEW'
    WHEN 'paid'      THEN 'PAID'
    WHEN 'cancelled' THEN 'CANCELLED'
  END
WHERE id >= 100001
  AND id < 110001
  AND status_code IS NULL
  AND status_text IN ('new', 'paid', 'cancelled');

COMMIT;
~~~

The **status_code IS NULL** predicate makes batches safe to re-run without overwriting values written by the new app. Record each ID range/checkpoint **after commit**; checkpoints track progress only and do not replace row-level state checks. With concurrent workers, partition ID ranges or lock rows appropriately, throttle load, and watch for deadlocks/lock timeouts.

Note: this script **intentionally avoids guessing** what **refund_pending** means. After batches finish, an inspection query spots unmapped rows:

~~~sql
SELECT status_text, COUNT(*) AS remaining_rows
FROM orders
WHERE status_code IS NULL
GROUP BY status_text
ORDER BY remaining_rows DESC;
~~~

Add mappings only after confirming business rules. If **refund_pending** maps to **REFUND_PENDING**, update contracts, code, and backfill scripts before resuming. If historical rows are genuinely corrupt, fix from an authoritative source instead of masking with inaccurate defaults.

Once all values are handled, reconcile even rows where **status_code** is populated wrongly:

~~~sql
SELECT COUNT(*) AS inconsistent_rows
FROM orders
WHERE status_text IS NULL
   OR status_text NOT IN ('new', 'paid', 'cancelled', 'refund_pending')
   OR status_code IS DISTINCT FROM CASE status_text
       WHEN 'new'            THEN 'NEW'
       WHEN 'paid'           THEN 'PAID'
       WHEN 'cancelled'      THEN 'CANCELLED'
       WHEN 'refund_pending' THEN 'REFUND_PENDING'
       ELSE NULL
     END;
~~~

The query uses PostgreSQL **IS DISTINCT FROM** for safe **NULL** comparison. Expected result is **0**, assuming this mapping matches business truth. Repeat the check after old writers stop and before switching reads to the new column.

### Phase C — Contract: enforce constraints and drop old column only when safe

Once all writers populate **status_code**, inconsistent rows equal 0, and consumers are compatible, add constraints in a separate migration. PostgreSQL example:

~~~sql
ALTER TABLE orders
  ADD CONSTRAINT orders_status_code_required
  CHECK (status_code IS NOT NULL) NOT VALID;

ALTER TABLE orders
  VALIDATE CONSTRAINT orders_status_code_required;
~~~

A **NOT VALID** constraint defers checking historical rows while enforcing rules on new writes immediately; therefore do not add it while old writers still write only **status_text**. Verify locking behavior and duration on realistic data. Drop **status_text** only in a subsequent release once zero apps, reports, consumers, or jobs depend on it and after sufficient observation.

### What if failure strikes at 60% progress?

Suppose 600,000 rows committed and the next batch fails. At this point:

1. The failing batch's transaction can roll back, while 600,000 committed rows keep **status_code**.
2. There is no need to "undo" 600,000 rows if the new column is valid, the old column remains intact, and transition compatibility holds.
3. Identify unhandled rows, add the approved mapping, and re-run batches idempotently.
4. If wrong mappings were written to those 600,000 rows, **WHERE status_code IS NULL** will not fix them automatically. Write a conditional corrective migration using authoritative source/audit data, check interactions with valid post-migration updates, and re-reconcile.

Crucially, **"repeatable" and "self-correcting" are two different properties**. Idempotency avoids duplicate edits, whereas fixing corrupted data requires knowing the true source state.

## 6. Why Can't Migrations Simply Be Reversed?

| Applied Change | Reversible via Inverse SQL? | Risks to Evaluate |
| --- | --- | --- |
| Add new column with no writes yet | Usually droppable if zero dependencies verified | Loses new data if any writer started using it. |
| Rename column | Reversible in some cases | Running apps/queries may already expect the new name; breaks rolling compatibility. |
| Convert string to number | Only if mapping is deterministic and lossless | `"00123"` and `"123"` collapse to one value; original formatting lost. |
| Merge two fields, normalize strings, round numbers | Usually cannot reconstruct exact originals | Many-to-one transformation; requires source data, audit logs, or backups. |
| Drop column, DROP/TRUNCATE table | Recreating schema does not restore content | Must recover from backups, event logs, or another authoritative store. |
| Publish messages or call external services | No SQL ROLLBACK exists for external systems | Consumers may already have processed emails, inventory deductions, or payments. |

A rollback script like **DROP COLUMN status_code** may succeed syntactically yet remain a disastrous decision if the app wrote new orders exclusively into that column.

**Restoring the entire database to a pre-migration timestamp** also has limits: valid orders or transactions created after the restore point risk being lost. In live systems, it is often safer to restore backup/PITR into a **separate database**, reconcile by business key, and patch selectively rather than overwriting production outright. Final choice depends on RPO/RTO and business integrity.

## 7. Designing Recoverable Migrations

### 7.1. Define invariants and reconciliation checks upfront

A solid migration specifies:

- **Preconditions:** tables/columns exist; legacy value set is understood; migration account has grants; disk space and lock budgets are sufficient.
- **Invariants:** each order keeps its ID, owner, and amount; new statuses preserve business meaning; row counts stay unchanged during backfills.
- **Postconditions:** zero unmapped rows remain, zero old/new conflicts, constraints valid, API reads/writes healthy.
- **Stop triggers:** halt migration on unknown values, mapping errors, abnormal lock wait spikes, or row count discrepancies.

Never verify only "SQL exited 0"; check **actual data contents** after each phase and after traffic cutover.

### 7.2. Batched, checkpointed, idempotent backfills

Avoid multi-hour transactions holding locks, bloating WAL/binlogs, and complicating recovery. Slice work into bounded batches, commit per batch, record progress, and resume cleanly from remaining rows. Tie checkpoints to migration versions and work scopes, never confusing "batch ran" with "batch produced **accurate** data."

Backfill queries should rely on stable keys and deterministic predicates, not run counts. Use row locking, range partitioning, or **FOR UPDATE SKIP LOCKED** where supported and multi-worker concurrency is truly needed. Monitor throughput, per-batch errors, and critical query latencies.

In Spring Boot, wrap transactions around **small atomic units of work** per batch. **@Transactional** applies only within Spring-managed transactions and enlisted resources; it cannot make non-transactional DDL rollbackable or undo HTTP/broker side effects.

### 7.3. Separate schema changes from long data conversions

Versioned migrations suit small, fast, predictable schema changes. For millions of rows, favor a dedicated, managed backfill job with progress tracking, pause/resume, and monitoring. Never attach a multi-hour backfill to every Spring Boot instance's startup path.

If using Flyway/Liquibase at startup, verify migration locking and deploy settings. For large workflows, run migrations in a **dedicated pipeline job**, then launch app instances against the ready schema—disabling duplicate startup migrations in the app configuration.

### 7.4. Two-way compatible application rollouts

During rolling deployments, old and new code may run together. Thus:

1. **Expand:** add columns/tables or event fields while older clients/consumers continue working.
2. **Migrate:** update writers, apply controlled dual-write or adapter conversion, backfill, and reconcile.
3. **Switch:** flip reads/feature flags once data and consumers align, keeping safe fallback while old data remains complete and consistent.
4. **Contract:** remove compatibility shims, old columns, or old event fields in a later release.

With caches, manage keys/versions/TTLs and invalidation so old entries aren't misread under the new schema. With events, version contracts, keep consumers able to read both old and new formats across transitions, and use the **outbox pattern** when DB persistence and event emission must not drift apart after crashes. Outbox still requires idempotent consumers because events can be delivered more than once.

### 7.5. Prepare recovery before destructive changes

Before **DROP**, **TRUNCATE**, merging fields, or lossy type conversions, confirm:

- Tested backups/PITR exist, knowing restore points and impact on newer writes.
- Reconciliation keys, audit history, or source snapshots exist for selective fixes.
- All old-schema reads/writes have stopped; compensation exists if data propagated to external systems.
- Clear authority exists on who halts migrations, triggers maintenance mode, or reopens traffic.

## 8. Scoping Flyway and Liquibase Properly in Spring Boot

Example config when the app allows Flyway on startup:

~~~yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

**ddl-auto: validate** verifies entity mappings against the expected schema instead of letting Hibernate alter structure. When Liquibase is the primary tool, configure Liquibase equivalently and prevent both tools from managing the same schema unintentionally.

**With Flyway:**

- Inspect versions, checksums, and states via **info/validate**. Never modify already-executed versioned migrations across environments; add a new corrective migration.
- On failed migrations, inspect committed SQL and physical schema before running **repair**. History repair fixes metadata only, not partial data.
- Isolate statements incompatible with transactions and configure execution per database. Never treat transaction support as uniform across all scripts.

**With Liquibase:**

- Keep changesets small, use appropriate preconditions, and pay attention to **runInTransaction** plus DBMS/statement transaction support. Auto-generated rollbacks are not always available or safe; destructive data edits require dedicated recovery plans.
- Check **DATABASECHANGELOG**, lock states, and changeset outcomes. Clear stale locks only after proving no Liquibase process is active.
- Never use **changelogSync** to mark changesets executed merely to bypass errors without verifying schema, data, and justification.

**With both:** never declare "success" just because migration history looks clean. Definition of done requires data reconciliation, app compatibility, and healthy operational signals.

## 9. Testing Before Production Execution

A useful test plan represents real data and realistic failures:

| Scenario | Outcome to Verify |
| --- | --- |
| Clean DB or prior version; normal migration | Schema/version right; data invariants hold; app starts and reads/writes cleanly. |
| Outliers, nulls, duplicate keys, overflows, or unknown states | Migration halts with clear diagnostics; valid rows remain uncorrupted. |
| Kill job after a few batches commit, then restart | Zero duplication, loss, or overwriting; progress and final reconciliation succeed. |
| Constraint/lock timeout/disk pressure at any step | Commit boundary known, intermediate state verifiable, clear recovery action works. |
| Two app versions running concurrently | Old/new writers and readers agree on data; read-flag toggles and app rollbacks lose no data. |
| Message redeliveries, stale caches, slow consumers | Consumers stay idempotent, contracts compatible, metrics catch drift. |
| Backup/PITR recovery needed | Test restore into isolated environment; measure duration and verify replaying valid newer writes. |

When testing on production-like volumes, measure table/index sizes, lock durations, replication lag, WAL/binlog growth, I/O cost, and pipeline timeouts. Never rely solely on a tiny fixture of a few "happy-path" rows.

## 10. Short Runbook When a Migration Reports FAILED

1. **Record:** migration/version, environment, timestamp, SQLState, logs, app build, and active instances.
2. **Contain:** pause the failing executor and determine which writes must be restricted to avoid further corruption.
3. **Verify:** inspect Flyway/Liquibase history, physical schema, committed batches, inconsistent rows, and backup/PITR status.
4. **Select remediation:** retry after true rollback; forward-fix if source data remains intact; selective restore/compensation if data was lost or leaked externally.
5. **Execute with control:** dry-run on equivalent staging state, checkpoint, monitor errors, and enforce stop conditions.
6. **Reconcile and reopen:** check row counts, invariants, APIs/consumers, caches, lag, and health checks; update incident postmortem.

### Actions to avoid

- Re-running migrations repeatedly or restarting the cluster without knowing which statements committed.
- Running **repair**, editing history tables, or dropping constraints solely to clear warnings.
- Modifying/deleting migrations already applied in other environments, causing checksum and history divergence.
- Rolling back or redeploying old code assuming the data reverted too.
- Dropping the old column right after a backfill batch finishes while old writers/consumers remain active.
- Restoring over all of production without accounting for valid transactions committed after the backup.

## 11. Takeaways

**A failed migration is fundamentally a problem of determining true state and preserving data correctness.** Versioning tools track which scripts were expected to run, yet do not guarantee reversibility of every change. Safe migration design relies on verifiable source data, compatible rollout phases, idempotent batches, checkpoints, operational observability, and tested recovery plans before executing irreversible changes.

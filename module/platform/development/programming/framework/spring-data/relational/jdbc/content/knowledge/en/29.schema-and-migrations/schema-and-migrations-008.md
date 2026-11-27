# Deploying Schema Changes Compatible with Multiple Application Versions

During a rolling deployment, application instances do not switch to the new version at the exact same moment. Some instances still run the old version while others already run the new version; background jobs, message consumers, and integration processes may also upgrade on separate schedules.

If the new version immediately requires a different schema, old instances can fail while continuing to read or write the database. Conversely, if a migration drops or renames a column too early, running old versions can break.

The common approach is **expand-migrate-contract** (also known as expand-and-contract):

1. **Expand:** extend the schema in a way the old version can still use.
2. **Migrate:** deploy compatible code, migrate data, and validate the new data.
3. **Contract:** remove old structures only after every related application and process has stopped using them.

The goal is preserving compatibility throughout the period when multiple versions coexist. This lesson covers planning, column rename/split examples, dual-writing, batched backfills, database constraints, rollout, rollback, and compatibility testing.

## 1. Why Do Multiple Application Versions Access One Schema Simultaneously?

A production system typically does not halt all traffic for deployments. In a rolling deployment, the orchestrator replaces instances one by one:

~~~text
Time T1
    App instance A: version 1
    App instance B: version 1
    App instance C: version 1

Time T2
    App instance A: version 2
    App instance B: version 1
    App instance C: version 1

Time T3
    App instance A: version 2
    App instance B: version 2
    App instance C: version 1

Time T4
    App instance A: version 2
    App instance B: version 2
    App instance C: version 2
~~~

During times T2 and T3, both versions access the same database schema concurrently.

Beyond web instances, there may also be:

- Message-processing workers.
- Scheduled jobs and batch imports.
- Change data capture (CDC) consumers.
- Other services sharing the database.
- Operational or reporting scripts.
- Older application versions still running in another region.

Therefore, "the new version is fully deployed" must be evaluated across the entire system, not merely web instance counts.

### 1.1. What Is Schema Compatibility?

A schema is compatible with multiple versions when each version can continue performing the operations it requires during the rollout window.

Example:

- The old version only knows column `customer_name`.
- The new version needs column `display_name`.
- During transition, both columns coexist.
- Intermediate code keeps data consistent so both versions work.

There is no universally "backward-compatible" schema for every change. You must explicitly identify which versions and read/write flows must work during the transition period.

### 1.2. Compatibility Matrix

Before deploying, build a table for every version and schema pair:

| Schema | Old App V1 | Transition App V2 | New App V3 |
|---|---|---|---|
| S1: old column only | Works | Fails if V2 requires new column | Fails |
| S2: both old and new columns | Works | Works | Works |
| S3: new column only | Fails | May fail | Works |

S2 is the intermediate schema needed during rolling deployment. S3 is deployed only after V1 and V2 have stopped accessing the old column, including jobs and consumers.

## 2. Expand-Migrate-Contract

These three phases separate structural additions, data conversion, and removal of old structures.

~~~text
Old Schema + App V1
        |
        v
1. EXPAND
   Add new structures, keep old structures
        |
        v
Expanded Schema + App V1 still works
        |
        v
2. MIGRATE
   Deploy compatible code
   Dual-write / backfill / validate
        |
        v
Expanded Schema + new data ready
        |
        v
3. CONTRACT
   Stop using old structures
   Remove old code, then drop old structures
        |
        v
New Schema + New App Version
~~~

### 2.1. Expand

Add only structures that old code can safely ignore:

- Add nullable columns.
- Add new tables.
- Add indexes in a database-appropriate way.
- Add constraints in a way that can be validated separately.
- Add new columns while retaining old ones.
- Add views or supporting transition structures.

Avoid renaming or dropping columns right away in this phase. Old apps may still depend on existing table and column names.

### 2.2. Migrate

Introduce new code that still supports the transitional schema. Depending on the use case, this phase may include:

- Writing both old and new columns.
- Reading the old column as primary, or reading the new column with controlled fallback.
- Backfilling legacy data to the new structure.
- Reconciling row counts and values.
- Enabling new behavior via feature flags once data is ready.
- Waiting for all old instances, jobs, and consumers to be replaced.

### 2.3. Contract

Execute only once no code depends on the old structures:

- Stop writing the old column.
- Stop reading the old column.
- Remove compatibility and fallback code.
- Confirm no queries, reports, jobs, or consumers use the old structure.
- Drop old columns/tables/indexes in a separate migration.

Contract is typically shipped in a later release. Separating it provides observation time and preserves the ability to roll back the application during transition.

## 3. Example: Renaming Column `customer_name` to `display_name`

Suppose the current table is:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);
~~~

App V1 reads and writes `customer_name`:

~~~java
String name = jdbcClient
        .sql("""
            SELECT customer_name
            FROM customers
            WHERE id = :id
            """)
        .param("id", customerId)
        .query(String.class)
        .single();
~~~

The new version wants to use column name `display_name`. A migration that simply renames the column:

~~~sql
ALTER TABLE customers
RENAME COLUMN customer_name TO display_name;
~~~

would immediately break App V1 when it continues querying `customer_name`.

### 3.1. Expand Step: Add the New Column

Create the first migration:

~~~sql
ALTER TABLE customers
    ADD COLUMN display_name VARCHAR(200);
~~~

After the migration, the schema has both columns:

~~~text
customers
+----+---------------+--------------+
| id | customer_name | display_name |
+----+---------------+--------------+
| 10 | An Nguyen     | NULL         |
+----+---------------+--------------+
~~~

App V1 keeps reading/writing `customer_name`. The new column does not require values yet, so V1 is unaffected.

### 3.2. Migrate Step: Deploy the Bridge Version

App V2 can write both columns in a single statement:

~~~sql
UPDATE customers
SET customer_name = :name,
    display_name = :name
WHERE id = :id;
~~~

Or on insert:

~~~sql
INSERT INTO customers (
    id,
    customer_name,
    display_name
)
VALUES (
    :id,
    :name,
    :name
);
~~~

While V1 and V2 run together, V1 writes only the old column. Therefore V2 cannot yet treat `display_name` as the sole source of truth.

A safe sequence:

1. Expand schema, keep old column.
2. Deploy V2 bridge; V2 still reads `customer_name`, yet writes both columns.
3. Wait for all V1 web instances, workers, jobs, and consumers to stop.
4. Backfill rows where `display_name` is still NULL.
5. Reconcile data and confirm no missing rows remain.
6. Deploy V3 reading `display_name`, while still writing both columns during the rollback window.
7. Wait for all V2 bridge instances to shut down.
8. Deploy V4 reading/writing only `display_name`.
9. Once the rollback window passes and zero consumers remain on the old column, drop `customer_name` in a separate release.

Why wait for V1 to stop writing before backfilling: if the backfill copies old data to the new column while V1 continues updating `customer_name`, `display_name` can immediately become stale right after the backfill passes that row.

### 3.3. Contract Step: Drop the Old Column

Once all code has moved to `display_name`, create the contract migration:

~~~sql
ALTER TABLE customers
    DROP COLUMN customer_name;
~~~

Never combine this drop migration into the initial release that adds `display_name`. Under instance-by-instance rollouts, old code can still run after the migration executes.

## 4. Example: Splitting `full_name` into `first_name` and `last_name`

Structural data changes are more complex than renames. Old schema:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);
~~~

The new schema needs `first_name` and `last_name`.

Do not drop `full_name` and add two new columns in a single migration while App V1 is still active.

### 4.1. Expand Schema

~~~sql
ALTER TABLE customers
    ADD COLUMN first_name VARCHAR(100),
    ADD COLUMN last_name VARCHAR(100);
~~~

App V1 continues reading/writing `full_name`.

### 4.2. Define Data Conversion Rules

Splitting names is not always simple string slicing. For example:

- Nguyen Van An
- Mary Jane Watson
- Jean-Claude Van Damme
- Single-word names.
- Names with leading/trailing whitespace.
- Names with Unicode characters or differing cultural naming orders.

Before backfilling, the business must define what `first_name` and `last_name` mean. If names cannot be split accurately, retain `full_name` or store a separate display name field to avoid losing information.

### 4.3. Bridge App Writes All Three Fields

~~~java
jdbcClient.sql("""
        UPDATE customers
        SET full_name = :fullName,
            first_name = :firstName,
            last_name = :lastName
        WHERE id = :id
        """)
    .param("fullName", fullName)
    .param("firstName", firstName)
    .param("lastName", lastName)
    .param("id", customerId)
    .update();
~~~

During transition, V2 can keep reading `full_name` so it does not depend on unbackfilled new data. Once V1 stops writing, legacy data can be converted into the two new columns.

### 4.4. Backfill and Verify

After V1 no longer writes `full_name`:

~~~sql
UPDATE customers
SET first_name = :derived_first_name,
    last_name = :derived_last_name
WHERE id = :id
  AND first_name IS NULL
  AND last_name IS NULL;
~~~

The NULL predicates allow the process to re-run without overwriting new values already written by the application.

After backfilling, identify rows that could not be converted and resolve them per business rules. Never set `NOT NULL` until all valid rows hold data.

## 5. Dual-Write and Dual-Read

Dual-write writes the same change to both old and new structures. Dual-read reads from the new structure with optional fallback to the old structure during transition.

These are useful techniques, but you must clearly define the authoritative source of truth at every phase.

### 5.1. Dual-Write

Example:

~~~sql
UPDATE customers
SET customer_name = :name,
    display_name = :name
WHERE id = :id;
~~~

Both columns are updated in the same statement, so they commit or roll back together. If writing via two separate statements, they must execute inside the same transaction and handle partial failure.

Dual-write carries several risks:

- A code path writes only the old column.
- A batch job forgets to update the new column.
- Two values are computed by diverging rules.
- Non-idempotent retries produce corrupted data.
- Two application versions write simultaneously without agreeing on the primary source.

Centralize dual-write logic in a clear adapter or service, and test every write path.

### 5.2. Dual-Read with Fallback

Read example:

~~~sql
SELECT COALESCE(display_name, customer_name) AS effective_name
FROM customers
WHERE id = :id;
~~~

Fallback lets new code read unbackfilled rows.

However, `COALESCE` does not resolve conflicts when both columns hold different values. Define which column is authoritative during the current phase.

Do not keep fallback forever. Once new data is verified and all writers have switched, remove the fallback so it does not mask missing or inconsistent data.

### 5.3. Source-of-Truth Matrix

| Phase | Primary read source | What must writers do? |
|---|---|---|
| Before expand | Old column | Write old column only |
| After expand, V1 still running | Old column | V2 writes both; V1 writes old only |
| After V1 drained, backfilling | Old column or fallback | V2 continues dual-writing |
| After backfill, read switch | New column | V3 reads new and continues dual-writing |
| After rollback window | New column | V4 writes new only |
| After contract | New column | No references to old column remain |

The critical rule is never to switch the read source to the new column before old writers stop updating the old source or an equivalent sync mechanism is active.

## 6. Batch Backfilling Large Datasets

A single UPDATE may work on small tables, but on large tables it can cause long transactions, extended locks, massive WAL growth, and heavy database load.

Split backfills into bounded batches.

PostgreSQL example using increasing IDs:

~~~sql
UPDATE customers
SET display_name = customer_name
WHERE id > :fromId
  AND id <= :toId
  AND display_name IS NULL;
~~~

A worker processes each ID range, committing after every batch.

~~~text
Batch 1: id 1       -> 10,000
Batch 2: id 10,001  -> 20,000
Batch 3: id 20,001  -> 30,000
...
~~~

### 6.1. Idempotency

Backfills should be safely re-runnable. Example:

~~~sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL;
~~~

If the job halts midway, the next run only processes rows lacking new values.

However, `IS NULL` works only when NULL truly means "not yet migrated." If NULL is a valid business value, use a migration status column or another predicate to distinguish states.

### 6.2. Do Not Overwrite Fresh Data

If the new application already wrote `display_name`, the backfill must not overwrite it with stale legacy data. The predicate:

~~~sql
AND display_name IS NULL
~~~

helps avoid overwriting populated new values.

If the source column can still change during the backfill, put a sync strategy in place. Options include:

- Draining old writers before backfilling.
- Using a temporary old-to-new synchronization trigger.
- Using change logs/CDC to apply changes occurring during backfill.
- Recording a watermark and running a final reconciliation pass.

Do not pick triggers merely out of convenience. Triggers introduce hidden database logic that must be managed, tested, and removed after transition.

### 6.3. Controlling Batches

A well-operated backfill typically requires:

- Configurable batch size.
- Keyset/range pagination on a stable key.
- Per-batch commits.
- Retries for failed batches.
- Rate limiting to avoid overloading the database.
- Progress logging and checkpoints.
- Counts of rows read, updated, skipped, and failed.
- Pause/resume capability.
- Avoiding large `OFFSET` queries on mutating tables when keyset pagination is possible.

Never run a multi-million-row backfill inside startup migrations across every app instance. Extract it into an observable, controllable job.

## 7. Adding NOT NULL and Constraints Without Disruption

A common requirement is making an initially nullable column `NOT NULL`.

Do not apply `NOT NULL` before legacy rows are backfilled. Sequence:

1. Add column as nullable.
2. Deploy code writing the new value.
3. Backfill legacy data.
4. Verify no NULLs remain.
5. Add/validate constraint.
6. Once data and writers are stable, enforce `NOT NULL`.

Verification query:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS NULL;
~~~

When the count is 0, proceed with enforcing the constraint using syntax and strategy suited to your database.

### 7.1. PostgreSQL: Separate Constraint Validation

In PostgreSQL, you can add a CHECK constraint as `NOT VALID`, then validate it separately:

~~~sql
ALTER TABLE customers
    ADD CONSTRAINT customers_display_name_present
    CHECK (display_name IS NOT NULL) NOT VALID;
~~~

Afterward:

~~~sql
ALTER TABLE customers
    VALIDATE CONSTRAINT customers_display_name_present;
~~~

Once data is verified and on a suitable PostgreSQL version, you can finalize setting `NOT NULL`:

~~~sql
ALTER TABLE customers
    ALTER COLUMN display_name SET NOT NULL;
~~~

Exact strategy depends on PostgreSQL version, lock modes, and DDL duration. The statements above are PostgreSQL examples, not portable SQL for every database.

### 7.2. Adding Foreign Keys

On large tables, validating an FK can take significant time. PostgreSQL supports:

~~~sql
ALTER TABLE order_lines
    ADD CONSTRAINT fk_order_lines_customer
    FOREIGN KEY (customer_id)
    REFERENCES customers(id)
    NOT VALID;
~~~

Afterward:

~~~sql
ALTER TABLE order_lines
    VALIDATE CONSTRAINT fk_order_lines_customer;
~~~

This separates adding the constraint from scanning existing rows. Understand lock behavior and enforcement on new writes at each stage by checking database documentation.

## 8. Indexes and DDL That Can Cause Locks

Not every single-column migration is safe in execution time. DDL can:

- Wait on locks held by long-running transactions.
- Block queries or writes.
- Scan the entire table.
- Build indexes with heavy I/O cost.
- Spike WAL generation or replication lag.
- Prolong startup time if migrations run synchronously at boot.

In PostgreSQL, creating large indexes can use:

~~~sql
CREATE INDEX CONCURRENTLY idx_customers_display_name
    ON customers(display_name);
~~~

`CREATE INDEX CONCURRENTLY` has specific transaction rules and cannot run inside a normal transaction block. Configure your migration tool to support non-transactional execution for this statement.

Online index syntax and behavior vary across PostgreSQL, MySQL, SQL Server, and Oracle. Consult the docs for your deployed database/version instead of guessing from command names.

### 8.1. Avoid Competing Startup Migrations

If every application instance runs migrations on startup, migration tools use locks to protect migration history, yet that does not replace a deployment plan.

In production, it is usually easier to control when migrations run via a dedicated deployment job before or between rollout steps, and then activate the new application version.

Clarify:

- Who executes migrations?
- Do migrations run before or after app deployment?
- Can the migration be safely re-run?
- If the migration fails, does the old app still run?
- Are lock timeouts and statement timeouts configured?
- Are duration and replication lag monitored?

## 9. Organizing Migrations with Flyway or Liquibase

Spring Boot integrates with migration tools such as Flyway and Liquibase. These tools version schemas and apply migrations in order.

### 9.1. Flyway

Flyway commonly uses file-based versioned migrations:

~~~text
db/migration/
  V001__create_customers.sql
  V002__add_display_name.sql
  V003__add_customer_display_name_index.sql
  V004__remove_customer_name.sql
~~~

A migration already applied in a shared environment should be treated as immutable. When changes are needed, create a new migration rather than modifying an already-executed file.

Separate expand and contract phases into distinct migrations. Large backfills should usually be separate jobs rather than embedded inside startup DDL migrations.

### 9.2. Liquibase

Liquibase describes changes via changelogs and changesets. You can use preconditions, rollback definitions, and contexts/labels to organize changes by environment or phase.

Regardless of tooling, you must still design for compatibility. Migration tools only manage ordering and schema history; they do not automatically make old and new code coexist safely.

### 9.3. Migrations Are Part of the Release Plan

A release can span multiple steps:

| Release step | Schema | Application |
|---|---|---|
| R0 | Old schema | V1 |
| R1 | Expand: add new column | V1 |
| R2 | Expanded schema | V2 bridge |
| R3 | Backfill and validate | V2 bridge |
| R4 | Expanded schema, full new data | V3 reads new column, dual-writes |
| R5 | Stop using old column | V4 uses new column only |
| R6 | Contract: drop old column | V4 |

Schema migrations and application deployments are linked histories, though they do not need to occur inside a single deployment.

## 10. Rollback and Roll-Forward

An expand migration is usually easy to keep compatible with old apps. A contract migration may not be safely reversible.

For instance, once `customer_name` is dropped, legacy data is gone. If you need to roll back the app to V1, V1 code will fail because the column no longer exists.

Therefore:

- Keep the old column throughout the rollback window.
- Contract only after confirming no rollback to the old version is needed.
- Retain backups or snapshots per recovery policies.
- Prepare roll-forward migrations if issues are discovered after contract.
- Never assume a down migration can restore lost data.

### 10.1. Application Rollback vs. Database Rollback

You can roll back a container image from V3 to V2 while keeping the expanded schema. This is normally safe as long as the schema still supports both versions.

Conversely, rolling back the database from schema S3 to S2 may require restoring columns and recreating data. If new data was written into the new structure and cannot be reversed cleanly, a down migration cannot restore it accurately.

A sound plan favors **roll-forward** for irreversible schema changes: fix the issue with a new migration and deploy compatible application code.

### 10.2. Do Not Contract Too Early

The old column should only be dropped once:

- No old app instances remain.
- No workers, schedulers, consumers, or scripts use the old column.
- Dashboards/reports/ETL/CDC have switched over.
- Query logs or telemetry show zero accesses to the old column over a sufficiently long observation period.
- The rollback window has elapsed.
- Backfill and validation are complete.
- An appropriate recovery plan is ready.

## 11. Feature Flags During Transition

Feature flags decouple code deployment from enabling new behavior.

For example, App V3 can support two read paths:

~~~java
String name = useNewColumn
        ? customer.displayName()
        : customer.customerName();
~~~

In practice, column selection should live in a repository/adapter rather than scattering conditionals throughout the domain model.

A typical sequence:

1. Deploy code capable of using the new schema with the flag turned off.
2. Expand schema and backfill.
3. Verify new data.
4. Enable the flag for a subset of traffic or a single tenant.
5. Monitor errors, latency, and data integrity.
6. Gradually expand rollout.
7. Once stable, remove the legacy code branch in a subsequent release.

Feature flags do not replace schema compatibility. If V3 code requires the new column at startup, turning the flag off will not allow V3 to run against an unexpanded schema.

## 12. Components Outside the Web App Also Need Compatibility

A common mistake is checking only web instances. Yet a database may be accessed by many components.

| Component | Risk |
|---|---|
| Scheduled jobs | Legacy job runs after column is dropped |
| Message consumers | Old consumer processes legacy payload or schema |
| Batch imports | Writes data using legacy structure |
| Reports/BI | Queries or views depend on old column |
| CDC pipelines | Downstream mappings still expect old fields |
| Data exports | Un-updated operational scripts |
| Other services | Share the database but have independent release schedules |

Before contracting, discover all schema consumers. Use query logs, database audits, source searches, and system inventories to find dependencies outside the primary application repo.

When a database is shared across multiple services, treat the schema as a contract between producers and consumers. Provide notice, transition windows, and confirmation from consumer-owning teams before removing legacy structures.

## 13. Compatibility Testing Across Application Versions

Unit-testing each version individually does not prove a rolling deployment is safe. Test the app/schema pairs that can coexist.

### 13.1. Matrix Testing

Example for changing `customer_name` to `display_name`:

| Test case | Expected result |
|---|---|
| V1 on schema S1 | Works |
| V1 on schema S2 after expand | Works |
| V2 bridge on schema S2 | Works |
| V1 and V2 running together on S2 | Both read/write per transition rules |
| Backfill after V1 drains | No old write sources stale the new data |
| V3 on S2 after validation | Reads new column successfully |
| V2 and V3 running together on S2 | Both keep old/new data consistent |
| V4 on S2 | Works even though it uses only the new column |
| V4 on S3 after contract | Works |
| V1 on S3 | Unsupported; ensure zero V1 remains before contract |

### 13.2. Testing Migrations from Realistic Schemas

A useful test flow:

1. Initialize the database at the pre-migration schema version.
2. Seed representative data, including NULLs, Unicode, long strings, and boundary values.
3. Run the expand migration.
4. Run old app tests against the expanded schema.
5. Deploy the bridge app and test dual-writes.
6. Run the backfill.
7. Reconcile data.
8. Run the new app against the expanded schema.
9. Run the contract migration in a dedicated environment.
10. Verify the new app works once the old column is gone.

Use the same database engine and a version close to production. H2 may not accurately reproduce locks, DDL, constraints, collations, or type semantics of PostgreSQL/MySQL/SQL Server.

### 13.3. Testing Rollback

Test reverting to the previous application version while the schema stays in the expanded phase. No database rollback is needed if the expanded schema remains compatible.

Also test scenarios where an expand migration fails midway while the old app continues operating. Because DDL transaction semantics vary across databases, know what gets committed.

## 14. Observability During Rollout

Do not proceed to contract solely because the deployment dashboard shows 100% new instances.

Monitor:

- Running application versions per instance.
- Worker and consumer versions.
- Requests/statements still accessing the old column.
- NULL rate in the new column.
- Backfill row counts: succeeded, skipped, and failed.
- Drift between old and new column values.
- Query latency and error rates.
- Lock waits, deadlocks, and replication lag.
- Migration duration and constraint validation duration.

Check unmigrated rows:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS NULL;
~~~

And check whether the two columns differ:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS DISTINCT FROM customer_name;
~~~

`IS DISTINCT FROM` is PostgreSQL syntax for NULL-safe comparison. For other databases, use the appropriate equivalent.

A zero diff metric is not enough if new data might be written incorrectly by a conversion bug. Sample and verify business edge cases.

## 15. High-Risk Schema Changes

Several changes commonly need expand-contract or dedicated planning.

| Change | Risk on direct deploy | Approach |
|---|---|---|
| Rename column | Old app cannot find column name | Add new column, dual-write, backfill, switch reads, drop old later |
| Drop column | Old app or reports still access it | Confirm zero consumers remain, then contract |
| Split/merge column | Needs data transformation and business rules | Add fields, bridge code, backfill, validate |
| Change data type | Parsing/formatting or range differences | Add new column, controlled conversion |
| Add NOT NULL | Existing rows lack values | Add nullable, backfill, validate, enforce |
| Add FK | Existing data may violate reference | Audit and clean first, validate per DB capability |
| Add index | May lock or spike I/O | Use DB-appropriate online/concurrent index |
| Change enum/status | Old app cannot parse new value | Deploy readers supporting new values before writers emit them |
| Change JSON shape | Old consumers may fail parsing | Version payloads or support both formats |
| Change precision/scale | Data rounded or overflows | Check ranges and backfill before contract |

### 15.1. Adding a New Enum Value

Suppose the database has statuses `DRAFT`, `CONFIRMED`, `CANCELLED`, and the new version wants to add `ON_HOLD`.

If the old app parses enums with `Enum.valueOf`, it may crash when reading `ON_HOLD`.

Safe sequence:

1. Deploy readers able to understand the new status or handle unknown values.
2. Wait for all old readers to be replaced.
3. Enable writers to start emitting `ON_HOLD`.
4. Confirm consumers, reports, and integrations understand the status.

If the database uses a native enum type, migrations adding values must also consider engine semantics and rollback capabilities.

### 15.2. Changing Data Types

For example, changing `amount` from `INTEGER` to `NUMERIC(18,2)`. Old apps might read integer, while new apps write decimal.

You can add a new column, convert data, dual-write with explicit rounding rules, confirm zero precision loss, and only then drop the old column. Do not cast in place if conversion could cause overflow, rounding issues, or unacceptable locks.

## 16. Schema Compatibility Rollout Workflow

Before a production schema change, plan across these steps:

**Step 1 — Inventory consumers.** Identify every app, job, consumer, report, and script reading/writing the target table or column.

**Step 2 — Build a compatibility matrix.** Specify which schemas must support which app versions at each phase.

**Step 3 — Design the expand migration.** Add only structures compatible with current code; avoid immediate renames/drops.

**Step 4 — Deploy the bridge version.** New code must run on the expanded schema and maintain compatible behavior while old apps remain active.

**Step 5 — Drain old writers.** Confirm all versions writing only the old structure have shut down.

**Step 6 — Batch backfill.** Include checkpoints, retries, rate limits, idempotency, and progress logs.

**Step 7 — Validate.** Check NULLs, counts, sample values, invariants, and data discrepancies.

**Step 8 — Switch reads.** Shift gradually to the new structure, using feature flags if helpful; continue dual-writing during the rollback window.

**Step 9 — Drain bridge versions.** Confirm no code still needs the old column.

**Step 10 — Contract.** Remove compatibility code and old structures in a separate release.

**Step 11 — Observe and retain evidence.** Keep metrics, migration history, validation results, and recovery plans.

~~~text
Inventory consumers + versions
             |
             v
       Compatibility matrix
             |
             v
        EXPAND schema
             |
             v
      Deploy bridge version
             |
             v
      Drain old writers
             |
             v
       Batch backfill
             |
             v
    Validate new data
             |
             v
      Switch reads/writes
             |
             v
      Drain bridge version
             |
             v
       CONTRACT schema
             |
             v
     Monitor + recovery plan
~~~

## 17. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Renaming/dropping immediately in one migration | Old apps fail during rolling deployment | Expand-contract |
| Backfilling while old writers remain active | New values become stale after backfill | Drain old writers or use sync mechanism |
| Switching reads to new column too early | New apps read NULL or out-of-sync data | Backfill, validate, then switch |
| Dual-writing only in web requests | Legacy jobs/consumers still write only old column | Inventory all writers |
| Dual-writing two statements outside a transaction | One column updates while the other fails | Same statement or same transaction |
| Dropping old column right after new code deploy | No window left to roll back the app | Retain old structures through rollback window |
| Running large backfill at app startup | Slow startup, competing instances, DB overload | Extract into a dedicated job |
| Using large OFFSET for backfills | Slow and prone to skipping/duplicating mutating rows | Keyset/range pagination on a stable key |
| Editing an already-executed migration | Schema history diverges across environments | Create a new migration |
| Testing only new app on new schema | Misses cross-version failures in rolling deploy | Test the compatibility matrix |
| Monitoring only web instances | Legacy jobs/consumers still access old structures | Monitor all consumers |
| Believing rollback migrations are always safe | Cannot recover converted/deleted data | Retain old data, prepare roll-forward/recovery |

## 18. Reasoning Exercises

**Scenario A — Rename Column**

App V1 reads `customer_name`; App V2 reads `display_name`. Why can't the column be renamed right before starting a rolling deployment?

**Hint:** During rollout, V1 continues running and querying `customer_name`. That column must remain until all V1 consumers have drained.

**Scenario B — Backfill**

A job copies `customer_name` to `display_name`, yet a V1 instance still updates `customer_name`. What can happen?

**Hint:** The backfill may have already passed that row before V1 updated it. `display_name` will not reflect the new value. Drain old writers or synchronize changes via another mechanism.

**Scenario C — Dual-Write**

App V2 writes both old and new columns. If two UPDATE statements run in separate transactions and the second fails, what happens?

**Hint:** Data in the two columns can drift apart. Write in a single statement or single transaction and handle rollback.

**Scenario D — NOT NULL**

A new column was just added and legacy rows are not backfilled yet. Should `NOT NULL` be added immediately?

**Hint:** No. Add as nullable first, write new data, backfill, validate, and only then enforce the constraint.

**Scenario E — Rollback**

App V3 uses only the new column, yet the old column still exists in the database. Can the app roll back to the V2 bridge?

**Hint:** Yes, provided V2 remains compatible with the current schema and legacy data continued to be dual-written. This is why the old column is retained during the rollback window.

**Scenario F — External Consumers**

Web instances have switched to the new column, yet a BI report still queries the old column nightly. Can the old column be dropped?

**Hint:** Not yet. Reports are schema consumers too; migrate and verify them before contracting.

## 19. Key Takeaways

| Concept | Role |
|---|---|
| Rolling deployment | Multiple application versions coexist during rollout |
| Schema compatibility | Schema supports all versions that must operate concurrently |
| Expand | Add new structures while keeping old structures |
| Migrate | Bridge code, dual-write/read, backfill, and validate |
| Contract | Remove old code and schemas once zero consumers remain |
| Dual-write | Write old and new structures simultaneously |
| Dual-read | Read new structure, with optional fallback during transition |
| Backfill | Convert existing data to the new structure |
| Idempotency | Allows batches to be re-run safely |
| Compatibility matrix | Defines which app version/schema pairs must work |
| Feature flag | Controls when new behavior is activated |
| Rollback window | Period preserving the ability to revert to the prior app version |
| Roll-forward | Fix schema via new migration when safe reversal is impossible |
| Consumer inventory | List of every component reading/writing the schema |

**Multi-version compatible schema changes must be rolled out in phases.** Expand the schema first, introduce bridge code while old and new columns coexist, drain old writers before backfilling and validating data, switch gradually to the new structure, and contract last. Retain old columns through the rollback window, test every app/schema pair, and account for jobs, consumers, reports, and other services in your plan.

## References

- [Flyway — Versioned migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): organizing migrations by version and managing schema history.
- [Liquibase — Changesets](https://docs.liquibase.com/concepts/changelogs/changeset.html): changelogs, changesets, and managing change ordering.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): altering table structure, locks, and validating constraints.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): creating indexes and `CONCURRENTLY`.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `CHECK`, `NOT NULL`, foreign keys, and constraint validation.

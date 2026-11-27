# Compatible Schema Changes When Multiple Application Versions Coexist

In Spring Data Relational R2DBC systems, application deployments rarely happen instantaneously across every instance. During rolling deployments, blue-green deployments, or autoscaling, old and new versions can access the same database simultaneously for a period of time. Therefore, a schema migration must remain compatible with both versions throughout the transition window.

For example, the old version reads and writes the `full_name` column, while the new version wants to switch to `display_name`. If a migration renames the column immediately, still-running old instances will throw SQL errors. If the old column is dropped before every new instance switches to the new column, an in-flight request or an old worker can fail.

A common strategy is **expand-contract**: expand the schema in a backward-compatible way, deploy code that operates with the transitional schema, migrate data and traffic, and only then contract the schema once no old consumers remain. The goal is for every deployment step to have a database state understood by all active application versions.

## 1. Why Coexisting Versions Make Migrations Harder

A rolling deployment typically follows this sequence:

```text
Time T0: only application v1 is running
    |
    v
T1: start deploying v2
    |  v1 and v2 run concurrently
    |
    v
T2: some instances are v2, the rest remain v1
    |  both read/write the database
    |
    v
T3: all web instances are v2
    |  workers, consumers, scheduled jobs may still be v1
    |
    v
T4: all old consumers have been replaced or stopped
    |
    v
T5: old schema elements can be removed once verified safe
```

During T1–T3, the database can receive SQL statements from multiple code versions:

- Old code may INSERT without knowing the new column exists.
- New code may read the new column while legacy rows have not yet been backfilled.
- Old code may continue writing the old column after new code already wrote the new column.
- A long-running old worker may write data after web instances have been upgraded.
- A transaction started before deployment may finish after migration or traffic switching occurs.
- A message consumer may use an older schema or payload longer than an HTTP request lifecycle.

Hence, "v2 deployment finished" does not necessarily mean all old code has stopped accessing the database. Inventory web instances, background workers, schedulers, consumers, batch jobs, admin scripts, and any other applications sharing the schema.

## 2. The Expand-Contract Principle

Expand-contract splits a breaking change into small steps where each step keeps both schema and code compatible with active versions.

<text weight="semibold">Expand Phase</text>

- Add new columns, tables, indexes, or structures so old code keeps working.
- Deploy new code capable of reading/writing both old and new schemas during the transition.
- Backfill historical data into the new structure in batches.
- Switch reads and writes to the new structure once data is ready.

<text weight="semibold">Contract Phase</text>

- Confirm no instances, workers, or jobs still rely on the old structure.
- Stop writing to the old structure and observe for an appropriate period.
- Drop old columns/tables/indexes or tighten constraints once safe.

Example renaming `full_name` to `display_name`:

```text
Initial schema
  customer.full_name
        |
        v
EXPAND: add customer.display_name (nullable)
  full_name       display_name
  v1 reads/writes v2 can write both
        |
        v
BACKFILL: copy full_name -> display_name
        |
        v
SWITCH: v2 reads display_name, temporarily continues dual-write
        |
        v
DRAIN: stop all v1 instances and consumers still using full_name
        |
        v
CONTRACT: stop writing then drop full_name
```

The crucial rule is never to combine "add new structure" and "drop old structure" in the same migration before code has fully transitioned.

## 3. Schema Compatibility Between Old and New Versions

A change is only safe when running code can keep performing required operations against the post-migration schema. Use the following matrix to evaluate:

| Schema State | Application v1 | Application v2 |
|---|---|---|
| Old schema | Works normally | May fail to run if v2 requires new column |
| Expanded schema, keeping old column and adding new column | Must keep working | Must work with both new and legacy data |
| Schema during dual-write/backfill | Allowed to write old structure | Reads/writes via transition strategy |
| Contracted schema, old column removed | No longer compatible | Works on new schema |

Therefore, deployment order is usually expand migration first, then deploy application v2. The expand migration must never require v1 to know about the new column. The contract step may only run once v1 is no longer permitted to execute.

### 3.1. Backward and Forward Compatibility

- **Backward compatibility:** new code can work with the old schema or old data during the transition.
- **Forward compatibility:** old code continues working after the schema has been expanded by the new migration.

In rolling deployments, forward compatibility of the expanded schema is especially vital because old code is still running. New code must also handle legacy rows not yet backfilled.

Not every change needs both directions at all times, but you must know exactly which version accesses which schema before deploying.

## 4. Safely Adding a New Column

Suppose `display_name` must be added to `customer`, while the old version only knows `name`.

An expand migration can add a nullable column:

```sql
ALTER TABLE customer
ADD COLUMN display_name VARCHAR(200);
```

Adding a nullable column usually has minimal impact on old code because INSERT statements omitting the new column still succeed and receive NULL. However, lock levels, DDL duration, and physical impact depend on the database, version, and table size. Check documentation for the target database engine.

New code must handle rows lacking `display_name`:

```java
public String effectiveDisplayName(Customer customer) {
    if (customer.getDisplayName() != null) {
        return customer.getDisplayName();
    }

    return customer.getName();
}
```

During the transition, read the new column if present, otherwise fall back to the old column. After backfilling completes and all writers populate the new column, code can drop the fallback.

### 4.1. Beware of DEFAULT and Old-Version INSERTs

A column can be added with a default:

```sql
ALTER TABLE customer
ADD COLUMN active BOOLEAN DEFAULT TRUE;
```

Be sure to distinguish:

- Column omitted from INSERT list: the database can apply the default.
- INSERT explicitly sending `active = NULL`: standard defaults do not replace explicit NULL.
- An ORM may generate SQL either including the new column with null or omitting it depending on mapping and configuration.

Therefore, do not assume adding a default automatically handles every INSERT from old or new code. Inspect actual SQL from Spring Data R2DBC, entity mappings, and database behavior.

### 4.2. Do Not Add NOT NULL Immediately if Existing Rows Lack Values

The following migration can fail if the table already has rows and the new column lacks a valid default:

```sql
ALTER TABLE customer
ADD COLUMN display_name VARCHAR(200) NOT NULL;
```

A safer sequence:

1. Add a nullable column.
2. Deploy code capable of writing the new column and reading with fallback.
3. Backfill all existing rows.
4. Verify no NULLs remain and confirm all writers populate the new column.
5. Add `NOT NULL` in a separate migration.

Example checking data before tightening the constraint:

```sql
SELECT COUNT(*)
FROM customer
WHERE display_name IS NULL;
```

Proceed only once results and business rules are confirmed. On large tables, adding constraints may need a dedicated strategy to avoid prolonged locks.

## 5. Renaming a Column Using Two Temporary Columns

Direct renaming is usually a breaking change:

```sql
ALTER TABLE customer RENAME COLUMN name TO display_name;
```

After this statement, old versions still querying `name` will fail. Use expand-contract:

### Step 1: Add the New Column

```sql
ALTER TABLE customer
ADD COLUMN display_name VARCHAR(200);
```

v1 code continues reading/writing `name` as before.

### Step 2: Deploy Transition-Compatible Code

v2 code can write both columns for a period of time:

```java
Mono<Customer> renameCustomer(Long id, String newName) {
    return databaseClient.sql("""
            UPDATE customer
            SET name = :name,
                display_name = :displayName
            WHERE id = :id
            """)
        .bind("name", newName)
        .bind("displayName", newName)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .then(customerRepository.findById(id));
}
```

The example uses explicit SQL to illustrate dual-write. In production code, handle `rowsUpdated()` returning 0, column mappings, transactions, and other write paths to keep both columns consistent.

### Step 3: Backfill Legacy Data

```sql
UPDATE customer
SET display_name = name
WHERE display_name IS NULL;
```

For large tables, never run one massive UPDATE if it creates huge transactions, locks, or logs. Split by ID range or checkpointed batches; details are covered in the backfill section.

### Step 4: Switch Reads to the New Column

Once data is backfilled and dual-write is stable, v2 reads `display_name`. While v1 is still running, v2 may still need to keep writing `name` so v1 can read updated values.

### Step 5: Stop Old Code and Contract

Only after all v1 instances, workers, consumers, and jobs have stopped or upgraded, stop writing `name`. Observe for an appropriate window before dropping:

```sql
ALTER TABLE customer DROP COLUMN name;
```

Dropping a column is a breaking change and is usually hard to roll back if old data is not preserved elsewhere. Execute it in a separate release.

## 6. Dual-Read and Dual-Write Require Clear Rules

During transition, the application may have to read and write two representations.

### 6.1. Dual-Read

New code reads the new column first, falling back to the old column:

```java
String displayName = customer.getDisplayName() != null
    ? customer.getDisplayName()
    : customer.getName();
```

This supports legacy data not yet backfilled. However, fallback can hide an incomplete backfill. Measure how many rows still hit fallback and set an explicit stop condition.

### 6.2. Dual-Write

New code writes the same value to both new and old columns:

```sql
UPDATE customer
SET name = :value,
    display_name = :value
WHERE id = :id;
```

Both columns should be updated in the same statement or transaction to prevent partial states where only one column is written. When multiple writers exist, all writers must follow the strategy or another sync mechanism is required.

### 6.3. Avoid Two Simultaneous Sources of Truth

Dual-write is only a transitional bridge. Define which column is the source of truth at each stage and who is allowed to write.

If v1 only writes `name` and v2 only writes `display_name`, the two columns drift apart. If v2 writes both while an old worker keeps overwriting `name`, the new value in `display_name` may no longer match `name`. Maintain dual-write across every writer that can mutate the data, or retire old writers before switching the source of truth.

For complex changes, database triggers can temporarily synchronize columns, though triggers introduce hidden logic and dialect coupling. If used, document when they are enabled/disabled, test against all writers, and remove triggers upon contract.

## 7. Changing Data Types

Changing a column type directly can prevent old code from reading it or force the database to convert data under a long lock.

For example, changing `customer_code` from numeric to string to support prefixes:

```sql
ALTER TABLE customer
ALTER COLUMN customer_code TYPE VARCHAR(40);
```

This syntax is database-dependent and can trigger table rewrites/locks. For potentially incompatible changes, add a new column:

```sql
ALTER TABLE customer
ADD COLUMN customer_code_v2 VARCHAR(40);
```

Sequence:

1. Add the new column with the target type.
2. Deploy code capable of writing both old and new types.
3. Backfill using a defined conversion.
4. Check for unconvertible values, overflows, precision loss, or format changes.
5. Switch reads to the new column.
6. Stop old writers and stop writing the old column.
7. Contract by dropping the old column in a later release.

Do not use naive casting if conversion could lose data. Define how invalid values are handled and report row counts that fail conversion.

### 7.1. Changing Numeric Precision/Scale

Changing `DECIMAL(10,2)` to `DECIMAL(18,4)` can alter rounding rules and how Java `BigDecimal` is handled. Check:

- Whether existing data can be represented accurately in the new type.
- Whether old code assumes a fixed scale.
- Whether new code can read values written by old code.
- Whether calculations, comparisons, and reports use the same rounding mode.

### 7.2. Changing Time Types and Timezones

Switching between timestamps without time zones, timestamps with time zones, or epoch numbers can alter how instants are interpreted. Standardize UTC conventions, Java mappings (`Instant`, `OffsetDateTime`, `LocalDateTime`), and database semantics before migrating.

Never change a temporal column type without inspecting real data and session/driver time zones.

## 8. Adding New Enum Values or Statuses

Enum changes are often overlooked because no columns are altered. Yet old code may fail to parse the new value.

Suppose the database has statuses `PENDING`, `PAID`, `CANCELLED`; the new version adds `REFUNDING`.

If v2 writes `REFUNDING` while v1 still reads the same table using:

```java
OrderStatus.valueOf(row.get("status", String.class));
```

v1 can throw `IllegalArgumentException` on encountering the unknown value.

Safe sequence:

1. Deploy reader code capable of handling unknown values, such as an `UNKNOWN` state or controlled fallback.
2. Wait until all old readers are upgraded.
3. Start writing the new enum value.
4. Monitor readers and consumers that might receive the new value.

With native database enums, adding enum values has engine-specific syntax and limits. With `VARCHAR` columns, adding a value usually requires no DDL yet remains a data contract change between code versions.

Do not check only the web application. Message consumers, reporting jobs, and batch exports can also deserialize enums.

## 9. Adding Constraints in Stages

New constraints can prevent old code from writing data. For instance, adding `NOT NULL`, `CHECK`, foreign keys, or unique constraints while old writers do not yet satisfy those rules.

General sequence:

1. Roll out new code capable of writing constraint-compliant data.
2. Backfill or fix existing data.
3. Verify zero violating rows remain.
4. Add the constraint or validate a previously added constraint.
5. Monitor write errors after enabling the constraint.

### 9.1. PostgreSQL: NOT VALID and VALIDATE CONSTRAINT

PostgreSQL supports creating certain constraints like foreign keys or checks as `NOT VALID`, then validating existing data in a separate command:

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customer(id)
NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT fk_orders_customer;
```

A `NOT VALID` constraint is still enforced for new/updated rows per PostgreSQL semantics, while full validation of historical data is decoupled. This syntax is not portable; use the appropriate strategy for your target database.

### 9.2. Unique Constraints Require Resolving Duplicates First

Before creating a unique index/constraint, find duplicates:

```sql
SELECT email, COUNT(*)
FROM customer
GROUP BY email
HAVING COUNT(*) > 1;
```

If duplicates exist, resolve them per business rules first. For large tables, PostgreSQL supports creating unique indexes concurrently, though the build can fail if new duplicates arise during creation. Have a plan to check and clean up index state after migration.

## 10. Adding Indexes Without Disrupting Writes

A new index may be needed before deploying code that uses a new query. However, creating an index on a large table can consume heavy resources, block writes, or prolong migrations depending on the database.

PostgreSQL example:

```sql
CREATE INDEX CONCURRENTLY idx_orders_customer_created
ON orders(customer_id, created_at DESC);
```

`CONCURRENTLY` is PostgreSQL syntax and carries restrictions, such as not running inside a standard transaction block. Migration tools must be configured appropriately when using this statement. Other databases offer online index creation options or alternative mechanisms.

An index rollout workflow:

1. Identify the query plan and rationale for the index.
2. Assess table size, disk space, and I/O load.
3. Create the index using the least blocking mechanism supported by the database.
4. Verify the index is valid and used by the optimizer where expected.
5. Only afterward deploy code depending on the index's performance.

An index can be added ahead of new code if it does not alter legacy query semantics. Do not drop an old index right when new code deploys; monitor query workloads and confirm no queries still need it.

## 11. Backfilling Large Datasets in Batches

Backfilling populates data into a new column or transforms data into a new structure. On small tables, a single UPDATE may suffice. On large tables, one giant transaction can cause locks, massive transaction logs/WAL, increased replication lag, and impact online workloads.

Simple SQL example:

```sql
UPDATE customer
SET display_name = name
WHERE display_name IS NULL;
```

On large tables, chunk by ID range:

```sql
UPDATE customer
SET display_name = name
WHERE id > :fromId
  AND id <= :toId
  AND display_name IS NULL;
```

A worker executes many small batches, committing each batch separately by design. Persist checkpoints or track a cursor so work can resume if the process stops.

### 11.1. Idempotent Backfills

A backfill should be safely re-runnable without corrupting already-migrated data. The condition:

```sql
WHERE display_name IS NULL
```

fills only rows lacking a value. However, if the source column `name` can change during the backfill, establish rules deciding which value wins.

Options:

- Dual-write ensures every new change updates both columns in the same transaction.
- Backfill uses a version or timestamp so it never overwrites newer values.
- Temporarily prevent modifications to a subset of records during conversion if business rules allow.
- Run reconciliation after backfilling to spot drifted rows.

### 11.2. Using Bounded Reactive Batches

You can read a batch of IDs, update in batches, and move to the next batch. Illustrative example using `R2dbcEntityTemplate`:

```java
Flux<Long> backfillBatch(List<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    Query query = Query.query(Criteria.where("id").in(ids)
        .and("displayName").isNull());

    Update update = Update.empty()
        .set("displayName", "<row-specific computed value>");

    // Illustration: if target values differ per row,
    // read and update per entity or use appropriate SQL batching.
    return Flux.fromIterable(ids);
}
```

The snippet above illustrates only batch bounding; `Update.set` with one constant value does not apply when each row copies its own value from a source column. In practice, use SQL `UPDATE ... SET new_col = old_col` per ID range or a database-specific row-wise update statement. Never load an entire table into the heap just to backfill.

With R2DBC, worker pipelines can use `buffer(batchSize)` and `concatMap` to bound in-flight work:

```java
sourceOfIdRanges
    .concatMap(this::backfillRange)
    .then();
```

If concurrency is needed, set explicit limits and measure database load. Backfills should support rate limiting, timeouts, checkpoints, and pause/resume.

### 11.3. Monitoring Progress and Data Quality

Track:

- Expected total rows versus processed rows.
- Rows still NULL in the new column.
- Rows failing conversion.
- Rows with mismatched old/new values.
- Per-batch duration and retry counts.
- Lock waits, I/O, CPU, and replication lag.
- Error rates on online requests during backfill.

Do not treat a worker finishing without exceptions as proof that data migrated accurately. Run reconciliation queries and define clear completion criteria.

## 12. Migrations Must Be Coordinated Separately from Rolling Deployments

Do not let every application instance run the same migration haphazardly as they start up concurrently. Migration tools have schema history and locks to prevent duplicate runs, yet you must understand how they interact with multiple instances and transactions.

Common options:

- Run Flyway or Liquibase in a dedicated migration deployment/job prior to application rollout.
- Designate a single migration runner in the release pipeline.
- If migrations run at startup, confirm tool locking and multi-instance configuration, while ensuring DDL is safe for old versions.

Spring Data R2DBC does not mandate a specific migration tool. Flyway typically uses JDBC to manage migrations in many Spring Boot setups; if an app only uses R2DBC, you may need to add a JDBC driver/connection for migrations or choose a tool matching your database/migration strategy. Liquibase also offers JDBC-based or version-dependent execution paths. Keep schema migration distinct from R2DBC runtime data access.

### 12.1. Versioned and Immutable Migrations

Applied migrations should be treated as immutable. Modifying a migration already executed in a real environment can cause schema history across environments to diverge. Create a new migration for the next step rather than editing an already-applied file.

Example migration sequence:

```text
V101__add_display_name.sql
V102__backfill_display_name.sql       (if scale and execution approach suit)
V103__add_display_name_constraint.sql
V104__drop_legacy_name.sql            (after contract phase)
```

For large backfills, run a dedicated worker/job rather than stuffing a long-running operation into startup migrations. DDL and data migrations may require different retry, checkpoint, and observability mechanisms.

### 12.2. Never Let the New Application Depend on an Incomplete Migration

If a backfill migration is a long-running job, new code must recognize incomplete data and handle fallbacks. Do not roll out code that reads the new column as if every row were populated before confirming backfill completion.

## 13. How Schema Changes Affect Spring Data R2DBC Mapping

Spring Data Relational maps entity properties to columns using metadata and annotations. When the transitional schema contains both old and new columns, clarify which entity version runs at each stage.

Example v2 entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("name")
    private String legacyName;

    @Column("display_name")
    private String displayName;
}
```

This mapping lets v2 code access both columns during the transition. If the v1 entity only has `name`, adding a new column does not make it automatically aware of that column. This is generally fine if the new column is nullable and old INSERTs are not forced to supply a value.

### 13.1. SELECT * Can Break Mapping

In raw SQL and DTO mappers, avoid unnecessarily depending on column order or column count:

```sql
SELECT id, name, display_name
FROM customer
WHERE id = :id;
```

Explicit column lists and aliases keep mappers stable when the schema adds columns. With `SELECT *`, column counts change after migrations; mappers relying on positional indexes or fixed metadata assumptions can fail.

### 13.2. Custom Insert/Update SQL Must Be Updated Deliberately

An INSERT listing columns explicitly is usually more compatible when adding nullable columns:

```sql
INSERT INTO customer(name, email)
VALUES (:name, :email);
```

Old code keeps working because it omits the new column. If the new column has a default, the database can apply it. If the new column is set NOT NULL without a valid default, old INSERTs will fail.

With dual-writing new code:

```sql
INSERT INTO customer(name, display_name, email)
VALUES (:name, :displayName, :email);
```

Audit all raw SQL, stored procedures, views, and batch jobs touching the table before contracting the old column.

## 14. Safely Dropping Columns and Tables

Dropping a column or table is a destructive contract step. Before executing it, verify:

- No application instances read or write the column/table.
- No old workers, schedulers, consumers, or scripts remain.
- No views, stored procedures, triggers, reports, or ETL jobs depend on it.
- No dashboards or ad hoc queries require the legacy data.
- Backfill and reconciliation are complete.
- Backups/recovery capabilities exist per policy.
- A sufficient observation window has elapsed to catch long-interval scheduled consumers.
- Appropriate application and data rollback plans exist.

If uncertain, stop writing to the old column first, monitor queries/audits/metrics, and drop it in a subsequent release. Separating deprecation from deletion leaves room to spot missed dependencies.

### 14.1. Old Applications Cannot Roll Back After Contraction

Once the old column is dropped, rolling back the binary to an older version can cause immediate failures. Hence, contraction is typically the final step and runs only after:

- The rollback window to the old version has closed.
- A newer release exists that is compatible with the current schema.
- All legacy consumers are confirmed to no longer need the column.
- A data recovery plan exists if needed.

Application rollback and schema rollback are distinct. A migration that dropped a column cannot simply be rolled back via `ADD COLUMN`, because the old data is already gone.

## 15. Rolling Deployment and Release Sequence

A schema/app release typically follows this sequence:

| Step | Schema | Application | Goal |
|---|---|---|---|
| 0 | Only legacy structure | v1 | Initial state |
| 1 | Expand: add new columns/tables/indexes, keep legacy structure | v1 | v1 continues running normally |
| 2 | Transitional schema | v1 and v2 | v2 is compatible with v1 and legacy data |
| 3 | Transitional schema | v2, backfill running | New data is synchronized |
| 4 | Transitional schema | v2 and upgraded workers only | Switch reads/writes to new structure |
| 5 | Transitional schema, legacy structure unused | v2 | Observe, verify zero remaining dependencies |
| 6 | Contract: remove legacy structure/tighten constraints | v2 | Complete the change |

If a rollback is needed at step 2 or 3, v1 can still run because the legacy schema remains intact. If rolling back after step 6, v1 is incompatible; deploy a hotfix compatible with the new schema or restore schema/data according to plan.

## 16. Schema Changes and Inter-Service Messages/Events

Database schemas are not the only thing needing compatibility. If the application emits events or messages with altered structures, old consumers may still be running.

Similar principles apply:

- Add optional fields before requiring every producer to populate them.
- Old consumers must ignore unknown fields when the format supports it.
- New producers must not emit new enums/values before old consumers can handle them.
- Rename fields by adding the new field, emitting both during transition, and deprecating the old field later.
- Use a schema registry/versioning when the system manages formal message contracts.

An old worker may read a new message hours after deployment. Account for retention, retry queues, and dead-letter queues when scheduling contraction.

## 17. Testing Multi-Version Compatible Migrations

Testing migrations solely from an empty schema is insufficient. Verify the old schema, transitional schema, and post-contract schema across every stage.

Recommended tests:

### 17.1. Migrations from the Prior Schema Version

- Initialize the database with the current pre-change migrations.
- Seed representative data, including NULLs, edge cases, and large datasets.
- Run the expand migration.
- Confirm old code can still SELECT/INSERT/UPDATE.
- Confirm new code reads both backfilled and unbackfilled rows.

### 17.2. Testing v1/v2 Coexistence

- Run both code versions against the same transitional database.
- Let v1 write data and confirm v2 reads it properly.
- Let v2 write during dual-write and confirm v1 reads it properly.
- Run concurrent updates and verify both representations stay consistent.
- Verify new enum/status values are not written while old readers are unready.

### 17.3. Testing Backfill and Contract

- Backfill can re-run without corrupting data.
- A worker stopped mid-batch resumes from checkpoint.
- Reconcile row counts and old/new values.
- Contract runs only once dependency checks pass.
- v2 code works after the old column is dropped.
- Migration failure does not leave the schema in an unrecognizable state.

### 17.4. Load and Locking Tests

- Measure DDL execution time on production-sized data.
- Monitor lock waits and request blocking duration.
- Run backfill while online read/write traffic continues.
- Verify the R2DBC pool and replication do not overload.
- Test rollback or resume after timeouts/disconnects.

Do not rely solely on mocked repositories. Run integration tests against the real database and R2DBC driver, because DDL locking, defaults, unique/foreign key validation, and SQL dialects are engine-dependent.

## 18. Observability and Criteria Allowing Contraction

Never drop legacy structures solely because the deployment pipeline succeeded. Set measurable criteria:

- Running instance counts by version: zero v1 remaining.
- Running worker/consumer counts by version: zero old processes remaining.
- Timestamp when the old column was last written.
- Rows still missing values in the new column equal 0 or fall within approved exceptions.
- Rows with mismatched old/new values equal 0 or have been resolved.
- Zero SQL queries or metrics accessing the old column.
- Backfill completed and checkpoint verified.
- No spike in mapping/query error rates.
- At least one full cycle of relevant long-interval scheduled jobs/consumers has passed.

Example reconciliation query:

```sql
SELECT COUNT(*)
FROM customer
WHERE display_name IS NULL;
```

And checking for mismatched data:

```sql
SELECT COUNT(*)
FROM customer
WHERE display_name IS DISTINCT FROM name;
```

`IS DISTINCT FROM` is PostgreSQL syntax and may not be supported by all databases. Write the equivalent comparison for your target dialect, including explicit NULL handling.

## 19. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Rename/drop column in the first migration | Old running instances fail | Expand-contract across multiple releases |
| Add NOT NULL column when existing rows lack values | Migration or old-code INSERTs fail | Add nullable, backfill, verify, then tighten constraint |
| Assume DEFAULT replaces explicit NULL | New data may still store NULL | Inspect ORM-generated SQL and database semantics |
| Deploy new code before expand migration | New code queries nonexistent columns | Run expand migration prior to rollout |
| Upgrade web instances only, forget workers/consumers | Old processes keep querying old schema | Inventory all consumers and schedules |
| Switch reads to new column before backfill | Requests return missing data | Keep fallback and switch only when data is ready |
| Dual-write in only one writer | Old workers make columns diverge | List every writer; sync or stop old writers |
| Backfill in a single massive transaction | Locks, WAL/logs, and replication lag spike | Batch, checkpoint, and rate-limit |
| Non-idempotent backfill | Retries can overwrite newer data | Design conditional updates/versioning and reconciliation |
| Write new enum before old readers understand it | Old readers fail parsing | Upgrade readers first, writers second |
| Create blocking index on large table | Writes block or migrations stall | Use online/concurrent indexing per database |
| Let every pod run migrations | Lock contention or unpredictable startup migrations | Dedicated migration job or clearly coordinated tooling |
| Modify already-run migrations | Schema history drifts across environments | Create new migrations; keep applied ones immutable |
| Contract immediately after v2 deploy | No rollback window back to v1 | Separate contract release after rollback window closes |
| Test only empty schemas | Misses legacy data and coexistence bugs | Test upgrades from prior schema/data and both versions |

## 20. Workflow for Deploying a Compatible Schema Change

When altering tables/columns in a multi-instance environment, follow this sequence:

1. **Inventory consumers:** web instances, workers, schedulers, message consumers, scripts, reports, and external apps.
2. **Define old/new contracts:** SQL statements, entity mappings, enum values, nullability, and constraints.
3. **Design transitional state:** ensure expanded schema lets old and new code run together.
4. **Run expand migration:** add new structures additively; avoid direct drops/renames.
5. **Deploy compatible code:** fallback reads or dual-writes per an explicit strategy.
6. **Backfill data:** run in batches with checkpoints, idempotency, and rate limits.
7. **Reconcile:** verify NULLs, mismatches, row counts, and conversion errors.
8. **Switch traffic/read path:** move new code to the new data source once ready.
9. **Drain old consumers:** wait for old instances, workers, jobs, and messages to finish or upgrade.
10. **Stop writing old structures:** monitor access and confirm zero remaining dependencies.
11. **Contract in a separate release:** drop old columns/tables/indexes or tighten constraints.
12. **Verify and monitor post-deployment:** watch query failures, locks, pools, backfills, and data consistency.

## 21. Key Principles to Remember

- During rolling deployments, multiple code versions can access the same schema simultaneously.
- Migrations must remain compatible with every active writer/reader, including long-lived workers and consumers.
- Use expand-contract: add new structures, deploy compatible code, backfill, switch traffic, then drop old structures.
- Add nullable columns first; backfill and verify data before adding `NOT NULL`.
- Do not assume database defaults handle explicit NULLs or all ORM-generated SQL.
- Rename columns or change types by adding a new column and using time-bounded dual-read/dual-write when necessary.
- Define one source of truth per stage; dual-write must cover all writers.
- Upgrade readers before producers begin writing new enums or statuses.
- Add constraints and indexes using strategies suited to the database and table size.
- Backfill in bounded, idempotent batches with checkpoints, rate limits, and reconciliation.
- Coordinate migrations separately or use a migration tool with explicit locking/coordination.
- Keep applied migrations immutable; create new migrations for subsequent changes.
- Never contract before all old instances, workers, consumers, and jobs are drained.
- Contraction usually prevents rolling back to old binaries; keep an observation and rollback window.
- Test old schema, transitional schema, multi-version coexistence, backfills, and post-contract schema on the target database/driver.

Safe schema changes in multi-version environments go beyond writing syntactically valid DDL. It is a process of coordinating schemas, code, data, and the lifecycle of every consumer. Expand-contract keeps active versions working at every deployment step, while controlled backfills, measurable contract criteria, and clearly coordinated migrations prevent downtime and data loss while the system continues serving traffic.

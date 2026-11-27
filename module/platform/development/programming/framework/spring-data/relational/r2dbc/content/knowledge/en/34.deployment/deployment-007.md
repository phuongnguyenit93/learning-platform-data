# Coordinating Schema Changes with Continuous Delivery

In continuous delivery systems, multiple versions of an application can coexist for a period of time. During a rolling update, some instances still run old code while new instances are already serving requests. Background workers, message consumers, and batch tasks may also run independently of the HTTP service lifecycle. Therefore, database schema changes must remain compatible with all active application versions throughout the rollout.

With Spring Data R2DBC, entity mappings, queries, converters, and repositories all depend on the current schema. A migration that renames or drops a column the moment new code is released can break old instances; conversely, new code reading a column that has not been created yet will fail if deployed before the migration finishes. The common solution is evolving the schema in compatible stages, known as *expand-and-contract*: expand the schema first, deploy code that works with both old and new structures, migrate data and traffic, and only remove the old structure once no consumer uses it anymore.

The goal of this workflow is to keep the application running while the schema evolves, minimize downtime, preserve application rollback capability within the deployment window, and make migrations observable, testable, and controllable.

## 1. Why do schema changes need coordination with releases?

A release typically consists of at least two independent changes:

- Database changes: adding/dropping columns, tables, indexes, constraints, changing data types, or transforming data.
- Application changes: entity mappings, repository queries, DTOs, business logic, and how data is written or read.

If two incompatible changes are deployed in a single non-atomic window, rolling deployments create an interval where code and schema disagree.

For example, an old application runs the query:

```sql
SELECT id, full_name
FROM customers
WHERE id = :id
```

The new release wants to rename `full_name` to `display_name`. If the migration renames the column right before new instances launch, old instances still query `full_name` and start failing. If new code deploys first, new instances query `display_name` while the column does not yet exist and also fail.

Rolling updates also keep both versions active simultaneously:

```text
Time       ---------------------------------------------------->

Database:  [old schema] ---- [expand schema] -------------------

App v1:    [v1 v1 v1 v1 v1] [v1 v1] [drain] --------------------
App v2:                      [v2] [v2 v2 v2 v2 v2] ------------

During the rollout window, both v1 and v2 must be able to run against the schema.
```

You cannot assume all instances are replaced in the same millisecond. Nor can you assume rollback is just spinning up the old container; schema changes may have rendered the old code unable to run.

### 1.1. Consumer sources to account for

When planning a schema migration, inventory every component accessing the database:

- HTTP application instances.
- Reactive message consumers and scheduled jobs.
- Batch jobs or data pipelines.
- Admin tools, reporting services, and other applications sharing the database.
- Older application versions still alive during rollout.
- Operational scripts or external integrations running direct queries.

A column is only safe to drop when every consumer has stopped using it—not merely when the main HTTP deployment completes.

## 2. Compatibility principles in rolling deployments

A safe migration generally needs to keep the schema compatible with both pre-release and post-release code for a period of time.

| Change | Risk if deployed directly | Common safe approach |
|---|---|---|
| Add nullable column | Old code ignores the new column; new code may expect a value | Add the column first, deploy compatible code, then backfill and add constraints if needed |
| Add table | Minimal impact on old code if not yet accessed | Create the table before new code uses it |
| Add index | Can lock or spike load during creation | Use online/concurrent index creation if supported by the database |
| Add enum/constraint value | Old code may not understand the new value | Expand consumers before writing new values |
| Rename column | Either old or new code will fail to find the other name | Add new column, dual-write/backfill, switch reads, then drop old column in a later release |
| Drop column | Old code may still query or write the column | Stop using the column, roll out all consumers, then drop it |
| Change data type | Conversion may lose data or break queries | Create a new column, convert in batches, verify, then switch the application |
| Change semantics | Structure remains valid but data is interpreted differently | Version logic, perform controlled dual-read/dual-write, and transition step by step |

The core rule is that **breaking changes must be split across multiple releases**. If compatibility cannot be maintained, schedule an approved maintenance window with downtime and a clear procedure to stop traffic, drain connections, migrate, and restart.

## 3. The Expand-and-Contract pattern

Expand-and-contract breaks a breaking change into small steps, each remaining compatible with running versions.

```text
1. EXPAND
   Add the new structure while keeping the old structure.
       |
       v
2. COMPATIBLE RELEASE
   Deploy code capable of reading/writing both old and new schemas.
       |
       v
3. BACKFILL / VERIFY
   Copy legacy data into the new structure and verify results.
       |
       v
4. SWITCH OVER
   Switch primary reads/writes to the new structure.
       |
       v
5. CONTRACT
   Wait until all old consumers are drained, then drop the old structure.
```

Not every change requires dual-writes. Adding an independent column may only need expand and deploy. For renames, field splits/merges, or data type changes, intermediate steps prevent one version from writing data another version cannot read.

### 3.1. The Expand phase

Add the new schema element without removing or renaming the old structure. For example, renaming `full_name` to `display_name`:

```sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(160);
```

At this step:

- Old code continues using `full_name`.
- New code must not yet assume `display_name` is populated.
- Do not add `NOT NULL` immediately if existing rows lack values.
- Do not drop or rename the old column.
- If indexes/constraints are needed, evaluate online creation to minimize locks.

### 3.2. The Compatible Release phase

Deploy code that works with both old and new schemas. One approach is writing both columns during the transition:

```sql
UPDATE customers
SET full_name = :name,
    display_name = :name
WHERE id = :id;
```

With Spring Data R2DBC, you can temporarily map both properties or use a custom repository for dual-writes. New code must keep `full_name` synchronized so old instances can continue reading newly written data.

Never deploy code that writes only to `display_name` while old instances still read `full_name`, unless triggers or equivalent mechanisms are proven to keep the old column updated on every write path.

### 3.3. The Backfill phase

Migrate legacy data to the new column in batches:

```sql
UPDATE customers
SET display_name = full_name
WHERE display_name IS NULL;
```

On large tables, never run a single massive transaction if it causes locks, huge WAL/redo logs, or replication lag. Split into batches by primary key, limit concurrency, and monitor progress. Backfills must be idempotent: re-running must not corrupt already-migrated rows.

### 3.4. The Switch Over phase

After backfill completes and data is verified, switch reads to `display_name`. For a period, you can keep writing both columns to preserve a rollback window. Once all old instances have drained and new code is stable, release an update that stops writing `full_name`.

### 3.5. The Contract phase

Only when no code, job, report, or integration uses `full_name` anymore, drop the old column:

```sql
ALTER TABLE customers DROP COLUMN full_name;
```

This is the breaking step. It should belong to a separate migration/release after the rollback window for versions relying on the old column has closed.

## 4. Column rename example with Spring Data R2DBC

Suppose the old entity is:

```java
@Table("customers")
public record CustomerEntity(
        @Id Long id,
        @Column("full_name") String fullName
) {
}
```

The target is to move to:

```java
@Table("customers")
public record CustomerEntity(
        @Id Long id,
        @Column("display_name") String displayName
) {
}
```

Do not simply change the annotation and deploy alongside `ALTER TABLE ... RENAME COLUMN`. During a rolling deployment, old instances will keep accessing `full_name`.

### 4.1. Release A: expand the schema

The migration adds a new nullable column:

```sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(160);
```

The old entity continues working normally because it ignores the new column.

### 4.2. Release B: two-column compatible code

Temporarily map both properties:

```java
@Table("customers")
public record CustomerEntity(
        @Id Long id,
        @Column("full_name") String fullName,
        @Column("display_name") String displayName
) {
}
```

The service or custom repository ensures both columns receive the same value. When reading, prefer the new value if present while falling back to the old column during backfill:

```java
String effectiveName = displayName != null ? displayName : fullName;
```

If using `save(entity)` with an entity mapping both properties, ensure update paths do not overwrite the other column with null. For critical dual-write logic, an explicit custom SQL update is often easier to control than relying on an entity with multiple nullable fields.

### 4.3. Backfill the data

Run a batched migration/backfill for rows where `display_name IS NULL`. Verify no rows remain un-migrated and confirm both columns match within permitted data rules.

### 4.4. Release C: switch reads to the new column

New code reads only `display_name`, while still writing both columns during the rollback window. Once all instances and workers run the new release, monitor logs/queries to confirm no traffic still accesses the old column.

### 4.5. Release D: stop writing the old column

Deploy code writing only `display_name`. Keep the `full_name` column for a safety window if rollback is still possible; if rolled back to old code, that code would need `full_name` to hold recent data. You may keep dual-writes longer or decide that rollbacks past this point happen only via forward fix.

### 4.6. Release E: contract

Once the rollback window closes, drop `full_name` and remove the old property from the entity. Never combine dropping the column into the first release that switches reads, as that eliminates the ability to roll back to the previous version if needed.

## 5. Adding columns, constraints, and indexes safely

Not all DDL statements carry the same workload impact. Adding a nullable column can be fast, whereas building an index on a large table or adding a constraint that scans data can generate heavy load and locks.

### 5.1. Add nullable columns first

When adding a new attribute:

```sql
ALTER TABLE orders ADD COLUMN source_channel VARCHAR(30);
```

This is usually a far less disruptive expand step than adding `NOT NULL` immediately. Old code ignores the new column; new code handles null for un-backfilled rows.

Whether a database supports fast or metadata-only default column additions depends on the server version. Never generalize from one database to another DBMS. Read the DDL documentation and measure on representative data.

### 5.2. Add NOT NULL after backfill

The typical sequence is:

1. Add a nullable column.
2. Deploy code populating the value for new records.
3. Backfill existing records in batches.
4. Verify no nulls remain.
5. Add the `NOT NULL` constraint in a separate migration.

```sql
ALTER TABLE orders
ALTER COLUMN source_channel SET NOT NULL;
```

Syntax and locking behavior vary by database. In PostgreSQL, staged constraint/check validation can be used for certain constraints; other engines work differently. Check documentation and lock behavior before running on large tables.

### 5.3. Create indexes online/concurrently

Indexes speed up new queries, yet creating an index on a large table can block writes or spike I/O. PostgreSQL supports `CREATE INDEX CONCURRENTLY`:

```sql
CREATE INDEX CONCURRENTLY idx_orders_source_channel
ON orders(source_channel);
```

This command has specific constraints—for example, it cannot run inside a normal transaction block. The migration tool must be configured to run that migration non-transactionally when required by the database. `CREATE INDEX CONCURRENTLY` is PostgreSQL syntax, not portable SQL.

On other databases, look up the equivalent online index mechanism. If none exists, evaluate maintenance windows, locks, and production impact before deploying.

### 5.4. Add unique constraints in stages

When enforcing uniqueness on new data, never add the constraint before inspecting existing data. Find and resolve duplicates first, create a unique index using an appropriate online method, and then attach the constraint if supported by the database. During transition, application code must still handle race conditions and unique violations, because application-level existence checks do not replace database constraints.

## 6. Changing data types without disrupting the application

Changing a column type in place can lose data, lock tables, or prevent old code from reading new values. For major changes, use a new column:

1. Add a new column with the target type.
2. Deploy code that reads/writes both old and new columns.
3. Backfill using controlled conversion.
4. Compare old and new values and handle unconvertible entries.
5. Switch the read path to the new column.
6. Stop writing the old column after all consumers upgrade.
7. Drop the old column in a later release.

Example converting `phone_number` from integer to text to preserve leading zeros and formatting characters:

```sql
ALTER TABLE customers ADD COLUMN phone_number_text VARCHAR(40);
```

Backfills need clear rules. If the old column stored integers, leading zeros are already lost and cannot be recovered by casting alone. You need source data or business rules to reconstruct them. This is why semantics must be analyzed before writing migrations.

## 7. Backfilling large datasets in batches

Backfilling moves existing data into the new structure. On large tables, never hold one giant transaction or load all IDs into memory.

### 7.1. Use primary-key keyset pagination

Process IDs in chunks:

```sql
SELECT id
FROM customers
WHERE id > :lastId
  AND display_name IS NULL
ORDER BY id
LIMIT :batchSize;
```

After processing each batch, advance the `lastId` cursor to the last processed ID. Keyset pagination avoids large offsets and supports resuming from a checkpoint if the job stops.

### 7.2. Batched updates

For each batch, update by ID list or ID range:

```sql
UPDATE customers
SET display_name = full_name
WHERE id > :fromId
  AND id <= :toId
  AND display_name IS NULL;
```

The predicate `display_name IS NULL` makes the job idempotent: re-running a batch does not overwrite rows already migrated. When concurrent writers exist, define precedence rules and prevent the backfill from overwriting newer updates.

### 7.3. Executing reactively with bounded concurrency

Illustrative job loading a batch and updating:

```java
Flux<Long> loadIdsAfter(long lastId, int batchSize) {
    return databaseClient.sql("""
            SELECT id
            FROM customers
            WHERE id > :lastId
              AND display_name IS NULL
            ORDER BY id
            LIMIT :batchSize
            """)
            .bind("lastId", lastId)
            .bind("batchSize", batchSize)
            .map((row, metadata) -> row.get("id", Long.class))
            .all();
}
```

With a batch of IDs, you can execute an `IN` update or range update. If each batch runs in its own transaction, use `concatMap` for sequential execution or `flatMap` with an explicitly configured small concurrency cap:

```java
Flux.fromIterable(batches)
        .concatMap(this::migrateBatch);
```

Never use unbounded `flatMap` across millions of records. Backfills can starve application traffic of connections and spike production latency.

### 7.4. Checkpoints, retries, and idempotency

Save the checkpoint only after the batch transaction commits successfully. If the job stops, resume from the checkpoint or scan again using the idempotent predicate. Never update the checkpoint before the data transaction finishes, or the job may skip an uncommitted batch.

Retry only transient errors with bounded attempts. A batch update can be re-run if idempotent. For non-idempotent transformations, persist processing status or design operations that recognize already-completed batches.

### 7.5. Throttling load

Monitor query latency, active connections, lock waits, replication lag, CPU, and I/O. Limit batch size, concurrency, or pause the job when application traffic spikes. Backfills should support pause/resume and avoid long transactions.

## 8. A compatible migration is not automatically a lock-free migration

A migration can be compatible with old code yet still cause an outage through DDL locks or I/O load. Evaluate separately:

- Lock duration and lock mode.
- Whether the table receives continuous writes.
- Whether the DDL scans the whole table or rewrites rows.
- Whether the migration runs inside a transaction.
- Whether the migration can be safely cancelled.
- How much replication lag and WAL/redo log growth it triggers.
- Whether it must run on replicas or during a maintenance window.

Application compatibility and operational impact are separate criteria. An `ALTER TABLE` that breaks no old code can still wait on locks for a long time or block traffic if the database rewrites the table.

### 8.1. Lock timeout and statement timeout

Where supported by the database, configure migration timeouts to avoid waiting indefinitely on locks. For example, PostgreSQL provides `lock_timeout` and `statement_timeout`. Exact values depend on your release workflow and allowed window. If a migration cannot acquire a lock within limits, failing early and retrying in a controlled manner is usually better than holding a long DDL lock queue.

### 8.2. Transactional vs. non-transactional migrations

Not all DDL can run inside a transaction across all databases. Statements like PostgreSQL's `CREATE INDEX CONCURRENTLY` cannot run inside an ordinary transaction block; some databases perform implicit commits on DDL. Configure the migration tool properly for each migration.

Never assume a transaction rollback reverses every DDL statement. Confirm your database and migration tool's exact semantics before shipping migrations to production.

## 9. Coordinating migrations across multiple application instances

If every replica runs migrations at startup, multiple instances may attempt schema changes simultaneously. Migration tools typically use locking/version tables to prevent duplicate runs, yet you must still verify that mechanism, database permissions, and startup behavior on migration failure.

### 9.1. Using a dedicated migration job

A more controllable approach is running migrations as an independent deployment step:

```text
Build artifact
     |
     v
Run migration job (one controlled runner)
     |
     v
Verify schema version / health
     |
     v
Deploy application replicas
     |
     v
Observe rollout and traffic
```

A separate job confirms migration success before rolling out code that depends on the schema. It also separates DDL privileges from application runtime privileges. However, the migration job must target the right database, use the matching release artifact, and emit clear logs and exit statuses.

### 9.2. Migration locks

Flyway/Liquibase and similar tools maintain lock or metadata tables to prevent two runners from applying migrations concurrently. Verify how locking works, wait timeouts, and behavior if a process dies mid-migration. Do not invent a parallel custom lock mechanism when the tool already provides one, unless specifically required.

### 9.3. Single source of schema management

Never let each application instance run ad-hoc DDL while a separate migration job applies main migrations. Choose one schema management source and one clear application workflow. Application startup can verify the schema version or reachability without needing DDL privileges.

### 9.4. Separate database permissions

In production, grant DDL privileges to the migration runner and only necessary DML privileges to the application runtime user. This reduces the risk of the application accidentally altering the schema. Role configuration must account for temp tables, sequences, functions, or special privileges genuinely required by the workload.

## 10. Flyway/Liquibase and R2DBC applications

Spring Data R2DBC uses a reactive `ConnectionFactory` for runtime operations. Popular migration tools still use a JDBC `DataSource` to run DDL. Therefore, an R2DBC application may need both a JDBC driver and separate migration connection configuration.

Example separation of responsibilities:

- Migration job: connects to the database via JDBC, applies versioned migrations.
- Runtime service: connects to the same database via R2DBC, runs reactive queries.

Do not assume `spring.r2dbc.url` is automatically picked up by the migration tool. Verify URLs, credentials, schemas, and execution ordering for each tool.

### 10.1. Migrations run before application rollout

For expand migrations, the pipeline can run migrations first and then deploy compatible code. If the migration job fails, stop the rollout and keep the current application version running. Because expand migrations are backward-compatible, the old application keeps working against the expanded schema.

### 10.2. Contract migrations run after rollout

Migrations dropping old columns or constraints should run only after the version removing references to them is deployed and all old consumers have stopped. Never attach a contract migration to the startup of the same release that switches the read path if rollback still depends on the old schema.

## 11. Readiness, health checks, and schema compatibility

New applications should not accept traffic before required schemas are ready. Deployment pipelines can await migration job completion before rolling out. Additionally, readiness checks can confirm the database is reachable and essential tables/columns exist.

Avoid running full-schema verification queries on every health probe. Overly heavy or frequent checks add load. A schema compatibility check can run once at startup or during deployment validation.

### 11.1. Liveness and readiness are distinct

- **Liveness:** the process is alive and not severely hung.
- **Readiness:** the instance meets conditions to receive traffic, including required dependencies.

Temporary database unavailability can fail readiness without necessarily failing liveness and causing continuous orchestrator restarts. Choose policies based on self-healing behavior and application architecture.

### 11.2. Schema version checks

Migration tools typically record applied versions. Deployment pipelines can read that version and verify it falls within the range supported by the current code. One approach is declaring a supported schema compatibility range in release metadata or checking a required set of features/columns.

Do not compare only a single major version integer if migrations branch or cover independent features. What matters is verifying the actual schema satisfies the running binary's contract.

## 12. Application rollback vs. schema rollback

Application rollbacks and database rollbacks do not carry equal safety.

- **Application rollback:** redeploying the previous binary/container.
- **Schema rollback:** reversing migrations or restoring previous schema/data.
- **Forward fix:** releasing a new migration/code update to fix the current state.

With expand-and-contract, the expanded schema typically permits application rollbacks during the compatibility window. Once the contract phase drops old columns or applies irreversible data transformations, rolling back old code may no longer be viable.

### 12.1. Never automatically run down migrations on app rollback

A down migration can delete newly written data or break another version still running. Schema rollbacks must be evaluated separately with a backup/restore strategy and clear understanding of potential data loss.

### 12.2. Maintaining a rollback window

After deploying new code:

1. Monitor error rates, query failures, latency, and data integrity.
2. Keep old columns/structures for the defined rollback window.
3. Stop dual-writes only once simple code rollback is no longer required.
4. Drop old structures only when the rollback window closes and all consumers have upgraded.

### 12.3. Backups and recovery

For migrations carrying data-loss risk, take proper backups, test restores, and have a point-in-time recovery plan if supported by the database. Untested backups are no proof you can recover within required time limits.

## 13. Feature flags and traffic shifting

Feature flags decouple code deployment time from enabling new logic. For instance, code already supports `display_name` while continuing to read `full_name` until backfill finishes.

A rollout can proceed as:

1. Deploy schema-compatible code for both versions.
2. Run backfill.
3. Verify data.
4. Enable the flag to read the new column for a subset of traffic.
5. Observe outcomes and gradually expand.
6. Once stable, shift 100% of traffic.
7. Remove use of the old column in the following release.

Flags do not replace schema compatibility. If new code only works when the new column exists, migrations must still run before enabling the flag or before code executes queries referencing that column.

### 13.1. Flags must have a removal plan

Long-lived transition flags multiply logic branches and obscure which columns are still in use. Assign an owner, completion criteria, and a target release to remove the flag. Contract migrations run only after the flag is fully transitioned and old consumers are gone.

## 14. Testing migrations and compatibility in CI/CD

A strong pipeline verifies not only new code against the new schema, but also all compatibility combinations required during rollout.

### 14.1. Test migrations from an empty database

Initialize a fresh database, apply all migrations, and verify the resulting schema. This catches missing migration files or hidden manual state dependencies.

### 14.2. Test upgrades from the previous schema version

Create a database using the previous release's migrations, seed representative data, and then run the new migrations. Verify data is preserved/transformed accurately and new queries work.

### 14.3. Test old code against the expanded schema

If possible, run integration tests of the previous binary against the post-expand schema. This directly verifies the migration does not break the version still running during a rolling deployment.

### 14.4. Test new code against the expanded schema

Run integration tests of the new binary against the expanded schema before contract. Verify dual-writes, fallback reads, null handling, and query projections.

### 14.5. Test contract after retiring the old column

Run the latest version's test suite against the post-contract schema. Also verify no remaining queries, mappings, jobs, or reports reference the old column.

### 14.6. Test backfill and resume

Verify:

- Running backfill multiple times does not corrupt data.
- Jobs can resume after checkpoints.
- Concurrently updated rows are not wrongly overwritten by backfill.
- Failed batches do not advance the checkpoint past uncommitted data.
- Backfill rate does not overload the pool or database.

### 14.7. Test on the target database engine

Use Testcontainers or an integration environment matching the production database. H2 is no substitute for testing locks, DDL, data types, generated values, and transaction semantics of the real DBMS.

## 15. Example release pipeline

A release replacing `full_name` with `display_name` can be broken down as:

| Stage | Database | Application | Gate to proceed |
|---|---|---|---|
| Release A | Add nullable `display_name` | v1 continues using `full_name` | Migration succeeds, v1 remains healthy |
| Release B | Keep both columns | v2 reads old/new and dual-writes | All v2 instances/workers rolled out |
| Backfill | Copy old data to new | Batch backfill job runs | Zero nulls/mismatches per rules |
| Release C | Keep both columns | v3 reads new, still dual-writes | Metrics/queries confirm new read path is stable |
| Release D | Keep old column temporarily | v4 writes only new | No rollback needed to code requiring old column |
| Release E | Drop old column | v5 uses only new column | Zero consumers reference old column |

Release names are illustrative. Stages can be merged or split depending on risk level, but never skip the compatibility overlap when multiple versions run concurrently.

## 16. Monitoring after migrations and rollouts

During and after a release, observe both application and database:

- Query error rates and exception mappings.
- "Column/table does not exist" or conversion errors.
- p95/p99 query latency and HTTP latency.
- Connection pool active, idle, pending counts, and acquire timeouts.
- Lock waits, deadlocks, and long-running transactions.
- Replication lag, WAL/redo logs, and disk usage.
- Count of remaining null or un-backfilled rows.
- Drift between old and new columns during dual-write.
- Percentage of traffic using the new feature flag.
- Migration runner logs and current schema version.

Set alerts for conditions that make a rollout unsafe. Do not look solely at deployment tools reporting all pods Ready; queries can fail only when a rarely used endpoint is hit.

### 16.1. Monitoring legacy queries

Before contracting, gather evidence that no queries still use the old column. Use query logs, database statement statistics, tracing, application metrics, or searches across all repositories, jobs, and reports. Remember prepared statements or long-lived workers can outlive rollout timing; confirm they have drained or reconnected per policy.

### 16.2. Verifying data before contract

Do not just check the count of backfilled rows. Compare data against domain rules:

- Total record count.
- Null count in the new column.
- Mismatch count between old and new columns.
- Cases where conversion lost information.
- Uniqueness/foreign-key/check constraints to enforce.

For sensitive or high-volume data, run verification queries in batches or use suitable checksums, avoiding heavy full-table scans during peak hours.

## 17. R2DBC-specific considerations

R2DBC does not alter expand-and-contract principles, though reactive runtimes introduce specific considerations.

### 17.1. Entity mappings must match the existing schema

Spring Data R2DBC uses entity metadata to generate select/insert/update statements. Adding a property to an entity before the column exists causes generated queries to reference a missing column. Dropping a column before removing the property from the entity also breaks queries.

Thus, the safe order is typically:

1. Add the column in the database.
2. Deploy entity mappings with the new property.
3. Transition read/write paths.
4. Remove the property from code before dropping the column in the database.

When properties use `@ReadOnlyProperty`, `@Transient`, or custom projections, inspect the actual generated SQL; annotations do not automatically make missing columns safe.

### 17.2. Custom queries must be updated in stages

Repository `@Query`, `DatabaseClient`, and custom repositories can reference column names directly. Searching application source code is not enough if queries live in views, stored functions, reporting tools, or external jobs. Inventory all query consumers before contracting.

### 17.3. Reactive backfills must cap concurrency

Backfills over R2DBC can process batches with `Flux`, yet should never launch thousands of updates concurrently. Use `concatMap` or `flatMap` with bounded concurrency, scope transactions per batch, and monitor the pool. Each batch should commit quickly and remain safe to retry.

### 17.4. Reactive transactions and DDL migrations

Migration tools may use JDBC while runtime uses R2DBC. Never assume migration transactions and application transactions share a transaction or connection. Deployment orchestration must ensure migrations complete before schema-dependent code receives traffic.

### 17.5. Connection pools and schema changes

After DDL, open connections usually remain in use, while prepared statement caches, server-side plans, and metadata caches depend on driver/database behavior. If a schema change invalidates old queries or prepared statements, monitor errors and verify how the driver handles plan invalidation. Do not restart every instance merely to mask schema errors; understand the mechanism and plan rollouts accordingly.

## 18. Common pitfalls

### Renaming or dropping columns in the initial release

Old instances can still query the old column during rolling deployments. Split into expand, code transition, and contract.

### Deploying new code before expanding the schema

New entities/queries reference columns that do not yet exist. Run expand migrations before rolling out code depending on those columns.

### Adding NOT NULL before backfilling legacy data

The migration can fail or lock the table. Add nullable, backfill, verify, and only then add the constraint.

### Running a backfill in one giant transaction

Can hold locks for a long time, bloat logs, lag replication, and degrade production. Split into batches, checkpoint, and throttle load.

### Dual-writing without handling concurrent updates

Backfills can overwrite newer writes without proper predicates or sync rules. Design idempotently and define the authoritative source.

### Running migrations from every replica startup

Multiple instances can contend for locks or produce hard-to-observe states. Prefer an orchestrated migration job or verify the tool's lock semantics.

### Contracting immediately once new pods turn Ready

Workers, consumers, batch jobs, or old versions may still be running. Confirm all consumers have drained and the rollback window has closed.

### Using down migrations to roll back migrated data

Down migrations can lose data or be irreversible. Prefer forward fixes; only roll back schemas when impacts are understood and recovery plans exist.

### Ignoring DDL lock behavior

Even compatible migrations can lock tables or generate heavy load. Check database documentation, test on representative data, and set proper timeouts.

### Assuming all migrations run inside a transaction

DDL transaction semantics differ across databases and statements. Confirm your migration tool's transaction support for each migration.

### Not testing old code on expanded schemas

New code passing tests does not prove old instances still work. Add compatibility tests for the previous binary when rolling deployments require it.

## 19. Process for coordinating schemas and releases

1. Inventory every consumer of modified tables/columns, including HTTP instances, workers, and external systems.
2. Classify changes as additive or breaking; evaluate DDL locks, rewrites, and data-loss risk.
3. Design expand schemas so currently running versions keep functioning.
4. Create versioned, observable migrations with database-appropriate transaction/lock rules.
5. Run migrations in CI on both an empty database and the previous schema version.
6. Execute expand migrations via a coordinated migration runner.
7. Deploy code compatible with both old and new schemas.
8. Run batched, idempotent, checkpointed backfills with bounded concurrency.
9. Verify row counts, nulls, mismatches, and constraints before switching the read path.
10. Enable feature flags or gradually shift traffic for risky changes.
11. Monitor errors, latency, pools, locks, and data throughout the rollback window.
12. Drain all old instances, workers, and consumers.
13. Stop dual-writes and verify no queries still reference old structures.
14. Run the contract migration in a separate release.
15. Update entities, queries, migration history, and runbooks; keep a forward recovery plan.

## 20. Pre-release checklist

- [ ] All applications/jobs/workers using the modified schema have been identified.
- [ ] Schema compatibility with both old and new application versions has been evaluated.
- [ ] Expand migrations do not drop/rename old structures while consumers still use them.
- [ ] DDL has been evaluated for locks, rewrites, transactions, and replication impact.
- [ ] Migrations run via an orchestrated runner with clear logs/exit statuses.
- [ ] DDL and runtime privileges are appropriately separated.
- [ ] New code handles nulls/un-backfilled values during transition.
- [ ] Dual-write or compatibility logic has clear rules and tests.
- [ ] Backfills are idempotent, batched, checkpointed, and concurrency-bounded.
- [ ] Data verification exists before switching the read path.
- [ ] Feature flags have owners and removal plans if used.
- [ ] CI tests migrations from an empty database and from the prior schema.
- [ ] Tests cover old code on the expanded schema and new code on the matching schema.
- [ ] Readiness/rollouts admit traffic only once required schemas are ready.
- [ ] Rollback windows and contract prerequisites are defined.
- [ ] Backup/restore or forward-fix strategies match risk levels.
- [ ] Zero consumers still reference columns/tables scheduled for removal.
- [ ] Contract migrations live in a separate release after old consumers have drained.

Coordinating schemas with continuous releases is a problem of compatibility over time, not merely ordering a SQL file. By using expand-and-contract, keeping old and new schemas coexisting long enough, backfilling in batches, verifying data, shifting code, and only then contracting, Spring Data R2DBC applications can continue serving traffic seamlessly through rolling deployments. Migrations must be orchestrated separately, tested on real databases, and monitored for locks, latency, pools, and data integrity so releases can advance or recover along a clear plan.

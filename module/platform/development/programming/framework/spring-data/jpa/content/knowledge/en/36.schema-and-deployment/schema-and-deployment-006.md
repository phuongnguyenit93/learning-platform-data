# Changing Columns, Indexes, and Constraints While Remaining Deployment-Compatible

Changing a database schema in a running application requires coordinating migrations with the lifecycle of application versions. An ALTER TABLE statement may be valid SQL yet still break the system if older instances are still running, a background worker is processing messages, or an un-redeployed job still accesses the old column.

The key principle is **expand and contract**:

1. Expand the schema in a way that stays compatible with the current application.
2. Deploy a new application version capable of working with both old and new schemas during the transition period.
3. Transform and backfill data in batches.
4. Switch all read/write flows to the new structure.
5. Remove the old column, index, or constraint only after confirming no application version still depends on it.

This lesson explains how to alter columns, rename columns or change data types, add indexes and constraints, backfill data, execute rolling deployments safely, handle table locks, and test migrations with Flyway/Liquibase on a production-like database.

**Example prerequisites:** Java 17 or later, Spring Boot 3.x, Spring Data JPA, and Hibernate. The SQL DDL statements below are examples; syntax, online capabilities, locking, transactional DDL, and index creation methods depend on the database/version. Adapt them to the production engine. This is a guide for live applications, not a migration script to copy verbatim onto every database.

## 1. Why Must Schema Changes Be Compatible Across Multiple Versions?

During a rolling deployment, instances are not replaced at the exact same instant. For a period of time, the system may concurrently run:

- Old-version instances.
- New-version instances.
- Background workers not yet restarted.
- Active scheduled jobs or consumers.
- Independently deployed admin and batch tasks.

If the new version requires the display_name column but the database does not have it yet, new instances fail. If a migration drops name while old instances still read name, old instances fail.

The transition period can be illustrated as:

~~~text
Database schema S0
       |
       | Expand: add compatible column/index/constraint
       v
Database schema S1
       |
       | Rolling deploy: old app and new app run concurrently
       v
New app reads/writes new structure, data is backfilled
       |
       | Wait for all old apps and old jobs to finish
       v
Contract: drop unused old structures
       |
       v
Database schema S2
~~~

A safe migration must account for compatibility in both directions:

- **Old app with new schema:** does the old app keep working after the expand step?
- **New app with transitional schema:** can the new app handle un-backfilled rows or new columns that are still null?

Do not test only the schema after the final migration. Test each intermediate state the application will actually run against.

## 2. The Expand-and-Contract Workflow

A major change is typically split into the following phases:

| Phase | Database | Application | Goal |
|---|---|---|---|
| 1. Expand | Add new structure without removing old structure | Old version keeps running | Create a compatible schema |
| 2. Compatibility deploy | Keep both old and new structures | New version supports both | Zero-disruption rolling deploy |
| 3. Backfill | Migrate legacy data to new structure | May dual-write or read fallback | Bring data to a consistent state |
| 4. Switch | New schema contains required data | Primary reads/writes use new structure | Move use cases to new schema |
| 5. Verify | Check data, metrics, and dependencies | No code uses old structure | Confirm readiness for contract |
| 6. Contract | Drop old column/index/constraint | New version has no remaining dependency | Finalize the change |

Phases can span multiple releases. You do not have to execute expand, deploy, backfill, and contract in a single deployment.

**Do not contract immediately after deploying new code.** Confirm that all instances, consumers, cron jobs, reports, admin scripts, and external integrations have stopped using the old schema.

## 3. Adding a New Column Without Breaking the Old Application

Suppose the customers table currently has a name column. A new requirement wants to split it into first_name and last_name.

Do not drop name and add two NOT NULL columns in the same migration while the old app is still running. The old app may continue inserting/updating name, while the new app expects the two new columns.

### Step 1: Expand with nullable columns

Example SQL:

~~~sql
ALTER TABLE customers
    ADD COLUMN first_name VARCHAR(120) NULL;

ALTER TABLE customers
    ADD COLUMN last_name VARCHAR(120) NULL;
~~~

The two new columns allow the old app to continue writing name without supplying values for the new columns.

Adding columns may still require a metadata lock or short lock on some databases. For large tables, check the engine, version, and online column-add capabilities before running.

### Step 2: Deploy compatible code

The intermediate version can:

- When creating/updating a customer, write name and both new columns according to an agreed conversion rule.
- When reading, prefer the new data if present, otherwise fall back to the old data.
- Never assume every row is already backfilled when the release starts.

Conceptual service example:

~~~java
@Transactional
public void renameCustomer(
        Long id,
        String firstName,
        String lastName) {

    Customer customer = repository.findById(id).orElseThrow();

    customer.setFirstName(firstName);
    customer.setLastName(lastName);
    customer.setName(firstName + " " + lastName);
}
~~~

This snippet illustrates dual-writing. Name formatting rules must fit the domain; not all personal names can be reliably split or joined with a single space. If the two new columns cannot be unambiguously parsed from legacy data, establish a dedicated verification or business mapping process.

### Step 3: Backfill legacy data

Run a job to update rows that lack the new data. Backfilling must be idempotent: re-running must not corrupt already-migrated rows.

Illustrative SQL for data with a simple splitting rule:

~~~sql
UPDATE customers
SET first_name = ...,
    last_name = ...
WHERE first_name IS NULL
   OR last_name IS NULL;
~~~

The ellipsis represents a transformation expression depending on the data and database, not literal executable SQL. For large datasets, do not run a single full-table UPDATE in one long transaction by default. Chunk by ID or a stable pagination key, limit rows per batch, and monitor locks/logs/replication lag.

### Step 4: Switch to reading and writing the new columns

Once backfilling completes and data is verified:

- Switch read code to first_name/last_name.
- Stop dual-writing to name after all legacy consumers have stopped.
- Monitor read errors, null data, and accesses to the old column.

### Step 5: Contract

In a later release, once no dependencies remain:

~~~sql
ALTER TABLE customers DROP COLUMN name;
~~~

This is a breaking step. Run it only when old apps, old jobs, views, triggers, reports, and integrations no longer use that column. You may need one release just to stop writing the old column, and another release to drop it.

## 4. Renaming a Column Safely

A direct rename statement:

~~~sql
ALTER TABLE customers RENAME COLUMN name TO display_name;
~~~

can break old application instances because SQL generated by Hibernate still references name.

A safer process:

1. Add nullable display_name.
2. Deploy compatible code that writes both name and display_name.
3. Backfill display_name from name.
4. Check for nulls, discrepancies, and row counts.
5. Switch read code to display_name.
6. Stop writing name once no old app instances remain.
7. Drop name in a separate contract migration.

If dual-writing for a period, define a single authoritative data source. When two columns can be updated independently, the application needs an explicit conflict-resolution rule; merely writing both without a rule can introduce divergence.

For a pure rename on a small database with controlled deployment downtime, a direct rename may be acceptable. In rolling deployments or multi-consumer systems, add-copy-switch-drop is usually safer.

## 5. Changing Data Types with a Shadow Column

Changing a column type directly can lock the table, scan large amounts of data, fail on unconvertible values, or break old code.

For example, changing phone from free-form text to a standardized format or new type/structure. You can use an intermediate column:

1. Add phone_normalized with the new data type.
2. Deploy code that simultaneously writes both the old and new fields.
3. Backfill old values through a validated conversion function.
4. Record unconvertible rows for separate handling.
5. Read from the new column after verification.
6. Stop writing to the old column.
7. Drop the old column and rename the new one in a later release if needed.

Never force conversion with CAST if legacy data contains invalid values. Before migrating, profile:

- Count of null rows.
- Unparseable values.
- Values exceeding the new length/precision.
- Duplicate values after normalization.
- Values requiring rounding or timezone rules.

For decimals, changing precision/scale can lose data. For timestamps, clarify timezone and instant vs. local time semantics. For enums, ensure old values map cleanly in the new code.

## 6. Enforcing NOT NULL in Multiple Steps

Adding a new column immediately as NOT NULL can fail when the table already has rows or the old app does not send a value.

A safe process is usually:

1. Add a nullable column.
2. Deploy code that always writes a value for new records.
3. Backfill legacy rows.
4. Verify no NULLs remain.
5. Add the NOT NULL constraint.
6. Update entity mapping to nullable = false if appropriate.

Verify before enforcing:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE external_code IS NULL;
~~~

Only when the count is 0 and every writer supplies the new value should you add the constraint:

~~~sql
ALTER TABLE customers
    ALTER COLUMN external_code SET NOT NULL;
~~~

This syntax fits PostgreSQL and several other engines; MySQL, SQL Server, and Oracle have their own syntax. Altering nullability may require a table lock or full scan depending on engine/version.

Setting a database default can allow older writers to keep inserting, but understand the difference among:

- **Database DEFAULT:** applied when an INSERT omits the column or uses DEFAULT.
- **JPA field initializer:** applied only when Java instantiates the object.
- **@ColumnDefault:** Hibernate metadata for DDL/schema generation; does not ensure every INSERT from every client receives the default.
- **@PrePersist:** application callback; does not run for SQL written directly from other sources.

Do not use an artificial default if the value must reflect real business data. A default should only be chosen when it is semantically valid for every new record.

## 7. Adding a FOREIGN KEY Without Disruption

Suppose you need to add orders.customer_id referencing customers.id.

Common process:

1. Add nullable customer_id.
2. Deploy new code writing customer_id for new orders.
3. Backfill the relationship for existing orders.
4. Check that no null customer_ids remain if business rules require it.
5. Check that no orphan references exist.
6. Create an index on the foreign key column if the workload needs it.
7. Add the FOREIGN KEY.
8. Add NOT NULL once all rows are valid and all writers are compatible.

Check for orphans:

~~~sql
SELECT o.id, o.customer_id
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

The result must be empty before adding the FK.

An index on the foreign key column is often helpful for JOINs and parent-table deletes/updates, but databases do not always create an index automatically when adding an FK. Check engine behavior and workload before creating it.

PostgreSQL can add certain constraints using NOT VALID, then validate existing rows separately:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id) REFERENCES customers(id)
NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT fk_orders_customer;
~~~

This is PostgreSQL-specific syntax. The new constraint is still enforced for new writes once added, while validating legacy data occurs as a separate step. Other databases have different mechanisms and lock levels; do not copy this syntax to other engines.

## 8. Adding CHECK Constraints in Phases

For example, enforcing quantity greater than 0:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT ck_order_items_quantity_positive
CHECK (quantity > 0);
~~~

Before adding the constraint, inspect legacy data:

~~~sql
SELECT COUNT(*)
FROM order_items
WHERE quantity <= 0;
~~~

If violating rows exist, decide how to fix, remove, or handle them according to business rules before enforcing.

In PostgreSQL, you can use NOT VALID followed by VALIDATE CONSTRAINT to separate adding the constraint from scanning legacy rows. This capability is not portable. On other engines, consult documentation on online constraint validation and DDL lock levels.

Once the constraint is enforced, new code should validate inputs early so users receive clear errors. The database remains the final safeguard, even when data is written outside the application.

## 9. Adding UNIQUE Constraints and Handling Duplicates

Suppose email must be unique within each tenant:

~~~sql
ALTER TABLE users
ADD CONSTRAINT uk_users_tenant_email
UNIQUE (tenant_id, email);
~~~

Before creating a unique constraint, find duplicate combinations:

~~~sql
SELECT tenant_id, email, COUNT(*)
FROM users
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
~~~

Duplicates must be resolved before enforcing. Never automatically delete duplicate records without business rules covering data merging, foreign keys, and history.

For large tables, building a unique index can take time and locks. PostgreSQL supports:

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY
    ux_users_tenant_email
ON users(tenant_id, email);
~~~

Then you can attach the index to the constraint:

~~~sql
ALTER TABLE users
ADD CONSTRAINT uk_users_tenant_email
UNIQUE USING INDEX ux_users_tenant_email;
~~~

This is a PostgreSQL-specific workflow. CREATE INDEX CONCURRENTLY has transaction restrictions and can leave an invalid index if it fails; monitor status and have a controlled cleanup/retry procedure. Do not place this statement in a standard migration transaction if the migration tool wraps the entire script in a transaction.

On other databases, syntax and online unique index creation capabilities vary. Check the exact engine version and choose an appropriate deployment window.

## 10. Creating Indexes Without Blocking Writes Too Long

Indexes speed up queries, but building an index on a large table consumes CPU, I/O, disk space, and can cause locks. Index creation must account for write throughput while building.

Before adding an index:

- Identify which queries are slow.
- Inspect WHERE, JOIN, ORDER BY, and selectivity.
- Check existing indexes.
- Read execution plans.
- Estimate size and build duration.
- Check replication lag and write load.
- Choose online/concurrent methods if supported by the database.

Example index for queries filtering by status and sorting by created_at:

~~~sql
CREATE INDEX idx_orders_status_created_at
ON orders(status, created_at);
~~~

This index is only an example. Appropriate column order depends on query patterns, cardinality, equality/range filters, and the database optimizer. A new index may go unused if selectivity is low or queries do not match the composite index prefix.

Database-specific options:

- **PostgreSQL:** CREATE INDEX CONCURRENTLY reduces interference with INSERT/UPDATE/DELETE, though it takes longer and cannot run inside a normal transaction block.
- **MySQL/InnoDB:** some ALTER TABLE/CREATE INDEX operations support ALGORITHM=INPLACE or INSTANT and LOCK=NONE depending on operation/version. Not every change is online.
- **SQL Server:** supports ONLINE = ON for certain editions/operations/index types; check specific limitations.
- **Oracle:** offers online options for certain index/DDL operations; resource usage and locks must still be evaluated.

Do not assume online means zero locks or zero impact. Online operations still consume resources and may take brief locks at the beginning/end.

## 11. Backfilling Large Datasets in Batches

Backfilling is migrating existing data into the new structure. A single full-table UPDATE can:

- Hold locks for a long time.
- Generate massive transaction logs/WAL.
- Increase replication lag.
- Bloat undo/redo logs.
- Contend for resources with user workloads.
- Be difficult to roll back if the job fails mid-way.

For large tables, chunk by a stable key:

~~~sql
UPDATE customers
SET normalized_email = LOWER(TRIM(email))
WHERE id > :last_id
  AND id <= :next_id
  AND normalized_email IS NULL;
~~~

The statement above is a SQL pattern with placeholders supplied by a coordinator job; bind syntax and range selection depend on the application/database.

A backfill job should:

1. Determine the next range or keyset.
2. Update a small batch.
3. Commit the batch.
4. Persist a checkpoint so it can resume.
5. Monitor throughput, errors, and replication lag.
6. Throttle or shrink batch size when system load is high.
7. Re-run safely if the worker stops mid-way.

Using conditions like normalized_email IS NULL makes the job idempotent for already-processed rows. However, if the new app concurrently updates this value, establish clear synchronization rules so the backfill does not overwrite newer values.

Avoid large OFFSET values for backfills on actively changing tables. Keyset pagination by ID or an ascending key is usually more stable. With multiple workers, design range partitioning or batch claiming so workers do not collide unnecessarily.

## 12. Dual-Write and Data Synchronization During Transitions

When both old and new columns exist, writing to both may be required during transition. Dual-write can happen inside the same database transaction if both columns reside in the same database.

Guidelines:

- Designate a single authoritative data source in each phase.
- Write both columns using the exact same transformation rule.
- Avoid having two different services update the two columns independently.
- Track the count of rows with mismatched values.
- Have the backfill only touch unmigrated rows or explicitly identified discrepancies.
- Stop dual-writing once legacy consumers are gone.

If dual-write spans two separate databases or systems, automatic atomicity does not exist. In that case, use a transactional outbox, event-driven synchronization, retries, and discrepancy detection/reconciliation.

Do not introduce a database trigger to synchronize two columns without documenting it in the design. Triggers can be useful, but they mutate data outside application code paths, surprising auditing, debugging, and ORM state. If used, document, test, and manage them through migrations.

## 13. Executing Rolling Deployments Safely

A release sequence that can be applied:

**Release A — Expand**

- Run migration adding new nullable columns, indexes, or transitional constraints.
- Verify migration completion.
- Old app continues running against the new schema.

**Release B — Compatibility code**

- Deploy new app supporting both old and new schemas.
- Dual-write both columns if needed.
- Read new data when available, falling back to legacy data.
- Keep code tolerant of un-backfilled rows.

**Backfill phase**

- Run batch job.
- Monitor remaining unmigrated rows and conversion errors.
- Compare old/new values against defined rules.
- Support pause/resume without corrupting results.

**Release C — Switch**

- Switch all reads to the new column.
- Drop reliance on the old column.
- Wait for all old instances/workers/consumers to finish.
- Confirm no queries, reports, or scripts still use the old column.

**Release D — Contract**

- Drop the old column or unused constraints/indexes.
- Remove legacy mappings and compatibility code.
- Monitor errors after the migration.

If a release must support rollback to the previous version, the schema must stay compatible with that rollback version. Once contract drops the old column, rolling the app back to the old version may no longer be safe; at that stage you need a forward-fix or a pre-prepared data recovery procedure.

## 14. Spring Data JPA Mappings During Transitions

An entity can temporarily map both columns:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "name")
    private String legacyName;

    @Column(name = "display_name")
    private String displayName;

    public String getEffectiveDisplayName() {
        if (displayName != null) {
            return displayName;
        }
        return legacyName;
    }

    public void rename(String newDisplayName) {
        this.displayName = newDisplayName;
        this.legacyName = newDisplayName;
    }
}
~~~

This example applies when both columns share the same semantics. When moving from one name column to first_name/last_name, use a domain-specific mapper rather than copying raw strings verbatim.

During the compatibility phase, you can use:

- An entity mapping both old and new columns.
- A single service method responsible for dual-writing.
- DTOs exposing only the new field.
- Metrics counting un-backfilled rows or fallbacks to the old column.

After contract, remove the legacy field from the entity in the same release or after the drop-column migration has completed. Never deploy code referencing a new column before the expand migration has succeeded.

## 15. Managing Migrations with Flyway or Liquibase

Do not let Hibernate modify production schemas via ddl-auto=update. Schema changes must be reviewed, versioned, tested, and deployed in a clear sequence.

With Flyway, versioned migrations are typically named like:

~~~text
V001__create_customers.sql
V002__add_display_name.sql
V003__backfill_display_name.sql
V004__add_customer_email_index.sql
~~~

Flyway maintains migration history to track which scripts ran. Versioned migrations already executed on shared environments should be treated as immutable; if logic needs fixing, create a new migration rather than editing an already-applied script.

Liquibase uses changelogs and changesets to manage changes. Whichever tool is chosen:

- Have only one primary schema management source.
- Review SQL/DDL before deployment.
- Record target database/version.
- Test migrations from both legacy schemas and completely empty databases.
- Manage rollbacks or forward-fixes for each change.
- Do not let multiple application instances compete to run the same migration without understanding the tool's locking mechanism.

In production, you can run migrations as a controlled deployment step prior to rolling out the app. This allows observing duration, locks, and migration errors independently from instance startup.

## 16. DDL Transactions and Table Locks Depend on the Database

Not all databases handle DDL inside transactions identically.

- **PostgreSQL:** supports transactions for many DDL commands, though certain commands such as CREATE INDEX CONCURRENTLY cannot run inside a normal transaction block.
- **MySQL:** many DDL statements cause implicit commits; instant/in-place/online support depends on operation, storage engine, and version.
- **Oracle and SQL Server:** have their own DDL transaction/locking rules; do not infer behavior from PostgreSQL or MySQL.

A migration may succeed quickly on a small dev database yet block production due to large tables, lock queues, or long-running transactions.

Before running DDL:

1. Read documentation for the exact database/version.
2. Identify lock modes and expected duration.
3. Check for long-running transactions holding locks.
4. Set appropriate lock timeouts or statement timeouts if supported by the engine.
5. Dry-run on production-scale data.
6. Prepare monitoring and abort criteria.
7. Have a retry/cleanup plan if online DDL partially fails.

Never treat fast local migration execution as proof of production safety.

## 17. Keep Migrations Small, Observable, and Recoverable

A good migration has a clear scope and predictable runtime. Avoid bundling all of these into a single release:

- Adding multiple columns.
- Migrating millions of rows.
- Creating several large indexes.
- Enforcing multiple constraints.
- Dropping old columns.

Separating DDL from backfills makes it possible to monitor each step, tune batch size, and pause if workload is impacted.

Metrics to monitor:

- Migration duration.
- Rows backfilled and remaining.
- Rows failing conversion.
- Fallbacks to the old column during reads.
- Write errors or constraint violations.
- Lock waits and deadlocks.
- CPU, I/O, and connection pool usage.
- WAL/redo/transaction log growth and replication lag.
- Query latency of primary workloads.

If a migration is interrupted, you must know which steps completed, whether the job is re-runnable, and how to inspect state. Never assume rollback SQL restores all transformed data or reverses every DDL across all databases.

## 18. Testing Migrations and Application Compatibility

A migration test suite must test multiple schema states, not just running all migrations on an empty database.

### Testing from the previous schema version

- Initialize the database at the old schema.
- Load representative data, including nulls, edge values, duplicates, and orphan rows if applicable.
- Run migrations.
- Verify new data, constraints, and indexes.
- Confirm data was not lost or mis-transformed.

### Testing code compatibility

- Run the old app version against the post-expand schema.
- Run the new app version against un-backfilled data.
- Run the new app after backfilling.
- Verify dual-write creates no divergence.
- Confirm the new app no longer depends on the old column before contract.

### Using Testcontainers

~~~java
@Testcontainers
@SpringBootTest
class CustomerMigrationIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    // Configure DataSource from container and run migrations
    // before executing schema/data assertions.
}
~~~

This is an illustrative skeleton; the application needs dynamic datasource configuration, appropriate Testcontainers dependencies, and the migration tool. Use a production-like engine/version to test DDL, constraints, indexes, and SQL behavior. H2 is not a complete substitute for PostgreSQL/MySQL/Oracle/SQL Server when migrations use database-specific features.

## 19. Rollback, Forward-Fix, and Transformed Data

Application rollback and database rollback are two separate concerns.

- App rollback can be done by redeploying the old artifact if the schema remains compatible.
- DDL rollback may be impossible if data has already been dropped or transformed.
- Backfills may not be reversible if the transformation loses information.
- Unique constraints or NOT NULL cannot always be safely dropped if new code already relies on them.

For destructive changes, prefer forward-fix: repair the migration/code via a new controlled step instead of trying to reverse DDL that risks data loss.

Before contracting or performing irreversible transformations:

- Verify backups and restore capability have been tested.
- Capture row counts and appropriate reconciliation checksums.
- Know how to restore the old column if necessary.
- Maintain a sufficiently long observation window.
- Confirm all consumers have finished switching over.

Backups are only useful when restore procedures have been rehearsed and recovery time meets operational requirements.

## 20. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Old app fails after migration | Column renamed/dropped while old instances still run | Use expand-and-contract |
| New app fails on legacy rows | Assumed new column was already backfilled | Allow null/fallback during transition |
| Adding NOT NULL fails | Existing table has nulls or old app omits field | Add nullable, backfill, then enforce |
| Adding UNIQUE fails | Existing data contains duplicates | Inspect and resolve duplicates beforehand |
| Adding FK fails | Orphan references exist | Backfill and verify parent-child data |
| Index build slows writes | Build holds locks or competes for I/O | Use appropriate online/concurrent options and monitor load |
| Backfill locks table too long | Single transaction updates entire dataset | Chunk batches, commit, and checkpoint |
| Dual-write causes data drift | Two fields lack an authoritative source | Define rules, reconcile, and track metrics |
| App rollback fails | Contract dropped column needed by old app | Contract only after all dependencies cease |
| Works locally, times out in prod | Small data, different locks/DDL behavior | Test with large datasets and exact database/version |
| Hibernate alters schema | Using ddl-auto=update in production | Manage via Flyway/Liquibase |
| Applied migration version edited | Migration history no longer reproducible | Create a new versioned migration |
| Tests only run on H2 | Differences in DDL, constraints, indexes, and SQL | Use Testcontainers with production engine |
| CREATE INDEX CONCURRENTLY fails | Statement disallowed in transaction or invalid index left behind | Configure migration properly and check index status |

## 21. Pre-Deployment Schema Change Checklist

- [ ] Inventory all app instances, workers, schedulers, reports, and integrations using the schema.
- [ ] Verify the old app remains compatible with the post-expand schema.
- [ ] Add new columns as nullable or with a business-valid default when appropriate.
- [ ] Deploy compatible code before migrating data.
- [ ] Design dual-write/read fallback with an authoritative data source.
- [ ] Backfill in batches with checkpoints, idempotency, and pause/resume support.
- [ ] Check for nulls, duplicates, orphans, and unconvertible values.
- [ ] Create indexes/constraints using online methods suitable for engine/version.
- [ ] Evaluate locks, transactional DDL, replication lag, and resources.
- [ ] Switch all read/write code to the new schema.
- [ ] Confirm no consumers still use old columns/indexes/constraints.
- [ ] Contract in a separate migration after an observation window.
- [ ] Test app rollback and database forward-fix.
- [ ] Test migrations from the old schema on the real database engine.
- [ ] Use Flyway/Liquibase as the primary schema management source.
- [ ] Keep appropriate Hibernate schema validation in production, such as ddl-auto=validate.

## 22. Conclusion

Safe schema changes require compatibility across multiple application versions coexisting during rolling deployments. **Expand-and-contract** separates adding new structures, deploying compatible code, backfilling data, switching read/write flows, and finally removing old structures.

Columns, data types, indexes, and constraints must all be evaluated for data size, locks, online capabilities, and database/version specifics. Use versioned migrations, re-runnable batched backfills, data validation prior to enforcing constraints, and contract only once all consumers have moved over. That way, schema changes can be rolled out incrementally, observed clearly, and recovered according to plan.
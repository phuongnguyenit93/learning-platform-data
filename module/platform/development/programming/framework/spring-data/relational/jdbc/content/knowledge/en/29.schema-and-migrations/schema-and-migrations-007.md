# Controlling Legacy Schemas, Default Values, and Data Backfills

## 1. Changing Schemas When a System Already Has Data

A Spring Data JDBC application typically starts with a relatively small schema: aggregate root tables, child tables, primary keys, and a few indexes. As the product evolves, the model and database must evolve too:

- Adding a new column for an attribute.
- Renaming or changing a column's type.
- Splitting one field into multiple fields.
- Adding new tables or relationships.
- Adding constraints, indexes, or default values.
- Migrating historical data into a new structure.

Changing a Java class is far simpler than changing a schema holding millions of rows while multiple application versions are actively using it. During deployment, old application instances, new instances, un-updated batch jobs, and historical rows lacking values for new columns can all coexist.

Consequently, schema migrations must control both structure and data. This guide focuses on three intertwined concerns: maintaining compatibility with legacy schemas, placing default values in the right layer, and safely backfilling historical data.

## 2. Schema Migrations and Application Responsibility

The schema is a contract between the application and the database. In Spring Data JDBC, entity/aggregate mappings depend on declared table names, column names, data types, keys, and relationships. When the schema changes without matching mapping updates, errors surface on reads or writes:

- `SELECT` queries referencing columns that no longer exist.
- `INSERT`/`UPDATE` writing to columns with incompatible types.
- New `NOT NULL` columns lacking values on insert.
- New entities reading nullable columns when code assumes a value is always present.
- Foreign keys or unique constraints rejecting incoming writes.

Do not let individual application instances create or alter schemas in production. Manage schemas with versioned migrations executed through an explicit deployment workflow.

Commonly used tools:

- **Flyway:** manages versioned or repeatable migrations; tracks history in a schema history table.
- **Liquibase:** describes schema changes via changesets and tracks applied changesets.
- **Custom SQL migrations:** can work for small systems, but still require versioning, history, ordering, and a consistent execution process.

Choose one tool as the primary schema manager. Avoid letting Flyway, Liquibase, manual scripts, and auto-generation settings modify the same database without coordination rules.

## 3. Migrations Must Be Versioned and Traceable

With Flyway, SQL migrations typically follow a versioned naming convention, for example:

~~~text
src/main/resources/db/migration/
  V001__create_customer.sql
  V002__add_customer_status.sql
  V003__add_customer_audit_columns.sql
~~~

Example migration:

~~~sql
ALTER TABLE customers
ADD COLUMN status VARCHAR(20);
~~~

With Liquibase, changes are described in changesets and recorded in Liquibase-managed history tables.

Key principles:

1. Every versioned migration already executed in a shared environment must be treated as immutable.
2. To change the schema later, create a new migration instead of modifying an already-applied one.
3. Name migrations descriptively and keep ordering clear.
4. Test migrations on a database of the same engine and version close to production.
5. Know clearly which migrations run before the new application starts.
6. Document whether a migration can be rolled back or must move forward via compensating migrations.

Many DDL operations do not share identical transaction semantics across databases. Some engines support transactional DDL for certain commands; others may implicitly commit, lock tables, or require special procedures. Never assume a multi-DDL migration always rolls back completely if the last statement fails.

## 4. Backward Compatibility When Deploying Multiple Application Versions

In rolling deployments, old and new versions run side by side for some duration. A safe migration must account for both versions.

For instance, the application currently stores full names in `full_name`. The new version wants to split this into `given_name` and `family_name`.

If you rename immediately and drop `full_name`, still-running old instances fail on queries or writes. If you deploy new code before adding the columns, new instances fail because the columns do not exist yet.

The standard solution is **expand-migrate-contract**:

~~~text
Phase 1: EXPAND
  Add new columns or tables in a backward-compatible way.
  Keep old columns intact.

Phase 2: MIGRATE
  Deploy code understanding both old and new schemas.
  Backfill historical data.
  Gradually shift reads/writes to the new structure.

Phase 3: CONTRACT
  Confirm no instances/jobs still use the old structure.
  Stop writing old columns.
  Drop old columns or constraints in a separate migration.
~~~

### 4.1. Expand

Add the two new columns as nullable:

~~~sql
ALTER TABLE customers
ADD COLUMN given_name VARCHAR(100);

ALTER TABLE customers
ADD COLUMN family_name VARCHAR(100);
~~~

The old application can continue using `full_name`. The new schema has extra columns without requiring old code to know about them.

Before adding columns, check:

- Column names do not clash with mappings or database reserved keywords.
- Types and lengths fit real data.
- Whether DDL locks or rewrites the table.
- Whether new indexes can be created online/concurrently.
- Whether the database has sufficient storage and log/replication capacity for the change.

### 4.2. Deploy Compatible Code

The intermediate version can read the new structure if already backfilled, while handling unbackfilled rows during the transition:

~~~java
public String displayName(Customer customer) {
    if (customer.givenName() != null
            && customer.familyName() != null) {
        return customer.givenName() + " " + customer.familyName();
    }

    return customer.fullName();
}
~~~

This is only an example of fallback logic. If old instances still write `full_name`, the new version needs a strategy to keep new data synchronized:

- Temporarily write both old and new columns.
- Use a database trigger during the transition window.
- Or control writer cutover so no old version continues writing.

Designate a single authoritative data source per phase. Dual-writes can introduce inconsistencies if one write updates one column and fails on the other; when dual-writing in a single database transaction, ensure both columns commit or roll back together.

### 4.3. Contract

Drop `full_name` only after:

- No old application instances remain.
- Batch jobs, scheduled tasks, consumers, and operational tools have been updated.
- No queries, views, reports, or integrations depend on the old column.
- New data has been backfilled and verified.
- A recovery plan exists if an overlooked dependency surfaces.

Dropping the column should be a dedicated migration after the transition window. Never bundle adding columns, backfilling, switching code, and dropping old columns into a single unobservable deployment step.

## 5. Adding a New Column to a Populated Table

Suppose `customers` already holds millions of rows and needs a `preferred_language` column.

### 5.1. Add a Nullable Column First

~~~sql
ALTER TABLE customers
ADD COLUMN preferred_language VARCHAR(10);
~~~

This is generally a safe way to expand a schema since existing rows keep NULL initially. New code must tolerate NULL until backfilling completes.

Avoid immediately adding `NOT NULL` before deciding how existing rows will be populated and ensuring every write path supplies a value.

### 5.2. Backfill Legacy Data

If language can be derived from a legacy field or business rule, run a controlled backfill. If it cannot be derived, agree on a fallback value with the business owner. Never pick an arbitrary value solely to satisfy a constraint.

Example:

~~~sql
UPDATE customers
SET preferred_language = 'vi'
WHERE preferred_language IS NULL;
~~~

For small tables, a simple statement suffices. For large tables, a single UPDATE can hold a long transaction, retain locks, generate heavy WAL/redo logs, and impact replication. Split into batches in that case.

### 5.3. Update Code to Always Supply a Value

Once the column exists, the new application version must ensure every customer creation path supplies a value:

- Creation APIs.
- File imports.
- Message consumers.
- Batch jobs.
- Administrative scripts.
- Test fixtures or seed data.

Updating only the controller is insufficient if another writer creates rows.

### 5.4. Add NOT NULL After Data Is Complete

After backfilling and ensuring all writers supply values, verify:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE preferred_language IS NULL;
~~~

Only when the count is 0 and new writers produce no NULLs, consider:

~~~sql
ALTER TABLE customers
ALTER COLUMN preferred_language SET NOT NULL;
~~~

`ALTER COLUMN` syntax varies by database. Before running on large tables, check how the engine validates the constraint and how long it locks the table. Some databases support adding a constraint in an unvalidated state and validating separately; others require a full scan or different locks.

## 6. Default Values in the Database vs. in the Application

Default values can be configured at two layers. They address different needs.

### 6.1. Database DEFAULT

Example:

~~~sql
ALTER TABLE customers
ADD COLUMN status VARCHAR(20) DEFAULT 'ACTIVE';
~~~

A database default applies when an `INSERT` omits the column or explicitly specifies the `DEFAULT` keyword for that column. If an `INSERT` names the column and binds SQL `NULL`, the database normally stores `NULL` rather than applying the default.

Example:

~~~sql
-- Database uses default ACTIVE for status.
INSERT INTO customers (id, name)
VALUES (101, 'An');

-- NULL is passed explicitly; DEFAULT does not automatically replace NULL.
INSERT INTO customers (id, name, status)
VALUES (102, 'Binh', NULL);
~~~

Database defaults are useful when:

- Multiple applications or scripts write to the same table.
- Default values must be safeguarded at the database layer.
- An older writer is unaware of a new column and omits it in `INSERT`.
- Data is inserted directly from operational tools or external batches.

### 6.2. Default Values in the Java/Domain Model

The application can assign defaults when constructing objects:

~~~java
public record Customer(
        Long id,
        String name,
        String status
) {
    public static Customer register(Long id, String name) {
        return new Customer(id, name, "ACTIVE");
    }
}
~~~

Application/domain defaults are useful when:

- Default rules are part of business logic.
- Code needs to know the value before saving.
- Validations or calculations depend on the default value.
- Domain objects should be valid immediately upon creation.

Do not rely on database defaults to replace domain behavior if the application needs the value before writing. Conversely, Java defaults do not protect external writers outside that application.

### 6.3. Do Not Assume Java Null Triggers Database DEFAULT

This is a critical detail with Spring Data JDBC. If generated `INSERT` statements include the `status` column and bind Java `null`, the database receives SQL `NULL`; the column's default is not necessarily applied.

Example SQL with two different semantics:

~~~sql
INSERT INTO customers (id, name)
VALUES (?, ?);

INSERT INTO customers (id, name, status)
VALUES (?, ?, NULL);
~~~

In the first statement, the database can apply `status`'s default. In the second, `status` is explicitly passed `NULL`.

With Spring Data JDBC generated SQL, check the mapping and actual SQL statements on your running version. Never assume a Java `null` property causes the framework to omit the column. If a database default is needed, you can:

- Assign the default in the domain model before saving.
- Use custom SQL that intentionally omits the column or uses `DEFAULT`.
- Design a dedicated insert path matching the schema.

Do not add a database default while letting the model and application logic assume a different value. Both layers must enforce one consistent policy.

## 7. Does DEFAULT Automatically Backfill Legacy Rows?

Do not assume adding a column with `DEFAULT` always produces the exact same physical and operational behavior across every database.

When adding a new column, a database might:

- Present the default for existing rows via metadata mechanisms.
- Write the default value into existing rows via a table rewrite.
- Perform DDL requiring a scan or table lock.
- Behave differently depending on database version and default expression type.

Even when a database permits adding `NOT NULL DEFAULT ...` in a short command, cost and semantics depend on the engine/version. A constant default may optimize differently from a dynamic expression default such as a timestamp.

For large tables, split the question into two parts:

1. How to add the column with minimal schema impact?
2. How to populate accurate values for historical rows and verify the result?

If legacy rows need values computed from multiple columns, a constant default cannot replace a business backfill.

## 8. What Is a Backfill and When Is It Needed?

A backfill is the process of populating or converting existing data to satisfy a new schema or model.

Examples:

- Adding `normalized_email` computed from legacy `email`.
- Splitting `full_name` into `given_name` and `family_name`.
- Converting numeric status codes to strings.
- Populating `created_at` for historical rows.
- Creating a new table from data currently stored inside an old JSON column.
- Populating a new foreign key based on an existing relationship.

A backfill is not just a bulk UPDATE. A safe backfill must define:

- Authoritative source data.
- Transformation formula.
- What counts as missing data.
- Whether it can be re-run safely.
- How to handle invalid or underivable rows.
- How to coordinate with active writers.
- How to measure progress and verify results.

## 9. Designing an Idempotent Backfill

An idempotent backfill can be re-run without corrupting data or causing duplicate side effects. This matters because jobs can stop mid-run, time out, or be restarted after an incident.

Example normalized email backfill:

~~~sql
UPDATE customers
SET normalized_email = LOWER(TRIM(email))
WHERE normalized_email IS NULL
  AND email IS NOT NULL;
~~~

The `normalized_email IS NULL` condition skips rows already processed or already populated by new writers.

If rows need updating when the source changes, the rules differ and require explicit conflict control. Never remove the predicate just to "make sure every row gets rewritten," as doing so can overwrite fresh values created by the application.

### 9.1. Idempotency Does Not Mean Ignoring Errors

If an email is invalid or a legacy name cannot be split, do not silently write a bogus value. You can:

- Record failed rows in an exception/quarantine table.
- Store the ID and failure reason for manual remediation.
- Mark a separate backfill status.
- Fix source data and re-run.

A job should be safely re-runnable while still surfacing unconvertible data.

### 9.2. Handling Intentional NULL Values

Not every NULL means "not yet backfilled." If NULL is a valid business state, use a separate status column or marker to distinguish states:

~~~text
backfill_status:
  PENDING
  COMPLETED
  NEEDS_REVIEW
~~~

Do not overload NULL to mean both "unprocessed" and "user provided no value" when those two states carry different meanings.

## 10. Splitting Backfills into Batches

For large tables, avoid one giant transaction unless table-wide atomicity is strictly required. Process in batches and commit each chunk.

### 10.1. Keyset Pagination by Primary Key

Suppose the table has increasing IDs. Fetch a batch of IDs after the checkpoint:

~~~sql
SELECT id
FROM customers
WHERE id > :last_id
ORDER BY id
LIMIT :batch_size;
~~~

Then update that range:

~~~sql
UPDATE customers
SET normalized_email = LOWER(TRIM(email))
WHERE id > :last_id
  AND id <= :batch_end_id
  AND normalized_email IS NULL
  AND email IS NOT NULL;
~~~

Keyset pagination tracks the last processed key value, avoiding escalating `OFFSET` costs and avoiding shifting row positions that cause skipped or duplicated rows while data changes.

`LIMIT` and bind parameter syntax depend on the database. You can fetch ID lists in the application and execute batch updates, or use CTE/update syntax supported by the engine.

### 10.2. Keep Each Batch a Short Transaction

Example service processing one batch:

~~~java
@Service
public class CustomerBackfillWriter {

    private final JdbcTemplate jdbc;

    public CustomerBackfillWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public int backfillRange(long firstId, long lastId) {
        return jdbc.update("""
                UPDATE customers
                SET normalized_email = LOWER(TRIM(email))
                WHERE id >= ?
                  AND id <= ?
                  AND normalized_email IS NULL
                  AND email IS NOT NULL
                """,
                firstId,
                lastId
        );
    }
}
~~~

A coordinator invokes the writer range by range. Because `backfillRange` lives on another bean and is called via a proxy, each invocation can run in its own transaction. After each batch commits, the coordinator updates the checkpoint.

Do not wrap the entire job in an outer transaction if your goal is per-batch commits; an outer transaction with `REQUIRED` propagation causes child methods to join one long transaction.

### 10.3. Storing Checkpoints

You can store checkpoints in a job table:

~~~sql
CREATE TABLE migration_job_checkpoint (
    job_name VARCHAR(100) PRIMARY KEY,
    last_processed_id BIGINT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

After a successful batch, update `last_processed_id`. If the process stops, the next run resumes from the checkpoint.

Checkpoints should commit consistently with the completed batch. If a checkpoint commits before the data, the job may skip unbackfilled rows. If data commits before the checkpoint, the job may reprocess one batch—which is safe when the backfill is idempotent.

## 11. Backfilling While the Application Is Still Writing Data

This is often the hardest part. Suppose a job is backfilling `normalized_email` from `email`, while the application continues updating `email`.

A race can occur:

1. Job reads old email.
2. User changes email.
3. Application writes new email.
4. Job writes normalized email computed from the old email.

The result is two out-of-sync columns.

Several strategies exist:

### Strategy A — New Writers Update Both Columns

Compatible application versions write `email` and `normalized_email` in the same transaction. The backfill only touches rows where `normalized_email IS NULL`. Values written by new writers will not be overwritten by the job.

This is straightforward once all legacy writers have been retired or cannot produce rows lacking the new column.

### Strategy B — Temporary Triggers

A database trigger can maintain the new column whenever any writer updates the old column. Triggers help when multiple writers exist or cannot deploy simultaneously, though they split write logic between application and database. Explicit migrations are needed to create and later drop the trigger.

### Strategy C — Quiesce Writers

Pause writes during a maintenance window, backfill, verify, then re-enable writers. This is simple to reason about, though it may not meet availability targets.

### Strategy D — Version or Timestamp Synchronization

The backfill can read a source version and only write if the version has not changed:

~~~sql
UPDATE customers
SET normalized_email = :computed_value
WHERE id = :id
  AND source_version = :version_read;
~~~

If the source changed, 0 rows update and the job re-reads. This requires a version column or reliable change detection.

No single strategy fits every system. Choose based on writer count, ability to pause writers, availability requirements, and desired consistency guarantees.

## 12. Backfilling Relationships and New Foreign Keys

A migration may add a new foreign key to an existing table. For example, orders previously stored a text customer code, and now need to reference `customers.id`.

Typical workflow:

1. Add a nullable `customer_id` column.
2. Deploy new code that populates `customer_id` while still understanding legacy data.
3. Backfill `customer_id` by looking up legacy keys.
4. Inspect rows where no matching customer is found.
5. Verify no NULLs or orphans remain.
6. Add the foreign key constraint.
7. Switch reads to the new relationship.
8. After a compatibility period, drop the old column if no longer used.

Before adding the constraint:

~~~sql
SELECT COUNT(*)
FROM purchase_orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

The count must be 0 before adding the foreign key if the schema forbids orphans.

If the database supports adding an unvalidated constraint and validating separately, use that strategy to minimize lock duration. Syntax and benefits depend on the engine; do not copy PostgreSQL syntax to other databases.

## 13. Indexes and Constraints in Large Migrations

Adding indexes to large tables can impact active writers. Check:

- Does the database support creating indexes concurrently/online?
- Is that command allowed inside a migration transaction?
- How long can reads or writes tolerate locking?
- Are index storage and temporary space sufficient?
- Is the index genuinely needed for new queries?

New constraints also require checking existing data. Example adding a unique constraint:

~~~sql
SELECT normalized_email, COUNT(*)
FROM customers
WHERE normalized_email IS NOT NULL
GROUP BY normalized_email
HAVING COUNT(*) > 1;
~~~

If backfilling produces duplicate values, adding the unique constraint will fail. Define duplicate-resolution rules before the contract migration.

Never delete invalid data arbitrarily just to make a constraint migration pass. Keep a report of rows needing correction and obtain business decisions for each case.

## 14. Controlling Time, Values, and Determinism in Backfills

A backfill should produce repeatable, explainable results. Watch out for:

- **Timestamps:** choose explicit timezones and time sources; never mix local time with UTC.
- **Strings:** define trimming, Unicode normalization, collation, and casing rules.
- **Currency:** never use floating point for monetary math; define scale and rounding.
- **Enums/statuses:** maintain explicit mappings between old codes and new statuses; never map unknown values to a fake valid status.
- **JSON:** define schema versions and handling for missing/mistyped fields.
- **IDs/foreign keys:** check uniqueness and orphans before adding constraints.
- **NULLs:** distinguish missing data, unprocessed rows, and legitimately null business values.

If the backfill formula relies on mutable external data, snapshot the source or record a version so results remain reproducible.

## 15. Observing and Operating Backfills

Never run a large job without visibility into whether it is progressing or stuck.

Metrics to monitor:

- Total expected rows.
- Processed row count.
- Rows still missing values.
- Rows that failed conversion.
- Throughput (rows/second) or time per batch.
- Transaction duration and lock wait time.
- CPU, I/O, WAL/redo log volume, and replication lag.
- Retry counts and errors by type.

Log per batch with checkpoints/ranges, without logging full personal data or sensitive payloads. Consider adding a dry-run mode to count eligible rows and failing rows before writing.

### 15.1. Throttling and Safe Stopping

A backfill job should support:

- Adjusting batch size.
- Pausing between batches when the database is under heavy load.
- Stopping and resuming from a checkpoint.
- Limiting retry attempts.
- Halting if error rates exceed a threshold.
- Re-running an already-processed range without corrupting data.

Do not hardcode one batch size for every database and table. Benchmark on a production-like environment and tune accordingly.

## 16. Auditing Legacy Schemas and Detecting Drift

Migration history shows which changesets the migration tool executed; it does not always prove the physical schema matches expectations completely.

Schema drift can happen when:

- A DBA makes manual edits.
- An out-of-band script adds or drops columns.
- A migration partially ran on a database lacking transactional DDL for that statement.
- Staging and production run different database versions.
- A hotfix was applied without recording a migration.

Audit steps:

1. Inspect migration history in each environment.
2. Compare actual schema metadata against expected schema.
3. Check columns, types, nullability, defaults, indexes, constraints, and triggers.
4. Run queries checking for NULLs, duplicates, and orphans.
5. Inspect the actual SQL emitted by Spring Data JDBC mappings.
6. Record any manual changes as traceable migrations if they must be kept.

Never directly edit Flyway/Liquibase history tables to mask drift. Use the tool's proper repair/clear/mark workflow, and only after understanding actual database state.

## 17. Testing Migrations and Mapping Code

A migration succeeding on an empty database does not prove it is safe for production. At a minimum, test:

### 17.1. Fresh Database

- Run all migrations from the beginning.
- Start the new application.
- Create, read, update, and delete key aggregates.
- Confirm defaults, constraints, and indexes match expectations.

### 17.2. Upgrade from Legacy Schema

- Create a database at the pre-migration version.
- Seed representative data, including NULLs, duplicates, and edge cases.
- Run the new migration.
- Run the backfill.
- Verify converted values and constraints.
- Start the new code and exercise read/write flows.

### 17.3. Compatibility During Rolling Deployment

- Verify old code runs on the post-expand schema.
- Verify new code handles unbackfilled rows.
- Verify old writers do not produce rows missing required new data unexpectedly.
- Only execute contract after all old writers are gone.

### 17.4. Testing on Production-Like Databases

H2 is great for fast tests, yet it cannot replace the production database when verifying:

- DDL locks and transactional DDL.
- Defaults when adding columns.
- Update/batch/index syntax.
- Constraint validation.
- Collation, timezones, and data types.
- Execution plans and backfill performance.

Use Testcontainers or matching integration environments when migrations rely on database-specific semantics.

## 18. Complete Example: Splitting full_name into given_name and family_name

Suppose the old schema is:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);
~~~

The goal is adopting two new columns with zero-downtime deployment.

### Step 1 — Expand

A new migration adds nullable columns:

~~~sql
ALTER TABLE customers
ADD COLUMN given_name VARCHAR(100);

ALTER TABLE customers
ADD COLUMN family_name VARCHAR(100);
~~~

Keep `full_name` so old code keeps functioning.

### Step 2 — Deploy Compatible Code

The new version:

- Reads the two new columns when populated.
- Falls back to `full_name` for unbackfilled rows.
- When creating or updating names, writes old and new columns in sync within the same transaction.
- Does not assume every name splits accurately by taking the first word and the remainder.

Name-splitting rules must be confirmed with business owners since personal names vary in components, ordering, and cultural conventions.

### Step 3 — Batch Backfill

Once an approved splitting rule exists, run a job by ID range. Update only rows lacking new values and persist checkpoints.

~~~sql
UPDATE customers
SET given_name = :given_name,
    family_name = :family_name
WHERE id = :id
  AND given_name IS NULL
  AND family_name IS NULL;
~~~

Rows that cannot be split reliably are written to a review list rather than guessed.

### Step 4 — Verify

~~~sql
SELECT COUNT(*)
FROM customers
WHERE given_name IS NULL
   OR family_name IS NULL;
~~~

Count rows flagged for review and categorize them. Also check rows where the two new columns do not match the legacy source under the agreed rule.

### Step 5 — Switch Read Path

Deploy the version reading `given_name` and `family_name` as the authoritative source. Keep the fallback during the compatibility window if legacy jobs or instances remain.

### Step 6 — Contract

After confirming no code uses `full_name`, create a dedicated migration to drop the old column. If application rollback might be needed, remember that once the old column is dropped, old application versions cannot safely run again without a restorative migration or compatibility strategy.

## 19. Schema Migration and Backfill Deployment Checklist

Before deploying:

- [ ] Identify production database engine and version.
- [ ] Identify all writers, readers, jobs, and integrations using the table.
- [ ] Create versioned migrations; never modify applied migrations.
- [ ] Check DDL impact, locking, table rewrites, and replication.
- [ ] Add new columns in a backward-compatible way.
- [ ] Define default values in application and database; ensure consistency.
- [ ] Check whether `INSERT` omits columns or binds NULL.
- [ ] Write idempotent, checkpointed backfills.
- [ ] Batch updates with appropriate transaction boundaries.
- [ ] Handle concurrent writers during backfill.
- [ ] Check for NULLs, duplicates, orphans, and unconvertible data.
- [ ] Add `NOT NULL`/unique/foreign key constraints only after data qualifies.
- [ ] Test fresh schemas and upgrades from legacy schemas.
- [ ] Drop legacy structures only after every consumer has switched.

## 20. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Old instances fail after new schema deploy | Migration dropped/renamed columns while old code still ran | Use expand-migrate-contract and retain legacy structures during transition |
| New inserts violate NOT NULL | Code or another writer omits the new column | Add nullable first, update all writers, backfill, then tighten constraint |
| Database DEFAULT is ignored | SQL INSERT names the column and explicitly binds NULL | Omit column from INSERT or use DEFAULT; inspect Spring Data JDBC SQL |
| Historical rows remain NULL after adding DEFAULT | Wrong assumption about database ALTER TABLE behavior | Run explicit backfill and verify on exact engine/version |
| Backfill overwrites fresh data | Job updates all rows while app continues writing | Use predicates like `target IS NULL`, version checks, dual-writes, or triggers |
| Job processes rows twice or skips rows | Using OFFSET on a mutating table or faulty checkpoints | Use stable-key keyset pagination and transaction-aligned checkpoints |
| Backfill slows down database | Single huge transaction, oversized batches, or missing indexes | Batch, throttle, monitor locks/I/O, and tune plan |
| Adding constraint fails | Remaining NULLs, duplicates, or orphans | Run audit queries and clean data before adding constraint |
| Migration passes in staging but fails in production | Different DB version, data edge cases, or DDL semantics | Test upgrade on production-like snapshot and verify engine/version |
| Rolled-back app cannot use schema | Contract ran too early | Delay contract; prepare restorative or forward-fix migration |

## 21. Hands-on Exercises

**Exercise 1 — Adding a New Column.** Add `preferred_language` to a populated customer table. Deploy code accepting NULL, backfill historical values, then add `NOT NULL`.

**Exercise 2 — Comparing DEFAULT and NULL.** Run two `INSERT` statements: one omitting a column with a default and one explicitly passing `NULL`. Observe the result on your database.

**Exercise 3 — Inspecting Spring Data JDBC.** Create an entity with a nullable property backed by a column with a database default. Save an object with the property set to `null`, enable SQL logging, and observe whether the framework omits the column or binds `NULL`.

**Exercise 4 — Idempotent Backfill.** Write a job normalizing emails by ID range, updating only rows without a normalized value. Run the job twice and confirm the output is unchanged.

**Exercise 5 — Checkpoints and Resuming.** Stop the job after a few batches. Restart from the checkpoint and confirm no rows are skipped.

**Exercise 6 — Concurrent Writers.** During backfilling, update a source row from another transaction. Test `target IS NULL` and version-check predicates to avoid overwriting fresh data.

**Exercise 7 — Expand-Migrate-Contract.** Write a migration adding new columns, deploy dual-write code, backfill, switch the read path, and then drop the old column in a separate migration.

**Exercise 8 — Constraints.** Backfill a new foreign key. Write a query checking for orphans and add the foreign key constraint only after data is valid.

## 22. Key Takeaways

Schema migrations in live systems must remain compatible with running application versions and existing data. Use versioned migrations, keep applied migrations immutable, and roll out breaking changes across three phases: expand, migrate, and contract.

Database `DEFAULT` only applies when an `INSERT` omits the column or requests `DEFAULT`; passing `NULL` explicitly does not invoke the default. Domain defaults give the application valid objects, while database defaults guard external writers omitting columns. Both policies must agree. With Spring Data JDBC, inspect generated SQL rather than assuming Java `null` properties cause columns to be omitted from `INSERT`.

Backfills require deterministic formulas, idempotency, proper batch sizes, short transactions, checkpoints, and coordination with live writers. Verify NULLs, duplicates, orphans, and unconvertible data before enforcing constraints. Drop legacy schemas only when every instance, job, and integration has moved to the new structure.

### References

- [Spring Boot – Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Flyway – Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)
- [Liquibase – Changesets](https://docs.liquibase.com/concepts/changelogs/changeset.html)
- [PostgreSQL – ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [MySQL – ALTER TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html)

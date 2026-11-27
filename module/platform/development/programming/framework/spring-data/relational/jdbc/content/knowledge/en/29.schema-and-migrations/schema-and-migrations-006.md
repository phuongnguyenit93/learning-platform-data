# Limitations of Schema Diff Generation: Renames and Data Conversions

In **Spring Data Relational JDBC (Spring Data JDBC)**, entity and mapping changes often require database schema changes. A property may be renamed, split into two properties, merged from multiple fields, changed to another data type, or moved into a value object. Schema comparison tools (schema diffs) help detect structural differences between two database layouts, but they cannot fully understand the business intent behind a change.

Two scenarios are especially error-prone: **renames** and **data conversions**. When an old column disappears and a new column appears, a diff tool may propose DROPPING the old column and ADDING the new one, even when the real intent was a RENAME that preserves existing data. When a column's type or structure changes, a tool may propose ALTER COLUMN without knowing how each legacy value must be transformed into the new representation.

Therefore, schema diff results should be treated as **suggestions for developers to review**, while migrations remain responsible for preserving data, performing transformations, and bringing the schema to a state compatible with the new application version.

## 1. Schema Mapping and Schema Migration Are Two Different Concerns

Spring Data JDBC uses domain model metadata to map objects to tables and columns:

- `@Table` identifies the entity's table.
- `@Column` maps a property to a column.
- `@Id` identifies the primary key.
- `@Embedded` flattens a value object into columns in the same table.
- `@MappedCollection` describes child members owned by an aggregate and the column referencing the root.

These annotations describe **how the application reads and writes data**. They do not supply the full schema change history or production data conversion rules.

Example entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;
}
~~~

The mapping states that property `displayName` corresponds to column `display_name`. If you rename the property or column, the database needs a migration so the new schema matches the mapping. Changing an annotation in Java does not automatically rename an existing column in the database.

### Responsibilities of Each Component

| Component | Responsibility |
|---|---|
| Spring Data JDBC mapping | Maps aggregates/properties to tables and columns |
| Schema diff | Compares database structure at two points in time |
| Migration script/changelog | Executes ordered, reproducible schema changes |
| Data migration/backfill | Transforms stored values |
| Application code | Reads/writes according to current version's mappings and domain rules |

Do not treat schema diff as a tool that understands your domain model and can decide how to migrate data on its own.

## 2. What Does Schema Diff Actually Compare?

Schema diff tools typically compare metadata from two schemas or snapshots, such as:

- Tables and views.
- Columns, column names, data types, and lengths.
- Nullability and defaults.
- Primary keys, foreign keys, and unique constraints.
- Indexes.
- Certain sequences, triggers, or database objects depending on the tool.

Example old schema:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
~~~

New schema:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(160) NOT NULL
);
~~~

Comparing column names and definitions, the tool sees:

| Old schema | New schema | Detected difference |
|---|---|---|
| `display_name` | Absent | Column removed |
| No `full_name` | `full_name` | New column added |

Structurally, the two columns have different names. Yet the tool cannot know for sure whether:

- `display_name` was renamed to `full_name`.
- `full_name` is a brand-new field and `display_name` truly should be deleted.
- Legacy data must be combined with another field.
- Part of the old content must be normalized before writing to the new column.

Two schemas can look identical in metadata while carrying completely different business meanings. Schema diff sees structure; it cannot infer intent.

## 3. Why Are Renames Often Interpreted as DROP and ADD?

Column names are one of the primary cues tools use to match columns across two snapshots. When a name changes, the tool may not know the two columns represent the same attribute.

Example:

~~~text
Before:
customers.display_name VARCHAR(120)

After:
customers.full_name VARCHAR(160)
~~~

A simple diff may generate:

~~~sql
ALTER TABLE customers DROP COLUMN display_name;
ALTER TABLE customers ADD COLUMN full_name VARCHAR(160);
~~~

If you execute this migration verbatim, existing data in `display_name` is lost. The new column is created empty without previous customer names.

Meanwhile, the actual intent might have been simply:

~~~sql
ALTER TABLE customers
RENAME COLUMN display_name TO full_name;
~~~

A rename preserves existing values in every row. This is why generated diff scripts must never be executed blindly on databases holding important data without review.

### Rename-Detection Heuristics Are Not Proof

Some tools suggest renames based on name similarity, data types, or metadata. Heuristics can help, yet ambiguities remain:

- Two old columns share a similar type and one new column appears.
- A column is renamed while simultaneously changing type/length.
- An old column was genuinely dropped and an unrelated new column was added.
- Two columns were swapped, merged, or split.

Only a developer who understands the business change can confirm which column corresponds to which and how data should be preserved.

## 4. Safe Column Rename Migrations

When the goal is simply renaming a column while keeping data intact, write a migration explicitly expressing the rename.

### PostgreSQL

~~~sql
ALTER TABLE customers
RENAME COLUMN display_name TO full_name;
~~~

### MySQL

In MySQL, column-rename syntax depends on the version. Modern syntax example:

~~~sql
ALTER TABLE customers
RENAME COLUMN display_name TO full_name;
~~~

Some older versions/syntaxes use `CHANGE COLUMN` and require restating the full column definition:

~~~sql
ALTER TABLE customers
CHANGE COLUMN display_name full_name VARCHAR(120) NOT NULL;
~~~

When using `CHANGE COLUMN`, you must specify the exact type, nullability, default, comment, and attributes to retain. Always verify syntax against your target database version.

### Updating Java Mappings

After the migration, the entity maps to the new column:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

Migrations and code must follow a compatibility plan. If old application instances still run while the migration executes, renaming immediately can break older versions expecting `display_name`. For systems requiring rolling deployments or zero downtime, use the expand-contract strategy covered later.

## 5. Renaming a Java Property Is Not the Same as Renaming a SQL Column

You can rename a Java property without renaming the database column by keeping `@Column`:

~~~java
@Column("display_name")
private String fullName;
~~~

In this case:

- Java code uses `fullName`.
- The database continues using `display_name`.
- No column-rename migration is needed just because the Java property changed.

Conversely, if you want to rename both the property and the column, update the mapping and write a migration together:

~~~java
@Column("full_name")
private String fullName;
~~~

Do not confuse the two changes:

| Change | Schema change required? |
|---|---|
| Rename property only, keep old `@Column` | No |
| Rename column and update `@Column` | Yes |
| Rename property using default naming strategy where column derives from property | Usually yes |
| Change table name via `@Table` | Yes, if the physical table name also changes |

Keeping explicit mappings is sometimes useful to decouple code refactoring from schema migrations. However, avoid letting property names and column names diverge unnecessarily when it harms readability.

## 6. Data Conversions Cannot Be Inferred from Schema Alone

A schema diff can detect that a column's type changed:

~~~text
Before: customers.phone_number VARCHAR(30)
After:  customers.phone_number VARCHAR(20)
~~~

It may propose `ALTER COLUMN` to shrink the length. Yet it does not know:

- Do any rows contain strings longer than 20 characters?
- Should country codes be normalized?
- Should spaces or separators be stripped?
- Is oversized data an error or meaningful business information to retain?
- If truncated, should the removed part be saved elsewhere?

A type change often needs a **data transformation** before or during the migration. For example, normalizing a free-form status field into a standard enum:

~~~text
Before: status = "in progress", "IN_PROGRESS", "processing"
After:  status = "PROCESSING"
~~~

Schema diff sees `VARCHAR` in both snapshots. It does not know that distinct legacy strings must be normalized into a single canonical status.

## 7. Example Data Conversion Using UPDATE

Suppose an old `status` column contains multiple spellings:

~~~sql
SELECT DISTINCT status
FROM sales_orders;
~~~

Results might include:

~~~text
in progress
IN_PROGRESS
processing
completed
done
cancelled
~~~

To normalize into the new value set:

~~~sql
UPDATE sales_orders
SET status = CASE
    WHEN LOWER(TRIM(status)) IN ('in progress', 'in_progress', 'processing')
        THEN 'PROCESSING'
    WHEN LOWER(TRIM(status)) IN ('completed', 'done')
        THEN 'COMPLETED'
    WHEN LOWER(TRIM(status)) = 'cancelled'
        THEN 'CANCELLED'
    ELSE 'UNKNOWN'
END;
~~~

This encodes an explicit business rule in the migration. Developers must decide how to handle unrecognized values; do not silently default to `UNKNOWN` if doing so discards data that needs investigation.

Before running UPDATE in production:

1. List distinct values and row counts for each value.
2. Define mappings for every existing value.
3. Decide how to handle NULLs and unrecognized values.
4. Test the migration on a representative copy of production data.
5. Reconcile counts and value distributions after conversion.

## 8. Type Conversions Require Explicit Rules

For example, converting string `amount_text` to numeric column `amount`:

~~~text
"1250.50" -> 1250.50
"1,250.50" -> 1250.50
"unknown" -> cannot be converted directly
~~~

Not every string parses cleanly as a number. The migration must specify locale, decimal separator, grouping separator, currency units, and invalid-value handling.

A safer strategy is adding a new column:

~~~sql
ALTER TABLE invoices
ADD COLUMN amount_numeric NUMERIC(14, 2);
~~~

Backfill validated rows:

~~~sql
UPDATE invoices
SET amount_numeric = CAST(amount_text AS NUMERIC(14, 2))
WHERE amount_text ~ '^[0-9]+([.][0-9]{1,2})?$';
~~~

Note: the regex operator and `CAST` expression above are PostgreSQL-specific. MySQL and other databases have different syntax, casting behavior, and validation functions.

Then find unconverted rows:

~~~sql
SELECT id, amount_text
FROM invoices
WHERE amount_text IS NOT NULL
  AND amount_numeric IS NULL;
~~~

Only after invalid rows have been resolved and verified should you consider setting `NOT NULL`, switching the application to the new column, and dropping the old column.

## 9. Merging Columns into a Value Object or Splitting One Column into Many

Schema diff detects added/removed columns, but cannot automatically infer merge/split rules.

### Splitting a Column

Before:

~~~sql
customers.full_address VARCHAR(300)
~~~

After:

~~~sql
customers.street VARCHAR(120)
customers.city VARCHAR(80)
customers.postal_code VARCHAR(20)
~~~

Free-form addresses cannot be split reliably by schema diff alone. You need a parser or specific data rules; addresses may lack components, contain commas inside street names, or vary in format by country.

### Merging Multiple Columns

Before:

~~~sql
customers.first_name VARCHAR(80),
customers.last_name VARCHAR(80)
~~~

After:

~~~sql
customers.full_name VARCHAR(160)
~~~

You can backfill using:

~~~sql
UPDATE customers
SET full_name = TRIM(
    COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')
);
~~~

The concatenation operator `||` works in PostgreSQL and several other databases; MySQL syntax differs. More importantly, concatenation rules must define how to handle empty names, NULLs, whitespace, and multi-part names.

## 10. Expand-Migrate-Contract for Live Systems

If an application runs multiple instances or performs rolling updates, renaming a column directly can make old and new versions incompatible during the transition window. The **expand-migrate-contract** strategy breaks the change into compatible steps.

Suppose we rename `display_name` to `full_name`:

~~~mermaid
flowchart TD
    A["1. Expand<br/>Add full_name"]
    B["2. Compatible app<br/>Read new/old column, write both in sync"]
    C["3. Backfill<br/>Copy old data to new column"]
    D["4. Switch<br/>App uses full_name only"]
    E["5. Contract<br/>Stop writing and drop display_name"]
    A --> B --> C --> D --> E
~~~

### Step 1: Expand Schema

Add the new column while keeping the old column:

~~~sql
ALTER TABLE customers
ADD COLUMN full_name VARCHAR(160);
~~~

The new column starts nullable so older application versions continue working.

### Step 2: Deploy Compatible Code

The intermediate version can read the new value if present and fall back to the old column otherwise. On write, the application keeps both columns synchronized during the transition.

Dual-writing both columns must be designed carefully. If multiple writers exist, define one authoritative source and prevent two versions from writing conflicting rules.

### Step 3: Backfill

Copy existing data:

~~~sql
UPDATE customers
SET full_name = display_name
WHERE full_name IS NULL;
~~~

For large tables, backfill in batches or by primary key ranges to limit lock duration and transaction size. When written idempotently, the statement can run safely multiple times.

### Step 4: Switch the Application to the New Column

After confirming data is synchronized, deploy the version that reads/writes only `full_name`. Monitor logs, NULL counts, and any queries still referencing `display_name`.

### Step 5: Contract

Only when all instances, jobs, reports, and integrated applications have stopped using the old column, drop it:

~~~sql
ALTER TABLE customers
DROP COLUMN display_name;
~~~

Contract is usually the hardest step to reverse. Perform it only after confirming zero old consumers remain and a recovery plan is in place.

## 11. How Should Schema Migrations and Data Migrations Be Organized?

A migration can contain both DDL and DML, but separate intent clearly so changes remain easy to read, review, and operate.

Example order:

1. Add new columns or tables.
2. Add indexes/constraints at the appropriate stage.
3. Transform/backfill data.
4. Validate data after conversion.
5. Update the application to the new mapping.
6. Remove old structures in a later migration.

You do not need to cram every step into a single migration. For small changes on a database supporting transactional DDL, one simple migration may suffice. For large tables or multi-version deployments, multiple smaller migrations control risk far better.

### Migrations Must Be Ordered and Versioned

Flyway example:

~~~text
src/main/resources/db/migration/
├── V001__create_customers.sql
├── V002__add_full_name.sql
├── V003__backfill_full_name.sql
└── V004__drop_display_name.sql
~~~

Flyway runs migrations in version order and records applied history. Normally developers author/edit explicit migration scripts; do not expect Flyway to infer renames or data conversion logic from two snapshots.

With Liquibase, changelogs can express changes via changesets such as `renameColumn`, `addColumn`, `update`, and `dropColumn`. Commands like `diff`/`diffChangeLog` can help spot structural differences between two databases, yet the output still needs review to verify renames, ordering, and data transformations. A structural diff does not replace data-conversion changesets.

Never edit migrations that have already run in shared/production environments to rewrite history. Create a new migration to advance the schema from its current state to the next state.

## 12. Limitations of Schema Diff with Constraints and Indexes

Renaming a column can affect:

- Indexes containing that column.
- Unique constraints.
- Foreign keys.
- Views or materialized views.
- Triggers and stored procedures.
- External queries/reports outside the application.

Depending on the database, some objects update references automatically on rename, while others require manual updates or block the rename. Schema diff may detect differing objects without always understanding a safe ordering of changes.

For example, renaming `customer_code` to `external_code`:

~~~sql
CREATE UNIQUE INDEX ux_customers_customer_code
    ON customers(customer_code);
~~~

After renaming, verify the index still exists with the right definition. If a diff tool proposes dropping and recreating the index, check whether rebuilding is genuinely needed or merely a naming/metadata difference.

For foreign keys, never drop a source column before identifying dependent constraints. Migrations must handle dependencies in a valid order.

## 13. Schema Diff Does Not Fully Validate Data Quality

Two schemas can be structurally identical while the data inside fails new rules.

For example, column:

~~~sql
customers.email VARCHAR(255)
~~~

The new schema adds a unique constraint:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Schema diff can detect the missing constraint. Yet it cannot guarantee existing data has no duplicates:

~~~sql
SELECT email, COUNT(*)
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

If duplicate emails exist, the migration adding the unique constraint will fail. Before applying the constraint, decide how to merge, fix, or reject duplicate records per business rules.

Data checks commonly needed before migrations:

- NULLs in columns about to become NOT NULL.
- Values exceeding new length limits.
- Values unparseable into the new type.
- Duplicate values before adding a unique constraint.
- Orphan rows before adding a foreign key.
- Values outside the new enum/status set.

## 14. Large-Table Backfills and Idempotency

On tables with millions of rows, a single table-wide UPDATE can create a huge transaction, lock many rows, bloat WAL/undo logs, and degrade live workloads. Batch by primary key instead:

~~~sql
UPDATE customers
SET full_name = display_name
WHERE id > :lastId
  AND id <= :nextId
  AND full_name IS NULL;
~~~

The backfill job iterates over ID ranges, tracks progress, and can resume after interruption.

A good backfill should:

- Limit batch scope.
- Be re-runnable without corrupting already-converted data.
- Track processed and failed row counts.
- Support pausing/resuming.
- Throttle execution to avoid overloading the database.
- Run reconciliation queries after each batch or full run.

The `full_name IS NULL` predicate in the example prevents overwriting newer data written by the application. If the application continues synchronizing both columns during backfill, explicitly define the authoritative source and conflict resolution.

## 15. Post-Migration Verification

Do not just check that the migration exited with code 0. Verify schema and data against concrete criteria.

For example, after copying names:

~~~sql
SELECT COUNT(*) AS missing_full_name
FROM customers
WHERE display_name IS NOT NULL
  AND full_name IS NULL;
~~~

Compare values:

~~~sql
SELECT id, display_name, full_name
FROM customers
WHERE display_name IS DISTINCT FROM full_name;
~~~

`IS DISTINCT FROM` is PostgreSQL syntax for NULL-safe comparison. For other databases, use the equivalent comparison.

After migration, verify:

- Columns/types/nullability/defaults match the new mapping.
- Row counts before and after align.
- Values transformed according to rules.
- No invalid or unbackfilled rows remain.
- Indexes, foreign keys, unique constraints, and views work.
- The new application reads and writes successfully.
- External jobs/reports/consumers no longer rely on the old structure.

## 16. Rollback and Data Recovery

Not every migration can be rolled back simply by running inverse DDL.

For example:

- Renaming a column can be renamed back if no conflicting data writes occurred.
- Dropping a column loses data; re-adding the column does not bring back old content.
- Collapsing multiple legacy values into one canonical status can lose the distinction between old values.
- Truncating string lengths or rounding numbers may be irreversible.
- Merging first/last names into full name may not split back accurately.

For lossy changes, take backups, keep the old column during the transition, or preserve original values in a recoverable location. A rollback script that only restores structure does not restore lost data.

Before production migrations:

1. Establish backup/restore points and recovery time objectives.
2. Test the migration on a representative copy of data.
3. Estimate duration, locks, and log volume.
4. Define stop/go criteria.
5. Plan compatibility between old and new application versions.

## 17. Process for Reviewing Schema Diff Output

When a tool generates scripts/changelogs, review every change against these questions:

| Question | What to verify |
|---|---|
| Are a dropped column and a new column actually one renamed attribute? | Use RENAME and preserve data if yes |
| Did the data type change? | Are conversion rules and old-value checks in place? |
| Did column length shrink? | Do any rows exceed the new limit? |
| Did nullability change? | Does existing data contain NULLs? |
| Adding unique/FK/check constraints? | Does existing data satisfy the constraints? |
| Was an index dropped/recreated? | Is rebuilding actually needed, or just metadata diff? |
| Do multiple app versions run concurrently? | Is expand-contract required? |
| Is a data transformation needed? | Are separate migrations and error handling defined? |
| Could rollback lose data? | Are backups or recovery strategies ready? |

Only after review should scripts go into the versioned migration directory. Never run unreviewed diff scripts in production.

## 18. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Running diff-generated DROP + ADD for a column that was merely renamed | Old column data is lost | Replace with database-appropriate RENAME operation |
| Assuming diff tools understand business intent | Wrong data mapping | Verify renames and transformations manually |
| Changing `@Column` without schema migration | Runtime cannot find new column | Deploy DDL and mappings per plan |
| Renaming Java property assuming DB renames automatically | Schema and mapping diverge | Keep old `@Column` or migrate column to match |
| Altering column type without checking legacy data | Migration fails or coerces/truncates data | Pre-check, backfill, and handle invalid values |
| Adding NOT NULL/UNIQUE/FK before cleaning data | Constraint creation fails | Check and remediate data first |
| One-shot backfill on a huge table | Excessive transaction/lock/log overhead | Batch updates and track progress |
| Backfill overwrites newer data | Lost updates during rollout | Idempotent predicates and authoritative-source rules |
| Dropping old column immediately on new code deploy | Old instances/jobs fail | Use expand-contract and wait for all consumers |
| Editing an already-executed migration | Environment histories diverge | Create a new migration |
| Assuming DDL rollback restores data | Lost data stays lost | Back up or keep original data during transition |
| Forgetting indexes, views, triggers, or FKs on column | Queries or constraints fail | Check all schema dependencies |

## 19. Exercises

1. Create a `customers` table with column `display_name` and insert sample rows.
2. Rename the entity property to `fullName` while keeping `@Column("display_name")`; verify why no migration is needed yet.
3. Change the mapping to `@Column("full_name")` and inspect what changes a schema diff tool might suggest.
4. Write a `RENAME COLUMN` migration to preserve data; verify row counts and values after renaming.
5. Simulate DROP + ADD on a test database and observe old data being lost.
6. Add `full_name` alongside `display_name`; backfill data using a conditional UPDATE.
7. Write checks for unbackfilled rows and rows with differing values.
8. Normalize several legacy status strings into a new status set using CASE; handle unrecognized values.
9. Add a unique constraint after checking for duplicates.
10. Design expand-migrate-contract for an application running multiple instances in a rolling deployment.
11. Split a backfill into ID batches and verify it can be re-run safely.
12. Write a rollback plan specifying which changes are reversible and which data requires backups.

## 20. Key Takeaways

Schema diffs detect structural differences between two schemas, yet they cannot reliably infer rename intent, column split/merge rules, or how individual values should be converted. One column disappearing and another appearing might be a rename, or it might be removing one attribute and adding a completely new one.

With Spring Data JDBC, mapping annotations describe how the application maps aggregates; migrations are where ordered schema and data changes are defined. Review every diff script, replace DROP/ADD with RENAME when preserving data, write explicit backfills for value transformations, validate data before enforcing constraints, and use expand-migrate-contract when multiple application versions must coexist. Data preservation and deployment compatibility—not merely making two schema snapshots look alike—must drive migration decisions.

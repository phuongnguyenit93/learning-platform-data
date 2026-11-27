# Expand-and-Contract Pattern for Application Compatibility During PostgreSQL Schema Changes

Changing a schema in a system serving live traffic often happens concurrently with deploying multiple application versions. For some period, older and newer versions may simultaneously read from or write to the same database. If a migration renames a column, drops a column, changes a data type, or alters a constraint immediately, a still-running application version can fail mid-flight.

The **expand-and-contract** pattern solves this by splitting a large change into small steps that can coexist. First, expand the schema to support both old and new behavior. Next, deploy application code capable of using the new schema, migrate data and traffic in steps, verify no consumers still depend on the old structure, and only then contract the schema by removing legacy elements.

This approach is especially valuable for rolling deployments, blue/green deployments, microservices, systems with background workers, and databases shared across multiple applications. It also applies to renaming columns, splitting tables, changing data types, normalizing data, changing relationships, and evolving storage APIs.

This lesson belongs to the **Schema Migrations** chapter of the *Database Engine Relational PostgreSQL* module. It covers multi-version compatibility principles, the expand/migrate/contract workflow, PostgreSQL SQL examples, data backfilling, dual-write/dual-read, lock control, testing, rollback, and operational checklists.

> **Principle:** Every deployment step must keep the schema usable by all active application versions at that moment. Remove legacy structures only after proving no readers, writers, jobs, or consumers still depend on them.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why direct schema changes can break running applications.
2. Describe the expand, migrate, and contract model.
3. Design a schema that serves old and new application versions simultaneously.
4. Distinguish backward compatibility and forward compatibility during rollout.
5. Sequence migration deployments and application releases.
6. Add columns, tables, indexes, and constraints safely in stages.
7. Rename columns using a replacement strategy with a transition period.
8. Change data types using shadow columns and backfills.
9. Execute batched, retryable, load-controlled backfills.
10. Design dual-write and dual-read with a clear source of truth.
11. Switch readers and writers via feature flags or controlled rollouts.
12. Detect legacy consumers in workers, ETL, BI, CDC, and manual SQL.
13. Reduce risks from locks, table rewrites, and index builds.
14. Use `NOT VALID`, `VALIDATE CONSTRAINT`, and `CREATE INDEX CONCURRENTLY` appropriately.
15. Monitor data consistency throughout the migration.
16. Build rollback and recovery plans for each phase.
17. Design idempotent migrations with observability.
18. Define completion criteria before contracting the old schema.

## 2. Why Can Schema Migrations Disrupt Applications?

Applications and databases often deploy on different cadences. The database is a shared component, whereas applications can have multiple replicas, worker processes, and service versions running concurrently.

For example, a table currently has a **full_name** column. The new application version wants to use two columns: **given_name** and **family_name**. If a migration immediately executes:

```sql
ALTER TABLE customers RENAME COLUMN full_name TO display_name;
```

Every process still querying **full_name** will error out. Even after a deployment pipeline starts rolling out the new version, a load balancer may still route traffic to old instances, an old background worker may not have restarted yet, or a cron job may fire hours later.

### 2.1. The Database Schema Is a Shared Contract

The schema is the interface between the database and:
- API services.
- Background workers.
- Scheduled jobs.
- ETL/ELT pipelines.
- Reporting and BI tools.
- CDC consumers.
- Admin scripts.
- Other services sharing the database.
- Humans running operational queries.

A migration compatible solely with the main API service can still break a worker or a rarely run report.

### 2.2. Rolling Deployments Create a Mixed-Version Window

During a rolling deployment, not all replicas switch versions at the exact same instant. During rollout, all of the following may coexist:
- Application v1 and v2.
- Worker v1 and v2.
- Migration already run while the new app is not fully rolled out.
- New app running while legacy consumers still exist.
- An older job whose schedule has not fired yet.

Therefore, migrations must account for transitional states, not just the final state.

### 2.3. DDL Can Hold Locks

Some DDL commands require strong table locks. If a lock must wait on a long transaction, the migration can queue; subsequent queries can then queue behind it. Even an ostensibly metadata-only command still needs a brief lock that can cause disruption if the lock queue backs up.

### 2.4. Structural Changes and Data Changes Are Separate Work

Adding a new column does not automatically copy data from an old column. Creating a new table does not automatically sync rows. Changing a data type may require lengthy data conversion and heavy I/O. Splitting a migration into schema changes and data backfills helps control each part.

## 3. The Expand-and-Contract Model

The model consists of three main phases:

```text
Current state
    |
    v
EXPAND
  Add new schema while old schema still works
    |
    v
MIGRATE
  Deploy compatible app, dual-write/backfill,
  validate data, switch readers
    |
    v
CONTRACT
  Stop old writes, prove old reads are gone,
  remove legacy schema
    |
    v
Target state
```

### 3.1. Expand

Expand the schema by adding new structures without breaking old ones:
- Add nullable columns.
- Add new tables.
- Add new indexes.
- Add constraints to be validated later.
- Add new enum values or new types when appropriate.
- Add compatibility views or triggers if needed.

The goal is for the new schema to coexist seamlessly with old application code.

### 3.2. Migrate

Deploy application logic and migrate data:
- Deploy code that understands both old and new schemas.
- Begin writing new data according to the chosen strategy.
- Backfill historical data in batches.
- Compare and validate data.
- Switch reads to the new structure.
- Monitor all consumers and manage lag.

### 3.3. Contract

Once no consumers depend on the old schema:
- Stop writing to old columns or tables.
- Confirm no reads still hit the old structure.
- Maintain an observation period covering workload and job schedules.
- Drop legacy columns, tables, indexes, or compatibility triggers.
- Clean up old code and configuration.

### 3.4. Do Not Merge All Three Phases Into One Deployment

If you add columns, backfill, switch reads, and drop old columns in a single migration transaction, the system loses staged rollout capability. Create separate migrations and application releases with clear completion states.

## 4. Backward Compatibility and Forward Compatibility

These two concepts determine deployment ordering.

- **Backward-compatible change:** the new application version still works with the old schema or supports the transition state.
- **Forward-compatible change:** the old application version continues working after the schema has been expanded in the new shape.

In rolling deployments, schema expansion must typically ensure the old app keeps working on the new schema. The new app must also be designed to run while historical data is not yet fully backfilled.

### 4.1. Compatibility Matrix

Example when adding **display_name** to replace **full_name**:

| Schema | App v1 | App v2 |
|---|---|---|
| S0: full_name only | Works | Must not be deployed |
| S1: both full_name and display_name | Works | Works if code falls back |
| S2: new data synchronized | Works | Works |
| S3: display_name only | Fails | Works |

During rollout, keep the system at S1/S2 until App v1 and all legacy consumers are gone. S3 is safe only once contraction is authorized.

### 4.2. Schema Compatibility Does Not Guarantee Semantic Compatibility

Two columns can coexist while carrying different meanings. If App v1 writes **full_name** and App v2 writes **display_name** using different normalization rules, data can diverge. Define mappings and the authoritative source of truth.

### 4.3. Every Writer Must Be Accounted For

A primary service may have deployed v2 while workers, triggers, import tools, or legacy scripts still write to the old schema. Never start contraction based solely on one service's deployment status.

## 5. End-to-End Example: Renaming a Column

Suppose we have the table:

```sql
CREATE TABLE customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

A new requirement wants to split the name into:
- **given_name**
- **family_name**

We cannot simply rename **full_name**, because old app code still reads and writes that column. We will retain the old column during the transition period.

### 5.1. High-Level Plan

1. Expand: add two new columns, initially nullable.
2. Deploy compatible app: read with fallback and write both old/new structures per chosen strategy.
3. Backfill: convert historical rows to the two new columns in batches.
4. Validate: verify converted rows and handle exceptions.
5. Switch reads: App v2 reads the two new columns.
6. Stop legacy writes: confirm all writers are updated.
7. Contract: drop **full_name** once dependencies are gone.
8. Enforce new constraints: apply NOT NULL or new constraints after data meets requirements.

### 5.2. Define Mapping Before Writing Code

Splitting **full_name** into two parts accurately is not always trivial. Decide:
- Rules for multi-part names.
- Single-word names.
- Prefixes and suffixes.
- Whitespace and Unicode handling.
- NULL/empty values.
- Names not fitting given/family structure.
- Whether the original value must be preserved for audit or display.

If mapping cannot be inferred reliably, route unclassified records to a review state or design a more appropriate field. Never apply an arbitrary split and assume the result is right.

## 6. Expand Phase: Adding New Structures

The first migration only adds the new columns:

```sql
ALTER TABLE customers
    ADD COLUMN given_name text,
    ADD COLUMN family_name text;
```

The new columns allow NULL so that:
- App v1 can continue inserting without knowing about them.
- App v2 can be deployed before backfilling finishes.
- Backfilling can run independently.
- No table rewrite is forced solely to compute values from the old column.

### 6.1. Adding Nullable Columns Is Usually Easiest to Roll Out

In PostgreSQL, ADD COLUMN without a default or with a constant default can be performed as a metadata change on modern versions; it still requires an appropriate lock on the table. Volatile defaults or per-row expressions can trigger a table rewrite. Check behavior for your exact major version and table size before running.

### 6.2. Do Not Add NOT NULL Before Data Exists

If the table already has rows, new columns cannot immediately satisfy NOT NULL when unpopulated. Adding the constraint too early can fail or require a scan/rewrite. Backfill and validate first, then enforce.

### 6.3. Use Explicit Column Lists

Applications using INSERT without listing column names break easily when a schema adds columns. Recommend that every insert query specify an explicit column list:

```sql
INSERT INTO customers (full_name)
VALUES ('Nguyen Van An');
```

Audit stored procedures, test fixtures, and scripts that depend on column ordering.

### 6.4. DDL Lock Timeouts

You can bound lock wait time so the migration fails fast instead of queueing long:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE customers
    ADD COLUMN given_name text;
COMMIT;
```

Tune the timeout for your environment. If the lock cannot be acquired, retry on a schedule with backoff after identifying the blocker. Never retry in a tight loop that increases contention.

## 7. Adding Indexes With Minimal Blocking

If the new app needs an index on a new column, build it concurrently:

```sql
CREATE INDEX CONCURRENTLY customers_given_name_idx
    ON customers (given_name);
```

### 7.1. CREATE INDEX CONCURRENTLY

This command allows INSERT/UPDATE/DELETE to continue for most of the build, though it performs multiple scans and can run longer than a standard CREATE INDEX.

It cannot run inside a transaction block. The migration framework must support non-transactional migrations or execute the statement separately.

### 7.2. Invalid Indexes After Failures

If CREATE INDEX CONCURRENTLY fails, an invalid index may remain. Check **pg_index.indisvalid** and **indisready**; handle invalid indexes per runbook before retrying. Never assume an index name existing means the index is usable.

### 7.3. Unique Indexes

If uniqueness is needed, build a unique index concurrently and then attach the constraint via ALTER TABLE ... ADD CONSTRAINT ... USING INDEX when appropriate. Confirm the index meets eligibility rules and constraint naming/semantics are right.

### 7.4. Indexes Are Not Always Free

Building an index consumes I/O, CPU, and temporary disk, and can raise replication lag. Monitor progress via **pg_stat_progress_create_index**, disk headroom, and workload latency.

## 8. Deploying Compatible Application Code

After schema expansion succeeds, deploy App v2 capable of operating during the transition period.

### 8.1. Read Fallback

While backfilling is incomplete, the new app can read the new columns when populated and fall back to the old column otherwise:

```sql
SELECT
    id,
    CASE
        WHEN given_name IS NOT NULL OR family_name IS NOT NULL
        THEN concat_ws(' ', given_name, family_name)
        ELSE full_name
    END AS display_name
FROM customers;
```

This is just an example where mapping can be expressed by concatenation. Real business rules may need a dedicated display field or application logic.

### 8.2. Deploy New App Before Switching Reads Completely

Initially, App v2 can keep reading **full_name** while only additionally writing the new columns. Once backfilling and validation pass, toggle a feature flag to read the new structure.

### 8.3. Mixed-Version Safety

During rollout, App v1 and App v2 may write concurrently. If v1 only updates **full_name**, the new columns must be kept synced or v2 must fall back. If v2 updates the new columns, the old column may also need updating so v1 still sees fresh data.

### 8.4. Do Not Assume Rollout Is Complete When the Deployment Controller Reports Success

Verify actual processes, worker pools, scheduled jobs, long-running sessions, and client versions. An old pod may still be running due to a termination grace period or an unfinished job.

## 9. Dual-Write: Writing Both Old and New Schemas

Dual-write means the application writes the same change to both old and new structures during the transition period.

For example:

```sql
UPDATE customers
SET
    full_name = $1,
    given_name = $2,
    family_name = $3
WHERE id = $4;
```

### 9.1. One Transaction for Both Representations

If both columns reside in the same database/table, writing both in the same transaction ensures they commit or roll back together. Never split into two independent requests without an explicit consistency mechanism.

### 9.2. Designate One Authoritative Source of Truth

In each phase, know which representation is authoritative:
- Before cutover: legacy field can be the source of truth.
- During backfill: legacy field is the source; new columns are a projection.
- After cutover: new columns are the source; legacy field remains only for old readers.
- Before contraction: stop updating legacy once no old readers/writers remain.

Never let both representations freely overwrite each other without a conflict policy.

### 9.3. Races Between Backfill and Writers

A backfill may read an old value while an incoming request updates the row. If the backfill writes results computed from the stale snapshot after the request commits, fresh data can be overwritten.

Mitigations:
- Use conditional updates, backfilling only when target columns are still NULL.
- Or use a trigger/dual-write synchronizing within the transaction.
- Or use version/timestamp checks to prevent overwriting newer updates.
- Run small batches and test concurrent updates.

Example filling only missing values:

```sql
UPDATE customers
SET
    given_name = $1,
    family_name = $2
WHERE id = $3
  AND given_name IS NULL
  AND family_name IS NULL;
```

Design predicates carefully so valid partial data is never overwritten.

### 9.4. Dual-Write Across Two Different Systems

If legacy and new schemas live in separate databases or services, a single PostgreSQL transaction cannot guarantee atomicity. You need a transactional outbox, CDC, idempotent consumers, or reconciliation. Two independent write calls can produce partial success.

### 9.5. Monitoring Write Divergence

Emit metrics for mismatched row counts, sync failures, retries, and dead-letter events. Do not rely solely on application logs.

## 10. Using Triggers to Maintain Compatibility

When multiple legacy writers cannot all be upgraded simultaneously, a trigger can synchronize legacy and new columns.

Illustrative trigger when **full_name** is the initial source of truth:

```sql
CREATE OR REPLACE FUNCTION sync_customer_name_columns()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- Replace parsing logic with agreed business rules.
        NEW.given_name := split_part(btrim(NEW.full_name), ' ', 1);
        NEW.family_name := CASE
            WHEN position(' ' IN btrim(NEW.full_name)) > 0 THEN
                nullif(btrim(substring(
                    btrim(NEW.full_name)
                    FROM position(' ' IN btrim(NEW.full_name)) + 1
                )), '')
            ELSE NULL
        END;
    ELSIF NEW.full_name IS DISTINCT FROM OLD.full_name THEN
        NEW.given_name := split_part(btrim(NEW.full_name), ' ', 1);
        NEW.family_name := CASE
            WHEN position(' ' IN btrim(NEW.full_name)) > 0 THEN
                nullif(btrim(substring(
                    btrim(NEW.full_name)
                    FROM position(' ' IN btrim(NEW.full_name)) + 1
                )), '')
            ELSE NULL
        END;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER customers_sync_name_columns
BEFORE INSERT OR UPDATE OF full_name
ON customers
FOR EACH ROW
EXECUTE FUNCTION sync_customer_name_columns();
```

This is a technical example, not a general-purpose person-name parser. Complex names require domain-defined mapping.

### 10.1. Triggers Protect Legacy Writers

Legacy writers only know **full_name**; the trigger updates the new representation in the same transaction. This helps when all producers cannot be released at once.

### 10.2. Triggers Can Conflict With New Writers

If App v2 writes **given_name/family_name**, a trigger watching only **full_name** will not automatically update the old column. If bidirectional sync is required, define explicit precedence and prevent infinite loops.

### 10.3. Triggers Do Not Replace a Rollout Plan

Triggers add complexity, latency, and debugging difficulty. Maintain metrics, test concurrency, and plan to drop the trigger once all writers have migrated.

### 10.4. Trigger Ordering and Replication

Check trigger firing order, **session_replication_role**, logical replication behavior, and bulk import tools. Never assume every write path executes with identical trigger semantics.

## 11. Batched Data Backfills

Backfilling populates new values for existing rows. On large tables, avoid running a single UPDATE across the entire table by default.

Example updating by primary key with a bounded batch:

```sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE given_name IS NULL
      AND full_name IS NOT NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET
    given_name = split_part(c.full_name, ' ', 1),
    family_name = nullif(
        substring(c.full_name FROM position(' ' IN c.full_name) + 1),
        ''
    )
FROM batch
WHERE c.id = batch.id;
```

This example only illustrates batching and locking. Replace name mapping with domain-approved logic.

### 11.1. Commit Between Batches

Each batch should be a short transaction, committed before proceeding. This:
- Reduces row lock hold durations.
- Reduces WAL spikes and long-transaction pressure.
- Gives vacuum opportunities to clean dead tuples.
- Limits sudden replication lag spikes.
- Enables pause and resume.

### 11.2. Size Batches Based on Load

Start small, measure runtime, WAL rate, lock waits, replica lag, disk usage, and application latency. Adjust batch size by metrics rather than picking one fixed constant for every table.

### 11.3. Use SKIP LOCKED Deliberately

FOR UPDATE SKIP LOCKED allows multiple workers to claim disjoint rows and skip rows locked by other transactions. Ensure the loop eventually processes skipped rows; never declare completion merely because one batch returned 0 rows.

### 11.4. Idempotent Backfills

Backfills must be safe to re-run without corrupting already-converted data. Use predicates like WHERE new_column IS NULL, migration status, or version markers. Avoid overwriting rows already updated by the new app.

### 11.5. Progress Tracking

Monitor:
- Rows scanned and updated.
- Rows remaining.
- Rows skipped and failed.
- Last processed key.
- Batch duration.
- WAL generated.
- Replica lag.
- Error count.
- Estimated completion time.

Do not log only "backfill started" and "finished."

### 11.6. Avoid OFFSET on Large Tables

OFFSET pagination grows more expensive as offsets increase and can miss or revisit rows while data changes. Use keyset pagination on the primary key or a locked work queue.

## 12. Data Verification and Reconciliation

After backfilling, prove the new representation accurately reflects the source data.

### 12.1. Coverage Check

```sql
SELECT
    count(*) AS total_rows,
    count(*) FILTER (
        WHERE given_name IS NOT NULL OR family_name IS NOT NULL
    ) AS rows_with_new_values,
    count(*) FILTER (
        WHERE given_name IS NULL AND family_name IS NULL
    ) AS rows_without_new_values
FROM customers;
```

This is a coverage check; it does not prove values are correct.

### 12.2. Mismatch Check

When the mapping normalizes into a deterministic expression:

```sql
SELECT count(*) AS mismatch_count
FROM customers
WHERE full_name IS DISTINCT FROM
      concat_ws(' ', given_name, family_name);
```

This example holds only if domain rules guarantee concat_ws reconstructs full_name exactly. For data with extra whitespace, prefixes, suffixes, or Unicode normalization, use an appropriate comparator.

### 12.3. Sampling Mismatches

```sql
SELECT
    id,
    full_name,
    given_name,
    family_name
FROM customers
WHERE /* predicate identifying mismatch per agreed mapping */
ORDER BY id
LIMIT 100;
```

Review edge cases specifically, not just ordinary random samples.

### 12.4. Periodic Reconciliation

During the dual-write phase, run periodic reconciliation to catch drift. Emit metrics and assign an owner per mismatch. Checksums or buckets over key ranges can help on large tables, provided checksums canonicalize values and do not replace validation logic.

### 12.5. Validation Should Not Lock the Entire Table for Long

Chunk checks by key ranges or appropriate snapshots. Large COUNT queries still generate I/O; measure load and schedule accordingly.

## 13. Switching Reads to the New Schema

Once backfill coverage is complete and mismatches are within acceptable limits, switch reads to the new representation.

### 13.1. Feature Flags

You can use a flag to control the read path:

```text
customer_name_read_source = legacy | new
```

Flags enable rolling out by traffic slice, tenant, or service instance and let you revert to the legacy read path while the old schema remains intact.

### 13.2. Canary

Shift a small percentage of traffic first and compare:
- Error rates.
- Response correctness.
- Query latency.
- Null/fallback rates.
- Mismatch metrics.
- Database load.

Ramp traffic up when the canary satisfies acceptance criteria.

### 13.3. Parallel Reads for Comparison

You can shadow-read both representations and compare results while returning only the legacy result during observation. Avoid multiplying heavy query load uncontrollably.

### 13.4. Do Not Let Fallbacks Mask Bugs Forever

Fallbacks are helpful during migration. If App v2 keeps falling back without alerting, missing backfill data can persist indefinitely. Track fallback rate and define criteria to disable fallbacks.

### 13.5. Switching Reads Still Does Not Allow Dropping Legacy

A service may have switched reads while an older writer still exists. Verify both read and write paths before contracting.

## 14. Stopping Legacy Writes

Once all writers support the new schema, shift the authoritative write source to the new structure.

Procedure:
1. Confirm all app and worker versions are upgraded.
2. Confirm cron jobs, ETL, admin tools, and external integrations.
3. Enable new-write mode per rollout plan.
4. Monitor old-column write activity.
5. Keep compatibility triggers/dual-write during an observation window if needed.
6. Stop legacy writes once no old writers remain.
7. Continue monitoring old-column reads.

### 14.1. Do Not Infer Zero Writers From Short Log Windows

A job may run daily, weekly, or only during incidents. Observation must span full operational cycles and operational runbooks.

### 14.2. Detecting Old-Column Access

Use query logs, pg_stat_statements, application instrumentation, database auditing, or controlled trigger instrumentation to detect usage. PostgreSQL has no default built-in counter tracking every read of a specific column.

### 14.3. Handling Consumers Outside the Application

BI, data warehouse extracts, CDC, replication, ad hoc notebooks, and stored procedures may still read the legacy field. Confirm with owners before dropping.

## 15. Contract Phase: Removing the Old Schema

Begin contraction only when:
- All deployed applications use the new schema.
- All workers and scheduled jobs are updated.
- Backfilling is complete and reconciled.
- Read fallbacks are no longer triggered.
- Legacy writes have stopped.
- Zero external consumers remain.
- The rollback window permits removing the legacy representation.
- Owners confirm the new data is authoritative.

Example dropping the old column:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE customers
    DROP COLUMN full_name;
COMMIT;
```

### 15.1. DROP COLUMN Requires a Lock

DROP COLUMN is usually a metadata change that does not immediately rewrite the entire table, yet it requires a strong lock on the relation. If the lock cannot be acquired quickly, the migration can wait. Use lock_timeout, check active transactions, and retry in an appropriate maintenance window.

### 15.2. Dropping Does Not Mean Disk Is Reclaimed Immediately

PostgreSQL can retain the physical space of a dropped column inside existing tuples until rows are rewritten or vacuumed by related operations. Do not expect DROP COLUMN to shrink filesystem size immediately.

### 15.3. Keep Code Cleanup Separate

After contraction, remove fallbacks, dual-writes, triggers, feature flags, and legacy SQL in dedicated releases as needed. Review code cleanup carefully so active compatibility paths are not removed prematurely.

### 15.4. Verify Zero Remaining References

Search repositories, migration histories, jobs, database objects, monitoring, dashboards, documentation, and runbooks. Check dynamic SQL and external integrations as well.

## 16. Safely Adding NOT NULL and CHECK Constraints

If the new column needs NOT NULL, you do not have to add the constraint upfront.

### 16.1. Add CHECK NOT VALID

For example:

```sql
ALTER TABLE customers
    ADD CONSTRAINT customers_given_name_present
    CHECK (given_name IS NOT NULL) NOT VALID;
```

The new constraint is enforced for rows inserted or updated after creation, while existing data is not yet validated across the whole table.

### 16.2. Validate Separately

```sql
ALTER TABLE customers
    VALIDATE CONSTRAINT customers_given_name_present;
```

Validation scans data using a weaker lock than blocking DDL operations; still measure I/O and lock impact.

### 16.3. Set NOT NULL

```sql
ALTER TABLE customers
    ALTER COLUMN given_name SET NOT NULL;
```

On PostgreSQL versions supporting the optimization, a valid CHECK constraint can skip re-scanning when setting NOT NULL. Check your exact major version's documentation and lock behavior before applying.

### 16.4. Foreign Keys

You can add a foreign key as NOT VALID and validate separately:

```sql
ALTER TABLE orders
    ADD CONSTRAINT orders_customer_id_fkey
    FOREIGN KEY (customer_id)
    REFERENCES customers(id)
    NOT VALID;

ALTER TABLE orders
    VALIDATE CONSTRAINT orders_customer_id_fkey;
```

Ensure an appropriate index exists on the referencing table if the workload needs it. PostgreSQL does not automatically create an index on foreign-key columns on the referencing side.

### 16.5. Constraint Validation Does Not Replace Data Migration

NOT VALID does not fix historical data. Backfill and clean data first, then validate. If validation fails, query violating rows and remediate per business rules.

## 17. Changing Data Types Using a Shadow Column

Changing a data type directly can require a table rewrite or long lock depending on types and conversions. For large tables, a shadow-column strategy is usually easier to control.

Example converting **amount_text text** to **amount numeric**:

### 17.1. Expand

```sql
ALTER TABLE invoices
    ADD COLUMN amount_numeric numeric;
```

### 17.2. Deploy Compatible Writer

The new app parses/validates the amount and writes both **amount_text** and **amount_numeric** in the same transaction. Reject or isolate unparseable input.

### 17.3. Backfill

```sql
UPDATE invoices
SET amount_numeric = amount_text::numeric
WHERE amount_numeric IS NULL
  AND amount_text IS NOT NULL;
```

On large tables, split into batches and handle failing conversions separately. Never run a full-table cast if unanalyzed data contains invalid formats.

### 17.4. Validate

Compare numeric values after normalization, checking rounding/scale, precision, overflow, and NULL semantics.

### 17.5. Switch Reads/Writes

Switch the app to read and write **amount_numeric**, keeping the old representation for the rollback window if needed.

### 17.6. Contract

Once all consumers have migrated, drop **amount_text** or rename columns according to the validated rollout strategy.

### 17.7. Conversion Semantics

Pay special attention to locale-specific decimal separators, thousands separators, currency symbols, rounding modes, numeric precision/scale, empty strings vs. NULL, negative values, scientific notation, and invalid legacy values.

## 18. Splitting or Merging Tables

Expand/contract also applies when changing relationships between tables.

Example moving address fields from **customers** into **customer_addresses**.

**Expand**
- Create the new table.
- Create appropriate primary keys and foreign keys.
- Create indexes.
- Add application code writing to the new table or a compatibility trigger.

**Migrate**
- Backfill addresses by customer ID.
- Handle duplicate or missing values.
- Synchronize writes during transition.
- Validate row counts and relationships.
- Switch reads to the new table.

**Contract**
- Stop reading and writing the old address columns.
- Confirm consumers have migrated.
- Drop the old columns.
- Retain the new table and constraints per final design.

### 18.1. Cardinality and Uniqueness

When extracting a column into a related table, decide whether one customer has one or many addresses. Unique constraints and application APIs must reflect the exact cardinality.

### 18.2. Transaction Boundaries

If writing customer and address must be atomic, perform both in the same transaction on the same database. Across separate services or databases, use an outbox, saga, or consistency protocol.

### 18.3. Delete Semantics

Define ON DELETE behavior, soft deletes, retention, and orphan handling before switching. A new foreign key can cause previously succeeding delete operations to fail.

## 19. Changing Enums, Lookup Tables, and Status Models

PostgreSQL enums can fit a stable set of values, yet changing allowed states requires careful rollout when multiple app versions run concurrently.

### 19.1. Adding an Enum Value

```sql
ALTER TYPE order_status
    ADD VALUE 'awaiting_review';
```

Transaction details depend on PostgreSQL version. On modern versions, an enum value can be added inside a transaction, but the new value cannot be used until the transaction containing ALTER TYPE commits. Check your target version's manual.

### 19.2. Old Apps May Not Understand the New Status

If App v1 parses enums with an exhaustive switch, a row holding a new status can break the app. Therefore:
- Deploy code able to recognize or safely ignore the new status first.
- Add the enum value once consumers are compatible.
- Create records using the new value only after sufficient rollout.
- Keep fallback/unknown handling for clients.

### 19.3. Removing or Renaming an Enum Value

PostgreSQL provides no simple operation to drop an enum value. It usually requires creating a new type, migrating columns, updating dependencies, and contracting. This is a multi-step migration.

### 19.4. Lookup Tables

If statuses require metadata, lifecycles, or frequent changes, a lookup table can be more flexible. However, it also requires foreign keys, seed data, cache invalidation, and application compatibility.

## 20. Changing JSON Schemas

A JSON/JSONB column can be shared by multiple application versions. Document structure changes also require expand/contract.

Example renaming key **phone** to **phone_number**:
1. Expand readers to understand both keys.
2. Deploy code reading phone_number if present, falling back to phone.
3. Deploy writers writing the new key, optionally keeping the old key during transition.
4. Backfill documents in batches.
5. Validate coverage and mismatches.
6. Stop writing the old key.
7. Confirm all consumers have migrated.
8. Contract by removing the old key from documents and code.

### 20.1. JSONB Updates Generate WAL

Backfilling JSONB can rewrite the entire row/TOAST representation, generating WAL and dead tuples. Monitor batch sizes, vacuum, and replication lag.

### 20.2. GIN Indexes

Changing JSON structure can affect index expressions and query predicates. You may need to create a new index concurrently, switch queries, and then drop the old index.

### 20.3. Schema Validation

Use application validation or database CHECK constraints/functions to enforce document shape. Define versioning for JSON documents when multiple producers or consumers exist.

## 21. Changing Views and Stored Procedures

Views and functions are also contracts with the application.

### 21.1. Creating a New View

Instead of modifying an existing view immediately, create **customer_summary_v2** or a compatibility view exposing the new output contract. Consumers migrate gradually before the old view is dropped.

### 21.2. CREATE OR REPLACE VIEW

CREATE OR REPLACE VIEW restricts changing the order, names, or types of existing columns. If the output contract must change, create a new view or use a transitional migration. Inspect dependencies.

### 21.3. Stored Procedures

Changing a function's signature or return type can break clients or dependent functions. Create an overload or versioned function, migrate callers, and drop the old signature once confirmed.

### 21.4. Dependencies

Use catalog dependency inspection and DROP ... RESTRICT to surface dependencies. Never use CASCADE in production migrations without listing every affected object beforehand.

## 22. Locking, Table Rewrites, and Operational Safety

Expand/contract narrows the blast radius of changes, but does not make every DDL automatically safe.

### 22.1. Understand Lock Modes

ALTER TABLE typically requires a strong lock; the exact mode depends on the subcommand. Even a metadata-only operation must acquire a relation lock. Long transactions can hold locks and block migrations.

### 22.2. Check Blockers Before Migration

```sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.xact_start,
    a.wait_event_type,
    a.wait_event,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.pid <> pg_backend_pid()
ORDER BY a.xact_start NULLS LAST;
```

Inspect pg_locks to identify relation locks and blocker chains. Appropriate privileges are required to view full session details per policy.

### 22.3. lock_timeout and statement_timeout

lock_timeout bounds lock wait time. statement_timeout bounds statement runtime. Use SET LOCAL inside migration transactions when appropriate; avoid global settings that impact all applications.

### 22.4. Long Transactions

Never hold a transaction open across a multi-hour backfill. Long transactions hold snapshots, block vacuum, and escalate storage pressure.

### 22.5. Table Rewrites

Changes to types, defaults, or column semantics can rewrite tables depending on version and expressions. Estimate disk space, I/O, WAL, replica lag, and downtime beforehand.

### 22.6. DDL Queues

A DDL waiting for AccessExclusiveLock can force incoming queries to queue behind it. If a migration cannot acquire the lock quickly, abort and retry cleanly rather than letting the queue grow.

## 23. Migration Frameworks and Ordering Management

Use a migration framework with version history and explicit deployment semantics.

### 23.1. Split Migrations by Phase

For example:
- V101__add_new_columns.sql
- V102__add_indexes_concurrently.sql
- Application release supporting dual-read/write.
- Backfill job.
- V103__add_not_null_check.sql
- Application release switching read path.
- V104__drop_legacy_columns.sql

Filenames are illustrative. Actual sequencing must follow the compatibility matrix and framework rules.

### 23.2. Transactional Migrations

Many DDLs can run inside a transaction. Commands such as CREATE INDEX CONCURRENTLY cannot run inside a transaction block. Configure the framework properly rather than auto-wrapping every migration in a transaction.

### 23.3. Idempotency

Versioned migrations normally run once, yet operational scripts and backfill jobs may retry. Design steps to inspect state before acting and avoid creating duplicate objects.

### 23.4. Never Edit Already-Applied Migrations

Keep migration history immutable. If logic needs changing, author a new migration. Editing a migration file after execution causes environments to drift.

### 23.5. Migration Ownership

Clarify who runs DDL, who deploys apps, who monitors backfills, and who authorizes contraction. Avoid having application startup automatically run destructive migrations when multiple replicas boot simultaneously.

## 24. Observability Throughout Migration

Every phase needs sufficient metrics and logs to decide whether to proceed or stop.

**Schema**
- Migration version and current state.
- Constraint validation state.
- Index validity and readiness.
- Column/table existence.

**Backfill**
- Rows remaining.
- Rows processed per second.
- Error and retry counts.
- Oldest/newest key processed.
- Mismatch count.
- Last successful batch.

**Application**
- App version distribution.
- Old vs. new read path usage.
- Fallback count.
- Legacy write count.
- Dual-write failure count.
- Request errors and latency.

**Database**
- Lock waits.
- Long-running transactions.
- CPU and I/O.
- WAL generation.
- Replication lag.
- Dead tuples and autovacuum progress.
- Disk headroom.

### 24.1. Feature Flag Metrics

Log flag state alongside app version, tenant, and traffic cohort. If a flag flips without observable code-path telemetry, you cannot verify the rollout truly shifted.

### 24.2. Migration-Specific Alerts

Alert when:
- Backfill stops progressing.
- Mismatches climb.
- Dual-write failures appear.
- Replica lag exceeds budget.
- Lock wait exceeds threshold.
- An index becomes invalid.
- Disk headroom drops low.
- Old-column usage persists past deadline.

### 24.3. Audit Trail

Record migration ID, deploy version, actor, timestamp, batch range, outcome, and approvals. Avoid logging personal data or secrets.

## 25. Rollback by Phase

Rollback differs across phases.

| Phase | Scenario | Remediation |
|---|---|---|
| Expand | Adding new column/index fails | Halt rollout; fix migration; drop new object only if zero dependencies are confirmed |
| Compatible app | App v2 errors while legacy remains | Roll back app to v1; keep expanded schema |
| Backfill | Batch fails or runs slow | Pause worker; preserve progress; fix and resume |
| Read switch | New reads error | Turn off flag, revert to legacy read if legacy stays synced |
| New source of truth | Legacy sync stopped | Restore dual-write/reconcile before reverting to old app |
| Contract | Old column already dropped | Cannot merely roll back app; must restore/recreate/repopulate or forward-fix |

### 25.1. Expand Is Usually Easiest to Roll Back

Unused new structures can be removed, but only after verifying no apps, triggers, indexes, or constraints depend on them. Keeping the expanded schema while investigating is often safer than rushing to drop it.

### 25.2. After Switching Writes, Rollback Gets Harder

If the new column is authoritative and old apps cannot read it, you must sync data back to the legacy representation before rolling back the app. Turning off a feature flag alone fails if legacy values are stale.

### 25.3. Contract Is the Application Point of No Return

Dropping an old column may not erase page-level bytes instantly, but the old application contract is gone. Rolling back requires restoring schema and data from a trusted source or deploying a forward fix.

### 25.4. Prefer Forward-Compatible Fixes

During a post-contract production incident, fixing the app to match the new schema is often faster and safer than restoring the old schema. The runbook should designate decision owners and recovery options.

## 26. Sample Rollout Schedule

Suppose an API service and worker run across multiple replicas.

| Time | Database | Application | Gate to proceed |
|---|---|---|---|
| T0 | Old schema S0 | App v1 | Baseline and backup ready |
| T1 | Expand S1: add new column | App v1 | App v1 still runs |
| T2 | S1 | App v2 reads fallback, dual-writes | All instances/workers compatible |
| T3 | S1 + backfill | App v2 | Backfill progresses, mismatches resolved |
| T4 | S1, new data complete | App v2 reads new column | Canary and regression pass |
| T5 | S1 | App v2 writes only new schema | Zero legacy writers remain |
| T6 | S1, legacy unused | App v2 | Observation window complete |
| T7 | Contract S2: drop old column | App v2 | Zero legacy readers remain |
| T8 | S2 | Cleaned-up App v2 | Monitoring stable |

### 26.1. Observation Window

Select an observation window covering:
- Longest scheduled job interval.
- Worker restart/rolling cycles.
- Batch import frequency.
- Reporting schedules.
- CDC lag.
- Maintenance and failover drills.

One day is insufficient if a job runs only once a week.

### 26.2. Do Not Leave Phases Hanging Indefinitely

An expanded schema can live for some time, but needs an owner, deadline, and metrics. Prolonged legacy columns and dual-writes increase complexity and risk drift.

## 27. Common Patterns

### 27.1. Additive Column

Add nullable column, deploy compatible app, backfill, switch reads, enforce constraints, and drop old fields once usage ceases.

### 27.2. Rename Column

Do not use ALTER TABLE ... RENAME COLUMN as the first step in a rolling deployment. Create the new column, synchronize, migrate consumers, and then drop the old column.

### 27.3. Change Data Type

Create a shadow column with the new type, write in parallel, backfill conversion, validate, switch, and contract. Avoid full-table casts without evaluating rewrite/lock impact.

### 27.4. Split Table

Create the new table, dual-write or trigger, backfill, validate FKs/uniqueness, switch reads, and drop old columns.

### 27.5. Merge Tables

Create the new representation, backfill from legacy tables, resolve conflicts/duplicates, switch consumers, and retire legacy tables.

### 27.6. Change Enum/Status

Expand consumers to understand the new value before producers emit it. Removing or renaming an old value generally requires type replacement or a lookup table.

### 27.7. JSON Key Migration

Readers understand both old and new keys, writers switch to the new key, backfill documents, measure fallbacks, and remove the old key.

## 28. Anti-Patterns to Avoid

- Renaming or dropping a column in the same release as code changing the name.
- Deploying the new app before the schema expansion exists.
- Dropping old schema while a worker or cron job remains un-upgraded.
- Running a full-table backfill inside one long transaction.
- Letting backfill overwrite rows recently updated by the application.
- Dual-writing without a designated source of truth.
- Having two systems write independently with no consistency mechanism.
- Keeping fallback reads with no metrics or expiration deadline.
- Using bidirectional triggers without conflict or loop-prevention rules.
- Using SELECT * and positional INSERTs.
- Building large indexes with blocking commands at peak traffic without assessment.
- Running CREATE INDEX CONCURRENTLY inside a transaction block.
- Setting NOT NULL before data is complete.
- Using DROP ... CASCADE just to force a migration through.
- Treating deployment success as proof zero old consumers remain.
- Dropping legacy schema immediately after canary success.
- Skipping rollback rehearsals after switching writes.
- Failing to store backfill progress and evidence.

## 29. Compatibility Testing

Tests must cover every schema/app combination possible during rollout.

| Schema | App version | Expected outcome |
|---|---|---|
| Old S0 | App v1 | Pass |
| Expanded S1 | App v1 | Pass |
| Expanded S1 | App v2 | Pass |
| Partially backfilled S1 | App v2 | Pass with designed fallback/guards |
| Migrated S1 | App v2 | Pass, new reads |
| Migrated S1 | Worker v1 | Pass while worker remains in window |
| Contracted S2 | App v2 | Pass |
| Contracted S2 | App v1 | Unsupported; must be proven decommissioned |

### 29.1. Test Rollout Order

Test the exact migration and deployment order, not just spinning up the final schema and running the new app.

### 29.2. Test Concurrent Writes

Run App v1, App v2, and the backfill worker concurrently. Issue updates, deletes, and inserts against the same keys to expose races.

### 29.3. Test Retries and Duplicate Execution

Simulate a worker crash after updating rows but before persisting the progress marker. Re-run and verify no duplicate or overwritten data.

### 29.4. Test Lag and Failures

Simulate slow replicas, lock contention, network drops, paused app rollouts, and migration retries. Verify operators can pause and resume safely.

### 29.5. Test Old Consumer Detection

Run sample scheduled workers/jobs to verify telemetry detects usage. Confirm the observation window covers real schedules.

## 30. Full Phased Migration SQL Example

The example below illustrates replacing **full_name** with **display_name** when the string value can be preserved as-is. Complex domain transformations require custom mapping.

### Phase A: Expand

```sql
ALTER TABLE customers
    ADD COLUMN display_name text;
```

### Phase B: Compatible Write

In the new application, write both columns in the same transaction:

```sql
UPDATE customers
SET
    full_name = $1,
    display_name = $1
WHERE id = $2;
```

During this phase, older apps still write only **full_name**. If old writers exist, use a trigger or another sync mechanism to populate **display_name**.

### Phase C: Backfill

Run repeated batches from a worker/job:

```sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE display_name IS NULL
      AND full_name IS NOT NULL
    ORDER BY id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET display_name = c.full_name
FROM batch
WHERE c.id = batch.id
  AND c.display_name IS NULL;
```

Commit after each batch. Measure rows updated, WAL, lag, and mismatches.

### Phase D: Validate

```sql
SELECT count(*) AS rows_missing_display_name
FROM customers
WHERE full_name IS NOT NULL
  AND display_name IS NULL;
```

Reconcile values:

```sql
SELECT count(*) AS mismatches
FROM customers
WHERE display_name IS DISTINCT FROM full_name;
```

This mismatch query only holds when business rules expect both strings to be identical.

### Phase E: Switch Reads

App v2 switches to reading **display_name**; canary first, then ramp traffic. Keep fallbacks and the old column throughout the observation window.

### Phase F: Stop Legacy Writes

Once all writers have upgraded, stop writing **full_name**. Monitor old-column references via instrumentation and logging.

### Phase G: Contract

Once zero legacy readers remain and the rollback window closes:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE customers
    DROP COLUMN full_name;
COMMIT;
```

Remove triggers, dual-write code, and fallbacks in appropriate releases. This migration cannot be rolled back simply by reverting the app; have a data recovery plan if needed.

## 31. Pre-Start Checklist

- [ ] Define current schema and target schema.
- [ ] Inventory all application versions and consumers.
- [ ] Identify readers, writers, workers, jobs, ETL, BI, and CDC.
- [ ] Designate the source of truth for every phase.
- [ ] Define mappings and exception-data handling.
- [ ] Check DDL lock/rewrite behavior on the exact PostgreSQL version.
- [ ] Estimate disk, WAL, I/O, and replication impact.
- [ ] Choose batch size and pause/resume strategy.
- [ ] Define index and constraint rollout.
- [ ] Build the compatibility matrix.
- [ ] Design feature flags and observability.
- [ ] Define rollback boundaries.
- [ ] Rehearse on staging with representative data.
- [ ] Assign an owner and contract approver.

## 32. Expand Checklist

- [ ] New schema only adds required structures.
- [ ] Old schema remains intact and functional.
- [ ] New columns allow NULL if backfilling is needed.
- [ ] Defaults do not trigger unexpected rewrites.
- [ ] DDL sets an appropriate lock_timeout.
- [ ] Large indexes are built with the appropriate method.
- [ ] Constraints can be validated in stages.
- [ ] App v1 still passes on the new schema.
- [ ] Migration history is recorded.
- [ ] Metrics and alerts are active.

## 33. Migrate Checklist

- [ ] New app handles both old and new data states.
- [ ] Writers synchronize representations per a single source of truth.
- [ ] Triggers/dual-writes have explicit conflict rules if used.
- [ ] Backfills are batched and retryable.
- [ ] Batch commits are short with pause/resume support.
- [ ] Backfills do not overwrite concurrent updates.
- [ ] Remaining rows and mismatches are monitored.
- [ ] Replication lag and disk headroom stay within budget.
- [ ] Canary read switch succeeds.
- [ ] Fallback rate trends to zero.
- [ ] Zero old writers remain after cutover.

## 34. Contract Checklist

- [ ] All app instances use the new schema.
- [ ] All workers and scheduled jobs use the new schema.
- [ ] BI/ETL/CDC/external consumers verified.
- [ ] Zero legacy reads during observation window.
- [ ] Zero legacy writes.
- [ ] Backfill and reconciliation complete.
- [ ] New constraints and indexes validated.
- [ ] Rollback window closure and approvals confirmed.
- [ ] DDL lock impact assessed.
- [ ] Legacy objects dropped via audited migration.
- [ ] Triggers, feature flags, and compatibility code removed.
- [ ] Monitoring detects zero old schema usage.

## 35. Incident Runbook During Migration

### 35.1. DDL Cannot Acquire Lock

1. Inspect **pg_stat_activity** and **pg_locks**.
2. Identify the lock-holding transaction.
3. Check whether the DDL is queueing and blocking new queries.
4. Cancel the migration if it exceeds lock_timeout or maintenance budget.
5. Handle the blocking transaction per incident policy.
6. Retry in a low-traffic window with a short lock_timeout.

### 35.2. Backfill Runs Slowly or Causes Lag

1. Pause the worker.
2. Check WAL generation, replica lag, I/O, and vacuum.
3. Reduce batch size or concurrency.
4. Identify indexes or triggers increasing write amplification.
5. Resume from the progress marker / idempotent predicate.
6. Monitor mismatches and remaining rows.

### 35.3. Dual-Write Divergence

1. Pause rollout or new-write flag.
2. Identify the authoritative representation.
3. Find the root cause: old writer, trigger, race, retry, or partial commit.
4. Choose reconciliation direction.
5. Fix logic and test concurrent updates.
6. Reconcile data in batches.
7. Re-enable rollout only after mismatches return within acceptable bounds.

### 35.4. New App Fails to Read the New Schema

1. Disable the read flag / canary.
2. Fall back to legacy reads while legacy remains synced.
3. Keep the expanded schema.
4. Capture SQLSTATE and failing queries.
5. Fix the app or migration in a forward-compatible way.
6. Re-run regression tests before switching back.

### 35.5. App Errors After Contraction

1. Halt rollout and assess traffic impact.
2. Locate where the old dependency remains.
3. Choose a forward fix or schema restoration.
4. If recreating a column, identify a trusted data source to repopulate it.
5. Never create an empty column and treat rollback as complete.
6. Validate data and consumer behavior before reopening traffic.

## 36. Best Practices

- Split destructive changes into additive expansion and separate contraction.
- Design App v2 to read the schema in transitional states.
- Maintain one authoritative source of truth in every phase.
- Keep backfills out of long migration transactions.
- Use batches, keyset pagination, and idempotent predicates.
- Monitor old reads/writes, fallbacks, and data divergence.
- Use CREATE INDEX CONCURRENTLY when appropriate and handle invalid indexes.
- Use NOT VALID/VALIDATE CONSTRAINT for supported constraints.
- Set lock_timeout and control DDL queues.
- Test mixed-version and concurrent writes on staging.
- Treat workers, cron jobs, BI, ETL, and CDC as application consumers.
- Contract only with evidence that zero old dependencies remain.
- Keep a clear rollback path before switching the source of truth.
- Clean up triggers, feature flags, and legacy code once the schema transition completes.
- Record migration IDs, owners, progress, metrics, and evidence.

## 37. Common Misconceptions

### 37.1. "Adding a column is always safe"

Not always. Apps may use SELECT *, positional inserts, ORM schema assumptions, or row serialization tied to column count. DDL still requires a lock.

### 37.2. "Renaming a column is a metadata operation so it has no impact"

The DDL itself may be fast, but every running query using the old column name will error the instant the rename commits.

### 37.3. "Finishing the backfill means the old column can be dropped"

You must still verify readers/writers, scheduled jobs, external consumers, fallback usage, and the rollback window.

### 37.4. "Dual-write always guarantees identical data"

Only with clear transaction/consistency mechanisms, an authoritative source of truth, and conflict policies. Two independent writes can partially succeed.

### 37.5. "Triggers handle every writer"

Triggers may behave differently during bulk loads, replication, or special session settings; bidirectional logic can create loops and conflicts.

### 37.6. "CREATE INDEX CONCURRENTLY does not affect workload"

It reduces blocking but still consumes I/O/CPU, performs multiple scans, and can leave invalid indexes on failure.

### 37.7. "Dropping a column frees disk immediately"

Not necessarily. Physical space may only be reclaimed through subsequent rewrites, vacuuming, or other operations.

### 37.8. "Rollback just means redeploying the old app"

If the new app has written data only to the new representation or the old schema was dropped, the old app may miss new data. You need reverse sync/reconciliation or a forward fix.

## 38. Official Reference Documentation

- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): adding/dropping columns, constraint validation, and table alterations.
- [PostgreSQL — CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index builds, CONCURRENTLY, and transaction caveats.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): table locks and lock modes.
- [PostgreSQL — System Catalogs](https://www.postgresql.org/docs/current/catalogs.html): catalog metadata and dependencies.
- [PostgreSQL — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): session, progress, and database statistics.
- [PostgreSQL — Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html): tracking progress of long-running operations.
- [PostgreSQL — CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): trigger behavior.
- [PostgreSQL — ALTER TYPE](https://www.postgresql.org/docs/current/sql-altertype.html): modifying enums and data types.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, NOT NULL, UNIQUE, and foreign keys.
- [PostgreSQL — Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshots and concurrent transaction behavior.

Details regarding locks, table rewrites, enum transaction semantics, and DDL optimizations can vary across major versions. Check the documentation for your exact production/target version and rehearse on staging with representative data before running major migrations.

## 39. Summary

Expand and contract enables schema changes while multiple application versions run concurrently. Instead of changing structures and deploying code in one shot, you add the new schema, deploy compatible code, migrate data, shift traffic, and remove legacy structures only once all dependencies are gone.

1. **Expand:** add new columns/tables/indexes/constraints so the old schema keeps working.
2. **Migrate:** deploy compatible apps, dual-write or trigger when needed, backfill in batches, and validate data.
3. **Switch:** shift reads and writes via rollout/canary while tracking fallbacks, mismatches, and old consumers.
4. **Contract:** stop legacy writes, verify zero legacy reads remain, and only then drop old structures.
5. **Operate safely:** bound locks, WAL, I/O, and transaction durations; monitor progress and preserve pause/resume.
6. **Recover:** establish rollback boundaries before switching the source of truth; after contraction, a forward fix or data restore may be required.

A schema migration is truly complete only when applications, workers, jobs, and related consumers all use the new contract, data is verified, and legacy structures can be safely removed.

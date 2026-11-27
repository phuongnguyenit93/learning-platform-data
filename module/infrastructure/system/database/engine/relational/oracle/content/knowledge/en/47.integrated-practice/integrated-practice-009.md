# Deploying Multi-Version Compatible Schema Changes

In an Oracle Database system, applications and schemas are often released at different times. During rolling deployments, blue-green deployments, or multi-replica scaling, old and new application versions can run concurrently against the same database. A schema change is safe only if every application version running during the deployment window understands the database structure at that moment.

For example, application R10 currently reads `CUSTOMER_PHONE`. Release R11 wants to transition to `CUSTOMER_PHONE_E164` to store normalized phone numbers. If a migration renames or drops the old column before every R10 instance stops, old instances fail immediately when running SQL referencing the missing column. Conversely, if the new app deploys before the new column exists, the new app fails as well. Changes must be split into steps so schema and code remain mutually compatible throughout the transition.

The standard strategy is **expand → migrate → contract**:

1. **Expand**: add new structures in a backward-compatible way; the old app keeps running.
2. **Migrate**: deploy code that works with both old and new structures, backfill data, gradually shift traffic, and verify.
3. **Contract**: remove old structures only after all consumers have migrated and the rollback window has closed.

In Oracle, this discipline is especially important because most DDL issues implicit commits. You cannot wrap a series of `ALTER TABLE`/`CREATE INDEX` statements in `@Transactional` and expect full schema rollback on failure. Application rollback, schema rollback, and database recovery are three distinct operations requiring separate plans.

## 1. Why Multi-Version Compatibility Matters

A production system rarely shuts down completely to replace both binaries and schema at once. Common deployment patterns create overlap windows where multiple versions coexist.

### 1.1. Rolling Deployment

When deploying across multiple replicas:
- Some instances still run version N.
- New instances roll out one by one to version N+1.
- The load balancer shifts traffic gradually.
- For a window of time, N and N+1 share the same schema.

If the schema is compatible only with N+1, remaining N instances will fail.

### 1.2. Blue-Green Deployment

The blue environment runs the current version while green runs the new version. Both environments may share one database during verification or traffic cutover. In that setup, the schema must remain compatible with both app versions unless separate databases and full data synchronization exist.

Merely switching traffic to green does not solve the problem if green has written data in a format blue cannot read. Rolling traffic back could then crash the old app or misinterpret data.

### 1.3. Multiple Consumers Sharing a Database

A schema may be accessed by:
- API services.
- Batch jobs.
- Reporting services.
- ETL pipelines.
- Stored procedures/packages.
- Scheduler jobs.
- Other consumers reading tables or views directly.

Do not inspect only the primary web/API version. A nightly job might still read the old column long after the new app deployed successfully.

### 1.4. Compatibility Window

The compatibility window is the period during which the schema must support multiple consumer versions. Before starting, determine:
- The oldest app version still permitted to run.
- The newest app version being deployed.
- Which jobs or consumers run on delayed schedules.
- The length of the rollback window.
- When old structures are eligible for removal.
- Who verifies that no consumers still touch old structures.

Never execute contract simply because the deployment pipeline reports all new pods are healthy. Workers, scheduled jobs, or external cluster consumers may still exist.

## 2. Design Principles

### 2.1. Additive Changes First

Changes that are generally backward-compatible:
- Adding a nullable column.
- Adding a new table.
- Adding an index that does not alter semantics.
- Adding a new view or API.
- Adding status values that old apps can safely ignore.
- Adding constraints after data is normalized.

High-risk changes:
- `DROP` or `RENAME` of a column or table.
- Changing data types in ways that lose data.
- Adding `NOT NULL` when old apps do not supply a value.
- Changing the meaning of a column used by multiple consumers.
- Changing enums/statuses in ways that send old code down wrong branches.
- Removing values or formats old apps still expect to read.

Additive does not automatically mean safe. Adding a `NOT NULL` column without an appropriate default breaks old app `INSERT`s. Adding constraints can cause old DML to fail.

### 2.2. Keep Data Contracts Stable During Transition

During the compatibility window:
- The old column remains present.
- The new column can be added.
- New code must handle un-backfilled legacy rows.
- Old code must continue reading and writing per the old contract.
- New consumers must not assume backfill has finished without proof.
- Every transformation must clearly designate the authoritative data source.

### 2.3. Separate Schema Migrations from Data Migrations

Schema migrations alter structure: columns, tables, indexes, constraints, views, packages.

Data migrations alter content: backfills, normalization, copies, value splits/merges, format conversions.

The two carry different risk profiles and runtimes. Adding a column is typically fast; backfilling hundreds of millions of rows can take hours. Never bundle both into one monolithic migration when independent observability, retries, or rollbacks are needed.

### 2.4. Migrations Must Be Safely Resumable

Long-running migrations should include:
- Batch/chunk boundaries.
- Checkpoints or progress markers.
- Idempotent predicates.
- Expected versus processed row counts.
- Retry mechanisms.
- Error-row handling.
- Time and resource budgets.
- Verifiable terminal state.

Never assume a migration runs once uninterrupted. Processes can stop mid-way due to deploy timeouts, session disconnects, database restarts, or bad data.

### 2.5. Do Not Delete Old Data Too Early

Retain legacy data while the new app is validated. An old column may be needed for:
- Binary rollback.
- Un-upgraded consumers.
- Un-migrated reports/ETL.
- Data reconciliation.
- Recovering from migration bugs.

Schedule the contract phase based on usage telemetry and retention policy—not a gut feeling that the release looks stable.

## 3. App and Schema Compatibility Matrix

Before deploying, document explicitly which app versions work against which schema versions.

Example:

| Schema | App R10 | App R11 | App R12 |
| --- | --- | --- | --- |
| S20: `phone` only | Yes | No | No |
| S21: add `phone_e164`, keep `phone` | Yes | Yes | Yes |
| S22: both columns maintained | Yes | Yes | Yes |
| S23: drop legacy `phone` | No | No if still reading `phone` | Yes |

The matrix shows:
- S21 is the expand schema.
- R11/R12 can deploy onto S21.
- S22 is the migrate/backfill stage.
- Only R12 is fully built for S23.
- Contracting to S23 is safe only after R10/R11 and all legacy consumers stop using `phone`.

### 3.1. Backward vs. Forward Compatibility

- **Backward compatibility**: new app works against older schemas within the committed range.
- **Forward compatibility**: old app keeps working against newer schemas.
- **N/N-1 compatibility**: a new release supports schemas of the current and prior release, or supports the prior app version during rolling upgrades.

Not every system needs every combination, but supported combinations must be stated explicitly rather than guessed.

### 3.2. Consumer Inventory

Catalog every consumer:
- App/service and version.
- Database user/schema.
- Tables/views/packages accessed.
- Legacy columns read or written.
- Execution schedule/frequency.
- Owner.
- Usage verification method.

Use SQL auditing, application metrics, SQL monitoring, source searches, and logs to discover consumers. Never rely solely on source code searches, as dynamic SQL, external jobs, or BI tools may exist outside the main repository.

## 4. Expand: Safely Adding New Structures

The expand phase builds the foundation for the new app while the old app continues running.

### 4.1. Adding a Nullable Column

Example:

~~~sql
ALTER TABLE customers
ADD (phone_e164 VARCHAR2(20));
~~~

The new column is nullable so old apps can keep issuing `INSERT`s without providing it. Verify storage, datatype, length, character semantics, and naming conventions.

Do not add `NOT NULL` immediately if old apps are unaware of the new column. Consider adding the constraint later once backfill finishes and new writers populate it consistently.

### 4.2. Adding a New Table

For major data model shifts, adding a new table can be safer than mutating existing tables right away.

Example extracting customer addresses:

~~~sql
CREATE TABLE customer_addresses (
    address_id   NUMBER GENERATED BY DEFAULT AS IDENTITY,
    customer_id  NUMBER NOT NULL,
    address_type VARCHAR2(30),
    line_1       VARCHAR2(200),
    city         VARCHAR2(100),
    country_code VARCHAR2(2),
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT customer_addresses_pk PRIMARY KEY (address_id),
    CONSTRAINT customer_addresses_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

If old apps only touch address columns on `CUSTOMERS`, the new table can coexist without impacting old apps. New apps need a clear read/write and backfill strategy.

### 4.3. Adding Indexes

Indexes can be created before the new app runs new queries. For large tables, evaluate `ONLINE` options, Oracle edition/release, edition licensing, DML concurrency, and lock duration. `ONLINE` does not mean zero locking or zero resource impact.

Example:

~~~sql
CREATE INDEX customers_phone_e164_ix
ON customers(phone_e164);
~~~

On large tables, verify online index creation syntax and support for your Oracle release/edition. Measure I/O, redo, undo, `TEMP`, and DML impact.

### 4.4. Adding Constraints in Stages

If historical data does not yet satisfy a constraint, add it in stages matching data state and Oracle version. For instance, some constraints support `NOVALIDATE` to enforce rules on new DML without validating every existing row upfront:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT customers_phone_e164_ck
CHECK (phone_e164 IS NULL OR LENGTH(phone_e164) BETWEEN 8 AND 20)
ENABLE NOVALIDATE;
~~~

`ENABLE NOVALIDATE` does not mean existing rows are valid. It enforces the constraint on new DML per Oracle semantics without scanning existing rows. After cleanup/backfill, validate:

~~~sql
ALTER TABLE customers
ENABLE VALIDATE CONSTRAINT customers_phone_e164_ck;
~~~

Verify constraint status in `USER_CONSTRAINTS`/`ALL_CONSTRAINTS`. Check exact semantics and limitations of each constraint type before using.

### 4.5. Defaults and Old Apps

Distinguish between:
- `DEFAULT` for `INSERT` statements omitting the column.
- `DEFAULT ON NULL` in supporting Oracle releases.
- Apps explicitly sending `NULL`.
- `NOT NULL` constraints.

A default does not automatically ensure old apps behave correctly. If an old app explicitly binds `NULL`, behavior differs from omitting the column in an `INSERT`. Test the exact SQL emitted by the old app.

## 5. Migrate: Deploying Dual-Compatible Code

After expand, deploy the new app version aware of the transitional state.

### 5.1. Dual-Read

The new app reads the new column if populated, otherwise falling back to the old column:

~~~sql
SELECT COALESCE(phone_e164, phone_legacy) AS phone_value
FROM customers
WHERE customer_id = :customer_id;
~~~

This example illustrates fallback only. If the two columns use different formats, never treat raw old and new values as equivalent without normalization. The app may need to parse/normalize per contract and emit metrics for unmigrated rows.

### 5.2. Dual-Write

During transition, the new app writes both old and new columns:

~~~sql
UPDATE customers
SET phone = :legacy_phone,
    phone_e164 = :normalized_phone
WHERE customer_id = :customer_id;
~~~

The goal is keeping both old apps (reading `phone`) and new apps (reading `phone_e164`) consistent.

Dual-write requires explicit rules:
- Which canonical value is the source of truth?
- If the two values diverge, which one wins?
- Does normalization happen in the application or database?
- Can old app instances overwrite `phone` after a new app wrote `phone_e164`?
- Do any other consumers update only one of the two columns?

If old apps keep writing only the old column while new apps write both, the columns can drift. Use triggers, CDC, compatibility services, or catch-up sync jobs to cover all writers.

### 5.3. Avoiding Uncontrolled Dual-Writes

Dual-writing across two separate systems or databases risks partial success. Within a single Oracle transaction, updating two columns in the same database is atomic; if one write goes to another service or message broker, atomicity is not automatic.

If using triggers to sync columns:
- Decide whether the trigger is temporary or permanent.
- Prevent trigger recursion/loops.
- Check bulk loads and replication interactions.
- Benchmark trigger overhead and error behavior.
- Plan trigger removal after contract.
- Ensure the app does not write conflicting values into both columns.

Triggers protect legacy writers, though they hide write logic and complicate debugging. Keep them time-bound and well documented.

### 5.4. Feature Flags

Feature flags let you shift behavior gradually by percentage or cohort:
- Read old column only.
- Read new column only.
- Dual-read.
- Dual-write.
- Write new column only after legacy consumers stop.

Manage flags centrally with safe defaults. Never allow two instances of the same version to run conflicting flag states without understanding the data impact.

## 6. Safe Data Backfills

Backfills convert historical data to the new structure. This is often the longest and highest-risk phase in production.

### 6.1. Batched Backfills

Example updating `phone_e164` from `phone_legacy` using a defined normalization function:

~~~sql
UPDATE customers
SET phone_e164 = normalize_phone(phone)
WHERE phone_e164 IS NULL
  AND customer_id BETWEEN :low_id AND :high_id;
~~~

This assumes an appropriate `normalize_phone` function exists. It must handle nulls, country codes, punctuation, extensions, and malformed inputs per contract. Never write a naive regex and assume every phone string is valid.

Split by key range or partition to:
- Bound undo/redo per transaction.
- Shorten lock durations.
- Enable checkpoints.
- Retry individual chunks.
- Track progress.
- Avoid gigantic single transactions.

### 6.2. Idempotency

Backfills should be safe to rerun without overwriting values already updated by the new app:

~~~sql
UPDATE customers
SET phone_e164 = normalize_phone(phone)
WHERE phone_e164 IS NULL
  AND customer_id BETWEEN :low_id AND :high_id;
~~~

The `phone_e164 IS NULL` guard prevents overwriting populated values, though you still must account for races with concurrent app writers. Use appropriate transaction isolation and predicates, and inspect actual updated row counts.

Idempotency does not just mean rerunning without errors—it means reruns never corrupt data or overwrite newer writes.

### 6.3. Backfill Contention with App Writes

During backfill:
- Old apps may update `phone`.
- New apps may update both `phone` and `phone_e164`.
- The batch might read an old value and write after an app wrote a newer value.

To prevent lost updates:
- Only update rows still needing migration.
- Use an optimistic version column if applicable.
- Include a predicate checking the source value has not changed.
- Enforce controlled chunk/row ownership.
- Pause writers briefly or run a final catch-up pass.
- Reconcile source and target before marking complete.

Example checking unchanged source value:

~~~sql
UPDATE customers
SET phone_e164 = :normalized_value
WHERE customer_id = :customer_id
  AND phone = :source_value
  AND phone_e164 IS NULL;
~~~

If rowcount is 0, the row changed or was already migrated; re-read and decide per business logic. Do not treat zero affected rows automatically as an error.

### 6.4. Checkpoints and Progress Tracking

You can persist batch progress:

~~~sql
CREATE TABLE migration_progress (
    migration_name VARCHAR2(100) PRIMARY KEY,
    last_customer_id NUMBER,
    rows_processed NUMBER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    status VARCHAR2(20)
);
~~~

Commit the checkpoint in the same transaction as the batch data if progress must never get ahead of data. If a checkpoint commits before data and the process crashes, rows get skipped. If data commits before the checkpoint, retries may reprocess rows—requiring idempotent updates.

### 6.5. Resource Budgets

Monitor:
- Undo tablespace usage.
- Redo generation and archive log volume.
- `TEMP` usage.
- CPU and I/O.
- Row lock waits.
- Buffer busy waits / contention.
- Replication / Data Guard lag.
- Application query latency.
- Batch throughput (rows/sec) and duration.

Tune batch size and worker concurrency from measurements. Adding workers can reduce throughput if contention spikes.

### 6.6. Unconvertible Data

Never silently skip bad rows or invent dummy defaults. Classify failures:
- Missing source data.
- Invalid format.
- Insufficient context to normalize.
- Out-of-domain values.
- Duplicates or conflicts.
- Character encoding corruption.

Store row keys, raw values, error codes, and remediation notes in a quarantine table or migration error log. Define who fixes them and how fixed rows are reprocessed.

## 7. Cutting Over Reads and Writes to the New Structure

Once backfill nears completion, switch consumers according to plan.

### 7.1. Read Cutover

Before switching the app to read only the new column:
- Backfill meets completion criteria.
- No valid rows lack target values, unless `NULL` is semantically valid.
- Quarantined rows are resolved.
- New read paths are tested.
- Query plans and indexes are ready.
- Metrics compare old and new values.

You can run dual-read verification temporarily to catch discrepancies:

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM customers
WHERE phone_e164 IS NOT NULL
  AND normalize_phone(phone) <> phone_e164;
~~~

This query is illustrative; handle `NULL`s and function semantics properly. Never run expensive full-table normalization checks repeatedly in production without measuring their cost.

### 7.2. Write Cutover

Once all writers are upgraded:
- New app writes the new column.
- The old column may still be maintained during the rollback window if required.
- Legacy writers must be retired or covered by a compatibility layer.
- Monitor for any writes touching only the old column.
- Confirm batch/ETL pipelines no longer write the old format.

Never stop dual-writing until every consumer depending on the old column has migrated.

### 7.3. Freezing Cutover State

Record:
- Release ID.
- Schema version.
- Start and end timestamps.
- Feature flag states.
- Backfill checkpoint.
- Mismatch count.
- Migrated consumer list.
- Error rate and latency.
- Approver.

This snapshot lets you reconstruct exact state if a rollback or post-release investigation is needed.

## 8. Contract: Removing Legacy Structures

Contract is the breaking step. Execute it only after legacy apps/consumers are gone and the rollback window has closed.

### 8.1. Preconditions Before DROP

- Zero running code reads or writes the old column.
- Batch jobs and reports have migrated.
- No dynamic SQL or database packages reference the old column.
- No external consumers remain.
- Backfill and reconciliation meet acceptance criteria.
- The new app version is stable.
- Binary rollback to versions depending on the old column is no longer needed.
- Backup and recovery plans are verified.
- Change approval and maintenance plan are signed off.

### 8.2. Dropping the Column

~~~sql
ALTER TABLE customers
DROP COLUMN phone;
~~~

This is an impactful DDL statement that cannot be rolled back like DML. Depending on table size, dependencies, edition, and Oracle release, it can take significant time/locks and affect storage. Test it first on a clone or staging environment.

In some scenarios, consider `SET UNUSED` followed later by `DROP UNUSED COLUMNS` to separate logical removal from physical space reclamation:

~~~sql
ALTER TABLE customers
SET UNUSED (phone);

ALTER TABLE customers
DROP UNUSED COLUMNS;
~~~

`SET UNUSED` makes the column immediately inaccessible by name and breaks old code at once. It is *not* a reversible rollback safeguard. Use it only after all contract preconditions are satisfied.

### 8.3. Is Renaming a Column Safe?

~~~sql
ALTER TABLE customers
RENAME COLUMN phone TO phone_legacy;
~~~

Renaming immediately breaks old code referencing the old name. During rolling deployments, use add-new-column → migrate → switch consumers → drop-old-column rather than renaming in place.

### 8.4. Dropping Constraints and Indexes

Before dropping:
- Identify dependent queries, foreign keys, packages, and reports.
- Check whether the index backs a constraint.
- Verify execution plans after removal.
- Confirm apps no longer rely on the old semantics.
- Save the pre-change DDL and state.

## 9. Complete Example: Migrating phone to phone_e164

Suppose `CUSTOMERS` currently has `PHONE VARCHAR2(40)`. The new release requires `PHONE_E164 VARCHAR2(20)`.

### 9.1. Initial State S100 / R10

~~~sql
CREATE TABLE customers (
    customer_id NUMBER PRIMARY KEY,
    phone       VARCHAR2(40)
);
~~~

App R10:
- `INSERT`/`UPDATE` `PHONE`.
- `SELECT` `PHONE`.
- Unaware of `PHONE_E164`.

### 9.2. Expand Schema S101

~~~sql
ALTER TABLE customers
ADD (phone_e164 VARCHAR2(20));
~~~

R10 continues working because the new column is nullable and does not break the legacy contract.

### 9.3. Deploy R11 Dual-Read / Dual-Write

R11:
- Reads `PHONE_E164` when present.
- Falls back to `PHONE` and normalizes if `PHONE_E164` is absent.
- Writes both `PHONE` and `PHONE_E164` in the same transaction.
- Emits a metric whenever fallback is used.

If R10 is still running and writing only `PHONE`, R11 or a compatibility mechanism must ensure `PHONE_E164` catches up after those writes. A temporary trigger or catch-up process can bridge this, provided one source of truth is defined.

### 9.4. Backfill

~~~sql
UPDATE customers
SET phone_e164 = normalize_phone(phone)
WHERE phone_e164 IS NULL
  AND customer_id BETWEEN :low_id AND :high_id;
~~~

Commit in chunks. Record checkpoints and quarantine rows failing normalization. Run a catch-up pass after R10 stops to pick up rows modified during backfill.

### 9.5. Reconcile

~~~sql
SELECT COUNT(*) AS missing_count
FROM customers
WHERE phone IS NOT NULL
  AND phone_e164 IS NULL;
~~~

~~~sql
SELECT COUNT(*) AS mismatch_count
FROM customers
WHERE phone_e164 IS NOT NULL
  AND normalize_phone(phone) <> phone_e164;
~~~

Adjust these queries for `NULL`s, invalid inputs, and normalization semantics. Mark complete only after every row is classified and any remaining discrepancies fall within approved exceptions.

### 9.6. Deploy R12 Reading/Writing Only the New Column

R12:
- Reads `PHONE_E164`.
- Writes `PHONE_E164`.
- May still dual-write `PHONE` during the rollback window.
- Removes fallback to `PHONE` once coverage is proven.

Wait until all R10/R11 instances, batches, and external consumers depending on `PHONE` are retired.

### 9.7. Contract S102

Once the rollback window closes and the consumer inventory confirms zero dependencies:

~~~sql
ALTER TABLE customers
DROP COLUMN phone;
~~~

Deploy R13 or run as a separate migration. After contract, binary rollback to R10/R11 is impossible without restoring the old schema or deploying a new compatibility layer.

## 10. Oracle DDL and Transaction Boundaries

Oracle DDL performs implicit commits according to database rules. This directly affects how migrations are written and how failures are handled.

### 10.1. DDL Is Not Like DML

Example:

~~~sql
UPDATE customers
SET status = 'ACTIVE'
WHERE customer_id = 100;

ALTER TABLE customers
ADD (new_flag CHAR(1));

ROLLBACK;
~~~

DDL commits any open transaction before executing and commits upon successful completion per Oracle semantics. The `UPDATE` before the DDL is already committed; the subsequent `ROLLBACK` does not revert it.

### 10.2. @Transactional Does Not Make DDL Roll Back

Never assume:

~~~java
@Transactional
public void migrate() {
    jdbcTemplate.execute("ALTER TABLE customers ADD new_flag CHAR(1)");
    jdbcTemplate.update("UPDATE customers SET new_flag = 'N'");
    throw new IllegalStateException("force rollback");
}
~~~

will roll back the `ALTER TABLE`. The DDL implicitly committed. Subsequent DML runs in a new transaction and rolls back per transaction semantics, but the schema change persists.

### 10.3. Separate DDL and DML Migrations

Design migrations with:
- Small DDL steps guarded by preconditions and postconditions.
- Data backfills executed separately in batches.
- Migration metadata recording completed steps.
- Inspection scripts to assess state if a run aborts partway.
- No reliance on transaction rollbacks to undo DDL.
- Forward-fix or compensating scripts ready when needed.

### 10.4. Flyway and Liquibase

Migration tools version and sequence changes cleanly. However, transactional rollback support depends on the database and statement types. For Oracle DDL, no tool can turn implicit commits into atomic transaction rollbacks.

Verify:
- Tool version.
- Migration transaction mode.
- Which statements are DDL.
- Whether migrations are re-runnable.
- Whether the schema history table accurately reflects partial failures.
- Recovery steps when a migration aborts mid-way.

Never run migrations concurrently from every application replica at startup. Use a single controlled migration job or runner to avoid races and locks.

## 11. Constraints and Indexes in Rolling Deployments

### 11.1. Adding NOT NULL

If old apps omit the new column, adding `NOT NULL` immediately breaks old `INSERT`s. A safe sequence is:
1. Add nullable column.
2. Deploy code writing the new value.
3. Backfill historical rows.
4. Confirm zero unexpected `NULL`s remain.
5. Add and validate the constraint.
6. Only then rely on the new invariant in application code.

### 11.2. CHECK Constraints

Use constraints to enforce invariants in the database rather than only in app code. First ensure old apps cannot generate violating rows. You can deploy `NOVALIDATE` and later `VALIDATE` on schedule if semantics fit.

### 11.3. Foreign Keys

Adding a foreign key can break old app DML if invalid references exist. Clean up data first, stage the constraint, and validate afterward.

### 11.4. New Indexes

Indexes can slow DML due to maintenance overhead. Create indexes before new apps activate queries against them, while measuring build time, redo, I/O, locks, and Data Guard impact. When using `ONLINE`, check limits and prerequisites for your Oracle release and edition.

## 12. Changing Data Types Safely

Changing a column's data type in place can fail or lose data. For example, converting `VARCHAR2` to `NUMBER`:
- Some rows fail to parse.
- Leading zeros may carry meaning.
- Precision/scale may be insufficient.
- Old apps still send strings.
- Indexes or constraints depend on the column.

The safer pattern is:
1. Add a new column with the target data type.
2. Deploy dual-read/dual-write code.
3. Backfill using validated conversions.
4. Quarantine invalid values.
5. Reconcile.
6. Switch consumers to the new column.
7. Close the rollback window.
8. Drop the old column last.

Even when widening types or shifting semantics, evaluate NLS behavior, rounding, truncation, nullability, and indexes.

## 13. Edition-Based Redefinition (EBR)

Oracle Edition-Based Redefinition enables online application and schema upgrades for more complex changes, especially when multiple editions must coexist inside one database.

EBR relies on concepts such as:
- Editions.
- Editioned objects.
- Editioning views.
- Crossedition triggers.
- Edition-scoped code deployment.
- Services/sessions bound to specific editions.

### 13.1. Editioning Views

An editioning view provides a stable projection per edition, allowing underlying table structures to evolve while code in another edition continues seeing its expected view contract.

### 13.2. Crossedition Triggers

Crossedition triggers synchronize data between old and new representations during edition transitions. They must be designed to avoid loops, handle concurrency, and preserve consistency.

### 13.3. When to Consider EBR?

- Large applications requiring true online upgrades.
- Many PL/SQL objects needing synchronized cutover.
- Overlapping execution windows for old and new editions.
- DBA/DevOps teams experienced in managing editions.
- Oracle release and licensing/feature support meet requirements.

EBR is not an automatic silver bullet for every schema change. Review object types, editionability rules, restrictions, and release runbooks.

## 14. Database APIs and View Compatibility

One way to reduce coupling is avoiding direct app access to raw base tables.

### 14.1. Views as Contracts

You can maintain a view preserving old names and shapes while underlying tables evolve. Old apps query the view; new apps use the new API or view.

~~~sql
CREATE OR REPLACE VIEW customer_legacy_v AS
SELECT customer_id,
       phone
FROM customers;
~~~

The view must preserve legacy semantics. If an underlying column is renamed or removed, adjust the view or preserve its backing source until consumers depart.

### 14.2. Stored Procedure / Package APIs

PL/SQL packages can shield table changes:
- Apps call procedures instead of raw DML.
- Packages maintain stable contracts.
- Underlying schemas evolve behind the package.
- Versioned packages/APIs support transitions.

However, packages also have consumers and dependencies. Invalidations or signature changes can still break old apps.

### 14.3. Avoiding Shared-Table Coupling

When multiple teams query each other's base tables directly, schema changes become hard to coordinate. Exposing data access APIs, views, or service boundaries keeps contracts and consumer inventories manageable.

## 15. Message and Event Schemas Must Also Be Compatible

Applications often exchange JSON, messages, or events. A database schema may be compatible while an event contract breaks.

Principles:
- Add optional fields first.
- Old consumers ignore unknown fields if serializers permit.
- Never alter the meaning of existing fields.
- Never repurpose old enum values with new meanings.
- Version events on breaking changes.
- Use bounded tolerant readers without silently accepting corrupted data.
- Test producer/consumer compatibility across N and N-1.

If a new app emits JSON that an old app cannot parse, rolling back app binaries still fails even if database columns stayed intact.

## 16. Testing Schema Compatibility

Testing must cover all critical app/schema combinations within the compatibility window.

### 16.1. Compatibility Matrix Testing

Example:

| Test | Schema S21 | Schema S22 |
| --- | --- | --- |
| App R10 read/write | Must PASS | Must PASS during transition |
| App R11 dual-read/write | PASS | PASS |
| App R12 new-column only | Only after backfill | PASS |
| Batch R10 | PASS | PASS until retired |
| Reporting consumer | PASS | PASS after query switch |

Never test only R12 against the final schema. Test old apps against the expanded schema and new apps against the transitional schema.

### 16.2. Migration Testing

On a clone with production-representative data:
- Run the expand DDL.
- Run the backfill.
- Abort mid-way and resume.
- Rerun migrations to verify idempotency.
- Test concurrent application writes.
- Test invalid data rows.
- Test locks and timeouts.
- Test rollback and forward-fix paths.
- Test contract only once preconditions are met.

### 16.3. Load and Performance Testing

Measure:
- DDL execution time.
- Lock waits.
- DML latency.
- Backfill rows/sec.
- Redo/undo growth.
- Index build cost.
- Query execution plans.
- Connection pool behavior.
- Data Guard transport/apply lag.
- Replication/CDC lag.

### 16.4. Failure Injection

Rehearse:
- Migration job killed mid-batch.
- Database restart.
- Connection timeout.
- A chunk containing unparseable data.
- New app rolled back mid-backfill.
- A legacy consumer still writing.
- Duplicate scheduler job execution.
- Index build failure.
- Feature flag toggled accidentally.
- Contract migration triggered while legacy consumers still run.

Define database state and recovery steps for every scenario.

## 17. Deployment Orchestration

### 17.1. Single Migration Owner

Designate a single job or pipeline to run schema migrations. Application replicas must never race to run DDL at startup.

The migration owner requires:
- Distributed locking or a single-runner mechanism.
- Migration history tracking.
- Precondition and postcondition checks.
- Logging.
- Timeouts.
- Explicit approval for destructive migrations.
- Least-privilege database permissions.

### 17.2. Phased Rollout Order

A common sequence:
1. Take backup/checkpoint per policy.
2. Run expand schema migration.
3. Deploy new app in compatibility mode.
4. Verify instance health.
5. Run batched backfill.
6. Reconcile data.
7. Flip feature flags / shift traffic.
8. Monitor the compatibility window.
9. Retire legacy consumers.
10. Execute contract in a separate release.

Some systems require deploying dual-write apps before backfilling; others require schema expansion before app rollout. Pick the order dictated by code contracts and testing, ensuring every intermediate state works.

### 17.3. Readiness and Liveness

Readiness probes should verify the app can serve traffic against the current schema. Avoid naive readiness checks that only ping a database connection while missing incompatible schema versions.

Consider checking:
- Schema capability/version.
- Required columns, indexes, and packages.
- Required privileges.
- Fail startup if the schema is too old for the app.
- Allow the new app to run on expanded schemas prior to contract.

Liveness probes should not depend on heavy queries or backfill completion if the process is healthy and serving valid requests.

### 17.4. Migration Locks and Concurrent Deployments

If two deployment pipelines run concurrently:
- Both may attempt migrations simultaneously.
- One pipeline could contract while another deploys an older app.
- Migration history tables can race.
- DDL locks can block DML.

Enforce release locks, change coordination, and a single migration executor. Only one release owner may alter a schema at a time.

## 18. Rollback and Forward-Fix

### 18.1. Binary Rollback

Reverting to an earlier app artifact is safe only if the schema remains compatible with that older app. During expand/migrate, retain legacy columns specifically to preserve binary rollback safety.

### 18.2. Schema Rollback

Not every migration has a clean inverse:
- Adding a nullable column: can stay in place on app rollback.
- Adding an index: can be dropped if unneeded.
- Backfills: new values can stay without necessarily deleting them.
- Data normalization: inverses often cannot restore raw formatting.
- Dropping/renaming columns: requires backup/restore or compatibility layers.
- Lossy conversions: cannot be fully reversed via reverse SQL alone.

### 18.3. Forward-Fix

Once schemas have changed and new live data has arrived, a forward-fix is often safer than rolling back:
- Patch the new code.
- Keep the schema additive.
- Repair bad data under controlled scripts.
- Add missing indexes or constraints.
- Ship a follow-up migration.

Never force a database backward if doing so discards valid live transactions.

### 18.4. Restore Points / PITR

Flashback Database or Point-in-Time Recovery (PITR) can return a database to pre-migration state, but wipes out transactions committed after the target point. Evaluate RPO, post-target data loss, Data Guard topology, and service cutover before invoking it. That is database recovery, not routine application rollback.

## 19. Post-Deployment Monitoring

Monitor throughout the compatibility window:
- App version per instance.
- Schema migration version.
- Count of remaining old instances.
- Query and error rates by `SQL_ID`.
- `ORA-00904` invalid identifier.
- `ORA-01400` cannot insert `NULL`.
- `ORA-02291`/`ORA-02292` constraint violations.
- `ORA-00054` resource busy.
- DDL lock waits.
- Backfill progress and row errors.
- Old/new column mismatches.
- Index status.
- Data Guard lag.
- Queue/CDC lag.
- Connection pool metrics.
- Scheduled job failures.

Emit metrics for fallback reads and legacy-column writes. Only consider contract after those metrics drop to zero for a sustained period and the consumer inventory confirms no stragglers.

## 20. Schema Change Deployment Runbook

### Pre-Release

1. Finalize schema and consumer inventory.
2. Build the app/schema compatibility matrix.
3. Plan expand/migrate/contract phases.
4. Account for Oracle DDL implicit commits.
5. Assess locks, storage, redo/undo, and Data Guard impact.
6. Author migrations with preconditions and postconditions.
7. Build chunked/checkpointed backfill scripts.
8. Define quarantine and reconciliation processes.
9. Prepare rollback and forward-fix plans.
10. Test on a clone with representative data.
11. Obtain separate approval for the destructive contract phase.

### During Release

1. Execute the expand migration once.
2. Verify schema capabilities.
3. Deploy compatible app version.
4. Run smoke tests.
5. Enable dual-read/dual-write via feature flags.
6. Execute batched backfill.
7. Monitor errors, lag, and resources.
8. Reconcile old and new data.
9. Cut over read and write paths.
10. Record release state.

### Post-Release

1. Confirm all app instances run the new version.
2. Confirm all batch jobs and consumers have migrated.
3. Monitor legacy column access.
4. Keep legacy schema intact during the rollback window.
5. Close the rollback window with sign-off.
6. Execute the contract migration separately.
7. Verify object, index, and constraint states.
8. Update schema and API documentation.
9. Archive evidence and release records.

## 21. Compatibility Design Checklist

- [ ] Identified all apps, jobs, and consumers using the schema.
- [ ] Identified the oldest version that may still run.
- [ ] Built the app/schema compatibility matrix.
- [ ] Separated breaking changes from expand.
- [ ] Added new columns/tables in ways old apps tolerate.
- [ ] Verified new apps handle un-backfilled rows.
- [ ] Defined canonical source and conflict rules for dual-writes.
- [ ] Built chunking, checkpoints, and retries into backfill.
- [ ] Prevented backfill from overwriting newer app writes.
- [ ] Quarantined unconvertible data.
- [ ] Built count/aggregate/hash reconciliation.
- [ ] Staged and validated constraints incrementally.
- [ ] Tested index builds.
- [ ] Accounted for DDL implicit commits.
- [ ] Enforced single migration owner.
- [ ] Verified binary rollback compatibility throughout the rollback window.
- [ ] Verified event/message contract compatibility.
- [ ] Confirmed zero legacy consumers before contract.
- [ ] Secured approval and recovery plans for contract.
- [ ] Verified legacy usage metrics reached zero.

## 22. Self-Practice Exercises

1. Why do rolling deployments require multi-version compatible schemas?
2. Distinguish backward compatibility from forward compatibility.
3. Diagram the three phases: expand, migrate, and contract.
4. Build a compatibility matrix for apps R10/R11/R12 and schemas S20/S21/S22.
5. Why is adding a nullable column usually safer than renaming a column?
6. When can adding `NOT NULL` break an old app?
7. Distinguish schema migrations from data migrations.
8. Why do backfills need checkpoints and idempotency?
9. Design a dual-read query when the new column is not yet fully backfilled.
10. Describe the risk when old apps write only the legacy column while new apps dual-write.
11. When is a trigger needed to synchronize two columns?
12. Why should compatibility triggers be time-bound?
13. Design a key-range backfill for a table with hundreds of millions of rows.
14. How do you prevent lost updates between a backfill and concurrent app writes?
15. Why should checkpoints commit in the same transaction as batch data?
16. Design a quarantine workflow for rows that fail normalization.
17. Write a reconciliation query checking missing and mismatched values between two columns.
18. When is it safe to switch the read path exclusively to the new column?
19. Why should you not `DROP` the old column immediately after deploying the new app?
20. Distinguish `DROP COLUMN` from `SET UNUSED`.
21. Why do Oracle DDL implicit commits make migration rollback different from DML rollback?
22. Can Flyway or Liquibase automatically roll back Oracle DDL?
23. Design a workflow to add a `CHECK` constraint using `NOVALIDATE` followed by `VALIDATE`.
24. What should you check before creating an index `ONLINE`?
25. When should you consider Edition-Based Redefinition (EBR)?
26. What roles do editioning views and crossedition triggers play?
27. How do you keep event/message contracts N/N-1 compatible?
28. When is a forward-fix safer than a schema rollback?
29. Design a failure-injection test for a backfill interrupted mid-run.
30. Write an expand-migrate-contract runbook for replacing a column shared by multiple services.

**Deploying multi-version compatible schema changes is a controlled transition across an overlap window where old and new apps coexist.** Add new structures first, deploy dual-compatible read/write code, backfill in checkpointed batches, reconcile data, migrate all consumers, and contract last. In Oracle, DDL performs implicit commits, so keep migrations small with explicit preconditions, postconditions, forward-fix options, and recovery plans; binary rollback stays safe only as long as the schema preserves the contract old apps require.

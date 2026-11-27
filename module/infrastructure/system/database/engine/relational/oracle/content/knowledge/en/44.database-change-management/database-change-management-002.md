# Flyway/Liquibase with Oracle and Migration Execution Order

Migrations manage versioned changes to database schemas and data. As an Oracle application evolves, changes such as creating tables, adding columns, modifying constraints, creating sequences, updating reference data, or replacing PL/SQL packages must be applied in a deterministic and traceable order. Flyway and Liquibase bring these changes under source control, apply them automatically per environment, and record execution history.

Oracle has an important characteristic that directly affects migrations: many DDL statements auto-commit. Therefore, you cannot assume an entire migration file will roll back like a normal DML transaction. You must design dependency ordering, break changes into small steps, prepare recovery strategies, and verify schema state after every run.

## 1. What Problems Do Migrations Solve?

Without a migration tool, operations teams often receive ad-hoc SQL files over email or tickets. Operators must manually figure out which file runs first, which environments have already run it, whether it can be re-run, and whether any changes should be skipped. This practice easily leads to schema divergence across development, test, and production.

A controlled migration process must answer:

- Which changes belong to which application version?
- Which changes have already been applied to the current database?
- What is the creation order for tables, foreign keys, indexes, data, and PL/SQL?
- If a migration fails partway through, what state is the database in?
- How do you verify that a schema matches the migration source code?
- How do you deploy the same changes across multiple environments without misordering or duplicate runs?

Both Flyway and Liquibase store migration history inside the database. Each tool has its own declaration model, yet both rely on one core rule: applied migrations must be treated as immutable history. When you need to fix a result, create a new migration with a higher version rather than editing the old file and re-running it across environments.

## 2. Choosing Between Flyway and Liquibase

| Criterion | Flyway | Liquibase |
|---|---|---|
| How changes are described | Primarily versioned or repeatable SQL scripts | XML, YAML, JSON, or Liquibase-formatted SQL changelogs |
| Ordering | Migration version; repeatable runs after versioned | Changeset order within a changelog and changelog includes |
| History | Schema history table, defaulting to `flyway_schema_history` | `DATABASECHANGELOG` |
| Update locking | Flyway's migration locking mechanism | `DATABASECHANGELOGLOCK` table |
| Pre-execution checks | `validate`, `info`, and testing on a separate database | `validate`, `updateSQL`, and testing on a separate database |
| Re-runnable changes | Repeatable migrations, commonly used for views or PL/SQL | `runOnChange`, `runAlways`, and preconditions |
| Rollback management | Usually favors forward-fix migrations; undo features depend on edition/configuration | Rollbacks can be declared per changeset, though still subject to Oracle DDL limits |

Flyway fits well when a team prefers managing schemas with clear SQL files and simple version ordering. Liquibase fits when structured changelogs, multiple formats, preconditions, contexts, labels, or change-coupled rollback declarations are needed.

Neither tool makes Oracle migrations atomic on its own. Choose a tool based on how the team manages source code, SQL skills, deployment control needs, and operational capabilities. For a single schema, maintain one tool as the single source of truth. If Flyway and Liquibase manage the same schema without clear boundaries, each tool only sees its own history and may apply duplicate or out-of-order changes.

## 3. Oracle Characteristics to Understand Before Writing Migrations

### 3.1. DDL Auto-Commits

Oracle performs an implicit commit before and after many DDL statements, such as `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, `CREATE SEQUENCE`, `CREATE OR REPLACE VIEW`, and `CREATE OR REPLACE PACKAGE`. As a result, a migration containing multiple DDL statements may already have created several objects before a later statement fails.

Example:

```sql
CREATE TABLE customer (
  customer_id NUMBER PRIMARY KEY,
  customer_name VARCHAR2(200 CHAR)
);

ALTER TABLE customer ADD status VARCHAR2(20 CHAR);

CREATE INDEX ix_customer_status ON customer(status);
```

If creating the index fails, the table and column already created may remain in place. Application-level transaction rollback will not automatically drop those objects. Migration tools also cannot turn Oracle DDL into a fully reversible transaction.

Design implications:

- Split migrations into small, meaningful changes; avoid bundling dozens of unrelated changes into a single file.
- Pre-check conditions for objects, privileges, storage capacity, and dependencies.
- Prepare a recovery plan in case part of the DDL committed while the tool has not marked the migration as successful.
- Use forward migrations to repair state after an incident, or restore from a backup/clone according to a verified plan.
- Do not rely on a tool's rollback button as a complete undo mechanism for DDL.

### 3.2. DML and DDL Have Different Transactional Behavior

DML operations such as `INSERT`, `UPDATE`, and `DELETE` participate in Oracle transactions. However, mixing DML and DDL in the same migration can cause the DDL to commit any pending DML before it. Do not write a file assuming all statements will roll back together on failure.

Do not insert `COMMIT` arbitrarily in migrations. For standard DML migrations, let the tool manage transactions according to its configuration. For large backfills requiring batched commits, design a separate data process with checkpoints and resumability rather than a long, unobservable schema change.

### 3.3. PL/SQL Contains Internal Semicolons

Packages, procedures, functions, triggers, and anonymous PL/SQL blocks contain many semicolons inside their bodies. A `/` on a standalone line is a SQL*Plus/SQLcl delimiter command, not part of a SQL statement sent directly over JDBC.

For migrations executed via JDBC, use the parser and delimiter appropriate for your Flyway/Liquibase version. In Liquibase, you can configure `splitStatements: false` on a changeset containing a single PL/SQL unit so the tool sends the whole block to Oracle. In Flyway, use the Oracle parser for your installed version and check how it detects PL/SQL; do not mix SQL*Plus conventions with JDBC conventions arbitrarily. Always test package/procedure scripts on the exact tool version before deploying.

Example package specification:

```sql
CREATE OR REPLACE PACKAGE customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  );
END customer_api;
```

And package body:

```sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  ) IS
  BEGIN
    UPDATE customer
       SET status = p_status
     WHERE customer_id = p_customer_id;
  END set_status;
END customer_api;
```

When using JDBC, the blocks above are separate statements. Do not insert SQL*Plus `/` inside PL/SQL content unless your tool's parser configuration explicitly requires that delimiter.

### 3.4. Schemas in Oracle Are Tied to Users

In Oracle, a schema is the collection of objects owned by a database user. For instance, user `APP_OWNER` owns table `CUSTOMER`, package `CUSTOMER_API`, and sequence `CUSTOMER_SEQ`. Therefore, determine whether migrations run as the schema owner or as a separate deployment user with appropriate privileges.

The `CURRENT_SCHEMA` setting only changes how Oracle resolves unqualified object names; it does not grant privileges and does not transfer object ownership. If running migrations with a dedicated deployment account, grant required privileges directly and explicitly specify the target schema, history table schema, object creation privileges, and tablespace quotas.

For packages running with definer's rights, required privileges on objects in other schemas generally must be granted directly to the package owner. Do not assume the login account's roles will automatically supply compile/runtime privileges for stored PL/SQL.

## 4. Determining Migration Order by Dependencies

Migration order must reflect object dependencies. A reference ordering for a new application schema:

1. Verify connectivity, user/schema, tablespace quotas, privileges, and environment settings.
2. Create shared data types, sequences, or foundational objects needed.
3. Create parent tables, columns, and primary keys.
4. Create child tables, foreign keys, unique constraints, and check constraints.
5. Create indexes supporting queries and constraints.
6. Load minimal reference data required by objects or the application.
7. Create views, synonyms, and table-dependent objects.
8. Grant required cross-schema privileges before compiling dependent packages.
9. Create package specifications, procedures/functions, and package bodies in dependency order.
10. Create triggers, jobs, or operational objects after the objects they call exist.
11. Backfill data, validate constraints, and verify object states.

This is a guiding sequence, not a rigid rule for every application. For example, a view may need to exist before a package that queries it; grants must exist before compiling a package referencing another schema's objects; synonyms must exist before compiling code that uses them. Build an actual dependency graph from your project's objects and source code.

### 4.1. Separate Schema Changes from Large Data Changes

Adding columns, constraints, and indexes are schema changes. Updating millions of rows is a data change. The two have different execution times, locking profiles, and recovery plans.

For large datasets, break the work into phases:

- Add the new structure in a state compatible with the running application, such as a nullable column.
- Deploy application code capable of reading or writing both old and new structures.
- Run the backfill in batches, recording checkpoints and tracking processed row counts.
- Verify data after the backfill.
- Switch the application to the new structure.
- Drop the old structure only in a subsequent migration after no running application version depends on it.

This pattern is commonly called expand-migrate-contract. It reduces risk when the application runs multiple instances or cannot tolerate extended downtime for schema changes.

### 4.2. Foreign Keys and Constraints on Large Tables

When adding foreign keys, unique constraints, or check constraints to a table with existing data, determine whether existing data satisfies the condition. On large tables, validating constraints can take significant time and affect workload.

Oracle supports constraint states such as `ENABLE NOVALIDATE` in appropriate situations: existing data is not validated yet, while new DML is checked against the constraint. After cleaning up data, the constraint can be validated using `ENABLE VALIDATE`. Understand the exact constraint state before considering a migration complete; `NOVALIDATE` does not guarantee all historical data is valid.

## 5. Organizing Migrations with Flyway

### 5.1. File Structure and Versioning Rules

Flyway commonly uses two types of migrations:

- **Versioned migrations:** filenames start with `V`, have a unique version, and execute in ascending version order.
- **Repeatable migrations:** filenames start with `R__`, re-execute whenever their content changes; typically used for views, packages, or source-managed procedures.

Example structure:

```text
db/
  migration/
    oracle/
      V001__create_customer_table.sql
      V002__add_customer_status.sql
      V003__create_customer_sequence.sql
      V004__insert_customer_status_reference.sql
      R__customer_summary_view.sql
      R__customer_api_package.sql
```

Example table creation migration:

```sql
-- V001__create_customer_table.sql
CREATE TABLE customer (
  customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
  customer_name VARCHAR2(200 CHAR) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_customer PRIMARY KEY (customer_id)
);
```

Identity columns require an Oracle release that supports the feature. If the application must remain compatible with older releases, use a sequence and key-generation strategy appropriate for your architecture rather than assuming every version supports identity syntax.

A subsequent migration might add a column:

```sql
-- V002__add_customer_status.sql
ALTER TABLE customer
  ADD status VARCHAR2(20 CHAR);

UPDATE customer
   SET status = 'ACTIVE'
 WHERE status IS NULL;

ALTER TABLE customer
  MODIFY status DEFAULT 'ACTIVE';
```

This example illustrates the sequence of adding a column, backfilling, and setting a default. On a large table, do not blindly run a full-table UPDATE inside a synchronous deployment migration; evaluate lock duration, redo/undo, storage, and split the backfill into a batched job if needed. If a NOT NULL constraint is required, add it only after verifying data validity and an appropriate locking plan.

Version numbers can use sequential numbers like `V001`, `V002` or a team versioning scheme like `V2026.11.14.1`. What matters is that versions are unique, monotonically increasing, and independent of alphabetical filename sorting. Never edit or rename a versioned migration that has already been applied in any shared environment.

### 5.2. Repeatable Migrations for Replaceable Objects

Views and packages are commonly created with `CREATE OR REPLACE`. When an object's source changes, a repeatable migration can update its definition:

```sql
-- R__customer_summary_view.sql
CREATE OR REPLACE VIEW customer_summary AS
SELECT status, COUNT(*) AS customer_count
FROM customer
GROUP BY status;
```

Repeatable migrations run after pending versioned migrations. Thus, any tables and columns required by a view must already be created in earlier versioned migrations. For packages with multiple dependencies, ensure specifications, bodies, and related objects deploy in the proper order; do not rely on arbitrary ordering among repeatable files.

Never use repeatable migrations for business data that must be applied exactly once, such as creating accounts, loading transactions, or adjusting balances. Those changes require versioned migrations or controlled data pipelines.

### 5.3. Oracle Connection Configuration

Example basic Flyway configuration:

```properties
flyway.url=jdbc:oracle:thin:@//dbhost:1521/appsvc
flyway.user=APP_OWNER
flyway.schemas=APP_OWNER
flyway.defaultSchema=APP_OWNER
flyway.locations=filesystem:db/migration/oracle
flyway.table=flyway_schema_history
```

The URL uses an Oracle service name in the format `jdbc:oracle:thin:@//host:port/service_name`. If the environment uses a SID or TNS configuration, the URL differs and should follow your system's connection standard.

Never store production passwords in configuration files committed to Git. Pass secrets via a secret store, environment variables, or pipeline security mechanisms. Restrict the migration user to the exact schema and privileges needed.

Depending on the Flyway version and distribution, Oracle database support may require a separate Oracle module alongside core; the Oracle JDBC driver must also be compatible with the JDK, database, and tool version. Pin these component versions in your build so local and CI environments use the exact same parser and driver.

### 5.4. Common Operational Commands

Common Flyway commands:

```text
flyway info
flyway validate
flyway migrate
flyway repair
```

- `info` displays applied migrations, pending migrations, and history status.
- `validate` checks source migrations against recorded history, including checksums of versioned migrations.
- `migrate` applies pending migrations in order.
- `repair` adjusts history metadata in supported scenarios, such as syncing checksums or handling certain history entries.

`repair` does not drop tables/columns created by DDL and does not restore data. Before running repair after an Oracle failure, identify which objects were created, which statements committed, and what history recorded. Only update metadata after reconciling the actual schema.

When introducing Flyway to a database with an existing schema, baseline can mark a starting version without running all historical migrations. Only baseline after verifying the current schema actually matches the baseline version. Never enable automatic baseline across all production databases without validation checks.

## 6. Organizing Migrations with Liquibase

### 6.1. Changelogs and Changesets

Liquibase manages changes in changelogs. Each changeset is identified by `id`, `author`, and changelog path. During execution, Liquibase records applied changesets in `DATABASECHANGELOG`; update locking is coordinated via `DATABASECHANGELOGLOCK`.

Changelogs can be written in XML, YAML, JSON, or formatted SQL. For Oracle, formatted SQL is useful when teams want native SQL and PL/SQL syntax, while XML/YAML are useful for expressing changes with structured change types.

Formatted SQL example:

```sql
--liquibase formatted sql

--changeset app:001 dbms:oracle
CREATE TABLE customer (
  customer_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
  customer_name VARCHAR2(200 CHAR) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
  CONSTRAINT pk_customer PRIMARY KEY (customer_id)
);

--changeset app:002 dbms:oracle
ALTER TABLE customer ADD status VARCHAR2(20 CHAR);
```

Each changeset should contain a single meaningful change with a clearly verifiable post-execution state. Avoid packing unrelated objects into one changeset just to reduce changelog lines.

### 6.2. Declaring PL/SQL and Delimiters

For packages, procedures, or triggers, prevent Liquibase from splitting statements at semicolons inside the PL/SQL body. A changeset containing a single package specification can be declared as:

```sql
--liquibase formatted sql
--changeset app:010 dbms:oracle splitStatements:false
CREATE OR REPLACE PACKAGE customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  );
END customer_api;
```

The package body should live in its own changeset:

```sql
--liquibase formatted sql
--changeset app:011 dbms:oracle splitStatements:false
CREATE OR REPLACE PACKAGE BODY customer_api AS
  PROCEDURE set_status(
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2
  ) IS
  BEGIN
    UPDATE customer
       SET status = p_status
     WHERE customer_id = p_customer_id;
  END set_status;
END customer_api;
```

In this example, each changeset submits one PL/SQL unit as a single statement. When using XML/YAML or `sqlFile`, configure `splitStatements` and `endDelimiter` according to your Liquibase version's documentation. Do not include SQL*Plus `/` inside JDBC content if the parser sends the statement intact.

### 6.3. runOnChange, runAlways, and Preconditions

Several attributes control how changesets are processed:

- `runOnChange: true` re-runs the changeset when its checksum changes. Useful for views or packages managed as replaceable source.
- `runAlways: true` runs the changeset on every update. Use only when repeated execution is explicitly designed to be safe.
- `preConditions` check conditions before applying, such as verifying the database is Oracle, a table exists, or a column does not exist yet.
- `context` and `labels` filter changeset groups by environment or deployment purpose.

Example:

```xml
<changeSet id="020-add-customer-status" author="app">
    <preConditions onFail="HALT">
        <dbms type="oracle"/>
        <not>
            <columnExists tableName="CUSTOMER" columnName="STATUS"/>
        </not>
    </preConditions>
    <addColumn tableName="CUSTOMER">
        <column name="STATUS" type="VARCHAR2(20 CHAR)"/>
    </addColumn>
</changeSet>
```

Preconditions help detect when a schema is not in the expected state. Do not use `onFail="MARK_RAN"` as a blanket way to ignore errors: if an object is missing or misconfigured, marking the changeset as executed makes history claim the schema is up to date when it actually is not.

### 6.4. Rollback and Metadata

Liquibase allows declaring rollbacks for changesets. For DML changes or clearly reversible schema changes, rollbacks can be helpful. However, rollback SQL must still execute cleanly on Oracle and must not destroy valid data created after the migration.

Because Oracle DDL auto-commits, declaring a rollback does not make DDL automatically transactional. Write explicit rollbacks, test them on data clones, and verify preconditions before running. For destructive changes such as dropping columns or lossy data transformations, safer options are typically backup/restore or a forward migration with a dedicated reverse conversion step.

Common commands:

```text
liquibase validate
liquibase updateSQL
liquibase update
liquibase status
liquibase release-locks
liquibase clear-checksums
```

- `validate` checks the changelog and changeset structure.
- `updateSQL` generates the planned SQL for review before applying.
- `update` executes pending changesets.
- `status` lists unapplied changesets.
- `release-locks` clears the metadata lock after confirming no update process is still running.
- `clear-checksums` clears stored checksums so Liquibase recalculates them on the next run; this is not a fix for schema drift.

If an update is interrupted and the lock remains held, first check running migration processes and database state. Release the lock only after confirming no legitimate process is active. Never drop `DATABASECHANGELOG` or `DATABASECHANGELOGLOCK` to work around routine errors.

### 6.5. Separating the History Schema

Liquibase can use a dedicated schema for its tracking tables. Distinguish between the target schema for application objects and the schema holding Liquibase metadata. Settings like `defaultSchemaName` and `liquibaseSchemaName` should be configured consistently across the pipeline. The migration user needs read/write access on the history tables and create/alter privileges on the target schema.

Do not arbitrarily rename changelog paths or changeset identifiers after execution, because Liquibase matches history using identifiers and changelog paths. When restructuring directories, use logical path mechanisms or proper transition procedures to preserve stable identifiers.

## 7. Practical Oracle Migration Ordering Structure

An easy-to-follow directory layout:

```text
database/
  oracle/
    001-foundation/
      V001__create_reference_types.sql
      V002__create_customer.sql
      V003__create_order.sql
    002-constraints/
      V004__add_customer_order_fk.sql
      V005__add_order_indexes.sql
    003-reference-data/
      V006__insert_customer_statuses.sql
    004-program-units/
      V007__create_customer_api.sql
      V008__create_order_api.sql
    repeatable/
      R__customer_summary_view.sql
      R__customer_api_package.sql
    data-jobs/
      backfill_customer_status.sql
```

With Flyway, actual versioned files are typically placed in configured locations and sorted by version. The subdirectories above illustrate logical grouping; configure locations appropriately or use a single location according to project conventions. With Liquibase, files can be included from a root changelog in the exact order desired.

Example Liquibase root changelog:

```yaml
databaseChangeLog:
  - include:
      file: changes/001-create-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-create-order.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/003-customer-order-fk.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/004-customer-api.yaml
      relativeToChangelogFile: true
```

Include order is part of the design. If an API package references table `CUSTOMER`, the table and necessary privileges must exist before the package changeset. If a view depends on a new column, the migration adding the column must precede the view update.

### 7.1. Creating Tables, Sequences, and Foreign Keys

If not using identity columns, you can create a separate sequence:

```sql
CREATE TABLE customer (
  customer_id NUMBER NOT NULL,
  customer_name VARCHAR2(200 CHAR) NOT NULL,
  CONSTRAINT pk_customer PRIMARY KEY (customer_id)
);

CREATE SEQUENCE customer_seq
  START WITH 1
  INCREMENT BY 1
  CACHE 100;
```

The application can obtain keys via `customer_seq.NEXTVAL`. Sequences are independent objects and sequence values do not roll back like regular table columns; gaps in sequence numbers are normal. Do not use sequences to guarantee gapless record numbering.

Create child tables after parent tables:

```sql
CREATE TABLE customer_order (
  order_id NUMBER NOT NULL,
  customer_id NUMBER NOT NULL,
  order_total NUMBER(14,2) NOT NULL,
  CONSTRAINT pk_customer_order PRIMARY KEY (order_id)
);

ALTER TABLE customer_order
  ADD CONSTRAINT fk_order_customer
  FOREIGN KEY (customer_id)
  REFERENCES customer(customer_id);

CREATE INDEX ix_order_customer
  ON customer_order(customer_id);
```

An index on a foreign key column can help certain queries and parent-row operations avoid child table scans, though decisions should be based on workload and overall index design. Do not create indexes that duplicate indexes already created to back constraints.

### 7.2. Loading Reference Data

Catalog values such as order statuses or customer types can be loaded via versioned migrations:

```sql
INSERT INTO customer_status (status_code, status_name)
VALUES ('ACTIVE', 'Active');

INSERT INTO customer_status (status_code, status_name)
VALUES ('INACTIVE', 'Inactive');
```

Versioned migrations run once according to tool history, making them suitable for versioned initial data. If a script might be run manually or re-run during recovery, guarantee idempotency using unique keys and proper check conditions. Avoid using `WHEN OTHERS THEN NULL` to swallow duplicate-key errors; that can mask privilege, data type, or constraint errors.

If catalog values need updating in a later release, create a new migration with explicit conditions targeting the records to modify. Never edit a seed file already applied in production.

### 7.3. Granting Privileges and Synonyms

If the application schema calls a package in another schema, grants must be executed before compiling dependent code:

```sql
GRANT SELECT ON reference_data.customer_status
  TO app_owner;

GRANT EXECUTE ON reference_data.customer_rules
  TO app_owner;

-- Run CREATE SYNONYM as APP_OWNER.
CREATE SYNONYM customer_status
  FOR reference_data.customer_status;
```

Replace owners and objects with your system's actual names. Creating a synonym does not grant privileges; users still need the corresponding privileges on the underlying object. For PL/SQL running with definer's rights, grant privileges directly to the program owner as required.

## 8. Deploying via a CI/CD Pipeline

A migration pipeline can be structured into stages:

1. **Build:** package changelogs or SQL migrations alongside the application version.
2. **Static validation:** check filenames, unique versions, changelog formats, parsers, and internal rules.
3. **Provision:** spin up a temporary Oracle database or isolated PDB with locked release, edition, RU, and settings.
4. **Preview:** use `liquibase updateSQL` or a similar plan-inspection tool; for Flyway, use `info`, `validate`, and test migration on a disposable database.
5. **Apply:** run migrations via a single deployment job using properly scoped credentials and secrets.
6. **Verify:** check migration history, invalid objects, data, constraints, and smoke tests.
7. **Deploy application:** roll out the application version compatible with the updated schema.
8. **Observe:** monitor SQL errors, response times, locks, sessions, and database metrics post-release.

Avoid letting every application instance run migrations at startup if a dedicated deployment job can be used. Multiple pods starting concurrently can cause contention, obscure failures, and tie application startup time to schema changes. Even when tools use locking, a separate migration job provides cleaner ordering between database and application releases.

In production, run preflight checks on backups, capacity, privileges, lock durations, current load, and maintenance windows. For changes risking large table locks, test on a clone with near-realistic data and agree on stop/go criteria.

## 9. Onboarding an Existing Database into Migration History

Many Oracle systems already have schemas before adopting Flyway or Liquibase. You cannot simply run all historical migrations against such a schema because objects already exist.

In Flyway, baseline marks a starting version for an existing schema. In Liquibase, `changelogSync` marks matching changesets as executed without running their SQL. Both actions are only safe after reconciling the current schema against the state represented by that baseline.

Process for onboarding a legacy schema:

1. Back up or clone the database for comparison and recovery.
2. Export an inventory of objects, DDL, constraints, indexes, sequences, packages, grants, and synonyms.
3. Determine the logical version of the current schema.
4. Reconcile the actual schema against the expected post-migration state.
5. Select the baseline version or set of changesets to sync.
6. Run validate/status and test subsequent migrations on a clone.
7. Only after confirming results apply the baseline metadata to the live environment.

Do not use `baselineOnMigrate` or `changelogSync` to skip over an unverified schema. Marking migrations as applied only updates history; it does not create missing objects or fix incorrect definitions.

## 10. Handling Failed Migrations in Oracle

When a migration fails, do not immediately re-run it and do not drop the history table. First determine:

- Did the tool record the migration as succeeded, failed, or not yet recorded?
- Which statements ran before the failure?
- Which objects were committed by DDL?
- Which DML committed and which can still be rolled back?
- Do existing objects match their intended definitions?
- Is another migration session still holding a lock?

You can check for invalid objects:

```sql
SELECT owner,
       object_type,
       object_name,
       status
FROM all_objects
WHERE status = 'INVALID'
ORDER BY owner, object_type, object_name;
```

For invalid objects, inspect compile errors:

```sql
SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM all_errors
ORDER BY owner, name, type, sequence;
```

Depending on privileges, you may need `DBA_OBJECTS` and `DBA_ERRORS` to inspect the entire database. Do not treat a migration tool's success status as sole proof; objects may be invalid or data may fail business constraints.

A controlled recovery sequence:

1. Halt further deployments to avoid overlapping migrations.
2. Capture logs, metadata status, and the current object inventory.
3. Compare the schema against both pre-migration state and intended state.
4. Decide whether to fix forward via a new migration, run a controlled recovery script, or restore from backup.
5. Update Flyway/Liquibase metadata only after the actual schema has been reconciled.
6. Re-run validate/status, inspect invalid objects and constraints, and run application tests.

Flyway `repair` and Liquibase `clear-checksums` modify history/checksums, not DDL rollback. Liquibase `release-locks` should only be used after confirming no migration process is active. Never manually delete history tables to force a tool to re-run.

## 11. Change Control and Deployment Safety

### 11.1. Applied Migrations Are Immutable

Once a versioned migration or changeset has been applied in a shared environment:

- Do not edit old content to change the expected outcome.
- Create a subsequent migration to modify the schema or data.
- Keep migration source in the same repository and review workflow as the application.
- Verify checksums before release.
- Record who ran it, when, on which database, and with which artifact version.

Repeatable migrations and `runOnChange` changesets are intentional exceptions for source-replaced objects. Even then, control content changes, dependencies, and re-execution impact.

### 11.2. Do Not Use Migrations for Every Operational Task

Not every database operation belongs in a schema migration. Rebuilding indexes, gathering statistics, purging old data, backfilling millions of rows, or changing instance parameters may need separate operational procedures. Putting them inside synchronous deployments makes deploy durations unpredictable or introduces prolonged locks.

If automation is required, separate operational steps from schema steps with timeouts, logging, checkpoints, monitoring, and resumability. Never let a migration hold transactions or sessions longer than necessary.

### 11.3. Securing Migration Accounts

The migration account needs enough privileges to create/alter application objects, but should not use `SYS` or `SYSTEM` for application schema changes. Separate user/tablespace administration from schema deployment privileges where architecture permits. Never grant broad privileges to `PUBLIC`; store secrets in a secret manager and rotate them per policy.

The application runtime account typically only needs required DML and execute privileges. Do not use a migration account with broad DDL privileges as the application's regular connection account.

## 12. Common Design Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Editing an already-executed versioned migration | Checksum mismatch across environments | Create a new migration to apply fixes |
| Treating Oracle DDL as transactionally rollbackable | Schema left with partially created objects | Track each DDL statement and prepare forward-fix/restore |
| Creating packages before required tables or grants | Invalid packages or compile failures | Order migrations by dependency graph |
| Sending `/` as a JDBC SQL statement | Parser or driver rejects the script | Configure delimiters per tool and send PL/SQL cleanly |
| Full-table backfill during deploy | Lock duration, redo/undo, and load spikes | Split into checkpointed batch jobs |
| Running migrations from every app instance | Hard to control concurrency and startup failures | Use a dedicated migration job |
| Using `repair` to fix a partially built schema | Metadata changes while objects stay broken | Reconcile the schema first, then update history |
| Baselining an uninventoried schema | Skips missing objects or constraints | Diff actual DDL before baselining |
| Using two tools to manage one schema | Independent histories can conflict | Choose one source of truth per schema |
| Using `MARK_RAN` or swallowing broad errors | History reports success despite broken schema | Halt deployment and address failed conditions explicitly |

## 13. Pre- and Post-Migration Checklists

**Before running**

- [ ] Confirmed target database, service, PDB, schema, and release.
- [ ] Pinned Flyway/Liquibase versions, Oracle JDBC driver, and parser settings.
- [ ] Checked migration versions, checksums, changelog order, and new files.
- [ ] Confirmed DDL privileges, quotas, tablespaces, and metadata permissions.
- [ ] Verified dependencies across tables, sequences, constraints, grants, synonyms, and PL/SQL.
- [ ] Tested migrations on a clone database matching production configuration.
- [ ] Reviewed planned SQL or execution logs and assessed lock durations.
- [ ] Prepared backup/restore or forward-fix plan tailored to the change.
- [ ] Confirmed only one migration job runs against the schema.

**After running**

- [ ] Tool recorded the expected applied versions/changesets.
- [ ] No unexpected pending migrations remain.
- [ ] Required objects exist and PL/SQL objects are valid.
- [ ] Constraints and indexes are in the expected state.
- [ ] Backfilled data and reference data are reconciled.
- [ ] Smoke tests and application integration tests pass.
- [ ] No stale migration locks or lingering deployment sessions remain.
- [ ] Migration logs and artifacts are archived alongside the application release.

## 14. Selection and Operational Principles

Flyway is a natural choice when teams want versioned SQL migrations, clear history, and a simple workflow. Liquibase fits when structured changelogs, preconditions, contexts/labels, and declared rollbacks are needed. Whichever tool you choose, maintain a single source of truth per schema, keep applied migrations immutable, and test all changes on an Oracle database matching your target environment.

For Oracle, migration order must reflect object dependencies and DDL's implicit commit behavior. Build foundational structures first, followed by constraints, reference data, grants, views, and PL/SQL according to dependencies; separate large backfills from schema deployment steps; and finally verify metadata, invalid objects, data, and the application. A migration marked successful is only partial proof: the actual schema must always be verified before proceeding with the next release.

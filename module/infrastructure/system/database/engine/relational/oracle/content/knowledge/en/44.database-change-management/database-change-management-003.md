# Deployment Locks, Migration History, and Schema Drift Detection

In an application backed by Oracle Database, the schema evolves with every application release: adding tables, columns, indexes, constraints, sequences, packages, views, or modifying seed/reference data. When multiple application servers or pipelines deploy concurrently, these changes must be coordinated to prevent two processes from running migrations at the same time, running out of order, or recording history that does not match the actual database structure.

Three mechanisms must be managed separately yet coordinated closely:

- **Migration lock** ensures only one process can modify the schema within the same scope at a given time.
- **Migration history** records which migrations have run, along with their version, checksum, timestamp, and execution status.
- **Schema drift detection** compares the actual database structure against the expected state from migrations or a reference model to uncover out-of-band changes.

Migration history answers "which changes has the tool recorded?" Drift detection answers "does the current schema still match the expected state?" These are distinct questions: a migration can be recorded as successful, yet a DBA may still manually edit the schema afterward. In that case, history does not change, but the schema has drifted.

## 1. Migrations and Expected Schema State

A database migration is a versioned change described in SQL or migration configuration. Each migration should have a clear goal and be stored in source control alongside application code.

Example of a migration adding a processing status column:

~~~sql
ALTER TABLE orders
  ADD processing_status VARCHAR2(20);
~~~

The next migration creates an index:

~~~sql
CREATE INDEX ix_orders_processing_status
  ON orders(processing_status);
~~~

When migrations are applied sequentially, the schema transitions from its initial state to the new state. The set of version-controlled migrations serves as the specification for building the expected schema.

A typical pipeline:

~~~text
Source control
    |
    | migration scripts + application code
    v
CI validation
    |
    | check syntax, checksums, dependencies
    v
Deployment coordinator
    |
    | acquire migration lock
    v
Oracle Database
    |
    | apply migrations in order
    | record migration history
    v
Post-deployment verification
    |
    | validate history and schema
    v
Release complete
~~~

Migration scripts should not be treated as ad-hoc SQL commands run manually. Migrations must be reviewed, tested on a comparable database, committed to the repository, and deployed via a reproducible workflow.

### Versioned Migrations vs. Repeatable Migrations

Tools like Flyway and Liquibase support different ways of describing migrations.

- **Versioned migrations** have a unique version or identifier, execute in order, and are typically applied once per database/schema.
- **Repeatable migrations** are re-executed when their content changes according to the tool's checksum or change rules. Commonly used for views, packages, or objects kept in sync with source definitions.

Example Flyway filenames:

~~~text
V001__create_customer_table.sql
V002__add_customer_status.sql
V003__create_order_index.sql
R__refresh_reporting_views.sql
~~~

`V` denotes a versioned migration; `R` denotes a repeatable migration by Flyway convention. Exact naming and rules must follow the project's Flyway configuration.

In Liquibase, a changeset has an `author` and `id` unique within the changelog scope, for example:

~~~xml
<changeSet id="2026-11-14-001" author="db-team">
    <createTable tableName="CUSTOMER">
        <column name="CUSTOMER_ID" type="NUMBER(19)">
            <constraints primaryKey="true" nullable="false"/>
        </column>
        <column name="STATUS" type="VARCHAR2(20)"/>
    </createTable>
</changeSet>
~~~

Do not edit the content of an already-applied migration just to make the current file resemble the schema. Create a new migration to update the database state. For deployed migrations, altering history or checksums destroys reproducibility and masks discrepancies.

## 2. What Problems Do Migration Locks Solve?

Suppose two pipelines, A and B, deploy to the same database concurrently:

1. A reads history and sees migration V010 has not run.
2. B also reads history and sees V010 has not run.
3. A begins executing V010.
4. B also begins executing V010.
5. Both may try to create the same objects, alter the same table, or write to migration history simultaneously.

The result can be "object already exists" errors, inconsistent history state, partially executed DDL, or mid-deployment failures.

A migration lock establishes a shared coordination point so only one runner has permission to alter the schema within the protected scope. Other runners must wait, abort, or fail according to policy.

~~~text
             Pipeline A              Pipeline B
                 |                        |
                 | acquire lock           | acquire lock
                 v                        v
          +----------------+      +----------------+
          | Lock available?|      | Lock available?|
          +-------+--------+      +-------+--------+
                  |                       |
               granted                 waiting
                  |                       |
                  v                       |
          Run migrations                  |
                  |                       |
          Validate schema                 |
                  |                       |
             release lock                 |
                  |                       v
                  +----------------> acquire lock
                                          |
                                      Run/check
                                          |
                                      release lock
~~~

The lock must be shared across all runners that can modify the same schema. An in-memory pipeline variable, an in-JVM mutex, or a local file lock on one build agent is insufficient when another pipeline runs on a different host.

### Lock Scope

You must decide at what granularity the lock applies:

- A database.
- A schema/owner.
- A group of schemas migrated together.
- A release spanning schemas with cross-dependencies.

If an application uses multiple schemas, two independent migrations can run in parallel when there are no object dependencies or shared resources. However, if a release modifies cross-schema foreign keys, synonyms, packages, or grants, use a single shared lock for the entire deployment unit.

Avoid locking too broadly for long durations if scopes can be safely separated, as overly coarse locks reduce deployment parallelism. Conversely, locking too narrowly can allow two runners to modify interdependent objects simultaneously.

## 3. How to Implement Migration Locks

There are two common approaches:

1. Use the locking mechanism provided by the migration framework.
2. Use a custom lock managed by the deployment system when coordinating multiple tools or multiple schemas.

Prefer the framework's built-in lock when all migrations run through the same framework and a supported version. Only add a custom lock when there is a clear coordination need; avoid creating two competing lock mechanisms or deadlocks.

### Liquibase DATABASECHANGELOGLOCK

Liquibase uses the `DATABASECHANGELOGLOCK` table to prevent multiple Liquibase processes from updating the changelog simultaneously on one database. This table stores lock status and holder details according to the Liquibase version's mechanism.

Common commands:

~~~bash
liquibase status
liquibase update
liquibase release-locks
~~~

- `status` shows which changesets are still pending.
- `update` applies changesets according to the changelog.
- `release-locks` releases the lock when handling a stale lock left behind after an incident.

Do not run `release-locks` habitually just because a pipeline is waiting. Before releasing a lock, verify that the previous Liquibase process has terminated and no migration is still running. If the old runner is still active, releasing the lock lets a second runner mutate the schema concurrently.

You can inspect the lock table:

~~~sql
SELECT id,
       locked,
       lockgranted,
       lockedby
FROM databasechangeloglock;
~~~

The schema holding the table depends on Liquibase configuration. The deployment account must have read/write access on the lock table and privileges to execute the required DDL.

### Flyway and Migration Coordination

Flyway stores migration history in the schema history table, defaulting typically to `flyway_schema_history`. Flyway manages migration execution and coordinates runners using a locking mechanism suited to the database and Flyway version.

Common commands:

~~~bash
flyway info
flyway validate
flyway migrate
~~~

- `info` displays migration status and history.
- `validate` checks applied migrations against available migrations, including checksums and metadata per Flyway rules.
- `migrate` applies pending migrations.

Do not assume you can add a custom lock table to replace Flyway's internal lock. When using Flyway, let the framework coordinate migrations and never run parallel SQL migrations with another tool without a shared lock.

### Custom Locking in Oracle Using DBMS_LOCK

When using a custom deployment coordinator or synchronizing multi-step schema changes outside a framework, Oracle provides `DBMS_LOCK` to acquire application locks. `DBMS_LOCK` lets multiple sessions coordinate on a lock name/id.

Conceptual example:

~~~sql
DECLARE
  l_lockhandle VARCHAR2(128);
  l_result     INTEGER;
BEGIN
  DBMS_LOCK.ALLOCATE_UNIQUE(
    lockname   => 'APP_SCHEMA_MIGRATION',
    lockhandle => l_lockhandle
  );

  l_result := DBMS_LOCK.REQUEST(
    lockhandle        => l_lockhandle,
    lockmode          => DBMS_LOCK.X_MODE,
    timeout           => 300,
    release_on_commit => FALSE
  );

  IF l_result <> 0 THEN
    RAISE_APPLICATION_ERROR(
      -20001,
      'Cannot acquire migration lock, result=' || l_result
    );
  END IF;

  -- Execute migration orchestration steps here.

  l_result := DBMS_LOCK.RELEASE(l_lockhandle);
END;
/
~~~

This example illustrates the API; production implementations need exception handling to always release the lock on error. Note that `DBMS_LOCK.ALLOCATE_UNIQUE` can commit the current transaction; call it only in a dedicated deployment session after prior business changes have been intentionally committed or rolled back. `DBMS_LOCK` may require `EXECUTE` privilege granted directly to the executing user; privileges granted solely via roles may be insufficient in certain stored PL/SQL contexts.

Key notes:

- `X_MODE` is an exclusive lock, held by only one session within the same lock scope.
- `timeout` limits how long to wait.
- `release_on_commit` controls whether the lock is released when a transaction commits.
- Oracle DDL performs implicit commits, so do not rely on transaction rollback to release application locks if the lock is not tied to commit behavior.
- If a session dies, Oracle cleans up session-owned locks per database rules; the coordinator still needs timeouts and runner health checks.

`DBMS_LOCK` is a session synchronization primitive, not a migration framework. It does not check versions, checksums, dependencies, or record migration history.

## 4. Lock Timeouts, Stale Locks, and Incident Recovery

A migration runner can be killed, lose connectivity, or have its host restarted. Distinguish between:

- A lock still actively held by a live database session.
- Lock metadata still marked locked while its owning session has died.
- A runner still executing while the pipeline lost connection to it.
- A migration that completed its DDL but has not finished writing history.

Never conclude a lock is stale based solely on how long it has been held. A large migration may legitimately run longer than expected. Cross-check the OS/pipeline process, database session, currently executing SQL, migration logs, and DDL state.

### Procedure for Handling a Stuck Lock

1. Identify the framework and database/schema protected by the lock.
2. Inspect the lock table or session info per framework guidelines.
3. Check whether the pipeline/agent holding the lock is still running.
4. Inspect the Oracle session, active SQL, and wait events if permitted.
5. Confirm the migration is no longer active and assess the database state.
6. Use the framework's official release-lock command or release the application lock via the corresponding API.
7. Run validate/status to determine which migrations were recorded.
8. Inspect the actual schema before re-running migrations.

Never delete rows directly from `DATABASECHANGELOGLOCK` or arbitrarily update the `LOCKED` column with raw SQL. Use the framework's API to avoid corrupting internal state or releasing a lock while another runner is still active.

### Timeouts and Retries

A runner waiting for a lock should have a finite timeout. If the timeout expires, the pipeline should clearly report that another migration holds the lock, including the database/schema and wait start time. Retries should use backoff so multiple pipelines do not continuously contend for the lock.

When a migration may run long, base the lock timeout on realistic execution durations and deployment windows. Do not set an overly short timeout and auto-release the lock. Timing out only means this runner failed to acquire the lock; it does not mean the lock holder failed.

## 5. What Does Migration History Store?

Migration history is a tool-managed metadata table tracking how far the database has been updated. It is the source the framework uses to decide which migrations are pending, applied, or require verification.

### Flyway Schema History

Flyway records fields such as version, description, type, script, checksum, execution timestamp, success flag, and execution duration. The default table name is usually `flyway_schema_history`, though it is configurable.

Example query:

~~~sql
SELECT installed_rank,
       version,
       description,
       type,
       script,
       checksum,
       installed_on,
       execution_time,
       success
FROM flyway_schema_history
ORDER BY installed_rank;
~~~

Column layouts can vary by Flyway version and configuration. Check your actual schema history table before writing fixed monitoring queries.

### Liquibase DATABASECHANGELOG

Liquibase records executed changesets in `DATABASECHANGELOG`. Common columns include `ID`, `AUTHOR`, `FILENAME`, `DATEEXECUTED`, `ORDEREXECUTED`, `EXECTYPE`, `MD5SUM`, `DESCRIPTION`, and `LIQUIBASE`.

Example:

~~~sql
SELECT id,
       author,
       filename,
       dateexecuted,
       orderexecuted,
       exectype,
       md5sum,
       description
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Changesets are identified by a composite key including id, author, and changelog path. Checksums detect when an already-applied changeset's content has been altered relative to the current definition per Liquibase rules.

### History Is Not a Schema Snapshot

Migration history tells you what the tool recorded, not the complete current definition of every database object. It does not prove that:

- A DBA has not manually altered a table.
- An index has not been dropped.
- Grants have not been changed.
- A package body has not been edited.
- A constraint has not been disabled.
- Extra objects have not been created outside migrations.
- Session/database settings have not altered migration behavior.

Therefore, combine history checks with schema comparison or targeted object inspection.

## 6. Checksums and Validating Migration History

A checksum is a digest generated from the contents of a migration or changeset. If an already-applied migration file is edited, the current checksum will differ from the checksum stored in history.

This detects when an old migration was altered after deployment. For example:

1. V005 is applied to production.
2. History stores the checksum of V005's content at execution time.
3. A developer edits V005 on a branch to rename a column.
4. The pipeline runs validate.
5. The tool detects a checksum mismatch.

This is a signal to investigate. Never manually edit the history checksum just to turn the pipeline green. If a schema change is needed, create a new migration, such as V006, to transition from the current state to the desired state.

### Flyway validate

~~~bash
flyway validate
~~~

Validate checks whether applied migrations match the migrations available in the current configuration per Flyway rules. It catches issues such as checksum mismatches, missing migrations, or inconsistent metadata.

Validate is not a full comparison of the Oracle schema against a reference model. A DBA can manually add a column and `flyway validate` will still succeed as long as history and migration files are unchanged.

### Liquibase validate and Checksums

~~~bash
liquibase validate
liquibase status
~~~

`validate` checks changelog validity and verifiable Liquibase structures. Liquibase can also detect when an applied changeset's checksum no longer matches. However, `validate` does not replace a schema diff between the actual database and the expected baseline.

Commands like `repair`/`clear-checksums` may be used in controlled situations, but they are not normal ways to handle edited migrations. Before running them, understand which changes were applied, why the checksum changed, and how all environments are affected.

## 7. What Is Schema Drift?

Schema drift is the divergence between the current database structure and the structure expected by the chosen source of truth.

For example, a migration defines:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER(19) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    status VARCHAR2(20),
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
);
~~~

Later, a DBA adds a column outside migrations:

~~~sql
ALTER TABLE customers
  ADD legacy_flag CHAR(1);
~~~

If the `legacy_flag` column is not defined in migrations or the reference model, the database has drifted. History may still report all migrations succeeded because manual changes are not written to the history table.

### Common Forms of Drift

| Drift Type | Example | Consequence |
|---|---|---|
| Out-of-band object | Manually created table, view, or sequence | Environments have divergent schemas |
| Missing object | Dropped index or constraint | Degraded performance or data integrity |
| Altered definition | Changed VARCHAR2 length, precision, or nullability | Read/write errors or changed behavior |
| Modified object | Edited package, trigger, or view body | Production logic diverges from source control |
| Divergent privileges | Out-of-band grant/revoke | Permission errors or data exposure |
| Altered state | Disabled constraint, unusable index | Changed enforcement or execution plans |
| Storage/partition changes | Different tablespace, partition, or logging attributes | Inconsistent operations and performance |

Not every metadata difference is drift that needs fixing. Some attributes are auto-tuned by Oracle or intentionally vary by environment, such as tablespaces, storage clauses, statistics, or physical layout. Define a baseline and an allowlist for acceptable differences.

### Schema Drift vs. Data Drift

Schema drift refers to structural changes such as tables, columns, indexes, constraints, packages, or grants. Data drift refers to business data diverging from expectations, such as row counts, reference values, or cross-system sync state.

Migration history and schema diffs focus on schema. Detecting data drift requires separate rules such as row counts, data checksums, referential integrity checks, or business reconciliation.

## 8. Defining the Schema Source of Truth

To detect drift, you must first define what the canonical state is. You can use one or a combination of sources:

- **Versioned migration scripts** in source control.
- **Liquibase changelog** or **Flyway migration history**.
- **DDL baseline** exported from a reviewed reference database.
- **JPA entity model** for the subset of schema managed by the ORM.
- **Database object scripts** for packages, views, triggers, synonyms, grants, and objects outside the JPA model.

Do not use the JPA entity model as the sole source of truth if the application also relies on PL/SQL objects, materialized views, partitions, function-based indexes, or database privileges. Hibernate schema validation primarily checks entity mappings against relevant tables/columns; it does not validate all database objects.

A practical rule is that migration scripts define versioned changes; a DDL baseline serves as a reference; and the application model is only a supplementary check for entity mappings.

### Distinguishing Acceptable Drift from Unintended Drift

For example, each environment may use a different tablespace while maintaining the same logical structure. Comparing raw DDL would report differences. Normalize or exclude physical attributes according to policy.

Conversely, do not ignore differences in nullability, data types, precision, constraints, or indexes just because they do not break migrations immediately. Such differences can cause edge-case data failures or performance regressions.

Maintain an explicit list covering:

- Attributes that must be identical across all environments.
- Attributes permitted to vary by environment.
- Auto-generated or Oracle-managed objects.
- Temporary objects to exclude from comparison.
- Schemas/owners included in inspection scope.

## 9. Detecting Drift with Liquibase Diff

Liquibase can compare a database against a reference database or configured changelog/model. Common commands:

~~~bash
liquibase diff
liquibase diff-changelog
~~~

- `diff` reports differences between reference and target.
- `diff-changelog` generates a changelog describing detected differences for review.

Conceptual example: DEV database is the reference, TEST database is the target. If TEST is missing an index or has an extra column, `diff` surfaces those differences within the scope of objects Liquibase supports and is configured to inspect.

Clearly specify reference URL/schema and target URL/schema. Never run diff in the wrong direction and auto-generate a changelog to apply. Generated diff files are change proposals requiring review because they may contain physical differences that should not enter migrations.

Certain Liquibase behaviors depend on the version and snapshot/reference configuration. Consult documentation matching your exact Liquibase version and Oracle extensions if applicable.

### Diffing Two Databases

Illustrative command using a properties file to avoid passing passwords on the command line:

~~~bash
liquibase --defaults-file=liquibase-dev.properties diff
~~~

The properties file specifies reference and target settings per Liquibase version, such as URL, username, schema, and driver. Protect credential files using a secret manager or secure mechanism; never commit passwords to source control.

### Diff Changelog and Review

~~~bash
liquibase --defaults-file=liquibase-diff.properties diff-changelog
~~~

`diff-changelog` output can serve as a starting point for a new migration, but must be reviewed:

- Which objects genuinely belong in source control?
- Are any differences purely storage/environment-specific?
- Will dropping/altering cause data loss?
- Is data backfilling needed before adding NOT NULL or constraints?
- Are there object dependencies or deployment ordering constraints?
- Is it compatible with running application versions?

Never automatically apply all diff results to production. Drift could be an intentional emergency change, a mistake, or an Oracle-generated object tied to environment configuration.

## 10. Detecting Drift Using Oracle DDL and Data Dictionary

You can use `DBMS_METADATA` to extract actual object DDL. Example:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'TABLE',
         'CUSTOMERS',
         'APP'
       )
FROM dual;
~~~

Extract index DDL:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'INDEX',
         'IX_CUSTOMERS_STATUS',
         'APP'
       )
FROM dual;
~~~

Extract package DDL:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'PACKAGE',
         'ORDER_API',
         'APP'
       )
FROM dual;
~~~

For package bodies, use the appropriate object type:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
         'PACKAGE_BODY',
         'ORDER_API',
         'APP'
       )
FROM dual;
~~~

`DBMS_METADATA` output can vary by privileges, transform parameters, database version, and selected attributes. Returned DDL may include environment-specific tablespace or storage clauses; normalize it before comparison.

### Inspecting Tables and Columns

~~~sql
SELECT owner,
       table_name,
       column_id,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM all_tab_columns
WHERE owner = 'APP'
ORDER BY table_name, column_id;
~~~

### Inspecting Indexes

~~~sql
SELECT owner,
       index_name,
       table_name,
       uniqueness,
       status,
       visibility
FROM all_indexes
WHERE owner = 'APP'
ORDER BY table_name, index_name;
~~~

### Inspecting Constraints

~~~sql
SELECT owner,
       constraint_name,
       table_name,
       constraint_type,
       status,
       validated
FROM all_constraints
WHERE owner = 'APP'
ORDER BY table_name, constraint_name;
~~~

### Inspecting Invalid Objects

~~~sql
SELECT owner,
       object_type,
       object_name,
       status
FROM all_objects
WHERE owner = 'APP'
  AND status <> 'VALID'
ORDER BY object_type, object_name;
~~~

### Inspecting Grants

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE owner = 'APP'
ORDER BY table_name, grantee, privilege;
~~~

`ALL_*` views show objects visible to the current user. DBAs can use `DBA_*` for broader visibility. To compare accurately, use the same owner, visibility privileges, and metadata version/configuration.

Never compare object counts alone. Two schemas with identical table counts can still differ in columns, constraints, indexes, triggers, or package bodies.

## 11. Detecting Schema Drift with Hibernate/JPA

Hibernate can validate part of the schema against entity mappings. In Spring Boot, the common property is:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

`validate` instructs Hibernate to verify entity-mapped schema structures at startup. If a table or column is missing or has an incompatible type within the provider's check scope, the application may fail to start.

Common values:

| Value | Behavior |
|---|---|
| none | Neither validates nor updates the schema automatically |
| validate | Validates mappings against the schema |
| update | Attempts to alter the schema to match mappings |
| create | Creates the schema at startup |
| create-drop | Creates the schema at startup and drops it on shutdown |

In production, use a migration tool for DDL and set `ddl-auto=validate` or `none` per policy. Avoid `update`/`create`/`create-drop` in production because the application could alter the schema outside migration history and deployment controls.

Hibernate `validate` is not a complete drift detector. It does not check all indexes, grants, triggers, packages, procedures, or objects outside entity mappings. Nor does it replace Liquibase diff or DDL inspection.

## 12. Handling Drift: Controlled Reconciliation

When drift is detected, do not immediately push `diff-changelog` to production. First determine the root cause and data state.

Recommended procedure:

1. **Freeze competing changes.** Stop or coordinate other migrations within the same scope.
2. **Gather evidence.** Collect migration history, deployment logs, actual DDL, object metadata, and change timestamps.
3. **Classify the drift.** Missing object, extra object, altered definition, altered privileges, or altered object status.
4. **Identify the source of change.** Migration, DBA intervention, emergency script, another tool, or automated action.
5. **Assess data impact.** Check for dependent data, disabled constraints, unusable indexes, or active packages used by the application.
6. **Establish the canonical state.** Decide whether the live schema or migration source control reflects the valid business requirement.
7. **Author a corrective migration.** If the database needs to return to baseline, write a new reviewable, reproducible migration.
8. **Test on a production-like clone.** Verify DDL, lock duration, data, rollback/forward recovery, and application compatibility.
9. **Apply under the migration lock.** Only one runner modifies the schema in scope.
10. **Re-run validate/diff.** Confirm drift is resolved and history is consistent.

If a manual change was a legitimate emergency hotfix applied in production, bring it back into source control using an equivalent migration or the framework's formal baseline/repair workflow. Never create a dummy migration just to mark state without verifying the database actually has the intended objects and data.

### Example: Column Created Manually in Production

Suppose a DBA added column `LEGACY_CODE` in production, but the migration repository lacks this change.

There are two options:

- If the column is no longer needed, create a migration with state checks and a safe drop plan after confirming no application uses it.
- If the column is a required business change to keep, create a migration describing it so other environments can reproduce it. Before applying, check that production already has the column to avoid "column already exists" errors; use preconditions or tool-supported adoption flows.

Do not edit an already-applied older migration to add the column. Creating a new migration keeps history accurately reflecting the change sequence.

## 13. Oracle DDL and Migration Transactionality

A critical difference in Oracle is that many DDL statements execute an implicit commit. Commands like `CREATE`, `ALTER`, and `DROP` generally commit the active transaction before running and commit upon successful completion per Oracle semantics.

This affects how migration frameworks manage transactions:

- Never assume a migration with multiple DDL statements can roll back completely like a normal DML transaction.
- If a migration executes partway and fails, preceding DDL statements may already be committed.
- The framework may record the migration as failed, yet the schema retains partial changes.
- Re-running the migration may hit "object already exists" errors or half-applied states.

Example:

~~~sql
ALTER TABLE customers ADD status VARCHAR2(20);
CREATE INDEX ix_customers_status ON customers(status);
~~~

If `ALTER TABLE` succeeds and `CREATE INDEX` fails, do not assume rollback removed the `status` column. Inspect the actual schema before fixing or re-running.

### Designing Safe Migrations for Oracle DDL

- Break large changes into small migrations with verifiable states.
- Use preconditions or existence-checking scripts before creating/dropping where supported by the tool.
- Avoid mixing DDL and DML in the same changeset if atomic rollback is expected.
- For large data backfills, separate them into DML jobs with dedicated batch/commit strategies.
- Log completed steps and failed steps clearly.
- Prepare forward-recovery migrations toward the desired state; do not assume automatic rollback is always possible.

Liquibase provides a `runInTransaction` attribute for changesets, but on Oracle DDL still performs implicit commits. Setting `runInTransaction=false` does not make DDL rollbackable; use it only when a changeset contains statements that cannot run inside a transaction or as required by the tool. Verify behavior on your exact version and design every changeset to be recoverable.

### Expand-and-Contract Deployment

For multi-instance applications that cannot stop all traffic during schema changes, use the expand-and-contract strategy:

1. **Expand**: add new columns/tables/indexes in a way compatible with older application versions.
2. **Deploy intermediate application**: code can read/write both old and new structures or dual-write during transition.
3. **Backfill**: migrate existing data in batches and verify results.
4. **Switch**: switch the application to use the new structure.
5. **Contract**: once all old instances are stopped and data is synced, drop the old structure in a separate migration.

Example adding a new column as nullable first:

~~~sql
ALTER TABLE customers
  ADD display_name VARCHAR2(200);
~~~

Then new application code writes `display_name` and data is backfilled. Only after confirming every code path uses the new column should you consider dropping the old column or enforcing required constraints.

Never drop or rename a column in the same release if old application instances are still running and accessing it. Migrations must be compatible across the rollout sequence, not just on the final schema.

## 14. Migration History and Deployment Auditing

Framework migration history is a technical record. For operations and auditing, supplement it with deployment metadata in the pipeline or change management system:

- Release/application version.
- Commit SHA or build artifact.
- Database unique name and schema/owner.
- Migration tool and version.
- User or service account that triggered the run.
- Start/end timestamps.
- Applied migration versions/changesets.
- Outcomes and errors.
- Ticket/change request and deployment window.
- Post-migration validate/diff evidence.

It is not necessary to cram all metadata into framework-owned history tables. Store it in a dedicated audit/deployment system or pipeline artifact. Never arbitrarily add columns to Flyway/Liquibase tables if the framework does not support that schema.

### Querying Migration Status

For Flyway, query schema history:

~~~sql
SELECT version,
       description,
       script,
       installed_on,
       execution_time,
       success
FROM flyway_schema_history
ORDER BY installed_rank;
~~~

For Liquibase:

~~~sql
SELECT id,
       author,
       filename,
       dateexecuted,
       exectype,
       md5sum
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Audit read accounts should have only necessary privileges. Avoid giving the runtime application privileges to modify or drop history tables. Repair/baseline operations must be performed by controlled deployment accounts.

## 15. Deployment Pipeline with Locks, History, and Drift Checks

A database deployment pipeline can consist of these stages:

~~~text
1. Build
   - package migrations
   - record commit/build identity
          |
          v
2. Static validation
   - check migration names/versions
   - validate changelog and checksums
          |
          v
3. Acquire migration lock
   - wait or fail if lock is held
          |
          v
4. Pre-deployment inspection
   - verify database/schema/version
   - read migration history
   - detect critical drift
          |
          v
5. Apply migration
   - execute in order
   - record history
   - save logs
          |
          v
6. Post-deployment verification
   - validate migration history
   - schema diff/metadata checks
   - check invalid objects
          |
          v
7. Release lock
          |
          v
8. Deploy/enable application
   - smoke tests
   - monitor errors and performance
~~~

Include a cleanup branch to release the lock if a job fails, but only release the lock actually owned by the current runner. If a pipeline is killed abruptly, the framework or database session mechanism must manage lock cleanup; shell cleanup steps cannot be treated as the sole guarantee.

### Separating Migrations from Each Application Instance

Do not let every Spring Boot instance run migrations on startup when running multiple replicas and parallel deployments without proper locking. Use a dedicated migration job in the pipeline, then roll out the application. This clarifies migration ownership, deployment timing, and audit logs.

If startup auto-migration is still used, confirm the framework uses a shared lock, migrations are appropriately idempotent, and concurrent startups do not create race conditions. For production, a dedicated deployment job is usually easier to control.

## 16. Common Pitfalls

- **Checking only history and assuming the schema is right.** History does not catch manual changes made after migrations.
- **Editing an already-applied migration file.** Causes checksum mismatches and breaks reproducibility. Create a new migration.
- **Manually deleting locks while a pipeline is waiting.** The old runner may still be running DDL. Verify the owner before releasing.
- **Using an in-memory lock on a single build agent.** Pipelines on other hosts will not see that lock.
- **Using a lock with an unclear scope.** Can either permit conflicting edits or needlessly block independent migrations.
- **Building a custom lock without timeouts/recovery.** A crashed runner can leave a hard-to-recover lock state.
- **Believing Oracle DDL rollbacks always restore the schema.** DDL usually implicit-commits; inspect state after errors.
- **Auto-applying diff results to production.** Diffs can contain unintended changes or environment-specific physical attributes.
- **Using Hibernate `ddl-auto=update` as a migration tool.** Mutates schema outside migration history and review.
- **Comparing raw DDL across differently configured environments.** Tablespaces, storage clauses, or environment settings create false positives.
- **Failing to check invalid objects after DDL.** Dependent packages/views can turn `INVALID` and break the application.
- **Dropping/renaming objects while old code still runs.** Rolling deployments may leave instances querying deleted objects.
- **Checking drift only at release time.** Manual changes can occur later; schedule periodic checks and DDL auditing.

## 17. Recommended Operational Process

1. **Store migrations in source control.** Every change has a unique ID, clear description, and review.
2. **Choose one primary migration framework.** Avoid multiple tools altering the same schema without shared coordination.
3. **Use a shared lock.** Across all runners capable of modifying the same schema scope.
4. **Never edit applied migrations.** Create new migrations or use controlled baseline/repair procedures.
5. **Maintain history and deployment audit logs.** Tie migrations to releases, commits, and change requests.
6. **Validate before and after migrations.** Check checksums, pending status, and history errors.
7. **Compare actual schemas.** Use Liquibase diff, DDL metadata, or baseline object checks.
8. **Define an environment allowlist.** Distinguish permitted physical differences from logical structures that must stay uniform.
9. **Design for Oracle DDL.** Assume implicit commits and plan how to resume after partial migration runs.
10. **Use expand-and-contract.** Maintain compatibility between the schema and multiple application versions during rolling deployments.
11. **Check invalid objects and privileges.** Especially packages, views, triggers, constraints, indexes, and grants.
12. **Rehearse recovery.** Test scenarios for lock timeouts, crashed runners, partial DDL runs, and checksum mismatches.

## 18. Checklist for a Database Release

- [ ] New migrations have unique versions/ids and have been reviewed.
- [ ] Migrations were tested on a comparable Oracle version and configuration.
- [ ] No unauthorized edits were made to already-applied migrations.
- [ ] Runner has least-privilege permissions via a dedicated deployment account.
- [ ] Migration lock is held by the correct runner.
- [ ] No other migration is running against the same scope.
- [ ] Pre-deployment history was recorded.
- [ ] Pre-deployment schema drift was triaged.
- [ ] Backup/recovery point appropriate to the risk level was verified.
- [ ] DDL is designed to handle implicit commits and partial failures.
- [ ] Deployment order is compatible with running application versions.
- [ ] Post-checks confirmed migration history and object metadata.
- [ ] No critical objects are `INVALID` or indexes unexpectedly `UNUSABLE`.
- [ ] Lock was released by the rightful owner.
- [ ] Logs, commit/build identity, and deployment results are archived for audit.

Migration locks protect the sequential order of schema changes; migration history records which versioned changes were applied; drift detection verifies whether the live database still matches the canonical state. Combining all three with compatible rollout patterns and clear recovery procedures keeps Oracle schemas consistent across environments and reduces risk when multiple pipelines or DBAs modify the database.

# Putting Database Schema Changes into the Versioning Process

Database schemas change alongside the application: adding tables, columns, indexes, constraints, views, stored procedures, or adjusting data types. If these changes are only applied manually per environment, it becomes difficult for the team to know which environment has which structure, when a change was applied, and which application version requires that structure.

Putting schema changes under version control means storing migrations as source code, reviewing them alongside application changes, testing them in CI, and applying them in a controlled manner across environments. Each change has an identifier, order, execution history, and evidence. As a result, the database becomes part of the software delivery pipeline rather than an operational step sitting outside it.

## 1. Why do schema changes need to be version-controlled?

A database change can affect existing data, multiple application versions, and shared accessing services. Running a DDL statement directly in production without managed migrations creates a gap between the actual structure and the structure in the repository.

Managing migrations in Git provides the following benefits:

- **History:** know which change was added, who reviewed it, and why.
- **Reproducibility:** stand up a new database following the exact same sequence of migrations.
- **Testing:** verify migrations against an ephemeral database before release.
- **Traceability:** link a schema version to a commit, artifact, and deployment run.
- **Control:** review SQL, execution privileges, locks, and data impact.
- **Recovery:** plan roll-forward or recovery according to a prepared strategy.
- **Environment consistency:** reduce differences across development, test, staging, and production.

For example, application version 2.8 needs a new `payment_method` column. If the migration is not in the repository, one environment might have had the column added manually while another does not. Deploying the same artifact will then behave differently depending on the database.

## 2. What is a migration and what types of changes does it include?

A migration is a database change described by a file or changeset with an identifier and execution order. The migration tool reads these definitions, determines which changes have already been applied, and runs the remaining ones.

Common types of changes:

| Type | Example | Risks to consider |
|---|---|---|
| Schema DDL | CREATE TABLE, ALTER TABLE, DROP COLUMN | Locks, execution time, application compatibility |
| Index | CREATE INDEX, modifying an index | CPU/I/O load, locks, and build time |
| Constraint | NOT NULL, UNIQUE, FOREIGN KEY | Whether existing data violates the constraint |
| View/procedure | CREATE VIEW, function, trigger | Changes in query or write behavior |
| Data migration | Value normalization, backfilling a new column | Duration, idempotency, and resumability |
| Reference data | Status catalogs, transaction types | Cross-environment synchronization and version-specific changes |
| Permission | GRANT/REVOKE | Privilege scope and runtime impact |

Schema migrations should be distinguished from business data. User-generated data is not something that can be recreated by re-running all migrations. Data migrations must be designed carefully with checkpoints, batching, and handling for interrupted runs.

## 3. Storing migrations in the repository

Migrations should live in a stable directory, close to the database configuration or the module that owns the schema. For example, in a Java project using Flyway:

~~~text
payments-service/
├── src/
│   └── main/
│       └── resources/
│           └── db/
│               └── migration/
│                   ├── V1__create_payment_table.sql
│                   ├── V2__add_payment_method.sql
│                   └── V3__add_payment_status_index.sql
├── src/test/
├── pom.xml
└── .github/
    └── workflows/
        └── ci.yml
~~~

File names must follow the tool's conventions. With Flyway, versioned migrations typically follow the form `V<version>__<description>.sql`. The version number determines the order; the description helps readers understand the intent.

A small migration should represent one meaningful change. Do not bundle unrelated changes into a single large file because it is hard to review and hard to pinpoint the failing part. Conversely, you do not need a separate migration for every single statement if they always need to be applied together.

For example:

~~~sql
-- V1__create_payment_table.sql
CREATE TABLE payment (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

~~~sql
-- V2__add_payment_method.sql
ALTER TABLE payment
    ADD COLUMN payment_method VARCHAR(40);
~~~

The second migration adds a nullable column so the older application version can continue writing data. Adding `NOT NULL` immediately without an appropriate default or backfill may fail on a table that already has data or incur heavy locking/resource costs.

## 4. Migrations must have clear versions and ordering

A database needs a migration history with a deterministic order. The tool usually creates a metadata table to store applied migrations, such as version, description, checksum, timestamp, and execution status.

With Flyway, the default history table is typically `flyway_schema_history`. With Liquibase, changelog history is recorded in tables such as `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`.

Key principles:

- Every versioned migration has a unique identifier within the schema/database scope managed by the tool.
- A new version must be greater than already applied versions.
- Do not modify the content of a migration that has already run on a shared environment.
- Do not reuse an existing version.
- Dependent migrations must have a clear order.
- A commit containing a migration must be reviewed together with the related application changes.

If two development branches both create migration version `V12`, a conflict can occur upon merge. The team needs a version allocation convention, pre-merge duplicate checks, and must assign the next version to the migration added later. Never resolve this by silently modifying the content of a migration already applied in another environment.

## 5. Use a migration tool instead of running SQL manually

You can write custom SQL scripts and deployment commands, but when a system has multiple environments and frequent releases, a migration tool helps manage history and ordering consistently.

Some common options:

| Tool | How migrations are defined | Notable points |
|---|---|---|
| Flyway | SQL versioned/repeatable migrations or Java migrations | Clear version conventions, checksums, and history |
| Liquibase | XML, YAML, JSON, or SQL changelogs | Changesets with id, author, context, and preconditions |
| Rails Active Record Migrations | Ruby migrations | Tightly integrated with the Rails ecosystem |
| Django migrations | Python migration files | Tracks dependencies between apps and migrations |
| Alembic | Python migrations for SQLAlchemy | Supports revisions and a dependency graph |

Choose one tool as the primary execution source for a schema. Do not let both Flyway and Liquibase manage the same set of changes without a clear coordination design, as the two histories may not reflect the same state.

### 5.1. Flyway example

With Flyway, a typical structure looks like:

~~~text
src/main/resources/db/migration/
├── V1__create_payment_table.sql
├── V2__add_payment_method.sql
├── V3__add_status_index.sql
└── R__refresh_payment_summary_view.sql
~~~

- Versioned migrations start with `V`, are executed in version order, and are recorded in history.
- Repeatable migrations start with `R`, are re-run whenever their checksum changes, and are typically used for views or procedures whose definitions need to stay synchronized.
- Baseline is used in some cases when adopting Flyway on an existing database; the actual schema must be verified before baselining.

Repeatable migrations should not be used in place of all schema changes. Changes that require sequential history and must not be arbitrarily re-run should use versioned migrations.

### 5.2. Liquibase example

A Liquibase changeset can declare an identifier and a change:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261118-01
      author: payments-team
      changes:
        - addColumn:
            tableName: payment
            columns:
              - column:
                  name: payment_method
                  type: varchar(40)
                  constraints:
                    nullable: true
~~~

Liquibase identifies changesets by their identity fields and stores a checksum. You should not edit an already applied changeset and expect every environment to synchronize automatically. When further changes are needed, create a new changeset; if a checksum must be adjusted for a special reason, understand the impact thoroughly and follow a controlled process.

## 6. Do not modify an already applied migration

A migration that has run on a shared environment is part of the database history. If an old file is edited, the checksum may change and the tool will detect that the history no longer matches.

For example:

- `V1` already created the `payment` table in development and staging.
- The team discovers a need to add a `reference_code` column.
- Do not reopen `V1` to add the column.
- Create `V2__add_reference_code.sql` to describe the new change.

Benefits of this principle:

- Existing environments and new environments share the exact same historical sequence.
- Reviewers can read incremental changes over time.
- Avoids silent drift between databases.
- Easy to identify which migration introduced a change.

If a migration has never been applied to any shared environment and has not been released, the team can edit it on the working branch before merging according to the review process. Once a migration has been applied or becomes part of a release, treat it as immutable.

Do not run `repair` commands or directly edit the history table to mask a checksum mismatch without investigating first. Repair is only appropriate in well-understood situations with a backup and approval; it is not a substitute for restoring proper history.

## 7. Testing migrations in CI

Migrations need to be tested just like code. A pipeline should verify both the ability to create a fresh database and the ability to upgrade a database containing existing data and an older schema.

Typical verification layers include:

1. **Syntax/validation:** SQL files or changelogs are valid.
2. **Fresh database test:** run all migrations from an empty database.
3. **Upgrade test:** build the schema from an older version and upgrade to the new version.
4. **Data preservation test:** verify existing data is preserved and transformed accurately.
5. **Application compatibility test:** the target application version works with the post-migration schema.
6. **Performance check:** estimate the impact of DDL or backfills on sufficiently large data.
7. **Repeatability/consistency check:** verify migration history, checksums, and final state.

An ephemeral database can run in a container for each CI job. For example, integration tests start PostgreSQL, run Flyway, and then run application tests. The test database should match the production version closely to avoid syntax or behavioral differences.

Do not test only from an empty database. Many failures only surface when tables already hold data: adding constraints, changing types, creating unique indexes, or backfilling can fail due to legacy data.

## 8. Example migration testing pipeline with Maven and PostgreSQL

A Java workflow can start a PostgreSQL service, configure test connectivity, and run Maven `verify`. GitHub Actions example:

~~~yaml
name: Database migration CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-migration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: app_test
          POSTGRES_USER: app
          POSTGRES_PASSWORD: test-only-password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U app -d app_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Validate and run migration tests
        env:
          DB_URL: jdbc:postgresql://localhost:5432/app_test
          DB_USER: app
          DB_PASSWORD: test-only-password
        run: ./mvnw --batch-mode verify
~~~

The password in the example is strictly for the disposable database in CI; do not reuse it in other environments. In real projects, test configuration should be separated from production config, and real credentials must never be committed to the repository.

The `verify` command only truly tests migrations if the project has configured Flyway/Liquibase and integration tests to run them. The pipeline needs tests that validate the final schema, constraints, critical indexes, and application behavior; merely starting PostgreSQL is not enough to prove the migrations are correct.

## 9. Testing upgrades from an older schema and existing data

A migration might pass on an empty database yet fail during a production upgrade. Therefore, the pre-migration state must be simulated.

For example, adding a `normalized_email` column:

~~~sql
ALTER TABLE customer
    ADD COLUMN normalized_email VARCHAR(320);
~~~

Followed by backfilling data:

~~~sql
UPDATE customer
SET normalized_email = LOWER(TRIM(email))
WHERE normalized_email IS NULL;
~~~

If the table has tens of millions of rows, a single `UPDATE` statement can create a huge transaction, spike WAL/redo logs, cause locking, and increase replication lag. In such cases, use a batched backfill job with checkpoints, rate limiting, and resume-on-failure capability.

Upgrade tests should cover these cases:

- Empty table.
- Table with normal data.
- NULL values or anomalous data.
- Duplicate data when adding a unique constraint.
- Large tables or simulation of significant load.
- Older application version still running during rollout.
- Migration interrupted mid-way or safely re-executed.

Do not rely on just a few fixture rows to conclude a migration is safe on a large production table. Estimate scale, indexes, locks, and execution duration based on real database characteristics.

## 10. Designing migrations compatible with application versions

During rolling or blue/green deployments, old and new application versions may run simultaneously for a period of time. Migrations must keep the schema compatible with both versions during the transition window.

A breaking change can cause the old application to fail immediately once the migration completes. For example, dropping a column that the old version still reads is unsafe.

The **expand-and-contract** pattern helps reduce risk:

1. **Expand:** add new columns/tables in a backward-compatible way.
2. Deploy code that can read/write both old and new structures.
3. Backfill data into the new structure.
4. Switch the application to use the new structure.
5. Verify no remaining instances or consumers use the old structure.
6. **Contract:** drop the old column/table in a separate migration once rollback is no longer needed.

For example, renaming from the `full_name` column to `display_name`:

| Phase | Schema | Application |
|---|---|---|
| Initial | Has `full_name` | Old code reads/writes `full_name` |
| Expand | Add `display_name` | New code supports both |
| Backfill | Both columns hold data | Job copies old data to new |
| Cutover | Both columns still exist | New code prefers `display_name` |
| Contract | Drop `full_name` | Only after all consumers have switched |

Do not combine expand and contract into a single deployment if parallel execution must be maintained. Keeping the old structure around for a period of time is an intentional cost traded for safe deployment capability.

## 11. DDL can lock tables and cause downtime

Not all `ALTER TABLE` statements carry the same cost. Behavior depends on the database engine, version, table size, indexes, and type of change.

Operations that require careful evaluation:

- Adding a column with a default on a large table.
- Changing data type or collation.
- Adding `NOT NULL` or `CHECK` constraints.
- Creating a unique index on a table that already contains data.
- Dropping or renaming a column used by multiple application versions.
- Rebuilding indexes or modifying partitions.
- Backfilling millions of rows.

Some database engines support online or concurrent operations, though syntax and limitations vary. For example, PostgreSQL supports `CREATE INDEX CONCURRENTLY` with specific conditions and does not run inside a standard transaction block; MySQL has algorithms and lock modes depending on DDL type, storage engine, and version. Read the documentation for the exact database version in use and test on representative data.

Before applying a major migration, determine:

- What locks may be acquired and for how long.
- Whether running queries/writes will be impacted.
- Temporary disk space and I/O required.
- Replication lag and impact on replicas.
- Deployment window and timeouts.
- How to cancel or resume if the operation takes too long.

Do not execute a DDL statement capable of long table locks during peak hours without a plan and evidence of execution duration.

## 12. Managing batched and resumable data migrations

Data migrations differ from simple schema changes. A backfill can run for hours, process millions of rows, and be interrupted by deployments, timeouts, or infrastructure incidents.

A well-designed backfill job should:

- Partition data into batches by a stable key.
- Persist checkpoints or processed watermarks.
- Be re-runnable without producing incorrect results.
- Rate-limit execution to avoid overloading the database.
- Emit metrics for processed row counts, errors, and duration.
- Log how failed rows are handled.
- Allow safe stopping and resuming.
- Include a data verification step after completion.

Pseudocode example:

~~~text
last_id = load_checkpoint()

while true:
    rows = fetch_next_batch(after_id=last_id, limit=1000)
    if rows is empty:
        break

    transformed = transform(rows)
    write_changes_idempotently(transformed)
    last_id = rows.last_id
    save_checkpoint(last_id)

verify_migration_totals()
~~~

Checkpoints must be updated consistently with data changes. If a checkpoint is saved before the data transaction commits, the job may skip records on restart. If data commits without saving the checkpoint, the job may reprocess the batch; therefore, write operations must be idempotent.

Do not place a large backfill on the application startup path. If every instance starts up and runs the data migration simultaneously, they can contend for locks, cause load spikes, or prolong rollouts. Run data migrations as a separate controlled job.

## 13. Transactions, locks, and idempotency

Migrations should have predictable behavior if they fail midway. Some databases support transactions for many DDL operations; certain operations or engines have implicit commits, making a full rollback impossible as expected.

Distinguish between:

- **Transactional migration:** changes execute within a transaction and can be rolled back if an error occurs before commit.
- **Non-transactional operation:** an operation that cannot run inside a transaction or has its own commit behavior.
- **Idempotent operation:** re-running does not produce incorrect changes or duplicate data.
- **Resumable operation:** can continue from a checkpoint after stopping.

Do not assume DDL is always transactional. Check database documentation and migration tool settings. For non-transactional operations, break steps down, verify pre/post state, and prepare a way to resume if a run is interrupted.

Versioned migrations are typically designed to run once per history, not to be arbitrarily re-run by operators via SQL files. For backfill or operational scripts that require retries, design explicit idempotent logic using natural keys or conditional updates to prevent duplicate writes.

Migration tools also commonly use locks to prevent two pipelines from applying migrations to the same database simultaneously. Do not disable locking just to let two deployments run in parallel. Concurrency control at the pipeline level and locking at the database layer are both necessary.

## 14. Database permissions for migrations and runtime applications

The account executing migrations typically requires higher DDL privileges than the runtime account. Sharing one administrative database account across both the application and the pipeline increases the blast radius if the application is compromised.

Separate identities:

| Identity | Typical required permissions |
|---|---|
| Migration job | DDL and DML required for migrations on the managed schema |
| Runtime application | Read/write permissions on required business data |
| Read-only reporting | SELECT on permitted data scopes |
| Backup/restore operator | Backup or recovery permissions per role |
| Local developer | Permissions on development databases, not production |

Migration credentials should only be granted to the migration deployment job after quality gates and approvals pass. Secrets should be retrieved from a secret manager via workload identity, scoped per environment, and never stored in the repository.

Do not grant the runtime application CREATE/DROP/ALTER permissions unless strictly necessary. If the application automatically runs migrations on startup, every replica may require DDL privileges; this broadens runtime permissions and complicates ordering control. For production, it is generally better to have a dedicated migration job run beforehand or under controlled orchestration.

## 15. Sequencing migrations in the release pipeline

A reference pipeline might follow this sequence:

~~~mermaid
flowchart TD
    A[Pull request with migration] --> B[Review SQL and schema impact]
    B --> C[Validate changelog and version]
    C --> D[Fresh database migration test]
    D --> E[Upgrade test from old schema]
    E --> F[Application integration tests]
    F --> G[Build artifact and record provenance]
    G --> H[Deploy migration job]
    H --> I[Verify schema version and data]
    I --> J[Deploy application]
    J --> K[Post-deploy verification]
~~~

The exact sequence depends on the change and compatibility strategy. With expand-and-contract, the expand migration can run before the new application; the contract migration usually runs after all old consumers have been removed.

Control checkpoints:

- Migration belongs to a reviewed commit.
- CI runs against a database matching the appropriate engine and version.
- Upgrade tests are included, not just fresh installs.
- The pipeline records migration version and checksum.
- The migration job uses a dedicated identity and permissions.
- Only one pipeline modifies the same database at a time.
- The application is deployed only when the schema reaches the required version.
- Post-deployment checks verify schema and application state.

The application deployment job should not assume a migration ran merely because the migration job was scheduled. Verify the actual result and version in the migration history.

## 16. Rolling back migrations is not like rolling back applications

Database rollbacks are usually harder than binary rollbacks. Once the schema has changed and data has been written in the new structure, running reverse DDL can cause data loss or fail to restore the original state.

There are three common approaches:

- **Down migration:** a script reversing the change when the operation is genuinely reversible and no data has been lost.
- **Roll-forward migration:** creating a new migration to fix an incorrect state or apply the needed adjustment.
- **Backup/PITR restore:** restoring the database to a point in time before the incident when necessary, with a plan for handling data generated after that point.

For example, adding a nullable column can usually be dropped again if there is no data that needs to be kept. However, merging two columns, normalizing data, and dropping the original values may be irreversible if no copy was preserved.

Do not treat down migrations as a guaranteed safe rollback. For production, determine in advance whether a migration is reversible, what data could be lost, and under what conditions roll-forward or restore is mandatory.

Before high-risk migrations, take a backup or confirm that point-in-time recovery is functioning. A backup is only useful when restore capability, recovery time, and impact on transactions after the backup timestamp have been verified.

## 17. Monitoring schema drift across environments

Schema drift is the condition where the actual database structure differs from the structure expected by the migration history or repository definitions.

Common causes:

- Operators running SQL manually.
- An environment missing a migration.
- A migration marked as applied while the actual change remained incomplete.
- Another tool modifying objects outside the process.
- Configuration or extension differences across environments.
- Restoring a database from an old backup without synchronizing migration history.

Methods are needed to detect drift:

- Compare actual schema against migration history.
- Use schema diff or drift-detection tools specific to the database engine.
- Check the migration version in each environment.
- Review manual changes and capture them as controlled migrations.
- Alert when production contains unmanaged objects.

Migration history only records what the tool ran; it does not always prove the current schema is still valid. If someone modifies a table directly after a migration, history may remain green while the structure has drifted.

Do not automatically overwrite the production schema when drift is detected. First determine what changes occurred, whether data was affected, and which migration will bring the state back into alignment.

## 18. Baselining an existing database

When introducing a migration tool to a system that has been running for years, the database may not start from an empty schema. The team needs to capture the current state and create a verified baseline.

Reference process:

1. Select a representative database and extract the current schema.
2. Compare development, staging, and production to detect differences.
3. Define the canonical schema version from which environments will begin tracking.
4. Create the initial baseline or changelog according to the tool.
5. Verify the baseline does not accidentally re-run creation/deletion of existing data.
6. Test on a clone or a staging database restored from backup.
7. Record the baseline version and checksum.
8. From that point on, all new changes must go through reviewed migrations.

Do not fabricate a historical migration and run it against production if the objects already exist, as this can cause errors or alter data. A baseline is how the tool begins managing an existing state; it must be grounded in evidence of the actual schema.

## 19. Recording migration evidence and traceability

Each deployment should record:

- Migration version or changeset ID.
- Checksum and execution status.
- Database engine and version.
- Target environment and database identity.
- Pipeline run ID, commit SHA, and artifact digest.
- Start/end timestamps, duration, and outcome.
- Requesting user or workflow.
- Approval record.
- Logs and errors if the migration failed.
- Post-deployment schema version.

Do not log passwords or sensitive data in migration logs. For data migrations, avoid logging individual record contents; only log counts, checkpoints, and necessary statistics.

This information helps answer which version the database was upgraded to, by which release, and which application version was deployed afterward. When investigating incidents, schema versions can be correlated with the time the issue began.

## 20. Checklist for putting schema changes under version control

Before merging a migration or deploying to a shared environment, check:

- [ ] The migration resides in the repository under the conventional directory.
- [ ] The file has a unique version/ID and deterministic ordering.
- [ ] The migration was reviewed for data impact, locks, indexes, and compatibility.
- [ ] Already applied migrations are not modified or versions reused.
- [ ] A single migration tool serves as the primary execution source for the schema.
- [ ] CI tests a fresh database from an empty state.
- [ ] CI tests upgrading from an older schema with representative data.
- [ ] Coexistence of old/new application versions is tested when using rolling deployments.
- [ ] Large backfills include batching, checkpoints, idempotency, and rate limiting.
- [ ] Transactions, locks, and DDL behavior are evaluated for the database engine.
- [ ] The migration job uses dedicated credentials and least-privilege permissions.
- [ ] Pipelines do not run concurrent migrations against the same database.
- [ ] An expand-and-contract plan is prepared for breaking changes.
- [ ] An appropriate down migration, roll-forward, or restore strategy is defined.
- [ ] Backup/PITR and restore capabilities are verified when needed.
- [ ] Schema drift and migration history checks are in place.
- [ ] Deployment records capture version, checksum, commit, and run ID.

When schema changes are stored in Git and executed through a pipeline, each environment can be upgraded following a deterministic history. Migrations are reviewed, tested against representative data, applied using a dedicated identity, and tied to release artifacts. This turns database changes into a controllable and traceable part of the CI/CD process.

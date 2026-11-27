# Distinguishing JPA Schema Generation from Migration Management in Spring Data JPA

## 1. Database Schema and the Role of JPA

A database schema describes the storage structure used by an application: tables, columns, data types, primary keys, foreign keys, unique constraints, indexes, views, and related objects.

In a Spring Data JPA application, entities describe how Java maps to the database structure. For example:

~~~java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 320)
    private String email;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(String email, Instant createdAt) {
        this.email = email;
        this.createdAt = createdAt;
    }
}
~~~

Annotations such as **@Entity**, **@Table**, **@Column**, **@Id**, and **@JoinColumn** describe the mapping between objects and the database. They do not automatically turn every Java change into a controlled database upgrade process.

There are two groups of tasks to distinguish:

- **Schema generation:** creating, altering, validating, or dropping database structures based on entity mappings.
- **Database migration:** managing schema and data changes by version, recording applied history, and deploying alongside source code across multiple environments.

A JPA provider such as Hibernate can generate DDL from entities. Flyway and Liquibase manage migrations using change history. The two approaches solve related problems but have different goals and levels of control.

## 2. Automatic Schema Generation with JPA/Hibernate

Hibernate can read entity metadata and generate DDL statements to initialize a schema. In Spring Boot, the most common configuration is:

~~~properties
spring.jpa.hibernate.ddl-auto=update
~~~

This property is a shortcut for Hibernate schema management, corresponding to the internal property **hibernate.hbm2ddl.auto**.

Commonly used values in Spring Boot:

| Value | Behavior |
|---|---|
| **none** | Does not automatically create or alter the schema |
| **validate** | Validates mappings against the existing schema; does not modify the schema |
| **update** | Attempts to adjust the existing schema to match the mappings |
| **create** | Creates a new schema on startup; existing objects may be dropped before creation |
| **create-drop** | Creates the schema on startup and drops it when the SessionFactory/application shuts down |

Spring Boot's default depends on the environment and schema manager: with embedded databases such as H2, HSQL, or Derby, Boot may choose create-drop when no schema manager is detected; otherwise, the default is typically none. Therefore, explicitly declare ddl-auto per profile instead of relying on the default.

### Example for a development environment

~~~properties
# application-dev.properties
spring.jpa.hibernate.ddl-auto=update
~~~

This configuration is convenient when experimenting with new entities on a disposable development database. However, a schema updated by Hibernate lacks detailed migration history for consistent deployment across environments.

### Example for tests using a temporary database

~~~properties
# application-test.properties
spring.jpa.hibernate.ddl-auto=create-drop
~~~

If tests use a dedicated database, creating the schema at the start and dropping it at the end gives each run a clean state. Do not use this configuration for databases containing data that needs to be preserved.

## 3. How Do Schema Creation, Validation, and Update Differ?

### create and create-drop

**create** is suitable for building a new schema in an environment that can be wiped. If the database already contains data, recreating the schema can cause existing data to be lost.

**create-drop** also drops the schema when Hibernate closes the SessionFactory. This is a common choice for temporary test databases, not a production deployment strategy.

### update

**update** attempts to adjust the database structure to match entity metadata. It is useful for prototypes or simple development environments, but it is not a migration engine.

Hibernate does not manage versioned change history like Flyway/Liquibase. Renaming columns, transforming data, splitting columns, merging tables, or running multiple application versions concurrently requires explicit planning that automatic update cannot replace.

Do not assume update will infer business intent when a property is renamed. Depending on the provider, dialect, and mapping differences, the operation may result in creating a new column while old data remains in the previous column.

### validate

**validate** checks entity mappings against the existing schema and fails if the required structure does not match. It does not create tables, add columns, or transform data.

Validate is a useful check after migrations have run. However, it is not a tool for detecting every form of schema drift: do not treat validate as a complete comparison of all indexes, triggers, procedures, permissions, or database objects not described by entity mappings.

## 4. JPA Schema-Generation Properties

In addition to Hibernate's ddl-auto shortcut, Jakarta Persistence defines standard schema generation properties. For example:

- **jakarta.persistence.schema-generation.database.action**: specifies the DDL action executed directly against the database.
- **jakarta.persistence.schema-generation.scripts.action**: specifies the action for exporting DDL to scripts.
- **jakarta.persistence.schema-generation.scripts.create-target**: target destination for the schema creation script.
- **jakarta.persistence.schema-generation.scripts.drop-target**: target destination for the schema drop script.

Standard actions include options such as none, create, drop, and drop-and-create. Support details may depend on the JPA provider and version.

For example, you can instruct the provider to export DDL to a file for review:

~~~properties
spring.jpa.properties.jakarta.persistence.schema-generation.scripts.action=create
spring.jpa.properties.jakarta.persistence.schema-generation.scripts.create-target=target/generated-schema.sql
spring.jpa.properties.jakarta.persistence.schema-generation.database.action=none
~~~

This example requests exporting the schema creation script without executing DDL directly against the database. The output path and execution capability depend on the provider/build configuration; verify the logs and actual generated file.

Scripts generated from entities can help produce an initial draft, but they require manual review before being used as migrations. Business rules, existing data, optimized indexes, partitions, triggers, and rollout ordering may not be fully represented in entity mappings.

## 5. Why Is Database Migration Needed?

Database migrations record each schema or data change in a repeatable sequence.

For example, an application initially has a customer table with an email column. Later, the business requires adding a status, adding an index, and transforming legacy data. Instead of letting each environment infer the structure from the current entities, migrations explicitly describe each step:

1. Create the customer table.
2. Add the status column.
3. Populate values for existing rows.
4. Add constraints.
5. Create appropriate indexes.
6. Apply subsequent changes using new migrations.

Migrations are stored alongside source code in version control. Development, test, staging, and production apply the same sequence of migrations in order. The migration tool stores history to track which versions have already run.

Benefits:

- Provides a history of schema and data changes.
- Enables DDL/DML review in pull requests.
- Supports repeatable deployments across multiple environments.
- Detects migrations modified after being applied via checksums.
- Controls ordering, baselines, and deployment state.
- Allows preparing planned rollbacks or forward-fixes.
- Makes it easy to spin up test databases matching a specific application version.

## 6. How Does Flyway Work?

**Flyway** manages migrations primarily via SQL files or Java migrations. For versioned SQL migrations, filenames typically follow this structure:

~~~text
V<VERSION>__<DESCRIPTION>.sql
~~~

For example:

~~~text
src/main/resources/db/migration/
    V1__create_customer.sql
    V2__add_customer_status.sql
    V3__create_customer_email_index.sql
    R__refresh_customer_views.sql
~~~

- **V1**, **V2**, **V3** are migration versions; each version must be unique.
- The part after the double underscore is the description.
- **R__...** is a repeatable migration, which is re-run whenever its checksum changes.

Flyway creates a history table, **flyway_schema_history** by default, to record applied migrations, versions, checksums, timestamps, and status. When running migrate, Flyway scans available migrations, compares them against the history, and executes pending migrations in order.

### Versioned migrations

A versioned migration is applied once per database. It is the appropriate place for creating/altering tables, adding columns, constraints, indexes, and transforming data.

Once a versioned migration has been deployed to a shared environment or production, treat that file as immutable. If structural fixes are needed, create a new versioned migration rather than editing the old file. If an old file changes, checksum validation may fail because its content no longer matches the recorded history.

### Repeatable migrations

Repeatable migrations do not have a version. Flyway re-runs them when the file's checksum changes. They are typically suited for views, procedures, functions, or reference data that can be recreated idempotently.

For example:

~~~sql
-- R__refresh_customer_view.sql
CREATE OR REPLACE VIEW active_customer AS
SELECT id, email
FROM customer
WHERE status = 'ACTIVE';
~~~

The statement above requires syntax compatible with the target database. A repeatable migration must be designed so that it can be re-run safely.

## 7. Flyway Migration Example

The first migration creates the table:

~~~sql
-- V1__create_customer.sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email)
);
~~~

The second migration adds the status column in a way that handles existing data:

~~~sql
-- V2__add_customer_status.sql
ALTER TABLE customer
    ADD COLUMN status VARCHAR(20);

UPDATE customer
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

After the application has been deployed and legacy data has been backfilled, a subsequent migration can enforce NOT NULL:

~~~sql
-- V3__require_customer_status.sql
ALTER TABLE customer
    ALTER COLUMN status SET NOT NULL;
~~~

The ALTER COLUMN statement in this example uses PostgreSQL syntax. MySQL, SQL Server, Oracle, and other databases may use different syntax. Migrations must be written and tested against the actual database used by the application.

Splitting the steps helps keep the application compatible during the transition period: add a nullable column, deploy code that reads/writes status, backfill existing data, and only then enforce the required constraint. For large tables, a full-table UPDATE can cause heavy locking and large transaction logs; plan appropriate batching/backfilling.

## 8. Integrating Flyway with Spring Boot

Add the Flyway dependency compatible with the project's Spring Boot version and database driver. Maven example using Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.flywaydb</groupId>
    <artifactId>flyway-core</artifactId>
</dependency>
~~~

Some databases require a separate Flyway module depending on the Flyway version, such as the MySQL support module. Check the documentation and dependency management of your active version rather than arbitrarily adding a version that conflicts with the BOM.

Configuration:

~~~properties
spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration

# Migrations create the schema; Hibernate only validates mappings
spring.jpa.hibernate.ddl-auto=validate
~~~

When Spring Boot detects Flyway on the classpath and enabled, Flyway automatically locates migrations at the configured locations and applies pending migrations during application startup. Boot manages initialization ordering so the schema is prepared before JPA uses it.

Common properties:

| Property | Meaning |
|---|---|
| spring.flyway.enabled | Enables/disables Flyway |
| spring.flyway.locations | Locations to scan for migrations |
| spring.flyway.schemas | Schemas managed by Flyway |
| spring.flyway.default-schema | Default schema |
| spring.flyway.baseline-on-migrate | Allows automatic baselining of a non-empty schema in configured situations |
| spring.flyway.validate-on-migrate | Validates migrations during migrate |
| spring.flyway.clean-disabled | Disables the clean command; defaults to true in current Spring Boot versions |

Do not enable the clean command on important databases. The clean command can drop schema objects and data; only use it on temporary databases in controlled test environments.

## 9. Flyway Baseline and Validate

### Baselining an existing database

If an application already has a database before adopting Flyway, you cannot assume it is an empty database. You must determine which version the current schema corresponds to, compare structures, and choose an appropriate baseline version.

Flyway baseline marks an existing database at a specified version so that newer migrations can be applied. Use baseline-on-migrate with great caution: if misconfigured, a database not in the expected state could be marked as already baselined.

Create baselines intentionally, inspect existing schema and data, test on a copy first, and only then deploy.

### Validate

The **flyway validate** command compares applied migrations against available migrations, including checksums, names, and migration types. It helps detect applied files that were modified, missing files, or mismatched migrations.

For example:

~~~bash
# Validate migrations against database history
./mvnw flyway:validate

# Apply pending migrations
./mvnw flyway:migrate
~~~

The Maven goal name and invocation depend on the plugin configured in the build. You can also use the Flyway CLI or corresponding Gradle tasks.

If validation fails, identify which environment ran the migration, which file changed, and which history differs. Do not arbitrarily edit checksums or run repair just to turn a pipeline green; repair must be based on a verified database state.

## 10. How Does Liquibase Work?

**Liquibase** manages database changes using a changelog. A changelog contains changesets, where each changeset describes a logical change. Changelogs can be written in XML, YAML, JSON, or formatted SQL.

A changeset is identified by the combination of **id**, **author**, and changelog path. Liquibase records history in tables such as **DATABASECHANGELOG** and uses **DATABASECHANGELOGLOCK** to coordinate concurrent updates.

YAML changelog example:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-customer
      author: team
      changes:
        - createTable:
            tableName: customer
            columns:
              - column:
                  name: id
                  type: bigint
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: varchar(320)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: created_at
                  type: timestamp
                  constraints:
                    nullable: false
~~~

This is a structural changelog example; auto increment, identity, and timestamp types may need adjustment for the target database.

### Changesets and checksums

When Liquibase applies a changeset, it calculates a checksum and records it in DATABASECHANGELOG. On subsequent runs, checksums are compared to detect if an already-applied changeset has been modified.

Once a changeset is deployed, keep it immutable. Create a new changeset to modify schema or data. Some changesets can use runOnChange for objects like views/procedures that need updating when their definition changes; only use this when the statement is designed to be safely re-runnable.

### Preconditions, contexts, and labels

Liquibase supports preconditions to check database state before running a changeset. For example, checking whether a table or column already exists, whether the database vendor matches, or whether data satisfies assumptions before dropping/altering.

Contexts and labels help select groups of changesets by purpose or environment. Use them with clear conventions; do not use environment filters to hide a required migration.

### Rollback

Liquibase supports rollback by tag, date/time, or changeset count, and rollback logic can be declared depending on the changelog type. However, not every operation can be safely reversed. When a migration has deleted or transformed data, rollback requires appropriate data recovery logic or backups.

## 11. Integrating Liquibase with Spring Boot

Add the dependency managed by Spring Boot dependency management:

~~~xml
<dependency>
    <groupId>org.liquibase</groupId>
    <artifactId>liquibase-core</artifactId>
</dependency>
~~~

Create a master changelog, for example:

~~~text
src/main/resources/db/changelog/db.changelog-master.yaml
~~~

Configuration:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml

spring.jpa.hibernate.ddl-auto=validate
~~~

Spring Boot auto-configures Liquibase when the dependency is on the classpath and the feature is enabled. Liquibase reads the master changelog, follows included files, and applies missing changesets.

Do not configure both Flyway and Liquibase to manage the same schema. Choose a single tool as the migration authority to avoid two competing histories and workflows.

## 12. Comparing JPA Schema Generation, Flyway, and Liquibase

| Criterion | JPA/Hibernate DDL | Flyway | Liquibase |
|---|---|---|---|
| Source of truth | Entity mapping | Migration files | Changelog/changesets |
| Primary goal | Initialize or validate schema | Version-based migration management | Change management via changesets |
| Deployment history | No standard migration history | flyway_schema_history | DATABASECHANGELOG |
| Modified file detection | No migration checksums | Checksum validation | Changeset checksums |
| Data migration | Not a versioned data management workflow | Can use SQL/Java migrations | Can use change types or SQL |
| Rollback | No versioned rollback history | Primarily creates new forward migrations; undo depends on version/edition | Has rollback support, though reversibility still must be verified |
| Multi-database | Depends on JPA provider/dialect | SQL migrations are often dialect-specific; supports Java migrations | Has abstract change types and custom SQL |
| Best suited for | Dev/test, bootstrapping, mapping validation | SQL-first, clear sequential migrations | Structured changelogs, preconditions, contexts, and rollback metadata |

No single tool fits every project. If the team wants explicit SQL DDL control and sequential versioning, Flyway is often simpler. If you need structured changelogs, preconditions, contexts/labels, and rollback metadata, Liquibase may be a better fit.

## 13. Do Not Let Multiple Tools Own the Same Schema

A common configuration mistake is simultaneously using Hibernate update, schema.sql, data.sql, and Flyway/Liquibase to create or alter the same schema.

Example to avoid in a migration-managed environment:

~~~properties
spring.jpa.hibernate.ddl-auto=update
spring.flyway.enabled=true
spring.sql.init.mode=always
~~~

When multiple tools modify the schema together, initialization ordering can cause conflicts: Hibernate adds a column and the migration tries to add it again, scripts run before tables exist, or environments end up in different states.

Spring Boot recommends using Flyway or Liquibase as the higher-level tool to create and initialize the schema. Do not combine them with schema.sql/data.sql as a parallel workflow for the same database.

Common configuration when a migration tool is the source of schema management:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
~~~

Or use none if you do not want Hibernate to perform even the startup validation step. With validate, mappings are verified after migrations have prepared the schema.

## 14. Entity Mappings Must Match Migrations

Migrations create the physical structure. Entity mappings describe how the application uses that structure. Both parts must be consistent.

Example migration creating a column:

~~~sql
ALTER TABLE customer
    ADD COLUMN created_at TIMESTAMP NOT NULL;
~~~

Entity mapping:

~~~java
@Column(name = "created_at", nullable = false)
private Instant createdAt;
~~~

Points to keep synchronized:

- Table and column names.
- Data types, precision, and scale.
- Nullability and default values.
- Primary keys, foreign keys, and unique constraints.
- Indexes required by queries.
- Enum storage strategy.
- Join columns and association mappings.
- Naming strategy and schema name.

Do not assume **@Column(nullable = false)** automatically creates a database constraint if Hibernate does not manage DDL. With a migration-managed schema, the corresponding DDL must exist in the migration.

Pay special attention to naming strategy: Hibernate may convert camelCase properties to snake_case depending on configuration. Check the actual SQL names in migrations and the database instead of guessing column names.

## 15. Schema Migration and Data Migration

Schema migration alters structure. Data migration transforms existing data to fit a new structure or business requirement.

For example, changing from full_name to first_name and last_name. Simply adding two columns is not enough; legacy data must be migrated, read/write code updated, and only then the old column dropped.

A safe deployment strategy typically includes:

1. **Expand:** add new columns or tables in a backward-compatible way; keep the old structure.
2. **Deploy compatible code:** the new application can read/write both old and new structures or dual-write during the transition period.
3. **Backfill:** migrate legacy data in batches safely, idempotently, and with progress tracking.
4. **Switch reads:** switch the application to use the new structure once data is complete.
5. **Contract:** after all old instances have stopped using the old structure, drop the old column or table in a separate migration.

The expand-and-contract pattern is especially useful during rolling or blue/green deployments, where old and new application versions may run concurrently for a period of time.

Do not combine a breaking change with a code deploy if older application instances can still access the database. Evaluate backfill duration, locks, transaction log volume, and rollback/forward-fix capabilities.

## 16. Migrations on Large Tables

Running ALTER TABLE, building indexes, or backfilling millions of rows can cause locks and impact active queries. Exact syntax and lock severity depend on the database and version.

Before migrating large tables:

- Inspect execution plans and existing indexes.
- Determine whether the DDL locks the table and estimate duration.
- Use concurrent/online index builds if supported and appropriate in the database.
- Split data backfills into batches by key or range.
- Persist checkpoints so tasks can resume after failures.
- Limit transaction size and monitor logs/replication lag.
- Plan deployment windows, monitoring, and forward-fix options.
- Test on a copy close to production scale.

Do not assume all DDL is transactional. Some databases implicitly commit or cannot roll back certain DDL operations. Verify actual database behavior and Flyway/Liquibase configuration before relying on automatic rollback.

## 17. Testing Migrations in CI/CD

Pipelines should verify both migrations and mappings:

1. Provision a clean database matching the production type and version.
2. Run all migrations from the beginning.
3. Run migration tool validation/checksum checks.
4. Start Spring Boot with Hibernate ddl-auto=validate.
5. Run repository/service integration tests.
6. Verify constraints, indexes, and data after migration.
7. Test upgrading from older schema versions if upgrade paths must be supported.
8. Archive logs and migration reports for traceability.

Testcontainers can be used to run the same database engine as production. H2 cannot always substitute for PostgreSQL, MySQL, or SQL Server because DDL syntax, data types, constraints, and transaction behavior differ.

Migration tests should cover:

- An empty database migrating to the latest version.
- An older database containing data upgrading successfully.
- Data backfills for null/legacy records.
- Ensuring unique/foreign key constraints do not drop or break valid data.
- Failing pipelines on migration errors rather than falsely marking success.
- Verifying Hibernate validate catches mapping mismatches.
- Ensuring application restarts do not re-execute already-succeeded versioned migrations.

## 18. Managing Existing Databases and Schema Drift

A project adopting Flyway/Liquibase may already have multiple manually created databases. Take inventory before baselining:

- Actual application version and schema in each environment.
- Tables, columns, constraints, and indexes.
- Special data or historical records.
- Manual changes not yet recorded in source control.
- Differences in collation, timezone, sequences, and schema owners.

After choosing a baseline, run migrations against a copy of each environment, compare schemas, and confirm there are no unexpected changes.

Schema drift occurs when the actual database diverges from the schema described by migration history or source code. It can arise from manual edits, out-of-band scripts, skipped migrations, or environments restored from outdated snapshots.

Migration history and checksums help detect certain discrepancies, but they do not replace actual schema comparisons, backups, and change control processes.

## 19. Rollback and Forward-Fix

Rollback means restoring a previous state. Not every migration is reversible.

For example:

- Adding a nullable column can usually be rolled back by dropping the column if no retained data exists yet.
- Dropping a column containing data cannot be recovered simply by adding the column back.
- Data transformations may lose information if the transformation is not reversible.
- Creating an index is usually easier to roll back than altering business data.

Before high-risk migrations, take backups/snapshots and verify restore capability. Having a rollback script does not guarantee a safe rollback if the new application has already written data using the new schema.

In production, forward-fix is often safer than attempting to reverse a destructive migration: create a new migration to repair the current state and keep deployment history consistent.

## 20. Common Mistakes

### 20.1. Using ddl-auto=create or create-drop in production

This can wipe tables/data or drop the schema when the application shuts down. Use a migration tool and set an appropriate ddl-auto, typically validate or none.

### 20.2. Treating update as a complete migration solution

Hibernate update does not provide versioned migration history, checksums, data transformations, or rollout workflows. Use Flyway/Liquibase for controlled schema evolution.

### 20.3. Modifying already-applied migration files

Changing a deployed versioned migration or changeset breaks checksum validation or causes environments to diverge. Create a new migration to apply fixes.

### 20.4. Running both Flyway and Liquibase on the same schema

The two tools maintain separate histories and can compete over structural changes. Choose one migration authority for the schema.

### 20.5. Using schema.sql/data.sql alongside a migration tool

Scripts can run out of order or introduce changes outside migration history. Use the migration tool as the single consistent workflow for schema and data initialization.

### 20.6. Migrating only the schema while forgetting legacy data

Adding NOT NULL columns or changing types can fail against existing data. Separate steps into adding nullable, backfilling, validating data, and then enforcing constraints.

### 20.7. Using one DDL script for every database vendor

Identity, sequences, indexes, ALTER COLUMN, and online DDL vary by vendor. Write migrations for the target database or provide vendor-specific migrations when needed.

### 20.8. Relying on H2 to validate production migrations

H2 may accept syntax or data types that differ from the real database. Run migration integration tests against the target database engine.

### 20.9. Baselining without inspecting the actual schema

An incorrect baseline can mark an out-of-sync database as being at the expected version. Compare schemas and data before baselining.

### 20.10. Assuming rollback can always recover data

Dropping columns or running destructive updates may be irreversible. Plan backups, forward-fixes, and restore verification before deploying.

## 21. Tool Selection Workflow

When designing schemas for a Spring Data JPA application:

1. Use entity mappings to describe the object-relational structure.
2. Choose JPA/Hibernate schema generation for prototypes, temporary databases, or exporting initial DDL drafts.
3. For shared schemas and production, choose one migration tool as the source of history management.
4. Choose Flyway if you want clear SQL/versioned migrations; choose Liquibase if you need structured changelogs, preconditions, contexts/labels, or rollback metadata.
5. Store migrations in version control and never edit applied migrations.
6. Set Hibernate ddl-auto=validate or none when the migration tool owns the schema.
7. Write data migrations and backward-compatible rollouts when altering structures with existing data.
8. Run migrations and integration tests on a production-equivalent database.
9. Baseline legacy databases only after auditing and reconciling actual state.
10. Back up, monitor, and prepare forward-fix plans for production migrations.

## 22. Key Takeaways

- Entity mappings describe how Java maps to the database; they do not replace migration history.
- Hibernate ddl-auto provides options none, validate, update, create, and create-drop.
- create/create-drop fit temporary databases; do not use them for production deployments with data to preserve.
- update is convenient for development but is not a versioned schema evolution tool.
- validate checks mappings against the current schema, does not create or alter the database, and does not inspect every database object.
- Jakarta Persistence provides schema-generation properties for applying DDL directly or exporting scripts.
- Flyway manages versioned and repeatable migrations, storing history/checksums in flyway_schema_history.
- Liquibase manages changelogs/changesets identified by id, author, and path, storing history/checksums in DATABASECHANGELOG.
- Never edit applied migrations/changesets; create a new migration to apply fixes.
- Choose a single tool as the migration authority; avoid mixing Hibernate update, Flyway, Liquibase, and schema.sql/data.sql on the same schema.
- Use ddl-auto=validate to verify mappings after migrations have run.
- Data migrations require backfilling, batching, and compatible rollouts; for multi-version deployments, use expand-and-contract.
- DDL can cause locks or be non-transactional; test according to your database vendor.
- CI must run migrations against a real database or production-equivalent Testcontainers.
- Backups, restores, and forward-fixes are part of the schema deployment plan.

JPA/Hibernate schema generation helps build or validate structures from entity mappings. Flyway and Liquibase manage schema and data changes with a history that can be reviewed, verified, and repeatably deployed. Once a database becomes a shared asset across multiple application versions and environments, versioned migrations are the foundation for safe deployments.

## References

- [Spring Boot — SQL Databases and JPA Schema Creation](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization and Migration Tools](https://docs.spring.io/spring-boot/4.2-SNAPSHOT/how-to/data-initialization.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Redgate Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations)
- [Redgate Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)
- [Redgate Flyway — Validate](https://documentation.red-gate.com/flyway/reference/commands/validate)
- [Liquibase — Changesets](https://docs.liquibase.com/concepts/changelogs/changeset.html)
- [Liquibase — Preconditions](https://docs.liquibase.com/community/user-guide-5-0-2/what-are-preconditions)
- [Liquibase — Changeset Checksums](https://docs.liquibase.com/community/user-guide-5-0-3/what-is-a-changeset-checksum)
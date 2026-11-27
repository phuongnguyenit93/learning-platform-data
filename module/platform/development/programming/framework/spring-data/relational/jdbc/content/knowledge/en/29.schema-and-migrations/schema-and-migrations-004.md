# Managing Schema Changes with Flyway or Liquibase

In a **Spring Data Relational JDBC** application, entities and repositories depend directly on the structure of tables, columns, primary keys, foreign keys, and data types in the database. As the application evolves, the schema changes too: adding columns, creating indexes, splitting tables, changing data types, or transforming legacy data. If every environment applies manual schema edits by hand, databases gradually drift apart and the application may work on a developer's machine yet fail in staging or production.

**Database migration** is the practice of managing schema changes by version, storing them in source control, and applying them in a deterministic order. Two popular tools in the Spring ecosystem are **Flyway** and **Liquibase**. Both track migration history in the database, detect already-applied changes, and help deploy schemas consistently across environments.

Spring Data JDBC does not automatically manage schema change history. Repositories require an appropriately prepared schema. Flyway or Liquibase handles schema evolution; Spring Data JDBC mappings then operate against the corresponding tables and columns.

## 1. Why Are Migrations Needed?

Suppose the initial version of an application has a product table:

~~~sql
CREATE TABLE product (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL
);
~~~

The next version needs status and price:

~~~sql
ALTER TABLE product
    ADD COLUMN status VARCHAR(24);

ALTER TABLE product
    ADD COLUMN price DECIMAL(19, 2);
~~~

Later the application needs default values, constraints, and indexes. If developers execute manual SQL statements from memory, some environments may end up missing columns or having different data types.

Migrations solve this problem by storing changes as versioned files:

~~~text
src/main/resources/db/migration/
  V1__create_product.sql
  V2__add_product_status.sql
  V3__add_product_price.sql
  V4__add_product_indexes.sql
~~~

During deployment, the tool reads history from the database, determines which migrations have not yet run, and applies them in order. A fresh database runs from V1; a database already at V2 only needs V3 and V4.

### 1.1. What Do Migrations Provide?

- **Reproducibility:** you can build the schema from scratch using the exact same sequence of migrations.
- **Audit trail:** you know which changes were applied and when.
- **Reviewability:** schema changes accompany code in pull requests.
- **Environment consistency:** dev, test, staging, and production use the same schema definitions.
- **Controlled deployment:** migrations run in order and can be verified via checksums/status.
- **Collaboration support:** multiple developers can add new migrations without rewriting released history.

### 1.2. Migrations Are Part of Source Code

Migration files should be committed to version control together with related entity/repository changes. Adding a Java field while forgetting the migration can cause runtime query or write failures. Editing production schemas directly without saving a migration prevents subsequent environments from reproducing the change.

A complete change typically includes:

1. A migration modifying schema or data.
2. Mappings/entities matching the new schema.
3. Repositories/queries using the new columns or tables.
4. Tests confirming the application works against the schema built by migrations.

## 2. How Do Flyway and Liquibase Work?

Both tools store migration state in the database, though they describe changes differently.

| Aspect | Flyway | Liquibase |
| --- | --- | --- |
| Common format | Versioned SQL migrations | Changelogs and changesets in XML, YAML, JSON, or SQL |
| History unit | Versioned migrations and repeatable migrations | Changesets with id, author, and file path |
| Tracking table | Usually `flyway_schema_history` | Usually `DATABASECHANGELOG` |
| Sync on run | Applies unexecuted migrations in version order | Applies unrecorded changesets |
| Change verification | Checksum and migration status | Checksum, id/author/path, and changeset status |
| Rollback | Usually favors new forward-fix migrations; undo has edition/config limits | Rollback can be declared per changeset; auto-generation depends on change type |
| Database description | Direct, explicit SQL close to the database | Structured change types that can partially abstract SQL |

Neither tool makes every migration safe automatically. Migration quality depends on design, review, testing, and deployment procedures.

### 2.1. Choose One Tool as the Source of Truth

A typical application should use either Flyway or Liquibase to manage its schema. Do not let both manage the same schema without a clear ownership split. When both modify the same table, history and deployment order become confusing.

If a project already has a migration tool and history, stay with that tool. Switching tools is a dedicated migration project: you must capture current state, baseline history, prevent both tools from running together, and verify each environment.

## 3. Flyway: Versioned SQL Migrations

Flyway fits teams that want to express schemas in direct SQL and manage migration ordering by version.

### 3.1. Directory Structure

Common default location:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_product.sql
      V2__add_product_status.sql
      V3__add_product_price.sql
      V4__create_category.sql
~~~

Versioned migration filenames follow the pattern:

~~~text
V<version>__<description>.sql
~~~

Examples:

- `V1__create_product.sql`
- `V2__add_product_status.sql`
- `V2_1__add_product_price.sql`
- `V3__create_product_category_index.sql`

Two underscores separate version and description. Versions are compared according to Flyway's rules; choose a consistent numbering scheme and avoid creating two migrations with the same version.

### 3.2. First Migration Example

File `V1__create_product.sql`:

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uk_product_sku UNIQUE (sku)
);
~~~

The migration creates the table and constraint. The identity syntax in the example fits several modern databases; for PostgreSQL, MySQL, SQL Server, or Oracle, choose syntax valid for your target database. Flyway does not turn vendor-specific SQL into portable SQL.

### 3.3. Adding a Column via a New Migration

File `V2__add_product_status.sql`:

~~~sql
ALTER TABLE product
    ADD COLUMN status VARCHAR(24);

UPDATE product
SET status = 'ACTIVE'
WHERE status IS NULL;

ALTER TABLE product
    ALTER COLUMN status SET NOT NULL;
~~~

The `ALTER COLUMN ... SET NOT NULL` syntax differs across databases. The example illustrates the three-step idea:

1. Add the column as nullable.
2. Backfill existing rows.
3. Enforce `NOT NULL` once every row has a value.

For other databases, use the corresponding syntax. Do not add `NOT NULL` directly to a populated table without ensuring every existing row gets a valid value.

### 3.4. Flyway Schema History

Flyway creates a history table, defaulting to `flyway_schema_history`. This table records version, description, type, script, checksum, execution timestamp, success status, and related metadata.

When running migrate:

1. Flyway reads history.
2. Compares migrations on the classpath with applied versions.
3. Identifies pending migrations.
4. Executes them in version order.
5. Records results in the schema history table.

If an already-applied migration's contents are modified, the checksum may mismatch. This signals that source code history no longer matches database history.

### 3.5. Do Not Modify Applied Versioned Migrations

Suppose `V2__add_product_status.sql` has already run in staging and production. Do not edit V2 to add a new column. Create V5 instead:

~~~text
V1__create_product.sql
V2__add_product_status.sql
V3__add_product_price.sql
V4__create_category.sql
V5__add_product_status_index.sql
~~~

Databases that already applied V2 keep V2's original checksum. Fresh databases run the entire chain. Editing V2 causes existing environments to report checksum mismatches while new environments receive different definitions from old ones.

This rule keeps migration history immutable once released.

### 3.6. Repeatable Migrations

Flyway also supports repeatable migrations, usually named with the pattern:

~~~text
R__refresh_product_search_view.sql
~~~

Repeatable migrations are re-applied whenever their checksum changes, after pending versioned migrations. They are commonly suited for objects that can be replaced with updated definitions, such as views, functions, or procedures, depending on the database and team conventions.

Do not use repeatable migrations to replace versioned migrations for all schema changes. Changes with historical significance need explicit versions and deterministic ordering.

## 4. Configuring Flyway in Spring Boot

Add the Flyway dependency matching your project's Spring Boot version and database driver. In many modern releases, the core dependency and database-specific module may be separated; consult the documentation compatible with your running version.

Illustrative Gradle example:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")

    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
}
~~~

Exact dependency coordinates and whether a separate database module is required depend on the Flyway version. Use Spring Boot's dependency management/BOM whenever possible to avoid incompatible versions.

### 4.1. Configuring Application Properties

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=$DB_PASSWORD

spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration
spring.flyway.schemas=public
spring.flyway.table=flyway_schema_history
~~~

In real environments, obtain passwords from a secret manager or environment variable; never commit credentials to source control.

Commonly used Flyway properties:

| Property | Purpose |
| --- | --- |
| `spring.flyway.enabled` | Enables/disables Flyway auto-configuration |
| `spring.flyway.locations` | Migration locations |
| `spring.flyway.schemas` | Schemas managed by Flyway |
| `spring.flyway.default-schema` | Default schema for Flyway |
| `spring.flyway.table` | Name of the history table |
| `spring.flyway.baseline-on-migrate` | Baselines a non-empty database lacking history; use cautiously |
| `spring.flyway.validate-on-migrate` | Validates status/checksums before migrating |
| `spring.flyway.clean-disabled` | Prevents destructive schema clean operations |

Property names and defaults may vary by Spring Boot version. Check configuration metadata or the reference docs for your project's release.

### 4.2. When Do Migrations Run?

With Spring Boot auto-configuration, Flyway normally runs during application context initialization once the datasource is ready. Boot coordinates database component initialization order so migrations execute before beans that depend on the schema in standard setups.

If a project has multiple datasources, multiple transaction managers, or custom initialization, explicitly configure the datasource and migration ordering. Never assume migrations run against the right database simply because the application has a Flyway bean.

### 4.3. Separating Migration Privileges from Runtime Privileges

In production, the migration account typically needs DDL privileges such as CREATE/ALTER/INDEX, whereas the application's runtime account only needs business data read/write privileges. Separating these two roles reduces blast radius if application credentials are exposed or runtime code has bugs.

You can configure a dedicated migration account via your deployment pipeline or dedicated Flyway configuration depending on application architecture. Do not grant DDL privileges to the runtime user out of convenience if operational workflows allow separation.

## 5. Liquibase: Changelogs and Changesets

Liquibase describes change history in a changelog. A changelog contains multiple changesets; each changeset is identified by `id`, `author`, and file path.

### 5.1. Directory Structure

Example:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-product.yaml
        002-add-product-status.yaml
        003-add-product-price.yaml
~~~

The master changelog includes changeset files:

~~~yaml
databaseChangeLog:
  - include:
      file: db/changelog/changes/001-create-product.yaml
  - include:
      file: db/changelog/changes/002-add-product-status.yaml
  - include:
      file: db/changelog/changes/003-add-product-price.yaml
~~~

Include order is part of deployment history. Do not reorder already-applied changesets in ways that alter database semantics.

### 5.2. Changeset Creating a Table

File `001-create-product.yaml`:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-product
      author: team
      changes:
        - createTable:
            tableName: product
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: sku
                  type: VARCHAR(80)
                  constraints:
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(200)
                  constraints:
                    nullable: false
        - addUniqueConstraint:
            tableName: product
            columnNames: sku
            constraintName: uk_product_sku
~~~

Change types describe structure at a higher level of abstraction than raw SQL. Liquibase generates SQL suitable for the configured database within the scope supported by each change type. For vendor-specific features, use SQL changes or appropriate preconditions.

### 5.3. Changeset Adding a Column and Backfilling

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-product-status
      author: team
      changes:
        - addColumn:
            tableName: product
            columns:
              - column:
                  name: status
                  type: VARCHAR(24)
        - update:
            tableName: product
            columns:
              - column:
                  name: status
                  value: ACTIVE
            where: status IS NULL
        - addNotNullConstraint:
            tableName: product
            columnName: status
            columnDataType: VARCHAR(24)
~~~

The example illustrates the sequence of adding a column, backfilling, and applying NOT NULL. SQL generation capabilities and atomicity depend on the database; for large tables, backfills may need batching in separate migrations to avoid prolonged transactions/locks.

### 5.4. Liquibase History Tables

Liquibase typically uses two tables:

- `DATABASECHANGELOG`: records applied changesets, checksums, authors, file paths, timestamps, and statuses.
- `DATABASECHANGELOGLOCK`: manages locking to prevent multiple concurrent Liquibase processes from modifying the schema simultaneously.

At startup, Liquibase reads the changelog, compares it with the history table, and applies unexecuted changesets. If an already-executed changeset is modified, checksum validation can detect the discrepancy.

### 5.5. Applied Changesets Must Also Remain Immutable

Once a changeset has been deployed to any shared environment, do not edit its contents to create a new change. Add a new changeset instead.

Do not delete changesets from the changelog or arbitrarily change `id`/`author`/`path` after application. Those attributes form part of the changeset's identity in the history table.

## 6. Rollbacks in Liquibase and Flyway

Rolling back a schema is harder than rolling back a business transaction. DDL may not be transactional on some databases; structural changes can also destroy data that cannot be recovered by an inverse statement.

### 6.1. Rollback in Liquibase

Liquibase allows declaring rollback steps for a changeset:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 004-add-display-label
      author: team
      changes:
        - addColumn:
            tableName: product
            columns:
              - column:
                  name: display_label
                  type: VARCHAR(200)
      rollback:
        - dropColumn:
            tableName: product
            columnName: display_label
~~~

For certain change types, Liquibase can infer rollbacks automatically; for complex operations or transformed data, declare explicit rollbacks or have a forward-fix plan. Do not assume every change has a safe automatic rollback.

### 6.2. Rollback in Flyway

Flyway traditionally focuses on forward-moving versioned migrations. Undo migrations have capabilities and limitations depending on edition/configuration. In many production workflows, the recommended strategy is creating a new migration to fix an error or restore compatibility rather than modifying an already-executed file.

For example, if V5 added an incorrect column:

~~~text
V5__add_wrong_column.sql
V6__remove_wrong_column.sql
~~~

V6 introduces a controlled subsequent change. However, if the column already contains valuable data, dropping it loses data; evaluate the impact before rolling back or forward-fixing.

### 6.3. Why Is Forward-Fix Usually Safer?

Once a migration has run in production:

- A new application version may have already written data to the new schema.
- New tables/columns may already contain critical data.
- Some DDL cannot be reversed without data loss.
- Old/new application instances may be running side by side.

A new migration lets you repair state intentionally while preserving history. Rollback still has a place in appropriate situations, but not every DDL statement should be assumed to have a clean inverse operation.

## 7. Baselining an Existing Database

A system may have been running long before adopting Flyway or Liquibase. In that case the database is non-empty, yet lacks a migration history table.

### 7.1. Flyway Baseline

Flyway supports baselining to mark an existing database as already at a specific version. Migrations with versions lower than or equal to the baseline are treated as already part of the initial state; newer migrations are applied as normal.

`baseline-on-migrate` can automatically baseline a non-empty database, but enabling it carelessly is dangerous. If Flyway mistakes a fresh database or incomplete schema for a baseline, initial table-creation migrations may be skipped.

Safe process:

1. Back up the database.
2. Inventory the current schema.
3. Establish a baseline version accurately reflecting the actual state.
4. Verify the history table and baseline version.
5. Create subsequent migrations for new changes.
6. Test on a database copy before running in production.

### 7.2. Liquibase Changelog Sync

Liquibase provides commands/operations to synchronize changelog history without re-running changesets, commonly used when taking over management of a database that already has the corresponding schema. Verify that the current schema truly matches the changesets marked as executed.

If you sync a changelog that does not match the actual schema, Liquibase will believe changes were applied even if tables or constraints are missing. Inspect the schema and test on a copy before executing.

## 8. Safe Schema Changes While the Application Is Running

Production often uses rolling deployments: old and new instances may serve requests concurrently for a period of time. Migrations must remain compatible with both versions during the transition window.

For example, suppose column `name` needs to be renamed to `display_name`. Renaming directly and deploying the new app can break the old app while it still queries `name`.

A common strategy is **expand-and-contract**.

### 8.1. Expand Phase

Add the new structure so old code continues working:

~~~sql
ALTER TABLE product
    ADD COLUMN display_name VARCHAR(200);
~~~

Do not drop `name` yet. Both old and new schemas coexist.

### 8.2. Backfill Data

Copy data from the old column to the new column:

~~~sql
UPDATE product
SET display_name = name
WHERE display_name IS NULL;
~~~

For large tables, backfilling may require a batched job, ID-range chunking, or checkpointing to avoid one giant transaction.

### 8.3. Deploy Code Compatible with Both

The new application version can read the new column and temporarily write both columns if old instances still need support. Design a clear source of truth during dual-write and handle errors if a write fails to update both.

### 8.4. Contract Phase

Only after:

- All old instances have been replaced.
- Code no longer reads/writes the old column.
- New data has been backfilled and verified.
- No consumers or jobs depend on the old column.

create a migration to drop the old column.

~~~sql
ALTER TABLE product DROP COLUMN name;
~~~

This is a destructive migration; confirm backups, retention, and recovery capability before running it.

### 8.5. Do Not Bundle Breaking Changes into a Single Deploy

Avoid a single release that both drops an old column and deploys code expecting only the new column if rolling deployments can leave old instances running. Split schema and code changes into compatible steps to minimize downtime and avoid breakage on application rollback.

## 9. Migrations for Large Tables and Large Datasets

A single ALTER or UPDATE can lock a table, hold a long transaction, or spike replication lag. Before running migrations on large tables, assess:

- Row count and table size.
- Existing indexes and index creation cost.
- Whether the database supports online/concurrent index creation.
- Whether DDL is transactional.
- Expected lock duration.
- Replication lag and backup/restore time.
- Impact on connection pools and application latency.

### 9.1. Add Nullable Columns First

Adding a nullable column is usually less risky than adding a `NOT NULL` column requiring immediate backfill, though physical behavior still depends on the database and default expressions.

Workflow:

1. Add a nullable column.
2. Deploy code capable of reading both null and non-null states.
3. Backfill in batches.
4. Verify no nulls remain.
5. Add the `NOT NULL` constraint in a separate migration.

### 9.2. Batch Backfilling

You do not need to execute a single UPDATE over tens of millions of rows during startup migration. Use a checkpointed job instead:

~~~text
while records remain to backfill:
    fetch a batch of IDs
    update batch
    commit
    save checkpoint
~~~

The job must be idempotent so it can resume safely after interruption. Schema migrations can just add columns and indexes; data backfilling can be executed as a separate operational step when it needs significant time.

### 9.3. Indexes and Locking

Some databases support creating indexes without blocking writes for the entire build duration, though the syntax may require running outside a transaction. Flyway/Liquibase must be configured appropriately for such DDL. Do not assume every migration runs inside a single transaction.

## 10. Data Migrations vs. Schema Migrations

These two kinds of changes are related but serve different purposes:

- **Schema migration:** creating/altering tables, columns, constraints, indexes, and views.
- **Data migration:** transforming or backfilling existing data values.

Example status transition:

~~~sql
UPDATE product
SET status = 'ACTIVE'
WHERE status IS NULL;
~~~

This is a data migration even when placed inside a schema migration file.

Before running a data migration:

- Identify which rows need transformation.
- Define old and new values.
- Estimate the expected number of affected rows.
- Determine how to re-run safely.
- Assess duration and locks.
- Have a reconciliation check afterward.

Do not let data migrations depend on random data or environment-specific quirks. If environment-specific configuration values are needed, pass them via controlled mechanisms rather than hardcoding secrets in migrations.

## 11. Organizing Migrations in a Spring Data JDBC Project

A clean layout:

~~~text
src/main/java/
  com/example/catalog/
    product/
      Product.java
      ProductRepository.java
      ProductService.java

src/main/resources/
  db/
    migration/
      V1__create_product.sql
      V2__add_product_status.sql
      V3__add_product_price.sql
~~~

Or with Liquibase:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-product.yaml
        002-add-product-status.yaml
~~~

Migrations do not have to live next to entities in Java packages. Keep them in a standard location so both tools and developers can find them easily.

### 11.1. Mappings Must Match Post-Migration Schema

Example migration adding a column:

~~~sql
ALTER TABLE product
    ADD COLUMN description VARCHAR(1000);
~~~

Entity:

~~~java
@Table("product")
public record Product(
        @Id Long id,
        String sku,
        String name,
        String description
) {
}
~~~

If the column name does not follow the naming strategy, use `@Column`:

~~~java
@Column("product_description")
private String description;
~~~

With Spring Data JDBC, mapping relies on entity metadata and the actual schema. Migrations must be applied before code using the new column runs against the database.

### 11.2. Do Not Rely on Schema Auto-Generation from Entities

Do not treat Java entities as the sole source for automatically updating production schemas. Spring Data JDBC focuses on persistence mapping and lacks an ORM schema auto-update mechanism equivalent to certain JPA setups.

Use a migration tool as the schema source of truth. If local/test environments have separate schema-creation scripts, ensure they do not diverge from the primary migration chain.

### 11.3. Disable Competing Schema Initialization Mechanisms

If a project uses Flyway or Liquibase as its schema manager, prevent another initialization script from independently creating the same tables. Check Spring Boot SQL initialization settings, test schema scripts, and provisioning tools so only one process owns schema changes.

## 12. Configuring Liquibase in Spring Boot

Add the Liquibase core dependency and matching database driver:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    runtimeOnly("org.postgresql:postgresql")
    implementation("org.liquibase:liquibase-core")
}
~~~

Example configuration:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=$DB_PASSWORD

spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.yaml
spring.liquibase.default-schema=public
~~~

Commonly used properties:

| Property | Purpose |
| --- | --- |
| `spring.liquibase.enabled` | Enables/disables Liquibase |
| `spring.liquibase.change-log` | Path to master changelog |
| `spring.liquibase.default-schema` | Default schema |
| `spring.liquibase.contexts` | Selects changesets by context |
| `spring.liquibase.labels` | Selects changesets by label |
| `spring.liquibase.drop-first` | Drops the schema before running; very dangerous if enabled by mistake |
| `spring.liquibase.liquibase-schema` | Schema storing Liquibase management tables |

Property names may vary by Spring Boot version; consult the configuration metadata for your release.

### 12.1. Contexts and Labels

Liquibase can attach contexts or labels to changesets to filter change groups—for example, a changeset strictly for demo data or a specific database group.

Do not use contexts to hide mandatory production migrations or cause environments to have divergent schemas without clear justification. Core structural changes should be applied consistently.

### 12.2. Preconditions

Liquibase supports preconditions to check conditions before executing a changeset, such as database type, schema, or table/column existence. Preconditions are helpful for asserting assumptions, but they do not replace schema inventorying and testing migrations on a copy.

If using `onFail: MARK_RAN`, be very careful: Liquibase can mark a changeset as executed even though the change never ran. Use it only when the condition reliably proves the schema is already in the target state.

## 13. Validating and Operating Migrations

Migrations are part of deployment, not merely something that happens when a developer starts the app.

### 13.1. Pre-Deployment Checks

Before production:

- Review SQL/changelogs just like code.
- Run on a clean database to verify fresh creation.
- Run upgrades from the previous version's schema.
- Verify checksums and migration status.
- Assess locks, duration, and storage.
- Verify backups/restores.
- Verify migration account privileges.
- Confirm the new application version is schema-compatible during rollout.

### 13.2. Flyway `validate` and `info`

Flyway provides administrative operations such as `info`, `validate`, and `migrate`. Depending on integration, you can use the API, Maven/Gradle plugin, or CLI:

- `info`: inspect applied, pending, and current migration statuses.
- `validate`: verify current migrations match history/checksums.
- `migrate`: apply pending migrations.
- `repair`: fix history metadata in well-understood situations.

`repair` is not a way to edit already-released migration files. Use it only after diagnosing the root cause and intentionally aligning actual schema state with history. Never run `repair` solely to silence a checksum mismatch without knowing which changes the database actually received.

### 13.3. Liquibase `status`, `validate`, and `update`

Liquibase has corresponding commands:

- `status`: inspect pending changesets.
- `validate`: validate changelog and changeset structure.
- `update`: apply unexecuted changesets.
- `rollback`: roll back by tag/count/date if changesets have available rollbacks.
- `changelogSync`: sync history without executing changes, used in controlled baselining.

Actual commands can be invoked via plugin, CLI, or API. Inspect status and preview expected SQL before running in production.

### 13.4. Do Not Let All Application Instances Race to Migrate

In multi-instance deployments, ensure migrations execute under the tool's lock/coordination mechanisms and rollout workflow. Flyway and Liquibase manage history/locking internally, yet production pipelines are usually more reliable when running migrations as an intentional step before or during deployment, followed by application rollout.

If the application self-migrates on every instance startup, test behavior under concurrent startups, timeouts, database permissions, and deployment rollback scenarios. For strict production environments, consider a single migration job in the pipeline.

## 14. Testing Migrations

An application test suite running only against a manually created schema can miss migration defects. Test the migration chain itself.

### 14.1. Testing from an Empty Database

Create a fresh database and run all migrations. Then verify:

- Tables, columns, and indexes exist.
- Primary keys, foreign keys, unique, and CHECK constraints are correct.
- Repositories can insert/read/update aggregates.
- Column types and nullability match mappings.

### 14.2. Testing Upgrades from Older Versions

Do not test only from an empty database. Build the schema at a prior version, insert representative data, and then run the new migrations:

~~~text
Create database
  -> apply V1
  -> insert legacy rows
  -> apply V2, V3, V4
  -> verify schema and transformed data
~~~

This catches backfill, default, constraint, and type-conversion bugs against realistic data.

### 14.3. Testing with Testcontainers

Testcontainers lets you run the same database engine as production in integration tests. Example Spring Data JDBC test skeleton:

~~~java
@DataJdbcTest
@Testcontainers
class ProductRepositoryMigrationTest {

    @Container
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }

    @Autowired
    ProductRepository products;

    @Test
    void repositoryWorksWithMigratedSchema() {
        // Insert/read/update an aggregate on the schema created by migrations.
    }
}
~~~

This is an illustrative skeleton; Testcontainers dependencies, database image, migration configuration, and repositories must be configured in the project. Check whether the Spring Boot test slice enables migration auto-configuration properly. If a test slice disables certain auto-configurations, configure them explicitly so migrations run before tests.

### 14.4. Testing Multiple Dialects When Supporting Multiple Databases

SQL migrations written for PostgreSQL may not run on MySQL or SQL Server. If an application claims multi-database support, maintain migration sets and matching tests for each dialect, or use portable Liquibase change types where possible.

Do not treat H2 as sole proof for PostgreSQL/MySQL production; differences in DDL, data types, locking, and functions can let tests pass while production fails.

## 15. Production Deployment Strategy

A deployment pipeline may include:

~~~text
Build application artifact
        |
        v
Review and validate migration
        |
        v
Backup / verify recovery plan
        |
        v
Run migration job
        |
        v
Verify schema and migration history
        |
        v
Deploy compatible application version
        |
        v
Monitor errors and database health
~~~

Exact ordering depends on migration type and rollout strategy. With expand-and-contract, expand migrations can run before the new app; migrations removing old structures must wait until every old consumer has been retired.

### 15.1. Migrate Before or After Application Deploy?

There is no single order for every change:

- **Adding a nullable column:** usually safe to migrate first, as old code ignores the new column.
- **Adding a `NOT NULL` column without a default:** requires backfill or compatible changes beforehand.
- **Renaming/dropping a column:** typically requires multi-release expand-and-contract.
- **Adding a constraint:** verify existing data is valid before enabling.
- **Changing a data type:** may require a shadow column and backfill.

Establish a compatibility matrix between schema versions and old/new application versions before choosing an order.

### 15.2. Backup and Restore

Destructive or high-risk type-changing migrations require backups and a tested restore procedure. An untested backup is not sufficient proof of recoverability.

Migration rollback is not a substitute for backups. If a migration drops a column, rolling back by re-adding an empty column cannot restore lost values.

### 15.3. Post-Migration Monitoring

Monitor:

- Migration history status.
- Application startup errors.
- SQL errors such as missing column/table or type mismatch.
- Latency and lock waits.
- Connection pools and replication lag.
- Row counts after backfill.
- Error rates of affected repositories/queries.

Retain migration logs to investigate which versions ran and how long they took.

## 16. Common Pitfalls

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Editing an already-applied migration | Checksum/history mismatch across environments | Add a new migration |
| Running manual SQL only in production | Other environments cannot reproduce the schema | Keep all changes in version-controlled migrations |
| Adding NOT NULL when table has nulls | Migration fails | Add nullable, backfill, validate, then add constraint |
| Carelessly using baseline | Required migrations get skipped | Inventory schema and baseline at exact version |
| Using repair/changelogSync to hide errors | History no longer reflects real schema | Verify actual state before editing metadata |
| Using both Flyway and Liquibase on one schema | Competing histories and change ordering | Choose a single management tool |
| Testing only on a clean database | Upgrade bugs on legacy data go undetected | Test upgrading from prior schema versions |
| Using H2 instead of production DB | Dialect/DDL differences get missed | Test against the target database |
| Migration updates millions of rows in one transaction | Long locks, timeouts, replication lag | Backfill in batches via checkpointed job |
| Dropping column in same release as code change | Old instances break during rolling deploy | Use expand-and-contract |
| Creating large index inside wrong transaction | Locks or migration failure | Use database-appropriate online/concurrent mechanism |
| Letting every app instance self-migrate | Concurrent startup and DDL privilege control issues | Use coordinated migration job/pipeline |
| Runtime user has unnecessary DDL privileges | Larger blast radius if credentials leak | Separate migration user from application user |
| Assuming DDL rollback restores data | Deleted data does not reappear | Plan forward-fix, backups, and restore |

## 17. When to Choose Flyway vs. Liquibase?

Choose based on your team's needs and workflow:

| Need | Flyway usually fits | Liquibase usually fits |
| --- | --- | --- |
| Team prefers writing direct SQL | Very good fit | SQL changesets can be used |
| Wants simple, readable versioned migrations | Good fit | Supported, though changelog layering is heavier |
| Wants portable structured change descriptions | Less focused on abstraction | Good fit with change types |
| Needs preconditions, contexts, labels | Has mechanisms, different model | Core strength of Liquibase |
| Needs declarative per-changeset rollback | Depends on edition/strategy | Has rollback blocks and auto-rollback for some changes |
| Database relies heavily on vendor-specific SQL | Direct SQL migrations are convenient | SQL changesets/preconditions can be used |
| Project already has migration history | Continue if using Flyway | Continue if using Liquibase |

Do not choose solely by feature count. Weigh reviewability, the team's SQL fluency, target database, deployment pipeline, and operational cost of maintaining migration history.

## 18. Checklist for a New Migration

Before committing a migration, a developer should confirm:

1. Does the migration have a unique name and version/id?
2. Has the file already been applied in any shared environment? If yes, am I accidentally editing an old file?
3. Is the change compatible with currently running application versions?
4. Does the table have existing data needing backfill?
5. Do nullability, defaults, unique constraints, and foreign keys have the right semantics?
6. Are indexes needed; what is the cost of building them on large tables?
7. Is DDL transactional on the target database?
8. How can the migration be retried or recovered if it fails?
9. Is a backup, restore, or forward-fix plan needed?
10. Do integration tests run the migration chain from scratch and upgrade from an older version?
11. Do Spring Data JDBC mappings match the post-migration schema?
12. Are database privileges and deployment ordering defined?

## 19. Workflow from Local to Production

A practical workflow:

1. **Identify schema change:** columns, tables, constraints, indexes, or data conversion.
2. **Create new migration:** use a new Flyway version or Liquibase changeset; never edit applied history.
3. **Update mappings:** update entities, repositories, and queries for the target schema.
4. **Run migrations on a clean local database:** ensure the schema builds from scratch.
5. **Test upgrade:** spin up the old schema with data and run the new migration.
6. **Check compatibility:** can old and new code run together during rollout?
7. **Review performance/locks:** especially ALTERs, backfills, and index creation on large tables.
8. **Run CI integration tests:** against the target database or Testcontainers.
9. **Deploy via migration job:** verify history and schema before rolling out the application.
10. **Monitor post-deploy:** watch startup, query errors, latency, and backfilled data.

## Key Takeaways

Flyway and Liquibase manage schemas as a versioned change history stored in source control and applied in order. Flyway typically uses SQL migrations such as `V1__create_product.sql` and the `flyway_schema_history` table; Liquibase uses changelogs/changesets with id, author, checksum, and the `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK` tables.

In Spring Data JDBC, migrations prepare the schema for entities and repositories to use; they do not replace mappings or domain logic. Choose one tool as the source of truth, never edit applied migrations, baseline legacy databases after inventorying, and test both clean databases and upgrades over existing data. When production uses rolling deployments, apply expand-and-contract so old and new code coexist safely. For large tables or destructive changes, evaluate locks, batch backfills, backups, and forward-fixes before deploying. Finally, execute migrations cleanly in the pipeline and verify schema history before serving traffic with the new application version.

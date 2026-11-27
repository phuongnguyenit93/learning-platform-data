# Separating a JDBC Connection for Migration Tools When Needed

Spring Data Relational R2DBC enables reactive database access via an R2DBC driver and ConnectionFactory. However, many schema management tools such as Flyway and Liquibase commonly integrate with databases over JDBC. When using these tools alongside an R2DBC application, a common architecture is to maintain two connection paths to the same database: R2DBC for runtime business queries and JDBC dedicated to migrations.

The two connection paths have different purposes and lifecycles. JDBC migrations typically run on application startup or in a separate deployment step to create/update the schema. Afterward, the application uses R2DBC to read and write data non-blockingly. Having a JDBC driver on the classpath does not mean R2DBC repositories switch to JDBC, nor does it mean the two connection types can share a single transaction.

This lesson explains when to add JDBC for migrations, how to configure Flyway/Liquibase separately alongside R2DBC, how to manage drivers and credentials, schema deployment ordering, transaction boundaries, testing, and troubleshooting common configuration errors.

## 1. Why Do R2DBC Applications Sometimes Still Need JDBC?

R2DBC and JDBC are two distinct SPIs:

- JDBC provides a blocking database access API, typically using DataSource and Connection.
- R2DBC provides a reactive/non-blocking API, using ConnectionFactory and Publisher.
- Spring Data R2DBC uses R2DBC for repositories, templates, and runtime queries.
- A JDBC-integrated migration tool requires a JDBC driver and DataSource to execute schema management DDL/DML.

A migration tool does not have to use the same connection technology as the business logic layer. It only needs to connect to the right database and apply schema changes before the application depends on that schema.

A common example:

- The application uses Spring Data R2DBC with PostgreSQL.
- Runtime repositories use the R2DBC PostgreSQL driver.
- Flyway uses the PostgreSQL JDBC driver to execute migration files.
- Both connect to the same server, database, and target schema, though each has its own URL, driver, pool, and transaction manager if needed.

### Architecture Diagram

~~~mermaid
flowchart TD
    A[Spring Boot application] --> B[Spring Data R2DBC]
    B --> C[R2DBC ConnectionFactory]
    C --> D[(Database schema)]
    A --> E[Flyway or Liquibase]
    E --> F[JDBC DataSource]
    F --> D
    G[Versioned migration files] --> E
~~~

Migrations and runtime act on the same schema. JDBC is used only on the migration path; repository operations still execute through R2DBC.

## 2. When Should You Separate a JDBC Connection for Migrations?

Separate a JDBC connection when the schema management tool requires JDBC or when the tool's JDBC integration is the stable, supported choice for the target database.

Common cases:

- The project uses Spring Data R2DBC but manages the schema with Flyway.
- The project uses R2DBC at runtime while Liquibase is configured with a JDBC DataSource.
- Migrations rely on tool features or extensions only available via JDBC.
- The deployment pipeline needs to run migrations as a standalone step prior to application rollout.
- The application does not need JDBC for business queries yet still needs a JDBC driver for the migration tool.

Do not add JDBC just because an application uses R2DBC. If the migration tool directly supports another suitable protocol or API, that integration can be used. Verify the requirements of the specific tool version before adding dependencies.

### Benefits of Separating Connections

- Keeps runtime repositories reactive.
- Uses a battle-tested migration tool over JDBC.
- Separates credentials: the application can hold only DML privileges while migrations hold DDL privileges.
- Runs migrations in an independent pipeline or job.
- Controls when schema updates occur before the new application version begins running.

If the project has no tool or library requiring JDBC, adding a JDBC driver and pool only increases dependencies and configuration. Do not add a JDBC starter automatically when only a JDBC driver is needed for migrations; verify the exact modules required by the migration tool.

## 3. Two URL Schemes and Two Connection Types

A common misconfiguration is accidentally using a JDBC URL for R2DBC or vice versa.

PostgreSQL example:

| Purpose | URL Scheme | Spring API |
| --- | --- | --- |
| Runtime access via R2DBC | r2dbc:postgresql://... | ConnectionFactory, R2dbcEntityTemplate, repository |
| Migration via JDBC | jdbc:postgresql://... | DataSource, Flyway, Liquibase |

For MySQL, MariaDB, SQL Server, and other engines, the corresponding scheme names and drivers also differ. Do not swap URL prefixes blindly without verifying driver support.

Both connections must point to the same schema target:

- Same database server or cluster.
- Same database/catalog.
- Same schema if the database distinguishes schemas.
- Same SSL parameters, timezone, search path, or required session settings.
- Accounts with privileges appropriate to each connection's role.

Do not compare hostnames alone. A JDBC URL might point to a different database name or schema than the R2DBC URL, causing migrations to succeed while the application still reports missing tables.

## 4. Dependencies for R2DBC Runtime and JDBC Migrations

An application may need the following dependency groups:

| Group | Role |
| --- | --- |
| Spring Data R2DBC | Reactive repositories and mapping. |
| R2DBC driver | Runtime connection to the database. |
| R2DBC pool (if used) | Pool management for ConnectionFactory. |
| Migration tool | Flyway or Liquibase. |
| JDBC driver | Migration connection if the tool uses JDBC. |
| JDBC pool (if needed) | Manages DataSource for migrations; one-time startup migrations usually do not need a large pool. |

Illustrative example with PostgreSQL and Flyway:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

In some newer Flyway versions, per-database support is split into separate modules. When using such a version, add the corresponding database module, such as the PostgreSQL module, per the dependency guide of the Flyway version managed by Spring Boot or your project's dependency management.

If using Liquibase, dependencies typically include Liquibase core and the database's JDBC driver. Do not configure both Flyway and Liquibase on the same schema unless the project intentionally coordinates two migration systems; normally, pick one tool as the sole source of schema history.

### Do Not Confuse the JDBC Starter with a JDBC Driver

A JDBC driver is the library that communicates with the database over JDBC. The Spring Boot JDBC starter typically pulls in Spring JDBC components and a connection pool. If only a migration tool needs JDBC, only the driver and supported migration dependencies may be required, depending on your Spring Boot version's auto-configuration.

Only add the JDBC starter when the application genuinely needs DataSource/JdbcTemplate or your project's migration setup requires it. When both JDBC and R2DBC are present, explicitly identify which beans belong to migrations and which belong to runtime.

## 5. Configuring R2DBC and Flyway Separately

Spring Boot has separate configuration namespaces for R2DBC and Flyway. Example YAML configuration for PostgreSQL:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db-host:5432/orders
    username: app_runtime
    password: runtime-secret

  flyway:
    url: jdbc:postgresql://db-host:5432/orders
    user: schema_migrator
    password: migration-secret
    locations: classpath:db/migration
    schemas: app
    default-schema: app
    validate-on-migrate: true
~~~

This example illustrates two separate sets of credentials. Real values should come from a secret manager or deployment environment variables—do not commit passwords into source control.

Common Flyway properties include:

- url: JDBC URL used for Flyway.
- user/password: migration credentials.
- locations: location of migration scripts.
- schemas/default-schema: managed schemas.
- validate-on-migrate: verifies history/checksums before applying migrations.
- baseline-on-migrate: enable only when intentionally baselining an existing schema; do not use it to mask migration errors.

Exact property names and whether a separate DataSource is auto-configured depend on the Spring Boot version. Consult the reference documentation for your project's version to confirm how Boot creates a DataSource for Flyway when the main application uses R2DBC.

### Environment Variables

Configurations can be mapped to environment variables at deployment time, for example:

~~~text
SPRING_R2DBC_URL
SPRING_R2DBC_USERNAME
SPRING_R2DBC_PASSWORD
SPRING_FLYWAY_URL
SPRING_FLYWAY_USER
SPRING_FLYWAY_PASSWORD
~~~

Environment variable names follow Spring Boot's relaxed binding rules. Keep credentials in a secret store and grant distinct privileges to runtime and migration accounts.

### Same Server, Different Users

The runtime user typically only needs the SELECT, INSERT, UPDATE, and DELETE privileges required by the application. The migration user may need CREATE, ALTER, DROP, or schema management privileges. Separating accounts limits impact if runtime credentials are exposed.

Do not grant DDL privileges to the runtime user simply so migrations can run under the same account. If migrations run in a separate pipeline, the privileged account only needs to exist during that deployment step.

## 6. Configuring a Separate JDBC DataSource When Needed

Some projects have both a JDBC DataSource and an R2DBC ConnectionFactory—for example, because another JDBC library is present or because the migration bean must be configured manually.

When multiple DataSources exist, specify clearly which DataSource belongs to Flyway or Liquibase. Spring Boot provides specialized qualifiers/annotations for the respective tool's datasource, such as Flyway-specific or Liquibase-specific datasource annotations in supported versions.

Conceptual example of explicit Flyway configuration:

~~~java
@Configuration
public class MigrationConfiguration {

    @Bean
    @FlywayDataSource
    DataSource migrationDataSource(
            @Value("${migration.jdbc.url}") String url,
            @Value("${migration.jdbc.username}") String username,
            @Value("${migration.jdbc.password}") String password) {

        return DataSourceBuilder.create()
            .url(url)
            .username(username)
            .password(password)
            .build();
    }
}
~~~

This example illustrates a DataSource marked for Flyway; driver configuration, pooling, bean naming, and whether Boot auto-creates the Flyway bean must be checked against your version. If manually configuring the Flyway bean, avoid creating two configurations that both run migrations.

For Liquibase, use the corresponding datasource qualifier if supported by your Spring Boot version, or declare the Liquibase bean with an explicit DataSource. Do not let migrations accidentally pick up a primary JDBC DataSource meant for another integration.

### When Both a Primary DataSource and an R2DBC ConnectionFactory Exist

Spring may auto-configure both bean types if the classpath and properties match. Some auto-configurations or libraries may favor a JDBC DataSource, so verify bean initialization conditions and transaction managers.

Guidelines:

- Avoid ambiguous bean names when multiple DataSources exist.
- Explicitly designate the DataSource for Flyway/Liquibase.
- Use R2dbcTransactionManager for R2DBC runtime operations.
- If separate JDBC transactions exist, use a dedicated JDBC transaction manager for that JDBC part.
- Do not assume a single transaction manager coordinates both JDBC Connections and R2DBC Connections simultaneously.

## 7. Configuring Liquibase with JDBC

Liquibase can also run migrations through a JDBC DataSource in an R2DBC application. Spring Boot example:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://db-host:5432/orders
    username: app_runtime
    password: runtime-secret

  liquibase:
    url: jdbc:postgresql://db-host:5432/orders
    user: schema_migrator
    password: migration-secret
    change-log: classpath:db/changelog/db.changelog-master.yaml
    default-schema: app
    liquibase-schema: app
~~~

Key properties:

- url/user/password: JDBC connection for Liquibase.
- change-log: root changelog.
- default-schema: default schema for database objects.
- liquibase-schema: schema holding Liquibase metadata tables if configured separately.
- contexts/labels: select changeset groups suited to the environment if used by the project.

Exact property names and how Boot creates the DataSource can vary by version. Refer to the corresponding Spring Boot and Liquibase documentation, especially when multiple DataSources exist.

Liquibase tracks changeset history via metadata tables, typically DATABASECHANGELOG and DATABASECHANGELOGLOCK. Do not manually delete or edit these tables to bypass errors; resolve changesets and checksums per the tool's guidance.

## 8. Choosing Flyway or Liquibase

Both can manage schemas over JDBC in an R2DBC application. Tool choice depends on how the team manages changes:

| Criterion | Flyway | Liquibase |
| --- | --- | --- |
| Migration format | Typically versioned SQL migrations; other formats supported depending on edition/config. | XML, YAML, JSON, or SQL changelogs. |
| History | Schema history table. | DATABASECHANGELOG and DATABASECHANGELOGLOCK. |
| Style | Focused on an ordered sequence of migrations. | Includes changeset metadata, contexts, labels, and preconditions. |
| Database-specific SQL | Vendor-specific scripts or separate locations can be used. | SQL changesets and database-specific preconditions/contexts can be used. |
| JDBC in Spring Boot | Configure Flyway DataSource/URL. | Configure Liquibase DataSource/URL. |

Do not run both tools to manage the same set of tables in the same schema without a clear ownership boundary. Doing so easily creates two competing migration histories and unpredictable update ordering.

## 9. Organizing Migration Files

With Flyway, a common structure is:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_customers.sql
      V2__create_orders.sql
      V3__add_order_status_index.sql
~~~

Versioned migration names typically follow `V{version}__{description}.sql`. Flyway records applied migrations in the schema history table. Never modify migration files that have already run in shared environments; add a new migration to change the schema.

With Liquibase:

~~~text
src/main/resources/
  db/
    changelog/
      db.changelog-master.yaml
      changes/
        001-create-customers.yaml
        002-create-orders.yaml
~~~

The master changelog includes changesets in order. Each changeset should have a stable id and author. Once a changeset is applied, avoid editing its content in ways that change its checksum outside Liquibase's managed workflow.

### Separating Shared and Vendor-Specific Migrations

If the application supports multiple database engines, you can organize separate locations or changelogs per database. For example, Flyway supports multiple locations and can select locations by profile. Liquibase can use dbms, context, or preconditions to choose changesets.

Do not put multiple vendor syntaxes into one script expecting the database to ignore unrecognized branches. SQL parsers usually parse the entire statement before evaluating conditions. Separate migrations by database or use the tool's official conditional features.

## 10. Migration Execution Order and Application Startup

The application should only receive traffic once the schema is at a compatible version. There are two common patterns.

### Auto-Running Migrations on Application Startup

Spring Boot can auto-configure Flyway/Liquibase and run migrations during application context initialization. When properly configured, beans depending on the schema are used after migrations complete.

Pros:

- Easy to set up for simple applications.
- Migrations run automatically when the deployment starts.
- Can fail fast if a migration fails.

Limitations:

- Every replica may start simultaneously and request migrations at once.
- Runtime instances require DDL credentials.
- Startup duration depends on migration duration.
- Long migrations can make rollouts harder to control.

Migration tools usually have locking/history mechanisms to prevent applying the same migration multiple times, but you must still verify concurrency behavior for your tool version and database. Do not rely on locking as a substitute for a rollout plan.

### Running Migrations as a Separate Deployment Step

In production, it is often easier to control if the pipeline runs migrations once before deploying the new application version:

~~~mermaid
flowchart TD
    A[Build application artifact] --> B[Run migration job with JDBC]
    B --> C{Migration succeeds?}
    C -->|No| D[Stop deployment and investigate]
    C -->|Yes| E[Deploy application replicas]
    E --> F[Application connects with R2DBC]
    F --> G[Health checks and traffic]
~~~

Pros:

- DDL credentials are granted only to the migration job.
- Migrations can be approved and observed separately.
- Avoids multiple replicas running DDL simultaneously.
- Allows verifying the schema prior to rollout.

If choosing this model, disable auto-migration in the runtime app or ensure it does not run a second time unexpectedly. Do not both run migrations in the pipeline and let every replica auto-run migrations without an explicit policy.

## 11. Schema Compatibility When Rolling Out Multiple Versions

When the application has multiple replicas or uses rolling updates, the schema may be accessed simultaneously by old and new versions. Migrations must consider backward compatibility.

A common deployment approach is expand-and-contract:

1. **Expand:** add nullable columns, new tables, or indexes while the old version still runs.
2. **Deploy application:** the new version reads/writes compatibly with the expanded schema.
3. **Backfill:** convert data in batches if needed.
4. **Switch:** move code to the new structure once data is ready.
5. **Contract:** drop old columns or structures in a later release once no old version uses them.

Do not drop or rename columns immediately in the first migration if old replicas are still running queries against those columns.

R2DBC runtime and JDBC migrations access the same schema and therefore must coordinate around version contracts. Completing a migration does not automatically guarantee old and new code are compatible; design migrations to fit the rollout sequence.

## 12. JDBC Migrations and R2DBC Transactions Are Separate Boundaries

An R2dbcTransactionManager manages transactions via the R2DBC ConnectionFactory. Flyway/Liquibase runs via a JDBC DataSource and JDBC Connection. These two connections do not automatically participate in the same transaction.

You cannot assume the following forms an atomic transaction spanning both technologies:

~~~text
R2DBC transaction:
    update application data

JDBC migration connection:
    alter table

Expected: both commit or both rollback
~~~

This is not a distributed transaction. If the migration succeeds and the runtime operation fails, the schema remains altered. If the runtime transaction rolls back, it cannot roll back DDL already committed by the migration connection.

Schema management should be a distinct deployment phase, not mixed into business transactions. For runtime applications, use the R2DBC transaction manager for repository operations requiring atomicity. For migrations, let the migration tool own its transaction and connection.

### DDL Transactionality Depends on the Database

Some databases support transactional DDL for many operations; some statements or database engines perform implicit commits or limit rollback. Do not assume a migration with multiple DDL statements always rolls back completely if the last statement fails. Verify your database's semantics and your migration tool's transaction capabilities.

## 13. Access Privileges and Credential Security

Separating the JDBC connection is an opportunity to separate privileges by role:

| Account | Typical Privileges |
| --- | --- |
| R2DBC runtime user | SELECT/INSERT/UPDATE/DELETE on objects needed by the application. |
| JDBC migration user | CREATE/ALTER/DROP and updates to schema history/changelog metadata. |
| Read-only/reporting user (if any) | SELECT on permitted tables or views. |

Principles:

- Do not hard-code passwords in committed YAML files.
- Use a secret manager, environment variables, or the platform's secret mechanism.
- Do not log URLs containing usernames/passwords.
- Grant DDL privileges only during the migration step.
- Rotate credentials per operational policy.
- Verify the migration user has permissions on both the application schema and the tool's metadata schema.
- Do not use a superuser account if minimal privileges are sufficient for migrations.

If the application runs migrations itself at startup, the runtime process needs DDL privileges. If the migration job is separated, DDL credentials can be omitted from runtime deployments.

## 14. Connection Pools for JDBC Migrations

The R2DBC pool and JDBC pool are independent. Do not use `spring.r2dbc.pool` settings to control the JDBC DataSource.

Migrations are usually short, sequential workloads. A single JDBC connection or a small pool is often enough. Avoid creating a large pool solely to run migrations once at startup.

Factors to consider:

- Do migrations run once per deployment or once per application instance?
- Is the DataSource created by Spring Boot or configured manually?
- Are connections closed after migrations complete?
- Do multiple JDBC tools share the DataSource?
- Are connection and statement timeouts sufficient for long migrations?

If using HikariCP or another JDBC pool, configure it separately for the migration DataSource. Do not share a connection pool with R2DBC because the two SPIs and connection types differ.

## 15. Testing Migrations Together with R2DBC

Integration tests should confirm that both connection paths see the same schema.

A testing pattern with Testcontainers:

1. Start a database container.
2. Build the JDBC URL for Flyway/Liquibase.
3. Build the R2DBC URL for the application.
4. Run migrations over JDBC.
5. Initialize R2DBC repositories.
6. Perform insert/select via R2DBC.
7. Verify tables, columns, constraints, and indexes were created as expected.

Conceptual test example:

~~~java
@Test
void migrationSchemaCanBeUsedThroughR2dbc() {
    // Migration runner uses the JDBC DataSource against the database container.
    // After migration completes, the R2DBC repository uses the same database.
    StepVerifier.create(customerRepository.save(sampleCustomer()))
        .assertNext(saved -> assertNotNull(saved.id()))
        .verifyComplete();
}
~~~

Actual tests must configure the corresponding container, credentials, and URLs. The JDBC URL and R2DBC URL must point to the same container/database/schema; do not rely solely on assuming a shared hostname.

### Testing from an Empty Schema

Always have a test or pipeline job initialize a fresh database from an empty schema. This helps catch:

- Missing migration files or wrong ordering.
- Missing JDBC driver on the migration job's runtime classpath.
- Wrong schema/default schema.
- Unfound changelog or Flyway locations.
- SQL that only works on a different database.
- Runtime mapping mismatches against the migrated schema.

### Testing Upgrades from Older Versions

Beyond an empty schema, test upgrading from the currently deployed schema version. A migration may succeed from scratch yet fail when legacy data, existing indexes, or pre-existing constraints are present.

Test data should include NULLs, duplicates, out-of-range values, and large tables if the migration performs backfills.

## 16. Diagnosing Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Flyway reports driver not found | Missing JDBC driver or Flyway database module. | Check runtime classpath and dependency versions. |
| R2DBC works but migration fails to connect | Incorrect JDBC URL/driver/credentials. | Check spring.flyway.url or spring.liquibase.url and the corresponding driver. |
| Migration succeeds but repository reports missing table | JDBC and R2DBC point to different databases/schemas. | Compare host, database, schema, search path, and user. |
| Boot does not create migration DataSource | Property configuration or auto-configuration does not fit the version. | Check reference docs, condition report, and DataSource beans. |
| Migrations run twice at startup | Both pipeline and runtime auto-run enabled or multiple configs. | Pick a single migration owner. |
| Permission denied during migrate | Migration user lacks DDL or metadata schema privileges. | Check privileges on target schema and history/changelog tables. |
| Checksum validation failed | Migration edited after being applied or artifact mismatch. | Restore historical file or create a new migration per tool guidelines. |
| Runtime user cannot create tables | Runtime credentials attempted DDL with only DML rights. | Run migrations using a dedicated user with DDL rights. |
| Schema changed but old app fails | Migration broke backward compatibility in rolling deployment. | Apply expand-and-contract. |
| JDBC migration runs but R2DBC type mapping fails | DDL created types or defaults incompatible with driver/runtime mapping. | Check schema, R2DBC converters, and integration tests. |

### Driver Not Found

If the error mentions a missing JDBC driver or no suitable driver for the URL, check:

- Is the JDBC driver on the runtime classpath of the process running migrations?
- Does the driver match the database vendor?
- Does the JDBC URL use the right scheme?
- Does your Flyway version require adding a separate database module?
- Was the dependency excluded or scoped only to compile/test?

Do not fix this by adding an arbitrary driver. The driver must match the database server and tool version.

### Migrations Running Against the Wrong Schema

If the history table shows migrations succeeded yet R2DBC repositories cannot find tables, inspect the default schema and search path of both connections. JDBC sessions and R2DBC sessions can have different session configurations even against the same database.

Set the schema explicitly in the migration configuration or name objects according to a uniform convention. If the database supports a schema search path, verify it for both connection types.

## 17. Running Migrations in a Pipeline Instead of Startup

For production environments, you can build a dedicated migration job/artifact using JDBC:

~~~text
Build:
  application artifact
  migration artifact/configuration

Deploy:
  1. Start database dependency
  2. Run migration job with JDBC credentials
  3. Verify migration result
  4. Deploy R2DBC application with runtime credentials
  5. Run health checks
  6. Route traffic
~~~

The migration job can share the same codebase and migration files, while needing only JDBC dependencies and the migration tool. The runtime application only needs the R2DBC driver and DML credentials.

This approach lets application deployments roll back independently of schema migrations, though it does not mean the schema rolls back automatically. If a migration breaks compatibility, a compensating migration or forward-fix deployment is needed per your established strategy.

Do not run concurrent migrations from multiple pipelines against the same schema without coordination. Tool locking does not replace a clear release process.

## 18. Things Not to Do

- Do not switch the entire runtime to JDBC repositories/JdbcTemplate just because a JDBC driver was added to run Flyway.
- Do not use a JDBC URL for spring.r2dbc.url.
- Do not use R2dbcTransactionManager to manage JDBC connections.
- Do not assume JDBC migrations and R2DBC writes are in the same transaction.
- Do not grant DDL privileges to the runtime user if a migration job can be separated.
- Do not run both Flyway and Liquibase on the same schema without ownership boundaries.
- Do not modify versioned migrations already applied in shared environments.
- Do not run migrations on every replica if a dedicated pipeline/job fits better.
- Do not assume a schema created over JDBC is automatically compatible with R2DBC mappings; test reads/writes.
- Do not leave unused JDBC DataSources or drivers around from legacy configurations.

## 19. Implementation Workflow

When an R2DBC application needs to use a JDBC migration tool, implement in this order:

1. **Identify the migration tool:** verify the Flyway/Liquibase version and supported connection protocols.
2. **Select drivers:** add the R2DBC driver for runtime and the JDBC driver for migrations if needed.
3. **Separate URLs:** use an R2DBC URL for ConnectionFactory and a JDBC URL for the migration DataSource.
4. **Separate credentials:** runtime user with DML rights; migration user with schema rights.
5. **Configure the tool:** set location/changelog, schema, validation, and necessary properties.
6. **Choose where to run:** startup auto-migration or a pipeline migration job; pick one primary mechanism.
7. **Ensure ordering:** migrations finish before the schema-dependent application version receives traffic.
8. **Preserve rollout compatibility:** use expand-and-contract when multiple versions coexist.
9. **Test both paths:** run migrations via JDBC, then read/write via R2DBC against the same database container.
10. **Monitor operations:** watch migration history, permission errors, connections, checksums, and schema versions.

Separating JDBC for migrations is a normal architectural choice in Spring Data Relational R2DBC applications. R2DBC continues handling reactive runtime queries; JDBC merely provides a connection for the tool that needs it to manage the schema. When the two URLs, drivers, credentials, and transaction boundaries are configured separately—while ensuring migrations run before the application and verifying the schema over both protocols—a project can use JDBC migration tools while keeping business data access reactive.

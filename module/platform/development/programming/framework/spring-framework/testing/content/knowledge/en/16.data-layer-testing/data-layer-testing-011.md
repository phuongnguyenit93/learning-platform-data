# Migrations and Verifying That the Schema Can Be Initialized

**Context:** Spring Framework Testing → Data-Layer Testing.

Migrations are the mechanism for transitioning a database structure from a known version to a new version. In data-layer testing, you need to prove that a fresh database can be initialized from scratch, migrations apply in the right order, and the resulting schema satisfies the contract required by the application.

An application starting up successfully is not enough to conclude migrations are valid. The application might be connecting to the wrong database, using a schema left over from a previous run, or letting Hibernate auto-create tables so missing migrations go unnoticed. Therefore, tests must control the initial database state and directly observe the post-migration result.

## 1. Goals of Migration Testing

A good migration test answers the following questions:

1. When a database has no business tables yet, can the application initialize the schema?
2. Are all required migrations executed in order?
3. Does the final schema have all essential tables, columns, data types, keys, constraints, and indexes?
4. When upgrading from an older schema version, is existing data preserved or transformed properly?
5. Is ORM configuration masking migration errors by auto-creating or modifying the schema?

These questions belong to different testing levels. Checking migration history shows which versions the tool applied; inspecting metadata or running SQL queries verifies actual structure; starting the Spring ApplicationContext tests end-to-end integration at application startup.

## 2. What Are Migrations and Schemas?

A schema describes the database structure used by the application, such as:

- Tables and columns.
- Data types, lengths, and nullability.
- Primary keys and foreign keys.
- Unique constraints and check constraints.
- Indexes and data-related rules.

A migration is a manageable, repeatable change tracked across version history. For instance, an application starts with a customer table and later adds a customer status:

~~~text
V1: create customer table
V2: add status column to customer
V3: create index on customer.status
~~~

When a fresh database is created, the migration tool applies V1, V2, and then V3. When a database is already at V2, the tool only needs to apply V3. Thus, development, test, and deployment environments can converge to the same schema state from different starting points.

Migrations are typically stored in source control alongside application code. Migration history is part of the deployment contract: the same set of migrations must produce the same database structure across compatible environments.

### Migrations Differ from ORM Auto-Schema Generation

Three mechanisms are frequently confused:

| Mechanism | Role | Suitable For |
|---|---|---|
| Flyway or Liquibase | Manages versioned schema changes | Controlled fresh database creation and upgrades |
| Hibernate DDL | Creates, updates, or validates schema from entity mappings | Development support and mapping compatibility checks |
| SQL initialization such as schema.sql | Runs initialization scripts per configuration | Simple databases or clearly scoped initialization data |

If migrations are the source of truth for the schema, do not let Hibernate use auto-update mode during migration tests. For example, configuring Hibernate with **ddl-auto: update** can add missing columns and let tests pass even when migrations are incomplete.

In integration test environments, you can configure:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

**validate** instructs Hibernate to check whether entity mappings are compatible with the current schema. It does not run migrations and does not alter the schema. This is a useful supplementary check, though it does not replace verifying migrations.

If the project does not use JPA/Hibernate, this setting is unnecessary. When Flyway or Liquibase owns the schema, also avoid enabling another SQL initialization mechanism that tries to create the same tables in a second way.

## 3. Migration Management Tools

Two common tools in Spring applications are Flyway and Liquibase. Choose the tool matching how the project manages its database; a typical application only needs one tool owning migration history.

### 3.1. Flyway

Flyway usually stores migrations as SQL or Java. With versioned SQL migrations, filenames follow this format:

~~~text
src/main/resources/
└── db/
    └── migration/
        ├── V1__create_customer_table.sql
        ├── V2__add_customer_status.sql
        └── V3__index_customer_status.sql
~~~

Example content of the first migration:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(150) NOT NULL
);
~~~

Next migration:

~~~sql
ALTER TABLE customer
    ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE';
~~~

Flyway identifies migrations by version and filename. When running migrations, Flyway records execution history in its metadata table, usually **flyway_schema_history**. This table tells the tool which versions have run and verifies migration checksums.

Principles to uphold:

- Versioned migrations already run on a shared environment must be treated as immutable.
- When schema changes are needed, create a new versioned migration instead of editing old migration files.
- Migration versions must increase in valid order without duplicates.
- Migrations must run on the actual target database, including the right dialect and database version.
- Do not run Flyway's schema clean command on a shared database just to make a test re-runnable.

Flyway also supports repeatable migrations, typically prefixed with **R__**. This type re-runs whenever its checksum changes and suits objects needing re-synchronization such as views or procedures. It follows different lifecycle rules from versioned migrations; do not use repeatable migrations to replace regular schema upgrade history.

### 3.2. Liquibase

Liquibase manages changes via changelogs and changesets. Changelogs can be written in YAML, XML, JSON, or SQL. Abbreviated YAML example:

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
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: name
                  type: VARCHAR(150)
                  constraints:
                    nullable: false
~~~

Liquibase records applied changesets in its history tables, typically **DATABASECHANGELOG** and **DATABASECHANGELOGLOCK**. Applied changesets must also be managed carefully: altering history can break checksum validation or cause environments to have divergent histories.

### 3.3. What Does Checking Migration History Prove?

Migration history shows which changes the tool detected and recorded. It is necessary evidence, yet not sufficient by itself to verify the schema.

For example, history might indicate V1 and V2 ran, while the test still needs to confirm the tables and columns used by the application actually exist. Conversely, merely seeing a table exist does not prove migrations ran: that table could have been created manually or by Hibernate.

Therefore, combine both forms of evidence:

- **Evidence from the migration tool:** no pending migrations remain, history is valid, checksums match.
- **Evidence from the database:** required tables, columns, constraints, and indexes are actually present.

## 4. Spring Migration Integration at Application Startup

### 4.1. With Spring Boot

When appropriate Flyway or Liquibase dependencies are on the classpath and a valid datasource is configured, Spring Boot can auto-configure the migration tool. During ApplicationContext initialization, migrations execute before components that depend on the schema access the database.

Example Flyway configuration:

~~~yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
  jpa:
    hibernate:
      ddl-auto: validate
~~~

With Liquibase:

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Changelog or migration paths must match actual resources in the application. If using a test profile, verify that profile's configuration does not inadvertently disable migrations or point to a different location.

A test using **@SpringBootTest** initializes the context using application configuration. If migrations fail during startup, the test usually fails immediately when Spring creates beans depending on the database. This is a critical signal for catching integration errors.

### 4.2. With Spring Framework Without Spring Boot

Spring TestContext can create an ApplicationContext via **@ContextConfiguration** or **@SpringJUnitConfig**. However, using Spring Framework Testing by itself does not automatically run Flyway or Liquibase.

The application must register and configure the corresponding migration beans, supply the datasource, changelog or migration locations, and ensure migrations finish before initializing repositories, ORMs, or components that access the schema.

When writing tests for plain Spring configurations, clearly identify which bean is responsible for running migrations and that bean's lifecycle. Do not assume Spring Boot's auto-configuration behavior exists in a plain Spring Framework ApplicationContext.

## 5. Designing Repeatable Test Environments

The most important precondition is knowing the exact state of the database before the test runs.

### 5.1. Prefer Dedicated Databases per Test Run

You can use an ephemeral database inside a container or a dedicated test database created for each run. Every migration test run should start from a known state, typically an empty database.

Do not run migration tests against a database shared with development data or real data. Resetting schemas, dropping tables, or running clean commands on a shared database can wipe out other people's data.

### 5.2. Choose the Right Database Engine

H2 or an embedded database can make tests fast, yet SQL migrations may depend on the dialect of PostgreSQL, MySQL, or another DBMS. A migration that passes on H2 is not guaranteed to work on the deployment database.

If migrations use database-specific syntax, data types, sequences, functions, JSON, indexes, or constraints, run integration tests against the exact target engine. Testcontainers is a common way to spin up a real database inside a container for test execution.

### 5.3. Do Not Let Stale Data Mask Bugs

A database with an existing schema from a previous run can prevent tests from catching missing initial migrations. Ensure the test database is genuinely fresh, or explicitly construct an older version state when testing upgrades.

Distinguish clearly:

- Fresh initialization tests: database starts with no business schema.
- Upgrade tests: database starts at a defined migration version and may contain legacy data.
- Repository tests: database has a valid schema and data supporting query scenarios.

These three goals can share infrastructure, but they require distinct starting states.

## 6. Example Migration Test with PostgreSQL and Testcontainers

The following example shows a Spring Boot test starting on a fresh PostgreSQL container, then verifying Flyway applied migrations and the business table exists.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DatabaseMigrationIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    Flyway flyway;

    @Test
    void appliesMigrationsAndCreatesExpectedSchema() {
        // No pending migrations left to apply.
        assertThat(flyway.info().pending()).isEmpty();

        // An applied current migration exists in history.
        assertThat(flyway.info().current()).isNotNull();

        // The business table was created on the fresh database.
        Integer tableCount = jdbcTemplate.queryForObject("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_name = 'customer'
                """, Integer.class);

        assertThat(tableCount).isEqualTo(1);
    }

    @Test
    void createsRequiredColumns() {
        var columns = jdbcTemplate.queryForList("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'customer'
                """, String.class);

        assertThat(columns)
                .contains("id", "name", "status");
    }
}
~~~

This example assumes the project has matching test dependencies, the PostgreSQL driver, Flyway, and migrations creating the **customer** table with the checked columns. The container is freshly created, so the test does not depend on any existing development database.

**@DynamicPropertySource** registers the container's URL, username, and password into Spring configuration before the context is created. As a result, the datasource used by Spring Boot points to the database owned by the test.

The two tests in the example serve distinct purposes:

- The first test checks migration status and verifies the table exists.
- The second test checks the columns the application expects.

In real projects, also verify data types, nullability, foreign keys, unique constraints, or indexes if they form a critical part of the data contract.

Note: schema names and metadata query syntax can differ across DBMSs. On PostgreSQL, **current_schema()** returns the connection's active schema. If the application places tables in a custom schema, configure the search path or specify that schema explicitly in queries.

## 7. Testing Upgrades from an Older Schema

Testing an empty database proves the migration chain can initialize a fresh schema. It does not prove upgrades preserve existing data.

Suppose:

- V1 creates the `customer` table with `id` and `name`.
- V2 adds `status` with default value `ACTIVE`.
- User databases have already run V1 and hold existing records.
- When deploying the new version, V2 must apply without losing existing records.

An upgrade test can follow this sequence:

1. Create a dedicated database.
2. Run Flyway capped at version V1.
3. Insert a record matching V1's structure.
4. Run Flyway uncapped to apply remaining migrations.
5. Read back the record and verify the new column has the expected value.

Example two-stage setup with Flyway:

~~~java
Flyway.configure()
        .dataSource(jdbcUrl, username, password)
        .locations("classpath:db/migration")
        .target("1")
        .load()
        .migrate();

// At this point the database is at schema V1.
jdbcTemplate.update(
        "INSERT INTO customer (id, name) VALUES (?, ?)",
        100L,
        "An"
);

// Run remaining migrations to upgrade to the latest version.
Flyway.configure()
        .dataSource(jdbcUrl, username, password)
        .locations("classpath:db/migration")
        .load()
        .migrate();
~~~

Then verify the data:

~~~java
String status = jdbcTemplate.queryForObject(
        "SELECT status FROM customer WHERE id = ?",
        String.class,
        100L
);

assertThat(status).isEqualTo("ACTIVE");
~~~

This is an abbreviated example: **jdbcTemplate**, **jdbcUrl**, **username**, and **password** must come from a dedicated test database. If migration V2 transforms data rather than just adding a default column, insert representative legacy-state data and assert the exact transformation outcome.

With Liquibase, you can bring the database to an earlier tag or changeset state, insert data at that state, and then run `update` to the current changelog. Specific details depend on how the project structures changelogs and tags versions.

### What to Verify After an Upgrade

Do not merely check that migrations threw no exceptions. Verify:

- Existing records remain intact if business rules require preserving data.
- New values are assigned properly to existing rows.
- Data types or formats are converted accurately.
- New constraints do not break valid existing data.
- Application queries still read data properly after the upgrade.

A migration can complete without error yet produce wrong data outcomes. Therefore, post-upgrade data checks are part of migration testing.

## 8. Verifying the Schema at the Structural Level

Table existence is only the starting condition. The schema must be verified against the contracts the application depends on.

### 8.1. Tables and Columns

Use JDBC metadata or standard views such as **information_schema** to verify table and column names. Metadata queries are generally readable and less coupled to internal migration tool details.

Example column check:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'customer';
~~~

You can confirm required columns exist, data types match, and columns disallow `NULL` when required by contract.

### 8.2. Primary Keys and Foreign Keys

Checking keys catches migrations that create tables yet omit critical relationships or constraints. On PostgreSQL, constraint metadata can be queried via **information_schema.table_constraints**, **key_column_usage**, and **constraint_column_usage**.

Example verifying a table has a primary key:

~~~sql
SELECT COUNT(*)
FROM information_schema.table_constraints
WHERE table_schema = current_schema()
  AND table_name = 'customer'
  AND constraint_type = 'PRIMARY KEY';
~~~

The expected result is typically one primary key for this table. If the design uses a composite key, inspect the set of participating columns rather than only counting constraints.

### 8.3. Unique Constraints and Check Constraints

Unique constraints prevent duplicate data per business rules. Check constraints enforce values within allowed domains.

Besides metadata checks, you can perform intentional write operations to prove the database enforces constraints. For example, insert two records with the same email when email must be unique; the second write must fail with the corresponding constraint error.

This kind of test must run inside an isolated transaction or database so test data does not affect other tests.

### 8.4. Indexes

Indexes can be critical for performance or technical requirements. Checking indexes requires verifying:

- Which table the index belongs to.
- Which columns the index includes.
- Column ordering in composite indexes.
- Whether the index is unique.
- Whether the index has a predicate or special condition.

The existence of an index name does not guarantee its definition is right. On PostgreSQL, you can query **pg_indexes** or matching system catalogs to verify definitions. These queries are database-specific, so place them in tests dedicated to that engine.

Do not mechanically assert every single index. Verify indexes that matter for the schema contract, data integrity, or critical queries.

## 9. Distinguishing Migration Tests from Repository Tests

Migration tests focus on initializing and upgrading the schema. Repository tests focus on data-access behavior over an existing schema.

Example:

| Test Type | Focus | Evidence |
|---|---|---|
| Fresh-database migration | Creating a new schema | Migrations succeed; tables and columns exist |
| Upgrade migration | Transitioning schema versions | Legacy data is preserved or transformed properly |
| Schema contract | Database structure | Column types, keys, constraints, indexes |
| Repository integration | Querying and writing data | Query results, mappings, and transactions |
| Spring context startup | Application configuration integration | ApplicationContext starts cleanly against the new database |

A PostgreSQL Testcontainer can be shared across multiple tests, provided container lifecycle and database state are managed cleanly. If Spring TestContext caches the ApplicationContext, the datasource in that context may keep holding connections to the container. Container and context lifecycles must align so subsequent tests never inherit a datasource pointing to a stopped container.

For **@DataJpaTest**, remember it is a test slice dedicated to JPA. Its default configuration may replace the datasource with an embedded database if available. When the goal is testing migrations on a PostgreSQL container, configure the slice to retain the supplied datasource—such as using **@AutoConfigureTestDatabase(replace = Replace.NONE)** where appropriate. When verifying full application startup, **@SpringBootTest** usually expresses the intent more clearly.

## 10. Common Errors and How to Investigate Them

### Migrations Not Found

Symptom: the application starts yet tables never appear, or the tool reports no migrations to run.

Check:

- Are files located in the expected migration or changelog directory?
- Do filenames follow Flyway's naming convention?
- Are resources packaged onto the classpath?
- Does a test profile override migration locations?
- Does configuration accidentally disable Flyway or Liquibase?

### Test Database Is Not the Expected Database

The test may be connecting to a default database, an embedded database, or a datasource other than the container.

Inspect URLs, usernames, profiles, datasource beans, and properties overridden in **@DynamicPropertySource**. Never conclude migrations are valid merely because the application booted.

### Hibernate Creates Tables Instead of Migrations

If Hibernate uses **create**, **create-drop**, or **update**, tables may exist even when migrations are missing or broken.

Set ORM configuration to match the schema management strategy. When migrations are the source of truth, **validate** is normally used to verify mappings without modifying structure.

### Checksum Mismatch

Checksum errors usually appear when an already-applied migration's content is modified later.

Do not fix this by arbitrarily clearing history or editing checksums in the database. First determine which environment ran the migration, what its original content was, and why the file changed. For already-released versioned migrations, the standard fix is creating a new migration.

### Migrations Succeed on H2 Yet Fail on the Deployment Database

The cause usually lies in differences in dialect, data types, SQL syntax, sequences, functions, or constraints.

Run migration tests on the same database type and a version compatible with the target environment. H2 can remain useful for tests not relying on engine-specific features, yet should not be the sole proof for PostgreSQL or MySQL migrations.

### Tests Pass Individually Yet Fail in the Full Suite

Causes can include tests sharing a schema, execution order dependencies, leftover data, or transactions not rolling back as expected.

Each test needs deterministic starting data. For migration tests, databases isolated per class or per test avoid state left by earlier tests. Do not share one database and rely on test order for the right schema state.

### Migrations Run Yet Post-Upgrade Data Is Wrong

Test data transformation separately. Create input data representing legacy state, run migrations, and verify every critical case: `NULL` values, duplicate values, empty strings, out-of-range values, and records linked via foreign keys.

## 11. Organizing Tests in a Project

A clear test suite can separate tests by goal:

~~~text
src/test/
└── java/
    └── .../
        ├── DatabaseMigrationIT.java
        ├── DatabaseUpgradeIT.java
        ├── DatabaseSchemaContractIT.java
        └── CustomerRepositoryIT.java
~~~

This reflects a separation of responsibilities, not a mandate to create all four classes in every project.

- **DatabaseMigrationIT:** initializes a fresh database and verifies all migrations run.
- **DatabaseUpgradeIT:** builds an older schema version, inserts legacy data, and tests upgrading.
- **DatabaseSchemaContractIT:** verifies critical structural elements such as keys, constraints, and indexes.
- **CustomerRepositoryIT:** verifies repository queries and writes.

For smaller test suites, checks may live in fewer classes. What matters is that test names and input data clearly express their goals so failures immediately point to schema initialization, upgrades, or data access.

In CI, migration tests should run as part of integration testing. Test databases must be created and torn down cleanly. Test output should make clear which migration failed and whether the root cause was SQL, connectivity, permissions, or Spring configuration.

## 12. Practical Guidelines

When building migration and schema tests, follow these guidelines:

1. Use a fresh database or controlled starting state.
2. Let the migration tool actually execute during Spring initialization.
3. Do not let Hibernate modify the schema when the goal is verifying migrations.
4. Check both migration history and actual database structure.
5. Test upgrades from older versions if the application must preserve deployed data.
6. Use the exact target DBMS when migrations rely on dialect or engine-specific features.
7. Verify data after migrations, especially for changes involving data transformations.
8. Never run schema drop/reset commands on a shared database.
9. Separate migration failures from repository failures for clearer investigation.
10. Keep applied migrations immutable and evolve schemas through new migrations.

A migration is considered reliable when it can initialize a fresh database, upgrade an older database cleanly according to rules, and leave the schema and data aligned with application requirements. Tests must provide evidence for all three rather than merely confirming the Spring ApplicationContext booted successfully.


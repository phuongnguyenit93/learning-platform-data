# Data Initialization Order and Hibernate Interaction

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, a Spring Boot application coordinates HTTP clients, databases, caches, message brokers, and Spring Integration adapters. These flows typically depend on **baseline schemas and data**: order tables, deduplication inboxes, event-publishing outboxes, job checkpoint tables, and integration configurations.

An application may work on H2 yet fail to start on PostgreSQL because **Hibernate checks tables before migrations create them**, or because **`data.sql` runs before Hibernate creates the schema**. Worse, enabling multiple schema-modifying mechanisms simultaneously can cause data loss or hard-to-explain discrepancies across environments.

This lesson belongs to the **Initialization and Migration** chapter and focuses on **data initialization order and interaction with Hibernate**. The goal is to understand the mechanisms accurately, choose who owns the schema, configure ordering, handle errors, test, and observe in real integration flows.

After this lesson, you will be able to:

- Distinguish Boot SQL scripts, Hibernate DDL, Hibernate import.sql, Flyway, and Liquibase.
- Explain the default initialization order between schema.sql/data.sql and EntityManagerFactory.
- Use spring.jpa.defer-datasource-initialization for its intended purpose.
- Design the sequence: migration → Hibernate validate → application starts business processing.
- Identify issues with duplicate seeding, schema mismatch, dependent bean ordering, and multi-datasource setups.
- Test against real databases and organize safe migrations for multiple replicas.

> **Principle:** There should be only one mechanism owning **schema changes** per database in a given environment. Database initialization does not automatically guarantee distributed transactions, idempotency, or broker delivery semantics.

## 1. Initialization Mechanisms and Their Relationship with Hibernate

| Mechanism | Source of Data/Definition | Role | Suitable Scope |
| --- | --- | --- | --- |
| **Spring Boot SQL initialization** | schema.sql, data.sql, platform scripts | Runs SQL at startup | Demos/tests, intentional simple seeding |
| **Hibernate schema generation** | JPA entities + ddl-auto | Create, update, or validate schema | Creating tables in dev/test; validating in production |
| **Hibernate import.sql** | import.sql at classpath root | Loads DML when Hibernate creates schema | Demo seeding alongside create/create-drop |
| **Flyway** | Migrations V1__..., V2__... | Versioned schema management and history | Production |
| **Liquibase** | Changelogs and changesets | Versioned/locked schema management | Production |

Crucially, **schema initialization** differs from **data initialization**. A tool creating tables does not imply baseline data exists, and a seed script does not automatically create tables if they do not exist yet.

~~~mermaid
flowchart TD
    A["Spring Boot startup"] --> B{"Schema ownership strategy"}
    B -->|"SQL scripts"| C["schema.sql → data.sql"]
    B -->|"Hibernate dev/test"| D["Hibernate DDL → import.sql / data.sql"]
    B -->|"Production migration"| E["Flyway or Liquibase"]
    C --> F["EntityManagerFactory / JDBC"]
    D --> F
    E --> G["Hibernate ddl-auto=validate"]
    G --> F
    F --> H["Repositories / services"]
    H --> I["HTTP / cache / broker / Integration"]
~~~

The three branches above are **alternative strategies**. Do not read the diagram as running scripts, Hibernate create, and migrations all at the same time.

## 2. Beans Participating in Initialization

The involved components include:

- `DataSource`: supplies JDBC connections, but **does not guarantee tables exist**.
- Boot's SQL script database initializer: handles location and ordering of schema/data scripts.
- `Flyway` or `SpringLiquibase`: applies new schema versions.
- `EntityManagerFactory`: Hibernate builds entity metadata and executes create/update/validate per configuration.
- `JdbcTemplate`, JPA repositories: query after being created and used.
- Application services, message consumers, HTTP handlers, jobs: may require baseline data before processing.

Expected startup flow in a production system:

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant D as DataSource
    participant M as Flyway/Liquibase
    participant H as Hibernate
    participant C as Consumer / Job
    B->>D: Configure connection
    B->>M: Apply pending migrations
    M-->>B: Schema ready
    B->>H: Build EntityManagerFactory
    H->>D: Validate mapping
    H-->>B: JPA ready
    B->>C: Start business processing
~~~

Spring Boot automatically establishes dependencies between many initializers and JPA in standard configurations. For custom beans that spawn threads/queries in constructors or multi-DataSource setups, ensure explicit ordering as well.

## 3. Spring Boot's schema.sql and data.sql

### 3.1. Files and purpose

Common resource names:

~~~text
src/main/resources/
    application.yml
    schema.sql
    data.sql
~~~

`schema.sql` can create tables:

~~~sql
CREATE TABLE integration_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value VARCHAR(500) NOT NULL
);

CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

`data.sql` loads data:

~~~sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true');
~~~

This is illustrative SQL. Data types/schema names, DDL keywords, and insert syntax may vary by database. Production inbox/outbox tables should use proper migrations and exact constraints rather than relying solely on snippets.

Spring Boot recognizes `schema.sql`, `data.sql`, or platform-variant scripts like `schema-postgresql.sql` and `data-postgresql.sql` when configured accordingly. Custom script paths can be set via `spring.sql.init.schema-locations` and `spring.sql.init.data-locations`.

### 3.2. Important properties

~~~yaml
spring:
  sql:
    init:
      mode: always
      encoding: UTF-8
      continue-on-error: false
~~~

| Property | Meaning |
| --- | --- |
| `spring.sql.init.mode` | Mode: embedded, always, or never |
| `spring.sql.init.platform` | Selects database-specific script variants |
| `spring.sql.init.schema-locations` | Where to read schema scripts |
| `spring.sql.init.data-locations` | Where to read seed scripts |
| `spring.sql.init.encoding` | Script character encoding |
| `spring.sql.init.continue-on-error` | Whether to continue after a script error |

By default, Boot usually auto-initializes scripts only on supported **embedded databases** such as H2, HSQLDB, or Derby. Running scripts against external PostgreSQL or MySQL requires explicitly enabling `spring.sql.init.mode=always`.

**Warning:** `always` may re-run scripts **every time the application starts**. If `data.sql` inserts the same primary key, subsequent startups can fail with duplicate key errors. Do not confuse startup seed scripts with history-tracked migrations.

The `never` mode is useful when the schema is already managed by Flyway/Liquibase or a deployment workflow.

## 4. Hibernate ddl-auto and Schema Generation

Spring Boot passes `spring.jpa.hibernate.ddl-auto` to Hibernate's schema management configuration.

| ddl-auto | How Hibernate Behaves | Recommendation |
| --- | --- | --- |
| none | Does not create, alter, or validate schema | Use when schema verification is handled separately |
| validate | Validates mappings against existing schema | Production with Flyway/Liquibase |
| update | Attempts to alter schema to match entities | Suitable only for some dev scenarios, not production migrations |
| create | Recreates schema at initialization | Tests/dev with disposable DBs |
| create-drop | Creates at initialization and drops when SessionFactory closes | Tests/dev with temporary DBs |

If not explicitly set, Boot may default to `create-drop` for recognized embedded databases without a schema manager, or `none` for external DBs / when a schema manager is present. Do not rely on defaults in production environments with data that must be preserved.

Entity example:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "integration_settings")
public class IntegrationSetting {

    @Id
    @Column(name = "setting_key", length = 100)
    private String key;

    @Column(
            name = "setting_value",
            length = 500,
            nullable = false)
    private String value;

    protected IntegrationSetting() {}

    public IntegrationSetting(String key, String value) {
        this.key = key;
        this.value = value;
    }

    public String getKey() { return key; }
    public String getValue() { return value; }
}
~~~

`@Entity` defines mapping expectations. It does not dictate whether the table is created by `schema.sql`, Hibernate, or Flyway. If using `ddl-auto=validate` and the table is missing, startup failure is the right signal: the schema does not satisfy the contract.

`ddl-auto=update` does not provide version history, column rename/drop control, data backfills, or migration-grade rollbacks. Never replace Flyway/Liquibase with Hibernate update in production.

## 5. Default Order: SQL Scripts Before Hibernate

In standard Spring Boot configuration, the SQL initializer runs **before** Hibernate finishes initializing `EntityManagerFactory`.

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant S as SQL initializer
    participant H as Hibernate
    participant A as Application
    B->>S: schema.sql
    S->>S: data.sql
    S-->>B: Scripts completed
    B->>H: EntityManagerFactory
    H->>H: none/validate/update/create
    H-->>B: JPA ready
    B->>A: Services can access DB
~~~

If `data.sql` needs to insert into a table **only created by Hibernate via `ddl-auto=create`**, the script may report `table not found`. If `schema.sql` already created the table and Hibernate `create` recreates it, the result may be a table-exists error or wiped seed data depending on Hibernate's handling.

### 5.1. Strategy A: Scripts create schema, Hibernate only validates

With H2 and Spring Data JPA:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'com.h2database:h2'
}
~~~

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:integration_test;DB_CLOSE_DELAY=-1

  sql:
    init:
      mode: always

  jpa:
    hibernate:
      ddl-auto: validate
~~~

`schema.sql` creates tables, `data.sql` loads data, and Hibernate validates mappings afterward. **Do not enable defer** in this strategy; if Hibernate validates before schema scripts run, it can fail because tables do not exist yet.

### 5.2. Two error-prone configurations

**data.sql running before Hibernate create:**

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
  sql:
    init:
      mode: always
~~~

When only `data.sql` is present, the SQL initializer may execute before Hibernate creates tables.

**schema.sql combined with Hibernate create:**

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create
  sql:
    init:
      mode: always
~~~

If `schema.sql` also creates the entity tables, two mechanisms are competing for DDL ownership. Do not fix this by enabling `continue-on-error=true` and hoping it stabilizes.

## 6. spring.jpa.defer-datasource-initialization=true

This property adjusts the ordering of **Boot SQL script initialization relative to JPA EntityManagerFactory**.

~~~yaml
spring:
  jpa:
    defer-datasource-initialization: true
~~~

When enabled, Boot defers script initialization until **after the relevant EntityManagerFactory instances are initialized**. This allows Hibernate to create tables before Boot runs `data.sql`.

~~~mermaid
sequenceDiagram
    participant B as Spring Boot
    participant H as Hibernate
    participant S as SQL initializer
    B->>H: Initialize EntityManagerFactory
    H->>H: ddl-auto=create-drop creates tables
    H-->>B: Schema exists
    B->>S: Run schema.sql if present
    S->>S: Run data.sql
    S-->>B: Seed completed
~~~

### 6.1. Strategy B: Hibernate creates schema, data.sql seeds

~~~yaml
# application-dev.yml
spring:
  datasource:
    url: jdbc:h2:mem:catalog_dev;DB_CLOSE_DELAY=-1

  jpa:
    hibernate:
      ddl-auto: create-drop
    defer-datasource-initialization: true

  sql:
    init:
      mode: always
~~~

`data.sql`:

~~~sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true');

INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.batch-size', '100');
~~~

Here, **there is no need for `schema.sql`** to recreate the same tables, since Hibernate owns DDL.

### 6.2. When defer=true is inappropriate

- `schema.sql` must create tables **before Hibernate validates**.
- Flyway/Liquibase is the production schema management source.
- You want to delay a business job or broker consumer: this property only adjusts **Boot SQL scripts**, not application-wide scheduling or orchestration.
- You need one-time data seeding across restarts: defer does not provide versioning or deduplication.

**Rule of thumb:** Hibernate creates tables → Boot `data.sql` seeds, consider `defer=true`. Scripts/migrations create tables → Hibernate validates, keep default order.

## 7. Hibernate's import.sql Differs from data.sql

Hibernate reads `import.sql` at the classpath root **when it creates a new schema**, typically with `create` or `create-drop`.

~~~text
src/main/resources/
    application-dev.yml
    import.sql
~~~

~~~sql
-- import.sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true');
~~~

| Characteristic | Hibernate import.sql | Boot data.sql |
| --- | --- | --- |
| Execution engine | Hibernate | Boot's SQL initializer |
| Timing | After Hibernate creates schema in appropriate modes | Follows Boot SQL initialization and dependency order |
| Runs with ddl-auto=validate? | Not under schema-creation import mechanism | Possible, if SQL initializer is enabled |
| Controlled by defer? | No | Yes |
| Has migration history? | No | No |

If both `import.sql` and `data.sql` insert the same primary key, the result is usually a duplicate error or unintended seed data. Choose **one demo/test seeding mechanism**.

Never leave a test-data-loading `import.sql` accidentally on the production runtime classpath alongside `ddl-auto=create`; that combination risks data loss.


## 8. Flyway Manages the Schema Before Hibernate Validates

For production, a clear strategy is to let **Flyway own schema changes**, while Hibernate only checks mapping compatibility.

~~~groovy
// build.gradle (Gradle Groovy DSL), PostgreSQL example
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.flywaydb:flyway-core'

    // Modern Flyway versions use separate database modules:
    implementation 'org.flywaydb:flyway-database-postgresql'

    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Let Spring Boot manage compatible dependency versions; when upgrading Flyway major versions, verify the vendor module required for your database.

~~~yaml
# application-prod.yml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

  flyway:
    enabled: true
    locations:
      - classpath:db/migration

  jpa:
    hibernate:
      ddl-auto: validate

  sql:
    init:
      mode: never
~~~

Meaning:

1. `DataSource` is created from environment configuration.
2. Flyway checks history and runs new migrations.
3. Hibernate creates `EntityManagerFactory` and `validate`s the schema.
4. Repositories/application code run against the managed schema.

Example migration structure:

~~~text
src/main/resources/
  db/
    migration/
      V1__create_integration_tables.sql
      V2__add_source_version.sql
      V3__add_outbox_index.sql
~~~

Contents of `V1__create_integration_tables.sql` for PostgreSQL:

~~~sql
CREATE TABLE integration_settings (
    setting_key VARCHAR(100) PRIMARY KEY,
    setting_value VARCHAR(500) NOT NULL
);

CREATE TABLE processed_events (
    event_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ NULL
);
~~~

Subsequent migration:

~~~sql
-- V2__add_source_version.sql
ALTER TABLE outbox_events
ADD COLUMN source_version BIGINT NOT NULL DEFAULT 1;
~~~

**Do not arbitrarily edit a versioned migration already deployed**, because history/checksums will no longer match. Create a new migration and follow a safe data-change workflow.

The scripts above use PostgreSQL syntax and do not apply verbatim to H2 or MySQL. Critical SQL tests must run against the same database type as production.

## 9. Liquibase as an Alternative Strategy

Liquibase provides changelogs and changesets tracked via its own history tables. If Liquibase is chosen, do not simultaneously allow Flyway to modify the same group of tables.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.liquibase:liquibase-core'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

~~~yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml

  jpa:
    hibernate:
      ddl-auto: validate

  sql:
    init:
      mode: never
~~~

Illustrative YAML changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: create-integration-settings
      author: integration-team
      changes:
        - createTable:
            tableName: integration_settings
            columns:
              - column:
                  name: setting_key
                  type: varchar(100)
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: setting_value
                  type: varchar(500)
                  constraints:
                    nullable: false
~~~

Boot arranges for Liquibase to complete schema updates before JPA uses the database in standard configurations. However, if you define a custom `SpringLiquibase`, multiple DataSources, or custom beans that query the DB early, still verify dependency ordering.

### 9.1. Critical seed data should have history

If `integration_settings` is mandatory reference data in production, put it inside a Flyway migration/Liquibase changeSet. Illustrative PostgreSQL UPSERT:

~~~sql
INSERT INTO integration_settings(setting_key, setting_value)
VALUES ('catalog.sync.enabled', 'true')
ON CONFLICT (setting_key) DO NOTHING;
~~~

If operators adjust settings after deployment, migrations must not overwrite those values on every startup. Clearly establish whether data is code-owned or operations-owned.

## 10. Hibernate Validate and Mapping Changes

If an entity adds a new non-null field, such as `sourceVersion`, and the current table lacks the column, Hibernate `validate` can report a schema mismatch:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    @Column(name = "order_id")
    private String id;

    @Column(
            name = "source_version",
            nullable = false)
    private Long sourceVersion;

    protected OrderEntity() {}
}
~~~

The migration should run before the code version requiring the column:

~~~sql
ALTER TABLE orders
ADD COLUMN source_version BIGINT;

UPDATE orders
SET source_version = 1
WHERE source_version IS NULL;

ALTER TABLE orders
ALTER COLUMN source_version SET NOT NULL;
~~~

On very large tables, a single full-table UPDATE or adding NOT NULL can hold locks for a long time. Consider **expand–migrate–contract**:

1. **Expand:** add columns/tables compatible with the older version.
2. **Deploy:** new code can read/write both transitional structures.
3. **Backfill:** update old data in batches with checkpoints and progress tracking.
4. **Contract:** drop old structures after all instances have upgraded.
5. **Validate:** verify JPA mappings, integration queries, and consumers against the new schema.

`ddl-auto=validate` catches partial entity/schema mismatches; it does **not** fully verify indexes, business unique constraints, query performance, historical data, or HTTP/broker contracts. Additional tests are still required.

## 11. Initialization Order of Database-Dependent Beans

Boot recognizes several beans as database initializers (script initializer, Flyway, Liquibase, and appropriate JPA components) to establish dependency order. However, a custom bean may query the DB in its constructor or `@PostConstruct` before initialization finishes if it lacks proper dependencies.

Example bean reading config after schema/data are loaded:

~~~java
// IntegrationConfigWarmup.java
import org.springframework.jdbc.core.JdbcTemplate;

public class IntegrationConfigWarmup {

    public IntegrationConfigWarmup(
            JdbcTemplate jdbcTemplate) {
        jdbcTemplate.queryForList(
                "SELECT setting_key, setting_value "
                        + "FROM integration_settings");
    }
}
~~~

Declaring the database initialization dependency for the bean:

~~~java
import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration(proxyBeanMethods = false)
public class WarmupConfiguration {

    @Bean
    @DependsOnDatabaseInitialization
    IntegrationConfigWarmup integrationConfigWarmup(
            JdbcTemplate jdbcTemplate) {
        return new IntegrationConfigWarmup(jdbcTemplate);
    }
}
~~~

`@DependsOnDatabaseInitialization` expresses that this bean must be created after Boot-detected initializers. It does not force external services (HTTP/broker) to be ready, nor does it guarantee that a background task outside the Spring lifecycle will wait.

### @PostConstruct, ApplicationRunner, and background consumers

- `@PostConstruct`: can access the DB if the bean has the right dependencies, but is unsuitable for running large migrations or repeatable side effects.
- `ApplicationRunner`/`CommandLineRunner`: runs after the context is created; useful for quick checks/warmups, **not** a replacement for history-tracked migrations.
- Quartz jobs, Spring Integration pollers, and broker listeners: must coordinate startup/readiness so they do not query a schema mid-change.
- Beans spawning threads in constructors: hard to manage ordering, shutdown, and retries; use Spring lifecycle mechanisms instead.

If cache warm-up or HTTP synchronization has side effects, idempotency and checkpoints are required; merely running "after migrations" is not enough to be safe across multiple replicas.

## 12. Multi-DataSource: Multiple Databases Need Multiple Initializers

An application may connect to an **orders DB** and a **reporting DB**. `spring.datasource.*` plus a single default initializer does not automatically migrate both.

~~~mermaid
flowchart TD
    A["Spring Boot"] --> B["Orders DataSource"]
    A --> C["Reporting DataSource"]
    B --> D["Orders migrations"]
    C --> E["Reporting migrations"]
    D --> F["Orders EntityManagerFactory"]
    E --> G["Reporting JdbcTemplate / JPA"]
    F --> H["Use case / Integration flow"]
    G --> H
~~~

Requirements:

1. Define separate `DataSourceProperties`/`DataSource` beans by prefix.
2. Mark `@Primary`/`@Qualifier` beans explicitly where needed.
3. Bind a Flyway/Liquibase/SQL initializer explicitly to **each appropriate datasource**.
4. Create `EntityManagerFactory`/repositories/transaction managers for the right source.
5. Ensure custom beans depend on the initializer of **the database they use**.
6. Verify at runtime that you never accidentally migrate a production database toward a test database or vice versa.

Spring Boot offers mechanisms to select a migration datasource such as `@FlywayDataSource` and separate connection settings; with multiple databases, you may need multiple Flyway/Liquibase instances. Do not assume that putting two URLs in YAML makes Boot create two initialization pipelines automatically.

**Transactions across different DBs:** `@Transactional` with a single transaction manager does not atomically commit across the orders DB, reporting DB, Redis, and a broker. You may need outbox, saga, event-driven synchronization, or reconciliation.

### R2DBC differs from JDBC/Hibernate

R2DBC uses `ConnectionFactory` and `spring.r2dbc.*`, whereas standard Hibernate ORM uses a JDBC `DataSource`. Do not use `spring.jpa.defer-datasource-initialization` as a switch to control all reactive data sources. When using both stacks, identify exactly which initializer and beans belong to which source.

## 13. Seed Data, Idempotency, and Integration Contracts

Classify data before deciding how to seed:

| Data | Example | Suggested Management |
| --- | --- | --- |
| Demo/test fixtures | A few fake products | data.sql/import.sql in dev/test only |
| Versioned reference data | Event types, status codes | Migrations with clear ownership |
| Operator-edited config | Enable flags, rate limits | Config service or admin DB |
| Business records | Orders/payments | Business transactions |
| Inbox/outbox/checkpoints | Event IDs, unpublished messages, cursors | SQL transactions/idempotency |
| Search/cache projections | Elasticsearch/Redis | Rebuild from authoritative source |

**Do not truncate or reset inbox/outbox tables at startup** just to keep the environment "clean," because events can be reprocessed or unpublished messages lost. Migrations must preserve data according to contract.

A seed statement like `INSERT ... ON CONFLICT DO NOTHING` avoids duplicate inserts in the database, but **does not replace** an idempotent consumer. To handle broker redelivery, you need stable event IDs, unique constraints/atomic claiming, and a shared transaction between marking the event and performing the business change.

Similarly, Flyway completing migrations **does not** make an outbound HTTP POST to a partner participate in a SQL transaction. If writing to the DB and then publishing to a broker, consider transactional outbox and consumer idempotency.

## 14. Safe Deployment with Multiple Replicas

During a rolling deployment, old and new versions may share the database simultaneously. Schema changes must consider:

- **Compatibility window:** do old APIs/repositories still query old fields/tables?
- **Lock contention:** do DDL and backfills hold locks for long durations?
- **Migration ownership:** does app startup or a dedicated migration job run DDL?
- **Permissions:** does the runtime DB user really need DDL permissions?
- **Readiness:** can the application accept HTTP/messages before the schema is compatible?
- **Recovery:** if a migration fails halfway, what state are the DB and migration history in?
- **Observability:** migration duration, applied version, job/consumer lag, and startup errors.

Flyway/Liquibase provide history/locking mechanisms to help prevent concurrent processes from applying changes simultaneously, yet they do not automatically turn heavy DDL migrations into zero-downtime operations.

Prefer backward-compatible migrations; drop columns only after old versions have stopped using them. When large backfills are needed, use measurable batches/checkpoints instead of putting all logic inside an `ApplicationRunner` on every deploy.

## 15. Testing Initialization Order

### 15.1. Testing SQL scripts before Hibernate validate

In an H2 test, configure:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:validation_test;DB_CLOSE_DELAY=-1
  sql:
    init:
      mode: always
  jpa:
    hibernate:
      ddl-auto: validate
    defer-datasource-initialization: false
~~~

With `schema.sql`/`data.sql` and matching entities, you can assert data after context initialization:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class InitializationOrderTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void seedIsAvailableAfterStartup() {
        String value = jdbcTemplate.queryForObject(
                """
                SELECT setting_value
                FROM integration_settings
                WHERE setting_key = ?
                """,
                String.class,
                "catalog.sync.enabled");

        assertEquals("true", value);
    }
}
~~~

### 15.2. Testing Hibernate create followed by data.sql

Dedicated test configuration:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
    defer-datasource-initialization: true
  sql:
    init:
      mode: always
~~~

With an embedded database and JPA entities having matching tables, Hibernate creates the schema and `data.sql` loads data. The test should verify data exists after startup. **Do not include `schema.sql` recreating the tables**.

### 15.3. Testing migrations with a production-like database

For production PostgreSQL, use PostgreSQL Testcontainers/test instances to verify:

- From an empty database, migrations create the expected tables/columns/indexes.
- Hibernate `ddl-auto=validate` starts successfully.
- Re-running migrations does not duplicate seed data.
- Unique constraints prevent duplicate `event_id` processing.
- Older schema versions can upgrade to the new version.
- Migration failures cause fail-fast startup, preventing consumers from processing incomplete data.

Skeleton:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class MigrationAgainstPostgresTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("integration_test");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                postgres::getUsername);
        registry.add(
                "spring.datasource.password",
                postgres::getPassword);
    }

    @Test
    void migrationsFinishedBeforeApplicationUsesDatabase() {
        // Real assertions must query tables, migration history, and constraints.
    }
}
~~~

This is a test skeleton requiring Testcontainers/JUnit dependencies, migration fixtures, a container runtime, and real assertions. A test that only checks context startup without verifying constraints/schema history is insufficient.

### 15.4. Spring Test `@Sql` differs from Boot `data.sql`

Spring Test's `@Sql` loads scripts at test lifecycle moments according to its configuration; `data.sql` is handled by Boot's SQL initializer during application context startup. Do not use `@Sql` to mask broken production initializer ordering. With test transaction rollbacks, understand the transaction mode and when `@Sql` executes.

## 16. Common Errors and Diagnostics

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `data.sql` reports table not found | SQL scripts ran before Hibernate create | Use `defer=true` when Hibernate creates schema, or move schema to scripts/migrations |
| Hibernate validate reports missing table | Migration/script hasn't run or wrong schema/search path | Check ordering and actual database/schema |
| Table already exists during Hibernate create | Both `schema.sql` and Hibernate perform DDL | Pick a single schema owner |
| Seed data duplicated after restart | `data.sql` executed repeatedly | Use migrations/UPSERT or seed in tests only |
| Seed data disappears | Hibernate create recreated tables after scripts seeded | Stop combining two out-of-order DDL sources |
| `import.sql` doesn't run | Hibernate is not in schema-creation mode | Check `ddl-auto` and classpath root |
| `import.sql` collides with `data.sql` | Two seed sources inserting same IDs | Keep only one source |
| Flyway checksum mismatch | Already-applied migration was edited | Create a new migration; repair history per procedure |
| Liquibase lock held | Interrupted run or migration still executing | Inspect status/owner and handle safely |
| Prod behaves differently from H2 tests | Different SQL dialects, constraints, transactions | Use Testcontainers with matching vendor |
| Custom bean queries before seed | Missing dependency on database initialization | Use appropriate annotation or lifecycle hook |
| Second DB missing schema | Missing dedicated migrator/initializer | Configure multi-datasource explicitly |
| Consumer processes before migrations | Asynchronous startup or wrong readiness | Gate lifecycle and fail-fast |

Diagnostic sequence:

1. Check URL, database schema, and active profile (without printing passwords).
2. Identify who owns DDL and the `ddl-auto` value.
3. Check `spring.sql.init.mode`, scripts, and `defer-datasource-initialization`.
4. Inspect the stacktrace of the **first error** from SQL initializer/Flyway/Liquibase/Hibernate.
5. Check migration history, locks, and DDL permissions if applicable.
6. Reproduce from an empty database or older schema version using a matching-vendor test.
7. Verify consumers/jobs do not access the DB prematurely.

**Do not apply temporary hacks** like `ddl-auto=update` in production, `create-drop`, `continue-on-error=true`, or deleting migration history. Such actions hide errors and risk data loss.

## 17. Pre-Deployment Checklist

- [ ] One clear **schema owner** per database: scripts, Hibernate dev/test, or migration tool.
- [ ] `ddl-auto` set explicitly; production prefers `validate` with a migrated schema.
- [ ] Default order understood: **schema.sql → data.sql → Hibernate**.
- [ ] `defer-datasource-initialization=true` used only when scripts should run after Hibernate creates the schema.
- [ ] `import.sql` and `data.sql` do not seed duplicates.
- [ ] Flyway/Liquibase maintain history; migrations are reviewed and checked for compatibility.
- [ ] Production data is never reset; inbox/outbox/checkpoint tables are preserved.
- [ ] Multi-datasource setups have properly wired initializers and transaction managers per source.
- [ ] Consumers, Quartz jobs, and cache warm-ups wait for required schema/data.
- [ ] Tested from both empty schema and older schema on a production-like database.
- [ ] Expand–migrate–contract workflow, checkpointed backfills, and migration observability are in place.
- [ ] HTTP, broker, and database side effects still have their own idempotency, transactions, and retries.

**Conclusion:** `spring.jpa.defer-datasource-initialization` only adjusts the **order of Boot SQL scripts relative to Hibernate**; it does not replace versioned migrations. For demos/tests, Hibernate can create tables and `data.sql` can load data. For production, the reliable architecture is **Flyway/Liquibase evolving the schema → Hibernate validating → the application accepting integration work**, combined with testing against old data, transactions, idempotency, and observability.

## References

- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): scripts, Hibernate, defer initialization, and schema managers.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JPA, and SQL integration.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): profiles, env, and property precedence.
- [Spring Framework — Executing SQL Scripts in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): @Sql and test lifecycle.
- [Hibernate ORM — Schema Generation](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#schema-generation): schema actions and import.sql.
- [Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations): versioned migrations and history.
- [Liquibase — Changelogs](https://docs.liquibase.com/concepts/changelogs/home.html): changesets and schema changes.

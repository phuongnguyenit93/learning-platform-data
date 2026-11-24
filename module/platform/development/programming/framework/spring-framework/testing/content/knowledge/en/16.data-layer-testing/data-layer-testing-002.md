# Choosing Between an Embedded Database and the Production-Like Engine

When testing the data layer, the choice of database directly affects the reliability of test results. An embedded database such as H2 starts quickly, runs in-process during tests, and makes it inexpensive to verify many CRUD operations. However, if the application deploys on PostgreSQL, MySQL, or another specific engine, an embedded database does not necessarily reproduce the SQL dialect, data types, transactions, locking, or constraints of the real environment.

Therefore, the question is not just which database is easier to configure. You need to determine what the test aims to prove: basic repository logic, database engine compatibility, migrations, transactions, engine-specific queries, or concurrency behavior. Choosing the database based on the goal helps balance feedback speed and confidence.

## What Characteristics Do the Two Options Have?

### Embedded Database

An embedded database runs inside the test application or is integrated directly into the process. Common options in the Java ecosystem include H2, HSQLDB, and Apache Derby. Spring JDBC provides an API to create embedded databases via `EmbeddedDatabaseBuilder`.

An embedded database can run in memory or use files depending on the engine and configuration. In testing, an in-memory configuration is typically chosen because creating a fresh environment is fast and cleanup is simple.

Typical characteristics:

- Fast startup with no need to manage a separate database server.
- Easy to recreate per test suite or ApplicationContext.
- Suitable for tests requiring frequent fast feedback loops.
- Can execute real SQL and verify mappings and basic repositories.
- SQL and transaction behavior depend on the embedded engine and may differ from production.

An embedded database is still a real database engine, complete with a SQL parser, transactions, and constraints. It is not a mock. However, it only proves behavior on that specific engine.

### Production-Like Database Engine

This option means tests use the same database engine as the application's deployment environment, such as PostgreSQL for PostgreSQL, MySQL for MySQL, or SQL Server for SQL Server. The database can run via Testcontainers, a dedicated service in CI, a local database, or a dedicated test instance.

Typical characteristics:

- SQL dialect and many engine behaviors closely match the deployment environment.
- Enables testing native queries, data types, constraints, sequences, locking, and real migrations.
- Catches engine-specific differences early that an embedded database cannot simulate.
- Startup and environment preparation typically take more time.
- Requires managing versions, resources, data, and CI execution capability.

Using the same engine does not mean tests should connect to the production database. You should create a dedicated test database or container with synthetic data and restricted access permissions.

## Quick Comparison

| Criterion | Embedded Database | Same Engine as Production |
|---|---|---|
| Startup time | Usually fast | Usually slower due to server/container startup |
| Required infrastructure | Usually just a Java dependency | Requires Docker, a database service, or equivalent |
| SQL dialect | Follows the embedded engine | Close to the deployment engine |
| Engine-specific data types | May be missing or simulated differently | Can be tested directly |
| Native queries | Reliable only if compatible with the embedded engine | Suitable for verifying queries on the target engine |
| Transactions and locking | May differ in isolation, locks, and concurrency | Closer to actual engine behavior |
| Migrations | Tests some migrations if dialect is supported | Tests migrations on the exact engine and version |
| Running many tests | Easy to create fresh databases at low cost | Requires optimizing containers, schema, and data |
| Suitability for fast tests | High | Can be more costly |
| Suitability for compatibility checks | Limited | Higher |

Neither option automatically fits every test. An embedded database optimizes for fast feedback loops; a same-engine database optimizes for confidence in engine-dependent behaviors.

## Database Differences That Can Skew Test Results

A repository test passing on H2 does not guarantee the same query will work on PostgreSQL or MySQL. Differences can emerge across multiple layers.

### 1. SQL Dialect and Syntax

Engines can differ on:

- String, date/time, JSON, and data-type manipulation functions.
- Pagination syntax such as `LIMIT/OFFSET`, `FETCH FIRST`, or variants.
- Upsert syntax, such as `ON CONFLICT`, `ON DUPLICATE KEY`, or `MERGE`.
- Syntax for retrieving generated keys and sequences.
- Record locking syntax such as `SELECT ... FOR UPDATE`.
- DDL syntax, conditional indexes, and constraints.

For example, a query using PostgreSQL-specific features may run normally on PostgreSQL but not be supported by H2 or carry different semantics. If tests use H2, compatibility errors may only surface after deployment.

### 2. Data Types and Conversions

Some data types do not map identically across engines:

- UUID may be stored as a native type or as a string.
- JSON/JSONB differs in querying and indexing capabilities.
- Boolean values may be represented differently.
- Timestamps with or without time zones follow different conversion rules.
- Decimal types may differ in scale, rounding, and overflow behavior.
- Arrays, enums, binary data, and large objects may have engine-specific support.

If the application uses specialized data types, testing on the same engine provides much more reliable evidence of mapping and conversion behavior.

### 3. Collation, Case Sensitivity, and String Comparison

Searching for emails or usernames can behave differently depending on collation and case-sensitivity settings. A query comparing `'Lan'` with `'lan'` may return different results across engines or collations.

Other differences include:

- Sorting Vietnamese diacritics and Unicode characters.
- Comparing strings with trailing whitespace.
- Accent-sensitive vs. accent-insensitive comparisons.
- Unique constraints on case-insensitive strings.

If business logic relies on specific comparison rules, test on the engine and collation the application will use.

### 4. Transactions, Isolation, and Locking

Databases can differ in default isolation levels, MVCC, lock granularity, deadlock detection, and handling of concurrent updates.

For example, a test verifying two transactions updating a balance concurrently might pass on an embedded database yet behave differently on the production database. A test using `SELECT FOR UPDATE` also needs the engine to enforce the proper locking semantics.

When verifying:

- Lost updates or optimistic/pessimistic locking.
- Transaction isolation.
- Deadlocks and lock timeouts.
- Concurrent inserts into unique keys.
- Transaction rollbacks across multiple operations.
- Commit and visibility behavior across connections.

you should use the same engine and configuration close to the deployment environment. Concurrency tests must manage multiple actual connections/transactions; running a single test method inside one transaction does not prove concurrent behavior.

### 5. Constraints, Generated Keys, and Sequences

Engines have their own rules for identity columns, auto-increment, sequences, default values, and constraints. For example, a sequence may advance even if a transaction rolls back; retrieving generated keys may work differently; some constraints are checked immediately per statement, while others may be deferred until the end of the transaction if the engine supports it.

If the application depends on those behaviors, testing on the same database engine is essential.

### 6. DDL and Migrations

A migration might run cleanly on H2 yet fail on PostgreSQL due to syntax differences, locking order, or DDL support. Some databases perform implicit commits on DDL; schema-change rollback behavior varies across engines.

Migration tests should create a clean database, run the exact migration sequence used by the application, and verify the resulting schema state. If the application deploys on a specific engine, run migrations on that engine.

## When Is an Embedded Database a Reasonable Choice?

An embedded database is appropriate when tests need to verify portable data-layer logic that does not depend on production engine-specific features.

Common cases include:

- Repositories performing basic CRUD through Spring JDBC.
- Standard SQL queries not using features specific to one engine.
- Simple entity mappings that do not depend on a specific dialect.
- Verifying service coordination with repositories in a small context.
- Large test suites needing fast database initialization for frequent feedback.
- Verifying fixture data, basic constraints, and simple queries.

For example, a repository finding a customer by email using a simple SQL query can be tested on H2 if the schema and SQL statement are compatible:

~~~java
@Repository
class CustomerJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    CustomerJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    Optional<String> findNameByEmail(String email) {
        return jdbcTemplate.query(
            "select name from customer where email = ?",
            rs -> rs.next()
                ? Optional.of(rs.getString("name"))
                : Optional.empty(),
            email
        );
    }
}
~~~

If the test only needs to prove the repository maps results of a portable query properly, H2 can be a fast choice. However, if the application runs on PostgreSQL and queries use JSONB, arrays, operators, or custom collations, H2 is insufficient to prove compatibility.

## Creating an Embedded Database with Spring JDBC

Spring JDBC provides `EmbeddedDatabaseBuilder` to create an embedded database from Java configuration and execute schema/fixture scripts.

The H2 dependency must be declared in test runtime, for example with Gradle:

~~~groovy
dependencies {
    testImplementation("org.springframework:spring-jdbc")
    testRuntimeOnly("com.h2database:h2")
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

Configuration example:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;

@Configuration
class EmbeddedDatabaseTestConfig {

    @Bean(destroyMethod = "shutdown")
    EmbeddedDatabase dataSource() {
        return new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .addScript("classpath:db/schema.sql")
            .addScript("classpath:db/reference-data.sql")
            .build();
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

`EmbeddedDatabaseBuilder` creates an H2 database and runs scripts in the declared order. The bean specifies destroy method `shutdown` to close the database when the context shuts down.

A test using this configuration via the Spring TestContext Framework:

~~~java
@SpringJUnitConfig(EmbeddedDatabaseTestConfig.class)
class CustomerJdbcRepositoryTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    CustomerJdbcRepository repository;

    @Test
    void findsCustomerByEmail() {
        jdbcTemplate.update(
            "insert into customer(id, email, name) values (?, ?, ?)",
            1001L,
            "lan@example.test",
            "Lan"
        );

        assertThat(repository.findNameByEmail("lan@example.test"))
            .contains("Lan");
    }
}
~~~

This example assumes the test configuration also registers the `CustomerJdbcRepository` bean, the schema has corresponding columns, and the test class imports the appropriate assertions. The goal is to illustrate how Spring creates an embedded database, injects DataSource/JdbcTemplate, and runs the repository against a real database inside the test process.

`EmbeddedDatabaseType.HSQL` or `EmbeddedDatabaseType.DERBY` can be used if the corresponding dependency is present. Specific configuration depends on the engine and library version.

### Advantages and Limitations of Embedded Databases in Spring

Advantages:

- No need to manage an out-of-process database server.
- Easy to create a fresh database for each ApplicationContext.
- Schema and data scripts can live in test resources.
- Well-suited for tests run frequently in the IDE and local builds.
- Can combine with Spring's test-managed transactions.

Limitations:

- SQL running on H2 is not guaranteed to be compatible with the deployment engine.
- Embedded configuration does not verify production networking, authentication, or connection pooling.
- Some data types, indexes, functions, and locking have different semantics.
- Tests may inadvertently rely on more permissive behavior of the embedded engine.
- Migration tests are only trustworthy to the extent migrations are actually compatible with the embedded engine; they do not prove production migrations work.

Do not treat H2's compatibility mode as proof that H2 has become PostgreSQL or MySQL. Compatibility mode may support some syntax, but it does not reproduce the entire behavior of the target engine.

## When Is the Same Engine as Production Needed?

Use the same engine when test outcomes depend on features or semantics specific to the production database.

Examples:

- Repositories using native SQL or engine-specific functions.
- Applications using JSONB, arrays, enums, full-text search, or database extensions.
- Migrations creating specialized indexes, triggers, sequences, stored procedures, or constraints.
- Locking behavior, transaction isolation, or concurrent updates being part of the requirements.
- Applications depending on specific collations, time zones, generated columns, or custom data types.
- Needing to verify complex queries and execution plans on the actual engine.
- Needing to check compatibility with the deployed database version.

Using the same engine is also valuable when a team has previously encountered bugs that only occurred in production due to database differences. In such cases, testing against the exact engine reproduces behavior more closely and reduces the gap between local, CI, and deployment environments.

## Using Testcontainers to Run the Same Database Engine

Testcontainers launches a database service inside a container dedicated to tests. For PostgreSQL, you can use the PostgreSQL module and JUnit Jupiter integration.

Example Gradle dependencies:

~~~groovy
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testRuntimeOnly("org.postgresql:postgresql")
}
~~~

Example test using a PostgreSQL container:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringJUnitConfig(PostgresTestConfig.class)
class CustomerRepositoryPostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void registerDatabaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add("test.datasource.url", postgres::getJdbcUrl);
        registry.add("test.datasource.username", postgres::getUsername);
        registry.add("test.datasource.password", postgres::getPassword);
    }

    @Test
    void runsAgainstPostgres() {
        // Execute queries against PostgreSQL running in the container.
    }
}
~~~

`@Container` and `@Testcontainers` belong to Testcontainers' JUnit integration. `@DynamicPropertySource` belongs to Spring Test and registers the container-allocated JDBC URL, username, and password into the Environment.

Spring configuration can create a DataSource from these properties:

~~~java
@Configuration
class PostgresTestConfig {

    @Bean
    DataSource dataSource(Environment environment) {
        DriverManagerDataSource dataSource =
            new DriverManagerDataSource();

        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl(
            environment.getRequiredProperty("test.datasource.url")
        );
        dataSource.setUsername(
            environment.getRequiredProperty("test.datasource.username")
        );
        dataSource.setPassword(
            environment.getRequiredProperty("test.datasource.password")
        );

        return dataSource;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

In a real project, configuration can use a connection pool and migration tool matching the application. This example uses `DriverManagerDataSource` to clearly demonstrate reading properties and connecting to the container; it is not a connection pool meant for production.

### Choosing the Right Container Version

Do not always use the `latest` tag. Pin the major/minor version matching the target environment, such as the exact major version of PostgreSQL or MySQL deployed. If production uses custom extensions or settings, the test container needs those components installed and enabled.

Even with the same engine name, different versions can vary in:

- Supported SQL syntax and features.
- Query planner and execution plans.
- Default collation or time zone.
- Driver behavior and protocol.
- Migration compatibility.
- Locking, optimizer, and performance.

If the system runs on a managed database with specialized extensions or configuration, a standard container may not fully reproduce it. In that case, add the corresponding extensions/configuration or maintain a dedicated set of environment tests.

## Watch Container Lifecycle and Spring Context Caching

The Spring TestContext Framework can cache ApplicationContexts across test classes with equivalent configurations. The Testcontainers JUnit extension typically manages static containers per test class lifecycle. If a cached context holds a DataSource pointing to a stopped container, a subsequent test class might accidentally reuse the stale context.

There are two common organizational approaches:

1. **Share a long-lived container:** use a singleton container for a group of tests and keep the endpoint stable for as long as the ApplicationContext is reused.
2. **Scope the context to the resource lifecycle:** when each class has its own container, ensure the corresponding context is closed/evicted from cache before the container stops, for instance using `@DirtiesContext(classMode = AFTER_CLASS)` where appropriate.

Do not carelessly mix a container that stops after each class with a context cached longer than the container. Dynamic endpoints can be registered with suppliers, but beans like DataSource typically retain the URL read at initialization; changing a supplier value does not automatically recreate a connection pool.

If tests run in parallel, ensure one class does not shut down a container or context that another class is actively using. You can use a shared singleton resource with isolated data/schemas, or give each test group an independent container and context.

## Migrations Must Run on the Database the Application Uses

One of the strongest reasons to pick the same engine is testing migrations. If the application uses Flyway or Liquibase, run the exact migration scripts against a clean test database.

General workflow:

1. Start a database of the target engine and version.
2. Create an empty database/schema dedicated to tests.
3. Run all migrations in the exact order the application uses.
4. Confirm migrations completed.
5. Run repository and integration tests on the schema produced by migrations.
6. Shut down the database/container or drop the schema when the suite finishes.

Do not create an H2 schema manually and use that result to conclude PostgreSQL migrations are correct. Fast tests can use a simplified schema; migration tests must execute real migrations on the target engine.

If a migration needs to upgrade from an older version, initialize the database at the old state, load representative data, run the migration, and verify data is transformed properly. This tests both DDL and data preservation.

## Combining Both Database Types in a Testing Strategy

Not every test needs to run on the exact production engine. A practical strategy can be partitioned by scope:

| Test Group | Suitable Database | What Is Verified |
|---|---|---|
| Logic unit tests without a database | No database or mocks | Business rules and dependency invocations |
| Repository tests with portable SQL | Embedded database | Mappings, CRUD, and basic queries |
| Service tests needing a simple persistence context | Embedded or real engine depending on behavior | Service/repository coordination and basic transactions |
| Native queries and engine-specific types | Same engine as production | SQL compatibility and engine-specific mappings |
| Critical migrations and constraints | Same engine as production | DDL, schema versions, constraints, and data |
| Locking, isolation, concurrency | Same engine as production | Transaction and concurrency behavior |
| Query performance | Production-like engine/version and data | Query plans, indexes, and execution time |

This combination keeps most simple tests fast while still verifying engine-sensitive behaviors on an appropriate database.

However, if the application relies heavily on a specific engine, choosing the same engine for most repository integration tests can reduce divergence risks. The strategy should be driven by the database features the code actually uses, rather than a rigid rule for every project.

## Conditions to Keep Aligned with Production

When the goal is testing database compatibility, choosing the same engine alone is not enough. Consider the following factors as well:

- **Version:** use a version matching the deployment environment.
- **Driver:** use an appropriate JDBC driver and compatible version.
- **Extensions/plugins:** enable extensions that the application uses.
- **Collation and encoding:** configure close to production if queries depend on string comparisons.
- **Timezone:** align database and application time zones.
- **Schema:** run actual migrations instead of creating a simplified schema.
- **Isolation:** configure transaction isolation according to requirements.
- **Users and permissions:** verify required privileges if the application depends on roles or grants.
- **Connection settings:** check pool, autocommit, and timeout settings when they affect behavior.
- **Data:** use data sizes and distributions representative enough for the test being performed.

There is no need to duplicate every production setting in every test. Only simulate conditions directly relevant to the behavior being verified. Never use customer data or production credentials in test environments.

## Performance and Stability of the Test Suite

A same-engine database incurs startup, image-pull, migration, and cleanup overhead. You can reduce this cost by:

- Sharing one container across a test suite when the endpoint and context share a stable lifecycle.
- Running migrations once for a shared schema if tests do not alter the schema.
- Using separate schemas or namespaces per test class/worker when running in parallel.
- Creating minimal fixtures per test method.
- Avoiding starting a fresh container for every test method unless necessary.
- Closing connections, executors, and auxiliary resources in the proper lifecycle.

Embedded databases can also cause flaky tests if tests share a single in-memory database, depend on execution order, or fail to clean up data. Fast speed does not automatically provide isolation.

With either choice, tests should:

- Be able to run individually without depending on data from prior tests.
- Use business keys or namespaces to avoid collisions.
- Manage transactions and cleanup within the right scope.
- Not rely on auto-increment IDs or the current timestamp unless necessary.
- Not perform destructive cleanup on a database shared with other tests.

## Common Misconceptions

**Assuming H2 is a mock database.** H2 is a real database engine. It executes SQL and transactions, but its behavior is not identical to PostgreSQL, MySQL, or other engines.

**Assuming H2 compatibility mode equals the production engine.** Compatibility mode supports only a subset of syntax or behavior. It does not replicate the full dialect, locking, optimizer, and extensions.

**Assuming passing tests on an embedded database prove the production database works.** Tests only prove behavior on the engine used in the test. Engine-specific features must be verified on the target engine.

**Assuming every test needs a production-like database.** Unit tests do not need a database if logic can be tested independently. Many portable repository tests can run quickly on an embedded database.

**Connecting directly to the production database for testing.** Tests require a dedicated database, synthetic data, and restricted permissions. Never run fixtures or cleanup against production data.

**Using the same engine but a version far removed from production.** Features, the optimizer, collations, or migrations can differ. Pin the test version to match the target version.

**Using Testcontainers while ignoring the Spring context lifecycle.** A container stopping while a context remains cached can leave the DataSource holding a stale endpoint. Resource and context lifecycles must be designed in sync.

**Writing a custom schema different from production migrations and calling it a full integration test.** Manual schemas can omit constraints or data types. Migration tests must run the real migration chain.

**Sharing one database across parallel tests without namespacing data.** Tests can read, write, or delete each other's data. Isolate databases/schemas or business keys.

## Decision Workflow for Choosing a Database for a Test

Before choosing an embedded database or the same engine as production, determine:

1. Is the test checking business logic, repository CRUD, native SQL, migrations, transactions, or concurrency?
2. Do queries use syntax or data types specific to the production database?
3. Does the test depend on specific collations, time zones, sequences, locking, or constraints?
4. Is the goal fast feedback or verifying engine compatibility?
5. Can an embedded database be used while preserving the properties under test?
6. If using Testcontainers, does the container have the right engine/version and required extensions?
7. Is the schema created from actual migrations?
8. Do the database, ApplicationContext, and fixtures have compatible lifecycles?
9. Can the test run independently, repeatably, and in parallel without unintentionally sharing data?

If a test only needs portable SQL and basic mappings, an embedded database is usually sufficient and keeps the suite fast. If a test depends on native features, migrations, locking, isolation, or specialized data types, use the same engine as the deployment environment. Combining both options according to your goals ensures data-layer tests deliver both fast feedback and catch database differences that could cause failures in real execution.

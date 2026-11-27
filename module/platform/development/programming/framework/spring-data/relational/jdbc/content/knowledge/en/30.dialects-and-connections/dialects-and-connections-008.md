# Verifying Compatibility Across H2, PostgreSQL, and MySQL

Spring Data JDBC supports multiple relational database management systems through its **dialect** mechanism. H2, PostgreSQL, and MySQL all have directly supported dialects, yet an application passing on H2 is not guaranteed to behave identically on PostgreSQL or MySQL.

The dialect helps Spring Data JDBC handle common SQL differences such as identifier representation, result limiting, generated-key retrieval, and certain database-specific capabilities. The dialect does not make all data types, DDL, constraints, collations, transaction behaviors, or custom SQL statements behave the same.

Therefore, verify against the exact database management system the application will deploy to. H2 is very useful for fast testing and early feedback, while PostgreSQL and MySQL should be exercised in integration tests with real databases, typically via Testcontainers.

This lesson covers how Spring Data JDBC selects dialects, differences across H2, PostgreSQL, and MySQL that commonly cause bugs, how to organize tests per database, and a workflow to verify application compatibility before release.

## 1. What layers comprise database compatibility?

A Spring Data JDBC application can run across multiple databases when these layers are compatible:

1. **JDBC driver:** the driver must connect, supply metadata, and map data types properly.
2. **Dialect:** Spring Data JDBC must select the right dialect to generate suitable SQL.
3. **Schema and migrations:** DDL, column types, identity, sequences, indexes, and constraints must be valid on the target database.
4. **Mapping:** table/column names, quoting, converters, embedded objects, and collections must map accurately.
5. **Queries:** derived queries and dynamic Query must work; custom SQL must match each vendor's syntax.
6. **Transactions and concurrency:** rollbacks, isolation, generated keys, and optimistic locking must meet business rules.
7. **Real data:** collation, timezone, precision, nullability, and driver behavior must match.
8. **Operations:** connection pool settings, timeouts, encoding, SQL modes, and server versions must be verified.

This can be visualized as:

~~~text
Spring Data JDBC application
          |
          v
     JDBC driver
          |
          v
    JDBC metadata
          |
          v
   DialectResolver
          |
          v
  H2 / PostgreSQL / MySQL
          |
          v
  SQL + schema + transaction
          |
          v
  Results on the real database
~~~

A test checking only repository save/load on H2 verifies just part of this chain. It does not prove migrations, custom SQL, data types, or concurrency behave identically on the production database.

## 2. How does Spring Data JDBC use dialects?

The dialect abstracts SQL behaviors dependent on the database or JDBC driver. Spring Data JDBC includes dedicated implementations for H2, PostgreSQL, and MySQL, where the corresponding JDBC dialect classes reside in package:

~~~java
org.springframework.data.jdbc.core.dialect
~~~

Examples of implementations:

| Database | JDBC dialect |
| --- | --- |
| H2 | §JdbcH2Dialect§ |
| PostgreSQL | §JdbcPostgresDialect§ |
| MySQL | §JdbcMySqlDialect§ |

Implementation names may change across Spring Data Relational versions; verify against the API of the version your project uses.

### 2.1. Dialects are auto-detected

In standard configuration, §AbstractJdbcConfiguration§ creates the §JdbcDialect§ bean by inspecting §NamedParameterJdbcOperations§. §DialectResolver§ acquires a JDBC connection and reads metadata provided by the driver.

With Spring Boot, when using §spring-boot-starter-data-jdbc§ and configuring a §DataSource§, auto-configuration sets up the Spring Data JDBC infrastructure and appropriate dialect.

Example PostgreSQL configuration:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop
spring.datasource.username=shop_app
spring.datasource.password=secret
~~~

Example MySQL configuration:

~~~properties
spring.datasource.url=jdbc:mysql://localhost:3306/shop
spring.datasource.username=shop_app
spring.datasource.password=secret
~~~

Example H2 configuration:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
~~~

Applications do not need to manually select a dialect using a database name string in code. Let Spring Data JDBC detect it from connection metadata in standard setups.

### 2.2. Inspecting database metadata

When troubleshooting an environment, you can read metadata from JDBC:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import javax.sql.DataSource;

import org.springframework.stereotype.Component;

@Component
public class DatabaseMetadataLogger {

    public DatabaseMetadataLogger(DataSource dataSource)
            throws Exception {

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();

            System.out.println(
                    "Database: " + metadata.getDatabaseProductName()
            );
            System.out.println(
                    "Database version: " + metadata.getDatabaseProductVersion()
            );
            System.out.println(
                    "Driver: " + metadata.getDriverName()
            );
            System.out.println(
                    "Driver version: " + metadata.getDriverVersion()
            );
        }
    }
}
~~~

The example illustrates how to inspect the actual database and driver the application connects to. In production applications, place this information in startup diagnostics or appropriate health/observability endpoints rather than opening connections inside a bean constructor.

To inspect the configured dialect, you can inject the §JdbcDialect§ bean in an integration test or diagnostic configuration. Never use dialect class names as business logic branches in services.

### 2.3. When do you need to configure a dialect manually?

Normally you do not. Only intervene when:

- The database or JDBC driver is not recognized by the resolver.
- The application uses a database partially compatible with another vendor whose metadata does not match.
- A custom dialect implementation exists.
- Special per-environment configuration or AOT requirements apply.

§AbstractJdbcConfiguration§ allows customizing §jdbcDialect(NamedParameterJdbcOperations)§. For an unsupported database, the application may need a custom §JdbcDialect§ implementation and a provider for resolver discovery.

Do not force a dialect solely because a database offers a compatibility mode. H2's compatibility mode does not turn H2 into real PostgreSQL or MySQL.

## 3. H2, PostgreSQL, and MySQL are supported, not identical

Spring Data JDBC directly supports dialects for all three databases. That means the framework can adapt SQL differences the dialect knows about. It does not mean the databases share identical semantics.

| Aspect | H2 | PostgreSQL | MySQL |
| --- | --- | --- | --- |
| Typical role | Embedded database, fast tests | Popular production database | Popular production database |
| JDBC driver | H2 JDBC | PostgreSQL JDBC | MySQL Connector/J |
| Identity | Supports identity and sequences | Identity and sequences | Usually uses AUTO_INCREMENT |
| Identifier quoting | Uses H2 identifier rules | Unquoted identifiers fold to lowercase; quoted identifiers are case-sensitive | Usually uses backticks; table name casing also depends on OS and config |
| Boolean | Has BOOLEAN type | Has BOOLEAN type | BOOLEAN is an alias for TINYINT(1) |
| Array | Has array support | Has native array types | Lacks a general SQL array type equivalent to PostgreSQL |
| JSON | Has JSON type | JSON and JSONB | Has JSON type |
| Timezone | Has time-with-timezone types | TIMESTAMP WITH TIME ZONE stores instants under PostgreSQL semantics | TIMESTAMP is affected by session timezone; DATETIME stores no timezone |
| Collation | Depends on configuration/collation | Default string comparisons are case-sensitive in many setups | Default collation is often case-insensitive |
| Upsert | H2-specific syntax and semantics | ON CONFLICT | ON DUPLICATE KEY UPDATE |
| Transaction/DDL | H2-specific behavior | PostgreSQL supports transactional DDL in many cases | Many DDL statements cause implicit commits |
| Locking | Differs from production database servers | MVCC and row-level locks | Typically uses InnoDB with MVCC and row-level locks |

This table guides what to test; it does not replace each database version's documentation. Server versions, drivers, SQL modes, collations, and configurations can alter behavior.

## 4. Differences that make H2 tests pass while production fails

### 4.1. Data types

Databases may share type names while differing in semantics, precision, or driver conversion behavior.

For example:

- BOOLEAN in PostgreSQL is a true boolean type.
- MySQL represents BOOLEAN as an alias for TINYINT(1).
- NUMERIC/DECIMAL requires explicit precision and scale.
- TIMESTAMP, DATETIME, and TIMESTAMP WITH TIME ZONE do not share identical semantics.
- JSON, JSONB, and MySQL's JSON type differ in operators, indexing, and parameter binding.
- Array columns are not uniformly supported; PostgreSQL has native array types, whereas MySQL lacks an equivalent general SQL array type.

Do not merely verify that a value writes and reads back on H2. Verify values on the production database, especially for monetary amounts, timestamps, JSON, UUIDs, and binary data.

Currency schema example:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    price DECIMAL(12, 2) NOT NULL
);
~~~

Tests should confirm:

- Which rule governs values with more than two decimal places.
- Whether values exceeding precision are rejected or rounded.
- Whether the driver returns §BigDecimal§ with the expected scale.
- Whether legacy data migrates to the new schema without precision loss.

### 4.2. Date/time and timezones

An application may store §Instant§, §LocalDateTime§, §OffsetDateTime§, or §LocalDate§ depending on meaning.

Do not treat these types as interchangeable:

| Java type | Meaning |
| --- | --- |
| §Instant§ | An absolute point on the UTC timeline. |
| §LocalDateTime§ | Local date and time without timezone/offset. |
| §OffsetDateTime§ | Date and time accompanied by an offset. |
| §LocalDate§ | Calendar date without time of day. |

PostgreSQL has its own semantics for §timestamp with time zone§; MySQL distinguishes §TIMESTAMP§ from §DATETIME§, where session timezone can affect reading/writing §TIMESTAMP§. H2 may accept different types and conversions.

To verify:

1. Choose a timezone policy, typically storing instants in UTC.
2. Configure the JDBC driver and session timezone appropriately.
3. Write a timestamp with a non-UTC offset.
4. Read it back on the target database.
5. Verify the exact same instant is preserved.
6. Verify calendar dates do not shift to the previous/next day upon timezone conversion.

Test example:

~~~java
@Test
void preservesInstantAcrossDatabaseRoundTrip() {
    Instant expected = Instant.parse("2026-11-13T08:30:00Z");

    Event event = repository.save(
            new Event(null, "CREATED", expected)
    );

    Event loaded = repository.findById(event.id())
            .orElseThrow();

    assertEquals(expected, loaded.occurredAt());
}
~~~

This test must run on every supported database, not just H2.

### 4.3. Identifiers, quoting, and letter casing

Spring Data Relational uses quoted identifiers by default for table/column names derived from mappings. Behavior can be customized via the mapping context, but do not change it merely to make one test database pass.

PostgreSQL folds unquoted identifiers to lowercase. Quoted identifiers preserve casing and become case-sensitive. MySQL typically uses backticks for identifiers, and table name comparisons also depend on OS, filesystem, and server configuration. H2 has its own rules.

Names like §Order§, §User§, §Group§, or §Rank§ may collide with reserved keywords on one or more databases.

Recommendations:

- Use clear table/column names and avoid reserved keywords.
- Do not rely on identifier letter casing.
- Use §@Table§ and §@Column§ when stable names are needed.
- Test schema migrations across all three databases.
- Do not write custom SQL assuming every vendor uses the same quote character.

Mapping example:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,

        @Column("order_status")
        String status
) {
}
~~~

Avoid naming a table §order§ and expecting every database to handle it identically.

### 4.4. Identity, sequences, and generated keys

Databases do not share the same ID generation strategy:

- H2 supports identity and sequences.
- PostgreSQL supports identity and sequences.
- MySQL commonly uses §AUTO_INCREMENT§.

Spring Data JDBC and dialects support retrieving generated keys as allowed by the driver. However, DDL migrations and ID configurations must still match the target database.

Entity example:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        String name
) {
}
~~~

Tests should confirm:

1. Insert without supplying an ID.
2. The database generates the ID.
3. The repository returns an aggregate with the populated ID.
4. It can be loaded back by that ID.
5. IDs are not lost or mismatched when inserting multiple records.
6. Batch insert ID generation works with the database/driver if batching is used.

If using an explicit sequence with §@Sequence§, verify the sequence exists after migrations and the database user has privileges on it.

### 4.5. Generated SQL and pagination

The dialect helps Spring Data JDBC produce appropriate SQL for common operations, yet custom SQL remains the application's responsibility.

Example:

~~~java
@Query("""
        SELECT id, name, price
        FROM products
        WHERE status = :status
        ORDER BY created_at DESC
        """)
List<ProductSummary> findByStatus(String status);
~~~

The SQL above can run on all three databases if schemas and data types align. However, adding functions, JSON operators, upserts, returning clauses, or vendor-specific syntax alters compatibility.

With dynamic §Query§, use §Sort§, §limit§, and §offset§ so the framework generates dialect-specific SQL. With string-based §@Query§, write and test SQL against each target database.

### 4.6. Upsert and native SQL

PostgreSQL, MySQL, and H2 have different upsert syntaxes. For example:

~~~sql
-- PostgreSQL
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-01', 10)
ON CONFLICT (sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

~~~sql
-- MySQL
INSERT INTO inventory (sku, quantity)
VALUES ('SKU-01', 10)
ON DUPLICATE KEY UPDATE quantity = VALUES(quantity);
~~~

MySQL syntax can evolve or deprecate certain value references in newer versions; use syntax suited to your target MySQL version.

Do not place native SQL like the above into a repository and expect it to run on H2 and PostgreSQL/MySQL simultaneously. When multi-database support is required:

- Use portable persistence APIs if they satisfy the use case.
- Separate SQL by database/dialect when genuinely needed.
- Use dedicated repository fragments or adapters per vendor.
- Run tests against all supported databases.
- Do not clutter domain services with branches checking database names.

### 4.7. Collation and string comparisons

A search query can return different results due to collation:

~~~sql
SELECT id, email
FROM customers
WHERE email = 'AN@example.com';
~~~

One database may compare case-insensitively under its default collation; another may compare case-sensitively. Query results and unique constraints on strings can also differ.

For emails or identifiers needing case-insensitive matching:

- Normalize data on write, e.g., lowercasing per domain rules.
- Define the exact collation or comparison mode required.
- Create matching unique constraints/indexes.
- Test cases like §AN@example.com§ and §an@example.com§.
- Do not rely on H2's default collation.

### 4.8. Constraints and transaction behavior

H2 may not faithfully reproduce:

- When the database checks constraints.
- DDL behavior inside transactions.
- Locking and deadlocks.
- Default isolation levels.
- Concurrent update handling.
- Cascade deletes and foreign keys.
- Specific errors returned by the driver.

MySQL can perform implicit commits on many DDL statements. PostgreSQL supports transactional DDL much more broadly. Consequently, a migration running inside a transaction on H2 may not share identical semantics on MySQL.

Tests for rollbacks, optimistic locking, unique constraints, and migrations must run on the production target database.

## 5. Can H2 compatibility mode replace PostgreSQL/MySQL?

H2 supports compatibility modes to emulate certain behaviors of other databases, for example:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop;MODE=PostgreSQL;DB_CLOSE_DELAY=-1
~~~

Or:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop;MODE=MySQL;DB_CLOSE_DELAY=-1
~~~

Compatibility modes can help when:

- Catching some non-portable SQL syntax.
- Supporting fast migration checks.
- Reducing minor parser or function rule differences.
- Maintaining legacy tests during a transition.

However, it does not replace the real database. H2 is still H2:

- JDBC metadata still reports H2.
- Spring Data JDBC still detects the H2 dialect.
- The driver is still the H2 driver.
- Data types, collations, locking, transactions, and optimizers still differ.
- Compatibility mode does not simulate the full server behavior of PostgreSQL/MySQL.

Do not treat tests passing on §MODE=PostgreSQL§ as proof of PostgreSQL compatibility. Use real PostgreSQL in Testcontainers to verify.

## 6. Multi-layered testing strategy

A practical strategy combines fast tests with tests against real databases.

| Layer | Database | Goal | Speed |
| --- | --- | --- | --- |
| Unit tests | No database needed | Domain logic, validation, pure Java converters | Fast |
| Repository smoke tests | H2 | Basic mapping, CRUD, fast feedback | Fast |
| Integration tests | PostgreSQL Testcontainer | Migrations, dialect, SQL, transactions, driver, and production semantics | Moderate |
| Integration tests | MySQL Testcontainer | Separately verify MySQL and Connector/J behavior | Moderate |
| Staging verification | Database matching production type/version | Verify real configuration, workload, and migrations | Slower |

Not every unit test needs to run three times. Use a shared integration contract test suite to verify key persistence behaviors across each database.

### 6.1. Database-independent unit tests

Domain behavior should be tested without Spring or JDBC:

~~~java
class InventoryItemTest {

    @Test
    void rejectsReservationGreaterThanAvailableQuantity() {
        InventoryItem item = new InventoryItem(
                1L,
                "SKU-01",
                3,
                1L
        );

        assertThrows(
                InsufficientStockException.class,
                () -> item.reserve(4)
        );
    }
}
~~~

Unit tests verify business rules. They do not test dialects, SQL, or drivers.

### 6.2. H2 for fast feedback

H2 works well for simple repository tests:

~~~properties
spring.datasource.url=jdbc:h2:mem:shop_test;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
~~~

Keep H2 tests scoped appropriately:

- Checking context and repository startup.
- Basic CRUD.
- Simple mappings.
- Pure converters.
- Portable derived queries.
- Fast feedback during development.

Do not rely solely on H2 for production migrations, custom SQL, or concurrency semantics.

## 7. Testing PostgreSQL with Testcontainers

Testcontainers spins up a temporary PostgreSQL server in Docker. Integration tests connect to a real database using the PostgreSQL JDBC driver.

### 7.1. Dependencies

Example Maven dependencies (versions should be managed consistently via the project's BOM):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Use the Testcontainers BOM so modules share compatible versions. Artifact coordinates/versions may change across major Testcontainers releases; follow the dependency guide for your version.

### 7.2. Integration test with @DynamicPropertySource

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class PostgreSqlRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("shop")
                    .withUsername("shop")
                    .withPassword("shop");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = repository.save(
                new Customer(null, "Nguyễn An")
        );

        Customer loaded = repository.findById(saved.id())
                .orElseThrow();

        assertEquals("Nguyễn An", loaded.name());
    }
}
~~~

In this example, tag §postgres:16-alpine§ is an explicitly pinned server version for tests. Use the matching major/minor version or image digest aligned with the production environment being verified.

§@DynamicPropertySource§ supplies the container's JDBC URL, username, and password to the Spring Environment before the context initializes.

### 7.3. Container lifecycle and Spring context caching

The JUnit Testcontainers extension manages container lifecycles per test class or test method. Spring TestContext may cache an ApplicationContext and reuse it after a test class finishes. If a cached context retains a datasource pointing to a stopped container, subsequent test classes can fail.

For large Spring Boot test suites, consider:

- Managing the container as a Spring bean so its lifecycle matches the context.
- Using a shared container configuration imported across tests.
- Avoiding cached contexts holding connections to stopped containers.
- Using §@DirtiesContext§ deliberately when test setup requires closing the context.
- Avoiding spinning up excessive containers per individual method.

Spring Boot also supports service connections via §@ServiceConnection§ when the §spring-boot-testcontainers§ module is present. This is an alternative to §@DynamicPropertySource§; do not use both for the same datasource without a specific reason.

## 8. Testing MySQL with Testcontainers

MySQL must be tested separately because its driver, DDL, collation, and certain semantics differ from PostgreSQL.

### 8.1. Dependencies

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mysql</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Use a MySQL Connector/J version compatible with your MySQL server and Spring version.

### 8.2. Integration test with MySQLContainer

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest
class MySqlRepositoryIntegrationTest {

    @Container
    static final MySQLContainer<?> mysql =
            new MySQLContainer<>("mysql:8.4")
                    .withDatabaseName("shop")
                    .withUsername("shop")
                    .withPassword("shop");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", mysql::getJdbcUrl);
        registry.add("spring.datasource.username", mysql::getUsername);
        registry.add("spring.datasource.password", mysql::getPassword);
    }

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = repository.save(
                new Customer(null, "Nguyễn An")
        );

        Customer loaded = repository.findById(saved.id())
                .orElseThrow();

        assertEquals("Nguyễn An", loaded.name());
    }
}
~~~

Choose an image version matching production MySQL. If production runs MySQL 8.0, testing on MySQL 8.4 does not automatically prove backward or full compatibility with 8.0.

If the application uses MariaDB, test MariaDB separately. MySQL and MariaDB share close origins but are distinct products; driver metadata and dialects can differ.

## 9. Sharing contract tests across multiple databases

To avoid duplicating the same test logic for H2, PostgreSQL, and MySQL, extract repository verification into contract tests.

A contract test defines mandatory behaviors:

- Insert aggregate.
- Load aggregate.
- Update aggregate.
- Delete aggregate.
- Save and load child collections.
- Check optimistic locking.
- Check queries/sorting/pagination.
- Check transaction rollbacks.
- Check converters and critical data types.

Abstract contract example:

~~~java
abstract class CustomerRepositoryContract {

    protected abstract CustomerRepository repository();

    @Test
    void persistsCustomer() {
        Customer saved = repository().save(
                new Customer(null, "Nguyễn An")
        );

        Customer loaded = repository()
                .findById(saved.id())
                .orElseThrow();

        assertEquals("Nguyễn An", loaded.name());
    }
}
~~~

Per-database test classes extend the contract and supply the repository wired to the corresponding database:

~~~java
@SpringBootTest
class PostgreSqlCustomerRepositoryTest
        extends CustomerRepositoryContract {

    @Autowired
    CustomerRepository customerRepository;

    @Override
    protected CustomerRepository repository() {
        return customerRepository;
    }
}
~~~

~~~java
@SpringBootTest
class MySqlCustomerRepositoryTest
        extends CustomerRepositoryContract {

    @Autowired
    CustomerRepository customerRepository;

    @Override
    protected CustomerRepository repository() {
        return customerRepository;
    }
}
~~~

This is an illustrative structure. In real projects, container configuration can live in dedicated test configurations or shared base classes. Ensure each test class genuinely connects to its target database rather than accidentally falling back to H2 from a default test profile.

Do not force every behavior into a shared contract if it is vendor-specific. For example, PostgreSQL JSONB queries and MySQL JSON queries may require separate tests.

## 10. Tests to run on both PostgreSQL and MySQL

A compatibility test suite can be organized by area.

### 10.1. Dialect and context startup

Verify:

- ApplicationContext starts cleanly.
- §DataSource§ connects to the right database.
- The resolver selects the right dialect.
- Repository proxies are created.
- Generated SQL executes properly.
- Driver metadata reports the expected product name/version.

If the context fails to boot, first check JDBC URL, driver, credentials, network, and database startup logs.

### 10.2. Mapping and CRUD

Verify:

- §@Table§, §@Column§, §@Id§.
- Naming strategy.
- Quoted identifiers.
- Generated IDs.
- Embedded objects.
- One-to-one and collection mappings.
- Null/default values.
- Custom converters.
- §@Version§.

Pay special attention to tables or columns near reserved words and mappings with mixed letter casing.

### 10.3. Migrations and schemas

Run Flyway or Liquibase against the real database:

- Create a fresh schema from scratch.
- Upgrade from an older schema version.
- Create indexes and unique constraints.
- Create foreign keys and cascade rules.
- Verify identity/sequences.
- Verify default values.
- Verify precision/scale.
- Check whether migrations contain vendor-specific DDL.

Do not run only a simplified §schema.sql§ in tests while skipping real production migrations.

### 10.4. Queries and custom SQL

Verify:

- Derived query methods.
- Criteria and dynamic §Query§.
- Sorting and pagination.
- Projections and DTOs.
- Custom §@Query§.
- Native SQL.
- Queries with joins or aggregate expressions.
- SQL using JSON, arrays, or specialized functions.

Every native SQL statement needs a test on its corresponding database vendor.

### 10.5. Transactions and concurrency

Verify:

- Multiple repositories in one transaction.
- Rollback when a later step fails.
- Optimistic locking with §@Version§.
- Two transactions updating the same aggregate.
- Unique constraints under concurrent inserts.
- Lock timeouts and deadlocks if relevant to business logic.
- Required isolation levels.

H2 is not sufficient proof of concurrency behavior on PostgreSQL/MySQL.

### 10.6. Data types and boundary values

Verify:

- §BigDecimal§ at maximum precision/scale.
- Timestamps near day boundaries and timezones.
- Unicode and multi-byte characters.
- Empty strings and NULL.
- Booleans.
- Enums.
- UUIDs.
- JSON or binary if used.
- Very large or very small numbers.
- Strings with accents, escape characters, and special characters.

## 11. Testing migrations per database

Migrations are one of the most frequent reasons an application passes H2 tests yet fails on deployment.

Table creation migration example:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

This statement is not necessarily portable verbatim across all databases and versions. Check:

- Identity syntax.
- Sequence behavior.
- Timestamp types.
- Index syntax.
- Constraint syntax.
- Default expressions.
- Functions and operators.
- DDL transaction behavior.

### 11.1. Use the migration tool as the primary schema source

If the application uses Flyway, run real migrations in integration tests:

~~~properties
spring.flyway.enabled=true
spring.sql.init.mode=never
~~~

Do not maintain two unsynchronized schema sources simultaneously, such as Flyway for production and a separate §schema.sql§ for H2 tests.

If per-database schemas are required, use vendor-specific Flyway locations:

~~~properties
spring.flyway.locations=classpath:db/migration/common,classpath:db/migration/postgresql
~~~

For MySQL, configure the matching location:

~~~properties
spring.flyway.locations=classpath:db/migration/common,classpath:db/migration/mysql
~~~

Ensure only the right vendor migrations run in each profile. Shared migrations should stick to portable SQL; vendor-specific migrations must be named and managed clearly.

### 11.2. Test upgrades, not just clean installs

An empty database only tests running migrations from scratch. Production usually has existing data and older schemas.

Create tests that:

1. Initialize the database at an older migration version.
2. Insert representative data.
3. Run the new migration.
4. Verify existing data remains intact.
5. Verify the new schema is accurate.
6. Run repository queries and updates against the new schema.

Migrations must be verified independently on PostgreSQL and MySQL.

## 12. Managing configuration per database

Spring profiles can select JDBC URLs and connection properties.

§application-h2.yml§:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:shop;DB_CLOSE_DELAY=-1
    username: sa
    password: ""
    driver-class-name: org.h2.Driver
~~~

§application-postgresql.yml§:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: ${DB_PASSWORD}
    driver-class-name: org.postgresql.Driver
~~~

§application-mysql.yml§:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/shop
    username: shop_app
    password: ${DB_PASSWORD}
    driver-class-name: com.mysql.cj.jdbc.Driver
~~~

Running a profile:

~~~bash
./mvnw test -Dspring.profiles.active=postgresql
~~~

Or:

~~~bash
./mvnw test -Dspring.profiles.active=mysql
~~~

These are profile configuration examples. With Testcontainers, hard-coded hosts/ports are typically unnecessary; §@DynamicPropertySource§ overrides datasource properties with the container address provisioned at runtime.

Never store production passwords in config files or repositories. Use a secret manager or environment variables.

## 13. Compatibility matrix in CI

A pipeline can run test suites such as:

| Job | Database | Test suite | Goal |
| --- | --- | --- | --- |
| §unit§ | No DB needed | Unit tests | Domain behavior |
| §jdbc-h2§ | H2 | Repository smoke tests | Fast feedback |
| §jdbc-postgresql§ | PostgreSQL container | Migrations + repository integration | Production compatibility |
| §jdbc-mysql§ | MySQL container | Migrations + repository integration | Production compatibility |
| §migration-upgrade§ | Each target DB | Upgrade tests | Safety of existing data |

If production uses only PostgreSQL, prioritize PostgreSQL integration tests. If the product commits to supporting both PostgreSQL and MySQL, both must be required checks.

Conceptual GitHub Actions example:

~~~yaml
jobs:
  test-postgresql:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./mvnw verify -Ppostgresql

  test-mysql:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./mvnw verify -Pmysql
~~~

Testcontainers requires an available Docker runtime in the runner. Real setups must adjust Java version, Maven profiles, and dependency caching to match the project.

### 13.1. Pin database versions

Do not use floating image tags like §postgres:latest§ or §mysql:latest§ for critical integration tests.

Pin versions close to production:

~~~text
Production PostgreSQL: 16.x
Test PostgreSQL:       16.x

Production MySQL:      8.4.x
Test MySQL:            8.4.x
~~~

Pin image digests if the pipeline demands stricter reproducibility. When upgrading database versions, update the CI image and re-run the entire compatibility suite prior to rollout.

## 14. Observing generated SQL

When a test fails, isolate whether the error stems from:

- Dialect.
- Mapping metadata.
- Auto-generated SQL.
- Custom SQL.
- Driver conversion.
- Schema migration.
- Database constraints.
- Transaction behavior.

Spring Data JDBC uses Spring JDBC mechanisms to execute SQL. You can enable logging:

~~~properties
logging.level.org.springframework.jdbc=DEBUG
~~~

SQL logs show executed statements and parameters. Avoid logging sensitive values in production.

When investigating failures:

1. Check database product/version and driver version.
2. Inspect the actual SQL.
3. Run the corresponding SQL directly on the database container.
4. Inspect the schema via §information_schema§ or vendor tools.
5. Check the execution plan if the issue is performance.
6. Compare results against H2 to pinpoint differences.
7. Add a regression test on the failing database.

Do not patch code by adding branches checking database names before identifying whether the real difference lies in dialect, schema, or custom SQL.

## 15. Example critical compatibility test: optimistic locking

Suppose an aggregate:

~~~java
@Table("inventory_items")
public record InventoryItem(
        @Id Long id,
        String sku,
        int availableQuantity,
        @Version Long version
) {
}
~~~

Stale update test:

~~~java
@SpringBootTest
class InventoryVersionIntegrationTest {

    @Autowired
    InventoryRepository repository;

    @Test
    void rejectsUpdateUsingStaleVersion() {
        InventoryItem created = repository.save(
                new InventoryItem(
                        null,
                        "SKU-01",
                        10,
                        null
                )
        );

        InventoryItem firstRead = repository.findById(created.id())
                .orElseThrow();

        InventoryItem secondRead = repository.findById(created.id())
                .orElseThrow();

        InventoryItem firstChange = new InventoryItem(
                firstRead.id(),
                firstRead.sku(),
                8,
                firstRead.version()
        );

        repository.save(firstChange);

        InventoryItem staleChange = new InventoryItem(
                secondRead.id(),
                secondRead.sku(),
                7,
                secondRead.version()
        );

        assertThrows(
                OptimisticLockingFailureException.class,
                () -> repository.save(staleChange)
        );
    }
}
~~~

Run this exact contract test on PostgreSQL and MySQL. It verifies optimistic locking semantics through the real JDBC driver and database.

If the test runs inside a test-framework-managed transaction, design transaction boundaries properly so the first save is visible to the stale save. Use tests without an outer transaction or separate the two operations into distinct transactions.

## 16. Example testing migrations and constraints

Suppose the database must enforce unique SKUs and non-negative quantities:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT chk_inventory_quantity
        CHECK (available_quantity >= 0)
);
~~~

Databases/versions differ in when or how thoroughly constraints are enforced. Test on each database:

~~~java
@Test
void databaseRejectsDuplicateSku() {
    repository.save(new InventoryItem(
            null, "SKU-01", 10, null
    ));

    assertThrows(
            DataIntegrityViolationException.class,
            () -> repository.save(new InventoryItem(
                    null, "SKU-01", 5, null
            ))
    );
}
~~~

Beyond checking the exception, verify final row counts and data state in the database. Upon constraint violation, a transaction may be marked rollback-only depending on database and transaction manager; do not continue using that transaction as if no error occurred.

## 17. Verifying vendor-specific behavior

Not every feature needs testing on all three databases if the application does not use it. List the features that actually appear in your schema/domain/queries.

| Feature | Verification question |
| --- | --- |
| JSON | How does the converter bind types? Do query operators run on the target DB? |
| Array | Does the DB support array types and does the JDBC driver have matching mappings? |
| UUID | Native column type or string? Does the converter round-trip? |
| Sequence | Is the sequence created with proper privileges? |
| Identity | Does insert return the generated key properly? |
| Upsert | Is SQL portable or must it be split per vendor? |
| Collation | Do comparisons and unique constraints match intended case sensitivity? |
| Timezone | Does Instant survive round-trips intact? |
| DDL | Do migrations run cleanly under the server's transaction behavior? |
| Pagination | Do sort tie-breakers and limit/offset return stable results? |
| Locking | Do optimistic/pessimistic locks have the expected semantics? |
| Stored procedures | Are parameter and result mappings driver-compatible? |

Prioritize testing features impacting data correctness before features affecting only syntax or performance.

## 18. Signs an application is not truly portable

An application may be database-dependent without realizing it. Warning signs:

- H2 tests pass while PostgreSQL/MySQL integration tests fail.
- Migrations use vendor-specific identity or sequence syntax without per-vendor migrations.
- Repositories contain many §@Query§ methods using specialized functions or operators.
- Table/column names contain reserved keywords.
- Email lookup queries return different results across environments.
- Timestamps shift by hours when switching databases.
- Decimal values round differently.
- Optimistic locking tests pass only on H2.
- JSON/array data works with only one driver.
- Production has different unique constraints or collations than H2.
- Certain DDL statements commit outside transactions on MySQL.
- The application forces a dialect while JDBC metadata reports another database.

When encountering these signs, define clearly which databases the application commits to supporting. Not every project needs portability across three vendors; what matters is that tests and documentation accurately reflect the supported scope.

## 19. Compatibility verification workflow

Verification can follow this sequence:

1. **Lock target databases:** H2, PostgreSQL, MySQL, or the exact supported combination.
2. **Lock server and driver versions:** pin versions close to production.
3. **Check dialect discovery:** confirm Spring Data JDBC recognizes the right database via JDBC metadata.
4. **Run migrations on an empty database:** verify DDL creates the schema cleanly.
5. **Run upgrade migrations:** confirm existing data is preserved.
6. **Run mapping contract tests:** CRUD, aggregates, collections, embedded, converters, ID generation.
7. **Run query tests:** derived queries, Criteria, sorting, pagination, and custom SQL.
8. **Run data type tests:** decimals, time, timezones, UUID, JSON, Unicode, and NULL.
9. **Run transaction tests:** rollbacks, optimistic locking, constraints, and concurrency.
10. **Run vendor-specific tests:** upsert, JSON operators, sequences, or specialized functions.
11. **Inspect SQL and metadata:** on failure, capture SQL/errors to build regression tests.
12. **Add database containers to CI:** required checks for every committed supported database.
13. **Verify on staging:** use matching major versions, collations, timezones, and production-like configuration.
14. **Verify before version upgrades:** update server/driver/dialect and re-run the entire compatibility suite.

~~~mermaid
flowchart TD
    A["Choose target database and version"] --> B["Configure JDBC driver + DataSource"]
    B --> C["Verify dialect detection"]
    C --> D["Run schema migrations"]
    D --> E["Run mapping and repository contract tests"]
    E --> F["Run query and data type tests"]
    F --> G["Run transaction/concurrency tests"]
    G --> H{"Compatibility errors?"}
    H -->|Yes| I["Inspect SQL, metadata, schema, and driver"]
    I --> J["Fix mapping/migration/query"]
    J --> E
    H -->|No| K["Add tests to CI"]
    K --> L["Verify on staging with matching DB type"]
~~~

## 20. Hands-on exercises

Create a Spring Data JDBC application with §Customer§ and §InventoryItem§ aggregates.

### Exercise 1: Run the same repository on H2

1. Configure H2 in-memory.
2. Create a repository for §Customer§.
3. Test insert, findById, update, and delete.
4. Check generated IDs.
5. Record generated SQL and database metadata.

### Exercise 2: Move integration tests to PostgreSQL

1. Add the PostgreSQL JDBC driver.
2. Add Testcontainers JUnit and PostgreSQL modules.
3. Start a PostgreSQL container.
4. Use §@DynamicPropertySource§ to configure the datasource.
5. Run migrations and repository tests.
6. Compare generated IDs, timestamps, constraints, and SQL with H2.

### Exercise 3: Verify MySQL

1. Add MySQL Connector/J and the MySQL Testcontainers module.
2. Start a MySQL container.
3. Run the same contract tests.
4. Inspect identity, collation, and Boolean mappings.
5. Verify real migrations succeed.

### Exercise 4: Test boundary data

1. Save §BigDecimal§ with maximum precision.
2. Save Vietnamese Unicode text.
3. Save timestamps with a non-UTC offset.
4. Save NULL and empty strings.
5. Read back across all three databases and compare semantics.

### Exercise 5: Test concurrency

1. Create an aggregate with §@Version§.
2. Read the same aggregate in two transactions.
3. Save the first change.
4. Save the object holding the stale version.
5. Verify §OptimisticLockingFailureException§ on PostgreSQL and MySQL.
6. Inspect the final database state.

### Exercise 6: Test migration upgrades

1. Create the schema at an older migration version.
2. Insert sample data.
3. Run the new migration.
4. Verify no data is lost.
5. Check indexes, foreign keys, unique constraints, and defaults.
6. Repeat on PostgreSQL and MySQL.

## 21. Key takeaways

- Spring Data JDBC directly supports dialects for H2, PostgreSQL, and MySQL.
- §DialectResolver§ detects the dialect via JDBC connection metadata; Spring Boot auto-configures it when the starter and §DataSource§ are present.
- Dialects handle common SQL differences; they do not turn different databases into the same engine.
- H2 is useful for fast tests, not a substitute for real PostgreSQL/MySQL.
- H2 compatibility mode is not proof of compatibility with the corresponding database vendor.
- Data types, timezones, precision, collation, identifier quoting, generated keys, and transaction semantics can differ.
- Derived queries and dynamic §Query§ can use Spring Data JDBC abstractions; custom SQL must be verified per vendor.
- Run Flyway/Liquibase migrations on real databases, covering both clean installs and upgrades.
- Testcontainers enables integration tests against temporary database servers in Docker.
- Test MySQL and PostgreSQL separately; if using MariaDB, test MariaDB separately.
- Pin database and JDBC driver versions close to production for reproducible tests.
- Share contract tests for CRUD, mapping, queries, transactions, and optimistic locking; add separate tests for vendor-specific features.
- Add PostgreSQL/MySQL integration tests to CI if the application commits to supporting those databases.
- Inspect SQL, metadata, and database errors to create regression tests.
- Verify on staging with production-like versions, collations, timezones, and settings.

**H2 catches bugs early; the production database proves actual compatibility.** Let the dialect handle common SQL generation, while migrations, data types, custom queries, transactions, and concurrency must be verified against the exact database the application will run in production.

## References

- [Spring Data Relational 4.1.2 — Getting Started and Dialects](https://docs.spring.io/spring-data/relational/reference/jdbc/getting-started.html)
- [Spring Data Relational 4.1.2 — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data JDBC 4.1.2 — DialectResolver API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/dialect/DialectResolver.html)
- [Spring Data JDBC 4.1.2 — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html)
- [Spring Boot 4.1.2 — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Testcontainers for Java — JDBC Support](https://java.testcontainers.org/modules/databases/jdbc/)

# Testing Repositories with Testcontainers and Real Migrations

A repository test running on H2 is fast and convenient, yet H2 cannot replace PostgreSQL or MySQL when an application relies on engine-specific SQL, data types, collations, constraints, locking, or runtime behavior. Testcontainers spins up a real database in Docker right when tests run. Combined with Flyway or Liquibase, the test walks through the exact startup sequence the application needs: create the database, execute migrations, validate JPA mappings, and run repository operations.

The goal of this lab is to build a test suite that verifies:

1. Tests connect to the exact database engine and version chosen.
2. The container starts before Spring creates `DataSource` and `EntityManagerFactory`.
3. Production migrations actually execute against the database container.
4. Hibernate validates mappings against the schema created by migrations.
5. Repositories read, write, paginate, and enforce constraints on the real engine.
6. Transaction rollbacks, commits, and database errors are tested at proper boundaries.
7. Tests have isolated data and run repeatably on developer machines and CI.

Testcontainers does not eliminate the need for unit tests. Use unit tests for business rules that do not require a database, fast repository tests for portable queries when beneficial, and containers for behavior requiring compatibility with a real database.

## 1. Choosing the Right Test Type

Spring Boot offers two common ways to test Spring Data JPA.

**`@DataJpaTest`** creates a test slice focused on entities, repositories, JPA, and related configuration. It does not load the full service or web layers. By default, tests are transactional and roll back when finished. If an embedded database is on the classpath, Spring Boot may replace the `DataSource` with an in-memory database. When using Testcontainers, configure `@AutoConfigureTestDatabase(replace = Replace.NONE)`.

**`@SpringBootTest`** loads the application's `ApplicationContext`. Use this when verifying services, transaction boundaries, event listeners, datasource configuration, security, or multiple beans collaborating. You can set `webEnvironment = NONE` when no HTTP server is needed.

| Requirement | Usually Appropriate Annotation |
|---|---|
| Entity mappings, derived queries, JPQL, native queries, and repository CRUD | `@DataJpaTest` |
| Repositories together with services and business transactions | `@SpringBootTest` |
| Testing HTTP APIs calling services and database | `@SpringBootTest(webEnvironment = RANDOM_PORT)` |
| Migrations creating schema and Hibernate validating mappings | Both; `@SpringBootTest` is often used for the full application flow |
| Verifying actual commits | Dedicated test designed without an enclosing rolling-back test transaction |

Do not pick `@DataJpaTest` solely for speed if the test requires service beans or configuration excluded from the slice. Test slices limit component scanning; you can import needed beans or switch to `@SpringBootTest` when the full application is needed.

## 2. Dependencies and Version Differences

The examples below use Spring Boot 4.1.x and Testcontainers 2.0.x. Versions are managed by Spring Boot dependency management and the Testcontainers BOM. Testcontainers 2.x renamed module artifacts and container packages compared to 1.x, so do not mix coordinates or imports between the two major lines.

Maven example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-postgresql</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-mysql</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>com.mysql</groupId>
        <artifactId>mysql-connector-j</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Choose Flyway or Liquibase; do not use both to manage the same schema. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-flyway</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-database-postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.flywaydb</groupId>
        <artifactId>flyway-mysql</artifactId>
    </dependency>
</dependencies>
~~~

If the project uses Liquibase, replace the Flyway starter and Flyway database modules with `spring-boot-starter-liquibase`; keep the PostgreSQL/MySQL JDBC drivers and Testcontainers modules. Never configure both Flyway and Liquibase to manage the same schema.

Since Spring Boot 3.1, `@ServiceConnection` has been available, though test annotation packages and Testcontainers dependency coordinates vary by version. Spring Boot 3.x typically uses `org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest` and Testcontainers 1.x artifacts `postgresql`, `mysql`, and `junit-jupiter`. Spring Boot 4.x and Testcontainers 2.x use the new test starter modules and packages shown in the example. Follow the BOM and documentation matching your project's major version.

## 3. Starting a PostgreSQL or MySQL Container

Spring Boot can manage containers as Spring beans. This integrates cleanly with TestContext caching: the container starts alongside the `ApplicationContext` and stops when the context closes. `@ServiceConnection` lets Spring Boot derive connection details from the container, removing the need to manually assemble JDBC URLs, usernames, and passwords.

### PostgreSQL Configuration

Place the configuration class in `src/test/java`:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class PostgresContainerConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer postgresContainer() {
        return new PostgreSQLContainer("postgres:16.6-alpine")
                .withDatabaseName("jpa_test")
                .withUsername("test_user")
                .withPassword("test_password");
    }
}
~~~

### MySQL Configuration

When testing MySQL, use a dedicated configuration and import it into the corresponding test classes:

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.mysql.MySQLContainer;

@TestConfiguration(proxyBeanMethods = false)
class MySqlContainerConfiguration {

    @Bean
    @ServiceConnection
    MySQLContainer mysqlContainer() {
        return new MySQLContainer("mysql:8.4")
                .withDatabaseName("jpa_test")
                .withUsername("test_user")
                .withPassword("test_password");
    }
}
~~~

Import only one database configuration per test context. If the application supports both PostgreSQL and MySQL, create two separate test suites or two CI profiles. Never let two containers provide competing default `DataSource` beans in the same test context unless multiple datasources are explicitly configured.

Pin image versions close to production, such as PostgreSQL 16.x or MySQL 8.4.x. Avoid the `latest` tag, as the image can change between test runs. If production enables specific extensions, collations, timezones, or server settings, reproduce them in the container.

### Attaching the Container to @DataJpaTest

~~~java
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(PostgresContainerConfiguration.class)
@ActiveProfiles("test")
class AccountRepositoryPostgresTest {
    // Repository tests
}
~~~

`replace = NONE` stops Spring from swapping out the PostgreSQL container for H2. `@Import` brings the `@TestConfiguration` into the test slice. For MySQL, swap the imported configuration to `MySqlContainerConfiguration.class`.

### When to Use @DynamicPropertySource?

`@DynamicPropertySource` is an alternative when not using `@ServiceConnection`, when configuring a custom datasource, or when on Spring Boot older than 3.1:

~~~java
@Container
static final PostgreSQLContainer postgres =
        new PostgreSQLContainer("postgres:16.6-alpine");

@DynamicPropertySource
static void datasourceProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
    registry.add("spring.datasource.driver-class-name",
            postgres::getDriverClassName);
}
~~~

This snippet assumes the container is managed by the JUnit Testcontainers extension via `@Testcontainers` and `@Container`. With the JUnit extension, a static container stops after the test class finishes, whereas Spring may cache the `ApplicationContext` and reuse it across classes. If the cached context survives while the container has stopped, subsequent tests fail to connect. With Spring Boot, prefer Spring-managed container beans or `@ImportTestcontainers` when sharing contexts across classes.

## 4. Running Real Migrations Before Testing Repositories

A core goal of this lab is ensuring the schema is created by production migrations. Never let Hibernate generate tables on its own and conclude your migrations are valid.

With Flyway, place migrations in `src/main/resources/db/migration`:

`V1__create_account.sql` for PostgreSQL:

~~~sql
CREATE TABLE account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_account_email UNIQUE (email)
);
~~~

When running the same feature on MySQL, migrations may require engine-specific syntax, for example:

`V1__create_account.sql` in the MySQL migration folder:

~~~sql
CREATE TABLE account (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_account_email UNIQUE (email)
);
~~~

Do not assume a migration using engine-specific identity, JSON, sequence, index, or function syntax will run unchanged across both engines. If multiple vendors must be supported, use separate migration folders or verified portable DDL. Flyway supports the `{vendor}` placeholder in locations, for example:

~~~properties
spring.flyway.locations=classpath:db/migration/{vendor}
~~~

The directory name is resolved from the vendor detected by Flyway, such as `postgresql` or `mysql`. Verify the resolved path in Flyway startup logs.

Test configuration:

~~~properties
spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=false
~~~

When Spring initializes the `ApplicationContext`, Flyway connects to the container, reads unapplied migrations, and runs them. Hibernate then initializes `EntityManagerFactory` and validates mappings against the resulting schema.

`ddl-auto=validate` catches certain table/column mismatches between entities and the schema. It does not replace testing every index, trigger, check constraint, extension, or migration data transformation. Therefore, still test critical constraints directly. If the schema is managed entirely by migrations, you can also use `ddl-auto=none` and verify the schema with dedicated tests.

Never use `create` or `create-drop` in production-migration tests, because Hibernate would create tables itself and mask missing or broken migrations. Nor should you mix `schema.sql`/`data.sql` with Flyway or Liquibase to manage the same schema.

### If Using Liquibase

Place the master changelog at the default path or configure it explicitly:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:db/changelog/db.changelog-master.yaml
spring.jpa.hibernate.ddl-auto=validate
~~~

Example YAML changelog:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-account
      author: team
      changes:
        - createTable:
            tableName: account
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    nullable: false
              - column:
                  name: email
                  type: VARCHAR(320)
                  constraints:
                    nullable: false
                    unique: true
              - column:
                  name: display_name
                  type: VARCHAR(120)
                  constraints:
                    nullable: false
~~~

Liquibase applies the changelog against the container's `DataSource` at Spring startup. The `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK` tables track execution history and lock status. When verifying rollbacks or contexts/labels, run the exact changelog and settings mirroring deployment.

## 5. Entities, Repositories, and Sample Data

Entities must match the migrated schema. Example:

~~~java
@Entity
@Table(name = "account")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 320, unique = true)
    private String email;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    protected Account() {
    }

    public Account(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Repository:

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {
    Optional<Account> findByEmail(String email);

    List<Account> findByDisplayNameContainingIgnoreCase(String keyword);

    boolean existsByEmail(String email);
}
~~~

In the example, getters and constructors show only what is needed for the test illustration. Real entities may use auditing, enums, relationships, embedded types, or custom converters; those mappings should also be verified against a production-compatible database.

Fixtures should be intentional and isolated:

- Use builders/factories to create valid entities with sensible defaults.
- Use distinct emails or business keys per test to prevent data collisions.
- Use `@Sql` with scripts under `src/test/resources` when a fixed dataset is needed.
- Use `JdbcTemplate` to seed specialized data or inspect schema state directly.
- Never depend on test execution order or specific auto-increment ID values.

Example SQL fixture:

~~~sql
INSERT INTO account(email, display_name)
VALUES ('seed@example.com', 'Seed Account');
~~~

If tests target both PostgreSQL and MySQL, keep fixtures portable or split them by vendor wherever syntax or data types differ.

## 6. Testing Repositories Against a Real Database

A test that reloads an entity after flushing and clearing proves the data round-tripped through the database rather than merely returning an object from the persistence context:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(PostgresContainerConfiguration.class)
class AccountRepositoryPostgresTest {

    @Autowired
    private AccountRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void savesAndReloadsAccount() {
        Account saved = repository.saveAndFlush(
                new Account("alice@example.com", "Alice")
        );

        Long id = saved.getId();
        assertThat(id).isNotNull();

        entityManager.clear();

        Account reloaded = repository.findById(id).orElseThrow();

        assertThat(reloaded.getEmail()).isEqualTo("alice@example.com");
        assertThat(reloaded.getDisplayName()).isEqualTo("Alice");
        assertThat(reloaded.getCreatedAt()).isNotNull();
    }

    @Test
    void findsByEmailAndName() {
        repository.saveAndFlush(
                new Account("bob@example.com", "Bob Nguyen")
        );

        assertThat(repository.findByEmail("bob@example.com")).isPresent();
        assertThat(repository.findByDisplayNameContainingIgnoreCase("BOB"))
                .extracting(Account::getEmail)
                .contains("bob@example.com");
    }
}
~~~

This test verifies insertion, ID generation, default timestamps, and query methods. Depending on the schema, `created_at` might receive a database default on insert. If Hibernate inserts an explicit `NULL` instead of omitting the column, the default will not fire; configure the mapping accordingly or assign the value via entity lifecycle/auditing.

Test categories to cover:

- CRUD and relationship mappings: `@ManyToOne`, `@OneToMany`, cascades, orphan removal.
- Derived queries, JPQL, Criteria/Specification, and native queries.
- Pagination/sorting, count queries, projections, and fetch strategies.
- Unique, not-null, foreign key, check constraints, and default values.
- Specialized data types: UUID, JSON/JSONB, enums, timestamps, decimals, and collations.
- Optimistic locking with `@Version`, pessimistic locking, and isolation levels where relied upon.
- Batch inserts/updates, stored procedures, triggers, or functions if used in production.

Do not merely assert that a repository returns a result; verify order, counts, null values, precision, and business edge cases.

### Verifying Real Constraints

~~~java
@Test
void rejectsDuplicateEmail() {
    repository.saveAndFlush(
            new Account("same@example.com", "First")
    );

    assertThatThrownBy(() ->
            repository.saveAndFlush(
                    new Account("same@example.com", "Second")
            )
    ).isInstanceOf(DataIntegrityViolationException.class);
}
~~~

`saveAndFlush()` forces Hibernate to send the insert so the database enforces the unique constraint right inside the call. The exact exception hierarchy can vary by provider/translator, though Spring Data JPA typically translates it to `DataIntegrityViolationException`.

Once an SQL statement fails, the transaction may be marked rollback-only or the database connection may enter an aborted state. Do not execute further write queries inside the same test transaction to inspect the aftermath. Isolate each constraint scenario in its own test method or verify post-rollback state in a separate transaction.

## 7. Verifying Migrations Ran and Schema Matches

With Flyway, you can query the migration history table:

~~~java
@Autowired
private JdbcTemplate jdbcTemplate;

@Test
void flywayAppliedMigrations() {
    Integer successful = jdbcTemplate.queryForObject(
            "select count(*) from flyway_schema_history where success = true",
            Integer.class
    );

    assertThat(successful).isNotNull();
    assertThat(successful).isGreaterThan(0);
}
~~~

With Liquibase, check `DATABASECHANGELOG` and `DATABASECHANGELOGLOCK`. However, counting history rows alone does not prove the schema is right. Verify specific versions, checksums, or expected structures; then run repository queries against that schema.

Maintain at least two migration test categories:

**Fresh install:** start an empty container, run all migrations from version one, and verify repositories work.

**Upgrade path:** stand up the schema at an older version, seed representative data, apply new migrations, and verify existing data remains intact. This catches data-conversion bugs, missing defaults, failing new constraints, or unsafe migrations against real rows.

With Flyway, never edit a versioned migration file already applied to shared environments. Add a new versioned migration instead; `validate` will catch unintended checksum edits. With Liquibase, avoid modifying deployed changeSets unless you have a deliberate checksum/`clearCheckSums` process; prefer adding new changeSets.

## 8. Choosing @DataJpaTest or @SpringBootTest for Migrations?

`@DataJpaTest` works well when testing repositories and mappings against a database container. The slice auto-configures `DataSource`, `EntityManager`, and repositories, wrapping each test in a rolling-back transaction by default. Import the container configuration and set `replace = NONE` to keep the real database.

`@SpringBootTest(webEnvironment = NONE)` fits when proving the full application boots against the container, runs migrations, wires services, and executes business transactions. Example:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Import(PostgresContainerConfiguration.class)
@ActiveProfiles("test")
class AccountServiceIntegrationTest {

    @Autowired
    private AccountService accountService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void serviceCreatesAccount() {
        Account account = accountService.register(
                "service@example.com",
                "Service Test"
        );

        assertThat(account.getId()).isNotNull();
        assertThat(accountRepository.findByEmail("service@example.com"))
                .isPresent();
    }
}
~~~

If the service method has `@Transactional`, the transaction opened by the service commits when the method finishes, because this test class is not annotated with `@Transactional`. Adding `@Transactional` to the test class would wrap everything in an outer test transaction that rolls back at the end of the test.

### Testing Commit and Rollback

`@DataJpaTest` rolls back test transactions by default. That helps with cleanup, yet does not prove the commit path works. To verify commits, disable test-managed transactions on the test method:

~~~java
@Test
@Transactional(propagation = Propagation.NOT_SUPPORTED)
void serviceCommitIsVisibleAfterMethodReturns() {
    accountService.register("commit@example.com", "Commit Test");

    assertThat(accountRepository.findByEmail("commit@example.com"))
            .isPresent();
}
~~~

This example assumes `register()` opens its own transaction via the Spring proxy. To test rollbacks, trigger a business error after writing, let the exception escape the transactional service, and verify the data is absent in a fresh transaction.

With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, HTTP requests execute on separate server threads/transactions. A test method's transaction does not enclose the server request's transaction, so automatic test rollback will not erase data committed by the server. Clean up explicitly or use an isolated database/schema.

## 9. Data Isolation and Container Lifecycle

One container can be shared across multiple test methods in a class or across classes when Spring reuses the cached `ApplicationContext`. This saves startup time but requires strict data hygiene.

- Generate unique business keys per test, such as emails suffixed with test names or UUIDs.
- Use `@Sql` or fixture builders to seed required data before each test.
- Use rolling-back transactions for standard repository tests.
- For commit tests or multi-transaction tests, clean up data in a separate transaction or use an isolated schema/database.
- Never rely on auto-increment IDs starting at 1; sequences typically do not roll back.
- Do not run tests in parallel against shared mutable data without isolation.
- Never allow one test method to depend on data created by another test method.

Static containers managed by the JUnit extension stop after the test class finishes. Spring TestContext may cache and reuse the `ApplicationContext` across classes; a live context pointing at a stopped container causes confusing connection errors. Therefore, with Spring Boot, prefer container beans or `@ImportTestcontainers` so the container's lifecycle aligns with the `ApplicationContext` lifecycle.

Do not enable reusable containers in CI without a reliable data-reset and isolation strategy. Container reuse can speed up local development, yet leaves stale state across runs if not cleaned carefully.

## 10. Running in CI

Testcontainers requires a Docker-compatible runtime. Before running tests, CI runners must have access to a Docker daemon or supported container environment. Example commands:

~~~bash
./mvnw -Dtest=AccountRepositoryPostgresTest test
~~~

Or:

~~~bash
./gradlew test --tests "*AccountRepositoryPostgresTest"
~~~

CI guidelines:

1. Pin container image versions and dependency BOMs.
2. Run container tests in jobs equipped with a Docker runtime.
3. Never silently fall back to H2 when Docker is unavailable; production-compatible jobs must explicitly report whether tests ran or were skipped.
4. Collect container and migration logs on test failure.
5. Run fast tests frequently and Testcontainers suites at least before merging or releasing.
6. If supporting multiple database engines, use separate PostgreSQL/MySQL matrix jobs so failures identify the exact engine.
7. Use image caching to reduce pull latency, without using mutable tags like `latest`.

Testcontainers automatically stops and removes lifecycle-managed containers. If containers are left behind, check for killed test processes, Docker runtime state, or cleanup configuration. Never hard-code host ports; always use the connection details provided by Testcontainers.

## 11. Common Errors and Fixes

| Symptom | Possible Cause | Fix |
|---|---|---|
| Docker daemon unavailable | Docker is not running or CI lacks permissions | Check Docker context/socket and runner permissions |
| Tests still run on H2 | `@DataJpaTest` replaces embedded datasource | Set `replace = NONE` and verify `@ServiceConnection` |
| Cannot create `ConnectionDetails` | Missing `spring-boot-testcontainers` or unrecognized container type | Check dependencies and container class |
| `No suitable driver` | Missing corresponding JDBC driver | Add the PostgreSQL/MySQL driver |
| Flyway reports missing database plugin | Missing Flyway module for the engine | Add matching `flyway-database-postgresql` or `flyway-mysql` version |
| Flyway cannot find migrations | Wrong location, profile, or filename | Check `spring.flyway.locations` and classpath directory |
| Hibernate `validate` fails | Entity and migration schema mismatch | Compare column names, types, nullability, and version columns |
| Test passes yet commit fails | Only tested inside rolling-back transaction | Add dedicated commit tests |
| Subsequent tests lose connection | JUnit stopped container while Spring cached the context | Manage the container as a Spring bean or import container configuration |
| PostgreSQL passes but MySQL fails | Vendor-specific SQL, collation, type, or migration | Split migrations/fixtures by engine and test on exact target versions |

When debugging, inspect Spring startup logs, resolved JDBC URL/driver, Flyway/Liquibase logs, and container logs. Never print passwords or sensitive bind values in CI logs.

## 12. Multi-Layered Testing Strategy

A balanced test pipeline can be structured as:

| Layer | Tools | What It Proves |
|---|---|---|
| Unit tests | JUnit, Mockito | Business rules independent of the database |
| Fast repository tests | H2 or database container | Portable mappings and queries |
| Repository integration | Testcontainers PostgreSQL/MySQL | Real SQL, types, constraints, and dialect behavior |
| Migration tests | Flyway/Liquibase on containers | Fresh installs and schema upgrades |
| Service/transaction integration | `@SpringBootTest` + container | Commits, rollbacks, and multi-bean collaboration |
| CI matrix | PostgreSQL/MySQL jobs | Each engine verified independently |

If production runs solely on PostgreSQL, prioritize a PostgreSQL container matching the production major version; there is no need to run MySQL just because Testcontainers supports it. If the product supports multiple databases, each engine needs its own migration set and integration suite. Passing on one engine does not prove compatibility with another.

## 13. Pre-Completion Checklist

- [ ] Chosen the right engine and pinned an image version close to production.
- [ ] Included Testcontainers JUnit and matching database module dependencies.
- [ ] Included the JDBC driver and `spring-boot-testcontainers` when using `@ServiceConnection`.
- [ ] Container lifecycle is aligned with the Spring `ApplicationContext`.
- [ ] `@DataJpaTest` sets `replace = NONE` when running on a container.
- [ ] Production migrations actually execute against the database container.
- [ ] Hibernate uses `validate` or `none` instead of auto-generating schema over migrations.
- [ ] Tests verify repository round-trips after flush/clear.
- [ ] Tests verify unique/FK/not-null/default constraints and critical native queries.
- [ ] Tests cover both fresh-install and upgrade-path migrations.
- [ ] Tests verify commit and rollback at appropriate transaction boundaries.
- [ ] Fixtures are isolated and independent of execution order or auto-increment IDs.
- [ ] CI provides a Docker runtime and never silently skips container tests.
- [ ] Container and migration logs are sufficient to diagnose failures.

## 14. Official References

- [Spring Boot Testcontainers and @ServiceConnection](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot testing: @DataJpaTest, @SpringBootTest, and transaction rollback](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Testcontainers PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)
- [Testcontainers MySQL module](https://java.testcontainers.org/modules/databases/mysql/)
- [Testcontainers JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/)
- [Flyway PostgreSQL support](https://documentation.red-gate.com/fd/postgresql-database-277579325.html)
- [Flyway MySQL support](https://documentation.red-gate.com/fd/mysql-277579322.html)
- [Spring Boot database initialization and Flyway/Liquibase](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html)

## Conclusion

Testcontainers lets Spring Data JPA repository tests run against real PostgreSQL or MySQL instances in an isolated environment. By wiring containers with `@ServiceConnection`, running Flyway/Liquibase migrations, and letting Hibernate validate the schema, tests verify both database initialization and repository behavior. Choose `@DataJpaTest` for repository slices, `@SpringBootTest` for full services and transactions, test commits and rollbacks explicitly, maintain repeatable fixtures, and configure Docker runtimes in CI. A test is only production-trustworthy when it executes against the same engine, migrations, and version that the application deploys.
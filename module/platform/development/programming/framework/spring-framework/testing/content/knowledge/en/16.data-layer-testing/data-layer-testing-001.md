# Loading Required DataSource and Repository Configurations

Data-layer testing requires a `DataSource` capable of connecting to a database and a set of repositories appropriate for the test scope. With Spring Data JPA, the context also needs to recognize entities, create an `EntityManagerFactory`, and provide a transaction manager. With JDBC, the context requires a `JdbcTemplate` or the corresponding DAOs. If any part of the configuration is missing, tests may fail to start, inject the wrong repository, or run against a different database than expected.

When preparing tests, clearly determine what you want to verify: SQL statements, entity mapping, repository queries, transactions, or the entire flow from service to database. Based on that goal, choose a test slice or full application context, then load the appropriate `DataSource`, repositories, and related configuration. A smaller data context typically runs faster and is easier to diagnose; a full context is appropriate when coordination with other beans itself is what needs testing.

## 1. Required Components in the Data Layer

A Spring test working with a database typically requires several of the following components:

| Component | Role | Examples |
| --- | --- | --- |
| `DataSource` | Provides JDBC connections to the database | HikariCP, H2, PostgreSQL datasource |
| JDBC access | Executes SQL directly | `JdbcTemplate`, `NamedParameterJdbcTemplate` |
| Entity | Describes data managed by the ORM | `@Entity Order` |
| `EntityManagerFactory` | Creates `EntityManager` instances for JPA | `LocalContainerEntityManagerFactoryBean` |
| Repository | Provides query and persistence APIs | `JpaRepository`, `CrudRepository`, custom DAO |
| Transaction manager | Manages transaction boundaries | `DataSourceTransactionManager`, `JpaTransactionManager` |
| Schema and sample data | Creates table structures and fixtures | Flyway, Liquibase, `schema.sql`, `@Sql` |

Not every test needs all of these components. A JDBC test may only need a `DataSource` and `JdbcTemplate`. A JPA repository test requires entity mapping, repository infrastructure, and a transaction manager. A service test calling a repository may also need service beans and other collaborators.

## 2. Choosing Test Scope Before Loading Configuration

Spring Boot provides test slices to initialize only the part of the application related to the data layer:

| Annotation | Primary Scope | When Appropriate |
| --- | --- | --- |
| `@JdbcTest` | JDBC infrastructure and related components | Testing SQL, `JdbcTemplate`, or JDBC components |
| `@DataJpaTest` | Entities, Spring Data JPA repositories, and JPA infrastructure | Testing mappings, derived queries, JPQL, and repositories |
| `@SpringBootTest` | Broad ApplicationContext according to Boot configuration | Testing repositories together with services, transactions, events, or other modules |
| `@SpringJUnitConfig` | Spring TestContext with specified Java/XML configuration | Using plain Spring Framework or a custom-designed context |

`@DataJpaTest` and `@JdbcTest` typically configure transactions for test methods and roll back after each method. By default, they do not load all application services. If a test needs a supporting bean, it can be imported using `@Import` or a test configuration.

Do not use `@SpringBootTest` just because a repository cannot be found. First check package scanning, entity scanning, and slice configuration. Switch to a full context only when the behavior under test genuinely depends on application-wide configuration.

## 3. Configuring DataSource in Spring Boot

Spring Boot can auto-configure a `DataSource` from `spring.datasource.*` properties, provided a suitable JDBC driver and dependencies are on the classpath.

Example configuration in `application-test.yml`:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders_test
    username: test_user
    password: test_password
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 4
      minimum-idle: 1
```

Common properties:

- `spring.datasource.url`: JDBC URL of the database.
- `spring.datasource.username` and `spring.datasource.password`: authentication credentials.
- `spring.datasource.driver-class-name`: JDBC driver; Boot can usually infer this from the URL.
- `spring.datasource.hikari.*`: pool configuration if the datasource uses HikariCP.

Do not put production passwords into test resources or source control. Use dedicated credentials for the test database, environment variables, or CI secrets. If tests use a dynamically created database, URL and credentials can be supplied via dynamic properties.

Activating the test profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderRepositoryIntegrationTest {
}
```

`@ActiveProfiles("test")` instructs Spring to load the `test` profile configuration, such as `application-test.yml` in Spring Boot. A profile only selects configuration; it does not automatically create the database, schema, or user accounts.

## 4. Required Dependencies for Data Testing

With Spring Boot and JPA, the commonly used dependencies are `spring-boot-starter-data-jpa`, the JDBC driver for the database, and `spring-boot-starter-test` in test scope. If using H2 as an embedded database, add H2 in test scope.

Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

If using PostgreSQL, add the PostgreSQL driver in a scope appropriate for how the application runs. With Testcontainers, add the corresponding database module and `spring-boot-testcontainers` if using `@ServiceConnection`.

Do not add multiple drivers or databases simultaneously just for random trial-and-error. Decide whether tests need an embedded database, a container database, or a dedicated database provided by CI.

## 5. What Does `@DataJpaTest` Auto-Configure?

`@DataJpaTest` is a test slice dedicated to JPA. It configures common components such as:

- Entity scanning and Spring Data JPA repositories according to application configuration.
- `DataSource` and JPA infrastructure.
- `EntityManager` for tests.
- Test-managed transactions; rolls back by default after each test method.
- Components required to test repositories without loading the entire application context.

Example:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository orderRepository;

    @Test
    void findsOrdersByCustomerId() {
        orderRepository.save(new Order("customer-42"));

        List<Order> result = orderRepository.findByCustomerId("customer-42");

        assertEquals(1, result.size());
    }
}
```

A test slice enables testing the real repository against a test database. There is no need to mock `OrderRepository` because the repository itself is the object under test.

`@DataJpaTest` does not load all `@Service`, controller, or custom application beans by default. If you need to test a service calling a repository, consider `@SpringBootTest` or importing the required service into the slice when the structure is suitable.

## 6. Choosing an Embedded Database vs. a Real Database

Depending on default configuration and Spring Boot version, `@DataJpaTest` may replace the application datasource with an embedded database if a compatible embedded database is on the classpath. H2 is commonly used for this purpose.

An embedded database has advantages:

- Fast startup and easy to run on a developer machine.
- No need to install a database server.
- Data can be recreated per context or based on URL configuration.
- Suitable for basic repository tests and verifying relatively portable SQL logic.

However, an embedded database may differ from the production database in:

- SQL syntax and engine-specific functions.
- Data types, collation, timezone, and sequences.
- Constraints, indexes, locking, and isolation.
- Query planner and performance.
- Database migration or extension behavior.

If the application runs on PostgreSQL, MySQL, or Oracle in production, there should be integration tests on the exact same engine via Testcontainers or a dedicated test database. H2 remains useful for fast tests, but cannot replace verifying compatibility with the production database.

## 7. Keeping the Configured Datasource with `@AutoConfigureTestDatabase`

When you want `@DataJpaTest` to use the configured datasource instead of replacing it with an embedded database, you can use:

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgreSqlOrderRepositoryTest {
    // ...
}
```

`Replace.NONE` requests keeping the configured datasource. This is the common choice when the datasource points to a PostgreSQL Testcontainers instance or a test database provided by CI.

Distinguish between two goals:

- Wanting to use an embedded database for fast tests: allow the test slice to replace the datasource per the Boot version's default configuration.
- Wanting to verify behavior on a specific database: keep the supplied datasource and ensure the URL points to a safe test environment.

Do not set `Replace.NONE` mechanically if the application has a default URL pointing to a shared or production database. Test configuration must explicitly ensure which database is allowed to receive test data.

## 8. Launching PostgreSQL with Testcontainers

Testcontainers creates a real database inside a container, enabling queries and mappings to be tested on the same database type as production. A common approach is the JUnit Testcontainers extension combined with `@DynamicPropertySource`.

```java
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class OrderRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderUsingPostgreSql() {
        repository.save(new Order("customer-42"));

        assertTrue(repository.existsByCustomerId("customer-42"));
    }
}
```

In this example, the container is started by the Testcontainers JUnit extension. `@DynamicPropertySource` supplies the JDBC URL, username, and password to Spring Boot. `Replace.NONE` keeps the datasource configured from the container.

To compile this example, the project needs the Testcontainers PostgreSQL module, JUnit Jupiter integration, and the PostgreSQL driver. When using Spring Boot 3.1 or later, consider `@ServiceConnection` with the `spring-boot-testcontainers` dependency so Boot can automatically infer connection details from the container.

The container does not create the application schema automatically. You need to configure Hibernate DDL, Flyway, Liquibase, or SQL initialization to create tables before repository tests run.

## 9. Using `@ServiceConnection` with Spring Boot

Spring Boot supports `@ServiceConnection` to automatically create connection details for several popular Testcontainers containers. Example:

```java
@DataJpaTest
@Testcontainers
class OrderRepositoryContainerTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    OrderRepository repository;
}
```

`@ServiceConnection` requires Spring Boot support for this API and the `spring-boot-testcontainers` dependency. This approach reduces the number of properties that must be registered manually. If the container or service type is not automatically supported, `@DynamicPropertySource` or `DynamicPropertyRegistrar` can be used depending on the Spring version.

Do not combine multiple mechanisms registering the same property without reason. Choose a single clear source of connection details to avoid confusion over which values are actually being used.

## 10. Loading Repositories and Entities in Separate Packages

Spring Boot usually infers package scanning from the `@SpringBootApplication` class or main configuration. If entities or repositories reside outside the root package, the scope must be specified explicitly.

Example:

```java
@SpringBootApplication
@EntityScan(basePackageClasses = OrderEntity.class)
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
public class OrdersApplication {
}
```

`@EntityScan` specifies the package containing entities; `@EnableJpaRepositories` specifies the package containing Spring Data repositories. Use `basePackageClasses` to avoid string-based package names and keep references to marker classes.

In a test slice, if Boot does not find an entity or repository, check the root package and scan configuration first. Add separate `@EnableJpaRepositories` or `@EntityScan` annotations in tests only when the package structure genuinely requires explicit configuration.

If a repository is defined in a library module, ensure that module is on the test runtime classpath and its package is included in repository scanning.

## 11. Configuring Spring Data Repositories with `@EnableJpaRepositories`

In plain Spring Framework or manual JPA configuration, `@EnableJpaRepositories` enables detection and implementation generation for repository interfaces.

```java
@Configuration
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
class JpaRepositoryConfig {
}
```

Example repository:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {

    List<Order> findByCustomerId(String customerId);
}
```

Spring Data creates a proxy implementation for the repository. You do not manually write a class implementing every CRUD method. However, custom repository fragments or separate implementations still need to be placed in the right package and follow Spring Data's corresponding naming conventions/configuration.

Useful attributes of `@EnableJpaRepositories` include `basePackages`, `basePackageClasses`, `entityManagerFactoryRef`, and `transactionManagerRef`. With a single default datasource, these references are usually inferred. With multiple datasources, you must explicitly specify which entity manager factory and transaction manager each repository group uses.

## 12. Configuring JPA in Plain Spring Framework

Without Spring Boot auto-configuration, you must declare `DataSource`, `EntityManagerFactory`, a transaction manager, and repository scanning.

Example test configuration with H2:

```java
@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
class JpaTestConfig {

    @Bean
    DataSource dataSource() {
        return new EmbeddedDatabaseBuilder()
            .setType(EmbeddedDatabaseType.H2)
            .addScript("classpath:/db/schema.sql")
            .build();
    }

    @Bean
    LocalContainerEntityManagerFactoryBean entityManagerFactory(
            DataSource dataSource) {

        var factory = new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.orders.domain");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
            "hibernate.hbm2ddl.auto", "none",
            "hibernate.show_sql", "false"
        ));
        return factory;
    }

    @Bean
    PlatformTransactionManager transactionManager(
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Test using the configuration:

```java
@SpringJUnitConfig(JpaTestConfig.class)
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void savesOrder() {
        // ...
    }
}
```

This example assumes Spring ORM, Spring Data JPA, Hibernate, H2, and Spring Test dependencies are declared. `EmbeddedDatabaseBuilder` belongs to Spring JDBC. `setPackagesToScan` must point to the package containing entities. `@EnableJpaRepositories` must point to the package containing repository interfaces.

In real configurations, prefer package marker classes over package strings where appropriate. Also ensure lifecycle management of the datasource and entity manager factory via Spring bean destruction.

## 13. Configuring JDBC Tests with `@JdbcTest`

If a component uses plain JDBC, there is no need to stand up JPA infrastructure. `@JdbcTest` creates a slice focused on the datasource and JDBC support:

```java
@JdbcTest
class OrderJdbcRepositoryTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void insertsAndReadsOrder() {
        jdbcTemplate.update(
            "insert into orders(id, customer_id, status) values (?, ?, ?)",
            42L, "customer-42", "PENDING"
        );

        String status = jdbcTemplate.queryForObject(
            "select status from orders where id = ?",
            String.class,
            42L
        );

        assertEquals("PENDING", status);
    }
}
```

`@JdbcTest` typically configures an embedded database if available and rolls back transactions after tests. If you need to test a specific DAO component, you can import it:

```java
@JdbcTest
@Import(OrderJdbcRepository.class)
class OrderJdbcRepositoryTest {
}
```

Do not use `@DataJpaTest` for plain JDBC DAOs if an entity manager is not needed. Choosing the right slice keeps the context small and makes the test clearly express the data access technology under test.

## 14. Loading Custom Repository Configuration into a Test Slice

Sometimes a repository requires a converter, custom implementation, or supporting bean that the slice does not load automatically. You can create a `@TestConfiguration`:

```java
@TestConfiguration(proxyBeanMethods = false)
class RepositoryTestSupport {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Import into the test:

```java
@DataJpaTest
@Import(RepositoryTestSupport.class)
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;
}
```

`@TestConfiguration` adds beans dedicated specifically to tests. Do not place test helpers inside production scan packages if you do not want those beans appearing in the runtime application.

If a repository depends on a converter or custom bean, import only the needed component. Avoid using application-wide `@ComponentScan` inside `@DataJpaTest`, as doing so can turn the slice into a near-full application context and increase startup time.

## 15. Using `@ContextConfiguration` to Load Dedicated Data Configuration

In plain Spring Framework, `@ContextConfiguration` specifies the exact configurations to load:

```java
@SpringJUnitConfig(classes = {
    JpaTestConfig.class,
    RepositoryTestSupport.class
})
class OrderRepositoryIntegrationTest {

    @Autowired
    OrderRepository repository;
}
```

If using XML:

```java
@SpringJUnitConfig(locations = "classpath:/spring/persistence-test-context.xml")
class LegacyRepositoryTest {
}
```

Java configuration and XML can be combined if a project is migrating gradually:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = JpaTestConfig.class,
    locations = "classpath:/spring/legacy-datasource-test.xml"
)
class RepositoryMigrationTest {
}
```

Ensure beans declared across multiple sources do not collide in name or type in a way that causes ambiguity. If a test uses Spring Boot, consider `@DataJpaTest` or `@SpringBootTest` before building the entire configuration manually.

## 16. Entity Scan and Repository Scan Are Two Separate Concerns

A common issue is that the repository interface is found while the entity is not recognized, or entities are found while repository proxies are not created.

Two scopes must be distinguished:

- Entity scan looks for classes with `@Entity`, `@Embeddable`, or related persistence types according to configuration.
- Repository scan looks for Spring Data interfaces such as `JpaRepository` and creates proxies.

In Spring Boot configuration:

```java
@EntityScan(basePackageClasses = OrderEntity.class)
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
```

In plain JPA configuration:

```java
factory.setPackagesToScan("com.example.orders.domain");
```

and:

```java
@EnableJpaRepositories(basePackageClasses = OrderRepository.class)
```

If a test reports `Not a managed type`, check the entity package and entity manager factory. If it reports a missing repository bean, check repository scanning, Spring Data dependencies, and context configuration.

## 17. Configuring Schema and Initialization Data

Repositories only work once the required schema exists. There are several common strategies:

| Schema Creation Approach | When Appropriate | Points to Watch |
| --- | --- | --- |
| Hibernate DDL (`create`, `create-drop`) | Fast tests with simple entity mappings | May not reflect production schema and migrations |
| `schema.sql` / `data.sql` | Small schemas or explicit SQL fixtures | Requires proper timing and database platform configuration |
| Flyway | Versioned migrations used at runtime | Good when wanting to test real migrations |
| Liquibase | ChangeLogs managing schema | Use the same changelog as production if testing the real schema |
| `@Sql` | Per-test-method/class fixtures | Must manage transactions and cleanup |

With Spring Boot, Hibernate DDL can be configured for tests:

```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
```

Use `create-drop` only when tests intentionally want the schema generated from entity metadata. If production uses Flyway or Liquibase, important integration tests should run real migrations to catch discrepancies between entities and the deployed schema.

With SQL initialization:

```yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:/db/schema-test.sql
      data-locations: classpath:/db/test-data.sql
```

Specific properties should be checked against the Spring Boot version. Avoid having Hibernate DDL, `schema.sql`, and Flyway/Liquibase all try to create the same schema under conflicting policies. Choose one primary mechanism and configure the initialization order explicitly.

## 18. Loading Per-Test Data with `@Sql`

`@Sql` is suitable when each test needs its own fixture or multiple tables need linked data:

```java
@DataJpaTest
@Sql("/sql/orders/insert-order-fixture.sql")
class OrderRepositoryQueryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsPendingOrders() {
        List<Order> result = repository.findByStatus(OrderStatus.PENDING);

        assertFalse(result.isEmpty());
    }
}
```

By default, scripts are typically executed before the test method. You can explicitly set `executionPhase` to `BEFORE_TEST_METHOD` or `AFTER_TEST_METHOD`.

With rollback test transactions, scripts and tests can participate in the transaction according to default settings. If isolated committed cleanup is required, you can use `@SqlConfig(transactionMode = ISOLATED)` and verify that the right transaction manager is selected.

Do not place one giant SQL file as a fixture for every test if each test only needs a few records. Overly broad fixtures couple tests together and obscure which data is actually necessary.

## 19. Flushing and Clearing When Testing JPA Repositories

JPA has a persistence context. When calling `save()`, an entity may only be managed inside the persistence context; SQL has not necessarily been sent to the database yet. A test might read back the same object from the persistence context and still pass even if a mapping or constraint issue would appear on flush.

To test actual database interaction more thoroughly, flush and clear:

```java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    OrderRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void persistsAndReloadsOrder() {
        Order saved = repository.save(new Order("customer-42"));

        entityManager.flush();
        entityManager.clear();

        Order reloaded = repository.findById(saved.getId()).orElseThrow();

        assertEquals("customer-42", reloaded.getCustomerId());
    }
}
```

`flush()` pushes pending changes down to the database, helping catch certain SQL, constraint, or mapping errors. `clear()` detaches managed entities from the persistence context, forcing subsequent queries to read data back again. `TestEntityManager` is a Spring Boot Data JPA Test utility; in plain Spring Framework, `EntityManager` can be used directly.

You do not need to flush/clear in every test. Use them when the goal is to verify that data has been written to and reloaded through the persistence layer, especially for mappings, cascades, constraints, and queries.

## 20. Configuring Multiple DataSources and Multiple Repository Groups

An application may connect to multiple databases, such as an orders database and a reporting database. In that case, each repository group needs to be bound to the appropriate `EntityManagerFactory` and transaction manager.

High-level configuration example:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = OrderRepository.class,
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
class OrdersDatabaseConfig {
    // Declare ordersDataSource, ordersEntityManagerFactory,
    // ordersTransactionManager
}
```

Reporting group:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = ReportRepository.class,
    entityManagerFactoryRef = "reportsEntityManagerFactory",
    transactionManagerRef = "reportsTransactionManager"
)
class ReportsDatabaseConfig {
    // Declare reportsDataSource, reportsEntityManagerFactory,
    // reportsTransactionManager
}
```

When multiple datasources exist, clearly specify:

- Which `DataSource` bean is injected into each entity manager factory.
- Which repository packages belong to which database.
- Which entity packages are scanned by the corresponding entity manager factory.
- Which transaction manager governs repository/service methods.
- Which transaction manager a test transaction should select when multiple options exist.

`@Qualifier` can be used when injecting a datasource or transaction manager. One bean may be marked `@Primary` for the default flow, but tests should not rely on primary when verifying that a repository uses a specific database.

Example of a test selecting a transaction manager:

```java
@DataJpaTest
@Transactional("ordersTransactionManager")
class OrderRepositoryTest {
    // ...
}
```

Annotations and multi-persistence-unit configuration must match the Spring Data JPA version and application structure. With multiple datasources, a small separate test context per database is often easier to diagnose than loading every persistence unit into every test.

## 21. Custom Repositories and Implementation Fragments

A repository can combine Spring Data auto-generated methods with custom implementations. When testing the repository, you must load the interface, entities, and custom fragment implementation.

Example:

```java
public interface OrderRepository extends
        JpaRepository<Order, Long>,
        OrderRepositoryCustom {
}

public interface OrderRepositoryCustom {
    List<Order> searchOpenOrders(String customerId);
}
```

Implementation:

```java
class OrderRepositoryCustomImpl implements OrderRepositoryCustom {

    private final EntityManager entityManager;

    OrderRepositoryCustomImpl(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Override
    public List<Order> searchOpenOrders(String customerId) {
        return entityManager.createQuery(
            "select o from Order o where o.customerId = :customerId " +
            "and o.status = :status", Order.class)
            .setParameter("customerId", customerId)
            .setParameter("status", OrderStatus.OPEN)
            .getResultList();
    }
}
```

Spring Data discovers implementations using fragment naming conventions and matching packages. If the implementation requires other beans, configure them as normal dependencies and ensure they are present in the test context.

Do not mock the custom fragment when the goal is to test its query. Run the real repository against a test database and assert results from the database.

## 22. Verifying DataSource Configuration Directly

When tests fail to start or connect to the wrong database, you can inject `DataSource` and inspect JDBC metadata:

```java
@SpringBootTest
class DataSourceConfigurationTest {

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToExpectedDatabase() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();

            assertEquals("PostgreSQL", metadata.getDatabaseProductName());
        }
    }
}
```

This test confirms the datasource can open a connection and the database engine matches expectations. Do not print the full JDBC URL if it contains sensitive information. If you need to verify the schema or catalog, inspect safe metadata or query an appropriate table/version.

When testing multiple datasources, inject by qualifier and verify each source individually. Do not merely check that the context has a `DataSource` bean; that does not prove a specific repository uses the right datasource.

## 23. Test Data Isolation and Cleanup

With `@DataJpaTest` or `@JdbcTest`, test transactions usually roll back after each method. However, cleanup still needs to be designed if:

- The test uses `@Commit` or `@Rollback(false)`.
- Code opens a `REQUIRES_NEW` transaction.
- Work executes on another thread or via an async executor.
- The database is shared across multiple workers/test processes.
- Side effects occur outside the database transaction.

When manual cleanup is needed, prefer test-specific IDs:

```java
@AfterEach
void cleanUp() {
    repository.deleteByTestRunId(testRunId);
}
```

Do not wipe entire tables on a shared database. If tests run in parallel, use UUIDs, dedicated schemas, or dedicated databases to prevent one test from deleting another test's data.

If a test only modifies business data, `@DirtiesContext` is not needed. The context can be reused; the database should be rolled back or cleaned up at the data source itself.

## 24. Common Errors When Loading DataSource and Repositories

- **Missing JDBC driver:** the datasource cannot open a connection or reports no suitable driver found.
- **Wrong URL or credentials:** context startup fails when the pool attempts to create connections.
- **Test using the wrong database:** the expected profile or property source was not activated.
- **`@DataJpaTest` replacing the datasource unexpectedly:** an embedded database is selected instead of the configured container/database; review `@AutoConfigureTestDatabase`.
- **No embedded database on the classpath:** the test slice has no embedded database available to use; a suitable database must be provided.
- **Entities not scanned:** `Not a managed type` error or the entity manager does not recognize entities.
- **Repositories not scanned:** no repository bean is available to inject.
- **Missing transaction manager:** repositories/services lack an appropriate transaction manager or multiple managers cause ambiguity.
- **Conflicting DDL and migrations:** Hibernate, SQL initialization, and Flyway/Liquibase all attempt to create or modify the schema.
- **H2 differing from production database:** fast tests pass on H2, but queries fail on actual PostgreSQL/MySQL.
- **Slice missing custom beans:** repositories need converters or collaborators that were not imported.
- **Test reading only from the persistence context:** missing flush/clear fails to prove data was written to and read back from the database.
- **Data leakage:** commits, `REQUIRES_NEW`, async work, or shared databases escape transaction rollback.
- **Ambiguity across multiple datasources:** repositories use the wrong entity manager factory or transaction manager.

## 25. Diagnostic Workflow for DataSource and Repositories

When data-layer tests fail to start or produce unexpected results, check in order:

1. **Dependencies:** are Spring Data/JDBC, the JDBC driver, and the required test database present on the test runtime classpath?
2. **Test scope:** are `@JdbcTest`, `@DataJpaTest`, `@SpringBootTest`, or `@SpringJUnitConfig` used appropriately for the goal?
3. **Properties/profiles:** are `spring.datasource.url`, username, password, and active profiles correct?
4. **Datasource replacement:** is the test slice replacing the datasource with an embedded database; is `Replace.NONE` needed?
5. **Schema:** are tables created via migrations, Hibernate DDL, or SQL scripts?
6. **Entity scan:** is the entity package included in the entity manager factory?
7. **Repository scan:** is the repository interface within the scope of `@EnableJpaRepositories` or Boot auto-configuration?
8. **Bean wiring:** does the repository use the expected `DataSource`, `EntityManagerFactory`, and transaction manager?
9. **Transactions:** does the test actually participate in the intended transaction; are there `REQUIRES_NEW`, async calls, or another datasource involved?
10. **Database engine:** is Testcontainers needed to verify production database behavior instead of relying solely on H2?

Appropriate logging can be enabled for `org.springframework.jdbc`, `org.springframework.orm.jpa`, `org.springframework.data.repository`, or the connection pool during diagnosis. Keep logs limited to what is necessary and never log credentials or sensitive data.

## 26. Example Configuration Choices by Goal

| Goal | Suggested Configuration | Database |
| --- | --- | --- |
| Testing a JDBC DAO | `@JdbcTest` and `@Import(dao.class)` | H2 or test database |
| Testing derived repository queries | `@DataJpaTest` | H2 for fast loops |
| Testing PostgreSQL native queries | `@DataJpaTest` + `Replace.NONE` + Testcontainers | PostgreSQL container |
| Testing a service calling repositories and transactions | `@SpringBootTest` or a narrow context with the service | Compatible test database |
| Testing JPA configuration in plain Spring Framework | `@SpringJUnitConfig(JpaTestConfig.class)` | EmbeddedDatabase or container |
| Testing multiple persistence units | Separate contexts, distinct datasources, and explicit repository groups | Separate databases/schemas per group |

A practical strategy typically has multiple layers: unit tests for services using mocked repositories when testing pure logic; repository slice tests using a real or embedded database; a set of integration tests using Testcontainers with the exact production engine; and only a small number of full-context tests verifying end-to-end wiring.

## 27. Summary

Loading the right `DataSource` and repositories forms the foundation of data-layer testing. With Spring Boot, `@JdbcTest` and `@DataJpaTest` provide tailored slices for JDBC and JPA; `@AutoConfigureTestDatabase` controls datasource replacement; Testcontainers or dedicated test databases enable testing on the exact target engine. With plain Spring Framework, you must explicitly declare the datasource, entity manager factory, transaction manager, and repository scanning.

Distinguish entity scanning from repository scanning, schema configuration from datasource configuration, and test transactions from side effects running outside transactions. When the context loads only the required beans and the database is chosen deliberately, data-layer tests become repeatable, easy to diagnose, and provide evidence closely aligned with the real application environment.

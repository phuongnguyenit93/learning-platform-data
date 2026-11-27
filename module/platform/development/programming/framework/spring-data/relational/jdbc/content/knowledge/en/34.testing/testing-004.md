# Distinguishing @DataJdbcTest, @JdbcTest, and @SpringBootTest

Spring Boot provides several testing annotations to create a Spring `ApplicationContext` with different scopes. For applications using Spring Data JDBC, the three commonly considered annotations are `@DataJdbcTest`, `@JdbcTest`, and `@SpringBootTest`.

- `@JdbcTest` creates a test slice for the basic JDBC layer: DataSource and JdbcTemplate. It is suitable when testing DAOs or SQL written directly with JDBC.
- `@DataJdbcTest` creates a test slice dedicated to Spring Data JDBC: in addition to JDBC infrastructure, it configures Spring Data JDBC repositories and aggregate mapping.
- `@SpringBootTest` boots the application's `ApplicationContext` using `SpringApplication`. It is suitable when testing business flows across multiple beans or application integration configuration.

The primary difference is **the ApplicationContext scope and which component types are auto-configured**. Choosing the right annotation makes tests faster, reduces dependencies, and still verifies the layer of interest.

This lesson explains each annotation, which beans are loaded, transactions and rollbacks, databases used in tests, how to add custom configuration, Java examples, and how to choose the right test scope.

## 1. Test Slices and the Full Application Context

Spring Boot calls tests that load only a required subset of configuration **test slices**. A slice restricts component scanning and enables only auto-configurations relevant to the layer under test.

`@JdbcTest` and `@DataJdbcTest` are two test slices. They normally do not load all services, controllers, security, and other business beans of the application.

`@SpringBootTest` creates the `ApplicationContext` through `SpringApplication` and uses the application's main configuration. Therefore, it typically loads more beans and incurs higher startup cost.

You can visualize the scope as follows:

~~~mermaid
flowchart TD
    A["@SpringBootTest"] --> B["Full ApplicationContext"]
    B --> C["Services, repositories, JDBC, configs, and application beans"]
    D["@DataJdbcTest"] --> E["Data JDBC test slice"]
    E --> F["Spring Data JDBC repositories + mapping + JDBC"]
    G["@JdbcTest"] --> H["JDBC test slice"]
    H --> I["DataSource + JdbcTemplate + JDBC infrastructure"]
~~~

The diagram shows the primary scopes. Specific components also depend on auto-configurations on the classpath and the project's test setup.

## 2. Quick Comparison of the Three Annotations

| Criterion | `@JdbcTest` | `@DataJdbcTest` | `@SpringBootTest` |
| --- | --- | --- | --- |
| Scope | JDBC slice | Spring Data JDBC slice | Full ApplicationContext |
| DataSource | Yes | Yes | Yes if configured by application |
| JdbcTemplate | Yes | Yes | Yes if JDBC auto-configuration is enabled |
| Spring Data JDBC repositories | Not the slice's target | Yes | Yes if configured by application |
| Aggregate mapping | Does not auto-configure Spring Data JDBC repository mapping | Yes | Yes if configured by application |
| Regular services/controllers | Not auto-scanned | Not auto-scanned | Loaded per application configuration |
| Default test transaction | Yes, rolls back after each test | Yes, rolls back after each test | Does not automatically add transaction to tests |
| Default database | Embedded database if available | Embedded database if available | Per application configuration |
| Best suited for | Manual DAO/JdbcTemplate/SQL | Repositories, aggregates, converters, mapping | Multi-layer use cases, wiring, and full-app integration |

A common misconception: `@JdbcTest` is not a stripped-down version of `@DataJdbcTest` for testing repositories. Spring Boot clearly states that `@JdbcTest` is for cases needing only a DataSource without Spring Data JDBC; when testing Spring Data JDBC repositories, use `@DataJdbcTest`.

## 3. @JdbcTest: Testing Basic JDBC

`@JdbcTest` fits when the code under test interacts directly with JDBC, such as:

- DAOs using `JdbcTemplate` or `NamedParameterJdbcTemplate`.
- Hand-written JDBC repositories without the Spring Data JDBC repository abstraction.
- Manual SQL statements, parameter binding, row mapping, and JDBC-level transactions.
- A data-access component needing a DataSource without Spring Data JDBC aggregate mapping.

By default, this slice creates an in-memory embedded database if a suitable database dependency is on the classpath and test configuration permits, and configures `JdbcTemplate`.

Regular `@Component` and `@ConfigurationProperties` beans are not scanned. If you need to test a specific DAO, you can add it using `@Import`.

### Example with JdbcTemplate

DAO:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class LedgerDao {

    private final JdbcTemplate jdbcTemplate;

    public LedgerDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countEntries() {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM ledger_entry",
            Integer.class
        );

        return count == null ? 0 : count;
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.test.autoconfigure.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
@Import(LedgerDao.class)
class LedgerDaoTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    LedgerDao ledgerDao;

    @Test
    void countsLedgerEntries() {
        jdbcTemplate.update(
            "INSERT INTO ledger_entry (description) VALUES (?)",
            "Opening balance"
        );

        assertThat(ledgerDao.countEntries()).isEqualTo(1);
    }
}
~~~

`@Import(LedgerDao.class)` brings the DAO into the test context. Without importing it, restricted component scanning may skip creating the `LedgerDao` bean.

The example assumes the `ledger_entry` schema has already been created by test SQL schema initialization or configured migrations. The test does not need to boot the whole application just to verify SQL statements and how the DAO reads results.

## 4. @DataJdbcTest: Testing Spring Data JDBC Repositories

`@DataJdbcTest` is the right choice when testing components belonging to Spring Data JDBC:

- Repositories extending `CrudRepository` or corresponding repository interfaces.
- Aggregate root and child entity mapping.
- `@MappedCollection`, `@Embedded`, `@Id`, and `@Version`.
- Custom converters and JDBC mapping.
- Query methods, derived queries, and aggregate save/read operations.
- Interactions between Spring Data JDBC repositories and `JdbcTemplate`.

By default, this slice creates an embedded database if available, and configures `JdbcTemplate` and Spring Data JDBC repositories. It also scans classes extending `AbstractJdbcConfiguration` to load specialized JDBC configurations.

Regular `@Component` and `@ConfigurationProperties` beans are not scanned. If a test needs a service or helper bean, import it explicitly or declare a test configuration.

### Example: Testing a Repository

Suppose we have an aggregate:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;

@DataJdbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = customers.save(
            new Customer("jens@example.com")
        );

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getEmail())
            .isEqualTo("jens@example.com");
    }
}
~~~

`@DataJdbcTest` auto-configures Spring Data JDBC repositories. You do not need to manually instantiate `JdbcAggregateTemplate` or `JdbcMappingContext` just to run repository CRUD in a test slice.

## 5. @SpringBootTest: Testing the Whole Application

`@SpringBootTest` builds the `ApplicationContext` using `SpringApplication` and uses Spring Boot's main configuration. It is the right choice when a test needs multiple collaborating components:

- Services calling repositories and other services.
- Transactions wrapping an entire use case.
- `ApplicationEvent`, `EntityCallback`, or beans configured across the application.
- Security, validation, configuration properties, or other integrations.
- HTTP flows through controllers and a web server.

Unlike the two test slices, `@SpringBootTest` does not restrict component scanning to a specific slice of the application. Auto-configurations and beans are wired just as in the real running application.

### Example: Testing a Service Using a Repository

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Transactional
class CustomerApplicationServiceTest {

    @Autowired
    CustomerApplicationService service;

    @Test
    void registersCustomerThroughApplicationService() {
        Long customerId = service.register("jens@example.com");

        assertThat(customerId).isNotNull();
    }
}
~~~

`WebEnvironment.NONE` instructs Spring Boot to create an `ApplicationContext` without a web environment. The test still loads application beans, but does not start an embedded web server.

In the example, `@Transactional` is added explicitly so the test runs in a transaction and rolls back after each test via Spring Test. `@SpringBootTest` itself does not add transactions to test methods by default.

### webEnvironment Modes

`@SpringBootTest` supports multiple modes:

| Value | Behavior |
| --- | --- |
| `MOCK` | Default; creates a web ApplicationContext with a mock environment without starting a server |
| `RANDOM_PORT` | Starts a real web server on a random port |
| `DEFINED_PORT` | Starts a real web server on the configured port |
| `NONE` | Creates an ApplicationContext with no web environment |

Use `MOCK` or `NONE` for service/integration tests that do not need an HTTP server. Use `RANDOM_PORT` when testing requests through a real server.

## 6. Transactions and Rollback Across the Three Test Types

`@JdbcTest` and `@DataJdbcTest` run tests in a transaction by default and roll back the transaction when the test completes. Thus, data inserted during a test normally does not remain after the test finishes.

Example:

~~~java
@DataJdbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void createsCustomer() {
        customers.save(new Customer("jens@example.com"));

        assertThat(customers.count()).isEqualTo(1);
    }
}
~~~

After the test, the transaction rolls back so the data is not committed to the test database.

`@SpringBootTest` does not automatically wrap tests in a transaction. If rollback is desired, add `@Transactional` to the class or method:

~~~java
@SpringBootTest
@Transactional
class CustomerServiceIntegrationTest {
    // test service; the test transaction rolls back after each method
}
~~~

### 6.1. When Testing Real Commits Is Needed

If the objective is to check data after commit, a test can use `@Commit` or `@Rollback(false)`, or disable the test transaction with appropriate propagation and manage transactions explicitly. Data cleanup is required so tests do not interfere with each other.

Example disabling the test framework's transaction:

~~~java
@JdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class LedgerDaoNonTransactionalTest {
}
~~~

With no outer test transaction, the DAO or application code uses its own transaction according to its configuration.

### 6.2. Note on RANDOM_PORT and DEFINED_PORT

When `@SpringBootTest` starts a real server, the HTTP client and server execute on different threads. A test method's transaction running on the client thread does not wrap the transaction processed on the server thread.

Therefore, if a test is annotated with `@Transactional` yet sends HTTP requests to a server at `RANDOM_PORT` or `DEFINED_PORT`, server-side transactions will not automatically roll back with the test transaction. Clean up data using test APIs, SQL cleanup, or a dedicated database isolation strategy.

## 7. Which Database Is Used in Tests?

With `@JdbcTest` and `@DataJdbcTest`, Spring Boot configures an in-memory embedded database by default if an embedded database is on the classpath. This keeps tests fast without requiring a separate database instance.

However, an embedded database may differ from the production database in:

- SQL syntax and dialect.
- Data types, enums, JSON, arrays, and sequences.
- Identifier quoting and case-sensitivity rules.
- Locking, isolation levels, and transaction semantics.
- Generated keys, batch inserts, and upserts.
- Constraints and migration behavior.

If you need to test against a pre-configured database, use `@AutoConfigureTestDatabase(replace = Replace.NONE)` so Spring Boot does not replace the existing DataSource with an embedded database.

Example:

~~~java
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.containers.PostgreSQLContainer;

@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgreSqlRepositoryTest {
}
~~~

For production databases such as PostgreSQL, MySQL, or SQL Server, Testcontainers is the right choice for running integration tests against the exact engine. Spring Boot also supports container integration through the service connection mechanism when using compatible versions and modules.

Do not rely solely on H2 to conclude that SQL queries, pessimistic locks, or dialect-specific features work the same as in production.

## 8. Adding Beans and Custom Configuration to a Test Slice

Because test slices limit component scanning, a service or helper bean may not appear in the `ApplicationContext`.

You can add beans with `@Import`:

~~~java
@DataJdbcTest
@Import(CustomerService.class)
class CustomerServiceSliceTest {
    // Repository and CustomerService are loaded for the test
}
~~~

Or declare test-only configuration with `@TestConfiguration`:

~~~java
@TestConfiguration
class CustomerTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

Then import the configuration:

~~~java
@DataJdbcTest
@Import(CustomerTestConfiguration.class)
class CustomerRepositoryTest {
}
~~~

`@TestConfiguration` is added alongside the main test configuration. When declared inside a test class, it does not replace the main application configuration.

With `@DataJdbcTest`, classes extending `AbstractJdbcConfiguration` are scanned to load Spring Data JDBC configuration. This is helpful when the application defines custom conversions, naming strategies, or specialized JDBC settings.

## 9. Package and Dependency Differences Between Spring Boot 3 and 4

Spring Boot 4 split several test slices into dedicated modules. Consequently, test annotation packages changed compared to Spring Boot 3.x.

| Annotation | Spring Boot 3.5 | Spring Boot 4.1 |
| --- | --- | --- |
| `@JdbcTest` | `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` | `org.springframework.boot.jdbc.test.autoconfigure.JdbcTest` |
| `@DataJdbcTest` | `org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest` | `org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest` |
| `@AutoConfigureTestDatabase` | `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` | `org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase` |
| `@SpringBootTest` | `org.springframework.boot.test.context.SpringBootTest` | `org.springframework.boot.test.context.SpringBootTest` |

In Spring Boot 4, the corresponding test slices reside in these modules:

- `spring-boot-jdbc-test` provides `@JdbcTest`.
- `spring-boot-data-jdbc-test` provides `@DataJdbcTest`.
- `spring-boot-test` provides core testing components, including `@SpringBootTest`.

With Gradle, test dependencies can be declared as follows when using Spring Boot 4:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-jdbc-test")
    testImplementation("org.springframework.boot:spring-boot-data-jdbc-test")
}
~~~

Dependency versions should be managed by Spring Boot dependency management/BOM. If you only use one of the two slices, add only the corresponding test module.

Use the dependency versions specified by your project's Spring Boot BOM. Do not copy Boot 4 imports into a Boot 3 project without verifying packages and dependencies.

## 10. Choosing an Annotation by Testing Goal

You can use the following decision table to choose the appropriate scope:

| Question | Annotation to Choose |
| --- | --- |
| Do I only need to test SQL via JdbcTemplate or a JDBC DAO? | `@JdbcTest` |
| Do I need to test CrudRepository, query methods, or Spring Data JDBC aggregate mapping? | `@DataJdbcTest` |
| Do I need to test a service calling repositories, transactions, and multiple application beans? | `@SpringBootTest` |
| Do I need to test controllers or HTTP requests through the full application? | `@SpringBootTest` combined with appropriate web configuration |
| Do I need to test vendor-specific SQL against the production database? | `@DataJdbcTest` or `@JdbcTest` with a real database/Testcontainers |
| Do I need to verify full-application configuration and wiring? | `@SpringBootTest` |

### 10.1. Do Not Combine Multiple Test Slices on the Same Test Class

Spring Boot does not support combining multiple slice annotations such as `@JdbcTest` and `@DataJdbcTest` on the same test class. Each slice has its own component scan filters and auto-configuration list.

If you need one slice plus extra auto-configurations, pick one primary test annotation and add the needed `@AutoConfigure…` annotations or `@ImportAutoConfiguration`.

`@AutoConfigure…` annotations can also be combined with `@SpringBootTest` if you need certain test beans auto-configured while keeping the full `ApplicationContext`.

### 10.2. When Should @Import Be Used in DataJdbcTest?

`@DataJdbcTest` fits repository testing, while regular services are not scanned automatically. If you only want to test a small service coordinating repositories within the slice:

~~~java
@DataJdbcTest
@Import(CustomerApplicationService.class)
class CustomerApplicationServiceSliceTest {

    @Autowired
    CustomerApplicationService service;
}
~~~

This adds only the specified service and dependencies supplied by the test. If the service depends on many beans, event listeners, security, or full-app configuration, `@SpringBootTest` usually reflects the real system better.

## 11. Example: Choosing the Right Test Type for the Same Feature

Suppose the application has a customer registration flow:

~~~text
CustomerController
       |
       v
CustomerApplicationService
       |
       v
CustomerRepository
       |
       v
Spring Data JDBC / DataSource
~~~

You can split tests along boundaries:

- Test `CustomerRepository` with `@DataJdbcTest` to verify mapping and SQL.
- Test any `JdbcTemplate`-based DAO with `@JdbcTest` if there are custom JDBC queries.
- Test `CustomerApplicationService` with `@SpringBootTest` to verify validation, transactions, callbacks, and bean wiring.
- Test HTTP endpoints with `@SpringBootTest(webEnvironment = RANDOM_PORT)` or a suitable web slice if only testing the controller.

There is no need to spin up the full `ApplicationContext` for every repository test. Conversely, testing a use case that depends on many beans should not assume a test slice automatically loads the entire service graph.

## 12. Configuring a Real Database with Testcontainers

An embedded database is helpful for fast tests, but does not replace integration tests against the production database when the application depends on dialect or vendor-specific behavior.

For example, if production uses PostgreSQL, a test slice can use a PostgreSQL container instead of H2:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class PostgreSqlCustomerRepositoryTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17");

    // Configure DataSource to connect to the container,
    // or use Spring Boot service connection appropriate for your version.
}
~~~

This is an illustrative skeleton; how connection details are provided depends on the Spring Boot and Testcontainers versions. With Spring Boot supporting service connections, you can register the container bean with `@ServiceConnection` so Boot configures the corresponding connection details automatically.

What matters is that the test actually connects to the container and is not replaced by an embedded database. `replace = Replace.NONE` preserves the DataSource configured for the test.

Scenarios worth testing on a real database:

- Generated keys and sequences.
- Composite IDs and composite foreign keys.
- Dialect-generated SQL, identifier quoting, and pagination.
- Pessimistic locking, isolation levels, and deadlocks.
- JSON, array, UUID, or vendor-specific data types.
- Flyway/Liquibase migrations and constraints.
- Upserts or queries using database-specific syntax.

Do not rely solely on H2 to conclude that SQL queries, pessimistic locks, or dialect-specific features behave the same as in production.

## 13. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Cannot inject repository in `@JdbcTest` | This is not the Spring Data JDBC repository slice | Use `@DataJdbcTest` |
| Cannot inject service in `@DataJdbcTest` | Slice does not scan regular components | Use `@Import` or `@TestConfiguration` |
| Test passes on H2 but fails in production | SQL, dialect, type, or locking differences | Run tests with production database via Testcontainers |
| Test data disappears after each method | Slice rolls back transactions by default | This is default behavior; use `@Commit` or disable transaction if needed |
| `@SpringBootTest` leaves data behind | No default test transaction | Add `@Transactional` or clean up data explicitly |
| HTTP test with RANDOM_PORT does not roll back data | Requests execute on separate server threads/transactions | Clean up data via API or SQL cleanup |
| Custom converter not loaded in slice | JDBC configuration not in slice context | Register via `AbstractJdbcConfiguration`, `@Import`, or test config |
| Annotation import not found | Test annotation packages differ between Boot 3 and Boot 4 | Check Boot version and corresponding test module |
| Test context starts slowly | Using full context for repository-only tests | Switch to `@DataJdbcTest` or `@JdbcTest` |
| Multiple test slices on one class do not work | Spring Boot does not support combining slice annotations | Pick one slice and add needed auto-configurations |

## 14. Workflow for Organizing Tests in Spring Data JDBC

A test structure can be divided by responsibility:

1. **DAO tests:** use `@JdbcTest` for hand-written JDBC SQL and JdbcTemplate.
2. **Repository tests:** use `@DataJdbcTest` for aggregate mapping, repositories, query methods, converters, and callbacks.
3. **Service integration tests:** use `@SpringBootTest` when verifying multiple collaborating beans and transactions.
4. **Web integration tests:** use `@SpringBootTest` with `MOCK`, `RANDOM_PORT`, or `DEFINED_PORT` as required.
5. **Database compatibility tests:** run slices or full contexts against the exact database using Testcontainers.
6. **Transaction tests:** clearly decide whether tests need default rollback, real commits, or multiple concurrent transactions.
7. **Configuration tests:** import the right custom JDBC configuration or use the full context if configuration is assembled across modules.

Separating tests along boundaries makes failures easy to localize. If a repository test fails, focus on mapping, SQL, and the database. If a service test fails while repository tests pass, inspect business rules or wiring between beans.

## 15. Practice Exercises

### Exercise 1 — Comparing the Two Slices

Write one test using `@JdbcTest` to insert and query with `JdbcTemplate`. Write a second test using `@DataJdbcTest` to save and read the same table using a repository. Observe which beans are injected in each context.

### Exercise 2 — Repository Testing

Create `CustomerRepository` and test save, findById, update, and delete with `@DataJdbcTest`. Confirm data rolls back after the test.

### Exercise 3 — Custom DAO Testing

Create a DAO using `NamedParameterJdbcTemplate`. Use `@JdbcTest` and `@Import` to bring the DAO into the context, then verify parameter binding and row mapping.

### Exercise 4 — Service Testing

Create `CustomerApplicationService` calling a repository and another bean. Use `@SpringBootTest(webEnvironment = NONE)` to verify wiring and business flow.

### Exercise 5 — Transaction Rollback

Compare a default test slice with `@SpringBootTest` with and without `@Transactional`. Inspect data after each test.

### Exercise 6 — Real Database Testing

Migrate a repository test from H2 to PostgreSQL Testcontainers. Verify migrations, generated keys, and queries work on the target database.

### Exercise 7 — Custom Configuration

Register a custom converter or naming strategy in JDBC configuration. Verify it is loaded in `@DataJdbcTest` and compare with `@SpringBootTest`.

### Exercise 8 — HTTP Transactions

Create a `@SpringBootTest(webEnvironment = RANDOM_PORT)` test that sends a request creating data. Confirm the test transaction does not automatically roll back the server-side transaction and design an appropriate cleanup step.

## 16. Official References

- [Spring Boot 4.1 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): test slices, `@JdbcTest`, `@DataJdbcTest`, default transactions, and `@SpringBootTest`.
- [Spring Boot 4.1 — Test Modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html): separate test modules such as `spring-boot-jdbc-test` and `spring-boot-data-jdbc-test`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): annotation packages and test slice configuration in the Boot 3.5 line.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): ApplicationContext, test execution, and transaction management in Spring Test.

`@JdbcTest` focuses on DataSource and JdbcTemplate for plain JDBC; `@DataJdbcTest` adds Spring Data JDBC repositories and mapping; `@SpringBootTest` tests the application with the full `ApplicationContext`. Choose the smallest scope that still covers the behavior you need to verify, and use the right database when tests depend on production dialects, locking, or data types.

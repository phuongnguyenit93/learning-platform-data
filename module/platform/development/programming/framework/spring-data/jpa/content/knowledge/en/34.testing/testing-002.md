# Auto-Configuration Scope of @DataJpaTest

## 1. What Is @DataJpaTest Used For?

`@DataJpaTest` is a Spring Boot slice testing annotation for the persistence layer. It creates a Spring `ApplicationContext` focused on JPA-related components, making it possible to test entity mappings, Spring Data repositories, queries, and persistence behavior without booting the entire application.

A repository test typically only needs:

- Entities and relationship mappings.
- `EntityManager` and JPA infrastructure.
- Spring Data JPA repositories.
- A `DataSource` and transaction manager.
- Configurations required to create schemas and execute SQL.

`@DataJpaTest` auto-configures the components matching that scope. Web-layer components, controllers, services, and ordinary application beans are not automatically loaded as they are with `@SpringBootTest`.

This is the core difference between a slice test and a full application integration test:

| Criterion | @DataJpaTest | @SpringBootTest |
|---|---|---|
| ApplicationContext scope | Focused on persistence/JPA | Full application according to configuration |
| Repositories and EntityManager | Auto-configured | Present if the application configures them |
| Controllers, ordinary services | Not loaded automatically | Usually loaded |
| Startup speed | Usually faster | Usually slower |
| Goal | Verify mappings, repositories, queries, persistence | Verify multi-layer integration or complete application flows |
| Test transaction | Transactional by default and rolls back after test | Depends on test and transaction configuration |

Choose `@DataJpaTest` when the question to answer belongs to the data layer. If you need to test a controller calling a service and then a repository, security filters, HTTP serialization, or full application wiring, use `@SpringBootTest` or a more suitable test type.

## 2. What @DataJpaTest Auto-Configures

In a Spring Boot application with JPA, `@DataJpaTest` typically sets up the following components:

1. **Entity scanning:** discovers entity classes within the application's configured scope.
2. **JPA infrastructure:** configures `EntityManagerFactory` and required JPA components.
3. **Spring Data repositories:** detects and creates beans for matching repositories.
4. **DataSource:** creates or uses a `DataSource` according to test configuration.
5. **Transaction support:** configures a transaction manager so tests can run within transactions.
6. **TestEntityManager:** provides entity manipulation utilities for tests when appropriate JPA infrastructure is present.
7. **Database initialization/auto-configuration:** applies database and JPA configurations relevant to the test slice scope.

This annotation is built from multiple Spring Boot test configuration annotations. It restricts component scanning and auto-configuration to persistence concerns. Therefore, do not expect every bean present in the production application to appear in the test context.

### 2.1. Entities and Repositories Are Discovered

Suppose an application has a `Product` entity and a `ProductRepository`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private String sku;

    protected Product() {
    }

    public Product(String name, String sku) {
        this.name = name;
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getSku() {
        return sku;
    }
}
~~~

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class ProductRepositoryTest {
    @Autowired
    private ProductRepository products;

    @Test
    void findsProductBySku() {
        products.save(new Product("Keyboard", "KB-01"));

        var result = products.findBySku("KB-01");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getName()).isEqualTo("Keyboard");
    }
}
~~~

Spring Boot creates a JPA test context, injects the repository, and allows testing derived query methods. This example illustrates classes belonging to the same application; entities and repositories must reside within the test configuration's scan scope.

## 3. Transactions and Default Rollback

`@DataJpaTest` is configured so that each test method runs inside a transaction. By default, this transaction is rolled back when the test completes. Thus, data created in one test does not persist to affect subsequent tests.

Example:

~~~java
@DataJpaTest
class ProductRepositoryTest {
    @Autowired
    private ProductRepository products;

    @Test
    void savesProduct() {
        Product product = products.save(new Product("Mouse", "MS-01"));

        assertThat(product.getId()).isNotNull();
        assertThat(products.findBySku("MS-01")).isPresent();
    }
}
~~~

When the test completes, Spring Test rolls back the transaction. There is no need to manually delete data via the repository in every test just to clean up data created within that transaction.

A few notes:

- Rollback applies to the Spring-managed test transaction. If a test opens an independent transaction or operates outside that transaction, data may not be rolled back along with the test.
- If calling a service that uses `REQUIRES_NEW` propagation, the inner transaction can commit independently; understand transaction boundaries thoroughly before using it.
- `@Commit` or `@Rollback(false)` can alter the default behavior. Only use them when a test genuinely needs data to be committed.
- Rollback does not undo side effects outside the database, such as sending messages, making HTTP calls, or writing files. Slice tests typically do not load these components, but tests invoking them directly must manage cleanup themselves.

### 3.1. Flushing to Check Database Errors

`save()` might only place the entity into the persistence context. SQL might not be sent to the database immediately. If you want to ensure INSERT statements or constraints are checked during the test, flush explicitly:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductPersistenceTest {
    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private ProductRepository products;

    @Test
    void persistsAndReloadsProduct() {
        Product saved = entityManager.persistAndFlush(
                new Product("Monitor", "MN-01")
        );

        Long id = saved.getId();

        entityManager.clear();

        Product reloaded = products.findById(id).orElseThrow();

        assertThat(reloaded.getName()).isEqualTo("Monitor");
    }
}
~~~

`persistAndFlush()` persists the entity and forces SQL synchronization down to the database. `clear()` evicts managed entities from the persistence context. The subsequent `findById()` call must reload the entity, helping the test verify data was written to and read from the persistence layer rather than merely reading an object still sitting in the first-level cache.

Flush is not commit. The test transaction can still roll back when the method finishes.

## 4. Default Database and Keeping the Configured Database

An important feature of `@DataJpaTest` is its ability to use an embedded database for tests if an appropriate library is on the classpath. Test database configuration can replace the `DataSource` configured by the application. Default behavior and test database detection may vary by Spring Boot version.

This is convenient for fast repository tests, but can cause discrepancies if production uses PostgreSQL, MySQL, Oracle, or SQL Server. SQL dialects, data types, sequences, locking, constraints, and transaction behavior do not always match H2.

If you want to use the configured `DataSource`, declare it explicitly:

~~~java
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryIntegrationTest {
    // Tests use the configured DataSource.
}
~~~

`Replace.NONE` tells Spring Boot not to replace the `DataSource` with an embedded database. In that case, the test needs valid connection settings, an available database, and an appropriately prepared schema.

With Testcontainers, you can spin up a database container for integration tests and supply connection details via `DynamicPropertySource` or the `ServiceConnection` mechanism of your Spring Boot version. When keeping a container-provided `DataSource`, configure `replace = NONE` when needed to prevent test database auto-configuration from replacing it.

Do not assume that tests passing on H2 prove SQL statements or mappings are fully compatible with the production database.

## 5. Customizing Configuration Directly on @DataJpaTest

`@DataJpaTest` provides several attributes to adjust the slice's scope and behavior. Application configuration properties can be passed directly on the annotation:

~~~java
@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.properties.hibernate.format_sql=true"
})
class ProductRepositoryTest {
}
~~~

The `properties` attribute adds entries to the test context's `Environment` and can override corresponding configuration values. The example above instructs Hibernate to create the schema when the context starts and drop it under `create-drop` at the appropriate lifecycle end. Only use `ddl-auto=create-drop` when the test database is allowed to create and drop schemas.

Commonly used customizations:

| Property/Annotation | Purpose |
|---|---|
| `@DataJpaTest(properties = {...})` | Add or override properties for the test context |
| `@DataJpaTest(showSql = false)` | Disable SQL logging configured by the slice |
| `@DataJpaTest(excludeAutoConfiguration = {...})` | Exclude a specific auto-configuration from the slice |
| `@AutoConfigureTestDatabase(replace = NONE)` | Keep the configured `DataSource` instead of replacing with an embedded database |
| `@Import(...)` | Add configurations or beans needed for the test |
| `@TestPropertySource` | Load properties from a file or inline declarations |
| `@Sql` | Execute SQL scripts to prepare or verify data |
| `@ActiveProfiles("test")` | Select a configuration profile for tests |

Check the API for your exact Spring Boot version because properties and auto-configuration behaviors can change between versions.

### 5.1. showSql and Logging

`@DataJpaTest` typically logs SQL during tests per the annotation's default configuration. It can be disabled with:

~~~java
@DataJpaTest(showSql = false)
class ProductRepositoryTest {
}
~~~

Or configure logging to adjust Hibernate log levels. Displaying SQL helps read queries, but if you need to see bind parameter values, execution counts, or JDBC batching, configure the corresponding logger or observability tool. Do not enable detailed logging of sensitive data in production environments.

## 6. Slice Component Scanning Boundaries

`@DataJpaTest` focuses on entities and repositories. Regular beans such as `@Service`, `@Controller`, `@RestController`, or components outside the JPA scope are usually not brought into the context automatically by component scanning.

For example, suppose a repository requires a custom bean for auditing or a specialized converter/configuration. If that bean is not loaded by the slice, the test may fail with a missing dependency error or behave differently from production.

There are two common ways to intentionally add configuration:

**Approach 1: @Import the needed configuration**

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

@DataJpaTest
@Import(ProductJpaTestConfig.class)
class ProductRepositoryTest {
}
~~~

`ProductJpaTestConfig` is a project-specific configuration class containing the exact beans the test needs. This approach makes added slice dependencies explicit.

**Approach 2: @TestConfiguration**

~~~java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration
class ProductJpaTestConfig {
    @Bean
    ProductNameNormalizer productNameNormalizer() {
        return new ProductNameNormalizer();
    }
}
~~~

Then import the configuration into the test:

~~~java
@DataJpaTest
@Import(ProductJpaTestConfig.class)
class ProductRepositoryTest {
}
~~~

`@TestConfiguration` is intended for test-supporting beans. When placing a configuration nested inside a test class or in a separate class, ensure Spring Boot discovers/imports it as intended. Explicit imports are usually easier to read and less dependent on component scanning.

### 6.1. includeFilters and excludeFilters

If you truly need to adjust which component types are scanned in the slice, `@DataJpaTest` supports component scan filters such as `includeFilters`, `excludeFilters`, and `useDefaultFilters`.

Illustrative example:

~~~java
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest(
    includeFilters = @ComponentScan.Filter(
        type = FilterType.ASSIGNABLE_TYPE,
        classes = ProductNameNormalizer.class
    )
)
class ProductRepositoryTest {
}
~~~

Filters only apply within the component scanning scope performed by the slice. They are not a way to turn on the entire application context. For complex configurations or beans with heavy dependencies, `@Import`ing a specific test configuration is usually easier to control.

If a test needs a complete service along with all its dependencies, that may be a sign the test is stepping outside `@DataJpaTest`'s scope. Consider an integration test using `@SpringBootTest`.

## 7. Components Not to Expect by Default

Several common misconceptions often lead to errors when writing slice tests:

- **Service beans:** `@Service` beans are not automatically loaded as in a full context. If a repository test needs a service, you can import that specific bean, but consider whether the test is still focused on persistence.
- **Controllers and web infrastructure:** not the target of `@DataJpaTest`. Use `@WebMvcTest` or `@SpringBootTest` for web testing.
- **Security configuration:** do not assume the full security filter chain and authentication configuration are loaded. Tests requiring security integration must configure the proper slice or use an appropriate test type.
- **Messaging, schedulers, and external clients:** Kafka listeners, schedulers, HTTP clients, or external integration beans usually do not belong in the JPA slice.
- **Full application configuration:** only configurations/auto-configurations relevant to the slice are applied. If a custom configuration affects JPA, import it intentionally.

Do not mechanically switch to `@SpringBootTest` to fix every missing bean error. First determine which bean is genuinely needed for the persistence test goal and import only that configuration.

## 8. Using @DataJpaTest With Test Data

Data can be prepared using repositories, `TestEntityManager`, `@Sql`, or appropriate data initialization.

Example using `TestEntityManager`:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

@DataJpaTest
class ProductRepositoryQueryTest {
    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private ProductRepository products;

    @Test
    void findsOnlyProductsInRequestedCategory() {
        entityManager.persist(new Product("Book A", "BOOK-A"));
        entityManager.persist(new Product("Book B", "BOOK-B"));
        entityManager.persist(new Product("Pen", "PEN-01"));
        entityManager.flush();
        entityManager.clear();

        var books = products.findByCategory("BOOK");

        assertThat(books).hasSize(2);
        assertThat(books)
                .extracting(Product::getSku)
                .containsExactlyInAnyOrder("BOOK-A", "BOOK-B");
    }
}
~~~

This example assumes the `Product` entity has a `category` property and the repository declares `findByCategory(String category)`. The entity/repository definitions must match your project's actual model.

Using `flush` and `clear` helps the test observe data that has been synchronized to the database. If you only call `persist` and inspect in-memory collections, the test may fail to exercise the real query.

For static data shared across multiple tests, `@Sql` or schema/data initialization scripts can be used. Keep in mind that each test runs in a transaction and rolls back by default; which phase a script executes in and whether it participates in the transaction depend on `@Sql` execution phase and transaction mode settings.

## 9. Testing Transactions and Commit Behavior

Default rollback after tests keeps tests isolated and prevents data accumulation. However, it also means tests do not necessarily verify exact post-commit behavior.

If you need to test logic that depends on transaction commit, after-commit callbacks, constraints checked on commit, or data visibility from another transaction, design the test more explicitly. Depending on the case, you can use `TransactionTemplate`, `@Commit`, `@Rollback(false)`, or independent transactions.

Key points:

1. `@DataJpaTest` opens a transaction for each test method by default. Repository calls inside the test usually join this transaction.
2. A test method running in a single transaction does not simulate concurrent transactions simply by calling the repository multiple times.
3. To test visibility between two transactions, you need independent connections/transactions and controlled commit ordering.
4. If an inner transaction uses `REQUIRES_NEW`, it can commit even if the outer transaction rolls back; test the propagation properly.
5. Tests can use `@Transactional(propagation = NOT_SUPPORTED)` to run outside the default test transaction when necessary, but then you must manage test data cleanup yourself.

Do not disable rollback across the entire slice just to make tests pass. Identify what needs to be verified and establish the corresponding transaction boundaries.

## 10. When Is @DataJpaTest Not Enough?

`@DataJpaTest` is suitable for testing repositories, entity mappings, JPQL/native queries, converters, persistence auditing, constraints, and data-layer transactions. However, it does not test full application wiring.

Switch to `@SpringBootTest` when you need to confirm:

- A service is genuinely injected and calls repositories as part of a business flow.
- Multiple configuration layers coordinate properly inside a full `ApplicationContext`.
- Controllers, security, messaging, or integration beans participate in the use case.
- A transaction spans multiple services/repositories and the overall behavior needs testing.
- Real production configuration has multiple interacting auto-configurations that the slice does not load.

`@SpringBootTest` can be combined with `@AutoConfigureTestDatabase` or Testcontainers depending on the goal. Full integration tests usually take longer, so keep `@DataJpaTest` for narrowly scoped persistence tests and reserve full contexts for flows that truly need them.

## 11. Common Issues and Fixes

| Symptom | Common Cause | Resolution |
|---|---|---|
| Repository bean not found | Repository is outside the scan scope or slice configuration was altered | Check the main configuration package and repository scanning; import required configuration |
| Entity/table not found | Entity is not scanned or schema was not created | Check entity packages, `ddl-auto`, migrations, and SQL initialization |
| Test passes on H2 but fails in production | Differences in dialect, sequences, data types, constraints, or SQL | Run integration tests on the same database engine as production |
| Missing custom bean | Slice does not load ordinary `@Service`/`@Component` beans | Use `@Import` or `@TestConfiguration` for needed dependencies |
| Test data disappears after method | Default transaction rollback | This is expected behavior; use `@Commit` or a separate transaction if the goal requires commit |
| Test misses constraint violation | SQL has not been flushed or constraint is checked later | Call `flush` and verify when the database enforces constraints |
| Test context is too heavy | Importing too many configurations or accidentally pulling full application config | Keep the slice focused on JPA; import only necessary dependencies |
| Query test returns stale results | Persistence context or cache affects results | Flush/clear, control caching, and inspect actual SQL |

## 12. Process for Designing a Good @DataJpaTest

A practical workflow you can apply:

1. Identify the exact target under test: entity mapping, derived query, JPQL, native SQL, repository behavior, or constraints.
2. Use `@DataJpaTest` to build a minimal persistence slice.
3. Decide on the test database: embedded database for fast checks or a real database via Testcontainers to verify compatibility.
4. If keeping the configured `DataSource`, set `@AutoConfigureTestDatabase(replace = NONE)` explicitly.
5. Seed data via `TestEntityManager` or repositories, then `flush`/`clear` when verifying SQL.
6. Add custom beans with `@Import` or `@TestConfiguration`, strictly within what is actually required.
7. Rely on default rollback for test isolation; design independent transactions when testing commits or concurrency.
8. If you must load services/controllers and multiple application layers, move that test to `@SpringBootTest`.
9. Run tests against the exact target Spring Boot, Hibernate, and database versions before concluding the configuration is compatible.

`@DataJpaTest` keeps persistence-layer testing fast and clearly scoped. Customizing its scope properly requires understanding which beans are auto-configured, how the test database is chosen, default transaction rollback, and component scanning limits. When the slice is no longer sufficient to represent the flow under test, use a full integration test rather than turning the slice into an unmanageable `ApplicationContext`.
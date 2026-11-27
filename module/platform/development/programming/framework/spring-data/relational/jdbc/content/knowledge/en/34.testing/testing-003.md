# Configuring @DataJdbcTest and Loaded Bean Scope

In Spring Data Relational JDBC, **`@DataJdbcTest`** is a test slice dedicated to repositories and JDBC mapping. It initializes the infrastructure needed for Data JDBC, restricts the scope of scanned beans, and by default runs each test inside a transaction that rolls back after the test finishes.

The crucial point is that `@DataJdbcTest` does not load the entire application context. Repositories and entities are discovered according to Data JDBC rules; regular services, controllers, components, and application configurations may not be present. When a test needs a bean outside the slice, bring it in explicitly with `@Import`, `@TestConfiguration`, or `@EnableConfigurationProperties`.

This lesson covers which beans are loaded, how to add configuration, database selection, default transactions, and the differences between `@DataJdbcTest`, `@JdbcTest`, and `@SpringBootTest`.

## 1. What Is @DataJdbcTest?

`@DataJdbcTest` enables only auto-configuration relevant to testing Spring Data JDBC. In a typical setup, it provides:

- A `DataSource` for testing.
- `JdbcTemplate` and required JDBC components.
- Spring Data JDBC repositories.
- Mapping infrastructure for entities and aggregates.
- Transaction management for tests.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @Test
    void savesAndLoadsProduct() {
        Product product = new Product(null, "SKU-01", "Notebook");

        Product saved = products.save(product);

        assertThat(saved.getId()).isNotNull();
        assertThat(products.findById(saved.getId()))
                .get()
                .extracting(Product::getName)
                .isEqualTo("Notebook");
    }
}
~~~

The example assumes the entity and repository are already declared. The goal is to test that the repository works with the database and mapping inside the test slice.

### 1.1. Test Slice Scope

`@DataJdbcTest` is suitable for testing:

- Repository CRUD.
- Derived queries and query methods.
- Entity, value object, and aggregate child mapping.
- Custom converters and naming strategies.
- Constraints, generated IDs, and JDBC behavior.

By default, it does not test full service orchestration, the HTTP layer, security filters, or message brokers. For cross-layer use cases, consider `@SpringBootTest`.

### 1.2. JUnit 5

`@DataJdbcTest` already integrates the Spring Test extension. With JUnit 5, manually adding `@ExtendWith(SpringExtension.class)` is normally unnecessary.

## 2. Beans That Are Loaded vs. Not Loaded

### 2.1. Components That Are Discovered

Spring Boot restricts the component scanning of the Data JDBC test slice to relevant persistence components, primarily including:

- Spring Data JDBC repositories.
- Entities annotated with `@Table`.
- Beans extending `AbstractJdbcConfiguration`.
- Auto-configurations related to Data JDBC testing.

Entity:

~~~java
@Table("product")
public class Product {

    @Id
    private Long id;

    private String sku;
    private String name;
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends CrudRepository<Product, Long> {
}
~~~

Entities and repositories are discovered if they reside within the appropriate application scan scope.

### 2.2. Regular Beans Not Automatically Loaded

The following application beans are usually not scanned in `@DataJdbcTest`:

- `@Service`.
- `@Component`.
- `@Controller` or `@RestController`.
- Regular `@Configuration` classes not part of permitted JDBC configurations.
- `@ConfigurationProperties` beans unless explicitly enabled.

For example, the following service is not automatically available just because it resides in the same package as the repository:

~~~java
@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }
}
~~~

This restriction prevents repository tests from accidentally depending on HTTP clients, brokers, schedulers, or components unrelated to persistence.

## 3. Adding Beans with @Import

When a test needs a specific service or configuration, use `@Import`:

~~~java
@DataJdbcTest
@Import(ProductService.class)
class ProductServiceJdbcTest {

    @Autowired
    ProductService productService;

    @Autowired
    ProductRepository products;

    @Test
    void createsProductThroughService() {
        productService.create("SKU-02", "Pen");

        assertThat(products.findBySku("SKU-02")).isPresent();
    }
}
~~~

`@Import(ProductService.class)` brings the service into the test context. The service's dependencies must still exist in the context. If the service requires a gateway, clock, or policy, import an appropriate real bean or declare a test bean.

Multiple beans can be imported:

~~~java
@DataJdbcTest
@Import({
        ProductService.class,
        ProductPolicy.class,
        ProductJdbcConfiguration.class
})
class ProductServiceJdbcTest {
}
~~~

Import only the beans the test needs. Importing a large application configuration can pull in many dependencies and defeat the purpose of the slice.

## 4. Using @TestConfiguration for Test-Only Beans

`@TestConfiguration` lets you declare additional beans exclusively for tests:

~~~java
@DataJdbcTest
@Import(ProductRepositoryTest.TestConfig.class)
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @TestConfiguration(proxyBeanMethods = false)
    static class TestConfig {

        @Bean
        ProductNamePolicy productNamePolicy() {
            return new ProductNamePolicy(100);
        }
    }
}
~~~

This example creates a policy used only in tests. `proxyBeanMethods = false` is suitable when `@Bean` methods do not call each other through proxies.

If a test bean needs a repository or `JdbcTemplate`, inject them as `@Bean` method parameters. Do not create a second datasource manually if the test only needs the infrastructure provided by `@DataJdbcTest`.

## 5. Adding @ConfigurationProperties

`@ConfigurationProperties` beans are not registered automatically just because the class exists. They can be enabled explicitly with `@EnableConfigurationProperties`:

~~~java
@DataJdbcTest
@EnableConfigurationProperties(DatabaseOptions.class)
class ProductRepositoryTest {
}
~~~

Example properties:

~~~java
@ConfigurationProperties(prefix = "app.database")
public record DatabaseOptions(
        int batchSize,
        boolean auditEnabled
) {
}
~~~

Test-specific values can be provided:

~~~java
@DataJdbcTest(properties = {
        "app.database.batch-size=50",
        "app.database.audit-enabled=false"
})
@EnableConfigurationProperties(DatabaseOptions.class)
class ProductRepositoryTest {
}
~~~

## 6. AbstractJdbcConfiguration and Custom Mapping

An application can customize Spring Data JDBC with a class extending `AbstractJdbcConfiguration`. This configuration can register custom conversions, naming strategies, and relevant mapping components.

Skeleton example:

~~~java
@Configuration
public class JdbcMappingConfiguration
        extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new MoneyToBigDecimalConverter(),
                new BigDecimalToMoneyConverter()
        );
    }
}
~~~

Converter configuration method names and signatures depend on the Spring Data Relational version; use the API from your project's dependency. If the configuration is not discovered in tests, import it explicitly:

~~~java
@DataJdbcTest
@Import(JdbcMappingConfiguration.class)
class ProductMappingTest {
}
~~~

If production uses custom converters for Money, enums, or value objects, persistence tests need to load the same mapping configuration so results accurately reflect production.

## 7. Default Database and DataSource Replacement

By default, `@DataJdbcTest` uses an in-memory embedded database if one is on the classpath. It may replace the application's datasource with a test database.

Example adding H2 for tests:

~~~groovy
dependencies {
    testRuntimeOnly("com.h2database:h2")
}
~~~

Embedded databases are useful for CRUD, simple mapping, and portable queries. However, they do not guarantee identical behavior to PostgreSQL, MySQL, SQL Server, or Oracle in all scenarios. SQL dialects, data types, functions, collations, locking, and DDL may differ.

### 7.1. Keeping the Application DataSource

If you want tests to use the configured datasource, you can declare:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {
}
~~~

`Replace.NONE` tells Spring not to replace the application's default datasource. This is an explicit choice when tests connect to a Testcontainers database or a dedicated test database.

### 7.2. Replace Modes

| Value | Meaning |
| --- | --- |
| `ANY` | Replace the datasource whether auto-configured or manually declared |
| `AUTO_CONFIGURED` | Only replace an auto-configured datasource |
| `NON_TEST` | Replace the datasource unless an auto-configured datasource is recognized as a test database |
| `NONE` | Do not replace the application datasource |

Defaults and test-datasource detection vary by Spring Boot version. In newer versions, Testcontainers datasources via `@ServiceConnection` or `@DynamicPropertySource` may be recognized as test databases. When you want to retain the datasource explicitly, use `Replace.NONE`.

## 8. Using Testcontainers for the Production Database

If production uses PostgreSQL, testing against PostgreSQL via Testcontainers helps catch dialect differences that H2 might miss.

~~~java
@DataJdbcTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
class ProductRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @Autowired
    ProductRepository products;

    @Test
    void savesProductUsingPostgres() {
        Product saved = products.save(
                new Product(null, "SKU-PG-01", "Notebook")
        );

        assertThat(products.findById(saved.getId())).isPresent();
    }
}
~~~

This example uses Spring Boot 3.1+ with `@ServiceConnection` support. You must declare the Testcontainers JUnit Jupiter dependency, PostgreSQL module, and Spring Boot Testcontainers module. Choose an image version matching the production database.

### 8.1. Using @DynamicPropertySource

If not using `@ServiceConnection`, you can register the URL, username, and password:

~~~java
@DynamicPropertySource
static void configureDatabase(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

The container must be ready before the datasource is created. Use `Replace.NONE` if you want to make explicit that the test keeps the container datasource.

### 8.2. When Is the Target Database Needed?

Use the production database or Testcontainers when tests depend on:

- Vendor-specific SQL syntax such as JSON operators, arrays, CTEs, or vendor functions.
- Specialized data types.
- Collation and case sensitivity.
- Locking/isolation semantics.
- Generated keys, sequences, and identity behavior.
- Migration DDL or specialized indexing strategies.

H2 remains useful for fast tests, but it is not proof that queries will run properly on the production database.

## 9. Default Transaction and Rollback

`@DataJdbcTest` is marked transactional. Each test method typically runs in its own transaction, and Spring rolls back the transaction after the test completes.

~~~java
@DataJdbcTest
class ProductRepositoryTest {

    @Autowired
    ProductRepository products;

    @Test
    void insertsProduct() {
        products.save(new Product(null, "SKU-01", "Notebook"));

        assertThat(products.count()).isEqualTo(1);
    }
}
~~~

After the test, the data is rolled back so subsequent tests are unaffected by the inserted row.

### 9.1. Testing Real Service Transactions

A test method running inside a transaction can cause repository operations to join the test's transaction. This sometimes prevents the test from observing the service's commit boundary.

If you need to test post-commit behavior, AFTER_COMMIT listeners, or transaction propagation, you can disable the test's outer transaction:

~~~java
@DataJdbcTest
@Import(OrderApplicationService.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class OrderApplicationServiceTransactionTest {
}
~~~

When the test has no outer transaction, a `@Transactional` service method opens its own transaction and commits/rolls back via proxy. You will need to prepare and clean up data appropriately for that test.

Another option is using `TestTransaction` or `@Commit` when you want to actively commit the test transaction. Use this only when the test objective genuinely requires a commit.

### 9.2. Do Not Disable Rollback for All Tests

Do not add `@Transactional(propagation = NOT_SUPPORTED)` to the entire test suite just because one test needs a commit. Regular tests should retain default rollback to stay independent and repeatable.

## 10. Migrations and Schema in @DataJdbcTest

Repositories only work if the schema is ready. A test schema can be created in one of these ways:

- Flyway migrations.
- Liquibase changelogs.
- Test-specific SQL initialization scripts.
- Schema pre-created by test infrastructure.

If the application uses Flyway or Liquibase, verify that migration auto-configuration is enabled in the test slice and runs before repository tests. Do not create the same table with both migrations and a standalone schema script, because the two schema sources can drift.

### 10.1. Testing the Migration Chain

Testing repositories against an empty database confirms that migrations create the schema. However, you still need to test upgrading from older schema versions if a migration performs backfills or alters column types.

For critical migrations:

1. Create a clean Testcontainers database.
2. Run migrations up to the old version.
3. Insert representative legacy data.
4. Run the new migration.
5. Verify schema, constraints, and migrated data.
6. Initialize repositories and confirm mapping works.

### 10.2. A Test Slice Is Not Always a Full Migration Test

`@DataJdbcTest` focuses on Data JDBC components. If migrations depend on custom application configuration or initialization ordering, verify that the test context actually runs migrations. When you need to test the full-application deployment flow, use a dedicated integration test with `@SpringBootTest`.

## 11. Adding Scan Filters Only When Truly Needed

`@DataJdbcTest` provides `includeFilters` and `excludeFilters` attributes to customize component scanning. This is an advanced option when you need to add specific bean types to the scan scope.

~~~java
@DataJdbcTest(
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = ProductService.class
        )
)
class ProductServiceTest {
}
~~~

In most slice tests, `@Import(ProductService.class)` or `@TestConfiguration` is easier to read and control. Use filters when you want to adjust scanning rules systematically.

### 11.1. Do Not Component-Scan the Whole Application

Adding `@ComponentScan("com.example")` can pull a huge number of beans into the context and defeat the purpose of the slice. If a test needs the entire application, use `@SpringBootTest` to state the intent clearly.

## 12. Comparing @DataJdbcTest, @JdbcTest, and @SpringBootTest

| Annotation | Scope | When to Use |
| --- | --- | --- |
| `@DataJdbcTest` | Spring Data JDBC repositories, entity mapping, and related JDBC infrastructure | Testing repositories, aggregate mapping, queries, and persistence |
| `@JdbcTest` | DataSource, JdbcTemplate, and basic JDBC infrastructure; does not focus on Spring Data JDBC repositories | Testing direct SQL/JdbcTemplate |
| `@SpringBootTest` | Entire application context according to application configuration | Testing service orchestration, multi-layer integration, full wiring |

### 12.1. @JdbcTest

`@JdbcTest` is suitable if code uses `JdbcTemplate` or `NamedParameterJdbcTemplate` directly and does not need Spring Data JDBC repositories.

~~~java
@JdbcTest
class ProductSqlRepositoryTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void countsRows() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM product",
                Integer.class
        );

        assertThat(count).isZero();
    }
}
~~~

### 12.2. @SpringBootTest

`@SpringBootTest` loads the full application configuration:

~~~java
@SpringBootTest
class ProductApplicationIntegrationTest {

    @Autowired
    ProductService productService;

    @Test
    void createsProductThroughApplicationFlow() {
        // test service, repository, and related dependencies
    }
}
~~~

This test may require more dependencies and take longer to run. In return, it verifies real wiring of the application context.

### 12.3. Choosing an Annotation by Goal

- Want to test entities, repositories, and SQL mapping: choose `@DataJdbcTest`.
- Want to test a JDBC class using a template directly: choose `@JdbcTest`.
- Want to test multiple layers and full configuration: choose `@SpringBootTest`.

Do not use `@SpringBootTest` for every repository test when a slice suffices. Conversely, do not force `@DataJdbcTest` to test the entire service graph.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| ProductService bean not found | Service is outside the slice's component scan | Use `@Import` or `@TestConfiguration` |
| Repository is not created | Entity/repository outside scan scope or missing auto-configuration | Check packages, `@Table`, and repository setup |
| Custom converter missing | JDBC configuration not imported/discovered | Import the `AbstractJdbcConfiguration` subclass |
| Properties fail to bind | `@ConfigurationProperties` not enabled | Use `@EnableConfigurationProperties` |
| Test runs on H2 instead of PostgreSQL | Test database replacement replaced datasource | Use Testcontainers and `Replace.NONE` |
| SQL runs on H2 but fails in production | Dialect or data type differences | Test against the target database |
| Test data persists between tests | Transaction rollback disabled or test committed | Check propagation, `@Commit`, and cleanup |
| Unable to observe AFTER_COMMIT | Outer test transaction has not committed | Use `NOT_SUPPORTED` or control `TestTransaction` |
| Flyway/Liquibase does not run | Auto-configuration disabled or missing dependency | Check dependencies, properties, and test auto-config |
| Too many beans loaded | Broad component scan used | Keep the slice narrow and import only needed beans |
| Test cannot find application configuration | Test placed outside Boot's scan package | Place test in the right package or specify test configuration |

## 14. Workflow for Configuring a Data JDBC Test

When creating a repository test:

1. **Identify the goal:** test only the repository, or are services/use cases needed?
2. **Use `@DataJdbcTest`:** to load the Data JDBC slice and repositories.
3. **Check entity scanning:** entities need appropriate mapping annotations like `@Table`.
4. **Add beans intentionally:** use `@Import`, `@TestConfiguration`, or `@EnableConfigurationProperties`.
5. **Choose the database:** embedded for fast tests, Testcontainers for production dialect.
6. **Control datasource replacement:** use `@AutoConfigureTestDatabase` if keeping a configured datasource.
7. **Prepare the schema:** confirm Flyway/Liquibase or SQL initialization runs properly.
8. **Keep default rollback:** only disable transactions for tests that need to observe real commits.
9. **Verify mapping and aggregates:** test root, children, generated IDs, custom conversions, and constraints.
10. **Move to full context when needed:** use `@SpringBootTest` for wiring and multi-layer integration.

## Key Takeaways

`@DataJdbcTest` is a test slice focused on Spring Data JDBC. It configures database infrastructure for tests, discovers repositories and `@Table` entities, and by default runs tests inside a transaction rolled back after each method. Bean scope is restricted: regular services, components, controllers, and configuration properties are not automatically loaded. Use `@Import` or `@TestConfiguration` to add needed beans; use `@EnableConfigurationProperties` for properties beans, and import configurations extending `AbstractJdbcConfiguration` when custom mappings are needed.

By default, tests typically use an embedded database if present on the classpath. When verifying exact production dialect behavior is required, use Testcontainers and configure `@AutoConfigureTestDatabase(replace = Replace.NONE)` to keep the container datasource. Keep default rollback for normal repository tests; only disable the outer transaction when verifying commits, rollbacks, or post-commit events. Choose `@JdbcTest` for JDBC code using templates directly, and `@SpringBootTest` when the full application context is needed.

## References

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [DataJdbcTest API — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/data/jdbc/DataJdbcTest.html)
- [AutoConfigureTestDatabase API — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html)
- [AutoConfigureTestDatabase.Replace API — Spring Boot 3.5](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html)

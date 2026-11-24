# @SpringJUnitConfig and Concise Configuration

The Spring TestContext Framework provides mechanisms to load and manage the ApplicationContext for tests. When using JUnit Jupiter, a test may need Spring to create beans, inject dependencies into the test class, manage the context lifecycle, and enable testing capabilities such as transactions. If every test had to declare the JUnit extension and context configuration separately, setup would become verbose and repetitive.

**@SpringJUnitConfig** is an annotation that combines two commonly used components: **@ExtendWith(SpringExtension.class)** to integrate Spring TestContext with JUnit Jupiter and **@ContextConfiguration** to specify the configuration used to create the ApplicationContext. As a result, a test can declare its Spring configuration with a single concise annotation.

This lesson focuses on how to use **@SpringJUnitConfig**, how to organize concise configuration using Java or XML, how to select beans to load for tests, and key considerations regarding the context cache, dependency injection, and supporting annotations.

## 1. What Is @SpringJUnitConfig?

In JUnit Jupiter, Spring needs an extension to connect the test lifecycle with the TestContext Framework. This extension is **SpringExtension**. Context configuration is typically declared with **@ContextConfiguration**.

Written explicitly, a test class might look like this:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = OrderTestConfig.class)
class OrderServiceTest {
    // Test methods
}
~~~

When using **@SpringJUnitConfig**, the two annotations above are combined:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {
    // Test methods
}
~~~

Both declarations express the same intent: SpringExtension participates in JUnit Jupiter and Spring TestContext loads the specified configuration to create the ApplicationContext.

**@SpringJUnitConfig** is a composed annotation provided in the package:

~~~java
org.springframework.test.context.junit.jupiter.SpringJUnitConfig
~~~

Related annotations reside in the following packages:

- **SpringJUnitConfig** and **SpringExtension** belong to the JUnit Jupiter package of Spring TestContext.
- **ContextConfiguration** belongs to the Spring TestContext package.
- **Configuration**, **Bean**, **Import**, and **ComponentScan** belong to Spring Framework Core/Context.

### Roles of the Two Combined Components

| Component | Responsibility |
|---|---|
| SpringExtension | Connects JUnit Jupiter with Spring TestContext, participates in callbacks, and supports test injection |
| ContextConfiguration | Declares configuration sources to create the ApplicationContext |
| SpringJUnitConfig | Combines the two components above in a single annotation |

SpringExtension is not a Spring bean and does not replace the ApplicationContext. It acts as the bridge between JUnit and Spring's testing mechanism.

## 2. Minimal Java Configuration

The most common approach is creating a configuration class with **@Configuration** and declaring the beans that the test needs.

Suppose the application has a service receiving a repository and a clock via constructor:

~~~java
public class OrderService {

    private final OrderRepository repository;
    private final Clock clock;

    public OrderService(OrderRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public Order create(String customerId) {
        var order = new Order(customerId, clock.instant());
        repository.save(order);
        return order;
    }
}
~~~

The test does not need to load the entire application. We can declare a small configuration:

~~~java
@Configuration
class OrderTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-04-12T10:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock testClock) {
        return new OrderService(repository, testClock);
    }
}
~~~

This configuration creates three beans:

- An in-memory repository so the test does not need a database.
- A fixed clock so time-dependent results are predictable.
- OrderService using the two beans above via constructor injection.

The test class only needs to declare:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceSpringTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrderWithConfiguredClock() {
        Order order = orderService.create("customer-18");

        assertEquals("customer-18", order.customerId());
        assertEquals(
                Instant.parse("2026-04-12T10:00:00Z"),
                order.createdAt()
        );
    }
}
~~~

When the test runs, Spring creates the ApplicationContext from OrderTestConfig, instantiates the beans, and injects OrderService into the field marked **@Autowired**.

This example still uses the real implementation of OrderService. The repository is an in-memory fake and the Clock is a real object configured with a fixed instant. The test verifies bean creation, constructor injection, and service behavior within a Spring context.

## 3. Declaring Configuration Classes in Multiple Ways

**@SpringJUnitConfig** supports the configuration sources provided by **@ContextConfiguration**. Which source to choose depends on the application type and available configuration.

### Passing Configuration Classes Directly

You can pass a configuration class as the value argument:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {
}
~~~

This is the concise form when there is only one or a few configuration classes.

### Using the classes Attribute

If you want to express the attribute explicitly, you can write:

~~~java
@SpringJUnitConfig(classes = {
        OrderTestConfig.class,
        AuditTestConfig.class
})
class OrderServiceTest {
}
~~~

Multiple configuration classes can be loaded at once. Spring processes bean definitions from these configuration sources within the same context, following the container's bean registration rules.

### Using XML Configuration

For applications still using XML, you can declare resource locations:

~~~java
@SpringJUnitConfig(locations = "classpath:order-test-context.xml")
class OrderServiceXmlTest {
}
~~~

XML example:

~~~xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="orderRepository"
          class="example.testing.InMemoryOrderRepository"/>

    <bean id="orderService"
          class="example.order.OrderService">
        <constructor-arg ref="orderRepository"/>
    </bean>
</beans>
~~~

The classpath path must point to a resource present on the test runtime classpath. If the XML file is in the test resources directory, the build tool must include that directory on the classpath when running tests.

### Combining Java and XML

An application gradually migrating from XML to Java configuration can load both sources:

~~~java
@SpringJUnitConfig(
        locations = "classpath:legacy-order-context.xml",
        classes = OrderTestConfig.class
)
class OrderMigrationTest {
}
~~~

Combine them only when both configuration sources are genuinely needed. Multiple configuration sources can make bean lookup and bean name conflict resolution harder to follow.

## 4. Using Nested Configuration Inside the Test Class

For tests needing only a small configuration, you can declare a static nested class annotated with **@Configuration** directly inside the test class.

~~~java
@SpringJUnitConfig
class TaxServiceTest {

    @Autowired
    private TaxService taxService;

    @Configuration
    static class TestConfig {

        @Bean
        TaxService taxService() {
            return new TaxService(new BigDecimal("0.10"));
        }
    }

    @Test
    void calculatesTaxForKnownRate() {
        BigDecimal tax = taxService.calculate(new BigDecimal("100000"));

        assertEquals(
                0,
                tax.compareTo(new BigDecimal("10000"))
        );
    }
}
~~~

When no configuration class or resource is specified, Spring TestContext can locate a static nested class annotated with **@Configuration** to use as the default configuration.

This approach has several benefits:

- Configuration used only by one test sits right next to that test.
- No need to create an extra configuration file when the setup is tiny.
- Readers easily spot special beans tailored for the test scenario.

If multiple tests need to share the configuration, move the configuration to a separate class. Nested configuration must also be `static` so Spring can instantiate it independently of the test class instance.

## 5. Concise Configuration Using @Import

It is not always necessary to redeclare every production bean. If the application already has suitable configuration classes or components, the test can import them into a small configuration.

~~~java
@Configuration
@Import(OrderService.class)
class OrderServiceTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-04-12T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

**@Import** brings the specified class into the context configuration process. In the example, OrderService is registered as a component bean and its constructor dependencies are resolved from beans in the context.

If the project has a production configuration class:

~~~java
@Configuration
class OrderModuleConfig {

    @Bean
    OrderService orderService(
            OrderRepository repository,
            Clock clock) {
        return new OrderService(repository, clock);
    }
}
~~~

The test can import this configuration:

~~~java
@Configuration
@Import(OrderModuleConfig.class)
class OrderModuleTestConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}

@SpringJUnitConfig(OrderModuleTestConfig.class)
class OrderModuleTest {

    @Autowired
    private OrderService orderService;
}
~~~

OrderModuleTestConfig imports the production configuration and supplies the beans required by OrderModuleConfig, such as OrderRepository and Clock. Consequently, the test can use the module's wiring while swapping the repository for an implementation suited to the testing environment.

**@Import** selects a specific set of configurations. It does not automatically enable component scanning for the entire package. If you want to discover components by package, declare **@ComponentScan** on the configuration class.

## 6. When to Use @ComponentScan?

**@ComponentScan** instructs Spring to scan packages to find components annotated with **@Component**, **@Service**, **@Repository**, or **@Controller**.

Example:

~~~java
@Configuration
@ComponentScan(basePackageClasses = OrderService.class)
class OrderComponentTestConfig {
}
~~~

Using a marker class such as OrderService.class avoids hard-coding package names as strings and reduces the risk of renaming a package while forgetting to update configuration.

However, scanning an entire package can bring more beans into the context than the test needs. Those beans may pull in databases, HTTP clients, message brokers, or security configuration. When the goal is testing a service, explicit configuration with **@Import** or **@Bean** methods is usually easier to control.

Choose a small enough scan scope. If you need to exclude or include a group of components, configure component scan filters. Do not use component scanning as the default for every test merely because it takes fewer lines of configuration.

## 7. How Does Spring Inject Dependencies into the Test Class?

When **SpringExtension** manages a test, Spring TestContext can perform dependency injection on the test instance. This allows tests to receive beans via fields or setters marked **@Autowired**.

Example using field injection:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private OrderRepository repository;

    @Test
    void createsOrder() {
        Order order = orderService.create("customer-18");

        assertNotNull(order);
        assertTrue(repository.findById(order.id()).isPresent());
    }
}
~~~

Constructor injection can be used for a test class if the JUnit Jupiter and Spring TestContext configuration permits constructor autowiring. An explicit declaration is:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderServiceConstructorTest {

    private final OrderService orderService;

    OrderServiceConstructorTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void createsOrder() {
        assertNotNull(orderService);
    }
}
~~~

With constructor injection, all constructor parameters are resolved by Spring from the ApplicationContext when autowire mode is enabled. Ensure the project's Spring TestContext version and JUnit Jupiter configuration support this usage.

Do not confuse injection into the test instance with injection between production beans. **@Autowired** on a test field is handled by Spring TestContext; meanwhile, constructor injection of OrderService is performed by the Spring container when creating the bean.

## 8. SpringExtension and the JUnit Jupiter Lifecycle

SpringExtension connects the TestContext Framework to JUnit Jupiter callbacks. Thanks to this, Spring can prepare the test instance, inject dependencies, and carry out testing actions according to TestContext configuration.

Some notable capabilities:

- Preparing and injecting beans into the test instance.
- Managing the context through the TestContext Framework.
- Integrating default TestExecutionListeners to support features such as test transactions when configured.
- Enabling Spring Test annotations such as **@DirtiesContext**, **@ActiveProfiles**, **@TestPropertySource**, and **@Transactional** within their respective scopes.

For example, if a test needs a Spring-managed transaction:

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class OrderTransactionTest {

    @Autowired
    private OrderRepository repository;

    @Test
    void savesOrderInsideTestTransaction() {
        repository.save(new OrderEntity("order-25", "customer-9"));

        assertTrue(repository.findById("order-25").isPresent());
    }
}
~~~

When a suitable transaction manager is present and the test runs with Spring TestContext transaction support, the test-managed transaction is normally rolled back after each test method. This isolates data changes across many persistence tests.

Do not assume by default that all side effects are rolled back. Messages sent to a broker, HTTP requests sent to external services, operations on another thread, or independent transactions may persist after the test. Clearly identify transaction boundaries and data cleanup strategies for each dependency.

## 9. Configuring Profiles and Properties for Tests

A context may require different profiles or properties than the running application environment.

### Using @ActiveProfiles

**@ActiveProfiles** activates one or more profiles when Spring creates the context for the test:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@ActiveProfiles("test")
class OrderProfileTest {
}
~~~

Beans declared with **@Profile("test")** can be registered when the corresponding profile is active.

### Using @TestPropertySource

**@TestPropertySource** adds a property source for the test environment:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(properties = {
        "orders.currency=VND",
        "orders.shipping.enabled=true"
})
class OrderPropertiesTest {
}
~~~

These properties can be read via **Environment**, **@Value**, or appropriate configuration mechanisms inside beans.

If using a dedicated property file, you can specify `locations`:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestPropertySource(locations = "classpath:order-test.properties")
class OrderPropertiesFileTest {
}
~~~

Use test properties to make intentional differences explicit, such as mock endpoints, feature flags, or timeout configurations. Do not place secrets or production credentials into test resources.

### Using @DynamicPropertySource When Values Are Only Known at Runtime

For dynamically launched resources such as database containers, **@DynamicPropertySource** allows registering properties from values only known while the test runs.

~~~java
@SpringJUnitConfig(DatabaseTestConfig.class)
class DatabaseContextTest {

    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    static {
        postgres.start();
    }

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

This example illustrates registering dynamic properties; a real project needs the Testcontainers dependency, PostgreSQL JDBC driver, and proper container lifecycle management. With containers, ensure the container is stopped after tests finish or use lifecycle management provided by the library.

## 10. Spring TestContext Cache and Consistent Configuration

Creating an ApplicationContext can be time-consuming because Spring must read configuration, register beans, perform component scanning, instantiate objects, and run initialization steps. Spring TestContext includes a context cache so tests with compatible configurations can reuse an already created context.

For example, multiple tests declare the same configuration:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderServiceTest {
}

@SpringJUnitConfig(OrderTestConfig.class)
class OrderRepositoryCollaboratorTest {
}
~~~

If the context configuration attributes are compatible, Spring can reuse the already created context. This reduces startup overhead across test classes.

Configuration factors such as classes or resources, initializers, active profiles, property sources, and customizers can affect the cache key. If each test creates a different configuration variant, reusability drops.

### Avoiding Dirtying the Context

Spring singleton beans are shared within an ApplicationContext. If a test modifies mutable state inside a singleton and does not restore it, other tests sharing the same context may observe leftover state.

Some ways to mitigate this:

- Keep shared beans stateless whenever possible.
- Create isolated test data per method.
- Reset the state of fakes or collaborators after the test if needed.
- Avoid directly altering the context's configuration or registry during a test.
- Use **@DirtiesContext** only when a test genuinely alters context state and requires removing that context from the cache.

**@DirtiesContext** causes Spring to close the current context and recreate it the next time it is needed. Using this annotation too frequently will slow down the test suite significantly. It is not a general-purpose database cleanup mechanism and does not automatically undo side effects outside the context.

## 11. Choosing Concise Configuration or Loading the Full Application?

**@SpringJUnitConfig** lets you specify only the required Spring configuration. This is an important difference compared to always loading the entire application.

| Approach | Scope | Suitable When |
|---|---|---|
| @SpringJUnitConfig with small config | A selected group of beans | Verifying module wiring and behavior |
| @SpringJUnitConfig with component scan | Components in scanned packages | Packages have clear boundaries and many real components are needed |
| @SpringJUnitConfig with XML config | Beans from XML resources | Application or module still uses XML |
| @SpringBootTest | Broader Spring Boot application config | Need to verify Boot application bootstrapping and integration |
| @WebMvcTest or @DataJpaTest | Spring Boot test slices | Testing a web or persistence slice |

**@SpringJUnitConfig** belongs to the Spring TestContext Framework. It does not automatically enable Spring Boot auto-configuration, does not automatically run component scanning across the whole application, and does not automatically create a Spring Boot web environment.

If a test requires Spring Boot-specific bootstrap behavior such as auto-configuration, application properties binding, or components auto-registered by Boot, consider **@SpringBootTest** or an appropriate slice annotation. You can use a Boot application's Java configuration in Spring TestContext, yet loading a single configuration class is not equivalent to Boot's full bootstrap process.

### Scope Selection Examples

- Testing constructor injection and a single service: small configuration with **@SpringJUnitConfig**.
- Testing controller mapping and validation in a Boot application: **@WebMvcTest** is usually more suitable.
- Testing a repository with Boot's JPA configuration: **@DataJpaTest** can provide an appropriate slice.
- Testing multiple modules, auto-configuration, and deployment configuration: consider **@SpringBootTest**.

Choose scope based on what needs to be proven. Loading more beans does not automatically make a test better; it increases startup time and the number of reasons a test can fail.

## 12. Common Configuration Errors

### Missing Bean Required for Injection

If a test requests **@Autowired OrderService** but the context has no matching bean, Spring will fail when creating the test instance or initializing the context.

The fix is registering the bean with **@Bean**, importing the appropriate class with **@Import**, or configuring properly scoped component scanning. Do not add whole-application scanning just to mask a single missing bean.

### Overly Broad Component Scan

A small service test can inadvertently load a database, HTTP client, or broker due to scanning an entire package. Use explicit configuration or restrict scanning via marker packages and filters.

### Confusing @SpringJUnitConfig with @SpringBootTest

**@SpringJUnitConfig** does not automatically run Spring Boot auto-configuration. If a test relies on a datasource, configuration properties, or auto-configured clients created by Boot, use appropriate Boot configuration or explicitly declare the required beans.

### Declaring SpringExtension Twice

**@SpringJUnitConfig** already includes **@ExtendWith(SpringExtension.class)**. There is no need to repeat the extension annotation on the same test class without a special reason.

### Using Incompatible Configurations Across Tests

Tests using different profiles, property sources, or bean overrides can produce multiple context cache entries. Share configuration when tests genuinely have the same requirements and create variants only when needed.

### Letting Singleton State Persist Across Tests

A mutable bean or shared fake in the context can retain data from an earlier test. Isolate data, reset state intentionally, or create a separate context when necessary.

### Using @DirtiesContext as a Catch-All Cleanup

This annotation manages the ApplicationContext lifecycle. It does not replace transaction rollback, deleting database data, stopping containers, or recalling externally sent requests.

## 13. Process for Creating a Test Class with @SpringJUnitConfig

When starting a new test, you can follow this sequence:

1. Identify the class or module to test and the beans actually required.
2. Choose Java configuration, XML, or nested configuration.
3. Register the production beans under test and replace external dependencies with fakes/stubs when test goals allow.
4. Use **@SpringJUnitConfig** to load the configuration and integrate SpringExtension with JUnit Jupiter.
5. Inject the beans under test into the test class.
6. Write tests against observable behavior using independent, reproducible data.
7. Consider transactions, profiles, properties, and the context cache if the test requires those features.
8. Expand context scope only when the test needs to verify an additional integration boundary.

Comprehensive example:

~~~java
@Configuration
class InventoryTestConfig {

    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-05-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository repository,
            Clock clock) {
        return new InventoryService(repository, clock);
    }
}
~~~

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {

    @Autowired
    private InventoryService inventoryService;

    @Test
    void recordsStockWithDeterministicTime() {
        StockRecord record =
                inventoryService.receive("SKU-100", 12);

        assertEquals("SKU-100", record.sku());
        assertEquals(12, record.quantity());
        assertEquals(
                Instant.parse("2026-05-01T00:00:00Z"),
                record.receivedAt()
        );
    }
}
~~~

This test uses Spring to create InventoryService and inject its dependencies. The in-memory repository lets the test run without a database; the fixed Clock makes timestamps predictable. If the goal shifts to verifying JPA mappings, transactions, or SQL, add a test using the real repository and a test database.

## 14. Checklist When Using @SpringJUnitConfig

Before finalizing configuration, verify:

- The test uses JUnit Jupiter and has SpringExtension via **@SpringJUnitConfig**.
- Configuration classes or resources are specified accurately.
- The context contains only the beans needed for the test goal.
- Bean dependencies are completely registered.
- Component scanning has an intentional scope.
- Profiles and property sources accurately reflect the test scenario.
- Test data and singleton state are isolated.
- Transaction rollback is expected only within the scope managed by Spring.
- Configuration is compatible across tests to leverage the context cache.
- If Boot auto-configuration or a specialized slice is needed, the corresponding bootstrap mechanism was chosen.

**@SpringJUnitConfig** streamlines declarations by combining SpringExtension and ContextConfiguration. Its core value lies in creating a clearly scoped Spring ApplicationContext for JUnit Jupiter. When paired with small Java or XML configuration, selective imports, dependency injection, and supporting annotations, tests can verify the exact module needed while still leveraging the TestContext Framework.


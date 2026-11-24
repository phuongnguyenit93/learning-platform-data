# @TestConstructor and Constructor Autowiring Modes

In JUnit Jupiter, a test class is also a Java object that must be instantiated before its test methods run. If a test uses the Spring TestContext Framework, Spring can supply beans from the `ApplicationContext` to the test class constructor. This approach is called **constructor injection for test classes**.

Spring provides the **@TestConstructor** annotation to select the constructor autowiring mode. This annotation is especially useful when a test has multiple required dependencies that you want to declare through the constructor and store in `final` fields. Instead of letting Spring quietly assign fields after object creation, the list of dependencies is expressed right at the point of test instantiation.

This lesson explains how `@TestConstructor` works, its two autowire modes, project-level default configuration, how it integrates with `SpringExtension` and Spring Boot, and how to distinguish constructor injection from test method parameter injection.

## 1. What is constructor injection in a test class?

A test class often needs several dependencies to verify application behavior:

- The service under test.
- A repository or client for preparing test data.
- A fixed `Clock` to control time.
- A configuration bean or test-support component.

Dependencies can be injected via fields:

~~~java
@SpringBootTest
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void shouldCreateOrder() {
        assertNotNull(orderService);
    }
}
~~~

Or injected via the constructor:

~~~java
@SpringBootTest
class OrderServiceTest {

    private final OrderService orderService;

    @Autowired
    OrderServiceTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void shouldCreateOrder() {
        assertNotNull(orderService);
    }
}
~~~

In the second approach, Spring supplies `OrderService` when JUnit requests creation of the test instance. Once the constructor finishes, the `final` field has its value and the test class is in a ready-to-use state.

**Constructor injection** has several characteristics:

- Required dependencies are explicitly declared in the constructor.
- Dependencies can be stored in `final` fields.
- The object cannot be created if a required dependency is missing.
- The test class does not need field injection or setter injection.
- Readers can immediately see which beans the test depends on from the constructor declaration.

Constructor injection for test classes only works when `SpringExtension` participates in the JUnit lifecycle. If a test runs with plain JUnit without registering `SpringExtension`, JUnit does not know how to retrieve beans from the `ApplicationContext`.

## 2. SpringExtension participates in creating the test instance

The Spring TestContext Framework integrates with JUnit Jupiter via **SpringExtension**. This extension implements JUnit callbacks and provides parameter resolution from the Spring `ApplicationContext`.

You can register the extension explicitly:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class CatalogServiceTest {
}
~~~

Or use the composed annotation:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class CatalogServiceTest {
}
~~~

With Spring Boot, `@SpringBootTest` already integrates `SpringExtension`:

~~~java
@SpringBootTest
class CatalogServiceTest {
}
~~~

Therefore, when using `@SpringBootTest`, you normally do not need to add `@ExtendWith(SpringExtension.class)`.

The test instance creation process can be visualized as follows:

~~~text
JUnit Jupiter discovers the test class
        |
        v
JUnit prepares to create the test instance
        |
        v
SpringExtension participates in constructor processing
        |
        v
Spring retrieves matching beans from ApplicationContext
        |
        v
Spring supplies dependencies to the constructor
        |
        v
Constructor completes, test instance is created
        |
        v
Setup callbacks and test methods are executed
~~~

Important point: the constructor is invoked to create the test instance, so dependencies must be resolved before the object is finished. This is why constructor injection differs from field injection, which takes place after the object has already been created.

## 3. What is @TestConstructor used for?

**@TestConstructor** is a Spring TestContext annotation for test classes running with JUnit Jupiter. It determines whether Spring automatically autowires the test class constructor.

Example:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class OrderServiceTest {

    private final OrderService orderService;
    private final Clock clock;

    OrderServiceTest(
            OrderService orderService,
            Clock clock
    ) {
        this.orderService = orderService;
        this.clock = clock;
    }

    @Test
    void shouldUseConfiguredDependencies() {
        assertNotNull(orderService);
        assertNotNull(clock);
    }
}
~~~

In this example:

- `@TestConstructor` selects the mode that automatically autowires the entire constructor.
- `OrderService` and `Clock` are retrieved from the `ApplicationContext`.
- `@Autowired` does not need to be placed on the constructor.
- Dependencies are stored in `final` fields.

The annotation's main attribute is **autowireMode**. This attribute accepts a value from the **TestConstructor.AutowireMode** enum.

The two modes to understand are:

- **ANNOTATED**: only automatically autowires the constructor when the test constructor is annotated with `@Autowired`.
- **ALL**: automatically autowires the test class constructor without requiring `@Autowired`.

The name `ANNOTATED` can be misleading: this mode refers to whether the constructor itself is annotated with `@Autowired`. It does not mean Spring only injects individual parameters annotated with `@Autowired`.

## 4. ANNOTATED mode

`ANNOTATED` is the default mode if no other configuration is present. In this mode, the test class constructor must be marked with `@Autowired` for Spring to automatically supply the constructor parameters.

Example:

~~~java
@SpringJUnitConfig(CatalogTestConfiguration.class)
class CatalogServiceTest {

    private final CatalogService catalogService;

    @Autowired
    CatalogServiceTest(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Test
    void shouldLoadCatalog() {
        assertNotNull(catalogService);
    }
}
~~~

Spring sees that the constructor is annotated with `@Autowired`, so it resolves the parameters from the `ApplicationContext`.

If `@Autowired` is omitted while still in `ANNOTATED` mode, the constructor is not automatically autowired by this mechanism. JUnit will attempt to resolve the constructor using registered parameter resolvers; if no matching resolver exists, the test may fail when creating the instance.

`ANNOTATED` mode is suitable when:

- Only a few test classes need constructor injection.
- Most existing tests still use field or setter injection.
- You want to decide explicitly per class whether constructor injection is used.
- You do not want to alter instance creation behavior across the entire test suite.

For a project with many legacy test classes, `ANNOTATED` allows adopting constructor injection gradually without changing the default for other classes.

## 5. ALL mode

`ALL` instructs Spring to automatically autowire the test class constructor. You do not need to put `@Autowired` on the constructor.

~~~java
@SpringJUnitConfig(CatalogTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class CatalogServiceTest {

    private final CatalogService catalogService;
    private final Clock clock;

    CatalogServiceTest(
            CatalogService catalogService,
            Clock clock
    ) {
        this.catalogService = catalogService;
        this.clock = clock;
    }

    @Test
    void shouldUseFixedClock() {
        assertNotNull(catalogService);
        assertEquals(ZoneOffset.UTC, clock.getZone());
    }
}
~~~

In this mode, Spring treats constructor parameters as dependencies to be resolved from the context. If there are multiple beans of the same type, you can use `@Qualifier` or `@Primary` to select the right bean.

`ALL` is suitable when:

- The project consistently uses constructor injection for test classes.
- Most test class dependencies are Spring beans.
- You want to avoid repeating the `@Autowired` annotation on every constructor.
- You want required dependencies to be expressed via constructors across all test classes within the configured scope.

However, do not enable `ALL` indiscriminately for the whole project if many test classes have constructors serving other purposes, such as constructors taking manually created data or non-bean test fixtures. In `ALL` mode, Spring will attempt to resolve all constructor parameters through autowiring.

## 6. Comparing ANNOTATED and ALL

| Criterion | ANNOTATED | ALL |
|---|---|---|
| Is it the default mode? | Yes, if no other configuration exists | No |
| Does the constructor require @Autowired? | Yes | No |
| Scope of application | Only annotated constructors | Test class constructor |
| Suitable when | Only some tests use constructor injection | The project wants consistent adoption |
| Potential impact on legacy tests | Lower | Higher if enabled globally |
| Risk with non-bean parameters | Only occurs when the constructor is autowired | Every constructor parameter must be resolvable by Spring |

Example of the same test class:

~~~java
@SpringBootTest
class PaymentServiceTest {

    private final PaymentService paymentService;

    @Autowired
    PaymentServiceTest(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

This is how it is written with `ANNOTATED`.

If switched to `ALL`:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class PaymentServiceTest {

    private final PaymentService paymentService;

    PaymentServiceTest(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

Both approaches achieve the same result for injected dependencies. The difference lies in how constructor autowiring is triggered.

## 7. Global default configuration with spring.test.constructor.autowire.mode

If you want to apply the same mode to many test classes, Spring TestContext supports the property:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

You can place this property in a **spring.properties** file on the test classpath, for example:

~~~text
src/test/resources/spring.properties
~~~

Contents:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

When Spring TestContext reads this configuration, test classes that do not declare `@TestConstructor` will use `ALL` mode.

It can also be set via a JVM system property:

~~~text
-Dspring.test.constructor.autowire.mode=all
~~~

Supported values:

| Value | Meaning |
|---|---|
| all | Automatically autowires test class constructors |
| annotated | Only autowires constructors annotated with `@Autowired` |

If no global property is configured, Spring uses `ANNOTATED` mode.

This global property belongs to Spring Framework's configuration mechanism and is read through `SpringProperties`. Therefore, place it in `spring.properties` or as a JVM system property according to that mechanism. Do not assume that merely adding it to `application.yml` is enough to change the Spring TestContext mode.

### When should ALL be enabled globally?

You can consider `ALL` when:

- A new project establishes constructor injection as the convention for test classes.
- All test classes use constructors to receive beans.
- The development team controls any tests with special constructors.
- CI and developer environments share the same test configuration.

If the project has multiple modules or multiple test groups with different structures, consider configuring per test class with `@TestConstructor` to avoid unintended side effects outside the target scope.

## 8. Precedence between @TestConstructor and global configuration

Configuration on a test class can override the global default mode.

For example, the project configures `spring.properties`:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

An individual test class can opt back into `ANNOTATED`:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ANNOTATED
)
class LegacyRepositoryTest {

    private final RepositoryService repositoryService;

    @Autowired
    LegacyRepositoryTest(RepositoryService repositoryService) {
        this.repositoryService = repositoryService;
    }
}
~~~

In this case, the annotation on the class determines the mode for that class. Other test classes that do not declare `@TestConstructor` still use the global value.

You can remember the decision order as follows:

~~~text
@TestConstructor on test class
        |
        | Declared?
        +---- Yes ----> Use autowireMode from the annotation
        |
        +---- No
                |
                v
spring.test.constructor.autowire.mode
        |
        | Configured?
        +---- Yes ----> Use the global mode
        |
        +---- No
                |
                v
        ANNOTATED (default)
~~~

This organization allows a project to have a shared default while keeping explicit exceptions on test classes that require different behavior.

## 9. Using @Qualifier and @Value in test constructors

Constructor injection follows Spring's dependency resolution mechanism. If there are multiple beans of the same type, use `@Qualifier` to specify the bean to inject.

Example with two `Clock` beans:

~~~java
@Configuration(proxyBeanMethods = false)
class ClockTestConfiguration {

    @Bean
    @Qualifier("utcClock")
    Clock utcClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    @Qualifier("localClock")
    Clock localClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T08:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")
        );
    }
}
~~~

The test can select a specific bean:

~~~java
@SpringJUnitConfig(ClockTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class ClockConfigurationTest {

    private final Clock clock;

    ClockConfigurationTest(
            @Qualifier("utcClock") Clock clock
    ) {
        this.clock = clock;
    }

    @Test
    void shouldUseUtcClock() {
        assertEquals(ZoneOffset.UTC, clock.getZone());
    }
}
~~~

If a property is needed instead of a bean, you can use `@Value`:

~~~java
@SpringBootTest(properties = "app.region=ap-southeast-1")
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class RegionConfigurationTest {

    private final String region;

    RegionConfigurationTest(
            @Value("${app.region}") String region
    ) {
        this.region = region;
    }

    @Test
    void shouldUseConfiguredRegion() {
        assertEquals("ap-southeast-1", region);
    }
}
~~~

Here Spring resolves the `region` parameter via property placeholder resolution. `@Qualifier` selects a bean, while `@Value` retrieves a value from the `Environment`. Distinguish these two approaches from asking JUnit to pass data for a single test invocation.

## 10. Combining constructor injection with @SpringBootTest

With a Spring Boot application, you can directly inject services and supporting dependencies from the `ApplicationContext`.

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class InvoiceServiceTest {

    private final InvoiceService invoiceService;
    private final Clock clock;

    InvoiceServiceTest(
            InvoiceService invoiceService,
            Clock clock
    ) {
        this.invoiceService = invoiceService;
        this.clock = clock;
    }

    @Test
    void shouldCreateInvoice() {
        var invoice = invoiceService.create(sampleOrder());

        assertNotNull(invoice);
        assertNotNull(clock);
    }
}
~~~

`@SpringBootTest` initializes the `ApplicationContext` according to Spring Boot configuration. `SpringExtension` is built in, so the constructor is resolved according to the selected mode.

If you need a test-only bean, you can declare `@TestConfiguration` and import it:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class InvoiceTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

~~~java
@SpringBootTest
@Import(InvoiceTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class InvoiceServiceTest {

    private final InvoiceService invoiceService;
    private final Clock clock;

    InvoiceServiceTest(
            InvoiceService invoiceService,
            Clock clock
    ) {
        this.invoiceService = invoiceService;
        this.clock = clock;
    }

    @Test
    void shouldUseTestClock() {
        assertEquals(ZoneOffset.UTC, clock.getZone());
    }
}
~~~

The example assumes the application has an `InvoiceService` and no other `Clock` bean causing a conflict. If multiple beans share the same type, use `@Qualifier` or configure an appropriate `@Primary`.

There is no need to add `@ExtendWith(SpringExtension.class)` when already using `@SpringBootTest`. Spring Boot already integrates this extension into its testing annotation.

## 11. Combining with @SpringJUnitConfig and minimal configuration

Not every test needs the full Spring Boot `ApplicationContext`. You can use `@SpringJUnitConfig` to load a small configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class GreetingTestConfiguration {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    GreetingService greetingService(Clock clock) {
        return new GreetingService(clock);
    }
}
~~~

Test class:

~~~java
@SpringJUnitConfig(GreetingTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class GreetingServiceTest {

    private final GreetingService greetingService;

    GreetingServiceTest(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @Test
    void shouldGenerateGreetingAtFixedTime() {
        var greeting = greetingService.greet("Lan");

        assertEquals(
                "Hello Lan at 2026-01-01T00:00:00Z",
                greeting
        );
    }
}
~~~

A minimal configuration helps the test instantiate only the necessary beans. Constructor injection still works just like with `@SpringBootTest` because `@SpringJUnitConfig` also registers `SpringExtension`.

This approach is suitable when the goal is to verify a specific group of beans and configuration without the rest of the application's auto-configurations.

## 12. Distinguishing constructor injection from test method parameters

An important point is that **@TestConstructor only controls autowiring of the test class constructor**. It does not decide how JUnit passes parameters to individual test methods.

For example, a test class can constructor-inject a service while a test method receives data from `@ParameterizedTest`:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class DiscountServiceTest {

    private final DiscountService discountService;

    DiscountServiceTest(DiscountService discountService) {
        this.discountService = discountService;
    }

    @ParameterizedTest
    @CsvSource({
            "100000, 0",
            "200000, 10000",
            "500000, 50000"
    })
    void shouldCalculateDiscount(
            BigDecimal amount,
            BigDecimal expectedDiscount
    ) {
        var result = discountService.calculate(amount);

        assertEquals(expectedDiscount, result);
    }
}
~~~

In the example:

- `DiscountService` is injected when creating the test instance.
- `amount` and `expectedDiscount` are supplied by JUnit for each invocation from `@CsvSource`.
- `@TestConstructor` does not turn CSV values into Spring beans.

Do not place data specific to individual test cases into the test class constructor. The constructor is meant for receiving stable dependencies from the context; data that varies by scenario should be passed into the test method, parameterized test, or fixture setup.

`SpringExtension` can also resolve parameters for test methods and lifecycle methods in supported cases, such as parameters annotated with `@Autowired`, `@Qualifier`, or `@Value`. This is a separate parameter resolution mechanism, not an effect of `@TestConstructor`.

## 13. Constructor injection and the test lifecycle

The test class constructor is invoked when JUnit creates the test instance. Therefore, the test instance lifecycle mode affects how many times the constructor executes.

With the default `PER_METHOD`:

- JUnit creates a test instance for each test method.
- Constructor injection runs each time an instance is created.
- The Spring `ApplicationContext` is typically reused via context caching.
- Singleton beans in the same context may still be the same objects across test instances.

With `PER_CLASS`:

- JUnit creates a single shared test instance for the entire class.
- Constructor injection only occurs when that instance is created.
- Fields of the test instance are retained between test methods.
- Mutable state must be managed carefully.

Example:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class CatalogLifecycleTest {

    private final CatalogService catalogService;
    private int invocationCount;

    CatalogLifecycleTest(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @BeforeEach
    void setUp() {
        invocationCount = 0;
    }

    @Test
    void shouldLoadCatalog() {
        invocationCount++;
        assertNotNull(catalogService);
    }
}
~~~

`PER_CLASS` does not change the dependency resolution rules of `@TestConstructor`. It only changes when and how many times JUnit creates the test instance.

Do not rely on the constructor being called multiple times to reset singleton beans in Spring. The test instance and the `ApplicationContext` have independent lifecycles.

## 14. Cases where ALL should not be used

`ALL` is convenient when every constructor parameter is a dependency that Spring can resolve. However, this mode may not be appropriate if the constructor contains non-bean data.

Example:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class ReportServiceTest {

    ReportServiceTest(
            ReportService reportService,
            String reportName
    ) {
        // ...
    }
}
~~~

If `String reportName` is not supplied by an appropriate injection mechanism such as `@Value`, Spring cannot infer the value to pass. The test may fail during instance creation.

Use the constructor for stable dependencies:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class ReportServiceTest {

    private final ReportService reportService;

    ReportServiceTest(ReportService reportService) {
        this.reportService = reportService;
    }

    @Test
    void shouldGenerateSummary() {
        var reportName = "monthly-sales";

        var report = reportService.generate(reportName);

        assertNotNull(report);
    }
}
~~~

If a parameter is genuinely a configuration property, use `@Value` or inject a `@ConfigurationProperties` class. If it is data specific to a test case, create it inside the test method or pass it via a parameterized test.

Global `ALL` should also be avoided when:

- Inherited test classes have incompatible constructors.
- Test constructors receive data supplied by another framework.
- Multiple modules use different JUnit extensions.
- Some test classes do not need Spring but sit in a suite with a global property configured.
- Enabling `ALL` alters how JUnit and Spring resolve parameters in existing tests.

In those situations, keeping `ANNOTATED` and enabling `ALL` only on the specific classes that need constructor injection is easier to control.

## 15. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Constructor does not receive beans | `SpringExtension` is not registered | Use `@SpringJUnitConfig` or `@SpringBootTest` |
| Constructor is not autowired | In `ANNOTATED` mode but missing `@Autowired` | Annotate the constructor or choose `ALL` |
| No bean found by type | Bean is not registered or context lacks configuration | Check `@ContextConfiguration`, component scan, and bean configuration |
| Multiple beans of the same type | Spring cannot determine a unique candidate | Use `@Qualifier` or `@Primary` |
| Cannot inject `String`/`Integer` parameter | No matching bean or `@Value` source | Use `@Value`, configuration properties, or create data in the test method |
| Legacy test suddenly fails after enabling global `ALL` | Test class constructor has non-bean parameters | Narrow the scope of `ALL` or adjust the constructor structure |
| `@ParameterizedTest` parameter mistaken as dependency | Confusing constructor injection with method parameter resolution | Keep test data on method parameters |
| Dependency field is null | Accessing the field before Spring prepares the test instance or missing `SpringExtension` | Check annotations and lifecycle |
| New test instance yet bean retains state | `ApplicationContext` cache reuses singletons | Reset state or design stateless beans |

When diagnosing errors, check in order:

1. Is the test running with `SpringExtension`?
2. Is the test class using `ANNOTATED` or `ALL`?
3. Is the constructor annotated with `@Autowired` when required?
4. Can every parameter be resolved by Spring from a bean, qualifier, or property?
5. Does the `ApplicationContext` register the corresponding bean?
6. Are there multiple beans of the same type or profile settings excluding the bean?
7. Did a global configuration inadvertently affect another test class?

## 16. Comparing constructor injection, field injection, and method parameter injection

| Injection approach | Timing | Strengths | Caveats |
|---|---|---|---|
| Constructor injection | During test instance creation | Required dependencies are explicit; can use `final` fields | Requires a suitable constructor and autowire mode |
| Field injection | After test instance creation | Short declaration, familiar in many legacy tests | Fields are not `final`; dependencies are less explicit |
| Setter/method injection | After instance creation or via lifecycle callback | Can be used for optional dependencies or setup | Easier to end up with an incompletely initialized object state |
| Test method parameter | When each test method is invoked | Good for per-method dependencies and test data | Requires `SpringExtension` or an appropriate parameter resolver |
| Parameterized test argument | Per invocation | Ideal for input data varying by case | This is test data supplied by JUnit, not bean injection |

Constructor injection is usually best suited for required, stable dependencies across the entire test class. Field injection can still be reasonable in simple tests or existing codebases. Method parameters are suitable when only a single test needs a dependency or when data varies per invocation.

There is no need to convert the entire test suite to constructor injection just because `@TestConstructor` exists. Use it when declaring dependencies in the constructor makes tests clearer and easier to maintain.

## 17. Workflow for adopting @TestConstructor in a project

When introducing constructor injection into an existing Spring project, you can follow these steps:

1. Pick a test class that has required, stable dependencies.
2. Verify the test class runs with `SpringExtension` via `@SpringJUnitConfig` or `@SpringBootTest`.
3. Choose `ANNOTATED` for local adoption, or `ALL` if the project has agreed on the convention.
4. Declare a constructor receiving the required beans.
5. Store dependencies in `final` fields.
6. Use `@Qualifier` or `@Value` if distinguishing beans or reading properties is needed.
7. Run the test class and check for context creation errors, missing bean errors, or parameter errors.
8. If you want to enable `ALL` globally, inspect test classes with special constructors before changing the configuration.
9. Keep test-method-specific data in test methods or parameterized tests.
10. Watch mutable state on test instances and singleton beans when running the full suite or running in parallel.

For example, a group of new tests can standardize on:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class CustomerServiceTest {

    private final CustomerService customerService;
    private final Clock clock;

    CustomerServiceTest(
            CustomerService customerService,
            Clock clock
    ) {
        this.customerService = customerService;
        this.clock = clock;
    }
}
~~~

While older test classes continue using `ANNOTATED` or field injection. Migrating group by group avoids changing the behavior of the entire suite at once.

## 18. Conclusion

`@TestConstructor` configures how Spring automatically injects dependencies into a test class constructor when running with JUnit Jupiter and `SpringExtension`.

Two modes to remember:

- **ANNOTATED**: only autowires test constructors annotated with `@Autowired`. This is the default when no other configuration is present.
- **ALL**: automatically autowires the test class constructor without needing `@Autowired`.

You can choose the mode per class with `@TestConstructor` or set a project default via `spring.test.constructor.autowire.mode` in `spring.properties` or a JVM system property. The class-level annotation lets an individual test choose its own mode.

Use constructor injection for required, stable dependencies that can be obtained from the `ApplicationContext`. Use `@Qualifier` when there are multiple beans of the same type, `@Value` for properties, and test method parameters for data that varies per scenario. By clearly separating test class dependencies from per-invocation test data, `@TestConstructor` makes tests easier to read, reduces intermediate state, and improves maintainability.


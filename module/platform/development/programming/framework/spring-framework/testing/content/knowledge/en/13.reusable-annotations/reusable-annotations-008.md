# Avoiding Large Test Superclasses That Hide Many Dependencies

In a Spring project, reusing configuration and fixtures helps reduce duplication across tests. However, a test superclass can grow over time: accumulating many injected fields, many class-level annotations, and many setup and helper methods for different scenarios. Child tests need only a small subset yet still inherit all of that configuration and those dependencies.

When this happens, a test's name no longer reveals everything required to run it. A test that looks like a simple service test might actually start the entire application, connect to a database, enable security filters, mock multiple beans, and run many preparation steps hidden in the superclass.

**A test superclass should contain only rules and resources truly shared by all subclasses.** For reusable configuration, clearly scoped composed annotations, small test configurations, and fixture factories usually make a test's intent easier to see. The goal is for readers to tell what kind of context a test uses, which dependencies it needs, and what behavior it is verifying right from the test class.

## 1. Why Do Large Test Superclasses Become a Problem?

Imagine a superclass created to avoid repeating Spring configuration:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
abstract class AbstractIntegrationTest {

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected OrderService orderService;

    @Autowired
    protected CustomerService customerService;

    @Autowired
    protected PaymentService paymentService;

    @Autowired
    protected OrderRepository orderRepository;

    @Autowired
    protected CustomerRepository customerRepository;

    @Autowired
    protected PaymentRepository paymentRepository;

    @Autowired
    protected TestDataCleaner testDataCleaner;

    @BeforeEach
    void cleanDatabase() {
        testDataCleaner.cleanAll();
    }

    protected Customer createCustomer() {
        // Create a default customer.
    }

    protected Order createOrder() {
        // Create a default order.
    }

    protected Payment createPayment() {
        // Create a default payment.
    }
}
~~~

A subclass might only need to test one small rule:

~~~java
class OrderNumberFormatterTest extends AbstractIntegrationTest {

    @Test
    void formatsOrderNumber() {
        // Test order number formatting.
    }
}
~~~

Yet this test still inherits:

- Full Spring Boot `ApplicationContext`.
- `MockMvc` and web configuration.
- The `test` profile.
- Transactions for test methods.
- Many unrelated services and repositories.
- Data cleanup logic before every test.
- Every lifecycle callback declared in the superclass.

If the goal is just testing string formatting, most of that context and fixture contributes no evidence to the behavior under test. The test can be slow, depend on a database, or fail due to an unrelated bean.

### Signs a Superclass Has Grown Too Large

Some common signs:

- A subclass extends it just to get one field or one helper.
- The superclass injects many beans while each subclass uses only a few.
- A configuration change in the superclass breaks many unrelated tests together.
- Subclasses must override setup methods to turn off part of the superclass logic.
- There are many boolean flags or hook methods to toggle parts of the fixture.
- Readers must inspect the superclass to understand how the database, profile, transaction, or security is configured.
- A unit test accidentally inherits a full context just because it needed a data-creation helper.
- The superclass contains many utility methods belonging to different domains.

The core issue is that dependencies have been obscured. Looking at the subclass, a reader cannot tell what it actually needs or what environment it runs in.

## 2. Distinguishing Configuration Reuse from Behavior Reuse

Two needs are often lumped together into one superclass:

**Configuration reuse:** many tests need the same way of starting a context, the same profile, the same set of auto-configurations, or the same group of beans.

**Preparation behavior reuse:** many tests need to create customers, orders, accounts, or test data according to a shared rule.

These two needs can be solved separately:

| Need | Typically Suitable Mechanism |
|---|---|
| Reuse a test slice for a group of controllers | Composed annotation based on @WebMvcTest |
| Reuse profile and config for a group of integration tests | Composed annotation or test configuration |
| Register a few test support beans | @TestConfiguration and @Import |
| Create sample entities or DTOs | Fixture factory or builder |
| Reuse special setup/cleanup behavior | JUnit Extension or clearly scoped helper |
| Share a test flow with a fixed structure | Small abstract base class with a clear contract |

There is no need to dump everything into one superclass. Spring configuration, data fixtures, and lifecycle behavior are separate concerns; keeping them separate ensures each test receives only what it needs.

## 3. Composed Annotations Help Reuse Configuration Intent

Spring supports using annotations as meta-annotations. As a result, you can create composed annotations to group a commonly used test configuration.

For example, many controller tests all need:

- `@WebMvcTest`.
- A shared MVC configuration.
- A profile dedicated to web tests.

You can define a dedicated annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@ActiveProfiles("web-test")
@Import(WebTestConfiguration.class)
public @interface WebLayerTest {
}
~~~

The test class expresses clear intent:

~~~java
@WebLayerTest
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CustomerService customerService;

    @Test
    void returnsCustomerDetails() throws Exception {
        // Send request and assert HTTP response.
    }
}
~~~

Readers immediately know this is a web-layer test with the `web-test` profile and MVC support configuration. There is no need to hunt for a superclass to understand why the context has that configuration.

### Allowing Composed Annotations to Accept Parameters

If a composed annotation needs to apply to different controllers, you can forward attributes with `@AliasFor`:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@ActiveProfiles("web-test")
@Import(WebTestConfiguration.class)
public @interface WebLayerTest {

    @AliasFor(
            annotation = WebMvcTest.class,
            attribute = "controllers")
    Class<?>[] controllers() default {};
}
~~~

Usage:

~~~java
@WebLayerTest(controllers = CustomerController.class)
class CustomerControllerTest {
    // ...
}
~~~

`@AliasFor` declares an attribute on the composed annotation corresponding to an attribute on a meta-annotation. Defining aliases must follow Spring's rules: the data type and default value must be compatible with the mapped attribute.

Do not create an annotation with dozens of attributes to replace a giant superclass. A composed annotation should express a meaningful configuration with a stable scope.

## 4. Creating Annotations by Risk Category

A project may have multiple test groups with different requirements. Name annotations by scope or purpose so readers recognize what part the test is verifying.

Example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@Import(ApiWebTestConfiguration.class)
public @interface ApiControllerTest {
}
~~~

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DataJpaTest
public @interface JpaRepositoryTest {
}
~~~

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@ActiveProfiles("integration")
public @interface ApplicationIntegrationTest {
}
~~~

Usage:

~~~java
@ApiControllerTest
class OrderControllerTest {
    // Tests only the MVC boundary.
}

@JpaRepositoryTest
class OrderRepositoryTest {
    // Tests mapping and queries.
}

@ApplicationIntegrationTest
class OrderWorkflowIntegrationTest {
    // Tests workflows coordinating multiple layers.
}
~~~

These annotations express three different scopes. Controller tests do not accidentally inherit the database and all services like a subclass of an integration base class. Repository tests do not need to start a web server if there is no web-related risk either.

The annotation name should reflect the real configuration. If `@ApplicationIntegrationTest` only loads a tiny context, that name can be misleading. Choose names that describe the scope and guarantees the team agrees on.

### Avoid Combining Conflicting Configurations

Do not create a composed annotation carrying both `@WebMvcTest` and `@SpringBootTest`. These two annotations use different bootstrap mechanisms and context scopes. Combining them can create a confusing or invalid configuration.

A composed annotation should represent one consistent way to bootstrap a test. If a test needs a full context and `MockMvc`, use `@SpringBootTest` combined with `@AutoConfigureMockMvc` in the corresponding integration annotation.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface MvcIntegrationTest {
}
~~~

Usage:

~~~java
@MvcIntegrationTest
class OrderWorkflowMvcIntegrationTest {
    // Requests pass through the full application context.
}
~~~

This is a different scope from `@WebMvcTest`: the full context is started, and `MockMvc` sends requests through the Spring MVC test infrastructure.

## 5. Using `@Import` and `@TestConfiguration` Instead of Hidden Fields in a Superclass

A superclass often holds many beans solely for testing. You can move those beans into a dedicated test configuration and import it intentionally.

~~~java
@TestConfiguration(proxyBeanMethods = false)
class OrderTestSupportConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    OrderNumberGenerator orderNumberGenerator() {
        return new SequentialOrderNumberGenerator();
    }
}
~~~

The test class loads the configuration only when genuinely needed:

~~~java
@SpringBootTest
@Import(OrderTestSupportConfiguration.class)
class OrderIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private Clock clock;

    @Test
    void createsOrderUsingConfiguredClock() {
        // Verifies time-dependent behavior.
    }
}
~~~

The configuration is named after its role and imported only in tests that need it. Readers can trace dependencies without following an inheritance tree.

### Splitting Support Configurations into Small Groups

If there are multiple types of test resources, you can split them by responsibility:

- `WebTestConfiguration`: converters, formatters, controller advice, or web support components.
- `PersistenceTestConfiguration`: database helpers or persistence support beans.
- `ClockTestConfiguration`: fixed clock for testing time.
- `MessagingTestConfiguration`: publisher or listener test doubles.
- `SecurityTestConfiguration`: users, authentication, or security policies for tests.

You do not necessarily need one configuration class per bean. Split only when a group of beans has a clear purpose and is used by many tests.

## 6. Fixture Factories Help Tests Show Required Data

A common reason a superclass bloats is that it holds many data-creation methods:

~~~java
protected Customer createCustomer() { ... }
protected Order createOrder() { ... }
protected Payment createPayment() { ... }
protected Product createProduct() { ... }
protected Invoice createInvoice() { ... }
~~~

If a test only needs one customer, extending an entire superclass can pull in a series of other dependencies and setups. An independent fixture factory can supply just the data needed.

~~~java
public final class CustomerFixtures {

    private CustomerFixtures() {
    }

    public static Customer activeCustomer() {
        return new Customer(
                "customer-42",
                "Linh",
                "linh@example.com",
                CustomerStatus.ACTIVE);
    }

    public static Customer customerWithEmail(String email) {
        return new Customer(
                "customer-42",
                "Linh",
                email,
                CustomerStatus.ACTIVE);
    }
}
~~~

Test uses it directly:

~~~java
@Test
void acceptsActiveCustomer() {
    Customer customer = CustomerFixtures.activeCustomer();

    CustomerResult result = customerPolicy.evaluate(customer);

    assertEquals(CustomerStatus.ACTIVE, result.status());
}
~~~

Fixture factories do not need to start Spring and do not inject repositories if they only create domain objects.

### Distinguishing Pure Fixtures from Fixtures Requiring Persistence

If data needs to be saved to a database, you can create a helper that accepts the repository explicitly:

~~~java
public class CustomerRepositoryFixtures {

    private final CustomerRepository repository;

    public CustomerRepositoryFixtures(
            CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer createActiveCustomer() {
        return repository.save(
                CustomerFixtures.activeCustomer());
    }
}
~~~

In the test:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    private CustomerRepositoryFixtures fixtures;

    @BeforeEach
    void setUp() {
        fixtures = new CustomerRepositoryFixtures(customerRepository);
    }

    @Test
    void findsActiveCustomer() {
        Customer customer = fixtures.createActiveCustomer();

        // Query and assert the result.
    }
}
~~~

The fixture's dependency is visible right at initialization. The test does not need to extend a base class just to grab a repository and a bunch of unrelated helpers.

### Builders When Data Has Many Variants

If an entity has many fields and each test needs a different variant, a builder can make data clear:

~~~java
Customer customer = CustomerBuilder.aCustomer()
        .withId("customer-42")
        .withName("Linh")
        .withStatus(CustomerStatus.ACTIVE)
        .withEmail("linh@example.com")
        .build();
~~~

Builders should have valid default values and let tests override fields meaningful to the scenario. Avoid overly clever builders that make readers unsure which fields are populated implicitly.

## 7. JUnit Extensions Fit Shared Lifecycle Behavior

A superclass often has `@BeforeEach` or `@AfterEach` to prepare and clean up resources. If this behavior is an independent testing utility, a JUnit Jupiter Extension can express it more clearly.

For example, an extension recording test execution time:

~~~java
public class ExecutionTimeExtension
        implements BeforeTestExecutionCallback,
                   AfterTestExecutionCallback {

    private static final ExtensionContext.Namespace NAMESPACE =
            ExtensionContext.Namespace.create(
                    ExecutionTimeExtension.class);

    @Override
    public void beforeTestExecution(
            ExtensionContext context) {
        context.getStore(NAMESPACE).put(
                "startedAt", System.nanoTime());
    }

    @Override
    public void afterTestExecution(
            ExtensionContext context) {
        long startedAt = context.getStore(NAMESPACE)
                .get("startedAt", Long.class);

        long elapsed = System.nanoTime() - startedAt;

        System.out.printf(
                "%s took %d ms%n",
                context.getDisplayName(),
                elapsed / 1_000_000);
    }
}
~~~

Can be registered on a test class:

~~~java
@ExtendWith(ExecutionTimeExtension.class)
class CustomerServiceTest {
    // ...
}
~~~

Extensions separate lifecycle behavior from the inheritance tree. Many tests can reuse it without inheriting a base class containing extra dependencies.

### When to Use an Extension?

Extensions fit when the behavior has its own lifecycle, for example:

- Starting and closing an external resource.
- Registering or releasing a test listener.
- Supplying parameters to test methods.
- Tracking test lifecycle or metadata.
- Managing a resource per test class or per test method.

If the behavior is just creating a small object or preparing a value, a plain helper is usually simpler than an extension. There is no need to turn every setup step into an extension.

### Extensions Are Not a Place to Hide Arbitrary Dependencies

An extension can create hidden coupling if it opens databases, connects to brokers, loads profiles, or injects many services that the test class cannot see. Name extensions after their responsibility, keep configuration minimal, and make usage conditions clear.

## 8. Properly Understanding Annotation Inheritance and Test Class Inheritance

Java and JUnit/Spring have different inheritance rules. Do not assume every annotation on a superclass automatically takes effect on a subclass.

### Java's `@Inherited`

An annotation marked `@Inherited` can be inherited through a superclass when looking up annotations on a subclass. This mechanism:

- Applies only to annotations placed on classes.
- Applies only through the superclass chain.
- Does not inherit annotations from interfaces.
- Does not make annotations on methods automatically inherited via the same mechanism.
- Does not apply if the annotation is not declared with `@Inherited`.

Custom annotation example:

~~~java
@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface IntegrationEnvironment {
}
~~~

If the superclass has `@IntegrationEnvironment`, the subclass can see this annotation through Java's inherited annotation lookup mechanism.

### Spring Has Its Own Meta-Annotation and Inherited Annotation Search Mechanism

Spring Test uses its own annotation search mechanism to support composed annotations, meta-annotations, and certain inheritance rules for testing annotations.

For example, annotations such as `@SpringBootTest`, `@ContextConfiguration`, and `@ActiveProfiles` are designed for test configuration and can participate in inheritance according to Spring's corresponding rules.

However, inherited attributes may have dedicated flags. For example:

- `@ContextConfiguration` has attributes controlling inheritance of locations and classes.
- `@ActiveProfiles` has the `inheritProfiles` attribute.
- `@TestPropertySource` has attributes controlling inheritance of locations and properties.
- `@NestedTestConfiguration` controls whether nested classes inherit test configuration from the enclosing class.

When using composed annotations, read the documentation of the underlying annotation and identify which attributes can be aliased, which are inherited, and how Spring searches annotations on superclasses.

### `@Inherited` Does Not Solve Superclass Design Problems

Even when a composed annotation is inherited properly, placing that annotation on a large superclass can still obscure the test scope. Annotation inheritance is only a mechanism to apply configuration; it does not make that configuration suitable for every subclass.

A subclass should declare the annotation reflecting its test goal directly when doing so makes the scope clearer. Only rely on a superclass when every subclass genuinely shares the same intent and configuration contract.

## 9. Lifecycle in a Superclass Is Also Inherited

JUnit Jupiter can discover test methods and lifecycle methods inherited from a superclass according to JUnit rules. Therefore, a superclass not only passes down class-level annotations, it can also add setup and cleanup to every child test.

Example:

~~~java
abstract class BaseTest {

    @BeforeEach
    void prepareBaseState() {
        // Shared setup.
    }

    @AfterEach
    void cleanBaseState() {
        // Shared cleanup.
    }
}

class CustomerServiceTest extends BaseTest {

    @BeforeEach
    void prepareCustomer() {
        // Customer-specific setup.
    }

    @Test
    void createsCustomer() {
        // ...
    }
}
~~~

In JUnit Jupiter, setup from the superclass runs before setup of the subclass; cleanup from the subclass runs before cleanup of the superclass. If a superclass has many callbacks or multiple intermediate inheritance layers, the execution order can be hard to see from the final test class.

A small base class with one genuinely shared callback can be useful. But if each subclass must override hooks, set flags, or rely on a multi-layer callback chain, move the behavior into an extension or explicitly called helpers.

## 10. Dependencies Commonly Hidden in a Superclass

### Full `ApplicationContext`

A base class with `@SpringBootTest` forces every subclass to boot a full context. A child test might not need a web server, database, or messaging yet still pays that cost and dependency burden.

Solution: use slice annotations or small configuration contexts for each test group.

### `@Autowired` Fields Not Declared in the Test Class

A subclass can call helpers using services or repositories injected in the superclass. Reading the subclass, those dependencies do not appear in its field declarations.

Solution: make required dependencies explicit fields in the test class or pass them into a helper created with constructor parameters.

### Global Data Setup

A `@BeforeEach` in a base class might wipe the entire database, create default accounts, start a mock server, and load reference data. A small test needing only one record ends up running all those steps.

Solution: split fixtures by domain and let tests call the exact factory they need.

### Hidden Profiles and Properties

A superclass might activate test profiles, alter properties, toggle feature flags, or register test initializers. A subclass sees the test annotation without knowing which beans were selected.

Solution: use clearly named composed annotations or declare profiles/properties directly at the test class when they are important to the scenario.

### Transactions and Context Reset

`@Transactional` or `@DirtiesContext` placed on a superclass can affect every subclass. This can lead subclasses to assume data always rolls back or the context is always restarted.

Solution: place transaction scope and context lifecycle on the exact test classes that need them. Do not use cleanup annotations on a base class as a blanket cure for state leaks.

### Mocks Registered from the Superclass

A base class might declare many `@MockitoBean` or `@MockBean` fields. All subclasses receive those mocks, even when unused. Bean overrides can also affect context caching.

Solution: put mocks on the test class or in an annotation/configuration dedicated to tests sharing the same dependencies.

## 11. An Example of Migrating from a Large Base Class to Clear Configuration

Suppose you start with:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
abstract class AbstractApplicationTest {

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected CustomerService customerService;

    @Autowired
    protected CustomerRepository customerRepository;

    @Autowired
    protected PaymentService paymentService;

    @Autowired
    protected PaymentRepository paymentRepository;

    @Autowired
    protected TestDataCleaner cleaner;

    @BeforeEach
    void resetAllData() {
        cleaner.cleanAll();
    }
}
~~~

Subclasses:

~~~java
class CustomerControllerTest extends AbstractApplicationTest {
    // Only uses mockMvc.
}

class CustomerRepositoryTest extends AbstractApplicationTest {
    // Only uses customerRepository.
}

class PaymentServiceTest extends AbstractApplicationTest {
    // Only uses paymentService.
}
~~~

Three tests have three different risks yet share the same configuration. They can be split into:

~~~java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CustomerService customerService;
}
~~~

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;
}
~~~

~~~java
@ExtendWith(MockitoExtension.class)
class PaymentServiceTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Mock
    private PaymentRepository paymentRepository;

    @InjectMocks
    private PaymentService paymentService;
}
~~~

If there is an integration test group that genuinely needs a full context, create a dedicated annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@ActiveProfiles("integration")
@Transactional
public @interface ApplicationIntegrationTest {
}
~~~

And the class testing the broad workflow declares:

~~~java
@ApplicationIntegrationTest
class CustomerRegistrationIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private CustomerRepository customerRepository;
}
~~~

After splitting, each test class shows its required dependencies and scope. Controller tests use mocked services, repository tests use the JPA slice, service tests use Mockito, and only integration tests load the broad application.

## 12. When Does an Abstract Base Test Class Still Make Sense?

You do not need to eliminate every superclass. A base class can fit when all subclasses share a clear contract and all need a stable setup.

For example, multiple tests for implementations of the same interface can inherit a contract test suite:

~~~java
abstract class CustomerStoreContractTest {

    protected abstract CustomerStore customerStore();

    @Test
    void savesAndFindsCustomer() {
        Customer customer = CustomerFixtures.activeCustomer();

        customerStore().save(customer);

        assertEquals(
                customer,
                customerStore().findById(customer.id()).orElseThrow());
    }
}
~~~

Subclasses provide the implementation:

~~~java
class InMemoryCustomerStoreTest
        extends CustomerStoreContractTest {

    private final CustomerStore store =
            new InMemoryCustomerStore();

    @Override
    protected CustomerStore customerStore() {
        return store;
    }
}
~~~

~~~java
@DataJpaTest
class JpaCustomerStoreTest extends CustomerStoreContractTest {

    @Autowired
    private JpaCustomerStore store;

    @Override
    protected CustomerStore customerStore() {
        return store;
    }
}
~~~

This is purposeful inheritance: the superclass contains the same suite of behaviors to verify for every implementation. Subclasses only supply the object under test.

A reasonable base class typically has these traits:

- Has a single responsibility, described by its name.
- Subclasses genuinely need almost all of its setup and lifecycle.
- Contains no dependencies from unrelated domains.
- Needs no multiple flags to disable individual features.
- Does not require subclasses to override many methods to alter default behavior.
- Its context scope is understandable from annotations on the parent class or a clearly named composed annotation.

### A Base Class Can Hold Test Contracts

A contract test suite for repositories, serializers, or adapters can be a good use of inheritance. Shared test methods verify the same contract; each subclass simply supplies the required implementation or fixture.

Do not use the same pattern for a superclass meant solely to collect every convenient bean in the application.

## 13. How to Design Maintainable Composed Annotations

A good composed annotation should answer three questions:

1. Which scope does the test belong to?
2. Which configuration is always needed for that scope?
3. Do annotation users need to customize any parameters?

Example annotation for controller tests:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@Import({
        ApiExceptionHandler.class,
        ApiWebTestConfiguration.class
})
@ActiveProfiles("web-test")
public @interface ApiControllerTest {

    @AliasFor(
            annotation = WebMvcTest.class,
            attribute = "controllers")
    Class<?>[] controllers() default {};
}
~~~

This annotation has one scope: MVC controllers. The supporting beans are the exception handler and web test configuration. Users can specify controllers via the alias.

Another annotation can represent integration tests:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface FullApplicationMvcTest {
}
~~~

Do not put every profile, mock, repository, service, and helper into a single annotation. When a test needs extra per-class dependencies, declare `@MockitoBean` or `@Import` on that class so the difference is visible.

### Should Composed Annotations Be Marked `@Inherited`?

Only add `@Inherited` when you want subclasses to automatically receive the annotation from superclasses and that holds true for every intended inheritance case.

If the annotation is used directly on individual test classes, `@Inherited` is unnecessary. If there is a contract test base class and every subclass must share the same test environment, you can consider it. Remember Java's `@Inherited` only applies via superclasses, not via interfaces, and does not govern method annotations.

For Spring test annotations, you must also consider Spring's annotation search mechanism and inheritance attributes. Do not add `@Inherited` mechanically to cascade every configuration down to subclasses.

## 14. Keep Dependencies Explicit in the Test Class

A readable test class should reveal the main dependencies it uses.

Example:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsOrderWhenFound() throws Exception {
        // ...
    }
}
~~~

Just looking at the declarations shows the test needs `MockMvc` and replaces `OrderService` with a mock. If dependencies sit in a deep superclass, readers have to open more files to understand the test.

For helpers, you can instantiate them directly:

~~~java
private final OrderRequestFactory requestFactory =
        new OrderRequestFactory();
~~~

If a helper needs a dependency:

~~~java
private OrderRepositoryFixtures fixtures;

@BeforeEach
void setUp() {
    fixtures = new OrderRepositoryFixtures(orderRepository);
}
~~~

Or use a fixture bean if it needs to be managed by Spring. Either way, dependencies should appear at the point of use or in a clearly named configuration.

### Do Not Overuse Test Class Constructors

JUnit Jupiter supports constructor injection via `ParameterResolver`, and `SpringExtension` can supply dependencies to a test constructor when configured properly. However, putting too many parameters into a test class constructor can make the dependency list hard to read.

Use constructor or method parameter injection when it clarifies dependencies and fits the project's JUnit/Spring setup. Field injection in tests is also acceptable; what to avoid is hiding dependencies in a superclass without reason.

## 15. Avoid Conditional Setup and Many Hooks in Base Classes

One sign a superclass has taken on too many responsibilities is having flags like:

~~~java
abstract class AbstractTest {

    protected boolean cleanDatabase = true;
    protected boolean startMockServer = true;
    protected boolean createDefaultCustomer = true;
    protected boolean enableSecurity = true;

    @BeforeEach
    void setUp() {
        if (cleanDatabase) {
            // ...
        }
        if (startMockServer) {
            // ...
        }
        if (createDefaultCustomer) {
            // ...
        }
        if (enableSecurity) {
            // ...
        }
    }
}
~~~

Every subclass must know which flags to disable. Changing a default can alter the behavior of many tests without any clue inside the test method.

Instead of flags, split configuration by purpose:

- Tests needing database cleanup use dedicated database fixtures or extensions.
- Tests needing a mock server register a mock server extension or explicit configuration.
- Tests needing security use a security test configuration.
- Tests needing a default customer call `CustomerFixtures`.
- Tests not needing a component do not load it.

If multiple behaviors truly always go together, group them in a composed annotation or an extension whose name expresses the full responsibility.

## 16. Context Caching and the Impact of Shared Configuration

The Spring TestContext Framework can reuse an `ApplicationContext` when tests have equivalent configuration. Using composed annotations helps a group of tests share one stable configuration, thereby supporting the context cache.

However, a large base class can introduce many configuration variations:

- Multiple profiles.
- Multiple property sources.
- Multiple initializers.
- Multiple bean overrides.
- Multiple imported configurations.
- Multiple context hierarchies.

Tests that do not need the same scope may still be forced to share a huge configuration, or per-subclass configurations may fragment the context cache.

Keep shared configuration stable within a group of tests sharing the same goal. If two test groups need different contexts, use two composed annotations or two separate test configurations. Do not force them into one base class just to save a few lines of annotations.

### `@DirtiesContext` Is Not a Substitute for Fixture Design

If a superclass uses `@DirtiesContext` to work around state leaks, identify where that state belongs:

- Mutable singleton bean: may need resetting or a separate context.
- Database rows: transaction rollback or data cleanup.
- Temporary files: delete files according to lifecycle.
- Mock server: shut down server or reset expectations.
- System properties: save and restore values.
- Static fields: avoid shared state or restore explicitly.

`@DirtiesContext` evicts the context from the cache according to the specified mode. It does not automatically clean databases, files, or external services. Putting this annotation on a superclass can impose context restart costs on every subclass.

## 17. Process for Shrinking a Growing Test Superclass

When a base class already has many fields and annotations, migrate gradually by test group.

### Step 1: List Subclasses and What They Actually Use

For each subclass, record:

- Inherited class-level annotations.
- Injected beans and which fields are actually used.
- Which lifecycle callbacks run.
- Which helpers are called.
- Which external resources are opened.
- Which transactions or profiles are active.

The goal is to see what is genuinely shared versus what serves only a few subclasses.

### Step 2: Group by Risk

For example:

- Controller tests need the MVC slice.
- Repository tests need the JPA slice.
- Service tests need unit tests with Mockito.
- Integration tests need a full context.
- Configuration tests need a small context with real beans.

Do not group by package name or because tests happen to use the same repository.

### Step 3: Turn Shared Configuration into Composed Annotations

Create an annotation for each group sharing the same bootstrap and profile. Use `@AliasFor` if annotation users need to pass controllers or corresponding parameters.

### Step 4: Turn Fixtures into Factories or Builders

Move plain Java DTO/entity creation out of the superclass. Split fixtures needing a database into helpers receiving the repository explicitly.

### Step 5: Turn Lifecycle Behavior into Extensions When Appropriate

If cleanup or setup is an independent utility, create a JUnit Extension. If it is only a few lines of setup, keep it inside the test class.

### Step 6: Make Dependencies Visible in the Test Class

Declare `@Autowired`, `@MockitoBean`, `@Import`, or fixture factories in the test class. Keep the superclass only for truly shared test contracts.

### Step 7: Remove No-Longer-Needed Hooks and Flags

Once subclasses declare their own configuration and fixtures, remove unused overridden methods, boolean flags, and helpers from the base class. Ensure no test still implicitly relies on an old callback before removing it.

### Step 8: Verify Each Test Scope Separately

Run the corresponding test group after changes. An MVC slice must check request mapping; a JPA slice needs real queries; unit tests verify service behavior; integration tests verify wiring and infrastructure. Results from one group do not replace another.

## 18. Common Mistakes When Reusing Annotations and Base Classes

### A Composed Annotation with Too Many Purposes

An annotation named `@CommonTest` might bundle profiles, database, web, security, mocks, transactions, and cleanup. Readers cannot tell what environment it creates.

Name annotations after a specific scope such as `@ApiControllerTest` or `@JpaRepositoryTest`.

### Superclass Exists Just to Provide One Field

If a subclass extends solely to get `MockMvc` or a fixture, consider declaring the dependency directly or creating a small helper. There is no need for an inheritance tree for one dependency.

### Superclass Contains Many Unrelated Beans

Every child test inherits extra dependencies and can fail due to out-of-scope beans. Switch to slices or small configurations.

### Overriding Setup to Disable Superclass Behavior

If many subclasses must override setup methods, the superclass is imposing behavior that is not truly shared. Split setup into extensions or explicitly invoked fixtures.

### Using `@Inherited` Without Understanding Its Scope

`@Inherited` only affects class-level annotations through superclasses. It does not make annotations on interfaces or methods automatically inherited. Spring also has its own meta-annotation search and inheritance attributes.

### Composed Annotation Hiding Too Much Configuration

Composed annotations reduce repetition, but if one includes too many configurations and mocks, readers still do not know what the test actually depends on. Keep annotations small, name them by scope, and leave specific dependencies on the test class.

### Mixing `@WebMvcTest` with `@SpringBootTest`

The two annotations have different bootstrap approaches. Pick one clear scope: MVC slice or full context with `@AutoConfigureMockMvc`.

### Using a Base Class to Reuse Data

Data fixtures usually do not need inheritance. Use factories, builders, or object mothers with valid default values.

### Assuming the Same Annotation Means the Same Behavior

A composed annotation can have aliased attributes or overridden configuration. Two classes using the same annotation while supplying different properties, profiles, or bean overrides can produce different contexts. Inspect the actual configuration when a test depends on bean selection.

## 19. Table for Choosing a Reuse Mechanism

| Scenario | Mechanism to Consider | Reason |
|---|---|---|
| Many controller tests share MVC configuration | Composed annotation | Clearly marks the test slice and web configuration |
| Many repository tests use the JPA slice | Composed annotation or standard annotation directly | Keeps the context at the persistence boundary |
| Many tests need the same support bean | @TestConfiguration + @Import | Dependencies are loaded intentionally |
| Many tests create the same sample objects | Fixture factory/builder | Needs neither Spring nor inheritance |
| Many tests need the same cleanup lifecycle | JUnit Extension | Separates lifecycle behavior from superclass |
| Many implementations must follow one contract | Abstract contract test | Shares meaningful test methods |
| A group of integration tests shares identical config | Composed integration annotation | Clearly reuses full-context configuration |
| Tests merely happen to share a few dependencies | Declare dependencies on each test | Avoids hidden coupling and overly broad contexts |

## 20. Checklist for Designing Reusable Annotations

When creating a composed annotation or superclass, ask yourself:

1. Does this annotation represent a specific testing scope?
2. Does every test using it genuinely need the same configuration?
3. Are any beans or filters loaded that are unrelated to the goal?
4. Do subclasses have to override hooks or disable flags to avoid unnecessary setup?
5. Are the primary dependencies visible from the test class?
6. Does the annotation combine conflicting bootstrap mechanisms?
7. Is `@AliasFor` used properly with meta-annotation attributes?
8. Is `@Inherited` actually needed?
9. Can the test run independently without reading multiple superclass layers?
10. Can maintainers tell which risk the test verifies just from annotations, fixtures, and assertions?

A good design makes the test's intent clear. If readers have to trace multiple parent classes to find the context, bean overrides, and cleanup, reuse is obscuring configuration.

## 21. Example of an Easy-to-Understand Test Directory Structure

A structure can separate annotations, configurations, and fixtures as follows:

~~~text
src/test/java/
  com/example/testing/
    annotations/
      ApiControllerTest.java
      JpaRepositoryTest.java
      MvcIntegrationTest.java
    config/
      ApiWebTestConfiguration.java
      PersistenceTestConfiguration.java
      FixedClockTestConfiguration.java
    fixtures/
      CustomerFixtures.java
      OrderFixtures.java
      CustomerRepositoryFixtures.java
    extensions/
      ExecutionTimeExtension.java

  com/example/customer/
    CustomerControllerTest.java
    CustomerRepositoryTest.java
    CustomerServiceTest.java

  com/example/order/
    OrderControllerTest.java
    OrderRepositoryTest.java
    OrderWorkflowIntegrationTest.java
~~~

The exact layout depends on project size. A small module can place annotations and fixtures near the test package using them. What matters is that names and locations help readers find the configuration the test uses.

## References

- [JUnit 5 User Guide: Test Classes and Methods](https://junit.org/junit5/docs/current/user-guide/)
- [JUnit 5 User Guide: Extensions](https://junit.org/junit5/docs/current/user-guide/#extensions)
- [Spring Framework Reference: TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Framework Reference: TestContext Framework — Annotation Support](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/annotation.html)
- [Spring Framework API: AliasFor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/AliasFor.html)

## Conclusion

Large test superclasses can make dependencies, context, and lifecycle hard to see in individual tests. Reserve superclasses for contract test suites or truly shared behavior; use composed annotations to reuse a clearly scoped configuration, `@TestConfiguration` and `@Import` for support beans, fixture factories for data, and JUnit Extensions for lifecycle behavior. When dependencies and scope are shown right on the test class, readers easily understand which environment the test runs in and what its evidence means.

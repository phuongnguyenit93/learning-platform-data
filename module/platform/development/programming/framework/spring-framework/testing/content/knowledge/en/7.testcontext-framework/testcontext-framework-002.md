# Roles of TestContext, TestContextManager, and TestExecutionListener

When testing a Spring application, many behaviors must be prepared before the test method runs: creating the `ApplicationContext`, injecting dependencies into the test instance, opening a test transaction, loading SQL data, managing events, and cleaning up the context after the test finishes. If each test performed these steps manually, test code would repeat a lot of configuration and easily miss part of the lifecycle.

The **Spring TestContext Framework** provides a unified model to manage that lifecycle. The three core components to understand are:

- `TestContext`: holds information about the current test and provides access to the `ApplicationContext` along with attributes bound to the test execution.
- `TestContextManager`: coordinates the test lifecycle, creates and updates `TestContext`, and invokes listeners at each stage.
- `TestExecutionListener`: receives callbacks at lifecycle milestones to perform tasks such as dependency injection, transaction management, running SQL, or handling shared testing logic.

When using JUnit Jupiter, `SpringExtension` connects JUnit with `TestContextManager`. Understanding this relationship shows why `@Autowired`, `@Transactional`, `@Sql`, `@DirtiesContext`, and other Spring Test features work at the right moment, while also allowing you to extend the framework with custom listeners when needed.

## 1. What Problem Does the TestContext Framework Solve?

A Spring test often requires more than calling a Java method. For example, a controller test may need to:

1. Initialize a context containing controllers, services, security filters, and MVC configuration.
2. Inject `MockMvc` or dependencies into the test instance.
3. Prepare data before calling an endpoint.
4. Run a request through the Spring MVC pipeline.
5. Record exceptions or test results.
6. Clean up data or close the context if the test alters application state.

The TestContext Framework standardizes those steps into a callback-driven lifecycle. As a result, extensions can participate at the right stage without knowing the internal details of the runner or test framework controlling execution.

The framework is designed to integrate with multiple testing platforms. JUnit Jupiter uses `SpringExtension`; JUnit 4 has `SpringRunner` (class name `SpringJUnit4ClassRunner`); other integrations may use their own mechanisms. Most examples in this article use JUnit Jupiter as it is the common choice in modern Spring projects.

The TestContext Framework belongs to Spring Test. It can be used in plain Spring Framework applications as well as in Spring Boot. Spring Boot provides convenient annotations such as `@SpringBootTest`, `@WebMvcTest`, and `@DataJpaTest`, but the underlying TestContext lifecycle is still managed by Spring Test.

## 2. The Three Core Components and Their Relationships

### `TestContext`

`TestContext` represents the test execution context. It provides information such as:

- The class containing the test.
- The current test instance.
- The current test method.
- Any exception thrown during execution, if present.
- The `ApplicationContext` associated with the test.
- An attribute store for listeners to save and share data across the test lifecycle.

Listeners receive a `TestContext` object in callbacks. From it, a listener can determine which test is running, access beans, or store information needed in subsequent callbacks.

`TestContext` is an abstraction; Spring's default implementation is `DefaultTestContext`. Using the interface keeps listeners less coupled to how Spring stores internal state.

### `TestContextManager`

`TestContextManager` coordinates the lifecycle for a test class. It creates or obtains the `TestContext`, manages the list of `TestExecutionListener` instances, and invokes corresponding callbacks when the test framework signals start and end milestones.

The manager also collaborates with the bootstrap mechanism to determine how to create the context, the context loader, and listeners. Normally you do not need to instantiate the manager directly in tests; Spring's extension or runner handles it.

### `TestExecutionListener`

`TestExecutionListener` is the extension point for participating in the test lifecycle. A listener can run before or after milestones such as preparing the test instance, before a method, after a method, and after the entire class.

Spring includes default listeners to provide many familiar features. For example, the dependency injection listener injects dependencies into the test instance; the transaction listener manages test transactions; the SQL scripts listener executes scripts declared with `@Sql`; and the dirties context listener handles contexts marked for cache eviction.

Overview diagram:

```text
JUnit Jupiter
    |
    v
SpringExtension
    |
    v
TestContextManager
    |              \
    |               +--> TestExecutionListener A
    |               +--> TestExecutionListener B
    |               +--> TestExecutionListener C
    |
    v
TestContext
    |-- test class / instance / method / exception
    |-- ApplicationContext
    +-- attributes used during the test lifecycle
```

`SpringExtension` is the bridge to JUnit; `TestContextManager` coordinates; `TestContext` carries information; and listeners perform work at each stage.

## 3. Callback Lifecycle of TestContext

The TestContext Framework divides execution into milestones. Common `TestExecutionListener` callbacks include:

| Callback | Timing | Suitable Work |
| --- | --- | --- |
| `beforeTestClass` | Before starting the test class | Prepare class-level resources or record the start of a small suite |
| `prepareTestInstance` | After the test instance is created, before running setup methods | Inject dependencies or prepare the test instance |
| `beforeTestMethod` | Before the test method and before the corresponding JUnit setup methods | Prepare per-method data, open a test transaction |
| `beforeTestExecution` | Immediately before executing the test method body | Start timing or record execution timestamp |
| `afterTestExecution` | Immediately after the test method body, before teardown methods | Collect results, duration, or exceptions from the test body |
| `afterTestMethod` | After completing the test method and corresponding teardown | Roll back transaction, clean up data according to policy |
| `afterTestClass` | After completing all test methods of the class | Clean up class-level resources or record completion |

Callback names describe TestContext milestones. Actual execution order when integrating with JUnit also relates to the callbacks implemented by the extension and JUnit's lifecycle order.

### Order When Using JUnit Jupiter

`SpringExtension` implements JUnit Jupiter callbacks and forwards them to `TestContextManager`. You can visualize the sequence as follows:

```text
BeforeAllCallback
    -> TestContextManager.beforeTestClass()

TestInstancePostProcessor
    -> TestContextManager.prepareTestInstance()

BeforeEachCallback
    -> TestContextManager.beforeTestMethod()

@BeforeEach of the test author

BeforeTestExecutionCallback
    -> TestContextManager.beforeTestExecution()

Body of @Test

AfterTestExecutionCallback
    -> TestContextManager.afterTestExecution()

@AfterEach of the test author

AfterEachCallback
    -> TestContextManager.afterTestMethod()

AfterAllCallback
    -> TestContextManager.afterTestClass()
```

This diagram helps identify the right place for logic. For instance, dependency injection for the test instance must occur before `@BeforeEach`, whereas measuring only the execution time of the test body should start at `beforeTestExecution` and end at `afterTestExecution`.

In JUnit Jupiter, Spring's `beforeTestMethod` callback is invoked during `BeforeEachCallback`, before `@BeforeEach` methods declared by the test author. The `beforeTestExecution` callback is invoked after setup methods and immediately before the test body. Conversely, `afterTestExecution` occurs after the test body and before `@AfterEach`; `afterTestMethod` is called after the corresponding teardown methods.

These milestones matter when using `@Transactional`, `@Sql`, or custom listeners. For example, to measure only the method execution time, measure from `beforeTestExecution` to `afterTestExecution`; to include fixture preparation and teardown, choose broader milestones.

## 4. What Information Does TestContext Hold?

A listener does not need to maintain a global variable to know which test is running. It receives `TestContext` and accesses information through the interface's methods.

Example:

```java
public class TestInformationListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        Class<?> testClass = testContext.getTestClass();
        Method testMethod = testContext.getTestMethod();
        Object testInstance = testContext.getTestInstance();

        System.out.printf(
            "Starting %s#%s on %s%n",
            testClass.getSimpleName(),
            testMethod.getName(),
            testInstance.getClass().getSimpleName()
        );
    }
}
```

This example illustrates reading test information. In a real application, use the project's logger instead of `System.out` so logs are structured and filterable by level.

`TestContext` also provides `getApplicationContext()` to retrieve the context being used for the test. A listener can fetch a bean from the context if it truly needs to interact with a Spring component:

```java
@Override
public void beforeTestMethod(TestContext testContext) {
    ApplicationContext applicationContext = testContext.getApplicationContext();
    TestAuditRecorder recorder = applicationContext.getBean(TestAuditRecorder.class);

    recorder.recordStarted(
        testContext.getTestClass(),
        testContext.getTestMethod()
    );
}
```

Access the context only when the listener actually needs a bean. Calling `getApplicationContext()` can trigger context loading if it has not been created yet. A listener applied to every test should not inadvertently force lightweight tests to boot the entire application.

## 5. How Do TestContext and ApplicationContext Differ?

These two names are easily confused, yet they represent two distinct kinds of context:

| Object | Represents | Typical Contents |
| --- | --- | --- |
| `ApplicationContext` | The Spring application container | Beans, environment, events, resources, and configuration |
| `TestContext` | The context of the test execution | Test class, instance, method, exception, ApplicationContext, and attributes |

An `ApplicationContext` can be reused by multiple test classes via the context cache. Each test class has a TestContext lifecycle coordinated by its corresponding manager. TestContext references the ApplicationContext needed for the test.

For example, `OrderService` is a bean in `ApplicationContext`; `OrderServiceTest` is the test class; and `createsOrderWhenPaymentIsApproved()` is the current test method. A listener can read the method from `TestContext` and then obtain `OrderService` from `ApplicationContext`.

Do not use `TestContext` as a substitute for application business data. It is test-support infrastructure, whereas order, customer, or transaction state belongs to the corresponding application components and database.

## 6. How Does TestContextManager Coordinate?

`TestContextManager` is created for a test class through Spring's integration with the test framework. The manager coordinates the following components:

- The bootstrapper determines the TestContext configuration, context loader, and listeners.
- TestContext holds information about the current test.
- The list of `TestExecutionListener` instances receives callbacks.
- The `ApplicationContext` loading and caching mechanism supplies the context for the test.

In JUnit Jupiter, `SpringExtension` typically creates or retrieves `TestContextManager` from the extension context store so callbacks for the same test class share the manager across the appropriate lifecycle.

You can think of the manager as a lifecycle event coordinator. It is not a business service, does not replace JUnit, and is not an ApplicationContext. Most projects only need to use the extension/runner provided by Spring without calling the manager's methods directly.

### Bootstrapper

`TestContextBootstrapper` is responsible for initializing the TestContext configuration. The default bootstrapper is `DefaultTestContextBootstrapper`; for web tests there may be a specialized bootstrapper. The `@BootstrapWith` annotation lets you choose a custom bootstrapper when a project needs to alter how TestContext is built.

Normally, Spring Boot's test annotations already declare the appropriate bootstrap mechanism. Only customize the bootstrapper when you need to change how the framework creates contexts or constructs the listener set at the test-platform level.

### Context Loader and Context Cache

The context loader is responsible for loading the `ApplicationContext` from the test configuration. Spring Test uses a caching mechanism to reuse contexts with equivalent configuration across test classes, reducing startup cost.

Factors such as context configuration, profiles, properties, initializers, context customizers, and certain annotations can affect the cache key. When a test dirties the context and uses `@DirtiesContext`, the corresponding listener instructs the framework to evict the context from the cache according to the annotation's policy.

This explains why a test can run quickly when its context has already been created by an earlier test, yet run significantly slower when executed in isolation. It also explains why listeners should not arbitrarily close the context or hold references to beans after the context has been evicted from the cache.

## 7. What Is TestExecutionListener?

`TestExecutionListener` is a Spring Test interface located in the `org.springframework.test.context` package. It defines callbacks for stages in the test lifecycle.

Main callbacks:

```java
public interface TestExecutionListener {

    default void beforeTestClass(TestContext testContext) throws Exception { }

    default void prepareTestInstance(TestContext testContext) throws Exception { }

    default void beforeTestMethod(TestContext testContext) throws Exception { }

    default void beforeTestExecution(TestContext testContext) throws Exception { }

    default void afterTestExecution(TestContext testContext) throws Exception { }

    default void afterTestMethod(TestContext testContext) throws Exception { }

    default void afterTestClass(TestContext testContext) throws Exception { }
}
```

This is a simplified form to illustrate the callbacks; refer to the API of the Spring version in use when writing an actual listener. Modern versions of Spring provide `AbstractTestExecutionListener` so you do not have to implement every method yourself.

A listener should have a narrow responsibility, such as recording timing, preparing shared data, or integrating an internal testing mechanism. If a listener initializes the database, creates users, checks permissions, and writes logs all at once, it becomes hard to reuse and hard to troubleshoot.

## 8. Spring's Default Listeners

Spring registers a set of default listeners to provide common testing features. The exact list may vary by Spring version and application type, but typical responsibilities include:

| Listener | Role |
| --- | --- |
| `ServletTestExecutionListener` | Prepares request/response infrastructure for certain web tests |
| `DirtiesContextBeforeModesTestExecutionListener` | Processes `@DirtiesContext` modes before the test method |
| `ApplicationEventsTestExecutionListener` | Prepares and manages recording of application events in tests |
| `DependencyInjectionTestExecutionListener` | Injects dependencies into the test instance |
| `DirtiesContextTestExecutionListener` | Marks or evicts the context when a test dirties the context |
| `TransactionalTestExecutionListener` | Manages test transactions for tests annotated with `@Transactional` |
| `SqlScriptsTestExecutionListener` | Executes SQL scripts declared with `@Sql` |
| `EventPublishingTestExecutionListener` | Publishes test lifecycle events in Spring Test's event mechanism |
| `MockitoResetTestExecutionListener` | Resets Mockito mocks/spies according to the supported configuration of the corresponding Spring version |

Do not rely on the ordering or presence of a specific listener without checking the framework version. Spring may add new listeners or change integrations over time. When diagnosing issues, inspect the actual list of listeners used by `TestContextManager` in your project's version.

### Dependency Injection for the Test Instance

Example:

```java
@SpringBootTest
class OrderServiceIntegrationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void createsOrder() {
        // Dependencies have already been injected before the test runs
    }
}
```

`DependencyInjectionTestExecutionListener` participates in preparing the test instance. Thanks to this, the test class can use `@Autowired` just like an application bean.

### Transactional Listener

```java
@SpringBootTest
@Transactional
class OrderTransactionTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInsideTestTransaction() {
        // Operations inside the test transaction
    }
}
```

`TransactionalTestExecutionListener` works with `@Transactional` to manage test transactions according to Spring Test configuration. By default, test transactions are typically rolled back after the method. Commit/rollback behavior can be controlled with supporting annotations like `@Commit`, `@Rollback`, or `TestTransaction` where appropriate.

Do not assume that a test's transaction always represents a production transaction. A test may run inside an outer transaction that rolls back at the end, whereas production services may open transactions via proxies or run on different threads. Design dedicated integration tests if you need to prove commit behavior, propagation, or post-commit processing.

### SQL Scripts Listener

`SqlScriptsTestExecutionListener` supports `@Sql` to run scripts before or after a test:

```java
@SpringBootTest
@Sql(scripts = "/sql/orders-test-data.sql", executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class OrderQueryTest {

    @Autowired
    OrderRepository repository;

    @Test
    void findsOrdersForCustomer() {
        // Data prepared by the SQL script
    }
}
```

The listener coordinates script execution timing with the test lifecycle. Ensure scripts are compatible with the schema and the test's transaction. If a script has side effects that cannot be rolled back, a separate cleanup strategy is needed.

## 9. SpringExtension Connects JUnit Jupiter to TestContextManager

With JUnit Jupiter, the common integration is `SpringExtension`:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class CustomerServiceTest {

    @Autowired
    CustomerService customerService;

    @Test
    void findsCustomerById() {
        // ...
    }
}
```

`SpringExtension` implements JUnit Jupiter extension callbacks and forwards them to `TestContextManager`. It also supports resolving test method and lifecycle method parameters from the Spring context when appropriate.

In Spring Boot, many test annotations already include `SpringExtension` via meta-annotation. Example:

```java
@SpringBootTest
class ApplicationIntegrationTest {
    // SpringExtension is already registered by the test annotation
}
```

Therefore, with typical `@SpringBootTest`, `@WebMvcTest`, or `@DataJpaTest` usage, you do not need to add `@ExtendWith(SpringExtension.class)` again. For tests using plain `@ContextConfiguration` and JUnit Jupiter, registering the extension is required to activate Spring Test integration.

### What Does SpringExtension Support?

Besides forwarding callbacks, the extension also supports:

- Preparing the test instance so Spring can inject dependencies.
- Resolving parameters obtainable from the Spring context or TestContext.
- Integrating Spring's test annotations with JUnit Jupiter.
- Managing callbacks before and after test methods according to the lifecycle described above.

This enables test authors to use familiar annotations without calling the manager or listeners directly.

## 10. Registering Custom Listeners

When a project needs shared behavior at a milestone in the test lifecycle, you can create a custom listener by extending `AbstractTestExecutionListener`.

Example recording the start and end time of a test method:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestTimingListener extends AbstractTestExecutionListener {

    private static final String START_TIME =
        TestTimingListener.class.getName() + ".startTime";

    @Override
    public void beforeTestExecution(TestContext testContext) {
        testContext.setAttribute(START_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(TestContext testContext) {
        Object value = testContext.getAttribute(START_TIME);
        if (value instanceof Long startTime) {
            long elapsedNanos = System.nanoTime() - startTime;
            System.out.printf(
                "%s#%s took %d ms%n",
                testContext.getTestClass().getSimpleName(),
                testContext.getTestMethod().getName(),
                elapsedNanos / 1_000_000
            );
            testContext.removeAttribute(START_TIME);
        }
    }
}
```

The listener uses a `TestContext` attribute to store the start time and reads it back in the ending callback. This avoids using a mutable static variable to share timing across tests. The example uses `System.out` for brevity; in a real project, use a logger.

Register the listener with `@TestExecutionListeners`:

```java
@SpringBootTest
@TestExecutionListeners(
    listeners = TestTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class OrderIntegrationTest {

    @Test
    void createsOrder() {
        // ...
    }
}
```

`MERGE_WITH_DEFAULTS` instructs Spring to combine the custom listener with the default listeners. This is usually the right choice when adding a listener while still needing dependency injection, transactions, SQL scripts, and default features.

## 11. Why Pay Attention to `mergeMode` and Default Listeners?

When declaring `@TestExecutionListeners`, how the custom listener merges with the default list is critical.

Two modes to distinguish:

- `MERGE_WITH_DEFAULTS`: adds declared listeners to the default list. Default listeners are preserved and Spring sorts the list according to ordering rules.
- `REPLACE_DEFAULTS`: replaces the default list with the declared listeners. Use only when intentionally managing all listeners yourself.

For example, if you replace all default listeners and forget `DependencyInjectionTestExecutionListener`, `@Autowired` fields in the test instance may not be injected. If you omit `TransactionalTestExecutionListener`, test transactions may not be managed as expected. If you omit the `@Sql` listener, scripts will not run as declared.

In modern Spring versions, `@TestExecutionListeners` also has an `inheritListeners` attribute to control listeners inherited from a parent class or meta-annotation configuration. Consider both `inheritListeners` and `mergeMode` when a test class sits in a multi-level inheritance hierarchy.

Normally, adding a custom listener should use `MERGE_WITH_DEFAULTS`. Use `REPLACE_DEFAULTS` only with a specific reason, clear understanding of which default capabilities are removed, and manual provision of the required functionality.

## 12. Listener Execution Order

When multiple listeners exist, ordering can affect outcomes. For example, a listener that prepares data must run before a listener that reads data; a listener that records results may need to run after a listener that performs assertions or captures exceptions.

Spring sorts listeners via its ordering mechanism, based on `Ordered` or the `@Order` annotation when supported. Before-callbacks are typically invoked in listener order; after-callbacks are invoked in reverse order to form a matching enter-exit structure.

You can specify order with `Ordered`:

```java
public class PrepareFixtureListener extends AbstractTestExecutionListener
        implements Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void beforeTestMethod(TestContext testContext) {
        // Prepare fixture before listeners with a higher order
    }
}
```

With listeners that have different orders, choose order values by contract and document the reason. Avoid relying on undocumented default ordering or on class declaration order in an annotation array when the framework has its own sorting mechanism.

Do not create multiple listeners with circular dependencies. If listener A needs data created by B while B needs results produced by A, consolidate the responsibilities into a single component with clear ordering or redesign the shared data.

## 13. Storing Data Between Callbacks with TestContext Attributes

`TestContext` provides `getAttribute`, `setAttribute`, `removeAttribute`, and access to the attribute set. A listener can use this space to pass information from an earlier callback to a later callback.

Example of a listener storing an ID created before the test method:

```java
public class FixtureListener extends AbstractTestExecutionListener {

    private static final String CUSTOMER_ID =
        FixtureListener.class.getName() + ".customerId";

    @Override
    public void beforeTestMethod(TestContext testContext) {
        testContext.setAttribute(CUSTOMER_ID, "customer-test-42");
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        String customerId = (String) testContext.getAttribute(CUSTOMER_ID);
        // Use the ID to clean up if the listener truly owns this fixture
        testContext.removeAttribute(CUSTOMER_ID);
    }
}
```

Namespace attribute keys using the listener class name to avoid collisions with other listeners. Check for null or type compatibility before casting if an attribute might not be created in every branch.

Attributes are suited for small data tied to the test lifecycle. Do not use them as a global cache, a store for large entities, or a means to pass state between unrelated test methods. Data shared across tests should be managed via fixtures, a database, or a dedicated mechanism with a clear lifecycle.

## 14. Registering Global Listeners via Default Discovery

Besides declaring listeners in `@TestExecutionListeners`, Spring Test supports discovering default listeners through `SpringFactoriesLoader`. In many Spring versions, default listeners are declared in `META-INF/spring.factories` under the key corresponding to `TestExecutionListener`.

This mechanism suits testing libraries that want to supply a listener to many test classes without adding annotations to each class. However, adding a listener to the default list has broad scope and can affect every test using TestContext on the classpath.

When creating a shared library:

- Register a listener only if it is broadly useful and causes no unintended side effects.
- Keep callbacks fast, idempotent when run repeatedly, and safe when tests fail.
- Document how to disable or replace the listener if needed.
- Verify compatibility with the Spring versions supported by the library.
- Avoid automatically initializing external systems just because a test uses Spring Test.

If a listener serves only one module or one group of tests, registering it with `@TestExecutionListeners` is usually clearer and better scoped.

## 15. Listeners and `@DirtiesContext`

Spring caches `ApplicationContext` to reduce test execution time. If a test alters singleton bean state or context configuration in a way that makes subsequent tests unreliable, `@DirtiesContext` can be used to mark the context for cache eviction.

Example:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyConfigurationMutationTest {

    @Test
    void changesSharedConfigurationForThisTestClass() {
        // ...
    }
}
```

`DirtiesContextTestExecutionListener` works with the annotation to process the context at the right time. Modes such as before/after method or before/after class can create a large runtime difference because the context must be reloaded.

Do not use `@DirtiesContext` as a way to clean up every kind of data. It evicts the context from the cache and closes related resources according to Spring's lifecycle, but it does not replace cleanup for shared databases, external files, sent messages, or data in external services.

If a test only modifies database data, transaction rollback or fixture cleanup should usually be used. Mark a context dirty only when the state of the context itself or singleton beans has been altered to the point where it cannot be reliably restored.

## 16. Listeners and Test Transactions

`TransactionalTestExecutionListener` is a clear example of the value of callbacks. When a test is annotated with `@Transactional`, the listener coordinates with `PlatformTransactionManager` to start a transaction before the test method and end it according to rollback/commit policy.

```java
@SpringBootTest
@Transactional
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesCustomer() {
        repository.save(new Customer("customer-42"));

        assertTrue(repository.existsById("customer-42"));
    }
}
```

Normally, changes are rolled back after the test so data does not affect the next method. If an intentional commit is needed, `@Commit` or `@Rollback(false)` can be used in appropriate scenarios.

There are several cases that a test transaction cannot cover:

- Code running on another thread, such as `@Async` tasks, does not join the transaction bound to the test thread by default.
- A transaction with `REQUIRES_NEW` propagation can commit independently of the test's outer transaction.
- Data written by external systems or message brokers does not roll back automatically with the database transaction.
- A test verifying `afterCommit` will not trigger commit callbacks if the transaction rolls back at the end of the test.

When you need to verify a real commit or post-commit event, design the test with clear transaction boundaries, potentially using `TestTransaction` to intentionally end the test transaction and re-read data from a new transaction.

## 17. Listeners and `@Sql`

`@Sql` declares SQL scripts to run before or after a test method, class, or test group depending on configuration. The listener handles this annotation and executes the scripts using the appropriate datasource.

```java
@SpringBootTest
@Sql(
    scripts = "/sql/insert-customers.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Sql(
    scripts = "/sql/cleanup-customers.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD
)
class CustomerSearchIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void findsCustomerByEmail() {
        assertTrue(repository.findByEmail("customer@example.test").isPresent());
    }
}
```

The pre-test script creates data; the post-test script cleans up data. If the test runs inside a rolled-back transaction, understand whether the script runs inside or outside the transaction according to `@SqlConfig` and the transaction manager. Do not assume a cleanup script is always needed if rollback already covers the changes; conversely, rollback will not undo side effects outside the transaction.

## 18. Writing a Custom Listener to Check Metadata or Common Rules

A listener can enforce common rules across multiple test classes. For example, a listener can require tests to follow a naming or metadata convention, log diagnostic information, or prepare a shared fixture.

```java
public class TestMetadataListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        Method method = testContext.getTestMethod();

        if (method.isAnnotationPresent(RequiresExternalService.class)) {
            String endpoint = System.getenv("EXTERNAL_SERVICE_URL");
            if (endpoint == null || endpoint.isBlank()) {
                throw new IllegalStateException(
                    "EXTERNAL_SERVICE_URL is required for this test"
                );
            }
        }
    }
}
```

The example assumes the project has a `@RequiresExternalService` annotation. The listener checks configuration before the test runs and fails clearly if a required dependency is not provided. If the dependency is optional, consider using a condition or assumption instead of failing every test.

In practice, avoid turning a listener into a container for all test rules. Rules specific to a single test should usually live inside that test or a specialized extension. A shared listener should only hold behavior that is meaningful across many test classes.

## 19. Testing Custom Listeners

A listener is also code and needs to be tested. Small behaviors can be unit tested by mocking `TestContext` or creating a suitable test context, then verifying that the listener reads/writes attributes and invokes collaborators correctly.

Example testing a listener that writes an attribute:

```java
@ExtendWith(MockitoExtension.class)
class FixtureListenerTest {

    @Mock
    TestContext testContext;

    @Test
    void storesCustomerIdBeforeTestMethod() {
        FixtureListener listener = new FixtureListener();

        listener.beforeTestMethod(testContext);

        verify(testContext).setAttribute(
            contains("customerId"),
            eq("customer-test-42")
        );
    }
}
```

This is an illustrative example; if the attribute key is a private constant, tests can verify via interactions or public behavior chosen by the team. Do not widen visibility solely to test an internal constant.

Beyond unit testing the listener, include at least one small integration test registering the listener via `@TestExecutionListeners` to prove the framework actually invokes callbacks at the right time. A unit test only proves the listener's logic; it does not prove the listener is discovered or registered properly.

## 20. Common Mistakes When Using the TestContext Framework

- **Forgetting to register `SpringExtension`:** a test uses `@ContextConfiguration` without the JUnit Jupiter extension, so Spring does not inject dependencies and callbacks do not run.
- **Registering a listener and unintentionally replacing the default list:** loses dependency injection, transactions, or the SQL listener.
- **Using the wrong callback:** preparing fixtures after the test body has started or cleaning up before assertions complete.
- **Accessing ApplicationContext too early:** a listener forces lightweight tests to load the entire context.
- **Holding state in static variables:** tests running in parallel or in different orders can leak state.
- **Using `@DirtiesContext` to clean up all data:** context cache and database are two different kinds of state.
- **Assuming test transactions roll back every side effect:** messages, emails, HTTP requests, and transactions on other threads do not roll back automatically.
- **Ignoring listener order:** a listener reads data before another listener finishes preparing it.
- **Giving a listener too many responsibilities:** callbacks become unpredictable, hard to test, and couple all tests to shared infrastructure.
- **Not checking skipped tests or uncreated contexts:** the pipeline may not provide the evidence the team assumes it has.

## 21. When to Use a Listener vs. a JUnit Extension?

A JUnit Jupiter extension is JUnit's extension mechanism. `TestExecutionListener` is Spring TestContext's extension mechanism. Both can coexist in a test, participating at different layers.

| Need | Typically Suitable Mechanism |
| --- | --- |
| Integrating Spring callbacks, managing contexts, transactions, or dependency injection | TestContext Framework and `TestExecutionListener` |
| Adding behavior tied to JUnit Jupiter without needing a Spring context | JUnit Jupiter extension |
| Parameterization, enable/disable conditions, or JUnit-specific lifecycle | JUnit Jupiter annotations and extensions |
| Injecting beans or coordinating with `ApplicationContext` in tests | SpringExtension and TestContext Framework |
| Sharing logic across multiple test frameworks via Spring Test | `TestExecutionListener` when the logic truly belongs to the TestContext lifecycle |

If the logic does not require `ApplicationContext` or TestContext, a JUnit extension is usually leaner. If the logic needs to know the test class, test method, Spring context, and must run alongside default listeners, `TestExecutionListener` is the right extension point.

Do not register the same behavior in both a JUnit extension and a TestExecutionListener without a clear reason, as callbacks may run twice and cause duplicate side effects.

## 22. Diagnostic Process When Callbacks Do Not Run as Expected

When `@Autowired`, `@Sql`, transactions, or a custom listener do not work, verify in sequence:

1. **Test framework:** is the test running on JUnit Jupiter, JUnit 4, or another platform?
2. **Integration adapter:** is `SpringExtension` or the appropriate runner registered? Does the Spring Boot annotation register the extension automatically?
3. **Bootstrap:** is the context configured via `@ContextConfiguration`, `@SpringBootTest`, or a corresponding annotation?
4. **Listener list:** are default listeners still present? Is `@TestExecutionListeners` merging or replacing?
5. **Lifecycle point:** which callback contains the logic, and does that callback occur before or after setup/teardown methods?
6. **Ordering:** does the listener run before the listener that supplies the data or dependency it needs?
7. **Context state:** is the context cached, marked dirty, or reloaded?
8. **Transaction:** which transaction and thread is the test running on, and are side effects inside or outside the transaction?

You can enable appropriate logging for the Spring Test package to observe bootstrapping, context loading, and callbacks. Use an adequate log level during diagnostics and avoid leaving overly verbose logs across the entire pipeline if it makes reports hard to read.

## 23. Summary of Roles in a Spring Test

When a Spring test starts, the test framework invokes the corresponding adapter such as `SpringExtension`. The extension forwards lifecycle milestones to `TestContextManager`. The manager updates `TestContext` and calls `TestExecutionListener` instances in the appropriate order. Default listeners inject dependencies, manage transactions, execute SQL, or handle the context; custom listeners can add shared behavior. `ApplicationContext` supplies application beans and can be cached for reuse across tests.

Understanding these three roles clearly lets you pick the right place to prepare data, measure timing, manage transactions, or clean up. TestContext carries execution info for the test; TestContextManager coordinates the lifecycle; and TestExecutionListener performs work at each callback. SpringExtension connects that model to JUnit Jupiter, helping Spring test annotations work consistently throughout the test lifecycle.

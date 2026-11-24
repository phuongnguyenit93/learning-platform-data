# Class, Test Instance, and Test Method Lifecycle

A test in Spring is governed by two collaborating lifecycles: the JUnit Jupiter lifecycle and the test management lifecycle of the Spring TestContext Framework. JUnit creates the test instance, invokes setup and teardown methods, and executes the test method. Spring hooks into those milestones to load the ApplicationContext, inject dependencies, manage transactions, execute test SQL, and handle shared state.

Understanding these milestones accurately answers common questions: Why are `@Autowired` fields populated before `@BeforeEach` runs? Why does each test method get a new test instance while a Spring bean still retains state? Why can database data be rolled back after a test? When should `@TestInstance(PER_CLASS)` be used, and when is `@DirtiesContext` needed?

This lesson focuses on the relationship between the **test class lifecycle**, the **test instance lifecycle**, and the **individual test method lifecycle** in Spring Framework Testing.

## 1. Two Lifecycles Participating in a Single Test

JUnit Jupiter manages how test classes and test methods are executed. The Spring TestContext Framework adds the ability to prepare the Spring environment and provides callbacks for each stage of the test.

You can visualize the responsibilities as follows:

~~~text
JUnit Jupiter
    |
    +-- Create test instance
    +-- @BeforeAll / @AfterAll
    +-- @BeforeEach / @AfterEach
    +-- @Test and test invocations
    +-- Manage extension callbacks
            |
            v
SpringExtension
    |
    v
TestContextManager
    |
    +-- Prepare test instance and inject dependencies
    +-- Invoke TestExecutionListener before/after each method
    +-- Manage test transactions
    +-- Run test SQL
    +-- Manage ApplicationContext state
~~~

**JUnit** decides when a test method executes and how long a test instance lives. **Spring** supplies the context, beans, and supporting behaviors at extension points exposed by JUnit.

In JUnit Jupiter, Spring is typically integrated using one of the following annotations:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class PricingServiceTest {
}
~~~

Or using the composed annotation:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class PricingServiceTest {
}
~~~

With Spring Boot, `@SpringBootTest` already integrates `SpringExtension`:

~~~java
@SpringBootTest
class ApplicationServiceTest {
}
~~~

Therefore, when using `@SpringBootTest` or `@SpringJUnitConfig`, you normally do not need to declare `@ExtendWith(SpringExtension.class)` separately.

## 2. Lifecycle of a Test Class in JUnit Jupiter

JUnit Jupiter provides the primary annotations to mark stages of a test:

| Annotation | Timing | Purpose |
|---|---|---|
| @BeforeAll | Once before test methods in the class | Prepare class-level shared resources |
| @BeforeEach | Before each test method execution | Prepare isolated data and state for the test |
| @Test | Main execution body | Verify a single behavior |
| @AfterEach | After each test method execution | Clean up state from the test run that just finished |
| @AfterAll | Once after test methods in the class | Release class-level resources |

Simple example:

~~~java
class CalculatorTest {

    @BeforeAll
    static void beforeAll() {
        System.out.println("Prepare test class");
    }

    @BeforeEach
    void beforeEach() {
        System.out.println("Prepare test method");
    }

    @Test
    void shouldAddNumbers() {
        assertEquals(5, 2 + 3);
    }

    @Test
    void shouldMultiplyNumbers() {
        assertEquals(6, 2 * 3);
    }

    @AfterEach
    void afterEach() {
        System.out.println("Clean test method");
    }

    @AfterAll
    static void afterAll() {
        System.out.println("Release test class");
    }
}
~~~

Under JUnit Jupiter's default configuration, a new test instance is created for each test method. Consequently, `@BeforeAll` and `@AfterAll` are static in the default mode: they run at the class level, independent of any specific instance.

General sequence:

~~~text
@BeforeAll
    |
    +-- Create test instance for first method
    |       |
    |       +-- @BeforeEach
    |       +-- @Test
    |       +-- @AfterEach
    |
    +-- Create test instance for second method
    |       |
    |       +-- @BeforeEach
    |       +-- @Test
    |       +-- @AfterEach
    |
@AfterAll
~~~

The order between test methods should not be used as a mechanism for sharing state. If test B only passes after test A, the suite may fail when JUnit changes execution order or runs tests in parallel.

## 3. Test Instance Lifecycle: PER_METHOD and PER_CLASS

JUnit Jupiter offers two modes for managing test instances.

### 3.1. PER_METHOD — The Default Mode

In `PER_METHOD` mode, JUnit creates a new instance for every test method.

~~~java
class ShoppingServiceTest {

    private int callCount = 0;

    @Test
    void firstTest() {
        callCount++;
        assertEquals(1, callCount);
    }

    @Test
    void secondTest() {
        callCount++;
        assertEquals(1, callCount);
    }
}
~~~

The two test methods have two different instances. Thus, the `callCount` field is initialized fresh on each instance.

Advantages:

- Instance state is isolated between test methods.
- Less risk of one test mutating a field and causing another test to fail.
- Easy to write isolated setup per test.
- Suitable for most unit tests and integration tests.

This is the mode to keep as the default unless there is a clear reason to share a test instance.

### 3.2. PER_CLASS — One Shared Instance for the Entire Class

You can instruct JUnit to create only one test instance for the entire class using `@TestInstance`:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingServiceTest {

    private int callCount = 0;

    @BeforeAll
    void beforeAll() {
        callCount = 0;
    }

    @Test
    void firstTest() {
        callCount++;
        assertEquals(1, callCount);
    }

    @Test
    void secondTest() {
        callCount++;
        assertEquals(2, callCount);
    }
}
~~~

In this example, both test methods use the same object, so the `callCount` field is preserved across methods. `@BeforeAll` and `@AfterAll` can be instance methods without requiring `static`.

`PER_CLASS` is useful when:

- You need to create an expensive resource once for the entire class.
- You have class-level setup that needs access to injected fields or dependencies.
- Tests need a shared configuration object with a way to ensure stable state.
- You want to reduce test instance creation overhead when a class has many test methods.

However, mutable state on the test instance can leak between methods. If one test alters a list, mock, fixture object, or member variable, the next test may receive modified data.

Error-prone example:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CartTest {

    private final List<String> items = new ArrayList<>();

    @Test
    void shouldAddFirstItem() {
        items.add("BOOK");
        assertEquals(1, items.size());
    }

    @Test
    void shouldStartWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
~~~

The second test depends on whether the first test has already run. If run individually, it may pass; when running the whole class, it may fail.

If using `PER_CLASS`, proactively reset state in `@BeforeEach` or create fresh fixtures for each test method:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CartTest {

    private List<String> items;

    @BeforeEach
    void setUp() {
        items = new ArrayList<>();
    }

    @Test
    void shouldAddItem() {
        items.add("BOOK");
        assertEquals(1, items.size());
    }

    @Test
    void shouldStartWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
~~~

### 3.3. Configuring PER_CLASS at the Project Level

JUnit lets you set the default test instance lifecycle via configuration:

~~~properties
junit.jupiter.testinstance.lifecycle.default = per_class
~~~

This can be placed in a `junit-platform.properties` file on the test classpath.

This setting affects test classes that do not declare their own lifecycle. When changing the default at the project level, review all tests with mutable state because tests that previously relied on a fresh instance may begin sharing state.

In a large Spring project, choose a clear and consistent mode. If using `PER_CLASS` globally, stricter setup and cleanup discipline is required.

## 4. How Does SpringExtension Connect into JUnit's Lifecycle?

`SpringExtension` is the JUnit Jupiter extension that integrates the Spring TestContext Framework. This extension translates JUnit callbacks into calls to `TestContextManager`.

Important callbacks include:

| SpringExtension Callback | Work in TestContext |
|---|---|
| BeforeAllCallback | beforeTestClass |
| TestInstancePostProcessor | prepareTestInstance |
| BeforeEachCallback | beforeTestMethod |
| BeforeTestExecutionCallback | beforeTestExecution |
| AfterTestExecutionCallback | afterTestExecution |
| AfterEachCallback | afterTestMethod |
| AfterAllCallback | afterTestClass |

Callback names help distinguish two commonly confused milestones:

- **beforeTestMethod** occurs before JUnit's `@BeforeEach` methods.
- **beforeTestExecution** occurs immediately before the test method body, after the `@BeforeEach` setup phase.
- **afterTestExecution** occurs immediately after the test method body, before the `@AfterEach` phase.
- **afterTestMethod** occurs after `@AfterEach` methods.

General sequence when running a test method:

~~~text
Spring: beforeTestClass (once per class)
        |
JUnit creates test instance
        |
Spring: prepareTestInstance
        |-- Dependency injection
        |-- Prepare test instance
        |
Spring: beforeTestMethod
        |-- TestExecutionListener before method
        |
JUnit: @BeforeEach
        |
Spring: beforeTestExecution
        |-- Listener immediately before test body
        |
JUnit: @Test
        |
Spring: afterTestExecution
        |-- Listener immediately after test body
        |
JUnit: @AfterEach
        |
Spring: afterTestMethod
        |-- Listener after method
        |
Spring: afterTestClass (once after class)
~~~

This is an overview sequence to understand each phase's responsibility. Other extensions, nested tests, test templates, or listener configurations may add their own callbacks.

The key point is that Spring does not invoke all JUnit annotations itself. JUnit drives the test lifecycle; `SpringExtension` participates via the extension API to carry out TestContext Framework operations.

## 5. TestContextManager and TestExecutionListener

`TestContextManager` is the object coordinating Spring-integrated test execution. It holds the `TestContext` for the test class under execution and notifies `TestExecutionListener` instances of lifecycle events.

A `TestExecutionListener` can perform work at one or more milestones:

- Before the test class runs.
- When preparing the test instance.
- Before the test method.
- Immediately before and after the test body.
- After the test method.
- After the test class finishes.

Common listeners in Spring TestContext:

| Listener | Primary Responsibility |
|---|---|
| DependencyInjectionTestExecutionListener | Injects dependencies into the test instance |
| DirtiesContextTestExecutionListener | Processes contexts marked dirty |
| TransactionalTestExecutionListener | Manages transactions for tests annotated with `@Transactional` |
| SqlScriptsTestExecutionListener | Executes SQL declared with `@Sql` |
| EventPublishingTestExecutionListener | Publishes Spring test lifecycle events |

Default listeners are registered by Spring according to the TestContext Framework mechanism. Annotations such as `@Transactional`, `@Sql`, or `@DirtiesContext` rely on their corresponding listeners to do their work.

When customizing `@TestExecutionListeners`, pay attention to the default listener merge mode. If you accidentally replace the default list without keeping the required listeners, dependency injection, transactions, or SQL tests may stop working as expected.

## 6. When Does Dependency Injection Occur?

In JUnit Jupiter, `SpringExtension` implements `TestInstancePostProcessor`. After JUnit creates the test instance, the extension calls `TestContextManager` to prepare that instance.

Spring can inject dependencies into fields:

~~~java
@SpringBootTest
class CatalogServiceTest {

    @Autowired
    private CatalogService catalogService;

    @Test
    void shouldFindCatalogItem() {
        assertNotNull(catalogService);
    }
}
~~~

With this declaration, the field is injected during the `prepareTestInstance` phase, before `@BeforeEach` and test methods run.

Therefore, injected dependencies can be used inside `@BeforeEach`:

~~~java
@BeforeEach
void setUp() {
    catalogService.resetTestData();
}
~~~

Be careful with static methods. A static `@BeforeAll` method in `PER_METHOD` mode cannot access injected instance fields. If you need a Spring dependency during class-level setup, consider `PER_CLASS` to use an instance `@BeforeAll` method, or design the setup using another suitable mechanism.

`SpringExtension` also supports parameter resolution for constructors, test methods, and lifecycle methods in cases where Spring can resolve the parameter. For example, a test method can receive a bean via a parameter marked `@Autowired`:

~~~java
@Test
void shouldUseConfiguredCatalog(@Autowired CatalogService catalogService) {
    assertNotNull(catalogService);
}
~~~

For constructor injection in test classes, you can use `@TestConstructor(autowireMode = ALL)` or configure Spring TestContext's constructor autowire mode. Check the configuration of the Spring version in use if choosing this approach.

## 7. Test Instance Lifecycle Differs from Spring Bean Lifecycle

A very common point of confusion is that test instances and Spring beans have independent lifecycles.

By default, JUnit creates a new test instance for each test method. However, the Spring `ApplicationContext` is typically reused from the context cache. Singleton beans in the context can be shared across multiple test methods and even across multiple test classes with the same context configuration.

Example:

~~~text
Cached ApplicationContext
    |
    +-- CatalogService (singleton)
    +-- CatalogRepository
    +-- Clock
    |
    +-- Test class A
    |      +-- Test instance A1
    |      +-- Test instance A2
    |
    +-- Test class B
           +-- Test instance B1
           +-- Test instance B2
~~~

Test instances may be new, yet the `CatalogService` singleton in the same `ApplicationContext` remains the same bean.

This leads to two different forms of state:

**Test instance state**

- Fields in the test class.
- Fixture lists created in `@BeforeEach`.
- Temporary variables and mocks declared in the test instance.
- Test helper objects held in fields.

**Spring ApplicationContext and bean state**

- Singleton beans with mutable fields.
- Caches inside the application.
- Listeners or schedulers registered in the context.
- Mock beans shared within the context.
- Singletons storing data in memory.

`PER_METHOD` only isolates the test instance. It does not automatically reset singleton beans or data in the database.

If a singleton bean holds mutable state, one test can affect another even when each method uses a separate test instance. Design services to be stateless when appropriate, or provide a clear way to reset state for the test environment.

## 8. Context Caching and Its Impact Across Multiple Test Classes

The Spring TestContext Framework stores `ApplicationContext` instances in a cache to avoid restarting the same configuration for each test class.

A context is identified based on configuration details such as:

- Context loader.
- Configuration classes.
- Initializers.
- Context customizers and mock bean configurations.
- Active profiles.
- Property sources.
- Parent context and related attributes.

If multiple test classes have equivalent configuration, Spring can reuse the same `ApplicationContext`. This makes the test suite faster, but also means singleton state can persist across multiple classes.

Example:

~~~java
@SpringBootTest
class CatalogServiceTest {
    // Uses the ApplicationContext of this configuration.
}
~~~

~~~java
@SpringBootTest
class CatalogControllerTest {
    // Can reuse the equivalent context from cache.
}
~~~

If two classes have different configurations, such as different active profiles or properties, Spring may need a different context.

Do not assume every test class always gets a fresh `ApplicationContext`. Nor should you rely on a context accidentally being recreated to wipe state that a test mutated.

### When to Use @DirtiesContext?

`@DirtiesContext` marks the `ApplicationContext` as altered and needing eviction from the cache. Spring will create a new context when a subsequent test requires the corresponding configuration.

It can be used at the method level:

~~~java
@Test
@DirtiesContext
void shouldRebuildContextAfterChangingSingletonState() {
    // Perform a change that cannot be safely restored
    // to the state of the ApplicationContext.
}
~~~

Or at the class level:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyContextMutationTest {
}
~~~

Some common class modes:

- `BEFORE_CLASS`: marks the context dirty before the class runs.
- `AFTER_CLASS`: marks it dirty after the class finishes.
- `BEFORE_EACH_TEST_METHOD`: refreshes the context before each method.
- `AFTER_EACH_TEST_METHOD`: refreshes the context after each method.

Per-method modes can make tests very slow because the context must be rebuilt repeatedly. Use `@DirtiesContext` only when a test genuinely changes context structure or state to an extent that cannot be safely restored via normal cleanup.

`@DirtiesContext` only handles the `ApplicationContext` cache. It does not automatically delete data written to an external database, clean up test files, or undo an HTTP request sent to another system. Those resources need separate cleanup mechanisms.

## 9. Transactions and Cleanup Order in a Test Method

Spring TestContext can manage transactions for test methods when using `@Transactional`.

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldPersistOrderInsideTestTransaction() {
        orderRepository.save(new Order("customer-1", new BigDecimal("250000")));

        assertEquals(1, orderRepository.count());
    }
}
~~~

With default test transaction configuration, a transaction is started for the test method and rolled back after the test finishes. This keeps database data isolated between tests.

`TransactionalTestExecutionListener` participates in the lifecycle via callbacks before and after the test method. Specialized hooks can be used:

- `@BeforeTransaction`: runs before the test transaction begins.
- `@AfterTransaction`: runs after the test transaction ends.
- `@Commit`: requests commit instead of default rollback.
- `@Rollback`: controls rollback or commit per configuration.
- `TestTransaction`: controls the test transaction in advanced scenarios.

### Cleanup in @AfterEach May Still Run Inside the Transaction

Because the test transaction opens before `@BeforeEach` methods and ends after the `@AfterEach` phase, cleanup operations in `@AfterEach` typically run within the same transaction as the test method.

If the test uses default rollback, database cleanup operations may be unnecessary since the entire transaction will roll back. However, cleanup is still necessary for non-transactional resources such as temporary files, mock servers, external caches, or data written over another connection.

### Be Careful with Servers Running on Another Thread

An important scenario:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class OrderApiTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void shouldCreateOrder() {
        http.postForEntity(
                "/api/orders",
                request(),
                OrderResponse.class
        );
    }
}
~~~

The test-managed transaction runs on the test thread. The HTTP request is processed on a server thread. The server-side transaction does not automatically join the test transaction of the thread sending the request.

Therefore, rolling back the test transaction does not guarantee that data created by a real HTTP request will be rolled back. API tests using `RANDOM_PORT` need appropriate data cleanup, such as deleting records by test ID or using a dedicated database/container for the test lifecycle.

This is why you must distinguish tests using in-process `MockMvc` from tests sending requests through a real HTTP server when designing data setup and cleanup.

## 10. Test Method Lifecycle and Types of Test Invocations

JUnit Jupiter has several kinds of test methods beyond `@Test`:

- `@ParameterizedTest`: runs the same test logic with multiple parameter sets.
- `@RepeatedTest`: repeats a test multiple times.
- `@TestFactory`: creates dynamic tests.
- `@TestTemplate`: supplies an execution template for extensions or test frameworks.

With test templates such as parameterized tests and repeated tests, callbacks before/after each invocation allow every execution to have its own setup and cleanup. `SpringExtension` continues coordinating with `TestContext` during the corresponding stages.

Parameterized test example:

~~~java
@SpringJUnitConfig(PricingTestConfiguration.class)
class DiscountCalculatorTest {

    @Autowired
    private DiscountCalculator calculator;

    @ParameterizedTest
    @CsvSource({
            "100000, 0.00",
            "200000, 0.05",
            "500000, 0.10"
    })
    void shouldCalculateDiscount(
            BigDecimal amount,
            BigDecimal expectedRate
    ) {
        assertEquals(expectedRate, calculator.discountRate(amount));
    }
}
~~~

Each parameter set creates one test execution. If mutable data is involved, re-prepare it per invocation and avoid depending on the order of parameter sets.

Dynamic tests from `@TestFactory` have their own lifecycle rules: the factory method's callbacks do not simply repeat all `@BeforeEach` and `@AfterEach` hooks for each `DynamicTest`. If isolated setup/cleanup is needed for each dynamic case, design the dynamic test executable to manage that itself or use a parameterized test when appropriate.

## 11. Test Lifecycle Under Parallel Execution

JUnit Jupiter can run tests in parallel when configured. This can reduce execution time, but exposes state dependencies that were hidden during sequential execution.

Common risks:

- Two tests writing the same database record.
- Multiple methods sharing a `PER_CLASS` instance and mutating the same field.
- Two tests concurrently altering a singleton bean in the `ApplicationContext`.
- A shared mock bean being reset or configured concurrently.
- Tests sharing a fixed file or fixed port.
- One test deleting data that another test is currently using.

If a test class uses `PER_CLASS`, pay special attention because methods share one instance. Under parallel execution, mutable fields can be accessed concurrently.

You can use `@Execution(ExecutionMode.SAME_THREAD)` on a class or method that needs sequential execution, though this is only an execution control measure. A better approach is isolating data and avoiding mutable shared state.

Example JUnit Platform configuration:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
~~~

Enable parallel execution only once tests have a clear strategy for isolating data, resources, and contexts. A fast yet flaky test suite is difficult to rely on as a trustworthy CI signal.

## 12. Comprehensive Example: Tracking the Lifecycle in a Spring Test

The example below shows how JUnit and Spring participate together:

~~~java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CatalogLifecycleTest {

    @Autowired
    private CatalogService catalogService;

    private String testId;

    @BeforeAll
    void beforeAll() {
        // Instance method because the class uses PER_CLASS.
        // SpringExtension has already prepared the test instance.
        assertNotNull(catalogService);
    }

    @BeforeEach
    void beforeEach() {
        // Dependencies have already been injected.
        testId = UUID.randomUUID().toString();
    }

    @Test
    void shouldFindCatalog() {
        var result = catalogService.findCatalog(testId);

        assertNotNull(result);
    }

    @AfterEach
    void afterEach() {
        // Clean up state specific to this test run.
        testId = null;
    }

    @AfterAll
    void afterAll() {
        // Release class-level resources if any.
    }
}
~~~

This example focuses on lifecycle; `CatalogService` and test data must be supplied per project configuration. If the test creates database data, add appropriate cleanup or use a test transaction when execution boundaries permit rollback.

Another option is keeping `PER_METHOD` and using a static `@BeforeAll`:

~~~java
@SpringBootTest
class CatalogLifecyclePerMethodTest {

    @Autowired
    private CatalogService catalogService;

    @BeforeAll
    static void beforeAll() {
        // Class-level setup does not access instance fields.
    }

    @BeforeEach
    void beforeEach() {
        // catalogService has already been injected into the instance.
        assertNotNull(catalogService);
    }
}
~~~

Both approaches are valid. Choose based on the test instance's state-sharing needs, not merely to drop the `static` keyword.

## 13. Common Lifecycle Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| `@Autowired` field is null in static `@BeforeAll` | Static method cannot access test instance | Use `PER_CLASS` with instance `@BeforeAll` or move bean usage to `@BeforeEach` |
| Test passes alone but fails when running the class | Mutable state retained across methods or shared data | Reset in `@BeforeEach`, create fresh fixtures, isolate database |
| Later test class affected by earlier class | Shared `ApplicationContext` cache and singleton beans | Reset bean state, clean up resources, or use `@DirtiesContext` when truly needed |
| `@BeforeEach` does not see bean | `SpringExtension` not registered or context improperly prepared | Use `@SpringBootTest`, `@SpringJUnitConfig`, or `@ExtendWith(SpringExtension.class)` |
| Data remains after test with `@Transactional` | Data written via another thread or transaction, e.g., real HTTP server | Clean up data separately or use an isolated database environment |
| `PER_CLASS` test fails under parallel execution | Multiple methods concurrently mutating state on one instance | Separate state, run sequentially, or make test thread-safe |
| Context restarts too many times | Differing context configurations or frequent `@DirtiesContext` usage | Standardize test configuration and dirty the context only when needed |
| `@AfterEach` does not clean non-database data | Cleanup only affects the test transaction | Use dedicated cleanup APIs for files, caches, or external services |

When a test fails, identify where the state resides before adding cleanup: test instance, singleton bean, `ApplicationContext`, database transaction, or external resource. Each type has a different lifecycle and restoration mechanism.

## 14. Designing the Right Lifecycle for Each Test Type

For **plain unit tests**, keep the default `PER_METHOD`, create fresh fixtures per method, and omit `SpringExtension` when not testing Spring behavior.

For **Spring slice tests**, let `SpringExtension` manage injection and context. Use `@BeforeEach` to prepare isolated data; avoid keeping mutable state in singleton beans.

For **Spring integration tests**, understand the context cache and test transactions. If using `@Transactional`, verify whether operations run in the same thread/transaction or through a real server. If the context is reused, ensure tests leave no state in singleton beans.

For **tests with class-level resources**, `PER_CLASS` can reduce resource creation cost, but requires resetting data and controlling parallel execution. If you only need a static setup without instance fields, keeping `PER_METHOD` and static `@BeforeAll` is simpler.

For **tests that mutate the `ApplicationContext`**, use `@DirtiesContext` narrowly and specify the dirty timing clearly. Do not use it in place of deleting database data or cleaning up files.

## 15. Conclusion

The testing lifecycle in Spring is formed by JUnit Jupiter and the Spring TestContext Framework. JUnit manages the test class, test instance, and test invocations; `SpringExtension` translates JUnit callbacks into context preparation, dependency injection, and notifications to `TestExecutionListener` instances.

Keep the core relationships in mind:

- `PER_METHOD` creates a separate test instance for each test method; this is JUnit Jupiter's default.
- `PER_CLASS` shares one test instance and allows `@BeforeAll`/`@AfterAll` to be instance methods; state must be managed carefully.
- `SpringExtension` prepares the test instance and coordinates TestContext callbacks around each method.
- A new test instance does not mean a new `ApplicationContext` or new singleton beans; Spring can reuse contexts via the cache.
- `@Transactional` normally rolls back the test transaction after the method, but requests through a real HTTP server run on a separate thread with their own transaction.
- `@DirtiesContext` evicts the context from the cache when context state has been altered and cannot be restored via normal cleanup.

Once you identify which lifecycle owns each piece of state and resource, you can place setup and cleanup at the exact right moment, reduce coupling between test methods, and keep the Spring test suite stable when run individually, as a class, or in CI.


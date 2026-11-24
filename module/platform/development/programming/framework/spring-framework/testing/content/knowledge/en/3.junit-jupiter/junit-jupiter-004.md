# Test Instance Lifecycle and Shared State

JUnit Jupiter creates and manages test objects according to a defined lifecycle. How these objects are instantiated directly affects constructors, test class fields, `@BeforeAll` / `@AfterAll` callbacks, parallel execution safety, and how data is shared among tests. Understanding this lifecycle clearly lets you organize fixtures properly without allowing one test to accidentally alter the outcome of another.

By default, JUnit Jupiter uses **one test instance per test method** (`PER_METHOD`). Alternatively, you can configure **one test instance for the entire test class** (`PER_CLASS`) using `@TestInstance`. These two modes do not change the meaning of assertions or how JUnit discovers `@Test`; they change when instances are created and how long state held in those instances lives.

## 1. What Is a Test Instance?

A test instance is the Java object created by JUnit from the class containing test methods. Example:

```java
class AccountServiceTest {
    private AccountService service;

    @BeforeEach
    void setUp() {
        service = new AccountService();
    }

    @Test
    void createsAccount() {
        // Verify account creation behavior.
    }
}
```

`AccountServiceTest` is the test class; each `AccountServiceTest` object created when JUnit executes tests is a test instance. Non-`static` fields, such as `service`, belong to a specific instance. Consequently, the lifetime of a field depends on whether JUnit creates one or multiple instances.

The lifecycle of a test instance is independent of the lifecycle of the application objects under test. For instance, a test using `@SpringBootTest` can receive the same Spring `ApplicationContext` cached by the TestContext Framework, while the test class still gets a fresh instance for each test method. Conversely, choosing `PER_CLASS` only keeps the test instance alive longer; it does not automatically re-initialize Spring singleton beans or databases.

## 2. The Default `PER_METHOD` Mode

If `@TestInstance` is not declared, JUnit Jupiter defaults to `TestInstance.Lifecycle.PER_METHOD`. JUnit creates a new instance for each test method. Instance fields of the test class are therefore re-initialized when moving to another method.

```java
class MessageServiceTest {
    private final List<String> sentMessages = new ArrayList<>();

    @Test
    void recordsFirstMessage() {
        sentMessages.add("hello");

        assertThat(sentMessages).containsExactly("hello");
    }

    @Test
    void startsWithAnEmptyMessageList() {
        assertThat(sentMessages).isEmpty();
    }
}
```

These two tests do not depend on execution order. When `recordsFirstMessage` runs, the list belongs to that method's instance. When `startsWithAnEmptyMessageList` runs, JUnit creates a different instance so the `sentMessages` field is re-initialized.

`PER_METHOD` is a safe starting point because it reduces the likelihood of instance state leaking between test methods. However, this mode does not isolate everything automatically. `static` fields, singletons, caches, files, system properties, databases, message brokers, and external resources can still be shared across multiple tests.

### 2.1. Impact on Constructors

With `PER_METHOD`, the test class constructor is invoked for every test method. If the constructor accepts parameters via JUnit's `ParameterResolver` or an extension, instance creation and parameter resolution also happen per instance.

Constructors should be used to initialize dependencies or immutable values needed by the test instance. Avoid putting expensive operations or global side effects in constructors, because those actions repeat for every test method.

### 2.2. Rules for `@BeforeAll` and `@AfterAll`

In `PER_METHOD` mode, `@BeforeAll` and `@AfterAll` must be `static` methods, because JUnit invokes them at the class level before any specific instance exists for an individual test method and after all methods have finished.

```java
class AccountServiceTest {
    @BeforeAll
    static void startSuite() {
        // Initialize shared class-scoped resource.
    }

    @BeforeEach
    void setUp() {
        // Prepare data specific to each test method.
    }

    @AfterEach
    void tearDown() {
        // Clean up data specific to the test method.
    }

    @AfterAll
    static void stopSuite() {
        // Release class-scoped resource.
    }
}
```

`@BeforeEach` and `@AfterEach` callbacks still run on the instance corresponding to each test method. They are the appropriate place to prepare and clean up per-test fixtures.

## 3. The `PER_CLASS` Mode

When a test class is annotated with `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, JUnit creates a single instance for that class and reuses it across test methods in the class.

```java
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.TestInstance.Lifecycle.PER_CLASS;

@TestInstance(PER_CLASS)
class ReportServiceTest {
    private ReportService service;

    @BeforeAll
    void initializeClassFixture() {
        // This is an instance method because the test instance already exists.
        service = new ReportService();
    }

    @BeforeEach
    void resetStateForCurrentTest() {
        service.clearReports();
    }

    @Test
    void createsMonthlyReport() {
        service.createMonthlyReport(2026, 11);

        assertThat(service.findAll()).hasSize(1);
    }

    @Test
    void startsWithoutReportsForAnotherTest() {
        assertThat(service.findAll()).isEmpty();
    }

    @AfterAll
    void releaseClassFixture() {
        service.close();
    }
}
```

With `PER_CLASS`, `@BeforeAll` and `@AfterAll` can be instance methods. They are called once for the class lifecycle, so they can access test instance fields. This difference is commonly leveraged when an expensive fixture needs to be initialized once or when using a non-static `@MethodSource`.

One caveat is that `service` also persists across test methods. The example above explicitly calls `clearReports()` in `@BeforeEach` so each test starts from a clean state. Without this reset step, the test that creates a report could cause the next test to see stale reports.

### 3.1. When Should You Use `PER_CLASS`?

This mode can be suitable when:

- An expensive resource needs to be initialized once for the whole class, such as a server or a shared fixture with an explicit reset mechanism.
- Non-`static` `@BeforeAll` / `@AfterAll` methods are needed to access dependencies managed on the test instance.
- Non-`static` factory methods are needed, such as a `@MethodSource` reading data from a test instance field.
- Tests in the class are designed to intentionally manage shared state and can reset independently.

Do not choose `PER_CLASS` merely to avoid writing `static` or to pass results from one test to another. If test B needs data created by test A, the two tests are order-dependent. Let each test set up its own preconditions or extract data creation into a shared fixture that can be invoked independently.

### 3.2. Risk of Leaked State

With `PER_CLASS`, every instance field can be accessed by multiple test methods. A test that mutates a list, map, counter, mock, or domain object can affect other tests if state is not restored.

The following example shows an error-prone design:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {
    private final List<String> items = new ArrayList<>();

    @Test
    void addsAnItem() {
        items.add("book");
        assertThat(items).containsExactly("book");
    }

    @Test
    void startsWithAnEmptyCart() {
        assertThat(items).isEmpty();
    }
}
```

The `startsWithAnEmptyCart` test depends on whether `addsAnItem` has already run. JUnit does not guarantee test method execution in source declaration order. When running individually, the test may pass; when running the whole class or running in parallel, outcomes can differ.

The proper fix is to initialize or reset data before each test:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingCartTest {
    private List<String> items;

    @BeforeEach
    void createFreshCart() {
        items = new ArrayList<>();
    }

    @Test
    void addsAnItem() {
        items.add("book");

        assertThat(items).containsExactly("book");
    }

    @Test
    void startsWithAnEmptyCart() {
        assertThat(items).isEmpty();
    }
}
```

Another approach is to keep the fixture immutable after `@BeforeAll` and create new mutable objects for each test. For example, you can share a read-only configuration while creating a fresh `ShoppingCart` in `@BeforeEach`. This reduces the number of places needing resets and clarifies state ownership.

## 4. Callback Sequence in a Test Class

JUnit Jupiter provides class-scoped and per-test callbacks. For a simple test class, you can visualize the sequence as follows:

```text
Create test instance
        |
        v
   @BeforeAll                 once for the class
        |
        +-----------------------------------+
        |                                   |
        v                                   v
   @BeforeEach                         @BeforeEach
        |                                   |
        v                                   v
     @Test                               @Test
        |                                   |
        v                                   v
   @AfterEach                          @AfterEach
        |                                   |
        +-----------------------------------+
        |
        v
    @AfterAll                  once after the class
```

The diagram focuses on JUnit callbacks. Extensions can contribute callbacks at corresponding lifecycle points; detailed ordering between extensions and callbacks is defined by the extension API and extension registration order.

| Callback | Frequency | Common Purpose |
|---|---|---|
| Constructor | Each test instance | Initialize instance fields and dependencies |
| `@BeforeAll` | Once before tests in the class | Create class-level resources |
| `@BeforeEach` | Before each test method | Prepare per-test data |
| `@Test` | Per test method | Execute scenario and assertions |
| `@AfterEach` | After each test method | Clean up per-test resources |
| `@AfterAll` | Once after tests in the class | Close class-level resources |

### 4.1. Order Between Callback Methods

Do not rely on the declaration order of `@BeforeEach` or `@AfterEach` methods within the same class. JUnit uses a deterministic ordering that is not intended to reflect source order; that order can be hard to read and should not be used to establish dependencies between callbacks.

If a test needs two preparation steps in sequence, invoke them from a single setup method or wrap them in a helper whose name expresses the order. This keeps the preparation flow directly visible.

With inheritance, `@BeforeAll` and `@BeforeEach` callbacks execute from superclass down to subclass. `@AfterEach` and `@AfterAll` callbacks run in reverse order: subclass before superclass. This lets the parent class prepare shared resources and the child class extend preparation; during cleanup, the child class releases its own resources before the parent class releases underlying resources.

Example:

```java
abstract class BaseRepositoryTest {
    @BeforeEach
    void initializeBaseFixture() {
        // Prepare common fixture.
    }

    @AfterEach
    void cleanBaseFixture() {
        // Clean up common fixture.
    }
}

class CustomerRepositoryTest extends BaseRepositoryTest {
    @BeforeEach
    void initializeCustomerFixture() {
        // Runs after initializeBaseFixture().
    }

    @AfterEach
    void cleanCustomerFixture() {
        // Runs before cleanBaseFixture().
    }
}
```

Do not use inheritance just to share a few short setup lines. If fixtures have many variants, explicit factories or helpers are usually easier to understand than a test class hierarchy with hidden callbacks.

## 5. Lifecycle of `@Nested` and Dynamic Tests

`@Nested` allows grouping related tests inside non-`static` nested classes. This structure is helpful when a subject has multiple contextual states or behaviors:

```java
class OrderServiceTest {
    private OrderService service;

    @BeforeEach
    void setUp() {
        service = new OrderService();
    }

    @Nested
    class WhenOrderIsPending {
        @Test
        void allowsConfirmation() {
            // Verify order confirmation.
        }
    }

    @Nested
    class WhenOrderIsCancelled {
        @Test
        void rejectsConfirmation() {
            // Verify confirmation rejection.
        }
    }
}
```

A nested class can access members of its enclosing outer instance per Java rules. Consequently, mutable fields on the outer class can become shared state across nested structures. Organize setup so each scenario gets a fixture in the right state; do not use one nested test to prepare data for another nested test.

Nested classes can also declare their own callbacks to add setup or cleanup for their context. When nesting multiple levels, keep callbacks concise and place fixtures close to the test group using them so readers can see what state is created at each level.

### 5.1. Dynamic Tests and Callbacks

`@TestFactory` creates dynamic tests using `DynamicTest`. There is an important difference: `@BeforeEach` and `@AfterEach` run around the factory method, not individually for each dynamic test returned by the factory. Therefore, do not assume every dynamic test receives an independent setup/teardown cycle like a normal `@Test` method.

```java
class PriceRulesTest {
    @TestFactory
    Stream<DynamicTest> validatesSeveralPrices() {
        List<BigDecimal> prices = List.of(
                new BigDecimal("0.00"),
                new BigDecimal("10.00"),
                new BigDecimal("99.00"));

        return prices.stream().map(price -> DynamicTest.dynamicTest(
                "accepts price " + price,
                () -> assertThat(price).isGreaterThanOrEqualTo(BigDecimal.ZERO)
        ));
    }
}
```

In this example, dynamic tests only use local data and pure assertions. If each dynamic test requires its own service or database state, create the fixture directly inside each `DynamicTest` executable, or consider `@ParameterizedTest` if the scenario is a single test method run with multiple parameter sets. Do not rely on `@BeforeEach` to reset between dynamic nodes.

## 6. Instance State, Static State, and External Resources

`PER_METHOD` mode only isolates instance fields of the test class. The following kinds of state can still outlive a single test instance:

| State Type | Typical Scope | Cross-Test Risk |
|---|---|---|
| Instance field | Single test instance | Can be shared across multiple test methods under `PER_CLASS` |
| `static` field | Class loaded in classloader | Instances of the same class share the same value |
| Singleton Spring bean | Spring `ApplicationContext` | Multiple tests can share the bean and mutable state |
| Cache or system property | JVM or application context | Another test may read stale data or altered configuration |
| Database, file, broker | External infrastructure | Data can persist across multiple classes and runs |
| Static mock or global registry | JVM/classloader | Can affect tests running in the same process |

For example, `static List<String> events` remains a shared list even when the test class uses `PER_METHOD`. Creating a new test instance does not create a new classloader and does not clear static values.

To manage shared state, pick measures by scope:

- Instance fields: create fresh fixtures in the constructor or `@BeforeEach`.
- Static fields: avoid mutable static state unless necessary; if unavoidable, explicitly reset in setup and ensure no concurrent modification occurs.
- Spring singletons: design beans to be stateless; if a bean holds state, expose a test-only reset API or use a dedicated context when truly needed.
- Databases: use uniquely identified data, transaction rollback where appropriate, or fixture-based deletion.
- Files and OS resources: create per-test temporary directories/files and always close or delete them in cleanup.
- System properties: save the old value, set the new value in the test, and restore it in `finally` or a cleanup callback.

Do not treat `@AfterEach` as the sole mechanism for restoring state. If a test fails halfway through, cleanup must still be written safely without assuming all setup steps completed. For closeable resources, prefer `try-with-resources` or resource-managing extensions.

## 7. Test Instance Lifecycle in Spring Tests

The Spring TestContext Framework and JUnit Jupiter collaborate through `SpringExtension`. These two systems manage different objects:

- JUnit manages test instances and Jupiter callbacks.
- Spring manages the `ApplicationContext`, dependency injection, test transactions, and TestContext Framework listeners.

Example:

```java
@SpringBootTest
class CustomerServiceIntegrationTest {
    @Autowired
    private CustomerService customerService;

    @Test
    void createsCustomer() {
        // Verify service in Spring context.
    }
}
```

With the default `PER_METHOD`, JUnit creates a new `CustomerServiceIntegrationTest` for each test method. Spring may reuse a cached `ApplicationContext` across compatible tests. Thus, the `customerService` field is injected into each new test instance, yet the bean it references may still be the same singleton in the shared context.

This leads to two consequences:

1. Resetting test class fields does not reset internal state inside singleton beans.
2. Creating a new test instance does not mean creating a new Spring context or a new database.

Spring beans should normally be stateless or manage state per request/session as appropriate. If a singleton bean retains mutable state, tests can interfere with each other even under `PER_METHOD`. Inspect bean design and data boundaries before reaching for `@DirtiesContext`.

`@DirtiesContext` marks an `ApplicationContext` as no longer usable so Spring evicts it from the cache and builds a fresh context when needed. This annotation is useful when a test genuinely alters context configuration or state in an unrecoverable way. It adds startup time and does not replace cleaning up database data, files, or external resources outside the context.

### 7.1. Test Transactions Do Not Depend on `PER_CLASS`

When using `@Transactional` in Spring Test, test transactions are typically managed per test method and rolled back after the test under the TestContext Framework's default configuration. Choosing `PER_CLASS` does not merge test methods into a single shared transaction.

Similarly, a field holding an entity or repository reference on the test instance does not dictate transaction boundaries. If a test needs to verify committed data, design transactions explicitly and read the data from another transaction after commit. Do not infer commit/rollback behavior from whether JUnit uses one or multiple test instances.

## 8. Parallel Execution and Shared State

JUnit Jupiter supports parallel test execution when enabled in platform configuration. By default, parallel execution is not enabled just because a test class uses `PER_CLASS`; however, when a project enables parallel execution, multiple test methods may access the same instance and the same mutable fields concurrently.

For example, with `PER_CLASS`:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SequenceServiceTest {
    private final List<Long> generatedIds = new ArrayList<>();

    @Test
    void generatesFirstId() {
        generatedIds.add(1L);
    }

    @Test
    void generatesSecondId() {
        generatedIds.add(2L);
    }
}
```

If both tests run concurrently, they access `generatedIds` at the same time. `ArrayList` is not designed for concurrent modification by multiple threads without synchronization. Even if switched to a thread-safe collection, tests could still depend on ordering or element count if state is not reset.

Options include:

- Keep tests independent and create separate data per test; this is usually the best option.
- Avoid `PER_CLASS` if instance sharing is unnecessary.
- Use `@Execution(ExecutionMode.SAME_THREAD)` when a class must execute sequentially for an explainable reason.
- Use `@ResourceLock` when multiple tests must access the same named resource and require coordinated access.
- Partition external resources per test, such as separate schemas, keys, directories, or queues.

Example using a resource lock for a shared system property:

```java
@ResourceLock(value = "user.timezone", mode = ResourceAccessMode.READ_WRITE)
class TimeZoneConfigurationTest {
    @Test
    void changesAndRestoresDefaultTimeZone() {
        // Modify configuration within locked scope and restore after test.
    }
}
```

Resource locks help JUnit coordinate tests that declare the same resource key. They do not lock code outside JUnit or other processes, and they do not automatically restore modified values. Tests must still clean up properly.

## 9. Configuring the Default Lifecycle Project-Wide

Besides per-class annotations, JUnit Jupiter allows changing the default lifecycle via platform configuration in `junit-platform.properties` on the test classpath:

```properties
junit.jupiter.testinstance.lifecycle.default = per_class
```

This file is typically placed at `src/test/resources/junit-platform.properties`. With this configuration, test classes that do not declare `@TestInstance` use `PER_CLASS` instead of the `PER_METHOD` default. A class with an explicit `@TestInstance` still expresses its own lifecycle choice.

Changing the project-wide default can affect many test classes at once. If the configuration exists only in an IDE or only in one module, tests may run with different lifecycles between local development and CI. Therefore:

- Only change the project-wide default when the team agrees on the policy and understands its effect across the entire test suite.
- Commit the configuration file to source control so IDEs, Gradle/Maven, and CI use the same setting.
- For classes that genuinely need `PER_CLASS`, consider declaring `@TestInstance(PER_CLASS)` directly so intent is clear at the point of use.
- When upgrading or migrating tests, check both engine and classpath configurations; do not assume lifecycle comes solely from annotations.

If the project has no clear need for another policy, keeping the `PER_METHOD` default makes behavior easier to predict for new test authors.

## 10. Choosing Between `PER_METHOD` and `PER_CLASS`

| Criterion | `PER_METHOD` | `PER_CLASS` |
|---|---|---|
| Number of instances | One instance per test method | One instance for the entire class |
| Instance fields | Re-initialized between methods | Can retain values across methods |
| `@BeforeAll` / `@AfterAll` | Must be `static` | Can be instance methods |
| Constructor | Invoked for each test method | Invoked once for the class |
| Instance state isolation | Better by default | Requires explicit reset or intentional state design |
| Parallel execution | Each method has its own instance, though other resources can still be shared | Methods can access the same instance concurrently if run in parallel |
| Suitable scenarios | Most ordinary unit and integration tests | Class-level fixtures, shared resources with explicit reset, non-static factories |

Choose based on the kind of state that actually needs to be shared. If you only want to avoid instantiating a small object a few times, the gain rarely justifies introducing mutable state into the test class. If you need to start a server or class-level resource, `PER_CLASS` can make setup/cleanup clearer, provided each test remains independent.

## 11. Common Mistakes and How to Handle Them

### Assuming `PER_METHOD` Resets All State

Instance fields are separated, but static fields, Spring singletons, databases, and files can still persist. Determine the scope of data before deciding how to reset it.

### Using `PER_CLASS` and Relying on Test Order

A test that creates data first and another that reads it later create order dependency. Each test should create its own fixture or call a shared factory to establish initial state.

### Using `@AfterEach` to Mask Uncertain Setup

If cleanup assumes a field was initialized or a step completed, it can throw secondary errors and obscure the original failure. Cleanup should check whether resources exist, be safe to invoke repeatedly, and always release whatever was created.

### Assuming `@BeforeAll` Runs Before Any Test Instance Exists in All Modes

In `PER_CLASS`, the instance is created so instance callbacks can run. Non-`static` `@BeforeAll` can access instance fields. In `PER_METHOD`, `@BeforeAll` is `static` and cannot access instance fields.

### Confusing Test Instances with the Spring Context

JUnit may create a new instance while Spring reuses the context. Resetting test class fields does not reset singleton beans. Only use `@DirtiesContext` when the context is genuinely dirtied and cannot be recovered by normal cleanup.

### Using Dynamic Tests While Expecting Setup per Dynamic Node

`@BeforeEach` / `@AfterEach` callbacks wrap the factory method, not each individual dynamic test. Create fixtures inside each executable or choose parameterized tests for matching scenarios.

### Running in Parallel with Shared Mutable State

Combining `PER_CLASS` with parallel execution can introduce race conditions. Prefer per-test fixtures; use resource locks or sequential execution only when shared resources are unavoidable.

## 12. Lifecycle-Driven Fixture Design Workflow

When designing a test class, explicitly answer these questions:

1. Does the test need instance fields to hold fixtures across callbacks?
2. Can each test method create a fresh fixture at a reasonable cost?
3. Are there resources that need to be created once for the class, and who is responsible for closing them?
4. If using `PER_CLASS`, which mutable fields must be reset before every test?
5. Is there any `static` state, Spring singleton, or external resource still shared even under `PER_METHOD`?
6. Does the project enable parallel execution, and which tests access shared resources concurrently?
7. Are cleanup callbacks safe when a test fails partway through?

A maintainable structure is often: `@BeforeAll` initializes class-level resources, `@BeforeEach` creates per-test fixtures, the test method executes a single scenario, `@AfterEach` cleans up per-test resources, and `@AfterAll` closes class-level resources. With `PER_METHOD`, the two class-level callbacks must be `static`; with `PER_CLASS`, they can be instance methods.

Not every class needs all callbacks. Omit a callback if it has no corresponding work. Overly generic setup can force every test to receive unused data and dependencies; keeping fixtures close to scenarios makes them easier to understand.

## 13. Combined Example: Class-Level Resource and Per-Test Fixture

Suppose a test class needs an HTTP stub server across the class, while each test sends requests with its own data. You can use `PER_CLASS` to start the server once, then reset mappings and request logs before each test:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CatalogClientTest {
    private StubServer stubServer;
    private CatalogClient catalogClient;

    @BeforeAll
    void startStubServer() {
        stubServer = new StubServer();
        stubServer.start();
        catalogClient = new CatalogClient(stubServer.baseUrl());
    }

    @BeforeEach
    void resetStubState() {
        stubServer.resetMappings();
        stubServer.resetRequests();
    }

    @Test
    void readsCatalogItem() {
        stubServer.stubGet("/catalog/42", 200, """
                {"id": 42, "name": "Keyboard"}
                """);

        CatalogItem item = catalogClient.findById(42L);

        assertThat(item.name()).isEqualTo("Keyboard");
        assertThat(stubServer.receivedRequests()).hasSize(1);
    }

    @Test
    void mapsNotFoundResponse() {
        stubServer.stubGet("/catalog/404", 404, "{}");

        assertThatThrownBy(() -> catalogClient.findById(404L))
                .isInstanceOf(CatalogItemNotFoundException.class);
    }

    @AfterAll
    void stopStubServer() {
        if (stubServer != null) {
            stubServer.stop();
        }
    }
}
```

`StubServer` here illustrates an HTTP mock server chosen by the project. Tests share the server process while resetting mappings and request logs before each method. When running in parallel, ensure the server supports per-test state partitioning or lock access; otherwise, run these methods sequentially.

This example demonstrates that `PER_CLASS` does not mean all data is retained. You deliberately classify resources by lifecycle: the server lives for the class, while mappings and request logs are reset per test.

## 14. Key Principles to Remember

- `PER_METHOD` is the default: each test method gets a new test instance.
- `PER_CLASS` creates a single shared instance for the class; mutable fields can leak across tests.
- `@BeforeAll` and `@AfterAll` are `static` in `PER_METHOD`, but can be instance methods in `PER_CLASS`.
- `@BeforeEach` and `@AfterEach` manage per-test-method fixtures; dynamic tests do not get separate callback cycles per dynamic node.
- A test instance is not the Spring `ApplicationContext`; creating a new instance does not reset singleton beans or external data.
- Static state and resources outside the JVM still need to be managed independently of JUnit's lifecycle.
- When parallel execution is enabled, control all shared mutable resources; independent fixtures are usually the simplest and most reliable approach.

The test instance lifecycle is the foundation for organizing state in JUnit Jupiter. Choose `PER_METHOD` for default independence, or `PER_CLASS` when there is a clear resource-sharing need and an explicit reset plan. When each test sets up its own initial state and cleans up only the state it owns, the test suite becomes more stable whether run individually, in full, or in parallel in CI.

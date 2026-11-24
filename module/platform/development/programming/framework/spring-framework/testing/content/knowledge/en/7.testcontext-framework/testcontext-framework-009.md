# Distinguishing the Test Lifecycle from the ApplicationContext Lifecycle

When writing Spring tests, two lifecycles occur concurrently yet serve two distinct purposes. The test lifecycle manages a test class, a test method, and callbacks such as setup, execution, and teardown. The `ApplicationContext` lifecycle manages the Spring container: loading configuration, creating beans, maintaining singletons, reusing contexts, and closing contexts when needed.

These two lifecycles are related but not identical. JUnit can create a new test instance for each method while Spring continues reusing the same cached `ApplicationContext`. As a result, fields on the test class may be refreshed, whereas state inside a singleton bean persists across multiple tests. Understanding this difference helps avoid order-dependent bugs, state leaks, and unnecessary context startups.

## Learning Objectives

After this lesson, you can:

- Describe the lifecycle of a test class and test method in JUnit Jupiter.
- Explain how Spring TestContext participates in test stages.
- Distinguish between test instance, test execution, and `ApplicationContext`.
- Explain why multiple test methods can share a single context.
- Understand Spring TestContext caching and the factors affecting context reuse.
- Use `@DirtiesContext` for the right purpose and at the right scope.
- Recognize which state is reset after each test and which state may remain.
- Distinguish the context lifecycle from transactions and the lifecycle of external resources.

## 1. Two Lifecycles Appearing Together in One Test

JUnit manages running tests. Spring TestContext adds the ability to prepare test instances, supply dependencies, and manage contexts. Meanwhile, the `ApplicationContext` itself has its own lifecycle, starting when loaded and refreshed, continuing while reused, and ending when closed.

You can visualize the general relationship:

~~~mermaid
flowchart TD
    A["JUnit starts test class"] --> B["Spring prepares TestContext"]
    B --> C["Load or get ApplicationContext from cache"]
    C --> D["Create and inject test instance"]
    D --> E["Run pre-test callbacks"]
    E --> F["Run test method"]
    F --> G["Run post-test callbacks"]
    G --> H["JUnit proceeds to next method"]
    H -->|Same context config| C
    H -->|Different config| I["Load another ApplicationContext"]
    C --> J["Context is reused"]
    J --> K["Closed when evicted from cache or JVM exits"]
~~~

The test lifecycle often repeats many times over an existing context. Spring does not create a brand-new container for every method by default. Caching reduces suite execution time, especially when the context contains many beans, auto-configurations, datasources, or an embedded server.

It is important to distinguish three concepts:

| Concept | Managed By | Meaning |
|---|---|---|
| Test class | JUnit Jupiter | Group of test methods and class-level callbacks |
| Test instance | JUnit, prepared by Spring | Java object holding test fields and methods |
| ApplicationContext | Spring Framework | Container holding beans, environment, and Spring resources |

A test instance is a Java object. `ApplicationContext` is a container that may hold hundreds of beans. Their creation and destruction times can differ greatly.

## 2. Test Lifecycle in JUnit Jupiter

JUnit Jupiter provides annotations and callbacks to control test execution. For an ordinary test class, the default test instance lifecycle is `PER_METHOD`: JUnit creates a new instance for each test method.

Example:

~~~java
class LifecycleTest {

    private int counter;

    @BeforeAll
    static void beforeAll() {
        System.out.println("Before all tests");
    }

    @BeforeEach
    void beforeEach() {
        counter = 0;
        System.out.println("Before each test");
    }

    @Test
    void firstTest() {
        counter++;
        assertEquals(1, counter);
    }

    @Test
    void secondTest() {
        counter++;
        assertEquals(1, counter);
    }

    @AfterEach
    void afterEach() {
        System.out.println("After each test");
    }

    @AfterAll
    static void afterAll() {
        System.out.println("After all tests");
    }
}
~~~

With the default lifecycle, each method runs on a separate instance. Thus, the `counter` field does not carry its value from the first test to the second. `@BeforeEach` can still be used to prepare data per method, while `@AfterEach` performs corresponding cleanup.

Common stages:

| Callback or Annotation | Scope | Timing |
|---|---|---|
| `@BeforeAll` | Once per test class | Before test methods |
| `@BeforeEach` | Per test method | Before test body |
| `@Test` | Single method | Executes behavior under test |
| `@AfterEach` | Per test method | After test body |
| `@AfterAll` | Once per test class | After test methods |

By default, `@BeforeAll` and `@AfterAll` are typically static. If using `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, JUnit uses one test instance for the whole class and allows these callbacks to be instance methods.

Example:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedTestInstanceTest {

    private int counter;

    @BeforeAll
    void initializeOnce() {
        counter = 10;
    }

    @Test
    void firstTest() {
        counter++;
        assertEquals(11, counter);
    }

    @Test
    void anotherTest() {
        // The counter value depends on order if tests mutate the same field.
    }
}
~~~

With `PER_CLASS`, test methods share fields on the test instance. If multiple tests modify a mutable field, results can depend on execution order. Use this lifecycle only when sharing the test instance is intentional and tests are designed safely for shared state.

JUnit can run tests sequentially or in parallel depending on configuration. Do not rely on implicit ordering to prepare data for another test. Each test should establish its own prerequisites and be able to run independently.

## 3. How Does Spring TestContext Participate in the Test Lifecycle?

The Spring TestContext Framework integrates Spring with testing frameworks like JUnit Jupiter. It provides a unified model to load contexts, inject dependencies into the test instance, manage test transactions, and invoke listeners at appropriate moments.

With JUnit Jupiter, `SpringExtension` is the bridge between JUnit and Spring TestContext. You can register the extension directly:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class SpringContextTest {
    // Test methods
}
~~~

Or use the composed annotation:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class SpringContextTest {
    // Test methods
}
~~~

Spring Boot annotations such as `@SpringBootTest` also integrate the Spring TestContext mechanism and the corresponding extension.

Conceptually, the process unfolds as follows:

1. JUnit begins processing the test class and registered extensions.
2. Spring TestContext creates or retrieves metadata needed for the test class.
3. When a context is needed, Spring loads configuration and retrieves `ApplicationContext` from the cache if a matching context exists.
4. Spring prepares the test instance and performs dependency injection per test configuration.
5. Spring TestContext callbacks are invoked around each method and around the test class.
6. JUnit executes the test body along with JUnit callbacks.
7. Spring executes post-test callbacks, including transaction- and SQL-related listeners if enabled.

`SpringExtension` connects JUnit Jupiter callbacks with `TestContextManager`. TestContextManager coordinates stages such as preparing the test instance, before and after test methods, before and after test execution, as well as before and after the test class.

Spring TestContext does not replace JUnit. JUnit still decides how tests are discovered and executed; Spring adds the context and necessary testing services.

## 4. ApplicationContext Has Its Own Lifecycle

`ApplicationContext` is Spring's high-level container. When a context is loaded, Spring reads configuration, registers bean definitions, performs refresh, and creates required eager singletons. During that process, the bean factory and post-processors participate in creating, injecting, and initializing beans.

An overview of the context lifecycle:

~~~mermaid
flowchart TD
    A["Read configuration and resources"] --> B["Register BeanDefinition"]
    B --> C["Refresh ApplicationContext"]
    C --> D["Create and inject beans"]
    D --> E["Initialize beans and callbacks"]
    E --> F["Context ready"]
    F --> G["Multiple tests can use context"]
    G --> H{"Context evicted from cache?"}
    H -->|Yes| I["Close context"]
    H -->|No| G
    I --> J["Destroy beans and release resources"]
~~~

Important steps:

- **Reading configuration:** Spring receives configuration from classes, XML, component scanning, auto-configuration, and specified sources.
- **Registering bean definitions:** the container learns bean types, scopes, dependencies, and how to construct them.
- **Refresh:** the context completes container setup and enters the ready state.
- **Creating beans:** Spring creates singletons requiring eager initialization, resolves dependencies, and applies post-processors.
- **Initialization:** callbacks such as `@PostConstruct`, `InitializingBean`, or custom init methods may be called.
- **Usage:** tests and components in the context can access beans.
- **Closing:** when the context is actually closed, Spring invokes bean destruction callbacks and releases container-managed resources.

A context does not close automatically after each test method. In Spring TestContext, contexts are typically kept in the cache so compatible tests can reuse them.

## 5. One Context Can Serve Multiple Test Instances

This is the single most important point when distinguishing the two lifecycles.

Example of two test classes sharing the same configuration:

~~~java
@SpringBootTest
class OrderServiceTest {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrder() {
        // Verify business logic
    }
}
~~~

~~~java
@SpringBootTest
class OrderControllerTest {

    @Autowired
    OrderService orderService;

    @Test
    void handlesOrderRequest() {
        // Verify HTTP or controller
    }
}
~~~

If the context configurations of both classes are compatible and yield the same cache key, Spring can reuse a single `ApplicationContext`. JUnit still creates test instances according to each class's lifecycle. Each test method gets its own instance by default, yet the `orderService` field is injected with the exact same singleton bean from the reused context.

You can visualize this:

~~~mermaid
flowchart TB
    C["One cached ApplicationContext"]
    B["Singleton OrderService"]
    C --> B
    T1["Test instance: method A"] -->|Autowired| B
    T2["Test instance: method B"] -->|Autowired| B
    T3["Test instance in another class"] -->|Autowired| B
~~~

That means:

- Regular fields in a test class can be reinitialized for each method.
- Singleton beans in the context may remain the exact same instance.
- Mutable state inside a singleton bean can persist across many tests.
- Context caching avoids the cost of reloading and reinitializing the entire application.
- Creating a new test instance does not mean creating a new Spring container.

A test can pass when run alone yet fail inside the suite if it relies on bean state altered by another test. Conversely, a later test may inadvertently rely on data or state left behind by an earlier test.

Therefore, do not store per-test business state inside shared singleton beans. Reset data via appropriate APIs or fixtures, use bean scopes suited to the purpose, or create a new context when a test genuinely alters configuration or container state unrecoverably.

## 6. How Does Spring TestContext Cache Contexts?

Spring TestContext maintains a cache of loaded `ApplicationContext` instances. When a test needs a context, the framework computes the test configuration and searches the cache for a matching context. If found, it reuses the context; otherwise, it loads a new context and stores it in the cache.

Caching is based on context configuration, not simply on the test class name. Key factors determining the cache key include:

- Configuration locations or configuration classes.
- Context initializers.
- Context loader and context hierarchy.
- Active profiles.
- Property sources declared for the test.
- Context customizers, such as mock bean configurations or dynamic properties.
- Resource base path for web contexts.

Hence, two test classes with the same superficial annotation are not guaranteed to share a context if their properties, profiles, customizers, or configurations differ.

For example, two classes both using `@SpringBootTest` but with different active profiles:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class TestProfileContextTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileContextTest {
}
~~~

Two different profile configurations produce different contexts because beans, properties, and conditional configuration may differ.

Similarly, differing `@TestPropertySource` or dynamic property configurations can change the cache key. Using many distinct configuration combinations forces the suite to load many contexts and can substantially increase execution time.

### The Cache Is Bounded

The context cache has a size limit and uses a policy to evict least-recently-used contexts when space is needed. When a context is evicted from the cache, Spring closes that context to release managed beans and resources.

The cache lives within the JVM of the test process. If a build tool splits tests across multiple forked JVMs, each fork has its own cache. A context loaded in one fork is not automatically reused in another fork.

This explains why the same suite may restart contexts when tests are split across multiple processes or when entries are evicted from the cache.

### Observing the Cache

You can enable DEBUG logging for Spring TestContext's cache package to see contexts retrieved from cache, loaded fresh, or evicted. Example logging configuration in tests:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Cache logs help distinguish two situations:

- A test method runs again on an existing context.
- A new configuration forces Spring to load a different context.


## 7. @DirtiesContext Affects the Context Lifecycle

`@DirtiesContext` informs Spring TestContext that the context has been altered in a way requiring cache eviction. When a context is marked dirty, the framework removes the corresponding context from the cache and closes it. A later test requiring the same configuration will have to load a new context.

Example:

~~~java
@SpringBootTest
@DirtiesContext
class ChangesApplicationContextTest {

    @Test
    void changesContextManagedState() {
        // Perform a change that prevents the context from being reused.
    }
}
~~~

The annotation can be placed at the class or method level depending on the scope of change. Common modes allow marking before or after a class/method, or before/after each test method. Choose the mode based on when the context is no longer safe to reuse.

Example at the method level:

~~~java
@Test
@DirtiesContext
void invalidatesContextAfterThisMethod() {
    // Modify bean state or configuration requiring context eviction.
}
~~~

Using at the class level:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationTest {
    // Tests in the class use this context.
}
~~~

`@DirtiesContext` is appropriate when a test modifies context or bean state in a way that cannot be safely restored. It carries a cost because the context must be rebuilt for subsequent tests.

Do not use this annotation as a general-purpose database cleanup command. It does not automatically roll back external transactions, delete files, clear messages in a broker, reset static fields, or undo requests sent to other services. Clean up the exact kind of resource that was modified.

## 8. Distinguishing Test Instance State, Bean State, and External Resources

When a test finishes, not all state is reset. Identify which layer each piece of state belongs to.

| State | Primary Lifecycle | What Happens After Each Test? |
|---|---|---|
| Local variables in test method | Method | Variables go out of scope after the method |
| Test instance fields with `PER_METHOD` | Test instance | A fresh instance is created per method; the old instance is not used for the next method |
| Test instance fields with `PER_CLASS` | Test class | Values may persist across methods |
| Singleton beans in context cache | ApplicationContext | May remain intact across many methods and classes |
| Request-scoped/session-scoped beans | Request or session | Depends on the corresponding scope lifecycle |
| Test-managed transaction | Test method | Typically ends and rolls back after test if configured by default |
| Database outside context | Database or container | Not automatically wiped just because the test instance ended |
| Files, messages, or external service data | External resources | Requires a dedicated cleanup mechanism |

A commonly confusing example:

~~~java
@SpringBootTest
class CounterIntegrationTest {

    @Autowired
    CounterService counterService;

    @Test
    void firstTest() {
        counterService.increment();
        assertEquals(1, counterService.value());
    }

    @Test
    void secondTest() {
        // If CounterService is a singleton and not reset,
        // the value may have changed from the previous test.
    }
}
~~~

With a reused context, `CounterService` can remain the same singleton bean. JUnit creating a new test instance does not reset fields inside that bean.

One solution is providing an intentional reset method for test fixtures, or designing services not to retain per-request mutable state. If the state is persistence data, prepare and clean up the database using an appropriate mechanism.

## 9. Test Transaction Lifecycle Is Not the Context Lifecycle

Spring TestContext can manage transactions for tests via `TransactionalTestExecutionListener` when the test is annotated with `@Transactional` and a suitable transaction manager exists.

Example:

~~~java
@SpringBootTest
@Transactional
class OrderTransactionTest {

    @Autowired
    OrderRepository repository;

    @Test
    void persistsOrderInsideTestTransaction() {
        repository.save(new Order("ORD-1001", "CUS-42", 2));

        assertEquals(1, repository.count());
    }
}
~~~

In a typical test-managed transaction setup, a transaction starts for the test and rolls back afterward. This prevents database data from leaking between methods as long as all operations stay within that transaction.

However, the context can still be cached and reused. Rolling back a transaction does not close the context, recreate singleton beans, or reset arbitrary in-memory state.

Also distinguish tests running on the same thread from requests through a real server. With `@SpringBootTest(webEnvironment = RANDOM_PORT)`, the HTTP request is handled on a server thread in a separate transaction. The transaction bound to the test method does not automatically encompass that request's transaction. If the request writes data, the test needs its own data cleanup strategy.

Several transaction callbacks have distinct ordering:

- `@BeforeTransaction` runs before the test transaction begins.
- `@AfterTransaction` runs after the test transaction ends.
- `@BeforeEach` and `@AfterEach` are JUnit lifecycle callbacks coordinated alongside Spring TestContext.

When checking data before or after a transaction, use the corresponding transaction callbacks rather than assuming all callbacks execute within the same transaction.

## 10. Bean Lifecycle and Context Lifecycle

`ApplicationContext` manages bean lifecycles. When a singleton bean is created, Spring can perform dependency injection, invoke aware callbacks, apply bean post-processors, call init methods, and put the bean into service. When the context closes, Spring invokes destruction callbacks on appropriately managed beans.

Example of a bean with callbacks:

~~~java
@Component
public class ResourceRegistry {

    @PostConstruct
    void initialize() {
        // Prepare resources when bean is created.
    }

    @PreDestroy
    void close() {
        // Release resources when bean is destroyed.
    }
}
~~~

If the context is cached across multiple tests, `@PostConstruct` does not run again after each test method. It runs when the bean is created in the context. Likewise, `@PreDestroy` does not run after each method; it runs when the bean is destroyed with the context or per its corresponding lifecycle mechanism.

This matters for beans holding connections, thread pools, schedulers, or long-lived resources. If a test wants to verify init/destroy callbacks, test the context or bean lifecycle in a properly scoped test.

Do not manually close a context managed by Spring TestContext just to clean up after each test. Closing the context manually can leave the cache holding a closed context and cause subsequent tests to fail. Let TestContext manage the cache and use `@DirtiesContext` when context eviction is genuinely needed.

## 11. When Is a New Context Created and When Is It Reused?

You can use the following table to identify behavior:

| Situation | Typical Behavior |
|---|---|
| Two test methods in the same class, same config | Share the loaded context |
| Two test classes with the same cache key | Can share the context |
| Different active profiles | Load separate contexts |
| Different property sources or context customizers | Can produce different cache keys and load separate contexts |
| Test marked `@DirtiesContext` | Context is evicted from cache and closed per mode |
| Cache full and old context evicted | Evicted context is closed |
| Test running in another JVM fork | Uses that JVM's separate cache |
| JUnit creating a new test instance | Does not mean a new context is created |

The phrase "can share" is important: Spring reuses the context when configurations produce the same cache key and the context remains in the cache. If the context was evicted or marked dirty, the framework reloads it.

Do not deduce that a context is reused solely because two classes both have `@SpringBootTest`. Inspect profiles, properties, configuration classes, context customizers, and cache logs when you need to determine this accurately.

## 12. Testing Safely When Contexts Are Shared

Because contexts and singleton beans can be shared, tests must control state.

**Do not let tests depend on execution order.** Each method prepares its own data and verifies its own results. Tests should not require another method to run first to insert records or mutate beans.

**Limit mutable state in singletons.** Services should typically process request data via parameters and return values. If caches or stateful components are needed, provide clean reset or isolation mechanisms.

**Clean up resources per their proper lifecycle.** Transaction rollback handles in-transaction changes; containers have their own lifecycles; files, messages, and external services need dedicated cleanup.

**Be careful with parallel execution.** Two tests sharing a context may access singleton beans concurrently. If tests mutate shared state, they can race or affect each other's outcomes. Tests using `@DirtiesContext` must also be organized carefully under parallel execution because a context could be evicted while another test is using it.

**Use `@DirtiesContext` purposefully.** Mark dirty only when context state cannot be restored. If the problem is only database data, clean the database instead of reloading the entire context.

**Monitor the number of loaded contexts.** Cache logs reveal unnecessary configuration variations or contexts being evicted repeatedly. This is useful when a suite is slow due to booting the application many times.

## 13. Process for Analyzing a Spring Test

When a test behaves unexpectedly, check sequentially:

1. Is JUnit using `PER_METHOD` or `PER_CLASS` lifecycle?
2. Which test instance is the test method running on?
3. Through which extension or annotation is the test integrated with Spring?
4. From which configuration is the context loaded, and what cache key might it use?
5. Is the injected bean prototype, request-scoped, or singleton?
6. Does the failing state live in the test instance, a bean, a transaction, or an external resource?
7. When the test ends, which callbacks run and which kind of state is reset?
8. Is there any `@DirtiesContext`, profile, or property causing the context to be recreated?
9. If persistence data leaks, does the test transaction truly wrap that operation?
10. If running in parallel or across multiple JVM forks, is the test still independent?

For example, when a singleton bean holds a counter and the second test receives a non-zero value, check whether the context is cached and whether the bean is reset. When `@PostConstruct` runs only once despite multiple test methods executing, that is usually a sign that the context is being properly reused. When logs show contexts reloading repeatedly, inspect the cache key and annotations that alter configuration.

## Conclusion

The test lifecycle and the `ApplicationContext` lifecycle are two separate mechanisms. JUnit manages test classes, test instances, and callbacks around methods. Spring TestContext connects JUnit to contexts, dependency injection, transactions, and listeners. `ApplicationContext` manages beans, singletons, init/destroy callbacks, and can be cached for reuse across compatible tests.

Therefore, a new test instance does not mean a new Spring context. Test class fields and state inside singleton beans can have very different lifetimes. When designing tests, clearly identify whether state belongs to the test instance, the context, a transaction, or an external resource, and choose setup and cleanup accordingly.



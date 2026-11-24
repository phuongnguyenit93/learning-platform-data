# Why TestContext Retains ApplicationContext for Sharing

Starting a Spring application in every test can take significant time. Spring must read configuration, scan components, evaluate bean creation conditions, initialize singletons, set up proxies, configure integrations, and sometimes connect to a database or other services. If dozens of test classes need the same application configuration and recreate the entire context every time, the suite execution time will increase substantially.

The Spring TestContext Framework solves this problem with the **ApplicationContext cache**. When a test needs a context, the framework looks in the cache for a context already created with an equivalent configuration. If found, the test reuses that context. If not, Spring loads a new context and stores it in the cache so subsequent tests can use it.

Therefore, multiple test classes can share a single ApplicationContext within the same JVM process. This mechanism reduces startup time and avoids repeating bean creation, but it also has a consequence: singleton beans and state tied to the context are shared among tests that use the same cache entry. To take advantage of the cache safely, you need to understand context identification criteria, lifetime scope, reasons for creating a new context, and how to isolate test state.

## 1. The Cost of Creating an ApplicationContext

ApplicationContext is the container that manages the beans and configuration of a Spring application. Creating a context can involve many tasks:

1. Reading configuration classes, XML, component scans, and imports.
2. Processing bean definitions and configuration conditions.
3. Registering BeanFactoryPostProcessor and BeanPostProcessor instances.
4. Creating eager-init singletons.
5. Injecting dependencies and executing initialization callbacks.
6. Creating proxies for transactions, security, caching, or aspects.
7. Setting up web infrastructure, message listeners, clients, and other integrations.
8. Initializing connection pools, ORM metadata, or components with significant startup costs.

Not every context performs all of the above steps. A plain Java unit test does not create a Spring context. A slice test such as @WebMvcTest typically loads only a subset of beans. A @SpringBootTest may load most of the application and usually incurs a larger cost.

Suppose a suite has 40 test classes that all need the same web configuration. If each class creates a new context on its own, Spring may have to repeat the configuration and initialization process 40 times. When the cache is active, the context is created on the first run and subsequent tests can reuse that context.

<text>
  <escape>40 test classes with the same configuration:</escape>
</text>

~~~text
Without reusing the context:
Test 1  -> create context A -> run test -> close
Test 2  -> create context B -> run test -> close
Test 3  -> create context C -> run test -> close
...
Test 40 -> create context N -> run test -> close

With TestContext cache:
Test 1  -> create context A -> store in cache -> run test
Test 2  -> get context A from cache -> run test
Test 3  -> get context A from cache -> run test
...
Test 40 -> get context A from cache -> run test
~~~

The diagram above illustrates the case where tests have the same cache key and the context has not been evicted from the cache. In practice, a suite may need multiple distinct contexts due to using different profiles, properties, web configurations, bean overrides, or slice configurations.

## 2. How Does the TestContext Cache Work?

The Spring TestContext Framework provides a common mechanism to load and manage contexts for integrated test frameworks. In JUnit Jupiter, SpringExtension coordinates with TestContextManager. When a test needs an ApplicationContext, TestContext asks the context loader to retrieve the context from the cache or create a new one if it does not exist yet.

Overview flow:

~~~text
Test class starts
       |
       v
SpringExtension / TestContextManager
       |
       v
Create or identify MergedContextConfiguration
       |
       v
Compute cache key from the merged configuration
       |
       v
Look up context in ApplicationContext cache
       |
       +---- Matching context found ----> Reuse context
       |
       +---- Not found -----------------> Load new context
                                             |
                                             v
                                      Store in cache
                                             |
                                             v
                                      Use for test
~~~

Test classes do not need to manage a Map holding contexts themselves. The framework handles identification, storage, retrieval, and cache lifecycle management.

### 2.1. What Is a Cache Key?

Spring does not rely solely on the test class name to decide whether a context can be reused. The framework builds a merged configuration, typically represented by MergedContextConfiguration, and uses that configuration as the basis for generating the cache key.

Two test classes can share a context when their required configurations are equivalent and produce the same cache key. If the configurations differ in a meaningful factor, Spring may create a separate context.

Important components involved in identifying the cache key include:

| Component | Example or meaning |
| --- | --- |
| locations | XML resources used to load the context |
| classes | Spring configuration classes |
| contextInitializerClasses | ApplicationContextInitializer classes |
| contextCustomizers | Context customizations, including many mechanisms such as @DynamicPropertySource and bean overrides |
| contextLoader | The context loader used |
| parent | Parent context in a hierarchy configuration |
| activeProfiles | Active profiles |
| propertySourceDescriptors | Descriptors of property sources declared for the test |
| propertySourceProperties | Inline properties in annotations |
| resourceBasePath | Web resource root when using @WebAppConfiguration |

The detailed list may evolve depending on the Spring version and extensions in use. The key point to remember is that the cache key reflects the merged context configuration, not just a class name or a single annotation.

### 2.2. Two Test Classes Can Share a Context

Example:

~~~java
@SpringBootTest
class OrderServiceTest {
    // Testing the service
}

@SpringBootTest
class CustomerServiceTest {
    // Testing another service
}
~~~

If two test classes use equivalent application configuration, profiles, properties, and context customizers, Spring can reuse the same ApplicationContext. Having different test class names does not automatically force Spring to create a new context.

Similarly, multiple test methods within the same class typically share that class's context. By default, JUnit Jupiter creates a new test instance for each test method, but the ApplicationContext managed by Spring is cached separately and can be re-injected from the same context.

### 2.3. Configuration Differences Create Separate Contexts

For example, two tests both use @SpringBootTest, but one activates the test profile while the other activates the integration profile:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {
}

@SpringBootTest
@ActiveProfiles("integration")
class OrderIntegrationTest {
}
~~~

Two different profile configurations can produce different cache keys, so Spring loads two separate ApplicationContexts. This is necessary if the profile changes the beans or properties that the test uses.

Similarly, the following differences can lead to separate contexts:

- Different lists of configuration classes.
- Different XML locations.
- @TestPropertySource with different properties or resources.
- Different active profiles.
- Different initializers.
- Different context hierarchies.
- Different web resource paths.
- Different bean overrides or context customizers.

Do not try to force tests to share a context if their configurations are genuinely different. The goal of the cache is to reuse equivalent contexts, not to use an arbitrary context for every test.

## 3. Within What Scope Does the Cache Exist?

The ApplicationContext cache is an in-memory cache tied to the JVM process. It is typically shared across test classes running in the same JVM and using the Spring TestContext Framework.

This has several consequences:

- Contexts are not saved to files to be reused in the next Gradle or Maven run.
- Contexts are not automatically shared between two independent JVMs.
- If the build tool runs tests across multiple forks or worker processes, each process has its own cache.
- When the JVM terminates, the cache in that process no longer exists.
- If a context is evicted from the cache or marked dirty, Spring may have to recreate it when a later test needs the same configuration.

Therefore, a suite running in a single JVM can utilize the cache better than a suite split into many short-lived processes. Running in parallel across multiple JVMs can increase throughput, but it also requires each process to initialize its own contexts.

### 3.1. The Cache Is Not a System-Wide Singleton

The context cache is not a shared registry across all Spring applications running on the machine. It belongs to the test process and the Spring TestContext Framework within that process.

If a production application is running in another JVM, the test process does not obtain its ApplicationContext from that application. Each process has its own container lifecycle.

### 3.2. When Is a Context Closed?

A context can be closed when:

- The cache evicts the context due to capacity limits and the eviction policy.
- A test marks the context dirty using @DirtiesContext.
- The cache or process terminates and Spring Test's shutdown hook closes the remaining managed contexts.

The completion of a test method does not mean the context must close immediately. This is precisely what creates the reuse benefit.

## 4. Size Limit and Eviction Policy

The Spring TestContext Framework limits the number of contexts kept in the cache to avoid holding too many resources. By default, the cache has a maximum size of **32 contexts**. When the limit is exceeded, the cache uses an LRU (Least Recently Used) policy: the least recently used context may be evicted first.

When a context is evicted, Spring closes that context to release beans and resources managed by the context. If a subsequent test needs the corresponding configuration again, the context must be reloaded.

You can change the limit using a system property:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

The value above is just an example of increasing the limit to 64 contexts. You should only adjust it after observing cache statistics and understanding the consumption of memory, connection pools, threads, or other resources. Setting the cache size too high can cause the JVM to hold many heavy contexts simultaneously and create memory pressure.

### 4.1. Why Does LRU Make Sense?

A suite may use some context configurations frequently and others rarely. Keeping recently used contexts gives subsequent tests a higher chance of reuse.

Example:

~~~text
Cache maximum of 3 contexts:

Use A, B, C in sequence:
Cache = [A, B, C]

Next test uses A:
Cache still contains A, B, C; A becomes the most recently used context.

Test needs D:
The least recently used context is evicted.
The cache then contains the remaining contexts and D.
~~~

This is a conceptual description. The exact order depends on the cache access history in the suite.

### 4.2. Multiple Contexts Are Not Necessarily a Bug

A suite having multiple contexts can be a reasonable design if it tests different profiles, databases, security configurations, or web slices. A problem arises when nearly identical contexts are separated by unnecessary configuration differences.

For example, declaring different inline properties across many test classes just because each test wants a simple value can increase the number of cache keys. Consider using fixtures, shared properties, or a unified test configuration if those differences do not represent genuinely different environments.

## 5. Benefits of Reusing ApplicationContext

### 5.1. Reducing Test Suite Execution Time

The cost of creating a context only needs to be paid when a cache key is not yet in the cache or when a previous context has been evicted. Tests sharing the same configuration can start faster because they do not have to repeat the initialization process.

For a Spring Boot application with extensive auto-configuration, database pools, security, and web infrastructure, the time saved can be substantial.

### 5.2. Reducing Bean Initialization Work

Singleton beans are created once in the context and reused when other tests retrieve the same context. Expensive initialization steps such as creating clients, reading metadata, or setting up infrastructure do not need to be repeated for every test class.

### 5.3. Creating a Common Foundation for Multiple Tests

Test classes can share a standard application configuration. This helps the suite consistently reflect how the application is assembled and avoids each class creating its own version of the configuration.

### 5.4. Preserving Spring's Singleton Model

In a real application, singleton beans usually exist for the entire lifetime of the ApplicationContext. Sharing a context helps tests observe that model, including how beans are managed and wired together in the same container.

However, sharing also requires beans to be safe with respect to state and test ordering. The cache does not automatically make singleton beans stateless or thread-safe.

## 6. Consequence: Tests Share Beans and State

When multiple tests use the same context, singleton beans in that context are also shared. If one test modifies the mutable state of a singleton and does not restore it, another test may observe the altered state.

Example of an unsafe bean:

~~~java
@Component
class SearchCounter {
    private int count;

    void increment() {
        count++;
    }

    int count() {
        return count;
    }

    void reset() {
        count = 0;
    }
}
~~~

If test A calls increment and test B expects count to be 0, the outcome of test B depends on execution order unless there is a reset step or a new context.

The cache is not the cause of failing tests. The issue is that tests mutated shared state without an isolation strategy.

### 6.1. Distinguishing Between Test Instance and Spring Bean

By default, JUnit Jupiter creates a new test class instance for each test method. However, that does not mean the ApplicationContext and singleton beans are also created anew for each method.

Example:

~~~java
@SpringBootTest
class SharedContextTest {

    @Autowired
    SearchCounter searchCounter;

    @Test
    void first_test() {
        searchCounter.increment();
    }

    @Test
    void second_test() {
        // May observe modified state if the previous test did not reset it.
    }
}
~~~

Two test methods may have two different test instances while receiving the exact same SearchCounter singleton from the same ApplicationContext.

### 6.2. Database State Is Not Automatically Cached or Rolled Back

The ApplicationContext cache only manages contexts and the beans managed by those contexts. It does not automatically delete data in the database after each test.

Database state requires its own strategy:

- Use test transactions and rollbacks when appropriate.
- Create separate data for each test.
- Use explicit cleanup.
- Use a separate schema/database for a group of tests when needed.
- Use Testcontainers or a test database with an appropriate lifecycle.

A test sharing the same ApplicationContext that modifies the database can affect the next test if data is not isolated.

### 6.3. External State Also Needs to Be Managed

Effects such as sending messages, writing files, calling external APIs, creating data in another system, or modifying a distributed cache are not automatically undone just because a test method finishes.

Use test doubles, separate data namespaces, containers with controlled lifecycles, or appropriate cleanup for each dependency. Do not confuse Spring reusing the ApplicationContext with all application state being restored.

### 6.4. Parallel Test Execution

When parallel execution is enabled, multiple tests may access the same singleton bean in the same context simultaneously. If the bean holds mutable state or non-thread-safe collaborators, tests can cause race conditions.

For safe parallel testing:

- Prefer stateless singleton beans.
- Do not store test-specific data in mutable fields of a singleton.
- Have each test use distinct identifier data.
- Synchronize or isolate shared resources when business logic genuinely requires it.
- Do not rely on test execution order.

Do not disable parallel execution merely to hide a test design that depends on shared state. First, identify which state is being shared and the appropriate way to isolate it.

## 7. @DirtiesContext: When Should a Context Be Removed from the Cache?

@DirtiesContext marks the ApplicationContext as having been modified to the point where it should not be reused for subsequent tests. The Spring TestContext Framework will remove the context from the cache and close it according to the corresponding lifecycle. When another test needs that configuration, Spring will create a new context.

Example:

~~~java
@SpringBootTest
@DirtiesContext
class ChangesApplicationContextTest {
    // Test modifies configuration/context state that cannot be restored.
}
~~~

@DirtiesContext can be used at the method or class level, with modes specifying when to mark it dirty, such as before or after a method/class. The default is typically after the annotated scope.

### 7.1. When Is @DirtiesContext Appropriate?

It should only be used when a test genuinely modifies the ApplicationContext in a way that cannot be safely restored, for example:

- Modifying bean definitions or context structure during the test.
- Modifying shared singleton state with no proper way to reset it, and that modification is the target of the test.
- Testing a component whose behavior corrupts the context or alters container-managed state.
- Certain legacy integration tests whose context configuration cannot be isolated via fixtures.

If the test only modifies database data, files, messages, or mock state, there is usually a more suitable direct reset or cleanup mechanism.

### 7.2. Common Modes

| Mode | General meaning |
| --- | --- |
| BEFORE_METHOD | Close the context before the test method runs |
| AFTER_METHOD | Close the context after the test method |
| BEFORE_CLASS | Close the context before the class's test methods |
| AFTER_CLASS | Close the context after the class's test methods |
| BEFORE_EACH_TEST_METHOD | Class-level mode, evict context before each test method |
| AFTER_EACH_TEST_METHOD | Class-level mode, evict context after each test method |

Mode names and applicability scopes depend on the corresponding annotation attributes in the Spring version. Consult the Javadoc of @DirtiesContext in use when configuring a specific lifecycle.

### 7.3. @DirtiesContext Is Not a Command to Clean All Data

Removing a context from the cache closes the beans and resources managed by that context. It does not guarantee deleting data in an external running database, clearing messages in a shared broker, or undoing requests sent to another system.

If a test writes to a shared database, use transactions, separate schemas, or cleanup. If a test sends messages, use separate topics/queues or purge messages according to the test environment's mechanism. @DirtiesContext does not replace these strategies.

### 7.4. Overusing @DirtiesContext Slows Down the Suite

Every time a context is marked dirty, the cache benefit for that context is lost. The next test may have to restart the context and recreate pools, beans, and infrastructure.

If many test classes use @DirtiesContext, the suite may end up recreating contexts almost continuously. Check whether you can:

- Reset bean state through an explicit test API.
- Create fresh fakes or mocks for each test.
- Use transaction rollback for persistence data.
- Use separate fixtures instead of mutating singletons.
- Separate tests that mutate the context into a distinct group.

Only keep @DirtiesContext when the context is genuinely no longer safe to reuse.

## 8. Context Cache and @DynamicPropertySource

Testcontainers and mock services often provide dynamic ports or URLs. @DynamicPropertySource allows registering properties into the test context's Environment:

~~~java
@SpringBootTest
class DatabaseIntegrationTest {

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
~~~

@DynamicPropertySource methods are reflected through a context customizer in the cache configuration. When tests use the corresponding same configuration, Spring can reuse the context.

This requires attention if the resource providing the properties has a short lifecycle:

- The context was created with the URL or port of the current container.
- The container is stopped and restarted with a different port.
- The next test retrieves the old context from the cache.
- Beans in the context still retain the configuration used when the context initialized.

Dynamic property values should not be assumed to automatically re-read and reconfigure every bean on each cache hit. Properties are typically consumed when beans or infrastructure are created. If a resource changes its lifecycle, ensure the resource remains stable for as long as the context is reused, or mark the context dirty when necessary.

A common approach is to share the container with a lifecycle matching the group of tests that share the context. If each class starts and stops its own container while the context is cached across classes, connections to an expired endpoint may occur.

## 9. How to Tell If the Cache Is Working

The Spring TestContext Framework can log cache statistics. Enable DEBUG logging for the logger:

~~~text
org.springframework.test.context.cache
~~~

Example logging configuration in tests:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Cache logs can provide information about:

- Number of times a context was retrieved from the cache (hits).
- Number of times a new context had to be loaded (misses).
- Number of contexts currently held.
- Number of context evictions or related statistics depending on the version.

If a suite creates very many contexts, statistics help find the cause. Inspect cache hits/misses alongside the configurations of the test classes to identify which differences are generating new cache keys.

### 9.1. Signs of Low Cache Hits

Some common causes:

- Multiple test classes declare different classes or locations even though configurations are nearly identical.
- Inconsistent active profiles.
- Unnecessarily different inline properties.
- Different @TestConfiguration or @Import declarations.
- Different bean override lists.
- Different context customizers.
- Different web resource paths or context hierarchies.
- Suite splits tests across multiple JVM processes.

Not every miss needs to be fixed. If tests genuinely need different configurations, misses are normal.

### 9.2. Use Statistics to Investigate, Not to Chase Hit Rate

A high hit rate alone does not prove a good test suite. If you force tests to share a context even though they need different configurations, tests may no longer represent the environment they need to verify.

The goal is to avoid unnecessary duplicate context creation while keeping each test running under the right configuration. Optimize based on execution time, context count, memory, and test stability.

## 10. How to Organize Tests to Leverage the Cache

### 10.1. Reuse Common Configuration

If multiple test classes need the same configuration, they can share a configuration class or an appropriate base configuration class. Avoid creating configuration classes that only differ in name while declaring identical beans if they do not represent different environments.

Example:

~~~java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseApplicationTest {
}

class OrderServiceTest extends BaseApplicationTest {
}

class CustomerServiceTest extends BaseApplicationTest {
}
~~~

Subclasses can share a context if they do not add configuration that changes the cache key. However, do not create a base class solely to force every test into the same configuration. A base test should contain setups that are genuinely shared and easy to understand.

### 10.2. Group Tests by Slice and Purpose

A @WebMvcTest, @DataJpaTest, and @SpringBootTest usually need different contexts because their bean scopes differ. That is normal.

Group tests by purpose:

- Web contract tests use the same MVC slice if configurations are equivalent.
- Repository tests use the same data slice and database configuration.
- Integration tests use the full application context for flows requiring coordination across multiple beans.
- Plain unit tests create no context if Spring is not needed.

Do not turn every test into a @SpringBootTest just to share a single context. Large contexts can make tests slower and make failures harder to isolate.

### 10.3. Avoid Changing Properties Arbitrarily Between Classes

If each test simply needs different input data, pass the data into the test method or fixture instead of changing application properties. Properties should represent environment configuration, not an arbitrary way to pass test data.

If you genuinely need to test two different application configurations, keep two separate contexts and clearly document their purpose.

### 10.4. Use @DirtiesContext Appropriately

Before adding @DirtiesContext, ask:

- Does the test modify the ApplicationContext or only data?
- Does the bean have a safe reset API?
- Can a fresh fake/mock be used per test?
- Can the database be rolled back or cleaned up?
- Can external resources be created separately and closed with the right lifecycle?

If the issue is only data, you should not close the entire context to solve it.

## 11. Cache and Different Types of State

To avoid confusion, distinguish the following:

| Type of state | Managed by ApplicationContext cache? | Commonly used isolation approach |
| --- | --- | --- |
| Bean definitions and singleton beans | Yes, inside the cached context | Design stateless beans or reset state in a controlled manner |
| JUnit test instance | No | JUnit test lifecycle |
| Database data | Not directly | Transactions, fixtures, cleanup, separate schemas |
| Mockito mocks in context | Mock bean belongs to reused context; reset depends on integration/lifecycle config | Reset mocks or use appropriate mock configuration |
| Messages in broker | No | Separate queues/topics, purge, or broker container |
| Files on filesystem | No | Temporary directories and cleanup |
| External distributed cache | No | Separate namespaces, reset, or container |
| Testcontainers container | Not directly | Manage container lifecycle compatible with context |
| Static fields in JVM | Not part of context cache | Avoid shared state or reset explicitly |

ApplicationContext may hold references to connection pools, clients, or adapters. When the context is closed, managed beans can release resources according to their lifecycle. However, data that those resources have already written to external systems does not disappear automatically.

## 12. Common Misconceptions

### Each Test Method Has Its Own ApplicationContext

Incorrect in the usual case. JUnit may create a new test instance per method, but Spring TestContext caches contexts based on configuration. Multiple methods and multiple classes can share the same context.

### Each Test Class Always Creates a Context

Incorrect. If the cache key is equivalent and the context is still in the cache, another class can reuse the already created context.

### Two Classes Both Using @SpringBootTest Definitely Share a Context

Not necessarily. Profiles, properties, configuration classes, context customizers, bean overrides, and other components can make cache keys different.

### The Context Cache Is Saved Across Build Runs

No. This is an in-memory cache of a single JVM test process. When the process terminates, the cache is not retained for subsequent runs.

### Using @DirtiesContext Clears the Database

No. This annotation evicts the context from the cache and closes the context. External databases need their own cleanup strategy.

### @Transactional Always Reverts Every Change Made by a Test

No. A transaction only covers operations that participate in that transaction. HTTP requests running on server threads, asynchronous messages, and external side effects may fall outside the test's transaction.

### A High Cache Hit Rate Means Tests Run Correctly

No. A cache hit only indicates that a context was reused. It does not prove that tests are independent, data is cleaned up properly, or singleton beans do not leak state.

### Closing the Context Is a Safe Way to Reset Everything

No. Closing the context releases bean resources, but it does not undo side effects that already occurred in external systems.

## 13. Illustrative Example of Multiple Test Classes Sharing a Context

Suppose the application has the configuration:

~~~java
@SpringBootApplication
class SampleApplication {
}
~~~

Two test classes:

~~~java
@SpringBootTest(classes = SampleApplication.class)
@ActiveProfiles("test")
class ProductServiceTest {

    @Autowired
    ProductService productService;

    @Test
    void finds_product() {
        // Prepare isolated data and then verify behavior.
    }
}

@SpringBootTest(classes = SampleApplication.class)
@ActiveProfiles("test")
class CategoryServiceTest {

    @Autowired
    CategoryService categoryService;

    @Test
    void finds_category() {
        // Prepare isolated data and then verify behavior.
    }
}
~~~

If both test classes have equivalent merged context configurations, Spring can reuse the ApplicationContext. ProductService and CategoryService are beans within that same context.

This does not mean the tests must share business data. ProductServiceTest still needs to prepare its own products, CategoryServiceTest prepares its own categories, and both must clean up data or use appropriate transactions.

If one class adds @TestPropertySource with different properties, or adds a different bean override, the context may become a separate cache entry. This is a consequence of the configuration having changed.

## 14. Investigation Workflow When a Suite Starts Contexts Too Many Times

When a test suite is slow due to starting Spring multiple times, you can follow this sequence:

**Step 1 – Enable cache statistics.** Enable DEBUG for org.springframework.test.context.cache and record hits, misses, and the number of held contexts.

**Step 2 – Group test classes by configuration.** Compare classes, locations, profiles, properties, initializers, context customizers, and resource paths.

**Step 3 – Identify intentional differences.** Distinguish necessary separate contexts from differences caused by duplicated or inconsistent configuration declarations.

**Step 4 – Check @DirtiesContext.** Find tests that are evicting contexts from the cache and determine whether state can be reset or cleaned up directly instead.

**Step 5 – Check forks/processes.** Determine whether the build tool runs tests across multiple JVMs. Each JVM has its own cache.

**Step 6 – Check cache size.** If the number of valid contexts exceeds the default limit, consider adjusting maxSize after evaluating memory and resources.

**Step 7 – Re-run the suite and compare.** Measure overall time, number of context creations, memory, and stability; do not look solely at a single hit-rate metric.

## 15. Principles for Using the Cache Safely

- Treat singleton beans in a cached context as shared state among the corresponding tests.
- Prefer stateless beans or beans with an explicit reset API for test state.
- Have each test prepare the data it needs.
- Do not depend on execution order or state left behind by a previous test.
- Distinguish ApplicationContext lifecycle from database, broker, filesystem, and service lifecycles.
- Use @DirtiesContext when a context genuinely cannot be safely reused.
- Keep test configuration consistent when tests need the same environment.
- Accept separate contexts when profiles, properties, or bean configurations genuinely differ.
- Monitor cache statistics before increasing the cache limit.
- Ensure dynamic resources like Testcontainers live compatibly with how long the context is cached.

## Conclusion

TestContext retains ApplicationContext for sharing because initializing a Spring container can involve significant work and resources. The cache allows tests with the same configuration to reuse a context within the same JVM, reducing configuration scanning, bean creation, and infrastructure setup. The cache key is formed from the merged context configuration, so differences in configuration classes, profiles, properties, initializers, customizers, or web resources can produce separate contexts.

Reusing a context also means singleton beans are shared among tests using the same cache entry. Therefore, tests must manage bean state, database data, and external side effects with appropriate isolation mechanisms. @DirtiesContext should only be used when a context genuinely cannot be reused; using it too frequently forfeits cache benefits. By properly understanding JVM scope, cache keys, eviction, and lifecycle, you can organize a faster Spring test suite while maintaining independence and reliability.

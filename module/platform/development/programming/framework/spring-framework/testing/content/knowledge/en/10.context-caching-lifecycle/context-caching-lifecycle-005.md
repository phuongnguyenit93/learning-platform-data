# Cache Size Limits and Eviction of Least Recently Used Contexts

The Spring TestContext Framework caches created ApplicationContext instances so that multiple tests with equivalent configurations can reuse the same context. Initializing a context is often time-consuming because Spring must read configuration, create beans, inject dependencies, and potentially open connections to databases or infrastructure services. The cache reduces that cost within a test suite.

The cache does not keep every context indefinitely. Spring enforces a size limit and uses a Least Recently Used (LRU) eviction policy when the cache exceeds the limit. This mechanism keeps memory usage under control while prioritizing recently used contexts since they are likely to be requested again soon.

## 1. Why Does Spring Need to Cache ApplicationContext?

In a Spring application, creating an ApplicationContext can involve many tasks:

- Reading and processing Java configuration, XML, or component-scan configuration.
- Creating beans and resolving dependencies between them.
- Running bean post-processors and initialization callbacks.
- Creating connection pools, configuring ORM, or initializing integration components.
- Preparing web infrastructure, message broker clients, or other infrastructure components if required by configuration.

If every test class recreated an identical context, the initialization time would be repeated. The Spring TestContext Framework solves this by storing loaded contexts in a shared cache within the test process.

For example, two test classes using the same configuration:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryServiceTest {
    @Autowired
    private InventoryService inventoryService;

    @Test
    void findsAnItem() {
        inventoryService.find("SKU-01");
    }
}

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryRepositoryTest {
    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    void loadsRepository() {
        inventoryRepository.findBySku("SKU-01");
    }
}
~~~

If the configuration metadata of both test classes is equivalent, Spring can reuse the same ApplicationContext. Each class's test instance is still created by JUnit according to its lifecycle; the cache only retains the context and the beans belonging to that context.

The cache saves time, but it also means singleton beans can live across multiple test classes. Therefore, shared beans must manage state carefully so test results do not depend on execution order.

## 2. What Does the Context Cache Store?

Spring does not use the test class name alone as the cache key. It builds the key from metadata describing how to create the context, typically represented via MergedContextConfiguration. Important details can include:

| Configuration component | Impact on cache key |
|---|---|
| Resource locations | XML files or context configuration resources |
| Configuration classes | Declared @Configuration classes or configuration classes |
| Context initializer classes | Initializers used before context refresh |
| Context customizers | Context customizations, including various test bean override and dynamic property mechanisms |
| Context loader | Loader responsible for creating the context |
| Parent configuration | Parent context configuration in a hierarchy |
| Active profiles | Enabled Spring profiles |
| Test property sources | Descriptors and property values declared for the test |
| Web resource base path | Root path of the web application when using a web context |

If two test classes have the same corresponding configuration components, they can share a cache entry. If one attribute in the key differs, Spring may treat it as a different context configuration and load a separate context.

For example, tests sharing InventoryTestConfig and the same active profiles can share a context. However, if one test adds @ActiveProfiles("integration"), another test uses @TestPropertySource with its own values, or each test declares a different set of bean overrides, the keys can differ and the cache needs a new entry.

This explains why a project with many test classes can still use few contexts, or conversely have many contexts even when the number of test classes is not very large. The number of test classes is not the number of cache entries; the number of distinct context configurations is what decides.

## 3. Default Cache Size Limit

The Spring TestContext Framework sets a default limit of 32 ApplicationContexts. This value is the limit on how many contexts are kept in the cache at one time, not the number of test classes, beans, or test methods.

The property controlling the limit is:

~~~text
spring.test.context.cache.maxSize
~~~

It can be changed via a JVM system property or the SpringProperties mechanism. For example, setting the limit to 64:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

The value must be set before the TestContext Framework initializes the cache. Changing the system property in the middle of a running test suite is not a reliable way to adjust an already created cache.

### Configuring With Gradle

With Gradle Groovy DSL, pass the system property to the test process:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.test.context.cache.maxSize", "64"
}
~~~

With Gradle Kotlin DSL:

~~~kotlin
tasks.withType<Test>().configureEach {
    systemProperty("spring.test.context.cache.maxSize", "64")
}
~~~

A point to note is that the property must be passed to the JVM running the tests. Setting the property in the Gradle daemon without forwarding it to the test worker can leave the test process using the default value.

### Configuring With Maven Surefire

You can set the system property in Maven Surefire configuration:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <spring.test.context.cache.maxSize>64</spring.test.context.cache.maxSize>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

If the project uses Maven Failsafe for integration tests, configure the property in the exact plugin running those tests. Surefire and Failsafe may run in different phases or processes, so ensure every test group needing the cache receives the intended configuration.

There is no single optimal value for every project. Keeping the default of 32 is a reasonable starting point. Only increase or decrease it after observing context counts, cache hit rates, reload times, and memory consumption of the test process.

## 4. How Does the LRU Policy Work?

LRU stands for Least Recently Used, meaning the item whose most recent use is furthest in the past is selected for eviction first. When the cache is full and a new context needs to be added, Spring evicts the least recently accessed cache entry to keep the size within the limit.

Suppose a cache has maxSize of 3 and currently holds three contexts A, B, and C. The usage sequence is as follows:

1. Tests use A, then B, then C.
2. Another test reuses A, making A the most recently accessed context.
3. The next test requests context D.
4. The cache is full, so Spring evicts B because B is the least recently used context.
5. The cache holds A, C, and D.

The state can be visualized as follows:

| Operation | Contexts in cache from least recently used to most recently used | Result |
|---|---|---|
| Load A, B, C | A, B, C | Cache full |
| Access A | B, C, A | A is marked recently used |
| Load D | C, A, D | B is evicted |
| Access B | A, D, B | B must be reloaded; the next least recently used context is evicted if space is needed |

The order in the table illustrates the LRU concept. Accessing a cache entry updates that entry's recency. A context created long ago that is still used frequently can remain in the cache; creation age is not the sole criterion.

### What Happens to an Evicted Context?

When an entry is evicted from the cache, Spring closes the corresponding ApplicationContext according to lifecycle management rules. Beans with destruction callbacks or properly managed resources can be released, such as connection pools or components implementing DisposableBean.

If a subsequent test needs the evicted configuration again, Spring must create a new context. The test can still run normally; only the cost increases because initialization is performed again.

LRU eviction does not mean tests are marked as failed or the context is corrupted. It is a cache capacity management mechanism. It only affects performance and the number of context initializations.

## 5. Distinguishing LRU Eviction From @DirtiesContext

Both mechanisms can cause a context to no longer be in the cache, but for different reasons:

| Mechanism | Why is the context removed? | When does it happen? |
|---|---|---|
| LRU eviction | The cache needs to free space because context count exceeds maxSize | Automatically when the cache exceeds the limit |
| @DirtiesContext | A test declares that the context has been modified and is no longer suitable for reuse | At the declared BEFORE or AFTER mode |

LRU eviction is based on recency of use. @DirtiesContext is an explicit eviction request tied to a test class or method.

Example using @DirtiesContext after a test method:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class ContextStateMutationTest {
    @Test
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void changesContextState() {
        // Test alters context state in a way that cannot be safely reset.
    }
}
~~~

When the method completes, Spring removes the context from the cache according to the declared mode. This can happen even when the cache has plenty of space left. Conversely, a context can undergo LRU eviction even if no test marks it @DirtiesContext, simply because the cache needs space for other configurations.

Do not use @DirtiesContext merely to deal with leftover database data. If the data is inside a transaction, consider rollback. If the data was created by SQL scripts, use cleanup scripts. If state lives in a fake or resettable bean, provide an explicit reset method. Recreating the context is more expensive than cleaning only the state that needs cleaning.

## 6. Context Hierarchy and Context Eviction

Some test applications use a context hierarchy, where a child context inherits beans or configuration from a parent context. For example, web integration tests may use a parent context containing services and repositories, and a child context containing web-specific beans.

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
class WebApplicationContextTest {
    // Test uses a context hierarchy consisting of parent and child.
}
~~~

The cache can hold contexts in the hierarchy and track parent-child relationships. Removing a context in a hierarchy must respect this relationship so a child context is not reused based on a parent that has been closed or removed from the cache.

When using @DirtiesContext with a hierarchy, the hierarchyMode attribute lets you specify the eviction scope across hierarchy levels. The default EXHAUSTIVE mode can also evict related child contexts; CURRENT_LEVEL restricts eviction to the current level according to TestContext Framework rules.

With LRU eviction, do not assume parent and child contexts will remain independent forever. Let Spring manage relationships in the cache and avoid holding manual references to an ApplicationContext that has been evicted. If tests use a hierarchy and experience repeated context reloads, inspect cache logs alongside parent/child configurations to understand which entry is being created or evicted.

## 7. Factors That Increase the Number of Cached Contexts

A test suite can inadvertently create many distinct contexts when test classes declare slightly different configurations. Some common sources:

### Different Active Profiles

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
@ActiveProfiles("test")
class InventoryServiceTest {
}

@SpringJUnitConfig(InventoryTestConfig.class)
@ActiveProfiles("integration")
class InventoryRepositoryIntegrationTest {
}
~~~

Two test classes with different active profiles need different context configurations. Spring cannot share a single cache entry if the profile is a differing part of the key.

### Different Test Property Sources

~~~java
@SpringJUnitConfig(InventoryTestConfig.class)
@TestPropertySource(properties = "inventory.mode=fast")
class FastInventoryTest {
}

@SpringJUnitConfig(InventoryTestConfig.class)
@TestPropertySource(properties = "inventory.mode=accurate")
class AccurateInventoryTest {
}
~~~

Two different property sets can create two contexts. If a value only differs to satisfy a single test, consider whether that value can be tested via constructor or a smaller-scoped fixture configuration.

### Different Bean Overrides or Context Customizers

Bean replacement annotations like @MockitoBean or equivalent mock bean mechanisms can contribute to context customizers. Two test classes declaring different sets of mock beans can lead to different context keys.

For example, one test replaces InventoryRepository with a mock, while another replaces PaymentGateway with a mock. Even when sharing the same base configuration class, different bean override sets may cause Spring to need two contexts.

### Different Web Configuration or Context Hierarchy

Different web resource base paths, parent contexts, initializers, or context loaders can also make cache keys differ. When many modules or test groups use separate configurations, context counts can grow rapidly.

## 8. How to Reduce Context Cache Fragmentation

Context fragmentation occurs when many test classes produce many nearly identical cache keys that do not match. This fills the cache quickly and increases context reloads.

Several organizational approaches can help:

- Share test configuration classes when tests genuinely need the same environment.
- Standardize active profiles and shared test properties.
- Centralize shared bean override configurations when appropriate for the same group of tests.
- Avoid declaring arbitrary or unique properties per test class if a different context is not needed.
- Do not use @DirtiesContext as a default cleanup action.
- Separate plain Java unit tests from tests requiring a Spring context, reducing the number of tests that must create contexts.
- Use slice tests for functional groups such as MVC or JPA when only part of the configuration needs testing.

For example, if multiple test classes need the same profile and repository configuration, you can create a shared test configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ActiveProfiles;

@Configuration
class SharedInventoryTestConfig {
    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }
}

@SpringJUnitConfig(SharedInventoryTestConfig.class)
@ActiveProfiles("test")
class SharedInventoryServiceTest {
    // Tests sharing this profile and configuration can share the context.
}
~~~

Then, test classes share this configuration when they genuinely need the same context. Do not force tests with different infrastructure needs into a single context just to reduce cache key counts; configuration must reflect the actual environment each test needs to verify.

## 9. Observing Cache Hits, Misses, and Evictions

When a test suite is slow, you need to know whether Spring is reusing contexts or creating new ones continuously. The TestContext Framework logs cache statistics via the logger category:

~~~text
org.springframework.test.context.cache
~~~

Set the log level to DEBUG to observe cache size, maxSize, hit counts, miss counts, and information related to the context cache.

With Spring Boot, this can be placed in application-test.properties or test logging configuration:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

If the project does not use Spring Boot logging configuration, configure the logger in logback-test.xml or whichever logging backend the test suite uses. Example with Logback:

~~~xml
<configuration>
    <logger name="org.springframework.test.context.cache" level="DEBUG"/>
</configuration>
~~~

Statistics logs may show fields such as:

| Field | Meaning |
|---|---|
| size | Number of contexts currently held in the cache |
| maxSize | Cache limit currently in effect |
| parentContextCount | Number of parent contexts tracked in hierarchies |
| hitCount | Number of context lookup requests that found a cache entry |
| missCount | Number of lookup requests that did not find an entry and needed to load a context |

The hit ratio can be calculated using the formula:

\[
\text{Hit ratio} =
\frac{\text{hitCount}}{\text{hitCount}+\text{missCount}}
\]

For example, if the cache has 900 hits and 100 misses, the hit ratio is 90%. This is only an observational metric. A high ratio does not guarantee a fast test suite if each context load is very expensive; a low ratio may also be acceptable if each context is small and loads quickly.

### Reading Signals in the Logs

- size frequently hits maxSize and evictions appear: the cache is under pressure from the number of contexts.
- missCount rises rapidly: many new contexts are being requested or previous contexts were evicted.
- hitCount increases steadily with few misses after startup: the test suite is reusing configurations effectively.
- The same test class repeatedly loads a new context: check for configuration changes between runs, forked processes, or @DirtiesContext.

Combine logs with context load times and test execution times. Do not raise maxSize merely because the cache looks full often; verify whether eviction is actually increasing total test time.

## 10. Impact of Forked JVMs and Parallel Execution

The context cache is a static cache within the JVM process. Tests running in the same JVM can share the cache. If the build tool spawns multiple forked JVMs, each process has its own cache and must load its required contexts independently.

For example, Maven Surefire can run tests across multiple forks. Gradle can also use multiple test worker processes. In that case, maxSize applies to each individual process, not a single cache shared across the entire machine.

This has several consequences:

- Increasing the number of forks can improve wall-clock time via parallelism, but each fork may have to reinitialize contexts.
- Total memory may increase because each JVM retains its own cache.
- Cache statistics in one process do not reflect the caches of other processes.
- The same context configuration may be loaded multiple times in different forks.

Running tests in parallel within the same JVM also requires attention to singleton bean state and shared resources. The cache can be accessed by multiple tests concurrently; bean design must be safe for that execution model. Avoid letting one test mutate global state that another test is using.

## 11. Choosing maxSize Based on Project Characteristics

Increasing maxSize keeps more contexts, reducing the likelihood of reloading previously used configurations. In return, more bean graphs, connection pools, mock web servers, or integration resources may remain in memory longer.

Decreasing maxSize limits the number of held contexts and can reduce memory pressure. In return, the cache more easily evicts contexts needed again, causing Spring to recreate contexts and re-run initialization callbacks.

| Symptom | Possible adjustment direction to consider |
|---|---|
| Cache is often full, frequent evictions, and reloading contexts is expensive | Measure memory usage; if headroom remains, try increasing maxSize |
| Test process suffers memory pressure from holding many contexts | Consider decreasing maxSize or reducing the number of distinct context configurations |
| Many misses because each test has a different configuration | Standardize shared configurations before increasing the cache |
| Many tests only verify logic yet still load a Spring context | Convert those tests into plain Java unit tests |
| Each fork reloads the same configuration | Evaluate fork counts and the trade-off between parallelism and cache duplication |

Do not pick a huge value just to avoid every eviction. One context can hold connection pools or substantial resources; the more contexts retained, the greater memory and resource consumption can be. Conversely, setting maxSize too low forces the test suite to recreate contexts continuously.

A tuning workflow can consist of:

1. Run the test suite with the current configuration and enable DEBUG logging for the cache.
2. Record maxSize, size, hitCount, missCount, and execution time.
3. Identify distinct context keys and what causes them.
4. Reduce unnecessary configuration differences if tests can genuinely share contexts.
5. If eviction still causes significant reloads and sufficient memory remains, try increasing maxSize in a controlled step.
6. Re-run in the same environment and compare execution time, context load counts, and memory.

## 12. An Example of Configuring and Observing the Cache

Suppose a project uses Gradle and has many integration tests. You can configure the cache size and enable logging in a test profile:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.test.context.cache.maxSize", "48"
    testLogging {
        events "failed"
    }
}
~~~

In logback-test.xml:

~~~xml
<configuration>
    <logger name="org.springframework.test.context.cache" level="DEBUG"/>
    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

The root appender in the example must reference an appender declared in the project's actual configuration. If logging configuration already exists, simply add the corresponding logger category instead of creating a completely new configuration.

When running tests, watch logs to see whether the cache reaches 48 and when missCount increases. If the test suite only uses 12 distinct contexts, raising maxSize from 32 to 48 may bring no benefit. If there are 70 context keys and older contexts are frequently requested again, the cache may evict often; at that point examine both memory headroom and opportunities to reduce fragmentation.

Do not base final decisions on metrics from a single run if the CI environment, fork count, or parallelism differs from a developer machine. Compare under equivalent execution conditions.

## 13. Common Misconceptions

### Cache Size Is the Number of Test Classes

The cache stores ApplicationContexts by configuration, not test classes. Multiple classes can share one context; a single class can also use different configurations in separate test groups.

### If a Context Undergoes LRU Eviction, Tests Will Fail

Eviction merely removes the context from the cache and closes it. When needed again, Spring can create a new context. Tests still pass if configuration is valid and required resources are available.

### The Oldest Context Is Always Evicted

LRU considers recent access, not just creation time. A context created long ago that is still accessed can be kept.

### Increasing maxSize Always Makes Tests Faster

Holding more contexts can reduce repeated initializations, yet increases memory and live concurrent resources. If many distinct context keys exist due to unnecessary configuration, resolving fragmentation can be more effective.

### @DirtiesContext and LRU Are the Same Mechanism

@DirtiesContext requests removing a context because a test made it unsuitable. LRU automatically removes the least recently used entry when the cache exceeds its limit.

### The Context Cache Is Shared Across All Processes

The static cache is only shared within one JVM. Forks or test worker processes have independent caches.

### The Cache Stores Test Instances and Test Results

The cache only stores ApplicationContext instances. JUnit still manages test instances per lifecycle, and test results are not cached by the TestContext context cache.

## 14. Principles for Managing the Context Cache

- Understand that the cache defaults to holding at most 32 ApplicationContexts per JVM.
- Use spring.test.context.cache.maxSize to adjust the limit before tests start.
- Remember LRU evicts the least recently accessed context when the cache needs space.
- Recognize that an evicted context will be closed; the next request must reload it.
- Distinguish automatic eviction from explicit eviction via @DirtiesContext.
- Inspect components in the context cache key such as configurations, profiles, properties, initializers, customizers, and hierarchies.
- Use DEBUG logging on org.springframework.test.context.cache to monitor size, maxSize, hits, and misses.
- Evaluate both initialization time and memory before increasing or decreasing maxSize.
- Reduce context fragmentation by sharing configurations when tests genuinely need the same environment.
- Remember caches are independent across forked JVMs and pay attention to singleton beans when running tests in parallel.
- Only use @DirtiesContext when context state genuinely needs to be discarded; clean up data with transactions or SQL cleanup when more appropriate.

The cache limit and LRU policy allow Spring TestContext to reuse frequently used ApplicationContexts while keeping the number of retained contexts bounded. When a test suite has many configurations, understanding cache keys, monitoring hits/misses, and recognizing evictions helps find the true cause of repeated context loads. Adjusting maxSize based on timing and memory metrics helps balance performance with test process resources.

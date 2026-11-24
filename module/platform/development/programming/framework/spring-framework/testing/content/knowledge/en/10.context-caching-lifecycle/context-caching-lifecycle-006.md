# Reading Context Cache Statistics Logs

Spring TestContext can reuse a single `ApplicationContext` across multiple test classes that share the same configuration. This mechanism reduces application startup time in a test suite. When a suite runs slowly or continuously creates new contexts, cache statistics logs help determine how effectively Spring is reusing contexts.

Statistics show how many contexts are currently in the cache, the cache limit, and how many lookups succeeded or missed a context. Reading these numbers accurately helps distinguish a first-time context load from test configurations inadvertently producing many different cache keys, contexts being removed by `@DirtiesContext`, or cache overflow.

## Learning Objectives

After this lesson, you can:

- Enable DEBUG logging for the Spring TestContext cache.
- Recognize the cache statistics line in test output.
- Explain `size`, `maxSize`, `parentContextCount`, `hitCount`, and `missCount`.
- Read hit/miss trends to identify why contexts are loaded repeatedly.
- Relate cache misses to profiles, property sources, context customizers, and context hierarchies.
- Understand the impact of `@DirtiesContext`, cache limits, and JVM forks.
- Adjust the cache size when appropriate evidence exists.
- Use logs to investigate a slow suite without drawing wrong conclusions from a single statistics line.

## 1. Why Do We Need to Read Context Cache Statistics?

A Spring context may require component scanning, auto-configuration, bean creation, datasource setup, web server startup, and wiring dependencies. These steps often take longer than running a typical test method.

Spring TestContext keeps loaded contexts in a cache. When a subsequent test requests a context with the same configuration, the framework can retrieve the existing context. When the configuration differs or the context has been removed from the cache, the framework must load another context.

For example, a suite has 80 test methods yet only needs two application configurations. If compatible tests reuse two contexts, startup costs can be shared. If each test class inadvertently creates a different configuration, Spring may have to start the application many times.

Cache statistics help answer these questions:

- How many contexts are currently held?
- Does the cache frequently find the needed context?
- Are there unusually many cache misses?
- Has the cache reached its size limit?
- Is there a context hierarchy to account for?
- Are profile or property changes creating additional contexts?

Statistics are a diagnostic signal. A cache miss is not automatically an error: loading a context the first time a new configuration is used is normal behavior. You need to read the log sequence and cross-reference it with test configurations to understand the cause.

## 2. Enabling DEBUG Logging for the Context Cache

The Spring TestContext cache logger resides in the package:

~~~text
org.springframework.test.context.cache
~~~

Set this logger to DEBUG level so Spring records cache accesses and statistics.

### With Spring Boot

You can add it to `src/test/resources/application-test.yml`:

~~~yaml
logging:
  level:
    org.springframework.test.context.cache: DEBUG
~~~

If tests use the `test` profile, Spring Boot will load this logging configuration alongside the corresponding profile configuration.

Another option is setting the logging level in a dedicated test configuration:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Use a configuration source that matches how the project organizes tests. There is no need to enable DEBUG for the entire Spring package if the goal is only to monitor the cache.

### With Logback XML

In a project configuring logging with Logback, you can declare the logger:

~~~xml
<configuration>
    <logger
        name="org.springframework.test.context.cache"
        level="DEBUG"
    />
</configuration>
~~~

Place the logger in the logging configuration file actually used by tests, such as `logback-test.xml`.

### With a JVM System Property

You can enable the logger through the corresponding logging configuration of the logging framework in use. If the project uses Spring Boot, the `logging.level...` property is usually the most concise way.

After enabling DEBUG, run a test class or a group of tests that uses a Spring context. Look for lines containing the phrase:

~~~text
Spring test ApplicationContext cache statistics
~~~

If no logs appear, check whether the logging configuration is loaded during tests, whether the logger is configured at a higher level, and whether the test actually uses Spring TestContext or is just a plain Java JUnit unit test.

## 3. Identifying a Cache Statistics Line

An illustrative log line may look like:

~~~text
Spring test ApplicationContext cache statistics:
[DefaultContextCache@4a7c1d2f size = 3, maxSize = 32,
 parentContextCount = 0, hitCount = 42, missCount = 3]
~~~

The exact format and displayed fields may vary across Spring Framework versions. The example above is used to explain common statistics fields.

| Field | Meaning |
|---|---|
| `size` | Number of contexts currently held in the cache |
| `maxSize` | Maximum number of contexts the cache is allowed to hold |
| `parentContextCount` | Number of parent contexts tracked in context hierarchies |
| `hitCount` | Number of lookups that found a matching context in the cache |
| `missCount` | Number of lookups that did not find a matching context in the cache |

Read each field according to its exact role. `size` describes how many contexts exist at the moment the log is written; `hitCount` and `missCount` are cumulative lookup counters over the lifetime of that JVM's cache.

## 4. Understanding Each Metric

### size: Number of Contexts Currently Cached

Example:

~~~text
size = 3
~~~

Three contexts are currently held in the cache. This does not mean the suite only has three test classes or three test methods. Multiple test classes can share a single context if their configurations are compatible.

`size` can increase as Spring loads additional new contexts. It can decrease when contexts are evicted from the cache due to `@DirtiesContext` or the eviction policy when the cache reaches its limit.

### maxSize: Context Count Limit

Example:

~~~text
maxSize = 32
~~~

The default Spring TestContext cache has a size limit of 32 contexts in common Spring Framework configurations. The limit can be changed using the system property `spring.test.context.cache.maxSize`.

If a suite has many different cache keys, the cache can reach its limit and must evict older contexts to make room for new ones. Once a context is evicted, a test needing that configuration again may have to load the context once more.

Do not increase `maxSize` merely because `size` looks large. First verify whether the distinct contexts are genuinely needed or are arising from inconsistent profiles, properties, or customizers.

### parentContextCount: Parent Contexts in a Hierarchy

Spring supports context hierarchies, in which a child context can inherit beans or configuration from a parent context. When a test uses `@ContextHierarchy`, the cache must manage parent-child relationships.

Example:

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfiguration.class),
    @ContextConfiguration(classes = WebTestConfiguration.class)
})
class WebLayerIntegrationTest {
}
~~~

In this scenario, `parentContextCount` reflects parent contexts tracked in the cache hierarchy. For suites that do not use a context hierarchy, this value is typically 0.

Do not mistake `parentContextCount` for the total number of beans or test classes. It relates to parent-child context structures.

### hitCount: Number of Times a Context Was Found

Example:

~~~text
hitCount = 42
~~~

The cache has successfully served 42 context lookups. When a test requests a context whose cache key already exists and the context is still in the cache, that is a cache hit.

Hits usually indicate that multiple tests are reusing the same configuration. A rising hit count is a good sign when a suite has many test classes needing a shared context.

### missCount: Number of Times a Context Was Not Found

Example:

~~~text
missCount = 3
~~~

Three lookups failed to find a matching context in the cache. Spring may need to load a new context for those cache keys.

Misses typically occur when:

- A context configuration is used for the first time.
- A test class has a different active profile.
- Property sources or dynamic properties differ.
- Context customizers differ, such as different mock bean configurations.
- A test marks the context dirty and it is evicted from the cache.
- An older context was evicted because the cache reached its limit.
- A test runs in another JVM that does not yet have the context in its cache.

A single miss is normal. What you want to look for are repeated misses for tests that seem like they should share a configuration.

## 5. Reading Hits and Misses Through an Example

Suppose a suite runs three groups of tests:

- Group A uses the `test` profile and test database configuration.
- Group B has the same configuration as group A.
- Group C uses the `postgres` profile to verify PostgreSQL integration.

Simple flow:

~~~mermaid
flowchart TD
    A["Group A requests test context"] --> B["Cache miss"]
    B --> C["Spring loads test context"]
    C --> D["Group B requests same cache key"]
    D --> E["Cache hit"]
    E --> F["Group C requests postgres context"]
    F --> G["Cache miss"]
    G --> H["Spring loads postgres context"]
    H --> I["Next test reuses postgres context"]
    I --> J["Cache hit"]
~~~

An illustrative statistics sequence:

| Point in time | size | hitCount | missCount | Interpretation |
|---|---:|---:|---:|---|
| After group A loads context | 1 | 0 | 1 | First configuration not yet in cache |
| Group B uses A's context | 1 | 1 | 1 | Context reused |
| Group C uses a different profile | 2 | 1 | 2 | Second context needed |
| Next test uses postgres profile | 2 | 2 | 2 | Second context reused |

This table depicts a simplified flow to explain the metrics. In a real suite, Spring may look up the cache at multiple stages and log multiple times during test preparation. Therefore, do not map one statistics line to exactly one test method.

## 6. Evaluating Hit/Miss Trends

A quick way to view this is comparing hits to total lookups:

\[
\text{Hit ratio} =
\frac{\text{hitCount}}
{\text{hitCount} + \text{missCount}}
\times 100\%
\]

For example, with 42 hits and 3 misses:

\[
\frac{42}{42 + 3} \times 100\%
\approx 93.3\%
\]

This ratio indicates that most lookups found a context. It is a reference metric, not a Spring pass/fail standard.

Some ways to interpret trends:

- **Hits climb steadily, misses only climb when new configurations appear:** the cache is being used as expected.
- **Misses climb on almost every test class:** each class may be creating a different cache key, or contexts are repeatedly being evicted.
- **Size frequently hits maxSize:** the suite has many concurrent contexts or the cache limit is low relative to demand.
- **Low hits after a context is dirtied:** check the placement and scope of `@DirtiesContext`.
- **One group of tests loads contexts repeatedly:** compare profiles, properties, configuration classes, and context customizers across those classes.

A high hit ratio does not prove tests are independent or functionally correct. It only describes context lookup efficiency. Likewise, a low hit ratio can be justified if the suite intentionally tests many independent environments.

## 7. Relating Cache Misses to Test Configuration

Spring TestContext generates cache keys from context configuration metadata. Several components commonly cause cache keys to differ:

- `@ContextConfiguration` with different classes or resources.
- Different context initializers.
- Different context loaders or context hierarchies.
- Different `@ActiveProfiles`.
- `@TestPropertySource` with different properties.
- `@DynamicPropertySource` providing different values.
- Different context customizers, such as mock bean configurations or additional imports.
- Different web resource base paths.

Example of two test classes:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class OrderControllerTest {
}
~~~

Both classes have different active profiles so they normally need separate contexts. A cache miss when the second class starts is appropriate.

If both classes use the `test` profile yet still create separate contexts, compare the other metadata. For instance, one class having its own `@TestPropertySource` or declaring different mock beans can produce a different cache key.

For Spring Boot, mock bean annotations can affect context customizers. In newer versions, projects may use `@MockitoBean`; in older versions, you may see `@MockBean`. When multiple test classes declare different sets of mocks, contexts may not be reused.

Do not remove necessary configuration just to raise the hit ratio. The goal is to understand why contexts differ and only unify configurations when tests genuinely need the same environment.

## 8. Recognizing the Impact of @DirtiesContext

`@DirtiesContext` marks a context for removal from the cache. After the context is evicted and closed, another test requesting the same configuration may cause Spring to load a new context.

Example:

~~~java
@SpringBootTest
class ContextMutationTest {

    @Test
    @DirtiesContext
    void changesContextState() {
        // Mutates bean state making the context unsafe to reuse.
    }
}
~~~

If many tests use `@DirtiesContext` at the method scope, miss counts and context startup counts can increase substantially.

Check:

- Whether the annotation is placed on a method or class.
- Whether `methodMode` or `classMode` is appropriate.
- Whether the test genuinely alters unrecoverable context state.
- Whether the altered state can be reset via an API or separate fixture.

`@DirtiesContext` is not a tool to clean all data. If the issue resides in a database, file, or message broker, clean that exact resource. Reloading the context should only be used when the context or managed beans have been modified in a way that is unsafe to reuse.

## 9. When the Cache Reaches maxSize and Eviction Occurs

The cache has a size limit. When adding a context while the cache is at its limit, Spring uses a policy to evict the least recently used context to free space. The evicted context is closed.

Example:

~~~text
size = 32, maxSize = 32
~~~

This indicates the cache is at its limit at the time of the log. It does not by itself prove eviction occurred, but if many new contexts appear afterward and old contexts have to be reloaded, cache churn may be happening.

A possible sequence of events:

1. The suite loads many different configurations.
2. The cache reaches `maxSize`.
3. Spring evicts an old context.
4. A subsequent test needs the evicted configuration again.
5. Spring records a miss and loads that context once more.

In this situation, `missCount` can increase even though tests had used the corresponding context earlier.

The cache limit can be increased via a system property:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

For instance, add the JVM system property to the build tool's test run configuration. With Gradle, you can configure the test task:

~~~groovy
tasks.withType(Test).configureEach {
    systemProperty "spring.test.context.cache.maxSize", "64"
}
~~~

With Maven Surefire, pass the system property via plugin configuration or JVM arguments appropriate to the project setup.

Only increase the limit after logs show eviction is causing repeated context loads and the machine has sufficient memory. Each context can hold many beans, connection pools, and resources. Keeping many contexts simultaneously increases heap and external resource usage.

## 10. Distinguishing a Cache Miss From a Context Load Failure

A cache miss means no matching context was found in the cache. It does not mean the context failed to load.

When a context loads successfully, Spring places it in the cache so it can be reused. When loading fails, context initialization error logs and the underlying exception provide far more important information than the cache statistics line.

Recent Spring Framework versions have a failure threshold mechanism to limit retrying the same failing context repeatedly. When encountering this error, locate the first exception in the log. Subsequent skips may merely be consequences of the initial load failure.

Do not adjust cache size to fix bean creation errors, misconfiguration, unreachable datasources, or missing properties. Read the first stack trace and resolve what prevented the context from initializing.

## 11. The Context Cache Exists Within JVM Scope

The Spring TestContext cache resides in the memory of the JVM process. If the build tool runs tests across multiple JVM forks, each process has its own cache.

Example:

~~~text
Test JVM 1:
  loads test context
  reuses context within JVM 1

Test JVM 2:
  starts separately
  needs to load JVM 2's test context
~~~

Therefore, logs from two JVMs may both start with `size = 0`, `hitCount = 0`, and `missCount = 0`. This is normal behavior because caches are not shared across processes.

If the build tool runs multiple test tasks or modules in separate processes, do not add up counters from individual JVMs as if they belonged to a single cache.

When analyzing logs, note the test task, fork, and PID if provided in the output. Compare statistics within the same process to understand hit/miss trends accurately.

## 12. Investigation Workflow When a Test Suite Starts Contexts Too Many Times

When a suite is slow and you suspect the context cache is ineffective, follow this sequence:

1. Enable DEBUG for `org.springframework.test.context.cache`.
2. Run the exact group of tests that is slow and save the full log.
3. Locate `Spring test ApplicationContext cache statistics` lines.
4. Record `size`, `maxSize`, `hitCount`, and `missCount` at key points.
5. Identify which test configurations correspond to the initial misses.
6. Compare `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, configuration classes, and context customizers across test classes.
7. Search for `@DirtiesContext` and determine whether tests genuinely need to evict contexts.
8. Check whether the cache frequently hits `maxSize` and shows signs of eviction.
9. Determine whether tests run in a single JVM or multiple forks.
10. Only change cache size or test configuration after pinpointing the cause.

When comparing two test classes, build a metadata table:

| Attribute | Test A | Test B |
|---|---|---|
| Configuration classes | `ApplicationConfig` | `ApplicationConfig` |
| Active profiles | `test` | `test` |
| Test properties | None | `feature.enabled=true` |
| Dynamic properties | PostgreSQL container A | PostgreSQL container B |
| Mock bean configuration | One mock | Two mocks |
| Context hierarchy | No | No |

This table helps spot differences that can change the cache key. Dynamic values like container ports or random URLs must be understood in terms of how Spring creates context customizers; do not assume that merely having identical property names guarantees identical cache keys.

## 13. Common Mistakes When Reading Logs

- **Treating every cache miss as a bug:** a new context must miss on first use; investigate only when unexpected repeated misses occur.
- **Treating `size` as the number of tests:** this is the number of currently cached contexts.
- **Treating `maxSize` as the total contexts loaded across the suite:** this is the limit on simultaneously held contexts.
- **Assuming `hitCount` equals the number of test methods reusing a context:** the framework may look up the cache at multiple stages, so the counter reflects cache activity.
- **Combining counters from two JVMs as one cache:** each JVM has its own cache.
- **Raising `maxSize` immediately upon seeing misses:** misses may be caused by differing configurations or `@DirtiesContext`, not by an undersized cache.
- **Ignoring profiles and properties:** this metadata can make cache keys differ.
- **Confusing a miss with a context load failure:** a miss means a context was not found in the cache; load failures have their own exceptions.
- **Enabling DEBUG for all of Spring:** logs can become overwhelming and obscure statistics; enable only the cache package.
- **Concluding a suite is faster from hit ratio alone:** startup time, bean counts, databases, web servers, and external resources also affect total execution time.

## 14. Statistics Reading Exercise

Suppose at the end of a test run there is a line:

~~~text
size = 4, maxSize = 32, parentContextCount = 0,
hitCount = 76, missCount = 4
~~~

It can be read as follows:

- Four contexts are currently held in the cache.
- The cache has not reached the limit of 32.
- No parent contexts are recorded in a hierarchy.
- 76 lookups found a context.
- Four lookups did not find a context.

Reference hit ratio:

\[
\frac{76}{76 + 4} \times 100\% = 95\%
\]

Such a result shows the cache is reusing contexts quite well. However, if one of the four misses happens repeatedly in an important test group, its cause still needs investigation. An overall ratio can mask a test group reloading contexts repeatedly.

Another scenario:

~~~text
size = 32, maxSize = 32, hitCount = 30, missCount = 45
~~~

The cache is at its limit and misses exceed hits. Check for evictions, differing context configurations, profiles, property sources, mock beans, and JVM forks. Only after confirming cache churn should you consider increasing the limit.

## Conclusion

Context cache statistics logs show how Spring TestContext is reusing `ApplicationContext` instances. `hitCount` reflects how many times a context was found, `missCount` reflects how many times none was found, `size` indicates how many contexts are held, and `maxSize` sets the cache limit. `parentContextCount` provides additional visibility when using context hierarchies.

Enable DEBUG for `org.springframework.test.context.cache`, read statistics lines within the same JVM, and cross-reference cache misses against profiles, properties, context customizers, `@DirtiesContext`, and eviction. When you understand where context loads come from, you can shorten suite execution time while keeping test configurations accurate.


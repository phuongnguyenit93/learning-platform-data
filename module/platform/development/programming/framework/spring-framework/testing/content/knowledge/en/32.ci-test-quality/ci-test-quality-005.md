# Reducing Distinct Contexts Without Losing Verification Scope

## 1. Why Does the Number of Spring Test Contexts Affect CI Duration?

Spring integration tests typically need to create an `ApplicationContext` to instantiate beans, read configuration, run component scanning, create proxies, connect datasources, and initialize web components. A full context can take several seconds or longer depending on the number of beans and the infrastructure the application starts.

The Spring TestContext Framework caches `ApplicationContext` instances across test classes. When two test classes request the same context configuration, Spring can reuse the already created context instead of booting from scratch. This benefit only materializes when test configurations are compatible with one another.

A suite with many test classes that share just a few common configurations can run faster than a suite with fewer test classes where each class creates a distinct context. Small variations such as adding a custom property, a different profile, a different mock bean configuration, or an unnecessary `@DirtiesContext` can cause a cache miss and force Spring to create a new context.

The optimization goal is to **reduce duplicate context configurations** while preserving the proper test boundaries. A controller test still needs to verify MVC behavior; a repository test still needs to verify persistence; some integration tests must still start a real server when HTTP transport needs verification. Reusing contexts does not mean collapsing every test into the same test type.

## 2. How Does Spring Determine Whether a Context Can Be Reused?

The Spring TestContext Framework builds a configuration key from test metadata. When a new test's key matches a context already present in the cache, that context can be reused.

Key components that contribute to the key include:

| Configuration element | Example that creates a difference |
|---|---|
| `locations` | Two classes load different XML configuration locations |
| `classes` | One class uses app config A; another adds a custom configuration class |
| `contextInitializerClasses` | Two classes register different initializers |
| `contextCustomizers` | Different `@DynamicPropertySource`, bean overrides, or customizers provided by Spring Boot/the test framework |
| `contextLoader` | Different loaders used |
| `parent` | Different parent contexts in a context hierarchy |
| `activeProfiles` | One test enables profile `test`; another enables `integration` |
| `propertySourceDescriptors` | Different `@TestPropertySource` files used |
| `propertySourceProperties` | Different inline properties |
| `resourceBasePath` | Different web resource base paths |

The test class name by itself is not the criterion determining the cache key. Two differently named classes can still share a context if their effective configuration components match. Conversely, two classes in the same package both using `@SpringBootTest` can still create two contexts if their properties, profiles, imports, or bean overrides differ.

Example:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.audit=true")
class OrderServiceIntegrationTest {
}

@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.audit=false")
class AuditDisabledIntegrationTest {
}
```

The two classes require different configuration values for the same property. Spring cannot use a single context for both configurations because beans already initialized in the context must observe a consistent value.

## 3. What Scope Does the Cache Operate Within?

The context cache is a static cache inside the JVM process running tests. Test classes in the same JVM can share contexts if cache keys match. When a test JVM terminates, the cache in that process ends as well.

This has implications for CI and Gradle:

- Multiple test classes running sequentially in the same test worker JVM can reuse contexts.
- If the build forks multiple JVMs, each JVM has its own cache; a context in worker A is not shared directly with worker B.
- A fresh Gradle test run usually spawns a new test JVM, so it does not inherit the cache from the previous run.
- Running a single class in isolation may have to rebuild a context even though a prior full-suite run used a similar context.

The number of distinct contexts therefore directly drives startup cost within each worker process. Increasing parallel workers can lower wall-clock time while simultaneously causing multiple identical contexts to boot concurrently, increasing CPU and memory usage.

## 4. Use the Same Base Configuration for Tests with the Same Scope

If multiple test classes require the same kind of integration context, standardize the shared annotations and configuration. For example, service integration tests that all need the full application, the `test` profile, and a shared set of test configuration:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
abstract class BaseIntegrationTest {
}
```

Subclasses can reuse that configuration:

```java
class OrderServiceIntegrationTest extends BaseIntegrationTest {
    // Tests related to order service.
}

class PaymentServiceIntegrationTest extends BaseIntegrationTest {
    // Tests related to payment service.
}
```

Extending a base class does not automatically guarantee a cache hit if a subclass adds different properties, profiles, imports, or bean overrides. The value of a base class is helping tests follow one standard configuration and reducing accidental divergence.

Do not force every test into one giant base class just to compel context sharing. A controller slice and a real-server integration test have different goals; they legitimately need separate contexts.

## 5. Create Composed Annotations for Test Groups with Identical Setup

A custom annotation can bundle commonly used annotations so each class avoids declaring its own variation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(SharedMvcTestConfig.class)
public @interface MvcIntegrationTest {
}
```

Usage:

```java
@MvcIntegrationTest
class OrderMvcIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}

@MvcIntegrationTest
class CustomerMvcIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
```

Composed annotations give every class in the group the same web environment, profile, MVC setup, and test configuration. They reduce the risk that one class accidentally enables a different profile or omits a shared setting.

If an intentional variant is needed, create a separate composed annotation such as `@RealServerIntegrationTest` using `RANDOM_PORT`. Do not add customizable attributes to the annotation and pass different values per class if the goal is reusing the same context; differing values create differing context configurations.

## 6. Standardize Profiles and Property Sources

Profiles and properties are a common cause of context cache fragmentation. Define a default test configuration set for each test group.

For example, instead of each class declaring a different set of inline properties:

```java
@SpringBootTest(properties = {
        "feature.audit=true",
        "client.timeout=2s"
})
class OrderIntegrationTest {
}

@SpringBootTest(properties = {
        "client.timeout=2s",
        "feature.audit=true"
})
class CustomerIntegrationTest {
}
```

Consolidate shared settings into a stable properties file:

```properties
# src/test/resources/application-test.properties
feature.audit=true
client.timeout=2s
```

Then use the same profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTest {
}

@SpringBootTest
@ActiveProfiles("test")
class CustomerIntegrationTest {
}
```

Tests that share `application-test.properties` and the same application configuration have a chance to reuse the context. If a test genuinely needs to verify `feature.audit=false`, that is a different behavioral configuration. Keep that test in its own context or verify the policy with a unit test whose dependencies are controlled, depending on the scope needing verification.

Do not mutate system properties or environment state between tests to force an already initialized context to see new values. Beans may have read properties during initialization and stored them in fields. Configuration must remain stable throughout the context's lifecycle.

## 7. Restrict `@DirtiesContext` to Where It Is Truly Needed

`@DirtiesContext` instructs Spring to evict the context from the cache and close it. The next test needing the same configuration will have to build a new context.

Example:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyContextMutationTest {
}
```

This annotation is appropriate when a test mutates configuration state or singleton beans in a way that cannot be safely restored and could affect other tests. It must not be added merely because a test writes database records or invokes a service with side effects.

Cases that normally do not need `@DirtiesContext`:

- Tests writing data inside a test transaction that rolls back properly.
- Tests that can delete their own records by ID after running.
- Mock beans managed by Spring Test and reset according to its lifecycle.
- Tests using a stateful fake or spy that can be reset explicitly.
- Tests needing to clean up messages, caches, or files that have dedicated cleanup logic.

Handle state at the owner responsible for it. Database cleanup should clean the database; mock state should reset mocks; application caches should evict relevant entries; a context should only be evicted from the cache when the context itself has been dirtied.

## 8. Share Test Configuration Instead of Creating Per-Class Variants

`@TestConfiguration` lets you declare beans used only in tests. If multiple test classes need the same fake, clock, or test adapter, put the configuration in a shared class and import it identically.

```java
@TestConfiguration(proxyBeanMethods = false)
public class SharedIntegrationTestConfig {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2025-04-10T09:30:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    NotificationGateway notificationGateway() {
        return new InMemoryNotificationGateway();
    }
}
```

Tests importing the same configuration:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
class OrderNotificationIntegrationTest {
}

@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
class AccountNotificationIntegrationTest {
}
```

A fixed `Clock` bean keeps time-based results consistent. An in-memory gateway can record notifications for tests to inspect without calling an external service.

If one test needs a fake with different behavior, consider writing a unit test for that policy or a dedicated integration configuration. Never mutate the same singleton fake across parallel tests unless its state is isolated.

## 9. Mock Beans Can Make Context Keys Differ

Test bean overrides—such as `@MockitoBean` in newer Spring Framework versions or `@MockBean` in older Spring Boot releases—are registered via context customizers. Different sets of mock beans, qualifiers, and override styles can produce distinct context configurations.

Example of two classes declaring two different sets of mocks:

```java
@SpringBootTest
class OrderIntegrationTest {
    @MockitoBean
    PaymentGateway paymentGateway;
}

@SpringBootTest
class CustomerIntegrationTest {
    @MockitoBean
    EmailGateway emailGateway;
}
```

Different mock configurations can result in different context cache keys. If two test groups require the same set of mock overrides, standardize the mock set in a shared configuration or use a test configuration with shared fakes.

However, do not add mocks just so two classes share the same key. If a test needs to verify real bean wiring or interactions with a real dependency, replacing it with a mock sacrifices verification scope. Choose test doubles according to the test's objective first, then standardize configuration among tests sharing that objective.

For plain unit tests, use Mockito directly and instantiate the service via constructor injection. Do not spin up a Spring context merely to use `@MockitoBean`; that is both slower and complicates cache keys.

## 10. Use `@DynamicPropertySource` Consistently

`@DynamicPropertySource` is commonly used to inject dynamic endpoints such as Testcontainers URLs into the Spring Environment:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

`@DynamicPropertySource` methods participate in context customizers. If each test class defines a different property-registration method or different endpoints, they can generate different context keys and reduce reuse.

If multiple test classes can share the same container or test infrastructure, place the container and dynamic property registration method in a shared base class or shared configuration. This is only suitable when the container lifecycle and endpoint are genuinely safe to share.

Never let a supplier return a changing endpoint after the context has been created and the datasource bean already holds a connection pool pointing to the old value. When an endpoint changes, you need a new context or a test infrastructure design with a matching lifecycle.

A static container shared across classes can reduce startup overhead, but watch out for parallel tests, cross-test data, and container shutdown order. Context reuse does not replace schema or data isolation.

## 11. Keep Slice Tests Intentional

Not every test needs `@SpringBootTest`. One way to reduce context count while preserving verification scope is using the right test type for each behavior:

| Goal | Suitable test scope | Typical context needed |
|---|---|---|
| Calculation logic or pure service rules | JUnit unit test, instantiate service directly | No Spring context needed |
| Controller mapping, validation, JSON | `@WebMvcTest` + MockMvc | MVC slice |
| Repository queries and persistence mapping | `@DataJpaTest` | JPA slice |
| HTTP client or integration adapter | Test with mock HTTP server or narrow context | Necessary adapter context |
| Multiple beans collaborating in the app | `@SpringBootTest(MOCK)` | Full application context, no open port |
| Filters/connectors/HTTP stack on real server | `@SpringBootTest(RANDOM_PORT)` | Full context with embedded server |

For example, if you only need to verify that a controller forwards a command to a service and builds the right response, use `@WebMvcTest` with a mocked service. There is no need to start a database, message broker, and full application context.

If you need to verify controller, service, repository, and transaction coordination, use an appropriately scoped integration test. If you need to verify server port binding, cookies, or TLS, keep a dedicated subset of `RANDOM_PORT` tests.

Do not merge tests into a broader context solely to cut down the number of contexts. A narrow slice usually boots faster and verifies a clearer boundary.

## 12. Context Reuse Does Not Mean Sharing Test State

When two test classes share a context, they also share the singleton beans inside that context. This can affect state:

- Application caches may still hold data from an earlier test.
- In-memory fakes may retain lists of events or requests.
- Singletons with mutable fields can carry state across tests.
- Mock beans can be reset according to Spring Test's lifecycle, but reset configuration must match your version and test setup.
- Scheduled tasks or background workers may continue running between tests.

Therefore, design per-test fixtures and cleanup. For instance, a fake can expose `clear()`; repository tests can delete records by test ID; caches can evict keys created in the test.

```java
@BeforeEach
void resetFixture() {
    notificationGateway.clear();
    orderRepository.deleteAllByTestRunId(TEST_RUN_ID);
}
```

This example is only suitable if the fake and repository are designed for safe resetting. Under parallel execution, use a unique ID per test method instead of deleting all shared data.

Do not use `@DirtiesContext` to mask an unresettable fake or a test that fails to manage its data. Clean up state at the proper resource owner so the context can keep being reused.

## 13. Be Careful with Parallel Tests

A context cache can serve multiple test classes or methods sharing one context. If parallel execution is enabled, tests may access the same singleton beans and external resources concurrently.

Important principles:

- Never let tests mutate shared singleton state without isolation mechanisms.
- Use isolated data keyed by test ID or tenant.
- Never wipe entire database tables while other tests may be using those tables.
- Never share a single mock server expectation queue across tests if requests can arrive concurrently.
- Never change system properties or default timezones while other tests are running.
- If a resource cannot be used concurrently, apply a resource lock or disable parallelism for that test group.
- Wait for background tasks to finish before resetting fakes, databases, or containers.

Increasing Gradle worker count also does not share context caches across processes. It can cause multiple identical contexts to be created across multiple JVMs. Balance startup cost and memory when choosing parallelism levels.

## 14. Context Cache Size Limit and LRU Behavior

The Spring TestContext Framework enforces a cache size limit. The default is typically 32 contexts per JVM. When distinct contexts exceed the limit, the cache uses a least recently used (LRU) policy to evict the least recently used context. When a later test needs an evicted context, Spring must reinitialize it.

The limit can be changed via a system property:

```text
spring.test.context.cache.maxSize=64
```

Or passed as a system property when running tests:

```bash
./gradlew test -Dspring.test.context.cache.maxSize=64
```

Increasing cache size can reduce evictions if the suite genuinely requires many configurations. However, each context may hold beans, connection pools, executors, caches, and embedded servers. Raising the limit can significantly increase memory usage and open resources.

Do not raise the cache size to mask a suite with too many near-duplicate configurations. First investigate what is causing distinct cache keys. Only raise the limit once you understand the required context count and have measured memory appropriately.

## 15. Observe Cache Hits, Misses, and Created Contexts

You can enable logging for Spring TestContext caching to see how the suite reuses contexts:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Cache logs show hit/miss counts and cache statistics. When analyzing:

- **Hits increase** when tests reuse an existing context.
- **Misses increase** when Spring searches for or creates a context for a key not yet in the cache.
- **Size** indicates how many contexts are currently retained in the cache.
- **Evictions** indicate contexts removed due to cache limits or being marked dirty.

A suite with many test classes does not necessarily suffer many cache misses. Inspect statistics within a single test JVM process and correlate them with context startup logs.

If CI runs multiple worker JVMs, each process has its own cache. To understand total duration, inspect logs per worker alongside your build tool's fork/parallel configuration. An aggregate report that does not distinguish processes can make it look like contexts are not being reused.

## 16. `@DirtiesContext` and Its Modes

`@DirtiesContext` can mark a context dirty at various points, such as after a method or after a class. When a context is marked dirty, Spring closes and evicts it from the cache; the next test needing that configuration creates a fresh context.

```java
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
@Test
void changesSingletonConfigurationThatCannotBeRestored() {
    // Mutates context state affecting other tests.
}
```

Different modes let you choose when to evict the context, such as before or after a method/class. Choose the narrowest mode that satisfies the requirement and use it only when context state truly cannot be restored.

If a test only updates the database, roll back or clean up the database. If a test adds keys to a cache, evict those keys. If a test changes a system property, save and restore the value. If a test starts a mock server, shut down the mock server. None of these actions require evicting the entire Spring context.

`@DirtiesContext` is useful for tests verifying context-mutating behavior or legacy tests whose singleton state cannot be recovered. Used broadly, however, it largely defeats the cache and lengthens CI.

## 17. When Is a Separate Context Actually Needed?

Not every cache miss is a problem. Some differences reflect genuinely distinct test scopes:

- `@WebMvcTest` and `@DataJpaTest` have different slice configurations.
- `MOCK` and `RANDOM_PORT` tests have different web environments.
- Security tests enabling and disabling a filter configuration differ.
- Production-like profiles and profiles with fake external services have different goals.
- Tests verifying a feature flag set to false may need a different property context than true.
- Tests requiring different database/container endpoints cannot share an already initialized datasource connection pool.

Do not eliminate legitimate differences just to boost cache hits. Ask: is that difference necessary to verify a distinct behavior or risk? If yes, keep a separate context. If the difference is only redundant declarations or a value irrelevant to the test, standardize it.

## 18. A Practical Workflow to Reduce Context Count

1. Enable cache logging and record how many contexts are created in a representative CI run.
2. Group tests by scope: unit, MVC slice, persistence slice, full-context mock web, and real server.
3. Within each group, define standard profiles, properties, imports, and bean overrides.
4. Create composed annotations or base configurations for groups sharing identical setup.
5. Move simple mock-based dependency tests to plain unit tests if a Spring context is unnecessary.
6. Standardize `@TestPropertySource`, `@ActiveProfiles`, and `@DynamicPropertySource` where tests truly share values.
7. Remove unnecessary `@DirtiesContext`; replace with cleanup for data, caches, or fake state.
8. Keep real-server tests for boundaries requiring real HTTP verification.
9. Re-run the suite and compare cache hits/misses, context boot counts, duration, and memory.
10. If the cache still experiences heavy eviction, evaluate `spring.test.context.cache.maxSize` after duplicate configurations have been reduced.

## 19. Example of Organizing a Multi-Scope Suite

A module can organize its tests as follows:

```text
src/test/java/
  unit/
    OrderPricingServiceTest.java
    RefundPolicyTest.java

  mvc/
    OrderControllerTest.java
    CustomerControllerTest.java

  persistence/
    OrderRepositoryTest.java
    PaymentRepositoryTest.java

  integration/
    BaseIntegrationTest.java
    OrderWorkflowIntegrationTest.java
    PaymentWorkflowIntegrationTest.java

  http/
    BaseRealServerTest.java
    OrderHttpIntegrationTest.java
```

Unit tests instantiate objects directly with no context. MVC tests share a single `@WebMvcTest` pattern and consistent security/import setup. Persistence tests share the JPA slice setup. Integration tests share one profile and test configuration. Real-server tests use `RANDOM_PORT` and an HTTP client when verifying connectors or filters on a real server.

Example base class for the integration group:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
abstract class BaseIntegrationTest {
}
```

Example real-server group:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
@Import(SharedIntegrationTestConfig.class)
abstract class BaseRealServerTest {
}
```

The two groups have different web environments, so they properly use two contexts. Within each group, test classes sharing the same configuration can reuse the context. Each test preserves its own verification scope via its own data and assertions.

## 20. Common Mistakes When Optimizing the Context Cache

| Symptom | Possible cause | Resolution |
|---|---|---|
| Every test class boots Spring anew | Different profiles, properties, imports, or bean overrides | Compare context configurations and standardize shared parts |
| `@SpringBootTest` has many inline variants | Each class adds a custom property | Move shared settings into a profile/property file; keep separate contexts only when behavior must differ |
| Low cache hit rate despite identical annotations | Different `@DynamicPropertySource`, customizers, or parent contexts | Inspect cache logs and dynamic property methods |
| Contexts keep getting closed | Widespread `@DirtiesContext` usage | Clean up resources/data at the proper owner instead of evicting the context |
| Raising cache size causes high CI memory usage | Many contexts holding connection pools, beans, and servers | Reduce distinct context keys first, measure memory, then adjust cache size |
| Passes alone but fails in the suite | Shared context singletons or shared data | Reset fakes/caches, isolate data, and check parallel access |
| Moving all tests to full context for sharing | Loses benefits of slices and unit tests | Keep required scopes; share contexts only within the same configuration group |
| Shared container but pool points to old endpoint | Dynamic property changes after context creation | Keep endpoints stable across context lifetime or create a new context intentionally |
| Multiple worker JVMs still recreate contexts | Cache is scoped per JVM | Evaluate fork count and parallelism; do not expect cross-process caching |

## 21. Checklist for Preserving Verification Scope While Reusing Contexts

- Which tests only check pure logic and can run without a Spring context?
- Are controller, repository, and full-application integration tests divided into appropriate scopes?
- Do tests in the same scope share profiles, property sources, imports, and bean overrides?
- Which configuration differences are genuinely required to verify a different behavior?
- Is `@DirtiesContext` being used instead of data cleanup or fake resets?
- Does `@DynamicPropertySource` provide stable values throughout the context lifecycle?
- Do tests sharing a context isolate databases, caches, mock servers, and mutable singleton state?
- Can parallel tests overwrite or delete each other's data?
- Are real-server tests retained for port, connector, TLS, or HTTP filter behavior that requires verification?
- What do cache logs show for hits/misses and evictions in each JVM?
- Does cache size fit the memory retained by active contexts?
- Does CI use multiple worker processes that partition the cache?

Reducing the number of distinct Spring test contexts is a problem of standardizing configuration and managing state. Spring can reuse a context when tests request the same configuration; therefore, consolidate profiles, properties, imports, and bean overrides that are genuinely identical, while avoiding unnecessary context eviction. Keeping unit, slice, full-context, and real-server tests at their proper boundaries preserves verification scope. Context caching speeds up the suite, while test data and mutable state must still be isolated independently.

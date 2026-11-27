# Isolating Contexts, Property Sources, and Static State Between Test Cases

> **Chapter:** Testing
> **Module:** `SPRING_CLOUD_CORE` — understanding the core foundations of Spring Cloud in distributed systems, especially Spring Cloud Commons, Context, externalized configuration, and version compatibility with Spring Boot. Learners explore refresh scope, discovery, service registries, service communication, and testing/operating shared abstractions.
> **Focus:** A test may pass in isolation yet fail in the full suite because it reuses an ApplicationContext, mutates the Environment, or leaves state behind in static variables and shared caches. This lesson guides identifying each lifecycle, choosing the right isolation technique, and cleaning up state cleanly so tests remain stable when run sequentially or in parallel.

## 1. Why Do Tests Need State Isolation?

In a Spring Cloud application, a test's outcome can depend on multiple layers of state:

- Singleton beans inside the `ApplicationContext`.
- Property sources and active profiles in `Environment`.
- The Spring TestContext cache.
- The `RefreshScope` target cache.
- Static library caches, such as `CachedRandomPropertySource`.
- JVM system properties, `Locale`, or `TimeZone`.
- Databases, registries, message brokers, containers, and out-of-process resources.

These states have distinct lifecycles. Closing a context does not reset the JVM; clearing a scope cache does not restore property sources; creating a new context does not automatically clear system properties.

For instance, test A adds a `PropertySource` to `Environment`. Test B reuses the same context and reads that property even though test B never declared it. In another case, test A writes a value into a static cache; test B uses the same cache key and receives test A's result.

Without identifying where state is held, fixing tests by reordering execution only hides the root cause. Tests should set up the required inputs, perform assertions, and restore every piece of shared state they mutated.

### Learning Outcomes

After this lesson, learners can:

1. Distinguish the lifecycles of test methods, beans, contexts, property sources, scope caches, and JVM static state.
2. Explain why Spring TestContext reuses `ApplicationContext` instances.
3. Use `@DirtiesContext` at the right time and understand its cost.
4. Choose `ApplicationContextRunner` for isolated configuration testing.
5. Add per-test properties via `TestPropertyValues`, `@TestPropertySource`, or `@DynamicPropertySource`.
6. Restore system properties and static caches after each test.
7. Distinguish refreshing a bean from recreating the entire context.
8. Recognize risks when running tests in parallel.
9. Design repeatable setup, assertion, and cleanup workflows.

## 2. Identifying State Layers and Lifecycles

Before selecting an isolation technique, determine where the test is mutating state.

| State layer | Where it lives | How long it typically persists | How to isolate or restore |
| --- | --- | --- | --- |
| Local test variables | Test call stack/frame | End of method | No special cleanup needed |
| Test instance fields | Test object | Test framework lifecycle | Use explicit setup; do not depend on method order |
| Singleton beans | One `ApplicationContext` | Until context closes or bean is replaced | Create separate context or use `@DirtiesContext` when context is dirtied |
| `Environment` / `PropertySource` | `ApplicationContext` or shared `Environment` | Lifetime of `Environment` | Use per-context properties; remove manually added sources |
| Spring TestContext cache | Static cache in test JVM | Test suite/process lifetime, subject to eviction or shutdown | Intentionally alter context key or use `@DirtiesContext` |
| `RefreshScope` target cache | Context's refresh scope | Until target invalidated or context closes | `RefreshScope.refresh(...)` or `refreshAll()` |
| Static caches / static fields | Class loader / JVM | Until cleared, class loader collected, or JVM exits | Dedicated reset API; cleanup and synchronization lock |
| System properties | JVM `System.getProperties()` | Until modified/cleared or JVM exits | Save previous value and restore in `finally` |
| External resources | Database, registry, broker, filesystem, containers | Resource lifecycle | Use isolated namespaces/test data and clean up |

No single operation cleans all of these layers. For example:

- `@DirtiesContext` removes the context from cache and closes it, yet does not clear arbitrary static fields of the application.
- `RefreshScope.refreshAll()` clears the target cache of refresh-scoped beans, yet does not restart the context.
- `CachedRandomPropertySource.clearCache()` clears the static random cache managed by that API, yet does not change values already bound into existing beans.
- `System.clearProperty()` removes a system property, yet does not automatically update beans that already read it earlier.

When investigating a flaky test, write down: who owns the state, where it is created, and which operation restores it?

## 3. How Does Spring TestContext Cache ApplicationContext?

### 3.1. Identical Configurations Can Share a Context

The Spring TestContext Framework caches an `ApplicationContext` after its first load. Subsequent tests with matching context configurations reuse that context within the same test suite and process.

This speeds up the suite because Spring does not recreate every bean for each test class. However, it also means singleton beans and `Environment` can be shared across multiple tests.

Example:

```java
@SpringBootTest
class FirstIntegrationTests {

    @Autowired
    MutableStateService stateService;

    @Test
    void changesSharedState() {
        stateService.setValue("changed-by-first-test");
    }
}

@SpringBootTest
class SecondIntegrationTests {

    @Autowired
    MutableStateService stateService;

    @Test
    void expectsInitialState() {
        // May receive the same bean/context used by FirstIntegrationTests.
        assertThat(stateService.getValue()).isEqualTo("initial");
    }
}
```

If both classes share the same context configuration, the second test can observe state left behind by the first. That is an isolation bug; never rely on the second test happening to run first.

### 3.2. Factors Forming the Cache Key

Spring TestContext constructs the cache key from the metadata used to load the context. Key components include:

- `locations` and `classes` in `@ContextConfiguration`;
- `ApplicationContextInitializer` instances;
- context customizers, including `@DynamicPropertySource` and test bean overrides;
- `ContextLoader`;
- parent context in `@ContextHierarchy`;
- active profiles in `@ActiveProfiles`;
- descriptors and inline properties of `@TestPropertySource`;
- resource base path of `@WebAppConfiguration`.

When this metadata matches, two test classes can receive the same context. Adding a profile or changing a test property source produces a different cache key and makes Spring load a separate context.

Do not add dummy configurations merely to force every test onto a new context. Leverage the cache to reduce startup cost, and re-isolate contexts only when a test genuinely mutates state that cannot be safely restored.

### 3.3. The Cache Lives in the JVM

The context cache is a static cache inside the test process. If a build tool forks a separate JVM per test, the cache is not shared across those processes. When tests run in the same process, cached contexts can be reused.

Spring Framework 6.2 documentation notes a default limit of 32 contexts with an LRU eviction policy when the limit is exceeded. You can view cache statistics by setting the `org.springframework.test.context.cache` logger to `DEBUG`.

Example logging config:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Logs reveal cache hits/misses, current cached context count, and evictions. When a suite creates too many profile or property combinations, the cache can thrash and increase test duration.

### 3.4. Context Cache Is Not a Business Bean Cache

The context cache only stores and reuses the container. It does not reset data inside beans after each method. If a singleton holds mutable state, tests can affect subsequent tests even while the context is being reused exactly as designed.

Prefer:

- Stateless services in the application.
- Test data keyed by unique IDs.
- Cleaning up data created by tests.
- Avoiding mutating singleton beans in tests unless necessary.
- Marking the context dirty if structural changes or unrecoverable state mutations occur.

## 4. Using @DirtiesContext Appropriately

### 4.1. What Does the Annotation Do?

`@DirtiesContext` tells Spring TestContext that the context was modified or corrupted and must be closed and removed from the cache. The next test needing the same configuration will create a fresh context.

Class-level example:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextMutationIntegrationTests {

    @Autowired
    MutableStateService stateService;

    @Test
    void mutatesContextOwnedState() {
        stateService.setValue("temporary");
    }
}
```

Or method-level:

```java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void testThatCorruptsContext() {
    // Mutates singleton state that other tests cannot safely restore.
}
```

When the test completes according to the chosen mode, Spring closes the context and evicts it from the cache. Later tests requiring the same configuration receive a new context.

### 4.2. When Should You Use It?

Use `@DirtiesContext` when a test:

- Alters bean definitions or context structure.
- Mutates a singleton bean in an unrecoverable way.
- Mutates internal context state that ordinary cleanup cannot clean.
- Needs to test fresh container initialization behavior.

Do not use it merely because a test modified database records, system properties, or static caches. Restore state at the exact layer where it is stored.

### 4.3. Cost and Limitations

Closing a context entails closing connection pools, clients, listeners, schedulers, and other bean lifecycles. The next context must reinitialize all of those components, slowing down the test suite.

`@DirtiesContext` also does not automatically:

- Clear set system properties.
- Reset static fields in application classes.
- Clear static library caches.
- Restore modified files or databases.
- Stop external resources not managed by the context.

Therefore, combine it with cleanup tailored to out-of-context state. Never treat `@DirtiesContext` as a JVM-wide reset button.

## 5. Creating Small Fresh Contexts per Combination with ApplicationContextRunner

### 5.1. When It Fits

Spring Boot's `ApplicationContextRunner` is suited for testing auto-configuration or small bean sets across different combinations of properties and user configurations.

Each `run(...)` call creates a context for that check and closes it after the callback. Thus, tests can express every configuration combination without booting the entire application.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void createsFeatureWhenEnabled() {
        runner.withPropertyValues("feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getEnvironment()
                            .getProperty("feature.enabled"))
                            .isEqualTo("true");
                });
    }

    @Test
    void doesNotCreateFeatureWhenDisabled() {
        runner.withPropertyValues("feature.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(FeatureService.class)
                );
    }
}
```

The two tests define two separate Environments. There is no need to mutate global system properties or modify a shared context to produce both cases.

### 5.2. Testing a Specific Auto-Configuration

You can pass auto-configurations to the runner:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                AcmeClientAutoConfiguration.class
                        )
                );
```

Then use `withPropertyValues(...)`, `withUserConfiguration(...)`, or a custom class loader to test conditional branches. This is ideal for verifying default beans, application replacement beans, and missing-dependency conditions.

### 5.3. Limitations

`ApplicationContextRunner` does not replace all integration tests. It does not simulate full application lifecycles, real web servers, bootstrap, Config Server, or external registries. Use the runner for configuration and auto-configuration; use `@SpringBootTest` or specialized tests when verifying the application in a realistic environment.

## 6. Isolating Property Sources per Test

### 6.1. Environment Is an Ordered Collection of PropertySources

Spring `Environment` looks up properties across a list of `PropertySource` objects. When multiple sources contain the same key, the higher-precedence source determines the returned value.

An application may receive properties from:

- command-line arguments;
- Java system properties;
- OS environment variables;
- `application.properties` or `application.yml`;
- `@PropertySource`;
- programmatically added property sources;
- property sources supplied by Spring Cloud or the test framework.

When a test does not receive the expected value, inspect the effective value through `Environment` instead of looking at only one config file.

### 6.2. Using TestPropertyValues

Spring Boot provides `TestPropertyValues` to add key/value pairs to a `ConfigurableEnvironment` or `ConfigurableApplicationContext`.

Example:

```java
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment environment = new MockEnvironment();

TestPropertyValues.of(
        "acme.client.enabled=true",
        "acme.client.timeout=2s"
).applyTo(environment);

assertThat(environment.getProperty("acme.client.enabled"))
        .isEqualTo("true");
```

You can use this in unit tests or initializers. Each test should use its own `Environment` or context so one test's properties do not leak into another.

### 6.3. Using @TestPropertySource for Integration Tests

With Spring TestContext, you can declare dedicated properties for a test class:

```java
@SpringJUnitConfig(FeatureConfiguration.class)
@TestPropertySource(properties = {
        "feature.enabled=true",
        "feature.timeout=2s"
})
class FeatureEnabledIntegrationTests {
    // Assertions for enabled configuration.
}
```

You can use a separate properties file via `locations` to keep lengthy configuration out of annotations. `@TestPropertySource` is part of the context cache key metadata, so tests with different property sources get separate contexts.

When a test needs only a few static values, this is usually the clearest option. When values become available only after an external resource starts, use dynamic properties.

### 6.4. Using @DynamicPropertySource for Dynamically Addressed Resources

`@DynamicPropertySource` registers properties using a `Supplier`. The supplier is invoked only when the property is resolved. This is the standard way to inject Testcontainers hosts, ports, or URLs into `Environment`.

Illustrative example:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class RedisIntegrationTests {

    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine").withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port", redis::getFirstMappedPort);
    }
}
```

The Testcontainers extension manages the container lifecycle. Dynamic properties retrieve the host and mapped port from the running container without hard-coding random ports.

Dynamic properties have higher precedence than `@TestPropertySource`, OS environment variables, Java system properties, and property sources declared via `@PropertySource` or added programmatically. This helps selectively override values in tests.

### 6.5. Caution When Using DynamicPropertySource in a Base Class

If a base test class has `@DynamicPropertySource` and suppliers return different values across subclasses, the context cache can cause a subclass to reuse an old context. Spring Framework recommends considering `@DirtiesContext` on the base class so each subclass gets a context matching its dynamic properties.

Test this carefully when each subclass uses a different container or endpoint. Changing a `Supplier` return value alone does not guarantee an already-created context will reinitialize beans with the new value.

## 7. Isolating Static State and System Properties

### 7.1. Static State Outlives ApplicationContext

Static variables are shared across tests running in the same class loader/JVM. They can survive after a context closes and another opens.

Example:

```java
public final class GlobalFlags {

    private static boolean enabled;

    private GlobalFlags() {
    }

    public static boolean isEnabled() {
        return enabled;
    }

    public static void setEnabled(boolean value) {
        enabled = value;
    }
}
```

If one test calls `GlobalFlags.setEnabled(true)` without restoring state, another test can start with `true`. `@DirtiesContext` does not reset this field automatically.

Best of all is avoiding static mutable state in application code. Where it cannot be eliminated, provide an explicit reset API or save the old value to restore during cleanup.

### 7.2. CachedRandomPropertySource

Spring Cloud Context provides `CachedRandomPropertySource` to cache random values by key. In versions exposing this API, `CachedRandomPropertySource.clearCache()` clears the static cache managed by that property source.

Can be used in tests:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.cloud.util.random.CachedRandomPropertySource;

@ResourceLock("cached-random-property-source")
class CachedRandomConfigurationTests {

    @BeforeEach
    void clearBeforeTest() {
        CachedRandomPropertySource.clearCache();
    }

    @AfterEach
    void clearAfterTest() {
        CachedRandomPropertySource.clearCache();
    }
}
```

Verify the package and presence of this API in your exact Spring Cloud Context version. Do not assume every release has the exact same signature or behavior.

Clearing the cache is a global operation for that cache. Other tests using the same cache can be affected. When running in parallel, attach the same JUnit `@ResourceLock` to every test accessing this cache or disable parallel execution for that group. You can use distinct cache keys per test when the only goal is avoiding data collisions.

Note: clearing the cache does not alter values already injected into fields or bound into beans beforehand. To observe a fresh value after clearing, re-read the property in a new resolution or create a new context/bean as appropriate for your test.

### 7.3. System Properties Must Be Restored

System properties are JVM-wide state. If a test calls `System.setProperty`, save the previous value and restore it precisely in `finally`:

```java
@Test
void readsSystemProperty() {
    String key = "acme.test.mode";
    String previous = System.getProperty(key);

    try {
        System.setProperty(key, "isolated");
        assertThat(System.getProperty(key)).isEqualTo("isolated");
    }
    finally {
        if (previous == null) {
            System.clearProperty(key);
        }
        else {
            System.setProperty(key, previous);
        }
    }
}
```

Do not blindly call `System.clearProperty(key)` in cleanup if the property existed before the test. Doing so wipes configuration supplied by the test environment or build tool.

If the property is read during context initialization, ensure the test context is created after setting the property and is not reused from cache with previously bound values. For per-test configuration, `@TestPropertySource`, `@DynamicPropertySource`, or `ApplicationContextRunner` are usually easier to control than mutating system properties.

### 7.4. Other JVM States

Other global APIs must also be restored if tests mutate them:

- `Locale.setDefault(...)`;
- `TimeZone.setDefault(...)`;
- system properties;
- default uncaught exception handler;
- thread context class loader;
- custom application static singletons or registries.

Save the previous value, mutate within a narrow scope, and restore in `finally` or cleanup callbacks. Never assume a test class runs in a fresh JVM.

## 8. Distinguishing Refresh Scope from Recreating ApplicationContext

### 8.1. RefreshScope Caches Bean Targets

`@RefreshScope` creates a lazy proxy for a bean. The target bean is initialized when the proxy is used and stored in the scope's cache. When the cache entry is invalidated, the next call creates a new target.

Spring Cloud provides `RefreshScope.refresh(String)` to refresh one bean by name and `RefreshScope.refreshAll()` to clear the target cache of all beans in the scope.

Example:

```java
RefreshScope refreshScope = context.getBean(RefreshScope.class);

// Name is the bean name registered in the ApplicationContext.
refreshScope.refresh("remoteClient");
```

After refreshing, a new target is created on the next call through the proxy. The context and non-refresh-scoped singletons remain intact.

### 8.2. Refresh Scope Does Not Replace @DirtiesContext

The two operations serve different goals:

| Operation | Scope | Effect |
| --- | --- | --- |
| `RefreshScope.refresh("beanName")` | One refresh-scoped bean | Invalidates that bean's target cache |
| `RefreshScope.refreshAll()` | All beans in refresh scope | Invalidates target caches in the scope |
| `ContextRefresher.refresh()` | Environment and refresh scope via `ContextRefresher` | Updates Environment then refreshes scope |
| `@DirtiesContext` | Entire `ApplicationContext` | Closes context and evicts it from TestContext cache |

If a test only needs to verify that a refresh-scoped bean is recreated, use `RefreshScope`. If a test corrupted the context or modified container structure, use `@DirtiesContext`.

### 8.3. Changed Properties and Rebound Beans

Refreshing a bean does not automatically clear static library caches. Likewise, modifying `Environment` does not guarantee every singleton bean rebinds.

When testing configuration refresh:

1. Set initial properties.
2. Create the context and invoke the bean to instantiate the target.
3. Update the property source using the mechanism under test.
4. Trigger refresh or use the appropriate `ContextRefresher`.
5. Call the proxy again to recreate the target.
6. Verify the new bean reads the new value.
7. Clean up property sources and test resources.

Do not call `RefreshScope.refreshAll()` to work around leftover system properties or static caches. Clean up the exact state layer that was modified.

## 9. Parallel Test Execution and Shared State

### 9.1. Why Do Parallel Tests Easily Cause Race Conditions?

Two concurrent tests can modify the same static field, system property, cache key, file, or database record. Even when each test passes individually, they can overwrite each other's data when run simultaneously.

Example:

- Test A sets `feature.enabled=true`.
- Test B sets `feature.enabled=false`.
- Both read the system property.
- Results depend on exact timing of set/get/cleanup.

Similarly, test A calls `CachedRandomPropertySource.clearCache()` while test B is resolving the same cache key.

### 9.2. When Not to Run in Parallel?

Spring Framework warns against running tests in parallel when they use `@DirtiesContext`, bean overrides like `@MockitoBean`/`@MockitoSpyBean`, or mutate shared system state such as databases, brokers, or filesystems. Tests that concurrently mutate static caches or system properties also require explicit synchronization.

If you see errors stating that a context was closed or is no longer active mid-test, check whether another thread just evicted the context from cache via `@DirtiesContext` or cache eviction.

### 9.3. Using ResourceLock When State Is Intentionally Shared

JUnit Jupiter provides `@ResourceLock` so tests declaring the same resource name are synchronized against each other during parallel execution.

Example:

```java
@ResourceLock("system-property:acme.test.mode")
class SystemPropertyTests {
    // Tests in this group all modify this property.
}
```

All tests touching the same resource must share the exact lock name. One test omitting the lock can still trigger race conditions. `ResourceLock` only coordinates tests within the same JUnit execution; it does not lock external processes or separate test runners.

If a group of tests mutates many global resources, consider disabling parallel execution for that group or running it in a dedicated sequential suite.

## 10. Repeatable Setup and Cleanup Pattern

A well-structured test has three clear phases:

1. **Setup:** create isolated data, property sources, contexts, or external resources needed.
2. **Exercise and assertions:** run the behavior under test and verify outcomes.
3. **Cleanup:** restore modified state, close resources, and delete test-created data.

JUnit skeleton example:

```java
class IsolatedEnvironmentTests {

    private ConfigurableEnvironment environment;
    private String previousMode;

    @BeforeEach
    void setUp() {
        environment = new StandardEnvironment();
        previousMode = System.getProperty("acme.mode");
    }

    @AfterEach
    void tearDown() {
        if (previousMode == null) {
            System.clearProperty("acme.mode");
        }
        else {
            System.setProperty("acme.mode", previousMode);
        }
    }

    @Test
    void testUsesItsOwnEnvironment() {
        TestPropertyValues.of("acme.mode=test")
                .applyTo(environment);

        assertThat(environment.getProperty("acme.mode"))
                .isEqualTo("test");
    }
}
```

The `Environment` is created fresh in setup so test properties never leak into a shared context. The system property is saved and restored to its exact prior state.

For external resources, prefer lifecycle APIs from the test framework or container library. Cleanup must run even when assertions fail; use `try`/`finally`, `@AfterEach`, `@AfterAll`, or appropriate extensions.

## 11. Common Failure Scenarios

| Symptom | Possible cause | How to diagnose and fix |
| --- | --- | --- |
| Test passes alone, fails in full suite | Singleton bean or static state mutated by an earlier test | Locate where state lives; add cleanup or isolate contexts |
| `@SpringBootTest` reads stale property | Context reused from TestContext cache | Inspect cache key, property metadata, and dynamic suppliers |
| `@DirtiesContext` still fails to reset random value | Random cache is static state outside context | Use version-appropriate `clearCache` API and synchronize access |
| Test A affects Test B even after context closes | System property or static field still persists | Save/restore previous values in `finally` |
| Testcontainers allocates new port yet bean uses old port | Dynamic property supplier changed while old context was reused | Use distinct contexts per resource or `@DirtiesContext` when needed |
| Bean refreshed yet value remains stale | Bean not in refresh scope, property source unchanged, or static cache retains value | Check scope, `Environment`, and separate static caches |
| Parallel tests fail intermittently | Multiple tests mutating shared resource concurrently | Use `ResourceLock`, separate namespaces, or serialize execution |
| Context initializes too many times | Too many distinct context keys or excessive `@DirtiesContext` | Check cache logs and group tests with shared configuration |
| Test reads wrong property source | Source precedence differs from expectation | Inspect `Environment` and `PropertySources` list |
| Cleanup wipes pre-existing configuration | Cleared system property without restoring pre-test value | Save prior value and restore it accurately |

## 12. Diagnostic Workflow for State-Leaking Tests

When a test fails depending on execution order, proceed step by step:

1. Run the failing test in isolation to establish a baseline.
2. Run the failing test right after the test suspected of mutating state.
3. Determine whether the two tests share an `ApplicationContext` cache key.
4. Inspect which singleton beans hold mutable state.
5. Read `Environment` and list property sources in priority order.
6. Look for modified system properties or static variables.
7. Check library-specific caches such as `CachedRandomPropertySource` or `RefreshScope`.
8. Check whether external resources share databases/schemas/topics/queues/files.
9. Add cleanup at the exact layer storing the state.
10. Use `@DirtiesContext` only if the context itself was genuinely dirtied.
11. Re-run in different orders and with parallel execution enabled if the suite requires it.
12. If failures appear only under parallelism, synchronize shared resources or exclude the test from parallel execution.

A helpful technique is logging key values before and after tests: context ID, active profiles, target property, cache key, bean instance identity, and resource identifiers. Never log secrets or sensitive data.

## 13. Test Isolation Checklist

Before adding a test to the suite, confirm:

- [ ] The test declares all properties and profiles it needs.
- [ ] It does not depend on a preceding test method running first.
- [ ] It does not mutate shared singleton beans without cleanup.
- [ ] Property sources are added to an isolated context or removed after the test.
- [ ] Dynamic properties match the lifecycle of external resources.
- [ ] TestContext caching is understood and used intentionally.
- [ ] `@DirtiesContext` is used only when a context cannot be restored.
- [ ] Static caches have a reset API or dedicated keys.
- [ ] System properties are restored to their original values.
- [ ] `RefreshScope` refreshes the exact target bean when needed.
- [ ] Databases, brokers, registries, and filesystems use isolated data or cleanup.
- [ ] Tests mutating shared state do not run in parallel without synchronization.
- [ ] Cleanup runs even if setup or assertions fail.

## 14. Practice Exercises

### Exercise 1 — Two Classes Sharing an ApplicationContext

Two test classes share the same `@SpringBootTest` configuration. Class A mutates a singleton bean; class B expects initial state and fails when running the full suite.

Explain context caching and propose two solutions: cleaning up bean state or marking the context dirty when state cannot be restored.

### Exercise 2 — Dynamic Property Changing Across Subclasses

A base class registers `server.port` via `@DynamicPropertySource`. Each subclass starts a server on a different port, yet some tests still hit an old port.

Explain suppliers, context cache keys, and when `@DirtiesContext` is required.

### Exercise 3 — Random Cache Leaking Between Tests

Two tests both read `cachedrandom.test-node.uuid`. The second test receives the UUID generated by the first test.

Propose using distinct cache keys, `clearCache()`, and `@ResourceLock` under parallel execution. Explain why `@DirtiesContext` alone is insufficient.

### Exercise 4 — System Property Accidentally Cleared

A test sets `acme.mode=test`, then calls `System.clearProperty("acme.mode")`. In the full suite, another test loses a value that the build tool had configured beforehand.

Write cleanup code that saves and restores the original value, including when the property was originally absent.

### Exercise 5 — RefreshScope and Context Lifecycle

A `@RefreshScope` bean holds a downstream endpoint. A test changes the property and calls `RefreshScope.refreshAll()`, yet the result is still the old endpoint.

List the diagnostic steps: did the property source change, is the bean actually in refresh scope, was the proxy invoked again, and is there an independent static cache?

### Exercise 6 — Parallel Tests with a Race Condition

Two parallel tests both mutate a system property and share one database schema. They fail intermittently.

Propose using `ResourceLock` for JVM state, isolated namespaces for database data, and sequential execution for groups that cannot be isolated.

## 15. Quick Self-Check

1. Where does Spring TestContext cache `ApplicationContext` instances? **In a static cache inside the test process.**
2. Can two tests with identical context metadata share a context? **Yes.**
3. What does `@DirtiesContext` do? **Closes and evicts the context from cache so the next run creates a fresh one.**
4. Does `@DirtiesContext` clear static fields of the application? **No.**
5. What kind of tests is `ApplicationContextRunner` useful for? **Testing auto-configuration and small, isolated context combinations.**
6. Where can `TestPropertyValues` add properties? **`ConfigurableEnvironment` or `ConfigurableApplicationContext`.**
7. Which object does `@DynamicPropertySource` receive? **`DynamicPropertyRegistry`.**
8. When is a dynamic property's `Supplier` invoked? **When the property is resolved.**
9. Do dynamic properties take higher precedence than `@TestPropertySource`? **Yes.**
10. Does `RefreshScope.refreshAll()` close the entire `ApplicationContext`? **No, it invalidates the refresh scope's target cache.**
11. Does `CachedRandomPropertySource.clearCache()` clear values already bound into beans? **No.**
12. Why does a static cache need `ResourceLock` during parallel tests? **To stop one test from clearing or mutating state another test is actively using.**
13. Should `@DirtiesContext` be added to every integration test? **No, because re-creation is expensive and it does not reset out-of-context state.**
14. When cleaning up a system property, why save the old value? **To accurately restore whatever configuration existed before the test.**

**Core message:** For reliable Spring Cloud tests, isolate the exact layer of state involved. The TestContext cache retains `ApplicationContext` instances for speed; `PropertySource` determines values visible to beans; `RefreshScope` manages bean target caches; static fields, system properties, and library caches live outside the context. Using `ApplicationContextRunner`, test-specific property sources, controlled cleanup, and `@DirtiesContext` when warranted ensures suites produce repeatable results independent of execution order.

**References:**

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring/reference/6.2/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html)
- [Spring Boot 4.1 — Test Utilities and TestPropertyValues](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html)
- [Spring Boot — Testing Auto-configuration with ApplicationContextRunner](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Cloud Commons 5.0.4 — Application Context Services and RefreshScope](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

Some APIs and packages depend on your active Spring Boot/Spring Cloud version. Cross-check your project's compatible release train before copying examples into source code.

# Context Failure Threshold Is a Consequence of a Previous Load Failure

When Spring TestContext cannot create an `ApplicationContext` for a test, the first error usually holds the real cause: a missing bean, misconfiguration, unreachable database, failed migration, or a resource that failed to initialize. Other tests sharing the same context configuration may continue requesting that exact context. If Spring kept retrying after every failure, the logs would repeat the same stack trace many times and the suite would waste time.

Since Spring Framework 6.1, TestContext includes a **context failure threshold** to limit how many attempts are made to load a context with the same cache key. By default, the threshold is `1`: after the first failed load attempt, subsequent requests for that same configuration are immediately skipped and Spring throws an `IllegalStateException` reporting that the failure threshold has been exceeded.

The threshold message is a consequence of an earlier load failure, not the root cause. When you see it, locate the stack trace of the first load attempt for that same context configuration and fix that underlying failure first.

## 1. How Does the Failure Threshold Work?

Spring TestContext caches `ApplicationContext` instances so tests with equivalent configurations can share a context. The cache identifies a context using a merged configuration set, such as:

- Resource locations or loaded configuration classes.
- Context initializer classes.
- Context customizers.
- Context loader.
- Parent context.
- Active profiles.
- Property source descriptors and inline properties.
- Web resource base path if it is a web context.

This set forms the cache key (`MergedContextConfiguration`). For each key, Spring tracks the number of failed context creation attempts. When a load fails, the failure count for that key is incremented.

With the default threshold of `1`, the progression can be visualized as follows:

```text
Test A requests context K
        |
        v
Spring starts loading context K
        |
        v
Load fails (failure count = 1)
        |
        v
Test B requests the same context K
        |
        v
Failure count has reached threshold = 1
        |
        v
Spring skips the next load attempt
and throws IllegalStateException
```

Example of two test classes sharing a configuration:

```java
@SpringBootTest
class CatalogServiceTests {
    // Test using a Spring application context.
}

@SpringBootTest
class OrderServiceTests {
    // Equivalent configuration, so it can share the same cache key.
}
```

If Spring cannot create the context on the first attempt, the subsequent test class with the same merged configuration may receive an error like:

```text
java.lang.IllegalStateException:
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for [...]
```

This message indicates that Spring stopped retrying the context with that key. It does not explain why the first load failed. The root cause lies in the exception and stack trace produced during the first attempt.

## 2. Distinguishing Context Load Failures from Test Method Failures

The failure threshold only applies to **loading the `ApplicationContext`**. It is not a counter for all test failures.

| Scenario | Increments context failure count? | Reason |
|---|---:|---|
| Bean creation fails while refreshing context | Yes | The ApplicationContext was not created successfully |
| `@Configuration` or property prevents context startup | Yes | The error occurs while loading the context |
| Context initializer or context customizer throws an exception | Yes | Spring cannot finish creating the context |
| Database or external resource causes bean initialization to fail | Yes, if it causes the context load to fail | The error occurs during context initialization |
| Assertion inside a test method fails after the context was created | No | The context loaded successfully; the test method itself failed |
| Service throws an exception when called by a test method | No, if the context loaded successfully | This is a test execution failure, not a context load failure |
| HTTP response returns 500 on a request after the context is running | Not automatically | A request failure does not equal a context load failure |

Therefore, if a test method fails due to an assertion or business logic error, changing `spring.test.context.failure.threshold` will not fix the problem. Classify the failure before adjusting the threshold.

## 3. Default Value and How to Change the Threshold

The property controlling the threshold is:

```properties
spring.test.context.failure.threshold=1
```

Spring Framework 6.1 and later default to `1`. You can set a higher value if you want to allow more load attempts for the same context key before subsequent attempts are skipped.

Example setting the threshold to `2` for Gradle's test task (Groovy DSL):

```groovy
tasks.withType(Test).configureEach {
    systemProperty 'spring.test.context.failure.threshold', '2'
}
```

With Gradle Kotlin DSL:

```kotlin
tasks.withType<Test>().configureEach {
    systemProperty("spring.test.context.failure.threshold", "2")
}
```

You can set the JVM system property directly when launching the test JVM, or configure it via Spring's `SpringProperties` mechanism. What matters is that the property must be present before Spring Test starts loading contexts.

This is a Spring TestContext property read via the `SpringProperties` mechanism; it is not an ordinary application property. Placing it inside `@SpringBootTest(properties = ...)` or `@TestPropertySource` is not an effective way to configure the failure threshold, because those properties belong to the `Environment` of the application context being created.

A large value such as `1000000` can be used to effectively disable the threshold during diagnosis, since Spring will allow many more attempts. Only do this temporarily and intentionally; it can cause the same configuration error to repeat across many tests, producing long logs and slowing down the suite.

## 4. The Threshold Is Tracked Per Cache Key

The failure count is tied to the merged context configuration, not a single global counter across all tests in the JVM.

Example:

```java
@SpringBootTest
class CatalogTests {
}

@SpringBootTest
class OrderTests {
}

@SpringBootTest(properties = "feature.experimental=true")
class ExperimentalTests {
}
```

If the first two classes have identical merged configuration attributes, they can share the same context cache key. The third class has a different inline property, so it usually produces a different cache key. A failure on the first key does not automatically cause the second key to be skipped.

Differences such as active profiles, configuration classes, property sources, initializers, or context customizers can produce different keys. Conversely, two differently named test classes can still share the same context if their merged configurations are equivalent.

Do not intentionally add random properties or different initializers to evade the failure threshold. That only creates extra cache keys and can cause identical contexts to be loaded repeatedly, obscuring the original configuration bug.

## 5. Why Does Spring Skip Subsequent Attempts?

Once the threshold is reached, Spring does not invoke the load process again for that cache key on the current request. This avoids repeating an operation that already failed and reports errors quickly for tests sharing the same context.

This behavior is especially helpful in large suites:

- One configuration error does not produce hundreds of identical stack traces.
- Subsequent tests do not waste time trying to start a context that is already marked as failed under the threshold.
- The logs clearly show that an earlier load failed and subsequent attempts were skipped.

The threshold is not a retry policy for databases, containers, or HTTP services. It does not check whether an external resource is ready, nor does it wait for a dependency to recover. If the first load failed because a service was not ready, fix the readiness/wait strategy or resource lifecycle so the service is ready before the context creates beans that depend on it.

## 6. Finding the Root Cause from the First Load Attempt

When you see `ApplicationContext failure threshold exceeded`, find the first occurrence of a load failure for the same configuration. Read from the root exception up through the stack trace to identify the failing bean or initialization step.

Common causes:

| Symptom in the first error | Area to inspect |
|---|---|
| `NoSuchBeanDefinitionException` | Component scan, `@Import`, profiles, or test configuration did not register the bean |
| `UnsatisfiedDependencyException` | A bean's constructor dependency could not be resolved; inspect the nested cause to see which bean is missing |
| `BeanCreationException` | `@Bean` factory method, constructor, init method, or bean configuration threw an exception |
| `Could not resolve placeholder` | Missing property, misspelled property name, or property source not loaded |
| Connection refused / timeout | Database, broker, mock server, or external service has not started or has the wrong host/port |
| Migration or schema validation failed | Empty/wrong database version, incompatible migration, or test targeting the wrong schema |
| Address already in use | Test server binds a fixed port or a previous resource was not released |
| Exception from initializer/customizer | TestContext extension logic running before refresh failed or depended on unready state |
| Error appears only when running in parallel | Data, ports, files, singleton beans, or external resources are shared across tests |

Do not start by increasing the threshold. First, determine whether the initial error is a deterministic configuration bug or a transient dependency that was not ready yet.

## 7. Analyzing a Shared-Context Scenario

Suppose `CatalogTests` and `OrderTests` both use `@SpringBootTest` with the same profiles and properties. `CatalogTests` starts first, but the `InventoryClient` bean cannot be created because `inventory.base-url` has not been configured.

```text
CatalogTests
  -> requests context K
  -> InventoryClient fails to resolve inventory.base-url
  -> context K load fails
  -> failure count(K) = 1

OrderTests
  -> requests context K
  -> default threshold = 1 reached
  -> Spring skips the next load
  -> IllegalStateException: failure threshold exceeded
```

Fixing the property or the `InventoryClient` configuration is the real solution. Raising the threshold to `2` only makes Spring try once more; if the property is still missing, the second attempt also fails and later ones are still skipped.

Another scenario is a database container that starts slowly. If the context loads before the container is ready, a connection error can be the first failure. Ensure the container has started and dynamic properties point to the right mapped port before Spring creates the datasource. Raising the threshold is no substitute for managing resource startup order.

## 8. Distinguishing Failure Threshold from Context Cache Max Size

Spring TestContext has multiple cache-related properties, but they control different things:

| Property | Controls | Does not do |
|---|---|---|
| `spring.test.context.failure.threshold` | Maximum failed load attempts allowed for a cache key before skipping subsequent attempts | Does not increase cache capacity and does not fix configuration errors |
| `spring.test.context.cache.maxSize` | Maximum number of application contexts kept in the cache | Does not allow retrying a context that failed to load |

Increasing `cache.maxSize` does not fix `ApplicationContext failure threshold exceeded`. Similarly, increasing the failure threshold does not make the cache hold more contexts.

If a suite creates too many distinct contexts, inspect cache statistics, the number of distinct context configurations, and `spring.test.context.cache.maxSize`. If the same context configuration fails to load, find the root cause and check `spring.test.context.failure.threshold`.

## 9. When Should You Increase the Threshold?

In most cases, keeping the default of `1` is appropriate. You may temporarily raise the threshold when investigating a transient load failure and wanting to observe whether a subsequent attempt succeeds.

A few notes:

- If the error is caused by a missing bean or wrong property, retrying will not help; fix the configuration.
- If the error is caused by a database or container not being ready yet, prioritize wait strategies and explicit lifecycles.
- If the error is caused by a port collision, use random ports and clean up servers.
- If the error only happens under concurrent execution, isolate resources or synchronize tests instead of raising the threshold.
- If you raise the threshold for diagnosis, document why and restore the default once the cause is found.

Do not set an extremely large threshold permanently just to stop the logs from showing skip messages. Doing so can hide the fact that many tests are repeating the exact same context initialization failure.

## 10. Failure Threshold Diagnostic Workflow

1. Confirm whether your Spring Framework version supports the failure threshold (6.1 and later).
2. Find the `ApplicationContext failure threshold ... exceeded` message in the logs.
3. Locate the first failed load attempt for that same context configuration and read the root cause.
4. Determine whether the cache key is shared across multiple tests by comparing the merged configurations.
5. Fix the underlying cause: bean, property, profile, initializer, database, port, or resource lifecycle.
6. Re-run the affected test group with the default threshold to verify the context loads successfully.
7. Only increase the threshold temporarily if you need to diagnose recoverability of a transient error; do not use it as a substitute for fixing the cause.

The context failure threshold helps Spring TestContext stop repeated load attempts for an already-failed configuration. When you see the threshold message, treat it as a pointer leading back to the initial failed load. Fixing the root cause while keeping an appropriate threshold configuration makes your test suite report failures more concisely, faster, and more diagnostically.

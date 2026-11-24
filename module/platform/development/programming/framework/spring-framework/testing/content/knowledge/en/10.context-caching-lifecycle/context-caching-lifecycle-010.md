# Context Failure Threshold and How to Find the Root Cause of the First Error

When a Spring test fails to initialize an `ApplicationContext`, other test classes using the same configuration may continue reporting errors even though the original cause occurred only once. Starting with Spring Framework 6.1, Spring Test includes a **context failure threshold** mechanism to limit how many times a failed context is retried. By default, the threshold is `1`: after the first context load fails, subsequent attempts for the same context cache key are skipped.

As a result, logs may display a message such as:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context
```

This message is usually a consequence of an earlier failed context initialization. It does not reveal the root cause. To fix the error properly, locate the first failed context load, read its exception chain, and identify the bean, property, profile, resource, or backing service that prevented Spring from creating the context.

## 1. Why Does Spring Need a Failure Threshold?

The Spring TestContext Framework caches `ApplicationContext` instances to avoid reinitializing an identical context for each test class. If a context initializes successfully, test classes with the same configuration can reuse the cached context.

If a context cannot initialize, repeatedly trying to create the same context wastes time without yielding new information. For example, an unreachable datasource or a misconfigured bean can cause every test class sharing the same configuration to fail during bootstrap.

Before the failure threshold existed, a test suite could repeat context initialization and print many long stack traces for the same cause. Since Spring Framework 6.1, Spring tracks failed context load attempts and stops retrying once failures reach the configured threshold.

The goals of this mechanism are:

- Avoid repeating context initialization attempts already known to fail.
- Reduce wasted time and redundant log volume in the test suite.
- Make clear that subsequent errors may simply be repeated accesses to the same broken context.
- Encourage finding the cause of the first load rather than patching each affected test class.

The failure threshold does not fix Spring configuration, recover a context, or turn a failed initialization into a success. It only limits how many times Spring attempts to load a context with the same cache key.

## 2. Default Value and Configuration Property

Spring Test provides the property:

```text
spring.test.context.failure.threshold
```

The default value is `1`. This is the number of failed context loads allowed before subsequent attempts for the same context cache key are skipped.

| Threshold | Behavior for the same context cache key |
|---:|---|
| `1` | Allows the first attempt. If it fails, subsequent attempts are skipped |
| `2` | Allows up to two failed loads; the next attempt is skipped |
| `3` | Allows up to three failed loads; the next attempt is skipped |
| Very large positive integer | Effectively makes the limit unlikely to be reached in a normal test run |

The threshold is a positive integer. Configuring an invalid or non-positive value is not a safe way to disable the mechanism; use a sufficiently large positive integer if needed temporarily for diagnostics.

The property can be passed to the test JVM:

```bash
-Dspring.test.context.failure.threshold=3
```

Set the property before Spring Test begins using `DefaultCacheAwareContextLoaderDelegate` and initializing contexts. Configuring it at the test JVM level ensures every test in the process uses the same threshold.

### 2.1. Configuring in Gradle

With Gradle Groovy DSL, you can pass the system property to the `test` task:

```groovy
def contextFailureThreshold = providers
        .systemProperty('spring.test.context.failure.threshold')
        .getOrElse('1')

tasks.withType(Test).configureEach {
    systemProperty 'spring.test.context.failure.threshold', contextFailureThreshold
}
```

Or configure it temporarily when running a task:

```bash
./gradlew test -Dspring.test.context.failure.threshold=3
```

Gradle reads `-D` in the build execution JVM; the snippet above forwards that value to the test worker via `Test.systemProperty`. Without forwarding configuration, do not assume every system property on the Gradle build process automatically appears in the test JVM.

### 2.2. Configuring in Maven Surefire

With Maven Surefire, you can pass the property to the forked test JVM:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <spring.test.context.failure.threshold>3</spring.test.context.failure.threshold>
        </systemPropertyVariables>
    </configuration>
</plugin>
```

Or pass it via the command line if the project's Maven and Surefire configuration forwards system properties to the test JVM:

```bash
mvn test -Dspring.test.context.failure.threshold=3
```

If using Maven Failsafe for integration tests, configure the property for Failsafe's test JVM accordingly. Surefire and Failsafe can run in different forks/processes, so do not assume one plugin's configuration automatically applies to the other.

## 3. Threshold Is Applied Per Context Cache Key

The failure threshold is not a total failure counter across the entire suite. Spring tracks failed load counts associated with **each context cache key** in the test process's context cache.

A context cache key is built from metadata used to identify an `ApplicationContext`, such as:

- Configuration classes declared via `@ContextConfiguration` or related annotations.
- XML resources or other configuration resources.
- Context initializers.
- Active profiles.
- Property source descriptors and inline properties.
- Context customizers, including customizers produced by certain test annotations.
- Context loader and parent context in a hierarchy configuration.

Therefore, two test classes using the same configuration metadata can share a context cache key and both be affected by the failure threshold. Two test classes with different configurations can have different cache keys, so failure counts are tracked independently.

Example:

```java
@SpringBootTest
class OrderServiceTests {
}

@SpringBootTest
class OrderRepositoryTests {
}
```

If both classes have identical bootstrap metadata, Spring can use the same context cache entry. If initializing that context fails, the first test class may show the root cause, while the subsequent test class may encounter the exceeded threshold message.

Conversely, if one class uses a different profile or property source:

```java
@SpringBootTest
@ActiveProfiles("integration")
class OrderServiceIntegrationTests {
}

@SpringBootTest
@ActiveProfiles("repository-test")
class OrderRepositoryTests {
}
```

the two configurations can produce separate cache keys. One failing context does not automatically cause every other context in the suite to be marked failed.

Failure counts live in the test process JVM's context cache. If the build tool runs tests across multiple forks or worker JVMs, each process has its own cache and counter. Therefore, logs from different processes may show independent attempts.

## 4. Distinguishing the First Initialization Error From Later Threshold Errors

This is the most important point when reading logs.

### 4.1. First Context Load Fails

When Spring attempts to create the context for the first time and fails, the exception usually describes the actual problem. Some messages you may see:

```text
Failed to load ApplicationContext
```

```text
BeanCreationException: Error creating bean with name 'dataSource'
```

```text
Could not resolve placeholder 'partner.api.base-url'
```

```text
Connection refused
```

This is where investigation must begin. The stack trace may contain multiple outer wrapping exception layers, so read the entire `Caused by` chain and look for causes related to configuration or application components.

### 4.2. Subsequent Attempts Are Skipped

Once the failure count for the same cache key reaches the threshold, Spring throws an `IllegalStateException` with a message similar to:

```text
ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for ...
```

This time Spring does not re-run the entire context creation process. Consequently, the stack trace of the threshold error does not necessarily contain the original exception from the earlier initialization. It only indicates Spring skipped the attempt because that context key had already failed enough times.

### 4.3. Comparison Table

| Signal | First initialization | Subsequent attempts after exceeding threshold |
|---|---|---|
| Behavior | Actually creates `ApplicationContext` | Skips loading the context |
| Message | `Failed to load ApplicationContext` with causal exceptions | `failure threshold ... exceeded` |
| Useful information | Bean, property, profile, resource, or connection causing failure | Cache key exceeded threshold |
| Action to take | Find and fix the root cause | Go back to the log of the first failure |

If you focus only on the last test class reporting the threshold, you may waste time fixing the wrong test class that did not cause the original error.

## 5. How to Find the First Error in Logs

When a test suite has many test classes and long logs, search in the following order.

### Step 1: Locate the Threshold Message

Search for the string:

```text
failure threshold
```

or:

```text
skipping repeated attempt to load context
```

This message confirms that a cache key has failed enough times. Note the test class, context key, or accompanying configuration description to identify the affected test group.

### Step 2: Locate the Earlier Context Load Error

Within the same test run and the same JVM, find the earliest occurrence of:

```text
Failed to load ApplicationContext
```

Do not simply pick the very first error in the entire log file if the build runs multiple modules or forks in parallel. Cross-reference the test class and context metadata to confirm it belongs to the same cache key.

### Step 3: Read the Full Exception Chain

A stack trace might look like:

```text
IllegalStateException: Failed to load ApplicationContext
    ...
Caused by: BeanCreationException: Error creating bean with name 'orderClient'
    ...
Caused by: IllegalArgumentException: Could not resolve placeholder
    'partner.api.base-url' in value "${partner.api.base-url}"
```

In this example, the top-level error can be summarized generally as failing to load the context. The meaningful cause is that bean `orderClient` could not be created due to missing property `partner.api.base-url`.

Read from the outermost exception down through the `Caused by` entries, while checking the first frames belonging to application code or test configuration. Do not assume the deepest exception is always the complete explanation; some libraries wrap system errors in lower-level exceptions such as `IOException`, `SQLException`, or `ConnectException`.

### Step 4: Cross-Reference Test Class and Context Configuration

Inspect annotations and configuration that can affect the cache key:

```java
@SpringBootTest
@ActiveProfiles("integration")
@TestPropertySource(properties = "feature.payment.enabled=true")
class PaymentIntegrationTests {
}
```

Check:

- Does the test use a profile for which the current environment has not supplied properties?
- Is `application-integration.yml` or a required property source present?
- Is `@DynamicPropertySource` registering URLs, hosts, or ports from a container?
- Was the container or server started before Spring creates beans using the endpoint?
- Is a bean declared conditionally whose condition is not met?
- Does the test configure component scans, imports, or mock beans differently from application configuration?

### Step 5: Run the Failing Test Class Alone

After identifying the first test class, run that class by itself for more focused logs:

```bash
./gradlew test --tests "com.example.orders.OrderServiceIntegrationTests"
```

With Maven Surefire:

```bash
mvn -Dtest=OrderServiceIntegrationTests test
```

If the test class run alone still fails on the first bootstrap, the error does not depend on another test class corrupting the context cache. If the isolated test succeeds while the suite fails, investigate execution order, shared state, resource lifecycles, parallel execution, or JVM/configuration differences between the two runs.

## 6. Example: Missing Dynamic Property Causing Context Failure

Suppose a client requires a URL:

```java
@Component
class PartnerClient {

    private final RestClient client;

    PartnerClient(
            RestClient.Builder builder,
            @Value("${partner.api.base-url}") String baseUrl
    ) {
        this.client = builder.baseUrl(baseUrl).build();
    }
}
```

The test class intends to obtain the URL from a test server but forgets to register the property:

```java
@SpringBootTest
class PartnerClientTests {
    // Missing @DynamicPropertySource registration
}
```

The first time Spring creates the context, the `PartnerClient` bean cannot be initialized because the placeholder is unresolved. The initial error will appear as `Failed to load ApplicationContext`, followed by `BeanCreationException` and the placeholder-related cause.

If another test class uses the same context configuration, Spring may skip the next reload attempt due to the default threshold of 1. The log of the second test class only shows the threshold message, without repeating the full missing-property cause.

The fix is to register the property before the context needs to create the client:

```java
@SpringBootTest
class PartnerClientTests {

    @DynamicPropertySource
    static void registerPartnerProperties(DynamicPropertyRegistry registry) {
        registry.add("partner.api.base-url", () -> "http://localhost:49172");
    }
}
```

In a real test, the URL should come from a started server or container, such as `wireMock::baseUrl` or a supplier combining `getHost()` with `getMappedPort(...)`. The example above uses an illustrative URL to focus on the relationship between the missing property and the bootstrap failure.

After fixing, re-run tests in a fresh test JVM to ensure the context is created from scratch with the new configuration. If still using a JVM or test run holding the old context cache, terminate that run before evaluating results.

## 7. Common Root Causes

The failure threshold is merely a mechanism detecting repeated failed context loads. The root cause usually lies in configuration or a component the context needs to initialize.

| Cause category | Common symptoms | Investigation direction |
|---|---|---|
| Bean cannot initialize | `BeanCreationException`, `UnsatisfiedDependencyException` | Inspect the first bean that failed to create and its dependencies |
| Missing property | `Could not resolve placeholder`, configuration properties binding failure | Check profiles, YAML files, environment variables, and dynamic properties |
| Wrong profile | Beans or properties not registered | Check `@ActiveProfiles` and profile-specific configuration |
| Database unavailable | `SQLException`, `Connection refused`, timeout | Check URL, mapped port, credentials, container health, and lifecycle |
| HTTP dependency unavailable | Connect timeout or connection refused | Check server startup, base URL, and runtime port |
| Invalid Java/XML configuration | Parse exception, bean definition conflict | Check `@Configuration`, `@Import`, XML resources, and component scans |
| Incompatible dependencies | `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException` | Check dependency graph and runtime versions |
| Incorrect custom test context | Errors from `ContextCustomizer`, initializer, or loader | Check test metadata and extensions |
| Resource already stopped | Context cache remains while container/server is no longer running | Synchronize resource lifecycle with context cache |

Start from the specific exception in the first load. Not every `Failed to load ApplicationContext` is a dependency error or threshold bug; many cases are simply an incomplete test configuration.

## 8. Failure Threshold and the Context Cache

The context cache retains successfully loaded contexts for reuse. For contexts that fail to load, Spring records failure counts per cache key to enforce the threshold. This means a single configuration error can affect multiple test classes sharing the context, even if individual classes did not directly cause the bug.

### 8.1. Why Do Multiple Test Classes Report Errors Together?

Suppose three test classes share `@SpringBootTest` and the same active profile:

```java
@SpringBootTest
@ActiveProfiles("integration")
class CustomerServiceTests {
}

@SpringBootTest
@ActiveProfiles("integration")
class CustomerRepositoryTests {
}

@SpringBootTest
@ActiveProfiles("integration")
class CustomerControllerTests {
}
```

If the `integration` profile context fails on the first attempt, subsequent attempts with the same cache key may be skipped. Then, a test report may list three failing classes, yet there is only one root bootstrap error to fix.

### 8.2. Different Configurations Can Create Different Contexts

If one test class uses `@ActiveProfiles("integration")` and another uses `@ActiveProfiles("repository")`, they can produce two different cache keys. Each context can fail for its own reason. Do not lump every threshold message in a suite into a single error if metadata differs.

### 8.3. The Cache Does Not Heal Itself After Configuration Changes

Within the same test JVM, failure counts and the context cache belong to the process lifecycle. When editing configuration files or fixing beans while the test JVM is still running, do not expect the cache to automatically forget the earlier failure and recreate the context from updated sources. Terminate the test process and re-run to verify the fixed configuration.

## 9. When Should the Threshold Be Increased?

In most cases, keeping the default `1` stops the test suite from repeatedly loading a broken context. However, you can temporarily increase the threshold to diagnose a special situation.

Example:

```bash
./gradlew test -Dspring.test.context.failure.threshold=3
```

This allows Spring up to three failed context load attempts before skipping the next attempt. It can be helpful when investigating a timing-dependent error or an unstable test environment.

However, raising the threshold has limitations:

- It does not fix what prevents the context from initializing.
- It can lengthen test execution time if each initialization takes significant time.
- It can produce multiple nearly identical stack traces and make logs harder to read.
- It does not replace checking resource lifecycles or race conditions.

If each retry yields a different result, identify why configuration or resources change between bootstraps. For example, a container not ready yet, a port not yet allocated, a service failing health checks, or a property supplier returning unstable values. After finding the cause, return the threshold to the default once diagnostics are no longer needed.

## 10. Do Not Confuse the Threshold With Retry or Self-Healing Mechanisms

The failure threshold is not a retry policy for databases or HTTP requests. Nor is it a mechanism to restart a Spring context after an application is running.

| Mechanism | Purpose |
|---|---|
| Context failure threshold | Limits attempts to load a failed `ApplicationContext` for the same cache key |
| HTTP/database client retry | Retries an I/O operation according to the client's retry policy |
| Testcontainers wait strategy | Waits for a service inside a container to become ready before tests use it |
| Context cache | Reuses successfully initialized contexts across tests with compatible configurations |
| `@DirtiesContext` | Marks a context no longer suitable for reuse and requests cache eviction per configured scope |

If a PostgreSQL container is not ready yet, increasing the context failure threshold does not solve the problem. Configure a wait strategy, check readiness, or adjust lifecycles so the datasource is created only when the service can accept connections.

If a test mutates context state or a resource attached to a context has terminated, `@DirtiesContext` may be appropriate. However, that annotation is not a fix for all bootstrap errors. If a bean is misconfigured or a property is missing, creating a new context with the same configuration will still fail.

## 11. Checking Order-Dependent and Parallel Execution Errors

Sometimes a test class succeeds when run alone, yet the full suite fails. In this case, check factors beyond configuration itself:

- Did an earlier test alter system properties, system clock, default locale, or global configuration?
- Did a test stop a container or mock server that another test still needs?
- Do tests share a fixed port, temporary file, database schema, or data?
- Did a test invoke `@DirtiesContext` and alter how contexts are reused?
- Are tests running in parallel contending for shared resources?
- Do test workers share the same JVM, or does the build tool split them across multiple forks?

To investigate, run the failing test class individually, then run it with its test group in a reproducible order. If it only fails during parallel execution, temporarily reduce parallelism to see whether the error relates to resource contention. That is a diagnostic step; the long-term solution still requires removing unsafe dependencies between tests.

For interleaved logs due to parallel execution, rely on test class names, timestamps, test worker/process IDs, and context metadata. Do not grab the nearest `Failed to load ApplicationContext` line in log file order without confirming it belongs to the same context key.

## 12. Step-by-Step Troubleshooting Workflow

When encountering `ApplicationContext failure threshold exceeded`, you can follow this workflow:

1. **Confirm the Spring version.** Failure threshold exists since Spring Framework 6.1; check the dependency graph if the project uses an older version or mixed Spring versions.
2. **Locate the threshold message.** Record the test class and context metadata in the log.
3. **Locate the first `Failed to load ApplicationContext`** for the same cache key and the same test JVM.
4. **Read the full cause chain.** Identify the first failing bean or component, unresolved property, failed connection, or invalid configuration.
5. **Cross-reference test configuration.** Check `@SpringBootTest`, `@ContextConfiguration`, profiles, property sources, initializers, and dynamic properties.
6. **Check resource lifecycles.** Ensure containers, databases, WireMock, or servers are ready and stay running while the context uses them.
7. **Run the first test class alone.** Shorten logs and verify whether the bootstrap error reproduces independently.
8. **Fix the root cause.** Adjust configuration or lifecycle on the exact failing component.
9. **Re-run in a fresh test JVM.** Confirm the context initializes successfully and tests sharing the context run.
10. **Return the threshold to its default** if it was previously raised solely for diagnostics.

When filing an issue or bug report, attach the first failing test class, the original exception, and relevant context metadata. A long list of test classes skipped due to the threshold is usually far less useful than one clearly identified causal stack trace.

## 13. End-to-End Log Reading Example

Suppose the abbreviated log looks like:

```text
OrderRepositoryTests
Failed to load ApplicationContext
Caused by: BeanCreationException: Error creating bean 'dataSource'
Caused by: SQLException: Connection refused

OrderServiceTests
IllegalStateException: ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for ...

OrderControllerTests
IllegalStateException: ApplicationContext failure threshold (1) exceeded:
skipping repeated attempt to load context for ...
```

How to read it:

- `OrderRepositoryTests` is the first test class in the example that attempted to load the context and failed.
- `dataSource` could not be created because the database connection was refused.
- `OrderServiceTests` and `OrderControllerTests` hit the same cache key, so Spring skipped subsequent load attempts with the default threshold of 1.
- Investigate the database URL, host, mapped port, credentials, container startup, and readiness on the first failure.
- There is no need to modify the two later test classes individually if they merely share the broken context.

If `OrderServiceTests` has a different profile or property source, verify the cache key before concluding it was affected by `OrderRepositoryTests`'s failure.

## 14. Common Mistakes

**Only fixing the test class showing the threshold message.** That test may not be where the error originated. Find the first failed context load for the same cache key.

**Raising the threshold and considering the issue fixed.** A higher threshold only permits more retries. If configuration remains broken, every attempt can still fail.

**Clearing the context cache without finding the cause.** Recreating a context with the same broken properties and beans will keep failing. The cache is not the root cause if the context never initialized successfully.

**Using `@DirtiesContext` on every test.** The annotation can slow down the suite and does not solve missing placeholders, broken beans, or unready databases.

**Assuming all test failures share the same cache key.** Different profiles, property sources, context customizers, or configuration classes can produce separate cache keys.

**Reading the threshold exception as the root exception.** The `skipping repeated attempt` message only explains why Spring did not retry. Look for the stack trace of the first failed bootstrap.

**Ignoring differences across test JVMs.** Each fork/worker JVM has its own context cache and failure count. Logs from multiple processes may contain multiple independent first loads.

**Reading only the deepest exception line.** The lowest root cause is sometimes just a generic I/O error. Combine the exception chain with the first application bean or configuration appearing in the stack trace.

## 15. How to Document and Share the Root Cause

When reporting a context threshold error to the development team, provide reproducible information:

| Information | Example |
|---|---|
| Spring Framework/Boot version | Actual version from the dependency graph |
| First failing test class | `OrderRepositoryTests` |
| Related context key | Profile, config class, property source, or loader |
| Threshold | `spring.test.context.failure.threshold=1` |
| Causal exception | `Connection refused` when creating datasource |
| Dependent resource | PostgreSQL Testcontainers, mapped port, or external server |
| Reproduction steps | Command to run the test class alone and output |
| Fix | Adjust startup/readiness or property registration |

Avoid sending only the tail of the log containing the threshold message, as that portion usually lacks details about the first context creation attempt. A good report clearly points out the first failing test class and the original exception leading to that failure.

The context failure threshold is a mechanism limiting repeated attempts to load a failed `ApplicationContext`, per context cache key in the test JVM. The default value of `1` makes Spring try once before skipping repetitions. When seeing `failure threshold exceeded`, treat it as a signal of an earlier bootstrap failure: locate the first `Failed to load ApplicationContext` for the same context, read the cause chain, check profiles/properties/beans and backing service lifecycles, and re-run tests in a fresh JVM after fixing the cause. Increasing the threshold should only be a temporary diagnostic measure, not a substitute for fixing the root error.

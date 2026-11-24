# Isolating Environment Variables, System Properties, and Shared State Across Tests

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Configuration Testing

## 1. Why Can One Configuration Test Break Another?

Spring Boot reads configuration from many sources: `application.yml`, `application.properties`, profile-specific files, imported files, OS environment variables, Java system properties, JSON application properties, command-line arguments, and property sources added by testing frameworks.

In a test, developers often want to change `client.timeout` or `feature.enabled` to verify two business branches. However, some operations mutate **JVM-process-wide state**, not just one test case's data. Without proper restoration—or when running in parallel—later tests can observe values left behind by earlier ones.

Dangerous example:

~~~java
@Test
void usesFastMode() {
    System.setProperty("demo.client.mode", "fast");
    // Verify fast branch...
}

@Test
void usesDefaultMode() {
    // May accidentally read demo.client.mode=fast
    // from the previous test instead of the default value.
}
~~~

When run individually, both may pass. When run as a suite, `usesDefaultMode` fails because it receives `fast`. Under parallel execution, the value can flip right as another test initializes beans.

This is **test interference** or **shared-state leakage**: one test case alters inputs or state used by another. With configuration, such bugs are especially subtle because `Environment` combines prioritized sources and an already-bound bean does not automatically update after a property source changes.

### Learning Objectives

After this lesson, you will:

1. Distinguish the scopes of OS environment, Java system properties, Spring `Environment`, and test property sources.
2. Understand why `System.setProperty` is a JVM-wide mutation and how to restore original state properly.
3. Know how to use `ApplicationContextRunner`, `@SpringBootTest(properties)`, `@TestPropertySource`, and `@ActiveProfiles` to avoid mutating global state.
4. Understand `@DynamicPropertySource`, resource lifecycles, and risks of the Spring TestContext cache.
5. Apply `@ResourceLock` or separate child processes when mutating global state is unavoidable.
6. Isolate static fields, mutable singleton beans, mock servers, databases, Testcontainers, clocks, and files.
7. Test precedence intentionally without depending on environment variables on a laptop or CI runner.
8. Diagnose tests that fail only in full suites or under parallel execution.
9. Keep real secrets out of test resources and logs.

## 2. Map of Shared State Types

| Data or tool | Typical scope | Risk to other tests | Strategy |
| --- | --- | --- | --- |
| `System.getenv` | Process environment | Tests in the same JVM see the same env | Inject via Spring/test sources or spawn a child process |
| `System.getProperties` | JVM-wide mutable map | Other tests read mutated values | Avoid mutating; if forced, save/restore and serialize |
| `@SpringBootTest(properties)` | Test ApplicationContext | Context may be reused via cache key | Declare explicit values per test context |
| `@TestPropertySource` | Test context | Cache may reuse beans inside the context | Declare isolated sources and clean up state |
| `ApplicationContextRunner` | Context created per `run` | Low risk unless app code touches globals | Use for binding and auto-configuration tests |
| `MockEnvironment` | Java object in test | Only if the object is shared | Create a fresh instance per test |
| `@DynamicPropertySource` | Test context + supplier | Context caching and resource lifecycles | Manage dynamic resource lifecycles properly |
| Static field | JVM/classloader | State leakage or data races | Avoid mutable statics or reset/lock |
| Singleton Spring bean | ApplicationContext | Shared across tests on context cache hit | Reset state or recreate context when needed |
| Database/container | External resource outside JVM | Shared rows and connections | Transactions, cleanup, or separate schemas |
| Mock HTTP server | Port and server process | Port collisions and leftover state | Dynamic ports and proper lifecycle shutdown |
| Test files | Filesystem | Colliding on the same path | `@TempDir` and unique filenames |
| Timezone/Locale/default clock | Global or instance | Results vary across host machines | Inject `Clock`; avoid changing global defaults |

The guiding principle is choosing the smallest scope that supplies test inputs. To test two values for one key, create **two contexts with separate sources** rather than mutating a shared JVM property between potentially concurrent tests.

## 3. OS Environment, JVM System Properties, and Spring Environment

### 3.1. OS Environment Variables

Example launch:

~~~bash
export DEMO_CLIENT_TIMEOUT=5s
java -jar app.jar
~~~

In Java:

~~~java
String timeout = System.getenv("DEMO_CLIENT_TIMEOUT");
~~~

The environment is supplied when the process spawns. Java has **no standard, safe, portable API** to mutate the current JVM's OS environment like a normal `HashMap`.

Some libraries use reflection or implementation-specific hacks to alter `System.getenv`, which can be blocked by Java module encapsulation, break across JDK versions, and race in parallel tests. Never rely on it as a default testing practice.

### 3.2. JVM System Properties

Can be supplied via a JVM flag:

~~~bash
java -Ddemo.client.timeout=5s -jar app.jar
~~~

Or mutated at runtime:

~~~java
System.setProperty("demo.client.timeout", "5s");
String value = System.getProperty("demo.client.timeout");
~~~

`System.properties` is shared JVM state. Every test and thread in the same process sees the same keys and values. Calling `System.setProperty` in a test affects far more than that single test's `ApplicationContext`.

### 3.3. Spring Environment

Spring `Environment` holds multiple `PropertySource`s and applies precedence:

~~~java
import org.springframework.core.env.Environment;

public class ClientConfigService {
    private final Environment env;

    public ClientConfigService(Environment env) {
        this.env = env;
    }

    public String timeout() {
        return env.getProperty("demo.client.timeout");
    }
}
~~~

A Spring test can attach a context-scoped property source making `env.getProperty` return `2s` while `System.getProperty("demo.client.timeout")` stays `5s`. That is not a bug: the two APIs have different sources and scopes.

### 3.4. Direct System.getenv Bypasses Test Sources

Suppose:

~~~java
String mode = System.getenv("DEMO_MODE");
~~~

Test:

~~~java
@SpringBootTest(properties = "demo.mode=test")
class ModeTest {}
~~~

The annotation tells Spring `demo.mode=test`. It **does not modify `System.getenv("DEMO_MODE")`**. If production code still calls `System.getenv` directly, it reads whatever happens to be on the CI runner or developer laptop regardless of test overrides.

For testability, bind settings into a `@ConfigurationProperties` bean or inject `Environment` into services. Tests can then control inputs without touching the OS process environment.

## 4. Using @ConfigurationProperties to Decouple Logic from Configuration Sources

Record example for Spring Boot 3 and Java 17+:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.client")
public record DemoClientProperties(
        @DefaultValue("3s") Duration timeout,
        @DefaultValue("false") boolean enabled,
        @DefaultValue("2") int retries
) {}
~~~

Business service consuming the typed object:

~~~java
package com.example.demo.service;

import com.example.demo.config.DemoClientProperties;

public class ClientPolicyService {

    private final DemoClientProperties config;

    public ClientPolicyService(DemoClientProperties config) {
        this.config = config;
    }

    public boolean shouldRetry(int currentAttempt) {
        return config.enabled()
                && currentAttempt < config.retries();
    }
}
~~~

Plain unit test needing no Spring environment:

~~~java
@Test
void policyDoesNotRetryWhenDisabled() {
    DemoClientProperties config =
            new DemoClientProperties(
                    Duration.ofSeconds(3), false, 2
            );

    ClientPolicyService service =
            new ClientPolicyService(config);

    assertThat(service.shouldRetry(1)).isFalse();
}
~~~

The test needs neither JVM properties nor OS environment variables. For business logic, this is usually the cleanest isolation level.

### 4.1. Separating Binding Tests from Business-Logic Tests

There are two distinct questions:

- Does Binder convert `demo.client.timeout=3s` into `Duration.ofSeconds(3)` properly?
- Does the service honor `enabled=false` when deciding whether to retry?

The first needs a binding test. The second can pass the typed object directly. Merging both into one heavy `@SpringBootTest` slows tests down, increases shared state, and makes failures harder to diagnose.

## 5. System.setProperty: Saving and Restoring Properly

When forced to test legacy code reading `System.getProperty` directly, restore the **exact original state**.

~~~java
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class TemporaryPropertyTest {

    @Test
    void readsTemporaryValue() {
        String key = "demo.client.timeout";
        String previous = System.getProperty(key);

        try {
            System.setProperty(key, "2s");
            assertThat(System.getProperty(key)).isEqualTo("2s");
        } finally {
            if (previous == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, previous);
            }
        }
    }
}
~~~

If the key was absent initially, call `clearProperty`. If it held `5s`, restore `5s`. Blindly calling `System.clearProperty` in `@AfterEach` can wipe out a legitimate setting supplied by another test or the JVM launcher.

### 5.1. Cleanup Still Does Not Solve Parallel Races

Example:

~~~text
Test A: save previous value
Test A: set demo.client.timeout = 2s
          Test B: read demo.client.timeout -> 2s
Test A: restore previous value
~~~

Test B read the wrong value while A was running. `finally` restores **after the scope finishes**, without isolating properties per thread.

Avoid global mutations altogether whenever possible. When unavoidable, run affected tests sequentially or use a resource lock obeyed by **every** test touching that resource.

### 5.2. AutoCloseable Helper to Reduce Teardown Bugs

~~~java
final class SystemPropertyScope implements AutoCloseable {

    private final String key;
    private final String previous;

    private SystemPropertyScope(String key, String nextValue) {
        this.key = key;
        this.previous = System.getProperty(key);
        System.setProperty(key, nextValue);
    }

    static SystemPropertyScope set(String key, String value) {
        return new SystemPropertyScope(key, value);
    }

    @Override
    public void close() {
        if (previous == null) {
            System.clearProperty(key);
        } else {
            System.setProperty(key, previous);
        }
    }
}
~~~

Using try-with-resources:

~~~java
@Test
void usesScopedSystemProperty() {
    try (SystemPropertyScope ignored =
                 SystemPropertyScope.set("legacy.mode", "test")) {
        assertThat(System.getProperty("legacy.mode"))
                .isEqualTo("test");
    }
}
~~~

This utility prevents forgotten cleanup, yet still does not prevent races across threads. Never use it in parallel suites without serializing access to global properties.

## 6. JUnit ResourceLock When Global State Exists

JUnit Jupiter provides `@ResourceLock` so tests declaring the same shared resource do not execute concurrently when parallel execution is enabled:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE
)
class LegacySystemPropertiesTest {

    @Test
    void testLegacyReader() {
        String previous = System.getProperty("legacy.mode");
        try {
            System.setProperty("legacy.mode", "test");
            // Test legacy logic...
        } finally {
            if (previous == null) {
                System.clearProperty("legacy.mode");
            } else {
                System.setProperty("legacy.mode", previous);
            }
        }
    }
}
~~~

### 6.1. ResourceLock Is Not Magic

- It coordinates only tests declaring matching resource locks inside JUnit's engine.
- Any test omitting the lock can still read or mutate the key at the wrong moment.
- Background threads or third-party libraries do not obey JUnit locks automatically.
- Locks do not restore values; `finally` is still mandatory.
- Overly broad locks slow down the suite by forcing sequential execution.

`@Isolated` can also isolate test classes from running alongside any other test class in JUnit, though proper teardown is still required.

### 6.2. Do Not Use ThreadLocal to Fake System Properties

`System.getProperty` does not read from a `ThreadLocal`. If code under test calls the JVM-wide API, setting a ThreadLocal in a test does nothing to alter that API's behavior.

A more durable fix is refactoring services to accept a `ConfigurationProvider` or injected typed properties, reserving process-wide tests only for code that explicitly tests JVM property handling.

## 7. ApplicationContextRunner: Isolating Binding Tests in Small Contexts

Spring Boot provides `ApplicationContextRunner` to build a fresh context per case, ideal for testing `@ConfigurationProperties`, auto-configurations, and conditional beans.

Example:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.client")
public record ClientProperties(
        Duration timeout,
        int retries
) {}
~~~

Test:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.junit.jupiter.api.Test;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClientPropertiesBindingTest {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestConfig {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsFastConfiguration() {
        runner.withPropertyValues(
                "demo.client.timeout=1s",
                "demo.client.retries=2"
        ).run(context -> {
            ClientProperties properties =
                    context.getBean(ClientProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(1));
            assertThat(properties.retries()).isEqualTo(2);
        });
    }

    @Test
    void bindsSlowConfiguration() {
        runner.withPropertyValues(
                "demo.client.timeout=10s",
                "demo.client.retries=5"
        ).run(context -> {
            ClientProperties properties =
                    context.getBean(ClientProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(10));
            assertThat(properties.retries()).isEqualTo(5);
        });
    }
}
~~~

Both tests use independent `ApplicationContext` instances created per `run`, needing no `System.setProperty`.

### 7.1. Note on Base Runners

`withPropertyValues` returns a new configured runner instance. Treat it as an immutable variant per scenario rather than a global mutable registry.

If the base runner already defines `demo.client.timeout=3s`, a test verifying "missing timeout" must use a runner that **never set timeout in the first place**. Do not mistake "test did not override timeout" for "timeout absent."

### 7.2. The Runner Does Not Erase Static State in Code Under Test

If a bean inside the context calls `System.setProperty` or writes to a static cache, those side effects survive after the context closes. The runner isolates **Spring configuration scope**, not the entire JVM sandbox.

## 8. @SpringBootTest(properties): Explicit Inputs for Integration Tests

For tests that must start a full application context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "demo.client.timeout=2s",
    "demo.client.retries=4"
})
class ClientIntegrationTest {

    @Autowired
    ClientProperties properties;

    @Test
    void usesTestValues() {
        assertThat(properties.retries()).isEqualTo(4);
    }
}
~~~

`@SpringBootTest(properties)` places values into the test context's property source, typically outranking normal Config Data. The test declares explicit inputs independent of whatever a developer exported before running.

### 8.1. A Test Property Does Not Change System.getenv

Even when a test sets `demo.client.timeout=2s`, calling `System.getenv("DEMO_CLIENT_TIMEOUT")` still queries the OS process environment. If a class calls that API directly, introduce an abstraction or test in a child process.

### 8.2. Do Not Boot the Whole App for Every Test Case

A `@SpringBootTest` can initialize database pools, message listeners, schedulers, and auto-configurations outside what is being tested, slowing runs and adding shared state. When testing only Binder behavior, `ApplicationContextRunner` or `MockEnvironment` fits better.

### 8.3. Test Classes with Different Inputs Are Distinguished Properly

Spring TestContext uses multiple inputs—including test property sources—to compute context cache keys. Test classes with different settings receive separate cache keys. Still, do not assume every test method gets a brand-new context or every test class gets a unique one; caching exists to reuse compatible contexts.

## 9. @TestPropertySource and @ActiveProfiles

### 9.1. Inline Test Properties

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
    "demo.client.timeout=4s",
    "demo.client.retries=3"
})
class ClientTestSourceIT {}
~~~

Spring TestContext's `@TestPropertySource` adds a test property source to the context, avoiding global System property mutations.

### 9.2. Loading a Test .properties File

~~~java
@TestPropertySource(
        locations = "classpath:/test-config/client.properties"
)
~~~

File `src/test/resources/test-config/client.properties`:

~~~properties
demo.client.timeout=4s
demo.client.retries=3
~~~

Test files organize shared module settings cleanly, as long as no test mutates a shared file at runtime.

### 9.3. Do Not Use TestPropertySource to Load Multi-Document YAML as Boot Does

A common mistake:

~~~java
@TestPropertySource(
        locations = "classpath:/application-test.yml"
)
~~~

`@TestPropertySource` does not replicate Spring Boot's Config Data pipeline for YAML and profile-activated documents. When testing `application-test.yml`, `spring.config.activate.on-profile`, or `spring.config.import`, use a Spring Boot test context that loads Config Data through Boot's rules.

### 9.4. Selecting a Test Profile

~~~java
import org.springframework.test.context.ActiveProfiles;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@ActiveProfiles("test")
class CatalogWithTestProfileIT {}
~~~

When profile `test` is active, Boot loads `application-test.yml` from matching config locations.

`@ActiveProfiles` does not clear other properties. Keys omitted in the test file can still resolve from `application.yml`, imported configs, OS environment, or other sources per precedence.

### 9.5. Avoid Stacking Too Many Override Layers

A test combining `@SpringBootTest(properties)`, `@TestPropertySource`, `@DynamicPropertySource`, and multiple profiles becomes hard to read. Only overlap sources on the same key when explicitly testing precedence; otherwise, choose one clear, simple source.

## 10. MockEnvironment and Binder: Testing Precedence at the Object Level

To test multi-source rules without depending on CI env, use `MockEnvironment` and `MapPropertySource`.

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PrecedenceTest {

    @Test
    void higherPriorityPropertyWins() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "defaults",
                        Map.of(
                                "lesson.labels.owner", "core",
                                "lesson.labels.region", "global"
                        )
                )
        );

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "overrides",
                        Map.of(
                                "lesson.labels.region", "apac",
                                "lesson.labels.stage", "test"
                        )
                )
        );

        Map<String, String> labels = Binder.get(environment)
                .bind(
                        "lesson.labels",
                        Bindable.mapOf(String.class, String.class)
                )
                .orElse(Map.of());

        assertThat(labels)
                .containsEntry("owner", "core")
                .containsEntry("region", "apac")
                .containsEntry("stage", "test");
    }
}
~~~

Here:

- `MockEnvironment` is freshly created inside the test.
- `defaults` and `overrides` are explicitly controlled sources.
- `addFirst` places `overrides` at highest priority.
- Binder merges map entries and picks `region=apac`.
- Neither `System.getProperties` nor OS environment is touched.

### 10.1. This Is Not a Full Config Data Integration Test

The test above verifies property resolution and Binder against simulated sources. It does not load `application-prod.yml`, profile-activated documents, or config imports. To test **how Spring Boot selects and loads real files**, use the Config Data pipeline.

## 11. TestPropertyValues: Another Tool for Test Scope

Spring Boot's `TestPropertyValues` adds test property sources cleanly.

~~~java
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.mock.env.MockEnvironment;

MockEnvironment environment = new MockEnvironment();

TestPropertyValues.of(
        "demo.client.timeout=3s",
        "demo.client.retries=2"
).applyTo(environment);
~~~

Useful whenever you need a deterministic `Environment` in tests without JVM-wide side effects like `System.setProperty`.

### 11.1. Apply Before Binding

If a bean was already bound from an earlier source, adding properties to `Environment` afterward does not rebind it. Tests checking startup configuration must add sources **before beans/context initialize**.

### 11.2. Never Share a Mutable Environment Across Tests

If a `MockEnvironment` sits in a static field and multiple tests add/remove `PropertySource`s, you recreate shared state. Instantiate a fresh one per test unless reuse has an explicit lifecycle contract.

## 12. DynamicPropertySource: Dynamic Sources for Testcontainers and Server Ports

Some values are known only after creating resources, such as random ports on mock HTTP servers or Testcontainers JDBC URLs.

Spring Test provides `@DynamicPropertySource`:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class DatabaseTestBase {

    static final String TEST_URL =
            "jdbc:postgresql://localhost:55432/demo";

    @DynamicPropertySource
    static void registerDatabaseUrl(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> TEST_URL);
    }
}
~~~

This merely demonstrates supplier syntax; a fixed URL does not guarantee a real database exists. In integration tests, fetch the URL from the container/server started by the fixture.

### 12.1. Dynamic Sources Have High Precedence

Properties registered with `@DynamicPropertySource` generally outrank `@TestPropertySource`, OS environment, JVM system properties, and standard sources. When two annotations set `spring.datasource.url`, the dynamic value wins.

When debugging, inspect the **effective winning source**, not just one line in `application-test.yml`.

### 12.2. Suppliers Can Be Dynamic While Created Clients Are Not

A supplier may return a new value on a later lookup, yet an already-created DataSource or HTTP client retains its initial settings. Do not confuse **dynamic property lookup** with **automatic client reconfiguration**.

### 12.3. Inherited Dynamic Methods and Context Caching

If subclasses inherit the same `@DynamicPropertySource` method while supplying different dynamic values, the Spring TestContext cache may reuse a stale context unexpectedly. In such cases, use `@DirtiesContext` or design context/resource lifecycles explicitly.

## 13. Testcontainers: Sharing Containers While Isolating Data

Spring Boot test with PostgreSQL Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                POSTGRES::getJdbcUrl
        );
        registry.add(
                "spring.datasource.username",
                POSTGRES::getUsername
        );
        registry.add(
                "spring.datasource.password",
                POSTGRES::getPassword
        );
    }

    @Test
    void loadsContext() {
        // Test uses the DB provisioned by the container.
    }
}
~~~

Requires matching dependencies, a Docker runtime, and JDBC drivers. This shows how container lifecycles pair with Spring test properties.

### 13.1. A Static Container Does Not Mean a Clean Database

A container can be shared across a test class; rows inserted by test A remain when test B runs. Use transaction rollbacks, cleanup scripts, or separate schemas/databases as needed.

### 13.2. Context Caching and Container Lifetimes Can Mismatch

If a container stops when class A finishes while A's Spring context stays in the TestContext cache, class B may reuse a DataSource pointing at a closed port. That produces connection-refused errors—not a bug in `@DynamicPropertySource`.

Pick one consistent policy:

- Keep the container alive at least as long as every referencing context.
- Prevent context reuse after the container stops.
- Reset external data between tests.
- Never hardcode ports/URLs when dynamic ports are available.

### 13.3. ServiceConnection Does Not Eliminate Shared State Either

In supported versions, Spring Boot's `@ServiceConnection` feeds connection details directly into auto-configuration. While cleaner than manual URL registration, container lifecycles and shared database state still require careful management.

## 14. Spring TestContext Caching and Mutable Singletons

`@SpringBootTest` participates in Spring TestContext's `ApplicationContext` cache. One context can be reused across test methods or classes with matching configurations and cache keys.

### 14.1. Why Is Caching Useful?

Starting a Spring Boot context is expensive: class scanning, auto-configuration, bean instantiation, client initialization, schema setup. Context reuse speeds up the suite.

### 14.2. Why Can Caching Leak State?

Suppose a singleton bean:

~~~java
@Component
public class FeatureRegistry {

    private final Map<String, Boolean> flags =
            new ConcurrentHashMap<>();

    public void enable(String name) {
        flags.put(name, true);
    }

    public boolean enabled(String name) {
        return flags.getOrDefault(name, false);
    }

    public void clear() {
        flags.clear();
    }
}
~~~

Test A calls `enable("beta")`. Test B, reusing the same context, observes `beta=true`. Both having `@ActiveProfiles("test")` does not reset singleton fields.

### 14.3. Mitigation

- Reset state via fixtures when safe.
- Design services to avoid mutable singleton test state.
- Use per-test instances or fixtures.
- When the context itself is mutated beyond reliable cleanup, use `@DirtiesContext`.

Example:

~~~java
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS
)
class MutatesApplicationContextIT {}
~~~

`@DirtiesContext` evicts the context from cache per the annotation policy. It **does not** automatically clear `System.properties`, static caches, database rows, or temp files; clean those up separately.

### 14.4. Do Not Overuse @DirtiesContext

Dirtied contexts must be rebuilt, slowing down the suite. For small resettable state, explicit cleanup is cheaper. Never slap `@DirtiesContext` onto every order-dependent failure without finding the true leak.

## 15. When Testing Real System.getenv Is Required: Child Processes

When tests must verify how the app handles **real OS environment variables at process startup**, a child JVM gives far cleaner isolation than reflection hacks.

`ProcessBuilder` example:

~~~java
import java.util.concurrent.TimeUnit;

public class ChildEnvironmentTestHelper {

    public static void runChild() throws Exception {
        ProcessBuilder builder =
                new ProcessBuilder("java", "-version");

        builder.environment().put(
                "DEMO_CLIENT_TIMEOUT",
                "2s"
        );
        builder.redirectErrorStream(true);

        Process process = builder.start();
        boolean exited = process.waitFor(
                30, TimeUnit.SECONDS
        );

        if (!exited) {
            process.destroyForcibly();
            throw new IllegalStateException(
                    "Child process exceeded timeout"
            );
        }
    }
}
~~~

`java -version` illustrates passing environment variables to a child process; it does not test Spring Boot Binder. For real integration, run a small Java fixture or Spring Boot app in the child process that reads and reports a **non-sensitive demo value**, then assert its exit code and output.

### 15.1. Benefits

- The child receives the environment before its JVM boots.
- `System.getenv` inside the child reads the test variable natively.
- Static state and System properties in the child never touch the parent JVM.
- Concurrent tests can spawn child processes with different environments safely.

### 15.2. Costs

- Process startup takes time.
- Must drain output streams and prevent hangs.
- Requires timeouts, cleanup, and avoiding port collisions.
- Never pass real secrets in command-line args or logs.
- Use separate temp directories and ports per process under parallel runs.

Reserve process-level tests for genuinely verifying OS environment or bootstrap lifecycles. For Spring property-binding unit tests, runners or `MockEnvironment` suffice.

## 16. Static Fields and Other Non-Environment State

State leakage does not come solely from configuration.

### 16.1. Static Caches

~~~java
public final class GlobalCache {
    public static final Map<String, String> VALUES =
            new ConcurrentHashMap<>();
}
~~~

If test A puts `VALUES.put("mode","fast")`, test B can read it. Clearing in `@AfterEach` helps in sequential runs, yet in parallel runs A's cleanup can wipe data B is currently using.

The real fix is **never sharing mutable global fixtures** or partitioning state by test-unique keys/sessions with verified isolation.

### 16.2. Clocks and Timezones

Code calling `Instant.now()` depends on the system clock; tests can fail around midnight or date rollovers. Instead of mutating the JVM timezone:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC
);
~~~

Inject `Clock`:

~~~java
public class ExpiryService {

    private final Clock clock;

    public ExpiryService(Clock clock) {
        this.clock = clock;
    }

    public boolean expired(Instant expiresAt) {
        return !Instant.now(clock).isBefore(expiresAt);
    }
}
~~~

Tests get deterministic timestamps without changing `TimeZone.setDefault` process-wide.

### 16.3. Locale and JVM-Wide Defaults

`Locale.setDefault`, `TimeZone.setDefault`, and certain security/SSL settings are global state. Whenever tests must change them, restore them and serialize access. Never rely on global defaults when logic can accept Locale/ZoneId/Clock as injected dependencies.

### 16.4. Async Threads and Schedulers

A test may trigger an async task and finish before the task completes. The lingering task mutates caches or sends messages, hitting later tests with side effects. Await, cancel, and clean up tasks cleanly; closing the Spring context is not always enough if code spawns unmanaged threads.

## 17. Filesystem: Use TempDir and Avoid Shared Paths

Never have multiple tests write to the real `./config/application.yml` or a fixed `/tmp/test-config.yml`.

JUnit `@TempDir`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigFileTest {

    @TempDir
    Path tempDir;

    @Test
    void createsIndependentFile() throws Exception {
        Path properties = tempDir.resolve(
                "client-test.properties"
        );

        Files.writeString(
                properties,
                "demo.client.timeout=2s\n"
        );

        assertThat(Files.readString(properties))
                .contains("demo.client.timeout=2s");
    }
}
~~~

### 17.1. Config Data Locations Must Be Supplied at the Right Time

If a test wants Spring Boot to load an external file via `spring.config.location`, that property is evaluated early in config processing. Supply the location before Spring Boot resolves Config Data files, not via ad-hoc System property mutations after the context starts.

To test real bootstrap, launch an isolated Spring Boot process with explicit working directory and temp config paths.

### 17.2. File Existence Is Not Proof of Binding

Asserting that a file contains `timeout=10s` does not prove Spring Boot uses that value. Verify file loading, active profiles, precedence, and that the bean/client received the final value.

## 18. Databases, Queues, and Mock Servers: Out-of-JVM State Leakage

### 18.1. Databases

Two tests sharing a schema:

~~~java
@Test
void createsRecord() {
    repository.save(new Customer("alice"));
}

@Test
void expectsEmptyDatabase() {
    assertThat(repository.count()).isZero();
}
~~~

If rows from the first test persist, the second fails. Use transaction rollbacks, SQL cleanup, separate schemas, or separate databases/containers depending on test scope.

Note: `@Transactional` on a test does not roll back work performed on async threads, remote systems, or separate transactions. Verify real transaction boundaries.

### 18.2. Message Brokers

A shared topic/queue can deliver test A's message to test B. Use unique consumer groups, correlation IDs, explicit cleanup, or isolated test resources.

### 18.3. HTTP Mock Servers

A mock server on a fixed port collides when suites run in parallel or two CI jobs share a host. Use dynamic ports and inject the URL via `@DynamicPropertySource` or timely test property sources.

### 18.4. External State Is Not Reset by @DirtiesContext

Closing a context does not truncate PostgreSQL tables, purge Kafka topics, or reset mock server state. Every external resource needs its own lifecycle and cleanup.

## 19. Choosing the Right Test Layer for Maximum Isolation

| Layer | Purpose | Tool | Strengths |
| --- | --- | --- | --- |
| Unit | Test service with fixed config | Construct typed object and inject directly | Fast, zero JVM-global dependencies |
| Binder | Type conversion, Maps/Lists, relaxed binding | `MockEnvironment` + `Binder` | Explicit property source control |
| Small context | Auto-configuration, conditional beans | `ApplicationContextRunner` | Lightweight contexts isolating cases |
| Integration context | Profiles, bean graph, startup | `@SpringBootTest`, test sources | Verifies Spring Boot wiring |
| External integration | DB, queues, HTTP providers | Testcontainers, mocks | Controlled real connectivity |
| Process/bootstrap | Real OS env and JVM flags | ProcessBuilder or test launcher | Strong JVM/state isolation |

Do not boot an entire application context just to test `shouldRetry`. Conversely, when testing profile activation of `application-prod.yml`, `MockEnvironment` alone cannot prove Boot loaded Config Data properly.

## 20. Testing Conditions and Validation When Properties Are Missing

Example:

~~~java
import java.net.URI;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "partner.client")
@Validated
public record PartnerClientProperties(
        @NotNull URI endpoint
) {}
~~~

If a test verifies that omitting `partner.client.endpoint` fails startup, build a context **where no test source or active base file supplies that property**. A class annotated `@SpringBootTest(properties = "partner.client.endpoint=...")` masks the missing case.

With `ApplicationContextRunner`, build a runner omitting endpoint, register `PartnerClientProperties` with Bean Validation infrastructure, and assert context failure.

This is why test inputs must be explicit and self-contained—never relying on what an earlier test happened to clear or set.

### 20.1. Cases Commonly Requiring Tests

- Required property completely absent.
- Property set to an empty string.
- Wrong type, such as `timeout=not-a-duration`.
- Constraint violation such as negative retries.
- Missing nested group with `@NotNull`/`@Valid`.
- Profile-specific overrides.
- Dynamic property sources from containers.
- Same key across two sources with known precedence.

Design each case with sufficient controlled inputs to be conclusive. No validation test needs global JVM property mutations.

## 21. When Tests Fail Only on CI or Depend on Execution Order

Common symptoms:

| Symptom | Suspected cause | Investigation |
| --- | --- | --- |
| Passes alone, fails in suite | Global mutation or context cache | Search for `System.setProperty`, static fields, singleton state |
| Fails when run order reverses | Earlier test left state behind | Restore, reset fixtures and external state |
| Fails only in parallel | Race on globals, DB, ports, or files | Lock/serialize, isolate resources |
| Fails only on CI | Different env vars, locale, timezone, cwd | Control test inputs explicitly |
| DynamicPropertySource returns old URL | Stopped resource, context cache reuse | Align lifecycles; dirty context if needed |
| `@ActiveProfiles("test")` yet wrong value | Higher-priority source overrides it | Inspect effective property sources |
| Fresh context passes, cached context fails | Mutable singleton state | Reset beans or use separate context |
| `@DirtiesContext` did not fix it | Global/static/DB state uncleaned | Clean up at the right scope |
| Test config file got overwritten | Shared filename with multiple writers | Use `@TempDir`, never edit source files |
| Fails only with forked JVMs | Shared ports/DB/filesystem paths | Unique namespaces, dynamic ports |
| Real secret appears in logs | Env/system-property dump or record toString | Log non-sensitive keys only |
| Fails after an async test fails | Background task still running | Await/cancel and manage schedulers |

### Investigation Procedure

1. Reproduce by running the failing test alone.
2. Run alongside suspected neighboring tests.
3. Check execution order and parallel execution settings.
4. Search codebase for `System.setProperty`, `clearProperty`, and `setProperties`.
5. Audit static mutable state, singleton beans, and context cache reuse.
6. Check `@DynamicPropertySource` suppliers and container/server lifecycles.
7. Check test fixtures, files, databases, and message queues.
8. Identify undeclared OS/CI environment dependencies.
9. Replace mutations with context-local sources or constructor injection.
10. Re-run with shuffled order and parallelism enabled to confirm isolation.

Never dump `System.getenv()` or `System.getProperties()` into CI logs while debugging: many runners contain credentials and sensitive tokens.

## 22. Anti-Patterns and Replacements

### Anti-Pattern A — setProperty in BeforeAll Without Teardown

~~~java
@BeforeAll
static void setUp() {
    System.setProperty("demo.mode", "test");
}
~~~

The entire JVM stays mutated until something else overwrites it. Replace with `@SpringBootTest(properties="demo.mode=test")` when using a Spring context, or save/restore with a lock if forced.

### Anti-Pattern B — Always Calling clearProperty in AfterEach

~~~java
@AfterEach
void cleanup() {
    System.clearProperty("demo.mode");
}
~~~

If the property existed intentionally before the test, clearing it wipes out the prior value. Save and restore accurately.

### Anti-Pattern C — Assuming Mutable JavaBeans Auto-Update

A setter-based `@ConfigurationProperties` bean does not rebind simply because a test edits a file or Spring Environment afterward. Build a fresh context or design explicit refresh mechanics.

### Anti-Pattern D — Mutating OS Env via Reflection

Non-portable and race-prone. Use test sources or a child JVM when real OS env vars are needed.

### Anti-Pattern E — static final Reading getenv Too Early

~~~java
static final String MODE = System.getenv("DEMO_MODE");
~~~

The value is captured at class-loading time. Spring test property sources cannot change it afterward. Refactor to configuration injection.

### Anti-Pattern F — Shared Testcontainers Without Data Reset

A database container retains records from earlier tests. Clean up rows or isolate schemas/test IDs; Spring context metadata does not wipe databases.

### Anti-Pattern G — @DirtiesContext Everywhere

Dirtied contexts waste rebuild time and ignore JVM globals. Use it only when a context is truly dirtied.

### Anti-Pattern H — Fixed Ports on Multiple Test Servers

Dynamic ports and dynamic property registration are far safer, especially under parallel CI runs.

## 23. Checklist Before Enabling Parallel Execution

- [ ] No `System.setProperty` calls without restoration.
- [ ] Tests touching global properties share a ResourceLock/serialization policy.
- [ ] No reflection hacks mutating `System.getenv`.
- [ ] Test inputs declared via context-scoped property sources where appropriate.
- [ ] `@ActiveProfiles` and test-specific files are controlled.
- [ ] ApplicationContext cache never reuses unexpectedly mutated singletons.
- [ ] `@DynamicPropertySource` and container lifecycles align.
- [ ] Databases and message queues have cleanup or partitioning policies.
- [ ] Mock servers bind dynamic ports.
- [ ] Test files live in `@TempDir`, never modifying source files.
- [ ] Timezone, Locale, and Clock do not depend on the host machine.
- [ ] No background tasks keep running after tests end and cause side effects.
- [ ] Fixture cleanup still executes when assertions fail.
- [ ] Credentials never print via env dumps, logs, or exceptions.
- [ ] Process-level env tests spawn isolated child JVMs when truly needed.
- [ ] Every test can run standalone without requiring another test beforehand.
- [ ] Invalid configurations fail cleanly at startup.

## 24. Practice Exercises

### Exercise A — Leaked System Property

Write test A setting `lesson.mode=fast` via `System.setProperty` and test B expecting the default value. Run each alone and together. Then add `try/finally` restoration. Explain why cleanup alone fails under parallel execution.

### Exercise B — Isolated Config with ApplicationContextRunner

Create `LessonProperties(Duration timeout,int retries)`. Use two `withPropertyValues` calls with `timeout=1s` and `timeout=10s`. Assert both contexts bind cleanly without touching global properties.

### Exercise C — TestPropertySource and ActiveProfiles

Create `application.yml`, `application-test.yml`, and `test-overrides.properties`. Combine `@ActiveProfiles("test")` and `@TestPropertySource` to predict final values and verify precedence across sources.

### Exercise D — Binder with Two Sources

Use `MockEnvironment` and two `MapPropertySource`s: low-priority `lesson.labels.owner=core`, `region=global`; high-priority `region=apac`, `stage=test`. Bind `Map<String,String>` and assert all three keys.

### Exercise E — DynamicPropertySource

Start an HTTP mock server on a random port. Register `lesson.api.base-url` via a dynamic property supplier. Test URL binding, then stop the server and analyze why context cache reuse can send another test to the dead port.

### Exercise F — Child JVM

Use `ProcessBuilder.environment().put("LESSON_MODE","test")` to launch a child Java fixture reading `System.getenv`. Verify the parent JVM environment stays unchanged.

### Exercise G — Static State

Create a static Map with two tests doing puts/gets. Run them in parallel. Choose between per-test state partitioning, fixture reset, locking, or refactoring away the global static.

### Exercise H — Cached Spring Singleton

Create a bean counting invocations. Write two integration tests sharing the cached context. Predict state risks, resolve with cleanup or separate contexts, and analyze the performance trade-off.

### Exercise I — Testcontainers Database

Run PostgreSQL container tests where test A inserts a row and test B expects an empty table. Use rollback or cleanup to eliminate order dependence, then enable parallel runs with proper data partitioning.

### Exercise J — Testing Missing Configuration

Create `@ConfigurationProperties` with a required endpoint. Write a context runner omitting endpoint expecting validation failure, and another supplying it. Never rely on a property left by an earlier test.

## 25. Runbook When Tests Fail Only on CI

1. Record JDK, OS, test runner, parallelism mode, and JVM fork count.
2. Run the failing test in isolation.
3. Run it in small batches with potentially interfering tests.
4. Inspect **non-sensitive** configuration inputs.
5. Search for global mutations, static caches, and mutable singleton beans.
6. Check TestContext cache hits and property sources.
7. Check Testcontainers, mock servers, ports, and lifecycles.
8. Check database state, temporary files, and working directory.
9. Check Clock/Locale/Timezone assumptions.
10. Replace global mutations with per-test property sources where possible.
11. Apply ResourceLock/serialization where global state cannot be removed.
12. Re-run with shuffled ordering and parallelism to verify reproducibility.
13. Never print the full environment or secrets to logs while debugging.

## 26. Summary

- **OS environment is process input**; Spring test property sources do not change `System.getenv`.
- **JVM System properties are mutable shared state**; `System.setProperty` affects every test in the JVM.
- **Restoring in `finally`** protects tests after completion, yet does not stop parallel races.
- **`ApplicationContextRunner`, `MockEnvironment`, `@SpringBootTest(properties)`, and `@TestPropertySource`** provide far cleaner isolation for configuration inputs.
- **`@ActiveProfiles`** selects profiles without erasing other sources.
- **`@DynamicPropertySource`** requires coordinating container/mock-server lifecycles with the context cache.
- **`@DirtiesContext`** manages only the Spring context; it does not reset Java globals, files, DBs, or queues outside the context.
- **Static fields, singleton state, filesystems, timezones, ports, and external services** can all leak state across a suite.
- **Child processes** give a clean boundary when testing real OS environment variables at startup.
- The goal is tests that reproduce reliably standalone, across the full suite, in parallel, and on CI—without leaking secrets.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence, and binding.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` and test contexts.
- [Spring Boot Reference — Test Utilities](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html): `ApplicationContextRunner` and test helpers.
- [Spring Framework Reference — Property Sources in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): `@TestPropertySource`.
- [Spring Framework Reference — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource`.
- [Spring Framework Reference — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): cache keys and context reuse.
- [Spring Framework Reference — @DirtiesContext](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html): evicting contexts from cache.
- [JUnit Jupiter — Parallel Execution](https://docs.junit.org/current/user-guide/#writing-tests-parallel-execution): `@ResourceLock` and `@Isolated`.
- [JUnit Jupiter — @TempDir](https://docs.junit.org/current/user-guide/#writing-tests-built-in-extensions-TempDirectory): managing temporary test directories.
- [Testcontainers Java](https://java.testcontainers.org/): container lifecycles, dynamic ports, and integration testing.

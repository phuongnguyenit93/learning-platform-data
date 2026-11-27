# Supplying Test Properties with TestPropertySource and DynamicPropertySource

When testing Spring Boot or Spring Cloud applications, many beans and auto-configurations depend on values in `Environment`. For example, service discovery needs a mock service URI, an HTTP client needs an endpoint and timeouts, Config Client needs isolation from external environments, or an integration needs a host/port assigned by Testcontainers at startup.

Spring Test provides two key ways to supply properties into a test context. **`@TestPropertySource`** loads fixed values from resources or inline declarations in the test. **`@DynamicPropertySource`** registers suppliers that provide values when the property is read. Choosing the right one keeps tests clear, reproducible, and independent of the machine running them.

This lesson belongs to the **Testing** chapter of the `SPRING_CLOUD_CORE` module. It explains how to use both annotations, property precedence, configuration inheritance across test classes, Testcontainers integration, interactions with Spring Cloud Config, and common issues when Spring Test reuses an ApplicationContext.

## 1. Why Supply Dedicated Properties for Tests?

Real-world applications pull configuration from multiple sources: `application.yml`, profiles, environment variables, system properties, command-line arguments, or Config Server. When running tests, leaving production/development configuration untouched can cause tests to:

- Accidentally connect to a real database, Redis, or service discovery registry.
- Depend on fixed ports already occupied by another process.
- Fail to reproduce consistently in CI.
- Be affected by environment variables on a developer's workstation.
- Activate auto-configurations unsuitable for the test's goal.

Instead of editing main configuration files for each test, Spring Test lets you attach property sources to a test class's dedicated context. These values enter `Environment` before beans are created, so they influence `@ConfigurationProperties`, `@ConditionalOnProperty`, auto-configuration, and client configuration.

For example, suppose a test calls a mock catalog server:

```yaml
catalog:
  client:
    base-url: http://localhost:18081
    connect-timeout: 500ms
    read-timeout: 2s
```

These values are test-only. They can be declared with `@TestPropertySource` or supplied dynamically from a test server.

## 2. What Is @TestPropertySource?

`@TestPropertySource` belongs to the Spring TestContext Framework in package `org.springframework.test.context`. This annotation adds a property source to the `Environment` of the `ApplicationContext` created for the test.

There are two main ways to declare it:

1. `locations`: loads one or more `.properties` or XML properties files from the classpath or filesystem.
2. `properties`: declares inline key/value pairs directly on the annotation.

Inline example:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.base-url=http://localhost:18081",
        "catalog.client.connect-timeout=500ms",
        "catalog.client.read-timeout=2s"
})
class CatalogClientTest {
}
```

The properties take effect when Spring creates the test context. Beans reading `catalog.client.base-url` receive the test URL instead of values from lower-precedence application configuration.

### 2.1. Loading from a Resource File

When multiple tests share a configuration set, put properties in a dedicated file:

```properties
# src/test/resources/catalog-test.properties
catalog.client.base-url=http://localhost:18081
catalog.client.connect-timeout=500ms
catalog.client.read-timeout=2s
spring.cloud.config.enabled=false
```

Then:

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-test.properties"
)
class CatalogClientIntegrationTest {
}
```

The `classpath:` prefix resolves the resource on the test classpath. Multiple locations can be declared if a test needs to compose multiple configuration sets. Resource locations support the property formats specified by the Spring TestContext Framework; do not assume every Spring Boot configuration format is directly parsed by `@TestPropertySource`.

### 2.2. Declaring Both Locations and Properties

You can combine a shared file with per-test overrides:

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-test.properties",
        properties = {
                "catalog.client.read-timeout=100ms",
                "catalog.client.mode=stub"
        }
)
class FastCatalogClientTest {
}
```

Inline values in `properties` take higher precedence than values read from resource locations within the same `@TestPropertySource` group. Thus, the example above overrides the file's read timeout.

### 2.3. Default Location by Test Class Name

If neither `locations` nor `properties` is specified, Spring Test can look for a default properties file matching the fully qualified name of the test class in the same package. This works for tests with dedicated config, though it couples the resource filename to the class name. For configuration shared across multiple tests, explicit `locations` is usually easier to follow.

## 3. How @TestPropertySource Works

When the TestContext Framework creates an `ApplicationContext` for a test, the property source is registered before configurable beans are initialized. Consequently, auto-configuration conditions can observe the test values.

Example conditional configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "catalog.client",
        name = "stub",
        havingValue = "true"
)
class CatalogStubConfiguration {

    @Bean
    CatalogGateway catalogGateway() {
        return new StubCatalogGateway();
    }
}
```

Test enabling the stub:

```java
@SpringBootTest
@TestPropertySource(properties = "catalog.client.stub=true")
class CatalogStubConfigurationTest {
    // Context is created with the stub property already present.
}
```

The condition is evaluated during context creation. There is no need to mutate `Environment` after beans are created to enable this configuration.

### 3.1. Using with Spring Boot Tests

It can be combined with `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, or other test slices that create a Spring context and support the TestContext Framework.

Example:

```java
@WebMvcTest(CatalogController.class)
@TestPropertySource(properties = {
        "catalog.client.enabled=false"
})
class CatalogControllerTest {
}
```

With test slices, only part of auto-configuration is loaded. The property source is still added to the test context, though that does not mean the full application configuration is active.

### 3.2. Properties Must Exist Before Context Refresh

Do not treat `@TestPropertySource` as an API for changing properties after the context has initialized. The annotation describes input configuration for the test context; it is not a runtime refresh mechanism.

If you need to test behavior after configuration changes, use a refresh mechanism or state-updating bean and test that lifecycle separately. Do not expect modifying annotation values during a test run to recreate beans.

## 4. Property Precedence

When multiple sources declare the same key, the active value depends on property source precedence.

In the TestContext Framework, key points to remember are:

1. Dynamic properties registered via `@DynamicPropertySource` have higher precedence than properties declared via `@TestPropertySource`.
2. Inline properties in `@TestPropertySource(properties=...)` have higher precedence than resource locations in `@TestPropertySource(locations=...)`.
3. Test properties have higher precedence than standard configuration sources such as system properties, environment variables, and application property sources per test context rules.
4. If a test also combines Spring Boot-specific attributes like `@SpringBootTest(properties=...)`, verify the effective value via `Environment` rather than inferring solely from annotation order.

Example with the same key declared in both a file and inline:

```properties
# catalog-test.properties
catalog.client.mode=real
catalog.client.read-timeout=2s
```

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-test.properties",
        properties = "catalog.client.mode=stub"
)
class CatalogClientTest {
}
```

In this test, `catalog.client.mode` resolves to `stub` because inline test properties take higher precedence than resource locations.

### 4.1. Verifying the Actual Value

When diagnosing, inject `Environment`:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.mode=stub"
})
class CatalogPropertyTest {

    @Autowired
    Environment environment;

    @Test
    void usesTestProperty() {
        assertThat(environment.getProperty("catalog.client.mode"))
                .isEqualTo("stub");
    }
}
```

This verifies the resolved value. If a test has multiple configuration sources, inspect the property sources in `ConfigurableEnvironment` to identify the winning source. Avoid dumping the entire environment to logs, as it may contain passwords or tokens.

## 5. @TestPropertySource Configuration Inheritance

Test classes can inherit configuration from a superclass. By default, both resource locations and inline properties are inherited.

Two attributes control inheritance:

| Attribute | Default | Effect when set to false |
| --- | --- | --- |
| `inheritLocations` | `true` | Does not inherit locations from superclass |
| `inheritProperties` | `true` | Does not inherit inline properties from superclass |

Example superclass supplying shared configuration:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.mode=stub",
        "catalog.client.connect-timeout=500ms"
})
abstract class BaseCatalogTest {
}
```

Child test inheriting and overriding:

```java
@TestPropertySource(properties = {
        "catalog.client.read-timeout=100ms"
})
class FastCatalogTest extends BaseCatalogTest {
}
```

The child test receives both the superclass configuration and its own additional properties. When the same key is declared at both child and parent levels, the child configuration applies according to TestContext Framework inheritance rules.

### 5.1. Disabling Inheritance Intentionally

```java
@TestPropertySource(
        properties = "catalog.client.mode=real",
        inheritProperties = false
)
class RealCatalogTest extends BaseCatalogTest {
}
```

When `inheritProperties=false`, the child test does not receive inline properties from the superclass. This is helpful when a test needs an independent configuration set, though it can drop baseline properties other tests rely on.

Similarly, `inheritLocations=false` only suppresses inheriting resource locations. The two attributes govern two distinct groups; setting one does not automatically disable the other.

### 5.2. Multiple Annotations and Composition

`@TestPropertySource` can be repeated or composed via custom/meta-annotations depending on your Spring Test version. For complex configurations, group shared properties into a dedicated, well-named test annotation, while verifying ordering and inheritance so tests do not receive unexpected properties.

## 6. What Is @DynamicPropertySource?

`@DynamicPropertySource` is a Spring TestContext Framework annotation added in Spring Framework 5.2.5. It marks a static method accepting a `DynamicPropertyRegistry` and registers properties via suppliers.

Unlike fixed inline properties, a supplier can retrieve values available only after test resources have started. For instance, Testcontainers assigns random ports when mapping container ports to the host; tests cannot know that port before the container runs.

Structure:

```java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", () -> "http://localhost:18081");
}
```

The method must be `static` and accept `DynamicPropertyRegistry`. For each key, call `registry.add(name, supplier)` to register the value provider.

### 6.1. Suppliers Are Evaluated When Properties Are Resolved

`DynamicPropertyRegistry` takes a supplier rather than requiring an eagerly computed value. The supplier is invoked when the property is resolved. This fits runtime values such as hosts, mapped ports, or URLs provided by test servers.

Example:

```java
registry.add("catalog.client.base-url", mockServer::baseUrl);
```

If you call `mockServer.baseUrl()` before the server starts and pass a static string, the test may receive an unassigned port. Using a method reference retrieves the value when Spring actually resolves the property.

Laziness does not mean Spring automatically refreshes beans if a supplier's return value changes. It only describes how the property source reads values; already-initialized beans are not recreated just because a supplier returns a different value.

### 6.2. Registering Multiple Properties

```java
@DynamicPropertySource
static void catalogProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.host", mockServer::getHostName);
    registry.add("catalog.client.port", mockServer::getPort);
    registry.add("catalog.client.base-url", mockServer::baseUrl);
}
```

Each supplier should return a value type compatible with the property consumer. You can register `String`, `Integer`, `Boolean`, or types convertible by Spring's conversion mechanism. Keep suppliers simple, deterministic, and side-effect-free.

## 7. Using DynamicPropertySource with Testcontainers

Testcontainers typically assigns dynamic ports to prevent collisions between tests or CI processes. `@DynamicPropertySource` is the standard way to pass container addresses into a Spring test context.

Redis example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RedisIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine")
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
                "spring.data.redis.port",
                redis::getFirstMappedPort
        );
    }

    @Test
    void applicationCanUseRedis() {
        // Test interacts with the application's Redis bean.
    }
}
```

Testcontainers starts the container according to the JUnit extension lifecycle. Suppliers fetch the assigned host and mapped port, and Spring Boot binds the Redis properties before creating beans that require a connection.

Redis property names depend on the Spring Boot version and Redis client configuration. For applications using a different property prefix, register the exact keys read by your bean configuration.

### 7.1. Never Assume a Fixed Port

Do not write `localhost:6379` when Testcontainers maps ports dynamically. The port inside the container is 6379, while the host port can be anything else. Use `getHost()` and `getFirstMappedPort()` to obtain the live endpoint.

### 7.2. The Container Must Be Ready When Suppliers Resolve

Suppliers do not start the container themselves. The Testcontainers lifecycle must ensure the container is running before the application uses the properties to open connections. If managing containers manually, start the container before the Spring context resolves properties and stop it after the test.

### 7.3. Works for Databases, Brokers, and Mock Servers

The same pattern applies to PostgreSQL, Kafka, RabbitMQ, WireMock, or other test doubles:

```java
@DynamicPropertySource
static void serviceProperties(DynamicPropertyRegistry registry) {
    registry.add("catalog.client.base-url", mockServer::baseUrl);
    registry.add("catalog.client.connect-timeout", () -> "300ms");
}
```

The key point is that the supplier retrieves the actual endpoint after the resource is provisioned. Never log sensitive credentials or tokens while debugging these properties.

## 8. Comparing TestPropertySource and DynamicPropertySource

| Criterion | `@TestPropertySource` | `@DynamicPropertySource` |
| --- | --- | --- |
| How values are supplied | Inline or resource locations | Suppliers registered in a static method |
| Values | Typically fixed per test | Can depend on runtime resources |
| Evaluation time | Loaded as a test property source during context creation | Supplier called when the property is resolved |
| Use with Testcontainers | Possible if endpoint is known beforehand | Ideal when host/port are assigned dynamically |
| Inheritance | Has `inheritLocations`, `inheritProperties` | Static method can be inherited from superclass |
| Precedence | Higher than app property sources; inline higher than resources | Higher than `@TestPropertySource` |
| Common targets | Feature flags, timeouts, test profiles, fixed endpoints | Container ports, mock server URLs, runtime endpoints |

Selection rules:

- Use `@TestPropertySource` when values are known upfront and you want clear, readable test configuration.
- Use `@DynamicPropertySource` when values depend on resources started during test execution.
- Both can be combined: a file holds shared config while dynamic properties override dynamic endpoints.
- Avoid using a supplier for a fixed value if an inline property is already clear enough.

## 9. Combining Both Sources and Testing Precedence

Example where a test file sets a default endpoint while a container provides the live endpoint:

```properties
# catalog-integration.properties
catalog.client.base-url=http://localhost:18081
catalog.client.connect-timeout=500ms
catalog.client.read-timeout=2s
```

```java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/catalog-integration.properties"
)
@Testcontainers
class CatalogIntegrationTest {

    @Container
    static final GenericContainer<?> catalog =
            new GenericContainer<>("example/catalog-test:latest")
                    .withExposedPorts(8080);

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.client.base-url",
                () -> "http://" + catalog.getHost()
                        + ":" + catalog.getFirstMappedPort()
        );
    }
}
```

`catalog.client.base-url` is provided from the dynamic source and takes precedence over the file value. The timeout properties still come from the resource file.

This combination works well when most test configuration is shared and only a few endpoints are assigned dynamically. There is no need to duplicate entire property files across test classes.

## 10. Interaction with Spring Cloud Config

Spring Cloud applications can load remote properties from Config Server. Integration tests often need to control this so they do not depend on external configuration servers.

You can override the relevant feature flags or endpoints in tests:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "spring.cloud.config.enabled=false",
        "catalog.client.mode=stub",
        "catalog.client.base-url=http://localhost:18081"
})
class IsolatedCatalogTest {
}
```

Disabling Config Client must match how your application loads configuration and your Spring Cloud Config version. If the application uses Config Data import, inspect startup logs and the actual import mechanism; setting a single property does not guarantee all remote configuration is excluded in every setup.

In tests verifying Config Client or Config Server itself, do not disable the integration. Instead, use a mock server or dedicated test Config Server and supply the endpoint via a test property source.

### 10.1. Test Properties Can Affect Auto-Configuration

Properties such as `spring.cloud.discovery.enabled`, `spring.cloud.config.enabled`, or custom feature flags can flip conditions before beans are created. Therefore, tests must set the right properties before context refresh.

### 10.2. Do Not Use Test Properties to Hide Production Config Bugs

Isolating external dependencies in tests to verify specific logic is sound. However, if the goal is verifying production configuration, you must have integration tests validating real properties or the corresponding deployment profile. If every test overrides endpoints and disables integrations, configuration bugs in live environments can slip through undetected.

## 11. Context Caching and Dynamic Property Inheritance

The Spring TestContext Framework caches `ApplicationContext` instances to reduce test execution time. Tests with identical context configurations can share an already-created context.

This is especially important when `@DynamicPropertySource` lives in a superclass:

```java
abstract class BaseCatalogIntegrationTest {

    static MockWebServer server;

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.client.base-url", () ->
                server.url("/").toString());
    }
}
```

If multiple subclasses share the method yet each starts a different server or endpoint, the context cache may reuse the context created with the previous test's dynamic property. Subsequent tests may then call the wrong server or stale port.

### 11.1. Use @DirtiesContext When Dynamic Config Genuinely Differs

If subclasses need different dynamic values and cannot share a context, mark the context to be evicted from the cache with `@DirtiesContext` at the appropriate level—typically the base test class or the class whose configuration changes.

```java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class IsolatedCatalogEndpointTest extends BaseCatalogIntegrationTest {
}
```

`@DirtiesContext` closes the context and evicts it from the cache according to the selected mode; creating new contexts incurs overhead. Do not apply this annotation mechanically to every test. It is better to group tests sharing an endpoint under the same context or intentionally create separate test configurations.

### 11.2. Suppliers Do Not Automatically Differentiate Runtime Values in the Cache

Spring uses test configuration metadata to decide whether contexts can be reused. Do not assume that two suppliers sharing the same method yet returning different values will automatically cause Spring to build a new context. If endpoints change per subclass, design explicit cache boundaries and test reuse behavior.

## 12. Inheriting DynamicPropertySource

A static `@DynamicPropertySource` method in a superclass can be inherited by child test classes. This is useful when a group of tests shares a container or mock service.

Example:

```java
abstract class BaseRedisIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine")
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
                "spring.data.redis.port",
                redis::getFirstMappedPort
        );
    }
}
```

Subclasses can share the Redis endpoint. When all subclasses share the same container lifecycle and configuration, sharing the context reduces test time.

If each subclass needs a separate container or distinct values, avoid letting inheritance and context caching create subtle coupling. Split test classes/configurations or use `@DirtiesContext` when required.

## 13. Testing Properties and Configured Beans

Do not just verify that a property was read; verify that beans use the value properly.

Example properties class:

```java
@ConfigurationProperties(prefix = "catalog.client")
public class CatalogClientProperties {

    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(1);

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
```

Test:

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.base-url=http://localhost:18081",
        "catalog.client.connect-timeout=250ms"
})
class CatalogClientPropertiesTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void bindsTestValues() {
        assertThat(properties.getBaseUrl())
                .isEqualTo(URI.create("http://localhost:18081"));
        assertThat(properties.getConnectTimeout())
                .isEqualTo(Duration.ofMillis(250));
    }
}
```

This test verifies property binding. If the goal is testing a real HTTP client, add a mock server and assert requests hit the dynamic endpoint. If the goal is testing conditions, assert bean presence or absence in the context.

## 14. Common Mistakes

| Symptom | Possible cause | Investigation path |
| --- | --- | --- |
| Bean receives `application.yml` value instead of test value | Annotation placed on wrong test class, context ignores annotation, or key typo | Check test context, full key, and Environment |
| Inline property does not override file | Key mismatch or another source has higher precedence | Inspect resolved value and property sources |
| Dynamic property returns port 0 or stale port | Supplier invoked before resource ready or context cache kept old endpoint | Check container lifecycle and context reuse |
| `@DynamicPropertySource` not discovered | Method is not static or has wrong signature | Use a static method accepting `DynamicPropertyRegistry` |
| Testcontainers connects to wrong localhost port | Using container port instead of host mapped port or wrong host | Use `getHost()` and `getFirstMappedPort()` |
| Child test missing properties from superclass | `inheritProperties=false` or `inheritLocations=false` set | Check inheritance flags |
| Test affected by previous test | Using system properties/global state or improper context caching | Use test property sources and manage context lifecycle |
| Config Server still called during test | Config Data import or Config Client setup not properly disabled | Check import logs and version-specific Config Client behavior |
| Bean condition fails to match | Property added after context already refreshed | Supply property before startup and check condition report |
| Two subclasses hit wrong endpoint | Inherited dynamic property method with shared cached context | Split contexts or use `@DirtiesContext` appropriately |
| Test passes locally but fails on CI | Fixed port, reliance on pre-installed services, or different env vars | Use dynamic ports, containers, and property suppliers |

Investigation sequence:

1. Identify which test class creates the context and which annotations are active.
2. Check the exact property key and its value in `Environment`.
3. See whether the property comes from `@DynamicPropertySource`, inline test properties, or resources.
4. Check precedence between dynamic sources and test property sources.
5. Check whether the supplier returns the right value at resolution time.
6. Verify the container/mock server has started and port mapping is complete.
7. Check context caching and superclass/subclass inheritance.
8. Inspect the condition evaluation report if a bean is not created.
9. Ensure tests do not mutate global system properties or share mutable state.

## 15. Practice: Testing a Spring Cloud Client with Dynamic Endpoints

Suppose `order-service` calls `catalog-service` over an HTTP client. The test starts a mock server on a random port and passes its URL to the Spring context.

### Step 1 — Create a Mock Server

Use WireMock, MockWebServer, or an appropriate test HTTP server. The server must start before Spring resolves the `catalog.client.base-url` property.

### Step 2 — Register Dynamic Properties

```java
@SpringBootTest
class CatalogClientIntegrationTest {

    static final MockWebServer server = startServer();

    private static MockWebServer startServer() {
        try {
            MockWebServer value = new MockWebServer();
            value.start();
            return value;
        }
        catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    @AfterAll
    static void stopServer() throws IOException {
        server.shutdown();
    }

    @DynamicPropertySource
    static void catalogProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "catalog.client.base-url",
                () -> server.url("/").toString()
        );
    }
}
```

This is an illustrative skeleton with MockWebServer; ensure the appropriate test dependency is present and the server starts before Spring resolves the supplier. With Testcontainers, you can use a static `@Container` to manage lifecycle.

### Step 3 — Supply Fixed Properties with TestPropertySource

```java
@SpringBootTest
@TestPropertySource(properties = {
        "catalog.client.connect-timeout=300ms",
        "catalog.client.read-timeout=1s",
        "catalog.client.retry.enabled=false"
})
class CatalogClientIntegrationTest {
    // Can be combined with DynamicPropertySource in the same test class.
}
```

The endpoint is supplied dynamically; timeouts and retry flags are declared statically. Two annotations address two different kinds of data.

### Step 4 — Verify Requests

Register a mock response for the catalog path, invoke the service client, and verify the request reaches the mock server. Tests should assert HTTP method, path, query parameters, and required payloads—not merely that the bean initialized.

### Step 5 — Verify Isolation

Run the test standalone and across the full suite. Confirm:

- No real catalog service is contacted.
- Ports are dynamically allocated with no collisions.
- Tests do not depend on execution order.
- Context caching does not cause tests to use another class's endpoint.
- The server shuts down after tests.
- Test values do not leak into the JVM or other test classes.

### Self-Check Questions

1. Which framework provides `@TestPropertySource` and where does it add properties?
2. What are the two primary ways to declare `@TestPropertySource`?
3. What is the precedence order between inline properties and resource locations?
4. What do `inheritLocations` and `inheritProperties` control?
5. Why does `@DynamicPropertySource` use a static method?
6. What problem does `DynamicPropertyRegistry.add` accepting a supplier solve?
7. Why does Testcontainers pair well with `@DynamicPropertySource`?
8. Does a dynamic property automatically recreate beans when a supplier returns a new value?
9. What is the precedence between dynamic properties and `@TestPropertySource`?
10. Why can context caching cause subclasses to use the wrong endpoint?
11. When should `@DirtiesContext` be used?
12. Why inspect values in `Environment` instead of only reading annotations?

**Answer hints:** (1) Spring TestContext Framework; it adds a property source to the test context's Environment; (2) `locations` and `properties`; (3) Inline properties have higher precedence than resource locations; (4) Inheritance of configuration files and inline properties from a superclass; (5) Spring must register suppliers before the context is created, following the annotation's static contract; (6) Retrieving values known only at runtime such as host/port; (7) Containers allocate mapped ports at startup; (8) No, lazy suppliers do not imply automatic bean refresh; (9) Dynamic properties have higher precedence; (10) An already-created context may be reused with the old endpoint configuration; (11) When tests need a fresh context because dynamic configuration differs; (12) To verify which property source and value actually resolved.

## 16. Key Principles to Remember

- `@TestPropertySource` supplies fixed properties via resource locations or inline properties to a Spring test context.
- Inline `properties` take higher precedence than resource `locations` within the same configuration.
- Test properties can govern `@ConfigurationProperties`, `@ConditionalOnProperty`, and auto-configuration before beans are created.
- `inheritLocations` and `inheritProperties` allow inheriting superclass configuration by default.
- `@DynamicPropertySource` uses a static method receiving `DynamicPropertyRegistry` to register suppliers.
- Suppliers fit hosts, ports, and endpoints assigned when test resources start.
- Dynamic properties take higher precedence than `@TestPropertySource`.
- Suppliers resolve lazily, but do not automatically refresh already-created beans.
- Testcontainers must provide actual hosts and mapped ports; never assume fixed host ports.
- Spring Test's context cache can retain stale dynamic configuration if multiple subclasses share a context yet require different endpoints.
- Use `@DirtiesContext` intentionally when a context must be evicted from cache; prefer designing tests to share contexts when configurations truly match.
- Verify effective values in `Environment`, and test property binding, bean conditions, and live requests.

Using `@TestPropertySource` for static configuration and `@DynamicPropertySource` for runtime endpoints keeps Spring Cloud tests independent of infrastructure running on developer machines. When precedence, resource lifecycle, and context caching are properly managed, tests run reliably both locally and in CI and verify true configuration behavior before release.

## References

- [Spring Framework Reference — Context Configuration with TestPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework Reference — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework API — TestPropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestPropertySource.html)
- [Spring Framework API — DynamicPropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/DynamicPropertySource.html)
- [Testcontainers for Java](https://java.testcontainers.org/)

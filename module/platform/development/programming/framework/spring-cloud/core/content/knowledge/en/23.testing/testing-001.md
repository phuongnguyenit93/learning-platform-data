# Layering Property, Context, and Integration Tests

Spring Cloud applications receive configuration from multiple sources and coordinate multiple components such as Spring Cloud Context, Config Client, service discovery, and LoadBalancer. A bug can start from an unbound property, a wrong profile selection, a bean not being created, refresh failing to recreate a target, or a registry returning an instance that the consumer cannot reach.

Do not verify every scenario with one massive **@SpringBootTest**. Choose the testing layer based on the behavior you need to prove: verify properties and auto-configuration with a lightweight context; verify bean lifecycle inside a Spring context; verify Config Server, registry, and HTTP through controlled integration tests.

This lesson belongs to the **Testing** chapter of the **SPRING_CLOUD_CORE** module. It focuses on how to structure tests for external configuration, Spring Cloud Context, Config Client/Server, service discovery, and load balancing; how to choose test fixtures; and how to avoid slow, environment-dependent, or flaky tests.

## 1. Learning Objectives

After this lesson, learners can:

- Distinguish unit tests, property binding tests, context tests, and integration tests.
- Test **@ConfigurationProperties**, validation, profiles, and property precedence.
- Use **ApplicationContextRunner** to test beans and auto-configuration in a small context.
- Choose properly between **@SpringBootTest**, test slices, and **@TestConfiguration**.
- Test **@RefreshScope** and target bean recreation.
- Test Config Client against a mock or real Config Server.
- Test service discovery and Spring Cloud LoadBalancer without relying on a production registry.
- Use **@DynamicPropertySource** to supply dynamic addresses/ports of test resources.
- Design tests for failure cases, timeouts, missing instances, and invalid configuration.
- Keep tests independent, repeatable, and suitable for running in CI.

## 2. Choosing the Testing Layer by the Question to Answer

Each layer answers a different kind of question:

| Layer | Main question | Common tools | Scope |
| --- | --- | --- | --- |
| Unit test | Is the pure logic correct? | JUnit, Mockito, AssertJ | A single class or method, without starting Spring |
| Property test | Are values bound/validated correctly? | Binder, ApplicationContextRunner | Environment, ConfigurationProperties |
| Context test | Do beans, conditions, and scopes work? | ApplicationContextRunner, SpringBootTest | Part or all of an ApplicationContext |
| Integration test | Do components communicate properly across real boundaries? | SpringBootTest, WireMock, Testcontainers | HTTP, Config Server, registry, database |
| Contract test | Do two services uphold the API contract? | Spring Cloud Contract or equivalent contract tests | Provider and consumer |

Start from the smallest layer capable of proving the behavior:

- Checking that a timeout binds to a Duration does not require starting a Config Server.
- Checking whether ConditionalOnProperty creates a bean does not require opening an HTTP port.
- Checking that RefreshScope recreates a target can be done in a context test.
- Checking that Config Client sends the right application/profile to Config Server requires a mock HTTP server or a real Config Server.
- Checking that a registered instance is reachable from a consumer requires testing over the corresponding network/registry.

A test only proves the parts it actually exercises. ApplicationContextRunner does not prove that Config Server works; mocking DiscoveryClient does not prove that a production registry registers the right address.

## 3. Testing ConfigurationProperties and Validation

Configuration classes should be tested independently of external infrastructure. For example, an internal client that needs a base URL and timeout:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "catalog.client")
@Validated
public record CatalogClientProperties(
        @NotBlank String baseUrl,
        @Min(1) @Max(5000) int timeoutMs) {
}
```

Register the properties class in a test configuration:

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogClientProperties.class)
class CatalogPropertiesTestConfiguration {
}
```

Use ApplicationContextRunner to create a lightweight context with specific values:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogClientPropertiesTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(CatalogPropertiesTestConfiguration.class);

    @Test
    void bindsValidProperties() {
        contextRunner
            .withPropertyValues(
                "catalog.client.base-url=https://catalog.internal",
                "catalog.client.timeout-ms=800"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();

                CatalogClientProperties properties =
                    context.getBean(CatalogClientProperties.class);

                assertThat(properties.baseUrl())
                    .isEqualTo("https://catalog.internal");
                assertThat(properties.timeoutMs()).isEqualTo(800);
            });
    }

    @Test
    void rejectsInvalidTimeout() {
        contextRunner
            .withPropertyValues(
                "catalog.client.base-url=https://catalog.internal",
                "catalog.client.timeout-ms=0"
            )
            .run(context -> assertThat(context).hasFailed());
    }
}
```

For Jakarta Validation annotations to take effect, the project needs a Bean Validation implementation, usually brought in via **spring-boot-starter-validation**. Without an implementation, binding tests may run without enforcing constraints as expected.

### 3.1. Checking Default and Missing Values

Do not only test the fully configured case. Include tests for:

- A missing property when the field has a default.
- A missing property that is required.
- An empty or whitespace-only string.
- Numeric values outside the allowed bounds.
- An invalid enum value.
- Malformed Duration or URI values.
- Partially missing nested properties.

If a constructor-bound record has no default, verify that the context fails with a clear cause. This helps catch configuration errors at startup rather than on the first service call.

### 3.2. Testing Binder Directly

When you only need to verify conversion and binding, you can use Binder without creating an ApplicationContext:

```java
import java.util.HashMap;
import java.util.Map;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

Map<String, Object> values = new HashMap<>();
values.put("catalog.client.base-url", "https://catalog.internal");
values.put("catalog.client.timeout-ms", "800");

ConfigurationPropertySource source =
    new MapConfigurationPropertySource(values);

CatalogClientProperties properties = new Binder(source)
    .bind("catalog.client", CatalogClientProperties.class)
    .orElseThrow();

assertThat(properties.timeoutMs()).isEqualTo(800);
```

This approach is fast and isolated. However, it does not verify EnableConfigurationProperties, Bean Validation inside the context, component scanning, or auto-configuration. Use ApplicationContextRunner when you need to prove those parts.

## 4. Testing Property Sources, Profiles, and Precedence

A Spring Boot application can receive configuration from many places: Config Data, profile-specific files, environment variables, JVM system properties, command-line arguments, PropertySource, and test-registered property sources.

In tests, set values explicitly so results do not depend on the developer's machine or the CI runner.

### 4.1. Selecting a Test Profile

Use ActiveProfiles to specify the profile:

```java
@SpringBootTest
@ActiveProfiles("test")
class CatalogConfigurationTests {
    // Test uses application-test.yml and the declared test properties.
}
```

The `application-test.yml` file should hold test-specific values such as mock service URLs, short timeouts, and feature flags. Never put production credentials in test resources.

### 4.2. Overriding Properties in Tests

`@SpringBootTest(properties = ...)` is suitable when you need a few inline values:

```java
@SpringBootTest(properties = {
    "catalog.client.base-url=http://localhost:18081",
    "catalog.client.timeout-ms=300"
})
class CatalogClientContextTests {
}
```

TestPropertySource is suitable when you want to manage a separate test properties file:

```java
@SpringBootTest
@TestPropertySource(locations = "classpath:/catalog-client-test.properties")
class CatalogClientPropertySourceTests {
}
```

When you need values supplied dynamically from Testcontainers, WireMock, or a server running on a random port, use DynamicPropertySource:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class CatalogDatabaseIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("catalog")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
```

This example illustrates how to supply a dynamic endpoint; real database configuration also requires the database name, username, and password matching the started container.

Dynamic properties have higher precedence than TestPropertySource, OS environment variables, system properties, and property sources declared via PropertySource or added by the application. Therefore, if a value in a test is not what you expect, inspect both its source and its precedence order.

### 4.3. Checking Origin When Values Are Overridden

When a test only asserts the final value, you may miss that it came from an unintended source. For precedence bugs, inspect the Environment and the corresponding origin/property source, or use the Actuator env endpoint in a secured test environment.

Examples to distinguish:

- `catalog.client.base-url` comes from `application-test.yml`.
- The same key is overridden by DynamicPropertySource.
- An environment variable on the CI machine accidentally alters the outcome.

Do not use DynamicPropertySource for every property just for convenience. Use it for resources whose address/port is only known after starting the test fixture.

## 5. Using ApplicationContextRunner to Test Beans and Auto-Configuration

ApplicationContextRunner starts a small context, runs the assertion callback, and automatically closes the context. It is the right tool for testing:

- ConditionalOnProperty.
- ConditionalOnClass.
- Beans created when a dependency is present.
- Default beans backing off when the application provides its own bean.
- Properties bound into auto-configuration.
- Context startup failures when a dependency or required configuration is missing.

Example auto-configuration that only creates a bean when a feature is enabled:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "catalog.cache",
    name = "enabled",
    havingValue = "true"
)
class CatalogCacheConfiguration {

    @Bean
    CatalogCache catalogCache() {
        return new CatalogCache();
    }
}
```

Test both branches:

```java
class CatalogCacheConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(CatalogCacheConfiguration.class);

    @Test
    void createsCacheWhenEnabled() {
        runner.withPropertyValues("catalog.cache.enabled=true")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogCache.class);
            });
    }

    @Test
    void doesNotCreateCacheWhenDisabled() {
        runner.withPropertyValues("catalog.cache.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(CatalogCache.class);
            });
    }
}
```

If testing Spring Cloud auto-configuration, pass only the target configuration into the runner and include only the relevant dependencies/auto-configurations. Avoid loading the entire application when the question is just a bean creation condition.

## 6. Choosing SpringBootTest or a Test Slice?

`@SpringBootTest` creates the ApplicationContext of the application or specified test configuration. Use it when you need to test the coordination of multiple beans, Config Client, refresh scope, or a real HTTP server.

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CatalogApplicationIntegrationTests {
    // Verifies the application has started and endpoints can be called over HTTP.
}
```

Test slices load only part of the application:

| Annotation | Scope |
| --- | --- |
| @WebMvcTest | Controllers, MVC configuration, converters, and filters in the MVC slice |
| @DataJpaTest | Entities, repositories, and JPA configuration |
| @RestClientTest | HTTP client components as supported by the Spring Boot version in use |
| @JsonTest | Serialization/deserialization |
| @SpringBootTest | The full ApplicationContext of the application |

For example, `@WebMvcTest` is suitable for verifying that a controller returns the right status and JSON. It does not prove that Config Server, Eureka, or LoadBalancer is configured properly, because those components are usually not part of the MVC slice.

### 6.1. Adding Test-Only Configuration

Use TestConfiguration to add mock beans or fixtures to the test context:

```java
@TestConfiguration(proxyBeanMethods = false)
class CatalogTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
```

Import this configuration into a test with `Import(CatalogTestConfiguration.class)`. A nested TestConfiguration is added to the application configuration; it does not replace the primary configuration the way a regular nested Configuration might.

### 6.2. Understanding Context Caching and DirtiesContext

The Spring TestContext Framework caches ApplicationContext instances across tests with equivalent configurations. This reduces startup time.

DirtiesContext marks the context as modified so it is removed from the cache and a fresh context is created for the next use. Only use it when a test genuinely mutates context state that cannot be safely restored, such as modifying a singleton bean or global scope configuration.

Do not add DirtiesContext to every test just to "be safe and clean." It slows down the suite and can hide the fact that tests are sharing mutable state.

## 7. Testing RefreshScope and Bean Recreation

RefreshScope creates a proxy for the bean and manages the initialized target. When the target is invalidated, the next call creates a new target and re-runs the bean's lifecycle.

You can test this lifecycle by supplying a dynamic property, changing its value, and calling `RefreshScope.refresh(beanName)`:

```java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.cloud.context.scope.refresh.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = RefreshScopeTestApplication.class)
class RefreshScopeTests {

    private static final AtomicReference<String> MESSAGE =
        new AtomicReference<>("before");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("catalog.message", MESSAGE::get);
    }

    @Autowired
    MessageProvider messageProvider;

    @Autowired
    RefreshScope refreshScope;

    @Test
    void recreatesRefreshScopedTarget() {
        assertThat(messageProvider.message()).isEqualTo("before");

        MESSAGE.set("after");

        assertThat(refreshScope.refresh("messageProvider")).isTrue();
        assertThat(messageProvider.message()).isEqualTo("after");
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class RefreshScopeTestApplication {

        @Bean
        @RefreshScope
        MessageProvider messageProvider(
                @Value("${catalog.message}") String message) {
            return () -> message;
        }
    }

    interface MessageProvider {
        String message();
    }
}
```

This test proves that the bean's target is recreated and picks up the new value from the Environment. It does not prove that Config Client called Config Server to fetch updated property sources.

### 7.1. Distinguishing Target Refresh from Environment Refresh

There are two separate parts to test:

1. **Refresh scope:** the target bean is evicted from cache and recreated on the next access.
2. **Environment refresh:** property sources are updated, properties are rebound, and change events are published according to the active refresh mechanism.

If you only call `refreshScope.refresh("messageProvider")`, you are testing the first part. To test the full path from external configuration to the bean, you need an integration test that modifies the configuration source, triggers the appropriate refresh mechanism, and verifies the new value.

Items to include in tests:

- Is the bean actually inside RefreshScope?
- Is the bean name passed to `refresh(String)` correct?
- Does the bean hold onto a bound value inside a non-refreshed dependency?
- Does the bean reinitialize successfully?
- Is a higher-precedence property source still shadowing the new value?

Spring Cloud does not update the presence of a property simply because that key was removed from the source and refresh was triggered. If business logic needs an on/off toggle, test behavior when the value is explicitly changed rather than relying solely on key deletion.

## 8. Testing Spring Cloud Config Client

Config Client loads configuration from Config Server via Config Data import. An integration test should prove at least:

- `spring.application.name` is sent correctly.
- Profile and label are selected correctly.
- Properties from the remote source appear in the Environment.
- Values bind into beans as expected.
- Behavior when Config Server is unreachable matches `optional:` or fail-fast mode.

Example client configuration in a test:

```properties
spring.application.name=orders
spring.profiles.active=integration
spring.config.import=configserver:http://localhost:18888
```

You can run a mock HTTP server like WireMock on a fixed test port or start it before the Spring test context is created. The mock server returns a Config Server Environment response for the corresponding paths:

- `/orders/default`
- `/orders/integration`

Spring Boot Config Data may load configuration in two passes: first with the `default` profile, and then loading any activated profiles. Therefore, the mock server must serve the requests the client actually sends rather than assuming a single request for the final profile.

The Environment response contains the application name, profiles, label, and list of `propertySources`. Abbreviated example:

```json
{
  "name": "orders",
  "profiles": ["integration"],
  "label": null,
  "version": "test-revision",
  "propertySources": [
    {
      "name": "orders-integration.yml",
      "source": {
        "catalog.page-size": 40
      }
    }
  ]
}
```

After the context starts, verify the `catalog.page-size` property in the Environment and the corresponding ConfigurationProperties bean. Also verify that requests hit the expected path, application name, and profile.

### 8.1. Testing Config Server Unavailability

Run two separate scenarios:

| Import configuration | Expected result when Config Server is unavailable |
| --- | --- |
| spring.config.import=optional:configserver:http://localhost:18888 | Application can continue starting without remote properties |
| spring.config.import=configserver:http://localhost:18888 | Startup fails if required configuration cannot be retrieved |

Do not use `optional:` in every test. If production configuration requires Config Server for mandatory credentials or endpoints, tests must prove that the application fails when that configuration source is unavailable.

### 8.2. Testing Config Server Separately

You can test Config Server with the native/file-system backend in tests. Enable the `native` profile, point `spring.cloud.config.server.native.searchLocations` to a fixture directory, start the server on a random port, and call `/{application}/{profile}/{label}`.

Server-side tests verify:

- The fixture repository is read properly.
- Application/profile/label selects the right files.
- Property sources and precedence are correct.
- Encrypted/decrypted values are handled per test configuration if encryption is used.

Client-side tests verify that Config Client consumes that response. Keeping these two tests separate helps distinguish repository/server bugs from client import bugs.

## 9. Testing Service Discovery and LoadBalancer

A discovery test needs to verify two layers:

1. Discovery returns the expected list of `ServiceInstance` objects.
2. The HTTP client uses the service ID to choose and call an instance.

When you do not need to test a real registry, you can use SimpleDiscoveryClient with instances declared via test properties:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
```

This setup is suitable for LoadBalancer tests without standing up Eureka or Consul. SimpleDiscoveryClient is used when there is no service-registry-based discovery client on the classpath. If the test has a real Eureka/Consul client, configure or mock the actual discovery implementation rather than assuming the simple client will be selected.

### 9.1. Verifying Requests Go Through LoadBalancer

With Spring Boot 3.2+ and Spring Framework 6.1+, you can use `@LoadBalanced RestClient.Builder`. Example:

```java
@Configuration(proxyBeanMethods = false)
class TestHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder(
            RestClientBuilderConfigurer configurer) {
        return configurer.configure(RestClient.builder());
    }
}
```

The client in the test must call by service ID:

```java
String response = restClient.get()
    .uri("http://catalog-service/api/items")
    .retrieve()
    .body(String.class);
```

Two mock HTTP servers listen on two ports. Configure SimpleDiscoveryClient to point to those ports, then verify that the request is received at an instance from the list.

If the project uses a Spring Boot version older than 3.2, choose RestTemplate or WebClient according to that release train's load balancer integration API; do not force Spring Framework 6.1 into an older Boot project just to use RestClient.

### 9.2. Do Not Test Round-Robin by Hardcoding Order Assumptions

A test should not assume the first request always goes to instance A and the second always goes to B, unless it controls the supplier, cache, and load balancer state.

Instead:

- Verify that the chosen host is in the valid instance list.
- Verify that the request path/headers/body are preserved.
- Verify that having no instances yields the appropriate no-instance error.
- If you need to test the round-robin algorithm, configure a deterministic test supplier and isolate the context per service ID.

Spring Cloud LoadBalancer creates a separate context per service ID and can cache the instance list. Therefore, instance distribution tests must control caching or create a fresh context between scenarios.

### 9.3. Testing a Real Registry When Needed

If the goal is to prove Eureka/Consul registration works properly, you need an integration test with the corresponding registry. Use Testcontainers or an equivalent fixture to start the registry, supply the dynamic address via DynamicPropertySource, start the service, and check:

- Service ID and instance ID.
- Host, port, secure flag, and metadata.
- Registration/heartbeat status.
- Deregistration when the instance stops.
- Consumer retrieves the instance from the registry and successfully calls the endpoint.

Mocking DiscoveryClient only tests application-side logic. It does not prove that a real registry receives heartbeats, updates status, or evicts stopped instances.

## 10. Testing HTTP Clients and Service Call Failures

For internal clients, separate client testing from discovery testing:

- Test request paths, query parameters, headers, and bodies with a mock HTTP server.
- Test response mapping to DTOs.
- Test 4xx/5xx error handling.
- Test timeouts and connection failures.
- Test LoadBalancer host selection by service ID.
- Test retry/circuit breaker at the corresponding configuration layer if the application uses them.

Do not let a single test simultaneously check JSON mapping, start Config Server, registry, database, and the entire application. When such a test fails, it is hard to tell which boundary broke.

For write requests such as creating an order or processing a payment, test retries separately. Only retry when the API has an idempotency key or a business contract guaranteeing the operation will not be executed twice.

## 11. Testing Events and Configuration Changes

Spring Cloud Context includes events such as `EnvironmentChangeEvent` and the refresh scope mechanism. If the application has listeners that update caches, feature flags, or log levels when configuration changes, test both the listener and the event-publishing path.

Example listener:

```java
@Component
class FeatureFlagListener {

    private volatile boolean enabled;

    @EventListener
    void onEnvironmentChange(EnvironmentChangeEvent event) {
        if (event.getKeys().contains("feature.catalog.enabled")) {
            // Re-read the property or update state according to application policy.
        }
    }
}
```

In a unit test, you can publish `EnvironmentChangeEvent` with a specific key set to verify listener logic. In an integration test, update the property source and trigger refresh using the exact mechanism the application uses, then verify the listener receives the event and state is updated.

Do not use a synthetic test event to conclude that Config Client downloaded new data from Config Server. Those two tests prove two different boundaries.

## 12. Managing Fixtures and State Across Tests

Spring Cloud components can retain caches or state per context/process:

- ApplicationContext is cached across tests by Spring TestContext.
- LoadBalancer maintains child contexts per service ID and may cache instance lists.
- RefreshScope holds target beans until cache entries are invalidated.
- Mock HTTP servers maintain request journals and stubs.
- Testcontainers may be shared across a class or suite lifecycle.
- Static mutable state can persist across tests in the same JVM.

To avoid order-dependent tests:

1. Initialize fixtures before the ApplicationContext needs to read configuration.
2. Use dynamic ports and register them with DynamicPropertySource.
3. Clear the request journal or reset stubs before each test when needed.
4. Use distinct cache keys/service IDs per scenario or actively refresh caches.
5. Do not mutate shared static state if tests run in parallel.
6. Close servers/containers and contexts according to the test framework lifecycle.
7. Do not use `Thread.sleep()` to wait for a registry; wait on a condition with a timeout or poll state in a controlled manner.

If a test passes when run in isolation but fails when running the whole suite, check for shared state, context caching, static fields, or fixed ports before increasing timeouts.

## 13. Common Mistakes When Writing Spring Cloud Tests

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Test property does not override old value | Test source has lower precedence or context was cached | Check property sources and use DynamicPropertySource/test properties properly |
| ConfigurationProperties not bound | Properties class not registered | Use EnableConfigurationProperties or configuration scanning |
| Validation does not run | Missing Bean Validation implementation | Add spring-boot-starter-validation and Validated |
| Test context does not create bean | Condition or classpath dependency not satisfied | Use ApplicationContextRunner to test each condition |
| RefreshScope still returns old value | Bean is not in refresh scope or target was not invalidated | Check scope, bean name, and RefreshScope.refresh |
| Deleting property and refreshing leaves old value in bean | Refresh does not automatically propagate removal of a deleted property | Check absence/default logic; use explicit state values |
| Config Client calls multiple endpoints | Config Data loads default profile then active profiles | Stub all actual requests; do not assume a single pass |
| Config Client starts even when Config Server is down | Using `optional:` | Remove `optional:` when remote config is mandatory |
| LoadBalancer reports no instances | Wrong service ID or discovery returns no instances | Check DiscoveryClient/SimpleDiscoveryClient and configuration |
| LoadBalancer calls wrong instance in test | Cache/supplier or per-service-ID context retains state | Isolate contexts, reset fixtures, and inspect instance list |
| Registry test is flaky | Waiting with sleep or heartbeat not yet completed | Wait on registry condition with timeout |
| Test passes alone but fails in full suite | Context cache or shared static state | Reset state, remove order dependencies, control parallelism |
| Integration test depends on developer machine | Fixed ports, local profiles, or local env variables | Use dynamic ports, test profile, and dynamic properties |

## 14. Recommended Test Matrix for the Spring Cloud Core Module

A module with Config Client, refresh scope, discovery, and an HTTP client can organize its suite as follows:

| Test group | Example scenario | Layer |
| --- | --- | --- |
| Configuration binding | Bind URI, timeout, retry, validation | Property test |
| Property precedence | Test profile overrides application default | Property/context test |
| Conditional beans | Enable/disable feature or discovery client | Context test |
| Refresh scope | Change property and recreate target bean | Context test |
| Config Client | Import remote properties, fail-fast, optional source | Integration test |
| Config Server | Native repository, application/profile/label | Integration test |
| Service discovery | Fetch instances by service ID | Context/integration test |
| LoadBalancer | Call multiple instances, no-instance, host selection | Integration test |
| HTTP client | DTO mapping, headers, status, timeout | Client test |
| Registry lifecycle | Register, heartbeat, deregister | Integration test |
| Config event | Listener receives changed keys and updates state | Unit/context test |
| Resilience | Retry, timeout, and instance errors | Integration test |

Not every project needs every row. Choose the groups matching the dependencies and behaviors actually present in your module.

## 15. Organizing Test Execution in CI

A sensible pipeline can be split into three tiers:

- **Fast tests:** unit tests, Binder/property tests, and ApplicationContextRunner; run frequently on every commit.
- **Application tests:** SpringBootTest, MVC/client slices, and refresh scope tests; run on pull requests.
- **Infrastructure integration tests:** Config Server, registry, database, and Testcontainers; run on relevant changes or in the full CI pipeline.

Keep dependency versions aligned using the Spring Cloud BOM and Spring Boot dependency management. When tests fail after an upgrade, record the Boot version, Cloud release train, JDK, and relevant dependency tree. Do not fix test failures by forcing a single Spring Cloud module to a different version without checking the compatibility matrix.

Tests need reasonable timeouts and explicit cleanup. An integration test should not depend on a public Config Server, a team-shared registry, or production data. Use isolated fixtures per run so one test cannot alter the outcome of another.

## 16. Practice Exercise

An `order-service` uses:

- ConfigurationProperties to read the URL and timeout of `catalog-service`.
- Spring Cloud Config Client to load profile-specific configuration.
- RefreshScope for a bean holding a feature flag.
- Eureka to register and discover instances.
- LoadBalanced `RestClient.Builder` to call `catalog-service`.

Design and implement the following tests:

1. A property test verifying a valid URL, valid timeout, and out-of-bounds timeout.
2. A profile test proving `application-test.yml` is selected.
3. A precedence test proving DynamicPropertySource overrides property files.
4. A context test verifying a bean is created only when the feature flag is enabled.
5. A refresh test changing the feature flag and confirming the RefreshScope target is recreated.
6. A Config Client integration test mocking Config Server and verifying application name and profile.
7. A fail-fast test confirming the application stops when a required Config Server is unavailable.
8. A discovery test confirming `catalog-service` returns the expected instance list.
9. A LoadBalancer integration test calling by service ID and confirming the request reaches a valid instance.
10. A registry integration test verifying registration, heartbeat, and deregistration.
11. An HTTP client test verifying response DTO mapping, 5xx handling, and timeouts.
12. Run the full suite multiple times and confirm results do not depend on test order.

**Completion criteria:** each test clearly identifies the layer and boundary it proves; no external infrastructure is started in property/context tests; integration tests have isolated fixtures, dynamic ports, and cleanup; configuration errors and missing-instance cases are explicitly tested.

## 17. Takeaways

- Unit tests verify logic; property tests verify binding/validation; context tests verify beans/conditions/scopes; integration tests verify communication across components.
- ApplicationContextRunner is ideal for properties and auto-configuration because the context is small and closes after each run.
- Use ActiveProfiles, TestPropertySource, and DynamicPropertySource to control test configuration.
- DynamicPropertySource is suited for supplying ports/URLs of Testcontainers or mock servers and takes precedence over many other test sources.
- SpringBootTest tests the application context; test slices load only part of the system.
- DirtiesContext evicts the context from the cache; use it only when a test genuinely dirties context state.
- Test RefreshScope target recreation separately from fetching new configuration from Config Server.
- Config Data import may cause Config Client to query Config Server for `default` and then active profiles.
- SimpleDiscoveryClient is useful for LoadBalancer tests without a registry; registry lifecycle needs its own integration test.
- Do not assume rigid round-robin ordering without controlling the supplier and cache.
- Use dynamic ports, isolated fixtures, cleanup, and controlled static state to keep tests reliable in CI.

## 18. References

- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): SpringBootTest, test configuration, and context caching.
- [Spring Boot — ApplicationContextRunner and Auto-configuration Testing](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): testing bean creation conditions and auto-configuration in a small context.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): DynamicPropertySource, DynamicPropertyRegistry, and precedence.
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): TestPropertySource and property sources in the test context.
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): RefreshScope, RefreshScope.refreshAll(), and refreshing beans by name.
- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, profile loading, optional import, and fail-fast.
- [Spring Cloud Config Server — File System Backend](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/file-system-backend.html): native profile and searchLocations for test servers.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): discovery supplier, caching, health checks, and instance selection.
- [Spring Cloud — Centralized Configuration Guide](https://spring.io/guides/gs/centralized-configuration): end-to-end example of Config Client and refresh endpoint.

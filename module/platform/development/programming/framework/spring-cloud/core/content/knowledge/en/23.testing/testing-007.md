# Testing PropertySourceLocator with Controlled Data Sources

`PropertySourceLocator` is a Spring Cloud Context extension point used to look up additional `PropertySource` instances from external sources in the legacy bootstrap flow. The locator receives the `Environment` being prepared and returns an appropriate property source, such as configuration keyed by application name or profile. When testing a locator, it is essential to control the input data so every run yields the same result without depending on Config Server, databases, or external networks.

This lesson belongs to the **Testing** chapter of the **SPRING_CLOUD_CORE** module. We will build a small locator reading from a simulated in-memory repository, verify how it selects data by application/profile, validate the returned property source, test precedence order, and write a bootstrap context integration test. At the end, we contrast testing legacy locators with Spring Boot Config Data.

## 1. Learning Objectives

After this lesson, you can:

- Explain the contract of `PropertySourceLocator.locate(Environment)`.
- Distinguish the locator, the data-providing repository, and the returned `PropertySource`.
- Create a `MockEnvironment` with deterministic application name and active profiles.
- Use `TestPropertyValues` to supply input properties for unit tests.
- Write an in-memory fake repository instead of making HTTP or database calls.
- Verify the name, contents, and value types inside `MapPropertySource`.
- Test missing data, error conditions, and different profiles.
- Verify precedence when property sources are added into `Environment`.
- Register a locator in the bootstrap context to run integration tests.
- Understand why a locator can be invoked multiple times when profiles are activated.
- Distinguish legacy bootstrap from Config Data using `spring.config.import`.
- Avoid tests that depend on invocation counts, timing, or shared state across tests.

## 2. What Does PropertySourceLocator Do?

`PropertySourceLocator` belongs to Spring Cloud Context and has the core contract:

~~~java
public interface PropertySourceLocator {

    PropertySource<?> locate(Environment environment);
}
~~~

The locator receives the `Environment` of the application context being prepared. That Environment already contains standard Spring Boot property sources, so the locator can read information such as:

- `spring.application.name` to choose configuration per application.
- Active profiles to choose configuration per environment.
- Region, tenant, or label defined by the application.

The locator returns a `PropertySource<?>`, such as a `MapPropertySource` holding key/value pairs. Spring Cloud bootstrap processes locators, combines the discovered sources, and inserts them into the application's Environment.

~~~mermaid
flowchart TD
    A[Bootstrap prepares Environment] --> B[PropertySourceLocator]
    B --> C[Read application and profiles]
    C --> D[Controlled repository or external source]
    D --> E[PropertySource result]
    E --> F[Bootstrap combines located sources]
    F --> G[Insert into application Environment]
    G --> H[Application resolves properties]
~~~

Three responsibilities must stay separated:

| Component | Responsibility |
| --- | --- |
| `PropertySourceLocator` | Reads Environment, decides what data to fetch, and returns a PropertySource |
| Repository/client | Fetches data from files, databases, HTTP APIs, secret stores, or other sources |
| `PropertySource` | Exposes key/value pairs for Spring Environment lookups |

A good unit test can verify the locator without running a bootstrap context or starting external services.

## 3. Distinguishing Legacy Bootstrap from Modern Config Data

This is a critical boundary when choosing how to test.

### 3.1. PropertySourceLocator Belongs to Legacy Bootstrap

Spring Cloud Context allows adding locators into the bootstrap context through `BootstrapConfiguration` declared in `META-INF/spring.factories`. The bootstrap context is a parent context that prepares property sources before the main application context finishes initialization.

Example metadata:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.example.bootstrap.CustomPropertySourceLocator
~~~

To enable legacy bootstrap, applications typically add `spring-cloud-starter-bootstrap` or enable bootstrap via a system/environment property according to the version's documentation.

### 3.2. Config Data Is the Default Mechanism for Config Server

Spring Boot 2.4 introduced Config Data. Spring Cloud Config Client now uses this mechanism as its default connection path:

~~~properties
spring.config.import=optional:configserver:
~~~

With the Config Data flow, Spring Boot uses `ConfigDataLocationResolver` and `ConfigDataLoader` to load configuration. A test targeting this flow should test Config Data integration, for instance with a mock HTTP server returning Config Server responses. That is not a direct test of `PropertySourceLocator`.

### 3.3. Choose the Right Test for Each Extension Point

| Goal | Mechanism to test |
| --- | --- |
| Custom source loaded via bootstrap context | `PropertySourceLocator` |
| Config Server loaded via `spring.config.import` | Config Client's Config Data resolver/loader |
| Logic selecting app/profile and building key/value map | Unit test locator with `MockEnvironment` |
| Locator registered and properties appearing in application context | Bootstrap integration test |
| Config Server HTTP response parsed properly | Client/Config Data test with mock HTTP server |

Do not use a locator unit test to conclude that the Config Data loader works, and do not start a real Config Server just to test a locator returning a map.

## 4. Designing a Controlled Data Source

Suppose each application has its own profile-specific configuration set:

| Application | Profile | Property | Value |
| --- | --- | --- | --- |
| `orders-service` | `test` | `feature.checkout.enabled` | `true` |
| `orders-service` | `test` | `limits.pool-size` | `12` |
| `orders-service` | `production` | `feature.checkout.enabled` | `false` |
| `catalog-service` | `test` | `catalog.cache.enabled` | `true` |

Tests must return the right dataset based on Environment. We can create a small repository interface:

~~~java
import java.util.List;
import java.util.Map;

public interface ControlledConfigRepository {

    Map<String, Object> load(String application, List<String> profiles);
}
~~~

In production, the implementation may read a database or API. In unit tests, substitute a lambda or a fake repository backed by immutable maps.

### 4.1. In-Memory Fake Repository

~~~java
import java.util.List;
import java.util.Map;

public final class InMemoryConfigRepository
        implements ControlledConfigRepository {

    private final Map<String, Map<String, Object>> fixtures;

    public InMemoryConfigRepository(
            Map<String, Map<String, Object>> fixtures) {
        this.fixtures = Map.copyOf(fixtures);
    }

    @Override
    public Map<String, Object> load(
            String application, List<String> profiles) {

        String key = application + ":" + String.join(",", profiles);
        return fixtures.getOrDefault(key, Map.of());
    }
}
~~~

Fixtures use a well-structured key so tests never depend on wall-clock time, developer machine environment variables, or running services.

Example creating the repository:

~~~java
Map<String, Map<String, Object>> fixtures = Map.of(
        "orders-service:test",
        Map.of(
                "feature.checkout.enabled", true,
                "limits.pool-size", 12),
        "orders-service:production",
        Map.of("feature.checkout.enabled", false),
        "catalog-service:test",
        Map.of("catalog.cache.enabled", true));

ControlledConfigRepository repository =
        new InMemoryConfigRepository(fixtures);
~~~

If the locator supports multiple profiles, profile ordering conventions must be explicitly defined. For example, profiles are evaluated in Environment order and later profiles can override keys from earlier ones. Tests should document that convention with dedicated fixtures.

## 5. Writing a Testable Locator

The implementation below does only three things: read the application name, read active profiles, and ask the repository for a map. It does not create an HTTP client or open network connections inside `locate`.

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

public final class ControlledPropertySourceLocator
        implements PropertySourceLocator {

    private final ControlledConfigRepository repository;

    public ControlledPropertySourceLocator(
            ControlledConfigRepository repository) {
        this.repository = repository;
    }

    @Override
    public PropertySource<?> locate(Environment environment) {
        String application = environment.getProperty(
                "spring.application.name", "application");

        String[] activeProfiles = environment.getActiveProfiles();
        List<String> profiles = activeProfiles.length == 0
                ? List.of("default")
                : Arrays.asList(activeProfiles);

        Map<String, Object> values =
                repository.load(application, profiles);

        if (values == null || values.isEmpty()) {
            return null;
        }

        Map<String, Object> snapshot =
                Collections.unmodifiableMap(new LinkedHashMap<>(values));

        String sourceName = "controlled:"
                + application + ":" + String.join(",", profiles);

        return new MapPropertySource(sourceName, snapshot);
    }
}
~~~

Several deliberate design decisions are made here:

- The application name has a fallback so the locator can still handle environments without a declared application name.
- When no active profile exists, it uses a default profile agreed upon as `default` in this example.
- The map is copied before returning, preventing tests or repositories from mutating the backing map after the locator creates the property source.
- The property source name includes application/profile for easier log reading and diagnostics.
- When no data exists, it returns `null` so bootstrap skips that locator. If business logic must distinguish "no configuration" from "empty configuration," define an explicit contract and test both cases.

The fallback profile name in the example is a repository convention. In a real application, decide whether to use `Environment.getDefaultProfiles()` or a system-specific rule, then apply it consistently to both the locator and tests.

## 6. Unit Testing with MockEnvironment

`MockEnvironment` lets you create a controlled Environment without starting a Spring Boot application context. `TestPropertyValues` is a utility for adding key/value properties to an Environment in tests.

### 6.1. Verifying the Locator Selects the Right Application and Profile

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.core.env.PropertySource;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class ControlledPropertySourceLocatorTests {

    @Test
    void locatesPropertiesForApplicationAndProfile() {
        Map<String, Map<String, Object>> fixtures = Map.of(
                "orders-service:test",
                Map.of(
                        "feature.checkout.enabled", true,
                        "limits.pool-size", 12));

        ControlledConfigRepository repository =
                new InMemoryConfigRepository(fixtures);
        ControlledPropertySourceLocator locator =
                new ControlledPropertySourceLocator(repository);

        MockEnvironment environment = new MockEnvironment();
        TestPropertyValues.of(
                "spring.application.name=orders-service")
                .applyTo(environment);
        environment.setActiveProfiles("test");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source).isNotNull();
        assertThat(source.getName())
                .isEqualTo("controlled:orders-service:test");
        assertThat(source.getProperty("feature.checkout.enabled"))
                .isEqualTo(true);
        assertThat(source.getProperty("limits.pool-size"))
                .isEqualTo(12);
    }
}
~~~

This test verifies the locator's core contract: the application name and profile in Environment determine which fixture is returned. It does not need a Config Server or database running.

### 6.2. Verifying Two Applications Do Not Share Data

Place this test method in the same test class from Section 6.1. Each test builds its own fixture so it does not depend on another test's state.

~~~java
@Test
void returnsDifferentPropertiesForDifferentApplications() {
    Map<String, Map<String, Object>> fixtures = Map.of(
            "orders-service:test",
            Map.of("feature.enabled", true),
            "catalog-service:test",
            Map.of("feature.enabled", false));

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(
                    new InMemoryConfigRepository(fixtures));

    MockEnvironment ordersEnvironment = new MockEnvironment();
    ordersEnvironment.setProperty(
            "spring.application.name", "orders-service");
    ordersEnvironment.setActiveProfiles("test");

    MockEnvironment catalogEnvironment = new MockEnvironment();
    catalogEnvironment.setProperty(
            "spring.application.name", "catalog-service");
    catalogEnvironment.setActiveProfiles("test");

    PropertySource<?> orders = locator.locate(ordersEnvironment);
    PropertySource<?> catalog = locator.locate(catalogEnvironment);

    assertThat(orders.getProperty("feature.enabled")).isEqualTo(true);
    assertThat(catalog.getProperty("feature.enabled")).isEqualTo(false);
}
~~~

This test catches bugs where a cache key mistakenly uses only the profile or only the application. If the repository caches results, cache keys must include every factor that changes configuration, such as application, profile, tenant, and label.

### 6.3. Testing Different Profiles

This is also an independent method in the same test class:

~~~java
@Test
void loadsProfileSpecificValues() {
    Map<String, Map<String, Object>> fixtures = Map.of(
            "orders-service:test",
            Map.of("feature.checkout.enabled", true),
            "orders-service:production",
            Map.of("feature.checkout.enabled", false));

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(
                    new InMemoryConfigRepository(fixtures));

    MockEnvironment testEnvironment = new MockEnvironment();
    testEnvironment.setProperty(
            "spring.application.name", "orders-service");
    testEnvironment.setActiveProfiles("test");

    MockEnvironment productionEnvironment = new MockEnvironment();
    productionEnvironment.setProperty(
            "spring.application.name", "orders-service");
    productionEnvironment.setActiveProfiles("production");

    assertThat(locator.locate(testEnvironment)
            .getProperty("feature.checkout.enabled")).isEqualTo(true);
    assertThat(locator.locate(productionEnvironment)
            .getProperty("feature.checkout.enabled")).isEqualTo(false);
}
~~~

Never rely on the real profile of the test runner machine. Always set active profiles directly on `MockEnvironment` so tests are unaffected by environment variables or JVM flags.

## 7. Testing Missing Data and Source Failures

A locator must have deterministic behavior when the repository lacks configuration or throws an error. Do not let tests check only the happy path.

### 7.1. No Configuration for the Application

~~~java
@Test
void returnsNullWhenRepositoryHasNoMatchingConfiguration() {
    ControlledConfigRepository repository =
            (application, profiles) -> Map.of();

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment environment = new MockEnvironment();
    environment.setProperty(
            "spring.application.name", "unknown-service");
    environment.setActiveProfiles("test");

    assertThat(locator.locate(environment)).isNull();
}
~~~

If application policy dictates that missing configuration is a startup failure, the locator or repository should throw a meaningful exception. Do not silently return an empty map when missing configuration causes the application to run incorrectly or insecurely.

### 7.2. Data Source Failure

Place this method in the test class and keep the AssertJ static import at the top of the file:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void propagatesRepositoryFailure() {
    ControlledConfigRepository repository =
            (application, profiles) -> {
                throw new IllegalStateException("controlled repository failure");
            };

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment environment = new MockEnvironment();
    environment.setProperty(
            "spring.application.name", "orders-service");

    assertThatThrownBy(() -> locator.locate(environment))
            .isInstanceOf(IllegalStateException.class)
            .hasMessage("controlled repository failure");
}
~~~

If the production implementation translates errors into a custom exception, assert that application's exception type and error code. Checking only an overly generic exception can conflate timeouts, auth errors, and malformed data.

### 7.3. Distinguishing Missing Data from Empty Data

These two situations can carry different business meanings:

| Situation | Possible meaning | Recommended behavior |
| --- | --- | --- |
| Repository does not find application/profile | No configuration yet or wrong identifier | Return `null` if source is optional; throw error if mandatory |
| Repository finds configuration, map is empty | Empty configuration intentionally stored | Preserve empty result or dedicated representation per contract |
| Repository unreachable | Infrastructure or authentication error | Throw error with clear cause; do not fake empty data |

Tests must express the chosen policy. Otherwise, a shift from "repository unavailable" to "return empty map" could cause applications to boot with unintended defaults.

## 8. Testing PropertySource Contents and Precedence

`PropertySourceLocator` only returns a property source; the bootstrap process is responsible for inserting that source into Environment. When testing a locator independently, you can manually add property sources to verify Spring's lookup rules.

### 8.1. Earlier Property Source Has Higher Precedence

~~~java
import java.util.Map;

import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

@Test
void firstPropertySourceWinsWhenKeysOverlap() {
    MockEnvironment environment = new MockEnvironment();

    environment.getPropertySources().addLast(
            new MapPropertySource(
                    "local",
                    Map.of("feature.mode", "local")));

    environment.getPropertySources().addFirst(
            new MapPropertySource(
                    "controlled-remote",
                    Map.of("feature.mode", "remote")));

    assertThat(environment.getProperty("feature.mode"))
            .isEqualTo("remote");
}
~~~

`addFirst` places the property source at the front of the list, so overlapping keys are read from that source first. `addLast` puts the source at the end, used only when earlier sources do not provide the key.

This tests `MutablePropertySources` rules. It does not prove where legacy bootstrap actually inserts the source; to verify bootstrap ordering, run an integration test with the bootstrap context.

### 8.2. Checking Source Names and Overlapping Keys

Property source names should be stable and unique within the context. Spring manages sources by name; if multiple locators share the same name, one source can overwrite another or behave differently than the test author expects.

Verify:

- Does the source name include the required source namespace, application, or tenant?
- Can two independent locators produce colliding names?
- When two sources both provide a key, which source wins?
- When a source is removed from Environment, does the value fall back to the lower-priority source as expected?

Do not test ordering by comparing the entire property source list of a Spring Boot context unless the test truly requires that contract. System property sources can vary across versions and environments.

### 8.3. Multiple Locators and Ordering

The bootstrap process sorts locators by order before collecting property sources. If the application has multiple locators, use `@Order` or `Ordered` to declare intentional ordering, then write an integration test for overlapping keys between the two sources.

~~~java
import org.springframework.core.annotation.Order;

@Order(10)
public class TenantPropertySourceLocator
        implements PropertySourceLocator {
    // locate(...)
}
~~~

Do not rely on accidental component scan order or bean initialization order. When two sources can own the same key, ordering must be an explicit part of both design and tests.

## 9. Integration Testing with the Bootstrap Context

Unit tests calling `locate` directly do not verify that the locator is discovered in the bootstrap context. To test the full path, register a test-only configuration and verify the property appears in the application context's Environment.

### 9.1. Adding the Bootstrap Starter in Test Runtime

Maven example:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-bootstrap</artifactId>
    <scope>test</scope>
</dependency>
~~~

This dependency is only needed when the test intentionally exercises legacy bootstrap. Manage versions using the Spring Cloud BOM compatible with your project's Spring Boot version.

### 9.2. Registering Test Bootstrap Configuration

Create file:

~~~text
src/test/resources/META-INF/spring.factories
~~~

Contents:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.example.testbootstrap.TestPropertySourceLocatorConfiguration
~~~

Place the test bootstrap class in package `com.example.testbootstrap`, outside the application's component scan scope. For example, the main application might live in `com.example.application`. Spring Cloud documentation warns against letting bootstrap configurations be accidentally component-scanned into the main application context.

### 9.3. Locator Fixture for Integration Tests

~~~java
package com.example.testbootstrap;

import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

@Configuration(proxyBeanMethods = false)
public class TestPropertySourceLocatorConfiguration
        implements PropertySourceLocator {

    @Override
    public PropertySource<?> locate(Environment environment) {
        return new MapPropertySource(
                "test-controlled-source",
                Map.of(
                        "test.remote.feature", "enabled",
                        "test.remote.limit", 17));
    }
}
~~~

The fixture returns fixed data without making HTTP or database calls. In real tests, you can inject a fake repository into the locator if you need to test selection by application/profile.

### 9.4. Verifying Properties in the Application Context

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class PropertySourceLocatorBootstrapIntegrationTests {

    @Autowired
    private Environment environment;

    @Test
    void exposesLocatedPropertiesToApplicationEnvironment() {
        assertThat(environment.getProperty("test.remote.feature"))
                .isEqualTo("enabled");
        assertThat(environment.getProperty("test.remote.limit", Integer.class))
                .isEqualTo(17);
    }
}
~~~

This test exercises bootstrap discovery, creates the property source, and transfers values into the application Environment. If unit tests pass yet this integration test fails, check the bootstrap dependency, metadata file, package scanning, initialization order, and bootstrap enablement conditions.

## 10. Locators Can Be Invoked Multiple Times

Since Spring Cloud 2022.0.3, `PropertySourceLocators` can be invoked twice:

1. First to fetch configuration without active profiles attached. That configuration may activate additional profiles via `spring.profiles.active`.
2. After the main application context starts, the locator is invoked again with active profiles to fetch profile-specific configuration.

Therefore:

- Unit tests calling `locate(environment)` directly inspect only one Environment state at a time.
- Integration tests must not assume the locator runs only once.
- Do not use static counters or non-idempotent side effects to determine data.
- Do not create single-use resources on the first call if subsequent calls need them again.
- If caching is used, cache keys must include profiles and every other factor affecting the output.

### 10.1. Testing Each Profile Phase Separately

You can simulate both states using two `MockEnvironment` instances:

~~~java
@Test
void supportsDefaultAndProfileSpecificLookups() {
    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment initialEnvironment = new MockEnvironment();
    initialEnvironment.setProperty(
            "spring.application.name", "orders-service");

    MockEnvironment profileEnvironment = new MockEnvironment();
    profileEnvironment.setProperty(
            "spring.application.name", "orders-service");
    profileEnvironment.setActiveProfiles("production");

    PropertySource<?> initial =
            locator.locate(initialEnvironment);
    PropertySource<?> production =
            locator.locate(profileEnvironment);

    assertThat(initial.getProperty("feature.checkout.enabled"))
            .isEqualTo(true);
    assertThat(production.getProperty("feature.checkout.enabled"))
            .isEqualTo(false);
}
~~~

This example assumes the repository has fixtures for both the default profile and `production`. In integration tests, assert the final value in Environment and avoid locking tests to internal call counts.

## 11. Testing Immutability and Avoiding State Leakage

A property source can outlive the locator call. If the backing map is mutated after being returned, values read by the application may change unexpectedly.

### 11.1. Verifying Snapshots Do Not Change with the Original Map

~~~java
@Test
void returnedPropertySourceUsesASnapshotOfRepositoryData() {
    Map<String, Object> sourceData = new LinkedHashMap<>();
    sourceData.put("feature.mode", "initial");

    ControlledConfigRepository repository =
            (application, profiles) -> sourceData;

    ControlledPropertySourceLocator locator =
            new ControlledPropertySourceLocator(repository);

    MockEnvironment environment = new MockEnvironment();
    PropertySource<?> source = locator.locate(environment);

    sourceData.put("feature.mode", "changed");

    assertThat(source.getProperty("feature.mode"))
            .isEqualTo("initial");
}
~~~

This test passes only if the locator copies data before constructing `MapPropertySource`, as shown in the Section 5 implementation.

### 11.2. Avoiding Static Mutable Fixtures

Never share a mutable map across tests. If test A modifies the fixture and test B runs afterward, results depend on test order or parallel execution.

Prefer:

- Creating a fresh fake repository inside each test.
- Using `Map.of(...)` for immutable fixtures.
- Never storing active profiles or application names in static fields.
- Never using a mutable stateful singleton fake repository across tests.
- If using Mockito, resetting or creating fresh mocks per test.

### 11.3. Do Not Hold Closed Resources in a PropertySource

A `PropertySource` may still be accessed after the bootstrap context completes. Do not let a `PropertySource` depend on an HTTP client or database connection that the locator closes as soon as bootstrap finishes. If a property source must query dynamic data, manage the client lifecycle appropriately or store a snapshot of fetched data in an immutable source.

## 12. Testing Repositories/Clients Without Real Services

If the repository calls HTTP or a database, split tests into layers:

| Test layer | Target | Suitable tools |
| --- | --- | --- |
| Locator unit test | App/profile selection and PropertySource creation | `MockEnvironment`, fake repository |
| Repository adapter unit test | Response parsing, key/value mapping, error handling | Mock HTTP client, stub DAO |
| Adapter integration test | Real in-process HTTP request/response | MockWebServer or mock HTTP server |
| Bootstrap integration | Locator discovery and properties entering Environment | `spring-cloud-starter-bootstrap` in test scope |

Never let locator unit tests call a real Config Server or database. Those dependencies make tests slow, hard to reproduce, and prone to environment failures.

### 12.1. Testing the HTTP Adapter

If the repository uses HTTP, test the adapter separately against a mock server:

- Return responses with deterministic key/value pairs.
- Return HTTP 404 when application/profile does not exist.
- Return HTTP 401/403 when credentials are invalid.
- Return HTTP 500 or timeouts to verify infrastructure failures.
- Return malformed payloads to verify parsing errors.

Then use a fake adapter inside the locator unit test. That way, locator tests do not need to know HTTP status codes or external service JSON schemas.

### 12.2. Handling Sensitive Data in Tests

If the locator reads secrets, tests must use fake values only. Never put real credentials into fixtures, assertion messages, or logs. Never print an entire `PropertySource` to the console, as it may contain passwords, tokens, or keys.

## 13. What to Verify in the Test Suite

| Category | Test cases |
| --- | --- |
| Data routing | Correct application name, profile, tenant, or label |
| Data types | Boolean, number, list, or string types preserved properly |
| Empty data | Missing source and empty source handled per contract |
| Errors | Timeouts, authentication, parse errors, and repository exceptions |
| Property source | Stable source name, accurate keys/values, immutable snapshot |
| Precedence | Overlapping keys resolved in expected order |
| Profiles | Default profile and each active profile return matching config |
| Bootstrap | Locator registered via test metadata and properties appear in Environment |
| Multiple locators | Explicit locator ordering; overlapping keys yield deterministic results |
| Repeated invocations | No reliance on fixed call count and no duplicate side effects |
| Isolation | Tests run independently and in parallel without mutating each other's fixtures |

## 14. Troubleshooting

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Unit test cannot find property | Locator returned `null`, wrong fixture key, or profile mismatch | Check application name, active profiles, and repository keys |
| Property source is right but Environment returns another value | Another property source has higher precedence | Print relevant source names and order in test |
| Integration test does not see bootstrap source | Missing bootstrap starter or wrong metadata | Check test runtime dependencies and `BootstrapConfiguration` key |
| Locator runs twice | Spring Cloud 2022.0.3+ supports pre- and post-profile-activation fetches | Do not assert call count; assert final result |
| Test passes alone but fails in full suite | Mutable fixture or context cache sharing state | Create fresh fakes per test and remove static mutable data |
| Production profile data appears in test | Test inherited profile from JVM/CI | Set active profiles explicitly on `MockEnvironment` |
| Remote value does not override local value | Property source inserted at wrong position or override policy differs | Check bootstrap ordering and override policy |
| Config Server import does not invoke locator | App uses Config Data instead of legacy bootstrap | Test Config Data resolver/loader and `spring.config.import` |
| PropertySource errors after bootstrap | Client/resource already closed while source still reused | Return data snapshot or manage resource lifecycle properly |

### 14.1. Diagnostic Workflow

1. Call the locator directly with a `MockEnvironment` having a known application name and profile.
2. Check whether the returned `PropertySource` is `null`.
3. Check the source name and its key/value entries.
4. Add the source into `MockEnvironment` to verify precedence.
5. If unit tests pass, check bootstrap metadata and test dependencies.
6. Verify whether the application uses legacy bootstrap or Config Data.
7. Inspect bootstrap logs, active profiles, and property source ordering.
8. Re-run the test in isolation to detect shared fixtures or caches.

## 15. Practice Exercises

### Exercise 1 — Locator with Deterministic Fixtures

Write a fake repository holding configuration for two applications and two profiles. Write a locator that selects the right fixture based on Environment.

### Exercise 2 — Unit Testing with MockEnvironment

Write tests for application name, active profile, property source name, and two values with Boolean/Integer types. Add a missing-data test.

### Exercise 3 — Testing Precedence

Create a local property source and a locator property source both containing key `feature.mode`. Insert them in two different orders and verify the value returned by Environment.

### Exercise 4 — Bootstrap Integration

Register a test bootstrap configuration in `src/test/resources/META-INF/spring.factories`. Include `spring-cloud-starter-bootstrap` in test runtime and verify the properties appear in the application Environment.

### Exercise 5 — Two-Phase Profile Activation

Create default and `production` fixtures. Test the locator against an Environment with no active profiles and an Environment with the `production` profile. The integration test should assert only the final value without assuming how many times the locator was called.

### Exercise 6 — Distinguishing Config Data

Write notes or a separate test describing how to test `spring.config.import=optional:configserver:`. Identify which parts belong to the Config Data resolver/loader and which parts belong to legacy `PropertySourceLocator`.

**Completion criteria:** you can test a locator with fully controlled data, verify application/profile selection and precedence, handle empty/error data, and prove the bootstrap context loads the expected property source.

## 16. Summary

`PropertySourceLocator` is a legacy bootstrap extension point: it accepts an `Environment` and returns a `PropertySource<?>`. A simple and reliable way to test it is to create a `MockEnvironment`, set the application name and active profiles, and use an in-memory fake repository returning fixed maps. Unit tests verify data selection, source names, key/value pairs, empty cases, and errors without calling external services.

To test precedence, verify how `MutablePropertySources` resolves overlapping keys and then run a bootstrap integration test to verify the actual source inserted into Environment. Register legacy locators via `BootstrapConfiguration` in `spring.factories`; the test runtime must enable bootstrap. Since Spring Cloud 2022.0.3, locators can be called before and after profiles are activated, so tests must focus on configuration outcomes rather than a fixed invocation count.

Spring Cloud Config now uses Config Data via `spring.config.import` as its default mechanism. When an application uses that flow, test the Config Data resolver/loader. Test `PropertySourceLocator` only when the application genuinely uses legacy bootstrap extensions or registers a custom locator in the bootstrap context.

## References

- [Spring Cloud Commons 5.0.4 — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): bootstrap context, custom `PropertySourceLocator`, registration via `spring.factories`, precedence, and double invocation starting in Spring Cloud 2022.0.3.
- [Spring Cloud Config 5.0.6 — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data via `spring.config.import` and enabling legacy config-first bootstrap.
- [Spring Boot 4.1.2 — Test Utilities](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html): `MockEnvironment` and `TestPropertyValues` for controlling properties in tests.
- [PropertySourceBootstrapConfiguration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/main/java/org/springframework/cloud/bootstrap/config/PropertySourceBootstrapConfiguration.java): how bootstrap collects locators, orders them, and inserts property sources.
- [ContextRefresherTests source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-context/src/test/java/org/springframework/cloud/context/refresh/ContextRefresherTests.java): Spring Cloud test example using `PropertySourceLocator` and map data.

Always verify your project's Spring Cloud release train and Spring Boot BOM. Legacy bootstrap, Config Data, and test APIs can vary across release generations.

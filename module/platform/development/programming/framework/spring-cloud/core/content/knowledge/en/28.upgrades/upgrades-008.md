# Regression Testing Configuration Source Order and Management Endpoints

When upgrading Spring Boot or Spring Cloud, an application may still start up normally while reading a configuration value from a different source than before. A property can shift precedence among internal files, environment variables, Config Server, Config Data imports, legacy bootstrap, or test property sources. Management endpoints can also change their enablement conditions, paths, access permissions, sanitization rules, or response structures.

Therefore, post-upgrade regression testing needs to verify two contracts: **which value actually wins when multiple sources declare the same key**, and **which management endpoints remain exposed, readable, or capable of mutating configuration with proper authorization**. It is not enough to check only whether the application starts.

This lesson belongs to the **Upgrades** chapter of the **SPRING_CLOUD_CORE** module. We will build a test suite covering Spring `Environment`, Config Data, legacy bootstrap, remote property sources, `@ConfigurationProperties`, Actuator `env`/`configprops`/`refresh`, and Spring Cloud Commons `serviceregistry`; then organize a version matrix and CI checklist to detect behavioral changes before release.

## 1. Learning Objectives

After this lesson, you can:

- Build a configuration source matrix and the precedence order to preserve after upgrading.
- Verify effective values using `Environment` and `MutablePropertySources`.
- Distinguish Spring Boot's source ordering from remote property source ordering managed by Spring Cloud Config.
- Test Config Data via `spring.config.import` and legacy bootstrap separately.
- Use `MockEnvironment`, `TestPropertyValues`, and `ApplicationContextRunner` for unit/context tests.
- Use integration tests to verify `@ConfigurationProperties` receives the right values.
- Test the `env`, `configprops`, `refresh`, and `serviceregistry` endpoints.
- Verify endpoint exposure, management base path, authentication, authorization, and sanitization.
- Distinguish configuration errors, endpoint contract errors, and errors caused by test property overrides.
- Organize testing across supported Spring Boot/Spring Cloud pairs.
- Create a regression baseline that can be compared before and after upgrading.

## 2. Why Test Configuration Source Order?

A key can appear in multiple sources. For example, `checkout.max-items` might be declared in the default file, the `production` profile file, environment variables, and Config Server.

If source ordering changes, the application can run with a different value without any startup error:

| Source | Example value | Purpose |
| --- | --- | --- |
| `application.yml` | `20` | Default value |
| `application-production.yml` | `30` | Profile value |
| OS environment | `40` | Deployment environment override |
| Config Server | `50` | Remote configuration |
| Command line | `60` | Runtime override |

The final outcome depends on how sources are added to `Environment`, how Config Data imports are processed, and Spring Cloud Config's override policy. Reading configuration files alone is not enough to know the runtime value.

### 2.1. Three Concepts to Keep Separate

| Concept | Question | How to test |
| --- | --- | --- |
| Source precedence | Which source wins when keys collide? | `Environment.getProperty()` and `PropertySources` ordering |
| Binding | Is the effective value bound to the bean with the right type? | `@ConfigurationProperties` and `Binder` |
| Management contract | Can operators observe or modify properties via endpoints? | HTTP integration tests, security tests, and Actuator |

A test that only checks `Environment.getProperty()` does not prove the bean rebound. A test that only calls `/actuator/env` likewise does not prove `@ConfigurationProperties` is using the right value.

## 3. Spring Boot Source Ordering

Spring Boot uses an ordered list of `PropertySource` instances. Sources appearing earlier have higher precedence when the resolver looks up a key; the higher-precedence source decides the value when the same key appears in multiple places.

In current Spring Boot documentation, the main source groups are ordered from lowest to highest precedence as follows:

1. Default properties supplied via `SpringApplication.setDefaultProperties(...)`.
2. `@PropertySource` annotations on configuration classes.
3. Config Data such as `application.properties`, `application.yml`, and profile files.
4. `RandomValuePropertySource`.
5. OS environment variables.
6. Java system properties.
7. JNDI and servlet context/config parameters in applicable web applications.
8. `SPRING_APPLICATION_JSON`.
9. Command-line arguments.
10. Test properties added by Spring Boot/Spring Test, including test-specific mechanisms.

Test-specific property sources have their own ordering; `@DynamicPropertySource` has higher precedence than `@TestPropertySource`. Inline values on `@TestPropertySource` take precedence over values read from resource locations on that same annotation.

The list above is Spring Boot's general model. When upgrading, consult the documentation for your target version because ordering and source types can change by framework generation or application type.

### 3.1. Config Data Has Internal Ordering

Within the Config Data group, verify:

- Default files on the classpath.
- Profile-specific files such as `application-production.yml`.
- Files outside the JAR and profile-specific files outside the JAR.
- Locations specified via `spring.config.location`.
- Additional locations via `spring.config.additional-location`.
- Imports from `spring.config.import`.
- Profile ordering when multiple profiles are active simultaneously.

Profile-specific files can override non-profile files. When multiple profiles are active, profiles processed later can override earlier profiles. Location ordering and location groups also affect the result.

### 3.2. spring.config.import Affects Precedence

Imports are processed when Config Data is loaded. Imported contents are placed immediately below the document declaring the import in property source order; consequently, imported values can override values in the document that declared them. Multiple imports are processed in declaration order, and later imports can have higher precedence.

Example:

~~~yaml
spring:
  config:
    import:
      - optional:file:./region.yml
      - optional:file:./service.yml

checkout:
  max-items: 20
~~~

If both `region.yml` and `service.yml` declare `checkout.max-items`, tests must verify the value from the later import according to the actual order used by the application. Do not infer precedence solely from line positions inside a file.

### 3.3. spring.config.location and additional-location Are Not the Same

`spring.config.location` replaces the default Config Data locations. `spring.config.additional-location` appends new locations to the default list; values in additional locations can override values loaded earlier.

When upgrading, test both if the application uses them. Accidentally switching from `additional-location` to `location` can drop configuration packaged inside the JAR.

## 4. Remote Property Sources in Spring Cloud Config

Do not lump remote configuration ordering into a single rule. Spring Cloud Config supports two common loading mechanisms:

| Mechanism | How to enable | Characteristics |
| --- | --- | --- |
| Config Data | `spring.config.import=configserver:` | Modern default mechanism; uses Config Data resolver/loader |
| Legacy bootstrap | `spring-cloud-starter-bootstrap` or `spring.cloud.bootstrap.enabled=true` | Creates bootstrap context and adds remote sources via bootstrap lifecycle |

Do not enable both mechanisms for the same application without an explicit design. Config Client documentation defines Config Data import as the default; legacy bootstrap must be enabled explicitly.

### 4.1. Testing Config Data Import

Configuration example:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: configserver:http://localhost:8888
  cloud:
    config:
      label: release-2026
~~~

In tests, run an embedded mock Config Server or WireMock/MockWebServer returning a response with deterministic property sources. Do not call a production Config Server in regression tests.

Tests should verify:

- The client sends the right application name.
- Profile and label are sent properly.
- The Config Data resolver is invoked during startup.
- Remote property sources appear in `Environment`.
- Remote and local values obey expected precedence.
- When the server is unavailable, `optional:` and fail-fast produce different outcomes as designed.
- When remote config activates a profile, the client loads the corresponding profile configuration.

### 4.2. Testing Legacy Bootstrap

If the application still uses legacy bootstrap, tests must enable bootstrap via the test runtime dependency or corresponding system property. Register a custom `PropertySourceLocator` in test `META-INF/spring.factories` if you need to verify bootstrap extensions.

Test separately:

- Whether the bootstrap context is created.
- Whether remote sources appear in the main application `Environment`.
- Which application name/profile `PropertySourceLocator` receives.
- Whether `spring.cloud.config.allowOverride`, `overrideNone`, and `overrideSystemProperties` take effect according to metadata from the remote source.
- Whether refresh/bootstrap lifecycles still behave properly after upgrading.

Do not use Config Data tests to conclude legacy bootstrap works, or vice versa. The two paths have different lifecycles and mechanisms for adding property sources.

### 4.3. Remote Override Flags

With bootstrap remote property sources, override flags must be tested from the proper source:

| Property | Meaning |
| --- | --- |
| `spring.cloud.config.allowOverride` | Whether the remote source allows local sources to override it |
| `spring.cloud.config.overrideNone` | Allows all local sources to override remote sources |
| `spring.cloud.config.overrideSystemProperties` | Controls precedence relative to system properties, command line, and environment |

`allowOverride` must be supplied by the remote property source; setting this flag only in local application config does not grant override authority from the server.

Example matrix to test:

| `allowOverride` | `overrideNone` | `overrideSystemProperties` | What to verify |
| --- | --- | --- | --- |
| `false` | — | — | Local sources do not override remote sources |
| `true` | `true` | — | Local sources take precedence over remote |
| `true` | `false` | `false` | System properties, command line, and environment can override; local config files cannot |
| `true` | `false` | `true` | Default remote override policy behavior; must be verified via integration tests |

Do not assert only the final value. Record the winning source so that if a release train changes property source ordering, the upgrade team can pinpoint the cause.

## 5. Designing a Regression Matrix

A solid test suite should cover sources, profiles, binding, and endpoints. The table below suggests a matrix:

| Group | Scenario | Expected outcome to preserve |
| --- | --- | --- |
| Config Data | Classpath default + profile | Profile overrides default |
| External files | Classpath + file outside JAR | External file wins when loaded later |
| Import | Two imports declaring the same key | Higher-priority import wins |
| OS environment | File + environment variable | Environment variable wins per Boot precedence |
| System property | Environment + `-D` | System property wins over environment |
| Command line | File + command line | Command line wins |
| Test override | Application config + test properties | Test override wins per test framework |
| Dynamic property | Testcontainers URL + test properties | Dynamic property beats `@TestPropertySource` |
| Config Server | Remote + local config | Matches remote override policy |
| Profile | Default + multiple active profiles | Values match profile order |
| Binding | `Environment` + `@ConfigurationProperties` | Bean receives right value and type |
| Actuator env | `GET /actuator/env` | Correct keys, sources, and sanitization |
| Actuator configprops | `GET /actuator/configprops` | Bound bean properties present |
| Refresh | `POST /actuator/refresh` | `Environment`/refresh-scoped beans update as designed |
| Env mutation | `POST /actuator/env` | Only allowed keys change; beans rebind properly |
| Service registry | `GET`/`POST /actuator/serviceregistry` | Status returned and updated per provider |
| Security | Missing permission/CSRF token | Management request is rejected |

### 5.1. Selecting Test Keys

Do not use only a simple key like `demo.value`. Choose keys representing the data types and behaviors the application actually uses:

- String: service name or endpoint URL.
- Integer/Duration: timeout, retry count, pool size.
- Boolean: feature flag.
- Enum: processing mode.
- List: list of origins or endpoints.
- Map: per-tenant/region configuration.
- Nested object: configuration bound to `@ConfigurationProperties`.

For lists, verify whole-list replacement semantics when a higher-priority source declares another list. For maps, distinct keys can merge while identical keys take the value from the higher-priority source.

## 6. Unit Testing PropertySource Order

For unit tests, use `MockEnvironment` and add clearly named `MapPropertySource` instances. This tests both the effective value and the winning source.

### 6.1. Testing addFirst and addLast

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PropertySourcePrecedenceTests {

    @Test
    void firstPropertySourceWinsWhenKeysOverlap() {
        MockEnvironment environment = new MockEnvironment();
        MutablePropertySources sources = environment.getPropertySources();

        sources.addLast(new MapPropertySource(
                "application-config",
                Map.of("checkout.max-items", "20")));
        sources.addLast(new MapPropertySource(
                "remote-config",
                Map.of("checkout.max-items", "50")));
        sources.addFirst(new MapPropertySource(
                "command-line",
                Map.of("checkout.max-items", "60")));

        assertThat(environment.getProperty("checkout.max-items"))
                .isEqualTo("60");
        assertThat(sources.iterator().next().getName())
                .isEqualTo("command-line");
    }

    @Test
    void removingHighestPrioritySourceRevealsNextValue() {
        MockEnvironment environment = new MockEnvironment();
        MutablePropertySources sources = environment.getPropertySources();

        sources.addFirst(new MapPropertySource(
                "remote-config",
                Map.of("checkout.max-items", "50")));
        sources.addLast(new MapPropertySource(
                "application-config",
                Map.of("checkout.max-items", "20")));

        assertThat(environment.getProperty("checkout.max-items"))
                .isEqualTo("50");

        sources.remove("remote-config");

        assertThat(environment.getProperty("checkout.max-items"))
                .isEqualTo("20");
    }
}
~~~

This test does not depend on Config Server, a web server, or bootstrap. It verifies Spring `Environment`'s contract: the first property source containing a key supplies the effective value.

### 6.2. Using TestPropertyValues for Fixtures

`TestPropertyValues` helps add multiple key/value pairs to an environment:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class TestPropertyValuesTests {

    @Test
    void appliesControlledPropertiesToEnvironment() {
        MockEnvironment environment = new MockEnvironment();

        TestPropertyValues.of(
                "spring.application.name=orders-service",
                "spring.profiles.active=staging",
                "checkout.max-items=25",
                "checkout.enabled=true")
                .applyTo(environment);

        assertThat(environment.getProperty("spring.application.name"))
                .isEqualTo("orders-service");
        assertThat(environment.getProperty("spring.profiles.active"))
                .isEqualTo("staging");
        assertThat(environment.getProperty("checkout.max-items", Integer.class))
                .isEqualTo(25);
    }
}
~~~

`TestPropertyValues` suits short fixtures. If a test verifies ordering across multiple sources, add sources explicitly with `MutablePropertySources.addFirst/addLast` to avoid depending on how the helper positions sources.

### 6.3. Testing Test Property Sources

In integration tests, you can use:

- `@SpringBootTest(properties = ...)` to pass properties into the test application.
- `@TestPropertySource` to load files or inline properties.
- `@DynamicPropertySource` to register dynamically generated URLs/ports, typically from Testcontainers.

Dynamic properties have higher precedence than `@TestPropertySource`. Inline properties in `@TestPropertySource` have higher precedence than files declared in `locations`. When two sources declare the same key, tests must assert the winning value in this exact order.

Example:

~~~java
@SpringBootTest
@TestPropertySource(properties = "checkout.max-items=30")
class CheckoutConfigurationTests {

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("checkout.max-items", () -> "40");
    }

    @Autowired
    Environment environment;

    @Test
    void dynamicPropertyOverridesTestPropertySource() {
        assertThat(environment.getProperty("checkout.max-items", Integer.class))
                .isEqualTo(40);
    }
}
~~~

The example above requires the corresponding JUnit, Spring Test, `Environment`, `@Autowired`, and AssertJ imports. Do not use `@DynamicPropertySource` to mock static properties; use it only when values depend on resources with lifecycles external to the context.

## 7. Testing Binding with ApplicationContextRunner

`ApplicationContextRunner` lets you launch a lightweight application context with controlled configuration and properties. It is well-suited for testing auto-configuration, conditional beans, and binding without running the full application.

### 7.1. Creating Configuration Properties

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private int maxItems;
    private boolean enabled;
    private Duration requestTimeout = Duration.ofSeconds(2);

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

### 7.2. Verifying Bound Values

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CheckoutPropertiesBindingTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsEffectiveValuesWithExpectedTypes() {
        contextRunner
                .withPropertyValues(
                        "checkout.max-items=45",
                        "checkout.enabled=true",
                        "checkout.request-timeout=1500ms")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutProperties properties =
                            context.getBean(CheckoutProperties.class);

                    assertThat(properties.getMaxItems()).isEqualTo(45);
                    assertThat(properties.isEnabled()).isTrue();
                    assertThat(properties.getRequestTimeout())
                            .isEqualTo(Duration.ofMillis(1500));
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CheckoutProperties.class)
    static class TestConfiguration {
    }
}
~~~

This test confirms the binder converts strings to integer, boolean, and duration. When upgrading Spring Boot, keep tests for any converters or custom `@ConfigurationPropertiesBinding` beans your application uses.

### 7.3. Testing Conditional Bean Activation

If an auto-configuration or component depends on a property, add tests for both branches:

- Property omitted: verify default and `matchIfMissing`.
- Property explicitly enabled/disabled: verify the bean appears or disappears.

Do not merely assert that the bean exists. Check which property source won so a test property does not accidentally mask runtime configuration.

## 8. Integration Testing Config Data and Remote Sources

Property source unit tests do not exercise the Config Data resolver/loader. Add integration tests that start Spring Boot with a mock Config Server.

### 8.1. Using ConfigDataApplicationContextInitializer for Config Data Files

If you only need to verify that `application.properties` loads into `Environment`, you can use `ConfigDataApplicationContextInitializer`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigDataInitializerTests {

    @Test
    void loadsConfigDataIntoEnvironment() {
        new ApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(TestConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getEnvironment()
                            .getProperty("checkout.max-items"))
                            .isEqualTo("25");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {
    }
}
~~~

Place the `application.properties` fixture on the test classpath or configure a dedicated location for the runner. `ConfigDataApplicationContextInitializer` only loads Config Data into `Environment`; if `@Value` placeholder processing is needed, use `@SpringBootTest` or configure `PropertySourcesPlaceholderConfigurer` appropriately.

### 8.2. Testing Config Server over Mock HTTP

A thorough integration test can:

1. Start WireMock or MockWebServer on a random port.
2. Return a Config Server response for a specific application/profile/label.
3. Supply the server URL in `spring.config.import` via dynamic properties.
4. Start the application with a specific test profile.
5. Assert `Environment.getProperty()` and `@ConfigurationProperties` beans.
6. Inspect the requests sent by Config Client to the server.

Cases to include:

| Case | Mock response | Assertion |
| --- | --- | --- |
| Config available | HTTP 200, valid property sources | Remote keys appear |
| Optional server unavailable | Connection refused or timeout | App continues startup when import is optional |
| Required server unavailable | Connection refused or timeout | Startup fails |
| Unauthorized | HTTP 401 | App fails or tries another URL per configuration |
| Profile activation | Default response activates a profile | Additional profile request/response occurs |
| Label changed | Returns configuration for the label | Value matching that label is selected |
| Remote/local collision | Both sources declare the same key | Winning value matches committed precedence |

Do not assert an exact request count if the Config Data resolver can query the server multiple times to resolve active profiles. Assert request contents and final results instead of assuming a single fetch.

## 9. Testing Management Endpoint Contracts

Management endpoints are operational APIs. After upgrading, confirm endpoints remain enabled, properly mapped, return accurate data, and permit configuration mutations only for authorized callers.

### 9.1. Distinguishing Endpoint Access from Exposure

An Actuator endpoint is reachable only when the endpoint is permitted to operate and exposed over HTTP or JMX. Check both settings separately:

- `management.endpoints.web.exposure.include/exclude`: which endpoints are mapped over HTTP.
- `management.endpoint.<id>.access`: whether the endpoint is accessible under the access policy (depending on Spring Boot version).

Example test profile:

~~~yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
          - env
          - configprops
          - refresh
          - serviceregistry
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Use this exposure configuration only in tests or on a protected management network. Do not expose `env`, `configprops`, `refresh`, or `serviceregistry` publicly just to make tests pass.

### 9.2. Endpoint Matrix

| Endpoint | Method | Key condition | Regression assertion |
| --- | --- | --- | --- |
| `/actuator/env` | `GET` | Actuator `env` exposed | Expected keys/sources present; sensitive values masked |
| `/actuator/env` | `POST` | Spring Cloud Context env POST enabled and key in allowlist | Allowed keys update; keys outside allowlist rejected |
| `/actuator/configprops` | `GET` | Actuator `configprops` exposed | Expected prefixes and bound beans present; secrets masked |
| `/actuator/refresh` | `POST` | Spring Cloud Context refresh endpoint exposed | `Environment` refreshed and refresh-scoped beans invalidated |
| `/actuator/serviceregistry` | `GET` | `Registration` bean exists and endpoint exposed | Returns registration status |
| `/actuator/serviceregistry` | `POST` | `Registration` bean exists and provider-supported status given | Registry receives new status |

Not every application needs every endpoint. A regression suite should test only the endpoints belonging to the application's operational contract.

### 9.3. Testing GET env and configprops

Example using `MockMvc`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,env,configprops",
        "management.endpoint.env.show-values=never",
        "management.endpoint.configprops.show-values=never",
        "checkout.max-items=45",
        "checkout.api-token=synthetic-secret"
})
@AutoConfigureMockMvc
class ConfigurationActuatorReadTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void envEndpointExposesKeyMetadataButMasksSecret() throws Exception {
        mockMvc.perform(get("/actuator/env"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("checkout.max-items")))
                .andExpect(content().string(
                        containsString("checkout.api-token")))
                .andExpect(content().string(
                        containsString("******")));
    }

    @Test
    void configpropsEndpointShowsBoundConfigurationAndMasksSecret()
            throws Exception {
        mockMvc.perform(get("/actuator/configprops"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("checkout")))
                .andExpect(content().string(
                        containsString("******")));
    }
}
~~~

These string assertions avoid locking tests to Actuator's entire JSON layout. For applications with strict JSON contracts, use JSONPath on stable fields the application actually depends on. Do not snapshot the entire response because metadata structures can expand across versions.

If endpoints are mapped under a different management base path or separate management port, tests must target the real URL/port. `MockMvc` fits when management endpoints run inside the mocked web application context; use `RANDOM_PORT` and a real HTTP client when testing a separate management server.

For `/actuator/configprops` to include `checkout` data, the test application context must register the `CheckoutProperties` bean via `@EnableConfigurationProperties` or component scanning just like the real application.

### 9.4. Testing POST env

Spring Cloud Context supports `POST` to `/actuator/env` to update properties, rebind `@ConfigurationProperties`, and alter log levels. The endpoint must be enabled explicitly and keys restricted with a regex.

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: "^(checkout\\.(enabled|max-items))$"
~~~

Tests must verify:

- `POST` with `checkout.enabled` or `checkout.max-items` is accepted.
- `POST` with a key like `spring.datasource.password` is rejected.
- `@ConfigurationProperties` beans receive the new value via rebinding.
- Invalid keys do not mutate `Environment`.
- Requests lacking management privileges are rejected.

Request example:

~~~http
POST /actuator/env
Content-Type: application/json

{
  "name": "checkout.max-items",
  "value": "55"
}
~~~

Do not enable `POST env` in production without a concrete operational use case, key allowlist, and proper authorization. When tests only need `GET`, leave `POST` disabled.

### 9.5. Testing POST refresh

Spring Cloud Context provides `/actuator/refresh` to refresh `Environment`/bootstrap property sources and invalidate `@RefreshScope` beans. This endpoint differs from `POST /actuator/env`: one updates a directly submitted property, while the other triggers the application's configuration refresh mechanism.

Regression tests should:

1. Start the application with initial properties.
2. Have the mock config source return updated values.
3. Call `POST /actuator/refresh`.
4. Assert changed keys if the version's response contract includes them.
5. Read `Environment` and `@ConfigurationProperties` beans.
6. Access `@RefreshScope` beans and verify the new target uses the updated values.

Do not assume the `refresh` endpoint always exists in every application. It depends on Spring Cloud Context and exposure. If an application migrates from legacy bootstrap to Config Data, verify refresh behavior with integration tests against the exact active mechanism.

### 9.6. Testing the Service Registry Endpoint

Spring Cloud Commons provides `/actuator/serviceregistry`. `GET` returns registration status; `POST` updates the status of the current registration. The endpoint requires a `Registration` bean and statuses supported by the provider.

Test example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties =
        "management.endpoints.web.exposure.include=health,serviceregistry")
@AutoConfigureMockMvc
class ServiceRegistryEndpointTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void registryStatusCanBeReadAndUpdated() throws Exception {
        mockMvc.perform(get("/actuator/serviceregistry"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("UP")));

        mockMvc.perform(post("/actuator/serviceregistry")
                        .contentType("application/json")
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/actuator/serviceregistry"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("OUT_OF_SERVICE")));
    }
}
~~~

The example above assumes the test context configured a registration starting in `UP` status and a registry provider supporting `OUT_OF_SERVICE`, such as Eureka. For Consul, Zookeeper, or custom registries, use the statuses and semantics provided by that implementation. To test logic independently of a provider, inject a fake `ServiceRegistry` and assert `setStatus` is invoked with the corresponding registration.

## 10. Testing Security and Sanitization

Management endpoints can expose sensitive details or alter runtime behavior. Therefore, endpoint tests must cover both positive and negative authorization.

### 10.1. Security Matrix

| Caller | `GET env/configprops` | `POST env/refresh` | `POST serviceregistry` |
| --- | --- | --- | --- |
| Unauthenticated | Per policy: typically denied when security is enabled | Denied | Denied |
| Read-only operator | Can read sanitized metadata | Denied | Denied |
| Config operator | Can read | Allowed only with config-mutation permission | Allowed only with registry-mutation permission |
| Application identity | Only endpoints needed for health/monitoring | No mutation privilege by default | No mutation privilege by default |

Actual permissions are governed by Spring Security and the application's Actuator configuration. Tests must verify real roles/authorities rather than only checking HTTP 200.

### 10.2. Sanitization Is Part of the Contract

`/actuator/env` and `/actuator/configprops` can return sensitive information. In current Spring Boot, `show-values` can be `never`, `always`, or `when-authorized`; keep the `never` default unless there is an explicit need.

Regression tests should use synthetic secrets and verify:

- Key names are observable when policy allows.
- Secret values do not appear in responses when `show-values=never`.
- `when-authorized` reveals values only to users holding the configured role.
- Custom `SanitizingFunction` beans continue applying after upgrading.

Never use real secrets in test fixtures or JSON snapshots.

### 10.3. CSRF and POST Endpoints

If Spring Security enables CSRF protection, `POST` management endpoints can return 403 when missing a CSRF token even if the user is authenticated. Tests should distinguish:

- 401: unauthenticated.
- 403 due to insufficient permissions.
- 403 due to missing/invalid CSRF token.
- 400 due to invalid payload or key.
- 404 due to endpoint not exposed or wrong path.

With `MockMvc`, include a CSRF token on positive `POST` tests and test missing-token requests separately. Do not disable CSRF globally just to pass one endpoint test; apply a policy appropriate for your management network and authentication scheme.

## 11. Establishing a Pre-Upgrade Baseline

Regression tests are most valuable with a clear baseline from a stable running version. Before changing the BOM or Spring Boot, record the behaviors the application commits to preserving:

- Effective values of critical keys.
- Winning property source for each key.
- Active profiles and Config Server label.
- Values bound into `@ConfigurationProperties`.
- Exposed management endpoints and permitted HTTP methods.
- Required permissions per endpoint.
- Sanitization rules.
- Refresh behavior and service registry status.

### 11.1. Do Not Snapshot the Entire Environment

Do not save all of `/actuator/env` or `/actuator/configprops` as a golden file. Responses can include internal metadata, source ordering, bean names, and extra fields that evolve across versions.

Instead, create a selective baseline:

~~~yaml
configuration-contract:
  application: orders-service
  profile: production
  assertions:
    - key: checkout.max-items
      expected-value: "45"
      expected-source: systemEnvironment
    - key: checkout.enabled
      expected-value: "true"
      expected-source: configserver:orders-service
    - key: checkout.request-timeout
      expected-value: "1500ms"
      expected-source: application-production.yml
~~~

This is a documentation format defined by the project team, not a Spring configuration format. Include only non-sensitive keys in the baseline. If source names might shift due to framework internals, prefer asserting effective values and source categories rather than hardcoding internal implementation strings.

### 11.2. Record Profile and Label

A value can be right under `default` yet wrong under `production`. The baseline must record:

- `spring.application.name`.
- Active profiles in order.
- Config Server label/commit if used.
- Important Config Data locations/imports.
- Environment variables permitted to override.

If a test does not pin a profile, it may accidentally run under `default` and miss bugs that occur only in `production`.

### 11.3. Compare Only Stable Data

Assert:

- Critical keys hold expected values.
- Appropriate source categories.
- Beans bind with the right types.
- Endpoints return expected HTTP statuses and enforce permissions.
- Secrets are masked.

Avoid asserting:

- The full ordering of every internal property source.
- Timestamps, random values, or run-varying metadata.
- Full Actuator JSON responses.
- Internal bean/auto-configuration names that are not public APIs.

## 12. Spring Boot and Spring Cloud Upgrade Matrix

A Spring Cloud release train is designed to be compatible with a specific Spring Boot range. When upgrading, test version pairs managed by the Spring Cloud BOM.

Example pipeline matrix:

| Job | Spring Boot | Spring Cloud BOM | Purpose |
| --- | --- | --- | --- |
| Baseline | Current production version | Current release train | Confirm existing contract tests |
| Candidate | Target Boot version | Compatible release train | Detect behavioral changes |
| Compatibility | Lowest supported Boot version | Corresponding release train | Catch loss of support if a library declares a compatibility range |

Do not pair a Spring Boot version with an unsupported release train just to make CI run. Use the BOM to manage dependency versions rather than overriding individual Spring Cloud modules ad hoc.

### 12.1. Enable the Compatibility Verifier in Tests

Spring Cloud Commons includes a compatibility verifier to validate the Spring Boot version. It can be enabled in tests/CI:

~~~yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
~~~

The verifier helps catch certain incompatible version pairs when the context starts. It does not replace regression tests for property precedence or Actuator endpoints; an application can still use a supported pair while changing runtime behavior.

### 12.2. Run the Same Suite Against Both BOMs

If your build supports a matrix, run the identical suite against:

- The BOM currently running in production.
- The candidate BOM selected for the upgrade.

Compare assertions for effective values, source categories, bean binding, and endpoint behavior. When differences appear, classify them as:

1. Intentional framework change.
2. Change caused by missing configuration or dependency.
3. Test fixture overriding runtime values.
4. Behavioral regression requiring a fix or rollback.

Do not edit expected values merely to turn CI green. Before accepting a change, understand which source is winning and which endpoint altered its contract.

## 13. Post-Upgrade CI Checklist

A regression pipeline can be structured into layers:

| Layer | Tests | Relative speed | Dependencies |
| --- | --- | --- | --- |
| 1 | `MockEnvironment` and `MutablePropertySources` unit tests | Fast | None |
| 2 | `ApplicationContextRunner` and configuration binding | Fast | None |
| 3 | Config Data file/location/profile tests | Fast | Test resources |
| 4 | Config Server HTTP contract tests | Medium | WireMock/MockWebServer |
| 5 | Actuator `MockMvc` tests | Medium | Application context |
| 6 | Management port/security integration tests | Medium | Web server/security |
| 7 | Provider integration tests (Eureka/Consul) | Slower | Registry test container |
| 8 | Smoke tests on candidate image | Slower | Staging environment |

### 13.1. Pass Criteria

A candidate should only be accepted when:

- Every key in the baseline has the right effective value.
- Winning sources match or differences are explained and approved.
- `@ConfigurationProperties` bind the right values and types.
- Config Data/Config Server/legacy bootstrap operate according to the application's chosen mode.
- Management endpoints have accurate mappings, exposure, and methods.
- Authorization and sanitization have not been relaxed unintentionally.
- `POST` endpoints cannot modify keys outside the allowlist.
- Refresh and service registry tests pass with realistic providers.
- Compatibility verifier reports no incompatible Boot/Cloud pair.

### 13.2. Save Comparable Reports

Each job should output a short report:

~~~text
Spring Boot: 4.x.y
Spring Cloud BOM: 5.x.y
Config mode: config-data
Active profiles: production

Property precedence:
- checkout.max-items: PASS (systemEnvironment)
- checkout.enabled: PASS (configserver)
- checkout.request-timeout: PASS (application-production.yml)

Management endpoints:
- GET /actuator/env: PASS
- GET /actuator/configprops: PASS
- POST /actuator/env allowlisted key: PASS
- POST /actuator/env forbidden key: PASS
- POST /actuator/refresh: PASS
- GET/POST /actuator/serviceregistry: PASS

Security:
- unauthenticated management request: DENIED
- secret sanitization: PASS
~~~

Do not print secret values into reports. Source categories and assertion statuses are usually enough to compare across jobs.

## 14. Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Different value after upgrade, yet startup passes | Property source order or Config Data import shifted | Inspect `Environment.getProperty()` and winning source |
| Local config fails to override Config Server | Remote source did not grant `allowOverride` or bootstrap mode differs | Check remote metadata and override flags |
| Config Server is never called | Missing `spring.config.import` or legacy bootstrap not enabled | Confirm config loading mode, then check starter/properties |
| Config Server is called multiple times | Config Data fetches default profile and active profiles | Assert request semantics, do not hardcode a single request |
| `production` profile not loaded | Wrong active profile or profile order changed | Pin profile explicitly in tests and inspect requests |
| `@DynamicPropertySource` beats test properties | Dynamic source has higher precedence than `@TestPropertySource` | Check fixtures; do not arbitrarily alter expectations |
| `Environment` is right, but bean is wrong | Binder/converter/bean lifecycle or test reads stale instance | Assert bean binding, context refresh, and custom converters |
| `/actuator/env` returns 404 | Endpoint not exposed or management base path/port differs | Check exposure and actual URL |
| `/actuator/env` returns 403 | Security, CSRF, or access policy | Distinguish missing role from missing CSRF token |
| Secret exposed in plaintext | `show-values` or custom sanitizer changed | Set `never` or role policy and add a regression test |
| `POST env` does not work | `POST` not enabled or key blocked by regex | Check `management.endpoint.env.post.*` |
| `POST refresh` does not exist | Spring Cloud Context absent from classpath or endpoint unexposed | Check dependencies and Actuator exposure |
| ServiceRegistry endpoint returns 404 | Missing `Registration` bean or endpoint unexposed | Check provider auto-configuration and registration |
| `POST` service registry returns error | Status unsupported by provider | Use a valid status for the implementation |
| Test passes alone, fails in suite | Context cache, system properties, or shared fixtures | Isolate fixtures, restore system properties, use `@DirtiesContext` if needed |
| Candidate fails only on CI | Runner env vars or JVM system properties differ from local | Log winning source metadata without printing secret values |

### 14.1. Precedence Mismatch Investigation Procedure

1. Record active profiles and application name.
2. Call `Environment.getProperty(key)` to obtain the effective value.
3. Iterate `MutablePropertySources` to find the first source containing the key.
4. Check Config Data locations/imports and profile-specific files.
5. If Config Server is present, determine whether Config Data or legacy bootstrap is active.
6. Check remote override flags if legacy bootstrap is enabled.
7. Check whether test properties are overriding production configuration.
8. Verify `@ConfigurationProperties` beans rebound properly.
9. Re-run tests on both the old BOM and candidate BOM to isolate changes.

### 14.2. Management Endpoint Investigation Procedure

1. Confirm endpoint ID and management base path.
2. Confirm the endpoint is exposed via HTTP/JMX.
3. Check access policy and the Spring Security filter chain.
4. Check CSRF for `POST` requests.
5. Verify the `Registration` bean if required by the endpoint.
6. Check payload, valid status values, and regex allowlist.
7. Test sanitization using a synthetic secret.
8. Compare required response contracts without snapshotting the entire JSON.

## 15. Practice Exercises

### Exercise 1 — Write a Three-Source Precedence Test

Create three `MapPropertySource` instances all declaring `checkout.max-items`. Add them with `addFirst` and `addLast`, verifying the effective value and winning source. Then remove the first source and verify the next value takes over.

### Exercise 2 — Profiles and Config Data Import

Create fixtures for the `default` profile and `production`. Add two imports declaring the same key. Write tests verifying profile order and import precedence. Try reversing import order to observe the result change.

### Exercise 3 — Remote Config Server

Use WireMock or MockWebServer to serve configuration by application/profile/label. Test Config Data import and, if the application still uses legacy bootstrap, write a separate test for bootstrap mode. Do not use a real Config Server.

### Exercise 4 — Binding Regression

Use `ApplicationContextRunner` to verify String, Integer, Duration, Boolean, List, and Map bind properly. Add a custom converter if your application uses one.

### Exercise 5 — Actuator Read Contract

Use `MockMvc` to call `GET /actuator/env` and `/actuator/configprops`. Verify critical keys appear, secret values are masked, and endpoints are exposed only as configured in tests.

### Exercise 6 — Actuator Mutation Contract

Enable `POST /actuator/env` with an allowlist regex in tests. Verify allowed keys update the bean, keys outside the allowlist are rejected, and unauthorized users cannot call the endpoint.

### Exercise 7 — Refresh and Registry Endpoints

Test `POST /actuator/refresh` on an application with refresh scope. With a registry provider, test `GET`/`POST /actuator/serviceregistry` using valid statuses for the implementation.

### Exercise 8 — Compare BOMs Before and After Upgrading

Run the same test suite on the current BOM and candidate BOM. Output a report showing Boot version, Cloud BOM, config mode, profile, winning property sources, endpoint statuses, and security results. Explain any differences before updating the baseline.

**Completion criteria:** you can demonstrate that runtime configuration values and management endpoint behaviors do not change unexpectedly after upgrading Spring Boot/Spring Cloud.

## 16. Summary

Configuration regression testing must verify source precedence, binding, and management endpoint contracts together. Spring Boot has its own configuration source ordering; Config Data adds file, profile, location, and import ordering. Spring Cloud Config has two distinct loading modes—Config Data and legacy bootstrap—with remote property source override policies that must be tested per mode.

Use `MockEnvironment`, `MutablePropertySources`, `TestPropertyValues`, and `ApplicationContextRunner` for focused logic checks, then use integration tests with a mock Config Server and `MockMvc` to verify real application behavior. For Actuator, verify exposure, mapping, HTTP methods, authorization, CSRF, and sanitization. For Spring Cloud Commons, test `serviceregistry` alongside `Registration` and provider statuses.

Before upgrading, capture a selective baseline for key properties, source categories, profiles, bean bindings, and endpoints. Run the identical regression suite on both the old BOM and candidate BOM; accept differences only after understanding their root causes and confirming the change is intentional.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property source ordering, Config Data locations, profiles, imports, and property precedence.
- [Spring Boot — Test Utilities](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html): `ConfigDataApplicationContextInitializer`, `TestPropertyValues`, and context testing utilities.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, access, sanitization, and `env`/`configprops` contracts.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource` and precedence relative to `@TestPropertySource`.
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): inline properties, resource locations, and test property source ordering.
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): `env`, `refresh`, bootstrap context, and refresh behavior.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `ServiceRegistry`, auto-registration, and the `/serviceregistry` endpoint.
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, legacy bootstrap, profile/label, and remote property sources.
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html): remote overrides and `overrideNone`.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): compatibility verifier and properties controlling Config/Commons.

Always check the documentation for the exact Spring Boot and Spring Cloud release train in your project. Properties, endpoint access policies, and response structures can change between release generations.

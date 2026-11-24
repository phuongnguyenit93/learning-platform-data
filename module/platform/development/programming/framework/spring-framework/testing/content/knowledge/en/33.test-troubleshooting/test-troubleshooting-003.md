# Profiles and Properties Out of Precedence Order

## 1. Distinguishing Active Profiles from Property Precedence

When a Spring test uses the wrong configuration, the cause usually lies in one of two distinct mechanisms:

- **Active profile** determines which beans or configurations annotated with `@Profile` are included in the `ApplicationContext`, as well as which profile-specific configuration files are loaded.
- **Property precedence** determines which value wins when the same key appears in multiple `PropertySource` entries of the `Environment`.

These two mechanisms are related, but they do not replace each other. `@ActiveProfiles("test")` asks Spring TestContext to activate the `test` profile; it does not mean every property in `application-test.yml` always overrides every other configuration source. An environment variable, JVM system property, or test property source can still override values in the profile file.

For example, suppose an application has the following configurations:

```yaml
# application.yml
payment:
  api-base-url: https://payments.example.com
  timeout: 5s
```

```yaml
# application-test.yml
payment:
  api-base-url: http://localhost:9091
  timeout: 2s
```

If the `test` profile is active, Boot loads the corresponding profile configuration. However, if the test runtime environment also sets `PAYMENT_TIMEOUT=10s`, the value from the environment variable can override the value in the configuration file. Therefore, whenever you see a bean using the wrong URL or timeout, verify separately which profile is active and which source provided the final property value.

## 2. How Are Profiles Activated?

The Spring `Environment` maintains lists of active profiles and default profiles. When no profile is explicitly activated, Spring uses the default profile, typically named `default`.

In a regular application, profiles can be activated using the `spring.profiles.active` property, for example:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Or via an environment variable:

```text
SPRING_PROFILES_ACTIVE=dev
```

For integration tests using the Spring TestContext Framework, the explicit declaration is usually `@ActiveProfiles`:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTests {
}
```

When `@ActiveProfiles` is present, the TestContext Framework uses the profiles declared on the annotation to determine active profiles. By default, `spring.profiles.active` set as a JVM system property or environment variable is not used to replace that list. This is a common source of confusion when running tests across an IDE and CI with different environment variables.

If a test needs to allow an external profile to override the annotation's profiles, you can implement a custom `ActiveProfilesResolver`. Do not expect `@ActiveProfiles("test")` and `SPRING_PROFILES_ACTIVE=staging` to merge automatically according to normal property precedence.

### Inheriting Active Profiles

By default, `@ActiveProfiles` allows inheriting profiles from superclasses and enclosing classes. For example:

```java
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

class OrderRepositoryTest extends BaseIntegrationTest {
    // The integration profile is inherited.
}
```

If a subclass needs its own separate set of profiles, set `inheritProfiles = false`:

```java
@ActiveProfiles(profiles = "repository-test", inheritProfiles = false)
class IsolatedRepositoryTest extends BaseIntegrationTest {
}
```

In this case, the subclass does not inherit `integration` from the superclass. The `inheritProfiles` attribute controls profile inheritance; it does not control inheritance of properties in `@TestPropertySource`.

### ActiveProfilesResolver

When profiles need to depend on the runtime environment, you can use a resolver:

```java
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ActiveProfilesResolver;
import org.springframework.test.context.support.DefaultActiveProfilesResolver;

public class CiAwareProfilesResolver implements ActiveProfilesResolver {

    private final DefaultActiveProfilesResolver fallback =
            new DefaultActiveProfilesResolver();

    @Override
    public String[] resolve(Class<?> testClass) {
        String ciProfile = System.getenv("TEST_PROFILE");
        if (ciProfile != null && !ciProfile.isBlank()) {
            return ciProfile.split(",");
        }
        return fallback.resolve(testClass);
    }
}
```

Register the resolver on the test class:

```java
@ActiveProfiles(resolver = CiAwareProfilesResolver.class)
class EnvironmentAwareIntegrationTest {
}
```

The resolver above checks the `TEST_PROFILE` variable first and falls back to Spring's default behavior if absent. This is a policy chosen by the test suite; restrict allowed profiles and avoid accepting arbitrary values from untrusted environments.

## 3. How Are Profile-Specific Configuration Files Loaded?

In Spring Boot, common configuration files include:

```text
src/main/resources/
  application.yml
  application-test.yml
  application-ci.yml
```

`application.yml` holds shared configuration. `application-test.yml` is only applied when the `test` profile is active; `application-ci.yml` is only applied when the `ci` profile is active.

Example:

```yaml
# application.yml
server:
  port: 8080
payment:
  timeout: 5s
```

```yaml
# application-test.yml
server:
  port: 0
payment:
  timeout: 1s
```

When running with the `test` profile, `server.port` is set to `0` so the server picks a random port, and `timeout` is set to one second. Keys not declared in the profile file still come from the shared configuration or other sources.

Spring Boot processes config data by location and profile. At a general level, configuration files external to the packaged application can override files on the classpath; profile-specific files can override general files within the same location group. Locations declared later generally have higher precedence than earlier locations. If `spring.config.location` or `spring.config.additional-location` is configured, account for that location ordering during diagnosis.

Several important distinctions:

- `spring.config.location` replaces the default search locations.
- `spring.config.additional-location` adds configuration locations and can override default configuration.
- Locations are processed in declaration order; later locations can override matching keys from earlier locations.
- `.properties` and YAML files in the same location have their own precedence rules; Boot recommends standardizing on a single format across the application.
- With multiple active profiles, corresponding configuration documents are evaluated in profile and source order; when multiple values collide, the higher-precedence source wins.

Do not assume `application-test.yml` always beats every file or every source. It is only one part of Boot's `PropertySource` system.

## 4. Property Precedence Order in Spring Boot

Spring Boot defines an order of configuration sources so values from higher-precedence sources override lower-precedence ones. According to the current Externalized Configuration documentation, the order from lowest to highest is described as follows:

| Order | Property source | Notes |
|---:|---|---|
| 1 | Default properties from `SpringApplication.setDefaultProperties(...)` | Lowest fallback values. |
| 2 | `@PropertySource` on `@Configuration` classes | Added during context refresh; too late for some properties read before refresh such as `logging.*` and `spring.main.*`. |
| 3 | Config data | Includes `application.yml`, `application-{profile}.yml`, and imported locations. |
| 4 | `RandomValuePropertySource` | Supplies keys under `random.*`. |
| 5 | OS environment variables | For example, `PAYMENT_TIMEOUT`. |
| 6 | Java system properties | For example, `-Dpayment.timeout=8s`. |
| 7 | JNDI attributes | When the application runs in an environment supporting JNDI. |
| 8 | `ServletContext` init parameters | For Servlet applications. |
| 9 | `ServletConfig` init parameters | For the corresponding configured Servlet. |
| 10 | `SPRING_APPLICATION_JSON` | Properties passed as JSON in an environment variable or system property. |
| 11 | Command-line arguments | For example, `--payment.timeout=3s`. |
| 12 | `properties` on `@SpringBootTest` and test slice annotations | Spring Boot inline test properties. |
| 13 | `@DynamicPropertySource` | Typically used to supply dynamic URLs/ports from Testcontainers or mock servers. |
| 14 | `@TestPropertySource` | Test-specific property sources. |
| 15 | Devtools global settings | Only relevant when Devtools is active. |

The table above describes the order per the Spring Boot reference; when using plain Spring Framework TestContext or a different Boot version, cross-check the exact version's documentation and inspect the `Environment` directly in the running context.

Spring Framework TestContext separately documents that dynamic properties have higher precedence than `@TestPropertySource`, system properties, environment variables, and application property sources. Spring Boot's documentation lists the test source order within Boot's externalized configuration table. Therefore, when a Boot test combines multiple kinds of test property sources, do not rely on memory or apply a single table to every bootstrapper; follow the order documented for the exact version in use and inspect the actual property sources.

## 5. `@TestPropertySource`: Files and Inline Properties

`@TestPropertySource` lets you declare properties files and inline key-value pairs for a test class:

```java
import org.springframework.test.context.TestPropertySource;

@TestPropertySource(
        locations = "classpath:/order-test.properties",
        properties = {
                "payment.timeout=750ms",
                "feature.audit.enabled=false"
        }
)
class OrderServiceTests {
}
```

Example `order-test.properties` file:

```properties
payment.timeout=2s
payment.retry-count=1
```

When the same key appears in both the file and the inline `properties` attribute, the inline property has higher precedence than the file location. Thus `payment.timeout` receives `750ms`, while `payment.retry-count` receives `1`.

`@TestPropertySource` has several notable rules:

- It can be declared multiple times on a class; later declarations override earlier ones for matching keys.
- An annotation declared directly on the test class has higher precedence than one discovered via a meta-annotation.
- `inheritLocations` and `inheritProperties` allow inheriting test property configuration from superclasses by default.
- Set `inheritLocations = false` or `inheritProperties = false` to replace the corresponding inherited part.
- If an empty `@TestPropertySource` is used, Spring looks for a default file named after the test class, such as `OrderServiceTests.properties`; if not found, the test can fail while loading the context.

By default, `@TestPropertySource` supports Java properties and XML properties. Since Spring Framework 6.1, a custom `PropertySourceFactory` can be used to load other formats such as YAML or JSON. Do not assume `@TestPropertySource("classpath:application-test.yml")` reads YAML automatically without configuring an appropriate factory.

## 6. `@DynamicPropertySource` for Runtime-Generated Values

`@DynamicPropertySource` is suited for values only known after a test resource starts, such as a random port from Testcontainers, WireMock, or a local server.

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RepositoryIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

A method annotated with `@DynamicPropertySource` must be `static` and accept a `DynamicPropertyRegistry`. Values are supplied via a `Supplier`, so they are only fetched when the property is resolved. This is why you should pass method references such as `postgres::getJdbcUrl` rather than reading the port prematurely before the container has started.

Dynamic properties are intended for dynamic endpoints. Do not use them to mask a broken test configuration or indiscriminately override every property. Limit them to values that genuinely depend on the lifecycle of test resources.

If a base test class declares `@DynamicPropertySource` but the dynamic values differ across subclasses, Spring Test may reuse the application context from the context cache. When the cached context still holds properties from a previous resource, separate the context configuration or use `@DirtiesContext` appropriately so each class gets a context with the right values.

## 7. `@SpringBootTest(properties)` and Test Slice Properties

Spring Boot allows declaring inline properties directly on test annotations:

```java
@SpringBootTest(properties = {
        "payment.timeout=500ms",
        "feature.audit.enabled=false"
})
class PaymentIntegrationTests {
}
```

These properties are useful when a single test class needs to override a few values without creating a separate properties file. Test slice annotations such as `@WebMvcTest` also support a similar attribute.

Do not confuse `@SpringBootTest(properties=...)` with `@TestPropertySource`. They are different mechanisms and sit at different positions in Spring Boot's property source order. If the same key is declared in multiple sources, verify precedence according to the documentation for the Boot version in use.

For values shared across many tests, an `application-test.yml` file or test configuration may be easier to manage. For an exception specific to one test class, inline properties are usually clearer.

## 8. Do Not Use Property Precedence to Replace Profile Activation

A common mistake is setting `spring.profiles.active` inside a test property source:

```java
@TestPropertySource(properties = "spring.profiles.active=test")
class OrderServiceTests {
}
```

This is not a reliable way to tell Boot to load `application-test.yml`. Test property sources are added to the context during test preparation; they are not always present at the point when Config Data has already decided which profiles to use for loading files. As a result, the property may appear in `Environment`, yet the profile-specific file was not loaded as intended.

Activate profiles using the test profile mechanism:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTests {
}
```

Or provide `spring.profiles.active` from an early bootstrap source such as a JVM system property, environment variable, or command line when no `@ActiveProfiles` overrides TestContext profile resolution.

If you want a test to override only one property, declare that property directly:

```java
@SpringBootTest(properties = "payment.timeout=500ms")
class FastPaymentTests {
}
```

Do not use `spring.profiles.active` as an ordinary configuration key when the real goal is simply to change a single value.

## 9. Profile-Specific Rules to Remember

Spring Boot enforces several restrictions so profile activation is processed consistently:

- `spring.profiles.active` and `spring.profiles.default` may only be declared in profile-independent configuration documents.
- Do not place these two keys inside `application-test.yml` or inside a document activated by `spring.config.activate.on-profile`.
- You can use `spring.profiles.include` to add profiles and `spring.profiles.group` to group multiple profiles under one logical name.
- Use `spring.config.activate.on-profile` to activate a specific document in a multi-document configuration file.
- The `default` profile is only used when no other active profile is set.

Example of a profile group:

```yaml
spring:
  profiles:
    group:
      integration:
        - test
        - database-test
        - messaging-test
```

When `integration` is activated, its member profiles are also added to active profiles. This is helpful when multiple tests require the same combination of configurations. Avoid declaring profile groups or includes across multiple different sources unless the final ordering and profile combination are clearly understood.

Example of document activation:

```yaml
app:
  banner: default
---
spring:
  config:
    activate:
      on-profile: test
app:
  banner: test-mode
```

The second document is only applied when the `test` profile is active. Activating profiles and selecting property sources remain two related yet distinct steps.

## 10. Diagnosing Where a Property Comes From

When a bean receives an unexpected value, first read the resolved value via `Environment` and inspect the list of `PropertySource` instances. `MutablePropertySources` is traversed in precedence order; the first property source containing the key is the source used.

```java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

void diagnose(ConfigurableApplicationContext context) {
    ConfigurableEnvironment environment = context.getEnvironment();

    System.out.println("Active profiles: "
            + String.join(", ", environment.getActiveProfiles()));
    System.out.println("Default profiles: "
            + String.join(", ", environment.getDefaultProfiles()));

    String key = "payment.timeout";
    System.out.println("Resolved value: " + environment.getProperty(key));

    for (PropertySource<?> source : environment.getPropertySources()) {
        if (source.containsProperty(key)) {
            System.out.println("First matching source: " + source.getName());
            break;
        }
    }
}
```

This snippet illustrates how to locate the first source containing a property. In real applications, avoid logging sensitive values such as passwords, tokens, or connection strings. You can log only the source name, or mask values before displaying them.

A quick check directly inside a test:

```java
@Autowired
Environment environment;

@Test
void printsTestConfiguration() {
    System.out.println(Arrays.toString(environment.getActiveProfiles()));
    System.out.println(environment.getProperty("payment.api-base-url"));
}
```

If using Spring Boot Actuator, the `env` endpoint helps inspect property sources and value origins; `configprops` helps inspect values bound into `@ConfigurationProperties`. Only enable and expose these endpoints in appropriate environments, and protect sensitive data according to security policy.

## 11. Diagnosing Binding with `@ConfigurationProperties`

Sometimes `Environment.getProperty("payment.timeout")` returns the expected value, yet the `@ConfigurationProperties` bean holds a different value. When that happens, check the prefix, key name, data types, validation, and how the binder handles complex structures.

Example:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        String apiBaseUrl,
        Duration timeout,
        int retryCount) {
}
```

Kebab-case keys are recommended in configuration files:

```yaml
payment:
  api-base-url: http://localhost:9091
  timeout: 2s
  retry-count: 1
```

Sources such as environment variables follow specific relaxed binding rules. For example, `PAYMENT_API_BASE_URL` can map to `payment.api-base-url`. When variable names contain underscores, dots, or list indices, follow Spring Boot's binding rules rather than guessing by replacing characters arbitrarily.

In particular, when the same structure is declared across multiple sources:

- For scalar properties, the value from the higher-precedence source is used.
- For lists, the higher-precedence source typically replaces the entire list; elements from lower-precedence sources are not automatically appended.
- For maps, entries can be merged by key, though the same key still takes the value from the higher-precedence source.

Therefore, a configuration list losing elements after adding a profile or environment variable may be standard list override behavior rather than a file-parsing bug.

## 12. Context Caching Can Cause Stale Configuration to Appear

The Spring TestContext Framework caches `ApplicationContext` instances to shorten suite execution time. Configuration attributes such as active profiles, context customizers, and test property sources participate in computing the context cache key.

If two test classes share identical configuration, they can reuse the same context. This is usually beneficial, but pay attention when:

- A `@DynamicPropertySource` in a base class returns values that change across subclasses.
- A static container or mock server is restarted while the context still retains the old endpoint.
- A test mutates singleton bean state or a property source after the context has already been created.
- A test uses `@DirtiesContext`, evicting the context from the cache and forcing the next test to build a new context.

If dynamic values differ across subclasses, ensure each subclass gets a context matching its resource. You can use `@DirtiesContext` at the appropriate scope or separate the test configuration so context cache keys differ. Do not mutate `Environment` arbitrarily after beans are initialized expecting `@Value` fields to update automatically; most injected values are resolved when the bean is created.

## 13. Common Errors and Resolutions

| Symptom | Common cause | Resolution |
|---|---|---|
| `application-test.yml` is not loaded | The `test` profile is not active or the test declares a different `@ActiveProfiles`. | Print `Environment.getActiveProfiles()` and check annotations/resolvers. |
| `SPRING_PROFILES_ACTIVE` does not change test profiles | The test class declares `@ActiveProfiles`, so TestContext does not use the env var to replace it. | Remove the annotation to use external profiles, or implement `ActiveProfilesResolver`. |
| Profile is right but URL/timeout is still wrong | An environment variable, JVM property, command-line arg, or test property source outranks the file. | Find the first property source containing the key and inspect the overriding source. |
| `@TestPropertySource` does not read YAML | The default factory does not support YAML. | Use `.properties` or configure a custom `PropertySourceFactory` (Spring Framework 6.1+). |
| Empty `@TestPropertySource` fails context loading | Spring cannot find a default properties file named after the test class. | Declare `locations` explicitly or remove the empty annotation. |
| `@DynamicPropertySource` gets the wrong value | The supplier reads the resource before readiness, or the context cache retains values from another test. | Use method references, align resource lifecycle, and isolate/refresh contexts when needed. |
| `@PropertySource` does not change `logging.*` | The property source is added too late in Boot's startup lifecycle. | Place the property in config data or an early bootstrap source. |
| List in `@ConfigurationProperties` loses items | A list in a higher-precedence source replaces the entire list. | Declare the full list in the overriding source or switch to a map if appropriate. |
| Subclass `@ActiveProfiles` still receives superclass profiles | `inheritProfiles` defaults to `true`. | Set `inheritProfiles = false` when replacing the inherited list. |
| Bean keeps old value after property change | The bean was created and injected before the property changed. | Create a new context or design dynamic configuration with an explicit refresh mechanism. |

## 14. Workflow for Troubleshooting Misconfigured Tests

When a test uses the wrong profile or property, diagnose in this order:

1. Print active profiles and default profiles from `Environment`.
2. Inspect the test class, base classes, enclosing classes, and `ActiveProfilesResolver` to see where profiles come from.
3. Verify the profile-specific file is named properly and located in a config location searched by Boot.
4. Check `spring.config.location`, `spring.config.additional-location`, config imports, and files outside the classpath.
5. Search all places declaring the key under investigation: YAML, properties, environment variables, JVM `-D`, command line, `@SpringBootTest(properties)`, `@DynamicPropertySource`, `@TestPropertySource`, and `@PropertySource`.
6. Iterate over `Environment.getPropertySources()` to identify the first source containing the key.
7. If using `@ConfigurationProperties`, check the prefix, relaxed binding, data types, list/map merging, and validation.
8. If tests pass individually but values change across classes in a suite, check context caching and dynamic resource lifecycles.
9. Modify only the intended configuration source; avoid piling on a new override without removing the old cause.

## 15. Principles for Organizing Test Configuration

- Use `@ActiveProfiles("test")` to choose profiles explicitly for the test context.
- Use `application-test.yml` for shared test environment configuration.
- Use `@TestPropertySource` or `@SpringBootTest(properties=...)` for overrides specific to a test class.
- Use `@DynamicPropertySource` for URLs, ports, and values only available after test resources start.
- Avoid declaring the same key in too many places; when an override is needed, document why in the test.
- Do not place `spring.profiles.active` in a profile-specific file or rely on a late test property source to replace profile activation.
- Do not leave production endpoints or credentials as fallbacks in test profiles.
- When inheriting test configuration, determine profile inheritance and property source inheritance rules separately.
- Inspect actual property sources whenever precedence is complex, especially between plain Spring Framework and Spring Boot's test bootstrapper.
- Protect diagnostic logs and endpoints so secrets are never exposed.

## 16. Conclusion

Profile activation and property precedence are two distinct mechanisms. `@ActiveProfiles` selects profiles for Spring TestContext; `PropertySource` determines the final value of each key. `application-{profile}.yml` is just one source among many configuration sources, while test property sources, environment variables, JVM properties, and command-line arguments can override it according to the precedence order of the Spring version in use. When encountering wrong configuration, verify the active profiles first, then locate the first property source containing the key in `Environment`. This check pinpoints the exact cause instead of piling on additional overrides.

## References

- [Spring Framework Reference — Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
- [Spring Framework Reference — Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework Reference — Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)

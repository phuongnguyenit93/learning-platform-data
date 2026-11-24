# Precedence Order of Configuration Sources

In a Spring application, a property can be declared in multiple places: configuration files, environment variables, JVM system properties, test-specific configurations, or values dynamically supplied from an external resource. When multiple sources declare the same key, Spring needs a rule to determine which source is used.

That rule is expressed through **the ordering of `PropertySource` instances in `Environment`**. Spring searches the sources in precedence order; the first source containing the key supplies the value. Understanding this ordering is therefore essential when configuring profiles, writing tests with `@TestPropertySource`, supplying Testcontainers data via `@DynamicPropertySource`, or diagnosing why `@Value` receives an unexpected value.

## 1. Environment and PropertySource

`Environment` is Spring's abstraction for accessing two groups of information:

- **Profiles:** the active profiles or default profile, used to decide which beans and configurations are applied.
- **Properties:** key/value pairs obtained from one or more configuration sources.

In Spring configuration, `ConfigurableEnvironment` allows reading and modifying the list of property sources. Each source is represented by a `PropertySource<?>`, typically a named collection of key/value pairs.

Some common source types:

| Source | Example | Purpose |
|---|---|---|
| `MapPropertySource` | Map created by the application or test | Supplies properties from in-memory data |
| `PropertiesPropertySource` | `java.util.Properties` object | Adds a Java properties set to Environment |
| `ResourcePropertySource` | `.properties` file or equivalent resource | Reads configuration from a resource |
| `System.getProperties()` | `-Dapp.timeout=30` | Configuration via JVM system properties |
| System environment | `APP_TIMEOUT=30` | Configuration via operating system environment variables |
| Test property source | `@TestPropertySource` | Test-specific configuration overrides |
| Dynamic test property source | `@DynamicPropertySource` | Supplies values computed or obtained from external resources at test runtime |

`Environment.getProperty("app.timeout")` looks up the key across registered sources. If the key appears in multiple sources, the value from the higher-precedence source is returned. This is an order-based property resolution mechanism, not a "most recently added over time always wins" rule.

### 1.1. Ordering in MutablePropertySources

`ConfigurableEnvironment#getPropertySources()` returns a `MutablePropertySources`. This list maintains search order and provides operations:

- `addFirst(propertySource)`: places the source at the front of the list, giving it the highest precedence among existing sources.
- `addLast(propertySource)`: appends the source at the end, with lower precedence than preceding sources.
- `addBefore(name, propertySource)` and `addAfter(name, propertySource)`: places the source before or after a named source.
- `replace(name, propertySource)`: replaces the named source with a new one.
- `remove(name)`: removes a source by name.

Example:

```java
ConfigurableEnvironment environment = new StandardEnvironment();

Map<String, Object> overrides = Map.of(
        "app.timeout", "15",
        "app.feature.enabled", "true");

environment.getPropertySources().addFirst(
        new MapPropertySource("local-test-overrides", overrides));

assertEquals("15", environment.getProperty("app.timeout"));
assertEquals(Boolean.TRUE,
        environment.getProperty("app.feature.enabled", Boolean.class));
```

`addFirst` causes the new source to be checked before default sources such as system properties and the system environment. In real applications, only alter the order when there is an explicit configuration requirement; an overriding source at the head of the list can shadow values from every source behind it.

### 1.2. The first-match-wins rule

Suppose the source list has the following order:

```text
1. test-overrides
2. systemProperties
3. systemEnvironment
4. application-properties
5. defaultProperties
```

If `app.timeout` exists in `test-overrides`, Spring returns the value from this source without reading from lower sources. If the key is absent from the first source, Spring continues checking the second source and so on until found or the list is exhausted.

This is why a property can appear in multiple files while the application sees only one value at a time. Lower sources still exist in `Environment`; they are simply not selected for keys already provided by a higher source.

## 2. Spring's Default Property Sources

With `StandardEnvironment`, Spring registers two important sources:

1. `systemProperties`: properties from the JVM's `System.getProperties()`.
2. `systemEnvironment`: operating system environment variables.

System properties come before the system environment in `StandardEnvironment`. If both declare a corresponding key, the system property takes precedence.

Example running the JVM:

```bash
java -Dapp.region=from-jvm -jar application.jar
```

Or declaring an environment variable:

```bash
APP_REGION=from-environment java -jar application.jar
```

On Windows PowerShell:

```powershell
$env:APP_REGION = "from-environment"
java -Dapp.region=from-jvm -jar application.jar
```

In `StandardEnvironment`, `Environment#getProperty("app.region")` returns `from-jvm` when both configuration mechanisms supply corresponding values. How environment variable names map can depend on `SystemEnvironmentPropertySource`; when working with environment variables, follow the naming conventions supported by the environment and framework in use.

For Servlet-based web applications, `StandardServletEnvironment` adds related sources such as servlet config, servlet context, and JNDI. These sources are ordered as defined by Spring's implementation; do not assume every `Environment` type has the exact same two sources as `StandardEnvironment`.

## 3. Configuration Sources Declared with @PropertySource

`@PropertySource` adds a resource to `Environment` when Spring processes Java configuration.

```java
@Configuration
@PropertySource("classpath:/config/application-defaults.properties")
public class ApplicationConfiguration {
}
```

Example contents of `application-defaults.properties`:

```properties
app.region=ap-southeast
app.timeout=10
app.feature.enabled=false
```

Once the configuration class is processed, these values can be read via `Environment` or placeholder resolution.

```java
@Component
public class ApplicationSettings {

    private final Environment environment;

    public ApplicationSettings(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region");
    }
}
```

With `StandardEnvironment`, `systemProperties` and `systemEnvironment` are already registered beforehand. Sources added by `@PropertySource` are normally placed after these default sources, so corresponding system properties or environment variables can override values in the file.

When there are multiple `@PropertySource` annotations, the order in which configuration classes are processed can affect which source is added earlier or later. If override order among multiple files is an important requirement, configure the order explicitly or use controlled `PropertySource` registration instead of relying on unspecified component-scanning order.

`@PropertySource` belongs to Spring Framework. Spring Boot's automatic loading of `application.properties`, `application.yml`, and profile-specific files is Spring Boot's Config Data mechanism, which has its own rules and more sources. Do not take Spring Boot Config Data ordering and apply it verbatim to a plain Spring Framework application.

## 4. Property Source Precedence Order in Spring TestContext

Spring TestContext provides annotations for adding test-specific configuration. These sources are placed with high precedence so tests can replace application configuration without editing production configuration files.

Within the scope of common Spring TestContext sources, the precedence order from highest to lowest is:

| Priority | Source | How Declared | Meaning |
|---:|---|---|---|
| 1 | Dynamic test properties | `@DynamicPropertySource` | Dynamic values, usually from containers or resources started in tests |
| 2 | Inline test properties | `@TestPropertySource(properties = ...)` | Key/value pairs written directly on the test class |
| 3 | Test property resources | `@TestPropertySource(locations = ...)` | Configuration files specified exclusively for tests |
| 4 | JVM system properties | `-Dkey=value` or `System.setProperty` | Configuration of the JVM process |
| 5 | System environment | Environment variables | Configuration from the operating system |
| 6 | Application `@PropertySource` | `@PropertySource` on configuration classes | Resource configuration declared by the application |
| 7 | Default properties | `MutablePropertySources` configured at the end | Fallback values when no other source supplies the key |

The table above describes the typical order when using Spring TestContext with `StandardEnvironment` and the listed sources. If the application or test manually adds, replaces, or reorders `PropertySource`s, the actual order depends on that configuration. With Spring Boot, Config Data sources and properties provided by Boot tests must also be accounted for according to the Boot version in use.

### 4.1. @TestPropertySource with resource files

`@TestPropertySource(locations = ...)` loads one or more test-only files:

```java
@SpringJUnitConfig(TestConfiguration.class)
@TestPropertySource(locations = "classpath:/config/test-defaults.properties")
class AccountServiceTest {
    // test methods
}
```

Example `test-defaults.properties`:

```properties
app.region=test-region
app.timeout=20
app.feature.enabled=true
```

Properties in test property resources have higher precedence than system properties, system environment, and application configuration sources declared with `@PropertySource` under TestContext rules.

If `locations` is omitted, Spring can look for a default resource matching the test class name by `@TestPropertySource` convention. To avoid tests depending on an implicit file that is hard to notice, specify `locations` explicitly when wanting to use a particular resource.

### 4.2. Inline properties have higher precedence than test files

Values can be declared right on the annotation:

```java
@TestPropertySource(
        locations = "classpath:/config/test-defaults.properties",
        properties = {
                "app.timeout=30",
                "app.feature.enabled=false"
        })
class AccountServiceTest {
}
```

If `test-defaults.properties` sets `app.timeout=20`, the value `30` in `properties` takes precedence. This is a convenient way for each test class to override a few values without creating extra separate configuration files.

Inline properties can use `key=value` or `key:value` form. Keep key names consistent with application configuration and avoid putting real secrets into source code or committed test files.

### 4.3. @DynamicPropertySource has the highest precedence among test sources

`@DynamicPropertySource` allows registering properties whose values are supplied by a `Supplier`. This mechanism is especially useful when a test needs the address, port, or temporary credentials of an external resource, such as Testcontainers.

```java
@SpringJUnitConfig(ExternalServiceTestConfiguration.class)
class ExternalServiceIntegrationTest {

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("service.base-url", () -> "http://localhost:18080");
        registry.add("service.timeout", () -> "5s");
    }
}
```

Spring invokes the supplier when the property value is resolved, rather than forcing all values to be computed immediately upon registration. Therefore, the supplier can read a port dynamically assigned after a container has started.

Illustrative example with Testcontainers:

```java
@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

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

This example uses Spring TestContext APIs together with Testcontainers; the project needs to declare the corresponding Testcontainers dependencies and lifecycle configuration. `@DynamicPropertySource` has higher precedence than `@TestPropertySource`, system properties, system environment, and application `@PropertySource`s. Consequently, the URL provided by the container can override fixed URLs in configuration files.

Methods annotated with `@DynamicPropertySource` must be `static`, accept a `DynamicPropertyRegistry`, and register keys with `registry.add(name, supplier)`. The key name must match the key read by the application.

### 4.4. Combined example with multiple sources declaring the same key

Suppose the application has an `application-defaults.properties` file:

```properties
app.mode=application
app.timeout=5
app.region=ap-southeast
```

A test-specific file `test-defaults.properties`:

```properties
app.mode=file
app.timeout=10
```

A test class declaring inline properties and a dynamic property:

```java
@SpringJUnitConfig(PropertyPrecedenceTest.TestConfiguration.class)
@TestPropertySource(
        locations = "classpath:/config/test-defaults.properties",
        properties = {
                "app.mode=inline",
                "app.timeout=20"
        })
class PropertyPrecedenceTest {

    @Configuration
    @PropertySource("classpath:/config/application-defaults.properties")
    static class TestConfiguration {
    }

    @Autowired
    private Environment environment;

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("app.mode", () -> "dynamic");
    }

    @Test
    void usesHighestPriorityValueForEachProperty() {
        assertEquals("dynamic", environment.getProperty("app.mode"));
        assertEquals("20", environment.getProperty("app.timeout"));
        assertEquals("ap-southeast", environment.getProperty("app.region"));
    }
}
```

The result is explained as follows:

| Key | Value in application file | Value in test file | Inline test value | Dynamic value | Value read |
|---|---|---|---|---|---|
| `app.mode` | `application` | `file` | `inline` | `dynamic` | `dynamic` |
| `app.timeout` | `5` | `10` | `20` | Not declared | `20` |
| `app.region` | `ap-southeast` | Not declared | Not declared | Not declared | `ap-southeast` |

The example shows precedence is evaluated independently per key. `app.mode` takes the dynamic value, while `app.timeout` takes the inline test value and `app.region` still comes from application configuration because no higher source overrides it.

## 5. Profiles and Property Sources Are Two Distinct Concepts

Profiles determine which configurations or beans are activated. Property sources determine which value is used when multiple sources supply the same key. The two mechanisms can work together, but they do not replace each other.

Example:

```java
@Configuration
@Profile("test")
public class TestMailConfiguration {

    @Bean
    MailGateway mailGateway() {
        return new InMemoryMailGateway();
    }
}
```

When the `test` profile is active, Spring can register `InMemoryMailGateway`. A profile does not automatically give every property in a file named `test` higher precedence. Profile-based file loading depends on application configuration; in Spring Boot, the `application-test.properties` mechanism belongs to Config Data.

### 5.1. Activating profiles for tests with @ActiveProfiles

Spring TestContext provides `@ActiveProfiles` to declare the profiles used when creating the `ApplicationContext` for a test:

```java
@SpringJUnitConfig(TestConfiguration.class)
@ActiveProfiles("test")
class AccountServiceTest {
}
```

Multiple profiles can be declared:

```java
@ActiveProfiles({"test", "stub-mail"})
class AccountServiceTest {
}
```

These profiles are used to evaluate `@Profile` conditions and bean configurations. If `@ActiveProfiles` is declared, Spring TestContext uses the declared profiles (and inherited profiles according to rules) instead of automatically picking up `spring.profiles.active` from system properties or environment variables. If custom profile selection logic is needed, you can implement `ActiveProfilesResolver` and declare it via the `resolver` attribute of `@ActiveProfiles`.

If `@ActiveProfiles` is not declared, the environment can obtain active profiles from `Environment` configuration, such as the `spring.profiles.active` system property, or use the default profile when no profile is activated.

### 5.2. Profile inheritance in a test class hierarchy

`@ActiveProfiles` inherits profiles from parent classes by default. Child classes can add profiles:

```java
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}

@ActiveProfiles("stub-mail")
class MailIntegrationTest extends BaseIntegrationTest {
}
```

With default inheritance configuration, the child class can use both `test` and `stub-mail`. If `inheritProfiles = false` is set, profiles declared on the parent class are not inherited. Understand this choice clearly to avoid a test accidentally running with production beans or missing required mock beans.

### 5.3. Inheriting @TestPropertySource

`@TestPropertySource` also supports inheritance from parent classes. By default, `locations` and inline `properties` are inherited; values on the child class can supplement or override according to the constructed source order.

Inheritance can be disabled independently for resources and inline properties:

```java
@TestPropertySource(
        locations = "classpath:/config/base-test.properties",
        properties = "app.region=base")
abstract class BaseServiceTest {
}

@TestPropertySource(
        locations = "classpath:/config/special-test.properties",
        inheritLocations = false,
        properties = "app.region=special",
        inheritProperties = false)
class SpecialServiceTest extends BaseServiceTest {
}
```

In this example, the child class does not receive resource `locations` or inline `properties` from the parent class. Use `inheritLocations = false` or `inheritProperties = false` only when you want to replace the corresponding configuration group; otherwise, default inheritance is usually more convenient for a test hierarchy.

## 6. Reading Properties with Environment, @Value, and Bean Configuration

After `Environment` is created and property sources are registered, the application can access values via several APIs.

### 6.1. Environment#getProperty

```java
@Component
public class FeatureSettings {

    private final Environment environment;

    public FeatureSettings(Environment environment) {
        this.environment = environment;
    }

    public boolean isFeatureEnabled() {
        return environment.getProperty(
                "app.feature.enabled", Boolean.class, false);
    }
}
```

The overload with a target type lets Spring convert the property string into a Java type. A default value can be passed if the key does not exist. Distinguish between the case where a key does not exist and the case where a key exists with an empty or unconvertible value.

### 6.2. @Value and placeholders

```java
@Component
public class RetrySettings {

    private final int maxAttempts;

    public RetrySettings(@Value("${app.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
```

The placeholder `${app.retry.max-attempts:3}` uses the key's value if found; if absent, the part after `:` is the default value. When multiple sources declare the same key, placeholder resolution uses the winning value according to `Environment` ordering.

In Spring Framework, placeholder resolution relies on a properly configured bean factory/configuration, typically via `PropertySourcesPlaceholderConfigurer` or an equivalent configuration mechanism. Spring Boot auto-configures much of this for Boot applications.

### 6.3. @ConfigurationProperties in Spring Boot

Spring Boot provides `@ConfigurationProperties` to bind a group of properties into a typed object:

```java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(int maxAttempts, Duration delay) {
}
```

Spring Boot's binder supports relaxed binding and type conversion according to Boot's rules. The final value is still influenced by the sources in `Environment` and the precedence order of Config Data/test sources. `@ConfigurationProperties` is a Spring Boot feature, not a core Spring Framework API.

## 7. Configuration Source Ordering in Spring Boot

When testing a Spring Boot application, distinguish general `Environment` rules from Boot's externalized configuration system. Boot adds sources such as Config Data, profile-specific files, command-line arguments, test annotation properties, and others. The exact ordering is defined by the Spring Boot version in use.

Common Boot sources include:

- Default properties declared on `SpringApplication`.
- `@PropertySource` on configuration classes.
- Config Data from `application.properties` or `application.yml` and profile-specific files.
- Random value property source.
- System properties and system environment.
- JNDI or servlet context parameters in corresponding environments.
- Command-line arguments.
- Test property sources such as `@SpringBootTest(properties = ...)`, `@TestPropertySource`, and `@DynamicPropertySource`.

These are categories of sources to recognize, not a complete precedence table. Boot has additional rules such as external files overriding classpath files, profile-specific files overriding non-profile files, and test sources having high priority. When a test depends on exact Boot precedence, consult the externalized configuration documentation for your exact Boot version and inspect `Environment#getPropertySources()` at runtime.

Do not assume that `application-test.properties` is always loaded automatically by plain Spring Framework just because `@ActiveProfiles("test")` is used. Automatic loading of profile-specific files is behavior of Spring Boot Config Data or must be configured separately in Spring Framework.

## 8. Testing Precedence Order in Tests

When writing configuration tests, verify the final value that a bean or component receives. If the goal is specifically to inspect property source ordering, you can read the source list in `Environment`.

### 8.1. Checking the effective value

```java
@SpringJUnitConfig(PropertyTestConfiguration.class)
@TestPropertySource(properties = "app.mode=test")
class EnvironmentPropertyTest {

    @Autowired
    private Environment environment;

    @Test
    void testPropertyOverridesApplicationDefault() {
        assertEquals("test", environment.getProperty("app.mode"));
    }
}
```

This test verifies the observable contract: the value a component reads from `Environment`. It depends less on internal property source names than directly asserting the position of a source in the list.

### 8.2. Observing which source provides a key

When diagnosing, you can iterate through the sources in exact order:

```java
ConfigurableEnvironment environment =
        (ConfigurableEnvironment) applicationContext.getEnvironment();

for (PropertySource<?> source : environment.getPropertySources()) {
    if (source.containsProperty("app.mode")) {
        System.out.println(source.getName() + " contains app.mode");
    }
}
```

The first source containing the key is the one preferred by the resolver. The snippet prints only the source name, not the value. In production logs, do not print values of all properties because they may contain passwords, tokens, connection strings, or sensitive information.

If you need to inspect values, do so only in tests with non-sensitive keys. Some Spring Boot environments also provide configuration diagnostic endpoints, but access must be restricted and comply with application security policies.

### 8.3. Checking conversion and default values

A property may be found yet fail to convert to the desired type. Tests should distinguish missing-key failures from conversion failures:

```java
@Test
void convertsPropertyToInteger() {
    assertEquals(30, environment.getProperty("app.timeout", Integer.class));
}

@Test
void usesDefaultWhenPropertyIsMissing() {
    assertEquals(5, environment.getProperty(
            "app.retry.max-attempts", Integer.class, 5));
}
```

If a property contains an invalid string such as `app.timeout=fast`, reading it as `Integer` can raise a conversion error. Do not test that scenario as if the key were missing; the two situations carry different configuration meanings.

## 9. Context Caching and Dynamic Properties

Spring TestContext has a mechanism to cache `ApplicationContext` instances to reduce initialization time between tests with identical configurations. Property sources and profiles are part of the configuration used to determine matching contexts.

`@DynamicPropertySource` is often declared on a parent class so multiple test classes share a resource, such as a container. However, if child classes inherit the same dynamic method yet the supplier returns different values per child class, the context cache may cause a context to be reused with unintended values.

In situations where dynamic properties genuinely differ and alter context configuration, `@DirtiesContext` may be needed to instruct TestContext to remove the context from the cache after the appropriate test. Do not add this annotation to every test; it reduces caching benefits and should only be used when a test alters context state or requires separating contexts by dynamic data.

With Testcontainers, ensure the container is ready before the supplier is used to create connections. Container lifecycle management must align with when Spring creates datasource or client beans. If the container stops while the context remains cached and reused, subsequent tests may fail even though the property source still holds the old URL.

## 10. Common Pitfalls When Configuring Multiple Sources

**Assuming a test file always beats every source.** `@DynamicPropertySource` has higher precedence than `@TestPropertySource`; inline properties also outrank resource `locations`. Identify the exact source type that is overriding.

**Confusing profiles with property source ordering.** `@ActiveProfiles("test")` selects configuration by profile; it does not automatically lift every property in a file to the top of the list. Determine which mechanism loads the file and where that source is placed.

**Confusing Spring Framework with Spring Boot Config Data.** `@PropertySource` and `Environment` belong to Spring Framework; automatic loading of `application-test.properties` by profile is Spring Boot behavior or requires separate configuration. Use the right documentation for the stack under test.

**Using `System.setProperty` and forgetting to restore.** System properties are JVM-wide state and can affect other tests. Save the old value, set the test value, and restore in `finally` or a state-managing extension.

**Expecting stable component-scan order.** Multiple configuration classes declaring `@PropertySource` may be processed in an order that does not match test assumptions. If order matters, configure it explicitly.

**Declaring the same key in multiple places without knowing which source wins.** Check `Environment#getProperty` and the names of sources containing the key in order. Avoid guessing based on filenames or when files were created.

**Not verifying the final value received by the bean.** A test verifying only that a property source exists does not prove placeholders, binders, or beans are configured properly. Assert the value at the point of use.

**Dynamic supplier depending on an unready resource.** If a supplier retrieves a container port or credential, ensure the resource is started before beans requiring the property are created.

**Putting secrets into inline test properties or logs.** Use dummy data in tests and do not print tokens, passwords, or URLs containing credentials in logs.

## 11. Workflow for Determining the Winning Source

When a property has an unexpected value, trace it through the following workflow:

1. Identify the exact key being read, such as `app.datasource.url`; do not confuse it with a similar key.
2. Identify how it is read: `Environment`, `@Value`, `@ConfigurationProperties`, or a custom application API.
3. Identify the environment type: plain Spring Framework or Spring Boot; MVC versus WebFlux does not change the first-match-wins principle but can change the set of registered sources.
4. Check active profiles and which configuration classes/beans were selected.
5. List the `PropertySource`s in their current order and identify the first source containing the key.
6. Check whether `@DynamicPropertySource`, inline `@TestPropertySource`, test resources, system properties, environment variables, and `@PropertySource` all declare the key.
7. Check conversion, placeholder defaults, and data types at the point of use.
8. If the context is cached, check whether the test is reusing a context with dynamic properties or global state from a previous test.
9. Write a test demonstrating the effective value the application must receive, while isolating system properties or external resources as needed.

## 12. Test Configuration Design Principles

To keep configuration understandable and minimize interference across tests:

- Use dedicated test files for groups of related values and name them clearly by purpose.
- Use inline `@TestPropertySource` for a few local override values.
- Use `@DynamicPropertySource` for addresses or details available only after test resources have started.
- Use `@ActiveProfiles` to select suitable beans/configurations for tests.
- Minimize modifying global system properties and environment; if unavoidable, always restore state.
- Do not put production secrets into test configuration files.
- Verify the final value at the bean or service requiring configuration.
- Use `@DirtiesContext` only when it is genuinely necessary to evict a context from the cache.

When you understand `Environment`, `PropertySource`, and Spring TestContext precedence rules, you can predict which value will be chosen when multiple sources declare the same key. Profiles help select configurations suited to the runtime context; property sources determine the effective value; and tests should verify the value the component actually receives. This forms the foundation for Spring test configurations that are stable, reproducible, and easy to diagnose when local, CI, or deployment environments supply different configuration sources.

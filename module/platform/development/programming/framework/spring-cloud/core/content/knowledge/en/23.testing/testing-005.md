# Testing PropertySource Ordering and Profiles

A Spring Cloud application often receives configuration from multiple places: `application.yml`, profile-specific files, environment variables, JVM system properties, command-line arguments, Config Server, and sources registered by the application itself. When running tests, Spring can also add values from `@SpringBootTest(properties)`, `@TestPropertySource`, or `@DynamicPropertySource`.

When multiple sources declare the same key, the application must determine which value wins and why. Testing `PropertySource` ordering catches unintended configuration overrides, verifies the right profiles are active, and ensures the test environment does not accidentally use endpoints, credentials, or resources from another environment.

This lesson belongs to the **Testing** chapter of the **SPRING_CLOUD_CORE** module. It focuses on Spring `Environment`, `PropertySource`, Spring Boot Config Data, profiles, test property sources, and verifying the final value actually received by beans. Examples use Spring Boot and Spring Test; always cross-check the Spring Boot/Spring Cloud versions in your project's BOM.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the relationship between `Environment`, `PropertySource`, and `PropertyResolver`.
2. Distinguish the precedence order documented in Spring Boot reference guides from the actual iteration order inside `Environment`.
3. Identify the source providing the final value of a property.
4. Test precedence across default files, profile-specific files, environment variables, system properties, and command-line arguments.
5. Use `@ActiveProfiles` to activate profiles in tests.
6. Use `@SpringBootTest(properties)`, `@TestPropertySource`, and `@DynamicPropertySource` for their intended purposes.
7. Inspect property sources added by Spring Cloud Config.
8. Recognize the impact of context caching and dynamic data across tests.
9. Write tests verifying both values in `Environment` and values bound into `@ConfigurationProperties`.
10. Diagnose bugs caused by wrong profiles, higher-priority sources, property sources inserted in the wrong position, or reused test configurations.

## 2. What Are `Environment` and `PropertySource`?

### 2.1. `Environment` Is the Configuration Access Point

Spring `Environment` represents the application's environment. It lets you read properties and inspect active profiles.

~~~java
@Component
class RegionResolver {

    private final Environment environment;

    RegionResolver(Environment environment) {
        this.environment = environment;
    }

    String currentRegion() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

`Environment` does not necessarily hold configuration values in a single file. It aggregates multiple sources and applies precedence rules when the same key appears multiple times.

Components commonly using this mechanism include:

- `Environment#getProperty(...)`.
- `@Value("${...}")`.
- `@ConfigurationProperties`.
- `Binder`.
- Property-based configuration conditions.
- Integrations that add configuration sources such as Spring Cloud Config.

### 2.2. `PropertySource` Represents a Single Source

`PropertySource` is an abstraction representing a source of key/value pairs. For example:

| Common property source | Data source |
| --- | --- |
| `systemEnvironment` | OS environment variables |
| `systemProperties` | JVM system properties |
| `applicationConfig: [...]` or corresponding Config Data source | Application properties/YAML files |
| `commandLineArgs` | `SpringApplication` command-line arguments |
| Test sources | Values added by the test framework |
| Config Server source | Property source from a remote configuration service |
| `MapPropertySource` | A `Map` added by the application or test |

Each source can contain the same key. Spring needs to know which source takes precedence to pick a value.

### 2.3. How Does `PropertyResolver` Look Up Values?

When calling:

~~~java
String region = environment.getProperty("app.region");
~~~

Spring iterates through property sources in the `Environment`'s priority order. The first source containing a matching value supplies the result. If a source does not contain the key or the value is treated as absent, the resolver continues searching subsequent sources.

Thus, a single application may have:

~~~text
application.yml       -> app.region=global
application-test.yml  -> app.region=test
OS environment        -> APP_REGION=ci
Test property         -> app.region=mock
~~~

The final value depends on which source has higher precedence in the running context.

### 2.4. Ordering in `MutablePropertySources`

`ConfigurableEnvironment` provides `MutablePropertySources` to add, remove, or reorder sources:

~~~java
MutablePropertySources sources =
        configurableEnvironment.getPropertySources();

sources.addFirst(new MapPropertySource(
        "test-high",
        Map.of("app.region", "test")
));

sources.addLast(new MapPropertySource(
        "test-low",
        Map.of("app.region", "fallback")
));
~~~

Key rules:

- `addFirst(...)`: adds a source at high priority.
- `addLast(...)`: adds a source at low priority.
- `addBefore(name, source)`: adds before an existing source.
- `addAfter(name, source)`: adds after an existing source.
- `replace(name, source)`: replaces an existing source with the same name.
- `remove(name)`: removes a source by name.

When `PropertySourcesPropertyResolver` iterates the collection, sources appearing earlier are checked first. Therefore, when inspecting `Environment#getPropertySources()`, understand the actual iterator order; do not mechanically copy the ordering list from Spring Boot documentation, because Boot documentation typically presents sources from lowest to highest precedence.

## 3. Inspecting the Winning Source in Environment

### 3.1. Reading the Final Value

The simplest approach is reading the property directly:

~~~java
String value = environment.getProperty("app.region");
~~~

This is the value that components using the same `Environment` can resolve at check time. With `@ConfigurationProperties`, also inspect the bound object if you want to verify the binding step.

### 3.2. Listing the Source Containing a Key

You can iterate property sources to find the first one containing a key:

~~~java
void logWinningSource(
        ConfigurableEnvironment environment,
        String propertyName
) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        if (source.containsProperty(propertyName)) {
            log.info(
                    "Property {} is supplied by source {}",
                    propertyName,
                    source.getName()
            );
            return;
        }
    }
}
~~~

This example only logs the source name, not the value. In production, never log password, token, or secret values.

When iterating in the actual order of `PropertySources`, the first source containing the key is the winning source for normal resolution. If the property has placeholders or is transformed by post-processors, the final resolved value may depend on additional processing steps.

### 3.3. Printing an Entire PropertySource Can Leak Data

Some property sources contain passwords, tokens, private keys, or URLs with credentials. When debugging, only log:

- The property name being investigated.
- The property source name.
- Active profiles.
- Non-sensitive configuration revision or label.
- Whether a value is present or absent.

Never print `source.getSource()` or dump the entire `Environment` to logs.

### 3.4. `@PropertySource` Has Timing Limitations

`@PropertySource` on a `@Configuration` class is added to the Environment during context refresh. Some properties such as `logging.*` or `spring.main.*` are already read before that point. Therefore, do not use `@PropertySource` to supply configuration needed very early in startup.

For standard application configuration, prefer Spring Boot Config Data (`application.properties`, `application.yml`, `spring.config.import`) instead of adding late sources manually.

## 4. Spring Boot PropertySource Precedence

### 4.1. General Overview List

Current Spring Boot documentation lists sources from lowest to highest precedence; a source appearing later can override an earlier source.

A common list in the Spring Boot 4.1 reference is:

| Order | Source | Notes |
| ---: | --- | --- |
| 1 | Default properties | `SpringApplication.setDefaultProperties(...)` |
| 2 | `@PropertySource` | Added during context refresh |
| 3 | Config Data | `application.properties`, YAML, and imported data |
| 4 | `RandomValuePropertySource` | `random.*` keys |
| 5 | OS environment variables | Environment variables |
| 6 | Java system properties | `System.getProperties()` |
| 7 | JNDI | `java:comp/env` |
| 8 | `ServletContext` init parameters | Servlet applications |
| 9 | `ServletConfig` init parameters | Servlet applications |
| 10 | `SPRING_APPLICATION_JSON` | Embedded JSON in environment or system property |
| 11 | Command line arguments | e.g., `--app.region=cli` |
| 12 | `@SpringBootTest(properties)` | Properties declared on test annotation |
| 13 | `@DynamicPropertySource` | Dynamic values in Spring TestContext |
| 14 | `@TestPropertySource` | Test properties from file or inline |
| 15 | Devtools global settings | When DevTools is enabled |

This list must be read against your exact Spring Boot version. Do not assume older Spring Boot versions have the exact same set of sources or identical ordering.

### 4.2. Command Line Typically Overrides Config Files

Example file:

~~~yaml
app:
  region: file
~~~

Running the application:

~~~bash
java -jar app.jar --app.region=command-line
~~~

When command-line properties are added to the Environment by default, `app.region` evaluates to `command-line`. You can disable command-line properties via `SpringApplication.setAddCommandLineProperties(false)`.

### 4.3. Environment Variables and System Properties

Example:

~~~bash
APP_REGION=environment java -jar app.jar
~~~

Or:

~~~bash
java -Dapp.region=system-property -jar app.jar
~~~

Environment variable names are mapped using relaxed binding rules; for example, `app.region` typically maps to `APP_REGION`.

In the Spring Boot list above, Java system properties appear after OS environment variables, so they have higher precedence. However, test runners, container runtimes, or CI may inject additional sources. Always inspect the live `Environment` rather than inferring from the launch command alone.

### 4.4. `SPRING_APPLICATION_JSON`

You can pass a group of properties as JSON:

~~~bash
SPRING_APPLICATION_JSON='{"app":{"region":"json","timeout":"2s"}}' java -jar app.jar
~~~

The JSON is parsed and added to the Environment. A `null` value in JSON is treated as missing when the resolver looks up a property, so do not use `null` to delete or override a value from a lower-priority source.

## 5. Config Data and Application File Ordering

### 5.1. Default Config Locations

Spring Boot automatically searches for `application.properties`, `application.yaml`, or `application.yml` in default locations such as:

- Classpath root.
- `classpath:/config/`.
- Current working directory.
- `./config/`.
- Direct subdirectories of `./config/`.

Locations are processed in priority order. A source processed later can override an earlier one for the same key.

### 5.2. Packaged Files vs. External Files

Current Spring Boot documentation describes Config Data ordering broadly as:

1. `application.properties` packaged inside the JAR.
2. `application-{profile}.properties` packaged inside the JAR.
3. `application.properties` outside the JAR.
4. `application-{profile}.properties` outside the JAR.

YAML variants follow the corresponding rules. Profile-specific files can override non-profile-specific files; external files can override packaged data.

Example:

~~~text
classpath:/application.yml
classpath:/application-test.yml
file:./config/application.yml
file:./config/application-test.yml
~~~

If all declare `app.region`, the value from the highest-priority source is chosen.

### 5.3. `spring.config.location` and `spring.config.additional-location`

These two properties serve different purposes:

- `spring.config.location`: replaces the default search locations.
- `spring.config.additional-location`: adds new locations after the default locations so values there can override default configuration.

Example:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./deploy-config/
~~~

The `optional:` prefix allows the application to proceed if the location does not exist. When the location is a directory, a trailing `/` is usually required.

`spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are read very early; supply them via environment variable, system property, or command line rather than only placing them inside the file the application needs to locate.

### 5.4. `spring.config.import`

Config Data can import other sources:

~~~yaml
spring:
  config:
    import: optional:file:./extra.yml
~~~

Values from an imported file can have higher priority than the file declaring the import. When a property appears in multiple files, check import order and location order rather than only line order in YAML.

### 5.5. Properties and YAML in the Same Location

If the same location contains both `application.properties` and `application.yaml`, Spring Boot prioritizes `.properties`. To reduce confusion, standardize on one format per configuration group.

## 6. Profiles and Profile-Specific Files

### 6.1. What Is a Profile?

Profiles allow activating configuration or beans tailored to a specific environment or execution purpose.

Examples:

- `local`: running on a developer workstation.
- `test`: automated testing.
- `staging`: pre-production environment.
- `prod`: production.

Profiles affect both Config Data and beans annotated with `@Profile`.

### 6.2. `application-{profile}.yml` Files

Suppose there are two files:

~~~yaml
# application.yml
app:
  region: global
  timeout: 5s
~~~

~~~yaml
# application-test.yml
app:
  region: test
  timeout: 2s
~~~

When the `test` profile is active, `application-test.yml` is loaded and matching keys can override values in the default file.

Tests can declare:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ApplicationProfileTest {
    // assertions
}
~~~

### 6.3. Activating Multiple Profiles

Multiple profiles can be activated:

~~~properties
spring.profiles.active=staging,cloud
~~~

If both `application-staging.yml` and `application-cloud.yml` define a key, profiles processed later can override earlier ones. Spring Boot documentation describes a last-wins strategy for profile lists.

Example:

~~~yaml
# application-staging.yml
app:
  region: staging
~~~

~~~yaml
# application-cloud.yml
app:
  region: cloud
~~~

With profile order `staging,cloud`, `app.region` evaluates to `cloud` if both files are loaded and no higher-priority source overrides it.

### 6.4. Default Profile

If no profile is active, Spring `Environment` uses the default profile, named `default` by default. Thus, `application-default.yml` may be considered when no specific profile is active.

You can rename the default profile using `spring.profiles.default`. Do not confuse the default profile with a profile that is always appended to every active profile.

### 6.5. Activating Documents in YAML

A single YAML file can hold multiple documents separated by `---`:

~~~yaml
app:
  region: global
---
spring:
  config:
    activate:
      on-profile: test
app:
  region: test
---
spring:
  config:
    activate:
      on-profile: prod
app:
  region: production
~~~

The second document activates only when the `test` profile matches; the third activates only when `prod` matches.

This is a Config Data document activation condition. It differs from `@Profile` on beans.

### 6.6. Do Not Put `spring.profiles.active` Inside Profile-Specific Documents

`spring.profiles.active` and certain profile-control properties must be declared in non-profile-specific documents. Do not use a profile-specific document to activate other profiles in unsupported ways.

If you need profile groups or profile includes, use the profile group/include properties per your Spring Boot version's documentation.

## 7. `@Profile` on Beans vs. Profiles in Config Data

Two concepts are frequently confused:

| Mechanism | Effect |
| --- | --- |
| `application-test.yml` | Loads property source when `test` profile is active |
| `spring.config.activate.on-profile` | Activates a Config Data document based on a profile expression |
| `@Profile("test")` | Registers a bean or configuration only when the profile matches |
| `@ActiveProfiles("test")` | Specifies profiles for the ApplicationContext loaded by Spring TestContext |

Example:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("test")
class TestClientConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

This bean is created only when the `test` profile is active. It does not load `application-test.yml` by itself; file loading is performed by Config Data based on active profiles.

## 8. Spring Cloud Config and Remote PropertySources

### 8.1. Config Server Is a Remote Configuration Source

A Config Client can fetch property sources from Spring Cloud Config Server. With Config Data, import configuration typically looks like:

~~~yaml
spring:
  config:
    import: optional:configserver:
~~~

If you omit `optional:`, the client can fail startup when Config Server is unreachable. You can specify the URL in the import string or via `spring.cloud.config.uri` as documented.

### 8.2. Config Client May Send Multiple Requests at Startup

With Config Data, Spring Boot/Config Client may execute two steps:

1. Fetch configuration with the `default` profile to discover properties that might activate additional profiles.
2. Once active profiles are determined, fetch configuration for those profiles.

Therefore, seeing multiple requests to Config Server during startup is not necessarily a bug. When testing, verify the application name, profiles, and label sent by the client.

### 8.3. Property Source Ordering from Config Server

Config Server can return property sources in order, for example:

1. `application.properties`.
2. `application-prod.properties`.
3. `orders-service.properties`.
4. `orders-service-prod.properties`.

Sources returned later can override earlier ones. If `spring.cloud.config.name` lists multiple configuration names, their order in the list also matters; names appearing later can override earlier names when declaring the same key.

### 8.4. Testing by Label/Revision

`spring.cloud.config.label` can select a branch, tag, or commit used by Config Server depending on the backend. In integration tests, use a dedicated label or fixed revision so results do not change when the configuration repository is updated concurrently.

Never let tests read a production label or a continuously changing branch if the goal is repeatable results.

### 8.5. Legacy Bootstrap and Config Data Differ

Spring Boot 2.4+ made Config Data import the default way to connect to Config Server. The legacy bootstrap mechanism still exists in some projects and has its own ordering/override semantics.

In bootstrap mode, remote property sources can take higher default precedence than local configuration. Properties such as:

- `spring.cloud.config.allow-override`
- `spring.cloud.config.override-none`
- `spring.cloud.config.override-system-properties`

govern how remote property sources are ordered in bootstrap mode. Permission to allow overrides must be granted from the Config Server configuration source per Spring Cloud Config documentation; do not assume setting `allow-override` only on the local client suffices.

These properties should not be copied into Config Data mode without checking the corresponding documentation. When testing, clearly establish whether the application uses `spring.config.import=configserver:` or legacy bootstrap before asserting remote/local ordering.

## 9. Test Property Sources in Spring Test

### 9.1. Why Do Tests Need Separate Property Sources?

Tests often need to swap endpoints, ports, mock credentials, feature flags, or timeouts without changing application configuration. Spring Test offers several ways to add properties:

- `@SpringBootTest(properties = "...")`.
- `@TestPropertySource`.
- `@DynamicPropertySource`.
- `@ActiveProfiles`.
- `ApplicationContextInitializer`.
- `TestPropertyValues` or `ApplicationContextRunner` in small tests.

Choose the tool based on the kind of data. Static values fit inline properties; values known only after a container starts fit dynamic properties.

### 9.2. `@SpringBootTest(properties)`

Example:

~~~java
@SpringBootTest(properties = {
        "app.region=from-spring-boot-test",
        "app.timeout=750ms"
})
class ClientConfigurationTest {
}
~~~

These values are added to the test context's Environment and can override normal application configuration. This is concise for a few fixed properties used only in that test.

### 9.3. `@TestPropertySource`

You can specify a file:

~~~java
@SpringBootTest
@TestPropertySource(locations = "classpath:/test-config.properties")
class ClientConfigurationTest {
}
~~~

Or declare inline properties directly:

~~~java
@SpringBootTest
@TestPropertySource(properties = {
        "app.region=from-test-property-source",
        "app.timeout=500ms"
})
class ClientConfigurationTest {
}
~~~

If the same annotation declares both `locations` and `properties`, inline values take precedence over values read from resource locations.

`@TestPropertySource` supports traditional `.properties` and XML files by default. With Spring Framework 6.1+, you can use a custom `PropertySourceFactory` to support other formats like YAML or JSON. Do not assume `@TestPropertySource("application-test.yml")` is automatically parsed like Spring Boot Config Data unless an appropriate factory is configured.

### 9.4. `@DynamicPropertySource`

When a property depends on a resource whose address is known only at runtime, use `@DynamicPropertySource`. The classic case is Testcontainers assigning random hosts and ports.

~~~java
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
~~~

The annotated method must be `static` and accept a `DynamicPropertyRegistry`. Each property is registered with a `Supplier`; the supplier is invoked only when the value is resolved.

Do not hard-code a container's random port before the container starts. Use method references like `postgres::getJdbcUrl` so values are fetched from the running container.

### 9.5. Note on DynamicPropertySource and TestPropertySource Ordering

Current Spring Framework TestContext documentation explicitly states that properties from `@DynamicPropertySource` have higher precedence than properties from `@TestPropertySource`.

However, the summary list on Spring Boot 4.1.2's Externalized Configuration page lists `@DynamicPropertySource` before `@TestPropertySource` in a sequence that page describes as later sources overriding earlier ones. This presentation is inconsistent with the Spring Framework TestContext precedence section.

When both annotations declare the same key, do not rely on a single summary table to conclude behavior across all combinations and versions. Write a small test reading `Environment#getProperty(...)` and checking the winning source on the exact Spring Boot/Spring Framework version your project uses. For dynamic data from Testcontainers, use `@DynamicPropertySource` because that is what the API is designed for.

### 9.6. Inline Property and File Ordering in `@TestPropertySource`

Example:

~~~java
@SpringBootTest
@TestPropertySource(
        locations = "classpath:/test-defaults.properties",
        properties = {
                "app.region=inline-value"
        }
)
class TestPropertySourceOrderTest {
}
~~~

If `test-defaults.properties` also declares `app.region`, the inline value `inline-value` wins. When multiple repeatable `@TestPropertySource` annotations exist, direct declarations and annotation merging order follow specific rules; avoid stacking multiple nested layers of annotations unnecessarily.

## 10. Testing Profiles with `@ActiveProfiles`

### 10.1. Activating Profiles in Tests

`@ActiveProfiles` declares profiles for the ApplicationContext loaded by Spring TestContext:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class TestProfileConfigurationTest {
}
~~~

Spring Boot loads Config Data matching the `test` profile, such as `application-test.yml`. Beans annotated with `@Profile("test")` can also be registered.

### 10.2. Multiple Profiles and Ordering

~~~java
@SpringBootTest
@ActiveProfiles({"staging", "cloud"})
class MultiProfileConfigurationTest {
}
~~~

When both profiles have configuration files defining the same property, the profile processed later can override the earlier one. Verify both the active profiles list and the final property value.

### 10.3. `@ActiveProfiles` and `spring.profiles.active`

When a test class uses `@ActiveProfiles`, Spring TestContext does not use `spring.profiles.active` from environment variables or JVM system properties to determine active profiles. If you want system properties/environment variables to decide, you need a custom `ActiveProfilesResolver`.

This is crucial in CI: a `SPRING_PROFILES_ACTIVE=prod` variable on the runner will not automatically make a test annotated with `@ActiveProfiles("test")` run with the `prod` profile. Conversely, do not omit `@ActiveProfiles` when a test needs a deterministic, safe profile.

### 10.4. Profile Inheritance

`@ActiveProfiles` can be inherited from a superclass or enclosing class. By default, profiles are inherited. Use `inheritProfiles = false` when a subclass test needs to replace the parent class's entire profile list.

~~~java
@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

@SpringBootTest
@ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false
)
class IsolatedConfigurationTest extends BaseIntegrationTest {
}
~~~

Do not let a base class accidentally add `prod` or an inappropriate profile into child tests.

## 11. Testing Combined Profiles and Test Overrides

### 11.1. Example Configuration Files

`application.yml`:

~~~yaml
app:
  region: global
  timeout: 5s
  client:
    endpoint: https://default.example.internal
~~~

`application-test.yml`:

~~~yaml
app:
  region: test-profile
  timeout: 2s
  client:
    endpoint: http://localhost:18080
~~~

Test:

~~~java
@SpringBootTest(properties = "app.region=spring-boot-test")
@ActiveProfiles("test")
class ProfileAndTestOverrideTest {

    @Autowired
    Environment environment;

    @Test
    void testPropertyOverridesProfileConfiguration() {
        assertThat(environment.getActiveProfiles())
                .containsExactly("test");

        assertThat(environment.getProperty("app.region"))
                .isEqualTo("spring-boot-test");

        assertThat(environment.getProperty("app.timeout"))
                .isEqualTo("2s");
    }
}
~~~

The test confirms:

- `@ActiveProfiles("test")` activates the profile file.
- `app.timeout` comes from the `test` profile.
- `app.region` is overridden by `@SpringBootTest(properties)`.

### 11.2. Also Inspect the Bound Bean

Suppose we have:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        String region,
        Duration timeout
) {
}
~~~

Register the type with `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`. Then test both `Environment` and the bean:

~~~java
@Autowired
AppProperties properties;

@Test
void boundPropertiesUseTheWinningValues() {
    assertThat(properties.region()).isEqualTo("spring-boot-test");
    assertThat(properties.timeout()).isEqualTo(Duration.ofSeconds(2));
}
~~~

This distinguishes failures at the property resolution stage from failures at the binding or conversion stage.

## 12. Verifying Order with a Concrete PropertySource Test

### 12.1. Adding Two MapPropertySources with Overlapping Values

Example using `ApplicationContextRunner`:

~~~java
class PropertySourceOrderTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withInitializer(context -> {
                        MutablePropertySources sources =
                                context.getEnvironment().getPropertySources();

                        sources.addLast(new MapPropertySource(
                                "test-low",
                                Map.of("app.region", "low")
                        ));

                        sources.addFirst(new MapPropertySource(
                                "test-high",
                                Map.of("app.region", "high")
                        ));
                    });

    @Test
    void firstPropertySourceWins() {
        runner.run(context -> {
            Environment environment = context.getEnvironment();

            assertThat(environment.getProperty("app.region"))
                    .isEqualTo("high");
        });
    }
}
~~~

This test confirms the `MutablePropertySources` rule: a source added with `addFirst` has higher priority than one added with `addLast`.

### 12.2. Asserting the Winning Source Name

You can extend the test to identify the source name:

~~~java
String winningSource = StreamSupport.stream(
        environment.getPropertySources().spliterator(),
        false
)
.filter(source -> source.containsProperty("app.region"))
.map(PropertySource::getName)
.findFirst()
.orElseThrow();

assertThat(winningSource).isEqualTo("test-high");
~~~

This snippet uses the iterator order of `PropertySources`, so the first source containing the key is the winner. Use only non-sensitive test properties.

### 12.3. When Real Config Data Needs Testing

`ApplicationContextRunner` is great for small configuration tests, but it does not automatically simulate full Config Data startup like `SpringApplication`. If the goal is testing `application.yml`, profile files, `spring.config.import`, or Config Server, use `@SpringBootTest` or a test running with the appropriate Config Data loader.

Do not conclude Config Data ordering from a unit test that merely adds `MapPropertySource`.

## 13. Testing Multiple Profiles with Integration Tests

### 13.1. Confirming Active Profiles

~~~java
@SpringBootTest
@ActiveProfiles({"test", "cloud"})
class ActiveProfileOrderTest {

    @Autowired
    Environment environment;

    @Test
    void expectedProfilesAreActive() {
        assertThat(environment.getActiveProfiles())
                .containsExactly("test", "cloud");
    }
}
~~~

If profile ordering matters for files defining the same key, assert exact order rather than merely checking that the profile names are present.

### 13.2. Confirming Last-Wins Values

Suppose `application-test.yml` has:

~~~yaml
app:
  region: test
~~~

and `application-cloud.yml` has:

~~~yaml
app:
  region: cloud
~~~

Test:

~~~java
assertThat(environment.getProperty("app.region"))
        .isEqualTo("cloud");
~~~

If the test fails, check:

- Is `@ActiveProfiles` in the right order?
- Is the profile actually active?
- Is an external file outside the JAR or another import overriding it?
- Is an environment variable, system property, or test property taking higher precedence?
- Has a Config Server property source been added?

### 13.3. Checking Profile-Specific Beans

You can use `ApplicationContext` to verify the expected beans are created:

~~~java
assertThat(context).hasBean("testPaymentGateway");
assertThat(context).doesNotHaveBean("productionPaymentGateway");
~~~

Do not rely solely on `Environment#getActiveProfiles()`: a bean can fail to be created due to other conditions, missing dependencies, or component scanning not finding the configuration.

## 14. Testcontainers and Dynamic Properties

### 14.1. Never Guess Container Ports

Testcontainers typically maps container ports to random host ports. Therefore, never hard-code:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/testdb
~~~

unless the test environment genuinely pins that port.

Use `@DynamicPropertySource` to register runtime values:

~~~java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

### 14.2. Suppliers Are Invoked When Properties Are Resolved

`registry.add("key", supplier)` does not necessarily call the supplier at registration time. Values are fetched when the resolver requests the property. This enables using addresses/ports after the container has started.

Suppliers must read the current state of the resource. Avoid side effects or returning different values on each invocation if the property must remain stable throughout the context lifecycle.

### 14.3. Dynamic Properties Changing Across Test Classes

If `@DynamicPropertySource` is placed in a base class and subclasses use different resources, the context cache might reuse a context that no longer matches the new suppliers.

If dynamic properties change across subclasses, consider `@DirtiesContext` to force a new context or design each test group with distinct context keys. Never use a static mutable map to swap endpoints between tests sharing the same ApplicationContext.

## 15. Context Caching and Test Isolation

### 15.1. Why Can Tests Reuse a Context?

Spring TestContext caches `ApplicationContext` instances when the corresponding test configurations match. Reuse speeds up the suite, but it also means bean state and Environment state can persist across multiple test methods.

Factors contributing to the context cache key include:

- Configuration classes.
- Context initializers.
- Active profiles.
- Test property source locations and inline properties.
- Context customizers.
- Dynamic property methods.
- Web environment and related test attributes.

### 15.2. Never Mutate a System Property in a Test Without Restoring It

Bad example:

~~~java
System.setProperty("app.region", "temporary");
~~~

If other tests run in the same JVM, the system property can linger and alter their results. If you must modify a system property, restore it in a `finally` block or use a test framework utility that manages properties.

Never rely on test execution order to hide configuration leakage.

### 15.3. When to Use `@DirtiesContext`?

`@DirtiesContext` marks the context as modified and removes it from the cache according to the specified scope. Use it when a test genuinely mutates context state that cannot be safely restored or when dynamic configuration differs across test classes.

Do not add `@DirtiesContext` to every test. It increases context creation time and can mask poor test design that shares mutable state.

### 15.4. Splitting Tests by Goal

A maintainable structure:

| Test type | Goal |
| --- | --- |
| Unit test | Verify logic using a specific property |
| `ApplicationContextRunner` test | Verify small binding/conditional configurations |
| `@SpringBootTest` | Verify Config Data, profiles, and full wiring |
| Integration test with Testcontainers | Verify dynamic properties from live resources |
| Config Server integration test | Verify remote property sources, labels, and profiles |

You do not need to boot the entire application for a simple check of `MapPropertySource.addFirst()`.

## 16. Testing Property Ordering with Config Server

### 16.1. Identify the Client Mode

Before writing tests, determine what the Config Client uses:

- Config Data import: `spring.config.import=configserver:`.
- Legacy bootstrap: bootstrap context enabled by starter or corresponding properties.

The two modes have different lifecycles and override behaviors. Do not mix legacy bootstrap tests with Config Data tests and expect identical outcomes.

### 16.2. Verify Application/Profile/Label

A Config Client can request configuration by:

- `spring.application.name` or `spring.cloud.config.name`.
- Active profiles.
- `spring.cloud.config.label`.

If a test reads the wrong application name or label, the returned value may look valid yet come from an unintended property source.

### 16.3. Testing Remote Sources with a Fixed Revision

An integration test should:

1. Start a test Config Server or point to an isolated server.
2. Specify the application name and profile clearly.
3. Choose a stable label/commit.
4. Provide a key with distinct remote and local values.
5. Start the Config Client.
6. Check `Environment#getProperty`.
7. Check the winning property source name.
8. Confirm there is no unintended fallback.

Never use a production Config Server to test overrides or property mutations. Use an isolated fixture/test repository.

### 16.4. Testing `allowOverride` and Legacy Bootstrap

In legacy bootstrap mode, properties like `spring.cloud.config.allow-override`, `spring.cloud.config.override-none`, and `spring.cloud.config.override-system-properties` affect how remote property sources are placed into the Environment.

Per Spring Cloud documentation, override permission must be granted from the remote environment repository. When testing, configure the remote fixture with explicit values and verify whether local properties win. Do not assume a local variable can always override a remote Config Server in every setup.

## 17. Diagnosing with Actuator and Environment

### 17.1. The `env` Endpoint

Spring Boot Actuator provides the `env` endpoint to inspect the Environment and property sources. It is helpful when a property has an unexpected value.

If enabled in a managed environment, restrict access and mask sensitive data. Do not expose `env` publicly just for debugging.

### 17.2. The `configprops` Endpoint

`configprops` lets you inspect `@ConfigurationProperties` beans and bound values. It helps when:

- `Environment#getProperty` is correct, yet the bean has a different value.
- Conversion or validation behaves unexpectedly.
- Prefix or field names do not match.
- The bean is not registered or bound.

### 17.3. Checking Across Two Layers

When a test fails, check in sequence:

1. `Environment#getProperty("app.region")`: what is the final resolved value?
2. Which source provides the value?
3. `Environment#getActiveProfiles()`: which profiles are active?
4. `@ConfigurationProperties` bean: what is the post-binding value?
5. Was the bean/client created before a property source was added?
6. Is the test reusing an `ApplicationContext` cache?

This separates source precedence bugs from binding bugs and lifecycle bugs.

## 18. Common Pitfalls

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `application-test.yml` is not loaded | `test` profile not active or file in wrong location | Check `@ActiveProfiles`, filename, and Config Data locations |
| Profile value does not win | Overridden by a higher-priority source | Inspect property sources and check env/system/CLI/test overrides |
| Test accidentally uses production profile | Missing `@ActiveProfiles` or custom resolver picked wrong profile | Check active profiles and CI environment |
| `@ActiveProfiles` ignores `SPRING_PROFILES_ACTIVE` | Annotation controls TestContext profiles | Use `ActiveProfilesResolver` if external override is desired |
| `@TestPropertySource` fails to read YAML | Default loader does not parse YAML | Use `.properties` or a custom `PropertySourceFactory` |
| Testcontainers value stays old localhost | Hard-coded property or dynamic property not registered | Use `@DynamicPropertySource` and container suppliers |
| Test A leaks unexpected property to Test B | Shared system property/static state or context cache | Restore state, separate contexts, or use `@DirtiesContext` when needed |
| Remote Config Server source beats local | Remote source precedence or bootstrap override policy | Identify Config Data/legacy bootstrap mode and override flags |
| `@ConfigurationProperties` bean mismatches Environment | Binding/conversion/registration issue | Check prefix, type, binder, and bean registration |
| `@PropertySource` fails to control `spring.main.*` | Source added too late in lifecycle | Use Config Data or an early-loaded source |
| Test `MapPropertySource` does not win | Used `addLast` or added after a higher-priority source | Use `addFirst` or insert at the right position |
| Test passes alone but fails in suite | Context cache, global state, or test order dependency | Remove shared state and verify isolation |
| `null` property fails to override another source | Resolver treats null as absent property | Use a sentinel value or appropriate remove/override mechanism |

## 19. Property Source Test Design Checklist

Before concluding configuration precedence is correct, verify:

- [ ] Tests use the target Spring Boot/Spring Cloud versions.
- [ ] Active profiles are correct and in the right order.
- [ ] `application-{profile}.yml` files reside in locations discovered by Config Data.
- [ ] Locations/imports are processed in the expected order.
- [ ] No environment variable or system property accidentally overrides values.
- [ ] No command-line arguments from the build/test runner interfere.
- [ ] `@SpringBootTest(properties)` contains only necessary overrides.
- [ ] `@TestPropertySource` uses a supported format.
- [ ] `@DynamicPropertySource` supplies values from running resources.
- [ ] Tests do not share contexts when dynamic properties change.
- [ ] Config Server tests use fixed application/profile/label values.
- [ ] Assertions check both Environment and bound beans when needed.
- [ ] Plaintext secrets or full property sources are never dumped to logs.
- [ ] Tests do not rely on execution order to produce correct results.

## 20. Practice Exercises

**Exercise 1 — Basic PropertySource.** Create two `MapPropertySource` instances both declaring `app.region`. Use `addFirst` and `addLast`, then verify the winning value with `Environment#getProperty`.

**Exercise 2 — Files and Profiles.** Create `application.yml`, `application-test.yml`, and `application-cloud.yml`. Activate the two profiles in two different orders and inspect the value of the overlapping key.

**Exercise 3 — External Sources.** Run the application with `APP_REGION`, `-Dapp.region`, and `--app.region`. Verify which source wins in your active Spring Boot version.

**Exercise 4 — `@SpringBootTest(properties)`.** Set one value in `application-test.yml` and another in `@SpringBootTest(properties)`. Inspect the final value and active profiles.

**Exercise 5 — `@TestPropertySource`.** Declare a `test-defaults.properties` file and an inline property with the same key. Prove that the inline value overrides the resource location.

**Exercise 6 — Dynamic Properties.** Use Testcontainers to start PostgreSQL and register URL/username/password via `@DynamicPropertySource`. Verify the `DataSource` bean connects to the container.

**Exercise 7 — Context Caching.** Create a base test class using dynamic properties, then two subclasses using different resources. Observe context reuse and test `@DirtiesContext` if needed.

**Exercise 8 — Config Server.** Create a remote fixture with keys overlapping local config. Choose a fixed profile and label, and inspect the winning property source in Config Data mode.

**Exercise 9 — Legacy Bootstrap.** For projects supporting legacy bootstrap, test the effects of `allow-override`, `override-none`, and `override-system-properties`. Note where the remote repository must grant override permission.

**Exercise 10 — Binding Diagnostics.** Create a `@ConfigurationProperties` bean with `Duration` and `DataSize`. Inspect Environment values, bound values, and errors when property sources contain invalid formats.

## 21. Takeaways and References

- `Environment` aggregates multiple `PropertySource`s; values are resolved according to the iteration order of sources in Environment.
- `MutablePropertySources.addFirst()` adds a high-priority source; `addLast()` adds a low-priority source.
- Spring Boot documentation presents sources from lowest to highest precedence; later sources can override earlier ones.
- Profile-specific files override non-profile-specific files; if multiple profiles declare the same key, later profiles can win.
- `@ActiveProfiles` controls active profiles in Spring TestContext; when present, system/environment `spring.profiles.active` does not automatically select profiles for the test.
- `@SpringBootTest(properties)` and `@TestPropertySource` fit static test values; `@DynamicPropertySource` is for dynamic values from runtime resources.
- Spring Framework documentation states `@DynamicPropertySource` has higher precedence than `@TestPropertySource`; the summary list in current Spring Boot documentation presents a different order. Verify the live Environment on your exact version.
- Config Server can add remote property sources; distinguish Config Data import from legacy bootstrap before concluding override precedence.
- Testcontainers typically requires `@DynamicPropertySource` to inject runtime hosts/ports into Environment.
- Context caching speeds up tests but requires care when dynamic properties vary across test classes.
- Inspect both `Environment` and `@ConfigurationProperties` beans to separate resolution bugs from binding bugs.

Official references to check against your project's Spring Boot/Spring Cloud versions:

1. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
2. [Spring Boot Reference – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
3. [Spring Framework Reference – Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
4. [Spring Framework Reference – Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
5. [Spring Framework Reference – Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
6. [Spring Framework Reference – Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
7. [Spring Cloud Config – Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html)
8. [Spring Cloud Config – Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html)
9. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
10. [Spring Cloud – Release train and Spring Boot compatibility](https://spring.io/projects/spring-cloud/)

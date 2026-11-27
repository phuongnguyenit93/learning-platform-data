# `Environment`, `ConfigurableEnvironment`, and `PropertySource`

In Spring, application configuration does not live solely in a single YAML or Properties file. When an application starts up, many different sources can provide the same property: files packaged in the JAR, external files, profiles, environment variables, JVM system properties, command-line arguments, test configuration, and remote configuration. Spring needs a unified mechanism to query these values and determine which source takes precedence.

This mechanism is expressed through three abstractions:

- **`Environment`**: the interface for reading properties and querying active profiles.
- **`ConfigurableEnvironment`**: the configurable version of `Environment` that manages profiles and the list of property sources.
- **`PropertySource`**: represents a source that supplies property values.

In the **SPRING_CLOUD_CORE** module, these abstractions form the foundation for understanding externalized configuration, Spring Cloud Config, discovery, service registry, and refresh. They allow integration libraries to supply configuration to a Spring Boot application in a uniform way, while business code can read values without needing to know whether a value comes from a file, an environment variable, or a config server.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain the roles of `Environment`, `ConfigurableEnvironment`, and `PropertySource`.
2. Read properties through `Environment` and handle cases where a key does not exist.
3. Distinguish between active profiles and default profiles, and use profile conditions.
4. Explain `PropertySource` precedence and how the first source containing a key determines the value.
5. Add or replace a property source in a controlled way via `MutablePropertySources`.
6. Understand how Spring Boot brings Config Data, environment variables, and command-line arguments into the Environment.
7. Distinguish between modifying the Environment and rebinding or refreshing running beans.
8. Test configuration and diagnose property value origins in a Spring Cloud application.

## 2. `Environment`: Interface for Reading Configuration and Profiles

`Environment` is a Spring Core abstraction that extends `PropertyResolver` and adds the ability to work with profiles. Application components can use it to read values without directly depending on a specific configuration file.

### 2.1. Reading Properties

Commonly used methods:

| Method | Meaning |
| --- | --- |
| `getProperty(key)` | Gets the value as a `String`; returns `null` if absent |
| `getProperty(key, defaultValue)` | Gets the value or uses the default value |
| `getProperty(key, targetType)` | Gets and converts the value to the target type |
| `getProperty(key, targetType, defaultValue)` | Converts the type or uses the default value |
| `getRequiredProperty(key)` | Reads a required property; throws an error if it does not exist |
| `containsProperty(key)` | Checks whether any source provides the key |
| `resolvePlaceholders(text)` | Substitutes placeholders; unresolved placeholders may be left as-is |
| `resolveRequiredPlaceholders(text)` | Substitutes placeholders and throws an error if any cannot be resolved |

For example, suppose the application has the following configuration:

~~~yaml
clients:
  inventory:
    base-url: https://inventory.internal.example
    read-timeout: 700ms
    enabled: true
~~~

These values can be read through `Environment`:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class InventoryEnvironmentProbe {
    private final Environment environment;

    public InventoryEnvironmentProbe(Environment environment) {
        this.environment = environment;
    }

    public void inspect() {
        URI baseUrl = environment.getProperty(
                "clients.inventory.base-url",
                URI.class
        );

        Duration timeout = environment.getProperty(
                "clients.inventory.read-timeout",
                Duration.class,
                Duration.ofMillis(500)
        );

        boolean enabled = environment.getProperty(
                "clients.inventory.enabled",
                Boolean.class,
                false
        );

        System.out.println("baseUrl = " + baseUrl);
        System.out.println("timeout = " + timeout);
        System.out.println("enabled = " + enabled);
    }
}
~~~

Spring uses the configured `PropertyResolver`/conversion service type conversion mechanism. Types such as `Duration`, `URI`, numbers, and booleans can be converted when an appropriate converter is available. If a key is required, you should use `getRequiredProperty` or binding with validation to detect errors right at initialization time.

### 2.2. Distinguishing Default Values and Required Values

Use a default value when the application has valid behavior even if the key is not configured:

~~~java
Duration timeout = environment.getProperty(
        "clients.inventory.read-timeout",
        Duration.class,
        Duration.ofMillis(700)
);
~~~

Use a required property when missing configuration must cause the application to fail fast:

~~~java
String registryEndpoint = environment.getRequiredProperty(
        "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri"
);
~~~

You should not turn every property into a required one. Classify them:

- **Required:** missing it prevents the application from safely serving business logic.
- **Valid default:** can run with a clearly chosen value.
- **Optional:** the feature can be disabled if not configured.
- **Sensitive:** needs to be retrieved from a secret store or secure source, avoiding logging.

Choosing a default value must be based on business needs. For example, a timeout that is too large can hold resources for too long, whereas a timeout that is too small can cause requests to fail unnecessarily.

### 2.3. Placeholders and Value Resolution

`PropertyResolver` also supports placeholder substitution:

~~~java
String endpoint = environment.resolveRequiredPlaceholders(
        "${clients.inventory.base-url}"
);
~~~

If the placeholder does not exist, `resolveRequiredPlaceholders` throws an error. This is suitable for required configuration. For optional placeholders, a default can be supplied directly in the expression where the configuration supports it:

~~~yaml
clients:
  inventory:
    base-url: "${INVENTORY_URL:http://localhost:8081}"
~~~

`Environment` is where values are read after sources have been combined. It is not a general-purpose template engine, nor does it automatically call Config Server just because a string contains a placeholder.

## 3. Profiles in Environment

A profile represents a group of configurations or beans that only apply in a specific context, such as `dev`, `test`, `staging`, or `prod`.

### 3.1. Active Profiles and Default Profiles

`Environment` provides:

- `getActiveProfiles()`: the list of currently active profiles.
- `getDefaultProfiles()`: the list of default profiles when no matching active profile is set.
- `acceptsProfiles(...)`: checks whether a profile expression is accepted.

Example:

~~~java
import java.util.Arrays;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ProfileProbe {
    ProfileProbe(Environment environment) {
        System.out.println("active profiles: "
                + Arrays.toString(environment.getActiveProfiles()));
        System.out.println("default profiles: "
                + Arrays.toString(environment.getDefaultProfiles()));
    }
}
~~~

If there are no active profiles, Spring typically uses the default profile named `default`, unless the application has configured different default profiles.

### 3.2. Profile Conditions

Profiles can be checked using `Profiles.of`:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

boolean isProduction = environment.acceptsProfiles(
        Profiles.of("prod")
);

boolean isProductionOrStaging = environment.acceptsProfiles(
        Profiles.of("prod", "staging")
);

boolean isProductionOnCloud = environment.acceptsProfiles(
        Profiles.of("prod & cloud")
);
~~~

In expressions:

- `&` represents an AND condition.
- `|` represents an OR condition.
- `!` represents negation.
- Parentheses can be used to group expressions.

Spring also allows using annotations:

~~~java
@Configuration
@Profile("prod")
class ProductionConfiguration {
    // Beans are only registered when the prod profile matches.
}
~~~

A profile is not a separate value source. It is a condition that affects which configurations are activated, which files are loaded, and which beans are registered.

### 3.3. Setting Profiles via ConfigurableEnvironment

`ConfigurableEnvironment` allows setting active or default profiles before the context refreshes:

~~~java
ConfigurableEnvironment environment = ...;

environment.setActiveProfiles("prod", "cloud");
environment.addActiveProfile("metrics");
environment.setDefaultProfiles("local");
~~~

Distinguish between:

- `setActiveProfiles(...)` replaces the list of active profiles configured via the API.
- `addActiveProfile(...)` appends a profile.
- `setDefaultProfiles(...)` replaces the list of default profiles.

Changing active profiles after the context has refreshed does not automatically re-register or remove beans that were created based on `@Profile`. Profile conditions are primarily evaluated during configuration/bean registration. Do not use runtime profile changes as a mechanism for dynamically toggling beans.

## 4. `ConfigurableEnvironment`: Managing the Environment

`ConfigurableEnvironment` extends `Environment` and `ConfigurablePropertyResolver`. It adds the ability to manage property sources, profiles, and several foundational properties of the environment.

Key capabilities:

| API | Role |
| --- | --- |
| `getPropertySources()` | Gets the mutable list of property sources |
| `getSystemProperties()` | Accesses system properties |
| `getSystemEnvironment()` | Accesses environment variables |
| `setActiveProfiles(...)` | Sets the list of active profiles |
| `addActiveProfile(...)` | Adds an active profile |
| `setDefaultProfiles(...)` | Sets the default profiles |
| `merge(parent)` | Merges property sources and profiles from a parent Environment |
| `setPlaceholderPrefix(...)`, `setPlaceholderSuffix(...)` | Customizes placeholder syntax when needed |
| `setConversionService(...)` | Configures the conversion service for type conversion |

Typically, business code only needs `Environment` to read configuration. Only use `ConfigurableEnvironment` when you need to configure the environment during the bootstrap phase, write integrations, or test.

### 4.1. Obtaining ConfigurableEnvironment from ApplicationContext

A `ConfigurableApplicationContext` provides `getEnvironment()`:

~~~java
ConfigurableApplicationContext context = ...;
ConfigurableEnvironment environment =
        (ConfigurableEnvironment) context.getEnvironment();
~~~

In a Spring Boot application, `ConfigurableApplicationContext` is the context type commonly used when access to mutable configuration is needed. Do not cast arbitrarily if you do not control the context type; obtain the appropriate type from the lifecycle or API in use.

### 4.2. Configuring the Environment Before Refresh

A common approach is to use `ApplicationContextInitializer` to add a property source before the context is refreshed:

~~~java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class RuntimeOverridesInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        ConfigurableEnvironment environment = context.getEnvironment();

        Map<String, Object> values = Map.of(
                "clients.inventory.read-timeout", "900ms",
                "clients.inventory.enabled", true
        );

        environment.getPropertySources().addFirst(
                new MapPropertySource("runtimeOverrides", values)
        );
    }
}
~~~

Register the initializer with `SpringApplication`:

~~~java
SpringApplication application =
        new SpringApplication(OrdersApplication.class);

application.addInitializers(new RuntimeOverridesInitializer());
application.run(args);
~~~

The `runtimeOverrides` source is added to the beginning of the list, so it takes higher precedence than sources behind it when they contain the same key. This example illustrates the technique; in production, clearly decide which override source is allowed to beat deployment configuration and avoid hardcoding sensitive values in source code.

### 4.3. `Environment.merge(parent)`

Some applications have a parent context and a child context. `merge(parent)` helps bring property sources and profiles from the parent Environment into the current Environment. The parent's property sources are added after the child's existing sources; therefore, sources already in the child retain higher precedence.

Do not confuse merging Environments with merging all beans between two contexts. Bean lookup across a context hierarchy is an `ApplicationContext` mechanism; `Environment.merge` is only about property sources and profiles.

## 5. `PropertySource`: A Source of Properties

`PropertySource<T>` is an abstraction representing a data source that can be queried by key name. `T` is the underlying source data type, such as `Map<String, Object>`, `Properties`, or a custom object.

A `PropertySource` typically has:

- **name:** the identifying name of the source.
- **source:** the underlying data object.
- **getProperty(name):** returns the value of the key or `null` if the source does not have the key.

### 5.1. Common PropertySource Types

| Type | Purpose |
| --- | --- |
| `MapPropertySource` | Reads properties from a `Map<String, Object>` |
| `PropertiesPropertySource` | Reads from a `Properties` object |
| `SystemEnvironmentPropertySource` | Reads process environment variables, supporting appropriate naming rules |
| `StubPropertySource` | Placeholder source used in certain phases/lifecycles |
| `CompositePropertySource` | Combines multiple `PropertySource` instances into a composite source |
| `EnumerablePropertySource` | A source capable of listing property names |

Spring Boot also creates property sources for Config Data, command-line arguments, random values, and other configuration sources. Those sources are fed into the same property resolution mechanism.

### 5.2. A PropertySource Does Not Have to Be a File

A property source can be built from:

- Loaded `.properties` or YAML files.
- JVM system properties (`-Dname=value`).
- Process environment variables.
- Command-line arguments.
- A Map created in code.
- Remote sources loaded into the Environment by an integration.
- Custom sources provided by the application or a library.

Therefore, when calling `environment.getProperty("clients.inventory.read-timeout")`, application code does not need to know whether the value was read from YAML, an environment variable, or Config Server. It simply requests the value by key.

## 6. Precedence Order Among PropertySources

`MutablePropertySources` maintains an ordered list. When Spring resolves a key, higher-precedence sources are checked first; the first non-`null` value is used.

### 6.1. The First-Match-Wins Rule

Suppose there are three sources:

| Order | PropertySource | `clients.inventory.read-timeout` |
| ---: | --- | --- |
| 1 | `commandLineArgs` | `1200ms` |
| 2 | `systemEnvironment` | `1000ms` |
| 3 | `applicationConfig` | `700ms` |

The result from `Environment` is `1200ms` because the first source containing this key is selected.

~~~mermaid
flowchart TD
    A[environment.getProperty(key)] --> B{Does Source 1 have key?}
    B -- Yes --> C[Return Source 1 value]
    B -- No --> D{Does Source 2 have key?}
    D -- Yes --> E[Return Source 2 value]
    D -- No --> F{Does next Source have key?}
    F -- Yes --> G[Return first value found]
    F -- No --> H[Return null or default]
~~~

The diagram illustrates the general principle. The exact source order in Spring Boot depends on the version and how the application is launched. Inspect the actual `Environment` instead of assuming the list is always the same across every project.

### 6.2. StandardEnvironment and Spring Boot

Spring Framework's `StandardEnvironment` has common default sources such as:

- `systemProperties`: JVM system properties.
- `systemEnvironment`: environment variables.

In the default configuration of `StandardEnvironment`, system properties have higher precedence than the system environment. Spring Boot adds many other sources, such as command-line arguments, Config Data, test properties, devtools, and integrated configuration sources. Therefore, the full order of a Boot application cannot be inferred solely from the two sources of `StandardEnvironment`.

For example, the argument:

~~~bash
java -jar orders-service.jar --server.port=9090
~~~

is placed by Spring Boot into a dedicated property source for the command line. This source usually has high precedence, allowing it to override values in configuration files.

### 6.3. The Same Key Appearing in Multiple Sources

Suppose the default configuration is:

~~~yaml
clients:
  inventory:
    read-timeout: 700ms
~~~

The deployment environment sets:

~~~bash
CLIENTS_INVENTORY_READTIMEOUT=1000ms
~~~

And the run includes the argument:

~~~bash
java -jar orders-service.jar --clients.inventory.read-timeout=1200ms
~~~

If no other higher-precedence source overrides it, the final value is `1200ms`. This is why when investigating a value that "does not match the file," you need to inspect all PropertySources rather than only opening `application.yml`.

## 7. MutablePropertySources: Adding, Replacing, and Removing Sources

`ConfigurableEnvironment.getPropertySources()` returns `MutablePropertySources`. This API allows adjusting the list of configuration sources.

| Method | Meaning |
| --- | --- |
| `addFirst(source)` | Adds a source to the front of the list, high precedence |
| `addLast(source)` | Adds a source to the end of the list, low precedence |
| `addBefore(name, source)` | Adds before a source with a known name |
| `addAfter(name, source)` | Adds after a source with a known name |
| `replace(name, source)` | Replaces the source with the corresponding name |
| `remove(name)` | Removes a source by name |
| `contains(name)` | Checks whether a source with that name exists |
| `precedenceOf(source)` | Returns the precedence position of the source in the list |

### 7.1. Adding a MapPropertySource

~~~java
Map<String, Object> values = Map.of(
        "clients.inventory.read-timeout", "850ms",
        "clients.inventory.enabled", true
);

MapPropertySource overrides =
        new MapPropertySource("inventoryOverrides", values);

environment.getPropertySources().addFirst(overrides);
~~~

After adding it, you can read:

~~~java
Duration timeout = environment.getProperty(
        "clients.inventory.read-timeout",
        Duration.class
);
~~~

Because `inventoryOverrides` was added to the front, it can override the same key in sources behind it. This source only exists in the process's memory and is not automatically written back to configuration files.

### 7.2. Adding a Source with Low Precedence

If you only want to provide fallback values, use `addLast`:

~~~java
MapPropertySource defaults = new MapPropertySource(
        "libraryDefaults",
        Map.of(
                "clients.inventory.read-timeout", "500ms",
                "clients.inventory.enabled", false
        )
);

environment.getPropertySources().addLast(defaults);
~~~

This source is only used if no preceding source supplies the corresponding key. This is a way for a library to provide defaults while still allowing the application to override them.

### 7.3. Adding Before or After a Specific Source

When precise positioning control is needed:

~~~java
environment.getPropertySources().addBefore(
        "systemEnvironment",
        new MapPropertySource("deploymentPolicy", values)
);
~~~

The property source name must exist in the list. If the name is absent, `addBefore`/`addAfter` cannot be performed and will throw an error. Do not hardcode Boot source names without checking the application's version and startup method.

### 7.4. Caution When Replacing or Removing

`replace` and `remove` affect property resolution across the entire context. If you accidentally remove `systemEnvironment` or a Config Data source, many keys may revert to default values without any clear syntax error.

Only replace or remove sources when there is a specific requirement and proper tests. For typical applications, adding a distinctly named source with a clearly defined precedence is usually easier to understand than replacing framework-created sources.

## 8. How Do Config Data and Spring Cloud Config Enter the Environment?

### 8.1. Spring Boot Config Data

Spring Boot loads `application.properties`, `application.yml`, profile-specific files, and imported sources during the Environment preparation phase. The result is represented as property sources so the rest of the application reads them via `Environment`.

Example:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:file:./deploy-config/overrides.yml

clients:
  inventory:
    read-timeout: 700ms
~~~

Imported files can add or override values depending on position and Config Data rules. `spring.config.import` is not a `PropertySource` API; it is a Spring Boot mechanism to bring additional Config Data sources into the configuration loading process.

### 8.2. Spring Cloud Config Client

When using Spring Cloud Config Client, the corresponding starter connects to Config Server according to the declared configuration. Values from the server are placed into the Environment via property sources created by the integration.

Example using the Config Data mechanism:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: optional:configserver:http://localhost:8888
~~~

An appropriate Config Client dependency matching the release train is required. Config Server returns configuration by application name, profile, and label. Where the remote property source sits and how it can be overridden depend on the Config Client mechanism, release train, and override options. Do not apply the ordering from an older project to a project using modern Config Data without verifying it.

**Key point:** `Environment` does not make HTTP requests to Config Server itself. Config Client is responsible for fetching configuration and placing it into the Environment; `Environment` provides the interface to read values after the integration process completes.

### 8.3. Discovery and Service Registry Are Separate Matters

Spring Cloud Commons has the `DiscoveryClient`, `ServiceRegistry`, and `ServiceInstance` abstractions. They describe service lookup/registration capabilities, whereas `Environment` provides configuration values such as registry endpoints, application names, or discovery options.

Example:

~~~yaml
spring:
  application:
    name: orders-service
  cloud:
    discovery:
      enabled: true
~~~

Reading `spring.cloud.discovery.enabled=true` from Environment proves neither that the registry has connected successfully nor that a `DiscoveryClient` provider has been created. You must separately inspect dependencies, auto-configuration, beans, and instance lookup behavior.

## 9. Changing Environment Does Not Mean Beans Automatically Refresh

An important misconception is assuming that merely changing a value in a `PropertySource` will automatically update every running bean.

### 9.1. Beans That Read Configuration Once

Example:

~~~java
@Component
class InventoryEndpoint {
    private final URI baseUrl;

    InventoryEndpoint(
            @Value("${clients.inventory.base-url}") URI baseUrl
    ) {
        this.baseUrl = baseUrl;
    }

    URI baseUrl() {
        return baseUrl;
    }
}
~~~

The value is resolved when the bean is created and stored in the field. If a property source is added or modified afterward, the `baseUrl` field is not automatically reassigned.

### 9.2. `@ConfigurationProperties` Also Has a Lifecycle

A bean bound from `@ConfigurationProperties` is also an object with a lifecycle in the context. Changing the Environment does not automatically guarantee that the object currently in use has been rebound, especially if a consumer holds a reference to a client or object created from old values.

### 9.3. Role of Spring Cloud Context

Spring Cloud Context adds a refresh mechanism, including `@RefreshScope` and Environment-related services. When the application triggers refresh properly:

- Property sources or the Environment may be updated according to the integration mechanism.
- Certain beans may be rebound or recreated according to their scope.
- Beans outside refresh scope may continue holding old state.
- Clients currently processing requests may still use old instances or configuration until their lifecycle is handled.

`@RefreshScope` does not automatically watch every file change on disk, does not automatically poll Config Server, and does not automatically broadcast changes to all replicas. A mechanism to emit refresh signals, proper endpoint/messaging configuration, and per-instance verification after updates are required.

### 9.4. When Should PropertySource Be Modified at Runtime?

Reasonable cases may include:

- Testing to simulate configuration.
- Bootstrapping a controlled override source.
- Integrating a dynamic configuration source with a clear lifecycle.
- Providing temporary values for a specific context.

Do not use continuously mutating `MutablePropertySources` as an application state store. If configuration changes frequently, use an intentional configuration management/refresh mechanism and define how dependent beans synchronize.

## 10. Inspecting Property Sources and Final Values

### 10.1. Listing Property Sources

You can print the names of configuration sources:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

void listSources(ConfigurableEnvironment environment) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        System.out.println(source.getName());
    }
}
~~~

The printed order reflects the precedence order in `MutablePropertySources`. Do not print entire source objects or all keys/values in production because they may contain sensitive information.

### 10.2. Checking One Key Across Each Source

~~~java
void inspectOneKey(
        ConfigurableEnvironment environment,
        String key
) {
    System.out.println("resolved value = "
            + environment.getProperty(key));

    for (PropertySource<?> source : environment.getPropertySources()) {
        Object value = source.getProperty(key);
        if (value != null) {
            System.out.printf(
                    "source=%s, contains key=%s%n",
                    source.getName(),
                    key
            );
        }
    }
}
~~~

This example only logs the name of the source containing the key, not the value. In test environments you can display values for comparison; in production, be careful because the key might be a secret.

Note: `getProperty` on an individual source does not perform the full placeholder resolution/conversion process like `Environment.getProperty`. It helps find the source directly containing the key, though it does not always determine the final origin if the source is composite or the value is referenced indirectly.

### 10.3. Actuator `env` and Origin Tracking

Spring Boot Actuator provides the `env` endpoint to observe the Environment and property sources, if the endpoint is enabled and exposed. This endpoint can help determine:

- Whether the key exists.
- Which property source supplies the value.
- Which value is currently used after applying precedence order.
- The origin/location of the property if the source supports origin tracking.

Do not expose this endpoint publicly. Sensitive values may be masked according to sanitization configuration, but authentication, authorization, and network restrictions are still required. Do not rely on default masking to protect all types of custom secrets.

## 11. Testing Environment and PropertySource

Testing helps prove that source precedence, profiles, and binding work as expected without needing to connect to a real Config Server or registry in every test.

### 11.1. Using MockEnvironment

Spring Test provides `MockEnvironment` to create a configurable Environment in tests:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class EnvironmentTest {

    @Test
    void resolvesPropertyFromMockEnvironment() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty(
                        "clients.inventory.read-timeout",
                        "700ms"
                );

        assertThat(environment.getProperty(
                "clients.inventory.read-timeout"
        )).isEqualTo("700ms");
    }
}
~~~

`MockEnvironment` is suitable for unit tests of components that accept `Environment`. If a test needs to verify multiple property sources and precedence, `MockPropertySource` can be added.

### 11.2. Testing Precedence

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PropertySourcePrecedenceTest {

    @Test
    void firstSourceWins() {
        MockEnvironment environment = new MockEnvironment();

        environment.getPropertySources().addFirst(
                new MapPropertySource(
                        "highPriority",
                        Map.of("app.mode", "production")
                )
        );

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "lowPriority",
                        Map.of("app.mode", "development")
                )
        );

        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("production");
    }
}
~~~

This test verifies the first-match-wins rule of the PropertySource list. It does not test Spring Boot's entire default property source ordering.

### 11.3. Testing Profiles

~~~java
@Test
void acceptsProductionProfile() {
    MockEnvironment environment = new MockEnvironment();
    environment.setActiveProfiles("prod", "cloud");

    assertThat(environment.acceptsProfiles(
            org.springframework.core.env.Profiles.of("prod & cloud")
    )).isTrue();
}
~~~

Tests can add cases for inactive profiles, OR expressions, and negation. For `@Profile` on configurations, context tests are needed to confirm beans are registered/not registered according to the profile.

### 11.4. Testing a Spring Boot Application

To test how Boot loads Config Data, binds `@ConfigurationProperties`, or applies auto-configuration, use `ApplicationContextRunner`, `@SpringBootTest`, or an appropriate context test. A standalone `MockEnvironment` does not reproduce `SpringApplication`'s full file discovery, profile processing, and Config Data import process.

## 12. Common Pitfalls

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| `getProperty` returns `null` | No source contains the key or wrong key name | List PropertySources, check canonical name and Config Data |
| Value differs from YAML file | Higher-precedence source overrides it | Check source order and Actuator `env` |
| Incorrect profile | Active profile not set or overridden | Check `getActiveProfiles()` and command line/environment |
| Added MapPropertySource but value did not change | Source added with `addLast` or wrong key | Check source position and key name |
| Bean still holds old value | Value was read when bean initialized | Check lifecycle, rebinding, and `@RefreshScope` |
| Config Server has data but client does not see it | Config Client not imported, wrong app/profile/label, or connection error | Check startup log, dependencies, `spring.config.import`, and Environment |
| Discovery bean does not exist | Missing provider/auto-configuration or wrong conditional property | Check classpath, condition report, and bean inventory |
| Tests pass but production fails | Tests use simple MockEnvironment, not reproducing real Config Data | Add integration tests close to the deployment environment |

### 12.1. Distinguishing a Missing Key from an Empty Value

`containsProperty(key)` checks whether any source supplies the key. A key declared with an empty string may differ from a key that does not exist at all. When using `getProperty`, both cases may need to be distinguished based on business requirements.

For example, if a URL must have a non-empty value, using `containsProperty` alone is not enough. You need to validate the string after reading or use `@NotBlank` in typed configuration.

### 12.2. Placeholders Can Reference Another Source

Suppose:

~~~properties
app.region=ap-southeast-1
app.display-name=${spring.application.name}-${app.region}
~~~

The value of `app.display-name` may depend on a key from another property source. When investigating, look not only at the source containing the placeholder key, but also at the referenced keys and the resolution process.

### 12.3. PropertySource Order Is Not Bean Creation Order

Property source precedence determines which configuration value is read. Bean initialization order is a different matter, governed by the dependency graph, `@DependsOn`, configuration processing, and lifecycle. Do not use `addFirst` to fix bean creation order errors; these two concepts are not directly related.

## 13. Design Conventions in Spring Cloud Core

When building applications using Spring Cloud abstractions, apply these principles:

1. Inject `Environment` when you need to read some dynamic keys or query profiles.
2. Use `@ConfigurationProperties` for structured groups of configuration with validation and multiple consumers.
3. Only use `ConfigurableEnvironment` during bootstrap, integrations, or tests when you need to modify the list of sources/profiles.
4. Give PropertySources clear and unique names to make investigation easy.
5. Only use `addFirst` when you genuinely want to override other sources; library defaults should generally have low precedence.
6. Do not remove or replace sources created by Spring Boot/Spring Cloud without a valid reason and appropriate tests.
7. Distinguish between loaded configuration, created beans, connected providers, and active runtime behavior.
8. When using Config Server, verify application name, profile, label, import, and precedence according to the exact release train.
9. When changing configuration at runtime, determine which beans need rebinding/recreation and which refresh mechanism emits the signal.
10. Do not log all configuration values or expose management endpoints to untrusted networks.

## 14. Practice Exercises

**Exercise 1 — Finding the Winning Source.** Create three `MapPropertySource` instances all containing the key `app.region`, adding them sequentially via `addFirst`, `addLast`, and `addBefore`. Record the `Environment.getProperty` result after each operation and explain the precedence order.

**Exercise 2 — Profile Expressions.** Set the active profiles to `prod` and `cloud`. Test the expressions `prod`, `dev`, `prod & cloud`, `prod | staging`, and `!test`. State which expressions are accepted.

**Exercise 3 — ConfigurableEnvironment.** Write an `ApplicationContextInitializer` that adds a `MapPropertySource` containing the key `clients.inventory.read-timeout`. Prove that this value takes precedence over `application.yml`, then try changing `addFirst` to `addLast`.

**Exercise 4 — Runtime Changes.** A bean holds `URI baseUrl` in its constructor. After adding a new property source to the Environment, observe why the field value does not change. Propose an appropriate design if business requirements require updating the endpoint at runtime.

**Exercise 5 — Spring Cloud Config.** Use Config Client to fetch `clients.inventory.read-timeout` from Config Server. Inspect the remote PropertySource, profile, and final value. Try adding an override from an environment variable and determine which source wins under your current configuration.

**Exercise 6 — Diagnosing Discovery.** An application reads `spring.cloud.discovery.enabled=true` but cannot look up instances. Separate the layers of evidence: Environment has the key, the provider bean exists, the registry connects successfully, and instances are returned.

## 15. Summary and References

- **`Environment`** is the interface for reading properties and profiles.
- **`ConfigurableEnvironment`** allows configuring profiles and the PropertySource list.
- **`PropertySource`** represents a source of values; it does not have to be a file.
- **`MutablePropertySources`** orders sources by precedence; the first source containing the key usually determines the final value.
- Spring Boot brings Config Data and external sources into the Environment; Spring Cloud Config Client integrates remote configuration into the same mechanism.
- Changing the Environment does not automatically update every created object. Check lifecycle, binding, and refresh scope.
- When debugging, inspect both the final value and the source providing it.

Official resources to cross-reference according to your project's Spring Framework, Spring Boot, and Spring Cloud versions:

1. [Spring Framework Reference – Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html)
2. [Spring Framework Javadoc – `Environment`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html)
3. [Spring Framework Javadoc – `ConfigurableEnvironment`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html)
4. [Spring Framework Javadoc – `PropertySource`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html)
5. [Spring Framework Javadoc – `MutablePropertySources`](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/MutablePropertySources.html)
6. [Spring Boot Reference – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
7. [Spring Cloud Config – Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
8. [Spring Cloud Context – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)

# Environment, PropertySource, and Runtime Configuration Values

A Spring Boot application often runs the same Java code across different environments: local, test, staging, and production. Database addresses, HTTP client timeouts, feature toggles, or server ports may vary without requiring source code changes.

Spring Boot addresses this need through its **externalized configuration** mechanism. At its core is Spring Framework's `Environment`, along with a set of `PropertySource` instances ordered by precedence. When the application asks for a property's value, Spring searches through those configuration sources and returns the effective value at query time.

A key point to understand clearly: **"runtime configuration values" does not mean "every configuration file change updates beans immediately"**. `Environment#getProperty(...)` can read the current state of the property sources attached to it, whereas `@Value`, `@ConfigurationProperties`, conditions, and already initialized beans have their own lifecycle. They do not automatically update when a file on disk or an environment variable changes.

This lesson is part of the **Application Configuration** chapter of **Spring Boot Fundamentals**. We will explore `Environment`, `PropertySource`, precedence, profiles, Config Data, how to read configuration in code, and how to determine the actual values the application is using.

## 1. Three foundational concepts

In Spring, you should distinguish three conceptual layers:

| Concept | Role | Example |
|---|---|---|
| `Environment` | Provides the API for reading properties and profile information for the application | `environment.getProperty("app.name")` |
| `PropertySource` | Represents a source that supplies configuration key-value pairs | A PropertySource from environment variables, system properties, or a YAML file |
| `PropertySources` | A collection of PropertySources ordered by precedence | `MutablePropertySources` in `ConfigurableEnvironment` |

For example, an application might receive the same `app.message` property from multiple sources:

```text
Command-line argument
    --app.message="from-cli"
                  │
                  ▼
Java system property
    -Dapp.message=from-system
                  │
                  ▼
OS environment variable
    APP_MESSAGE=from-env
                  │
                  ▼
application.yml
    app.message: from-yaml
```

In a typical Spring Boot setup, command-line arguments have higher precedence than the other three sources. Therefore:

```java
environment.getProperty("app.message")
```

may return `from-cli` even though `application.yml` contains a different value.

### 1.1. A key can have multiple values

Spring does not require a key to be declared only once. Different sources can provide the same key to allow environment-specific configuration overrides.

For example:

```yaml
# application.yml
app:
  message: "from-yaml"
```

Run:

```bash
java -jar demo.jar --app.message=from-cli
```

In this case, `Environment` can be aware of both the file source and the command-line source, but the usual resolved result is `from-cli` because that source has higher precedence.

### 1.2. Environment is not a single file

`Environment` is not synonymous with `application.yml`.

It is an abstraction that aggregates multiple data sources and resolution rules. Some sources may not exist as files at all, such as process environment variables, Java system properties, command-line arguments, or maps added in code.

Therefore, when a value "differs from application.yml", it does not necessarily mean Spring read the wrong file. A higher-precedence source may have overridden it.

## 2. What interface is Environment?

`Environment` lives in Spring Framework:

```java
import org.springframework.core.env.Environment;
```

This interface lets you read properties and profile information. Common methods include:

```java
String value = environment.getProperty("app.message");

String fallback = environment.getProperty(
        "app.message",
        "Hello"
);

Boolean enabled = environment.getProperty(
        "app.feature.enabled",
        Boolean.class,
        false
);

boolean exists = environment.containsProperty("app.message");

String required = environment.getRequiredProperty("app.message");

String[] active = environment.getActiveProfiles();

String[] defaults = environment.getDefaultProfiles();
```

Some methods are inherited from `PropertyResolver`.

### 2.1. What does getProperty return if a key does not exist?

With the call:

```java
String name = environment.getProperty("app.name");
```

if the property is not found, the result is `null`.

If you want a default value:

```java
String name = environment.getProperty(
        "app.name",
        "Spring Boot App"
);
```

If a configuration property is required to exist:

```java
String name = environment.getRequiredProperty("app.name");
```

`getRequiredProperty` throws `IllegalStateException` when the property has no resolvable value. This can be useful for checking required configuration, though for large and complex configuration sets, consider `@ConfigurationProperties` with validation.

### 2.2. getProperty with a target type

Spring can convert the value when you request a specific type:

```java
boolean enabled = environment.getProperty(
        "app.feature.enabled",
        Boolean.class,
        false
);

int retries = environment.getProperty(
        "app.client.retries",
        Integer.class,
        3
);
```

If the configured value cannot be converted to the requested type, a conversion error may occur instead of returning a valid value.

For example:

```properties
app.client.retries=not-a-number
```

is not an integer, so it is incompatible with `Integer.class`.

### 2.3. Environment does not hold business logic

`Environment` should be used to query configuration, not as a store for business data such as order status, account balances, or login sessions.

A property like `app.client.timeout` is configuration; a value like "remaining balance of account 123" is business data and should be managed by an appropriate data system.

## 3. Injecting Environment into a Spring bean

`Environment` is normally already available for injection in a Spring ApplicationContext.

For example:

```java
package com.example.demo.config;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final Environment environment;

    public GreetingService(Environment environment) {
        this.environment = environment;
    }

    public String greeting() {
        return environment.getProperty(
                "app.greeting.message",
                "Hello"
        );
    }
}
```

Configuration file:

```yaml
app:
  greeting:
    message: "Hello from application.yml"
```

Another component can call:

```java
String text = greetingService.greeting();
```

The result is the effective value of `app.greeting.message` in `Environment` at the time of the call.

### 3.1. Using Environment in a CommandLineRunner

An example of observing configuration after the ApplicationContext has initialized:

```java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigurationPrinter implements CommandLineRunner {

    private final Environment environment;

    public ConfigurationPrinter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(String... args) {
        System.out.println(
                "app.greeting.message = "
                        + environment.getProperty(
                                "app.greeting.message",
                                "<missing>"
                        )
        );
    }
}
```

This example only prints a single non-sensitive property. **Do not print the entire Environment to logs**, because passwords, API keys, tokens, or sensitive data may exist in the configuration sources.

### 3.2. Reading configuration directly on every request?

You can call `environment.getProperty(...)` whenever needed. However, if a property is simply static configuration for a service, reading it repeatedly across requests makes the code harder to test and increases coupling to the framework.

In many cases, it is better to bind configuration into an explicit object using `@ConfigurationProperties`. Using `Environment` directly is suited for infrastructure code, cases requiring dynamic key lookups, or scenarios where you need to see the current source value.

## 4. What is PropertySource?

`PropertySource<T>` lives in:

```java
import org.springframework.core.env.PropertySource;
```

It represents a source capable of answering the question: "In this source, what is the value of key X?"

Conceptually:

```java
Object value = propertySource.getProperty("app.message");
```

A `PropertySource` has:

- A source name, such as `systemProperties`.
- A corresponding underlying source object.
- Property lookup logic by key.
- The ability to return `null` if the requested key is absent.

Common implementations include `MapPropertySource` and `SystemEnvironmentPropertySource`, along with the source types created by Spring Boot when loading Config Data.

### 4.1. MapPropertySource example

```java
import java.util.HashMap;
import java.util.Map;
import org.springframework.core.env.MapPropertySource;

Map<String, Object> values = new HashMap<>();
values.put("app.message", "from-map");
values.put("app.feature.enabled", true);

MapPropertySource source = new MapPropertySource(
        "custom-map",
        values
);

System.out.println(source.getProperty("app.message"));
```

Result:

```text
from-map
```

This is only a standalone source. For it to participate in the application's resolution process, it must be added to `Environment`'s collection of PropertySources.

### 4.2. PropertySources may use different key formats

A source from Java properties may have the key `app.client.timeout`, whereas the OS environment typically uses the name `APP_CLIENT_TIMEOUT`.

Spring Boot provides binding and name conversion rules to work across different naming conventions. However, do not assume that calling `propertySource.getProperty("app.client.timeout")` directly on an individual source will behave identically to resolving or binding through the full Environment.

When debugging, you must distinguish between **looking up in a specific source** and **looking up through Environment with multiple sources, adapters, and name-handling rules**.

## 5. PropertySources and precedence

A `ConfigurableEnvironment` provides `MutablePropertySources`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;

MutablePropertySources sources =
        configurableEnvironment.getPropertySources();
```

`MutablePropertySources` allows you to inspect and modify the order of configuration sources.

When resolving a key, higher-precedence sources are typically checked first. The first source that provides a matching value can determine the returned value.

### 5.1. Diagram

```text
Environment.getProperty("app.mode")
                    │
                    ▼
         High-priority PropertySource
         --app.mode=production
                    │
          Has value? ───── Yes ───► production
                    │
                    No
                    ▼
         Java system properties
         -Dapp.mode=staging
                    │
          Has value? ───── Yes ───► staging
                    │
                    No
                    ▼
         OS environment
         APP_MODE=development
                    │
          Has value? ───── Yes ───► development
                    │
                    No
                    ▼
         application.yml
         app.mode: default
                    │
                    ▼
                  default
```

This is a conceptual diagram to visualize precedence. In practice, Spring Boot also has Config Data, JSON, test properties, and other sources applied according to specific rules.

### 5.2. Common configuration sources and relative precedence

In a typical Spring Boot application, if the same key appears in several of the following sources, the order is usually:

| Source | Relative precedence |
|---|---|
| Command-line argument `--app.mode=...` | Higher than the sources listed below |
| `SPRING_APPLICATION_JSON` | Below command line; can be higher than system properties |
| Java system property `-Dapp.mode=...` | Higher than OS environment variables and Config Data |
| OS environment variable `APP_MODE` | Higher than Config Data |
| Config Data (`application.yml`, `application.properties`, profile files, external config) | Ordered per Config Data rules |
| `@PropertySource` on Java configuration | Typically lower than Config Data; added during refresh |
| `SpringApplication` default properties | Low default level among common sources |

This table highlights several common relationships and is **not an exhaustive list of every PropertySource**. Test frameworks may add higher-precedence sources; Servlet/JNDI and DevTools may add their own sources; and Config Data file selection also has internal ordering.

Therefore, when you need an exact conclusion, inspect the actual PropertySources present in the running process rather than relying solely on a general table.

### 5.3. Three-source conflict example

In `application.yml`:

```yaml
app:
  mode: from-file
```

Set an environment variable:

```bash
export APP_MODE=from-environment
```

Run:

```bash
java -Dapp.mode=from-system -jar demo.jar --app.mode=from-command-line
```

Expected result of:

```java
environment.getProperty("app.mode")
```

is:

```text
from-command-line
```

If you omit the command-line argument, the system property can win. If you also omit the system property, the OS environment variable can win over the YAML file.

Do not overlook the difference between an environment variable and a Java system property: `APP_MODE` belongs to the process environment, whereas `-Dapp.mode=...` is passed to the JVM.

## 6. Config Data: when are application.yml and application.properties loaded?

Spring Boot uses the **Config Data** mechanism to load application configuration files during the bootstrap phase.

For example:

```yaml
# application.yml
app:
  client:
    endpoint: "https://api.example.test"
    timeout: 5s
```

Spring Boot places these values into `Environment` through appropriate configuration sources before most bean definitions are created and constructors or configuration properties are bound.

Common Config Data sources include:

- `application.properties` on the classpath.
- `application.yml` on the classpath.
- Configuration files outside the artifact.
- Profile-specific files such as `application-prod.yml`.
- Locations specified with `spring.config.location`.
- Additional locations specified with `spring.config.additional-location`.
- Resources imported via `spring.config.import`.

### 6.1. Files inside the JAR vs. files outside the JAR

For example:

```text
application.jar
  └── BOOT-INF/classes/application.yml

./config/application.yml
```

When running from a directory that has an external configuration file in a location searched by Spring Boot, the external configuration can have higher precedence than the values packaged inside the JAR.

This allows a single artifact to be deployed across multiple environments without rebuilding just to change a URL or timeout.

### 6.2. Ordering within the Config Data group

For the default supported locations, a common precedence order (from lowest to highest) can be understood as:

1. Regular configuration files packaged inside the JAR.
2. Profile-specific configuration files packaged inside the JAR.
3. Regular configuration files outside the JAR.
4. Profile-specific configuration files outside the JAR.

Custom config imports or location groups can affect the effective ordering, so this serves as a mental model for default cases rather than a universal rule for every custom file layout.

### 6.3. application.properties and application.yml in the same location

Spring Boot supports both formats. However, you should choose **one primary format per location** to avoid confusion over precedence.

If both `application.properties` and `application.yml` exist in the same location, under normal Config Data processing `.properties` takes precedence over YAML. Avoid building business override logic around keeping both files and relying on this detail.

### 6.4. Config Data vs. @PropertySource

`application.yml` is loaded by Boot while preparing the `Environment`. `@PropertySource` is a Spring Framework mechanism processed when configuration classes participate in context refresh.

Because `@PropertySource` is added later, it is unsuitable for certain properties needed before refresh, such as some `logging.*` or `spring.main.*` settings.

Consequently, **do not use `@PropertySource` to replace Spring Boot's entire Config Data system**.

## 7. How do profiles affect the effective value?

Profiles let an application select groups of configuration per environment.

Shared file example:

```yaml
# application.yml
app:
  payment:
    endpoint: "https://sandbox.example.test"
    timeout: 3s
```

Production file:

```yaml
# application-prod.yml
app:
  payment:
    endpoint: "https://payment.example.test"
    timeout: 10s
```

Run:

```bash
java -jar demo.jar --spring.profiles.active=prod
```

Then `Environment` can resolve:

```text
app.payment.endpoint = https://payment.example.test
app.payment.timeout  = 10s
```

because the `prod` profile file is loaded and can override the corresponding keys from the shared file.

### 7.1. Reading active profiles

```java
import java.util.Arrays;
import org.springframework.core.env.Environment;

String[] activeProfiles = environment.getActiveProfiles();

System.out.println(Arrays.toString(activeProfiles));
```

If run with `--spring.profiles.active=prod`, the array normally contains `prod`.

`getDefaultProfiles()` returns the list of default profiles used when no active profile has been selected.

### 7.2. An application can have multiple profiles

For example:

```bash
java -jar demo.jar --spring.profiles.active=prod,metrics
```

Profiles can contribute configuration from multiple sources. If profile-specific files set the same key, profile application order and Config Data ordering affect the final value.

Therefore, when debugging, check the **actual list of active profiles**, not just a single `application-prod.yml` file.

### 7.3. Profiles are not the same as OS environment

The word "environment" in "development environment" and Spring's `Environment` API are related but not identical.

- A **profile** is a label for selecting appropriate configurations or beans.
- An **OS environment variable** is a process environment variable.
- **Spring Environment** is an abstraction covering both properties and profiles.

For example, you can enable the `prod` profile using the `SPRING_PROFILES_ACTIVE` environment variable, but that does not make profiles and environment variables the same mechanism.

## 8. Setting properties with environment variables

In container or cloud deployments, configuration via OS environment variables is very common.

YAML file example:

```yaml
app:
  feature:
    enabled: false
```

You can override it with:

```bash
APP_FEATURE_ENABLED=true java -jar demo.jar
```

On a shell that does not support inline temporary variable assignment before a command, set the variable using that shell's syntax. For example, in PowerShell:

```powershell
$env:APP_FEATURE_ENABLED = "true"
java -jar demo.jar
```

Spring Boot provides relaxed binding to map canonical property names to appropriate environment variable names. For example, `app.feature.enabled` corresponds to `APP_FEATURE_ENABLED`.

### 8.1. Be careful with dashes

For canonical kebab-case property names, Boot's standard conversion rule to an environment variable name is:

1. Replace dots `.` with underscores `_`.
2. Remove dashes `-`.
3. Convert to uppercase.

For example:

```text
spring.main.log-startup-info
        ↓
SPRING_MAIN_LOGSTARTUPINFO
```

Do not assume every dash always turns into a new underscore. For `@ConfigurationProperties` and complex bound types, use canonical names and verify Spring Boot's relaxed binding rules.

### 8.2. Environment variables do not automatically change in a running JVM

OS environment variables are supplied to a process when it starts. Editing a variable in a new shell or changing external deployment settings **does not automatically modify the Environment of an already running JVM**.

In container orchestration, changing environment variables usually requires restarting or rolling out a new process for the new values to take effect.

This differs from an in-memory `MapPropertySource` actively updated by code.

## 9. Java system properties and command-line arguments

### 9.1. Java system property

Run:

```bash
java -Dapp.client.retries=5 -jar demo.jar
```

In Java code:

```java
String raw = System.getProperty("app.client.retries");
```

This can return `5`.

Through Spring:

```java
int retries = environment.getProperty(
        "app.client.retries",
        Integer.class,
        3
);
```

In a typical configuration, `Environment` can resolve that same system property unless a higher-precedence source overrides the key.

### 9.2. Command-line argument

Run:

```bash
java -jar demo.jar --app.client.retries=8
```

Spring Boot can turn `--key=value` arguments into a high-precedence property source.

If `-Dapp.client.retries=5` is also present, the value `8` from the command line normally wins.

### 9.3. Do not confuse application arguments with Environment

`ApplicationArguments` helps inspect command-line arguments in option/non-option form:

```java
public void run(ApplicationArguments args) {
    boolean hasMode = args.containsOption("mode");
}
```

`Environment` provides a way to inspect effective configuration values across multiple sources:

```java
String mode = environment.getProperty("app.mode");
```

The two APIs serve different purposes, even though a command-line option may appear in both.

## 10. Placeholders: referencing other configuration values

Spring supports `${...}` placeholder syntax in many configuration and injection contexts.

For example:

```yaml
app:
  service:
    host: "localhost"
    port: 8081
    url: "http://${app.service.host}:${app.service.port}"
```

When resolving `app.service.url`, Spring can use the `host` and `port` properties to construct the full value.

For example:

```java
String url = environment.getProperty("app.service.url");
```

can return:

```text
http://localhost:8081
```

### 10.1. Placeholders with default values

```yaml
app:
  endpoint: "https://${API_HOST:api.example.test}"
```

If no suitable property or environment variable is present, the portion after the colon provides the default value.

In `@Value`:

```java
@Value("${app.client.retries:3}")
private int retries;
```

If the key does not exist, the default value is `3`.

### 10.2. resolvePlaceholders and resolveRequiredPlaceholders

`Environment` provides:

```java
String value = environment.resolvePlaceholders(
        "Endpoint = ${app.service.url}"
);
```

And:

```java
String value = environment.resolveRequiredPlaceholders(
        "Endpoint = ${app.service.url}"
);
```

The required method raises an error if any placeholder cannot be resolved according to its rules.

Distinguish between a placeholder-level default value and the default value passed to `getProperty(key, defaultValue)`. Both help the application handle unset properties, but they operate in different contexts.

## 11. @Value and Environment: snapshot or live lookup?

A bean can receive configuration with `@Value`:

```java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingSettings {

    private final String message;

    public GreetingSettings(
            @Value("${app.greeting.message:Hello}") String message
    ) {
        this.message = message;
    }

    public String message() {
        return message;
    }
}
```

When Spring creates `GreetingSettings`, the placeholder is resolved and passed to the constructor. The `message` field stores the injected value.

Meanwhile, a bean using `Environment` can query again on every call:

```java
@Component
public class GreetingReader {

    private final Environment environment;

    public GreetingReader(Environment environment) {
        this.environment = environment;
    }

    public String readNow() {
        return environment.getProperty(
                "app.greeting.message",
                "Hello"
        );
    }
}
```

The two approaches have different semantics:

| Reading approach | Typical time of resolution | When an in-memory property source changes |
|---|---|---|
| `@Value` on constructor/field | When the bean is created and injected | The injected value does not automatically change |
| `@ConfigurationProperties` | When the configuration bean is bound/created | The bound object does not automatically rebind |
| `environment.getProperty(...)` inside a method | Each time the method calls the property resolver | May see the new value if the actual PropertySource updated and no higher-precedence source overrides it |

"Environment is a live lookup" **does not mean** Spring automatically re-reads `application.yml` from disk or that every property source always updates itself. It simply means each new call queries the current state of the sources configured in the container at that moment.

### 11.1. Why don't @Value values change automatically?

Spring does not continuously poll sources and reassign every injected field. Doing so could also break object invariants and introduce concurrency bugs.

For instance, if `GreetingSettings` is created with `message = "Hello"`, a newly added property source later will not re-invoke the constructor or replace the `final` field.

If you need a feature flag that changes at runtime, design a component that intentionally reads a dynamic source rather than assuming `@Value` behaves like an observable variable.

## 12. @ConfigurationProperties: typed and structured binding

When an application has many related properties, `@ConfigurationProperties` is usually better suited than calling `getProperty` repeatedly.

Configuration example:

```yaml
app:
  client:
    endpoint: "https://api.example.test"
    timeout: 5s
    retries: 3
```

With Spring Boot 3 and a compatible Java version:

```java
package com.example.demo.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI endpoint,
        Duration timeout,
        int retries
) {
}
```

Enable scanning for `@ConfigurationProperties` classes:

```java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
```

Then inject `ClientProperties` via the constructor:

```java
@Service
public class ApiClient {

    private final ClientProperties properties;

    public ApiClient(ClientProperties properties) {
        this.properties = properties;
    }

    public void connect() {
        URI endpoint = properties.endpoint();
        Duration timeout = properties.timeout();
        // Use endpoint and timeout to configure the client.
    }
}
```

### 12.1. Benefits

- Type-safe: can bind `Duration`, `URI`, integers, booleans, and nested objects.
- Clearly structured by prefix.
- Easy to check with validation.
- Easy to use in unit tests.
- Well suited when multiple values configure the same client or service.
- Spring Boot supports relaxed binding from multiple configuration sources.

### 12.2. Binding still has a lifecycle

`@ConfigurationProperties` is bound when the corresponding bean is created or through appropriate binding infrastructure; it **does not automatically rebind after every property source change**.

For example, changing `application.yml` from `timeout: 5s` to `timeout: 10s` while the application is running will not automatically mutate an existing `ClientProperties` object.

To apply new configuration under the default model, you normally need to restart the application or use an explicitly designed refresh/rebind mechanism.

### 12.3. When to use Environment instead of ConfigurationProperties?

Use `Environment` when:

- You need to query an arbitrary property by a dynamic key.
- You are writing infrastructure components or startup diagnostics.
- You need to observe the value currently returned by the resolver.
- You need to check active profiles.
- You need to manipulate `PropertySources` in specialized infrastructure code.

Use `@ConfigurationProperties` when a group of properties forms the configuration contract of a bean or subsystem. That is the common choice for application code.

## 13. ConfigurableEnvironment and MutablePropertySources

`Environment` is the read API. If you genuinely need to customize the set of property sources, work with `ConfigurableEnvironment`:

```java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySource;
```

Some operations:

```java
MutablePropertySources sources =
        configurableEnvironment.getPropertySources();

sources.addFirst(customPropertySource);
sources.addLast(otherPropertySource);

PropertySource<?> systemProperties =
        sources.get("systemProperties");
```

Meaning:

- `addFirst(...)`: adds a source at the highest-precedence position in the current collection.
- `addLast(...)`: adds a source at the lowest-precedence position.
- `addBefore(...)`, `addAfter(...)`: inserts relative to a specific source name.
- `remove(...)`: removes a source by name.
- `replace(...)`: replaces a source with a known name.

These operations affect property resolution **from the moment of the change onward**, but do not automatically update beans that have already bound configuration.

### 13.1. Example of adding a custom source

```java
Map<String, Object> overrides = new HashMap<>();
overrides.put("app.message", "custom-value");

MapPropertySource customSource =
        new MapPropertySource("manual-overrides", overrides);

configurableEnvironment.getPropertySources()
        .addFirst(customSource);

System.out.println(
        configurableEnvironment.getProperty("app.message")
);
```

Unless special conditions apply, the result is:

```text
custom-value
```

because the custom source was just added at the head of the PropertySources collection.

### 13.2. Why shouldn't you call addFirst arbitrarily?

`addFirst` can override values coming from the command line, system properties, or configuration files. This can surprise operators.

If you truly need default configuration, `addLast` or `SpringApplication#setDefaultProperties` may be more appropriate. If you need an intentional override, give the source a clear name and document at which stage it is added.

Do not mutate `PropertySources` inside business methods as a way to manage business state.

## 14. When a PropertySource is added affects the outcome

Two points in time must be distinguished:

1. **Before the context finishes creating beans:** new properties can affect injection, binding, or conditions not yet evaluated.
2. **After the context has initialized:** new properties can affect subsequent lookups, but will not retroactively undo completed bean registration decisions or configuration bindings.

Diagram:

```text
JVM startup
      │
      ▼
SpringApplication prepares Environment
      │
      ▼
Read Config Data and add PropertySources
      │
      ▼
Process configuration and @Conditional
      │
      ▼
Create beans, inject @Value,
bind @ConfigurationProperties
      │
      ▼
ApplicationReadyEvent
      │
      ▼
Running application
      │
      ├── Environment#getProperty(...)
      │       reads current property sources
      │
      └── @Value / ConfigurationProperties
              already injected/bound earlier
```

This is a simplified model. Spring Boot has many lifecycle events and post-processors, but the timing relationship above is the key takeaway.

### 14.1. Adding a source before beans are created

You can add a source via `ApplicationContextInitializer`:

```java
package com.example.demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.MapPropertySource;

public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoConfiguration.class);

        application.addInitializers(context -> {
            Map<String, Object> overrides = Map.of(
                    "app.message", "from-initializer"
            );

            context.getEnvironment()
                    .getPropertySources()
                    .addFirst(new MapPropertySource(
                            "bootstrap-overrides",
                            overrides
                    ));
        });

        application.run(args);
    }
}
```

Here, the source is added during context initialization, before most application beans are created. A bean injected with `app.message` afterward can receive `from-initializer` according to precedence.

Note that certain special properties affecting `SpringApplication` itself or logging **are read earlier than the initializer stage**. If you need to influence those very early settings, use a configuration mechanism loaded at the appropriate time, such as Config Data, the command line, or an `EnvironmentPostProcessor`.

### 14.2. EnvironmentPostProcessor

Spring Boot provides the `EnvironmentPostProcessor` extension point to customize `Environment` while preparing the application.

Conceptual example:

```java
package com.example.demo.bootstrap;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class CustomEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "custom-defaults",
                        Map.of("app.feature.enabled", "false")
                )
        );
    }
}
```

For this extension point to be loaded, the library must register the implementation using the corresponding Spring Boot mechanism, commonly an `EnvironmentPostProcessor` entry in `META-INF/spring.factories`.

You do not need to write an `EnvironmentPostProcessor` just to read `application.yml`. It is a tool for infrastructure libraries or specialized bootstrap requirements.

## 15. Demo: Environment can change while @Value keeps the old value

The following example intentionally modifies an **in-memory** `PropertySource` after the context has refreshed. The goal is to observe the difference between a fresh lookup and a previously injected value.

### 15.1. application.yml

```yaml
app:
  greeting:
    message: "from-yaml"
```

### 15.2. Bean receiving the value via @Value

```java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingSnapshot {

    private final String message;

    public GreetingSnapshot(
            @Value("${app.greeting.message}") String message
    ) {
        this.message = message;
    }

    public String message() {
        return message;
    }
}
```

### 15.3. Runner adding a property source at runtime

```java
package com.example.demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.boot.CommandLineRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.stereotype.Component;

@Component
public class RuntimePropertyDemo implements CommandLineRunner {

    private final ConfigurableEnvironment environment;
    private final GreetingSnapshot snapshot;

    public RuntimePropertyDemo(
            ConfigurableEnvironment environment,
            GreetingSnapshot snapshot
    ) {
        this.environment = environment;
        this.snapshot = snapshot;
    }

    @Override
    public void run(String... args) {
        System.out.println("Before: "
                + environment.getProperty("app.greeting.message"));
        System.out.println("Snapshot: " + snapshot.message());

        ConcurrentMap<String, Object> values =
                new ConcurrentHashMap<>();
        values.put("app.greeting.message", "from-runtime-map");

        environment.getPropertySources().addFirst(
                new MapPropertySource("runtime-overrides", values)
        );

        System.out.println("After: "
                + environment.getProperty("app.greeting.message"));
        System.out.println("Snapshot: " + snapshot.message());
    }
}
```

With the example and precedence above, illustrative output is:

```text
Before: from-yaml
Snapshot: from-yaml
After: from-runtime-map
Snapshot: from-yaml
```

Reason:

- `Environment#getProperty(...)` performs a fresh resolution across the current PropertySources collection.
- `GreetingSnapshot` holds the value Spring injected when creating the bean.
- Adding a runtime source does not tell Spring to recreate `GreetingSnapshot`.

### 15.4. This is not a complete dynamic configuration mechanism

This example only illustrates `Environment`'s lookup behavior. In a production application, modifying property sources requires considering:

- Concurrency across threads.
- Validation and atomic updates for related property groups.
- Access control and auditing when configuration changes.
- Side effects on components that may read properties at different times.
- Previously bound/configured beans not being updated.
- Properties used during startup not being re-applied automatically.

If you need dynamic runtime configuration, design a configuration service or cache with a clear contract, or use an appropriate dynamic configuration tool.

## 16. Why does editing application.yml while the app is running usually have no effect?

Suppose the application is running with:

```yaml
app:
  client:
    timeout: 5s
```

You edit the file to:

```yaml
app:
  client:
    timeout: 10s
```

In standard Spring Boot, Config Data files were already read and placed into PropertySources during startup. Spring Boot **does not by default watch every YAML file on disk to reload it immediately**.

Therefore:

- `Environment#getProperty("app.client.timeout")` may still return `5s` because the PropertySource holds the previously loaded data.
- A `@ConfigurationProperties` bean may still hold `Duration.ofSeconds(5)`.
- A `@Value` field still holds the previously injected value.
- A `@ConditionalOnProperty` condition is not automatically re-evaluated to create or destroy beans.

To apply `10s` in the straightforward way, restart the application after editing the configuration or roll out a new configuration version per your operational workflow.

### 16.1. Cases where a source actually changes

If a `PropertySource` is built to read from a source that changes over time, or code actively modifies an in-memory map, subsequent `Environment#getProperty(...)` calls **can** see the new value.

That applies only to sources with such dynamic behavior. Do not infer that every `PropertySource` behaves this way automatically.

### 16.2. System.setProperty can differ from editing the OS environment

For example:

```java
System.setProperty("app.message", "new-system-value");

String now = environment.getProperty("app.message");
```

If no higher-precedence source overrides it, `Environment` can see the new value from Java system properties. This is a change inside the current JVM.

Conversely, running `export APP_MESSAGE=...` in another shell after the JVM has started does not automatically alter the environment of the running Java process.

## 17. Conditions, @Profile, and values at bean registration time

A condition can use `Environment` to decide which beans are registered:

```java
@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.feature",
            name = "enabled",
            havingValue = "true"
    )
    public FeatureService featureService() {
        return new FeatureService();
    }
}
```

If `app.feature.enabled=false` when the condition is evaluated, the bean definition from the method above is not registered.

Changing a `PropertySource` to `true` after the context is ready **does not automatically make Spring re-run the condition and register FeatureService**.

Similarly, `@Profile("prod")` is evaluated while processing configuration. Changing the active profiles list after context initialization does not automatically create beans that were previously skipped.

### 17.1. Distinguishing three points in time

| Operation | Typical timing | When a property changes after startup |
|---|---|---|
| `@ConditionalOnProperty` | While processing configuration/bean definitions | Not automatically re-evaluated |
| `@Value` and `@ConfigurationProperties` | When the bean is created or binding occurs | Not automatically re-injected/rebound |
| `Environment#getProperty` | When the method is called | Can see the change if the underlying source actually changed |

This is an essential table when debugging configuration-driven feature toggles.

### 17.2. When to use runtime feature flags?

If the business requirement is to enable or disable a feature **without restarting**, bean-registration conditions are usually not suitable.

Keep the bean/service in existence, and have it consult a controlled, mutable feature flag source:

```java
@Service
public class NotificationService {

    private final FeatureFlagService flags;

    public NotificationService(FeatureFlagService flags) {
        this.flags = flags;
    }

    public void notifyUser(String message) {
        if (!flags.isEnabled("notification")) {
            return;
        }

        // Perform notification delivery.
    }
}
```

`FeatureFlagService` in this example is an application-provided abstraction. Implementing and managing its updates is a separate runtime concern, not the default behavior of `@ConditionalOnProperty`.

## 18. Config import and multi-file configuration

Spring Boot supports importing Config Data via `spring.config.import`.

For example:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"

app:
  greeting:
    message: "from-main-file"
```

External file:

```yaml
# ./config/extra.yml
app:
  greeting:
    message: "from-imported-file"
```

When the import is resolved, the imported file can contribute a `PropertySource` with higher precedence than the document that declared the import according to Config Data rules.

### 18.1. What is optional:?

The `optional:` prefix allows the application to continue if the specified configuration location does not exist, rather than failing startup because the Config Data resource was not found.

For example:

```yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
```

If `extra.yml` is absent, Boot can skip that optional location.

This is useful when a configuration file only exists in certain environments. However, for mandatory configuration such as essential connection details, marking it optional can hide deployment mistakes. Choose based on system requirements.

### 18.2. Config import is not runtime refresh

Importing an external file only causes Spring Boot to load it during Config Data processing. It **does not turn the file into a continuously watched and reloaded source**.

If an operator edits an imported file after startup, a restart or a dedicated refresh mechanism is normally still required.

## 19. @PropertySource: adding a source from Java configuration

Spring Framework allows:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;

@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy.properties")
public class LegacyPropertiesConfiguration {
}
```

File example:

```properties
# src/main/resources/legacy.properties
legacy.feature.enabled=true
```

When the configuration class is processed, Spring adds the corresponding `PropertySource` so `Environment` can resolve the `legacy.feature.enabled` key.

### 19.1. When to use @PropertySource?

Useful when integrating a `.properties` file from a legacy library, or when Java configuration intentionally adds a property resource.

However, it is not the default choice for new Spring Boot application configuration. `application.yml` and Config Data handle profiles, external config, and bootstrap requirements much better.

### 19.2. @PropertySource does not automatically support YAML like application.yml

By default, `@PropertySource` uses a property source factory suited for Java properties and does not provide YAML parsing the way Spring Boot loads `application.yml`.

To read YAML via `@PropertySource`, you need a custom `PropertySourceFactory` or Config Data; for typical Boot applications, prefer Config Data over writing a custom YAML loader.

### 19.3. Some configuration is needed very early

Values controlling `SpringApplication` itself or logging are read early. `@PropertySource` is processed during context refresh, so it may be too late to affect them.

For instance, when configuring `spring.main.banner-mode` or startup logging properties, use `application.yml`/`application.properties`, command-line arguments, environment variables, or an appropriate bootstrap source.

## 20. Inspecting the actual PropertySources present

When you need to determine why a property is being overridden, you can inspect the list of sources currently in `ConfigurableEnvironment`.

```java
package com.example.demo.diagnostics;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceNamesPrinter implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public PropertySourceNamesPrinter(
            ConfigurableEnvironment environment
    ) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Available PropertySources:");

        for (PropertySource<?> source :
                environment.getPropertySources()) {
            System.out.println("- " + source.getName());
        }
    }
}
```

Sample log of source names might contain:

```text
commandLineArgs
systemProperties
systemEnvironment
...
```

**Actual source names may vary across Spring Boot versions and application types.** Do not hard-code diagnostics around a specific file name or source name without verifying the running context.

### 20.1. Why print only source names and not all values?

PropertySources can contain:

- Database passwords.
- API tokens.
- OAuth client secrets.
- Private keys or service access credentials.
- Internal endpoint configurations.

Printing all property values to stdout or logs can leak secrets. When diagnosing issues, prefer printing the list of source names and querying only **identified non-sensitive keys**.

### 20.2. If you want to see which source wins

For a safe key like `app.greeting.message`, you can print `Environment`'s resolved value:

```java
System.out.println(
        environment.getProperty("app.greeting.message")
);
```

Then inspect the relevant sources. However, calling `source.getProperty(key)` directly on individual sources does not always reproduce all of Boot's relaxed binding or adapter logic. Therefore, do not write an overly simplistic manual debugger and treat its output as an absolute answer.

For modern Boot versions, Actuator and origin-aware APIs can provide more accurate information.

## 21. Actuator and the origin of a property

Spring Boot Actuator provides useful endpoints for investigating configuration:

- `/actuator/env`: `Environment` information and property sources according to how they are configured/exposed.
- `/actuator/configprops`: information about `@ConfigurationProperties` beans and observable bound data.
- `/actuator/conditions`: condition evaluation report, helping determine why an auto-configuration was applied or excluded.

To use them, the application needs the Actuator dependency and appropriate endpoint exposure and security configuration.

### 21.1. Actuator does not automatically expose every value

Configuration endpoints have sanitization mechanisms or value display policies. Depending on the Boot version, values may be masked, and permitting value display requires explicit configuration.

Do not enable full display of all config values in production just to debug a single property. Configuration data can contain secrets; endpoints must be protected with appropriate authentication, authorization, and network policies.

### 21.2. Looking at origin to find bugs

For some properties, Spring Boot tracks **origin** information, such as the configuration file and line from which the value was read.

This information helps answer:

- Is the value coming from `application-prod.yml` or `application.yml`?
- Is an external file outside the JAR overriding the packaged value?
- Is an environment variable being applied?
- Which profile is contributing the configuration source?
- Is a test property or command-line argument overriding it?

Not every `PropertySource` supports origin tracking at the same level of detail. Rely on the origin information actually reported by the tooling rather than guessing from source names.

## 22. Spring Boot externalized configuration and checking differences between environments

One JAR artifact can behave differently locally and in production due to different configuration sources.

Local example:

```yaml
# application.yml
app:
  payment:
    mode: sandbox
```

Production:

```bash
APP_PAYMENT_MODE=live java -jar demo.jar
```

Or the container deployment supplies the `APP_PAYMENT_MODE=live` environment variable.

Even with the exact same JAR, `Environment#getProperty("app.payment.mode")` can return `sandbox` locally and `live` in production.

### 22.1. Workflow for debugging an unexpected value

1. **Identify the canonical key** the application is reading, such as `app.payment.mode`.
2. **Check the effective value** via `Environment` or safe diagnostic tools.
3. **Identify active profiles**.
4. **Inspect the PropertySources order** and the sources that might supply that key.
5. **Check command-line arguments** passed when starting the process.
6. **Check Java system properties** passed with `-D...`.
7. **Check OS environment variables** and name mapping.
8. **Check external configuration files and imports**.
9. **Check when the property was injected/bound**.
10. **Determine whether runtime refresh is expected**; if so, inspect the actual refresh mechanism.

Do not simply open `application.yml` and conclude that the runtime value must match the file. A property in the file may already have been overridden by a higher-precedence source.

### 22.2. Avoiding unintended overrides with a "defaults" source

For example:

```java
configurableEnvironment.getPropertySources().addFirst(
        new MapPropertySource(
                "defaults",
                Map.of("app.payment.mode", "sandbox")
        )
);
```

Even though the source is named `defaults`, `addFirst` gives it high precedence in the current set. As a result, it can override `APP_PAYMENT_MODE=live` supplied by production, leading to dangerous behavior.

If you truly want defaults, use the default properties mechanism or place the source at an appropriate precedence level. **A source's name does not determine precedence; its position in PropertySources does.**

## 23. Configuration data sources in integration tests

Tests often need to override configuration without affecting production.

Common approaches include:

```java
@SpringBootTest(properties = {
        "app.feature.enabled=true",
        "app.client.retries=1"
})
class FeatureIntegrationTest {
}
```

Or:

```java
@TestPropertySource(properties = {
        "app.feature.enabled=true"
})
class FeatureIntegrationTest {
}
```

For dynamic values like a test container database port, Spring Test supports `@DynamicPropertySource`:

```java
@DynamicPropertySource
static void databaseProperties(
        DynamicPropertyRegistry registry
) {
    registry.add(
            "app.database.port",
            () -> testContainer.getMappedPort(5432)
    );
}
```

These are ways to add property sources for testing. They usually have precedence designed to override normal application config.

### 23.1. Test properties vs. runtime refresh

`@DynamicPropertySource` supplies a property source for preparing the test context; it does not mean all bound beans will automatically change when external data changes.

Similarly, `@SpringBootTest(properties = ...)` only takes effect inside the test context created by the test framework. It does not modify the application's `application.yml` file.

### 23.2. Testing the effective value

A simple test:

```java
@SpringBootTest(properties = "app.mode=test")
class EnvironmentTest {

    @Autowired
    private Environment environment;

    @Test
    void readsOverriddenMode() {
        assertThat(environment.getProperty("app.mode"))
                .isEqualTo("test");
    }
}
```

This example assumes the project has JUnit, AssertJ, and Spring Boot test dependencies. The test shows that a test configuration source can override a value from the application's file.

## 24. Common errors and misconceptions

| Symptom | Possible cause | What to check |
|---|---|---|
| `application.yml` says `false` but the app reads `true` | Higher-precedence OS env, system property, or CLI | Check PropertySources and effective value |
| Edited YAML file after startup with no visible change | Config Data does not auto-reload files | Restart or use a purpose-built refresh mechanism |
| `Environment#getProperty` sees the new value, but `@Value` is still old | Field/constructor injected once | Distinguish live lookup from snapshot |
| `@ConfigurationProperties` does not change after runtime override | Object was bound earlier | Do not expect automatic rebinding |
| `@ConditionalOnProperty` does not create bean after property changes | Condition was evaluated during bean registration | Use a runtime feature flag if dynamic toggling is needed |
| Property does not resolve when environment variable is set | Wrong name mapping or variable not in process environment | Check relaxed binding and process environment |
| Used `@PropertySource` for YAML but it does not parse properly | Annotation does not use Config Data YAML parser automatically | Use `application.yml` or a custom factory |
| Property controlling logging has no effect from `@PropertySource` | Source was added too late during refresh | Use an earlier bootstrap source |
| Added `MapPropertySource` but value does not win | Low-precedence source or higher-precedence source exists | Check `MutablePropertySources` order |
| Used `addFirst` for defaults and accidentally overrode production | Misunderstood precedence | Place defaults in a low-precedence source |
| Local app and container have different values | Different profiles, environment variables, or config files | Compare configuration sources of each process |
| Config secret leaked during debugging | Printed entire Environment or exposed actuator | Restrict logging, apply sanitization and access control |

### 24.1. Do not confuse a missing property with a binding error

If a property does not exist, `getProperty` can return `null` or the specified default.

If a property exists but has an invalid value, type conversion or binding can fail.

For example:

```properties
app.client.retries=abc
```

differs from:

```properties
# app.client.retries is not declared
```

The first case requires fixing the invalid type value; the second case can use an appropriate default or require the mandatory property.

### 24.2. Do not confuse "changing a property" with "reconfiguring an object"

A `DataSource` created from `spring.datasource.*` has usually already opened or configured its pool according to the configuration at initialization time.

Even if `Environment` later returns a new URL, the existing `DataSource` does not automatically close the old pool and build a new pool for that URL.

The same rule applies to HTTP clients, schedulers, bean conditions, and most components configured upon creation. An intentional reconfiguration mechanism or application restart is required.

## 25. Workflow for designing operations-friendly configuration

When building a Spring Boot system, you can apply these principles:

- Use `application.yml` or `application.properties` for readable, properly version-controlled default configuration.
- Use profile-specific Config Data to separate environment differences when genuinely needed.
- Use OS environment variables or external config for values that vary by deployment.
- Do not commit secrets to the repository; use appropriate secret management.
- Use `@ConfigurationProperties` for typed, validatable configuration groups.
- Use `Environment` directly when you need dynamic key lookup or are writing infrastructure/diagnostics.
- Name properties consistently in canonical kebab-case.
- Clearly document defaults, missing-value behavior, and startup conditions.
- Avoid adding a `PropertySource` with overly high precedence without a clear reason.
- Do not assume modifying a config file will automatically update beans.
- If dynamic runtime config is needed, design dedicated update, validation, synchronization, and rollback mechanisms.
- When debugging, inspect the effective value and its origin, not just a single configuration file.

Good configuration can answer three questions: **where does the value come from, when is it read, and does changing it update running objects?**

## 26. Practice exercises

### Exercise 1 — Reading Environment

Create an application with the `app.greeting.message` property in `application.yml`. Inject `Environment` into a `CommandLineRunner` and print the value. Try omitting the property, using a default, and calling `getRequiredProperty`.

### Exercise 2 — Checking precedence

Configure the same `app.mode` key in YAML, an OS environment variable, a Java system property, and a command-line argument. Predict the effective value, run the application, and then remove higher-precedence sources one by one to compare.

### Exercise 3 — Printing PropertySource names

Inject `ConfigurableEnvironment` into a runner and iterate over `getPropertySources()`. Print the **name** of each source, not all values. Compare the list between running locally and running in a container/test.

### Exercise 4 — Comparing @Value and Environment

Create one bean that receives `app.greeting.message` with `@Value` and another bean that reads it via `Environment#getProperty` on every call. Add a `MapPropertySource` at runtime and observe the new value versus the snapshot value.

### Exercise 5 — @ConfigurationProperties

Create a `ClientProperties` record with `endpoint`, `timeout`, and `retries`. Bind it from YAML and inject it into a service. Try setting `retries=abc` to observe the binding error.

### Exercise 6 — Profiles

Create `application.yml` and `application-prod.yml` with different `app.payment.endpoint` values. Run with and without `--spring.profiles.active=prod`, then print the effective value and active profiles.

### Exercise 7 — Config import

Add `spring.config.import=optional:file:./config/extra.yml`. Run when the file exists and when it does not. Observe the imported configuration source and how optional locations are handled.

### Exercise 8 — @PropertySource

Create `legacy.properties` and a `@Configuration` class with `@PropertySource`. Read the key from `Environment`. Compare when the source is added relative to `application.yml`.

### Exercise 9 — Conditional configuration

Create a `@ConditionalOnProperty` for an optional bean. Run with the property set to true/false, then try adding a runtime `MapPropertySource` to see that the condition does not automatically re-run after context refresh.

### Exercise 10 — Inspecting property origins safely

If the project has Spring Boot Actuator, configure and secure the appropriate endpoints to inspect Environment sources. Pick a **non-sensitive** property, find its actual origin/value, and explain why it wins over the remaining sources.

## 27. Official references

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySources, precedence, Config Data, profiles, environment variables, and config imports.
- [Spring Framework Reference — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): how Spring manages properties and profiles.
- [Spring Framework Javadoc — Environment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/Environment.html): API for reading properties and profiles.
- [Spring Framework Javadoc — ConfigurableEnvironment](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html): accessing and modifying PropertySources.
- [Spring Framework Javadoc — PropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/PropertySource.html): abstraction representing a property source.
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties` and binding.
- [Spring Boot Reference — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): inspecting Environment/configuration properties and security considerations.

The core takeaway is that **`Environment` provides property lookup results across prioritized `PropertySource`s**, while the actual values used by the application depend on which sources were loaded, active profiles, query timing, and the lifecycle of the beans using that configuration. A `getProperty` call can observe an updated property source; however, `@Value`, `@ConfigurationProperties`, conditions, and already initialized components are not automatically rebuilt. Understanding this boundary helps you configure Spring Boot consistently, avoid cross-environment discrepancies, and accurately diagnose effective values.

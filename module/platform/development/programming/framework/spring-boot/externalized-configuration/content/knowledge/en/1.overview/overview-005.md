# The Journey from Configuration Source to Values Used by Beans

## 1. The Big Picture

In Spring Boot, a bean often needs values such as external service addresses, timeouts, retry counts, or feature toggle flags. These values vary by deployment environment, while the Java code can stay unchanged.

The key point to understand is: **a bean does not search for and directly read each `application.yml` file or each environment variable on its own**. Spring Boot collects configuration sources, orders them by precedence, enables property lookup, and delivers the resolved values to beans when Spring initializes the application.

You can visualize the journey as follows:

```text
application.yml / application-prod.yml
environment variables / command-line arguments / other sources
                         |
                         v
       Load and organize configuration sources
                  (PropertySource)
                         |
                         v
                Spring Environment
        (look up values by property name)
                         |
            +------------+-------------+
            |            |             |
            v            v             v
       @Value       Environment    @ConfigurationProperties
     placeholder     .getProperty      + Binder
            |            |             |
            +------------+-------------+
                         |
                         v
      Type conversion, constraint checks if configured
                         |
                         v
         Properties/configuration object in bean
                         |
                         v
              Used by business code
```

The diagram depicts the **conceptual flow**. For example, the `Binder` mechanism for `@ConfigurationProperties` works against the property sources normalized by Spring Boot from `Environment`; do not assume every branch must sequentially invoke an `Environment.getProperty()` method.

## 2. Starting with a Concrete Property

Suppose an application has a notification feature. The notification bean needs to know the timeout and enabled/disabled state. In `src/main/resources/application.yml`:

```yaml
checkout:
  notification:
    enabled: true
    timeout: 3s
```

We have two properties:

- `checkout.notification.enabled`: whether the feature is enabled.
- `checkout.notification.timeout`: timeout when calling the notification service.

The property name is the address Spring uses to locate the value. `3s` represents a duration of three seconds; Java code can receive a `Duration` object instead of manually parsing the string `"3s"`.

The same key can be declared from other sources. For instance, before running the application on Linux/macOS:

```bash
export CHECKOUT_NOTIFICATION_TIMEOUT=5s
java -jar app.jar
```

In PowerShell:

```powershell
$env:CHECKOUT_NOTIFICATION_TIMEOUT = "5s"
java -jar app.jar
```

Or pass an argument directly at launch:

```bash
java -jar app.jar --checkout.notification.timeout=2s
```

For this key, the environment variable spelling `CHECKOUT_NOTIFICATION_TIMEOUT` can map to `checkout.notification.timeout`. In a typical scenario involving only the three sources above, the command-line argument `2s` takes precedence over the environment variable `5s`, and the environment variable takes precedence over `application.yml` with `3s`.

That does not mean Spring sums the three timeouts or creates three bean instances. **Spring resolves a single effective value for the requested key**, based on the precedence order of participating sources.

## 3. From Files and Environment Variables to PropertySource

When `SpringApplication.run(...)` is called, Spring Boot prepares the `Environment` for the application. During startup, the Config Data mechanism finds and loads appropriate application configuration files, including profile-specific configuration for active profiles. Sources such as OS environment variables and command-line arguments are also added to the property system.

A `PropertySource` can be understood as a named source that knows how to return a value for a property key. `Environment` manages multiple such sources and provides value lookup taking precedence into account.

Example:

```text
Key to look up: checkout.notification.timeout

Command-line argument    -> 2s
Environment variable     -> 5s
application.yml          -> 3s

Typical lookup result    -> 2s
```

The table above illustrates a simple case, not Spring Boot's complete precedence list. In real applications there may also be profile-specific configuration, imported files, test properties, and other sources. A higher-precedence source determines the value when multiple sources supply the same key.

If you create `application-prod.yml`:

```yaml
checkout:
  notification:
    timeout: 10s
```

and activate the profile via `--spring.profiles.active=prod`, `prod`-specific configuration can override base values in `application.yml`. However, a direct command-line argument `--checkout.notification.timeout=2s` can still override the timeout from the profile file. Therefore, **profiles determine which configurations are loaded; precedence order determines which value wins when keys collide**.

`Environment` also reports which profiles are active. Distinguish two separate actions: selecting configuration sources during startup, and reading property values when creating beans.

## 4. Three Ways to Bring Values into Java Code

Once a property can be looked up, application code typically uses one of the following three approaches. All three rely on Spring's configuration system, but serve different needs.

### 4.1. Direct Lookup via Environment

A bean can receive `Environment` through dependency injection:

```java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class NotificationConfigReader {
    private final Environment environment;

    public NotificationConfigReader(Environment environment) {
        this.environment = environment;
    }

    public String timeoutText() {
        return environment.getProperty(
            "checkout.notification.timeout",
            "3s"
        );
    }
}
```

`getProperty(key, defaultValue)` looks up the value by key; if absent, it returns the default value. This example returns a `String`. `Environment` also has overloads supporting target types, but when a configuration group is used across multiple places, reading each key manually tends to scatter code and hurt maintainability.

This approach fits when you need flexible lookup of a few keys, or when inspecting/checking effective values.

### 4.2. Injecting a Single Value with @Value

Spring supports `${...}` placeholders inside `@Value`:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class NotificationSwitch {
    private final boolean enabled;

    public NotificationSwitch(
            @Value("${checkout.notification.enabled:true}")
            boolean enabled) {
        this.enabled = enabled;
    }

    public boolean isEnabled() {
        return enabled;
    }
}
```

When creating `NotificationSwitch`, Spring evaluates the placeholder, retrieves the effective value, converts it to `boolean`, and passes it to the constructor. In the expression `${checkout.notification.enabled:true}`, the part after the colon is the default value `true` if the property is not found.

`@Value` is convenient for one or two standalone properties. For many related properties, repeating string keys throughout Java code becomes harder to rename and manage than a strongly typed configuration object. Write placeholder keys in canonical lowercase form, hyphen-separated where needed, for better compatibility with Spring Boot property naming rules.

### 4.3. Binding an Entire Group with @ConfigurationProperties

For a group of configuration settings serving the same feature, `@ConfigurationProperties` establishes a clear boundary between configuration and business code.

Example with Spring Boot 3:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout.notification")
public record NotificationProperties(
        boolean enabled,
        Duration timeout
) {}
```

To have Spring register this type as a bean, enable configuration scanning on the startup class in an appropriate parent package:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
```

Spring Boot can then create a `NotificationProperties` bean. The binding mechanism matches `checkout.notification.enabled` to the `enabled` component and `checkout.notification.timeout` to the `timeout` component. The value `"3s"` is converted into `Duration.ofSeconds(3)`. For a single-constructor `record` as in this example, Spring Boot 3 can use that constructor for binding without adding `@ConstructorBinding`.

A business bean simply injects the configuration object:

```java
import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public boolean shouldSendNotification() {
        return properties.enabled();
    }

    public Duration requestTimeout() {
        return properties.timeout();
    }
}
```

`NotificationService` does not need to know whether values originated from YAML, environment variables, or command-line arguments. It uses a Java dependency prepared by Spring. This is a major benefit of externalized configuration: **changing where values are supplied without modifying business logic**.

In applications with many configurations, register the right `@ConfigurationProperties` classes and keep each group close to its functional domain. You can use `@EnableConfigurationProperties(NotificationProperties.class)` instead of package-wide scanning when explicit registration is preferred.

## 5. What Happens During Binding?

Binding is not merely copying text from YAML into Java fields. Conceptually it performs several steps:

1. Identify the prefix, such as `checkout.notification`.
2. Locate child properties from effective sources.
3. Match configuration names to Java member names, with support for `@ConfigurationProperties` *relaxed binding* rules.
4. Convert source values to target types, such as string `"3s"` into `Duration`, or `"true"` into `boolean`.
5. Construct and provide the configuration object to dependent beans; if validation constraints are configured on the properties, validation runs according to the declared mechanism.

Relaxed binding allows conventions suitable for each source. For example, the property `checkout.notification.timeout` can receive its value from the environment variable `CHECKOUT_NOTIFICATION_TIMEOUT`. For names containing hyphens, the convention for environment variables is typically replacing dots with underscores, removing hyphens, and converting to uppercase; for example `checkout.retry.max-attempts` maps to `CHECKOUT_RETRY_MAXATTEMPTS`.

Do not infer that every syntax behaves identically across every API: group binding with `@ConfigurationProperties` and resolving an arbitrary placeholder in `@Value` have differences. Writing canonical property names from the start helps avoid lookup failures.

If a value cannot be converted to the declared type, binding can fail at startup and produce an error message citing the property name, value, or target type. For example, `checkout.notification.timeout=hello` does not represent a valid `Duration` as expected in this example. Failing early like this is usually preferable to silently running with broken configuration until the first request arrives.

If you want to require that a value be present, you can add Bean Validation constraints to the `@ConfigurationProperties` class, use `@Validated` and appropriate annotations, and ensure the application includes the required validation library. Choosing whether to provide a default or require a value is a functional design decision, not an inherent trait of every configuration source.

## 6. Timing Order: When Do Beans Receive Values?

A typical startup sequence:

```text
1. Call SpringApplication.run(...)
2. Prepare Environment and determine effective configuration sources
3. Process Config Data and relevant profiles
4. Create/refresh ApplicationContext, register bean definitions
5. Instantiate beans; resolve @Value and bind @ConfigurationProperties
6. Inject dependencies and complete bean lifecycle
7. Application begins handling work using supplied values
```

The sequence above is simplified to trace the path of a value; in practice, bean post-processing, auto-configuration conditions, and lifecycle callbacks interleave.

An important consequence: editing `application.yml` on disk after the application has started **does not automatically** update values in `NotificationProperties` or `@Value` fields. A process's environment variables are also typically set prior to launch. To apply new configuration, the usual approach is restarting the application or using a dedicated configuration refresh mechanism. Do not assume calling a business method again reloads YAML.

Also understand source loading timing: some properties are used very early by Spring Boot to configure startup itself. Sources added via `@PropertySource` during context processing may arrive too late for early properties such as certain logging settings. Therefore, Config Data sources and environment variables are generally better suited for application startup configuration.

## 7. Tracing a Value from Start to Finish

Consider the scenario:

```yaml
# application.yml
checkout:
  notification:
    enabled: true
    timeout: 3s
```

The host running the application supplies:

```text
CHECKOUT_NOTIFICATION_TIMEOUT=5s
```

Launch command:

```bash
java -jar app.jar --checkout.notification.timeout=2s
```

Trace `NotificationService.requestTimeout()`:

| Stage | What Is Observed |
| --- | --- |
| Sources | YAML provides `3s`, environment variable provides `5s`, command line provides `2s` |
| Loading | Spring Boot adds the applicable sources to the configuration system |
| Lookup | For the sources in this example, the effective value of `checkout.notification.timeout` is `2s` |
| Binding | `NotificationProperties.timeout` receives a `Duration` of two seconds |
| Injection | `NotificationService` receives the `NotificationProperties` bean |
| Usage | `requestTimeout()` returns `Duration.ofSeconds(2)` |

If the command-line argument is omitted, the result in the same scenario is five seconds. If the environment variable is also omitted, the result is three seconds. **No Java source code changes** across all three runs.

This is the best verification exercise when learning: keep the bean unchanged and swap one source at a time. It clarifies the boundaries between *configuration source*, *effective value*, *type-safe binding*, and *bean usage*.

## 8. Diagnosing When a Bean Receives an Unexpected Value

When the observed timeout differs from `3s` in YAML, trace the journey in reverse:

1. **Which key is the bean reading?** Check the `@ConfigurationProperties` `prefix`, Java member names, and `@Value` placeholders. A single typo is enough to miss the key.
2. **Which source is supplying the value?** Check command-line arguments, environment variables, profile-specific config, and imported sources. Do not open only `application.yml` and assume the final value.
3. **Which profiles are active?** Check how profiles are selected and which configuration files accompany them. `application-prod.yml` does not take effect simply by existing.
4. **Is there a type conversion or binding error?** Read startup logs for the property name and target type such as `Duration`, `int`, or `boolean`. Distinguish "property not found" from "found but failed type conversion."
5. **When was the value captured?** For an already initialized bean, editing a file at runtime does not guarantee the bean updates.
6. **Are two different reading mechanisms in use?** Compare `Environment`, `@Value`, and `@ConfigurationProperties`; verify canonical key names, defaults, and call timing.

When Spring Boot Actuator is installed and appropriate endpoints are enabled, `/actuator/env` and `/actuator/configprops` can help inspect sources and bound configuration. Follow your application's security policy because properties may hold secrets; never expose these endpoints publicly or log sensitive values just to debug.

Do not fix configuration issues by hard-coding the desired outcome inside a bean. Doing so hides the root cause and makes other environments behave inconsistently.

## 9. Hands-On Practice

Keep `NotificationProperties` and `NotificationService` from above, then try four application launches:

| Run | Condition | Expected Value of `requestTimeout()` |
| --- | --- | --- |
| 1 | Only `application.yml` declaring `3s` | 3 seconds |
| 2 | Add environment variable `CHECKOUT_NOTIFICATION_TIMEOUT=5s` | 5 seconds |
| 3 | Keep environment variable and add `--checkout.notification.timeout=2s` | 2 seconds |
| 4 | Remove both environment variable and override argument; change YAML to `7s` and restart | 7 seconds |

To observe the result, you can call `requestTimeout().toSeconds()` in a snippet that runs after context initialization. Only print non-sensitive test properties; never apply this approach to passwords or tokens.

After each run, ask yourself: **which source did the value come from, why did that source win, at which step was the string converted to `Duration`, and which bean actually used it?**

Once you can answer those four questions, you understand the core path of externalized configuration: **configuration sources → PropertySource/Environment → lookup and binding/conversion → bean dependency → application behavior**.

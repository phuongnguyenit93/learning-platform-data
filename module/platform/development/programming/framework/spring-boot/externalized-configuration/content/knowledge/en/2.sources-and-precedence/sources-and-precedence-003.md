# Default Configuration Using `SpringApplication.setDefaultProperties`

In Spring Boot, the same property can be declared in multiple sources: Java startup code, `application.properties`/`application.yml`, environment variables, Java system properties, or command-line arguments. `SpringApplication.setDefaultProperties(...)` gives an application **application-wide fallback values** that external configuration sources can still override.

This lesson uses Spring Boot 3.3.x and Java 21. The focus is on how to declare default values, when they apply, and their precedence order.

## 1. What Does `setDefaultProperties` Do?

`SpringApplication` provides two overloads:

~~~java
void setDefaultProperties(Map<String, Object> defaultProperties);
void setDefaultProperties(Properties defaultProperties);
~~~

The key/value pairs are added to the Spring `Environment` under a property source named `defaultProperties`. This is the **lowest-precedence source** in Spring Boot's normal configuration order. If a higher-precedence source provides the same key, the value from that source is used.

For example, when the default property is `server.port=8081` while `application.properties` contains `server.port=8082`, the web application runs on port `8082`. If you also start it with `--server.port=9090`, the effective port is `9090`.

Key points:

- Default values are only used when no higher-precedence source provides a value for the same key.
- These values are supplied before the application starts; they do not modify configuration files on disk.
- They can be read via `Environment`, injected with `@Value`, or bound via `@ConfigurationProperties` like other Spring properties.
- They should not be used to enforce production-specific configuration or embed sensitive secrets.

## 2. Runnable Example: Declaring Before `run(args)`

Suppose a Spring Boot application has `spring-boot-starter` and `spring-boot-starter-web` in its dependencies. Create the startup class:

~~~java
package com.example.configdemo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ConfigDemoApplication.class);

        Map<String, Object> defaults = new LinkedHashMap<>();
        defaults.put("spring.application.name", "config-demo");
        defaults.put("server.port", 8081);
        defaults.put("demo.message", "Hello from defaultProperties");
        defaults.put("demo.retry-count", 3);

        // Must be set before SpringApplication.run is called.
        application.setDefaultProperties(defaults);
        application.run(args);
    }

    @Bean
    ApplicationRunner showEffectiveConfiguration(Environment environment) {
        return args -> {
            System.out.println("demo.message = "
                    + environment.getProperty("demo.message"));
            System.out.println("demo.retry-count = "
                    + environment.getProperty("demo.retry-count", Integer.class));
            System.out.println("server.port = "
                    + environment.getProperty("server.port", Integer.class));
        };
    }
}
~~~

When none of those keys are declared in other sources, the program prints output similar to:

~~~text
demo.message = Hello from defaultProperties
demo.retry-count = 3
server.port = 8081
~~~

`Environment.getProperty("demo.retry-count", Integer.class)` demonstrates typed reading; in this example the value `3` is placed into the `Map` as an integer. In an application without a web server, the `server.port` property can still reside in `Environment` without automatically opening a listening port.

**Why instantiate `SpringApplication`?** The shorthand call `SpringApplication.run(ConfigDemoApplication.class, args)` runs the application immediately. To set default values before startup, instantiate `SpringApplication`, configure it, and only then call `application.run(args)`.

## 3. Comparing Default Values with External Configuration

Keep the Java program in section 2 unchanged. Create `src/main/resources/application.properties`:

~~~properties
demo.message=Hello from application.properties
server.port=8082
~~~

On a normal startup, the two keys in the file override the values from `setDefaultProperties`; `demo.retry-count` is absent from the file, so it still receives `3` from the Java code:

~~~text
demo.message = Hello from application.properties
demo.retry-count = 3
server.port = 8082
~~~

Next, run the JAR with command-line arguments (replace `config-demo.jar` with the actual JAR name):

~~~bash
java -jar config-demo.jar --demo.message="Hello from CLI" --server.port=9090
~~~

Then:

~~~text
demo.message = Hello from CLI
demo.retry-count = 3
server.port = 9090
~~~

The following table describes the precedence order **for the same key** across common Spring Boot 3.3 sources; sources in lower rows override sources in upper rows:

| Configuration Source | Example | Role |
| --- | --- | --- |
| Default properties | `application.setDefaultProperties(...)` | Lowest fallback values |
| Config data | `application.properties`, `application.yml`, profile-specific files | Application and environment configuration |
| OS environment variables | `DEMO_MESSAGE` | Deployment-time configuration |
| Java system properties | `-Ddemo.message=...` | JVM arguments |
| Command-line arguments | `--demo.message=...` | Run-specific overrides |

This is an abridged table, not the complete list of `PropertySource` instances. Spring Boot also supports `@PropertySource`, `SPRING_APPLICATION_JSON`, test-supplied properties, and several other sources. Test sources such as `@TestPropertySource` can have even higher precedence than command-line arguments. Among the sources listed in the table, `setDefaultProperties` is always in the fallback position.

### Same Key Across Multiple Sources

Suppose:

~~~text
setDefaultProperties    demo.message = "A"
application.properties  demo.message = "B"
environment variable    DEMO_MESSAGE = "C"
command-line argument   --demo.message=D
~~~

The effective value is `D`. If you omit the command-line argument, the result is `C`; if you also omit the environment variable, the result is `B`; `A` is only used when no higher-precedence source declares that key.

Note: property handling in Spring Boot also involves name-binding rules and profile-specific configuration. In this example, `DEMO_MESSAGE` is the environment variable form of the `demo.message` key.

## 4. Reading Configuration at Point of Use

### Via `Environment`

This is the direct way to observe the **resolved value after precedence is applied**:

~~~java
@Component
class MessagePrinter {

    private final Environment environment;

    MessagePrinter(Environment environment) {
        this.environment = environment;
    }

    String currentMessage() {
        return environment.getProperty("demo.message");
    }

    int retryCount() {
        return environment.getRequiredProperty("demo.retry-count", Integer.class);
    }
}
~~~

You need to import `org.springframework.stereotype.Component` and `org.springframework.core.env.Environment`. `getRequiredProperty` throws an error when a required key is missing, whereas `getProperty` can return `null` if not found.

### Via `@Value`

A bean can also receive the same effective value:

~~~java
@Component
class MessageService {

    @Value("${demo.message}")
    private String message;

    String message() {
        return message;
    }
}
~~~

Import `org.springframework.beans.factory.annotation.Value` and `org.springframework.stereotype.Component`. The `${demo.message}` placeholder pulls the value from `Environment`; when a file or command-line argument overrides it, the bean receives the overridden value.

### Via `@ConfigurationProperties`

For multiple related keys, bind them into a strongly typed configuration object:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoSettings(String message, int retryCount) {
}
~~~

Register the class with `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(DemoSettings.class)`. `demo.retry-count` is then bound to `retryCount`; initial values can come from `setDefaultProperties` and be overridden by other sources. This approach scales better than scattering many `@Value` annotations as configuration grows.

## 5. Using the `Properties` Overload

If your input is already a `java.util.Properties` object, you can pass it directly:

~~~java
SpringApplication application = new SpringApplication(ConfigDemoApplication.class);

Properties defaults = new Properties();
defaults.setProperty("demo.message", "Default value");
defaults.setProperty("demo.retry-count", "3");

application.setDefaultProperties(defaults);
application.run(args);
~~~

Import `java.util.Properties`. This is an **alternative** to the `Map` snippet, not an extra call needed in the same example. `Properties` stores string values; Spring provides conversion when binding to the target type.

When values are built directly in Java code, `Map<String, Object>` is usually easier to read and allows passing numbers and booleans alongside strings. When you already have a `Properties` instance, the second overload avoids manual conversion.

## 6. When Should You Use It?

**Application fallback values:** setting the application name, safe business-logic options, or default retry limits. Deployment environments can adjust them via files or environment variables.

**Launching a shared program:** multiple launchers can create a `SpringApplication` and assign corresponding defaults, while still accepting operator configuration.

**Reducing repetition of optional settings:** instead of forcing every environment to declare `demo.retry-count`, you can put the default value in one place. However, for ordinary business configuration properties, declaring them in `application.yml` is usually easier to track and adjust.

Example of general values:

~~~java
Map<String, Object> defaults = Map.of(
        "demo.retry-count", 3,
        "demo.feature-enabled", false,
        "demo.batch-size", 100
);
application.setDefaultProperties(defaults);
~~~

Only use defaults that are appropriate for real environments. Sensitive keys such as passwords, tokens, and API keys must be supplied from a secrets management system or an appropriate deployment configuration source.

## 7. Distinguishing from Easily Confused Mechanisms

| Mechanism | Meaning |
| --- | --- |
| `setDefaultProperties(...)` | Adds fallback values to `Environment` at low precedence |
| `application.properties` / `application.yml` | Stores configuration in files, separable by profile or deployment location |
| `@Value("${demo.message:Fallback}")` | Provides a fallback solely for **one placeholder** when resolving it |
| `@ConfigurationProperties` | Binds multiple keys into a typed object; does not itself define precedence order |
| `SpringApplicationBuilder.properties(...)` | Builder API for setting default properties when constructing the application |
| `setAdditionalProfiles(...)` | Adds active profiles; not an API for declaring default key/value pairs |

For example, `@Value("${demo.message:Fallback}")` only provides a fallback at that injection site. By contrast, setting `demo.message` with `setDefaultProperties` puts the value in `Environment` so other components can share it.

## 8. Common Mistakes and How to Diagnose Them

**Setting defaults after `run(args)`.** By then, `Environment` creation, bean binding, and application configuration have already occurred. Call `setDefaultProperties` on the `SpringApplication` instance **before** `run`.

**Mistaking defaults for mandatory values.** If `application.yml` or startup arguments contain the same key, the default value is overridden by design. To find the effective source, inspect the sources providing that key rather than repeatedly editing the value in the `Map`.

**Key name mismatch.** For instance, `demo.retry-count` and `demo.retryCount` can be handled under relaxed binding rules when using `@ConfigurationProperties`, but you should write canonical lowercase hyphenated names for multi-word keys. Check the exact name when using `Environment.getProperty` or placeholders.

**Assuming every CLI argument takes effect.** Normally Spring Boot puts `--key=value` arguments into `Environment`, but an application can disable this mechanism with `setAddCommandLineProperties(false)`. In that case, CLI overrides no longer apply.

**Using fallbacks to mask missing required configuration.** If the application cannot run safely without an endpoint or secret, validate the presence of that configuration instead of providing a dummy default. `setDefaultProperties` is meant for genuinely valid fallback values.

**Diagnosing from a single file.** A value read from a file is not necessarily the effective value. You can use `Environment` to print the final value, or the Actuator `env`/`configprops` endpoints if the application has enabled, secured, and authorized them appropriately.

## 9. Practice Exercises

1. Run the application from section 2, keeping `application.properties` without the three keys `demo.message`, `demo.retry-count`, and `server.port`. Observe the default values.
2. Declare `demo.retry-count=5` in `application.properties`; verify that `Environment` returns `5` while the other keys stay unchanged.
3. Run with `--demo.retry-count=8`; verify that the CLI argument overrides both the file value and the default.
4. Move the `demo.message` line in the file to `application-dev.properties` and start with `--spring.profiles.active=dev`; verify the profile-specific value.
5. Remove all overrides and confirm the program falls back to the values set in `setDefaultProperties`.

If two sources declare the same key and the result differs from your expectation, determine their precedence order and check active profiles alongside startup arguments.

## Key Takeaways

`SpringApplication.setDefaultProperties` is the place to declare **application-wide default values before running**. It gives the application consistent fallbacks while still respecting configuration from files, environment variables, and command-line arguments. This ability to be overridden is intentional in Spring Boot's externalized configuration mechanism.

## References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)

# Disabling the Command-Line Source with `setAddCommandLineProperties(false)` in Spring Boot

## 1. The problem: command-line arguments can override application configuration

Spring Boot lets you separate configuration from Java code. The same application can read properties from `application.yml`, `application.properties`, operating system environment variables, Java system properties, and command-line arguments. By default, application arguments starting with `--`, such as `--server.port=9090`, are converted by Spring Boot into **configuration properties** and added to `Spring Environment`.

Suppose `application.yml` has:

~~~yaml
server:
  port: 8080

app:
  message: from-file
  timeout: 3s
~~~

The application is run with:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=from-cli
~~~

Using the default mechanism, command-line arguments usually have higher precedence than file configuration. Spring Boot sees `server.port=9090` and `app.message=from-cli`. This is convenient for adjusting settings per run, yet a system may want to **avoid using `--key=value` arguments as a configuration source**.

Spring Boot provides the method:

~~~java
springApplication.setAddCommandLineProperties(false);
~~~

This method disables adding the **command-line property source** to `Environment`. Arguments are still passed to the program and can still be handled through application argument processing.

> Key takeaway: `setAddCommandLineProperties(false)` does not strip arguments passed to `main(String[] args)`; it changes how Spring Boot **exposes option arguments to the configuration lookup system**.

## 2. How does the default mechanism work?

When calling:

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

Spring Boot initializes the application with default behavior equivalent to `addCommandLineProperties=true`. Option arguments in the form:

~~~text
--server.port=9090
--logging.level.root=DEBUG
--app.timeout=10s
--spring.profiles.active=prod
~~~

can be converted into properties inside a command-line `PropertySource`. `Environment` aggregates multiple `PropertySource` instances in priority order to return the final value of a property name.

Typical model:

~~~text
args passed to main(String[] args)
             |
             v
SpringApplication prepares Environment
             |
             +-- addCommandLineProperties = true
             |          |
             |          v
             |    creates CommandLinePropertySource
             |          |
             |          v
             |    adds to Environment
             |
             v
other sources: system properties, OS environment, config data...
             |
             v
lookup server.port, app.timeout, spring.profiles.active...
             |
             v
binding, auto-configuration, and application beans
~~~

Among Spring Boot's common configuration sources, the approximate order from highest to lowest is:

| Source | Example |
| --- | --- |
| Application arguments in `--key=value` form | `--server.port=9090` |
| Java system properties | `-Dserver.port=9091` |
| Operating system environment variables | `SERVER_PORT=9092` |
| Config data | `application.yml`, `application-prod.yml`, external files outside JAR |
| `SpringApplication` default properties | Fallback configuration supplied programmatically |

The table selects common sources for illustration; in practice Spring Boot also has other sources such as JSON properties, web environments, test sources, and DevTools. Do not assume this table is an exhaustive precedence list across every context.

If CLI, JVM, and file all provide `server.port`, the CLI source can win in default mode. Hence `--server.port=9090` is a quick local override.

## 3. How to disable taking configuration from the command line

### 3.1. Configuring in `main` before running

Replace the static `SpringApplication.run(...)` call by creating a `SpringApplication` instance and setting the property:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        // Do not convert --key=value into a property in Environment.
        application.setAddCommandLineProperties(false);

        application.run(args);
    }
}
~~~

Points to note:

1. Create a `SpringApplication` instance from the application class.
2. Call `setAddCommandLineProperties(false)` **before calling `run(args)`**.
3. Still pass `args` into `run` so the application receives regular arguments.
4. Spring Boot initializes the context, loads config data, performs binding, and creates beans using the remaining configuration sources.

After this change, if you run:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=from-cli
~~~

and `application.yml` still has `server.port=8080`, `app.message=from-file`, then those command-line options **no longer directly override those two properties in `Environment`**. Assuming no other higher-priority source exists, the application uses port `8080` and message `from-file`.

### 3.2. Must be called on the right instance before running

The following example has no effect on the active run:

~~~java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class, args);

    // Too late, and this is also a different SpringApplication instance.
    SpringApplication another =
            new SpringApplication(DemoApplication.class);
    another.setAddCommandLineProperties(false);
}
~~~

To change how `Environment` receives command-line properties, configure **the actual SpringApplication object used to launch** and do so before `run`.

### 3.3. Value `true` and default behavior

If you need to restore the default command-line property handling:

~~~java
application.setAddCommandLineProperties(true);
~~~

Without calling this method, Spring Boot allows command-line option properties into `Environment` by default. You can use `false` when a design intends to prohibit overrides through this channel.

## 4. Disabling the command-line property source does not mean ignoring `args`

This is the easiest distinction to misunderstand in this lesson.

Spring Boot has **two separate flows** for command-line arguments:

- **Configuration:** converting `--key=value` into properties in `Environment` so `@Value`, `@ConfigurationProperties`, and Spring Boot auto-configuration can read them.
- **Application parameters:** passing and parsing `args` for business code via `ApplicationArguments`, `ApplicationRunner`, or `CommandLineRunner`.

`setAddCommandLineProperties(false)` disables the **first flow**, not the second flow.

| Usage | Under default behavior | With `setAddCommandLineProperties(false)` |
| --- | --- | --- |
| `Environment.getProperty("app.mode")` receiving `--app.mode=fast` | Can receive `fast` | Does not receive from that CLI source |
| `@Value` or `@ConfigurationProperties` reading from CLI | Yes | No, unless another source supplies the same property |
| `ApplicationArguments.containsOption("app.mode")` | Can be `true` | Can still be `true` |
| `ApplicationArguments.getOptionValues("app.mode")` | Can return `["fast"]` | Can still return `["fast"]` |
| `CommandLineRunner.run(String... args)` | Receives raw arguments | Still receives raw arguments |
| Environment variable `APP_MODE=...` | Evaluated as OS environment | Still evaluated as OS environment |
| Java system property `-Dapp.mode=...` | Evaluated | Still evaluated |

Therefore, **do not claim the program will become completely blind to all command-line arguments**. If application code manually reads `args` and calls `System.setProperty(...)` or sets configuration in its own way, that custom behavior is not automatically blocked by this method.

## 5. Complete example: distinguishing `Environment` and `ApplicationArguments`

### 5.1. Configuration file

`src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: cli-property-demo

server:
  port: 8080

app:
  message: from-file
  mode: normal
~~~

### 5.2. Java code

~~~java
package com.example.demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(DemoApplication.class);
        app.setAddCommandLineProperties(false);
        app.run(args);
    }

    @Bean
    ApplicationRunner printConfiguration(Environment environment) {
        return (ApplicationArguments args) -> {
            System.out.println("server.port = "
                    + environment.getProperty("server.port"));
            System.out.println("app.message = "
                    + environment.getProperty("app.message"));
            System.out.println("app.mode = "
                    + environment.getProperty("app.mode"));

            System.out.println("Option app.message present = "
                    + args.containsOption("app.message"));
            System.out.println("Option app.message values = "
                    + args.getOptionValues("app.message"));
        };
    }
}
~~~

The example only prints non-sensitive settings. In real products, do not print passwords, tokens, API keys, or raw arguments if they could contain secret data.

### 5.3. Running with `--app.message`

~~~bash
java -jar demo.jar --server.port=9090 --app.message=from-cli
~~~

Provided no other configuration source overrides it, the output from the runner corresponds to:

~~~text
server.port = 8080
app.message = from-file
app.mode = normal
Option app.message present = true
Option app.message values = [from-cli]
~~~

This simultaneously demonstrates two facts:

1. `Environment` takes `server.port` and `app.message` from the configuration file, because the command-line property source is disabled.
2. `ApplicationArguments` still sees `--app.message=from-cli` and returns that option's value.

If you remove `app.setAddCommandLineProperties(false)` and run again under the same conditions, the effective configuration values can become `server.port=9090` and `app.message=from-cli` per default behavior.

## 6. Impact on operating system environment variables

This topic group is **Environment Variables**, so **OS environment variables** must be clearly separated from **command-line option arguments**. Both sources can appear in the same run, yet they are not the same mechanism.

Example file configuration:

~~~yaml
server:
  port: 8080
app:
  mode: normal
~~~

Keeping `setAddCommandLineProperties(false)` and running in a Unix shell:

~~~bash
SERVER_PORT=9191 APP_MODE=production \
  java -jar demo.jar --server.port=9292 --app.mode=from-cli
~~~

Assuming no source has higher priority than environment variables:

| Property | YAML file | OS environment | CLI | Effective value |
| --- | --- | --- | --- | --- |
| `server.port` | `8080` | `SERVER_PORT=9191` | `--server.port=9292` | `9191` |
| `app.mode` | `normal` | `APP_MODE=production` | `--app.mode=from-cli` | `production` |

Reason: Spring Boot **still reads environment variables** and applies relaxed binding. For example, `SERVER_PORT` maps to `server.port`; `APP_MODE` maps to `app.mode`. Only the CLI option properties source is excluded from `Environment`.

In PowerShell you can prepare the environment as follows:

~~~powershell
$env:SERVER_PORT = "9191"
$env:APP_MODE = "production"
java -jar demo.jar --server.port=9292 --app.mode=from-cli
~~~

The configuration outcome is similar, provided no other configuration source overrides it.

**Do not confuse `-D` with `--`:** `-Dserver.port=9191` is a **Java system property** passed to the JVM, whereas `--server.port=9292` is an **application argument** passed after the JAR name. `setAddCommandLineProperties(false)` handles the second source, not Java system properties.

## 7. Impact on Java system properties

Consider the command:

~~~bash
java -Dserver.port=9191 -jar demo.jar --server.port=9292
~~~

With `setAddCommandLineProperties(false)`, Spring Boot still receives `server.port=9191` from JVM system properties. The `--server.port=9292` part remains in raw args but is not added into `Environment` as command-line configuration.

Syntactic position difference:

~~~text
java -Dserver.port=9191 -jar demo.jar --server.port=9292
     └─ JVM property ──┘               └─ app option ──┘
~~~

Put `-D...` **before** `-jar` so the JVM treats it as a system property. Put `--...` after `demo.jar` so it is passed into the application's `main(String[] args)`.

A common question: what if all `--key=value` options are changed to `-Dkey=value`? Those values can still take effect through `systemProperties`, because this method **does not block the `-D` channel**. If deployment policy requires controlling system properties, environment variables, and file mounts alike, corresponding governance measures must be applied; a single method call does not govern all configuration channels.

## 8. Impact on `@Value` and `@ConfigurationProperties`

In an application, `Environment` is commonly consumed by:

- Spring Boot auto-configuration, such as `server.port`.
- `@Value`, when injecting an individual property.
- `@ConfigurationProperties`, when binding multiple properties under a prefix into a Java structure.
- Code calling `Environment.getProperty(...)` directly.

Example configuration:

~~~yaml
app:
  client:
    base-url: https://sandbox.example.test
    timeout: 5s
~~~

Record using `@ConfigurationProperties`:

~~~java
package com.example.demo;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(String baseUrl, Duration timeout) {
}
~~~

Register configuration scanning via `@ConfigurationPropertiesScan` on the `@SpringBootApplication` class or register properly using `@EnableConfigurationProperties`.

If you run:

~~~bash
java -jar demo.jar --app.client.timeout=20s
~~~

with the command-line property source disabled, `ClientProperties.timeout()` will **not** receive `20s` from that argument alone. If the file declares `5s` and no other source overrides it, the bean receives a `Duration` corresponding to `5s`.

If using an environment variable:

~~~bash
APP_CLIENT_TIMEOUT=12s java -jar demo.jar --app.client.timeout=20s
~~~

then the bean can receive `12s` from the environment variable. This is a direct application of **distinguishing which configuration sources are enabled**.

Remember not to bind critical configuration silently. When URLs, timeouts, credentials, or threshold values are mandatory, add validation and clear startup errors so misconfigured deployments are caught early.

## 9. Impact on profiles at startup

One major effect is **activating Spring profiles via CLI arguments**.

Under default behavior, the command:

~~~bash
java -jar demo.jar --spring.profiles.active=prod
~~~

places `spring.profiles.active=prod` into `Environment` and can activate the `prod` profile, thereby loading files like `application-prod.yml`.

After calling `setAddCommandLineProperties(false)`, **the value from `--spring.profiles.active=prod` is not added into `Environment` via the CLI source**. Thus, unless another source activates `prod`, do not expect that command to activate the profile.

Instead, you can set an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar demo.jar
~~~

Or use a JVM system property:

~~~bash
java -Dspring.profiles.active=prod -jar demo.jar
~~~

Both forms remain valid configuration sources processed by Spring Boot when the command-line property source is disabled.

If you want the `prod` profile fixed from code or another environment configuration, corresponding mechanisms exist too; the important part is identifying **which source actually sets the profile**, especially since profiles determine which configuration files and beans get activated.

Example:

~~~text
application.yml       → app.timeout=3s
application-prod.yml  → app.timeout=15s

setAddCommandLineProperties(false)
java -jar demo.jar --spring.profiles.active=prod
~~~

If no other source enables `prod`, `app.timeout` does not become `15s` from that argument alone. However, if run with `SPRING_PROFILES_ACTIVE=prod`, `application-prod.yml` can participate and supply `15s`.

## 10. Impact on Config Data loading options

Beyond profiles, certain properties must be recognized **very early** for Spring Boot to decide where to look for and load configuration:

- `spring.config.name`
- `spring.config.location`
- `spring.config.additional-location`

In default mode, you can pass:

~~~bash
java -jar demo.jar \
  --spring.config.additional-location=file:/etc/my-service/
~~~

However, once the command-line property source is disabled, do not rely on `--spring.config.additional-location=...` to add locations. That argument remains an option argument in `ApplicationArguments`, yet it is not added into `Environment`'s configuration sources via the default mechanism.

Use another source recognized early, for example:

~~~bash
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/my-service/ \
  java -jar demo.jar
~~~

Or:

~~~bash
java -Dspring.config.additional-location=file:/etc/my-service/ -jar demo.jar
~~~

The same applies to `spring.config.location` and `spring.config.name`. When switching to external files outside the JAR, verify that paths, read permissions, environment variables, and profile files exist at startup time.

For automated run modes, if the system previously specified profiles or file locations via `--...`, a single line adding `setAddCommandLineProperties(false)` can cause the application to start with a **different default configuration set**. Therefore, audit deployment launch contracts before enabling it in production.

## 11. Impact on logging and server configuration

Besides `server.port`, logging properties are also commonly passed via CLI:

~~~bash
java -jar demo.jar --logging.level.root=DEBUG
~~~

When the command-line property source is disabled, `--logging.level.root=DEBUG` does not supply configuration values to Spring Boot logging through that CLI channel. Effective values may come from files, environment variables, or Java system properties.

To supply from an environment variable:

~~~bash
LOGGING_LEVEL_ROOT=DEBUG java -jar demo.jar
~~~

Or from a file:

~~~yaml
logging:
  level:
    root: DEBUG
~~~

Similarly for server and datasource properties:

~~~bash
java -jar demo.jar \
  --server.port=9090 \
  --spring.datasource.url=jdbc:postgresql://localhost:5432/demo
~~~

These options will not automatically override `server.port` and `spring.datasource.url` in `Environment` when the command-line property source has been disabled. If the deployment still needs per-environment values, supply them via an allowed source such as `SERVER_PORT` and `SPRING_DATASOURCE_URL`.

**Do not put credentials into sample commands.** Passwords, API keys, and tokens must be managed via an appropriate secret mechanism, with restricted access and logging. Disabling the command-line property source does not remove raw arguments from the operating system or prevent application code from inspecting them.

## 12. Why would a project want to disable the command-line configuration source?

This method is useful when operational design is deliberate and wants to reduce unwanted configuration overrides from `--key=value`.

### 12.1. Standardizing configuration channels in deployment environments

A team may decide runtime configuration must go through:

- `application.yml`/`application.properties` inside the artifact for defaults.
- External mounted files or config data imports for environment differences.
- Environment variables provided by pipelines, Docker Compose, Kubernetes, or a secret manager.

Then, if an entrypoint accidentally appends `--server.port=...`, it will not alter the port through Spring Environment. Application arguments can still be used for other functionality.

### 12.2. Avoiding overrides originating from launch scripts

Scenario:

~~~text
Deployment file specifies:
  SERVER_PORT=9191

Script copied from an older environment:
  java -jar app.jar --server.port=8080
~~~

If the command-line property source is allowed, `--server.port=8080` can override the environment variable. If disabled, `SERVER_PORT=9191` can take effect as intended.

This only resolves conflicts **between two configuration sources**. You still need to manage scripts, understand port binding, and control deployment data.

### 12.3. Separating task parameters from system configuration

A CLI tool written with Spring Boot might receive:

~~~bash
java -jar batch-tool.jar --job=import --file=/data/orders.csv
~~~

The application wants to process `job` and `file` inside an `ApplicationRunner`, without accidentally turning them into global properties in `Environment`. In that case, you can disable the command-line property source and read args in the task-handling layer.

Even so, if some `--...` options **must control Spring Boot auto-configuration**, this method may be unsuitable: it disables the CLI configuration source globally rather than selectively ignoring specific options.

## 13. When should you NOT use it?

Do not arbitrarily disable the CLI source when the system relies on `--...` arguments to control Spring Boot.

Cases to consider carefully:

- A JAR launched by an operations platform with `--spring.profiles.active=...`.
- A runtime platform that injects `--server.port=...`.
- A pipeline using `--spring.config.location=...` to point to a configuration file.
- Local scripts using `--logging.level...` to enable diagnostic logging.
- Jobs or tests using `--app.*` as an intentional way to supply parameters binding into `@ConfigurationProperties`.

In such contexts, disabling the command-line property source can make expected configuration values **stop taking effect**. Alternatives include standardizing and controlling arguments at the launch layer, or moving required properties to OS environment/system properties/config data. If you only want to forbid **a few** specific options, this method is fairly broad because it applies to the **entire command-line property source**.

This is a startup-design decision and must be documented in deployment guides so operators know which sources the program actually honors.

## 14. Comparing three ways to pass values when command-line properties are disabled

Suppose:

~~~yaml
# application.yml
app:
  mode: from-file
~~~

And in `main`:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Execute independent runs:

| Run command | Value source | `Environment.getProperty("app.mode")` |
| --- | --- | --- |
| `java -jar demo.jar` | YAML file | `from-file` |
| `java -jar demo.jar --app.mode=from-cli` | CLI disabled in Environment | `from-file` |
| `APP_MODE=from-env java -jar demo.jar --app.mode=from-cli` | OS environment | `from-env` |
| `java -Dapp.mode=from-jvm -jar demo.jar --app.mode=from-cli` | Java system property | `from-jvm` |

The table assumes no other overriding source and that each run starts a fresh process with a clean environment. The `APP_MODE=... java ...` syntax is for Unix shells; in PowerShell, declare environment variables using PowerShell syntax.

## 15. Distinguishing from other ways of working with command-line arguments

### 15.1. `SpringApplication.setDefaultProperties(...)`

`setDefaultProperties(...)` supplies low-priority fallback values. It **does not** disable the command-line property source.

Example:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setDefaultProperties(java.util.Map.of("app.mode", "fallback"));
app.run(args);
~~~

With Spring Boot defaults, `--app.mode=from-cli` can still override the fallback value. If you want to disable the command-line source, you must explicitly call `setAddCommandLineProperties(false)`.

### 15.2. `ApplicationArguments`

`ApplicationArguments` provides an interface to **access parsed arguments**:

~~~java
@Bean
ApplicationRunner runner() {
    return args -> {
        if (args.containsOption("job")) {
            var values = args.getOptionValues("job");
            // Validate the value and then perform the appropriate task.
        }
    };
}
~~~

It can read `--job=import` even when the command-line property source is disabled. If you need to parse various argument types, this is the proper place to implement custom logic.

### 15.3. `CommandLineRunner`

`CommandLineRunner` receives the raw string array of arguments:

~~~java
@Bean
CommandLineRunner printArgCount() {
    return args -> System.out.println("arg count = " + args.length);
}
~~~

The count of raw args does not become 0 after `setAddCommandLineProperties(false)`. They are still passed by Spring Boot to the runner.

### 15.4. Manually manipulating `Environment` or `PropertySource`

Spring Framework provides APIs to read and organize property sources. However, if the goal is solely disabling addition of command-line option properties, Spring Boot already exposes a **direct flag** on `SpringApplication`. There is no need to access `MutablePropertySources` manually to find and remove the property source after context startup; by then it may already be too late for configuration used during startup.

## 16. Verifying behavior on a sample application

Run the same application with the following configuration:

~~~yaml
server:
  port: 8080
app:
  message: file-value
~~~

Use an observer component:

~~~java
@Bean
ApplicationRunner verify(Environment environment) {
    return args -> {
        System.out.println("Effective server.port: "
                + environment.getProperty("server.port"));
        System.out.println("Effective app.message: "
                + environment.getProperty("app.message"));
        System.out.println("CLI app.message supplied: "
                + args.containsOption("app.message"));
    };
}
~~~

### Case A — Command-line properties enabled

In `main`, do not call `setAddCommandLineProperties(false)` or set `true`:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=cli-value
~~~

With normal sources, the effective configuration is port `9090` and message `cli-value`.

### Case B — Command-line properties disabled

In `main`, set `setAddCommandLineProperties(false)` and run the same command:

~~~bash
java -jar demo.jar --server.port=9090 --app.message=cli-value
~~~

Under the same assumptions, port is `8080` and message is `file-value`; `args.containsOption("app.message")` remains `true`.

### Case C — Command-line properties disabled while supplying environment variables

~~~bash
SERVER_PORT=9191 APP_MESSAGE=env-value \
  java -jar demo.jar --server.port=9090 --app.message=cli-value
~~~

Port is `9191` and message is `env-value`, while the CLI option remains visible via `ApplicationArguments`.

These verification steps show that the method alters **data sources for Environment**, while preserving the path for raw arguments.

## 17. Common errors and misconceptions

| Symptom or assumption | Explanation and resolution |
| --- | --- |
| "I disabled CLI, yet `ApplicationRunner` still sees `--app.mode`." | Expected by design: runners receive `ApplicationArguments` independently of the CLI configuration source. |
| "`--server.port=9090` stopped working." | Check `setAddCommandLineProperties(false)`; if enabled, use OS env, JVM property, or a file to supply the port. |
| "`--spring.profiles.active=prod` does not activate the profile." | When the CLI property source is disabled, supply `spring.profiles.active` from another source such as `SPRING_PROFILES_ACTIVE` or `-Dspring.profiles.active`. |
| "`--spring.config.additional-location` does not search the extra directory." | File-location settings must come from an early-active source; use a system property or OS env. |
| "`-Dserver.port=9090` still works—why didn't the method block it?" | `-D` is a JVM system property, not an app command-line property `--key=value`. |
| "Environment variable `SERVER_PORT` was also disabled." | No. OS environment is a different `PropertySource`. |
| "Calling the method after `run` will change configuration." | It must be set before Spring Boot creates and uses `Environment` for that launch. |
| "Disabling the CLI source secures all secrets passed via argv." | False. Raw args and process arguments can still be logged or read by the application. |
| "I only want to block `--server.port` while keeping `--app.mode`." | This method disables the entire command-line property source; design a different selection mechanism if you need per-option filtering. |
| "Using `@Value` still reads disabled arguments automatically." | `@Value` resolves values through the property system; it does not turn raw args into properties. |
| "Without `--key=value`, the app cannot be externally configured." | Application files, environment variables, JVM properties, and other built-in sources remain available. |

## 18. Reasoning exercise

Suppose an application calls:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

Packaged configuration:

~~~yaml
server:
  port: 8080
app:
  region: vn
  timeout: 3s
~~~

Launched with:

~~~bash
APP_REGION=apac java -Dapp.timeout=7s -jar demo.jar \
  --server.port=9090 \
  --app.region=from-cli \
  --app.timeout=20s \
  --job=sync
~~~

**Question 1:** what are the values in `Environment`?

- `server.port=8080`, because `--server.port=9090` does not become a property.
- `app.region=apac`, because environment variable `APP_REGION` remains in effect.
- `app.timeout=7s`, because JVM system property `-Dapp.timeout=7s` remains in effect.

**Question 2:** does an `ApplicationRunner` see the `job` option?

Yes. `ApplicationArguments.containsOption("job")` can still return `true`; `getOptionValues("job")` can still return `["sync"]`. Disabling the command-line property source does not remove this argument from `args`.

**Question 3:** what changes if `setAddCommandLineProperties(false)` is removed?

With default behavior and no source having higher priority than CLI in the example, the values can become `server.port=9090`, `app.region=from-cli`, and `app.timeout=20s`. Meanwhile, `ApplicationArguments` still receives `--job=sync` in both modes.

## 19. Key takeaways

`setAddCommandLineProperties(false)` configures `SpringApplication` **not to add `--key=value` option arguments into `Spring Environment`**. It must be called on the launching instance **before `run(args)`**.

Clearly distinguish three things:

1. **CLI configuration source:** disabled when calling the method with `false`; `--...` values no longer override properties automatically.
2. **Other configuration sources:** environment variables, Java system properties, application files, and config data continue operating by their own rules.
3. **Application arguments:** still reach `main`, `ApplicationArguments`, `ApplicationRunner`, and `CommandLineRunner`; application code can still explicitly process them.

Before using this in a real system, review how deployments pass `spring.profiles.active`, `spring.config.*`, `server.port`, `logging.level.*`, and business properties. If they are currently supplied via `--...`, move them to an appropriate configuration source or accept that they no longer affect Spring Boot Environment automatically.

### References

- Spring Boot Reference — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Application Arguments: https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-arguments
- Spring Boot Javadoc — SpringApplication: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/SpringApplication.html

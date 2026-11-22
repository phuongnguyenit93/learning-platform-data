# Logback Configuration Profiles in Java: dev, test, staging, and production

## 1. What is a Configuration Profile?

A **logging configuration profile** is a way to select logging settings suited to an application's environment or running mode. The same Java program may need:

- **Development (`dev`):** detailed, easy-to-read console output for troubleshooting.
- **Test (`test`):** consistent output, reduced noise, and avoiding unnecessary file writes.
- **Staging:** close to production for testing the pipeline, while optionally enabling some controlled diagnostics.
- **Production (`prod`):** appropriate log levels, a stable format for collectors to parse, controlled sensitive data, and proper storage/rotation.

For example, in `dev` we might see the event `DEBUG com.example.orders.OrderService - cache miss`, whereas in `prod` only `INFO/WARN/ERROR` is needed depending on policy. The goal is to **change how logs are processed without changing business logic on every deployment**.

Two concepts must be distinguished right away:

1. **Plain Logback** is a logging backend. It has configuration files, property substitution, appenders, loggers, levels, filters, and configuration selection mechanisms. It **does not have a built-in Spring profile concept within Logback itself**.
2. **Spring Boot + Logback** has dedicated integration for the Spring Environment, specifically the `<springProfile>` and `<springProperty>` tags in `logback-spring.xml`. Those tags **are not standard XML for standalone Logback**.

Therefore, "profile-based configuration" can mean **selecting configuration values via environment/system properties** in a plain Java application, or **selecting configuration branches by Spring profile** when using Spring Boot. This article covers both and points out the boundary between them.

## 2. Which Logging Components Do Profiles Affect?

Logback typically operates along this flow:

```text
Application → SLF4J Logger → Logback event → Appender → Encoder/Layout → Console/File/Collector
                    |               |             |
                  Level        Filter/route     Pattern/JSON
```

This diagram is conceptual; the appender coordinates the encoder/layout, and filtering conditions can exist at multiple layers.

A profile can control:

| Component | Dev/test | Production |
|---|---|---|
| **Root level** | `DEBUG` or `INFO` as needed | `INFO` or `WARN` depending on system specifics |
| **Package-level logging** | Enable `DEBUG` specifically for `com.example.orders` | Enable only during investigations, in a controlled manner |
| **Appender** | Console for observation | Console for collectors; optionally add file/remote appenders if needed |
| **Encoder/layout** | Human-readable text pattern | Stable pattern or structured JSON via an appropriate encoder |
| **Context data** | Request ID, trace ID for debugging | Still needs correlation ID, but sensitive data is restricted |
| **Rotation/retention** | Usually simple | Needs preservation policies, limits, access permissions, and retention |
| **Async/buffering** | Only when useful | Evaluated by throughput and requirements to avoid log loss |

A profile **does not automatically generate** `requestId`, `traceId`, MDC, JSON fields, or business data. The application and backend must provide them; the profile only decides whether and how they are emitted and processed.

## 3. Selecting Configuration with Plain Logback (Without Spring)

### 3.1. Environment Variables and System Properties

With standalone Logback, the simplest approach is to maintain **one configuration** and use property substitution:

```xml
<configuration>
    <property name="SERVICE_NAME" value="orders-api"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} app=${SERVICE_NAME} env=${APP_ENV:-local} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="${ROOT_LOG_LEVEL:-INFO}">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This is a `logback.xml` file for Logback, not a Spring Boot extension file. The variables:

- `SERVICE_NAME` is declared directly in the file for reuse in the pattern.
- `APP_ENV` can come from an environment variable or a system property; `local` is the fallback value in Logback syntax.
- `ROOT_LOG_LEVEL` selects the root level. If not provided, the fallback is `INFO`.
- `%logger{0}` in the pattern shortens the logger name to display only the last segment, without changing the logger identifier in the event.
- `%msg%n` outputs the message and a line break.
- `target=System.out` routes this appender to stdout. This is a **Logback** setting, unlike `java.util.logging.ConsoleHandler`, which typically writes to stderr.

When running with `ROOT_LOG_LEVEL=DEBUG`, `DEBUG` calls will be accepted if no other filter discards them. When `ROOT_LOG_LEVEL=INFO`, `DEBUG` is filtered out. The effective level is also affected by child loggers with their own levels, filters, and additivity.

**Do not put secrets into patterns** or declare sensitive variables just to print them in logs. Property substitution selects configuration; it is not a data-masking mechanism.

### 3.2. Selecting Different Configuration Files per Environment

If environments genuinely require different appender topologies, you can use separate files such as `logback-dev.xml` and `logback-prod.xml`. With a **plain Logback application**, you can specify the file using a JVM system property at startup:

```bash
java -Dlogback.configurationFile=/opt/app/config/logback-prod.xml -cp "app.jar:lib/*" com.example.Main
```

This command is an **illustrative form** for a Unix-like environment: the corresponding JARs, main class, and paths must exist; on Windows, the classpath separator and path format will differ. The property must be set early enough, before Logback initializes.

Pros: each configuration can have independent appenders and policies. Cons: files easily suffer from **configuration drift**, where you forget to update patterns, logger names, security policies, and output standards in sync. Therefore, only split files when the benefits outweigh the maintenance cost; shared parts can be reused via Logback's include mechanism if appropriate.

In Spring Boot, `logging.config` is another option to specify the configuration location; do not mix Spring Boot's config loading with Logback's self-initialization without checking the startup order.

### 3.3. Configuration File Precedence

When using Logback's standard auto-configuration mechanism, `logback-test.xml` usually takes precedence over `logback.xml` if both are present on the classpath. This allows tests to have their own configuration without writing production files or producing overly noisy output.

Programmatic configuration, system properties, SPI, framework initializers, or different Logback versions can alter the configuration loading path. Therefore, if logs appear to use "the wrong profile," verify **which file is actually being loaded** before changing levels across the board.

## 4. Runnable Java 17 Example with Plain Logback and Maven

This small example demonstrates that **a single `logback.xml` file can change log levels and environment labels without modifying Java code**. The code uses the SLF4J API with the Logback backend. **It cannot be run with just `javac ProfileLoggingDemo.java`**, because Maven dependencies are required; the Maven command below compiles and runs the program.

### 4.1. Project Structure

```text
logback-profile-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/logging/ProfileLoggingDemo.java
        └── resources/
            └── logback.xml
```

### 4.2. The `pom.xml` File

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>logback-profile-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>com.example.logging.ProfileLoggingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` brings the Logback backend onto the runtime classpath and pulls in the SLF4J API via a matching dependency. The version in `pom.xml` is a **pinned illustrative version for this lesson**, not a claim that it is the latest release. For real systems, check JDK requirements, CVEs, dependency management, and compatible versions managed by your team.

### 4.3. The `src/main/resources/logback.xml` File

```xml
<configuration>
    <property name="SERVICE_NAME" value="orders-api"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger{0} app=${SERVICE_NAME} env=${APP_ENV:-local} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="${ROOT_LOG_LEVEL:-INFO}">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This file is identical to the example in section 3 and resides on the classpath under `src/main/resources`. No profile needs to be defined in Java code.

### 4.4. The `src/main/java/com/example/logging/ProfileLoggingDemo.java` File

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class ProfileLoggingDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(ProfileLoggingDemo.class);

    public static void main(String[] args) {
        LOG.info("event=app_started");
        LOG.debug("event=cache_probe");
    }
}
```

`LoggerFactory.getLogger(ProfileLoggingDemo.class)` creates a logger with the class's fully qualified name. `root` in the configuration sets the default effective level if child loggers do not specify their own level. The code emits both INFO and DEBUG, but **the backend only outputs events permitted by the level/filter**.

### 4.5. Running with the Default Profile

From the `logback-profile-demo` directory, requiring JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Assuming neither `APP_ENV` nor `ROOT_LOG_LEVEL` is set in the OS/JVM and no higher-priority configuration file is present, **the stdout produced by the program** will consist of this exact line:

```text
INFO ProfileLoggingDemo app=orders-api env=local - event=app_started
```

The DEBUG line is not printed because root defaults to INFO. Logback in this configuration writes to stdout. Maven may produce its own messages on stderr or stdout under different build/environment configurations; the snippet above describes **the logger output in the example**, not a guarantee that Maven's entire output will only be a single line.

### 4.6. Running with the dev Profile

On Linux/macOS (POSIX-compatible shell):

```bash
APP_ENV=dev ROOT_LOG_LEVEL=DEBUG mvn -q compile exec:java
```

On Windows PowerShell:

```powershell
$env:APP_ENV = "dev"
$env:ROOT_LOG_LEVEL = "DEBUG"
mvn -q compile exec:java
Remove-Item Env:APP_ENV
Remove-Item Env:ROOT_LOG_LEVEL
```

When run with these two environment variables, the logger output is:

```text
INFO ProfileLoggingDemo app=orders-api env=dev - event=app_started
DEBUG ProfileLoggingDemo app=orders-api env=dev - event=cache_probe
```

Here, `APP_ENV=dev` is only displayed in the pattern; **enabling DEBUG is due to `ROOT_LOG_LEVEL=DEBUG`**, not because Logback inherently understands the word `dev`. If you only set `APP_ENV=dev` without setting `ROOT_LOG_LEVEL`, the logger remains at INFO. That is a crucial distinction between an **environment label** and **conditional configuration rules**.

If you want a profile to control multiple appenders, JSON encoders, or different routing, you must add conditional configuration or a file selection mechanism rather than just changing the `env` label.

## 5. Spring Boot: `logback-spring.xml` and `springProfile`

For **Spring Boot applications using Logback** as the backend, Spring Boot provides extension tags to apply configuration based on the Spring Environment. Two prominent elements are:

- `<springProfile name="dev"> ... </springProfile>`: activates the inner configuration only when the profile expression matches.
- `<springProperty .../>`: exposes a property from the Spring Environment into Logback's configuration context for use in patterns, appenders, or other settings.

These tags must be processed by Spring Boot; **plain Logback does not understand them**. Typically, the file is placed at `src/main/resources/logback-spring.xml` instead of `logback.xml` so Spring Boot orchestrates it at startup.

### 5.1. Example `logback-spring.xml`

```xml
<configuration>
    <springProperty scope="context"
                    name="serviceName"
                    source="spring.application.name"
                    defaultValue="orders-api"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level [${serviceName}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Default: INFO for loggers without an override. -->
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>

    <!-- Only this namespace is more verbose in dev. -->
    <springProfile name="dev">
        <logger name="com.example" level="DEBUG"/>
    </springProfile>

    <!-- This namespace is less noisy in production. -->
    <springProfile name="prod">
        <logger name="com.example" level="WARN"/>
    </springProfile>
</configuration>
```

**Configuration outcome:**

- When the `dev` profile is active, loggers under `com.example` have an effective level of DEBUG; their DEBUG events can flow to the CONSOLE appender inherited from root.
- When only `prod` is active, `com.example` has level WARN; INFO/DEBUG events in that namespace are not emitted.
- If neither `dev` nor `prod` matches, the namespace is not overridden and inherits INFO from root.
- Loggers outside `com.example` still follow root INFO unless another rule applies.

This example has **one root and one console appender**. Profiles only change the level of a single namespace, keeping the focus on verifiable behavior. If you want to configure different appenders per profile, you can place appender definitions, root/logger elements, or appender references inside `<springProfile>` branches, but you must avoid duplicate names or multiple competing root elements when multiple profiles are active simultaneously.

**Environment note:** `dev` and `prod` should not be activated at the same time if both branches define a level for `com.example`. When multiple profiles match, the final outcome may depend on configuration processing order; design mutually exclusive profile groups and verify effective levels.

### 5.2. Activating a Spring Profile

You can set the application name in `application.yml`:

```yaml
spring:
  application:
    name: orders-api
```

Then activate a profile at runtime using Spring Boot's mechanisms, for example:

```bash
java -jar orders-api.jar --spring.profiles.active=dev
java -jar orders-api.jar --spring.profiles.active=prod
```

These two commands are **illustrative** and require a Spring Boot application packaged as `orders-api.jar`; they cannot be run from the plain Logback Maven project in section 4.

Alternatively, set an environment variable:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar orders-api.jar
```

Settings in `application.properties`/`application.yml`, environment variables, command-line arguments, and deployment environments follow Spring Boot's precedence rules. When multiple sources exist, verify the **actual active profiles** and final properties provided by the Spring Environment. Avoid hardcoding `spring.profiles.active=dev` into artifacts deployed to production; select the profile from the deployment environment.

### 5.3. Distinguishing Spring Profiles from Logback Properties

In the plain Maven example, `APP_ENV=dev` and `ROOT_LOG_LEVEL=DEBUG` are **two independent variables**. In Spring Boot, `SPRING_PROFILES_ACTIVE=dev` controls the `<springProfile name="dev">` expression. Writing only:

```properties
APP_ENV=dev
```

does not automatically activate the `dev` profile in Spring Boot. Conversely, activating the `dev` profile alone does not guarantee that every logger enables DEBUG: there must be a matching rule in `logback-spring.xml` or a corresponding level configuration.

Spring Boot also supports configuring log levels via `logging.level.root` or `logging.level.com.example` in the Spring Environment. When mixing `logging.level.*` with level definitions in `logback-spring.xml`, you must test **the actual effective level after application startup**, rather than inferring it from a single file. Configuration loading order and how Spring Boot manages logging can produce unexpected results.

### 5.4. Why Is `logback.xml` Different from `logback-spring.xml`?

- `logback.xml` is the standard name for Logback auto-loading; Logback may process this file **before** the Spring Boot Environment is ready for Spring extensions.
- `logback-spring.xml` is the name actively processed by Spring Boot, suitable when using `springProfile` and `springProperty`.
- Do not copy `springProfile` tags into a plain Java/Maven application expecting Logback to understand them; it may report "no applicable action" or a similar configuration error.
- With Spring's Logback extensions, **do not arbitrarily enable Logback's `scan="true"` mechanism**: Logback's scanner reconfiguration is incompatible with how Spring processes these extensions. Use reload/management methods supported by Spring Boot or your application architecture.
- If the application uses `logging.config` or other Logback customizations, verify the exact file path being loaded rather than assuming `logback-spring.xml` is always picked up.

**The `logback-spring.xml` example above is not a standalone program.** It must reside in a Spring Boot application with a Logback backend; do not use the `javac`/`java` commands from the plain Logback example to launch it.

## 6. Separating Shared Configuration from Profile-Specific Parts

For large projects with multiple environments, keep as many **shared** rules consistent as possible, such as:

- Timestamp format and timezone; JSON/text structure decisions.
- Logger names derived from package/class and event names.
- Correlation ID, trace ID, error code, and required business fields.
- Policies against logging secrets, data masking, and log volume limits.
- Exception/cause conventions and how collectors aggregate multiline stack traces.

Only separate what genuinely needs to differ: levels, output destinations, verbosity, sampling, file policies, and specific filters.

There are two main approaches:

**Approach A — One configuration, properties for small variations.**

```xml
<root level="${ROOT_LOG_LEVEL:-INFO}">
    <appender-ref ref="CONSOLE"/>
</root>
```

Easy to manage when each environment only changes a few values. Property fallbacks must be sensible; production systems should monitor the loaded values.

**Approach B — Selecting branches or separate files.**

Example in Spring Boot:

```xml
<springProfile name="dev">
    <logger name="com.example.orders" level="DEBUG"/>
</springProfile>

<springProfile name="prod">
    <logger name="com.example.orders" level="INFO"/>
</springProfile>
```

Use this when profile-based changes are needed and Spring Boot extensions are available. With plain Logback, you can select a configuration file at startup or organize shared/included files; do not use `<springProfile>` without Spring Boot.

**Avoid repeating the entire root/appender/filter setup in every profile if only a level differs**, as it makes it easy for one profile to forget an encoder, masking rule, or exception format, or accidentally write to two different output destinations.

## 7. Package-Level Logging: Avoiding System-Wide DEBUG

For multi-module services, it is generally best to choose a safe root level and enable verbose logging only where an issue is being investigated.

```xml
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>

<logger name="com.example.orders" level="DEBUG"/>
```

This is a **Logback fragment**, assuming the `CONSOLE` appender is already declared in the full configuration. Loggers under `com.example.orders` get DEBUG enabled, while other parts continue using INFO. Logger names must follow packages/classes consistently; a logger with an arbitrary name outside the namespace will not receive the rule as expected.

### A Common Misconception: Does Root INFO Block DEBUG from a Child Logger?

In Logback, when a child logger has an effective level of DEBUG, its DEBUG events are created and passed to appenders following hierarchy/additivity. **Root's INFO level does not re-filter events already accepted by a child logger** simply because the appender is attached to root. However, an appender with its own filter can still block them.

If a record is emitted twice, check whether the appender is attached to both the child logger and root, along with the `additivity` value. Do not fix it by blindly disabling propagation: you could lose the only log collection path.

## 8. Profiles and the Test Environment

Tests usually need minimal logging so test results are not obscured. With plain Logback, you can create `src/test/resources/logback-test.xml`, for example:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{0} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="WARN">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

When this file is on the **test classpath** under standard Logback behavior, it can be picked up instead of `logback.xml` during test runs. Do not accidentally include test-only configuration in production artifacts.

With Spring Boot, the `test` profile can be paired with `application-test.yml` and a `<springProfile name="test">` branch. However, note the distinction:

- **Spring test profile** is a Spring Environment state.
- **`logback-test.xml`** is a Logback/classpath file selection mechanism.
- The two mechanisms are conceptually independent; sharing the name "test" **does not automatically make them a single system**.

When tests inspect log contents, you can use a test appender to capture events and assert on level, logger name, and message/arguments instead of relying solely on console text. Avoid snapshot testing with dynamic timestamps unless time data is controlled.

## 9. Structured Logging, JSON, and MDC by Profile

In development, a human-readable text pattern is usually sufficient:

```text
INFO  [http-17] OrderService - event=order_accepted orderId=ORD-7
```

In production, collection systems may prefer JSON:

```json
{"timestamp":"2026-11-09T08:15:03.125Z","level":"INFO","logger":"com.example.orders.OrderService","traceId":"trace-42","event":"order_accepted","orderId":"ORD-7"}
```

These two lines are **illustrative format samples**, not output from the Maven demo in section 4. Logback does not automatically turn `%msg` into JSON with an `orderId` field; producing structured fields requires an appropriate API/context/encoder, which may require additional dependencies.

**MDC** (Mapped Diagnostic Context) lets you attach `requestId` and `traceId` to events if the application sets and propagates context properly. In Logback, the `%X{traceId}` pattern reads a value from MDC; it does not generate trace IDs on its own. With thread pools or async execution, context must be propagated and cleared properly to prevent leaking data from other requests.

Do not let a dev profile log sensitive payloads and accidentally deploy the same configuration to production. Even though profiles can change verbosity, **data protection rules must be enforced consistently** in every environment handling real data.

## 10. Safety Rules When Designing Logging Profiles

### 10.1. Log Level Is Not a Security Mechanism

Merely lowering the level from DEBUG to INFO does not guarantee sensitive information disappears: secrets can appear in INFO messages, exceptions, MDC, or structured fields. Never log passwords, access tokens, API keys, session cookies, card data, or unnecessary personal information; consider masking at the source and verifying the encoder.

### 10.2. Watch Out for stdout, stderr, and Collection Targets

In the demo, `ConsoleAppender` targets `System.out`; some environments route stderr separately. In containerized deployments, decide whether the collector reads stdout, stderr, or both. Adding both a file appender and a console appender simultaneously can increase storage usage or duplicate data if collectors ingest both.

### 10.3. Rotation and Retention Are Not Guaranteed by a Spring Profile

A profile can select a `RollingFileAppender`, but the name `prod` itself does not create file size limits, compression/retention/deletion policies, or data-loss guarantees. Verify rolling policies against your running Logback version, file write permissions, log volume, disk quota, and collection pipeline.

### 10.4. Async Does Not Mean Zero Log Loss

If prod uses `AsyncAppender`, define queue policies, drop behavior, blocking, flush/shutdown behavior, and error handling when downstream fails. Each environment may choose different performance trade-offs, but you must test realistically rather than assuming async is always better.

### 10.5. Avoid Overlapping Profile-Dependent Configurations

If both `dev` and `prod` are active, rules for the same logger can conflict. Placing different root/appender definitions in both branches makes issues even harder to diagnose. Prefer profiles with clear, non-overlapping roles or mutually exclusive condition groups.

### 10.6. Observe the Effective Configuration

After startup, verify at least: active profiles, the loaded config path, root level, package overrides, target appenders, output format, and the context actually logged. Never log a message containing a secret just to prove an environment variable was read successfully.

## 11. Common Issues and How to Troubleshoot Them

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `<springProfile>` is not recognized | File loaded by plain Logback or `logback.xml` instead of Spring Boot extension | Use `logback-spring.xml` with Spring Boot; check loading path |
| `SPRING_PROFILES_ACTIVE=dev` is set but no DEBUG logs appear | Missing dev rule, logger name in a different namespace, or a filter | Check active profiles, effective level, and filters |
| `APP_ENV=dev` appears in logs but level is still INFO | It is only a display variable; `ROOT_LOG_LEVEL` or a rule was not set | Check level variable; do not confuse with environment label |
| Tests log too much despite `logback-test.xml` | File is not on test classpath or framework uses a different config | Check classpath and which file is actually loaded |
| Production profile does not seem applied | Different active profile, or `prod`/`production` name mismatch | Confirm exact profile name at runtime |
| Logs are duplicated twice | Appender attached to both child logger and root, or additivity | Check `appender-ref`, `additivity`, and external collection |
| JSON fails to parse | Text pattern faking JSON or improper string escaping | Use a structured encoder/serializer |
| Missing `traceId` | MDC not populated or not propagated across async boundaries | Check context initialization and cleanup |
| Production suddenly logs too much DEBUG | Root/package level overridden by wrong variable/profile | Verify actual config; add log volume alerts |
| Changing `logging.level.*` does not behave as expected | Spring Boot rules, Logback file, and initialization order interact | Check effective level after startup |
| Logback scanner reports errors with `springProfile` | Using scan/reload incompatible with Spring extensions | Remove Logback auto-scan; use an appropriate mechanism |
| Console and file both writing increases log count | Both destinations are ingested by collectors | Clarify pipeline and deduplicate at collector |

## 12. Per-Environment Deployment Checklist

Before releasing a new Logback configuration, verify:

1. **Where is the environment determined?** Environment variable, JVM system property, config file, Spring profile, or deployment manifest?
2. **What changes?** Level, appender, pattern/JSON encoder, rolling, async, or package-specific loggers?
3. **Is there a safe fallback configuration?** If no profile is selected, what level and destination will the system use?
4. **Is there any formatting error?** Test text/JSON, timestamps, timezones, newlines, Unicode, and exception stack traces.
5. **Are logs duplicated or missing?** Check additivity, root, `appender-ref`, filters, and collectors.
6. **Is correlation context present?** Request ID/trace ID must be supplied by the application; they do not appear automatically from a profile.
7. **Is there any sensitive data?** Check messages, parameters, MDC, `Throwable`, and retention.
8. **Are cost limits in place?** Log volume, CPU/IO, async queues, rotation, and storage/quotas.
9. **Does it match the right runtime?** `logback.xml` for plain Logback, `logback-spring.xml` for Spring Boot extensions.
10. **Was it tested after packaging?** Check classpath files, active profiles, effective configuration, and actual output.
11. **Is rollback preserved?** Ensure a way to revert to a stable configuration if a new profile drops logs or increases load.
12. **Is there operational documentation?** Document how to temporarily enable diagnostics without modifying the application and how to turn them off afterward.

**Conclusion:** Logback supports environment-specific configuration through properties, configuration files, and logger/appender rules. In **Spring Boot applications**, `logback-spring.xml` adds `springProfile` and `springProperty` to conditionalize configuration based on the Spring Environment. For reliable configuration, clearly separate environment labels from actual log levels, keep logger names consistent, test effective levels and output, and protect sensitive data across every profile.
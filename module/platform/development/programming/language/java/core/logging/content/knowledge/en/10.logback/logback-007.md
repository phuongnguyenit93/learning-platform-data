# logback-spring.xml in Spring Boot: Environment-Specific Logback Configuration

**`logback-spring.xml`** is the Logback configuration file name that **Spring Boot** can load and process using its own logging mechanism. This file lets you write standard Logback configuration (loggers, appenders, encoders, rolling files, etc.) and use several **Spring Boot extensions**, such as `<springProfile>` to branch by Spring profile and `<springProperty>` to read values from the Spring `Environment`.

This file name is not a general Java Core concept or a syntax that standalone Logback understands on its own. It is intended for applications running **Spring Boot + Logback** with the appropriate runtime support. The document below explains how the file is loaded, its syntax, a Java 17/Spring Boot example, and common configuration pitfalls, following one key principle: **the configuration must match the backend, the initialization timing, and the environment**.

## 1. What Is `logback-spring.xml` Used For?

An application typically emits logs through SLF4J:

```java
// Fragment in a class that already has SLF4J and a LOG variable.
LOG.info("event=order_received orderId={}", orderId);
```

Business code only states "emit an event at the INFO level." Decisions about **where to print, how to format, how long to retain, and whether DEBUG is enabled** are handled by the logging backend, such as Logback.

```text
Spring Boot bootstrap
      |
      | LoggingSystem loads logging configuration
      v
logback-spring.xml
      |
      +-- <springProperty> reads Spring Environment
      +-- <springProfile> selects configuration sections by profile
      +-- <logger> / <root> sets logger level and scope
      +-- <appender> selects console, file, network...
      +-- <encoder> / <pattern> formats messages
      |
      v
SLF4J Logger -> Logback -> appender -> console / file / collector
```

`logback-spring.xml` configures **the path of logs**, rather than creating a logger for each class. Java classes still use `org.slf4j.LoggerFactory.getLogger(MyClass.class)` or an equivalent approach chosen by the project.

Practical benefits:

1. **Environment-specific log levels:** enable `DEBUG` for a module during development, and restrict to `INFO` or `WARN` in production.
2. **Output customization:** console for containers, rolling files for environments that require file storage, or encoders suited to a log collector.
3. **Application-wide consistency:** a single configuration handles loggers using the Logback backend, instead of each service creating its own appender.
4. **Leveraging the Spring Environment:** reference properties such as `spring.application.name`, optionally with a default value.
5. **Easy inspection:** reading the file helps determine why `DEBUG` is filtered out, why events are printed twice, or why the application is not creating a log file.

## 2. How Does `logback-spring.xml` Differ from `logback.xml`?

| Criterion | `logback.xml` | `logback-spring.xml` |
| --- | --- | --- |
| Processed by | Can be discovered and loaded early by **Logback** itself | Recognized and processed by **Spring Boot LoggingSystem** when Boot controls logging |
| Common location | Root of the classpath | `src/main/resources/logback-spring.xml` → root of the classpath after packaging |
| Standard Logback syntax | Yes | Yes |
| `<springProfile>`, `<springProperty>` extensions | **Not usable directly** when Logback self-loads early | Yes, when Boot loads it properly |
| Suitability for Spring Boot apps | Valid when Spring extensions are not needed | Usually preferred when Spring extensions are needed or when Boot should control initialization |
| Use in plain Java apps with Logback only (no Boot) | Yes | Should not assume Logback will discover and understand this file name on its own |

**Key point:** Spring Boot initializes the logging system quite early, before the full `ApplicationContext` is ready. Plain Logback may read `logback.xml` before Boot is ready to provide its extensions. Therefore, placing `<springProfile>` in `logback.xml` typically causes parser errors; renaming it to `logback-spring.xml` and letting Boot load it is the approach recommended by Spring Boot documentation. If the file needs to live elsewhere, you can point the `logging.config` property to the corresponding resource.

**Avoid having both files unmanaged:** When multiple logging configurations exist on the classpath, it becomes hard to tell which file is in effect, and one file may be loaded by the backend before Boot. Keep **one intentional primary configuration source** and check the file-selection rules of the Boot version you are using.

### Where Should the File Be Placed?

Common Maven application structure:

```text
my-app/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/Application.java
    └── resources/
        ├── application.properties
        └── logback-spring.xml
```

In this structure, Maven places the XML file at the classpath root. When running a Spring Boot executable JAR, the file resides in the application's resources.

If you intentionally use a file outside the classpath, Boot configuration can use:

```properties
logging.config=file:/opt/my-app/config/logback-spring.xml
```

This is an **example path**; the file must exist and the process must have read permissions. For a file inside the JAR, you can specify `classpath:logback-spring.xml`. Because logging initializes early, `logging.config` should come from a configuration source that Boot reads early enough (system properties, command-line arguments, or an appropriate `application.properties`), rather than expecting a `@PropertySource` added late in a bean.

## 3. Basic Logback XML Structure

A `logback-spring.xml` file can use standard elements:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Meaning:

- **`<configuration>`**: the root of the Logback configuration.
- **`<appender name="CONSOLE">`**: defines a destination for events. `ConsoleAppender` typically writes to the console; Logback also provides file appenders, rolling file appenders, and other implementations.
- **`<encoder>`** and `<pattern>`: encodes/formats events. `%d` is the timestamp, `%level` is the level, `%logger` is the logger name, `%msg` is the message, and `%n` is a newline.
- **`<logger name="...">`**: adjusts the level for a category or group of categories.
- **`<root level="INFO">`**: sets the root logger level. Loggers without an explicit level typically inherit the appropriate effective level according to the backend hierarchy.
- **`<appender-ref>`**: attaches a defined appender to a logger or root. Merely defining an appender does not guarantee events will be sent to it.

This XML snippet is **a valid configuration for an application with Logback**, without depending on Spring extensions yet. With a file containing this exact XML, you could also use `logback.xml` if the application does not need `springProfile` and `springProperty`.

Note: child loggers can propagate events up to parent loggers through Logback's additivity mechanism. If you attach the same destination at both levels while additivity remains enabled, the same event may be written **twice** to the console or file.

## 4. `<springProfile>`: Profile-Based Configuration

The `springProfile` extension lets you enable a configuration block when a Spring profile expression matches:

```xml
<springProfile name="dev">
    <logger name="com.example.logging" level="DEBUG"/>
</springProfile>

<springProfile name="!dev">
    <logger name="com.example.logging" level="INFO"/>
</springProfile>
```

The two blocks above are **fragments to place inside `<configuration>`** of `logback-spring.xml`. When the `dev` profile is active, loggers under `com.example.logging` are set to `DEBUG`; when `dev` is inactive, they are set to `INFO`.

Supported usage patterns in Spring Boot can include:

- `name="dev"`: only when `dev` is active.
- `name="!prod"`: when `prod` is not active.
- `name="dev | staging"`: when at least one of the two profiles is active.
- `name="prod & eu"`: when both are active. Inside an XML attribute, `&` must be escaped as `&amp;`: `name="prod &amp; eu"`.

**A profile name is not a file name:** the `dev` profile can be activated via `--spring.profiles.active=dev`, `SPRING_PROFILES_ACTIVE`, or application configuration. Avoid hardcoding conflicting `spring.profiles.active` values across multiple sources without understanding configuration precedence rules.

### `springProfile` Is Not a Log Level in Java Application Code

`log.debug(...)` calls remain in the source code in every environment. Whether an event appears depends on the **effective level** of the logger and any filters/appenders. Do not write `if (dev) log.debug(...)` just to replace logging policy; profiles and levels in configuration are the proper mechanism when only verbosity changes.

## 5. `<springProperty>`: Reading Values from the Spring Environment

When you want to include the application name in logs, Boot can read `spring.application.name` from `application.properties`:

```properties
spring.application.name=order-service
```

In `logback-spring.xml`:

```xml
<springProperty scope="context"
                name="serviceName"
                source="spring.application.name"
                defaultValue="unknown-service"/>

<appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
        <pattern>%d{HH:mm:ss.SSS} %-5level service=${serviceName} %logger{36} - %msg%n</pattern>
    </encoder>
</appender>
```

This is a **fragment**: it must be placed inside `<configuration>`, and the appender must be referenced by `root` or a `logger` to receive events. After Boot loads the file, `springProperty` sets a Logback property named `serviceName`, which can be used in `<pattern>`. If the Spring Environment does not have the corresponding key, `defaultValue` provides a fallback.

Comparison:

| Syntax | Value Source | Meaning |
| --- | --- | --- |
| `<springProperty source="spring.application.name" .../>` | Spring `Environment` | Retrieves a Boot-managed property for use in Logback |
| `<property name="..." value="..."/>` | Logback configuration | Declares a Logback property directly |
| `${serviceName}` | A Logback property already set | References the value inside the XML configuration |
| `%X{requestId}` | Event MDC | Inserts the request ID if the application/tracing put it into MDC |

With `springProperty`, the `source` name should use **Spring Boot's canonical kebab-case** when hyphens are needed, such as `my.feature-name`, rather than relying arbitrarily on relaxed binding. A `springProperty` does not automatically pull values from late-created Spring beans, and **it should not be used to inject secrets into logs**.

Database credentials, passwords, access tokens, or secret keys may exist in the Spring Environment, but **must not be extracted and printed into patterns**. `springProperty` is a configuration convenience, not a security feature.

## 6. Runnable Example: Spring Boot + Java 17 + `logback-spring.xml`

This example uses **Spring Boot 3.5.16**, Java 17, and Maven. This is a specific version used to illustrate the exercise, not a claim that it is the latest version at all times. The code creates an application without a web server, runs a `CommandLineRunner` to emit logs, and exits. It only uses `spring-boot-starter`, which brings in the appropriate logging dependencies in a standard starter setup.

Structure:

```text
logback-spring-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/logging/LoggingConfigDemo.java
    └── resources/
        ├── application.properties
        └── logback-spring.xml
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>logback-spring-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Because the Spring Boot parent manages dependency and plugin versions, the example **does not manually add another Logback or SLF4J provider alongside it**. If your project replaces `spring-boot-starter-logging` with Log4j 2, `logback-spring.xml` will no longer be the configuration file for the backend you are running.

### 6.2. `application.properties`

```properties
spring.application.name=logging-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
```

Do not fix `spring.profiles.active` in this file so you can test running **with and without the `dev` profile** via command-line arguments.

### 6.3. `logback-spring.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <springProperty scope="context"
                    name="serviceName"
                    source="spring.application.name"
                    defaultValue="unknown-service"/>

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level service=${serviceName} %logger{40} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="dev">
        <logger name="com.example.logging" level="DEBUG"/>
    </springProfile>

    <springProfile name="!dev">
        <logger name="com.example.logging" level="INFO"/>
    </springProfile>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This is a **complete file**, not a fragment. `springProperty` reads `spring.application.name`, producing `service=logging-demo` in the pattern. `springProfile` selects the level for the `com.example.logging` package logger. `root` stays at INFO and attaches a single console appender, avoiding duplicate logs.

The configuration above **does not need `scan="true"`** and does not add a file appender on its own. In production systems, consider timestamps with a timezone, structured logging, exception patterns, MDC, and an appropriate collection mechanism; the short pattern here is mainly for easy comparison.

### 6.4. `LoggingConfigDemo.java`

```java
package com.example.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoggingConfigDemo implements CommandLineRunner {
    private static final Logger LOG =
            LoggerFactory.getLogger(LoggingConfigDemo.class);

    public static void main(String[] args) {
        SpringApplication.run(LoggingConfigDemo.class, args);
    }

    @Override
    public void run(String... args) {
        LOG.debug("event=debug_probe requestId={}", "req-17");
        LOG.info("event=sample_ready requestId={}", "req-17");
        System.out.println("demoFinished=true");
    }
}
```

The Java code only uses the SLF4J API via the Spring Boot starter, without embedding `if (dev)` logic in logger calls. Changing the profile only changes the configuration, not the compiled classes.

### 6.5. Building and Running

Inside the `logback-spring-demo/` directory:

```bash
mvn -q package
java -jar target/logback-spring-demo-0.0.1-SNAPSHOT.jar
```

Running **without `dev`** will emit logs from the example similar to:

```text
10:15:30.125 INFO  service=logging-demo com.example.logging.LoggingConfigDemo - event=sample_ready requestId=req-17
demoFinished=true
```

This is an **illustrative snippet**: actual timestamps will differ, Spring Boot also logs other startup events, and the console may interleave stdout with backend output. Within the program itself, `System.out.println` prints **exactly** one line `demoFinished=true`; that does not mean total stdout consists of only one line.

Running with the `dev` profile:

```bash
java -jar target/logback-spring-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=dev
```

Then the two logs emitted by `CommandLineRunner` look like:

```text
10:15:30.125 DEBUG service=logging-demo com.example.logging.LoggingConfigDemo - event=debug_probe requestId=req-17
10:15:30.126 INFO  service=logging-demo com.example.logging.LoggingConfigDemo - event=sample_ready requestId=req-17
demoFinished=true
```

This is also **illustrative**; timestamps and ordering relative to Spring Boot startup logs are not fixed. The key check is that `DEBUG` should only appear when the `dev` profile is active, while `INFO` and `demoFinished=true` appear in both runs.

**Self-check step:** Remove or rename `src/main/resources/logback-spring.xml`, rebuild, and compare against Spring Boot's default format. When using the custom file, the `service=logging-demo` pattern will appear in logs written by `CONSOLE`. If you do not see it, check the file name, classpath location, actual backend, and `logging.config`.

## 7. Using Spring Boot's Template Configurations with `<include>`

You do not always need to write every pattern and appender from scratch. Spring Boot provides resources that can be included, for example:

- `org/springframework/boot/logging/logback/defaults.xml`: several default conversion rules and pattern properties.
- `org/springframework/boot/logging/logback/console-appender.xml`: common console appender definition.
- `org/springframework/boot/logging/logback/file-appender.xml`: file appender definition with Boot-provided policies.
- In Spring Boot branches that support structured logging, there are also includes for structured console/file appenders; check the Boot version you are running.

Example of **a complete alternative configuration** for `logback-spring.xml`, not combined with the file in section 6:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>
    <include resource="org/springframework/boot/logging/logback/console-appender.xml"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

This lets Spring Boot maintain the framework's own pattern and console conventions. Do not place both the alternative configuration file and the file from section 6 in the same location and assume Spring Boot will merge them automatically. If you want custom behavior, intentionally choose one clear configuration strategy.

**Version note:** Boot-provided includes and properties can change across release branches; `base.xml` was a legacy compatibility resource in some versions, but it should not be treated as a mandatory foundation for new configurations. Check the documentation for the specific Spring Boot version you are running.

## 8. Console, Rolling Files, and Deployment Environments

Console output suits many containerized applications: external systems can collect stdout/stderr from the process. File logs are useful if the environment requires local files and has an appropriate retention/shipping policy. Choose the destination based on operational architecture, **not merely because a file appender can be configured**.

If you need to add a rolling file in an application using Logback, the **fragment** below can be placed inside `<configuration>` and then referenced via `<appender-ref ref="FILE"/>` on `root` or the appropriate `logger`:

```xml
<appender name="FILE" class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>

    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>20MB</maxFileSize>
        <maxHistory>14</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger{36} - %msg%n</pattern>
    </encoder>
</appender>
```

Explanation:

- `<file>` specifies the path of the active log file. Relative paths are resolved against the process working directory.
- `SizeAndTimeBasedRollingPolicy` supports time- and size-based rotation; `%d` and `%i` are components of the archive file name.
- `maxHistory` limits history by number of periods; `totalSizeCap` caps total archive storage size according to the policy.
- `<appender-ref>` must attach `FILE` to the appropriate `logger` or `root`. **Merely declaring an appender** does not produce output if no events are routed to it.

**Do not blindly put a file appender into production while ignoring** directory write permissions, read-only filesystems, quotas, container lifecycle, retention, backups, and storage costs. If you only use file logging without console logging, verify that your log collector can still retrieve the logs.

Spring Boot also has properties such as `logging.file.name` and several rolling policy settings; however, once you fully define a file appender and rolling policy in XML, **do not assume** Spring Boot properties will automatically modify that appender. Check explicitly which values are actually referenced in the XML.

## 9. Precedence Between `application.properties` and Logback XML

In Spring Boot, two places are commonly used to select log levels:

**Spring Environment:**

```properties
logging.level.root=INFO
logging.level.com.example.logging=DEBUG
```

**Logback XML:**

```xml
<logger name="com.example.logging" level="INFO"/>
<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
```

These are **two separate illustrative ways to configure levels**. When used together, Spring Boot's `LoggingSystem` may apply level settings from the Environment during initialization, causing the effective level to differ from what is written in XML. Avoid claiming "XML always wins" or "properties always win" for every aspect; verify the behavior of your Boot version and actual configuration.

A maintainable division of responsibilities:

- Use `application.properties`/`application.yaml` for simple log levels and application configuration properties.
- Use `logback-spring.xml` when you need custom patterns, appenders, filters, rolling policies, or profile-based extensions.
- Do not scatter the same level rule across multiple places without a deliberate reason.
- Only use `logging.config` when you need to point to a configuration file in a different location or when project conventions require it.

Properties like `logging.file.name`, `logging.pattern.console`, or `logging.structured.format.console` behave depending on how the backend is configured. A custom `<encoder>` with a hardcoded pattern **does not automatically read every Spring Boot customization property** unless the XML references them or uses the appropriate includes.

## 10. Combining MDC, Structured Logging, and Exceptions

To investigate errors across requests, a text pattern can include MDC fields:

```xml
<pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level requestId=%X{requestId} traceId=%X{traceId} %logger - %msg%n</pattern>
```

This is a **fragment inside an encoder**, not a complete Logback file. `%X{requestId}` and `%X{traceId}` only contain data if the application or instrumentation has populated MDC. `logback-spring.xml` does not generate request IDs, create distributed traces, or automatically propagate MDC across all thread pools. When using async or reactive execution, proper context propagation and cleanup are required to avoid assigning the wrong ID across requests.

For exceptions:

```java
// Fragment in an application with SLF4J; LOG and the variable e are already declared.
LOG.error("event=operation_failed requestId={}", requestId, e);
```

The `Throwable` is passed to the backend so the layout/encoder can decide how to format the stack trace. When editing a custom pattern, verify that stack traces are actually written; Logback provides conversion words for exceptions and may append exception details automatically in some configurations, but do not rely on that if you have configured a specialized encoder/layout.

**Structured logging:** If a collector requires each event to be a JSON object, use a formatter/encoder that supports JSON and proper escaping instead of assembling JSON messages via string concatenation. Newer Spring Boot versions have built-in structured logging support; how to enable it and which formats are supported depend on the release branch. Do not write an ad-hoc JSON string-concatenation `<pattern>` and assume user data is properly escaped.

Do not log `Authorization` headers, session cookies, tokens, passwords, or sensitive personal payloads in messages or MDC. `springProperty` is also not a valid way to put secrets into log output.

## 11. Common Issues with `logback-spring.xml`

| Symptom | Common Cause | How to Investigate |
| --- | --- | --- |
| XML file has no effect | Wrong file name or wrong `src/main/resources` location; runtime uses a different backend | Check JAR/classpath, `logging.config`, and actual provider/backend |
| `no applicable action for [springProfile]` | Extension loaded by plain Logback or config re-scanned | Use `logback-spring.xml` loaded by Boot; avoid `scan="true"` with extensions |
| `no applicable action for [springProperty]` | File loaded at the wrong time or not processed by Boot | Check how the file is loaded and whether scanning is enabled |
| `serviceName_IS_UNDEFINED` or wrong property value | Wrong `source` name, missing value, wrong Logback property scope | Use appropriate kebab-case, check `spring.application.name`, and `defaultValue` |
| `DEBUG` not visible in `dev` | Profile not active, logger category mismatch, or another filter blocking | Check active profiles, effective logger level, and appender |
| Logs printed twice | Two console appenders, additivity, or overlapping configurations | Trace the path logger → root → appender |
| Log file not created | `FILE` not attached, path not writable, or appender initialization error | Check `appender-ref`, path/permissions, and Logback internal status |
| Logs appear on console but collector misses them | Collector reads the wrong stream or format is incompatible | Check stdout/stderr, pipeline, parser, and container collection setup |
| Pattern ignores `logging.pattern.console` | Custom encoder has its own pattern without referencing Boot properties | Use Boot includes or explicitly wire properties in XML |
| `logging.level.*` differs from expected | Level declared in multiple places or another profile is active | Check configuration layers and runtime effective values |
| Scan configuration fails after editing XML | Logback re-scans the file without Boot extensions available during that parse | Disable scan and use reload mechanisms supported by Boot/the framework |
| Using Logback XML with Log4j 2 | Backend does not understand the syntax or ignores the file | Use the configuration for the active backend, e.g., `log4j2-spring.xml` if switched to Log4j 2 |

**Recommended troubleshooting sequence:**

1. Confirm the application is actually using **Spring Boot + Logback** with a compatible provider.
2. Confirm the file is at the **right classpath location** and `logging.config` does not point elsewhere.
3. Check startup logs for XML parse errors, missing appenders, or undefined properties.
4. Check which Spring profiles are active before concluding `springProfile` is wrong.
5. Check logger categories, levels, filters, additivity, and `appender-ref` along the relevant branch.
6. Compare an `INFO` event and a `DEBUG` event across both profiles; inspect the output at the actual destination.
7. If using files or a collector, verify paths, permissions, and the collection pipeline—not just that the logger was called.

## 12. Deployment Rules and Checklist

Before introducing `logback-spring.xml` into a project, verify:

- **Right backend:** runtime uses Logback with compatible dependencies/providers; not mistakenly configuring Log4j 2.
- **Right path:** `src/main/resources/logback-spring.xml` or a file specified via `logging.config`; avoid competing config files.
- **Right Spring mechanism:** `springProfile` and `springProperty` are only used in configurations actually loaded by Boot; do not enable Logback auto-scan alongside extensions.
- **Right profile coverage:** test `dev`, `prod`, and no-profile runs; do not let verbose `DEBUG` logs appear unintendedly.
- **Right loggers and appenders:** `root`/loggers have `appender-ref`, sensible additivity, and no duplicate log output.
- **Right format:** timestamps with an explicit timezone in operational environments, level, logger name, service, correlation IDs, and stack traces when needed.
- **Right data:** no passwords, tokens, session cookies, or disallowed PII; untrusted input is encoded/escaped.
- **Right storage:** rolling/retention, capacity, file write permissions, or collector setup are configured and tested.
- **Right configuration coordination:** no accidental overrides across `application.properties`, `logging.level.*`, and XML.
- **Right versions:** includes, extensions, and property keys are compatible with the specific Spring Boot/Logback versions.

**Remember:** `logback-spring.xml` is **Logback configuration managed by Spring Boot**, most useful when you need Spring profiles and properties together with Logback appenders and encoders. Java code continues to emit logs via SLF4J; Boot loads the configuration at the right time to determine levels, formats, and destinations. A good configuration must be **readable, testable per environment, and must never leak sensitive data**.

## Official Documentation

- Spring Boot, *Logging (reference)*: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot, *Configure Logback for Logging*: https://docs.spring.io/spring-boot/how-to/logging.html
- Logback, *Configuration*: https://logback.qos.ch/manual/configuration.html

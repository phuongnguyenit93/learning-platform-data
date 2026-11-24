# logback-spring.xml or Equivalent Logging System Configuration

Logging is one of the very first components initialized when a Spring Boot application begins running. Even before the entire ApplicationContext is created, Spring Boot already needs to record startup information, profiles, configuration parsing failures, and causes of startup failure. Once the application is running, logging continues supporting request diagnostics, business events, warnings, and incidents.

Spring Boot allows configuring logging at two levels:

- **Simple configuration via properties**: using keys such as **logging.level.root**, **logging.level.com.example**, and **logging.file.name** to adjust log levels and common behaviors.
- **Detailed configuration via the logging system's dedicated file**: for Logback this is typically **logback-spring.xml**; for Log4j2 there is an equivalent XML configuration such as **log4j2-spring.xml**. These files control appenders, encoders, log patterns, logger hierarchies, file rotation, and advanced rules.

The focus of this lesson is **logback-spring.xml** in Spring Boot, while also explaining how to transfer this mindset to another logging system. We will build configurations featuring console logging, file rotation, package-level log settings, Spring profile-based configuration, and ways to observe/diagnose when logs do not behave as expected.

## 1. Three layers of logging in Spring Boot

To configure properly, distinguish:

1. **Logging API**: application code calls loggers to emit log events.
2. **Logging implementation**: the library that actually processes logs, e.g., Logback or Log4j2.
3. **Logging configuration**: rules deciding log levels, formatting, routing to console/file, and output lifecycle management.

A typical diagram:

~~~text
OrderService / PaymentService / Controller
                 │
                 ▼
           SLF4J Logger
                 │
                 ▼
       Logging implementation
            (Logback)
                 │
                 ▼
        logback-spring.xml
                 │
        ┌────────┴────────┐
        ▼                 ▼
    ConsoleAppender    RollingFileAppender
        │                 │
        ▼                 ▼
     stdout/stderr      log files
~~~

**SLF4J** is the API/facade that code normally uses; **Logback** is an implementation capable of executing it. Spring Boot provides a **LoggingSystem** class to initialize and control the logging implementation present on the classpath.

Using the right abstraction means most business code needs no changes when switching backends from Logback to Log4j2.

### 1.1. Logging in Java code

Example service:

~~~java
package com.example.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void createOrder(String orderId) {
        log.info("Creating order {}", orderId);
        log.debug("Validating order {}", orderId);
        // Business logic.
    }
}
~~~

In the code above:

- **LoggerFactory.getLogger(OrderService.class)** creates/retrieves a logger named after the class.
- **log.info** records normal operational activity.
- **log.debug** supplies details for diagnostics.
- The **{}** placeholder formats parameters via the SLF4J API instead of manual string concatenation.

The code above does not dictate which file logs go to, what color they are, or whether rotation occurs. That is the responsibility of logging configuration.

### 1.2. Spring Boot usually chooses Logback by default

In applications using standard Spring Boot starters, the **spring-boot-starter-logging** dependency usually brings Logback and necessary bridging components into the application.

Do not conclude that **every** Spring Boot application uses Logback: a project can exclude the default logging starter and use Log4j2, or alter the dependency graph and logging implementation.

If `logback-spring.xml` has no effect, the first step is confirming the **actual logging backend on the runtime classpath**. A Logback file will not configure Log4j2.

## 2. When is application.yml enough?

Before writing XML, check whether your needs can be solved with Spring Boot properties.

Example `application.yml`:

~~~yaml
logging:
  level:
    root: INFO
    com.example.orders: DEBUG
    org.springframework.web: WARN
~~~

Meaning:

- The default root logger uses INFO.
- Loggers under `com.example.orders` are permitted to log DEBUG unless overridden by a closer level.
- Loggers under `org.springframework.web` only emit WARN and above in the corresponding cases.

With Spring Boot's default logging implementation and output, this configuration may suffice for many services.

### 2.1. File output via property

Example:

~~~yaml
logging:
  file:
    name: logs/my-application.log
~~~

Spring Boot can enable file logging with the specified filename. However, requirements such as **multiple files per package, special rolling policies, custom encoders, multiple appenders, or profile-based configuration** usually require a dedicated configuration file.

### 2.2. Logging patterns via properties

Properties such as:

~~~properties
logging.pattern.console=%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n
logging.pattern.file=%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n
~~~

can customize patterns when using a logging setup compatible with Spring Boot's support mechanism.

**Note:** if you completely replace the Logback configuration with your own XML, these pattern properties do not necessarily apply automatically. The XML file must reference Boot-provided properties or declare patterns itself. Do not assume an arbitrary XML config automatically inherits Boot's default patterns.

### 2.3. When to move to logback-spring.xml?

Consider `logback-spring.xml` when you need:

- **ConsoleAppender and RollingFileAppender** with independent settings.
- Separate loggers for a specific package or event type.
- Rolling by date, size, and retention policies.
- **springProfile** or **springProperty** to select configuration from the Spring Environment.
- AsyncAppender, custom encoders, or specialized filters.
- Distinct logging rules for local vs production environments.

Conversely, if the goal is merely changing one package's log level from INFO to DEBUG, **logging.level** is usually simpler and easier to operate.

## 3. Where does logback-spring.xml live?

In a Spring Boot application using Logback, the standard location is:

~~~text
src/
└── main/
    └── resources/
        ├── application.yml
        └── logback-spring.xml
~~~

After building, the file resides on the application's **runtime classpath**. When running an executable JAR, Spring Boot finds this resource via its logging configuration mechanism.

The name **logback-spring.xml** matters: this is the name Spring Boot recommends so Spring-integrated extensions apply when Boot initializes Logback.

### 3.1. Distinguishing logback.xml and logback-spring.xml

| Criterion | logback.xml | logback-spring.xml |
|---|---|---|
| Who can detect it early? | Logback detects it via native discovery. | Spring Boot recognizes and loads it via supported mechanism. |
| Standard Logback syntax | Yes | Yes |
| `springProfile`/`springProperty` extensions | Should not be relied upon during native loading. | Supported by Spring Boot when Boot manages loading. |
| Spring Environment interaction | Not directly available in native Logback parser. | Can use Boot's extensions. |
| Common choice in Spring Boot | Only when native semantics are intentionally required. | Usually preferred for full integration. |

**logback.xml** can be loaded very early by Logback, before Spring Boot has enough Environment ready to process Spring-specific tags. Thus a `logback.xml` containing `springProfile` can raise parser errors or fail to behave as expected.

**logback-spring.xml** gives Boot better control over loading and supports its extensions. This is the preferred choice if the application needs profile conditions or binding a Spring property into XML.

### 3.2. Not every arbitrarily named file loads automatically

For example, a file:

~~~text
src/main/resources/logging/my-logback.xml
~~~

will not be picked up automatically just by existing on the classpath. To use a file with a non-conventional name or location, specify it via **logging.config**.

### 3.3. Separating logging files from application.yml

`application.yml` typically holds high-level Spring Boot configurations such as `logging.level` and application properties.

`logback-spring.xml` describes Logback-specific structures: appenders, encoders, policies, and logger hierarchy.

Both files can coexist. What matters is avoiding duplicate, conflicting configurations without knowing which source holds final control.

## 4. Minimal logback-spring.xml file

Console logging configuration example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>

</configuration>
~~~

This configuration has one appender named `CONSOLE` and a root logger at `INFO`.

Example output:

~~~text
2026-11-13 09:15:23.104 INFO  [main] c.e.orders.OrderService - Creating order ORD-17
~~~

### 4.1. Parts of the XML

| Element | Role |
|---|---|
| **configuration** | Root of the Logback configuration. |
| **appender** | Defines where logs are written, e.g., console or file. |
| **encoder** | Converts a logging event into strings/bytes. |
| **charset** | Character set of text data emitted by the encoder. |
| **pattern** | How fields of a log event are formatted. |
| **root** | Root logger inherited by the logger hierarchy, unless overridden specifically. |
| **appender-ref** | Attaches a defined appender to a logger. |

An appender that is declared yet **not attached to a logger/root** will not receive events as intended. Logback needs both the output destination and the route delivering events to that destination.

### 4.2. Meaning of common pattern tokens

| Token | Typical meaning |
|---|---|
| **%d{...}** | Timestamp in the specified format. |
| **%level** or **%p** | Log level such as INFO/WARN/ERROR. |
| **%-5level** | Prints log level left-aligned in a field at least 5 characters wide. |
| **%thread** | Name of the thread emitting the log. |
| **%logger{36}** | Logger name abbreviated to configured length. |
| **%msg** or **%message** | Formatted message content. |
| **%n** | Platform-appropriate newline character. |
| **%ex** or **%throwable** | Exception/stack trace information. |
| **%X{requestId}** | MDC value under key `requestId`, if present. |

Patterns are Logback's language, not Spring template syntax. Each logging system can have different tokens, escaping, and layout syntax.

### 4.3. Do not carelessly drop stack traces

If an application has:

~~~java
try {
    paymentClient.charge(orderId);
} catch (Exception ex) {
    log.error("Charge failed for order {}", orderId, ex);
}
~~~

the log event carries a Throwable. Logback encoders can display stack traces; exact rendering depends on the configured pattern and converters.

In configurations needing error diagnostics, verify whether stack traces are preserved. A custom pattern keeping only messages or a custom encoder/filter can strip root-cause details that operations depend on.

## 5. Log levels and logger hierarchy

Common levels from most detailed to most severe:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

When the threshold is INFO, INFO/WARN/ERROR events are normally allowed through; TRACE/DEBUG are filtered out at the level check step.

For class:

~~~java
package com.example.orders.service;

public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);
}
~~~

the logger takes a name matching the class, usually:

~~~text
com.example.orders.service.OrderService
~~~

Loggers can inherit their effective level from parent packages in the hierarchy:

~~~text
ROOT                 INFO
└── com
    └── example      DEBUG
        └── orders   (inherits DEBUG)
            └── service
                └── OrderService
~~~

### 5.1. Configuring package loggers in XML

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG"/>
    <logger name="org.springframework.web" level="WARN"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Then:

- `com.example.orders` and child loggers without their own level can log DEBUG.
- `org.springframework.web` has threshold WARN.
- Other loggers inherit INFO from root unless a closer override exists.

The loggers in the example do not define their own appenders. Events propagate up the logger hierarchy to root's appender.

### 5.2. Difference between level and appender

**Level** answers: is this event permitted to be logged?

**Appender** answers: if the event passes, where is it sent?

A DEBUG logger may still fail to appear in an expected file if the file appender is not attached or an appender filter blocks it. Conversely, a properly working FileAppender cannot print DEBUG from a logger whose effective level is WARN.

Diagnostics must verify **both level thresholds and appender routing paths**.

## 6. Additivity: why can a log line appear twice?

By default, Logback uses **additivity** to propagate events from child loggers up the parent hierarchy. This is usually convenient because package loggers do not need their own appender attachments.

However, it can produce duplicate logs when a logger has its own appender and also propagates up to root carrying the same appender.

Example prone to duplication:

~~~xml
<logger name="com.example.orders" level="DEBUG">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

For an event in `com.example.orders`, `CONSOLE` can be invoked at the child logger **and** at root.

### 6.1. Solution when wanting a dedicated appender

~~~xml
<logger name="com.example.orders"
        level="DEBUG"
        additivity="false">
    <appender-ref ref="CONSOLE"/>
</logger>

<root level="INFO">
    <appender-ref ref="CONSOLE"/>
</root>
~~~

**additivity="false"** stops forwarding events up to ancestor loggers along the normal path. That logger uses only the appenders attached directly to it.

### 6.2. Be careful when turning off additivity

If you write:

~~~xml
<logger name="com.example.orders"
        level="DEBUG"
        additivity="false"/>
~~~

without attaching an appropriate appender, events from this package can disappear because they neither propagate to root nor have their own output destination.

Practical rules:

- Only changing a package's level → usually no need to disable additivity.
- Attaching a dedicated appender and not wanting duplicate writes to root → consider `additivity=false`.
- Wanting logs in both console and file → intentionally attach both appenders to root or the target logger.

## 7. Using springProfile in logback-spring.xml

Spring Boot adds the **springProfile** element so sections of Logback config apply only when a Spring profile expression matches.

Suppose you want:

- Local/dev: enable DEBUG to troubleshoot easily.
- Other profiles: keep INFO to reduce log volume.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="local | dev">
        <logger name="com.example" level="DEBUG"/>
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

    <springProfile name="!local &amp; !dev">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

</configuration>
~~~

In XML, the **&** character used in boolean expressions must be escaped as **&amp;**. This is an XML syntax rule, not a special quirk of Spring profile expressions.

When `local` or `dev` is active, logger `com.example` is set to DEBUG. In all other cases, root INFO is used via the second branch.

### 7.1. springProfile is a condition, not a command to activate a profile

~~~xml
<springProfile name="prod">
    <!-- Content is loaded only if prod matches. -->
</springProfile>
~~~

This **does not activate** `prod` on its own. Spring Boot reads profile state from the Environment prepared during startup.

To activate a profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Or use an environment variable:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

### 7.2. Do not confuse !prod with dev

~~~xml
<springProfile name="!prod">
    <!-- Applies to local, test, staging... -->
</springProfile>
~~~

Condition **!prod** matches whenever `prod` is not active. It does not mean "dev only".

If DEBUG logging might expose data or create heavy load, use an explicit allowlist of profiles like `local/dev` rather than an overly broad negation condition.

### 7.3. Multiple profiles can be active simultaneously

If the application runs with:

~~~text
spring.profiles.active=dev,prod
~~~

both `dev` and `prod` conditions can match. Do not structure Logback config with two blocks assumed "never to match together" unless the project strictly prevents profile combinations.

In complex configs, define one baseline root appender/level, then use `springProfile` to adjust only the parts that differ. This reduces risks of duplicate root blocks or attaching appenders twice.

## 8. Using springProperty to pull values from the Spring Environment

**springProperty** is a Spring Boot extension that extracts a property from the Environment and binds it to a named variable for use inside Logback configuration.

Example:

~~~yaml
spring:
  application:
    name: order-api

app:
  logging:
    directory: logs/order-api
~~~

In `logback-spring.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <springProperty scope="context"
                    name="appName"
                    source="spring.application.name"
                    defaultValue="demo-service"/>

    <springProperty scope="context"
                    name="logDirectory"
                    source="app.logging.directory"
                    defaultValue="logs"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [${appName}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>

</configuration>
~~~

Meaning:

- **source** is the property key in the Spring Environment.
- **name** is the variable name referenced in Logback, e.g., **${appName}**.
- **defaultValue** is the fallback if the Spring property is missing.
- **scope="context"** scopes the property to the Logback context.

In the snippet above, `logDirectory` is not yet used to create a file appender; it demonstrates reading a path from the Environment, which will be used in the rolling file section.

### 8.1. Use canonical property names

In **springProperty source**, use canonical kebab-case property names. Example:

~~~xml
<springProperty name="logDir"
                source="app.logging.directory"
                defaultValue="logs"/>
~~~

If a Java property is named `connectTimeout`, write **connect-timeout** in configuration rather than relying on camelCase in XML. Accurate, consistent property names help Environment sources using relaxed binding resolve cleanly.

### 8.2. Do not rely on @Value or application beans in XML

The logging system initializes very early. When `logback-spring.xml` is processed, the application's `@ConfigurationProperties`, `@Service`, or `@Value` fields may not exist yet.

Do not design Logback config around injecting an already-initialized Java service.

If you need a simple setting, supply that value into the Environment early enough and read it with `springProperty`, or use system properties/environment variables supported by the logging implementation. Properties from `@PropertySource` on `@Configuration` are processed late and may **not be available when the logging system initializes**.

### 8.3. Provide fallbacks so startup does not fail on missing properties

Example:

~~~xml
<springProperty name="appName"
                source="spring.application.name"
                defaultValue="unknown-application"/>
~~~

A sensible fallback for the application name keeps startup logs clear.

For file paths or sensitive appender settings, evaluate whether a fallback is appropriate. Silently falling back to the wrong directory can prevent operators from finding logs or cause permission conflicts.

## 9. Combining ConsoleAppender and RollingFileAppender

A common requirement is logging to both console and file.

Complete example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <property name="LOG_DIR" value="logs"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">

        <file>${LOG_DIR}/application.log</file>

        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] %logger{50} - %msg%n%ex</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>${LOG_DIR}/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>20MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>2GB</totalSizeCap>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="FILE"/>
    </root>

</configuration>
~~~

This Logback configuration specifies:

- `CONSOLE` writes events to the console.
- `FILE` writes events to **logs/application.log**.
- When triggered, the rolling policy rotates files by date and index.
- Historical files have a **.gz** suffix for compression.
- The root logger forwards qualifying events to both appenders.

### 9.1. Role of file and fileNamePattern

~~~xml
<file>${LOG_DIR}/application.log</file>
~~~

defines the active log file currently being written in this `RollingFileAppender` pattern.

~~~xml
<fileNamePattern>${LOG_DIR}/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
~~~

defines the archive filename after rollover. **%d** represents the date segment, and **%i** is the index used when multiple archives occur in the same period due to size limits.

These tokens belong to `RollingPolicy`, not a log line's message pattern.

### 9.2. maxFileSize, maxHistory, and totalSizeCap

| Property | Purpose |
|---|---|
| **maxFileSize** | Size threshold triggering size-based rollover in the policy. |
| **maxHistory** | Number of historical periods retained, based on the policy's time period. |
| **totalSizeCap** | Total archive storage cap enforced by Logback's cleanup mechanism. |

In the example, `maxHistory=14` with a daily period typically corresponds to retaining roughly 14 archive periods; it does not necessarily mean literally 14 files because a single day can produce multiple files via size rollover.

Actual retention also depends on the policy, cleanup timing, how the application starts, and archive counts. For systems needing logs for compliance auditing, design a centralized storage solution rather than relying solely on a container's local disk.

### 9.3. Relative file paths depend on the working directory

~~~xml
<property name="LOG_DIR" value="logs"/>
~~~

Relative paths are resolved relative to the process's working directory. In an IDE, Docker, systemd, and Kubernetes, the working directory can differ.

If file logging is important, use an explicitly configured path/volume with write permissions and rotation/cleanup policies.

### 9.4. Why limit storage size?

Using a non-rolling `FileAppender` on a long-running service can:

- Write hundreds of GBs of logs.
- Fill up the filesystem.
- Cause requests or the entire container to fail when writes fail.
- Slow down backups or incident investigations.

A rolling policy does not replace disk usage monitoring, yet it is a critical control layer when logging to local files.

## 10. Configuring file paths from Spring properties

We can replace a fixed Logback property with **springProperty**:

`application.yml`:

~~~yaml
app:
  logging:
    directory: logs
~~~

`logback-spring.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <springProperty scope="context"
                    name="logDir"
                    source="app.logging.directory"
                    defaultValue="logs"/>

    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">

        <file>${logDir}/application.log</file>

        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>${logDir}/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>

</configuration>
~~~

Run with:

~~~bash
java -jar app.jar --app.logging.directory=/var/log/my-app
~~~

and if the process has write permissions, Logback can use the provided directory.

### 10.1. Do not confuse app.logging.directory with logging.file.path

**app.logging.directory** in the example is a project-defined custom property. Spring Boot does not inherently know it controls file logging. It is the `springProperty` tag in XML and **${logDir}** references that turn it into the path.

**logging.file.path** or **logging.file.name** are Spring Boot's own properties for its supported file logging mechanism. If you write a custom XML config and do not reference those values, changing `logging.file.path` may not affect your custom FileAppender.

### 10.2. Prefer deployable configurations

Avoid hard-coding:

~~~xml
<file>C:\Users\developer\Desktop\application.log</file>
~~~

in code shared across environments. Let deployment supply the file location, or prefer stdout when the platform already collects container logs.

## 11. Choosing console in containers, files in other environments

In Docker and Kubernetes, the common pattern is writing to **stdout/stderr** and letting the platform's runtime/agent collect, rotate, forward, and store logs.

Writing local files inside containers can cause:

- Logs disappearing when a container is replaced.
- Two competing rotation mechanisms.
- Missing persistent volumes.
- Write permission failures when containers run as non-root.
- Harder log aggregation across replicas.

An illustrative profile-specific configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/local-app.log</file>
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/local-app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <springProfile name="local">
        <root level="DEBUG">
            <appender-ref ref="CONSOLE"/>
            <appender-ref ref="FILE"/>
        </root>
    </springProfile>

    <springProfile name="!local">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

</configuration>
~~~

In the example, `FILE` is defined upfront yet only attached to root in the `local` branch. With Logback, an appender may still be initialized by configuration even if not attached to a logger, depending on processing behavior; if the goal is **not touching the filesystem at all** in container environments, place **the FILE appender definition itself** inside the `local` `springProfile` rather than only moving `appender-ref`.

### 11.1. Pattern avoiding FILE creation when the profile does not need it

~~~xml
<springProfile name="local">
    <appender name="LOCAL_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/local.log</file>
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.local"
            level="DEBUG"
            additivity="false">
        <appender-ref ref="LOCAL_FILE"/>
    </logger>
</springProfile>
~~~

When `local` does not match, that config branch is skipped. Depending on your goal, you can also attach `LOCAL_FILE` to root inside that branch to capture all application logs.

### 11.2. Do not use profiles as a substitute for runtime observation

A process reporting **prod** is not guaranteed to be a container or VM with the right log volume. Logging policies must match the deployment architecture, not merely the profile name.

For production environments with centralized log pipelines, many teams prefer console JSON/structured logging or a uniform text pattern, letting infrastructure handle routing and retention.

## 12. Precedence between logging.level and XML

When using Logback with Spring Boot, log levels can appear in multiple sources:

~~~yaml
logging:
  level:
    com.example.orders: DEBUG
~~~

and:

~~~xml
<logger name="com.example.orders" level="INFO"/>
~~~

Do not maintain two conflicting sources controlling the same logger. Spring Boot initializes and applies log levels from the Environment; the observed result also depends on initialization order, whether the logging system reloads config, and runtime level-change APIs.

**Operations-friendly principle**:

- Appender structure, encoders, rolling policies → manage in `logback-spring.xml`.
- Log levels that change frequently per deployment → prefer `logging.level` in `application.yml`/env/CLI unless they need to be hard-coded in XML.
- If XML intentionally chooses levels via `springProfile` → avoid setting `logging.level` for the same logger in other sources with conflicting intent.

### 12.1. Setting a logger level via CLI

~~~bash
java -jar app.jar --logging.level.com.example.orders=DEBUG
~~~

This is useful when needing more detail for a single run to investigate a bug without editing `logback-spring.xml`.

### 12.2. Changing the level does not guarantee an appender will emit logs

If a logger has `additivity=false` yet no appender, raising its level to DEBUG still produces no logs. If an appender has its own filter discarding DEBUG, the issue also persists.

Inspect along the chain:

~~~text
Logger name
    │
Effective level
    │
Appender route / additivity
    │
Appender filter / encoder
    │
Output destination
~~~

## 13. logging.config: using a config file outside the default location

Spring Boot supports the **logging.config** property to specify a logging configuration resource.

Example:

~~~bash
java -jar app.jar --logging.config=classpath:logging/custom-logback.xml
~~~

With file:

~~~text
src/main/resources/logging/custom-logback.xml
~~~

Or a file outside the JAR:

~~~bash
java -jar app.jar --logging.config=file:/etc/my-app/logback-spring.xml
~~~

When the file lives outside the artifact, the process needs read permission and startup must receive the exact path configuration.

### 13.1. Do not read logging files manually via @Bean too late

Logging initializes early; a `@Configuration` class creating a bean after context refresh is not the proper way to choose the initial Logback file.

To make bootstrap use a configuration file, use the conventional name `logback-spring.xml` or pass **logging.config** through an appropriate early configuration source.

### 13.2. Check URLs, paths, and classpath

Common mistakes:

- Specifying `classpath:` yet the file was not packaged into the JAR.
- Using a relative path that mismatches the working directory.
- Mounting the file under a different directory than `logging.config`.
- Container lacking file read permissions.
- Malformed XML syntax.
- Active backend is actually Log4j2 while the file configures Logback.

Do not point `logging.config` to a non-existent resource expecting Spring Boot to ignore every error silently. Depending on the logging system and path, the application may fail to start or fall into unintended behavior.

## 14. When does Spring Boot initialize logging?

The logging system is prepared by Spring Boot **early in the startup lifecycle**, before the ApplicationContext is completely ready. This is necessary because configuration reading errors or bean creation errors themselves must be logged.

A conceptual diagram:

~~~text
SpringApplication.run(...)
           │
           ▼
Start logging and prepare Environment
           │
           ▼
Load Config Data / apply appropriate logging config
           │
           ▼
Create and refresh ApplicationContext
           │
           ▼
Instantiate beans, run runners, handle requests
           │
           ▼
Application shutdown / logging system releases resources
~~~

Boot has finer-grained event milestones, and some logging initialization steps can execute again once the Environment has full information. The point to remember is that **logging does not wait for all application beans to be created**.

### 14.1. Why does @PropertySource sometimes fail to control logging?

Example:

~~~java
@Configuration
@PropertySource("classpath:custom-logging.properties")
public class AdditionalPropertyConfiguration {
}
~~~

`@Configuration` classes are typically processed during ApplicationContext construction. If `custom-logging.properties` sets keys like `logging.level.root` or `logging.config`, they may be added to the Environment **too late** for initial logging configuration selection.

For keys controlling startup logging, use early-loaded configuration sources such as:

- `application.yml` or appropriate Config Data.
- Environment variables.
- JVM system properties.
- Command-line arguments.

Do not treat `@PropertySource` as fully equivalent to those sources for logging initialization.

### 14.2. Do not rely on Spring beans to build Logback appenders at bootstrap

A Logback appender instantiated from XML config is not necessarily a Spring bean and does not automatically participate in ApplicationContext dependency injection. Do not assume you can use `@Autowired` inside an Appender class instantiated by Logback.

If a custom appender needs complex dependencies, design explicit integration between Logback's lifecycle and Spring's lifecycle, paying close attention to initialization order, async queues, and resource destruction.

Usually, built-in appenders and external logging pipelines are much easier to maintain than custom appenders coupled to business services.

### 14.3. Disable Logback scan when using Spring extensions

Native Logback supports automatic config rescanning:

~~~xml
<configuration scan="true" scanPeriod="30 seconds">
    <!-- Native Logback configuration. -->
</configuration>
~~~

However, **Spring Boot extensions such as `springProfile`/`springProperty` are incompatible with Logback's native configuration scanning**. When Logback reloads on its own, it may fail to interpret those tags and emit errors similar to:

~~~text
no applicable action for [springProperty]
no applicable action for [springProfile]
~~~

When using Spring Boot extensions, do not enable `scan="true"` as a simple hot-reload trick. Logging configuration changes should go through a controlled deploy/restart workflow or a properly designed and tested reload mechanism.

## 15. Logging exceptions properly

Logging is not just writing a message string. With exceptions, the stack trace and root cause are critical for investigation.

Example:

~~~java
try {
    repository.save(order);
} catch (DataAccessException ex) {
    log.error("Cannot save order {}", order.getId(), ex);
    throw ex;
}
~~~

Passing the exception as the final parameter gives the logging backend the chance to output the stack trace.

### 15.1. Avoid logging only ex.getMessage()

Example to avoid:

~~~java
log.error("Cannot save order: {}", ex.getMessage());
~~~

This can lose the stack trace and cause chain. Some exception messages also contain system internals or sensitive data.

Prefer:

~~~java
log.error("Cannot save order {}", orderId, ex);
~~~

and govern where logs are stored per security policy.

### 15.2. Avoid logging the same exception at every layer

Example:

~~~text
Repository: ERROR Save failed
Service:    ERROR Save failed
Controller: ERROR Save failed
Global:     ERROR Request failed
~~~

If each layer catches the exception, logs ERROR, and rethrows it, a single failure produces four duplicate stack traces.

A practical convention:

- Lower layers log when adding genuinely useful new context or when they **handle** the error locally.
- When simply rethrowing, re-logging is often unnecessary.
- Boundary layers such as global exception handlers can log the error once with the request ID and safe context.

Exact rules depend on architecture, yet avoid "log then throw" in every method.

### 15.3. Log WARN or ERROR?

There is no rigid rule for all applications:

- **DEBUG**: diagnostic details, safe to turn off in production.
- **INFO**: important business/operational milestones under normal conditions.
- **WARN**: abnormal situation where the system can continue or has fallen back.
- **ERROR**: failed operation needing attention, usually affecting functionality or operational health.

Do not log ERROR for every transient retry if the retry ultimately succeeds, because that creates alert noise and obscures real incidents. You can log WARN/DEBUG on intermediate attempts and ERROR on the final failure outcome, per system policy.

## 16. Correlation IDs and MDC in log patterns

When a request passes through controller, service, and repository, multiple log lines appear on the same or different threads. Without a correlation ID, it is hard to tell which lines belong to the same request.

SLF4J supports **MDC** (Mapped Diagnostic Context) to attach key-values to the logging context. Logback patterns can read them via **%X{key}**.

Example pattern:

~~~xml
<pattern>%d{HH:mm:ss.SSS} %-5level [requestId=%X{requestId:-none}] %logger{36} - %msg%n</pattern>
~~~

Here:

- **%X{requestId}** retrieves the MDC value under key `requestId`.
- **:-none** is the fallback value in the converter's pattern syntax.

A log line may look like:

~~~text
09:34:10.327 INFO  [requestId=41dd5a] c.e.OrderService - Creating order ORD-17
~~~

### 16.1. Filter attaching request ID with Spring MVC

Example using Spring Boot 3 and Jakarta Servlet API:

~~~java
package com.example.demo.logging;

import java.io.IOException;
import java.util.UUID;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();

        try (MDC.MDCCloseable ignored =
                     MDC.putCloseable("requestId", requestId)) {

            response.setHeader("X-Request-Id", requestId);
            chain.doFilter(request, response);
        }
    }
}
~~~

This pattern generates a new ID per request, puts it into MDC for the filter scope, and cleans up the key on exit.

In distributed systems, a request may already have a trace ID from tracing infrastructure. In that case, generating a separate ID is not strictly necessary. Use a unified correlation/tracing mechanism and validate untrusted header values before logging them.

### 16.2. Why must MDC be cleaned up?

MDC in traditional logging setups is tied to threads. Servlet threads are reused to handle other requests.

If code does:

~~~java
MDC.put("requestId", requestId);
// Process request without remove/clear.
~~~

then the next request on the same thread may see an old `requestId`, corrupting traceability.

Using `try-finally` or `MDC.putCloseable` bounds the lifetime of the set key.

### 16.3. MDC and async/reactive contexts

MDC does not automatically propagate cleanly across every executor, `CompletableFuture`, or Reactor pipeline. When switching threads, logging context can be lost or contaminated without proper propagation/cleanup.

In modern Spring Boot, Micrometer Tracing/Observation can inject `traceId`/`spanId` into logs depending on stack and configuration. Prefer framework-supported propagation mechanisms instead of manually copying MDC across threads without cleanup.

### 16.4. MDC is not a place to store secrets

Do not place access tokens, passwords, card numbers, or personal payloads into MDC just to have them printed on every log line. An MDC value can be written by many loggers/appenders to places you do not control.

Appropriate keys are typically:

- `requestId`.
- `correlationId`.
- `traceId`/`spanId` managed by tracing infrastructure.
- Non-sensitive business operation IDs.

## 17. AsyncAppender and asynchronous logging

An appender writing to disk or network can take time. Logback supports **AsyncAppender** to enqueue logging events before writing through a target appender.

Example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ASYNC_CONSOLE"
              class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>2048</queueSize>
        <appender-ref ref="CONSOLE"/>
    </appender>

    <root level="INFO">
        <appender-ref ref="ASYNC_CONSOLE"/>
    </root>

</configuration>
~~~

When a logger emits an event, `AsyncAppender` enqueues it for a worker thread to pass to `CONSOLE`. This reduces part of the write latency on business threads, though it does not make logging completely "free".

### 17.1. Trade-offs when using AsyncAppender

- The queue consumes memory.
- When the application logs faster than the output destination drains, the queue can fill up.
- Discarding/blocking policies affect log loss vs latency.
- During abrupt shutdowns, events still in the queue may not be written out.
- Certain caller data must be captured before the emitting thread moves on.

Do not enable async assuming every ERROR is guaranteed to persist durably. Inspect queue policies, discarding thresholds, and flush/stop timeouts of the active appender.

### 17.2. Do not use AsyncAppender as a business message queue

Logs are not a guaranteed delivery system for business events. If the business requires a "payment completed" event never to be lost, use an appropriate transaction/outbox/message broker. An INFO log line, even via AsyncAppender, does not replace a durable event store or audit ledger.

### 17.3. Beware of slow output targets

If `ConsoleAppender` writes to a stdout pipe experiencing backpressure or an unresponsive remote appender, logging can hurt overall performance.

Monitor log volume, queue depth (if instrumented), collector throughput, and policies when output destinations become unavailable.

## 18. Structured logging and XML patterns

Text patterns are simple and easy for humans to read. However, in systems with many replicas and centralized log querying, **structured logging** (e.g., one JSON object per line) makes querying by field easy.

Example of an event in structured form:

~~~json
{
  "timestamp": "2026-11-13T09:34:10.327Z",
  "level": "INFO",
  "logger": "com.example.orders.OrderService",
  "message": "Creating order ORD-17",
  "service": "order-api",
  "requestId": "41dd5a"
}
~~~

This is a data illustration, not a guarantee that all Boot versions ship with this exact JSON schema out of the box.

There are multiple ways to implement structured logging:

- Structured logging features supported by the Spring Boot version in use.
- A JSON encoder/layout from a Logback-compatible library.
- Custom logging integration managed by your organization's platform.

When using **logback-spring.xml**, defining a custom encoder can replace the default encoder/pattern. Ensure important fields such as timestamp, severity, logger, thread, and trace/correlation IDs are still recorded.

### 18.1. Choose text or JSON based on your log collection system

| Output | Advantages | Things to watch out for |
|---|---|---|
| Text pattern | Easy to read in terminals, minimal config. | Analytics tools must parse strings to extract fields. |
| JSON structured | Convenient field-based querying, ideal for log pipelines. | Requires encoder, schema, and escaping/field privacy handling. |

If your collection system already parses text in a standard format, you do not have to switch to JSON unnecessarily. What matters is a consistent format analyzable by your actual observability tooling.

### 18.2. Do not construct JSON manually with String concatenation

Avoid:

~~~java
log.info("{\"user\":\"" + userInput + "\"}");
~~~

Input containing quotes, newlines, or special characters can produce invalid JSON. Untrusted input can also cause log injection or make one event look like multiple events.

Use an appropriate structured logging encoder or library-supported structured arguments API while restricting which fields may be logged.

## 19. Switching from Logback to Log4j2

A Spring Boot application can use Log4j2 instead of Logback. In that case, **logback-spring.xml is no longer the primary configuration file for the logging backend**.

With Gradle, an example of dependency management for a starter:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-logging'
    }

    implementation 'org.springframework.boot:spring-boot-starter-log4j2'
}
~~~

This snippet illustrates excluding the default logging starter and adding Log4j2. In a project with multiple starters, inspect the actual dependency graph to ensure no conflicting bindings/providers or unintended logging implementations remain. Dependency versions are usually managed by Spring Boot dependency management.

### 19.1. log4j2-spring.xml file

Corresponding location:

~~~text
src/main/resources/log4j2-spring.xml
~~~

Minimal Log4j2 example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">

    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout
                    pattern="%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.orders" level="debug"/>

        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>

</Configuration>
~~~

This is **Log4j2 syntax**, not Logback XML. The `Configuration`, `Appenders`, `Loggers`, `Root`, and `AppenderRef` tags differ from Logback's structure.

### 19.2. Keep SLF4J in business code

If services write:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

most code needs no edits when switching logging backends, provided runtime has the right SLF4J provider/bridges and consistent dependencies.

Do not scatter Logback-specific APIs across every business class just because the project currently uses Logback. Keep implementation-specific APIs confined to configuration/infrastructure code that truly needs them.

### 19.3. Log4j2 Spring Boot extensions

Spring Boot supports appropriate configuration integration for Log4j2, including using **log4j2-spring.xml** so Boot can participate in setup. However, **do not copy Logback's `springProfile`/`springProperty` tags verbatim** into Log4j2.

Each backend has its own configuration model and extensions. When switching backends:

- Switch XML syntax to match the logging system.
- Verify Spring profile/environment lookups via Boot-supported Log4j2 mechanisms.
- Check provider and bridge dependencies.
- Verify console/file output, rotation, and JSON encoders if used.
- Check patterns and throwable output because converters can differ.

### 19.4. Java Util Logging and bridges

Some libraries use `java.util.logging` (JUL), Commons Logging, or other APIs. Spring Boot starters normally include appropriate bridges to route logs to the primary backend.

Avoid configuring multiple incompatible backends/bridges simultaneously or creating bridge loops. When logs disappear or duplicate, inspect the dependency tree and which logging implementations are actually loaded.

## 20. Appender filters: not every output needs the same level

Suppose an application wants:

- Console logging INFO and above.
- A warnings file logging only WARN and ERROR.

You can use Logback's **ThresholdFilter** per appender:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="WARN_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/warnings.log</file>

        <filter
                class="ch.qos.logback.classic.filter.ThresholdFilter">
            <level>WARN</level>
        </filter>

        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n%ex</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/warnings.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="WARN_FILE"/>
    </root>

</configuration>
~~~

With this configuration:

- INFO can appear on the console.
- WARN and ERROR can appear in both console and `warnings.log`.
- DEBUG is usually dropped at root INFO and never reaches any appender.

### 20.1. Levels and filters are two checking layers

An appender filter **cannot recover** an event already blocked earlier by a logger.

Example:

~~~text
Logger effective level = WARN
             │
      DEBUG event
             │
             ▼
      Dropped early
             │
             X
Never reaches ConsoleAppender even if its filter permits DEBUG
~~~

When wanting to save DEBUG for a dedicated package:

~~~xml
<logger name="com.example.orders" level="DEBUG"/>
~~~

also verify that the appender route and filters permit DEBUG.

### 20.2. Using filters to restrict information

Filters can reduce the volume of events stored in a destination, yet they are not a complete substitute for data security and classification. Do not assume a regex filter catches every secret or PII in all log messages.

For sensitive data, the best practice is **never generating dangerous log content in code** or applying masking/redaction designed and tested at the right layer.

## 21. Changing log levels while the application is running

In many systems, you do not want to restart a production service just to turn on DEBUG temporarily for a package.

Spring Boot Actuator can provide the **loggers** endpoint to observe and change log levels at runtime, depending on logging system support.

Example endpoints:

~~~text
GET /actuator/loggers
GET /actuator/loggers/com.example.orders
POST /actuator/loggers/com.example.orders
~~~

Request body when setting DEBUG:

~~~json
{
  "configuredLevel": "DEBUG"
}
~~~

To return a logger to having no explicitly configured level, Actuator supports setting `configuredLevel` to `null` in the corresponding endpoint mechanism:

~~~json
{
  "configuredLevel": null
}
~~~

### 21.1. Expose only with access control

Example exposure config:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,loggers
~~~

This is **not a complete security configuration**. An endpoint that changes log levels can expose debug data, increase system load, and generate large log volumes.

Restrict access with appropriate security configuration, network policies, and operational processes. Never expose log-level controls to unauthorized users.

### 21.2. Do runtime changes persist across restarts?

Normally, a log-level change via Actuator affects the logging system of **the current process**. It does not edit `application.yml` or `logback-spring.xml` in the repository.

When the instance restarts, the system initializes logging from the deployed configuration. Therefore:

- Use Actuator for controlled short-term diagnostics.
- Use configuration management/CI/CD for permanent changes.
- Record who changed the level and when it was restored.

In a multi-replica cluster, changing a logger level on one instance does not automatically update all other instances. Operational tooling must target the right scope.

### 21.3. Do not leave DEBUG on in production too long

DEBUG/TRACE can:

- Increase formatting and log-writing overhead.
- Increase log pipeline traffic.
- Exhaust disk space or retention quotas faster.
- Emit data fields the system was not designed to process in production.

When used for investigation, specify a clear time window, package, and exit condition.

## 22. Testing logging with OutputCaptureExtension

Spring Boot provides a test utility to capture console output, commonly via **OutputCaptureExtension** in `spring-boot-test`.

JUnit 5 example:

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class OrderLoggingTests {

    private static final Logger log =
            LoggerFactory.getLogger(OrderLoggingTests.class);

    @Test
    void writesExpectedMessage(CapturedOutput output) {
        log.info("Order {} accepted", "ORD-42");

        assertThat(output.getAll())
                .contains("Order ORD-42 accepted");
    }
}
~~~

This test verifies that the message is written to output captured by the extension, provided the logger has an appropriate level and the logging backend uses a console appender.

### 22.1. Tests do not need to match the entire log line

Timestamps, thread names, PIDs, and patterns can vary across test runs. Avoid locking unit tests to full log lines fragiley when the goal is simply verifying a required message.

If your goal is specifically testing the pattern or correlation ID, write a tighter test against a controlled test configuration.

### 22.2. OutputCaptureExtension does not prove file rotation

Console output tests do not verify that:

- `RollingFileAppender` wrote to the right file.
- Archives rotate by size/date.
- The filesystem has write permissions.
- `totalSizeCap` actually caps archives.
- `AsyncAppender` drained its queue.

Those requirements need integration tests or separate operational verification with temporary directories and matching logging configs.

Within simple unit tests, avoid adding complex test suites just to prove `log.info` can print a String.

### 22.3. @SpringBootTest and profiles for logging

If logging configuration depends on Spring profiles, you can use:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class LoggingConfigurationIntegrationTests {
    // Test logging behavior under the test profile.
}
~~~

However, test contexts and the logging system can have different lifecycles in some scenarios, especially when a test suite runs multiple contexts and the logging system is JVM-wide. Do not assume global logging changes in one test are strictly isolated from other tests.

When testing specific `logback-spring.xml` branches, scope tests cleanly and avoid modifying global logger levels without restoring them.

## 23. Checking logger levels from code and Actuator

In application code, with SLF4J:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Complex diagnostic value: {}",
            buildExpensiveDiagnostic());
}
~~~

Why check `isDebugEnabled` here? Because `buildExpensiveDiagnostic()` can consume CPU even when DEBUG is blocked if evaluated before passing into the log call.

For already-available values, wrapping every `log.debug` in an `if` is usually unnecessary:

~~~java
log.debug("Order {} has status {}", orderId, status);
~~~

SLF4J placeholders avoid manual message string concatenation in standard cases.

### 23.1. When is Logback's own API needed?

If an application must inspect appender configuration or change levels via the Logback API, it may need to downcast to `ch.qos.logback.classic.Logger`. However, that behavior is implementation-dependent.

In business code, prefer SLF4J to retain the ability to switch logging backends. For operational changes, prefer `logging.level` or Actuator loggers when they meet requirements.

### 23.2. Level is not output format

Having:

~~~properties
logging.level.com.example.orders=DEBUG
~~~

does not mean logs will gain `requestId`, JSON fields, or exception stacks. Those fields are decided by event code, MDC/tracing, and encoders/patterns.

Conversely, a very detailed pattern still will not display DEBUG if the logger level blocks it.

## 24. Logging and data security

Logging is helpful for operations, yet also a common place where sensitive data is unintentionally stored.

Do not directly log:

- Passwords, tokens, API keys, or session cookies.
- Full `Authorization` headers.
- Payment card data.
- Payloads containing sensitive personal information.
- Secrets read from Environment or configuration properties.
- JDBC connection strings containing credentials.
- Sensitive identifiers unnecessary for diagnostics.

Example to avoid:

~~~java
log.info("Login request: {}", loginRequest);
~~~

If `LoginRequest.toString()` prints the password, the secret enters logs.

Log approved fields instead:

~~~java
log.info("Login attempt accepted for requestId={}",
        requestId);
~~~

Or log safe outcomes and status codes instead of full request/response bodies.

### 24.1. Do not leave TRACE enabled system-wide indefinitely

Verbose logging levels can cause frameworks or HTTP clients to record extra metadata. Some libraries support wire logging, which may include request headers or bodies depending on configuration.

Therefore, do not set:

~~~yaml
logging:
  level:
    root: TRACE
~~~

in production as the "easiest way to find a bug". If needed, enable only the exact logger for a limited time, check for data leakage, and plan how to turn it off.

### 24.2. Log injection and untrusted data

User input can contain newlines or control characters. If printed directly into text logs, a single message can split across multiple lines appearing like separate events.

Example:

~~~java
log.info("Display name: {}", untrustedDisplayName);
~~~

In systems with sensitive log ingestion/parsers, use proper structured logging encoders or escape/normalize input per pipeline rules. Do not treat every user-submitted string as safe metadata.

### 24.3. Access control, retention, and rotation

A production logging configuration should establish:

- Who can read logs and for what purpose?
- Are logs stored via console pipeline or files?
- How long are logs retained?
- Is encryption applied in transit/at rest?
- Is audit logging required for log access?
- Which policy governs deleting or masking data?

`logback-spring.xml` can configure file rotation, yet **retention policies of centralized log systems** are a broader infrastructure/operations responsibility. Do not rely solely on `maxHistory` in an XML file to conclude all data has been purged everywhere.

## 25. Logging in production: practical guidelines

1. **Prefer one clear log collection path.** In containers, typically console → collector → storage/analysis.
2. **Use sensible levels.** INFO for major operational milestones; WARN/ERROR for noteworthy conditions; controlled DEBUG/TRACE.
3. **Name loggers by class/package.** Easy to adjust per component via `logging.level`.
4. **Attach correlation/trace IDs when needed.** Avoid manual tracing by timestamp alone.
5. **Bound storage and retention.** If writing files, configure rotation; if using collectors, manage retention/quotas.
6. **Keep secrets out of logs.** Do not log raw untrusted payloads or sensitive configuration.
7. **Avoid duplicate logs.** Check additivity and attached appenders.
8. **Monitor logging cost.** Log volume, blocking output, and async queues all affect performance.
9. **Keep configuration consistent across replicas.** One pod on DEBUG and another on INFO makes investigation inconsistent.
10. **Separate responsibilities clearly.** Code emits log events; XML/Boot properties determine how they are written; infrastructure handles collection and long-term storage.

## 26. Troubleshooting when logback-spring.xml has no effect

When an XML config is added yet the application still logs with the old pattern, inspect layer by layer:

### Step 1: Confirm the runtime logging system

Is the Spring Boot application actually using Logback? Was it switched to Log4j2 by another starter or dependency exclusions?

You cannot control Log4j2 using a Logback XML file.

### Step 2: Check whether the file is on the classpath

Correct location:

~~~text
src/main/resources/logback-spring.xml
~~~

After building, the resource must exist inside the JAR or classpath. The filename must be exact; a file sitting only in `src/test/resources` will not necessarily be packaged into the runtime artifact.

### Step 3: Check whether logging.config overrides it

If:

~~~text
logging.config=classpath:logging/custom.xml
~~~

is set in the process, Boot may use that location instead of the default file. Check command line, environment, and active Config Data.

### Step 4: Verify valid XML

Common mistakes:

- Missing closing tags.
- Non-existent appender/encoder class names.
- Missing corresponding `appender-ref`.
- Using Log4j2 XML syntax in Logback.
- Unescaped **&** characters inside XML attributes.
- Defining two appenders with the same name and conflicting config.

Syntactically valid XML is not guaranteed to be valid Logback configuration; both structure and component types must be right.

### Step 5: Verify Spring extensions are processed

If using `springProperty` or `springProfile`:

- Is the file loaded by Boot through the supported path?
- Is there a `logback.xml` being loaded too early by Logback itself?
- Is `scan="true"` causing reloads via the native parser?
- Does the active profile actually match the expression?
- Was the property source in the Environment early enough?

### Step 6: Inspect logger effective levels

What is the name of the logger writing the message? Does its effective level allow DEBUG or INFO? Is a `logging.level` property or runtime Actuator override active?

### Step 7: Inspect appender routes

Does root/logger have an appender attached? Is `additivity=false` set without an `appender-ref`? Are filters dropping events?

### Step 8: Inspect output destinations

Is the console being collected? Does the file path match the working directory? Does the process have permission to create directories/files? Does the volume still have free space?

### Step 9: Inspect rollover and lifecycle

Was the file rotated to a different name? Are events sitting unflushed in an async queue? Was the process killed abruptly before flushing output?

Diagnosing in this order is usually far more effective than immediately raising root level to TRACE.

## 27. Common errors and resolutions

### 27.1. Using logback.xml with springProfile

**Symptom:** startup throws parser errors or Spring profile branches do not take effect.

**Cause:** native Logback loading processes `logback.xml` before or independently of Spring Boot extensions.

**Resolution:** prefer **logback-spring.xml** when using `springProfile` or `springProperty`. Do not enable native configuration scanning on files containing Spring extensions.

### 27.2. Setting logging.level yet DEBUG does not appear

**Symptom:** `logging.level.com.example=DEBUG` is set, yet expected `log.debug` lines are missing.

**Possible causes:** logger name mismatches package, property overridden, missing appender route, `additivity=false`, appender filter blocking, or code never reaches the log branch.

**Resolution:** inspect effective level via Actuator loggers, verify actual logger name, and check appender routing.

### 27.3. One event appears twice

**Symptom:** two lines with identical timestamps/messages appear in the same output.

**Cause:** child logger has its own appender while `additivity=true` and root also attaches that appender; or multiple log bridges or collectors read twice.

**Resolution:** inspect logger hierarchy, `appender-ref`, additivity, and the log collection pipeline. Use `additivity=false` only when the logger has an explicit output route.

### 27.4. Logs disappear after adding additivity=false

**Symptom:** a package previously had logs, then produced zero lines after configuring a dedicated logger.

**Cause:** the logger was blocked from propagating to root yet has no appender of its own.

**Resolution:** attach an appropriate `appender-ref`, or remove `additivity=false` if you only needed to change the level.

### 27.5. Log file is not created

**Symptom:** console has logs, file does not appear.

**Cause:** `FileAppender` not attached to root/logger, wrong path, unwritable directory, full disk, or appender skipped because profile condition did not match.

**Resolution:** check `appender-ref`, working directory, permissions, profiles, Logback status, and filesystem.

### 27.6. Log file sits in an unexpected directory

**Symptom:** looking for logs in the project folder while the file landed elsewhere.

**Cause:** relative paths like `logs/application.log` resolve relative to the process's working directory.

**Resolution:** use explicit locations, deployment-supplied config variables, and verify resolved paths at startup.

### 27.7. logback-spring.xml is not packaged

**Symptom:** IDE uses the custom pattern, executable JAR uses a different configuration.

**Cause:** file sits in the wrong folder, e.g., `src/test/resources` instead of `src/main/resources`, or build excludes the resource from the artifact.

**Resolution:** inspect the runtime artifact's classpath and exact filename.

### 27.8. springProperty ignores values from @PropertySource

**Symptom:** the property is readable after context initializes, yet logging XML uses `defaultValue`.

**Cause:** `@PropertySource` on a configuration class is added too late relative to logging initialization.

**Resolution:** place logging properties in early config sources such as Config Data, environment variables, or command line.

### 27.9. Log file reloads yet Spring tags error out

**Symptom:** app starts cleanly yet later logs **no applicable action for springProperty/springProfile**.

**Cause:** native Logback scan reloaded configuration bypassing Spring Boot extensions.

**Resolution:** disable `scan` and manage configuration changes through Boot-supported mechanisms and operational processes.

### 27.10. Log file exists yet rotation does not work

**Symptom:** one file grows forever; no archives appear or policy differs from expectation.

**Cause:** using `FileAppender` instead of `RollingFileAppender`, misconfigured `RollingPolicy`, bad `fileNamePattern`, or size/date thresholds not met yet.

**Resolution:** verify appender type, policy, `fileNamePattern`, `maxFileSize`/`maxHistory`, and Logback status. Do not treat `maxHistory` as a size limit for the current file.

### 27.11. Editing logback-spring.xml inside JAR does not change running process

**Symptom:** source or image file changed yet the running JVM still uses the old config.

**Cause:** logging system initialized at startup; editing source files does not auto-update an already-running process.

**Resolution:** build/redeploy or perform a controlled restart; do not rely on native scan with Spring extensions.

### 27.12. INFO/ERROR logged yet stack trace is missing

**Symptom:** only error message visible, missing root cause or line numbers.

**Cause:** logging only `ex.getMessage()`, omitting `Throwable`, or custom encoder/filter drops exception data.

**Resolution:** pass `Throwable` to the logger at the appropriate position and verify throwable conversion in the encoder.

### 27.13. Excessive logging slows down the application

**Symptom:** throughput drops when DEBUG or TRACE is enabled, CPU/disk/network rise.

**Cause:** high event volume, expensive message formatting, synchronous appenders, slow collector, or full async queue.

**Resolution:** narrow level/scope, optimize log content, review appenders, and design an appropriate pipeline.

### 27.14. Wrong Request IDs across requests

**Symptom:** two unrelated requests share the same MDC `requestId`.

**Cause:** failing to remove MDC before thread reuse, or improper context propagation across executors.

**Resolution:** use `try-finally`/`MDC.putCloseable` and official trace propagation mechanisms for your stack.

### 27.15. JSON logs exist yet collector parses them wrongly

**Symptom:** centralized log system cannot read fields or splits one event into multiple records.

**Cause:** manual String concatenation for JSON, missing escaping, or multiline stack traces unhandled by encoder schema.

**Resolution:** use a proper encoder, standardize schema, and configure ingestion accordingly.

### 27.16. Multiple providers or backends found on classpath

**Symptom:** warnings about multiple SLF4J providers/bindings, loggers ignore expected config, or logs duplicate.

**Cause:** dependency graph pulls in multiple conflicting logging implementations and bridges simultaneously.

**Resolution:** select one primary backend, exclude unneeded dependencies, and verify the runtime classpath after building.

## 28. Complete example: order-api with console logging and local-only file output

Suppose a Spring Boot application named **order-api** has these requirements:

- One artifact runs in both local and production.
- Both environments have console logging.
- Locally: DEBUG logs for business code and rolling file output.
- In other profiles: console INFO, without actively creating local files.
- Log lines show service name and support MDC request IDs.
- Local log directory is configurable via Environment.

### 28.1. application.yml

~~~yaml
spring:
  application:
    name: order-api

app:
  logging:
    directory: logs

logging:
  level:
    root: INFO
~~~

Deployment-specific properties can be added externally or in profile-specific files. `app.logging.directory` is a custom property read by `logback-spring.xml` via `springProperty`.

### 28.2. logback-spring.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>

    <springProperty scope="context"
                    name="serviceName"
                    source="spring.application.name"
                    defaultValue="unknown-service"/>

    <springProperty scope="context"
                    name="logDir"
                    source="app.logging.directory"
                    defaultValue="logs"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <charset>UTF-8</charset>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [${serviceName}] [requestId=%X{requestId:-none}] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <springProfile name="local">

        <appender name="LOCAL_FILE"
                  class="ch.qos.logback.core.rolling.RollingFileAppender">
            <file>${logDir}/order-api.log</file>

            <encoder>
                <charset>UTF-8</charset>
                <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [${serviceName}] %logger{50} - %msg%n%ex</pattern>
            </encoder>

            <rollingPolicy
                    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
                <fileNamePattern>${logDir}/order-api.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
                <maxFileSize>10MB</maxFileSize>
                <maxHistory>7</maxHistory>
                <totalSizeCap>500MB</totalSizeCap>
            </rollingPolicy>
        </appender>

        <logger name="com.example.orders" level="DEBUG"/>

        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
            <appender-ref ref="LOCAL_FILE"/>
        </root>
    </springProfile>

    <springProfile name="!local">
        <root level="INFO">
            <appender-ref ref="CONSOLE"/>
        </root>
    </springProfile>

</configuration>
~~~

Implementation thinking:

1. `springProperty` pulls `serviceName` and `logDir` from the Environment.
2. `ConsoleAppender` is always declared for output.
3. Only the `local` branch declares and attaches `LOCAL_FILE`.
4. `com.example.orders` is raised to DEBUG locally, while other loggers retain appropriate inherited levels.
5. Non-local branches use console INFO.
6. No child logger attaches `CONSOLE` redundantly alongside root, avoiding duplicate events from additivity.

### 28.3. Running locally

~~~bash
java -jar order-api.jar --spring.profiles.active=local
~~~

Expected behavior by design:

- Root INFO logs go to console and `LOCAL_FILE`.
- Loggers in `com.example.orders` are permitted to emit DEBUG.
- The local log file rolls according to the declared policy.

This assumes the process has permission to create/write the `logs` directory and no other overrides alter the logging system.

### 28.4. Running in production

~~~bash
java -jar order-api.jar --spring.profiles.active=prod
~~~

When only `prod` is active, the **!local** branch applies:

- Root INFO attaches `CONSOLE`.
- `LOCAL_FILE` is not declared through the `local` branch.
- Logs are sent to the console for the deployment platform to collect.

In real systems, verify the right profile is active, the backend is Logback, and final logger levels are not overridden by other runtime properties.

### 28.5. Running with a temporary log-level increase

~~~bash
java -jar order-api.jar --spring.profiles.active=prod --logging.level.com.example.orders=DEBUG
~~~

This command illustrates using properties to enable DEBUG for a package on a single run. When no other Logback filters block it, debug events can be sent to `CONSOLE`.

If a system policy forbids DEBUG in production, enforce that in deployment and security processes; a simple XML file alone cannot block every configuration override.

## 29. Choosing a logging configuration approach by need

| Need | Commonly suitable approach |
|---|---|
| Change root or package log level | `logging.level` in `application.yml` or CLI. |
| Change default console pattern | `logging.pattern.console` when supported by current setup. |
| Basic log file output | `logging.file.name`/`path` if default mechanism suffices. |
| Complex file rotation, multiple appenders | `logback-spring.xml` with `RollingFileAppender`/filters. |
| Conditional config by Spring profile | `springProfile` in `logback-spring.xml`. |
| Read app name or path from Environment | `springProperty` in `logback-spring.xml`. |
| Temporarily enable DEBUG at runtime | Secured Actuator loggers, if supported. |
| Use Log4j2 | Choose matching starter/backend and `log4j2-spring.xml`. |
| Query logs by fields across replicas | Structured logging/encoder aligned with collector. |
| Trace a request across multiple services | Micrometer Tracing/MDC with proper context propagation. |
| Audit events that must never be lost | Durable audit/outbox system, not merely a regular logger. |

No single XML template is best for every application. The choice depends on the logging backend, deployment model, observability infrastructure, and security/retention requirements.

## 30. Common misconceptions

**"Spring Boot always uses Logback."**  
No. Logback is the common default via the logging starter, yet applications can choose another backend.

**"SLF4J and Logback are the same library."**  
No. SLF4J is an API/facade; Logback is an implementation.

**"Having logback-spring.xml means all logging.level properties are ignored."**  
Not necessarily. Spring Boot still applies log levels from the Environment depending on initialization. Best practice is avoiding conflicting configs and checking effective levels.

**"logback.xml and logback-spring.xml are completely equivalent."**  
No. `logback-spring.xml` supports Spring Boot extensions; `logback.xml` can be loaded early by Logback's native parser.

**"springProfile in XML activates a profile."**  
No. It only applies a branch when the profile already matches.

**"springProperty can inject any Spring bean."**  
No. It reads properties from the Spring Environment during logging initialization, not dependency injection like `@Autowired`.

**"Attaching two appenders to root always causes duplicate logs."**  
No. Root writing events to two destinations is intentional behavior. Duplicate logs in the same destination usually stem from an appender invoked along multiple paths or duplicate collection pipelines.

**"Disabling additivity is always best."**  
No. If a logger lacks its own appender, events may no longer reach any output.

**"FileAppender rotates automatically."**  
No. Rolling requires an appropriate appender/policy.

**"maxHistory=14 guarantees exactly 14 files."**  
No. It manages historical periods per policy; a single day can produce multiple archives via size-based rollover.

**"AsyncAppender guarantees zero log loss."**  
No. Queue overflow, discard policies, or abrupt shutdowns can still drop events.

**"Changing log levels via Actuator edits config files in Git."**  
No. Runtime changes usually apply only to the current process.

**"Logback configuration is a Spring bean so you can @Autowired inside XML."**  
No. The logging system initializes early, and Logback components do not participate in IoC like application beans.

**"Setting scan=true always auto-reloads springProfile."**  
No. Native Logback scanning is incompatible with Spring Boot Logback extensions.

**"Having TRACE always makes diagnostics easier."**  
No. System-wide TRACE causes noise, increases load, and risks data exposure.

**"Text logs are guaranteed-retention audit records."**  
No. Auditing with zero-loss requirements demands a more durable design.

## Core takeaways

In a Spring Boot application using Logback, **logback-spring.xml** is the right configuration file when you need deep control over appenders, encoders, patterns, logger hierarchies, rolling policies, and Spring Environment-driven setup. **springProfile** selects config branches based on active profiles; **springProperty** reads values from the Environment. These two extensions are key reasons to prefer `logback-spring.xml` over `logback.xml` in Boot applications.

When you only need to adjust log levels, start with **logging.level**. When you need multiple destinations, rotation, filters, or specialized formats, use XML matching your **actual logging system**. Logback XML cannot substitute for Log4j2 XML; business code should use SLF4J to minimize backend coupling.

Finally, proper logging is more than "printing a line". Verify effective logger levels, appender routing/additivity, destinations, charsets, retention, correlation IDs, and permitted data. In production systems, protect access to logs and Actuator, control DEBUG/TRACE usage, and align the logging pipeline with how the application is deployed.

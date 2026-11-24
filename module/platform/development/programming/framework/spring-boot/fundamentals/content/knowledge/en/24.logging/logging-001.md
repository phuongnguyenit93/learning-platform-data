# Logging Facade, SLF4J, and Implementation Libraries

When developing a Spring Boot application, developers often write a very simple log line:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);

log.info("Order {} was created", orderId);
~~~

The code only knows about `Logger` and `LoggerFactory` from **SLF4J**, yet the actual message is formatted, filtered by level, and written to the console or a file by a **logging implementation library** such as **Logback** or **Log4j 2**. This separation is intentional by design: source code does not need to depend directly on a specific logging mechanism.

In Spring Boot, logging is a very early infrastructure component of the startup process. The application needs to log even when the ApplicationContext has not been created yet, when configuration fails, and during shutdown. Spring Boot therefore prepares defaults that allow code to use logging immediately, while also providing configuration points to change levels, formats, and the backend.

This lesson explains the entire flow **logging facade → SLF4J API → provider/binding → logging backend → output**, the differences between SLF4J, Logback, Log4j 2, Java Util Logging, and Spring JCL; how Spring Boot selects defaults; how to switch backends; how to resolve classpath conflicts; and practices that keep logs useful without creating performance or sensitive-data risks.

## 1. Why not use System.out.println for logging?

Java allows printing directly:

~~~java
System.out.println("Order " + orderId + " created");
~~~

This approach is valid for quickly testing a small program, but it has limitations in long-running services:

- There are no standard levels such as `DEBUG`, `INFO`, `WARN`, or `ERROR`.
- Log levels cannot be adjusted separately per package or component without modifying code.
- It is hard to attach timestamps, thread names, correlation IDs, and consistent metadata.
- It is hard to send output to multiple destinations such as the console, files, a log collector, or an observability system.
- It performs string concatenation even when the message does not need to be emitted.
- It is hard to apply rolling, retention, asynchronous appenders, and filtering rules.
- It easily leads to uncontrolled printing of sensitive information.

Example with a logger:

~~~java
log.debug("Loading order {}", orderId);
log.info("Order {} created", orderId);
log.warn("Order {} is close to expiration", orderId);
log.error("Unable to finalize order {}", orderId, exception);
~~~

Operations can keep `INFO` in production and enable `DEBUG` only for the relevant package when investigating. Business code does not need to change.

### Logging does not replace business outcomes

Logs are **system observability** data, not the sole place to store business state. A successful transaction must be reflected in the database or appropriate source of truth, not merely by an `INFO` line. If the log collection system is temporarily interrupted, business data must still be preserved according to its transaction.

## 2. What is a logging facade?

A **facade** is a common interface standing in front of concrete implementations. Callers interact with a stable API without needing to know which library is used underneath.

Conceptual example:

~~~text
OrderService
    |
    v
Logger API (facade)
    |
    v
Logging backend
    |
    +--> Console
    +--> File
    +--> Remote collector
~~~

If code directly imports a backend-specific logger API, switching backends can require modifying many source files. If code uses a unified facade, most changes are concentrated in dependencies and runtime configuration.

### Three common layers

| Layer | Question answered | Examples |
|---|---|---|
| Logging API / facade | Which method does code call to log? | SLF4J API, Commons Logging API |
| Provider / binding / adapter | Which implementation is the API connected to? | SLF4J provider for Logback or Log4j 2 |
| Logging backend | Who filters, formats, and writes events? | Logback, Log4j 2, JUL |

An application can use multiple original APIs from different libraries. In that case, bridges/adapters can route the calls into a single common logging pipeline.

### A logging facade does not necessarily write logs itself

The SLF4J API defines contracts such as `Logger.debug(...)` and `LoggerFactory.getLogger(...)`. It does not require every application to write files the same way. Execution belongs to the actual provider/backend.

Therefore, **having the `slf4j-api` dependency does not mean an active backend is already present**.

## 3. What is SLF4J?

**SLF4J** (*Simple Logging Facade for Java*) is a popular logging abstraction in Java. Application code and many libraries can use the same API even when the actual backend differs.

Important classes:

~~~java
org.slf4j.Logger
org.slf4j.LoggerFactory
org.slf4j.MDC
org.slf4j.Marker
~~~

Example:

~~~java
package com.example.store.service;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String orderNumber) {
        log.info("Submitting order {}", orderNumber);

        // Order placement business logic.

        log.info("Order {} submitted", orderNumber);
    }
}
~~~

This code does not directly import `ch.qos.logback.*` or `org.apache.logging.log4j.core.*`. It depends only on the facade.

### Why should libraries also depend on the SLF4J API?

A library using SLF4J lets the **final application** decide the output. If a library forces users to install a specific backend, the application could end up with multiple simultaneous logging systems or conflicting configuration files.

A common principle:

- **Application:** choose one clear SLF4J provider/backend and configure where logs are written.
- **Reusable library:** prefer depending only on the logging API; avoid forcing a backend onto applications consuming the library.

This does not mean every Java library must use SLF4J. Some libraries use JUL, Log4j API, or JCL; bridges help unify them in appropriate cases.

## 4. What is a logging backend?

The backend is responsible for turning a logger call into a log event, deciding whether to emit the event, and deciding where to write it.

A typical backend has these components:

~~~text
Logger call
    |
    v
Level check / filter
    |
    v
Log event
    |
    v
Appender / handler
    |
    +--> Console encoder
    +--> Rolling file appender
    +--> Async appender
    +--> Structured log encoder
    +--> Other supported sinks
~~~

Concepts may have different names across backends. For example, Logback and Log4j 2 commonly use the term **appender**; Java Util Logging uses **handler**.

### Common backends

| Backend | Ecosystem | General characteristics |
|---|---|---|
| **Logback** | SLF4J / QOS | Default backend in many common Spring Boot starter configurations |
| **Log4j 2** | Apache Logging Services | Backend with its own configuration, appender, async, and plugin ecosystem |
| **Java Util Logging (JUL)** | JDK | Logging API and implementation built into the JDK |
| **SLF4J Simple** | SLF4J | Lightweight implementation, often used for examples or small tools |
| **SLF4J NOP** | SLF4J | Discards logs; useful in certain specialized tests, but dangerous if accidentally used in production |

No single backend is "best" in every case. The choice depends on requirements, existing dependencies, operations, and organizational standards.

## 5. What does Spring Boot use by default?

In typical Spring Boot projects using a starter such as `spring-boot-starter-web`, the default dependency for logging is **Spring Boot starter logging**, which usually brings **Logback** onto the runtime classpath.

Maven example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

If the project uses Spring Boot dependency management and does not exclude the logging starter, the necessary logging components are usually already present; there is no need to manually declare Logback just to use `LoggerFactory`.

General flow:

~~~text
spring-boot-starter-web
           |
           v
spring-boot-starter
           |
           v
spring-boot-starter-logging
           |
           +--> SLF4J API
           +--> Logback backend/provider
           +--> Required bridges
                    |
                    v
             Console logging
~~~

This diagram is conceptual; the exact dependency structure varies by Spring Boot version or the starters a project uses.

### Logback is the default, not a mandatory API

Code should be written as:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
~~~

rather than depending on backend classes:

~~~java
import ch.qos.logback.classic.Logger;
~~~

If app code uses only SLF4J, switching the backend from Logback to Log4j 2 usually does not require editing masses of logger calls.

### When not using a Spring Boot starter

A Spring Boot application assembled with manual dependencies might not include the logging starter. In that case, you need to verify that `slf4j-api`, a compatible provider, and a backend are present. Do not assume every Spring application has Logback just because importing `LoggerFactory` succeeds.

## 6. Distinguishing SLF4J 1.7 bindings and SLF4J 2.x providers

This is very important when inspecting the dependency tree and debugging startup messages.

### SLF4J 1.7 generation

With SLF4J 1.7.x and earlier generations, implementations typically linked using a **binding** mechanism, tied to the class:

~~~text
org.slf4j.impl.StaticLoggerBinder
~~~

Older documentation often says "SLF4J binding". For example, a library provides a binding connecting the SLF4J API to a backend.

### SLF4J 2.x

SLF4J 2.x uses a **provider** mechanism, based on Java `ServiceLoader` and the contract:

~~~text
org.slf4j.spi.SLF4JServiceProvider
~~~

A provider can appear on the runtime classpath and be selected by SLF4J to supply the logger factory.

Therefore:

- With API 1.7, messages mentioning `StaticLoggerBinder` are familiar.
- With API 2.x, look for **SLF4J providers**.
- A binding built only for SLF4J 1.7 does not automatically become a valid provider for API 2.x.
- The provider/backend should match the major version of the SLF4J API that the application uses.

In Spring Boot 3.x, the ecosystem typically uses SLF4J 2.x. For older projects using Spring Boot 2.x, check the actual version before applying 2.x provider recipes.

### Do not fix errors by adding a random JAR

If SLF4J reports that no provider was found, the solution is not adding any arbitrary dependency whose name contains `slf4j`. You must choose the provider with the right version for your desired backend while removing other conflicting providers.

## 7. Flow when SLF4J uses Logback

Example code:

~~~java
log.info("Payment {} succeeded", paymentId);
~~~

In an SLF4J + Logback configuration, you can picture it as:

~~~text
PaymentService
    |
    | org.slf4j.Logger.info(...)
    v
SLF4J API
    |
    v
Logback SLF4J provider
    |
    v
Logback LoggerContext
    |
    v
Effective level / filters
    |
    v
LoggingEvent
    |
    v
Appenders + Encoder / Pattern
    |
    +--> stdout / stderr
    +--> rolling file
    +--> other destinations
~~~

Main steps:

1. Code calls a method on SLF4J `Logger`.
2. The provider routes the call to Logback.
3. Logback determines the corresponding level and filters.
4. If the event is accepted, Logback creates/formats the log event.
5. The appender writes the message according to the configuration.

The backend can also handle asynchronous logging, rolling policies, or structured output. These capabilities belong to the backend and its configuration, not a universal guarantee of every SLF4J call.

## 8. How do Logback and Log4j 2 differ from SLF4J?

A common misconception is treating SLF4J, Logback, and Log4j 2 as three competing peer APIs.

In reality:

- **SLF4J** is primarily a **facade API**.
- **Logback** is a logging backend tightly integrated with SLF4J.
- **Log4j 2** is an entire logging ecosystem with its own API, its own core/backend, and an adapter/provider for SLF4J.

Illustrative table:

| Component | Role |
|---|---|
| `slf4j-api` | API that application/library code can call |
| `logback-classic` | Logback SLF4J implementation/provider |
| `logback-core` | Appender/encoder infrastructure and core of Logback |
| `log4j-api` | Log4j 2's own facade/API |
| `log4j-core` | Log4j 2 execution backend |
| `log4j-slf4j2-impl` | Provider routing SLF4J 2.x API into Log4j 2 |
| `log4j-to-slf4j` | Bridge routing Log4j API calls into SLF4J |

Specific artifact names matter when debugging the classpath. In particular, **`log4j-slf4j2-impl` and `log4j-to-slf4j` move logs in opposite directions**. You should not put both on the same classpath to "support everything".

## 9. Parameterized logging

SLF4J supports the `{}` placeholder to separate the template from arguments:

~~~java
log.info("Order {} created for customer {}", orderId, customerId);
~~~

Unlike string concatenation:

~~~java
log.debug(
        "Order " + orderId
                + " has " + items.size()
                + " items"
);
~~~

Parameterized logging helps avoid unnecessary string concatenation when the log level is disabled and lets the backend perform formatting in an appropriate way.

### {} syntax is not String.format

Correct example:

~~~java
log.info("User {} performed action {}", userId, action);
~~~

Incorrect example if you intend to use SLF4J placeholders:

~~~java
log.info("User %s performed action %s", userId, action);
~~~

`%s` is syntax commonly used in `String.format`, not SLF4J's default placeholder.

### Do not pass an array as a message template arbitrarily

When logging a list or array, use the appropriate API and avoid generating excessively large dump strings. A single logger call can generate huge amounts of data if an argument is an object with a heavy `toString()` or a wide object graph.

### Parameterization does not prevent all costs

Example:

~~~java
log.debug("Product snapshot: {}", buildExpensiveSnapshot());
~~~

`buildExpensiveSnapshot()` is still called when Java evaluates the argument, **before Logger decides whether to log**.

Safer approach:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Product snapshot: {}",
            buildExpensiveSnapshot()
    );
}
~~~

With SLF4J 2.x, the fluent API also supports supplying arguments via `Supplier` to defer computation.

## 10. SLF4J logging levels

Common SLF4J levels:

| Level | When to use? | Example |
|---|---|---|
| `ERROR` | Operation failed, needs handling/investigation | Failed to save order |
| `WARN` | Abnormal behavior but not a complete failure yet | Retries nearing limit |
| `INFO` | Important operational/lifecycle milestone | Job started and completed |
| `DEBUG` | Details supporting development and investigation | Processing branch selection |
| `TRACE` | Very deep detail, usually high event volume | Tracking each small step |

The common rule when configured with an `INFO` threshold is:

~~~text
ERROR -> Logged
WARN  -> Logged
INFO  -> Logged
DEBUG -> Discarded
TRACE -> Discarded
~~~

There is no general `FATAL` level in the SLF4J API. Some backends have their own level systems, but application code via SLF4J usually uses the five levels above.

### Choose log levels based on operational meaning

Example:

~~~java
log.info(
        "Payment reconciliation started: batchId={}",
        batchId
);
~~~

A job start event may be worth logging at `INFO`.

~~~java
log.debug(
        "Using payment strategy {} for batch {}",
        strategyName,
        batchId
);
~~~

Implementation details fit better at `DEBUG`.

~~~java
log.warn(
        "Payment gateway timed out; retry {} of {}",
        attempt,
        maxAttempts
);
~~~

If the error ultimately leads to a business failure:

~~~java
log.error(
        "Payment reconciliation failed: batchId={}",
        batchId,
        exception
);
~~~

Do not log the same exception at `ERROR` at every layer and then rethrow it; that can create multiple duplicate stack traces for a single incident. Usually you should log at the boundary that has sufficient context and is responsible for handling the error.

## 11. Logging exceptions properly

Logger has an overload for `Throwable`:

~~~java
try {
    paymentClient.capture(paymentId);
} catch (PaymentException ex) {
    log.error(
            "Failed to capture payment {}",
            paymentId,
            ex
    );
    throw ex;
}
~~~

Passing `ex` at the end lets the backend log the stack trace according to configuration; unlike:

~~~java
log.error("Capture failed: {}", ex.getMessage());
~~~

The second approach logs only the message, potentially losing the stack trace when investigating.

### Not every error always needs a stack trace

Invalid input created by a user usually does not need an `ERROR` with a full stack trace. You can log warnings selectively or rely on metrics and the HTTP error response.

Conversely, unexpected errors from supporting systems may need a stack trace to identify where the error originated.

### Note on logging and rethrowing

If a controller advice, scheduler, or message listener at an outer layer already logs the error, an inner service does not necessarily need to write an additional duplicate `ERROR` log. You can add context to the exception or log at `DEBUG` as needed, and let the higher boundary log it once.

## 12. Configuring logging with application.yml

Spring Boot supports many common logging properties.

Example:

~~~yaml
logging:
  level:
    root: INFO
    com.example.store: DEBUG
    org.springframework.web: WARN
~~~

Meaning:

- The root logger has a threshold of `INFO`.
- Loggers under package `com.example.store` have a threshold of `DEBUG`.
- Loggers under `org.springframework.web` have a threshold of `WARN`.

With `application.properties`:

~~~properties
logging.level.root=INFO
logging.level.com.example.store=DEBUG
logging.level.org.springframework.web=WARN
~~~

Spring Boot processes these properties to configure the supported logging system.

### Logger names usually follow package/class

When you write:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

the logger name is usually the fully-qualified class name, for example:

~~~text
com.example.store.order.OrderService
~~~

Configuring `logging.level.com.example.store=DEBUG` can apply to this logger via the logger name hierarchy mechanism.

### Choose a narrow DEBUG scope

Setting `logging.level.root=DEBUG` in production can generate massive log volumes from all libraries. Usually you should enable it only for the package under investigation:

~~~yaml
logging:
  level:
    root: INFO
    com.example.store.payment: DEBUG
~~~

You also need a time limit and log volume monitoring when enabling `DEBUG` or `TRACE` in production.

## 13. Configuring files and format via Spring Boot

Some common properties:

~~~properties
logging.file.name=logs/store-service.log
logging.level.root=INFO
logging.pattern.console=%d{yyyy-MM-dd HH:mm:ss} %-5level [%thread] %logger{36} - %msg%n
~~~

The `logging.file.name` property can instruct a Spring Boot-supported backend to write to a file according to Boot's configuration. The console pattern lets you adjust formatting in versions/backends that support that pattern property.

However, **not every backend and every Spring Boot version has the same set of properties or supports the same pattern syntax**. If the configuration requires complex rolling policies, multiple appenders, or specialized filters, the backend's native configuration file is usually more appropriate.

### File logging and container operations

In containers, the common practice is writing to stdout/stderr and letting the infrastructure collect logs. Writing files into a container's ephemeral filesystem can cause logs to disappear when the container is replaced, unless an appropriate volume or collector is in place.

This does not mean a file appender is always wrong. In environments requiring special compliance, retention, or auditing, file logging can be a reasonable choice if operated under proper control.

### Pay attention to encoding, rotation, and disk space

When writing files, you must pay attention to:

- UTF-8 for Vietnamese and international characters.
- Rolling policies by size/time.
- Retention limits and total disk capacity.
- File write permissions for the process.
- Cleanup when disk space fills up.
- Backpressure during log spikes.

These settings depend on the actual backend and deployment environment, and are not solved simply by calling `log.info(...)`.

## 14. Dedicated Logback configuration

When using Logback, Spring Boot supports configuring the backend via a file such as:

~~~text
src/main/resources/logback-spring.xml
~~~

Simple example:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.store" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

This file illustrates a console appender along with a package logger override. When providing a native configuration instead of the default, **the application must actively declare all required appenders and the root logger**; do not assume every default detail from Boot will still be automatically added to a custom file.

### logback.xml and logback-spring.xml

`logback.xml` can be loaded very early by Logback using its own mechanism. `logback-spring.xml` is the name supported by Spring Boot to bring Spring-specific extensions into the Logback configuration at the appropriate Boot-managed time.

Example using profiles:

~~~xml
<configuration>
    <springProfile name="dev">
        <logger name="com.example.store" level="DEBUG"/>
    </springProfile>

    <springProfile name="prod">
        <logger name="com.example.store" level="INFO"/>
    </springProfile>

    <include resource="org/springframework/boot/logging/logback/base.xml"/>
</configuration>
~~~

This is an illustration of the `<springProfile>` extension. Built-in include resources provided by Spring Boot may differ across versions; choose a resource supported by the documentation of the version in use rather than blindly copying a path from an older version.

The key point to remember is that **Spring Boot extensions should not be placed arbitrarily in a file loaded too early by the backend itself**, because the Spring Environment may not be ready yet at that time.

### Do not hard-code secrets into log config

Appenders sending logs externally may require credentials. Do not write tokens directly inside committed XML files. Use secure configuration sources and appropriate backend integration mechanisms.

## 15. Configuring log levels using profiles

Common configuration:

~~~yaml
logging:
  level:
    root: INFO
    com.example.store: INFO
~~~

In `application-dev.yml`:

~~~yaml
logging:
  level:
    com.example.store: DEBUG
~~~

In `application-prod.yml`:

~~~yaml
logging:
  level:
    com.example.store: INFO
    org.springframework: WARN
~~~

When the appropriate profile is active, Config Data can bring the corresponding logging properties into the Environment. Spring Boot configures logging based on the effective values during the bootstrap phase.

If run with:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

the logging values of the `prod` profile can be applied, unless overridden by a configuration source with higher precedence.

### Why can @PropertySource be too late?

A `@PropertySource` on `@Configuration` is processed during ApplicationContext refresh, whereas Spring Boot already needs to initialize logging early. Therefore, you should not rely on `@PropertySource` to configure logging properties needed during the bootstrap step.

Placing them in `application.yml`, profile-specific Config Data, environment variables, or command-line arguments is the standard choice.

## 16. Switching Spring Boot's backend from Logback to Log4j 2

A reason to switch backends might be specific requirements for appenders, asynchronous logging, formats, or operational policies standardized on Log4j 2.

What matters is **not keeping two primary SLF4J providers at the same time**. Switching backends requires changing the runtime classpath, not just adding another dependency.

### Maven with spring-boot-starter-web

Example:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-logging</artifactId>
            </exclusion>
        </exclusions>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-log4j2</artifactId>
    </dependency>
</dependencies>
~~~

This example assumes the project uses Spring Boot dependency management and therefore does not declare versions on the starters.

If the project has multiple other starters that also pull `spring-boot-starter-logging` onto the classpath, you must exclude the logging starter from those dependency paths or configure appropriate exclusions. Excluding from only one starter may not be enough.

### Gradle Kotlin DSL

Example of one way to switch backends:

~~~kotlin
configurations.configureEach {
    exclude(
        group = "org.springframework.boot",
        module = "spring-boot-starter-logging"
    )
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-log4j2")
}
~~~

The exclusion above is applied broadly across configurations in the example; in a real project, examine the dependency graph to decide the appropriate exclusion scope.

### After switching backends

Application code can still write:

~~~java
private static final Logger log =
        LoggerFactory.getLogger(OrderService.class);
~~~

The runtime provider itself routes SLF4J calls to Log4j 2.

Verify that the classpath has:

- A compatible SLF4J API version.
- The `log4j-slf4j2-impl` provider for SLF4J 2.x if corresponding to the Spring Boot generation.
- The `log4j-core` backend.
- No remaining competing Logback provider.
- No reverse bridge causing a loop.

### Configuring Log4j 2

A commonly used filename in Spring Boot is:

~~~text
src/main/resources/log4j2-spring.xml
~~~

Minimal example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{HH:mm:ss.SSS} %-5p %c{1} - %m%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="com.example.store"
                level="debug"
                additivity="false">
            <AppenderRef ref="Console"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
~~~

This configuration illustrates Log4j 2 syntax. When using a specific backend, consult the schema and version of that backend.

## 17. Java Util Logging (JUL)

The JDK provides logging through the package:

~~~java
java.util.logging
~~~

Example:

~~~java
import java.util.logging.Logger;

public class LegacyImporter {

    private static final Logger log =
            Logger.getLogger(LegacyImporter.class.getName());

    public void importData() {
        log.info("Starting import");
    }
}
~~~

JUL has its own logger, handler, formatter, and level system. It does not naturally use the SLF4J API just because the project has `slf4j-api` on the classpath.

If the application wants to unify JUL logs into the backend used by SLF4J, it can use a **JUL-to-SLF4J bridge** such as `jul-to-slf4j` along with appropriate handler configuration.

### Having a bridge does not mean all JUL logs switch automatically

With JUL, bridging requires installing the corresponding handler/routing. Simply having a JAR without the handler applied may not be enough for all log paths.

Spring Boot's logging starter normally brings in the relevant bridges/infrastructure, but if the project manages dependencies manually or initializes logging in a special way, check the runtime configuration.

### Do not configure a loop

If you both bridge JUL → SLF4J and set SLF4J → JUL as the provider, an event can loop back and continue repeating. Do not use opposite-direction bridges simultaneously on the same path.

## 18. Commons Logging, Spring JCL, and SLF4J

Some traditional Java libraries use the **Apache Commons Logging API**, commonly called JCL. Spring Framework provides `spring-jcl` to support a logging facade compatible with how Spring uses logging.

Example code in Commons Logging style:

~~~java
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;

public class LegacyService {

    private final Log log =
            LogFactory.getLog(LegacyService.class);

    public void execute() {
        log.info("Executing task");
    }
}
~~~

In a Spring Boot application, Spring Framework itself routes logging through Spring JCL. Spring JCL can adapt to available logging APIs/backends.

### Why distinguish spring-jcl and jcl-over-slf4j?

`spring-jcl` is a facade/adapter provided by Spring. `jcl-over-slf4j` is another bridge provided by the SLF4J ecosystem to replace the Commons Logging path with SLF4J.

These artifacts can provide classes with the same package name `org.apache.commons.logging`. If both accidentally coexist or are pulled in by an older library, warnings, classpath-order conflicts, or unpredictable logging behavior can occur.

In a Spring Boot application, prefer the dependency model managed by Spring Boot and inspect before adding a Commons Logging bridge yourself.

### Spring JCL is different from the SLF4J API

Spring can use the Commons Logging-style API through `spring-jcl`, while application code intentionally uses the SLF4J API. These two do not conflict. They can both lead to the same backend, even though they are not the same Java interface.

## 19. Bridging logging to unify multiple APIs

A real-world application might use library A calling SLF4J, library B calling JUL, and library C calling the Log4j API. To output logs to the same system, you need a clearly directed routing design.

Example when the target is Logback:

~~~text
Application calling SLF4J --------+
                                  |
Library calling Log4j API --------+--[bridge Log4j API -> SLF4J]--+
                                  |                               |
Library calling JUL --------------+--[bridge JUL -> SLF4J]--------+--> SLF4J
                                                                  |
                                                                  v
                                                            Logback provider
                                                                  |
                                                                  v
                                                                Output
~~~

Conversely, if the backend is Log4j 2:

~~~text
Application calling SLF4J
        |
        v
SLF4J provider -> Log4j 2
        |
        v
Log4j 2 Core -> appenders
~~~

Calls to the Log4j API can go directly to Log4j 2; there is no need to bridge from Log4j API to SLF4J and then back to Log4j 2.

### A bridge is an event-routing direction, not just a dependency

Read artifact names like an arrow:

| Artifact | General direction |
|---|---|
| `log4j-to-slf4j` | Log4j API → SLF4J |
| `log4j-slf4j2-impl` | SLF4J 2.x API → Log4j 2 |
| `jul-to-slf4j` | JUL → SLF4J |
| `slf4j-jdk14` | SLF4J → JUL |
| `jcl-over-slf4j` | Commons Logging API → SLF4J |

What must be avoided is configuring both directions simultaneously:

~~~text
SLF4J --> Log4j 2 --> SLF4J --> Log4j 2 ...
~~~

or:

~~~text
SLF4J --> JUL --> SLF4J --> JUL ...
~~~

Some implementations have mechanisms to detect dangerous configurations and report an error instead of looping forever, but you should not rely on that. Actively design **one primary direction toward one final backend**.

## 20. Why do multiple SLF4J providers cause trouble?

Suppose the runtime classpath contains:

~~~text
slf4j-api-2.x.jar
logback-classic-1.x.jar
log4j-slf4j2-impl-2.x.jar
~~~

Two backends can simultaneously supply an SLF4J provider. SLF4J 2.x usually emits a warning about multiple providers and picks one actual provider, but the result depends on how service providers are discovered; you should not rely on arbitrary classpath ordering to decide the backend.

Symptoms:

- Logs have an unexpected format.
- `logback-spring.xml` has no effect because Logback was not the chosen backend.
- `log4j2-spring.xml` has no effect because Log4j 2 was not chosen.
- Startup warnings related to SLF4J.
- Different behavior between the IDE, test runtime, and executable JAR.

### The right way to resolve it

1. Decide on **one backend** for the application.
2. Identify which starter or library is pulling in each provider.
3. Exclude redundant dependencies from their source rather than just silencing warnings.
4. Use a provider version compatible with the SLF4J API.
5. Ensure bridges route events in one direction only toward the chosen backend.
6. Verify that the expected backend configuration is actually loaded.

In a Spring Boot application using dependency management, the easiest approach to maintain is usually using Boot's default logging starter or Log4j 2 starter, avoiding manually pinning individual logging JAR versions unless there is a good reason and compatibility has been verified.

## 21. When there is no SLF4J provider

For example, the classpath only has:

~~~text
slf4j-api-2.x.jar
~~~

With SLF4J 2.x, if no provider is found, SLF4J can warn and fall back to the default NOP logger. The application may still start, but logs via SLF4J **are not emitted as expected**.

This is a dangerous error in production: the service can run while lacking logs needed for investigation.

### Distinguishing a missing provider from a disabled level

If `DEBUG` does not appear while `INFO` still appears, it may simply be a logging threshold. If no events appear at all, check:

- Is a provider present on the runtime classpath?
- Are there SLF4J warnings about providers?
- Does the backend have an appropriate appender?
- Are the root level or filters discarding events?
- Is output going to stdout, stderr, or a different file?
- Are loggers being routed into another backend?

### Old bindings are ignored by SLF4J 2.x

A JAR that only supplies the `StaticLoggerBinder` mechanism for SLF4J 1.7 is not a valid provider for API 2.x. SLF4J 2.x can report that the old-style binding is ignored. The solution is using a compatible provider, not adding more old bindings.

## 22. Inspecting the dependency tree

Logging conflicts are usually a **dependency graph problem**, not a bug on the `log.info` line.

With Maven, you can view the dependency tree:

~~~bash
mvn dependency:tree
~~~

You can filter for relevant artifacts:

~~~bash
mvn dependency:tree -Dincludes=org.slf4j:slf4j-api
mvn dependency:tree -Dincludes=ch.qos.logback:logback-classic
mvn dependency:tree -Dincludes=org.apache.logging.log4j:log4j-slf4j2-impl
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find the path pulling in an artifact:

~~~bash
./gradlew dependencyInsight \
  --dependency logback-classic \
  --configuration runtimeClasspath
~~~

Similarly:

~~~bash
./gradlew dependencyInsight \
  --dependency slf4j-api \
  --configuration runtimeClasspath
~~~

These are suggested commands to use when diagnosing in a real project, not steps required to run when writing this documentation.

### Runtime classpath matters more than compile classpath

A module can compile successfully because `slf4j-api` is present, yet at runtime have no provider or have two providers. Therefore, when logging misbehaves, inspect **runtimeClasspath** or the dependencies of the actual executable artifact.

### Spring Boot dependency management

When using Spring Boot's parent/BOM, the framework manages versions of many logging libraries in sync. Manually setting mismatched versions of SLF4J, Logback, or Log4j 2 can cause compatibility errors or unpredictable behavior.

Only override versions when genuinely necessary and after understanding the impact on the remaining components.

## 23. A logging facade keeps libraries backend-independent

An internal library:

~~~java
public class DiscountCalculator {

    private static final Logger log =
            LoggerFactory.getLogger(DiscountCalculator.class);

    public BigDecimal apply(
            BigDecimal original,
            BigDecimal discount
    ) {
        log.debug(
                "Applying discount {} to amount {}",
                discount,
                original
        );

        return original.subtract(discount);
    }
}
~~~

This library can be used by:

- A Spring Boot application using Logback.
- An application using Log4j 2.
- A CLI tool using an appropriate simple provider.
- A test application with its own logging backend.

When building the library, it usually only needs a compile/runtime dependency on `slf4j-api` according to packaging design. The consuming application is responsible for choosing the provider.

### Why not include Logback in a library?

If a library pulls in Logback as a mandatory dependency, an application wanting to use Log4j 2 may end up with multiple providers. That reduces library reusability and increases the exclusion burden.

If a library provides a Spring Boot starter, carefully consider any backend dependencies pulled in and respect the host application's choice.

## 24. SLF4J 2.x fluent API

Alongside the familiar `debug/info/warn/error` methods, SLF4J 2.x supports fluent logging:

~~~java
log.atInfo()
        .addKeyValue("orderId", orderId)
        .addKeyValue("customerId", customerId)
        .log("Order created");
~~~

The fluent API can attach key-value metadata, markers, exceptions, and arguments in a structured manner. However, the backend must support/format them appropriately for key-values to appear as expected.

### Deferred arguments with Supplier

Example:

~~~java
log.atDebug()
        .addArgument(() -> buildExpensiveSnapshot())
        .log("Current snapshot: {}");
~~~

With this API style, the argument supplier can be evaluated only when the event is actually processed according to the SLF4J 2.x contract. This is a way to avoid the cost of building the snapshot when `DEBUG` is disabled.

The traditional approach remains valid:

~~~java
if (log.isDebugEnabled()) {
    log.debug("Current snapshot: {}", buildExpensiveSnapshot());
}
~~~

You are not required to rewrite all logging code to the fluent API. Use the syntax your development team can read and operate consistently.

### Key-values do not automatically turn every output into JSON

Example:

~~~java
log.atInfo()
        .addKeyValue("event", "order-created")
        .addKeyValue("orderId", orderId)
        .log("Order created");
~~~

SLF4J supplies information to the backend. Whether the output is JSON with separate fields or plain text depends on the backend, encoder, and structured logging configuration. Do not promise that calling `addKeyValue(...)` will automatically produce a standard JSON schema for every system.

## 25. MDC: attaching context to logs

**Mapped Diagnostic Context (MDC)** is a mechanism for carrying a set of key-value information typically bound to the execution context, for example:

- `traceId` or `correlationId`.
- `requestId`.
- `jobId`.
- `tenantId` if permitted by data policy.
- `batchId`.

Example:

~~~java
import org.slf4j.MDC;

String previous = MDC.get("correlationId");
MDC.put("correlationId", correlationId);

try {
    orderService.process(orderId);
} finally {
    if (previous == null) {
        MDC.remove("correlationId");
    } else {
        MDC.put("correlationId", previous);
    }
}
~~~

Restoring the previous value in `finally` prevents polluting the MDC of a reused thread. With a request-thread pool, forgetting cleanup can cause the next request to mistakenly carry the correlation ID of the previous request.

### Logback patterns can reference MDC

Example pattern:

~~~text
%d{HH:mm:ss.SSS} %-5level [%X{correlationId}] %logger - %msg%n
~~~

`%X{correlationId}` is Logback's common pattern syntax for an MDC value. For other backends, the layout syntax may differ.

### MDC and async do not automatically propagate across new threads

Many MDC implementations bind context to the thread. When handing work off to `@Async`, an executor, or a new thread, MDC information is not necessarily carried along.

If you need correlation IDs in async tasks, you can:

- Pass the value via method parameters or event payload.
- Use a `TaskDecorator` or framework-supported context propagation.
- Restore/clean up MDC properly when the task finishes.
- Integrate with the appropriate tracing/observation infrastructure.

Do not treat MDC accidentally appearing on a thread as a business contract.

## 26. Structured logging

Text logs are helpful when read directly, but log collection systems often prefer structured fields:

~~~json
{
  "timestamp": "2026-11-13T09:00:00Z",
  "level": "INFO",
  "logger": "com.example.store.OrderService",
  "message": "Order created",
  "orderId": "O-1024",
  "correlationId": "req-7f9a"
}
~~~

This is an example data shape, not a mandatory JSON structure of Spring Boot, SLF4J, or any specific backend.

Benefits of structured logging:

- Filter logs by field without manual text parsing.
- Find events sharing the same correlation ID.
- Build dashboards by event name and level.
- Standardize output across multiple services.

Recent versions of Spring Boot have built-in configuration options for structured logging; the exact scope and property names depend on the version. In addition, Logback/Log4j 2 have encoders/layouts or add-on libraries for structured output.

### Keep messages and fields meaningful

When using structured fields, put values such as `orderId` into separate fields; keep the message describing the event concisely:

~~~text
message = "Order created"
orderId = "O-1024"
customerId = "C-83"
~~~

There is no need to cram the entire object or a raw JSON string into `message` if the backend can emit structured fields.

### Do not treat structured logs as a business data store

Structured logs can be sampled, have short retention, or be lost if the collector fails. For data that must be retained reliably, use an appropriate database, event store, or audit store.

## 27. Early logging during startup

Spring Boot needs logging before the ApplicationContext is completely ready in order to report configuration, dependency, or startup errors.

General flow:

~~~text
JVM starts main
       |
       v
SpringApplication starts
       |
       +--> Prepare logging system
       |
       +--> Prepare Environment/Config Data
       |
       +--> Apply required logging properties
       |
       v
Create ApplicationContext
       |
       v
Create beans and run application
~~~

How Spring Boot uses logging listeners and the Environment can vary across versions, but the core point is that logging configuration belongs to **bootstrap configuration**.

### Why not wait for a @Configuration bean to configure loggers?

A `BeanCreationException` can occur before a custom logging configuration bean is created. If logging only initialized then, bootstrap errors would be hard to observe.

Therefore, important logging properties should live in configuration sources read early by Boot, such as Config Data or system/environment properties. Do not put the entire logging setup inside a late-created `@Bean` and expect it to control all startup logs.

### System properties and environment variables

Example:

~~~bash
java -jar store.jar --logging.level.com.example.store=DEBUG
~~~

Or:

~~~bash
java -Dlogging.level.root=DEBUG -jar store.jar
~~~

The actual log level depends on property source precedence and how Spring Boot coordinates logging. When debugging startup, the command line is a useful way to enable a level without modifying packaged files.

## 28. Adjusting log levels at runtime with Actuator

If Spring Boot Actuator is present and configured to expose the appropriate endpoint, the **loggers** endpoint can provide the ability to view or change logging levels at runtime.

Concept:

~~~text
GET  /actuator/loggers
GET  /actuator/loggers/com.example.store
POST /actuator/loggers/com.example.store
~~~

Example request body for a logger:

~~~json
{
  "configuredLevel": "DEBUG"
}
~~~

Exact capabilities and endpoints depend on the Spring Boot/Actuator version and security/exposure configuration. Management endpoints can alter the logging behavior of a running service, so **do not expose this endpoint publicly without control**.

### Changing levels at runtime is not a persistent configuration change

If an administrator changes a log level via the endpoint, that change may be lost when the application restarts or is redeployed. To make a persistent change, update the managed config source.

### Plans to enable DEBUG should have an endpoint

DEBUG/TRACE can significantly increase log volume, CPU usage, and storage costs. You should define the investigation time window, specific package, authorized operators, and the time to revert the level back to default.

## 29. Logging performance

Logging incurs costs at multiple steps:

~~~text
Build arguments
    |
    v
Check level
    |
    v
Create log event
    |
    v
Format message / stack trace
    |
    v
Encoder / serialization
    |
    v
I/O (console, file, network)
~~~

When the level is disabled, many subsequent steps may not run; however, **Java still evaluates arguments before calling the method**.

Expensive example:

~~~java
log.debug(
        "Repository state = {}",
        repository.loadAllForDebug()
);
~~~

Even when DEBUG is disabled, `repository.loadAllForDebug()` still executes because it is a Java argument.

Appropriate approach:

~~~java
if (log.isDebugEnabled()) {
    log.debug(
            "Repository state = {}",
            repository.loadAllForDebug()
    );
}
~~~

Or use a `Supplier` with SLF4J 2.x's fluent API.

### Async logging: when is it useful?

Backends can support async appenders or async loggers. Offloading I/O from business threads can reduce latency, but consider:

- Queue size and memory limits.
- What happens when the queue is full.
- Log loss if the process crashes.
- Flush time during shutdown.
- Event ordering and how log timestamps are generated.
- Preserving correlation context across threads.

Async logging does not automatically guarantee zero log loss. For mandatory auditing, use a durable data mechanism rather than treating async logs as transactions.

### Excessive logging is also an operational bug

Logging every processed record at `INFO` in a job with millions of records can consume substantial CPU, disk, and log collector budget. You can log batch summaries, counters, metrics, and error cases instead of every item.

## 30. Sensitive logs and security

A useful logging system must not expose personal data or authentication credentials.

**Do not log:**

- Passwords, API keys, bearer tokens, session cookies.
- Private keys, database credentials, or connection strings containing passwords.
- Full request/response bodies containing sensitive data.
- Complete payment details.
- Personal data unnecessary for investigation.
- Exception contents if they might contain unfiltered secrets.

Dangerous example:

~~~java
log.info("Login request: {}", loginRequest);
~~~

If `loginRequest.toString()` includes the password, that information can appear in logs and be copied to the collector.

Safer:

~~~java
log.info(
        "Login attempt for accountId={}",
        accountId
);
~~~

Log only identifiers sufficient for operations and compliant with data policy.

### Watch out for log injection

User-supplied data can contain newline or control characters. If written directly into text logs, that data can forge fake log entries or break parsing.

Use structured logging/encoders with proper escaping, enforce field length limits, and sanitize high-risk inputs.

### Do not dump the entire Environment

The Spring Environment can contain secrets from variables, config trees, or secret stores. Logging all property sources for debugging can leak credentials. When diagnosing, prefer logging **configuration source names**, not printing all key-values.

## 31. Log4j 1.x and Log4j 2 are not the same

The name "Log4j" can cause confusion across generations.

- **Log4j 1.x** is an older generation that reached end-of-life long ago and should not be used for new projects.
- **Log4j 2** is a modern ecosystem with `log4j-api`, `log4j-core`, and appropriate adapters.
- **Logback** is a different backend, not "renamed Log4j 1.x".

When you see a dependency containing `log4j`, check the **artifact and major version**, not just the name.

### Security updates are also part of logging management

Logging backends sit on the processing path of massive amounts of data, including user-controlled data. If a backend has a security vulnerability, the impact can be wide.

Let appropriate dependency management/BOM manage versions, track advisories, and update according to organizational security processes. Do not keep outdated logging libraries just because "logs still work".

## 32. Testing logging in Spring Boot

There are multiple levels of logging tests.

### Business tests should not over-rely on log text

For example, if an order-placement service needs to save data properly, a unit test should verify database interactions or business output rather than just asserting that `"Order created"` was logged.

Log messages can change based on operational needs. If text logs are treated as a business contract, every wording tweak can unnecessarily break tests.

### Verifying log output with OutputCaptureExtension

Spring Boot Test provides a utility to capture output in tests. Example:

~~~java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class LoggingExampleTest {

    private static final Logger log =
            LoggerFactory.getLogger(LoggingExampleTest.class);

    @Test
    void writesInfoLog(CapturedOutput output) {
        log.info("Inventory refresh completed");

        assertThat(output)
                .contains("Inventory refresh completed");
    }
}
~~~

To use this test, the project needs the `spring-boot-starter-test` dependency and `Logger`/`LoggerFactory` imports. Capture results also depend on the logging configuration in the test runtime; if the level is disabled or output goes to a different destination, assertions may not match.

### Testing specific appenders

When you need to inspect exact fields, levels, or events, you can attach a test appender to the backend within the test scope. For instance, Logback has `ListAppender`, though such tests depend on the Logback API and must clean up the appender afterward to avoid affecting other tests.

If the goal is solely testing business logic, avoid writing tests that unnecessarily depend on a backend.

### Testing configuration when switching backends

For a change from Logback to Log4j 2, you can have a smoke test or integration test that starts the application and verifies:

- SLF4J has a provider.
- The provider/backend matches the design.
- There are no multiple-provider warnings.
- Console/file appenders work.
- Required MDC/structured fields are present.

This is an appropriate type of infrastructure test when a system requires a consistent logging standard.

## 33. Identifying the actual backend at runtime

When an incident occurs, looking at config files is not enough. You need to know which provider was **actually** selected.

In a local diagnostic tool or test, you can print the logger factory class:

~~~java
Object factory = LoggerFactory.getILoggerFactory();

System.out.println(
        "SLF4J logger factory: "
                + factory.getClass().getName()
);
~~~

For example, with Logback, the factory is usually a class under `ch.qos.logback.classic`. With a Log4j 2 provider, it belongs to the corresponding implementation.

Do not turn this into a mandatory startup log in every application; it is a diagnostic tool when needed.

### Verify the actual JARs

When running from an IDE, tests, or a packaged JAR, the dependency graph can differ. A provider might exist in test scope yet be absent from the production artifact; conversely, another starter might pull an extra backend into runtime.

When identifying root causes, check the exact runtime classpath rather than only the POM/build.gradle file.

## 34. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| SLF4J reports no provider | Only `slf4j-api` is present or wrong provider version | Add the right compatible provider/backend |
| SLF4J reports multiple providers | Both Logback and Log4j 2 have providers | Choose one backend and exclude redundant dependencies |
| Log4j 2 backend does not work | Logback provider or reverse bridge remains | Inspect the logging starter and `runtimeClasspath` |
| Duplicate logs or loop | Two bridges routing in opposite directions | Keep only one direction toward the primary backend |
| `logback-spring.xml` has no effect | Selected backend is not Logback, file not loaded, or misconfigured | Verify provider and log config |
| `DEBUG` does not appear | Wrong logger level, filter, or package name | Check effective level and logger name |
| Logs still appear despite YAML level | Higher-precedence config source or native backend file overrides | Inspect property sources/config |
| No logs from JUL | Missing bridge handler or separate output | Check JUL-to-SLF4J integration |
| Missing logs after app exits | Async queue not flushed or collector failed | Design proper shutdown/flush/collector handling |
| Logs fill up disk | Missing rolling/retention or excessive INFO | Configure size/time limits and sampling |
| Logs lack correlation ID | MDC not set, missing from pattern, or lost across async | Check MDC/`TaskDecorator` |
| Response time increases | Logging I/O or expensive argument computation | Reduce volume, parameterize, use lazy evaluation |
| Secrets appear in logs | Dumping full objects/requests, missing redaction | Log only necessary fields and filter secrets |
| Commons Logging warnings | Multiple JCL artifacts/bridges providing classes | Inspect `spring-jcl` and dependency tree |
| Code compiles but runtime is NOP | SLF4J API is present but provider is missing | Inspect runtime artifact |
| Test logs differ from production | Different test dependencies/provider/levels | Compare `runtimeClasspath` by scope |

### When troubleshooting, identify which layer failed

Do not change everything at once. Ask:

1. Was the log line actually called?
2. Is the logger level enabled?
3. Was an SLF4J provider discovered?
4. Which backend was actually selected?
5. Which direction are bridges pointing?
6. Which appenders/handlers are configured?
7. Where is output being written: file, console, or collector?
8. Is any filter, async queue, or retention preventing the event from appearing?

Answering in this order distinguishes code bugs, dependency issues, configuration errors, and log collection infrastructure issues.

## 35. Real-world scenario: an application with libraries using multiple APIs

Suppose a Spring Boot service uses:

- Business code calling SLF4J.
- A legacy library calling JUL.
- Another library calling the Log4j 2 API.
- Spring Framework using Spring JCL.

If Logback is chosen as the backend, the desired flow is:

~~~text
Business code --------> SLF4J API -----+
                                        |
JUL library -- JUL-to-SLF4J bridge ----+
                                        |
Log4j API library -- log4j-to-slf4j ----+----> Logback
                                        |
Spring JCL ------- appropriate adapter -+
                                              |
                                              v
                                     Console / file / collector
~~~

The exact wiring of Spring JCL depends on the classpath and configuration, but the goal is for different logging sources to converge on one final backend.

If the organization later migrates to Log4j 2:

- Remove the Logback provider.
- Add the Spring Boot Log4j 2 starter.
- Use the version-appropriate SLF4J → Log4j 2 provider.
- Do not keep the reverse Log4j API → SLF4J bridge that risks a loop.
- Verify JUL and Spring JCL continue routing under the new configuration.
- Migrate native configuration files to the new backend or use Boot-supported properties.

Business code still uses:

~~~java
log.info("Order {} created", orderId);
~~~

This is the practical benefit of a facade: **business code rarely has to change when logging infrastructure changes**.

## 36. Choosing an operations-friendly logging architecture

For a typical Spring Boot application, you can apply these principles:

1. **Use the SLF4J API in business code.** Do not create direct dependencies on appenders/backends unless necessary.
2. **Choose only one primary SLF4J provider.** Do not let Logback and Log4j 2 compete.
3. **Let Spring Boot manage versions and the logging starter** whenever possible.
4. **Use property configuration for simple needs.** For example, levels per package and basic output.
5. **Use native backend files when multiple appenders/filters/rolling policies are needed.**
6. **Understand that SLF4J 1.7 bindings differ from SLF4J 2.x providers.**
7. **Configure bridges in one direction.** Avoid loops between SLF4J, JUL, and Log4j API.
8. **Use parameterized logging.** Avoid string concatenation and expensive evaluations when the level is disabled.
9. **Use INFO for operational milestones, DEBUG/TRACE for detailed diagnostics.**
10. **Log exceptions with Throwable when a stack trace is needed**, while avoiding repeated logging across multiple layers.
11. **Protect sensitive data.** Do not log tokens, passwords, or full objects containing personal data.
12. **Attach correlation IDs or trace context** using mechanisms with clear cleanup/propagation.
13. **Measure logging volume, retention, and performance impact.**
14. **Inspect the runtime classpath** whenever providers, bridges, or backends behave unexpectedly.
15. **Test logging infrastructure configuration separately**, without making every business test depend on log text.
16. **Do not use logs as a business source of truth.** Mandatory auditing requires durable data storage and proper access control.

## Conclusion

A **logging facade** separates the API that application code uses from the library that actually processes logs. **SLF4J** provides a unified API such as `Logger` and `LoggerFactory`; the **provider** connects this API to a backend; **Logback**, **Log4j 2**, or another implementation determines levels, formats, and destinations. In typical Spring Boot applications using default starters, Logback is the common backend; Spring Boot also supports switching to Log4j 2 when dependencies are configured properly.

The hardest part is not calling `log.info(...)`, but understanding the **classpath and routing direction**. SLF4J 1.7 uses legacy bindings; SLF4J 2.x uses providers. Adding multiple providers or combining bidirectional bridges can cause warnings, ignored configurations, or logging loops. Therefore, when logs do not behave as expected, determine which API is called, which provider is actually selected, which backend is running, and which appenders receive the output.

A good logging system has a stable API, operations-friendly configuration, sufficient context for investigation, reasonable cost, and no sensitive data leakage. Keeping these principles allows a Spring Boot application to evolve its logging infrastructure while keeping business code clean and reliable.

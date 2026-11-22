# Package-Based Log Separation in Java: Logger Hierarchy, Routing, and Duplicate Control

## 1. Purpose and Scope

In a Java application, packages typically represent functional groups such as orders, payments, external integrations, and background jobs. **Package-based log separation** is the practice of using structured logger names to apply **different log levels, filters, or output destinations** to each group, helping you observe the right component without increasing system-wide noise.

For example, you might want:

- `com.acme.orders` to log at DEBUG when investigating ordering business logic, while most of the application logs at INFO.
- `com.acme.payments` to write to a separate file or pipeline for easier access control and retention management.
- `com.acme.integration` to use WARN to reduce log volume from high-traffic adapters.
- The remaining packages to continue going through a shared appender to maintain operational signals.

After this lesson, you will be able to distinguish **level-based separation** from **destination-based separation (routing)**; understand logger inheritance, appender additivity, filters, and the scope of each configuration; build a standalone Java 17 example using only JUL; configure Logback, Log4j2, and Spring Boot; and test your setup to prevent duplicate, lost, or misrouted logs.

> The core idea is **logger names corresponding to packages**, not partitioning data by parsing package name strings out of log messages to classify them manually. Choosing appropriate logger names lets the framework route events before formatters or sinks process them.

## 2. How Are Packages and Logger Names Related?

In Java, a package is a namespace declared in source code:

~~~java
package com.acme.orders;

public class OrderService {
    // ...
}
~~~

When a logger is named after the fully qualified class name, the logger name is typically `com.acme.orders.OrderService`. SLF4J example:

~~~java
// Illustration in an application that already has SLF4J and a backend.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
~~~

This naming convention allows configuration on `com.acme.orders` to apply to the logger inside `com.acme.orders.OrderService` and to subpackages such as `com.acme.orders.workflow`.

Logging systems typically organize loggers by **dot-separated name segments**, for example:

~~~text
root
└── com
    └── com.acme
        ├── com.acme.orders
        │   ├── com.acme.orders.OrderService
        │   └── com.acme.orders.workflow.CheckoutFlow
        ├── com.acme.payments
        │   └── com.acme.payments.PaymentService
        └── com.acme.integration
            └── com.acme.integration.HttpAdapter
~~~

This diagram illustrates **logical name relationships**. The backend does not necessarily create a physical Logger object for every intermediate node; parent lookup or matching configuration mechanisms can use the nearest existing logger or config.

**Note:** `com.acme.order` and `com.acme.orders` are not the same package, and configuring `com.acme.order` does not automatically mean "every logger with the character prefix com.acme.order". Always verify exact dot-separated name segments. In addition, loggers **can be given arbitrary names**; if code uses `getLogger("business")`, package configuration on `com.acme.orders` will not control that logger. Therefore, you should follow a convention of obtaining loggers by class or package.

## 3. Three Types of "Log Separation" to Distinguish

| Goal | What changes? | Example | What is needed? |
| --- | --- | --- | --- |
| **Adjust level by package** | Which DEBUG/INFO/WARN events qualify to be emitted. | DEBUG for `com.acme.orders`, INFO for the rest. | Logger level; typically configured via properties/YAML or XML. |
| **Route by package** | Which appender/handler a qualifying event goes to. | Orders to `orders.log`, Payments to `payments.log`. | Appender/handler configuration, logger attachment, additivity. |
| **Classify at the collector** | Tagging/filtering/searching after the event has been emitted. | Dashboard filtering `logger_name` starting with `com.acme.orders`. | Structured logs, collector, and query rules. |

Setting `logging.level.com.acme.orders=DEBUG` **does not automatically create** `orders.log`. Configuring a separate appender **does not guarantee** DEBUG lines either if the effective level is still INFO. Conversely, a collector can create multiple indexes from the same log stream; that is **collector-tier routing**, which is different from splitting streams inside the JVM.

### A Typical Event Processing Flow

~~~text
Logger call (by class / package name)
                 │
                 ▼
     Does logger level allow it?
                 │
          ┌──────┴──────┐
         No            Yes
          │             │
       Ignored     Event created
                        │
                        ▼
             Logger filter / backend rules
                        │
                        ▼
             Selected Appender/Handler
                        │
                        ▼
           Appender filter, encoder, sink
                        │
                        ▼
           Console / file / collector
~~~

This is a conceptual model: Logback, Log4j2, and JUL each have their own sequence and terminology. **Do not assume that the parent logger's level is always re-checked at every step up the hierarchy.** In Logback/Log4j2, appender inheritance rules and effective level resolution rules are separate mechanisms.

## 4. Logger Hierarchy and Log Level Inheritance

An example level configuration:

~~~text
root                         INFO
com.acme.orders              DEBUG
com.acme.payments            WARN
com.acme.integration         (unset, inherits INFO)
~~~

Expected behavior when no other filters are present:

| Emitting logger | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- |
| `com.acme.orders.OrderService` | Yes | Yes | Yes | Yes |
| `com.acme.payments.PaymentService` | No | No | Yes | Yes |
| `com.acme.integration.HttpAdapter` | No | Yes | Yes | Yes |

The **effective level** is the level applied to a logger after considering its direct configuration and inheritance from the appropriate ancestor. A child logger without its own level typically uses the level of its nearest configured parent.

A package containing many classes **does not need** a separate configuration line for each class. That is why package-level rules are easier to maintain than per-class configuration, unless you need to investigate a very specific component.

Key points to remember:

- **Level** inheritance determines whether a log event is created/accepted at the source logger.
- **Appender** inheritance determines which destinations an accepted event is sent to.
- **Appender filters/thresholds** can still drop events, so having `DEBUG` accepted by a logger does not mean every sink will write DEBUG lines.
- A broad package logger name like `com.acme` can affect hundreds of classes; prefer a narrow scope when increasing verbosity.

## 5. Additivity: A Common Cause of Duplicate Logs

In Logback and Log4j2, **additivity** means an event from a child logger is sent to its own appenders **and** to the appenders on its ancestor chain. The default for common loggers is `true`.

Suppose:

~~~text
root                          -> CONSOLE
com.acme.orders               -> ORDERS_FILE, additivity=true
com.acme.orders.OrderService  -> logs INFO
~~~

Events from `OrderService` will go to `ORDERS_FILE` **and** `CONSOLE`, because the event also propagates through root. This may be intentional if you want orders logs to appear in both the combined log and a dedicated file.

If the goal is **to write orders only to a separate file**, set:

~~~text
root                          -> CONSOLE
com.acme.orders               -> ORDERS_FILE, additivity=false
com.acme.orders.OrderService  -> ORDERS_FILE
~~~

The event goes to the appenders on the orders branch and then **stops before root**. Setting `additivity=false` on a logger that has **no appropriate appender** can cause events to reach no destination at all; always verify appenders before blocking inheritance.

### When Are Logs Truly Duplicated?

- **One line in console and one line in a separate file:** may be **delivering one event to two intended destinations**.
- **Two identical lines in the same console/file:** usually caused by attaching the same destination at multiple logger levels, additivity, or two pipelines collecting/writing the same record.
- **Multiple records with the same message from two actual calls:** not necessarily a routing bug; inspect the logging call sites and trace/correlation IDs.

Do not fix duplicate logs by disabling the root logger system-wide. Draw the appender diagram and trace the path of **one specific event**.

## 6. Standalone Java 17: Routing Packages to Two Files with JUL

`java.util.logging` (JUL) is built into JDK 17, so you can learn the mechanics right away without installing Logback or Log4j2. JUL uses dot-hierarchical **Loggers** and **Handlers** to write logs. When a logger has `setUseParentHandlers(false)`, its records will not continue propagating to parent logger handlers.

The following program:

1. Creates package-level loggers `academy.orders` and `academy.payments`.
2. Attaches a separate `FileHandler` to each package.
3. Allows `FINE` on orders, but only `INFO` and above on payments.
4. Uses `setUseParentHandlers(false)` so an extra copy is not sent to the root handler.
5. Closes the handlers before reading the files so the results can be verified.
6. Writes ASCII messages with a fixed format so stdout is not affected by timestamps or locale.

Save as **PackageRoutingDemo.java**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class PackageRoutingDemo {

    private static FileHandler createFileHandler(String file)
            throws IOException {
        FileHandler handler = new FileHandler(file, false);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setLevel(Level.ALL);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + record.getLoggerName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        return handler;
    }

    private static void configurePackage(
            Logger packageLogger, Level level, Handler handler) {
        packageLogger.setLevel(level);
        packageLogger.setUseParentHandlers(false);
        packageLogger.addHandler(handler);
    }

    private static void printFile(String file) throws IOException {
        System.out.println(file + ":");
        for (String line : Files.readAllLines(
                Path.of(file), StandardCharsets.UTF_8)) {
            System.out.println(line);
        }
    }

    public static void main(String[] args) throws Exception {
        // Keep strong references to both package loggers in main.
        Logger ordersPackage = Logger.getLogger("academy.orders");
        Logger paymentsPackage = Logger.getLogger("academy.payments");

        FileHandler ordersFile = createFileHandler("orders.log");
        FileHandler paymentsFile = createFileHandler("payments.log");

        try {
            configurePackage(ordersPackage, Level.FINE, ordersFile);
            configurePackage(paymentsPackage, Level.INFO, paymentsFile);

            // Class-named loggers are created under the two packages.
            Logger orders = Logger.getLogger(
                    "academy.orders.OrderService");
            Logger payments = Logger.getLogger(
                    "academy.payments.PaymentService");

            orders.fine("order-debug");
            orders.info("order-created");
            payments.fine("payment-debug");
            payments.warning("payment-delayed");
        } finally {
            ordersPackage.removeHandler(ordersFile);
            paymentsPackage.removeHandler(paymentsFile);
            ordersFile.close();
            paymentsFile.close();
        }

        printFile("orders.log");
        printFile("payments.log");
    }
}
~~~

Compile and run in a directory **with write permissions**, using JDK 17 or later:

~~~bash
javac PackageRoutingDemo.java
java PackageRoutingDemo
~~~

**Expected stdout**, when running a standalone instance and the file paths are not held by another process:

~~~text
orders.log:
FINE academy.orders.OrderService order-debug
INFO academy.orders.OrderService order-created
payments.log:
WARNING academy.payments.PaymentService payment-delayed
~~~

The generated files contain, respectively:

**orders.log**

~~~text
FINE academy.orders.OrderService order-debug
INFO academy.orders.OrderService order-created
~~~

**payments.log**

~~~text
WARNING academy.payments.PaymentService payment-delayed
~~~

The `payment-debug` line does not appear because the `academy.payments` logger blocks `FINE` before it reaches the FileHandler. Child loggers inherit levels from their respective package loggers. `setUseParentHandlers(false)` prevents records from continuing up to the root handler; as a result, the demo does not print extra logs through JUL's default console handler.

**Things to keep in mind when applying this:**

- `FileHandler` requires directory write permissions and may create `.lck` files while running. The program above uses `append=false` so each run's output does not mix with old logs; **do not use this for production logs that must preserve history**.
- FileHandler may use a different naming pattern when a file name is locked by another instance. Therefore, the sample output assumes no other process is holding the same file.
- The example configures logging programmatically at startup for ease of learning. In production, use your framework/backend's configuration mechanism and do not mutate global loggers arbitrarily while requests are running.
- JUL has both a **Logger level** and a **Handler level**. If a handler has a `WARNING` threshold, then even if the logger accepts `FINE`, the handler will not output `FINE` events. In the demo, the handler is set to `ALL` so the threshold is governed by the package logger.
- `FileHandler` is closed in `finally` to release resources. If a sink encounters an I/O error, you must observe the `ErrorManager`/infrastructure mechanism and account for potential event loss; this example is not meant to guarantee data durability.
- In a real application, naming a logger after a class like `academy.orders.OrderService` is a **convention**, not a requirement from the Java compiler that such a class or package exist in the demo file itself.

## 7. Logback Configuration: One File per Package

Logback Classic is commonly used behind SLF4J. A `logback.xml` configuration can define loggers by package and attach corresponding appenders.

Example placed at **src/main/resources/logback.xml** in an application using Logback:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ORDERS_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/orders.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="PAYMENTS_FILE" class="ch.qos.logback.core.FileAppender">
        <file>logs/payments.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.acme.orders" level="DEBUG" additivity="false">
        <appender-ref ref="ORDERS_FILE"/>
    </logger>

    <logger name="com.acme.payments" level="INFO" additivity="false">
        <appender-ref ref="PAYMENTS_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Routing results for the configuration above:**

| Logger | Path | Level |
| --- | --- | --- |
| `com.acme.orders.OrderService` | `ORDERS_FILE` only → `logs/orders.log` | DEBUG and above |
| `com.acme.payments.PaymentService` | `PAYMENTS_FILE` only → `logs/payments.log` | INFO and above |
| `com.acme.inventory.StockService` | Inherits root → `CONSOLE` | INFO and above |

Because both package loggers set `additivity=false`, logs from the orders and payments branches no longer propagate up to `CONSOLE` on root. This **can cause loss of visibility on container stdout** if your system only collects logs from stdout/stderr.

If the operational requirement is **both combined logs on console and separate files**, you can add `<appender-ref ref="CONSOLE"/>` to each package logger that has `additivity="false"`. That way each event reaches the console and its dedicated file **once each**, without re-enabling additivity. Another option is `additivity=true` with a dedicated file appender and root console, as long as you do not attach a duplicate console appender to the child logger.

This is a **learning example** without a rolling policy. Production setups need to consider **RollingFileAppender**, rollover, retention, disk quota, write permissions, and collector strategy. The `logs/` path is relative to the current working directory; in containers/Kubernetes, define volumes, persistence, and log collection before using separate files.

### 7.1. When You Only Need DEBUG Level by Package

If all logs still need to go to a single shared console appender, the minimal configuration is simply:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.acme.orders" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

The orders logger inherits the CONSOLE appender from root via the default `additivity=true`, but uses the DEBUG threshold. Other packages inherit INFO from root. **This is per-package level tuning, not per-package sink separation.**

### 7.2. Does Root INFO Prevent DEBUG from Orders from Reaching the Root Appender?

In Logback configuration, a DEBUG event permitted by **the `com.acme.orders` logger** can reach root's appender if additivity allows it. The root INFO level **is not treated as a second threshold filter** just because the appender is attached to root. If you want an appender to accept only INFO and above, place an appropriate filter/threshold **on the appender itself**. This is a common point of confusion when enabling DEBUG for a child package.

## 8. Log4j2: Routing with LoggerConfig and AppenderRef

Log4j2 uses `LoggerConfig` with hierarchical names, levels, additivity, and appender references. Example **log4j2.xml** for an application that already includes Log4j Core:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %logger - %msg%n"/>
        </Console>

        <File name="ORDERS_FILE" fileName="logs/orders.log" append="true">
            <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </File>

        <File name="PAYMENTS_FILE" fileName="logs/payments.log" append="true">
            <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
        </File>
    </Appenders>

    <Loggers>
        <Logger name="com.acme.orders" level="DEBUG" additivity="false">
            <AppenderRef ref="ORDERS_FILE"/>
        </Logger>

        <Logger name="com.acme.payments" level="INFO" additivity="false">
            <AppenderRef ref="PAYMENTS_FILE"/>
        </Logger>

        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

The semantics are similar to Logback: loggers matching the orders package and its child classes use ORDERS_FILE, loggers in the payments branch use PAYMENTS_FILE, and other loggers use root CONSOLE. Each LoggerConfig can have multiple AppenderRefs; `additivity=false` prevents sending events to appenders in parent configurations.

**Note when switching libraries:** Log4j 1.x and Log4j2 have different syntax and configuration; do not copy Logback or Log4j 1.x configs expecting Log4j2 to understand them automatically. Verify that the actual backend, dependencies, and config path are loaded.

To make orders logs appear in both a dedicated file and the shared console, design appender references and additivity explicitly just as in Logback. In Log4j2, filters can live on the logger, appender, or AppenderRef; check **all filters** whenever observed log levels do not match expectations.

## 9. Spring Boot: Per-Package Level vs. Per-Package Routing

In a Spring Boot application using the default logging starter, logger levels are typically controlled directly via **application.properties**:

~~~properties
logging.level.root=INFO
logging.level.com.acme.orders=DEBUG
logging.level.com.acme.payments=WARN
logging.level.com.acme.integration=ERROR
~~~

Or **application.yml**:

~~~yaml
logging:
  level:
    root: INFO
    com.acme.orders: DEBUG
    com.acme.payments: WARN
    com.acme.integration: ERROR
~~~

This adjusts **verbosity by package**. It **does not automatically generate** three files or three separate collectors. If you want appender-based routing, configure the Logback/Log4j2 backend, or split streams by the logger name field at the collector.

When using Logback in Boot and you need fine-grained routing control, place your configuration in **logback-spring.xml** to use Boot's proper integration hooks. If you have multiple `application-{profile}.yml` files, identify which overrides are active. For Log4j2, use `log4j2-spring.xml` when Boot integration is needed.

### Separating Levels by Environment Without Mixing Policies

Base configuration example:

~~~properties
# application.properties
logging.level.root=INFO
logging.level.com.acme.orders=INFO
~~~

Dev-specific configuration:

~~~properties
# application-dev.properties
logging.level.com.acme.orders=DEBUG
~~~

Prod-specific configuration:

~~~properties
# application-prod.properties
logging.level.com.acme.orders=INFO
~~~

Set the active profile at startup from the appropriate deployment config source. If the production process receives `LOGGING_LEVEL_COM_ACME_ORDERS=DEBUG` or a higher-precedence override, the effective value can differ from the prod file. Always check the **effective config**, rather than drawing conclusions solely from repository files.

Avoid enabling root DEBUG in production when you only need to investigate the orders package. Enable a narrow branch, time-box it, monitor volume, and ensure messages do not contain secrets or PII.

### When Some Logs Do Not Follow the Expected Package

- The application uses `LoggerFactory.getLogger("business")` instead of a class name.
- A third-party library uses its own logger names, such as `org.hibernate.SQL`, `io.netty`, or `org.springframework`; they are not under the `com.acme` package.
- Logging is routed through a bridge/provider different from the backend you are editing.
- A child logger or intermediate package has a different level/additivity setting.
- The collector transforms or abbreviates the `logger_name` field, while the underlying backend still routes by the real logger name.
- Some frameworks use logger category names that do not align exactly with Java packages.

Investigate using **the actual logger name printed in the event**, then match it against the configuration.

## 10. Package Separation in JUL with Properties

Besides programmatic configuration, JUL can read a config file with levels per logger name. Example **logging.properties**:

~~~properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

com.acme.orders.level=FINE
com.acme.payments.level=WARNING
~~~

Start the JVM with:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.acme.Main
~~~

This is **illustrative syntax for a compiled application** `com.acme.Main` located in `out`, not a command to run the section 6 example directly.

With the configuration above, the orders level accepts FINE, payments accepts WARNING and above, and root defaults to INFO. ConsoleHandler is set to ALL so it does not accidentally block FINE logs from orders. If the handler is set to INFO, even when the orders logger has an effective level of FINE, FINE records can still be blocked at the handler.

**Full per-package file routing in JUL** generally requires creating/registering handlers and managing **useParentHandlers** carefully, or using a configuration mechanism compatible with LogManager/the application. The section 6 example illustrates this path more clearly than assuming that simply adding `com.acme.orders.level=FINE` will automatically create `orders.log`.

## 11. Common Routing Strategies

| Strategy | Best suited when | Watch out for |
| --- | --- | --- |
| **Single console, different levels per package** | Containerized apps, centralized logs, primary need is noise reduction. | Easy to operate; per-package levels still need careful control. |
| **Shared console + dedicated file for critical packages** | Need quick access to specific logs while keeping combined logs. | One event can land in two sinks; design additivity and account for storage cost. |
| **Fully separate file/appender** | Strict access control, retention, or dedicated pipeline requirements. | Disabling additivity can drop logs from centralized console; requires a dedicated collector. |
| **Single structured stream + split at collector** | Many packages, want flexible routing/retention outside the JVM. | Attach consistent logger_name, service, environment, traceId and secure the transport path. |
| **Marker/MDC-based filtering beyond packages** | Cross-cutting event types across packages (audit, security, business type). | Packages alone may not suffice; requires clear schema and rules. |

Do not assume splitting into files is automatically better. In systems with container logging and a centralized collector, **a single JSON stream with full logger names** is often simpler than managing multiple files inside a container. However, when a group of events has special retention or access-control policies, dedicated routing may be necessary. Choose based on observability and retention requirements, not simply because the codebase has many packages.

### Should Packages Be Used to Route Audit/Security Logs?

Packages partition code by **where the code is written**, whereas audit/security classifies events by **event semantics**. An audit event can originate from many packages; conversely, a single package can contain both debug and audit logs. If you need to guarantee that all audit events follow a dedicated policy, designing **markers, dedicated logger categories, structured fields, or a separate event pipeline** is more reliable than relying on packages alone.

## 12. Testing Routing to Avoid Lost and Duplicate Logs

A useful test matrix:

| Test | Check | Expected outcome |
| --- | --- | --- |
| **Package A and B** | Emit an INFO event in each branch. | Each event reaches its configured sink with no cross-contamination. |
| **Subpackage** | Log in `com.acme.orders.workflow.CheckoutFlow`. | Inherits `com.acme.orders` rules if no specific override exists. |
| **Similarly named packages** | Log in `com.acme.order` and `com.acme.orders`. | No confusion between the two branches under namespace configuration. |
| **Level below threshold** | Log DEBUG in payments with WARN threshold. | Event is filtered by policy and does not appear as INFO/WARN. |
| **Additivity=true** | Attach file on child branch, console on root. | Event appears in both file and console if that is the intended design. |
| **Additivity=false** | Block propagation to root. | Event does not reach root appenders, but still reaches child branch appenders. |
| **Appender with no sink** | Disable additivity but forget child appender. | Test detects lost logs and fails the configuration. |
| **Sink failure** | Read-only file, disk full, or collector unreachable. | Error signal and handling policy are observable, no silent data loss. |
| **Multiple threads** | Log from thread pools, concurrent requests. | Level/routing by logger name remains correct; MDC/trace context must be handled separately. |
| **Runtime config change** | Reload or change level via management API. | Effective config after reload is correct, without adding duplicate appenders. |

When tests need to compare event counts, use a **unique message or event ID** and verify both sides: the target sink has one copy, and unrelated sinks have zero copies. JSON logs with `logger_name`, `level`, `event_id`, and `trace_id` make verification and querying clearer.

### Diagnosing a Duplicate or Lost Event

~~~text
Did the log call actually execute?
       │
       ▼
What is the actual logger name?
       │
       ▼
Does the effective level allow the event?
       │
       ▼
What is the LoggerConfig / nearest parent?
       │
       ▼
Which Appender/Handler is attached?
       │
       ▼
Does additivity / useParentHandlers propagate to root?
       │
       ▼
Do filter, threshold, encoder, and sink let it pass?
       │
       ▼
Does the collector receive, rename, duplicate, or drop the record?
~~~

You must inspect **both the JVM/backend configuration and the external pipeline**. A record duplicated at the collector may not be caused by additivity; conversely, Logback sending twice to the same appender can make the collector look like it received two separate events.

## 13. Interaction with MDC, Trace Context, and Async Logging

**Package-based separation** relies on the **logger name**. **MDC and trace context** hold information tied to a request or execution flow, used to correlate logs across packages and services. The two mechanisms complement each other rather than replacing each other:

- A single request may traverse orders, inventory, and payments; records carry the **same traceId** while going to different sinks based on logger name.
- Package-based log separation does not automatically propagate MDC across `CompletableFuture`, `ExecutorService`, or message consumers. If a logger in a callback lacks a traceId, fix context propagation.
- If the backend uses **AsyncAppender/AsyncLogger**, events may be enqueued and written later by a worker thread. Check the backend's MDC/thread-name snapshot mechanism; do not infer worker behavior from the logger name.
- Routing a record to multiple sinks does not mean every sink has persisted it durably. Queue, disk, or collector failures can still drop logs.
- For sensitive events, restrict messages and fields at the source. Moving them to a separate file does not automatically encrypt or protect their contents.

The following structured event example uses logger name for routing and traceId for tracing:

~~~json
{
  "level": "INFO",
  "logger_name": "com.acme.orders.OrderService",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "event": "order.created",
  "message": "Order created"
}
~~~

This is a **sample payload**, not the output of the Java program in section 6. `trace_id` should come from a valid tracing context when available, rather than hardcoding a fixed value just to make logs look complete.

## 14. Common Mistakes

**1. Setting only the level and assuming files are separated.** Level decides whether an event is accepted; splitting files/sinks requires configuring appenders/handlers or collector routing.

**2. Using additivity=false without attaching a child appender.** Records will not reach root and will have no sink on the child branch either.

**3. Attaching the same CONSOLE appender to both child and root while keeping additivity=true.** An event can be written twice to the same destination. Choose one clear path.

**4. Misunderstanding root INFO.** In Logback/Log4j2, a DEBUG event permitted by a child logger can still be processed by root's appender if additivity allows it. If you need separate filtering on the appender, configure a threshold/filter on the appender or AppenderRef.

**5. Setting overly broad package rules.** Enabling DEBUG on `com.acme` in production just to diagnose `com.acme.orders.payment` can spike log volume and data exposure risk.

**6. Assuming every logger name matches a package name.** APIs allow arbitrary names; third-party library loggers may use different namespaces. Always observe the actual names in logs.

**7. Looking only at the file name and forgetting write permissions.** Paths like `logs/orders.log` depend on the working directory, filesystem permissions, and container volumes; valid XML can still fail to write.

**8. Using multiple files in a container when the collector only reads stdout.** Disabling additivity to split files can cause the application to lose logs in the central dashboard. Check the collection path.

**9. Omitting rotation/retention.** Per-package files multiply file count and storage cost. Production requires quotas, rotation, retention, and disk monitoring.

**10. Using packages to decide which data is audit data.** Security/audit events can appear across many packages, so semantic classification usually needs dedicated markers or fields.

**11. Mixing backends.** Editing `logback.xml` does nothing if the runtime actually uses Log4j2, JUL, or another SLF4J provider. Check the runtime classpath and bootstrap logging.

**12. Not testing subpackages and similar package names.** Testing a single class can miss child loggers inheriting the wrong level or sibling branches routing to the wrong sink.

## 15. Practice Exercises

1. Run `PackageRoutingDemo.java`, then open **orders.log** and **payments.log**. Explain why `payment-debug` was filtered out while `order-debug` was written.
2. Change `ordersPackage.setUseParentHandlers(false)` to `true` in the demo. Observe how `orders` can continue propagating to parent/root handlers if root has a handler configured. Compare stdout/stderr and the files; understand the path rather than just counting lines.
3. Change `ordersPackage`'s level from `FINE` to `WARNING`. Verify that the orders file no longer contains `FINE` and `INFO`.
4. In Logback, configure root INFO + CONSOLE and logger `com.acme.orders` DEBUG + ORDERS_FILE. Try both `additivity="true"` and `additivity="false"`, predicting which destinations each event will appear in before running.
5. If using Spring Boot, set `logging.level.com.acme.orders=DEBUG` in the dev profile and INFO in prod; run each profile in a test environment, check the effective level, and ensure DEBUG is not enabled unintentionally.
6. Add a logger `com.acme.orders.workflow.CheckoutFlow` and a logger `com.acme.order.OrderService`. Check which branch is routed like orders and why.
7. Design a test that catches **duplicate events in a single sink** using a unique `event_id` and a test that catches **lost events** when `additivity=false` without an appender.

## 16. Key Takeaways

Package-based log separation is a technique for **routing and classifying by logger name**. There are two distinct decisions: **which events are emitted** (levels/filters) and **where events are delivered** (appenders/handlers, additivity, collectors). Class-based logger names let package-level rules cover many child classes; additivity lets you inherit destinations or stop propagation at package boundaries. When designing, trace the path of a single event, determine the expected record count at each sink, and verify the negative cases too: logs must not be lost or sent to the wrong place.

### Official References

- Java SE 17 — `java.util.logging.Logger`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Logback Architecture — Logger hierarchy and appender additivity: https://logback.qos.ch/manual/architecture.html
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Log4j2 Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Log4j2 Architecture and appender additivity: https://logging.apache.org/log4j/2.x/manual/architecture.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
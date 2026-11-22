# Per-Logger Configuration in Java Logging

## 1. What is per-logger configuration?

In a Java application, a **logger** is a named logging object. Its name is typically the fully qualified name of a class or package, for example:

- com.example.shop.payment.PaymentService
- com.example.shop.repository.OrderRepository
- org.springframework.web
- org.hibernate.SQL

**Per-logger configuration** means setting the logging level and, when needed, a dedicated output destination for a specific logger name or logger branch. This approach increases detail in the exact area under investigation while keeping overall log volume within reasonable limits.

For example, suppose an e-commerce system is experiencing payment errors. You can keep **root = INFO**, enable **com.example.shop.payment = DEBUG**, and set **com.example.shop.repository = WARN**. As a result, payment processing code is logged in detail for diagnosis, data access logs only warnings and errors, and other areas continue following the general policy.

Per-logger configuration is especially useful when:

- Only a single class or package needs DEBUG/TRACE logging to investigate an issue.
- A third-party library logs too much INFO/DEBUG output and needs its level lowered individually.
- A specific log stream, such as audit logs, needs to go to a separate appender/destination.
- Logging levels need to be adjusted temporarily in testing or production environments.

Do not confuse a **logger name** with a correlation ID, thread name, or log file name. A single logger is typically reused across many requests; a correlation ID is a property of the execution flow used to correlate log lines.

## 2. Distinguishing logging API, logger, and logging backend

In a Java project, three conceptual layers are commonly involved:

| Component | Role | Example |
| --- | --- | --- |
| Logging API / facade | Provides logging calls in application code | SLF4J, java.util.logging (JUL) |
| Logger | Named object used to decide whether an event is enabled at a given log level | com.example.shop.payment.PaymentService |
| Backend / implementation | Handles configuration, filters, appenders, formatters, and log output | Logback Classic, Log4j 2 Core, JUL |

With SLF4J, code is typically written as:

~~~java
// Illustrative snippet in the PaymentService class,
// requires the SLF4J dependency; not a standalone Java program.
private static final org.slf4j.Logger log =
        org.slf4j.LoggerFactory.getLogger(PaymentService.class);

public void pay(String orderId) {
    log.info("Paying order {}", orderId);
    log.debug("Payment workflow entered for {}", orderId);
}
~~~

The logger name here defaults to the fully qualified name of the **PaymentService** class, including its package. SLF4J forwards events to the configured backend; the XML/Properties syntax for setting levels and appenders belongs to the backend or runtime environment, not to the `LoggerFactory.getLogger` method itself.

If the application already uses SLF4J + Logback, configure Logback; if it uses SLF4J + Log4j 2, configure Log4j 2 accordingly. Avoid accidentally putting multiple conflicting logging providers/bindings on the classpath. JUL is both the API and implementation built into the JDK, making it useful for demonstrating general behavior and running standalone examples.

## 3. Logger name hierarchy and inheritance rules

In Logback and Log4j 2, logger names are organized into dot-separated segments. **Root** is the top-level logger. For example:

~~~text
ROOT
  └── com
      └── com.example
          └── com.example.shop
              ├── com.example.shop.payment
              │   └── com.example.shop.payment.PaymentService
              ├── com.example.shop.repository
              │   └── com.example.shop.repository.OrderRepository
              └── com.example.shop.audit
~~~

The hierarchy above is a logical model; intermediate parent loggers do not need to be explicitly instantiated in code. Hierarchy is based on **name**, not on Java class inheritance (`extends`). A similar name with a different segment or different letter casing may not belong to the intended branch.

If a child logger **is not assigned its own level**, it uses the **effective level** from its nearest ancestor that has a configured level. For example:

| Logger | Declared level | Effective level |
| --- | --- | --- |
| ROOT | INFO | INFO |
| com.example.shop | (inherited) | INFO |
| com.example.shop.payment | DEBUG | DEBUG |
| com.example.shop.payment.PaymentService | (inherited) | DEBUG |
| com.example.shop.repository | WARN | WARN |
| com.example.shop.repository.OrderRepository | (inherited) | WARN |
| com.example.shop.audit | ERROR | ERROR |

Configuration at the package level typically affects many classes in that branch; configuration at the class name level has a narrower scope. **An explicit level on a child logger takes precedence over an inherited level from a parent logger**. Changing root does not override explicit levels on child branches.

For example, if **com.example.shop = INFO** and **com.example.shop.payment = DEBUG** are configured, DEBUG calls from `PaymentService` are enabled. If **com.example.shop.payment.PaymentService = ERROR** is also set, that class will emit only ERROR events according to its own threshold, while other payment classes still follow the package's DEBUG level.

## 4. Log levels and level evaluation

In Logback or Log4j 2, common levels are ordered by severity:

~~~text
TRACE < DEBUG < INFO < WARN < ERROR
~~~

An event is enabled if its level is **equal to or more severe than** the effective level of the logger emitting the event.

| Effective level | TRACE | DEBUG | INFO | WARN | ERROR |
| --- | --- | --- | --- | --- | --- |
| TRACE | Yes | Yes | Yes | Yes | Yes |
| DEBUG | No | Yes | Yes | Yes | Yes |
| INFO | No | No | Yes | Yes | Yes |
| WARN | No | No | No | Yes | Yes |
| ERROR | No | No | No | No | Yes |
| OFF | No | No | No | No | No |

Note: this table shows **initial filtering at the logger**. An event that passes this step can still be blocked by an appender filter, threshold, sampling, I/O error, or output pipeline configuration. `ALL`/`OFF` levels, `FATAL`, and framework-specific level names can vary across frameworks; do not copy this table verbatim for JUL.

A very important distinction:

> **Logging already enabled at a child logger is not filtered a second time by a parent logger simply because the parent has a stricter level**, when the event is passed up to ancestor appenders via Logback/Log4j 2 additivity. Appenders and filters along the receiving pipeline can still filter independently.

For example, with `ROOT=INFO`, `payment=DEBUG`, and a console appender with no extra filter: a DEBUG line emitted from `PaymentService` can reach `ROOT`'s console appender via additivity. Setting `ROOT=INFO` is not enough to block DEBUG lines from a child logger explicitly configured as DEBUG. This is the difference between **inheriting an effective level** and **propagating events to parent appenders**.

## 5. Level, appender, filter, and additivity are separate decisions

Typically, an event goes through the following steps:

~~~text
logger.debug("...") call
          |
          v
Determine logger name and effective level
          |
          v
Is DEBUG enabled on the logger?
  ├── No: discard
  └── Yes: create log event
                    |
                    v
            Logger's appenders
                    |
                    v
        Ancestor appenders (if additivity)
                    |
                    v
          Filter / threshold / encoder
                    |
                    v
            Console / file / sink
~~~

- **Level:** decides whether a log call is severe enough to be processed at the emitting logger.
- **Appender/Handler:** delivers logs to a concrete destination such as console, file, or network.
- **Filter/Threshold:** can drop or restrict events at specific points in the output pipeline.
- **Additivity:** decides whether an enabled event is forwarded to appenders on ancestor branches. In Logback/Log4j 2, additivity defaults to `true`; JUL has a similar mechanism via `useParentHandlers`.

For example, suppose `ROOT` has a `CONSOLE` appender and logger `com.example.shop.audit` also has an `AUDIT_FILE` appender:

- If `audit` has **additivity=true**, audit events go to `AUDIT_FILE` and can also go to `CONSOLE` via `ROOT`.
- If `audit` has **additivity=false**, audit events stop at the `audit` branch and go only to appenders attached at this branch or child loggers along the propagation path up to the stop point.
- If `audit` has **additivity=false** but has no suitable appender, logs may not be written anywhere even though the level allows them.

One common cause of duplicate log lines is attaching the same appender to both a child logger and an ancestor while additivity remains enabled. To avoid duplication, attach the appender in one appropriate place or explicitly set `additivity=false` on branches with dedicated destinations.

## 6. Standalone Java 17+ example using java.util.logging

To directly observe **a child level overriding a parent level**, the following example uses JUL (built into the JDK), requiring no Maven/Gradle or external logging libraries.

Create **LoggerConfigDemo.java**:

~~~java
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerConfigDemo {
    public static void main(String[] args) {
        // Initialize the parent logger first, then retrieve the child loggers.
        Logger app = Logger.getLogger("com.example.shop");
        Logger payment =
                Logger.getLogger("com.example.shop.payment.PaymentService");
        Logger stock =
                Logger.getLogger("com.example.shop.stock.StockService");

        // Handler prints only the level, logger name, and message for deterministic output.
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLoggerName()
                            + " | " + record.getLevel().getName()
                            + " | " + record.getMessage());
                }
            }

            @Override public void flush() {}
            @Override public void close() {}
        };

        handler.setLevel(Level.ALL);
        app.setUseParentHandlers(false);
        app.addHandler(handler);

        app.setLevel(Level.WARNING);
        payment.setLevel(Level.FINE);

        try {
            payment.fine("payment-debug");
            payment.info("payment-info");
            stock.info("stock-info");
            stock.warning("stock-warning");
        } finally {
            app.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac LoggerConfigDemo.java
java LoggerConfigDemo
~~~

**Deterministic stdout:**

~~~text
com.example.shop.payment.PaymentService | FINE | payment-debug
com.example.shop.payment.PaymentService | INFO | payment-info
com.example.shop.stock.StockService | WARNING | stock-warning
~~~

Explanation:

1. The parent logger **com.example.shop** is set to **WARNING**.
2. The **payment** logger is explicitly set to **FINE**, allowing both FINE and INFO. In JUL, `FINE` is used for detailed diagnostics, similar to `DEBUG` in many other backends.
3. The **stock** logger has no level of its own, so it inherits `WARNING`: the INFO call is dropped, and WARNING is emitted.
4. The handler on the `app` branch is set to **Level.ALL** so it does not further filter valid FINE events.
5. `useParentHandlers(false)` prevents the example from also printing through `ROOT`'s handlers, keeping stdout easy to verify. At the end of the program, the handler is removed from the logger and closed.

This example configures loggers via the API at runtime. In larger applications, it is generally preferable to centralize configuration in files or a management system rather than scattering `setLevel` calls throughout business code.

## 7. Configuring logger names with JUL logging.properties

JUL supports configuring loggers by name through a properties file. Example **logging.properties** file:

~~~properties
# Default threshold on the root logger.
.level = INFO

# Handler on root: also accepts FINE if allowed by the child logger.
handlers = java.util.logging.ConsoleHandler
java.util.logging.ConsoleHandler.level = ALL
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Per-package loggers.
com.example.shop.payment.level = FINE
com.example.shop.repository.level = WARNING
~~~

Start a Java program that uses JUL with the JVM option (replace `MainClass` and classpath according to your actual application):

~~~bash
java -Djava.util.logging.config.file=logging.properties MainClass
~~~

JUL has the levels **SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST** (plus `ALL`/`OFF`). Do not configure JUL with words like `DEBUG` or `WARN` as if it were Logback. Do not treat `FINE ≈ DEBUG` or `SEVERE ≈ ERROR` as an exact, universal mapping across all levels in every system.

Two thresholds must be kept separate:

- **Logger level:** decides whether a `LogRecord` is created and forwarded.
- **Handler level:** decides whether the handler accepts the received `LogRecord`.

If the `payment` logger enables `FINE` but `ConsoleHandler` only accepts `INFO`, `FINE` calls still will not appear on the console. Similarly, when **useParentHandlers=false**, the logger needs its own handler; otherwise, records valid at the logger level may still not be written anywhere.

JUL-specific properties and `LogManager` update behavior can depend on the JDK version; consult the JavaDoc when changing configuration dynamically.

## 8. Per-logger configuration with SLF4J + Logback

When the backend is Logback Classic, **logback.xml** can be used. The following example sets general INFO, enables DEBUG for the payment package, restricts the repository package to WARN, and routes audit logs to a separate file.

~~~xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{HH:mm:ss.SSS} %-5level %logger{50} - %msg%n</pattern>
    </encoder>
  </appender>

  <appender name="AUDIT_FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/audit.log</file>
    <append>true</append>
    <encoder>
      <pattern>%d{ISO8601} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <logger name="com.example.shop.payment" level="DEBUG"/>
  <logger name="com.example.shop.repository" level="WARN"/>

  <logger name="com.example.shop.audit" level="INFO"
          additivity="false">
    <appender-ref ref="AUDIT_FILE"/>
  </logger>

  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
~~~

**Expected results with this configuration:**

| Event source | Event | Destination |
| --- | --- | --- |
| com.example.shop.payment.PaymentService | DEBUG | CONSOLE |
| com.example.shop.repository.OrderRepository | INFO | Not emitted due to WARN threshold |
| com.example.shop.repository.OrderRepository | ERROR | CONSOLE |
| com.example.shop.audit.AuditService | INFO | AUDIT_FILE |
| com.example.shop.stock.StockService | DEBUG | Not emitted due to ROOT=INFO |
| com.example.shop.stock.StockService | INFO | CONSOLE |

XML element ordering and appender configuration follow Logback rules. The `logs/audit.log` file must be written to a location with write permissions; when using Docker/Kubernetes, account for file persistence and container lifecycle. This example only illustrates log branching; if audit logs are legal evidence or mandatory transaction records, a durable mechanism with separate verification is required.

**Key takeaways:**

- The **com.example.shop.payment** logger has no appender of its own, so it inherits the `CONSOLE` output path through the default `additivity=true`. DEBUG lines enabled on the child branch can be delivered to `ROOT`'s appender.
- The **com.example.shop.audit** logger has `additivity=false` and references `AUDIT_FILE`, so it does not forward events to `ROOT`'s `CONSOLE`.
- Adding the `CONSOLE` appender again to `payment` while keeping `additivity=true` can cause events to be emitted twice to the same destination.
- Level does not determine formatting. Patterns belong to the appender's encoder/layout, not to the logger's level attribute.
- Logback configuration requires the appropriate dependencies; the XML snippet cannot be run directly with `javac`.

In a Spring Boot application using the default Logback backend, extended configuration is typically placed in **logback-spring.xml** to leverage Spring Boot's configuration integration; simple log level settings can be placed in `application.properties`.

## 9. Per-logger configuration with Log4j 2

Log4j 2 uses a different XML syntax. An equivalent example in **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p %c - %m%n"/>
    </Console>
    <File name="AUDIT_FILE" fileName="logs/audit.log" append="true">
      <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
    </File>
  </Appenders>

  <Loggers>
    <Logger name="com.example.shop.payment" level="debug"/>
    <Logger name="com.example.shop.repository" level="warn"/>

    <Logger name="com.example.shop.audit"
            level="info" additivity="false">
      <AppenderRef ref="AUDIT_FILE"/>
    </Logger>

    <Root level="info">
      <AppenderRef ref="CONSOLE"/>
    </Root>
  </Loggers>
</Configuration>
~~~

Here, **Logger** configures a logger by name, **Root** is the default, **AppenderRef** selects the destination, and **additivity** controls propagation to parent loggers. When using Log4j 2, you need Log4j API/Core (and the appropriate SLF4J binding/provider if code calls SLF4J). Do not mix Logback's **ch.qos.logback...** class syntax with Log4j 2's XML plugin syntax.

Log4j 2 also supports filters on both `Logger` and `AppenderRef`, meaning an event can be accepted by a logger yet still not reach a specific appender. Check logger level, appender reference, additivity, and individual filters when investigating missing logs.

## 10. Per-logger configuration in Spring Boot

Spring Boot lets you set levels by logger name in **application.properties** or **application.yml**, regardless of which supported logging backend is in use:

~~~properties
logging.level.root=INFO
logging.level.com.example.shop.payment=DEBUG
logging.level.com.example.shop.repository=WARN
logging.level.org.springframework.web=INFO
logging.level.org.hibernate.SQL=WARN
~~~

The equivalent YAML form:

~~~yaml
logging:
  level:
    root: INFO
    com.example.shop.payment: DEBUG
    com.example.shop.repository: WARN
    org.springframework.web: INFO
    org.hibernate.SQL: WARN
~~~

The **logging.level** properties adjust logger thresholds. They **do not replace** configuration for appenders, additivity, formatting, rolling policies, or advanced filters. When you need to split console/file output streams, use the appropriate backend configuration file.

Operational notes:

- For package loggers, you can configure levels via environment variables, such as **LOGGING_LEVEL_COM_EXAMPLE_SHOP_PAYMENT=DEBUG** (property name mapping depends on Spring Boot's binding rules).
- Configuring a **class name containing uppercase/lowercase letters** via a standard environment variable may fail because relaxed binding lowercases names. Use `application.properties`/YAML or a configuration mechanism that preserves exact casing, such as `SPRING_APPLICATION_JSON`, when exact class-name configuration is needed.
- When multiple configuration sources exist, verify the effective value after Spring Boot applies its property precedence rules. Do not assume `logback.xml` will always take precedence over all `logging.level` properties.
- Levels can be adjusted at runtime using supported management tools, such as Spring Boot Actuator's `loggers` management endpoint when properly configured and secured. Dynamic changes may persist only for the lifetime of the process depending on deployment; ensure you have a way to revert them and synchronize across instances if needed.

**Scenario example:** When investigating slow payments, enable DEBUG specifically for `com.example.shop.payment` for a short period; keep framework packages at INFO or WARN and never enable `ROOT=DEBUG` across production. Once the investigation ends, revert the level and check whether logs might contain sensitive data.

## 11. Choosing levels for each logger branch

There is no single fixed level that fits every application. A guiding table:

| Logger branch | Suggested baseline level | When to change |
| --- | --- | --- |
| ROOT | INFO | WARN if log volume is too high and suitable alternative observability exists |
| Business service | INFO | DEBUG temporarily to trace failing code paths |
| Repository/SQL | INFO or WARN | DEBUG on the exact library logger to diagnose queries |
| Noisy framework/library | WARN | INFO/DEBUG when investigating integration issues |
| Audit | Dedicated policy | Ensure destination and durability match business requirements |
| Security/Authentication | INFO/WARN per policy | Increase detail in a controlled way; avoid logging tokens, passwords, or sensitive data |

These levels are discussion examples, **not mandatory configurations**. For some applications, repository INFO logs remain important; for SQL libraries, the logger name to enable can vary by version. Check framework documentation and inspect actual emitted logger names before applying changes.

A common mistake is trying to fix performance problems by lowering every level to ERROR, losing essential context when incidents occur. Conversely, enabling TRACE on a broad package can spike CPU, I/O, log size, and data exposure. Selecting the right logger branch usually solves both problems.

## 12. Verifying configuration correctness

Use a test with at least two logger branches and events at multiple levels. With `ROOT=INFO`, `payment=DEBUG`, `repository=WARN`, `audit=INFO + additivity=false`, verify:

1. **Name matching:** does the logger name obtained from code match the package/class declared in configuration? Names are case-sensitive.
2. **Inheritance:** an unconfigured class inherits the level of its nearest ancestor, and does not automatically enable DEBUG just because another class in the same package has DEBUG enabled.
3. **Overriding:** a child class or package with an explicit level has the corresponding effective level.
4. **Output routing:** `payment` DEBUG events are allowed to reach `CONSOLE` if the appender has no separate blocking filter.
5. **Level blocking:** `repository` INFO is not emitted; `repository` WARN/ERROR are allowed.
6. **Additivity:** `audit` goes only to `AUDIT_FILE`, does not also appear on `CONSOLE`, and is not lost completely due to a missing appender.
7. **Handler/Appender threshold:** test an enabled logger level that still produces no output when the sink is intentionally configured with a filter — this proves the result depends on both layers.
8. **Reload/Deployment:** verify the configuration actually loaded in the running process and on each instance, not just the file in the source repository.

When testing logs that include timestamps, thread IDs, or asynchronous appenders, avoid brittle full-stdout comparisons. Prefer verifying **level, logger name, message content, emission count, and destination**. If an async appender is used, wait for flushing to complete or shut down the context cleanly before asserting record counts.

## 13. Common issues and how to investigate them

### DEBUG is enabled but no logs appear

Check in order:

- Does the actual logger name match the declared branch? For example, `com.example.shop.payment` differs from `com.example.shop.paymentx`.
- Is a more specific level configured on a child class name overriding the package configuration?
- Which configuration file is loaded, and is any profile or property source overriding the value?
- Is a filter, appender threshold, JUL `Handler` level, or sampling feature dropping the event?
- Does the logger have `additivity=false` without its own appender/handler?
- Was the log enqueued but not yet flushed, or did the sink fail to write/collect it?

### A log line appears twice

Check appenders attached to both child loggers and ancestors, default additivity, and whether the same event is routed to multiple sinks that are later merged into one centralized logging system. The cause may be duplicate appender configuration or duplication in the collector; do not immediately assume the business method ran twice.

### Setting a package level does not affect every class

Check the logger names. If code creates a logger with a custom name, such as `LoggerFactory.getLogger("paymentFlow")`, configuring `com.example.shop.payment` will have no effect. Also check for direct overrides on child loggers and other runtime configurations.

### Logging is turned off but some lines still appear

Those lines may come from another logger, a different logging bridge, `System.out`/`System.err`, framework startup before logging is initialized, or a separate collector target. Distinguish the logging API being used from the actual backend. Do not assume all stdout output goes through the application's loggers.

### Broad configuration slows down the system

Enabling DEBUG/TRACE on a wide branch adds formatting, I/O, storage, and collection overhead. For expensive arguments, you can guard first:

~~~java
// Illustrative snippet using SLF4J inside a method:
if (log.isDebugEnabled()) {
    log.debug("Diagnostic state: {}", buildExpensiveDiagnosticState());
}
~~~

Use a guard when constructing log arguments is genuinely expensive; avoid putting side-effecting logic inside expressions meant only for logging. Never use DEBUG or TRACE to log secrets.

## 14. Organizing maintainable configurations

- Choose consistent logger naming: prefer class/package names so configuration is predictable; use custom names only when there is a clear reason.
- Keep the root policy relatively stable. Apply narrow overrides to packages that need different behavior.
- Separate level policy from output routing: use logger levels for verbosity, and appenders + additivity/filters for routing.
- When routing separately, such as for audit logs, declare the appender explicitly and verify data is not lost when `additivity=false`.
- Document the reason and expiration for temporary DEBUG/TRACE settings; revert them after investigation.
- Protect runtime configuration and level-change endpoints so unauthorized users cannot enable sensitive logging or overload infrastructure.
- Use independent metrics/traces for critical operational signals; logging can be filtered, delayed, or unavailable.

**Rule of thumb:** set **level** on loggers to control detail, use **inheritance** to apply policies by package, and use **additivity and appenders** to route output. When logs are missing or duplicated, check all three instead of looking only at the `ROOT` level.

## 15. References

- [Logback Manual — Architecture](https://logback.qos.ch/manual/architecture.html): logger hierarchy, effective level, basic selection rule, appender additivity.
- [Logback Manual — XML Configuration](https://logback.qos.ch/manual/configuration-xml.html): logger, root, and appender syntax.
- [Apache Log4j 2 — Configuration](https://logging.apache.org/log4j/2.x/manual/configuration.html): Logger, Root, AppenderRef, additivity, and filters.
- [Oracle Java SE 17 — java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): parent, setLevel, isLoggable, useParentHandlers.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging.level, per-package/class configuration, and runtime environment.

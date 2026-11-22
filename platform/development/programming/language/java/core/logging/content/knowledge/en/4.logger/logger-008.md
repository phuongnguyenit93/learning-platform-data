# Creating a Logger in Java

A **logger** is the object Java code uses to emit events that need to be recorded: starting an operation, completing processing, detecting an anomaly, or catching an exception. When a logger is created properly, every event has a **stable source identifier**, follows the application's logging configuration, and can be traced by class, package, or functional area.

This lesson focuses on **how to create and obtain a logger**, where to place the reference, naming conventions, differences among `java.util.logging` (JUL), SLF4J, and Log4j 2, and common pitfalls. The main examples use **Java 17+ and JUL built into the JDK**, with no external libraries required.

## 1. What is a logger and what does "creating a logger" mean?

A logging event flows through the following conceptual roles:

```text
Application code
    |
    | calls logger.info(...) / logger.log(...)
    v
Logger identified by name
    |
    | checks level/filter at logger
    v
Log event / LogRecord
    |
    | forwards to handler/appender per configuration
    v
Destination: console, file, log collection system...
```

Obtaining a logger only creates or retrieves a **log emission point**. This operation does not guarantee that a file will be opened, does not automatically attach a new handler to every logger, and does not decide that every message will appear on the console. The **logger** determines where an event is emitted from and which levels can be emitted; the **handler/appender** along with backend configuration determines how events are filtered, formatted, routed, and written to a destination.

Three concepts to keep distinct:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Logger name** | Event source/category | `com.example.order.OrderService` |
| **Log level** | Level of detail or severity | JUL: `FINE`, `INFO`, `WARNING`, `SEVERE` |
| **Handler/appender** | Where events are sent and how they are further processed | `ConsoleHandler`, rolling file, collector |

An HTTP request may be processed across multiple loggers belonging to different classes. The request ID is carried in the **log event**, while the logger name typically stays fixed per class. Do not create a new logger whose name changes with each request.

## 2. Creating a logger in JUL with `Logger.getLogger`

The JDK provides `java.util.logging.Logger`. In a Java class, the standard declaration is:

```java
import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());

    public void createOrder(String orderId) {
        LOGGER.info("Creating order");
    }
}
```

This snippet is a valid class that can be saved in `OrderService.java` and compiled with the JDK, though it **does not have a `main` method to run standalone**. `OrderService.class.getName()` returns the fully qualified class name, including its package if present, such as `com.example.order.OrderService`.

**Why use `private static final`?**

- `private`: the logger serves the class's internal implementation and does not need to be exposed as part of its business API.
- `static`: all instances of the same class share a single reference, avoiding repeated logger lookups on every call.
- `final`: the reference cannot be reassigned to another logger after initialization.
- `OrderService.class.getName()`: the logger name is stable and automatically follows the class name when changing packages or refactoring.

The variable name can be `LOGGER`, `LOG`, or `log`, depending on codebase conventions. The **variable name** is not the **logger name**: renaming `LOGGER` to `LOG` does not change the logger name passed to `getLogger(...)`.

### How does `Logger.getLogger(String)` work?

JUL uses `LogManager` to manage named loggers. `Logger.getLogger(name)` looks up an existing logger by name in the appropriate management context or registers a corresponding one. Calling it does not mean creating a brand-new independent instance every time. In normal applications, a `static final` field keeps a strong, stable reference; `LogManager` may hold weak references to application-created loggers, so you should not rely on looking up a name again after all strong references are gone to preserve custom state.

Do not call `new Logger(...)` directly for normal use: JUL's `Logger` constructor is not a public API for creating application loggers, and the system relies on `LogManager` to manage names and hierarchy.

When declaring loggers across multiple classes, use **the class's own name**. For example, `InvoiceService` should obtain `Logger.getLogger(InvoiceService.class.getName())`, rather than mistakenly copying `OrderService` and making logs hard to trace back to their source.

## 3. Complete Java 17 program: obtaining a logger and logging three events

This example creates a class-named logger and **attaches a `ConsoleHandler` specifically for the demonstration program**. We configure the `FINE` level on both the logger and the handler, using a fixed formatter so the output is easy to inspect.

Save as **`CreateLoggerDemo.java`**:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class CreateLoggerDemo {
    private static final Logger LOGGER =
            Logger.getLogger(CreateLoggerDemo.class.getName());

    public static void main(String[] args) {
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.FINE);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + record.getLoggerName()
                        + " - " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.FINE);
        LOGGER.addHandler(console);

        try {
            LOGGER.fine("stage=start");
            LOGGER.log(Level.INFO,
                    "requestId={0} stage=validated", "req-17");
            LOGGER.warning("stage=done");
        } finally {
            LOGGER.removeHandler(console);
            console.close();
        }
    }
}
```

Compile and run with **JDK 17 or newer**:

```bash
javac -encoding UTF-8 CreateLoggerDemo.java
java CreateLoggerDemo
```

**Exact output on `stderr`:**

```text
FINE CreateLoggerDemo - stage=start
INFO CreateLoggerDemo - requestId=req-17 stage=validated
WARNING CreateLoggerDemo - stage=done
```

The program does not actively write to `stdout`. JUL's `ConsoleHandler` writes to `System.err` by default. A terminal that displays both stdout and stderr will show the lines above; a tool that captures only stdout will not.

Program breakdown:

1. `Logger.getLogger(CreateLoggerDemo.class.getName())` retrieves the logger named `CreateLoggerDemo` (because the class is in the default package in this example).
2. `LOGGER.setLevel(Level.FINE)` allows the logger to emit records at level `FINE` and above; `console.setLevel(Level.FINE)` ensures the handler does not filter out `FINE` entries on its own.
3. `LOGGER.setUseParentHandlers(false)` prevents forwarding records to parent logger handlers, avoiding extra output from environment configuration. **Do not apply this automatically to every production logger** if you rely on a centralized logging setup.
4. `Formatter.formatMessage(record)` formats JUL messages that use `{0}` placeholders; `"requestId={0} stage=validated"` becomes `requestId=req-17 stage=validated`. JUL uses `MessageFormat`-style syntax here, unlike the `{}` syntax commonly used in SLF4J.
5. `removeHandler` and `close` manage the lifecycle of the handler that this example explicitly attached to the logger. In real applications, shared handlers/appenders should be managed centrally during application startup and shutdown.

The formatter intentionally omits timestamps to keep the output deterministic; in production, logs need timezone-aware timestamps, component identifiers, correlation IDs, and proper exception details.

### Experimenting with log levels

Keep the logger at `Level.FINE`, but change:

```java
console.setLevel(Level.WARNING);
```

This is a **one-line edit in the program above**, not a standalone program. When rerun, the handler only writes the `WARNING` line; `FINE` and `INFO` were emitted by the logger but filtered out by the handler. If you instead set **`LOGGER.setLevel(Level.INFO)`**, the `FINE` event is blocked right at the logger, so even if the handler is set to `FINE`, it cannot recover a record that was never emitted.

## 4. Should you create a logger per class or by a custom name?

### Naming by class

```java
private static final Logger LOGGER =
        Logger.getLogger(InventoryService.class.getName());
```

This snippet assumes it resides in the `InventoryService` class. The fully qualified class name naturally aligns with the package hierarchy, such as `com.example.inventory.InventoryService`. During investigations, you can filter logs by class or package.

### Naming by category

```java
private static final Logger AUDIT_LOG =
        Logger.getLogger("com.example.audit");
```

Manual naming can make sense when a project defines a shared category, such as access logs or audit logs. However, if every class uses a single generic name like `"application"`, pinpointing where an event originated becomes much harder. For audit logs with regulatory or transactional requirements, an ordinary logger does not replace a durable, controlled audit system.

### Do not create loggers per user or per request

```java
// Snippet not recommended; assumes requestId is an existing variable.
Logger logger = Logger.getLogger("request." + requestId);
```

If logger names vary across millions of requests, you end up with a proliferation of categories that are hard to configure and create management overhead. Instead, use a stable class-based logger and pass `requestId`, `jobId`, or correlation IDs in the **event content/metadata**. Never put sensitive data directly into a logger name.

### Can a logger be an instance field?

Yes, if the design genuinely requires a replaceable logger, dependency injection, or a dedicated abstraction. However, calling `Logger.getLogger(...)` per object instance usually offers no benefit when every instance of the class uses the same name. Most Java applications choose **one `private static final` field per class**.

## 5. Creating a logger with SLF4J (commonly used with Logback)

Many modern applications use **SLF4J** as a common API. The syntax differs from JUL:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class PaymentService {
    private static final Logger LOG =
            LoggerFactory.getLogger(PaymentService.class);

    public void authorize(String paymentId) {
        LOG.info("Authorizing paymentId={}", paymentId);
    }
}
```

This is a valid class in a **project that provides the SLF4J API along with a compatible provider/backend**, such as Logback; it **will not compile with the plain JDK** without those dependencies.

`LoggerFactory.getLogger(PaymentService.class)` retrieves a logger named after the class. SLF4J is a **facade/API**; a backing provider must handle the actual logging. When using Logback, `Appender`s, `Encoder`s, log levels, and rolling files are configured in Logback—not by creating appenders inside each `PaymentService`.

SLF4J's placeholder is **`{}`**:

```java
// Fragment: LOG is an SLF4J Logger; paymentId and status are already defined in the method.
LOG.info("paymentId={} status={}", paymentId, status);
```

Do not copy this syntax into JUL. JUL has its own parameterization and formatter rules, such as `LOGGER.log(Level.INFO, "paymentId={0}", paymentId)`.

When a library or framework has already standardized on SLF4J as its primary API, business code should follow that convention. Do not add another backend arbitrarily just to get `LoggerFactory`: multiple providers or incompatible bridges can lead to unpredictable runtime behavior.

### Loggers generated by Lombok

If the project has **Lombok** installed and annotation processing enabled, `@Slf4j` can generate the SLF4J logger field:

```java
import lombok.extern.slf4j.Slf4j;

@Slf4j
public class ShippingService {
    public void ship(String shipmentId) {
        log.info("Shipping shipmentId={}", shipmentId);
    }
}
```

This is not a plain-JDK example. Lombok reduces boilerplate, but it is **not a logging backend**; SLF4J and a suitable runtime provider are still required. Using Lombok is a codebase choice, not a prerequisite for creating a logger.

## 6. Creating a logger with Log4j 2

If an application uses the Log4j 2 API directly, it can be written as:

```java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class ReportService {
    private static final Logger LOG =
            LogManager.getLogger(ReportService.class);

    public void generate(String reportId) {
        LOG.info("Generating reportId={}", reportId);
    }
}
```

This snippet requires the appropriate Log4j 2 dependencies and will not run with the JDK alone. `LogManager.getLogger(ReportService.class)` obtains a class-named logger. If the backend is Log4j 2 but the application uses SLF4J as its facade, business code **can still obtain loggers via `LoggerFactory`**, provided the binding/provider is configured properly. There is no need to switch to the Log4j API just because Log4j is the underlying log backend.

| Ecosystem | Factory/call to get logger | Logger type | What manages the output? |
| --- | --- | --- | --- |
| JUL | `Logger.getLogger(MyClass.class.getName())` | `java.util.logging.Logger` | JUL `Handler`s and JUL configuration |
| SLF4J | `LoggerFactory.getLogger(MyClass.class)` | `org.slf4j.Logger` | Provider/backend, typically Logback or a compatible implementation |
| Log4j 2 API | `LogManager.getLogger(MyClass.class)` | `org.apache.logging.log4j.Logger` | Log4j Core / active runtime configuration |
| Lombok `@Slf4j` | Generates `log` field at compile time | SLF4J Logger | SLF4J provider/backend |

**Import pitfall:** JUL, SLF4J, and Log4j 2 all define a class or interface named `Logger`, but they are not the same type. Avoid mixing `import java.util.logging.Logger` with `LoggerFactory.getLogger(...)` or passing an `org.slf4j.Logger` into an API that expects a JUL `Logger`.

### Is `System.getLogger` the same as JUL?

JDK 9+ also provides:

```java
System.Logger log = System.getLogger("com.example.ReportService");
log.log(System.Logger.Level.INFO, "Starting report");
```

This is **`java.lang.System.Logger`**, a different API from `java.util.logging.Logger` that uses the runtime's `System.LoggerFinder` mechanism to select an implementation. Do not cast between the two logger types or mechanically apply all JUL configuration rules to `System.Logger`. Choose the API that matches your project architecture.

## 7. Logger names, packages, and JUL configuration inheritance

JUL loggers have a dot-separated name hierarchy, for example:

```text
(com.example)
   |
   +-- com.example.order
          |
          +-- com.example.order.OrderService
          +-- com.example.order.OrderController
```

This diagram illustrates the **name hierarchy**; it does not imply that every parent logger already exists as an object declared in code. `LogManager` manages relationships among created loggers and creates or adjusts parent links as loggers appear.

Two mechanisms are easy to confuse:

- **Inherited level:** if `logger.getLevel() == null`, the logger can inherit its **effective level** from a parent; `null` does not mean `OFF` or an error.
- **Inherited handler routing:** if `logger.getUseParentHandlers()` is `true`, a record accepted by the logger can travel up to its parent logger's handlers. Each parent handler still applies its own level and filter.

This explains why a newly retrieved logger can still produce output even when the application has not attached a handler directly to it: the runtime may already have configured handlers on the root logger.

Be careful about attaching a separate `ConsoleHandler` to individual child loggers while the root logger also writes to the console. When propagation is enabled, an event can **appear twice** at the same destination. The earlier example used `setUseParentHandlers(false)` to achieve deterministic output; production applications should clearly define what manages the shared output pipeline.

JUL allows configuration through `LogManager` and a `logging.properties` file (depending on how the runtime is bootstrapped). Calling `Logger.getLogger(...)` in business code does not replace system configuration. For SLF4J/Logback, levels, appenders, and additivity are configured according to Logback conventions; do not mistakenly try to configure Logback using JUL's `logging.properties` syntax.

## 8. Performance, exceptions, and context after creating a logger

### Avoid building expensive messages when the level is disabled

An example that can waste resources:

```java
// Fragment: expensiveSummary() is an application-defined method.
LOGGER.fine("state=" + expensiveSummary());
```

Even when `FINE` is disabled, Java still evaluates `expensiveSummary()` before calling `fine`. JUL supports a lazy message supplier:

```java
// Fragment: LOGGER is java.util.logging.Logger; Level is already imported.
LOGGER.log(Level.FINE, () -> "state=" + expensiveSummary());
```

The supplier is invoked only if the logger accepts the log level. This does not guarantee that every handler will write the record, as handlers have their own levels and filters. Do not rely on side effects inside the supplier, because when the log level is disabled, those side effects will not occur.

In SLF4J, using `{}` placeholders avoids string concatenation before the call:

```java
// Fragment: LOG is org.slf4j.Logger; count is a precomputed number.
LOG.debug("Processed {} records", count);
```

However, if you write `LOG.debug("Report {}", expensiveSummary())`, Java still evaluates `expensiveSummary()` before entering the API. For costly computations, use a lazy mechanism or an appropriate level guard provided by the API/backend.

### A logger does not replace error handling

Once you have a logger, catching an exception still requires a business decision: return an error, roll back, retry, restart, or rethrow. To preserve technical traces, pass the **`Throwable` object**:

```java
// Fragment inside a catch block; LOGGER and exception e already exist.
LOGGER.log(Level.SEVERE, "Could not initialize settings", e);
```

The backend/formatter decides how to render the stack trace. Logging only `e.getMessage()` often omits the exception class and the `Caused by` chain. Also avoid logging the same full exception at every layer and rethrowing it without adding new context, as a single failure can be recorded as multiple separate incidents.

### Identify by class, add context per event

`requestId`, `jobId`, deployment version, and related fields should be attached to the event for troubleshooting. Logging ecosystems may offer MDC/thread context or other mechanisms to enrich log events with these fields. However, thread-bound context **does not automatically propagate across all thread pools or services**; when using asynchronous execution, design context propagation and cleanup carefully. Never log tokens, passwords, session cookies, or unnecessary sensitive data.

## 9. Common mistakes when creating a logger

| Issue | Why it happens | How to check or fix |
| --- | --- | --- |
| `getLogger` succeeds but no logs appear | Logger level, handler/appender level, filter, or sink | Trace the path from logger to destination; check every filtering point |
| `FINE` lines are missing | Logger or handler only allows `INFO` and above | Check `isLoggable(Level.FINE)` and the handler level |
| One event prints twice | Child and parent both write to console, duplicate handlers, or logging bridges | Check propagation/additivity and the event routing path |
| All logs show the same class name | Mistakenly copied `.class` when creating the logger | Use the class that actually owns the logger field |
| Compile error on `LoggerFactory` or `LogManager` | Wrong import/dependency or mixing up JUL with SLF4J/Log4j | Verify the FQCN, chosen API, and compatible backend |
| SLF4J runs but logs do not reach the expected destination | Missing/wrong provider or appender configuration | Check the runtime provider and backend configuration |
| Creating a new logger with a dynamic name per request | Too many categories, difficult to manage | Use a class-based logger; put correlation IDs in the log event |
| Using `System.out.println` instead of a logger | No levels, categories, or unified policy | Use an appropriate logger with centralized configuration |
| Calling `LOGGER.fine("x=" + heavy())` when disabled | Expensive value is still computed | Use a supplier or an appropriate level guard |
| Obtaining a logger and attaching a new handler on every call | Easy to duplicate logs and leak/grow resources | Obtain the logger per class; manage handlers centrally |
| Log has message but no stack trace | `Throwable` was not passed or formatter drops error details | Pass the exception and check the formatter/backend |
| Logs appear only on stderr | JUL `ConsoleHandler` writes to stderr | Configure log collectors to read the right stream |

**Do not conclude that a logger was not created just because nothing appears on the console.** The logger may have emitted the event while a handler blocked it, the destination failed to write, or the collection tool is reading the wrong stream (stdout vs. stderr).

## 10. Self-check after creating a logger

When adding a logger to a class, you can follow these steps:

1. **Choose the right API:** JUL if you want built-in JDK features; SLF4J or Log4j 2 if the project has already adopted that ecosystem. Do not mix `Logger` types from different packages.
2. **Name by class:** prefer the fully qualified name to enable package-level filtering; do not put `requestId` into the logger name.
3. **Declare once:** use `private static final` where appropriate; do not re-fetch loggers or re-attach handlers per request.
4. **Verify effective configuration:** check effective levels on the logger, handler/appender, formatter, and propagation.
5. **Test across levels:** emit `INFO`, a detailed level, and a warning/exception; verify output in the expected console/file/collector.
6. **Inspect messages:** ensure useful context, no secrets, and no expensive data construction when the level is disabled.
7. **Check concurrency and lifecycle:** sharing a single logger across threads is standard; do not close shared handlers before application shutdown.

**Target outcome:** When reading a line like `Logger.getLogger(...)`, `LoggerFactory.getLogger(...)`, or `LogManager.getLogger(...)`, you know **what the logger is identified by**, **which API it belongs to**, **where destination configuration lives**, and **what checkpoints to inspect when an event does not appear**. A good logger has a consistent name, is reused at the appropriate scope, and emits logs through an intentionally configured logging system.

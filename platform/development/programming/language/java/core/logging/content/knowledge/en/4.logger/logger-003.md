# Package-Based Loggers in Java

## 1. What Is a Package-Based Logger?

In Java applications, code is typically organized into **packages** such as `com.example.catalog`, `com.example.orders`, and `com.example.orders.internal`. Logging can follow this exact structure: logger names reflect the package (or the name of a class in that package), allowing operators to configure log levels and output destinations for **a group of components** instead of adjusting individual log statements.

For example, when order processing slows down, we can increase the verbosity of `com.example.orders` to observe classes in that branch while keeping other packages at `INFO`. This approach reduces noise, saves log storage costs, and helps isolate incidents.

Two common naming approaches:

```java
import java.util.logging.Logger;

// A shared logger for classes in the package:
Logger packageLogger = Logger.getLogger("com.example.orders");

// A class-named logger, usually recommended to identify the specific source:
Logger classLogger = Logger.getLogger(OrderService.class.getName());
```

The snippet above only illustrates naming conventions; `OrderService` is a hypothetical class in a project, not a standalone Java program.

Important distinction: **a logger name is a string identifier**, not a Java `Package` object. The `Logger.getLogger(String name)` API does not automatically verify whether that name matches an actual package. Developers choose the convention of "logger names follow packages," while the logging system uses the name structure to apply hierarchical configuration. In Java 9 and later, `OrderService.class.getPackageName()` retrieves the actual package name of the class; `OrderService.class.getName()` retrieves the fully qualified class name, including the package.

### Why Not Use a Single Logger for the Entire Application?

Suppose every class called `Logger.getLogger("application")`. Log lines might show what happened, but it would be difficult to separate sources by package. When you want to inspect details for the payment feature alone, enabling `FINE` on the shared logger would make unrelated components noisy as well.

Hierarchical naming creates a tree to **adjust the exact scope**:

```text
com.example
├── com.example.orders
│   ├── com.example.orders.OrderService
│   └── com.example.orders.internal
│       └── com.example.orders.internal.StockChecker
└── com.example.payments
    └── com.example.payments.PaymentService
```

The class names at the leaves of the tree only appear as logger nodes if the program actually creates loggers with those names. The tree above describes **usable logger name relationships**, and does not imply that the library automatically registers every package or class in the project.

## 2. Two Approaches: One Logger per Package or One Logger per Class

| Criterion | Package-Based Logger | Class-Based Logger |
| --- | --- | --- |
| Obtaining the name | `Logger.getLogger(OrderService.class.getPackageName())` | `Logger.getLogger(OrderService.class.getName())` |
| Example name | `com.example.orders` | `com.example.orders.OrderService` |
| Purpose | Group events from multiple classes in the same package | Clearly record the source class emitting the log |
| Package-level configuration | Applied directly | Still applies via hierarchical naming |
| Trade-off | Less precise class distinction in the logger field | More logger names, but greater flexibility |

Both approaches can make sense. In projects with many classes, a common choice is for **each class to declare its own logger by class name**, while log levels are set at the **package level** via configuration. This provides both detailed source information and the ability to toggle verbosity for an entire branch. A literal package-based logger is useful when you only need to group sources at the package level, such as in a small example or component.

With JUL (`java.util.logging`), an example in `com.example.orders`:

```java
private static final Logger LOG =
        Logger.getLogger(OrderService.class.getName());
```

With SLF4J (an API facade requiring appropriate dependencies and a backend):

```java
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(OrderService.class);
```

Both snippets **illustrate placing a logger inside a class**; they will not compile standalone without the surrounding class declaration. With SLF4J, actual logger configuration is handled by a backend such as Logback or Log4j2.

You should not create logger names from request IDs, user IDs, or unbounded data, such as `Logger.getLogger("orders." + userId)`. Logger names should be stable per component; correlation IDs or request IDs belong in the event context, not in the logger name.

## 3. Dot-Separated Hierarchy Mechanism

In JUL, loggers have hierarchical names using dots `.` to separate segments. If `com.example.orders` has an existing parent logger `com.example`, the child logger can inherit its log level from the parent. This is a **logger** relationship, not Java class inheritance or a directory structure.

Example policy:

| Logger | Configured Level | Typical Effective Level |
| --- | --- | --- |
| `com.example` | `INFO` | `INFO` |
| `com.example.orders` | `null` (not set explicitly) | `INFO` from parent |
| `com.example.orders.internal` | `null` | `INFO` from nearest ancestor with a level |
| `com.example.payments` | `WARNING` | `WARNING` |
| `com.example.payments.PaymentService` | `null` | `WARNING` from parent |

In JUL, `logger.setLevel(null)` means **inherit the level from the parent**, not allow all records. `Level.ALL` is the level that permits all levels (at the level-check step); `Level.OFF` disables logging on that logger.

One way to think about it:

```text
com.example                       INFO
  |
  +-- com.example.orders           (inherits INFO)
  |       |
  |       +-- .internal             (inherits INFO)
  |
  +-- com.example.payments         WARNING
```

If you change `com.example.orders` from inherited to `FINE`, child loggers without their own explicit level can start producing `FINE` records. That **does not yet guarantee the records will appear in the console or a file**, because the log destination may have its own threshold.

### Logger Level vs. Handler Level

There are two independent questions:

1. **Does the logger accept creating the record?** For example, a logger with an effective level of `INFO` blocks `FINE`.
2. **Does the handler/appender write the created record?** For example, a `ConsoleHandler` set to `WARNING` drops `INFO` even if the source logger accepted it.

In JUL, when a record from a child logger propagates to a parent logger's handlers, **the parent logger's level is not used to re-filter an already created record**. Instead, the threshold and `Filter` on each handler decide output. Therefore, a `FINE` record emitted by a child logger with `FINE` enabled can reach a parent handler that allows `FINE`, even if the parent logger itself is set to `INFO`. Do not rely on a parent logger's threshold as a final safety gate at the output destination.

### Propagation and Duplicate Logs

JUL provides `setUseParentHandlers(boolean)`; the default value usually allows a record to pass through the current logger's handlers and then up to parent loggers. If a console handler is attached to both child and parent, the same record can appear twice. Calling `setUseParentHandlers(false)` on the right logger stops forwarding to parents, though it can also drop copies that were meant to be collected on a shared route.

In Logback, the corresponding concept is usually called `additivity`. You should check both **where appenders/handlers are attached** and **propagation rules** when encountering duplicate logs or missing logs.

## 4. Runnable Java 17 Example: Multiple Packages, One Shared Configuration

This example has three package branches: `demo` (configuration point), `demo.orders` with its subpackage `demo.orders.internal`, and `demo.payments`. To observe behavior accurately, the program uses a custom handler that prints a fixed format to stdout. This handler is for demonstration only, not a production logging solution.

Create the directory structure:

```text
src/
└── demo/
    ├── App.java
    ├── orders/
    │   ├── OrderService.java
    │   └── internal/
    │       └── StockChecker.java
    └── payments/
        └── PaymentService.java
```

**File `src/demo/App.java`** — sets levels per package and attaches a handler to the `demo` logger:

```java
package demo;

import demo.orders.OrderService;
import demo.payments.PaymentService;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class App {
    public static void main(String[] args) {
        Logger appLogger = Logger.getLogger("demo");
        appLogger.setLevel(Level.INFO);
        appLogger.setUseParentHandlers(false);

        Handler console = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (!isLoggable(record)) {
                    return;
                }
                System.out.printf("%s %s - %s%n",
                        record.getLevel().getName(),
                        record.getLoggerName(),
                        record.getMessage());
            }

            @Override
            public void flush() {
                // Each record is printed directly in this example.
            }

            @Override
            public void close() {
                // Do not close System.out because the handler does not own it.
            }
        };
        console.setLevel(Level.ALL);
        appLogger.addHandler(console);

        Logger ordersLogger = Logger.getLogger("demo.orders");
        ordersLogger.setLevel(null); // Inherits INFO from "demo".

        Logger paymentsLogger = Logger.getLogger("demo.payments");
        paymentsLogger.setLevel(Level.WARNING);

        new OrderService().process();
        new PaymentService().process();

        appLogger.removeHandler(console);
        console.close();
    }
}
```

**File `src/demo/orders/OrderService.java`** — logger uses the actual package name:

```java
package demo.orders;

import demo.orders.internal.StockChecker;
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getPackageName());

    public void process() {
        LOG.info("order.created");
        new StockChecker().check();
        LOG.warning("order.delayed");
    }
}
```

**File `src/demo/orders/internal/StockChecker.java`** — subpackage inherits configuration from `demo.orders`:

```java
package demo.orders.internal;

import java.util.logging.Logger;

public class StockChecker {
    private static final Logger LOG =
            Logger.getLogger(StockChecker.class.getPackageName());

    public void check() {
        LOG.info("stock.available");
        LOG.fine("stock.debug");
    }
}
```

**File `src/demo/payments/PaymentService.java`** — `INFO` level will be blocked by the package's `WARNING` level:

```java
package demo.payments;

import java.util.logging.Logger;

public class PaymentService {
    private static final Logger LOG =
            Logger.getLogger(PaymentService.class.getPackageName());

    public void process() {
        LOG.info("payment.started");
        LOG.warning("payment.retry");
    }
}
```

From the directory containing `src`, run with JDK 17 or later:

```bash
javac -d out src/demo/App.java src/demo/orders/OrderService.java src/demo/orders/internal/StockChecker.java src/demo/payments/PaymentService.java
java -cp out demo.App
```

**Expected stdout:**

```text
INFO demo.orders - order.created
INFO demo.orders.internal - stock.available
WARNING demo.orders - order.delayed
WARNING demo.payments - payment.retry
```

Why do exactly four lines appear?

1. `demo` has an `INFO` threshold. `demo.orders` has no explicit threshold, so it accepts `INFO` and `WARNING`.
2. `demo.orders.internal` sits under that branch and inherits `INFO`, so it emits `stock.available` but drops `stock.debug` at `FINE`.
3. `demo.payments` sets `WARNING`, so `payment.started` at `INFO` is dropped at the source logger; `payment.retry` is kept.
4. The handler on `demo` is set to `ALL` so it does not filter out records already accepted by loggers. `appLogger.setUseParentHandlers(false)` avoids extra output via the JUL root logger's handler.
5. Each class calls `getPackageName()` to get its own package; when multiple classes in the same package choose the same logger name, they share the logger with that name.

This example intentionally omits timestamps because the goal is to demonstrate **package -> log level -> predictable output**. Production setups should use a formatter with timestamps, logger name, level, correlation context, and a stable format. In practice, you also need to handle closing/flushing writers, I/O errors, and concurrent threads.

### Controlled Experiments

If you change:

```java
ordersLogger.setLevel(Level.FINE);
```

then `stock.debug` can appear because both the `demo.orders.internal` logger and the `console` handler accept `FINE`. Note that the `demo` handler is `ALL`; **the `INFO` level on the `demo` logger itself does not re-filter `FINE` records already accepted by a child logger**, so this change takes effect.

If you change:

```java
console.setLevel(Level.WARNING);
```

then only `WARNING` records in the example are printed, even though the `demo.orders` logger can still create `INFO` records. This illustrates the difference between **filtering at the source** and **filtering at the destination**.

## 5. Configuring Package Levels in Real Systems

You should not hardcode production logging policy in code like `App.java` above. Instead, business code typically declares loggers once, while the deployed application selects package levels via configuration files or startup parameters.

### 5.1. JUL Example with `logging.properties`

Here is a configuration for **a typical JUL application without the programmatic configuration from Section 4**:

```properties
handlers=java.util.logging.ConsoleHandler

.level=INFO
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

demo.orders.level=FINE
demo.payments.level=WARNING
```

If you invoke the JVM with:

```bash
java -Djava.util.logging.config.file=logging.properties -cp out demo.App
```

then **`demo.App` from Section 4 still configures its own loggers, handler, and levels**; in particular, it sets `ordersLogger.setLevel(null)` and `paymentsLogger.setLevel(WARNING)`. Therefore, the command above is not an example for observing the effect of `logging.properties` alone. To configure entirely from a file, use an application that does not programmatically attach handlers or override those levels. This is an important difference between external configuration and in-code configuration.

In `logging.properties`, `demo.orders.level=FINE` allows code under the orders branch to emit detailed logs; `ConsoleHandler.level=ALL` ensures the handler does not filter them out. With multiple handlers, each handler needs an appropriate threshold and formatter for its destination channel.

### 5.2. SLF4J + Logback Example

For an application using SLF4J as the API and Logback as the backend, you can write `logback.xml` with a similar idea:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.orders" level="DEBUG" />
    <logger name="com.example.payments" level="WARN" />

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

The configuration above illustrates:

- `com.example.orders` and matching child-named loggers can emit `DEBUG` and above, even though root is set to `INFO`. Once an event is created, the root level does not by default block it on the way to root's appender.
- `com.example.payments` and its sub-branch only emit `WARN` and above, unless a child logger has a more specific level configured.
- The appender on root serves the entire application; a package `<logger>` only changes the threshold and does not automatically create extra files or log channels.
- Do not attach the same appender to a child logger while leaving `additivity=true` if you do not want the same record sent twice.

Logback configuration **does not apply directly** to JUL; you must identify which API and backend are actually running. Level names differ across libraries: JUL typically uses `FINE` and `SEVERE`, whereas SLF4J/Logback use `DEBUG` and `ERROR`. Do not guess level names assuming every backend shares the same syntax.

### 5.3. Package Name vs. Class Name

If your code uses:

```java
Logger.getLogger(OrderService.class.getName());
```

and the class name is `com.example.orders.OrderService`, configuration for `com.example.orders` can still govern the class logger through the hierarchical naming structure. This lets you enable verbose logging for an entire package, then dial down a single noisy class if the backend supports per-class level configuration.

If your code instead uses a shared logger named after the package `com.example.orders`, all classes share that name; in that case, configuring by **logger name** for a single class cannot distinguish which class emitted the event. You can include another source field when needed, but naming loggers by class is usually clearer.

## 6. Real-World Scenario: Isolating Errors by Package

Suppose a system has these branches:

- `com.example.api`: receives HTTP requests.
- `com.example.orders`: validates and creates orders.
- `com.example.payments`: calls payment services.
- `com.example.notifications`: sends notifications.

By default, production logs `INFO` to track key events and `WARN`/`ERROR` for failures. When intermittent payment errors occur, operations needs more context from the internal steps of the payment service.

A controlled troubleshooting workflow:

1. Identify the symptom (error rate, time window, error code) and the closest responsible package, such as `com.example.payments`.
2. Temporarily increase verbosity for that package alone if an appropriate configuration mechanism is available. Use `DEBUG` (Logback) or `FINE` (JUL), without enabling verbose logging application-wide.
3. Log structured events: `event`, `status`, `duration_ms`, `error_code`, `trace_id`. Avoid personal data, passwords, tokens, card details, and sensitive request bodies.
4. Check the threshold of **appenders/handlers** and the collection pipeline: enabling a level on the logger while an appender still blocks it means new logs will not reach the viewer.
5. After finding the root cause, restore levels to normal policy to avoid increased storage volume, CPU load, and exposure risk.
6. Correlate events sharing the same `trace_id` across multiple packages; package-based logging helps filter by source, but **does not replace correlation IDs** for tracing a single request across components.

Increasing a package's level can be done via a configuration change and redeployment, or via dynamic updates if the framework/application supports them; not every runtime automatically reloads configuration files. Verify your specific system's configuration refresh mechanism before relying on it in operations.

## 7. Common Misconceptions

### 7.1. A Package Declaration in Code Does Not Create Logger Configuration

The statement `package com.example.orders;` does not automatically create a logger or emit any records. You must use a logging API to obtain a logger object, call event-logging methods, and have a suitable backend/handler. In JUL, loggers are typically obtained with `Logger.getLogger(...)`; in SLF4J, through `LoggerFactory`.

### 7.2. "Parent–Child" Relationships Are Determined by Name

`com.example.orders.internal` can sit under `com.example.orders` in the logger tree by the dot rule, even if the physical Java files live in different locations or the classes are compiled from generated sources. Conversely, if you use an arbitrary logger name like `billing.debug` inside a class in `com.example.orders`, configuration for `com.example.orders` will not automatically apply to `billing.debug`.

### 7.3. A Package-Based Logger Does Not Guarantee Every Class Logs

Each class still must use a logger and call the appropriate levels. If a class throws an exception and no handling path logs it, raising the package level alone will not produce new records. Adding too many logs also does not make a system "more observable" if the content lacks meaning, is duplicated, or leaks secrets.

### 7.4. Java Packages Are Not Java Modules

The Java Platform Module System (JPMS) has its own concepts of modules and packages. Logger configuration for `com.example.orders` is normally based on the **logger name**, and does not automatically partition by `module-info.java` or module boundaries. When you need separation by module, runtime, or service, you must add appropriate context or policy.

### 7.5. Renaming a Package Can Change the Log Source

Refactoring a class from `com.example.orders` to `com.example.checkout` changes `getPackageName()` and `getName()`. Level configurations and filters based on the old name may no longer apply. After refactoring, update configurations, dashboards, collector filters, and related tests.

### 7.6. Beware of the Default Package

A class without a `package` declaration in the *unnamed package* returns an empty string for `getPackageName()`. Avoid using the default package in real applications because an empty logger name and lack of namespace organization are unclear. Use a stable package naming convention.

### 7.7. Logger Names Are Not a Security Boundary

Renaming loggers or separating packages does not prevent another application from reading log files. Access permissions, what data gets logged, retention policies, and transport controls remain separate security mechanisms. In particular, audit logs should not rely solely on logger package names for integrity.

### 7.8. Creating Unbounded Loggers from Dynamic Data Increases Overhead

`Logger.getLogger("orders." + orderId)` creates many logger names; besides making configuration difficult, it consumes memory and metadata in the backend and loses stable grouping. Use a class- or package-based `logger name`, and place `orderId` in the event context after evaluating sensitive-data concerns.

## 8. Common Issues and How to Check Them

| Symptom | Possible Cause | Verification Step |
| --- | --- | --- |
| Enabled `FINE` for a package but no logs appear | Child logger has a higher level, handler limits to `INFO`, or code does not emit `FINE` | Check effective level of source logger, handler level/filter, and loaded runtime config. |
| A single log appears twice in the console | Handlers on both child and parent loggers with propagation enabled | Check `useParentHandlers` or `additivity`, and where appenders/handlers are attached. |
| Enabled verbose logging for package A, but B also emits many logs | Rule set on root, or both A and B use the same shared logger name | Print logger names and verify the exact package and level for each branch. |
| Logs from a new class do not follow old configuration | Package/class name changed or logger uses a custom name | Compare `getLogger(...)` in code against the name in configuration. |
| Only `WARN` appears in file while console shows `INFO` | File destination has a higher level/filter | Check each handler/appender, not just logger levels. |
| Child `INFO` logs still reach a parent handler with a lower threshold | Child logger accepted the record and parent handler allows it | Distinguish parent logger level from handler threshold. |
| Package records disappear after a configuration change | Propagation accidentally disabled or required appender removed | Test sample log routing before and after deployment. |

A useful test is to prepare a **package x log level x output channel** matrix. Emit a few sample records at `FINE`, `INFO`, and `WARNING` from each package; verify exactly which lines reach the console, file, or collector. At the same time, ensure no sensitive content remains and no logs are duplicated unintentionally.

## 9. Practice Exercise

An application uses JUL with the following loggers:

```text
app                 level = INFO, handler console level = ALL
app.catalog         level = null
app.catalog.cache   level = FINE
app.checkout        level = WARNING
```

Child loggers have `useParentHandlers=true`, while `app` has `useParentHandlers=false`. No child logger has its own handler. Determine whether each of the following lines reaches `app`'s console:

| Source | Log Level | Message |
| --- | --- | --- |
| `app.catalog` | `INFO` | `catalog.loaded` |
| `app.catalog` | `FINE` | `catalog.debug` |
| `app.catalog.cache` | `FINE` | `cache.miss` |
| `app.checkout` | `INFO` | `checkout.started` |
| `app.checkout` | `SEVERE` | `checkout.failed` |

**Answers:**

- `app.catalog / INFO`: **yes**, because it inherits `INFO` from `app` and the handler accepts all levels.
- `app.catalog / FINE`: **no**, because the source logger's effective level is `INFO`, so it does not create `FINE` records.
- `app.catalog.cache / FINE`: **yes**, because the child logger sets `FINE` and the parent handler allows `ALL`. The `INFO` level of logger `app` does not re-filter the record.
- `app.checkout / INFO`: **no**, because the checkout logger sets `WARNING`.
- `app.checkout / SEVERE`: **yes**, because it exceeds the `WARNING` threshold and the handler allows it.

If `app`'s handler is changed to `WARNING`, the `INFO` and `FINE` lines above will not be printed even though some loggers still accept creating them. This shows that **package-based configuration primarily controls the source**, while handlers/appenders and propagation rules determine the final output.

To check your understanding, answer in your own words: Why can choosing a class-named logger still be configured by package? When renaming a package, which configurations need to be reviewed? And when logs go "missing," how do you determine whether they were blocked at the source logger or at the destination handler?

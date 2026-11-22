# Hands-on Project: Per-Package Logger Configuration in Java 17

## 1. Objectives and Expected Outcomes

A real-world Java application has multiple packages: order processing, payments, audit, external integrations, and infrastructure. Each group requires a different logging level. When investigating an order issue, we can enable detailed logging for the **orders package** without turning on DEBUG for the entire JVM or logging unnecessary payment data.

This project helps you:

1. Build a Java 17 project with genuinely separated packages.
2. Create loggers using the fully qualified class name so the logger hierarchy matches Java packages.
3. Configure the root level and per-package levels via **config/logging.properties**.
4. Compile and run with **javac/java**, without needing Maven or external libraries.
5. Read deterministic output and understand why some events are logged while others are blocked.
6. Write a program to verify the policy: logger level, inheritance, and handler threshold.
7. Distinguish between **log level selection** and **log routing**.
8. Learn how to express the same policy using Logback, Log4j2, and Spring Boot.
9. Evaluate common mistakes, security, performance, test isolation, and safe level-change procedures.

**Topic:** Per-package logger configuration. **Context:** Hands-on project in Java Core Logging. The entire main project uses **java.util.logging (JUL)** from the JDK. The Logback/Log4j2/Spring Boot versions in later sections are **alternative options** requiring their corresponding dependencies/backends; do not mix their configuration syntax into the JUL project.

## 2. Simulated Business Requirements

The demo application calls three services in sequence:

~~~text
App
 |
 +-- OrderService.reserve("O-101")
 |     +-- FINE: order.reserve.validate
 |     +-- INFO: order.reserved
 |
 +-- PaymentService.authorize("O-101")
 |     +-- FINE: payment.authorize.start
 |     +-- INFO: payment.authorized
 |     +-- WARNING: payment.gateway.slow
 |
 +-- AuditService.record("O-101")
       +-- INFO: audit.recorded
~~~

These operations only **emit illustrative logs**—they do not call a database, persist transactions, or perform real payment or audit operations.

Policy:

| Logger Scope | Applied Level | Expectation |
| --- | --- | --- |
| Root logger | INFO | Logs INFO and above by default. |
| demo.shop.orders | FINE | Logs FINE and INFO to debug order business logic. |
| demo.shop.payments | WARNING | Logs only WARNING/SEVERE; blocks FINE and INFO. |
| demo.shop.audit | INFO | Logs simulated INFO audit events. |
| ConsoleHandler | ALL | Does not further filter events that passed the source logger. |

After running App, we want to see exactly four log events:

~~~text
FINE demo.shop.orders.OrderService order.reserve.validate orderId=O-101
INFO demo.shop.orders.OrderService order.reserved orderId=O-101
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
INFO demo.shop.audit.AuditService audit.recorded orderId=O-101
~~~

The two events from PaymentService at FINE and INFO **do not appear** because the payments package is set to WARNING. These results come from **level configuration**, not from removing logger calls from the code.

## 3. Understanding the Logger Hierarchy

### 3.1. Logger Names and Package Names

In Java, common practice is:

~~~java
// Example in a class named OrderService.
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(
                OrderService.class.getName());
~~~

If the class name is **demo.shop.orders.OrderService**, the corresponding logger is named **demo.shop.orders.OrderService**. Therefore, a level configured for **demo.shop.orders** can be inherited.

Loggers are organized by dot-separated name chains:

~~~text
root
  |
  +-- demo
       |
       +-- shop
            |
            +-- orders           FINE
            |    +-- OrderService (inherited)
            |
            +-- payments         WARNING
            |    +-- PaymentService (inherited)
            |
            +-- audit            INFO
                 +-- AuditService (inherited)
~~~

Java package names and logger categories are not strictly bound by the JVM. If a class in the orders package calls `Logger.getLogger("business")`, the logger named `business` **does not automatically inherit** the `demo.shop.orders` policy.

**Recommendation:** Create loggers from **Class.getName()** or a consistent naming convention. When refactoring packages, review the logging configuration as well so no rules are left with outdated names.

### 3.2. Configured Level vs. Effective Level

A child logger without its own configured level can inherit the level from its nearest ancestor that has a level set. In JUL, **Logger.getLevel() == null** usually means the logger inherits its level, **not OFF**.

For example, with root at INFO, orders at FINE, and no class-level override on OrderService: OrderService has an **effective level of FINE**. PaymentService inherits WARNING.

### 3.3. Basic Levels in JUL

| Level | Standard intValue | Common Meaning |
| --- | ---: | --- |
| SEVERE | 1000 | Serious failure. |
| WARNING | 900 | Potential problem. |
| INFO | 800 | Informational operational message. |
| CONFIG | 700 | Static configuration information. |
| FINE | 500 | Tracing information for debugging. |
| FINER | 400 | More detailed tracing information. |
| FINEST | 300 | Highly detailed tracing information. |
| OFF | Integer.MAX_VALUE | Turns off logging at that threshold. |
| ALL | Integer.MIN_VALUE | Enables all messages at that threshold. |

FINE is roughly analogous to DEBUG, WARNING to WARN, and SEVERE to ERROR in purpose. **Do not assume every JUL → SLF4J/Log4j2 bridge maps levels identically** without testing the actual provider.

### 3.4. Logger Level vs. Handler Level

This is the most important mechanism:

~~~text
OrderService calls LOG.fine(...)
            |
            v
Logger effective level FINE
    → accepts FINE event
            |
            v
ConsoleHandler.level
    +-- ALL: accepts FINE event
    +-- INFO: drops FINE event
            |
            v
Formatter and stderr
~~~

Once the source logger accepts an event, propagating it up to parent handlers in JUL **does not necessarily re-filter using the parent logger's level**. Each **Handler** still has its own threshold and Filter. Therefore, setting root to INFO does not automatically block FINE events from the FINE-configured orders package if the root handler is set to ALL.

Logback behaves similarly: a DEBUG event accepted by a child logger can reach the root appender via additivity even if the root logger is set to INFO; the appender's threshold/filter decides whether to filter it further.

## 4. Project Structure

Create the **package-logger-demo** directory:

~~~text
package-logger-demo/
├── config/
│   └── logging.properties
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           └── shop/
│   │               ├── App.java
│   │               ├── orders/
│   │               │   └── OrderService.java
│   │               ├── payments/
│   │               │   └── PaymentService.java
│   │               └── audit/
│   │                   └── AuditService.java
│   └── test/
│       └── java/
│           └── demo/
│               └── shop/
│                   └── LogPolicyProbe.java
└── out/        (create before compiling)
~~~

**Four source files in main** form the application. **LogPolicyProbe.java** is a plain Java test harness requiring no JUnit. Every package declaration must match its source directory.

All code below targets JDK 17; levels and handlers are supplied via a configuration file so we **avoid hard-coding runtime configuration in business methods**.

## 5. Creating the Main Source Code

### 5.1. App.java

Path: **src/main/java/demo/shop/App.java**

~~~java
package demo.shop;

import demo.shop.audit.AuditService;
import demo.shop.orders.OrderService;
import demo.shop.payments.PaymentService;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        String orderId = "O-101";

        OrderService orders = new OrderService();
        PaymentService payments = new PaymentService();
        AuditService audit = new AuditService();

        orders.reserve(orderId);
        payments.authorize(orderId);
        audit.record(orderId);
    }
}
~~~

App does not write to `System.out`. Each service uses only a logger. Calls execute **sequentially on a single thread**, making the output predictable.

### 5.2. OrderService.java

Path: **src/main/java/demo/shop/orders/OrderService.java**

~~~java
package demo.shop.orders;

import java.util.logging.Logger;

public final class OrderService {

    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void reserve(String orderId) {
        LOG.fine("order.reserve.validate orderId=" + orderId);
        LOG.info("order.reserved orderId=" + orderId);
    }
}
~~~

With the orders package at FINE, both FINE and INFO are permitted. These are simulated business/diagnostic events and do not prove a database commit occurred.

### 5.3. PaymentService.java

Path: **src/main/java/demo/shop/payments/PaymentService.java**

~~~java
package demo.shop.payments;

import java.util.logging.Logger;

public final class PaymentService {

    private static final Logger LOG =
            Logger.getLogger(PaymentService.class.getName());

    public void authorize(String orderId) {
        LOG.fine("payment.authorize.start orderId=" + orderId);
        LOG.info("payment.authorized orderId=" + orderId);
        LOG.warning("payment.gateway.slow orderId=" + orderId);
    }
}
~~~

The payments package is set to WARNING, so FINE and INFO are dropped. WARNING appears on the terminal. In a real application, logging `"gateway.slow"` should only happen when measured latency exceeds a threshold, rather than emitting a WARNING on every request.

### 5.4. AuditService.java

Path: **src/main/java/demo/shop/audit/AuditService.java**

~~~java
package demo.shop.audit;

import java.util.logging.Logger;

public final class AuditService {

    private static final Logger LOG =
            Logger.getLogger(AuditService.class.getName());

    public void record(String orderId) {
        LOG.info("audit.recorded orderId=" + orderId);
    }
}
~~~

This is **not a real audit store**. A system requiring durable, tamper-evident, or guaranteed-delivery auditing needs dedicated infrastructure rather than relying solely on `ConsoleHandler`.

## 6. Configuring logging.properties

Path: **config/logging.properties**

~~~properties
# A ConsoleHandler attached to the root logger.
handlers=java.util.logging.ConsoleHandler

# Default level for loggers without an override.
.level=INFO

# Handler accepts all events permitted by the source logger.
java.util.logging.ConsoleHandler.level=ALL
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

# %4$s: level; %3$s: logger name; %5$s: message;
# %6$s: throwable; %n: newline.
java.util.logging.SimpleFormatter.format=%4$s %3$s %5$s%6$s%n

# Per-package levels.
demo.shop.orders.level=FINE
demo.shop.payments.level=WARNING
demo.shop.audit.level=INFO
~~~

How to read this file:

- **handlers** attaches `ConsoleHandler` to the root logger.
- **.level** sets the default level for root.
- **ConsoleHandler.level=ALL** prevents the handler from dropping FINE events already allowed by the orders logger.
- **ConsoleHandler.formatter** selects the JDK's `SimpleFormatter`.
- **SimpleFormatter.format** fixes a single-line format of `level logger-name message`, without timestamp or hostname.
- The three **demo.shop.<module>.level** properties determine the threshold per namespace.

**Do not confuse syntaxes:** JUL uses `FINE`/`WARNING`/`SEVERE`. SLF4J/Logback uses `DEBUG`/`WARN`/`ERROR`. You cannot replace `FINE` with `DEBUG` in JUL `logging.properties` and expect the JDK to understand it.

### 6.1. Why Use SimpleFormatter Instead of the Default?

The default formatter can print timestamps, source locations, and other details; this is useful in production but makes exact output harder to verify while learning.

In this sample project, the format **%4$s %3$s %5$s%6$s%n** is based on the `SimpleFormatter` API: `%4$s` is the log level, `%3$s` is the logger name, `%5$s` is the formatted message, `%6$s` is the `Throwable` and stack trace (if any), and `%n` is a newline. The example emits no `Throwable`, so each event takes one line.

Do not use this pattern as a mandatory production format: real systems should include UTC timestamps, service/environment, correlation ID, event name, structured fields/encoding, and proper access controls.

### 6.2. ConsoleHandler Writes to stderr

JUL `ConsoleHandler` outputs to **System.err**. Therefore, the four lines in this guide go to **stderr**, not stdout. If a CI or test runner only captures stdout, it may miss them. Level tests are better off using an in-memory `Handler` or capturing the proper stream.

## 7. Compiling and Running the Project

Open a terminal in the **package-logger-demo** directory. Create `out`:

~~~bash
mkdir out
~~~

Compile the four Java files (single line; avoid relying on shell line-continuation):

~~~bash
javac -encoding UTF-8 -d out src/main/java/demo/shop/App.java src/main/java/demo/shop/orders/OrderService.java src/main/java/demo/shop/payments/PaymentService.java src/main/java/demo/shop/audit/AuditService.java
~~~

Start a new JVM with the logging config file explicitly specified:

~~~bash
java -Djava.util.logging.config.file=config/logging.properties -cp out demo.shop.App
~~~

**Expected four log lines on stderr:**

~~~text
FINE demo.shop.orders.OrderService order.reserve.validate orderId=O-101
INFO demo.shop.orders.OrderService order.reserved orderId=O-101
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
INFO demo.shop.audit.AuditService audit.recorded orderId=O-101
~~~

This result assumes JDK 17+, running from the project root directory, `logging.properties` being loaded, and no external system property overriding the formatter configuration.

### 7.1. Explaining the Output

- **orders FINE:** the `order.reserve.validate` event is kept.
- **orders INFO:** higher than FINE, so it is kept.
- **payments FINE:** lower than WARNING, so it is dropped.
- **payments INFO:** lower than WARNING, so it is dropped.
- **payments WARNING:** meets the threshold, so it is kept.
- **audit INFO:** meets the INFO threshold, so it is kept.

In total, the code calls the logger **six times**, and the terminal shows **four events**. It is not that `PaymentService` skipped the first two statements; the logger blocked them according to the configuration.

### 7.2. Why Is -Djava.util.logging.config.file Needed?

JUL `LogManager` reads configuration properties using this mechanism. This JVM argument points to the project's file instead of relying on the JDK's default configuration. You must place **-D... before the main class name**.

Simply compiling the class files does not make Java automatically discover `config/logging.properties`. If running the app in an IDE, ensure the IDE uses the same working directory and JVM arguments.

### 7.3. Does Editing properties Require Recompiling?

Not necessarily. If you only change **logging.properties**, a new JVM will load the updated configuration without recompiling. For a long-running application, editing the file on disk **does not automatically hot-reload** into `LogManager` by default; it requires a controlled reload mechanism or a restart.

If you edit Java source files or rename packages, you must recompile and verify the logger/config namespaces.

## 8. Creating the Test Harness LogPolicyProbe.java

Path: **src/test/java/demo/shop/LogPolicyProbe.java**

This program verifies the policy using actual JUL behavior:

- The orders logger allows FINE.
- The payments logger blocks INFO.
- The payments logger still allows WARNING.
- The audit logger allows INFO.
- A WARNING handler captures only WARNING when the orders logger emits FINE/INFO/WARNING.

We avoid the Java `assert` keyword because it can be disabled by default in the JVM unless `-ea` is passed. The program explicitly throws `AssertionError` when a condition fails.

~~~java
package demo.shop;

import demo.shop.audit.AuditService;
import demo.shop.orders.OrderService;
import demo.shop.payments.PaymentService;

import java.util.ArrayList;
import java.util.List;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class LogPolicyProbe {

    private LogPolicyProbe() {
    }

    private static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    private static final class CaptureHandler extends Handler {
        private final List<String> events = new ArrayList<>();

        @Override
        public void publish(LogRecord record) {
            if (isLoggable(record)) {
                events.add(record.getLevel().getName()
                        + ":" + record.getMessage());
            }
        }

        @Override
        public void flush() {
            // No I/O.
        }

        @Override
        public void close() {
            // Only stores the list in memory.
        }

        List<String> captured() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args) {
        Logger orders = Logger.getLogger(
                OrderService.class.getName());
        Logger payments = Logger.getLogger(
                PaymentService.class.getName());
        Logger audit = Logger.getLogger(
                AuditService.class.getName());

        check("orders FINE allowed",
                orders.isLoggable(Level.FINE));
        check("payments INFO blocked",
                !payments.isLoggable(Level.INFO));
        check("payments WARNING allowed",
                payments.isLoggable(Level.WARNING));
        check("audit INFO allowed",
                audit.isLoggable(Level.INFO));

        Logger ordersPackage = Logger.getLogger(
                "demo.shop.orders");
        boolean oldParentUse =
                ordersPackage.getUseParentHandlers();

        CaptureHandler capture = new CaptureHandler();
        capture.setLevel(Level.WARNING);
        ordersPackage.setUseParentHandlers(false);
        ordersPackage.addHandler(capture);

        try {
            orders.fine("probe.fine");
            orders.info("probe.info");
            orders.warning("probe.warning");

            check("handler WARNING filters",
                    capture.captured().equals(
                            List.of("WARNING:probe.warning")));
        } finally {
            ordersPackage.removeHandler(capture);
            capture.close();
            ordersPackage.setUseParentHandlers(oldParentUse);
        }

        System.out.println("ALL 5 CHECKS PASSED");
    }
}
~~~

### 8.1. Running the Test

After compiling main, compile and run the probe:

~~~bash
javac -encoding UTF-8 -cp out -d out src/test/java/demo/shop/LogPolicyProbe.java
java -Djava.util.logging.config.file=config/logging.properties -cp out demo.shop.LogPolicyProbe
~~~

**Expected stdout:**

~~~text
PASS orders FINE allowed
PASS payments INFO blocked
PASS payments WARNING allowed
PASS audit INFO allowed
PASS handler WARNING filters
ALL 5 CHECKS PASSED
~~~

The probe keeps test events from spilling into the root `ConsoleHandler`: it attaches an in-memory `Handler` to the `orders` package logger and disables parent handlers on that package **for the duration of the test**, then restores the state in `finally`.

### 8.2. Meaning of Each Check

| Check | Layer Verified |
| --- | --- |
| orders FINE allowed | Effective logger level of `OrderService`. |
| payments INFO blocked | Policy disallowing INFO in the payments package. |
| payments WARNING allowed | Positive control: payments is not completely OFF. |
| audit INFO allowed | Audit package permits INFO business events. |
| handler WARNING filters | Handler further filters events already accepted by the orders logger. |

A test that only checks a class's **Logger.getLevel()** can fail because `getLevel() == null` indicates inheritance. **Logger.isLoggable** verifies whether the logger permits the level, though it still does not guarantee that a Handler/Appender actually wrote the event. The fifth check covers that part.

### 8.3. Test Isolation

`CaptureHandler` is a resource attached to a **shared named logger**. Even though this test does not modify root, it must remove the `Handler` and restore `useParentHandlers` in `finally` to avoid affecting other cases. In parallel test suites, avoid mutating the same logger namespace from multiple tests concurrently.

## 9. Exercise: Changing orders Level from FINE to INFO

In **config/logging.properties**, change:

~~~properties
demo.shop.orders.level=INFO
~~~

Run `App` in a new JVM. The `FINE` line from `OrderService` disappears. The remaining output is:

~~~text
INFO demo.shop.orders.OrderService order.reserved orderId=O-101
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
INFO demo.shop.audit.AuditService audit.recorded orderId=O-101
~~~

Running `LogPolicyProbe` will **fail** at **orders FINE allowed**, which is expected because the active policy no longer matches the baseline test criteria.

If this is an intentional and approved change, update the test alongside the new policy. Never modify a test just to hide an accidental loss of DEBUG logging in configuration.

## 10. Exercise: Changing payments from WARNING to INFO

Change in the config:

~~~properties
demo.shop.payments.level=INFO
~~~

Keep orders at FINE and audit at INFO as before. When running `App`, the following line appears before WARNING:

~~~text
INFO demo.shop.payments.PaymentService payment.authorized orderId=O-101
~~~

The total number of log events becomes **five**. `FINE` from payments is still blocked because it is below INFO. `LogPolicyProbe` will fail at **payments INFO blocked**: the test is protecting the previous policy where payments only allows WARNING.

In real systems, a package should not automatically be set to WARNING if doing so drops important business events. Choose levels based on operational policy rather than applying this pattern mechanically.

## 11. Exercise: Handler Filtering Logs Allowed by the Logger

Change:

~~~properties
java.util.logging.ConsoleHandler.level=WARNING
~~~

With baseline package levels, `ConsoleHandler` only accepts WARNING and above. The result on stderr is:

~~~text
WARNING demo.shop.payments.PaymentService payment.gateway.slow orderId=O-101
~~~

Notice that **OrderService still has a FINE logger** and can emit FINE/INFO events, and **AuditService still has an INFO logger**, yet `ConsoleHandler` drops those events. This illustrates why "a logger has level FINE" does not mean "the console displays FINE."

If the probe runs, all four `isLoggable` checks can still PASS because they observe the **logger**, not `ConsoleHandler`. The in-memory WARNING handler test also passes because it uses its own handler threshold.

## 12. Exercise: A Package Without Its Own Configuration

Suppose you create an additional file:

~~~java
package demo.shop.shipping;

import java.util.logging.Logger;

public final class ShippingService {
    private static final Logger LOG =
            Logger.getLogger(ShippingService.class.getName());

    public void ship(String orderId) {
        LOG.fine("shipping.check orderId=" + orderId);
        LOG.info("shipping.scheduled orderId=" + orderId);
    }
}
~~~

This is an **optional exercise** not called by the baseline `App`. If you create the file, call `ship()`, and recompile, the logger under **demo.shop.shipping** has no override and inherits root INFO: `shipping.check` (FINE) is blocked and `shipping.scheduled` (INFO) is logged.

If you want to debug shipping specifically, add:

~~~properties
demo.shop.shipping.level=FINE
~~~

Do not switch root to FINE just to debug shipping, as that increases verbose logging across many unrelated packages.

## 13. Exercise: Overriding at the Class Level

Sometimes only a single class needs debugging:

~~~properties
demo.shop.orders.level=INFO
demo.shop.orders.OrderService.level=FINE
~~~

With this, `OrderService` gets FINE, while other classes under `demo.shop.orders` without their own override continue to inherit INFO. This narrows the scope compared to enabling FINE for the entire orders package.

A logger category created with a literal string different from the class name may not be affected by this rule. When a test fails, inspect the actual **logger.getName()**.

## 14. Distinguishing Per-Package Level vs. Routing

Level configuration:

~~~text
orders FINE    ──> decides which events are allowed
payments WARN  ──> decides which events are allowed
~~~

Routing:

~~~text
orders events   ──> Console / orders.log / collector
payments events ──> Console / payments.log / collector
~~~

**A property `demo.shop.orders.level=FINE` does not automatically create `orders.log`.** If you need a separate file, you must configure a corresponding `FileHandler` or appender, attach it to the right logger/category, and choose parent propagation behavior.

In JUL:

- **Logger.setUseParentHandlers(true)**: can forward events to parent handlers.
- **Logger.setUseParentHandlers(false)**: stops forwarding to parent handlers.
- Handlers also have their own **setLevel** and **Filter**.
- If you disable parent handlers without attaching a replacement handler, events may go nowhere even when the logger allows them.
- If you attach two handlers pointing to the same sink while keeping parent propagation enabled, duplicate logs can appear.

When extending this exercise to log files, manage file paths, rotation, permissions, retention, and close/flush. Do not treat a file appender as an exactly-once delivery guarantee.

## 15. Duplicate Logs: Distinguishing Two Causes

**Cause A — routing duplicate:** the same `LogRecord` passes through two handlers/appenders sharing the same output sink. Fix this by designing the hierarchy and parent propagation/additivity properly.

**Cause B — code emitting multiple events:** the repository logs ERROR and throws, the service logs ERROR and throws, and the controller logs ERROR again for the same exception. Those are three separate logging calls. Disabling additivity will not fix this; you must define **one boundary responsible for the terminal failure log**.

When investigating, use trace ID/request ID, logger name, event name, and `Throwable` cause to tell whether one event was emitted twice or multiple events were created across layers.

## 16. Extending to SLF4J + Logback

In many Java applications, code uses the **SLF4J API** with a **Logback** backend. The policy concept is the same, but level names and configuration files differ:

- JUL uses `FINE`, `WARNING`, `SEVERE` and `logging.properties`.
- Logback/SLF4J typically uses `DEBUG`, `WARN`, `ERROR` and `logback.xml`.
- SLF4J `LoggerFactory.getLogger(OrderService.class)` creates a logger named after the class.

Illustrative code when the project has SLF4J dependencies:

~~~java
package demo.shop.orders;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void reserve(String orderId) {
        LOG.debug("order.reserve.validate orderId={}", orderId);
        LOG.info("order.reserved orderId={}", orderId);
    }
}
~~~

This is an **alternative implementation**—do not share the class file with the JUL version in Section 5; it requires compatible SLF4J API and Logback provider dependencies.

Example **src/main/resources/logback.xml**:

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="demo.shop.orders" level="DEBUG"/>
    <logger name="demo.shop.payments" level="WARN"/>
    <logger name="demo.shop.audit" level="INFO"/>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

In this setup, only root has an appender attached, and package loggers let events flow to root via default **additivity**. Once the `orders` logger at DEBUG accepts a DEBUG event, root INFO does not re-filter it during appender propagation; if you want the console to accept only INFO and above, add a **ThresholdFilter** on the appender.

### 16.1. Logback Additivity and Duplicate Records

If you attach the `CONSOLE` appender to the `orders` logger while root also attaches `CONSOLE`, `additivity=true` can cause the same event to appear twice. To separate routes, set `additivity=false` **when the child logger has its own appender**. Never set `false` and forget the appender, or events will not reach root.

**Effective level** and **additivity** are distinct concepts: one decides whether the source logger allows the event, while the other controls appender inheritance.

## 17. Extending to Log4j2

An application with Log4j2 API/Core or an appropriate SLF4J provider can use **log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout pattern="%level %logger - %msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Logger name="demo.shop.orders" level="debug"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Logger name="demo.shop.payments" level="warn"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Logger name="demo.shop.audit" level="info"
                additivity="false">
            <AppenderRef ref="CONSOLE"/>
        </Logger>
        <Root level="info">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Each package logger has its own `CONSOLE` appender and **additivity=false**, so it does not forward the event to root a second time. Another approach is attaching the appender only on root and keeping `additivity=true`.

Do not copy Logback XML into Log4j2: `LoggerConfig`, `AppenderRef`, `Filter`, and the schema are different. Nor should you expect a Log4j2 file to control a JUL project without an appropriate bridge/backend.

## 18. Spring Boot: Per-Package Configuration

In a **Spring Boot** application, you can declare:

~~~properties
logging.level.root=INFO
logging.level.demo.shop.orders=DEBUG
logging.level.demo.shop.payments=WARN
logging.level.demo.shop.audit=INFO
~~~

Or in **application.yml**:

~~~yaml
logging:
  level:
    root: INFO
    demo.shop.orders: DEBUG
    demo.shop.payments: WARN
    demo.shop.audit: INFO
~~~

This configuration is for the **Spring Boot logging system**, not the plain JUL file from Section 6. Spring Boot integrates the logging backend and property sources across profiles, environment variables, command-line arguments, and runtime configuration.

### 18.1. Dev/Test/Staging/Prod

An illustrative policy:

| Environment | Root | Orders | Payments |
| --- | --- | --- | --- |
| dev | INFO | DEBUG | INFO |
| test | INFO | DEBUG or intentional INFO | WARN |
| staging | INFO | INFO | WARN |
| prod | INFO | INFO | WARN |

This is a suggestion, **not a mandatory default**. For critical payment events, do not suppress all INFO logs simply because the table above lists WARN; choose severities that match business requirements.

### 18.2. Runtime Overrides

An environment variable such as **LOGGING_LEVEL_ROOT** can override the root level via Spring Boot's configuration mechanism. Actuator **/actuator/loggers**, if installed and safely enabled, allows reading and changing logger levels at runtime.

Restrict changes to authorized operators, record the previous level, and restore it after investigation. Never expose logging management endpoints publicly; keep DEBUG narrow and time-bound.

A test that only reads an `Environment` property **does not prove** the actual backend/appender emitted the event properly. Verify both the effective logger level and captured output.

## 19. Testing Logback/Log4j2 in Real Projects

With Logback + JUnit 5, you can attach a **ListAppender** to capture `ILoggingEvent` instances and assert:

- DEBUG appears when orders is DEBUG.
- DEBUG does not appear when orders is INFO.
- Important WARN/ERROR events are still present.
- The logger name matches the expected package.
- The exception cause is preserved when needed.
- No unexpected duplicates occur.
- The appender is detached and the level is restored in `finally`.

Snippet (requires JUnit/Logback imports and dependencies):

~~~java
// Illustration, not a standalone program.
Logger logger = (Logger) LoggerFactory.getLogger(
        "demo.shop.orders.OrderService");

Level oldLevel = logger.getLevel();
ListAppender<ILoggingEvent> capture = new ListAppender<>();
capture.start();
logger.addAppender(capture);

try {
    logger.setLevel(Level.INFO);
    logger.debug("should-not-appear");
    logger.info("visible");
    // Assert capture.list has one INFO event and no DEBUG.
} finally {
    logger.detachAppender(capture);
    capture.stop();
    logger.setLevel(oldLevel);
}
~~~

An in-memory `ListAppender` does not verify production `FileAppender`/`ConsoleAppender` or collectors; write separate integration tests for those. Do not run multiple tests in parallel that mutate levels or the root logging context without isolation.

## 20. Structured Logs, MDC, and Context

A per-package logger helps select levels and routing, but it does not automatically supply **trace ID, request ID, or business event ID**. Structured log data might look like this:

~~~json
{
  "timestamp": "2026-11-10T03:00:00Z",
  "service.name": "shop-service",
  "logger.name": "demo.shop.orders.OrderService",
  "severity_text": "INFO",
  "event": "order.reserved",
  "order_id": "O-101",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736"
}
~~~

This is illustrative JSON, **not the default output of JUL SimpleFormatter**. Systems using OpenTelemetry/MDC must propagate context properly across threads, HTTP, and messaging.

**Security:** Never log passwords, tokens, API keys, cookies, raw request bodies, or payment details just because DEBUG/FINE is enabled for a package. DEBUG disabled in production today can be turned on tomorrow. Unnecessary sensitive data must be excluded at the **source**, not just filtered at the collector.

For client-controlled input, validate the grammar and length of `requestId`/`orderId` and escape CRLF to prevent log injection. Any tenant ID used for read authorization or routing must come from authenticated context, not self-reported headers.

## 21. Performance and Reliability

When enabling FINE/DEBUG for a package with many classes, log volume can spike sharply:

- Each request traverses multiple methods and retries.
- Stack traces and JSON fields inflate record size.
- Console/file/collector pipelines increase CPU, disk I/O, and network usage.
- Async queues can fill up, drop events, or cause backpressure.
- Central log indexing incurs higher cost and ingestion latency.

With 10,000 requests/second and 20 extra DEBUG records per request, that adds **200,000 records/second** in a simple model. Do not leave broad debug logging enabled for long periods just to investigate a narrow issue.

A sound operational policy:

1. Keep root at INFO or an approved baseline level.
2. Increase verbosity on **a specific package or class**.
3. Set a time limit or restoration condition.
4. Monitor rate/bytes, dropped events, queue depth, and ingestion lag.
5. Do not use log counts as exact request counts if the pipeline performs sampling or dropping.
6. Never change logging settings in a way that drops mandatory security/audit events.
7. Verify appender/collector/storage capacity and retention policies.

## 22. Common Mistakes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Set orders to FINE, still no FINE | `ConsoleHandler` is still INFO; config not loaded; wrong logger name. | Check JVM `-D` arg, handler level, `isLoggable`. |
| `Logger.getLevel()` returns null | Child logger inherits its level. | Test effective behavior; do not treat null as OFF. |
| DEBUG appears despite root INFO | Child logger overrides to DEBUG and appender receives via propagation. | Inspect the source logger's effective level. |
| Payments INFO still appears | Misnamed package rule or class-level override. | Compare `logger.getName()` with the property key. |
| One log appears twice | Parent handlers/additivity and multiple appenders on the same sink. | Redesign routing; count per sink. |
| Package produces no logs | Parent propagation disabled without a dedicated handler. | Attach a handler or enable propagation. |
| Config file has no effect | Wrong file path or a different logging backend is active. | Verify JVM args and logging provider. |
| Tests capture only stdout | JUL `ConsoleHandler` writes to stderr. | Use an in-memory `Handler` or capture stderr. |
| Production still emits lots of DEBUG | Env/Actuator/runtime override or class-specific level. | Inspect effective configuration after bootstrap. |
| Renaming source packages breaks policy | Config still uses old namespace. | Update package names and add regression tests. |
| App slows down after enabling FINE | Volume/encoder/collector overload. | Narrow debug scope; measure rate and queue depth. |
| Logs leak tokens under DEBUG | Code/encoder logs raw data. | Fix at the source; add sentinel security tests. |

### 22.1. Do Not Fix Issues by Setting Root to DEBUG

If you only need to debug orders, set **demo.shop.orders.level=FINE** instead of **.level=FINE**. Root FINE causes every non-overridden namespace to emit verbose logs, risking overload or data leaks from third-party libraries.

### 22.2. Do Not Use Levels as a Substitute for Routing

Setting a package to DEBUG does not create a separate log file. You need a handler/appender and output tests. If you need durable audit logs, you must also design storage, integrity, access control, and retention; a level property alone cannot achieve this.

### 22.3. Do Not Log and Throw at Every Layer

If repository, service, and controller each log ERROR for the same exception and rethrow, those are multiple independent events created by code—not an additivity bug. Choose one boundary responsible for the terminal error log, preserve the cause/context, and avoid duplication.

## 23. Complete Test Matrix

| Scenario | Source Logger | Handler/Appender | Expectation |
| --- | --- | --- | --- |
| Baseline orders | FINE | ALL | FINE/INFO emitted. |
| Baseline payments | WARNING | ALL | FINE/INFO suppressed; WARNING emitted. |
| Baseline audit | INFO | ALL | INFO emitted. |
| Orders changed to INFO | INFO | ALL | FINE disappears; INFO remains. |
| Payments changed to INFO | INFO | ALL | INFO also emitted; FINE still suppressed. |
| Console changed to WARNING | Orders FINE | WARNING | FINE/INFO do not reach console. |
| Unconfigured shipping package | Inherits root INFO | ALL | Shipping INFO emitted; FINE suppressed. |
| Class override FINE | Package INFO, class FINE | ALL | Only the overridden class emits FINE. |
| Parent propagation false | Logger has own handler | Controlled handler | Does not propagate to root; not lost if sink exists. |
| Parent propagation false, no handler | Logger allows | No sink | Events are not emitted despite matching level. |
| Two appenders sharing console | Logger allows | Duplicate routes | Detect and fix duplication. |
| DEBUG enabled in tests | Narrow-scope logger | Real encoder | No secrets/PII leaked. |
| Async/backpressure collector | Logger allows | Async pipeline | Metrics present; timeout/flush tested. |
| Spring Boot prod profile | Root INFO | Real backend | Package levels match deployment config. |

**Positive and negative assertions must go together.** A test that only checks "DEBUG is absent" can false-pass when all logging is disabled; the test must prove that a valid WARNING/INFO event still reaches the sink.

## 24. Pre-Completion Review Checklist

- [ ] Created **App, OrderService, PaymentService, AuditService** in their proper packages.
- [ ] Placed **config/logging.properties** at a path readable by the JVM.
- [ ] Loggers use `Class.getName()` to stay aligned with packages.
- [ ] Root is INFO and packages are FINE/WARNING/INFO per the baseline policy.
- [ ] `ConsoleHandler` is ALL so it does not accidentally filter FINE.
- [ ] Compiles with JDK 17 without external dependencies.
- [ ] Running `App` produces four log events on stderr.
- [ ] Compiling and running `LogPolicyProbe` produces five PASS lines on stdout.
- [ ] Tested changing orders level, payments level, and handler threshold.
- [ ] Understand the effect of class overrides and package inheritance.
- [ ] Do not confuse a `null` configured level with OFF.
- [ ] Avoided duplicate handlers/appenders or lost events due to additivity.
- [ ] Do not confuse JUL configuration with Logback/Log4j2/Spring Boot.
- [ ] Tests clean up log levels/handlers/MDC when mutating them dynamically.
- [ ] No secrets, tokens, or raw headers/bodies logged when increasing DEBUG.
- [ ] Have a volume/retention policy and verified async/collector behavior if going to production.

## 25. Practice Exercises

1. Run `App` and explain why the code has six logger calls but only four output lines.
2. Run `LogPolicyProbe` and state which policy each check protects.
3. Change orders from FINE to INFO, predict the outcome, and verify the log disappears.
4. Change payments from WARNING to INFO, predict the outcome, and verify the extra log appears.
5. Set `ConsoleHandler` to WARNING; why is `isLoggable(FINE)` on orders still true?
6. Remove the audit override; does it still log INFO due to root INFO?
7. Add `ShippingService`, observe it inheriting root INFO, then override it to FINE individually.
8. Enable FINE only for `OrderService`, keeping another class `OrderValidator` in the orders package at INFO.
9. Configure a `FileHandler` for orders while keeping the root console handler, and check for duplicate logs.
10. Migrate the project to SLF4J/Logback using `logback.xml` with DEBUG for orders and WARN for payments.
11. Do the same with Log4j2 and explain `AppenderRef`/`additivity`.
12. Create `application-dev/prod.properties` in Spring Boot and smoke-test effective levels.
13. Write a test with a dummy token on a request object, enable DEBUG in an isolated environment, and prove the token is not logged.
14. Time-box a package debug session, then restore the configuration and observe the log volume.
15. Distinguish between events created at the logger and events indexed by the collector.

## 26. Summary

**Per-package logger configuration** lets you increase observability in one area of code without flooding the entire application with verbose logs. The Java 17 project using **JUL** demonstrates the full chain: **logger name → hierarchy → effective level → Handler threshold → Formatter → stderr**. The `logging.properties` file changes runtime behavior without modifying business methods.

Three key takeaways:

1. **Per-package logger configuration selects which events are allowed.** Child loggers can inherit or override their parent's level.
2. **Handlers/appenders, filters, and propagation decide where events go.** An event allowed by a logger can still be blocked at the destination, or duplicated across multiple routes.
3. **Testing must cover both allowed and blocked paths**, clean up state, check privacy/security, and verify actual backend configuration.

This same mindset applies to **SLF4J/Logback, Log4j2, and Spring Boot**, provided you use the right level names, config formats, backend dependencies, and operational controls. This hands-on project serves as a foundation before expanding into separate log files, collectors, tracing, production profile testing, and dynamic logger management.

### Official References

- Java SE 17 — Logger: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html
- Java SE 17 — LogManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html
- Java SE 17 — Level: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Level.html
- Java SE 17 — Handler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Handler.html
- Java SE 17 — ConsoleHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/ConsoleHandler.html
- Java SE 17 — SimpleFormatter: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/SimpleFormatter.html
- Logback Architecture — hierarchy/additivity: https://logback.qos.ch/manual/architecture.html
- Logback Configuration: https://logback.qos.ch/manual/configuration.html
- Logback Filters: https://logback.qos.ch/manual/filters.html
- Log4j2 Configuration: https://logging.apache.org/log4j/2.x/manual/configuration.html
- Log4j2 Filters: https://logging.apache.org/log4j/2.x/manual/filters.html
- SLF4J Manual: https://www.slf4j.org/manual.html
- Spring Boot Logging: https://docs.spring.io/spring-boot/reference/features/logging.html
- Spring Boot Actuator loggers: https://docs.spring.io/spring-boot/reference/actuator/loggers.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
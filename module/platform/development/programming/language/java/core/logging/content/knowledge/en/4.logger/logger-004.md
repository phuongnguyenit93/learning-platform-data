# Per-Class Logger in Java

## 1. What is a per-class logger?

A **per-class logger (class-specific logger)** is an approach where each Java class uses a logger object named after **the fully qualified name of that class itself**. This is a common convention to identify which component a log event originated from, while also allowing log levels to be configured per class or per package.

With Java Util Logging (**JUL**, part of the JDK), the familiar declaration is:

~~~java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());
}
~~~

If the class is in the **com.example.orders** package, the logger name is **com.example.orders.OrderService**. When inspecting log records, this name helps quickly identify the relevant class. Log collection tools can use it to filter, group, or search.

An important distinction: **“per-class logger” is a convention for naming and using loggers, not a mechanism for creating a separate log file for each class**. Loggers can all send records to the console, a file, a centralized collector, or a shared Handler. Where logs are written, their format, and filtering conditions are determined by the logging configuration.

Example in an ordering system:

| Class | Typical JUL logger name | Events that can be logged |
| --- | --- | --- |
| **OrderService** | com.example.orders.OrderService | Order creation, status updates, failure handling |
| **PaymentClient** | com.example.payment.PaymentClient | Payment gateway calls, timeouts, retries |
| **InventoryService** | com.example.inventory.InventoryService | Inventory checks, stock reservation |
| **CheckoutController** | com.example.web.CheckoutController | HTTP request start/end at the processing boundary |

A production system typically has many classes and packages, so clear logger names aid investigation without needing to read through source code to guess the event source.

## 2. Why use a logger named after each class?

### Identify the exact source of an event

Compare two log records:

~~~text
INFO | Order status updated
INFO | com.example.orders.OrderService | Order status updated
~~~

The second record provides the **logger name**, allowing the reader to immediately know the component involved. Whether the logger name is output is determined by the **Formatter/layout**: declaring a per-class logger does not automatically guarantee the name will appear in the log.

### Fine-grained log level control

You can enable verbose logging only for **com.example.payment.PaymentClient** when investigating payment errors, while keeping all other loggers at INFO. This reduces noise and logging overhead compared to enabling debug across the entire application.

### Consistent management as the project grows

When every class uses a name from **Class.getName()**, renaming a package or class automatically updates the logger name after compilation. Operations teams can search records by package prefix or specific logger without maintaining an arbitrary list of names.

However, **renaming a class also changes the logger name**, which can affect search rules, dashboards, or log level configurations that depend on the old name. For log identifiers that must remain stable long-term, you should add **structured event codes** rather than relying solely on class names.

### No need to allocate a logger per object

Instances of the same class typically share a single **static final Logger**. For example, creating 1,000 OrderService objects does not require declaring 1,000 separate logger fields. The logger represents **the class's category of events**, while data tied to a specific request or object is passed into the log message or context when needed.

## 3. Detailed breakdown of JUL syntax

~~~java
private static final Logger LOGGER =
        Logger.getLogger(OrderService.class.getName());
~~~

Meaning of each part:

- **private:** Other classes cannot directly access the logger field; each class manages how it emits its own events. Another visibility scope can be used if the architecture truly requires it, but **private** is the standard choice.
- **static:** The field belongs to the class, not created separately per instance. Static methods can also use the logger.
- **final:** The reference variable cannot be reassigned after initialization. **final does not mean the logger is immutable**: its level, Handler, or Filter can still be configured via the API.
- **Logger:** The **java.util.logging.Logger** type, not **org.slf4j.Logger**.
- **Logger.getLogger(String name):** Retrieves a logger by name in the JUL management system.
- **OrderService.class.getName():** Returns the fully qualified name of the class, including the package if present. For nested classes, the JVM name representation may contain the **$** character.

In JUL, the **getLogger** method takes a **String** for this call. The syntax **Logger.getLogger(OrderService.class)** is not a corresponding JUL overload; passing a **Class** directly is the common pattern of **SLF4J LoggerFactory**, which is covered later.

### How do getName() and getSimpleName() differ?

~~~java
String fullName = OrderService.class.getName();
String shortName = OrderService.class.getSimpleName();
~~~

If OrderService is in the **com.example.orders** package:

~~~text
fullName  = com.example.orders.OrderService
shortName = OrderService
~~~

**You should use getName()** because two different packages can easily both have a class named OrderService. If you use getSimpleName(), they may accidentally share the same logger name, losing package context and making separate configuration difficult.

### Class-level or instance-level logger?

In most services, controllers, and repositories, you should use **one static final logger per class**:

~~~java
private static final Logger LOGGER =
        Logger.getLogger(MyService.class.getName());
~~~

If a method simply needs to log an event for MyService, there is no need to look up a logger on every call:

~~~java
public void process() {
    Logger logger = Logger.getLogger(MyService.class.getName());
    logger.info("Processing");
}
~~~

The second snippet still uses a valid API, but it repeats the logger lookup and obscures the convention of a fixed class logger. It generally offers no benefit. Similarly, using **getClass().getName()** from an instance can return a subclass name at runtime; that is a separate architectural choice and is not automatically equivalent to a fixed logger for the declaring class.

## 4. Standalone Java 17 example: two classes, two log levels

The following example uses **java.util.logging** built into the JDK. Two classes have their own loggers named after their class. The program intentionally:

1. Sets the **OrderService** logger to **FINE** to display INFO and FINE.
2. Sets the **PaymentClient** logger to **WARNING** to block INFO while allowing WARNING through.
3. Uses **a shared ConsoleHandler**, formatting the logger name, level, and message.
4. Disables propagation to parent Handlers **only in this example** to prevent default log lines from altering the output.

Create the file **LoggerPerClassDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LoggerPerClassDemo {
    public static void main(String[] args) {
        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLoggerName()
                        + " | " + record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        configure(OrderService.LOGGER, Level.FINE, console);
        configure(PaymentClient.LOGGER, Level.WARNING, console);

        new OrderService().submit("ORD-42");
        new PaymentClient().charge("ORD-42");

        OrderService.LOGGER.removeHandler(console);
        PaymentClient.LOGGER.removeHandler(console);
        console.close();
    }

    private static void configure(Logger logger, Level level, Handler handler) {
        logger.setLevel(level);
        logger.setUseParentHandlers(false);
        logger.addHandler(handler);
    }
}

final class OrderService {
    static final Logger LOGGER = Logger.getLogger(OrderService.class.getName());

    void submit(String orderId) {
        LOGGER.info("Created order " + orderId);
        LOGGER.fine("Validation passed for " + orderId);
    }
}

final class PaymentClient {
    static final Logger LOGGER = Logger.getLogger(PaymentClient.class.getName());

    void charge(String orderId) {
        LOGGER.info("Starting payment for " + orderId);
        LOGGER.warning("Gateway responded slowly for " + orderId);
    }
}
~~~

Run with **JDK 17 or later**, directly in the directory containing the file:

~~~bash
javac -encoding UTF-8 LoggerPerClassDemo.java
java LoggerPerClassDemo
~~~

**Output printed to stderr** (ConsoleHandler writes to stderr by default, not stdout):

~~~text
OrderService | INFO | Created order ORD-42
OrderService | FINE | Validation passed for ORD-42
PaymentClient | WARNING | Gateway responded slowly for ORD-42
~~~

The line **PaymentClient | INFO | Starting payment...** does not appear because **INFO** is lower than the **WARNING** threshold of the PaymentClient logger.

Note on the Java file: the example has **one public class**, LoggerPerClassDemo; OrderService and PaymentClient are two non-public classes in the same file, so it can be compiled directly with the command above. They are placed in the **default package** to keep the demo concise; therefore, the Formatter prints **OrderService** and **PaymentClient** as the logger names. In a real project with package declarations, **getName()** will produce fully qualified names like **com.example.orders.OrderService**.

This sample code configures levels and Handlers directly in **main** to ensure predictable results. When building a real application, you should configure logging centrally and let each class only declare its logger and make log calls.

## 5. How per-class loggers relate to packages and parent configuration

In JUL, logger names form a **hierarchical namespace**. For example:

~~~text
com
  └── example
      ├── orders
      │   ├── OrderService
      │   └── OrderRepository
      └── payment
          └── PaymentClient
~~~

The paths above illustrate **dot-separated logger names**, not an in-memory class tree. The parent logger of a fully named logger is determined by the existing logger hierarchy; the nearest parent can be a prefix name or the root logger. Not every prefix segment has to exist as a separate Logger.

When a logger **does not set its own level** (**setLevel(null)**), it inherits the effective level from its parent Logger. This makes it possible to configure a package as a whole and override only the specific class under investigation.

Conceptual example (illustrative code assuming the classes belong to the corresponding packages):

~~~java
Logger orders = Logger.getLogger("com.example.orders");
orders.setLevel(Level.INFO);

Logger orderService =
        Logger.getLogger("com.example.orders.OrderService");
orderService.setLevel(null); // Inherit from parent logger.

Logger orderRepository =
        Logger.getLogger("com.example.orders.OrderRepository");
orderRepository.setLevel(Level.FINE); // Override for this class.
~~~

**Logger level** and **Handler level** are two separate filters. To receive FINE records, both the Logger and the target Handler must allow FINE. For example, setting the Logger to FINE while ConsoleHandler remains at INFO can still cause FINE records to be dropped before display.

### Role of parent Handlers

Under typical configurations, a logger can forward records to Handlers attached to its parent. This allows Handlers to be configured at the application-wide level. If you attach a Handler to a child logger while still allowing forwarding to parent Handlers, **two records may be displayed** for the same log call.

The method **logger.setUseParentHandlers(false)** prevents forwarding records to parent Handlers. However:

- It **does not automatically add** a new Handler.
- If the logger has no suitable Handler, records may not appear at all.
- It **does not disable log level inheritance** from the parent if the logger's own level is still **null**.
- You should not disable it broadly in business code when the system already has a centralized Handler configuration mechanism.

In the standalone example above, both classes reference the same Handler, but each record is published only from its respective class logger; they do not forward logs to parent Handlers, so there is no duplication.

## 6. Configuring per-class log levels in practice

With JUL, thresholds can be set in a **logging.properties** file. Example for a project with classes in the **com.example.orders** and **com.example.payment** packages:

~~~properties
handlers = java.util.logging.ConsoleHandler

.level = INFO
java.util.logging.ConsoleHandler.level = FINE

com.example.orders.OrderService.level = FINE
com.example.payment.PaymentClient.level = WARNING
~~~

Meaning:

- **.level = INFO:** Default level for the root logger.
- **ConsoleHandler.level = FINE:** The Handler allows FINE messages as well.
- **OrderService.level = FINE:** Enables additional FINE logs for this class.
- **PaymentClient.level = WARNING:** Focuses on WARNING and SEVERE events for that class.

The JVM can load JUL configuration from a file at startup—for instance, for an application with main class **com.example.Main** and compiled output in the **out** directory:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This command **illustrates how to load configuration for a real application**, not how to run LoggerPerClassDemo, because the demo in section 4 explicitly sets levels and Handlers in code. In applications using other logging frameworks, the syntax and configuration loading mechanism may differ from JUL.

Beyond per-class configuration, you can configure by **package**—for example, setting the log level for the entire repository layer and overriding one specific class. With structured or centralized logs, you can filter by **loggerName** or **class/package** if those fields are configured to be emitted.

## 7. Using per-class loggers to log errors properly

A per-class logger should record **events that the class is responsible for**, with enough context for investigation.

Example inside a method of OrderService (this snippet is **not standalone** and assumes variables and methods are already declared):

~~~java
LOGGER.log(Level.INFO, "Order accepted: id={0}", orderId);

try {
    persistOrder(orderId);
} catch (java.io.IOException e) {
    LOGGER.log(Level.SEVERE, "Could not persist order", e);
    throw e;
}
~~~

**Logger.log(Level, String, Object)** uses parameters in the message, such as the **{0}** placeholder when supported by the Formatter; **Logger.log(Level, String, Throwable)** attaches the exception to the LogRecord so the Formatter can print the stack trace. Logging only **e.getMessage()** is often insufficient for diagnosing errors.

You should deliberately decide **which layer logs an error**: if the same exception is logged at the DAO, Service, and Controller layers and then rethrown, the system may produce three SEVERE records for a single failure. Log where the error is handled or at the appropriate boundary, and avoid redundant logging that adds no value.

For debug data that is expensive to construct as a string, JUL supports a **Supplier** form:

~~~java
LOGGER.log(Level.FINE, () -> "Current cache size: " + expensiveCount());
~~~

The message-building expression is evaluated only when the Logger decides to accept the FINE level; whether the Handler further filters the record happens afterward. If you want to perform an expensive computation only when a log level is enabled, you can also guard the necessary work with **LOGGER.isLoggable(Level.FINE)**.

Do not put **passwords, tokens, secret keys, full sensitive requests, or unnecessary personal information** into logs. In distributed systems, include a request/trace ID and a stable event code for investigation, while avoiding creating loggers with names containing per-request IDs, as that can generate too many categories and break class-based grouping.

## 8. Comparison with per-class loggers in SLF4J

Many modern Java applications use **SLF4J** as the logging API, while a backend such as **Logback** or **Log4j 2** handles writing the logs. The per-class logger principle remains the same, though the syntax differs from JUL.

Example using SLF4J (this illustrative snippet requires **SLF4J and logging backend dependencies** and does not run standalone with only the JDK):

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void submit(String orderId) {
        log.info("Created order {}", orderId);
        log.debug("Validated order {}", orderId);
    }
}
~~~

Quick comparison:

| Aspect | JUL (JDK) | SLF4J |
| --- | --- | --- |
| Logger declaration | **Logger.getLogger(OrderService.class.getName())** | **LoggerFactory.getLogger(OrderService.class)** |
| Logger type | **java.util.logging.Logger** | **org.slf4j.Logger** |
| Common verbose levels | **FINE, FINER, FINEST** | **DEBUG, TRACE** |
| Error levels | **SEVERE, WARNING** | **ERROR, WARN** |
| Message parameters | **{0}**, **{1}** when formatted by JUL | **{}** placeholder |
| Output destination config | JUL Handlers and Formatters | Backend and corresponding appenders/layouts |

Do not mix **import java.util.logging.Logger** with **LoggerFactory.getLogger(Class)**, or use SLF4J's **{}** placeholder in JUL expecting a JUL Formatter to handle it automatically. In a Spring Boot application, use the API and backend standardized by the project; do not add JUL Handlers inside individual classes if the system already collects logs via centralized configuration.

## 9. Common mistakes when creating per-class loggers

### Mistake 1: Using a manual logger name that does not match the class

~~~java
// Two different classes share the same category name.
Logger logger = Logger.getLogger("CommonLogger");
~~~

When all classes use **CommonLogger**, logs lose the ability to be filtered accurately by class. Only use a shared category when it is an intentional decision, such as an audit stream independent of any single class.

### Mistake 2: Using getSimpleName() instead of getName()

~~~java
Logger logger = Logger.getLogger(OrderService.class.getSimpleName());
~~~

Short class names can collide across different packages. For loggers named by class, **class.getName()** is generally safer and easier to configure.

### Mistake 3: Creating a new logger on every log call

~~~java
void process() {
    Logger logger = Logger.getLogger(OrderService.class.getName());
    logger.info("Processing");
}
~~~

Looking up by name does not necessarily create a new object every time, but it repeats an unnecessary operation. A **private static final Logger** field makes the intent clear and keeps usage consistent.

### Mistake 4: Adding a Handler in every constructor or every call

~~~java
OrderService() {
    LOGGER.addHandler(new ConsoleHandler());
}
~~~

When multiple objects are created, the same logger can have multiple Handlers attached to it, causing the same message to be logged multiple times and wasting resources. Manage Handlers centrally or initialize them once at a configuration point with a clear lifecycle.

### Mistake 5: Setting only the Logger level and expecting to see all logs

**LOGGER.setLevel(Level.FINE)** is not enough if ConsoleHandler is still at INFO. Check the thresholds of the Logger, Handler, Filter, and parent propagation settings.

### Mistake 6: Disabling parent Handlers without adding a dedicated Handler

After **setUseParentHandlers(false)**, records are no longer forwarded to parent Handlers. If the child logger has no Handler of its own, logs may not appear at all. Only change routing when you clearly understand the active logging configuration.

### Mistake 7: Logging everything at SEVERE/ERROR

Not every exception or code branch is an operational incident. Use INFO for normal significant events, WARNING for recoverable anomalies, SEVERE for serious failures, and FINE for diagnostics. Choose levels based on impact and project policy.

### Mistake 8: Assuming a per-class logger guarantees the class name appears in output

The logger may have the right name, yet the Formatter/layout might only output the message. To see the category name, you must configure the **loggerName** field or corresponding pattern at the log output destination.

## 10. Design choices for multi-layered projects

A maintainable way to organize logging:

1. **Each class uses its own logger via Class.getName() or LoggerFactory.getLogger(Class).** Maintain the same logging API across the entire project.
2. **Configure Handlers/appenders centrally.** Business classes only emit events; configuring levels, output destinations, and formatting belongs to application startup or the logging system.
3. **Enable verbosity selectively.** When an error occurs, raise the level for the specific package or class under investigation instead of enabling debug system-wide.
4. **Use structured messages and context.** The logger name identifies the class, but does not replace a request ID, event code, or stack trace when needed.
5. **Control verbosity and sensitive data.** Account for performance, storage capacity, production environments, and access permissions.

For example, when **PaymentClient** experiences timeouts, you do not need to enable FINE for the entire application. You can allow verbose logs only for **com.example.payment.PaymentClient**, observe the errors briefly, identify the root cause, and return the threshold to normal once resolved.

## 11. Self-check questions

1. **Why should you use Class.getName() when naming a logger?** To obtain the class name including its package, avoid name collisions, and support per-class/per-package configuration.
2. **Does static final Logger mean each instance owns its own logger?** No. A static field belongs to the class and is shared; final prevents reassigning the reference.
3. **Does a per-class logger write to one file per class?** No. The output destination is determined by Handlers/appenders and configuration.
4. **Why might a Logger set to FINE still not show FINE records?** Because a Handler or Filter may block them, or the record routing does not reach the intended destination.
5. **Why should you not call addHandler in a constructor?** Because creating multiple objects can attach multiple Handlers to the same logger and cause duplicate logging.
6. **Is the syntax for obtaining a per-class logger the same in JUL and SLF4J?** No. JUL typically uses **Logger.getLogger(MyClass.class.getName())**; SLF4J typically uses **LoggerFactory.getLogger(MyClass.class)**.

**Key takeaway:** Per-class loggers give log records a clear origin, make it easy to filter by class name or package, and standardize logging across a Java project. Using a **static final** logger named after the class's fully qualified name, managing Handlers in a central configuration, and choosing appropriate log levels will create a logging foundation that is easy to scale and diagnose.

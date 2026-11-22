# What Is java.util.logging? — Java Util Logging (JUL) Overview

## Lesson Objectives

After this lesson, you will be able to explain what **java.util.logging** (JUL) is, why logging is needed in Java, distinguish a Logger from a Handler, understand how Level, LogRecord, Filter, Formatter, and LogManager work together, and produce logs with context, parameters, and exceptions in a standalone **Java 17+** program. You will also know how to configure JUL via a properties file, troubleshoot missing logs, distinguish JUL from other popular logging systems, and apply security and performance best practices.

This lesson belongs to the **Java Util Logging** section of **Java Core Logging**. The hands-on examples use only libraries built into the JDK and require no Maven or Gradle dependencies.

## 1. What Is Java Util Logging (JUL)?

**java.util.logging** is the standard logging package of the Java platform, commonly abbreviated as **JUL**. It provides APIs for Java applications and libraries to **create, categorize, filter, format, and output logs**. JUL allows you to record useful runtime events: a service starting up, a request being processed, a business branch being chosen, a dependency timing out, or an exception occurring.

Example of a human-readable log line:

~~~text
INFO | event=order.created orderId=OD-42 items=2
~~~

This line describes the order.created event along with the orderId and item count. INFO is the log level. However, **a JUL record is not just a display string**: internally, it can also contain a timestamp, logger name, raw message, parameters, a Throwable, and other metadata. The exact text format is determined by the Formatter/Handler. The example line above is neither a mandatory nor a default JUL format.

JUL **does not automatically record everything that happens in an application**. Application or library code must call the logging API; a record can be dropped at the logger, handler, or filter; and the output destination itself can fail. Therefore, not finding a log line does not prove that the event never occurred.

### How Does Logging Differ from System.out.println?

| System.out.println | java.util.logging |
| --- | --- |
| Writes values directly to stdout | Creates records with level, logger name, message, and metadata |
| Has no built-in severity levels | Provides SEVERE, WARNING, INFO, CONFIG, FINE, FINER, FINEST |
| Hard to adjust message volume by package | Allows configuring levels and filters per logger |
| Has no built-in handler mechanism | Provides ConsoleHandler, FileHandler, and other handlers |
| Requires manual handling for formatting or exceptions | Provides Formatter and overloads accepting Throwable |
| Reasonable for CLI output or very small experiments | Suitable for long-term diagnostic and observability logging |

This does not mean every System.out.println call is wrong. For a CLI program, stdout may be the **official output data**. Diagnostic information, however, needs mechanisms to control level, source, format, and destination. That is why a unified logging API should be used.

**JUL is built into the JDK**. For Java code running on the classpath like the examples below, no external logging framework is needed to use JUL. In a named-module application, the java.logging module must be explicitly declared as a dependency; this is explained in section 10.

## 2. Basic Logging Architecture of JUL

The conceptual path of a record is shown below:

~~~mermaid
flowchart LR
    A["Application code calls Logger"] --> B["Logger: level and filter"]
    B --> C["LogRecord"]
    C --> D["Handler: level and filter"]
    D --> E["Formatter"]
    E --> F["Console, file, or other destination"]
~~~

This is a simplified model and does not depict all parent/child logger rules or every handler strategy.

Core components:

| Component | Role | Illustrative API or Class |
| --- | --- | --- |
| **Logger** | Entry point receiving log requests from the application | Logger.getLogger, Logger.info, Logger.log |
| **Level** | Represents the severity or verbosity of a record | Level.INFO, Level.WARNING, Level.FINE |
| **LogRecord** | Object holding the content and metadata of a single log event | getLevel, getMessage, getInstant, getThrown |
| **Filter** | Additional rule deciding whether to accept a record | Filter.isLoggable |
| **Handler** | Processes and delivers records to a destination | ConsoleHandler, FileHandler, StreamHandler |
| **Formatter** | Converts a record into a text/XML representation | SimpleFormatter, XMLFormatter, custom Formatter |
| **LogManager** | Manages loggers and JUL configuration | LogManager.getLogManager |

From your code, you call **Logger**. The Logger may drop the record immediately if its level is not met, or check an additional Filter. If the record is accepted, **Handlers** can receive it; each Handler also has its own level and Filter. The Handler's Formatter determines the actual content written out.

A single logger can have multiple Handlers attached: for example, the console displays INFO and above, while a diagnostic file receives FINE as well. At the same time, JUL has a parent/child logger hierarchy, so a parent logger's Handlers can also receive the record depending on propagation settings.

### A Logger Is Not a Log File

Creating a Logger **does not automatically create a log file**. The Logger is where records are emitted; the Handler decides where they are written. If the application lacks an appropriate Handler or the configuration filters records out, you may see nothing on the console or in a file even though the code called a logging method.

## 3. Logger: How to Create and Use One in a Java Class

In Java, the common practice is to create a logger named after the class and keep a reusable reference:

~~~java
// Illustrative snippet inside the MyService class.
private static final java.util.logging.Logger LOG =
        java.util.logging.Logger.getLogger(MyService.class.getName());
~~~

MyService is an example class name; this snippet must be placed inside an actual class, not run as a standalone program. The package-qualified name helps trace the source: logs from com.example.payment.PaymentClient are distinct from logs from com.example.order.OrderService.

Convenience methods:

~~~java
// Illustration: the LOG object above is already declared.
LOG.info("event=service.started");
LOG.warning("event=dependency.retry attempt=2");
LOG.fine("event=cache.lookup result=miss");
LOG.log(java.util.logging.Level.SEVERE, "event=storage.failed");
~~~

**Logger.getLogger(name)** retrieves a logger by name. Storing the logger in a static final field reuses the logger and keeps a stable reference throughout the class lifecycle. Do not create a new logger per request.

### Logger Names and Parent/Child Relationships

Logger names usually follow a dot-separated hierarchy:

~~~text
com.example
com.example.order
com.example.order.OrderService
~~~

If a child logger has its level set to null, it typically **inherits its effective level** from the appropriate parent. JUL can forward records from a child logger to its parent's Handlers. This mechanism lets you configure logging by package or at the root instead of attaching handlers to every class.

Commonly used methods:

~~~java
// Illustration: logger and handler have already been declared.
logger.setLevel(java.util.logging.Level.FINE);
logger.setUseParentHandlers(false);
logger.addHandler(handler);
~~~

**setUseParentHandlers(false)** prevents records from propagating to the parent logger's handlers. It does not create a new handler, does not change any handler's level, and does not guarantee that records will be output. If you disable parent handlers without attaching a direct handler, logs may be lost at the destination you are observing.

Conversely, if you attach a handler to a child logger while still allowing propagation to the parent, the same record may appear multiple times if multiple handlers receive it.

## 4. Level: Categorizing Events by Severity

JUL provides standard Levels:

| Level | Typical Meaning | Examples |
| --- | --- | --- |
| **SEVERE** | Serious error preventing an operation or component from completing properly | Essential data write failed, service unavailable |
| **WARNING** | Notable anomaly that may still be recoverable | Timeout and retry, unexpected fallback |
| **INFO** | Operational or business milestone worth tracking | Application started, order created |
| **CONFIG** | Configuration information | Run mode, non-sensitive feature flags |
| **FINE** | Details useful for debugging | Cache miss, chosen processing branch |
| **FINER** | Deeper detail | Progress of a complex processing step |
| **FINEST** | Extremely detailed and usually high-frequency | Step-by-step parser trace, internal transformations |
| **OFF** | Threshold used to turn logging off | Configuration setting |
| **ALL** | Threshold allowing all levels | Maximum observability configuration |

Do not choose a Level based solely on an exception's name. A properly handled validation error can be a normal business outcome. A retry logged at WARNING does not necessarily mean the request failed; you must check the final outcome.

In JUL, an INFO threshold normally permits INFO, WARNING, and SEVERE; FINE/FINER/FINEST are dropped. A FINE threshold additionally permits CONFIG and FINE, but not FINER/FINEST. An ALL threshold lets every level pass the level check, though a record can still be dropped by a Filter or Handler.

### Both Logger and Handler Filter by Level

| Logger Effective Level | Handler Level | Is a FINE Record Output by Handler? |
| --- | --- | --- |
| INFO | FINE | No: dropped by Logger |
| FINE | INFO | No: dropped by Handler |
| FINE | FINE | Yes, if other filters do not reject it and the destination works |
| FINEST | FINE | Yes |
| OFF | ALL | No: Logger is off |

This is one of the most common mistakes: setting the Logger to FINE while ConsoleHandler is still at INFO means you cannot observe FINE logs on that console.

## 5. LogRecord: What Does a Record Contain?

A logger call can create a **LogRecord**. The record holds information such as:

- The Level at the time of logging.
- The Logger name.
- The raw message and any passed parameters.
- The timestamp when the record was created, accessible as an Instant in modern Java.
- The Throwable when using a log overload that accepts an exception.
- Metadata that helps trace the source of the record.

An **Event** is what happened, such as order.created. A **Message** is the text describing the event. A **LogRecord** is the structure the logging system uses to hold the message and metadata. A **Formatter** is the component that decides how the record is rendered; a **Handler** is what delivers it to a destination.

When calling JUL with a parameterized message:

~~~java
// Illustration: LOG and orderId have already been declared.
LOG.log(java.util.logging.Level.INFO,
        "event=order.created orderId={0} items={1}",
        new Object[] {orderId, 2});
~~~

The raw message can contain placeholders **{0}**, **{1}** and a parameter array. When the Formatter calls formatMessage(record), they are substituted according to JUL's syntax. Some other libraries use **{}** placeholders, so do not mix one API's syntax with another.

Strings like requestId=req-7, event=payment.retry, and durationMs=125 are **conventions written into the message by developers**. JUL does not turn them into separate structured fields by default. If you need field-based searching in a log collection system, you must standardize on a schema/format or use an appropriate structured logging solution.

## 6. Handler, Formatter, and Filter

### Where Do Handlers Send Records?

Common Handlers:

- **ConsoleHandler:** outputs logs to the console, defaulting to stderr. Useful in terminals, IDEs, and containers when stderr collection is configured properly.
- **FileHandler:** writes logs to files; supports configuring file names, size/rotation, and file counts via appropriate constructors/config. Pay attention to write permissions, disk space, locks, and retention.
- **StreamHandler:** writes records to an OutputStream using a configured Formatter.
- **SocketHandler:** sends logs over a socket to a configured host; network errors and reliability must be considered.
- **MemoryHandler:** buffers a number of records in memory and forwards them to a target Handler when triggered. It is not durable storage.

A record can reach multiple Handlers with independent configurations. When debugging "logs appear in the file but not on the console," check the level/filter of each Handler and the parent handlers configuration.

### Formatter Presents the LogRecord

**SimpleFormatter** produces human-readable text; **XMLFormatter** outputs XML; you can also subclass Formatter to define a custom representation. The output format depends on the formatter and may vary by JDK version or configuration.

For example, a Throwable can make a text record span multiple lines with a stack trace. Do not assume **each line of text is a separate event**. With FileHandler, if no Formatter is specified, the default format is typically XML rather than single-line text like a custom demo.

### What Is a Filter For?

A Filter lets you add conditions beyond Level, such as keeping only records related to a specific module or suppressing low-value records. Both **Logger** and **Handler** can have a Filter. Meeting the Level threshold does not guarantee a record is written if a Filter rejects it.

Do not use a Filter or Formatter to execute business logic. Turning logging on/off or filtering records must never alter the application's behavior or outcome.

### LogManager

**LogManager** manages Loggers and JUL configuration. In real applications, maintain a clear logging configuration so individual classes do not override handlers or levels inconsistently, which leads to duplicate, missing, or inconsistent logs.

## 7. A Java 17+ Program Using JUL

This example uses pure JDK JUL: it creates a Logger named after the class, configures a ConsoleHandler and a Formatter, logs INFO, FINE, and WARNING messages, passes parameters via a message template, and attaches a Throwable.

Create a file named **JulOverviewDemo.java** with the following complete contents:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulOverviewDemo {
    private static final Logger LOG =
            Logger.getLogger(JulOverviewDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.FINE);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.FINE);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String line = record.getLevel().getName()
                        + " | " + formatMessage(record);
                if (record.getThrown() != null) {
                    line += " | exception="
                            + record.getThrown().getClass().getSimpleName();
                }
                return line + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        try {
            LOG.info("event=request.started requestId=req-7");
            LOG.fine("event=cache.lookup requestId=req-7 result=miss");
            LOG.log(Level.INFO,
                    "event=order.created orderId={0} items={1}",
                    new Object[] {"OD-42", 2});
            LOG.warning("event=payment.retry requestId=req-7 attempt=2");
            LOG.info("event=request.finished requestId=req-7 status=200");
            try {
                Integer.parseInt("two");
            } catch (NumberFormatException ex) {
                LOG.log(Level.WARNING,
                        "event=quantity.invalid requestId=req-8", ex);
            }
        } finally {
            LOG.removeHandler(console);
            console.close();
        }
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac JulOverviewDemo.java
java JulOverviewDemo
~~~

**Exact output on stderr** produced by ConsoleHandler (the program writes nothing to stdout):

~~~text
INFO | event=request.started requestId=req-7
FINE | event=cache.lookup requestId=req-7 result=miss
INFO | event=order.created orderId=OD-42 items=2
WARNING | event=payment.retry requestId=req-7 attempt=2
INFO | event=request.finished requestId=req-7 status=200
WARNING | event=quantity.invalid requestId=req-8 | exception=NumberFormatException
~~~

This is the output of the Formatter in the code, which intentionally **omits timestamps** so the result is deterministic. With SimpleFormatter, the format and timestamp will differ.

### How It Works

1. **Logger.getLogger(...)** returns a logger named JulOverviewDemo.
2. **LOG.setUseParentHandlers(false)** prevents records from being forwarded to the root logger's Handler in this demo, avoiding duplicate output.
3. **LOG.setLevel(FINE)** and **console.setLevel(FINE)** allow FINE records to pass both thresholds.
4. **console.setFormatter(...)** sets a formatter that outputs only the Level, the formatted message with parameters substituted, and the Throwable class name (if present).
5. The call LOG.log(Level.INFO, template, Object[]) stores the message template and parameters; when the Formatter calls formatMessage(record), it produces orderId=OD-42 items=2.
6. The payment.retry WARNING describes an unusual step; request req-7 still finishes with status=200. Do not infer request failure from a WARNING alone.
7. The data-parsing error belongs to requestId req-8, a separate event. The log overload accepting Throwable attaches the exception to the LogRecord; the demo Formatter shortens its display to just the class name.
8. In the finally block, the Handler is removed from the Logger and closed; real applications typically manage Handlers at the system lifecycle level rather than per request.

### Quick Experiment After Running

Change both **LOG.setLevel(Level.FINE)** and **console.setLevel(Level.FINE)** to **Level.INFO**, then run again. The FINE line for cache.lookup will disappear, while INFO and WARNING lines remain. If you change only one of them, FINE records will still be dropped at whichever component remains at INFO. The simulated business logic still runs completely even though the FINE line is not printed.

## 8. Parameterization, Logging Exceptions, and Deferred Message Construction

**Parameterization** helps produce consistent messages. In JUL, when parameters are passed, numbered placeholders {0}, {1} are interpreted according to MessageFormat rules via Formatter.formatMessage. Do not confuse this with SLF4J's {} placeholder.

For Throwables, use the overload that accepts a Throwable whenever you need to preserve the stack trace and cause:

~~~java
// Illustrative code snippet; assume LOG and ex already exist.
LOG.log(java.util.logging.Level.SEVERE,
        "event=storage.failed operation=save", ex);
~~~

Merely concatenating ex.getMessage() into a plain string does not attach the Throwable to the record; it can lose the cause chain and stack trace needed for investigation.

For log messages that require expensive computation, JUL supports Supplier:

~~~java
// Illustrative snippet; expensiveSummary() is defined in the application.
LOG.log(java.util.logging.Level.FINE,
        () -> "event=debug.snapshot summary=" + expensiveSummary());
~~~

Supplier defers building the message string when the logger rejects the level. Never put business side effects inside a Supplier: the Supplier might not be invoked. You can also use LOG.isLoggable(Level.FINE) to guard expensive data preparation. Note that a logger accepting a record does not guarantee a handler will output it; a Filter or Handler can still drop it later.

In multi-request applications, prefer stable event names, permitted requestId/traceId values, clear units (durationMs, bytes), and appropriate levels instead of dumping entire objects or payloads into messages.

## 9. Configuring JUL Externally with logging.properties

To change Levels or Handlers without modifying code, real applications typically use external configuration. An illustrative **logging.properties** file:

~~~properties
# Root log level: INFO and above.
.level = INFO

# Attach a ConsoleHandler to root.
handlers = java.util.logging.ConsoleHandler

# Handler must accept FINE if a child package enables this level.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Increase verbosity only for a package under investigation.
com.example.order.level = FINE
~~~

If another application has a compiled com.example.Main class in the out classpath directory and **does not override loggers/handlers in code**, it can be run with:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This is an **illustrative command for an application with a matching structure**, not the command to run JulOverviewDemo from section 7. That demo creates its own Formatter and calls setLevel in code, so its output will not depend entirely on a properties file.

How to read the configuration:

- **.level = INFO** sets the root logger's level.
- **handlers = ...ConsoleHandler** attaches ConsoleHandler via JUL's global configuration.
- **ConsoleHandler.level = FINE** allows the handler to accept FINE records from child loggers that enable it.
- **com.example.order.level = FINE** changes verbosity for the specified logger/package; other loggers continue to inherit INFO.
- **java.util.logging.config.file** is a JVM system property pointing to the configuration file, placed before the main class name in the java command.

If logging does not behave as expected, verify whether the file was loaded, check the actual logger name, parent loggers, Handlers, Filters, and whether any code or framework overrides the configuration afterward. For FileHandler, pay attention to file paths, permissions, rotation settings, retention, and the formatter.

## 10. JUL in the Java Platform Module System

Since Java 9, JUL resides in the standard **java.logging** module. For an application using **named modules** and module-info.java, declare:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

This snippet is **module-info.java content**, not code to insert into JulOverviewDemo.java. For simple examples running on the classpath with a full Java runtime, you do not need to create module-info.java.

When building a minimal runtime image with jlink, ensure all required module dependencies—including java.logging if the application uses JUL—are included in the image. The java.base module is always included, but it does not replace java.logging.

Do not confuse **java.util.logging.Logger** with **System.Logger** in java.lang or **org.slf4j.Logger** in SLF4J; they differ in APIs as well as configuration and provider mechanisms.

## 11. JUL vs. SLF4J, Logback, and Log4j 2

| Name | Role | Distinction |
| --- | --- | --- |
| **java.util.logging** / JUL | Built-in Java logging API and implementation | Has Logger, LogRecord, Handler, Formatter, LogManager |
| **SLF4J** | Logging facade, common interface for application code | Not the JUL Logger class; usually requires a matching provider/backend |
| **Logback** | Popular logging backend, often paired with SLF4J | Has its own appenders, encoders, and configuration |
| **Log4j 2** | Logging framework with its own API, core, and configuration system | Not compatible with JUL's logging.properties file |
| **System.Logger** | Logging API in java.lang | Not a direct alias for JUL Logger |

JUL is built into the JDK and meets many basic logging needs. Larger projects may choose other frameworks based on structured logging requirements, integrations, and team standards. Bridges or adapters can unify multiple systems, though level mapping and output paths depend on specific configuration. Misconfiguration can produce duplicate records or make logs appear missing.

When maintaining a project, it is essential to **identify which API the code calls and which backend actually processes the records**. Adjusting a JUL ConsoleHandler will not automatically change the DEBUG level of a Logback logger unless a corresponding bridge is configured.

## 12. Common Mistakes and How to Fix Them

| Problem | Possible Cause | How to Fix |
| --- | --- | --- |
| FINE logs not visible | Logger or Handler is still at INFO | Check both levels and any Filters |
| Duplicate log entries | Both child and parent loggers have Handlers | Check parent handlers setting and attached Handlers |
| No logs after disabling parent | No direct Handler attached | Attach an appropriate Handler or use parent intentionally |
| File log format differs from console | Different Formatter, such as XMLFormatter | Check the Formatter and log parser |
| Syntax orderId={} not substituted | Confused placeholder syntax with another library | Use {0}, {1} in JUL when passing parameters |
| Only exception message appears | Throwable not passed or Formatter omits stack trace | Use overload accepting Throwable and suitable Formatter |
| Every exception logged as SEVERE | Choosing level mechanically | Base level on impact and whether the error was handled |
| Log flood during debugging | Enabling ALL/FINEST on too many packages | Enable verbosity selectively and revert once evidence is gathered |
| Secrets or personal data in logs | Dumping raw requests or objects | Log only necessary fields; apply masking/redaction and policies |
| Logs missing in CI | Looking at wrong stdout/stderr stream or backend, filter, sampling | Verify output destination and collection pipeline |
| Logging success before commit | Event logged at the wrong point | Confirm completion only after commit/completion succeeds |
| Logging every iteration in a loop | High CPU/I/O cost and noisy data | Aggregate into metrics or reduce verbosity |

**Security:** Never log passwords, access tokens, API keys, session cookies, card details, or private payloads; even FINEST logs on a developer machine can be synced or shared. Untrusted input may contain newlines or control characters to forge records (**log injection**); limit, escape, or use structured logging and appropriate sanitization.

**Performance:** Logging is not free. Even when a record is not output, preparing complex arguments can still consume CPU before the logger call. When actually written, Formatter, I/O, buffering, and log shipping all consume resources. Do not log every loop iteration or entire large objects at INFO.

**Reliability:** Diagnostic logs are not automatically a durable audit trail or proof of a committed transaction. When an audit trail is required, integrity, access control, retention, and traceability must be designed separately.

## 13. Workflow for Adding JUL to a New Class

1. **Choose the Logger name** using the class or package name, and keep a long-lived reference.
2. **Identify key events**: start, completion, failure, retry, or decisions needed for diagnostics.
3. **Choose appropriate Levels** based on impact and verbosity, not merely whether an exception occurred.
4. **Design contextual messages**: event name, permitted requestId/traceId, relevant entity IDs, outcome, and clear units.
5. **Pass Throwable when needed** to preserve the cause chain and stack trace; avoid logging the same exception redundantly across layers.
6. **Configure Handler/Formatter**, ensuring neither the logger level nor the handler level blocks the records you need to observe.
7. **Test in practice** with one success case and one failure case, then inspect logs on the console, file, or target backend.
8. **Manage configuration and data safely** per environment; avoid leaving ultra-verbose levels enabled long-term.

In asynchronous applications, records from multiple threads may interleave. Use identifiers and context propagated properly across execution boundaries to correlate them. Do not assume lines with adjacent timestamps belong to the same request.

## 14. Self-Check Questions

**Question 1:** Is java.util.logging an external dependency outside the JDK?

**Answer:** No. JUL is Java's built-in logging API. With named modules, declare requires java.logging in module-info.java.

**Question 2:** Why is a Logger set to FINE, yet FINE logs do not appear on the console?

**Answer:** ConsoleHandler may still be at INFO, or a Filter is rejecting the record. You must check the Logger's effective level, the Handler's level/Filter, and the output path.

**Question 3:** How does a Logger differ from a Handler?

**Answer:** A Logger receives logging requests from code and checks its level/filter; a Handler processes and writes the record to a destination, using its own Formatter and level/filter.

**Question 4:** What is the difference between a LogRecord and the displayed text?

**Answer:** LogRecord is an object containing the message, Level, parameters, Throwable, and metadata; the Formatter determines the output text or XML, so it may omit or represent fields differently.

**Question 5:** Why does JulOverviewDemo display orderId=OD-42 even though the code uses {0}?

**Answer:** The log API accepts a parameter array, and Formatter.formatMessage(record) substitutes JUL's numbered placeholders.

**Question 6:** Logs for req-7 show a WARNING, but also request.finished status=200. Can we conclude the request failed?

**Answer:** No. The WARNING may describe a recovered retry; the final outcome for that requestId must be checked separately.

**Question 7:** What happens if you disable useParentHandlers without attaching a dedicated handler?

**Answer:** Logs may never reach an output destination, because propagation to the parent logger's Handlers was disabled.

**Question 8:** Why shouldn't tokens or raw payloads be logged at FINEST?

**Answer:** Log level is not a data-protection mechanism. Logs can be stored, collected, attached to issues, or shared unintentionally.

## Key Takeaways

**java.util.logging (JUL)** is Java's built-in logging system. **Logger** is where code emits records; **Level** classifies severity; **LogRecord** holds the event data; **Filter** applies additional conditions; **Handler** chooses the destination; **Formatter** controls the presentation; and **LogManager** manages configuration. Useful logging requires understanding the record's full path, logger/handler thresholds, timing, and event context—while keeping security, cost, and formatting under control.

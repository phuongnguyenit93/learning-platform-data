# What Is a Handler in Java Logging?

## 1. The Handler Concept

In **Java Util Logging (JUL)**, a **Handler** is the component that **receives and publishes log records** forwarded by a Logger. A Logger lets Java code emit events; a Handler decides where and how an accepted event is delivered, such as to the console, a file, or a log-receiving system.

The key classes all reside in the JDK's **java.util.logging** package:

- **Logger:** Where the application calls methods such as **info**, **warning**, **severe**, or **log** to emit an event.
- **LogRecord:** The object carrying the event's information: level, message, logger name, timestamp, parameters, Throwable, and some metadata.
- **Handler:** The component that receives a LogRecord and performs the publishing operation.
- **Formatter:** The component that transforms LogRecord contents into an appropriate representation, such as plain text or XML.
- **Filter:** An additional rule that can accept or reject a LogRecord.
- **LogManager:** The component that manages logging configuration and loggers in JUL.

You can visualize the flow as:

~~~text
Java application code
    |
    | LOGGER.warning("Gateway slow")
    v
Logger
    | checks level and Logger Filter
    v
LogRecord
    |
    +-----------------------------+
    |                             |
    v                             v
ConsoleHandler                FileHandler
    | level + Handler Filter      | level + Handler Filter
    | Formatter                   | Formatter
    v                             v
Console (usually stderr)      Log file
~~~

**A Handler is not an exception handler.** The word "handler" here refers to the component that processes **log records**, not a **catch (Exception e)** block in Java. Catching and handling exceptions is a decision of program logic; Logger and Handler record the observable event.

Example:

~~~java
private static final java.util.logging.Logger LOGGER =
        java.util.logging.Logger.getLogger(MyService.class.getName());

LOGGER.info("Service started");
~~~

This is an illustrative snippet of two statements within an appropriate class/method context, not a standalone Java file. The **LOGGER.info(...)** line emits an event; which Handler actually outputs the event depends on the Logger configuration, attached Handlers, levels, and Filters.

## 2. How Do Handler and Logger Differ?

| Criterion | Logger | Handler |
| --- | --- | --- |
| Primary responsibility | Emits events and identifies category by name | Receives events and writes them to a specific destination |
| Typical application call site | LOGGER.info, LOGGER.warning, LOGGER.log... | Usually configured at startup, rarely called directly from business logic |
| Has a level? | Yes: the logger's effective threshold | Yes: the Handler's own threshold |
| Has a Filter? | Can have a Logger Filter | Can have a Handler Filter |
| Has a Formatter? | Not the component that directly formats the record | Can hold a Formatter to produce output |
| Hierarchical relationship | Loggers have parent/child relationships by name | Handlers are attached to Loggers; they do not form a logger tree on their own |
| Can there be multiple? | Each class/category can have its own logger name | One Logger can have multiple Handlers attached |
| Example | com.example.payment.PaymentClient | ConsoleHandler, FileHandler, custom Handler |

A Logger can emit one event to multiple Handlers so that the same LogRecord is written to the console **and** a file. Conversely, multiple Loggers can forward records to the **same Handler**, such as a ConsoleHandler attached to the root logger.

**One logger per class does not mean one file per class.** Loggers across many packages can share a single Handler writing to the console or a file; splitting by service, file, or environment is a configuration choice.

When using Logback or Log4j 2, output destination components are typically called **Appenders**. They play a role similar to JUL's Handler, but they are **not the same class or API**. Do not pass a **java.util.logging.Handler** directly to a Logback Logger and expect it to work.

## 3. Built-in Handler Types in JUL

The JDK provides several common Handlers:

| Handler | Purpose | Key Notes |
| --- | --- | --- |
| **ConsoleHandler** | Outputs logs to the console, typically **System.err** | Has a filter level and Formatter; output may not match the program's stdout |
| **FileHandler** | Writes LogRecords to files, supporting filename patterns and basic file rotation | May throw IOException when opening files; must be closed to release resources |
| **StreamHandler** | Writes to an application-provided OutputStream | Uses buffering; pay attention to **flush** and stream lifecycle management |
| **SocketHandler** | Sends logs over a socket connection in a configured format | Depends on network connectivity; not a drop-in replacement for a durable observability pipeline |
| **MemoryHandler** | Temporarily holds LogRecords in memory and pushes them to a target Handler under a condition | Useful when you only want to flush context when a sufficiently severe event occurs |

### ConsoleHandler

This is an easy choice for learning JUL and observing applications. Example:

~~~java
ConsoleHandler console = new ConsoleHandler();
console.setLevel(Level.INFO);
console.setFormatter(new SimpleFormatter());
logger.addHandler(console);
~~~

This illustrative snippet assumes classes are already imported, a suitable **logger** variable exists, and Handler cleanup code is present. **ConsoleHandler writes to stderr by default**, not stdout. Therefore, when running Java, **System.out.println(...)** lines and ConsoleHandler lines may appear on two different streams. If the terminal merges stdout/stderr, the relative display order between the two streams is not always reliable as expected output.

### FileHandler

An example illustrating a FileHandler with a maximum of about 1 MB per file, rotating across three files:

~~~java
FileHandler file = new FileHandler(
        "%h/app-%u.%g.log",
        1_000_000,
        3,
        true
);
file.setLevel(Level.WARNING);
file.setFormatter(new SimpleFormatter());
logger.addHandler(file);
~~~

In JUL, **%h** represents the home directory, **%u** helps disambiguate filenames when avoiding collisions, and **%g** is the rotation generation index. The value 1,000,000 in the constructor is the byte limit per file as implemented by FileHandler; 3 is the number of files in the rotation. **true** requests appending if possible, which does not mean log data is unconditionally durable.

**FileHandler is not equivalent to a full production log rotation/retention system.** Applications must verify write permissions, disk space, number of JVM processes, paths, encoding, and centralized collection pipelines. FileHandler has file-locking mechanisms, but multiple independent processes should not arbitrarily contend for the same path.

If no custom Formatter is set, FileHandler typically uses **XMLFormatter**, so logs may be emitted as XML rather than simple text lines. If you want a text file, explicitly configure SimpleFormatter or another Formatter.

### StreamHandler and SocketHandler

**StreamHandler** is suitable when you want to write to a specific OutputStream, but you must understand that events may sit in a buffer before flushing. If the stream is owned by another component, do not close it arbitrarily because doing so may close a shared resource.

**SocketHandler** sends data over a socket; connection loss or receiver errors can affect log publishing. Do not treat the default SocketHandler as a guaranteed retry queue after a process crash. For cloud applications, it is usually better to use a collection pipeline supported by the runtime platform and review log-loss/backpressure characteristics.

### MemoryHandler

**MemoryHandler** stores recent records in a circular buffer and can push them through a target Handler when encountering a record that meets **pushLevel**. This is useful when you want to retain detailed context leading up to an abnormal event. MemoryHandler only keeps a configured number of records and does not guarantee long-term history or persistence across restarts.

## 4. How Logs Propagate from Logger to Handler

In JUL, when code calls:

~~~java
logger.warning("Dependency responded slowly");
~~~

the general flow is:

1. The Logger checks its own **effective level**. If the LogRecord's level is too low, the Logger may not emit the record.
2. If a Filter is configured on the Logger, the Filter may reject the record.
3. The Logger forwards the LogRecord to Handlers attached directly to it.
4. Depending on **useParentHandlers**, the LogRecord continues to be forwarded to Handlers on the parent Logger and its ancestors.
5. Each Handler can use its own **level**, **Filter**, and processing/Formatter mechanism to decide whether to publish the record.

An important detail: once a LogRecord has been accepted by a child Logger and forwarded to a parent's Handlers, **the parent Logger's level is not necessarily used to re-filter that record**. However, the level and Filter of **Handlers on the parent** can still drop it.

Example:

~~~text
com.example.payment.PaymentClient  -> Logger level FINE
                  |
                  | Logger accepts FINE
                  v
                 Root handler
                  |
                  +--> ConsoleHandler level INFO
                  |
                  +--> FileHandler level FINE
~~~

In the example above, a FINE record can be recorded by FileHandler while being ignored by ConsoleHandler. You cannot conclude "I set the Logger to FINE, so every Handler will log FINE."

### Minimum Conditions to See a Record

- The Logger emits the event at an accepted level.
- The Logger Filter does not reject it.
- There is a route to an appropriate Handler.
- The Handler level allows the event.
- The Handler Filter does not exclude the event.
- The output destination works and the Formatter/encoder can process it.

Collector configuration, storage tiers, or ingestion limits outside the JVM can also affect whether the record appears in a dashboard.

## 5. Handler Levels

**Handler.setLevel(Level)** sets the minimum threshold a Handler will accept. The standard JUL levels from most severe to most detailed are:

~~~text
SEVERE (1000)
WARNING (900)
INFO (800)
CONFIG (700)
FINE (500)
FINER (400)
FINEST (300)
~~~

Two special levels are **OFF** (rejects all under normal threshold checks) and **ALL** (allows all standard levels under threshold checks). Handler level and Logger level serve separate roles.

| Logger Level | Handler Level | Event | Can Reach Destination? |
| --- | --- | --- | --- |
| INFO | INFO | INFO | Yes, if Filter/destination allow |
| INFO | ALL | FINE | No, blocked by Logger |
| FINE | INFO | FINE | No, blocked by Handler |
| FINE | FINE | FINE | Yes, if Filter/destination allow |
| WARNING | FINE | INFO | No, blocked by Logger |
| ALL | WARNING | SEVERE | Yes, if Filter/destination allow |

This table assumes no other Filters are present and a route to the corresponding Handler exists.

**Do not just raise the Handler level to enable debugging.** If the Logger remains at INFO, calls to logger.fine(...) will not pass the first filtering step. Conversely, a Logger at FINE with a Handler at INFO is also insufficient.

Each Handler can have a different level. For example, the console outputs INFO+, while a file supports FINE for investigation; or a centralized Handler keeps structured fields while another Handler only records warnings. This decision affects storage volume, data safety, and how logs are accessed.

## 6. Filter and Formatter in a Handler

### Filter: Selecting Records by Rule

In addition to levels, **Handler.setFilter(Filter)** enables rules such as:
- Accepting only records belonging to a specific group of event codes.
- Dropping overly frequent heartbeat events.
- Allowing certain event types to reach a specialized Handler.

Example:

~~~java
handler.setFilter(record ->
        !record.getMessage().startsWith("NOISY_"));
~~~

This is an illustrative snippet, assuming the message of the evaluated records is non-null. It drops any record whose message starts with **NOISY_**. In production deployments, consider null message handling, errors during filtering, and impact on troubleshooting.

**Do not use a Filter as the sole solution for masking secrets** if logs can still reach another Handler or another Collector. A safer approach is to avoid putting sensitive data into events in the first place.

### Formatter: Deciding Output Appearance

**java.util.logging.Formatter** defines how a LogRecord is converted into a string. Built-in Formatters include:
- **SimpleFormatter:** Human-readable text format that can include timestamp, level, message, and exception according to a pattern.
- **XMLFormatter:** XML format, commonly used by default in FileHandler.

Example of creating a custom Formatter:

~~~java
Formatter formatter = new Formatter() {
    @Override
    public String format(LogRecord record) {
        return record.getLevel().getName()
                + " | "
                + record.getLoggerName()
                + " | "
                + formatMessage(record)
                + System.lineSeparator();
    }
};
handler.setFormatter(formatter);
~~~

This is an illustrative snippet within a class that has a valid Handler. **formatMessage(record)** uses the message formatting and resource bundle/parameter support inherited from Formatter, which is better than assuming every message is already a formatted string.

If you want to log a **stack trace** or structured JSON, the Formatter needs to handle **record.getThrown()** and the relevant fields. Simply choosing a Formatter does not automatically generate metadata like request IDs or trace IDs; the application and tracing environment must populate that context properly.

### Distinguishing Filtering Stage and Formatting Stage

~~~text
Logger level / Logger Filter
        |
        v
Handler level / Handler Filter
        |
        v
Handler.publish()
        |
        v
Formatter
        |
        v
I/O or log-receiving system
~~~

This is the conceptual model. With a custom Handler, **publish()** can decide when to call the Formatter and whether to honor **isLoggable(record)**. You should not implement a Handler and arbitrarily bypass level and Filter checks.

## 7. Standalone Java 17 Example: Writing a Custom Handler

This example demonstrates all core responsibilities of a Handler:

1. The Logger is named **demo.orders.OrderService** and set to **Level.FINE**.
2. The Handler is set to **Level.INFO**, so it drops FINE records even though the Logger accepts them.
3. The Handler Filter drops events whose message starts with **NOISY_**.
4. The custom Formatter prints the level, Logger name, message, and **Throwable type**.
5. The Handler writes to **System.out** for deterministic output independent of timestamps.
6. Forwarding to parent Handlers is disabled in the example to avoid extra lines from the default configuration.

Create the file **HandlerDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class HandlerDemo {
    private static final Logger LOG =
            Logger.getLogger("demo.orders.OrderService");

    public static void main(String[] args) {
        Handler output = new DeterministicHandler();
        output.setLevel(Level.INFO);
        output.setFilter(record ->
                !record.getMessage().startsWith("NOISY_"));

        LOG.setLevel(Level.FINE);
        LOG.setUseParentHandlers(false);
        LOG.addHandler(output);

        try {
            LOG.fine("QUERY_DETAILS");
            LOG.info("SERVICE_READY");
            LOG.info("NOISY_HEARTBEAT");
            LOG.warning("DEPENDENCY_SLOW");
            LOG.log(
                    Level.SEVERE,
                    "ORDER_SAVE_FAILED",
                    new IllegalStateException("disk unavailable"));
        } finally {
            LOG.removeHandler(output);
            output.close();
        }
    }

    private static final class DeterministicHandler extends Handler {
        private DeterministicHandler() {
            setFormatter(new Formatter() {
                @Override
                public String format(LogRecord record) {
                    String cause = record.getThrown() == null
                            ? ""
                            : " | cause="
                                + record.getThrown()
                                        .getClass()
                                        .getSimpleName();

                    return record.getLevel().getName()
                            + " | " + record.getLoggerName()
                            + " | " + formatMessage(record)
                            + cause;
                }
            });
        }

        @Override
        public synchronized void publish(LogRecord record) {
            if (!isLoggable(record)) {
                return;
            }
            System.out.println(getFormatter().format(record));
        }

        @Override
        public void flush() {
            System.out.flush();
        }

        @Override
        public void close() {
            flush();
        }
    }
}
~~~

Compile and run with **JDK 17 or later**, in the directory containing the file:

~~~bash
javac -encoding UTF-8 HandlerDemo.java
java HandlerDemo
~~~

**Exact stdout of the example:**

~~~text
INFO | demo.orders.OrderService | SERVICE_READY
WARNING | demo.orders.OrderService | DEPENDENCY_SLOW
SEVERE | demo.orders.OrderService | ORDER_SAVE_FAILED | cause=IllegalStateException
~~~

Explanation of each event:

- **LOG.fine("QUERY_DETAILS")**: The FINE Logger accepts it, but the INFO Handler rejects it.
- **LOG.info("SERVICE_READY")**: Both Logger and Handler accept it; the Filter does not reject it, so one INFO line is printed.
- **LOG.info("NOISY_HEARTBEAT")**: The level is valid, but the Handler's Filter rejects it; no output line is produced.
- **LOG.warning("DEPENDENCY_SLOW")**: WARNING is logged normally.
- **LOG.log(Level.SEVERE, ..., Throwable)**: The Handler receives a LogRecord with **getThrown()**; the Formatter prints only **IllegalStateException** to keep the example concise.
- **setUseParentHandlers(false)**: Does not forward LogRecords to ancestor Handlers, preventing lines from the default configuration from affecting the output.
- **removeHandler(output)** and **close()**: Detaches and performs cleanup for the Handler owned by the demo.

**Note on Throwable:** When calling Logger.log(Level, String, Throwable), the exception is attached to the record so a Formatter can print its stack trace. The Formatter in this example prints only the type name to keep stdout stable; **it does not automatically print the full stack trace**. In production, consider how to log the cause chain, stack trace, contextual information, and limits on sensitive data.

The Handler above **does not replace a full production ConsoleHandler**. It serves to demonstrate filtering/formatting. If a custom Handler opens files, sockets, or queues, it must handle I/O errors, resource closing, thread safety, blocking/dropping records, and health monitoring of the logging pipeline itself.

## 8. The Three Abstract Methods of Handler

**java.util.logging.Handler** is an abstract class. When creating a custom Handler, you need to implement the following main methods:

### publish(LogRecord record)

~~~java
@Override
public void publish(LogRecord record) {
    if (!isLoggable(record)) {
        return;
    }

    // Format and send LogRecord to the chosen destination.
}
~~~

**publish** is responsible for outputting the event. In a custom Handler, check **isLoggable(record)** to respect the current level/filter. Avoid calling back into the same Logger from inside publish uncontrollably, as that can lead to recursive logging.

In a Handler that sends over the network, the destination may be failing. The policy in that case must be explicit: drop the record, block the thread, buffer, retry, or fail over to another destination. There is no single default choice that fits all requirements.

### flush()

~~~java
@Override
public void flush() {
    // Push buffered data to the destination if a buffer exists.
}
~~~

**flush** requests that buffered data be flushed according to the Handler/destination's capabilities. For a Handler that only calls System.out.println, flush may simply call **System.out.flush()**. For buffered files or streams, flush helps reduce data lingering in memory buffers.

**flush is not necessarily equivalent to fsync or a durability guarantee on disk.** Distinguish flushing application buffers from ensuring data is persisted without loss.

### close()

~~~java
@Override
public void close() {
    flush();
    // Close resources that the Handler actually owns.
}
~~~

**close** is used to end the lifecycle and release resources such as files or sockets. If the Handler does not own a passed-in stream, closing that stream can break other components. Ownership decisions must be explicit.

**In real applications, closing and removing a Handler from a Logger should be organized around application startup/shutdown lifecycles**, not called after every log emission. If a shared Handler is referenced by multiple Loggers, do not close it when an individual request or object finishes.

The code snippets in this section are **method illustrations**, not three separate classes or standalone runnable Java programs.

## 9. How Do Handler Level, Filter, and Logger Filter Work Together?

An evaluation rule can be represented as:

~~~text
Record has level L
     |
     v
Logger.isLoggable(L)?
     | no -> discard
     v yes
Logger Filter accepts?
     | no -> discard
     v yes
Find Handlers attached to the Logger and eligible parents
     |
     v
At each Handler: isLoggable(record)?
     | no -> that Handler does not publish
     v yes
publish + Formatter + I/O
~~~

**One Handler rejecting a record does not mean other Handlers must reject it as well.** Independent Handlers have their own levels and filters.

For example, suppose the root Logger has two Handlers:
- **CONSOLE** accepts WARNING+.
- **FILE** accepts FINE+.

When a child Logger at FINE logs a FINE event, FILE can receive it while CONSOLE can drop it. When the child Logger is at INFO, neither will receive FINE because it is blocked before the dispatch step.

**A Filter is not based solely on level.** It can inspect the message, logger name, event code, exception state, or additional fields, but avoid creating obscure filter conditions that cause security events or critical errors to vanish unnoticed.

## 10. Parent Handlers and Duplicate Logging

JUL Loggers have parent/child relationships by namespace. A Logger named after a class such as **com.example.orders.OrderService** typically has parent Loggers at the package or root level according to the existing Logger hierarchy.

**By default**, events from a child Logger continue to be forwarded to the parent Logger's Handlers. This helps centralize configuration: the application only attaches ConsoleHandler at the root, and Loggers in business classes share the output route.

However, it also causes duplicate logs if you add a separate Handler to a child Logger without considering the parent route:

~~~java
Logger logger = Logger.getLogger("com.example.orders.OrderService");
logger.addHandler(new ConsoleHandler());
// Logger still allows forwarding records to the parent's Handler.
~~~

The snippet above can cause a single record to appear multiple times: once in the newly added Handler and again in the parent's Handler. It also creates a new Handler without managing its lifecycle. Do not write this logic inside every service constructor.

There are two design approaches:

**Approach A — Shared Handler at root/parent:** Keep Handlers configured centrally; child Loggers only emit events and adjust levels when needed.

**Approach B — Dedicated Handler route for a subtree:** Attach all necessary Handlers to the child Logger, and use:

~~~java
logger.setUseParentHandlers(false);
~~~

This is a configuration setting, not a guarantee that logs will be emitted. If you disable parent forwarding without **a valid Handler on the child logger**, logs may reach no destination at all.

Note: **setUseParentHandlers(false)** only controls forwarding to ancestor Handlers; it **does not disable level inheritance**. A Logger can still inherit its effective level from its parent if **setLevel(null)** is set.

In many production applications, centralized configuration and avoiding ad-hoc Handler creation in business code are much easier to control.

## 11. Configuring Handlers in logging.properties

You do not have to create every Handler in Java code. JUL supports loading configuration from a **logging.properties** file.

Example:

~~~properties
# Common handler attached to root
handlers = java.util.logging.ConsoleHandler

# Root logger level
.level = INFO

# ConsoleHandler level and Formatter
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Enable FINE specifically for a class under investigation
com.example.payment.PaymentClient.level = FINE

# Log other classes at their inherited level
com.example.orders.OrderService.level = INFO
~~~

Here:
- The Root Logger has level INFO.
- The Console Handler is allowed to receive FINE.
- The Logger **com.example.payment.PaymentClient** is set to FINE, so FINE logs from that class can propagate up to ConsoleHandler.
- The Logger **com.example.orders.OrderService** remains at INFO, so it does not emit FINE.

If ConsoleHandler.level=INFO were set instead of FINE, then even with PaymentClient set to FINE, ConsoleHandler would drop FINE. This is a common reason developers think logger levels are not working.

To load the file when starting a compiled Java program:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This is a **command template for an application with a com.example.Main class in the out directory**, not the command to run the HandlerDemo demo. For the demo, configuration is set directly in main so the result is deterministic.

When using **SLF4J + Logback** or **Log4j 2**, the corresponding configuration files are logback.xml, log4j2.xml, or another format supported by the backend; **JUL's logging.properties does not automatically configure Appenders in those backends**. An application using a bridge may behave differently, so you must verify the actual pipeline.

## 12. Handler and Appender: Connections Across Java Logging Systems

| Aspect | JUL | Logback | Log4j 2 |
| --- | --- | --- | --- |
| Common logging API | java.util.logging.Logger | SLF4J Logger | Log4j API or SLF4J via provider |
| Output target component | Handler | Appender | Appender |
| Console target example | ConsoleHandler | ConsoleAppender | Console Appender |
| File logging example | FileHandler | FileAppender/RollingFileAppender | File/RollingFile Appender |
| Formatting | Formatter | Encoder/Layout/Pattern | Layout |
| Filtering | Logger/Handler Filter and level | Logger/Appender Filter and level | Logger/Appender Filters and level |
| Parent propagation | useParentHandlers | additivity | additivity |
| Typical configuration | logging.properties | logback.xml | log4j2.xml |

The similarity lies in **architectural role**: Logger emits events; Handler/Appender performs the output routing. The internal mechanics, lifecycle, configuration, and extensibility are **not identical**.

When a project has standardized on a backend other than JUL, you generally should not add a JUL FileHandler inside individual classes just to write to a separate file. Use the backend's own Appender or a properly configured bridge; if multiple providers/bridges are active at once, events may be duplicated or misrouted.

## 13. Designing Custom Handlers for Production

This lesson only requires understanding Handlers, but before writing a real custom Handler, consider:

### 13.1. Concurrency and Lifecycle

Multiple threads may call a logger simultaneously. A Handler accessing buffers, files, or sockets must handle **race conditions**, record atomicity, event ordering, and shutdown behavior. Use synchronization or an internal queue as needed, balancing throughput and blocking.

If a Handler writes to a file, manage opening/closing the resource in the application lifecycle. If a shared Handler is used by multiple Loggers, do not close it from an individual request.

### 13.2. Do Not Let Logging Errors Accidentally Break Business Logic

A custom Handler may encounter IOException, timeouts, or encoder errors. You need a clear policy when writes fail. JUL provides **ErrorManager** for Handlers to report errors during publishing; many standard Handlers use this mechanism instead of throwing arbitrary I/O exceptions into business code paths.

However, do not automatically swallow all errors in an audit path that must be durable. Audit requirements may demand a different architecture, such as an outbox, a durable queue, or write confirmation before completing a transaction.

**Avoid recursive logging:** If publish encounters an error and calls the Logger that uses that same Handler, the system can enter an infinite loop or overload. Choose a dedicated error-reporting mechanism designed to avoid loops.

### 13.3. Controlling Backpressure

If the output destination is slower than the rate at which LogRecords are generated:
- Synchronous writes can increase business latency.
- Asynchronous writes can fill up queues.
- Dropping logs can lose critical evidence.
- Blocking producers can cause cascading failures.

Choose based on SLO targets, cost, event types, and compliance requirements. **A custom Handler is not automatically safe under heavy load** merely because it implements publish, flush, and close.

### 13.4. Sensitive Data and Log Structure

Do not log passwords, tokens, private keys, login cookies, payloads containing payment data, or unnecessary personal data. A custom Formatter can output structured JSON, but you must still apply redaction, access control, retention, and protect against log injection when messages contain untrusted input.

Useful fields typically include **timezone-aware timestamp, level, service, logger_name, event_code, request_id/trace_id, operation, exception type, and outcome**. A Handler can only output fields already present in the LogRecord or properly attached; creating a new Handler does not automatically generate trace IDs.

## 14. Common Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Thinking a Handler is an exception catch block | Confuses logging with error handling | Distinguish LogRecord/Handler from try-catch |
| Setting Logger to FINE but Handler to INFO | FINE logs still do not appear | Check both thresholds |
| Adding ConsoleHandler in every constructor | One Logger gets multiple Handlers, duplicate logs | Configure Handlers centrally, manage lifecycle |
| Attaching a Handler to a child logger while still forwarding to parent | Same event may be printed multiple times | Use a shared root Handler or disable parent handlers appropriately |
| Disabling parent handlers without adding a Handler | Events do not reach the intended destination | Verify the output route and directly attached Handlers |
| Skipping isLoggable in custom publish | Ignores level or Filter | Check isLoggable(record) before publishing |
| Using only getMessage() when stack traces are needed | Loses Throwable in output | Pass Throwable and use an appropriate Formatter |
| Assuming ConsoleHandler always writes to stdout | Hard to verify output in terminal | Distinguish stderr and stdout |
| Forgetting to flush/close FileHandler | Data remains buffered, resources are leaked | Close Handlers at shutdown according to ownership |
| Treating a network Handler as durable | Logs may be lost on network/process failure | Use a pipeline with guarantees and separate monitoring |
| Logging everything at SEVERE | Noise, misleading incident signals | Choose levels by impact; INFO/WARNING/FINE as appropriate |
| Putting tokens or sensitive payloads into logs | Data leaks | Strip/redact data at the emission point |
| Naming Loggers by request ID | High cardinality, hard to manage | Name Loggers by class/package, put request ID in context |
| Using a JUL Handler as a Logback Appender | Incompatible API/backend | Choose the right configuration mechanism and bridge |

## 15. Handler Configuration Checklist

1. **Is the application using JUL or SLF4J/Logback/Log4j 2?** Identify the backend to choose the right Handler/Appender.
2. **Are Loggers named sensibly?** Usually by class/package, e.g., com.example.orders.OrderService.
3. **Which Handlers are receiving records?** Check Handlers on both the direct logger and its ancestors.
4. **Are Logger/Handler levels appropriate?** Do not forget filtering at both places.
5. **Does the Filter drop important events?** Evaluate by event code and business outcome.
6. **Does the Formatter include enough information?** Timestamp, level, logger, message, exception, and correlation when needed.
7. **Are there duplicate logs from parent handlers?** Avoid attaching duplicate Handlers and understand useParentHandlers.
8. **Is the output destination working?** Check stderr/stdout, file permissions, paths, network, and collector.
9. **Is the Handler lifecycle clear?** Define ownership, flush, close, and shutdown behavior.
10. **Are production requirements met?** Performance, concurrency, backpressure, security, and retention.
11. **Have you tested the result in a real runtime environment?** A test should verify the LogRecord's path, not merely that Logger.info was called.

## 16. Self-Check Questions

**1. What does a Handler in JUL do?**  
A Handler receives LogRecords from a Logger and publishes them to a destination, optionally using its own level, Filter, and Formatter.

**2. With Logger.INFO and Handler.ALL, will FINE be printed?**  
No. The Logger already blocks FINE beforehand.

**3. With Logger.FINE and ConsoleHandler.INFO, will FINE be printed?**  
No. The Handler blocks it, even though the Logger allowed it.

**4. Why can enabling useParentHandlers cause duplicate logs?**  
Because the same LogRecord can pass through both the child logger's Handler and an ancestor's Handler; if both write to the console, the output may be printed twice.

**5. Does ConsoleHandler print to stdout or stderr by default?**  
Typically **stderr**. If you need consistent stdout, you can write a custom Handler or choose a backend that supports configuring the console target.

**6. Which methods does a custom Handler need?**  
The abstract methods **publish(LogRecord), flush(), close()**; when implementing publish, honor **isLoggable(record)**.

**7. Does setUseParentHandlers(false) disable level inheritance from the parent?**  
No. It only disables forwarding records to ancestor Handlers; the effective level can still be inherited if the Logger does not set a level directly.

**8. Does a Handler automatically guarantee no log loss when a process crashes?**  
No. Durability depends on the destination, buffering, flushing, architecture, and the guarantees of the collection system.

**9. Is a JUL Handler the same as a Logback Appender?**  
They are not the same API, even though both handle delivering log events to a destination.

**Takeaway:** **The Logger decides whether to emit an event; the Handler decides where and how to publish it.** For logging to work properly, you must understand levels, Filters, Formatters, parent/child Logger routing, lifecycle, and destination characteristics together. A well-configured Handler gives a Java system enough logs for diagnosis without causing duplication, data loss, or uncontrolled costs.

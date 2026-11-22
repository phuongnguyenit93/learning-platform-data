# JDK Logger: java.util.logging.Logger

**java.util.logging.Logger** is the standard logger class built into the JDK, part of the Java Logging API (commonly called **JUL**, short for *Java Util Logging*). Applications can use Logger to emit events such as startup, task processing, warnings, and errors without installing SLF4J, Logback, or Log4j 2.

Key point: **Logger receives log requests and applies event acceptance rules; Handler receives forwarded events and writes them to the destination; Formatter decides how they are presented.** Calling `logger.info(...)` alone does not guarantee a log line will appear, because log levels, filters, handlers, and runtime configuration can all affect the outcome.

## 1. Where does JUL live in the JDK?

JUL is built into the standard **java.logging** module, commonly using the following classes:

| Component | Class/Interface | Role |
| --- | --- | --- |
| Logger | `java.util.logging.Logger` | Object that application code calls to create log events |
| Level | `java.util.logging.Level` | Granularity/severity level |
| LogRecord | `java.util.logging.LogRecord` | Data of a log event, containing level, message, parameters, exception, and metadata |
| Handler | `java.util.logging.Handler` | Receives and outputs logs; can filter by level/filter |
| ConsoleHandler | `java.util.logging.ConsoleHandler` | Default handler targeting the console, typically writes to **stderr** |
| FileHandler | `java.util.logging.FileHandler` | Writes logs to a file, supporting size limits and file rotation |
| Formatter | `java.util.logging.Formatter` | Converts a LogRecord into an output string |
| Filter | `java.util.logging.Filter` | Performs an additional check on whether a LogRecord is accepted |
| LogManager | `java.util.logging.LogManager` | Manages JUL loggers and logging configuration |

Conceptual model:

~~~text
Java Code
   |
   | Logger.getLogger(...).info(...)
   v
java.util.logging.Logger
   |  checks Level, Filter at the emitting logger
   v
LogRecord
   |
   +--> Handler on logger (if any)
   |
   +--> Handler on parent logger (if forwarding is enabled)
          |
          +--> checks Handler's Level/Filter
          |
          +--> Formatter
                    |
                    +--> stderr / file / other destination
~~~

This is a learner-oriented view; in the implementation, `LogRecord` is the object that Logger passes to Handler after acceptance, and Formatter is typically used by Handler. Different configurations can cause an event to go to multiple handlers or to no handler at all.

JUL runs on the classpath of a regular Java SE application. If you build a **named Java module**, you must declare the module dependency:

~~~java
// module-info.java: example for a modular application
module demo.logging {
    requires java.logging;
}
~~~

This is an illustrative module descriptor snippet, not a standalone program; classpath applications do not need to create `module-info.java` just to use JUL.

## 2. Creating and Naming a Logger

The most common way is to use `Logger.getLogger(String name)`:

~~~java
import java.util.logging.Logger;

public final class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void acceptOrder(String orderId) {
        LOG.info("Order accepted: " + orderId);
    }
}
~~~

This is a valid class but an **illustrative snippet**, without a `main` method to run directly. In a packaged application, `OrderService.class.getName()` returns the fully qualified name, such as `com.example.orders.OrderService`.

Some important points:

- **Loggers have stable names**, usually following the class or package name. This name allows configuring the log level for one component without modifying the entire application.
- `Logger.getLogger(name)` returns an already registered logger with the matching name if one exists; do not treat each call as a new independent logging instance.
- The **`private static final Logger`** pattern holds a strong reference to the logger for the class's lifecycle and avoids looking up the logger on every operation. JUL manages named loggers using a mechanism that may use weak references; do not rely on a logger not referenced by source code staying alive forever.
- **Do not use requestId, userId, orderId, or timestamp to create dynamic Logger names**. Those are event data and should be placed in the message/context; dynamic names increase the number of loggers and make namespace-based configuration hard to control.
- `Logger.getLogger("com.example.orders")` works for a shared package or subsystem logger, but for per-class logs, using `Class.getName()` is usually easier to trace.

JUL also provides `Logger.getAnonymousLogger()` for cases where no globally registered name is needed. Anonymous loggers have different management behavior from named loggers; in typical business applications, a stably named logger is easier to configure and investigate.

### Root logger and Global logger

JUL has a **root logger** whose name is the empty string `""`. Named loggers typically sit under root in a hierarchy. You can obtain root with:

~~~java
Logger root = Logger.getLogger("");
~~~

JUL also has a logger named **global** (`Logger.getGlobal()`), but using a separate per-class logger usually identifies the event source more clearly. Do not equate the global logger with the root logger: they are different loggers.

## 3. Emitting Logs with the JDK API

`java.util.logging.Logger` provides convenience methods:

~~~java
logger.severe("Unrecoverable failure");
logger.warning("Retry scheduled");
logger.info("Task finished");
logger.config("Loaded configuration");
logger.fine("Cache lookup");
logger.finer("More detailed operation");
logger.finest("Fine-grained trace");
~~~

These are illustrative statements inside a method that already has a `logger` variable of type `java.util.logging.Logger`. There are also `log(...)` overloads:

~~~java
logger.log(Level.INFO, "event=job_completed jobId={0}", jobId);
logger.log(Level.SEVERE, "event=job_failed", exception);
logger.log(Level.FINE, () -> "details=" + computeDetails());
~~~

This snippet assumes `jobId`, `exception`, and `computeDetails()` already exist. The three overloads have different meanings:

- **`log(Level, String, Object)`** uses one argument to format the message, in `{0}` format.
- **`log(Level, String, Throwable)`** attaches an exception to the event so the formatter can print the stack trace.
- **`log(Level, Supplier<String>)`** only computes the message when the event passes the appropriate level check; for expensive-to-compute data, this is a useful choice.

Do not mix JUL's **`{0}`, `{1}`** syntax with SLF4J's **`{}`** parameter syntax. Both Logger types share the same simple name but belong to two different APIs.

## 4. JUL Log Levels

JUL declares the following standard levels:

| Level | Common Purpose | Example |
| --- | --- | --- |
| `SEVERE` | Serious error causing a function/task to fail | Unable to complete job due to dependency unavailable |
| `WARNING` | Notable anomaly that may still be recoverable | Retry, fallback, unexpected data |
| `INFO` | Meaningful normal operational milestone | Service ready, import completed |
| `CONFIG` | Configuration or initialization information | Loading operationally relevant configuration |
| `FINE` | Diagnostic detail | Cache hit/miss decision |
| `FINER` | Deeper detail | Intermediate steps |
| `FINEST` | Very detailed level | Low-level execution flow tracing |
| `ALL` | Allows all normal levels through the level check | Used when full observation is desired |
| `OFF` | Disables normal log events at the logger or handler | Reduces/disables logging in a specified scope |

JUL compares levels by **numeric priority**. For standard levels, SEVERE is more severe than WARNING, WARNING more than INFO, INFO more than CONFIG and FINE. When the threshold is INFO, an INFO/WARNING/SEVERE event is accepted by the logger based on level, while CONFIG/FINE/FINER/FINEST are blocked.

Set the threshold directly:

~~~java
logger.setLevel(Level.INFO);
~~~

Check whether a level is enabled:

~~~java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Detailed state");
}
~~~

If `logger.getLevel()` returns **null**, it usually means the logger **inherits its effective level from its parent logger**, not that the Logger cannot log. To determine whether an event will actually be output, you also need to check the Handler's level/filter and the path to the handler.

When comparing with SLF4J, remember that JUL uses `SEVERE`/`WARNING`/`FINE`, whereas SLF4J typically uses `ERROR`/`WARN`/`DEBUG`. The two level sets correspond in operational purpose in many cases, but they are not the same enum or API names.

## 5. LogRecord: Event Data

In JUL, an event can be represented by **`LogRecord`**. This object carries information such as:

- **Level:** the level at which the event was emitted;
- **Message and Parameters:** the template and the data passed into the template;
- **Logger name:** the name of the logger emitting the event;
- **Instant/timestamp:** the timestamp of the record;
- **Thrown:** the exception, if any;
- **Other thread/component info:** metadata managed by the logging system.

Illustrative example:

~~~java
LogRecord record = new LogRecord(
        Level.WARNING,
        "event=inventory_low sku={0} available={1}"
);
record.setParameters(new Object[]{"book-1", 2});
record.setLoggerName(logger.getName());
logger.log(record);
~~~

This is a code snippet inside a method that already has `logger` and imports `LogRecord` and `Level`. In most business code, `logger.log(Level, String, Object[])` is sufficient: **you do not need to manually create a LogRecord for every statement**.

`Formatter.formatMessage(record)` can combine the template and parameters to produce the display text. If you write a custom Formatter that only returns `record.getMessage()`, you may see raw `{0}` instead of the actual value. To preserve additional data such as exceptions, you must handle `record.getThrown()` or use an appropriate Formatter.

LogRecord also supports resource bundles for localizing messages in applications that need it; this is a JUL capability, not required for typical business logging.

## 6. Handler and Formatter: Why Calling Logger Does Not Guarantee Output

Logger applies log levels and filters at the emission source. Then the event is forwarded to Handlers attached to the logger and, if enabled, the parent logger's Handlers.

Common Handlers:

- **`ConsoleHandler`**: prints to the console, typically via **stderr**; do not assume logs are on stdout by default.
- **`FileHandler`**: writes to files; supports rolling/rotation options by size and file count.
- **`StreamHandler`**: base class for Handlers writing to a stream; requires attention to stream management/flushing.
- **`MemoryHandler`**: buffers logs and pushes them to a target Handler based on configured conditions.
- **Custom Handler**: sends events to a custom destination; requires proper error handling, synchronization, and resource lifecycle management.

Handlers have their own thresholds:

~~~java
logger.setLevel(Level.FINE);
handler.setLevel(Level.WARNING);
~~~

For example, if the logger allows FINE but the Handler only accepts WARNING: a `logger.fine(...)` call can pass the logger but **be blocked by the handler**. Do not change only the logger level and conclude the backend is broken when you do not see FINE.

**Formatter** receives a LogRecord and produces the output content. JUL includes `SimpleFormatter` and `XMLFormatter` as well as the ability to write custom formatters. How timestamps, levels, logger names, parameters, and Throwables are formatted depends on the Formatter. Manually inserting all metadata into the message can easily cause redundancy or inconsistency.

**Filter** can be attached to a Logger or Handler to apply additional conditions beyond the log level. For example, allowing only one event type; a misconfigured filter can also cause records to disappear. Not all Handlers share the same filter: each Handler can decide independently.

## 7. Standalone Java 17+ Example

The following complete example uses **only the JDK** to demonstrate four things:

1. A logger level of INFO allows INFO/WARNING/SEVERE but drops FINE.
2. JUL message templates `{0}`, `{1}` have their values substituted by the Formatter.
3. Throwable is stored separately in the record and can have its information output by the formatter.
4. Changing the level to FINE causes the subsequent FINE call to appear.

Create the file **JulLoggerDemo.java**:

~~~java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulLoggerDemo {
    private static final Logger LOG =
            Logger.getLogger(JulLoggerDemo.class.getName());

    public static void main(String[] args) {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                String cause = record.getThrown() == null
                        ? ""
                        : " | cause="
                                + record.getThrown().getClass().getSimpleName();
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + cause + System.lineSeparator();
            }
        });
        LOG.addHandler(console);

        LOG.fine(() -> "event=cache_probe");
        LOG.log(Level.INFO,
                "event=order_accepted orderId={0} units={1}",
                new Object[]{"ord-17", 3});
        LOG.log(Level.WARNING,
                "event=inventory_low item={0}", "book-1");
        LOG.log(Level.SEVERE, "event=payment_failed orderId=ord-18",
                new IllegalStateException("timeout"));

        LOG.setLevel(Level.FINE);
        LOG.fine(() -> "event=cache_probe");

        LOG.removeHandler(console);
        console.close();
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac JulLoggerDemo.java
java JulLoggerDemo
~~~

Exact output on **stderr** (timestamps omitted by the custom formatter written in the example):

~~~text
INFO | event=order_accepted orderId=ord-17 units=3
WARNING | event=inventory_low item=book-1
SEVERE | event=payment_failed orderId=ord-18 | cause=IllegalStateException
FINE | event=cache_probe
~~~

Step-by-step explanation:

- The first FINE call produces no output because the Logger is at INFO. The `Supplier` in this call does not need to build the message.
- INFO uses a template with two parameters and is accurately substituted by `formatMessage(record)`.
- WARNING has one string parameter.
- SEVERE attaches an `IllegalStateException` via the overload taking a Throwable; the illustrative formatter prints only the **exception class name**, not the full stack trace.
- After `LOG.setLevel(Level.FINE)`, the final FINE call passes both the logger and the ConsoleHandler (handler set to ALL).
- `setUseParentHandlers(false)` prevents the event from continuing to root/parent handlers and being printed an extra time; the program explicitly removes and closes the handler at the end of main.

**Do not use a formatter that only prints the exception name in systems that require serious error analysis.** Production formatters typically need to output stack traces according to security policies. Configuring the Handler in main is only for the example to reproduce the output; real applications should manage logging centrally.

## 8. Logger Hierarchy in JUL

JUL organizes loggers by names with dot-separated components:

~~~text
""  (root logger)
  |
  +-- com.example
        |
        +-- com.example.orders
              |
              +-- com.example.orders.payment
~~~

`com.example.orders.payment` can be a child logger of `com.example.orders` when that parent logger exists; the actual direct parent is the nearest existing ancestor logger in the system. You can check this with `child.getParent()`.

Two **distinct** concepts:

**A. Level inheritance:** `child.setLevel(null)` means the child logger takes its effective level from the nearest parent that has a specific level set. If the parent is WARNING, child INFO events can be dropped right at the emission source.

**B. Forwarding events to parent handlers:** `child.setUseParentHandlers(true)` allows a record accepted by the child to reach handlers on parent loggers. `false` prevents the child from using parent handlers. This mechanism is independent of whether the child inherits its level.

Important: **JUL does not re-apply the parent logger's level/filter once a LogRecord has been accepted by the child logger and forwarded to the parent's handler.** It is the **parent's handler** that checks its own level/filter. Therefore, if the child has level FINE, the parent has level WARNING, and the parent handler is at ALL, the child's FINE record can still be output.

Illustrative example:

~~~java
Logger parent = Logger.getLogger("demo.orders");
Logger child = Logger.getLogger("demo.orders.payment");

parent.setLevel(Level.WARNING);
child.setLevel(null);  // child inherits WARNING
child.warning("retry requested");

child.setLevel(Level.FINE);   // child overrides level
child.fine("diagnostic info"); // can reach parent handler if handler allows
~~~

This is only a snippet inside a Java method, not a complete program. Printed output also depends on handlers, filters, and `setUseParentHandlers`.

If you both attach a ConsoleHandler to the child and allow the child to forward to the ConsoleHandler on root, an event can be printed twice. When you want the child to write only through its own handler, use `setUseParentHandlers(false)` **and ensure its own handler exists**.

In JUL, logger names are **not a Java class `extends` tree** and **not a thread hierarchy**. This is a configuration/routing hierarchy by logger name, usually tied to package or class names.

## 9. Configuring JUL with logging.properties

Instead of attaching Handlers and calling `setLevel` throughout source code, an application can place configuration in a `logging.properties` file.

Example:

~~~properties
# Handler attached to root
handlers = java.util.logging.ConsoleHandler

# General level for loggers inheriting from root
.level = INFO

# Console handler can also receive FINE from child loggers
java.util.logging.ConsoleHandler.level = ALL
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Reduce logs in most of the orders module
com.example.orders.level = WARNING

# Increase detail specifically for payment
com.example.orders.payment.level = FINE
~~~

Run a compiled application class with the configuration file:

~~~bash
java -Djava.util.logging.config.file=logging.properties MyApplication
~~~

In this command, **MyApplication** is a hypothetical application class name with `main`, not an extra file provided in this article. Place the property **before the class name** so the JVM passes the configuration path to JUL at startup.

Points to remember:

- `handlers` in the example declares root handlers; child loggers can forward events there by default.
- `.level` is the level of the **root logger**; it is not level syntax for all Handlers.
- `java.util.logging.ConsoleHandler.level` is the Handler's own threshold. Setting root to INFO while Handler is ALL allows child loggers that set FINE themselves to output FINE records through the root Handler.
- `com.example.orders.payment.level=FINE` increases detail in the corresponding named package without enabling FINE for all components.
- **Path, runtime environment, and configuration load timing** must be correct. If code in `main` later explicitly calls `setLevel`, adds/removes Handlers, or changes Filters, it can alter behavior compared to the properties file.
- Use `LogManager` to manage configuration centrally when the application needs to reload/update; modifying the file on disk **does not automatically** update all running loggers.

Java frameworks like Spring Boot often have their own logging configuration and default framework backend. When working within a framework, check which logging system is actually handling logs before treating `logging.properties` as the sole configuration source.

## 10. Methods and Properties to Know

| JUL API | Meaning | Notes |
| --- | --- | --- |
| `Logger.getLogger(name)` | Get logger by name | Use a stable name, usually from class |
| `Logger.getGlobal()` | Get global logger | Less source context than a per-class logger |
| `Logger.getParent()` | Get current parent logger | Not present on `org.slf4j.Logger` |
| `Logger.getLevel()` | Get directly assigned level | `null` may mean inherited |
| `Logger.setLevel(level)` | Set logger level | `null` to inherit |
| `Logger.isLoggable(level)` | Check acceptance threshold at logger | Not enough to conclude the handler will output |
| `Logger.log(Level, String)` | Emit message with level | No formatting parameters attached |
| `Logger.log(Level, String, Object[])` | Emit template with multiple parameters | JUL uses `{0}`, `{1}` |
| `Logger.log(Level, String, Throwable)` | Log event with exception | Preserves Throwable instead of only calling `getMessage()` |
| `Logger.log(Level, Supplier<String>)` | Lazily build message when level is enabled | Suitable for expensive messages |
| `Logger.addHandler(handler)` | Attach Handler to logger | Can cause duplicates if parent also outputs |
| `Logger.removeHandler(handler)` | Remove Handler | Handler resources need to be closed properly |
| `Logger.setUseParentHandlers(boolean)` | Enable/disable forwarding events to parent handlers | Does not change level inheritance |
| `Logger.setFilter(filter)` | Set additional Filter | Can block events even if level matches |

The methods in the table belong to **`java.util.logging.Logger`**. Do not port syntax verbatim to SLF4J, Logback, or Log4j 2 just because they also have an object called Logger.

## 11. Distinguishing java.util.logging.Logger and System.Logger

Since Java 9, the JDK also has **`java.lang.System.Logger`**, typically obtained via **`System.getLogger(name)`**. This is a system-level logging API of the Java Platform, using levels from `System.Logger.Level` such as INFO, WARNING, ERROR, DEBUG, and TRACE.

Example:

~~~java
System.Logger logger = System.getLogger("demo.platform");
logger.log(System.Logger.Level.INFO, "Application initialized");
~~~

This is an illustrative snippet inside a method. `System.Logger` is a **different type** from `java.util.logging.Logger` and also different from SLF4J's `org.slf4j.Logger`.

In a standard JDK, the default `System.LoggerFinder` mechanism can route to the platform logging system; the implementation can be replaced by an appropriate provider. Therefore, do not assume that every JUL configuration approach or every `Logger.log(...)` overload applies to `System.Logger`.

When the topic is **Java Util Logging**, look for imports of `java.util.logging.Logger` along with `Level`, `Handler`, and `LogManager`. If a project uses `System.Logger`, that is a different API requiring inspection of the specific backend/bridge.

## 12. Performance, Concurrency, and Data Safety

### Avoiding Unnecessary Message Construction

A statement like:

~~~java
logger.fine("state=" + expensiveStateDump());
~~~

still calls `expensiveStateDump()` **before** the Logger can drop FINE. If this data is expensive, use the Supplier overload:

~~~java
logger.fine(() -> "state=" + expensiveStateDump());
~~~

In lambda form, message computation is deferred until the event is needed at an enabled log level. If you pre-compute expensive objects/strings **before** the lambda statement, the lazy benefit is lost for the work already done.

For small data, do not create complex logic just to avoid a few cheap operations. Focus optimization on hot paths and expensive serialization/formatting work.

### Logger and Multithreading

A per-class logger is commonly shared across many threads; JUL has internal mechanisms to manage logging in concurrent environments. However:

- Logs from multiple threads can interleave; do not infer absolute business ordering solely from line positions.
- Each **custom** Handler or Formatter must be written to be thread-safe, including shared state and output.
- A logger name is not a correlation ID. To correlate records from the same request/job, add requestId, jobId, or traceId to the event.
- When writing a Handler for file/network output, consider buffering, flushing, shutdown, I/O errors, and potential log loss when the process terminates abruptly.

### Controlling Sensitive Content

Do not log passwords, tokens, API keys, Authorization headers, session cookies, card data, or full requests/responses containing private information directly. `logger.info("Request: " + request)` can accidentally expose sensitive data to log files via `toString()`.

Choose useful fields such as `event`, internal `requestId`, `outcome`, `reason`, `durationMs`; remove or mask other information before emitting the event. For untrusted input containing newlines/control characters, use appropriate encoding/escaping to reduce the risk of **log injection** in text records.

Placeholders `{0}` help format parameters but **do not automatically mask secrets** and do not replace untrusted input sanitization.

## 13. JUL in Applications with Multiple Logging Frameworks

JUL is both an API and has built-in JDK implementations/handlers. **SLF4J** is a different facade, while **Logback** and **Log4j 2 Core** are different backends with their own configurations.

Some applications want to consolidate all events into a single backend. In that case, a bridge can be used, such as the route **JUL → SLF4J → chosen backend**. However, adding a bridge library to dependencies does not necessarily activate forwarding; with JUL you typically have to install the bridge handler and manage existing JUL handlers to avoid duplicate logs.

Do not automatically add multiple reverse bridges, as this can create loops or provider conflicts. If a framework already configures logging, prefer the mechanism the framework provides.

Key distinctions to keep clear:

- **JUL Logger** in source code uses `java.util.logging.Logger`, `Level.FINE` levels, and JUL handlers.
- **SLF4J Logger** uses `org.slf4j.Logger`, DEBUG/WARN/ERROR levels, and the backend determines appenders and output.
- Java Platform's **System.Logger** is a separate API backed by an appropriate logger finder.

To determine which system a statement goes through, inspect **imports in code** and **logging backend dependencies/runtime**, then check the actual handlers/appenders.

## 14. Common JUL Logger Pitfalls

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `logger.fine(...)` not visible | Effective level is INFO or handler blocks FINE | Check `getLevel()`, `isLoggable(FINE)`, handler level/filter |
| `getLevel()` is null | Logger is inheriting level from parent | Check `getParent()` and levels up the hierarchy |
| INFO printed twice | Custom handler added while still using parent handlers | Check `getHandlers()` and `getUseParentHandlers()` |
| Logger exists but no records | No suitable handler, handler disabled, filter drops it, or output goes elsewhere | Trace Logger → Handler → Formatter → stdout/stderr/file |
| Logs appear on stderr instead of stdout | `ConsoleHandler` typically uses stderr | Check both streams; do not assume logs are lost |
| Message still shows raw `{0}` | Custom formatter does not call `formatMessage(record)` | Use a Formatter that processes parameters properly |
| Stack trace missing | Only `exception.getMessage()` logged or custom formatter ignores `record.getThrown()` | Pass Throwable; use a formatter that handles exceptions |
| `logging.properties` has no effect | Wrong JVM property timing/path, framework controls backend, or code overrides level | Check JVM command, loaded file, and post-startup config |
| Mistaking SLF4J `Logger` for JUL | Different imports | Check package names and method signatures |
| Logger behaves inconsistently when code holds no reference | Named logger lifecycle management and weak references | Keep logger `static final` per class instead of repeatedly creating and discarding |
| Logs too long or leak data | String concatenation or logging entire objects/raw payloads | Select necessary fields, avoid sensitive data, use lazy logging if appropriate |
| Logs from multiple threads hard to correlate | Missing requestId/jobId/traceId | Put IDs in message/structured context, not in Logger name |

### Troubleshooting Checklist When Logs Are Missing

1. Confirm the code path actually reaches the logger statement.
2. Verify whether the logger belongs to JUL or another API and identify the exact logger name.
3. Check the direct or inherited level, then test `isLoggable(level)`.
4. Inspect the Filter on the logger, the Handler list, and `setUseParentHandlers`.
5. Check each Handler: level, Filter, Formatter, and output destination.
6. Look for logs in **stderr**, files, or container logs; do not assume everything goes to stdout.
7. If using a bridge/framework, check dependencies, forwarding loops, and the logging configuration actually loaded.

If a LogRecord is dropped at the Logger, raising the Handler's level is not enough. If the Logger accepts it but the Handler drops it, changing only the Logger's level will not solve the problem either.

## 15. Practice Exercise

Suppose the JUL configuration is as follows:

~~~text
Parent logger: demo.orders, level = WARNING
Child logger:  demo.orders.payment, level = null
Parent handler level = INFO
Child has no own handler
Child uses parent handlers
~~~

Predict:

1. Is `child.info("start")` accepted by the Logger?
2. Is `child.warning("retry")` output by the parent handler?
3. If `child.setLevel(Level.FINE)`, is `child.fine("details")` output?
4. Then if `parentHandler.setLevel(Level.ALL)`, how does question 3 change?
5. If `child.setUseParentHandlers(false)` while still having no own handler, where does a WARNING record go?

**Answers:**

1. **No**: child inherits WARNING, so INFO is dropped at the source.
2. **Yes**: WARNING passes both child and the parent handler at level INFO.
3. **Not yet output**: child accepts FINE, but the parent handler at level INFO drops FINE.
4. **Output**: the handler allows ALL. The parent logger's WARNING level is not re-applied to filter events already accepted by the child.
5. **No output destination** in the given configuration, because the child stopped forwarding to parent handlers and has no own handler. Having no output does not prove the child's level was disabled.

This exercise highlights two independent steps: **whether the Logger accepts the event** and **whether the event reaches a Handler that accepts it**.

## 16. Takeaways for Using the JDK Logger Effectively

When writing Core Java, create a **`private static final Logger` per class**, use stable logger names, choose log levels based on actual operational impact, pass templates/parameters or Throwables to the right overloads, and place level/handler configuration where it can be managed centrally.

To enable detailed logs for a group of classes, use **hierarchy and package-level settings**. To control output, inspect **Handler, Formatter, Filter, and parent handlers**. For expensive debug logging, consider **Supplier**. For sensitive data, exclude it at the emission source.

**The JDK Logger is sufficient for many basic Java applications**, but when integrating frameworks or other logging systems, you must identify the exact API and backend running. A `logger.info(...)` call only starts a log event; log levels, configuration, and handlers determine whether the record appears and is useful for investigation.
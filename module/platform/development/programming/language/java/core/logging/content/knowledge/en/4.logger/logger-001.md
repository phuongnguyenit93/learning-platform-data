# What is a Logger? — Java Core Logging

## 1. The Logger Concept

In Java, a **Logger** is the object that source code uses to **emit log event records** while a program is running. Instead of printing arbitrary messages with System.out.println(...), developers call logger methods with a **level** and descriptive information so the logging system can decide which events to record, how to format them, and where to send them.

Example of logging intent:

~~~text
INFO    Application has started
WARNING Missing optional configuration; using default value
SEVERE  Unable to connect to payment service
~~~

These are **illustrative messages**, not Java's default output: timestamps, class names, threads, layout, and output destinations depend on configuration.

A useful mental model:

- **Logging**: the activity of recording events throughout an application's lifecycle.
- **Logger**: the entry point (object/API) that application code calls to create log events.
- **Handler/Appender**: the component that receives events to output them to the console, a file, or a collection system.
- **Formatter/Encoder**: the component that determines how event information is represented, such as timestamped text or JSON.

A Logger **is not a log storage location**. A logger call only results in an actual log line when the event passes through filters and has an appropriate output component. Therefore, calling LOGGER.info(...) is not enough to guarantee that the log has been durably written to a file or external service.

## 2. Why Do Applications Need a Logger?

A Logger helps separate **the observability intent of source code** from **how logs are operated and stored**:

1. **Event level classification**: INFO for operational milestones, WARNING for unusual situations, SEVERE for critical errors; reduces noise by suppressing debug details during normal operation.
2. **Identify the origin**: loggers typically carry the class or component name, making it easy to locate the event source in a large codebase.
3. **Change configuration without modifying call sites**: administrators can adjust levels, handlers, formatters, or output destinations depending on the library/framework.
4. **Preserve exception details**: a logger can accept a Throwable so the logging system displays the stack trace and root cause.
5. **Support multithreaded and multi-service operations**: context such as a request ID or trace ID helps correlate related events.
6. **Avoid unnecessary work**: logging APIs support level checks and *lazy message evaluation* in certain cases.

Using System.out.println(...) for quick testing in a small exercise is not wrong; however, when you need level classification, filtering, centralized collection, and configurable output, a Logger is more appropriate.

## 3. Logger in the Java Standard Library

The JDK includes the **java.util.logging** system (commonly called **JUL**). Its core classes include:

| Component | Role |
| --- | --- |
| java.util.logging.Logger | The object application code calls to emit logs |
| java.util.logging.Level | Represents severity/detail level |
| java.util.logging.LogRecord | Holds information for a log event such as level, message, timestamp, logger name, exception, and parameters |
| java.util.logging.Handler | Receives a LogRecord and outputs it to a destination |
| java.util.logging.Formatter | Converts a LogRecord into a string representation |
| java.util.logging.Filter | Additional filtering rules when configured |
| java.util.logging.LogManager | Manages JUL loggers and configuration |

In application code, a logger is typically retrieved by class name:

~~~java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOGGER =
            Logger.getLogger(OrderService.class.getName());
}
~~~

This is an **illustrative snippet inside a class**; it has no main method so it does not produce output on its own. A logger tied to a class name makes it easy to configure by package, such as com.example.order, and easy to identify the source when reading logs.

### Why use private static final?

- **private**: each class keeps its own logging entry point.
- **static**: no need to create a new logger for every OrderService instance.
- **final**: prevents accidentally reassigning the LOGGER reference variable.
- **getLogger(OrderService.class.getName())**: names the logger after the fully qualified class name; this is a **useful convention**, not a strict requirement.

A logger can also be retrieved using a functional name such as "com.example.payment" if the project intentionally organizes it that way. A logger name does not have to match a class name, but there should be a consistent convention.

## 4. How Does a Logger Receive and Process an Event?

High-level flow in JUL:

~~~text
Java code: LOGGER.info("...")
            |
            v
         Logger
   (check level/filter)
            |
       if accepted
            v
         LogRecord
            |
            v
      Handler/Filter
   (filter, choose output)
            |
            v
         Formatter
            |
            v
    Console / File / ...
~~~

In JUL, parent logger handlers can also receive records when **forwarding to parent** is enabled. Because of this, a single event can be written to multiple destinations by multiple handlers, or printed multiple times if misconfigured.

Examples of two-tier filtering:

- Logger set to **INFO**, handler set to **FINE**: FINE messages are still blocked by the logger; the handler cannot recover an event already discarded earlier.
- Logger set to **FINE**, handler set to **INFO**: the logger lets FINE pass through, but the INFO handler can discard the FINE event.
- Both logger and handler set to **FINE**: the FINE event can be output, provided no other filter blocks it.

**The logger decides whether an event is emitted into the logging system; the handler decides how to process the received event.** In JUL, a parent logger's level serves for threshold inheritance by child loggers when needed; it does not necessarily re-filter every LogRecord that a child logger has already accepted and forwarded to the parent's handlers.

## 5. Log Levels in JUL

Common levels, ordered from highest severity to finest detail:

| Level | When commonly used |
| --- | --- |
| SEVERE | Critical task failure; functionality cannot continue as expected |
| WARNING | Unusual state, risk, or something needing attention; execution may still continue |
| INFO | Key operational events: startup, completion of an important task |
| CONFIG | Configuration information needed for diagnostics |
| FINE | Details used when troubleshooting |
| FINER | More detailed information about processing steps |
| FINEST | Deepest level of detail for thorough tracing |

**OFF** and **ALL** are primarily used to configure thresholds to disable or allow all events; they should not be treated as everyday business event levels.

A logger with an **INFO** threshold normally allows INFO, WARNING, and SEVERE through while blocking CONFIG, FINE, FINER, and FINEST. A level only reflects logging severity: **emitting SEVERE does not throw an exception or stop the program**; calling WARNING does not automatically recover from an error either.

In other frameworks, you will often see **ERROR, WARN, INFO, DEBUG, TRACE**. You can conceptually relate them to JUL's SEVERE, WARNING, INFO, FINE, FINER/FINEST, but **do not treat these values as the same API or assume identical mapping across all libraries**.

## 6. Runnable Java 17+ Example: Creating, Configuring, and Using a Logger

This example uses **JUL**, requiring no dependencies outside the JDK. It explicitly formats logs and sends them to stdout so you can see the exact result rather than relying on the machine's default logging configuration.

Create the file **LoggerDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggerDemo {
    private static final Logger LOGGER =
            Logger.getLogger(LoggerDemo.class.getName());

    public static void main(String[] args) {
        // Prevent parent logger handlers from printing duplicate records.
        LOGGER.setUseParentHandlers(false);

        // Logger only allows INFO and more severe levels.
        LOGGER.setLevel(Level.INFO);

        // Handler outputs to stdout with a simple, deterministic format.
        Handler stdout = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        stdout.setLevel(Level.INFO);
        LOGGER.addHandler(stdout);

        LOGGER.info("Ứng dụng đã khởi động");
        LOGGER.fine("Chi tiết debug sẽ bị lọc");
        LOGGER.log(Level.WARNING,
                "Thiếu cấu hình {0}; dùng giá trị mặc định", "theme");

        // StreamHandler may buffer data before writing.
        stdout.flush();
    }
}
~~~

Compile and run in a terminal supporting UTF-8, with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 LoggerDemo.java
java LoggerDemo
~~~

**Exact stdout** of the program (each line ends with a newline):

~~~text
INFO | Ứng dụng đã khởi động
WARNING | Thiếu cấu hình theme; dùng giá trị mặc định
~~~

Why are there only two lines?

1. **Logger.getLogger(LoggerDemo.class.getName())** retrieves the logger by class name.
2. **LOGGER.setLevel(Level.INFO)** blocks the LOGGER.fine(...) call, so the debug line does not appear.
3. **stdout.setLevel(Level.INFO)** sets the threshold for the corresponding handler.
4. **setUseParentHandlers(false)** prevents the parent logger from also outputting the record via another handler. Without this line, the system's default configuration might print the message again to stderr.
5. **Formatter.format(...)** determines the output string consisting of the level, separator, and message; timestamp and class name are omitted so the output is easy to verify.
6. With **JUL**, parameter placeholders typically use **{0}**, **{1}** according to JUL's message formatting rules; the example above turns {0} into theme.
7. **StreamHandler.flush()** requests writing any buffered data; StreamHandler with System.out is used in the example to show output without needing to close System.out.

**Note:** this explicitly configures a logger for an exercise. Real-world applications typically use centralized logging configuration, allowing levels and output destinations to vary by environment instead of creating handlers inside business methods.

## 7. How Do Logger, Handler, and Formatter Differ?

Consider these three statements:

- **Logger:** “There is a WARNING event: missing theme configuration”.
- **Handler:** “Send this event to the console or a file”.
- **Formatter:** “Render it as WARNING | Missing theme configuration; using default value”.

A logger can have multiple handlers attached, and handlers can target different destinations. For example, the console might only receive INFO and above, while a diagnostic file receives FINE and above. In that case, the logger threshold must be set low enough so FINE is not discarded before the handler processes it.

### Where does ConsoleHandler write by default?

In JUL, **ConsoleHandler writes to stderr by default**, unlike System.out.println(...) which writes to stdout. Because stdout and stderr are two separate streams, their display order when interleaved in a terminal or pipeline can be confusing. The runnable example above uses **StreamHandler(System.out, ...)** to explicitly write to stdout.

In container environments or centralized collection systems, both stdout and stderr can be collected depending on infrastructure configuration; do not assume logs will automatically end up in a file.

### Why does a log line sometimes appear twice?

A typical cause is attaching a dedicated handler to a child logger while still leaving forwarding to the parent logger's handlers enabled. Ways to handle this include organizing handlers at an appropriate common level, or only disabling forwarding when you truly want to isolate a logger. Do not add/create a new handler every time a business method is called: that easily causes duplicate output, resource leaks, and hard-to-manage configuration.

## 8. When Should You Write LOGGER.info, warning, severe, or fine?

Consider the **impact of the event on operators**, rather than relying solely on the type of statement being executed:

~~~java
LOGGER.info("Dịch vụ đã sẵn sàng nhận yêu cầu");
LOGGER.warning("Không truy cập được cache; chuyển sang nguồn dữ liệu chính");
LOGGER.severe("Không thể khởi tạo kết nối bắt buộc");
LOGGER.fine("Đã chọn nhánh xử lý dự phòng");
~~~

These are **illustrative statements**, not a standalone program. They will only be output if the logger, handler, and filters allow them.

Some guidelines for choosing levels:

- **INFO**: states/milestones that help understand what the application is doing. Do not turn INFO into a step-by-step log for every loop iteration.
- **WARNING**: something unusual that needs monitoring, while the system can still handle it or recover.
- **SEVERE**: an error with real impact, a failed operation, or a feature no longer working properly.
- **FINE/FINER/FINEST**: details for debugging; can be enabled selectively during investigations.

There is no rule saying “every caught exception must be SEVERE”. For example, invalid input data where the application returns a valid error response may not be a critical infrastructure incident. The log level should reflect event semantics and project conventions.

## 9. A Logger Can Record Exception Stack Traces

Logging only a message like "An error occurred" is usually not enough to find the root cause. JUL lets you pass a **Throwable** directly so an appropriate handler/formatter can render the stack trace.

The following snippet illustrates usage inside a class that has a LOGGER field:

~~~java
try {
    int amount = Integer.parseInt("abc");
    LOGGER.info("Đã đọc số tiền: " + amount);
} catch (NumberFormatException ex) {
    LOGGER.log(Level.WARNING, "Không thể chuyển dữ liệu sang số", ex);
}
~~~

This is an **illustrative code snippet**, not a standalone program with deterministic stdout. The actual stack trace depends on line numbers and the formatter in use. In the LoggerDemo example in section 6, the formatter only returns the level and message, so it **does not automatically display the stack trace** if you reuse that minimal formatter. To display a Throwable, use a formatter that supports it or add appropriate handling for record.getThrown().

When catching an exception, decide whether you can handle it. Avoid having multiple layers log the same throwable and rethrow it, which leads to duplicate error lines; at the same time, do not swallow an exception just because you logged it.

## 10. Optimizing Message Construction Cost

Even when the FINE level is disabled, Java code still evaluates method arguments before calling the method. Therefore:

~~~java
LOGGER.fine("Chi tiết: " + createExpensiveDebugDescription());
~~~

This may **still call createExpensiveDebugDescription()** even when the logger ignores FINE. This is only an illustrative snippet: that method would need to be defined in a real program.

A better approach is to use **Supplier<String>**, which JUL supports:

~~~java
LOGGER.log(Level.FINE,
        () -> "Chi tiết: " + createExpensiveDebugDescription());
~~~

When the level is not accepted by the logger, the supplier does not need to be executed to build the message. You can also check explicitly if generating debug data is expensive:

~~~java
if (LOGGER.isLoggable(Level.FINE)) {
    LOGGER.fine(createExpensiveDebugDescription());
}
~~~

Keep in mind that a downstream handler or filter can still discard the log; **isLoggable(...) reflects the threshold and filter at the logger**, and does not guarantee the event will be saved at the final destination.

Do not put required side-effecting operations inside a log supplier. If the level is disabled, the supplier will not execute and business logic may not run as expected.

## 11. Logger in Multithreaded or Multi-Service Systems

A static logger is typically shared across many threads. Code should include **enough context to trace the event** rather than creating a new logger for each request.

Example of structured messages using key=value pairs:

~~~text
INFO service=order-api requestId=req-23 action=create-order result=success durationMs=41
WARNING service=order-api requestId=req-24 action=create-order result=retry cause=timeout
~~~

These are **illustrative messages**. In real logging systems, context can be placed in records, JSON fields, the library's MDC, or a framework context mechanism. **java.util.logging.Logger does not inherently have an MDC API equivalent to every framework**; how request IDs are propagated across threads/async tasks must follow the chosen tool.

Multithreaded logging can produce interleaved output. Timestamps and correlation/trace IDs help with investigation, but you should not assume the order of log lines collected from multiple machines reflects every happens-before relationship.

## 12. Logger in JUL, SLF4J, Logback, and Log4j 2

The term **Logger** also appears in many Java libraries. They share the same purpose as the entry point for emitting logs, but differ in API and how they connect to the processing pipeline.

| Component | What role does Logger play? |
| --- | --- |
| **java.util.logging (JUL)** | Logger is a JDK API, paired with JUL's LogManager and Handler/Formatter |
| **SLF4J** | Logger is a facade interface for the application; an appropriate provider/backend performs the actual writing |
| **Logback** | A logging system commonly used as a backend for SLF4J, providing loggers, appenders, and encoders |
| **Log4j 2** | Has its own logger API and execution/configuration components; can integrate with SLF4J with proper configuration |

Illustrative **SLF4J** example:

~~~java
// Requires SLF4J dependency and an appropriate provider.
// This is not a standalone Java program using only the JDK.
private static final org.slf4j.Logger LOG =
        org.slf4j.LoggerFactory.getLogger(MyService.class);

LOG.info("Đã xử lý đơn hàng {}", orderId);
~~~

With **SLF4J**, the common placeholder is **{}**. With parameterized formatting calls in **JUL** in section 6, **{0}** is used. Avoid copying logging syntax from one framework to another without checking the API.

In a project that has chosen a logging framework, prefer **the same way of obtaining a Logger and the same configuration system**. Do not install multiple overlapping providers/backends or bridges without careful control, as that can cause duplicate logs, wrong levels, or forwarding loops.

## 13. Rules for Safe and Maintainable Logger Usage

1. **Keep Loggers per class/component and use stable names**. In multi-module applications, organized logger names enable package-level configuration.
2. **Log meaningful events**: describe the action, outcome, and necessary context; prefer stable request IDs or error codes when available.
3. **Never put secrets in logs**: passwords, access tokens, API keys, session cookies, card numbers, or sensitive personal data should not be output in raw form. Do not log entire request/response bodies by default.
4. **Do not use logging as control flow**: logging SEVERE does not replace exception handling; the application must still handle the error, return an error response, or stop according to proper logic.
5. **Do not over-log**: large loops or every successful event under high traffic can cause heavy I/O and storage costs. Use metrics when you need counts or rates.
6. **Do not rely on log durability**: logs can be lost when buffers are not flushed, outputs fail, or the receiving system is overloaded. Critical business events that must be reliably persisted require a dedicated mechanism.
7. **Actively decide levels and handlers**: both filtering layers must be configured appropriately if you want to see details.
8. **Have retention and access control policies**: logs are for diagnostics, but they are also data that must be protected.

## 14. Common Mistakes When Using a Logger

| Mistake | Symptom | How to avoid |
| --- | --- | --- |
| Setting logger to FINE while handler stays INFO | FINE logs are not visible | Adjust thresholds appropriately on **both** the logger and the handler |
| Child logger has its own handler while still forwarding to parent | Same event appears multiple times | Check where handlers are attached and useParentHandlers |
| Creating a handler on every request | Duplicate logs, resource leaks, hard to manage | Configure logging once at initialization |
| Logging DEBUG/FINE everywhere in production | Excessive data and cost | Enable detailed logging selectively |
| Calling LOGGER.info with sensitive data | Information leakage via logs | Remove, mask, or reduce data granularity |
| Logging only ex.getMessage() | Missing stack trace/root cause | Pass the Throwable to the logging API when needed |
| Confusing LOGGER.severe with throw | Log appears but program keeps running | Handle errors with appropriate control flow |
| Confusing JUL {0} with SLF4J {} | Message is not formatted as expected | Use the correct API and parameter syntax |
| Not flushing StreamHandler in short examples | Program finishes without expected output | Flush when needed; real environments use appropriate buffer policies |

## 15. Self-Check Questions

**Question 1. Is a Logger the log file itself?**

No. A Logger is the object/API that emits events; the Handler/Appender and output destination determine where data is sent or stored.

**Question 2. Will a Logger at INFO output LOGGER.fine(...)?**

Normally no, because FINE is lower than the INFO threshold. Raising the handler's level will not output an event that was already discarded by the logger.

**Question 3. Why might a LOGGER.warning(...) call appear twice?**

A common cause is that the child logger has its own handler while also forwarding records to the parent's handlers. Check the handler configuration and the useParentHandlers property.

**Question 4. Why should you pass the exception to LOGGER.log(..., ex) when investigating errors?**

So the logging system can preserve the stack trace and cause chain; ex.getMessage() alone is often not enough. The formatter must support outputting throwables for that information to appear in the output log.

**Question 5. Should you use Logger or System.out.println for a Java project?**

Logger is usually the right choice because it provides levels, origin tracking, and configurable output. System.out.println can still be useful for very small programs or console examples, but it does not fully replace an application's logging mechanism.

**Remember:** **A Logger is the emission point for event records from Java code.** For events to appear in the right place at the right level, understand **Logger → Level/Filter → Handler/Appender → Formatter → Destination**, along with naming conventions, exception management, and protecting sensitive data.

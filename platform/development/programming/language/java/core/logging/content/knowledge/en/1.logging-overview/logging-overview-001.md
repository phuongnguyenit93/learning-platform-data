# What Is Logging? — Java Logging Overview

## 1. Concept

**Logging** is the practice where a program generates and records events that occur at runtime, in the form of contextual messages that humans or observability systems can inspect later. An event can be an application startup, a handled request, a missing configuration, a slow connection, or a thrown exception.

A log record typically carries the following information:

- **Timestamp** when the event occurred, with an explicit time zone.
- **Severity level**: INFO, WARN, ERROR… depending on the logging system.
- **Source**: application name, class, or logger, sometimes including the thread.
- **Message and context**: action, request/order ID, processing duration, result.
- **Error cause**: exception type and stack trace when needed for diagnosis.

Illustrative example (actual format depends on configuration):

~~~text
2026-11-09T10:00:00Z INFO  order-service orderId=ORD-42 Order created
2026-11-09T10:00:02Z WARN  order-service orderId=ORD-42 Inventory service responded slowly
~~~

Logging answers questions such as “what happened?”, “when did it happen?”, “at which step?”, and “why did it fail?”. Logs are operational observability data, not core business functionality.

## 2. How Does Logging Help?

1. **Error diagnosis:** trace the events leading up to a failure, preserving exceptions and the context needed to reproduce the issue.
2. **Operational monitoring:** know when the application started, which services it called, and which tasks succeeded or failed.
3. **Finding performance issues:** record processing step durations and signs of timeouts or unusual slowness; for continuous quantitative analysis, you still need metrics.
4. **Investigating distributed incidents:** correlate related logs using a request ID, trace ID, or correlation ID.
5. **Supporting behavior verification:** confirm that a particular execution branch actually ran in environments where attaching a debugger is difficult.

Logging differs from several related tools:

| Tool | Primarily used to | Key point to remember |
| --- | --- | --- |
| Logging | Store **discrete events** with context | Requires configuring log levels, output destinations, and retention |
| Debugger | Pause the program, inspect variables, and step through execution | Suitable during development; hard to use directly on every production incident |
| Metrics | Measure counts, rates, and distributions over time | For example: requests/second, error rate, p95 latency |
| Tracing | Follow the path of a request across multiple components | Span/trace IDs help link with logs |
| Audit trail | Record evidence of critical actions that require traceability | May require stricter integrity guarantees, access control, and retention periods than technical logs |

Printing a line with **System.out.println** can help with quick observation, but it usually lacks levels, source information, and centralized filtering or configuration. In real-world applications, use a logging API.

## 3. How Does Logging Work?

Common processing flow in Java:

~~~text
Application code
   → Logger (creates event, evaluates level/filter)
   → LogRecord or logging event
   → Handler/Appender (evaluates level/filter, selects destination)
   → Formatter/Encoder (formats into text or JSON)
   → Console, file, log collection service…
~~~

- **Logger** is the code-level object used to emit events; it is usually named after a class or component.
- **Level** determines which messages are important enough to process. Events can be filtered out at both the logger and the handler/appender.
- **Handler** (terminology in `java.util.logging`, abbreviated **JUL**) or **appender** (common terminology in Logback/Log4j) determines where logs are sent.
- **Formatter/encoder** determines how logs are represented, such as timestamp + level + message or JSON.
- **Output destination** can be the console, a file, or a centralized system. An event is only truly persisted at the destination when the write/forwarding operation succeeds; logging does not guarantee durable storage on its own.

In multi-threaded applications, events may interleave. The order of log lines at a collection target is not always the global order of all operations. That is why timestamps, threads, and correlation IDs are very useful.

## 4. Log Levels and How to Choose Them

Java provides **java.util.logging** built into the JDK. Common JUL levels, in decreasing order of severity, include:

| JUL level | Common meaning |
| --- | --- |
| SEVERE | Serious failure; an operation or component has failed |
| WARNING | Anomalous condition with potential risk, but execution can continue or recover |
| INFO | Noteworthy operational milestone |
| CONFIG | Configuration information useful for diagnosis |
| FINE | Standard debug details |
| FINER, FINEST | Increasingly detailed information for analyzing execution flow |

**OFF** and **ALL** are mainly used to configure filter thresholds, not as event levels to emit regularly in application logic. In many other libraries, common names are **ERROR → WARN → INFO → DEBUG → TRACE**. You can roughly relate ERROR to SEVERE, WARN to WARNING, and DEBUG to FINE; they are not a single uniform level system across all libraries.

Examples of choosing levels:

- **INFO:** “Application is ready to accept requests”; “Completed syncing 120 records”.
- **WARNING:** “External service responded slowly, retrying”.
- **SEVERE:** “Unable to connect to database, initialization failed”.
- **FINE:** “Selected fallback processing branch with state X”.

An INFO threshold normally allows INFO, WARNING, and SEVERE, while blocking FINE/FINER/FINEST. **A level describes the importance of an event; it does not fix errors or control program flow by itself.**

## 5. Runnable Java 17+ Example: java.util.logging

JUL is built into the JDK and requires no external libraries. The example below explicitly configures a handler so the output is easy to verify.

Create the file **LoggingDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class LoggingDemo {
    private static final Logger LOGGER =
            Logger.getLogger(LoggingDemo.class.getName());

    public static void main(String[] args) {
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.INFO);

        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        output.setLevel(Level.INFO);
        LOGGER.addHandler(output);

        LOGGER.info("Ứng dụng đã khởi động");
        LOGGER.log(Level.INFO, "Đã xử lý {0} bản ghi", 3);
        LOGGER.warning("Thiếu cấu hình tùy chọn");
        LOGGER.fine("Chi tiết chỉ dành cho debug");

        output.flush();
    }
}
~~~

Compile and run with JDK 17 or later in a terminal that supports UTF-8:

~~~bash
javac -encoding UTF-8 LoggingDemo.java
java LoggingDemo
~~~

Exact **stdout** output of this program (each line ends with a newline):

~~~text
INFO | Ứng dụng đã khởi động
INFO | Đã xử lý 3 bản ghi
WARNING | Thiếu cấu hình tùy chọn
~~~

Explanation:

1. **Logger.getLogger(...)** retrieves a logger named after the class. **setUseParentHandlers(false)** prevents forwarding to the parent logger's handlers, avoiding duplicate log output in this example.
2. **LOGGER.setLevel(Level.INFO)** and **output.setLevel(Level.INFO)** set the threshold on both the logger and the handler. Therefore, the **fine(...)** call is not emitted.
3. **StreamHandler(System.out, ...)** sends logs to stdout. The **Formatter** is customized to print only the level and message; in production, you should include a timestamp, source, and context.
4. **LOGGER.log(Level.INFO, "Đã xử lý {0} bản ghi", 3)** uses the **{0}** placeholder following JUL's formatting style. The **{}** placeholder is common in SLF4J and will not be substituted the same way in this JUL call.
5. **output.flush()** flushes data buffered by `StreamHandler` to stdout. JUL's default `ConsoleHandler` normally writes to stderr; the two handlers have different characteristics.

In real applications, configuration is usually centralized (configuration files, environment variables, or framework configuration) rather than creating handlers on every request.

## 6. Logging Exceptions Properly

When you need to know **why** an operation failed, log the exception object so the logging system preserves the stack trace and cause chain. For example, the following snippet can be placed inside a method using the logger above:

~~~java
try {
    Integer.parseInt("khong-phai-so");
} catch (NumberFormatException ex) {
    LOGGER.log(Level.WARNING, "Giá trị số đầu vào không hợp lệ", ex);
}
~~~

This is an **illustrative snippet**, not a standalone program; the stack trace and line numbers depend on where you place it. Logging only the exception message often loses the context needed for diagnosis.

A useful rule of thumb is to **log an error where there is enough context to decide how to handle it**. If one layer logs an exception and rethrows it, and an upper layer logs the same error again, you may end up with multiple duplicate records for a single incident. Avoid catching an exception, logging it, and silently swallowing it if business logic needs to know that the operation failed.

## 7. Choosing Valuable Log Content

A good log entry usually answers: **what event occurred, which entity it involved, what the outcome was, and how long it took**. When a request/trace ID is available, record it consistently to link steps together, for example:

~~~text
INFO order-service requestId=req-17 orderId=ORD-42 action=create result=success durationMs=28
~~~

Specific fields depend on the application; the illustration above is not the output of the Java program in section 5. For multi-service systems, structured log formats (such as JSON) make searching and filtering by field much more accurate than concatenating free-form text.

Only include information in logs that genuinely helps with diagnosis. **Do not log passwords, access tokens, API keys, card numbers, session cookies, or sensitive personal data in raw form.** If an identifier is strictly required, prefer internal IDs, truncated values, or masked sensitive parts according to system policy. Do not log full HTTP request/response bodies by default.

## 8. Performance and Operations

- **Avoid logging too densely inside loops:** millions of INFO lines can cause heavy I/O and storage costs and make important events hard to find. Use counters/metrics to measure high-frequency occurrences.
- **Avoid building expensive messages when the level is disabled:** JUL supports suppliers, such as **LOGGER.log(Level.FINE, () -> "Đang xử lý: " + soBanGhi)** if the variable **soBanGhi** exists and is effectively final. The supplier is not evaluated when the logger discards that level.
- **Set thresholds appropriate for the environment:** typically INFO for normal operation; enable FINE/DEBUG within a narrow scope and controlled time window when investigating incidents.
- **Manage storage size and retention:** configure rotation, size limits, retention policies, and access permissions. Containers typically write to stdout/stderr for infrastructure log collectors.
- **Account for log loss:** buffering, overload, or failures in the receiving system can prevent logs from reaching their destination. Do not rely on a single regular log line as the sole proof of a critical transaction.
- **Keep formatting consistent:** use timestamps with an explicit time zone (usually UTC), level, service, correlation ID, and stable event codes where appropriate.

## 9. How Do JUL, SLF4J, Logback, and Log4j 2 Differ?

| Component | Role |
| --- | --- |
| **java.util.logging (JUL)** | Logging API and implementation built into the JDK; usable directly without external dependencies |
| **SLF4J** | Unified facade/API for application code to call logging; requires a suitable provider/backend to actually output logs |
| **Logback** | A logging backend commonly used with SLF4J, supporting rich appenders, encoders, and configuration |
| **Log4j 2** | Logging framework with its own API, core, and configuration ecosystem; can integrate with SLF4J with proper configuration |

For Java Core beginners, starting with JUL is enough to understand loggers, levels, handlers, and formatters. In projects using a framework, follow the project's established logging choice and avoid adding overlapping backends or bridges that cause duplicate output or forwarding loops.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Recommended practice |
| --- | --- | --- |
| Using System.out.println everywhere | No severity hierarchy, hard to filter and manage | Use a logger and log levels |
| Emitting every event at INFO/SEVERE | Alert noise, wasted resources | Choose levels based on the true meaning of the event |
| Logging only “Error occurred” | Insufficient information for tracing | Record the action, relevant IDs, and the throwable when needed |
| Logging secret data | Information leakage via console, files, and collection systems | Never log secrets; filter or mask sensitive data |
| Logging and rethrowing across multiple layers | Multiple error lines for a single root cause | Define which layer is responsible for logging |
| Configuring only the logger and forgetting the handler | Expected logs may not appear | Check both logger and handler/appender thresholds |
| Assuming logs are always ordered and kept forever | Incorrect under concurrency, buffering, or rotation | Use timestamps/correlation IDs and proper retention policies |

## 11. Self-Check

**Scenario A:** A program sets both the logger and handler to INFO, then calls `fine(...)`. Will any log be emitted? **No**, because FINE is lower than the INFO threshold.

**Scenario B:** You want to understand why a request failed, but there is only a line saying “Processing error”. What should be improved? **Add** the operation being performed, correlation IDs, and the exception object (when appropriate), while avoiding sensitive data.

**Scenario C:** An application needs a chart of error rate per minute and to see how each request travels across multiple services. Is logging alone enough? **Not optimal**: combine logging with **metrics** to measure rates and **tracing** to follow request paths.

**Remember:** Logging is the mechanism for recording contextual events to observe and diagnose applications. Mastering **logger → level/filter → handler/appender → formatter → destination**, choosing appropriate levels, and protecting sensitive data form the foundation for using logging properly in Java.

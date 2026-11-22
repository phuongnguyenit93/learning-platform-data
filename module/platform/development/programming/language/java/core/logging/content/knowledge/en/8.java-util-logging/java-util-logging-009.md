# Configuring JUL (java.util.logging) in Java

## 1. What is JUL and what does “configuring JUL” mean?

**JUL** stands for **Java Util Logging** — the logging system built into the JDK via the **java.util.logging** package. JUL provides **Logger**, **Level**, **Handler**, **Formatter**, **Filter**, and **LogManager** out of the box, so a Java program can write logs without installing external libraries.

**Configuring JUL** means deciding:

- **Which events are recorded:** setting level thresholds for loggers and handlers, and adding filters if needed.
- **Where logs go:** console, file, or another destination via a Handler.
- **How logs are displayed:** Formatter, encoding, timestamp, logger name, message, and exceptions.
- **Which logger uses which rules:** by logger name or package hierarchy.
- **Log lifecycle:** file size, number of rotated files, access permissions, and configuration loading mechanism.

For example, the same call:

~~~java
LOGGER.fine("Đã chọn nhánh xử lý dự phòng");
~~~

may **produce no output at all** if the threshold is currently INFO; may appear on the console when FINE is enabled; or may go into a debug file without appearing on the console when two handlers have different thresholds.

This is the meaning of **separating application code from operational observability configuration**: the code only describes the event, while the configuration decides how the record is handled.

## 2. Components involved in configuration

Typical flow in JUL:

~~~text
Application code: Logger.info(), fine(), log(...)
                     |
                     v
               Named Logger
        (effective level, Filter)
                     |
              event is accepted
                     v
                 LogRecord
                     |
                     v
       Logger's Handler and possibly
       parent loggers' Handlers
                     |
          (Handler level, Filter)
                     |
                     v
                 Formatter
                     |
                     v
     Console / File / other destinations
~~~

| Component | Role in configuration |
| --- | --- |
| **Logger** | Sets the log source name, level threshold, and filter; may have direct handlers |
| **Level** | Thresholds such as INFO, FINE, WARNING, SEVERE... |
| **Handler** | Receives LogRecord and outputs to a destination; a handler also has its own level/filter |
| **ConsoleHandler** | Writes to **stderr** by default in JUL |
| **FileHandler** | Writes to a file, with optional size limits and file rotation |
| **Formatter** | Turns a LogRecord into text, such as SimpleFormatter or XMLFormatter |
| **Filter** | A rule deciding whether to accept a record beyond the level condition |
| **LogManager** | Manages the list of loggers and JUL configuration; reads configuration from a file or via API |

**A Logger is not a log file.** A logger can emit events to multiple handlers, or have no matching receiving handler and output nothing at all. A successful call on a logger also does not by itself guarantee that the data has been durably stored in a remote collection system.

### Logger name hierarchy and the root logger

A logger named **com.example.order.OrderService** can typically inherit its threshold from parent loggers **com.example.order**, **com.example**, **com**, and finally the **root logger** (empty name). A logger with a level of **null** means it uses the inherited effective threshold; **Logger.getLevel() returning null does not mean logging is disabled**.

In JUL, the **root logger** has the name **""** (empty string); properties in the configuration file starting with a dot such as **.level = INFO** set the level for the root.

Handlers attached to parent loggers can also receive LogRecords forwarded from child loggers. The **useParentHandlers** property controls that forwarding.

## 3. Two common ways to configure JUL

There are two main approaches:

1. **Via a logging.properties file:** convenient when you want to change levels, handlers, and formatters per environment without modifying Java code. Specify the file using the JVM system property **java.util.logging.config.file**.
2. **Via Java code:** call **Logger.setLevel**, **Handler.setLevel**, **Logger.addHandler**, **Handler.setFormatter**, **Logger.setUseParentHandlers** to configure directly.

They can be combined in certain controlled scenarios, but you should clearly establish **who owns the configuration**. If a framework or library has already set up logging, adding handlers in multiple places yourself can cause duplicate logs or alter another component's configuration.

It is also important to distinguish:

- **JVM system property**: e.g., **-Djava.util.logging.config.file=...**, which tells JUL where to load configuration from.
- **Property inside logging.properties**: e.g., **.level = INFO**, **handlers = ...**, which defines specific logging rules.
- **Environment variable**: JUL does not automatically understand a variable like LOG_LEVEL=DEBUG just because it exists; the application or framework must actively map it to JUL configuration.

## 4. Configuring with logging.properties: runnable Java 17+ example

This is the easiest way to learn because you can edit the configuration file and re-run the same program to see the effect.

### 4.1. Create the Java file

Create **JulConfigDemo.java** in your practice directory:

~~~java
import java.util.logging.Logger;

public class JulConfigDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.orders");

    public static void main(String[] args) {
        LOGGER.fine("Đã chọn chiến lược xử lý=standard");
        LOGGER.info("Dịch vụ đơn hàng sẵn sàng");
        LOGGER.warning("Sử dụng cấu hình dự phòng");
    }
}
~~~

The logger name is fixed as **demo.orders** to illustrate name-based configuration. In real projects, a class-based name such as **Logger.getLogger(JulConfigDemo.class.getName())** is usually a helpful convention.

### 4.2. Create the logging.properties file

Create **logging.properties** in the same directory with the exact contents below:

~~~properties
# Handler attached to the root logger.
handlers = java.util.logging.ConsoleHandler

# Root accepts INFO and above by default.
.level = INFO

# Dedicated logger for order operations also accepts FINE.
demo.orders.level = FINE

# The console handler also needs to accept FINE.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding = UTF-8

# Fixed format so the example does not depend on date/time.
java.util.logging.SimpleFormatter.format = %4$s | %5$s%6$s%n
~~~

Explanation of each setting:

- **handlers = java.util.logging.ConsoleHandler**: declares the handler of the root logger; child loggers normally forward records to this handler unless forwarding is disabled.
- **.level = INFO**: sets the threshold for root. If a child logger has no explicit level, it usually inherits this threshold.
- **demo.orders.level = FINE**: the **demo.orders** logger accepts events from FINE and above, including FINE, INFO, WARNING, SEVERE.
- **java.util.logging.ConsoleHandler.level = FINE**: allows the console handler to accept FINE. If the handler is set to INFO, a FINE record already accepted by the logger can still be blocked at the handler.
- **java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter**: uses the built-in text formatter in the JDK.
- **java.util.logging.ConsoleHandler.encoding = UTF-8**: specifies the encoding so non-ASCII characters (such as Vietnamese) display properly when the receiving environment supports it.
- **java.util.logging.SimpleFormatter.format**: customizes the display string. In SimpleFormatter, **%4$s** is the level, **%5$s** is the formatted message, **%6$s** is the exception part, and **%n** is the platform-specific newline.

**Note on parent level:** once a FINE record from the **demo.orders** logger has been accepted and forwarded to the root handler, **the root's INFO threshold is not re-applied as a second filter to that LogRecord**; the **handler's** threshold is what matters at the output destination. Therefore, the configuration above allows FINE to be seen even though root is set to INFO.

### 4.3. Compile and run

Using **JDK 17 or later**, in the directory containing both files:

~~~bash
javac -encoding UTF-8 JulConfigDemo.java
java -Djava.util.logging.config.file=logging.properties JulConfigDemo
~~~

**Exact stderr** of the program when run with the exact files above:

~~~text
FINE | Đã chọn chiến lược xử lý=standard
INFO | Dịch vụ đơn hàng sẵn sàng
WARNING | Sử dụng cấu hình dự phòng
~~~

**Stdout is empty**, because **JUL's ConsoleHandler writes to stderr by default**. If your terminal merges both streams, you will still see the log lines above. Each line ends with the operating system's newline character.

The **-Djava.util.logging.config.file=...** parameter is a **JVM option** and must be placed **before the main class name**. It must be provided at JVM startup so LogManager reads the right configuration when the logging system is first initialized.

If the filename or path contains spaces, quote the argument appropriately for your shell, for example:

~~~bash
java "-Djava.util.logging.config.file=conf/logging dev.properties" JulConfigDemo
~~~

The command with spaces only illustrates how to quote: the target file must actually exist.

### 4.4. Try changing the level

Change the line:

~~~properties
demo.orders.level = FINE
~~~

to:

~~~properties
demo.orders.level = INFO
~~~

and run the program again. Then, under the same configuration and conditions as the example, the **FINE** line is no longer emitted; the remaining two lines still appear:

~~~text
INFO | Dịch vụ đơn hàng sẵn sàng
WARNING | Sử dụng cấu hình dự phòng
~~~

You have changed observability without modifying Java code. If you only change **ConsoleHandler.level = INFO** while keeping the logger at FINE, the result also has no FINE line because the handler drops it.

## 5. Distinguishing Logger threshold and Handler threshold

Whether an event appears depends on **both the emitter and the receiver**.

Assuming the logger has no additional filter and has only one handler:

| Logger level | Handler level | Calling fine(...) | Calling info(...) | Calling warning(...) |
| --- | --- | --- | --- | --- |
| INFO | INFO | Not output | May output | May output |
| FINE | INFO | Not output at handler | May output | May output |
| INFO | FINE | Not emitted from logger | May output | May output |
| FINE | FINE | May output | May output | May output |
| OFF | ALL | Not emitted | Not emitted | Not emitted |

“**May output**” means it still depends on filters, handler state, forwarding configuration, and the final destination. **ALL** and **OFF** are typically threshold values used to allow everything or disable logging, rather than everyday business event levels.

JUL levels from highest severity to lowest detail are:

~~~text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
~~~

Libraries such as SLF4J/Logback commonly have ERROR, WARN, INFO, DEBUG, TRACE. **JUL does not have Level.DEBUG or Level.ERROR**; when using plain JUL, the closest equivalents are FINE and SEVERE. This is an analogy in intended usage, not an exact mapping across all frameworks.

## 6. Writing to a file with FileHandler

For applications that want to store logs locally, JUL provides **java.util.logging.FileHandler**. You can attach both console and file handlers to the root logger.

Example **logging.properties** file for development/testing:

~~~properties
handlers = java.util.logging.ConsoleHandler, java.util.logging.FileHandler

.level = INFO
demo.orders.level = FINE

java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.ConsoleHandler.encoding = UTF-8

java.util.logging.FileHandler.level = FINE
java.util.logging.FileHandler.pattern = logs/app-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.encoding = UTF-8
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter

java.util.logging.SimpleFormatter.format = %4$s | %5$s%6$s%n
~~~

With this configuration:

- **ConsoleHandler** only outputs INFO, WARNING, SEVERE, and levels more severe than INFO.
- **FileHandler** has a FINE threshold, so it can also record FINE details from **demo.orders**.
- **pattern = logs/app-%g.log** sets the path pattern; **%g** represents the file generation number in the rotation cycle.
- **limit = 1048576** sets the size limit per file (approximately 1 MiB); when reached, FileHandler can rotate to the next file.
- **count = 3** sets the number of files in the rotation set.
- **append = true** requests appending data to an existing file when appropriate for rotation/locking state; it does not guarantee that every startup will append strictly to a fixed path.
- Handlers can choose their own formatters; this example uses the same SimpleFormatter for easy comparison.

**Important:** the **logs** directory must exist and the process must have write permission; FileHandler is not a mechanism guaranteed to create all parent directories. Before running on Linux/macOS, you can create the directory with:

~~~bash
mkdir -p logs
~~~

On PowerShell, you can create the directory if it does not exist:

~~~powershell
New-Item -ItemType Directory -Force -Path logs
~~~

Files are created according to the pattern and may have an extra suffix to avoid collisions between FileHandlers/processes. **Do not assume the actual filename will always be app-0.log** on every run or configuration. FileHandler uses a file-locking mechanism; multiple instances writing to the same path must be designed carefully.

Some common pattern tokens:

| Token | Meaning |
| --- | --- |
| **%g** | Generation number of the file in rotation |
| **%u** | Unique number to resolve certain file/lock conflicts |
| **%t** | System temporary directory |
| **%h** | User's home directory |
| **%%** | A literal percent sign |

In containerized environments, operational guidelines usually prefer writing to the console and letting infrastructure handle log collection, rotation, and storage. Writing to both console and file can be appropriate, but it increases cost and requires a clear retention policy.

## 7. Customizing log format with SimpleFormatter

SimpleFormatter supports format strings following **java.util.Formatter** with defined arguments. For example:

~~~properties
java.util.logging.SimpleFormatter.format = %1$tFT%1$tTZ %4$s %3$s - %5$s%6$s%n
~~~

The idea of this pattern is to print the timestamp, level, logger name, message, and exception part. The specific syntax is based on **SimpleFormatter**'s formatting conventions, not the **{0}** placeholders used in log messages.

Arguments:

| Position | Content in SimpleFormatter |
| --- | --- |
| **%1$** | Date/time from the record; supports date/time conversions such as tF and tT |
| **%2$s** | Log source, as determined by JUL |
| **%3$s** | Logger name |
| **%4$s** | Log level |
| **%5$s** | Formatted message |
| **%6$s** | Exception/stack trace string if present |

**Time zone note:** timestamp display depends on the formatter and the environment's time zone; if you need UTC and strict formatting to aggregate logs from multiple machines, configure/implement an appropriate encoder and verify the output in the real system. Do not assume any arbitrary date/time pattern guarantees UTC.

### Logging exceptions to get a stack trace

With JUL, you should pass the **Throwable** when an error needs diagnosis:

~~~java
try {
    Integer.parseInt("invalid-number");
} catch (NumberFormatException ex) {
    LOGGER.log(java.util.logging.Level.WARNING,
            "event=validation.failed field=count", ex);
}
~~~

This is an **illustrative snippet** that requires a LOGGER variable in the enclosing class, not a standalone runnable program. **LOGGER.log(Level, message, ex)** preserves the exception in the LogRecord. Standard SimpleFormatter can display the stack trace via the exception argument; a custom formatter that only prints the message will **not automatically print the stack trace** if it does not handle record.getThrown().

Avoid logging only ex.getMessage() and losing the root cause. At the same time, do not log the same Throwable across multiple layers if it only leads to duplicate stack traces; decide on clear logging responsibility boundaries.

## 8. Configuring JUL in Java code

When you need to set up a dedicated logger in an example, tool, or small application, you can use the API instead of a properties file.

Create **ProgrammaticJulDemo.java**:

~~~java
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public class ProgrammaticJulDemo {
    private static final Logger LOGGER =
            Logger.getLogger("demo.runtime");

    public static void main(String[] args) {
        // This logger only uses handlers attached directly to it.
        LOGGER.setUseParentHandlers(false);
        LOGGER.setLevel(Level.FINE);

        // Use stdout instead of stderr to demonstrate clear output.
        Handler output = new StreamHandler(System.out, new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        output.setLevel(Level.FINE);
        LOGGER.addHandler(output);

        LOGGER.fine("event=order.validate outcome=passed");
        LOGGER.info("event=order.created outcome=success");

        // StreamHandler is buffered.
        output.flush();
    }
}
~~~

Compile and run using only JDK 17+:

~~~bash
javac -encoding UTF-8 ProgrammaticJulDemo.java
java ProgrammaticJulDemo
~~~

**Exact stdout**:

~~~text
FINE | event=order.validate outcome=passed
INFO | event=order.created outcome=success
~~~

Explanation:

1. **Logger.getLogger("demo.runtime")** retrieves the logger by name.
2. **setUseParentHandlers(false)** prevents forwarding records to parent loggers' handlers; avoids duplicate lines or different formatting in the example.
3. **setLevel(Level.FINE)** lets the logger accept FINE.
4. **output.setLevel(Level.FINE)** lets the handler accept FINE as well.
5. **StreamHandler(System.out, Formatter)** writes logs to stdout, unlike ConsoleHandler which defaults to stderr.
6. **output.flush()** flushes the buffered data to stdout so the short program exits with complete output.

This example intentionally creates the handler once. In real applications, do not create and attach a handler on every request or every object instantiation; doing so can cause duplicate records, increased resource usage, and cleanup difficulties.

### Configuring a logger directly by class

Common convention:

~~~java
private static final java.util.logging.Logger LOGGER =
        java.util.logging.Logger.getLogger(MyService.class.getName());
~~~

This is an **illustrative snippet** inside the MyService class. Logger names can be configured by class/package in logging.properties. Using the class name is not mandatory, but name stability helps with grouping and selecting levels.

## 9. Parent–child relationship and useParentHandlers

A Logger can have handlers attached directly to it and also forward records up to its parent's handlers. By default, JUL typically allows forwarding to parent loggers' handlers.

Illustrative example (not a standalone program):

~~~java
java.util.logging.Logger logger =
        java.util.logging.Logger.getLogger("com.example.payment");

logger.setUseParentHandlers(false);
logger.addHandler(customHandler);
~~~

This snippet assumes **customHandler** has already been created. When **useParentHandlers=false**, only matching handlers attached directly to the logger in question receive records from it; the root handler does not receive them via this forwarding path.

Things to remember:

- If you disable parent handlers but **forget to attach a handler**, records may not reach the expected destination.
- If you both attach a handler to a child logger and use the root handler, a single event may be output **twice**; that does not necessarily mean two separate incidents occurred.
- Do not call **setUseParentHandlers(false)** mechanically in every class: centralized configuration usually **relies on handlers at root** to collect logs across the entire application.
- A logger with level **null** inherits its effective level from its parent; this is **different** from whether handlers are inherited/forwarded.

Typically, the easiest approach to manage is to **attach handlers at root**, let child loggers inherit, and only configure specific log levels per package or component under investigation.

## 10. When does LogManager load configuration?

JUL uses **LogManager** to manage configuration. When the logging system is first initialized, LogManager reads configuration according to the JDK mechanism. The common approach is to specify a file before Java starts:

~~~bash
java -Djava.util.logging.config.file=/path/to/logging.properties JulConfigDemo
~~~

If no custom file is specified, JUL has a JDK default configuration mechanism; the specific contents/paths may vary across distributions and JDK versions. Do not rely on the default output format as a stable contract.

**Common mistake:** calling System.setProperty("java.util.logging.config.file", "...") in main **after a static logger has already been created**. By then LogManager may have already loaded its configuration, so merely changing the system property does not guarantee the configuration is re-read. The simple and reliable approach in examples is **placing -D before the class name at startup**.

### Reloading configuration at runtime

JUL has the **LogManager.readConfiguration(...)** API to re-read configuration, and modern Java versions also provide configuration update mechanisms. However, **re-reading configuration can reset level/handler state or close and replace handlers depending on the API and context**. Do not call it automatically to “refresh” on every request or while multiple libraries are concurrently using JUL.

Conceptual example of loading a file via API (illustrative snippet requiring IOException handling and adherence to the application's runtime policy):

~~~java
try (java.io.InputStream input =
        java.nio.file.Files.newInputStream(
                java.nio.file.Path.of("logging.properties"))) {
    java.util.logging.LogManager.getLogManager()
            .readConfiguration(input);
}
~~~

This snippet is **not a standalone program**. In a running application, configuration changes take effect globally for JUL in the JVM; make sure not to disrupt loggers and handlers managed by other frameworks.

**Do not call LogManager.reset() arbitrarily** just to clean up a single logger: that operation can remove/close handlers and reset the configuration of many loggers across the entire JVM.

## 11. Configuration scope and framework ecosystems

A plain Java application using **java.util.logging** can follow the examples above. However, many projects use **SLF4J**, **Logback**, or **Log4j 2** as their primary logging API/backend.

| System | Typical configuration point |
| --- | --- |
| Plain JUL | logging.properties, java.util.logging.config.file, Logger/Handler/LogManager |
| SLF4J | Facade API; the actual provider/backend decides where configuration is loaded and applied |
| Logback | Backend configuration such as logback.xml, appender, encoder, logger level |
| Log4j 2 | Configured via the Log4j 2 system, with equivalent handlers called appenders |
| Spring Boot | Provides its own logging properties and configuration, depending on the chosen backend |

Do not assume **JUL's logging.properties** will control all logs of an application using Logback or Log4j 2. In systems with a **bridge/adapter**, some records may be routed between APIs, but the direction and behavior depend on the actual setup.

If your application uses a framework that already manages logging, follow the **project's unified configuration source**. Mixing too many backends, providers, or bridges can cause duplicate logs, lost logs, or forwarding loops.

## 12. Customizing Formatter and Filter

When SimpleFormatter is not enough, you can subclass **java.util.logging.Formatter** to create a suitable format:

~~~java
// Illustrative snippet in a class that already has Handler handler.
handler.setFormatter(new java.util.logging.Formatter() {
    @Override
    public String format(java.util.logging.LogRecord record) {
        return record.getLevel().getName() + " "
                + formatMessage(record)
                + System.lineSeparator();
    }
});
~~~

This snippet prints the log level and message, but **does not print exception stack traces** because it does not access **record.getThrown()**. In real applications, a formatter should include a timestamp with an explicit time zone, logger name, event code, correlation ID, and Throwable when needed.

Filter lets you add conditions beyond the level:

~~~java
// Illustrative snippet: handler has already been created.
handler.setFilter(record ->
        record.getMessage() != null
                && record.getMessage().startsWith("event="));
~~~

The example above only lets through records whose **message template** starts with event=. It is for learning purposes only: if the message uses placeholders or is structured differently, checking **record.getMessage()** may not be equivalent to searching the formatted string. Do not rely on overly simplistic manual filters for complex production logging.

For structured logs, **do not simply build JSON with String.format without escaping**. Use an appropriate encoder/serializer and control the number of fields, data types, and stack trace preservation. JUL allows writing a custom Formatter, but it does not automatically turn every log into parseable JSON.

## 13. Security and operations when configuring

JUL configuration directly affects cost, risk, and incident investigation capability.

### 13.1. Do not log sensitive data

Do not put **passwords, tokens, API keys, session cookies, private keys, card details, or sensitive personal data** in raw form into messages or stack traces. Enabling FINE/FINER/FINEST can expose data that was not emitted at the INFO threshold.

If a correlation identifier is needed, choose an appropriate correlation ID, mask/encrypt according to policy, and grant appropriate access permissions. Do not log full HTTP request bodies or object.toString() by default for “easier debugging”.

### 13.2. Keep log volume at a useful level

- **INFO:** notable operational milestones.
- **WARNING:** anomalies to monitor where the system can still recover.
- **SEVERE:** critical errors requiring investigation and response.
- **FINE/FINER/FINEST:** details needed for diagnosis, enabled selectively and for controlled durations.

If there are millions of events in a loop, emitting an INFO line for each item can overwhelm files/console. For counts/rates, metrics are usually more appropriate.

### 13.3. Performance and message evaluation

Even when a level is disabled, Java method arguments are still evaluated before the call happens. Illustrative example:

~~~java
LOGGER.fine("state=" + expensiveDescription());
~~~

**expensiveDescription()** is still called to construct the String before the logger knows whether to drop FINE.

JUL supports logging with a supplier to defer evaluation:

~~~java
LOGGER.log(java.util.logging.Level.FINE,
        () -> "state=" + expensiveDescription());
~~~

These are **illustrative snippets**, requiring LOGGER and the expensiveDescription() method in a real class. The supplier may not be executed when the level is filtered out; do not place business logic or required side effects inside the supplier.

### 13.4. Rotation, encoding, and retention

- **FileHandler.limit/count** helps rotate a set of files, but does not fully replace infrastructure-level retention and archiving policies.
- Set a consistent **encoding** (e.g., UTF-8) to prevent non-ASCII characters (such as Vietnamese) from being garbled.
- If running multiple instances, manage each instance's paths and write permissions clearly; do not let processes contend for the same log file.
- For containers, consider writing to stdout/stderr and delegating collection/rotation to the infrastructure.
- Timestamps should have an explicit time zone, typically UTC in distributed systems, and avoid inferring global ordering from log lines across multiple machines.

### 13.5. Do not treat logs as a transactional data store

Handlers may buffer and write asynchronously using different mechanisms; I/O errors or collector overload can prevent records from reaching the final destination. **Calling Logger in your program does not guarantee that every log will persist forever or be successfully stored centrally.** For audit/transactional events with strict preservation requirements, use a more suitable storage mechanism.

## 14. Diagnosing when JUL configuration has no effect

A useful checklist in order:

1. **Is the JVM option right?** The argument must be **-Djava.util.logging.config.file=...** and placed before the class/JAR in the java command.
2. **Does the file actually exist?** Relative paths are resolved against the process working directory, not by default the directory containing the .class or .jar file.
3. **Was the property set early enough?** LogManager may have already initialized before the application changed the property in main.
4. **Do the logger names match?** **demo.orders.level** only targets the logger named demo.orders and matching inheriting loggers; a differently named logger may still follow the root threshold.
5. **What are the logger and handler thresholds?** Both must allow the intended level.
6. **Is there a receiving handler?** Check root **handlers**, direct handlers, and **useParentHandlers**.
7. **Are logs on stdout or stderr?** **ConsoleHandler writes to stderr by default**. A redirect command **> file** usually captures only stdout, so JUL logs may not appear.
8. **Which Formatter is active?** A custom formatter might not print Throwable even when the record carries a Throwable.
9. **Can FileHandler open the file?** Check directory existence, write permissions, file locks, and the pattern path.
10. **Is another framework/bridge interfering?** Projects using Logback/Log4j 2 may not use JUL configuration directly for all components.
11. **Are records being filtered or buffered?** Check handler/filter, flush behavior, collection destination, and retention.

### Example of redirecting stderr while learning JUL

On bash:

~~~bash
java -Djava.util.logging.config.file=logging.properties JulConfigDemo 2> jul-stderr.log
~~~

The **2>** operator redirects **stderr** to a file; a single **>** usually redirects only stdout. FileHandler is the way to save logs via JUL's own mechanism, which is different from shell output redirection.

In PowerShell, redirection syntax also supports **2>**, though encoding and error representation can differ across versions; when you need to preserve bytes/non-ASCII characters accurately, check the encoding and actual collection mechanism.

## 15. Common mistakes when configuring JUL

| Mistake | Symptom | How to fix |
| --- | --- | --- |
| Using Level.DEBUG or Level.ERROR with JUL | Compilation error | Use Level.FINE or Level.SEVERE according to semantics |
| Setting only logger to FINE, handler still INFO | FINE details do not appear | Adjust the handler threshold as well |
| Setting only handler to FINE, logger still INFO | Logger drops events first | Set the appropriate logger/package level |
| Disabling useParentHandlers without adding a handler | No output | Attach a dedicated handler or enable parent forwarding |
| Attaching a handler on every request | Duplicate logs, growing resource usage | Configure once at initialization |
| Calling System.setProperty after JUL has initialized | New configuration is not loaded as expected | Pass JVM -D at startup or reload in a controlled way |
| Confusing stdout with stderr | Redirecting the wrong stream and thinking there are no logs | Remember ConsoleHandler defaults to stderr |
| FileHandler.pattern pointing to a non-existent directory | Cannot open file | Create the directory, check path and permissions |
| Configuring SimpleFormatter and expecting always-identical output | Time zone, time, and source may vary | Customize the format and verify in the runtime environment |
| Logging only ex.getMessage() | No stack trace/cause | Pass the Throwable to the API and check the formatter |
| Leaving FINE enabled across all of production for too long | High log volume, higher cost, and data exposure risk | Enable selectively, set appropriate thresholds/retention |
| Calling LogManager.reset() from an arbitrary library | Affects logging across the whole JVM | Let the application/framework manage global configuration |
| Installing multiple bridges/backends uncontrolled | Duplicate logs, lost logs, or forwarding loops | Choose one consistent logging architecture |

## 16. Self-check questions

**Question 1.** Logger **demo.orders** is set to FINE, ConsoleHandler is set to INFO. Will a fine(...) call appear on the console?

**Answer:** No. The logger accepts it, but ConsoleHandler drops the FINE record according to the handler's level.

**Question 2.** Root is set to INFO, logger demo.orders is set to FINE, and ConsoleHandler at root is set to FINE. Can a FINE event be output?

**Answer:** Yes, provided no other filter blocks it and forwarding to the root handler is enabled. The INFO level at root does not re-filter a record already accepted by a child logger.

**Question 3.** To configure from a file before running main, what should you use?

**Answer:** Use the JVM option **-Djava.util.logging.config.file=<path>**, placed before the class/JAR name. The file contains properties such as **handlers**, **.level**, and **java.util.logging.ConsoleHandler.level**.

**Question 4.** Why can **java JulConfigDemo > out.log** produce an empty file even though the terminal still shows JUL logs?

**Answer:** **ConsoleHandler outputs to stderr by default**, whereas **>** usually redirects stdout. Use **2>** if you want to redirect stderr, or configure an appropriate handler.

**Question 5.** You need a FINE line written to a file without appearing on the console. What can you do?

**Answer:** The logger must accept FINE, FileHandler must be set to FINE, and ConsoleHandler must be set to INFO. The example in the FileHandler section illustrates this exact separation.

**Question 6.** Does **Logger.getLevel() == null** mean the logger is disabled?

**Answer:** No. The logger can inherit its effective threshold from its parent. If you want to disable by level, the threshold value is **Level.OFF**.

**Question 7.** If you use SimpleFormatter and do not see the Throwable's stack trace, what should you check?

**Answer:** Check whether the Throwable was actually passed into the LogRecord, which handler/formatter is outputting the event, and whether the pattern retains the exception part. A custom formatter must actively handle this part if you want it displayed.

**Question 8.** Why should a library not call LogManager.reset() just to change its own logger?

**Answer:** Because LogManager manages logging globally for the JVM; resetting can detach/close handlers and alter the configuration of other loggers.

**Key takeaway:** JUL configuration decides **which logger emits logs, which level is accepted, which handler receives them, and how the Formatter displays them**. For plain Java, start with **logging.properties + -Djava.util.logging.config.file**, check **both the logger level and the handler level**, and then add **FileHandler, formatter, rotation, and data protection** as operational needs require.

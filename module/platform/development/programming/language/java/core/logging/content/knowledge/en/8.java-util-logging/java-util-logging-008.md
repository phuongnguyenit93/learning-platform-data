# LogManager in Java Util Logging (JUL)

## 1. What Problem Does LogManager Solve?

**java.util.logging.LogManager** is the configuration manager and Logger registry for **Java Util Logging (JUL)**, the built-in logging system in the JDK. When an application has many classes, packages, and log destinations, it needs a central place to determine the level of each Logger, configure Handlers, read configuration from files, and manage registered Loggers. That is the role of LogManager.

For example, a sales application has Loggers **com.example.order**, **com.example.payment**, and **com.example.inventory**. When you want to enable detailed logging only for payment, you can configure it by name instead of modifying every `logger.info` or `logger.fine` call in business code.

After this lesson, you will be able to:

- Distinguish **LogManager**, **Logger**, **LogRecord**, **Level**, **Handler**, **Filter**, and **Formatter**.
- Understand LogManager as a **JVM-scoped** management component, how to obtain the instance via **getLogManager()**, and how to look up a Logger by name.
- Use the APIs **getProperty**, **getLogger**, **getLoggerNames**, and understand the roles of **addLogger**, **readConfiguration**, **reset**, and **updateConfiguration**.
- Know the loading path of **logging.properties**, the JVM argument **java.util.logging.config.file**, and the relationship between the root Logger and child Loggers.
- Compile and run a Java 17+ program that loads configuration via an `InputStream` and accurately observe how Logger/Handler filter records.
- Identify issues such as reload dropping Handlers, configuring FINE without seeing logs, duplicate logging, and confusing JUL with other backends.

**Scope of content:** This lesson focuses on JUL's LogManager in Java Core. It does not implement a centralized log storage system and does not replace LogManager with a custom framework.

## 2. Position in the Logging Architecture

JUL components collaborate as follows:

~~~text
Application code
  |
  | Logger.getLogger("com.example.order")
  v
Logger  <------------------------- LogManager
  |                             - register/lookup Logger names
  |                             - configure from properties
  |                             - read/reload/reset
  |                             - level and Handler config
  v
LogRecord (Level, message, time, parameters, Throwable)
  |
  +--> Logger Filter (if any)
  |
  v
Handler(s): level + Filter
  |
  v
Formatter
  |
  v
stdout/stderr, file, output stream, collector...
~~~

The diagram illustrates **roles**, not every internal JDK call in strict order. In JUL, the Logger checks its level and filter before passing the LogRecord to Handlers; each Handler also has its own filtering threshold. Formatter is the component used by a Handler to produce text output.

**LogManager does not write directly to the console or a file.** It does not replace Handler and is not an API for emitting logs. If business code calls **logger.info("order created")**, the Logger emits the event; JUL/LogManager configuration helps determine which Loggers are enabled and which Handlers a record can reach.

| Component | Responsibility | Familiar APIs |
| --- | --- | --- |
| **LogManager** | Manages JUL configuration, Logger registry, and configuration lifecycle | getLogManager, getProperty, readConfiguration |
| **Logger** | Emits records, checks level/filter, forwards to handlers | getLogger, info, warning, log |
| **LogRecord** | Carries data for a single event | getLevel, getMessage, getThrown |
| **Level** | Severity level or threshold | SEVERE, WARNING, INFO, FINE, ALL, OFF |
| **Handler** | Accepts records and writes to a destination | publish, flush, close |
| **Filter** | Decides whether a record is valid at a checkpoint | isLoggable |
| **Formatter** | Converts a record into text | format, formatMessage |

Simply using standard Logger names and centralized configuration is still not enough to guarantee that logs are observable. The actual output path depends on all of the layers above as well as any post-JVM pipeline if present.

## 3. The Global JVM LogManager

In most applications, LogManager is obtained via:

~~~java
import java.util.logging.LogManager;

LogManager manager = LogManager.getLogManager();
~~~

This is an illustrative snippet inside a Java method, not a standalone program with `main()`. **LogManager.getLogManager()** returns the LogManager that JUL is currently using in the JVM. It is a shared infrastructure object, not per-request data.

An application should hold Loggers per class or module:

~~~java
import java.util.logging.Logger;

public class OrderService {
    private static final Logger LOG =
            Logger.getLogger(OrderService.class.getName());

    public void create(String orderId) {
        LOG.info("event=order.created orderId=" + orderId);
    }
}
~~~

The class above is a compilable component; it does not have `main()`. The **static final** field keeps a stable Logger reference; the Logger is named after the class. In production environments, you must control the data placed into messages so that sensitive information is not logged.

**Do not create a Logger per request ID or per customer.** For example, **Logger.getLogger("request-" + requestId)** creates a dynamic namespace that is hard to manage, increases the number of Loggers, and makes properties difficult to apply. A correlation ID should be event data rather than a Logger name.

### 3.1. Root Logger

The Root Logger in JUL has **the empty string as its name**:

~~~java
Logger root = LogManager.getLogManager().getLogger("");
~~~

Therefore, the level configuration for root is typically:

~~~properties
.level = INFO
~~~

Loggers have dot-separated hierarchical names by namespace:

~~~text
"" (root)
  |
  +--- com
         |
         +--- com.example
                   |
                   +--- com.example.order
                   +--- com.example.payment
~~~

Some parent nodes may be created by the system to maintain the Logger tree. Registered names and Logger references can change over the JVM lifecycle.

### 3.2. Own Level vs. Inherited Level

A Logger can have a specific level or **getLevel() == null**. **Null** means the Logger has no explicit level of its own, so it inherits the effective level from the nearest configured ancestor. Null **does not mean ALL**.

For example:

~~~text
root: INFO
  com.example: WARNING
    com.example.order: null => inherits WARNING
    com.example.payment: FINE => uses own FINE
~~~

**Level inheritance** is different from **forwarding records to a parent's Handlers**. A record already accepted by a child Logger can be forwarded to a parent Logger's Handlers if `useParentHandlers` allows it; the level of each parent Logger is not re-evaluated the way it would be when the record originates at that parent. However, the parent's Handlers still apply their own threshold and filter.

## 4. Important Methods of LogManager

### 4.1. getLogManager()

Obtains the LogManager currently used by JUL:

~~~java
LogManager manager = LogManager.getLogManager();
~~~

This is the standard entry point for working with global configuration; there is no need to create a separate LogManager per package or request.

### 4.2. getProperty(String key)

Returns a **String** from the loaded properties set:

~~~java
String level = manager.getProperty("com.example.payment.level");
~~~

If the key does not exist, the result can be **null**. A value of **"FINE"** is configuration text, not definitive proof that the console is printing FINE. The Handler might still be at INFO, a Filter might be blocking it, or the Logger might be using a different name.

**Distinguish:** `getProperty` returns configuration text; `logger.getLevel()` returns the Level set directly on the Logger; `logger.isLoggable(Level.FINE)` checks whether the Logger accepts that level at the time of the call.

### 4.3. getLogger(String name)

Looks up a Logger already registered with LogManager:

~~~java
Logger candidate = manager.getLogger("com.example.payment");
~~~

This method **can return null** when the Logger has not been registered yet or no longer has an active reference. To obtain or create a Logger in application code, you should use:

~~~java
Logger logger = Logger.getLogger("com.example.payment");
~~~

**Do not confuse LogManager.getLogger with Logger.getLogger.** One is a registry lookup, while the other is the convenience API to retrieve or create the corresponding Logger.

### 4.4. getLoggerNames()

Lists the names of Loggers currently being managed:

~~~java
import java.util.Enumeration;
import java.util.logging.LogManager;

Enumeration<String> names = LogManager.getLogManager().getLoggerNames();
while (names.hasMoreElements()) {
    System.out.println(names.nextElement());
}
~~~

This is a snippet inside a method, without `main`. The result may include root with the empty name and Loggers created by the JDK, libraries, or the application. The registry is not an immutable list of every class in the project: some Loggers can be garbage-collected if no strong reference is held. Do not use the count of Logger names to infer the number of requests or business services.

### 4.5. addLogger(Logger)

Registers a manually created Logger into LogManager. If another Logger with the same name already exists in the registry, `addLogger` can **return false**. Most application code does not need to call this method because **Logger.getLogger(name)** already performs the standard registration flow.

Creating multiple Loggers with the same name manually can lead to confusing registry/configuration relationships. Only use `addLogger` when you have a specialized Logger management need and understand the API contract.

### 4.6. readConfiguration and reset

Notable methods:

- **readConfiguration()**: reloads configuration through the configuration source mechanism chosen by LogManager.
- **readConfiguration(InputStream)**: reads properties configuration from a stream provided by the application.
- **reset()**: resets the logging state, including removing and closing existing Handlers, and resets levels according to JUL rules.

These operations have a **JVM-wide effect on JUL**. Do not call them on every business request to try to "refresh logging".

### 4.7. updateConfiguration and Listeners

Modern JDKs provide **updateConfiguration(...)** to apply new configuration through property merging/mapping rules. LogManager also provides **addConfigurationListener** and **removeConfigurationListener** for components that need to know when configuration changes.

These APIs are useful for dynamic configuration management, but you must understand the exact contract of the target JDK. **A listener does not automatically turn a file into a continuously watched source.** The application must still decide when to update/reload and handle errors. If a small application only needs console/file output and fixed levels, a startup configuration file is usually enough.

## 5. Where Is JUL Configuration Loaded From?

### 5.1. Default JDK File

In modern JDKs (Java 9+), the default configuration is typically located at:

~~~text
<JAVA_HOME>/conf/logging.properties
~~~

Older JDKs use a different directory layout. Applications do not need to edit the JDK's own configuration file to change logging; they can provide a separate file for the application.

### 5.2. java.util.logging.config.file

When starting the JVM, you can specify the application's logging file:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This illustrative command assumes there is already a **com.example.Main** class in the **out** directory and a **logging.properties** file found relative to the working directory. It is not the command to run the `LogManagerDemo` program in section 7.

**Set the property at startup**, before LogManager is initialized. If a library uses a Logger during bootstrap, setting the property later does not mean all components will automatically re-read the file. Use an absolute path or a controlled working directory to avoid reading the wrong file.

### 5.3. java.util.logging.config.class

JUL also supports specifying a dedicated configuration class via **java.util.logging.config.class** during initialization. This mechanism is for advanced configuration and has precedence rules with file-based loading. Do not assume `config.file` and `config.class` will merge unconditionally; choose one clear bootstrap source.

### 5.4. Reading an InputStream Directly

Inside a program, you can call:

~~~java
LogManager manager = LogManager.getLogManager();
manager.readConfiguration(inputStream);
~~~

This snippet assumes **inputStream** is an open stream containing Java properties content; it is not a standalone runnable program. The example in section 7 uses `ByteArrayInputStream` so learners do not need to prepare a file.

Be careful: **readConfiguration** can reset the previous configuration and close active Handlers. It is suitable for controlled bootstrap or a designed reload mechanism, not for changing a single setting arbitrarily.

## 6. Contents of logging.properties

Example:

~~~properties
# Root logger level
.level = INFO

# Output destination for root
handlers = java.util.logging.ConsoleHandler

# Console handler settings
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# A named logger can be more verbose
com.example.payment.level = FINE
~~~

Meaning:

- **.level = INFO**: the root Logger has level INFO.
- **handlers = ...ConsoleHandler**: configures the Handler for root.
- **ConsoleHandler.level = INFO**: ConsoleHandler has threshold INFO.
- **ConsoleHandler.formatter = ...SimpleFormatter**: formats the output.
- **com.example.payment.level = FINE**: that named Logger is configured to FINE; child Loggers inherit it unless they set their own level.

**Very common pitfall:** the payment Logger accepts FINE, but ConsoleHandler is at INFO, so **FINE records still do not appear on the console**. If you want to output FINE on this Handler (and no filter blocks it), you must change:

~~~properties
java.util.logging.ConsoleHandler.level = FINE
~~~

You do not necessarily have to set root to FINE if the child Logger has its own FINE level and forwards records to root's Handler; JUL does not re-check the level of each parent Logger along the forwarding path. However, Handler/Filter and `useParentHandlers` still determine the actual output.

### 6.1. Standard Levels

| Level | Common Usage |
| --- | --- |
| SEVERE | Serious failure |
| WARNING | Anomaly requiring attention |
| INFO | Operational event |
| CONFIG | Configuration information |
| FINE, FINER, FINEST | Diagnostic details |
| OFF | Blocks normal records at the configured threshold |
| ALL | Allows all normal levels at the configured threshold |

Setting OFF on a parent Logger **does not necessarily disable** a child Logger that has its own level; setting ALL on a Logger **does not force** an INFO Handler to print FINE records.

### 6.2. FileHandler Configuration Example

~~~properties
java.util.logging.FileHandler.pattern = logs/app-%u-%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

These properties **only describe how FileHandler behaves if a FileHandler is created/attached**. They do not create files on their own when the pipeline does not use FileHandler. Prepare the **logs/** directory and write permissions, and manage file rotation, retention, and disk-full handling.

### 6.3. Properties Format

The JUL configuration file uses Java properties syntax, with key/value pairs and comment lines starting with **#** or **!**. Content is loaded using the traditional `Properties` mechanism. In particular, an **InputStream** has different decoding rules than reading arbitrary UTF-8 text; the technical properties in the examples use ASCII only. When Unicode is present in configuration, verify escaping/reading behavior according to the exact API and JDK.

Configuration encoding and **log message** encoding are two separate concerns. Console, file, and collector each have their own charset/encoder to preserve Vietnamese or other Unicode characters.

## 7. Standalone Java 17+ Example: Loading Configuration with LogManager

This program can run with only the JDK. We will:

1. Create an in-memory configuration: root **WARNING**, Logger **demo.billing** at **FINE**.
2. Load it into **LogManager.readConfiguration(InputStream)**.
3. Obtain the Logger and attach a custom Handler that only accepts INFO and above.
4. Observe **getProperty**, **getLogger**, **getLevel**, **isLoggable**, and the output.
5. Clean up the attached Handler when the demo finishes.

Create **LogManagerDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogManagerDemo {
    public static void main(String[] args) throws Exception {
        String config = ".level=WARNING\n"
                + "demo.billing.level=FINE\n";

        LogManager manager = LogManager.getLogManager();
        try (ByteArrayInputStream in =
                     new ByteArrayInputStream(config.getBytes(StandardCharsets.ISO_8859_1))) {
            manager.readConfiguration(in);
        }

        Logger logger = Logger.getLogger("demo.billing");
        logger.setUseParentHandlers(false);
        Handler handler = new Handler() {
            @Override
            public void publish(LogRecord record) {
                if (isLoggable(record)) {
                    System.out.println(record.getLevel().getName() + " " + record.getMessage());
                }
            }
            @Override public void flush() { System.out.flush(); }
            @Override public void close() { flush(); }
        };
        handler.setLevel(Level.INFO);
        logger.addHandler(handler);

        try {
            System.out.println("manager-property=" + manager.getProperty("demo.billing.level"));
            System.out.println("logger-level=" + logger.getLevel().getName());
            System.out.println("root-level=" + manager.getLogger("").getLevel().getName());
            System.out.println("same-logger=" + (manager.getLogger("demo.billing") == logger));
            System.out.println("fine-allowed-by-logger=" + logger.isLoggable(Level.FINE));
            logger.fine("billing.debug");
            logger.info("billing.started");
            logger.warning("billing.retry");
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 LogManagerDemo.java
java LogManagerDemo
~~~

**stdout verified by compiling and running:**

~~~text
manager-property=FINE
logger-level=FINE
root-level=WARNING
same-logger=true
fine-allowed-by-logger=true
INFO billing.started
WARNING billing.retry
~~~

### 7.1. Why Are Those Exact Lines Printed?

- **manager-property=FINE**: the `demo.billing.level` property was loaded successfully.
- **logger-level=FINE**: the Logger was configured by name.
- **root-level=WARNING**: root carries level WARNING from the `.level` configuration.
- **same-logger=true**: `manager.getLogger` looks up the same Logger object currently held by reference.
- **fine-allowed-by-logger=true**: the Logger at FINE allows the FINE level at its own layer.
- **billing.debug does not appear**: the Handler at INFO drops FINE.
- **billing.started** and **billing.retry** appear because INFO/WARNING pass both the Logger and the Handler.

Do not conclude that LogManager dropped FINE: in this case the Logger allowed it, while the Handler filtered it at the output point.

### 7.2. Why Use an Illustrative Handler?

JUL's default **ConsoleHandler** normally uses **stderr** and a formatter with environment-dependent timestamps/content. The small Handler in the demo intentionally prints to **stdout** with a fixed format so output can be verified reliably. **setUseParentHandlers(false)** prevents a record from also being emitted through the root Handler.

The Handler here is only for learning, not a complete production sink: it has no I/O error handling, concurrency, or backpressure policy. In real applications, use built-in Handlers or an appropriate backend.

## 8. Reloading, Updating Configuration, and Resetting

Three different operations must be distinguished.

### 8.1. Initial Load

When the JVM first initializes logging, LogManager reads configuration from the selected source. If a custom file is needed, set **java.util.logging.config.file** at startup. Libraries that create a Logger before `main()` can trigger early logging initialization, so do not rely on setting the system property late in bootstrap.

### 8.2. readConfiguration(...) Replaces the Current Configuration

When calling **readConfiguration(InputStream)**, JUL applies the new configuration set and, per its contract, can **reset the previous configuration**, including removing and closing registered Handlers.

A system might be in the following state:

~~~text
Logger demo.billing
  +-- Console Handler
  +-- File Handler
~~~

After reload, the Handler list may no longer be the same as before. If the new file does not recreate/reattach the right destinations, logs can disappear even though the Logger still exists.

**Verified on a Java program:** A Logger with a ConsoleHandler attached and set to FINE, after `readConfiguration` with property **demo.reload.level=SEVERE**, had **logger.getLevel() == SEVERE** and **logger.getHandlers().length == 0**. This proves that reloading affects both the level and Handlers in the tested example.

Do not simply edit a file and call `readConfiguration` on every request; design a verified reload process and control when the operation occurs.

### 8.3. updateConfiguration(...) Merges by Policy

**updateConfiguration** in modern JDKs allows updating properties based on a caller-supplied mapping/merge function. It is better suited when complex dynamic configuration management is needed, but it is not a guarantee that changes will leave Handlers or current state untouched.

Clearly define the semantics when keys appear, disappear, or change; test level, handler, formatter, file path, and in-flight records. Check the API contract of your target JDK before implementing.

### 8.4. reset()

**LogManager.reset()** puts the logging state into a reset state according to JUL rules, removing and closing existing Handlers. It affects logging across the entire JVM. Do not use `reset` to temporarily mute a single package.

If you only want to enable details for one module, change that Logger's level or configure by package. If you want to disable an output destination, control the corresponding Handler/routing.

### 8.5. Editing a File Is Not the Same as Changing a Running Logger

The following two operations are different:

~~~java
Logger.getLogger("com.example").setLevel(Level.WARNING);
~~~

and editing a line in the file:

~~~properties
com.example.level = WARNING
~~~

The first operation changes the runtime state of the Logger. The second only changes the file contents; for the application to pick up the change, there must be a reload or restart step according to policy. A `setLevel` call in code can also be overwritten by a subsequent configuration reload.

## 9. Loggers, the Registry, and Name Stability

LogManager manages Loggers by **name**, so names must be exact. If you configure:

~~~properties
com.example.payment.level = FINE
~~~

but the code requests a Logger named **com.example.payments**, the property will not apply to the intended target.

Naming recommendations:

- Use **Class.getName()** for a class Logger.
- Use stable package/module names if you want to control a group together.
- Do not embed `requestId`, `userId`, `transactionId`, or runtime timestamps into Logger names.
- Put correlation metadata into the event or an appropriate logging context.

A Logger without its own level can inherit a level from an ancestor, but **getLevel() == null** does not directly tell you what the effective level is. Use **isLoggable(level)** to ask whether the current Logger accepts a specific level; after that, you still need to check Handlers/filters to know whether a record reaches the destination.

### 9.1. The Registry Is Not a Historical Log

**getLoggerNames()** reflects the Loggers currently tracked by LogManager. It does not list every Logger ever created in the past and does not represent a list of all Java files. LogManager may only hold weak references to some Loggers; code should retain references to the Loggers it actually needs.

### 9.2. Parent Handlers and Duplicate Logs

For example, a child Logger has its own ConsoleHandler attached while **useParentHandlers=true**; the record also travels to the parent's Handler, potentially producing two lines. To have a separate pipeline, you can set:

~~~java
logger.setUseParentHandlers(false);
~~~

However, **only disable parent handlers when another destination has been configured**. If a Logger has no Handlers of its own and does not forward to its parent, there may be no output at all. Check **logger.getHandlers()**, **getUseParentHandlers()**, and ancestor Handlers before changing this.

## 10. Logging Levels and Observability

Levels such as SEVERE, WARNING, INFO, and FINE are compared against the Logger's threshold. Afterward, the Handler also applies its own level/filter.

For example:

| Logger level | Handler level | INFO record | FINE record |
| --- | --- | --- | --- |
| INFO | INFO | Can be emitted | Dropped by Logger |
| FINE | INFO | Can be emitted | Dropped by Handler |
| FINE | FINE | Can be emitted | Can be emitted |
| OFF | ALL | Blocked at Logger | Blocked at Logger |
| ALL | OFF | Dropped by Handler | Dropped by Handler |

The table assumes there is no additional Filter, Logger/Handler are wired properly, and the output destination is working. In real systems, files, consoles, or collectors can also fail, be rate-limited, or drop data in the post-JVM pipeline.

**A missing log does not mean LogManager failed to load the file.** Verify each step in order: property, Logger, level, Filter, Handler, Formatter, destination.

## 11. Customizing the System LogManager

An advanced scenario is replacing the LogManager implementation via a JVM system property:

~~~text
-Djava.util.logging.manager=com.example.logging.CustomLogManager
~~~

This is an example of the flag syntax. It will not run without a valid class, class-loading setup, and an implementation conforming to the JDK contract. Selecting a custom LogManager must usually happen **before logging initializes**.

Only consider a custom LogManager if your platform, framework, or container has special JVM-wide logging management requirements. It is **not** the default choice for switching to JSON format, adding timestamps, writing files, or changing destinations. Those changes belong in Handler/Formatter/encoder/collector.

Issues to consider when customizing:
- Initialization order of LogManager and other logging classes.
- Class loader / module path of the custom implementation.
- Compatibility with libraries using JUL.
- How reload, reset, Handlers, and shutdown are handled.
- Isolated testing to avoid affecting the test environment's loggers.

## 12. Does LogManager Control All Logging Frameworks?

No. **LogManager** belongs to **java.util.logging**. Other systems have their own configuration mechanisms.

| Logging API/stack | What to check |
| --- | --- |
| java.util.logging.Logger | LogManager, JUL Logger, Handler, Filter |
| org.slf4j.Logger | SLF4J provider and actual backend |
| Logback | Logback logger context, appender/encoder/filter |
| Log4j 2 | Log4j 2 configuration, logger config, appender |
| JDK's System.Logger | Active LoggerFinder/provider |

**SLF4J** is a facade; it usually routes to a provider/backend such as Logback or another solution. Editing JUL's `logging.properties` does not automatically change Logback levels. **Log4j 2** has a different API and implementation from JUL.

The JDK also has **System.Logger** and the **System.LoggerFinder** mechanism. Depending on the runtime/provider, routing may involve JUL, but you should not assume LogManager always governs every `System.Logger` when a custom provider is present.

If a library uses JUL and the main application uses SLF4J, a **bridge** may be needed. Control the bridge direction to avoid loops such as `JUL -> SLF4J -> JUL`, and check for duplicate record output. Do not install multiple adapters just to "make sure every log is collected".

## 13. Risks When Manipulating Configuration

### 13.1. Initialization Timing

A library may use a Logger in a static initializer or during framework bootstrap. If **java.util.logging.config.file** is set afterward, LogManager may have already read the old source. Good practice is to set the configuration right at JVM startup, then verify the values on a real Logger.

### 13.2. Handler Lifecycle

**readConfiguration/reset** can detach and close existing Handlers. When an application creates a FileHandler or network handler, reload must handle:

- Have old Handlers been flushed and closed properly?
- Are new Handlers created and attached to the right Loggers?
- Does the file path have write permission and does the directory exist?
- Is there an output gap between the two configurations?
- Are records duplicated if two Handlers are attached simultaneously?
- If the sink fails or fills up, is there appropriate error reporting/backpressure?

Do not deploy untested hot reload and rely on luck.

### 13.3. Concurrency and Global Configuration

LogManager is shared state. Threads may be writing records while configuration changes. Changing levels/Handlers at runtime causes output to vary depending on processing timing; do not expect an arbitrary "atomic configuration snapshot" if the backend does not guarantee it.

A test calling **reset()** or **readConfiguration** can affect other tests if run concurrently in the same JVM. Tests that modify global configuration should be run in an isolated JVM or with clear lifecycle management.

### 13.4. Performance and Cost

Enabling FINE/FINER/FINEST broadly can dramatically increase log volume, driving up CPU, I/O, memory, network, storage, and latency. Synchronous Handlers can block business threads if the destination is slow. Collectors/async pipelines can drop records under overload.

Choose levels by environment and package scope. Do not use LogManager as a business data store or a replacement for tracing/metrics policies.

### 13.5. Sensitive Data

A FINE-level record may contain query parameters, request bodies, or exception messages with private information. Enabling verbose levels can expose data that was previously suppressed. Never log tokens, passwords, API keys, session cookies, private keys, or sensitive payloads at any level. Enforce this from message creation through all sinks.

## 14. Diagnosing LogManager Configuration Issues

### Case A: Edited logging.properties but level did not change

Check in order:

1. Was **java.util.logging.config.file** set at JVM startup?
2. Is the file path valid for the working directory and readable?
3. Is **java.util.logging.config.class** or a custom manager affecting the load source?
4. Does the property key match the exact Logger name, e.g. **com.example.payment** vs. **com.example.payments**?
5. Does code call **setLevel** after loading the file?
6. Is another **readConfiguration** call overwriting the configuration?
7. Is the application actually using JUL, or is it using SLF4J/Logback/Log4j 2?

You can compare **manager.getProperty(key)**, **logger.getLevel()**, and **logger.isLoggable(Level.FINE)** in a controlled diagnostic environment.

### Case B: getProperty returns FINE but FINE logs do not appear

Check next: **Handler level**, Logger Filter, Handler Filter, parent handlers, the actual list of Handlers attached to the Logger, and the output destination. **getProperty** is not proof that records are being printed.

### Case C: No logs after reload

If the application uses **readConfiguration**, old Handlers may have been detached/closed. Check the Handler count before/after in a test environment and verify the mechanism that recreates Handlers from configuration. Do not call reload repeatedly before knowing whether the pipeline has been restored.

### Case D: Logs appear twice

Usually caused by Handlers attached to both child and parent loggers with **useParentHandlers=true**, or two bridges/providers writing together. Identify the exact Handlers and namespaces; do not disable parent handlers blindly.

### Case E: manager.getLogger returns null

This is valid if the Logger has not been registered yet or no longer has an active reference. Application code that needs a Logger should call **Logger.getLogger(name)** and keep a reference; inspection tools must handle `null`.

### Case F: Custom class is not loaded

Check the classpath/module path, fully qualified class name, constructor/initialization contract, permissions, when the JVM initializes logging, and supporting libraries. Do not jump to blaming file write permissions without a specific error message.

## 15. Testing LogManager

A test suite should focus on **behavior** rather than only reading property strings:

| What to test | Useful check |
| --- | --- |
| Loading properties | `manager.getProperty(key)` returns the expected value |
| Logger registration | `manager.getLogger(name)` finds the created instance |
| Level configuration | `logger.getLevel()`, `isLoggable(level)` |
| Level inheritance | Child Logger with null level has the expected effective level |
| Parent forwarding | `getUseParentHandlers()` and actual output |
| Handler filtering | INFO Handler drops FINE records even when Logger is FINE |
| Output format | Log line has the expected level/message/Throwable |
| Configuration reload | Logger/Handler change properly and sink remains active |
| File/network failure | Appropriate error handling and fallback, no recursion |
| Shutdown | Resources flush/close properly without unexpected data loss |

**Do not use ConsoleHandler's stdout as an absolute criterion**: JUL's default ConsoleHandler normally writes to stderr and SimpleFormatter includes timestamps, class/source, and exceptions. In the section 7 example, the Handler controls stdout so output can be compared deterministically.

When testing global configuration, avoid running reset/reload tests in the same JVM concurrently with business tests that rely on global Loggers.

## 16. Self-Check Exercises

**Exercise 1 — Change the Logger level.** In the demo, change property **demo.billing.level=FINE** to **demo.billing.level=WARNING**. Run again. Is INFO blocked? Is WARNING still emitted? Explain Logger and Handler thresholds.

**Exercise 2 — Change the Handler level.** Keep the Logger at FINE but set the Handler to FINE. Observe **billing.debug** appear; change the Handler back to INFO and watch it disappear. The result clearly demonstrates two independent thresholds.

**Exercise 3 — Use an external file.** Create `logging.properties` and run a Java class with a matching Logger name using **-Djava.util.logging.config.file=...**. Compare LogManager's property values with the loaded file.

**Exercise 4 — Reload in a test JVM.** Attach a Handler to a Logger, record **getHandlers().length**, call `readConfiguration` with a different level, then inspect the Handler list and level after reload. Explain why production programs must care about sink lifecycle.

**Exercise 5 — Distinguish frameworks.** In an application with a library using JUL and a component using SLF4J, describe which part LogManager manages; identify the need for a bridge and the risk of a loop.

### Questions and Answers

**1. Is LogManager a Handler?** No. It manages configuration and the Logger registry; a Handler processes and writes records to a destination.

**2. Does getLogger(name) always create a new Logger?** No. `LogManager.getLogger` looks up an already registered Logger; application code normally uses `Logger.getLogger`.

**3. Which property configures the Root Logger?** **.level**, because the root Logger has an empty name.

**4. Does getProperty returning FINE mean the console prints FINE?** No. The Handler, Filter, and route to the output must also allow it.

**5. Why can a child Logger with a null level still log?** Because it inherits the effective level of its ancestor; null does not mean OFF.

**6. Does editing a properties file reload automatically?** Not by default. A restart or an intentional reload mechanism is required.

**7. Why can readConfiguration cause logs to disappear?** Because it can reset configuration and remove/close old Handlers while the new destination has not been attached.

**8. Should reset be called on every request?** No. It affects logging across the entire JVM, including other requests.

**9. To switch the formatter to JSON, do you need to replace LogManager?** Usually not; configure the appropriate Formatter/encoder, Handler, or backend.

**10. Does LogManager control all SLF4J or Log4j 2 loggers?** Not by default. Check the actual provider/backend and bridge.

## 17. Key Takeaways

**LogManager is the JVM-scoped configuration manager for JUL**, while Logger emits records and Handler writes them to a destination. A **logging.properties** file provides centralized configuration by Logger name, root Logger, and Handlers. **getProperty** inspects configuration values; **getLogger** queries the registry; **readConfiguration** loads configuration and can affect Handler lifecycle.

To diagnose missing logs, follow the path **property -> logger name/level -> filter -> handler/parent handlers -> output**. To reload safely, verify both levels and that logging resources are properly recreated, and avoid mutating global configuration while other threads are processing unless a clear operational contract is in place.

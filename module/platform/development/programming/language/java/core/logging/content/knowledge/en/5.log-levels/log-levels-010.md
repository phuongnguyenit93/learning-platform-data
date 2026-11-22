# Changing the Log Level While a Java Program Is Running

## 1. What Does Changing the Log Level at Runtime Mean?

A **log level** is a threshold that controls which logging events are accepted. When a system is running, it is sometimes necessary to enable more detailed logs to investigate an issue, and then revert to the original threshold after diagnosing it. **Changing the level at runtime (runtime log level change)** means adjusting that threshold in an already-running Java process without modifying the source code and recompiling.

For example, an application normally logs `INFO`, `WARNING`, and `SEVERE`. When a hard-to-reproduce issue occurs in the payment feature, the operations team temporarily enables `FINE` on the relevant logger, observes a few requests, and then switches back to `INFO`. There is no need to add new log statements if `logger.fine(...)` calls are already in the code; only the configuration needs to allow those records to be emitted.

Three different operations must be distinguished:

1. **Setting the level at startup**: reading configuration from a file, JVM arguments, or a framework before the application serves requests.
2. **Changing the level directly inside the JVM**: calling a logger management API or a logging administration mechanism provided by the framework.
3. **Editing a configuration file on disk**: modifying the file **does not necessarily** cause the application to apply the new value automatically; it only takes effect at runtime if a reload mechanism is active or an explicit reload operation is performed.

This article focuses on **`java.util.logging` (JUL) in Java 17+**, which is built into the JDK. With SLF4J/Logback, Log4j2, or Spring Boot, the corresponding operation depends on the actual backend.

## 2. Reviewing Log Levels in JUL

JUL has the following common levels ordered from most severe to most detailed:

| Level | Practical Meaning |
| --- | --- |
| `SEVERE` | Critical error; the task cannot complete |
| `WARNING` | Anomaly worth noting, though the process can continue |
| `INFO` | Important operational milestones |
| `CONFIG` | Configuration information for diagnostics |
| `FINE` | Details for debugging |
| `FINER` | More detailed than `FINE` |
| `FINEST` | Very deep detail |

Two special values: `Level.ALL` allows all levels, and `Level.OFF` disables records passing through that filter.

The `INFO` level allows `INFO`, `WARNING`, and `SEVERE`; records at `CONFIG`, `FINE`, `FINER`, and `FINEST` are filtered out. When lowering the threshold from `INFO` to `FINE`, the application can additionally emit `CONFIG` and `FINE` records.

> SLF4J/Logback and Log4j2 have `DEBUG` and `TRACE` levels. **JUL does not have `Level.DEBUG` or `Level.TRACE`**. Do not copy level names from one backend to another without checking the supported API and configuration.

## 3. Logger Level and Handler Level Are Two Separate Thresholds

In JUL, whether a log line appears depends at least on the **originating logger** and the **receiving handler**:

```text
logger.fine("Preparing payment")
    |
    v
Logger: accept Level.FINE?
    | no -> dropped at logger
    | yes
    v
Handler: accept Level.FINE?
    | no -> not output at that handler destination
    | yes
    v
Console / file / other log destination
```

Examples:

| Logger level | ConsoleHandler level | `logger.fine(...)` |
| --- | --- | --- |
| `INFO` | `ALL` | Not visible: blocked by logger |
| `FINE` | `INFO` | Not visible: blocked by handler |
| `FINE` | `FINE` | Visible on console, unless another filter blocks it |
| `ALL` | `WARNING` | Not visible on console; blocked by handler |
| `OFF` | `ALL` | Not visible: logger blocks all standard records |

To **enable a detailed level**, you must check both the effective threshold of the logger and the threshold of each handler; each handler can have a different level. For instance, the console can remain at `INFO` for readability, while a file handler accepts `FINE` for deep investigation.

A logger may have no handler attached directly and instead forward records to a parent logger's handlers, including the root logger. This also depends on `useParentHandlers`. When a record is propagated up from a child logger, **JUL does not re-apply the level of each parent logger**; handlers along the path still filter using their own levels. Therefore, changing only the root level does not guarantee that all records from child loggers will disappear or appear as expected.

## 4. Changing the Level Directly Using the Java API

A logger is retrieved by name and updated via `setLevel(...)`:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger paymentLogger = Logger.getLogger("com.example.payment");

// When investigation is needed:
paymentLogger.setLevel(Level.FINE);

// Check whether level FINE passes the logger filter:
boolean allowed = paymentLogger.isLoggable(Level.FINE);

// After investigation is complete:
paymentLogger.setLevel(Level.INFO);
```

The snippet above **illustrates how to call the API** and should be placed inside an appropriate method/class. The changed value affects the **logger with the same name managed within the current JVM**, not the JVMs of other services. `Logger.getLogger(name)` does not automatically send commands to every running application instance.

In real applications, keep loggers as `static final` per class or retain a reference to the configured logger to avoid unpredictable instance management. `setLevel` changes the logger's filtering behavior for subsequent log calls; records that were already filtered out earlier cannot be regenerated just by changing the level.

### Inherited Levels and the `null` Level

`Logger.getLevel()` returns the level **set directly** on the logger, which is not necessarily the current effective level:

```java
Logger logger = Logger.getLogger("com.example.payment");

logger.setLevel(Level.FINE); // Set explicit level.
logger.setLevel(null);       // Clear explicit level: inherit level from parent.
```

`null` means **inherit** from the nearest ancestor logger that has a defined level, which may ultimately be the root logger; **it does not mean disabling logs**. When a logger is inheriting, changing the parent logger's level can change the child logger's logging behavior. If the child logger has an explicit level set, changing the parent's level does not override that explicit configuration.

To check whether a level is accepted by a logger, use `isLoggable(Level.FINE)`; even if it returns `true`, a handler may still drop the record.

## 5. Runnable Java 17 Example: Changing the Level Inside the Program

This example has one logger and one `ConsoleHandler`. The program changes the level multiple times within **a single run**, showing which records are emitted after each change.

Create the file `RuntimeLogLevelDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RuntimeLogLevelDemo {
    private static final Logger LOG =
            Logger.getLogger(RuntimeLogLevelDemo.class.getName());

    public static void main(String[] args) {
        Level oldLevel = LOG.getLevel();
        boolean oldUseParentHandlers = LOG.getUseParentHandlers();
        Handler[] existingHandlers = LOG.getHandlers();

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        // Isolate demo handlers to avoid duplicate log records.
        for (Handler handler : existingHandlers) {
            LOG.removeHandler(handler);
        }
        LOG.setUseParentHandlers(false);
        LOG.addHandler(console);

        try {
            // Step 1: WARNING on logger, INFO on handler.
            LOG.setLevel(Level.WARNING);
            LOG.info("INFO before change - hidden");
            LOG.warning("1. WARNING is visible");

            // Step 2: lower logger threshold to INFO.
            LOG.setLevel(Level.INFO);
            LOG.info("2. INFO is now visible");
            LOG.fine("FINE while logger is INFO - hidden");

            // Step 3: logger allows FINE, but handler is still INFO.
            LOG.setLevel(Level.FINE);
            LOG.fine("FINE while handler is INFO - hidden");

            // Step 4: change handler so FINE is actually output.
            console.setLevel(Level.FINE);
            LOG.fine("3. FINE is now visible");

            // Step 5: handler only allows SEVERE.
            console.setLevel(Level.SEVERE);
            LOG.warning("WARNING while handler is SEVERE - hidden");
            LOG.severe("4. SEVERE is visible");
        } finally {
            LOG.removeHandler(console);
            console.close();

            // Restore initial logger state.
            LOG.setLevel(oldLevel);
            LOG.setUseParentHandlers(oldUseParentHandlers);
            for (Handler handler : existingHandlers) {
                LOG.addHandler(handler);
            }
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac RuntimeLogLevelDemo.java
java RuntimeLogLevelDemo
```

**Output from `ConsoleHandler` on `System.err`:**

```text
WARNING | 1. WARNING is visible
INFO | 2. INFO is now visible
FINE | 3. FINE is now visible
SEVERE | 4. SEVERE is visible
```

Because the formatter intentionally omits timestamps, the lines above are deterministic. In JUL, `ConsoleHandler` writes to **stderr** by default; this is not the program printing output via `System.out.println(...)`.

**Explanation in execution order:**

1. In step 1, the logger is set to `WARNING`, so `INFO` is blocked right at the logger. The handler set to `INFO` still receives `WARNING`.
2. When the logger is changed to `INFO` in step 2, `INFO` records pass the filter and appear on the console.
3. When the logger switches to `FINE` while the handler remains `INFO`, the `FINE` record is accepted by the logger but **dropped by the handler**.
4. After `console.setLevel(Level.FINE)`, both the logger and handler allow `FINE`, so the detailed line appears.
5. When raising the handler threshold to `SEVERE`, the `WARNING` record continues to be accepted by the logger, but is not output to the console; `SEVERE` is still output.

The example saves and restores the logger's level, parent propagation, and handlers; it does not call `close()` on pre-existing handlers because they may belong to other components. This is a standalone demo. In a multi-threaded running server, changing shared handlers or logger configurations can affect other requests; you should have an administrative mechanism that restricts permissions and synchronizes changes with the application lifecycle.

## 6. Changing the Level of Only One Package or Class

In a large application, it is usually inadvisable to lower the root logger threshold to `FINE` because too many components will emit detailed logs, increasing overhead and potentially exposing sensitive information. Choose a narrow logger by feature:

```java
import java.util.logging.Level;
import java.util.logging.Logger;

Logger payment = Logger.getLogger("com.example.payment");
payment.setLevel(Level.FINE); // Only this logger's scope and its inheriting children.

Logger sql = Logger.getLogger("com.example.persistence");
sql.setLevel(Level.WARNING); // Keep logs less verbose.
```

A logger named `com.example.payment.PaymentService` can inherit the `FINE` level from `com.example.payment` **if the parent–child relationship is established and it does not have an explicit level set**. Dots in the name do not guarantee that every intermediate logger already exists; when diagnosing, check `getParent()` and the effective level. If `PaymentService` has its own `setLevel(Level.INFO)`, changing the level on the `com.example.payment` package may not affect it.

To temporarily disable records emitted directly from a logger:

```java
payment.setLevel(Level.OFF);
```

Use `OFF` only intentionally; it can hide warnings/errors needed for operations. After investigation, restore the previous level, **including the case where it was previously `null`** (inherited), instead of always forcing it back to `INFO`.

## 7. Changing the Root Logger Level and Why It May Not Be Enough

The JUL root logger has the empty name `""`:

```java
Logger root = Logger.getLogger("");
root.setLevel(Level.WARNING);
```

Changing the root level can affect child loggers **that are inheriting** their level from root. However:

- Child loggers with an explicit level set continue to use their own level.
- Root handlers have their own level filter; for example, a handler set to `INFO` will not print `FINE`.
- When a child logger emits a record that has passed the child's level, JUL forwards the record to the parent's handlers without re-checking the parent's level.
- A child logger may disable `useParentHandlers` or use its own handlers, so the root configuration does not directly determine its output.

For example, to view `FINE` on a specific logger through the root handlers:

```java
Logger target = Logger.getLogger("com.example.payment");
target.setLevel(Level.FINE);

Logger root = Logger.getLogger("");
for (java.util.logging.Handler handler : root.getHandlers()) {
    handler.setLevel(Level.FINE);
}
```

This is an **illustrative snippet**, not a recommendation to run verbatim in production. The loop above changes the level of **all handlers attached directly to root**, altering logging in other areas as well. If the target logger disables parent propagation or has other filters, changing root handlers may still not produce the desired result.

In real applications, identify **which handler actually receives the record** and control the right destination, rather than adjusting root across the entire application just to debug one class.

## 8. Changing Levels via Administrative Mechanisms Instead of Modifying Business Code

Many applications need to change levels **after startup** based on operator actions. Several options exist:

### 8.1. JMX for Java Util Logging

The JDK provides `java.lang.management.PlatformLoggingMXBean` to inspect and adjust the levels of named loggers at runtime. Example **illustrative snippet placed inside a method**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.PlatformLoggingMXBean;

PlatformLoggingMXBean bean =
        ManagementFactory.getPlatformMXBean(PlatformLoggingMXBean.class);

if (bean != null) {
    // A logger with the same name must already exist in LogManager.
    bean.setLoggerLevel("com.example.payment", "FINE");

    // Check the level set directly on the logger:
    String level = bean.getLoggerLevel("com.example.payment");
    System.out.println(level);

    // Revert to inheriting level from parent:
    bean.setLoggerLevel("com.example.payment", null);
}
```

This is a logging management API, **not an API for writing a log line**. The `setLoggerLevel` method requires an existing logger name and a valid level name; if the logger does not exist or the level name is invalid, the call may throw `IllegalArgumentException`. The level returned by `getLoggerLevel` reflects the **directly configured** level; an empty string indicates the logger inherits, while `null` may indicate that the logger does not exist.

When exposing this through remote JMX tools, you must enforce authentication, authorization to change configuration, and connection security. Changes via JMX apply to the JVM receiving the command and do not automatically propagate to other JVMs or pods.

### 8.2. Framework Operational Mechanisms

Applications using **SLF4J** typically call a backend-independent logging API. However, SLF4J's common logger API does not provide a standard method such as `setLevel(...)` across all backends. To change levels dynamically, use the mechanism provided by the underlying backend.

For example, with **Logback Classic** (illustrative snippet requiring the corresponding Logback library on the classpath):

```java
org.slf4j.Logger generic =
        org.slf4j.LoggerFactory.getLogger("com.example.payment");

if (generic instanceof ch.qos.logback.classic.Logger logbackLogger) {
    logbackLogger.setLevel(ch.qos.logback.classic.Level.DEBUG);
}
```

Do not cast like this when the actual application uses a different backend; the operation may have no effect or fail a type check. In a Spring Boot application, logging administration via **Spring Boot Actuator** can support viewing/changing log levels dynamically when the `loggers` endpoint is enabled and authorized. Exact invocation, access permissions, and available endpoints must be verified against your application's version and configuration; **never expose a level-changing endpoint to unauthorized users**.

### 8.3. Configuration Management Tools or Internal Admin Commands

An application can proactively expose an administrative operation to update levels at runtime—for example, selecting a logger by name and calling `setLevel` in JUL. When building such a mechanism, you should:

- Maintain an allowlist of loggers permitted to be modified; avoid allowing arbitrary changes to every logger.
- Restrict access to authorized operators only; audit the action and who performed it.
- Limit which levels are allowed in production and how long detailed levels stay enabled.
- Provide a reset button or expiration timeout to **restore the initial value**, including `null`.
- Clearly display differences between the in-memory configuration and the startup configuration.
- If multiple instances exist, apply the change to the intended set of instances; do not assume updating one node is enough.

## 9. Modifying `logging.properties` at Runtime

With JUL, a `logging.properties` file can configure initial log levels, for example:

```properties
handlers=java.util.logging.ConsoleHandler
.level=INFO
java.util.logging.ConsoleHandler.level=INFO
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

com.example.payment.level=FINE
```

Run the JVM with this configuration:

```bash
java -Djava.util.logging.config.file=logging.properties MyApplication
```

Here, `MyApplication` is a startup class name **illustrating an existing application**, not a class provided in this article. `-Djava.util.logging.config.file` is a **JVM system property** pointing to the configuration file path. Relative paths are resolved from the process working directory.

**Editing the file after the JVM has started does not automatically update levels in JUL by default.** To reload via API, JUL provides `LogManager.readConfiguration(...)`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.LogManager;

public static void reloadJulConfiguration(Path file) throws IOException {
    try (InputStream in = Files.newInputStream(file)) {
        LogManager.getLogManager().readConfiguration(in);
    }
}
```

This is an **illustrative method** that must be placed inside a class, with imports at the top of the file. Calling `readConfiguration(InputStream)` reloads the **LogManager** logging configuration and may reset many active properties, levels, filters, or handlers; it is not equivalent to "only changing one logger from INFO to FINE." It has JVM-wide impact and may close or replace managed handlers. Only perform this when you understand the lifecycle and configuration ownership of the entire application.

Libraries or frameworks may provide automatic configuration reloading, but **this is not a general behavior guaranteed by JUL simply by editing the file**. If you use Logback or Log4j2, consult that backend's own reload documentation and configuration; JUL's `logging.properties` file does not necessarily manage that backend's loggers.

## 10. Changing Levels in a Multi-Instance System

Suppose a system has 3 service replicas running in 3 separate JVMs:

```text
Request ──> Load Balancer
             ├── Payment JVM A: INFO
             ├── Payment JVM B: FINE  <- level changed
             └── Payment JVM C: INFO
```

If `setLevel(FINE)` is only called on **JVM B**, detailed records appear on B, while A and C remain at INFO. You cannot conclude that "the entire service has FINE enabled" from the response of a single JVM.

In real-world scenarios, you need to determine:

1. **Scope:** one logger, one package, the entire application, or a subset of instances.
2. **Duration:** how long the temporary change lasts and when it will be reverted.
3. **Persistence:** in-memory changes can be lost after a JVM restart or an automatic configuration reload.
4. **Observing results:** verify on the right instance and the right handler destination; avoid confusing data from other nodes.
5. **Performance impact:** `FINE`/`FINER`/`FINEST` can increase formatting/I/O/CPU work, disk pressure, and log ingestion costs.

If logs are aggregated from multiple instances, attaching `service`, `instance_id`, `request_id`, or `trace_id` helps trace the exact node and request. When debugging in production, prefer a narrow scope and a short duration rather than enabling verbose logs indefinitely.

## 11. Does Changing the Level Affect Performance and Data?

Yes. Although the level-changing API itself is usually simple, the **actual volume of logs emitted** can grow sharply.

**Early logger filtering:** if `isLoggable(Level.FINE)` is false, the logger does not create a record at that level. However, Java evaluates method call arguments before invoking the method. For example:

```java
logger.fine("Payload = " + expensiveSerialize(payload));
```

`expensiveSerialize(payload)` still runs to concatenate the string **even when `FINE` is being filtered out**. This is an illustrative snippet using assumed existing variables/methods. For expensive message construction, guard it:

```java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Payload = " + expensiveSerialize(payload));
}
```

Or use JUL's **Supplier** overload:

```java
logger.log(Level.FINE,
        () -> "Payload = " + expensiveSerialize(payload));
```

String evaluation inside the lambda is deferred until the message actually needs to be formatted. However, lambdas can incur capture overhead, and records still pass through handlers afterward; measure actual impact rather than assuming "logging is free when disabled."

Do not log passwords, tokens, API keys, authentication cookies, sensitive personal data, or full request bodies for debugging. **Enabling `FINE` is not a reason to bypass data-masking rules**. Data may be retained in centralized logging systems longer than the debug window and be visible to many people.

## 12. Common Pitfalls When Changing Levels

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Called `setLevel(FINE)` but `FINE` is not visible | Handler is at `INFO`/`WARNING`; logger has no receiving handler | Check direct handlers, parent chain handlers, propagation, and filters |
| Changed root to `WARNING` but `FINE` still appears | Child logger has an explicit level and root handler allows `FINE` | Check the actual level of the emitting logger and root handlers |
| `getLevel()` returns `null` | Logger inherits its level from parent | Use `isLoggable(...)` and check `getParent()` |
| Edited properties file but logs did not change | JVM has not reloaded configuration | Use an official reload mechanism or administrative API |
| One line appears twice after adding a handler | Both child logger and parent/root logger have handlers | Avoid duplicate attachment or control `useParentHandlers` |
| Logs disappear after calling `setUseParentHandlers(false)` | Child logger has no handler of its own | Attach an appropriate handler or enable propagation |
| Only one pod shows detailed logs | Change was applied only in that JVM/pod | Identify and apply across multiple instances if needed |
| Debug configuration is lost after restart | Level was only changed in RAM | Restore intentionally or put it in startup configuration |
| Enabling `FINE` increases latency or file size | Too many records written; heavy formatting/I/O | Restrict logger scope, duration, and use appropriate sampling/retention |
| Changing level in JUL code does not affect application logs | Application uses SLF4J/Logback/Log4j2 | Check the actual logging backend and use that backend's API |

**Minimal diagnostic check in JUL** (illustrative snippet assuming a `logger` variable exists):

```java
System.out.println("logger=" + logger.getName());
System.out.println("configuredLevel=" + logger.getLevel());
System.out.println("canLogFine=" + logger.isLoggable(Level.FINE));
System.out.println("useParentHandlers="
        + logger.getUseParentHandlers());

for (java.util.logging.Handler handler : logger.getHandlers()) {
    System.out.println("handler="
            + handler.getClass().getSimpleName()
            + " level=" + handler.getLevel());
}
```

`getHandlers()` only returns handlers **attached directly** to the logger being inspected; the logger may still output logs through parent handlers. For full diagnostics, walk `getParent()` up to root if propagation is enabled.

## 13. Safe Debugging Workflow in Production

A practical workflow for Java services using JUL:

1. Record the current level of the logger **and related handlers** before making changes; distinguish an explicitly set level from an inherited level (`null`).
2. Identify the logger or package to investigate, the target instance(s), and the debug time window.
3. Change the **target logger** from `INFO` to `FINE` (or an appropriate level); if records are blocked at a handler, adjust the right handler within permitted scope and privileges.
4. Trigger or observe the relevant requests. Search by request ID/trace ID and confirm logs appear in the expected console/file/backend.
5. Read logs to locate processing milestones, anomalies, and exceptions while avoiding sensitive data collection.
6. **Revert** the logger and handlers to their saved values, including `null` to resume inheritance, as soon as sufficient data is gathered.
7. Confirm log volume returns to normal and record the configuration change in the operations log if applied to production.

In systems with multiple operators, provide an authorized "temporary debug level" action with automatic expiration and auditing of who enabled detailed logging. In distributed applications, when changing multiple instances, clearly record which nodes were updated successfully and verify the result on each node.

## 14. Self-Check Questions

**Question 1:** The logger is at `INFO` and `ConsoleHandler` is at `FINE`; will calling `logger.fine(...)` appear?  
**Answer:** No. The logger filters out `FINE` before the handler receives it.

**Question 2:** The logger is at `FINE` and `ConsoleHandler` is at `WARNING`; will changing only the logger to `ALL` make `FINE` lines appear?  
**Answer:** No. The handler still filters out `FINE`. You must adjust the appropriate handler to see `FINE` on the console.

**Question 3:** Does `logger.setLevel(null)` disable logging?  
**Answer:** No. The logger clears its explicit level and inherits from its parent.

**Question 4:** Does editing `logging.properties` while the JVM is running automatically change thresholds?  
**Answer:** It is not guaranteed and is not JUL's default automatic behavior. An explicit reload/configuration mechanism is required.

**Question 5:** Does enabling `FINE` on one pod enable `FINE` on all pods?  
**Answer:** No. It only changes the JVM that received the command. Other instances must be configured accordingly.

**Question 6:** Why is it important to remember whether the original level was `null` or `INFO`?  
**Answer:** `null` means inheritance, which differs from a fixed `INFO` level. Reverting incorrectly will permanently alter logging behavior when a parent logger's level changes.

**Key takeaway:** In Java, changing the log level at runtime is primarily an operation on an **existing logger** and possibly the **handlers receiving its records**. Understanding inheritance, propagation, and backend configuration helps you enable detailed logs with the right scope, observe the results, and then revert safely.

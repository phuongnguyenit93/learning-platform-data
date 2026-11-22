# JUL Levels in Java: Meaning, Order, and Record Filtering

## 1. JUL and log levels

**Java Util Logging** (commonly called **JUL**) is the built-in logging API in the JDK, located in the `java.util.logging` package. When a program calls `Logger` to record an event, **`Level`** indicates the importance or level of detail of that event. JUL uses levels to decide which records are created and forwarded to destinations such as the console or a file.

For example, a program can log:

```java
logger.info("Ứng dụng đã khởi động");
logger.warning("Bộ nhớ đệm gần đầy");
logger.log(java.util.logging.Level.SEVERE, "Không thể lưu dữ liệu", exception);
```

These are **illustrative** statements, assuming the `logger` variable is a `java.util.logging.Logger` and `exception` is an existing `Throwable` object. An event's level does not guarantee it will appear: the record also passes through the **logger threshold**, **handlers**, and other filters if configured.

Lesson objectives:

- Know all standard levels of `java.util.logging.Level` and their **priority order**.
- Understand the difference between **record level**, **logger level**, and **handler level**.
- Know how to apply levels when writing code, configuring JUL, and checking filtered records.
- Avoid confusing JUL's `FINE/FINER/FINEST` with `DEBUG/TRACE` in other logging backends.

## 2. List of standard JUL levels

Each level in JUL has a **name**, a **numeric value** (accessed via `intValue()`), and an appropriate use case.

| Level | Numeric Value | Common Purpose |
| --- | ---: | --- |
| `SEVERE` | 1000 | Serious failure: the operation cannot complete, functionality is affected. |
| `WARNING` | 900 | Unusual condition or potential error needing attention; the application can continue. |
| `INFO` | 800 | Important operational information such as startup, shutdown, or operation completion. |
| `CONFIG` | 700 | Configuration details useful when diagnosing how the application behaves. |
| `FINE` | 500 | Details for debugging, such as execution branches or sub-calls. |
| `FINER` | 400 | More detailed information, such as steps inside an algorithm. |
| `FINEST` | 300 | Very detailed information, typically for deep investigation. |
| `OFF` | `Integer.MAX_VALUE` | Special value: disables logging at the threshold where it is applied. |
| `ALL` | `Integer.MIN_VALUE` | Special value: allows all normal levels through the threshold. |

The numeric values in order are: `SEVERE=1000`, `WARNING=900`, `INFO=800`, `CONFIG=700`, `FINE=500`, `FINER=400`, and `FINEST=300`. A **larger** numeric value corresponds to **higher severity / less detail**. `ALL` and `OFF` are two special control values, not levels to attach to a normal business event.

You can remember the order as:

```text
More severe / less detail
     SEVERE (1000)
        |
     WARNING (900)
        |
       INFO (800)
        |
      CONFIG (700)
        |
       FINE (500)
        |
      FINER (400)
        |
      FINEST (300)
More detail / typically generates more records
```

**There is no `DEBUG` or `TRACE` among JUL's standard level constants.** Those levels are familiar in SLF4J/Logback or Log4j2, but you cannot write `java.util.logging.Level.DEBUG` or `java.util.logging.Level.TRACE`. Detailed levels in JUL typically use `FINE`, `FINER`, and `FINEST`. Mapping between frameworks depends on the bridge/backend and actual configuration—do not assume every name has an exact one-to-one meaning.

### Event classification examples

| Scenario | Suggested Level | Reason |
| --- | --- | --- |
| Application started successfully | `INFO` | Important lifecycle event. |
| Which cache mode the configuration uses | `CONFIG` | Helps with diagnostics but usually not needed in daily operational logs. |
| Retrying because an external service returned a temporary error | `WARNING` | Anomaly to monitor; the entire operation has not necessarily failed. |
| Required request aborted due to an unrecoverable error | `SEVERE` | Significant operation failure. |
| Selecting a pricing calculation branch | `FINE` | Details for debugging. |
| Tracing each step / intermediate value of an algorithm | `FINER` or `FINEST` | Enable only when deep investigation is needed. |

These are **practical conventions**; there is no rigid rule forcing every `IOException` to be `SEVERE` or every `IllegalArgumentException` to be `WARNING`. Choose the level based on the **impact of the event in its processing context**.

## 3. How does a level threshold work?

A level set on a logger/handler acts as a **minimum threshold**. For normal levels, if the record's numeric value is **greater than or equal to** the threshold, it can pass the level filter.

For example, with threshold `INFO=800`:

- `SEVERE=1000`: allowed.
- `WARNING=900`: allowed.
- `INFO=800`: allowed.
- `CONFIG=700`, `FINE=500`, `FINER=400`, `FINEST=300`: filtered out.

A threshold of `FINE=500` allows `FINE`, `CONFIG`, `INFO`, `WARNING`, and `SEVERE`, while still filtering out `FINER` and `FINEST`.

| Threshold | Normal levels that can pass |
| --- | --- |
| `SEVERE` | Only `SEVERE` |
| `WARNING` | `WARNING`, `SEVERE` |
| `INFO` | `INFO`, `WARNING`, `SEVERE` |
| `CONFIG` | `CONFIG`, `INFO`, `WARNING`, `SEVERE` |
| `FINE` | `FINE`, `CONFIG`, `INFO`, `WARNING`, `SEVERE` |
| `FINER` | Same as above, plus `FINER` |
| `FINEST` | All seven normal levels |
| `ALL` | Allows all levels at the level filter |
| `OFF` | Allows no records through the level filter |

There is a technical exception to remember: `OFF` and `ALL` have **special** handling, so do not rely on simple numeric comparison to reason about every case. In application code, check using the `logger.isLoggable(level)` API instead of comparing `intValue()` manually.

## 4. Distinguishing record, logger, and handler levels

The three components use levels in different roles:

- **Record level**: the level passed to `logger.log(Level.FINE, ...)` or via a shorthand method such as `logger.info(...)`.
- **Logger level**: the threshold for the logger to decide whether to emit the record.
- **Handler level**: an independent threshold for the output destination (console/file/...) to decide whether to accept the record.

Basic processing flow:

```text
logger.fine("Loading cache")
          |
          v
Does logger level allow FINE?
          |
       No | Yes
        X |----> LogRecord(level=FINE)
                       |
                       v
              ConsoleHandler / FileHandler
                       |
                       v
               Does handler allow FINE?
                    No | Yes
                     X |----> Formatter ---> Console / File
```

The table below assumes no additional filter is present and the handler actually receives the record:

| Logger level | Handler level | Logging `FINE` | Result at handler |
| --- | --- | --- | --- |
| `INFO` | `ALL` | `logger.fine(...)` | Blocked at logger. |
| `FINE` | `INFO` | `logger.fine(...)` | Logger passes it, handler blocks it. |
| `FINE` | `FINE` | `logger.fine(...)` | Record can be emitted. |
| `ALL` | `WARNING` | `logger.info(...)` | Handler blocks INFO. |
| `WARNING` | `ALL` | `logger.severe(...)` | SEVERE can be emitted. |
| `OFF` | `ALL` | `logger.severe(...)` | Logger does not emit the record. |

Therefore, **`logger.setLevel(Level.FINE)` does not guarantee that `FINE` records will appear**. If `ConsoleHandler` is still at `INFO`, the record is blocked at the handler. Conversely, lowering only `ConsoleHandler` to `FINE` does not help if the logger is still at `INFO`.

A `Logger` can forward records to a parent logger's handler without necessarily having its own handler. When investigating why a record appears, you need to check **the originating logger, parent–child relationships, `useParentHandlers`, the receiving handlers, handler levels, and filters**.

## 5. Complete Java 17 example: testing multiple levels

This example creates a dedicated JUL logger, attaches a `ConsoleHandler`, and uses a short format for easy inspection. The program changes logger and handler thresholds within a single run to clearly distinguish the two filtering points.

Create `JulLevelsDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class JulLevelsDemo {
    private static final Logger LOG =
            Logger.getLogger(JulLevelsDemo.class.getName());

    public static void main(String[] args) {
        // Save the current configuration to restore after the example.
        Level oldLevel = LOG.getLevel();
        boolean oldParents = LOG.getUseParentHandlers();
        Handler[] oldHandlers = LOG.getHandlers();

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.ALL);
        console.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        for (Handler old : oldHandlers) {
            LOG.removeHandler(old);
        }
        LOG.setUseParentHandlers(false);
        LOG.addHandler(console);

        try {
            // 1. Logger INFO, handler ALL.
            LOG.setLevel(Level.INFO);
            LOG.fine("Hidden by logger");
            LOG.info("Service started");
            LOG.warning("Slow dependency");

            // 2. Logger FINE, handler WARNING.
            LOG.setLevel(Level.FINE);
            console.setLevel(Level.WARNING);
            LOG.fine("Hidden by handler");
            LOG.warning("Retry scheduled");

            // 3. Both logger and handler allow FINE.
            console.setLevel(Level.FINE);
            LOG.fine("Cache key computed");
            LOG.config("Cache mode configured");

            // 4. OFF blocks records at the logger.
            LOG.setLevel(Level.OFF);
            LOG.severe("Hidden because logger is OFF");
        } finally {
            LOG.removeHandler(console);
            console.close();

            LOG.setLevel(oldLevel);
            LOG.setUseParentHandlers(oldParents);
            for (Handler old : oldHandlers) {
                LOG.addHandler(old);
            }
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac JulLevelsDemo.java
java JulLevelsDemo
```

**Output on `ConsoleHandler`'s stderr stream:**

```text
INFO | Service started
WARNING | Slow dependency
WARNING | Retry scheduled
FINE | Cache key computed
CONFIG | Cache mode configured
```

The lines `Hidden by logger`, `Hidden by handler`, and `Hidden because logger is OFF` do not appear.

**Explanation:**

1. In phase 1, the `INFO`-level logger discards `FINE` before the handler is called. `INFO` and `WARNING` pass through because the handler is set to `ALL`.
2. In phase 2, the `FINE`-level logger accepts `FINE`, but the `WARNING`-level handler discards `FINE`. `WARNING` is still emitted.
3. In phase 3, the handler switches to `FINE`, so both `FINE` and `CONFIG` records pass both thresholds.
4. In phase 4, `Level.OFF` on the logger blocks even the `severe(...)` call.
5. `setUseParentHandlers(false)` prevents records from propagating to the root logger's default handler to avoid duplicate output. The program restores the modified configuration in `finally`.

JUL's `ConsoleHandler` writes to **`System.err`** by default, not `System.out`. Even if a terminal displays both streams together, it is important to know they are separate streams when redirecting or collecting logs. The `Formatter` in this example intentionally omits timestamps; in real applications, timestamps, logger names, context, and exceptions are usually essential.

## 6. Key Level APIs

### 6.1. Using logging methods

JUL provides convenience methods for common levels:

```java
logger.severe("Cannot connect to primary database");
logger.warning("Retrying operation");
logger.info("Application ready");
logger.config("Using in-memory cache");
logger.fine("Selecting query plan");
logger.finer("Entering helper method");
logger.finest("Visited state 42");
```

These are **illustrative snippets** requiring a `logger` variable already declared in the class/method. Equivalently, you can use the general method:

```java
logger.log(Level.WARNING, "Retrying operation");
logger.log(Level.FINE, "Selecting query plan");
```

The method `logger.log(Level.SEVERE, message, throwable)` also accepts the full `Throwable` so the formatter can print the stack trace; do not just concatenate `throwable.getMessage()` when detailed error information is needed.

### 6.2. Checking the threshold before logging

`Logger.isLoggable(Level.FINE)` returns whether the logger allows the `FINE` level according to its effective level:

```java
if (logger.isLoggable(Level.FINE)) {
    logger.fine("Calculated subtotal = " + calculateSubtotal());
}
```

This illustrative snippet assumes a `calculateSubtotal()` method exists. This check avoids computing an expensive message when the logger already blocks `FINE`, though it **does not guarantee** that any handler will actually output the record.

Because Java evaluates arguments before calling a method, the code:

```java
logger.fine("Calculated subtotal = " + calculateSubtotal());
```

still calls `calculateSubtotal()` even when `FINE` is filtered at the logger. JUL supports overloads using `Supplier<String>` to construct messages lazily:

```java
logger.log(Level.FINE,
        () -> "Calculated subtotal = " + calculateSubtotal());
```

In this example, the lambda body is evaluated only when the logger accepts the level. However, a handler can still filter the record afterward; `Supplier` does not guarantee eliminating all overhead. For sensitive content, you must still control what values are logged, even at `FINEST`.

### 6.3. Inspecting level names and numeric values

`Level.getName()` returns the name (for example `"WARNING"`), and `intValue()` returns the numeric value. `Level.parse(String)` parses a registered level name or valid numeric representation.

```java
import java.util.logging.Level;

public class JulLevelValues {
    public static void main(String[] args) {
        System.out.println(Level.WARNING.getName());
        System.out.println(Level.WARNING.intValue());
        System.out.println(Level.parse("FINE") == Level.FINE);
    }
}
```

Compile and run:

```bash
javac JulLevelValues.java
java JulLevelValues
```

**Exact stdout output:**

```text
WARNING
900
true
```

When handling untrusted configuration strings, catch `IllegalArgumentException` for invalid level names—for example, `Level.parse("DEBUG")` in standard JUL does not recognize a `DEBUG` constant and will throw unless a custom level with that name has been registered. If a project registers custom levels by subclassing `Level`, the set of names can differ; do not assume every application only has the exact names in the standard level table.

## 7. Directly set levels, inherited levels, and the root logger

JUL loggers can have parent–child relationships. Calling `setLevel(null)` on a logger means it **has no explicit threshold of its own** and will **inherit its effective level from the nearest parent** with a concrete level, ultimately often the root logger.

Illustrative example inside a method:

```java
Logger parent = Logger.getLogger("com.example.payment");
Logger child = Logger.getLogger("com.example.payment.PaymentService");

parent.setLevel(Level.WARNING);
child.setLevel(null); // Inherits from parent.
System.out.println(child.getLevel());                  // null
System.out.println(child.isLoggable(Level.INFO));      // false
System.out.println(child.isLoggable(Level.SEVERE));    // true

child.setLevel(Level.FINE); // Has its own threshold.
System.out.println(child.isLoggable(Level.FINE));      // true
```

This snippet is **not a standalone Java file**; place it inside `main` with `java.util.logging.Level` and `Logger` imports to run it. Because the code creates `parent` before `child` and sets its level, `child` has the parent named `com.example.payment` in this example. `getLevel() == null` **does not mean OFF**: it only indicates the logger inherits its level.

If an intermediate logger does not yet exist, a logger with a long name may have the root logger as its direct parent. Therefore, to inspect the actual relationship, use `getParent()` rather than assuming from the dots in the logger name.

### Root level and root handlers

The JUL root logger has the empty string name `""`:

```java
Logger root = Logger.getLogger("");
root.setLevel(Level.INFO);
```

Changing the root level affects child loggers **currently inheriting from root**, but does not override explicit levels set on individual loggers. One important point: once a child logger creates a log record and forwards it to a parent/root logger's handler, JUL **does not re-check the parent logger's level**; each handler still checks its own level and filter.

Example:

- Root logger is `WARNING`.
- Child logger has an explicit level of `FINE`.
- Root's handler is set to `FINE`.
- Child logger has `useParentHandlers` enabled and is not blocked along the path to root.

Result: the child logger's `FINE` record **can still be emitted** through the root handler, even though the root logger's level is `WARNING`. Learners often mistakenly assume that root `WARNING` will always block `FINE` from all child loggers.

By default, a child logger forwards records to its parent via `useParentHandlers=true`. If both the child logger and root have console-writing handlers attached, a single record may appear twice. When you want a child logger to use its own handler exclusively, call `setUseParentHandlers(false)`, but make sure the child logger has a handler attached; otherwise records may not reach any destination.

## 8. Configuring levels via logging.properties

When an application uses JUL, levels can be configured **at JVM startup** instead of calling `setLevel(...)` in source code.

Create `logging.properties`:

```properties
# Console handler attached to the root logger.
handlers = java.util.logging.ConsoleHandler

# Default level for loggers inheriting from root.
.level = INFO

# Handler has its own threshold.
java.util.logging.ConsoleHandler.level = FINE
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter

# Only this package logger logs down to FINE.
demo.jul.level = FINE
```

Create `JulConfigDemo.java` in the same directory:

```java
import java.util.logging.Logger;

public class JulConfigDemo {
    private static final Logger LOG = Logger.getLogger("demo.jul");

    public static void main(String[] args) {
        LOG.info("Service started");
        LOG.fine("Diagnostic detail");
    }
}
```

Compile and run:

```bash
javac JulConfigDemo.java
java -Djava.util.logging.config.file=logging.properties JulConfigDemo
```

`SimpleFormatter` typically prints both **INFO** and **FINE** records to the console (along with date/time, logger name, and thread/source depending on the format), because:

- `demo.jul.level=FINE` allows logger `demo.jul` to create `FINE` records.
- `ConsoleHandler.level=FINE` allows the root handler to output `FINE`.
- Root level `INFO` serves as the default inherited threshold; it does not re-filter `FINE` when a record from a child logger is forwarded to the root handler.

Do not compare `SimpleFormatter`'s console output verbatim with the example in section 5, because `SimpleFormatter` includes timestamps and other fields. If you remove `demo.jul.level=FINE`, the demo logger inherits root `INFO` and **does not emit `FINE` records**. If you change `ConsoleHandler.level` to `INFO`, `FINE` logs are accepted by the logger but **do not appear on the console**.

`-Djava.util.logging.config.file` is a JVM system property pointing to the configuration file. With a relative path, the JVM reads from the working directory at runtime. **Editing the file** after the JVM has started **does not automatically update** JUL unless a reload operation or management mechanism is configured; a runtime level change via `Logger.setLevel(...)` also does not persist across restarts unless recorded in the startup configuration.

**Framework note:** Spring Boot typically logs through SLF4J and a backend such as Logback. Properties like `java.util.logging.ConsoleHandler.level` only control JUL handlers and do not configure loggers of other backends. Identify the actual backend and bridges before changing levels.

## 9. Changing levels at runtime and null values

JUL allows changing levels in a running JVM:

```java
Logger payment = Logger.getLogger("com.example.payment");

Level previousLevel = payment.getLevel();
try {
    payment.setLevel(Level.FINE);  // Temporarily enable detailed logging.
    // Perform the operation to observe.
} finally {
    payment.setLevel(previousLevel); // Restore, including null.
}
```

This is an **illustrative snippet**. In a multithreaded application, changing a shared logger can affect other concurrent requests at the same time. Restrict who has permission to change levels, the logger scope, how long detailed logging stays enabled, and where the data is sent. If an application runs across multiple JVMs, changing a level in one JVM **does not propagate automatically** to other JVMs.

Note: `getLevel()` returns the **directly set** level, which may be `null` when inherited. Restoring `null` is important: forcing every logger back to `INFO` after debugging can accidentally break level inheritance from parent loggers.

Adjust specific loggers by package/class rather than switching the entire root logger to `FINEST` by default. Widening detail too broadly increases record volume, I/O overhead, storage usage, and the risk of logging sensitive data.

## 10. Levels in exception logging

You can pass the full `Throwable` to JUL:

```java
try {
    saveOrder();
} catch (java.io.IOException exception) {
    logger.log(Level.SEVERE, "Cannot save order", exception);
}
```

This illustrative snippet assumes `saveOrder()` is an existing method and `logger` is a `Logger`. `SEVERE` is appropriate if a required operation fails with no remaining fallback. If the application has a fallback and will retry normally, `WARNING` or `INFO` may be more reasonable depending on the case.

Passing `Throwable` as an argument to `log(Level, String, Throwable)` preserves the exception in the `LogRecord`. Whether the stack trace is visible depends on the formatter: `SimpleFormatter` prints exceptions, whereas a custom formatter that only reads `record.getMessage()` may drop the stack trace. The level itself does not decide whether stack trace frames are printed.

Avoid calling both `exception.printStackTrace()` and `logger.log(..., exception)` for the same error at the same boundary without a clear reason; doing so creates duplicate logs. For genuine error conditions, pick an appropriate level and record enough safe context for investigation.

## 11. Cost and security when choosing levels

Enabling `FINE`, `FINER`, and `FINEST` helps with troubleshooting but has costs:

- More log records increase CPU usage, formatting work, and I/O.
- Log files can grow rapidly without rotation/retention.
- Centralized log collection systems may charge by volume; excessive logging makes important events harder to find.
- Debug content may accidentally include API keys, tokens, auth cookies, personal data, or SQL statements with sensitive parameters.

Do not put passwords, tokens, or sensitive user content into log messages, even at `FINEST`. Log levels are not a data access control mechanism. Protect the log creation points, formatters, and read permissions on log storage systems.

For performance, it is generally beneficial to short-circuit expensive message construction early, for example using `isLoggable` or the `Supplier<String>` overload. However, log-building logic should not have essential side effects: when the level is filtered out, the supplier may not run.

## 12. Common issues and how to check them

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `logger.fine(...)` does not appear | Logger is at INFO/WARNING; handler is at INFO; another filter | Check `logger.isLoggable(Level.FINE)`, handler level, propagation, and filters. |
| Changed logger to ALL but still no FINEST | Handler only accepts INFO or WARNING | Adjust the appropriate handler if you want to see FINEST. |
| `logger.getLevel()` returns null | Logger inherits level from parent | Do not treat null as OFF; check `getParent()` and `isLoggable(...)`. |
| Changed root level but one logger still emits FINE | Child logger has an explicit level; root handler accepts it | Check the level on the emitting logger and the receiving handler. |
| Same event appears twice | Both child and parent/root loggers have handlers, propagation is on | Use only shared handlers or disable propagation when using a dedicated handler. |
| File log lacks CONFIG while console has it | File handler has a higher level than CONFIG, or a different filter | Check `FileHandler` threshold, formatter, and path. |
| Edited `logging.properties` at runtime but levels didn't change | No automatic reload | Use a reload/management mechanism or restart per procedure. |
| Using `Level.DEBUG` causes a compile error | JUL does not define DEBUG | Choose the corresponding JUL level as needed. |
| Log has message but no stack trace | Only `exception.getMessage()` was logged or formatter ignores `getThrown()` | Pass the full Throwable and use an exception-aware formatter. |
| FINEST produces too many logs | Broad scope configuration and no storage limits | Enable temporarily only on needed loggers; configure rotation, retention, and revert afterward. |

### Checklist for diagnosing a missing record

1. Confirm whether the application uses `java.util.logging.Logger` or another backend.
2. Confirm the logger **emitting** the record: logger name and directly set level.
3. Check the effective level via `logger.isLoggable(targetLevel)`, remembering inheritance if `getLevel() == null`.
4. Check handlers attached directly (`logger.getHandlers()`) and parent logger handlers if `getUseParentHandlers()` is enabled.
5. Check `handler.getLevel()`, filters, formatters, and write capability to console/file.
6. Verify that the record is actually created on the executed code path, then confirm whether the collection system retains the data.

`logger.getHandlers()` only returns handlers attached **directly** to the called logger; an array length of 0 is **not enough** to conclude there is no output destination, because records can propagate up to root.

## 13. Self-check questions

**Question 1.** Logger is at INFO; ConsoleHandler is at ALL. Will `logger.fine(...)` appear on the console?

**Answer:** No. The INFO logger discards FINE before the handler receives it.

**Question 2.** Logger is at FINE; FileHandler is at INFO. Will `logger.config(...)` be written to the file?

**Answer:** No. CONFIG=700 meets the FINE=500 threshold at the logger, but is lower than INFO=800 at the FileHandler.

**Question 3.** To observe `FINER`, what minimum level should be chosen on both the logger and handler?

**Answer:** `FINER` or a more detailed level (`FINEST`/`ALL`), provided no other filter blocks it and the handler actually receives the record.

**Question 4.** Does `logger.setLevel(null)` disable logging?

**Answer:** No. It causes the logger to inherit its level from the nearest parent with a defined level.

**Question 5.** Why can a child logger's FINE record still appear through the root handler when the root logger is at WARNING?

**Answer:** The child logger can have its own explicit FINE level and emit the record. Once the record is forwarded upward, JUL does not re-check the root logger's level; the root handler decides based on its own level and filter.

**Question 6.** How is `CONFIG` filtered at an `INFO` threshold?

**Answer:** It is filtered out because CONFIG=700 is less than INFO=800. Lower the threshold to CONFIG or FINE/FINER/FINEST/ALL if you want to see CONFIG.

**Question 7.** Should full FINEST logging be kept enabled long-term in production?

**Answer:** Usually not. Enable it only on the area being debugged for a short time, control sensitive data and storage volume, and then restore the original threshold.

**Key takeaway:** JUL has seven normal levels **SEVERE → WARNING → INFO → CONFIG → FINE → FINER → FINEST**, plus **OFF** and **ALL**. A record's level must pass the **logger threshold**, and then the **handler threshold**. Level inheritance and forwarding records through parent loggers are two separate mechanisms; understanding both is essential for controlling logs accurately.

# Root Logger in Java

## 1. What is the Root Logger?

In the JDK's **Java Util Logging (JUL)** mechanism, the **root logger** is the logger at the top of the logger hierarchy. The root logger has **the empty string `""` as its name** and **no parent logger**. Named loggers in the JUL system generally trace back through parent–child relationships to the root logger.

A logger is used to emit event records; handlers receive records, filter them, and send them to the console, a file, or another destination. The root logger has two special roles:

1. **Configuration inheritance point**: a child logger without its own level set can inherit its level from the nearest ancestor logger with a defined level, ultimately falling back to the root.
2. **Destination for propagated records**: when `useParentHandlers` is enabled, records emitted by a child logger can be forwarded to the handlers of parent loggers, including the root.

This organization allows an application to configure common log levels and handlers in one place instead of configuring every class individually.

> The scope of this article is `java.util.logging` in Java 17+. Other logging backends such as Logback/Log4j2 also have the concept of a root logger, but they use their own APIs and configuration syntax; do not mechanically apply every JUL command to those frameworks.

## 2. How to Access the Root Logger

You can obtain the root logger via `LogManager` or the empty name:

```java
import java.util.logging.LogManager;
import java.util.logging.Logger;

Logger root = LogManager.getLogManager().getLogger("");
Logger sameRoot = Logger.getLogger("");

System.out.println(root == sameRoot);         // true
System.out.println(root.getName().isEmpty()); // true
System.out.println(root.getParent() == null); // true
```

This is an **illustrative snippet** and needs to be placed inside a method such as `main` to run. The root logger's name is `""`, not the string `"root"`. Calling `Logger.getLogger("root")` creates or looks up a *named* logger called `root`, rather than retrieving the JUL root logger.

### Root Logger vs. Global Logger

JUL also has a global logger accessed via `Logger.getGlobal()`. Its name is `"global"`, and **it is not the root logger**:

```java
Logger global = Logger.getGlobal();
Logger root = Logger.getLogger("");

System.out.println(global.getName()); // global
System.out.println(global == root);   // false
```

The global logger is a *named* logger for shared use when you do not want to create a separate logger per class. The root logger serves a foundational role in the logger tree. The two terms "global" and "root" are not interchangeable.

## 3. Logger Tree and Parent–Child Relationships

Logger names typically follow package/class names, such as `com.example.order.OrderService`, `com.example.order`, and `com.example`. Dots represent the **name** hierarchy, but the actual parent relationship depends on which loggers have been created and registered in `LogManager`.

Illustrative example when all intermediate loggers exist:

```text
Root Logger (name "")
└── com
    └── com.example
        └── com.example.order
            └── com.example.order.OrderService
```

If only `com.example.order.OrderService` is created without `com`, `com.example`, or `com.example.order`, its direct parent may be **root**, rather than a non-existent intermediate logger. When an intermediate logger is created later, JUL can adjust the parent–child relationships. Therefore, you should not infer the parent logger merely by splitting the name string; use `logger.getParent()` to observe the actual relationship.

A common JUL setup:

```java
import java.util.logging.Logger;

Logger orderLogger =
        Logger.getLogger("com.example.order.OrderService");

Logger parent = orderLogger.getParent();
System.out.println(parent.getName());
```

The result depends on which loggers are currently present in the same `LogManager`. In a small program that only registers a single long-named logger, `parent.getName()` is usually the empty string (root).

## 4. Level Inheritance from the Root Logger

Each logger can have its own level set with `setLevel(...)`. If a logger is set with `setLevel(null)`, it **inherits its effective level** from the nearest ancestor logger that has a non-null level. The root logger is the end of the inheritance chain. The common default when JUL initializes with the JDK configuration is `INFO` on root, though the system can change this level via a configuration file or in code.

JUL levels in order from most severe to most detailed:

```text
SEVERE > WARNING > INFO > CONFIG > FINE > FINER > FINEST
```

`ALL` enables all levels and `OFF` disables logging; these are special control values. For a logger inheriting the `WARNING` level:

- `logger.severe(...)` and `logger.warning(...)` are allowed to create log records.
- `logger.info(...)` and `logger.fine(...)` are filtered out right at the logger.
- If a child logger sets `Level.FINE` on its own, it can still emit `FINE` regardless of root remaining at `WARNING`.

You can check the directly configured level using `getLevel()`. A value of **`null` does not mean logging is disabled**; it means the inherited level is used. To determine whether a specific level can pass the logger's filter, use `isLoggable(level)`:

```java
Logger logger = Logger.getLogger("com.example.order");
logger.setLevel(null); // Allow inheriting level from parent.

boolean allowFine = logger.isLoggable(java.util.logging.Level.FINE);
```

The snippet above checks the decision at the **logger**; even if it returns `true`, a handler can still filter out the record before writing it to the destination.

## 5. How Records Travel from a Child Logger to Root

This is the most important part when distinguishing between **logger level** and **handler level**.

A record is conceptually processed as follows:

```text
orderLogger.log(FINE, "...")
  │
  ├─ Check orderLogger's level/filter
  │   ├─ Fails → stop, do not emit log record
  │   └─ Passes → emit record
  │
  ├─ Handlers attached directly to orderLogger
  │   └─ Handler checks its own level/filter
  │
  └─ If useParentHandlers=true
      └─ Nearest parent logger's handlers
          └─ ... continues up to root's handlers
```

**An easily misunderstood detail:** once a record passes the filter at the originating logger, JUL forwards the record to parent loggers' handlers **without re-checking the level or filter of each parent logger**. Each handler still checks its own level and filter.

For example: the root logger is set to `WARNING`, the `com.example.order` logger is set to **`FINE`**, and the root's handler is set to `FINE`. A `FINE` record from the child logger can still appear through the root handler because the child logger accepted it; root's `WARNING` level is not re-applied during propagation.

Conversely, if the root's handler only accepts `INFO`, a `FINE` record from the child logger will be discarded by the handler. Adjusting **only the root level** does not mean you have configured the log verbosity of all child loggers.

### Scenario Table

| Effective level at emitting logger | Root logger level | Root handler level | Emitted record | Result at root handler |
| --- | --- | --- | --- | --- |
| `WARNING` (inherited from root) | `WARNING` | `ALL` | `INFO` | Does not reach handler: filtered by emitting logger |
| `WARNING` (inherited from root) | `WARNING` | `ALL` | `WARNING` | Displayed |
| `FINE` (explicitly set) | `WARNING` | `FINE` | `FINE` | Displayed when parent propagation is enabled |
| `FINE` (explicitly set) | `WARNING` | `INFO` | `FINE` | Discarded by root handler |
| `FINE` (explicitly set) | `WARNING` | `ALL` | `FINE` | Does not reach root if `useParentHandlers=false` on emitting logger |

The table assumes no additional filters, normal handler operation, and that propagation to root is not blocked at an intermediate logger.

## 6. Runnable Java 17 Example: Root Level, Inheritance, and Handlers

This example intentionally creates **a standalone runnable program** for consistent results: it saves the current root configuration, temporarily removes existing handlers, attaches a `ConsoleHandler` with a short format, runs three checks, and then restores the configuration in `finally`.

Create `RootLoggerDemo.java`:

```java
import java.util.logging.ConsoleHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogManager;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RootLoggerDemo {
    public static void main(String[] args) {
        Logger root = LogManager.getLogManager().getLogger("");
        Logger global = Logger.getGlobal();
        Logger child = Logger.getLogger("course.logging.orders");

        // Prove that root is different from the global logger.
        System.out.println("rootNameEmpty=" + root.getName().isEmpty());
        System.out.println("rootParentNull=" + (root.getParent() == null));
        System.out.println("globalIsRoot=" + (global == root));

        // Save initial state to restore after the example.
        Handler[] savedHandlers = root.getHandlers();
        Level savedRootLevel = root.getLevel();
        Level savedChildLevel = child.getLevel();
        boolean savedPropagation = child.getUseParentHandlers();

        ConsoleHandler demoHandler = new ConsoleHandler();
        demoHandler.setLevel(Level.ALL);
        demoHandler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });

        try {
            // Temporarily remove default handlers to avoid duplicate lines.
            for (Handler handler : savedHandlers) {
                root.removeHandler(handler);
            }
            root.addHandler(demoHandler);
            root.setLevel(Level.WARNING);

            child.setUseParentHandlers(true);
            child.setLevel(null); // Inherit WARNING from root.
            child.info("Hidden INFO"); // Filtered out at child.
            child.warning("Inherited WARNING");

            child.setLevel(Level.FINE); // Override inherited level.
            child.fine("Explicit FINE from child");
        } finally {
            // Restore modified configurations.
            child.setLevel(savedChildLevel);
            child.setUseParentHandlers(savedPropagation);
            root.setLevel(savedRootLevel);
            root.removeHandler(demoHandler);
            demoHandler.close();
            for (Handler handler : savedHandlers) {
                root.addHandler(handler);
            }
        }
    }
}
```

Run from the directory containing the file:

```bash
javac RootLoggerDemo.java
java RootLoggerDemo
```

**Output on `stdout`:**

```text
rootNameEmpty=true
rootParentNull=true
globalIsRoot=false
```

**Log lines on `stderr` from `ConsoleHandler`:**

```text
WARNING | Inherited WARNING
FINE | Explicit FINE from child
```

There is no `Hidden INFO` line. In a terminal, `stdout` and `stderr` usually appear together; if a tool merges both streams, the exact ordering between streams is not strictly guaranteed.

### Why Does This Happen?

1. `child.setLevel(null)` makes `child` inherit `WARNING` from root, because this standalone program creates no intermediate loggers between `course.logging.orders` and root.
2. `child.info(...)` is filtered out before creating a log record; no handler receives it.
3. `child.warning(...)` is accepted by `child` and forwarded to the root's handler.
4. `child.setLevel(Level.FINE)` allows `child` to emit a `FINE` record. Even though root remains at `WARNING`, JUL does not re-apply the root level when forwarding the record to the root handler.
5. `demoHandler.setLevel(Level.ALL)` accepts `FINE`, so this line appears.

Modifying global configuration is only appropriate when running **in isolation for learning and experimentation**. In an application or multi-component test suite, changing the root level/handlers can affect every logger using JUL. You should normally configure it once at application startup and avoid changing root between requests. When you only need to control a specific area of code, prefer configuring the package/class-named logger and its corresponding handler.

## 7. Configuring the Root Logger with logging.properties

JUL supports configuration via a `logging.properties` file. The root logger is represented by a **leading dot in the property name** (e.g., `.level`), while the `handlers` property declares the root's handlers in JUL configuration.

Create `logging.properties`:

```properties
# Handler attached to the root logger
handlers=java.util.logging.ConsoleHandler

# Root logger only accepts WARNING when child loggers inherit
.level=WARNING

# Handler can still output FINE from a child logger that explicitly sets FINE
java.util.logging.ConsoleHandler.level=FINE
java.util.logging.ConsoleHandler.formatter=java.util.logging.SimpleFormatter

# Set a specific level for the business logger
course.logging.orders.level=FINE
```

Create `RootConfigDemo.java`:

```java
import java.util.logging.Logger;

public class RootConfigDemo {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger("course.logging.orders");

        logger.fine("Order lookup started");
        logger.info("Order lookup completed");
    }
}
```

Compile and specify the configuration **at JVM startup**:

```bash
javac RootConfigDemo.java
java -Djava.util.logging.config.file=logging.properties RootConfigDemo
```

With this configuration, both `FINE` and `INFO` from `course.logging.orders` can appear on the console, even though `.level=WARNING`. Reason: the child logger has its own `level=FINE` and the root handler has `level=FINE`. Actual output from `SimpleFormatter` also includes date/time, logger name, and other metadata, so it does not have fixed single-line formatting like the formatter in the first example.

If you remove `course.logging.orders.level=FINE`, the child logger inherits root's `WARNING`: both `FINE` and `INFO` will be filtered out at the logger, even though the console handler still accepts `FINE`. If you change the handler level to `WARNING`, neither record is displayed either because the handler filters them after the logger emits them.

**Note:** Declaring `handlers` on root in `logging.properties` is specific to JUL. If a Spring Boot project uses SLF4J/Logback, levels and appenders are typically configured in `application.properties`/`application.yml` and Logback configuration. The Logback root logger is not managed by JUL's `LogManager` in this way unless a bridge/integration is explicitly configured.

## 8. useParentHandlers and Duplicate Logs

By default, named loggers allow forwarding records to parent loggers via `getUseParentHandlers() == true`. When **both the child and root** have console handlers attached, a single event can be printed twice:

```text
Logger OrderService
   ├─ OrderService's ConsoleHandler → prints once
   └─ forwards to Root Logger
       └─ root's ConsoleHandler    → prints a second time
```

This is not because `logger.info(...)` was called twice, but because two handlers receive the same `LogRecord`. There are two common ways to handle this:

**Approach A — Use the shared root handler.** Do not attach separate handlers to each child logger. Leave parent propagation enabled and use the root configuration for shared log destinations:

```java
Logger logger = Logger.getLogger("com.example.order");
logger.setUseParentHandlers(true);
logger.info("Order submitted");
```

**Approach B — Child logger manages its own destination.** If a child logger needs a dedicated handler, disable forwarding to parents when you want to avoid duplicates:

```java
Logger logger = Logger.getLogger("com.example.order");
logger.setUseParentHandlers(false);
// Must attach an appropriate handler to this logger before expecting
// logs to be displayed or saved.
```

Do not call `setUseParentHandlers(false)` and forget to attach a dedicated handler; in that case, the logger can create events with no destination to receive them, causing logs to "disappear".

**Do not confuse with level inheritance:** disabling `useParentHandlers` only prevents **forwarding records to parent handlers**. A logger with `getLevel() == null` can still **inherit its level from its parent**. These two mechanisms are independent.

If there are multiple logger levels, disabling propagation on an intermediate logger can block records from reaching higher-level handlers; when diagnosing duplicate or missing logs, inspect the actual chain from the emitting logger up to root.

## 9. When Should You Change the Root Logger?

### Reasonable Scenarios

- **Small command-line programs:** use a shared root configuration to send all JUL logs to the console.
- **Applications using JUL consistently:** use root to apply default settings across components, then override the level of specific packages that need debugging.
- **Application startup:** configure handlers for console/file/collector once during bootstrap.
- **Temporary debugging:** lower the threshold of the handler and relevant loggers to inspect `FINE`, then revert to avoid excessive logging.

### Risks to Avoid

1. **Increasing verbosity on root too broadly:** inheriting packages and libraries can generate a huge volume of logs. Target a specific logger for debugging whenever possible.
2. **Changing only the logger level and forgetting the handler:** `FINE` records are still filtered out by a handler set to `INFO` or `WARNING`.
3. **Changing only the root level and thinking all child loggers are blocked:** loggers with their own explicit level can still emit logs, and the root handler can still receive them.
4. **Adding handlers to root on every request/test run:** can cause duplicate logs, open many files, and leak resources. Configure handlers according to the application lifecycle.
5. **Modifying global handlers while multiple threads are logging:** can alter the observable behavior of other threads. Initialize in a controlled manner and close handlers you own at the right time.
6. **Closing handlers you do not own:** root's handlers may be in use by other components; avoid calling `close()` indiscriminately on shared handlers.
7. **Confusing JUL with SLF4J/Logback:** JUL's root and Logback's root are different objects/mechanisms. Identify the active logging backend before changing configuration.
8. **Logging sensitive information:** overly verbose root configuration can leak tokens, authentication headers, or user data into logs. Restrict logged fields and access permissions at the source.

## 10. How to Diagnose Missing Logs

When `logger.info(...)` or `logger.fine(...)` does not appear as expected, check in this order:

1. **Which logger is it?** Read `getName()` and `getParent()` to determine its position in the actual hierarchy.
2. **Does the logger accept the level?** Use `isLoggable(Level.FINE)`. If `getLevel()==null`, trace the inherited level from its parent.
3. **Are logs propagated to the parent?** Check `getUseParentHandlers()` and any intermediate loggers.
4. **Do handlers exist?** Inspect `getHandlers()` on the emitting logger, its ancestors, and root.
5. **Does the handler accept the level/filter?** A record can be discarded by a handler even after the logger accepted it.
6. **Can the handler write to its destination?** `ConsoleHandler` typically uses `System.err`; `FileHandler` is also affected by file path, write permissions, rotation, and log collectors.
7. **Is another configuration or bridge interfering?** Logging libraries, JVM options, or deployment environments can change levels, handlers, or destinations.

A few helpful debug expressions (illustrative snippet placed in a method with a `logger` variable):

```java
System.out.println("name = " + logger.getName());
System.out.println("level = " + logger.getLevel()); // null = inherited
System.out.println("parent = " +
        (logger.getParent() == null
                ? "(none)" : logger.getParent().getName()));
System.out.println("parentHandlers = " + logger.getUseParentHandlers());
System.out.println("canLogFine = " + logger.isLoggable(Level.FINE));
```

`getHandlers()` only lists handlers attached **directly** to the logger it is called on; it does not automatically return all handlers inherited from parents. Therefore, seeing `logger.getHandlers().length == 0` is not enough to conclude the logger has no output destination: records can still reach the root's handlers when propagation is enabled.

## 11. Self-Check Questions

**Question 1:** Is the JUL root logger named `"root"` or `""`?  
**Answer:** The empty string `""`. `Logger.getLogger("root")` is a regular named logger, distinct from root.

**Question 2:** Is `Logger.getGlobal()` the root logger?  
**Answer:** No. The global logger is named `global`; the root logger has an empty name and no parent.

**Question 3:** Root is at level `WARNING`. A child logger is set to `FINE`, the root handler is also `FINE`, and parent propagation is enabled. Will `FINE` logs from the child appear on the console?  
**Answer:** Yes, they can. JUL does not re-check the root logger's level when forwarding records from a child to the root's handler; if the handler accepts it and no other filter blocks it, the record is output.

**Question 4:** Does calling `setUseParentHandlers(false)` stop a child logger from inheriting the root level?  
**Answer:** No. It only controls forwarding records to parent handlers, not level inheritance.

**Question 5:** An `INFO` record appears twice after adding a `ConsoleHandler` to a child logger. What should you check?  
**Answer:** Directly attached handlers and handlers on the parent/root chain; if both output the same event, use the shared root handler or disable parent propagation for loggers that manage their own handlers.

**Key takeaway:** The JUL root logger is the top of the hierarchy with the name `""`. It provides the default level for loggers that have not overridden it and receives records propagated from child loggers. Accurate log control requires considering **the emitting logger's level, parent propagation, and the level/filter on each handler**.

# Per-Module Log Files in Java: Controlled Log Stream Separation

## 1. What Are Per-Module Log Files?

**Per-module log files** are a logging organization approach in which events emitted by different functional components of an application are written to **separate log files**. A "module" in this article usually refers to a **package group, subsystem, or business bounded context**, such as `payment`, `inventory`, `notification`, or `authentication`. It is **not necessarily** a Java Platform Module System (JPMS) module with `module-info.java`.

Instead of sending every event into a single file:

```text
logs/application.log
  INFO  event=payment.started requestId=req-17
  WARN  event=stock.low sku=sku-2
  ERROR event=payment.failed code=UPSTREAM_TIMEOUT
  INFO  event=email.sent notificationId=n-8
```

the application can split them:

```text
logs/
  payment.log
    INFO  event=payment.started requestId=req-17
    ERROR event=payment.failed code=UPSTREAM_TIMEOUT

  inventory.log
    WARN  event=stock.low sku=sku-2

  notification.log
    INFO  event=email.sent notificationId=n-8
```

The lines above are **illustrative**. Actual files may record timestamps, levels, logger names, threads, trace IDs, and stack traces according to the system's formatter/encoder.

### When Is Splitting Files Useful?

- Operations teams need to quickly inspect errors for a specific subsystem without filtering through millions of mixed lines.
- Modules have different **retention**, access permission, or storage frequency requirements.
- Logs from one module are very noisy, making other modules' logs hard to read or increasing storage costs for them.
- A specific group of logs needs to be routed through a dedicated pipeline/collector.
- A large application runs as **a single process** with multiple functional groups and genuinely needs separate physical files.

However, **splitting files does not automatically make logs safer or more efficient**. In many container and cloud environments, a single JSON stream to stdout combined with a `module`/`logger` field for querying in the collector is often simpler and more reliable than creating multiple local files. The decision must be based on operational needs, not on a default assumption that having many packages requires having many files.

### Learning Objectives

After this lesson, you should be able to:

1. Understand the relationship between **Logger name**, Logger hierarchy, and **Handler/Appender**.
2. Distinguish between **filtering logs by module** and **writing files per module**.
3. Use JUL `FileHandler` and Logback `RollingFileAppender` to create dedicated output routes.
4. Understand `useParentHandlers` in JUL and `additivity` in Logback to avoid duplicated or missing logs.
5. Design file naming, rotation, retention, write permissions, charset, and safe log collection.
6. Run a Java 17 program with per-module file output and verify its exact behavior.

## 2. Distinguishing Logger, Handler, Appender, and Log File

A Logger is **not** a log file. A Logger receives a log call, evaluates its level/filter, and then forwards the record to one or more destinations.

In **JUL** (`java.util.logging`):

```text
Logger.getLogger("demo.payment")
           |
           v
     Logger / LogRecord
           |
           v
     FileHandler (payment)
           |
           v
  Formatter + payment.log
```

In **SLF4J + Logback**:

```text
LoggerFactory.getLogger("com.example.payment.PaymentService")
           |
           v
   SLF4J API + Logback Logger
           |
           v
   RollingFileAppender "PAYMENT"
           |
           v
    Encoder + payment.log
```

| Component | JUL | SLF4J + Logback |
| --- | --- | --- |
| Logging call | `java.util.logging.Logger` | `org.slf4j.Logger` |
| Logger group name | `demo.payment`, `demo.inventory` | `com.example.payment`, `com.example.inventory` |
| Output destination | `Handler`, e.g. `FileHandler` | `Appender`, e.g. `RollingFileAppender` |
| Formatting | `Formatter` / `LogRecord` | `Encoder` / `Layout` / logging event |
| Common levels | `INFO`, `WARNING`, `SEVERE`, `FINE`... | `INFO`, `WARN`, `ERROR`, `DEBUG`... |
| Destination inheritance/propagation | `useParentHandlers` | `additivity` |

**Do not mix configurations:** adding a `FileHandler` to a JUL Logger does not change Logback's Appenders unless a bridge/routing layer is explicitly configured. Likewise, `logback.xml` does not control a pure JUL Handler just because SLF4J is also on the application's classpath.

### 2.1. Categorize by Module, Not Per Request

Choose **finite and stable** module identifiers:

```text
com.example.payment
com.example.inventory
com.example.notification
```

Do not create a new `FileHandler` or `Appender` with a path like `logs/request-<id>.log` for every request. That approach can create an unbounded number of files, hold too many file handles, increase lock contention, degrade performance, and make rotation/retention difficult to enforce. Fields like `requestId` or `traceId` belong in the **log content or MDC**, while physical files are divided by relatively stable module groups.

Module names used to construct file paths must never be taken directly from untrusted input. A user-supplied value such as `../../secrets` can cause **path traversal** if concatenated into a file path without an allowlist.

## 3. Designing Per-Module Output Routes

Suppose a system has three groups:

```text
                    Root logger
                     /       \
        Payment Logger     Inventory Logger
             |                  |
             v                  v
       PAYMENT_FILE       INVENTORY_FILE
       logs/payment.log   logs/inventory.log
```

There are two main policies.

**Policy A — Strict Separation:** `payment` logs go only to `payment.log`, and `inventory` logs go only to `inventory.log`. A shared Appender/Handler can still serve other modules. Once a module Logger has its own destination, propagation to the root/parent must be controlled to prevent writing to the shared destination as well.

**Policy B — Dedicated Plus Shared:** Payment logs go to both `payment.log` **and** `application.log`. This is an intentional design when you need a consolidated stream for all events alongside a dedicated file for a subsystem. However, if a collector ingests both files and counts them as two independent events, error counts can be **doubled**.

Before writing configuration, decide:

- Does each module write to **one file or multiple files**?
- Should the consolidated file retain logs from modules that already have dedicated files?
- How many **destinations** is a single event allowed to appear in?
- Which levels are needed, and are exceptions/trace IDs required?
- Who manages rotation, retention, and cleanup?
- Can the collector deduplicate events or classify them by a `module` field?

Without answers to these questions, per-module file splitting easily turns into a hard-to-manage web of Appenders.

## 4. JUL: Using a Dedicated FileHandler per Module Logger

The JDK includes `java.util.logging.FileHandler` out of the box with no external libraries required. You can create one `Logger` per module, attach its corresponding `FileHandler`, and configure propagation.

Conceptual example:

```java
Logger payment = Logger.getLogger("demo.payment");
Logger inventory = Logger.getLogger("demo.inventory");

payment.setUseParentHandlers(false);
inventory.setUseParentHandlers(false);

// Each Logger will be attached to its own FileHandler,
// with Formatter, Level, Encoding, and proper close configured.
```

This is an **illustrative snippet**, not a complete program. `setUseParentHandlers(false)` prevents records from this Logger from being forwarded to the parent's Handlers. It does **not** change level inheritance from the parent. To keep levels explicit, configure both the source Logger's Level and the Handler's Level.

### 4.1. JUL Logger Hierarchy

Logger names are organized using dot-separated hierarchies: `demo.payment` and `demo.payment.gateway` have a hierarchical naming relationship. A child Logger can inherit its level when `setLevel(null)` is used and can forward records to parent Logger Handlers if allowed.

Distinguish between two mechanisms:

- **Level inheritance**: when a Logger does not set its own level, it uses the effective level from the appropriate ancestor.
- **Handler propagation**: records can be forwarded to ancestor Handlers, controlled by `useParentHandlers`.

If a child Logger enables `FINE` while its parent is configured at `INFO`, records accepted by the child Logger can still be forwarded to the parent's Handlers; **the parent Logger's level is not re-applied automatically to filter forwarded records**. The parent's Handler still applies its own level and Filter.

### 4.2. Important FileHandler Methods

| API / Option | Meaning |
| --- | --- |
| `new FileHandler(pattern, append)` | Creates a Handler writing to a file name pattern, allowing append or starting a new file |
| `new FileHandler(pattern, limit, count, append)` | Limits the size of each file and the number of generations for size-based rotation |
| `setFormatter(Formatter)` | Determines how each record is formatted |
| `setEncoding("UTF-8")` | Sets the output charset |
| `setLevel(Level)` | Minimum level threshold at the Handler |
| `setFilter(Filter)` | Additional custom filtering rules |
| `close()` | Flushes/closes the Handler and releases resources/file locks |

**`FileHandler` uses `XMLFormatter` by default if left unconfigured**, so it may produce XML files instead of the plain text you expect. If you want one line per record, attach an appropriate `Formatter` such as `SimpleFormatter` or a custom `Formatter`.

In `FileHandler`, the pattern supports placeholders such as `%h`, `%t`, `%g`, and `%u` according to JDK rules. Specifically:

- `%g`: generation number for rotation.
- `%u`: unique number to resolve file name conflicts.
- `%h`, `%t`: home directory or temporary directory depending on the environment.

Do not confuse these **JUL file name** placeholders with Logback's `%d` or `%msg` pattern tokens. Before relying on file naming or rotation, verify the actual paths created and the constructor or `logging.properties` policy.

### 4.3. Levels on Logger and Handler

If you want the payment file to record `INFO` and higher levels:

```java
payment.setLevel(Level.INFO);
paymentFile.setLevel(Level.INFO);
```

If you only call `payment.setLevel(Level.FINE)` while `FileHandler` remains at `INFO`, `FINE` records are created by the Logger but dropped by the Handler. Conversely, if the Handler is at `FINE` and the Logger is at `INFO`, `FINE` records are discarded before reaching the Handler.

Do not configure Loggers arbitrarily just to "have enough files." Decide which modules need `DEBUG`/`FINE`, who is responsible for toggling them, and how much log volume they can produce.

## 5. Standalone Java 17 Example: One File per Module

The example below uses **only JDK 17**—no SLF4J, Logback, Gradle, or Maven required. The program:

1. Creates the `logs` directory.
2. Creates two functional Loggers: `demo.payment` and `demo.inventory`.
3. Attaches dedicated `FileHandler` instances: `logs/payment.log` and `logs/inventory.log`.
4. Uses a custom `Formatter` so each record contains only level and message, without a varying timestamp.
5. Logs three events: payment INFO, inventory WARNING, and payment SEVERE.
6. Removes and calls `close()` on the Handlers in `finally` before reading the files.
7. Reads the files using `Files.readAllLines` and prints them to the console to verify that events went to the right files.

### 5.1. Create ModuleFileLoggingDemo.java

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class ModuleFileLoggingDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Path.of("logs");
        Files.createDirectories(directory);

        Logger payment = Logger.getLogger("demo.payment");
        Logger inventory = Logger.getLogger("demo.inventory");

        payment.setUseParentHandlers(false);
        inventory.setUseParentHandlers(false);
        payment.setLevel(Level.ALL);
        inventory.setLevel(Level.ALL);

        Formatter lineFormatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " " + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        FileHandler paymentFile =
                new FileHandler("logs/payment.log", false);
        FileHandler inventoryFile =
                new FileHandler("logs/inventory.log", false);

        paymentFile.setEncoding(StandardCharsets.UTF_8.name());
        inventoryFile.setEncoding(StandardCharsets.UTF_8.name());
        paymentFile.setLevel(Level.INFO);
        inventoryFile.setLevel(Level.INFO);
        paymentFile.setFormatter(lineFormatter);
        inventoryFile.setFormatter(lineFormatter);

        payment.addHandler(paymentFile);
        inventory.addHandler(inventoryFile);

        try {
            payment.log(
                    Level.INFO,
                    "event=payment.started requestId={0}",
                    "req-17");

            inventory.warning("event=stock.low sku=sku-2");

            payment.severe(
                    "event=payment.failed code=UPSTREAM_TIMEOUT");
        } finally {
            payment.removeHandler(paymentFile);
            inventory.removeHandler(inventoryFile);
            paymentFile.close();
            inventoryFile.close();
        }

        printFile("payment.log", Path.of("logs/payment.log"));
        printFile("inventory.log", Path.of("logs/inventory.log"));
    }

    private static void printFile(
            String label,
            Path file) throws IOException {
        System.out.println(label + ":");
        List<String> lines = Files.readAllLines(
                file, StandardCharsets.UTF_8);
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
```

### 5.2. Compile and Run

In the directory containing `ModuleFileLoggingDemo.java`, with **JDK 17 or later**:

```bash
javac ModuleFileLoggingDemo.java
java ModuleFileLoggingDemo
```

**Exact stdout of the program above when files are created successfully:**

```text
payment.log:
INFO event=payment.started requestId=req-17
SEVERE event=payment.failed code=UPSTREAM_TIMEOUT
inventory.log:
WARNING event=stock.low sku=sku-2
```

Contents of **`logs/payment.log`**:

```text
INFO event=payment.started requestId=req-17
SEVERE event=payment.failed code=UPSTREAM_TIMEOUT
```

Contents of **`logs/inventory.log`**:

```text
WARNING event=stock.low sku=sku-2
```

The example uses `append=false`, so each successful run starts a fresh file instead of retaining records from previous runs. Before reading the file contents, the program closes both `FileHandler` instances to flush buffers and release resources. `FileHandler` may create auxiliary lock files while running; those are not the target log files of this exercise.

### 5.3. Key Takeaways

- **Logger names:** `demo.payment` and `demo.inventory` classify events by module. These names are fixed and do not contain request IDs.
- **Dedicated Handlers:** `payment.addHandler(paymentFile)` ensures payment records go through the payment Handler; inventory has its own Handler.
- **`setUseParentHandlers(false)`:** prevents the parent/root's default `ConsoleHandler` from printing extra copies (and avoids parent files if configured). If the program also wants a consolidated file, a shared route should be designed intentionally.
- **`setLevel(Level.ALL)`:** lets the Logger accept standard events; the `INFO` Handler then decides to emit only `INFO` and above. This choice highlights the two filtering layers and is not a recommendation to enable all levels on every production Logger.
- **`formatMessage(record)`:** JUL processes `{0}`-style placeholders, turning `requestId={0}` into `requestId=req-17`.
- **`close()`:** ensures streams are flushed and closed when the program exits normally, rather than reading buffered, unflushed files. In this example, `FileHandler` is not used in try-with-resources; we remove and close it explicitly in `finally`.
- **Ordering:** the code runs sequentially and the Formatter omits clock/thread, so output is deterministic. If multiple threads log concurrently, cross-module event ordering is not synchronized into a single shared sequence.

### 5.4. Experiments and Adjustments

**Experiment 1 — enable DEBUG/FINE:** add `payment.fine("event=payment.debug")`. With `paymentFile` still at `INFO`, this line will **not** appear in the file even though the Logger is set to `ALL`. Change the Handler level to `FINE` to see it.

**Experiment 2 — enable parent Handlers:** set `payment.setUseParentHandlers(true)`. With the root having a `ConsoleHandler` in typical environments, a payment log may go to both the file and the console. Do not assume there are always exactly two copies, as it depends on the Handlers attached to ancestors.

**Experiment 3 — add a module:** create a third `Logger` and `FileHandler` for `demo.notification`, remembering to configure its Formatter/Level and close the Handler. Do not copy this initialization logic into per-request paths; in real applications, create Handlers at startup.

**Experiment 4 — switch to append mode:** change the constructor to `new FileHandler("logs/payment.log", true)`. If the file already exists, new records can be appended. You must define a rotation/cleanup policy, otherwise the file can grow indefinitely.

## 6. Configuring JUL via logging.properties

When you do not want to initialize Handlers in business code, you can use JUL configuration. Conceptual example of `FileHandler` properties:

```properties
.level = INFO
java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
java.util.logging.FileHandler.pattern = logs/application.%u.%g.log
java.util.logging.FileHandler.limit = 1000000
java.util.logging.FileHandler.count = 5
java.util.logging.FileHandler.append = true
```

This is an **illustrative snippet showing `FileHandler` properties**, not a complete configuration that automatically creates **two independent per-module `FileHandler` instances**. Note that JUL `LogManager` manages Handlers by class name and handler declarations; writing arbitrary properties like `demo.payment.file=payment.log` does not by default create two separate `FileHandler` instances.

If you want to configure multiple per-module destinations purely through properties files, you must rely on what JUL actually supports, configure appropriate Handlers, or write configurable custom Handlers/subclasses. Some frameworks and configuration systems extend JUL with other declaration styles; **do not assume extended properties are standard JDK features**.

In small programs, a code-based setup like Section 5 can be clearer. For production applications using Logback, named Appenders in `logback.xml` are usually much more intuitive when multiple separate files are needed.

**Relative paths:** `logs/application.%u.%g.log` depends on the process working directory. When running as a service, in a container, or from an IDE, the working directory may differ from what you expect. When needed, use an absolute path from deployment configuration or a controlled directory with an explicit permission policy.

## 7. Logback: RollingFileAppender per Package/Module

For applications using **SLF4J + Logback**, you can configure a separate `RollingFileAppender` for each module. The advantage is that each Appender has its own **file path, encoder, filter, rolling policy, and retention**, referenced via `<appender-ref>` from the module's logger.

Suppose the code packages are:

```text
com.example.payment.*
com.example.inventory.*
com.example.notification.*
```

A Logback configuration can define:

- `PAYMENT_FILE` for `com.example.payment`.
- `INVENTORY_FILE` for `com.example.inventory`.
- `APPLICATION_FILE` at the root for all other packages.

### 7.1. Complete logback.xml File

The example below demonstrates **two modules with dedicated files** and one shared file for other loggers. Place `logback.xml` on the runtime classpath, such as `src/main/resources/logback.xml`, when using Logback Classic. The `logs` directory must be writable; real deployments should verify paths and filesystem permissions.

```xml
<configuration>
    <!-- Payment module log file -->
    <appender name="PAYMENT_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/payment.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/payment.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>14</maxHistory>
            <totalSizeCap>500MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Inventory module log file -->
    <appender name="INVENTORY_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/inventory.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/inventory.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>200MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} requestId=%X{requestId} - %msg%n</pattern>
        </encoder>
    </appender>

    <!-- Shared file for other loggers -->
    <appender name="APPLICATION_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy
              class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>500MB</totalSizeCap>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS,UTC} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="com.example.payment"
            level="INFO" additivity="false">
        <appender-ref ref="PAYMENT_FILE"/>
    </logger>

    <logger name="com.example.inventory"
            level="INFO" additivity="false">
        <appender-ref ref="INVENTORY_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="APPLICATION_FILE"/>
    </root>
</configuration>
```

**How the XML works:**

1. `RollingFileAppender` keeps the active file path, while `TimeBasedRollingPolicy` creates daily archives and compresses them to `.gz` on rollover.
2. `maxHistory` and `totalSizeCap` help bound archive history and total size by policy, though cleanup depends on application lifecycle and actual configuration; they do not strictly guarantee zero data loss.
3. The `com.example.payment` logger groups child Loggers sharing that package prefix via hierarchy.
4. `additivity="false"` stops payment records from propagating to the root Appender, preventing them from being duplicated into `application.log`.
5. Inventory is configured similarly, with its own file and retention.
6. Loggers outside those two branches are still handled by root and written to `application.log` if level/filter allow.
7. Each module still needs a security policy: **splitting files does not replace sanitizing message/MDC content**.
8. Pattern tokens `%d`, `%logger`, `%msg`, and `%X` are **Logback** syntax and do not apply to `java.util.logging.FileHandler`.

### 7.2. When to Use additivity=false?

In Logback, Loggers follow a hierarchical naming structure and **additivity** is enabled by default. When a Logger has its own Appender, events can still be forwarded to ancestor/root Appenders.

```text
com.example.payment.PaymentService
          |
          +--> PAYMENT_FILE
          |
          +--> root -> APPLICATION_FILE   (if additivity=true)
```

If you want payment logs **only in `payment.log`**, setting `additivity="false"` on the module logger is the right choice. However, if you set it to `false` **without attaching an Appender to that branch**, logs may have no destination at all. Design the full route before disabling additivity.

`additivity="false"` **does not mean the Logger stops inheriting its level**. It only controls forwarding events to ancestor Appenders. A child Logger with its own level can emit `DEBUG` events and forward them to the root Appender via additivity; the root level is not necessarily re-checked to filter events already accepted by the child Logger. Appender filters can still drop events.

### 7.3. When You Want Both Module Files and a Shared File

If policy requires payment logs in both `payment.log` and `application.log`, keep **default additivity** or configure the shared appender intentionally. Do not treat an event appearing in two files as a bug when it is by design, but you should:

- Document **which destination is the source of truth** when building dashboards and alerts.
- Avoid ingesting both records as two separate errors.
- Check retention differences between dedicated files and the shared file.
- Avoid attaching the **exact same Appender** to both a child logger and root while additivity is enabled, which would write twice to the same destination.

Scenario table:

| Configuration | Where do payment events go? | Interpretation |
| --- | --- | --- |
| `PAYMENT_FILE` on payment, additivity false | Only `payment.log` | Strict module separation |
| `PAYMENT_FILE` on payment, additivity true, root has `APPLICATION_FILE` | `payment.log` and `application.log` | Dedicated plus shared |
| Payment has no appender, additivity false | No destination from ancestors | High risk of lost logs |
| Same `PAYMENT_FILE` attached to payment and root, additivity true | Can invoke the same Appender twice | Risk of duplicate lines in one file |

Test with an event carrying a recognizable `requestId`, and inspect both the dedicated file and the shared file before deploying to production.

## 8. Splitting Files Alone Is Not Enough: Designing Levels, Formats, and Context

A system split by module must not lose the information needed for cross-module tracing. For example, a request flowing through payment and inventory:

```text
payment.log:
INFO event=payment.started requestId=req-17 orderId=ord-8

inventory.log:
INFO event=stock.reserved requestId=req-17 orderId=ord-8

payment.log:
ERROR event=payment.failed requestId=req-17 code=UPSTREAM_TIMEOUT
```

**The common link is `requestId=req-17`**, not the file path. When an incident spans multiple modules, your collection system must be able to search for the same correlation ID across files and streams.

With SLF4J/Logback, MDC can inject context into the pattern:

```java
String old = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    processPayment();
} finally {
    if (old == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", old);
    }
}
```

This is a **code snippet** assuming `org.slf4j.MDC` is imported and `requestId` / `processPayment()` exist. In Logback patterns, `%X{requestId}` resolves to the corresponding MDC value.

**Be careful with async:** MDC/`ThreadLocal` does not automatically propagate across every `ExecutorService`, `CompletableFuture`, queue, or reactive pipeline. When crossing thread boundaries, use a supported context propagation mechanism and ensure context is cleared/restored so logs from one request are never attributed to another.

Distinguish further:

- **Module name**: stable source classification, suitable for Logger/file names.
- **`requestId`**: links events of a single request, which may appear across multiple modules.
- **`traceId`, `spanId`**: supports distributed tracing if your stack uses tracing.
- **`event`, `errorCode`, `outcome`**: classifies event type and result.
- **`level`**: severity level, whose naming differs between JUL and Logback.

Never create files per `requestId` as a substitute for correlation IDs and centralized log querying.

## 9. File Naming and Directory Structure

A simple convention:

```text
/var/log/my-app/
  payment.log
  payment.2026-01-12.log.gz
  inventory.log
  inventory.2026-01-12.log.gz
  application.log
```

These paths are **illustrative**; many containers do not use `/var/log` for application logs, and a relative path like `logs/payment.log` resolves against the working directory.

When naming files, you should:

1. Select module names from a **fixed allowlist**, never concatenating raw user input.
2. Ensure each Appender manages **one intentional path**; avoid multiple independent writers writing to the same file.
3. If running multiple instances on the same host, add an appropriate **instance/process namespace** rather than letting multiple JVMs open the same file.
4. Choose a storage location with write permissions and sufficient disk space.
5. Explicitly define **UTF-8 charset** and timezone in the format.
6. Restrict read permissions, because authentication module logs may be more sensitive than general operational logs.
7. Distinguish **active open files** from **rotated archives** so collectors read them properly.

With file-tailing collectors, renaming or compressing files during rotation can cause **duplicate or missed events** if the agent does not track file positions properly. Test the actual collector rather than running a single `logger.info()` and assuming the pipeline works.

## 10. Rotation, Retention, and Size Limits

If you create dedicated files for five modules without rotation/retention, total log volume can grow even faster than a single shared file because some events are duplicated across destinations.

### 10.1. Policy Categories

- **Size-based**: rolls over when a file reaches a configured size.
- **Time-based**: rolls over on a schedule, such as daily.
- **Size-and-time based**: combines both for high-volume log files.

In JUL, `FileHandler(pattern, limit, count, append)` supports size-based rotating file sets. `limit` is the size threshold and `count` is the number of generations. Verify actual file names whether using `%g` or omitting `%g`.

In Logback, `TimeBasedRollingPolicy` supports `fileNamePattern`, `maxHistory`, and `totalSizeCap`; `SizeAndTimeBasedRollingPolicy` is the right choice when you genuinely need both daily rotation and per-archive size limits.

### 10.2. Retention Is More Than Just Day Counts

For example, keeping payment logs for 14 days and inventory logs for 7 days. You must also answer:

- Does the payment file contain data that must be purged earlier due to sensitivity?
- Are audit events required to be retained longer than routine diagnostic logs?
- Are archives compressed, encrypted at rest, and access-controlled?
- Does a backup system or collector also retain copies under its own retention policy?
- When archives are deleted from the filesystem, what policy governs copies stored in the collector?

**Appender retention does not automatically delete copies already shipped elsewhere.** Storage tiers must be managed consistently according to organizational policy.

### 10.3. When Files Grow Unexpectedly Fast

Do not blindly raise file size limits. Check:

1. Is a module Logger accidentally running at `DEBUG`/`TRACE`?
2. Is a retry loop printing a full stack trace on every iteration?
3. Is a single event being duplicated by additivity or a logging bridge?
4. Is a large DTO or request body being logged in full?
5. Is appropriate sampling or rate limiting configured for high-frequency events?
6. Is the collector ingesting both dedicated and shared files, doubling storage costs?

Avoid using logs as the sole store for critical business transactions. If data has strict audit durability requirements, use a dedicated audit/storage mechanism with an explicit contract rather than relying on logger rotation.

## 11. Concurrency, Multiple JVMs, and File I/O Errors

### 11.1. Multiple Threads in One Process

Loggers and Handlers/Appenders are built for multi-threaded logging, but events from different threads can interleave; **do not infer global causality from two separate module files**. A `payment.log` and `inventory.log` entry with close timestamps is not enough to prove which event caused which, especially across multiple hosts. Use correlation IDs and traces.

If a custom `Formatter` holds shared mutable state, verify its thread safety. Prefer immutable Formatters, and never use an unprotected shared mutable `SimpleDateFormat`.

### 11.2. Multiple Processes Writing to the Same Path

Two JVMs running the same application and writing to `logs/payment.log` can cause lock contention, interleaved writes, rotation conflicts, and corrupted output. JUL `FileHandler` has locking and `%u` to disambiguate some file name collisions, but **do not treat that as a guarantee of atomic, durable multi-process logging**. With Logback `RollingFileAppender`, having multiple processes write to and rotate the same file is likewise unsafe by default.

Better approaches:

- Have each instance write to stdout/stderr and let the platform/collector gather logs.
- Or give each instance its own path from trusted deployment configuration.
- If shared writing is unavoidable, use a centralized collection architecture with explicit synchronization and durability guarantees rather than sharing file handles directly.

### 11.3. I/O Errors and Handler/Appender Lifecycle

Common failures include:

- The directory does not exist or the process lacks write permissions.
- Disk full, out of inodes, or filesystem remounted read-only.
- Too many open file handles from creating Appenders per request.
- Rotation fails or the collector fails to follow the new file.
- Abrupt process termination before buffers/async queues flush.
- An Appender is declared in config but never referenced by any Logger.

Initialize Handlers/Appenders with the application lifecycle, provide clear error paths, and **close/stop them cleanly** on normal shutdown. `logger.info(...)` returning **does not mean the event is durably persisted on disk**.

Do not let logging failures crash the business path due to an unwritable log file without error handling; at the same time, ensure operational alerts fire when logging breaks, because silently swallowing log file errors is equally dangerous.

## 12. Dedicated Files in Containers or Centralized stdout?

In Kubernetes or modern container environments, an effective default rule is **applications write to stdout/stderr**; the platform/agent reads the stream, attaches metadata such as pod, namespace, instance, and container, and forwards it to a centralized logging system.

| Design | Strengths | Limitations |
| --- | --- | --- |
| One local file per module | Easy to tail by module on fixed hosts | Managing paths, permissions, rotation, collectors, ephemeral storage |
| One `application.log` with a module field | Fewer files, simpler management | Requires filtering in tools to view a single module |
| One JSON stream via stdout | Ideal for containers and centralized observability | Depends on collector/parser/schema |
| Dedicated files + shared file | Both focused and consolidated views | Risk of double-ingestion, higher cost, complex retention |

If your infrastructure already has Elasticsearch, OpenSearch, Loki, or a similar platform, you can usually query by `logger`, `module`, `service`, and `requestId` **without splitting physical files**. Per-module files remain valuable when meeting specific storage, access-control, or pipeline constraints and when their operational cost is accepted.

**Selection rule:** design logical **classification via fields** first, and decide later whether **physical file splitting** is needed. This keeps the architecture less coupled to a specific backend and easier to move across deployment environments.

## 13. Security: Preventing Log Files from Becoming Sensitive Data Stores

Splitting files only separates **storage paths**; it does not strip sensitive data from messages. Authentication, payment, and account modules in particular can accidentally log sensitive information.

- Never log passwords, bearer tokens, cookies, private keys, CVVs, or sensitive payment payloads.
- Use field allowlists: `requestId`, `operation`, `errorCode`, `outcome`, `durationMs`, and approved internal IDs.
- Avoid logging `toString()` on objects with uncontrolled fields.
- User input may contain newlines, carriage returns, and control characters to perform **log injection**. Use a safe/structured JSON encoder or escape values in plain-text output.
- Never use client input to determine file names or paths.
- Apply least-privilege permissions to log directories and archives.
- Audit retention, storage/backup encryption, and read permissions in the centralized logging system.

Example of malicious input:

```text
comment=normal
ERROR event=admin.login outcome=success
```

If a `comment` containing a newline is concatenated directly into a plain-text log, the `ERROR` line can be **forged by user input**, not a real log record. A dedicated payment file does not solve this problem; data must be encoded/escaped at the source or in the final formatter.

### 13.1. Stack Traces and Error Payloads

An exception message can contain URLs, usernames, or payloads. Log `Throwable` only at boundaries where investigation is needed, rather than printing the same error at multiple layers. If using a JSON encoder, represent exceptions as properly escaped fields; if using multi-line text stack traces, ensure the collector is configured for multiline aggregation.

## 14. Observing from Two Angles: Business Logs and Operational Logs

**Reading by module** is helpful when a team only needs events from its own subsystem. However, **end-to-end investigation** requires connecting logs across modules and services. Therefore:

- Give each module a stable Logger name and consistent event codes.
- Carry a correlation ID across all steps of a request.
- Standardize timestamps on a single timezone (typically UTC).
- Keep severity rules consistent even though Logback uses `WARN`/`ERROR` while JUL uses `WARNING`/`SEVERE`.
- Use metrics for error rates, latency, and throughput; traces for distributed journeys; and logs for per-event details.
- When a collector ingests multiple files, attach metadata such as `source_file`, `service`, and `module` to identify event origin and prevent double-counting.

Per-module files are **a storage routing decision**, not a replacement for tracing. Do not split files to the point where steps of a single request are scattered without a trace key.

## 15. Common Issues and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Payment logs appear in both `payment.log` and `application.log` | Parent handler/additivity is enabled | Decide between strict separation or both; align configuration |
| `payment.log` is empty despite `logger.info` | Blocked by level/filter, Appender not attached/started, or invalid path | Check Logger, Handler/Appender, filesystem, and status messages |
| Child logs do not reach module file | Logger name does not match branch or additivity is disabled elsewhere | Check Logger name, hierarchy, and `appender-ref` |
| Disabling additivity stops all logs | Module Logger has no Appender of its own | Attach the target Appender or restore propagation |
| `FileHandler` outputs XML instead of text | Default `XMLFormatter` is active | Set `SimpleFormatter` or a custom `Formatter` |
| Files are created in the wrong directory | Relative path resolves against a different working directory | Print/check working directory and path configuration |
| Files grow without bound | Missing rolling/retention policy, excessive `DEBUG` logging | Configure policies and inspect log volume |
| Multiple files have interleaved writes across JVMs | Multiple processes using the same path | Separate namespaces per instance or use a collector |
| Non-ASCII/Unicode text is garbled | Mismatched charset/encoding between writer and collector | Enforce UTF-8 from writer through parser |
| Events are lost after shutdown | Async buffer/queue not flushed or abrupt process kill | Check shutdown lifecycle and pipeline durability |
| Collector double-counts errors | Ingesting both dedicated and shared files | Define a primary source of truth and deduplication |
| Errors appear only on console, not in files | Missing file Handler, differing level/filter/path | Check Logger propagation and Handler configuration |
| Cannot trace a request across modules | Missing `requestId`/`traceId` | Standardize context and propagate across async boundaries |
| Logs still contain secrets despite module split | Code accidentally logs sensitive fields/Throwables | Redact at source, review formats, and enforce permissions |
| JUL config has no effect on Logback | Different logging backends/APIs | Identify the runtime provider and edit the matching config |

### Systematic Investigation Steps

1. **Emit a test event** in each module with a recognizable event code and ID.
2. Verify the exact **Logger name** and effective level.
3. Check which Handlers/Appenders are actually attached to that Logger.
4. Check `useParentHandlers` or `additivity`—are records continuing to root?
5. Check the level/filter of each Handler/Appender and the actual file path.
6. Verify Formatter/Encoder, charset, write permissions, and lifecycle.
7. Read both dedicated and consolidated files (if any), comparing expected vs. actual record counts.
8. Test rotation/retention, concurrent requests, shutdown, and disk-full behavior in an appropriate test environment.
9. Verify the collector ingests the right files/streams without duplicating alerts or metrics.

Do not change multiple things at once: altering Logger names, Appenders, additivity, and rolling policies simultaneously makes root-cause analysis difficult.

## 16. Pre-Deployment Checklist

- [ ] Decided whether **multiple physical files are truly needed** or a single JSON stream with a module field is sufficient.
- [ ] Agreed on a finite module list, Logger names, and fixed file paths.
- [ ] Each module has the intended Handler/Appender and Formatter/Encoder.
- [ ] Decided whether events also go to a shared file; controlled `useParentHandlers`/`additivity`.
- [ ] Level and Filter policies are in place without dropping critical events.
- [ ] File names, working directory, charset, timezone, and write permissions verified in the real runtime.
- [ ] Rolling, retention, archive size caps, and filesystem monitoring configured.
- [ ] No two JVMs/instances write to the same file path unless explicitly designed for concurrency.
- [ ] Correlation ID/trace ID present to trace across modules.
- [ ] Context propagation handled across executors/async pipelines, with MDC/`ThreadLocal` cleanup.
- [ ] Secrets and sensitive payloads excluded from logs; escaping and access control enforced.
- [ ] Collector reads the right paths without missing archives or double-ingesting.
- [ ] Tested file output, missing/duplicate logs, shutdown, rotation, and disk errors.
- [ ] Configuration change and rollback plan ready in case module splitting disrupts monitoring signals.

### Technical References

- [Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): file name patterns, limit/count, append, and locking.
- [Java 17 — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): hierarchy, levels, and `useParentHandlers`.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): logger hierarchy, Appenders, and additivity.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): `RollingFileAppender`, rolling policies, and encoders.
- [SLF4J Manual](https://www.slf4j.org/manual.html): facade and parameterized logging.

**Conclusion:** **Per-module log files** help separate information streams by function when there is a clear operational need. In JUL, use `Logger` + `FileHandler` + `useParentHandlers`; in Logback, use package-based `Logger` + `RollingFileAppender` + `additivity`. What matters is not just creating multiple files, but preserving **accurate record counts, proper levels, reliable paths, sufficient context, rotation/retention, and data security**. If your system already has centralized logging, consider classifying by a `module` field in JSON before expanding the number of physical files.

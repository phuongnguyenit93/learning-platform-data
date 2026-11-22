# Per-Application Log Files in Java

## 1. What is a per-application log file?

**A per-application log file** is a way of organizing logging so that events from a single **application, service, or process** are written to a file (or a group of rotating files) with its own name and path. For example, on a machine running three services:

```text
logs/
├── orders-service.log
├── billing-service.log
└── inventory-service.log
```

Here, `orders-service.log` contains logs from the order-processing application, while `billing-service.log` belongs to the billing system. Separating output destinations like this speeds up incident investigation and makes it easier to manage access permissions, disk usage, and retention periods.

**Do not equate "one file per application" with "one file per class".** Java can have hundreds of loggers organized by class or package, yet all of them send events to **a single file appender/handler**. This is a configuration decision of the logging backend, not a special feature that happens automatically when calling `Logger.getLogger(...)`.

For example, a single service may have the following loggers:

- `com.example.orders.OrderController`
- `com.example.orders.OrderService`
- `com.example.orders.OrderRepository`

All three can write together into `logs/orders-service.log`, distinguished within each line by the `loggerName` field.

Organizing files per request or per user—such as `REQ-123.log`—is a different problem. It creates an unmanageable number of files and easily leads to path issues, privacy concerns, and retention problems; it should not be the default choice.

## 2. When should you separate files by application?

Suppose multiple JVMs on the same host write to a shared `logs/application.log`. Lines from different applications can interleave, making it hard to find root causes and causing contention when writing or rotating files. Separating into individual files helps you:

1. **Isolate errors:** know which service's logs to read without filtering an entire shared file.
2. **Choose detail levels:** a service that needs debugging can be allowed to write `DEBUG` to its file without affecting other services.
3. **Manage operations:** each service has its own rotation, retention, quota, and permissions.
4. **Optimize collection:** log collectors can easily attach labels such as `service`, `environment`, and `instance`.
5. **Avoid file contention:** independent JVMs do not have to hold the same write path simultaneously.

On the other hand, more files mean more configuration, storage overhead, and monitoring work. On Kubernetes or infrastructure that already collects stdout/stderr per container, **separating by metadata in the collector** can be more effective than forcing each application to create files inside its container.

### Selection guidelines

| Separation strategy | Example name | Purpose |
| --- | --- | --- |
| By service | `orders-service.log` | Output of a single application |
| By environment | `orders-prod.log` | Distinguish dev/test/prod if sharing a filesystem |
| By instance | `orders-instance-a.log` | Prevent multiple JVMs from writing to the same file |
| By event group | `orders-errors.log` | Store WARN/ERROR separately from INFO |
| By module/package | `orders-payment.log` | Separate when a module needs its own policy |
| By user/request | `user-42.log` | **Usually unsuitable** due to security risks and file explosion |

If a system runs one service per JVM, the typical choice is a **primary rotating file** per service, storing the request ID, logger name, and instance ID **inside the log record**, rather than creating a new file for each request.

## 3. How logs flow inside an application

A common logging architecture:

```text
OrdersApp
   ├── OrderController ─┐
   ├── OrderService ────┼──> Logger API
   └── OrderRepository ┘           │
                                   ▼
                       Logger config: level/filter
                                   │
                                   ▼
                         File/RollingFile Appender
                                   │
                            Layout/Formatter
                                   │
                                   ▼
                          logs/orders-service.log
```

Each component has a distinct responsibility:

- **Logger:** receives `info`, `warn`, `error` calls, named by class or package.
- **Logger level/filter:** discards events that do not need to be created or forwarded.
- **Appender (Log4j2/Logback):** connects the logger to a file, console, or other destination.
- **Handler (JUL):** the concept equivalent to an appender in `java.util.logging`.
- **Layout/Formatter:** determines how the timestamp, logger name, message, and exception are formatted.
- **Rolling policy:** controls rotating and storing archive files.

**File names do not automatically follow class names.** Having a `Logger` named `OrderService` does not mean the system will create `OrderService.log`; the file path must be specified by the backend or the program.

When code uses the SLF4J facade, `org.slf4j.Logger` only emits events. File creation is determined by the **provider/backend**, such as Logback or Log4j2. JUL configuration documentation cannot be used verbatim to configure Logback, and vice versa.

## 4. File naming and directory structure

An ideal file name should be clear, stable, and free of collisions with other applications:

```text
/var/log/example/
├── orders/
│   ├── orders-service.log
│   └── archive/
├── billing/
│   ├── billing-service.log
│   └── archive/
└── inventory/
    ├── inventory-service.log
    └── archive/
```

These are **illustrative Linux paths**, not mandatory locations. Each deployment can choose a log directory with appropriate permissions.

**Recommended:**

- Service name from controlled configuration: `orders-service`.
- Environment or instance when it is genuinely needed to distinguish shared files.
- A dedicated archive directory for rolled-over files.
- A well-defined path with permissions to create, write, and rename files.

**Avoid:**

- Raw values from URLs, user input, or request headers for file names.
- A single fixed `application.log` name for all JVMs on the same filesystem without controlling shared access.
- File names containing passwords, tokens, emails, or sensitive personal data.
- Creating a new handler/file per request just to filter logs by request ID.

If the application is launched from a different working directory, a relative path like `logs/orders-service.log` may resolve to a different location. Specify the working directory explicitly in your launch script/service manager, or use an absolute path configured at deployment time.

## 5. Complete example: Java 17 + Maven + Log4j2

To see how an application log file works in practice, let's build an **Orders Service** application using Log4j2 API and Log4j2 Core.

Demo requirements:

- Loggers under the `demo.orders` namespace.
- `INFO`, `WARN`, and `ERROR` events printed to the console.
- `logs/orders-service.log` receives `DEBUG` and above.
- The file uses **RollingFile** so it can rotate by size and time.
- No duplicate logs caused by both a child logger and the root logger handling the same event.

### 5.1. Project structure

```text
orders-service/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── orders/
        │           └── OrdersApp.java
        └── resources/
            └── log4j2.xml
```

### 5.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The versions in this demo are **a fixed combination for illustration**, not necessarily the latest releases or suitable for every production environment. In real deployments, use maintained versions with up-to-date security patches and keep `log4j-api`, `log4j-core`, and any bridges/backends aligned.

### 5.3. File src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%level | %msg%n"/>
        </Console>

        <RollingFile name="OrdersFile"
                     fileName="logs/orders-service.log"
                     filePattern="logs/archive/orders-service-%d{yyyy-MM-dd}-%i.log.gz"
                     append="true">
            <PatternLayout pattern="%level | %msg%n"/>
            <Policies>
                <SizeBasedTriggeringPolicy size="1 MB"/>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
            </Policies>
            <DefaultRolloverStrategy max="3"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Logger name="demo.orders" level="debug" additivity="false">
            <AppenderRef ref="Console" level="info"/>
            <AppenderRef ref="OrdersFile" level="debug"/>
        </Logger>

        <Root level="warn">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

Configuration breakdown:

1. **`OrdersFile` is the appender name**, while `fileName` is the actual path of the active file.
2. `filePattern` names the archive files on rollover; `%d` is the date, and `%i` is the index.
3. `append="true"` appends to the existing file after a restart instead of overwriting it by default.
4. `SizeBasedTriggeringPolicy` and `TimeBasedTriggeringPolicy` provide the conditions for file rotation. A short demo run with a few lines may **not create any archive files yet**.
5. `DefaultRolloverStrategy max="3"` relates to the archive window/index limit for that strategy; **it does not mean keeping exactly three days of logs**.
6. The logger named `demo.orders` receives events from code in this namespace; the `debug` level allows debug messages to be logged.
7. The `Console` AppenderRef is at `info`, so it does not print `DEBUG`.
8. The `OrdersFile` AppenderRef is at `debug`, so the file receives more detail than the console.
9. `additivity="false"` stops Orders events from propagating to the root `Console`, preventing duplicate printing.
10. Root `warn` handles loggers outside the configured namespace. **In this example, the dedicated file only receives events from the Orders namespace.**

If a project wants the application file to capture **all** loggers in the JVM, it can attach the file appender to root. If it only wants a specific module, it attaches it to the appropriate logger namespace. These are two different policies and should be chosen deliberately.

### 5.4. File src/main/java/demo/orders/OrdersApp.java

```java
package demo.orders;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class OrdersApp {
    private static final Logger LOG =
            LogManager.getLogger(OrdersApp.class);

    public static void main(String[] args) {
        String orderId = "ORD-42";

        LOG.debug("Checking inventory for {}", orderId);
        LOG.info("Order {} accepted", orderId);
        LOG.warn("Low stock for {}", orderId);

        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException exception) {
            LOG.error("Invalid numeric configuration", exception);
        }

        System.out.println("business-finished");
    }
}
```

The code uses a per-class logger, while the configuration routes records to **the file for the entire Orders application**. The example intentionally triggers a `NumberFormatException` to verify that the `Throwable` is preserved for the logging backend.

### 5.5. Running the program

From the `orders-service` directory with Maven and JDK 17 or newer:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.orders.OrdersApp
```

**Main message lines on stdout**, omitting Maven's own output:

```text
INFO | Order ORD-42 accepted
WARN | Low stock for ORD-42
ERROR | Invalid numeric configuration
business-finished
```

Because the `ERROR` event carries a `Throwable`, Log4j2 `PatternLayout` can **automatically print the stack trace** after the `ERROR` line. Therefore, this shows the **main message lines**, not the full byte-for-byte console output.

**Main message lines in `logs/orders-service.log` after one run from a clean directory:**

```text
DEBUG | Checking inventory for ORD-42
INFO | Order ORD-42 accepted
WARN | Low stock for ORD-42
ERROR | Invalid numeric configuration
```

The file may also contain the **multi-line stack trace** for `NumberFormatException`. The exact line count and stack frames depend on the JDK version. If you run it again, `append="true"` causes new records to be appended after the previous ones.

Viewing the file:

```bash
cat logs/orders-service.log
```

On PowerShell:

```powershell
Get-Content logs/orders-service.log
```

**Why does `DEBUG` go to the file but not to the console?** `DEBUG` is accepted by the `demo.orders` logger, but each `AppenderRef` has its own threshold. `OrdersFile` accepts `DEBUG`, whereas `Console` only accepts `INFO` and above. It is not because the code calls two loggers or opens files inside each method.

### 5.6. Post-run checks

- `log4j2.xml` is actually on the runtime classpath.
- Log4j2 API/Core are present at the expected versions and not overridden by another backend.
- The working directory is as expected.
- The log/archive directories can be created and are writable.
- The file contains at least the `INFO`/`WARN`/`ERROR` messages.
- The console does not duplicate events due to additivity.
- `ERROR` events preserve exceptions/stack traces if the configured layout supports them.
- When increasing event volume to test rollover, archive file names match the pattern.

Do not rely on `mvn compile` succeeding to conclude that file logging works: configuration and filesystem permissions are primarily verified at runtime.

## 6. Creating separate files for multiple applications on the same machine

For **two independent JVMs**, the most common approach is for **each JVM to load its own configuration**:

```text
JVM Orders:
  logs/orders-service.log

JVM Billing:
  logs/billing-service.log
```

If two services are built from the same template, pass the service name and log directory through safe deployment configuration. Do not let both write to `logs/application.log` just because the template shares a single literal.

An example of choosing paths by deployment convention:

| Application | Active log file | Archive directory |
| --- | --- | --- |
| Orders | `/var/log/example/orders/orders-service.log` | `/var/log/example/orders/archive` |
| Billing | `/var/log/example/billing/billing-service.log` | `/var/log/example/billing/archive` |
| Inventory | `/var/log/example/inventory/inventory-service.log` | `/var/log/example/inventory/archive` |

The POSIX paths above are **illustrative only**; the actual directories must be created, secured, and mounted for the process. On Windows, use platform-appropriate paths rather than copying Linux paths.

### If one JVM hosts two modules

When a single JVM contains both `com.example.orders` and `com.example.billing`, you can separate them by logger namespace:

```xml
<Loggers>
    <Logger name="com.example.orders" level="info"
            additivity="false">
        <AppenderRef ref="OrdersFile"/>
    </Logger>

    <Logger name="com.example.billing" level="info"
            additivity="false">
        <AppenderRef ref="BillingFile"/>
    </Logger>

    <Root level="warn">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

This is a **configuration snippet**: `OrdersFile`, `BillingFile`, and `Console` must be defined in `<Appenders>`. Separating by package within a single JVM is **module-level separation**, not separating two processes with independent lifecycles.

If you want module events to also go to the console, add a console reference to the module logger or adjust propagation accordingly. With `additivity="false"`, child loggers do not automatically forward events to the root `Console`.

## 7. Preventing duplicate logs from additivity

When configuring multiple loggers and appenders, events can be emitted multiple times if the same appender is referenced by both a child logger and a parent/root logger.

An example that easily causes duplicates:

```xml
<Loggers>
    <Logger name="demo.orders" level="info">
        <AppenderRef ref="Console"/>
    </Logger>

    <Root level="info">
        <AppenderRef ref="Console"/>
    </Root>
</Loggers>
```

Assuming `Console` is declared, the child logger emits the event through `Console`, and then because of additivity, it propagates to root and is emitted again.

Two common ways to avoid this:

1. Put `Console` **only on root**; child loggers can set their own levels without attaching the same appender again.
2. Give the child logger **all of its own appenders** and set `additivity="false"` to stop events from propagating to root.

**Important:** disabling additivity can **drop destinations** that only existed on root. For example, if a child logger has a file appender but no console appender, setting `additivity="false"` means events will only go to the file. Whether that is right or wrong depends on your requirements, and should not be assumed as a default.

A `WARN` appearing **once on the console and once in the file** is normal fan-out. A `WARN` appearing **twice in the same file** usually indicates duplicate configuration or application code logging the same error at multiple layers.

## 8. Logback: per-application files with SLF4J

If a project uses `org.slf4j.Logger` with **Logback** as the backend, file configuration is typically placed in `logback.xml`. Complete illustrative example:

```xml
<configuration>
    <appender name="ORDERS"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/orders-service.log</file>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss} %-5level %logger - %msg%n</pattern>
        </encoder>
        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/orders-service.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
        </rollingPolicy>
    </appender>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%-5level %logger{1} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="ORDERS"/>
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

In this configuration, root sends logs at `INFO` and above to the **process** file, including logs from third-party libraries if they route through the same Logback backend.

**Differences from Log4j2:** Logback uses `RollingFileAppender`, `SizeAndTimeBasedRollingPolicy`, and `<appender-ref>`, whereas Log4j2 uses `RollingFile`, `Policies`, and `AppenderRef`. Do not copy XML configurations between the two and expect them to work.

`maxHistory` and `totalSizeCap` configure Logback's archive retention and size cap policies, though you should still verify actual retention behavior during rollover and startup. Logback requires a backend dependency compatible with your application's SLF4J API version.

A reusable Java library should normally depend only on the `slf4j-api` facade and let the host application choose the logging provider and file paths; do not force every consuming application to write to a file named by the library.

## 9. JUL: using FileHandler for application files without external dependencies

The JDK provides `java.util.logging.FileHandler`. It can write to files using a pattern and rotate based on size and generation count.

Create a standalone file `JulApplicationFileDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.ConsoleHandler;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulApplicationFileDemo {
    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        Logger logger = Logger.getLogger("demo.orders");
        Level oldLevel = logger.getLevel();
        boolean oldUseParents = logger.getUseParentHandlers();
        Handler[] oldHandlers = logger.getHandlers();

        Formatter concise = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        ConsoleHandler console = new ConsoleHandler();
        console.setLevel(Level.INFO);
        console.setFormatter(concise);

        FileHandler file = new FileHandler(
                "logs/orders-service-%g.log",
                1_048_576, 3, true);
        file.setLevel(Level.FINE);
        file.setFormatter(concise);

        for (Handler h : oldHandlers) {
            logger.removeHandler(h);
        }
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.FINE);
        logger.addHandler(console);
        logger.addHandler(file);

        try {
            logger.fine("Preparing order cache");
            logger.info("Order accepted");
            logger.warning("Low stock");
            System.out.println("jul-finished");
        } finally {
            logger.removeHandler(file);
            logger.removeHandler(console);
            file.close();
            console.close();
            logger.setLevel(oldLevel);
            logger.setUseParentHandlers(oldUseParents);
            for (Handler h : oldHandlers) {
                logger.addHandler(h);
            }
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac JulApplicationFileDemo.java
java JulApplicationFileDemo
```

**Stdout produced by the program:**

```text
jul-finished
```

**Lines written by ConsoleHandler to stderr:**

```text
INFO | Order accepted
WARNING | Low stock
```

**Three event lines in the JUL file**, typically `logs/orders-service-0.log` when there are no conflicts or rollovers:

```text
FINE | Preparing order cache
INFO | Order accepted
WARNING | Low stock
```

Because `append=true`, the file may contain lines from previous runs; the output above describes **a single run**. `FileHandler` can append a suffix when file name/lock conflicts occur and uses the `%g` generation pattern. Do not assume the file name is always identical when multiple JVMs compete for the same directory.

**Key takeaways:**

- `Files.createDirectories(...)` prepares the directory path.
- `new FileHandler(pattern, limit, count, append)` sets the pattern, byte limit, generation count, and append mode.
- `setFormatter(...)` produces readable plain-text logs. Without a formatter, JUL `FileHandler` defaults to XML.
- `logger.setUseParentHandlers(false)` stops events from reaching root handlers, avoiding duplicate console output in the example.
- Logger at `FINE`, file handler at `FINE`, console at `INFO`: **the logger level and each handler's level filter independently**.
- `close()` releases file handles and locks. Only close handlers owned by your program.

**Do not create a new `FileHandler` per request.** Initialize it once, hold a reference, and close it on application shutdown. In multithreaded applications or container-managed servers, removing or attaching shared handlers can affect concurrent requests; the example above only illustrates behavior in a standalone JVM.

## 10. Rotation and retention: preventing a service from filling the disk

An application log file can grow rapidly under `DEBUG` logging, high request volume, or repeated exceptions. Therefore, separate these concerns:

- **Rotation (rollover):** when a size or time threshold is reached, the active file is moved to an archive and a new file is opened.
- **Retention:** how long archives are kept, or the total size/count limits enforced by policy.
- **Compression:** compressing archive files when supported by the backend.
- **Quota/monitoring:** alerting before the filesystem runs out of space.

| Policy | Example | Things to watch |
| --- | --- | --- |
| Size-based | Rotate around 10 MB | A large event can exceed the limit before rollover triggers |
| Time-based | Rotate daily | Pay attention to time zones and scheduling |
| Size and date-based | `%d{yyyy-MM-dd}-%i` | Number of archives within a single day |
| Keep N archives | `max="3"` per strategy | Does not mean keeping exactly three days |
| Age-based | Delete files older than N days | May require a separate Delete/retention policy |
| Total size cap | Keep total archives under a threshold | Checked on rollover and appender startup |

**Rotation alone does not guarantee durability.** If the JVM is killed while data is still buffered, if the filesystem is full, or if a downstream collector fails, logs may be missing where you expect them. Standard file logging also does not replace a transaction log or audit trail that requires integrity guarantees and tamper resistance.

When running multiple services on the same disk, each service has its own file, yet you still must monitor **total disk usage**. One overly verbose `DEBUG` appender can exhaust disk space and prevent other services from writing logs as well.

## 11. Multiple JVMs of the same application: do not share one file on a shared filesystem

For example, scaling Orders to two JVMs:

```text
Not recommended without special coordination:
Orders JVM A ─┐
              ├─> logs/orders-service.log
Orders JVM B ─┘
```

Thread safety within a single JVM **does not guarantee** that two processes can safely write to and rotate the same file concurrently. You may encounter:

- File lock contention or unexpected alternative file names.
- Interleaved log lines making it hard to tell which instance emitted an event.
- One process rotating or renaming the file while the other is still writing.
- Overwritten archives, incomplete collection, or retention behaving differently than expected.

Two easier-to-operate options:

```text
Option A: per-instance file
Orders JVM A ──> logs/orders-instance-a.log
Orders JVM B ──> logs/orders-instance-b.log

Option B: stdout/stderr and collector
Orders JVM A ──> stdout ──┐
                          ├─> Collector (service=orders, instance=A/B)
Orders JVM B ──> stdout ──┘
```

If using per-instance files, the instance ID must be provisioned by infrastructure, controlled, collision-free, and free of dangerous path characters. Never derive file names from request/user input or unvalidated values.

On Docker/Kubernetes, local files may reside on ephemeral filesystems that are lost when a container is replaced. Many platforms prefer collecting stdout/stderr centrally; per-application files are then replaced by **collector labels such as service/namespace/pod**.

## 12. Write permissions, paths, and security

A simple yet common error is an appender failing to create a file due to **filesystem permissions**.

### Relative paths vs. absolute paths

`logs/orders-service.log` is a path **relative to the JVM's working directory**. If launched with Maven from the project directory, the path appears under the project. If launched by a service manager from another directory, the file may end up elsewhere.

In Linux deployments, you can choose an absolute path:

```text
/var/log/example/orders/orders-service.log
```

This is an illustrative path; an application does not automatically have permission to write to arbitrary directories. Prepare the directory, ownership, read/write permissions, rename permissions, and archive creation permissions through deployment configuration rather than running the application as root/administrator.

### What to check

- Is the resolved path inside an allowed log directory?
- Does the process have permissions to create, write, rename, and delete files for rotation?
- Could the log file accidentally sit inside a directory served publicly by a web server?
- Is another application sharing the same `fileName`/`filePattern`?
- Does the file name come from trusted configuration rather than unvalidated user input?
- Are retention, quotas, and disk monitoring configured?
- What data can users with log read access see?

**Log files can contain sensitive information.** Exception messages, SQL queries, internal paths, correlation IDs, and user-supplied data can persist for a long time. Never write passwords, tokens, API keys, auth cookies, payment card data, or PII into messages or context. Every log destination—console, file, and collector—needs access-control and retention policies.

## 13. Include request IDs in the file instead of creating a file per request

A per-application file typically contains logs from many concurrent requests. To find a specific request, attach `requestId` or `traceId` to events.

In Log4j2, `ThreadContext` can be used:

```java
import org.apache.logging.log4j.ThreadContext;

ThreadContext.put("requestId", "REQ-204");
try {
    LOG.info("Order processing started");
} finally {
    ThreadContext.remove("requestId");
}
```

This is an **illustrative code snippet**; place it inside a method of a class that has `LOG` and the appropriate imports. To display the context, the file layout can use:

```text
%d{ISO8601} %-5level [%t] %logger requestId=%X{requestId} - %msg%n%ex
```

In the SLF4J/Logback ecosystem, the equivalent concept is **MDC**. However, setting context does not automatically propagate it across `CompletableFuture` threads or thread pools: you must propagate and clean up context according to the execution lifecycle to avoid leaking IDs between requests.

Adding `traceId` to logs helps correlate events, **but it does not mean the system automatically creates distributed traces**. Across multiple JVMs, using service/instance IDs in metadata identifies which node produced each file or line without creating a file per request.

## 14. Difference between per-application logs and per-event-type logs

A single application may need multiple files for different purposes:

```text
orders-service/
├── application.log        (INFO and above)
├── errors.log             (ERROR and above)
└── audit.log              (valid audit events only)
```

This is **separating by event type within one application**, not a replacement for per-application files. Doing it properly requires dedicated appenders/handlers and filters. An `INFO` log in `application.log` may not appear in `errors.log`, while an `ERROR` log may appear in both `application.log` and `errors.log` if designed to fan out that way.

Do not assume two files containing the same `ERROR` represent a duplication bug. **Intentional fan-out** is different from **the same event being written twice to the exact same file** because both a child logger and root reference the same appender.

For auditing, naming a file `audit.log` is not enough. A reliable audit trail may require an explicit event schema, actor identity, modification controls, time synchronization, retention, and tamper-evident storage. Standard appenders do not satisfy these requirements on their own.

## 15. Verifying log files after deployment

Do not just see `LOG.info(...)` in code and assume file logging works. Verify along the entire event path:

1. **API:** does the code use JUL, SLF4J, or Log4j2?
2. **Backend:** is the corresponding provider/implementation present at runtime?
3. **Logger name:** does the emitting class/package match the logger configuration for that service?
4. **Level:** does the logger allow the required level?
5. **Appender/handler:** is the file appender actually attached to that logger?
6. **Additivity:** are records duplicated or dropped due to propagation?
7. **Path:** which working directory is the file path resolved from?
8. **Filesystem:** does the directory exist with write permissions, sufficient space, and rotation permissions?
9. **Rotation:** do the active file and archives match the configured pattern and policy?
10. **Collector:** if using centralized logging, is the file tailed/shipped and labeled properly?

You can trigger a distinctive `WARN` event and check the file and appender status. Do not enable `TRACE` globally in production indefinitely just to locate a log file.

## 16. Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Missing `orders-service.log` | Config not loaded, wrong path, missing permissions, or appender failed to initialize | Check classpath, status logs, working directory, and permissions |
| Billing logs appear in Orders file | Services share a path or logger routing is misconfigured | Separate `fileName` per service/instance and check `AppenderRef` |
| `DEBUG` missing from file | Logger or `AppenderRef`/filter blocks `DEBUG` | Check levels on both logger and appender |
| File has `WARN` but console does not | Console has a higher threshold or separate filter | Check `Console` `AppenderRef` |
| Event appears twice in the file | Duplicate additivity/`AppenderRef` path or code logs the same error at multiple layers | Keep a single path to the appender or fix duplicate log calls |
| File overwritten on restart | `FileAppender` `append=false` or unsuitable file policy | Configure append/rolling deliberately |
| File grows until disk is full | No rotation, no retention, or overly verbose logging | Configure rolling/retention, alerts, and quotas |
| Container file lost after deploy | Ephemeral filesystem or no collector | Use stdout/stderr or an appropriate volume/collector |
| File split across multiple names | Multiple JVMs contending for the file or JUL `%u` conflict handling | Separate per instance; check locks and pipeline |
| Exception lacks stack trace | Logging only `exception.getMessage()` or layout omits `Throwable` | Pass the exception object and check the formatter |
| File name does not match class name | File name is set by the appender, not the class name | Configure the file name per service |
| Editing `log4j2.xml` has no effect | Wrong file/backend in use or configuration not reloaded | Verify the active runtime configuration |
| File fails to roll over | Missing archive/rename permissions, full disk, or invalid pattern | Check status logs and filesystem |
| Two JVMs writing one file cause errors | Concurrent write/rotation contention | Separate per instance or switch to a collector |

## 17. Self-check questions

**Q1.** Does a per-application log file require a separate file for each class?  
**Answer:** No. Many class- or package-named loggers can share a single application file.

**Q2.** Why shouldn't multiple independent JVMs write to `orders-service.log` on a shared filesystem?  
**Answer:** It can cause lock contention, interleaved writes, and rollover failures; use per-instance files or collect via stdout.

**Q3.** In the Log4j2 example, where do `DEBUG` records go?  
**Answer:** The `demo.orders` logger allows `DEBUG`, the `OrdersFile` appender accepts `DEBUG`, and the console accepts only `INFO+`, so `DEBUG` goes only to the file.

**Q4.** Does `append="true"` guarantee logs are kept forever?  
**Answer:** No. It only appends instead of overwriting when opening the file; rotation, retention, and external actions can still move or delete data.

**Q5.** Does `DefaultRolloverStrategy max="3"` mean keeping exactly three days of logs?  
**Answer:** No. It configures the rollover strategy; it is not an age-based retention policy.

**Q6.** In JUL, which component writes to the file and when should it be closed?  
**Answer:** `FileHandler`; the owner should close it at the end of its lifecycle to release resources and locks.

**Q7.** Can Logback's `FileAppender` and Log4j2's `RollingFile` share one XML configuration file?  
**Answer:** No. Different backends have different classes, schemas, and configuration syntax.

**Q8.** Why might a service's relative log file appear in a different directory when launched by a service manager?  
**Answer:** Because relative paths are resolved from the process's working directory.

**Q9.** Should you generate file names from a client-supplied request ID?  
**Answer:** Not as a default; attach a validated ID to a log field instead to avoid file explosion, path traversal, and privacy risks.

**Key takeaway:** **A per-application log file is an output destination managed by the backend**, not a separate logger per class or per request. Choose files/destinations by service and instance, route class loggers into them, and then govern rotation, retention, permissions, sensitive data, and multi-JVM rules.

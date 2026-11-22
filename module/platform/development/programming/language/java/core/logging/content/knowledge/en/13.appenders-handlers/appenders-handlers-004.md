# File appender in Java Logging

## 1. What is a file appender?

In the **Appender and handler** architecture of Java Core Logging, a **file appender** is the component that receives log records accepted by the logging system, converts them into formatted data, and **writes them to a file**. It differs from Console Appender/ConsoleHandler, which writes to stdout or stderr.

For example, a file might contain:

~~~text
INFO  event=service.ready service=catalog
INFO  event=order.accepted orderId=ORD-17 requestId=req-42
WARN  event=inventory.slow dependency=stock
~~~

These are illustrative lines, **not a universal default format** across all Java libraries.

Three common technology groups:

- **Log4j 2:** File Appender, RollingFile Appender, and Log4j Core variants.
- **Logback:** FileAppender and RollingFileAppender, typically behind the SLF4J logging API.
- **java.util.logging (JUL):** uses the **FileHandler** class, a built-in Handler in the JDK. It performs a similar file-writing role but has its own API and configuration mechanism.

A file appender **does not manage all of logging on its own**: Logger, Level, Filter, Layout/Encoder/Formatter, file manager, and collector together determine whether a record actually reaches the file and is retained.

**When to use:** the application needs local log files for investigation, an agent must tail the file to send logs to a centralized system, or deployment policy requires storing logs on a dedicated volume. For applications running in containers that already have a stdout/stderr collection pipeline, local log files can increase operational overhead and the risk of losing logs when a container disappears.

## 2. Position of the file appender in the pipeline

~~~text
Application code
  logger.info("event=order.accepted ...")
                 |
                 v
           Logger / LoggerConfig
           level check, Filter
                 |
        +--------+------------+
        |                     |
        v                     v
  Console Appender        File Appender
  Dedicated Filter        Dedicated Filter
        |                     |
  Layout/Encoder          Layout/Encoder
        |                     |
  stdout/stderr           FileOutputStream
                              |
                         filesystem
                              |
                         log collector
                         if configured
~~~

Distinctions:

| Component | Function |
| --- | --- |
| **Logger** | Receives log calls, determines the level and source context |
| **Level/Filter** | Passes or drops records according to rules |
| **Appender/Handler** | Delivers records to a specific destination |
| **Layout/Encoder/Formatter** | Converts LogEvent/LogRecord into strings or bytes |
| **File manager/stream** | Opens the file, writes, flushes, and manages resources |
| **Collector/agent** | Reads the file and ships it to a storage platform if deployed |

An event can be routed to both **Console** and **File** simultaneously. Filters attached specifically to File may drop some events that Console still writes. If the **Logger has already blocked a record**, the Appender cannot recover it.

In frameworks that support a Logger hierarchy, **additivity** or a parent Logger's Handler can route logs to multiple destinations. If duplicate lines appear in the file, inspect the AppenderRef/Handler paths before assuming the application called the same log statement multiple times.

## 3. File Appender vs. RollingFile Appender

A **plain File Appender** writes to a single file, which can keep growing for the entire lifetime of the process. A **RollingFile Appender** adds policies to switch to a new file and manage archived files.

| Technology | Type | Built-in rolling? |
| --- | --- | --- |
| Log4j 2 | File | No |
| Log4j 2 | RollingFile | Yes |
| Log4j 2 | RandomAccessFile | No |
| Log4j 2 | RollingRandomAccessFile | Yes |
| Logback | FileAppender | No |
| Logback | RollingFileAppender | Yes |
| JUL | FileHandler | Has rotation mode by size and file count |

**Rolling** can be based on time, size, or both; it can also compress historical files and delete them according to a retention policy. **Append** only means appending data to the end of the file, **not rolling**.

With Log4j 2, file appenders have File, RandomAccessFile, and MemoryMappedFile variants with different I/O characteristics. Do not assume RandomAccessFile or MemoryMappedFile is always better than File: the cost depends on buffering, message size, filesystem, concurrency, and operational requirements.

## 4. append=true, append=false, and the risk of log loss

**append=true** generally means **appending** to an existing file when opened; **append=false** can truncate the old file upon opening.

~~~text
Existing file:
INFO service.started run=1

Restart with append=true:
INFO service.started run=1
INFO service.started run=2

Restart with append=false:
INFO service.started run=2
~~~

This is a conceptual behavior diagram. If rolling is enabled, the current file name and archived files are also governed by their own policies.

A common mistake is leaving **append=false** in production, causing a restart to wipe out previous records. Conversely, **append=true** without rotation can cause the file to grow indefinitely until the disk fills up.

**Decide together:** whether to append or overwrite, when to rotate files, how many files to retain, and where logs are collected and stored long-term.

## 5. File paths and OS permissions

Example file names:

~~~text
logs/application.log
/var/log/catalog/application.log
D:/logs/catalog/application.log
~~~

A **relative path** such as logs/application.log is typically resolved from the **JVM's working directory**. Running from an IDE, Maven, systemd, or a container may produce different results. An **absolute path** is more predictable in location, but requires environment-appropriate configuration.

Essential checks:

1. Does the process have permission to create and write the file?
2. Does the parent directory exist, or can the backend create it?
3. During rolling, does the process have permission to rename, compress, and delete archives?
4. Is the file on a persistent volume or on a container's ephemeral filesystem?
5. Are there quotas and alerts when disk space runs low?
6. Do file permissions/ownership restrict read access to log data?
7. Is the path taken directly from user input, risking **path traversal**?
8. If multiple JVMs write to the same file, is there a safe plan for concurrency, locking, and rollover?

Log4j 2 File Appender can create parent directories when needed, but do not assume this behavior across all systems. For deployment, **configuring the path via environment or deployment settings** is usually safer than hard-coding a personal machine path into library code.

## 6. Layout, Encoder, Formatter, and charset

Different frameworks use different names:

| Platform | Formatting component | Examples |
| --- | --- | --- |
| Log4j 2 | **Layout** | PatternLayout, JsonTemplateLayout |
| Logback | **Encoder** | PatternLayoutEncoder, appropriate JSON encoder |
| JUL | **Formatter** | XMLFormatter, SimpleFormatter, custom Formatter |

Data can be plain text:

~~~text
2026-11-09T12:00:00Z INFO catalog event=order.accepted orderId=ORD-17
~~~

or JSON:

~~~json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "catalog",
  "event": "order.accepted",
  "orderId": "ORD-17"
}
~~~

**A file appender does not turn logs into JSON by itself**; it requires a supporting Layout/Encoder/Formatter. The blocks above are illustrative rather than default output.

A good record typically includes **timestamp, level, logger/service, event, requestId or jobId, outcome, reasonCode**, and Throwable information when error investigation is needed. Choose **UTF-8** consistently with the log collector so Vietnamese or other non-ASCII text is not corrupted.

Unsanitized user data may contain newlines or control characters that cause **log injection**. Encoders should escape data appropriately; never log secrets, tokens, or sensitive payloads at the source.

## 7. Configuring Log4j 2 File Appender

If the runtime actually uses **Log4j Core**, create **src/main/resources/log4j2.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
    <Appenders>
        <File name="FILE"
              fileName="logs/application.log"
              append="true"
              bufferedIo="true"
              immediateFlush="true">
            <PatternLayout
                pattern="%d{ISO8601} %-5level %logger - %msg%n"
                charset="UTF-8"/>
        </File>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="FILE"/>
        </Root>
    </Loggers>
</Configuration>
~~~

Explanation of each element:

- **File** is a Log4j 2 Appender plugin; the name **FILE** is referenced by the Root Logger.
- **fileName** is the file path; for relative names, you must verify the working directory.
- **append=true** appends to the existing file.
- **bufferedIo=true** uses a buffer to reduce the number of write operations.
- **immediateFlush=true** flushes buffered data after each event according to the backend mechanism; it **does not guarantee fsync/durability**.
- **PatternLayout** outputs timestamp, level, Logger name, and message. Because the actual timestamp varies, there is no single fixed output file for this XML example.
- **Root level=info** only allows records meeting that threshold to reach the Appender. Other Filters can still reject them.
- The XML declares no Console Appender, so it does not automatically emit application logs to stdout.

Application code using the Log4j API:

~~~java
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public class CatalogService {
    private static final Logger LOG =
            LogManager.getLogger(CatalogService.class);

    public void started() {
        LOG.info("event=service.ready service=catalog");
    }
}
~~~

This is **a component class**, without a main() method to run standalone. You need **log4j-api** at compile time and a compatible **log4j-core** at runtime for the XML configuration to take effect.

### Other File Appender attributes

- **createOnDemand:** can defer file creation until an event actually reaches the Appender.
- **bufferSize:** sets the buffer size.
- **ignoreExceptions:** typically true by default; on write errors, the backend may report via **Status Logger** instead of throwing into business code.
- **locking:** applies file locking when needed, though semantics depend on the OS and incur overhead.
- **filePermissions/fileOwner/fileGroup:** usable when supported by the filesystem and system permissions.

A plain File Appender like the example above will not automatically rotate files by date or size.

## 8. Configuring FileAppender in Logback

If the application uses **SLF4J + Logback**, the configuration must use Logback syntax as follows:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <appender name="FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/application.log</file>
        <append>true</append>
        <immediateFlush>true</immediateFlush>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="FILE"/>
    </root>
</configuration>
~~~

Differences:

1. Logback uses the class **ch.qos.logback.core.FileAppender**, not Log4j's **File** plugin.
2. The path is declared via **file**, not a fileName attribute.
3. Logback uses an **encoder** to convert events into bytes; do not copy Log4j's PatternLayout syntax verbatim.
4. **append** and **immediateFlush** control writing behavior according to Logback's semantics.
5. **root level=INFO** and **appender-ref** determine which Logger sends events to FILE.
6. A plain FileAppender does not automatically roll when the file grows large.

SLF4J code:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger LOG =
            LoggerFactory.getLogger(OrderService.class);

    public void accepted(String orderId) {
        LOG.info("event=order.accepted orderId={}", orderId);
    }
}
~~~

This is an illustrative component class, not a standalone program. To actually write to a file, you need the **appropriate Logback provider at runtime**, a valid logback.xml file, and write permissions.

**Do not add slf4j-simple to an application already using Logback** just to get another destination; normally you should keep a single provider and configure an additional Appender inside that backend.

## 9. Rolling files for long-running applications

A service running continuously for days can produce huge files. **RollingFileAppender** is used to manage the current file and historical files based on conditions:

- **Time-based:** rotates files on a schedule or time boundary.
- **Size-based:** rotates when a size threshold is reached.
- **Combined:** caps the size of each file within each time period.
- **Archive:** uses a pattern with date/index and can gzip-compress old files.
- **Retention:** limits history count, total size, or file age depending on the backend.

### RollingFile configuration snippet for Log4j 2

~~~xml
<RollingFile name="ROLL"
             fileName="logs/application.log"
             filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz"
             append="true">
    <PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"/>
    <Policies>
        <TimeBasedTriggeringPolicy interval="1"/>
        <SizeBasedTriggeringPolicy size="10 MB"/>
    </Policies>
    <DefaultRolloverStrategy max="7"/>
</RollingFile>
~~~

Place the snippet above inside **Appenders** in the Log4j 2 configuration and reference ROLL under **Loggers**. **DefaultRolloverStrategy max=7 does not automatically mean keeping 7 days**; it is a limit on the index window per the strategy. To delete archives by age or total size, you need appropriate retention rules.

### RollingFile configuration snippet for Logback

~~~xml
<appender name="ROLL"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/application.log</file>
    <rollingPolicy class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
        <maxFileSize>10MB</maxFileSize>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>
    <encoder>
        <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

Place it inside **configuration**, add root/appender-ref, and verify against your actual Logback policy/version.

**Rolling does not automatically solve every retention problem.** When rotating files, verify archive naming, create/delete permissions, how the agent tails old files, compression, and behavior after a restart. The collector must also follow the new file so events are not lost.

## 10. FileAppender and external logrotate

A File Appender can hold an open file descriptor. If an external program renames or moves the file, the application may keep writing to the old file object instead of automatically opening the new path.

The Apache Log4j 2 documentation notes that File Appender **does not provide a mechanism to force reopening the file from an external application**. The **copy-truncate** approach can lose events between copying and truncating.

Consequences:

1. Prefer using the **backend's RollingFileAppender** if you want the appender to manage rotation itself.
2. Do not let **logrotate and RollingFileAppender manage the same file** unless you have designed, tested, and accepted the consequences.
3. If external rotation is required, establish a clear reopen/copy-truncate policy and evaluate event loss or duplication.
4. Check how the collector uses inode/file identity, how it tracks renamed files, and how it behaves when a file is truncated.

A log file rotated properly on the writer side is not guaranteed to be collected completely on the reader side.

## 11. Buffering, immediateFlush, and durability

A log call can pass through multiple buffers:

~~~text
Application -> LogEvent -> Appender/Handler
            -> framework buffer
            -> OutputStream
            -> OS filesystem buffer
            -> storage device
~~~

**Buffered I/O** batches bytes to reduce small write operations. **Flush** pushes buffered bytes down to the next layer. **fsync/force** aims to synchronize data at a lower level, though the final result still depends on the filesystem, mount options, and storage hardware.

**immediateFlush=true does not mean bytes have been durably written to disk.** This is critical when log retention is required after a crash or power loss.

| Option | Benefit | Trade-off |
| --- | --- | --- |
| immediateFlush=true | Reduces data held in backend buffer | May incur higher I/O overhead |
| immediateFlush=false | Can increase throughput | Buffered data may be lost on unclean shutdown |
| Large buffer | Batches more events | Memory usage and flush latency |
| Async logging | Reduces I/O work on business threads | Queue full, shutdown, backpressure |
| Network volume file | Shares data across hosts | Latency and complex consistency/locking |

If high log durability is required, do not rely on a single flush flag—design the **backend, OS, volume, collector, and retry/backup** together, and test sudden process termination.

## 12. Writing to a file from multiple threads and multiple JVMs

An Appender is normally designed by the backend for use by multiple threads within the **same JVM**. However, this **does not guarantee** that two JVM processes can safely write to or roll the same file.

- **Multiple threads, one Appender:** the backend typically coordinates writes, though you should still benchmark latency.
- **Multiple Appenders on the same file:** easily causes duplicate records or configuration conflicts.
- **Two JVMs on the same file:** atomic append/locking depends on the appender and the operating system.
- **Multiple pods on a network filesystem:** adds network locking issues and competing rollovers.

Logback has **prudent mode** to support multiple JVMs sharing a file via locking, but it **has a performance cost** and restrictions with rolling/compression. Log4j 2 has a **locking** option for File Appender, but advisory locks on some POSIX filesystems are not guaranteed to be respected by all processes.

A design that is usually easier to operate is **a separate file per instance**, or having each instance write to stdout/stderr and letting a collector aggregate by service, instance, requestId, and traceId.

## 13. JUL FileHandler: the built-in JDK option

**java.util.logging.FileHandler** is Java SE's file-writing Handler. It extends **StreamHandler** and can write to a single file or a rotating set of files by size.

Illustrative constructors:

~~~java
FileHandler oneFile = new FileHandler("logs/app.log", true);
FileHandler rotating = new FileHandler(
        "logs/app-%g.log", 10_000_000, 5, true);
~~~

This is a snippet and will not run standalone without imports, IOException handling, directory creation, and a close() call.

| Property | Meaning |
| --- | --- |
| **pattern** | File name pattern |
| **limit** | Approximate byte threshold per file |
| **count** | Number of rotating files |
| **append** | Append to existing file |
| **level/filter** | Threshold and rules for accepting records |
| **formatter** | Formatting; defaults to **XMLFormatter** |
| **encoding** | Charset used when writing |

JUL file name tokens:

- **%t**: temporary directory.
- **%h**: user's home directory.
- **%g**: generation number for rotation.
- **%u**: unique number to avoid conflicts with files currently in use.
- **%%**: literal % sign.

Unlike Logback/Log4j 2 RollingFileAppender, JUL's FileHandler only provides size/count-based rotation in its standard configuration. It does not natively provide all advanced scheduling, compression, and historical retention policies.

## 14. Standalone Java 17+ example: writing and reading back a log file

This program requires only the **JDK**, with no external dependencies. It uses a dedicated temporary directory to avoid overwriting user files.

Goals:

1. Logger at level ALL, Handler at INFO.
2. FINE log is blocked by the Handler; INFO and WARNING are written.
3. Formatter has a deterministic format and uses **formatMessage(record)** for JUL's **{0}** parameter.
4. Close the FileHandler before reading the data back.
5. Read the UTF-8 file and print its contents to stdout for verification.

Save the entire code as **FileLogDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class FileLogDemo {
    private static final Logger LOG =
            Logger.getLogger("examples.logging.file");

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("file-log-demo-");
        Path file = dir.resolve("application.log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.ALL);

        FileHandler handler = new FileHandler(file.toString(), false);
        handler.setEncoding("UTF-8");
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName()
                        + " | " + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        LOG.addHandler(handler);
        try {
            LOG.fine("event=cache.hit");
            LOG.info("event=service.ready service=catalog");
            LOG.log(Level.INFO,
                    "event=order.accepted orderId={0}", "ORD-17");
            LOG.warning("event=inventory.slow dependency=stock");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        List<String> lines =
                Files.readAllLines(file, StandardCharsets.UTF_8);
        System.out.println("records=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac FileLogDemo.java
java FileLogDemo
~~~

**Exact stdout**:

~~~text
records=3
INFO | event=service.ready service=catalog
INFO | event=order.accepted orderId=ORD-17
WARNING | event=inventory.slow dependency=stock
~~~

### Explanation of each result

1. **Files.createTempDirectory()** creates a new directory; the actual name varies, but it is not printed to stdout so it does not affect the expected lines.
2. **LOG.setUseParentHandlers(false)** prevents Handlers on parent Loggers from printing an extra record to stderr.
3. **LOG.setLevel(Level.ALL)** lets FINE pass the Logger check.
4. **handler.setLevel(Level.INFO)** blocks FINE while allowing INFO/WARNING into the file.
5. **formatMessage(record)** replaces **{0}** with **ORD-17**; this is JUL's parameter syntax, not SLF4J's **{}** placeholder.
6. **setEncoding("UTF-8")** paired with **StandardCharsets.UTF_8** keeps the writer and reader charsets aligned.
7. **handler.close()** flushes and closes the file/releases resources before Files.readAllLines() reads it.
8. **records=3** because there are two INFO records and one WARNING record; FINE was filtered out by FileHandler.
9. The three INFO/WARNING lines on stdout come from the for loop **printing the file contents just read**. FileHandler itself does not write to stdout.
10. The example leaves the temp file in place so learners can inspect it. In real tests, clean it up after the handler has been closed.

To verify the level difference, try changing **handler.setLevel(Level.WARNING)**. The file will then contain only WARNING even though the Logger remains at ALL.

## 15. Configuring JUL with logging.properties

In an application using JUL that does not replace Handlers programmatically, you can declare:

~~~properties
handlers=java.util.logging.FileHandler
.level=INFO

java.util.logging.FileHandler.level=INFO
java.util.logging.FileHandler.pattern=logs/application-%u.%g.log
java.util.logging.FileHandler.limit=10000000
java.util.logging.FileHandler.count=5
java.util.logging.FileHandler.append=true
java.util.logging.FileHandler.formatter=java.util.logging.SimpleFormatter
java.util.logging.FileHandler.encoding=UTF-8
~~~

Launch the compiled application with main class **com.example.Main**:

~~~bash
java -Djava.util.logging.config.file=logging.properties com.example.Main
~~~

This is a separate application launch template, **not the command to run FileLogDemo**. FileLogDemo intentionally creates its own FileHandler, disables parent Handlers, and uses a fixed Formatter.

Notes:

- **handlers** specifies the root Logger's Handlers according to LogManager configuration.
- Root **.level** and **FileHandler.level** are two separate thresholds.
- **pattern** includes **%u/%g** to handle unique filenames and generation numbers during rotation.
- **limit/count** rotates files when approaching the byte threshold; this is not date-based retention.
- **append=true** preserves the existing file per FileHandler's mechanism.
- **SimpleFormatter** replaces the default XMLFormatter; output includes timestamps/sources that may vary.
- The **logs/** path must match the working directory and the process's write permissions.
- Configuration is read when LogManager initializes; frameworks or application code may override it.

Do not put JUL FileHandler properties into logback.xml or log4j2.xml: key names, APIs, and handling differ.

## 16. Exceptions and stack traces in files

An error record should retain the **Throwable** so the backend can print the stack trace and cause chain:

**Log4j 2 / SLF4J:**

~~~java
try {
    persistOrder(orderId);
} catch (RuntimeException ex) {
    LOG.error("event=order.persist.failed orderId={}", orderId, ex);
    throw ex;
}
~~~

**JUL:**

~~~java
logger.log(Level.SEVERE,
        "event=order.persist.failed orderId=" + orderId, ex);
~~~

This is a snippet that depends on declared variables and methods. Using only **ex.getMessage()** typically omits the full stack trace and cause chain. However, **passing the Throwable is still not enough** if the chosen Layout/Encoder/Formatter intentionally omits exception details.

If log files contain multi-line stack traces, the collector must support **multiline** parsing or use an encoder with a dedicated exception field. Avoid logging the same stack trace at repository, service, and controller layers if all three simply rethrow the same error; one failure would be counted as multiple incidents.

## 17. File write errors and monitoring

| Incident | Symptoms and impact |
| --- | --- |
| Permission denied | Unable to create/open the file |
| Disk full or quota | Appender cannot write further records |
| Read-only filesystem | File writes are blocked after a deployment change |
| Invalid archive path | Rollover/compression fails |
| Stale file descriptor | After an external rename, the writer may not write to the new file name |
| Sudden process crash | Unflushed bytes or undrained async queues may be lost |
| Multiple processes on one file | Races/locks and rotation can cause errors |
| Collector tailing incorrectly | Missing/duplicate logs in the centralized system |

With Log4j 2, **ignoreExceptions** usually defaults to **true**: file write errors may be reported via **Status Logger** rather than thrown back to the LOG.info() call. This keeps logging from necessarily failing requests, but operators may fail to notice that logs are being lost if they do not monitor the backend.

With JUL, **Handler.ErrorManager** is the mechanism for handling/reporting I/O errors; do not assume logger.info() will always throw an IOException when the disk is full.

**Perform end-to-end verification:** emit an event with a known identifier, read the file at the exact path, and confirm the collector ingested it. A file merely existing does not prove the pipeline is still working.

## 18. File appenders in containers and multi-instance systems

For a service with multiple replicas:

- Have each instance **write to its own file**, or emit to stdout/stderr separately for the platform to collect.
- Do not assume a shared volume with append=true is safe for multiple JVMs.
- If using a network filesystem, evaluate locking, latency, consistency, and rollover in the exact target environment.
- In containers with ephemeral filesystems, files can vanish after a restart or pod replacement.
- If logs are sent to both console and file, a collector might read both sources and **double-count** them.
- Design events, requestId/traceId, and instance IDs so logs can be searched across services.
- Test shutdown behavior when the application uses an Async Appender or large buffers.

In many container deployments, **Console Appender + platform collector** is simpler than managing local files. A file appender remains appropriate when specific requirements call for it, provided you ensure log files are actually mounted, collected, or retained per policy.

## 19. Security, cost, and retention

Log files are often stored and backed up multiple times, so data must be controlled:

1. Never log **passwords, tokens, cookies, API keys**, card details, or sensitive payloads.
2. Avoid placing log files inside a web root or directories with overly broad read permissions.
3. Use appropriate **permissions/ownership** for the active file, archives, and backups.
4. Apply **retention** and monitor disk usage to prevent high-volume logs from filling the disk.
5. Log **stable event names** and necessary IDs rather than entire user data objects.
6. Escape newlines/control characters to reduce **log injection** risk.
7. Watch out for third-party exception messages that may contain internal data.
8. Do not rely on Filters as the sole secret-masking mechanism; retained records can still leak information.
9. For audit trails with legal requirements, design for completeness, integrity, and tamper resistance—do not assume a file appender provides these out of the box.
10. Track file/collector/backup costs and set limits appropriate to load.

**Log files are not automatically safe just because they reside on a local disk.** Access permissions and data lifecycle must be managed wherever records are copied.

## 20. Troubleshooting by symptom

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| File not found | Wrong path, wrong backend, createOnDemand, or config not loaded | Check working directory and runtime appender |
| Empty file | Logger/Filter not routing events to the file | Check levels, filters, and AppenderRef |
| Only ERROR/WARN visible | High threshold or Filter rejecting INFO | Inspect all pipeline stages |
| File in unexpected location | Relative path | Verify the JVM's cwd |
| Restart wipes old logs | append=false | Change config when history must be kept |
| File grows indefinitely | Plain FileAppender without rolling | Use RollingFile/retention |
| Duplicate logs | Additivity/multiple appenders/collector double-reading | Trace all routing paths |
| Stack trace missing | Only message logged or formatter drops Throwable | Use the overload accepting Throwable |
| Corrupted Unicode/Vietnamese text | Mismatched writer/reader charset | Verify UTF-8 end-to-end |
| Works in IDE, fails as service | Different process permissions, mounts, or cwd | Run test under the service user |
| Rollover does not run | Wrong policy, archive path, or permissions | Check config and diagnostics |
| New file empty after logrotate | Writer holds old descriptor | Check reopen/rolling mechanism |
| Missing tail logs after crash | Unflushed buffer/async queue | Check flush and shutdown policies |
| No Java error despite no writes | Appender reports via Status Logger | Observe backend diagnostics |

**Suggested troubleshooting sequence:** verify backend → confirm event is actually called → Logger level/Filter → AppenderRef/Handler → path and write permissions → encoding/Formatter → Status Logger/ErrorManager → rolling and collector.

## 21. Common misconceptions

**1. FileAppender automatically limits disk size.** False for a plain FileAppender; you need RollingFile or external management.

**2. append=true means rolling.** No; append only appends data when opening the file.

**3. flush equals fsync.** No; bytes may still sit only in the OS cache.

**4. Two JVMs writing to one file is safe by default.** You must understand locking and the filesystem; separate files per instance are usually easier to control.

**5. The file existing means logging works.** The file may be empty or may have stopped receiving data.

**6. Logback XML and Log4j XML are interchangeable.** No; they have different structures, classes, and encoders/layouts.

**7. Having a File Appender automatically produces JSON.** No; JSON depends on the appropriate Layout/Encoder.

**8. A Throwable just needs to be concatenated into the message.** No; you must pass the Throwable via the proper API and use a formatter that outputs it.

**9. External logrotate is always safe.** No; rename/copy-truncate can lose events or leave the writer holding the old file descriptor.

**10. Internal log files contain no sensitive data.** They may; data minimization, access control, and retention are still required.

## 22. File Appender implementation checklist

1. **Identify the backend:** Log4j 2, Logback, or JUL, and which configuration file is actually loaded.
2. **Choose the path:** clarify cwd, mounts, owner, and create/write/delete permissions.
3. **Set append properly:** avoid unintended truncation after restarts.
4. **Choose rolling/retention:** know when files rotate and how much history is kept.
5. **Configure Level/Filter:** check both Logger source and destination.
6. **Choose the format:** timestamp, level, event, context IDs, and Throwable if needed.
7. **Standardize charset:** UTF-8 from writer to collector.
8. **Measure I/O:** buffering, immediateFlush, async, and real latency.
9. **Avoid contention:** multiple JVMs/pods must have safe write and rotation paths.
10. **Monitor errors:** disk/quota/permissions/Status Logger and collector health.
11. **Protect data:** do not log secrets; control archives, backups, and retention.
12. **Test end-to-end:** emit events, read back the file, and test restart/rollover/crash scenarios as appropriate.

**Conclusion:** The **file appender** is the link that writes events passed by Logger/Filter to the filesystem. Using it properly requires understanding **Logger → Appender/Handler → Layout/Encoder/Formatter → file**, distinguishing **append from rolling**, and remembering that **flush does not guarantee durability**. That is the foundation for logs that aid investigation, avoid filling disks, and do not introduce data risks.

## 23. Official references

- [Apache Log4j 2 — File appenders](https://logging.apache.org/log4j/2.x/manual/appenders/file.html): File/RandomAccessFile, append, buffering, locking.
- [Apache Log4j 2 — Rolling file appenders](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html): RollingFile, TriggeringPolicy, and rollover.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): buffering, immediateFlush, and ignoreExceptions.
- [Logback — Console and File appenders](https://logback.qos.ch/manual/appenders-console-file.html): FileAppender, encoder, append, prudent.
- [Logback — Rolling File appenders](https://logback.qos.ch/manual/appenders-rolling.html): RollingFileAppender and retention.
- [Oracle Java 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): FileHandler, pattern, limit/count, Formatter, and API.

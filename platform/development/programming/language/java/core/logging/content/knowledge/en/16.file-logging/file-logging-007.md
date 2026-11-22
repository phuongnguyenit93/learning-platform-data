# Dynamic Log File Names in Java Logging

## 1. What Is a Dynamic File Name?

A **dynamic file name** in file logging is a log file name or path determined by a **value that varies by environment or execution context**, rather than always being fixed like `logs/application.log`. That value can be a service name, instance ID, deployment environment, validated job/batch code, time period, or a routing key.

For example:

~~~text
Fixed name:
logs/application.log

Name determined at application startup:
logs/application-node-02.log
logs/application-staging.log

Name selected by the job being processed:
logs/jobs/job-import-17.log
logs/jobs/job-export-04.log

Archive name changing on rollover:
logs/archive/application.2026-11-09.0.log.gz
~~~

These examples describe **three different mechanisms**. Simply having a variable in a path does not mean the appender will automatically switch files on every logger call.

- **Startup-time naming:** the value is substituted when loading configuration or creating the appender. For example, each instance writes to one file.
- **Event-time routing:** a routing appender selects the corresponding appender/file based on a value in **each event's** context. For example, Logback's `SiftingAppender` or Log4j2's `RoutingAppender`.
- **Rolling/archiving:** the archive file name changes by date/time and index during rollover. This is *archive naming*, not necessarily creating a separate file per tenant/job.

This lesson explains how to choose the right mechanism, a standalone Java 17 example with JUL, how to configure Logback/Log4j2, path protection, limiting file counts, and troubleshooting when logs do not appear in the expected place.

## 2. Why Use Dynamic File Names?

An application may need to separate logs across processing groups:

| Goal | Example | Typically Suitable Mechanism |
| --- | --- | --- |
| One file per instance | `service-node-a.log` | Startup property |
| One file per environment | `orders-staging.log` | Environment variable or deployment config |
| One file per batch job | `job-reconcile-17.log` | Per-job handler creation or MDC/ThreadContext-based routing |
| Archive by date/size | `orders.2026-11-09.2.log.gz` | Rolling policy/strategy |
| Send certain event types to a separate file | `audit.log`, `error.log` | Logger/AppenderRef/filter/marker, not necessarily dynamic file names |
| Trace a request across multiple files | `requestId` as a log field | Usually **do not** create a file per request; use correlation ID + collector |

Benefits when used properly: separating logs as required, avoiding multiple instances contending for a single file, supporting job log lookup, and managing files by lifecycle.

Drawbacks: each file can create its own file descriptor, buffer, appender, or worker; many file names cause **high cardinality**, increase the number of files to rotate/clean up, make collection harder, and can open vulnerabilities if file names originate from untrusted data.

**Important rule:** if you only need to **search logs by requestId**, logging `requestId` in structured logging/MDC and using a shared log stream is usually much more efficient than creating thousands of separate files.

## 3. Distinguishing Startup-Time Interpolation from Event-Time Routing

Suppose you have a file configuration:

~~~xml
<file>logs/app-${INSTANCE_ID}.log</file>
~~~

In Logback XML, `${INSTANCE_ID}` (when written with the framework's proper property syntax) is resolved when the appender configuration is created. Once the program is running, having a thread set MDC `INSTANCE_ID` to a different value **does not cause a regular FileAppender to automatically switch to a new file**.

In contrast, with an event-routing appender:

~~~text
Event A (jobKey=import-17) ---> Router ---> FileAppender A
Event B (jobKey=export-04) ---> Router ---> FileAppender B
Event C (jobKey=import-17) ---> Router ---> FileAppender A
~~~

The router reads the event's key and retrieves or creates the appropriate child appender. This is the approach used for **file names that change based on runtime context**.

### 3.1. Do Not Equate File Names with Logger Names

The logger `example.OrderService` identifies the event source; it does not necessarily correspond to a single file. Multiple loggers can write to the same file, and one logger can send events to multiple files depending on appenders/filters. Renaming a logger does not automatically create a new file without corresponding routing configuration.

### 3.2. Rolling Filenames Are Not Per-Request Filenames

A `RollingFileAppender` with a `fileNamePattern` containing `%d{yyyy-MM-dd}` and `%i` only renames **archives on rollover**. It does not mean every INFO event opens a new file named after a requestId. To combine per-job filenames with rolling, place the RollingFileAppender inside an appropriate routing/sifting mechanism and control the number of created appenders.

## 4. Safety Principles for File Naming Values

Dynamic file names often receive values from environment variables, command-line arguments, message queues, or HTTP requests. **This is potentially untrusted input**. Do not do this:

~~~java
// Wrong: rawJobId may contain /, .., control characters, or be too long.
Path file = Path.of("logs", rawJobId + ".log");
~~~

Values like `../secrets`, `C:\...`, `/`, `\`, `:`, unexpected Unicode characters, or `%` (which has special meaning in JUL FileHandler) can divert the path from its intended target, cause runtime errors, or create unexpected file structures.

### 4.1. Use Validated Internal Keys

An example policy for job keys:

~~~text
Allow only A-Z, a-z, 0-9, "_" and "-"
Length from 1 to 32 characters
No "." or path separator characters
Must not contain email, token, authentication code, or full username
~~~

Validation code in Java:

~~~java
// Illustration inside a class that has a rawKey variable.
if (!rawKey.matches("[A-Za-z0-9_-]{1,32}")) {
    throw new IllegalArgumentException("Invalid job key");
}
~~~

If you need to support display names with accents or special characters, generate a separate **safe internal key** for file naming, while handling the original label according to data policy and storing it as a log field if truly needed.

### 4.2. Keep the Target Directory Fixed with Proper Permissions

Use an application-configured directory such as `logs/jobs`. When constructing paths, you can normalize with `Path.normalize()` and verify the path stays within the allowed root directory. However, string/normalize checks **do not by themselves protect against symbolic links, mounts, or races on an untrusted filesystem**. The write directory must have strict permissions, preventing external users from replacing files or creating symlinks.

### 4.3. Limit Cardinality

A key can have valid characters and still generate millions of distinct values. For example, `requestId=req-unique-...` is suitable data for **searching logs**, but is usually a poor choice for **creating a separate file/appender per request**.

Limit the number of active jobs, child appenders, appender idle timeouts, total storage capacity, and retention. Separate **active open files** from **old archive files**: closing an appender does not automatically delete the file.

## 5. Standalone Java 17 Example: JUL FileHandler and Dynamic jobKey

`java.util.logging` (JUL) is built into the JDK, so `FileHandler` can be used to create a file from a validated key **at handler initialization time**. This example requires no Maven, SLF4J, Logback, or Log4j2.

Create **DynamicFileNameDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class DynamicFileNameDemo {
    private static final Logger LOG =
            Logger.getLogger(DynamicFileNameDemo.class.getName());

    private DynamicFileNameDemo() {
    }

    private static String validatedJobKey(String raw) {
        if (!raw.matches("[A-Za-z0-9_-]{1,32}")) {
            throw new IllegalArgumentException("Invalid job key");
        }
        return raw;
    }

    public static void main(String[] args) throws IOException {
        String raw = args.length == 0 ? "batch-17" : args[0];
        String jobKey = validatedJobKey(raw);

        Path directory = Path.of("target", "logs");
        Files.createDirectories(directory);
        Path file = directory.resolve("job-" + jobKey + ".log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(file.toString(), true);
        handler.setLevel(Level.INFO);
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        try {
            LOG.log(Level.INFO, "jobKey={0} phase={1}",
                    new Object[] {jobKey, "started"});
            LOG.log(Level.INFO, "jobKey={0} processed={1}",
                    new Object[] {jobKey, 3});
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.println("logFile=target/logs/job-" + jobKey + ".log");
        System.out.println("events=2");
    }
}
~~~

Compile and run in the directory where you want `target/logs` created:

~~~bash
javac -encoding UTF-8 DynamicFileNameDemo.java
java DynamicFileNameDemo
~~~

**Stdout of a successful run with the default key:**

~~~text
logFile=target/logs/job-batch-17.log
events=2
~~~

On the first run with a new file not held by another process, `target/logs/job-batch-17.log` contains:

~~~text
INFO jobKey=batch-17 phase=started
INFO jobKey=batch-17 processed=3
~~~

The example sets a custom JUL formatter with `formatMessage(record)`, because JUL uses `{0}`/`{1}` for message parameterization. Both INFO lines go to the file rather than the console: the program called `LOG.setUseParentHandlers(false)` and attached only the FileHandler.

Re-running with the same key when the file already exists: because `append=true`, two more lines may be appended to the file. **Do not assume the file always has exactly two lines** after multiple runs. In addition, JUL FileHandler uses a lock mechanism and may generate a `%u` suffix to avoid conflicts if the file is in use by another process; under concurrency, the actual path may differ from the expected one. The demo assumes a single process writing in a directory owned by the application.

### 5.1. Choosing a Different Name at Runtime

~~~bash
java DynamicFileNameDemo import-42
~~~

**Stdout**:

~~~text
logFile=target/logs/job-import-42.log
events=2
~~~

The corresponding file is chosen when the handler initializes, not per event. This command **does not create or delete the old file** for `batch-17`.

Testing an invalid key:

~~~bash
java DynamicFileNameDemo ../unsafe
~~~

The program throws `IllegalArgumentException("Invalid job key")` before creating the FileHandler; the stack trace and exit code depend on how the JVM displays uncaught exceptions. Do not treat a fixed stack trace transcript as expected output.

### 5.2. Why Use try/finally Instead of try-with-resources?

In Java 17, `java.util.logging.FileHandler`/`Handler` **does not implement `AutoCloseable`**, even though it has a `close()` method. Therefore, `try (FileHandler handler = ...)` **will not compile** as a resource in try-with-resources. The demo uses `try/finally` to ensure the handler is removed from the logger and the file handle/lock is closed.

Proper closing is critical when a process creates handlers for many jobs over time. Do not leave all handlers attached to the logger forever or leak file locks.

### 5.3. Special Patterns in JUL FileHandler

FileHandler interprets several tokens **in the file name pattern**:

| Token | Meaning |
| --- | --- |
| `%t` | System temporary directory |
| `%h` | Home directory per system configuration |
| `%g` | Generation index during rotation |
| `%u` | Unique index to resolve locked/conflicting files |
| `%%` | Literal percent sign |

Example:

~~~java
// Illustration: up to 3 generation files, approximately 1 MiB per file.
FileHandler rotation = new FileHandler(
        "target/logs/job-" + jobKey + "-%u.%g.log",
        1_048_576, 3, true);
~~~

This snippet belongs inside a method where `jobKey` has been validated and the directory has been created. After use, it must be removed from the logger and `rotation.close()` must be called in `finally`. `%g` and `%u` are not date/time syntax; JUL FileHandler does not have the same `fileNamePattern`/`maxHistory` policies as Logback.

## 6. Logback: Startup-Time Dynamic File Naming with Variables

With **SLF4J + Logback**, a `FileAppender` or `RollingFileAppender` can use property substitution when Logback reads `logback.xml`.

Simple `logback.xml` example:

~~~xml
<configuration>
    <appender name="INSTANCE_FILE"
              class="ch.qos.logback.core.FileAppender">
        <file>logs/service-${INSTANCE_ID:-local}.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="INSTANCE_FILE"/>
    </root>
</configuration>
~~~

`${INSTANCE_ID:-local}` is **Logback property substitution** syntax with a fallback value `local` when the property is not set. Once the variable is substituted, the appender writes to a fixed path. For example:

~~~bash
java -DINSTANCE_ID=node-02 -cp "..." example.Main
~~~

This is only a **JVM argument illustration**, not a standalone runnable command because the classpath `...` and `example.Main` depend on your project. With `INSTANCE_ID=node-02`, the expected file name is `logs/service-node-02.log`. Without the property, the expected name is `logs/service-local.log`.

**Important limitation:** a regular Logback FileAppender does not automatically substitute `INSTANCE_ID` from each log event's MDC. It resolves the file name when the appender is created; changing MDC on a thread afterward does not switch files. Property values supplied by the deployment environment must be controlled/sanitized before being used in paths.

This approach is suitable for separating files **by pod/instance**, environment, or a job where each process handles only one key for its entire lifecycle.

### 6.1. Where Do Properties Come From?

Logback supports property/configuration sources such as JVM `-D...` properties, environment variables, and properties declared in configuration, following specific lookup rules. This is not identical to Java's `System.getenv`; operators must verify actual variable names, default values, and scopes.

When configuration reload is enabled, changing a property can cause a new appender to be created; however, **continuous config reload should not be used as a per-request routing mechanism**. Event-based routing has dedicated tools.

### 6.2. RollingFileAppender with Per-Instance File Names

Startup properties can be combined in both the active file and archives:

~~~xml
<!-- Illustration placed inside <configuration>. -->
<appender name="ROLLING"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/service-${INSTANCE_ID:-local}.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/service-${INSTANCE_ID:-local}.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>7</maxHistory>
        <totalSizeCap>200MB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d %-5level %logger - %msg%n</pattern>
    </encoder>
</appender>
~~~

Archives change by date and instance, **not by requestId**. `maxHistory=7` limits the number of history periods according to the granularity of `%d`, which does not necessarily mean always keeping exactly seven files; `totalSizeCap` limits archives managed by the policy, not every file on the volume. An `appender-ref` must be configured on a logger/root so events reach this appender.

## 7. Logback: SiftingAppender for Per-Job Files

To create files based on a runtime key such as `jobKey`, Logback Classic provides **SiftingAppender**. It reads the value through a **discriminator**, then selects an existing child appender or creates a new one from the template in `<sift>`.

Example `logback.xml` for **validated jobKeys**:

~~~xml
<configuration>
    <appender name="JOB_SIFT"
              class="ch.qos.logback.classic.sift.SiftingAppender">
        <timeout>15 minutes</timeout>
        <maxAppenderCount>64</maxAppenderCount>

        <discriminator>
            <key>jobKey</key>
            <defaultValue>unassigned</defaultValue>
        </discriminator>

        <sift>
            <appender name="FILE-${jobKey}"
                      class="ch.qos.logback.core.FileAppender">
                <file>logs/jobs/job-${jobKey}.log</file>
                <append>true</append>
                <encoder>
                    <pattern>%d{HH:mm:ss.SSS} %-5level jobKey=%X{jobKey} %msg%n</pattern>
                    <charset>UTF-8</charset>
                </encoder>
            </appender>
        </sift>
    </appender>

    <root level="INFO">
        <appender-ref ref="JOB_SIFT"/>
    </root>
</configuration>
~~~

In Logback Classic, the default discriminator for `SiftingAppender` is `MDCBasedDiscriminator` when no class is explicitly specified. It reads `jobKey` from MDC; if missing, it uses `defaultValue=unassigned`, preventing an empty path.

Java scoping code (snippet in a service with an SLF4J logger `LOG` and a `validatedJobKey` helper):

~~~java
// Requires org.slf4j.MDC and a valid SLF4J logger.
String key = validatedJobKey(rawJobKey);
org.slf4j.MDC.put("jobKey", key);
try {
    LOG.info("job started");
    executeJob();
    LOG.info("job completed");
} finally {
    org.slf4j.MDC.remove("jobKey");
}
~~~

If `key=import-42`, events in that scope normally go to `logs/jobs/job-import-42.log`; when the key changes to `export-04` in another scope, SiftingAppender selects a different child appender.

This is **event-time routing**, unlike the startup-time `INSTANCE_ID` property substitution in Section 6. Having validated keys and a clear scope lifecycle is essential.

### 7.1. Do Not Use Arbitrary Raw Request IDs, Usernames, or Tenant IDs

This pattern is only suitable for a relatively small, managed set of keys. If a system handles one million requests/day and each request carries a unique `jobKey`, SiftingAppender can create huge numbers of appenders/files. Do not open a separate file per request just because it is technically possible.

`timeout` allows idle child appenders to be closed and removed from memory; `maxAppenderCount` (in Logback versions that support it) caps the number of managed child appenders. **They are not deletion policies for files already on disk**. Separate retention and storage cleanup are required.

A child appender can be closed and later recreated when the key reappears; with `append=true`, the existing file can be appended to. Verify concurrency and thread-safety policies, especially if multiple instances write to the same path.

### 7.2. MDC Scope and Thread Pools

MDC is typically thread-bound. If a worker thread is reused for another job without calling `MDC.remove("jobKey")`, logs from the next job can go into the previous job's file. `finally` is a critical requirement.

When a job crosses `CompletableFuture`, an executor, or another thread, context is not propagated automatically by default. You need framework-provided context propagation or custom task wrappers that transfer/restore context appropriately and then clean up the thread context. Do not just set MDC on the request-receiving thread and assume all other threads see the same value.

### 7.3. Combining SiftingAppender with Rolling

Replacing the child `FileAppender` inside `<sift>` with a `RollingFileAppender` allows per-job active and archive files. In that case, `fileNamePattern` must distinguish both the job and rollover periods, such as `logs/jobs/archive/job-${jobKey}.%d{yyyy-MM-dd}.%i.log.gz` when using a size-and-time policy.

However, **having a separate rolling appender per job** means each job also carries the overhead of active files, archives, and retention. For high cardinality, console + structured logging with a `jobKey` field and a collector is usually easier to operate.

## 8. Log4j2: RoutingAppender with ThreadContext

**Apache Log4j 2** provides **RoutingAppender**, which selects a route/appender based on a key evaluated from the log event. For applications using the Log4j API directly, `ThreadContext` supplies fields attached to the event.

Usage code (snippet in a service that already has a Log4j2 `LOG` and a validated key):

~~~java
// Requires log4j-api, LOG, and validatedJobKey(...).
String key = validatedJobKey(rawJobKey);
org.apache.logging.log4j.ThreadContext.put("jobKey", key);
try {
    LOG.info("job started");
    executeJob();
    LOG.info("job completed");
} finally {
    org.apache.logging.log4j.ThreadContext.remove("jobKey");
}
~~~

Example `log4j2.xml` configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Routing name="JOB_ROUTER">
            <Routes pattern="$${ctx:jobKey}">
                <Route>
                    <File name="JOB-${ctx:jobKey}"
                          fileName="logs/jobs/job-${ctx:jobKey}.log"
                          append="true">
                        <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5p jobKey=%X{jobKey} %m%n"/>
                    </File>
                </Route>
            </Routes>
        </Routing>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="JOB_ROUTER"/>
        </Root>
    </Loggers>
</Configuration>
~~~

**Lookup syntax in RoutingAppender is critical:**

- `<Routes pattern="$${ctx:jobKey}">` uses **two `$` signs** in Log4j2 configuration to defer route key lookup until event processing time.
- Inside `<Route>`, child appender attributes use **one `$` sign**, such as `fileName="logs/jobs/job-${ctx:jobKey}.log"`, because they are evaluated when the dynamic child appender is created for that route.
- A `<Route>` without a `key` attribute acts as the default route: in the configuration above, it can create a child appender for each route key value.

**Scope of this example:** use only when code has placed a valid `jobKey` in ThreadContext before every event reaches the router. In real applications, you must design a **fallback for events without a key** (for example, a shared appender referenced by a matching route) and key validation to prevent invalid file names. Never allow raw HTTP/request values to be used directly in file names without validation.

Do not write `${ctx:jobKey}` into the `fileName` attribute of a regular `File`/`RollingFile` outside `RoutingAppender` and assume the file name changes per event. In regular appenders, file initialization attributes are not re-evaluated on every incoming log event.

### 8.1. Managing Route Lifecycles

RoutingAppender can create dynamic appenders for many keys. In supported Log4j2 versions, `IdlePurgePolicy` helps close routes that have not been used for a given duration. This reduces the number of open appenders, **but does not automatically delete files on disk**.

When using RoutingAppender per tenant/job, review:

- Number of active routes and open appenders/file descriptors.
- Behavior when a key stops emitting events.
- Number of created files and archive cleanup strategy.
- Events writing to ThreadContext, async context propagation, and cleanup.
- Rollover, file deletion, and collector behavior when appenders close and reopen.

### 8.2. Combining RoutingAppender with RollingFile

If each job requires daily and size-based archiving, you can replace the `File` appender inside `<Route>` with `RollingFile` and `<Policies>`. This is a **replacement child appender snippet**, not a standalone XML file:

~~~xml
<RollingFile name="JOB-${ctx:jobKey}"
             fileName="logs/jobs/job-${ctx:jobKey}.log"
             filePattern="logs/jobs/archive/job-${ctx:jobKey}.%d{yyyy-MM-dd}.%i.log.gz">
    <PatternLayout pattern="%d %-5p %m%n"/>
    <Policies>
        <TimeBasedTriggeringPolicy interval="1"/>
        <SizeBasedTriggeringPolicy size="10MB"/>
    </Policies>
    <DefaultRolloverStrategy max="10"/>
</RollingFile>
~~~

`%d` represents the time period and `%i` distinguishes archives within the same period when the size threshold is reached. In Log4j2, `DefaultRolloverStrategy max="10"` relates to the archive index window per strategy, **not simply keeping 10 days**. If you need to delete archives by age or total size, you must configure an appropriate delete action and test it in a staging environment.

## 9. A Simpler Alternative When You Only Need to Filter/Search by Job

Not every "dynamic" requirement actually needs **separate physical files**. If you need to find events belonging to a job, you can often keep **a single shared file or JSON stream** and attach a `jobKey` field:

~~~text
2026-11-09T10:00:00Z INFO jobKey=import-42 operation=read count=150
2026-11-09T10:00:01Z INFO jobKey=export-04 operation=write count=50
2026-11-09T10:00:02Z WARN jobKey=import-42 operation=read retry=1
~~~

This is illustrative data. A log collector/search engine can filter by the `jobKey` field without needing thousands of different files, **provided the encoder and pipeline actually preserve jobKey as a structured field**. A `jobKey=...` substring in a message is just plain text if the system does not parse it into a field.

When separate files are required by organizational policy, permissions, or offline batch workflows, routing remains appropriate. Still, clearly define who owns the files, when they close, how long they are retained, and how they are collected.

## 10. Safe File Naming in Multi-Instance Systems

Suppose three instances all create `logs/jobs/job-import-42.log` on a network filesystem. Having the same job name is not enough to prevent collisions. Multiple processes can write concurrently, causing file lock issues, reordering, corruption, or rollover conflicts. Therefore, the design should include an **instance** key in the path:

~~~text
logs/node-01/jobs/job-import-42.log
logs/node-02/jobs/job-import-42.log
logs/node-03/jobs/job-import-42.log
~~~

The instance name must be sanitized by the same safety criteria. In containerized infrastructure, consider writing to stdout and collecting logs centrally with service, pod, and job fields rather than trying to create/mount a shared file structure across multiple nodes.

**Do not treat dynamic file names as a security isolation guarantee.** If all files on a volume share the same read permissions, separating files by tenant does not prevent cross-access. You need filesystem permissions, ownership, and collector policies, not just file names.

### 10.1. Archive Names and Retention

When using rolling:

~~~text
Active:  logs/node-01/jobs/job-import-42.log
Archive: logs/node-01/jobs/archive/job-import-42.2026-11-09.0.log.gz
~~~

Rollover does not necessarily occur on the clock if no new events arrive; retention may be enforced on rollover/startup or according to a specific policy. An archive `totalSizeCap` on one rolling policy does not cap all files on the volume, especially when **multiple policies/child appenders** exist.

### 10.2. Do Not Generate File Names from High-Resolution Timestamps Per Event

A dangerous design pattern:

~~~text
logs/app-20261109T104201001.log
logs/app-20261109T104201002.log
logs/app-20261109T104201003.log
...
~~~

If every event gets its own file name, the system can create thousands of small files per second. That is not an appropriate substitute for continuous event logging. Timestamps should only be used for **file periods** defined by a rolling policy or a batch with a clear lifecycle.

## 11. Performance and Operations

| Risk | Why It Happens | Mitigation |
| --- | --- | --- |
| Too many file descriptors | Each route/job opens an appender/file | Limit active routes; close idle appenders |
| Many small files | High-cardinality job/request keys | Consolidate into shared structured logs; do not split per request |
| Logs written to wrong file | Stale MDC/ThreadContext from a previous task | Use `finally` and proper context propagation |
| File fails to open | Permissions, invalid path, missing directory | Check startup status and resolved paths |
| Fragmented data | Changing file names not detected by agent | Configure collector to recognize patterns and rollovers |
| Cross-instance collisions | Multiple processes writing to the same path | Separate path per instance, or stdout + collector |
| Missing logs in expected file | Locked handler, JUL added unique index; router picked fallback | Check locks, route keys, and appender status |
| Old files not deleted | Missing retention or cleanup runs only on rollover | Lifecycle policies, volume monitoring |
| High I/O/CPU cost | Appender creation, file opens, sync flush, archive compression | Measure p95/p99, bytes/s, allocations, and appender count |
| Sensitive data exposure | User input/sensitive IDs appear in file names | Use safe internal keys, permissions, and retention |

When using asynchronous appenders, events may sit in a queue before being written. When output is flushed and how MDC is captured/propagated depend on the backend/version; verify in practice. Do not assume an async appender guarantees durability on crash or when the queue is full.

## 12. How to Test a Dynamic File Name Configuration

1. **Identify the dynamic type:** startup property, event-time routing, or rolling archive? Document where the value is produced and evaluated.
2. **Verify the key source:** is it a validated job code, a trusted instance ID, or raw request input? Never use unvalidated strings to build paths.
3. **Check runtime dependencies:** JUL is built into the JDK; Logback and Log4j2 require the proper dependencies/providers/backends.
4. **Check config files:** are `logback.xml` and `log4j2.xml` loaded properly; is the appender attached to a logger/root?
5. **Test two distinct keys:** e.g., `import-42` and `export-04`, and confirm each event goes to the right file without confusing active and archived files.
6. **Test missing keys:** does Logback's `defaultValue` work? For Log4j2 Routing, does the fallback route target a safe shared file?
7. **Test invalid keys:** strings with slashes, `..`, control characters, or excessive length must be rejected or mapped to a safe internal key.
8. **Test thread reuse:** finish one job and run another on the same executor thread; no events may leak into the wrong file.
9. **Test concurrent instances:** does each instance have file ownership, and are lock/rollover conflicts or `%u` suffixes handled?
10. **Test high volume and lifecycle:** generate many valid keys in a test environment and measure open files, queues, rollover, cleanup, and actual disk usage.
11. **Check the collector:** does the agent pick up new files created after startup, renames on rollover, and compressed archives?
12. **Check security:** file permissions, symlinks, paths, retention, and data present in both file names and log contents.

Instead of checking only "does the file exist," verify that **the right events land in the right file, with no duplicates, no losses, and no unbounded resource leaks**.

## 13. Common Mistakes When Using Dynamic File Names

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Putting `${jobKey}` in a regular FileAppender and changing MDC | File name does not change per event | Use SiftingAppender/RoutingAppender |
| Using requestId as the file name | Countless small appenders/files | Keep requestId as a log field |
| Not sanitizing keys | Path traversal, invalid characters/paths | Whitelist and generate internal keys |
| Forgetting `finally` to clear context | Reused thread logs to the old job's file | Remove/restore MDC/ThreadContext |
| No fallback value | Events without a key produce abnormal file names | Design safe route/`defaultValue` |
| Missing `%i` in archive name when size+time rolling is needed | Archive name collisions within the same period | Use a pattern matching the policy |
| Assuming `maxHistory` limits all files | Volume still grows from active files/other keys | Monitor all files and system-wide retention |
| Two JVMs writing to the same file | Lock/rollover conflicts | One file per instance or a collector |
| Expecting JUL `%u` to always create the exact specified name | Locked files may get a suffix | Check target path and process model |
| Duplicate direct + routed appender references | An event may be written twice | Define a single routing path to each target |
| Assuming closing an appender deletes the file | Old files remain on disk | Configure separate cleanup/retention |
| Not informing the agent of new patterns | Logs hit the right file but miss search indexing | Configure dynamic file discovery/collection |

## 14. Practice Exercises

1. **Classification:** Do `service-node-02.log`, `job-import-42.log`, and `service.2026-11-09.log.gz` belong to startup naming, event routing, or archive rolling? Explain the boundaries.
2. **Run JDK 17:** Create `DynamicFileNameDemo.java`, run it with the default key and with argument `export-04`. Verify stdout and `target/logs/job-export-04.log`.
3. **Invalid keys:** Test `../unsafe`, `a/b`, a string longer than 32 characters, and `%`. Why must the program reject them?
4. **JUL:** Replace the non-rotating FileHandler constructor with `new FileHandler(pattern, limit, count, true)` using `%g` and `%u`. What do the generation and unique index mean in file names?
5. **Logback:** Explain why `${INSTANCE_ID}` in a regular FileAppender does not change when MDC `jobKey` changes. When is SiftingAppender needed?
6. **Sifting:** Create one job with `jobKey=import-42` and one with `jobKey=export-04`, then verify two separate files exist. Confirm MDC is always removed in `finally`.
7. **Log4j2:** From the RoutingAppender example, explain the two `$` signs in `$${ctx:jobKey}` on `Routes pattern` versus the single `$` sign in the child appender's file name.
8. **Cardinality:** An API serves 5,000 requests/s and each request generates a file name. How many new files could be created in one minute? Why should structured logging be used instead?
9. **Multi-instance:** Propose a file naming scheme using both instance ID and jobKey; describe the risks when two JVMs write to the same file on a network filesystem.
10. **Production:** Design a monitoring checklist for file descriptors, file count, free disk space, rolling, context leaks, and collector lag for a system using dynamic file names.

## 15. Official References

- Java SE 17 — `java.util.logging.FileHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html
- Logback Manual — SiftingAppender: https://logback.qos.ch/manual/appenders-async-sift.html
- Apache Log4j 2 — RoutingAppender: https://logging.apache.org/log4j/2.x/manual/appenders/delegating.html
- Apache Log4j 2 — Configuration/property substitution: https://logging.apache.org/log4j/2.x/manual/configuration.html

**Remember:** dynamic file names can be **fixed at appender initialization**, **routed per log event**, or changed only during **archive rolling**. In JUL, initialize FileHandler with a safe key and remember to close the handler; in Logback, use properties for per-instance files and SiftingAppender for per-job files; in Log4j2, use RoutingAppender with ThreadContext. Before creating a new file per key, control **input validation, file count, thread context, write permissions, retention, and log collection**.
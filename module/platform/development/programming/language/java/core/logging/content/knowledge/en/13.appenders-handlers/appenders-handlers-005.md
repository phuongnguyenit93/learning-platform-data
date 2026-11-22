# Rolling Appenders in Java Logging

## 1. What is a rolling appender?

A **rolling appender** is an appender that writes logs to a file with an added **rollover** mechanism: when a condition is met, the file currently being written to is moved to an *archive*, and a new file begins receiving subsequent log events. This prevents a single file from growing indefinitely, makes it easy to organize logs by time, and allows appropriate retention policies to be applied.

In common Java logging ecosystems:

- **Logback** uses `ch.qos.logback.core.rolling.RollingFileAppender` together with a *rolling policy*.
- **Apache Log4j 2** uses the `RollingFile` plugin, combining a *triggering policy* (when to roll over) and a *rollover strategy* (how to roll over, store, and delete).
- **`java.util.logging` (JUL)** provides `FileHandler`, which supports file rotation by size and file count, though it is not called `RollingFileAppender` and does not use the same XML syntax as Logback/Log4j2.

A rolling appender **is not a logger**, does not independently decide all log levels, and does not automatically collect logs from every service. Application code calls a logger; the backend processes levels/filters and creates a log event, and then the appender receives and writes the event to the configured path.

Diagram:

~~~text
Java code -> Logger -> filter/level -> Logging event
                                      |
                                      v
                             Rolling file appender
                                      |
               +----------------------+--------------------+
               |                                           |
         Active log file                           Triggering condition?
         logs/app.log                         time/size/startup/custom...
               |                                           |
               +----------------------+--------------------+
                                      |
                                      v
                           Rollover / archive
                       logs/archive/app-....log.gz
                                      |
                                      v
                        Retention / cleanup policy
~~~

Depending on the configuration, rollover can rename, move, compress the archive, or switch writing to a new file. **Rollover conditions and archive deletion conditions are two distinct types of rules.**

## 2. Distinguishing active file, rollover, archive, and retention

| Concept | Meaning | Example |
| --- | --- | --- |
| Active file | The current file the appender is writing to | `logs/app.log` |
| Trigger / triggering policy | The condition that causes the appender to evaluate whether to roll over | Date change, reaching 10 MB, JVM startup |
| Rollover | The operation of ending a write cycle, creating an archive, and opening/switching the active file | `app.log` is archived as `app-2026-11-09.log.gz` |
| Archive file | A file from a completed cycle, possibly compressed | `logs/archive/app-2026-11-09.0.log.gz` |
| Rolling policy / rollover strategy | How archive naming, location, and rollover behavior are organized | `TimeBasedRollingPolicy`, `DefaultRolloverStrategy` |
| Retention | The policy for keeping and deleting old archives | Keep 7 days or cap total archives at 1 GB |
| Compression | Compressing archives to save disk space | `.gz` or `.zip` suffix |

Illustrative example: the appender writes data to `logs/app.log`. When the rollover period arrives, data from the previous period is moved to the archive `logs/archive/app-2026-11-09.log.gz`, while `logs/app.log` continues receiving new events.

**Do not assume rollover is a timer that automatically deletes files at exactly 00:00 across all backends.** Many time-based configurations evaluate whether to roll over when a new log event is written after crossing the time boundary. If the application emits no events for several hours, the archive may only appear when the next record arrives or when an appropriate startup/cleanup mechanism runs.

**Retention is not equivalent to long-term backup.** An archive can be deleted according to policy and become unrecoverable. If logs are required to be retained for regulatory compliance, you must design dedicated durable storage/backup and access controls rather than relying solely on the appender's archive directory.

## 3. When should you use a rolling appender?

A rolling appender is especially valuable when an application **needs to write log files to a local machine/volume** over a long period:

1. **Long-running servers:** logs grow daily, needing an easy-to-follow active file while keeping daily historical archives.
2. **Batches/jobs generating many events:** a single day's file can become very large, so combining size and time conditions is helpful.
3. **Time-based incident investigation:** archive names containing the date or period help narrow down the search quickly.
4. **Disk space management:** set limits on the number of retained periods and total archive size to prevent old files from accumulating indefinitely.
5. **Forwarding logs to a collector:** an agent can read the active file and archives if designed to work with the rotation mechanism.

Not every environment needs local rolling files. In **containers/Kubernetes**, a common pattern is for the application to write to stdout/stderr using `ConsoleAppender`, while the runtime and agent handle collection and rotation at the infrastructure layer. Running both in-container rolling files and external log rotation without coordination can complicate log paths and increase costs.

## 4. Logback's RollingFileAppender: key components

Logback Core provides `RollingFileAppender`. When using Logback as the backend for SLF4J, application code still calls SLF4J's `info(...)`, `warn(...)`, and `error(...)` methods; the XML configuration determines the file and rollover behavior.

Example daily Logback configuration:

~~~xml
<appender name="ROLLING"
          class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>logs/app.log</file>
    <append>true</append>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
        <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
        <maxHistory>7</maxHistory>
        <totalSizeCap>1GB</totalSizeCap>
    </rollingPolicy>

    <encoder>
        <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        <charset>UTF-8</charset>
    </encoder>
</appender>
~~~

This is a **snippet inside `<configuration>`**; it is incomplete on its own because the appender must be referenced in `<root>` or `<logger>`.

### 4.1. `<file>`: the active file name

`<file>logs/app.log</file>` specifies the path the application is currently writing to. When using a relative path, the actual location depends on the JVM process's working directory. In a different deployment, the same relative path may point to a different directory.

You can omit `<file>` in certain supported rolling configurations so that the active file name changes according to the pattern; however, if you want a stable active file name for an agent to read, explicitly declaring `<file>` is usually easier to operate.

### 4.2. `<fileNamePattern>`: the archive name

The pattern `app.%d{yyyy-MM-dd}.log.gz` generates archive names with a date component. The `.gz` suffix instructs Logback to compress the archive using its built-in compression support. The `%d{...}` token determines the time period; `%d{yyyy-MM-dd}` is typically daily, whereas `%d{yyyy-MM-dd_HH}` provides hourly granularity.

**Do not confuse the archive file pattern with the log line content pattern.** `fileNamePattern` names the file; `<encoder><pattern>...` determines the text written inside the file.

### 4.3. `<maxHistory>`: how many periods to keep

`<maxHistory>7</maxHistory>` generally means keeping historical periods corresponding to the pattern's time unit: for daily archives that is roughly 7 daily periods, and for monthly archives 7 monthly periods. It is not simply a count of **seven files**: if there are multiple archives in one day, there can still be multiple files belonging to a single period.

### 4.4. `<totalSizeCap>`: total archive size limit

`<totalSizeCap>1GB</totalSizeCap>` sets a cap on the total size of archives managed by the rolling policy. It **is not a hard cap on every byte on the volume**: the active file, files not matching the pattern, backup data, temporary files, and files created by other systems can fall outside this scope.

Typically `maxHistory` must be configured for `totalSizeCap` to take effect in a time-based policy. Cleanup is tied to rollover cycles and startup options; **you should not promise that disk usage will always remain below the cap at every instant**. If the application writes very little or stops for a long time, cleanup timing may differ from expectations.

### 4.5. `<append>`, encoder, and appender reference

`<append>true</append>` allows continuing to write to an existing file rather than truncating it on startup. The encoder converts events into bytes: patterns can include `%level`, `%logger`, `%msg`, `%n`, or `%X{requestId}` for MDC. If `ROLLING` is not attached to a logger/root via `<appender-ref ref="ROLLING"/>`, the appender definition will not receive any logs.

## 5. Runnable Java 17 example: SLF4J + Logback + RollingFileAppender

This example uses **JDK 17, Maven, SLF4J 2.0.17, and Logback Classic 1.5.18** to run a small project. This is a compatible pair of versions for hands-on practice, **not a claim that they are the latest versions**. Real projects should use versions/BOMs that have been vetted against security and dependency policies.

Directory structure:

~~~text
rolling-log-demo/
  pom.xml
  src/main/java/example/RollingDemo.java
  src/main/resources/logback.xml
~~~

### 5.1. Create pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>rolling-log-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.17</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.RollingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`slf4j-api` is the facade that Java code calls. `logback-classic` provides the provider/implementation; Maven will bring the required transitive dependencies onto the classpath. Do not add another SLF4J provider such as `slf4j-simple` to the example, as that can cause multiple competing providers.

### 5.2. Create RollingDemo.java

~~~java
package example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class RollingDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(RollingDemo.class);

    private RollingDemo() {
    }

    public static void main(String[] args) {
        String jobId = "J-17";

        LOG.debug("jobId={} step=prepare", jobId);
        LOG.info("jobId={} phase=started", jobId);
        LOG.warn("jobId={} retry={} reason={}",
                jobId, 1, "temporary-unavailable");
        LOG.info("jobId={} phase=finished processed={}",
                jobId, 3);
    }
}
~~~

The program does not open a file with `FileOutputStream`, does not call `RollingFileAppender` directly, and has no awareness of the rollover schedule. All file writing belongs to the Logback configuration.

### 5.3. Create logback.xml

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%level %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>target/logs/app.log</file>
        <append>true</append>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>target/logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%level %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
~~~

Place the file at `src/main/resources/logback.xml`. When running Maven from the project root directory, `target` is created during the build and Logback can create subdirectories for the log file along the configured path. In other environments, verify the working directory, write permissions, and appender initialization status.

**Both appenders receive the same log events**: `CONSOLE` writes to stdout, and `ROLLING` writes to the file. This is not duplicate logging caused by calling the logger twice; it is the intentional routing of the same event to two destinations.

### 5.4. Compile, run, and verify the output

From the `rolling-log-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

**Three application log lines are printed to stdout** with the configuration above:

~~~text
INFO jobId=J-17 phase=started
WARN jobId=J-17 retry=1 reason=temporary-unavailable
INFO jobId=J-17 phase=finished processed=3
~~~

There is no DEBUG line because the root level is INFO. The active file `target/logs/app.log` also contains the three corresponding lines if run for the first time on an empty file. Because `append=true`, subsequent runs within the same period will append data; **do not** assume the file will always have only three lines.

**Rollover will not necessarily occur in this short demo.** `TimeBasedRollingPolicy` rolls over at the date boundary of the pattern, not simply because the program emits three lines. To observe a daily archive, you need to keep the application running into the next period and emit an event after the boundary, or create a test with a shortened condition such as a per-minute pattern in an isolated environment; when changing the pattern, review retention as well because the unit of `maxHistory` also changes.

Maven, the runtime environment, or Logback's status logger may print additional tool messages; the three lines above are the **application log output according to the configured pattern**, not a guarantee of the entire process's stdout in every environment.

### 5.5. Change the configuration and predict the outcome

- Change `<root level="INFO">` to `DEBUG`: both console and file gain the line `DEBUG jobId=J-17 step=prepare`.
- Remove `<appender-ref ref="ROLLING"/>`: console still receives logs, but the file appender is no longer invoked by root.
- Keep root at INFO and add a `ThresholdFilter` for WARN on `ROLLING`: console keeps all three lines; the file only receives the WARN line, provided the filter is configured correctly.
- Change `ROLLING`'s content pattern: the file has a different timestamp/logger name format than the console, while business logic remains unchanged.
- Changing `append=true` to `append=false` should only be done for testing when you understand the consequences; **do not do this casually in production**, as it can overwrite existing log content on startup.

## 6. Logback: combining time and size conditions

A standard `TimeBasedRollingPolicy` uses the date/hour to decide rollover. If a single day's file can become very large, Logback provides **`SizeAndTimeBasedRollingPolicy`** to roll over either when the time period ends **or** when the file in the current period reaches a size threshold.

Replace the `<rollingPolicy>` block in the `ROLLING` appender with:

~~~xml
<rollingPolicy
    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>target/logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>10MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>100MB</totalSizeCap>
</rollingPolicy>
~~~

In this pattern:

- `%d{yyyy-MM-dd}` denotes the daily period.
- `%i` numbers multiple archives within the same period if log volume is large enough.
- `maxFileSize=10MB` is the active file size trigger threshold.
- `maxHistory=7` limits the number of historical periods, **not exactly 7 files**, because there can be multiple `%i` indices in a single day.
- `totalSizeCap=100MB` limits the total archives within the policy's scope, **not everything stored on the volume**.

**Both `%d` and `%i` are required** in a `SizeAndTimeBasedRollingPolicy` pattern. Do not simply add `<maxFileSize>10MB</maxFileSize>` to `TimeBasedRollingPolicy` and expect it to become a size-based policy.

A single very large event or the fact that checks occur when a new event is written can cause the actual file size to briefly exceed the expected mark. Therefore, `maxFileSize` should be understood as a **rollover trigger threshold**, not a safety guarantee that every file is strictly under 10MB at all times. Set up separate volume space alerts and log payload size limits.

**Practical note:** `TimeBasedRollingPolicy` with `totalSizeCap` already addresses capping total archives by period. Logback documentation recommends not using `SizeAndTimeBasedRollingPolicy` unless you genuinely need a **per-file** size limit, because rolling over and renaming files has overhead. Choose the simplest policy that meets your requirements rather than enabling every mechanism by default.

### Archive compression

A file pattern ending in `.gz` enables Logback to compress archives. Compression reduces stored bytes but requires additional CPU and I/O, which can increase rollover duration. Compression **does not mean the active file is being written directly in gzip format**; typically the active file remains a plain text file, and the archive is compressed upon rollover.

Do not rely solely on compression to solve excessive log volume: controlling log levels, message length, retention, and event volume at the source is usually more important.

## 7. Log4j2: RollingFile, TriggeringPolicy, and RolloverStrategy

In **Apache Log4j 2**, rolling appender configuration is structured differently from Logback. Log4j2 typically uses:

- `<RollingFile>` to define the appender and file paths.
- `fileName` for the active file; `filePattern` for archives.
- `<Policies>` containing one or more *triggering policies*, such as `TimeBasedTriggeringPolicy`, `SizeBasedTriggeringPolicy`, or `OnStartupTriggeringPolicy`.
- `<DefaultRolloverStrategy>` or another strategy to handle archives, indexing, and cleanup actions.

Example `log4j2.xml` **for a project with compatible `log4j-api` and `log4j-core` dependencies**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="target/logs/app.log"
                     filePattern="target/logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz">
            <PatternLayout pattern="%d{HH:mm:ss.SSS} %-5level %msg%n"/>

            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="10MB"/>
            </Policies>

            <DefaultRolloverStrategy max="20"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="ROLLING"/>
        </Root>
    </Loggers>
</Configuration>
~~~

This is a standalone Log4j2 XML example, **not a `logback.xml` file**. Do not mix Logback's `<rollingPolicy>` tag into `log4j2.xml`.

Explanation:

1. When the daily period changes or the file size reaches the threshold, a triggering policy can request a rollover.
2. `%d` places the date component and `%i` allows multiple archives within a period; omitting `%i` when combining size and time triggers can lead to archive name collisions.
3. `DefaultRolloverStrategy max="20"` relates to the **archive file index window** under the active strategy; **it does not automatically mean "keep 20 days"**.
4. If you need to delete old archives by age, total size, or file name, configure a *Delete action* with explicit conditions suited to the strategy, rather than treating `max` as day-based retention.

Example **extension snippet** inside `DefaultRolloverStrategy` to delete `.gz` archives older than 7 days:

~~~xml
<DefaultRolloverStrategy max="20">
    <Delete basePath="target/logs/archive">
        <IfFileName glob="app.*.log.gz"/>
        <IfLastModified age="P7D"/>
    </Delete>
</DefaultRolloverStrategy>
~~~

This snippet applies only to files matching the conditions in the specified directory and is executed according to the strategy's rollover/cleanup mechanism. **Do not apply broad deletion rules to a shared directory containing other business files.** In real configurations, test matching conditions, archive name variations, delete permissions, timezones, and trigger cycles before relying on the outcome.

There is also a Log4j2 configuration mode that omits `fileName` and uses `DirectWriteRolloverStrategy` to write directly to archive names; its behavior and how the active file is identified differ from the fixed active file model shown above. Do not assume one strategy's behavior applies to every `RollingFile`.

## 8. JUL FileHandler: an equivalent rotation mechanism with a different API

The JDK includes `java.util.logging.FileHandler`. It supports size and file count limits via configuration, though it does not use Logback's `RollingFileAppender` model.

A standalone **JDK 17-only** example to illustrate the difference:

~~~java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public class JulRotationDemo {
    private static final Logger LOG =
            Logger.getLogger(JulRotationDemo.class.getName());

    public static void main(String[] args) throws IOException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        // 1 MiB per file, use up to 3 files in the rotation set.
        try (FileHandler handler =
                new FileHandler("jul-demo-%g.log", 1_048_576, 3, true)) {
            handler.setLevel(Level.INFO);
            handler.setFormatter(new SimpleFormatter());
            LOG.addHandler(handler);

            for (int i = 0; i < 5; i++) {
                LOG.info("record=" + i);
            }
            handler.flush();
            LOG.removeHandler(handler);
        }

        System.out.println("emitted=5");
    }
}
~~~

**Syntax note:** the snippet above illustrates using `FileHandler` within a scope; `java.util.logging.FileHandler` extends `Handler`, which has `close()`, but **does not implement `AutoCloseable` in all JDK versions**. To keep the example reliably compatible, prefer `try/finally` rather than relying on `try-with-resources`. An alternative standalone version that does not depend on `AutoCloseable` is:

~~~java
import java.io.IOException;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

public class JulRotationDemo {
    private static final Logger LOG =
            Logger.getLogger(JulRotationDemo.class.getName());

    public static void main(String[] args) throws IOException {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        FileHandler handler =
                new FileHandler("jul-demo-%g.log", 1_048_576, 3, true);
        try {
            handler.setLevel(Level.INFO);
            handler.setFormatter(new SimpleFormatter());
            LOG.addHandler(handler);

            for (int i = 0; i < 5; i++) {
                LOG.info("record=" + i);
            }
            handler.flush();
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        System.out.println("emitted=5");
    }
}
~~~

Save as `JulRotationDemo.java` and run:

~~~bash
javac -encoding UTF-8 JulRotationDemo.java
java JulRotationDemo
~~~

**Exact stdout** of this example:

~~~text
emitted=5
~~~

The INFO lines are written to the file using `SimpleFormatter` and are not shown on stdout because parent handlers were disabled. With only five small records, the 1 MiB threshold will not be reached, so **rotation will not necessarily occur in this run**. To inspect files by generation `%g`, use a file explorer or OS commands to view `jul-demo-0.log`, etc., after running in a writable directory.

In the constructor `new FileHandler(pattern, limit, count, append)`:

- `pattern` is the file name template, with `%g` as the generation index.
- `limit` is the byte size threshold to trigger rotation.
- `count` is the number of files in the rotation set.
- `append` enables appending when opening the file, subject to handler capabilities and rules.

JUL rotation has no direct `<maxHistory>` or `<fileNamePattern>` syntax equivalent to Logback. Do not paste Logback/Log4j2 configurations into a JUL setup.

## 9. Rolling appender and AsyncAppender: two different purposes

A rolling appender **manages files** and archive schedules. An async appender/async logger **manages when and on which thread writing occurs** by placing log events into a queue and forwarding them to a target appender.

They can be combined:

~~~text
Application thread -> AsyncAppender -> queue -> worker
                                              |
                                              v
                                     RollingFileAppender
                                              |
                                              v
                                  active file + archives
~~~

Combining them can reduce request I/O wait times in some workloads, but it does not reduce the cost of writing, rotating, or compressing to zero. When the queue is full, depending on the framework and policy, it may block, drop logs, or use a fallback path; if the process is killed before flushing, some events may never reach the file.

**Do not attach both a direct path and an async path to the same `RollingFileAppender` unless you intend duplicate writes.** For example, having root reference both `ROLLING` and `ASYNC`, while `ASYNC` also references `ROLLING`, can cause the same event to be written twice.

For logs that require reliable retention, you must evaluate end-to-end durability, shutdown handling, filesystem behavior, crash scenarios, and collector behavior. A `RollingFileAppender` inside a single process does not automatically constitute a tamper-proof audit store.

## 10. Estimating capacity and choosing a policy

Log data rate depends on event rate and encoded bytes per event:

~~~text
bytes/second = events/second × average bytes/event
bytes/day = bytes/second × 86,400
~~~

For example, a service generating **200 events/s** at an average of **500 bytes/event**:

~~~text
200 × 500 = 100,000 bytes/second
100,000 × 86,400 = 8,640,000,000 bytes/day
                  ≈ 8.64 GB/day (decimal units)
~~~

If the active file threshold is set around 100 MB, the service may require **multiple rollovers per day**. A time-only daily policy could produce a single file approaching 8.64 GB/day before compression in this idealized example. In that case, consider `SizeAndTimeBasedRollingPolicy`, reducing log volume, changing the collection pipeline, or allocating appropriate storage.

The numbers above **are not exact predictions of real-world disk usage**, because metadata, compression, message size variance, indexing, copies, library output, and other files also contribute. `maxFileSize` defines a trigger condition and does not replace actual volume capacity monitoring.

### Choosing retention by requirements

- Routine INFO logs may have shorter retention than critical error logs or reconciliation events, but the policy should be driven by system requirements.
- If retention spans weeks or months, consider archiving/compression or shipping logs to appropriate storage; do not rely on small container/pod disks.
- Distinguish between **local archives for debugging** and **backups or compliance-grade storage**.
- Monitor volume usage, active/archive file counts, rollover rate, compression/deletion errors, and log collector lag.

## 11. Operational scenarios and common risks

### 11.1. Multiple JVMs writing to the same file

Two processes sharing `logs/app.log` can contend for the file, miscalculate sizes, encounter rename conflicts, and cause missing or duplicate archives. **Do not assume a rolling appender is safe for multiple processes writing to the same file.**

Logback offers `prudent` mode for certain multi-JVM shared-file scenarios, but it has constraints: with `TimeBasedRollingPolicy`, compression cannot be used simultaneously, and `<file>` must be left empty in supported prudent configurations. Prudent mode can also reduce performance due to file synchronization. For multiple instances/containers, **having each instance write its own file or using console + collector** is usually simpler.

Log4j2 also notes that size-based rollover can miscalculate if multiple managers write to the same file. Design clear file ownership and test on the actual filesystem.

### 11.2. Rollover and external `logrotate` tools

If Logback/Log4j2 renames and compresses files while another tool simultaneously rotates or truncates the same file, you can lose data or keep writing to a stale file descriptor. Choose **one party to be primarily responsible** for rotation, unless an interactive mechanism is explicitly designed and tested.

If an agent tails files, verify how the agent handles **renames, truncations, file inodes, restarts, and archive compression**. Do not conclude that every log line reached the collector simply because a new archive appeared.

### 11.3. Full disk or missing write permissions

Failures in creating directories, active files, archives, compression, or deletion can prevent the appender from initializing or writing properly. Check backend status messages at startup, file/directory permissions, free space, quotas, filesystem mounts, inodes, and container permissions.

An application can continue running business logic even when the logging backend fails. Therefore, set up independent operational alerts on files/collectors and do not treat "no ERROR logs" as proof that no errors occurred.

### 11.4. Active file exceeding the archive cap

In Logback, `totalSizeCap` limits managed archives, not `app.log` itself. If traffic spikes and the application has not yet hit a rollover time or condition, the active file can still grow large. Monitor the **actual size of the entire directory**, configure a file size policy when per-file limits are required, and set up volume alerts.

### 11.5. Archive compression consumes CPU and can be slow

Compression saves disk space but requires CPU and file I/O. Compressing or uploading multiple large archives at once can create load spikes, especially on slow volumes. Monitor CPU, disk I/O, p95/p99 latency, and collector lag during rollover windows—not just logging overhead when files are not rotating.

### 11.6. Additivity and duplicate writes

When a child logger and root both reference a rolling appender with default additivity, an event can enter the appender twice. If unintentional, review `appender-ref` attachments or set `additivity="false"` on the appropriate logger (while ensuring the child logger still has the appenders it needs).

This is a **log routing** issue, not rollover creating extra messages on its own.

### 11.7. Security and sensitive data

Active files, archives, and backups can all contain passwords, API tokens, cookies, payment data, or personal information if logged unchecked. Compression **is not encryption**. Select safe fields at the source, restrict read permissions, enforce retention, encrypt at rest/in transit where required by policy, and sanitize inputs containing newlines/control characters to mitigate log forging.

When deleting archives, remember that this does not automatically delete copies already shipped to collectors or backups. Data protection policies must cover the entire pipeline.

## 12. Checklist for verifying a rolling appender in a real project

1. **Verify the actual backend:** is the code using JUL, SLF4J+Logback, or Log4j2? Is the intended `logback.xml`/`log4j2.xml` actually being loaded?
2. **Identify the active file:** check the resolved path, working directory, write permissions, and file owner.
3. **Check rollover conditions:** is the time pattern using the right unit? Does the size policy have an appropriate threshold? Is an event after the boundary required to trigger it?
4. **Check archive names:** verify `%d`, `%i`, compression suffix, and archive directory; test multiple rollovers to detect overwrites.
5. **Check retention:** are `maxHistory`/`totalSizeCap` or strategy/Delete actions scoped correctly? Is there any risk of deleting unrelated files?
6. **Measure volume and resources:** track bytes/s, free disk space, archive count, CPU/compression overhead, GC, p95/p99 latency, and collector lag.
7. **Test restarts:** is the active file appended or truncated? Are archives intact? Are resources flushed/closed on shutdown?
8. **Test under load:** generate enough volume to exceed the size threshold and inspect indexed archives, not just date-based ones.
9. **Test filesystem failures:** simulate full disk, permission denied, and failed archive deletion; observe status logging, alerts, and application behavior.
10. **Test multiple instances/collectors:** ensure no unintended shared-file writes occur and that the agent does not drop events during file renames/compression.

In test environments, you can lower `maxFileSize` to a reasonably small value and generate safe log traffic to trigger rollover quickly. **Do not use tricks that generate massive log volume in production**, as the test itself can fill the volume or overload the collector.

## 13. Comparison: Logback, Log4j2, and JUL

| Topic | Logback | Log4j2 | JUL |
| --- | --- | --- | --- |
| File rotation component | `RollingFileAppender` | `RollingFile` / related plugins | `FileHandler` |
| Time-based configuration | `TimeBasedRollingPolicy` | `TimeBasedTriggeringPolicy` | No direct time-based rolling policy equivalent in `FileHandler` |
| Size-based configuration | `SizeAndTimeBasedRollingPolicy` when combining date + size | `SizeBasedTriggeringPolicy` inside `Policies` | `limit` in bytes, `count` for file count |
| Archive naming | `fileNamePattern` with `%d`/`%i` | `filePattern` with `%d`/`%i` | `pattern` with `%g` |
| Retention | `maxHistory` and `totalSizeCap` | RolloverStrategy, index limits, and Delete action | Rotates within the `count` file set |
| Compression | Based on archive suffix, policy-dependent | Based on archive suffix, strategy-dependent | No built-in compression equivalent to the other two frameworks |
| Configuration | `logback.xml` | `log4j2.xml` | `logging.properties` or handler API |

Do not swap XML snippets verbatim between Logback and Log4j2. For JUL, file rotation uses handler configuration/constructors; do not call SLF4J methods or use Log4j2 plugins.

## 14. Common misconceptions and mistakes

| Misconception or mistake | Consequence | How to handle |
| --- | --- | --- |
| "Rolling means old logs are automatically deleted after exactly 24 hours" | Archives may persist longer or only be cleaned up on rollover | Configure retention and check cleanup timing |
| "`maxHistory=7` means there are always at most 7 files" | A single day can have multiple `%i` files | Understand time periods vs. archive policies |
| "`totalSizeCap` caps the active file too" | Volume still fills up if the active file grows too large | Monitor active + archives; use a size trigger if needed |
| Using only `FileAppender` in a long-running app | A single file grows without bound | Use `RollingFileAppender` or an external collector |
| Adding `maxFileSize` to the wrong policy | Does not roll over by size as expected | Use `SizeAndTimeBasedRollingPolicy` properly |
| Omitting `%i` when combining date and size | Archive name collisions within the same day | Use both `%d` and `%i` |
| Treating `DefaultRolloverStrategy max` as retention days | Fails to delete aged-out files as expected | Configure a Delete action/age if needed |
| Assuming archive compression equals encryption | Sensitive data remains readable | Protect data and access permissions separately |
| Two JVMs writing to the same active file | File/rollover conflicts | Use one file per instance or a shared collector |
| Using external `logrotate` without coordination | Potential log loss or duplication | Choose one rotation mechanism and test it |
| Forgetting `appender-ref` | Logger never sends events to the appender | Attach the appender name to logger/root |
| Routing both direct and async paths to one rolling appender | Same event written twice | Keep one intentional routing path |
| Expecting rollover in a demo with a few lines | Trigger is not reached, so no archive is created | Test actual trigger conditions |
| Checking only `app.log` without checking archives | Mistakenly thinking old logs were lost | Check directory, pattern, and policy |
| Not monitoring disk/quota | Logger stops writing while the app may keep running | Monitor backend status, disk, and collector |

## 15. Practice exercises

1. **Definitions:** explain the difference between active file, archive, rollover, and retention. Why should gzip compression never be treated as secret protection?
2. **Run Logback:** create the three files from the Maven example in section 5 on JDK 17. Predict the three stdout lines, the active file contents on the first run, and why no archive appears immediately.
3. **Daily vs. hourly retention:** change `fileNamePattern` to an hourly pattern, such as `%d{yyyy-MM-dd_HH}`. What does `maxHistory=7` mean now compared to a daily pattern?
4. **Size-based:** use `SizeAndTimeBasedRollingPolicy` with `%d` and `%i` and a small threshold in a test environment. Observe the first and second archive names in the same period, and explain why one period does not always correspond to one file.
5. **Log4j2:** starting from the `RollingFile` example, add `OnStartupTriggeringPolicy` to `<Policies>` if needed. Explain why `DefaultRolloverStrategy max="20"` does not mean "keep 20 days."
6. **JUL:** run `JulRotationDemo.java`, locate `jul-demo-0.log`, and explain the roles of `limit`, `count`, and `%g`. Lower `limit` to observe generation rotation.
7. **Capacity math:** a service generates 400 events/s at an average of 250 bytes/event. Calculate GB/day before compression and compare the risk of daily-only rotation versus adding a 100 MB size threshold.
8. **Troubleshooting:** the active file has logs, but no archives appear after a configuration change. List the order in which to check triggers, patterns, directory permissions, `appender-ref`, startup status, and events after the time boundary.
9. **Multi-process safety:** two JVMs write to the same file and both rotate it. Name two design solutions to avoid conflicts; why is prudent mode not a universal replacement for a collector?
10. **Operations:** propose minimum metrics/alerts for volume usage, archive count, compression/deletion errors, collector lag, and request latency during rollover windows.

## 16. Official references

- Logback Manual — Appenders, RollingFileAppender, and Rolling Policies: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 — Rolling File Appenders: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Java SE — `java.util.logging.FileHandler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html

**Key takeaway:** a rolling appender does more than rename files. It manages **the active file lifecycle, rollover conditions, archive naming, and retention**, while also requiring attention to compression, performance, security, and log collection. In Logback, pair `RollingFileAppender` with the right rolling policy; in Log4j2, pair `RollingFile` with triggering policies and a rollover strategy; in JUL, use `FileHandler` according to its own mechanism.

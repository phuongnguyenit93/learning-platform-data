# Rotation on Restart: Managing Log Files Across Multiple Java Runs

## 1. What is rotation on restart?

**Log rotation** (or *rollover*) is the process of turning the log file currently being written into an **archive file** and continuing to write to a new or different active file. The goal is to control file size, organize logs by time, and help enforce *retention* policies.

**Rotation on restart** is the question of what happens to those files when a Java application stops and is started again:

- Does the log file from the previous run still exist?
- Does the new JVM continue to **append** to the old file, or create a new file?
- Is there a separate archive for each restart?
- Are logs from a crashed process preserved?
- When is time-based or size-based rotation performed after a restart?
- If multiple instances overlap, who is allowed to rotate the shared file?

**The most important rule: a restart does not automatically mean a rotation.** The JVM has no global rule forcing Log4j2, Logback, or JUL to create a new archive on every startup. Behavior depends on the **backend, appender/handler, triggering policies, and file state**.

For example:

```text
Before restart:
logs/
└── orders.log                (first run)

After restart, if appending and no trigger has fired:
logs/
└── orders.log                (first run + second run)

After restart, if a startup rotation policy triggers:
logs/
├── orders.log                (records from the second run)
└── archive/
    └── orders-...log.gz      (logs from the first run)
```

Both outcomes above can be **correct by design**. You should not add a file rotation mechanism if the application needs a single continuous file across multiple runs, or conversely, allow the file to be overwritten when you need to preserve diagnostic logs from a previous crash.

## 2. Distinguishing append, truncate, rollover, retention, and restart

| Concept | Meaning | Does it create a readable archive? |
| --- | --- | --- |
| **Restart** | The old Java process stops, a new process starts | Not by default |
| **Append** | Opens an existing file and writes to the end | No |
| **Truncate / overwrite** | Truncates or replaces the contents of an existing file | Not guaranteed; old logs may be lost |
| **Rollover / rotate** | Moves the active file to an archive and uses a new active file | Yes, if the operation succeeds |
| **Retention / cleanup** | Keeps/deletes/compresses archives by age, count, or total size | Not a rotate action |

You can visualize it as follows:

```text
JVM stops
  │
  ▼
Does the active file still exist on the filesystem?
  │
  ├── No --> create file when the appender/handler starts writing
  │
  └── Yes
       │
       ├── Append mode and rotation condition not yet met
       │     └── Append to the old file
       │
       ├── Valid startup / size / time trigger
       │     └── Rollover --> archive + new active file
       │
       └── Opened in overwrite mode
             └── Old file may be truncated, not archived
```

**`append=true` does not mean rotate.** It only specifies how to use an existing file. **`append=false` is not a safe "rotate on startup"**: relying on that attribute alone can cause data from the previous session to disappear from the current file without being preserved in an archive.

A newly named file or a truncated file after a restart **does not prove** that a rollover succeeded. You must verify the archive contents and the retention policy.

## 3. Common restart scenarios

### 3.1. Restart within the same day, file is still small

An application writes logs to `logs/app.log`, stops after a few events, and restarts later the same day. If the backend only rotates at 10 MB and the file is only 20 KB, a restart is usually not enough to trigger the policy. With append enabled, the new session appends its records.

### 3.2. Restart overnight

An application stops before midnight and restarts the next morning. If using daily time-based rolling, **the first event** after the restart can trigger rotation of the file from the previous period. This is not because "restart always rotates"; the reason is that **the time period boundary has changed**.

### 3.3. Restart on deploy

A service is restarted to update its version. If each deployment requires its own file, you can choose a startup rotation policy or name the file using a **run/deployment ID** provided by the infrastructure. You need to control file names, archive files, and collection permissions.

### 3.4. JVM crashes and is restarted by a supervisor

The old file may still exist but not contain all of the final events if logs were still in a queue/buffer. Rollover on a new start **cannot recover** a `LogEvent` or `Throwable` that was never successfully flushed before the old process died.

### 3.5. Crash loop

If a service starts and crashes dozens of times, startup rotation can create dozens of small archives whenever each file meets the condition. You must limit the number of files and total size, and fix the root cause of the crash loop rather than just increasing retention.

### 3.6. Multi-instance rolling deployment

If instance A is still writing to a file while instance B starts up with the same file path, B's startup rotation can interfere with the file A is using. This case requires **per-instance files** or a stdout/collector pipeline; two independent JVMs should not compete for the same active file without a dedicated coordination mechanism.

## 4. What conditions trigger rotation?

Common mechanisms in Java backends:

| Policy | When can rollover happen? | Relationship to restart |
| --- | --- | --- |
| **Size-based** | File reaches/exceeds the size condition | Can happen after restart if the file is already large or as more is written |
| **Time-based** | A new time period arrives per pattern/schedule | After restart, can be evaluated on the next event |
| **Startup-based** | A new JVM session detects an old file meeting the condition | Specifically intended to rotate after startup |
| **Manual/external** | A script or admin task requests rotation | Can run before startup, but requires backend coordination |
| **Combined** | One of several policies is satisfied | Need to identify exactly which trigger caused the rollover |

Many triggering policies are evaluated when **a log event arrives at the appender**. Therefore, simply starting the process does not guarantee a new archive yet, especially if no record passing the filter has been logged.

This has two consequences:

- If you want to verify rotation after a restart, emit an `INFO`/`WARN` event and confirm the backend actually receives it.
- Do not create a startup log by printing directly with `System.out.println(...)` and expect RollingFile to receive it: that call does not go through the Log4j2/Logback file appender.

## 5. Log4j2: What is OnStartupTriggeringPolicy?

In **Apache Log4j2**, a `RollingFile` appender can be paired with `OnStartupTriggeringPolicy`. This policy determines when to roll over **an existing file that predates a JVM startup**.

Example policy configuration:

```xml
<Policies>
    <OnStartupTriggeringPolicy minSize="1"/>
    <SizeBasedTriggeringPolicy size="1 MB"/>
</Policies>
```

This is a Log4j2 XML snippet that must be placed inside a properly declared `RollingFile` appender.

**Mechanism to remember:**

1. The appender initializes, receiving the active file path and the archive file pattern.
2. `OnStartupTriggeringPolicy` checks the conditions that apply to the old file, including the **minimum size `minSize`** and timestamp information compared to when the new JVM started.
3. When the first qualifying event reaches the appender, the policy may request a rollover of the previous file.
4. The old file is moved to an archive according to the rollover strategy, and then the current event is written to the active file.

**It is not "rotate every time `main()` is called".** Calling `main` twice in the same JVM, having no old file, or having a file that is too small may not produce the same result as two actual process startups.

Similarly, `OnStartupTriggeringPolicy` is not responsible for automatically deleting old logs. **Retention** is the responsibility of a separately configured file retention/deletion strategy.

### Related attributes

- `fileName`: the file currently being written, e.g. `logs/restart-demo.log`.
- `filePattern`: the archive pattern, which may include date/time, index `%i`, and `.gz` compression extension.
- `append="true"`: prefers appending to the existing file when opened; not a trigger.
- `minSize="1"`: avoids trying to rotate an empty/too-small file on startup.
- `SizeBasedTriggeringPolicy`: an additional size policy that operates independently of restarts.
- `DefaultRolloverStrategy max="10"`: controls the index window/archive strategy; does not directly mean keeping exactly ten days.

## 6. Complete Java 17 + Maven + Log4j2 Example

We will create an application that can be run **twice in two separate JVMs**. The first run writes to the file, and the second run uses `OnStartupTriggeringPolicy` to attempt rotating the old file when conditions are met.

### 6.1. Directory structure

```text
restart-rotation-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── RestartRotationDemo.java
        └── resources/
            └── log4j2.xml
```

### 6.2. The pom.xml file

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>restart-rotation-demo</artifactId>
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

The versions in this example are **pinned to illustrate a specific dependency set**, not to claim they are the latest or safest versions for every system. In real use, keep `log4j-api` and `log4j-core` synchronized on a maintained patch release.

### 6.3. The src/main/resources/log4j2.xml file

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="AppFile"
                     fileName="logs/restart-demo.log"
                     filePattern="logs/archive/restart-demo-%d{yyyy-MM-dd-HH-mm-ss}-%i.log.gz"
                     append="true">
            <PatternLayout pattern="%level | %msg%n"/>
            <Policies>
                <OnStartupTriggeringPolicy minSize="1"/>
                <SizeBasedTriggeringPolicy size="1 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="10"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="AppFile"/>
        </Root>
    </Loggers>
</Configuration>
```

Part-by-part explanation:

- **AppFile:** a `RollingFile` appender writing to `logs/restart-demo.log`.
- **filePattern:** archive directory with timestamp, `%i` index to distinguish rollovers, and `.gz` to compress the archive.
- **append=true:** does not erase contents simply because the file is opened when a new session starts.
- **OnStartupTriggeringPolicy:** allows rotating the old file after startup when conditions are met.
- **SizeBasedTriggeringPolicy:** still rotates by size if the application runs for a long time.
- **DefaultRolloverStrategy:** manages archive naming/indexing; does not replace age-based retention.
- **Root INFO:** INFO and WARN records in this example are routed to AppFile.

There is no Console appender. Thus Log4j2 lines are sent to the **file**, while `System.out.println` in `main` produces independent stdout.

### 6.4. The src/main/java/demo/RestartRotationDemo.java file

```java
package demo;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

public final class RestartRotationDemo {
    private static final Logger LOG =
            LogManager.getLogger(RestartRotationDemo.class);

    public static void main(String[] args) {
        String runName = args.length > 0 ? args[0] : "unnamed";

        LOG.info("Started run {}", runName);
        LOG.warn("Diagnostic marker for {}", runName);

        System.out.println("run-finished:" + runName);
    }
}
```

This is a **standalone Java class** when placed in the Maven project above. No Spring Boot or SLF4J is needed to run the sample.

### 6.5. Running the first pass

From the `restart-rotation-demo` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RestartRotationDemo -Dexec.args=first
```

**Exact stdout from the application code itself:**

```text
run-finished:first
```

On a clean log directory, `logs/restart-demo.log` is expected to contain:

```text
INFO | Started run first
WARN | Diagnostic marker for first
```

This is **file content**, not stdout. Maven or plugins may print their own messages, but the example has no Log4j2 Console appender. When the first process finishes, the file already contains data before the second JVM starts.

### 6.6. Running the second pass in a new JVM

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RestartRotationDemo -Dexec.args=second
```

**Stdout from the program itself:**

```text
run-finished:second
```

If the file from the `first` run still exists, is not too small, and has a timestamp matching the startup policy condition, after the first event of the `second` run enters the appender:

1. Log4j2 moves the previous session's active file into `logs/archive/`.
2. The archive is named according to `filePattern` and is typically `.gz` compressed.
3. Log4j2 writes the new run's events into the active file `logs/restart-demo.log`.

When rollover succeeds, the **new active file** is expected to contain:

```text
INFO | Started run second
WARN | Diagnostic marker for second
```

The archive corresponding to the `first` run contains the two lines `Started run first` and `Diagnostic marker for first`.

The archive filename **is not hardcoded in the example** because it depends on the current time, filesystem, and previous runs. If the file is empty, the timestamp does not match, no event is logged, or a different config is loaded, you may not see an archive. Do not assume every restart guarantees a `.gz` file.

### 6.7. Inspecting the file and archive

Linux/macOS:

```bash
cat logs/restart-demo.log
ls -l logs/archive
```

PowerShell:

```powershell
Get-Content logs/restart-demo.log
Get-ChildItem logs/archive
```

A `.gz` archive file must be decompressed with an appropriate tool; `Get-Content` does not decompress automatically. When using `gzip` in a POSIX shell, select the **actual file** that appeared in the archive directory rather than an assumed name from a guide.

**Proper testing:** each Maven command above must be run in a separate process, not by calling `main` again in the same JVM. Log4j2's startup policy relies on JVM startup time, and relative file paths depend on the **working directory**.

## 7. Changing the config to see that restart does not rotate

In the Log4j2 example, replace only `<Policies>` with:

```xml
<Policies>
    <SizeBasedTriggeringPolicy size="1 MB"/>
</Policies>
```

Keep `append="true"`. With the very short records in the demo, after running `first` and `second`, the active file usually remains under 1 MB and may contain:

```text
INFO | Started run first
WARN | Diagnostic marker for first
INFO | Started run second
WARN | Diagnostic marker for second
```

There is no startup trigger, so there is **no reason** for a new archive to be created just because a second JVM started. Only when the size grows large enough to satisfy the policy will the file roll over.

However, this conclusion holds only if no other trigger, configuration, or external tool is rotating the file. A system that already uses `TimeBasedTriggeringPolicy` can still rotate when crossing a time boundary even without a startup trigger.

If you change `append="false"` to "keep only new logs", the old file may be truncated and **lose old contents**, without automatically being preserved in an archive. Therefore, **truncating is not a safe type of rotation**.

## 8. TimeBasedTriggeringPolicy and restarting after a period of time

Another Log4j2 configuration uses **`TimeBasedTriggeringPolicy`**:

```xml
<RollingFile name="DailyFile"
             fileName="logs/app.log"
             filePattern="logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
    <PatternLayout pattern="%d{ISO8601} %level %msg%n"/>
    <Policies>
        <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
        <SizeBasedTriggeringPolicy size="10 MB"/>
    </Policies>
</RollingFile>
```

This is an **illustrative configuration snippet** to place inside `<Appenders>` of a complete Log4j2 file. If the service stops at the end of the day and restarts on a new day, the first record can trigger rollover of the file from the previous period. The condition is **time**, not the occurrence of a restart.

Things to keep in mind:

- Restarting **within the same period** when the file is still small may not rotate.
- Restarting **into a new period** may cause the file to rotate when a log event arrives.
- Periods with no activity **do not necessarily** produce empty files for each day.
- Timezone, the `%d` pattern, system clock, and policy evaluation time affect the result.
- Do not assume an archive appears **immediately when the JVM starts** before any log event.

To diagnose why an archive exists, distinguish **startup triggers** from **size/time triggers** instead of calling everything "restart rotation".

## 9. Logback: RollingFileAppender on application restart

In the **SLF4J + Logback Classic** ecosystem, rolling mechanisms have their own names and syntax. Example `logback.xml`:

```xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/orders-service.log</file>
        <append>true</append>
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss} %-5level %logger - %msg%n</pattern>
        </encoder>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/orders.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>10MB</maxFileSize>
            <maxHistory>7</maxHistory>
            <totalSizeCap>100MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
```

Distinguish accurately:

- `<append>true</append>`: appends to the existing file when appropriate, **does not force rotation on every restart**.
- `SizeAndTimeBasedRollingPolicy`: rotates based on size and time period.
- `maxHistory`, `totalSizeCap`: belong to the archive retention policy.
- `cleanHistoryOnStart`: allows **history cleanup** on startup, **does not mean** forcing the active file to be archived on every start.

This example is only a Logback configuration; application code typically calls `org.slf4j.Logger` and requires a compatible Logback provider at runtime. Do not paste Log4j2's `OnStartupTriggeringPolicy` into `logback.xml` and expect it to work.

### If you strictly need one file per run in Logback

You can choose an environment-controlled mechanism, such as **assigning a different fileName per run/deploy** using a standardized run ID or timestamp:

```text
logs/orders-2026-11-09T2000Z-instance-a.log
logs/orders-2026-11-09T2100Z-instance-a.log
```

These two names only illustrate a **file naming convention**, not automatic behavior of the given Logback config. Turning runtime configuration into these paths requires explicit setup and cleanup/collector management. Another approach is performing an external rotate step **before the new appender opens the file**, while ensuring the old process is no longer writing to it.

## 10. JUL FileHandler: append on restart and size-based rotation

The JDK provides `java.util.logging.FileHandler`, requiring no external logging library. Common constructor:

```java
new FileHandler(pattern, limit, count, append)
```

Where:

- `pattern`: file name/path, supporting `%g` (generation) and `%u` (unique number).
- `limit`: target maximum size in bytes.
- `count`: number of generation files managed.
- `append`: whether to append to an existing file when opened.

`FileHandler` **has no `OnStartupTriggeringPolicy` plugin like Log4j2**. When `append=true` and the size limit has not been reached, a restart can continue writing to the old file. With `append=false`, opening the file may lose old contents or rotate depending on the implementation; **do not infer that each JVM start will preserve a separate per-run archive**.

### Standalone Java 17 program

Create `JulRestartDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public final class JulRestartDemo {
    public static void main(String[] args) throws IOException {
        Files.createDirectories(Path.of("logs"));

        String runName = args.length == 0 ? "unnamed" : args[0];
        Logger logger = Logger.getLogger("demo.JulRestartDemo");
        Level oldLevel = logger.getLevel();
        boolean oldParents = logger.getUseParentHandlers();

        FileHandler file = new FileHandler(
                "logs/jul-restart-%g.log",
                1_000_000, 2, true);
        file.setLevel(Level.INFO);
        file.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        });

        logger.setLevel(Level.INFO);
        logger.setUseParentHandlers(false);
        logger.addHandler(file);

        try {
            logger.info("Start run " + runName);
            logger.warning("End run " + runName);
        } finally {
            logger.removeHandler(file);
            file.close();
            logger.setLevel(oldLevel);
            logger.setUseParentHandlers(oldParents);
        }

        System.out.println("jul-run-finished:" + runName);
    }
}
```

From the directory containing the file:

```bash
javac JulRestartDemo.java
java JulRestartDemo first
java JulRestartDemo second
```

**Stdout from the two runs:**

```text
jul-run-finished:first
jul-run-finished:second
```

In a clean directory with no contention, the file is typically `logs/jul-restart-0.log`, containing:

```text
INFO | Start run first
WARNING | End run first
INFO | Start run second
WARNING | End run second
```

It **does not need to rotate** just because a new JVM started. The file is too small to reach the 1,000,000-byte threshold, and `append=true` allows continued writing.

The actual filename may change if there is a name conflict, lock, or existing older generations. `file.close()` closes the handler created by the program to release the handle/lock. Do not create a new `FileHandler` on every request, and do not arbitrarily detach shared handlers on a multi-threaded server.

## 11. Graceful shutdown vs. crash and unflushed data

During a **graceful shutdown**, the logging backend has a chance to:

- Flush queued or buffered data depending on the implementation.
- Close file handles and release locks.
- Complete managed rollover/compression tasks.
- Write shutdown events if the logger is still active.

During a **crash, sudden kill, or power loss**, those tasks may **not complete**. If an event carrying a `Throwable` was created in memory but not yet durably written by the backend, a newly started JVM **cannot recover that event simply by rotating the old file**.

Therefore:

- Do not assume an archive after a restart contains all final errors from the previous session.
- Do not delete the old active file at startup just because there is no shutdown message.
- With `AsyncAppender`/`AsyncLogger`, check queue size, backpressure, and shutdown behavior.
- If logs have audit value or require zero data loss, use an appropriate storage design rather than relying solely on file logging.
- When analyzing crashes, log start/stop events and a safe run ID/instance ID to identify session boundaries.

**Rotation processes data that already exists on the filesystem; it is not a transaction recovery mechanism.**

## 12. Multiple JVMs sharing a file: risks during rolling deployment

Imagine process A is still running while process B of the same service starts up:

```text
JVM A ─┐
       ├── logs/orders-service.log
JVM B ─┘
```

If both open the same active file and each evaluates rollover based on its own state, you risk lock contention, colliding archive renames, writing to an already-renamed old file, or losing logs. Being thread-safe **within one JVM** does not mean safe **across two JVMs**.

In particular, if B has `OnStartupTriggeringPolicy`, it may treat the file currently used by A as predating B's start and attempt to rotate it.

Prefer:

```text
Option 1: per-instance files
JVM A ── logs/orders-instance-a.log
JVM B ── logs/orders-instance-b.log

Option 2: log collection infrastructure
JVM A ── stdout ─┐
                 ├── Collector (service=orders, instance=A/B)
JVM B ── stdout ─┘
```

Per-instance filenames must be generated from **trusted** deployment values, never directly from user input. In Docker/Kubernetes, stdout/stderr is often simpler because the container filesystem may be ephemeral.

If you must use a shared filesystem and a dedicated multi-process appender, you must understand the exact locking/support documentation of your chosen backend. Do not assume every `RollingFileAppender` is safe for concurrent writes from multiple JVMs.

## 13. External logrotate tools and restarts

On some Linux systems, **logrotate** or admin scripts rotate files outside the logging backend. Two common strategies:

1. **Rename then create new file:** the Java process may still hold the file descriptor of the renamed old file and continue writing to it if the appender has not been told to reopen.
2. **copytruncate:** copies the active file to an archive and truncates the file in place; has a race window where lines emitted during copy/truncate can be missed or duplicated.

If Log4j2/Logback is already rolling **and** logrotate also operates on the same active file, the two mechanisms can race to rename, compress, or delete archives. This causes hard-to-reproduce bugs, especially around restarts.

**Choose a single owner responsible for rotation per active file**, or build a thorough, verified coordination mechanism. When using a pre-startup rotation script, ensure the old JVM has stopped and is no longer using the file, the archive step is recoverable on error, the path is writable, and the collector can still read historical logs.

Do not casually run `mv` and expect an open appender to automatically switch to a new file. Behavior on Unix and Windows can differ due to how file handles/locks are held.

## 14. Retention: what if restarts happen repeatedly?

Startup rotation can separate logs by session, but it can also create too many archives:

- Service restarts once or twice a day: usually manageable.
- Service crashes repeatedly: hundreds of starts can create many tiny archives.
- Each deploy generates a new run ID: requires rules to delete old logs and collect them before cleanup.

Set clear operational goals:

| Question | Decision needed |
| --- | --- |
| How long to keep logs? | Retention duration |
| Total archive limit? | Max size, file count/ratio |
| Compress or not? | Compression, CPU, and completion latency |
| Delete archives on startup? | Cleanup policy and safety |
| Has the collector finished reading? | Compatibility when archives are renamed/deleted |
| Is a crash loop detected? | Restart count metric and rising file count |

In Log4j2, `DefaultRolloverStrategy max="10"` does not automatically mean "keep only 10 days". In Logback, `maxHistory`, `totalSizeCap`, and `cleanHistoryOnStart` each have specific meanings. Verify cleanup rules on appender startup, on rollover, and when disk space runs low.

Log files may contain sensitive information, so retention must comply with the system's access and data-deletion policies, not just disk optimization.

## 15. How to test rotation on restart?

Test in a **separate demo directory**; do not delete or overwrite production logs.

### Valuable test cases

| Case | State before startup | Expectation to verify |
| --- | --- | --- |
| First run | No active file | File is created on event, usually no old archive |
| Restart with append=true | Small active file, no startup trigger | New records append to the old file |
| Startup trigger | Previous session's active file, sufficient size, matching mtime | After a new event, active/archived files separate sessions |
| Empty file | Active file has 0 bytes | Startup policy may not roll over |
| Restart into new period | Time-based policy and old-period file | Observe when rollover is evaluated |
| Restart after crash | File contains only partial logs | Do not assume unflushed events auto-recover |
| Multi-instance restart | Two JVMs with the same path | Observe conflicts, switch to per-instance if needed |
| Unwritable file | Restricted archive directory | Observe appender errors, do not mark write as successful |

### Step-by-step diagnostic procedure

1. Identify whether the runtime uses **Log4j2, Logback, or JUL**; do not guess from dependency names.
2. Confirm which `log4j2.xml`/`logback.xml`/`logging.properties` file is actually loaded.
3. Check `File` vs. `RollingFile`, `append`, `fileName`, `filePattern`, and policies.
4. Determine the process **working directory** and actual file paths.
5. Run the first session, emit logs with clear markers, and shut down the process gracefully.
6. Record the **size, mtime, and contents of the active file**.
7. Run the second session as a **new JVM**, emitting an event that meets the logger/appender level.
8. Inspect the active file, archive name, archive contents after decompression, and file count.
9. Determine whether rollover was triggered by startup, size, time, or an external tool; do not infer from filename alone.
10. Check permission errors, file locks, status logs, and collector behavior before concluding PASS.

**Do not call `System.exit(...)` between two runs in the same JVM to simulate a restart**; actually launch two separate JVM processes. This is especially important for `OnStartupTriggeringPolicy`.

## 16. Common issues and how to handle them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| After restart, file still has previous session's logs | append=true and rollover condition not yet met | If you want one archive per session, configure appropriate startup rotation |
| Restart loses old logs | append=false or script deletes/truncates | Use an explicit archiving mechanism before replacing the file |
| OnStartupTriggeringPolicy configured but no .gz | Empty/small file, timestamp, no event yet, wrong config, or missing permissions | Check minSize, mtime, active config, and appender status |
| Time-based rollover happens on the right day but not at start | Policy is evaluated on event or per backend mechanism | Emit a first record and observe the period boundary |
| Every deploy generates too many archives | Frequent restarts and startup policy | Reduce archive count, set retention/quota, and fix restart root cause |
| New file does not appear | Wrong path, missing permissions, filter blocking logs | Check working directory, AppenderRef, and permissions |
| Config edited but behavior unchanged | App loads a different backend/config file | Verify runtime dependencies/actual loaded config |
| Two JVMs writing to file lose lines | Shared file and uncoordinated rollover | Per-instance files or stdout/collector |
| logrotate renamed file but Java still writes to old one | Appender still holds the file handle | Design reopen or let the backend handle rollover |
| copytruncate drops lines near rotation time | Race between copy and truncate | Avoid ad-hoc mixing; choose a consistent strategy |
| Archive lacks final exception before crash | Event or Throwable was not written/flushed | Accept logging limits, use appropriate durability mechanisms |
| cleanHistoryOnStart does not create a new archive | It is cleanup, not a startup trigger | Use a separate rotation mechanism if needed |
| DEBUG not visible after restart | Logger/appender filter still blocks DEBUG | Check thresholds at both layers |
| .gz file not ready right after rollover | Compression/rollover in progress or failed | Check status and complete archive before reading |

## 17. Security and operations

- Do not test truncate/rotate by deleting real user or production log files.
- Grant create/write/rename/archive permissions to the proper service account; do not run with elevated privileges just to bypass permissions.
- Do not base archive paths on request IDs or untrusted user input, to avoid path traversal.
- Do not log passwords, cookies, tokens, API keys, or PII even if files are rotated.
- Check for sensitive data in stack traces and `Throwable` messages.
- Monitor filesystem usage, appender errors, archive count, restart count, and collector backlog.
- Choose per-instance files when running multiple JVMs; do not let a new process's startup trigger rotate an active process's file.
- If using rolling files alongside external rotation tools, choose a single owner or verified coordination.
- Do not treat file-count retention as a safe audit policy without defining durability, integrity, and retention duration.
- For containers, consider stdout/stderr and collectors to reduce reliance on filesystems that may be lost on restart/redeploy.

## 18. Self-check exercises

**Q1.** Does `append=true` force creating an archive after every JVM restart?  
**Answer:** No. It controls appending to the file; to rotate, you must have an appropriate trigger/policy.

**Q2.** Why is `append=false` not equivalent to safe rotation?  
**Answer:** The file may be overwritten/truncated without an archive preserving the old logs.

**Q3.** What does Log4j2 `OnStartupTriggeringPolicy` check?  
**Answer:** Conditions for rolling over an old file when a new JVM session has started, including minimum size and time/file metadata. Not every restart is guaranteed to create an archive.

**Q4.** Why must you run two separate `java` commands or two separate Maven runs when testing?  
**Answer:** Because startup policies depend on when a **new JVM** starts; calling `main` again in the old JVM is not equivalent.

**Q5.** What does `cleanHistoryOnStart` in Logback mean?  
**Answer:** Cleaning up archive history on startup according to the rolling policy, not archiving the active file on every start.

**Q6.** When can a time-based policy roll over after a restart?  
**Answer:** When a period boundary has passed and the policy is evaluated, usually on the next event; not necessarily the moment the JVM starts.

**Q7.** If a JVM is killed while `AsyncAppender` still has events in its queue, can the new JVM recover them via rotation?  
**Answer:** There is no guarantee. Rotation only processes files already written; it does not recreate unflushed events.

**Q8.** Why shouldn't two JVMs arbitrarily share one active RollingFile?  
**Answer:** There is a risk of lock contention, interleaved writes, colliding rollovers/renames, or lost logs.

**Q9.** Does `DefaultRolloverStrategy max="10"` mean keeping exactly 10 days?  
**Answer:** No. It is a rollover strategy/index parameter, not automatically equivalent to day-based retention.

**Q10.** If an archive appears after a restart, how do you tell whether it was caused by OnStartup or by size/time?  
**Answer:** Check the active configuration, file state, size, timestamp, and triggering event; test isolating each policy in a controlled environment.

**Remember:** **A restart is not automatically a rotation.** Distinguish **append – truncate – rollover – retention**, understand the policies of Log4j2/Logback/JUL, and test with **two real JVMs**. Preserving old data, managing archives/retention, and separating files per instance are essential for logs to remain useful after a restart.

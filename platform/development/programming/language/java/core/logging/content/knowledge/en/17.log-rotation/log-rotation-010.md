# Testing Log File Rotation in Java

## Learning Objectives

**Testing rotation** means verifying whether a logging system **moves the currently written file to an archive and continues writing to a new file at the right time, with the right name, the right count, and the right retention policy**. Testing is only valuable if it goes beyond seeing a few files created: it must clarify which file is active, whether records are unintentionally lost or duplicated, whether old data is kept or deleted according to policy, and whether the log collector is still reading from the right place.

This lesson belongs to the **Log rotation** group in **Java Core Logging**, focusing directly on **“Testing rotation”**. After this lesson, you will be able to:

- Define acceptance criteria for **size-based rotation** and **time-based rotation**.
- Distinguish **active file**, **archive**, **trigger**, **rolling policy**, **retention**, **compression**, and **cleanup**.
- Build a **pure-JDK Java 17** test using **java.util.logging.FileHandler** with deterministic data to verify file generations, file count limits, record ordering, and history eviction due to retention.
- Practice **Java 17 + Logback Classic** with **RollingFileAppender** and **SizeAndTimeBasedRollingPolicy** to verify the active file, archives, data integrity, and shutdown.
- Understand why **maxHistory does not mean the maximum number of files**, why archives may be cleaned up asynchronously, and why a file can slightly exceed the size threshold due to writing a complete record.
- Build a test matrix for restarts, concurrency, compression, permissions, disk full, async logging, containers, and collectors.
- Distinguish **logs lost according to retention policy** from **logs lost due to pipeline bugs**.

The examples use extremely small thresholds so rotation happens quickly. **Practice only in a test directory or temporary files; never apply such small thresholds in production.**

## 1. What Does Testing Rotation Actually Verify?

A file-based logging system typically has an **active file** receiving new records. When a trigger is reached, the backend turns that file into an archive or closes the current generation and opens the next one.

~~~mermaid
flowchart LR
    A["Application emits event"] --> B["Appender / Handler"]
    B --> C["Active log file"]
    C --> D{"Rollover condition met?"}
    D -->|No| C
    D -->|Yes| E["Archive / increment generation"]
    E --> F["Open next active file"]
    F --> B
~~~

Depending on the backend, the detailed lifecycle may include renaming, opening a new stream, compressing archives, and cleaning up history. Some operations run asynchronously. The diagram is a logical model, not the exact thread sequence of every implementation.

There are at least **six conditions** to verify:

1. **Trigger:** the activation condition is accurate (byte count, date/time, or both).
2. **Continuity:** new logs continue going into a valid file after rollover.
3. **Naming:** active file and archive names/paths follow the configured rules.
4. **Integrity:** retained records are not corrupted, duplicated, or missing outside what the policy allows.
5. **Retention:** old files are kept or deleted according to the configured number of generations, periods, or total size.
6. **Operations:** files have read/write permissions, are discovered by the collector, do not block the application, and do not leak resources after shutdown.

**Having multiple files is not enough to conclude that rotation PASSES.** The backend might simply create a new file on every startup; or an archive might exist while the latest records were never written after the switch. You need evidence tied to the trigger and the data.

## 2. Terminology to Distinguish

| Term | Meaning | How to Verify |
| --- | --- | --- |
| **Active file** | The file currently receiving new logs | Check the configured path and the latest record |
| **Archive / rolled file** | A file from a past period or generation | Check name, timestamp, content, and permissions |
| **Triggering policy** | The condition deciding when rollover occurs | Emit records past the threshold or cross a time boundary |
| **Rolling policy** | Decides how to archive/name and create the new file | Match active/archive names and lifecycle |
| **Size limit** | Size threshold in bytes or configured units | Measure actual file bytes, not just character count |
| **Time period** | Day/hour/month period based on pattern and timezone | Observe before and after the period boundary |
| **Generation/index** | File version identifier number | Check `%g` in JUL or `%i` in Logback |
| **Retention** | Limit on how much history to keep | Generate enough periods/records and verify files are deleted per policy |
| **Compression** | Compressing archives into `.gz`/`.zip`... | Verify decompression succeeds and data is intact |
| **Collector** | Component reading/shipping logs to a central backend | Confirm it follows the new file and does not skip archives |

**Rotation is not retention.** Rotation switches from one file to another; retention decides how long old data is kept. Do not call intentional deletion of old records by count/age “broken rotation” if the policy explicitly defines that limit.

**Counting files is not the same as counting records.** An exception record can print multiple stack trace lines, and a line can contain multi-byte UTF-8 characters. For reliable QA, attach a sequence ID to each **event**; when scanning files, clearly distinguish one-line-per-event from multiline formats.

## 3. Acceptance Criteria

Before running tests, write down **what will count as PASS** and **the scope that the test cannot prove**.

| Test | Stimulus | Example PASS Condition |
| --- | --- | --- |
| Size trigger | Write enough records to exceed threshold | Archive exists, new file continues receiving records |
| No premature rollover | Write below threshold | No unexpected new archive appears |
| Naming | Roll over multiple times | Generation/index names and paths are correct |
| Data continuity | Write continuous sequence IDs | Records within retention scope are uncorrupted and unique |
| Count-based retention | Exceed JUL generation count | Does not exceed count and oldest records are evicted by design |
| Time-based retention | Generate data across multiple periods | Only configured periods remain after cleanup |
| Total archive size | Generate archives exceeding quota | Cleanup gradually brings total size within backend contract |
| Restart | Stop/restart the process | Does not unexpectedly overwrite archives and resumes with correct name |
| Invalid directory | Use a path without permissions in test env | Reports error clearly, does not silently drop logs |
| Async shutdown | Write a burst then graceful stop | Queue drains per timeout and policy, no logs emitted after stop |
| Collector | Follow file before/after rollover | No broken read stream or misread rename/truncate |
| Compression | Roll over to `.gz`/`.zip` | Compressed file completes and can be decompressed/queried |

**Do not use “file size must always be less than or equal to maxFileSize to the exact byte” as the sole assertion.** Backends usually write a **complete record** and then evaluate rollover. When the last record reaches or crosses the threshold, the file can be larger than the configured limit. What matters is that rotation proceeds and the file does not grow unbounded due to a missed trigger.

For time-based rotation, **reaching exactly 00:00 does not necessarily switch the file immediately if no new event arrives**. Many rolling implementations check the time on the next append. QA needs to emit an event after the period boundary and allow for design-expected delay/cleanup.

## 4. Techniques for Generating Verifiable Test Data

Do not write random messages or just print “hello”. Give every record:

- **a unique sequence ID**, such as `seq=01`, `seq=02`..., sufficient to detect missing/duplicate records.
- **a deterministic payload size**, to easily trigger size thresholds.
- **a stable event name** and a one-line-per-event formatter in the test.
- **an explicit charset** (UTF-8).
- **an isolated test directory**, never reusing production logs.
- **a mechanism to close the handler/appender** before reading all files, avoiding partial snapshots.

Example of two sample records:

~~~text
seq=01 payload=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
seq=02 payload=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
~~~

In the example above, the payload has 44 ASCII `X` characters. If the format is `seq=NN payload=` + 44 `X` + `\n`, each record is **60 UTF-8 bytes** (15-byte prefix, 44-byte payload, 1-byte newline). Using ASCII characters avoids discrepancies between character count and byte count. If you use emojis or accented Vietnamese characters, UTF-8 typically requires more bytes; you cannot treat 60 characters as 60 bytes.

If the backend compresses archives, **event counting must be performed after decompression**. Do not compare the `.gz` file size against the size limit meant for the uncompressed active file.

## 5. Pure-JDK Java 17: Testing JUL FileHandler Rotation

JUL provides **java.util.logging.FileHandler**, supporting file size limits and the number of retained generations. Example constructor:

~~~java
new FileHandler(pattern, 120, 3, false);
~~~

Meaning:
- **pattern:** storage location and filename, which can include **%g** for generation.
- **120:** approximate byte limit for each file in the rotating set.
- **3:** number of output files rotated in the count mechanism.
- **false:** do not append to old data; suitable for a fresh test directory in this lesson.

According to the Java SE 17 documentation, FileHandler **closes/rotates the file when the size limit is reached** and numbers generations **0, 1, 2...**. By default it uses `XMLFormatter` if not changed, so this exercise sets a single-line `Formatter` for deterministic results.

### Complete RotationCheckDemo.java Program

Create **RotationCheckDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.stream.Stream;

public class RotationCheckDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("rotation-check-");
        Logger logger = Logger.getLogger(RotationCheckDemo.class.getName());
        logger.setUseParentHandlers(false);
        logger.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(
                dir.resolve("service-%g.log").toString(), 120, 3, false);
        handler.setLevel(Level.INFO);
        handler.setEncoding("UTF-8");
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return formatMessage(record) + "\n";
            }
        });
        logger.addHandler(handler);

        try {
            for (int seq = 1; seq <= 13; seq++) {
                logger.info(String.format(Locale.ROOT,
                        "seq=%02d payload=%s", seq, "X".repeat(44)));
            }
        } finally {
            logger.removeHandler(handler);
            handler.close();
        }

        List<Path> logFiles;
        try (Stream<Path> paths = Files.list(dir)) {
            logFiles = paths
                    .filter(p -> p.getFileName().toString().endsWith(".log"))
                    .sorted()
                    .toList();
        }

        List<String> records = new ArrayList<>();
        for (Path path : logFiles) {
            records.addAll(Files.readAllLines(
                    path, StandardCharsets.UTF_8));
        }

        Set<String> ids = new HashSet<>();
        for (String record : records) {
            ids.add(record.substring(0, 6));
        }

        System.out.println("generated=13");
        System.out.println("logFiles=" + logFiles.size());
        System.out.println("rotationObserved=" + (logFiles.size() > 1));
        System.out.println("countLimitRespected=" + (logFiles.size() <= 3));
        System.out.println("retainedRecords=" + records.size());
        System.out.println("oldestEvicted=" + records.stream()
                .noneMatch(s -> s.startsWith("seq=01 ")));
        System.out.println("latestRetained=" + records.stream()
                .anyMatch(s -> s.startsWith("seq=13 ")));
        System.out.println("noDuplicateIds="
                + (records.size() == ids.size()));

        for (Path path : logFiles) {
            System.out.println(path.getFileName()
                    + " bytes=" + Files.size(path)
                    + " lines=" + Files.readAllLines(
                            path, StandardCharsets.UTF_8).size());
        }

        for (Path path : logFiles) {
            Files.delete(path);
        }
        Files.delete(dir);
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac RotationCheckDemo.java
java RotationCheckDemo
~~~

**Verified stdout** on the JDK for this exact exercise:

~~~text
generated=13
logFiles=3
rotationObserved=true
countLimitRespected=true
retainedRecords=5
oldestEvicted=true
latestRetained=true
noDuplicateIds=true
service-0.log bytes=60 lines=1
service-1.log bytes=120 lines=2
service-2.log bytes=120 lines=2
~~~

Here each record is 60 bytes and **13 records = 780 bytes emitted**. However, the system is configured for only **3 files of approximately 120 bytes** each, so it cannot hold all 13 records. The result **retainedRecords=5** and **oldestEvicted=true** is an intentional consequence of generation-based retention. The current file at generation 0 holds the latest record; generations 1 and 2 hold the most recent history.

**Do not interpret the absence of `seq=01` as a bug**, because the number of history files is bounded. This test proves **rotation occurred**, **the configured generation count is respected**, **the latest record is present**, and **there are no duplicate sequence IDs in the retained data**.

### Clarifying Common Points of Confusion

1. **Files.createTempDirectory** creates a separate directory per run, avoiding mixing with old files and reducing conflicts.
2. **service-%g.log** includes the generation in the filename. `FileHandler` also supports **%u** when filename conflicts need to be resolved.
3. **FileHandler(...,120,3,false)** is a configuration solely for the demo. Do not use a 120-byte limit on real systems.
4. **Formatter** intentionally omits timestamps or class names from the message, keeping record length deterministic.
5. **"\n"** is hardcoded so the byte count does not depend on Windows/Linux newlines.
6. **Locale.ROOT** ensures `String.format` formats numbers reproducibly.
7. **handler.close()** runs before reading files, releasing streams and locks.
8. **Files.list** retrieves the created `.log` files; do not treat the raw list of temp directory entries as log records.
9. **substring(0,6)** only works because the demo knows the `seq=NN` format. Production parsers must handle variable messages/stack traces rather than slicing by a fixed length.
10. **Set ids** checks for duplicates among retained records. This alone does not prove there was no log loss outside retention if we do not know which IDs were allowed to be evicted.

### Stronger Check: Retention Forms a Contiguous Tail

In the demo, we know the 13 IDs in order `01..13`. If the configuration keeps only a **most recent tail** of events, a stronger assertion is:

~~~text
Retained IDs: 09, 10, 11, 12, 13
Missing IDs:  01..08 (exceeded designed capacity)
Latest ID:    13
~~~

This is the interpretation of the verified run. In a real system with multiple producers, retries, filters, and async logging, you must compute the **set of events accepted by the backend**, rather than insisting every sequence number from business code must be present. Events can be dropped by level/filter or evicted by retention policy.

### How to Test Without Losing Records to Retention

Create a workload small enough relative to total capacity, or increase count/limit in the **test environment** so all 13 records are retained. You can then compare **expected/actual** ID sets without intentional history deletion. Only after verifying this completeness should you run a separate over-capacity scenario to test retention.

## 6. Different Rotation Types Must Be Tested Differently

### Size-Based Rotation

Typically uses thresholds such as **1MB**, **100MB**, or another configured value. Procedure:

1. Confirm no new archive appears while the workload remains below the threshold.
2. Continuously write records of controlled length/charset until rollover.
3. Emit at least one more record **after the trigger**.
4. Inspect the active file and archives to confirm data continuity.
5. Do not assume every file's size is always less than or equal to the exact byte threshold due to whole-record writes and trigger evaluation timing.

A common mistake is writing just up to the threshold, seeing no immediate archive, and drawing the wrong conclusion. Check whether the backend evaluates **before writing**, **after writing**, or on the next append.

### Time-Based Rotation

For example, files roll over by **UTC day** or a **configured timezone**. Tests should check:
- Which date/time determines the archive name?
- If the process has no events after the time boundary, does rollover run immediately or wait for a new event?
- Does a record right before the boundary belong to the old or new period?
- Do timezone changes or DST cause unexpected filenames?
- After a restart within the same period, does the file resume with the right name without unexpected overwriting?
- Does cleanup of old periods run immediately or on a rollover schedule/signal?

**Do not change the production system clock** to test time-based rotation. In a controlled test harness, you can use a mock clock/time injection mechanism if the backend supports it; otherwise, run integration tests across a real time boundary or use staging with an appropriate policy.

### Combined Size-and-Time Rotation

In Logback's **SizeAndTimeBasedRollingPolicy**, the archive pattern requires both **%d** (time period) and **%i** (file index within the period). Each day can have multiple archives when the size threshold is exceeded; on a new day, the time period changes. Therefore **maxHistory is the number of periods to keep**, not an absolute limit on the number of archive files.

## 7. Logback: Configuration for Testing Size and Time

An example **logback.xml** for Logback Classic:

~~~xml
<configuration>
  <appender name="ROLLING"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>target/rolling/service.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
      <fileNamePattern>
        target/rolling/archive/service.%d{yyyy-MM-dd}.%i.log
      </fileNamePattern>
      <maxFileSize>1KB</maxFileSize>
      <maxHistory>2</maxHistory>
      <totalSizeCap>10MB</totalSizeCap>
    </rollingPolicy>

    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="ROLLING"/>
  </root>
</configuration>
~~~

**XML whitespace note:** if you wrap **fileNamePattern** across multiple lines as shown above, the XML includes newline whitespace. To prevent the parser/backend from misinterpreting the filename, **keep the content of fileNamePattern on a single line** in actual use:

~~~xml
<fileNamePattern>target/rolling/archive/service.%d{yyyy-MM-dd}.%i.log</fileNamePattern>
~~~

Components:
- **file** is the active file currently being written to.
- **fileNamePattern** is the archive filename; **%d** represents the date period and **%i** the index within that day.
- **maxFileSize=1KB** triggers rollover quickly for testing. Production values must be sized for load and requirements.
- **maxHistory=2** limits the number of **time periods** kept by the cleanup policy, **not keeping only two .log files**.
- **totalSizeCap=10MB** caps total archive size during cleanup when `maxHistory` is set; it is not the size limit of the active file.
- **encoder** formats log content, distinct from the rolling `fileNamePattern`.
- **root INFO** and `appender-ref` ensure `INFO` events reach `ROLLING`.

The configuration in the Maven example below uses a **single-line fileNamePattern** to avoid path confusion. When using compression, the pattern can end with **.gz** or **.zip**, but file verification must account for asynchronous compression.

**Note from the official Logback manual:** if your only goal is to cap the **total archive size**, `TimeBasedRollingPolicy` with `totalSizeCap` is usually sufficient; do not use `SizeAndTimeBasedRollingPolicy` just because it has more features. Choose the combined policy only when you genuinely need per-file size limits within each period.

## 8. Java 17 + Maven: Runnable Logback Verification Test

To avoid depending on a specific calendar date, this test uses **30 events with sequence IDs**, a sufficiently long payload, and a **RollingFileAppender**. After calling **LoggerContext.stop()**, the program scans the active file and archives, then compares record counts and uniqueness. The goal is to verify **size-based rotation within the same period**; time-boundary and multi-day retention testing are covered separately.

### Project Structure

~~~text
logback-rotation-check/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/
        │       └── example/
        │           └── logging/
        │               └── LogbackRotationCheck.java
        └── resources/
            └── logback.xml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>logback-rotation-check</artifactId>
  <version>1.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
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
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.3.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Versions are pinned for a reproducible lesson, **which does not mean they are the latest versions**. Maven needs to download dependencies or have them cached. In real projects, follow your BOM/`dependencyManagement` and update/security policies.

### File src/main/resources/logback.xml

~~~xml
<configuration>
  <appender name="ROLLING"
            class="ch.qos.logback.core.rolling.RollingFileAppender">
    <file>target/rolling/service.log</file>

    <rollingPolicy
        class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
      <fileNamePattern>target/rolling/archive/service.%d{yyyy-MM-dd}.%i.log</fileNamePattern>
      <maxFileSize>1KB</maxFileSize>
      <maxHistory>2</maxHistory>
      <totalSizeCap>10MB</totalSizeCap>
    </rollingPolicy>

    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="ROLLING"/>
  </root>
</configuration>
~~~

This example **does not use compression** so the program can read all `.log` files directly. If you change `fileNamePattern` to `.gz`, the test reader must decompress them; do not scan and read compressed files as plain text.

### File src/main/java/com/example/logging/LogbackRotationCheck.java

~~~java
package com.example.logging;

import ch.qos.logback.classic.LoggerContext;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class LogbackRotationCheck {
    public static void main(String[] args) throws Exception {
        Logger logger = LoggerFactory.getLogger(LogbackRotationCheck.class);
        LoggerContext context =
                (LoggerContext) LoggerFactory.getILoggerFactory();

        try {
            for (int i = 1; i <= 30; i++) {
                logger.info("seq={} payload={}",
                        String.format("%02d", i), "X".repeat(180));
            }
        } finally {
            context.stop();
        }

        Path root = Path.of("target", "rolling");
        List<Path> files;
        try (Stream<Path> stream = Files.walk(root)) {
            files = stream.filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".log"))
                    .sorted()
                    .toList();
        }

        List<String> lines = new ArrayList<>();
        for (Path file : files) {
            lines.addAll(Files.readAllLines(
                    file, StandardCharsets.UTF_8));
        }

        Set<String> unique = new HashSet<>();
        for (String line : lines) {
            unique.add(line.substring(0, 6));
        }

        System.out.println("generated=30");
        System.out.println("activeFileExists="
                + Files.isRegularFile(root.resolve("service.log")));
        System.out.println("archiveObserved="
                + files.stream().anyMatch(p ->
                        p.getParent().getFileName()
                                .toString().equals("archive")));
        System.out.println("allRecordsPresent=" + (lines.size() == 30));
        System.out.println("noDuplicateIds="
                + (unique.size() == lines.size()));
        System.out.println("latestRetained=" + lines.stream()
                .anyMatch(s -> s.startsWith("seq=30 ")));
        System.out.println("contextStarted=" + context.isStarted());
    }
}
~~~

### Run Command

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:exec "-Dexec.executable=java" "-Dexec.args=-classpath %classpath com.example.logging.LogbackRotationCheck"
~~~

The command uses the Maven Exec Plugin to launch a **child JVM** with the project classpath, avoiding interference from Maven's own logging backend. The program was tested with Logback Classic 1.5.18.

**Program stdout when tested:**

~~~text
generated=30
activeFileExists=true
archiveObserved=true
allRecordsPresent=true
noDuplicateIds=true
latestRetained=true
contextStarted=false
~~~

Any Maven-specific output lines (if present) are not part of the sample output. In the test run, the system created **multiple archive files alongside one active file**; the observed `fileCount` was **5**. Do not hardcode the archive file count as a general contract because it depends on message size, encoding, newline, library version, and rollover timing.

### Interpreting the Results

- **activeFileExists=true:** the active file exists.
- **archiveObserved=true:** rollover occurred at least once.
- **allRecordsPresent=true:** in this specific test, all 30 events were found when scanning both active and archive files. The test uses **maxHistory=2 periods** but runs within a single period, so it is not meant to verify two-day history deletion.
- **noDuplicateIds=true:** no duplicate IDs in the lines read.
- **latestRetained=true:** the final event continued to be written after rollovers.
- **contextStarted=false:** the Logback context stopped before the program scanned the files.

**Caveat on proof scope:** the program uses a single thread to emit events and a one-line-per-event format. In real systems, filters, `AsyncAppender`, I/O errors, multiple threads/processes, or multiline exceptions require a stronger test design. In particular, `lines.size()==30` is only valid when retention is not expected to delete records or when the test is designed so all records must remain.

## 9. Testing Logback Time-Based Rotation and Retention

**TimeBasedRollingPolicy** typically uses a date pattern such as:

~~~xml
<fileNamePattern>logs/app.%d{yyyy-MM-dd}.log</fileNamePattern>
~~~

With a size-and-time policy, add the index:

~~~xml
<fileNamePattern>logs/app.%d{yyyy-MM-dd}.%i.log</fileNamePattern>
~~~

Conditions QA must clarify:

1. **Is the rollover period daily, hourly, or monthly?** The `%d` pattern determines the cadence based on the date pattern and timezone.
2. **Does the time boundary require a subsequent event?** If midnight passes and nobody logs, the file might not rotate yet. Test by emitting a record after crossing into the new period.
3. **Which date does the archive name belong to?** The archive holds data from the completed period, while the active file continues receiving records.
4. **How many periods is maxHistory?** With a daily pattern, `maxHistory=2` essentially retains historical periods per policy, not just 2 archive files if each day has multiple index files.
5. **When does cleanup run?** Logback usually cleans up archives during rollover; this can execute asynchronously. Do not mark FAIL just because an old file lingers for a few milliseconds right after the trigger.
6. **Does totalSizeCap take effect alongside maxHistory?** Logback requires setting `maxHistory` when using `totalSizeCap`; the history limit is applied before the total archive size cap.
7. **On a short-lived startup without rollover**, does cleanup run? Setting **cleanHistoryOnStart=true** can trigger history cleanup when the appender starts if needed.
8. **How do DST/timezone and clock changes** affect period naming? You need a consistent time policy between log events and archive names.

**You cannot test two-day retention with a single run on the same day.** The Logback test in Section 8 verifies size rotation within one period; accepting time-based retention requires generating data across multiple valid periods in a test harness or an appropriate staging environment.

### Testing Cleanup Properly

- Seed a representative set of archives spanning multiple periods in a **test directory**.
- Ensure the right rolling policy is loaded.
- Trigger rollover or a supported cleanup mechanism.
- Wait for asynchronous cleanup tasks to reach a valid completion point before asserting.
- Compare **remaining periods**, **total archive size**, and verify the **active file is not accidentally deleted**.
- Never let QA delete production files just to demonstrate retention.

According to Logback documentation, **maxHistory** controls archive history, **totalSizeCap** adds a total archive size cap, and **cleanHistoryOnStart** can request cleanup at startup. When files are compressed or renamed asynchronously, observation timing must account for transient states.

## 10. Verifying Active File, Archive Naming, and Compression

Actual file paths are an important part of QA. For the Logback example:

~~~text
target/rolling/
├── service.log
└── archive/
    ├── service.2026-11-09.0.log
    ├── service.2026-11-09.1.log
    └── service.2026-11-09.2.log
~~~

This is an **example of filename structure**, not the exact list for every run or every date. **service.log** is the file currently receiving records; archive names depend on the date and index. Checking only the archives does not confirm the active file continues to be written.

If using **.gz/.zip**, verify:
- Compressed filenames match the policy, without generating misnamed period files.
- Archives can be decompressed and the event count matches.
- Are temporary compressed files or compression tasks still running? Do not read mid-compression.
- Does the collector watch compressed archives or only the active file? Avoid duplicate or missed reads during rename.
- Does retention count compressed archives toward total size per the backend policy?
- Do not treat the compressed size as the byte size that triggers rollover of the active file.

A **collector watching a static path** can break when the active file is renamed or truncated. QA must trace the sequence **before rotation → immediately after rotation → after collector ingestion** rather than only checking files on disk.

## 11. Reconciling Records: Completeness, Uniqueness, and Ordering

An effective verification strategy is to attach a unique **sequence ID** or event ID to each test record.

Let:
- **E** be the set of expected accepted events.
- **A** be the set of events read from all active and archive files within the retention scope.
- **D** be the set of events intentionally deleted according to a clearly defined retention policy.

When there is no retention/drop/filter, expect **A = E**; IDs are unique and uncorrupted. With retention, the appropriate expectation is **A = E \ D** under the designed cleanup conditions and timing. This is a logical model, not a formula for every complex pipeline.

Check at least:
- **Missing IDs:** which events should still be present but are missing?
- **Duplicate IDs:** did any event appear twice due to additivity, retries, or the collector?
- **Ordering:** is ordering consistent for a single-threaded producer? With multiple threads, do not expect a simple global total order.
- **Boundary IDs:** do the last event in the old file and the first event in the new file connect cleanly?
- **Encoding:** was a UTF-8 record split mid-character?
- **Malformed records:** was a record split across two files, or was a stack trace parsed as multiple records?
- **Retained tail:** is the latest record still present after rollover?
- **End-to-end delivery:** if a collector is used, did events reach the central backend, not just local files?

**Record count does not equal text line count in every format.** If the formatter writes multiline stack traces, you need a parser that respects event boundaries or structured logs to count accurately.

A **zero-duplicates** result does not by itself prove **nothing is missing**. Always check counts, ID sets, and retention conditions together.

## 12. Manual Verification via Terminal

### Linux/macOS

For a test directory with uncompressed text archives:

~~~bash
find target/rolling -type f -name '*.log' -print
find target/rolling -type f -name '*.log' -exec wc -c {} \;
find target/rolling -type f -name '*.log' -exec wc -l {} \;
grep -R 'seq=30 ' target/rolling
~~~

These commands list filenames, byte counts, line counts, and search for the last event. They only work when the format is one record per line and archives are uncompressed `.log` files. For `.gz`, you must decompress with the appropriate tool before reading contents.

**Do not simply run `tail -f` on a file and assume it will keep following logs after the file is renamed.** Inode/path following behavior depends on options and environment. Verify the exact file-tailing tool and collector configuration your application actually uses.

### Windows PowerShell

~~~powershell
Get-ChildItem -Path .\target\rolling -Recurse -File |
  Where-Object { $_.Extension -eq '.log' } |
  Select-Object FullName, Length, LastWriteTime

Get-ChildItem -Path .\target\rolling -Recurse -Filter '*.log' -File |
  ForEach-Object { Select-String -Path $_.FullName -Pattern 'seq=30 ' }
~~~

These two examples show which files exist, their byte sizes, and where the last event is located. If the application is running, renaming/rotation can change files while the listing runs; for a deterministic snapshot, **run test → graceful stop → inspect**. Do not treat a snapshot taken mid-write as the final result.

## 13. Concurrency and AsyncAppender

### Multiple Threads in One JVM

When multiple threads emit logs concurrently:
- Global sequence IDs must be assigned in a thread-safe manner, e.g., `AtomicLong`, if used to check for duplicates/missing records.
- The logger/appender may process events in a different order than they were created; do not enforce strict timestamp ordering.
- Do not read a file undergoing rotation without explicit synchronization or a clean snapshot policy.
- Check both the active file and archives; grepping only the active file can mislead readers into thinking old events were lost.

### Multiple JVMs/Processes Writing to the Same Path

Do not assume two processes concurrently writing/rotating the same file is safe on every backend or filesystem. File locks, prudent mode, renaming, and retention can have limitations. With multiple instances, **separate paths per instance** or use `stdout`/`stderr` + a collector per a supported architecture. If a backend offers a multi-process mode, test that mode directly rather than extrapolating from single-JVM tests.

### AsyncAppender

If a logger sends events to an **AsyncAppender**, events may still be in the queue when you read the file. Therefore:
1. Stop producers first.
2. Wait for business tasks to finish.
3. **Stop the logging context** so the worker drains the remaining queue per policy/timeout.
4. Read files or query the backend after an appropriate synchronization point.

With Logback, settings like **queueSize, discardingThreshold, neverBlock, maxFlushTime** affect whether events are dropped, blocked, or flushed on shutdown. You cannot take results from a synchronous appender and claim the async pipeline preserves every event.

**Clean shutdown does not guarantee zero log loss during crashes.** `SIGKILL`, crashes, power loss, I/O errors, and interrupted collectors can lose records outside the scope of rotation. Separate rotation tests from durability/delivery-guarantee tests.

## 14. Restarts, Renaming, and Permissions

### Restarts

After rotating a few times:
1. Stop the context and process cleanly.
2. Capture the file list, sizes, and last event.
3. Restart with the same configuration.
4. Emit additional records with new IDs.
5. Confirm the active file resumes writing, archive names are not unintentionally overwritten, and retention still holds.

**Do not use `append=false` in production when old history must be preserved** without understanding its effect; in JUL, `false` in the demo is only for clean test data. In Logback, active names/paths and archive indices must be verified under the real policy.

### Permission or Disk Errors

To test errors safely, create a **test directory without write permissions**, a read-only volume, or simulate I/O failures in a dedicated environment. Do not unmount production volumes or fill up real disks to test.

An initialization error in `FileAppender` or `FileHandler` can prevent the system from emitting logs as expected. QA must inspect the logging backend's **status/error manager** and decide whether the application should fail-fast, warn, or fall back per requirements. Do not automatically treat “the app is still running” as a rotation test PASS.

### Archive Paths

The active file might live at **logs/app.log** while archives go to **logs/archive/app.2026-11-09.log**. If the collector only reads an outdated path, post-rollover logs can be missing from the central backend even though they were written properly to disk.

**Do not modify `fileNamePattern` or the active file while the appender is running** without using an official reconfiguration mechanism. Races between renames and readers can make testing non-deterministic.

## 15. Monitoring Rotation in Production Operations

Even after functional tests PASS, monitor signals that detect broken rotation later on:

| Signal | Anomaly | Suggested Action |
| --- | --- | --- |
| Active file size | Grows continuously past designed limit | Check trigger/policy or stalled rotation |
| Archive file count | No archives despite exceeding threshold | Verify active config/path and new events |
| Total log directory size | Grows unbounded | Check retention, `totalSizeCap`, cleanup |
| Age of oldest archive | Exceeds expected retention period | Check `maxHistory`, `cleanHistoryOnStart`, and rollovers |
| Appender status/errors | Permission, rename, compression, I/O fail | Check permissions, disk, and sink health |
| Missing new sequences/events | Output file may be stalled | Check logger level, appender, and collector |
| Collector ingestion lag | Events exist locally but not in central backend | Check reader, rename/truncate, network, and indexing |
| Async queue | Backlog/drops spike during bursts/shutdown | Check `queueSize`, `discardingThreshold`, `maxFlushTime` |
| File descriptors/locks | Leaks after restart/redeploy | Check lifecycle, `stop`/`close` |

**Do not monitor using a single number without context.** For example, a high archive count can be valid on a high-traffic day with many `%i` files; remember `maxHistory` counts periods, not files. Conversely, seeing no archives might mean the application had insufficient traffic to trigger rollover, not necessarily a bug.

In containers/Kubernetes, consider writing to **stdout/stderr** so the platform/collector handles rotation instead of the application, unless file logging is required. When the platform manages log files, **test rotation at the owning layer**; `RollingFileAppender` settings do not control rotation performed by the container runtime.

## 16. Common Issues and How to Analyze Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| No archives | Threshold not reached or no event after boundary | Generate enough data, emit event after time boundary |
| Active file slightly larger than `maxFileSize` | Backend writes whole event before rolling over | Check next cycle/file; do not assert strict byte cap against design |
| Archives unexpectedly overwritten | Wrong append/rotation config, path reused on restart | Test restarts and inspect generation/index names |
| Old records disappear | Count/age/cap retention | Compare against policy before concluding log loss |
| Latest records missing | Appender error, not flushed/stopped, collector lag | Stop cleanly and read both active + archives |
| Duplicate records | Multiple appenders, additivity, bridges, or collector re-reading | Check event IDs and the entire pipeline |
| One stack trace counted multiple times | Multiline logs | Parse by event, not just `wc -l` |
| `MaxHistory=2` but more than two files exist | Two periods with multiple size-index files | Understand `maxHistory` is **periods**, not file count |
| Archives remain past retention period | Cleanup runs on rollover/start or asynchronously | Test cleanup triggers and allow time to complete |
| `.gz` file does not appear immediately | Compression runs asynchronously | Wait for valid completion before checking |
| Appender fails to start | Invalid XML, missing path permissions, class version mismatch | Check Logback status and `logback.xml` |
| Error due to missing `%i` | `SizeAndTimeBasedRollingPolicy` requires `%d` and `%i` | Fix `fileNamePattern` |
| JUL missing expected filename | `%g`/`%u` or file lock altered name | Inspect pattern and actual output files |
| Rotation PASSES locally but FAILS in container | Different volume, working directory, or UID/GID | Check filesystem/container and mounts |
| Dashboard empty after rollover | Collector did not follow rename/truncate | Check tailing config and ingest lag |
| Rotation slows down the app | Rename/compression/flush I/O overhead | Measure latency, tune policy and storage |

## 17. Pre-PASS QA Checklist

Mark PASS only when the conditions applicable to the policy under test are confirmed:

- [ ] Identified the **actual backend** and effective configuration file.
- [ ] Know the exact **active file** and **archive `fileNamePattern`**.
- [ ] Emitted data with verifiable **sequence IDs** or event IDs.
- [ ] Tested **below** and **above** the size threshold and verified the trigger.
- [ ] Tested that the **first event after rollover** continues to be written.
- [ ] Tested time boundaries safely without altering production clocks.
- [ ] Did not treat **maxHistory** as a file count when using time-based rolling.
- [ ] Verified retention/`totalSizeCap` by **period**, after cleanup completed.
- [ ] Scanned **both active and archive files**, decompressing if needed.
- [ ] Reconciled expected/actual ID sets within retention scope; checked for duplicates/missing IDs.
- [ ] Tested startup/restart and shutdown, avoiding unread async queues.
- [ ] Tested permission/disk errors in a **test environment**, without harming production.
- [ ] Verified paths and collector behavior after rename/truncate, especially in containers.
- [ ] Configured storage limits and disk/retention monitoring.
- [ ] Recorded **policy, backend version, workload, date/time, timezone, and actual results** so others can reproduce them.

A checklist is a self-assessment tool; a small lab exercise does not prove full production correctness of rotation.

## 18. Self-Check Questions

**Q1.** You see `service-0.log`, `service-1.log`, and `service-2.log`; is rotation guaranteed to be working?

**Answer:** Not yet. You must verify the trigger, data after rollover, filenames, retention, and the retained record set. Multiple files can also result from multiple startups or separate processes.

**Q2.** Does JUL `FileHandler` `count=3` mean all events ever written are kept?

**Answer:** No. It rotates across the configured number of files. Once total capacity is exceeded, older generations are replaced and old records disappear intentionally.

**Q3.** Why did the JUL exercise emit 13 events but keep only 5 records?

**Answer:** Each record is 60 bytes; a 120-byte limit and `count=3` means a finite number of generations, so old events are replaced across multiple rotations. The latest record remains present.

**Q4.** With `maxHistory=2` on a daily `SizeAndTimeBasedRollingPolicy`, is the maximum number of archive files two?

**Answer:** False. `maxHistory` limits the number of **day periods**; within each day there can be multiple `%i` indexed archives if size thresholds are exceeded.

**Q5.** If it is 00:00 and no new archive exists yet, is time-based rotation definitely broken?

**Answer:** No. Many backends roll over when the next event is emitted after the period changes; understand the actual trigger and emit an event after the boundary.

**Q6.** Why can a file slightly exceed `maxFileSize`?

**Answer:** The backend may write a complete event before checking the trigger. Verify that the next file is created properly and size does not grow unbounded.

**Q7.** If there are `.gz` compressed files, can you use `Files.readAllLines` directly and count records?

**Answer:** No. You must decompress and parse according to the generated format. Compressed files may also be in the middle of asynchronous creation.

**Q8.** Is it reliable to run `AsyncAppender` and inspect the file immediately after the `logger.info` loop finishes?

**Answer:** Not yet. Events may still be in the queue. You must stop producers, drain/stop per policy, and inspect at an appropriate synchronization point.

**Q9.** Does proper rotation on disk prove the collector has ingested every record?

**Answer:** No. The collector may hit rename/truncate issues or lag. A separate end-to-end test is required.

**Q10.** When testing retention, can you delete the production log directory to see if the backend recreates it?

**Answer:** No. Use a test directory/staging volume, synthetic data, and controlled operations; never destroy operational evidence.

## 19. Technical References

- [Oracle Java SE 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): limit, count, append, `%g`/`%u` naming, and rotation mechanism.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): listing, reading, and checking file sizes.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): `RollingFileAppender`, `TimeBasedRollingPolicy`, `SizeAndTimeBasedRollingPolicy`, `maxHistory`, `totalSizeCap`, and cleanup.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): loading `logback.xml`, lifecycle, and configuration diagnostics.
- [Logback Manual — AsyncAppender](https://logback.qos.ch/manual/appenders-async-sift.html): queue, discarding policy, backpressure, and shutdown.

## Key Takeaways

**Testing rotation is verifying safe handoff between files alongside the history retention policy.** Generate records with predictable IDs and sizes, activate triggers in a controlled manner, scan both active and archive files, reconcile ID sets, and confirm the latest event is preserved. Always distinguish data evicted **by retention** from data lost due to bugs. For time-based rotation, understand periods, timezones, and rollover timing; for `AsyncAppender` and collectors, establish synchronization points and separate end-to-end tests. **Rotation PASS does not automatically mean zero-loss or durable delivery.**

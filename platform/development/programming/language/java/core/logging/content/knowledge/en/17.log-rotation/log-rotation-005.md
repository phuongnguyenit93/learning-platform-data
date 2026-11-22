# Log File Compression in Java Logging: GZIP, ZIP, Rolling Policies, and Operations

## 1. What Is Log File Compression?

**Log file compression** is the encoding of log file data into a form that consumes less storage space, typically using *lossless compression* algorithms. In Java systems, this operation most commonly occurs when an actively written file undergoes **rollover** into an **archive**, and that archive is then compressed into `.gz`, `.zip`, or another format supported by the framework.

Example flow:

~~~text
Logger -> Rolling appender -> logs/app.log     (active file being written, plain text)
                                  |
                          Rollover when conditions are met
                                  |
                                  v
                         app.2026-11-09.log
                                  |
                              Compression
                                  |
                                  v
                    archive/app.2026-11-09.log.gz
                                  |
                       Retention / backup / collector
~~~

The file names, timing, and processing steps above are an illustrative model. Each backend may perform renaming, compression, and file cleanup in its own way.

**Key takeaway:** log compression and log rotation are **two distinct concepts**.

- **Rollover / rotation:** ending the write cycle for one file, moving the old file to an archive or another generation, and opening/selecting the next file to continue writing.
- **Compression:** reducing the number of bytes used to store an archive's contents, usually triggered by an archive name ending in `.gz` or `.zip`.
- **Retention / cleanup:** specifying which archives are kept and which are deleted when they exceed an age, period count, or total size limit.
- **Collection:** shipping logs from files, stdout, or archives to a centralized collection system.

A system can rotate files **without compressing** them; it can compress archives and keep them **indefinitely** if retention is not configured; and it can have retention yet still need a separate backup or collection destination.

In Logback and Log4j2, the standard configuration keeps the **active file in plain text** for continuous writing by the appender, while only rolled-over files carry a compression suffix. Do not assume that putting `.gz` in the archive pattern means every byte in `app.log` is being streamed through gzip at the moment the logger calls `info(...)`.

## 2. Why Do Logs Compress Well?

Many text logs repeat structured parts: timestamps, logger names, levels, operations, field names, JSON punctuation, stack traces, and message templates. Lossless algorithms can represent repeating patterns with fewer bytes.

Example:

~~~text
2026-11-09T10:00:00Z INFO service=orders operation=checkout state=started id=O-1
2026-11-09T10:00:01Z INFO service=orders operation=checkout state=started id=O-2
2026-11-09T10:00:02Z INFO service=orders operation=checkout state=started id=O-3
~~~

When storing many similar lines, strings like `service=orders`, `operation=checkout`, and `state=started` repeat, which generally gives the compression algorithm plenty of redundancy to exploit.

However, **there is no fixed compression ratio** for all files. The ratio depends on content, size, entropy, encoding, and algorithm:

- Text logs with many similar lines usually compress better than random strings.
- Logs containing encrypted data, ciphertext, already-compressed formats, random UUIDs, or base64 of incompressible data may shrink very little.
- Extremely small archives may save no space at all, or even grow slightly due to the compressed format's header/trailer overhead.
- Repeating stack traces often share common patterns, but reducing duplicate logging and selecting useful events remains more important than compression alone.

**GZIP/ZIP is not security encryption.** Anyone with read access to a compressed file can usually decompress it and recover the full contents, including tokens, personal data, or sensitive stack traces. Compression does not replace redaction, encryption, access control, or retention.

## 3. GZIP vs. ZIP: How to Choose?

| Criterion | GZIP (`.gz`) | ZIP (`.zip`) |
| --- | --- | --- |
| Basic structure | Compressed data stream, typically used for a single log file | Container format that can hold one or more entries |
| Common usage in rolling | Archives such as `app.2026-11-09.log.gz` | Archives such as `app.2026-11-09.log.zip` |
| Common algorithm | DEFLATE inside GZIP | ZIP supports multiple methods; DEFLATE is commonly used |
| Reading in Java JDK | `GZIPInputStream` | `ZipInputStream`, `ZipFile` |
| Writing in Java JDK | `GZIPOutputStream` | `ZipOutputStream` |
| Direct searchability | Usually requires decompression or gzip-aware tools | Tools must read entries inside the ZIP |
| When suitable | Single-file log archives, pipelines supporting `.gz` | Systems using ZIP containers or tools expecting ZIP |

**Do not manually rename a file extension to "compress" it.** Simply renaming `app.log` to `app.log.gz` does not produce valid GZIP data. A framework compresses only if its **rolling policy/strategy actually implements compression** and recognizes the suffix.

In Logback, `TimeBasedRollingPolicy` automatically compresses archives when `fileNamePattern` ends with `.gz` or `.zip`. Versions supporting `.xz` may require an external XZ dependency; do not assume that dependency is present. In Log4j2, the rolling file strategy recognizes `.gz`, `.zip`, and certain other extensions depending on version and dependencies; GZIP and ZIP are the two most common and easiest choices to deploy.

**Choose based on the entire ecosystem:** does the log shipper read gzip archives? Which files does retention manage? Does the incident investigation workflow require decompressing before searching? A format that is well supported from write time through retrieval matters more than one format achieving slightly better compression.

## 4. Lifecycle of a Compressed Log File

A typical lifecycle:

1. **Open active file:** the appender writes text/JSON events to `logs/app.log`; it must have write permissions and sufficient filesystem space.
2. **Evaluate triggers:** by date/time, size, startup, or other policy-supported conditions.
3. **Rollover:** the backend moves the active file to an archive name or a generation, then prepares a file to receive subsequent events.
4. **Compression:** the archive data is compressed into `.gz`/`.zip` according to the strategy.
5. **Cleanup:** the retention policy deletes managed archives when their conditions are met.
6. **Collection/backup:** external pipelines may ingest active or archive files according to the agent's own rules.

The exact execution order, background operations, and completion timing vary across frameworks and versions. Do not assume that `logger.info(...)` returning means the archive has finished compressing or been backed up.

### Active Files and Archives Are Distinct

~~~text
logs/app.log                                  <- currently being written by the appender
logs/archive/app.2026-11-08.log.gz            <- previous period, compressed
logs/archive/app.2026-11-09.0.log.gz          <- previous period with size index
logs/archive/app.2026-11-09.1.log.gz
~~~

The names above illustrate that an archive directory can contain multiple files for the same day when using size-and-time rotation. With a purely daily configuration, there is usually no `%i` index.

**Never compress a file that the JVM is still writing to** using an uncoordinated external process. If reading/compressing and writing happen concurrently, the archive may miss lines, contain half-written data, be compressed before flushing, or be mis-tracked by a log shipper. Let the rolling appender own the file handoff timing; if an external tool is used, proper coordination and testing are required.

## 5. Logback: Enabling Compression via fileNamePattern

In Logback, `RollingFileAppender` writes the active file, while `TimeBasedRollingPolicy` determines the archive name and rollover period. With **SLF4J + Logback**, Java code still calls the standard SLF4J logger; the compression configuration lives in `logback.xml`.

Complete configuration example with daily archiving and GZIP compression:

~~~xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/app.log</file>
        <append>true</append>

        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.gz</fileNamePattern>
            <maxHistory>7</maxHistory>
            <totalSizeCap>512MB</totalSizeCap>
        </rollingPolicy>

        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
~~~

Place this in `src/main/resources/logback.xml` so it is on the classpath of an application using Logback. This configuration requires compatible SLF4J API and Logback backend dependencies; **the plain JDK does not include `RollingFileAppender`**.

Explanation of each element:

- `<file>logs/app.log</file>`: the active file name, usually remaining in uncompressed text/JSON.
- `<fileNamePattern>...%d{yyyy-MM-dd}.log.gz</fileNamePattern>`: archives daily and compresses with gzip; `.gz` is the compression signal supported by Logback.
- `<maxHistory>7</maxHistory>`: retains recent **daily periods** according to the policy, not necessarily exactly seven files in every configuration.
- `<totalSizeCap>512MB</totalSizeCap>`: caps total archive size within the policy's scope; typically requires `maxHistory` to be set and does not account for files outside that scope (in particular, it does not automatically cap the entire active file or volume).
- `<encoder>`: determines the format of the **log content** before compression, not the archive name.
- `<appender-ref ref="ROLLING"/>`: connects the root logger to the appender; defining an appender without referencing it may result in nothing being written.

**Time-based rollover usually requires a new log event after the period boundary.** An application that stops logging for many hours might not produce an archive immediately at 00:00 on the clock. Cleanup policies may also execute at rollover time or startup depending on options, so there is no guarantee an archive disappears the exact second it reaches the age limit.

### 5.1. Switching to ZIP

For a policy that supports ZIP, change the archive pattern:

~~~xml
<fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.log.zip</fileNamePattern>
~~~

When Logback recognizes the `.zip` suffix and the policy supports it, it creates a ZIP-compressed archive. Do not assume ZIP and GZIP backends have identical CPU cost or internal structure. Measure on real data if the choice affects operations.

### 5.2. Compression with Size-and-Time Rollover

One file per day can grow too large; use `SizeAndTimeBasedRollingPolicy`:

~~~xml
<!-- Replace only the rollingPolicy inside the ROLLING appender. -->
<rollingPolicy
    class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
    <maxFileSize>20MB</maxFileSize>
    <maxHistory>7</maxHistory>
    <totalSizeCap>512MB</totalSizeCap>
</rollingPolicy>
~~~

In this configuration:

- `%d{yyyy-MM-dd}` distinguishes the daily period.
- `%i` distinguishes **multiple archives within the same period** if a single day produces too much data.
- `maxFileSize=20MB` is a **rollover trigger threshold on the active file**, not a guarantee that every file on disk is under 20MB at all times.
- `maxHistory=7` is counted in time periods, which does not mean at most seven files: there can be multiple indices per day.
- `totalSizeCap=512MB` primarily manages the total size of archives controlled by the policy, not the active file or files not matching the pattern.

Do not simply insert `<maxFileSize>` into a standard daily `TimeBasedRollingPolicy` and expect it to combine size-based rotation. When using `SizeAndTimeBasedRollingPolicy`, the pattern must include both `%d` and `%i` appropriately.

**Performance note:** each rollover may involve renaming, creating directories, compressing, and processing archives. If an application logs heavily and the file size threshold is too small, compressing many tiny files wastes resources and puts pressure on the log collector. Choose thresholds suited to actual throughput and storage capacity.

## 6. Apache Log4j 2: RollingFile, Policies, and Strategy

Log4j2 organizes rolling files using `RollingFile`, `Policies`, and `RolloverStrategy`; its configuration syntax differs from Logback. The archive name in `filePattern` can end with `.gz` to instruct the framework to compress rolled-over files.

Example `src/main/resources/log4j2.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="logs/app.log"
                     filePattern="logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz">
            <PatternLayout pattern="%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n"/>

            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="20MB"/>
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

This configuration requires compatible Log4j2 API/Core dependencies; on its own, it does not turn JUL or Logback into Log4j2.

Meaning of each part:

1. `fileName="logs/app.log"` specifies the active file.
2. `filePattern="...%d{yyyy-MM-dd}.%i.log.gz"` specifies archives with date, index, and gzip compression.
3. `TimeBasedTriggeringPolicy` evaluates time-period boundaries derived from the pattern.
4. `SizeBasedTriggeringPolicy` checks the active file size to trigger rollover when the threshold is reached.
5. `DefaultRolloverStrategy max="20"` manages the **index window** of archives for the strategy; **it does not mean keeping archives for exactly 20 days**. If you need to clean up old files by age, add a `Delete` action with appropriate conditions.

In Log4j2, archive compression is triggered by a supported suffix in `filePattern`. Besides gzip, ZIP and other formats are available depending on version and dependencies. Options such as `compressionLevel` exist on the rollover strategy; use them when you need to measure compression quality versus CPU cost, rather than assuming stronger compression is always better.

### 6.1. Cleaning Up Archives by Age in Log4j2

Example **replacement snippet** for `DefaultRolloverStrategy max="20"` in the configuration above:

~~~xml
<DefaultRolloverStrategy max="20">
    <Delete basePath="logs/archive">
        <IfFileName glob="app.*.log.gz"/>
        <IfLastModified age="P7D"/>
    </Delete>
</DefaultRolloverStrategy>
~~~

This action evaluates **archive files whose names match and whose age exceeds the specified duration**, running as part of the framework's rollover/action mechanism. Always verify the actual pattern and path before enabling deletion; never delete an entire shared directory that contains files outside the log scope.

- `P7D` is a duration in the format accepted by the plugin, here representing seven days.
- `IfFileName` restricts which file names are considered.
- `IfLastModified` checks the file's last-modified timestamp, which is not necessarily the business event time.
- The cleanup action is not a real-time scanner guaranteed to delete a file the exact instant it turns seven days old.

Log4j2 also has **DirectWriteRolloverStrategy** when `fileName` is omitted: the active file is written directly according to `filePattern`. Do not blindly apply assumptions about a fixed `logs/app.log` to that mode; read the actual strategy configuration.

### 6.2. Do Not Infer Everything from the ".gz" Extension

A `.gz` extension in `filePattern` enables compression if the policy/strategy supports it and starts up successfully. It does **not** by itself determine:

- Which INFO/DEBUG events are written (that is controlled by logger levels and filters).
- How fast events are shipped to a collector.
- Whether files are flushed and closed before the JVM is killed.
- Whether archives are deleted after seven days.
- Whether files are encrypted or sensitive data is masked.

For production issues, always inspect appender startup status and actual rollover behavior rather than looking only at the XML.

## 7. JUL FileHandler: Rotation Without Automatic Gzip

`java.util.logging.FileHandler` in the JDK supports **rotation by size and generation count** via its constructor, for example:

~~~java
// Snippet inside a method that handles IOException, not a standalone program.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler(
                "logs/application-%g.log",
                1_048_576, 5, true);
~~~

The parameters correspond to `pattern`, `limit`, `count`, and `append`. `%g` is the generation number; `%u` can be used to generate a unique number in case of file lock/conflict.

**JUL's `FileHandler` does not have built-in automatic GZIP compression equivalent to Logback or Log4j2's `RollingFileAppender`.** If an application uses only JUL and needs compression, you can:

- Choose a backend with appropriate rolling and compression through an approved logging architecture.
- Delegate log rotation and compression to an external tool that coordinates on closed files.
- Build a custom archiving workflow that compresses **files that are no longer being written to**, with data verification and retention.

Do not rename JUL's file pattern to `.gz` expecting the contents to be compressed. `FileHandler` still writes using its formatter and will not turn into a GZIP stream just because of the file name.

In multi-JVM setups, `FileHandler` can pick a unique name via its locking mechanism, but that is **not** a mechanism for multiple processes to safely write, rotate, and compress a shared file. Each process should own its own files or use a collector.

## 8. Standalone Java 17 Example: GZIP Archive Compression and Verification

To understand "log file compression" accurately without external libraries, this example simulates a single rollover **when no logger or handler still holds the file open**:

1. Create an active file containing two UTF-8 log lines.
2. Move the active file to an uncompressed archive file.
3. Compress the archive into a temporary file using `GZIPOutputStream`.
4. Decompress the temporary file using `GZIPInputStream` and compare **byte-for-byte** with the original content.
5. Only after verification succeeds, rename the temporary file to `.gz`, delete the plain archive, and create a new active file.
6. Print a short report with predictable output.

This is a **file-mechanics demo**, not a production logging appender. It does not implement synchronization with a live writer, atomic rename guarantees across all filesystems, retry on compression failure, or retention. Those responsibilities belong to a battle-tested backend.

Create **GzipLogRotationDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public final class GzipLogRotationDemo {
    private GzipLogRotationDemo() {
    }

    private static void gzip(Path source, Path destination) throws IOException {
        try (InputStream input = Files.newInputStream(source);
             GZIPOutputStream output = new GZIPOutputStream(
                     Files.newOutputStream(destination,
                             StandardOpenOption.CREATE,
                             StandardOpenOption.TRUNCATE_EXISTING))) {
            input.transferTo(output);
        }
    }

    public static void main(String[] args) throws IOException {
        Path directory = Path.of("target", "gzip-demo");
        Files.createDirectories(directory);

        Path active = directory.resolve("app.log");
        Path plainArchive = directory.resolve("app.1.log");
        Path temp = directory.resolve("app.1.log.gz.tmp");
        Path compressed = directory.resolve("app.1.log.gz");

        String initial = "INFO phase=start message=khởi-động\n"
                + "WARN phase=retry attempt=1\n";

        Files.writeString(active, initial, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING);

        // Simulate rollover when the file is no longer held open by the writer.
        Files.move(active, plainArchive, StandardCopyOption.REPLACE_EXISTING);

        // Compress to a temporary file; do not delete the plain archive yet.
        gzip(plainArchive, temp);

        byte[] restored;
        try (GZIPInputStream input =
                     new GZIPInputStream(Files.newInputStream(temp))) {
            restored = input.readAllBytes();
        }

        boolean identical = Arrays.equals(
                initial.getBytes(StandardCharsets.UTF_8), restored);
        if (!identical) {
            throw new IOException("GZIP round-trip verification failed");
        }

        Files.move(temp, compressed, StandardCopyOption.REPLACE_EXISTING);
        Files.delete(plainArchive);

        Files.writeString(active, "INFO phase=running\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.TRUNCATE_EXISTING);

        System.out.println("archiveExists=" + Files.exists(compressed));
        System.out.println("plainArchiveRemoved=" + !Files.exists(plainArchive));
        System.out.println("roundTrip=" + identical);
        System.out.println("archivedLines="
                + new String(restored, StandardCharsets.UTF_8).lines().count());
        System.out.println("active=" + Files.readString(active,
                StandardCharsets.UTF_8).strip());
    }
}
~~~

Compile and run in a writable working directory:

~~~bash
javac -encoding UTF-8 GzipLogRotationDemo.java
java GzipLogRotationDemo
~~~

**Expected stdout on success:**

~~~text
archiveExists=true
plainArchiveRemoved=true
roundTrip=true
archivedLines=2
active=INFO phase=running
~~~

Explanation of each result:

- `archiveExists=true` because `app.1.log.gz` was created and the temporary file was moved to the target name.
- `plainArchiveRemoved=true` because the plain archive was deleted only **after** decompression and byte-level comparison succeeded.
- `roundTrip=true` verifies that the decompressed GZIP data matches the exact original UTF-8 byte array, including Vietnamese diacritics and newlines.
- `archivedLines=2` because the old file contained two log lines.
- `active=INFO phase=running` is the content of the new active file, showing that the old archive and the active file being written are two separate objects.

All paths live under `target/gzip-demo` in the working directory. The demo overwrites these test file names on rerun; use a **dedicated test directory**, and do not run it in a directory containing production logs with the same names.

**Important limitation of the demo:** `readAllBytes()` loads the entire decompressed file into memory for easy comparison. This is only suitable for small test files. For multi-gigabyte production archives, use streaming decompression with a bounded-memory checksum/byte comparison, or rely on a verified framework/verification pipeline. Replacing the temporary file via `Files.move(..., REPLACE_EXISTING)` is also not guaranteed to be atomic on all filesystems; production requires stronger crash handling and cleanup.

### 8.1. Requirement for Lossless Compression

Lossless compression requires:

~~~text
decompress(compress(originalBytes)) == originalBytes
~~~

Compare **bytes** rather than just line counts, because two files with the same number of lines can still have altered characters or missing bytes. Encoding (UTF-8), newline style (LF/CRLF), and byte-stream errors all matter.

GZIP includes headers/trailers and a checksum to detect many forms of corruption; however, CRC is not an authentication mechanism against intentional tampering. To guarantee security-grade integrity, design authenticated checksums/signatures or use storage with appropriate access controls.

### 8.2. Reading Compressed Archives from Java

Use `GZIPInputStream` as documented in the JDK:

~~~java
// Snippet inside a method with throws IOException:
try (GZIPInputStream input =
         new GZIPInputStream(Files.newInputStream(archivePath))) {
    byte[] all = input.readAllBytes();
    // Only use readAllBytes() when you know the decompressed file is small enough.
}
~~~

Do not use `Files.readString(archivePath)` to read a `.gz` file directly as UTF-8 text; it contains compressed bytes, not plain text characters. For large files, prefer streaming via `InputStream` or search/collection tools with gzip support.

## 9. Log Compression Does Not Replace Retention Policies

Three concepts are frequently confused:

| Goal | Mechanism | Example |
| --- | --- | --- |
| Limit a single active file cycle | Time/size trigger | Rotate daily or at 20 MB |
| Save disk space on archives | GZIP/ZIP compression | `.log.gz` |
| Bound storage duration and size | Retention/cleanup | Keep 7 daily periods or total archives ≤ 512 MB |

Suppose a system generates 12 GB/day of logs before compression; if compressed archives retain about 30% of the original bytes, that is still roughly 3.6 GB per day. Keeping seven days requires about 25.2 GB of archives, **excluding the active file, temporary compression files, backups, metadata, and other files**. Compression can substantially reduce disk usage, but it never replaces retention limits.

**Cleanup limits do not necessarily take effect instantaneously.** Archives may wait for a rollover or a cleanup job; the active file is typically excluded from archive `totalSizeCap`; and multiple instances or appenders create separate sets of archives. Therefore, measure **actual disk usage** rather than treating a single XML parameter as the system-wide footprint.

Do not delete an archive just because it was uploaded to a collector unless you have confirmed the collector received all records and your backup/retention policy allows it. Conversely, do not let a server fill up with old logs under the assumption that compression manages file age.

## 10. Estimating Compressed Size and Choosing Thresholds

To roughly estimate log volume before and after compression:

~~~text
Uncompressed bytes/day
  = (events/second) × (average bytes/event) × 86,400

Compressed bytes/day
  ≈ Uncompressed bytes/day × (compressed size / original size)
~~~

**Hypothetical example**, not a universal benchmark or compression ratio:

- 500 events/second.
- 300 bytes/event after encoding.
- Ratio `compressed size / original size = 0.30` (retaining 30% of bytes, a 70% reduction).

Calculation:

~~~text
500 × 300 = 150,000 bytes/second
150,000 × 86,400 = 12,960,000,000 bytes/day
                 = 12.96 GB/day (decimal GB)

12.96 × 0.30 = 3.888 GB archive/day
3.888 × 7   = 27.216 GB archive / 7 days
~~~

These numbers assume steady throughput and compression ratio, and exclude other logs, active file size, rollover timing, filesystem overhead, and backups. Measure on **sanitized logs** from real workloads when selecting a policy.

### Choosing File Size Before Compression

- Active file too large: infrequent rollovers, archives harder to move or read, and risk of filling the volume.
- Active file too small: constant rollovers and compression, many tiny files, high overhead, and a more complex collection pipeline.
- Too many archives: retention and file handle management become expensive.
- High compression level: may further reduce size, but increases CPU usage and compression duration depending on data.

Evaluate under load across CPU, disk I/O, throughput, p95/p99 latency, GC/heap, rollover time, compression duration, archive size, and free disk space. **There is no universal "10 MB size" that fits every application.**

## 11. Log File Compression and Async Logging Are Separate Problems

An **AsyncAppender/async logger** can offload part of the log-writing work to another thread; **archive compression** is work performed at rollover, which may use the backend's own mechanism. The two can coexist, but they are not the same thing:

~~~text
Application threads
       |
       v
Async queue (if any)
       |
       v
RollingFileAppender / RollingFile
       |
       +--> active file
       |
       +--> rollover --> archive --> compression --> retention
~~~

If the queue fills up or the JVM is killed before events are written to the active file, having archive compression **cannot recover unsaved events**. Likewise, if compression fails, async logging will not automatically repair a broken archive.

When a system has strict non-loss audit requirements, you must establish durability end-to-end from request to storage; an in-memory queue or a single file appender may not satisfy that requirement.

## 12. Log Compression in Containers and Collection Systems

In containers or orchestration platforms, the common pattern is to write logs to stdout/stderr and let the runtime and log agent manage rotation and collection:

~~~text
SLF4J / Log4j2 / JUL
       |
       v
Console appender / ConsoleHandler
       |
       v
stdout/stderr
       |
       v
Container runtime / log driver
       |
       v
Log agent / collector
       |
       v
Central storage / search / retention
~~~

This model avoids requiring the application to own active/archive files inside the container. However, **not all environments are identical**: log drivers may cap file sizes and enforce their own rotation and retention policies, while some agents do not automatically read compressed archives.

If the application still writes rolling files to a volume:

- Verify whether the agent detects the active file after rename/rollover.
- Verify how the agent handles `.gz`/`.zip`: does it ignore them, read them directly, or wait for an archive import job?
- Prevent the agent from reading the active file and the compressed archive **simultaneously** in a way that produces duplicate records.
- Do not compress or delete an archive before the collection system has ingested all records.
- Monitor disk quota and file count in the volume, because compressed archives still consume space.

Do not assume `kubectl logs` or console log commands automatically read `.log.gz` archives that an application places on an arbitrary volume. Those are two separate collection paths.

## 13. Safety, Security, and Integrity

Compression is a **space-saving** tool, not a security tool.

1. **Do not log secrets in the first place.** Never log passwords, OTPs, API keys, tokens, cookies, or unnecessary personal data; they remain present after compression.
2. **Do not treat `.gz` as encrypted.** Anyone with read access to a compressed archive can usually decompress it. Use filesystem ACLs, storage encryption, and collector access controls where needed.
3. **Keep the source until compression succeeds.** Do not delete the plain archive if compression fails or the output is unverified. If building a custom pipeline, write to a temporary file, verify, and only then rename/delete the source in a controlled manner.
4. **Prevent races during compression.** Do not let a writer keep a file open while it is being copied or compressed without explicit synchronization.
5. **Guard against corrupted archives.** Design retry, quarantine, and alerting when decompression fails; do not let a compression bug lose the root-cause evidence stored in logs.
6. **Bound decompressed data.** A small archive can decompress into a huge payload. Never call `readAllBytes()` on untrusted or unknown-size archives.
7. **Validate symlinks/paths during cleanup.** Avoid scanning or deleting files outside the archive directory, especially when paths are influenced by inputs or mounts.
8. **Backups and retention:** deleting a local `.gz` file does not automatically delete copies in the collector, backups, or object storage.
9. **Do not use GZIP checksums as security signatures.** They help detect accidental corruption, not deliberate tampering.
10. **Monitor logging errors.** An application can continue processing business logic even when an appender fails to create archives; set up independent alerts for logging errors, disk usage, and collector health.

If mandatory retention compliance is required, design a dedicated, reliable audit/storage system rather than relying on `.gz` files on a single node as the sole source of truth.

## 14. Diagnosing Common Compression Issues

| Symptom | Possible Cause | Investigation / Fix |
| --- | --- | --- |
| Active file stays `app.log`, no `.gz` yet | Rollover trigger not reached or no event after boundary | Check policy, time/size thresholds, generate a safe test event |
| Archive created but not compressed | Pattern lacks supported suffix or policy/config not loaded | Inspect `fileNamePattern`/`filePattern` and backend status |
| `.gz` file exists but fails to decompress | Extension only renamed, partial write, failed compression, or corrupt archive | Check magic bytes/format, test with `GZIPInputStream` or `gzip` tool |
| Disk full despite gzip enabled | Large active file, old archives not deleted, temp files, backups, or low compression ratio | Measure per-directory usage, check retention and compression headroom |
| No archive right at 00:00 | Rollover is evaluated on a new event or policy has not run | Check how triggers fire and when the next log event arrives |
| Archives deleted too early | Retention too aggressive or delete action matches too broadly | Check pattern, `maxHistory`, delete action, and backups |
| Archives never deleted | Missing retention, cleanup not running, or permission error | Check rollover timing and backend status messages |
| Compression spikes CPU / latency | Large files, multiple instances compressing simultaneously, threshold too small | Measure CPU, I/O, latency; tune thresholds and rollover schedule |
| Collector missing old logs | Agent does not read gzip or archive deleted too early | Check rotation/rename/compression interaction with the agent |
| Collector has duplicate logs | Reading both active file and archive with same content, or multiple appenders | Check source identity, offsets, and pipeline |
| Missing logs in archive | Writer not stopped, async queue not drained, kill/crash | Check shutdown hooks, flush, locks, and durability |
| ZIP/GZIP barely reduces size | High-entropy data or archive too small | Measure on real logs, review log volume and format |
| `GZIPInputStream` throws an error | Corrupt file, invalid GZIP, or truncated stream | Preserve original if available, quarantine, and inspect CRC/size |

### Practical Investigation Checklist

1. Verify the logger calls the **intended backend** and loads the right configuration file.
2. Verify **root/logger levels, filters, and `appender-ref`** are not blocking logs.
3. Check the active file path, write permissions, free disk space, and inode/file descriptor counts.
4. Inspect the archive pattern to distinguish `%d`, `%i`, and `.gz`/`.zip`.
5. Check daily/size trigger policies and behavior across restarts.
6. Test a small rollover in a test environment rather than forcing multi-gigabyte compression in production.
7. Confirm archives actually decompress and preserve expected records.
8. Verify retention deletes only the intended scope and cleans up failed temporary files.
9. Test behavior when the collector lags, files are renamed, and archives are compressed or deleted.
10. Measure resources and alert on backend errors, free disk space, compression duration, archive count, and collector lag.

## 15. Self-Check Exercises

1. **Concepts:** Explain the difference between rollover, compression, and retention. Does putting `.gz` in the active file name make the writer compress logs immediately?
2. **GZIP vs. ZIP:** State one practical advantage of GZIP for single-file archives and one scenario where ZIP is a better fit. Why is renaming `app.log` to `app.log.gz` not compression?
3. **Run Java 17:** Create `GzipLogRotationDemo.java`, run it with `javac` and `java`, and verify `roundTrip=true` and the active file contents. If you intentionally alter one byte in the compressed archive, what error might `GZIPInputStream` report?
4. **Logback:** Change `fileNamePattern` from `.log` to `.log.gz`; explain the roles of `maxHistory` and `totalSizeCap` once compression is enabled.
5. **Size + time:** Write a Logback pattern containing both `%d` and `%i` with a 20MB threshold; explain why multiple archives can exist for the same day.
6. **Log4j2:** Identify the roles of `RollingFile`, `TimeBasedTriggeringPolicy`, `SizeBasedTriggeringPolicy`, and `DefaultRolloverStrategy`. Why does `max="20"` not mean "keep 20 days"?
7. **JUL:** Why does `FileHandler` not automatically produce `.gz` even with `limit` and `count`? Design a workflow to compress closed files without losing logs.
8. **Capacity calculation:** At 1,000 events/s and 250 bytes/event, calculate raw GB/day. If compression reduces the size to 40% of the original bytes, roughly how many GB are needed for seven days of archives before backups?
9. **Collector:** In a file-based setup, how can compressing an archive immediately after rollover affect an agent? How do you verify there are no missing or duplicate events?
10. **Safety:** Why must you never log tokens and rely on gzip to "protect" them? Outline an access-control and retention policy for archives.
11. **Performance:** Compare a daily rotation policy against a 20MB rotation policy under highly variable traffic; choose metrics to measure compression cost.
12. **Error recovery:** If compression fails mid-way, what is the proper order of operations among keeping the original file, writing a temporary file, verifying, and cleaning up?

## 16. Official References

- Logback — Rolling File Appenders: https://logback.qos.ch/manual/appenders-rolling.html
- Apache Log4j 2 — Rolling File Appenders: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Java SE 17 — GZIPOutputStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html
- Java SE 17 — GZIPInputStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html
- Java SE 17 — java.util.logging.FileHandler: https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html

**Remember:** log file compression in Java is typically **compressing archives after rollover**, not gzipping the active file directly. In Logback, a `.gz`/`.zip` suffix on `fileNamePattern` enables compression when supported by the policy; in Log4j2, `filePattern` and the rollover strategy handle compression; JUL `FileHandler` supports rotation but does not automatically gzip. Always pair compression with **retention, data verification, access controls, disk capacity monitoring, collector coordination, and compression error handling** to save storage space without sacrificing investigability.
# Reading Log Files in Java: Viewing, Filtering, Tailing, and Safe Analysis

When a Java application writes logs to a file, the next step in incident investigation is **reading the right log file**, understanding the record structure, filtering the right events, and knowing whether the log is still being updated or has been rotated (**rotation**). Reading a log file is not just opening a text file: a single request can produce multiple events, an exception can span multiple lines, the file can be very large, and the logs visible in a terminal are not necessarily all the data that has been persisted.

The topic **“Reading Log Files”** belongs to the **File logging** group. This lesson guides you through finding the file, viewing the head/tail, following new logs, searching by level or correlation ID, reading with Java 17 using UTF-8 and bounded memory, handling compressed files, reading multiline stack traces, assessing reliability, and protecting sensitive data.

**Learning objectives:** be able to read a small or large log file, distinguish **physical lines** from **log events**, avoid overlooking file rotation, know when to use a parser/collector instead of plain-text operations, and run a standalone Java 17 program that reads logs using `BufferedReader`.

## 1. What Are You Reading in a Log File?

A typical text log file might contain:

```text
2026-11-09T10:00:00Z INFO  requestId=req-7 event=start
2026-11-09T10:00:01Z WARN  requestId=req-7 event=retry
2026-11-09T10:00:02Z ERROR requestId=req-8 event=failed
java.lang.IllegalStateException: upstream unavailable
    at com.example.PaymentClient.call(PaymentClient.java:42)
2026-11-09T10:00:03Z INFO  requestId=req-7 event=done
```

This is **illustrative data**. There are **six physical lines** but **four events** according to the format convention: the exception line and stack frame belong to the `ERROR` event. If you count with `wc -l`, the result is the number of line breaks in the file, **not the number of events**.

An event typically has:

| Field | Meaning | Example |
| --- | --- | --- |
| Timestamp | When the event occurred according to the recorded clock | `2026-11-09T10:00:02Z` |
| Level | Severity of the event | `INFO`, `WARN`, `ERROR` |
| Logger/category | Component that emitted the event | `com.example.PaymentClient` |
| Thread | Logging thread or related metadata | `http-worker-2` |
| Correlation ID | Links logs belonging to the same operation | `requestId=req-8` |
| Message | Business/technical message | `event=failed` |
| Throwable | Exception and stack trace (if any) | `IllegalStateException` |

**Not every file uses this format.** JUL, Logback, Log4j 2, Spring Boot, and JSON encoders each have their own output styles. You need to inspect the **actual formatter/layout/encoder** before writing search commands or parsers.

## 2. Finding the Right Log File Before Reading

First, determine **whether the application actually writes to a file**. A containerized service might only emit logs to stdout/stderr for an external agent to collect; in that case, there will be no `application.log` in the project directory.

Common locations in a project or environment:

- Relative file: `logs/application.log` or `logs/server.log`, resolved from the **process working directory**, not necessarily the directory containing the JAR.
- Absolute file: for example `/var/log/myapp/application.log` on Unix-like systems.
- Path specified via Spring Boot's `logging.file.name`/`logging.file.path` configuration in cases where the backend uses those properties.
- File appender configured by Logback/Log4j 2 using `<file>` or equivalent.
- JUL `FileHandler`, where the filename may contain placeholders such as `%h`, `%t`, `%g`, `%u` according to Java's conventions.
- File redirected from stdout or stderr by the system/service runner, for example `java -jar app.jar >out.log 2>err.log`.

**Do not infer from the class name:** `LoggerFactory.getLogger(MyService.class)` only creates/retrieves a logger by category; it **does not decide** where the file lives. The appender/handler configuration and startup arguments determine the output destination.

How to check in sequence:

1. Find the configuration actually loaded when the application starts.
2. Verify whether the **file appender/handler is attached to the logger/root** and active.
3. Determine the actual path, working directory, container volume/mount, and permissions of the account running the process.
4. Check whether there is a rolling policy, `.gz` compression, date suffix, or sequence number.
5. Distinguish the **currently active file** from **rotated archive files**; older error information may be in an archive file.

Finding a file with the right name but an old timestamp does not prove the application stopped logging: the log level may be filtered, the active file may have moved to another name, or the application may only be writing to stdout/stderr.

## 3. Quick Reading with Linux/macOS Commands

These commands read **an existing file** (once the path and read permissions are confirmed). They illustrate shell operations, not Java code.

### Viewing file size and metadata

```bash
ls -lh -- logs/application.log
```

`ls -lh` shows the size in human-readable units and the modification time in the listing output. Depending on the Unix system, some commands handle `--` options differently; if your environment does not support it, check that system's `ls` manual.

### Viewing the first and last few lines

```bash
head -n 20 logs/application.log
tail -n 100 logs/application.log
```

- `head`: the first lines of the file (often useful for checking startup logs).
- `tail`: the last lines of the file (often useful for checking recent errors).
- `-n 100`: limits to **100 physical lines**, not necessarily 100 log events. A long stack trace can occupy almost all 100 lines.

### Opening a file to search and scroll

```bash
less logs/application.log
```

In `less`, you can search `/requestId=req-7` and press Enter, press `n` to jump to the next match, and `q` to quit. `less` is usually preferable to running `cat` on an entire multi-GB file in the terminal. Specific tools and keybindings depend on the environment.

### Searching by identifier string

```bash
grep -n -F 'requestId=req-7' logs/application.log
```

- `-n` adds the **physical line number**.
- `-F` searches for a literal string, avoiding interpreting characters in the request ID as regex.
- For user-supplied patterns, consider adding `--` or a safe pattern-passing mechanism appropriate for the environment so the value is not treated as a flag/option.

Searching for lines containing WARN or ERROR using a simple regex:

```bash
grep -n -E ' WARN | ERROR ' logs/application.log
```

This is a **text search**, not a general-purpose log parser. It can match the message body of an INFO event containing the word ERROR, or miss formats with brackets or other levels. For production logs, rely on standardized formats/structured fields.

### Filtering by multiple conditions

```bash
grep -F 'requestId=req-7' logs/application.log | grep -E ' WARN | ERROR '
```

This pipe searches **lines** containing both the ID and the level text; continuation stack trace lines that do not contain the request ID may not appear. When investigating exceptions, inspect the **surrounding text context** or use a collector that already groups multiline events.

One way to view surrounding context with GNU grep:

```bash
grep -n -C 5 -F 'event=failed' logs/application.log
```

`-C 5` displays five lines before and after each match. It helps view stack traces, but **does not guarantee** that an entire very long exception will be captured.

### Counting physical lines

```bash
wc -l logs/application.log
```

`wc -l` counts LF newline characters according to the tool's semantics; if the last line does not end with a newline, the count may differ from the number of lines `BufferedReader.readLine()` reads. It **does not accurately count log events** when there are multiline stack traces or messages containing newlines.

## 4. Following an Actively Written Log File: `tail -f` and `tail -F`

While the application is still running, you may want to watch new logs appear in near real time:

```bash
tail -n 50 -f logs/application.log
```

This command displays the last 50 lines and continues following appended content. Press `Ctrl+C` to stop. It only displays new bytes **once they have been written/flushed by the process to the file the tool is watching**; it does not guarantee an event appears the instant the code calls the logger.

### Why can `tail -f` miss logs after rotation?

There are two common rotation patterns:

**Rename then create a new file:**

```text
logs/application.log   (file A)
        |
        | rotation
        v
logs/application.log.1 (file A, new name)
logs/application.log   (new file B)
```

A tool following the **old file descriptor/inode** may stay attached to file A while the application is writing to file B. With GNU coreutils, `tail -F` follows the **path name** and attempts to reopen it after the file is replaced, making it generally more suitable for rename-based log rotation:

```bash
tail -n 50 -F logs/application.log
```

`-F` does not mean “never lose a single byte”: it still depends on polling intervals, when the application rotates and flushes, and whether files are replaced too rapidly. Depending on the OS/`tail` version, name-following and behavior when a file disappears may vary; check the manual of the system in use.

**Copy-truncate:** the system copies the existing file to an archive and truncates the active file to 0. This can cause a window where writes/reads are lost or duplicated in some situations; the reader needs to know the rotation policy rather than assuming every file is renamed.

**Operational rule:** when investigating a time window that includes a rotation boundary, inspect both the current file **and the relevant archives**, not just `tail -f` on the open file.

## 5. Reading on Windows PowerShell

On Windows, equivalent operations can use PowerShell, with system-appropriate paths:

### Viewing the last 50 lines

```powershell
Get-Content -LiteralPath 'C:\logs\application.log' -Tail 50
```

### Following newly appended lines

```powershell
Get-Content -LiteralPath 'C:\logs\application.log' -Tail 50 -Wait
```

`-Wait` follows appended content. Behavior when a file is renamed/truncated or replaced is not necessarily identical to GNU `tail -F`; check the rotation mechanism and PowerShell version.

### Searching for a request ID

```powershell
Select-String -LiteralPath 'C:\logs\application.log' -SimpleMatch -Pattern 'requestId=req-7'
```

`Select-String` returns line-by-line matches, usually including the path and line number. `-SimpleMatch` performs a literal search, which is useful for IDs with special characters. When dealing with UTF-8 logs and Vietnamese characters, pay attention to the Windows PowerShell/PowerShell 7 version and how the tool detects encoding.

### Viewing file metadata

```powershell
Get-Item -LiteralPath 'C:\logs\application.log' |
    Select-Object FullName, Length, LastWriteTime
```

`Length` is in **bytes**, not Java characters. The commands above do not recover logs that have already been deleted/rotated or logs that were never written by an appender.

## 6. Encoding, Newlines, and Vietnamese Characters

In Java, strings are Unicode, but files contain **bytes**. To read Vietnamese text accurately, the writer and reader must agree on the **charset** (usually UTF-8).

Common pitfalls:

- The file was actually written in UTF-8, but the reading tool uses a different encoding → Vietnamese characters become garbled.
- Logs contain `CRLF` (`\r\n`), while a parser only expects LF in certain cases.
- The file has a UTF-8 BOM, or a pipeline adds/strips a BOM → the first timestamp token does not match expectations.
- The file is mid-write and the last line lacks a trailing newline → a real-time reader may observe an **incomplete line**.
- Control characters/ANSI color codes from redirected console logs are present → reading as plain text may show escape sequences or abnormal formatting.

In Java programs, explicitly specify UTF-8 instead of relying on the default charset:

```java
// Fragment using java.nio.file.Files, Path, StandardCharsets.
try (java.io.BufferedReader reader =
        java.nio.file.Files.newBufferedReader(
                path, java.nio.charset.StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process line as it is read.
    }
}
```

This is a **fragment**: `path` must be declared and the file must exist. `BufferedReader.readLine()` reads up to LF, CR, or CRLF and returns a string **without the line-termination characters**. This is convenient for line-by-line processing, but does not preserve how the file separates lines; if you need the raw bytes, use a byte-stream API.

**Correctness note:** content being actively written can change between when the reader checks the file size and when it reads. Reading a live file does not automatically create a consistent snapshot. If an analysis requires reproducible results, use a safely created copy/snapshot or a completed archive, recording the timestamp and source version.

## 7. Standalone Java 17 Example: Streaming a Log File, Filtering an ID, and Counting Sample Events

This example uses **only JDK 17+**, with no Maven or external libraries. To run on any machine without touching production logs, the program creates a **temporary directory**, writes sample log content, reads that file, prints the results, and deletes its own temporary resources upon completion.

Example goals:

1. Open the file with `Files.newBufferedReader(..., UTF_8)`.
2. Read line by line with `readLine()`, without loading the entire file into memory.
3. Count physical lines and **count events using a header convention specific to the sample file**.
4. Filter events containing `requestId=req-7`.
5. Close the reader with `try-with-resources`; leave no file handles open afterward.

Save **`ReadLogFileDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class ReadLogFileDemo {
    private static boolean isEventHeader(String line) {
        // Only valid for the SAMPLE file with this prefix.
        return line.startsWith("2026-11-09T");
    }

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("read-log-demo-");
        Path logFile = directory.resolve("application.log");

        try {
            String sample = String.join("\n",
                    "2026-11-09T10:00:00Z INFO  requestId=req-7 event=start",
                    "2026-11-09T10:00:01Z WARN  requestId=req-7 event=retry",
                    "2026-11-09T10:00:02Z ERROR requestId=req-8 event=failed",
                    "    at com.example.Service.run(Service.java:42)",
                    "2026-11-09T10:00:03Z INFO  requestId=req-7 event=done"
            ) + "\n";

            Files.writeString(
                    logFile,
                    sample,
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW);

            int physicalLines = 0;
            int events = 0;
            int warnEvents = 0;
            int errorEvents = 0;

            try (BufferedReader reader =
                    Files.newBufferedReader(logFile, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    physicalLines++;

                    if (isEventHeader(line)) {
                        events++;
                        if (line.contains(" WARN ")) {
                            warnEvents++;
                        }
                        if (line.contains(" ERROR ")) {
                            errorEvents++;
                        }
                    }
                }
            }

            System.out.println("physicalLines=" + physicalLines);
            System.out.println("events=" + events);
            System.out.println("warnEvents=" + warnEvents);
            System.out.println("errorEvents=" + errorEvents);
            System.out.println("matching requestId=req-7:");

            try (BufferedReader reader =
                    Files.newBufferedReader(logFile, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (isEventHeader(line)
                            && line.contains("requestId=req-7")) {
                        System.out.println(line);
                    }
                }
            }
        } finally {
            Files.deleteIfExists(logFile);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ReadLogFileDemo.java
java ReadLogFileDemo
```

**Exact stdout when the program runs successfully:**

```text
physicalLines=5
events=4
warnEvents=1
errorEvents=1
matching requestId=req-7:
2026-11-09T10:00:00Z INFO  requestId=req-7 event=start
2026-11-09T10:00:01Z WARN  requestId=req-7 event=retry
2026-11-09T10:00:03Z INFO  requestId=req-7 event=done
```

**Stderr:** no output is intentionally written by the program on success. If the system denies creating/writing/deleting the temporary file due to permissions or an I/O error, Java may throw an exception with a stack trace; that is not the sample success output.

Point-by-point explanation:

- The sample data has **five physical lines**: four timestamp headers and one `at com.example...` continuation line for the ERROR event. Thus `physicalLines=5` while `events=4`.
- `warnEvents=1`, `errorEvents=1` because there is only one WARN header and one ERROR header in the sample log.
- The three lines with `requestId=req-7` are three **distinct events** of the same request, not three random lines.
- `Files.createTempDirectory` creates a randomized path and does not print it, so stdout is deterministic. Files in the temporary directory do not overwrite any production logs.
- `StandardOpenOption.CREATE_NEW` requires that the temporary log file does not already exist when created; it will not accidentally overwrite an existing file.
- `try-with-resources` closes the file reader even if an error occurs during the loop. `finally` deletes the file/directory **created by the demo itself**; in a real investigation tool, **never delete the source file** after reading.

**Important limitation:** `isEventHeader()` only checks a prefix from the sample. This is **not a production parser**: files with different dates, different timestamp formats, a BOM character, JSON, or messages containing text that looks like a timestamp can produce inaccurate event counts. To count events reliably, define a standard format and a format-specific parser, or emit structured logging from the start.

### Reading a real log file instead of the sample file

For an existing file, the opening pattern is similar:

```java
// Fragment inside a method with permission to read the log file.
Path path = Path.of("logs/application.log");

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Parse each line according to the actual format; do not delete the source file.
    }
}
```

This snippet uses the imports from the main example and assumes `logs/application.log` exists. Relative paths are resolved against the **working directory**. In an application launched by a service manager or container, that is not necessarily the source directory or where the JAR is located.

## 8. Why `BufferedReader` Is Suitable for Large Files

An easy-to-write but risky approach for multi-GB files is:

```java
// Fragment that should only be used when the file is small and its size is known.
var all = Files.readAllLines(path, StandardCharsets.UTF_8);
```

`Files.readAllLines` builds a list containing every line; large files can consume massive amounts of heap and trigger `OutOfMemoryError`. `Files.readString` is also unsuitable when you want to read a very large log file into a single string.

With `BufferedReader`, the program reads **one line at a time**, keeping a bounded amount of data in memory at any moment:

```java
try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
```

This is a **fragment**: `path` and `processLine` must be provided by the application. Memory usage for held lines is typically much smaller than reading the whole file, but **a single extremely long line can still consume significant memory** because `readLine()` must construct a `String` for that line. When input may be untrusted, enforce a policy limiting **bytes/characters per record** or use an appropriate byte-streaming parser.

### Using `Files.lines(...)` with the Stream API

Java also provides:

```java
// Fragment: path is a valid Path; import java.util.stream.Stream.
try (java.util.stream.Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(line -> line.contains(" ERROR ")).count();
    System.out.println("matchingPhysicalLines=" + count);
}
```

Notes:

- `Files.lines` returns a `Stream<String>` backed by an I/O resource, so it **must be closed**, typically via `try-with-resources`.
- `filter` on strings counts **matching lines**, not log events automatically.
- `Stream` enables concise expressive pipelines, but is not the optimal default for every stateful multiline parser.
- For file-backed streams, do not casually call `parallel()` when the parser depends on ordering, state, or assembling continuation lines.
- If you need to reuse the data after the stream has been consumed, you must reopen the stream; a stream cannot be re-read automatically.

### Reading the last N lines in Java without loading the whole file

You can maintain a queue of at most N lines while scanning the file:

```java
// Fragment: imports java.util.ArrayDeque, java.util.Deque;
int limit = 100;
java.util.Deque<String> last = new java.util.ArrayDeque<>();

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        if (last.size() == limit) {
            last.removeFirst();
        }
        last.addLast(line);
    }
}
last.forEach(System.out::println);
```

The queue uses memory proportional to the **last 100 lines** rather than the whole file, but this approach still **scans from start to finish** in O(file size) time. It is not an I/O-efficient replacement for `tail` on tens-of-GB files. To read backward from the end in bytes/UTF-8, you must handle **character and newline boundaries**, rather than arbitrarily calling `RandomAccessFile.seek` and decoding from the middle of a multi-byte character.

In this snippet `limit=100`, so the queue capacity is never 0; if `limit` comes from input, validate that it is a positive number.

## 9. Accurate Log Filtering: Level, Request ID, Time, and Error Codes

During an investigation, a common workflow is:

1. Determine the time window when the error occurred, including the timezone.
2. Find the `requestId` or `traceId` from the response/client or alert, if the system provides one.
3. Filter to the right **service, file, and time window** before searching for detailed strings.
4. Inspect preceding `INFO`/`WARN` events as well as `Caused by` clauses in stack traces.
5. Cross-check error codes against metrics/tracing rather than concluding from a single ERROR line.

### Why not search by level alone?

Example:

```text
INFO  requestId=req-7 message="last error was recovered"
ERROR requestId=req-8 message="dependency timeout"
```

A literal search for `ERROR` or `error` can match text inside the **message** rather than the level field. If the format guarantees that `level` follows the timestamp, you can write a parser tailored to that format. For JSON logs, read the `level` field instead of searching text across the entire line.

### Why not search by timestamp text alone?

A file might record timestamps in UTC (`Z`), `+07:00` offset, local machine timezone, or only `HH:mm:ss`. String comparison fails when offsets differ or the format omits the date. In Java, if timestamps are ISO-8601 with an offset, you can parse them with `java.time.OffsetDateTime.parse(...)` and compare **`Instant`** values; for `Z` timestamps, `Instant.parse(...)` is a straightforward choice.

```java
// Fragment: only valid for the provided ISO-8601 timestamps.
java.time.Instant first =
        java.time.Instant.parse("2026-11-09T10:00:00Z");
java.time.Instant second =
        java.time.Instant.parse("2026-11-09T10:00:02Z");

System.out.println(first.isBefore(second)); // true
```

The last line prints `true` if run inside a method with the imports/references above. However, **timestamp ordering is not sufficient to prove absolute execution order across multiple machines**: clocks can skew or events can arrive late at a collector. Correlation IDs, sequence numbers, spans, and causal structures reconstruct system flows much more reliably.

### Preserving exception continuation lines

If an ERROR event has a stack trace:

```text
2026-11-09T10:00:02Z ERROR requestId=req-8 event=failed
java.lang.IllegalStateException: upstream unavailable
    at com.example.PaymentClient.call(PaymentClient.java:42)
    at com.example.OrderService.place(OrderService.java:17)
Caused by: java.net.SocketTimeoutException: timed out
    ...
```

then printing only the line containing `ERROR` **loses the root-cause details**. A multiline parser must define rules for **when a new event starts**, when subsequent lines belong to the previous event, and how to handle nested exceptions. If a message itself contains fake lines resembling a timestamp/level, a regex-header parser may misgroup them; properly formatted structured logging or a collector is generally more reliable.

## 10. Reading Log Files by Event Instead of Physical Line

There are three common approaches:

| File type | Appropriate reading approach | Notes |
| --- | --- | --- |
| Text, one event per line | Read line by line and parse the header | Requires a convention to escape newlines in messages |
| Text, events with multiline stack traces | Multiline parser aware of event boundaries | Error-prone if messages look like headers or multiple threads interleave |
| JSON Lines/NDJSON, one JSON object per line | Read line by line and parse into an object | Use a standard JSON parser; validate schema and record size |

**Structured logging** clearly separates `timestamp`, `level`, `logger`, `requestId`, `message`, and `exception`. Example of a JSON line:

```json
{"timestamp":"2026-11-09T10:00:02Z","level":"ERROR","requestId":"req-8","errorCode":"UPSTREAM_TIMEOUT","message":"call failed","exception":"java.lang.IllegalStateException: upstream unavailable\n    at com.example.PaymentClient.call(...)"}
```

This is **an illustrative JSON object**, where `\\n` is the escaped representation inside the string value. When an encoder actually outputs **single-line compact JSON**, each physical line can map to one event, even if the `exception` value contains logical newlines.

**Do not parse JSON yourself with `String.split(",")`**: commas can appear inside strings, nested JSON, escaped values, and fields can change order. Use a JSON parser such as Jackson or an official library matching your application version; that is a dependency outside the JDK. When parsing external logs, bound record size, nesting depth, allowed field types, and how malformed records are reported.

Do not assume every `.json` file is NDJSON: a JSON file might contain **one large array**, a pretty-printed object spanning multiple lines, or records separated by another delimiter. Know the encoder/collector contract before reading.

## 11. File Rotation: `.log.1`, Timestamps, and `.gz` Files

Production systems routinely rotate files to prevent unbounded growth:

```text
logs/application.log
logs/application.log.1
logs/application.log.2.gz
logs/application.2026-11-08.log.gz
```

The filenames here are examples. Logback, Log4j 2, JUL `FileHandler`, logrotate, or a container runtime may use different naming rules. Do not guess chronological order from filenames alone; know the actual rolling policy.

When searching for an older event:

1. Identify the incident time and timezone.
2. Check the active file and the list of archives.
3. Check the compression policy, max history, total size cap, and when files are deleted.
4. Select the archives covering the investigation window.
5. If a complete timeline is needed, read the archives in logical chronological order and handle records at rotation boundaries.
6. Cross-check with central log storage if local files have been rotated out or purged by retention.

### Reading gzip files on Unix-like systems

With GNU gzip:

```bash
gzip -dc logs/application.log.2.gz | less
```

`gzip -dc` decompresses to stdout **without creating a new decompressed file**, and `less` lets you browse it. Depending on the system, `zcat` or `zgrep` may also be available, though naming and options vary.

To search for a request ID inside an archive:

```bash
gzip -dc logs/application.log.2.gz | grep -n -F 'requestId=req-7'
```

**Security:** when reading/decompressing files from untrusted sources, account for the decompressed size; a very small `.gz` file can expand into a huge volume of data. Do not decompress the entire file into memory just to search for a string.

### Reading gzip in Java

```java
// Fragment: gzPath is a Path pointing to an existing gzip file.
try (var input = new java.util.zip.GZIPInputStream(
            Files.newInputStream(gzPath));
     var reader = new java.io.BufferedReader(
            new java.io.InputStreamReader(
                    input, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each decompressed line.
    }
}
```

This is a **fragment**, not a complete program; `gzPath`, `Files`, and `StandardCharsets` must be provided accordingly. `GZIPInputStream` only handles **gzip-compressed files**, not general ZIP archives. Even when streaming data, enforce limits on total bytes/lines/records if the source is untrusted.

## 12. Reading Logs While the Application Is Still Writing

Reading a live file introduces several edge cases:

**Partially written lines:** an appender may perform multiple writes before flushing a newline. A reader reading at that exact moment may see a partial record or not see new data yet.

**Buffering:** an event has been enqueued into an async logger but not yet flushed to the file. Not finding the text right away does not mean the application never emitted the event.

**Rotation:** the file is renamed/truncated or compressed. A reader holding the old file descriptor may no longer follow the new file; if continuous reading is needed, you must handle reopening by path and avoiding duplicate reads.

**File/encoding changes:** another process or agent writing to the same file with a different encoding/format can break parsers. By design, there should be a single owner managing the log file's lifecycle.

**Concurrent writers:** if multiple processes write text to the same file without proper synchronization/file locking, records can interleave or appear out of order. Do not assume opening a file successfully yields a consistent snapshot.

**Timestamps and ordering:** an async system may flush logs out of emission order; clocks across multiple nodes can drift. Do not naively sort by timestamp and assume exact causal relationships.

For investigations requiring **reproducible evidence**, use closed archives or snapshots with timestamps/hashes and leave source files untouched; avoid editing log files directly. Reading tools should open files in read-only mode.

### Should you write your own `tail -f` in Java?

You can, but it is a **stateful problem**, not just a `readLine()` loop:

- Track the byte offset read so far without splitting in the middle of a UTF-8 multibyte character.
- Buffer partial lines until a newline arrives.
- Track file identity and handle rotate/recreate/truncate events.
- Handle the file disappearing, permission changes, or the appender switching targets.
- Implement timeout/backoff, a clean shutdown mechanism, and avoid high-CPU busy polling.
- Manage offsets/acknowledgments if events must be delivered reliably through a collector.

NIO's `WatchService` can notify you of changes in a **directory** on some systems, but it does not assemble events, does not guarantee a one-to-one notification per append, and does not replace rotation handling. If you only need to watch logs during development, `tail -f`, `tail -F`, or `Get-Content -Wait` is simpler; in production, use a battle-tested log shipper/agent.

## 13. Permissions and Security When Reading Log Files

Logs may contain usernames, emails, IPs, session IDs, queries, exception messages, or accidentally logged payloads. **Reading a log file** is itself an operation on potentially sensitive data.

Principles to follow:

- **Only read files you are authorized to access.** Do not bypass access-control policies to view logs of other services, tenants, or users.
- **Do not send raw log files outside authorized boundaries** without a PII/secrets handling policy and a secure sharing mechanism.
- **Do not paste entire large files into tickets/chat**; instead, share the relevant excerpt with sensitive data properly masked and include the correlation ID.
- **Do not execute commands from log text.** Stack traces, URLs, or messages in logs are data, not system instructions.
- **Do not accept arbitrary paths from user input** to read server files: that creates a path traversal/file disclosure risk. If building a log-viewer UI, use an allowlist of files, validate canonical paths and symlinks, enforce authorization, limit sizes, and apply rate limits.
- **Preserve original history** if logs serve as audit evidence; reading/filtering tools must avoid modifying files or altering retention outside process.
- **Be cautious with ANSI escape/control characters** in input: when reprinting logs to a terminal, such characters can manipulate display output. Use an appropriate protective viewer/encoder when the source is untrusted.

**Note:** Redacting/masking tokens in an exported log excerpt does not fix the fact that the token already exists in the original file or storage. Remediating a leak requires a separate security assessment (revoking secrets, addressing retention/access); do not treat terminal filtering as sufficient.

## 14. Common Errors When Reading Log Files

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| `NoSuchFileException` | Wrong path, working directory, or rotated file | Check actual path, container mount, active file/archives |
| `AccessDeniedException` | Reading process lacks permissions | Check file owner/permissions per policy |
| File exists but is empty | No events emitted, filtered by level, unflushed buffer, unattached appender | Check logging config, levels, and pipeline |
| Only very old logs appear | Reading an archive or old file after rotation | Identify the file currently open by the writer |
| `tail -f` stops showing logs after rotation | Following old file instead of path name | Check rotation type; consider `tail -F` |
| Vietnamese text is garbled | Charset/BOM mismatch or console encoding issue | Verify write encoding; read consistently as UTF-8 |
| `ERROR` count exceeds actual errors | Word `ERROR` appears in messages/stack traces | Parse the level field; count events instead of lines |
| Full exception is missing | Reading only last N lines or grepping header only | Read continuation/stack trace or use a multiline parser |
| `OutOfMemoryError` when reading | `readAllLines`/`readString` on an oversized file | Stream line by line, bound record size, avoid loading all data |
| Reading `.gz` file yields gibberish | Reading compressed bytes as plain text | Wrap with a gzip decoder before the UTF-8 reader |
| Events duplicated/split at boundaries | Copy-truncate rotation or multiple writers | Check rolling policy, file identity, and collector |
| ID not found in file | Missing correlation ID, or event is in another file/service | Search by trace/service/time range and context config |
| Timestamps out of order | Different timezones, clock skew, async flushing | Parse `Instant`, cross-check trace/sequence |
| JSON parse error | File is not NDJSON or record is truncated | Check schema, bytes/record, encoder, and parser |
| `readLine` reads only part of a logical event | A multiline event is split into separate strings | Group multiline records or use one-event-per-line JSON |
| Logs appear in console but not in file | Appender only targets stdout/stderr | Check configured destinations; do not assume a file always exists |

### Investigation sequence for “missing logs”

```text
Are you sure the application called the logger?
          |
          v
Do the level and filters allow the event?
          |
          v
Is the file appender/handler attached and active?
          |
          v
Does the file path match the working directory/container?
          |
          v
Is it in the current file or a rotated archive?
          |
          v
Has it flushed; are charset and format read correctly?
          |
          v
Did a parser or filter accidentally drop the event?
          |
          v
Did the collector/storage retain the record?
```

Do not increase storage retention if the event was blocked by the logger from the start. Do not fix the parser if the file was never written by an appender. Identifying the **first layer where the event is lost or altered** reduces investigation time.

## 15. Practical Checklist

Before concluding that you have read/investigated a log file properly:

1. **Right source:** the file belongs to the target service, instance, environment, and time window.
2. **Right path:** relative/absolute path, working directory, and container mounts are clear.
3. **Right format:** you know whether it is single-line text, multiline text, or JSON Lines.
4. **Right encoding:** use UTF-8 or the matching charset; know how to handle CRLF and BOM.
5. **Right counting unit:** distinguish **physical lines** from **events**, especially with exceptions.
6. **Right time range:** parse timestamps with the correct timezone rather than assuming the reader machine's clock.
7. **Right correlation:** filter by `requestId`/`traceId`/`errorCode` and read preceding/following events.
8. **Right rotation handling:** check both the active file and relevant archives, including `.gz` if present.
9. **Right resource usage:** use buffered/streaming reads for large files, never load everything onto the heap; bound record sizes.
10. **Right reliability:** remember live files can change, events can flush late, and readers may follow an old file.
11. **Right security:** only view authorized data, never expose secrets/PII, never execute text from logs.
12. **Right cross-checking:** compare with traces, metrics, responses, or collectors when exact evidence is needed.
13. **Right outcome:** a Java 17 example can open a UTF-8 file, read line by line, count, and filter IDs without modifying production logs.

**Conclusion:** Reading log files combines **locating the file, reading efficiently, understanding the format, and tracking the data lifecycle**. Commands like `head`, `tail`, `grep`, `less`, or PowerShell enable quick checks; `BufferedReader` and `Files.lines` let you build Java tools; and log rotation, multiline stack traces, structured JSON, and access permissions determine whether your findings are reliable and safe.

## Official References

- Oracle Java 17 — `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Oracle Java 17 — `BufferedReader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html
- Oracle Java 17 — `GZIPInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html
- GNU Coreutils — `tail`: https://www.gnu.org/software/coreutils/manual/html_node/tail-invocation.html
- Logback — Appenders: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 — Appenders: https://logging.apache.org/log4j/2.x/manual/appenders.html

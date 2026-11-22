# Building a Large File Analyzer with Proper Resource Lifecycle Closing

In the **Advanced Exercises and Projects** chapter of the **Java Stream API**, we combine knowledge of Stream sources, lazy pipelines, `filter`, `map`, `reduce`, `collect`, and resource management to solve a problem close to real-world work: **analyzing a large log file without loading all lines into memory**.

The focus is not on writing the shortest pipeline. A reliable analyzer must simultaneously satisfy:

- **Correct results:** distinguish valid records from malformed lines; neither miss records nor double-count them.
- **Independence from total file size:** process line by line and store only the statistics actually needed.
- **Proper resource lifecycle closing:** the file is closed on success, when an exception is thrown, or when stopping early.
- **Clear contract:** input format, data types, memory bounds, overflow, completion timing, and error reporting policy must be defined.
- **Verifiability:** include sample data, expected results, edge cases, and extension paths.

We will build a per-service log analyzer. After the implementation, the lesson also covers adding filters, avoiding pitfalls with parallel Streams, benchmarking, and extension tasks.

> **Example environment:** Java 17 or later, UTF-8 encoding, and a text file recording one event per line. The core of the Stream API and `Files.lines` has existed since Java 8; `record`, `String.isBlank()`, and convenience APIs used in the examples require a newer version.

## 1. Problem Specification Before Writing Code

Suppose the system has a large log file where each line represents a processed request. The format is **intentionally simplified** for the project:

~~~text
timestamp|service|level|latencyMs
~~~

Where:

| Field | Type and Rules | Example |
| --- | --- | --- |
| `timestamp` | UTC instant in ISO-8601 format, parseable by `Instant.parse` | `2026-11-18T08:00:00Z` |
| `service` | Non-empty service code, consisting only of ASCII letters, digits, dots, hyphens, underscores | `checkout` |
| `level` | One of `INFO`, `WARN`, `ERROR` (case-sensitive) | `ERROR` |
| `latencyMs` | Non-negative `long` integer, in milliseconds | `145` |

The `|` character is the delimiter. The project does **not** support delimiters inside values, multi-line log entries, quoted CSV syntax, or other timestamp variants. If real data includes such cases, use a parser matching the actual format rather than arbitrarily extending `String.split`.

### Required Output

For the entire file, the report must include:

1. **Total number of lines** read.
2. **Number of valid lines** and **number of invalid lines**.
3. **Number of valid `WARN` and `ERROR` events**.
4. For **each service**: request count, error count, total processing time, maximum latency, and average latency.

Do not store the full log. A malformed line is counted toward `totalLines` and `invalidLines`, but does **not** increment service statistics.

### Sample Data

File `events.log`:

~~~text
2026-11-18T08:00:00Z|checkout|INFO|120
2026-11-18T08:00:01Z|search|WARN|45
2026-11-18T08:00:02Z|checkout|ERROR|310
not-a-log-line
2026-11-18T08:00:03Z|search|INFO|20
2026-11-18T08:00:04Z|checkout|WARN|-1
~~~

Expected output:

| Overall Metric | Value |
| --- | ---: |
| Total lines | 6 |
| Valid lines | 4 |
| Invalid lines | 2 |
| Valid `WARN` events | 1 |
| Valid `ERROR` events | 1 |

| Service | Requests | Errors | Total Latency (ms) | Max (ms) | Average (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| `checkout` | 2 | 1 | 430 | 310 | 215.00 |
| `search` | 2 | 0 | 65 | 45 | 32.50 |

The line `not-a-log-line` violates the structure; the line with `latencyMs = -1` violates the data rules. Both are excluded from service statistics.

## 2. Single-Pass Architecture

Instead of reading the entire file into a `List<String>`, we create a lazy source and traverse the file **once**:

~~~text
File events.log
      |
      v
Files.lines(path, UTF_8)       [I/O source, must be closed]
      |
      v
Stream<String>
      |
      v
collect(Report::new,
        Report::acceptLine,
        Report::merge)
      |
      v
Report
  +-- total lines / invalid lines / WARN / ERROR
  +-- Map<service, ServiceStats>
      +-- request count
      +-- ERROR count
      +-- total latency
      +-- max latency
      |
      v
Close Stream upon exiting try-with-resources
      |
      v
Print or export Report
~~~

`collect` here is a **controlled mutable reduction**: it creates the `Report` accumulator, accepts each line, and merges results into a single report. We only mutate the accumulator managed by the collector, rather than updating a shared `Map` from `parallelStream().forEach(...)`.

The memory retained is primarily **per-service statistics**, not an object for every line read. That is the difference between "analyzing a large file" and "reading a large file into a list before analyzing it".

## 3. Why Choose Files.lines and try-with-resources?

`Files.lines(path, StandardCharsets.UTF_8)` returns a `Stream<String>` that can read lines as the pipeline demands them. This source is backed by an I/O resource that must be closed.

Correct approach:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
~~~

`try-with-resources` closes the Stream upon exiting the block, even when `count()` throws an exception. Conversely, the following does not establish a closing lifecycle:

~~~java
// Avoid using this with a Files.lines source.
long count = Files.lines(path, StandardCharsets.UTF_8).count();
~~~

**Terminal operations do not automatically close the Stream.** Methods like `count`, `collect`, `reduce`, `findFirst`, `anyMatch`, or `toList` terminate the logical pipeline, but do not replace `close()` on the I/O source.

`Files.lines` may open the file successfully yet encounter an I/O error **while a terminal operation is reading data**. Depending on the stage, the error may surface as an `IOException` (opening the source) or an `UncheckedIOException` (lazy reading). Both cases must still be reported properly and must not silently turn into "a file with 0 records".

## 4. Designing Data Types and Parser Boundaries

We separate three responsibilities:

- `LogEvent`: represents **one valid line** after parsing.
- `ServiceStats`: holds statistics for **one service**.
- `Report`: holds file-wide statistics and the Map of seen services.

We can use a `record` for the parsed result data:

~~~java
enum Level { INFO, WARN, ERROR }

record LogEvent(
        java.time.Instant timestamp,
        String service,
        Level level,
        long latencyMs
) {}
~~~

The parser has a clear contract:

~~~text
parseLine(valid line)         -> LogEvent
parseLine(invalid data line)  -> null (counted as invalid)
~~~

In this **demonstration project**, using `null` as an internal parser signal keeps the code concise. For public APIs or when detailed error information is needed, use a structured parse result type—such as a `ParseResult` with `Success`/`Failure`—instead of returning `null`.

Distinguish **record errors** from **system errors**:

- Invalid timestamp, invalid `level`, negative latency: **invalid data**; the report increments the `invalidLines` counter.
- Missing file, permission denied, decoding failure, interrupted I/O: **source reading error**; should be thrown upward and never silently counted as a malformed line.
- `long` overflow during summation: **arithmetic limit error**; must be handled separately, not treated as a normal malformed record.

This design helps operations know when a report is truly complete and when it is untrustworthy.

## 5. Complete Implementation: LargeLogAnalyzer

This is a version you can place in `LargeLogAnalyzer.java` for hands-on practice. The entire analysis runs in a single `collect` pass and the file source is closed in its owning scope.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Stream;

public class LargeLogAnalyzer {

    enum Level { INFO, WARN, ERROR }

    record LogEvent(
            Instant timestamp,
            String service,
            Level level,
            long latencyMs
    ) {}

    // Statistics for exactly one service.
    static final class ServiceStats {
        long requests;
        long errors;
        long totalLatencyMs;
        long maxLatencyMs;

        void accept(LogEvent event) {
            requests = Math.addExact(requests, 1L);
            if (event.level() == Level.ERROR) {
                errors = Math.addExact(errors, 1L);
            }
            totalLatencyMs = Math.addExact(
                    totalLatencyMs, event.latencyMs());
            maxLatencyMs = Math.max(
                    maxLatencyMs, event.latencyMs());
        }

        void merge(ServiceStats other) {
            requests = Math.addExact(requests, other.requests);
            errors = Math.addExact(errors, other.errors);
            totalLatencyMs = Math.addExact(
                    totalLatencyMs, other.totalLatencyMs);
            maxLatencyMs = Math.max(
                    maxLatencyMs, other.maxLatencyMs);
        }

        double averageLatencyMs() {
            return requests == 0
                    ? 0.0
                    : (double) totalLatencyMs / requests;
        }
    }

    // Collector accumulator: each line passes through exactly once.
    static final class Report {
        long totalLines;
        long validLines;
        long invalidLines;
        long warningEvents;
        long errorEvents;
        final Map<String, ServiceStats> byService = new HashMap<>();

        void acceptLine(String line) {
            totalLines = Math.addExact(totalLines, 1L);

            LogEvent event = parseLine(line);
            if (event == null) {
                invalidLines = Math.addExact(invalidLines, 1L);
                return;
            }

            validLines = Math.addExact(validLines, 1L);

            if (event.level() == Level.WARN) {
                warningEvents = Math.addExact(warningEvents, 1L);
            } else if (event.level() == Level.ERROR) {
                errorEvents = Math.addExact(errorEvents, 1L);
            }

            byService.computeIfAbsent(
                    event.service(), key -> new ServiceStats()
            ).accept(event);
        }

        // Combiner used when the collector needs to merge separate results.
        void merge(Report other) {
            totalLines = Math.addExact(totalLines, other.totalLines);
            validLines = Math.addExact(validLines, other.validLines);
            invalidLines = Math.addExact(invalidLines, other.invalidLines);
            warningEvents = Math.addExact(
                    warningEvents, other.warningEvents);
            errorEvents = Math.addExact(
                    errorEvents, other.errorEvents);

            other.byService.forEach((service, stats) ->
                    byService.computeIfAbsent(
                            service, key -> new ServiceStats()
                    ).merge(stats)
            );
        }
    }

    // null = a line that does not match the project format.
    static LogEvent parseLine(String line) {
        String[] fields = line.split("\\|", -1);
        if (fields.length != 4) {
            return null;
        }

        String service = fields[1].trim();
        if (!service.matches("[A-Za-z0-9._-]+")) {
            return null;
        }

        try {
            Instant timestamp = Instant.parse(fields[0].trim());
            Level level = Level.valueOf(fields[2].trim());
            long latencyMs = Long.parseLong(fields[3].trim());

            if (latencyMs < 0) {
                return null;
            }

            return new LogEvent(
                    timestamp, service, level, latencyMs);
        } catch (DateTimeParseException
                 | IllegalArgumentException ex) {
            return null;
        }
    }

    static Report analyze(Path path) throws IOException {
        // Stream is opened, traversed, and closed within the same method.
        try (Stream<String> lines =
                     Files.lines(path, StandardCharsets.UTF_8)) {

            return lines.collect(
                    Report::new,
                    Report::acceptLine,
                    Report::merge
            );
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.err.println(
                    "Usage: java LargeLogAnalyzer <path-to-log>");
            return;
        }

        Report report = analyze(Path.of(args[0]));

        System.out.printf(
                "total=%d valid=%d invalid=%d warnings=%d errors=%d%n",
                report.totalLines,
                report.validLines,
                report.invalidLines,
                report.warningEvents,
                report.errorEvents
        );

        report.byService.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .forEach(entry -> {
                    ServiceStats stats = entry.getValue();
                    System.out.printf(
                            Locale.ROOT,
                            "%s: requests=%d errors=%d " +
                            "sumMs=%d maxMs=%d avgMs=%.2f%n",
                            entry.getKey(),
                            stats.requests,
                            stats.errors,
                            stats.totalLatencyMs,
                            stats.maxLatencyMs,
                            stats.averageLatencyMs()
                    );
                });
    }
}
~~~

To practice with the sample file, save the six log lines from section 1 into `events.log`, place both the Java file and the log in your working directory, and run:

~~~bash
javac LargeLogAnalyzer.java
java LargeLogAnalyzer events.log
~~~

Expected output:

~~~text
total=6 valid=4 invalid=2 warnings=1 errors=1
checkout: requests=2 errors=1 sumMs=430 maxMs=310 avgMs=215.00
search: requests=2 errors=0 sumMs=65 maxMs=45 avgMs=32.50
~~~

Service names are sorted by key **after the file source has been closed**. This is a new Stream over the resulting `Map`, not continued use of the closed file-reading Stream.

> The example assumes that the number of distinct services is small enough to keep the statistics Map in memory. In real systems, service codes may need stricter validation, and unusually large records need dedicated size-limiting policies.

## 6. Why Does This Implementation Not Load the Entire File into RAM?

A simpler approach that is poorly suited for large files:

~~~java
// Avoid doing this if the goal is single-pass large file processing.
java.util.List<String> allLines = Files.readAllLines(
        path, StandardCharsets.UTF_8);

long errors = allLines.stream()
        .filter(line -> line.contains("|ERROR|"))
        .count();
~~~

`Files.readAllLines` creates a `List<String>` containing every line. When the file is large, memory demand grows with **total text size**. Moreover, searching for the substring `"|ERROR|"` neither validates the format nor guarantees the event has a valid level.

With `Files.lines` combined with an accumulator:

~~~java
try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {

    Report report = lines.collect(
            Report::new,
            Report::acceptLine,
            Report::merge);
}
~~~

Each line is processed and can then become eligible for garbage collection; what remains long-lived are the counters and `Map<String, ServiceStats>`. Therefore, memory usage **does not grow linearly with line count** provided the number of distinct services and the length of each line are reasonably bounded.

Preliminary notation:

- `N`: total number of lines in the file.
- `D`: number of distinct services.
- `L`: maximum line size that must be processed at one time.

Processing time is typically proportional to the number of lines and the length to parse, plus Map update cost; accumulated report memory is roughly **O(D)**, while read/parsing buffers depend on the source and line size (which can be viewed as **O(D + L)** when considering only retained state).

**Note:** Never advertise "constant memory in all cases". A file with millions of distinct service codes will create huge numbers of Map entries. A single abnormally long line still must be read and parsed. If hard memory limits are required, you must change the storage model, enforce size/value caps, or use out-of-core aggregation mechanisms such as a database or external aggregation.

## 7. Role of the Three-Argument collect

Core snippet:

~~~java
return lines.collect(
        Report::new,
        Report::acceptLine,
        Report::merge
);
~~~

General signature of the overload:

~~~java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner
)
~~~

Mapping to the project:

| Parameter | Type | Role |
| --- | --- | --- |
| `supplier` | `() -> Report` | Creates an independent accumulator container. |
| `accumulator` | `(Report, String) -> void` | Counts one line, parses it, and updates statistics. |
| `combiner` | `(Report, Report) -> void` | Merges two intermediate reports when the Stream splits work. |
| Result | `Report` | The report collected after the pipeline completes. |

In sequential mode, most work goes through `acceptLine`. However, `merge` remains a required part of the collection contract and must merge all report fields with the right semantics.

**Do not do the same thing with a shared report variable and `parallel().forEach(report::acceptLine)`.** Because `Report`/`HashMap` is mutable and unsynchronized, multiple threads updating it concurrently cause race conditions. `collect` lets the Stream library manage creating and merging accumulators according to contract.

We do not use `reduce` with a mutable `Report` as identity, because that reduction style has different constraints and breaks easily when the identity is shared. `collect` is the right tool for building a mutable container.

## 8. Verifying Report Invariants

Beyond eyeballing printed output, define invariants that can be checked automatically.

### 8.1. Total Lines Must Equal Valid Lines Plus Invalid Lines

~~~text
totalLines = validLines + invalidLines
~~~

If this invariant fails, classification logic either dropped or double-counted lines.

### 8.2. Sum of Service Requests Equals Valid Lines

~~~text
sum(service.requests) = validLines
~~~

Every valid event belongs to exactly one service.

### 8.3. Sum of Service Errors Equals ERROR Events

~~~text
sum(service.errors) = errorEvents
~~~

This holds because the report counts errors only for valid records and only when `level == ERROR`.

### 8.4. Latency Must Be Non-Negative and Average Well-Defined

For each service with `requests > 0`:

~~~text
0 <= maxLatencyMs <= totalLatencyMs
averageLatencyMs = totalLatencyMs / requests
~~~

In this project, input latency is always non-negative, so maximum and total have the relationship above. If extended to negative measurements such as temperature deltas, this invariant no longer applies.

Do not use `double` to **sum** latencies when inputs are integer milliseconds; the sum here uses `long` with `Math.addExact` to detect overflow. Converting to `double` is only for **displaying the average**, where representational error when formatting to two decimal places is acceptable; if business rules require exact decimals, use `BigDecimal` with an explicit rounding rule.

## 9. When Is a Line Considered Invalid?

The parser deliberately distinguishes failure modes:

| Input | Result | Reason |
| --- | --- | --- |
| `2026-11-18T08:00:00Z\|api\|INFO\|10` | Valid | Four fields present and values valid |
| `broken` | Invalid | Insufficient fields |
| `2026-11-18T08:00:00Z\|\|INFO\|10` | Invalid | Empty service code |
| `2026-11-18T08:00:00Z\|api\|DEBUG\|10` | Invalid | Unsupported level |
| `2026-11-18T08:00:00Z\|api\|INFO\|-2` | Invalid | Negative latency |
| `2026-11-18T08:00:00Z\|api\|INFO\|abc` | Invalid | Latency is not an integer |
| `2026-99-18T08:00:00Z\|api\|INFO\|10` | Invalid | Timestamp cannot be parsed |
| Blank line | Invalid | Not exactly four fields |

The examples above use `|` as the delimiter; the backslash before it in the table is only escaping so Markdown renders the columns properly.

### Do Not Swallow I/O Errors Inside parseLine

The parser only processes **the content of a line that has already been read successfully**. If the file-reading Stream encounters a decoding or I/O error, that error belongs to the **source layer**, not a malformed `LogEvent`. Wrapping all of `analyze` in `catch(Exception)` and returning `new Report()` can turn a failed analysis into a "0 events" report, which is very dangerous.

If an application needs to tolerate input failures at the file level, it must expose a distinct report status such as `PARTIAL` or `FAILED`, rather than silently returning a fake successful report.

## 10. Proper Resource Closing Even on Early Termination

Another variant only needs to check **whether an ERROR event exists in the file**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static boolean hasErrorMarker(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.anyMatch(
                line -> line.contains("|ERROR|"));
    }
}
~~~

`anyMatch` can stop early; exiting `try` still closes the Stream. However, this example only searches for a text marker and **does not verify** that the level is in the right position or that the remaining fields are valid. If the business requirement is "has a valid `ERROR` event", replace the predicate with the parser:

~~~java
static boolean hasValidError(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.map(LargeLogAnalyzer::parseLine)
                .anyMatch(event ->
                        event != null &&
                        event.level() == Level.ERROR);
    }
}
~~~

Here `Level` is the nested enum in `LargeLogAnalyzer` from the full example, and this method can reside in the same class. Short-circuiting is no reason to omit `try-with-resources`.

Specifically, **`count()`/`toList()`/`collect()`/`findFirst()` do not call `close()` themselves**, whether they consumed the entire file or stopped early.

## 11. Common Resource Bug: Returning a Closed Stream

Do not write:

~~~java
// Wrong: caller receives a lazy pipeline depending on a closed Stream.
static Stream<String> badOpen(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.filter(line -> !line.isBlank());
    }
}
~~~

`filter` is a lazy intermediate operation. Before the caller invokes a terminal operation, the `try` block has already exited and the Stream is closed.

Two correct options:

**Option A — The method owns the Stream and returns the computed result:**

~~~java
static long countNonBlank(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

**Option B — The method returns an open Stream and delegates closing responsibility to the caller:**

~~~java
/**
 * Caller owns and must close the returned Stream.
 */
static Stream<String> openNonBlank(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> !line.isBlank());
}

// Caller side:
try (Stream<String> lines = openNonBlank(path)) {
    long count = lines.count();
}
~~~

In the main project, choose Option A: `analyze(Path)` owns the source and returns the completed `Report`; the caller does not have to manage the Stream.

If you need to return lazy data so the caller controls the pipeline, document ownership explicitly. Never create an I/O Stream and forget who will close it.

## 12. Read Errors, Close Errors, and Exception Scope

With `Files.lines`, distinguish:

- **`IOException` on open:** missing file, insufficient permissions, or source cannot be opened.
- **`UncheckedIOException` during lazy read:** an I/O error may arise while `collect` is requesting the next line.
- **`ArithmeticException`:** `Math.addExact` detects when a counter or latency sum exceeds `long` bounds.
- **Other `RuntimeException`:** programming bugs in the accumulator or parser, if any.

Caller layer example:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;

try {
    LargeLogAnalyzer.Report report =
            LargeLogAnalyzer.analyze(path);
    // Only publish the report after analysis completes.
} catch (IOException | UncheckedIOException ex) {
    System.err.println("Cannot read file: " + path);
    // Log or report failure to the calling system.
} catch (ArithmeticException ex) {
    System.err.println("Aggregated value exceeded long limit");
}
~~~

`try-with-resources` runs `close()` even when the terminal operation throws. If both a processing error and a close error occur, Java keeps the processing error as the primary exception and may attach the close error via `getSuppressed()`.

A production system should record the path, cause, and processing status; it should never display incomplete results as complete.

## 13. Testing Before Using Real Files

You can build a small dataset with `List<String>` and use the **exact same accumulator logic** to test. You do not need a huge file to verify summation or parsing rules.

~~~java
import java.util.List;

List<String> sample = List.of(
        "2026-11-18T08:00:00Z|checkout|INFO|120",
        "2026-11-18T08:00:01Z|search|WARN|45",
        "2026-11-18T08:00:02Z|checkout|ERROR|310",
        "not-a-log-line",
        "2026-11-18T08:00:03Z|search|INFO|20",
        "2026-11-18T08:00:04Z|checkout|WARN|-1"
);

LargeLogAnalyzer.Report report = sample.stream()
        .collect(
                LargeLogAnalyzer.Report::new,
                LargeLogAnalyzer.Report::acceptLine,
                LargeLogAnalyzer.Report::merge
        );

if (report.totalLines != 6L ||
        report.validLines != 4L ||
        report.invalidLines != 2L ||
        report.errorEvents != 1L ||
        report.warningEvents != 1L) {
    throw new AssertionError("Incorrect overall statistics");
}

if (report.byService.get("checkout").totalLatencyMs != 430L) {
    throw new AssertionError("Incorrect checkout total latency");
}
~~~

This example assumes the test code is in the same package or in a context with access to the package-private members of `LargeLogAnalyzer`.

### Essential Test Case Matrix

| Scenario | What to Verify |
| --- | --- |
| Empty file | All counters are 0, service Map is empty |
| Single valid line | Total and valid lines equal 1, correct service |
| Single malformed line | Total lines equals 1, invalid equals 1 |
| Blank line, missing or extra fields | Parser classifies properly, throws no unexpected error |
| Bad timestamp, unsupported level | Counted as invalid |
| Negative latency, non-numeric, or exceeding `long` | Counted as invalid |
| Multiple lines for the same service | Count, errors, sum, max aggregate accurately |
| Multiple services | Statistics keys are not mixed |
| Non-existent file | Read error raised, no fake successful report created |
| File larger than available memory | Does not retain all lines; still measure actual memory |
| Source fails mid-traversal | Error propagates properly, resource still closed |
| Services repeated many times | Memory does not grow with occurrences of the same key |

Do not check only total line count. A program can count `totalLines` accurately while attributing metrics to the wrong services or swallowing I/O errors.

## 14. Adding Tests for Resource Lifecycle

For I/O sources, correctness is not just in the report data. You must test **resource closing on completion and on error**.

A simulation without accessing a real file:

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.stream.Stream;

AtomicBoolean closed = new AtomicBoolean(false);

try (Stream<String> lines = List.of("a", "b").stream()
        .onClose(() -> closed.set(true))) {

    long count = lines.count();
    System.out.println(count); // 2
}

System.out.println(closed.get()); // true
~~~

`onClose` illustrates when the Stream is closed. Do not infer that `count()` closes it automatically; `try-with-resources` is what invokes `close()` when leaving the block.

To test the error path:

~~~java
AtomicBoolean closed = new AtomicBoolean(false);

try (Stream<String> lines = Stream.of("x")
        .onClose(() -> closed.set(true))) {

    throw new IllegalStateException("processing failed");
} catch (IllegalStateException ex) {
    // Processing error is reported, yet the close handler still ran.
}

System.out.println(closed.get()); // true
~~~

This tests the **closing mechanism** in simulation, not a proof that `Files.lines` itself closes OS file handles on every platform. For real resources, integration tests can open/read files across different paths and monitor file descriptors/handles where the environment permits.

## 15. Should You Use parallelStream for Large Files?

**Not by default.** A large file does not automatically become easy to split for parallel work.

~~~java
try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {

    Report report = lines.parallel().collect(
            Report::new,
            Report::acceptLine,
            Report::merge
    );
}
~~~

In principle, `Stream.collect` can accumulate into independent intermediate `Report` instances and merge them with `merge`. Integer addition using `Math.addExact` and taking `max` are associative when values stay within bounds. However, parallel execution also depends on how splittable the source is, how errors are handled, and the cost of merging Maps.

**The standard version of the project uses a sequential Stream.** Consider parallelism only after:

1. Proving `Report.merge` is correct across multiple data splits.
2. Ensuring all mappers/accumulators avoid shared mutable state outside the accumulator container.
3. Confirming record order is unnecessary for the current statistics.
4. Benchmarking with sufficiently large files, multiple services, and realistic data.
5. Identifying CPU, I/O, memory, and error-handling limits.

In particular, `Files.lines` may have varying source-splitting characteristics depending on how the file is read and its charset. Parallelizing parsing does not guarantee a speedup if the bottleneck is disk read speed or batch creation overhead.

**Pitfall to avoid:**

~~~java
Report shared = new Report();

// Unsafe: multiple tasks mutate shared HashMap and counters.
try (Stream<String> lines = Files.lines(path)) {
    lines.parallel().forEach(shared::acceptLine);
}
~~~

`Report` is not a concurrent data structure. Use a proper collector or keep the pipeline sequential; do not mechanically slap `synchronized` onto it to mask a design flaw.

## 16. Extension: Reporting Across Multiple Files in a Directory

If you need to analyze multiple files, you must manage **two levels of resources**: the directory-listing Stream and the Stream reading each file.

A controllable design collects a finite list of paths from the directory, **closes the listing Stream**, and then processes each file independently:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static List<Path> logFiles(Path dir) throws IOException {
    try (Stream<Path> paths = Files.list(dir)) {
        return paths
                .filter(Files::isRegularFile)
                .filter(path -> path.getFileName()
                        .toString().endsWith(".log"))
                .sorted()
                .toList();
    }
}
~~~

The caller can iterate over `List<Path>` and call `LargeLogAnalyzer.analyze(path)` for each file. Each call closes its own file-reading Stream.

If a combined report is needed:

~~~java
LargeLogAnalyzer.Report combined = new LargeLogAnalyzer.Report();

for (Path file : logFiles(directory)) {
    LargeLogAnalyzer.Report oneFile =
            LargeLogAnalyzer.analyze(file);

    combined.merge(oneFile);
}
~~~

Here `directory` is the caller's directory path. `combined` is an accumulator outside the Stream, used **sequentially**; no multiple threads mutate it concurrently. Only publish the final report after all files have been analyzed successfully.

Collecting the path list causes memory to grow with the **number of files**. If the directory contains a massive number of files, consider processing each `Path` directly within the `Files.list` scope with explicit error handling and ownership.

## 17. Limitations and Design Decisions in Real Applications

This project intentionally simplifies several aspects. Before deploying to production, decide on:

### 17.1. Log Format

If logs are CSV with commas/quotes, JSON Lines, or a binary format, do not rely on `String.split("\\|")`. Use a spec-compliant parser and decide how overly long lines or payloads containing newlines are handled.

### 17.2. Sensitive Data

Do not include raw log lines verbatim in error reports if lines might contain access keys, emails, tokens, or personal data. Only retain allowed fields, cap error sample length, and apply data masking policies.

### 17.3. Metric Precision

`Math.addExact` signals when a `long` sum overflows, but does not fix the data. For values that may exceed limits, consider `BigInteger` or another aggregation strategy. When average latency requires decimal accuracy, use `BigDecimal` with an explicit `RoundingMode`.

### 17.4. Key Cardinality and Memory Bounds

A Map holds one entry per service. If `service` is dynamically generated per request or user, the number of keys can explode. In that case, cap cardinality, group under valid criteria, or aggregate out-of-core.

### 17.5. Files Being Written Concurrently

This lesson assumes the input file is a stable snapshot during analysis. `Files.lines` does not automatically provide consistent snapshot semantics if another process continuously appends to or modifies the file. Use log rotation, snapshots, or file-locking contracts if consistent reporting is required.

### 17.6. Publishing Reports

Do not overwrite an official report while analysis is incomplete. If JSON/CSV export is required, write to a temporary output, publish only after reading and closing the source succeed, and handle destination writes safely against partial/failed writes.

## 18. Tiered Advanced Tasks

| Level | Task | Acceptance Criteria |
| --- | --- | --- |
| Basic | Read one file, count valid/invalid, close source | Matches sample data; file is always closed |
| Intermediate | Compute `WARN`/`ERROR` and per-service latency stats | Invariants in section 8 hold |
| Intermediate | Record at most N invalid line samples | Does not retain all bad lines; bounded memory |
| Upper-Intermediate | Group stats by `(service, level)` or by UTC date | Aggregation keys do not mix data |
| Upper-Intermediate | Analyze multiple files and merge reports | Each file Stream and listing Stream are closed |
| Hard | Refactor parser to return `ParseResult` instead of `null` | Distinguishes error codes, never swallows I/O errors |
| Hard | Compare sequential vs. parallel pipelines | Results obey contract, accompanied by proper benchmark |
| Hard | Handle inputs with millions of distinct keys | Sensible memory/cardinality strategy |

### Extension A — Retaining N Invalid Line Samples

Add a small list to `Report`:

~~~java
private static final int MAX_SAMPLES = 10;
private final java.util.List<String> invalidSamples =
        new java.util.ArrayList<>();
~~~

When encountering an invalid line, append only if capacity remains:

~~~java
if (invalidSamples.size() < MAX_SAMPLES) {
    invalidSamples.add(line);
}
~~~

However, remember **a line can be very long** or contain sensitive data. Truncate character length and mask sensitive fields as needed, and specify the ordering and selection rules when merging two intermediate reports. Do not cap sample count while ignoring the size of each sample.

### Extension B — Processing Time by Date

From a `LogEvent`'s `Instant`, you can extract the UTC date:

~~~java
java.time.LocalDate day = event.timestamp()
        .atZone(java.time.ZoneOffset.UTC)
        .toLocalDate();
~~~

If grouping by date, explicitly define the business time zone. UTC and local time can produce **different dates** for events near midnight boundaries. Never mix UTC timestamps with local dates implicitly.

### Extension C — Resource Failure Scenarios

Design tests for missing files, permission-denied files, and processing actions that throw exceptions. The goal is to prove the program does not leave resources open and **does not publish fake results on failure**.

## 19. Project Acceptance Checklist

Before considering the analyzer complete, check:

- [ ] Input adheres to the described format; parser does not silently accept out-of-contract values.
- [ ] Sample data produces exact `total=6, valid=4, invalid=2, warnings=1, errors=1`.
- [ ] `checkout` has 2 requests, total 430 ms, max 310 ms; `search` has 2 requests, total 65 ms.
- [ ] Empty files, malformed lines, negative numbers, and duplicate keys are handled properly.
- [ ] Neither `Files.readAllLines` nor `Stream.toList` is called to retain the entire large log.
- [ ] `Files.lines` is opened, traversed, and closed inside `try-with-resources`.
- [ ] Error handling paths exist when `Files.lines` or the terminal operation throws I/O errors.
- [ ] Counters/sums do not overflow silently; clear behavior exists when `ArithmeticException` occurs.
- [ ] `parallel().forEach(...)` is never used to mutate a shared `HashMap` or counters.
- [ ] Memory is evaluated by distinct key count and max line size, not line count alone.
- [ ] Report is used only after analysis finishes and the source is closed.
- [ ] Integration tests fit the runtime environment; performance benchmarks are kept separate from correctness tests.

## 20. Self-Check Exercises

**Exercise 1.** Why is `Files.readAllLines(path)` not the default choice for very large log files?

**Answer:** It materializes all lines into a `List<String>`, causing memory to scale with data size. Using `Files.lines` with an aggregating collector avoids retaining all lines when only statistics are needed.

**Exercise 2.** If the analyzer sees 10 lines, of which 7 are valid and 3 are malformed, what are the basic invariants?

**Answer:** `totalLines = 10`, `validLines = 7`, `invalidLines = 3`, and the sum of `requests` across all services is 7.

**Exercise 3.** Once `lines.filter(...).findFirst()` returns, can `close()` be omitted?

**Answer:** No. Short-circuiting stops the pipeline but does not automatically close the I/O resource. Wrap Stream creation and the terminal operation in `try-with-resources`.

**Exercise 4.** Why not use `Report shared = new Report(); lines.parallel().forEach(shared::acceptLine)`?

**Answer:** Multiple tasks would mutate shared counters and a mutable `HashMap`. That is unsafe and can corrupt results. Use `collect` with private accumulators or keep the pipeline sequential.

**Exercise 5.** With one million lines but only three services, will this design's memory grow proportionally to the number of lines?

**Answer:** Not proportionally to **already processed** lines, provided the source does not retain all lines and there are no excessively long lines; the report itself holds around three service entries. Still, you cannot claim an absolute memory bound because of I/O buffers, parser allocations, and individual line sizes.

**Exercise 6.** A file starts with valid data and then loses read permission mid-read. Should we return a `Report` with the processed lines and mark it as "success"?

**Answer:** No, unless the system has an explicitly marked partial-report contract. For this project, the I/O error must propagate and the caller must not publish a fake complete report.

**Exercise 7.** If we want daily statistics in Vietnam, what should we use?

**Answer:** Explicitly select the business time zone, for example `ZoneId.of("Asia/Ho_Chi_Minh")`, convert the `Instant` to a date in that zone, and then group. Do not blindly extract the UTC date if the report requires local dates.

## 21. Key Takeaways

- **Put I/O sources in `try-with-resources`:** terminal operations such as `collect`, `count`, or `findFirst` do not close `Files.lines` automatically.
- **Read in one pass, keep statistics:** use a collector with a clearly scoped accumulator instead of materializing every line.
- **Separate data errors from system errors:** a malformed line differs from an I/O failure or arithmetic overflow during aggregation.
- **Design by contract:** define format, grouping, time units, metric calculation, key cardinality limits, and source consistency.
- **Never share mutable accumulators carelessly:** `collect` fits mutable reduction; consider parallelism only when the combiner is proven correct and benchmarked.
- **Keep resources open throughout the lazy pipeline:** never return an already-closed Stream; whoever opens the source must close it or transfer ownership explicitly.
- **Optimize after correctness:** verify sample outputs, invariants, and resource lifecycle before benchmarking large files.

**Main takeaway:** A reliable large file analyzer is not judged solely by how fast it reads. It must **read element by element without holding the entire file, aggregate accurately, distinguish record errors from I/O errors, and guarantee source closing on every exit path**. `Files.lines` combined with `try-with-resources` and a well-designed collector is a foundational practical pattern for building safe Stream API pipelines in real-world applications.

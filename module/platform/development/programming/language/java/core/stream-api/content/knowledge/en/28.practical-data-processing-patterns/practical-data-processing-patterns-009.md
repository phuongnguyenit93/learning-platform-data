# Line-by-Line Log File Analysis with Explicit Error-Handling Policies

## 1. Problem: Log Reports Must Never Silently Drop Data

In **JAVA_STREAM_API**, pipelines of `filter`, `map`, `reduce`, and `collect` fit well for turning log lines into summary metrics. However, a log file is not a clean in-memory `List`: lines may be malformed, measured values may be invalid, the file may be deleted mid-read, and I/O errors can occur after a stream opens successfully.

Suppose an application writes logs in this format:

```text
2026-11-18T08:00:00Z|INFO|api|40
2026-11-18T08:00:01Z|ERROR|api|120

2026-11-18T08:00:02Z|WARN|worker|75
invalid line
2026-11-18T08:00:03Z|ERROR|api|80
2026-11-18T08:00:04Z|INFO|worker|-1
```

Each valid line contains: `timestamp|level|service|durationMs`. Line 3 is blank, line 5 lacks fields, and line 7 has a negative duration.

An approach like:

```java
// Unreliable if you need to know whether the source contained invalid lines:
long errors = Files.lines(path)
    .map(LogParser::parseOrNull)
    .filter(Objects::nonNull)
    .filter(event -> event.level() == Level.ERROR)
    .count();
```

may report `2` ERROR events, yet gives no indication of **how many lines were skipped**, **at which line numbers**, or **why**. This snippet also fails to close the `Files.lines` stream. If the parser swallows every exception and returns `null`, the system easily produces a "successful" report from incomplete data.

In the **Practical Data Processing Patterns** chapter, this lesson builds a line-by-line log processing pipeline with an **explicit error-handling contract**, ensuring:

1. Streaming log reads without loading the whole file into memory.
2. Preserving line numbers to pinpoint errors.
3. Distinguishing **valid lines**, **blank lines**, and **malformed lines**.
4. Supporting three policies: **FAIL_FAST**, **SKIP_WITH_COUNT**, and **COLLECT_ERRORS**.
5. Separating log-content errors from **file open/read/close I/O errors**.
6. Aggregating event count, min/max duration, and average duration by `service` and `level` in **a single pass**.
7. Testing empty sources, bad inputs, bounded error samples, arithmetic overflow, and resources.

Complete examples use **Java 17+** (for `record` and `sealed interface`). The focus is the Stream API and data policies; this is not a full parser for every production log format.

## 2. Define the Data Contract Before Writing the Pipeline

### 2.1. Valid Line Format

| Field | Example | Rule |
| --- | --- | --- |
| `timestamp` | `2026-11-18T08:00:00Z` | Timestamp string parseable via `Instant.parse` |
| `level` | `INFO`, `WARN`, `ERROR` | Must match the published enum strictly |
| `service` | `api`, `worker-1` | Identifier matching `[a-z][a-z0-9-]{0,31}` |
| `durationMs` | `40`, `120` | Non-negative `long` integer |

Here `|` separates fields. Use `String.split("\\|", -1)`: `|` is a regex metacharacter so it must be escaped, and `-1` preserves **trailing empty fields** so missing data is caught.

Examples:

```text
2026-11-18T08:00:00Z|INFO|api|40  -> valid
2026-11-18T08:00:00Z|DEBUG|api|40 -> invalid level
2026-11-18T08:00:00Z|INFO|api|   -> invalid duration
2026-11-18T08:00:00Z|INFO|api|-1 -> negative duration
2026-11-18T08:00:00Z|INFO|api    -> missing one field
```

Never assume `DEBUG` equals `INFO` or an empty `durationMs` equals `0`. Such coercions require **explicit business rules** before acceptance.

### 2.2. Three Distinct Line Categories

| Category | Meaning | Contributes to Report? |
| --- | --- | --- |
| **Valid** | Parses into an event with valid fields | Yes: increments event count and updates metrics |
| **Blank** | Empty or whitespace-only line | Not an event; increments `blankLines` |
| **Invalid** | Has content but violates schema or value bounds | Not an event; increments `invalidLines` and follows policy |

This lesson's contract **does not count blank lines as errors**. Another system might decide differently, provided it defines and tests that choice clearly.

For every file processed to completion without I/O errors:

\[
\text{totalLines}=\text{validLines}+\text{blankLines}+\text{invalidLines}
\]

This is a key **test invariant**. Never filter out invalid lines prematurely so the system loses track of how many lines were discarded.

## 3. Explicitly Define Three Invalid-Line Policies

### 3.1. `FAIL_FAST` — Stop on the First Invalid Line

When the parser encounters a non-blank malformed line, throw an exception carrying **line number and reason code**. Do not return a partial report as if the run succeeded.

Suitable for:

- Pipelines requiring **complete, clean** data before billing, charging, or publishing.
- Data-quality gates before main processing.
- Systems where a single bad line invalidates the statistics.

Drawback: does not list all bad lines in one pass. Run an error-audit mode beforehand if multiple issues must be gathered together.

### 3.2. `SKIP_WITH_COUNT` — Skip Bad Lines While Always Counting Them

Do not throw on **malformed lines**, but increment `invalidLines` and aggregate only valid events. Do not retain individual error details.

Suitable for sources whose spec allows **best-effort** processing while still monitoring error rates.

Never call a report "complete" when `invalidLines > 0`. Downstream stages can enforce quality thresholds—for example, refusing to publish if the error rate exceeds a configured limit.

### 3.3. `COLLECT_ERRORS` — Continue and Keep Bounded Error Samples

Matches `SKIP_WITH_COUNT` in metrics and invalid-line counts, while also keeping up to `sampleLimit` error items, each holding **line number and error code**—without storing raw line text that could contain secrets.

Suitable for:

- Operational reports needing both metrics and diagnostics.
- Initial log-ingestion tools surfacing multiple schema errors at once.
- Data-quality dashboards that must avoid buffering every bad line in RAM.

**Crucial rule:** `sampleLimit` **caps only stored error samples**, never the number of processed lines and never `invalidLines`. If a file has one million invalid lines and the sample cap is 20, the invalid counter must still reach one million.

### 3.4. Outcome Matrix

| Scenario | FAIL_FAST | SKIP_WITH_COUNT | COLLECT_ERRORS |
| --- | --- | --- | --- |
| Valid line | Aggregate | Aggregate | Aggregate |
| Blank line | Count blank, continue | Count blank, continue | Count blank, continue |
| Schema-invalid line | Throw exception | Increment invalid, continue | Increment invalid, store sample up to limit |
| File cannot be opened | I/O error | **Still I/O error** | **Still I/O error** |
| Read fails mid-file | I/O error | **Still I/O error** | **Still I/O error** |
| Report returned normally | Zero invalid lines | May have invalid lines | May have invalid lines |

**Do not conflate these two error classes:** a policy to skip **invalid lines** does not authorize silently skipping **unreadable files**. If you need to continue when a file fails, design a **per-file** result with success/failure state and audit all skipped files.

## 4. Reading Files with `Files.lines` and Managing Stream Lifecycle

`Files.lines(path, charset)` returns a **lazy** `Stream<String>` of lines, avoiding loading the whole file into memory:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> !line.isBlank())
            .count();
    }
}
```

**Resource ownership:**

- `Files.lines` opens an I/O resource; the **caller must close the stream**.
- `count()`, `collect()`, and `toList()` are terminal operations that **do not call `close()`**.
- `try-with-resources` closes the source both on normal completion and when a terminal operation throws.
- `Files.lines` can throw checked `IOException` on open; read failures occurring **during traversal** are wrapped in `UncheckedIOException`.
- Specify the right charset; this lesson uses UTF-8. Never "fix" a wrong encoding by silently dropping lines that fail parsing.

### 4.1. Why Not Read Every Line with `readAllLines`?

`Files.readAllLines(path)` loads all lines into a list. On huge files, memory grows with total file content. `Files.lines` or `BufferedReader.readLine` processes line by line while keeping statistical state **far smaller**.

When **physical line numbers** are needed for errors, a bare `Files.lines` stream has no built-in line index. Incrementing a mutable `AtomicLong` inside `map` breaks easily if the pipeline is parallelized or optimized. This lesson provides a **sequential line-numbered stream source** so mappers remain free of side effects.

### 4.2. `BufferedReader.lines()` and Reader Ownership

`BufferedReader.lines()` produces a stream of lines from the reader, yet the reader **remains owned by whoever opened it**:

```java
import java.io.BufferedReader;

try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    long count = reader.lines().count();
}
// Reader is closed by try-with-resources.
```

Never assume closing `reader.lines()` automatically closes the `BufferedReader`. In the complete solution, we own the reader directly and close it at the analysis method's boundary.

## 5. Pure Parser: Return a Typed Outcome

A testable parser should depend only on **line content** and **line number**, without opening files, logging globally, incrementing global counters, or deciding fail-fast policy itself.

Type design:

```java
record NumberedLine(long number, String text) {}
record LogEvent(Instant time, Level level, String service, long durationMs) {}

sealed interface ParseOutcome permits Accepted, Blank, Rejected {}

record Accepted(LogEvent event) implements ParseOutcome {}
record Blank(long lineNumber) implements ParseOutcome {}
record Rejected(Issue issue) implements ParseOutcome {}

record Issue(long lineNumber, String code) {}
```

**Why not use `Optional<LogEvent>` for everything?**

`Optional.empty()` cannot distinguish a blank line from a malformed line. When business rules require separating them, an explicit sum-type outcome is much clearer. Only when both intentionally mean "no event" does `Optional` suffice.

Field splitting example:

```java
String[] fields = line.split("\\|", -1);
if (fields.length != 4) {
    return new Rejected(new Issue(lineNumber, "FIELD_COUNT"));
}
```

Then validate timestamp, level, service, and duration in turn. Catch **expected data exceptions** such as `DateTimeParseException` and `NumberFormatException`. Avoid `catch (Exception e) { return Optional.empty(); }`, which can swallow programming bugs or infrastructure failures.

### 5.1. Structured Error Codes Beat Raw Line Dumps

An `Issue(7, "NEGATIVE_DURATION")` tells operators the failure reason and points straight to line 7 in the source file. Because logs may contain tokens, PII, or sensitive business data, **do not dump full raw lines into reports, consoles, or dashboards by default**. If a preview snippet is required, bound its length, strip control characters, and redact sensitive fields per security policy.

### 5.2. What Does Line Number Mean?

Here `lineNumber` starts at **1** and increments each time `BufferedReader.readLine()` returns a line, including blank lines. It counts **lines in the file read during that pass**, not byte offsets, timestamps, or valid events. If a single log record spans multiple physical lines (e.g., multiline stack traces), replace the single-line parser with a stateful framing parser under its own contract.

## 6. `Stream<NumberedLine>` Source Without Mapper Counters

To pair **line numbers** with **line text** when total line count is unknown upfront, build a sequential `Iterator<NumberedLine>` over `BufferedReader`, then wrap it:

```java
StreamSupport.stream(
    Spliterators.spliteratorUnknownSize(
        iterator, Spliterator.ORDERED | Spliterator.NONNULL
    ),
    false
);
```

Concept:

```text
BufferedReader.readLine()
      │
      ├─ call 1 -> NumberedLine(1, "2026-...|INFO|api|40")
      ├─ call 2 -> NumberedLine(2, "2026-...|ERROR|api|120")
      ├─ call 3 -> NumberedLine(3, "")
      └─ EOF    -> no more elements
                      │
                      ▼
           Sequential Stream<NumberedLine>
                      │
                  map(parse)
                      │
           collect(reportCollector)
```

Characteristics `ORDERED` matches physical line order, and `NONNULL` holds because every emitted element is a non-null `NumberedLine`. **Do not** declare `SIZED` or `SUBSIZED`, because line count is unknown ahead of time.

### 6.1. Why Must the `Iterator` Manage Lookahead?

`Iterator.hasNext()` can be called multiple times before `next()`. The implementation must **buffer at most one pre-read line** so repeated `hasNext` calls do not skip lines. When `next()` runs, it returns the buffered line and clears the ready flag for the next read.

If `readLine()` throws `IOException`, the iterator wraps it in `UncheckedIOException` because `Iterator.hasNext/next` cannot throw checked exceptions. That exception **propagates out** rather than turning into a schema-error row.

### 6.2. Do Not Arbitrarily Parallelize This Iterator Source

`BufferedReader` has sequential read state; the `Iterator` owns a line counter. This lesson sets `StreamSupport.stream(..., false)` to keep line numbers and ordering exact. Adding `parallel()` downstream does not let multiple workers safely call `readLine` with accurate line numbers; parallel file splitting requires careful byte-range and line-boundary design.

## 7. Report Accumulator: Count Errors and Aggregate Events in One Pass

An inefficient or invalid attempt:

```java
// Cannot reuse an already-consumed Stream<String>:
long total = lines.count();
long errors = lines.filter(LogParser::isError).count();
```

On an I/O stream, you cannot run two terminal operations on **the same consumed stream**. Re-reading the file for separate counts wastes I/O and risks the file changing between passes.

Instead, a custom `Collector` consumes each `ParseOutcome` and updates compact state:

```text
                    ParseOutcome
                          │
           ┌──────────────┼────────────────┐
           ▼              ▼                ▼
       Accepted          Blank           Rejected
           │              │                │
       validLines++    blankLines++    invalidLines++
           │                               │
   service + level map            policy FAIL/SKIP/COLLECT
           │
      GroupStats
   count/sum/min/max
           │
           ▼
      Final Report
```

The accumulator holds:

- `totalLines`, `validLines`, `blankLines`, `invalidLines`;
- map `service → level → GroupStats`;
- up to `sampleLimit` `Issue` samples;
- policy and sample-limit settings.

Using `Math.addExact` for counts and total durations **throws `ArithmeticException` on `long` overflow** instead of silently wrapping to a wrong total. A `double` mean is a floating-point approximation suitable for typical latency summaries; currency or exact-precision figures require dedicated arithmetic rules.

### 7.1. Why Does the Collector Have a `combiner` If the Source Is Sequential?

The `Collector<T,A,R>` contract comprises supplier, accumulator, combiner, and finisher. Even when the current source is sequential, writing an **associative** combiner is part of a well-formed collector. Here:

- Counters add via `Math.addExact`.
- Matching-key stats merge count/sum/min/max.
- Error samples append left-to-right and **cap at `sampleLimit`**.
- `CONCURRENT` is not declared for mutable maps/accumulators.

This does **not** magically make `BufferedReader` parallel-safe. The I/O source and the collector have separate responsibilities.

## 8. Complete Java 17 Program: `LogLineAnalyzer`

The file below is standalone and can be saved as `LogLineAnalyzer.java`. It combines a sequential line-numbered source, pure parser, and error-aware aggregating collector.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

public final class LogLineAnalyzer {

    private LogLineAnalyzer() {}

    public enum Level { INFO, WARN, ERROR }

    public enum InvalidLinePolicy {
        FAIL_FAST,
        SKIP_WITH_COUNT,
        COLLECT_ERRORS
    }

    public record Issue(long lineNumber, String code) {}

    public record Metric(
        long count,
        long totalMs,
        long minMs,
        long maxMs,
        double averageMs
    ) {}

    public record Report(
        long totalLines,
        long validLines,
        long blankLines,
        long invalidLines,
        Map<String, Map<Level, Metric>> groups,
        List<Issue> issueSamples
    ) {}

    public static final class InvalidLogLineException
            extends RuntimeException {
        public InvalidLogLineException(Issue issue) {
            super("Line " + issue.lineNumber() +
                  " is invalid: " + issue.code());
        }
    }

    private record NumberedLine(long number, String text) {}

    private record LogEvent(
        Instant time, Level level, String service, long durationMs
    ) {}

    private sealed interface ParseOutcome
            permits Accepted, Blank, Rejected {}

    private record Accepted(LogEvent event) implements ParseOutcome {}
    private record Blank(long lineNumber) implements ParseOutcome {}
    private record Rejected(Issue issue) implements ParseOutcome {}

    // Pure parser: performs no I/O and mutates no external state.
    private static ParseOutcome parse(NumberedLine line) {
        String raw = line.text();
        if (raw.isBlank()) {
            return new Blank(line.number());
        }

        String[] fields = raw.split("\\|", -1);
        if (fields.length != 4) {
            return new Rejected(
                new Issue(line.number(), "FIELD_COUNT")
            );
        }

        Instant time;
        try {
            time = Instant.parse(fields[0]);
        } catch (DateTimeParseException ex) {
            return new Rejected(
                new Issue(line.number(), "INVALID_TIMESTAMP")
            );
        }

        Level level;
        try {
            level = Level.valueOf(fields[1]);
        } catch (IllegalArgumentException ex) {
            return new Rejected(
                new Issue(line.number(), "INVALID_LEVEL")
            );
        }

        String service = fields[2];
        if (!service.matches("[a-z][a-z0-9-]{0,31}")) {
            return new Rejected(
                new Issue(line.number(), "INVALID_SERVICE")
            );
        }

        long duration;
        try {
            duration = Long.parseLong(fields[3]);
        } catch (NumberFormatException ex) {
            return new Rejected(
                new Issue(line.number(), "INVALID_DURATION")
            );
        }
        if (duration < 0L) {
            return new Rejected(
                new Issue(line.number(), "NEGATIVE_DURATION")
            );
        }

        return new Accepted(
            new LogEvent(time, level, service, duration)
        );
    }

    // Reader remains owned by analyze(), not by the Iterator.
    private static Stream<NumberedLine> numberedLines(
        BufferedReader reader
    ) {
        Iterator<NumberedLine> iterator = new Iterator<>() {
            private long number;
            private NumberedLine nextLine;
            private boolean ready;
            private boolean ended;

            private void load() {
                if (ready || ended) {
                    return;
                }
                try {
                    String text = reader.readLine();
                    if (text == null) {
                        ended = true;
                    } else {
                        number = Math.addExact(number, 1L);
                        nextLine = new NumberedLine(number, text);
                        ready = true;
                    }
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            }

            @Override
            public boolean hasNext() {
                load();
                return ready;
            }

            @Override
            public NumberedLine next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                NumberedLine result = nextLine;
                nextLine = null;
                ready = false;
                return result;
            }
        };

        Spliterator<NumberedLine> source =
            Spliterators.spliteratorUnknownSize(
                iterator,
                Spliterator.ORDERED | Spliterator.NONNULL
            );
        return StreamSupport.stream(source, false);
    }

    // Internal mutable state, never exposed directly to callers.
    private static final class GroupStats {
        long count;
        long sum;
        long min = Long.MAX_VALUE;
        long max = Long.MIN_VALUE;

        void add(long durationMs) {
            count = Math.addExact(count, 1L);
            sum = Math.addExact(sum, durationMs);
            min = Math.min(min, durationMs);
            max = Math.max(max, durationMs);
        }

        void merge(GroupStats other) {
            count = Math.addExact(count, other.count);
            sum = Math.addExact(sum, other.sum);
            if (other.count > 0L) {
                min = Math.min(min, other.min);
                max = Math.max(max, other.max);
            }
        }

        Metric finish() {
            // GroupStats exists only when at least one event was added.
            return new Metric(
                count, sum, min, max, (double) sum / count
            );
        }
    }

    private static final class Accumulator {
        final InvalidLinePolicy policy;
        final int sampleLimit;
        long totalLines;
        long validLines;
        long blankLines;
        long invalidLines;

        final Map<String, EnumMap<Level, GroupStats>> groups =
            new HashMap<>();
        final List<Issue> issueSamples = new ArrayList<>();

        Accumulator(InvalidLinePolicy policy, int sampleLimit) {
            this.policy = policy;
            this.sampleLimit = sampleLimit;
        }

        void accept(ParseOutcome outcome) {
            totalLines = Math.addExact(totalLines, 1L);

            if (outcome instanceof Accepted accepted) {
                validLines = Math.addExact(validLines, 1L);
                LogEvent event = accepted.event();
                groups.computeIfAbsent(
                    event.service(), unused -> new EnumMap<>(Level.class)
                ).computeIfAbsent(
                    event.level(), unused -> new GroupStats()
                ).add(event.durationMs());
            } else if (outcome instanceof Blank) {
                blankLines = Math.addExact(blankLines, 1L);
            } else if (outcome instanceof Rejected rejected) {
                invalidLines = Math.addExact(invalidLines, 1L);
                Issue issue = rejected.issue();

                if (policy == InvalidLinePolicy.FAIL_FAST) {
                    throw new InvalidLogLineException(issue);
                }
                if (policy == InvalidLinePolicy.COLLECT_ERRORS
                        && issueSamples.size() < sampleLimit) {
                    issueSamples.add(issue);
                }
            }
        }

        Accumulator merge(Accumulator other) {
            totalLines = Math.addExact(totalLines, other.totalLines);
            validLines = Math.addExact(validLines, other.validLines);
            blankLines = Math.addExact(blankLines, other.blankLines);
            invalidLines = Math.addExact(invalidLines, other.invalidLines);

            other.groups.forEach((service, levels) -> {
                EnumMap<Level, GroupStats> target =
                    groups.computeIfAbsent(
                        service, unused -> new EnumMap<>(Level.class)
                    );
                levels.forEach((level, stats) -> {
                    target.computeIfAbsent(
                        level, unused -> new GroupStats()
                    ).merge(stats);
                });
            });

            if (policy == InvalidLinePolicy.COLLECT_ERRORS) {
                for (Issue issue : other.issueSamples) {
                    if (issueSamples.size() == sampleLimit) {
                        break;
                    }
                    issueSamples.add(issue);
                }
            }
            return this;
        }

        Report finish() {
            Map<String, Map<Level, Metric>> output = new TreeMap<>();

            groups.forEach((service, levels) -> {
                EnumMap<Level, Metric> finished =
                    new EnumMap<>(Level.class);
                levels.forEach(
                    (level, stats) -> finished.put(level, stats.finish())
                );
                output.put(
                    service, Collections.unmodifiableMap(finished)
                );
            });

            return new Report(
                totalLines,
                validLines,
                blankLines,
                invalidLines,
                Collections.unmodifiableMap(output),
                List.copyOf(issueSamples)
            );
        }
    }

    public static Report analyze(
        Path file, InvalidLinePolicy policy, int sampleLimit
    ) throws IOException {
        Objects.requireNonNull(file, "file");
        Objects.requireNonNull(policy, "policy");
        if (sampleLimit < 0) {
            throw new IllegalArgumentException(
                "sampleLimit must be non-negative"
            );
        }

        try (BufferedReader reader =
                 Files.newBufferedReader(
                     file, StandardCharsets.UTF_8
                 )) {
            return numberedLines(reader)
                .map(LogLineAnalyzer::parse)
                .collect(Collector.of(
                    () -> new Accumulator(policy, sampleLimit),
                    Accumulator::accept,
                    Accumulator::merge,
                    Accumulator::finish
                ));
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println(
                "Usage: java LogLineAnalyzer <file.log>"
            );
            return;
        }

        Path file = Path.of(args[0]);
        Report report = analyze(
            file, InvalidLinePolicy.COLLECT_ERRORS, 10
        );

        System.out.println("Total lines: " + report.totalLines());
        System.out.println("Valid: " + report.validLines());
        System.out.println("Blank: " + report.blankLines());
        System.out.println("Invalid: " + report.invalidLines());
        System.out.println("Sample issues: " + report.issueSamples());
        System.out.println("Groups: " + report.groups());
    }
}
```

### 8.1. Running on the Sample Data

Save the seven opening lines to `app.log` and run:

```bash
javac LogLineAnalyzer.java
java LogLineAnalyzer app.log
```

Expected key counts:

```text
Total lines: 7
Valid: 4
Blank: 1
Invalid: 2
Sample issues: [Issue[lineNumber=5, code=FIELD_COUNT],
                Issue[lineNumber=7, code=NEGATIVE_DURATION]]
```

Grouped metrics:

| Service | Level | Events | Total Duration (ms) | Min (ms) | Max (ms) | Avg (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| api | INFO | 1 | 40 | 40 | 40 | 40.0 |
| api | ERROR | 2 | 200 | 80 | 120 | 100.0 |
| worker | WARN | 1 | 75 | 75 | 75 | 75.0 |

With the internal `HashMap`, iteration order is **unspecified during accumulation**. `finish` copies service keys into a `TreeMap` and levels into an `EnumMap`, so finished reports iterate cleanly in deterministic order; numeric metrics never depend on map iteration order.

### 8.2. Why Does the Main Code Not Use `parallel()`?

The file reader is a sequential iterator over **one `BufferedReader`**. Line numbers advance monotonically, and `readLine()` must run sequentially. `StreamSupport.stream(..., false)` deliberately runs sequentially. Even though the collector has a valid combiner, flipping to `parallel()` will not partition the file cleanly with exact line numbers or necessarily speed up I/O.

To process **multiple independent files**, dispatch **one task per file** and merge reports under an explicit contract while bounding open file handles. For a **single huge file**, byte-range splitting must handle charsets, line boundaries, ordering, and offsets—a custom source design in its own right.

### 8.3. Why Does the Report Keep Memory Small?

`Accumulator` stores only one stats object per (`service`, `level`) pair and at most `sampleLimit` error samples. It **does not buffer log lines**.

With `g` distinct groups and `k` error samples, state scales around `O(g + k)`, not linearly with the **total length of all lines**, assuming groups and sample limits are bounded. `BufferedReader` also uses an internal buffer; an extraordinarily long single line can still demand large memory, so production systems should bound maximum line length.

## 9. Testing Each Policy on the Same File

Suppose `app.log` holds the seven lines from the opening section.

### 9.1. `FAIL_FAST` Mode

```java
try {
    LogLineAnalyzer.Report strict = LogLineAnalyzer.analyze(
        Path.of("app.log"),
        LogLineAnalyzer.InvalidLinePolicy.FAIL_FAST,
        0
    );
    System.out.println(strict);
} catch (LogLineAnalyzer.InvalidLogLineException ex) {
    System.err.println(ex.getMessage());
}
// Line 5 is invalid: FIELD_COUNT
```

`analyze` halts at the first invalid line with **no successful `Report` returned**. `BufferedReader` is still closed by `try-with-resources` inside `analyze`. Later invalid lines are never read—that is the meaning of fail-fast.

### 9.2. `SKIP_WITH_COUNT` Mode

```java
LogLineAnalyzer.Report report = LogLineAnalyzer.analyze(
    Path.of("app.log"),
    LogLineAnalyzer.InvalidLinePolicy.SKIP_WITH_COUNT,
    0
);

System.out.println(report.validLines());       // 4
System.out.println(report.invalidLines());     // 2
System.out.println(report.issueSamples());     // []
```

The report reflects **4 valid events**, not "all 7 lines were valid". If downstream requires at least 99.9% valid non-blank lines, enforce that data-quality gate **after collection** using the counters rather than ignoring the error rate.

### 9.3. `COLLECT_ERRORS` Mode with Sample Limit

```java
LogLineAnalyzer.Report report = LogLineAnalyzer.analyze(
    Path.of("app.log"),
    LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
    1
);

System.out.println(report.invalidLines());     // 2
System.out.println(report.issueSamples().size()); // 1
System.out.println(report.issueSamples().get(0).lineNumber()); // 5
```

Only one error sample is retained, yet both errors are counted. Never use `issueSamples().size()` as the **total error count**: that field measures **stored samples**, not the total count.

### 9.4. Empty File Case

A file with 0 lines produces:

```text
totalLines   = 0
validLines   = 0
blankLines   = 0
invalidLines = 0
groups       = {}
issueSamples = []
```

Never synthesize an `"UNKNOWN"` group or claim average latency is 0 when zero events occurred. Empty `groups` means no valid data existed to form groups.

## 10. Verifying Statistics and Commonly Misunderstood Calculations

### 10.1. `count` Does Not Measure Dropped Data

If `parseOrNull` returns null and you call `filter(Objects::nonNull).count()`, you only know **surviving events**, not how many lines failed. A pure pipeline emits a `ParseOutcome` for **every line** and collects all counts.

### 10.2. Averages Include Only Valid Events

`api/ERROR` in the sample has two durations: 120 and 80 ms.

\[
\text{averageMs}=\frac{120+80}{2}=100.0
\]

Never treat schema errors or blank lines as duration 0; injecting synthetic zeros drags the average down and invalidates the measurement.

### 10.3. Never Take an Unweighted Mean of Group Averages

To compute the overall mean across all events, use:

\[
\overline{d}
=\frac{\sum_{g}\mathrm{totalMs}_{g}}
       {\sum_{g}\mathrm{count}_{g}}
\]

Do not average each group's `Metric.averageMs()` directly when group sizes differ. Sum `count` and `totalMs` across all groups from `Report.groups()` and divide cleanly.

### 10.4. Overflow and Floating-Point Precision

Here `Math.addExact` guards `count` and `sum` against overflow. Yet `(double) sum / count` remains a floating-point approximation; for huge `long` values it can lose low-order precision. If totals can exceed `long` or exact reproducible arithmetic is required, use `BigInteger`/`BigDecimal` with explicit rounding rules.

Because `durationMs` is **non-negative** by schema, when the final sum fits within `long`, merging partial non-negative sums in any order will not overflow intermediate steps; arithmetic must still guard the final total.

## 11. JUnit 5 Tests: Data, Policies, and I/O Errors

These tests use `LogLineAnalyzer` from section 8. Configure JUnit Jupiter in your project and place the test class in the same package.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class LogLineAnalyzerTest {

    @TempDir
    Path temporary;

    private Path sampleFile() throws IOException {
        Path file = temporary.resolve("app.log");
        Files.write(file, List.of(
            "2026-11-18T08:00:00Z|INFO|api|40",
            "2026-11-18T08:00:01Z|ERROR|api|120",
            "",
            "2026-11-18T08:00:02Z|WARN|worker|75",
            "invalid line",
            "2026-11-18T08:00:03Z|ERROR|api|80",
            "2026-11-18T08:00:04Z|INFO|worker|-1"
        ), StandardCharsets.UTF_8);
        return file;
    }

    @Test
    void collectsMetricsAndBoundedErrorExamples() throws IOException {
        var report = LogLineAnalyzer.analyze(
            sampleFile(),
            LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
            1
        );

        assertEquals(7L, report.totalLines());
        assertEquals(4L, report.validLines());
        assertEquals(1L, report.blankLines());
        assertEquals(2L, report.invalidLines());
        assertEquals(report.totalLines(),
            report.validLines() + report.blankLines()
                + report.invalidLines());

        assertEquals(1, report.issueSamples().size());
        assertEquals(5L, report.issueSamples().get(0).lineNumber());
        assertEquals("FIELD_COUNT", report.issueSamples().get(0).code());

        var metric = report.groups()
            .get("api").get(LogLineAnalyzer.Level.ERROR);
        assertEquals(2L, metric.count());
        assertEquals(200L, metric.totalMs());
        assertEquals(80L, metric.minMs());
        assertEquals(120L, metric.maxMs());
        assertEquals(100.0, metric.averageMs(), 1e-9);
    }

    @Test
    void skipPolicyKeepsInvalidCountWithoutSamples() throws IOException {
        var report = LogLineAnalyzer.analyze(
            sampleFile(),
            LogLineAnalyzer.InvalidLinePolicy.SKIP_WITH_COUNT,
            0
        );
        assertEquals(2L, report.invalidLines());
        assertTrue(report.issueSamples().isEmpty());
        assertEquals(4L, report.validLines());
    }

    @Test
    void failFastReportsPhysicalLineNumber() throws IOException {
        var ex = assertThrows(
            LogLineAnalyzer.InvalidLogLineException.class,
            () -> LogLineAnalyzer.analyze(
                sampleFile(),
                LogLineAnalyzer.InvalidLinePolicy.FAIL_FAST,
                0
            )
        );
        assertTrue(ex.getMessage().contains("Line 5"));
        assertTrue(ex.getMessage().contains("FIELD_COUNT"));
    }

    @Test
    void emptyFileCreatesEmptyReport() throws IOException {
        Path file = temporary.resolve("empty.log");
        Files.writeString(file, "", StandardCharsets.UTF_8);

        var report = LogLineAnalyzer.analyze(
            file,
            LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
            20
        );
        assertEquals(0L, report.totalLines());
        assertTrue(report.groups().isEmpty());
        assertTrue(report.issueSamples().isEmpty());
    }

    @Test
    void allBlankLinesAreNotInvalid() throws IOException {
        Path file = temporary.resolve("blank.log");
        Files.write(file, List.of("", "  ", "\t"),
            StandardCharsets.UTF_8);

        var report = LogLineAnalyzer.analyze(
            file,
            LogLineAnalyzer.InvalidLinePolicy.FAIL_FAST,
            0
        );
        assertEquals(3L, report.blankLines());
        assertEquals(0L, report.invalidLines());
        assertTrue(report.groups().isEmpty());
    }

    @Test
    void missingFileDoesNotBecomeEmptyReport() {
        Path missing = temporary.resolve("missing.log");
        assertThrows(NoSuchFileException.class, () ->
            LogLineAnalyzer.analyze(
                missing,
                LogLineAnalyzer.InvalidLinePolicy.SKIP_WITH_COUNT,
                0
            )
        );
    }

    @Test
    void rejectsNegativeSampleLimit() throws IOException {
        assertThrows(IllegalArgumentException.class, () ->
            LogLineAnalyzer.analyze(
                sampleFile(),
                LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
                -1
            )
        );
    }

    @Test
    void resultCollectionsCannotBeMutated() throws IOException {
        var report = LogLineAnalyzer.analyze(
            sampleFile(),
            LogLineAnalyzer.InvalidLinePolicy.COLLECT_ERRORS,
            10
        );

        assertThrows(UnsupportedOperationException.class, () ->
            report.groups().clear()
        );
        assertThrows(UnsupportedOperationException.class, () ->
            report.issueSamples().clear()
        );
        assertFalse(report.groups().get("api").isEmpty());
    }
}
```

**What these tests verify:**

- **valid/blank/invalid** counts preserve the total-line invariant.
- Error samples are bounded while **error counters remain unbounded**.
- `FAIL_FAST` reports the exact first physical failing line without returning a fake successful report.
- Empty files and missing files produce different outcomes.
- Collections inside `Report` cannot be mutated directly by callers.

`NoSuchFileException` covers files absent on open; an I/O read failure occurring **after open** typically surfaces via `UncheckedIOException`. Mid-stream read errors are awkward to simulate with real files; in production projects, inject a mock `Reader` throwing `IOException` at a chosen line to test that path.

## 12. Advanced Testing: Parser and Boundary Cases

Beyond the unit tests above, maintain an independent test matrix for these cases:

| Input | Expected Outcome |
| --- | --- |
| `2026-11-18T08:00:00Z|INFO|api|0` | Valid: duration `0` is allowed |
| `2026-11-18T08:00:00Z|INFO|api|-1` | `NEGATIVE_DURATION` |
| `2026-11-18T08:00:00Z|INFO|api|abc` | `INVALID_DURATION` |
| `2026-11-18T08:00:00Z|DEBUG|api|12` | `INVALID_LEVEL` |
| `not-a-time|INFO|api|12` | `INVALID_TIMESTAMP` |
| `2026-11-18T08:00:00Z|INFO||12` | `INVALID_SERVICE` |
| `2026-11-18T08:00:00Z|INFO|api|` | `INVALID_DURATION` |
| `2026-11-18T08:00:00Z|INFO|api` | `FIELD_COUNT` |
| A line with 5 fields | `FIELD_COUNT` |
| A whitespace-only line | Blank, not Invalid |
| Only invalid lines | `groups` empty; accurate `invalidLines` |
| All events in one group | Single `Metric` with exact count/sum |
| Final line lacking trailing newline | Still read by `BufferedReader.readLine` |
| Sum of durations exceeding `long` | `ArithmeticException` from `Math.addExact` |
| Null path or null policy | `NullPointerException` from input validation |

**Important distinction:** `Long.parseLong` accepts a leading `+` sign; if your schema requires **ASCII digits only**, check a pattern like `[0-9]+` before parsing. This lesson specifies non-negative `long` without explicitly forbidding `+`; do not write tests enforcing rules never stated in the contract.

### 12.1. Data Containing `|` Inside a Field

`split("\\|", -1)` suits only simple delimited formats without escaping or quoting. If a service or log message can contain `|`, fields will split wrong and trigger `FIELD_COUNT`. Never patch around it by concatenating pieces arbitrarily: define an escaped grammar or use a format with a proper parser like JSON Lines.

### 12.2. Unicode and BOM

`StandardCharsets.UTF_8` is explicit, yet some producers prepend a **UTF-8 BOM** at the start of a file. When present, `Instant.parse` on the first line's timestamp can fail. If your system must support BOMs, define and test a policy stripping BOM **only at the start of the file**, rather than calling `strip()` blindly across every log line.

### 12.3. Multiline Stack Traces

Java exceptions often span many lines; lines after the first belong to the stack trace, not new log records. A line-by-line parser flags them as `FIELD_COUNT`. For multiline logs, add a **framing** stage grouping physical lines into one logical event before parsing, while retaining `startLine`/`endLine` bounds for traceability.

## 13. Deciding Report Publishability from Quality Counters

`COLLECT_ERRORS` and `SKIP_WITH_COUNT` let you compute metrics **over valid lines**, yet do not automatically mean those metrics meet publication quality.

Example publication gate:

```java
static boolean acceptable(LogLineAnalyzer.Report r) {
    long nonBlank = r.validLines() + r.invalidLines();
    if (nonBlank == 0L) {
        return false; // No samples yet.
    }
    // Illustrative threshold: at least 99% of non-blank lines are valid.
    return (double) r.validLines() / nonBlank >= 0.99;
}
```

This is an **illustrative rule**, not a universal threshold for every system. Some domains demand **100%**, while others permit small error rates with alerts. If too few valid events exist, even 100% validity may lack statistical sample size; add a minimum sample threshold too.

For huge line counts, `validLines + invalidLines` could overflow `long`; the core program guards counters with `Math.addExact` and is practically bounded by file reading, yet new decision-layer calculations should define numeric ranges and overflow checks as well.

### 13.1. Do Not Define Success as "No Exception Thrown"

In both best-effort modes, `analyze` returns a `Report` normally even when `invalidLines > 0`. Therefore separate:

- **Technical status:** file read completely, no I/O or overflow errors, report produced.
- **Data quality:** do valid ratio, error count, and error codes satisfy policy?
- **Business readiness:** is the report accurate enough for monitoring, alerting, or decisions?

Represent these three conclusions separately in operations.

## 14. Multiple Files: Distinguish Per-File Failures from Per-Line Failures

With 100 log files per day, there are two result levels:

```text
BatchReport
  ├── app-01.log -> Report (success, invalidLines = 2)
  ├── app-02.log -> Report (success, invalidLines = 0)
  ├── app-03.log -> FileFailure(IOException)
  └── ...
```

**Line-error policy** governs processing **inside a single file**. **File-error policy** decides whether to continue when a file cannot be opened or read. Never conflate them by catching `IOException` and returning `new Report(0, 0, ...)`.

Skeleton modeling file-level outcomes:

```java
sealed interface FileResult permits FileSuccess, FileFailure {}

record FileSuccess(
    Path path, LogLineAnalyzer.Report report
) implements FileResult {}

record FileFailure(
    Path path, String errorCode, String message
) implements FileResult {}
```

If the system uses **continue-on-file-error**, store path, error code, and sanitized message; the batch summary must show both succeeded and failed file counts. Under **fail-batch-fast**, an error in one file halts the batch and closes all open resources.

### 14.1. `Files.list`, `flatMap`, and Child Resources

When listing paths:

```java
try (Stream<Path> paths = Files.list(directory)) {
    List<Path> selected = paths
        .filter(path -> path.getFileName().toString()
            .endsWith(".log"))
        .toList();
}
```

`Files.list` holds an OS directory handle that must be closed. After collecting the `Path` list, analyze each file with `analyze` and the desired policy. If you use `flatMap` to open `Files.lines` per file, verify child-stream closing contracts carefully; the directory stream still belongs to the caller.

**Never** rely on `Files.list` iteration order as "first file" without sorting by a criterion; order affects both fail-fast stopping and which error samples get recorded first.

## 15. Laziness, Short-Circuiting, and Logs Mutating Mid-Read

### 15.1. Why Not Put `limit` and Call It a Full-File Report?

`limit(1000)` analyzes **at most the first 1,000 lines**, not the entire file. That can be a valid **sampling** mode, provided the output is explicitly labeled as a sample:

```java
try (Stream<String> lines = Files.lines(path)) {
    long firstThousand = lines
        .limit(1_000)
        .filter(line -> !line.isBlank())
        .count();
}
```

Never treat this count as the full file's event count. `findFirst` also short-circuits early, leaving later lines unchecked, so it cannot prove "the file has no errors".

### 15.2. Do Not Rely on `peek` or Mapper Invocation Counts for Audit Logs

Intermediate Stream operations are lazy and subject to short-circuiting. Valid optimizations can even elide intermediate calls that do not affect the terminal result. Avoid placing mandatory side effects (incrementing business counters, writing audit records, opening unclosed handles) inside `peek` or mappers.

In our main program, the parser produces `ParseOutcome` and the **collector records all counts**, avoiding shared external counters.

### 15.3. Files Being Appended, Rotated, or Truncated

For actively written logs, never assume the file is an immutable snapshot:

- Writers may append lines while the reader scans.
- Log rotation may rename or replace the file.
- A half-written line may lack trailing fields when read.
- File size and total line count can shift mid-pass.

**Analyzing closed/archived files** is a different problem from **real-time log tailing**. For reproducible reports, process closed snapshots; for live tailing, design reader lifecycles, retries, checkpoints, and partial-line handling explicitly.

### 15.4. Never Convert I/O Errors into `Invalid` Lines

An I/O failure between `readLine` calls must not become `Rejected("IO_ERROR")` as though it were a schema error on one line. The reader failed to deliver the line, and the remaining line count is unknown. Continuing after read failures requires retry/reopen logic and separate consistency semantics outside this lesson's three line policies.

## 16. Performance, Memory, and Security in Production Systems

### 16.1. Balancing Throughput and Diagnostics

| Design | Benefit | Cost / Risk |
| --- | --- | --- |
| `Files.readAllLines` | Simple for small files | Memory grows with entire file size |
| `Files.lines` | Lazy reading, Stream-friendly | No built-in line numbers; must close stream |
| `BufferedReader.readLine` + iterator | Preserves line numbers, controls I/O | Must implement lookahead and ownership cleanly |
| Unbounded `COLLECT_ERRORS` | Full diagnostics | Can retain too many errors in RAM |
| Bounded `COLLECT_ERRORS` | Capped error memory | Does not store every error location |
| `summarizingLong` per group | Built-in count/sum/min/max/avg | `long` sum does not detect overflow automatically |
| Accumulator with `Math.addExact` | Catches overflow | Extra code and check overhead |

`String.split` and `String.matches` are simple and sufficient here; for high-throughput logs, consider zero-regex tokenizers and precompiled `Pattern`s. Optimize only after schema and correctness are verified, backed by benchmarks on your target JDK and workload.

### 16.2. Single-Line Size and Group Cardinality

The pipeline avoids buffering the whole file, yet **one gigantic line** still requires memory to hold its string. Likewise, millions of distinct `service` values create `O(g)` group state. Production systems need caps on line length, field length, group count, processing time, and rejection policies for threshold breaches.

Never encode "missing data" as negative `durationMs`: our schema already marks negatives as errors. If failed measurements must be represented, add an explicit state rather than overloading numeric fields with sentinels.

### 16.3. Logs Can Contain Secrets

Even storing only `Issue(lineNumber, code)`, raw log files may contain access tokens, cookies, emails, or IDs. Never print full failing lines in `catch`, never forward raw system exception messages straight to public APIs, and never push sensitive payloads to dashboards without redaction policies.

For investigation, pair file paths and line numbers with access-controlled file inspection. Sample logs in this lesson contain purely synthetic data.

### 16.4. Resource Limits and Cancellation

`try-with-resources` protects the reader even if parsers, accumulators, or downstream stages throw. It does not, however, enforce timeouts on network sources or prevent a single huge line from exhausting memory. For non-local sources, add timeouts, cancellation, and buffer caps at the I/O layer.

## 17. Anti-Patterns to Avoid

| Anti-Pattern | What Goes Wrong | Solution |
| --- | --- | --- |
| `Files.lines(path).collect(...)` without closing | Leaks OS I/O resources | `try-with-resources` |
| Parser returning `null` for all failures | Loses reason and error counts | Explicit `ParseOutcome` |
| `catch (Exception) { return Stream.empty(); }` | Swallows read errors / produces partial reports silently | Separate schema errors from I/O errors |
| `filter(Objects::nonNull)` right after parser | Discards error counts | Count outcome types before filtering |
| `AtomicLong.incrementAndGet()` in parallel mapper for line numbers | Line numbers depend on thread scheduling | Sequential `NumberedLine` source or dedicated Spliterator |
| Using `issueSamples.size()` as total errors | Wrong once sample limit caps storage | Use `invalidLines` |
| Treating duration `0` as "no samples" | Confused with valid 0-ms events | Track `count` |
| Unweighted mean of group averages | Wrong when group event counts differ | Combine sums and counts |
| `readAllLines` regardless of file size | Risks out-of-memory errors | Lazy reads, compact accumulation |
| Using `limit` yet labeling report as full-file | Skips unread lines | Label report as a sample or remove limit |
| Blindly adding `parallel()` on one reader | Reader cursor is sequential; overhead and risk | Benchmark and design a splittable source |
| Assuming `LongSummaryStatistics` always catches overflow | Sum can wrap silently | Use `Math.addExact` or arbitrary-precision math |
| Storing raw failing lines in dashboards | Risks leaking sensitive data | Store error codes, line numbers, and redacted previews if needed |
| Assuming files never mutate mid-read | Log rotation or partial writes | Closed snapshots or real-time streaming design |

## 18. Practice Exercises

### Exercise 1 — Choosing a Policy

Using the 7-line log from section 1, run `FAIL_FAST`, `SKIP_WITH_COUNT`, and `COLLECT_ERRORS` with `sampleLimit = 1`. Build a table showing valid, blank, invalid lines, and stored sample errors. Explain why `FAIL_FAST` yields no success report whereas both best-effort modes must surface dropped-line counts.

### Exercise 2 — Adding a New Error Code

Change the `durationMs` schema to strictly positive integers **greater than 0**. Update the parser so duration `0` returns `ZERO_DURATION` instead of valid. Write tests for `0`, negative numbers, blank strings, and non-numeric strings. Describe the impact of this schema change on historical metrics.

### Exercise 3 — Computing Error Rate per Service

From `Report.groups()`, compute for each service:

\[
\text{errorRate}=\frac{\text{ERROR count}}
{\text{INFO count}+\text{WARN count}+\text{ERROR count}}
\]

If a service has zero valid events, do not fabricate `0`—represent "no data". Cross-check `api` on the sample file: 2 ERRORs out of 3 total events.

### Exercise 4 — Top Services by Total Duration

Produce a list of services sorted by total `totalMs` descending, breaking ties by service name ascending. Do not depend on `HashMap` iteration order. Explain the difference between aggregating by `service` vs. `service + level`.

### Exercise 5 — Sample Cap at Scale

Generate 10,000 invalid lines and run `COLLECT_ERRORS` with `sampleLimit = 10`. Verify `invalidLines == 10_000`, the sample list holds only 10 items, and `totalLines` stays exact. Assess memory impact if the sample cap were raised to 10,000.

### Exercise 6 — Simulated I/O Failure Source

Build a test `Reader`/`BufferedReader` throwing `IOException` after three lines. Refactor the analysis method to accept an injected reader in tests. Prove that this failure **never becomes `Rejected`**, and the reader is still closed on failure.

### Exercise 7 — Multi-File Reporting

Given three files `app-1.log`, `app-2.log`, and one missing file. Design a result model with `FileSuccess` and `FileFailure`. Choose either **fail-batch-fast** or **continue-on-file-error** and explain how per-file line-error policies remain independent.

### Exercise 8 — Multiline Logs

Define a rule treating lines starting with whitespace as stack-trace continuations of the previous event. Sketch a **framing state machine** combining physical lines into one logical event, detailing how to report `startLine`/`endLine` and handle EOF mid-event.

### Exercise 9 — Arithmetic and Precision

Add two valid lines with durations `Long.MAX_VALUE` and `1` in the same group. Prove `Math.addExact` throws when the sum overflows. Write a `BigInteger` alternative if business rules truly permit such huge values; never wrap silently into negative numbers.

## 19. Production Log-Pipeline Checklist

- [ ] Log format and charset are explicitly specified.
- [ ] Definitions of **blank**, **invalid**, and **valid** lines are clear.
- [ ] Every physical line carries a clear line number.
- [ ] The parser catches only expected data errors, never swallowing all exceptions.
- [ ] `FAIL_FAST` / `SKIP_WITH_COUNT` / `COLLECT_ERRORS` policy is chosen explicitly.
- [ ] `totalLines`, `validLines`, `blankLines`, and `invalidLines` are all tracked for reconciliation.
- [ ] Error sample limits **never** cap the total invalid-line counter.
- [ ] I/O failures are never misreported as "empty data".
- [ ] `BufferedReader` or `Files.lines` is closed by its proper owner.
- [ ] Line numbering never relies on shared mutable mapper state in parallel execution.
- [ ] Whole files are not buffered in RAM when only summary stats are needed.
- [ ] Averages on zero-sample groups are never reported as real measurements.
- [ ] Overflow, `double` precision, and negative durations are controlled.
- [ ] Tested on empty files, missing files, invalid lines, blank lines, read failures, and grouped totals.
- [ ] Sensitive raw log lines are never written to diagnostics without redaction.
- [ ] Policies exist for active/rotating files and multi-file batches if required.

## 20. Decision Table and Summary

| Requirement | Recommended Choice |
| --- | --- |
| Streaming line reads | `Files.lines(path, UTF_8)` inside `try-with-resources` |
| Accurate, verifiable physical line numbers | Sequential `BufferedReader.readLine` + `Iterator<NumberedLine>` |
| Distinguishing parse failures from blank lines | `ParseOutcome` with `Accepted`, `Blank`, `Rejected` |
| One bad line must abort the whole report | `FAIL_FAST` |
| Dropping bad lines allowed with quality tracking | `SKIP_WITH_COUNT` |
| Need bounded diagnostic samples | `COLLECT_ERRORS` with `sampleLimit` |
| Full line counts and multi-key stats | One collector holding counters and `service → level → Metric` |
| Simple stats on already clean data | `groupingBy` + `counting`/`summarizingLong` |
| Source cannot be opened/read | Surface I/O failure, never an empty report |
| Exact sums exceeding `long` | `BigInteger`/`BigDecimal` per domain rules |
| Multi-file analysis | Separate **file-level** error policy and close each source |
| Real-time streaming metrics | Dedicated tailing, checkpointing, retry, and partial-line design |

**Line-by-line log analysis with explicit error policies** is far more than `Files.lines(...).filter(...).count()`. What matters most is **honoring the data contract**: accounting for valid, blank, and invalid lines; separating parser errors from I/O errors; returning verifiable numbers; closing resources properly; and bounding diagnostic memory. Once those guarantees are in place, the Java Stream API lets you express `map`, `filter`, `collect`, grouped metrics, and downstream reporting cleanly, safely, and extensibly.

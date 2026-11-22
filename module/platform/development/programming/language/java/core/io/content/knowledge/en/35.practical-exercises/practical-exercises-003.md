# Reading Large Files Line by Line and Aggregating Data Statistics in Java

When processing logs, transaction data, measurement results, or a CSV file ranging from hundreds of MB to many GB, calling `Files.readAllLines(path)` and then iterating over the list can create massive heap pressure: each line is a string, plus there is the list of references, intermediate objects, and decoding overhead. Most statistical problems **do not need to keep all lines in memory**. They only need to read one line at a time, validate the record, and update a few counters, sums, min/max values, or per-group statistics.

This exercise walks through reading a large file line by line with `BufferedReader` and `Files.lines()`, designing **streaming / one-pass** aggregation, and handling malformed lines, encoding, numeric overflow, resources, and performance. A complete Java 17 program will read data in the `level,durationMs` format, count valid/invalid records, per-log-level counts, total, min, max, and average without creating a list of all lines.

**Goal:** Memory cost mainly depends on the size of the **largest line** and the amount of statistical state retained, rather than scaling linearly with total line count when only fixed counters and groups are stored.

## 1. Distinguishing Whole-File Reading from Line-by-Line Reading

| Reading Approach | Behavior | Best For |
| --- | --- | --- |
| `Files.readString(path)` | Reads file content into a single `String` | Small files where the entire content is needed in RAM |
| `Files.readAllLines(path, charset)` | Reads all lines and builds a `List<String>` | Small/medium files when every line must be revisited |
| `Files.newBufferedReader(path, charset)` | Reads sequentially via `BufferedReader.readLine()` | Large files, line-by-line processing, flow and error control |
| `Files.lines(path, charset)` | Returns a lazy `Stream<String>`, read when a terminal operation runs | Filter/map pipelines; the stream must still be closed |
| `FileChannel.read(ByteBuffer)` | Reads byte blocks, **does not split lines or decode charsets automatically** | Binary protocols, custom parsers, or when byte-buffer control is needed |

For large text files, `BufferedReader` is a solid starting point: easy to manage lines, handle checked `IOException`, and control lifecycle. `Files.lines()` is appropriate when the pipeline is clear and you do not accidentally collect every line into memory with `collect(toList())`.

Large file size **does not automatically mean** you must use `MappedByteBuffer` or write a custom byte decoder: streaming text through `BufferedReader` is usually sufficient, maintainable, and easy to benchmark.

## 2. Input Dataset and Statistical Requirements

Suppose each data line is a record with two comma-separated columns:

```text
level,durationMs
INFO,120
WARN,300
ERROR,450
INFO,80
WARN,200
broken
INFO,-1
ERROR,150
```

Business rules for this exercise:

1. The first line **must be exactly** `level,durationMs`, which is the header and is not included in statistics.
2. Each subsequent line must have exactly one comma and two non-empty fields.
3. `level` must be one of `INFO`, `WARN`, or `ERROR`; matched case-sensitively after trimming leading/trailing whitespace on each field.
4. `durationMs` must be a **non-negative** `long` integer.
5. Invalid lines are **counted in `invalid`** and skipped when computing sum/min/max/average. Do not reject the entire file because of one dirty line.
6. Metrics to print: total data lines, valid, invalid, line count per level, total duration, min, max, average.
7. The file can be very large; the program does not store a `List<String>`, does not retain all valid records, and does not need to create intermediate files.

With the sample data: there are **8 data lines**, 6 valid lines, and 2 invalid lines (`broken` and `INFO,-1`). Each level has 2 valid lines; total duration is **1300 ms**, min **80 ms**, max **450 ms**, and average **1300 / 6 = 216.67 ms**.

This is a **simple CSV format defined by this exercise**, **not a general RFC 4180 CSV parser**: it does not support commas inside quoted fields, newlines inside fields, or escaping rules. When processing real-world CSVs with quoted fields, use a dedicated CSV parser or implement a resource-bounded state machine instead of blindly calling `split(",")`.

## 3. `BufferedReader.readLine()`: Reading Lines Without Loading the Whole File

Basic pattern:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("events.csv");

try (BufferedReader reader =
        Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each line immediately, updating the accumulators.
    }
}
```

This is an **illustrative snippet**: the input file must exist and the application must handle `IOException`; the code does not include a `main` method. Key points:

- `readLine()` returns a string containing the line content, **excluding line-termination characters**; or `null` at end of file.
- Common line endings such as LF (`\n`), CRLF (`\r\n`), and CR are recognized as line terminators per the `BufferedReader` contract.
- **An empty line is `""`, not `null`.** If the data contains empty lines, decide whether to skip them, count them as errors, or treat them as blank records.
- `readLine()` can throw `IOException`, for example on device errors or invalid input decoding.
- `try-with-resources` closes the reader even if the processing loop stops due to an error. It also closes the underlying stream created by `Files.newBufferedReader()`.

**Distinguish "not loading the whole file" from "an absolute RAM cap".** `readLine()` must construct a string for **an entire line**. If a file contains **a single GB-long line** with no newline, the program still risks running out of memory. Line-by-line reading is memory-safe **when individual line length is bounded**; for untrusted input, use a parser that limits character/byte count before building an overly long string.

### Character Encoding and Charset

Specify the charset explicitly:

```java
Files.newBufferedReader(path, StandardCharsets.UTF_8);
```

Do not rely on the default charset when files are shared across machines. A real file may use UTF-8, UTF-16, or another encoding; **specify the source's exact encoding**. A `UTF-8 BOM` at the start of a file may appear in the read content as the `\uFEFF` character, causing a header check with `equals()` to fail. If your convention accepts BOMs, handle it explicitly right at the **start of the file**, rather than stripping the first character from every line.

## 4. One-Pass Aggregation: Keeping Small State and Updating Incrementally

Instead of:

```java
List<String> lines = Files.readAllLines(path);
long valid = lines.stream().filter(...).count();
```

(this snippet only illustrates an anti-pattern; `...` is not runnable Java code), maintain accumulators:

```text
rows           = 0      // Total lines after the header
valid          = 0      // Number of accepted lines
invalid        = 0      // Number of rejected lines
sumDurationMs  = 0      // Total valid duration
minDurationMs  = +∞     // Min of valid lines
maxDurationMs  = -∞     // Max of valid lines
count[INFO]    = 0
count[WARN]    = 0
count[ERROR]   = 0
```

For each line:

1. Increment `rows`.
2. Validate column count, level, and duration.
3. If invalid: increment `invalid`, move to the next line.
4. If valid: increment `valid`, increment the level counter, add duration to the sum, update min/max.
5. At EOF: compute the average if `valid > 0`; if there are no valid lines, use `n/a` to avoid division by zero.

**There is no need to know the total line count or file size in advance** to compute these statistics. With three fixed levels, the number of counters is also fixed. Time cost roughly corresponds to the total characters/bytes read plus parsing overhead, while memory is not a `List` growing with file size.

### Overflow and Precision

Do not use `int` for total duration when a file may contain millions of records. Use `long`, and if the sum could exceed `Long.MAX_VALUE`, check with `Math.addExact()` (throws `ArithmeticException` on overflow) or use `BigInteger` if business logic truly requires a larger range.

For the average:

```java
double average = valid == 0 ? Double.NaN
        : (double) sumDurationMs / valid;
```

This is an illustrative formula; variables must be declared in the application context. `double` is suitable for reporting averages; for monetary values or business requirements needing exact decimal precision, use `BigDecimal` with an explicit rounding policy. Do not accumulate `long` values into an `int` and expect the final division to fix an overflow that already occurred.

## 5. Complete Java 17 Program: One-Pass Large File Statistics

Create the file **`LargeFileStatsDemo.java`**. If run **with no arguments**, the program generates sample data in a temporary file, analyzes it, and deletes the sample file. If passed **one path**, the program reads that file and **does not modify or delete the user-specified file**.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class LargeFileStatsDemo {
    private LargeFileStatsDemo() {}

    private enum Level { INFO, WARN, ERROR }

    private static final class Stats {
        long rows;
        long valid;
        long invalid;
        long sumMs;
        long minMs = Long.MAX_VALUE;
        long maxMs = Long.MIN_VALUE;
        final long[] byLevel = new long[Level.values().length];

        void accept(Level level, long durationMs, long lineNumber)
                throws IOException {
            try {
                sumMs = Math.addExact(sumMs, durationMs);
                valid = Math.incrementExact(valid);
                byLevel[level.ordinal()] =
                        Math.incrementExact(byLevel[level.ordinal()]);
            } catch (ArithmeticException overflow) {
                throw new IOException(
                        "Statistics overflow at line " + lineNumber,
                        overflow);
            }
            minMs = Math.min(minMs, durationMs);
            maxMs = Math.max(maxMs, durationMs);
        }

        void print() {
            System.out.println("rows=" + rows);
            System.out.println("valid=" + valid);
            System.out.println("invalid=" + invalid);
            for (Level level : Level.values()) {
                System.out.println(level + "=" + byLevel[level.ordinal()]);
            }
            System.out.println("totalMs=" + sumMs);
            if (valid == 0) {
                System.out.println("minMs=n/a");
                System.out.println("maxMs=n/a");
                System.out.println("avgMs=n/a");
            } else {
                System.out.println("minMs=" + minMs);
                System.out.println("maxMs=" + maxMs);
                System.out.printf(Locale.ROOT, "avgMs=%.2f%n",
                        (double) sumMs / valid);
            }
        }
    }

    public static void main(String[] args) throws IOException {
        if (args.length > 1) {
            System.err.println("Usage: java LargeFileStatsDemo [file.csv]");
            return;
        }

        if (args.length == 1) {
            analyze(Path.of(args[0])).print();
            return;
        }

        Path example = Files.createTempFile("large-file-stats-", ".csv");
        try {
            String sample = String.join("\n",
                    "level,durationMs",
                    "INFO,120",
                    "WARN,300",
                    "ERROR,450",
                    "INFO,80",
                    "WARN,200",
                    "broken",
                    "INFO,-1",
                    "ERROR,150") + "\n";

            // Only overwrite the temporary file just created by this program.
            Files.writeString(example, sample, StandardCharsets.UTF_8);
            analyze(example).print();
        } finally {
            Files.deleteIfExists(example);
        }
    }

    private static Stats analyze(Path file) throws IOException {
        Stats stats = new Stats();

        try (BufferedReader reader =
                Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String header = reader.readLine();
            if (!"level,durationMs".equals(header)) {
                throw new IOException("Missing or invalid CSV header");
            }

            String line;
            long lineNumber = 1;
            while ((line = reader.readLine()) != null) {
                lineNumber++;
                stats.rows++;

                int comma = line.indexOf(',');
                if (comma <= 0
                        || comma == line.length() - 1
                        || line.indexOf(',', comma + 1) >= 0) {
                    stats.invalid++;
                    continue;
                }

                Level level;
                long duration;
                try {
                    level = Level.valueOf(
                            line.substring(0, comma).trim());
                    duration = Long.parseLong(
                            line.substring(comma + 1).trim());
                } catch (IllegalArgumentException invalidRow) {
                    stats.invalid++;
                    continue;
                }

                if (duration < 0) {
                    stats.invalid++;
                    continue;
                }

                stats.accept(level, duration, lineNumber);
            }
        }

        return stats;
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac LargeFileStatsDemo.java
java LargeFileStatsDemo
```

**Exact stdout for the built-in sample data:**

```text
rows=8
valid=6
invalid=2
INFO=2
WARN=2
ERROR=2
totalMs=1300
minMs=80
maxMs=450
avgMs=216.67
```

To read your own file:

```bash
java LargeFileStatsDemo /path/to/events.csv
```

This is only a Unix-style path syntax example; replace it with a real path appropriate for your operating system. The file must follow the `level,durationMs` format described above; output will reflect the data of the passed-in file.

### Analyzing How the Example Works

- `Files.newBufferedReader()` only holds a read buffer and the string of the current line, instead of a list of all lines.
- The header is checked upfront to avoid mistaking columns or aggregating a completely malformed file.
- `line.indexOf(',')` locates the single comma and verifies there is no second comma; suited for a **simple two-column format**, without quoted CSV.
- `Level.valueOf()` validates the level; `Long.parseLong()` validates the duration; both can throw `IllegalArgumentException` (including `NumberFormatException` as a subclass) and are recorded as invalid lines.
- `stats.accept()` only runs for valid records; `Math.addExact()` prevents the sum from silently overflowing `long`.
- `minMs/maxMs` are initialized with sentinels, but **sentinels are not printed if valid=0**.
- `Locale.ROOT` keeps the `.` decimal separator in the sample output, avoiding dependence on the machine's regional locale settings.
- The argument branch only **reads** the user's file, while the no-argument branch only creates and deletes a **temporary file owned by the program**.

The exercise intentionally counts bad lines without printing the full line content, because large files can bloat error logs or leak data. In a real service, you can emit **a bounded number of diagnostics**, such as at most the first 10 errors, with line number and reason, without exposing sensitive fields.

## 6. `Files.lines()`: Same Goal Using the Stream API

`Files.lines(path, StandardCharsets.UTF_8)` returns a lazily read `Stream<String>`. A simple example counting lines containing a keyword:

```java
// Illustrative snippet inside a method that allows throwing IOException.
try (java.util.stream.Stream<String> lines =
        Files.lines(file, StandardCharsets.UTF_8)) {
    long errors = lines.filter(s -> s.startsWith("ERROR,")).count();
    System.out.println(errors);
}
```

This is an **illustrative snippet**, not a standalone program: `file` must be a valid `Path`, with `Files` imported and exceptions handled. `Files.lines()` does not need to build a list before `count()`. It reads and checks lines as the terminal operation executes.

**Closing the stream is mandatory.** The stream returned by `Files.lines()` is tied to an open file resource; do not return it out of a `try-with-resources` block and let the caller consume it after the file has been closed.

During stream execution, an I/O error arising after the stream is created can be wrapped into an `UncheckedIOException` by the pipeline. This differs from `BufferedReader.readLine()`, which declares checked `IOException`. Choose an appropriate error-handling strategy and do not swallow exceptions in terminal operations.

### Do Not Turn Streaming into Eager Collection

An anti-pattern:

```java
try (var lines = Files.lines(path)) {
    var all = lines.toList();
    // all now holds every line in RAM!
}
```

This snippet is **illustrative**, requiring a `Path` variable `path` and `IOException` handling. `Files.lines()` is only lazy **until** you use a terminal operation. `toList()`, `collect(toList())`, or `groupingBy(..., toList())` can accumulate massive amounts of data, forfeiting the memory advantage.

You can use a collector to count groups:

```java
// Illustrative snippet: only suitable after validating line data.
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    var counts = lines
            .filter(s -> !s.isBlank())
            .collect(java.util.stream.Collectors.groupingBy(
                    s -> s.substring(0, s.indexOf(',')),
                    java.util.stream.Collectors.counting()));
}
```

However, **this code is unsafe for input missing a comma**, and the header will be counted unless skipped. It only illustrates collectors and **does not replace complete, validated code**. Moreover, the memory of `groupingBy()` grows with the number of distinct groups. If every line has a unique key, the map can grow close to the total line count; in that case, you need cardinality limits or external aggregation.

## 7. Designing Per-Group Statistics for Large Files

This exercise's fixed three-level counters keep memory O(1) relative to line count. Real data often requires grouping by date, region, or status code:

| Problem | Minimum State | Memory |
| --- | --- | --- |
| Count total lines and invalid lines | A few `long` counters | Near O(1) |
| Sum, min, max, average | `sum, count, min, max` | Near O(1) |
| Count by level with 3 values | Three-element array / `EnumMap` | Near O(1) |
| Count by HTTP status code with finite domain | Array or map bounded by code count | Proportional to codes that may appear |
| Count by unbounded user ID | `Map<userId, count>` | Proportional to distinct user IDs, potentially very large |
| Compute exact distinct value count | `HashSet` | Proportional to distinct values |
| Top-K with fixed size K | Min-heap and appropriate counters | Usually O(K) for top-K selection once frequencies exist, though exact per-key frequency counting still needs other state |
| Exact median/p95 | Usually requires data or suitable index/algorithm structure | Not always O(1) |
| Approximate median/p95 | Suitable sketch/histogram | Can bound memory at the cost of error margin |

Do not claim "line-by-line reading ⇒ every statistic is O(1) memory". What is true is that **the reading mechanism itself does not store the entire file**; aggregation can still retain lots of data depending on requirements. If cardinality is high, consider bucketing by key, external sort, a database, or chunked data processing tools.

### Retaining Enough Information to Compute Averages Correctly

To aggregate averages across multiple files, do not directly store and average each file's average, because files have different valid line counts. Store **`sum` and `count`**, then combine:

```text
File A: sum=100, count=1      --> avg=100
File B: sum=300, count=3      --> avg=100
Combined: (100+300)/(1+3)    --> avg=100
```

Another case clearly exposes the "average of averages" bug:

```text
File A: sum=100, count=1       --> avg=100
File B: sum=0, count=9         --> avg=0
Incorrect: (100+0)/2          --> 50
Correct:   (100+0)/(1+9)      --> 10
```

When merging across machines, define overflow handling, combination order, and invalid-line policies before aggregating.

## 8. I/O Optimization: Buffer, Allocations, and Charset Decoder

`Files.newBufferedReader()` uses a buffered character reader suitable for many cases. If a specific buffer size is needed, you can combine:

```java
// Illustrative snippet, file is a valid Path; IOException is handled by the caller.
try (BufferedReader reader = new BufferedReader(
        new java.io.InputStreamReader(
                Files.newInputStream(file), StandardCharsets.UTF_8),
        64 * 1024)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Aggregate directly.
    }
}
```

Do not assume increasing the buffer from 8 KiB to 64 KiB is always faster. Results depend on line length, disk, page cache, charset decoding, file count, and parsing cost.

Several optimization choices require controlled benchmarking:

1. **Minimize unnecessary object creation.** `String.split(regex)` allocates an array and multiple strings; if the format has only one delimiter, `indexOf()` and `substring()` can be simpler. However, never trade away correctness on complex CSVs for speed.
2. **Count with `long` instead of `int`** for very large files.
3. **Separate I/O from parsing in benchmarks.** Measuring raw reads differs from measuring read + validation logic + record allocation + aggregation.
4. **Warm up JVM/JIT and file cache fairly.** A second run may be faster due to the OS page cache even with the same API; do not compare a cold run against a warm run and conclude one algorithm is better.
5. **Do not build a giant `StringBuilder` for all lines** just to compute a few metrics.
6. **Do not blindly parallelize `Files.lines()`**: line splitting, ordering, shared resources, and mutable accumulators can complicate code without speeding it up.
7. **Avoid logging on every line** when processing hundreds of millions of lines; stdout/logging itself can be slower than read I/O.
8. **Pick the right charset** and handle encoding errors; speed does not matter if data is parsed wrongly.

You can benchmark pure CPU/parsing steps with JMH, but **JMH does not automatically control the operating system cache**. To evaluate end-to-end throughput, also measure file open, read, decode, parse, GC, and resource close times across your application's real scope.

## 9. Handling Dirty Data and Safety Limits

Large files are rarely completely clean. A **skip, fail-fast, or quarantine** policy should be agreed upon before running:

| Situation | Suggested Handling |
| --- | --- |
| Invalid header or empty file | Fail-fast, as you may be reading the wrong kind of data |
| Line with wrong column count | Count invalid, log a bounded number of diagnostics |
| Unknown level | Count invalid or map to OTHER if business logic allows |
| Non-integer duration | Count invalid or fail-fast depending on requirements |
| Negative duration | Reject if the valid domain requires non-negative values |
| Duration value causing sum overflow | Stop with a clear error or use `BigInteger` |
| File with wrong charset | Report decode error; do not auto-switch encoding and continue without rules |
| Extremely long line | Enforce character/byte limit inside the parser before allocating too much memory |
| File modified while reading | Results may not reflect a consistent snapshot |
| Disk/network filesystem error | `IOException`; do not report completion with partial stats without a checkpoint |

If statistics serve sensitive domains (finance, auditing), also store the parse policy, schema version, input file checksum, and error-handling behavior so results remain traceable. Do not automatically discard bad lines and publish statistics as if all data had been processed.

### Do Not Accept Unbounded Lines Just Because You Stream

`BufferedReader.readLine()` does not provide a "maximum line length" parameter. If input comes from an untrusted third party, the limiter must run **while consuming characters/bytes**, not just:

```java
String line = reader.readLine();
if (line.length() > 10000) { ... }
```

because by the time the check runs, `readLine()` **has already constructed a very long string**. A safer bounded parser can read in chunks/characters, stop/flag when the threshold is exceeded, and continue discarding the remainder up to the newline without accumulating it. If proper standard CSV is needed, choose a parser library capable of bounding record/field lengths.

## 10. Handling Multi-GB, Multi-Day, or Multi-Source Files

For **one large file**, one-pass streaming is usually enough. For **multiple files**, you can loop over each file, close `BufferedReader` after each one, and merge statistics into a total accumulator using overflow-checked addition. There is no need to open thousands of file descriptors concurrently.

For continuously updated files like a live log, a single pass may hit EOF before the log writer writes more. **Reading a file to EOF is different from tailing a file (`tail -f`).** If the application needs to receive new data in real time, use a designed polling, rotation handling, or watcher mechanism rather than spinning `readLine()` in an infinite busy-wait loop.

When a file is being written concurrently, you do not automatically get a consistent snapshot. Options include:

- Process only files that the producer has **fully closed** and published via an appropriate rename.
- Create a snapshot/immutable input with an explicit checksum or version.
- If a live file must be read, define when an incomplete line without a trailing newline is considered complete, and handle log rotation and retries.
- To read different parts of the same file in parallel, find **actual line boundaries** at split points; splitting purely by byte offset and letting workers read arbitrarily risks undercounting or duplicating lines.

**Note:** Java's `BufferedReader.readLine()` can return the last line even if the file does not end with a newline. For an immutable file, this is a valid line under text-reading rules; for a file actively being written, it may be an **incomplete record**. Define a publish/snapshot protocol instead of guessing.

## 11. Testing Statistics Before Using on Real Data

Cases to include:

1. **Header-only file:** `rows=0`, `valid=0`, `invalid=0`, min/max/average are `n/a`.
2. **Empty file:** Reports header error, not accepted as a valid dataset.
3. **Malformed lines:** Missing comma, extra comma, single column only, unknown level, non-numeric duration.
4. **Blank lines:** Under the example policy, blank lines are `invalid`.
5. **Negative duration:** Rejected, does not affect `sum` or average.
6. **Zero duration:** Valid, affects `count` and can affect `minMs`.
7. **Large durations:** Test `long` parsing and handling sums exceeding `Long.MAX_VALUE`.
8. **UTF-8/BOM:** Check encoding and BOM policy on real files.
9. **CRLF/LF:** Ensure line counting does not depend on newline style.
10. **No trailing newline at EOF:** The last line is still read.
11. **Very large file:** Monitor heap/GC, avoiding memory growth with line count.
12. **File modified mid-pass:** Ensure there is a snapshot/retry policy or clearly note results are not a snapshot.
13. **Mid-read error:** Do not output a "success" report when `IOException` occurs.
14. **User-specified file:** Program does not delete or modify the input content.

In the sample from section 5, the six valid records have durations `120, 300, 450, 80, 200, 150`. Manual check: sum is `1300`, min `80`, max `450`, average `216.666...` so it prints `216.67`. Each level appears exactly twice, and total lines after the header is eight.

## 12. Extension Exercises

After getting the program running, you can extend it in the following directions:

**Exercise 1 — Per-day statistics.** Add an ISO `yyyy-MM-dd` `date` column, counting by date and level. Use `LocalDate.parse()` to validate dates, then consider `Map<LocalDate, Stats>`. Analyze memory if the file has millions of distinct date/key values.

**Exercise 2 — Reading multiple files.** Pass a list of paths from the CLI, process each file through the same `analyze()` method, then merge. Define a policy when one file fails: halt all or report per-file status; do not silently skip failed files.

**Exercise 3 — Reporting error rate.** Compute `invalid / rows × 100%` if `rows > 0`, printed with `Locale.ROOT`. Set a threshold (for example error rate above 1%) to warn or fail the job.

**Exercise 4 — Distinguishing exact and approximate statistics.** With billions of durations, try designing a fixed histogram with buckets `0–99`, `100–499`, `500+`. Bucket counters use near-O(1) memory, but percentiles derived from buckets are **estimates**, not exact values.

**Exercise 5 — Comparing two approaches.** Write another version using `Files.lines()`, ensure the stream is closed, parse identically, and compare byte/line totals, checksums, and invalid line counts; benchmark multiple runs with fair page cache states. Do not measure once and conclude which API is faster.

## 13. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `Files.readAllLines()` on multi-GB files | Heap spikes, GC/OutOfMemoryError | Use `BufferedReader.readLine()` |
| `Files.lines().toList()` | Collects all lines into RAM | Use terminal operations that do not materialize every line |
| Forgetting to close `Stream` from `Files.lines()` | File descriptor/resource leak | `try-with-resources` |
| Comparing `line == null` for blank lines | Confuses EOF and blank records | `null` only occurs at EOF |
| Assuming a large file only has short lines | A single extremely long line still spikes RAM | Parser with record length limit |
| Not specifying charset | Misreads Vietnamese/header columns | Use appropriate charset, usually UTF-8 |
| `split(",")` for CSV with quoted commas | Splits records incorrectly | Use a compliant CSV parser |
| Summing durations in `int` | Silent overflow | `long` + overflow check |
| Computing average when `count=0` | Division by zero or wrong output | Convention `n/a` |
| Using `groupingBy()` with a unique key per line | Map grows near line count | Bound cardinality or use external aggregation |
| Logging every record | Logging I/O overwhelms aggregation work | Aggregate errors and cap diagnostics |
| Using `parallel()` with unsynchronized shared accumulators | Race conditions, wrong totals | Thread-safe aggregator or partition/merge design |
| Skipping header and column count checks | Reads wrong schema yet still yields "results" | Validate input structure |
| Reading a changing file as an immutable snapshot | Incomplete/inconsistent metrics | Publish immutable files or snapshots |
| Assuming one `readLine()` always reads a full business record | Multiline quoted CSV can span multiple physical lines | Compliant stateful CSV parser |

**Remember:** For large text files, **read line by line with `BufferedReader` or `Files.lines()`**, validate schema and data immediately, and update accumulators instead of accumulating all records. Memory can stay nearly constant when only computing count/sum/min/max and when group count is bounded, but you must still control **line length, group cardinality, charset, I/O errors, overflow, and stream lifecycle**. That is the foundation of a Java statistics job that is both scalable and verifiable.
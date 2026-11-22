# Reading Large Files Line by Line and Aggregating Statistics in Java

When processing logs, transaction records, telemetry, or a CSV file ranging from hundreds of MBs to multiple GBs, calling `Files.readAllLines(path)` and iterating over the resulting list can create massive heap pressure: each line is a string, plus the list of references, intermediate objects, and decoding overhead. Most aggregation tasks **do not need to keep all lines in memory**. They only need to read one line at a time, validate the record, and update a few counters, sums, minimums/maximums, or per-group statistics.

This exercise walks through reading a large file line by line with `BufferedReader` and `Files.lines()`, designing **streaming / one-pass** statistics, and handling malformed lines, encoding, numeric overflow, resources, and performance. A complete Java 17 program reads `level,durationMs` data and counts valid/invalid records, per-log-level counts, total, min, max, and average without building a list of all lines.

**Goal:** Memory cost depends primarily on the size of the **longest line** and the amount of statistical state retained, rather than scaling linearly with the total number of lines when only fixed counters and groups are kept.

## 1. Whole-File Reading vs. Line-by-Line Reading

| Reading Approach | Behavior | Best Suited For |
| --- | --- | --- |
| `Files.readString(path)` | Reads file content into a single `String` | Small files needing full content in RAM |
| `Files.readAllLines(path, charset)` | Reads all lines and builds a `List<String>` | Small/medium files needing random re-access to every line |
| `Files.newBufferedReader(path, charset)` | Reads sequentially via `BufferedReader.readLine()` | Large files, line-by-line processing, flow and error control |
| `Files.lines(path, charset)` | Returns a lazy `Stream<String>`, reading when a terminal operation runs | Filter/map pipelines; the stream must still be closed |
| `FileChannel.read(ByteBuffer)` | Reads byte blocks, **does not split lines or decode charsets** | Binary protocols, custom parsers, or explicit byte-buffer control |

For large text files, `BufferedReader` is a solid starting point: easy line management, explicit checked `IOException` handling, and clear lifecycle control. `Files.lines()` is appropriate when the pipeline is straightforward and you do not accidentally collect every line into memory with `collect(toList())`.

Large file size **does not mean** you have to use `MappedByteBuffer` or write your own byte decoder: streaming text via `BufferedReader` is usually sufficiently accurate, maintainable, and easy to benchmark.

## 2. Input Dataset and Statistics Requirements

Suppose each data line is a two-column record separated by a comma:

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

1. The first line **must strictly be** `level,durationMs`, serving as the header and excluded from statistics.
2. Each subsequent line must have exactly one comma and two non-empty fields.
3. `level` must be one of `INFO`, `WARN`, `ERROR`; matched case-sensitively after trimming leading/trailing whitespace on each field.
4. `durationMs` must be a **non-negative** `long` integer.
5. Invalid lines are **counted in `invalid`** and skipped when computing sum/min/max/average. Do not discard the entire file because of one dirty line.
6. Metrics to print: total data rows, valid, invalid, count per level, total duration, min, max, average.
7. The file can be very large; the program does not store a `List<String>`, does not retain all valid records, and creates no intermediate files.

For the sample data: there are **8 data rows**, 6 valid rows, and 2 invalid rows (`broken` and `INFO,-1`). Each level has 2 valid rows; total duration is **1300 ms**, min **80 ms**, max **450 ms**, and average **1300 / 6 = 216.67 ms**.

This is a **simple CSV format defined by the exercise**, **not a general RFC 4180 CSV parser**: it does not support commas inside quoted fields, newlines inside fields, or escape rules. When processing real-world CSV with quoted fields, use a dedicated CSV parser or implement a resource-bounded state machine instead of blindly calling `split(",")`.

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
        // Process each line immediately and update accumulators.
    }
}
```

This is an **illustrative snippet**: the input file must exist and the application must handle `IOException`; the code does not yet include a `main` method. Key points:

- `readLine()` returns a string containing the line content, **excluding line-termination characters**; or `null` at end of file.
- Common line endings such as LF (`\n`), CRLF (`\r\n`), and CR are recognized as line terminators per the `BufferedReader` contract.
- **An empty line is `""`, not `null`.** If the data contains blank lines, decide whether to skip them, count them as errors, or treat them as empty records.
- `readLine()` can throw `IOException`, such as a device error or invalid input decoding.
- `try-with-resources` closes the reader even if the loop stops due to an error. It also closes the underlying stream created by `Files.newBufferedReader()`.

**Distinguish "not loading the whole file" from "strictly bounded RAM".** `readLine()` must construct a string for **one entire line**. If a file contains **a single gigabyte-long line** with no newline, the program still risks running out of memory. Line-by-line reading is memory-safe **when individual line length is bounded**; for untrusted inputs, use a parser that limits character/byte counts before materializing overly long strings.

### Character Encoding and Charset

Specify the charset explicitly:

```java
Files.newBufferedReader(path, StandardCharsets.UTF_8);
```

Do not rely on the default charset when files are shared across machines. A real file might use UTF-8, UTF-16, or another encoding; **specify the source's true encoding**. A `UTF-8 BOM` at the start of a file can appear in read content as `\uFEFF`, causing header checks using `equals()` to fail. If the convention allows a BOM, handle it explicitly right at the **start of the file**, rather than stripping the first character of every line.

## 4. One-Pass Aggregation: Keeping Small State and Updating Incrementally

Instead of:

```java
List<String> lines = Files.readAllLines(path);
long valid = lines.stream().filter(...).count();
```

(this snippet only illustrates an anti-pattern; `...` is not runnable Java code), maintain accumulators:

```text
rows           = 0      // Total rows after header
valid          = 0      // Number of accepted rows
invalid        = 0      // Number of rejected rows
sumDurationMs  = 0      // Sum of valid durations
minDurationMs  = +∞     // Min of valid rows
maxDurationMs  = -∞     // Max of valid rows
count[INFO]    = 0
count[WARN]    = 0
count[ERROR]   = 0
```

For each line:

1. Increment `rows`.
2. Validate column count, level, and duration.
3. If invalid: increment `invalid` and move to the next line.
4. If valid: increment `valid`, increment the level counter, add duration to the sum, and update min/max.
5. At EOF: compute average if `valid > 0`; if there are no valid rows, print `n/a` to avoid division by zero.

**You do not need to know the total line count or file size in advance** to compute these statistics. With three fixed levels, the number of counters is also fixed. Time cost scales roughly with total characters/bytes read plus parsing overhead, while memory is not a `List` ballooning alongside file size.

### Overflow and Precision

Do not use `int` for total duration when files can hold millions of records. Use `long`, and if the sum could exceed `Long.MAX_VALUE`, check with `Math.addExact()` (throwing `ArithmeticException` on overflow) or use `BigInteger` if business logic genuinely requires a wider range.

For the average:

```java
double average = valid == 0 ? Double.NaN
        : (double) sumDurationMs / valid;
```

This is an illustrative formula; variables must be declared in the application context. `double` is suitable for reporting averages; for currency or domains needing exact decimal precision, use `BigDecimal` with an explicit rounding policy. Do not sum `long` values into an `int` and expect the final division to undo an overflow that already happened.

## 5. Complete Java 17 Program: One-Pass Large File Statistics

Create the file **`LargeFileStatsDemo.java`**. If run **with no arguments**, the program generates sample data in a temporary file, analyzes it, and deletes the sample file. If passed **one path**, the program reads that file and **never modifies or deletes the user-specified file**.

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

            // Only overwrite the temporary file just created by this program itself.
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

This is only an example of Unix path syntax; replace it with the actual path appropriate for your operating system. The file must follow the `level,durationMs` format described above; output will reflect the data of the passed file.

### Analyzing How the Example Works

- `Files.newBufferedReader()` holds only a read buffer and the string for the current line, rather than a list of all lines.
- The header is validated upfront to avoid mismatched columns or summarizing a completely wrong file format.
- `line.indexOf(',')` locates the single comma and ensures there is no second comma; this fits the **simple two-column format** without quoted CSV.
- `Level.valueOf()` validates the level; `Long.parseLong()` validates the duration; both can throw `IllegalArgumentException` (including its subclass `NumberFormatException`) and are recorded as invalid lines.
- `stats.accept()` runs only for valid records; `Math.addExact()` prevents silent `long` overflow on totals.
- `minMs/maxMs` are initialized with sentinel values, yet **sentinels are never printed when valid=0**.
- `Locale.ROOT` keeps the `.` decimal separator in sample output, avoiding dependence on local machine regional settings.
- The argument branch only **reads** the user's file, while the no-argument branch only creates and deletes **a temporary file owned by the program**.

The exercise intentionally counts invalid lines without printing their full line contents, because large files can bloat error logs or expose sensitive data. In a real service, you can output a **capped number of diagnostics**, such as the first 10 errors with line number and reason, without leaking sensitive fields.

## 6. `Files.lines()`: Same Goal Using the Stream API

`Files.lines(path, StandardCharsets.UTF_8)` returns a lazy `Stream<String>`. A simple example counting lines containing a keyword:

```java
// Illustrated inside a method allowed to throw IOException.
try (java.util.stream.Stream<String> lines =
        Files.lines(file, StandardCharsets.UTF_8)) {
    long errors = lines.filter(s -> s.startsWith("ERROR,")).count();
    System.out.println(errors);
}
```

This is an **illustrative snippet**, not a standalone program: `file` must be a valid `Path`, with `Files` imported and exceptions handled. `Files.lines()` does not need to build a list before `count()`. It reads and inspects lines as the terminal operation executes.

**Closing the stream is mandatory.** The stream returned by `Files.lines()` is backed by an open file resource; do not return it out of a `try-with-resources` block for a caller to consume after the file has been closed.

During stream execution, I/O errors arising after stream creation may be wrapped in `UncheckedIOException` by the pipeline. This differs from `BufferedReader.readLine()` declaring a checked `IOException`. Choose appropriate error handling and never swallow exceptions in terminal operations.

### Do Not Turn Streaming into Eager Collection

An anti-pattern:

```java
try (var lines = Files.lines(path)) {
    var all = lines.toList();
    // all now holds every line in RAM!
}
```

This snippet is **illustrative**, requiring a `Path` variable `path` and `IOException` handling. `Files.lines()` is only lazy **until** you invoke a terminal operation. `toList()`, `collect(toList())`, or `groupingBy(..., toList())` can accumulate huge amounts of data, forfeiting memory benefits.

A collector can be used to count groups:

```java
// Illustrative snippet: appropriate only after row data is validated.
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    var counts = lines
            .filter(s -> !s.isBlank())
            .collect(java.util.stream.Collectors.groupingBy(
                    s -> s.substring(0, s.indexOf(',')),
                    java.util.stream.Collectors.counting()));
}
```

However, **this code is unsafe for inputs missing a comma**, and the header will be counted if not skipped. It only illustrates a collector and **does not replace complete, validated code**. Moreover, memory used by `groupingBy()` grows with the number of distinct groups. If every line has a unique key, the map can grow nearly as large as the total line count; in that case, bound cardinality or use external aggregation.

## 7. Designing Group-by Statistics for Large Files

The exercise's fixed three-level counters keep memory O(1) relative to line count. Real datasets often need statistics by date, region, or status code:

| Problem | Minimum State | Memory |
| --- | --- | --- |
| Count total rows and invalid rows | A few `long` counters | Nearly O(1) |
| Sum, min, max, average | `sum, count, min, max` | Nearly O(1) |
| Count by 3-value level | Three-element array / `EnumMap` | Nearly O(1) |
| Count by HTTP status code (finite domain) | Array or map bounded by code count | Proportional to codes that appear |
| Count by unbounded user ID | `Map<userId, count>` | Proportional to distinct user IDs, potentially huge |
| Exact distinct value count | `HashSet` | Proportional to distinct values |
| Top-K with fixed K | Min-heap and suitable counters | Often O(K) for top-K selection once frequencies exist, though exact frequencies for all keys still require additional state |
| Exact median/p95 | Typically requires storing data or suitable indexing/algorithms | Not always O(1) |
| Approximate median/p95 | Appropriate sketch/histogram | Can bound memory at the cost of approximation error |

Do not claim "reading line by line ⇒ all statistics are O(1) memory". What is true is that **the reading mechanism itself does not store the whole file**; aggregation can still hold significant data depending on requirements. For high cardinality, consider bucketing by key, external sorting, a database, or chunked data-processing tools.

### Retaining Enough State for Accurate Averages

To combine averages across multiple files, do not store and directly average each file's average, because files have different valid row counts. Store **`sum` and `count`**, then combine:

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

When merging across machines, define overflow handling, associativity/order, and invalid-line policies before aggregating.

## 8. Optimizing I/O: Buffers, Allocations, and Charset Decoders

`Files.newBufferedReader()` uses a buffered character reader suitable for many cases. If a specific buffer size is needed, you can combine:

```java
// Illustrative, file is a valid Path; IOException is handled by the caller.
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

Several optimization choices that require controlled benchmarking:

1. **Minimize unnecessary object allocation.** `String.split(regex)` allocates an array and multiple strings; if the format has only one delimiter, `indexOf()` and `substring()` can be simpler. However, never trade away correctness on complex CSV for speed.
2. **Count with `long` instead of `int`** for very large files.
3. **Separate I/O from parsing in benchmarks.** Measuring raw reading differs from measuring read + validation logic + record creation + aggregation.
4. **Warm up the JVM/JIT and file cache fairly.** A second run can be faster due to the OS page cache even with the same API; never compare a cold run to a warm run and conclude one algorithm is better.
5. **Do not build a massive `StringBuilder` for all lines** just to compute a few metrics.
6. **Do not blindly parallelize `Files.lines()`**: line splitting, ordering, shared resources, and mutable accumulators can complicate code without speeding it up.
7. **Avoid logging on every line** when processing hundreds of millions of rows; stdout/logging itself can be slower than read I/O.
8. **Choose the right charset** and handle encoding errors; speed does not matter if data is parsed incorrectly.

You can use JMH to benchmark pure CPU/parsing steps, though **JMH does not automatically control the OS cache**. To evaluate end-to-end throughput, also measure file opening, reading, decoding, parsing, GC, and resource closing under realistic application scope.

## 9. Handling Dirty Data and Safety Limits

Large files are rarely completely clean. Policies for **skip, fail-fast, quarantine** must be agreed upon before running:

| Scenario | Suggested Handling |
| --- | --- |
| Wrong header or empty file | Fail-fast, as you may be reading the wrong data type |
| Row with wrong column count | Increment invalid, log a bounded number of diagnostics |
| Unknown level | Increment invalid or map to OTHER if business rules allow |
| Non-integer duration | Increment invalid or fail-fast per requirements |
| Negative duration | Reject if valid domain requires non-negative |
| Duration value causing sum overflow | Stop with a clear error or use `BigInteger` |
| File with wrong charset | Report decode error; do not silently switch encoding and proceed without rules |
| Extremely long single line | Enforce character/byte limits in the parser before allocating excessive memory |
| File modified while reading | Results may not reflect a consistent snapshot |
| Disk/network filesystem error | `IOException`; do not report completion with partial statistics without checkpoints |

If statistics serve sensitive domains (finance, auditing), record the parsing policy, schema version, input file checksum, and error-handling behavior so results are traceable. Do not silently drop bad rows and publish statistics as if all data were processed.

### Do Not Accept an Unbounded Line Just Because You Are Streaming

`BufferedReader.readLine()` offers no "maximum line length" parameter. If inputs come from untrusted third parties, the limit must run **while consuming characters/bytes**, not merely:

```java
String line = reader.readLine();
if (line.length() > 10000) { ... }
```

because by the time of the check, `readLine()` **has already constructed the huge string**. A safer bounded parser can read chunk/character by chunk, stop/flag when the threshold is exceeded, and skip the rest up to the newline without accumulating. If standard CSV data is required, choose a parser library capable of limiting record/field lengths.

## 10. Processing Multi-GB, Multi-Day, or Multi-Source Files

For **a single large file**, one-pass streaming is usually sufficient. For **multiple files**, loop over each file, close `BufferedReader` after each one, and merge statistics into a global accumulator using overflow-checked addition. There is no need to hold thousands of file descriptors open simultaneously.

For continuously appended files like live logs, one pass can hit EOF before the log writer appends more data. **Reading a file to EOF is different from tailing a file (`tail -f`).** If the application needs new data in real time, design proper polling, rotation handling, or file watching instead of spinning `readLine()` in an infinite busy-wait loop.

When a file is written concurrently, a consistent snapshot is not guaranteed by default. Options include:

- Processing only files **completely closed** by the producer and published via an appropriate rename.
- Creating a snapshot/immutable input with an explicit checksum or version.
- If live reading is unavoidable, defining when an incomplete line lacking a trailing newline is considered complete, and handling log rotation and retries.
- To read parts of the same file in parallel, locate **true line boundaries** at split points; splitting purely by byte offset and letting workers read arbitrarily risks double-counting or dropping lines.

**Note:** Java's `BufferedReader.readLine()` can return the final line even when the file does not end with a newline. For immutable files, this is a valid line per text-reading rules; for an active log, it may be a **partial record**. Define a publish/snapshot protocol instead of guessing.

## 11. Testing Statistics Before Running on Real Data

Cases to cover:

1. **Header-only file:** `rows=0`, `valid=0`, `invalid=0`, min/max/average are `n/a`.
2. **Empty file:** Fails on header check; not accepted as a valid dataset.
3. **Malformed lines:** Missing comma, extra comma, single column only, unknown level, non-numeric duration.
4. **Blank lines:** Under the example policy, blank lines are `invalid`.
5. **Negative duration:** Rejected; does not affect `sum` or average.
6. **Zero duration:** Valid; affects `count` and can affect `minMs`.
7. **Large durations:** Test `long` parsing and handling sums exceeding `Long.MAX_VALUE`.
8. **UTF-8/BOM:** Verify encoding and BOM policy on real files.
9. **CRLF/LF:** Ensure line counting is independent of newline style.
10. **No trailing newline at EOF:** Final line is still read.
11. **Very large file:** Monitor heap/GC; avoid memory growth with row count.
12. **File modified mid-run:** Ensure a snapshot/retry policy exists or explicitly document results are not a snapshot.
13. **Mid-read error:** Do not emit a "success" report when `IOException` occurs.
14. **User-specified file:** Program never deletes or modifies input content.

In the sample from section 5, the six valid records have durations `120, 300, 450, 80, 200, 150`. Manual check: sum is `1300`, min `80`, max `450`, average `216.666...` so it prints `216.67`. Each level appears exactly twice, and total rows after the header is eight.

## 12. Extension Exercises

Once the program runs, you can extend it in the following directions:

**Exercise 1 — Daily statistics.** Add an ISO `yyyy-MM-dd` `date` column and count by date and level. Use `LocalDate.parse()` to validate dates, then consider `Map<LocalDate, Stats>`. Analyze memory if the file has millions of distinct dates/keys.

**Exercise 2 — Reading multiple files.** Pass a list of paths from the CLI, process each file through the same `analyze()` method, and aggregate. Define a policy when one file fails: abort all or report per-file status; never silently skip failed files.

**Exercise 3 — Reporting error rate.** Compute `invalid / rows × 100%` when `rows > 0`, printed with `Locale.ROOT`. Set a threshold (e.g., error rate above 1%) to warn or fail the job.

**Exercise 4 — Exact vs. approximate statistics.** For billions of durations, design a fixed-bucket histogram `0–99`, `100–499`, `500+`. Bucket counters take nearly O(1) memory, though percentiles derived from buckets are **estimates**, not exact values.

**Exercise 5 — Comparing two approaches.** Write an additional version using `Files.lines()`, ensure the stream is closed, parse identically, and compare total bytes/lines, checksums, and invalid row counts; benchmark across multiple runs with fair page-cache state. Never measure just once and declare one API faster.

## 13. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `Files.readAllLines()` on multi-GB files | Heap spikes, GC/OutOfMemoryError | Use `BufferedReader.readLine()` |
| `Files.lines().toList()` | Pulls all lines into RAM | Use terminal operations that do not materialize every line |
| Forgetting to close `Stream` from `Files.lines()` | File descriptor/resource leaks | `try-with-resources` |
| Comparing `line == null` for blank lines | Confuses EOF and empty records | `null` occurs only at EOF |
| Assuming large files always have short lines | One huge line still exhausts RAM | Use a parser with record-length limits |
| Not specifying a charset | Misreads accented text/header columns | Specify the right charset, usually UTF-8 |
| `split(",")` on CSV with quoted commas | Splits records incorrectly | Use a standards-compliant CSV parser |
| Summing durations in an `int` | Silent integer overflow | `long` + overflow checks |
| Computing average when `count=0` | Division by 0 or wrong output | Use `n/a` convention |
| Using `groupingBy()` with a unique key per line | Map grows nearly to row count | Bound cardinality or use external aggregation |
| Logging every record | Logging I/O overwhelms aggregation work | Aggregate errors and cap diagnostics |
| Using `parallel()` with an unsynchronized shared accumulator | Race conditions, wrong totals | Thread-safe aggregator or partition/merge design |
| Not checking header and column count | Misreads schema yet produces "results" | Validate input structure |
| Reading a changing file while treating it as an immutable snapshot | Incomplete/inconsistent metrics | Publish immutable files or snapshots |
| Assuming one `readLine()` always reads a complete business record | Quoted multiline CSV can span physical lines | Stateful standards-compliant CSV parser |

**Remember:** For large text files, **read line by line with `BufferedReader` or `Files.lines()`**, validate schema and data immediately, and update accumulators instead of accumulating all records. Memory can stay nearly constant when computing count/sum/min/max with bounded groups, but you still must control **line length, group cardinality, charset, I/O errors, overflow, and stream lifecycles**. That is the foundation of a Java statistics job that is both scalable and verifiable.

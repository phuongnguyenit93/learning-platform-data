# Streaming Large Datasets Line by Line and Bounding Result Size

When processing log files, transactions, system-exported tables, or event streams with millions of lines, calling `Files.readAllLines(path)` and holding everything in a `List` often wastes large amounts of heap. The Java Stream API lets you **read and process line by line on demand** with `Files.lines`, filter and transform through a lazy pipeline, and then compute a sum, count, write to a file, or collect a **bounded result**. However, **reading input line by line does not automatically guarantee small memory**: a trailing `collect(toList())`, `sorted()`, `distinct()`, or `groupingBy(..., toList())` can still hold data proportional to the entire source.

This lesson belongs to the **Performance and Memory** chapter of the **JAVA_STREAM_API** module. We will combine lazy pipelines, `filter`, `map`, `reduce`, and `collect` to process large datasets without materializing every record. Concepts of grouping, custom collectors, `Spliterator`, parallel processing, and resource limits are also analyzed. The focus is not a trick like “turn on Stream to save RAM”, but **designing bounds for each category of state and output**.

## 1. Three bounds to set before running

Suppose the input has `n` lines, of which `m` are valid, with `k` distinct group keys, and the application only needs `K` priority results.

| Bound | Question to answer | Example |
|---|---|---|
| **Per-record input** | How long can a single line be? How many objects does each line create? | Reject overly long lines; cap text field sizes |
| **Intermediate state** | Does the operation hold a list, Set, Map, or sort buffer that grows with the source? | Per-region aggregator; a top-K heap |
| **Output result** | Is the entire result kept in memory, or written incrementally / capped at K records? | `limit(100)`, top-10, writing via `BufferedWriter` |

A design with `limit(100)` at the end can still run out of memory if an earlier `sorted` has to buffer millions of records. Conversely, a pipeline processing **all `n` lines** and only computing `count`/`sum` can keep nearly constant state.

### 1.1. Distinguish runtime from memory

- **Reading `n` lines** takes at least work proportional to the data actually read, unless the problem allows short-circuiting or the source is indexed.
- **Memory does not have to scale with `n`**. A summation can scan line by line and hold only a single running total.
- **Bounding result count does not mean bounding lines read**. Finding the 10 largest transactions across a whole file typically still requires inspecting all transactions.
- **Potentially unbounded sources** cannot support operations that require seeing the entire input, such as global sorting, without an appropriate termination bound.

Notation such as `O(1)`, `O(K)`, `O(k)`, or `O(n)` in this lesson refers to **order of auxiliary memory**, not an exact byte guarantee; the JVM also involves object headers, buffers, boxing, capacity, and garbage collection overhead.

## 2. Reading data line by line with `Files.lines`

Since Java 8, `java.nio.file.Files.lines(Path, Charset)` creates a `Stream<String>` that reads lines from a file on demand:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = /* resolved file path */;

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long nonBlank = lines
            .filter(line -> !line.trim().isEmpty())
            .count();

    System.out.println(nonBlank);
}
```

This snippet must sit inside a method that handles or declares `IOException`. `Files.lines` does not load the entire file into a `List<String>` before creating the Stream. The reader may allocate buffers and individual `String`s during traversal, while `filter` and `map` steps generally do not need to retain all prior lines.

### 2.1. Comparing with `readAllLines`

```java
// Unsuitable if the file is too large for the heap:
List<String> allLines =
        Files.readAllLines(path, StandardCharsets.UTF_8);

// Line-by-line streaming approach:
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.count();
}
```

`readAllLines` returns a `List` containing every line, with memory growing with line count and total text length. `Files.lines` enables on-demand traversal, yet **the downstream pipeline determines whether all lines are retained**.

### 2.2. `Files.lines` holds an I/O resource

A Stream created by `Files.lines` is backed by an open resource. Therefore:

1. Use `try-with-resources` to **close the source Stream**.
2. Closing is still required after terminal operations like `count`, `findFirst`, `limit`, or `collect` finish.
3. Short-circuiting **does not automatically close the file**.
4. Do not return a Stream created inside an already-exited `try-with-resources` block: the caller would receive a closed Stream.
5. If you intentionally return an open Stream, clearly document that **the caller owns closing responsibility**; for public APIs, a callback/consumer executing inside the resource scope is often safer.

I/O errors occurring **during traversal** may surface as `UncheckedIOException`, not only `IOException` when opening the file. `try-with-resources` still ensures `close` is called whether exiting via error or normally.

## 3. `BufferedReader.lines` and similar sources

If you already have a `BufferedReader`, you can create a Stream from the reader:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    Stream<String> lines = reader.lines();
    long count = lines.filter(s -> !s.isEmpty()).count();
}
```

Here, the **reader** opened by the program is closed via `try-with-resources`; do not rely solely on a terminal operation on `reader.lines()`. Avoid reading `reader` via other methods while the Stream from `reader.lines()` is being consumed: two traversal paths could interfere on the same source state.

| Source | Characteristic | Resource handling |
|---|---|---|
| `Files.lines(path, UTF_8)` | Reads file lines through a Stream | Close the Stream |
| `BufferedReader.lines()` | Stream from an already-opened reader | Close the owning reader |
| `Files.list(dir)` | Stream of directory entries | Close the Stream |
| `Files.walk(dir)` | Walks a directory tree | Close the Stream |
| `Stream.of(...)` | In-memory elements | Usually holds no I/O resources |
| `Collection.stream()` | Traverses an existing collection | Source data stays in memory |

`Files.walk` is a stream of paths; it does not read every file's contents immediately. If you use `flatMap` to open each child file, make the inner close policy and error handling explicit; never leave thousands of file readers open simultaneously without control.

## 4. Lazy pipelines save RAM only when the terminal operation allows it

Consider the pipeline:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines
            .filter(s -> s.startsWith("ERROR"))
            .count();
}
```

Semantically, the pipeline can scan and count continuously without needing a List of every `ERROR` line. If we change the terminal operation:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> errors = lines
            .filter(s -> s.startsWith("ERROR"))
            .collect(java.util.stream.Collectors.toList());
}
```

The `errors` list must keep **every error line**, so memory grows with the number and length of error lines. Having `Files.lines` as the source **does not erase the cost of `toList`**.

### 4.1. Analyzing by retained record count

| Pipeline | Typical retained state/output |
|---|---|
| `lines.count()` | Small, near `O(1)` |
| `lines.map(...).reduce(...)` | Depends on reduction; many numeric reductions are `O(1)` |
| `lines.filter(...).findFirst()` | Small; can short-circuit |
| `lines.filter(...).limit(K).toList()` | Roughly `O(K)` plus size of the `K` retained elements |
| `lines.sorted().limit(K).toList()` | May need to hold `O(n)` before `limit` |
| `lines.distinct().limit(K).toList()` | Usually maintains “seen” state; retained count depends on execution path and consumed source prefix |
| `lines.collect(groupingBy(key, counting()))` | `O(k)` group state |
| `lines.collect(groupingBy(key, toList()))` | `O(k+n)` references for groups and elements |

This is a typical model for **general sources**. The JVM and Stream implementation may optimize special cases; do not treat Big-O entries in the table as a specification across all runtimes.

### 4.2. Be especially careful with very long text elements

`Files.lines` reads **line by line**, but a single line can be huge. So you must never infer that “only one line exists at a time” means memory is always tightly bounded. A single line of several hundred MB can exhaust the heap even before a `filter` predicate can inspect it.

A check like:

```java
.map(line -> {
    if (line.length() > 1024) {
        throw new IllegalArgumentException("Line too long");
    }
    return line;
})
```

only **rejects after the line String has already been constructed**. It is useful as a data policy, yet **not a hard memory cap while reading**. If you must guarantee never materializing a line past a threshold, use a reader/parser that reads character chunks and **enforces the limit before accumulating the whole line**, or enforce limits at the source layer.

## 5. Placing `limit` correctly and understanding result semantics

`limit(K)` is a **short-circuiting stateful intermediate operation**: on a Stream with encounter order, it keeps at most the **first K elements in source order**.

```java
List<String> firstTenErrors;
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    firstTenErrors = lines
            .filter(s -> s.startsWith("ERROR"))
            .limit(10)
            .collect(Collectors.toList());
}
```

The result has at most 10 error lines. `filter` is placed **before `limit`**, so the program looks for the **first 10 error lines** rather than “taking the first 10 lines of the file and checking for errors”.

### 5.1. Order of `filter` and `limit` changes semantics

```java
// Get up to the first 10 error lines appearing across the source.
lines.filter(isError).limit(10);

// Inspect only the first 10 lines of the source; may return fewer than 10 errors.
lines.limit(10).filter(isError);
```

These are **separate pipeline patterns**; do not reuse the same `lines` variable after a terminal operation. `isError` is an application-defined predicate.

If there are a million lines and the tenth error appears near the end, the first version may still have to read nearly a million lines. Thus `limit(10)` bounds **output count**, not the number of input elements inspected.

### 5.2. `sorted` before `limit` does not bound memory to K

```java
List<Event> top = events.stream()
        .sorted(Comparator.comparingLong(Event::getAmountCents)
                .reversed())
        .limit(10)
        .collect(Collectors.toList());
```

The pipeline may buffer up to all `n` elements to sort before returning the top 10. If you need the **10 largest transactions in the entire file**, `limit(10)` alone does not guarantee `O(10)` added memory. Section 8 uses a **K-bounded heap** to solve this problem more accurately.

### 5.3. `skip`/`limit` does not give cheap random-access pagination

`lines.skip(offset).limit(pageSize)` can bound the **page output size**, but to reach line one million of a file, the program typically still has to read/skip all preceding lines. This is **not `O(1)` random access**. If data is indexed in a database or storage engine, consider indexed queries / keyset pagination rather than repeatedly scanning from the start of a file.

### 5.4. `limit` on an unordered Stream

For a source without encounter order or a pipeline calling `unordered()`, `limit(K)` is permitted to select any qualifying subset under its contract, not “the earliest K records”. If business logic requires **the exact first K lines in file order**, keep the source and pipeline ordered and avoid unnecessary order drops.

## 6. Three ways to bound memory during aggregation

### 6.1. Narrow elements then count/aggregate numerically

If the requirement is **total transaction line count and total amount**, keep only counters:

```java
long totalCents;
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    totalCents = lines
            .skip(1) // Skip header according to file format.
            .map(BoundedStreamingReportDemo::parse)
            .mapToLong(Event::getAmountCents)
            .reduce(0L, Math::addExact);
}
```

This snippet uses `parse` and `Event` from the complete program in section 9. `Math.addExact` detects `long` overflow; it does not build a list of parsed events.

### 6.2. Grouping by metrics, not retaining element lists

```java
Map<String, Long> countByRegion;
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    countByRegion = lines
            .skip(1)
            .map(BoundedStreamingReportDemo::parse)
            .collect(Collectors.groupingBy(
                    Event::getRegion,
                    Collectors.counting()));
}
```

Memory depends on **the number of distinct regions `k`** rather than transaction count `n`, provided Map values are just counts. Still, **`k` can approach `n`** if keys are unconstrained. For a trustworthy RAM bound, you must know or cap group key cardinality, not merely assume `groupingBy` is “small”.

### 6.3. Using a collector with bounded state

To get the **K highest-value transactions**, keep a **min-heap of at most K elements**. To report by region, keep a Map capped at an allowed key limit `maxGroups`. Both bounds can be combined into one custom collector to **scan the source in a single pass**.

State model:

```text
Stream<Event> (read from file)
         |
         v
  BoundedAccumulator
   - totalCount: long                 O(1)
   - totalCents: long                 O(1)
   - byRegion: Map<String, Stats>     O(maxGroups)
   - bestEvents: PriorityQueue<Event> O(K)
         |
         v
Report: metrics + region Map + list of K largest transactions
```

With bounded ID/region lengths, **state and result** memory scales mainly as `O(maxGroups + K)`. The source still reads every required line, without storing all `n` events.

## 7. Choosing between bounded results and continuous streaming output

Two problem types are easily confused:

1. **Bounded result record count**: you only need the first 100 events or the 10 largest events. Keeping K elements in memory is reasonable.
2. **Need to output all results without holding them in heap**: for example, normalizing a 50 GB file into a cleaned file. Here you cannot reduce the **number of lines to write**, yet you can write line by line directly to a `BufferedWriter` instead of building a giant List.

### 7.1. Writing output line by line

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static void exportNormalized(Path input, Path output)
        throws IOException {
    try (Stream<String> lines =
                 Files.lines(input, StandardCharsets.UTF_8);
         BufferedWriter writer =
                 Files.newBufferedWriter(output,
                         StandardCharsets.UTF_8)) {
        lines.map(String::trim)
                .filter(s -> !s.isEmpty())
                .forEachOrdered(line -> {
                    try {
                        writer.write(line);
                        writer.newLine();
                    } catch (IOException cause) {
                        throw new UncheckedIOException(cause);
                    }
                });
    } catch (UncheckedIOException failure) {
        throw failure.getCause();
    }
}
```

Here, **output must differ from input**: never open the same file for simultaneous reading and overwriting. The example applies a simple “trim and drop blank lines” policy, not CSV quoting. `forEachOrdered` preserves action order when the source has encounter order; writing to the file is an **intentional side effect in the terminal operation**, not mutating a shared List.

**Important consequence:** if an error happens mid-write, the output file may contain partial data. For applications requiring atomicity, write to a **temporary file on the same filesystem**, close cleanly, then move/rename using an OS-appropriate strategy. The application must handle temp-file cleanup and error recovery; `Stream` does not provide file transactions.

### 7.2. Do not use parallel `forEach` to write to a shared writer

`parallel().forEach(...)` can invoke actions concurrently and out of order, while `BufferedWriter` is not automatically a safe ordered concurrent sink. If the goal is simply streaming lines into one file in order, sequential processing or an explicitly coordinated pipeline is much simpler and safer.

## 8. File-wide Top-K using a bounded heap

Suppose there are `n` transactions and you only need the **K largest transactions** by amount. When K is much smaller than n:

- `sorted(desc).limit(K)` typically needs `O(n)` intermediate memory.
- A **min-heap holding at most the K best candidates** needs `O(K)` state.
- Each new transaction is compared against the smallest candidate currently in the top-K.

Algorithm:

```text
empty heap (min-heap), capacity K

for each transaction e:
    if heap.size < K:
        add e
    else if e ranks higher than heap.peek:
        remove heap.peek
        add e
    else:
        discard e

after reading all inputs:
    drain up to K transactions from heap
    sort the K results in desired order
```

Typical complexity: **`O(n log K + K log K)` time** and **`O(K)` auxiliary memory** for the heap and final result list. When K = 0, return an empty list without inserting into the heap.

### 8.1. Tie-breaking is part of correctness

If two transactions have the same amount, the application must decide which one to keep when only one slot remains. We can compare by:

1. `amountCents` ascending.
2. `id` ascending as tie-breaker.

In a top-K selecting the **highest rank**, a transaction with a larger ID ranks higher when amounts are equal. This is only an **illustrative rule**; real reports may choose timestamp, ID, or require keeping all ties at the K boundary. If you must keep **all ties at rank K**, output size can exceed K and it is no longer a strictly bounded top-K problem.

### 8.2. Why not use the average of K candidates as the threshold?

To tell whether a new candidate belongs in top-K, you only need to compare against the **smallest element among the K retained candidates**, without computing averages or re-sorting the whole set on every line. `PriorityQueue` supports `peek/poll/offer` with appropriate cost.

## 9. Complete Java 8 program: single-pass memory-bounded report

This program runs on **JDK 8 or higher**. It creates a small TSV file for demonstration (or reads a user-supplied path), uses `Files.lines` and **a custom collector** to:

- Count all valid transactions after the header.
- Sum amounts using `Math.addExact`.
- Count and sum amounts per region, **capping the maximum number of regions**.
- Select the **top-3 transactions by largest amount** using a `PriorityQueue` never exceeding 3 elements.
- Return a report without exposing internal mutable Maps/Lists.

Data format: **TSV** (*tab-separated values*) with exactly three columns: `id`, `region`, and `amountCents`. This is a simple example, **not a quoted-field CSV parser**.

### 9.1. Standalone source code

Save as `BoundedStreamingReportDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class BoundedStreamingReportDemo {

    static final class Event {
        private final String id;
        private final String region;
        private final long amountCents;

        Event(String id, String region, long amountCents) {
            this.id = id;
            this.region = region;
            this.amountCents = amountCents;
        }

        String getId() { return id; }
        String getRegion() { return region; }
        long getAmountCents() { return amountCents; }
    }

    // Ascending order by amount then ID. Heap keeps lowest rank at root.
    private static final Comparator<Event> RANK =
            Comparator.comparingLong(Event::getAmountCents)
                    .thenComparing(Event::getId);

    static Event parse(String rawLine) {
        // Reject long lines after the String has already been built.
        // This is NOT a hard limit on memory while reading a line.
        if (rawLine.length() > 1024) {
            throw new IllegalArgumentException("Line too long");
        }

        String[] fields = rawLine.split("\t", -1);
        if (fields.length != 3) {
            throw new IllegalArgumentException(
                    "Expected 3 TSV fields: " + rawLine);
        }

        String id = fields[0].trim();
        String region = fields[1].trim();
        if (id.isEmpty() || region.isEmpty()
                || id.length() > 32 || region.length() > 24) {
            throw new IllegalArgumentException(
                    "Invalid ID or region");
        }

        long cents = Long.parseLong(fields[2].trim());
        if (cents < 0) {
            throw new IllegalArgumentException(
                    "Amount cannot be negative");
        }
        return new Event(id, region, cents);
    }

    // Metrics for one region.
    static final class RegionTotals {
        long count;
        long sumCents;

        void add(long cents) {
            count = Math.addExact(count, 1L);
            sumCents = Math.addExact(sumCents, cents);
        }

        void combine(RegionTotals right) {
            count = Math.addExact(count, right.count);
            sumCents = Math.addExact(sumCents, right.sumCents);
        }
    }

    // Value DTO not mutated after creation.
    static final class RegionView {
        final long count;
        final long sumCents;

        RegionView(long count, long sumCents) {
            this.count = count;
            this.sumCents = sumCents;
        }
    }

    // A: mutable state of a Collector.
    static final class BoundedState {
        final int topK;
        final int maxRegions;
        long count;
        long totalCents;
        final Map<String, RegionTotals> byRegion = new HashMap<>();
        final PriorityQueue<Event> best = new PriorityQueue<>(RANK);

        BoundedState(int topK, int maxRegions) {
            if (topK < 0 || maxRegions <= 0) {
                throw new IllegalArgumentException(
                        "topK must be >= 0 and maxRegions must be > 0");
            }
            this.topK = topK;
            this.maxRegions = maxRegions;
        }

        void keepCandidate(Event event) {
            if (topK == 0) {
                return;
            }
            if (best.size() < topK) {
                best.offer(event);
            } else if (RANK.compare(event, best.peek()) > 0) {
                best.poll();
                best.offer(event);
            }
        }

        RegionTotals getOrCreate(String region) {
            RegionTotals state = byRegion.get(region);
            if (state == null) {
                if (byRegion.size() >= maxRegions) {
                    throw new IllegalStateException(
                            "Exceeded region limit");
                }
                state = new RegionTotals();
                byRegion.put(region, state);
            }
            return state;
        }

        // Accumulator: updates all metrics for one Event.
        void add(Event event) {
            count = Math.addExact(count, 1L);
            totalCents = Math.addExact(
                    totalCents, event.getAmountCents());
            getOrCreate(event.getRegion())
                    .add(event.getAmountCents());
            keepCandidate(event);
        }

        // Combiner following contract if the framework splits the source.
        BoundedState combine(BoundedState right) {
            if (topK != right.topK || maxRegions != right.maxRegions) {
                throw new IllegalArgumentException(
                        "Accumulator configuration mismatch");
            }

            count = Math.addExact(count, right.count);
            totalCents = Math.addExact(
                    totalCents, right.totalCents);

            right.byRegion.forEach((region, totals) -> {
                getOrCreate(region).combine(totals);
            });

            // Top-K of union lies within union of local top-Ks.
            for (Event event : right.best) {
                keepCandidate(event);
            }
            return this;
        }

        Report finish() {
            Map<String, RegionView> regions = new TreeMap<>();
            byRegion.forEach((region, totals) -> regions.put(
                    region, new RegionView(
                            totals.count, totals.sumCents)));

            List<Event> sortedBest = new ArrayList<>(best);
            sortedBest.sort(RANK.reversed());

            return new Report(
                    count,
                    totalCents,
                    Collections.unmodifiableMap(regions),
                    Collections.unmodifiableList(sortedBest));
        }
    }

    // R: result does not expose mutable Collector state.
    static final class Report {
        final long count;
        final long totalCents;
        final Map<String, RegionView> byRegion;
        final List<Event> bestEvents;

        Report(long count, long totalCents,
                Map<String, RegionView> byRegion,
                List<Event> bestEvents) {
            this.count = count;
            this.totalCents = totalCents;
            this.byRegion = byRegion;
            this.bestEvents = bestEvents;
        }
    }

    static Collector<Event, BoundedState, Report> boundedCollector(
            int topK, int maxRegions) {
        return Collector.of(
                () -> new BoundedState(topK, maxRegions),
                BoundedState::add,
                BoundedState::combine,
                BoundedState::finish);
    }

    static void reportFrom(Path input) throws IOException {
        Report report;
        try (Stream<String> lines =
                     Files.lines(input, StandardCharsets.UTF_8)) {
            report = lines
                    .skip(1) // One header in sample TSV format.
                    .filter(line -> !line.trim().isEmpty())
                    .map(BoundedStreamingReportDemo::parse)
                    .collect(boundedCollector(3, 1000));
        }

        System.out.println("Transactions: " + report.count);
        System.out.println("Total cents: " + report.totalCents);
        report.byRegion.forEach((region, totals) ->
                System.out.println(region
                        + ": count=" + totals.count
                        + ", cents=" + totals.sumCents));

        System.out.println("Top transactions:");
        report.bestEvents.forEach(event ->
                System.out.println(event.getId()
                        + ": " + event.getAmountCents()));
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 1) {
            reportFrom(Paths.get(args[0]));
            return;
        }
        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Usage: java BoundedStreamingReportDemo [file.tsv]");
        }

        // Generate sample data to run without preparing a file.
        Path sample = Files.createTempFile("bounded-stream-", ".tsv");
        try {
            Files.write(sample, Arrays.asList(
                    "id\tregion\tamountCents",
                    "E01\tBAC\t120",
                    "E02\tNAM\t990",
                    "E03\tBAC\t500",
                    "E04\tTRUNG\t1500",
                    "E05\tNAM\t250",
                    "E06\tBAC\t1500",
                    "E07\tNAM\t0"
            ), StandardCharsets.UTF_8);
            reportFrom(sample);
        } finally {
            Files.deleteIfExists(sample);
        }
    }
}
```

### 9.2. Running and interpreting output

On JDK 8 or higher:

```text
javac BoundedStreamingReportDemo.java
java BoundedStreamingReportDemo
```

Expected output:

```text
Transactions: 7
Total cents: 4860
BAC: count=3, cents=2120
NAM: count=3, cents=1240
TRUNG: count=1, cents=1500
Top transactions:
E06: 1500
E04: 1500
E02: 990
```

Group totals: `2120 + 1240 + 1500 = 4860`. The heap keeps at most **3 candidates**. Regions are capped at **1000 keys**; if data contains a 1001st region, the collector **fails explicitly** instead of silently allocating more memory for group keys.

In real usage, run:

```text
java BoundedStreamingReportDemo data.tsv
```

with the documented TSV format and input policy. The demo does not read the entire file into a List; the file is only created in the sample branch to provide test data.

### 9.3. Why is one collector enough for multiple metrics?

In `BoundedState.add`, a single `Event` updates the overall count, overall sum, region statistics, and heap. **There is no need** to reopen the file four times to compute four metrics. The final finisher creates a `Report` containing a copy of the retained results.

`BoundedState.combine` is also implemented to merge two branches if the framework chooses partitioned accumulation. Numeric addition, keyed merging, and top-K under a total order must be designed correctly; **do not declare `CONCURRENT`** because `HashMap` and `PriorityQueue` are not safe for concurrent modification by multiple workers on a single instance.

However, **the file source in the example runs sequentially by default**. Do not add `parallel()` to `Files.lines` merely because a combiner exists: file reading, parsing, and merging can lose benefits due to I/O, source splitting, or contention. Measure specifically before enabling it.

### 9.4. Top-K can be merged across branches

Given a total-order comparator for Events, if an Event is **not in its own branch's top-K**, at least K Events in that branch rank higher than it; thus it cannot be in the global top-K when merged with other branches. Therefore, considering candidates from **each branch's top-K** suffices to compute the global top-K.

The example requires transaction IDs to be **unique** for deterministic tie-breaking. If the ranking key does not define a total order, or business rules require keeping all ties at the K boundary, adjust the algorithm and bounding rules accordingly.

### 9.5. Limits not solved by the demo

The demo checks line length **after reading the entire line into a String**; to defend against extremely long lines at the input layer, use a reader/parser that enforces the cap **before materializing the line**. Capping key count is also insufficient if keys can be arbitrarily long, so the code bounds `region.length()` and `id.length()`.

Moreover, `split("\t", -1)` is a naive TSV split that does not understand escaping, embedded tabs, or quoted fields. Real CSV/JSON Lines formats require an appropriate parser. The sample fails on bad data rather than silently skipping rows; a production system may need a *dead-letter* policy, error counters, and safe logging.

## 10. Notes on pagination and batch loading

When the source is a database or API, **result bounding should start at the layer capable of applying it efficiently**:

- For queries ordered by an indexed key, querying from the next key (*keyset/cursor pagination*) avoids scanning/skipping huge numbers of prior-page rows.
- For plain unindexed text files, `skip(offset)` typically still must read/scan all lines before the offset.
- For unbounded event streams, establish termination rules by record count, time, size, or business signal; never call `sorted().collect(toList())` on an endless stream.
- A *batch* should have an explicit size bound. When writing each batch to storage, release references to the old batch before building the next.

### 10.1. Sequential batch processing example

```java
final int BATCH_SIZE = 500;
List<Event> batch = new ArrayList<>(BATCH_SIZE);

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    lines.skip(1)
            .map(BoundedStreamingReportDemo::parse)
            .forEachOrdered(event -> {
                batch.add(event);
                if (batch.size() == BATCH_SIZE) {
                    processBatch(batch);
                    batch.clear();
                }
            });
}

if (!batch.isEmpty()) {
    processBatch(batch);
    batch.clear();
}
```

`processBatch(batch)` in the example is an **application-provided function**. It must execute **synchronously** and not retain a reference to `batch` after returning; if it dispatches the batch asynchronously and then we call `clear()`, downstream tasks could observe an emptied list. For async processing, transfer ownership of a copy of the batch or design a bounded queue with backpressure.

Bounding `BATCH_SIZE` controls **the element count in the buffer**, yet if each `Event` holds huge payloads, the RAM budget remains uncertain. Additionally, if `processBatch` fails, you need retry/idempotency policies to avoid lost or duplicate writes; Stream provides no transactions.

### 10.2. Backpressure and queue bounds

A producer reading a file faster than a consumer writes to a database can build an unbounded queue if implemented by continuously `submit`ting tasks. Even if each batch has only 500 elements, **10,000 queued batches** still hold millions of elements.

Thus, when decoupling producer and consumer, bound **both batch size and queued batch count**. Options include bounded queues, semaphores, or backpressure mechanisms from your framework. `parallelStream()` does not automatically bound total business queue capacity.

## 11. Ordering, repeatability, and parallel processing

### 11.1. Encounter order

`Files.lines` emits lines in file order. If the output requires the **first 10 error lines**, keep the pipeline ordered and use `filter(...).limit(10)`. `forEachOrdered` is appropriate when side-effect order such as writing a file is an explicit requirement.

If you switch to `parallel()`, do not call `forEach` and expect lines to be written in original order. If only counting or summing with a properly associative operation, order may not matter; even then, verify actual performance gains.

### 11.2. `findFirst` and `findAny`

`findFirst()` picks the first element by encounter order when the source is ordered. `findAny()` can pick any matching element for greater parallel freedom. If you need **the first error line in the file**, do not replace `findFirst` with `findAny` just to “optimize” and alter result meaning.

### 11.3. Limits and `distinct`

`distinct` typically tracks seen values. On a very large source where distinct count approaches n, the hash table can grow large. If you only need the **first K distinct SKUs** in order, `map(...).distinct().limit(K)` can stop early after K distinct values, though the amount of data read before seeing K distinct values may still be huge. When needing **all** distinct SKUs, the Set can grow to `O(u)`; consider off-heap storage or a database when `u` is too large.

## 12. Handling bad data, precision, and consistency

### 12.1. Avoid losing rows via silent filtering

A pipeline like:

```java
lines.map(BoundedStreamingReportDemo::parse)
     .filter(event -> event.getAmountCents() > 0)
```

**drops all zero-amount transactions**. If 0 is a valid transaction, this skews counts and group metrics. Before “filtering to go faster”, define clearly which records belong in the report.

For malformed data, two common strategies are:

- **Fail-fast**: stop on the first invalid line and raise a clear error.
- **Continue and track errors**: separate valid/invalid records, count error types, and optionally route failures to a separate handler.

Never silently drop malformed lines while claiming “processed all n transactions” when n includes those lines.

### 12.2. Overflow and reduction operations

`LongStream.sum()` returns `long`, which can overflow when sums exceed its range. The demo uses `Math.addExact` in both accumulator and combiner to **fail loudly** instead of returning negative wrapped numbers.

When monetary values exceed `long` or averages follow accounting rounding rules, use `BigInteger`/`BigDecimal` or an appropriate numeric model; do not default to `double` for exact money.

### 12.3. Input changing while being read

If the file is appended to, truncated, or replaced while the pipeline is reading, do not assume traversal gets a **consistent snapshot**. Safer operations include immutable batch inputs, writing to a temp file and renaming on completion, or querying with storage-level snapshots/transactions. `Files.lines` is a line-reading utility, not a database snapshot mechanism.

## 13. Measuring memory and performance properly

Do not measure only `Runtime.totalMemory() - Runtime.freeMemory()` after `collect`: intermediate buffers may already have been GC'd, while the result may retain source objects long-term.

| Metric | Purpose |
|---|---|
| **Allocated bytes** | Inspect total allocations from mappers, parsers, boxing, containers |
| **Peak live heap** | Observe peak live objects during execution |
| **Retained size** | Identify which objects are kept alive by result Maps/Lists |
| **GC pause / throughput** | Evaluate collection cost and latency impact |
| **Elapsed time / throughput** | Evaluate processing speed for n lines |
| **File descriptor/handle count** | Catch unclosed I/O sources |
| **Max line length & group key count** | Verify assumptions about memory bounds |

Suitable tools in the Java ecosystem include Java Flight Recorder (JFR), Java Mission Control (JMC), VisualVM, heap dump analyzers, and JMH for microbenchmarks.

### 13.1. Benchmark scenarios to include

1. **Keep data and business rules identical** across approaches.
2. Vary `n` from thousands to millions while holding `K` constant.
3. Grow `k` sharply to see whether group Maps hit bounds.
4. Test varying line lengths, including abnormally long lines.
5. Compare `Files.readAllLines` against `Files.lines` on finite inputs small enough to run safely.
6. Compare `sorted().limit(K)` against a top-K heap, verifying **identical results**, including tie-breakers.
7. Observe peak memory and allocations, not only memory after the program finishes.
8. Measure I/O separately on real disks, warm/cold filesystem caches, and concurrent thread load.

Do not conclude “Streams are faster than loops” or “parallel is always better than sequential” from a single run on a dev laptop. Choose line-by-line streaming and bounded state for the **memory contract**, then optimize with real measurements.

## 14. Common mistakes

| Practice or claim | Consequence | Fix |
|---|---|---|
| “Using `Files.lines` means RAM is always `O(1)`.” | `collect(toList())`, `sorted` can still retain n elements | Analyze the entire pipeline and terminal |
| `filter(...).collect(toList())` on a huge file | List may hold millions of Strings | Count/aggregate, `limit`, or write to a file |
| `sorted().limit(10)` for top-10 and calling it `O(10)` RAM | Sort may buffer n elements | Use min/max or a bounded heap |
| `limit(10).filter(isError)` when needing the first 10 errors | Inspects only the first 10 lines of the source | `filter(isError).limit(10)` |
| Using `skip(1_000_000)` and treating it as fast paging | Still must skip all preceding lines | Indexed or keyset/cursor pagination |
| `groupingBy(key, counting())` without bounding keys | Map can grow near n | Bound/control key cardinality |
| Checking line length only **after** `Files.lines` | Huge line already materialized before check | Reader with hard limit before line allocation |
| `Files.lines(...).count()` without closing Stream | I/O resource leak | `try-with-resources` |
| Returning a Stream created inside an exited `try` block | Caller receives a closed Stream | Change ownership API or collect inside scope |
| Parallel `forEach` writing to a shared mutable writer/List | Data races or lost ordering | Sequential processing or controlled synchronization |
| Batching by 500 with an unbounded task queue | Many batches pile up, exhausting RAM | Bound both batch size and queue depth |
| `batch.clear()` after async batch submission | Consumer sees mutated List | Transfer ownership/copy |
| Keeping only counts when business needs details | Drops required information | Match detail level to report contract |
| Using `sum()` for money while ignoring overflow | Total can be wrong | `Math.addExact` or larger numeric type |
| Printing every line while benchmarking throughput | Logging I/O dominates timing | Measure compute and I/O separately |

## 15. Practice exercises with answers

### Exercise 1. Reading one million lines when only total money is needed

**Problem:** Should you use `Files.readAllLines` followed by `mapToLong`, or `Files.lines` + `mapToLong` + `reduce`?

**Answer:** Choose `Files.lines` inside `try-with-resources`, parse line by line, and aggregate. You do not need a List of one million lines when the result is a single number. If the sum risks exceeding `long`, consider `Math.addExact` or an appropriate numeric type.

### Exercise 2. Two positions of `limit`

**Problem:** A file has 500 initial lines with no `ERROR`, followed by 30 error lines. Do `filter(isError).limit(10)` and `limit(10).filter(isError)` return the same result?

**Answer:** No. The first pipeline finds the first 10 errors (when enough exist); the second inspects only the first 10 lines of the file and returns empty. `limit` bounds element count **at its position** in the pipeline.

### Exercise 3. Top-5 on a very large file

**Problem:** You have 20 million transactions and only need the five largest. Should you use `sorted(desc).limit(5).toList()` or a bounded heap?

**Answer:** Consider a bounded heap keeping at most 5 candidates, with auxiliary memory `O(5)` for retained Events and runtime roughly `O(n log 5)`. `sorted` may need a buffer proportional to all `n`. Define tie-breaking rules before choosing the algorithm.

### Exercise 4. Report with unbounded keys

**Problem:** Does `groupingBy(User::getId, counting())` always use less memory than `collect(toList())`?

**Answer:** Not guaranteed. If nearly every line has a unique userId, group count `k` approaches `n`, the Map can be very large, and each entry has overhead. When only a few groups repeat, `groupingBy(counting())` usually saves substantially.

### Exercise 5. Is the batch really bounded?

**Problem:** A producer continuously creates 100-element batches and pushes them into an unbounded `BlockingQueue`. The consumer is very slow. Is system memory bounded to `O(100)`?

**Answer:** No. The number of queued batches can grow without bound. You must bound **both batch size and pending batch count**, or use an appropriate backpressure mechanism.

### Exercise 6. Abnormally long data lines

**Problem:** Why does `Files.lines(path).filter(line -> line.length() <= 4096)` not create a hard 4096-character cap on read memory?

**Answer:** Because `Files.lines` already builds the line `String` before `filter` checks its length. A huge line can spike memory first. A hard cap requires a reader/parser checking length **while reading**, before storing the full line.

### Exercise 7. Empty results vs. zero values

**Problem:** A file contains only a header. A collector computing count and total amount returns `0`; is that enough to conclude “there is a transaction worth 0”?

**Answer:** No. Count = 0 means no records after the header, while total = 0 can occur even when zero-amount transactions exist. Both count and sum are needed to distinguish the two cases.

### Exercise 8. Exporting all lines without keeping them in heap

**Problem:** You need to normalize 10 million lines into a new file without returning a List. What is the right approach?

**Answer:** Read via `Files.lines` or `BufferedReader` and write line by line to a `BufferedWriter` closed in `try-with-resources`, using `forEachOrdered` when order matters. Plan handling for partial output files on error; do not use `collect(toList())` just to loop and write lines.

### Exercise 9. Explaining peak memory of `collect`

**Problem:** A program returns a `List` of only 10 elements, yet a profiler shows a sharp heap spike before the terminal operation. What could cause this?

**Answer:** There may be a `sorted` or stateful operation buffering the source, or a mapper creating many temporary objects. Final List size does not equal **peak processing memory**. Inspect allocations, live heap, and allocation sites.

### Exercise 10. Merging top-K across branches

**Problem:** When a collector has multiple local accumulators, can you build the global top-K solely from each branch's top-K?

**Answer:** Yes, if using the same **deterministic** ranking order and K-selection rule. Any element outside a branch's top-K already has at least K elements in that branch ranked higher, so it cannot be a global top-K candidate. Define a tie-breaker, and do not apply directly if business rules require keeping all ties.

## 16. Checklist before processing large files or streams

1. **Are output requirements clear?** Count/sum only, top-K, first K lines, or all transformed data?
2. **Have you distinguished lines read from results retained?** `limit` does not always shrink traversal work.
3. **Are sources opened and closed properly?** `Files.lines`/`BufferedReader` need clear resource ownership scopes.
4. **Is per-line size bounded?** Checking after `Files.lines` is not a pre-allocation hard limit.
5. **Are there stateful data-retaining operations?** `sorted`, `distinct`, `groupingBy(toList())`, or `collect(toList())` can blow RAM budgets.
6. **Can counts/sums replace detail Lists?** Only when business rules do not require retaining records.
7. **If grouping by key, is cardinality `k` bounded?** Is there a policy when the limit is exceeded?
8. **If taking top-K, are comparator and tie-breaker explicit?** Can ties exceed K?
9. **If exporting all data, are you streaming writes instead of building a List?** Is there recovery for partial output?
10. **If using batches/async, are both batch size and queue depth bounded?**
11. **Do monetary/quantity calculations detect overflow?** Do averages check `count == 0`?
12. **Have you tested empty data, bad lines, high key counts, huge lines, and large files?** Verify both semantics and resources.
13. **Have you measured peak heap, allocations, GC, and I/O?** Do not inspect only final List size.
14. **Is parallelism truly needed?** Measure first; never use a shared writer or unsafe mutable Map.

**Conclusion:** Processing large data line by line with the Java Stream API avoids **materializing the entire input**, yet keeping memory controlled also requires bounding **per-record size**, **accumulated state**, and **retained results**. `Files.lines` paired with `try-with-resources` handles source lifecycles; `filter`/`limit` select subsets; `reduce`, numeric collectors, and top-K heaps keep state small; and `BufferedWriter` streams full output line by line without giant Lists. Combining these three bounds with edge-case testing and profiling lets pipelines handle large sources while preserving correctness, performance, and operability.

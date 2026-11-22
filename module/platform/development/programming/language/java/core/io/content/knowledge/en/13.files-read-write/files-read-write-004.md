# Lazy Reading with `Files.lines` and Mandatory Stream Lifecycle Management in Java

## 1. What Problem Does `Files.lines()` Solve?

In Java NIO.2, **`java.nio.file.Files.lines(Path)`** returns a **`Stream<String>`** of text lines from a file. Instead of reading the entire file into a `List<String>` before processing, the application can build a chain of operations such as `filter`, `map`, `limit`, `findFirst`, `count`, etc., and process the content on demand.

Example:

~~~java
// Code snippet: path is a valid Path; the method handles IOException.
try (java.util.stream.Stream<String> lines =
        java.nio.file.Files.lines(
                path, java.nio.charset.StandardCharsets.UTF_8)) {
    long count = lines
            .filter(line -> line.startsWith("ERROR"))
            .count();
    System.out.println(count);
}
~~~

Here **`Files.lines()` creates a Stream bound to the file**, while `filter()` does not traverse the lines immediately. When the terminal operation `count()` executes, the Stream starts pulling elements to compute the result. Exiting the **try-with-resources** block automatically calls `close()` on the Stream, releasing the I/O resource.

**Most important takeaway:**

> **Lazy reading does not mean no resource is open.** `Files.lines()` opens the file to create the Stream, while the content is read as the Stream is consumed. Therefore, a `Stream<String>` obtained from `Files.lines()` must be closed after use.

This is a crucial distinction between an **in-memory** Stream like `List.stream()` and a Stream **backed by an external resource** like `Files.lines()`. Using the Stream API in general does not require `close()`, but the `Files.lines()` specification requires closing the Stream to release the open file.

## 2. Three Stages: Opening the File, Building the Pipeline, and Consuming

Diagram:

~~~text
Path to file
    |
    | Files.lines(path, UTF_8)
    v
Stream<String> bound to an I/O resource
    |
    | .filter(...)
    | .map(...)
    | .limit(...)
    v
Declared pipeline — has not traversed all data yet
    |
    | .count() / .findFirst() / .forEach() / .toList()
    v
Terminal operation causes data to be consumed
    |
    | End of try-with-resources
    v
Stream.close() -> closes the associated file resource
~~~

Distinguish carefully:

1. **`Files.lines(...)` can throw `IOException` immediately at call time**, for example if the file cannot be opened due to permissions or a bad path. Do not say "absolutely no I/O occurs until `count()`".
2. **Intermediate operations** like `filter()`, `map()`, `skip()`, and `limit()` generally only configure the pipeline. They do not force the entire file to be read immediately.
3. Once a **terminal operation** runs, pipeline traversal begins; some operations such as `findFirst()`, `anyMatch()`, and `limit(n)` can **short-circuit**, meaning they do not need to process the whole file.
4. **Completion of a terminal operation does not automatically close the Stream**. You must close it explicitly or preferably use try-with-resources.
5. A Stream is for **single-use consumption**. After a terminal operation, you cannot run another terminal operation on the same pipeline; to scan the file again, open a new Stream.

Implementations may use buffering or optimize splitting; do not rely on an assumption like "each `map()` step reads exactly one line of bytes from disk". *Lazy* describes pipeline execution semantics, not a promise about the exact count of I/O calls.

## 3. Java 17+ Program: Lazy Reading and Resource Closing

Create **`LazyFileLinesDemo.java`** (UTF-8 source):

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class LazyFileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lazy-lines-", ".log");

        try {
            Files.writeString(file,
                    "INFO start\n"
                    + "WARN slow\n"
                    + "ERROR disk\n"
                    + "INFO continue\n"
                    + "ERROR network\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {
                System.out.println("streamOpened=true");

                String firstError = lines
                        .filter(line -> line.startsWith("ERROR "))
                        .findFirst()
                        .orElse("not found");

                System.out.println("firstError=" + firstError);
            }

            try (Stream<String> lines =
                    Files.lines(file, StandardCharsets.UTF_8)) {
                long totalErrors = lines
                        .filter(line -> line.startsWith("ERROR "))
                        .count();

                System.out.println("totalErrors=" + totalErrors);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 LazyFileLinesDemo.java
java LazyFileLinesDemo
~~~

Stdout output:

~~~text
streamOpened=true
firstError=ERROR disk
totalErrors=2
~~~

Explanation:

- The program creates a temporary file, writes five UTF-8 lines, and then performs two **independent** `Files.lines()` passes.
- The first pass uses `filter(...).findFirst()` to find `ERROR disk`. Because `findFirst()` can stop once a match is found, it **does not necessarily process all remaining lines**.
- Even though the pipeline only needed the first error line, the Stream still must be **closed**. TWR handles this when leaving the block.
- The second pass opens a new Stream and uses `count()` to count every line prefixed with `ERROR `, producing 2.
- Finally, `Files.deleteIfExists(file)` removes the temporary file created by the program. Deleting the file is a separate operation, **not a substitute for closing the Stream**.

The demo lines contain only ASCII, so stdout is stable when run in a standard terminal. In real programs using Vietnamese or Unicode characters, both reader and writer must use the same charset.

## 4. Why Is `try-with-resources` Necessary?

`Files.lines()` returns a Stream holding a file I/O resource, so the standard pattern is:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    // Use lines here.
}
~~~

`Stream` inherits `BaseStream.close()` (`BaseStream` implements `AutoCloseable`), so it can be declared inside try-with-resources.

When the try block exits:

- If the body succeeds, the Stream is closed.
- If `filter`, `map`, `forEach`, or business code throws an exception, TWR still attempts to close the Stream.
- If the body executes `return`, TWR still runs `close()` before returning.
- If closing fails at the same time as a body exception, TWR's **primary/suppressed exception** rules apply; the body failure is not silently replaced by the cleanup error.

Do not close only when you "have read to EOF". A terminal operation that reads the entire file, stops early, or fails all require lifecycle management.

**Error-prone example:**

~~~java
// WRONG: the file resource may not be closed promptly.
long n = Files.lines(path).filter(String::isBlank).count();
~~~

Even though `count()` has finished running, the snippet does not close the Stream. Do not rely on the garbage collector to close file descriptors. Write:

~~~java
// RIGHT: whether the body reads all lines or throws an exception, it still closes.
try (Stream<String> lines = Files.lines(path)) {
    long n = lines.filter(String::isBlank).count();
}
~~~

**Do not write a method that returns a Stream already inside a TWR block and expect the caller to keep using it:**

~~~java
// WRONG: the Stream is closed when the method returns.
static Stream<String> broken(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank());
    }
}
~~~

TWR invokes `close()` before the returned value is handed back to the caller. The caller receives a pipeline backed by a closed source; consuming it later is invalid and can throw `IllegalStateException` or errors related to a closed resource.

## 5. Stream Ownership When Returning from a Method

There are two valid design patterns, depending on API needs.

### Pattern A — Process Inside the Method, Close Locally

~~~java
// Code snippet: add imports for Path, Files, IOException, StandardCharsets,
// and Stream when placing into an application source file.
static long countNonBlank(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
~~~

This is the **easiest to understand and least leak-prone** pattern. The method owns the file Stream and closes it completely before returning `long`. The caller does not need to know about the internal resource.

### Pattern B — Return the Stream and Transfer Close Responsibility to the Caller

~~~java
static Stream<String> openNonBlankLines(Path path)
        throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8)
            .filter(line -> !line.isBlank());
}
~~~

The caller **must** use TWR:

~~~java
try (Stream<String> lines = openNonBlankLines(path)) {
    lines.forEach(System.out::println);
}
~~~

`openNonBlankLines` returns a live Stream and **transfers ownership** to the caller. Because this is easy to misuse, the API should clearly name or document that the Stream must be closed. Do not write a wrapper that returns a Stream while closing it inside the factory.

**Note:** If you want to return an easier-to-manage result, consider returning a list, a count, or a computed value instead of forcing callers to remember to close a Stream. However, if you use `toList()` on a very large file, you must account for memory usage.

## 6. `filter`/`map`/`limit` Do Not Replace `close()`

The following examples **still require TWR**:

~~~java
// Read a few lines:
try (Stream<String> lines = Files.lines(path)) {
    lines.limit(5).forEach(System.out::println);
}
~~~

~~~java
// Find the first matching line:
try (Stream<String> lines = Files.lines(path)) {
    boolean found = lines.anyMatch(s -> s.contains("ERROR"));
    System.out.println(found);
}
~~~

~~~java
// Skip the first line and process the rest:
try (Stream<String> lines = Files.lines(path)) {
    lines.skip(1).forEach(System.out::println);
}
~~~

- `limit(5)` may stop reading after the first five elements.
- `anyMatch` may stop immediately upon finding a matching element.
- `skip(1)` skips the first line in the pipeline but still has to step through the source to identify elements.
- **All of them must be closed**, whether the terminal operation reads the entire file or not.

Do not assume **`findFirst()` closes the file automatically because it found a result**. Pipeline completion and I/O resource release are two separate concerns.

### Derived Streams Share the Underlying Resource

~~~java
try (Stream<String> errors = Files.lines(path)
        .filter(line -> line.startsWith("ERROR"))) {
    errors.forEach(System.out::println);
}
~~~

Closing the Stream produced by the pipeline triggers closing on the underlying Stream from `Files.lines()`. You do not need to—and should not—open/close the file again just because an intermediate operation was applied.

However, a Stream is still **single-use**: you cannot call `count()` and then `findFirst()` on the same `errors` variable. You must build a combined pipeline or open a new Stream.

## 7. Comparison with `Files.readAllLines` and `Files.readString`

**`Files.lines`**, **`Files.readAllLines`**, and **`Files.readString`** all read text, but their usage differs:

| API | Result | When data is fetched | Must caller close Stream? | Best fit |
| --- | --- | --- | --- | --- |
| `Files.lines(path)` | `Stream<String>` | Read as pipeline is consumed | **Yes** | Filtering/counting/processing large files or early termination |
| `Files.readAllLines(path)` | `List<String>` | Reads all lines before returning | No file Stream for caller to close | Small/medium files needing a list |
| `Files.readString(path)` | `String` | Reads entire text file | No file Stream for caller to close | Small text files needing full content including line breaks |
| `Files.newBufferedReader(path)` | `BufferedReader` | Per read operation | **Yes**, close Reader | Fine-grained line reading control or manual parsing |

Consequences:

- **`readAllLines`** holds all lines in memory upon return; for large files this can consume huge RAM. The API manages resources internally within the call, so the caller receives no Stream to close.
- **`readString`** reads all text into a single String and preserves line terminators; use it when you need the whole raw text rather than individual lines.
- **`Files.lines`** can save memory when processing maintains minimal state (counting, finding the first match, writing results to a sink). However, `Files.lines(...).toList()` still **creates a list holding all collected elements**: laziness at the source does not make an unbounded result list cheap.
- **`BufferedReader`** supports `readLine()` loops and manual control; the Reader itself is a resource that must be closed with TWR.

All three `Files` text-reading APIs have overloads accepting a charset; the common overloads **without a charset use UTF-8** in Java SE 17. When working with external formats or legacy files, specify `StandardCharsets.UTF_8` or the agreed charset explicitly instead of guessing.

## 8. Java 17+ Program: Aggregating Results Without Retaining All Lines

To count lines by log level, a Stream can traverse the file and keep only **counters** per group instead of storing the entire list of lines. Create **`LineSummaryDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LineSummaryDemo {
    static Map<String, Long> countLevels(Path file) throws IOException {
        try (Stream<String> lines =
                Files.lines(file, StandardCharsets.UTF_8)) {
            return lines
                    .filter(s -> !s.isBlank())
                    .map(s -> s.split(":", 2)[0])
                    .collect(Collectors.groupingBy(
                            Function.identity(),
                            TreeMap::new,
                            Collectors.counting()));
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("summary-", ".log");
        try {
            Files.writeString(file,
                    "INFO:started\n"
                    + "WARN:slow\n"
                    + "INFO:done\n",
                    StandardCharsets.UTF_8);

            System.out.println(countLevels(file));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LineSummaryDemo.java
java LineSummaryDemo
~~~

Stdout:

~~~text
{INFO=2, WARN=1}
~~~

In this example:

1. `Files.lines` creates a Stream reading the file.
2. `filter` skips blank lines; `map` extracts the prefix before the colon (per the demo log convention).
3. `Collectors.groupingBy` maintains counts per level; `TreeMap` keeps key ordering deterministic when printed.
4. `collect` consumes all lines to be processed. As soon as the try block ends, the Stream is closed.
5. The method returns the **computed Map**, no longer depending on an open file Stream.

With a small number of log levels, retained data does not scale linearly with total line count. However, if grouping keys are unbounded (e.g., grouping by each distinct line), the Map itself can still grow very large. **Laziness does not guarantee constant memory usage**; that depends on the terminal operation and stored state.

The program uses `String.split(":", 2)` as a minimal parser for the demo format. For production logs with escapes, timestamps, and complex structure, use a specification-compliant parser.

## 9. `IOException` on Opening the Stream and `UncheckedIOException` During Traversal

There are **two distinct I/O error stages**:

### Source Opening Stage

~~~java
Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8);
~~~

If the file cannot be opened, this call may throw **`IOException`** (a checked exception), for example when the path does not exist or lacks read permission. TWR has not yet received a successfully created Stream so there is no Stream to close; the file-opening API is responsible for internal cleanup if initialization fails.

### Consumption Stage

After `Files.lines()` has returned the Stream, I/O errors or decoding errors occurring during traversal may be **wrapped in `UncheckedIOException`** (a runtime exception). The root cause can be retrieved via `getCause()`.

Example handling both error categories explicitly:

~~~java
// Code snippet: path is a Path, UTF_8 is imported
try (Stream<String> lines = Files.lines(
        path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
} catch (java.io.UncheckedIOException duringRead) {
    System.err.println("Read failed: " + duringRead.getCause());
} catch (IOException duringOpen) {
    System.err.println("Open failed: " + duringOpen);
}
~~~

This is an illustrative diagnostic pattern. When multiple errors occur simultaneously, also check **suppressed exceptions**, because `close()` in TWR may fail while another exception is propagating. Do not swallow read errors and report success; if traversal stopped midway due to an I/O error, the computed summary can be incomplete.

**The wrong charset** can also cause text corruption or rejection while reading. `Files.lines(path, charset)` decodes bytes using the specified charset; it does not auto-detect the true original charset of arbitrary files. If the content is binary, use `InputStream` or byte-oriented `Files` APIs instead of trying to decode it into text lines.

## 10. Line Terminators and Edge Cases

`Files.lines()` produces a Stream of **text lines**, not strings retaining their line terminators. Supported line separators by contract include **LF** (`\n`), **CR** (`\r`), and **CRLF** (`\r\n`). Line terminators are stripped from the Strings representing lines.

Example:

~~~text
ASCII content bytes: A 
 B 
 
 C
Lines: ["A", "B", "", "C"]
~~~

Therefore:

- A **blank line in the middle of the file** is a valid empty String, not EOF.
- An empty file yields a Stream with zero lines.
- A file ending with a single line terminator after the final content **does not necessarily create an extra trailing blank line**; do not mechanically infer line count from newline character count.
- Very long lines can still force the program to hold a large line String in memory; "lazy reading" does not eliminate per-line memory bounds.
- If the file is being modified concurrently, **do not assume `Files.lines` provides a consistent snapshot**. For tasks requiring consistency, use a snapshot/locking mechanism or appropriate data source design.

**Distinguishing `String.lines()` from `Files.lines()`:** `String.lines()` creates a Stream from a String already in memory and holds no file descriptor to close. `Files.lines()` creates a Stream bound to an external file; it must be closed to release resources. Both APIs return `Stream<String>`, yet their **resource ownership** differs.

## 11. `BufferedReader.lines()` and Reader Lifecycle

Another option is opening a `BufferedReader` and obtaining a Stream from **`reader.lines()`**:

~~~java
// Code snippet: path is a Path, UTF_8 is imported.
try (java.io.BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines()
            .filter(s -> s.startsWith("ERROR"))
            .forEach(System.out::println);
}
~~~

In this pattern **the object to close is `BufferedReader` itself** because the method opened the Reader and holds ownership of it. Do not assume that running a terminal operation on `reader.lines()` automatically closes the Reader. Putting the Reader in TWR ensures `Reader.close()` runs when leaving scope.

Both approaches are valid, provided ownership is clear:

- `Files.lines(path)`: resource managed by the Stream from `Files.lines()`; **close the Stream**.
- `Files.newBufferedReader(path)` then `reader.lines()`: the application opened the Reader; **close the Reader**.
- If wrapping other layers or returning a Stream externally, clearly define when and by whom the underlying resource will be closed.

Do not let a Reader-backed Stream escape the scope where the Reader has already been closed, because by the time the caller traverses it, the data source is no longer alive.

## 12. Does Calling `parallel()` Always Make `Files.lines` Faster?

Streams support **`parallel()`**, but file I/O does not automatically speed up just by adding threads:

~~~java
// Code snippet: Path path is available and IOException is handled.
try (Stream<String> lines = Files.lines(path)) {
    long n = lines.parallel()
            .filter(s -> s.contains("ERROR"))
            .count();
}
~~~

Considerations:

- File reading and character decoding costs can be the bottleneck; `parallel()` does not guarantee shorter execution time.
- Work splitting and load balancing depend on the charset and spliterator implementation. Java optimizes certain charsets that can split along line boundaries, but do not assume **every charset or file source splits efficiently**.
- Operations with side effects—such as writing to a shared file, incrementing an unsynchronized mutable counter, or printing to stdout from multiple threads—can suffer from ordering issues and race conditions.
- With `findAny()` in parallel, the found element is not necessarily the first in file order; if you require the first line, use `findFirst()` and understand the cost of maintaining encounter order.

Benchmark with real data before choosing `parallel()`. **The requirement to close the Stream with try-with-resources does not change when the pipeline runs in parallel.**

## 13. Resource Management in Long-Running Applications

A short-lived CLI program can make leaks hard to notice. However, in servers, workers, services, or multi-file scanning jobs:

~~~text
for each request:
    Files.lines(file)      -> opens resource
    findFirst()            -> reads a portion
    no close()             -> resources can accumulate
~~~

The consequences can be too many open file descriptors, failures opening new files, OS resource exhaustion, or inability to modify/delete files on certain platforms. Therefore, treat the **Stream lifecycle** as a design requirement, not an optional optimization.

A sound workflow:

1. Identify the file and charset of the text data.
2. Open the Stream in **try-with-resources** within the smallest possible scope.
3. Build a pipeline without hard-to-control side effects; choose the terminal operation as required.
4. Do not reuse a Stream after a terminal operation and do not return a closed Stream.
5. Let TWR handle `close()` on all exit paths; log/propagate open, traversal, and cleanup errors per policy.
6. If only summary statistics are needed, **return the computed result** instead of a live Stream.
7. With a large number of files, open and close each file within its own scope; do not keep hundreds of Streams open unnecessarily at the same time.

**Key point:** there is no "automatic close guarantee" merely because code called `count()`, `forEach()`, `findFirst()`, or `toList()`.

## 14. Common Mistakes and Fixes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| `Files.lines(path).count()` without TWR | I/O resource may not close promptly | Wrap `Files.lines` in TWR |
| Thinking `Files.lines` opens the file only when terminal runs | Overlooks open errors and Stream ownership | Understand the file is opened when `Files.lines` returns the Stream |
| `findFirst()` without closing | Reading stops early while file stays held open | Close the Stream even on short-circuiting |
| `limit(10)` means automatic resource release | Confuses element limit with close | TWR independent of `limit` |
| Returning a Stream out of an already-exited TWR | Caller gets a pipeline over a closed source | Compute result locally or transfer ownership explicitly |
| Reusing a Stream after `count()` | Can throw `IllegalStateException` | Open a new Stream for a new traversal |
| Calling `toList()` on a huge file thinking it uses no RAM | List still holds many lines | Use streaming aggregation/suitable sink |
| Assuming `IOException` only happens at `Files.lines()` | Traversal errors can become `UncheckedIOException` | Catch and propagate errors per stage |
| Calling `reader.lines()` and forgetting to close the reader | Leaks underlying Reader | TWR on `BufferedReader` |
| Reading a file with the wrong charset | Decoding failures/garbled text | Specify the appropriate charset |
| Using `Stream<String>` to hold binary bytes | Decoding can alter bytes | Use byte streams |
| Assuming `parallel` is always faster | Extra overhead, races/out-of-order effects | Benchmark and keep processing thread-safe |
| Modifying the file while Stream traverses it | Results can be inconsistent | Use snapshots/synchronization when needed |

## 15. Self-Check Questions

**Q1.** Does `Files.lines(path)` wait until `count()` to open the file?  
**Answer:** No. `Files.lines` creates a file-backed Stream when called. The pipeline reads lines on demand as it is consumed, but opening the resource does not wait for the terminal operation.

**Q2.** If `findFirst()` reads only the first line, do you still need to close?  
**Answer:** Yes. Short-circuiting only stops consuming elements; it does not automatically release the file.

**Q3.** Does `Files.lines(path).toList()` always save RAM compared to `Files.readAllLines(path)`?  
**Answer:** No. Both can build a list holding all lines; a lazy source does not mean a collected result is lazy.

**Q4.** If a method returns a `Stream<String>` created from `Files.lines`, who must close it?  
**Answer:** If the Stream is meant to remain usable after returning, the caller must take ownership and close it via TWR or `close()` promptly. The API must state this contract clearly.

**Q5.** How can I/O errors during traversal appear after `Files.lines` has returned a Stream?  
**Answer:** `UncheckedIOException` wrapping the underlying `IOException`; file-opening failures can appear directly as `IOException` at `Files.lines()`.

**Q6.** Is it valid to call `count()` and then `findFirst()` on the same Stream?  
**Answer:** No. A Stream can only be used for one pipeline/terminal operation; open another Stream or combine requirements in a single traversal.

**Q7.** When using `BufferedReader.lines()` inside a method that opens its own reader, which object needs to be closed?  
**Answer:** The `BufferedReader` opened by the method; place it in TWR.

**Q8.** Why doesn't a lazy file Stream guarantee memory won't grow?  
**Answer:** A single line can be very long, and terminal operations like `toList()` or `groupingBy()` can retain lots of data in RAM.

## 16. Java SE 17 Documentation

- [Files.lines(Path)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path)): text line Stream, lazy population, file lifecycle and close.
- [Files.lines(Path, Charset)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset)): charset selection and exceptions.
- [BaseStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html): close, onClose, and single-use semantics.
- [BufferedReader.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#lines()): line Stream from a Reader.
- [Files.readAllLines](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readAllLines(java.nio.file.Path)): reading all lines into a List.

**Remember:** `Files.lines()` lets you build a Stream pipeline that reads lines on demand, yet **opens the file resource when creating the Stream**. Every path — reading to completion, stopping early, returning, or throwing an exception — requires closing the Stream promptly. The safe default pattern is **`try (Stream<String> lines = Files.lines(path, charset)) { ... }`**, and when passing a Stream out to a caller, you must also transfer close responsibility to that caller.
# `Files.readAllLines()` and Loading All Data into Memory in Java

## Lesson Objectives

In Java I/O, `Files.readAllLines(path)` is very convenient when you need to read a text file line by line. With a single call, you get a `List<String>` to iterate, access by index, count, or compare lines. However, the most important thing to remember is that **the method reads the entire file content and keeps all lines in the Java process's memory**.

After this lesson, you will:

- Understand the exact output and behavior of `Files.readAllLines(Path)` and `Files.readAllLines(Path, Charset)`.
- Explain the difference between **eager reading** of all lines and **streaming/lazy reading**.
- Know why file size on disk **does not equal** the heap memory used by `List<String>`.
- Use `Files.lines()` or `Files.newBufferedReader()` when data is large or of unknown size.
- Avoid pitfalls with newline characters, charsets, resources that must be closed, and the limitations of checking `Files.size()`.

The examples use **Java 17+**, with compile/run commands and easily verifiable output.

## 1. What Does `readAllLines` Actually Do?

Overloads to remember in `java.nio.file.Files`:

```java
public static List<String> readAllLines(Path path) throws IOException;

public static List<String> readAllLines(Path path, Charset cs)
        throws IOException;
```

These are **illustrative API signatures**, not a standalone program.

- `path` identifies the file's location on the filesystem. If the path is relative, its location depends on the working directory or base resolved by the filesystem.
- `Files.readAllLines(path)` uses **UTF-8** per Java's modern API contract.
- `Files.readAllLines(path, charset)` decodes bytes using the charset you choose, such as `StandardCharsets.UTF_8` or `StandardCharsets.UTF_16LE`.
- The result is **a list containing all read lines**; each element is a `String` without line-terminator characters.
- The method reads until **EOF** or an I/O error. It does not return earlier lines first while letting you read the rest on demand.
- After the call completes, the line contents reside in `List<String>` in Java memory and you do not need to keep an open file stream to iterate the list.
- If the file does not exist, cannot be read, is corrupted for the chosen charset, or has an access error, the call may throw `IOException` or an appropriate subclass.

Mental model example:

```text
UTF-8 file:
  alpha\n
  \n
  beta\r\n
  gamma\n

Files.readAllLines(...)
          |
          v
List<String> on the heap
  index 0: "alpha"
  index 1: ""
  index 2: "beta"
  index 3: "gamma"
```

In the diagram, `\n` and `\r\n` denote line-terminator characters, **not** literal backslashes stored in the list. An empty line **in the middle of the file** produces an `""` element; a simple line terminator at the **end of the file** does not create an extra trailing empty line.

Line terminators recognized by Java currently include LF (`\n`), CR (`\r`), and CRLF (`\r\n`). The API may expand the set of recognized line terminators in future versions, so do not build binary storage formats assuming only these exact three will ever exist.

## 2. Java 17+ Example: Reading an Entire File into `List<String>`

The program below creates a temporary file so it does not depend on paths on the learner's machine. It contains an empty line in the middle, different newline styles, and a trailing newline at the end of the file.

Save as **`ReadAllLinesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReadAllLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("lines-demo-", ".txt");

        try {
            Files.writeString(
                    file,
                    "Java\n\nPython\r\nGo\n",
                    StandardCharsets.UTF_8
            );

            List<String> lines =
                    Files.readAllLines(file, StandardCharsets.UTF_8);

            System.out.println("number of lines = " + lines.size());
            System.out.println("first = " + lines.get(0));
            System.out.println("second is empty = " + lines.get(1).isEmpty());
            System.out.println("last = " + lines.get(lines.size() - 1));
            System.out.println("joined = " + String.join("|", lines));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac ReadAllLinesDemo.java
java ReadAllLinesDemo
```

Output:

```text
number of lines = 4
first = Java
second is empty = true
last = Go
joined = Java||Python|Go
```

**Explanation:**

1. `Files.writeString` writes the exact specified string with UTF-8 encoding.
2. `readAllLines` reads to the end of the file and builds a `List<String>` with four elements: `"Java"`, `""`, `"Python"`, `"Go"`.
3. `lines.get(1).isEmpty()` shows that the empty line in the middle is preserved.
4. The trailing `\n` does not add a fifth line.
5. `String.join("|", lines)` only changes how we display the list; it does not restore the exact original line endings, because `readAllLines` stripped them.
6. `finally` cleans up the exact temporary file created. `readAllLines` manages opening/closing the internal read source; you do not call `close()` on `List<String>`.

**Edge case:** A completely empty file returns an empty list (`lines.size() == 0`). When handling potentially empty input, check `isEmpty()` before calling `get(0)`.

## 3. Why Is "Loading Everything into Memory" a Big Problem?

This is the most important distinction in the topic.

```text
                         Files.readAllLines(path)
                                   |
               read all, decode, split into lines
                                   |
                                   v
Java Heap:    List<String>
             +-----------------------------------+
             | reference -> String line 1        |
             | reference -> String line 2        |
             | reference -> String line 3        |
             | ...                               |
             | reference -> String line N        |
             +-----------------------------------+
                                   |
                         all data stays alive
                         while the list is retained
```

While the list remains referenced, the `String` objects and the structure holding them continue to occupy memory. Total memory usage can **differ significantly from the file size on disk**, because:

- Bytes in the file must be **decoded** into Java string data. UTF-8 byte count does not equal Java `char` count or in-memory string representation size.
- There is **per-`String` overhead**, element references, and list structure overhead. With millions of very short lines, overhead proportional to the **line count** can be substantial.
- Intermediate buffers and objects can appear during reading/decoding; peak memory usage while reading does not necessarily equal the size of the resulting list alone.
- How the JVM represents strings (such as compact strings), runtime architecture, and Java version affect actual sizes. **There is no fixed formula** like "a 100 MB file always uses 200 MB in the list".
- If you go on to call `stream()`, `map()`, `toArray()`, `copyOf()`, `collect()`, or create other copies, the program can retain even more objects and increase peak memory.

**General complexity:** storing all `N` lines requires memory that grows with **total retained content length plus per-line overhead**, rather than only the size of the read buffer. `readAllLines` suits **small, clearly bounded** data; for multi-GB logs, very large CSV files, or unbounded user-uploaded data, it is usually not a good choice.

If the heap runs out, the program may hit `OutOfMemoryError`. This is a serious `Error`; catching it and trying to continue should not be treated as a normal operational strategy. **Prevention by choosing the right algorithm and input limits** is the primary approach.

### Illustrative Quantitative Comparison

A 10-million-line file, where each line is only a few characters long, still requires creating and holding a huge number of `String` elements and list references. Even if the text byte count on disk is not huge, the required heap can exceed the JVM's `-Xmx` limit. This is an **observation about trends and overhead**, not a promise of a specific RAM figure; to measure actual usage you must profile on your specific JDK and data.

`Files.size(path)` returns the filesystem metadata size (in bytes) at a single point in time; it **does not accurately predict `readAllLines` heap usage**, does not account for string overhead, and does not guarantee the file won't change after the check.

## 4. Comparing Three Ways to Read Lines

| Criterion | `Files.readAllLines(path, cs)` | `Files.lines(path, cs)` | `Files.newBufferedReader(path, cs)` |
| --- | --- | --- | --- |
| Result | `List<String>` | `Stream<String>` | `BufferedReader` |
| Model | Reads everything before returning | Lazy on-demand reading/traversal stream | Loop reading line by line |
| Stores all lines? | **Yes** | Not required, depends on pipeline | Not required, depends on code |
| Can take only the first few lines? | Already read everything | Can use `limit(n)`, though may pre-read partially | Can break out of the loop |
| Resource to close | Method finishes reading/closing before returning | **Must close Stream** via `try-with-resources` | **Must close Reader** via `try-with-resources` |
| Random index access after reading | Yes: `list.get(i)` | Not directly | Not directly |
| Suitable scenarios | Small/bounded files needing retained lines | Filtering/counting/transforming line by line | Loop-based parsers, fine-grained control logic |
| Pitfall | Heap grows with the entire file | `toList()`/`collect(...)` can still pull everything into RAM | Manually accumulating all lines causes the same issue |

`Files.lines` and `BufferedReader` may pre-read into buffers, but typically **do not need to retain all processed lines**. However, they do not guarantee constant memory consumption in every situation: **a single extremely long line** can still cause `readLine()` to allocate a huge string; operators like `sorted()`, `distinct()`, `toList()`, or storing results in a `List` can also retain large amounts of data.

**API selection rule:** If you need random access or multiple passes over a small file, `readAllLines` is convenient. If you only need to aggregate, filter, process line by line, and discard already-used content, `Files.lines` or `BufferedReader` is usually more appropriate.

## 5. Using `Files.lines()` for Stream Processing

`Files.lines(path, charset)` returns a `Stream<String>` for processing via `filter`, `map`, `limit`, `count`, and `forEach`. Streams are lazy: intermediate operations do not execute until a *terminal operation* runs. Consuming the file source typically happens as the pipeline executes, without waiting to read the entire file before yielding data.

### Java 17+ Program: Counting Warning Lines

Save as **`StreamLinesDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class StreamLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("stream-lines-", ".txt");

        try {
            Files.writeString(file,
                    "INFO started\nWARN low\nWARN high\nINFO done\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long warnings = lines
                        .filter(line -> line.startsWith("WARN "))
                        .count();

                System.out.println("warnings = " + warnings);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run:

```bash
javac StreamLinesDemo.java
java StreamLinesDemo
```

Output:

```text
warnings = 2
```

**Analysis:**

- `lines.filter(...)` constructs the pipeline description, while `count()` triggers traversal and counting.
- There is no `List<String>` holding all four lines. The program only needs to retain the counter state and the item currently being processed.
- A `Stream<String>` opened from a file holds an underlying I/O resource: **you must close it** using `try-with-resources`, even when using `limit(1)` or when an error occurs during processing.
- A `Stream` can only be consumed by a pipeline once. If you need to scan the file again, open a new `Files.lines(...)` or choose a bounded caching strategy.
- I/O errors occurring while traversing the stream may be wrapped in `UncheckedIOException` instead of appearing only when calling `Files.lines`. Remember to handle errors per your application design.

**Watch out:** Replacing `count()` with `toList()` or `collect(Collectors.toList())` builds a collection holding all collected results. Even though the input comes from a lazy API, **all results can still end up on the heap**.

Anti-pattern example:

```java
// Illustrative only, not a standalone program.
try (Stream<String> stream = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> all = stream.toList(); // Still collects all lines into RAM.
}
```

`Files.lines` is not an "OOM shield" if the downstream pipeline actively retains all data.

## 6. Using `Files.newBufferedReader()` for Controlled Loops

If you need a parser with complex state, stop conditions, per-line counting, or position-based error handling, `BufferedReader` is a readable choice:

```java
// Illustrative snippet: path exists, handle IOException at the call site.
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line); // Application method, not shown in this snippet.
    }
}
```

`readLine()` returns `null` at EOF. A valid empty line returns `""`, **not `null`**. The loop condition must check `!= null`, not `!line.isEmpty()`, to avoid stopping prematurely on an empty line.

### Java 17+ Program: Reading 10,000 Lines While Keeping Only Counters

Save as **`BufferedCounterDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedCounterDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("counter-lines-", ".txt");

        try {
            try (BufferedWriter writer =
                         Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                for (int i = 0; i < 10_000; i++) {
                    writer.write(i % 10 == 0 ? "ERROR " : "INFO ");
                    writer.write(Integer.toString(i));
                    writer.newLine();
                }
            }

            int total = 0;
            int errors = 0;

            try (BufferedReader reader =
                         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    total++;
                    if (line.startsWith("ERROR ")) {
                        errors++;
                    }
                }
            }

            System.out.println("lines = " + total);
            System.out.println("errors = " + errors);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run:

```bash
javac BufferedCounterDemo.java
java BufferedCounterDemo
```

Output:

```text
lines = 10000
errors = 1000
```

Even though the file has 10,000 lines, the program does not build a `List<String>` containing them. The loop only holds the current line and two counters. `BufferedWriter` is closed before the program starts reading, ensuring data has been flushed and closed to the file.

**Limitation:** If a single line is very long, `BufferedReader.readLine()` still has to create a `String` containing that entire line. For untrusted input that may contain multi-GB lines or files without newlines, strict memory control requires designing a chunked parser with explicit byte/character limits, rather than merely swapping `readAllLines` for `readLine()`.

## 7. Can You Check `Files.size()` Before Using `readAllLines`?

You can check the file size before calling an eager-read method to reduce the risk of accidentally loading an oversized file:

```java
// Illustrative snippet; requires importing java.nio.file.Files/Path,
// java.nio.charset.StandardCharsets, java.io.IOException, and java.util.List.
static List<String> readSmallText(Path path) throws IOException {
    long maxBytes = 1_000_000L;

    if (Files.size(path) > maxBytes) {
        throw new IOException("file exceeds configured size limit");
    }
    return Files.readAllLines(path, StandardCharsets.UTF_8);
}
```

This pattern fits **regular, stable files with business-defined size bounds**, but do not treat it as absolute resource protection:

1. `Files.size(path)` is the filesystem size at one moment; the file can **change between check and read** (TOCTOU).
2. Size in **bytes** does not equal the memory needed to construct `List<String>`. A file with many short lines still creates many objects.
3. Some special sources/filesystems may report uninformative sizes or change while being read.
4. An untrusted filename/path can be affected by symbolic links or access permissions; you must validate paths and file operations per specific security requirements.
5. A program concurrently processing many files—even if each is small—can still consume a lot of heap.

For large or untrusted sources, use **incremental processing**, limits on total bytes/lines, line count, individual line length, execution time, and appropriate quotas. If strict enforcement is mandatory, apply limits **during reading**, not only via prior metadata checks.

## 8. Charsets, Blank Lines, and Newline Characters

### Charset Must Match Actual Data

`Files.readAllLines(path)` defaults to UTF-8. If the file was saved with another charset (e.g., Windows-1258 or UTF-16LE), you must specify the right charset:

```java
// Illustrative snippet, assuming path is already declared.
List<String> lines =
        Files.readAllLines(path, StandardCharsets.UTF_16LE);
```

Using the wrong charset can cause reading to fail due to invalid byte sequences or produce garbled characters even if it succeeds. For UTF-16 data with a BOM, BOM/endianness handling also depends on the chosen charset; do not infer everything solely from the filename extension.

### Keep or Strip Line Terminators?

`readAllLines` returns strings **without** line separators. For example, the input may mix `\r\n` and `\n`, but once `List<String>` is returned, you no longer have exact information on which terminator each line used. Calling `String.join(System.lineSeparator(), lines)` creates **a new representation**, not an exact restoration of the original bytes.

If you need verbatim comparison, checksum computation, binary protocol parsing, or exact line-ending preservation, work with bytes and explicit charsets according to the format; do not call `readAllLines` and assume the result still retains the original separators.

### Blank Lines and End of File

- Empty file: the list has zero elements.
- Two consecutive newlines after a line: can produce a blank line in the middle.
- A single newline terminating the last line: does not automatically append a trailing blank line after EOF.
- `BufferedReader.readLine()` returns `null` at EOF; a blank line returns `""`.
- `Files.lines` also yields line content without terminators, matching the line-splitting model of `readAllLines`.

## 9. When Is Using `readAllLines` Still Right?

**Use `readAllLines` when:**

- The text file is **small and reliably bounded**, such as a few-KB list of config keys, test fixture data, or short text needing lookup.
- You need index-based line access repeatedly or random line comparisons.
- You need to inspect or operate on the **entire list** where reading everything upfront is intentional and has predictable cost.
- You want simple code and do not want to keep a read resource open while processing the results.

**Prefer `Files.lines` or `newBufferedReader` when:**

- Dealing with large logs, multi-line CSVs, unknown-size data, or files that may grow continuously.
- The goal is simply counting, filtering, aggregating, or forwarding line by line.
- Only the first few lines are needed, allowing early exit or conditional processing.
- You want to process each line and discard it actively to avoid accumulating results in RAM.

**Choose another API when:**

- You need the **entire text in a single `String`**: `Files.readString(path, charset)` is also an eager-read method with similar memory risks; only the return type differs.
- You need **all bytes verbatim**: `Files.readAllBytes(path)` loads all bytes into memory and is also unsuitable for very large files.
- You need binary reading, massive files, or strict memory limits: process with `InputStream` in chunks, a bounded parser, or a format-appropriate I/O API.
- You need to tail logs or watch a file being appended: do not use `readAllLines` as a continuous change-watching mechanism; design a dedicated incremental reader/monitor.

## 10. Common Mistakes

1. **Reading multi-GB logs with `readAllLines` before filtering.** The program can run out of heap before filtering begins. Use `Files.lines` to filter during traversal.
2. **Thinking `Files.lines(path).toList()` saves heap.** It collects all lines back into a list; laziness at the source does not guarantee low memory when the terminal operation gathers everything.
3. **Forgetting to close `Files.lines`.** The stream holds file resources until closed; use `try-with-resources`, do not rely on GC.
4. **Thinking `BufferedReader.readLine()` processes any data in constant memory.** A single overly long line can still consume huge amounts of memory.
5. **Using `readAllLines` to preserve original newlines.** The method strips line terminators; it is unsuitable for byte-exact round-trips.
6. **Using `String.length()` as the file size.** Java's UTF-16 string length differs from UTF-8 byte size and heap overhead.
7. **Confusing a blank line with EOF.** A blank line is `""`; `BufferedReader.readLine()` returns `null` at EOF.
8. **Relying on `Files.size()` as an absolute guarantee.** Files can change and heap overhead differs from byte size; enforce limits during processing.
9. **Decoding with the wrong charset.** Specify `UTF-8` or the correct charset from metadata or the data contract; do not guess from the file extension.
10. **Thinking a large `-Xmx` replaces streaming design.** Increasing heap only raises the failure threshold and wastes resources; choose the right algorithm.
11. **Retaining results of `map`, `groupingBy`, `sorted` on an unbounded Stream.** Those operations can accumulate lots of data; account for the cost of the entire pipeline, not just the stream source.
12. **Catching `OutOfMemoryError` and treating the read as finished.** This error does not mean the list is complete and can leave the process in an unstable resource state.
13. **Thinking `readAllLines` suits continuously growing files.** It reads up to the provider's EOF at read time, not as a tailing channel; use a dedicated strategy when logs are being appended.

## 11. Quick Decision Table

| Scenario | Recommendation |
| --- | --- |
| Small config file needing frequent `get(i)` | `Files.readAllLines(path, cs)` |
| Counting lines matching a condition in a large file | `try (Stream<String> s = Files.lines(path, cs)) { ... }` |
| Parser needing line positions and explicit state | `try (BufferedReader r = Files.newBufferedReader(path, cs)) { ... }` |
| Reading the first 10 lines of a large file | `Files.lines(...).limit(10)` and close the stream |
| Multi-GB file, only computing a sum | Stream, keeping only the accumulator and minimal state |
| Data that might contain an extremely long line | Chunked parser with line-length constraints |
| Need exact bytes and newlines preserved | `InputStream` or format-appropriate byte API |
| Need a single `String` holding a small file | `Files.readString(path, cs)`, still all in RAM |
| Untrusted user-supplied data | Limit bytes/lines/total processing and validate input |

## 12. Self-Check Questions

**Q1.** Does `Files.readAllLines(path)` return lines lazily one by one like an iterator over an open file?

**Answer:** No. It reads the entire content and returns a `List<String>` containing all read lines.

**Q2.** Is an 80 MB file on disk guaranteed to consume only 80 MB of heap when using `readAllLines`?

**Answer:** No. Memory also includes decoded strings, `String` objects, references and list structures, plus intermediate buffers; consumption depends on the data and the JVM.

**Q3.** Why doesn't `Files.lines(path).toList()` solve the memory issue?

**Answer:** Because even though reading from the file is lazy, `toList()` collects all lines into memory to return the list.

**Q4.** With `BufferedReader`, when does `readLine()` return `null` and when does it return `""`?

**Answer:** `null` means EOF; `""` means a valid blank line was read.

**Q5.** Do you need to close the `List<String>` returned by `readAllLines`?

**Answer:** No. It is just an in-memory list; the method has already finished reading. Conversely, `Stream<String>` from `Files.lines` and `BufferedReader` must be closed.

**Q6.** If a file ends with a trailing newline, does `readAllLines` always add an `""` element at the end of the list?

**Answer:** No. A newline terminating the last line does not create a new empty line after EOF.

**Q7.** When processing external data with strict resource limits, is checking `Files.size(path)` before `readAllLines` sufficient?

**Answer:** Not yet. The file can change, memory overhead does not equal byte size, and some sources have metadata that does not reflect all data. Enforce limits during reading and processing.

## 13. References

- [Java 17 — `Files.readAllLines(Path, Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#readAllLines(java.nio.file.Path,java.nio.charset.Charset))
- [Java 17 — `Files.lines(Path, Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#lines(java.nio.file.Path,java.nio.charset.Charset))
- [Java 17 — `Files.newBufferedReader(Path, Charset)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset))
- [Java 17 — `BufferedReader.readLine()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine())

**Remember:** `Files.readAllLines()` is an **eager** API that holds all lines in a `List<String>` on the heap. It is convenient for small, clearly bounded files. When you only need to traverse/filter/count lines in large files, choose `Files.lines()` or `Files.newBufferedReader()`, close resources promptly, and avoid collecting results back into a giant list.
# Reading Text Lines with Files.lines and BufferedReader.lines

The Java Stream API does not only process data already held in a `List` or an array. Many systems need to traverse logs, CSV files, transaction reports, or configuration data stored on disk. Two common ways to create a `Stream<String>` are `Files.lines(...)` and `BufferedReader.lines()`. Both allow expressing declarative pipelines with `filter`, `map`, `limit`, `reduce`, and `collect`, but they differ significantly in **how the source is opened** and **who is responsible for closing the resource**.

This lesson belongs to the **I/O Sources and Resource Management** chapter of the `JAVA_STREAM_API` module. The focus is on reading lines on demand (*lazy*), choosing a character encoding, distinguishing file-opening exceptions from errors occurring during Stream traversal, combining with terminal operations, and writing leak-free code when stopping early or encountering errors. Understanding the I/O source lifecycle properly is an important prerequisite before optimizing performance or processing in parallel.

The examples below use APIs available since **Java 8**. Some snippets are complete example methods, while others use a `path` or `reader` variable created in an earlier section.

## 1. Two Ways to Create a Stream<String> from Text Lines

### Files.lines: from a file path

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long countLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.count();
    }
}
```

`Files.lines(path, charset)` opens a file-reading source and returns a `Stream<String>`. `Files.lines(path)` is the default overload that uses **UTF-8**. Data is supplied to the Stream on demand when the terminal operation runs, rather than forcing the entire file to be loaded into a list as soon as the Stream is created.

With this source, **the returned Stream is the resource that must be closed**. `try-with-resources` calls `close()` even when the pipeline throws an exception or stops after a `limit` or `findFirst`.

### BufferedReader.lines: from an already-open Reader

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static long countNonBlankLines(Path path) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.lines()
                .filter(line -> !line.trim().isEmpty())
                .count();
    }
}
```

`BufferedReader.lines()` creates a Stream backed by **an existing BufferedReader**. When `Files.newBufferedReader` is used to create the reader, it also opens an I/O resource. Here, `try-with-resources` must **close the reader itself**; you must not assume that calling `count()` or closing the Stream created by `reader.lines()` will automatically close the reader.

The two patterns above both process data line by line, but they have **different resource owners**.

## 2. Quick Comparison Table

| Aspect | `Files.lines(...)` | `BufferedReader.lines()` |
| --- | --- | --- |
| Input | `Path` to a file | An already-open `BufferedReader` |
| Object opening the source | The `Files.lines` method | The code creating `BufferedReader`, such as `Files.newBufferedReader` |
| Result | `Stream<String>` | `Stream<String>` |
| When lines are read | When the pipeline is consumed | When the pipeline is consumed |
| Charset | `Files.lines(path, charset)` or UTF-8 by default | Chosen when constructing the Reader |
| Needs closing | The **Stream** returned by `Files.lines` | The underlying **BufferedReader** |
| Typical closing pattern | `try (Stream<String> lines = Files.lines(...))` | `try (BufferedReader reader = ...)` |
| Exception when opening source | `IOException` | `IOException` when opening the Reader |
| I/O exception during traversal | May be `UncheckedIOException` | May be `UncheckedIOException` |
| Parallel usability | Depends on source properties, charset, operations | Should not assume reading a Reader splits effectively |
| Suitable use case | Reading directly from a file by path | Already have a Reader, need configuration control or Reader API integration |

The easiest mistake to make: **closing the Stream from `reader.lines()` does not replace closing `reader`**. Conversely, if you receive a `Stream` directly from `Files.lines`, the owner of that Stream must close it.

## 3. Lazy I/O: Declaring a Pipeline Does Not Mean Reading the Whole File

A Stream has intermediate operations such as `filter`, `map`, `peek`, and `limit`. Assembling these steps usually does not run the lambdas yet; a terminal operation such as `count`, `collect`, `findFirst`, or `forEach` triggers consumption.

```text
Path
  |
  +-- Files.lines(path, UTF_8) -> Stream<String>
                                     |
                                     +-- filter(...)
                                     |
                                     +-- map(...)
                                     |
                                     +-- limit(10)
                                     |
                                     +-- collect(...)  [terminal]
                                     |
                                     v
                                List<String>
```

Example when only the first five lines are needed:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> readFirstFive(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines.limit(5).collect(Collectors.toList());
    }
}
```

`limit(5)` allows the pipeline to complete once five lines have been received, without eagerly materializing the entire file into a list. However:

- `Files.lines` **already opens the resource** as soon as it is called; "lazy" here refers to **supplying lines**, not a guarantee that the file is not yet open.
- You must not infer the exact number of physical reads from the number of emitted elements: buffering, decoders, and the implementation may read data ahead.
- `try-with-resources` is still necessary even when taking only a single line.
- If `limit(0)` or another operation causes the pipeline to request no elements, the opened source still has to be closed.

Do not use `peek` to implement business logic that must run for every line. Depending on the pipeline structure and optimizations, not every element is guaranteed to pass through `peek` before the terminal operation returns.

## 4. How Are Text Lines Split and Returned?

With both APIs, each element in the Stream is **the content of a single line of text**, excluding line-termination characters. Common line terminators recognized include:

- `\n` (line feed);
- `\r` (carriage return);
- `\r\n` (carriage return followed by line feed).

For example, for a file with content equivalent to:

```text
alpha
beta
gamma
```

The Stream can emit `"alpha"`, `"beta"`, and `"gamma"` in order. There is no need to call `split("\n")` on each element.

Blank lines can still produce an empty string and are not skipped by default. If a line contains only whitespace, `line.isEmpty()` returns `false`; you can use:

```java
.filter(line -> !line.trim().isEmpty())
```

`trim()` has existed since Java 8 and strips whitespace at both ends according to its own rules; it is not a full normalization solution for all Unicode whitespace characters. Java 11 introduced `String.isBlank()` and `String.strip()`, but those methods cannot be used if a project compiles strictly against Java 8.

If the data is CSV with quoted fields, commas inside a cell, or a text cell containing newline characters, **one physical line does not necessarily correspond to one CSV record**. `Files.lines` and `BufferedReader.lines` only provide text lines, not a full CSV parser.

## 5. Charset: Decoding Bytes into Characters Correctly

Files store **bytes**, while the Stream returns **character strings**. Therefore, you need to use a character encoding matching the stored data.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEachOrdered(System.out::println);
}
```

The equivalent for choosing a charset with a Reader:

```java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    reader.lines().forEachOrdered(System.out::println);
}
```

Choosing a charset is a **decision about file format**, not an option to "fix garbled text" by guessing at random. A Vietnamese file saved in UTF-8 should be decoded as UTF-8; if a file genuinely uses a legacy encoding, you must determine the exact charset before parsing the data.

With an incompatible charset, decoding may fail with an I/O exception (which may be wrapped in an `UncheckedIOException` during traversal), or produce wrong results if the bytes still form valid strings with incorrect meaning. You should not catch every decoding error and silently drop lines; doing so can cause statistics to miss data.

**BOM (byte-order mark)** and other control characters are part of the data/format and must be handled according to the source specification. Do not assume every UTF-8 file has a BOM, or that every line-reading method automatically strips a leading BOM. If a system must accept multiple formats, build an explicit input validation and normalization step.

## 6. The Most Important Lifecycle Difference: Who Closes What?

### 6.1. Files.lines: Close the Returned Stream

```java
static long countErrors(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

This is the **correct** pattern: the Stream is opened within the `try` scope and closed after computation, even if `filter` or `count` fails.

**Wrong** pattern:

```java
// WRONG: the stream from Files.lines may hold an unclosed resource.
static long countErrorsLeaky(Path path) throws IOException {
    return Files.lines(path)
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
```

`count()` consumes the pipeline, but it **does not automatically call `Stream.close()`**. Likewise, `collect`, `findFirst`, and `forEach` do not automatically close the source resource.

### 6.2. BufferedReader.lines: Close the Reader

```java
static long countErrorsWithReader(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.lines()
                .filter(line -> line.startsWith("ERROR"))
                .count();
    }
}
```

Here `reader.lines()` returns a Stream that reads from the state of `BufferedReader`. Closing the Reader via `try-with-resources` is the required resource-release operation.

**Wrong** pattern:

```java
// WRONG: closing this Stream does not replace closing the BufferedReader.
static long countErrorsWrongClose(Path path) throws IOException {
    BufferedReader reader = Files.newBufferedReader(path);
    try (Stream<String> lines = reader.lines()) {
        return lines.filter(s -> s.startsWith("ERROR")).count();
    }
}
```

When `reader.lines()` does not attach a separate close handler for the Reader, `lines.close()` does not automatically call `reader.close()`. As a result, the underlying Reader resource can remain open.

If you want to own both the `BufferedReader` and a child Stream in the same block, you can write:

```java
try (BufferedReader reader = Files.newBufferedReader(path);
     Stream<String> lines = reader.lines()) {
    // process lines...
}
```

However, the Reader is the critical resource that must be closed; declaring the Stream as well does not change that ownership. Java closes resources in a `try` header **in reverse order**: `lines` first, then `reader`.

### 6.3. When the Reader Is Passed In from Elsewhere

Not every method that accepts a `BufferedReader` should close the Reader itself. For example:

```java
// Illustrative contract: the method does NOT own the passed-in reader.
static long countWarnings(BufferedReader reader) {
    return reader.lines()
            .filter(line -> line.startsWith("WARN"))
            .count();
}
```

The method above neither opens the Reader nor closes it. The place that creates the Reader should manage its lifecycle externally:

```java
try (BufferedReader reader = Files.newBufferedReader(path)) {
    long totalWarnings = countWarnings(reader);
    System.out.println(totalWarnings);
}
```

API design should clearly document **who opens, who closes, and who is allowed to read**, especially when multiple functions share the same Reader object. You must not concurrently call `readLine()` or another `lines()` pipeline on the same Reader while a terminal operation is reading. After a `BufferedReader.lines()` terminal operation finishes, the API also does not guarantee that the Reader is positioned at a specific convenient offset for a subsequent read pass.

## 7. Returning a Stream from a Method: Ownership Transfer

A method returning a `Stream<String>` from `Files.lines` is not inherently wrong, but it **transfers closing responsibility to the caller**.

```java
// Caller MUST close the returned Stream.
static Stream<String> openTextLines(Path path) throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

static void printFirstLine(Path path) throws IOException {
    try (Stream<String> lines = openTextLines(path)) {
        lines.findFirst().ifPresent(System.out::println);
    }
}
```

If the caller forgets `try-with-resources`, the file may remain open. A public API returning an I/O Stream should clearly document its lifecycle and single-use requirement.

**Do not return a Stream from an already-closed Reader:**

```java
// WRONG: the Reader is closed before the caller consumes the lazy Stream.
static Stream<String> brokenLines(Path path) throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(path)) {
        return reader.lines();
    }
}
```

When the caller runs a terminal operation, `reader` is already past its lifetime, so reading may fail.

For a method that only needs to return an aggregated result or a small subset of data, it is usually easier to manage if you **consume the Stream right inside `try`** and return the computed result:

```java
static java.util.List<String> firstTenValidLines(Path path)
        throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .limit(10)
                .collect(java.util.stream.Collectors.toList());
    }
}
```

This method returns a materialized `List<String>` that no longer depends on an open resource. Of course, if you intend to read an entire very large file into a List, memory cost can be high; you must balance a safe API against streaming needs.

## 8. Handling Exceptions at Open Time and Traversal Time

There are two common points where failures occur:

| Stage | Example | Exception type to watch for |
| --- | --- | --- |
| Opening the source | File does not exist, missing read permission, invalid path | `IOException` or a subclass |
| Consuming the Stream | I/O failure while fetching the next line | `UncheckedIOException` (wrapping `IOException`) |
| Transforming content | `Integer.parseInt("abc")` | `NumberFormatException`, not `UncheckedIOException` |
| Caller code | Predicate throws `IllegalArgumentException` | Exceptions from application logic |
| Closing the resource | Reader or Stream close fails | May be `IOException` or an exception appropriate to the resource |

Example distinguishing file-read errors from data-format errors:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

static long sumNumberLines(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .mapToLong(Long::parseLong)
                .sum();
    } catch (UncheckedIOException ex) {
        throw ex.getCause(); // convert read error back to IOException
    }
}
```

Notable behaviors:

- Errors at `Files.lines(...)` can directly throw `IOException`.
- Read errors while the terminal `sum()` traverses the source can throw `UncheckedIOException`; the example unwraps it back to `IOException` so the caller handles it per the method contract.
- A line containing `"abc"` throws `NumberFormatException`. The method above does **not** automatically skip malformed lines: if you need to skip, record, or stop on format errors, specify that policy explicitly.
- The `try-with-resources` block closes the Stream in both normal and exceptional cases. If both the main operation and closing fail, Java uses *suppressed exceptions* to preserve the close failure alongside the primary exception.

Do not use `catch (Exception ex) { return 0; }` for aggregation tasks. Doing so makes a corrupted file or dirty data look like a valid file whose sum is 0.

### Reading Invalid Lines While Continuing

If the requirement is to accept valid numeric lines and skip unparseable ones, you can define a helper returning `OptionalLong`. With Java 9+, `OptionalLong.stream()` allows direct flattening; Java 8 requires another approach.

One Java 8 option, solely to illustrate the business logic:

```java
import java.util.OptionalLong;

static OptionalLong parseLongSafely(String line) {
    try {
        return OptionalLong.of(Long.parseLong(line.trim()));
    } catch (NumberFormatException ex) {
        return OptionalLong.empty();
    }
}
```

However, turning all invalid lines into `OptionalLong.empty()` can **lose the audit trail of bad data**. If auditing is required, preserve line numbers, error details, and the count of skipped lines in an explicit result model rather than scattering side effects inside `peek`.

## 9. Practical Example: Reading Logs, Filtering, and Counting Errors

Suppose a log file contains lines like:

```text
INFO start
WARN low-memory
ERROR connection-failed
ERROR request-timeout
INFO stop
```

Task: count lines starting with `"ERROR "` and extract at most the first five error messages.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> firstFiveErrors(Path path) throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> line.startsWith("ERROR "))
                .map(line -> line.substring("ERROR ".length()))
                .limit(5)
                .collect(Collectors.toList());
    }
}
```

Each step has a distinct meaning:

1. `Files.lines` opens the file and creates the line Stream source.
2. `filter` keeps lines starting with the error prefix. This check does not require loading the entire file into a List.
3. `map` extracts only the message after the prefix.
4. `limit(5)` keeps at most five **error lines**, not the first five lines of the entire file.
5. `collect` triggers the pipeline; `try` always closes the source afterward.

If you changed the order to `lines.limit(5).filter(...)`, you would inspect only the **first five lines of the file**, potentially getting fewer than five errors even when more errors exist later. Operation order is part of the statistical meaning.

To only count errors, you can use `filter(...).count()`; to group errors by code, you can use `Collectors.groupingBy` with an appropriate classifier. Those collectors avoid retaining every record when only per-group counts are needed, though the Map still consumes memory proportional to the number of distinct keys.

## 10. Practical Example: Reading Simple CSV Line by Line

Suppose a simple text file has each line formatted as `code,value`, with no quoted commas and no records spanning multiple lines:

```text
C01,10
C02,20
C01,5
```

We want to compute totals by code:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> totalsByCode(Path path)
        throws IOException {
    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> !line.trim().isEmpty())
                .map(line -> line.split(",", -1))
                .collect(Collectors.toMap(
                        parts -> parts[0].trim(),
                        parts -> Long.parseLong(parts[1].trim()),
                        Long::sum
                ));
    }
}
```

The example intentionally assumes **every non-empty line has exactly two columns**, a non-empty code, and a valid integer in the second column. If a line is missing a column, `parts[1]` causes `ArrayIndexOutOfBoundsException`; if the value is not numeric, `parseLong` causes `NumberFormatException`. In a real program, you should validate the column count, code, overflow risk, and line-numbered error reporting policy.

`Long::sum` adds values when the same code appears multiple times; `toMap` needing a merge function is independent of whether data is read with `Files.lines` or `BufferedReader.lines`.

This is **not a full CSV parser**. When data contains commas inside quoted strings, escape characters, or multiline fields, use a format-compliant CSV parser instead of `String.split`.

## 11. Should You Convert an I/O Source to a Parallel Stream?

The syntax allows it:

```java
try (Stream<String> lines = Files.lines(path)) {
    long matches = lines
            .parallel()
            .filter(line -> expensivePureCheck(line))
            .count();
}
```

The snippet above is an **outline**; `expensivePureCheck` represents a pure, side-effect-free check function provided by the application.

Whether speedup occurs depends on several conditions:

- Is disk reading or decoding the bottleneck?
- Can the Stream source split work effectively? `Spliterator` characteristics depend on implementation and charset.
- Is the transformation CPU-intensive enough to offset splitting/merging overhead?
- Does the result require encounter order? Operations like `findFirst`, `forEachOrdered`, and ordered collection can incur coordination overhead.
- Is a Reader or mutable object shared across lambdas? If so, contention and ordering bugs increase.

Do not assume `BufferedReader.lines().parallel()` can read parts of a single Reader independently like separate files. `BufferedReader` is a stateful input stream; concurrent operations directly on the same Reader are not a safe speedup strategy.

In many applications, a simpler and more controllable approach is to **read sequentially, perform lightweight per-line processing, and only offload heavy CPU work to an explicitly designed pipeline or queue**. Still, you should not claim it is always faster; when optimization is needed, measure on actual file sizes, hardware, charsets, and JDKs.

## 12. Memory Limits: Streaming Does Not Mean Zero Memory Usage

`Files.lines` and `BufferedReader.lines` avoid reading all lines into a `List` up front, but downstream operations can still cause memory usage to grow significantly.

| Pipeline | Memory characteristics |
| --- | --- |
| `filter(...).count()` | Does not need to retain all filtered elements |
| `mapToLong(...).sum()` | Keeps a small aggregate result, not every line |
| `limit(10).collect(toList())` | Holds at most 10 output strings (excluding source buffering) |
| `collect(toList())` over the whole file | Can retain all lines in memory |
| `sorted().collect(toList())` | May require large buffers and lists |
| `distinct().count()` | May need to store the set of seen keys |
| `groupingBy(..., counting())` | Keeps state proportional to the number of groups |
| Default `groupingBy(...)` | Stores lines/records into each group's list |

For very large files, `Files.readAllLines(path)` reads the entire content into a List and is usually not the right choice when you only need to count, filter a few lines, or aggregate directly.

However, for small files, `readAllLines` can be simple enough and still correct; choose the API based on requirements rather than an optimization slogan. I/O resources still need to be closed for file-backed Stream sources even when the pipeline output is very small.

## 13. Common Pitfalls When Working with Streams from a Reader

| Mistake | Why it is dangerous | Fix |
| --- | --- | --- |
| `Files.lines(path).count()` without closing the Stream | Terminal operations do not automatically close the file | `try (Stream<String> lines = Files.lines(path))` |
| `try (Stream<String> lines = reader.lines())` without closing the reader | A Stream from a Reader does not own the Reader | `try (BufferedReader reader = ...)` |
| Returning `reader.lines()` from a `try (BufferedReader reader = ...)` block | The Reader closes before the lazy Stream is traversed | Return a computed result, or transfer ownership explicitly |
| Assuming `Files.lines` reads the entire file when called | Data is read on demand, while the resource is opened up front | Understand lazy traversal and manage open lifetime |
| Calling `reader.readLine()` while the Stream is being consumed | Interferes with Reader state, behavior is not guaranteed | Have only one consumer traverse the data at a time, per contract |
| Reusing a Stream after `count` or `collect` | A Stream is single-use | Create a new source if another processing pass is needed |
| Assuming `limit(5)` closes the source after five lines | Short-circuiting does not replace `close()` | Close the source even on early stop |
| Catching every `Exception` and returning an empty list | Hides broken files, decoding errors, and parse errors | Classify and propagate errors with context |
| Not specifying a charset when the source is not UTF-8 | Characters may be decoded incorrectly | Choose the charset per the source contract |
| `map(String::trim)` treated as a CSV parser | Does not handle quoting, multiline cells, or escapes | Use a dedicated parser for complex data |
| `collect(toList())` on a huge file expecting low RAM usage | The output still holds all the data | Use streaming aggregation or limit output |
| Blindly using `parallel()` with a shared Reader | Splitting efficiency and state safety are not guaranteed | Benchmark and avoid shared mutable state |
| `forEach` on parallel expecting file order | `forEach` does not preserve encounter order | Use `forEachOrdered` if exact order is required |

## 14. Checklist When Designing a Line-Reading API

Before putting a file-processing pipeline into an application, answer these questions:

1. **Which source is appropriate?** If you have a `Path` directly, `Files.lines` is usually concise; if the system already owns a Reader, use `BufferedReader.lines`.
2. **Who opens and who closes?** `Files.lines` -> close the Stream; `BufferedReader.lines` -> close the Reader. State the contract clearly when passing/returning sources.
3. **Which charset is right?** Follow the format and the data provider's contract.
4. **What should happen with blank or malformed lines?** Filter intentionally, record errors, or fail; avoid silently ignoring them.
5. **Must line order be preserved?** If yes, preserve encounter order and be careful with parallel, `unordered`, and `forEach`.
6. **Can it stop early?** `limit`, `findFirst`, and `anyMatch` can avoid processing everything, but they do not close the source automatically.
7. **Could the result consume too much memory?** `collect(toList())`, `sorted`, `distinct`, and grouping grow memory with the data.
8. **What errors can occur during traversal?** Besides `IOException` on open, watch for `UncheckedIOException` and parser/predicate errors.
9. **Does the Stream need to leave the method?** If so, callers must know it is a single-use resource that must be closed.
10. **Have empty sources and mid-file errors been tested?** Especially if a reporting function returns a sum or list that could be mistaken for a valid empty result.

## 15. Self-Check Questions

1. Does `Files.lines(path)` use UTF-8 by default? **Yes**, the overload without a charset uses UTF-8.
2. Does `BufferedReader.lines()` open a file from a Path on its own? **No**, it creates a Stream from an existing Reader.
3. In `try (Stream<String> lines = Files.lines(path))`, which resource is closed? The returned **Stream**, which in turn closes its underlying file source.
4. Does `try (Stream<String> lines = reader.lines())` automatically close the Reader? **No**; you must close the Reader you own.
5. Do `count()`, `findFirst()`, or `collect()` automatically call `close()`? **No**.
6. Why does `limit(5)` still require `try-with-resources`? **Because** the source may already be open, and short-circuiting does not close it automatically.
7. How can file-opening exceptions differ from exceptions while traversing the Stream? **IOException** when opening, **UncheckedIOException** during lazy reading.
8. If `Long.parseLong("abc")` fails, is that an `UncheckedIOException`? **No**, that is a `NumberFormatException`.
9. When reading text lines, is the `\n` character included in the returned line strings? **No**, line terminators are not part of line content.
10. When you only need to count error lines in a large file, do you need `collect(toList())`? **No**, use `filter(...).count()` to avoid storing all lines.
11. Why must `BufferedReader.lines()` not be used simultaneously with `reader.readLine()`? **Because** both mutate the Reader's state and break the traversal contract.
12. Is a method that returns a Stream from `Files.lines` without closing it always wrong? **No**, provided the contract clearly states the caller must close it and the caller does so.
13. Is `Files.lines` a CSV parser that supports multiline cells? **No**, it only splits text lines.
14. Can you enable `parallel()` to make file reading faster by default? **No**, effectiveness depends on source, charset, CPU, memory, and coordination overhead.

**Rule of thumb:** `Files.lines` and `BufferedReader.lines` both bring text lines into a lazy Stream pipeline, but **resource ownership is not the same**. Close the Stream opened by `Files.lines`, close the `BufferedReader` when using `reader.lines()`, consume the pipeline while the source is still open, control the charset, and distinguish I/O errors from data errors. Optimizations like `limit`, `collect`, or parallel execution are only valuable when results remain correct and resources are always released.

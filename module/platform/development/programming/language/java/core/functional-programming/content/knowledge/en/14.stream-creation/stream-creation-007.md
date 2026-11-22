# Creating Streams from Files, Text Lines, and Other JDK APIs

## 1. Objectives

In Java, a `Stream` does not only come from a `List`, `Set`, or array. The JDK also provides sources suited to different kinds of data: file contents, lines of text, directory trees, tokens split from text, `Optional` results, generated sequences, and sources supplied via `Spliterator`.

This lesson helps you:

1. Create a Stream from files and text lines using `Files.lines`, `BufferedReader.lines`, and `String.lines`.
2. Traverse files and directories via `Files.list`, `Files.walk`, and `Files.find`, understanding their scope and ordering.
3. Use `Scanner.tokens`, `Pattern.splitAsStream`, and other JDK APIs to create Streams when data is not in a collection.
4. Distinguish Streams that hold I/O resources requiring closing from purely in-memory Streams.
5. Properly handle laziness, I/O errors, single-use lifecycles, memory, ordering, and the limitations of infinite data.
6. Practice with a complete Java 17 program and verify deterministic output.

Key takeaway: a Stream is **a pipeline for processing elements from a source**, not a permanent container for elements. The source can be an existing collection, a file-reading object, or an algorithm that generates elements on demand.

## 2. Families of Stream Sources in the JDK

| Source | How to create | Stream type | Needs closing? | Notes |
| --- | --- | --- | --- | --- |
| Lines in a file | `Files.lines(path, charset)` | `Stream<String>` | **Yes** | Reads when consumed; the Stream holds the file resource |
| Lines from a reader | `reader.lines()` on `BufferedReader` | `Stream<String>` | **Close reader** | The reader is a resource managed by the caller |
| String with line breaks | `text.lines()` | `Stream<String>` | No | Java 11+, processes in-memory text |
| Direct directory entries | `Files.list(directory)` | `Stream<Path>` | **Yes** | Does not traverse subdirectories |
| Directory tree | `Files.walk(directory)` | `Stream<Path>` | **Yes** | Traverses recursively, including the root path |
| Search in a tree | `Files.find(directory, maxDepth, matcher)` | `Stream<Path>` | **Yes** | Matcher receives `Path` and file attributes |
| `Scanner` tokens | `scanner.tokens()` | `Stream<String>` | **Close scanner** | Depends on the delimiter and Scanner source |
| Split by regex | `pattern.splitAsStream(text)` | `Stream<String>` | No | Regex splits an in-memory string |
| Elements in `Optional` | `optional.stream()` | `Stream<T>` | No | `0` or `1` element |
| Nullable value | `Stream.ofNullable(value)` | `Stream<T>` | No | Java 9+, `0` or `1` element |
| Integer range | `IntStream.range(a, b)` | `IntStream` | No | Upper bound is exclusive |
| Algorithmically generated sequence | `Stream.iterate(...)`, `Stream.generate(...)` | `Stream<T>` | Usually no | Can be infinite; requires a limit or termination condition |
| Pseudorandom numbers | `random.ints(...)` | `IntStream` | No | Has finite and infinite overloads |
| Custom source | `StreamSupport.stream(spliterator, false)` | `Stream<T>` | Depends on source | Requires managing its own resource lifecycle |

The "Needs closing?" column describes the application's responsibility for **sources or Streams that own external resources**. Not every Stream needs `close()` called on it. Streams created from `List`, `String.lines()`, or `IntStream.range` normally have no file handle to release.

## 3. `Files.lines`: Reading a File Line by Line

### Syntax and Behavior

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("data.txt");

try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long nonEmpty = lines
            .map(String::strip)
            .filter(s -> !s.isEmpty())
            .count();
    System.out.println(nonEmpty);
}
```

This snippet is illustrative; a `data.txt` file is required to run it. The API has an overload `Files.lines(path)` that defaults to UTF-8; passing `StandardCharsets.UTF_8` makes the encoding contract explicit in code.

Each element is a **line of text without line-terminator characters**. The Stream is only consumed when a terminal operation such as `count`, `toList`, `forEach`, or `collect` executes. You should not treat `Files.lines` as an operation that reads the entire file into a `List` immediately when called. The JDK may hold buffers and resources during traversal.

**Important:** The Stream returned by `Files.lines` holds an I/O resource that must be closed. Use `try-with-resources`, even when the pipeline throws an exception or terminates early:

```java
try (Stream<String> lines = Files.lines(path)) {
    String first = lines.findFirst().orElse("<empty>");
    System.out.println(first);
}
// close() is called when exiting the try block.
```

`findFirst()` does not guarantee closing the Stream by itself; the closing semantics are handled by `try-with-resources`. Do not return an unconsumed Stream from a method after it has already been closed inside `try`; the terminal call at the caller will no longer have access to the source. If your API returns a Stream backed by a resource, it must document the closing responsibility for the caller or design a callback API so the resource stays alive long enough.

### Exceptions While Reading

Opening the file can throw `IOException`. I/O errors during lazy traversal may surface as `UncheckedIOException` from the terminal operation, rather than occurring at Stream creation time. These errors must be propagated or handled according to business policy; do not use an empty `catch` so that the Stream "keeps running".

For very large files, streaming can reduce the need to keep all lines in RAM. However, if the terminal operation ends with `.toList()`, **the results are still collected in memory**. `sorted()` and some stateful operations may also retain large intermediate data. Consider `forEach`, aggregations like `count`/`reduce`, or batch processing when the contract allows.

## 4. `BufferedReader.lines`: When You Already Have a Reader

If the code already owns a `BufferedReader`, call `lines()` to turn the remaining text into a Stream:

```java
try (java.io.BufferedReader reader =
             java.nio.file.Files.newBufferedReader(
                     path, java.nio.charset.StandardCharsets.UTF_8)) {
    long count = reader.lines()
            .filter(line -> !line.isBlank())
            .count();
    System.out.println(count);
}
```

`BufferedReader.lines()` reads from the reader's **current position**; if `readLine()` was called earlier, the Stream does not re-read the already-consumed portion. While the Stream from `lines()` is in use, you should not read directly from the same reader by other means. I/O errors encountered during traversal may be wrapped in `UncheckedIOException`.

Unlike `Files.lines`, the clearest lifecycle responsibility is closing the `BufferedReader` itself. Use `try (BufferedReader reader = ...)`; there is no need to create two independent lifecycles or continue reading the reader after it is closed. If the reader wraps a socket or a special source, closing behavior usually propagates to the underlying resource and must be designed accordingly.

`Files.lines` is the direct approach when you only need a Stream of lines from a file. `BufferedReader.lines` is convenient when a reader already exists or when you need to combine it with other `BufferedReader` read methods, provided operations are not interleaved while the Stream is traversing.

## 5. `String.lines`: Lines of an In-Memory String

Since Java 11, `String.lines()` creates a `Stream<String>` of lines separated by `\n`, `\r`, or `\r\n`:

```java
String text = "first\r\nsecond\n";

List<String> lines = text.lines().toList();
System.out.println(lines); // [first, second]
```

`String.lines()` does not include line terminators in each element. A trailing newline at the end of the string does not automatically produce an extra empty line at the end; an empty string produces a Stream with no elements. Unlike `Files.lines`, the data is already in memory, so the Stream does not need to close a file handle.

Practical use case: parsing data received from an API, response, or preloaded string when you want to process it line by line. If the text is too large, already holding the entire content in a `String` can consume RAM; `String.lines` does not turn that source into direct file reading.

## 6. `Files.list`, `Files.walk`, and `Files.find`: Filesystem Sources

### `Files.list`: One Level Only

```java
try (Stream<Path> entries = Files.list(directory)) {
    List<String> names = entries
            .map(path -> path.getFileName().toString())
            .sorted()
            .toList();
    System.out.println(names);
}
```

`Files.list(directory)` creates a Stream containing the direct entries in the directory: files and subdirectories. It **does not recurse automatically**. There is no general guarantee on the filesystem listing order; if you want deterministic results, use `.sorted()` with your criteria.

### `Files.walk`: Traversing a Directory Tree

```java
try (Stream<Path> paths = Files.walk(directory)) {
    List<Path> regularFiles = paths
            .filter(Files::isRegularFile)
            .toList();
}
```

By default, `Files.walk` starts at the root path itself and traverses entries depth-first, without following symbolic links unless `FileVisitOption.FOLLOW_LINKS` is specified. You can limit the depth:

```java
try (Stream<Path> paths = Files.walk(directory, 1)) {
    // The root path and direct entries (if accessible).
    long pathsAtDepthZeroOrOne = paths.count();
}
```

`Files.walk(directory, 1)` is not completely equivalent to `Files.list(directory)` because `walk` **includes the root path** and handles directory-tree errors differently.

### `Files.find`: Filtering Based on `Path` and Attributes

```java
try (Stream<Path> matching = Files.find(
        directory,
        10,
        (path, attrs) -> attrs.isRegularFile()
                && path.getFileName().toString().endsWith(".txt"))) {
    long txtCount = matching.count();
    System.out.println(txtCount);
}
```

`Files.find` uses a `BiPredicate<Path, BasicFileAttributes>` to decide based on the path and file attributes. When attributes such as `isRegularFile` are needed, this API is useful because it can reuse the attributes already fetched during traversal. `Files.walk(...).filter(...)` is often more readable when those attributes are not needed.

`Files.list`, `Files.walk`, and `Files.find` all create Streams that hold open resources related to directory listing, so **you must close the Stream with `try-with-resources`**. Errors when opening the source are usually checked `IOException`s, while I/O errors during lazy traversal can appear as `UncheckedIOException`.

For very large trees or user-supplied paths, you should set limits on depth, element count, permissions, errors, and symbolic-link following policy. You should not use `.toList()` to collect millions of paths if you only need to count, filter, or aggregate.

## 7. `Scanner.tokens` and `Pattern.splitAsStream`: Turning Text into Tokens

### `Scanner.tokens()`

Since Java 9, `Scanner.tokens()` returns a `Stream<String>` according to the scanner's delimiter.

```java
try (java.util.Scanner scanner =
             new java.util.Scanner("red, blue,green")) {
    scanner.useDelimiter("[,\\s]+");
    List<String> tokens = scanner.tokens().toList();
    System.out.println(tokens); // [red, blue, green]
}
```

Here, commas and whitespace matching the regex rule serve as delimiters. `Scanner` can read from a `String`, `Readable`, `Path`, or input stream. When the scanner owns an I/O source, close the Scanner properly according to its lifecycle; closing the Scanner closes the underlying source if that source is `Closeable`. Do not change the delimiter or interleave other scanner read operations while consuming the token Stream.

**Note:** `Scanner` has many token-parsing features and locale support. It is not simply `String.split`; verify the delimiter, input read errors, and actual token behavior when designing a data parser.

### `Pattern.splitAsStream()`

A compiled `Pattern` can split a string into a Stream:

```java
java.util.regex.Pattern comma =
        java.util.regex.Pattern.compile("\\s*,\\s*");

List<String> parts =
        comma.splitAsStream("red, blue,green").toList();

System.out.println(parts); // [red, blue, green]
```

This operates on an existing string and owns no file resource. `splitAsStream` is useful when you want to chain token splitting with `map`, `filter`, and `flatMap` without building an intermediate list yourself.

Do not assume `Pattern.splitAsStream` is a full CSV parser. CSV text with quotes, commas inside fields, escapes, or multiline records requires a parser that follows the CSV specification.

## 8. Other JDK APIs That Create Streams

### `Optional.stream()` and `Stream.ofNullable()`

`Optional<T>.stream()` yields 0 or 1 element, which is suitable when you need to `flatMap` multiple optional results:

```java
List<String> names = List.of(
        java.util.Optional.of("Lan"),
        java.util.Optional.<String>empty(),
        java.util.Optional.of("Minh"))
        .stream()
        .flatMap(java.util.Optional::stream)
        .toList();

System.out.println(names); // [Lan, Minh]
```

`Stream.ofNullable(value)` has 0 elements if `value == null`, and 1 element if non-null:

```java
String maybeName = null;

long count = Stream.ofNullable(maybeName).count();
System.out.println(count); // 0
```

These two APIs help represent **a potentially absent value**, but they do not classify data errors on their own. If a missing value is an error condition that must be reported, preserve the error information instead of silently discarding all null values.

### Primitive Ranges and `Random`

Specialized Streams such as `IntStream`, `LongStream`, and `DoubleStream` avoid boxing in many numeric operations:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 3).sum();
System.out.println(sum); // 6

long total = new java.util.Random(7)
        .ints(3, 0, 10)
        .count();
System.out.println(total); // 3
```

`rangeClosed(1, 3)` includes both 1 and 3; `range(1, 3)` includes only 1 and 2. `Random.ints(3, 0, 10)` has size 3 and generates values in `[0, 10)`. The `count()` result is 3; you should not rely on side effects in intermediate steps to prove that random numbers were actually generated because a Stream can optimize the pipeline.

### `Stream.iterate`, `Stream.generate`, and `Stream.Builder`

```java
List<Integer> even = Stream.iterate(2, n -> n + 2)
        .limit(4)
        .toList();
System.out.println(even); // [2, 4, 6, 8]

List<String> repeated = Stream.generate(() -> "x")
        .limit(3)
        .toList();
System.out.println(repeated); // [x, x, x]

Stream.Builder<String> builder = Stream.builder();
builder.add("a").add("b");
List<String> built = builder.build().toList();
System.out.println(built); // [a, b]
```

Unbounded `iterate`/`generate` can create infinite Streams. When a terminal operation requires traversing all elements (such as `count()` without a proper stopping condition), the program may never terminate. In addition to the infinite overload, Java 9 provides `Stream.iterate(seed, hasNext, next)` to allow predicate-based termination.

After `build()`, the builder cannot be used to add more elements to the built Stream. Like other Streams, a Stream created from a builder is a single-use object.

### `StreamSupport.stream`: Custom Iterable/Spliterator Sources

```java
Iterable<Integer> values = java.util.List.of(4, 5, 6);

List<Integer> copied = java.util.stream.StreamSupport
        .stream(values.spliterator(), false)
        .toList();

System.out.println(copied); // [4, 5, 6]
```

The `false` argument requests a sequential Stream. `StreamSupport` is the bridge for a source that provides a `Spliterator`, especially when implementing your own data structure or traversal mechanism. Correctness when running in parallel depends on spliterator characteristics such as splittability, ordering, sizing, and concurrency policy. Do not write a custom spliterator if existing high-level APIs already suffice.

If the spliterator reads from a socket, file, or special source, wrapping it into a Stream **does not automatically establish a resource-closing policy**; you usually must add an explicit lifecycle or register an appropriate `onClose` handler and still require the caller to close it.

## 9. Complete Java 17+ Example: Combining File Sources and JDK Sources

The following program creates a temporary directory, writes sample data, processes it with multiple types of Stream sources, closes resources, and deletes the sample data at the end. No manual file preparation or external libraries outside the JDK are required.

Create the file `JdkStreamSourcesDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Random;
import java.util.Scanner;
import java.util.regex.Pattern;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class JdkStreamSourcesDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("jdk-stream-sources-");
        Path notes = directory.resolve("notes.txt");
        Path colors = directory.resolve("colors.txt");
        Path archive = directory.resolve("archive");
        Path oldNote = archive.resolve("old.txt");

        try {
            Files.createDirectory(archive);
            Files.writeString(notes, "  Java  \n\nStream\n",
                    StandardCharsets.UTF_8);
            Files.writeString(colors, "red, blue,green\n",
                    StandardCharsets.UTF_8);
            Files.writeString(oldNote, "Old entry\n",
                    StandardCharsets.UTF_8);

            // Stream owns a file resource: must be closed.
            try (Stream<String> lines =
                         Files.lines(notes, StandardCharsets.UTF_8)) {
                List<String> words = lines
                        .map(String::strip)
                        .filter(s -> !s.isBlank())
                        .toList();
                System.out.println("fileLines=" + words);
            }

            // Reader is a resource that must be closed.
            try (BufferedReader reader =
                         Files.newBufferedReader(
                                 notes, StandardCharsets.UTF_8)) {
                long count = reader.lines()
                        .filter(s -> !s.isBlank())
                        .count();
                System.out.println("readerCount=" + count);
            }

            // Lines from an in-memory string, no file handle.
            List<String> memoryLines =
                    "first\r\nsecond\n".lines().toList();
            System.out.println("stringLines=" + memoryLines);

            // Files.list: direct entries only.
            try (Stream<Path> entries = Files.list(directory)) {
                List<String> names = entries
                        .map(path -> path.getFileName().toString())
                        .sorted()
                        .toList();
                System.out.println("list=" + names);
            }

            // Files.walk: includes files inside the archive directory.
            try (Stream<Path> paths = Files.walk(directory)) {
                List<String> names = paths
                        .filter(Files::isRegularFile)
                        .map(directory::relativize)
                        .map(Path::toString)
                        .map(path -> path.replace('\\', '/'))
                        .sorted()
                        .toList();
                System.out.println("walkFiles=" + names);
            }

            // Files.find: filters using Path and BasicFileAttributes.
            try (Stream<Path> matching = Files.find(
                    directory, 5,
                    (path, attrs) -> attrs.isRegularFile()
                            && path.getFileName().toString()
                                    .endsWith(".txt"))) {
                System.out.println("findTxtCount=" + matching.count());
            }

            // Scanner manages the lifecycle of the reader it wraps.
            try (Scanner scanner = new Scanner(
                    Files.newBufferedReader(
                            colors, StandardCharsets.UTF_8))) {
                scanner.useDelimiter("[,\\s]+");
                System.out.println(
                        "tokens=" + scanner.tokens().toList());
            }

            Pattern comma = Pattern.compile("\\s*,\\s*");
            System.out.println("pattern="
                    + comma.splitAsStream("one,two, three").toList());

            System.out.println("range="
                    + IntStream.rangeClosed(1, 3).boxed().toList());

            System.out.println("generatedCount="
                    + new Random(7).ints(3, 0, 10).count());

            System.out.println("nullableCount="
                    + Stream.ofNullable((String) null).count());
        } finally {
            // Delete children before parent, even if processing fails.
            Files.deleteIfExists(oldNote);
            Files.deleteIfExists(archive);
            Files.deleteIfExists(colors);
            Files.deleteIfExists(notes);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run on JDK 17 or newer:

```bash
javac JdkStreamSourcesDemo.java
java JdkStreamSourcesDemo
```

Expected stdout (the random temporary path is not printed; the order is sorted):

```text
fileLines=[Java, Stream]
readerCount=2
stringLines=[first, second]
list=[archive, colors.txt, notes.txt]
walkFiles=[archive/old.txt, colors.txt, notes.txt]
findTxtCount=3
tokens=[red, blue, green]
pattern=[one, two, three]
range=[1, 2, 3]
generatedCount=3
nullableCount=0
```

Notes:

- `Files.list` sees `archive` as a direct entry, but does not automatically list `old.txt` inside it. `Files.walk` traverses deeply and after filtering for regular files includes `archive/old.txt`.
- `map(path -> path.replace('\\', '/'))` only normalizes **the printed string for demonstration** across Windows/Linux; it does not replace Java's `Path` handling.
- Sorting with `.sorted()` keeps the output of `list`/`walk` stable, because directory listing order is not guaranteed.
- `Files.find` counts three `.txt` files, including one file in `archive`.
- Each file/directory Stream lives strictly within a `try-with-resources` block. For Scanner, the `try` block closes the Scanner and the reader owned by the Scanner.
- `finally` cleans up the temporary directory; this part is for a demo with a known structure and known filenames. With real files, do not automatically delete source data after processing.
- If deleting temporary data fails, `IOException` from cleanup may be thrown; the demo program does not ignore errors to pretend everything succeeded.

## 10. Performance, Lifecycle, and Safety Rules

### Do Not Reuse the Same Stream

```java
Stream<String> lines = "a\nb".lines();
long count = lines.count();
// lines.toList(); // Invalid: the Stream has already been consumed.
```

To process again, create a new Stream from a repeatable source. For files, each `Files.lines(...)` call opens a new source and must be closed separately. For a reader that has already been read to the end, calling `lines()` again does not make old content reappear; if you need to re-read the file, open a new reader.

### Avoid Resource Leaks with I/O Sources

Dangerous pattern:

```java
// Avoid: Stream from Files.lines has no explicit closing scope.
// List<String> lines = Files.lines(path).toList();
```

Even after the terminal operation finishes, you should not rely on the garbage collector to clean up file descriptors. Wrap `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` in `try-with-resources`. With `Scanner` and `BufferedReader`, close the resource-owning object.

### Do Not Assume All Data Is Always Read

A pipeline such as `findFirst`, `anyMatch`, or `limit` can stop early. For example:

```java
try (Stream<String> lines = Files.lines(path)) {
    boolean hasHeader = lines.anyMatch(s -> s.startsWith("HEADER"));
}
```

If the header is found early, the Stream may not read subsequent lines. `close()` still needs to happen. Avoid relying on side effects in `peek` or `map` as if every element is guaranteed to be visited.

### Do Not Conflate Source-Creation Errors with Traversal Errors

`Files.lines(path)` can fail immediately when opening the file and throw `IOException`. Once you have a Stream, deferred read errors can arise at the terminal operation as `UncheckedIOException`. If you need to apply retry policies or report errors, distinguish these two phases; do not `catch (Exception ignored)` and return an empty list.

### Do Not Assume Every Stream Is Ordered

Line-based file sources usually preserve text order. `Files.list` does not guarantee listing order by name; use `.sorted()` if deterministic results are required. `findAny`, especially in a parallel Stream, is not synonymous with `findFirst`. Sources from `HashSet`, custom splitters, or generators may have different ordering characteristics.

### Do Not Arbitrarily Modify the Source While a Stream Is Active

While traversing a directory, creating or deleting entries directly at the source can make listing results inconsistent; a Stream does not guarantee an immutable snapshot. For files whose contents are written concurrently by another process, how data is observed depends on the filesystem, buffering, and specific contracts. When consistency is needed, the application must use an appropriate snapshot, transaction, or synchronization.

### Consider Depth and Symlinks When Traversing Trees

`Files.walk` does not follow symbolic links by default. Enable `FOLLOW_LINKS` only when truly necessary and after considering permissions, cyclic trees, depth, and I/O limits. `Files.find` has a mandatory `maxDepth` parameter; if deep traversal is not needed, set a small limit to avoid going out of scope.

### Do Not Use Streams to Replace Dedicated Parsers

`Files.lines` provides lines; it does not understand multiline CSV, JSON, YAML, or escaped data formats. `Scanner.tokens` and `Pattern.splitAsStream` are useful for simple splitting rules; for complex structured data, you need a spec-compliant parser, the proper charset, and position-aware error reporting.

## 11. Which API to Choose for Each Requirement?

| Requirement | Appropriate API | Reason |
| --- | --- | --- |
| Filter/count lines in a large file | `Files.lines` + terminal aggregate | Avoids holding all lines in a List if unnecessary |
| Already have a reader for a file/socket | `BufferedReader.lines` | Uses the reader's current position and closes the owner |
| Split lines of an already-loaded String | `String.lines` | No need to create a reader or file handle |
| List immediate files/dirs in a single directory | `Files.list` | No need to recurse |
| Traverse an entire directory tree | `Files.walk` | Supports depth, subpaths, and file/dir filtering |
| Search by file metadata | `Files.find` | Matcher receives attributes alongside the path |
| Split tokens by delimiter | `Scanner.tokens` | Leverages Scanner's token configuration |
| Split a string with an existing regex | `Pattern.splitAsStream` | Chains into a pipeline without creating an intermediate List |
| Flatten multiple Optionals | `flatMap(Optional::stream)` | Turns `0 or 1` values into Stream elements |
| Number sequence without an input List | `IntStream.range`/`rangeClosed` | Generates elements over a numeric range |
| Self-generated data | `Stream.iterate`/`generate` | Generates algorithmically; requires termination control |
| Custom Iterable/Spliterator source | `StreamSupport.stream` | Used when high-level APIs do not suffice |

## 12. Exercises and Self-Check Criteria

1. Create a UTF-8 file containing three lines: `" Java "`, a blank line, and `"Stream"`. Use `Files.lines` with `try-with-resources` to produce `List.of("Java", "Stream")`. Explain where the resource is closed.
2. Given a directory containing `a.txt`, `b.csv`, and a subdirectory `archive/c.txt`, compare the results of `Files.list`, `Files.walk`, and `Files.find` when selecting only `.txt` files and sorting by relative path.
3. Use `BufferedReader.lines` after one call to `reader.readLine()`. Predict which lines the Stream sees; explain why other read operations should not be mixed in while the Stream is traversing.
4. Given the string `"A\r\nB\n"`, use `String.lines` to obtain a list; try adding one more newline to observe the element count.
5. Use `Pattern.compile("\\s*,\\s*").splitAsStream("a, b,c")` followed by `.map(String::toUpperCase).toList()`; predict `[A, B, C]`.
6. Use `Optional.of("ok").stream()` and `Optional.empty().stream()`; combine both via `Stream.of(...).flatMap(Optional::stream)` and explain why there is one element.
7. Create `Stream.iterate(2, n -> n + 2).limit(5)` and compute the sum without calling `toList()`. The expected result is `30`.
8. Describe why `Files.lines(path).findFirst()` is not proper resource management if the Stream is not closed, even when a result has already been found.

When self-evaluating, always answer four questions: **Where does the data source live? When are elements supplied? Who closes the resource? What result does the terminal operation produce?** Answering these four questions correctly helps you choose the right Stream source, avoid file handle leaks, avoid reading unnecessary data, and avoid confusing a pipeline with a storage structure.

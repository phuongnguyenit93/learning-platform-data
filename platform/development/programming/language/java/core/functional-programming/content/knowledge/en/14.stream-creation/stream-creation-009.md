# Closing Resource-Backed Streams with `try-with-resources` in Java

## 1. Why Do Some Streams Need to Be Closed?

`java.util.stream.Stream<T>` describes a declarative data-processing pipeline: source → intermediate operations → terminal operation. A Stream can be created from a collection, an array, provided values, a file, or directory traversal. **Not every Stream owns a resource that must be closed**, but some I/O-backed sources keep a file handle or directory handle open throughout traversal. If those Streams are not closed, the application can leak resources, fail to release handles promptly, and encounter errors when opening more files or working with directories.

In Java, `Stream<T>` inherits closeability from `BaseStream<T,S>`, and `BaseStream` extends `AutoCloseable`. Therefore, you can use the syntax:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines.count();
    System.out.println(count);
}
~~~

This is a **code snippet placed inside a method**, requiring an existing `path` of type `Path`, importing `java.nio.file.Files`, `java.nio.file.Path`, `java.util.stream.Stream`, and handling `IOException`. When the block ends, Java calls `lines.close()` automatically, even if an operation inside the block throws an exception.

**Do not confuse this:** `count()`, `forEach()`, `toList()`, and other terminal operations **do not automatically call `Stream.close()`**. Having the pipeline consume all elements and closing the resource are **two different concepts**.

### Learning Objectives

After this lesson, you can:

- Identify which Streams need to be closed; distinguish in-memory sources from I/O sources.
- Understand the roles of `AutoCloseable`, `Stream.close()`, and `BaseStream.onClose()`.
- Write `try-with-resources` with the right scope when using Streams from `Files.lines`, `Files.list`, `Files.walk`, and `Files.find`.
- Distinguish closing a Stream from consuming a Stream; understand that a terminal operation does not mean the resource has been closed.
- Manage resource lifecycles when a pipeline is lazy, throws exceptions, uses helpers, returns a Stream to a caller, or involves multiple resources.
- Avoid common mistakes: returning a Stream out of a `try` block, reusing a Stream after a terminal operation, and forgetting to close when using `iterator()` or `findFirst()`.
- Run and explain a standalone Java 17 program with deterministic output, requiring no external files.

## 2. What Is a Stream and What Is It Not?

### 2.1. A Stream Is a Pipeline, Not a Collection

With a collection source:

~~~java
List<String> names = List.of("An", "Binh", "Chi");
List<String> upper = names.stream()
        .map(String::toUpperCase)
        .toList();
~~~

This is code inside a method with `java.util.List` imported. The Stream takes its data source from the `List` and produces a result. It is **not another list that can be arbitrarily re-read**; the pipeline has its own lifecycle and should generally be consumed only once.

A Stream created from a collection or `Stream.of(...)` usually **does not hold OS resources that need closing**. Calling `close()` on this kind of Stream generally has no resource benefit beyond running any registered close handlers. The `BaseStream` Javadoc also emphasizes that most Streams do not need to be closed; the notable exceptions are I/O-backed Streams, such as sources from `Files`.

### 2.2. A Stream Can Be Backed by External Resources

When using `Files.lines(path)`, `Files.list(directory)`, or `Files.walk(directory)`, traversal may require file/directory handles. Using a Stream enables reading or searching on demand, but it also places the responsibility of closing the resource on the caller or the component that owns the lifecycle.

For example:

~~~java
Stream<String> lines = Files.lines(path);
~~~

This is a Stream that must be managed. Simply declaring it like this without closing it easily leads to resource management bugs when code exits early, encounters an exception, or returns before finishing traversal.

Instead of relying on the garbage collector or runtime to clean up resources "eventually," place the Stream in `try-with-resources` so it closes at a **deterministic time**.

### 2.3. Quick Identification Table

| Stream Creation | Source | Needs Closing Management? | Appropriate Usage |
| --- | --- | --- | --- |
| `list.stream()` | In-memory `Collection` | Usually no I/O closing needed | Execute pipeline directly |
| `Stream.of(...)` | Provided values | Usually no external resource | Use directly |
| `Arrays.stream(array)` | In-memory array | Usually no external resource | Use directly |
| `IntStream.range(a,b)` | In-memory number range | Usually no external resource | Use directly |
| `Files.lines(path)` | File data | **Yes** | `try (Stream<String> ...)` |
| `Files.list(dir)` | Direct children of a directory | **Yes** | `try (Stream<Path> ...)` |
| `Files.walk(dir)` | Directory tree | **Yes** | `try (Stream<Path> ...)` |
| `Files.find(dir, depth, matcher)` | Directory tree with condition | **Yes** | `try (Stream<Path> ...)` |

Practical rule: read the **Javadoc of the Stream-creating method**. If the documentation states that the Stream holds a reference to an open directory/file and must be closed, use `try-with-resources`. Do not conclude based on whether the elements are of type `String` or `Path`; the same element type can come from either an in-memory source or I/O.

## 3. `AutoCloseable` and Stream Lifecycle

### 3.1. Why Does Java Allow a Stream in `try`?

`BaseStream` extends `AutoCloseable`, so a `Stream<T>` has a `close()` method. `try-with-resources` requires the resource variable to implement `AutoCloseable`, so a Stream fits:

~~~java
try (Stream<String> stream = Files.lines(path)) {
    // Use the stream only within this scope.
}
~~~

Execution overview:

~~~text
Create resource and Stream
          |
          v
Register Stream in try-with-resources
          |
          v
Execute pipeline (may finish early or throw an error)
          |
          v
Exit try block (normal / return / exception)
          |
          v
Automatically call stream.close()
          |
          v
Release I/O source per Stream contract
~~~

`close()` is the operation that **closes the Stream lifecycle** and triggers close handlers. For a Stream with no I/O or close handler, closing may produce no observable action. For a Stream from `Files.lines`/`list`, it serves to release the I/O-backed source.

### 3.2. Terminal Operations Do Not Automatically Close the Stream

~~~java
Stream<String> lines = Files.lines(path);
long total = lines.count();
~~~

After `count()`, the Stream has been consumed for processing, but **there is no rule that a terminal operation automatically calls `close()`**. If the code does not close `lines`, there is still a risk of holding the handle longer than intended.

You must use:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long total = lines.count();
    System.out.println(total);
}
~~~

With `findFirst()`, `limit(n)`, or `anyMatch()`, the pipeline can **short-circuit** and not read the entire source, making closing at the end of the block even more important.

### 3.3. Closing a Stream Does Not Automatically Delete the File

`close()` releases the reading/traversal resource owned by the Stream; it **does not delete the file** and does not necessarily clean up external resources outside the Stream that you created yourself. Creating, writing, and deleting files belong to the separate contracts of `Files` and the respective resources.

If you also create a `BufferedReader`, `InputStream`, or database resource and attach your own Stream, you must determine **who owns** each object rather than assuming `stream.close()` will close every arbitrary resource.

## 4. Using `Files.lines` Correctly

`Files.lines(Path)` and `Files.lines(Path, Charset)` create a Stream of lines from a file for lazy processing. Instead of loading the entire file via `Files.readAllLines`, the program can filter, count, or transform line by line as needed. This is why Streams are often suitable for large files, while also needing to be closed carefully.

### 4.1. Recommended Pattern

~~~java
Path file = Path.of("data.txt");

try (Stream<String> lines = Files.lines(file, StandardCharsets.UTF_8)) {
    long nonBlank = lines.filter(s -> !s.isBlank()).count();
    System.out.println(nonBlank);
}
~~~

This is a **code snippet inside a method** with `Path`, `Files`, `StandardCharsets`, `Stream` imported and `IOException` handled. It assumes `data.txt` exists. Using `StandardCharsets.UTF_8` makes the encoding explicit instead of relying on environment defaults.

When the block ends, `lines.close()` is called. If `filter` or `count` throws a runtime exception, `try-with-resources` still closes the Stream.

### 4.2. Errors When Using `Files.lines`

The Stream-creating method `Files.lines(...)` can throw `IOException`; I/O errors **arising during traversal** may be surfaced as `UncheckedIOException` because Stream API functional interfaces do not declare checked exceptions. You should distinguish **timing** and **exception type**:

- Calling `Files.lines(file)`: may throw `IOException` when opening the file.
- Traversing `filter`/`map`/`count`/`toList`: later I/O errors may appear as `UncheckedIOException`.
- During closing and running close handlers: errors can also occur during cleanup; pay attention to exception propagation and suppressed exceptions.

A handling pattern:

~~~java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.forEach(System.out::println);
} catch (UncheckedIOException ex) {
    // I/O error occurred during traversal, see ex.getCause().
    System.err.println("Read failed: " + ex.getCause());
} catch (IOException ex) {
    // Checked error when creating/opening the resource.
    System.err.println("Open failed: " + ex);
}
~~~

This is a **snippet with a valid `path`**. Do not write business logic assuming all I/O errors have the same type and timing. `UncheckedIOException` is unchecked, and catching it just to print a message may not meet error-handling requirements in a real application.

### 4.3. Avoid Escaping the Resource Outside the Closing Scope

The following code has a **lifecycle bug** even though it compiles in Java:

~~~java
static Stream<String> broken(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank());
    }
}
~~~

As soon as the method returns, the `try` block ends and the Stream is closed. The caller receives a pipeline pointing to a closed source; attempting to execute it afterward may fail because the Stream is already closed or the I/O source is no longer usable.

If the caller only needs a small list, you can **materialize the result inside `try`**:

~~~java
static List<String> readNonBlank(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank()).toList();
    }
}
~~~

`toList()` is a terminal operation; the resulting data is created **before** the Stream closes. The returned `List` no longer depends on the I/O stream. `Stream.toList()` in Java 17 returns an unmodifiable list; if you need to modify it, create a new collection explicitly. For very large files, materializing the entire result can consume significant memory; consider returning an aggregated result, processing via a callback, or transferring Stream ownership to the caller (see section 8).

## 5. Traversing Directories with `Files.list`, `Files.walk`, and `Files.find`

### 5.1. `Files.list` — Single-Level Listing

~~~java
try (Stream<Path> paths = Files.list(directory)) {
    List<String> names = paths
            .map(p -> p.getFileName().toString())
            .sorted()
            .toList();
    System.out.println(names);
}
~~~

This is a **snippet** with `directory` of type `Path` pointing to a valid directory, with appropriate imports and `IOException` handled. `Files.list` is a source backed by a directory stream; traversal results have no guaranteed fixed order by contract, so the example uses `sorted()` before printing.

**Do not** turn `Files.list(directory).forEach(...)` into a one-liner if doing so leaves the resource unclosed. The clean, correct way is to open it in `try-with-resources` and operate inside the block.

### 5.2. `Files.walk` — Walking a Directory Tree

~~~java
try (Stream<Path> paths = Files.walk(root)) {
    long count = paths
            .filter(Files::isRegularFile)
            .count();
    System.out.println(count);
}
~~~

This code is a **snippet** with `root` of type `Path` and `IOException` handled. `Files.walk` may need to hold directory handles while walking the tree, so closing it is essential.

By default, `Files.walk` **does not follow symbolic links** unless `FileVisitOption.FOLLOW_LINKS` is specified. When following links, you must consider cycles, access permissions, and I/O errors. On large trees, walking can take time and encounter files being deleted or having permissions changed while running.

If you only want to traverse to a specific depth, there is the `Files.walk(root, maxDepth)` overload. You should not use `Files.walk(root)` unconditionally on very large system directories.

### 5.3. `Files.find` — Filtering by File Attributes During Traversal

~~~java
try (Stream<Path> files = Files.find(root, 3,
        (path, attrs) -> attrs.isRegularFile()
                && path.toString().endsWith(".java"))) {
    long javaFiles = files.count();
    System.out.println(javaFiles);
}
~~~

This is a snippet inside a method with a valid `root` of type `Path`. `Files.find` uses a `BiPredicate<Path,BasicFileAttributes>` to select elements, and also returns a Stream that must be closed. The result above depends on the state of the real directory tree, so there is no fixed stdout for this illustration.

### 5.4. Quick Comparison

| API | Purpose | Key Points to Remember |
| --- | --- | --- |
| `Files.lines` | Traverse text lines | Charset, read errors during traversal, close source |
| `Files.list` | Direct children of a directory | Order not guaranteed; directory handle must be closed |
| `Files.walk` | Traverse directory tree | Depth, symlinks, access errors, handles must be closed |
| `Files.find` | Traverse tree and filter by attributes | Predicate/depth, I/O source must be closed |

## 6. Standalone Java 17 Program: Closing Streams After Use

This program creates a temporary directory and two sample files, reads content, lists files, and then cleans up the temporary files. The directory name is randomly generated by Java but **not printed**, so stdout can be verified deterministically.

Create file **`StreamResourceDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class StreamResourceDemo {
    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("stream-close-demo-");
        Path a = dir.resolve("a.txt");
        Path b = dir.resolve("b.txt");

        try {
            Files.writeString(
                    a, "Java\n\nLambda\nStream\n",
                    StandardCharsets.UTF_8);
            Files.writeString(
                    b, "notes\n",
                    StandardCharsets.UTF_8);

            // Source is a file, use try-with-resources.
            try (Stream<String> lines = Files.lines(
                    a, StandardCharsets.UTF_8)
                    .onClose(() -> System.out.println("lines closed"))) {
                long nonBlank = lines
                        .filter(s -> !s.isBlank())
                        .count();

                System.out.println("nonblank=" + nonBlank);
            }

            // Source is a directory, also needs to be closed.
            try (Stream<Path> paths = Files.list(dir)
                    .onClose(() -> System.out.println("paths closed"))) {
                List<String> names = paths
                        .map(p -> p.getFileName().toString())
                        .sorted()
                        .toList();

                System.out.println("files=" + names);
            }
        } finally {
            // Separate cleanup; close() does not delete files.
            Files.deleteIfExists(a);
            Files.deleteIfExists(b);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 StreamResourceDemo.java
java StreamResourceDemo
~~~

**Exact stdout on a successful run with a newly created temporary directory:**

~~~text
nonblank=3
lines closed
files=[a.txt, b.txt]
paths closed
~~~

Explanation:

1. `Files.writeString` creates `a.txt` with 4 lines: `Java`, a blank line, `Lambda`, `Stream`; only 3 lines are non-blank, so `nonblank=3`.
2. Terminal `count()` finishes the pipeline **but does not close the Stream**. When exiting the `try` block, the close handler registered by `onClose` runs and prints `lines closed`.
3. `Files.list(dir)` provides two paths. `sorted()` ensures the list of names is printed as `a.txt` then `b.txt`, instead of depending on filesystem return order.
4. Exiting the directory traversal block, the close handler prints `paths closed`.
5. `finally` cleans up the files and directory. This separate deletion is not a function of `Stream.close()`. If file creation or cleanup fails due to permissions or environment conditions, the program may throw `IOException` and not print the full output; this program runs on the real filesystem.

In the example, `onClose` is used to **observe when closing happens**, not to replace `try-with-resources`. In production code, you usually do not need to print a message on every close; what matters is releasing the resource.

## 7. `onClose` — Registering Actions When Closing a Stream

`BaseStream.onClose(Runnable closeHandler)` returns a Stream with a handler that runs when the Stream is closed. It is commonly used for cleanup logic or lifecycle tracking, especially when combining a data source with external resources yourself.

~~~java
try (Stream<String> s = Stream.of("A", "B")
        .onClose(() -> System.out.println("closed"))) {
    System.out.println(s.count());
}
~~~

Stdout:

~~~text
2
closed
~~~

Because `Stream.of` does not hold a file handle, the close handler is why `closed` is displayed. Terminal `count()` does not trigger the handler; only when exiting `try` is the Stream closed.

### 7.1. Multiple Handlers: Registration Order

When multiple handlers are registered via `onClose`, Java runs them in **registration order**:

~~~java
try (Stream<String> stream = Stream.of("x")
        .onClose(() -> System.out.println("first"))
        .onClose(() -> System.out.println("second"))) {
    stream.count();
}
~~~

Stdout:

~~~text
first
second
~~~

If one handler throws an exception, the other handlers still execute; the first exception is thrown and subsequent errors may be attached as **suppressed exceptions**. Therefore, cleanup handlers should be simple, have clear error contracts, and avoid complex side effects. `Stream.close()` has idempotent semantics for running close handlers: repeatedly closing an already-closed Stream does not run the handlers again.

### 7.2. Linking `onClose` to Another Resource

If you create a Stream yourself from a source with an external resource, you can use:

~~~java
Stream<String> stream = makeStreamFromResource(resource)
        .onClose(resource::close);
~~~

This is an **illustrative API sketch, not standalone runnable**: you must define `makeStreamFromResource` and the appropriate `resource` type; a `Runnable` close handler cannot declare checked exceptions. If `resource.close()` throws a checked exception, the method reference `resource::close` may be **incompatible with `Runnable`**, so you need to handle the exception or design a different resource-owning class. Do not attach a handler twice if a Stream from `Files` already closes the underlying resource properly.

If a resource has a complex lifecycle, managing each resource explicitly with `try-with-resources` is usually clearer.

## 8. Resource Ownership: Which Layer Closes It?

### 8.1. Fundamental Principle

**The layer that creates a resource-backed Stream must clearly define who closes it.** A method can:

1. **Own the entire lifecycle:** create, consume, and close the Stream internally; return the computed result.
2. **Transfer ownership to the caller:** return an open Stream and **explicitly document that the caller must close it** with `try-with-resources`.
3. **Accept a processing callback:** create the Stream, invoke the callback inside a `try` block, and close it before returning a normal result.

Option 1 is usually easiest to use when you only need a count, an aggregated result, or a list that fits in memory.

### 8.2. Helper Returning a Computed Result

~~~java
static long countNonBlank(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank()).count();
    }
}
~~~

Having `return` inside the `try` block does not skip cleanup: Java still calls `close()` **before the method actually returns the result**. This method does not let the Stream escape.

### 8.3. Helper Returning a Stream: Caller Must Close

~~~java
static Stream<String> openNonBlank(Path path) throws IOException {
    return Files.lines(path).filter(s -> !s.isBlank());
}
~~~

This is a method that **transfers resource ownership**. If you choose this design, the caller must be clearly informed:

~~~java
try (Stream<String> lines = openNonBlank(path)) {
    lines.forEach(System.out::println);
}
~~~

Calling close on the pipeline's resulting Stream closes the entire pipeline associated with the original source Stream and its close handlers. You should not casually call `openNonBlank(path).toList()` without an explicit close mechanism.

In public APIs, the Javadoc should state: *Returned Stream must be closed by the caller*. Be cautious if callers might store the Stream and use it only later, because how long the resource stays open becomes hard to control.

### 8.4. Helper Accepting a Callback and Guaranteeing Close

If you do not want callers to manage the Stream directly, you can accept a processing function:

~~~java
static <R> R withLines(
        Path path, Function<Stream<String>, R> action)
        throws IOException {
    Objects.requireNonNull(action, "action");
    try (Stream<String> lines = Files.lines(path)) {
        return action.apply(lines);
    }
}
~~~

This is an illustrative method with `Path`, `Files`, `Function`, `Objects`, and `Stream` imported. It closes the Stream when the callback finishes, returns a value, or throws an unchecked exception. **Do not** let the callback return the Stream itself for traversal after the block, because that result would point to a closed Stream. If the callback needs to throw checked exceptions other than `IOException`, you must design a dedicated lambda contract for that case.

Example usage returning a `Long`:

~~~java
long count = withLines(path,
        lines -> lines.filter(s -> !s.isBlank()).count());
~~~

This approach keeps resource responsibility in the helper while still letting the caller choose the action within a safe scope.

## 9. Lazy Evaluation and Resource Closing

### 9.1. Intermediate Operations Have Not Traversed Data Yet

~~~java
try (Stream<String> lines = Files.lines(path)) {
    Stream<String> filtered =
            lines.filter(s -> s.startsWith("A"));

    // No terminal operation yet: filter has not traversed the data.
}
~~~

Upon exiting `try`, the source Stream is closed even though no elements were read. This matters if a lazy Stream is created but never reaches a terminal operation: **it still must be closed** if it holds a resource.

### 9.2. Short-Circuiting Still Requires Closing

~~~java
try (Stream<String> lines = Files.lines(path)) {
    boolean found =
            lines.anyMatch(s -> s.contains("ERROR"));
    System.out.println(found);
}
~~~

`anyMatch` can stop as soon as it finds a matching line without consuming the whole file. `try-with-resources` closes the source at the end of the block. The same applies to `findFirst`, `limit`, `findAny`, and other pipelines that can terminate early.

### 9.3. A Stream Cannot Be Reused After Consumption

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long count = lines.count();
    // long second = lines.count(); // Wrong: Stream has already been consumed.
}
~~~

A Stream can generally only be processed through a pipeline once. Calling a terminal operation or operating on a Stream after it has been consumed or closed can throw `IllegalStateException`. When you need to analyze data twice, open a new Stream and close it separately, or materialize the result into a collection if size permits.

Do not reuse an already-processed Stream just because the Java object is still held by a reference variable.

## 10. Exceptions When Using `try-with-resources`

### 10.1. The `try` Block or `close` Can Fail

`try-with-resources` guarantees an attempt to close successfully created resources when exiting the block, including when a callback/lambda throws a runtime exception. If `close()` or a close handler also throws an exception, Java applies **suppressed exception** rules:

- If the `try` body throws a primary exception and closing the resource also fails, the close error is typically attached to the primary exception via `getSuppressed()`.
- If the `try` body completes normally but closing fails, the close-step exception can be the exception thrown out.
- When multiple resources are declared in the same `try-with-resources`, they are closed in **reverse order** of initialization, and close errors may be suppressed.

Do not catch errors broadly and ignore `getSuppressed()` when investigating complex file read/close failures.

### 10.2. Multiple Resources in One Block

~~~java
try (BufferedReader reader = Files.newBufferedReader(path);
     Stream<String> lines = reader.lines()) {
    lines.forEach(System.out::println);
}
~~~

This is an **illustrative snippet** with `IOException` handled, and **reader** is the actual resource registered for closing. `BufferedReader.lines()` returns a Stream of lines, but **you must not rely on `Stream.close()` as a substitute for `reader.close()`**; in this example, `try-with-resources` closes `reader` independently. The closing order is `lines` first, `reader` second.

This differs from `Files.lines(path)`, where the returned Stream is designed to close the underlying file source. When the source is a `Reader` you own, manage the `Reader` explicitly instead of assuming the Stream will always close it for you.

### 10.3. Distinguishing Open Errors from Traversal Errors

With `Files.lines`, `Files.list`, and `Files.walk`, opening the source can throw `IOException`; during traversal, I/O errors may be converted into `UncheckedIOException`. Documentation may specify different details for each API; you should not write a single catch and claim it covers every case. Error propagation, task cancellation, and resource cleanup should be tested against scenarios such as missing files, locked files, insufficient permissions, or files modified during traversal.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `Files.lines(path).count()` without closing | Risk of holding a file handle | Put the Stream in `try-with-resources` |
| Believing `count()`/`toList()` auto-closes | Terminal operations consume, do not promise close | Always close resource-backed sources |
| Returning a Stream out of a closed `try` | Caller gets a pipeline on a closed resource | Return the result, or transfer ownership explicitly |
| Using a `Stream` twice | Stream is already consumed/closed | Create a new source or store the result |
| Using `findFirst()` then discarding the Stream | Short-circuiting does not auto-close | Use `try-with-resources` |
| Assuming every collection Stream needs closing | Not every Stream holds I/O | Check the source API and Javadoc |
| Using `Files.list`/`walk` without closing | Can leak directory handles | Use `try (Stream<Path> ...)` |
| Relying on `Files.list` order | Directory traversal does not guarantee order | Use `sorted()` if order is needed |
| Forgetting to close `BufferedReader` while closing `reader.lines()` | Closing that Stream is not a substitute for `Reader.close` | Put the `Reader` in `try-with-resources` |
| Using `onClose` instead of `try-with-resources` | Handler only runs if `close()` is called | Still need an explicit place calling close |
| Catching all exceptions and swallowing them | Loses root cause, misses cleanup errors | Catch purposefully, preserve cause/suppressed |
| Assuming `close()` deletes the file | Close releases resources, does not delete data | Delete with a separate API if actually needed |
| Creating a lazy pipeline without consuming so not closing | Source may still hold resources | Close even when no terminal operation runs |
| Returning a Stream from a helper callback and using it later | Stream is already closed when helper returns | Do not let the Stream escape scope |
| Opening Streams from too many files at once | May exhaust OS handles | Process in small scopes, close each source |

## 12. Code Review Checklist

When a method **creates a Stream**, ask:

1. Is the Stream sourced from `Collection`/`Stream.of` or from `Files`/I/O?
2. Does the source API Javadoc require closing the Stream?
3. If yes, does `try-with-resources` cover the entire **creation, transformation, and terminal operation**?
4. Are there early `return`s, exceptions, or short-circuits? Does closing still happen in the right place?
5. Is the Stream returned to the caller? If so, **who is the owner** and does the Javadoc clearly state the caller must close it?
6. Does a resource-dependent Stream/iterator/spliterator accidentally escape **outside the closed scope**?
7. When the source is a separate `BufferedReader`/`InputStream`, is that resource itself closed?
8. Is `onClose` used? Is the handler guaranteed to be invoked via a close call?
9. Are there multiple resources? Have closing order and suppressed exceptions been considered?
10. Are you relying on directory traversal order? Is `sorted()` needed?
11. Can I/O errors occur during lazy traversal? Are `IOException` and `UncheckedIOException` handled per contract?
12. Have you tested with empty files, missing files, empty directories, early exits, and permission errors?
13. Is a Stream accidentally consumed twice or used after closing?
14. Are file handles held longer than necessary due to nesting pipelines or returning a Stream from the creation layer?

## 13. Practice Exercises

### Exercise 1 — Count Non-Empty Lines

Create a UTF-8 file with 5 lines, 2 of which are blank. Write a method `static long countNonBlank(Path path) throws IOException` using `Files.lines` inside `try-with-resources`, `filter(s -> !s.isBlank())`, and `count()`. Expected result: `3`. Explain why you should not call `Files.lines(path).filter(...).count()` directly without closing.

### Exercise 2 — Find First Line and Close

Use `Files.lines(path)` with `filter`/`findFirst()` to find the first line containing `"ERROR"`. Even when found on the very first line, demonstrate that `try-with-resources` still calls close when leaving scope. Try attaching `onClose(() -> System.out.println("closed"))` to observe it.

### Exercise 3 — List Files by Name

Create a sample directory containing `b.txt` and `a.txt`. Use `Files.list(dir)` inside `try-with-resources`, get `getFileName()`, `sorted()`, and `toList()`. Predict the output `[a.txt, b.txt]`. Try removing `sorted()` and explain why print order is no longer guaranteed.

### Exercise 4 — Refactor a Method Returning a Closed Stream

Fix the method:

~~~java
static Stream<String> bad(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isBlank());
    }
}
~~~

There are two approaches: (a) return `List<String>` using `toList()` inside the `try` block, or (b) return an open Stream and require the caller to close it. Write Javadoc describing ownership for option (b).

### Exercise 5 — Reader and Stream

Use `Files.newBufferedReader(path)` in `try-with-resources` and traverse `reader.lines()`. Explain why you must ensure `reader.close()` instead of assuming the Stream created from `reader.lines()` closes the Reader as well.

### Exercise 6 — Test Errors and Suppressed Exceptions

Create a custom `AutoCloseable` whose `close()` throws `IllegalStateException("close failed")` and a `try` body that throws `IllegalArgumentException("body failed")`. Catch the primary exception and inspect `getSuppressed()` to see that the close error is not lost. Relate this to the case of a Stream whose `onClose` handler throws an exception.

### Exercise 7 — Traverse a Directory Tree with a Depth Limit

Use `Files.walk(root, 2)` to count regular files within two levels below `root`. Place it in `try-with-resources`. Explain why you should limit depth on very large directories and how to handle `UncheckedIOException` during traversal.

### Exercise 8 — Design an API with Ownership

Write two variants: `countLines(Path)` returning `long` and `openLines(Path)` returning `Stream<String>`. For the second variant, write a caller example using `try (Stream<String> lines = openLines(path))`. Evaluate the trade-off between convenience and resource-closing responsibility.

## 14. Summary and References

**Streams backed by I/O resources must be closed on time.** `BaseStream` extends `AutoCloseable`, so `try-with-resources` is the standard way to call `close()` automatically when exiting scope. For Streams from `Files.lines`, `Files.list`, `Files.walk`, and `Files.find`, place both **source creation and the entire pipeline you need** inside the `try` block; do not assume `count()`/`toList()`/`findFirst()` closes the resource.

Most Streams from collections or arrays do not require closing for external resources, though they can still have close handlers. `onClose` is a hook for registering cleanup callbacks on close, not a replacement for lifecycle management. If returning a Stream from a method, transfer ownership clearly to the caller; otherwise, prefer returning a computed result inside `try`. For a `Reader` source you create yourself, close the **Reader** where it is owned, rather than assuming the Stream will close every underlying resource for you.

**Official documentation to consult:** Java SE 17 Javadoc for `java.util.stream.BaseStream` and `Stream`; `java.nio.file.Files` (`lines`, `list`, `walk`, `find`); `java.io.BufferedReader` and `AutoCloseable`; Java Language Specification section `14.20.3 try-with-resources`.

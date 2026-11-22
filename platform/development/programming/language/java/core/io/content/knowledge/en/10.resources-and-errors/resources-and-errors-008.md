# UncheckedIOException When Combining I/O with the Stream API

## 1. Why Is UncheckedIOException Needed?

In Java, many I/O operations can throw **`IOException`**, a *checked exception*. The compiler requires the calling method to catch (`catch`) or declare (`throws IOException`) that exception. However, standard functional interfaces of the **Stream API** such as `Function<T,R>`, `Predicate<T>`, and `Consumer<T>` do not declare checked exceptions on their abstract methods.

Consequently, this seemingly natural code **does not compile**:

```java
// Intentionally WRONG example: Files.readString can throw IOException.
List<String> contents = paths.stream()
        .map(path -> Files.readString(path))
        .toList();
```

`Stream.map` accepts a `Function`; `Function.apply` does not declare `throws IOException`. Even if the enclosing method declares `throws IOException`, the lambda itself is still constrained by the signature of `Function.apply`.

`java.io.UncheckedIOException` bridges that boundary: it is a **`RuntimeException` dedicated to wrapping `IOException`**. We can convert a checked I/O error into an unchecked error inside the lambda, allowing the exception to propagate through `map`, `filter`, `forEach`, or other transformations, and then decide how to handle it at an appropriate boundary.

```text
File / network / Reader
      │
      ▼
I/O method throws IOException  (checked)
      │
      ▼
catch (IOException cause)
      │
      ▼
throw new UncheckedIOException(cause)
      │
      ▼
Stream pipeline / terminal operation  (unchecked)
      │
      ▼
catch (UncheckedIOException ex)
      └─ ex.getCause()  → original IOException
```

**The goal of UncheckedIOException is not to hide errors.** It preserves the **underlying `IOException` cause** so code can report the error, abort processing, perform controlled retries, or convert the exception back to a checked API at an upper layer.

### Distinguishing Key Concepts

| Concept | Meaning |
| --- | --- |
| `IOException` | Checked exception describing read/write or data-source errors |
| `UncheckedIOException` | Runtime exception wrapping an `IOException`, convenient where checked exceptions are not declared |
| `RuntimeException` | Broader unchecked exception group; not specific to I/O |
| Stream pipeline | Chain of transformation steps that typically execute **lazily** |
| Terminal operation | `toList()`, `collect()`, `count()`, `forEach()`, `findFirst()`... triggers execution |
| Resource-owning stream | Certain Stream API objects hold file/directory handles and require `close()` |

A pure in-memory data-processing pipeline may not need `UncheckedIOException` at all; it appears when **an actual I/O operation** is performed or when standard Java APIs themselves use this exception type to propagate errors during stream traversal.

## 2. API and Relationship with IOException

`UncheckedIOException` lives in `java.io`. It extends `RuntimeException`, so the compiler does not require callers to catch or declare it. Key constructors:

```java
new UncheckedIOException(IOException cause)
new UncheckedIOException(String message, IOException cause)
```

These are **illustrative expressions**, requiring imports `java.io.UncheckedIOException` and `java.io.IOException`; `cause` must be a non-null `IOException`. There is **no constructor accepting an arbitrary `Throwable`**. Do not use this type to wrap `IllegalArgumentException` or `NullPointerException`, as they do not represent I/O errors.

Capabilities:

- `getCause()` returns the original `IOException`.
- `getMessage()` returns the wrapper's message (where extra context can be added).
- The stack trace shows where wrapping happened, and the `cause` chain traces back to where the I/O failure originated.
- Because it is unchecked, `UncheckedIOException` can propagate through `Function.apply`, `Predicate.test`, and `Consumer.accept` without requiring `throws` declarations.

A good practice when wrapping is adding **practical context** such as relative path, current operation, record ID, or expected format:

```java
try {
    return Files.readString(path, StandardCharsets.UTF_8);
} catch (IOException cause) {
    throw new UncheckedIOException(
            "Cannot read: " + path, cause);
}
```

This snippet sits inside **a method returning String** with `Path path` and required imports. Do not return `""` just to avoid errors unless the application explicitly defines "unreadable means empty string", because doing so mixes I/O failures with valid data.

## 3. Checked Exceptions and Lambda Signatures

Consider `java.util.function.Function<T,R>`:

```java
@FunctionalInterface
public interface Function<T, R> {
    R apply(T value);
}
```

This is a **condensed form to explain the signature**, not a complete copy of the standard interface. `apply` declares no checked exceptions. A lambda used as `Function<Path, String>` therefore cannot let `IOException` from `Files.readString` escape directly.

### Common Approach: Catch Inside the Lambda and Wrap

```java
List<String> texts = paths.stream()
        .map(path -> {
            try {
                return Files.readString(path, StandardCharsets.UTF_8);
            } catch (IOException cause) {
                throw new UncheckedIOException(
                        "Cannot read " + path, cause);
            }
        })
        .toList();
```

This is an illustrative snippet; `paths` is an existing `List<Path>`. It requires `Files`, `StandardCharsets`, `IOException`, `UncheckedIOException`, and `List`. The `toList()` call is a terminal operation introduced in **Java 16**.

If every file is readable, `texts` holds contents in sequential list-stream encounter order. If one file causes `IOException`, the lambda wraps it in `UncheckedIOException`, `toList()` fails, and no partial list is returned.

**No automatic transactions:** if the lambda also writes files, updates databases, or mutates state, items processed before the error may still leave side effects. The Stream API does not roll back those effects.

### Alternative: Move I/O Into a Named Adapter Method

```java
static String readUtf8Unchecked(Path path) {
    try {
        return Files.readString(path, StandardCharsets.UTF_8);
    } catch (IOException cause) {
        throw new UncheckedIOException(
                "Failed to read " + path, cause);
    }
}
```

This is an **illustrative method**; callers write `paths.stream().map(MyClass::readUtf8Unchecked)`. Placing wrapping logic in a method makes stream code easier to read and test. A general utility can provide an adapter for a "throwing function", yet it should enforce a clear policy that **only `IOException` is wrapped in `UncheckedIOException`**; other programming bugs keep their original types.

## 4. Runnable Java 17 Example: Wrapper in a Pipeline

This program simulates a deterministic I/O source so we can see the difference between the original exception and the wrapper. It needs no external files, so output is deterministic.

**File `UncheckedIoPipelineDemo.java`:**

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;

public class UncheckedIoPipelineDemo {
    static String load(String name) throws IOException {
        if ("broken".equals(name)) {
            throw new IOException("synthetic read failure");
        }
        return name.toUpperCase(Locale.ROOT);
    }

    static String loadUnchecked(String name) {
        try {
            return load(name);
        } catch (IOException cause) {
            throw new UncheckedIOException("Loading " + name, cause);
        }
    }

    public static void main(String[] args) {
        List<String> good = List.of("alpha", "beta").stream()
                .map(UncheckedIoPipelineDemo::loadUnchecked)
                .toList();
        System.out.println("Success: " + good);

        try {
            List.of("alpha", "broken", "beta").stream()
                    .map(UncheckedIoPipelineDemo::loadUnchecked)
                    .toList();
        } catch (UncheckedIOException failure) {
            System.out.println("Wrapper: "
                    + failure.getClass().getSimpleName());
            System.out.println("Cause: "
                    + failure.getCause().getClass().getSimpleName());
            System.out.println("Cause message: "
                    + failure.getCause().getMessage());
        }
    }
}
```

Compile and run:

```bash
javac UncheckedIoPipelineDemo.java
java UncheckedIoPipelineDemo
```

**Exact stdout:**

```text
Success: [ALPHA, BETA]
Wrapper: UncheckedIOException
Cause: IOException
Cause message: synthetic read failure
```

Points to observe:

1. `load` declares `throws IOException`; it keeps a checked API when called directly.
2. `loadUnchecked` catches and wraps the error; it can be passed as a method reference to `map`.
3. `toList()` executes the pipeline. When an element throws, the result list is not returned.
4. `getCause()` retains the original `IOException` with its initial message.

Not every test has to construct real failing files. Testing with a simulated method like this clearly verifies **exception propagation policy**, while integration tests should check permissions, missing files, disks, or networks where needed.

## 5. Stream API Executes Lazily: When Do Errors Happen?

Intermediate transformations such as `map`, `filter`, `peek`, and `flatMap` build a pipeline **without processing any elements yet**. Thus constructing the pipeline may not throw; errors appear when invoking the terminal operation:

```java
Stream<String> pipeline = paths.stream()
        .map(MyClass::readUtf8Unchecked); // Does not necessarily read files yet.

// This is when elements are actually read:
List<String> result = pipeline.toList();
```

The snippet above assumes `readUtf8Unchecked` and corresponding imports exist. Never conclude "the pipeline built cleanly, so I/O succeeded".

**Short-circuit operations** also change which errors can occur:

- `findFirst()`, `anyMatch()`, and `limit(n)` may read only part of the source.
- A failing element later in the stream may **never be reached**.
- `count()` on certain sources and pipelines can be optimized to skip intermediate operations that do not affect the count. Do not put I/O side effects inside `peek` and assume they always execute.

If business logic requires **every file to be verified**, choose an appropriate terminal operation and processing structure. The Stream API is a data-processing tool, not a transaction engine guaranteeing every side effect ran exactly once.

### Is Putting I/O Inside map Always a Good Choice?

No. When a workflow involves multiple states, retry logic, rollback requirements, or collecting multiple errors, a plain `for` loop is often clearer. `UncheckedIOException` is a technical tool for when **checked exceptions hit a functional-interface boundary**, not a reason to force all I/O work into a stream pipeline.

## 6. Files.lines: IOException at Open Time and UncheckedIOException During Lazy Reading

`Files.lines(Path, Charset)` returns a `Stream<String>` that reads lines from a file lazily. There are **two error phases** to distinguish:

1. **At open time**: `Files.lines(path, charset)` can throw **`IOException` (checked)** if opening the file fails.
2. **During consumption**: once the stream is created, if an I/O error occurs while reading lines, the error is typically propagated as **`UncheckedIOException`** from the operation traversing the stream.

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
} catch (UncheckedIOException duringRead) {
    // Error occurred while traversing the stream.
} catch (IOException duringOpenOrClose) {
    // Checked error during open or at an I/O call declaring checked exceptions.
}
```

This is an **illustrative snippet**, requiring imports for `Stream`, `Files`, `Path`, `StandardCharsets`, `UncheckedIOException`, and `IOException`. `Stream.close()` does not declare checked `IOException`, so you cannot assume a file-release error always lands in the checked catch branch. Most importantly, always use `try-with-resources` to close the `Stream<String>` returned by `Files.lines`.

**Terminal operations do not automatically close the stream.** Completing `count()`, `toList()`, or `forEach()` does not replace `close()` when the stream owns a file handle.

### Runnable Java 17 Example: Files.lines and Resource Management

**File `FileLinesDemo.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-lines-", ".txt");

        try {
            Files.writeString(file, "alpha\n\nbeta\n",
                    StandardCharsets.UTF_8);

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                long nonBlank = lines.filter(s -> !s.isBlank()).count();
                System.out.println("Nonblank lines: " + nonBlank);
            }

            try (Stream<String> lines =
                         Files.lines(file, StandardCharsets.UTF_8)) {
                String joined = lines
                        .filter(s -> !s.isBlank())
                        .map(String::toUpperCase)
                        .reduce((a, b) -> a + "," + b)
                        .orElse("");
                System.out.println("Joined: " + joined);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Commands:

```bash
javac FileLinesDemo.java
java FileLinesDemo
```

**Exact stdout when file operations succeed:**

```text
Nonblank lines: 2
Joined: ALPHA,BETA
```

A stream that has already run a terminal operation **cannot be reused**; the example opens `Files.lines` a second time to perform another computation. The temp file is deleted in `finally`. If deletion fails, the program may throw `IOException`, so the output above represents the successful run.

For files with encoding errors or content read while the file is being modified, error reporting depends on the API and charset; applications must handle `UncheckedIOException` per their policy, not just catch checked `IOException` on the open call.

## 7. BufferedReader.lines and Who Owns the Resource?

`BufferedReader.lines()` also returns a `Stream<String>` reading lines from the reader. When an I/O error occurs during reading, the stream can throw `UncheckedIOException`. However, ownership must be clearly distinguished:

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    long lines = reader.lines().count();
    System.out.println(lines);
}
```

This is an illustrative snippet. Here `BufferedReader` is the opened resource, and **try-with-resources on the reader itself** is responsible for closing. Never assume that merely because an object has type `Stream<String>`, closing it always closes the underlying reader; **`BufferedReader.lines()` does not share the same resource contract as `Files.lines()`**.

Note: while a Stream is consuming a `BufferedReader`, avoid operating directly on the reader from another thread or between stream steps. A reader is stateful, easily leading to skipped data or unexpected consumption.

### Quick Comparison

| API | Who Opens the Source? | Who Must Close? | Traversal Error |
| --- | --- | --- | --- |
| `Files.lines(path, charset)` | API opens file | Caller closes returned `Stream<String>` | May be `UncheckedIOException` |
| `reader.lines()` | Caller already has `BufferedReader` | Caller manages and closes reader | May be `UncheckedIOException` |
| `Files.readAllLines(path, charset)` | API reads inside the call | No live stream returned; returns `List<String>` | Checked `IOException` from the call |
| `Files.readString(path, charset)` | API reads inside the call | No live stream returned; returns `String` | Checked `IOException` from the call |

APIs returning all data upfront are simpler regarding ownership, yet consume memory proportional to file size. Lazy APIs are useful for large inputs, yet require careful closing lifecycle management.

## 8. Files.list, Files.walk, and Files.find

Beyond `Files.lines`, directory-traversal APIs also return **Stream API objects tied to I/O resources**:

- `Files.list(directory)`: returns a stream iterating direct entries of a directory.
- `Files.walk(start, maxDepth, ...)`: walks a file and directory tree up to a specified depth.
- `Files.find(start, maxDepth, matcher, ...)`: walks a tree and filters via `BiPredicate<Path,BasicFileAttributes>`.

The call **opening** these streams can throw checked `IOException`. During lazy traversal, if an error occurs reading directories or attributes, `UncheckedIOException` may be thrown. These streams **must be closed** to release resources used for directory traversal.

```java
try (Stream<Path> entries = Files.list(directory)) {
    List<Path> names = entries.sorted().toList();
    // Use names here.
}
```

This is an illustrative snippet assuming `Path directory` exists. Having `toList()` return a list of `Path` values does not require keeping the directory stream open after the `try` block finishes.

### Nesting I/O Inside Files.walk

A common pattern is traversing files while reading their contents:

```java
try (Stream<Path> files = Files.walk(root)) {
    List<String> texts = files
            .filter(Files::isRegularFile)
            .map(UncheckedFileReader::readUtf8Unchecked)
            .toList();
}
```

This is an illustrative snippet: class `UncheckedFileReader` is assumed to provide `readUtf8Unchecked(Path)` like the adapter method in section 3. There are **two error sources**:

1. `Files.walk` itself while traversing the filesystem (and querying attributes), which can throw `UncheckedIOException`.
2. Application-written `readUtf8Unchecked`, which can also throw `UncheckedIOException`.

For diagnostics, add operation/path context right when wrapping the cause. **Do not blindly parallelize** over a file tree without controlling file descriptors, effects of concurrent file changes, read permissions, and memory limits when accumulating all contents.

## 9. Practical Example: Reading Multiple Files and Returning Contextual Errors

A method accepting a list of paths wants to use the Stream API yet still declare **`throws IOException`** to callers. It can wrap inside the lambda and **unwrap at the public API boundary**.

**File `ReadFilesWithStream.java`:**

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class ReadFilesWithStream {
    static List<String> readAll(List<Path> paths) throws IOException {
        try {
            return paths.stream()
                    .map(path -> {
                        try {
                            return Files.readString(
                                    path, StandardCharsets.UTF_8);
                        } catch (IOException cause) {
                            throw new UncheckedIOException(
                                    "Reading " + path.getFileName(), cause);
                        }
                    })
                    .toList();
        } catch (UncheckedIOException failure) {
            throw failure.getCause();
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-batch-", ".txt");
        try {
            Files.writeString(file, "hello",
                    StandardCharsets.UTF_8);

            System.out.println("Read: " + readAll(List.of(file)));

            Path missing = file.resolveSibling(
                    "missing-" + file.getFileName());
            try {
                readAll(List.of(missing));
            } catch (IOException failure) {
                System.out.println("Missing file reported: "
                        + (failure instanceof java.nio.file.NoSuchFileException));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run:

```bash
javac ReadFilesWithStream.java
java ReadFilesWithStream
```

**Stdout in standard conditions (when `missing` genuinely does not exist):**

```text
Read: [hello]
Missing file reported: true
```

`file` is a temp file created at runtime. `missing` points to a different name in the same directory with prefix `missing-`; the example assumes it does not exist to trigger `NoSuchFileException`. In real systems, a file object could be created concurrently by another process, so when writing strict tests, create an isolated temp directory and control fixtures directly.

### A Trade-off Worth Noting

In `readAll`, `throw failure.getCause()` preserves the original `IOException` subtype, yet **strips the wrapper's contextual message** from the exception thrown to the caller. If path context is critical information, you can:

- Declare the API to propagate `UncheckedIOException` and pass the wrapper intact.
- Throw a new `IOException` with a contextual message and `failure.getCause()` as the cause.
- Record context via appropriate logging/diagnostics before propagating the error.

Do not "unwrap" out of habit if doing so leaves operators unable to tell which file failed. Choosing the exception type at the **API boundary** must fit both the public contract and diagnostic needs.

## 10. A Design Policy: Unchecked Internally, Checked Externally

Three common API styles exist:

**Style A — Keep checked IOException on the public API.** Inside the Stream API you can wrap temporarily; before returning, unwrap or construct a new `IOException` carrying added context.

```java
static List<String> process(List<Path> paths) throws IOException {
    try {
        return paths.stream()
                .map(MyClass::readUtf8Unchecked)
                .toList();
    } catch (UncheckedIOException ex) {
        throw new IOException("Batch read failed", ex.getCause());
    }
}
```

This is an illustrative method; `MyClass::readUtf8Unchecked` must be defined accordingly.

**Style B — Public API allows UncheckedIOException to escape.** Standard APIs like `Files.lines` during lazy traversal follow this approach. Callers must know errors can occur **late** while consuming the stream.

**Style C — Per-element error handling.** Instead of letting the first error abort the entire pipeline, the system returns results like `Success(value)` or `Failure(path, error)`. That lets every element be evaluated and multiple errors be reported together. Do not replace errors with `null`, `""`, or `Optional.empty()` if business logic must distinguish "empty file", "no data", and "read failure".

The choice depends on a business question: **should a single failure fail the entire batch**, or do users want separate lists of successes and failures?

## 11. Turning an IOException Method Into a Reusable Function

If a codebase has many lambdas reading/writing, you can define a custom interface declaring `IOException` and build an adapter:

```java
@FunctionalInterface
interface IOFunction<T, R> {
    R apply(T value) throws IOException;
}

static <T, R> java.util.function.Function<T, R> unchecked(
        IOFunction<T, R> operation) {
    return value -> {
        try {
            return operation.apply(value);
        } catch (IOException cause) {
            throw new UncheckedIOException(cause);
        }
    };
}
```

This is an **illustrative snippet inside a Java class**, requiring `java.io.IOException` and `java.io.UncheckedIOException`. Usage:

```java
List<String> texts = paths.stream()
        .map(unchecked(path -> Files.readString(path,
                StandardCharsets.UTF_8)))
        .toList();
```

The adapter centralizes catch/wrap logic. Still, it has limitations:

- It does not automatically add path/record context; use an adapter taking a message from the caller if needed.
- Wrap only `IOException`. Never catch all `Exception` and turn programming bugs into an "I/O problem".
- If I/O has side effects and retries, an adapter does not make the operation idempotent.
- For readability, adapters shorten code yet sometimes obscure where reads/writes happen; use them when they genuinely improve clarity.

Similar adapters can be written for `IOConsumer`, `IOPredicate`, or `IOBiFunction`. Avoid building an oversized wrapper library for just a couple of catch sites.

## 12. Do Not Use UncheckedIOException for Every Exception

`UncheckedIOException` only expresses "an `IOException` occurred, but the API here does not declare checked exceptions". Distinguish these cases:

| Incident | Natural Error Type | Should You Wrap in UncheckedIOException? |
| --- | --- | --- |
| `Files.readString` denied read permission | `IOException`/subclass | Yes, when crossing a lambda without checked throws |
| File disappears while opening | `NoSuchFileException` (subclass of `IOException`) | Can wrap as above |
| Parser finds invalid number in text | `NumberFormatException` | No; this is a data/parse error, not `IOException` |
| `String.substring` uses invalid index | `IndexOutOfBoundsException` | No; logic or input bug |
| Unexpected null inside lambda | `NullPointerException` | No; fix the null cause |
| Java heap runs out of memory | `OutOfMemoryError` | No; not an `IOException` |
| `Files.lines` fails while traversing content | `UncheckedIOException` from API | Keep/catch at appropriate boundary; no pointless re-wrapping |

When a pipeline throws `UncheckedIOException`, always inspect `getCause()` to understand the root error, while keeping the wrapper's context if present. Never log only `failure.getMessage()` and drop the stack trace and cause when diagnosing tough failures.

## 13. Resources and Exceptions: try-with-resources Around the Terminal Operation

An I/O error can occur **mid-traversal**. If a stream was opened from a file or directory, the resource still must be closed when the operation throws an exception.

```java
try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    lines.map(this::transform)
         .forEach(this::accept);
} catch (UncheckedIOException failure) {
    // Resource of Files.lines was already closed before entering catch.
    handleIoError(failure.getCause());
}
```

This is **illustrative code with application-specific methods** (`transform`, `accept`, `handleIoError`) left undefined; not a standalone program. `try-with-resources` guarantees calling `close()` on the Stream even if `map` or `forEach` fails. Whether **closing itself succeeds unconditionally** still depends on the resource and API behavior.

If you only close the stream on the success path:

```java
// Wrong lifecycle handling if the terminal operation throws an exception.
Stream<String> lines = Files.lines(path);
lines.forEach(System.out::println);
lines.close();
```

then when `forEach` throws, `close()` never runs. Open and consume within the same `try-with-resources`.

### Suppressed Exceptions

When the `try` body throws an exception and closing the resource also throws an exception, Java attaches the close error as **suppressed** on the primary error per try-with-resources rules. If you wrap or construct new exceptions arbitrarily at higher layers without preserving the chain, cleanup details can be lost. When investigating multi-layer I/O failures, inspect both `getCause()` and `getSuppressed()`.

## 14. Sequential Streams, Parallel Streams, and Error Observability

In a **sequential stream**, operations follow the pipeline's sequential traversal mechanics. When the first error is thrown, the terminal operation can halt; subsequent elements are not necessarily processed.

In a **parallel stream**:

- Multiple files may be read concurrently.
- Start/completion order of I/O may differ from encounter order.
- An exception in one branch does not mean all tasks stopped instantaneously; other operations may have already produced side effects.
- Consider resources like file descriptors, disk, network, and concurrency limits.

Never switch to `parallel()` merely because I/O is slow. For I/O with many tasks, choose an appropriate concurrency/queue model, cap concurrent requests, and define explicit cancellation and resource-closing mechanisms.

Pipelines combining `parallel`, side effects, retries, and data recovery are usually far easier to control with an explicit executor/service architecture than with error-catching lambdas everywhere.

## 15. Contextual Error Logging and Avoiding Information Leaks

A helpful exception message should state **which operation** failed:

```java
throw new UncheckedIOException(
        "Reading configuration: " + path.getFileName(), cause);
```

This is an illustrative snippet, not a standalone class. Not every full path, username, or file content is safe to write to public logs. When logging in multi-tenant applications, consider avoiding leaking absolute paths or sensitive data.

Log **once at the right contextual layer** and preserve the exception cause. If every layer both logs and rethrows, the same failure appears repeatedly without adding useful insight.

A sound strategy:

- Low I/O layer: wrap `IOException` with helpful operation/source context.
- Business layer: decide retry, fail-fast, or per-item failure recording.
- API/CLI layer: translate errors into user-facing responses/error codes and messages; keep stack traces in appropriate diagnostic channels.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `Files.readString(path)` directly inside `map` | Lambda fails to compile due to checked `IOException` | Catch/wrap `UncheckedIOException` or handle I/O outside stream |
| Catching only `IOException` outside terminal operation | May miss `UncheckedIOException` from lazy traversal | Catch the right type at the corresponding boundary |
| Assuming `map` runs immediately when pipeline is declared | Errors only appear on `toList()`/terminal operation | Understand lazy evaluation |
| Not closing `Files.lines`/`Files.walk` | Can leak file/directory handles | `try-with-resources` around the entire terminal operation |
| Assuming `count()` closes the stream automatically | Resource still needs closing | Use `try-with-resources` |
| Using `reader.lines()` and closing only the Stream API | Caller-owned reader still needs closing | Manage `BufferedReader` lifecycle |
| Wrapping any `Exception` into `UncheckedIOException` | Wrong type or masks non-I/O bugs | Wrap only `IOException` |
| Catching and returning empty string on file read failure | Loses distinction between empty file and read error | Propagate error or model failure result |
| Unwrapping and discarding messages containing the path | Hard to know which file failed | Keep context in wrapper or new `IOException` with cause |
| Using `peek` for mandatory I/O side effects | May be skipped due to short-circuit/optimization | Use explicit processing rather than relying on `peek` |
| Using unbounded `parallel()` when traversing files | Excessive concurrent I/O, unpredictable side effects | Bound concurrency and pick a suitable architecture |
| Assuming first few elements succeeding means batch succeeded | Mid-stream error stops pipeline | Verify terminal operation completes; decide rollback/partial policy |
| Closing file stream only after `forEach` | Exception skips the close statement | Put both processing and resource inside try-with-resources |
| Logging only wrapper message and dropping cause | Loses root error location | Propagate/log cause and suppressed exceptions properly |

## 17. When Should You Use a `for` Loop Instead of the Stream API?

The Stream API fits when data transformations are concise, elements are largely independent, and error policies are simple. However, if you require:

- Per-file retries with explicit backoff;
- Aggregating all errors while continuing to process remaining items;
- Transactions, rollbacks, or multi-step coordinated resources;
- Closing multiple sources in a complex order;
- Guaranteeing all elements are processed even when one fails;
- Accurate progress reporting, cancellation handling, or resource contention control;

then a plain `for` loop is usually simpler and more transparent:

```java
List<String> contents = new ArrayList<>();
for (Path path : paths) {
    contents.add(Files.readString(path, StandardCharsets.UTF_8));
}
```

This is an **illustrative snippet** inside a method declaring `throws IOException`, requiring `List`, `ArrayList`, `Path`, `Files`, and `StandardCharsets`. No unchecked wrapper is needed because the `for` loop allows the method to declare `throws IOException` directly.

There is no rule that the Stream API is faster, cleaner, or more correct for every I/O problem. Choose the tool that **accurately expresses error behavior and resource lifecycles**.

## 18. Practice Exercises

1. Write the lambda `path -> Files.readString(path)` inside `Stream.map` and compile it. Explain why the compiler requires handling the checked exception.
2. Run `UncheckedIoPipelineDemo` and add `"gamma"` after `"broken"`. Explain why the second result list is not returned when an error occurs.
3. Create a method `readUtf8Unchecked(Path)`, add a message containing the file name, and verify `getCause()` is still an `IOException`.
4. Run `FileLinesDemo` on Java 17 and add a `"  "` line; compare `isBlank()` with `isEmpty()`.
5. Modify `FileLinesDemo` to read a non-existent file; distinguish errors occurring at `Files.lines` open time from errors occurring when a terminal operation traverses an open source.
6. Write a `Files.list(directory)` program with `try-with-resources`, print filenames after `sorted()`, and contrast with not closing the stream.
7. Practice `BufferedReader.lines()` inside `try (BufferedReader reader = ...)`; explain whether the owner is the reader or the returned stream.
8. Run `ReadFilesWithStream`, replace `throw failure.getCause()` with `throw new IOException("Batch failed", failure)`, and observe the cause chain in the stack trace.
9. Write an `IOFunction<T,R>`/`unchecked` adapter, apply it to `Files.readString`, then add a unit test ensuring `IllegalArgumentException` is never converted into `UncheckedIOException`.
10. Design a `Result<T>` type holding either a success value or an `IOException` per file. Compare its behavior with a fail-fast pipeline when one out of ten files is unreadable.
11. Use `limit(1)` and `findFirst()` to demonstrate a pipeline can skip elements; explain why `peek` must not be used for mandatory I/O.
12. Propose a concurrency-limiting design if you need to check 10,000 files while opening at most 16 files at once.

## 19. Summary

`UncheckedIOException` serves as a clean bridge between **checked I/O exceptions** and **Stream API/lambdas that do not declare checked exceptions**. It preserves the original `IOException` via `getCause()` while allowing errors to propagate through `Function`, `Predicate`, `Consumer`, or lazy pipelines.

Three core principles:

1. **Wrap at the right boundary:** convert only `IOException` to `UncheckedIOException` when needed, with useful context; at the public API boundary, choose whether to keep it unchecked or convert back to checked per contract.
2. **Remember laziness:** errors may occur when the terminal operation runs, not when the pipeline is constructed; short-circuiting and parallelism affect which data gets processed.
3. **Preserve resource lifecycles:** `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` can open resources that must be closed. Wrap **the entire stream consumption period** in `try-with-resources`; with `BufferedReader.lines()`, the owner is usually the reader opened by the caller.

If an I/O workflow requires reporting multiple errors, retries, rollbacks, or complex resource management, consider a `for` loop or a dedicated abstraction. The goal is **accurate data semantics, error policies, and ownership**, not forcing the Stream API at any cost.

### References

- Java SE 17 API: [`UncheckedIOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/UncheckedIOException.html), [`IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html).
- Java SE 17 API: [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`BufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html).
- Java SE 17 API: [`Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [`Function`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html), [`AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html).

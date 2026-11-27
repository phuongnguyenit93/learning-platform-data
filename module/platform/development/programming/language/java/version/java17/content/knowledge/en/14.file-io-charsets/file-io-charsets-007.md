# Closing Resource Streams with try-with-resources in Java 17

**Topic:** Java 17  
**Chapter:** File I/O and Character Encodings  
**Lesson:** Closing Resource Streams with try-with-resources

When working with files, streams, sockets, or database connections, a program typically must release resources after finishing. If you forget to close them, the application can hold onto file descriptors, sockets, buffers, or connections longer than necessary, causing resource leaks and subsequent failures.

Java provides the **try-with-resources** construct to call `close()` automatically on resources once the `try` block completes. This syntax guarantees resource release whether the `try` block finishes normally or exits via an exception or `return`.

In Java 17, try-with-resources has been a stable feature since Java 7; syntax allowing pre-declared resource variables outside the `try` header was added in Java 9. This is Java's standard mechanism for managing objects with an explicit closing lifecycle.

This lesson focuses on:

- Requirements for an object to be used in try-with-resources.
- Declaring one or multiple resources.
- Initialization and closing order.
- How Java handles exceptions when both the block body and `close()` fail.
- Syntax for using pre-declared resource variables.
- Applications with UTF-8 text files, byte streams, and JDBC.
- Designing resource ownership to prevent accidental or repeated closing.

## 1. Why Must Resources Be Closed?

Some Java objects represent resources outside the Java heap:

- `InputStream` and `OutputStream` read/write bytes.
- `Reader` and `Writer` read/write characters.
- `BufferedReader` and `BufferedWriter` provide buffering for text operations.
- `Socket` and socket-backed streams manage network connections.
- `Connection`, `Statement`, `PreparedStatement`, and `ResultSet` manage JDBC resources.
- `ZipFile` and similar APIs manage files or archive structures.

Not every Java object requires `close()`. Ordinary objects such as `String`, `List`, or `BigDecimal` do not represent closeable external resources. You must close objects whose API contracts require resource release.

Example reading a file:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadFileExample {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("message.txt");

        BufferedReader reader =
                Files.newBufferedReader(path, StandardCharsets.UTF_8);

        String line;
        while ((line = reader.readLine()) != null) {
            System.out.println(line);
        }

        reader.close();
    }
}
```

This snippet closes `reader` when reading completes normally. However, if `readLine()` throws `IOException`, the method exits before reaching `reader.close()`. The resource may never be released.

You could place `close()` inside `finally`, but you would then have to handle `null` checks, exceptions thrown during closing, and ensuring a close error does not mask the original read error. Try-with-resources solves these problems directly in the language syntax.

## 2. Requirement: Resources Must Implement AutoCloseable

Try-with-resources only accepts resources whose types implement `java.lang.AutoCloseable`.

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

When the `try` block finishes, Java automatically invokes `close()` on each resource that was successfully initialized.

`java.io.Closeable` is a sub-interface of `AutoCloseable`:

```java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
```

Consequently, standard I/O streams, readers, and writers work seamlessly with try-with-resources. `Closeable.close()` narrows the declared exception to `IOException`, whereas `AutoCloseable.close()` declares `Exception`.

Key points to understand:

- `AutoCloseable` describes an object that supports a close operation.
- Implementing `AutoCloseable` does not mean the object closes itself automatically when references are dropped.
- Java only invokes `close()` automatically at the end of a try-with-resources block.
- Custom classes can implement `AutoCloseable` to participate in this mechanism.
- If a resource expression evaluates to `null`, Java does not call `close()` on it.

### 2.1. Creating a Custom Resource

```java
class ReportSession implements AutoCloseable {

    public void write(String message) {
        System.out.println("Write: " + message);
    }

    @Override
    public void close() {
        System.out.println("Release report session");
    }
}
```

Using it with try-with-resources:

```java
try (ReportSession session = new ReportSession()) {
    session.write("Monthly report");
}
```

Upon leaving the `try` block, Java automatically calls `session.close()`. The developer does not have to remember to call `close()` on every `if`, `return`, or `catch` path.

If the close operation needs to signal errors, declare an appropriate exception:

```java
class FileSession implements AutoCloseable {

    @Override
    public void close() throws IOException {
        // Release resources; may throw IOException.
    }
}
```

Design `close()` to release resources cleanly, finish quickly, and avoid performing unrelated business logic.

## 3. Basic Syntax of try-with-resources

General structure:

```java
try (ResourceType resource = createResource()) {
    // Use resource here
} catch (SomeException exception) {
    // Handle errors if needed
} finally {
    // Runs after the resource has already been closed
}
```

The parenthesized portion is the *resource specification*. One or more resources can be declared, separated by semicolons.

Example reading a text file:

```java
Path path = Path.of("message.txt");

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

When the `try` block exits, `reader.close()` is called automatically. This happens regardless of whether:

- Reading reaches the end of the file.
- A `return` executes inside the block.
- A `break` or `continue` exits the block.
- An exception is thrown inside the body.
- An exception is handled in `catch` after the resource is closed.

### 3.1. The catch Block Runs After Resources Are Closed

```java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

    System.out.println(reader.readLine());

} catch (IOException exception) {
    System.err.println("Unable to read file: " + exception.getMessage());
}
```

The execution order is:

1. Java initializes the resource.
2. The `try` body executes.
3. When the body completes, `close()` is called.
4. After closing resources, control moves to the matching `catch` block if an exception occurred.
5. `finally` runs if present.

Therefore, inside `catch`, the resource is already closed. Do not continue using that reader/stream as if it were still open.

### 3.2. The finally Block Can Still Be Used Normally

`finally` remains useful for non-resource cleanup tasks, such as updating state or releasing another resource that does not support `AutoCloseable`.

```java
try (var reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    process(reader);
} catch (IOException exception) {
    logReadFailure(exception);
} finally {
    updateRequestMetrics();
}
```

Order matters: resources are closed before any associated `catch` or `finally` block runs. You no longer need to put `reader.close()` in `finally`.

## 4. Multiple Resources in One try Statement

Multiple resources can be declared in the same parentheses:

```java
try (
    var reader = Files.newBufferedReader(input, StandardCharsets.UTF_8);
    var writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)
) {
    String line;

    while ((line = reader.readLine()) != null) {
        writer.write(line);
        writer.newLine();
    }
}
```

In this example:

- `reader` is created first.
- `writer` is created second.
- When leaving the `try` block, `writer` is closed first.
- Then `reader` is closed.

### 4.1. Resources Are Closed in Reverse Order

The closing rule is **last-in, first-out (LIFO)**: resources initialized later are closed first.

```text
Initialization:
  1. resource A
  2. resource B
  3. resource C

Automatic closing:
  1. resource C
  2. resource B
  3. resource A
```

This ordering is helpful when later resources depend on earlier ones. For instance, when a writer/reader or wrapper is built on top of an underlying stream, closing the wrapper first lets it finish flushing before the underlying stream is closed.

### 4.2. Note on Failure While Initializing a Second Resource

Suppose `reader` opens successfully, but creating `writer` fails. Java still closes the already-initialized `reader`.

```java
try (
    var reader = Files.newBufferedReader(input, StandardCharsets.UTF_8);
    var writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8)
) {
    copy(reader, writer);
}
```

If initializing `writer` throws an exception:

1. The `try` body does not execute.
2. The successfully created `reader` is closed.
3. The exception from initializing `writer` is propagated out.
4. If `reader.close()` also throws an exception, that close failure is attached as a suppressed exception on the initialization exception.

This is a critical safeguard: already-opened resources are never leaked just because another resource in the same header failed to open.

## 5. Closing Resources and Suppressed Exceptions

A practical scenario is when both the `try` body and `close()` throw exceptions.

With manual closing in `finally`, the close exception can overwrite and hide the original exception. Try-with-resources follows dedicated rules to preserve the primary exception.

### 5.1. The Exception from the Body Is the Primary Exception

```java
class DemoResource implements AutoCloseable {

    @Override
    public void close() throws IOException {
        throw new IOException("close failed");
    }
}

public class SuppressedExample {
    public static void main(String[] args) {
        try (DemoResource resource = new DemoResource()) {
            throw new IOException("body failed");
        } catch (IOException exception) {
            System.out.println("Primary: " + exception.getMessage());

            for (Throwable suppressed : exception.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Output:

```text
Primary: body failed
Suppressed: close failed
```

The exception thrown from the `try` body is kept as the **primary exception**. Exceptions thrown while closing resources are attached to the primary exception via `addSuppressed()` and can be inspected via `getSuppressed()`.

This ensures you do not lose the root cause of the operation failure.

### 5.2. If the Body Succeeds but close Fails

```java
try (DemoResource resource = new DemoResource()) {
    System.out.println("Body completed");
} catch (IOException exception) {
    System.out.println("Caught: " + exception.getMessage());
}
```

Output:

```text
Body completed
Caught: close failed
```

When the body does not throw an exception, the first failure encountered during closing is propagated as the primary exception. If multiple resources fail to close, subsequent close exceptions are recorded as suppressed exceptions on the first close exception.

### 5.3. Inspecting Suppressed Exceptions for Diagnostics

```java
try (DemoResource resource = new DemoResource()) {
    doWork();
} catch (IOException exception) {
    logger.error("Operation failed", exception);

    for (Throwable suppressed : exception.getSuppressed()) {
        logger.error("Resource close also failed", suppressed);
    }
}
```

Many modern loggers print suppressed exceptions in the primary exception's stack trace. Even so, `getSuppressed()` remains useful when you need to handle or report them individually.

Do not confuse a suppressed exception with a cause:

- `getCause()` returns the underlying cause linked via `initCause()` or a constructor.
- `getSuppressed()` returns secondary errors raised while closing resources after a primary error already occurred.

### 5.4. Multiple Resources Failing on Close

```java
class NamedResource implements AutoCloseable {
    private final String name;

    NamedResource(String name) {
        this.name = name;
    }

    @Override
    public void close() throws IOException {
        System.out.println("Closing " + name);
        throw new IOException("close " + name);
    }
}

public class MultipleCloseFailures {
    public static void main(String[] args) {
        try (
            NamedResource first = new NamedResource("first");
            NamedResource second = new NamedResource("second")
        ) {
            throw new IOException("body");
        } catch (IOException exception) {
            System.out.println("Primary: " + exception.getMessage());

            for (Throwable suppressed : exception.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Output:

```text
Closing second
Closing first
Primary: body
Suppressed: close second
Suppressed: close first
```

Resources close in reverse order. Since the body threw an exception, the close failures from `second` and `first` are both attached to the `body` exception in the order they occurred.

## 6. Using Pre-Declared Resource Variables (Java 9+)

Since Java 9, a resource specification can reference a previously declared resource variable, provided that variable is `final` or *effectively final*.

Example:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    System.out.println(reader.readLine());
}
```

This syntax is useful when:

- The resource is created in an earlier branch or processing step.
- You want the variable in scope outside the `try` block.
- An API receives an already-open resource and needs to manage its closing within a specific scope.

### 6.1. Variables Must Be final or Effectively Final

Valid example:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    process(reader);
}
```

After initial assignment, `reader` is never reassigned. It is effectively final.

Invalid example:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

reader = Files.newBufferedReader(otherPath, StandardCharsets.UTF_8);

// Invalid: reader was reassigned, so it is no longer effectively final.
try (reader) {
    process(reader);
}
```

If you need to create another resource, declare a new variable or declare the resource directly inside the `try` specification.

### 6.2. Variable Scope Differences

Declaring a resource directly inside `try`:

```java
try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    process(reader);
}

// reader is no longer in scope here.
```

Using a pre-declared variable:

```java
BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8);

try (reader) {
    process(reader);
}

// reader is still in lexical scope,
// but the resource is already closed and must not be used further.
```

A variable remaining in lexical scope does not mean the resource is still open. Once the try-with-resources block finishes, do not continue reading or writing through it.

### 6.3. Using Multiple Pre-Declared Variables

```java
BufferedReader reader =
        Files.newBufferedReader(input, StandardCharsets.UTF_8);
BufferedWriter writer =
        Files.newBufferedWriter(output, StandardCharsets.UTF_8);

try (reader; writer) {
    copy(reader, writer);
}
```

The variables must be final/effectively final. They still close in reverse order of how they are listed in the resource specification: `writer` first, `reader` second.

This syntax has been available since Java 9 and works as expected in Java 17.

## 7. Reading and Writing Text Files with UTF-8

When working with text, specify the charset explicitly so data does not depend on the host machine's default configuration.

### 7.1. Reading a File with BufferedReader

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8Reader {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("input.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        }
    }
}
```

`Files.newBufferedReader(path, UTF_8)` creates a buffered reader using UTF-8. If the file does not exist, cannot be read, or experiences an I/O error, the method can throw `IOException`; if the reader was successfully created, try-with-resources still closes it during error handling.

### 7.2. Writing a File with BufferedWriter

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class Utf8Writer {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("output.txt");

        try (BufferedWriter writer =
                     Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {

            writer.write("Hello Java 17");
            writer.newLine();
            writer.write("Try-with-resources");
        }
    }
}
```

When the `try` block ends, `writer.close()` is called. Closing the writer also flushes its buffer according to the writer contract; you do not need to call `flush()` manually just to ensure buffered data is written before closing.

By default, `Files.newBufferedWriter(path, charset)` opens the file for writing, creates it if needed, and truncates any existing file. If appending is required, pass the appropriate `StandardOpenOption` values.

### 7.3. Copying Text Content

```java
static void copyText(Path source, Path target) throws IOException {
    try (
        BufferedReader reader =
                Files.newBufferedReader(source, StandardCharsets.UTF_8);
        BufferedWriter writer =
                Files.newBufferedWriter(target, StandardCharsets.UTF_8)
    ) {
        String line;

        while ((line = reader.readLine()) != null) {
            writer.write(line);
            writer.newLine();
        }
    }
}
```

Both reader and writer are closed automatically. `writer` closes before `reader` because `writer` is declared second.

**Content note:** `readLine()` strips line terminators; `newLine()` writes the platform's line separator. Therefore, this example copies text line by line while potentially normalizing line endings. If you need an exact byte-for-byte copy, use byte streams or `Files.copy()` rather than going through `readLine()`.

## 8. Using try-with-resources with Byte Streams

When working with images, PDFs, archives, or binary data, use `InputStream` and `OutputStream`.

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void copyBytes(Path source, Path target) throws IOException {
    try (
        InputStream input = Files.newInputStream(source);
        OutputStream output = Files.newOutputStream(target)
    ) {
        byte[] buffer = new byte[8192];
        int count;

        while ((count = input.read(buffer)) != -1) {
            output.write(buffer, 0, count);
        }
    }
}
```

`try-with-resources` guarantees both streams are closed even if `read()` or `write()` throws `IOException`.

### 8.1. Wrapper Streams and Ownership

A wrapper such as `BufferedInputStream` is typically constructed around another stream:

```java
try (InputStream input = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(input)) {
    // Read from buffered.
}
```

When `buffered` is closed, it normally closes the underlying stream as well. Then try-with-resources also invokes `input.close()` because `input` was declared as a resource too. Many standard stream implementations tolerate repeated closes safely, but you should not assume every custom `AutoCloseable` is idempotent.

When a wrapper owns the underlying stream, you can declare only the wrapper as the resource:

```java
try (BufferedInputStream input =
             new BufferedInputStream(Files.newInputStream(path))) {
    // Use input.
}
```

When the wrapper closes, it assumes responsibility for closing the underlying stream. Choose a clear ownership model so multiple layers do not mistakenly attempt to close the same resource.

## 9. Using try-with-resources with JDBC

Modern JDBC interfaces such as `Connection`, `Statement`, `PreparedStatement`, and `ResultSet` all support `AutoCloseable`.

Example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

static void listUsers(DataSource dataSource) throws SQLException {
    String sql = "SELECT id, username FROM users";

    try (
        Connection connection = dataSource.getConnection();
        PreparedStatement statement = connection.prepareStatement(sql);
        ResultSet resultSet = statement.executeQuery()
    ) {
        while (resultSet.next()) {
            long id = resultSet.getLong("id");
            String username = resultSet.getString("username");

            System.out.println(id + ": " + username);
        }
    }
}
```

Closing order:

1. `ResultSet`.
2. `PreparedStatement`.
3. `Connection`.

This order ensures dependent objects are closed before the objects from which they were obtained.

### 9.1. Closing a Connection Does Not Necessarily Close the Physical Socket

In applications using a connection pool, calling `Connection.close()` usually returns the connection to the pool for reuse rather than closing the underlying physical socket or database session immediately. Nevertheless, the application must still call `close()` so the pool knows the connection has been returned.

Try-with-resources works seamlessly with both direct connections and pooled connections, because it invokes `close()` properly per the JDBC contract.

### 9.2. Using PreparedStatement and Parameter Binding

Try-with-resources manages resource lifetimes; it does not protect SQL statements from injection on its own. Use placeholders and bind parameters:

```java
String sql = "SELECT id, username FROM users WHERE status = ?";

try (
    Connection connection = dataSource.getConnection();
    PreparedStatement statement = connection.prepareStatement(sql)
) {
    statement.setString(1, "ACTIVE");

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getString("username"));
        }
    }
}
```

`ResultSet` is declared in a nested `try` block and closes before the outer block closes `PreparedStatement` and then `Connection`.

## 10. try-with-resources with return, break, and Exceptions

A major strength of try-with-resources is that resource closing does not depend on how execution exits the block.

### 10.1. Resources Still Close on return

```java
static String firstLine(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
```

Java evaluates the return value, closes the reader, and then completes the `return`. If `close()` throws an exception during normal return, the close exception prevents the return from completing normally.

### 10.2. Resources Still Close on Exception

```java
try (var input = Files.newInputStream(path)) {
    throw new IllegalStateException("Processing failed");
}
```

Even when an exception is thrown in the body, Java still calls `input.close()`. If `close()` also fails, that error is attached to the primary exception as a suppressed exception.

### 10.3. break and continue

```java
for (Path path : files) {
    try (var reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        if (shouldSkip(path)) {
            continue;
        }

        process(reader);

        if (isComplete(path)) {
            break;
        }
    }
}
```

Each time execution leaves the try-with-resources block, the current iteration's reader is closed before the loop continues or breaks.

## 11. Comparison with Manual Closing in finally

Before try-with-resources existed, code commonly used `try/finally`:

```java
InputStream input = null;

try {
    input = Files.newInputStream(path);
    process(input);
} finally {
    if (input != null) {
        input.close();
    }
}
```

This approach can close resources, but requires handling several details manually:

- The variable must allow `null`.
- You must ensure `close()` is invoked when an exception occurs.
- If both the body and `close()` throw exceptions, the exception from `finally` can mask the original exception.
- With multiple resources, nested blocks or multiple close branches become verbose and error-prone.

Try-with-resources expresses resource ownership directly and applies the language's standard suppressed-exception rules.

Do not manually write `close()` inside `finally` for a resource already declared in the resource specification; calling it manually and letting try-with-resources call it again can cause unintended duplicate closes.

## 12. Designing AutoCloseable for Custom Resources

When a class owns a file, socket, or another resource, implement `AutoCloseable` so callers can manage it with try-with-resources.

Example:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

final class DirectoryScanner implements AutoCloseable {

    private final Stream<Path> paths;

    DirectoryScanner(Path directory) throws IOException {
        this.paths = Files.list(directory);
    }

    Stream<Path> paths() {
        return paths;
    }

    @Override
    public void close() {
        paths.close();
    }
}
```

Usage:

```java
try (DirectoryScanner scanner =
             new DirectoryScanner(Path.of("logs"))) {
    scanner.paths()
            .filter(path -> path.toString().endsWith(".log"))
            .forEach(System.out::println);
}
```

`Files.list()` returns a stream backed by system resources, so it must be closed after use. `DirectoryScanner` owns that stream and closes it inside `close()`.

### 12.1. Clarify Resource Ownership

An important design principle:

- If a method creates and returns a new resource, the caller is typically responsible for closing it.
- If an object receives a resource supplied by the caller without taking ownership, it should not arbitrarily close that resource.
- If an object creates and owns a resource internally, that object's `close()` is responsible for releasing it.
- Whenever transferring ownership, document it clearly in the API or documentation.

Example of a method receiving an `InputStream`:

```java
static void parse(InputStream input) throws IOException {
    // If the contract says the caller owns input,
    // this method does not close input.
    parseData(input);
}
```

The caller manages the lifecycle:

```java
try (InputStream input = Files.newInputStream(path)) {
    parse(input);
}
```

If `parse()` closes `input` while the caller also manages it, behavior becomes unpredictable. Keep ownership consistent with the API contract.

### 12.2. Designing close() to Be Safe When Called

For custom resources, track closed state and avoid releasing the same native resource multiple times if the underlying API forbids it.

```java
final class ManagedResource implements AutoCloseable {

    private boolean closed;

    public void use() {
        if (closed) {
            throw new IllegalStateException("Resource is closed");
        }

        System.out.println("Using resource");
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("Resource released");
        }
    }
}
```

This illustrates a simple, single-threaded resource without concurrency synchronization. If an object is shared across threads, design appropriate synchronization for its state and `close()` operation.

`AutoCloseable` does not automatically make a class thread-safe. Likewise, do not assume every `close()` implementation is idempotent; check the contract of the resource in use.

## 13. Nested Resources and Management Scope

Nested try-with-resources blocks can be used when one resource's lifecycle depends on another or requires a narrower closing scope.

```java
try (var connection = dataSource.getConnection()) {
    try (var statement =
                 connection.prepareStatement("SELECT id FROM users")) {

        try (var resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                System.out.println(resultSet.getLong(1));
            }
        }
    }
}
```

This makes ordering explicit, though verbose. Resources sharing the same scope can be grouped into a single `try`:

```java
try (
    var connection = dataSource.getConnection();
    var statement = connection.prepareStatement("SELECT id FROM users");
    var resultSet = statement.executeQuery()
) {
    while (resultSet.next()) {
        System.out.println(resultSet.getLong(1));
    }
}
```

Choose structure based on actual lifecycles:

- Use a single `try` when resources are created together and should close in the same scope.
- Use nested `try` blocks when an inner resource only exists during a smaller sub-step.
- Avoid deep nesting out of habit if one resource list expresses the scope more clearly.

## 14. Common Mistakes

### Mistake 1. Forgetting to Close Resources on Exception

Use try-with-resources so Java closes resources automatically on all exit paths.

### Mistake 2. Using Objects That Do Not Implement AutoCloseable

Only types compatible with `AutoCloseable` can appear in a resource specification. If a custom class manages resources, consider implementing this interface.

### Mistake 3. Continuing to Use a Resource After the try Block

Once the `try` block exits, the resource is closed. Even if a variable remains in scope, it can no longer be treated as an open resource.

### Mistake 4. Closing in the Wrong Order

Java closes resources in reverse order of initialization. When managing dependent resources, declare them in creation order and rely on LIFO to close wrappers before underlying resources.

### Mistake 5. Letting close Errors Mask Processing Errors

Try-with-resources preserves the body exception as the primary exception and attaches close errors to `getSuppressed()`.

### Mistake 6. Thinking catch Runs Before Closing

Resources are closed before control enters any `catch` or `finally` block attached to that `try`.

### Mistake 7. Using a Non-Effectively-Final Variable in the Resource Specification

With Java 9+ `try (reader)` syntax, the variable must be `final` or effectively final. If it was reassigned, introduce a new variable or declare the resource directly inside `try`.

### Mistake 8. Declaring a Wrapper-Owned Resource Separately and Double-Closing

Wrappers usually close their underlying resource. Clarify ownership and close responsibilities so multiple layers do not close a non-idempotent resource twice.

### Mistake 9. Assuming try-with-resources Handles Encoding

Try-with-resources manages resource lifecycles; it does not choose charsets. For text, specify a charset explicitly, such as `StandardCharsets.UTF_8`.

### Mistake 10. Confusing close with Transaction Commit

Closing a `Connection` does not replace explicit transaction commit/rollback rules. When managing JDBC transactions manually, commit or roll back explicitly before the connection is closed or returned to the pool.

### Mistake 11. Swallowing Exceptions Inside close()

Do not catch and silently ignore exceptions inside `close()` if those errors matter to resource release. Follow the resource's contract and let try-with-resources preserve error details when needed.

## 15. Step-by-Step Workflow for Choosing and Using try-with-resources

When an API returns a closeable object, follow these steps:

1. **Identify the resource type:** check whether the class implements `AutoCloseable` or `Closeable`.
2. **Determine ownership:** who creates the resource and who is responsible for closing it?
3. **Choose the scope:** identify the shortest code block that needs the resource.
4. **Declare in try:** use `try (Resource resource = ...)`; for final/effectively final variables, `try (resource)` can be used since Java 9.
5. **Declare in dependency order:** resources created later will close first.
6. **Handle exceptions:** catch relevant exceptions outside the `try` block; inspect suppressed exceptions if close failures matter.
7. **Specify charsets for text:** use UTF-8 or the protocol-specified charset.
8. **Verify the close() contract:** do not assume every resource is thread-safe or safe to close repeatedly.

## 16. Complete Example: Reading Configuration and Ensuring File Closure

Save the file as `TryWithResourcesDemo.java`:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TryWithResourcesDemo {

    static int countNonEmptyLines(Path path) throws IOException {
        int count = 0;

        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (!line.isBlank()) {
                    count++;
                }
            }
        }

        return count;
    }

    public static void main(String[] args) {
        Path path = Path.of("config.txt");

        try {
            int count = countNonEmptyLines(path);
            System.out.println("Non-empty lines: " + count);
        } catch (IOException exception) {
            System.err.println("Cannot read configuration: "
                    + exception.getMessage());
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 TryWithResourcesDemo.java
java TryWithResourcesDemo
```

Output depends on the contents of `config.txt`. The key point is that the reader is closed before `countNonEmptyLines()` returns or propagates an exception.

## 17. Practice Exercises

### Exercise 1. Determining When Closing Occurs

```java
try (var input = Files.newInputStream(path)) {
    System.out.println(input.read());
} catch (IOException exception) {
    System.out.println("error");
}
```

**Question:** Is `input.close()` called before or after entering `catch`?

**Answer:** Before. The resource is closed upon leaving the `try` body, before `catch` executes.

### Exercise 2. Determining Closing Order

```java
try (
    Resource a = new Resource("A");
    Resource b = new Resource("B");
    Resource c = new Resource("C")
) {
    work();
}
```

**Question:** In what order is `close()` called?

**Answer:** C, B, A. Resources close in reverse order of declaration.

### Exercise 3. Which Exception Is Primary?

The `try` body throws `IOException("read")`; `close()` throws `IOException("close")`.

**Answer:** `"read"` is the primary exception; `"close"` appears in `getSuppressed()`.

### Exercise 4. What If the Body Succeeds but close Fails?

**Answer:** The exception from closing is propagated as the primary exception and can be handled in `catch`.

### Exercise 5. Can a Resource Variable Be Reassigned?

```java
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
reader = Files.newBufferedReader(other, StandardCharsets.UTF_8);

try (reader) {
    process(reader);
}
```

**Answer:** Invalid. `reader` was reassigned, so it is no longer effectively final. Using a pre-declared variable requires it to be `final` or effectively final.

### Exercise 6. Should You Call close Manually Inside the try Block?

```java
try (var input = Files.newInputStream(path)) {
    process(input);
    input.close();
}
```

**Answer:** No. Java calls `close()` when the block ends; calling it manually can cause double closing. Only close early if the API contract and lifecycle design explicitly require it, keeping in mind try-with-resources will still invoke `close` at the end.

### Exercise 7. Does Reading Text Need an Explicit Charset?

**Answer:** Yes. Use an overload accepting `StandardCharsets.UTF_8` or the protocol-defined charset so data remains consistent across environments.

### Exercise 8. Does `Connection.close()` Always Close the Physical Socket?

**Answer:** Not necessarily. With a connection pool, `close()` typically returns the connection to the pool. The application must still call `close` to return the resource to the pool.

## 18. Official References

- [Java Language Specification 17 — `14.20.3 try-with-resources`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): rules for initialization, resource closing, and suppressed exceptions.
- [JDK 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): contract of `close()` and use in try-with-resources.
- [JDK 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): I/O resource closing interface and relationship with `AutoCloseable`.
- [JDK 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getSuppressed()` and the suppressed exception mechanism.
- [OpenJDK JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): Java 9 change allowing pre-declared final/effectively final variables in try-with-resources.
- [JDK 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): APIs for creating file-backed readers, writers, and streams.
- [JDK 17 API — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): JDBC connection lifecycle and close semantics.

**Key takeaway:** Declare every closeable resource in `try (...)` so Java calls `close()` automatically when exiting the block. Resources are initialized in declaration order and closed in reverse order. If both the body and `close()` fail, the body's error stays the primary exception while close errors go into `getSuppressed()`. Use explicit charsets for text files and clearly define resource ownership in your application's APIs.

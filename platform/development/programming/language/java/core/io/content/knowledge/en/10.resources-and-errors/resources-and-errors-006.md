# Closing Wrapped Streams, Shared Resources, and Caller-Passed Resources

## 1. The Core Question: Who Is Responsible for Closing a Resource?

In Java I/O, we frequently write a chain of wrapper classes around a file, socket, or other source/destination:

```text
Application
   │ reads characters line by line
   ▼
BufferedReader
   │ reads characters
   ▼
InputStreamReader (UTF-8 decoding)
   │ reads bytes
   ▼
FileInputStream / Files.newInputStream
   │
   ▼
OS-managed file
```

Each class has one job: `FileInputStream` reads bytes from the file; `InputStreamReader` converts bytes into characters; `BufferedReader` adds buffering and `readLine()`. However, these objects are **not completely independent in lifecycle**. Closing the outer wrapper typically closes the inner layers and ultimately releases the underlying file or connection.

The crucial question is not merely "does a stream need `close()`?", but rather:

- **Who creates and owns** the underlying resource?
- **Who is authorized to end** usage of the resource?
- Does a wrapper **forward `close()`** down to the underlying resource?
- If the same resource is used by multiple components, **which component closes it**?
- If a method is passed an `InputStream`, `OutputStream`, `Reader`, or `Writer` from a caller, does the method's contract **transfer ownership** or only **borrow it temporarily**?

For a stream bound to a file or socket, forgetting to close can leak OS resources or leave buffered data incomplete. Conversely, closing a shared stream too early can prevent the rest of the application from reading or writing further.

**Default API design principle:** the side that **owns the resource** is responsible for closing it; a method that only **borrows a stream** normally reads/writes per contract and returns without closing it on its own. Exceptions must be documented clearly in the API documentation.

## 2. Distinguishing Resource, Wrapper, and Ownership

A *resource* is an object with a managed lifecycle, such as a file handle, network connection, native memory region, or I/O construct requiring finalization before termination. A *wrapper* is an object that adds behavior to another resource or stream: buffering, byte/character conversion, decompression, encoding, typed data writing, etc.

Example:

```java
InputStream raw = Files.newInputStream(path);
InputStream buffered = new BufferedInputStream(raw);
```

This is an **illustrative snippet**, requiring `java.io.InputStream`, `BufferedInputStream`, `java.nio.file.Files`, `Path`, and `IOException` handling. If code creates both `raw` and `buffered`, that code normally owns the stream and must close them using a safe strategy. With this common wrapping pattern, closing `buffered` closes `raw`.

The same underlying stream can be treated in different ways:

| Scenario | Who Owns It? | Who Closes It? |
| --- | --- | --- |
| Method opens `Files.newInputStream(path)` itself for local processing | The method opening the stream | The method closes it, typically via try-with-resources |
| Method receives `InputStream in` from caller only to parse | Caller | Caller closes; the parse method does not close if contract says borrowed |
| Factory opens a file and returns a `BufferedReader` to caller | Caller receives ownership through return value | Caller closes the returned reader |
| Application uses `System.in`, `System.out`, `System.err` | Runtime/high-level application | Do not close arbitrarily in libraries |
| Two components share one application-managed stream | High-level coordinator component | Closes once all consumers are finished |
| `GZIPOutputStream` created and owned by a method to produce GZIP format | Method or caller receiving stream, per API | Owner must call `finish`/`close` at the right time |

**A wrapper does not automatically become the rightful owner just because it holds a reference to an underlying stream.** Yet many standard wrappers **forward close**, so if an API is only permitted to borrow a resource, we must design it so we do not inadvertently call `close()` on that wrapper.

## 3. How Does Close Propagate from Outside to Inside?

Many `java.io` wrappers follow this pattern: when closing the outer wrapper, it flushes/finalizes its own state and closes the inner delegate object.

```text
close(BufferedOutputStream)
    ├─ flushes buffered byte data
    └─ close(underlying OutputStream)
          └─ releases real resource (if any)
```

Some familiar wrappers:

| Wrapper | Lifecycle Behavior to Note |
| --- | --- |
| `BufferedInputStream` | `close()` closes the wrapped input stream |
| `BufferedOutputStream` | `close()` may flush buffered data and then close the underlying stream |
| `InputStreamReader` | `close()` closes the wrapped byte stream |
| `OutputStreamWriter` | `close()` completes writing/encoding and then closes the underlying stream |
| `BufferedReader` / `BufferedWriter` | `close()` closes the wrapped reader/writer |
| `DataInputStream` / `DataOutputStream` | `close()` normally forwards to the delegate stream |
| `GZIPInputStream` / `GZIPOutputStream` | `close()` ends the wrapped resource; GZIP output needs to finalize compression structure |
| `PrintWriter` / `PrintStream` | Have their own write/flush/close lifecycle and error-reporting mechanism; may close underlying target |

Exact behavior must be based on **the specific class's API**, not guessed from its name. For example, `ByteArrayInputStream` and `ByteArrayOutputStream` have `close()` methods that do not disable further use; `StringReader.close()` makes subsequent read operations invalid. The fact that a test using memory streams still works after close **does not prove** closing is safe for files or sockets.

### A Fully Owned Chain: Closing the Outer Layer Suffices

```java
Path path = Path.of("data.txt");
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(path), StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process.
    }
}
```

This is an **illustrative snippet**, requiring imports for `java.io.BufferedReader`, `InputStreamReader`, `java.nio.file.Files`, `Path`, `StandardCharsets`, and `IOException` handling. When `reader` closes, it closes `InputStreamReader`, which closes the file input stream. Calling `reader.close()` again in `finally` is unnecessary.

Note on **exceptions while building a wrapper chain**: if creating a wrapper could throw an exception after opening the underlying resource yet before the wrapper becomes the `try` resource, the underlying resource needs separate protection. A safer construction pattern when constructors carry risk is declaring the underlying resource directly in the `try` list, even though closing both wrapper and base at the end can trigger a repeated close call. Choose a structure matching the API and consider safety under repeated closing.

## 4. Try-with-resources: Recommended Mechanism for Self-Owned Resources

`try-with-resources` (Java 7+, enhanced syntax since Java 9) calls `close()` automatically on each resource variable implementing `AutoCloseable` or `Closeable`, even if the processing block throws an exception.

```java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
}
// out.close() is called before in.close().
```

This is an **illustrative snippet**, assuming `Path source`, `Path target`, and appropriate imports. Because `in` and `out` are two **independent** resources, declaring both in `try` is appropriate. With multiple resources, Java closes them in **reverse order of declaration**.

If one resource **wraps another**, such as `BufferedInputStream(raw)`, placing both `raw` and the wrapper in the `try` list exposes the base stream to potentially receiving **two close calls**:

```java
// raw is passed directly into wrapper; illustrates double close.
try (InputStream raw = Files.newInputStream(source);
     InputStream buffered = new BufferedInputStream(raw)) {
    // ...
}
// buffered.close() closes raw; then try-with-resources closes raw again.
```

Some streams are designed so repeated closing has no effect, yet **you cannot assume every `AutoCloseable` is idempotent**. If the wrapper constructor cannot fail after opening the resource (like simple wrapper constructors given valid arguments), a clean choice is declaring **only the outer wrapper** as the `try` resource. If you need to guard multiple initialization steps that may fail, protect the resource from the moment it opens and handle repeated closes per the specific contract.

### Errors During Processing and Errors on Close

`try-with-resources` preserves the primary exception thrown from the `try` body; errors thrown while closing resources are attached as **suppressed exceptions**. This is a major difference from careless manual `finally` blocks, where an exception from `close()` can mask the original error.

```java
try (InputStream in = Files.newInputStream(source)) {
    // If processing throws an exception...
} // ...and close also fails, the close error is attached as suppressed.
```

Because resources can fail both during use and during closing, suppressed exception details are valuable for diagnosis. Never catch `IOException` and ignore it simply because the code is "cleaning up".

## 5. Runnable Example: Verifying a Wrapper Closes the Underlying Stream

This example subclasses `ByteArrayOutputStream` to count calls to `close()`. This lets us verify closing behavior without needing real files.

**File `WrapperCloseDemo.java`:**

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class WrapperCloseDemo {
    static final class TrackingOutput extends ByteArrayOutputStream {
        private int closes;

        @Override
        public void close() throws IOException {
            closes++;
            super.close();
        }

        int closeCount() {
            return closes;
        }
    }

    public static void main(String[] args) throws IOException {
        TrackingOutput underlying = new TrackingOutput();

        try (BufferedOutputStream buffered = new BufferedOutputStream(underlying)) {
            buffered.write("ABC".getBytes(StandardCharsets.US_ASCII));
            System.out.println("Before close, bytes: " + underlying.size());
        }

        System.out.println("After close, text: "
                + underlying.toString(StandardCharsets.US_ASCII));
        System.out.println("Underlying close calls: "
                + underlying.closeCount());
    }
}
```

Commands with JDK 17+:

```bash
javac WrapperCloseDemo.java
java WrapperCloseDemo
```

**Exact stdout:**

```text
Before close, bytes: 0
After close, text: ABC
Underlying close calls: 1
```

`BufferedOutputStream` has a default buffer large enough to hold three bytes, so before closing, `underlying` has received zero bytes. When `try` finishes, the wrapper closes, flushing buffered bytes down to `underlying` and calling its `close()` exactly once in this example. We can still read the contents of `ByteArrayOutputStream` after close because this in-memory class permits it; do not extrapolate that **all** output streams allow accessing data after closing.

**Key implication:** if `underlying` were a socket or file stream passed in by a caller that still needed to use it, closing `BufferedOutputStream` over it would cut off the caller's work.

## 6. Caller-Passed Resources: Borrow or Take Ownership?

In Java libraries, a method like the following is very common:

```java
static void encode(Data record, OutputStream output) throws IOException {
    // Write record to output...
}
```

This is an **illustrative signature**; `Data` represents an undefined application data type. The signature **does not by itself tell you** who must close `output`. You must publish the contract:

- **Borrowed input/output:** caller retains ownership; method does not close the stream. If the method creates a temporary wrapper for local use, it must not unintentionally close the underlying resource either.
- **Transferred ownership:** caller hands over ownership; method is permitted to close the stream and must document this clearly, including on exception paths.
- **Resource returned by factory:** method creates a stream and returns a new `Closeable`; caller assumes responsibility for closing when done.
- **Shared resource:** multiple components use it together; a coordinator determines when to close rather than letting each consumer close at will.

The **borrowed** convention is especially useful when an API accepts `InputStream`/`OutputStream`, because the caller can compose multiple operations on the same stream:

```text
Caller creates output
  ├─ writeHeader(output)
  ├─ writeRecords(output)
  ├─ writeFooter(output)
  └─ caller flushes/closes(output) at the end
```

If `writeRecords(output)` closes output when done, `writeFooter(output)` can fail. That is an **ownership** bug, even when each piece of code passes standalone tests.

### What Should an API Borrowing OutputStream Do?

- Write data in the proper format, handling `IOException` per contract.
- Never call `output.close()` unless explicitly receiving ownership transfer.
- Agree on whether to `flush()`. Normally the owning caller decides when to flush; an interactive protocol may require flushing after each message.
- If using `BufferedOutputStream` or `OutputStreamWriter` to wrap a borrowed output, flush written data before returning **without closing the delegate**.
- If a wrapper uses an encoder or format requiring "ending the stream" to finalize (GZIP, ZIP, certain stateful encoders), you cannot arbitrarily substitute flush for close. Use `finish()` when supported or redesign ownership.

### What Should an API Borrowing InputStream Do?

- Read the required byte count, or up to EOF if the contract says so.
- Never close input if the caller still uses it.
- Consider buffering and stream position upon return: a wrapper may **read ahead** many bytes into its buffer, causing the caller's subsequent reads from the raw stream not to see data as expected.
- When coordinating multiple parsers/consumers over one stream, standardize framing, read bounds, and sharing **the exact same wrapper** rather than creating multiple independent read-ahead wrappers.

**Read-ahead and closing a stream are two separate issues:** even without calling close, a separate `BufferedReader` may hold pre-fetched bytes/characters in its buffer. Callers should not immediately resume using the raw stream without a buffering/position design.

## 7. Runnable Example: A Stream-Borrowing Method Must Not Close It

The following program proves processing code only writes data and lets the caller close. `TrackingOutput` records whether any `close()` call occurred.

**File `BorrowedStreamDemo.java`:**

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BorrowedStreamDemo {
    static final class TrackingOutput extends ByteArrayOutputStream {
        private boolean closed;

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }

        boolean isClosed() {
            return closed;
        }
    }

    // Contract: borrowed OutputStream; method neither closes nor flushes.
    static void writePart(OutputStream output, String value)
            throws IOException {
        output.write(value.getBytes(StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws IOException {
        TrackingOutput shared = new TrackingOutput();

        try {
            writePart(shared, "A");
            writePart(shared, "B");

            System.out.println("Closed before caller: " + shared.isClosed());
            System.out.println("Accumulated: "
                    + shared.toString(StandardCharsets.UTF_8));
        } finally {
            shared.close(); // Caller is the owner.
        }

        System.out.println("Closed by caller: " + shared.isClosed());
    }
}
```

Compile/run:

```bash
javac BorrowedStreamDemo.java
java BorrowedStreamDemo
```

**Exact stdout:**

```text
Closed before caller: false
Accumulated: AB
Closed by caller: true
```

Notice that **the caller invokes `writePart` twice on the same destination**, and only the caller closes the destination at the end. If `writePart` closed a real file stream itself, the second call would fail to write. `ByteArrayOutputStream` allows writing after close by specification, so the example uses a tracking flag rather than relying on that quirk.

When methods exchange multiple message parts over one connection, ownership matters even more: a single parser must not tear down the socket right after finishing one message if the protocol still uses that connection for the next message.

## 8. When a Self-Created Wrapper Closes a Borrowed Resource: What Are the Solutions?

This is a common mistake:

```java
// DANGEROUS illustrative code if output is owned by the caller:
static void badWrite(OutputStream output) throws IOException {
    try (BufferedOutputStream buffered = new BufferedOutputStream(output)) {
        buffered.write(42);
    } // buffered.close() also closes the caller-passed output.
}
```

`BufferedOutputStream` is a wrapper created inside the method, yet its delegate belongs to the caller. Using `try-with-resources` on the wrapper looks sensible on the surface, but violates the borrowing contract.

There are three design options depending on intent:

**Option 1 — Do not create a wrapper inside the method.** Have the caller create a buffered stream and pass it in:

```java
static void writeBytes(OutputStream output, byte[] bytes)
        throws IOException {
    output.write(bytes);
}
```

The caller decides when to flush/close; the method uses the given stream directly. This is usually the simplest approach.

**Option 2 — Create a temporary wrapper and flush, without closing.** Example:

```java
static void writeBuffered(OutputStream borrowed, byte[] bytes)
        throws IOException {
    BufferedOutputStream buffered = new BufferedOutputStream(borrowed);
    buffered.write(bytes);
    buffered.flush();
    // Do not close buffered because close would close borrowed.
}
```

Use this pattern only when **no finish/close step is required to finalize a format** and the wrapper is not retained across calls. If the caller controls the full lifecycle, it is better for the caller to maintain one long-lived wrapper to avoid creating repeated buffer layers and unnecessary flushes on every call.

**Option 3 — Use a wrapper with a "do not close delegate" policy** if a wrapper must be closed/finalized locally. You can create a `FilterOutputStream` overriding `close()` to only flush without forwarding close, then wrap it with the wrapper needing close:

```java
final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream delegate) {
        super(delegate);
    }

    @Override
    public void close() throws IOException {
        flush(); // Intentionally does not call super.close().
    }
}
```

This is an **illustrative class**; it requires importing `java.io.FilterOutputStream`, `OutputStream`, and `IOException`. It protects **the delegate from being closed** when the outer wrapper invokes close. However:

- It **does not stop other code holding a reference to the delegate from closing the delegate directly**.
- It does not make a resource owned elsewhere thread-safe.
- It does not replace the wrapper's buffering, encoding, or format requirements.
- If another wrapper already touched the raw resource earlier, ordering/read-ahead issues still apply.
- Some libraries already provide non-closing variants; understand the exact contract of whichever implementation you choose.

### Complete Java 17 Example: Closing BufferedOutputStream While Keeping Delegate Alive

**File `NonClosingWrapperDemo.java`:**

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class NonClosingWrapperDemo {
    static final class TrackingOutput extends ByteArrayOutputStream {
        private boolean closed;

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }

        boolean wasClosed() {
            return closed;
        }
    }

    static final class NonClosingOutputStream extends FilterOutputStream {
        NonClosingOutputStream(OutputStream target) {
            super(target);
        }

        @Override
        public void close() throws IOException {
            flush();
        }
    }

    static void writeBorrowed(OutputStream borrowed) throws IOException {
        try (BufferedOutputStream buffered =
                     new BufferedOutputStream(
                             new NonClosingOutputStream(borrowed))) {
            buffered.write("Hello".getBytes(StandardCharsets.US_ASCII));
        }
    }

    public static void main(String[] args) throws IOException {
        TrackingOutput shared = new TrackingOutput();
        try {
            writeBorrowed(shared);
            System.out.println("Closed after wrapper: " + shared.wasClosed());

            shared.write('!');
            System.out.println("Content: "
                    + shared.toString(StandardCharsets.US_ASCII));
        } finally {
            shared.close();
        }
        System.out.println("Closed by caller: " + shared.wasClosed());
    }
}
```

Run:

```bash
javac NonClosingWrapperDemo.java
java NonClosingWrapperDemo
```

**Exact stdout:**

```text
Closed after wrapper: false
Content: Hello!
Closed by caller: true
```

Here `BufferedOutputStream.close()` pushes bytes into `NonClosingOutputStream`, then invokes `close()` on the guard class. `NonClosingOutputStream.close()` only calls `flush()`, leaving `shared` open. After `writeBorrowed` returns, the caller continues writing `'!'` and finally closes the resource itself. This directly tests that **ownership was not accidentally transferred**.

## 9. Shared Resources: System.in, System.out, System.err

`System.in` is an `InputStream`; `System.out` and `System.err` are `PrintStream` instances provided by the JVM environment. They are normally shared by multiple pieces of code within the same process.

A common mistake:

```java
// Illustrative code: if the program still needs stdin, do not do this.
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8))) {
    System.out.println(reader.readLine());
} // Closes reader => InputStreamReader => System.in.
```

If other parts still need to read `System.in`, they may no longer be able to read. Similarly, closing a `PrintWriter` wrapping `System.out` can close stdout, causing subsequent `System.out.println` calls not to appear as expected. `PrintStream` may record an error flag rather than throwing `IOException` to callers, making failures easy to overlook.

**Sound strategy:** the top-level application controls the lifecycle of standard streams; library methods only borrow them. If you create a wrapper to read stdin continuously, keep that wrapper in one place and pass it to components per contract. Avoid multiple independent `Scanner`/`BufferedReader` instances consuming stdin simultaneously, because buffering lets each component read ahead and interfere with the others.

### Scanner Also Has Ownership Issues

```java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
// ...
scanner.close(); // Also closes underlying System.in.
```

This is an illustrative snippet requiring `java.util.Scanner` and `StandardCharsets`. `Scanner` implements `Closeable`; closing Scanner closes its underlying source if that source implements `Closeable`. Using `try-with-resources` with Scanner on a **self-owned file stream** is right, whereas using it on `System.in` requires considering the application lifecycle.

### PrintWriter, PrintStream, and Write/Close Errors

`PrintWriter` and `PrintStream` offer convenient `print`/`println` APIs, yet typically **do not throw checked `IOException` from print methods**. They record I/O errors internally, checkable via `checkError()`. Therefore, even when ownership is respected, if output integrity matters, your code needs an appropriate error-detection strategy; `close()` in `try-with-resources` on these classes does not necessarily surface errors like other `Writer` implementations do.

For output that must guarantee `IOException` reporting, using an appropriate `OutputStream`/`Writer` (and checking errors during write/flush/close) can be clearer than `PrintWriter` for strict requirements.

## 10. A Shared Resource Is Not Automatically Thread-Safe for Multiple Threads

There are two independent concerns:

1. **Lifecycle safety:** who is allowed to close, and when?
2. **Concurrency safety:** if two threads read/write the same stream together, are data and ordering preserved according to protocol?

Not closing a borrowed stream solves most lifecycle risks, yet **does not guarantee** concurrent writers will not interleave bytes, concurrent readers will not race for data, or buffered wrappers will handle concurrent access safely.

For example, two components share one `OutputStream` to emit JSON; if one writes a header and the other injects a message in the middle, the output is corrupted even though neither called `close()`. You must synchronize/assemble complete messages at the protocol level, or route writes through a single coordinator component.

When multiple components must share a resource:

- Designate a **single owner** responsible for closing.
- Define **borrowing scope** and when no active consumers remain.
- Design read/write protocols with explicit framing and ordering.
- Do not let each consumer create its own independent buffering wrapper if they share one stream position.
- With asynchronous processing, ensure the resource remains alive until all tasks complete.

In complex architectures, you can introduce an **owner/coordinator** or an abstraction exposing only required operations, rather than handing raw streams to many places and hoping none of them closes it.

## 11. Close Error Example: Suppressed Exceptions in try-with-resources

A stream can fail during read/write while `close()` also fails. Java retains the primary error and attaches the close error as suppressed.

**File `SuppressedCloseDemo.java`:**

```java
import java.io.IOException;

public class SuppressedCloseDemo {
    static final class FaultyResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FaultyResource resource = new FaultyResource()) {
            throw new IOException("work failed");
        } catch (IOException failure) {
            System.out.println("Main failure: " + failure.getMessage());
            System.out.println(
                    "Suppressed count: " + failure.getSuppressed().length);
            for (Throwable suppressed : failure.getSuppressed()) {
                System.out.println(
                        "Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Commands:

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

**Exact stdout:**

```text
Main failure: work failed
Suppressed count: 1
Suppressed: close failed
```

If no error occurs inside the `try` body, yet `close()` throws, the close error becomes the primary error. When multiple resources are open and multiple closes fail, Java can attach multiple suppressed exceptions; closing order remains **reverse order of declaration**.

The practical lesson is **do not mask the original error**. Avoid this manual pattern unless you handle exceptions properly:

```java
// DANGEROUS illustrative code: exception from close can mask initial exception.
try {
    doWork();
} finally {
    resource.close();
}
```

`doWork()` and `resource` here are conceptual placeholders in an explanatory pattern, not a standalone program. Whenever possible, prefer `try-with-resources`; when complex exception handling is required, preserve the original cause and suppressed exceptions rather than discarding them.

## 12. Flush, Finish, and Close: Three Non-Equivalent Actions

**`flush()`** requests pushing buffered data of an output stream down to the lower layer. It normally does not close the stream and does not promise bytes are durably written to disk.

**`finish()`** exists on certain format wrappers, such as `GZIPOutputStream` or `ZipOutputStream`, to complete the generated data structure **without closing the underlying stream**, per the implementation's contract. It does not exist on general `OutputStream`.

**`close()`** ends the resource/wrapper lifecycle; an outer wrapper normally flushes/finishes any remainder and then closes its delegate.

GZIP example:

```java
// Illustrative snippet: output owned by caller, GZIP wrapper is local.
GZIPOutputStream gzip = new GZIPOutputStream(output);
gzip.write(payload);
gzip.finish(); // Finalizes GZIP data.
gzip.flush();  // If needed to push data down to output.
               // Do not call gzip.close() if output must stay open.
```

This is an **illustrative snippet**, requiring `GZIPOutputStream`, `OutputStream output`, `byte[] payload`, and `IOException` handling. `finish()` can complete a GZIP member without closing the delegate, yet the design must specify whether the wrapper will be reused and who releases the wrapper. Do not apply this pattern indiscriminately to every format; other wrappers may **lack `finish()`** or require close to finalize.

**Note:** even while keeping the underlying output open, data may not appear at the destination until flushed. Conversely, flushing does not guarantee durability on disk; true durability requirements need appropriate file-synchronization mechanisms.

## 13. Returning a Stream from a Factory: Transferring Ownership to the Caller

A helper can create and return a stream for calling code to use:

```java
static BufferedReader openUtf8Reader(Path path) throws IOException {
    return new BufferedReader(
            new InputStreamReader(
                    Files.newInputStream(path), StandardCharsets.UTF_8));
}
```

This is an **illustrative method**, requiring corresponding imports. It opens a file stream and returns the outer wrapper. Because the factory **transfers ownership through the return value**, the caller is responsible for closing:

```java
try (BufferedReader reader = openUtf8Reader(path)) {
    // Use reader.
}
```

If the caller forgets to close it, the file stream can leak. Conversely, **never** do this:

```java
// Incorrect illustrative code:
static BufferedReader brokenFactory(Path path) throws IOException {
    try (BufferedReader reader = openUtf8Reader(path)) {
        return reader; // Returns a reader already closed upon leaving try.
    }
}
```

This example demonstrates a lifecycle bug: returning a still-referenced object whose underlying resource is already closed. If you want to ensure the caller never needs to close, do not return a live resource; instead, read the data within a bounded scope and return an **immutable value** or data-owning object, accepting the memory trade-off.

### How to Avoid Ownership Confusion in APIs

You can choose clarifying names such as `openReader()`, `withReader(...)`, or write Javadoc:

```java
/**
 * Reads records from a borrowed InputStream.
 * This method does not close the supplied stream.
 */
static void parse(InputStream borrowed) throws IOException {
    // ...
}
```

This is an **API documentation skeleton** with the method body omitted to illustrate the contract. If an API actually closes the passed stream, state explicitly "takes ownership and closes the stream" and define error behavior. Never rely solely on method names and leave callers guessing.

## 14. Callback-Based API Design to Close Resources in the Right Scope

In some situations, there is no need to return a live resource to the caller. You can own opening/closing right at the boundary and accept a processing callback:

```java
@FunctionalInterface
interface ReaderAction<T> {
    T apply(BufferedReader reader) throws IOException;
}

static <T> T withUtf8Reader(Path path, ReaderAction<T> action)
        throws IOException {
    try (BufferedReader reader = Files.newBufferedReader(
            path, StandardCharsets.UTF_8)) {
        return action.apply(reader);
    }
}
```

This is an **illustrative snippet**, requiring imports for `BufferedReader`, `IOException`, `Files`, `Path`, and `StandardCharsets`. `withUtf8Reader` owns the stream and guarantees closing before returning the result. The callback only **borrows the reader for its execution scope**, and should not save a reference to use after the callback finishes.

Semantic example:

```java
long count = withUtf8Reader(path, reader ->
        reader.lines().count());
```

With `BufferedReader.lines()`, the line stream depends on the underlying reader; the terminal operation `count()` executes **inside the callback**, so by the time the callback finishes, all reading has completed before the reader closes. Avoid returning a lazy `Stream<String>` out of the callback hoping to read it later, because the reader will already be closed by then.

The "with resource" pattern binds lifetimes cleanly in APIs, yet only fits synchronous processing within the callback's scope. For asynchronous tasks, you need an appropriate ownership and completion management model.

## 15. `Stream<String>` from `Files.lines` and Indirect Resource Closing

The name `Stream` in Java can refer to:

1. **I/O streams** in `java.io`, such as `InputStream`/`OutputStream`.
2. **Stream API** in `java.util.stream`, such as `Stream<String>`.

These are two distinct concepts. However, certain Stream API instances **are backed by I/O resources**:

```java
try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
```

This is an **illustrative snippet**, requiring imports for `java.util.stream.Stream`, `java.nio.file.Files`, `Path`, `StandardCharsets`, and `IOException` handling. `Files.lines` opens a file-backed resource and returns a lazy stream with an appropriate `onClose` handler. **Terminal operations like `count()` do not automatically close Stream API pipelines**; `try-with-resources` is what guarantees closing when done.

Conversely, not every `Stream<T>` holds an OS resource needing closing, such as `List.of("a", "b").stream()`. Do not misunderstand every Stream API object as identical to `FileInputStream`; know where it was created and check the closing rules of that API.

## 16. If You Truly Need to Share One Stream Across Multiple Consumers

You can design a single owner class where every consumer receives a **narrow interface** rather than access to `close()`.

Conceptual example:

```java
interface MessageSink {
    void send(String message) throws IOException;
}
```

The owner creates one `OutputStream` and exposes `MessageSink` to consumers. Only the owner retains authority to close the output. Because the interface does not expose `close()`, it reduces the chance of consumers closing the resource themselves. The owner can enforce synchronization, framing, and flushing in one place.

For resources with multiple asynchronous consumers, you need a mechanism to know when the last consumer finishes: such as lifecycle scopes, carefully designed reference counting, or application shutdown hooks. **Never guess that one thread finishing means no other thread is still using the stream.**

If an API must accept a `Closeable` yet the consumer must not close the delegate, consider a non-closing wrapper at the boundary or an explicit borrowed contract. A non-closing wrapper only guards close calls passing through that wrapper; **it does not protect against out-of-order writes/reads**.

## 17. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `try (BufferedReader r = ... System.in ...)` inside every method | Closes stdin after method finishes; later code cannot read | Caller/app owns stdin; keep one shared wrapper or avoid closing when borrowing |
| `try (BufferedOutputStream b = new BufferedOutputStream(callerOut))` | Unintentionally closes caller's output | Have caller pass wrapper, or use a non-closing delegate / explicit flush |
| Each parser creates its own `BufferedReader` over the same input | Buffers read ahead data meant for another parser | Share one coordinated wrapper or design explicit framing |
| Placing both `raw` and wrapper in `try` without thinking | Can trigger duplicate close on delegate | Understand ownership chains and each class's close behavior |
| Returning a reader from inside `try-with-resources` | Returns an already closed object | Factory transfers ownership; caller closes |
| Forgetting to close a factory-returned stream | Leaks files/sockets or related resources | Caller uses `try-with-resources` |
| `close()` in `finally` masking a `try`-body error | Loses the primary root cause | Use `try-with-resources`; inspect suppressed exceptions |
| Treating `flush()` as a substitute for `close()` on GZIP | Missing GZIP trailer/final format data | Call `finish()`/`close()` per API |
| Closing a shared resource inside one worker | Other consumers fail | High-level owner decides when to close |
| Assuming because `ByteArrayOutputStream` works after close, files do too | Unit tests hide lifecycle bugs | Test using tracking streams or fake closes |
| Using `PrintWriter.println` expecting checked `IOException` | Write errors may be recorded internally instead | Check `checkError()` or choose an error-reporting API |
| Closing Scanner over `System.in` while other input features remain | Stdin closes along with Scanner | Keep scanner for app lifetime or document ownership |
| Reading lines from `Files.lines` without closing | File resource may stay open | `try (Stream<String> lines = Files.lines(...))` |
| Returning a lazy Stream API pipeline backed by a closed reader | Fails when consumed outside scope | Run terminal operation in scope or transfer ownership clearly |
| Multiple threads sharing output and nobody closing | Can still interleave bytes and corrupt protocol | Coordinate ordering/sync, framing; close after all tasks finish |

## 18. Checklist When Writing or Reviewing a Stream-Accepting API

Before deciding on `try-with-resources`, determine:

1. **Origin:** did the method open the stream, did the caller pass it in, or did it come from a singleton/global?
2. **Owner:** which component has authority to terminate the real resource?
3. **Wrappers:** closing which wrapper closes which delegate? Are there exceptions like memory streams?
4. **Subsequent consumers:** will any method, task, or thread still need the stream after the current operation finishes?
5. **Buffering and position:** does a wrapper read ahead, retain unprocessed bytes/chars, or hold unflushed buffered writes?
6. **Termination protocol:** does the format require `finish()`, a footer/trailer, or stateful encoder finalization before closing?
7. **Errors:** must close errors be reported? If multiple errors occur, how are suppressed exceptions preserved?
8. **API contract:** does Javadoc state borrowed / takes ownership / returns owned closeable?
9. **Test evidence:** are there tests with close-tracking streams, simulated errors, and continued post-call usage?
10. **Execution model:** is it synchronous or asynchronous; who ensures the resource stays alive until task completion?

If a method only performs a brief transformation on a caller-passed stream, a **borrow and do not close** contract is usually appropriate. If a method opens a stream from a file itself, `try-with-resources` is generally the safest choice. If a stream is returned from a factory, state clearly that the caller is the owner.

## 19. Practice Exercises

1. Run `WrapperCloseDemo`; explain why the byte count is 0 before close and becomes `ABC` after close.
2. Replace `ByteArrayOutputStream` in the example with a real file stream. Observe the effect of `close()` and why you must not keep writing after close.
3. In `BorrowedStreamDemo`, modify `writePart` to close output itself, then use the tracking stream to catch the ownership violation (without relying on `ByteArrayOutputStream` allowing writes after close).
4. Run `NonClosingWrapperDemo`; remove the `close()` override on `NonClosingOutputStream` to observe the difference in delegate close count.
5. Run `SuppressedCloseDemo`; remove the `try`-body error and the `close()` error in turn. Identify which exception becomes primary.
6. Write `copy(InputStream, OutputStream)` taking two borrowed streams, closing neither, writing only the `count` of bytes actually read. Use two fixtures with `closed` flags to ensure the caller can keep using them.
7. Create two `BufferedReader` instances over the same multi-line `InputStream` and explain why read-ahead makes sharing two readers hard to control. Redesign to have a single reader owner.
8. Write a factory `openUtf8Reader` and use it with `try-with-resources`; add a missing-file case and verify no resource hangs open.
9. Use `Files.lines` on a small file with `try-with-resources`, then write a `withUtf8Reader` callback that reads while still open.
10. Design Javadoc for two methods: one **borrows an OutputStream**, and the other **takes ownership**. Clarify behavior when `IOException` is thrown.
11. Describe how to handle an async task currently writing when the application receives a shutdown request: who waits for completion, who flushes/closes, and how to avoid closing mid-message.
12. Given a caller-owned output stream and a GZIP format needing finalization, choose among `finish()`, a non-closing wrapper, and ownership transfer; explain the chosen contract.

## 20. Summary

Resource management in Java I/O requires understanding **actual stream lifetimes**, **wrapper-delegate relationships**, and **ownership contracts** simultaneously.

- **Self-opened and owned:** use `try-with-resources` to close promptly; for wrapper chains, closing the outer layer is usually enough.
- **Passed in as borrowed:** do not close the delegate yourself; note wrappers can forward `close()`, buffering can read ahead, and flush/finish need explicit conventions.
- **Shared:** a single owner/coordinator decides shutdown; do not let consumers arbitrarily close `System.in/out/err`, sockets, or shared streams.
- **Returning live resources:** caller takes ownership and closing duty; never return a stream already closed inside a try block.
- **When processing fails:** `try-with-resources` preserves the primary error and suppressed exceptions for diagnosis; never hide errors.
- **Testing ownership:** use tracking streams to prove borrowed methods do not close, wrappers close the right delegates, and callers can continue using streams after the call returns.

**The single most important question whenever writing `close()` is: "Do I truly own this resource, and will anyone else still need it afterward?"**

### References

- Java SE 17: [`AutoCloseable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html), [`Closeable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html), [`InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html), [`OutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html).
- Java SE 17: [`BufferedInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html), [`BufferedOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html), [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html), [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html).
- Java SE 17: [`Scanner`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html), [`PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html), [`Files.lines`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`GZIPOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html).

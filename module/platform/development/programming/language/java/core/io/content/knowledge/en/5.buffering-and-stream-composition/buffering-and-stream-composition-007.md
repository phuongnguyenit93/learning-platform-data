# `close()` on the Outermost Layer and Closing Underlying Resources in Java I/O

In Java I/O, classes are often **chained together (wrappers/decorators)** to add capabilities. For instance, a `BufferedReader` adds buffered reading to an `InputStreamReader`, while `InputStreamReader` decodes bytes fetched from a `FileInputStream` into characters:

```text
Application code
    |
    v
BufferedReader                 <- outermost layer, app calls read()/close()
    |
    v
InputStreamReader              <- decodes bytes into characters
    |
    v
FileInputStream                <- holds file resource / descriptor
    |
    v
OS file
```

**Practical rule:** For standard I/O wrappers that close the underlying layer per their contract, **close the outermost layer owned by the application**. The `close()` call is forwarded down through the wrapped layers, releasing the underlying resource; for output streams, closing also finalizes/flushes data sitting in buffers. However, **never assume every custom wrapper or every API owns the resource passed into it**. You must examine the ownership contract and `close()` behavior of the specific class.

This lesson clearly distinguishes: propagating close behavior, closing order, `flush()` vs. `close()`, resource ownership boundaries, error handling during close, and verification in Java 17+.

## 1. Why Are Streams Wrapped in Multiple Layers?

Wrappers split responsibilities instead of cramming every feature into one class:

| Layer | Role | May Own / Wrap |
| --- | --- | --- |
| `FileInputStream`, `FileOutputStream` | Read/write bytes with a file | File handle/descriptor |
| `InputStreamReader`, `OutputStreamWriter` | Convert between bytes and characters per `Charset` | `InputStream` / `OutputStream` |
| `BufferedInputStream`, `BufferedOutputStream` | Reduce lower-layer I/O calls via a byte buffer | Wrapped byte stream |
| `BufferedReader`, `BufferedWriter` | Character buffer; `BufferedReader` adds `readLine()` | `Reader` / `Writer` |
| `DataInputStream`, `DataOutputStream` | Read/write primitive types and binary formats | Wrapped byte stream |
| `GZIPInputStream`, `GZIPOutputStream` | Decompress/compress GZIP data | Wrapped byte stream |

Example of opening a file with three layers:

```java
InputStream raw = Files.newInputStream(path);
Reader decoder = new InputStreamReader(raw, StandardCharsets.UTF_8);
BufferedReader reader = new BufferedReader(decoder);
```

This is **illustrative code**: `path`, imports, and exception handling are not shown as a standalone program. A single `reader.readLine()` can read across all three layers. Closing the outermost `reader.close()` also cascades down the chain **for these standard classes**. To avoid leaking resources when exceptions occur, use `try-with-resources` immediately when creating the wrapper.

## 2. What Does `close()` on the Outermost Layer Close?

For many standard `java.io` wrappers, `close()` **delegates** to the wrapped stream/reader/writer. Thus:

```text
reader.close()
    -> BufferedReader closes the underlying Reader
        -> InputStreamReader closes the underlying InputStream
            -> FileInputStream releases the file descriptor
```

Similarly, an output stream can form a chain:

```text
BufferedWriter.close()
    -> flushes remaining buffered characters
    -> OutputStreamWriter.close()
        -> finalizes encoder state and closes OutputStream
            -> FileOutputStream.close()
                -> releases the file resource
```

**Terminology note:** In the chain above, calling `close()` on the outermost wrapper and moving down the layers is **close propagation along the wrapping relationship**, not a special JVM recursion mechanism. Each class executes its own `close()` logic per its contract. If you use a custom wrapper, you must check whether its implementation forwards `close()`.

### Example 1 — Observing Lower-Layer Closing Directly

The following example uses `FilterInputStream` to track the moment the underlying source is asked to close. The data source here is `ByteArrayInputStream` for deterministic repeatable results; `TrackingInputStream` observes `close()` calls rather than relying on whether a file is locked.

```java
// CloseChainDemo.java
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class CloseChainDemo {
    static final class TrackingInputStream extends FilterInputStream {
        boolean closed;

        TrackingInputStream(InputStream source) {
            super(source);
        }

        @Override
        public void close() throws IOException {
            super.close();
            closed = true;
            System.out.println("closed: underlying input");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] sourceBytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
        TrackingInputStream source = new TrackingInputStream(
                new ByteArrayInputStream(sourceBytes));

        try (BufferedReader outer = new BufferedReader(
                new InputStreamReader(source, StandardCharsets.UTF_8))) {
            System.out.println("read: " + outer.readLine());
        }

        System.out.println("underlying.closed=" + source.closed);
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 CloseChainDemo.java
java CloseChainDemo
```

Output:

```text
read: Xin chào
closed: underlying input
underlying.closed=true
```

Because `try-with-resources` manages **the outermost `BufferedReader` itself**, on exiting the `try` block Java calls `outer.close()`. `BufferedReader` closes `InputStreamReader`, and `InputStreamReader` closes `TrackingInputStream`. The line `closed: underlying input` confirms the close call reached the lower layer.

`ByteArrayInputStream.close()` has no OS resource to release and does not forbid subsequent reads; in this example, the `closed` flag records **that close was called**, rather than claiming every stream type becomes unreadable after close. For `FileInputStream`, closing also releases the file handle.

## 3. `try-with-resources`: Closing Wrappers Properly and Safely

Preferred pattern for a file opened by the program:

```java
Path path = Path.of("data.txt");
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(path), StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

This is an **illustrative code snippet**; it needs the appropriate imports and an existing `data.txt` file. Key principle: a single resource—the outermost `BufferedReader`—is sufficient to close this standard chain. There is no need to manually call `reader.close()` in a `finally` block.

`try-with-resources` guarantees `close()` runs when leaving the block, including when:

- finishing normally;
- hitting `return` or `break`;
- code inside throws an exception.

Managing the outermost layer makes sense because it knows how to finalize any data it still holds and how to close the layer underneath. If you close a raw `FileOutputStream` prematurely before the wrapper's buffer is flushed, data still sitting in the wrapper may never be written and subsequent write attempts will fail.

**You do not need to declare every layer as a `try-with-resources` variable.** The following is usually unnecessary:

```java
try (InputStream raw = Files.newInputStream(path);
     BufferedInputStream buffered = new BufferedInputStream(raw)) {
    // ...
}
```

When exiting the block, Java closes `buffered` first, and then closes `raw` a second time because both were declared as resources. Standard classes normally tolerate repeated closing, yet not every custom resource has an idempotent `close()` contract. When a standard outermost wrapper serves as owner, declare only that wrapper.

### *Independent* Resources Close in Reverse Order

Unlike a wrapper chain, when you declare multiple truly **independent** resources in one `try`, Java closes them from right to left (reverse declaration order). Standalone runnable example:

```java
// CloseOrderDemo.java
public class CloseOrderDemo {
    static final class NamedResource implements AutoCloseable {
        private final String name;

        NamedResource(String name) {
            this.name = name;
            System.out.println("open " + name);
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        try (NamedResource first = new NamedResource("A");
             NamedResource second = new NamedResource("B")) {
            System.out.println("work");
        }
    }
}
```

```bash
javac CloseOrderDemo.java
java CloseOrderDemo
```

Output:

```text
open A
open B
work
close B
close A
```

This is the **closing order of resource variables declared in `try`**; meanwhile, close propagation across a wrapper chain happens inside each wrapper's `close()` method.

## 4. `flush()` Differs from `close()`: Data Remaining in Buffers

For output streams, distinguish two operations:

- **`flush()`** requests pushing a wrapper's buffered data down to the layer underneath. The stream **remains open** and writable.
- **`close()`** finishes using the resource. Standard output wrappers perform whatever steps are needed to flush remaining buffered data and then close the wrapped layer.

`flush()` does not mean data has been written **durably to the storage device**; data may still reside in OS or hardware caches. When file durability is required, look into `FileChannel.force(...)` and filesystem-specific guarantees.

### Example 2 — Buffer Not Written to Underlying Sink Until Flush/Close

```java
// BufferedCloseDemo.java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BufferedCloseDemo {
    static final class TrackingOutputStream extends FilterOutputStream {
        boolean closed;

        TrackingOutputStream(OutputStream destination) {
            super(destination);
        }

        @Override
        public void close() throws IOException {
            super.close();
            closed = true;
            System.out.println("closed: underlying output");
        }
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        TrackingOutputStream underlying = new TrackingOutputStream(sink);

        try (BufferedOutputStream outer =
                     new BufferedOutputStream(underlying)) {
            outer.write("ABC".getBytes(StandardCharsets.UTF_8));
            System.out.println("before close bytes=" + sink.size());
        }

        System.out.println("after close bytes=" + sink.size());
        System.out.println("underlying.closed=" + underlying.closed);
        System.out.println("text=" + sink.toString(StandardCharsets.UTF_8));
    }
}
```

```bash
javac BufferedCloseDemo.java
java BufferedCloseDemo
```

Output:

```text
before close bytes=0
closed: underlying output
after close bytes=3
underlying.closed=true
text=ABC
```

The three bytes `ABC` are small enough to sit inside `BufferedOutputStream`'s default buffer. Closing `outer` pushes the data down to `TrackingOutputStream`/`ByteArrayOutputStream` and asks the lower layer to close as well. Because `ByteArrayOutputStream` operates in RAM, its own `close()` does not erase data; `underlying.closed` is recorded by the tracking wrapper.

If inside `try` you replace with:

```java
outer.write("ABC".getBytes(StandardCharsets.UTF_8));
outer.flush();
System.out.println(sink.size()); // 3
```

this is an **alternative illustrative snippet**: `flush()` makes data appear in `sink` right inside the block without closing the stream. If you want to keep writing after `flush()`, you still can; after `close()`, you should no longer use the wrapper.

**Do not close the lower layer before the outer layer:** For instance, if you call `underlying.close()` first and then `outer.close()`, bytes still inside `BufferedOutputStream` may try to flush through an already-closed layer; for real sinks like files or sockets, this can cause data loss or errors. Let the outermost output wrapper close in proper order.

## 5. Wrappers That Perform Finalization Work on `close()`

Some wrappers do more than buffer—they **format data**:

- `GZIPOutputStream` must finalize the compressed stream structure; `close()` finishes and closes the underlying stream. If you want to finalize GZIP while **keeping the underlying stream open** in an intentional design, look at `finish()`; a plain `flush()` does not replace finalizing the format.
- `ZipOutputStream` must write ZIP trailer structures (such as the central directory) for a complete ZIP archive. `close()` closes both the archive and the underlying stream; `finish()` finalizes the archive without closing the underlying stream.
- `OutputStreamWriter` converts characters to bytes via a `CharsetEncoder`. Encoder data/state may need to be flushed or finalized on `flush()` or `close()`, so you cannot assume merely writing to the wrapper means the underlying source has received everything.
- `BufferedWriter` and `BufferedOutputStream` hold data in RAM to reduce lower-layer calls; closing the proper wrapper prevents leaving buffered tail data behind.

**Distinguish `finish()` and `close()` where supported:** `finish()` finalizes the format of a specialized stream; `close()` also releases/closes the object and usually the underlying stream. Not every `OutputStream` has `finish()`.

Do not replace `close()` with `flush()` everywhere. File/socket resources still must be closed by their owner; a compressed format may remain incomplete if finalization logic never runs.

## 6. Who Actually Owns the Underlying Stream?

The most important factor when deciding whether to close the outer layer is **resource ownership**:

| Situation | Who Should Close? | Reason |
| --- | --- | --- |
| Method opens the file itself and wraps it | The method, via the outermost wrapper | It created and owns the entire chain. |
| Function receives `InputStream`/`OutputStream` from caller and reads/writes part of it | Usually the caller, unless the contract clearly transfers ownership | The function must not break a shared stream. |
| `System.in`, `System.out`, `System.err` | Application/runtime lifecycle | Closing a wrapper around them can close standard streams needed elsewhere. |
| One socket shared across multiple components | The component designated as the socket owner | Closing a socket's stream can close the connection, affecting other components. |
| Custom wrapper with a special `close()` override | Per that wrapper's contract | Never assume `close()` always delegates. |

Practical API design rules:

- **Manage lifecycle where the resource is created**, unless documentation or interface explicitly transfers ownership.
- Document clearly in Javadoc/contracts whether a passed-in `OutputStream`/`Reader` will be closed or remains owned by the caller.
- If a function only *borrows* a stream, it may call `flush()` when data must be pushed, but normally **must not `close()`** it.
- If a function *takes ownership*, ensure closing on completion or error, preferably via `try-with-resources`.

Example of a function that only borrows an `OutputStream`:

```java
// Illustrative snippet; will not run standalone without imports/enclosing class.
static void sendMessage(OutputStream borrowed, String text)
        throws IOException {
    borrowed.write(text.getBytes(StandardCharsets.UTF_8));
    // Do not call borrowed.close(): caller still owns the stream.
}
```

In particular, avoid `try (BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(System.out)))` in a helper that just prints to the console: closing `writer` propagates to `System.out` and can break later print calls. Similarly, with a `Scanner` wrapping `System.in`, `scanner.close()` can close the shared standard input stream.

### When You Need a Wrapper Without Closing the Caller's Stream

There are three approaches depending on architecture:

1. The caller creates the wrapper itself and retains lifecycle control over **both wrapper and source**; the helper only receives the wrapper to use.
2. The helper borrows the source and creates a temporary buffer; it must `flush()` before returning if output was written, and avoid closing a propagating wrapper. Error handling and any remaining buffered state must be well defined.
3. Use a **close-shield / non-closing wrapper** when an outer layer must be closed to finalize its content while the lower layer belongs to the caller. This must be designed and tested explicitly; it is not the default behavior of `BufferedOutputStream`.

Illustrative close-shield example for output (placed in an appropriate Java class importing `FilterOutputStream`, `OutputStream`, `IOException`):

```java
static final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream delegate) {
        super(delegate);
    }

    @Override
    public void close() throws IOException {
        flush(); // Do not call super.close(), keeping delegate open.
    }
}
```

If you construct `new BufferedOutputStream(new NonClosingOutputStream(borrowed))`, calling `close()` on `BufferedOutputStream` flushes its data and closes the shield wrapper; the shield only flushes and **never calls `borrowed.close()`**. This illustrates an ownership policy and does not replace checking whether upper wrappers require `close()` to finalize formats or have stateful lifecycles.

## 7. Exceptions During Reading/Writing and During Resource Closing

`close()` can throw `IOException`. Errors may surface while flushing remaining buffer contents to a file, finalizing encoding/compression, or closing the resource. Thus exceptions from `close()` **are not merely things that happen after the real work has already succeeded**.

With `try-with-resources`:

- If the `try` body succeeds but `close()` fails, the exception from `close()` is thrown.
- If the `try` body throws an exception and `close()` also throws, the body's exception is kept as the **primary exception**, while the `close()` exception is attached to the **suppressed exceptions** array.
- If multiple resources are declared, they close in reverse order; exceptions thrown while closing subsequent resources can be recorded as suppressed.

Standalone Java 17+ example:

```java
// SuppressedCloseDemo.java
import java.io.IOException;

public class SuppressedCloseDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("body failed");
        } catch (IOException ex) {
            System.out.println("primary=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed=" + suppressed.getMessage());
            }
        }
    }
}
```

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

Output:

```text
primary=body failed
suppressed=close failed
```

When investigating data loss or corrupted files, do not inspect only `ex.getMessage()` of the primary error. You may need to check `getSuppressed()` to uncover flushing/closing failures. Also never write a naive `finally { stream.close(); }` where closing risks **masking the primary exception** from the block body; `try-with-resources` has explicit suppression rules.

One caveat: even though standard wrappers propagate `close()` downward, **you cannot assume every resource has definitely closed cleanly when `close()` throws an error**. Exact state depends on the implementation, OS, and failure mode—which is why preserving exceptions and designing proper recovery matters.

## 8. Other Easily Misunderstood Cases

### `close()` Normally Differs from EOF

When reading data, EOF indicates the source has no more characters/bytes in the stream. `close()` is an application-driven action releasing a resource, which can occur **before EOF** if only part of the stream is needed. Trying to read after `close()` is not a valid EOF check; many streams will throw `IOException`.

### Not Every Closed Object Becomes "Unusable" in the Same Way

`ByteArrayInputStream` and `ByteArrayOutputStream` operate in memory, so their `close()` has **no effect** per contract. On a closed `FileInputStream`, subsequent reads typically throw an error. Do not extrapolate from an in-memory class to OS-backed resources.

### `PrintWriter`/`PrintStream` Differ in Error Reporting

`PrintWriter` typically **does not throw `IOException` from many write methods**; you can inspect error state with `checkError()`. Closing `PrintWriter` can still close the underlying writer/stream, yet seeing no exception from a print call does not prove data was written successfully. For logic requiring explicit I/O error reporting, prefer `BufferedWriter`/`Writer` and catch `IOException`.

### Compression or Formatting Layers May Need Proper Finalization

If you only close the `FileOutputStream` underneath an open `GZIPOutputStream` or `ZipOutputStream`, the output structure may miss its trailer. Always have the owner close the outermost formatting wrapper or call `finish()` per contract before closing the layer you own.

### Do Not Generalize to Every Java API

Standard classes like `FilterInputStream`, `FilterOutputStream`, `BufferedReader`, `BufferedWriter`, `InputStreamReader`, and `OutputStreamWriter` propagate close by design. However, a custom `Reader`, a third-party buffer, a servlet stream, or a lifecycle-managed API may have a different contract. When unsure, read the `close()` documentation of **that exact implementation**.

## 9. How to Choose a Resource-Closing Design

Before building an I/O chain, answer four questions:

1. **Origin of resource:** Who opened the file, socket, or connection?
2. **Lifecycle owner:** Who is responsible for closing?
3. **What must the outermost wrapper finalize:** flush buffers, flush charset encoder, `finish()` compressed format?
4. **On failure:** Does `try-with-resources` preserve both the original exception and any close error?

A decision diagram:

```text
Did I create the source and own it?
  |
  +-- Yes --> Wrap as needed, try-with-resources on the outermost layer.
  |           Let close() cascade down through standard wrappers.
  |
  +-- No  --> Verify whether the contract transfers ownership.
                |
                +-- Yes --> Manage close() per the received contract.
                |
                +-- No  --> Do not close() the shared source.
                              If creating a wrapper, design flush/shield
                              and lifecycle handoff explicitly.
```

With standard streams, the concise pattern is usually the right one for *sources created by the function itself*:

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Dữ liệu cần lưu");
}
```

This illustrative snippet assumes `path` is defined. `Files.newBufferedWriter` handles opening the file and returns a buffered wrapper. Exiting the block closes the writer, flushes remaining buffered characters, and releases the file resource. You do not need `writer.flush()` immediately before `close()` just to be safe; needing others to observe data while the stream **is still open** is the reason to call `flush()`.

## 10. Self-Check Questions

**1.** A `BufferedReader` wraps an `InputStreamReader` wrapping a `FileInputStream`. If the function opened the file itself, what should it close?

**Answer:** Close the outermost `BufferedReader` with `try-with-resources`; standard wrappers propagate closing down to the file layer.

**2.** Is it safe to close the underlying `FileOutputStream` before closing `BufferedOutputStream`?

**Answer:** No. The outer buffer may still hold bytes not yet sent down to the sink. Close the outermost wrapper so flushing and closing occur in order.

**3.** Does `flush()` substitute for `close()`?

**Answer:** No. `flush()` pushes buffered data downward and leaves the stream open; `close()` ends the lifecycle, and formatting wrappers may also need to emit trailer structures.

**4.** A function receives a caller's `OutputStream`. Should it automatically close it when done?

**Answer:** Only if the contract explicitly states ownership is transferred. By default, let the caller manage the lifecycle of the stream it passed in.

**5.** In what order does `try (A a=...; B b=...)` close resources?

**Answer:** `b` first, `a` second. This is the order among **declared resources**, not a replacement for wrapper close propagation.

**6.** If the `try-with-resources` body throws an exception and `close()` throws another, where do you find the close error?

**Answer:** Usually inside `primaryException.getSuppressed()`. Do not ignore suppressed exceptions when diagnosing failures.

**7.** Can closing a wrapper around `System.out` affect other parts of the application?

**Answer:** Yes. Standard streams are shared resources; avoid letting helpers close them if the helpers do not own them.

**8.** `ByteArrayOutputStream.close()` does not prevent reading data afterward; does `FileOutputStream.close()` work the same way?

**Answer:** No. `ByteArrayOutputStream` is special because it holds no OS I/O resource; never use it as evidence for file or socket streams.

**Takeaway:** When you **own the whole standard I/O wrapper chain**, closing the **outermost wrapper** ensures data/formats are finalized and underlying resources are closed. When you only **borrow a source**, `close()` authority belongs to the owner; document the contract clearly and handle `flush()` or close-shields where needed.
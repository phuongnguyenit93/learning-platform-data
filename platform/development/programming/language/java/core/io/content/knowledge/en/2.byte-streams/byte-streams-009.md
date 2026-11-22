# `InputStream.transferTo` and ownership of the two streams

When copying bytes from a source to a destination, Java provides `InputStream.transferTo(OutputStream)` to read all **remaining data** from the input stream and write it sequentially to the output stream. This method keeps copying code concise, but there is one rule that is easy to overlook: **`transferTo` does not close either stream**. Closing resources is the responsibility of the party that owns them.

This lesson focuses on two questions: **what does `transferTo` actually do with the data?** and **who must close the input/output after that call?**

## 1. API and mechanism of `transferTo`

Since **Java 9**, the `java.io.InputStream` class has the method:

~~~java
public long transferTo(OutputStream out) throws IOException
~~~

Called with:

~~~java
long count = input.transferTo(output);
~~~

Meaning:

- **`input`** is the `InputStream` at its current read position. It is the source of the operation.
- **`output`** is the `OutputStream` that receives the bytes. It is the destination of the operation.
- The method sequentially reads the remaining bytes from `input` and writes them to `output` **in the same order**.
- Upon returning normally, `input` is at **end of stream**; a subsequent read will typically receive the end-of-stream indicator `-1` if the stream class follows standard EOF semantics.
- The `long` return value is the **number of bytes transferred**, not a string, not a byte array, and not a character count.
- `transferTo` **does not call `close()` on `input` or `output`** per the API contract. After the transfer completes, they remain the responsibility of whoever manages them.
- If `output` is `null`, the method throws `NullPointerException`. If a read/write operation encounters an error, it may throw `IOException` **after some data has already been transferred**.

Data flow diagram:

~~~text
                      InputStream.transferTo(OutputStream)
File / socket / memory -------- [read bytes -> write bytes] --------> File / socket / memory
      input (source)                                                  output (destination)
      at EOF if successful                                            not auto-closed
      not auto-closed                                                 no flush guarantee
~~~

The key point is that **`transferTo` performs byte copying**—it does not convert character encodings, does not process text, and does not require you to create your own `byte[]` to write a typical loop. The transferred content can be UTF-8 text, images, ZIP files, or any arbitrary binary data.

For example, with a stream containing `A B C D E` where `A B` has already been read, calling `transferTo` will transfer **`C D E`**, because it operates from the **current position**; it does not rewind to the beginning of the stream. With a source that has no data left, the result is `0`.

### Compared to a `read`/`write` loop

Semantically, the work is roughly equivalent to:

~~~java
byte[] buffer = new byte[8192];
long total = 0;
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
    total += n;
}
~~~

In this snippet, you must write exactly the `n` bytes just read because `read(buffer)` is not required to fill the array. `transferTo` hides the looping and buffer management inside the implementation. Do not conclude from this that every concrete `InputStream` has the exact same optimization strategy; subclasses may override the implementation.

With the Java I/O API, **reading to EOF is not equivalent to closing a stream**: an input stream may be exhausted yet still unclosed, and may still hold resources such as a file descriptor or a connection.

## 2. What is stream ownership?

**Ownership** is the responsibility for deciding when a resource is closed or released. In Java code, the `InputStream` or `OutputStream` type itself **does not definitively indicate** who owns it: this comes from how the stream is created and **the contract between methods**.

There are three common roles:

1. **Creator and owner of the stream:** for example, a method that calls `Files.newInputStream(path)` and `Files.newOutputStream(path)` itself to perform work. Typically, it is responsible for closing both streams.
2. **Borrower of the stream:** for example, a helper that accepts `InputStream input, OutputStream output` parameters passed in by the caller. By default, the helper only uses them; the caller continues to manage their lifecycle. If an API intends to take over ownership, it must state so explicitly in its contract.
3. **Higher-level lifecycle manager:** for example, a framework managing request/response, network connections, or `System.in`/`System.out` provided by the runtime environment. One-off code should not arbitrarily close shared resources.

Practical design rule: **the owner of the resource closes the resource; a borrower does not close it**. `transferTo` does not change ownership merely because it transfers data.

| Case | Who owns it? | What should be done after `transferTo`? |
|---|---|---|
| Caller opens both input and output, then calls helper | Caller | Helper returns byte count; caller closes both |
| Helper opens both streams itself within the same method | Helper | Use `try-with-resources` for both input and output |
| Helper opens input from a file but receives output from caller | Input belongs to helper; output belongs to caller | Helper closes only input; leaves output open |
| Helper transfers bytes to `System.out` | Usually belongs to the application/runtime environment | Do not close `System.out` inside the helper |
| Framework supplies streams to a callback | Per the framework's contract | Follow the ownership rules of the API in use |

**There is no rule that “whoever calls `transferTo` must close both.”** Conversely, there is also no rule that “a stream passed into a method must never be closed”: if the API explicitly states that ownership is transferred, the receiving side may be responsible for closing it.

## 3. Complete example: `transferTo` does not close input or output

The Java 17+ example below tracks whether `close()` has been called. We use `ByteArrayInputStream` and `ByteArrayOutputStream` so the program can run standalone without external files. The two classes `TrackedInput` and `TrackedOutput` are wrappers that record each time the `close()` method is called.

Save as **`TransferToOwnershipDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class TransferToOwnershipDemo {
    static final class TrackedInput extends FilterInputStream {
        boolean closed;

        TrackedInput(InputStream delegate) {
            super(delegate);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;

        TrackedOutput(OutputStream delegate) {
            super(delegate);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    static long copyBorrowed(InputStream source, OutputStream destination)
            throws IOException {
        return source.transferTo(destination);
    }

    public static void main(String[] args) throws IOException {
        byte[] original = "Java I/O".getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream storage = new ByteArrayOutputStream();
        TrackedInput input = new TrackedInput(new ByteArrayInputStream(original));
        TrackedOutput output = new TrackedOutput(storage);

        try (input; output) {
            long bytesCopied = copyBorrowed(input, output);
            System.out.println("Transferred: " + bytesCopied + " byte");
            System.out.println("After transferTo: inputClosed=" + input.closed
                    + ", outputClosed=" + output.closed);

            output.write('!');
            output.flush();
            System.out.println("After extra write: "
                    + storage.toString(StandardCharsets.UTF_8));
        }

        System.out.println("After try: inputClosed=" + input.closed
                + ", outputClosed=" + output.closed);
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 TransferToOwnershipDemo.java
java TransferToOwnershipDemo
~~~

Expected output:

~~~text
Transferred: 8 byte
After transferTo: inputClosed=false, outputClosed=false
After extra write: Java I/O!
After try: inputClosed=true, outputClosed=true
~~~

**Step-by-step explanation:**

1. `"Java I/O"` has 8 bytes in UTF-8 (all ASCII characters), stored in `input`.
2. `copyBorrowed` calls `source.transferTo(destination)`; the helper **borrows** both streams, only returns the byte count, and does not close them.
3. Immediately after `transferTo`, both `closed` flags are still `false`. This is evidence in the example that **`close()` has not been called**.
4. `output.write('!')` can still write an additional byte after the transfer; the content in `ByteArrayOutputStream` becomes `"Java I/O!"`. Input has reached the end of stream, but output was not closed by `transferTo`.
5. At the end of `try (input; output)`, **try-with-resources** calls `close` in **reverse order of declaration**: output then input. Both flags become `true` after the block.

*Note:* `ByteArrayInputStream`/`ByteArrayOutputStream` do not represent releasing real file descriptors; the wrappers here only help observe **`close` calls**. With files, sockets, or OS resources, omitting `close` can cause resource leaks. `try (input; output)` uses the syntax for resources declared outside, supported since Java 9; the variables here must be final or *effectively final*.

## 4. When a method opens both streams itself

When opening resources from file paths directly inside a method, that method usually **owns both**. Use `try-with-resources` to close both even if `transferTo` throws `IOException`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileCopyService {
    public static long copyFile(Path source, Path destination)
            throws IOException {
        try (InputStream input = Files.newInputStream(source);
             OutputStream output = Files.newOutputStream(destination)) {
            return input.transferTo(output);
        }
    }
}
~~~

This is a **utility class with a `copyFile` method**, without a `main` method; it is called from other application code. When both streams are created successfully, `try-with-resources` manages them. If opening output fails, the already-opened input is still closed. If `transferTo` fails, the opened resources are also closed; any additional exception during closing may be attached as a *suppressed exception*.

**Be careful when writing real files:** `Files.newOutputStream(destination)` with default options can create a new file or **truncate the contents of an existing file**. If you do not want to overwrite, choose an appropriate open option, such as `StandardOpenOption.CREATE_NEW`, according to the task's contract. Stream ownership is a separate concern from the policy for replacing destination data.

There is no need to call `input.close()`/`output.close()` again inside the `try` block. Avoid manual closing across multiple branches because it is easy to miss resources when an exception occurs.

## 5. When a helper only receives streams supplied by the caller

In library code, a copy method often does not know whether input/output will continue to be used afterward. The stream-borrowing contract should be clear:

~~~java
// This method only uses two streams owned by the caller.
// It does not close them and does not decide on its own to flush output.
static long transfer(InputStream input, OutputStream output)
        throws IOException {
    return input.transferTo(output);
}
~~~

This is an **illustrative method snippet** to be placed inside a class that imports `java.io.InputStream`, `java.io.OutputStream`, and `java.io.IOException`. The caller can open them in `try-with-resources` and call the helper:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(destination)) {
    long count = transfer(input, output);
    System.out.println("Copied: " + count);
}
~~~

The variables `source` and `destination` are already-declared `Path` values; this snippet illustrates usage, not a standalone program.

A **mixed ownership** case:

~~~java
// The helper opens input itself: the helper must close input.
// destination is passed in by the caller: the helper does not close destination.
static long sendFile(Path path, OutputStream destination)
        throws IOException {
    try (InputStream input = Files.newInputStream(path)) {
        return input.transferTo(destination);
    }
}
~~~

If you call `sendFile(path, System.out)`, the helper closes the **file input** while leaving **`System.out` open** so the application can continue printing other messages.

Conversely, writing the following violates the stream-borrowing contract:

~~~java
// WRONG if the caller still owns output:
try (OutputStream borrowed = output) {
    input.transferTo(borrowed);
}
// borrowed.close() has been called, which may close the caller's output.
~~~

`try-with-resources` is the right closing mechanism when the code **owns** the resource; putting a borrowed stream into `try` can accidentally seize the right to close it. Valid syntax does not mean the ownership contract is correct.

## 6. How do `flush()`, `close()`, and `transferTo()` differ?

| Operation | Primary meaning | Does it automatically close input/output? |
|---|---|---|
| `input.transferTo(output)` | Transfers remaining bytes to output; returns byte count | **No** |
| `output.flush()` | Requests pushing buffered bytes to the underlying destination | Does not close |
| `output.close()` | Terminates the output resource, usually flushing depending on the implementation | **Closes output**; may cascade to underlying stream |
| `input.close()` | Terminates the input resource | **Closes input**; may cascade to underlying stream |
| `try-with-resources` | Calls `close()` automatically upon exiting the block, even on error | Closes **the declared resources** |

**`transferTo` makes no guarantee that output has been flushed.** If output has a buffer such as `BufferedOutputStream`, bytes remaining in the buffer may require `flush()` before the receiver sees all the data. When to `flush` must follow the protocol and the contract of the output's owner: a helper borrowing output should not arbitrarily force closing or flushing unless requested.

**`flush` does not mean data has been durably persisted to storage.** Under the general `OutputStream` contract, flushing to an underlying layer may only reach the operating system; guaranteeing durability on disk may require dedicated APIs and procedures. Closing output also does not prove that a network peer has processed the entire message.

**Wrappers can cascade-close underlying streams:** `BufferedOutputStream`, `FilterOutputStream`, and certain compression/decompression streams commonly wrap another stream. Calling `close` on a wrapper can also close the underlying stream, while some formats require `finish()` or a separate procedure to finalize content. If a wrapper wraps `System.out` or a framework-provided stream, ownership must also be designed at the wrapper layer to avoid closing shared resources.

## 7. Exceptions, partial transfers, and blocking behavior

`transferTo` is convenient, but it does not turn I/O into an atomic operation:

- If reading input or writing output fails, `IOException` can occur **after some bytes have already been written**. You must not assume the destination file is still empty or that the source remains at its original position.
- If the input produces data continuously or the output is slow, the method can **block** while waiting to read/write, potentially indefinitely. With sockets and network protocols, timeouts, cancellation, or data limits are needed from the owning layer.
- If you want to limit the transfer to only a portion of the data, `transferTo` itself does not take a “maximum N bytes” parameter. You can use an appropriate limiting stream or a controlled read/write loop.
- When handling errors, the stream owner should close the resources and decide whether to delete a partially written destination file, retry, or report the error. A helper that only borrows streams should propagate the error to the caller unless the contract specifies otherwise.
- Calling `transferTo` a **second time** on an input already at EOF will not resend the data on its own; to run again, you must open a new source or use a stream that supports repositioning appropriately.

Streams used **concurrently** by multiple threads can produce unexpected results, especially when threads read from the same input or write to the same output together. `transferTo` does not establish synchronization protocols to guard against other calls.

## 8. Distinguishing from similarly named APIs

- **`InputStream.transferTo(OutputStream)`**: transfers **bytes** from a readable input to an output, returning the **byte count**; available since Java 9.
- **`Reader.transferTo(Writer)`**: transfers **characters** from a `Reader` to a `Writer`, returning the **character count**; available since Java 10. This lesson is about **byte streams**.
- **`Files.copy(Path, Path, ...)`**: a path-based copying API with file-handling options; resource creation/closing is managed by `Files`, which differs from passing two streams yourself to `InputStream.transferTo`.
- **`FileChannel.transferTo(...)`**: a channel API with a different signature and transfer conditions; you should not infer semantics or ownership from this method onto `InputStream.transferTo`.

When reviewing code, identify the **exact object types and method signature** before applying rules.

## 9. Common mistakes and fixes

| Mistake | Problem | Fix |
|---|---|---|
| “`transferTo` closes input and output for me.” | The API does not close streams; resources can leak. | The owner uses `try-with-resources` or explicit lifecycle management. |
| “A helper receiving output can just put it in `try`.” | May close a resource the caller still needs. | A helper borrowing output only transfers data; the caller is responsible for closing. |
| “After copying, input automatically rewinds to the start.” | `transferTo` reads from the current position to EOF. | If a fresh read is needed, open a new stream or design for repositioning. |
| “If output received the bytes, the file/network transfer is definitely complete.” | Buffers and storage/protocol layer guarantees may still apply. | Determine when `flush`, closing, or protocol acknowledgment is needed. |
| “`transferTo` always completes cleanly without partial copies.” | I/O can fail midway or block indefinitely. | Have a timeout/cancellation strategy, cleanup, and handling for partially written data. |
| “It's UTF-8 data, so `transferTo` will decode and re-encode it.” | `transferTo` only transfers bytes. | Use Reader/Writer with a charset only when character processing is actually needed. |
| “`try-with-resources` is only for the success path.” | It is a resource cleanup mechanism that also runs on errors. | Declare the streams **that you own** in the resource header. |

## 10. Self-check

**Question 1.** `input.transferTo(output)` returns `120L`. What is the number 120? If the operation succeeds, where is `input`?

> **Answer:** 120 is the number of **bytes transferred**. `input` is at the end of the readable data; `transferTo` does not automatically close `input` or `output`.

**Question 2.** The method `saveReport(OutputStream out)` receives `out` from the caller and creates an `InputStream` itself to read the report. Who closes what?

> **Answer:** The method closes the `InputStream` it created. The caller closes (or manages) the `OutputStream` it owns according to the contract. `transferTo` does not change that responsibility.

**Question 3.** If `output` wraps a `BufferedOutputStream` and a helper calls `transferTo`, yet the caller does not see all the content yet, what should be examined?

> **Answer:** Check the buffering policy and `flush`/`close`, as well as when the receiver reads the data. `transferTo` does not guarantee a flush; flushing or closing must match ownership.

**Question 4.** If the input has already been completely read before `transferTo`, what is the result?

> **Answer:** `0` bytes are transferred, because there are no remaining bytes to read. `output` is still not closed by `transferTo`.

### Key takeaway

**`input.transferTo(output)` = transfer remaining bytes + return byte count; does not close either stream.** Write safe code by clearly identifying **who creates, who borrows, and who closes** each resource, using `try-with-resources` at the owning layer, and handling I/O errors that can occur after partial data has been written.

**Reference:** [Java SE 17 `InputStream.transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#transferTo(java.io.OutputStream)) and [Java SE 17 `OutputStream.flush`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html#flush()).
# Who Opens, Who Closes: Resource Ownership Rules in Java I/O API Design

> **Context:** Java Core -> I/O -> **Resources and Errors**. This lesson answers a seemingly simple question that easily causes leaks and hard-to-trace bugs: **who is responsible for calling `close()`, when can that responsibility be transferred, and should a read/write method close a stream passed in by the caller?** This knowledge applies to `InputStream`, `OutputStream`, `Reader`, `Writer`, channels/files, and open I/O objects. Standalone examples use Java 17; most foundational contracts have existed longer.

## 1. Resource Ownership Is a Contract, Not Just Calling close

I/O resources such as file descriptors, sockets, directory handles, or channels typically have a **lifecycle independent** of the Java object referencing them. When opening a file, the JVM/OS may allocate a finite handle; forgetting `close()` can exhaust handles, leave files locked, fail to flush buffers on time, or keep resources alive longer than intended.

The **resource owner** is the component responsible for determining the lifecycle and **closing** the resource promptly, including when exceptions occur. Ownership should be expressed in the **API contract**: is a parameter a borrowed source or a transferred source, and does an open return value need to be closed by the caller or did the method clean it up itself?

Common rules are:

- **A method that opens internally for internal use -> that method normally closes it** before returning computed results.
- **A method receiving a caller-supplied stream -> by default treat the stream as borrowed, use it without closing it**, unless the API explicitly states ownership transfer.
- **A method returning an open stream/channel -> the caller receives ownership and bears responsibility for closing it**.
- **A method wrapping a stream (decorator/wrapper) -> read the wrapper's `close()` contract**: closing the outer layer normally closes the inner source too.
- **Shared resources or framework/JVM-managed resources -> do not arbitrarily close them from a utility function**.

These statements are **API design conventions**, not rigid rules enforced by the Java language. Calling `new` or receiving a reference **does not by itself prove** ownership. A factory may open a resource and **transfer** closing duty to the caller; a constructor may receive a caller-opened resource whose contract grants ownership to the wrapper. Be explicit and consistent.

### What Happens When Ownership Is Unclear?

| Lifecycle Mismatch | Consequence |
| --- | --- |
| Nobody calls `close()` | File descriptor, socket, or directory handle leaks; delayed, non-deterministic release |
| Both sides think they own closing and one closes early | `IOException: Stream closed` or failed read/write on the side still using it |
| A utility method closes a stream the caller is still using | Broken pipeline; shared file/socket cannot be used further |
| Method opens a stream and returns a lazy `Stream` without documenting close duty | Caller assumes a terminal operation closes it automatically; file/directory stays open |
| Wrapper is closed after one step, closing the underlying stream too | Another user of the original source fails even without calling `close()` directly |
| Failure to flush/close output per lifecycle | Data stays in buffer; file may be missing content if the process ends abnormally |
| Resource serving an async task is closed before the task finishes | Race between `close()` and I/O; timing-dependent intermittent failures |

## 2. Three Ownership Models to Define Clearly in Java APIs

### 2.1. Borrowed: The Method Only Borrows the Resource

The caller retains ownership of the `InputStream` or `OutputStream`. The utility method may **read/write**, yet **must not close** them and must not retain references for use after returning, unless agreed otherwise.

~~~java
// Contract: borrowed input/output; method does not close either stream.
static long copy(InputStream in, OutputStream out) throws IOException {
    byte[] buffer = new byte[8192];
    long copied = 0;
    int n;
    while ((n = in.read(buffer)) != -1) {
        out.write(buffer, 0, n);
        copied += n;
    }
    return copied;
}
~~~

This is a fragment inside a class, requiring imports for `java.io.InputStream`, `java.io.OutputStream`, and `java.io.IOException`. The method only transfers bytes, **without closing** or flushing `out`: the caller may still want to write more data, or this output may belong to a larger request/transaction. If the application contract requires flushing at a specific point, document that explicitly too; do not silently flush on every call.

### 2.2. Owned: The Method Accepts Responsibility for Closing

If a method accepts a `Path` and **opens the file itself** inside its body, it typically owns the newly opened reader:

~~~java
// Contract: method opens and closes BufferedReader itself.
static long countLines(Path path) throws IOException {
    try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        long count = 0;
        while (reader.readLine() != null) {
            count++;
        }
        return count;
    }
}
~~~

This is a fragment with imports `java.io.BufferedReader`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`. The caller only passes the path and does not manage the internal reader. `try-with-resources` closes the reader on both normal and exceptional paths.

### 2.3. Transferred: The Method Transfers Closing Duty to the Receiver

~~~java
// Method opens and returns a live resource.
// Caller becomes the owner once return succeeds.
static InputStream openDocument(Path path) throws IOException {
    return Files.newInputStream(path);
}

// Proper call site:
try (InputStream stream = openDocument(path)) {
    // Read stream...
}
~~~

This is a fragment requiring corresponding imports. Returning an `InputStream` **does not automatically** close the stream; state in Javadoc that **caller must close returned stream**. The caller must close it even when reading only a few bytes or after parsing fails. If a method accepts a stream and **receives ownership transfer** into a long-lived object, the contract must specify when the owning object will close it.

## 3. Decision Table: Who Closes in Familiar I/O Operations?

| Source or Action | Who Opens / Creates | Who Should Close | Notes |
| --- | --- | --- | --- |
| `Files.newInputStream(path)` | `Files` method opens handle; caller receives return value | **Caller** | Wrap usage in try-with-resources. |
| `Files.newBufferedReader(path, UTF_8)` | `Files` opens reader | **Caller** | Returns open `BufferedReader`; call `close()` after reading. |
| `Files.readString(path)` or `Files.readAllBytes(path)` | API performs the file read internally | **API** manages internal handle | Caller receives `String`/`byte[]`, not an open resource to close. |
| `Files.lines(path)` | API opens file and returns lazy stream | **Caller** closes `Stream<String>` | `count()`, `findFirst()`, `forEach()` **do not replace** `close()`. |
| `Files.list(dir)` / `Files.walk(dir)` | API opens directory handle | **Caller** closes stream | Use try-with-resources even after running a terminal operation. |
| `Files.newDirectoryStream(dir)` | API opens directory stream | **Caller** | Do not let directory handle outlive the listing scope. |
| `new BufferedInputStream(input)` | Wrapper adds buffering; `input` existed beforehand | **Depends on wrapper ownership contract** | Wrapper `close()` invokes close on the inner source. |
| `new BufferedReader(reader)` | New wrapper; `reader` existed beforehand | **Depends on source ownership** | Closing the wrapper also closes the wrapped reader. |
| `new Scanner(input)` | New Scanner using caller-passed source | Must decide explicitly before closing scanner | On `Scanner.close()`, if source implements `Closeable`, scanner closes it too. |
| `System.in` / `System.out` / `System.err` | JVM/environment provides standard streams | Usually **do not close** in utilities | Closing may cut off stdin/stdout/stderr for other parts of the app. |
| `InputStream.transferTo(output)` | Both streams supplied externally | **Caller/owner of each stream** | Copy method does not close input or output itself. |
| `ByteArrayInputStream` / `ByteArrayOutputStream` | In-memory inside JVM | Per contract, close may do nothing | Still keep ownership consistent in case sources later switch to files/sockets. |
| Stream/channel given by server framework | Runtime or container | Per **framework contract** | Do not infer caller must close just because the type is `InputStream`. |

**Crucial distinction:** implementing `Closeable` does not dictate where closing happens; it only indicates **closeability**. Ownership is determined by **contract** and lifecycle. Conversely, not everything needing closing has type `InputStream`: `Stream<String>` from `Files.lines` must also be closed because it holds a file handle.

## 4. Standalone Example: Method Borrowing Streams Does Not Close Them

Save **`BorrowedCopyDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BorrowedCopyDemo {
    // Counter to observe exactly who calls close().
    static final class TrackedInput extends FilterInputStream {
        int closes;

        TrackedInput(byte[] source) {
            super(new ByteArrayInputStream(source));
        }

        @Override
        public void close() throws IOException {
            closes++;
            super.close();
        }
    }

    // Borrowed API: method does not own input/output.
    static long copyBorrowed(InputStream input, OutputStream output)
            throws IOException {
        byte[] buffer = new byte[8];
        long total = 0;
        int n;
        while ((n = input.read(buffer)) != -1) {
            output.write(buffer, 0, n);
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        TrackedInput in = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        try (in) { // Caller owns and closes input.
            System.out.println("bytes=" + copyBorrowed(in, out));
            System.out.println("closesInside=" + in.closes);
        }

        System.out.println("closesAfter=" + in.closes);
        System.out.println("text=" +
                new String(out.toByteArray(), StandardCharsets.UTF_8));
    }
}
~~~

~~~bash
javac --release 17 BorrowedCopyDemo.java
java BorrowedCopyDemo
~~~

Stdout:

~~~text
bytes=3
closesInside=0
closesAfter=1
text=abc
~~~

`TrackedInput` exists purely for this lesson: the counter increments whenever the wrapper receives `close()`, proving `copyBorrowed` **did not close the stream**. The actual backing resource in the demo is `ByteArrayInputStream` in memory, so closing it has no OS file-descriptor effect. With real files/sockets, premature closing has far stronger consequences.

Specifically, `ByteArrayOutputStream.close()` does not disable the class's methods per contract, yet **you must not** extrapolate from that to assume `FileOutputStream` or network streams behave the same way.

### Why Not Put try-with-resources Inside copyBorrowed?

Doing so **violates the contract** when parameters are borrowed:

~~~java
// Design counterexample: do not use when caller still owns input.
static long wrongCopy(InputStream input, OutputStream output)
        throws IOException {
    try (input; output) { // AUTOMATICALLY closes both when method exits!
        return input.transferTo(output);
    }
}
~~~

In Java 9+, `try (input; output)` compiles if both variables are effectively final, yet it **changes behavior to closing both input and output** on method exit. Even though `transferTo` itself does not close the streams, try-with-resources does. This method is only valid if the contract **explicitly accepts ownership of both**. Never choose to close simply because you see the `AutoCloseable` interface.

## 5. Standalone Example: Two File-Reading API Styles and Two Closing Points

Save **`OpenVsReturnDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public class OpenVsReturnDemo {
    // Internally consuming method: opens itself, closes itself.
    static long countLines(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            long count = 0;
            while (reader.readLine() != null) {
                count++;
            }
            return count;
        }
    }

    // Factory transfers Stream<String> closing duty to the caller.
    static Stream<String> openLines(Path path) throws IOException {
        return Files.lines(path, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("ownership-", ".txt");
        try {
            Files.writeString(
                    file, "one\ntwo\n", StandardCharsets.UTF_8);

            System.out.println("count=" + countLines(file));

            // Stream from Files.lines holds file handle until close.
            try (Stream<String> lines = openLines(file)) {
                System.out.println(
                        "first=" + lines.findFirst().orElse("none"));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

~~~bash
javac --release 17 OpenVsReturnDemo.java
java OpenVsReturnDemo
~~~

Stdout:

~~~text
count=2
first=one
~~~

Key lessons:

- `countLines(Path)` opens `BufferedReader` **and closes it** before returning `long`. No open resource is returned to the caller.
- `openLines(Path)` returns a `Stream<String>` holding a file handle. The caller must use `try (Stream<String> lines = ...)` even when calling only `findFirst()`. The file must be closed **before** the `finally` block attempts to delete the temporary file.
- `Files.writeString` manages opening/closing the file internally before returning; `Files.createTempFile` creates the file, while deleting the **physical file** is a cleanup duty distinct from closing a handle. Never confuse `close()` with `Files.deleteIfExists()`.
- For arbitrarily large files, `countLines` reads line by line using a buffer without loading everything into a `List` or `String`.

## 6. Callback APIs: Borrowing a Resource Within a Controlled Scope

A useful option is a **lifetime-scoped callback**: the method opens/closes the resource, and the callback may only use it while the method invokes it. Example:

~~~java
@FunctionalInterface
interface ReaderTask<T> {
    T apply(BufferedReader reader) throws IOException;
}

// Fragment: method opens and closes reader itself.
static <T> T withReader(Path path, ReaderTask<T> task)
        throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return task.apply(reader);
    }
}

// Illustrative usage:
String first = withReader(path, BufferedReader::readLine);
~~~

This is a **fragment**, placed inside a class with imports `java.io.BufferedReader`, `java.io.IOException`, `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets`, and a valid `Path path`. The callback **borrows** the reader; after the callback (whether it succeeds or fails), `withReader` closes it.

Strengths: the caller cannot forget to close, the method confines resource lifetime to a single lexical scope, and I/O/close errors have a clear path. Contract caveat: the callback **must not close it**, store references, return the open resource outside, or spawn background tasks that continue using the reader after the callback returns. Java generics do not prevent a caller from returning the reference out of scope, so this remains a **contract constraint**; you can restrict return types to reduce violation risk.

For callbacks handling `OutputStream`, the same applies: the method creates the stream and closes it after the callback; the callback must finish writing **inside** the callback. If asynchronous I/O needs to outlive the method return, do not use a short-lived callback design as though work completed synchronously.

## 7. Wrappers and Decorators: Closing the Outer Layer Usually Closes the Inner Layer

Example:

~~~java
// Method creates both input stream and reader, so it owns the entire wrapper chain.
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                Files.newInputStream(path), StandardCharsets.UTF_8))) {
    String firstLine = reader.readLine();
}
~~~

This is a **fragment** inside a method handling `IOException` with corresponding imports. `BufferedReader.close()` invokes close on the inner reader; `InputStreamReader.close()` closes the underlying input stream. Thus **closing the outermost wrapper** releases the entire source chain. You do not need to declare every layer as separate variables in try-with-resources only to trigger redundant closes.

However, if the inner resource **was borrowed from the caller**, that same close-propagation mechanism becomes a trap:

~~~java
// Counterexample when 'borrowed' is still used by the caller:
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(borrowed, StandardCharsets.UTF_8))) {
    return reader.readLine();
} // reader.close() triggers borrowed.close().
~~~

If a method wants to close a wrapper while keeping the underlying source alive, you need an **explicit sharing contract**, an adapter class designed not to close the underlying stream on demand, or to let the owner create the wrapper and transfer ownership. Do not simply omit `close()` on the wrapper and assume everything is fine: buffers may have **read ahead** many bytes, advancing the caller's source position unexpectedly. Choosing **one clear owner for the wrapper chain** is the easiest design to verify.

Another example is `Scanner`: standard documentation states that when Scanner is closed, it closes its underlying source if that source implements `Closeable`. Therefore:

~~~java
// Dangerous in an application that still needs to read System.in:
try (java.util.Scanner scanner =
             new java.util.Scanner(System.in)) {
    String command = scanner.nextLine();
} // Scanner.close() can close System.in.
~~~

If a scanner reads `System.in` for the whole CLI lifecycle, let an **application-level input component** own the scanner and decide when to close it, rather than creating/closing a scanner per token read. Never stack multiple buffered scanners/readers over the same input to read interleaved.

## 8. Should You Flush, Close, or Both?

`flush()` and `close()` serve different purposes:

- **`flush()`** on a buffered output pushes data sitting in that layer's buffer toward the underlying sink per contract; it **does not** guarantee the OS durably persisted data to disk, and it **does not release** handles.
- **`close()`** ends the resource lifecycle and releases held resources. Many buffered outputs flush remaining data during close; **close can fail**. Never assume a close call succeeds just because the write loop finished.
- With borrowed APIs, a copy method typically **does not auto-flush/close output** unless requested; the owner decides when data is complete and when to finish.
- With owned APIs, close output inside try-with-resources. Guaranteeing physical storage durability is a separate concern: `FileChannel.force(...)` or `FileDescriptor.sync()` have their own contracts and filesystem dependencies.

Example:

~~~java
// Fragment: method owns writer because it opened the file itself.
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Đã hoàn thành\n");
} // BufferedWriter is closed even if the body errors.
~~~

Never treat `writer.flush()` as a substitute for `writer.close()`. Conversely, **never call `close()` on a caller-borrowed output** just to "make sure it flushed", because doing so terminates the owner's ability to use it.

## 9. Try-with-resources: Who Closes, When Does Closing Happen?

`try-with-resources` works with objects implementing `AutoCloseable`; whether the block exits via return, exception, or normal completion, resources are closed in reverse declaration order.

~~~java
try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(target)) {
    in.transferTo(out);
} // out.close() first, then in.close().
~~~

This is a fragment; `source`/`target` are provided `Path` instances, with I/O and `Files` imports. The code **owns both streams** because it opened both in the block. Since Java 9, `InputStream.transferTo` does not close either stream itself; the try block handles closing duty.

Important cases:

1. When initializing the second resource throws an error, the successfully created first resource is still closed automatically.
2. If code inside the body throws an exception **and** close also throws, the body's exception is the **primary exception**; close errors are attached to `getSuppressed()`.
3. If the body succeeds yet close throws an exception, the close exception propagates out according to its exception type. Do not ignore it when write completion must be verified.
4. With multiple resources, Java closes in **reverse order** of declaration; never assume dependencies close in arbitrary order.
5. `try (resourceVariable)` from Java 9 allows using an existing final or effectively final local variable/parameter, yet **it still requests closing that resource**. Using this syntax on a borrowed parameter silently changes the contract.
6. `Closeable.close()` per standard contract is idempotent on repeat calls; general `AutoCloseable` **does not require** every implementation to be idempotent. Never rely on double-closing as an ownership strategy.

`try-with-resources` is **the mechanism that performs closing**; it does not decide **who has the right to close**. Ownership decisions must happen before placing an object inside `try (...)`.

## 10. Standalone Example: Error in Body and Error on Close

Save **`SuppressedCloseDemo.java`**:

~~~java
public class SuppressedCloseDemo {
    static final class Faulty implements AutoCloseable {
        private final String name;

        Faulty(String name) {
            this.name = name;
        }

        @Override
        public void close() throws Exception {
            throw new Exception("close-" + name);
        }
    }

    public static void main(String[] args) {
        try (Faulty a = new Faulty("A");
             Faulty b = new Faulty("B")) {
            throw new IllegalStateException("body");
        } catch (Exception ex) {
            System.out.println("main=" + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println(
                        "suppressed=" + suppressed.getMessage());
            }
        }
    }
}
~~~

~~~bash
javac --release 17 SuppressedCloseDemo.java
java SuppressedCloseDemo
~~~

Stdout:

~~~text
main=body
suppressed=close-B
suppressed=close-A
~~~

**Explanation:** the body fails with `IllegalStateException("body")`. Java still invokes `close()` on `b` then `a`, without losing the original exception; both close failures become **suppressed exceptions**. If a logger prints only `ex.getMessage()` and omits stack traces/suppressed exceptions, crucial information about failed resource release can be lost. In server applications, log/report both primary and suppressed exceptions per security/logging policies.

The example uses a custom `Faulty` class to guarantee deterministic output without requiring files; this is an intentional demonstration case, not how normal `close()` implementations should behave.

## 11. Return Types and Method Names Should Express Ownership

Look at these signatures:

~~~java
byte[] readAll(Path path);        // Returns read data; internal resource closed.
InputStream open(Path path);      // Returns open resource; caller closes.
void copy(InputStream in, OutputStream out); // Both borrowed; neither closed.
~~~

These three lines are an **API sketch**, without implementations or `IOException` declarations; they are for comparing contracts rather than standalone execution.

The name `readAll` suggests processing finishes inside the method; `open` suggests the caller receives a live handle; `copy` suggests operating on provided handles. Still, names only assist readers — **they do not replace Javadoc**.

Clear Javadoc template for a borrowed API:

~~~java
/**
 * Copies remaining bytes from input to output.
 *
 * <p>Both streams are owned by the caller. This method neither closes
 * nor flushes either stream; caller controls their lifetimes.
 *
 * @param input an open, caller-owned source stream
 * @param output an open, caller-owned destination stream
 * @return number of bytes copied
 * @throws IOException if an I/O operation fails
 */
public static long copyBorrowed(InputStream input,
                                OutputStream output)
        throws IOException {
    return input.transferTo(output); // Java 9+; transferTo does not close streams.
}
~~~

This method can live in a Java 17 class with appropriate I/O imports. To support Java 8, replace `transferTo` with a buffer loop like in earlier examples. You can disallow `null` explicitly via `Objects.requireNonNull` to fail fast per contract.

Javadoc template for a transferred API:

~~~java
/**
 * Opens an input stream. The returned stream is open and its
 * caller MUST close it, preferably with try-with-resources.
 */
public static InputStream open(Path path) throws IOException {
    return Files.newInputStream(path);
}
~~~

Other patterns are also valid: a method taking a `Supplier` that creates the source internally, a method taking a callback that consumes within a scope, or an object whose `close()` owns multiple resources. Pick a consistent contract and state clearly when ownership changes.

## 12. Special Cases Requiring Caution

### 12.1. Standard Streams and Shared Resources

`System.in`, `System.out`, and `System.err` typically serve the **entire process**. A utility method accepting `System.in` should normally only read and let the caller/runtime own its lifecycle. For example, wrapping `new BufferedReader(new InputStreamReader(System.in, UTF_8))` and closing the reader can close `System.in` itself. Closing `System.out` can likewise cause subsequent outputs to fail; `PrintStream` does not necessarily throw write exceptions the way you might expect.

If a program genuinely needs to close a standard stream, that is a deliberate application-level decision that should never occur inside a helper reading a single line. If you only want to ensure a prompt appears, `System.out.flush()` does not mean closing `System.out`.

### 12.2. Resources Supplied by a Framework/Container

A framework may hand you a request body stream, response writer, or connection managed by the request/transaction lifecycle. Even though the object has `close()`, a receiving library should not close it if the framework retains ownership. Follow the specific framework's official documentation; simply having type `InputStream` says nothing about ownership. If your API method **takes ownership** instead of borrowing, document it clearly and guarantee proper error/cleanup handling on every path.

### 12.3. Shared Resources Across Components

Two services sharing a stream must not both believe they are independent owners. Have one owner hand out borrowed references, use a lease mechanism, or assign lifecycle management to one service. If the resource can be accessed concurrently by multiple threads, add a **thread-safety** and synchronization contract: ownership alone does not make concurrent reads/writes safe.

### 12.4. Async: Task Lifetime Exceeds Method Lifetime

~~~java
// DESIGN COUNTEREXAMPLE — do not execute as production code.
try (InputStream in = Files.newInputStream(path)) {
    CompletableFuture.runAsync(() -> consume(in));
} // in.close() can occur before the consume(in) task finishes reading.
~~~

This is a **lifecycle sketch**, not a standalone program; `consume` is an application-defined function that must handle `IOException`. The issue is that `runAsync` returns before the task finishes. If the callback is still reading when the try block ends, the resource closes prematurely.

The proper solution is to let the **task own opening/closing** inside the task itself, or have the owner **await task completion** before closing, handling timeouts/cancellations/exceptions. Never wrap an outer try-with-resources around a background task bound to a resource with a shorter scope than the task.

### 12.5. Finishing Processing and Closing the Source Are Separate Things

A parser may stop after a few header bytes; that **does not** authorize it to close a borrowed stream. A reader that hits EOF still needs the owner to decide when to close the handle. Closing a file reader does not delete the file from the filesystem. Conversely, the file can remain on disk after all handles are closed.

## 13. Testing Ownership Rules

Do not test only that data was copied accurately. Tests should also answer **who calls close and how many times**.

- For borrowed APIs, pass a wrapped stream with a `closeCalls` counter; call the method and verify it **was not closed** when the method returns, even on exception paths. `BorrowedCopyDemo` shows an easy way to observe this.
- For owned APIs, use a fake `Closeable` or close counter; ensure the resource is closed both on success and when the body throws.
- For resource-returning APIs, receive the stream and use try-with-resources in the caller; verify examples/test docs reflect the caller's duty.
- For wrappers, test whether closing the outer layer closes the delegate per each class's contract. If the delegate is borrowed, do not "fix" leaks by blindly closing the outer wrapper.
- For output, verify flush/close timing; testing written bytes is essential yet does not replace testing resource release.
- When fakes are unavailable, temporary files and OS-appropriate handle checks or file-descriptor monitors can help, though do not assume every OS handles open files identically.
- Test exception paths and suppressed close errors when release can also fail.

**You do not need to test that every Java object is closed exactly once.** For example, `ByteArrayInputStream.close()` is documented to do nothing; what matters is that the API's **ownership contract** is honored and creates no surprises when switching implementations from memory to files or sockets.

## 14. I/O API Design Checklist Before Publishing

| Question | Decision to Document Clearly |
| --- | --- |
| **Where** is the resource created? | Method opens internally, caller opens, factory transfers ownership, or framework manages? |
| **How long** is the resource used? | Only inside method, after return, object lifetime, request, or async task? |
| Who has authority to **close**? | Callee, caller, callback boundary, framework, or app-level owner? |
| Does the method return data or an **open resource**? | Already-read `String/byte[]` differs from lazy `InputStream/Stream<String>`. |
| Are wrappers involved? | Does outer `close()` propagate to the inner source? |
| Does the method **flush**? | If so, when; never equate flush with close or disk sync. |
| What when exceptions happen? | Who still closes the resource, how are close errors reported, are suppressed preserved? |
| Is there shared access or other threads? | Who coordinates closing to avoid closing while others read/write? |
| How is **new ownership** handed over? | Factory return, constructor transfer, explicit close-on-completion, or callback scope? |
| Where will callers learn the contract? | Method name, Javadoc, return type, tests, and clear call examples. |

## 15. Common Code Review Mistakes

1. **"Whoever creates it must always close it."** Not always true: a factory creating and returning a resource may transfer ownership to the caller; a framework creating a resource may keep cleanup responsibility.
2. **"Method takes `InputStream`, so just write `try (in)`."** Wrong if input is borrowed; try closes the borrowed stream.
3. **"No `close()` visible in helper means a leak."** The caller may be the owner; inspect the full lifecycle and contract.
4. **"Closing `BufferedReader` only closes its buffer."** False for standard wrappers: it normally closes the inner reader/stream too.
5. **"Closing Scanner does not affect `System.in`."** False if Scanner was constructed from `System.in`; closing Scanner closes the `Closeable` source.
6. **"`findFirst()`/`count()` automatically closes `Files.lines`."** False: close resource-backed `Stream` instances with try-with-resources.
7. **"`transferTo` automatically closes input and output."** False: the copy method does not take ownership of either stream.
8. **"`flush()` is enough, no need to close."** Flush does not end the lifecycle or release handles.
9. **"close cannot throw errors."** False: `IOException` or exceptions in `AutoCloseable.close()` can occur during cleanup.
10. **"When the body throws, close does not run."** False with try-with-resources; close still runs and secondary errors go into `getSuppressed()`.
11. **"Using the resource after a callback method returns is fine."** False if the owning scope already closed it; this is a lifetime-escape bug.
12. **"Launch async inside try, then return is fine."** The task can outlive the scope; the resource closes while the task is still using it.
13. **"Just call close twice to be safe."** `Closeable` states repeat close has no effect, yet broader `AutoCloseable` does not require idempotency; define one clear owner.
14. **"Closing a file deletes the file."** Two independent operations; resource closing and file deletion have separate lifecycles.
15. **"Ignore file close errors because write succeeded."** Close may be when buffers flush or errors surface; handle according to required data guarantees.

## 16. Self-Check Questions

1. A library provides `copy(InputStream in, OutputStream out)`, and the caller passes a socket output stream used again afterward. Who should close `out` and why?
2. How do `Files.readString(path)` and `Files.lines(path)` differ regarding ownership?
3. When you close a `BufferedReader` created from `InputStreamReader(System.in)`, what can happen to `System.in`?
4. A factory `openLog(Path)` returns an `InputStream`. What Javadoc must be present so callers do not forget to close?
5. Why can `try (InputStream in = callerInput)` inside a method violate the contract?
6. If the body throws an exception and two resource closes also throw, how are they reported?
7. Why can creating `new Scanner(System.in)` and closing it after one read break a CLI that still has subsequent prompts?
8. Can a callback borrowing a reader in `withReader(path, callback)` store that reader in a field for a background thread to use later?
9. If a resource is opened in `main` yet passed to an async task, who must decide when to close it?
10. Should you fix resource leaks by closing every `AutoCloseable` you spot in code? State which contracts must be checked first.

**Suggested Answers:** (1) The caller/owner because the helper only borrows the stream; (2) `readString` manages the handle internally, `lines` returns a lazy stream the caller must close; (3) closing the wrapper can close stdin; (4) document that the returned stream is open and the caller must close it; (5) try will close the borrowed variable; (6) the body exception is primary, close errors are suppressed in reverse declaration order; (7) scanner can close the source; (8) no if the owner closes when the callback finishes; (9) the owner closes once the task finishes or the task takes ownership; (10) no, you must check ownership and wrapper propagation first.

## 17. Official API References

- [Oracle Java SE 21 — Closeable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html): close releases I/O resources, repeat-close contract, and `IOException` errors.
- [Oracle Java SE 21 — AutoCloseable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AutoCloseable.html): try-with-resources and notes on close throwing exceptions.
- [Oracle Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): methods that read data directly, methods returning open streams, and requirement to close `Files.lines/list/walk`.
- [Oracle Java SE 21 — Scanner](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Scanner.html): closing a scanner also closes its input source if it implements `Closeable`.
- [Oracle Java SE 21 — InputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): `close()`, `transferTo()`, and distinguishing copy behavior from closing resources.
- [Oracle Java SE 21 — BufferedReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/BufferedReader.html) and [InputStreamReader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStreamReader.html): relationship between wrappers and underlying sources.

**Practical Takeaway:** **"Who opens, who closes" is a question about ownership contracts, not where the `new` keyword appears.** If you create a resource for internal use, use try-with-resources and clean it up within scope. If you borrow a resource from a caller, do not close it yourself. If you return an open resource, transfer closing responsibility explicitly. With wrappers, callbacks, and async tasks, always verify the real lifetime of the underlying resource.

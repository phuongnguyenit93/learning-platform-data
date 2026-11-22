# Avoiding Accidental Closure of Shared Standard Streams in Java

In Java applications, `System.in`, `System.out`, and `System.err` are often used across many places: reading console commands, printing results, logging messages, and reporting errors. An action that looks reasonable—such as placing `Scanner(System.in)` inside `try-with-resources` in a utility method—can cause **standard input to be closed** when the method returns. The rest of the program can then no longer read input as before.

The core principle of this lesson: **close only resources that you own or are authorized to close**. A helper that merely borrows a standard stream to read or write **must not end that stream's lifecycle**. When wrapping with `Scanner`, `BufferedReader`, `PrintWriter`, or other wrappers, remember that calling `close()` on the wrapper can **close the underlying stream as well**.

## 1. What Are Java's Three Standard Streams?

The `java.lang.System` class provides three shared static fields in a Java process:

| Stream | Type | Typical Role | Example |
|---|---|---|---|
| `System.in` | `InputStream` | Receives standard input data (stdin) | Reading user-typed content or data redirected from a file |
| `System.out` | `PrintStream` | Outputs normal results/information (stdout) | `System.out.println("OK")` |
| `System.err` | `PrintStream` | Outputs error/diagnostic messages (stderr) | `System.err.println("Lỗi nhập liệu")` |

`System.in` supplies **bytes**, while `System.out` and `System.err` are `PrintStream` objects offering convenient `print`/`println`/`printf` methods. These names describe **I/O channels**, not a guarantee that the other end is always a physical keyboard or screen.

Example run from a shell:

~~~bash
java Main < input.txt > output.txt 2> error.txt
~~~

What the command means: Java's stdin is connected to `input.txt`, stdout is directed to `output.txt`, and stderr to `error.txt`. In an IDE, test environment, container, or service, these streams may also be connected to other systems. Therefore, a method deep inside an application **must not treat itself as their exclusive owner**.

The `System.in`, `System.out`, and `System.err` fields can be replaced via `System.setIn(...)`, `System.setOut(...)`, and `System.setErr(...)` by application code with appropriate permissions, such as in tests or when embedding an application. This further reinforces the need to distinguish **who provides the stream, who uses it, and who closes it**.

## 2. Why Is Closing a Standard Stream in a Helper Dangerous?

Suppose a program has two phases:

~~~text
main()
  ├── readProfile(): reads one line from System.in
  └── readCommand(): reads another command from System.in
~~~

If `readProfile()` creates a `Scanner` wrapping `System.in` and closes the scanner on return, it may **close `System.in` as well**. When `readCommand()` tries to read next, it may encounter an error or find no remaining readable data.

An error-prone code pattern:

~~~java
// DO NOT DO THIS if the application still needs System.in after this method.
static String readOneName() {
    try (Scanner scanner = new Scanner(System.in)) {
        return scanner.nextLine();
    } // scanner.close() also closes the System.in input source.
}
~~~

This is an **ownership bug illustration**, not a recommended example. `Scanner.close()` invokes `close()` on its input source if that source implements `Closeable`; `System.in` is an `InputStream` and implements this interface.

The issue is not `try-with-resources` itself: that mechanism is **right** when the resource is owned by the method's scope. The mistake is placing a **wrapper borrowing a shared resource** into an auto-closing block.

A similar mistake with stdout:

~~~java
// DO NOT DO THIS: closing the wrapper may close System.out.
static void printReport() {
    try (PrintWriter writer = new PrintWriter(System.out)) {
        writer.println("Báo cáo hoàn tất");
    }
}
~~~

`PrintWriter.close()` closes the writer and the underlying output layer. Because `System.out` is a shared stream, later code printing logs or results may stop working as expected. `PrintStream` instances like `System.out` typically record errors instead of throwing `IOException` from `print`/`println`, so accidentally closing stdout might not manifest as an obvious exception.

**Closing a wrapper** is usually different from **finishing using a wrapper**. When the caller owns a standard stream, a helper may use a temporary wrapper to read/write, yet must not arbitrarily call `close()` on it.

## 3. Ownership and Lifecycle: Ask Who Is Responsible for Closing?

**Ownership** is the agreement on which party is responsible for terminating a resource. It cannot be deduced merely from a parameter type like `InputStream` or `OutputStream`.

### Case A — Method Opens the Resource Itself: Method Is Responsible for Closing

Example opening a file to read:

~~~java
static String readFile(Path path) throws IOException {
    try (BufferedReader reader =
                 Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
        return reader.readLine();
    }
}
~~~

This is an **illustrative method**, requiring imports for `java.io.*`, `java.nio.file.*`, and `java.nio.charset.StandardCharsets`. The file stream is created inside the method; once reading finishes, the method no longer needs it. Using `try-with-resources` to close it is appropriate.

### Case B — Method Receives a Stream from the Caller: Method Only Borrows

~~~java
static void writeGreeting(PrintStream destination, String name) {
    destination.println("Xin chào, " + name);
    // Do not call destination.close(): the caller owns it.
}
~~~

This is an **illustrative method** accepting a `PrintStream` from the caller. It can be used with `System.out`, `System.err`, or another `PrintStream` created by the caller. The method's contract is **writing one line**, not **terminating the destination**.

### Case C — Environment-Managed Standard Streams: Do Not Close in Local Code

`System.in`, `System.out`, and `System.err` typically live for the entire application lifetime and can be shared by libraries, frameworks, command loops, REPLs, or logging components. A method reading one prompt or printing one report is merely a **temporary user**.

| Who Creates/Supplies the Resource? | User | Who Normally Closes It |
|---|---|---|
| Method opens `FileInputStream`/`Files.newInputStream` | That same method | The method, usually with `try-with-resources` |
| Caller passes `InputStream` into a library | Library/helper only borrows | The caller, unless the contract explicitly transfers ownership |
| Java runtime or app environment supplies `System.in/out/err` | Many parts of the application | Application/environment lifecycle manager; helpers do not close them |
| Method creates `ByteArrayInputStream` or `ByteArrayOutputStream` | The method | The method; closing in-memory streams may not release OS resources, yet a clear contract still helps |
| Framework provides request/response stream | Callback code | Per framework contract |

**Remember:** ownership is an **API contract**. When designing public methods, explicitly document "this method does not close the passed input/output stream" or "this method takes ownership and will close the stream".

## 4. How Can Wrappers Close Standard Streams?

An underlying stream can be wrapped in multiple layers. When closing the outer layer, many standard classes forward the close operation down to inner layers:

~~~text
Scanner.close() ------------------------> System.in.close()

BufferedReader.close()
  -> InputStreamReader.close() ----------> System.in.close()

PrintWriter.close()
  -> OutputStreamWriter.close() ---------> System.out.close()

BufferedOutputStream.close() -----------> System.out.close()
~~~

The diagram illustrates cases where wrappers actually wrap **the standard streams themselves**. Whether closing propagates deeply depends on the specific wrapper's contract; these examples illustrate standard JDK wrapper behavior.

### `Scanner`

`Scanner` can accept an `InputStream`, `Readable`, `File`, `Path`, or `String` depending on the constructor. If the source is `Closeable`, `scanner.close()` also closes the source. Therefore:

~~~java
Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8);
String name = scanner.nextLine();
// Do not call scanner.close() if the application still uses System.in.
~~~

This is an **illustrative snippet**, requiring imports for `java.util.Scanner` and `java.nio.charset.StandardCharsets`. If a helper genuinely owns its source, closing rules differ.

### `BufferedReader` and `InputStreamReader`

~~~java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(System.in, StandardCharsets.UTF_8));
String line = reader.readLine();
// Do not call reader.close() in a helper that only borrows System.in.
~~~

`BufferedReader` wraps `InputStreamReader`; closing the outermost reader closes the character adapter, which in turn closes the underlying byte stream. An important addition: **buffered readers can read ahead multiple bytes/characters**. Creating multiple separate `Scanner`/`BufferedReader` instances reading `System.in` can cause them to contend over data even without closing the stream. Use **a single shared reader at the appropriate layer** for the same input session.

### `PrintWriter`, `OutputStreamWriter`, and `PrintStream`

~~~java
Writer writer = new OutputStreamWriter(System.out, StandardCharsets.UTF_8);
writer.write("Xin chào\n");
writer.flush(); // Push the character buffer to the borrowed output.
// Do not call writer.close() in a helper that only borrows System.out.
~~~

`OutputStreamWriter` converts characters to bytes using the specified charset. `flush()` pushes data in the writer's buffer down to the underlying output; unlike `close()`, it does not terminate the stream. If `PrintWriter` wraps `System.out`, `PrintWriter.close()` also closes the underlying target per the wrapper contract.

**Note on charset:** `System.out` is already a `PrintStream` with a mechanism for converting characters to bytes for the runtime's configured target. Wrapping it in `OutputStreamWriter(System.out, UTF_8)` introduces a separate encoding layer; do this only when you **intentionally** want UTF-8 bytes to go through that layer and it fits the environment. For ordinary console printing, calling `System.out.print/println/printf` directly is usually clearer.

## 5. Java 17 Example: Helper Borrows Streams, Owner Closes Later

To verify the behavior of **not closing caller-managed sources/targets** without disrupting the real `System.in`/`System.out`, the program uses two test streams that flip a flag whenever `close()` is called.

The `greet` helper receives an input and output. It creates a `Scanner` to read a line and an `OutputStreamWriter` to write UTF-8, calls `flush()` as needed, and **does not call `close()`**. After the helper returns, the caller can keep writing to the output. Only the **owner** places both source and destination in `try-with-resources`.

Save the complete code to **`SharedStandardStreamsDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class SharedStandardStreamsDemo {
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

    // Only borrows input/output; close ownership belongs to the caller.
    static void greet(InputStream input, OutputStream output)
            throws IOException {
        Scanner scanner = new Scanner(input, StandardCharsets.UTF_8);
        Writer writer = new OutputStreamWriter(output, StandardCharsets.UTF_8);

        writer.write("Tên: ");
        writer.flush();
        if (scanner.hasNextLine()) {
            String name = scanner.nextLine();
            writer.write("Xin chào, " + name + "\n");
            writer.flush();
        }
        // Do not call scanner.close() or writer.close().
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream capture = new ByteArrayOutputStream();
        TrackedInput input = new TrackedInput(
                new ByteArrayInputStream(
                        "Mai\n".getBytes(StandardCharsets.UTF_8)));
        TrackedOutput output = new TrackedOutput(capture);

        try (input; output) {
            greet(input, output);
            output.write("Tiếp tục\n".getBytes(StandardCharsets.UTF_8));
            output.flush();

            System.out.println("Trong try: inputClosed=" + input.closed
                    + ", outputClosed=" + output.closed);
        }

        System.out.println("Sau try: inputClosed=" + input.closed
                + ", outputClosed=" + output.closed);
        System.out.println("Nội dung đã ghi:");
        System.out.print(capture.toString(StandardCharsets.UTF_8));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 -encoding UTF-8 SharedStandardStreamsDemo.java
java SharedStandardStreamsDemo
~~~

Output when the console supports Vietnamese display:

~~~text
Trong try: inputClosed=false, outputClosed=false
Sau try: inputClosed=true, outputClosed=true
Nội dung đã ghi:
Tên: Xin chào, Mai
Tiếp tục
~~~

**Explanation:**

1. `TrackedInput` and `TrackedOutput` are wrappers recording `close()` calls around in-memory byte streams. They serve solely to verify **caller-controlled lifecycle**.
2. `greet` reads `"Mai\n"`, writes output through `Writer`, calls `flush()` to push writes at that point, yet **does not close the wrappers**.
3. Immediately after `greet` returns, both `closed` flags remain `false`. The caller even successfully calls `output.write(...)` to append `"Tiếp tục\n"`.
4. Upon exiting `try (input; output)`, Java automatically calls `close()` on the resources **whose ownership the caller declared** (in reverse declaration order: output then input). Both flags then become `true`.
5. The real `System.out` is used only to print the report; the example **never closes or replaces** any process standard stream.
6. `ByteArrayOutputStream` can still provide its written bytes even after being closed; this is specific to this class. Do not assume files/sockets behave similarly after `close()`.

In a real application, if `greet(System.in, System.out)` is called from a command loop, the borrowing contract still applies: the helper must not close the standard streams because the caller may continue reading/writing. However, do not repeatedly create a new `Scanner` on `System.in` inside a command loop, because a scanner may **read ahead** and retain data in its private buffer. Instead, let the caller create **one shared reader/scanner** and pass it to the helpers.

## 6. Better API Design: Caller Owns the Scanner, Helpers Just Use It

If an entire program asks multiple questions, lift reader creation and management up to the application layer:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Scanner;

public class SharedConsoleReader {
    static void askName(Scanner scanner) {
        System.out.print("Tên: ");
        if (scanner.hasNextLine()) {
            String name = scanner.nextLine();
            System.out.println("Xin chào, " + name);
        }
        // Helper does not close scanner.
    }

    static void askCity(Scanner scanner) {
        System.out.print("Thành phố: ");
        if (scanner.hasNextLine()) {
            String city = scanner.nextLine();
            System.out.println("Bạn ở " + city);
        }
        // Still does not close scanner.
    }

    public static void main(String[] args) {
        Scanner sharedScanner =
                new Scanner(System.in, StandardCharsets.UTF_8);
        askName(sharedScanner);
        askCity(sharedScanner);
        // Do not close System.in in the illustrative program.
    }
}
~~~

This is a **standalone Java 17 program**, saved as `SharedConsoleReader.java`. When running `java SharedConsoleReader`, the user enters a name and a city in turn. Interactive output depends on user responses; for example, entering `Lan` then `Đà Nẵng`:

~~~text
Tên: Lan
Xin chào, Lan
Thành phố: Đà Nẵng
Bạn ở Đà Nẵng
~~~

In practice, many terminals echo typed characters on the prompt line. The snippet above is a **sample interactive session**, not a fixed output string in every setup.

Benefits of this design:

- Only **one** `Scanner` reads `System.in`, reducing the risk of competing buffers.
- Each helper receives an existing reader and does not dictate the whole application's lifecycle.
- Testing becomes easier: callers can pass a `Scanner` built from a `String`, and output can be parameterized with a `PrintStream` rather than writing directly to `System.out`.
- The coordinator layer decides when the input stream truly ends, based on the application contract.

There is no requirement to close `System.in` at the end of `main` in every console application. When the process exits, the OS reclaims process resources; avoiding closing standard streams in helpers prevents side effects on components still running. For resources **opened by the application itself**, still close them at the right time.

## 7. `flush()` Is Not `close()`

When writing through a buffered layer, data may not reach the destination immediately after `write()`. Three distinct operations:

| Operation | Purpose | Effect on Further Use |
|---|---|---|
| `write(...)` / `print(...)` | Sends characters/bytes into the output API, possibly buffered | Usually safe to keep writing |
| `flush()` | Requests pushing buffered content down to the underlying output layer | **Does not close**; can keep writing |
| `close()` | Ends the stream/wrapper lifecycle, typically flushing per contract then closing the lower layer | **Must not be used afterward** |

In a helper using a `Writer` wrapping `System.out`, if you need buffered output pushed out before returning, call `writer.flush()`; that is **never a reason to call `writer.close()`**.

`PrintWriter` has constructors accepting an **autoFlush** option, though you should not assume "autoFlush = true" makes every write method flush. On `PrintWriter`, auto-flush applies to operations like `println`, `printf`, and `format` per the class contract; plain `write` or `print` may not trigger as expected. When clear output boundaries are required, check the contract and call `flush()` appropriately.

Similarly, `System.out.flush()` and `System.err.flush()` are much safer than `close()` when you only want to push written data. Still, `flush()` does not guarantee data is durably stored on disk or processed by a remote network receiver.

## 8. Easy-to-Miss Details

### Closing `System.out` Sometimes Reports No Immediate Error

`PrintStream`'s `print`/`println` operations do not propagate `IOException` directly like many other output APIs. Consequently, after a library accidentally closes stdout, subsequent print statements **may silently produce no output** instead of immediately throwing an obvious exception. `PrintStream.checkError()` lets you inspect the error flag per contract, yet **error checking does not replace** proper ownership design.

Do not experiment on real `System.out` by deliberately calling `System.out.close()` to "see what happens", especially inside IDEs, test runners, notebooks, or shared multi-feature processes.

### `System.err` Is Also a Shared Resource

Do not assume stderr can be closed arbitrarily just because it "only logs errors". Logging tools, exception handlers, and frameworks may still need `System.err` after your call. Even though a terminal merges stdout and stderr onto one display, that **does not alter** the ownership lifecycle of the two `PrintStream` objects.

### Closing a Wrapper When the Caller Still Needs the Stream Violates the Contract

Example:

~~~java
// WRONG if the caller still needs to use System.out:
try (BufferedOutputStream buffered = new BufferedOutputStream(System.out)) {
    buffered.write("Hello\n".getBytes(StandardCharsets.UTF_8));
} // BufferedOutputStream.close() closes the underlying stream.
~~~

This is an **anti-example of behavior to avoid**. Required imports include `java.io.BufferedOutputStream` and `java.nio.charset.StandardCharsets`; the enclosing method must handle/declare `IOException`. If buffering is genuinely needed, manage that layer at the stream-ownership level or design an API accepting a caller-managed writer, flushing at contract boundaries.

### Redirecting Streams in Tests Must Also Be Restored

When tests need to intercept output, `System.out` can be swapped with a `PrintStream` writing to a `ByteArrayOutputStream`. Calling `System.setOut(...)` mutates **global state** and can affect concurrent tests. If swapping is unavoidable, restore the original stream in `finally` and close only the temporary stream created by the test; avoid accidentally closing the original stream. For library code, a design accepting `PrintStream`/`Writer` via parameters is usually easier to test and avoids global side effects.

### `try-with-resources` Is Not Wrong; Wrong Ownership Assignment Causes the Bug

~~~java
// CORRECT: opened input from a file ourselves, own it, so close it ourselves.
try (InputStream input = Files.newInputStream(path)) {
    input.transferTo(System.out);
}
// input is closed; System.out remains open.
~~~

This is an **illustrative snippet** with a declared `Path path`, requiring imports for `java.io.InputStream` and `java.nio.file.Files`, plus `IOException` handling. `transferTo` itself **does not close** either input or output. Here `try-with-resources` encloses only **the input we own**, so it does not close `System.out`.

**A rule no syntax trick can replace:** before using `try-with-resources`, ask "who owns this resource and has the right to terminate it?".

## 9. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| `try (Scanner sc = new Scanner(System.in))` in a helper reading one value | Closing scanner closes the shared input source | Use a shared scanner provided by the caller; helper only reads |
| `try (PrintWriter w = new PrintWriter(System.out))` in a print helper | Exiting `try` may close stdout | Use `System.out` directly or a caller-managed writer |
| Calling `System.out.close()` after printing a block | Subsequent code may fail to print | If you only want to push the buffer, call `flush()` |
| Calling `System.err.close()` assuming stderr is no longer needed | Subsequent logging/errors may be lost | Leave stderr to the application lifecycle manager |
| Assuming closing a wrapper only frees its own buffer | Many wrappers also close the underlying stream | Check the `close` contract of each class |
| Creating multiple `Scanner` instances reading `System.in` | Read-ahead buffering traps data inside separate scanners | Create one shared scanner and pass it down to helpers |
| Not closing `Files.newInputStream` out of fear of closing standard streams | File descriptor leaks unrelated to stdout/stdin | Close file resources you opened; only leave borrowed streams open |
| Using `close()` instead of `flush()` after each record | Terminates the output sink prematurely | Flush appropriately, let the owner close when finished |
| Assuming `System.out` is always a screen | When redirected, stdout may be a file or pipe | Treat the stream by its I/O channel role |
| Tests replacing `System.out` without restoring it | Other tests are affected by global state | Restore the original reference in `finally` |

## 10. Self-Check Exercises

**Question 1.** A method `askAge()` creates `Scanner(System.in)` in `try-with-resources`. Another method next needs to read a name from `System.in`. What is wrong?

> The first method **closed the scanner**, which closed the input source per `Scanner`'s contract. It is better to create one scanner at the coordinator layer and pass it into both methods without closing it inside the helpers.

**Question 2.** A helper receives `OutputStream out` from the caller and wraps it in `OutputStreamWriter(out, UTF_8)`. Should the helper call `writer.close()` after each write?

> No, unless the contract lets the helper own and close the output. When merely borrowing, it can call `writer.flush()` to push data, because closing the writer closes the underlying stream.

**Question 3.** When is `try-with-resources` the right choice?

> When code **opens and owns** a resource—such as `Files.newInputStream(path)` or `Files.newBufferedWriter(path, UTF_8)`—and no longer needs it after the block ends. For borrowed streams, close responsibility belongs to the caller or owning layer.

**Question 4.** Running `System.out.println("Done")` after a library closed `System.out` shows no error. Does that prove stdout still works?

> No. `PrintStream` can record an internal error instead of throwing `IOException` from `println`. You must fix the improper stream closure and, when diagnosing, can inspect `checkError()`.

**Question 5.** Why avoid two independent `Scanner` objects reading `System.in` even if neither is closed?

> Because each scanner can **read ahead** data into its own buffer; one scanner may already have consumed bytes that the other expected to read. Use one shared scanner for the same input session to manage data order.

**Question 6.** A method opens a file's `InputStream` and calls `input.transferTo(System.out)`. Which stream should be closed in the method?

> Close the **file input opened by the method**, usually with `try-with-resources`. Do not close `System.out` because it is a shared standard stream; `transferTo` itself closes neither stream.

## Takeaways

**Standard streams `System.in`, `System.out`, and `System.err` are channels normally shared across an application.** Wrappers like `Scanner`, `BufferedReader`, and `PrintWriter` can **close the underlying source/destination** when `close()` is called. Therefore:

1. **Close** streams you create and own (using `try-with-resources`).
2. **Do not close** streams supplied by callers or the environment when merely borrowing them.
3. **Share a single reader** for `System.in` when a program reads multiple turns.
4. **Distinguish `flush` from `close`** when outputting buffered data.

A well-designed API always makes clear **who owns, who only uses, and when resources are closed**. This is the key to ensuring console programs, CLI tools, libraries, and Java tests never accidentally break shared streams.

**References:** [Java SE 17 — `System`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html), [`Scanner.close()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Scanner.html#close()), [`PrintStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html), [`PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html).

# How `PrintStream` Differs from `PrintWriter` in Java I/O

## Objectives

Java has two familiar output classes supporting `print`, `println`, `printf`, and `format`: `java.io.PrintStream` and `java.io.PrintWriter`. Their syntax is similar, yet they differ in **target destination type, bytes vs. characters, charset handling, auto-flush rules, and how I/O errors are reported**.

After this lesson, you will:

- Distinguish `PrintStream extends FilterOutputStream` from `PrintWriter extends Writer` and choose based on destination type.
- Understand why `print("é")` differs from `write(0xE9)` on `PrintStream`.
- Specify a charset explicitly when converting characters to bytes.
- Understand exactly what causes each class to call `flush()` automatically when `autoFlush` is enabled.
- Properly handle write errors where `print` does not throw `IOException` directly outward.
- Know how to use these classes with the console, files, memory, and Java 17+ programs.

## 1. Core Difference in the Hierarchy

```text
Java Data: int, double, String, Object
                     |
        print / println / printf / format
                     |
        +------------+-------------+
        |                          |
        v                          v
   PrintStream                PrintWriter
   (OutputStream)               (Writer)
        |                          |
        v                          +---> Target Writer:
  converts characters to bytes          StringWriter,
  using chosen charset                  BufferedWriter,...
        |                          |
        v                          +---> or OutputStream
    OutputStream                       via OutputStreamWriter layer
    (file/socket/memory)
```

`PrintStream` is a type of `OutputStream`: besides printing text representations, it has methods to write **raw bytes**. `PrintWriter` is a type of `Writer`: its `write` operations accept **characters/character strings** and have no raw `byte[]` write method. Nevertheless, `PrintWriter` **does have constructors accepting an `OutputStream`**, in which case it places a character-to-byte encoding layer underneath.

| Criterion | `PrintStream` | `PrintWriter` |
| --- | --- | --- |
| Inheritance | `FilterOutputStream` → `OutputStream` | `Writer` |
| Direct suitable target | `OutputStream` | `Writer` or `OutputStream` via conversion |
| Writing raw bytes | `write(int)`, `write(byte[], off, len)`, `writeBytes(byte[])` | No `write(byte[])` API |
| Writing Java values | `print`, `println`, `printf`, `format` | `print`, `println`, `printf`, `format` |
| I/O errors during print operations | Sets internal error flag; check with `checkError()` | Also sets internal error flag; check with `checkError()` |
| `autoFlush` | Includes triggers related to newline/byte-array writes and `println` | Only on `println`, `printf`, `format` |
| Examples | `System.out`, `System.err` | Generating reports with `StringWriter`, `BufferedWriter` |

You must understand accurately what "`PrintStream` works with bytes" means: **it does not mean `PrintStream.print(String)` writes each Java `char` directly as a byte**. Text is encoded using a charset before being written to the `OutputStream`. Conversely, `PrintWriter` is character-oriented yet can still write to files/sockets through an `OutputStreamWriter`.

## 2. Java 17+ Example: Same Text, Two Target Types

The program below produces deterministic output across operating systems by normalizing line endings for **display**, without altering the written data itself.

Save as **`PrintTargetsDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class PrintTargetsDemo {
    private static String display(String text) {
        return text.replace("\r\n", "\n")
                   .replace('\r', '\n')
                   .replace("\n", "|");
    }

    public static void main(String[] args) {
        ByteArrayOutputStream byteSink = new ByteArrayOutputStream();

        try (PrintStream ps =
                     new PrintStream(byteSink, true, StandardCharsets.UTF_8)) {
            ps.print("Count=");
            ps.println(7);
            ps.printf(Locale.ROOT, "Ratio=%.1f%n", 2.5);
        }

        StringWriter charSink = new StringWriter();
        try (PrintWriter pw = new PrintWriter(charSink, true)) {
            pw.print("Count=");
            pw.println(7);
            pw.printf(Locale.ROOT, "Ratio=%.1f%n", 2.5);
        }

        String textFromBytes =
                new String(byteSink.toByteArray(), StandardCharsets.UTF_8);
        System.out.println("PrintStream: " + display(textFromBytes));
        System.out.println("PrintWriter: " + display(charSink.toString()));
    }
}
```

Compile and run:

```bash
javac PrintTargetsDemo.java
java PrintTargetsDemo
```

Output:

```text
PrintStream: Count=7|Ratio=2.5|
PrintWriter: Count=7|Ratio=2.5|
```

With `PrintStream`, the result is held in `ByteArrayOutputStream` as UTF-8 bytes; the program then decodes it back to a `String`. With `PrintWriter`, `StringWriter` holds characters directly. Both print the same content; **the difference lies in the interface, destination, and encoding process**, not the visual form of `println`.

Notes:

- `Locale.ROOT` keeps `%.1f` printing `2.5` consistently instead of depending on the system locale.
- `println` and `%n` use the platform's line separator, which is why the display helper converts it to `|`.
- `try-with-resources` calls `close()` at the end of the block. These two in-memory sinks still allow reading their contents afterward for demonstration; do not assume every file/socket sink can be used after closing.

## 3. Charset: One Character Can Produce Multiple Bytes

In Java, `String`/`char` represent character data; `OutputStream` holds bytes. For the letter `é`, the valid UTF-8 encoding is **two bytes `C3 A9`**.

- `PrintStream.print("é")` with UTF-8 writes `C3 A9`.
- `PrintStream.write(0xE9)` writes the raw byte `E9`; this single byte is **not** valid UTF-8 for `é`.
- `PrintWriter.print("é")` with a UTF-8 encoding layer writes `C3 A9`.

Standalone example **`PrintCharsetDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class PrintCharsetDemo {
    public static void main(String[] args) {
        ByteArrayOutputStream a = new ByteArrayOutputStream();
        try (PrintStream out =
                     new PrintStream(a, false, StandardCharsets.UTF_8)) {
            out.print("é");
        }

        ByteArrayOutputStream b = new ByteArrayOutputStream();
        try (PrintStream out =
                     new PrintStream(b, false, StandardCharsets.UTF_8)) {
            out.write(0xE9);
        }

        ByteArrayOutputStream c = new ByteArrayOutputStream();
        try (PrintWriter out =
                     new PrintWriter(c, false, StandardCharsets.UTF_8)) {
            out.print("é");
        }

        HexFormat hex = HexFormat.of();
        System.out.println("PrintStream text = " + hex.formatHex(a.toByteArray()));
        System.out.println("PrintStream raw = " + hex.formatHex(b.toByteArray()));
        System.out.println("PrintWriter text = " + hex.formatHex(c.toByteArray()));
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 PrintCharsetDemo.java
java PrintCharsetDemo
```

Stdout:

```text
PrintStream text = c3a9
PrintStream raw = e9
PrintWriter text = c3a9
```

This is why **you must not use `write(int)` as a substitute for `print(char)`**. On `PrintStream`, `write(int)` takes a byte, not a Unicode code point. When outputting text content, use `print` with a charset compatible with the reader.

### Choosing a Charset When Constructing the Object

```java
// Illustrative snippet; output is a valid OutputStream owned by the application.
PrintStream ps =
        new PrintStream(output, true, StandardCharsets.UTF_8);
PrintWriter pw =
        new PrintWriter(output, true, StandardCharsets.UTF_8);
```

These are two **constructor alternatives**, not advice to use two writers concurrently on the same `output`. Wrappers sharing one `OutputStream` can have different buffering/flush behavior and compete over resource closing, making byte ordering hard to control.

- When no charset is passed, `OutputStream`-based constructors use the JVM's default charset; for externally exchanged data, **declare the charset explicitly**.
- When you already have a `Writer`, `PrintWriter(writer)` fits directly. If it is an `OutputStreamWriter`, encoding is determined by that `OutputStreamWriter`.
- By default, both classes replace unmappable character sequences with the charset's replacement character. If you require **detecting** unencodable data, use `CharsetEncoder` with `CodingErrorAction.REPORT`.
- Text written with `println` uses OS-dependent line endings; if a protocol requires an exact LF (`0A`) or CRLF (`0D 0A`) byte sequence, follow the protocol format rather than relying on `println`.

## 4. How Does `autoFlush` Differ?

Flushing is the operation of pushing unforwarded data out of buffers to the underlying layer. Flushing is **not synonymous** with closing a resource, does not assert data has been physically synced to disk, and does not guarantee a network peer has finished processing it.

### `PrintStream` Rules

When `autoFlush=true` is enabled, the `PrintStream` API specifies automatic flushing when:

1. A `println(...)` method is invoked.
2. A byte array is written to the stream (e.g., `write(byte[], off, len)`).
3. A newline character/byte `'\n'` is written; e.g., `print("\n")` or `write('\n')`.

### `PrintWriter` Rules

When `autoFlush=true` is enabled, the `PrintWriter` API flushes automatically **only when calling**:

1. `println(...)`.
2. `printf(...)`.
3. `format(...)`.

**`PrintWriter.print("\n")` does not auto-flush merely because the string contains a newline.** Similarly, `write("\n")` or `append('\n')` are not treated as auto-flush triggers. When you need to ensure data has passed through the buffer after such calls, invoke `flush()`.

| Call (autoFlush=true) | `PrintStream` | `PrintWriter` |
| --- | --- | --- |
| `println("ready")` | Auto-flushes | Auto-flushes |
| `print("\n")` | Auto-flushes due to newline | **Does not auto-flush** |
| `write('\n')` | Auto-flushes for LF byte | **Does not auto-flush** when writing LF character |
| `write(byte[], 0, len)` | Auto-flushes when writing byte array | No corresponding byte-write API |
| `printf("id=%d", 7)` | Not a separately listed trigger; call `flush()` if guaranteed flush is needed | **Auto-flushes**, even when format has no newline |

Internal implementation details may cause `PrintStream` to flush when a formatting operation eventually goes through the byte-write path; however, never rely on that in place of an explicit `flush()` at **protocol boundaries**.

### Java 17+ Example: Observing the Difference Directly in `PrintWriter`

Save file **`PrintWriterFlushDemo.java`**:

```java
import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Locale;

public class PrintWriterFlushDemo {
    static class CountingWriter extends StringWriter {
        int flushCount;

        @Override
        public void flush() {
            flushCount++;
        }
    }

    public static void main(String[] args) {
        CountingWriter sink = new CountingWriter();

        try (PrintWriter out = new PrintWriter(sink, true)) {
            out.print("first\n");
            System.out.println("after print = " + sink.flushCount);

            out.println("second");
            System.out.println("after println = " + sink.flushCount);

            out.printf(Locale.ROOT, "count=%d", 3);
            System.out.println("after printf = " + sink.flushCount);
        }
    }
}
```

Run:

```bash
javac PrintWriterFlushDemo.java
java PrintWriterFlushDemo
```

Output:

```text
after print = 0
after println = 1
after printf = 2
```

The numbers are printed **before** the `try-with-resources` block closes the writer. We are observing how many times `flush` is triggered inside the block, not measuring device speed or when data is durably persisted.

A real-world scenario: a program sends a request using `PrintWriter.print(...)` and waits for a response. If not flushed and the peer is waiting for the complete request, both sides can deadlock waiting on each other. When a protocol requires a delimiter or fixed length, **complete the message** and call `flush()` or use an appropriate trigger before reading the response.

## 5. I/O Write Errors Do Not Necessarily Escape from `print()`

Both classes are designed so text-printing methods **record I/O errors in an internal flag** rather than throwing `IOException` on each print call. Hence the snippet below can execute past `println` while the target never actually received the data:

```java
// Snippet: out is a PrintStream or PrintWriter already created.
out.println("result");
if (out.checkError()) {
    // Writing data encountered an I/O error detected by the print API.
}
```

`checkError()` inspects the error state and calls flush if the object is still open, helping surface errors occurring in the buffer as well. Note:

- `checkError() == true`: an error was recorded by the print class; handle it per application logic.
- `checkError() == false`: no error detected **at the time of checking**; does not prove disk writes are durable or that the recipient succeeded.
- Constructors opening files can still throw `IOException` or related exceptions. `printf` syntax errors (`IllegalFormatException`) or `NullPointerException` are also not suppressed by the "no IOException thrown" rule.
- If you need to **catch `IOException` directly at the write site**, use `Writer`/`OutputStream` or classes such as `BufferedWriter` and `OutputStreamWriter` instead of relying solely on `print`.

### Java 17+ Example: Simulating a Failing Write Target

Create **`PrintErrorDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.io.PrintWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class PrintErrorDemo {
    static class FailingOutputStream extends OutputStream {
        @Override
        public void write(int value) throws IOException {
            throw new IOException("write failed");
        }
    }

    static class FailingWriter extends Writer {
        @Override
        public void write(char[] chars, int offset, int length)
                throws IOException {
            throw new IOException("write failed");
        }

        @Override
        public void flush() throws IOException {
            throw new IOException("flush failed");
        }

        @Override
        public void close() {
            // No external resource.
        }
    }

    public static void main(String[] args) {
        try (PrintStream out = new PrintStream(
                new FailingOutputStream(), false, StandardCharsets.UTF_8)) {
            out.print("data");
            System.out.println("PrintStream error = " + out.checkError());
        }

        try (PrintWriter out = new PrintWriter(new FailingWriter())) {
            out.print("data");
            System.out.println("PrintWriter error = " + out.checkError());
        }
    }
}
```

Compile, run:

```bash
javac PrintErrorDemo.java
java PrintErrorDemo
```

Stdout:

```text
PrintStream error = true
PrintWriter error = true
```

The `print` methods **do not throw `IOException` directly** from the two simulated failing targets; `checkError()` reports the error state. In a real service, inspect the state after critical write/flush points, record the failure, and apply an error-handling strategy rather than assuming calling `print` means data was delivered successfully.

## 6. `System.out`, `System.err`, and the Console

`System.out` and `System.err` are **`PrintStream`** instances, not `PrintWriter`:

```java
System.out.println("Ready");
System.err.printf("Status=%d%n", 500);
```

This is a valid illustrative snippet inside a Java method. It explains why "Hello World" examples call `println` directly on `System.out`.

Do not close `System.out` or `System.err` inside a utility method:

```java
// Bad design example when the application still needs the console:
try (PrintStream console = System.out) {
    console.println("Ready");
}
```

`close()` typically closes the underlying resource as well and can prevent the rest of the program from printing anything further. Let the application lifecycle manager decide the lifetime of global streams.

You **can** wrap `System.out` in a `PrintWriter`:

```java
// Illustrative snippet: do not close arbitrarily as it may close the underlying System.out.
PrintWriter consoleWriter = new PrintWriter(System.out, true);
consoleWriter.println("Ready");
```

However, extra wrapping is usually unnecessary just for console printing and can complicate flush/close management. To test output, pass a `PrintStream` or `Writer` from the caller; tests can use `ByteArrayOutputStream` or `StringWriter` to compare contents.

In server applications, most long-term operational messages should go through an appropriate logging API instead of calling `System.out.println` everywhere.

## 7. When to Choose Which?

### Choose `PrintStream` When

- You already have an `OutputStream` and need to output formatted text/values.
- You are working with `System.out` or `System.err`.
- A library API specifically requires a `PrintStream` object.
- There is a clear reason to mix raw byte operations with text printing; you must define encoding and data framing rather than mixing arbitrarily in a protocol.

### Choose `PrintWriter` When

- You already have a `Writer` such as `BufferedWriter`, `StringWriter`, or a framework-provided writer.
- You want to work with **characters** and need `print`, `println`, and `printf` without needing to write raw bytes.
- You want to build text in memory and inspect its contents without intermediate encode/decode steps.

### Neither Is Always Strictly Necessary

| Requirement | API to Consider |
| --- | --- |
| Write text and catch `IOException` directly | `BufferedWriter`, `OutputStreamWriter`, `Files.newBufferedWriter` |
| Write binary data | `OutputStream`, `BufferedOutputStream` |
| Write primitive values in binary form | `DataOutputStream` |
| Accumulate text in memory | `StringWriter`; wrap in `PrintWriter` if formatting is needed |
| Strict character-encoding error control | `CharsetEncoder` + `CodingErrorAction.REPORT` |
| Production application logs | Logging framework |

Do not treat `PrintStream` as the default way to write a binary protocol merely because it also has `write(byte[])`. Conversely, there is no need to create a `PrintWriter` if an existing `Writer` only needs `write(String)` without formatting utilities.

## 8. Common Mistakes

1. **Confusing `PrintStream` with a text-only stream.** It can write raw bytes; `print` is a convenience API converting values to text on a byte stream.
2. **Thinking `PrintWriter` cannot write to files/sockets.** It can accept an `OutputStream` and charset. The API itself remains character-based.
3. **Using `PrintStream.write(int)` to encode Unicode.** That writes a byte, not a UTF-8 encoding of a Unicode code point.
4. **Assuming every call containing `\n` auto-flushes.** With `PrintWriter`, only `println/printf/format` trigger autoFlush; `print("\n")` is not enough.
5. **Ignoring `checkError()`.** `print` does not guarantee surfacing errors via exceptions and may let subsequent statements run even when the lower layer failed.
6. **Using `printf` without managing locale.** For machine-readable exchange files, use an explicit locale and specify the decimal separator.
7. **Assuming `println` always writes `\n`.** It uses the platform's line separator; network/file formats have specific rules that must be followed.
8. **Creating multiple wrappers writing to the same destination.** When buffers, charsets, and flush order differ, data can interleave or reorder; choose one owned write pipeline.
9. **Closing a writer borrowed from the caller.** `close()` typically closes the underlying target too; distinguish wrappers owned by a method from streams managed by the caller.
10. **Assuming flush means durable persistence.** Flush only moves data through the appropriate buffer layer; data durability or peer acknowledgment is a separate concern.

## 9. Self-Check

**Question 1.** Why does `System.out.println(...)` use `PrintStream`?

**Answer:** `System.out` is a `PrintStream`, a kind of `OutputStream` providing convenient print/formatting methods.

**Question 2.** Can `PrintWriter` accept an `OutputStream`?

**Answer:** Yes. Constructors taking an `OutputStream` build a character-to-byte conversion layer underneath; it remains a `Writer` API.

**Question 3.** Does `PrintWriter.print("\n")` with `autoFlush=true` guarantee immediate flushing?

**Answer:** No. `PrintWriter` auto-flushes on `println`, `printf`, or `format`; if needed, call `flush()` explicitly.

**Question 4.** Does `PrintStream.write(0xE9)` write the letter `é` in UTF-8?

**Answer:** No. It writes the exact byte `E9`, whereas `print("é")` in UTF-8 writes `C3 A9`.

**Question 5.** Does `out.println("ok")` completing without throwing an exception prove the file was written successfully?

**Answer:** No. Both print APIs can store I/O errors in an internal flag; you must check `checkError()` and handle errors according to the application's reliability requirements.

**Question 6.** What should be used to build a text report into a `StringWriter`?

**Answer:** Use `StringWriter.write(...)` directly when only writing strings; wrap with `PrintWriter` if `println` and `printf` value formatting are needed.

## 10. Official References

- [Java SE 17 — `PrintStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintStream.html)
- [Java SE 17 — `PrintWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [Java SE 17 — `OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [Java SE 17 — `StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)

**Takeaway:** `PrintStream` is a print class rooted in **byte streams**, and `PrintWriter` is a print class rooted in **character writers**; both share `print/println/printf` and `checkError`, yet **autoFlush differs**. Pick the class based on the actual destination and data, specify the charset when bytes are needed, check for I/O errors, and manage stream ownership properly.

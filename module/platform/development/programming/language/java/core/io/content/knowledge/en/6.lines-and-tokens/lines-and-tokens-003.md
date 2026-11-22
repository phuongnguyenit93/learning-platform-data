# BufferedWriter.newLine and System.lineSeparator in Java

When writing multiline text, we must distinguish **character content**, **line separator**, and **write buffering**. Two Java APIs are directly involved: `BufferedWriter.newLine()` and `System.lineSeparator()`:

- `BufferedWriter.newLine()` **writes a line terminator character sequence** following the platform's convention to the open character stream.
- `System.lineSeparator()` **returns a `String`** containing the line terminator sequence according to the platform's convention; calling this method alone **writes nothing**.
- Both are appropriate when you want to produce text files **using the runtime environment's line-ending convention**. If a format/protocol strictly requires `\n` or `\r\n`, you must write the exact sequence required by that standard rather than choosing automatically by operating system.

This lesson belongs to the **Lines and Tokens** topic of Java I/O: understanding how to separate lines of text and avoid corrupting data when writing, reading back, or exchanging files between operating systems.

## 1. What Is a Line Separator?

In text, a line break is typically represented by one or more control characters:

| Java Representation | Name | Common Where |
| --- | --- | --- |
| `"\n"` | LF, Line Feed, code `U+000A` | Unix/Linux, modern macOS |
| `"\r\n"` | CRLF, Carriage Return + Line Feed | Windows |
| `"\r"` | CR, Carriage Return, code `U+000D` | Some older formats and legacy systems |

For example, these two strings display similarly in many tools, yet **differ in character count and bytes**:

```java
String lf = "Một\nHai";      // "Một" + LF + "Hai"
String crlf = "Một\r\nHai";  // "Một" + CRLF + "Hai"
```

These are two illustrative declarations that can be placed inside a Java method. The actual number of control characters and bytes depends on how text is encoded to a file; for instance, when UTF-8 encoded, LF takes 1 byte `0A`, whereas CRLF takes 2 bytes `0D 0A`.

**Note:** A "new line" in text is not a distinct Java object. `BufferedWriter` only writes characters; `BufferedReader` can interpret line terminators when reading. A final line that does not end with a line break is still valid line content in many text formats.

## 2. What Does `BufferedWriter.newLine()` Do?

`BufferedWriter` is a buffered `Writer` that reduces the number of writes to the underlying stream. When you call:

```java
writer.newLine();
```

`BufferedWriter` writes the line terminator string obtained from the platform convention, described in Java via the `line.separator` system property. This **does not guarantee it is always a single `'\n'` character**: on Windows it is typically `"\r\n"`, and on Unix/Linux it is typically `"\n"`.

Illustrative snippet:

```java
writer.write("Dòng thứ nhất");
writer.newLine();
writer.write("Dòng thứ hai");
```

If the environment uses LF, the character result is `"Dòng thứ nhất\nDòng thứ hai"`. If it uses CRLF, it is `"Dòng thứ nhất\r\nDòng thứ hai"`. `newLine()` **does not automatically add spaces**, **does not write the next line's content**, and **does not call `flush()`** just because a line break was written.

### Signature and Exceptions

`newLine()` is an instance method in `java.io.BufferedWriter`, returning `void` and potentially throwing `IOException`:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.Writer;

// Illustrative method; the destination parameter is an already open Writer.
static void writeTwoLines(Writer destination) throws IOException {
    try (BufferedWriter writer = new BufferedWriter(destination)) {
        writer.write("Alpha");
        writer.newLine();
        writer.write("Beta");
    }
}
```

**Stream ownership:** closing `BufferedWriter` closes the underlying `Writer`. This method should only be used when it **is allowed to close** `destination`. If the caller still needs to use the passed-in stream, clearly establish ownership and lifecycle.

### Does `newLine()` Automatically Create a Blank Line?

Fundamentally, `newLine()` writes only **one line terminator**. If you write:

```java
writer.write("A");
writer.newLine();
writer.newLine();
writer.write("B");
```

an empty line will appear between A and B. Conversely, if you call `newLine()` after the last line, the file will **end with a line break**. Whether a trailing line break is needed at the end of the file depends on the conventions of the format, tool, or project.

## 3. What Does `System.lineSeparator()` Return?

`System.lineSeparator()` is a static method on `java.lang.System` that returns the platform-dependent line-ending string:

```java
String separator = System.lineSeparator();

String content = "Alpha" + separator + "Beta";
// Creates only a String; nothing is written to a file or OutputStream yet.
```

You can combine it with `StringBuilder`, `String.join`, or any `Writer`:

```java
String content = String.join(
        System.lineSeparator(),
        "Dòng 1", "Dòng 2", "Dòng 3"
);
```

Or:

```java
writer.write("Dòng 1");
writer.write(System.lineSeparator());
writer.write("Dòng 2");
```

These illustrative snippets assume `writer` already exists. `System.lineSeparator()` is suited for when you need to **build a `String` value containing environment-appropriate line breaks**, whereas `BufferedWriter.newLine()` is more concise when writing directly with a `BufferedWriter`.

According to Java documentation, `System.lineSeparator()` is based on the initial value of the `line.separator` property and remains constant at runtime. **Do not modify `System.setProperty("line.separator", ...)` mid-program to try to change a file's format**: this is not a reliable way to design output formatting. When fixed LF or CRLF is needed, use explicit string literals.

## 4. Comparison and Choice

| Criterion | `BufferedWriter.newLine()` | `System.lineSeparator()` |
| --- | --- | --- |
| API Kind | Instance method of a `BufferedWriter` | Static method of `System` |
| Effect | **Writes** the line terminator into the writer | **Returns a `String`**, writes nothing |
| Return value | `void` | `String` |
| Common exceptions | `IOException` on write | Does not declare `IOException` |
| When to use | Writing lines via `BufferedWriter` | Concatenating `String`s or writing through another API |
| Environment dependence | Follows environment's line separator | Follows environment's line separator |
| When fixed LF or CRLF must be emitted | Not the right choice | Not the right choice |

If the program **writes multiple lines directly to a file**, `BufferedWriter.newLine()` is readable:

```java
writer.write("Tên: An");
writer.newLine();
writer.write("Tuổi: 20");
```

If the program **builds text content beforehand**, `System.lineSeparator()` is convenient:

```java
String report = "Tên: An"
        + System.lineSeparator()
        + "Tuổi: 20";
```

When both use the same platform convention in a normal Java program, the corresponding line-ending content is identical. The key difference is that **one API performs a write**, while the other **supplies the character string**.

## 5. Complete, Runnable Java 17+ Program

The example below writes three lines to a `StringWriter` via `BufferedWriter`. After the writer closes, the program checks whether the resulting string matches joining with `System.lineSeparator()`, verifies exactly three lines with `BufferedReader.readLine()`, and checks whether a trailing line break was appended.

Save with the exact filename **`LineSeparatorDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.StringReader;
import java.io.StringWriter;

public class LineSeparatorDemo {

    public static void main(String[] args) throws IOException {
        StringWriter destination = new StringWriter();

        try (BufferedWriter writer = new BufferedWriter(destination)) {
            writer.write("Dòng một");
            writer.newLine();
            writer.write("Dòng hai");
            writer.newLine();
            writer.write("Dòng ba");
        }

        String actual = destination.toString();
        String expected = String.join(
                System.lineSeparator(),
                "Dòng một", "Dòng hai", "Dòng ba"
        );

        System.out.println("Matches platform separator: " +
                actual.equals(expected));
        System.out.println("Logical line count: " +
                countLines(actual));
        System.out.println("Ends with separator: " +
                actual.endsWith(System.lineSeparator()));
    }

    private static int countLines(String text) throws IOException {
        int count = 0;

        try (BufferedReader reader =
                     new BufferedReader(new StringReader(text))) {
            while (reader.readLine() != null) {
                count++;
            }
        }

        return count;
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 LineSeparatorDemo.java
java LineSeparatorDemo
```

**Stdout on typical LF or CRLF environments:**

```text
Matches platform separator: true
Logical line count: 3
Ends with separator: false
```

**Why does it produce this output?**

1. `writer.newLine()` is called **twice**, between the lines, so the string has three logical lines.
2. `String.join(System.lineSeparator(), ...)` also inserts the exact same two separators; the equality comparison returns `true`.
3. `BufferedReader.readLine()` returns `"Dòng một"`, `"Dòng hai"`, `"Dòng ba"` in sequence, then `null` at EOF. It strips the line-ending characters from each result.
4. The last line `"Dòng ba"` is not followed by `newLine()`, so `endsWith(separator)` is `false`.

The example uses `StringWriter` to observe the content without creating a real file. `StringWriter` stores characters in memory; closing `BufferedWriter` calls `close()` on the underlying writer, though with `StringWriter` you can still retrieve the written content via `toString()`.

### Clearly Seeing LF and CRLF When Debugging

Do not rely on your eyes to guess separators because consoles or editors can display both LF and CRLF nearly identically. Given a text string:

```java
String visible = actual
        .replace("\r", "\\r")
        .replace("\n", "\\n");
System.out.println(visible);
```

Place that snippet in `main` of the example after creating `actual`. With LF, you will see:

```text
Dòng một\nDòng hai\nDòng ba
```

With CRLF, you will see:

```text
Dòng một\r\nDòng hai\r\nDòng ba
```

These are **platform-dependent illustrative outputs**, not two lines appearing simultaneously on stdout.

## 6. Writing UTF-8 Files Line by Line

`BufferedWriter` handles **characters and buffering**; a charset such as UTF-8 is determined when connecting to the file's byte stream. With Java NIO, the clear approach is:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public static void writeReport(Path path) throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
            path, StandardCharsets.UTF_8)) {
        writer.write("Tiêu đề");
        writer.newLine();
        writer.write("Nội dung tiếng Việt");
        writer.newLine();
    }
}
```

This is an **illustrative method** and must be placed inside a class. `Files.newBufferedWriter(path, StandardCharsets.UTF_8)` creates a buffered writer that encodes characters in UTF-8, while `writer.newLine()` picks the line-ending characters according to the runtime environment. The two decisions are **independent**:

- **Charset UTF-8** determines how Unicode characters are converted into bytes.
- **Line separator** determines whether LF, CRLF, or the configured line-ending string is inserted.

With default options, `Files.newBufferedWriter` creates the file if it does not exist or truncates its content if the file already exists. Define an overwrite policy if older reports must be retained.

In this example, because `newLine()` is called after `"Nội dung tiếng Việt"`, the file **has a trailing line terminator**. That may be the desired convention for line-oriented files; if the output format requires no newline after the final content, omit that call.

## 7. Buffering, `flush()`, and `close()`

`BufferedWriter` holds data in a buffer; there is no guarantee that each `write` or `newLine` call immediately produces an observable change in the destination file.

- `writer.write(...)` writes characters to the writer; the content may remain in the buffer.
- `writer.newLine()` writes the newline sequence to the writer and **does not automatically flush**.
- `writer.flush()` pushes buffered data down through underlying writer layers. It is **not synonymous** with guaranteeing data has been durably persisted to the storage device.
- `writer.close()` closes the writer, flushing buffered data during closing, and releases resources. `try-with-resources` ensures `close()` is called even when an exception occurs.

Example when data needs to be observed before closing the writer:

```java
writer.write("Trạng thái: đang chạy");
writer.newLine();
writer.flush();  // Needed when the receiver must see the data immediately.
```

Do not call `flush()` after **every** line unnecessarily, as doing so can diminish the benefit of buffering. For ordinary files, closing properly with `try-with-resources` at the end of the task is usually sufficient.

## 8. When Must You Write `"\n"` or `"\r\n"` Explicitly?

This distinction is especially important when a Java program emits data to be read by another system. Not every format uses the running machine's line separator.

**When a format or protocol requires a specific line terminator**, write that exact form per the standard:

```java
writer.write("line 1");
writer.write("\n");    // Fixed LF, regardless of operating system.
writer.write("line 2");
```

Or when a protocol requires CRLF:

```java
writer.write("Header: value");
writer.write("\r\n");  // Fixed CRLF.
```

The snippets above are illustrative and require an already open `writer`. For example, HTTP/1.1 protocol headers have their own CRLF rule; in real applications, let the HTTP library manage message formatting rather than assembling protocol strings manually.

Typical scenarios:

| Need | How to Choose the Line Ending |
| --- | --- |
| Notes or reports on a user's machine following platform convention | `writer.newLine()` or `System.lineSeparator()` |
| LF-standardized files shared across multiple environments | Explicit `"\n"` or normalized output |
| Protocol requiring CRLF | Explicit `"\r\n"` or a dedicated protocol API |
| Output file that must preserve the source file's line endings | Must read and retain the exact existing separators, not read with `readLine()` and pick anew |
| Building a multiline `String` for a platform-native application | `String.join(System.lineSeparator(), lines)` |
| Binary data | Use byte streams; `newLine()` has no meaning |

**Do not use `System.lineSeparator()` as a way to guess an external file's line ending.** A file created on Linux can still contain CRLF, and a file created on Windows can still contain LF. The data source, format standard, or actual file content determines which characters are present in that file.

## 9. Reading Back with `BufferedReader.readLine()` and Its Limitations

`BufferedReader.readLine()` recognizes lines terminated by LF, CR, or CRLF. It returns strings **without line-ending characters**; `null` signifies EOF when no lines remain.

```java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each line's content, without LF or CRLF.
        System.out.println(line);
    }
}
```

This illustrative snippet assumes `path` and imports for `BufferedReader`, `Files`, and `StandardCharsets` exist. One key point to remember is that **reading line by line loses the original separator information**:

```text
Source 1: "A\nB"
Source 2: "A\r\nB"
readLine() on both: "A", "B"
```

Therefore, if you read with `readLine()` and write back with `newLine()`, you may **normalize or alter line endings**, even though the displayed text looks unchanged. For tasks that must preserve exact bytes, mixed line-ending characters, or file signatures/checksums, read bytes/characters and preserve the exact original data rather than treating `readLine()` as a verbatim copy method.

Additionally, a final line **without** a line terminator is still returned by `readLine()` before EOF, as long as it has content.

## 10. Comparison with `PrintWriter.println()`, `System.out.println()`, and `%n`

Several other Java APIs also provide convenient line-ending operations with distinct behaviors:

| API | Purpose | Notes |
| --- | --- | --- |
| `BufferedWriter.newLine()` | Writes the line separator to `BufferedWriter` | Throws `IOException`; does not auto-flush |
| `System.lineSeparator()` | Returns the separator `String` | Performs no I/O |
| `PrintWriter.println(...)` | Writes a value and ends the line | `PrintWriter` typically records an error flag instead of throwing `IOException` directly; check `checkError()` when needed |
| `System.out.println(...)` | Prints a value/line to standard output | Usually follows the environment's convention |
| `String.format("A%nB")` | Formats a string with a platform-specific line break | `%n` is a format specifier, different from a fixed `\n` |

`PrintWriter` has auto-flush constructors/options; whether `println` flushes automatically depends on whether auto-flush is enabled. **Do not assume `BufferedWriter.newLine()` has auto-flush like some `PrintWriter` instances.**

If you need explicit `IOException` handling when writing files and want control over when to flush, `BufferedWriter` is a straightforward choice.

## 11. Common Mistakes

| Mistake | Consequence | Appropriate Practice |
| --- | --- | --- |
| Thinking `newLine()` always writes `"\n"` | Output can differ between Windows and Linux | Use `newLine()` when platform convention is desired; use literals when a standard requires one |
| Calling `System.lineSeparator()` alone and expecting the file to advance a line | No characters are written | `writer.write(System.lineSeparator())` or `writer.newLine()` |
| Using `newLine()` to emit a format requiring fixed CRLF | File may be malformed on an LF environment | Write exact `"\r\n"` or use a protocol library |
| Calling `newLine()` and assuming data has been flushed | Another reader may not see the line yet | `flush()` at synchronization points; close properly |
| Reading with `readLine()` and rewriting while expecting byte-for-byte preservation | Loses original CR/LF/CRLF information | Read/write preserving exact characters or bytes |
| Assuming UTF-8 determines LF/CRLF | Confuses charset with line ending | Choose charset and separator independently |
| Writing `newLine()` after every line without checking the standard | May add an unwanted trailing newline | Define the trailing line-terminator policy |
| Using `"\n"` and claiming the file will always display properly in all apps | Some legacy systems or specialized tools expect a different convention | Follow the format or the receiving application's requirements |
| Adding unnecessary `flush()` after every statement | Reduces buffering efficiency and increases I/O | Flush intentionally at synchronization points |

## 12. Self-Check Exercises

1. **On typical Windows**, after `writer.write("A"); writer.newLine(); writer.write("B");`, what form is the character sequence equivalent to? **`"A\r\nB"`**, if the environment uses CRLF.
2. **On typical Linux**, what is the equivalent string? **`"A\nB"`**, if the environment uses LF.
3. **Does calling `System.lineSeparator()` alone write anything to a file?** **No**; the method returns a `String`.
4. **Does `newLine()` automatically call `flush()`?** **No**; call `flush()` when buffered data must be pushed out, or close the writer properly.
5. **A standard requires fixed LF on all OSes: what should you use?** **Write `"\n"` explicitly** or use an API outputting to that standard.
6. **Does reading a CRLF file with `readLine()` and writing it back with `newLine()` on Linux preserve bytes?** **Not guaranteed**; line-ending characters can turn into LF.
7. **Does UTF-8 make `newLine()` always use LF?** **No**; byte encoding and line endings are two separate decisions.
8. **If you want a text file to always have a trailing newline, where do you place `newLine()`?** **After the last line as well**, following the file format specification.

**Rule of thumb:** use `BufferedWriter.newLine()` to **write a platform-native line break**, use `System.lineSeparator()` to **obtain the platform-native line-break string**, and use **explicit `"\n"` or `"\r\n"`** when the output specification mandates an exact terminator.

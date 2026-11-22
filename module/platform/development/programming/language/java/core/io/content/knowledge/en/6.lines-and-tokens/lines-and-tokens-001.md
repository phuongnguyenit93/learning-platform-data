# BufferedReader.readLine(): Reading Line by Line and Stripping Line Terminators

`BufferedReader.readLine()` in Java reads text line by line without having to manually scan for newline characters. Each call returns **the content of one line, with the line terminator stripped**, or `null` if the end of data is reached and there are no characters left to form a new line.

This is very convenient when parsing lines in configuration files, logs, or text data. However, there is an important consequence: **you cannot tell whether the line just read ended with `\n`, `\r`, `\r\n`, or simply ended at EOF solely from the `String` returned by `readLine()`**. When you need to preserve line terminators, you must choose another reading approach.

## 1. What Is BufferedReader?

`java.io.BufferedReader` is a `Reader` with a character buffer. It typically wraps another `Reader` to read characters more efficiently, such as `FileReader` or `InputStreamReader`. In addition to `read()` for reading characters, the `readLine()` method groups characters into a line.

Example of a reading loop:

~~~java
String line;
while ((line = reader.readLine()) != null) {
    // Process the exact line content, without line terminator characters.
    System.out.println(line);
}
~~~

This is an **illustrative snippet**: the `reader` variable must be an open `BufferedReader`, and the program must handle `IOException`. The assignment inside the condition is intentional: each iteration calls `readLine()` **once** and compares the return value with `null`.

The data flow has two layers to distinguish:

~~~text
File or byte stream --[decode with Charset]--> Reader containing characters
                                                |
                                                v
                                          BufferedReader
                                                |
                                                v
                                     readLine(): String or null
~~~

`BufferedReader` processes **already decoded characters**; it does not directly determine the file's encoding. If the source is bytes, choose the correct charset when constructing `InputStreamReader`, or use `Files.newBufferedReader(path, StandardCharsets.UTF_8)`. This is important for Vietnamese text and data exchanged across multiple machines.

## 2. Which Line Terminators Does readLine() Recognize?

According to the contract of `BufferedReader.readLine()`, a line is considered terminated at:

| Notation in a Java String | Name | Line terminator characters |
|---|---|---|
| `"\n"` | LF (line feed) | `U+000A` |
| `"\r"` | CR (carriage return) | `U+000D` |
| `"\r\n"` | CRLF | Two consecutive characters `U+000D U+000A` |

All three cases are recognized while reading. With CRLF, `\r\n` counts as **one** line terminator and does not produce an extra empty line just because it has two characters.

Example:

~~~text
Input data in escaped form: "Java\r\nSpring\nSQL\rEOF"
Results of sequential readLine() calls:
1. "Java"
2. "Spring"
3. "SQL"
4. "EOF"
5. null
~~~

The line `"EOF"` is returned even though there is no trailing newline after it: **EOF can also terminate the last line with content**. Only the next call, when no characters remain, returns `null`.

Do not confuse these three line terminators with all Unicode characters that render like a line break. For example, `U+2028` (LINE SEPARATOR) is **not** a line break defined in the `readLine()` contract. `readLine()` also does not require the line separator to match the current OS's `System.lineSeparator()`. An application running on Windows still reads LF-delimited data properly and vice versa.

## 3. What Exactly Is Stripped?

Suppose the source contains:

~~~text
"A\r\nB\nC\rD"
~~~

`BufferedReader.readLine()` returns in order:

~~~text
"A"
"B"
"C"
"D"
null
~~~

Each returned `String` **does not contain** the `\r` or `\n` used to terminate the line. The method does not insert a space or replacement delimiter.

No metadata accompanies the return value to indicate whether the line used LF, CR, CRLF, or ended at EOF. Therefore, different sources can produce **the same list of lines**. For instance, both `"A\nB"` and `"A\r\nB"` produce the list `["A", "B"]`.

Note that `readLine()` strips **the line terminator**, rather than calling `trim()` or `strip()`:

- Leading and trailing whitespace (spaces, tabs) remains in the `String`.
- A line containing three spaces returns a string of length 3, **not** an empty string.
- A truly blank line returns `""`, meaning a `String` of length 0, **not** `null`.
- The `\r`/`\n` characters serving as the line terminator are no longer in the result.

If an application needs to distinguish whitespace-only lines from completely empty lines, check `line.isEmpty()` versus `line.isBlank()` directly. The two conditions carry different meanings.

## 4. Complete Example: CRLF, CR, LF, and Empty Lines

Create a file **`ReadLineDemo.java`** with the following code (Java 17+):

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ReadLineDemo {
    public static void main(String[] args) throws IOException {
        String content = "An\r\n\r\nBinh\nCuong\rDung\n";

        try (BufferedReader reader = new BufferedReader(
                new StringReader(content))) {
            String line;
            int index = 0;
            while ((line = reader.readLine()) != null) {
                index++;
                System.out.printf("%d: <%s> (len=%d)%n",
                        index, line, line.length());
            }
            System.out.println("count=" + index);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ReadLineDemo.java
java ReadLineDemo
~~~

Exact stdout:

~~~text
1: <An> (len=2)
2: <> (len=0)
3: <Binh> (len=4)
4: <Cuong> (len=5)
5: <Dung> (len=4)
count=5
~~~

Order explanation:

1. `"An\r\n"` produces line `"An"`; both CR and LF of the CRLF pair are stripped.
2. `"\r\n"` immediately after produces an **empty** line; that is the second line `""`, of length 0.
3. `"Binh\n"` produces `"Binh"`, `"Cuong\r"` produces `"Cuong"`.
4. `"Dung\n"` produces `"Dung"`. Even though the data has a trailing LF, `readLine()` **does not generate an extra empty line** just because the string ends with a single line terminator.
5. The final call hits EOF and returns `null`; the loop terminates.

The example uses `StringReader` so that the result does not depend on the operating system or the encoding of a real file. The terminator-stripping rules belong to `BufferedReader` and still apply when the source is a file.

## 5. Distinguishing Empty Lines, End of File, and Trailing Newlines

This is the part that most often causes bugs. Consider the following data patterns:

| Source content (escaped notation) | Values returned by `readLine()` before EOF | Line count |
|---|---|---:|
| `""` | No `String`; returns `null` immediately | 0 |
| `"\n"` | `""` then `null` | 1 |
| `"\r\n"` | `""` then `null` | 1 |
| `"A"` | `"A"` then `null` | 1 |
| `"A\n"` | `"A"` then `null` | 1 |
| `"A\r\n"` | `"A"` then `null` | 1 |
| `"A\n\n"` | `"A"`, `""` then `null` | 2 |
| `"\nA"` | `""`, `"A"` then `null` | 2 |
| `"A\n\nB"` | `"A"`, `""`, `"B"` then `null` | 3 |

Two distinctions to remember:

**Empty line**: a line terminator appears when no content characters have been seen since the previous line terminator. Thus reading `"\n"` yields an empty line `""`. The loop must continue when the value is `""`.

**EOF**: when `readLine()` has no characters left at all to form a new line, it returns `null`. The last line with content is returned even without a line terminator. When a line terminator is already the final character, EOF afterward **does not produce a new line**.

Consequently, `"A"` and `"A\n"` return the exact same sequence `"A"` then `null`. If you need to know whether the original file had a trailing newline, `readLine()` **does not provide enough information**.

### Verifying with a Java Program

Create **`ReadLineEdgeCases.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;

public class ReadLineEdgeCases {
    public static void main(String[] args) throws IOException {
        inspect("empty", "");
        inspect("LF", "\n");
        inspect("A", "A");
        inspect("A+LF", "A\n");
        inspect("A+LF+LF", "A\n\n");
        inspect("A+CRLF", "A\r\n");
    }

    private static void inspect(String label, String source)
            throws IOException {
        List<String> lines = new ArrayList<>();

        try (BufferedReader reader = new BufferedReader(
                new StringReader(source))) {
            String line;
            while ((line = reader.readLine()) != null) {
                lines.add(line);
            }
        }

        String first = lines.isEmpty()
                ? "<none>" : "\"" + lines.get(0) + "\"";
        System.out.printf("%s -> count=%d, first=%s%n",
                label, lines.size(), first);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReadLineEdgeCases.java
java ReadLineEdgeCases
~~~

Stdout:

~~~text
empty -> count=0, first=<none>
LF -> count=1, first=""
A -> count=1, first="A"
A+LF -> count=1, first="A"
A+LF+LF -> count=2, first="A"
A+CRLF -> count=1, first="A"
~~~

The program shows the difference between **`null` at EOF**, **`""` when there is an empty line**, and the fact that **a single trailing newline does not automatically add an empty line**.

## 6. Reading Real Files: Always Control the Charset

When the source is a file, you can use `Files.newBufferedReader`. By default `Files.newBufferedReader(path)` uses UTF-8; to make the data contract explicit, pass `StandardCharsets.UTF_8` explicitly, especially when processing files containing Vietnamese text.

Standalone example **`ReadTextFileLines.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadTextFileLines {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("read-lines-", ".txt");

        try {
            Files.writeString(path, "red\r\n\r\nblue\n",
                    StandardCharsets.UTF_8);

            try (BufferedReader reader = Files.newBufferedReader(
                    path, StandardCharsets.UTF_8)) {
                String line;
                int lineNumber = 0;
                while ((line = reader.readLine()) != null) {
                    System.out.printf("%d: [%s]%n",
                            ++lineNumber, line);
                }
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReadTextFileLines.java
java ReadTextFileLines
~~~

Stdout:

~~~text
1: [red]
2: []
3: [blue]
~~~

The temporary file is only for demonstration; the snippet uses `finally` to delete it after closing `BufferedReader`. With a user-supplied path, handle access permissions and `IOException`; do not use temp-file deletion code to delete a real file.

You can open with a constructor or factory passing another charset:

~~~java
// Illustrative snippet: path is an already defined Path.
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Use line.
    }
}
~~~

This is convenient when the source is a UTF-8 file. If the file is encoded in a different charset, you must know and pass that exact charset; `BufferedReader` **does not auto-detect encoding**. Wrong-encoding bytes can cause decoding errors or replacement characters depending on the reader/decoder and API rules.

### BufferedReader and the BOM

If a UTF-8 file has a BOM prefix (`EF BB BF`), UTF-8 character reading APIs typically leave the `U+FEFF` character at the start of the content instead of stripping it automatically. `readLine()` **only strips line terminators** by contract, so do not expect it to strip BOMs, whitespace, or other metadata. If your system supports files with a BOM, decide how to handle the BOM at the beginning of the text according to your data format.

## 7. When Writing Back: Line Terminators May Change

Because the original separator characters are lost, code that reads with `readLine()` and writes back with a chosen separator will **normalize line terminators**, rather than reproducing the original bytes.

Example:

~~~java
// Illustrative snippet: reader and writer are already open and must be closed properly.
String line;
while ((line = reader.readLine()) != null) {
    writer.write(line);
    writer.newLine();
}
~~~

`BufferedWriter.newLine()` writes **the current platform's line separator** according to `System.lineSeparator()`. If the original file used CRLF, a program running on an LF environment will turn CRLF into LF. Moreover, this example always writes a line terminator after every line, even if the last line of the original source had no line terminator.

With `writer.write('\n')`, the program fixes LF as the separator, which still alters the input if the original used CRLF/CR. With `System.lineSeparator()` or `PrintWriter.println()`, the effect is likewise generating a new separator, not restoring the stripped separator.

### Example Demonstrating Normalization

Create file **`NormalizeLinesDemo.java`**:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class NormalizeLinesDemo {
    public static void main(String[] args) throws IOException {
        String source = "one\r\ntwo\rthree\n";
        StringBuilder normalized = new StringBuilder();

        try (BufferedReader reader = new BufferedReader(
                new StringReader(source))) {
            boolean first = true;
            String line;
            while ((line = reader.readLine()) != null) {
                if (!first) {
                    normalized.append('\n');
                }
                normalized.append(line);
                first = false;
            }
        }

        System.out.println("source chars=" + source.length());
        System.out.println("normalized chars=" + normalized.length());
        System.out.println("normalized="
                + normalized.toString().replace("\n", "|"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NormalizeLinesDemo.java
java NormalizeLinesDemo
~~~

Stdout:

~~~text
source chars=15
normalized chars=13
normalized=one|two|three
~~~

The source content has CRLF, CR, and a trailing LF; the result simply joins the lines with LF and has no trailing newline. `boolean first` is used instead of `normalized.length() > 0` because **the first line may be empty**: an empty line must still count as a line that was read. Even when the code inserts LF before every line after the first, reconstructing the exact source bytes is impossible from plain `readLine()` strings alone.

If your goal is simply **parsing line-by-line content**, stripping line breaks is usually desirable. If your goal is **copying a file verbatim**, do not read lines and write them back; copy bytes with `Files.copy` or `InputStream`/`OutputStream`. If you need to edit while preserving CR, LF, CRLF, and trailing newline state accurately, read character-by-character/byte-by-byte and store the separator alongside each line (or keep the entire content in memory when size permits).

## 8. readLine(), lines(), and Other APIs

| Reading approach | Result | Separator preservation |
|---|---|---|
| `BufferedReader.readLine()` | One `String` at a time; `null` at EOF | Strips CR, LF, CRLF |
| `BufferedReader.lines()` | `Stream<String>` of lines | Still strips line terminators |
| `Files.lines(path, charset)` | `Stream<String>` from a file | Strips line terminators |
| `Files.readAllLines(path, charset)` | `List<String>` of all lines | Strips line terminators |
| `Files.readString(path, charset)` | Entire text as a `String` | Preserves `\r` and `\n` characters present in the content |
| Reading via `Reader.read()` or `read(char[])` | Raw characters decoded by the reader | Allows observing and retaining CR/LF |

`BufferedReader.lines()` can be convenient for Stream-style processing, but the results are still lines **without terminators**. When reading `lines()`, if an I/O error occurs while consuming the stream, the exception is surfaced as `UncheckedIOException`. Do not mix direct read calls on `BufferedReader` with consuming an active `lines()` stream.

Example when iterating lines using a Stream:

~~~java
// Illustrative snippet: reader must be open within a try-with-resources scope.
reader.lines()
      .filter(line -> !line.isBlank())
      .forEach(System.out::println);
~~~

This approach actively skips empty and whitespace-only lines because of `!line.isBlank()`; that is an application decision, **not the default behavior of `readLine()`**.

Resource management note: for a stream obtained from `reader.lines()`, closing the stream does not replace managing the closing of `reader` per `BufferedReader`'s contract; use `try-with-resources` for `BufferedReader`. For `Files.lines(...)`, the returned stream holds the file resource and the stream itself must be closed.

## 9. Performance, Line Length, and Cases Requiring Care

- **May block while waiting**: on an open character source such as a socket, `readLine()` may wait until a line terminator, EOF, or an error is encountered; do not assume every call yields a line immediately.
- **Very long lines**: `BufferedReader` has a buffer, yet `readLine()` must still construct a `String` for the entire line. Untrusted data may contain abnormally long lines causing high memory consumption. If you need to bound each record's size, implement bounded character-reading logic before assembling a full line.
- **Not a general CSV parser**: CSV can contain newlines inside quoted fields. `readLine()` only splits physical lines, not logical CSV records.
- **Does not strip whitespace**: `readLine()` does not call `trim()`/`strip()`, strip comments, or split tokens; the application must explicitly choose subsequent processing steps.
- **Do not use `reader.ready()` as an end-of-file condition**: `ready()` indicates whether the next read operation can proceed without blocking, not EOF. The proper loop condition remains checking `readLine() != null`.
- **I/O exceptions**: the method can throw `IOException`; use `try-with-resources`, report read errors properly, and avoid assuming `null` represents an error.

For small files when preserving newline characters is the goal, `Files.readString(path, UTF_8)` is simpler to reason about. For large files when line-by-line processing is the goal, `BufferedReader.readLine()` avoids loading the entire file, provided individual lines remain reasonably sized.

## 10. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | Correct approach |
|---|---|---|
| `while ((line = reader.readLine()) != "")` | Compares `String` references and does not check EOF; can encounter `null` | Use `while ((line = reader.readLine()) != null)` |
| `if (line.isEmpty()) break;` | An empty line `""` is valid data, not EOF | Stop when `line == null` |
| Assuming a file ending in `\n` has an extra empty line | A single trailing terminator does not create a new line at EOF | See the `"A\n"` and `"A\n\n"` examples |
| Joining `readLine()` with `System.lineSeparator()` to recreate the file identically | Original separators were stripped; LF/CRLF/CR or trailing newline state is lost | Read/preserve raw separators if preservation is required |
| Assuming `readLine()` automatically understands UTF-8 | `BufferedReader` reads characters decoded by the underlying Reader | Choose the charset in `InputStreamReader` or `Files.newBufferedReader` |
| Using `trim()` when whitespace must be kept | `trim()` removes meaningful content, unlike stripping terminators | Keep `line` as-is; only strip if business logic requires it |
| Using `reader.ready()` to detect EOF | `ready()` is not an end-of-data check | Read until it returns `null` |
| Using `readLine()` for documents that must preserve bytes or newlines | Line reading discards separator information | Read raw chars/bytes or `Files.readString` for files fitting in memory |

## 11. Key Takeaways

1. `BufferedReader.readLine()` recognizes **LF (`\n`), CR (`\r`), and CRLF (`\r\n`)** and **strips the line terminator** from the returned `String`.
2. **`null` means EOF** when no lines remain; **`""` is a valid empty line**. Always stop on `null`, never on `""`.
3. A final line **without a terminator** is still returned; a single trailing newline at the end of a file **does not create an extra empty line**.
4. From `readLine()` you **cannot accurately recover** the separator type or know whether the source had a trailing newline. Reading and writing back often alters line endings.
5. Choose the **correct charset**, close `BufferedReader` with `try-with-resources`, and handle `IOException`.
6. Use line-based reading for content processing; use character/byte-preserving reading if formatting preservation is required.

### Official References

- [Java SE — BufferedReader.readLine()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#readLine())
- [Java SE — BufferedReader.lines()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html#lines())
- [Java SE — Files.newBufferedReader()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset))

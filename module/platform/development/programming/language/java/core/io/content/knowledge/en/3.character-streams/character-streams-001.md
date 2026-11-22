# Reader and Writer Handle `char` Units in Java

In Java, `java.io.Reader` and `java.io.Writer` are the two foundational abstract classes for **character I/O**. `Reader` provides operations to **read** `char` units from a source, while `Writer` provides operations to **write** `char` units to a destination. This model fits when an application works with **text**: file contents, character strings, logs, text-based exchange data, etc.

It is important to understand from the outset: a Java `char` is **a 16-bit UTF-16 code unit**, not always a "user-visible character". Therefore, the API for reading/writing `char` differs from the API for reading/writing **bytes**, and also differs from iterating over **Unicode code points**.

## 1. The Reader/Writer Model and Data Boundaries

`Reader` and `Writer` belong to the `java.io` package:

- **`Reader`**: receives character-form data from a source; for example, `StringReader` reads an existing string, `InputStreamReader` decodes bytes from an `InputStream`, and `BufferedReader` wraps a `Reader` to improve efficiency and support reading lines.
- **`Writer`**: sends character-form data to a destination; for example, `StringWriter` accumulates characters in memory, `OutputStreamWriter` encodes characters into bytes to write to an `OutputStream`, and `BufferedWriter` adds buffering and `newLine()`.
- A `Reader` or `Writer` is a **read/write operation channel**, not a list or collection already holding the entire text; reading, writing, buffering, and closing behavior depends on the implementation class and the source/destination.
- `Reader` does not provide `write()`, and `Writer` does not provide `read()`. To read from a source and write to a destination, use both objects together.

Conversion flow diagram when data is stored as bytes:

```text
Byte source (file/socket/byte[])
         |
         v
InputStream --[InputStreamReader + Charset: decode]--> char/Reader
                                                          |
                                                          v
                                            Text processing program
                                                          |
                                                          v
OutputStream <--[OutputStreamWriter + Charset: encode]-- char/Writer
         |
         v
Byte destination (file/socket/byte[])
```

`InputStreamReader` and `OutputStreamWriter` are the **bridge** between byte streams and character streams; whereas `StringReader`/`StringWriter` work with characters already in memory, requiring no file decoding.

## 2. What Unit Is `char` Exactly?

The primitive `char` type in Java is 16-bit and stores **one UTF-16 code unit** (values from `0x0000` to `0xFFFF`). A Unicode code point is the identifier of a Unicode character in the range `U+0000` to `U+10FFFF`, excluding the surrogate range when considering valid code points.

- Most common characters in the **Basic Multilingual Plane (BMP)** use **one** `char`: `'A'`, `'đ'`, `'中'`.
- Characters outside the BMP, such as the emoji `😊` (U+1F60A), use **two** consecutive `char`s in UTF-16, called a **surrogate pair**: `\uD83D` and `\uDE0A`.
- A displayed character can even consist of **multiple code points**, such as a letter with combining diacritical marks or an emoji with variation selectors. Therefore, **counting `char`s**, **counting code points**, and **counting grapheme clusters** are three different counts.
- `String.length()` returns the number of UTF-16 code units; `String.codePointCount(0, s.length())` counts code points within that range; neither guarantees equivalence to the number of user-perceived characters.

This directly affects I/O: `Reader.read()` reads **one UTF-16 code unit** per successful return, rather than guaranteeing a complete Unicode code point. `Writer.write(int)` writes the **low 16 bits** of the argument as one `char` unit; it is not a general "write one Unicode code point" API. If you need to convert a non-BMP code point into text, convert it using `Character.toChars(codePoint)` or process a string containing the full surrogate pair.

### Example 1 — Observing individual `char` units with `StringReader`

Create the file `ReaderWriterUnitsDemo.java`:

```java
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;

public class ReaderWriterUnitsDemo {
    public static void main(String[] args) throws Exception {
        String text = "A😊B";
        try (Reader reader = new StringReader(text);
             StringWriter writer = new StringWriter()) {
            int codeUnit;
            while ((codeUnit = reader.read()) != -1) {
                System.out.printf("unit=U+%04X%n", codeUnit);
                writer.write(codeUnit);
            }
            String copy = writer.toString();
            System.out.println("char units=" + copy.length());
            System.out.println("code points=" + copy.codePointCount(0, copy.length()));
            System.out.println("same=" + text.equals(copy));
        }
    }
}
```

Compile and run with Java 17 or later:

```bash
javac -encoding UTF-8 --release 17 ReaderWriterUnitsDemo.java
java ReaderWriterUnitsDemo
```

Exact output:

```text
unit=U+0041
unit=U+D83D
unit=U+DE0A
unit=U+0042
char units=4
code points=3
same=true
```

`Reader.read()` returns `int` so there is enough room to represent every `char` value from 0 to 65535 **and** the special value `-1` for end of stream (EOF). You should not immediately cast the result of `read()` to `char` before checking for EOF, because the `-1` signal will be lost.

The example has four code units: `A`, high surrogate, low surrogate, `B`; yet only three code points. `StringWriter` writes back each unit faithfully, so the original string is restored. If you convert each code unit independently to bytes or to strings and process them arbitrarily, a surrogate pair can be split and corrupt the text.

## 3. Core Methods and Return Value Meanings

| API | Meaning | Key Notes |
|---|---|---|
| `int Reader.read()` | Reads one UTF-16 code unit | Returns `0..65535` or `-1` at EOF; may throw `IOException` |
| `int Reader.read(char[] buffer)` | Reads up to `buffer.length` code units into the array | Returns **the number of elements actually read** or `-1`; do not assume the array is filled |
| `int Reader.read(char[] b, int off, int len)` | Reads up to `len` units into the array starting at `off` | Must respect `off` and the returned count; `len = 0` may return `0` |
| `long Reader.skip(long n)` | Skips `n` `char`s | Unit is code unit; result is the number actually skipped |
| `boolean Reader.ready()` | Checks whether reading can proceed immediately without blocking | **Not** an EOF check; `false` does not mean no more data remains |
| `void Writer.write(int c)` | Writes one `char` | Uses the low 16 bits of `c` |
| `void Writer.write(char[] b, int off, int len)` | Writes the exact slice of the character array | Suitable when copying chunks read from a `Reader` |
| `void Writer.write(String s)` | Writes a character string | Does not automatically append a newline |
| `void Writer.flush()` | Pushes buffered data down to the underlying destination | Does not mean the data has been durably synced to disk |
| `void close()` | Releases resources | Call with `try-with-resources` when owning the source/destination |

The operations above may throw `IOException` depending on the implementation. When reading with `read(char[])`, a single call **may retrieve fewer characters than requested**; this is not EOF. Check `n == -1` to terminate and process only `buffer[0..n)`.

A correct character-copying pattern is:

```java
char[] buffer = new char[4096];
int n;
while ((n = reader.read(buffer, 0, buffer.length)) != -1) {
    writer.write(buffer, 0, n);
}
writer.flush();
```

This is an **illustrative snippet inside a method**; both `reader` and `writer` variables must be created by the caller, and the caller must handle `IOException`. In particular, using `writer.write(buffer)` instead of `writer.write(buffer, 0, n)` can write leftover stale characters remaining in the array on the final read.

Copying intact code units with the pattern above still preserves surrogate pairs, even when the two halves of a pair land in two different reads. Conversely, chunk-by-chunk **transformation** operations (such as splitting strings, uppercasing per `char`, or encoding each chunk separately) must account for the possibility of splitting surrogates and process by code point or complete text segments.

Since Java 10, `Reader.transferTo(Writer)` can directly copy all remaining `char`s to a writer, returning the number of units transferred; this method **does not automatically close** the reader or writer.

## 4. Practical Text Reading and Writing via `BufferedReader`/`BufferedWriter`

`BufferedReader` and `BufferedWriter` wrap a character source/destination with a buffer, reducing the overhead of many small operations:

- `BufferedReader.readLine()` retrieves the contents of a line, **excluding** line-termination characters; returns `null` when no lines remain. A valid empty line returns an empty string `""`, not `null`.
- `BufferedWriter.newLine()` writes the platform-dependent line separator (such as LF or CRLF); if you want an exact format regardless of the operating system, explicitly write the line ending specified by the protocol or file format.
- Buffering does not turn I/O into a data source residing completely in RAM. It only reduces the number of reads/writes to the underlying layer, depending on buffer size and access patterns.
- `Files.newBufferedReader(path, charset)` / `Files.newBufferedWriter(path, charset)` are convenient ways to open text files with an explicit charset.

### Example 2 — Reading and writing a UTF-8 file, preserving Vietnamese and emoji

Create the file `TextFileDemo.java`:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("reader-writer-", ".txt");
        String first = "Tiếng Việt: Nguyễn";
        String second = "Emoji: 😊";
        try {
            try (BufferedWriter writer =
                     Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
                writer.write(first);
                writer.newLine();
                writer.write(second);
            }
            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String a = reader.readLine();
                String b = reader.readLine();
                String end = reader.readLine();
                System.out.println("line 1 matches=" + first.equals(a));
                System.out.println("line 2 matches=" + second.equals(b));
                System.out.println("EOF=" + (end == null));
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TextFileDemo.java
java TextFileDemo
```

```text
line 1 matches=true
line 2 matches=true
EOF=true
```

**Processing flow explanation:**

1. `Files.createTempFile` creates an actual file path. The program does not depend on an existing file.
2. `newBufferedWriter` writes code units from `String`, while the encoding layer converts them into **UTF-8 bytes**. `newLine()` writes the platform-appropriate newline.
3. The `try-with-resources` block closes the writer before opening the reader, ensuring buffered data is pushed down and the file is ready for the subsequent read.
4. `newBufferedReader` reads UTF-8 bytes and decodes them into UTF-16 code units. `readLine` returns text segments **with line terminators stripped**, so both comparisons match.
5. The third `readLine()` call returns `null`: EOF. The `finally` block deletes the temporary file after the reader has closed.

Note: `try-with-resources` also handles closing when an exception occurs. `finally` is used in the example to clean up the temporary file; a file deletion failure can still cause the program to throw `IOException`. The printed output consists of booleans, so it remains reliable even if the machine's console does not render Vietnamese or emoji properly.

## 5. Why Must Characters Pass Through a Charset When Moving to/from Bytes?

**A Java `char` is not a UTF-8 byte.** A code point can occupy a varying number of bytes in UTF-8; a Java `String` holds UTF-16 code units. Writing text to a file, socket, or `OutputStream` requires an **encoding** (`encode`) step. When reading bytes into text, **decoding** (`decode`) is required.

| Data Layer | Representation | Unit |
|---|---|---|
| Byte I/O | `InputStream`, `OutputStream`, `byte[]` | 8-bit byte |
| Character I/O | `Reader`, `Writer`, `char[]` | UTF-16 code unit |
| Unicode code point | `int`, `String.codePoints()` | Code point value (may correspond to one or two code units) |
| Visible character | Grapheme cluster, user interface | May consist of multiple code points |

Common bridges:

- **`InputStreamReader(input, StandardCharsets.UTF_8)`** decodes bytes from an input stream into `char`s.
- **`OutputStreamWriter(output, StandardCharsets.UTF_8)`** encodes `char`s and writes bytes into an output stream.
- `Files.newBufferedReader` and `Files.newBufferedWriter` combine opening a file, charset conversion, and buffering in a convenient way.

You should not rely on the **system default charset** when accurate text reading/writing across machines is required. Choose a charset according to the data format or protocol, such as `StandardCharsets.UTF_8`, and use it consistently on both sides. The wrong charset can garble text; handling of invalid byte sequences also depends on the decoder's policy (replacing malformed characters or reporting an error).

### Example 3 — byte ⇄ char with `OutputStreamWriter` and `InputStreamReader`

Create the file `EncodingBridgeDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Reader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class EncodingBridgeDemo {
    public static void main(String[] args) throws Exception {
        String text = "Chữ 😊";
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (Writer writer = new OutputStreamWriter(sink, StandardCharsets.UTF_8)) {
            writer.write(text);
        }
        byte[] bytes = sink.toByteArray();
        StringWriter result = new StringWriter();
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes), StandardCharsets.UTF_8)) {
            char[] buffer = new char[2];
            int n;
            while ((n = reader.read(buffer, 0, buffer.length)) != -1) {
                result.write(buffer, 0, n);
            }
        }
        String copy = result.toString();
        System.out.println("UTF-8 bytes=" + bytes.length);
        System.out.println("UTF-16 units=" + copy.length());
        System.out.println("same=" + text.equals(copy));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 EncodingBridgeDemo.java
java EncodingBridgeDemo
```

```text
UTF-8 bytes=10
UTF-16 units=6
same=true
```

The string `"Chữ 😊"` has six UTF-16 code units: `C`, `h`, `ữ`, space, and the two units of the emoji. However, after UTF-8 encoding, the byte sequence requires **10 bytes**. `OutputStreamWriter` accepts text and produces bytes; `InputStreamReader` reads the bytes back and reconstructs the text.

The character buffer in the example is only two elements long in order to demonstrate **chunked reading**. Even if a surrogate pair spans the boundary between two chunks, `StringWriter.write(buffer, 0, n)` copies the exact sequence of code units. Do not assume `n == 2`; a read may return fewer units than the buffer size.

`OutputStreamWriter` may hold buffered bytes/code units, so you need to **flush or close** before retrieving the complete result from the destination. The example closes the writer using `try-with-resources`; the in-memory `ByteArrayOutputStream` still allows calling `toByteArray()` afterward.

## 6. Resource Management and Buffering

`Reader` and `Writer` implement `Closeable`, so they can be used in `try-with-resources`. When opening a file, socket, or other connection, identify **which object owns the resource** and close it at the right time:

```java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each line here.
    }
}
```

This is an **illustrative pattern**; the `path` variable must be defined and `IOException` must be handled or declared by the caller. When `BufferedReader` is closed, it also closes the underlying `Reader`. Similarly, closing `BufferedWriter` closes the underlying writer; do not close the byte source before the outer wrapper finishes reading/writing.

**`flush()` vs. `close()`:**

- `flush()` pushes data currently held in the `Writer`'s buffer down to underlying layers and still allows further writing (if the destination supports it).
- `close()` completes and releases resources; for `BufferedWriter`/`OutputStreamWriter`, closing guarantees flushing buffered data according to the class's contract, though it may throw `IOException`.
- `flush()`/`close()` **do not replace** durable synchronization to physical storage (for example, `FileChannel.force`) when an application requires strict durability guarantees.

**Appropriate buffering for small operations:** calling `write` one `char` at a time is not always efficient on files or networks. Wrap the writer with `BufferedWriter` or use `Files.newBufferedWriter`; similarly, `BufferedReader` helps avoid unbuffered single reads from the source. Do not automatically assume a larger buffer is always better: scale, protocol, capacity, and latency determine the right choice.

**In-memory classes:** `StringReader` and `StringWriter` still follow the `Reader`/`Writer` model, but do not hold a file descriptor. Closing them has implementation-specific nuances; you can still use `try-with-resources` when you want to express clear ownership boundaries.

## 7. Common Mistakes and How to Fix Them

1. **Assuming `char` is always one Unicode code point.** Non-BMP emoji take two `char`s. To work by code point, use `String.codePoints()`, `Character.codePointAt(...)`, and `Character.toChars(...)` instead of processing individual `char`s independently.
2. **Casting the result of `read()` to `char` before checking `-1`.** Receive it as `int`, compare against `-1`, and only then use the read value.
3. **Assuming `read(buffer)` always fills the array.** Capture the exact number of units `n` returned by the API; when writing back, call `write(buffer, 0, n)`.
4. **Using `ready()` to decide whether the end of file is reached.** `ready() == false` is not equivalent to EOF. Read until `read()` returns `-1` or `readLine()` returns `null`.
5. **Confusing a blank line with EOF.** `readLine()` returns `""` for a valid empty line; `null` indicates the end of data.
6. **Using the wrong charset or omitting the charset.** Reading a UTF-8 file with a different charset can produce garbled characters; define the encoding explicitly right at the byte↔char boundary.
7. **Using `Reader`/`Writer` to copy binary data.** Transcoding can alter bytes; images, ZIPs, and binary content should go through `InputStream`/`OutputStream` or corresponding byte APIs.
8. **Processing each half of a surrogate separately.** A single `read()` or a single buffer chunk does not guarantee code point boundaries. If modifying Unicode content, pay attention to surrogate pairs, combining marks, and cases where multiple code points form a single visible character.
9. **Omitting `close()` or forgetting `flush()` when needed.** For I/O resources, use `try-with-resources` and let the outer wrapper manage the lifecycle of the underlying layer.
10. **Assuming `write(String)` or `readLine()` preserves line breaks.** `write(String)` does not append a newline automatically; `readLine()` strips the terminator. When preserving newline formatting matters, read/write raw characters in chunks or handle newline policy explicitly.
11. **Assuming all writers report errors the same way.** `Writer` typically throws `IOException`; `PrintWriter`, however, has print methods that do not throw `IOException` during normal printing and provides `checkError()`. Understand the contract of the actual class.
12. **Treating `Reader`/`Writer` as synonymous with `java.util.stream.Stream`.** Reader/Writer are `char`-based I/O APIs; `java.util.stream.Stream<T>` is an element-processing pipeline. `BufferedReader.lines()` can produce a `Stream<String>` to process lines, yet you still need to manage the opened reader.

## 8. When to Choose Which Class?

| Need | Common Choice | Reason |
|---|---|---|
| Read a text file, process line by line | `Files.newBufferedReader(path, UTF_8)` | Convenient `BufferedReader.readLine()`, buffered |
| Write a text file, need line breaks | `Files.newBufferedWriter(path, UTF_8)` | `write` and `newLine`, buffered |
| Convert bytes from socket/file to text | `InputStreamReader` + charset, optionally wrapped in `BufferedReader` | Decodes with the right charset |
| Convert text to bytes for socket/file | `OutputStreamWriter` + charset, optionally wrapped in `BufferedWriter` | Encodes with the right charset |
| Test or build text content in memory | `StringReader` / `StringWriter` | No OS source/destination needed |
| Copy text by `char` | `Reader.transferTo(writer)` or `read(char[])`/`write(char[],0,n)` loop | Copies the exact amount of character data |
| Copy a binary file intact | `InputStream`/`OutputStream`, `Files.copy` | Preserves bytes, no transcoding |

## 9. Check Your Understanding

**Scenario A.** A `Reader` returns `0xD83D` followed by `0xDE0A`. Does the source contain two emojis? **No**. That is one surrogate pair representing a single code point U+1F60A (😊).

**Scenario B.** `reader.read(buffer)` returns `3` while the array length is `1024`. Should you write all `1024` elements? **No**. Process/write only `buffer[0..3)`; the remainder does not belong to this read.

**Scenario C.** `BufferedReader.readLine()` returns `""`. Has EOF been reached? **Not necessarily; normally that is an empty line**. EOF is signaled by `null`.

**Scenario D.** A file containing Vietnamese text was written via `OutputStreamWriter`, but when read back the diacritics are corrupted. What should you check first? **The charset used for encoding and decoding**, followed by inspecting the input bytes and the invalid-data handling policy.

**Scenario E.** You need to save a PNG image without changing a single byte. Should you use `Writer`? **No**. Choose a byte I/O API; `Writer` is meant for text and may perform transcoding.

## Conclusion

**`Reader` and `Writer` operate on UTF-16 `char`s, not directly on bytes or Unicode code points.** `Reader.read()` returns a code unit as an `int` or `-1` at EOF; `Writer.write(...)` accepts a code unit or a sequence of code units. When crossing files, networks, or byte sources, a charset is required to **decode** or **encode**. For real-world text, `BufferedReader`/`BufferedWriter` and `try-with-resources` enable efficient reading/writing, clear resource ownership, and prevent losing buffered data.

### Java SE 17 Reference Documentation

- [`java.io.Reader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Reader.html) and [`java.io.Writer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html)
- [`InputStreamReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) and [`OutputStreamWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html)
- [`BufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html) and [`BufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [`java.lang.Character`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html), [`java.lang.String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Files.newBufferedReader`, `Files.newBufferedWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
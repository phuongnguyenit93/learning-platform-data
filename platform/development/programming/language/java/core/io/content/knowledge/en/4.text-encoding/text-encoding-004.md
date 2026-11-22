# Choosing an Explicit Charset When Reading and Writing Text in Java

A program can write a file successfully, yet when read back, characters such as **“Ã©”, “Tiáº¿ng”, or “”** appear. The cause usually lies in how the program **encodes characters into bytes when writing** and **decodes bytes into characters when reading**. Choosing an explicit charset establishes the same interpretation of data on both sides, avoiding dependence on the runtime environment.

In Java, prefer passing a specific `Charset` object, typically `StandardCharsets.UTF_8`, at the **bytes ↔ text** conversion boundary. What matters is not only “using UTF-8”, but also knowing which charset the system and file actually used.

## 1. What does a charset do?

Java represents text in objects such as `String`, `char`, `Reader`, and `Writer`. Meanwhile, files and many I/O connections store or transmit **bytes**. `java.nio.charset.Charset` describes how to map between Unicode characters and a sequence of bytes.

- **Encoding:** characters → bytes, occurring when writing text to a file or sending bytes over a network.
- **Decoding:** bytes → characters, occurring when reading bytes from a file or network into text.
- **Charset:** the rules for those two conversions; for example `UTF-8`, `UTF-16`, `ISO-8859-1`.
- **The charset of the data** must be determined from the format specification, protocol, source documentation, or reliable metadata; it cannot be reliably inferred solely from Java's `String` type.

~~~text
                    WRITING TEXT
String/char --encode UTF-8--> byte[] / file / network stream
    "é"                        C3 A9

                    READING TEXT
byte[] / file / network stream --decode UTF-8--> String/char
          C3 A9                                  "é"
~~~

For example, `é` has the Unicode code point U+00E9. When encoded with UTF-8, this character becomes **two bytes `C3 A9`** (in hexadecimal). Reading those two bytes with UTF-8 yields `é` again; reading them with ISO-8859-1 yields **`Ã©`**, because that charset assigns a different meaning to each byte.

**There is no “UTF-8 String” in the sense of a `String` keeping raw UTF-8 bytes internally.** `String` is Unicode text data; a charset is only involved when converting to or from a byte representation. Calling `text.getBytes(charset)` produces encoded bytes, and `new String(bytes, charset)` decodes bytes into a string.

## 2. Why must you choose an explicit charset?

Some older APIs use the **default charset of the runtime environment** if you do not supply an argument. For example:

~~~java
// Environment-dependent: no charset specified for reading/writing.
String text = new String(bytes);
byte[] encoded = text.getBytes();

Reader reader = new InputStreamReader(inputStream);
Writer writer = new OutputStreamWriter(outputStream);
~~~

These are **illustrative lines**, so the variables `bytes` and `inputStream`/`outputStream` must already exist; this is not a standalone program. Overloads without a charset parameter are easily mistaken for “always UTF-8”.

Important environment history:

- On **Java 17 and earlier**, Java's default charset could vary by operating system, locale settings, or JVM configuration; a program running on two machines could write different bytes if it relied on the default.
- Starting with **Java 18**, JEP 400 standardized the default charset to UTF-8 in most cases, but exceptions or compatibility settings still exist, and not every API follows the same rules. Therefore, data-exchange code should continue declaring the charset according to the **data contract**.
- Some modern APIs already **specify UTF-8 by default**, such as `Files.readString(path)` or `Files.writeString(path, text)`. Even so, passing `StandardCharsets.UTF_8` makes the intent clear to readers and makes it easy to change when a file requires a different encoding.
- You should not assume that the charset of a terminal, console, third-party-generated CSV file, or HTTP header matches the JVM's default charset.

Recommended examples:

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
byte[] encoded = text.getBytes(StandardCharsets.UTF_8);

Reader reader = new InputStreamReader(inputStream, StandardCharsets.UTF_8);
Writer writer = new OutputStreamWriter(outputStream, StandardCharsets.UTF_8);
~~~

These are also illustrative lines, using imports `java.nio.charset.StandardCharsets`, `java.io.Reader`, `java.io.Writer`, `java.io.InputStreamReader`, and `java.io.OutputStreamWriter`. In a real program, stream lifecycles must be managed according to the proper ownership contract.

**The goal of choosing an explicit charset:** data crossing the byte/text boundary must be interpreted under **a well-defined convention**, rather than changing merely because the application is run in a different environment.

## 3. Which charset should you choose?

### UTF-8 is usually a good default for new text

`StandardCharsets.UTF_8` is a widely used Unicode charset that represents characters with a variable number of bytes and is ASCII-compatible for ASCII characters. It represents Vietnamese and most multilingual text, and is widely used across modern systems and formats.

Example:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

Charset charset = StandardCharsets.UTF_8;
~~~

There is no need to construct charset names from strings when Java already provides standard constants. `StandardCharsets` guarantees the availability of charsets such as `UTF_8`, `UTF_16`, `UTF_16BE`, `UTF_16LE`, `ISO_8859_1`, and `US_ASCII`, which also prevents typos when writing names.

### But you must respect the actual charset of the data

If a specification requires UTF-16LE, data was exported in ISO-8859-1, or a legacy system uses another charset, **do not blindly apply UTF-8 to “fix” the file**. You must read it with the original charset first, and only then, if needed, explicitly **transcode** it to UTF-8 on output.

Example where the format indicates the source is ISO-8859-1:

~~~java
String decoded = new String(sourceBytes, StandardCharsets.ISO_8859_1);
byte[] utf8Bytes = decoded.getBytes(StandardCharsets.UTF_8);
~~~

This is an illustrative snippet with an existing `sourceBytes`: first **decode using the source encoding**, then **encode using the target encoding**. You cannot “change the encoding” by renaming a file or calling `new String` with an arbitrary charset.

In particular, **do not use `US_ASCII` or `ISO_8859_1` for text containing all kinds of Vietnamese characters**: these charsets cannot represent all the required characters. Some encoding APIs may replace unrepresentable characters with replacement characters, resulting in **irrecoverable data loss**.

## 4. Reading and writing text files: `Files.readString` and `Files.writeString`

For relatively small text files, the `java.nio.file.Files` API is a simple choice:

~~~java
Path path = Path.of("note.txt");
Files.writeString(path, "Xin chào", StandardCharsets.UTF_8);
String value = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is an illustrative snippet requiring imports `java.nio.file.Files`, `java.nio.file.Path`, and `java.nio.charset.StandardCharsets`; I/O exceptions must be handled or declared. The charsets on the writing side and reading side **match**.

- `Files.writeString(path, text, charset)` encodes the content using the passed charset and writes it to the file; under the default open options, the file may be created or an existing file's content overwritten.
- `Files.readString(path, charset)` reads the file content and decodes it into a `String` using the specified charset.
- Both APIs may require memory proportional to the text size. For large files or when line-by-line processing is needed, use streaming readers/writers.

### Standalone Java 17+ program

Save as **`ExplicitCharsetDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;

public class ExplicitCharsetDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("explicit-charset-", ".txt");
        String original = "Tiếng Việt: cà phê ☕";

        try {
            Files.writeString(file, original, StandardCharsets.UTF_8);

            byte[] storedBytes = Files.readAllBytes(file);
            String restored = Files.readString(file, StandardCharsets.UTF_8);

            System.out.println("Round-trip: " + original.equals(restored));
            System.out.println("Text: " + restored);
            System.out.println("Bytes equal: " + Arrays.equals(
                    storedBytes, restored.getBytes(StandardCharsets.UTF_8)));

            byte[] eAcuteUtf8 = "é".getBytes(StandardCharsets.UTF_8);
            System.out.println("Correct decode: "
                    + new String(eAcuteUtf8, StandardCharsets.UTF_8));
            System.out.println("Wrong decode: "
                    + new String(eAcuteUtf8, StandardCharsets.ISO_8859_1));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac -encoding UTF-8 ExplicitCharsetDemo.java
java ExplicitCharsetDemo
~~~

On a terminal that supports Unicode display, the expected output is:

~~~text
Round-trip: true
Text: Tiếng Việt: cà phê ☕
Bytes equal: true
Correct decode: é
Wrong decode: Ã©
~~~

Points to observe:

1. `Files.writeString` **encodes** `original` into UTF-8 bytes in the file.
2. `Files.readAllBytes` retrieves the exact raw bytes; it does not decode them.
3. `Files.readString` **decodes** the same bytes using UTF-8, recovering the original string. The line `Round-trip: true` proves that the restored text equals the original string in the example.
4. Comparing `storedBytes` with `restored.getBytes(UTF_8)` verifies that re-encoding the restored string yields the exact bytes of the file.
5. The last two lines use **the same UTF-8 bytes of `é`** and change only the charset when reading: UTF-8 → `é`, ISO-8859-1 → `Ã©`. This is *mojibake* — byte data interpreted under the wrong rules.
6. `finally` deletes the temporary file so the example does not depend on a fixed filename and does not leave a created file behind on the system when the program exits normally.

Depending on terminal configuration, **how Unicode is displayed on the console** may differ from the Unicode content inside `String`. The command `javac -encoding UTF-8` specifies **the charset for the compiler to read Java source files**, not the charset of the files the application reads or writes; these two concerns must be clearly distinguished.

## 5. Streaming text I/O with `Reader`/`Writer`

When processing large or continuous data, use an explicit-charset bridge:

- `InputStreamReader`: decodes **bytes from an `InputStream`** into characters for reading code.
- `OutputStreamWriter`: encodes **characters from code** into bytes for an `OutputStream`.
- `BufferedReader`/`BufferedWriter`: add buffering and convenient APIs for reading/writing text; they do not change the charset of the underlying conversion layer.

Diagram:

~~~text
READ:  InputStream --[InputStreamReader + UTF-8]--> Reader/String
WRITE: Writer/String --[OutputStreamWriter + UTF-8]--> OutputStream
~~~

Example showing methods in the same class (called from another application):

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileLines {
    public static void writeTwoLines(Path file) throws IOException {
        try (BufferedWriter writer =
                     Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
            writer.write("Hà Nội");
            writer.newLine();
            writer.write("Đà Nẵng");
            writer.newLine();
        }
    }

    public static void readLines(Path file) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println(line);
            }
        }
    }
}
~~~

This is a **standalone compilable utility class**, without a `main` method; a caller creates a `Path` and calls `writeTwoLines(file)` then `readLines(file)` to see the two lines of place names. `readLine()` returns the content of each line **excluding** the line terminator. `writer.newLine()` adds a line break according to the system convention; this is **distinct** from charset: a charset controls how characters are converted into bytes.

You can also create the bridge directly when the source/destination is not yet a file:

~~~java
// The input/output variables are streams already provided by the caller.
BufferedReader reader = new BufferedReader(
        new InputStreamReader(input, StandardCharsets.UTF_8));
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8));
~~~

The two lines above are **illustrative**: if wrapping them in `try-with-resources` to close the wrappers, make sure the current method **owns** the underlying stream as well. Closing `BufferedReader`/`BufferedWriter` usually closes the underlying stream too; do not accidentally close `System.in`, `System.out`, or a stream still in use by a framework or caller.

If you use `Files.newBufferedReader(file)` or `Files.newBufferedWriter(file)` without passing a charset, those specific overloads already use UTF-8 by API contract, though the version with `StandardCharsets.UTF_8` makes this lesson's convention explicit.

## 6. Distinguishing byte streams and character streams

| Task | Typical API | Where is a charset needed? |
|---|---|---|
| Copying images, ZIP, PDF, arbitrary bytes | `InputStream`, `OutputStream`, `Files.copy` | Do **not** decode/encode; keep bytes as-is |
| Writing a `String` to a text file | `Files.writeString(path, text, charset)` | At the **encoding** step |
| Reading a text file into a `String` | `Files.readString(path, charset)` | At the **decoding** step |
| Reading text line by line | `Files.newBufferedReader(path, charset)` | Reader applies the charset when reading bytes |
| Writing text line by line | `Files.newBufferedWriter(path, charset)` | Writer applies the charset when writing bytes |
| Working with network streams containing text | `InputStreamReader`, `OutputStreamWriter` | Charset matching the **data protocol** |
| Already have bytes and need a string | `new String(bytes, charset)` | At the **decoding** step |
| Already have a string and need bytes | `text.getBytes(charset)` | At the **encoding** step |

Do not read an image into a string and write it back with UTF-8: image bytes can be invalid from a text perspective and will be altered. When you only need to copy verbatim, use byte streams; when you need to interpret text content, choose a charset and use text APIs.

## 7. Legacy data and mismatched charsets: how to handle them?

Suppose a file already contains bytes representing text in charset X, while the program decodes them using Y. One of two situations commonly occurs:

- **The bytes are valid under Y but produce the wrong characters:** for example, the two UTF-8 bytes of `é` are read as ISO-8859-1 and become `Ã©`. The program may not throw an error even though the displayed content is wrong.
- **The byte sequence is invalid under Y:** a strictly checking decoder may throw an error; another decoder may replace malformed sequences with **U+FFFD REPLACEMENT CHARACTER (``)** or another replacement character depending on the API's policy.

Distinguish **an error at the decoding step** from **an error at the encoding step**:

1. Determine whether the original bytes are still intact by reading the **raw bytes** first (not through a text reader).
2. Find the true charset of the source from documentation/protocol/export settings; check BOM/metadata if the format uses them, but do not treat them as conclusive proof for every file.
3. Decode the raw bytes with the right charset, checking accented characters and non-ASCII characters.
4. If standardization is needed, **re-encode** the correct text into UTF-8 to write a new file. Preserve the original until you are certain.
5. If the bytes themselves were already replaced or overwritten earlier, re-reading with a new charset may **not recover** the lost content.

### Controlling decoding errors with `CharsetDecoder`

When you need to **detect invalid UTF-8 bytes** instead of silently replacing them, you can choose the `CodingErrorAction.REPORT` policy:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class StrictUtf8Reader {
    public static void readStrictly(Path file) throws IOException {
        var decoder = StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);

        try (InputStream bytes = Files.newInputStream(file);
             Reader reader = new InputStreamReader(bytes, decoder)) {
            char[] buffer = new char[4096];
            while (reader.read(buffer) != -1) {
                // Process the characters just read according to the actual length.
            }
        }
    }
}
~~~

This is a **compilable utility class** without a `main` method. The example mainly shows how to **configure a decoder**; in real processing, you must store the return value of `reader.read(buffer)` and use only the number of characters read. `REPORT` causes decoding errors to be reported via an I/O exception instead of accepting replacement characters. When using `new String(bytes, charset)`, do not assume the API will throw an error on every invalid byte: replacement/error behavior depends on the API and decoder.

For encoding characters that cannot be represented in the target charset, `CharsetEncoder` can also be configured with `CodingErrorAction.REPORT`. Failing fast is especially useful for data that must be preserved completely, such as importing/exporting text containing Vietnamese proper names.

## 8. Practical pitfalls to watch out for

### Source code encoding differs from runtime data encoding

- `javac -encoding UTF-8 Main.java`: specifies how the compiler **reads source code**.
- `Files.readString(path, StandardCharsets.UTF_8)`: specifies how the application **reads file content at runtime**.
- `System.out.println(text)`: the string is Unicode, but converting it to bytes and displaying it on the terminal also depends on the standard stream and terminal configuration. It **does not replace** inspecting the bytes in the file.

These three stages can use different settings. Do not use a console printing “proper accents” to conclude that a file was saved with the right bytes.

### Ensure both sides agree

For a protocol or API exchanging text, the charset should be part of the **contract**. The sender encodes in UTF-8 and the receiver decodes in UTF-8. If the protocol carries charset metadata (for example `Content-Type` of an appropriate HTTP format), handle it according to the corresponding protocol specification; do not force a charset regardless of valid metadata.

If a product lets users choose an encoding on import, expose the choice clearly and use that exact choice for reading. For files managed solely by the application, pick **one fixed charset**, document it clearly, and test it with accented strings.

### BOM, newlines, and non-text data

Some files have a **byte-order mark (BOM)** at the beginning. How a BOM is handled depends on the charset and API; do not assume every text reader strips a BOM automatically. For UTF-8, a BOM is not required. If your format allows or requires a BOM, specify clearly how to write and read it.

**Line endings** such as LF/CRLF are a **content convention** issue; a correct charset does not automatically normalize all line breaks. When comparing bytes between two systems, account for line endings and BOMs, not just visible characters.

## 9. Common mistakes and how to fix them

| Mistake | Consequence | Correct approach |
|---|---|---|
| `new String(bytes)` without knowing the default charset | The same bytes can yield different results across environments | `new String(bytes, StandardCharsets.UTF_8)` if the source is truly UTF-8 |
| `text.getBytes()` when exporting data to another service | Output bytes depend on the API/JVM default charset | `text.getBytes(StandardCharsets.UTF_8)` per the contract |
| Reading UTF-8 as ISO-8859-1 | Text looks like `Ã©` instead of `é` | Read using the true original charset |
| Writing Vietnamese with US-ASCII | Characters outside the charset may be replaced | Use UTF-8 or a target charset capable of representing them |
| Using `Reader`/`Writer` to copy images/ZIPs | Can corrupt binary bytes | Use byte streams |
| Thinking `javac -encoding UTF-8` fixes runtime file errors | Only affects how the compiler reads source code | Specify the charset on runtime operations |
| Forgetting to close a reader/writer you opened | Can lose buffered data or leak resources | Use `try-with-resources` when you own it |
| Seeing proper accents on console and assuming the file encoding is right | The terminal has its own display mechanism | Inspect the file in bytes or read it back with the right charset |
| Assuming all `Files` overloads use the JVM default charset | Some overloads explicitly specify UTF-8 | Read each API's contract; pass a charset when clarity is needed |

## 10. Self-check

**Question 1.** Application A writes the string `"Cà phê"` in UTF-8; application B reads the same file using ISO-8859-1. At which step is the problem?

> At **B's decoding step**: B interprets the bytes under a charset that does not match the convention A used when encoding. B must use UTF-8, provided the original bytes are still intact.

**Question 2.** Why does `Files.readAllBytes(path)` have no charset parameter while `Files.readString(path, charset)` does?

> `readAllBytes` only retrieves **raw bytes**, without interpreting them into characters. `readString` needs to **decode** bytes into text, so it requires a charset rule.

**Question 3.** If you want to copy a ZIP file without altering its contents, do you need to choose UTF-8?

> **No.** ZIP is binary data; copy the bytes directly. A charset is only used when reading/writing **text parts** in a format where the specification defines one.

**Question 4.** If code runs on Java 17 and Java 21, should you use `new String(bytes)` when you know the file is UTF-8?

> You should use **`new String(bytes, StandardCharsets.UTF_8)`**. This makes the file's convention explicit and avoids effects from differences in default charset, version, or JVM configuration.

**Question 5.** An original file is ISO-8859-1. To convert it to UTF-8, which step must be done first?

> **Decode the original bytes using ISO-8859-1**, then **encode the resulting Unicode string using UTF-8**. Do not interpret the raw bytes directly as UTF-8 when they were not encoded with UTF-8.

## Takeaways

When **writing text**, choose a charset to **encode characters into bytes**; when **reading text**, choose a charset to **decode bytes into characters**. In new Java code, prefer **`StandardCharsets.UTF_8`** for data you control, while always respecting the actual encoding or format/protocol specification. Specifying the charset at the right byte/text boundary is part of the data contract and is how you prevent garbled-accent bugs across environments.

**References:** [Java SE 17 — `Charset`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html), [Java SE 17 — `Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400).
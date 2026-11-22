# FileReader, FileWriter, and Choosing a Charset in Java

## 1. Why Does Reading/Writing Text Files Require Attention to Charset?

Files on disk store **bytes**, whereas Java programs usually work with **characters** (`char`, `String`). Between these two worlds there is always a conversion step:

```text
Reading a file:
File (bytes) ──decode with Charset──> Reader ──characters──> Program

Writing a file:
Program ──characters──> Writer ──encode with Charset──> File (bytes)
```

In the **character streams** family (`java.io`), `FileReader` reads characters from a file and `FileWriter` writes characters to a file. They let you use the `Reader`/`Writer` API instead of assembling bytes manually. However, **merely calling `new FileReader("data.txt")` or `new FileWriter("data.txt")` does not specify which character encoding the file uses**. Picking the wrong charset can produce corrupted diacritics like `CafÃ©` or cause data loss when writing.

Goal of this article: know what `FileReader`/`FileWriter` do, use the proper Java 17+ APIs, specify charsets explicitly, and handle practical scenarios such as overwriting, appending, line endings, encoding errors, and file resources.

### Core Concepts

| Term | Meaning |
| --- | --- |
| Character | Application-level text unit; the `Reader`/`Writer` API exchanges Java UTF-16 `char` units |
| Byte | 8-bit unit stored in a file; distinct from `char` |
| Charset | Mapping rule between characters and bytes (for example UTF-8, UTF-16, ISO-8859-1) |
| Encoding | Direction of encoding characters into bytes when writing |
| Decoding | Direction of decoding bytes into characters when reading |
| Default charset | Default charset of the Java runtime, which may vary by version/configuration |
| Mojibake | Garbled text caused by reading bytes with a charset different from the one used to write them |

A charset is a **convention of the data**; filenames such as `.txt`, `.csv`, `.json` do not by themselves determine the charset.

## 2. `FileReader`: Reading a File into Characters

`FileReader` extends `InputStreamReader` → `Reader`. It opens a file, reads bytes from the source, and **decodes** them into Java `char` units. Several ways to construct it in Java 17:

```java
Reader reader1 = new FileReader("notes.txt"); // Default JVM charset.
Reader reader2 = new FileReader("notes.txt", StandardCharsets.UTF_8);
Reader reader3 = new FileReader(Path.of("notes.txt").toFile(),
                                StandardCharsets.UTF_8);
```

This is an **illustrative snippet**, requiring imports for `java.io.FileReader`, `java.io.Reader`, `java.nio.charset.StandardCharsets`, and `java.nio.file.Path`; make sure to close the readers after use. Constructors accepting `Charset` were added in **Java 11**. Use the constructor with a charset to state the file's contract explicitly.

Key methods inherited from `Reader`:

| Method | Meaning |
| --- | --- |
| `int read()` | Reads a single `char` unit as an `int`, or `-1` at end of stream |
| `int read(char[] buffer)` | Reads some character units into an array, returning the count read or `-1` |
| `int read(char[] buffer, int off, int len)` | Reads into the slice `buffer[off .. off+len)` |
| `long skip(long n)` | Skips at most `n` character units; may skip fewer |
| `void close()` | Closes the reader and associated resources |

Notes:

- The result of `read()` must be stored in an `int` to distinguish data from **EOF = -1**.
- `read(char[])` does not guarantee filling the array on every call. Only process `buffer[0..count)` when `count > 0`.
- A `char` is **one UTF-16 code unit**, not necessarily one Unicode code point. For example, emojis outside the BMP typically consist of **two `char`s** (a surrogate pair). Therefore, the number of `char` units read does not necessarily equal the number of "user-perceived characters."
- `FileReader` reads **text**; if you need to preserve the exact bytes of an image, ZIP, or binary file, use `InputStream`.

### Reading Until EOF with a Character Array

```java
// Assumes Reader reader is already opened in try-with-resources.
char[] buffer = new char[4096];
int count;
while ((count = reader.read(buffer)) != -1) {
    // Process only elements 0 through count - 1.
}
```

This is an **in-context code pattern**, not a standalone runnable program. The termination condition is always based on the return value of `read`, not on the file size in bytes.

## 3. `FileWriter`: Writing Characters into Bytes

`FileWriter` extends `OutputStreamWriter` → `Writer`. It accepts `String`/`char`, **encodes according to a charset**, and writes bytes to a file.

```java
Writer writer1 = new FileWriter("notes.txt"); // Default charset.
Writer writer2 = new FileWriter("notes.txt", StandardCharsets.UTF_8);
Writer writer3 = new FileWriter("notes.txt", StandardCharsets.UTF_8, true);
```

This is an **illustrative snippet**, requiring imports for `java.io.FileWriter`, `java.io.Writer`, `java.nio.charset.StandardCharsets`, and stream-closing management. The boolean parameter `true` in the third constructor enables **append**: appending to the end of the file. Constructors combining `Charset` with `append` were introduced in Java 11.

Important methods:

| Method | Behavior |
| --- | --- |
| `write(int c)` | Writes one `char` unit (the low 16 bits of `int`), then encodes it to bytes per the charset |
| `write(char[] data)` | Writes the entire character array |
| `write(char[] data, int off, int len)` | Writes a slice of the character array |
| `write(String text)` | Writes a character string |
| `write(String text, int off, int len)` | Writes a slice of a string |
| `append(CharSequence csq)` | Appends characters to the stream |
| `flush()` | Pushes buffered writer data down to the underlying layer; the writer remains usable |
| `close()` | Finalizes the writer, handles any remaining buffered data, and releases resources |

By default, `new FileWriter(path, UTF_8)` **creates the file if it does not exist**, and **erases old content to write anew** if the file already exists. This matters for configuration files, logs, and user data. `new FileWriter(path, UTF_8, true)` is used for appending; it **does not automatically insert a newline character** between old and new content.

Just like byte streams, `flush()` does not guarantee that data is durably persisted on disk (`fsync`). For resources you open yourself, prefer `try-with-resources` so `close()` runs automatically when leaving the block, even if an exception occurs.

## 4. Which Charset to Choose and Why UTF-8 Is Usually a Good Default

**UTF-8** encodes common ASCII with a single byte while representing all of Unicode using variable-length byte sequences. It suits multilingual text, including Vietnamese, and interoperates well with tools, APIs, HTML, and JSON.

Some common charsets:

| Charset | Characteristics | When to Use |
| --- | --- | --- |
| `StandardCharsets.UTF_8` | Unicode, 1–4 bytes per code point | Preferred choice for new text files and modern data exchange |
| `StandardCharsets.UTF_16` | Unicode; a byte-order mark may be used to indicate byte order | When a format/file specifies UTF-16 |
| `StandardCharsets.UTF_16LE` / `UTF_16BE` | UTF-16 forms with fixed byte order | When a partner system specifically requires LE/BE |
| `StandardCharsets.ISO_8859_1` | One byte per character unit in the Latin-1 set; cannot fully represent Vietnamese | Only when the data is genuinely Latin-1 |
| `StandardCharsets.US_ASCII` | ASCII characters only | Data with an ASCII-only contract |
| Legacy charsets such as `windows-1252` | Legacy encoding with a limited character set | When compatibility with legacy files/systems is required by specification |

**Do not choose a charset merely because the text looks readable**. UTF-8 can also contain pure ASCII; seeing the line `Hello` does not prove the format is UTF-8. Verify through format documentation, export configuration, a BOM if present, or an explicit agreement between writer and reader.

### Why Not Rely on `Charset.defaultCharset()`?

There are important differences across Java versions:

- **Java 17 and earlier:** the JVM's default charset typically depends on the operating system, locale, or runtime configuration. Two machines can have different defaults.
- **Java 18 and later:** under **JEP 400**, the default across most Java SE APIs is **UTF-8**; there is a compatibility mode `-Dfile.encoding=COMPAT`. Some console/device channels still have their own encoding rules.
- `Files.newBufferedReader(path)` and `Files.newBufferedWriter(path)` are specified to use UTF-8 when no charset is passed, even on Java 17; therefore do not equate the default of these two APIs with `new FileReader(path)` without a charset argument.

If the file is controlled by your application, choose **`StandardCharsets.UTF_8` explicitly** on both the reading and writing sides. If an external format mandates a different charset, **follow that charset** instead of switching to UTF-8 unilaterally without agreement.

## 5. Runnable Example: UTF-8 Write and Read Round Trip

The following program creates `hello-utf8.txt`, writes Vietnamese text using `FileWriter` with UTF-8, reads it back using `FileReader` with the same charset, and compares the content. It uses a `read(char[])` loop to demonstrate the chunked-reading contract.

**Save as `FileTextRoundTrip.java` (UTF-8 source encoding):**

```java
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTextRoundTrip {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("hello-utf8.txt");
        String original = "Tiếng Việt: Hà Nội, Đà Nẵng và Cần Thơ.";

        try (Writer writer =
                     new FileWriter(path.toFile(), StandardCharsets.UTF_8)) {
            writer.write(original);
        }

        StringBuilder restored = new StringBuilder();
        try (Reader reader =
                     new FileReader(path.toFile(), StandardCharsets.UTF_8)) {
            char[] buffer = new char[8];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                restored.append(buffer, 0, count);
            }
        }

        System.out.println("Equal text: " + original.contentEquals(restored));
        System.out.println("File exists: " + Files.exists(path));
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 FileTextRoundTrip.java
java FileTextRoundTrip
```

**Exact stdout when reading/writing succeeds:**

```text
Equal text: true
File exists: true
```

The two `try-with-resources` blocks establish a clear boundary: the writer must be completely closed **before** the reader opens the file to read. Creating `FileReader` after `FileWriter` finishes also avoids having to guess when buffered data has reached the file.

`StringBuilder.append(char[], offset, length)` uses the exact `count`; otherwise, on the final read pass, stale characters from the buffer array would leak in. The file format is UTF-8 because **both constructors use the same `StandardCharsets.UTF_8`**. Printing ASCII booleans keeps the verification output independent of terminal fonts or console charsets.

## 6. Demonstrating Diacritic Corruption When Choosing the Wrong Charset

Suppose a file contains the word `Café` saved in UTF-8. The character `é` has the UTF-8 bytes `C3 A9`. If those same two bytes are interpreted as Latin-1, they yield the two characters `Ã` and `©`, producing the string `CafÃ©`. This is **mojibake**, not `String` corrupting Unicode on its own.

**File `CharsetMismatch.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class CharsetMismatch {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("cafe-utf8.txt");
        String expected = "Café";

        Files.writeString(path, expected, StandardCharsets.UTF_8);

        String correct = Files.readString(path, StandardCharsets.UTF_8);
        String wrong = Files.readString(path, StandardCharsets.ISO_8859_1);

        System.out.println("UTF-8 matches: " + expected.equals(correct));
        System.out.println("Latin-1 matches: " + expected.equals(wrong));
        System.out.println("File hex: "
                + HexFormat.of().formatHex(Files.readAllBytes(path)));
    }
}
```

Run:

```bash
javac -encoding UTF-8 CharsetMismatch.java
java CharsetMismatch
```

**Exact stdout:**

```text
UTF-8 matches: true
Latin-1 matches: false
File hex: 436166c3a9
```

`HexFormat` has been available since Java 17. The bytes `43 61 66` are `Caf` in ASCII; `C3 A9` is the character `é` in UTF-8. The boolean results prove that **the bytes do not change, yet the decoded string can differ**. If a file originally encoded in Latin-1 is mistakenly read as UTF-8, the decoder may encounter invalid byte sequences and handle them according to the API's error policy.

Changing the decoding charset is **not a magic repair**: if data was already decoded wrongly, edited, and overwritten back, the original information may already be lost. You need to know what encoding created the original file.

## 7. Overwriting, Appending, and Line Boundaries

Two ways of opening a writer have different semantics:

```java
// Overwrite: existing content of the file will be erased.
new FileWriter("events.txt", StandardCharsets.UTF_8);

// Append bytes produced from written characters:
new FileWriter("events.txt", StandardCharsets.UTF_8, true);
```

This is an **illustrative snippet**; in real use, open inside `try-with-resources` and close the writer. Also remember that append only moves the write position to the end of the file; it does not automatically add a space or newline character.

**File `AppendText.java`:**

```java
import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class AppendText {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("events.txt");

        // Repeated runs still start with deterministic content.
        try (FileWriter writer =
                     new FileWriter(path.toFile(), StandardCharsets.UTF_8)) {
            writer.write("first");
            writer.write(System.lineSeparator());
        }

        try (FileWriter writer =
                     new FileWriter(path.toFile(), StandardCharsets.UTF_8, true)) {
            writer.write("second");
            writer.write(System.lineSeparator());
        }

        try (BufferedReader reader =
                     new BufferedReader(
                             new FileReader(path.toFile(), StandardCharsets.UTF_8))) {
            System.out.println("Line 1: " + reader.readLine());
            System.out.println("Line 2: " + reader.readLine());
            System.out.println("EOF: " + (reader.readLine() == null));
        }
    }
}
```

Run:

```bash
javac AppendText.java
java AppendText
```

**Exact stdout:**

```text
Line 1: first
Line 2: second
EOF: true
```

`BufferedReader.readLine()` reads until a line terminator or EOF and **strips the line terminator from the returned string**. When no more data remains, it returns `null`; `null` is different from an empty line (`""`). `System.lineSeparator()` produces the platform's line separator, typically `"\n"` on Linux/macOS or `"\r\n"` on Windows. If a file format requires fixed LF (for instance a protocol or normalized file), write `"\n"` explicitly according to that convention rather than depending on the operating system.

An existing file might **lack a trailing newline**; appending `second` in that case will stick directly onto the last word of the previous line. Logging problems require even more care: multiple processes appending to the same file, file locking, synchronization, and log rotation are not guaranteed simply by `append=true`.

## 8. FileReader/FileWriter and BufferedReader/BufferedWriter

`FileReader` and `FileWriter` open files and perform charset conversion. They already have some internal buffering when converting between bytes and characters, but they do not offer all the line-oriented conveniences of the buffered wrapper classes.

```java
// Illustrative snippet; imports java.io.* and StandardCharsets.
try (BufferedReader reader = new BufferedReader(
        new FileReader("input.txt", StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process line by line, without holding the entire file in RAM.
    }
}
```

`BufferedReader` has `readLine()`; `BufferedWriter` has `newLine()`. Wrappers handle small-sized operations more efficiently depending on the workload. When using `try-with-resources`, declare and close only the outer wrapper if the wrapper owns the inner stream; closing the wrapper closes the underlying reader/writer as well.

A line-oriented writer can be constructed similarly:

```java
// Illustrative snippet; imports java.io.* and StandardCharsets.
try (BufferedWriter writer = new BufferedWriter(
        new FileWriter("output.txt", StandardCharsets.UTF_8))) {
    writer.write("Dòng thứ nhất");
    writer.newLine();
    writer.write("Dòng thứ hai");
}
```

`newLine()` uses the platform's line terminator. If a file has a specific LF/CRLF requirement, write that exact character sequence instead.

### Using the Modern Files API When Convenient

Java 17 also provides `java.nio.file.Files` methods that return `BufferedReader`/`BufferedWriter`:

```java
Path path = Path.of("notes.txt");

// UTF-8 is stated explicitly, keeping the content contract clear:
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("Xin chào!");
}

try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    System.out.println(reader.readLine());
}
```

This snippet requires importing `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.charset.StandardCharsets`, `java.io.BufferedReader`, `java.io.BufferedWriter`, and handling `IOException`. If run successfully, stdout is `Xin chào!` on a Unicode-capable terminal. Both `Files.newBufferedReader(path)` and `Files.newBufferedWriter(path)` default to UTF-8, yet passing it explicitly still makes the convention obvious to readers of the code.

For small text files, `Files.readString(path, StandardCharsets.UTF_8)` and `Files.writeString(path, text, StandardCharsets.UTF_8)` are concise. However, reading an entire file into a single string requires memory proportional to file size; use `Reader`/`BufferedReader` to stream large data sequentially. `Files.writeString` creates or truncates the file by default; to append, pass `StandardOpenOption.APPEND` along with appropriate file-creation options.

### Choosing the Right Approach

| Need | Appropriate API |
| --- | --- |
| Understand file-backed reader/writer mechanics | `new FileReader(file, charset)`, `new FileWriter(file, charset)` |
| Read a text file line by line | `Files.newBufferedReader(path, charset)` or `BufferedReader(FileReader)` |
| Write a text file line by line | `Files.newBufferedWriter(path, charset)` or `BufferedWriter(FileWriter)` |
| Small file, read/write as a whole string | `Files.readString` / `Files.writeString` |
| Simply copy a file verbatim without interpreting content | Byte APIs such as `Files.copy` / `InputStream` |
| Transcode between text formats | Reader decoding with source charset, then Writer encoding with target charset |

## 9. Charset Transcoding and Handling Legacy Files

Suppose you have verified that an old file is genuinely stored in Latin-1 and want to convert it to UTF-8. The right flow is:

```text
legacy.txt (Latin-1 bytes)
    └─ FileReader(..., ISO_8859_1)
            └─ Unicode chars in Java
                    └─ FileWriter(..., UTF_8)
                            └─ utf8.txt (UTF-8 bytes)
```

**File `ConvertLatin1ToUtf8.java`:**

```java
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;

public class ConvertLatin1ToUtf8 {
    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println(
                    "Usage: java ConvertLatin1ToUtf8 <latin1-source> <utf8-target>");
            return;
        }

        Path source = Path.of(args[0]);
        Path target = Path.of(args[1]);

        if (source.toAbsolutePath().normalize()
                    .equals(target.toAbsolutePath().normalize())
                || (java.nio.file.Files.exists(target)
                    && java.nio.file.Files.isSameFile(source, target))) {
            throw new IllegalArgumentException("Use distinct files");
        }

        try (Reader reader =
                     new FileReader(source.toFile(), StandardCharsets.ISO_8859_1);
             Writer writer =
                     new FileWriter(target.toFile(), StandardCharsets.UTF_8)) {
            char[] buffer = new char[4096];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                writer.write(buffer, 0, count);
            }
        }

        System.out.println("Conversion complete");
    }
}
```

Run after preparing a Latin-1 source file:

```bash
javac ConvertLatin1ToUtf8.java
java ConvertLatin1ToUtf8 legacy.txt utf8.txt
```

**Stdout upon successful completion:**

```text
Conversion complete
```

This task differs from a **binary copy**: the output file may contain different bytes and have a different size even though the character content is equivalent. You cannot reliably infer the source charset from the filename; the example assumes the source charset has already been verified. Do not pass two paths pointing to the same file, because opening the writer can erase the source. Checking paths before opening only reduces risk in normal cases; it is not an atomic guard against concurrent modification.

**Limitation of ISO-8859-1:** it does not cover all Vietnamese letters. If the original data came from an encoding like `windows-1258` or another charset, you must select the actual charset used, for example `Charset.forName("windows-1258")` **if that charset is supported by the runtime**. Do not blindly substitute Latin-1 whenever you see garbled diacritics.

## 10. Malformed Encodings, Unmappable Characters, and BOM

### 10.1 Charsets Cannot Always Represent Every Input

With restricted charsets such as US-ASCII or Latin-1, some Unicode characters **cannot be encoded directly**. Conversely, a byte stream can contain byte sequences that are **invalid** for UTF-8.

The reaction to invalid input or unmappable characters depends on the API and how the decoder/encoder is configured. Some convenience ways of creating a reader/writer may use **replacement** (a replacement character when decoding or a replacement byte when encoding), allowing the program to keep running while losing information. Thus, "no exception thrown" **does not prove the data was preserved intact**.

If detecting invalid data is mandatory, you can configure a **`CharsetDecoder`** and choose `CodingErrorAction.REPORT`:

```java
// Illustrates strict UTF-8 reading from an existing file.
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(
        Files.newInputStream(Path.of("input.txt")), decoder)) {
    char[] buf = new char[4096];
    while (reader.read(buf) != -1) {
        // Process decoded content.
    }
}
```

This is an **illustrative snippet**; it requires `java.nio.charset.CharsetDecoder`, `CodingErrorAction`, `StandardCharsets`, `java.io.InputStreamReader`, `java.io.Reader`, `java.nio.file.Files`, and `Path`. When encountering malformed UTF-8 bytes, a decoder in `REPORT` mode can throw `MalformedInputException` (an `IOException`). Decide your application policy clearly: report an error, replace characters, or ignore—never silently alter critical content.

Similarly, you can configure a `CharsetEncoder` with `REPORT` when you need to detect unencodable characters.

### 10.2 Byte Order Mark (BOM)

A BOM is a byte pattern at the beginning of some Unicode files used to identify encoding/byte order. For UTF-8, the BOM is typically `EF BB BF` and is **optional**. `FileWriter` with UTF-8 **does not automatically insert a BOM**; if source data includes a BOM, understand how your specific tool or decoder handles it so you do not end up with an unwanted `U+FEFF` character at the start of the text.

For UTF-16, byte order matters. Use `UTF_16`, `UTF_16LE`, or `UTF_16BE` according to the **exact format specification**; do not guess based on the operating system.

### 10.3 Unicode Characters and Buffer Splitting

Because `Reader` returns UTF-16 `char` units, a code point outside the BMP can be split across **two code units**. A `char[]` read/write loop therefore does not mean each read returns a whole "display character." If your application must process independent Unicode code points, you can use `String.codePoints()` after collecting a valid string segment, taking care with surrogate pairs split across buffer boundaries.

When **copying characters faithfully** from a Reader to a Writer using the same convention, writing arrays in order remains appropriate; the key is not dropping or modifying surrogate pairs between read passes.

## 11. Reading Line by Line and Line-Ending Formats

When you need logical lines, `BufferedReader.readLine()` is more convenient than searching for `'\n'` manually. It recognizes LF, CR, or CRLF and returns the content **without the line terminator**. A file with an empty line yields `""`, while EOF returns `null`.

If you read with `readLine()` and write back with `writer.newLine()`, the output file may change line endings from LF to CRLF or vice versa depending on the environment. If the goal is to **preserve file content byte-for-byte**, do not decode and re-write line by line; copy bytes instead.

In formats with fixed line-ending requirements—for example data exchanged between Linux and Windows—agree on `"\n"` or `"\r\n"` per the specification. If a text file is produced by multiple different components, specify both the **charset** and the **newline convention**.

## 12. Resource Lifecycle and Errors to Handle

Use `try-with-resources` to close `FileReader`/`FileWriter` even when an exception occurs:

```java
try (FileReader reader =
         new FileReader("input.txt", StandardCharsets.UTF_8)) {
    // Process data.
}
```

This is an **illustrative snippet** with the corresponding imports. If `read()`/`write()` fails, you typically receive an `IOException` or a subclass; opening a reader can fail if the file does not exist or lacks read permission, and opening a writer can fail if the file cannot be created or written. An incomplete write can leave an **output file containing only partial data**; closing a resource does not turn the whole operation into an atomic transaction.

Several principles:

1. **Be clear on stream ownership**: if a method receives a Reader owned by the caller, define which side is responsible for closing it. Never arbitrarily close a shared stream.
2. **Avoid unintended overwrites**: for important files, check file-existence scenarios, use appropriate file-creation options, or write to a temporary file first and replace upon success.
3. **Read in chunks for large files**: `Files.readString`/`readAllLines` accumulate data in RAM, whereas `BufferedReader.readLine` processes line by line.
4. **Distinguish technical errors from data errors**: a file that opens cleanly with the wrong charset does not necessarily throw `IOException` immediately.
5. **Do not rely on `flush()` for durability**: applications requiring guaranteed persistence to hardware must use dedicated file-synchronization mechanisms.
6. **When opening multiple resources in one try**: Java closes them in **reverse** declaration order and preserves additional close errors in `suppressed exceptions`.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `new FileReader("a.txt")` on Java 17 forgetting default charset | May read differently across machines | `new FileReader("a.txt", UTF_8)` or the data's true charset |
| Writing UTF-8 but reading as Latin-1/another default charset | Garbled diacritics, mojibake | Agree on the same charset on both sides |
| Writing Vietnamese with US-ASCII | Unmappable characters may be replaced | Choose UTF-8 or an encoding that supports the data |
| Using `byte[]` and casting directly to `char` to read text | Ignores multi-byte encoding rules | Use `Reader`/`CharsetDecoder` |
| Writing `new FileWriter(path, UTF_8)` onto an existing file | Existing file is truncated | Explicitly choose overwrite, append, or fail-if-exists |
| `append=true` without inserting a newline | Content runs together on the same line | Add newlines according to the format |
| Assuming every `read(char[])` fills the buffer | Data loss or reading stale characters | Use the exact `count` |
| Comparing `char` directly with EOF and ignoring return type | Easy to confuse `int -1` with character data | Keep the `read()` result in an `int` |
| Forgetting to `close()` a writer | Can leak resources or leave buffered data unflushed | `try-with-resources` |
| Reading a huge file entirely into a `String` | High memory consumption | Stream by chunks or lines |
| Using `readLine()` then `newLine()` when original bytes must stay intact | Newlines/encoding can change | Copy bytes verbatim |
| Assuming every UTF-8 file has a BOM | May strip valid leading bytes or leave U+FEFF behind | Follow the actual file/input specification |

## 14. Practical Rules for Choosing an API

- **Just need to save/read new UTF-8 text simply:** `Files.writeString`/`Files.readString` for small files; `Files.newBufferedReader`/`newBufferedWriter` for long data.
- **Using `FileReader`/`FileWriter`:** pass `StandardCharsets.UTF_8` or the specified charset instead of relying on an unclear default.
- **Want line-by-line operations:** use `BufferedReader`/`BufferedWriter`.
- **Want to fix or convert a legacy document's charset:** know the exact source charset, decode properly, then encode in the target charset; test with tricky characters such as accented letters and emojis.
- **Want 100% byte preservation:** prefer byte APIs rather than decoding and re-encoding.
- **Need to handle potentially malformed encoding:** define an error policy and consider a decoder/encoder with `CodingErrorAction.REPORT`.

There is no single charset that is "right for every file": **UTF-8 is a good choice for new files**, but for existing files the right charset is the one the data source actually uses.

## 15. Self-Check Exercises

1. Run `FileTextRoundTrip` twice and confirm `hello-utf8.txt` is rewritten from scratch. Change `original` to a string with emojis and Vietnamese diacritics, and verify `Equal text: true`.
2. Run `CharsetMismatch`, explain each group of bytes in `436166c3a9`, and why reading as Latin-1 does not match the original.
3. In `AppendText`, remove `System.lineSeparator()` on the first write. Predict what `readLine()` will return and verify it.
4. Write a function that reads a UTF-8 file line by line and counts empty lines. Distinguish an empty line `""` from `null` at EOF.
5. Construct an invalid UTF-8 file (for example a lone `0xC3` byte at the end of the file), test the default decoder versus a `REPORT` decoder, and record the difference in result or exception.
6. Answer for yourself: why shouldn't Java 17 rely on `new FileReader(path)` for multilingual data? When is `ISO_8859_1` needed? When copying an image file, should you use `FileReader`/`FileWriter`?
7. Given a `legacy.txt` file confirmed to be Latin-1, test the transcoding program and inspect the leading/trailing bytes of the target file; explain why the resulting UTF-8 file can be larger.

## References

- Java SE 17 API: [`FileReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileReader.html), [`FileWriter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/FileWriter.html).
- Java SE 17 API: [`Files`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html), [`StandardCharsets`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- OpenJDK: [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400).

**Key takeaway:** `FileReader` reads bytes from a file and decodes them into characters; `FileWriter` encodes characters into bytes and writes them out. Choose the **right charset for the data**, prefer **explicit UTF-8** for new files, manage resources with `try-with-resources`, and carefully check **overwrite/append** modes.

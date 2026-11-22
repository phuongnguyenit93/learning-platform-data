# InputStreamReader, OutputStreamWriter, and the Files API in Java

## 1. Essence: Files and Networks Store Bytes, Java Processes Characters

In a localized Java application, a charset bug can turn Vietnamese text, personal names, emoji, or data from external systems into the replacement character `�`, question marks `?`, or “mojibake” strings such as `cafÃ©`. To read and write properly, you must understand the boundary between **bytes**, **UTF-16 characters in Java**, and **encoding rules**.

- `InputStream`: reads **bytes** from sources like files, sockets, memory, or packaged resources.
- `OutputStream`: writes **bytes** to a destination.
- `Reader`: reads **chars** (UTF-16 units) from a text stream.
- `Writer`: writes **chars** to a text stream.
- `Charset`: the rule for **encoding** characters into bytes and **decoding** bytes into characters.
- `InputStreamReader`: the **byte → char** bridge via `CharsetDecoder`.
- `OutputStreamWriter`: the **char → byte** bridge via `CharsetEncoder`.
- `java.nio.file.Files`: provides high-level APIs to read/write files directly by bytes, text, reader/writer, line streams, and many filesystem operations.

**Core principle:** there is no concept of “a file is automatically Vietnamese or English.” A file is a sequence of bytes; only by knowing the true charset can the program decode those bytes into the right text. **`Locale`** serves localization, and does not itself dictate byte encoding.

### 1.1. Bidirectional Diagram

~~~text
Read:
file / HTTP / byte[] --InputStream--> bytes
     --CharsetDecoder (e.g., UTF-8)-->
  UTF-16 char in Reader --> String / text processing

Write:
String / UTF-16 char --Writer-->
    CharsetEncoder (e.g., UTF-8)
     --OutputStream--> bytes --> file / HTTP / memory
~~~

If the **reading** encoding does not match the **writing** encoding, text can become corrupted without the program necessarily throwing an exception. For instance, a UTF-8 sequence misdecoded with another 8-bit charset can turn into strange characters that are still “valid” to that decoder.

### 1.2. Do Not Confuse Bytes, Chars, Code Points, and Graphemes

In Java, `char` is a UTF-16 code unit. A Unicode code point outside the BMP, such as emoji `U+1F603`, occupies **two `char`s** in a `String`, yet occupies **four bytes** when encoded in UTF-8.

Consider a string containing ASCII `Cafe`, combining acute accent `U+0301`, two Chinese characters, and an emoji:

~~~java
String text = "Cafe\u0301 | \u4F60\u597D | \uD83D\uDE03";
~~~

This is an illustrative statement inside a Java method. The string has **15 UTF-16 code units**, **14 code points**, and when encoded as UTF-8 becomes **22 bytes**. Do not use `text.length()` to infer UTF-8 file size or visible character count.

## 2. InputStreamReader: Decoding Bytes into Text

Use `InputStreamReader` when you already have an **`InputStream`** source and want to process it as characters. Construct it with an explicit charset:

~~~java
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;

try (InputStream stream = /* valid byte source */ null;
     Reader reader = new InputStreamReader(stream, StandardCharsets.UTF_8)) {
    // Read chars from reader.
}
~~~

**The snippet above only illustrates structure** and is not runnable due to the `null` source placeholder. In real code, replace it with `Files.newInputStream(path)`, a `ByteArrayInputStream`, or a valid stream; a complete standalone example appears in Section 8.

With an existing `InputStream`, a shorter form is:

~~~java
try (Reader reader =
        new InputStreamReader(source, StandardCharsets.UTF_8)) {
    char[] buffer = new char[4096];
    int n;
    while ((n = reader.read(buffer)) != -1) {
        // Process only buffer[0..n), not the entire buffer.
    }
}
~~~

`source` in this snippet is a valid `InputStream` managed by this scope. **A single `read` call is not guaranteed to fetch the entire content**. It returns the number of `char`s actually read, or `-1` at end-of-stream. Iterate the buffer up to `n`, not using `buffer.length` as the count of new characters.

### 2.1. Explicit Charset vs. Default Charset

Multiple constructors exist:

| Constructor | Charset used | Consequence |
| --- | --- | --- |
| `new InputStreamReader(in)` | `Charset.defaultCharset()` | Depends on runtime configuration/environment |
| `new InputStreamReader(in, StandardCharsets.UTF_8)` | UTF-8 | Explicit, easy to test, and portable |
| `new InputStreamReader(in, "UTF-8")` | By charset name | Can throw `UnsupportedEncodingException` if name is unsupported |
| `new InputStreamReader(in, decoder)` | Custom `CharsetDecoder` | Controls handling of malformed/unmappable bytes |

On Java 17, **do not** rely on the default charset of a developer machine or container. Java 18 and later change the default under JEP 400 in most situations, yet that does not magically turn bytes of a legacy file into UTF-8. For protocols/files with a defined encoding, always pass the charset directly.

`StandardCharsets.UTF_8`, `US_ASCII`, `ISO_8859_1`, `UTF_16`, `UTF_16BE`, and `UTF_16LE` are predefined constants. **Do not** infer charset from the content's language: Vietnamese text can be stored in UTF-8, UTF-16, or a legacy charset depending on the source.

### 2.2. Buffering and Stream Boundaries

`InputStreamReader` may read ahead more bytes than the number of `char`s needed for the current `read()` call, because a single character can span multiple bytes. Do not interleave direct byte reads from the same underlying stream while `InputStreamReader` is decoding, as the decoder may have already buffered ahead.

When reading line by line, wrap with `BufferedReader`:

~~~java
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(source, StandardCharsets.UTF_8))) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Process each line.
    }
}
~~~

This snippet requires importing `java.io.BufferedReader`. `readLine()` **strips line terminators**; if you need to preserve `CRLF`, `LF`, `CR`, or byte-exact original strings, use a different method. An extremely long “line” can still consume significant memory even when `BufferedReader` is used.

**Resource closing note:** closing an outer wrapper reader normally closes the underlying reader/stream layers. Use try-with-resources to close automatically even on error. If the underlying stream is owned by a framework (such as `System.in` or a caller-managed HTTP response), agree on ownership and avoid unexpectedly closing `System.in`.

### 2.3. ready Is Not an EOF Signal

`Reader.ready()` only indicates whether the next read is guaranteed not to block in a given context; `false` **does not mean end-of-data**. Keep reading until `read()` returns `-1`, or `readLine()` returns `null`.

## 3. OutputStreamWriter: Encoding Characters into Bytes

Use `OutputStreamWriter` when you have an `OutputStream` and need to write text in a specific charset:

~~~java
try (Writer writer = new OutputStreamWriter(
        destination, StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
}
~~~

This is an illustrative snippet inside a method, with `destination` as a valid `OutputStream` and imports `java.io.Writer`, `java.io.OutputStreamWriter`. The writer **encodes UTF-16 chars into UTF-8 bytes**. It does not choose language, resolve resource bundles, or adapt line endings by locale.

### 3.1. Why Do flush/close Matter?

`OutputStreamWriter` maintains an internal byte buffer. If a program calls `write` without calling `flush` or `close`, not all bytes are guaranteed to have reached the underlying stream. `close()` also flushes before closing.

~~~java
writer.write(text);
writer.flush();
~~~

This snippet illustrates usage with `writer` and `text` variables. With try-with-resources, `close` is called automatically; you only need an early `flush` when data must be displayed or forwarded **before** the block ends, such as in streaming protocols.

**Do not equate flush with durable persistence to disk.** A `Writer`'s flush pushes its encoding buffer to the underlying stream; durability requirements (fsync/force, atomic replace, and file-writing guarantees) are a separate I/O/transaction concern.

When performing many small `write` calls, wrap with `BufferedWriter` to batch character operations:

~~~java
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(destination, StandardCharsets.UTF_8))) {
    writer.write("dòng một");
    writer.newLine();
    writer.write("dòng hai");
}
~~~

This snippet requires importing `java.io.BufferedWriter`; `newLine()` writes the **platform's line separator**. If a file or protocol specifically requires `\n` (LF), write `writer.write('\n')` per the contract rather than relying on `newLine()`.

### 3.2. UTF-8 Is Not “One Byte Per Char”

Writing:

~~~java
String s = "Cafe\u0301";
byte[] encoded = s.getBytes(StandardCharsets.UTF_8);
~~~

produces 5 UTF-16 units yet 6 UTF-8 bytes, because the combining acute accent `U+0301` takes two bytes. For supplementary emoji, the surrogate pair is encoded into four bytes. Measure `encoded.length` when the protocol limits **bytes**, and `s.length()` when an API limits **UTF-16 units**.

## 4. Byte Streams vs. Character Streams: Choosing the Right Class

| Scenario | Appropriate API | Why |
| --- | --- | --- |
| Reading PNG, PDF, ZIP, encrypted data, protocol bytes | `InputStream`, `Files.readAllBytes` for small files | **Binary** data, must not be decoded as text |
| Reading a small UTF-8 file as a full string | `Files.readString(path, UTF_8)` | Simple, explicit charset |
| Reading many lines in a large file | `Files.newBufferedReader(path, UTF_8)` | Line-by-line iteration without loading entire file |
| Receiving text via socket or ByteArrayInputStream | `InputStreamReader(in, UTF_8)` | Bridges bytes to a Reader |
| Writing a text string to a small file | `Files.writeString(path, text, UTF_8)` | Simple, closes file automatically |
| Writing large text or line by line | `Files.newBufferedWriter(path, UTF_8)` | Incremental writes with buffering |
| Writing text to HTTP/socket/byte[] | `OutputStreamWriter(out, UTF_8)` | Converts chars to bytes |
| Handling encoding errors needing reject vs. replace distinction | `CharsetDecoder`/`CharsetEncoder` | Configures `CodingErrorAction` |

**Never** pass arbitrary binary bytes through `new String(bytes, UTF_8)` and then `getBytes(UTF_8)` to “preserve” a binary file: bytes that are not valid UTF-8 can be replaced, corrupting the data. Use byte APIs whenever data is not text.

## 5. The Files API: High-Level with Explicit Charset

`java.nio.file.Files` operates on `Path` and provides both text and byte APIs. The examples below are **illustrative snippets inside a method with `throws IOException` or exception handling**, except for the complete program in Section 8.

### 5.1. readString/writeString (Java 11+)

~~~java
Path file = Path.of("message.txt");
Files.writeString(file, text, StandardCharsets.UTF_8);
String restored = Files.readString(file, StandardCharsets.UTF_8);
~~~

`Files.writeString(path, text, charset)` writes **exactly the provided character string**, without appending a newline. If no `OpenOption` is passed, it defaults to **CREATE**, **TRUNCATE_EXISTING**, **WRITE**: a new file is created, and an existing file is overwritten (its old content erased before writing). Do not use this pattern on critical files without a backup or safe-write strategy.

`Files.readString(path, charset)` reads the entire file into one `String` and preserves the line endings from the source data. It is **not** meant for overly large files; it can exhaust RAM or throw `OutOfMemoryError`.

In Java 17:

- `Files.readString(path)` **defaults to UTF-8**.
- `Files.writeString(path, text)` **defaults to UTF-8**.

This differs from calling `new InputStreamReader(in)` **without a charset**, which uses the runtime's default charset. Do not lump those APIs together under a blanket claim that “all Java I/O defaults to UTF-8” on Java 17.

### 5.2. newBufferedReader/newBufferedWriter

~~~java
Path path = Path.of("lines.txt");

try (BufferedWriter writer =
        Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("first");
    writer.newLine();
    writer.write("second");
}

try (BufferedReader reader =
        Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

This snippet can sit inside a method with `throws IOException`; it requires importing `java.nio.file.Files`, `Path`, `StandardCharsets`, `BufferedWriter`, and `BufferedReader`. When options are omitted, `newBufferedWriter` also opens with **CREATE**, **TRUNCATE_EXISTING**, **WRITE**.

The overloads of `Files.newBufferedReader` and `Files.newBufferedWriter` **without a Charset** default to UTF-8 in Java 17. Even so, in code requiring an explicit contract, passing `StandardCharsets.UTF_8` spares readers from having to remember differences across API groups.

`newBufferedReader` operates line by line. It returns decoded text and can throw `IOException` on invalid-charset bytes; do not use it to preserve raw bytes or exact line separators.

### 5.3. Files.lines and readAllLines

~~~java
try (java.util.stream.Stream<String> lines =
        Files.lines(path, StandardCharsets.UTF_8)) {
    long count = lines.filter(s -> !s.isBlank()).count();
    System.out.println(count);
}
~~~

This is a snippet assuming `path` is already declared. `Files.lines` returns a **lazily read Stream** that keeps the file open. **You must close the stream** via try-with-resources. I/O exceptions encountered while consuming the stream after opening may be wrapped in `UncheckedIOException`, unlike exceptions during file opening.

`Files.readAllLines(path, UTF_8)` returns `List<String>`, convenient for small files, but loads all lines into memory with line terminators stripped from each string. When you need the verbatim file and it is moderately sized, `readString` fits better; for large/streaming line processing, use `newBufferedReader` or `lines`.

### 5.4. Files.readAllBytes and Files.write

~~~java
byte[] raw = Files.readAllBytes(path);
Files.write(path, raw);
~~~

These operations handle **bytes** rather than decoding text. If you need to inspect headers, BOMs, signatures, binary data, or compare raw bytes before and after, this is the right tool for **small files**. `readAllBytes` should not be used for huge files; for streaming, use `Files.newInputStream` or channels.

## 6. Charset Errors: Replacement vs. REPORT

An easily overlooked point: APIs can apply different **invalid byte/character handling policies**. Two common error types are:

- **Malformed input:** a byte sequence invalid under the charset, e.g., `C3 28` is not a valid UTF-8 sequence.
- **Unmappable character:** a character or byte with no valid representation in the target/source charset.

`CodingErrorAction` options:

| Mode | Meaning | Consequence |
| --- | --- | --- |
| `REPORT` | Reports an error instead of silently altering | Can throw `MalformedInputException` or `UnmappableCharacterException` |
| `REPLACE` | Substitutes the bad segment with a replacement | Data is **no longer preserved verbatim** |
| `IGNORE` | Skips the bad segment | Can cause **silent data loss** |

### 6.1. InputStreamReader(InputStream, Charset) and Replacement

When constructed directly from a `Charset`, `InputStreamReader` replaces invalid byte input with the decoder's default replacement character in the tested case. This is convenient for displaying text, yet **unsuitable when invalid data must be rejected**.

For example, given two bytes:

~~~text
C3 28
~~~

The first byte `C3` signals the start of a multi-byte UTF-8 sequence, but `28` is not a valid continuation byte. Reading with `InputStreamReader(..., StandardCharsets.UTF_8)` in the full example produces **U+FFFD** (replacement) as the first character, while `(` continues to be read.

If an application processes documents requiring exactness or auditing, silent replacement can be dangerous: you can no longer tell the exact original bytes from the decoded string. Validate input with a strict decoder or retain the raw bytes for inspection.

### 6.2. CharsetDecoder Configured with REPORT

~~~java
CharsetDecoder decoder = StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Reader reader = new InputStreamReader(source, decoder)) {
    // Read; decoding errors will be reported.
}
~~~

This snippet assumes `source` is a valid `InputStream` and imports `java.nio.charset.CharsetDecoder`, `CodingErrorAction`. Given input `C3 28`, reading raises `MalformedInputException` instead of completing with a replacement.

**Avoid sharing mutable `CharsetDecoder` instances across threads:** a decoder holds encoding/decoding state; create a new instance per reader or manage concurrency explicitly.

### 6.3. Files.readString Is Stricter Than the Case Above

Per the Java 17 API, `Files.readString(path, charset)` throws `IOException` upon encountering **malformed or unmappable** bytes. In our verified example, reading a file containing `C3 28` via `Files.readString(..., UTF_8)` throws `MalformedInputException` and prints `Files malformed=REJECTED`.

Therefore, these two calls:

~~~java
new InputStreamReader(source, StandardCharsets.UTF_8)
Files.readString(path, StandardCharsets.UTF_8)
~~~

**must not be described as having the same byte-error policy**. Both use UTF-8, yet differ in API and default malformed-input handling. If you must reject all invalid UTF-8 bytes, choose an API with the matching contract or a `REPORT` decoder.

### 6.4. OutputStreamWriter and CharsetEncoder

`OutputStreamWriter` with a `Charset` may replace malformed/unmappable characters with the charset's substitution byte. If lossless writing is mandatory, use a `CharsetEncoder` with `REPORT`:

~~~java
CharsetEncoder encoder = StandardCharsets.UTF_8.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(destination, encoder)) {
    writer.write(text);
}
~~~

This snippet assumes `destination` is a valid `OutputStream` and `text` is a `String`. Malformed surrogate pairs in the source or charsets incapable of encoding a character must be reported and handled; do not let errors turn into `?` unintentionally.

**Do not equate `new String(bytes, UTF_8)` with strict UTF-8 byte validation**. With the `Charset` constructor, invalid data may be replaced; if rejection is required, use a `REPORT` decoder or an API guaranteed to throw on errors.

## 7. BOM, Legacy Encodings, and Line Endings

### 7.1. BOM Is Leading Byte Data, Not Language

The UTF-8 BOM is normally the sequence **EF BB BF**. UTF-8 does not require a BOM, and many UTF-8 files have no BOM at all. A BOM may appear due to the system that exported the file.

- Do not assume **every** UTF-8 file has a BOM.
- Do not blindly strip the first three bytes without verifying they are actually `EF BB BF`.
- Once decoded into a `String`, a UTF-8 BOM may appear as a leading `U+FEFF` character if the API does not strip it automatically; test the behavior of your target API/file pipeline.
- Some protocols or CSV/JSON payloads have specific BOM policies. Follow the contract instead of “guessing” from locale.

For UTF-16, the variants `UTF_16`, `UTF_16BE`, and `UTF_16LE` differ in BOM usage and endianness. Do not treat UTF-16LE bytes as UTF-8 and expect the reader to auto-detect them accurately.

### 7.2. Legacy Encodings Do Not Convert Themselves to UTF-8

If a partner sends a file in Windows-1252, ISO-8859-1, or a legacy charset, you must know the true encoding (from technical specs, trusted HTTP headers, or file metadata/source contract) to decode it correctly.

Illustrative example:

~~~java
Charset legacy = Charset.forName("windows-1252");
String value = Files.readString(path, legacy);
Files.writeString(output, value, StandardCharsets.UTF_8);
~~~

This snippet only works when **the input file actually uses the specified charset**; it requires importing `Charset`, `Files`, `Path`, and variables. Proper encoding conversion means **decoding with the source charset and encoding with the target charset**. If the decode step uses the wrong charset, writing out UTF-8 only preserves corrupted data in a new encoding.

### 7.3. Line Endings

Three common styles:

- LF: `\n`.
- CRLF: `\r\n`.
- CR: `\r`.

`Files.readString` preserves the decoded line-ending characters actually present. `BufferedReader.readLine()` strips line terminators; `BufferedWriter.newLine()` uses the platform's line separator. When transferring files between Windows and Linux where **bytes or exact line endings** must be preserved, do not read by line and write with `newLine()` without an explicit line-ending conversion policy.

## 8. Complete Java 17 Program: UTF-8 Round-Trip and Error Decoders

The following file **`CharsetFilesDemo.java`** compiles and runs on Java 17+. It creates two temporary files via `Files.createTempFile` and deletes them in `finally`; it does not depend on external files or the host's default charset. Input uses Unicode escapes so terminals do not need to enter emoji directly.

~~~java
import java.io.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.HexFormat;

public class CharsetFilesDemo {
    static String readAll(Reader reader) throws IOException {
        StringBuilder text = new StringBuilder();
        char[] buffer = new char[4];
        int count;
        while ((count = reader.read(buffer)) != -1) {
            text.append(buffer, 0, count);
        }
        return text.toString();
    }

    public static void main(String[] args) throws IOException {
        String original = "Cafe\u0301 | \u4F60\u597D | \uD83D\uDE03";
        ByteArrayOutputStream output = new ByteArrayOutputStream();

        try (Writer writer = new OutputStreamWriter(
                output, StandardCharsets.UTF_8)) {
            writer.write(original);
        }
        byte[] bytes = output.toByteArray();
        System.out.println("encoded bytes=" + bytes.length);
        System.out.println("encoded hex=" +
                HexFormat.of().formatHex(bytes));

        String decoded;
        try (Reader reader = new InputStreamReader(
                new ByteArrayInputStream(bytes),
                StandardCharsets.UTF_8)) {
            decoded = readAll(reader);
        }
        System.out.println("stream roundtrip=" +
                original.equals(decoded));

        Path file = Files.createTempFile(
                "charset-files-demo-", ".txt");
        Path invalidFile = Files.createTempFile(
                "charset-invalid-", ".bin");
        try {
            Files.writeString(file, original,
                    StandardCharsets.UTF_8);
            System.out.println("Files roundtrip=" +
                    original.equals(Files.readString(
                            file, StandardCharsets.UTF_8)));
            System.out.println("Files size=" + Files.size(file));

            byte[] invalid = {(byte) 0xC3, (byte) 0x28};
            String replacement;
            try (Reader reader = new InputStreamReader(
                    new ByteArrayInputStream(invalid),
                    StandardCharsets.UTF_8)) {
                replacement = readAll(reader);
            }
            System.out.println("default replacement=" +
                    (replacement.codePointAt(0) == 0xFFFD));

            CharsetDecoder strict =
                    StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT);
            try (Reader reader = new InputStreamReader(
                    new ByteArrayInputStream(invalid), strict)) {
                readAll(reader);
                System.out.println("strict decoder=ACCEPTED");
            } catch (MalformedInputException ex) {
                System.out.println("strict decoder=REJECTED");
            }

            Files.write(invalidFile, invalid);
            try {
                Files.readString(invalidFile,
                        StandardCharsets.UTF_8);
                System.out.println("Files malformed=ACCEPTED");
            } catch (MalformedInputException ex) {
                System.out.println("Files malformed=REJECTED");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(invalidFile);
        }
    }
}
~~~

Compile and run (requires JDK 17+ for `HexFormat`):

~~~bash
javac -encoding UTF-8 CharsetFilesDemo.java
java CharsetFilesDemo
~~~

**Verified stdout** on Java:

~~~text
encoded bytes=22
encoded hex=43616665cc81207c20e4bda0e5a5bd207c20f09f9883
stream roundtrip=true
Files roundtrip=true
Files size=22
default replacement=true
strict decoder=REJECTED
Files malformed=REJECTED
~~~

Explanation:

1. `Cafe` uses 4 ASCII bytes; `U+0301` uses 2 UTF-8 bytes, spaces/`|` add 6 bytes; the two Chinese characters use 6 bytes, and emoji `U+1F603` uses 4 bytes. Total `4 + 2 + 6 + 6 + 4 = 22`.
2. `encoded hex` shows the exact 22 bytes written by `OutputStreamWriter` into `ByteArrayOutputStream`, independent of console charset.
3. `InputStreamReader` decodes valid bytes as UTF-8, so `stream roundtrip=true`.
4. `Files.writeString` and `Files.readString` also preserve valid Unicode; `Files.size(file)` measures **bytes** in the file.
5. For invalid UTF-8 bytes `C3 28`, the default decoder of `InputStreamReader(InputStream, Charset)` uses replacement, so the first character is `U+FFFD`.
6. When using a `CharsetDecoder` with `REPORT`, the error is signaled via `MalformedInputException`.
7. `Files.readString(invalidFile, UTF_8)` also rejects the malformed file and throws `MalformedInputException` in this program.
8. Both temporary files are deleted after testing; in real applications, error handling must also consider failures when writing or deleting files.

Do not copy these hex values to claim all Unicode text has this length; this is the result **for this exact sample string**. Every byte measurement must be computed from the actually encoded bytes and chosen charset.

## 9. Choosing APIs by Scale and Resource Lifecycle

| Requirement | Typical appropriate approach | Constraints |
| --- | --- | --- |
| Small UTF-8 config/README file | `Files.readString` | Entire file loaded into RAM |
| Small report file | `Files.writeString` | Watch default overwrite behavior |
| Multi-line log/CSV file | `newBufferedReader` or `Files.lines` | Close resources, guard against extremely long lines |
| Incrementally generated text | `newBufferedWriter` | Fix charset, line ending, options |
| Network InputStream | `InputStreamReader` | Correct charset per HTTP/protocol contract |
| Network OutputStream | `OutputStreamWriter` | Flush/configure charset encoder properly |
| Exact bytes for checksum/signature | `Files.newInputStream` or `readAllBytes` | Do not convert to text unnecessarily |
| Large file that cannot fit in RAM | Buffered/streaming I/O | Bound input size, do not accumulate into a huge `StringBuilder` |
| Potentially malformed data | Strict decoder or error-reporting Files text API | Avoid silent replacement if auditing is required |

For small files, minimal boilerplate usually matters more than raw throughput. For multi-GB files, **reading everything into a single `String`** is impractical and can create multiple in-memory copies. Process sequentially by buffer or line and bound resources.

### 9.1. Specify OpenOption Explicitly When Needed

`Files.writeString` or `Files.newBufferedWriter` **truncates an existing file by default** if options are omitted. To append instead:

~~~java
Files.writeString(path, "more text",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
~~~

This snippet requires importing `StandardOpenOption` and having variables ready. When appending text with `APPEND`, ensure the existing file uses the **same charset**—do not append UTF-8 onto a legacy file encoded differently. If you never want to overwrite, consider `CREATE_NEW` and handle `FileAlreadyExistsException`.

A single write operation does not guarantee **atomic replace** or consistency in case of a process crash. When writing critical configuration files, you typically need a temporary file on the same filesystem and a safe replacement strategy via `Files.move`, considering `ATOMIC_MOVE` when supported by the provider. Do not confuse closing a stream with an atomic file transaction.

### 9.2. Files.lines Must Be Closed

Do not write:

~~~java
long n = Files.lines(path).count();
~~~

and abandon the stream as if it were an in-memory collection. `Files.lines` holds the file open; use:

~~~java
try (var lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long n = lines.count();
}
~~~

Both snippets illustrate code inside a method handling `IOException`; the first is **discouraged** because it leaks an unclosed resource. For a file being modified concurrently while the stream is read, results can be unspecified per the API contract.

## 10. Real-World Errors and Fixes

| Error | Symptom | Resolution |
| --- | --- | --- |
| Reading UTF-8 with wrong charset | Mojibake, corrupted Vietnamese letters | Identify source charset, decode properly |
| Using `new InputStreamReader(in)` on Java 17 | Depends on runtime default charset | Pass `StandardCharsets.UTF_8` |
| Assuming `Files.readString` always matches `InputStreamReader` | Different malformed-input policies | Read API contract, use `REPORT` decoder when needed |
| Using `new String(bytes)` without charset | Depends on default charset | `new String(bytes, charset)` for quick decoding |
| Using `OutputStreamWriter` without flush/close | Bytes stuck in buffer, truncated output | try-with-resources, flush at proper points |
| Mixing direct byte reads with Reader on same stream | Reader may read ahead | Use one consistent I/O layer |
| Using `available()` or `ready()` as end condition | Incomplete reads | Read until `-1` or `null` |
| Calling `Files.writeString` on existing file unchecked | File truncated | Choose `CREATE_NEW`, `APPEND`, or safe replace workflow |
| `readLine()` then `newLine()` to copy file verbatim | Line endings change, trailing newline added/dropped | Use byte copy or `readString/writeString` when appropriate |
| Using `String.length()` as UTF-8 byte count | Wrong for non-ASCII Unicode | Measure `getBytes(UTF_8).length` or file size |
| Ignoring malformed/unmappable errors | Silent replacement/loss of data | Set controlled `REPORT`/`REPLACE` policy |
| Using `Files.readString` on huge files | High RAM usage or OOME | Streaming Reader/`Files.lines` |
| Forgetting to close `Files.lines` | File descriptor/handle leak | try-with-resources |
| Using text readers for binary files | Bytes altered or decode errors | `InputStream`/`OutputStream`, byte APIs |
| Transcoding without considering BOM/line endings | File incompatible downstream | Specify BOM/newline contract |
| Allowing arbitrary user-supplied paths | Path traversal / out-of-scope file overwrite | Validate permissions, paths, and limits |

### 10.1. Data Safety Goes Beyond the Right Charset

When receiving files from users or external systems:

- Bound file size, line count, and maximum length per line.
- Do not use unvalidated filenames/paths to access arbitrary locations outside allowed directories; account for symlinks, race conditions, and file permissions.
- Verify encoding against a published contract, never guessing from `Locale`.
- Decide clearly whether to **reject or replace** invalid-charset input; for invoices, signatures, accounting records, or auditable data, silent replacement is usually inappropriate.
- If content is rendered as HTML, also HTML-escape it to prevent injection; properly decoded UTF-8 **does not** mean content is safe to embed in markup.
- For international text, Unicode normalization, invisible characters, graphemes, and locale-sensitive collation are separate problems not solved by charset alone.

## 11. Essential Tests

A reliable I/O/charset module should test:

1. **ASCII:** identical content through UTF-8 reader/writer, matching byte count.
2. **Accented Vietnamese:** precomposed characters and combining mark `U+0301`, preserving original code points.
3. **Non-BMP Unicode:** emoji `U+1F603`, verifying two UTF-16 `char`s encode/decode accurately.
4. **CJK/RTL:** different scripts do not alter charset or drop characters.
5. **Malformed bytes:** `C3 28`, comparing `REPLACE` with `REPORT`.
6. **Unmappable characters:** try encoding a Unicode character outside US-ASCII with an error-reporting `CharsetEncoder`.
7. **Mismatched charset:** intentionally reading UTF-8 with another charset to recognize mojibake; do not call it Unicode normalization.
8. **BOM:** UTF-8 files with and without `EF BB BF`; verify consumer policy.
9. **Newlines:** LF, CRLF, CR, files with and without a trailing newline; compare `readLine` and `readString`.
10. **OpenOption:** existing file truncated by default; `APPEND` and `CREATE_NEW` must follow defined behavior.
11. **Close/flush:** Writer closed/flushed before inspecting bytes; `Files.lines` stream always closed.
12. **Large files:** streaming by buffer/line without holding the entire file in RAM; test extremely long lines.
13. **Permissions/IO failure:** missing file, unreadable file, out-of-disk-space, partial write failure.
14. **Portability:** run on JDK 17+ with explicit charsets; independent of OS default locale/charset.
15. **Exact files:** compare raw bytes, file size, and hash when the contract requires byte preservation; compare `String.equals` when text preservation is required.

### Exercise 1 — Same String, Different Length Units

Measure `length()`, `codePointCount`, and `getBytes(UTF_8).length` for the sample string. Explain why the byte count is 22 even though the `char` count is 15 and the code point count is 14.

### Exercise 2 — Comparing Default APIs

Read the Java SE 17 documentation and explain the difference between `new InputStreamReader(in)` and `Files.readString(path)` regarding **default charset**. Use `Charset.defaultCharset()` to inspect the runtime environment, but do not treat that information as a UTF-8 file protocol.

### Exercise 3 — Malformed Input

With bytes `C3 28`, test `InputStreamReader` using the UTF-8 `Charset`, a `REPORT` decoder, and `Files.readString`. Explain which cases produce a replacement character and which throw an error.

### Exercise 4 — Controlled Encoding Conversion

Suppose a source file actually uses `windows-1252`. Write a program that reads with the source charset and then writes UTF-8; verify the text after round-trip using a sample containing non-ASCII characters. Do not infer the charset from language.

### Exercise 5 — Multi-Line Files

Use `Files.newBufferedWriter` to write two lines containing Unicode, read them back with `Files.newBufferedReader`, and then compare with `Files.readString` to see why one API preserves line endings while the other strips them from line results.

## 12. Summary

`InputStreamReader` and `OutputStreamWriter` are **the two bridges between byte streams and character streams**. Always pick the `Charset` matching the true source and destination—typically `StandardCharsets.UTF_8` in modern protocols—and never let Java 17's default charset or locale settings dictate data accidentally.

`Files` provides convenient APIs: `readString/writeString` for small files, `newBufferedReader/newBufferedWriter` or `lines` for line-by-line and stream processing, and `newInputStream/readAllBytes` when bytes are needed. You must manage **resource closing**, **file opening/overwriting**, **line endings**, **BOM**, and **malformed/unmappable sequences**.

**Having the right charset is not enough:** a solid I/O system also separates bytes from text, specifies acceptance/rejection of invalid data, preserves content per contract, tests Unicode thoroughly, and avoids hidden dependencies on the runtime environment.

**References:**

- Java SE 17, `InputStreamReader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html
- Java SE 17, `OutputStreamWriter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html
- Java SE 17, `Files`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17, `Charset`, `CharsetDecoder`, `CharsetEncoder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/package-summary.html
- Java SE 17, `StandardCharsets`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html
- Java SE 17, `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html

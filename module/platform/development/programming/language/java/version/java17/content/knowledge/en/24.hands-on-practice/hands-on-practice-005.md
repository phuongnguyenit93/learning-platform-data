# Reading Text Data, Converting Bytes to Hex, and Writing Results

A Java program may need to read a text file, represent its bytes in hexadecimal (hex), and write the result to another file. This is useful when inspecting encodings, viewing payloads, comparing data, or storing a human-readable representation of binary content.

Java 17 provides standard APIs to carry out this workflow:

- `Files.readString` reads a text file into a `String` using a specified charset.
- `Files.readAllBytes` reads the raw bytes of a file into a byte array.
- `String.getBytes(Charset)` encodes a string into bytes.
- `HexFormat` formats bytes into hex and parses hex back to bytes. This API was introduced in Java 17.
- `Files.writeString` writes text; `Files.write` writes bytes.
- `Files.newInputStream` and `Files.newBufferedWriter` process files in chunks.

Before writing code, decide clearly whether you want to convert the **original file bytes** or the bytes produced after **decoding text and re-encoding it**. The two approaches can yield different results. If you need an exact byte-level representation of the file, read the raw bytes directly.

## 1. Bytes and Hexadecimal Representation

A byte has 8 bits, giving 256 possible values from 0 to 255 (`0x00` to `0xFF`). Hexadecimal uses 16 symbols: `0–9` and `A–F`. Each hex digit represents 4 bits, so every byte is always written using two hex digits.

| Byte value | Binary | Hex |
| ---: | --- | --- |
| 0 | 00000000 | 00 |
| 10 | 00001010 | 0A |
| 65 | 01000001 | 41 |
| 127 | 01111111 | 7F |
| 255 | 11111111 | FF |

For example, the following bytes:

```text
48 65 6C 6C 6F
```

have the continuous hex representation:

```text
48656C6C6F
```

Decoded as UTF-8, they correspond to the text `Hello`. Hex is merely a readable notation for bytes; converting bytes to hex does not alter the underlying data.

## 2. Choosing the Right Way to Read a File

There are two common scenarios:

1. The file is treated as text in a known charset.
2. You need the exact bytes stored in the file, regardless of whether they form valid text.

Do not conflate the two scenarios because decoding/encoding is a data transformation step.

### 2.1. Reading a Text File with Files.readString

For a UTF-8 text file:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("data", "message.txt");
String content = Files.readString(input, StandardCharsets.UTF_8);
System.out.println(content);
```

`Files.readString(Path, Charset)` was added in Java 11. It reads the entire file and decodes it into a `String` using the specified charset. The overload without a charset also uses UTF-8, but passing `StandardCharsets.UTF_8` makes the encoding contract explicit in code.

A `String` is a Java character sequence, no longer the file's original byte array.

### 2.2. Reading All Bytes with Files.readAllBytes

If you need to convert the exact file bytes to hex:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

Path input = Path.of("data", "message.txt");
byte[] bytes = Files.readAllBytes(input);
```

`readAllBytes` returns the entire file contents in a byte array. It does not decode text, change charsets, or normalize line endings.

This is the right choice when you need an accurate hex dump, when the file contains invalid UTF-8 byte sequences, or when BOMs, CRLF/LF, and special bytes must be preserved. Because the whole file is loaded into memory, avoid `readAllBytes` for very large files unless memory budgets allow it.

### 2.3. Comparing Reading APIs

| Need | Appropriate API |
| --- | --- |
| Read UTF-8 text into a string | `Files.readString(path, UTF_8)` |
| Get the raw original bytes of a file | `Files.readAllBytes(path)` |
| Read a large file in byte chunks | `Files.newInputStream(path)` |
| Read a large text file line by line | `Files.newBufferedReader(path, UTF_8)` |

If the goal is byte-for-byte hex conversion of the file contents, use a byte API. If the goal is to read a text string, encode it as UTF-8, and display the UTF-8 bytes in hex, read the text first and encode it explicitly.

## 3. Reading Text and Converting to Bytes

A `String` is not a byte array. Converting string content to bytes requires selecting a charset:

```java
import java.nio.charset.StandardCharsets;

String content = "Hello, Java 17!";
byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
```

`getBytes(StandardCharsets.UTF_8)` encodes the string into UTF-8 bytes. Never rely on the machine's default charset when exchanging data between systems. Two machines with different default charsets can produce different bytes from the same string.

### 3.1. The Same Text Can Have Different Byte Representations

A character can encode into different numbers of bytes depending on the charset. The letter `A` in UTF-8 is a single byte `41`; accented Vietnamese characters typically require multiple UTF-8 bytes. Therefore, hex represents bytes, not Unicode characters directly.

### 3.2. Original Bytes vs. Re-Encoded Bytes

```java
byte[] original = Files.readAllBytes(input);
String text = Files.readString(input, StandardCharsets.UTF_8);
byte[] encodedAgain = text.getBytes(StandardCharsets.UTF_8);
```

For valid UTF-8 text without string transformations, the two arrays are usually identical. However, never assume they always match in every situation: input may contain invalid UTF-8 sequences, code might normalize Unicode or modify content, or decode/encode pipelines might handle BOMs differently.

When byte-for-byte fidelity is required, do not decode and re-encode. Convert the original bytes directly.

## 4. Converting Bytes to Hex with HexFormat

Java 17 includes `java.util.HexFormat`, the standard API for formatting and parsing hexadecimal data:

```java
import java.util.HexFormat;

byte[] bytes = {
    0x48, 0x65, 0x6C, 0x6C, 0x6F
};

String hex = HexFormat.of().formatHex(bytes);
System.out.println(hex);
// 48656c6c6f
```

`HexFormat.of()` returns the default formatter: lowercase hex digits, no delimiter, and no `0x` prefix. Every byte always produces two digits; byte `0x0A` is formatted as `0a`, not `a`.

### 4.1. Using Uppercase

```java
HexFormat hexFormat = HexFormat.of().withUpperCase();
String hex = hexFormat.formatHex(bytes);
```

Output: `48656C6C6F`.

### 4.2. Adding a Delimiter Between Bytes

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ");
String hex = hexFormat.formatHex(bytes);
```

Output: `48 65 6c 6c 6f`.

You can combine a delimiter with uppercase:

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ").withUpperCase();
String hex = hexFormat.formatHex(bytes);
```

Output: `48 65 6C 6C 6F`.

### 4.3. Adding a Prefix and Suffix

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ")
        .withPrefix("0x")
        .withUpperCase();

String hex = hexFormat.formatHex(bytes);
```

Output: `0x48 0x65 0x6C 0x6C 0x6F`. Prefixes and suffixes are applied to each byte.

### 4.4. Specifying a Byte Slice

```java
String hex = HexFormat.of().formatHex(bytes, 1, 4);
```

The two indices are `fromIndex` (inclusive) and `toIndex` (exclusive). The example above formats the bytes at indices 1, 2, and 3.

## 5. Complete Example: Reading a File and Writing a Hex String

The following example reads the raw bytes of a file, converts them to hex, and writes the result to another file:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class TextToHex {
    public static void main(String[] args) throws IOException {
        Path input = Path.of("data", "message.txt");
        Path output = Path.of("out", "message.hex");

        byte[] bytes = Files.readAllBytes(input);
        String hex = HexFormat.of().formatHex(bytes);

        Files.createDirectories(output.getParent());
        Files.writeString(
                output,
                hex + System.lineSeparator(),
                StandardCharsets.UTF_8
        );

        System.out.println("Read " + bytes.length + " bytes");
        System.out.println("Wrote hex to " + output);
    }
}
```

Processing flow:

1. `Path.of` constructs the input and output file paths.
2. `Files.readAllBytes` reads the original bytes.
3. `HexFormat.of().formatHex` produces the hex string.
4. `Files.createDirectories` creates the output directory if missing.
5. `Files.writeString` writes the result in UTF-8.

Without a delimiter or prefix, the hex portion is exactly twice as long as the input byte count. For example, 5 bytes yield 10 hex characters. `System.lineSeparator` appends a trailing newline.

Never point `input` and `output` to the same file. `Files.writeString` creates or truncates the destination file by default; overwriting the input file can destroy source data.

### 5.1. Writing Space-Separated Hex

Replace the formatter with:

```java
HexFormat hexFormat = HexFormat.ofDelimiter(" ").withUpperCase();
String hex = hexFormat.formatHex(bytes);
```

For `n` bytes, the continuous form takes `2n` hex characters. The single-space-delimited form takes `3n - 1` characters, excluding any line ending.

## 6. Writing Output with Files.writeString

`Files.writeString` is suitable for text output:

```java
Files.writeString(output, hex, StandardCharsets.UTF_8);
```

The overload taking a charset lets you specify the encoding explicitly. Without a charset argument, the API uses UTF-8.

When no `OpenOption` is passed, the method defaults to creating the file if absent and truncating existing content if present. You can specify this explicitly:

```java
import static java.nio.file.StandardOpenOption.CREATE;
import static java.nio.file.StandardOpenOption.TRUNCATE_EXISTING;
import static java.nio.file.StandardOpenOption.WRITE;

Files.writeString(
        output,
        hex,
        StandardCharsets.UTF_8,
        CREATE,
        TRUNCATE_EXISTING,
        WRITE
);
```

### 6.1. Appending to a File

```java
import static java.nio.file.StandardOpenOption.APPEND;
import static java.nio.file.StandardOpenOption.CREATE;

Files.writeString(
        output,
        hex + System.lineSeparator(),
        StandardCharsets.UTF_8,
        CREATE,
        APPEND
);
```

`APPEND` fits logs or accumulated outputs across multiple runs. If multiple threads or processes write to the same file concurrently, design proper synchronization or separate files; do not assume concurrent appends from multiple writers form an atomic transaction.

## 7. Parsing Hex Back to Bytes

`HexFormat` also supports parsing a hex string back into a byte array:

```java
import java.util.HexFormat;

String hex = "48656c6c6f";
byte[] bytes = HexFormat.of().parseHex(hex);
```

If the hex string uses delimiters, use a matching formatter:

```java
HexFormat spaced = HexFormat.ofDelimiter(" ");
byte[] bytes = spaced.parseHex("48 65 6c 6c 6f");
```

You can write the bytes back to a file:

```java
Files.write(Path.of("out", "restored.bin"), bytes);
```

When the hex string was produced from original bytes and has not been altered, parsing it restores the exact original byte array.

### 7.1. Validating Invalid Hex

Hex input must contain valid hex digits and match the expected format. Non-hex characters, mismatched delimiters, or an odd/invalid digit count will cause `parseHex` to throw `IllegalArgumentException`.

```java
try {
    byte[] bytes = HexFormat.of().parseHex(userInput);
    Files.write(output, bytes);
} catch (IllegalArgumentException ex) {
    System.err.println("Hex input is invalid");
}
```

If hex input comes from external sources, enforce a length limit before parsing. A string of `2n` hex digits represents `n` bytes, so the text representation is at least twice the size of the binary payload.

## 8. Reading UTF-8 Text and Exporting Hex of the Encoded Content

If the requirement is to read text into a `String` and then export the UTF-8 bytes of that string:

```java
Path input = Path.of("data", "message.txt");
Path output = Path.of("out", "message-utf8.hex");

String text = Files.readString(input, StandardCharsets.UTF_8);
byte[] utf8 = text.getBytes(StandardCharsets.UTF_8);
String hex = HexFormat.of().formatHex(utf8);

Files.createDirectories(output.getParent());
Files.writeString(output, hex, StandardCharsets.UTF_8);
```

Here, the hex represents the UTF-8 bytes produced from the `text` string. When you need the exact original bytes of the file, use `Files.readAllBytes(input)` instead of a decode/encode round trip.

Do not call `trim`, `strip`, `replace`, or Unicode normalization if the goal is to preserve exact content. `trim`/`strip` removes leading and trailing whitespace; replacing CRLF with LF alters the bytes upon re-encoding.

## 9. Processing Large Files in Chunks

`readAllBytes` and `readString` load the entire file into memory. For large files, this can cause heap pressure or `OutOfMemoryError`.

You can read in byte chunks and stream hex output sequentially:

```java
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.HexFormat;

public class LargeFileToHex {
    public static void convert(Path input, Path output)
            throws IOException {

        HexFormat hexFormat = HexFormat.of();
        byte[] buffer = new byte[8192];

        Path parent = output.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        try (InputStream in = Files.newInputStream(input);
             BufferedWriter writer = Files.newBufferedWriter(
                     output,
                     StandardCharsets.UTF_8,
                     StandardOpenOption.CREATE,
                     StandardOpenOption.TRUNCATE_EXISTING,
                     StandardOpenOption.WRITE)) {

            int count;
            while ((count = in.read(buffer)) != -1) {
                hexFormat.formatHex(writer, buffer, 0, count);
            }
        }
    }
}
```

The overload `formatHex(Appendable, byte[], int, int)` writes directly to an `Appendable`, avoiding allocating an intermediate string for the entire file. `BufferedWriter` batches small writes to reduce I/O syscalls.

Example invocation:

```java
LargeFileToHex.convert(
        Path.of("data", "large-input.bin"),
        Path.of("out", "large-input.hex")
);
```

This example writes continuous hex with no delimiter and no line breaks. Buffer memory stays constant regardless of file size. The output file itself will still be roughly twice the size of the input file.

### 9.1. Why Avoid Reading Entire Large Files?

If an input file has `N` bytes:

- The input byte array takes roughly `N` bytes, excluding object overhead.
- The hex string takes roughly `2N` characters; actual heap cost depends on the runtime's `String` representation.
- Holding both the array and string simultaneously can push peak memory usage to several times the file size.

Streaming avoids holding the entire input and output in the heap at the same time.

### 9.2. Handling Errors During Streaming

Reads and writes can fail due to deleted files, permission changes, full filesystems, or hardware errors. Try-with-resources ensures the stream and writer are closed when an error occurs.

If writing fails partway through, an incomplete output file may remain on disk. When atomic output integrity is needed, write to a temporary file on the same filesystem, close it cleanly, and rename it to the final target via `Files.move`. Be sure to define the replacement policy and verify filesystem support for atomic moves.

## 10. Writing Hex by Lines or Byte Groups

With an array already in memory:

```java
HexFormat format = HexFormat.ofDelimiter(" ").withUpperCase();
String hex = format.formatHex(bytes);
```

If you need lines of 16 bytes each:

```java
HexFormat format = HexFormat.ofDelimiter(" ").withUpperCase();
StringBuilder result = new StringBuilder();

for (int offset = 0; offset < bytes.length; offset += 16) {
    int end = Math.min(offset + 16, bytes.length);
    result.append(format.formatHex(bytes, offset, end))
          .append(System.lineSeparator());
}
```

For large files, do not build a `StringBuilder` holding the entire output. Format each chunk and write it directly to `BufferedWriter`. If each line must contain exactly 16 bytes, track line boundaries independently of how many bytes each `InputStream.read` call returns, because `read` does not guarantee filling the buffer.

## 11. Charsets, BOMs, and Line Endings

Encoding and byte layout affect the resulting hex output.

### 11.1. Specify Charsets Explicitly

```java
String text = Files.readString(path, StandardCharsets.UTF_8);
```

If a file uses another charset, specify that exact charset. You cannot reliably infer a charset merely by inspecting a few bytes; some formats include a BOM or metadata, while many files carry no encoding header at all.

### 11.2. BOM

Some text files begin with a byte order mark (BOM). When reading raw bytes, the BOM remains in the array and is formatted as hex just like any other byte.

When reading via a decoder, how the BOM is interpreted depends on the charset and decoder. With UTF-8, the BOM may be preserved as character `U+FEFF` rather than stripped automatically. If re-encoded afterward, the BOM bytes may reappear.

If the application needs to strip a BOM for a specific file format, implement that as an explicit rule and only when the data specification calls for it. Never silently drop leading bytes simply because they look unusual.

### 11.3. Line Endings

Windows typically uses CRLF, whereas many Unix environments use LF. When reading raw bytes and formatting hex, both CR and LF bytes are preserved intact.

If you read text and replace CRLF with LF, the re-encoded output bytes will differ from the original file. Do not normalize line endings when comparing or storing exact byte representations.

## 12. Error Handling and Path Validation

File operations can throw `IOException` or specific subclasses:

| Error | Possible cause |
| --- | --- |
| `NoSuchFileException` | File or parent directory does not exist. |
| `AccessDeniedException` | Process lacks read or write permission. |
| `FileAlreadyExistsException` | File creation option forbids overwriting an existing file. |
| `InvalidPathException` | Path string is invalid for the current filesystem. |
| `IOException` | Read/write, filesystem, or device error. |
| `IllegalArgumentException` from `parseHex` | Hex string does not match the formatter's rules. |

Example:

```java
try {
    byte[] bytes = Files.readAllBytes(input);
    String hex = HexFormat.of().formatHex(bytes);
    Files.writeString(output, hex, StandardCharsets.UTF_8);
} catch (java.nio.file.NoSuchFileException ex) {
    System.err.println("Input file does not exist: " + input);
} catch (java.nio.file.AccessDeniedException ex) {
    System.err.println("Permission denied: " + ex.getFile());
} catch (IOException ex) {
    System.err.println("File processing failed: " + ex.getMessage());
}
```

Never catch an exception and continue as though the result was written successfully. If conversion fails, report the error and avoid consuming a half-written output file.

### 12.1. Checking the File Before Reading

```java
if (!Files.isRegularFile(input)) {
    throw new IOException("Input is not a regular file");
}

long size = Files.size(input);
if (size > 50L * 1024 * 1024) {
    throw new IOException("Input file is too large");
}
```

The size limit is an example; choose one matching application requirements. Pre-checks do not completely eliminate race conditions: a file can change after the check runs. For untrusted files or files modifiable by other processes, still handle read errors and enforce limits at the stream layer.

## 13. Complete Example: Reading UTF-8 Text, Generating Hex, and Writing a File

This version fits small or medium text files when the goal is to represent the UTF-8 bytes of the decoded text:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HexFormat;

public class TextHexExporter {
    public static void main(String[] args) throws IOException {
        Path input = Path.of("input", "note.txt");
        Path output = Path.of("output", "note.hex");

        String text = Files.readString(input, StandardCharsets.UTF_8);
        byte[] utf8Bytes = text.getBytes(StandardCharsets.UTF_8);

        HexFormat formatter = HexFormat.ofDelimiter(" ")
                .withUpperCase();
        String hex = formatter.formatHex(utf8Bytes);

        Path parent = output.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        Files.writeString(
                output,
                hex + System.lineSeparator(),
                StandardCharsets.UTF_8
        );

        System.out.println("Characters: " + text.length());
        System.out.println("UTF-8 bytes: " + utf8Bytes.length);
        System.out.println("Hex output: " + output.toAbsolutePath());
    }
}
```

If the requirement is the hex of the original file bytes, replace the read and encode steps with:

```java
byte[] sourceBytes = Files.readAllBytes(input);
String hex = HexFormat.ofDelimiter(" ")
        .withUpperCase()
        .formatHex(sourceBytes);
```

Do not perform both flows and assume their outputs must match. Pick the exact output definition required by the problem.

## 14. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Hex missing leading zeros on bytes | Hand-rolled conversion without zero-padding to two digits. | Use `HexFormat`; every byte always produces two hex digits. |
| Hex differs between two machines | Different default charsets or string normalization. | Specify charset explicitly, usually UTF-8 per the data contract. |
| Hex does not match original bytes | Decoded to `String` and re-encoded or modified text. | Use `readAllBytes` or a byte stream when byte-for-byte fidelity is needed. |
| Large file causes out-of-memory error | Using `readAllBytes`, `readString`, or holding huge hex strings in memory. | Stream in chunks via `InputStream` and write via `BufferedWriter`. |
| Old output file contents were truncated | `writeString` truncates the target file by default. | Use a temp file, or specify `APPEND` when appending is intended. |
| Output has spaces but parsing fails | Parsing formatter does not use the matching delimiter. | Use a `HexFormat` configured with the same delimiter to parse. |
| `parseHex` throws `IllegalArgumentException` | Non-hex characters, wrong delimiter, or invalid digit count. | Validate input and handle the exception. |
| CRLF or BOM disappeared | Text processing normalized or stripped special data. | Convert raw bytes directly when exact file preservation is needed. |
| File not found | Relative path depends on current working directory. | Verify working directory or use appropriate paths/resources. |
| Incomplete output | I/O error mid-write or process terminated. | Write to a temp file, close cleanly, then rename when integrity is required. |

## 15. Practice Exercises

### Exercise 1 — Read and Print Hex

Create a `message.txt` file containing `Hello, Java 17!`. Use `Files.readAllBytes` and `HexFormat.of().formatHex` to print hex. Explain why every byte has two digits.

### Exercise 2 — Compare UTF-8 and Raw Bytes

Create a file containing accented Vietnamese text. Compare the hex of `Files.readAllBytes` with the hex of `Files.readString(..., UTF_8).getBytes(UTF_8)`. Explain the conditions under which both byte arrays are identical.

### Exercise 3 — Change Display Formatting

Try `withUpperCase`, `ofDelimiter(" ")`, `withPrefix("0x")`, and `withSuffix`. Record the outputs and parse each back using the matching formatter.

### Exercise 4 — Write Output to a File

Use `Files.writeString` to write hex. Run twice and observe the truncation behavior; then use `CREATE` and `APPEND` to append results.

### Exercise 5 — Processing Large Files

Create a large binary file, write a program reading via a buffer and calling `HexFormat.formatHex(Appendable, ...)` to write to disk. Observe heap usage compared to `readAllBytes`.

### Exercise 6 — Restoring Data

Read a hex file, parse it with `HexFormat.parseHex`, write the byte array back to a new file, and compare checksums or raw byte contents of the two files.

## 16. Official Java 17 Documentation

- [Java SE 17 API — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html): formatting bytes to hex, delimiters, prefixes, suffixes, uppercase, and parsing hex.
- [Java SE 17 API — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `readString`, `readAllBytes`, `writeString`, streams, and file operations.
- [Java SE 17 API — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html): standard charsets such as UTF-8 and UTF-16.
- [Java SE 17 API — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): representing and manipulating file paths.

When converting data to hex, determine clearly whether you need to represent the **original file bytes** or the UTF-8 bytes encoded from decoded text. For small files, `Files.readAllBytes` combined with `HexFormat` and `Files.writeString` is concise and clear. For large files, read in chunks and stream directly through a writer to keep memory usage constant. Always specify a charset when handling text, avoid unintended content normalization, and verify the output file after writing.

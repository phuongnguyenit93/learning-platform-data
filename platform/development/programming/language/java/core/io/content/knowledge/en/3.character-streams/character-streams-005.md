# OutputStreamWriter: the bridge from characters to byte streams in Java

`OutputStreamWriter` in `java.io` is **the bridge between the character-writing API (`Writer`) and the byte-writing API (`OutputStream`)**. When a program writes text using `write(...)`, this object uses a **charset** to encode characters into a sequence of bytes, then passes those bytes down to the destination stream. It is an essential component when writing Vietnamese text, Unicode, line-oriented data, or text-based protocols over files, memory, or sockets.

Goal: understand accurately the conversion direction, the role of the charset, how to combine `OutputStreamWriter` with `OutputStream`/`BufferedWriter`, the meaning of `flush()`/`close()`, and the bugs that cause written text to be corrupted.

## 1. How does the bridge work?

Diagram:

```text
String / char[] / Java characters
       |
       | Writer.write(...)
       v
+-------------------------+
| OutputStreamWriter      |
| CharsetEncoder          |  UTF-8, UTF-16, US-ASCII, ...
| UTF-16 chars -> bytes   |
+-------------------------+
       |
       | encoded bytes
       v
OutputStream (FileOutputStream / ByteArrayOutputStream / Socket OutputStream...)
       |
       v
File, byte array, network, or another byte destination
```

Java stores the contents of a `String` as **UTF-16 code units** (`char` is a 16-bit unit); characters outside the Basic Multilingual Plane, such as the emoji `😀`, use a **surrogate pair** (two `char`s). `OutputStreamWriter` receives this sequence of characters, processes it with the chosen encoder, and emits bytes according to the charset. Therefore, **the number of `char`s is not necessarily equal to the number of Unicode characters, nor is it equal to the number of bytes**.

Example:

| Content | UTF-16 `char` units | UTF-8 bytes |
| --- | ---: | ---: |
| `A` | 1 | 1 |
| `é` | 1 | 2 |
| `中` | 1 | 3 |
| `😀` | 2 | 4 |
| Newline character `\n` | 1 | 1 |

If writing `"Aé中😀\n"` in UTF-8, this string has **6 `char` units, 5 Unicode code points, and 11 UTF-8 bytes**. You should not use `String.length()` to predict how many bytes will be stored or sent over the network.

`OutputStreamWriter` only **encodes characters into bytes**. The reverse direction, reading bytes into characters, is the job of `InputStreamReader`.

## 2. Building a character-writing pipeline

Basic example:

```java
OutputStream destination = new FileOutputStream("message.txt");
Writer writer = new OutputStreamWriter(destination, StandardCharsets.UTF_8);
writer.write("Xin chào, Java!");
writer.close();
```

This is an **illustrative snippet**; you need to import `java.io.*`, `java.nio.charset.StandardCharsets`, and handle `IOException`. When run, `FileOutputStream` receives bytes; `OutputStreamWriter` is responsible for converting characters to UTF-8. After `close()`, the write stream has ended.

In real code, use `try-with-resources` to close resources even when an exception occurs:

```java
try (Writer writer = new OutputStreamWriter(
        new FileOutputStream("message.txt"), StandardCharsets.UTF_8)) {
    writer.write("Xin chào, Java!");
}
```

`try-with-resources` automatically calls `close()` on `writer`. When closing, `OutputStreamWriter` finalizes the encoding stream, flushes any remaining data, and **closes the underlying `OutputStream`**. Therefore, you do not need to close `FileOutputStream` separately once ownership has been handed over to the writer. If you receive an `OutputStream` managed elsewhere, you must agree on who has the right to close it before creating the writer.

## 3. Choosing a charset explicitly

Constructors worth knowing:

```java
new OutputStreamWriter(outputStream)
new OutputStreamWriter(outputStream, StandardCharsets.UTF_8)
new OutputStreamWriter(outputStream, "UTF-8")
new OutputStreamWriter(outputStream, charsetEncoder)
```

- `OutputStreamWriter(OutputStream)` uses the **default charset** of the runtime environment. You should not rely on it for file formats, inter-system communication, or results that must remain consistent across machines. Java 17 may have a platform/configuration-dependent default charset; other versions and configurations also affect default behavior.
- `OutputStreamWriter(OutputStream, Charset)` selects a specific charset. `StandardCharsets.UTF_8` is usually preferred to avoid typos in charset names and ensure consistency.
- `OutputStreamWriter(OutputStream, String)` accepts a charset name; an unsupported name can cause an `UnsupportedEncodingException` at construction time.
- `OutputStreamWriter(OutputStream, CharsetEncoder)` allows controlling the policy for handling unmappable characters or malformed UTF-16 input.

A charset **is not a property of the `String` data type**, nor is it an attribute automatically attached to an arbitrary `OutputStream`. The writer and reader must agree on the byte format. Writing with UTF-8 while the reading side decodes with a different charset can produce garbled text (*mojibake*) or replacement characters.

Reading back with the matching UTF-8 charset:

```java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
String restored = new String(bytes, StandardCharsets.UTF_8);
```

The snippet above illustrates an encode/decode pair when all data is already available in memory; when you need to write **as a stream**, `OutputStreamWriter` provides `write(...)` operations without requiring you to build the entire byte array upfront. Conversely, `InputStreamReader` can be used when data is read as a stream.

## 4. Important operations on OutputStreamWriter

| Operation | Meaning |
| --- | --- |
| `write(int c)` | Writes a single **character unit**; the `int` parameter does not mean an arbitrary Unicode code point |
| `write(char[] chars, int offset, int length)` | Writes a slice of a `char` array, with length measured in `char`s |
| `write(String text, int offset, int length)` | Writes a slice of a `String` indexed by UTF-16 code units |
| `write(String text)` | Convenience method inherited from `Writer` to write an entire string |
| `append(...)` | Appends a string/character via the `Appendable` interface |
| `flush()` | Pushes buffered encoded bytes and requests the underlying stream to flush |
| `close()` | Finalizes and closes the writer, also closing the destination stream |
| `getEncoding()` | Returns the encoding name (may be a historical name); may return `null` after being closed |

The variants with `offset` and `length` validate array or string bounds and throw an error if the range is invalid. `Writer.write(int)` writes a single `char`, so **do not** pass a raw Unicode code point like `0x1F600` expecting it to be automatically converted into a surrogate pair. To write an emoji, use `write("😀")` or:

```java
writer.write(Character.toChars(0x1F600));
```

This is a code snippet, where `writer` is an open `Writer` and the calling method handles `IOException`. `Character.toChars(...)` returns the `char` pair needed for a code point outside the BMP.

Also avoid accidentally splitting a surrogate pair in half when slicing a `String` by `offset`/`length`. When data is assembled across multiple write calls, the encoder may have to retain state for an incomplete character; do not rely on a single `write` always corresponding to a ready number of bytes underneath.

## 5. Complete Java 17+ example: from Unicode to UTF-8 bytes

Create the file `OutputStreamWriterDemo.java`:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class OutputStreamWriterDemo {
    public static void main(String[] args) throws IOException {
        String text = "Aé中😀\n";
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (OutputStreamWriter writer =
                     new OutputStreamWriter(destination, StandardCharsets.UTF_8)) {
            writer.write(text);
            writer.flush();
            System.out.println("Bytes after flush: " + destination.size());
        }

        byte[] result = destination.toByteArray();
        System.out.println("UTF-16 code units: " + text.length());
        System.out.println("Unicode code points: "
                + text.codePointCount(0, text.length()));
        System.out.println("UTF-8 bytes: " + result.length);
        System.out.println("Hex: "
                + HexFormat.ofDelimiter(" ").withUpperCase().formatHex(result));
        System.out.println("Round trip: "
                + text.equals(new String(result, StandardCharsets.UTF_8)));
    }
}
```

Compile/run with JDK 17+:

```bash
javac OutputStreamWriterDemo.java
java OutputStreamWriterDemo
```

Exact stdout:

```text
Bytes after flush: 11
UTF-16 code units: 6
Unicode code points: 5
UTF-8 bytes: 11
Hex: 41 C3 A9 E4 B8 AD F0 9F 98 80 0A
Round trip: true
```

Explanation:

1. `ByteArrayOutputStream` is an in-memory byte destination; it makes it easy to inspect bytes without depending on the filesystem.
2. `writer.write(text)` feeds the UTF-16 code units to the UTF-8 encoder. `writer.flush()` pushes the encoded bytes to the destination, so `destination.size()` returns **11** right at the moment of inspection.
3. `HexFormat` (available in Java 17) prints each byte in hexadecimal: `41` for `A`, `C3 A9` for `é`, `E4 B8 AD` for `中`, `F0 9F 98 80` for the emoji, and `0A` for `\n`.
4. `new String(result, UTF_8)` decodes with the matching charset, restoring the original string accurately; the comparison evaluates to `true`.
5. `close()` called by `try-with-resources` also closes the writer and the byte destination. `ByteArrayOutputStream` allows calling `toByteArray()` after being closed, unlike many real I/O destinations.

This example demonstrates **encoding**, without depending on whether the console renders emojis properly: the result is verified via hex and a boolean, running consistently on JDK 17+.

## 6. OutputStreamWriter, BufferedWriter, and OutputStream: separation of responsibilities

When writing many small chunks in practice, three classes are commonly used:

```text
Application calls write("...")
        |
        v
BufferedWriter            buffers characters; supports newLine()
        |
        v
OutputStreamWriter        encodes characters as UTF-8 into bytes
        |
        v
FileOutputStream          writes bytes to the file
```

`OutputStreamWriter` has a buffer for **encoded bytes**, but it does not maintain a large character buffer to coalesce small `write` calls. The Java documentation recommends wrapping it in a `BufferedWriter` when better performance is needed: batching characters before invoking the encoder can reduce the number of conversion calls.

Example of writing a text file:

```java
import java.io.BufferedWriter;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class WriteTextFile {
    public static void main(String[] args) throws Exception {
        Path path = Path.of("message.txt");

        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(
                        Files.newOutputStream(path),
                        StandardCharsets.UTF_8))) {
            writer.write("Dòng đầu");
            writer.newLine();
            writer.write("Dòng thứ hai");
        }
    }
}
```

Run:

```bash
javac WriteTextFile.java
java WriteTextFile
```

The result is a `message.txt` file in the working directory containing two UTF-8 lines. `Files.newOutputStream(path)` with default options creates the file if it does not exist and **truncates the existing content** if the file already exists. `BufferedWriter.newLine()` writes the **platform line separator** (for example `\r\n` on some systems, `\n` on others). If a format/protocol strictly requires LF, use `writer.write("\n")` instead of `newLine()`.

When closing `BufferedWriter`, the close chain follows the wrappers: flush characters, finalize encoding, then close `OutputStream`. For configuration files, JSON Lines, text exchanged over HTTP, or logs with explicit charset requirements, the charset and line-ending rules must be specified where the format is designed.

### Appending to the end of a file instead of overwriting

If you genuinely need to append, open the byte destination with `StandardOpenOption.APPEND`:

```java
Path path = Path.of("message.txt");
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(
                Files.newOutputStream(path,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND),
                StandardCharsets.UTF_8))) {
    writer.write("Một dòng được nối tiếp\n");
}
```

This is a **code snippet**; you need to import `java.io.*`, `java.nio.file.*`, `java.nio.charset.StandardCharsets`, and handle `IOException`. When appending, a newline character is not automatically inserted between old and new content; you must manage record boundaries yourself. If multiple processes/threads write to the same file concurrently, append mode alone is not enough to guarantee that each multi-operation record remains intact without interleaving.

## 7. Flush, close, and when bytes appear

### `write(...)` does not mean "bytes are durably on disk"

`OutputStreamWriter` may accumulate encoded bytes in an internal buffer. If there is an outer `BufferedWriter`, characters may also sit in the character buffer. Therefore, returning from `write(...)` does not guarantee that all bytes have been pushed to the destination.

- `writer.flush()` requests pushing the relevant buffers down to `OutputStream` and invokes flush on the underlying stream. It helps the receiver observe bytes sooner when the stream/transport structure supports it.
- `writer.close()` completes the encoding sequence, flushes any remainder, and closes the underlying layers. Use it when finishing with the resource.
- `flush()` **does not** mean the data has been durably synced to the storage device (*fsync*) or acknowledged by the remote system. Durability/ACK requires separate file/network/protocol mechanisms.
- `flush()` does not close the stream. You can continue writing after `flush()`, whereas after `close()` you cannot.

If wrapped in an outer `BufferedWriter`, call `flush()` on the **outermost writer** to ensure both the character buffer and the downstream pipeline are flushed. Avoid calling flush directly only on the inner `OutputStream` while `BufferedWriter` still holds unforwarded characters.

For stateful encodings or data ending with half of a surrogate pair, **ending the stream** via `close()` may perform a final processing step that differs from an intermediate `flush()`. Always close the writer when finished writing; do not treat `flush()` as a full substitute for `close()`.

### Resource ownership

A wrapper is part of the resource-closing chain. For example:

```java
try (Writer writer =
        new OutputStreamWriter(System.out, StandardCharsets.UTF_8)) {
    writer.write("Hello\n");
}
```

**Do not** use the pattern above if the program still needs to print to `System.out` after the `try` block: closing the writer can close standard output that the rest of the application still relies on. For `System.out` or a socket stream owned by another component, only close it if the current code owns the stream's lifecycle. Otherwise, coordinate the ownership contract or simply call `flush()` at the appropriate point.

## 8. Unmappable characters and malformed Unicode data

Not every charset can represent all of Unicode. `US_ASCII` only represents characters within the ASCII range. For instance, the string `"café"` contains the character `é`, which cannot be encoded directly with `US_ASCII`.

When creating an `OutputStreamWriter` with a regular charset, by default the class **replaces** unmappable character sequences or invalid surrogates with the charset's replacement byte sequence. This can cause data loss without necessarily throwing an exception.

If the data format requires **no character loss**, use a `CharsetEncoder` configured with the `REPORT` action:

```java
CharsetEncoder encoder = StandardCharsets.US_ASCII.newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT);

try (Writer writer = new OutputStreamWriter(
        new ByteArrayOutputStream(), encoder)) {
    writer.write("café");
} catch (CharacterCodingException e) {
    // Character cannot be represented in US-ASCII;
    // handle the error at the business layer instead of accepting data loss.
}
```

This is an **illustrative code snippet**; you need to import `java.io.*`, `java.nio.charset.*`. `CharacterCodingException` is a subclass of `IOException`. The error may surface during writing, flushing, or closing, depending on buffering and encoder state. If you replace `REPORT` with `REPLACE` or `IGNORE`, the application is accepting character replacement/dropping — that should be an intentional decision.

In most modern Vietnamese and Unicode text scenarios, **UTF-8** is the practical choice, widely compatible and capable of representing all valid Unicode. However, even with UTF-8, a `String` containing an unpaired surrogate is still invalid UTF-16; the replacement or error-reporting rules still need to be understood.

## 9. Practical scenario: writing text to a socket

Suppose a text protocol uses **UTF-8**, with each message terminated by an LF byte (`0A`):

```java
OutputStream socketBytes = socket.getOutputStream();
Writer writer = new BufferedWriter(
        new OutputStreamWriter(socketBytes, StandardCharsets.UTF_8));

writer.write("HELLO Xin chào\n");
writer.flush();
```

This is a code snippet: `socket` is already connected; handle `IOException` and manage closing the socket at the owning layer. The application must agree with the receiving end that messages use UTF-8 and are delimited by LF. `flush()` helps push buffered data so the receiver can process it, but **does not confirm** that the remote peer has received or finished processing it.

If sending a **binary protocol** mixing length headers, checksums, and text payloads, byte order and boundaries must be clearly defined. For example, payload length must be declared as the **number of UTF-8 bytes** (`payload.getBytes(UTF_8).length`), not `payload.length()`. If encoded into a byte buffer first, this byte count is exact; if streaming incrementally, design how to transmit the length or framing mechanism before sending.

Do not write concurrently through `OutputStreamWriter` and directly to the same `OutputStream` while buffered characters/bytes remain unflushed: the actual order may differ from the call order across the two wrapper layers. Establish a single pipeline owner or clear synchronization/flush/close rules. For HTTP, JSON, or protocols with dedicated serializers, prefer the appropriate serializer API/library if it provides complete escaping, charset, and framing rules.

## 10. Distinguishing from related APIs

| API | Unit of processing | When it fits best |
| --- | --- | --- |
| `OutputStream` / `FileOutputStream` | Byte | Writing binary bytes or pre-encoded bytes |
| `OutputStreamWriter` | Accepts characters, encodes to bytes | Writing text with a specific charset to any `OutputStream` |
| `BufferedWriter` | Characters, with a character buffer | Many small writes, line-by-line writing, wrapping a `Writer` |
| `InputStreamReader` | Accepts bytes, decodes to characters | Reading text from an `InputStream` using a charset |
| `String.getBytes(charset)` | Encodes the entire string into `byte[]` | When the whole string is already in memory and a byte array is needed |
| `Files.newBufferedWriter(path, charset)` | Convenience `Writer` for files | Writing text to a file without manually managing stream layers |

`FileWriter` is a subclass of `OutputStreamWriter` convenient for files; Java 17 also provides constructors that accept a `Charset`. `OutputStreamWriter` is worth learning because it clearly shows the character ↔ byte conversion model and applies to destinations beyond files.

A modern file example can be concise:

```java
try (BufferedWriter writer = Files.newBufferedWriter(
        Path.of("message.txt"), StandardCharsets.UTF_8)) {
    writer.write("Xin chào");
}
```

This illustrative snippet requires importing `java.nio.file.*`, `java.nio.charset.StandardCharsets`, `java.io.BufferedWriter`, and handling `IOException`. The abstraction remains the same as above: work with characters, and ultimately write bytes using a charset.

## 11. Common mistakes and how to prevent them

| Mistake | Consequence | Correct practice |
| --- | --- | --- |
| Not specifying a charset | Output changes when the default environment differs | Pass `StandardCharsets.UTF_8` or the charset specified by the protocol |
| Writing UTF-8 but decoding with another charset | Corrupted diacritics, replacement characters | Write and read using the same charset and agree on the format |
| Assuming `String.length()` is the byte count | Wrong message length, truncated Unicode data | Encode to bytes first and count, or compute size with the proper encoder |
| Calling `write(...)` then immediately reading the file/destination without flush/close | May not see all bytes yet | Call `flush()` when needed, and `close()` when finished |
| Closing a writer wrapping `System.out`/a socket owned elsewhere | Other components can no longer write | Design clear ownership; only close when owning the destination |
| Using `write(int)` for an emoji code point | Truncated to a single `char` unit | Use `write(String)` or `Character.toChars(...)` |
| Reading and writing text on the same stream while ignoring charset | Transmitted data is corrupted or loses characters | Pair `InputStreamReader`/`OutputStreamWriter` with a consistent charset |
| Assuming `flush()` means the file is durable/the receiver has ACKed | False conclusion about write state | Use `FileDescriptor.sync`/`FileChannel.force` or protocol ACKs when truly needed |
| Using `newLine()` in a format that strictly requires LF | Line-ending bytes differ across operating systems | Use `write("\n")` when the protocol mandates LF |
| Expecting every unmappable character to throw an exception | May be silently replaced with other bytes, losing data | Use `CharsetEncoder` with `CodingErrorAction.REPORT` |

## 12. Self-check questions

1. **Which direction does OutputStreamWriter go?** From Java characters (`Writer`) to bytes (`OutputStream`), using the chosen charset.
2. **Why can't the UTF-8 output size be obtained from `String.length()`?** Because each Unicode code point can take 1–4 bytes in UTF-8, whereas a Java `char` is a UTF-16 unit.
3. **Why wrap `BufferedWriter` around `OutputStreamWriter`?** To batch small character writes before encoding, reducing repeated conversion calls.
4. **Does `flush()` close the writer or guarantee a network ACK?** No. `flush()` pushes the relevant buffers, but it neither closes the stream nor confirms receipt by the remote peer.
5. **How does `close()` on OutputStreamWriter affect the OutputStream?** The writer finalizes and closes the underlying byte stream, so ownership must be clear.
6. **What happens when a charset cannot represent a character?** By default the writer may replace it; if an error should be reported, use `CharsetEncoder` with `REPORT`.
7. **How many bytes does writing `"Aé中😀\n"` in UTF-8 produce?** 11 bytes; the string's `String.length()` is 6.
8. **If a message requires LF (`0A`), should you use `newLine()`?** No, not when exact bytes are required; use `write("\n")`.

## Official API references

- [Java 17 — OutputStreamWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStreamWriter.html).
- [Java 17 — BufferedWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html).
- [Java 17 — CharsetEncoder and CodingErrorAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetEncoder.html).
- [Java 17 — StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html).
- [Java 17 — HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html).

**Key takeaway:** `OutputStreamWriter` is not simply "writing a String to a file." It is a stateful encoding layer sitting between the character API and the byte API. Choosing the charset, using buffering, managing flush/close, and stream ownership determine whether text is accurate, complete, and delivered to its intended destination.
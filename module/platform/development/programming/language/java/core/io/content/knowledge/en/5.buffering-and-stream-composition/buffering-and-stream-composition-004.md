# Composition Order of Streams, Buffers, Charsets, and Formats in Java I/O

## 1. Thinking in Data Flow: Bytes → Characters → Structure

In Java I/O, multiple classes can **wrap** the same source/destination so each class takes on one responsibility. For text data, four concerns need to be distinguished:

1. **Byte stream:** connects to a physical or logical source/destination, such as `FileInputStream`, `FileOutputStream`, `Files.newInputStream`, or `ByteArrayInputStream`.
2. **Buffer:** reduces calls to the underlying layer by reading/writing in blocks, such as `BufferedInputStream`, `BufferedOutputStream`, `BufferedReader`, or `BufferedWriter`.
3. **Charset:** converts between **bytes** and **characters**, such as `InputStreamReader` and `OutputStreamWriter` with `StandardCharsets.UTF_8`.
4. **Format:** conventions that turn values and records into text or binary data: one line per record, CSV, JSON, or `DataOutputStream` with a specific binary protocol.

**Core rule:** Compose classes according to the **data types each class accepts and returns**, then verify the file/protocol format specification. Never swap classes arbitrarily just because they all have "stream" or "buffer" in their names.

Simple text-reading diagram:

```text
Byte source (file/network)
    ↓  byte
[BufferedInputStream]       (optional: byte buffer)
    ↓  byte
InputStreamReader(UTF-8)     (decode byte → char)
    ↓  char
BufferedReader              (optional: char buffer, readLine)
    ↓  String
Format parser               (parse lines, CSV, JSON...)
    ↓
Domain values
```

The text-writing diagram runs in the opposite direction in terms of **data-processing semantics**:

```text
Domain values
    ↓
Format generator             (CSV, JSON, text lines...)
    ↓  String / char
BufferedWriter               (optional: char buffer)
    ↓  char
OutputStreamWriter(UTF-8)     (encode char → byte)
    ↓  byte
[BufferedOutputStream]       (optional: byte buffer)
    ↓  byte
Byte destination (file/network)
```

Square brackets denote optional layers. The diagrams depict **how data flows**; actual Java code is typically constructed from the **innermost layer (source/destination) outward to the outermost layer (the API the application calls)**.

## 2. Composing Layers by Java Type

| Group | Class Input/Output | Role |
| --- | --- | --- |
| `InputStream` / `OutputStream` | `byte`, `byte[]` | Byte I/O foundation |
| `BufferedInputStream` / `BufferedOutputStream` | `InputStream` / `OutputStream` | Wraps a byte stream and adds a byte buffer |
| `Reader` / `Writer` | `char`, `char[]`, `String` | Character I/O foundation |
| `InputStreamReader` | Wraps an `InputStream` | Decodes bytes into characters using a charset |
| `OutputStreamWriter` | Wraps an `OutputStream` | Encodes characters into bytes using a charset |
| `BufferedReader` / `BufferedWriter` | Wraps `Reader` / `Writer` | Adds a character buffer, `readLine()` / `newLine()` |
| `PrintWriter` | Wraps `Writer` or `OutputStream` | `print`, `println`, `printf` for formatted text output |
| `DataInputStream` / `DataOutputStream` | Wraps a byte stream | Reads/writes primitive types in a defined **binary format** |

Type-correct examples:

```java
// input is an already opened InputStream:
Reader decoder = new InputStreamReader(input, StandardCharsets.UTF_8);
BufferedReader lines = new BufferedReader(decoder);

// output is an already opened OutputStream:
Writer encoder = new OutputStreamWriter(output, StandardCharsets.UTF_8);
BufferedWriter text = new BufferedWriter(encoder);
```

The snippet above **only illustrates how to compose layers**; `input`/`output` must be declared and opened in the enclosing context. In real code, manage stream closing with `try-with-resources`, as in the complete example below.

Examples that are wrong in type or semantics:

- `new BufferedReader(input)` **will not compile**, because `BufferedReader` requires a `Reader` rather than taking an `InputStream` directly. You need an `InputStreamReader` as a bridge.
- `new BufferedInputStream(reader)` also fails to compile, because a byte buffer does not accept a `Reader`.
- Calling `readLine()` on an `InputStream` makes no sense; that is a character-processing API on `BufferedReader`.
- Taking UTF-8 bytes and casting each byte to `char` is not UTF-8 decoding; a Unicode character can require multiple bytes.

## 3. Composing a Read Chain in the Right Order

Starting from a byte source:

```java
BufferedReader reader = new BufferedReader(
        new InputStreamReader(
                new BufferedInputStream(input),
                StandardCharsets.UTF_8));
```

Actual processing flow:

1. `BufferedInputStream` fetches bytes from `input` in blocks.
2. `InputStreamReader` **decodes UTF-8**, properly handling multi-byte characters split across read boundaries.
3. `BufferedReader` holds characters in a buffer and provides `readLine()`.
4. The application receives `String` values to process according to the agreed format.

**You do not always need both buffers.** `InputStreamReader`/decoders and I/O classes have their own data-management buffers; `BufferedReader` is often sufficient for line-by-line reading. Adding `BufferedInputStream` purely because "more buffers means faster" can increase memory and complexity without improving speed. Choose buffers based on access patterns, the I/O source, and real measurements.

If the file contains binary data rather than text, do not use a `Reader` just to take advantage of `readLine()`. Choose a byte API or an appropriate binary parser.

## 4. Composing a Write Chain in the Right Order

Starting from a byte destination:

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(
                new BufferedOutputStream(output),
                StandardCharsets.UTF_8));
```

When the application calls `writer.write(...)`:

1. `BufferedWriter` may hold characters in its buffer.
2. `OutputStreamWriter` converts characters into bytes using UTF-8.
3. `BufferedOutputStream` may hold bytes in its buffer.
4. `output` writes bytes to the destination when data is pushed down.

The outermost layer determines the API the application uses: `write(String)` and `newLine()` on `BufferedWriter`. The application does not need to compute UTF-8 bytes manually. For a protocol requiring UTF-8, the charset must be specified on **both the write side and the read side**; a buffer cannot fix a mismatched charset.

To write a small document or an ordinary file, a **simpler** variant is also reasonable:

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8));
```

Or when working with files via `Path`:

```java
BufferedReader reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
BufferedWriter writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8);
```

These lines are **illustrative snippets** requiring `path` to be declared, `java.nio.file.Files` and `java.nio.file.Path` imported, and `IOException` handled. By default, `Files.newBufferedWriter` can **create or overwrite file contents**; do not run it carelessly on files you need to preserve. These `Files` APIs save you from manual wiring when you do not need direct control over the lower byte stream.

## 5. Runnable Java 17+ Example: Byte Buffer, Charset, and Line Formatting

This program uses an in-memory byte array to avoid touching real files. Create **`LayeredTextDemo.java`**:

```java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class LayeredTextDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(
                        new BufferedOutputStream(sink),
                        StandardCharsets.UTF_8))) {
            writer.write("Tên,điểm");
            writer.newLine();
            writer.write(String.format(Locale.ROOT, "%s,%.2f", "An", 7.5));
            writer.newLine();
            writer.write(String.format(Locale.ROOT, "%s,%.2f", "Bình", 8.0));
            writer.newLine();
        }

        byte[] bytes = sink.toByteArray();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new BufferedInputStream(new ByteArrayInputStream(bytes)),
                        StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                System.out.println("Dòng: " + line);
            }
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 LayeredTextDemo.java
java LayeredTextDemo
```

Output:

```text
Dòng: Tên,điểm
Dòng: An,7.50
Dòng: Bình,8.00
```

Points to observe:

- Values `7.5`/`8.0` become `7.50`/`8.00` at the **formatting step** `String.format(Locale.ROOT, "%.2f", ...)`. `Locale.ROOT` ensures the decimal separator is a dot; the charset does not choose decimal separators.
- `StandardCharsets.UTF_8` determines the **bytes of accented words** such as `Tên`, `điểm`, and `Bình`, but does not determine column names or comma conventions.
- `writer.newLine()` emits the platform's line ending. `reader.readLine()` recognizes standard line-ending styles and returns content without the line terminator, keeping console output consistent.
- `try-with-resources` closes the outermost `BufferedWriter`, pushing data through `OutputStreamWriter` and `BufferedOutputStream` down to `sink` before `toByteArray()` is called. If you grab bytes too early, data still sitting in buffers may not have appeared yet.
- `ByteArrayOutputStream` still allows copying out the written contents even after an upper wrapper closes it.

The code uses simple CSV-like syntax to illustrate **layer order**. This is not a complete CSV serializer/parser: if values contain commas, quotes, or newlines, you must follow CSV escaping/quoting rules, typically via a dedicated CSV library. A naive `line.split(",")` is not enough for those cases.

## 6. Where Does "Format" Sit in the Chain?

Choose the **format** before deciding which API to call for encoding or decoding.

### Structured Text

The format defines the **syntax of records and values**:

- CSV: field delimiters, quoting commas, escaping double quotes, lines, and headers.
- JSON: objects, arrays, strings, escapes, and boolean/number values per the JSON specification.
- Line-oriented records: each line is one record if the application defines it that way; do not assume every text file follows this structure.
- Logs: timestamps, levels, messages, newline conventions; date/time and number formatting must be chosen independently of the charset.

In these cases, the **serializer/parser** runs at the character or byte level per the format library, while the **charset** handles converting between characters and bytes. For example, JSON over a UTF-8 protocol: the serializer produces UTF-8 bytes (or writes characters through an appropriate `Writer`); you cannot turn a JSON parser into `BufferedReader` merely by adding a buffer.

### `PrintWriter` and `printf`

`PrintWriter` is convenient for presentation formatting with `print`, `println`, and `printf`. A commonly seen setup:

```java
PrintWriter out = new PrintWriter(
        new BufferedWriter(
                new OutputStreamWriter(output, StandardCharsets.UTF_8)));

out.printf(Locale.ROOT, "total=%.2f%n", 12.5);
out.flush();
```

This is **illustrative code**, where `output` is an already opened `OutputStream` whose lifecycle is managed by the caller. `printf` handles **how numbers and strings are formatted**, `OutputStreamWriter` handles the **charset**, and `BufferedWriter` handles **buffering**. `PrintWriter` typically **does not throw `IOException` from print/write/printf operations**, instead recording an internal error flag; when output reliability matters, call `checkError()` or choose a `Writer`/API that propagates errors directly. When using `try-with-resources` with a `PrintWriter` that owns the stream, close only the outermost layer.

`%n` is the platform-dependent line separator, unlike a fixed `\n`. For file formats with a strict specification for CRLF/LF, write the exact terminator explicitly rather than relying on the OS.

### Custom Binary Data Formats

A binary format might define a 4-byte `int`, an 8-byte `long`, a length followed by payload bytes, a checksum, etc. `DataOutputStream`/`DataInputStream` operate directly on bytes:

```java
DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(output));
out.writeInt(42);
out.writeUTF("Xin chào");
out.flush();
```

This is **illustrative code** requiring an opened `output`, imports for `java.io.DataOutputStream`/`java.io.BufferedOutputStream`, and proper closing/exception handling. The matching read side must call `DataInputStream.readInt()` before `readUTF()`, in the exact **field order** written. `writeUTF` uses **`DataOutputStream`'s modified UTF-8**, which differs from standard UTF-8 in certain cases (such as NUL characters and surrogates); do not replace it with `new String(bytes, UTF_8)` or `InputStreamReader(UTF_8)` unless you replicate the exact byte layout.

Here **there is no step passing a text document through `OutputStreamWriter`**. Trying to apply a charset/`Reader` across the whole byte stream of a binary format will corrupt the data. Choose the text or binary branch based on the actual format specification.

## 7. When Compression, Encryption, or Other Byte Transforms Exist

Byte-transforming layers (such as `GZIPInputStream`/`GZIPOutputStream`) operate on **compressed bytes**, and cannot accept characters directly. Thus for GZIP-compressed UTF-8 text:

```text
WRITE: String → Writer produces chars → UTF-8 bytes → GZIP bytes → destination
READ:  GZIP byte source → decompress → UTF-8 bytes → Reader → String
```

Standalone Java 17+ example **`GzipTextPipelineDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class GzipTextPipelineDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (BufferedWriter writer = new BufferedWriter(
                new OutputStreamWriter(
                        new GZIPOutputStream(destination),
                        StandardCharsets.UTF_8))) {
            writer.write("Café");
            writer.newLine();
        }

        byte[] compressed = destination.toByteArray();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                        new GZIPInputStream(
                                new ByteArrayInputStream(compressed)),
                        StandardCharsets.UTF_8))) {
            System.out.println(reader.readLine());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 GzipTextPipelineDemo.java
java GzipTextPipelineDemo
```

Output:

```text
Café
```

**Key point:** `GZIPOutputStream` requires `finish()` or `close()` to write the full GZIP trailer/checksum. Closing the outermost `BufferedWriter` cascades the close down to GZIP before `destination.toByteArray()` is called. If you reverse the order and try feeding raw GZIP bytes straight into `InputStreamReader`, the UTF-8 decoder will read compressed bytes as text and produce garbage.

When compression and cryptographic encryption coexist, the layer order must follow the **protocol specification**: for example, a protocol may require compressing first and then encrypting on write, and decrypting first and then decompressing on read. Do not swap them casually because transformations are not generally commutative. Any buffer layer must also be placed where it does not break message boundaries or protocol flush semantics.

## 8. Speed, Buffer Sizes, and Read-Ahead Behavior

A **byte buffer** batches byte read/write calls; a **character buffer** batches character operations and adds conveniences like `readLine()`. Both buffers can coexist because they sit on opposite sides of the charset converter, though **adding both is not automatically beneficial**.

Common scenarios:

| Need | Typically Suitable Chain |
| --- | --- |
| Read UTF-8 lines from a file | `Files.newBufferedReader(path, UTF_8)` |
| Write UTF-8 lines to a file | `Files.newBufferedWriter(path, UTF_8)` |
| Read byte blocks from a file | `BufferedInputStream(Files.newInputStream(path))` or block reads directly from `InputStream` |
| Process text records from a socket | `BufferedReader(InputStreamReader(socket.getInputStream(), UTF_8))`, with protocol framing |
| Emit multi-field binary data | `DataOutputStream(BufferedOutputStream(output))` |
| Read GZIP-compressed text | `BufferedReader(InputStreamReader(GZIPInputStream(input), UTF_8))` |

Most Java examples above use UTF-8 as the explicit encoding. When a protocol/format mandates a different charset, apply that exact charset in both directions.

**Read-ahead has consequences:** `BufferedReader` and `InputStreamReader` can pull more bytes from the underlying byte stream than the characters the application has just requested. If you read a few lines with the wrapper and then go back to reading the raw `InputStream` directly, the actual read position may already be past where you think it is. Never mix direct raw-stream reads with a `BufferedReader` wrapping that stream; let **one outermost layer** manage reading, or use a framing/parser layer designed for switching between data types.

Larger buffer sizes are not always faster: it also depends on network/disk speed, access patterns, concurrent stream count, memory pressure, flush policy, and target throughput/latency. Only increase buffer sizes based on concrete measurements.

## 9. `flush()`, `close()`, and Stream Ownership

`BufferedWriter` may not push data out immediately upon `write`. Even after bytes pass `OutputStreamWriter`, `BufferedOutputStream` may still hold them. Therefore:

- **`flush()` on the outermost layer** requests pushing data through the wrapper chain down to the lower layers according to each layer's contract.
- **`close()` on the outermost layer** normally flushes pending data and then closes the wrapped layers underneath; `try-with-resources` is the standard way to ensure this happens.
- `flush()` **does not mean data is durably persisted on the device** (fsync) or processed by the receiver. If durability is required, use appropriate APIs and protocols, such as `FileChannel.force(...)` where applicable.
- For transforming streams with a finalization format, like GZIP, **flush may not be enough to complete the output**; `finish()` or `close()` is needed per the codec's contract.

Example:

```java
try (BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(output, StandardCharsets.UTF_8))) {
    writer.write("OK");
    writer.flush(); // push buffered data; for example, may be needed for an immediate response
}
```

This is **illustrative code**: `output` is an already opened stream owned by the wrapper. Do not close a wrapper if you need the underlying stream to stay open unless a separate lifecycle design manages it. Avoid closing individual layers multiple times without understanding ownership. For `System.out`, never put it into `try-with-resources` casually because closing it affects the entire application.

In interactive protocols, a buffered writer needs `flush()` at **the completion boundary of a message** if the peer is waiting; conversely, flushing after every character defeats buffering. `BufferedReader.readLine()` requires a line terminator or EOF to complete a line; if the writer has not sent a newline or flushed, the reader can wait indefinitely even though the app thinks it called `write`.

## 10. Common Composition Mistakes

| Mistake | Why It Happens | Right Approach |
| --- | --- | --- |
| `BufferedReader(InputStream)` | Type mismatch: reader needs a `Reader` | Add `InputStreamReader(input, charset)` |
| Creating `InputStreamReader` after reading arbitrary binary with `DataInputStream` | Protocol bytes may not be text | Use the parser/format specified by the protocol |
| Encoding Strings in UTF-8, reading with the default charset | Charsets do not match across both sides | Pass the same explicit charset |
| Splitting UTF-8 bytes by casting `(char)byte` | A character can span multiple bytes | Let a decoder handle byte boundaries |
| Mixing direct reads on the source with a `BufferedReader` wrapping it | Read-ahead advances the source position unpredictably | Use one consistent parser/wrapper chain |
| Reading GZIP bytes directly with `InputStreamReader` | Not decompressed yet | `GZIPInputStream` must decompress before decoding |
| Calling `toByteArray()` while the writer is still open | Content still sits in buffers | Flush/close at the right time; for GZIP, finish the trailer |
| Opening both a byte buffer and a char buffer for no reason | Adds overhead/memory, sometimes extra latency | Choose buffering by need and measure |
| `println` in a protocol requiring exact LF | Line break depends on the OS | Write the exact delimiter required by the protocol |
| Calling `String.split(",")` to parse arbitrary CSV | Fails to handle quoting/escaping | Use a compliant CSV parser |
| Trusting `PrintWriter` to always throw `IOException` directly | PrintWriter stores an internal error flag instead | Check `checkError()` or pick an error-throwing API |
| Calling `flush` and assuming data is safely on disk | Buffer flush ≠ filesystem durability | Use force/sync mechanisms when durability is required |

## 11. A Method for Designing an I/O Pipeline

For any read or write path, answer in order:

1. **What is the raw data source/sink?** File, socket, byte array, memory, or a stream already opened by another API?
2. **Is the logical data text or binary?** For binary, pick the binary format/protocol; for text, identify the actual encoding.
3. **Are there byte transformations?** Compression, decompression, encryption, checksums... Arrange them in the exact order specified by the format.
4. **At what level does the application operate?** Individual bytes, text lines, CSV records, JSON objects, binary integers?
5. **Where does a buffer add value?** For line reading, usually `BufferedReader`; for byte blocks, a byte buffer or array reads. Avoid redundant buffering.
6. **Who owns the source/destination and when does it finish?** Choose where to call `flush`, `finish`, or `close`; remember a writer may not have pushed data yet.
7. **Have you tested both directions?** Encode → decode, format → parse, EOF, Unicode data, invalid characters, missing final newline, and small buffer sizes.

**Practice exercise:** Design a pipeline that writes a GZIP file containing UTF-8 CSV, then reads it back line by line. On the write side, place the CSV generator at the outermost logical layer, then a UTF-8 writer, then `GZIPOutputStream`, and the byte file. On the read side, reverse the transformation path: byte file → `GZIPInputStream` → `InputStreamReader(UTF_8)` → `BufferedReader` → CSV parser. Explain why you cannot read GZIP bytes directly with `BufferedReader`, and why the gzip writer must be closed before taking the complete compressed output.

**Takeaway:** The right order follows from **type contracts** and **format specifications**: byte streams at the I/O core; byte buffers at the byte layer when needed; charset bridges strictly at the byte–character boundary; character buffers and formatters/parsers at the text layer; and byte compression/encryption placed at the exact positions defined by the protocol.
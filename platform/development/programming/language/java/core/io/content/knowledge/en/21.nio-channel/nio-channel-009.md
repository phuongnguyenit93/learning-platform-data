# `Channels.newReader`, `Channels.newWriter`, and Charset Conversion in Java NIO

## 1. Context: Channels Transport Bytes, Reader/Writer Handle Characters

`ReadableByteChannel` and `WritableByteChannel` operate on **bytes** via `ByteBuffer`, while `java.io.Reader` and `java.io.Writer` provide a **character** interface (`char`/Java strings). When the data is text, a **charset** conversion step is needed between the two layers:

```text
READ:
Source (file/socket/byte stream)
    → ReadableByteChannel: bytes
    → CharsetDecoder: bytes → Java Unicode characters
    → Reader: char / String

WRITE:
Writer: char / String
    → CharsetEncoder: Java characters → bytes
    → WritableByteChannel: bytes
    → Target (file/socket/byte stream)
```

`java.nio.channels.Channels` is the utility class bridging channel-style I/O with traditional stream/reader/writer APIs. Two method groups focused on in this lesson:

- `Channels.newReader(...)`: creates a `Reader` to **decode** bytes read from a `ReadableByteChannel` into characters.
- `Channels.newWriter(...)`: creates a `Writer` to **encode** characters into bytes and write them to a `WritableByteChannel`.

These adapters **do not turn a byte channel into an independent text-storage object**: they use the supplied channel, maintain their own conversion buffers, and share a lifecycle relationship with the channel. The “charset” determines which bytes represent which characters; choosing the wrong one can corrupt text even when channel reads/writes report no I/O error.

After this lesson, you should be able to pick the right overload, specify charsets explicitly, control decoding/encoding error handling, close resources properly, and understand the limits of pairing Reader/Writer with channels.

## 2. Exact Overloads in `java.nio.channels.Channels`

Java SE 17+ supports the following six key overloads:

| Read or Write | Signature | When to Use |
|---|---|---|
| Read | `newReader(ReadableByteChannel ch, String csName)` | Charset name as a string, e.g. `"UTF-8"` |
| Read | `newReader(ReadableByteChannel ch, Charset charset)` | Known `Charset`, commonly `StandardCharsets.UTF_8` |
| Read | `newReader(ReadableByteChannel ch, CharsetDecoder dec, int minBufferCap)` | Need custom error policy on decode or buffer allocation control |
| Write | `newWriter(WritableByteChannel ch, String csName)` | Charset name as a string |
| Write | `newWriter(WritableByteChannel ch, Charset charset)` | Explicit charset without custom encoder configuration |
| Write | `newWriter(WritableByteChannel ch, CharsetEncoder enc, int minBufferCap)` | Need custom error policy on encode or encoder configuration |

The overloads accepting `Charset` were introduced in Java 10, so they are available on Java 17+. With the `Charset` overloads:

```java
Reader reader = Channels.newReader(channel, StandardCharsets.UTF_8);
Writer writer = Channels.newWriter(channel, StandardCharsets.UTF_8);
```

*The two lines above are independent illustrations: `channel` on the first line must be a `ReadableByteChannel`; on the second line it must be a `WritableByteChannel`. They do not have to be the same object.* Each call creates an adapter over the given channel; it **does not open a file itself** and does not take a `Path`.

Behaviorally, those two overloads are equivalent to:

```java
Reader reader = Channels.newReader(
        readableChannel, StandardCharsets.UTF_8.newDecoder(), -1);

Writer writer = Channels.newWriter(
        writableChannel, StandardCharsets.UTF_8.newEncoder(), -1);
```

This is an illustrative snippet requiring appropriate channel variables and imports for `java.io.Reader`, `java.io.Writer`, `java.nio.channels.Channels`, and `java.nio.charset.StandardCharsets`. The `-1` argument means using an implementation-defined default buffer capacity.

With the `String csName` overload, Java must resolve the charset name, such as `"UTF-8"`. An invalid or unsupported name can throw `IllegalCharsetNameException` or `UnsupportedCharsetException`. Prefer `StandardCharsets.UTF_8`, `StandardCharsets.ISO_8859_1`, etc., when the charset is known at compile time to avoid typos, control environment behavior, and eliminate reliance on default charsets.

**There is no single-argument `Channels.newReader(channel)` or `Channels.newWriter(channel)` overload.** Specifying the charset is a mandatory part of this interface.

## 3. What Is Charset Conversion?

Java `String` and most character APIs store text in UTF-16 code units (`char` is a 16-bit code unit). A Unicode character can consist of one or two `char`s—for example, many emojis use a **surrogate pair**. Channels only transport bytes; a charset maps between valid sequences of code units and bytes.

Example for character `é` (`U+00E9`):

| Charset | Encoded Bytes for `é` (hex) | Byte Count |
|---|---|---|
| UTF-8 | `C3 A9` | 2 |
| ISO-8859-1 | `E9` | 1 |
| UTF-16BE | `00 E9` | 2 |

The exact same bytes decoded with a different charset can produce different text:

```text
Actual bytes (UTF-8): C3 A9
Decoded as UTF-8:       é
Decoded as ISO-8859-1:  Ã©
```

When you choose the wrong charset yet every byte happens to be valid in the target charset, the result is **mojibake** (garbled display text) rather than necessarily an exception. Thus, `Reader.read()` succeeding without error does not prove you chose the right charset.

Conversely, the byte sequence `C3 28` is not valid UTF-8: after lead byte `C3`, a continuation byte is required, yet `28` is not a continuation byte. When `CharsetDecoder` is in `REPORT` mode, reading can throw `MalformedInputException`.

The write direction has another error mode: some characters have no representation in the target charset. For instance, `☕` (`U+2615`) cannot be encoded in ISO-8859-1; the encoder reports an **unmappable character** error when configured with `REPORT`.

## 4. Using `newReader` to Read Text from a Channel

Example reading a UTF-8 file via a channel:

```java
import java.io.Reader;
import java.nio.channels.Channels;
import java.nio.channels.ReadableByteChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

Path path = Path.of("notes.txt");

try (ReadableByteChannel channel = Files.newByteChannel(path);
     Reader reader = Channels.newReader(
             channel, StandardCharsets.UTF_8)) {

    char[] chars = new char[1024];
    int count;
    while ((count = reader.read(chars)) != -1) {
        System.out.print(new String(chars, 0, count));
    }
}
```

This is an **illustrative snippet inside a method declaring `throws IOException`**, not a standalone Java file with `main`. `Files.newByteChannel(path)` opens the channel for reading; `newReader` decodes with UTF-8; `reader.read(chars)` returns the actual number of `char`s read, or `-1` at EOF.

Notes:

- `reader.read(chars)` operates on a **`char` buffer**; a single read does not correspond 1:1 to a byte or to a complete Unicode code point.
- A single read may return fewer characters than the array length even before EOF. For large inputs, read in a loop.
- Use the exact `0..count` range; do not print the entire array if the final read produced fewer characters.
- If you only need the entire text of a small file with a specific charset, `Files.readString(path, StandardCharsets.UTF_8)` is simpler. `Channels.newReader` is useful when your source is already a channel or an API expects a `Reader`.
- Avoid `new String(bytes)` or `new InputStreamReader(input)` without specifying a charset when you want environment-independent results.

### 4.1. Reading Line by Line

The `Reader` from `Channels.newReader` provides character-reading operations, not `readLine()`. To read line by line, wrap it in `BufferedReader`:

```java
try (var reader = new java.io.BufferedReader(
        Channels.newReader(
                Files.newByteChannel(Path.of("notes.txt")),
                StandardCharsets.UTF_8))) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
```

*This snippet sits inside a method handling `IOException`; `Channels`/`StandardCharsets`/`Files`/`Path` are imported.* `BufferedReader` adds line-reading and character buffering; `Channels.newReader` maintains its own **byte** buffer for the decoder. `readLine()` excludes line terminators from its return value, so reconstructing original text from lines requires an explicit policy for preserving line endings.

## 5. Using `newWriter` to Write Text to a Channel

Example opening an output file and writing UTF-8:

```java
import java.io.Writer;
import java.nio.channels.Channels;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("notes.txt");

try (WritableByteChannel channel = Files.newByteChannel(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.TRUNCATE_EXISTING,
        StandardOpenOption.WRITE);
     Writer writer = Channels.newWriter(
             channel, StandardCharsets.UTF_8)) {

    writer.write("Xin chào");
    writer.write(System.lineSeparator());
}
```

This is an illustrative snippet inside a method handling `IOException`. `Writer` receives Java characters, the encoder converts them into UTF-8 bytes, and the channel writes them to the file. The options `CREATE`, `TRUNCATE_EXISTING`, `WRITE` mean: create if absent, erase existing content on open, and open for writing. If you want to append, configure other options such as `APPEND` appropriately; do not use `TRUNCATE_EXISTING` when you want to preserve existing file contents.

**When bytes reach the destination:** the Writer has an internal byte buffer. `write` may hold part of the data in that buffer before forwarding it to the channel. `flush()` pushes buffered data to the channel; `close()` finishes encoder processing, flushes any unwritten bytes, and closes the underlying channel. `flush()` does not mean the data is durably persisted on the storage device. If crash-safe file durability is required, that is a separate requirement—such as `FileChannel.force(...)` where applicable.

### 5.1. Should You Wrap with `BufferedWriter`?

`BufferedWriter` adds an outer **character buffer**:

```java
try (var writer = new java.io.BufferedWriter(
        Channels.newWriter(
                Files.newByteChannel(
                        Path.of("notes.txt"),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING),
                StandardCharsets.UTF_8))) {

    writer.write("Dòng 1");
    writer.newLine();
    writer.write("Dòng 2");
}
```

This is an illustrative snippet inside a method handling `IOException`. The outer layer can reduce small calls into the encoder layer and provides `newLine()`. That does not mean you must add `BufferedWriter` in every situation: effectiveness depends on write pattern, buffer sizing, and the sink. The `Writer` from `Channels` already has an internal byte buffer.

## 6. Default Adapter Error Handling and How to Configure It

**An easily overlooked difference:** the `Channels.newReader(channel, Charset)` and `Channels.newWriter(channel, Charset)` overloads create a decoder/encoder whose default action is **`CodingErrorAction.REPORT`** for both malformed and unmappable errors. That means they fail loudly instead of silently substituting a fallback character.

Per-direction policy choices:

| Action | Meaning on Bad Data | When to Consider |
|---|---|---|
| `REPORT` | Reports an error (via exception during adapter read/write) | Config data, strict protocols, integrity verification |
| `REPLACE` | Replaces with the decoder/encoder's replacement character/bytes | Best-effort display when data loss is acceptable |
| `IGNORE` | Drops the portion that cannot be decoded/encoded | Only when business logic permits silent data loss without a placeholder |

Configuring a decoder:

```java
CharsetDecoder decoder = StandardCharsets.UTF_8
        .newDecoder()
        .onMalformedInput(CodingErrorAction.REPLACE)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);

Reader reader = Channels.newReader(sourceChannel, decoder, -1);
```

This illustration assumes `sourceChannel` is an open `ReadableByteChannel` with imports for `CharsetDecoder`, `CodingErrorAction`, `StandardCharsets`, `Reader`, and `Channels`. A default UTF-8 decoder typically substitutes `U+FFFD` (replacement character ``) when `REPLACE` is selected; the replacement string can be configured via `CharsetDecoder.replaceWith(...)`.

Configuring an encoder:

```java
CharsetEncoder encoder = StandardCharsets.ISO_8859_1
        .newEncoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPLACE);

Writer writer = Channels.newWriter(outputChannel, encoder, -1);
```

This illustration assumes `outputChannel` is an open `WritableByteChannel` with appropriate imports. The ISO-8859-1 encoder uses `?` (`0x3F`) as its default replacement byte. For other encoders, never guess the replacement byte: inspect `replacement()` and the charset contract. `REPLACE` or `IGNORE` produces lossy output; never use them if an exact byte round-trip is required.

`MalformedInputException` and `UnmappableCharacterException` are both subtypes of `CharacterCodingException`, which extends `IOException`. Surfacing the error happens when `read`/`write`/`flush`/`close` actually processes the data, not necessarily at the moment the Reader/Writer is constructed.

### 6.1. Distinguishing Malformed vs. Unmappable

- **Malformed input**: a byte sequence or `char` sequence that **violates the rules** of the chosen encoding—for example, UTF-8 bytes `C3 28`, or UTF-16 containing an unpaired high surrogate without a matching low surrogate during encoding.
- **Unmappable character**: structurally valid input that cannot be represented in the target charset—for example, `☕` is valid in a Java String yet unsupported in ISO-8859-1.
- A charset mismatch can produce wrong text **without throwing an error** if the decoder accepts every byte. The `REPORT` policy cannot detect a wrong charset choice as long as the bytes happen to be valid in the selected charset.

Correct text handling always requires knowing the source encoding (from spec, protocol, metadata, or user choice) and the target encoding.

## 7. Runnable Java 17+ Example: Round-Trip and Charset Error Reporting

This is a complete example with no local file dependencies. It builds channels from `ByteArrayOutputStream` and `ByteArrayInputStream` using `Channels.newChannel`. The output demonstrates both a UTF-8 round-trip and `REPORT` / `REPLACE` choices.

**Source file:** `ChannelCharsetDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.Reader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.channels.Channels;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CharsetEncoder;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.MalformedInputException;
import java.nio.charset.StandardCharsets;
import java.nio.charset.UnmappableCharacterException;

public class ChannelCharsetDemo {

    private static String readAll(Reader reader) throws IOException {
        StringWriter result = new StringWriter();
        reader.transferTo(result); // Available since Java 10.
        return result.toString();
    }

    public static void main(String[] args) throws IOException {
        // Unicode escapes keep the source independent of file encoding when copied.
        String message = "C\u00E0 ph\u00EA \u2615";
        ByteArrayOutputStream encoded = new ByteArrayOutputStream();

        try (Writer writer = Channels.newWriter(
                Channels.newChannel(encoded), StandardCharsets.UTF_8)) {
            writer.write(message);
        }

        byte[] utf8 = encoded.toByteArray();
        try (Reader reader = Channels.newReader(
                Channels.newChannel(new ByteArrayInputStream(utf8)),
                StandardCharsets.UTF_8)) {
            System.out.println("UTF-8 round-trip: "
                    + message.equals(readAll(reader)));
        }

        // C3 must be followed by a continuation byte; 28 is not a continuation byte.
        byte[] malformed = {(byte) 0xC3, (byte) 0x28};

        try (Reader reader = Channels.newReader(
                Channels.newChannel(new ByteArrayInputStream(malformed)),
                StandardCharsets.UTF_8)) {
            readAll(reader);
        } catch (MalformedInputException ex) {
            System.out.println("decode strict: MalformedInputException");
        }

        CharsetDecoder forgivingDecoder = StandardCharsets.UTF_8
                .newDecoder()
                .onMalformedInput(CodingErrorAction.REPLACE);

        try (Reader reader = Channels.newReader(
                Channels.newChannel(new ByteArrayInputStream(malformed)),
                forgivingDecoder, -1)) {
            System.out.println("decode replace equals: "
                    + "\uFFFD(".equals(readAll(reader)));
        }

        try (Writer writer = Channels.newWriter(
                Channels.newChannel(new ByteArrayOutputStream()),
                StandardCharsets.ISO_8859_1)) {
            writer.write("\u2615");
        } catch (UnmappableCharacterException ex) {
            System.out.println("encode strict: UnmappableCharacterException");
        }

        ByteArrayOutputStream replaced = new ByteArrayOutputStream();
        CharsetEncoder forgivingEncoder = StandardCharsets.ISO_8859_1
                .newEncoder()
                .onUnmappableCharacter(CodingErrorAction.REPLACE);

        try (Writer writer = Channels.newWriter(
                Channels.newChannel(replaced), forgivingEncoder, -1)) {
            writer.write("\u2615");
        }

        System.out.println("encode replace: "
                + new String(replaced.toByteArray(),
                             StandardCharsets.ISO_8859_1));
    }
}
```

Compile/run in the directory containing the file:

```bash
javac ChannelCharsetDemo.java
java ChannelCharsetDemo
```

**Stdout (ASCII, independent of terminal emoji rendering):**

```text
UTF-8 round-trip: true
decode strict: MalformedInputException
decode replace equals: true
encode strict: UnmappableCharacterException
encode replace: ?
```

Result explanation:

1. The Writer encodes `"Cà phê ☕"` into UTF-8; the Reader decodes using the **same** charset, so comparing with the original string yields `true`.
2. The default UTF-8 decoder on `Channels.newReader` uses `REPORT`. Upon hitting `C3 28`, the Reader throws `MalformedInputException`; the program catches that specific exception.
3. The customized decoder using `REPLACE` produces `"\uFFFD("`, so the equality check prints `true`.
4. ISO-8859-1 cannot represent `☕`; the default writer throws `UnmappableCharacterException`.
5. The encoder switched to `REPLACE` writes the fallback byte; reading back as ISO-8859-1 yields `?`.

`ByteArrayOutputStream` lets you read its bytes after the wrapper closes; the in-memory byte source in this example needs no file cleanup either. With a real socket or file, closing the Reader/Writer closes the channel, so resource ownership must be managed carefully.

## 8. Transcoding Text: From One Charset to Another

“Transcoding” text means **decoding from the source charset and then encoding into the target charset**. Never relabel a byte array with a different charset name and expect the bytes to transform on their own. Diagram:

```text
ISO-8859-1 file --[ReadableByteChannel]
                --[CharsetDecoder ISO-8859-1]
                --> char / String
                --[CharsetEncoder UTF-8]
                --[WritableByteChannel] --> UTF-8 file
```

The method below streams the conversion without holding the whole file in RAM:

```java
import java.io.IOException;
import java.io.Reader;
import java.io.Writer;
import java.nio.channels.Channels;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TextTranscoder {
    public static void transcode(
            Path source, Charset sourceCharset,
            Path target, Charset targetCharset) throws IOException {

        try (Reader reader = Channels.newReader(
                Files.newByteChannel(source), sourceCharset);
             Writer writer = Channels.newWriter(
                Files.newByteChannel(target,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.TRUNCATE_EXISTING,
                        StandardOpenOption.WRITE),
                targetCharset)) {

            char[] chunk = new char[4096];
            int count;

            while ((count = reader.read(chunk)) != -1) {
                writer.write(chunk, 0, count);
            }
        }
    }
}
```

This is a **compilable helper class** (`TextTranscoder.java`) with no `main` and no stdout. External call example:

```java
TextTranscoder.transcode(
        Path.of("source-latin1.txt"),
        StandardCharsets.ISO_8859_1,
        Path.of("target-utf8.txt"),
        StandardCharsets.UTF_8);
```

This call illustration requires importing `Path`, `StandardCharsets`, and handling `IOException`; the input file must exist. Source and target must be **two paths not pointing to the same file**, because opening the writer with `TRUNCATE_EXISTING` can destroy the source data if they collide. For critical files, write to a temporary file and safely replace the target only after succeeding, while handling errors and permissions.

Notes:

- Each read may return a few characters, with no 1:1 ratio to the number of bytes read or written.
- `Writer` encodes while writing and finishes buffered data upon closing; there is no need to convert `char[]` to bytes manually.
- Character counts and byte counts before vs. after can differ. For example, ISO-8859-1 `é` is one byte, while UTF-8 `é` is two bytes.
- If a source character does not exist in the target charset, the default `REPORT` encoder fails; being “readable” does not guarantee “writable to another charset without loss”.
- This is **text** conversion; do not use it on binary files, images, ZIP archives, or non-text binary protocols.
- Decide explicitly whether to preserve or normalize line endings, Unicode normalization, and BOMs if business rules require it. Those transformations do **not** happen automatically just from changing charsets.

## 9. `minBufferCap` and Buffering Reality

The two detailed overloads accept `minBufferCap`:

```java
Channels.newReader(readable, decoder, minBufferCap);
Channels.newWriter(writable, encoder, minBufferCap);
```

`minBufferCap` specifies **the minimum capacity of the internal byte buffer** used when the adapter reads/writes, or `-1` for an implementation-defined default. For `Writer`, the API documentation allows the implementation to **ignore** this value. Therefore:

- The parameter is the capacity of a **byte buffer**, not the number of `char`s in a `String`/`char[]`.
- It does **not** limit total file/text size, the length of a single `read` or `write`, final byte count on disk, or bytes per character in a charset.
- A larger value does not automatically guarantee faster execution. Real impact depends on how the adapter decodes/encodes, channel type, call sizes, and underlying I/O.
- Without performance measurements, use the `Charset` overload or `-1`. To optimize, benchmark a realistic workload across languages and string lengths rather than guessing by eye.

The internal buffer is also a cause of **channel position** surprises: `Reader` may read many bytes ahead from the channel to prepare decoding even if the caller only pulled a few `char`s. If another part of the code later reads directly from that same channel, it may start at a byte position much further along than expected.

## 10. Resource Lifecycle and Channel Sharing

### 10.1. Closing the Wrapper Also Closes the Channel

Under the `Channels.newReader` and `newWriter` contracts, **calling `close()` on the wrapper closes the underlying channel**. This matters greatly when the channel comes from a caller:

```java
ReadableByteChannel channel = Files.newByteChannel(Path.of("notes.txt"));
Reader reader = Channels.newReader(channel, StandardCharsets.UTF_8);

reader.close();
System.out.println(channel.isOpen()); // false
```

This snippet assumes the file exists, imports are present, and the method handles `IOException`. After `reader.close()`, the channel is no longer usable; do not continue writing/reading on the channel as before. Closing a Writer likewise closes the underlying `WritableByteChannel`.

**Recommendation:** within the scope that owns the resource, use `try-with-resources`. If a caller must keep the channel open for further use, do not wrap and close it without agreeing on ownership in the contract; consider separating lifecycles or adjusting the API so the owner decides when to close.

### 10.2. Avoid Having Two Adapters Read/Write on the Same Channel

Two separate `Reader`s sharing one `ReadableByteChannel` do **not** have two independent byte positions. Each `Reader` has its own buffer and decoder state; interleaved calls risk scrambling bytes, especially with multi-byte encodings.

Likewise, creating two `Writer`s on the same channel and interleaving writes can misalign byte order relative to character order, especially while one `Writer` still holds buffered bytes. On a `FileChannel` with a shared file position, mixing `channel.position(...)`, `channel.read(ByteBuffer)`, and `Reader.read(...)` can break positioning assumptions.

If business logic needs to read independent segments, manage separate channels/streams and decoders per segment, specify offsets in **bytes**, and never slice mid-way through a multi-byte character sequence. Never split UTF-8 text at arbitrary byte offsets and decode each slice as an independent valid text string.

### 10.3. Non-Blocking Channels Are a Practical Boundary

`Channels.newReader`/`newWriter` are synchronous character-API adapters. Per the documentation, if a **selectable channel** is in non-blocking mode when the adapter needs to perform I/O, it can throw `IllegalBlockingModeException`. These wrappers do not magically turn the flow into selector/reactive/asynchronous I/O.

For example, with a `SocketChannel` configured with `configureBlocking(false)`, do not use `Channels.newReader(socket, UTF_8)` as an automatic solution for a non-blocking protocol. Instead, use `Selector` to read/write `ByteBuffer`s and manage `CharsetDecoder`/`CharsetEncoder` according to connection state and message boundaries, including partial-byte decodes and end-of-stream flushing.

### 10.4. `CharsetDecoder`/`CharsetEncoder` Hold State

Codecs can be **stateful** and are generally not safe for concurrent use by multiple threads on the same instance. For each logical data stream, create a dedicated decoder/encoder via `charset.newDecoder()`/`charset.newEncoder()`. Never hand the same decoder currently used by one Reader to another Reader, or interleave manual `decode(...)` calls while a Reader is using it.

When starting a new text stream, do not assume you can reuse an existing coder still holding leftover state from a previous stream as-is. Give codecs their own lifecycle, or reset them explicitly when the API/contract allows.

## 11. Distinguishing Nearby APIs

| Need | Appropriate API | Note |
|---|---|---|
| Channel bytes → characters | `Channels.newReader(ch, charset)` | Decodes bytes; wrapper closes channel on close |
| Characters → channel bytes | `Channels.newWriter(ch, charset)` | Encodes characters; wrapper closes channel on close |
| `InputStream` bytes → characters | `new InputStreamReader(input, charset)` | No need to create an intermediate channel if you already have an `InputStream` |
| Characters → `OutputStream` bytes | `new OutputStreamWriter(output, charset)` | No channel needed when working purely with streams |
| Small text file → `String` | `Files.readString(path, charset)` | Handles opening/closing the file per API |
| `String` → file | `Files.writeString(path, text, charset, options...)` | Simpler when no channel is needed |
| Channel bytes → `InputStream` bytes | `Channels.newInputStream(ch)` | Performs no charset conversion |
| `OutputStream` bytes → channel bytes | `Channels.newChannel(output)` | Performs no charset conversion |
| Channel bytes → `ByteBuffer` | `channel.read(buffer)`/`write(buffer)` | Lower byte level; caller handles decode/encode |

Two common points of confusion:

1. **`Channels.newInputStream` is not `Channels.newReader`.** A stream carries raw bytes; a `Reader` delivers decoded Unicode characters.
2. **`Charset.encode/decode` convenience methods and `newReader/newWriter` adapters can have different error policies.** Read the contract of the exact API you call; for the `Charset`-based adapters, the default error action is `REPORT`.

## 12. BOM, Line Endings, and Content Integrity

### 12.1. Byte Order Mark (BOM)

Some text files start with a BOM, such as UTF-8 BOM bytes `EF BB BF`, UTF-16BE `FE FF`, or UTF-16LE `FF FE`. A BOM helps describe byte order for certain formats, though handling depends on the specific charset and decoder.

Do not assume `Channels.newReader(..., UTF_8)` always “strips every BOM automatically”. With UTF-8, a BOM may be decoded as the character `U+FEFF` at the beginning of the content. If a protocol specifies an optional BOM, implement an explicit input-reading rule and test it with real data. Do not strip every `U+FEFF` in the middle of text, as it can have meaning other than a start-of-file marker.

### 12.2. Line Endings and Normalization

`newReader`/`newWriter` **do not automatically convert** CRLF (`\r\n`) to LF (`\n`), nor do they normalize Unicode to NFC/NFD. `BufferedReader.readLine()` strips line terminators when splitting lines, which is a separate layer. When transcoding config files, CSVs, or signed protocols, differences in line endings, BOMs, and normalization can alter output bytes or signatures. Decide the conversion policy before processing.

### 12.3. Round-Trips Require Clear Conditions

Reading and then writing with the same charset is not a byte-preserving copy for every possible input. Conditions to check:

- Are the source bytes valid in that charset?
- Can the decoder and encoder map through Unicode and back to the exact original bytes? Some encodings allow multiple byte representations for the same character sequence.
- Are `REPLACE`/`IGNORE` enabled, causing data loss?
- Is a BOM added/removed, or are line endings or normalization altered?
- Is the file something other than plain text, containing bytes meaningful outside the charset?

If **100% exact byte copying** is required, copy bytes via channels/streams without going through `Reader`/`Writer`. If **human-readable text read/write in a specific charset** is required, use decoders/encoders and verify the results appropriately.

## 13. Common Mistakes and Fixes

1. **Omitting the charset** and assuming every environment uses UTF-8. With Channels adapters, pass `StandardCharsets.UTF_8` or the protocol-specified charset.
2. **Mixing up conversion direction.** `newReader` takes bytes from a channel and decodes; `newWriter` takes chars and encodes. Do not call `newReader` on a write-only `WritableByteChannel`.
3. **Calling `newReader(ch)` or `newWriter(ch)`.** There is no single-argument overload; you must specify a charset/decoder/encoder.
4. **Treating `Charset` and `CharsetDecoder` as the same type.** The decoder overload also requires `minBufferCap`; the `Charset` overload has no buffer parameter.
5. **Using the wrong target encoding**, causing mojibake. No exception is thrown in some charset mismatch cases; rely on source specifications.
6. **Assuming codecs always replace invalid characters.** Channels adapters with the `Charset` overload use `REPORT`; handle `CharacterCodingException` or create a coder with an explicit `CodingErrorAction`.
7. **Confusing “malformed” with “unmappable”.** One is structurally invalid input; the other is a valid character that cannot be mapped in the target charset.
8. **Believing `REPLACE` is lossless.** Replacement keeps processing going, yet loses original bytes or characters.
9. **Calling `write` without closing/flushing the writer.** Data can remain in buffers. Use `try-with-resources` within the scope owning the channel.
10. **Thinking `flush()` guarantees the file is fsynced.** Pushing Java buffers to the channel is distinct from storage durability guarantees.
11. **Closing Reader/Writer and still trying to use the old channel.** `close` closes the channel too; establish clear ownership.
12. **Calling `readLine()` directly on `Reader`.** Use `BufferedReader` for line-oriented processing.
13. **Mixing direct channel reads with a Reader on the same channel.** Read-ahead and decoder state desynchronize the expected byte position.
14. **Attaching synchronous Reader/Writer to a non-blocking `SocketChannel`.** This can throw `IllegalBlockingModeException`; non-blocking I/O requires managing `ByteBuffer` and decoders in a state machine.
15. **Splitting UTF-8 bytes arbitrarily and decoding each chunk separately.** A character can span multiple bytes. Use a stateful decoder across the continuous byte stream, or a Reader adapter that manages incomplete byte sequences.
16. **Treating `minBufferCap` as a text size limit.** It only concerns the internal byte buffer and may be ignored by implementations for Writer.
17. **Thinking closing the channel only frees metadata without flushing encoder state.** Closing the Writer completes encoding, flushes, and then closes the channel.
18. **Using character transcoding to copy binary data.** Text decoding/encoding can alter bytes; copy binary data as raw bytes.
19. **Forgetting BOMs and line endings** when byte-for-byte identity with the original file is expected. A charset alone does not guarantee byte equivalence.
20. **Sharing a `CharsetDecoder`/`CharsetEncoder` across threads.** Codecs are stateful and not thread-safe by default.

## 14. Self-Check Questions

**Q1.** A `ReadableByteChannel` contains UTF-8 bytes. Which method returns a `Reader` with UTF-8?  
**Answer:** `Channels.newReader(channel, StandardCharsets.UTF_8)`.

**Q2.** What can happen when writing `☕` via `Channels.newWriter(channel, StandardCharsets.ISO_8859_1)`?  
**Answer:** During encoding, the default is `REPORT`, so it can throw `UnmappableCharacterException`; that charset cannot represent the character.

**Q3.** You need to accept invalid UTF-8 and display `U+FFFD` as replacement—how?  
**Answer:** Create `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPLACE)` and pass it to `Channels.newReader(channel, decoder, -1)`.

**Q4.** Does closing the `Reader` created by `Channels.newReader` close the channel?  
**Yes.** The Reader owns closing the underlying channel per the adapter contract.

**Q5.** If you call `newReader` and read 10 characters, is it guaranteed the channel consumed exactly 10 bytes?  
**No.** Unicode and charsets vary in bytes per character; the adapter also maintains a byte buffer and may read ahead.

**Q6.** If you only need to read a small UTF-8 text file into a `String`, should you always use `Channels.newReader`?  
**Not necessary.** `Files.readString(path, StandardCharsets.UTF_8)` is usually cleaner. Choose `Channels` when a channel source or `Reader` API is an actual requirement.

**Q7.** To convert ISO-8859-1 text to UTF-8, is renaming the file or wrapping `byte[]` with `newWriter` enough?  
**No.** You must decode from ISO-8859-1 into chars and then encode into UTF-8 (or use an equivalent transcoder API).

**Q8.** Does `minBufferCap=8192` guarantee the Writer will write exactly 8192 bytes each time?  
**No.** It is a minimum hint for the internal buffer, implementations may ignore it, and how many bytes each channel write sends depends on the data and flush timing.

**Q9.** If UTF-8 bytes are decoded as ISO-8859-1 into `"Ã©"`, will `REPORT` mode necessarily throw an error?  
**No.** ISO-8859-1 can decode each individual byte validly, even though the user sees garbled text.

**Q10.** Does reading text with a Reader and writing it through a Writer always preserve 100% of the bytes?  
**No.** Decoding/encoding can alter bytes, especially across different charsets, replacements, BOMs, line endings, or mappings lacking byte-level round-trip fidelity.

## 15. Takeaways and Official Documentation

**Core takeaway:** `Channels.newReader` is a **byte channel → character `Reader`** adapter via `CharsetDecoder`; `Channels.newWriter` is a **character `Writer` → byte channel** adapter via `CharsetEncoder`. Specify charsets explicitly, choose an appropriate error policy, manage wrapper/channel lifecycles, and keep text transcoding separate from verbatim byte copying.

Java SE 21 documentation:

- `Channels` (six overloads, buffering, blocking mode, close behavior): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/Channels.html
- `Charset`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/Charset.html
- `CharsetDecoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- `CharsetEncoder`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetEncoder.html
- `CodingErrorAction`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CodingErrorAction.html
- `StandardCharsets`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html
- `ReadableByteChannel`, `WritableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html

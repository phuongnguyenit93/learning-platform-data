# Normal EOF vs. Truncated Data in Java I/O

When reading a file, socket, or data source in Java, encountering **EOF** (*end of file/end of stream*) can be completely normal: the source has no more elements to read. However, EOF can also occur **too early** relative to the amount of data required by a protocol, file format, or record; in that case, the application must recognize **truncated data**.

The key point is that **EOF only says "there is no more data from the source"; it does not by itself confirm "the message is complete"**. To distinguish valid EOF from truncation, a program must know the **application-level completion condition**: expected size, end marker, record count, framing, checksum, format structure, or predefined rules.

This lesson belongs to the **Resources and Errors** group of Java Core I/O. It covers EOF signals across APIs, how to read complete data, distinguishing valid termination from premature termination, standalone Java 17 examples, pitfalls with text and network data, and integrity-checking strategies.

## 1. Definition: EOF and Truncation Are Not Strict Opposites

**EOF** (*end of file/end of stream*) is the state indicating no further data remains in the input source. In Java:

- `InputStream.read()` returns **`-1`** when no bytes remain to be read.
- `Reader.read()` returns **`-1`** when no character units remain to be read.
- `BufferedReader.readLine()` returns **`null`** when no lines remain to be read.
- `DataInputStream` has operations that require an exact byte count, such as `readInt()` and `readFully(...)`, which may throw **`EOFException`** if data runs out before completion.
- `ByteBuffer` and `CharBuffer` do not by themselves signify "EOF"; they are buffers. Channel or decoder APIs determine how end-of-stream state is reported.

**Truncation** is the situation where content is **shorter than or missing components** compared to a format/contract. For example, a frame declares a 100-byte payload, yet only 60 bytes are received before EOF.

A byte source can terminate normally at the operating system level while still being **invalid data at the application level**. Conversely, a short file can be completely valid if its format permits that length.

| Scenario | Has EOF? | Is Truncated? | Reason |
|---|---|---|---|
| Valid text file ending after the last line with no newline | Yes | **Not necessarily** | Many conventions allow the final line to end at EOF |
| Byte stream promises no length; caller reads until `-1` | Yes | **Cannot conclude from EOF alone** | No expected size or sentinel |
| Header states "100-byte payload" but only 60 bytes exist | Yes | **Yes** | Missing 40 bytes per the contract |
| 4-byte header receives only 2 bytes before EOF | Yes | **Yes**, if the 4-byte header is mandatory | Cannot decode the full header |
| File format requires a mandatory footer, but the footer is missing | Yes | **Yes**, if the footer is mandatory | Missing completion structure |
| Network connection temporarily has no bytes available to read | Not certain | Not certain | No data at this instant does not mean EOF |
| `read(buffer)` returns fewer bytes than buffer capacity | Not certain | Not certain | A single short read proves neither EOF nor truncation |

**Only the caller that understands the contract can determine when EOF is normal.** I/O APIs provide signals, but do not know on their own what constitutes a complete business record.

## 2. How Does EOF Appear in Java?

### `InputStream.read()` and `Reader.read()`

`InputStream.read()` returns an `int` in the range **`0..255`** for an actual byte and **`-1`** at EOF. Because `byte` is signed in Java, returning `int` avoids confusing a `0xFF` data byte with the special value `-1`.

`Reader.read()` returns an `int` in the range **`0..65535`** for a UTF-16 `char`, or **`-1`** at EOF. It does not necessarily read a full Unicode code point per call; characters outside the BMP can consist of two code units.

Example loop reading bytes until EOF:

```java
int value;
while ((value = input.read()) != -1) {
    // Process byte from 0 to 255.
}
```

This is an **illustrative snippet**, not a complete program: `input` must be an initialized `InputStream`, and the method must handle `IOException`. The correct loop pattern compares `value != -1`; do not cast to `byte` and compare against `-1`, because a `0xFF` data byte would be mistaken for EOF.

`read()` may **block** waiting for bytes, return bytes, report EOF, or throw `IOException` depending on the source's characteristics. **Waiting for data** does not mean EOF has been reached.

### `read(byte[])` and `read(char[])`

`int n = input.read(buffer)` returns the **actual number of bytes read** or `-1` at EOF (for a positive-length array under the standard contract). `Reader.read(char[])` behaves similarly in UTF-16 code units.

Do not assume:

- "The buffer is 4096 bytes long, and this time I got 100 bytes, so the data must be truncated."
- "Every read must fill the entire buffer."
- "A short read means EOF."

A read can be valid even when returning fewer elements than requested. For an array/slice with `len == 0`, Java may return **`0`**; never treat `0` as EOF.

Loop for reading a stream of unknown size:

```java
byte[] buffer = new byte[4096];
int n;
while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
```

This is **illustrative code**: initialized `input` and `output`, close management, and `IOException` handling are required. The goal is copying until EOF. If a target byte count must be met, **you must count and validate further** before treating the result as successful.

### Line-Based Reading

`BufferedReader.readLine()` returns `null` when no more lines remain; a valid empty line returns `""`. Do not use `line.isEmpty()` to detect EOF, because an empty line is data.

Example:

```java
String line;
while ((line = reader.readLine()) != null) {
    // May be an empty string yet still a valid line.
}
```

This snippet requires `reader` to be an open `BufferedReader`. Note that `readLine()` **strips line terminators** (LF, CRLF, or CR); therefore, it can return the exact same final line string whether the file has a terminal newline or not.

## 3. When Is EOF Normal?

EOF can serve as a **valid completion signal** when the protocol or format specifies reading to the end of the source with **no other completion condition**. Examples include:

1. Reading an entire free-form text file with no requirement for a trailing newline.
2. Reading an arbitrary binary file solely to copy **all currently available content**, with no expected byte count and no need to assert original source completeness.
3. An application protocol explicitly designed to use **connection close as the message terminator**, under appropriate safety conditions. Distinguish this as a deliberate framing choice, not a rule for all network protocols.
4. Reading a finite collection/source defined as "all elements until none remain".

Here, the application enforces a contract like: *"Take whatever the source provides up to EOF."* EOF is the stopping condition of the operation, not an error signal on its own.

**Limitation:** "Successfully copying until EOF" does not prove the source file or message **is not missing bytes compared to the author's original**. Without a reliable size, checksum, or canonical structure to verify against, the caller may have no way to detect missing data.

## 4. When Does EOF Become a Sign of Truncation?

EOF is abnormal when it occurs **before a mandatory completion condition**. Common forms:

- **Fixed length:** exactly 16 bytes are needed for a binary field, but only 11 are obtained.
- **Header-declared length:** the header states the body is 500 bytes, but the source ends after 200.
- **Mandatory terminator:** the format requires a footer, marker, checksum, or closing tag, yet EOF is reached without encountering it.
- **Declared element count:** the file header states "10 records", but only 9 can be parsed.
- **Multi-field record:** the first field was read, but mandatory subsequent fields are missing.
- **Incomplete character encoding:** a UTF-8 sequence requires additional continuation bytes, yet the byte stream ends mid-code-point.
- **Compressed stream or container:** the internal structure requires a footer/CRC/length or terminating block, and the data was cut off.

Each case needs **a clear technical criterion** to determine what is missing. Do not throw an arbitrary `EOFException` simply upon reaching EOF in a program designed to read to the end of a file.

### Fixed-Length Frame Example

Suppose a protocol specifies:

```text
+--------------------+-------------------------+
| Length (4 bytes)   | Payload (length bytes)  |
| big-endian signed  |                         |
+--------------------+-------------------------+
```

If the byte stream only has two bytes in the header, **a complete `int` cannot be read**. If the header is complete but the payload is shorter than `length`, that is also truncation. If both header and payload are complete, the frame is complete **with respect to length** (even though the payload content might still be invalid per business rules or charset).

An important point: the header-declared length must be checked to be **non-negative** and **within bounds** to avoid allocating huge arrays from untrusted data. When data arrives over the network, check size limits before allocating or reading the full payload.

## 5. Read-to-EOF APIs vs. Exact-Data APIs

| API | When Source Ends | Meaning |
|---|---|---|
| `InputStream.read()` | Returns `-1` | Normal EOF at the stream level |
| `InputStream.read(byte[])` | Returns `-1` if no bytes remain and length > 0 | Each prior read may be short |
| `InputStream.readNBytes(int len)` | Returns an array of **at most** `len` bytes; may be fewer on EOF | **Caller must check** size if exact length is required |
| `InputStream.readNBytes(byte[], off, len)` | Returns bytes read, which may be less than `len` at EOF | Caller must compare against expected count |
| `InputStream.readAllBytes()` | Returns all remaining bytes up to EOF | Unknown expected length unless caller verifies separately |
| `InputStream.transferTo(output)` | Returns total bytes transferred up to EOF | Copies to EOF; does not validate an expected byte count |
| `DataInputStream.readFully(byte[])` | **Throws `EOFException`** if the array cannot be filled | Very convenient for mandatory fixed-length fields |
| `DataInputStream.readInt()` | Throws `EOFException` if fewer than 4 bytes remain | Reads a fixed binary field |
| `BufferedReader.readLine()` | Returns `null` when no lines remain | Does not inspect trailing newline presence |
| `Reader.read()` | Returns `-1` | EOF at the character level |
| `FileChannel.read(ByteBuffer)` | Returns `-1` when channel reaches end-of-stream | Unaware of format-specific byte requirements |
| `SocketChannel.read(ByteBuffer)` | Returns `-1` if channel reaches end-of-stream | Non-blocking mode may also return `0` when no bytes are ready |

**Note:** `EOFException` is a subclass of `IOException`. It typically comes from APIs requiring a specific byte count (such as `DataInputStream`), which does not mean every `InputStream.read()` operation throws an exception at EOF.

When reading a file whose contract is simply "read until the end", `readAllBytes()` can be suitable for small inputs, though it consumes large amounts of RAM for big files. For large data, prefer bounded chunk reads, streaming, or appropriate mechanisms. Avoid treating `readAllBytes()` as proof that the file has valid structure.

## 6. Example 1 — `-1` Is EOF, While Short Reads Against Expected Size Must Be Checked

Create `StreamEofDemo.java` (Java 17+):

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.util.Arrays;

public class StreamEofDemo {
    public static void main(String[] args) throws Exception {
        byte[] bytes = {10, 20};
        try (InputStream in = new ByteArrayInputStream(bytes)) {
            System.out.println("first=" + in.read());
            System.out.println("second=" + in.read());
            System.out.println("EOF=" + in.read());
            System.out.println("EOF again=" + in.read());
        }

        try (InputStream in = new ByteArrayInputStream(bytes)) {
            byte[] result = in.readNBytes(4);
            System.out.println("requested=4, received=" + result.length);
            System.out.println("data=" + Arrays.toString(result));
            System.out.println("complete fixed-size field=" + (result.length == 4));
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 StreamEofDemo.java
java StreamEofDemo
```

Output:

```text
first=10
second=20
EOF=-1
EOF again=-1
requested=4, received=2
data=[10, 20]
complete fixed-size field=false
```

**Explanation:**

1. The first two `read()` calls retrieve bytes 10 and 20; the next call returns `-1` because the array has no data left. That is **normal EOF at the stream layer**. Calling it once more on `ByteArrayInputStream` still returns `-1`.
2. `readNBytes(4)` requests **at most** 4 bytes, but the array only contains 2. It returns a length-2 array **without throwing `EOFException`**.
3. If the application only wants to "read all available bytes", 2 bytes can be a complete result. If a protocol field requires **exactly 4 bytes**, `result.length == 4` is `false` and the data is **truncated according to the contract**.

Do not assume `-1` is always an error, and do not assume `readNBytes` returning cleanly proves enough data was received.

## 7. `DataInputStream.readFully` — Reading an Exact Mandatory Length

`DataInputStream` wraps an `InputStream` to read binary data types according to Java conventions. Two very useful methods:

- `readInt()` requires exactly **4 bytes**, reading a signed big-endian integer. If the source ends before 4 bytes, it throws `EOFException`.
- `readFully(byte[])` attempts to read until **the array is filled**, the source hits EOF, or an I/O error occurs. If EOF occurs before filling the array, it throws `EOFException`. Note there is no promise that it will be fast or guaranteed to finish if the source stays open without sending enough data.

You can write your own loop to read exactly n bytes and check the count, but `readFully` already provides clear "must be complete" semantics for fixed byte fields.

### Example 2 — Complete Length-Prefixed Data, Short Header, and Short Payload

Create `FramedPayloadDemo.java` (Java 17+):

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class FramedPayloadDemo {
    static byte[] frame(String text) throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (DataOutputStream data = new DataOutputStream(out)) {
            data.writeInt(payload.length);
            data.write(payload);
        }
        return out.toByteArray();
    }

    static String readFrame(byte[] bytes) throws IOException {
        try (DataInputStream in =
                     new DataInputStream(new ByteArrayInputStream(bytes))) {
            int size = in.readInt();
            if (size < 0 || size > 1024) {
                throw new IOException("Invalid length");
            }
            byte[] payload = new byte[size];
            in.readFully(payload);
            return new String(payload, StandardCharsets.UTF_8);
        }
    }

    static void verify(String label, byte[] frame) throws IOException {
        try {
            System.out.println(label + "=" + readFrame(frame));
        } catch (EOFException e) {
            System.out.println(label + "=TRUNCATED (" + e.getClass().getSimpleName() + ")");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] complete = frame("OK");
        verify("complete", complete);
        verify("short header", new byte[] {0, 0});
        verify("short payload", Arrays.copyOf(complete, complete.length - 1));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 FramedPayloadDemo.java
java FramedPayloadDemo
```

```text
complete=OK
short header=TRUNCATED (EOFException)
short payload=TRUNCATED (EOFException)
```

**Explanation of the three test cases:**

1. **`complete`:** the program writes an `int` header equal to the UTF-8 byte length of `"OK"`, followed by the exact payload. `readInt()` and `readFully` succeed.
2. **`short header`:** only two bytes exist while `readInt()` needs four; `EOFException` is thrown.
3. **`short payload`:** the header still declares two payload bytes, but the array has had its final byte trimmed off. `readFully` detects EOF before reading enough bytes.

In the example, `size` is bounded to `0..1024` **before allocating the array**. That is a mandatory safety step for untrusted input; real-world applications also need memory limits, timeouts, and total frame caps.

**Important note:** the example verifies receiving **one complete frame** per the header, without checking for trailing bytes after the frame because a real connection may carry **multiple consecutive frames**. If a format requires "the entire file contains exactly one frame with no trailing bytes", add an EOF check **after** the frame according to that contract.

In addition, `new String(payload, UTF_8)` is a text-decoding step and can replace invalid UTF-8 bytes. Having **enough bytes** and having a payload that is **valid UTF-8 text** are two separate criteria, which must be checked independently if the format requires strict Unicode.

## 8. Distinguishing EOF Signals from Other I/O Errors

Not every failed read operation is EOF:

| Signal or Exception | What It Tells You | What Not to Conclude |
|---|---|---|
| `read() == -1` | Source reported no more data | Entire business message is definitely complete |
| `EOFException` during `readFully` | Insufficient data for a mandatory operation | Source itself always "errored"; shortage could be file truncation or contract mismatch |
| `SocketTimeoutException` | Socket operation exceeded configured wait time | Peer closed and will definitely send no more |
| Other `IOException` | Specific I/O problem occurred | All errors are merely end-of-file |
| `read(buffer)` returns small positive count | Partial data was read | EOF reached or data truncated |
| Non-blocking `SocketChannel` read returns `0` | No bytes obtainable in this call right now | EOF |
| `BufferedReader.readLine() == null` | No more lines | Whether the last line had a newline or not |

**Timeout differs from truncation.** If an application is waiting for more bytes of a frame and misses a deadline, it can report that the operation **did not complete in time**; that is not proof the peer ended the stream. You may retry or cancel per policy, but must not treat a timeout as EOF.

**Closing a TCP connection does not imply a valid message.** A TCP FIN moves the reader toward EOF after consuming remaining buffered data, yet whether the message has a complete header/body is an application-layer framing responsibility. A TCP reset can surface as an I/O error rather than a clean EOF. Both paths must be handled.

**Closing a source from the application's own code is different from the source exhausting its data.** Calling `close()` to release resources is not a mechanism for detecting record completeness.

## 9. Text: Is a Last Line Without a Newline Truncated?

There is no universal rule that text files **must** end with LF. Many programs read the final line without a newline. `BufferedReader.readLine()` returns the last line in both cases:

```text
"alpha\nbeta"   (no trailing LF)
"alpha\nbeta\n" (with trailing LF)
```

Both yield two line contents: `alpha` and `beta`. Calling `readLine()` a third time returns `null` in both cases. Yet the **raw bytes differ**, and a specific format's contract may require a trailing newline.

### Example 3 — `readLine` Does Not Verify a Terminal Newline

Create `TextLineEofDemo.java`:

```java
import java.io.BufferedReader;
import java.io.StringReader;

public class TextLineEofDemo {
    static void show(String label, String text) throws Exception {
        try (BufferedReader reader = new BufferedReader(new StringReader(text))) {
            System.out.println(label + " line1=" + reader.readLine());
            System.out.println(label + " line2=" + reader.readLine());
            System.out.println(label + " EOF=" + (reader.readLine() == null));
            System.out.println(label + " terminal LF=" + text.endsWith("\n"));
        }
    }

    public static void main(String[] args) throws Exception {
        show("no LF", "alpha\nbeta");
        show("with LF", "alpha\nbeta\n");
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TextLineEofDemo.java
java TextLineEofDemo
```

```text
no LF line1=alpha
no LF line2=beta
no LF EOF=true
no LF terminal LF=false
with LF line1=alpha
with LF line2=beta
with LF EOF=true
with LF terminal LF=true
```

`readLine()` only reveals line contents and line-level EOF, discarding the terminator itself. In the example, the program still holds the original `text` so it can check `endsWith("\n")`. If data might use CR or CRLF, trailing-terminator checks must include the corresponding rules rather than LF alone.

When a format mandates that **every record must end with LF**, a missing final LF may be a format error or a sign of truncation. If the format allows the last line to terminate at EOF, a missing LF is **not an error**. You cannot decide solely by observing `readLine() == null`.

### Structured Formats and Lines

A CSV, JSON, or log parser can have its own termination syntax. For example, CSV allows newlines inside quoted fields per parser rules; calling `readLine()` is insufficient to tell whether a record is complete. JSON can terminate validly at EOF if its objects/structures are properly closed; reading half an object before EOF yields **syntactically incomplete** text.

**Physical lines** and **logical records** are two distinct concepts. A format-appropriate parser is needed, not just newline-counting logic.

## 10. EOF Mid-UTF-8 Code Point: Malformed Input

A text file might satisfy some logical block byte count yet end right in the middle of a **multi-byte encoded sequence**. For instance, the character `€` in UTF-8 is `E2 82 AC` (three bytes). If the file ends with `E2 82`, the UTF-8 sequence is incomplete.

A `CharsetDecoder` in strict mode can throw `MalformedInputException` when informed that end-of-input has been reached while continuation bytes are still missing. Meanwhile, convenience APIs like `new String(bytes, StandardCharsets.UTF_8)` typically **replace** invalid input with `U+FFFD` rather than throwing an exception.

### Example 4 — UTF-8 Ending Mid-Code-Point

Create `TruncatedUtf8Demo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class TruncatedUtf8Demo {
    public static void main(String[] args) throws Exception {
        byte[] valid = "A\u20ac".getBytes(StandardCharsets.UTF_8);
        byte[] truncated = Arrays.copyOf(valid, valid.length - 1);
        System.out.println("complete matches="
                + "A\u20ac".equals(new String(valid, StandardCharsets.UTF_8)));

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(truncated));
        } catch (CharacterCodingException e) {
            System.out.println("strict decoder=" + e.getClass().getSimpleName());
        }

        String lenient = new String(truncated, StandardCharsets.UTF_8);
        System.out.println("lenient decoder="
                + lenient.replace("\uFFFD", "<U+FFFD>"));
    }
}
```

```bash
javac -encoding UTF-8 --release 17 TruncatedUtf8Demo.java
java TruncatedUtf8Demo
```

```text
complete matches=true
strict decoder=MalformedInputException
lenient decoder=A<U+FFFD>
```

**Explanation:**

- `valid` holds UTF-8 bytes for `A€`. Removing the last byte of `€` produces an invalid byte sequence.
- The strict decoder encounters incomplete input at the end and throws `MalformedInputException`. This is a **text encoding** error, independent of whether an outer protocol declared a total byte count.
- `new String(...)` in this case inserts the `U+FFFD` replacement character. To keep stdout consistent regardless of console font, the example replaces that character with the literal string `<U+FFFD>` before printing.
- **Not every missing byte can be detected by a decoder.** If a trailing byte disappears yet the remaining bytes still form valid UTF-8, the decoder will not complain; only framing, length, or checksums can catch missing text according to the contract.

When reading chunk by chunk, never mark `endOfInput=true` simply because a single **chunk** lacks bytes. A valid UTF-8 character can be split across two reads; keep the decoder's state until the source genuinely ends.

## 11. Using Framing to Know When "Enough Has Been Received"

Common framing models each have trade-offs:

### 11.1 Fixed Length

A record has exact length **N bytes**. The caller must read all N via `DataInputStream.readFully` or an accumulation loop up to N. EOF before N signals shortage. Suitable for fixed headers or binary records with predefined layouts.

### 11.2 Length-Prefix

The header contains the length of the following payload. After reading a **complete** header, validate limits and read that exact byte count. EOF before reaching the declared byte count is truncation. You must decide whether the header counts **bytes** or **characters**; in byte-stream protocols, payload size is normally in bytes and must be computed from encoded bytes.

**Do not use `String.length()` as UTF-8 byte length.** Vietnamese characters or emojis often take multiple bytes, differing from UTF-16 length. For example, sending `"😊"` has `String.length() == 2` yet UTF-8 needs **4 bytes**; if the header writes length 2, the receiver will misframe the message.

### 11.3 Delimiter or End Marker

Read until a separator token (such as LF, a sentinel byte, or a dedicated terminator). If the contract requires a marker, EOF before the marker can be an error. However, escaping/quoting rules are needed if the marker can appear inside the payload. When LF is the delimiter, CRLF support may be needed per specification, rather than guessing from the platform.

### 11.4 Closing the Stream as End Marker

Some protocols use "until the peer closes the connection" to mark the end of the body. In that case, EOF **can** satisfy completion under that framing. However, if an upstream component truncates data and then closes cleanly, the receiver may **fail to detect it** without an external length, checksum, or marker. Therefore, weigh the diagnosability of missing data.

### 11.5 Checksum, Hash, or Footer

Checksums help detect altered or missing received data, **provided** the expected value is transmitted/stored reliably and an appropriate algorithm is used. For compressed files or containers, a footer/CRC and trailing structure help the parser catch abnormal termination.

**Note:** plain checksums like CRC do not provide tamper-proof authenticity; if an adversary can modify both content and CRC, an appropriate MAC or signature is needed. Byte-count and checksum checks must also remain separate from **semantic validation** of the data.

## 12. A Reliable Frame-Reading Workflow

For a protocol with a length header and payload, a typical workflow is:

1. **Define the contract**: how many bytes in the header, byte order (endianness), body length in bytes or characters, frame count, encoding, and connection termination semantics.
2. **Read the complete header**. If EOF occurs before any header byte is read, consult the contract: that may be a valid end of a *frame list*; EOF mid-header is typically truncation. In our `readFrame` example expecting **one mandatory frame**, EOF right before the header is also an error.
3. **Validate the header**: reject negative, over-limit, or invalid lengths. Never allocate arrays from unchecked numbers.
4. **Read the full body** up to the validated length. Use `readFully` or accumulate bytes up to exact length. If EOF occurs before length is reached, report missing data.
5. **Verify integrity**: checksum, footer, record count, schema, and strict decoding when required.
6. **Handle the remainder** per protocol: if multiple frames are expected, loop until the stop condition. If exactly one frame is allowed, check for disallowed trailing bytes.
7. **Close resources** using `try-with-resources` when the caller owns the source; handle timeouts/cancellations so file descriptors or connections are not held indefinitely.
8. **Report errors with context**: record name, expected length, and bytes actually read; avoid logging raw secrets.

### Byte-Count Verification Algorithm Example

This is **illustrative code** inside a method that has `InputStream in`, `int expected`, and handles `IOException`:

```java
if (expected < 0 || expected > 1_000_000) {
    throw new IllegalArgumentException("Invalid length");
}
byte[] payload = in.readNBytes(expected);
if (payload.length != expected) {
    throw new java.io.EOFException(
            "Expected " + expected + " bytes, got " + payload.length);
}
// Read enough bytes; next step is validating content per format.
```

This approach uses `readNBytes` and checks the length. `DataInputStream.readFully` turns a byte shortage directly into an `EOFException`; however, after an exception from `readFully`, you do not always know how many bytes were placed into the array unless you counted them separately.

If the body is large, allocating everything into one array is unnecessary; you can loop with a bounded buffer, accumulate the received byte count, and pass chunks to a streaming parser/destination.

## 13. Do Not Use `available()` to Guess EOF or Completeness

`InputStream.available()` returns an **estimate of bytes readable without blocking** per the stream's contract. It is not the total source size, guaranteed remaining file bytes, or application-level message length.

Common mistake:

```java
// DO NOT use available() as a completion condition:
while (input.available() > 0) {
    input.read();
}
```

This is a **wrong illustrative snippet**, not a valid reading workflow. With network streams, `available() == 0` may simply mean no bytes are ready **at that exact moment**, not that the peer closed. The program can stop prematurely and treat an incomplete message as complete.

Better practices:

- When reading "until EOF", call `read()`/`read(buffer)` until `-1`.
- When needing N exact bytes, read all N and compare with N.
- When the protocol uses delimiters, have the parser scan for the delimiter per rules.
- When timeouts are needed, use timeout/deadline as an independent failure/cancellation condition, never pretending it is EOF.

## 14. Similar Cases in NIO and Asynchronous Processing

For `ReadableByteChannel`/`FileChannel` and `SocketChannel`, the concepts remain the same, though exact signals depend on each channel's documentation.

- On a channel read to EOF, `read(ByteBuffer)` can return **`-1`** at end-of-stream.
- On a `SocketChannel` in **non-blocking** mode, a `read` call returning **`0`** may simply mean "no bytes read right now"; it does not mean EOF. The caller must wait for readiness or an appropriate event and continue.
- `ByteBuffer.remaining()` is the number of elements remaining to read/write in the **buffer**, not the bytes left on the socket or frame completeness.
- If a callback/event delivers 300 bytes while the message requires 500, **maintain frame state** and accumulate across subsequent events. Do not throw truncation just because one read was incomplete.
- When the channel actually signals end-of-stream, compare current parser state against completion rules. If a header, body, or delimiter is unfinished, report incomplete/truncated.

**Chunk boundaries are not message boundaries.** TCP is a byte stream: the number of `write` calls on the sender has no one-to-one correspondence with `read` calls on the receiver. This is why protocol design requires explicit framing rather than relying on "one read equals one record".

## 15. File I/O, Length, and Read Consistency

For an existing file, `Files.size(path)` can show the current size before reading, yet **is not absolute proof** that exact byte count will stay unchanged in a concurrently modified file. Files can change after measuring size.

A safer approach is clarifying requirements:

- If a **consistent snapshot** is needed, use snapshots, locks, or design patterns appropriate for the filesystem and environment.
- If the file format carries an **internal length**, compare actual bytes read against that length.
- If ensuring an **exact release artifact**, compare checksums/hashes against a trusted expected source.
- For files actively being written to (e.g., append-only logs), current EOF usually means **no new bytes exist at this moment**, not that the producer will never write more later. To "follow" a file, use dedicated polling/watch/tailing mechanisms.
- If data was cut short during a copy or download, check expected size, appropriately trusted HTTP metadata, checksums, or file-ending markers.

**Never turn a short read into overwriting the file.** First determine whether the source is still being updated, whether the read timed out, and which contract confirms the shortage.

## 16. Principles for Exceptions, Resources, and Retries

### Identifying the Failure Kind Correctly

- **Valid EOF:** loop termination or complete parse state per contract.
- **Truncated data:** report application-level error (potentially `EOFException` when mandatory bytes are missing), specifying expected vs. actual if known.
- **I/O failure:** handle `IOException`/network errors accordingly without conflating them with normal end-of-stream.
- **Timeout:** handle timeouts and cancellation/retry policies separately instead of converting them into a successful EOF result.
- **Malformed format:** such as negative length, malformed UTF-8, or broken payload structure; report the actual cause rather than simply logging "EOF".

In Java, `EOFException` is a subtype of `IOException`. When branching specifically:

```java
try {
    data.readFully(payload);
} catch (java.io.EOFException e) {
    // Input data is shorter than payload.length.
    throw e;
} catch (java.io.IOException e) {
    // Other I/O error.
    throw e;
}
```

This is an **illustrative snippet**, requiring initialized `DataInputStream data`, `byte[] payload`, and a method declaring `throws IOException` or handling it further. Avoid catching generic `Exception` and returning an empty string, as doing so makes it impossible to distinguish a "valid empty record" from a "failed record".

### Retries and Re-readability

Retrying makes sense if the cause may be transient and the caller has a recoverable source or can re-request data. For a partially consumed stream, **never assume** you can rewind and read again. `mark/reset` is only available under specific stream contracts, and sockets generally cannot rewind already consumed bytes.

If partial output has already been written before truncation is detected, manage **atomicity**: write to a temporary file, verify completion/integrity, and only then rename or commit, rather than publishing a half-written file as a success. Atomic move guarantees depend on platform and filesystem.

### Closing Resources

Use `try-with-resources` for sources/destinations you own. Closing resources prevents leaking file descriptors/sockets, yet **is not a completeness check**. Validate length, delimiter, checksum, or parser state **before** marking a task successful.

## 17. Common Programming Mistakes

1. **Treating `read() == -1` as always an error.** If the contract is read-to-EOF, this is normal termination.
2. **Returning success on EOF for every message.** If a frame requires N bytes, EOF before N is truncation.
3. **Treating a short read as the end.** A single `read(buffer)` is not a promise to fill the buffer.
4. **Failing to compare `readNBytes(n).length` with `n`.** The API can return fewer than n bytes at EOF.
5. **Using `available() == 0` to conclude EOF.** It only reflects an estimated non-blocking readable count, not message completion.
6. **Forgetting `readFully`/header length validation.** Missing data or malicious headers can cause errors or uncontrolled memory allocation.
7. **Using `String.length()` as UTF-8 byte length.** A non-BMP emoji takes two UTF-16 code units but four UTF-8 bytes.
8. **Assuming `readLine()` distinguishes whether the last line has a newline.** This method strips terminators.
9. **Treating any file without a trailing LF as truncated.** Check whether the format actually mandates a trailing LF.
10. **Using a default replacing decoder for strict text validation.** Truncated UTF-8 at file end can turn into `U+FFFD` instead of failing.
11. **Failing to distinguish timeout from EOF.** Timeout means not finished in time; it does not prove the source closed.
12. **Assuming one `SocketChannel.read` equals one message.** TCP can fragment or coalesce bytes arbitrarily.
13. **Assuming checksums are always sufficient.** A checksum verifies one integrity layer under a specific trust model; it does not replace framing or schema validation.
14. **Ignoring trailing data after a single message.** If the format allows exactly one frame, leftover bytes also violate the contract.
15. **Assuming `readAllBytes` succeeding means valid file format.** It only read to EOF; a parser/validator must still inspect the content.
16. **Keeping an incomplete output file as a finished file.** Publish output only after all completion conditions are confirmed.

## 18. Quick Decision Table

| Goal | Success Signal | Approach |
|---|---|---|
| Traverse bytes to source end | `read() == -1` after processing all prior bytes | `read` loop to EOF |
| Read exact N-byte field | Accumulated **exact N bytes** | `readFully`, or `readNBytes` + length check |
| Read 4-byte header | `readInt` reads completely | Catch `EOFException` when short |
| Read length-prefixed frame | Valid header and full body matching length | Validate length, `readFully`, validate payload |
| Read free-form text file | Parser accepts all input | `BufferedReader`/`Files`, check format rules |
| Verify trailing newline | Terminator present per contract | Inspect raw text/bytes, not just `readLine()` |
| Verify valid UTF-8 text | Strict decoder accepts all bytes | `CharsetDecoder` with `REPORT` |
| Handle non-blocking socket | Parser received complete frame, not just one readable `read` | Accumulate state across reads |
| Detect truncated download | Expected bytes and integrity per trusted metadata | Length + checksum/hash when available |
| Handle transient error | Retry/cancel under clear policy | Distinguish timeout, EOF, `IOException` |

## 19. Self-Check

**Question 1.** An `InputStream` contains only 2 bytes. Three `read()` calls return 10, 20, -1. Can we conclude the data is truncated?  
**Answer:** No. Normal EOF for a 2-byte source; it is only truncated if a contract requires more.

**Question 2.** `input.readNBytes(100)` returns a 73-byte array without throwing an exception. Is that valid?  
**Answer:** Yes per the API, if EOF arrives early. However, if the caller **requires** 100 bytes, it must report 27 missing bytes.

**Question 3.** Why can `DataInputStream.readFully` throw `EOFException` while `InputStream.read()` returns `-1`?  
**Answer:** `readFully` has a completion condition of **reading enough bytes**, so EOF beforehand is exceptional; a single `read()` merely reports source status.

**Question 4.** `BufferedReader.readLine()` returns `"last"` and the next call returns `null`. Does the file have a trailing LF?  
**Answer:** Cannot tell from `readLine()` alone, because terminators are stripped.

**Question 5.** A message header declares a 64-byte body, yet only 30 bytes arrive before TCP FIN. What is that?  
**Answer:** EOF at the byte stream level; **truncation at the framing layer** because 34 bytes are missing relative to the declaration.

**Question 6.** Non-blocking `SocketChannel.read` returns `0`. Is this EOF?  
**Answer:** No. The call read zero bytes at that moment; EOF is indicated by `-1` under the corresponding contract.

**Question 7.** A UTF-8 byte stream ends with `E2 82` followed by EOF. Can it be considered valid UTF-8 text?  
**Answer:** No. A strict decoder detects an incomplete multi-byte encoded sequence at end of input.

**Question 8.** A text file ends right after the last character of a line with no LF. Is that automatically an error?  
**Answer:** No; it depends on whether the format requires a trailing newline.

## Conclusion

**EOF is the source's signal that no more data remains, whereas "truncated data" is a conclusion based on the full contract of a format or protocol.** Java uses `-1` or `null` to indicate normal termination in many read APIs; exact-read operations like `DataInputStream.readFully` can throw `EOFException` when mandatory bytes are missing. To avoid mistakenly accepting an incomplete message, define length, delimiter, footer, checksum, or parser state explicitly; verify sufficient data, handle timeouts and I/O failures separately, and manage resource lifecycles properly.

### Java SE 17 Reference Documentation

- [`InputStream`: `read`, `readNBytes`, `readAllBytes`, `transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`DataInputStream`: `readInt`, `readFully`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [`EOFException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html)
- [`BufferedReader.readLine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [`SocketChannel.read`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [`CharsetDecoder` and `CodingErrorAction`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html)

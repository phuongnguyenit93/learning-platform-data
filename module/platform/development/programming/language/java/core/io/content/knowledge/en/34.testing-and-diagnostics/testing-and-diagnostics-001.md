# Testing with In-Memory Streams Before Depending on Real Files in Java I/O

## 1. Goal of the Testing Strategy

When a feature is responsible for **reading data, transforming content, and writing results**, bugs in byte- or character-processing algorithms can often be found without creating files on disk. Instead of hardwiring logic to `Path`, `FileInputStream`, or `FileOutputStream`, separate the **data processing logic** from **resource opening** and test the processing part using streams stored in RAM.

For example, to test a copy operation:

~~~text
Tightly coupled to files:
  Input Path -> Files.newInputStream -> copy -> Files.newOutputStream -> Target Path
                  ^                       ^     ^
                  |                       |     |
           hard to isolate       logic mixed with real I/O

Decoupled approach:
  InputStream  ----------------> copy(input, output) ----------------> OutputStream
       ^                                                               ^
       |                                                               |
  ByteArrayInputStream                                     ByteArrayOutputStream
  (tested in RAM)                                          (tested in RAM)

In production:
  Files.newInputStream(path)                                Files.newOutputStream(path)
~~~

With this model, the same `copy(InputStream, OutputStream)` method runs on **in-memory data** in unit tests and **real files** in integration tests; there is no need to fork the logic into two versions.

Common benefits:

- **Fast and repeatable:** does not depend on directory location, write permissions, conflicting file names, or disk space when testing only the algorithm.
- **Easy to pinpoint bugs:** wrong offsets, byte ordering, encoding, EOF, or `flush` calls show up directly through the expected byte array or string.
- **Fault injection in tests:** you can create a mock stream that limits bytes per read, or intentionally throws an `IOException`.
- **Minimal side effects:** tests create no leftover files, have fewer cleanup issues, and avoid modifying user data.
- **Easy to parallelize:** each test owns its own independent byte arrays and stream objects.

However, in-memory testing **does not completely replace** integration tests with the filesystem: access permissions, symlinks, symbolic link races, locks, concurrent file modifications, durability, differences across providers, and path name handling still need to be tested in an appropriate environment.

## 2. Understanding the Two Layers: Byte Streams and Character Streams

Java I/O distinguishes two stream hierarchies:

| Group | Base Types | In-Memory Implementation | Used to Test |
| --- | --- | --- | --- |
| Byte-oriented | `InputStream` / `OutputStream` | `ByteArrayInputStream` / `ByteArrayOutputStream` | Binary files, byte protocols, checksums, ZIP, encrypted data. |
| Character-oriented | `Reader` / `Writer` | `StringReader` / `StringWriter` | Decoded text content, parsers, line normalization, templates. |
| Array-based character-oriented | `Reader` / `Writer` | `CharArrayReader` / `CharArrayWriter` | Operations working directly on `char[]`, testing character slices. |

**Bytes are not synonymous with characters.** An accented Vietnamese character like `é` uses multiple bytes when encoded in UTF-8, whereas when handled through a `Reader`, the program sees one or more **UTF-16 code units** depending on the code point. If a feature needs to test encoding, use `ByteArrayInputStream` combined with `InputStreamReader` and an explicit charset—do not use `StringReader` and claim UTF-8 was tested.

For text, answer these questions first:

- Is the unit under test responsible for **decoding bytes into characters**?
- Or does the unit under test only **process text** after the charset has already been chosen?

If testing only a character parser, `StringReader` helps isolate the logic. If you want to catch decoding errors, malformed UTF-8, or BOMs, you must test at the byte-to-character layer.

## 3. ByteArrayInputStream: Building Input in RAM

`ByteArrayInputStream` reads from an existing `byte[]`:

~~~java
byte[] fixture = {10, 20, 30};
try (InputStream in = new ByteArrayInputStream(fixture)) {
    System.out.println(in.read()); // 10
    System.out.println(in.read()); // 20
    System.out.println(in.read()); // 30
    System.out.println(in.read()); // -1: EOF
}
~~~

This is a **code snippet placed inside a method**; it requires importing `java.io.InputStream` and `java.io.ByteArrayInputStream`. `read()` returns an `int` from 0 to 255 or `-1` on EOF, without using a negative `byte` to represent EOF.

Key points to remember:

1. The constructor `ByteArrayInputStream(byte[])` uses **the passed-in array** without copying all of it. If the test mutates the array after creating the stream, the data read may also change.
2. `ByteArrayInputStream(byte[], offset, length)` can simulate a data slice starting from a non-zero position.
3. The stream supports `markSupported() == true`, `mark(...)`, and `reset()`. This is useful for testing code that needs to peek ahead and rewind, but **you must not infer that every `InputStream` supports mark/reset**.
4. `available()` reports the remaining bytes in this specific memory stream. For general I/O sources, `available()` is **not** the total content size and is not a way to detect EOF.
5. `ByteArrayInputStream.close()` does nothing. Do not rely on that behavior to conclude that closing a caller's input stream in your code is always harmless.

When using Vietnamese strings as fixtures, you must specify a concrete charset:

~~~java
byte[] inputBytes = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
InputStream in = new ByteArrayInputStream(inputBytes);
~~~

This is an illustrative snippet requiring `java.nio.charset.StandardCharsets`. Do not use `getBytes()` without a charset if byte output must be consistent across environments.

## 4. ByteArrayOutputStream: Observing Output Without Files

`ByteArrayOutputStream` writes bytes into an automatically growing buffer:

~~~java
ByteArrayOutputStream out = new ByteArrayOutputStream();
out.write(new byte[] {65, 66, 67});
byte[] written = out.toByteArray();
System.out.println(Arrays.toString(written)); // [65, 66, 67]
~~~

The snippet above requires `java.io.ByteArrayOutputStream` and `java.util.Arrays`. `toByteArray()` returns **an independent copy** of the current contents. It can be called again after writing more data to observe the new bytes.

Some useful APIs:

| API | Meaning |
| --- | --- |
| `new ByteArrayOutputStream()` | Creates an output buffer in RAM. |
| `new ByteArrayOutputStream(initialCapacity)` | Chooses initial capacity without limiting final length. |
| `write(int b)` | Writes one byte, using the low 8 bits. |
| `write(byte[], off, len)` | Writes the exact specified array region. |
| `size()` | Number of bytes written. |
| `toByteArray()` | Returns a copy of the current byte content. |
| `toString(StandardCharsets.UTF_8)` | Decodes bytes using the given charset, convenient for text tests. |
| `reset()` | Clears logical content so the object can be reused. |
| `writeTo(OutputStream out)` | Copies current contents to another output stream. |

**Limitation:** this buffer keeps the entire output in RAM. For multi-gigabyte data, testing with a `ByteArrayOutputStream` does not reflect the memory characteristics of real streaming files/streams; you can use a mock output that counts bytes or computes a checksum without accumulating every byte.

`ByteArrayOutputStream.close()` has no effect; writes after `close` can still succeed. `FileOutputStream` or normal network outputs do not behave that way. Therefore, if you want to verify proper ownership/close semantics, you need a mock stream that tracks `close` or a real integration test.

## 5. Designing Testable Code: Accept Streams Instead of Opening Paths Directly

**Do not place `Files.newInputStream(...)` directly inside the algorithm method** if the logic needs unit testing independent of the filesystem. Separate into two layers:

~~~java
// Logic testable in RAM:
static long copy(InputStream source, OutputStream target)
        throws IOException {
    byte[] buffer = new byte[8192];
    long copied = 0;
    int n;

    while ((n = source.read(buffer)) != -1) {
        if (n == 0) {
            throw new IOException("InputStream không tiến triển");
        }
        target.write(buffer, 0, n);
        copied += n;
    }
    target.flush();
    return copied;
}

// Adapter opening actual files:
static long copyFile(Path from, Path to) throws IOException {
    try (InputStream source = Files.newInputStream(from);
         OutputStream target = Files.newOutputStream(to)) {
        return copy(source, target);
    }
}
~~~

These two methods are **code snippets**, requiring imports for `java.io.*`, `java.nio.file.Files`, and `Path`.

Ownership conventions:

- `copy(InputStream, OutputStream)` **does not close** the streams passed by the caller, because the caller may want to keep using them or pass the output to another step.
- `copyFile(Path, Path)` **owns** the two resources it opened, so it closes them with `try-with-resources`.
- `flush()` is called upon a successful copy to support buffered outputs; however, `flush` does not mean the data has been durably synchronized to the storage device.
- If the output targets an existing file, `Files.newOutputStream(to)` may create/truncate by default per the API. Production code must separately decide on overwrite, atomic replace, backups, permissions, and error handling.
- If input and output point to the same file, the adapter above can corrupt data. Check and handle as required; in-memory unit tests will **not detect** this issue.

A standard `read(buffer)` loop on an `InputStream` with a positive-length array follows the contract of waiting for at least one byte or EOF; the `n == 0` branch here catches unusual implementations or non-compliant wrappers. Do not apply this as a rule for non-blocking `SocketChannel.read(ByteBuffer)`, where `0` is a valid result.

## 6. What Should Basic Tests Cover?

A unit test for stream copying or transformation needs more than just a "hello world" case. At minimum, test:

| Case | Data / Scenario | What to Verify |
| --- | --- | --- |
| Empty input | `byte[0]` | Empty output, byte count 0, no exception. |
| Single byte | A value such as `0xFF` | Unsigned byte preserved, proper EOF. |
| Multi-chunk buffer | Input longer than buffer | No missing/duplicate bytes, order preserved. |
| Short reads | Stream returns at most 1–2 bytes per read | Code uses `n`, does not assume a read fills the buffer. |
| Special bytes | `0x00`, `0x80`, `0xFF` | Does not confuse null byte with end of data. |
| Multi-byte UTF-8 | `"AéB"`, `"Tiếng Việt"` | Exact byte and charset verification. |
| Output failure | Wrapper throws `IOException` after a few bytes | Exception is propagated/handled properly, does not report success. |
| Input failure | Stream throws an error after several reads | Does not swallow error, does not produce bogus successful output. |
| Flush/close | Stream tracks flush/close counts | Ownership matches the contract. |
| Mark/reset | Streams with and without support | Code does not wrongly depend on `ByteArrayInputStream` behavior. |
| Partial parsing | Header/payload split across chunks | Parser retains incomplete data and detects premature EOF. |

The number of bytes returned by a single `InputStream.read(byte[])` call **can be smaller than the array length**, even when more data remains to be read. Tests should deliberately trigger that condition.

## 7. Standalone Java 17+ In-Memory Test Program

The example below includes:

- `copy(...)` as the logic under test.
- `TwoByteInputStream`: a wrapper that deliberately allows at most two bytes per read.
- `FailAfterThreeBytesOutputStream`: a mock output that throws `IOException` as soon as the application tries to write the fourth byte.
- Assertions using `require(...)` that throw `AssertionError` on failure; no external test library beyond the JDK is needed.
- Tests for UTF-8 data `AéB`, empty input, chunked reads, character streams, and binary `DataInput`/`DataOutput`.

Save the file as `MemoryStreamTestDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.Reader;
import java.io.StringReader;
import java.io.StringWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class MemoryStreamTestDemo {

    static long copy(InputStream source, OutputStream target)
            throws IOException {
        byte[] buffer = new byte[4];
        long total = 0;
        int n;
        while ((n = source.read(buffer)) != -1) {
            if (n == 0) {
                throw new IOException("InputStream không tiến triển");
            }
            target.write(buffer, 0, n);
            total += n;
        }
        target.flush();
        return total;
    }

    static long copyChars(Reader source, Writer target)
            throws IOException {
        char[] chars = new char[3];
        long total = 0;
        int n;
        while ((n = source.read(chars)) != -1) {
            if (n == 0) {
                throw new IOException("Reader không tiến triển");
            }
            target.write(chars, 0, n);
            total += n;
        }
        target.flush();
        return total;
    }

    static final class TwoByteInputStream extends ByteArrayInputStream {
        TwoByteInputStream(byte[] data) {
            super(data);
        }

        @Override
        public synchronized int read(byte[] bytes, int offset, int length) {
            return super.read(bytes, offset, Math.min(length, 2));
        }
    }

    static final class FailAfterThreeBytesOutputStream
            extends OutputStream {
        private int accepted;

        @Override
        public void write(int b) throws IOException {
            if (accepted >= 3) {
                throw new IOException("Injected output error");
            }
            accepted++;
        }
    }

    static void require(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] original =
                "AéB".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        long count;
        try (InputStream input = new TwoByteInputStream(original)) {
            count = copy(input, output);
        }

        require(count == 4, "Số byte sao chép");
        require(Arrays.equals(original, output.toByteArray()),
                "Nội dung byte không giống input");
        System.out.println("copiedBytes=" + count);
        System.out.println("copiedText=" +
                output.toString(StandardCharsets.UTF_8));

        ByteArrayOutputStream emptyOutput =
                new ByteArrayOutputStream();
        long emptyCount = copy(
                new ByteArrayInputStream(new byte[0]), emptyOutput);
        require(emptyCount == 0 && emptyOutput.size() == 0,
                "Input rỗng phải cho output rỗng");
        System.out.println("emptyBytes=" + emptyCount);

        StringWriter writer = new StringWriter();
        long chars = copyChars(
                new StringReader("abc\nxyz"), writer);
        require(chars == 7 && writer.toString().equals("abc\nxyz"),
                "Character stream bị đổi nội dung");
        System.out.println("copiedChars=" + chars);
        System.out.println("textLines=" +
                writer.toString().replace("\n", "|"));

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream data =
                new DataOutputStream(bytes)) {
            data.writeInt(0x01020304);
            data.writeUTF("Hi");
        }

        try (DataInputStream data = new DataInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            int value = data.readInt();
            String text = data.readUTF();
            require(value == 0x01020304 && text.equals("Hi"),
                    "Sai định dạng dữ liệu nhị phân");
            System.out.println("dataBytes=" + bytes.size());
            System.out.println("dataRoundTrip=" +
                    Integer.toHexString(value) + ":" + text);
        }

        boolean writeErrorCaught = false;
        try {
            copy(
                    new ByteArrayInputStream(new byte[] {1, 2, 3, 4, 5}),
                    new FailAfterThreeBytesOutputStream());
        } catch (IOException expected) {
            writeErrorCaught = true;
        }
        require(writeErrorCaught, "Lỗi output phải được báo");
        System.out.println("writeErrorCaught=" + writeErrorCaught);
        System.out.println("allChecksPassed=true");
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 MemoryStreamTestDemo.java
java MemoryStreamTestDemo
~~~

**Exact stdout on Java 17+ when running the program with a UTF-8 source file:**

~~~text
copiedBytes=4
copiedText=AéB
emptyBytes=0
copiedChars=7
textLines=abc|xyz
dataBytes=8
dataRoundTrip=1020304:Hi
writeErrorCaught=true
allChecksPassed=true
~~~

### 7.1. Why Is `copiedBytes=4` Instead of 3?

The string `AéB` has three visible characters, but `é` has Unicode code point U+00E9, which is encoded as **two UTF-8 bytes**. The byte sequence is:

~~~text
'A'    'é'      'B'
41     C3 A9    42
     total: 4 bytes
~~~

`TwoByteInputStream` prevents the algorithm from assuming a single `read` fills the 4-byte buffer. Finally, `Arrays.equals` compares **the byte data** exactly against the original. If a developer mistakenly writes `target.write(buffer)` instead of `write(buffer, 0, n)`, testing with short reads or a short final chunk will catch the extra trailing bytes.

### 7.2. Why Is `copiedChars=7`?

The string `"abc\nxyz"` has seven UTF-16 code units: three letters, one newline, and three letters. In `Reader`/`Writer`, the count is in `char` units, **which is not automatically equal to the number of UTF-8 bytes**, nor is it the number of Unicode code points when supplementary characters are present.

### 7.3. Why Is `dataBytes=8`?

`DataOutputStream.writeInt` writes **4 big-endian bytes** for `0x01020304`. `writeUTF("Hi")` writes the length in modified UTF-8 according to the `DataOutput` format in **2 bytes**, followed by the two bytes `'H'` and `'i'`. The total is `4 + 2 + 2 = 8`. `DataInputStream.readUTF` is compatible with this modified UTF-8 format, unlike arbitrarily using a raw UTF-8 string without a length prefix.

### 7.4. Why Is Output Failure Tested Separately?

`FailAfterThreeBytesOutputStream` accepts three bytes and deliberately throws an error when writing the fourth byte. `OutputStream.write(byte[], off, len)` by default can call `write(int)` byte by byte, so the error propagates up to `copy`. The test confirms that the program **does not pretend the copy succeeded** when the output fails. In a real application, you must also check what state the target file is left in after an error and establish a temporary file cleanup or rollback policy.

## 8. StringReader and StringWriter: Testing Character Parsers

`StringReader` reads characters from a `String`, while `StringWriter` writes characters into a growable memory buffer. No charset conversion happens inside these two classes.

For example, a parser that only needs to normalize lines:

~~~java
static String linesToCsvLike(Reader reader) throws IOException {
    BufferedReader input = new BufferedReader(reader);
    StringJoiner result = new StringJoiner(",");
    String line;
    while ((line = input.readLine()) != null) {
        result.add(line.trim());
    }
    return result.toString();
}
~~~

This is a **method snippet**, requiring imports for `BufferedReader`, `Reader`, `IOException`, and `StringJoiner`. The method does not close `reader` because the resource is owned by the caller.

Test completely in memory:

~~~java
String actual = linesToCsvLike(
        new StringReader("  blue \r\n green\nred"));
if (!actual.equals("blue,green,red")) {
    throw new AssertionError(actual);
}
~~~

Because `BufferedReader.readLine()` strips line terminators supported by the API, the output can be verified reliably for fixtures containing both `\r\n` and `\n`.

**Note:** `StringReader` receives already-decoded Java characters, so this test **will not detect UTF-8 decoding bugs** in real files. If the parser depends on BOM handling, newline encoding, or malformed bytes, test the decoder layer separately using `InputStreamReader`.

### 8.1. CharArrayReader and CharArrayWriter

These two classes are useful if the system already holds a `char[]` or only wants to read a slice of a character array:

~~~java
char[] chars = {'a', 'b', 'c', 'd'};
try (Reader reader = new CharArrayReader(chars, 1, 2);
     CharArrayWriter writer = new CharArrayWriter()) {
    reader.transferTo(writer);
    System.out.println(writer.toString()); // bc
}
~~~

This is a code snippet requiring `java.io.*`. Note that `Reader.transferTo(Writer)` was added in Java 10, so it works on Java 17.

## 9. Testing the Charset Layer with Byte Streams

One risk is relying on the machine's default charset, causing code to produce different results on CI versus a developer's local machine.

Always pass the charset explicitly or fix it to `StandardCharsets.UTF_8`:

~~~java
static String readUtf8(InputStream source) throws IOException {
    try (Reader reader =
            new InputStreamReader(source, StandardCharsets.UTF_8)) {
        StringWriter writer = new StringWriter();
        reader.transferTo(writer);
        return writer.toString();
    }
}
~~~

This is an **illustrative method snippet**; it requires importing `InputStreamReader`, `InputStream`, `StringWriter`, and `StandardCharsets`. Here the method **closes the Reader and therefore closes the underlying InputStream**: this behavior differs from `copy` earlier. Choose an ownership contract consistent with your design, or let the caller manage the Reader if the caller owns the source.

Unit test:

~~~java
byte[] utf8 = "Tiếng Việt".getBytes(StandardCharsets.UTF_8);
String actual = readUtf8(new ByteArrayInputStream(utf8));
if (!"Tiếng Việt".equals(actual)) {
    throw new AssertionError(actual);
}
~~~

If you need to test **malformed UTF-8**, `InputStreamReader` by default typically replaces invalid data with the replacement character according to the decoder configuration. To test rejecting invalid bytes rather than silently replacing them, create a `CharsetDecoder` with `CodingErrorAction.REPORT` and test the `MalformedInputException` handling branch. The replace vs. report policy should be part of the application contract.

In particular, reading byte chunks and calling `new String(chunk, UTF_8)` independently on each chunk can corrupt a multi-byte UTF-8 character split across two chunks. A stateful stream decoder is the right approach when processing text across multiple reads.

## 10. Fault Injection to Test Failure Paths

Standard memory streams usually succeed so fast that they can **mask error-handling bugs**. You can create test doubles using subclasses or wrappers:

- `FilterInputStream`: limit the number of bytes per read, log read counts, or throw an error on a specific call.
- `FilterOutputStream`: track `flush`/`close` and reject writes after a threshold.
- Custom `InputStream`: test EOF immediately after the header, a stream returning one byte at a time, or mid-stream I/O errors.
- Custom `OutputStream`: simulate disk-full, broken pipe, or permission errors, keeping in mind this is only a **simulation** of API outcomes.

### 10.1. Limiting Bytes per Read

~~~java
final class OneByteAtATime extends FilterInputStream {
    OneByteAtATime(InputStream inner) {
        super(inner);
    }

    @Override
    public int read(byte[] bytes, int offset, int length)
            throws IOException {
        return super.read(bytes, offset, Math.min(length, 1));
    }
}
~~~

This is a class declaration snippet requiring `java.io.FilterInputStream`, `InputStream`, and `IOException`. When `length == 0`, the wrapper still passes 0 down to the inner stream, preserving zero-length read behavior.

Important reason: a correct algorithm must not rely on "`read(buffer)` always returns `buffer.length`"; many real sources return fewer bytes due to network behavior, buffering, or EOF.

### 10.2. Tracking Flush and Close

~~~java
final class TrackingOutputStream extends ByteArrayOutputStream {
    int flushCount;
    int closeCount;

    @Override
    public void flush() throws IOException {
        flushCount++;
        super.flush();
    }

    @Override
    public void close() throws IOException {
        closeCount++;
        super.close();
    }
}
~~~

This is a class snippet you can place in tests with the corresponding imports. With the `copy` design in section 5, we expect:

- After a successful copy, `flushCount == 1`.
- `closeCount == 0` because `copy` does not own the output stream.
- Only when the caller closes the output itself does `closeCount` increment.

If a test needs to verify that resources are closed on error, create a wrapper with close tracking and test the adapter code that uses `try-with-resources`. Do not turn every processing helper into a method that closes the caller's stream.

### 10.3. Testing Mid-Stream InputStream Failures

A class can throw an error after two bytes:

~~~java
final class FailAfterTwoBytes extends InputStream {
    private int position;

    @Override
    public int read() throws IOException {
        if (position == 2) {
            throw new IOException("Injected read error");
        }
        position++;
        return 'x';
    }
}
~~~

This is a test class snippet. Note that the default `InputStream.read(byte[],off,len)` implementation may **return the bytes already read successfully before encountering an IOException**, and then throw on the subsequent call. Therefore, do not write a test demanding "the first call must throw" when the wrapper may return a partial read first.

You should verify that the error is eventually propagated to the caller, not silently ignored or turned into a false result claiming all data was copied.

## 11. What Can In-Memory Tests Miss?

Testing with `ByteArrayInputStream`/`ByteArrayOutputStream` is useful, but it does not completely model the production environment:

| Important Behavior | In-Memory Test | Why Real Files / Other Environments Are Needed |
| --- | --- | --- |
| Reading/writing bytes and transformations | Very well suited. | Algorithms can be tested thoroughly. |
| EOF, short reads, simulated errors | Can be simulated proactively. | Mock streams only simulate scenarios you thought of. |
| Charset encoding/decoding | Testable with byte fixtures. | Providers, file BOMs, and real-world data can vary more widely. |
| Access permissions and ACLs | Not truly simulated. | The OS/provider enforces permissions. |
| Symlinks / path traversal / TOCTOU | Insufficient. | Involves real paths and file system objects. |
| Size / durability after flush | Not verified. | `flush` is not equivalent to `FileChannel.force`/fsync. |
| File locks and concurrent writers | Unrealistic. | Requires process/thread/filesystem tests. |
| File names, separators, case sensitivity | Absent in byte streams. | Varies by OS/provider. |
| Atomic move/rename | Not tested. | Depends on the filesystem. |
| File truncated while reading | Can mock stream errors, insufficient. | Needs testing of real file/ownership mechanisms. |
| Buffering/closing of files/network | Only per custom wrappers. | Runtime/OS has its own semantics. |
| ZIP/GZIP compression/decompression | Works very well with byte arrays. | If relying on file metadata/quota/path extraction, test separately. |

A passing memory-stream test proves that **the tested logic behaves correctly on the given inputs and stream doubles**, not that all real resources will behave properly.

## 12. When to Move from Unit Tests to File Integration Tests?

A practical progression:

1. **Test the core** with `ByteArrayInputStream`/`ByteArrayOutputStream` or `StringReader`/`StringWriter`: payloads, empty inputs, chunks, EOF, and simulated I/O errors.
2. **Test the adapter** that opens files using a temporary directory via `Files.createTempDirectory` or JUnit `@TempDir`: verify paths, permissions, resource closing, and expected file contents.
3. **Test formats** with real files/streams for XML, JSON, ZIP, GZIP, or binary protocols: charsets, metadata, and structure.
4. **Test special environments** when required: read-only filesystems, missing permissions, symbolic links, atomic moves, file locks, concurrent file modifications, and networking.
5. **E2E / stress tests** for large data, contention, high load, timeouts, resource leaks, and post-crash behavior.

It is not strictly necessary to run all integration tests on every minor edit, but CI should have at least one suite testing real file adapters across target platforms.

### 12.1. Testing with Temporary Files to Verify the Adapter

~~~java
Path input = Files.createTempFile("input-", ".bin");
Path output = Files.createTempFile("output-", ".bin");
try {
    byte[] original = {0, 1, 2, (byte) 0xFF};
    Files.write(input, original);

    long count = copyFile(input, output);
    if (count != original.length
            || !Arrays.equals(original, Files.readAllBytes(output))) {
        throw new AssertionError("File adapter sai");
    }
} finally {
    Files.deleteIfExists(input);
    Files.deleteIfExists(output);
}
~~~

This is an **illustrative integration snippet**, assuming the `copy`/`copyFile` methods from earlier are declared and `Files`, `Path`, `Arrays` are imported. In real tests, use a dedicated temporary directory rather than predictable names; JUnit provides `@TempDir` to supply an isolated directory and clean it up after the test.

**Do not create temporary files in a shared location and assume no one else can modify them.** When handling untrusted data, appropriate permissions/ownership policies must be enforced. `Files.createTempFile` generates hard-to-guess names and creates files atomically per the provider, but security assumptions still depend on the operating system.

## 13. Testing with JUnit 5 Instead of a `main` Method Throwing `AssertionError`

`MemoryStreamTestDemo` runs with only Java 17, which suits a standalone example. In real projects, split each case into a test method using JUnit Jupiter and integrate with Maven/Gradle.

Example of a test method (not standalone code without JUnit):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

@Test
void copyWorksWithShortReads() throws IOException {
    byte[] original = "AéB".getBytes(StandardCharsets.UTF_8);

    ByteArrayOutputStream target = new ByteArrayOutputStream();
    try (InputStream source = new TwoByteInputStream(original)) {
        long copied = copy(source, target);
        assertEquals(original.length, copied);
    }

    assertArrayEquals(original, target.toByteArray());
}
~~~

The code above assumes `copy` and `TwoByteInputStream` exist in the test class, along with imports for `java.io.*` and `StandardCharsets`. It requires the JUnit Jupiter dependency and a corresponding test runner, unlike the dependency-free `main` example in section 7.

### 13.1. Asserting According to Contract Semantics

- **`assertArrayEquals(expected, actual)`:** exact byte-by-byte verification for binary payloads.
- **`assertEquals(expectedText, actualText)`:** suitable for text output once the charset is defined.
- **`assertThrows(IOException.class, ...)`:** verifies failure paths throw the expected exception type.
- **`assertTimeout...`:** use cautiously; a test timeout does not prove all production I/O has proper deadlines.
- **`@TempDir`:** for filesystem integration tests without guessing file names or polluting the repository.

Do not merely use `assertTrue(output.size() > 0)` for a copy algorithm. It will not catch missing bytes, duplicated bytes, wrong order, or wrong encoding.

## 14. Rules for Creating Stable and Diagnosable Fixtures

A good test should have **minimal environment dependence**:

- Do not use `Charset.defaultCharset()` or `String.getBytes()` without a charset when tests need deterministic byte results.
- Do not depend on the OS line separator: use `\n`/`\r\n` explicitly defined by the test or normalize output before comparing, depending on requirements.
- Do not use `System.currentTimeMillis()` for expected content when you can inject a mock clock or fixed value.
- Do not rely on the iteration order of `Files.list`/directory iteration unless a sort rule is applied.
- Do not hardcode network ports when the OS can assign port 0, though that crosses into network integration testing rather than in-memory unit testing.
- Do not share mutable arrays or streams across tests running in parallel; create separate fixtures for each test.
- On failure, include expected/actual byte counts and hex formatting for binary payloads in assertion messages.
- For Unicode tests, include multi-byte UTF-8 fixtures and supplementary code points when logic handles code points.
- Never accidentally place real sensitive data into test fixtures or CI logs.

## 15. Which Mock Stream to Choose for Each Case?

| What You Want to Test | Suggestion |
| --- | --- |
| Byte copying and exact byte comparison | `ByteArrayInputStream` + `ByteArrayOutputStream`. |
| Text line parser | `StringReader` / `BufferedReader`. |
| Text output formatting | `StringWriter`. |
| UTF-8 conversion | `ByteArrayInputStream` + `InputStreamReader(UTF_8)`. |
| Writing length-prefixed bytes and binary numbers | `DataOutputStream` wrapping `ByteArrayOutputStream`. |
| Reading binary-number protocols | `DataInputStream` wrapping `ByteArrayInputStream`. |
| Slow reads / chunked reads | Custom `FilterInputStream` limiting read size. |
| Raising `IOException` | Custom `InputStream` / `OutputStream`. |
| Verifying `flush`/`close` | Wrapper counting invocations. |
| Counting very large output bytes without holding all in RAM | Custom `OutputStream` incrementing a counter/checksum only. |
| Checking paths / ACLs / symlinks / providers | Integration test with real files. |

A sustainable model is **stream-oriented core + resource-oriented adapters**. The core only knows `InputStream`/`OutputStream` or `Reader`/`Writer`, while adapters handle `Path`, file locks, buffering policy, charsets, and OS resource lifecycles.

## 16. Common Mistakes

### 16.1. Believing ByteArrayInputStream Behaves Like Every Real Source

`ByteArrayInputStream` typically returns data immediately and supports `mark/reset`, so code with faulty assumptions about short reads or `available()` may still "pass" basic tests. Add a mock stream that restricts read sizes, and never call `available()` to measure total input length in general code.

### 16.2. Always Passing `buffer.length` Instead of `n`

The last read may return fewer bytes than the buffer size; calling `output.write(buffer)` will write stale bytes from the previous read into the output. Use `write(buffer, 0, n)` with **the actual `n` received**.

### 16.3. Converting Text Using the Default Charset

`new String(bytes)` and `text.getBytes()` without a charset can differ across runtimes and operating systems. Explicitly specify `StandardCharsets.UTF_8` (or the protocol's charset) so tests are reproducible.

### 16.4. Failing to Separate Processing from File Opening

A method that accepts only `Path` and opens files in every branch forces core tests to create temporary files and coordinate unnecessary cleanup. Extract the core into a stream-accepting method and keep file-opening adapters at the boundary.

### 16.5. Closing the Caller's Stream Inside the Core

A helper method that closes a shared `OutputStream` can prevent downstream pipeline stages from writing further data. Define **who owns the stream** and test that contract. Testing solely with `ByteArrayOutputStream` may miss this bug because its `close()` is a no-op.

### 16.6. Testing Only the Happy Path

Omitting tests for empty input, short reads, encoding, binary data containing `0x00`, mid-stream `IOException`, and output error handling leaves most I/O bugs undetected.

### 16.7. Using Memory Output for Unbounded Large Data

`ByteArrayOutputStream` retains all bytes and can consume large amounts of memory. Stress tests for large data streams should use a byte-counting/checksum sink, or a temporary file environment with explicit limits.

### 16.8. Treating In-Memory Tests as Sufficient for Filesystem Semantics

Methods using `Files.move`, `Files.delete`, `FileChannel.force`, or file locks depend on the OS and provider; memory streams cannot verify their semantics. Appropriate integration tests are required.

### 16.9. Confusing Successful Writes with Durable Storage

`ByteArrayOutputStream.flush()` does not represent `fsync`. With real files, `OutputStream.flush()` does not guarantee by default that bytes are durably persisted on the device; when durability is required, inspect APIs such as `FileChannel.force` and provider documentation.

### 16.10. Writing Overly Complex Mock Files

Only mock **the behavior under test** (short chunk reads, errors, close tracking). Do not try to re-implement an entire filesystem inside a hard-to-verify mock; when you need to test paths or file attributes, switch to temporary files and the real provider.

## 17. Self-Check Questions

1. **Why does passing `InputStream`/`OutputStream` instead of only `Path` make tests faster?** Because you can substitute sources and targets with memory streams without accessing the filesystem for the algorithm.
2. **What does `ByteArrayInputStream.read()` return when data is exhausted?** `-1`.
3. **Does `ByteArrayInputStream` automatically copy the array passed into it?** No, it uses that array as its backing data.
4. **Does `ByteArrayOutputStream.toByteArray()` share its internal array?** No, it returns a copy.
5. **If a read receives 2 bytes into an 8-byte buffer, how many bytes should be written?** Exactly 2 bytes via `write(buffer, 0, 2)`.
6. **How many bytes is `AéB` in UTF-8?** 4 bytes.
7. **Does `StringReader` test UTF-8 decoding?** No; it reads characters that already exist.
8. **What should be used to test UTF-8 decoding from bytes?** `ByteArrayInputStream` with `InputStreamReader`/`CharsetDecoder` configured with an explicit charset and error policy.
9. **Why is a mark/reset test using only `ByteArrayInputStream` insufficient?** That stream supports mark, whereas many other streams do not.
10. **When output throws an `IOException` after a few bytes, may `copy` report success?** No; it must propagate or handle the error according to the contract.
11. **Who should close a stream passed by a caller to a helper?** According to the defined ownership; if the caller owns it, the helper must not close it.
12. **Does `ByteArrayOutputStream.flush()` prove data is durably persisted on disk?** No.
13. **When must you switch to testing with real files?** When checking file open/close, permissions, symlinks, atomic moves, metadata, file locks, durability, or provider behavior.
14. **Should you assert non-empty output instead of comparing all bytes?** No; missing, duplicated, or misordered bytes can still yield non-empty output.
15. **How do you simulate small read chunks in unit tests?** Use a custom `InputStream`/`FilterInputStream` that returns at most 1–2 bytes per call.
16. **Why do some malformed UTF-8 test cases require a `CharsetDecoder` with `REPORT`?** Because default decoding may replace invalid bytes with the replacement character rather than throwing the expected error.
17. **How do you test file copying with temporary files?** Write input, invoke the adapter, read output, compare bytes, and clean up resources—or use JUnit `@TempDir`.
18. **If logic relies on path uniqueness, are memory streams sufficient?** No. You need filesystem integration tests and an appropriate concurrency model.

## 18. Official Java 17 Documentation

- [ByteArrayInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayInputStream.html) and [ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html): in-memory byte streams.
- [StringReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringReader.html) and [StringWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/StringWriter.html): character streams.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html) and [OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): general contract, EOF, read/write.
- [InputStreamReader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStreamReader.html) and [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html): decoding bytes to characters.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): real file adapters, temporary files, and path operations.

**Remember:** before testing against real files, build a **core accepting `InputStream`/`OutputStream` or `Reader`/`Writer`** and verify it with `ByteArrayInputStream`/`ByteArrayOutputStream` and `StringReader`/`StringWriter`. Add fixtures for empty input, Unicode, short chunk reads, and `IOException` to test failure paths. Once the core is solid, use integration tests with temporary files to verify **filesystem semantics**—do not treat memory streams as a complete mock filesystem.

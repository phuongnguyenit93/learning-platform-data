# readNBytes and Its Differences from readAllBytes in Java I/O

**InputStream** reads byte-based data streams. Both **readNBytes(...)** and **readAllBytes()** return bytes taken from the *current position* of the stream, but they solve two different needs: **reading up to N bytes** and **reading the entire remaining content until EOF**. Choosing the wrong API can break message boundaries, read incomplete data, block indefinitely, or consume too much memory.

## 1. Methods to Distinguish

| InputStream API | Available Since Java | Returns | Stops When |
| --- | --- | --- | --- |
| **byte[] readNBytes(int len)** | 11 | A new array containing 0 to **len** bytes | **len** bytes read, EOF reached, or I/O error |
| **int readNBytes(byte[] b, int off, int len)** | 9 | Actual number of bytes written into the existing array | **len** bytes read, EOF reached, or I/O error |
| **byte[] readAllBytes()** | 9 | A new array containing all remaining bytes | EOF reached or I/O error |
| **int read(byte[] b)** | 1.0 | Number of bytes read, or **-1** at EOF | May return as soon as a partial set of bytes is read |

**EOF** (end of stream) means the end of the stream; **len** is the requested number of bytes, not the number of characters. All three of the first methods **do not close the InputStream**. They consume data strictly in order: bytes already read will not appear again, unless you create a new stream or set up and use reset on a stream that supports it.

A single **read(buffer)** call may return fewer bytes than the buffer size even though more data is available. **readNBytes(...)** attempts to keep reading until the specified number of bytes is reached; it may return fewer if EOF is encountered. If the program needs *exactly* N bytes, you must check the result yourself or use **DataInputStream.readFully(...)**.

## 2. How readNBytes(int len) Works

~~~java
byte[] firstFive = input.readNBytes(5);
~~~

With **len = 5**, Java attempts to read 5 bytes from the current position. If 5 bytes are available before EOF, the returned array has length 5 and the remaining data stays in the stream. If only 3 bytes remain until EOF, the method returns an array of length 3; **it does not automatically throw EOFException because 2 bytes are missing**. If already at EOF, the result is an empty array. If **len = 0**, it also returns an empty array without reading. **len < 0** causes an **IllegalArgumentException**.

The method may block the executing thread while waiting until **len** bytes are read, EOF is reached, or an I/O error occurs. A network stream that has only sent 3 bytes while keeping the connection open may cause **readNBytes(5)** to keep waiting for 2 more bytes. Therefore, **len** only limits the *number of bytes*, not the *wait time* at all.

The returned byte array matches the exact number of bytes actually received, without zero-padding to fill the requested size. However, it still requires memory proportional to the amount of data read and can encounter **OutOfMemoryError** if the requested amount is too large. Errors from the read source may throw **IOException**.

## 3. How readAllBytes() Works

~~~java
byte[] remaining = input.readAllBytes();
~~~

The **readAllBytes()** method reads until EOF, then returns an array containing **all remaining bytes**. If 4 bytes of a 10-byte stream have already been read and you then call **readAllBytes()**, the array will only have 6 bytes. The method does not rewind to the beginning of the stream.

Unlike **readNBytes(int len)**, **readAllBytes()** has no parameter to set a byte limit. With large files, untrusted sources, or infinite streams, loading all data into RAM can cause memory pressure or **OutOfMemoryError**. With a socket kept open, the call may keep waiting until EOF is received even if part of the data has already arrived.

**Do not use available() to measure the size of the entire stream**: it only indicates an estimate of bytes that can be read without blocking at that moment, not the total remaining bytes. Both APIs differ from checking what data is “currently available”.

## 4. Comparison by Practical Scenario

| Question | **readNBytes(int len)** | **readAllBytes()** |
| --- | --- | --- |
| Does it limit the data amount by a parameter? | Yes: at most **len** bytes | No |
| Does it keep reading until EOF even after N bytes are met? | No | Yes |
| What if EOF arrives early? | Returns an array that may be shorter than **len** | Returns all bytes obtained |
| What if the stream stays open when data is not enough yet? | May block waiting for N bytes | May block waiting for EOF |
| Suitable for reading an N-byte header/prefix? | Yes | No, because it will consume the rest as well |
| Suitable for reading a small, finite file? | If only the beginning or N bytes are needed | Yes, if the RAM cost is acceptable |
| Suitable for large data of unknown length? | Use in bounded chunks | Should be avoided |
| Does it close the stream after the call? | No | No |

If you need to read a data frame whose length is declared in a header, **readNBytes(expectedLength)** is useful because it can stop at that boundary. If the exact length is required, **you must check bytes.length**. If the goal is to retrieve an entire small resource with a clear EOF, **readAllBytes()** is more convenient.

## 5. Runnable Java 17+ Example: Bytes Read and Stream Position

Save as **ReadNBytesDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReadNBytesDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII);

        // Read 4 bytes, then read the remaining bytes.
        try (InputStream in = new ByteArrayInputStream(source)) {
            byte[] prefix = in.readNBytes(4);
            byte[] remaining = in.readAllBytes();
            System.out.println("prefix=" +
                    new String(prefix, StandardCharsets.US_ASCII));
            System.out.println("remaining=" +
                    new String(remaining, StandardCharsets.US_ASCII));
        }

        // Request more bytes than are available until EOF.
        try (InputStream in = new ByteArrayInputStream(
                "XYZ".getBytes(StandardCharsets.US_ASCII))) {
            byte[] five = in.readNBytes(5);
            byte[] afterEnd = in.readNBytes(2);
            System.out.println("requested=5, actual=" + five.length);
            System.out.println("bytes=" +
                    new String(five, StandardCharsets.US_ASCII));
            System.out.println("afterEOF=" + afterEnd.length);
        }

        // Variant that writes into an existing buffer, offset = 1.
        try (InputStream in = new ByteArrayInputStream(
                "123456".getBytes(StandardCharsets.US_ASCII))) {
            byte[] buffer = new byte[4];
            int count = in.readNBytes(buffer, 1, 3);
            System.out.println("buffer count=" + count + ", segment=" +
                    new String(buffer, 1, count, StandardCharsets.US_ASCII));
            System.out.println("tail=" +
                    new String(in.readAllBytes(), StandardCharsets.US_ASCII));
        }
    }
}
~~~

Compile/run:

~~~bash
javac ReadNBytesDemo.java
java ReadNBytesDemo
~~~

Output:

~~~text
prefix=ABCD
remaining=EFGHIJ
requested=5, actual=3
bytes=XYZ
afterEOF=0
buffer count=3, segment=123
tail=456
~~~

The first stream contains “ABCDEFGHIJ”; **readNBytes(4)** takes “ABCD”, and then **readAllBytes()** only takes “EFGHIJ”. The “XYZ” stream only has 3 bytes, so **readNBytes(5)** returns an array of length 3, and the next call at EOF returns an array of length 0. With a buffer of length 4, calling **readNBytes(buffer, 1, 3)** writes “123” into the elements from index 1 to 3; the 3 bytes “456” still remain.

## 6. readNBytes(byte[] b, int off, int len): Easy-to-Confuse Points with read

This overload takes an existing destination array and returns **int count** (the number of bytes just written), avoiding allocating a new array for every read. The positions containing the new data are **b[off]** through **b[off + count - 1]**. Other elements may still hold old data; do not process all **len** elements when **count < len**.

Boundary conditions and exceptions:

- Array **b** is null: **NullPointerException**.
- **off < 0**, **len < 0**, or **len > b.length - off**: **IndexOutOfBoundsException**.
- **len = 0**: returns 0, reads nothing.
- EOF before any byte is read: returns **0**, even when **len > 0**.
- EOF after receiving a partial read: returns the actual number of bytes read, which may be less than **len**.
- I/O error: may throw **IOException** after partially modifying the destination array.

An important difference: **read(...)** signals EOF with **-1** when a positive length is requested; **readNBytes(buffer, off, len)** returns **0** at EOF. Therefore, a loop using **while (n != -1)** written for **read(...)** cannot be copied verbatim to the **readNBytes** overload: it can easily loop infinitely at EOF.

If you need to read in fixed-size chunks from a finite stream, you can call **readNBytes(buffer, 0, buffer.length)** and process only the slice from index 0 to **count - 1**. With **count == 0** and a positive requested size, the stream has reached EOF under normal operating conditions.

## 7. Reading Exactly N Bytes for a Protocol: Checking EOF

A message may encode the payload length in its header. If the header says there are 5 bytes but the sender only transmits 3 bytes and closes the stream, **readNBytes(5)** returns 3 bytes. Treating that as a valid message is an application bug. You need to compare the length and throw **EOFException** when the data is truncated.

Example payload-reading method (save as **PayloadReader.java**; the class compiles standalone, though it has no **main** to run on its own):

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

public final class PayloadReader {
    private static final int MAX_PAYLOAD_BYTES = 1024 * 1024;

    private PayloadReader() {
    }

    public static byte[] readPayload(InputStream in, int expectedBytes)
            throws IOException {
        // Block negative/excessively large lengths, especially when taken from external input.
        if (expectedBytes < 0 || expectedBytes > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException("Invalid payload length");
        }

        byte[] payload = in.readNBytes(expectedBytes);
        if (payload.length != expectedBytes) {
            throw new EOFException(
                    "Truncated payload: expected " + expectedBytes +
                    " bytes, got " + payload.length);
        }
        return payload;
    }
}
~~~

**MAX_PAYLOAD_BYTES** sets a threshold to avoid arbitrary allocations when the length is supplied externally. For network sources, you also need to add a **timeout** at the protocol/connection level; setting a byte threshold does not prevent an open connection that stops sending data from causing the read operation to wait for a long time.

Another option for the requirement of **having to read exactly N bytes** is **DataInputStream.readFully(byte[])**: it throws **EOFException** if not enough bytes are read before EOF. **readNBytes(...)** intentionally returns shorter data at EOF, so their usage contracts are different.

## 8. Memory, Large Data, and Character Encoding

**InputStream** handles *bytes*, not *characters*. UTF-8 can encode one character using multiple bytes; taking exactly 5 bytes does not guarantee taking exactly 5 characters. You should not decode arbitrary fragments when boundaries may cut through the middle of a UTF-8 character. For text data, use an explicit charset such as **StandardCharsets.UTF_8**, or read via **InputStreamReader** when appropriate.

**readAllBytes()** is suitable for data that is **small, finite, and has a practical limit**. Multi-gigabyte files or infinite streams should be processed incrementally with a buffer, avoiding loading everything into an array. Example of copying a file using streams (Java 17+):

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class CopyFileDemo {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("input.bin");
        Path target = Path.of("output.bin");

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(target)) {
            long copied = in.transferTo(out);
            System.out.println("Copied bytes: " + copied);
        }
    }
}
~~~

The program needs the **input.bin** file to exist before running; the printed byte count depends on the actual file size. **transferTo(OutputStream)** reads until EOF and writes to the destination without requiring application code to collect the entire content into one large **byte[]**. For network streams or slow sources, timeouts and read/write errors still must be handled.

## 9. Common Mistakes

1. **Assuming readNBytes(N) always returns N bytes.** The length can be shorter at EOF; check the length if a complete data frame is required.
2. **Assuming readAllBytes() reads from the beginning again.** It reads from the current position; previously consumed bytes do not come back.
3. **Using readAllBytes() on an unbounded source.** Excessively large data can consume significant RAM or cause an OOME; set a threshold and read in chunks.
4. **Confusing read with readNBytes(buffer, ...).** EOF for **read(...)** is signaled by -1; EOF for the **readNBytes(buffer, ...)** overload is signaled by 0.
5. **Using available() as the file/stream size.** This is not the total remaining bytes and is not a reliable EOF signal.
6. **Assuming readNBytes() has a timeout.** Maximum byte count is not maximum time; a network stream can still block.
7. **Decoding UTF-8 by arbitrarily sliced byte chunks.** A byte chunk may miss part of a character; manage boundaries properly or use an appropriate decoder.
8. **Forgetting to close resources.** Neither method calls close automatically; use **try-with-resources** when owning the stream.

## 10. Self-Check

- Calling **readNBytes(4)** on a 10-byte stream, then **readAllBytes()**: the byte counts are **4** and **6**, respectively.
- Calling **readNBytes(7)** on a stream with 2 bytes left before EOF: the result has length **2**, without automatically throwing EOFException.
- Calling **readAllBytes()** from a socket that remains open: may block waiting for **EOF**, even if some bytes have already been sent.
- Reading a frame that requires all 8 bytes: use **readNBytes(8)** and check **length == 8** (or **DataInputStream.readFully**), along with a length limit and timeout when needed.
- Reading 3 bytes into **buffer[1..3]** with **readNBytes(buffer, 1, 3)**: process only the **count** bytes actually read; EOF for this API returns 0.

**Conclusion:** **readNBytes** limits the number of bytes by **N**, whereas **readAllBytes** retrieves **all remaining bytes up to EOF**. They differ in read boundaries, stopping conditions, memory usage, and applicable scenarios.

### References

- [Oracle Java SE 11 — InputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/InputStream.html): **readNBytes**, **readAllBytes** contracts and **Since** milestones.
- [Oracle Java SE 11 — DataInputStream](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/io/DataInputStream.html): **readFully** and **EOFException**.

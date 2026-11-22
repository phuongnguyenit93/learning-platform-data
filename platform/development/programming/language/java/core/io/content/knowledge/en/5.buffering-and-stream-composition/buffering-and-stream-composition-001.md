# Purpose of BufferedInputStream and BufferedOutputStream in Java I/O

When working with files, sockets, or other data sources, reading/writing **one byte at a time** often causes a program to make too many calls down to the underlying source or destination. **BufferedInputStream** and **BufferedOutputStream** are two byte-stream wrapper classes in the **java.io** package that use an in-memory buffer to **batch many small operations into block-level reads/writes**. Their primary goal is to reduce the overhead of calling the underlying stream; both still operate on **bytes** and do not automatically convert charsets or alter binary content.

## 1. What Problem Do BufferedInputStream and BufferedOutputStream Solve?

Suppose you want to read 100,000 bytes from a file, process each byte, and then write it to another file. If you call **FileInputStream.read()** and **FileOutputStream.write(int)** individually for every single byte, the program may have to perform a huge number of operations down to the underlying streams, depending on how those classes are implemented. The cost of state checks, crossing Java/native layers, and communicating with the device or operating system can be greater than the work of processing one byte.

A **buffer** is a byte array in JVM memory. Instead of going down to the source 100,000 times to satisfy 100,000 **read()** calls, a **BufferedInputStream** can fetch a large block and serve many small reads from the block in RAM. The write side works similarly: **BufferedOutputStream** accumulates written bytes and sends them in blocks down to the underlying stream.

| Class | Wraps Stream Type | Primary Purpose | How It Works |
| --- | --- | --- | --- |
| **BufferedInputStream** | **InputStream** | Reduce small reads from the source | Loads bytes in blocks into a buffer, serving them incrementally to subsequent reads |
| **BufferedOutputStream** | **OutputStream** | Reduce small writes to the destination | Holds bytes in a buffer and pushes them to the underlying stream when full or on flush/close |
| **BufferedReader** | **Reader** | Buffer character data, support line reading | Works with **char**, does not replace byte streams for binary data |
| **BufferedWriter** | **Writer** | Buffer character writes | Works with text, not for copying arbitrary bytes |

**Buffering does not make the CPU, disk, or network inherently faster.** It helps reduce the number of small calls and overhead when configured and accessed appropriately. For APIs that already transfer data in large blocks, wrapping an additional buffer may provide little benefit.

## 2. How BufferedInputStream Works

### 2.1. How Does the Read Buffer Work?

For example, suppose we wrap an InputStream with a 4-byte buffer:

~~~text
Data source: A B C D E F G H I J
                │
                │ load a block when needed
                ▼
       [ A | B | C | D ]    internal buffer
         ▲
         └── read() returns 'A'; next call reads 'B' from RAM

When A..D are exhausted, the buffer is loaded with block E..H, then I..J.
~~~

This is the **conceptual model** of small **read()** calls: the buffer lets you reuse data already read. In reality, Java also includes an optimization: when a caller requests **a very large block** via **read(byte[], off, len)**, BufferedInputStream can read directly into the destination array, bypassing unnecessary copying through the buffer, depending on the mark state and JDK implementation.

When creating the stream:

~~~java
InputStream buffered = new BufferedInputStream(originalStream);
~~~

or specifying a buffer size:

~~~java
InputStream buffered = new BufferedInputStream(originalStream, 16 * 1024);
~~~

**originalStream** is a **previously created InputStream**, for example from **Files.newInputStream(path)**. The two snippets above are *illustrative code fragments*, not standalone runnable programs. The constructor accepts a positive **size**; a zero or negative size throws **IllegalArgumentException**. If no size is passed, the JDK uses an implementation-defined default capacity; do not rely on that default number as part of a protocol.

While bytes are available in the buffer, subsequent **read()** calls typically retrieve data directly from RAM. Once the buffer is exhausted and the source stream is still open, the next read must fetch more data, so it **can still block** or throw **IOException**. Buffering **does not eliminate timeouts, EOF, or read errors from the source**.

### 2.2. Reading One Byte vs. Reading in Blocks

With **BufferedInputStream.read()**, each call returns an integer from **0 to 255**, or **-1** at EOF. The byte **0x00** is normal data; do not treat it as EOF. With **read(byte[])**, the actual number of bytes received may be smaller than the array's capacity, even before EOF. The number of valid bytes is always the returned **count**.

Example:

~~~java
byte[] chunk = new byte[8192];
int count;
while ((count = buffered.read(chunk)) != -1) {
    // Only process chunk[0] through chunk[count - 1].
}
~~~

This snippet assumes you already have a **buffered** variable of type **InputStream**. When reading large blocks, **read(byte[])** itself already reduces the number of calls compared to reading byte-by-byte; therefore, **the benefit of adding an extra BufferedInputStream layer may be small or negligible**. Measure with your real workload instead of always stacking multiple buffer layers.

### 2.3. mark() and reset(): A Notable Utility

**BufferedInputStream** supports **mark() / reset()** even when the underlying source does not support marking on its own. This is useful when a parser needs to peek ahead a few bytes to identify a format, and then return to the marked position.

- Call **mark(readlimit)** to mark the current position and declare how many bytes can be read before the mark becomes invalid.
- Call **reset()** to return to the marked position if the mark is still valid.
- **markSupported()** returns **true** for BufferedInputStream.
- If reading past the limit invalidates the mark, **reset()** may throw **IOException**.
- Holding a mark with a large readlimit may force the buffer to expand, increasing RAM usage; this is not a mechanism for arbitrarily rewinding an entire file.

This is a functional benefit beyond reducing read calls, though you still need to manage the readlimit and stream lifetime.

## 3. How BufferedOutputStream Works

### 3.1. Batching Small Writes into Large Writes

Suppose we set a 4-byte buffer and call **write(int)** one byte at a time:

~~~text
write('A')  → [ A |   |   |   ]
write('B')  → [ A | B |   |   ]
write('C')  → [ A | B | C |   ]
write('D')  → [ A | B | C | D ]
write('E')  → flushes A B C D down to the underlying OutputStream,
              keeps E in the buffer for the next write.
~~~

The diagram illustrates the byte-batching principle; exact timing can vary depending on how writes are made and the implementation. For a large array whose length is **>= buffer size**, BufferedOutputStream can flush any buffered bytes and write that array **straight through to the underlying stream**, avoiding an extra copy.

Creating the wrapper:

~~~java
OutputStream buffered = new BufferedOutputStream(originalStream, 16 * 1024);
~~~

**originalStream** is an already created OutputStream, such as **Files.newOutputStream(path)**. For write operations, it is essential to know that **a successful write(...) on the wrapper does not necessarily mean the bytes have been sent to the destination at that moment**. Some or all of the data may still reside in the buffer.

### 3.2. When Is Buffered Data Pushed Out?

During normal usage, buffered output sends bytes to the underlying stream when:

1. The buffer is full and the program attempts to write more bytes.
2. The program explicitly calls **flush()**.
3. The program calls **close()** or exits a **try-with-resources** block: buffered data is flushed during closing (unless an I/O error occurs).

Use **flush()** at boundaries where data must be transmitted immediately, such as after an application message or after writing a response that needs to be sent while the connection stays open:

~~~java
buffered.write(message);
buffered.flush();
~~~

This is an illustrative code snippet assuming **buffered** is of type OutputStream and **message** is a byte[]. **flush()** requests pushing bytes out of this layer's buffers (and by the contract of nested streams, flushing may propagate to the underlying layer). It **does not guarantee the bytes are durably persisted to physical disk**, does not replace data synchronization like **FileChannel.force(...) / FileDescriptor.sync()**, and **does not guarantee the remote network peer has received or processed the message**.

**Do not flush after every single byte** if your goal is to speed up writes. Doing so defeats most of the purpose of batching small operations. If the operation is short-lived and you own the wrapper, you can usually let **close()** in try-with-resources finish the flush instead of making a redundant manual flush right before close.

## 4. Runnable Java 17+ Example: Observing Buffering, Flush, mark/reset, and Byte Preservation

Save the following code as **BufferedStreamsDemo.java**. The example operates purely in memory so that the results are consistently repeatable without creating files or depending on disk speed.

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class BufferedStreamsDemo {
    public static void main(String[] args) throws IOException {
        // 1. Read buffer and mark/reset functionality.
        byte[] letters = "ABCDE".getBytes(StandardCharsets.US_ASCII);
        try (BufferedInputStream in = new BufferedInputStream(
                new ByteArrayInputStream(letters), 3)) {
            System.out.println("first=" + (char) in.read());
            in.mark(3);
            byte[] next = in.readNBytes(2);
            System.out.println("next=" +
                    new String(next, StandardCharsets.US_ASCII));
            in.reset();
            System.out.println("after reset=" + (char) in.read());
        }

        // 2. Write buffer holds bytes temporarily before flush.
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (BufferedOutputStream out =
                     new BufferedOutputStream(sink, 8)) {
            out.write(new byte[] {65, 66, 67}); // A B C
            System.out.println("before flush=" + sink.size());
            out.flush();
            System.out.println("after flush=" + sink.size());
            out.write('D'); // Byte D stays in the buffer until close.
        }
        System.out.println("after close=" + sink.size());
        System.out.println("text=" +
                new String(sink.toByteArray(), StandardCharsets.US_ASCII));

        // 3. Copy binary data containing bytes 00 and FF.
        byte[] binary = {0x00, (byte) 0xFF, 0x0A, 0x41};
        ByteArrayOutputStream copyTarget = new ByteArrayOutputStream();
        try (InputStream in = new BufferedInputStream(
                     new ByteArrayInputStream(binary), 2);
             OutputStream out =
                     new BufferedOutputStream(copyTarget, 2)) {
            byte[] chunk = new byte[3];
            int count;
            while ((count = in.read(chunk)) != -1) {
                out.write(chunk, 0, count);
            }
        }
        byte[] copied = copyTarget.toByteArray();
        System.out.println("binary equal=" +
                Arrays.equals(binary, copied));
        System.out.println("binary hex=" +
                HexFormat.of().formatHex(copied));
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac BufferedStreamsDemo.java
java BufferedStreamsDemo
~~~

Output:

~~~text
first=A
next=BC
after reset=B
before flush=0
after flush=3
after close=4
text=ABCD
binary equal=true
binary hex=00ff0a41
~~~

Explanation:

- **mark(3)** sets a mark before B; after reading BC, **reset()** returns to B, hence **after reset=B**.
- With an output buffer capacity of 8, the three bytes **ABC** are not enough to trigger a write to **sink**, so **before flush=0**.
- **flush()** gives sink 3 bytes; adding D and then exiting try-with-resources calls **close()**, which flushes and gives sink 4 bytes.
- For the binary bytes **00 FF 0A 41**, the output matches identically (**Arrays.equals** is true). Buffered streams **do not decode UTF-8 or alter binary data**.

The sink size figures in this example are based on writing a 3-byte array with an 8-byte buffer and are explicitly controlled. In real file/network systems, when the device or receiver actually processes the data also depends on lower layers.

## 5. Practical Example: Copying a File with Buffered Streams

To copy an arbitrary file without turning bytes into characters, you can combine buffering in both directions with a block-based read/write loop. Save the program as **BufferedFileCopy.java**:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public class BufferedFileCopy {
    public static void main(String[] args) throws IOException {
        Path source = Path.of("input.bin");
        Path target = Path.of("output.bin");

        try (InputStream in = new BufferedInputStream(
                     Files.newInputStream(source), 16 * 1024);
             OutputStream out = new BufferedOutputStream(
                     Files.newOutputStream(target), 16 * 1024)) {
            byte[] chunk = new byte[8192];
            int count;
            while ((count = in.read(chunk)) != -1) {
                out.write(chunk, 0, count);
            }
        }

        System.out.println("identical=" +
                (Files.mismatch(source, target) == -1L));
    }
}
~~~

Compile/run commands after creating **input.bin** in the current directory:

~~~bash
javac BufferedFileCopy.java
java BufferedFileCopy
~~~

Assuming no errors, the source file does not change during copying, and no other actor concurrently modifies the target, the output is:

~~~text
identical=true
~~~

Notes:

- **Files.newInputStream** opens the source and **Files.newOutputStream** opens the target. By default, with Files.newOutputStream(path) and no options, the target file is created if absent or **truncated to empty if it already exists**; you must actively choose the target file handling policy to avoid data loss.
- **out.write(chunk, 0, count)** is mandatory: only **count** bytes were just received, especially on the final read. Writing the whole buffer can insert stale bytes into the target file.
- Try-with-resources **closes the wrappers**, which in turn closes the underlying streams. When an OutputStream is closed, buffered data is flushed; if that throws IOException, the copy may be incomplete.
- **Files.mismatch** (Java 12+) compares byte by byte; **-1** means no differing byte was found between the two compared files. Comparing file sizes alone is not enough to prove the data is identical.
- If you want something simpler and do not need chunk-by-chunk processing, **Files.copy(source, target)** is usually the direct way to copy files. Use buffered wrappers when your program **actually needs to work with streams**.

### When Reading/Writing in Chunks with Your Own Buffer, Do You Still Need BufferedInputStream/OutputStream?

Not always. With a loop reading an **8192-byte** array and writing arrays in blocks, the code already reduces call counts compared to single **read() / write(int)** calls. Underlying layers may also optimize on their own—for example, the OS layer has a page cache or a library may have its own buffer. Wrapping with **BufferedInputStream/BufferedOutputStream** sometimes adds extra memory copies without noticeably increasing throughput; at other times it helps if the layers interacting with a slow source or the program interleave many small operations. **Measure in practice** with your application's block sizes, device types, and access patterns.

## 6. Stream Composition: Adding Functionality by Wrapping Layers

Both classes follow the **decorator** pattern: one stream wraps another, preserving the InputStream/OutputStream interface while adding buffering. You can stack multiple layers to combine capabilities.

For example, reading primitive types from a file using **DataInputStream**'s protocol:

~~~java
try (DataInputStream in = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(path)))) {
    int version = in.readInt();
    // ...
}
~~~

For example, writing typed data with **DataOutputStream**:

~~~java
try (DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(Files.newOutputStream(path)))) {
    out.writeInt(42);
    out.writeUTF("Java");
}
~~~

The two snippets above are **illustrative code fragments**, assuming **java.io.*** and **java.nio.file.*** are imported and **path** is declared as a **Path**. **DataInputStream/DataOutputStream** read/write structured primitive values, while the Buffered classes handle batching bytes; each layer keeps its own responsibility.

Some rules for stream composition:

1. **Perform business calls on the outermost wrapper.** For DataOutputStream in the example, call **writeInt** on DataOutputStream instead of bypassing it to write directly to the underlying OutputStream.
2. **Close the outermost wrapper if you own the entire chain.** Closing decorators normally forwards to the underlying stream; do not continue using a stream that has been closed.
3. **Avoid closing shared streams you do not own.** For instance, a wrapper around **System.out** should generally not be closed casually because it will close standard output for the whole application; only flush at appropriate points.
4. **Do not stack duplicate buffers thinking more is always faster.** Wrapping BufferedInputStream around BufferedInputStream or BufferedOutputStream around BufferedOutputStream usually increases complexity and can add copies with no clear benefit.
5. **Pay attention to ordering when compression/encryption is involved.** Placing a buffer on the raw-data side versus the post-processed side changes where blocks are batched. Classes like GZIPInputStream/GZIPOutputStream often have their own block handling and buffering mechanisms; understand the wrapper chain and benchmark rather than assuming one universal optimal order.

## 7. Choosing a Buffer Size

Constructors of the form **(stream, size)** let you choose the internal byte array size. For example, **8 KiB (8192 bytes)** or **16 KiB (16384 bytes)** are often reasonable starting values to test, though not optimal for every case.

**Too small:** the buffer must refill/drain frequently, resulting in more underlying calls. **Too large:** each stream holds a lot of RAM, which can be wasteful when thousands of connections or files are open concurrently; returns diminish. For example, with 10,000 streams each having a 64 KiB buffer, the theoretical buffer memory alone reaches roughly **625 MiB** for just one direction (64 × 10,000 KiB = 640,000 KiB ≈ 625 MiB), not counting overhead and other buffers.

If using bidirectional input/output for the same connection, there may be **two separate buffers**. RAM usage must be evaluated by the total number of concurrently live wrappers. When benchmarking, measure throughput and latency under a realistic workload: the number of small calls, size per call, disk/network speed, flush requirements, stream lifetime, and concurrent connection count.

Decisions should not rely on **InputStream.available()** to infer total file/stream length; it only estimates bytes readable immediately without blocking, not the final size or a sole basis for allocation.

## 8. Relationship Between flush, close, Timeouts, and Data Durability

| Action | BufferedInputStream | BufferedOutputStream |
| --- | --- | --- |
| **read()** | Returns buffered data or loads more from the source | Not applicable |
| **write()** | Not applicable | Writes to the buffer or pushes bytes to the destination when appropriate |
| **flush()** | Not provided (InputStream has no flush) | Pushes buffered data down to the underlying OutputStream |
| **close()** | Closes wrapper and underlying stream, releasing the buffer | Flushes remaining buffered data then closes wrapper/underlying stream; I/O errors can still occur |
| **mark/reset** | Supported within the readlimit boundary | Not applicable |

**flush() does not mean "safely stored on disk".** For file output, the OS may still cache it; for sockets, bytes leaving the Java buffer do not mean the peer has processed them. To request disk durability, you need appropriate synchronization APIs and an understanding of the filesystem contract; to confirm network delivery, you need an application-layer acknowledgment protocol when required.

**Buffers do not replace timeouts.** Network reads can still block waiting for new bytes. The program must configure timeouts at the appropriate socket/network layer and handle disconnects. BufferedInputStream itself does not impose a time limit on read(), and BufferedOutputStream does not turn a slow destination into a non-blocking one.

**A write call does not mean all data was delivered successfully** if a subsequent close/flush throws an error. When data is critical, check for I/O errors, integrity, and the state of the target file/stream.

## 9. Common Mistakes

1. **Confusing buffered streams with character streams.** BufferedInputStream/OutputStream hold bytes, whereas BufferedReader/Writer work with characters. Binary data should use byte streams.
2. **Forgetting to flush while a connection stays open and data must be sent immediately.** Bytes may still sit in BufferedOutputStream; call **flush()** at message boundaries that need to be transmitted.
3. **Flushing after every byte.** Defeats the efficiency of batching small operations. Batch by message/block and flush when needed.
4. **Forgetting to close owned wrappers.** Final bytes may remain unflushed and descriptors unreleased. Use **try-with-resources**.
5. **Thinking a wrapper's close() only closes the wrapper.** Normally it also closes the inner stream; avoid closing shared streams that are still needed.
6. **Writing more bytes than were read.** In a buffer loop, you must use **out.write(buffer, 0, count)**, never write the whole array when **count < buffer.length**.
7. **Measuring performance with a single run.** Speed also depends on page cache, JIT, actual I/O, data, OS, and concurrency; benchmark a realistic workload.
8. **Assuming bigger buffer size is always better.** RAM grows with the number of streams, and sometimes underlying calls do not drop noticeably further.
9. **Believing flush equals fsync or a network ACK.** They are different; choose the acknowledgment/durability mechanism that fits your requirements.
10. **Abusing mark/reset when long rewinding is needed.** Mark has a readlimit and can expire; it does not replace re-reading a file from the start.

## 10. Self-Check Questions

**Q1.** Does BufferedInputStream convert data from bytes into text?  
**A:** No. It holds bytes in a buffer array and does not decode characters.

**Q2.** If you write "ABC" into a BufferedOutputStream of capacity 8, have the bytes necessarily reached the underlying OutputStream?  
**A:** Not yet. They may still sit in the buffer; **flush()** or **close()** will request pushing the bytes out.

**Q3.** Why can writing byte-by-byte to FileOutputStream be slower than wrapping it with BufferedOutputStream?  
**A:** Because the wrapper batches small calls into larger writes to the underlying stream, reducing I/O call overhead.

**Q4.** If a loop already reads **byte[8192]** and writes in blocks, is adding a buffer always faster?  
**A:** No. The benefit depends on the source/destination implementation, access size, memory copy cost, and actual workload.

**Q5.** Does calling flush on buffered output guarantee the disk has persisted the write or the network peer has received it?  
**A:** No. Flush pushes data from Java's buffering layer down to the underlying stream, which is different from disk synchronization or protocol-level acknowledgment.

**Q6.** What capability does BufferedInputStream provide besides buffering?  
**A:** It supports **mark/reset**, allowing you to return to a marked position within valid limits even when the underlying InputStream does not support it on its own.

## 11. Takeaways and Choosing an API

**BufferedInputStream** batches small reads into fewer larger reads from the source; **BufferedOutputStream** batches small writes and needs its buffer drained at the right time via **flush() / close()**. Both are byte-stream wrappers that can be composed with other underlying streams via the decorator pattern, do not automatically convert charsets, and do not solve timeouts or data durability on their own.

If you are doing a **simple file copy**, consider **Files.copy(...)**. If you process bytes as a stream, need to work byte-by-byte, or have many small I/O operations, the two buffered classes are the right tools. Choose buffer sizes based on read/write frequency, available RAM, and actual measurements.

### References

- [Oracle Java SE 17 — BufferedInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedInputStream.html): buffering principles, constructors, mark/reset, read.
- [Oracle Java SE 17 — BufferedOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedOutputStream.html): buffering, flush, and close.
- [Oracle Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): byte reading, read(byte[]), EOF.
- [Oracle Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): write(byte[], off, len), flush, close.
- [Oracle Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): newInputStream, newOutputStream, copy, and mismatch.
# `InputStream.available()` Is Not the Total Data Size

## Lesson Objectives

When working with **byte streams** in Java, you need to distinguish between the amount of data *readable right now* and the total size of the data source. After this lesson, you can:

- Correctly explain the meaning of `InputStream.available()` and why its result is not the length of the entire stream.
- Recognize why `available() == 0` **does not mean** the data has ended (EOF), and `available() > 0` **does not tell you** how long the entire data is.
- Read data using `read()`, `read(byte[])`, or appropriate read-until-EOF APIs; choose the right way to determine file size when you actually have a file.
- Avoid allocating buffers, writing loop conditions, or building protocol logic based on `available()`.

## 1. What Does `available()` Actually Return?

`java.io.InputStream` declares:

```java
public int available() throws IOException
```

The return value is **an estimate of the number of bytes that can be read or skipped over from the stream without blocking** at the time of the call. It can be `0`, even when the stream still has data and the next `read()` call can obtain bytes after waiting, or immediately.

Keep three distinct concepts separate:

| Concept | Correct Understanding |
| --- | --- |
| `available()` | An estimate of bytes obtainable **without waiting** at the current moment; depends on the stream type. |
| Total source size | The total number of bytes in the entire file, message, or data to be supplied; many streams do not have this total known upfront. |
| EOF | The end-of-data state, indicated when `read()` returns `-1` (or a corresponding API indicates the end of the stream). |

In particular, the default implementation of `InputStream.available()` returns **`0`**. Subclasses can override this method when they know more about the data currently available. Therefore, you cannot infer the capacity of the entire stream from a single `available()` number.

## 2. Why Do Results Differ Across Streams?

- **`ByteArrayInputStream`:** all data is already present in the byte array; `available()` returns the number of unread bytes **remaining in the array**. For this specific class, that number reflects the remainder of the available source.
- **`FileInputStream`:** for a regular file, the value is usually close to the number of bytes remaining to be read from the current position, but the API still describes it under the `available()` contract. Do not turn a characteristic of `FileInputStream` into a general rule for every `InputStream`.
- **Streams from sockets, pipes, or incremental sources:** there may be no bytes in the buffer *right now*, even though the sender will send more later. `available() == 0` does not prove that the connection has ended or that the message is complete.
- **Subclasses that only implement `read()`:** if `available()` is not overridden, the value is always `0` per the default implementation, even though data can still be read.

Note: the number can change after a read or when new data arrives. Nor does it replace a protocol format that specifies the message length upfront.

## 3. Java 17+ Experiment: Data Exists, Yet `available() == 0`

Save the following snippet to the file **`AvailableDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class AvailableDemo {
    public static void main(String[] args) throws IOException {
        byte[] data = "ABCDE".getBytes(StandardCharsets.US_ASCII);

        try (InputStream arrayStream = new ByteArrayInputStream(data)) {
            System.out.println("array before = " + arrayStream.available());
            System.out.println("array first  = " + (char) arrayStream.read());
            System.out.println("array after  = " + arrayStream.available());
        }

        try (InputStream customStream = new InputStream() {
            private int index;

            @Override
            public int read() {
                return index < data.length ? (data[index++] & 0xff) : -1;
            }
        }) {
            System.out.println("custom before = " + customStream.available());
            System.out.println("custom first  = " + (char) customStream.read());
            System.out.println("custom after  = " + customStream.available());
        }
    }
}
```

Compile and run:

```bash
javac AvailableDemo.java
java AvailableDemo
```

Expected output:

```text
array before = 5
array first  = A
array after  = 4
custom before = 0
custom first  = A
custom after  = 0
```

**Explanation:**

1. `ByteArrayInputStream` knows the array contains five bytes; after reading `A`, four unread bytes remain, so `available()` goes from `5` to `4`.
2. `customStream` only overrides `read()` and inherits the default `available()`. Therefore `available()` is always `0`, even before `read()` successfully returns the byte `A`.
3. Both streams are initialized from the same `ABCDE` data, yet their `available()` measurements differ. That proves this method **does not represent the total data size**.

The example intentionally uses a small custom `InputStream` to clearly observe the API contract; this is not how you need to create every stream in real-world applications.

## 4. Two Misuses That Easily Lose Data

### Mistake A: Allocating by `available()` and Reading Once

```java
// WRONG: does not guarantee retaining all bytes of the stream.
byte[] all = new byte[in.available()];
int count = in.read(all);
```

This snippet has at least two independent bugs:

1. `available()` can be `0` or smaller than the data that will arrive, so the `all` array may lack space or be empty even though the stream has not ended.
2. Even if the array is large enough, **a single `read(byte[])` call is not guaranteed to fill the array**; the return value is the number of bytes actually read or `-1` on EOF. Never assume `count == all.length`.

### Mistake B: Using `available() > 0` to Decide Whether Data Remains

```java
// WRONG: may stop early before all data has been received.
while (in.available() > 0) {
    int oneByte = in.read();
    // Process byte...
}
```

With a network stream, data can arrive in bursts. When the buffer is temporarily empty, `available()` can drop to `0`; the loop terminates even though the other side is still transmitting. With an `InputStream` subclass that does not override `available()`, the loop does not even run once.

**Rule:** do not use `available()` as a data termination condition, do not use it as a message length, and do not use it as the basis for allocating a buffer to hold an entire stream.

## 5. The Right Way: Read Until EOF

For a typical stream that you want to read completely, read in a loop and check the return value of `read(byte[])`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ReadUntilEofDemo {
    public static void main(String[] args) throws IOException {
        byte[] source = "Xin chao IO!".getBytes(StandardCharsets.UTF_8);

        try (InputStream in = new ByteArrayInputStream(source);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[4];
            int count;

            while ((count = in.read(buffer)) != -1) {
                out.write(buffer, 0, count);
            }

            byte[] result = out.toByteArray();
            System.out.println(new String(result, StandardCharsets.UTF_8));
            System.out.println("bytes = " + result.length);
        }
    }
}
```

Save as **`ReadUntilEofDemo.java`**, then run:

```bash
javac ReadUntilEofDemo.java
java ReadUntilEofDemo
```

Output:

```text
Xin chao IO!
bytes = 12
```

Why this approach is right:

- The `buffer` has a fixed size of `4` bytes, independent of `available()`. This is the capacity *per read call*, not the size of the entire source.
- `read(buffer)` returns the actual number of bytes in that read call. `out.write(buffer, 0, count)` writes only `count` bytes, avoiding writing stale leftover bytes in the array.
- Only when the API reports `-1` does the loop consider the stream ended. If the source can block, `read` may need to wait for the next data; that is the read behavior defined by the stream.

In this example, `ByteArrayOutputStream` holds all bytes in RAM for demonstration. For large data, you should process chunk by chunk or write directly to the destination `OutputStream` instead of accumulating everything in memory.

## 6. Choosing the Right API for Practical Goals

| What do you want to do? | Appropriate approach | Notes |
| --- | --- | --- |
| Read an entire stream of unknown length | `read(byte[])` in a loop until `-1` | Suitable when you need to process/write chunk by chunk; no need to call `available()`. |
| Get all bytes of a **small, bounded** stream | `in.readAllBytes()` (Java 9+) | Reads until EOF; consumes memory proportional to data size and can wait long if the source is not closed. |
| Transfer data to an output | `in.transferTo(out)` (Java 9+) | Returns the number of bytes transferred as a `long`; no need to measure stream length beforehand. |
| Need to read at most `n` bytes from a stream | `in.readNBytes(n)` or a bounded loop | Actual bytes received may be fewer than `n` if EOF is reached. |
| Protocol requires **exactly N bytes** | Loop reading until N bytes are obtained; `DataInputStream.readFully(byte[])` can be used | `readFully` throws `EOFException` if the stream ends before enough bytes are read. |
| Need the size of a **file on the filesystem** | `Files.size(path)` | Returns a `long` for the file at query time; do not use for sockets or arbitrary `InputStream` instances. |

Example of getting a file's size:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileSizeDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("data.bin");
        long size = Files.size(path);
        System.out.println("File size (bytes): " + size);
    }
}
```

This is a valid Java program; when running it, a file named `data.bin` is needed in the working directory. The printed value **depends on the actual file**, so there is no fixed stdout. `Files.size(path)` tells you the size of the specified file, not the number of bytes currently in the buffer of an open `InputStream`. If the file changes while being read, a previously measured size still does not replace checking the result of each `read` call.

## 7. EOF, Blocking, and Message Boundaries

Imagine a network stream receiving a sequence of bytes in two bursts:

```text
Time t1: [A B] has arrived; the C D E part has not arrived yet
Time t2: [C D E] arrives later
End:     the sender closes the stream or the protocol confirms end of message
```

At a point between the two bursts, `available()` can be `0` even though `read()` will later still return the byte `C`. Similarly, sometimes `available()` is positive, yet that number does not prove that the complete message has been received.

Distinguish two different questions:

- **“Has the stream reached EOF?”** Rely on `read() == -1` when reading to the end of the stream, not on `available() == 0`.
- **“Has the full message been received?”** This depends on the protocol: for example, a length prefix sent beforehand, a delimiter character, data framing, or the end of the stream. A single network connection can carry multiple messages before EOF; do not wait for EOF for each message if the protocol uses another framing mechanism.

In practice, when `read()` might wait indefinitely, use size limits, timeouts, or framing mechanisms appropriate to the source type. `available()` does not replace those measures.

## 8. Common Pitfalls When Handling Bytes

1. **Byte count is not character count.** With UTF-8, a single character can take multiple bytes; even when `available()` matches the exact number of bytes currently present, it does not tell you the number of text characters.
2. **`read()` returns type `int`.** A valid byte is returned in the range `0..255`; `-1` is the EOF marker. When implementing `InputStream.read()` yourself, convert `byte` to `int` using `& 0xff` as shown in the example to avoid mistaking a byte with its sign bit set for a negative value.
3. **One read does not mean a full read.** Check `count` from `read(buffer)` and process only the `0..count-1` range.
4. **Buffer capacity is a performance decision, not the data length.** You can use a buffer of a few KiB and read many times without knowing the total size.
5. **Do not hold unbounded untrusted data in RAM.** `readAllBytes()` and `ByteArrayOutputStream` are useful for finite, bounded data; for uploads or long-lived connections, process the stream in chunks and apply explicit limits.
6. **Only close streams you own.** `try-with-resources` releases resources in the demonstration programs; in library code, follow the ownership contract for the stream.

## 9. Self-Check

**Question 1.** An `InputStream` returns `available() == 0`. Can you conclude that the immediately following `read()` will return `-1`?

**Answer:** No. The stream may still have data even though no bytes are ready at the exact moment of the check; or the subclass uses the default `available()`, which always returns `0`. EOF must be determined through a read operation.

**Question 2.** A `ByteArrayInputStream` is created from a 10-byte array, and 3 bytes have been successfully read. Assuming no other `mark/reset/skip` operations, what does `available()` on this specific class return?

**Answer:** `7`, because this class knows the exact number of unread bytes in the array. That is a characteristic of `ByteArrayInputStream`, not a general guarantee for every stream.

**Question 3.** If you want to copy data from an `InputStream` of unknown length to an `OutputStream`, do you need to compute `available()`?

**Answer:** No. You can use `in.transferTo(out)` or a `read(buffer)` and `out.write(buffer, 0, count)` loop until EOF, with limits and timeout handling where appropriate.

**Key Takeaway:** `available()` returns *an estimate of the number of bytes that can be obtained immediately without blocking*, **not the total data size and not an EOF test**. Read using the result of `read()`; get the length from the data source or protocol if you truly need to know it beforehand.
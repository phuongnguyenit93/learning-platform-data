# Meaning of `0` and EOF `-1` Results When Reading an NIO Channel

## 1. Core Question

When calling `int n = channel.read(buffer)` in Java NIO, the value `n` is not the byte content just read. It is **the number of bytes transferred from the channel into `ByteBuffer` during that specific call**, or an end-of-stream marker (commonly called EOF). Under the `ReadableByteChannel.read(ByteBuffer)` contract:

- **`n > 0`**: successfully read exactly `n` bytes; only that many bytes were just added into the buffer's remaining space.
- **`n == 0`**: the call transferred no bytes. This may happen because the buffer has no space left (`remaining() == 0`), because the channel has no bytes available at that instant (especially in non-blocking mode), or another condition permitted by the API. **`0` is not EOF.**
- **`n == -1`**: the channel reports reaching **the end of the input stream**. No new bytes were transferred during this call.
- **Exception**: I/O errors or invalid channel states are reported via exceptions, never “encoded” as `0` or `-1`.

This lesson belongs to **Java Core I/O → NIO Channel**. The goal is to interpret `read` results accurately, distinguish files from sockets and blocking from non-blocking, and design loops without data loss or busy-looping.

## 2. Full Contract of `read(ByteBuffer)`

Let `dst` be the receiving `ByteBuffer`. Immediately before the call:

```text
p = dst.position()
r = dst.remaining() = dst.limit() - dst.position()
```

The channel attempts to read **at most `r` bytes**. If `n` bytes are read (`0 <= n <= r`), the bytes are written starting at index `p`, `dst.position()` increases to `p + n`, and `dst.limit()` stays unchanged. If `-1` is returned, the read encountered EOF; no new bytes were written.

Example assuming the buffer has 5 available slots:

```text
Before read:    position=3, limit=8, remaining=5
read returns 2: position=5, limit=8, remaining=3
read returns 0: position=3, limit=8, remaining=5   (if starting from the initial state)
read returns -1: no new bytes; has not moved to a new data region
```

Never infer “reading less than the requested capacity means EOF”. A channel can return `1` byte even when plenty of data remains. Each `read` only reports the result *of that single read*.

| Result from `read(dst)` | New Data | Meaning to Understand | Typical Handling |
| --- | --- | --- | --- |
| `1 .. dst.remaining()` before call | Exactly `n` bytes | Progress made; does not confirm all data is read | `flip()`, process received bytes or accumulate message frames |
| `0` | None | Cannot conclude data has ended | Check `remaining`, blocking state, and waiting mechanism |
| `-1` | None | Reached end of input stream at call time | Stop reading; process any buffered data |
| Throws `IOException` or related exception | No normal byte count returned | I/O failure or channel closed/interrupted | Handle error, close resources per policy |

`remaining()` is evaluated **before the call** if you want the maximum read length, and **after the call** to know how many free slots remain. When `read` returns `0`, the buffer's state does not automatically switch to read mode: `flip()` and `clear()` remain the application's responsibility.

## 3. `0`: No Progress, Yet Two Very Different Situations

### 3.1. Buffer Out of Space

If `buffer.remaining() == 0`, there is no slot for the channel to write more bytes. A read with a full buffer can return `0` even if the file or socket still has data. The read **cannot meaningfully probe whether new bytes or EOF come next** for flow-control purposes.

```java
ByteBuffer dst = ByteBuffer.allocate(4);
dst.position(dst.limit()); // remaining() == 0
int n = channel.read(dst); // typically 0 because there is no space
```

This is an illustration snippet inside a method that has a `channel` variable, not a standalone program. For a general `ReadableByteChannel`, the result when requesting 0 bytes depends on the API rules and implementation in that specific state; **do not rely on `read(emptyBuffer)` to detect EOF**. A common mistake is forgetting `clear()` or `compact()` before the next data-receiving pass.

### 3.2. No Data Available Yet on a Non-Blocking Socket

A `SocketChannel` in non-blocking mode (`configureBlocking(false)`) can return `0` when the socket is usable yet **no bytes are available to fetch at the moment of the call**. This result does not mean the other side closed the connection. More bytes may arrive later.

```java
int n = socketChannel.read(buffer);

if (n > 0) {
    // Received n bytes.
} else if (n == 0) {
    // Could not read any bytes right now: wait for an event or suitable time.
} else { // -1
    // Input has ended.
}
```

The snippet above is illustrative code assuming `socketChannel` is open and `buffer` is ready to receive data. In applications using `Selector`, when `0` occurs, you typically return control to the event loop and continue awaiting `OP_READ`, adjusting interest ops as needed. Do not call `read` repeatedly in a tight empty `while` loop just to wait for new bytes: that easily spikes CPU usage.

### 3.3. How Does a Blocking Channel Differ from Non-Blocking?

The `ReadableByteChannel` contract guarantees that for a channel in **blocking mode** with `dst.remaining() > 0`, the call waits until at least one byte is read. If the stream ends before any byte is read, stream termination is represented by `-1`; I/O errors are reported separately by exceptions.

For `FileChannel`, `SocketChannel`'s non-blocking mode does not apply directly: regular files are read at the file position and can reach EOF quickly. When the buffer has space and the file still has data, the byte count read may be less than requested; do not treat `0` as a sign that “the file is out of data”.

Note: various API methods, channel types, and filesystems have detailed differences. Always follow the contract of the actual channel rather than extrapolating from a socket demo.

## 4. `-1`: End-of-Stream (EOF) Signal

`-1` is a **sentinel value** outside the range of read byte counts `0 .. remaining()`. It indicates no further bytes can be received because input has ended on this read.

For files:

- If a file contains three bytes `ABC`, a read with a 2-byte buffer returns `2` (`AB`), the next returns `1` (`C`), and the one after returns `-1`.
- Reading an empty file with a buffer that has space usually returns `-1` immediately.
- The file read position has reached the end of existing data; it does not mean “waiting for a new file”.
- If another process appends bytes to an open file later, whether subsequent reads see them depends on timing, position, and file/provider consistency. Do not treat EOF on a concurrently modified file as an immutable world-wide event.

For TCP sockets:

- `-1` from `SocketChannel.read` means **the incoming side of the stream has reached its end**; typically the peer closed its outbound stream cleanly or called `shutdownOutput()`.
- TCP supports **half-close**: the peer may stop sending while remaining able to receive data. Thus EOF on the read side **does not assert that both directions of the connection are closed**.
- If the peer resets the connection or an I/O error occurs, Java may throw `IOException` instead of returning `-1`. That is not normal EOF.
- Bytes that arrived prior to the end signal still must be processed. For example, if the buffer holds an incomplete application frame, encountering `-1` requires deciding whether it is a valid final message or a truncated data error, depending on the protocol.

**Distinction:** `0` means “no bytes transferred in this turn”; `-1` means “reached the end of input”. Neither adds bytes to the buffer, yet they **lead to completely different actions**.

## 5. Standalone Java 17+ Example: `0`, Positive Counts, and EOF `-1`

Create `ChannelReadResultDemo.java`. The program creates a temporary file containing the exact three ASCII bytes `ABC`, opens a `FileChannel` for reading, performs one read into a zero-capacity buffer to demonstrate `0`, and then reads the file through a capacity-2 buffer to observe positive results and `-1`.

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class ChannelReadResultDemo {
    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("nio-read-result-", ".txt");

        try {
            Files.write(path, "ABC".getBytes(StandardCharsets.US_ASCII));

            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ)) {

                ByteBuffer noSpace = ByteBuffer.allocate(0);
                int zero = channel.read(noSpace);
                System.out.println("Empty buffer: " + zero);
                System.out.println("File position: " + channel.position());

                ByteBuffer buffer = ByteBuffer.allocate(2);
                while (true) {
                    buffer.clear();               // Prepare to receive new bytes
                    int n = channel.read(buffer);

                    if (n == -1) {
                        System.out.println("Read: -1 (EOF)");
                        break;
                    }
                    if (n == 0) {
                        System.out.println("Read: 0 (no progress)");
                        continue;
                    }

                    buffer.flip();                // Process only the n bytes just read
                    byte[] bytes = new byte[n];
                    buffer.get(bytes);
                    String chunk = new String(bytes, StandardCharsets.US_ASCII);
                    System.out.println("Read: " + n + " (" + chunk + ")");
                }
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile and run:

```bash
javac ChannelReadResultDemo.java
java ChannelReadResultDemo
```

Stdout on JDK 17+ when the temporary file is created successfully:

```text
Empty buffer: 0
File position: 0
Read: 2 (AB)
Read: 1 (C)
Read: -1 (EOF)
```

**Step-by-step interpretation:**

1. `ByteBuffer.allocate(0)` has `remaining() == 0`; `FileChannel.read(noSpace)` returns `0` and the file position stays `0`. Therefore `0` here **cannot** be interpreted as EOF.
2. `ByteBuffer.allocate(2)` allows reading up to 2 bytes. The first `read` takes `AB`, advances `buffer.position()` to 2, and advances the file position by 2.
3. The next loop iteration calls `clear()` for a new round; only `C` remains in the file, so `read` returns `1` instead of `2`. It is still not EOF on that read.
4. After consuming `C`, the next call with space in the buffer returns `-1`, and the loop ends.
5. `flip()` bounds the buffer read range to the exact newly received bytes. Old data may remain in the backing storage; do not treat the entire `buffer.array()` as valid content.

The `continue` when `n==0` in this example is only meant for **`FileChannel` with a buffer that always has capacity 2 and has been `clear()`ed**; it is not a safe wait strategy for a non-blocking `SocketChannel`. With a non-blocking socket you must use `Selector`, callbacks, or an appropriate wait mechanism.

## 6. Do Not Equate `read` Return Value with Data Byte Values

A byte in a file can hold value 0 (`0x00`), or `0xFF`. That **does not mean** `read` returns `0` or `-1`.

Example file containing bytes `[0x00, 0xFF]`:

```java
ByteBuffer buffer = ByteBuffer.allocate(4);
int n = channel.read(buffer);
```

This is an illustration snippet that belongs inside a method handling `IOException` with `channel` reading the target file. If `read` retrieves both bytes, it returns **`2`**. Byte `0x00` is not “unreadable”; byte `0xFF` is not EOF. The `-1` value belongs to the **`int` return value of the read method**, not a byte inside `ByteBuffer`.

This is also why many Java APIs choose `int` for read return values: they need a negative sentinel outside the valid byte counts. With `InputStream.read()` (reading one byte), `0 .. 255` is data while `-1` is EOF; do not confuse it with `ReadableByteChannel.read(ByteBuffer)` which returns a **byte count**.

## 7. Why Do `flip()`, `clear()`, and `remaining()` Affect Understanding `0`?

`read(ByteBuffer)` writes into **the remaining region from `position` to `limit`**. Always check buffer state before diagnosing `0`.

```text
Buffer capacity 8:
  position=8, limit=8 => remaining=0 => no room to write
  clear()             => position=0, limit=8 => room to write
  read() returns 3    => position=3, limit=8
  flip()              => position=0, limit=3 => only 3 bytes can be read
  consume 3 bytes     => position=3, limit=3
  compact()           => position=0, limit=8 => ready to write more
```

- `clear()`: resets to **write fresh from the start**; does not wipe old storage. Use when the buffer has no bytes left to preserve.
- `flip()`: switches to **reading bytes already written** by setting `limit` to the current `position`, then `position=0`.
- `compact()`: shifts **unconsumed** bytes to the start, preparing to write more into the remaining free space. Useful in streaming protocols when a frame can arrive across multiple `read` calls.
- `hasRemaining()`: asks whether elements remain in the current `position .. limit` range; does not indicate whether the channel has external bytes left.
- `remaining()==0` after `flip()` only means the buffer's read region is empty; it does not mean the source stream hit EOF.

Classic mistake: reading `2` bytes, then calling `clear()` before processing; the application loses the boundary of the 2 new bytes and may misread leftover backing storage. Conversely, forgetting `clear()`/`compact()` after reading out of a buffer causes the next `channel.read(buffer)` call to return `0` even though the source still has bytes.

## 8. Proper File Channel Loop and Why Not to Wait Forever

When reading a regular file with `FileChannel` into a buffer that always has `remaining()>0`, a clear pattern is:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;

static long drain(FileChannel source) throws IOException {
    ByteBuffer buffer = ByteBuffer.allocate(8192);
    long total = 0;

    while (true) {
        buffer.clear();
        int n = source.read(buffer);

        if (n == -1) {
            return total;
        }
        if (n == 0) {
            // For FileChannel with space in buffer, check unusual conditions
            // or apply an appropriate policy; do not treat 0 as EOF.
            continue;
        }

        total += n;
        buffer.flip();
        while (buffer.hasRemaining()) {
            byte b = buffer.get();
            // Process byte b; here merely illustrating data consumption.
        }
    }
}
```

This is an **illustrative method**, not a standalone Java file; place it in a class with imports. It counts bytes read during the current read pass and consumes bytes from the buffer without returning file contents. In real applications, do not keep an unconditional `continue` if the channel type can repeatedly return `0`: use an appropriate limit/wait mechanism. The caller is responsible for opening and closing the `FileChannel`; the method does not close the channel because it does not own that resource.

Several important details:

- `n < buffer.capacity()` **does not mean** EOF. Keep looping.
- After `-1`, stop the `read` loop. If application logic still holds bytes in the buffer, finish processing them or report an incomplete frame error.
- Remember to check exceptions such as `ClosedChannelException`, `AsynchronousCloseException`, `IOException`; `read` never uses `0` as an error code.
- If the underlying resource can be modified concurrently, reads and file position must be coordinated; do not infer the number of read calls from a pre-measured file size.

## 9. Non-Blocking Socket Loop: `0` Leads to Waiting, `-1` Leads to Ending Input

Unlike ordinary files, sockets connect to a stream of data arriving over time. Put `SocketChannel` in non-blocking mode and register it with a `Selector` to avoid waiting by burning CPU.

Logic flow:

```text
Selector notifies readability
            |
      SocketChannel.read(dst)
         /       |         \
      n > 0     n == 0      n == -1
        |           |           |
   New bytes    No bytes      Read-side EOF
   parse/acc-   right now     handle buffered data
   umulate      return to     then finish reading
                loop
```

When `n>0`, read data into the buffer, `flip()`, parse **only complete frames**, then `compact()` to retain any partial frame. When `n==0`, do not discard unprocessed data in the buffer or assume the connection dropped; simply let the event loop keep waiting. When `n==-1`, the application should stop expecting input on the channel and decide how to close/half-close based on the protocol.

Illustrative single-event handler skeleton, **not a standalone Java program**:

```java
// socket is open, non-blocking; dst is ready to be written into.
// Buffer read/write modes must be managed across callbacks.
int n = socket.read(dst);

if (n == -1) {
    // Peer ended output; process any buffered application data.
    // Deregister read interest / close per protocol rules.
} else if (n == 0) {
    // No progress right now; return control to event loop.
} else {
    dst.flip();
    // parseCompleteMessages(dst): consume only messages with all bytes present.
    dst.compact();  // Preserve any bytes of an incomplete message.
}
```

If `dst` is full while an incomplete message remains, `compact()` may still leave `remaining()==0` after shifting. At that point you need a **larger buffer or a frame-size limit policy**, not infinite `read` calls. `Selector` can also wake up while the actual read still returns `0`; readiness is not an ironclad promise that bytes will be readable at every moment.

**Do not treat `read()==0` as “the server sent an empty packet”.** TCP is a byte stream; there is no `read=0` event meaning “a zero-length message”. If an application protocol has 0-byte frames, that frame must be represented by the protocol's own header/length framing.

## 10. Distinguishing `read` and `write`: `write()==0` Also Matters

`WritableByteChannel.write(ByteBuffer)` returns the number of bytes **taken from the buffer to send/write** in that call, which is a value `0` or greater. `write` does not use `-1` for EOF.

- `write() > 0`: consumed part or all of the remaining bytes in `src`; `src.position()` advances.
- `write() == 0`: no bytes were written this time. For instance, `src.remaining()==0`, or a non-blocking socket cannot accept more writes at that instant.
- `write()` returning less than initial `remaining()`: **partial write**, not an error. Unwritten bytes remain in the buffer.
- Write errors, closed channels, or invalid states are reported via appropriate exceptions.

With a blocking output channel that makes progress, code commonly reads:

```java
while (buffer.hasRemaining()) {
    destination.write(buffer);
}
```

This is an illustration snippet. On a non-blocking socket, the loop above will **busy-spin** if `write` keeps returning `0`. You must pause, register `OP_WRITE` while data remains to be sent, and resume when the socket becomes writable. Do not `clear()` while unsent bytes remain, because doing so loses track of pending bytes.

## 11. EOF Across Multiple Channel Types and Related APIs

| API / Situation | `0` or No-Progress Case | `-1` | Notes |
| --- | --- | --- | --- |
| `ReadableByteChannel.read(ByteBuffer)` | May be `0`; depends on `remaining`, blocking, channel state | End of input stream | Core contract of readable channels |
| `FileChannel.read(ByteBuffer)` | Empty buffer may yield `0` | Read position is already at end of file when called | Short reads are still positive |
| `SocketChannel.read(ByteBuffer)` non-blocking | No bytes available at call time may yield `0` | Input stream has ended | Needs event loop/selector |
| `SocketChannel.read(ByteBuffer)` blocking | With buffer space, waits until a byte is read or EOF/error | Input stream ended | Do not use `0` as peer-close signal |
| `ScatteringByteChannel.read(ByteBuffer[])` | Total bytes read may be `0` | Input stream ended | Returns `long`, not `int`; buffers receive data in order |
| `AsynchronousFileChannel.read(...)` | Async completion result may be `0` if no space or no progress | Reading at/past end of file | Result received via `Future<Integer>` or callback, not directly from initiation call |
| `WritableByteChannel.write(ByteBuffer)` | `0` = no bytes written this pass | Does not use EOF `-1` | Partial writes must be handled |
| `InputStream.read(byte[])` | When buffer length is 0 or per stream contract | EOF is also `-1` | Stream API differs from channels; check each overload contract |

### With Asynchronous Channels, Results Arrive Differently in Time

`AsynchronousFileChannel.read(dst, position)` **returns `Future<Integer>`**, while `read(dst, position, attachment, handler)` delivers the result to a `CompletionHandler`. Here `0` and `-1` live inside **the completion result of the I/O operation**, not as a direct return value from initiating the call.

For `AsynchronousByteChannel`, if `dst.remaining()==0`, an asynchronous read may complete immediately with `0` without starting real I/O. If `-1` is received, input has ended. With all asynchronous APIs, do not arbitrarily mutate `ByteBuffer` state before the operation using that buffer completes.

## 12. Common Programming Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| `if (n <= 0) break;` | Lumps `0` with `-1`; on non-blocking sockets drops the chance to read data arriving later | Separate `n==-1`, `n==0`, `n>0` |
| `while (channel.read(buf) != -1) {}` | No buffer processing; once full, keeps returning `0` and loops forever | Call `flip()`, consume, `clear()`/`compact()` at the right times |
| `if (n < buf.capacity()) break;` | A short read does not equal EOF | Stop only on EOF, protocol end, or business condition |
| `while (socket.read(buf)==0) {}` | Busy loop on non-blocking I/O | Yield control back to `Selector` or scheduler |
| Closing the socket upon receiving `0` | `0` does not signal input closed | Keep monitoring read readiness |
| Receiving `-1` and discarding data read earlier | A partial frame may remain in the buffer | Finalize or report incomplete frame per protocol |
| Reading into a full buffer and concluding the file is empty | No space left to receive bytes | Use `flip()`, consume, `clear()` or `compact()` |
| Treating `buffer.array()` as the full read result | Array contains stale/invalid bytes | Use `n`, `remaining()` after `flip()`, and proper offsets |
| Confusing `0x00` with read `0`, or `0xFF` with EOF | One is a byte value, the other is a byte count/sentinel | Read data from buffer; check return value separately |
| Thinking `write()==0` means receiver closed | Zero progress on write is not proof of a dead connection | Wait for `OP_WRITE` or handle exceptions |
| Catching `IOException` and returning `-1` from a wrapper | Masks an I/O error as valid EOF | Preserve error type or explicit retry/timeout policy |

## 13. Practical Scenarios

### A. Reading an Entire File of Any Size

Use a fixed-size buffer, call `read` repeatedly, accumulate `n>0` byte counts, and stop on `-1`. You do not need to know total file size beforehand. Use `flip()` each pass to process newly received data, and `clear()` once fully consumed.

### B. Network Protocol with Explicit Message Length

Suppose a 4-byte header encodes the body length. One `read` might return `1`, `2`, or `3` bytes of the header. Any positive value is progress; until 4 bytes arrive, accumulate them. When `read` returns `0`, wait for more data without emitting a bad message; when it returns `-1` before a complete header/body arrives, report a truncated frame per application rules.

### C. Reading from a Socket and Writing to a File

`SocketChannel.read` returns `0` in non-blocking mode: let `Selector` wait for the next batch. When `n>0`, `flip()` the buffer and write until all data is consumed (or queue any remainder for output). On `-1`, finish/close input and flush any remaining output; do not drop unwritten data merely because the source hit EOF.

## 14. Self-Check Questions

**1.** `channel.read(buffer)` returns `0`; are we definitely at the end of the file?  
**Answer:** No. Check `buffer.remaining()`, channel type, mode, and I/O state. `0` only indicates that this call read no bytes.

**2.** A file has 5 bytes, buffer capacity is 8, and the first call returns `5`; has EOF been reached yet?  
**Answer:** You cannot conclude EOF from `5` alone. A subsequent read with space in the buffer is what confirms EOF via `-1` if no bytes remain.

**3.** A file contains two bytes with values `0x00` and `0xFF`. If `read(buffer)` retrieves both, what does it return?  
**Answer:** `2`, because the return value is the byte count, not the byte values.

**4.** Non-blocking `SocketChannel` returns `0`; should you immediately call `read` millions of times in a row?  
**Answer:** No. Yield control to the `Selector`/event loop or appropriate wait mechanism; manage buffer state and `OP_READ` registration.

**5.** `read` returns `-1` while the application still holds half a message in the buffer; can that fragment be ignored?  
**Answer:** Depends on the protocol specification. If a complete frame is mandatory, report truncation/protocol error; if the format allows ending there, process the remainder according to business rules.

**6.** Why is the loop `while (channel.read(buffer) != -1)` dangerous?  
**Answer:** It neither consumes nor resets the buffer; once the buffer is full, subsequent reads can return `0` forever. Failing to use the positive return counts can also break data-processing logic.

**7.** What does `write(src)` returning `0` mean?  
**Answer:** That call wrote no bytes; `write` has no `-1` EOF sentinel. Either `src` had no remaining bytes or a non-blocking channel was not ready to accept writes.

## 15. Takeaways

```text
READ:
    n > 0   -> received exactly n bytes, process new data
    n == 0  -> no progress; check buffer and wait if needed
    n == -1 -> input EOF; stop reading and resolve buffered data
    throws  -> I/O error or invalid state; handle separately

WRITE:
    n > 0   -> wrote n bytes
    n == 0  -> no progress; avoid busy loop
    no -1 as an EOF signal
```

In NIO, **a `0` result describes a single call's state, whereas `-1` signals end of the input stream**. Application data must still be delimited using `ByteBuffer.position/limit` and framing rules rather than relying on a single read.

## Official References

- Java SE 21 — `ReadableByteChannel.read(ByteBuffer)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 21 — `FileChannel.read(ByteBuffer)`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 21 — `SocketChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html
- Java SE 21 — `WritableByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/WritableByteChannel.html
- Java SE 21 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 21 — `AsynchronousByteChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousByteChannel.html
- Java SE 21 — `AsynchronousFileChannel`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html

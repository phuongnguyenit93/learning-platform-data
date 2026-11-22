# Sequential, Random Access, Blocking, and Non-Blocking in Java I/O

When designing input/output (I/O) operations, there are two distinct questions:

1. **In what order is data accessed?** Reading/writing **sequentially** or being able to **jump to any arbitrary position** (random access)?
2. **How long must the call wait?** A **blocking** operation may hold the calling thread to wait; a **non-blocking** operation returns control when it cannot be processed immediately.

These are **two conceptually independent classification axes**, not four mutually exclusive types of I/O. A program can read sequentially using a blocking API, or process data sequentially over a non-blocking network connection. Specific combinations depend on the device and API: Java NIO does not provide `configureBlocking(false)` mode for a regular file's `FileChannel`.

## 1. Sequential and Random Access

### 1.1. Sequential Access

With sequential access, a program processes data as a flow from the current position to the next position. For example: reading byte by byte, block by block, or line by line of text; writing continuously to the end or the current position of the stream.

- `InputStream` / `OutputStream` work with bytes; `Reader` / `Writer` work with characters.
- `BufferedInputStream` and `BufferedReader` reduce the number of underlying accesses through buffering. `BufferedReader.readLine()` is suitable for line-delimited text.
- `Files.newInputStream(path)` and `Files.newBufferedReader(path, charset)` are common ways to open a stream/file.
- `mark()` / `reset()` on some `InputStream`s only allow returning to a bookmark when supported; **this is not equivalent** to arbitrarily setting a pointer to any offset.
- "Sequential" refers to the **access pattern**, not a guarantee that data lies physically contiguous on disk or that reading is always fast.

A standalone Java 17+ example that creates a temporary UTF-8 file, reads it line by line, and cleans up the file:

```java
// SequentialDemo.java
import java.io.BufferedReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SequentialDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("sequential-", ".txt");
        try {
            Files.writeString(file, "dòng 1\ndòng 2\n", StandardCharsets.UTF_8);

            try (BufferedReader reader =
                     Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
                String line;
                while ((line = reader.readLine()) != null) {
                    System.out.println(line);
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SequentialDemo.java
java SequentialDemo
```

Output:

```text
dòng 1
dòng 2
```

`readLine()` advances through the content; `null` signals the end of the file. It returns the line content without line break characters. `try-with-resources` closes the reader; `finally` cleans up the temporary file even when an error occurs.

### 1.2. Random Access

Random access allows setting a **logical position (offset)** and reading/writing there without having to read the entire preceding portion sequentially. This technique is suited for fixed indexes, fixed-size records, updating a region in a file, or reading headers/footers.

In Java, there are three representative APIs:

| API | Position and meaning |
| --- | --- |
| `RandomAccessFile` | `seek(long)` moves the file pointer; `getFilePointer()`, `length()`, `setLength()`; supports reading/writing primitive types. |
| `SeekableByteChannel` | Channel abstraction with `position()` and `position(long)`; relative read/write operations use the current position. |
| `FileChannel` | Channel for files; supports `position(long)` and `read(ByteBuffer, long)` / `write(ByteBuffer, long)` at a specified offset **without changing the current position** of the channel. |

Positions in these APIs are measured in **bytes**, not Unicode character count or line count. When using UTF-8 text with multi-byte characters, you cannot assume `seek(10)` corresponds to the 11th character. Also, random access only makes sense when the data source and API support seeking; a TCP socket cannot jump backward to old bytes in a network stream.

Example using `RandomAccessFile` with three `int` integers (4 bytes each):

```java
// RandomAccessDemo.java
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class RandomAccessDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("random-", ".bin");
        try {
            try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "rw")) {
                raf.setLength(0);
                raf.writeInt(10);  // bytes 0..3
                raf.writeInt(20);  // bytes 4..7
                raf.writeInt(30);  // bytes 8..11

                raf.seek(4);
                System.out.println("second = " + raf.readInt());

                raf.seek(8);
                raf.writeInt(99);  // overwrite the third number
                raf.seek(0);
                System.out.println("values = " +
                        raf.readInt() + ", " + raf.readInt() + ", " + raf.readInt());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac RandomAccessDemo.java
java RandomAccessDemo
```

Output:

```text
second = 20
values = 10, 20, 99
```

`seek(4)` goes directly to the second integer; `seek(8)` goes to the third. `writeInt` / `readInt` use a 4-byte binary representation in big-endian order defined by `DataOutput` / `DataInput`, so this is **not** an example of handling numbers as strings. For variable-length records, `seek()` alone is not enough: you need an index structure or storage format that knows each record's offset.

With `FileChannel`, distinguish two styles:

```java
channel.position(100);       // change the logical position of the channel
channel.read(buffer);        // read from the current position, updating position
channel.read(buffer, 500);   // read at byte 500, without changing the current position
```

The three lines above are an **illustrative snippet**, assuming `channel` is already open and `buffer` has remaining space. `read` may read fewer bytes than requested; when a full block is needed, you must loop and check for EOF. Seek APIs do not automatically make I/O non-blocking.

## 2. What Do Blocking and Non-Blocking Actually Mean?

### 2.1. Blocking I/O

With blocking I/O, the ongoing call **may wait** until data arrives, a connection is accepted, a resource becomes ready, or the operation completes / fails. During that time, the Java thread calling the API does not continue executing subsequent statements.

Examples:

- `InputStream.read()` on a socket may wait for the peer to send data, close its output, or raise an error.
- `ServerSocket.accept()` and `ServerSocketChannel.accept()` in blocking mode may wait for an incoming connection.
- `SocketChannel.read(ByteBuffer)` in default blocking mode may wait for data when the buffer has remaining space.
- `FileChannel.read` / `write` are synchronous operations and may block while accessing the file system, even though they belong to the `java.nio` package.

"Blocking" **does not mean every call always waits a long time**: if data is already ready, it can return immediately. Nor does it mean `read` always fills the buffer; the number of bytes returned must be checked. A read path can end with EOF (`-1`) or an error. Timeout/cancellation mechanisms differ across APIs; you cannot assume every blocking call shares the same interruption behavior.

### 2.2. Non-Blocking I/O

In non-blocking mode, an operation on a supported channel can return immediately even when no data has been read/written yet. Application code decides when to retry or registers **readiness events** with a `Selector`.

Java NIO applies `configureBlocking(false)` to `SelectableChannel` implementations such as:

- `SocketChannel` — TCP communication;
- `ServerSocketChannel` — accepting TCP connections;
- `DatagramChannel` — sending/receiving UDP.

Example of `SocketChannel.read(dst)` when `dst` has remaining space:

| Result | Interpretation |
| --- | --- |
| `n > 0` | Read `n` bytes; not necessarily a complete message. |
| `n == 0` | No bytes have been read right now; common in non-blocking mode, not EOF. |
| `n == -1` | Reached the end of the connection's input stream. |
| Throws exception | An I/O error occurred; handle/close resources appropriately. |

For `SocketChannel.write(src)`, a single write may process **fewer than** `src.remaining()` bytes, even in situations where a full write should not be assumed. If non-blocking returns `0`, retain the unsent portion of the buffer and wait for the next readiness event; **do not discard unsent data**.

Note: `Selector.select()` **may block itself** waiting for events even when the registered channels are in non-blocking mode. Use `selectNow()` or `select(timeout)` when a different waiting policy is needed. Non-blocking helps one thread manage many connections using events; by itself, it does not guarantee higher speed for every workload.

## 3. Two-Axis Matrix and API Selection

| Access Type | Blocking/synchronous | Non-blocking/asynchronous |
| --- | --- | --- |
| **Sequential** | `BufferedReader` reading lines from a file; `InputStream` on a socket; blocking `SocketChannel`. | Non-blocking `SocketChannel` / `DatagramChannel` + `Selector` handling byte streams or datagrams by events. |
| **Random** | `RandomAccessFile`, `SeekableByteChannel`, `FileChannel` accessing file offsets. | For regular files, Java does not allow converting `FileChannel` into selectable non-blocking mode. `AsynchronousFileChannel` provides an asynchronous positional API, but that is a separate **completion model**, not `SocketChannel.configureBlocking(false)`. |

Two properties should be viewed independently when reading library names:

- **`java.io` and `java.nio` are not absolute synonyms for blocking and non-blocking.** NIO includes synchronous `FileChannel`, dual-mode `SocketChannel`, and `AsynchronousFileChannel`.
- **`AsynchronousFileChannel.read(buffer, position)`** returns a `Future<Integer>` or accepts a `CompletionHandler`. Calling `future.get()` may cause the calling thread to wait. Having an asynchronous API does not guarantee disk operations always run without background threads.
- **Memory-mapped files** (`FileChannel.map`) support positional access through a mapped buffer, yet page faults / data access can still wait on I/O; they should not be labeled "always non-blocking".
- A sequential `BufferedReader` read can still be backed by a file that supports random access; this is a choice of **how the program accesses data**, not an immutable property of every file.

## 4. `Selector`: Readiness Events in Non-Blocking Networking

Basic processing flow:

1. Open a `SelectableChannel` and call `configureBlocking(false)`.
2. Register the channel with a `Selector` using the appropriate interest operations (`OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE`).
3. Call `select()`/`select(timeout)` to wait; iterate through `selectedKeys()` and **remove each handled key** from the selected set.
4. For an accepted connection, configure the new socket to non-blocking and register `OP_READ`.
5. When readable, read into a `ByteBuffer`; handle `> 0`, `0`, `-1`; retain incomplete message fragments. When writable, continue writing the remaining portion of the buffer.
6. Cancel keys/close channels when done or on error; manage timeouts and buffer limits in production.

A self-contained loopback example with a **server in non-blocking mode** using `Selector`. The client in this example intentionally uses default blocking mode to send a short message; this clearly demonstrates that I/O mode is determined **per channel**:

```java
// NonBlockingDemo.java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Iterator;

public class NonBlockingDemo {
    public static void main(String[] args) throws Exception {
        try (ServerSocketChannel server = ServerSocketChannel.open();
             Selector selector = Selector.open()) {

            server.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), 0));
            server.configureBlocking(false);
            server.register(selector, SelectionKey.OP_ACCEPT);

            try (SocketChannel client = SocketChannel.open()) {
                client.connect(server.getLocalAddress());

                ByteBuffer outgoing =
                        ByteBuffer.wrap("ping".getBytes(StandardCharsets.UTF_8));
                while (outgoing.hasRemaining()) {
                    client.write(outgoing);
                }
                client.shutdownOutput();

                ByteArrayOutputStream received = new ByteArrayOutputStream();
                long deadline = System.nanoTime() + Duration.ofSeconds(5).toNanos();
                boolean eof = false;

                while (!eof && System.nanoTime() < deadline) {
                    selector.select(1000);
                    Iterator<SelectionKey> keys = selector.selectedKeys().iterator();

                    while (keys.hasNext()) {
                        SelectionKey key = keys.next();
                        keys.remove();

                        if (key.isAcceptable()) {
                            SocketChannel peer = server.accept();
                            if (peer != null) {
                                peer.configureBlocking(false);
                                peer.register(selector, SelectionKey.OP_READ);
                            }
                        } else if (key.isReadable()) {
                            SocketChannel peer = (SocketChannel) key.channel();
                            ByteBuffer buffer = ByteBuffer.allocate(32);
                            int n;

                            while ((n = peer.read(buffer)) > 0) {
                                buffer.flip();
                                received.write(buffer.array(), 0, buffer.remaining());
                                buffer.clear();
                            }
                            if (n == -1) {
                                peer.close();
                                eof = true;
                            }
                        }
                    }
                }

                if (!eof) {
                    throw new IOException("Timeout waiting for EOF");
                }
                System.out.println(received.toString(StandardCharsets.UTF_8));
            }
        }
    }
}
```

```bash
javac NonBlockingDemo.java
java NonBlockingDemo
```

Output under normal loopback conditions:

```text
ping
```

Explanation: the operating system allocates an available loopback port; `OP_ACCEPT` signals an incoming connection to accept; the peer is switched to non-blocking and registered for `OP_READ`. The client sends four bytes and calls `shutdownOutput()`, so the server can observe EOF `-1` after the data. Although `selector.select(1000)` may wait, `server.accept()` and `peer.read()` on the server in non-blocking mode will not block waiting for data/connections. The example includes a deadline to avoid an infinite loop when running in an abnormal network environment.

In a real program, a single `read` cannot be treated as one TCP message. TCP is a **byte stream** and does not preserve boundaries between `write` calls. Define message framing (length prefix, delimiter, or protocol headers), retain buffers across multiple events, and decode UTF-8 characters only after collecting complete byte sequences. For large data, do not allocate a new `ByteBuffer` on every event as in the illustrative example; manage buffers per connection.

### Common Pitfalls When Using NIO

- **`ByteBuffer.flip()`** switches from writing into the buffer to reading data from the buffer; **`clear()`** prepares for writing again without erasing physical bytes. If there is partially read data, use **`compact()`** to keep the unprocessed portion.
- Non-blocking `read() == 0` does not signal EOF; do not use a continuous `while (read(...) == 0) {}` spin loop as it wastes CPU. Typically, register `OP_READ` and wait for a new event.
- Only enable `OP_WRITE` when there is actually data waiting to be sent. Connections are frequently writable, so registering `OP_WRITE` unconditionally easily causes `select()` to wake up repeatedly (busy loop).
- `OP_CONNECT` pairs with a non-blocking connecting `SocketChannel`: `connect()` may return `false`, and when ready to connect you must check `finishConnect()`.
- "Readable" / "writable" events indicate **readiness at the moment of observation**, not a guarantee of filling the buffer or completing message transmission. The connection may close or fail between the event notification and the operation.
- Do not arbitrarily mix an `InputStream` obtained from a socket with selector logic on the same socket; coordinate a clear single read/write model per connection.

## 5. Pros/Cons Comparison and Selection Scenarios

| Need | Recommendation | Why |
| --- | --- | --- |
| Reading logs or CSV from start to finish | `BufferedReader` / `Files.newBufferedReader` | Sequential reading, minimal state, easy to combine with line processing. |
| Updating a binary record at a known offset | `RandomAccessFile` or `FileChannel` | Direct access to byte position, avoiding reading the whole file first. |
| Copying a large file block by block | Buffered streams or `FileChannel` | Processes data in chunks without loading the entire file into RAM. |
| TCP server with many connections handled by few I/O threads | Non-blocking `SocketChannel` + `Selector` | One event loop can multiplex many channels; requires managing state and buffers. |
| Small application, few connections, wanting easy-to-follow code | Blocking sockets or high-level abstraction libraries | Linear control flow is usually easier to write and test. |
| Reading multiple file regions via a completion API | `AsynchronousFileChannel` with `CompletionHandler` / `Future` | Knows offsets and receives results upon completion without designing a file selector yourself. |

**Performance is not determined by labels alone.** Random access can increase seeks / random disk I/O and hurt memory locality; sequential reading often benefits from readahead. Non-blocking helps reduce waiting threads when managing many sockets, but state machines, selectors, framing, and backpressure add complexity. Measure the actual workload (connection count, buffer size, latency, throughput, CPU/RAM usage) before changing designs.

## 6. Common Misconceptions and How to Check

1. **“Using `java.nio` means non-blocking.”** False: `FileChannel` and many NIO APIs still perform synchronous I/O; check whether the channel is a `SelectableChannel` and its `isBlocking()` state.
2. **“Random access makes operations not wait on disk.”** False: seeking only changes the logical position; data retrieval can still block.
3. **“Non-blocking read returning `0` means end of stream.”** False: `-1` indicates EOF for `SocketChannel.read`.
4. **“`read(buffer)` always reads the requested number of bytes.”** False: the number of bytes read may be less than the destination capacity; rely on the return value, buffer state, and protocol.
5. **“Selector runs code automatically when data arrives.”** False: the application must run an event loop, iterate over selected keys, read/write, and manage state.
6. **“`Future.get()` is a way to read files that never blocks.”** False: calling `get()` may wait; for asynchronous processing, structure the program to continue other work or use a completion callback.
7. **“Seeking by character count is the same as seeking by byte count.”** False for UTF-8 and many other encodings; you need a byte index or proper sequential decoding.

Self-check: (a) Want to read line 1 to the last line of a text file—which access type should be used? **Sequential**. (b) Want to replace a byte at offset 4096 of a binary file? **Random access** via a seekable API. (c) A non-blocking `SocketChannel` returns `0` when reading? **No bytes could be read at that moment**, keep state and wait for readiness. (d) Does `FileChannel.position(4096)` make the next read automatically non-blocking? **No**.

Key takeaway: **sequential/random access answers "where to read"; blocking/non-blocking answers "whether the call waits or not".** Choose an API based on the nature of the data source and processing requirements, and check the result of every read/write operation rather than inferring from class names.

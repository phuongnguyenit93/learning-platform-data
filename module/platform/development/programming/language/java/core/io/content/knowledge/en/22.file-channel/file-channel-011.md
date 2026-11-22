# `FileChannel` Is Not a `SelectableChannel` in Java NIO

## 1. Objectives and Real-World Problem

`java.nio.channels.FileChannel` is an important API for reading/writing files with `ByteBuffer`, moving the position within a file, accessing by offset, transferring data between channels, and mapping files into memory. However, **`FileChannel` is not a `SelectableChannel`**, so it cannot be registered directly with a `Selector` to receive `OP_READ` or `OP_WRITE` events like `SocketChannel` or `Pipe.SourceChannel`.

This is a **Java NIO type-contract limitation**, not a missing import or a forgotten initialization method. Some confusion comes from both containing the word "channel", yet they solve two different sets of needs.

After this lesson, you will be able to:

1. Explain why `FileChannel` has neither `register(Selector, ops)` nor `configureBlocking(false)`.
2. Distinguish offset-based file I/O from readiness-based I/O on sockets/pipes.
3. Write and run a program proving `FileChannel` does not implement `SelectableChannel` yet supports random file access.
4. Register a **truly selectable channel** with `Selector`, using `SelectionKey.OP_READ` properly.
5. Choose the right solution when you need to process files without blocking a business thread: `AsynchronousFileChannel`, offloading tasks to another thread, or `WatchService` for directory change notifications.
6. Avoid misinterpreting file EOF, "ready" state on a selector, and promises of optimized data-transfer methods.

Examples target **Java 17+**, using standard Java SE with no Spring or external libraries.

## 2. Two Channel Families with Different Purposes

### `FileChannel`: Working with Bytes at File Positions

`FileChannel` belongs to `java.nio.channels`, extends `AbstractInterruptibleChannel`, and implements interfaces related to byte I/O, including:

- `SeekableByteChannel`: `position()`, `position(long)`, `size()`, `truncate(long)`.
- `ReadableByteChannel` and `WritableByteChannel`: reading/writing via `ByteBuffer` when the channel is opened with permitting options.
- `ScatteringByteChannel` and `GatheringByteChannel`: reading/writing across multiple `ByteBuffer` instances.
- Dedicated capabilities: `read(dst, position)`, `write(src, position)`, `transferTo`, `transferFrom`, `map`, `lock`, `tryLock`, `force`.

A `FileChannel` is typically opened via:

```java
try (FileChannel file = FileChannel.open(
        path,
        StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(4096);
    int n = file.read(buffer);
}
```

This snippet requires declaring `path`, importing `FileChannel`, `ByteBuffer`, `StandardOpenOption`, and handling `IOException`. `n` is the actual number of bytes read; it may be smaller than the buffer capacity. When the end of the file is reached, `read` returns `-1`.

### `SelectableChannel`: Selecting Channels with Ready I/O States

`SelectableChannel` is an abstract class for channels that can register with a `Selector` to monitor a set of **readiness operations**. It provides distinctive APIs:

- `configureBlocking(boolean)` / `isBlocking()`: selects blocking or nonblocking mode, if supported by the channel.
- `validOps()`: bitmask of operations registrable for that specific channel.
- `register(Selector, int)`: registers to receive notifications via a `SelectionKey`.
- `keyFor(Selector)` and `isRegistered()`: checks registration.

Common selectable channel types are:

| Type | Typically valid operations | Purpose |
| --- | --- | --- |
| `SocketChannel` | `OP_CONNECT`, `OP_READ`, `OP_WRITE` | TCP connections |
| `ServerSocketChannel` | `OP_ACCEPT` | Accepting new TCP connections |
| `DatagramChannel` | `OP_READ`, `OP_WRITE` | UDP |
| `Pipe.SourceChannel` | `OP_READ` | Reading bytes from a pipe |
| `Pipe.SinkChannel` | `OP_WRITE` | Writing bytes into a pipe |
| **`FileChannel`** | **Has no `SelectionKey`/`validOps()` of `SelectableChannel`** | **File I/O; does not register with a selector** |

Actual operations and states depend on the channel. For example, `OP_ACCEPT` only makes sense on `ServerSocketChannel`; merely being in the same NIO package does not mean every channel accepts every bit.

## 3. Type Relationship Diagram: Similar Names, Different Branches

```text
                      Channel (interface)
                         |
          +--------------+----------------------+
          |                                     |
   ByteChannel /                           other Channels
   SeekableByteChannel                          |
          |                              SelectableChannel
      FileChannel                            (abstract)
   (abstract class)                             |
     | does not extend                  AbstractSelectableChannel
     | SelectableChannel                        |
     +--------------------X              SocketChannel,
                                          ServerSocketChannel,
                                          DatagramChannel,
                                          Pipe.SourceChannel,
                                          Pipe.SinkChannel
```

The diagram intentionally shows only **relationships relevant to selectability**, not the full inheritance hierarchy of all interfaces. Both `FileChannel` and `SelectableChannel` belong to the `Channel` framework, yet `FileChannel` neither extends nor implements the `SelectableChannel` API.

A channel **can be both `ReadableByteChannel` and selectable** (for example, `SocketChannel`); therefore, classifying merely by "has `read(ByteBuffer)`" is insufficient. What determines whether `register` is possible is whether the object is a **`SelectableChannel`** and supports the relevant operation.

### What Cannot Be Done

```java
FileChannel file = FileChannel.open(path, StandardOpenOption.READ);

// The following lines are INTENTIONALLY WRONG, will not compile:
// file.configureBlocking(false);
// file.register(selector, SelectionKey.OP_READ);
// file.validOps();
```

The snippet above is **erroneous illustration code**: `FileChannel` does not declare those methods. Casting to `SelectableChannel` does not transform the object either, and fails if attempted through a `Channel` or `Object` reference. No overload of `Selector.register` accepts a `FileChannel`.

Registering a `SelectableChannel` still in **blocking mode** is also invalid: `register` requires nonblocking mode and may throw `IllegalBlockingModeException`. With `FileChannel`, however, you do not even reach the blocking-mode check because the channel type itself is not selectable.

## 4. "Blocking I/O" Differs from "Selector Readiness"

A **blocking call** means the calling thread may have to wait for the operation to finish or fail. With files, the OS may need to read blocks from a device, handle caches, network filesystems, or sync metadata. The duration may be very short, yet you still cannot assume `FileChannel.read()/write()` never waits.

**Selector readiness** is a mechanism to wait for one or more `SelectableChannel` instances to report an operation as ready; for instance, a socket has bytes waiting to be read. Readiness does not promise that any single I/O call will process all data at once, does not replace checking `read()/write()`, and does not itself indicate that an application-protocol message has arrived completely.

For regular files, the OS may report them as always ready for reading in many contexts, so the notion of readiness is generally not useful in the same way as for sockets. **The underlying OS rationale is not a substitute for the Java API contract**: the accurate, stable, and sufficient conclusion for Java programming is that **`FileChannel` does not implement `SelectableChannel`**.

Comparing three easily confused terms:

| Question | Where it is answered | Meaning |
| --- | --- | --- |
| How many bytes are in the file and from what offset are we reading? | `FileChannel.size()`, `position()` | File / read-cursor state |
| Can a socket/pipe be read immediately under the readiness model? | `Selector`, `SelectionKey.isReadable()` | Operation readiness state on a selectable channel |
| When does a file operation finish? | `FileChannel.read()` returning; or `Future/CompletionHandler` of `AsynchronousFileChannel` | Operation result / completion |

An `OP_READ` event does **not** mean EOF, "file changed", or "full record read". Do not design a log-tailing application by trying `fileChannel.register(selector, OP_READ)`.

## 5. Runnable Java 17+ Example: Proving `FileChannel` Is Not Selectable

Save as **`FileChannelNotSelectableDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.channels.Channel;
import java.nio.channels.FileChannel;
import java.nio.channels.SelectableChannel;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelNotSelectableDemo {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("not-selectable-", ".txt");

        try {
            Files.writeString(file, "ABC", StandardCharsets.US_ASCII);

            try (FileChannel channel =
                         FileChannel.open(file, StandardOpenOption.READ)) {

                // Runtime check through the common Channel interface.
                Channel asChannel = channel;

                System.out.println("selectable="
                        + (asChannel instanceof SelectableChannel));
                System.out.println("seekable="
                        + (asChannel instanceof SeekableByteChannel));
                System.out.println("size=" + channel.size());

                channel.position(1);
                ByteBuffer buffer = ByteBuffer.allocate(2);
                int read = channel.read(buffer);

                buffer.flip();
                byte[] bytes = new byte[buffer.remaining()];
                buffer.get(bytes);

                System.out.println("bytesRead=" + read);
                System.out.println("text="
                        + new String(bytes, StandardCharsets.US_ASCII));
                System.out.println("position=" + channel.position());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run:

```bash
javac FileChannelNotSelectableDemo.java
java FileChannelNotSelectableDemo
```

Stdout when file operations succeed:

```text
selectable=false
seekable=true
size=3
bytesRead=2
text=BC
position=3
```

Explanation:

1. `Files.writeString` creates exact 3-byte ASCII content: `A`, `B`, `C`.
2. Variable `asChannel` has the common interface type `Channel`, so `instanceof SelectableChannel` is a valid runtime check. It evaluates to `false` because `FileChannel` has no selectable capability.
3. `SeekableByteChannel` is an interface supported by `FileChannel`, so that result is `true`.
4. `channel.position(1)` moves the read position to the second byte (`B`). `read(buffer)` reads two bytes `BC`, returns `2`, and advances the file position to `3`.
5. `buffer.flip()` switches the buffer from receiving bytes to reading bytes. Then `get(bytes)` extracts the exact newly loaded byte count.
6. `try-with-resources` closes the channel before deleting the temporary file.

No line needs a `Selector` in this file-reading task. When the goal is processing file data by position, `FileChannel` already provides the right API.

## 6. Truly Selectable Example: `Pipe.SourceChannel` and `Selector`

To see the difference, use `Pipe.SourceChannel`. It is a `SelectableChannel`, can be switched to nonblocking mode, and can register `OP_READ`.

Create file **`PipeSelectorDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Pipe;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

public class PipeSelectorDemo {
    public static void main(String[] args) throws Exception {
        Pipe pipe = Pipe.open();

        try (Pipe.SourceChannel source = pipe.source();
             Pipe.SinkChannel sink = pipe.sink();
             Selector selector = Selector.open()) {

            source.configureBlocking(false);
            source.register(selector, SelectionKey.OP_READ);

            // Write bytes into the pipe so the source side has data to read.
            ByteBuffer outgoing = ByteBuffer.wrap(
                    "ready".getBytes(StandardCharsets.US_ASCII));
            while (outgoing.hasRemaining()) {
                sink.write(outgoing);
            }

            int n = selector.select(3000); // at most 3 seconds
            if (n == 0) {
                throw new IOException("No readiness event in time");
            }

            Iterator<SelectionKey> it =
                    selector.selectedKeys().iterator();

            while (it.hasNext()) {
                SelectionKey key = it.next();
                it.remove(); // done handling this key for this selection pass

                if (key.isValid() && key.isReadable()) {
                    ByteBuffer incoming = ByteBuffer.allocate(16);
                    int count = source.read(incoming);
                    if (count > 0) {
                        incoming.flip();
                        byte[] data = new byte[incoming.remaining()];
                        incoming.get(data);

                        System.out.println("readable=true");
                        System.out.println("text="
                                + new String(data, StandardCharsets.US_ASCII));
                    }
                }
            }
        }
    }
}
```

```bash
javac PipeSelectorDemo.java
java PipeSelectorDemo
```

Stdout **when pipe and selector operations behave normally**:

```text
readable=true
text=ready
```

Execution flow:

1. `Pipe.open()` creates a channel pair: `SinkChannel` for writing and `SourceChannel` for reading.
2. `source.configureBlocking(false)` permits registration with the selector.
3. `source.register(selector, SelectionKey.OP_READ)` requests notification when the read side has data.
4. Writing `"ready"` to `sink` makes data ready for `source`; `selector.select(3000)` waits up to 3 seconds for an event. If the environment fails to signal an event in time, the example throws an error instead of printing results.
5. Once a readable key arrives, `source.read(incoming)` must still report the actual bytes read. `incoming.flip()` lets only the received bytes be decoded.

If you omit `source.configureBlocking(false)`, registering a blocking channel with `Selector` can cause `IllegalBlockingModeException`. This is an example of **true readiness**. Replacing `Pipe.SourceChannel` with `FileChannel` will fail to compile at the `register` line.

## 7. Proper Approaches When You Want to Process Files Without Waiting on the Main Thread

"Not wanting to block the event loop" does not equate to "must use `Selector`". Depending on requirements, better-suited approaches exist.

### Approach A: `AsynchronousFileChannel` (Java NIO.2)

`AsynchronousFileChannel` provides read/write overloads returning `Future<Integer>` or taking `CompletionHandler<Integer, A>`. You specify a file offset on each call and receive the result when the operation completes. It is **not a `SelectableChannel`** and still cannot register with a `Selector`.

Characteristics:

- `AsynchronousFileChannel.read(dst, position)` returns `Future<Integer>`.
- Another overload accepts an attachment and a `CompletionHandler` invoked upon success/failure.
- The provider/JDK implementation may use OS asynchronous I/O or a thread pool. The API does not guarantee every filesystem or JVM has native kernel async I/O.
- `Future.get()` blocks the thread **calling get** until the Future completes; so to keep the main thread unblocked, structure work via callbacks, completions, or an appropriate executor.
- The `read` result is the actual number of bytes read; do not assume every call fills `ByteBuffer`. `-1` indicates EOF.

### Complete Java 17+ Example with `AsynchronousFileChannel`

Save as **`AsyncFileReadDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.nio.channels.AsynchronousFileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Future;

public class AsyncFileReadDemo {
    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("async-file-", ".txt");

        try {
            Files.writeString(path, "HELLO", StandardCharsets.US_ASCII);

            try (AsynchronousFileChannel file =
                         AsynchronousFileChannel.open(
                                 path, StandardOpenOption.READ)) {

                ByteBuffer dst = ByteBuffer.allocate(5);
                long offset = 0;

                while (dst.hasRemaining()) {
                    Future<Integer> future = file.read(dst, offset);
                    int n = future.get(); // demo waits for result here

                    if (n == -1) {
                        break;
                    }
                    if (n == 0) {
                        throw new IllegalStateException(
                                "Read did not make progress");
                    }
                    offset += n;
                }

                dst.flip();
                byte[] result = new byte[dst.remaining()];
                dst.get(result);

                System.out.println("bytes=" + result.length);
                System.out.println("text="
                        + new String(result, StandardCharsets.US_ASCII));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac AsyncFileReadDemo.java
java AsyncFileReadDemo
```

Stdout on successful completion:

```text
bytes=5
text=HELLO
```

In this learning example, `future.get()` is called to observe completion simply. A real model that wants to keep a request-handling thread non-blocking **does not call `get()` right on the event loop**; instead it uses a completion mechanism or moves waiting onto an executor. `AsynchronousFileChannel` does not become selector-registrable just because its name contains `Asynchronous`.

### Approach B: Running File I/O on a Worker Thread

If an application uses an event loop for sockets yet occasionally needs to read regular files, you can offload `FileChannel.read` / `write` calls onto a dedicated executor and dispatch the processed result back to the coordinator. The I/O thread may still wait, yet the event loop is not tied up by file tasks.

In Java 17, `ExecutorService` with `submit`/`Future` is the foundational illustration. You must size the pool, bound queued tasks, configure timeouts, handle cancellation, close channels, and pass results safely. Never spawn unbounded threads per byte/record or use an unbounded queue when data arrives faster than disk speed.

This approach fits well when you must call a synchronous file-reading library that cannot easily switch to an async API.

### Approach C: `WatchService` to Know When a Directory/File Changes

If the problem is "when a log file is modified, inspect the new portion", explore `java.nio.file.WatchService`:

- Register a **directory** with `WatchService` using events such as `ENTRY_CREATE`, `ENTRY_MODIFY`, and `ENTRY_DELETE`.
- Call `watcher.take()` or `poll()` to receive notifications and then inspect relevant files.
- Once you determine what needs reading, use `FileChannel` or an appropriate file API to fetch the data.

`WatchService` is **not** a `Selector` for file contents. It reports directory-entry change events, may coalesce events or overflow its queue (`OVERFLOW`), and behaves differently across providers/filesystems. You still must re-verify size, offset, deletion, rename, truncation, or replacement, as well as the possibility of incomplete events on remote mounts.

You cannot infer "the file now has a complete log line" merely from receiving `ENTRY_MODIFY`; content parsing must still handle partial chunks and character encoding.

### Approach D: Reading Files with Synchronous `FileChannel` When Appropriate

For CLIs, batch jobs, data import/export, or block-based file processing, a synchronous `FileChannel.read(buffer)` loop is often the simplest and cleanest design:

```java
try (FileChannel file =
             FileChannel.open(path, StandardOpenOption.READ)) {
    ByteBuffer buffer = ByteBuffer.allocate(8192);

    while (true) {
        int n = file.read(buffer);
        if (n == -1) {
            break;
        }
        if (n == 0) {
            continue;
        }

        buffer.flip();
        while (buffer.hasRemaining()) {
            byte value = buffer.get();
            // Process value.
        }
        buffer.clear();
    }
}
```

This snippet requires declaring `path`, imports, and `IOException` handling. For block-oriented file reads, code progresses cleanly without a selector. At large scale, decode/process `ByteBuffer` chunk-by-chunk or via streaming APIs rather than allocating memory proportional to file size.

## 8. File, Pipe, Socket, and Async: Decision Table

| Problem | Appropriate API | Registers with `Selector`? |
| --- | --- | --- |
| Read/write a file at arbitrary offsets | `FileChannel` | No |
| `map` a file into memory for random read/access | `FileChannel.map` | No |
| Lock file regions, `force` data | `FileChannel.lock/force` | No |
| Many sockets operating with readiness | `SocketChannel` + `Selector` | Yes, when configured nonblocking |
| Accept TCP connections | `ServerSocketChannel` + `Selector` | Yes, `OP_ACCEPT` |
| Transfer bytes over an in-process pipe | `Pipe.SourceChannel/SinkChannel` | Yes, per valid operations |
| Read/write files with completion callbacks or Futures | `AsynchronousFileChannel` | No |
| Get notified when directory entries change | `WatchService` | No; uses `take/poll` |
| Call blocking libraries while keeping an event loop free | `FileChannel` + executor / dedicated task | No selector needed |

**Terminology note:** "NIO Channel" is a broad concept. One kind of channel is `FileChannel`, while several others are `SelectableChannel`. The word "NIO" does not mean every operation is nonblocking, nor does it mean every channel works with a selector.

## 9. Technical Misconceptions to Fix

### Misconception 1: "Since both are `Channel`, `FileChannel` can be cast to `SelectableChannel`"

Casting does not implement additional interfaces. An actual object from `FileChannel.open` is not selectable. Trying to force a cast to `SelectableChannel` through a common reference will fail at runtime with `ClassCastException`. Fix: pick the right API from the start.

### Misconception 2: "`FileChannel` would have `configureBlocking(false)` if imported properly"

`configureBlocking` is a method on `SelectableChannel`. `FileChannel` has no such method; the compile error is expected. No portable nonblocking flag exists for `FileChannel` under the same selector contract as sockets.

### Misconception 3: "The file has data, so a selector always reports readable"

`FileChannel` has no `register` method to create a `SelectionKey`, so there is no file readable event on a Java `Selector`. To detect file growth or content changes, inspect metadata, watch the directory with `WatchService`, or coordinate via an explicit protocol.

### Misconception 4: "`Selector` makes file I/O run faster"

A selector multiplexes readiness across supported channels; it is not a turbo button for disk reads. For large files, examine buffer sizes, access patterns, `FileChannel.transferTo/transferFrom`, batching, and device characteristics. Measure realistically instead of guessing from the word "nonblocking".

### Misconception 5: "`FileChannel.transferTo` is always zero-copy and needs no loop"

`transferTo(position, count, target)` can leverage provider/OS-specific optimizations, yet Java does not promise every path is zero-copy or that a single call transfers all `count` bytes. The return value is the **actual** bytes transferred, which can be less than requested; building a complete transfer loop requires advancing the offset and handling zero progress.

For instance, `transferTo` takes `position` as an explicit read offset; it does not even mutate the source channel's `position()` on that call. File mapping/transfer must be verified on its own merits, never cited as evidence that files are selectable.

### Misconception 6: "`read()==-1` on a file means no data will ever arrive again"

When `FileChannel.read()` reads at current EOF, it can return `-1`. However, if another program appends data to the file afterward, reading again at the appropriate offset can see new bytes. With log rotation, a file may be truncated or replaced by another file, while the old channel may stay attached to the old file object. A file-tailing application must manage offsets, size, file identity, events, and resource lifetimes; no selector solves that automatically.

### Misconception 7: "`AsynchronousFileChannel` also uses `Selector`"

`AsynchronousFileChannel` belongs to the asynchronous file I/O API with `Future`/`CompletionHandler` and does not extend `SelectableChannel`. The **completion** and **readiness** models are different:

```text
Readiness:
  Selector.select() -> channel reports ready -> application attempts read/write

Completion:
  AsynchronousFileChannel.read(...) -> operation is initiated
                                     -> Future/CompletionHandler receives result
```

Do not confuse a file-operation completion callback with `SelectionKey.OP_READ`.

### Misconception 8: "Offloading file I/O to another thread never blocks at all"

That technique keeps the **calling thread / event loop** from waiting directly, yet the worker thread can still block. If file operations are unbounded, thread pools and queues can overload. Enforce resource bounds, backpressure, and error handling.

## 10. Correctly Interpreting File I/O and Reading Progress

Consider a process appending to a growing log file:

```text
time t0: file size=100 bytes
time t1: reader position=100, read() -> -1
time t2: writer appends 30 more bytes, size=130
time t3: reader can read bytes at offsets 100..129
```

Key takeaways:

- EOF at t1 is the result at **that moment in time**.
- Regular files have no `Selector.OP_READ` mechanism via `FileChannel` to wait for the 30 new bytes.
- You can poll `size` at a reasonable interval or use `WatchService` for directory change notifications, then verify and read the new slice.
- Designing a custom tailer must also handle truncation (size shrinking), rotation (file path pointing to a different inode/object depending on OS), duplicate events, encoding, and incomplete records.
- Distinguish nonblocking HTTP/socket response handling from append-style log file processing; the two resource types demand different waiting strategies.

Because `FileChannel` offers `read(dst, position)` and `position(long)`, maintaining exact offsets is its strength. Tracking **when** a new offset has data is the responsibility of the application or `WatchService`, not `Selector`.

## 11. Checking Knowledge About `SelectionKey`

A `SelectionKey` represents a registration of a **`SelectableChannel`** with a `Selector`. It has:

- `interestOps()`: set of operations the application wants notifications for.
- `readyOps()` and `isReadable()/isWritable()/isAcceptable()/isConnectable()`: operations reported ready in that selection pass.
- `channel()`: the registered selectable channel.

For a channel being registered:

1. Switch it to nonblocking mode before calling `register`.
2. Register only operations included in `channel.validOps()`. Registering an invalid bit may throw `IllegalArgumentException`.
3. After `selector.select(...)`, iterate over `selectedKeys()` and remove each handled key from the selected set (e.g., `it.remove()`); otherwise subsequent processing may revisit the same key.
4. Do not equate ready with I/O already completed; you still must call `read/write` and inspect the return value.
5. Closing the channel or canceling the key must be managed alongside application resources.

These rules **apply only to selectable channels**; `FileChannel` has no `SelectionKey` to inspect.

## 12. Notes on Testing and Performance

For a feature using `FileChannel`:

- Write tests reading/writing a temporary file by exact bytes and offsets; verify `size()`, `position()`, EOF, and partial transfers where relevant.
- Do not write tests expecting `FileChannel` to support `OP_READ`; confirming it is **not** selectable is a stable API-level property.
- Do not treat `read/write` counts or dev-machine speed as a guarantee across all filesystems.
- When testing asynchronous code, test success, errors, cancellation, timeouts, and ordering issues; do not rely on fixed completion speeds.
- Ensure temporary `Path` cleanup after closing all channels; especially on Windows, open files can block deletion.
- Stream large files in bounded chunks, avoiding loading everything into one `byte[]`; measure before optimizing.
- When write durability is needed, `FileChannel.force(metaData)` carries a contract to synchronize updates to the storage device within system capabilities, subject to device, provider, and filesystem limits. This is a file-channel feature, unrelated to selectors.

## 13. Self-Check Questions

1. Why does `FileChannel` have `read(ByteBuffer)` yet cannot call `register(selector, OP_READ)`?
2. Under what circumstances do `FileChannel` and `SocketChannel` share the `ReadableByteChannel` interface? Is that enough for both to be selectable?
3. When do you use `FileChannel.position(100)`, and when do you need a `SelectionKey.OP_READ`? What different questions do these two concepts answer?
4. With 10,000 TCP connections, what does choosing between `Selector` and 10,000 `FileChannel`s mean? Why is asking "optimize files with a selector" off-scope?
5. To get notified when a log file just changed, how can you use `WatchService`, and why must you still inspect the file after receiving an event?
6. What does `AsynchronousFileChannel.read(dst, offset)` return? Does calling `Future.get()` on an event loop retain "non-blocking" benefits?
7. If `transferTo` transfers only part of the requested bytes, what must the application do before concluding the file copy is complete?
8. What must `Pipe.SourceChannel` call before registering with a selector? Can that same method be applied to `FileChannel`?
9. If `FileChannel.read()` returns `-1` while the file writer continues appending, does that EOF stay valid forever?
10. What is the difference between **readiness** and **completion** in the NIO model?

## 14. Java SE 17 References

- [`FileChannel` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): file position, scattering/gathering I/O, transfer, map, lock, force.
- [`SelectableChannel` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SelectableChannel.html): `register`, `configureBlocking`, `validOps`.
- [`Selector` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/Selector.html): selecting readiness of selectable channels.
- [`AsynchronousFileChannel` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/AsynchronousFileChannel.html): file read/write with `Future` and `CompletionHandler`.
- [`WatchService` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): monitoring directory changes.

## 15. Takeaways

**`FileChannel` is a file-manipulation channel, not a `SelectableChannel`.** It supports `ByteBuffer`, file position, random access, transfers, and file-specific features, yet cannot call `configureBlocking(false)` or `register` with a `Selector`. **`Selector`** is used with genuinely selectable channels such as `SocketChannel`, `ServerSocketChannel`, and `Pipe.SourceChannel`.

If you need to process files without blocking a main thread, consider `AsynchronousFileChannel` or offloading `FileChannel` work to a worker thread. If you need notifications when a file is modified, `WatchService` or an appropriate monitoring mechanism is the right path. Choose the API based on resource type and signal semantics: **file offset/size**, **socket/pipe readiness**, **async operation completion**, or **directory change events**.

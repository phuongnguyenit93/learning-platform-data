# `flush()` Pushes Software Buffers but Does Not Mean Data Is Durable

## Lesson Objectives

In Java I/O, calling `flush()` at the right time helps forward data sitting inside **a write layer's buffer** down to the layer underneath. However, that **does not mean** the bytes have reached the physical disk, will survive a power loss, have been received and processed by the remote network peer, or that the entire write operation is atomic.

After this lesson, you will be able to:

- Distinguish **writing to a buffer**, **flush**, **close**, **readback visibility**, **synchronization/durability**, and **atomicity**.
- Explain the `flush()` behavior of `BufferedOutputStream`, `BufferedWriter`, `OutputStreamWriter`, `PrintWriter`, and wrapper classes.
- Know when to use `FileChannel.force(...)` or `FileDescriptor.sync()` to request syncing a file to the storage device.
- Design the order of operations when you must both flush Java buffers and request file synchronization, while understanding the limits of rename operations, network flushes, and distributed applications.
- Avoid calling `flush()` excessively or treating it as proof of durable data.

## 1. A `write()` Call May Only Have Written to Java Memory

Imagine an application wanting to write a line to a file:

```text
Java Application
    │ write("order=42\n")
    ▼
BufferedWriter / BufferedOutputStream       ← buffer managed by Java/library
    │ flush() — forwards pending data to the next layer
    ▼
OutputStreamWriter / FileOutputStream
    │ writes bytes to the operating system
    ▼
OS buffer / page cache                      ← may still reside in RAM
    │ appropriate sync operation (e.g., force / fsync)
    ▼
Filesystem, driver, storage device          ← own cache/journal mechanisms
    │
    ▼
Data confirmed by the storage system
```

This diagram simplifies the path of an ordinary file; other filesystems, devices, virtualized environments, or remote storage may involve additional layers. The key point is that **each layer has its own buffer and guarantees**. `flush()` on a Java class **does not automatically traverse all layers** and must not be equated with `fsync`.

For example: `BufferedOutputStream` receives three bytes and stores them in its internal byte array. Until the buffer is full or flushed, the underlying `OutputStream` may not have seen a single byte. When `flush()` is called, the three bytes are sent down to the underlying stream. If the underlying stream is `FileOutputStream`, the OS has received the write request but may keep the data only in the page cache. If the underlying stream is a socket, the bytes may sit in the OS send queue.

Not every output stream owns its own buffer. On the base `OutputStream`, `flush()` has a default implementation that **does nothing**; subclasses may override it. Therefore, the mere existence of the method on an API is not enough to conclude hardware synchronization occurs.

## 2. Five States You Must Distinguish

| State | What Can Be Claimed | What **Cannot** Yet Be Concluded |
|---|---|---|
| **`write(...)` into a buffered class** | The writer accepted the data under its API contract | Data has reached the underlying stream/file/socket |
| **`flush()` succeeded** | The called layer forwarded buffered data and asked lower layers to flush per that layer's contract | Data is definitely on durable disk or processed by the receiver |
| **`close()` succeeded** | The resource is closed; for many standard write wrappers, remaining buffered data is flushed during close | Disk is synced, transaction is atomic, or network peer has saved it |
| **Re-reading the file shows the data** | Data is currently observable via read APIs under current conditions | Data will survive a power loss / OS crash |
| **`force()`/`sync()` succeeded** | Sync to the device was requested per the API contract and underlying support | A multi-file transaction is atomic, every arbitrary device/transport satisfies all guarantees, or directories/renames are fully synced |

Distinguish **visibility** from **durability (surviving crashes)**. Another process may read the bytes from cache while the data is still not guaranteed to survive a crash.

Also distinguish **atomicity**. Atomicity is about whether an observer sees either the entire old state or the entire new state, never a half-written state; durability is about whether committed state survives a failure. `flush()`, `force()`, and `ATOMIC_MOVE` solve different problems and cannot substitute for one another.

## 3. How Does `flush()` Work Across Java Classes?

### 3.1. `OutputStream` and `BufferedOutputStream`

`OutputStream.flush()` is a method allowing subclasses to push pending bytes; its default implementation does nothing. `BufferedOutputStream` holds bytes in a buffer and, on flush, writes those bytes to the underlying stream and then calls `flush()` on that underlying stream.

Pay attention to order when composing layers:

```java
OutputStream raw = Files.newOutputStream(path);
BufferedOutputStream buffered = new BufferedOutputStream(raw);
```

This is an **illustrative snippet**, assuming `path` is a valid `Path` and `IOException` is handled. Use try-with-resources in real programs. `buffered.write(...)` may only modify the byte array inside `buffered`. `buffered.flush()` pushes bytes down to `raw`; **`raw.flush()` will not necessarily push data still sitting above it inside `buffered`**. Call flush on the outermost layer responsible for writing so it traverses the entire wrapper chain.

An underlying stream may itself have another buffer. `BufferedOutputStream` does not promise that the entire path onward to the storage device is persisted.

### 3.2. `Writer`, `BufferedWriter`, `OutputStreamWriter`

`Writer` is a character abstraction, whereas `OutputStream` writes bytes. `OutputStreamWriter` encodes characters into bytes according to the chosen charset and may hold internal bytes before sending them down to the stream. `BufferedWriter` adds a character buffer on top of that.

```text
BufferedWriter                (char buffer)
    ↓ flush()
OutputStreamWriter            (char → byte encoder, may have byte buffer)
    ↓ flush()
OutputStream                  (target layer; may be BufferedOutputStream)
    ↓
file / network / memory sink
```

Thus, flushing the **outermost write wrapper** is essential when data must pass through the full character/byte conversion chain. If you only flush the bottom `OutputStream` without flushing `BufferedWriter` above it, unpushed characters may remain trapped upstairs.

`BufferedWriter.newLine()` only writes the system line separator; it **does not flush automatically**. `writer.write("\n")` does not guarantee a flush either. When consumers must see data promptly, call `writer.flush()` at the right protocol points.

### 3.3. `PrintWriter` and Auto-Flush

`PrintWriter` offers an `autoFlush` option at construction, yet `autoFlush=true` **does not mean** every `print(...)`, `write(...)`, or every `'\n'` triggers a flush. For `PrintWriter`, auto-flush behavior is triggered by `println`, `printf`, and `format`, per the class contract. If a protocol requires pushing bytes after a `print` call, flush explicitly.

Another important difference: `PrintWriter` does not propagate `IOException` the way `BufferedWriter` does, instead storing an internal error state; you can check it via `checkError()` (which also flushes if the stream is open). Do not ignore write errors when data accuracy matters. `PrintStream` likewise has its own error-handling mechanism; do not assume successful print calls mean successful storage.

## 4. Java 17 Example: Observing `flush()` on a Software Buffer

The following program avoids the filesystem so it can measure accurately whether bytes are still in `BufferedOutputStream` or have reached the underlying destination.

Save **`BufferedFlushDemo.java`**:

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class BufferedFlushDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (BufferedOutputStream buffered =
                 new BufferedOutputStream(sink, 8)) {
            buffered.write("ABC".getBytes(StandardCharsets.UTF_8));
            System.out.println("before flush: " + sink.size());

            buffered.flush();
            System.out.println("after flush: " + sink.size());

            buffered.write('D');
            System.out.println("after another write: " + sink.size());
        }

        System.out.println("after close: " +
            sink.toString(StandardCharsets.UTF_8));
    }
}
```

Run:

```bash
javac BufferedFlushDemo.java
java BufferedFlushDemo
```

Output:

```text
before flush: 0
after flush: 3
after another write: 3
after close: ABCD
```

Step-by-step explanation:

1. `BufferedOutputStream` is given an 8-byte buffer; writing `ABC` (3 bytes) does not fill the buffer, so `sink` still has length 0.
2. `buffered.flush()` transfers `ABC` into `ByteArrayOutputStream`, making `sink.size() == 3`.
3. Writing `D` does not force an immediate push, because the buffer still has room; `sink` stays at 3 bytes.
4. On exiting try-with-resources, `BufferedOutputStream.close()` flushes the pending `D` byte and closes the wrapper. `ByteArrayOutputStream` still permits reading its in-memory contents.

**Scope of proof:** this example only confirms that `flush()` pushes bytes from a Java buffer to `ByteArrayOutputStream`; there is no file, kernel page cache, or disk here, so it cannot be used as a durability test.

## 5. Example: Character Buffers Also Need `flush()`

Save **`WriterFlushDemo.java`**:

```java
import java.io.BufferedWriter;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.StandardCharsets;

public class WriterFlushDemo {
    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (Writer writer = new BufferedWriter(
                new OutputStreamWriter(sink, StandardCharsets.UTF_8),
                64)) {
            writer.write("café");
            System.out.println("bytes before: " + sink.size());

            writer.flush();
            System.out.println("bytes after: " + sink.size());
            System.out.println("decoded: " +
                sink.toString(StandardCharsets.UTF_8));
        }
    }
}
```

Run:

```bash
javac WriterFlushDemo.java
java WriterFlushDemo
```

Output:

```text
bytes before: 0
bytes after: 5
decoded: café
```

`BufferedWriter` initially holds the four UTF-16 characters in its buffer, so `sink` sees nothing yet. After flushing, the string is encoded into **5 UTF-8 bytes** (three ASCII letters plus the two-byte `é`). Calling flush on the outermost `BufferedWriter` sends the characters through `OutputStreamWriter` down to `sink`.

This also illustrates that a `Writer` still involves a **charset**; `flush()` pushes pending data, but does not substitute for specifying the right charset.

## 6. File I/O: Already Flushed in Java May Still Sit in the Page Cache

Suppose an application writes a file on a standard filesystem. With `FileOutputStream` or `Files.newOutputStream`, once bytes are passed to the OS write call, the data may be stored in the **page cache** before reaching the physical device. A Java wrapper's `flush()` addresses the wrapper's buffer; it does not guarantee the OS has flushed all file data to the device.

Even if you close the stream and reopen the file to read back the right data, that result may still come from the live cache. **A successful readback checks visibility, not power-loss resilience.**

### 6.1. `FileChannel.force(boolean metaData)`

`java.nio.channels.FileChannel.force(metaData)` requests that updates to the file's content be written out to the storage device per the channel's contract. For a file on a **local storage device**, the Java API specifies that relevant updates are forced to the device; for non-local devices, guarantees may depend on the system/provider.

- `force(false)`: requests forcing changes to **file content**; may still force metadata depending on implementation.
- `force(true)`: requests forcing both **content** and associated **file metadata**.
- The operation may throw `IOException` if forcing fails.
- A successful `force` does not create an atomic transaction across multiple files, does not synchronize all related directories under a universal contract, and does not guarantee remote storage behaves like local storage.
- If data was modified through a mechanism **other than this channel**, do not assume `channel.force(...)` covers all of those changes. Using the same channel for writing and forcing expresses responsibility cleanly.

A common mistake is calling `force` **before** `BufferedOutputStream.flush()`. In that case bytes may still sit in a Java array without ever having passed through `FileChannel`; force cannot push to disk data that the channel has not yet received.

### 6.2. Java 17 Example: Flush the Wrapper First, Then Force the Channel

Save **`FlushAndForceDemo.java`**. The program creates a temporary file, writes through a buffer, flushes to `FileChannel`, requests a force, and reads the data back to verify bytes:

```java
import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FlushAndForceDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("io-flush-", ".txt");

        try {
            try (FileChannel channel =
                     FileChannel.open(file, StandardOpenOption.WRITE);
                 OutputStream buffered = new BufferedOutputStream(
                     Channels.newOutputStream(channel), 8192)) {

                buffered.write("DATA\n".getBytes(StandardCharsets.UTF_8));

                buffered.flush();  // 1. Push bytes remaining in the Java buffer
                channel.force(true); // 2. Request forcing content/metadata
            }

            System.out.print(
                Files.readString(file, StandardCharsets.UTF_8)
            );
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Run:

```bash
javac FlushAndForceDemo.java
java FlushAndForceDemo
```

Output in a normal I/O environment:

```text
DATA
```

Here `Channels.newOutputStream(channel)` adapts `FileChannel` to the `OutputStream` API, and `BufferedOutputStream` provides the buffering layer. Calling `buffered.flush()` **before** `channel.force(true)` ensures the bytes have been delivered to the channel. A successful `Files.readString` only verifies observable content; this example **cannot prove** post-crash/power-loss behavior, and is neither a benchmark nor a hardware test. The program deletes the temporary file for cleanup; in real persistence applications, deletion and directory synchronization must follow dedicated procedures.

An alternative in the `java.io` API is **`FileDescriptor.sync()`**, for example via `FileOutputStream.getFD().sync()`, after flushing any wrapper holding data. It asks the system to synchronize the descriptor's buffers with the storage device. Order still matters: if bytes have not reached the file descriptor, syncing underneath cannot synchronize bytes still sitting in a Java buffer.

### 6.3. Limitations of `force` and `sync`

`force`/`sync` is stronger than a wrapper flush, yet its exact scope must be understood:

- Files on a network filesystem may have different semantics, buffering, and guarantees than local files.
- Filesystem, kernel, device, controller caches, and hardware/virtualization must all cooperate to achieve real durability. Never claim a "100% guarantee" across arbitrary hardware combinations.
- Calling `force` on a file does not automatically guarantee **every filename or directory entry change** has been synced. File creation, renaming, and replacement involve directory metadata; directory synchronization is not exposed by Java NIO.2 as a portable interface across all operating systems.
- When modifying a memory-mapped region, `MappedByteBuffer` has its own `force()` mechanism; do not assume a wrapper flush or a random channel force substitutes for the mapping's own operation.
- A sequence of "write A, write B" can still be left half-done after a crash, even if each step calls force separately. **Durability does not automatically equal atomicity.**

When business requirements demand transactional commits, crash recovery, consistent multi-record writes, or strict commit ordering, use a properly designed log/transaction protocol or a database whose guarantees have been verified on the target infrastructure.

## 7. `close()` Differs from `flush()`

**`flush()`** pushes data sitting in write-layer buffers while **keeping the stream/writer open** for further writes. **`close()`** ends the lifecycle and releases resources; for `BufferedOutputStream`, `BufferedWriter`, and many other write wrappers, closing also flushes any pending data.

```java
try (var writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("first line");
    writer.newLine();
    writer.flush(); // Only needed if you want to push before exiting scope
    writer.write("second line");
}
// close is called automatically when leaving try-with-resources
```

This is an **illustrative snippet**, where `path` is a `Path`, `Files` and `StandardCharsets` are imported, and the method handles `IOException`. If you only need to close after writing, you normally **do not need to flush right before close** on standard buffered writers/streams. Conversely, if data must travel onward before leaving the scope, an explicit flush makes sense.

Notes:

- `close()` can throw `IOException` during flushing/closing; use try-with-resources so you do not forget to close and so Java handles suppressed exceptions properly.
- Whether closing a wrapper closes the underlying resource follows the **specific wrapper's contract**. Standard wrappers like `BufferedOutputStream` typically close the underlying stream too. Do not carelessly share the same underlying stream among multiple owners with close authority.
- You cannot continue writing to a closed `Writer`; `flush()` does not replace `close()` for releasing file descriptors.
- Completing `Files.writeString(...)` does not mean the file has been forced to disk.

## 8. Network: `flush()` Is Not an Application-Level ACK from the Receiver

Diagram for a buffered socket:

```text
Sending application
    ↓ buffered.write(message)
Java buffer
    ↓ buffered.flush()
SocketOutputStream / kernel send buffer
    ↓ TCP/network
Receiving machine's kernel
    ↓ remote application read()
Business processing, DB write, commit
    ↓ remote application sends business ACK
Sending application receives ACK and verifies
```

On the sender side, `buffered.flush()` can push bytes out of the Java buffer to be handed to the network stack. **It does not prove the peer has called `read()`, decoded the protocol properly, processed the request successfully, or durably committed the data.** Even a TCP ACK (if observed at the transport level) mainly confirms bytes reached the receiving TCP stack, not that the business operation succeeded.

If a client reports "payment succeeded" or "order saved," knowing the server actually processed it requires an **application-level response** carrying request identity, commit status, and idempotency/retry handling. Over TCP, `write()` and `read()` boundaries do not correspond one-to-one with messages; framing (length prefixes, delimiters with proper escaping, or a structured protocol) is required.

Some wrappers have buffers, while some socket streams hold no separate Java buffer. Therefore, `flush()` is not a universal "send urgently" command across every network; it depends on which layer holds the data. For interactive protocols, balance batching/flushing, message size, latency, backpressure, and socket options instead of flushing after every byte.

## 9. `flush()` Does Not Guarantee Atomic File Replacement

Consider updating a configuration file:

```text
Open old file and truncate
→ Write half of new content
→ Power loss / process killed
→ File may be empty, half-written, or inconsistent
```

Calling `flush()` after each chunk **does not prevent** a reader from seeing a half-written file or a crash occurring mid-update. A safer file-update workflow typically requires dedicated design steps:

1. Create a **temporary file in the same target directory/filesystem** and write the complete new content into it; avoid overwriting content currently served to readers in place.
2. Flush all relevant Java buffers and force the temporary file per durability requirements; handle `IOException`.
3. Once the temporary file is ready, use `Files.move(temp, target, StandardCopyOption.ATOMIC_MOVE, ...)` **when supported by the filesystem/provider**; this may throw `AtomicMoveNotSupportedException`. How replacing an existing target behaves during an atomic move is provider-specific; do not assume `REPLACE_EXISTING` always has identical semantics on every platform.
4. If crash durability of the filename/path is required, verify directory-entry synchronization and recovery behavior on the target OS/filesystem. Java does not provide a single portable workflow with universal guarantees across all filesystems.
5. Define a fallback policy when atomic rename is unsupported; never silently fall back to a non-atomic operation if atomicity is mandatory.

This is a **conceptual workflow**, not standalone code or a promise that every filesystem/device provides transactions. If multiple files must update their state together, a single file rename is still insufficient; consider a write-ahead journal, a versioned manifest with a commit marker, or a database.

## 10. Cost and When to Call `flush()`

Flushing too rarely can delay data in buffers; flushing too often loses batching benefits, increases system calls, or increases network round trips/packets. `force()`/sync is typically much more expensive because it requests deeper synchronization.

| Scenario | When to Flush | Is `sync`/`force` or Another Protocol Needed? |
|---|---|---|
| Write a small file and close | Usually the wrapper's close is enough to drain Java buffers | If crash survival is needed, consider file force and a commit protocol |
| Streaming large file writes | Flush at boundaries that truly need visibility, or let full buffers drain naturally | Depends on durability requirements; do not force every byte |
| CLI/REPL printing a prompt | Flush after prompt if there is no trailing newline or stdout is buffered | Unrelated to file durability |
| Client/server protocol exchanging immediate commands and responses | Flush at message boundaries after full encoding/framing | Needs application ACK to confirm peer processing |
| Writing audit/trading/payment logs | Flush Java buffers before marking a record processed | Usually needs a defined commit/durability mechanism; consider a DB or dedicated log |
| Writing directly to `ByteArrayOutputStream` | No external buffer, so flush usually adds no effect | No disk to sync |
| Wrapping `ByteArrayOutputStream` with `BufferedOutputStream` | Flush so the sink receives bytes still held in the wrapper | Unrelated to durability |
| Updating a config file that must never be half-written | Flush temp file and force as required | Needs atomic replace/recovery tailored to the filesystem |

Do not turn "call `flush()` at the end of every `write()`" into a mechanical rule. Identify **when others need to see the data** and **what counts as a durable commit**; those two requirements are distinct.

## 11. Frequently Asked Questions

### Does `flush()` write data from RAM down to the hard drive?

It pushes pending data from a specific buffer layer (such as `BufferedOutputStream` or `BufferedWriter`) down to the next layer. That next layer might be memory, a socket, a file stream, or another buffer. To ask the OS to synchronize a file to the storage device, use APIs like `FileChannel.force()` or `FileDescriptor.sync()` properly, within the guarantees of the filesystem.

### Does calling `flush()` followed by `Files.readString` reading the right text prove durability?

No. The data may simply be in the page cache so the read sees the new version; it can still be lost on power failure if not synced. A readback tests data logic **in the current live state**, not crash/power-loss resilience.

### If I already use try-with-resources, do I still need `flush()` before `close()`?

For standard `BufferedOutputStream` and `BufferedWriter`, usually no if the goal is simply pushing data at scope exit, because `close()` drains the buffer. You may need to flush **earlier**, while the stream stays open, if a consumer needs data immediately. Do not equate closing a stream with `fsync`.

### Does `FileChannel.force(true)` turn a file update into an atomic transaction?

No. It requests synchronizing file data and metadata per its contract; it does not automatically make a transition from old state to new state atomic, nor does it synchronize directories or sets of files. Atomicity requires its own mechanism.

### Is calling `flush()` underneath `BufferedWriter` enough?

Not necessarily. If characters are still sitting inside `BufferedWriter`, flushing an underlying `OutputStream` directly cannot push characters that `BufferedWriter` has not yet forwarded. Flush the outermost write layer that the application wrote into.

### Does `flush()` on a socket tell us the server successfully received the request?

No. It may push bytes to the socket/OS layer on the sender side; you need a protocol and an application response to confirm the server processed/committed it.

### Does `PrintWriter(autoFlush=true)` automatically flush on every `print()`?

No. On `PrintWriter`, auto-flush applies to `println`, `printf`, and `format` (not all `print`/`write` calls). If you need to push after `print`, call `flush()` explicitly; to detect errors, use `checkError()` or choose a Writer with explicit exceptions.

## 12. Self-Check

1. **A `BufferedOutputStream` holds 20 unflushed bytes. The app calls `FileChannel.force(true)` on the underlying channel. Are those 20 bytes guaranteed to be forced?**  
   **No.** While sitting in the Java buffer, they have not reached the channel. Flush the wrapper first, then force the channel.
2. **An application just flushed a file, reopened it, and read the content back. What has been verified?**  
   Visibility of the content in the current state; it does not prove the data would survive a crash.
3. **How does `close()` differ from `flush()`?**  
   Flush drains the buffer while keeping the stream usable; close ends the lifecycle and releases resources. For many standard buffered writers/streams, close also flushes the buffer.
4. **What is the difference between `FileChannel.force(false)` and `force(true)`?**  
   `false` requests forcing content; `true` requests forcing content and file metadata. Detailed behavior depends on the provider and underlying infrastructure.
5. **Right after `socketOutputStream.flush()`, can you report "payment succeeded"?**  
   No. You must wait for a business-level response confirming the server processed and committed it.
6. **Are `flush()` and `force()` enough when a file requires atomic updates?**  
   No. You need an atomic publication mechanism—such as a temp file and atomic move where supported—alongside environment-appropriate metadata sync/recovery design.

**Takeaway:** `flush()` addresses **software buffers in the write path**; `force()`/`sync()` addresses requesting **file synchronization to storage** at the level supported by the system; atomic rename/transactions address **atomicity**, and application ACKs confirm **receiver-side processing**. These four concerns must be designed and verified separately.
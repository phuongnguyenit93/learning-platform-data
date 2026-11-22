# Diagnosing Unflushed Data, Open File Handles, and Misconfigured Buffer State in Java I/O / NIO.2

An application may call `write()` while the file remains empty; a file may refuse to be deleted or renamed because a resource is still open; or `FileChannel` may write 0 bytes even though `ByteBuffer` holds data. These three symptoms are often lumped together as "I/O didn't finish writing," yet they stem from **three distinct state layers**:

1. **Unflushed output buffer**: data still sits inside `BufferedWriter`, `BufferedOutputStream`, or the character-encoding layer and has not been pushed down to the underlying I/O layer.
2. **Unclosed OS resource**: an `InputStream`, `OutputStream`, `Reader`, `Writer`, `FileChannel`, `DirectoryStream`, or file-backed `Stream` is still holding a resource; file descriptors/handles or file locks can accumulate.
3. **Incorrect `Buffer` `position`/`limit`**: data is in memory, yet NIO APIs see zero `remaining` bytes to read/write, or stale data gets written repeatedly or mixed with invalid bytes.

To fix these properly, first identify which layers the data has passed through, who owns the resource, and the buffer's state at the moment the API is called.

## 1. The Data Path: `write`, `flush`, `close`, and Disk Durability

A typical write path has several layers:

```text
Application data
   └─ BufferedWriter (character buffer)
        └─ OutputStreamWriter (encodes characters to bytes)
             └─ BufferedOutputStream (byte buffer, if present)
                  └─ FileOutputStream / FileChannel
                       └─ OS / filesystem cache
                            └─ storage device
```

Not every program includes all layers. For example, `Files.newBufferedWriter(path, UTF_8)` returns a buffered writer; `Files.writeString` is a convenience write API that leaves no writer for the caller to close manually.

| Action | Guaranteed Under Normal Contract | **Not** Guaranteed |
| --- | --- | --- |
| `writer.write(...)` | Feeds data into the writer's state; may still sit solely in memory | That the file immediately observes all data |
| `writer.flush()` | Requests pushing buffered data to the underlying destination and flushing chained writers/streams per contract | That bytes are durably persisted on physical storage |
| `writer.close()` | On standard writers like `BufferedWriter`, flushes before closing and releasing resources; may throw I/O errors | That a business transaction is complete or the file was strictly `fsync`'d |
| `FileChannel.force(true)` | Requests forcing content and metadata changes through the channel to the device per provider guarantees | Turning every filesystem, NFS/remote mount, or hardware cache into a durable transaction |
| `FileDescriptor.sync()` | Requests the OS to synchronize data associated with the descriptor | Replacing flushing of Java-layer buffers that haven't pushed bytes to the descriptor yet |

**Distinguish three questions:** "Was `write` called?" differs from "Was it `flush`ed to the OS?" and differs from "Was `force`/`sync` called to reduce crash data-loss risk?" If a writer still buffers characters in RAM, calling `force` on the underlying file channel without flushing the writer **cannot sync bytes that never reached the channel**.

For ordinary file handling, `try-with-resources` and checking close exceptions usually suffice to ensure Java-layer buffers drain and resources release. For high-durability requirements (transaction logs, checkpoints), add explicit sync contracts, temporary files, proper atomic renames, and filesystem support checks.

## 2. Signs of Unflushed Data

Familiar situations:

- Calling `write("hello")` on a `BufferedWriter`, then another process reads the file and does not see `"hello"` yet. The writer may still hold that string in its buffer.
- Using `PrintWriter.print(...)` and expecting data to appear immediately. `PrintWriter`'s `autoFlush=true` flag flushes automatically on `println`, `printf`, or `format`, **not** after every `print` or `write`.
- Multiple buffering layers exist, yet only one layer is flushed manually by the wrong owner. In a normal design, flushing the **outermost wrapper** pushes data through the layers beneath.
- The process terminates abnormally before closing the writer. `try-with-resources` handles normal Java control flow and exceptions, but does not run if the process is killed immediately or the JVM/OS crashes.
- Logging "saved" before the write/flush/close sequence finishes, when those steps can still throw an exception. Report success only after the entire write path returns normally.

Correct pattern:

```java
import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path file = Path.of("report.txt");
try (BufferedWriter writer =
         Files.newBufferedWriter(file, StandardCharsets.UTF_8)) {
    writer.write("hello");
    writer.newLine();
    writer.flush(); // Needed only if data must be visible before closing.
} // close will flush and close on the normal execution path.
```

The snippet above is **illustrative code inside a method**; class and `main` are omitted. If there is no need to observe the file before closing, calling `flush()` manually right before `close()` is usually unnecessary. However, if the output is an interactive protocol like a socket, flush at every response boundary instead of waiting for connection close.

**Never use `Thread.sleep(...)` as a flushing workaround.** Waiting does not guarantee `BufferedWriter` will drain its buffer on its own. Likewise, avoid calling `flush` after *every single byte* when writing large files, because frequent small syscalls degrade performance.

### `PrintWriter` Swallows I/O Errors

Unlike most writers, `PrintWriter` does not throw `IOException` directly from standard write methods; `checkError()` reports error status and flushes if the stream is still open. Therefore, calling `println` without an exception **does not prove** the file was written successfully. When explicit error reporting is needed, prefer `BufferedWriter` or exception-throwing APIs; if using `PrintWriter`, call `checkError()` at appropriate checkpoints.

## 3. Open File Handles: Who Is Responsible for Closing?

A "file handle" on Windows and a "file descriptor" on Unix-like systems are OS resources. A Java object keeping a stream or channel open can continue holding this resource, directly or through a wrapper. Common symptoms:

- `Too many open files` / `EMFILE` when opening resources without closing them, especially in long-running servers.
- On Windows, `AccessDeniedException`, move/delete failures, or another application failing to rename a file while a process holds a handle with an incompatible sharing mode. On Unix, unlinking an open file name usually succeeds; the underlying data/resource persists until the final handle closes. Exact behavior depends on the filesystem and OS permissions.
- File locks held longer than necessary, blocking other workers from acquiring locks or exclusive access.
- After a series of requests, descriptor counts climb over time; restarting temporarily "fixes" the symptom until the error recurs.

**Ownership principle:** whoever creates a stream or channel is normally responsible for closing it. Returning a stream from a method without specifying that the caller must close it is a classic leak source. If an API returns a lazy file-backed `Stream<String>`, wrap it in `try-with-resources` at the consumption site.

Example of reading a file and closing the source properly:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("events.log");
try (Stream<String> lines =
         Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines.filter(line -> line.contains("ERROR")).count();
    System.out.println(errors);
}
```

This is a **snippet inside a method declaring `throws IOException` or handling errors**, not a standalone Java program. `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` can hold filesystem resources open; always close the returned `Stream`. Terminal commands like `cat` or `grep` do not manage a Java stream's lifecycle.

For channels or file locks, close in proper scope:

```java
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (FileChannel channel = FileChannel.open(
         Path.of("state.bin"), StandardOpenOption.CREATE,
         StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    // Work requiring lock, performed within this try scope.
} // Lock is released, then channel is closed (reverse creation order).
```

This is an illustrative snippet. `FileLock` also depends on OS and filesystem semantics and support. Closing a wrapper can also close the underlying stream or channel; never continue using that resource after its owning wrapper has closed. Conversely, `ByteArrayOutputStream` is an in-RAM buffer and opens no file descriptors; do not conflate every `close()` with releasing OS file resources.

### How to Track Down Leaked File Descriptors

| Environment | Useful Inspection Tools | Notes |
| --- | --- | --- |
| Linux | `lsof -p <PID>`; `ls -l /proc/<PID>/fd` | `lsof` may require separate installation/privileges; `/proc` access may be restricted in containers |
| Windows | Resource Monitor → CPU → Associated Handles; Sysinternals Process Explorer/Handle | Search by file name or process; note handle sharing and access privileges |
| JVM on Unix | `com.sun.management.UnixOperatingSystemMXBean.getOpenFileDescriptorCount()` | Platform-specific extension API; reports **total count** only, not which file leaked |
| In-application | Open descriptor/handle count metrics; log paths, creation sites, close events; repeated stress tests | Never log full sensitive file names, user details, or file contents to public monitoring systems |

For leaks, observe **trends under load and again after the workload finishes**. Rising counts while many connections are active do not prove a leak; suspicion is warranted when counts keep climbing across identical load cycles without returning to baseline.

Never assume a JVM thread dump reveals every open file: thread dumps show stacks and threads, not a complete descriptor list. Likewise, GC or `System.gc()` is **not** a reliable handle-release mechanism; close explicitly.

## 4. `ByteBuffer`: `capacity`, `position`, `limit`, and `remaining`

`ByteBuffer` is a stateful buffer. Four key numbers:

- `capacity`: fixed capacity in bytes.
- `position`: index of the next element to read or write in relative operations.
- `limit`: *exclusive* boundary of the readable/writable region.
- `remaining() = limit - position`: number of bytes relative operations can still process.

The invariant is `0 <= position <= limit <= capacity`.

Example `ByteBuffer.allocate(8)` after writing bytes `A B C` with `put`:

```text
Index:       0  1  2  3  4  5  6  7
Bytes:       A  B  C  ?  ?  ?  ?  ?
State:       position=3, limit=8, capacity=8
```

`?` marks bytes outside the example's valid data. After `flip()`:

```text
Index:       0  1  2  3  4  5  6  7
Bytes:       A  B  C  ?  ?  ?  ?  ?
State:       position=0, limit=3, capacity=8
Remaining:   A  B  C
```

Calling `FileChannel.write(buffer)` **before `flip`** makes the channel read from `position=3` to `limit=8`—not the 3 bytes just inserted. In another case, if `position == limit`, `write` returns `0` because `!hasRemaining()`, even though the backing array still holds old data.

### Four State Transitions to Remember

| API | State Change | When to Use | Common Misconceptions |
| --- | --- | --- | --- |
| `flip()` | `limit = position; position = 0` | Finish **writing data into the buffer**, prepare to read from it | Forgetting to call before channel write; or calling twice, setting `limit` to 0 |
| `clear()` | `position = 0; limit = capacity` | Prepare to overwrite buffer once old data is fully processed | **Does not zero physical bytes**; loses track of unread pending data |
| `rewind()` | `position = 0`, keeps `limit` | Re-read the same valid byte range | Confusing with `clear` and reading invalid bytes |
| `compact()` | Moves `remaining` bytes to the front; sets `position` after them; `limit = capacity` | Consumed **part** of the buffer, keeping unprocessed bytes to receive more | Confusing with `clear` and losing unused bytes |

`mark`/`reset` is also part of buffer state; `flip`/`clear`/`rewind`/`compact` discard the mark per `Buffer`'s contract. When debugging, printing `position`, `limit`, `capacity`, and `remaining()` before and after each channel read/write is far faster than printing the buffer object itself.

**`buffer.array()` is not synonymous with "valid data in the buffer."** On heap buffers, it can contain already-consumed bytes, empty slots, or bytes outside `[position, limit)`; on direct or read-only buffers, the backing array may be inaccessible. To read exact remaining bytes, use `byte[] result = new byte[buffer.remaining()]; buffer.get(result);` or use `slice()` as needed.

## 5. Java 17+ Example with Deterministic Stdout

This example uses a text file with `BufferedWriter` and a binary file with `ByteBuffer`/`FileChannel`. Files are created inside a temporary directory so nothing depends on external file names, and no concurrent task modifies them.

Create `IoDiagnosticsDemo.java`:

```java
import java.io.BufferedWriter;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class IoDiagnosticsDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("io-diagnostics-");
        Path text = dir.resolve("notes.txt");

        // 1) Flush buffer, read back while writer is still open.
        try (BufferedWriter writer =
                Files.newBufferedWriter(text, StandardCharsets.UTF_8)) {
            writer.write("hello");
            writer.flush();
            System.out.println("after flush="
                    + Files.readString(text, StandardCharsets.UTF_8));
        }
        System.out.println("after close="
                + Files.readString(text, StandardCharsets.UTF_8));

        // 2) Switch ByteBuffer from put mode to channel.write.
        Path binary = dir.resolve("data.bin");
        try (FileChannel out = FileChannel.open(binary,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            ByteBuffer buffer = ByteBuffer.allocate(8);
            buffer.put("ABC".getBytes(StandardCharsets.UTF_8));

            System.out.printf("before flip: pos=%d limit=%d%n",
                    buffer.position(), buffer.limit());
            buffer.flip();
            System.out.printf("after flip: pos=%d limit=%d%n",
                    buffer.position(), buffer.limit());

            while (buffer.hasRemaining()) {
                out.write(buffer);
            }
        }
        System.out.println("saved="
                + Files.readString(binary, StandardCharsets.UTF_8));

        // 3) Reverse direction: channel.read then flip before get.
        try (FileChannel in = FileChannel.open(binary,
                StandardOpenOption.READ)) {
            ByteBuffer buffer = ByteBuffer.allocate(8);
            int count = in.read(buffer);
            System.out.printf("after read: n=%d pos=%d limit=%d%n",
                    count, buffer.position(), buffer.limit());

            buffer.flip();
            byte[] result = new byte[buffer.remaining()];
            buffer.get(result);
            System.out.println("decoded="
                    + new String(result, StandardCharsets.UTF_8));
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 IoDiagnosticsDemo.java
java IoDiagnosticsDemo
```

Stdout on JDK 17+ on an ordinary filesystem with no interference from other tasks:

```text
after flush=hello
after close=hello
before flip: pos=3 limit=8
after flip: pos=0 limit=3
saved=ABC
after read: n=3 pos=3 limit=8
decoded=ABC
```

Each `try-with-resources` manages its own resource while surfacing any `close` failure as an exception. The `flush()` call in the example allows inspecting `notes.txt` **before the writer closes**; it does not mean every program needs to flush twice.

`data.bin` contains exactly the three bytes `ABC` because `flip` bounds the write range to `[0,3)`; the `while (buffer.hasRemaining())` loop handles the possibility that a channel writes fewer than `remaining` bytes in a single call. On non-blocking channels, if `write` repeatedly returns `0`, use `Selector` or a proper wait strategy rather than spinning infinitely; this example uses a standard blocking `FileChannel`.

## 6. Debugging Checklist When a File Is Empty, Missing Bytes, or Delayed

When encountering a "written yet still empty" file, check in this order:

1. **Right file and right path?** Print/log the normalized path and actual runtime context (working directory, file path, mount/container). Mixing up relative paths is a very common cause. Never include sensitive paths in public logs.
2. **Which open options were used?** `TRUNCATE_EXISTING` erases prior content; `APPEND` writes at the end; `CREATE_NEW` refuses to overwrite existing files. If another thread opens the file with truncate, the file can appear empty even after an earlier writer succeeded.
3. **Is there a buffering wrapper?** `BufferedWriter`, `BufferedOutputStream`, and `OutputStreamWriter` can retain data; flush/close the owning outer layer. Read back only *after flushing* to verify visibility—never draw conclusions from file size before buffers are flushed.
4. **Was an exception swallowed?** Check for `IOException` on write, flush, and close; with `PrintWriter`, check `checkError()`.
5. **Does `ByteBuffer` still have `remaining`?** Log `position`/`limit`/`capacity` and `n = channel.write(buffer)` updates after each call. Compare returned byte counts against intended byte counts.
6. **Were `force`/`sync` called if durability is required?** Only evaluate after Java buffers have flushed; remember `force` and `flush` operate at different layers.
7. **Who else is writing to the file?** Synchronize workers and prevent concurrent writers from modifying the file between inspection and re-reading. Never claim "flush failed" when the real cause is a race or reading a different file.

Instead of printing `System.out.println("saved")` right after placing data into a buffer, observe distinct milestones such as `write completed`, `flush completed`, `close completed`, and `file published` as needed. Never log every byte on production hot paths; use metrics or targeted trace points when reproducing bugs.

## 7. Debugging Checklist When Open File Handles Keep Increasing

A leak scenario:

```java
// Wrong: every call opens a Stream from the filesystem without closing it.
long countErrors(Path file) throws java.io.IOException {
    return java.nio.file.Files.lines(file)
            .filter(s -> s.contains("ERROR"))
            .count();
}
```

Because `Files.lines` returns a lazy `Stream`, finishing `count()` **does not automatically call `close()` on the stream**. Fix:

```java
long countErrors(Path file) throws java.io.IOException {
    try (java.util.stream.Stream<String> lines =
            java.nio.file.Files.lines(file)) {
        return lines.filter(s -> s.contains("ERROR")).count();
    }
}
```

These are two **standalone illustrative methods** for inside a class; they will not compile in the same file with identical signatures. Keep only the fixed version in real projects.

How to reproduce and leak-test:

1. Measure open descriptors/handles before running a representative workload cycle.
2. Repeatedly exercise **success, exception, cancellation, and timeout** branches. Error paths are the ones most often skipping manual `close()` calls at the end of a method.
3. After the workload stops, compare against baseline, list open handles/paths using OS tools, and trace them back to stream/channel/reader/writer creation sites.
4. Convert to `try-with-resources`; for multiple resources, declare them in proper ownership order. Ensure all `return` and `throw` paths close owned resources.
5. Re-run the same workload; confirm descriptor counts stay bounded and required move/delete/lock operations succeed normally.

If a resource is handed to a caller or an async job, transfer ownership explicitly and guarantee closure **after** the task finishes. Closing a channel too early while a worker is still doing I/O causes `ClosedChannelException` or `AsynchronousCloseException`; closing too late leaks handles. Canceling a `Future` does not prove I/O has stopped immediately.

## 8. Common `ByteBuffer` Bugs and How to Test Them

### Forgetting `flip` Before Writing to a Channel

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {65, 66, 67});
// Wrong: not flipped; remaining is 5, not the 3 bytes "ABC".
channel.write(buffer);
```

This illustrative snippet sits inside a method with `WritableByteChannel channel`. Fix by calling `buffer.flip()` before reading from the buffer. When using `ByteBuffer.wrap(byte[])`, `position` starts at `0` and `limit` equals the array length, so **do not call `flip` unconditionally** right after `wrap` if no `put` occurred; doing so sets `limit` to `0`.

### Forgetting `flip` After `channel.read`

```java
ByteBuffer dst = ByteBuffer.allocate(1024);
int n = channel.read(dst);
if (n > 0) {
    dst.flip();
    // Process the exact dst.remaining() bytes, not capacity.
}
```

If you forget `flip`, `get` calls read unfilled regions or miss the newly received data depending on `position`/`limit`. At end-of-stream, `read()` typically returns `-1`; on non-blocking channels, `0` can mean no data is currently available, **not** EOF.

### Calling `clear` While an Incomplete Frame Remains

In a protocol parser, one `read` may deliver only half a message. After `flip` and consuming complete frames, call `compact()` to move bytes of the incomplete frame to the front of the buffer before reading more:

```java
// Illustrative code inside a protocol processing loop, not a standalone main.
buffer.flip();
consumeCompleteFrames(buffer); // Advances position past processed bytes.
buffer.compact();              // Keeps remaining bytes for the next read.
```

Calling `clear()` here marks the remaining data as nonexistent even though physical bytes still sit in the array. Calling `rewind()` after consuming half the buffer causes the already-processed prefix to be consumed again.

### Sharing a Buffer Across Multiple Threads

`ByteBuffer` is not thread-safe for concurrent mutations of `position`/`limit` on one instance. If multiple workers invoke relative `get`/`put` on the same buffer, bytes can be lost or reordered even if `FileChannel` itself supports concurrent positional access. Use per-task buffers, or synchronize and slice explicitly; never share a mutable `ByteBuffer` without clear ownership.

### Partial Writes and Post-Write State

`FileChannel.write(buffer)` returns the number of bytes actually written. Only close or publish a file once the buffer has no remaining bytes or errors are handled properly. `write` does not automatically `clear` or `flip` the buffer; it advances `position` by the bytes transferred. When writing with multiple buffers, inspect actual bytes written and file position rather than assuming `buffer.array().length` was written.

## 9. Automated Testing and Diagnostics

Write dedicated tests for each of the three failure classes so you immediately know where a defect lives.

| Test Scenario | Evidence Required | Defect Caught |
| --- | --- | --- |
| Write characters to `BufferedWriter`, call `flush`, read immediately while writer stays open | Read-back content matches | Missing `flush` where visibility is required |
| Exit `try-with-resources` and read back | Complete data; close exceptions handled | Missing `close` / swallowed end-of-write errors |
| Repeat operations on `Files.lines`, `Files.walk`, `FileChannel` | Descriptor count stays bounded after workload | Resource leak |
| Trigger exceptions, cancellations, early returns | Resources still close; no stray file locks remain | Closing only on the happy path |
| `ByteBuffer.put` → `flip` → channel write | Bytes written equal valid byte count | Wrong `position`/`limit` |
| Read file using a buffer smaller than the file | Loops to EOF without losing bytes | Assuming a single `read` fetches everything |
| Parser receives half a frame in one read | `compact` retains unconsumed bytes | Dropping frames at buffer boundaries |
| Output requiring crash durability | Sequence `flush` → `force`/`sync` → commit defined and tested per filesystem | Confusing visibility with durability |

**Never rely on "file size is still 0 right after an unflushed write" as a strict guarantee**: depending on data size, buffer size, and implementation, a writer may auto-flush when full. Tests should assert results after explicit `flush`/`close`, not demand pre-flush invisibility.

For parser unit tests, `ByteBuffer.allocate(4)` forces frames to split across multiple reads. For resource integration tests, use temporary files and measure descriptors where supported; avoid relying solely on file deletion succeeding on Unix because open files can still be unlinked.

## 10. Distinguishing the Three Symptoms in Practice

| Symptom | First Possibility to Check | Resolution |
| --- | --- | --- |
| File empty while writer open, valid after close | Buffered output not flushed | Flush at boundaries requiring visibility |
| File valid after flush yet lost on power/OS crash | Missing durability steps or filesystem/storage limits | Check `FileChannel.force`/`FileDescriptor.sync` and durable save protocols |
| `Too many open files` | Unclosed streams/channels; unclear worker ownership | `try-with-resources`, check error paths, monitor descriptors |
| Cannot rename/delete file on Windows | Open handle/lock or OS sharing permissions | Identify process holding handle; ensure proper close/unlock |
| NIO `write` transfers 0 bytes | `!buffer.hasRemaining()` or non-blocking output not writable | Print `position`/`limit`, check channel and readiness |
| File contains garbage bytes or wrong length | Missing `flip`, using full `array()`, or unhandled partial write | Manage buffer state and write loop properly |
| Parser drops data at block end | Using `clear` instead of `compact`, or treating chunks as whole frames | Retain pending bytes; test split inputs |
| Works once, fails under load | Uncoordinated concurrent read/write, shared mutable buffer, premature close | Per-task buffers, locking/ordering, clear ownership |

## 11. Checklist for Reviewing I/O Code

1. Locate every resource acquisition: `Files.newBufferedWriter`, `Files.newInputStream`, `FileChannel.open`, `Files.lines`/`list`/`walk`/`find`, `ZipFile`, `RandomAccessFile`. Identify who closes each along every path.
2. For buffered outputs, define **when external observers may see the data**. If before close, place intentional `flush` calls; if durability is needed, add `force`/`sync` after data reaches the file layer.
3. Never report success before writing and closing/committing complete; capture errors from `write`, `flush`, and `close`. With `PrintWriter`, call `checkError()` or switch to exception-throwing APIs.
4. With NIO, make buffer state clear before/after `put`/`read`/`flip`/`write`/`clear`/`compact`. Use `remaining` for valid bytes and loop on partial channel reads/writes.
5. Add tests for repeated loops and error branches to catch handle leaks; test on the target deployment platform, especially if behavior depends on Windows file sharing, remote filesystems, or cloud storage.
6. Keep resource scopes minimal: never hold channels or streams across unrelated network calls or async tasks unnecessarily. For async workers, never close sources while work still needs them.

Key rule to remember: **`flush` drains Java-layer buffers; `close` ends resource ownership; `ByteBuffer.flip`/`clear`/`compact` manage read/write cursor state; `force`/`sync` address storage synchronization.** None of them substitutes for another.

### Official Reference Documentation

- Java SE 17 `BufferedWriter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html
- Java SE 17 `Writer` and `OutputStream` (`flush`/`close`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html
- Java SE 17 `ByteBuffer` / `Buffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `FileChannel` (`write`/`force`/`close`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 `Files` (resource management): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
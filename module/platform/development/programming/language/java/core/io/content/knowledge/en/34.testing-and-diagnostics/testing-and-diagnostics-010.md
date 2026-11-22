# Diagnosing Unflushed Data, Open File Handles, and Misconfigured Buffers in Java I/O / NIO.2

An application may call `write()` while the file remains empty; fail to delete or rename a file because a resource is still open; or have `FileChannel` write 0 bytes even though `ByteBuffer` holds data. These three symptoms are often lumped together as "I/O hasn't finished writing yet", yet they stem from **three different state layers**:

1. **Unflushed output buffers**: data is still sitting inside `BufferedWriter`, `BufferedOutputStream`, or the character-encoding layer, not yet pushed down to the underlying I/O layer.
2. **Unclosed OS resources**: an `InputStream`, `OutputStream`, `Reader`, `Writer`, `FileChannel`, `DirectoryStream`, or file-backed `Stream` is still holding a resource; file descriptors/handles or file locks can accumulate.
3. **`Buffer` with wrong `position`/`limit`**: data sits in memory, yet the NIO API sees zero "remaining" bytes to read/write, or stale data gets written repeatedly or mixed with invalid bytes.

To fix the issue properly, determine which layers the data has passed through, who owns the resource, and what state the buffer holds at the API call site.

## 1. Data Transfer Chain: `write`, `flush`, `close`, and Disk Durability

A typical write path has several layers:

```text
Application data
   └─ BufferedWriter (character buffer)
        └─ OutputStreamWriter (encodes chars to bytes)
             └─ BufferedOutputStream (byte buffer, if present)
                  └─ FileOutputStream / FileChannel
                       └─ OS / filesystem page cache
                            └─ storage device
```

Not every program uses all layers. For example, `Files.newBufferedWriter(path, UTF_8)` returns a buffered writer; `Files.writeString` is a convenience write API that leaves no writer for the caller to close.

| Action | Guaranteed Under Standard Contract | **Not** Guaranteed |
| --- | --- | --- |
| `writer.write(...)` | Places data into writer state; may still sit solely in a buffer | File immediately reflects all data |
| `writer.flush()` | Pushes buffered data to the underlying destination and flushes nested writers/streams per contract | Bytes are durably persisted on physical storage |
| `writer.close()` | On standard writers like `BufferedWriter`, flushes before closing and releasing resources; may throw I/O errors | Business transaction completion or absolute `fsync` |
| `FileChannel.force(true)` | Requests forcing content and metadata changes through the channel to the device per provider guarantees | Turning every filesystem, NFS/remote mount, or hardware cache into durable transactions |
| `FileDescriptor.sync()` | Requests OS synchronization of data associated with the descriptor | Replacing flushing of Java-layer buffers that haven't pushed bytes to the descriptor |

**Distinguish three questions:** "Did `write` run?" differs from "Was it `flush`ed to the OS?" and from "Was `force`/`sync` called to reduce crash data-loss risk?". If a writer still buffers characters in RAM, calling `force` on the underlying file channel without flushing the writer **cannot sync bytes that never reached the channel**.

For everyday file handling, `try-with-resources` and checking `close` exceptions suffice to drain Java buffers and release resources. For high-durability requirements (transaction logs, checkpoints), add explicit sync contracts, temp files, safe atomic renames, and filesystem support verification.

## 2. Signs of Unflushed Data

Familiar scenarios:

- Calling `write("hello")` on `BufferedWriter`, after which another process reads the file and does not see `"hello"` yet. The writer may still hold the string in its buffer.
- Calling `PrintWriter.print(...)` and expecting output immediately. `PrintWriter`'s `autoFlush=true` flag flushes automatically on `println`, `printf`, or `format`, **not** after every `print`/`write`.
- Multiple buffering layers where only an inner layer is flushed manually by a non-owner. In standard designs, flushing the **outermost wrapper** pushes data through the underlying layers.
- The process terminates abnormally before closing the writer. `try-with-resources` handles normal Java control flow and exceptions, but does not run on immediate process kill or OS-level JVM crashes.
- Logging "saved" before the write/flush/close path actually finishes, when those steps can still throw exceptions. Publish success only after the entire write path returns normally.

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
} // close flushes and closes on the normal execution path.
```

This is **illustrative code inside a method**; class and `main` are omitted. If nothing needs to observe the file before closing, calling `flush()` right before `close()` is usually unnecessary. On interactive protocols such as sockets, however, flush whenever a response must be sent rather than waiting for connection close.

**Never use `Thread.sleep(...)` as a flush workaround.** Waiting does not make `BufferedWriter` drain its buffer. Conversely, avoid calling `flush` after *every single byte* on large files, as excessive small syscalls degrade performance.

### `PrintWriter` hides I/O errors

Unlike most writers, `PrintWriter` does not throw `IOException` directly from common write methods; `checkError()` reports error status and flushes if the stream is still open. Thus calling `println` without an exception **does not prove** the file write succeeded. When explicit error reporting is needed, prefer `BufferedWriter` or APIs with transparent exceptions; if using `PrintWriter`, check errors at an appropriate boundary.

## 3. Open File Handles: Who Owns Closing Them?

A "file handle" on Windows and a "file descriptor" on Unix-like systems are OS resources. Any Java object holding an open stream or channel keeps this resource alive, directly or through a wrapper. Common symptoms:

- `Too many open files` / `EMFILE` when opening resources repeatedly without closing, especially in long-running servers.
- On Windows, `AccessDeniedException`, move/delete failures, or external apps unable to rename a file while a process holds a handle with incompatible share modes. On Unix, unlinking an open filename generally succeeds, while data/resources persist until the last handle closes. Exact behavior depends on filesystem and OS permissions.
- File locks held longer than needed, blocking other workers or exclusive operations.
- Descriptor counts creeping upward over requests; restarting temporarily "cures" the symptom before the failure returns.

**Ownership principle:** whoever creates a stream/channel normally owns closing it. Returning a stream from a method without documenting that the caller must close it invites leaks. When an API returns a lazy file-reading `Stream<String>`, wrap it in `try-with-resources` at the consumption site.

Example reading a file and closing the source automatically:

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

This is a **snippet inside a method that `throws IOException` or handles errors**, not a standalone Java program. `Files.lines`, `Files.list`, `Files.walk`, and `Files.find` can hold filesystem handles open; always close the returned `Stream`. Terminal commands like `cat` or `grep` do not manage Java stream lifecycles.

For channels or file locks, close in proper order:

```java
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

try (FileChannel channel = FileChannel.open(
         Path.of("state.bin"), StandardOpenOption.CREATE,
         StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {
    // Work requiring the lock executes inside this try block.
} // Lock releases, then channel closes (reverse creation order).
```

This is an illustrative snippet. `FileLock` also depends on OS and filesystem support/semantics. Closing a wrapper can close the underlying stream/channel; never keep using that resource after its owning wrapper has closed. Conversely, `ByteArrayOutputStream` is an in-memory buffer with no file descriptor; do not equate every `close()` with releasing an OS file.

### How to hunt down leaked file descriptors

| Environment | Useful Observation Tools | Notes |
| --- | --- | --- |
| Linux | `lsof -p <PID>`; `ls -l /proc/<PID>/fd` | `lsof` may require separate install/permissions; `/proc` may be restricted in containers |
| Windows | Resource Monitor → CPU → Associated Handles; Sysinternals Process Explorer/Handle | Search by filename/process; watch share modes and access rights |
| JVM on Unix | `com.sun.management.UnixOperatingSystemMXBean.getOpenFileDescriptorCount()` | Platform-specific extension API; gives **total count** only, not which file leaked |
| In-application | Descriptor/handle metrics; log creation site, path, close events; repeated stress tests | Never log sensitive filenames, user info, or file contents to public monitoring |

For leaks, observe **trends under load and after workload completion**. Rising counts during active connections are not necessarily a leak; suspect a leak when counts keep climbing across identical load cycles without returning to baseline.

Never assume a JVM thread dump shows every open file: thread dumps show stacks/threads, not full descriptor tables. Nor are GC or `System.gc()` reliable handle-release mechanisms; always close explicitly.

## 4. `ByteBuffer`: `capacity`, `position`, `limit`, and `remaining`

`ByteBuffer` is a stateful buffer. Four key numbers:

- `capacity`: fixed capacity in bytes.
- `position`: index of the next element to read or write via relative operations.
- `limit`: *exclusive* boundary of the region currently readable/writable.
- `remaining() = limit - position`: bytes left for relative methods to process.

The invariant is `0 <= position <= limit <= capacity`.

Example `ByteBuffer.allocate(8)` after putting bytes `A B C` with `put`:

```text
Index:       0  1  2  3  4  5  6  7
Bytes:       A  B  C  ?  ?  ?  ?  ?
State:       position=3, limit=8, capacity=8
```

The `?` marks bytes outside valid example data. After `flip()`:

```text
Index:       0  1  2  3  4  5  6  7
Bytes:       A  B  C  ?  ?  ?  ?  ?
State:       position=0, limit=3, capacity=8
Remaining:   A  B  C
```

Calling `FileChannel.write(buffer)` **before `flip`** makes the channel read from `position=3` to `limit=8`—not the 3 bytes just inserted. In another case, if `position == limit`, `write` returns 0 because `!hasRemaining()`, even though the backing array still holds old data.

### Four essential state transitions

| API | State Change | When to Use | Common Misuse |
| --- | --- | --- | --- |
| `flip()` | `limit = position; position = 0` | Finished **writing into buffer**, preparing to read from buffer | Omitting before channel write; or calling twice, setting limit to 0 |
| `clear()` | `position = 0; limit = capacity` | Preparing to overwrite buffer once old data is fully consumed | **Does not erase physical bytes**; loses track of unread bytes |
| `rewind()` | `position = 0`, keeps `limit` | Re-reading the same valid byte region | Confusing with `clear` and reading invalid bytes |
| `compact()` | Copies `remaining` bytes to start; sets `position` after them; `limit = capacity` | Consumed **part** of buffer, keeping unread bytes to receive more | Confusing with `clear` and losing unused data |

`mark`/`reset` are also buffer state; `flip`/`clear`/`rewind`/`compact` discard marks per `Buffer` contract. When debugging, printing `position`, `limit`, `capacity`, and `remaining()` before and after each channel read/write reveals issues faster than printing the buffer object reference.

**`buffer.array()` is not synonymous with "valid data in the buffer".** On heap buffers, it includes already-consumed bytes, empty slots, or bytes outside `[position, limit)`; on direct/read-only buffers, the backing array may be inaccessible. To extract exact remaining bytes, use `byte[] result = new byte[buffer.remaining()]; buffer.get(result);` or use `slice()`.

## 5. Java 17+ Example With Deterministic Stdout

This example uses a text file with `BufferedWriter` and a binary file with `ByteBuffer`/`FileChannel`. Files are created in a temporary directory to avoid external filename dependencies, with no concurrent modifiers.

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

Stdout on JDK 17+ on a standard filesystem with no interfering tasks:

```text
after flush=hello
after close=hello
before flip: pos=3 limit=8
after flip: pos=0 limit=3
saved=ABC
after read: n=3 pos=3 limit=8
decoded=ABC
```

Each `try-with-resources` manages its specific resource and surfaces close exceptions if any occur. The `flush()` in the example allows inspecting `notes.txt` **before the writer closes**; it does not mean every program must flush twice.

File `data.bin` holds exactly the three bytes `ABC` because `flip` bounds the write region to `[0, 3)`; the `while (buffer.hasRemaining())` loop handles the possibility of a channel writing fewer bytes than remain in a single call. On non-blocking channels, if `write` repeatedly returns 0, use `Selector` or an appropriate wait strategy instead of spinning; this example uses `FileChannel` opened for standard file writes.

## 6. Debugging Workflow When a File Is Empty, Short, or Updates Late

When facing a file that "was written yet has no data", check in order:

1. **Right file and right path?** Print/log the normalized path and actual runtime location (working directory, file path, mount/container). Confusing relative paths is very common. Never expose sensitive paths in public logs.
2. **Which open options were used?** `TRUNCATE_EXISTING` wipes existing content; `APPEND` appends at the end; `CREATE_NEW` refuses to overwrite existing files. If another thread opens with truncate, a reader can see an empty file even after an earlier writer succeeded.
3. **Is there a buffering wrapper?** `BufferedWriter`, `BufferedOutputStream`, or `OutputStreamWriter` may still hold bytes; flush/close the owning layer. Only verify visibility *after flushing*, rather than concluding from file size while buffers are unflushed.
4. **Were exceptions swallowed?** Check `IOException` on write, flush, and close; with `PrintWriter`, check `checkError()`.
5. **Does `ByteBuffer` still have `remaining`?** Log `position`/`limit`/`capacity`, `n = channel.write(buffer)`, and updates after each call. Distinguish the returned byte count from intended bytes.
6. **Is `force`/`sync` needed for durability?** Consider only after Java buffers are flushed; remember `force` and `flush` solve different layers.
7. **Who else writes to the file?** Coordinate workers so nothing mutates data between check and re-read. Avoid blaming "flush failed" when the real cause is a race or reading a different file.

Instead of printing `System.out.println("saved")` right after pushing bytes into a buffer, observe milestones like `write completed`, `flush completed`, `close completed`, and `file published` as needed. Do not log every byte on production hot paths; use metrics/targeted traces during reproduction.

## 7. Debugging Workflow When File Handles Climb Continuously

A leak scenario:

```java
// Bug: every call opens a filesystem Stream without closing it.
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

These are two **standalone illustrative methods** inside a class; they won't compile together in one file with identical signatures. In a real project, keep only the fixed version.

How to reproduce/leak-test:

1. Measure descriptor/handle count before running a workload covering representative requests.
2. Loop over **success, exception, cancellation, and timeout** paths. Error paths are exactly where manual end-of-method `close()` calls get skipped.
3. After the workload stops, compare against baseline, inspect open handles/paths with OS tools, and trace back to stream/channel/reader/writer creation sites.
4. Refactor to `try-with-resources`; for multiple resources, declare them in ownership order. Verify `return` and `throw` paths close everything properly.
5. Re-run the same workload; confirm descriptor counts stay bounded and required move/delete/lock operations succeed normally.

If ownership transfers to a caller or async job, transfer it explicitly and ensure `close` runs **after** the task finishes. Closing a channel too early while workers still perform I/O triggers `ClosedChannelException` or `AsynchronousCloseException`; closing too late leaks handles. Cancelling a `Future` does not guarantee I/O stopped immediately.

## 8. Common `ByteBuffer` Bugs and Tests

### Forgetting `flip` before writing to a channel

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
buffer.put(new byte[] {65, 66, 67});
// Bug: not flipped; remaining is 5, not the 3 bytes "ABC".
channel.write(buffer);
```

This snippet sits in a method with a `WritableByteChannel channel`. Fix by calling `buffer.flip()` before reading data out of the buffer. When using `ByteBuffer.wrap(byte[])`, initial `position` is 0 and `limit` equals array length, so **do not blindly call `flip` right after `wrap`** unless `put` occurred; otherwise `limit` becomes 0.

### Forgetting `flip` after `channel.read`

```java
ByteBuffer dst = ByteBuffer.allocate(1024);
int n = channel.read(dst);
if (n > 0) {
    dst.flip();
    // Process exact dst.remaining() bytes, not capacity.
}
```

Omitting `flip` causes `get` to read unfilled slots or miss the newly received bytes depending on `position`/`limit`. At end-of-stream, `read()` typically returns `-1`; on non-blocking channels, `0` means no data right now—**not** EOF.

### Calling `clear` while an incomplete frame remains

In protocol parsers, one `read` may deliver only half a message. After `flip` and consuming complete frames, call `compact()` to shift incomplete frame bytes to the front before reading more:

```java
// Illustrative code inside a protocol loop, not a standalone main.
buffer.flip();
consumeCompleteFrames(buffer); // Advances position past processed bytes.
buffer.compact();              // Keeps remaining bytes for next read.
```

Calling `clear()` here treats remaining data as gone even though physical bytes still sit in the array. Calling `rewind()` after processing half the buffer re-processes the already consumed prefix.

### Sharing a buffer across multiple threads

`ByteBuffer` is not thread-safe for concurrent mutations of `position`/`limit` on one instance. If multiple workers invoke relative `get`/`put` on one buffer, bytes get dropped or reordered even though `FileChannel` supports concurrent positional use. Give each task its own buffer, or synchronize and slice explicitly; never share a mutable `ByteBuffer` without clear ownership.

### Partial writes and post-write state

`FileChannel.write(buffer)` returns the actual bytes written. Only close/publish the file when the buffer has no remaining bytes or errors are handled. `write` does not auto-`clear` or auto-`flip` the buffer; it advances `position` by bytes transferred. For multi-buffer file writes, track actual bytes written and file position, avoiding `buffer.array().length` as bytes emitted.

## 9. Automated Testing and Diagnostics

Build separate tests for the three failure layers so you know which layer broke.

| Test Scenario | Required Evidence | Bug Caught |
| --- | --- | --- |
| Write a few chars to `BufferedWriter`, call `flush`, read while writer stays open | Read-back matches content | Missing `flush` where visibility is needed |
| Exit `try-with-resources` and read back | Complete data; `close` exceptions handled | Missing `close` / swallowed end-of-write error |
| Repeatedly invoke `Files.lines`, `Files.walk`, `FileChannel` | Descriptor count stays bounded after workload | Resource leak |
| Exercise exception, cancellation, early return paths | Resources still closed, no lingering file locks | Closing only on happy path |
| `ByteBuffer.put` → `flip` → channel write | Bytes written equals valid byte count | Wrong `position`/`limit` |
| Read file with buffer smaller than file | Loops until EOF, zero lost bytes | Assuming one `read` captures all data |
| Parser receives half a frame in one read | `compact` preserves unconsumed bytes | Dropping frames across buffer boundaries |
| Output requires crash durability | `flush` → `force`/`sync` → commit sequence defined and verified per filesystem | Confusing visibility with durability |

**Never write a test asserting "file size must stay 0 before `flush`" as an absolute guarantee**: depending on data size, buffer capacity, and implementation, writers may auto-flush when full. Tests should prove visibility after explicit flush/close, not demand pre-flush invisibility.

For parser unit tests, `ByteBuffer.allocate(4)` forces frames to split across multiple reads. For resource integration tests, use temp files and measure descriptors where possible; avoid relying solely on file deletion succeeding on Unix since open files can still be unlinked.

## 10. Distinguishing the Three Symptom Classes in Practice

| Symptom | First Suspect to Check | Resolution |
| --- | --- | --- |
| File empty while writer open, valid after close | Buffered output not flushed | Flush at required visibility boundaries |
| File intact after flush, lost on power/OS crash | Missing durability requirement or storage/filesystem limits | Check `FileChannel.force`/`FileDescriptor.sync` and durable save protocol |
| `Too many open files` | Unclosed stream/channel; unclear worker ownership | `try-with-resources`, test error paths, monitor descriptors |
| Cannot rename/delete file on Windows | Open handle/lock or OS share permissions | Find handle-holding process; ensure `close`/lock release |
| NIO `write` writes 0 bytes | `!buffer.hasRemaining()` or non-blocking output not writable | Print `position`/`limit`, check channel and readiness |
| File has garbage bytes or wrong length | Missing `flip`, reading whole `array()`, or unhandled partial write | Maintain buffer state and write-loop properly |
| Parser loses data at block ends | Calling `clear` instead of `compact`, treating chunks as whole frames | Retain pending bytes, test split inputs |
| File succeeds once, corrupts under load | Uncoordinated concurrent read/write, shared mutable buffer, premature close | Per-task buffers, locking/ordering, clear ownership |

## 11. Code Review Checklist for I/O

1. Locate every resource acquisition: `Files.newBufferedWriter`, `Files.newInputStream`, `FileChannel.open`, `Files.lines/list/walk/find`, `ZipFile`, `RandomAccessFile`. Verify who closes it on every path.
2. For buffered outputs, define **when external readers are allowed to see the data**. If before `close`, insert intentional `flush` calls; if durability is required, add `force`/`sync` after data reaches the file layer.
3. Never report success before writing and closing/committing complete; capture write/flush/close errors. For `PrintWriter`, call `checkError()` or switch to exception-throwing APIs.
4. For NIO, track buffer state before/after `put`/`read`/`flip`/`write`/`clear`/`compact`. Use `remaining` for valid bytes and loop on partial channel reads/writes.
5. Add repeated-load and failure-path tests to catch handle leaks; test on the target deployment platform, especially when behavior depends on Windows file sharing, remote filesystems, or cloud storage.
6. Minimize resource scope: avoid holding channels/streams across unrelated network calls or async tasks. For async workers, never close sources while work still needs them.

Key distinction: **`flush` drains bytes buffered in the Java layer; `close` ends resource ownership; `ByteBuffer.flip/clear/compact` manages read/write cursor state; `force/sync` addresses syncing to storage.** None substitutes for another.

### Official Documentation

- Java SE 17 `BufferedWriter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html
- Java SE 17 `Writer` and `OutputStream` (flush/close): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Writer.html
- Java SE 17 `ByteBuffer` / `Buffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `FileChannel` (write/force/close): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 `Files` (resource management): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
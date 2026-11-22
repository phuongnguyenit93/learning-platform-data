# `APPEND` and `OpenOption` Combination Limits When Reading/Writing with `Files`

## 1. Lesson Objectives

In Java NIO.2, `java.nio.file.Files` methods can accept file-opening options (`OpenOption`) to decide whether a file is **read, newly created, overwritten, truncated, or appended to**. A key option is `StandardOpenOption.APPEND`: new data is written at the **end of an existing file**, instead of starting from the beginning.

However, `APPEND` cannot be combined arbitrarily with every `OpenOption`. If configured improperly, a program can throw exceptions, lose old content, write duplicate data, or run into trouble when multiple threads/processes write concurrently.

After this lesson, you should:

- Understand what `APPEND` does, and how it differs from `WRITE`, `CREATE`, `CREATE_NEW`, and `TRUNCATE_EXISTING`.
- Know the **defaults when omitting options** in `Files.writeString`, `Files.write`, `Files.newBufferedWriter`, and `Files.newOutputStream`.
- Distinguish valid combinations, invalid combinations, and filesystem/provider-dependent cases.
- Properly use `Files.writeString`, `Files.newBufferedWriter`, `Files.newOutputStream`, and `Files.newByteChannel` in Java 17+.
- Recognize limitations regarding file creation, charsets, newlines, concurrency, atomicity, disk sync, and resource lifecycles.
- Choose safely between **appending records to a log** and **replacing entire file content**.

**Central message:** `APPEND` describes **where writes go**; it does not implicitly mean "create file if missing", "can read on the same channel", "write entire records atomically", or "data is durably persisted".

## 2. `StandardOpenOption` and How to Interpret Them

`OpenOption` is a marker interface for file-opening options. In the NIO.2 API, the `java.nio.file.StandardOpenOption` enum provides the common options:

| Option | Primary purpose | Notes |
| --- | --- | --- |
| `READ` | Open for reading | Cannot be used with `APPEND` on `Files.newByteChannel` |
| `WRITE` | Open for writing | Does not automatically mean append; may write from current position |
| `APPEND` | Write each time at end of file | Implies write intent; do not combine with `READ` or `TRUNCATE_EXISTING` when opening a byte channel |
| `CREATE` | Create file if it does not exist | If it already exists, does not truncate content |
| `CREATE_NEW` | Create new file only | Fails if path already exists; suitable to avoid writing into an existing file |
| `TRUNCATE_EXISTING` | Truncate existing file to 0 when opening for write | **Not append**; typically erases old content |
| `SYNC` | Request synchronous updates to content and metadata per open contract | Not guaranteed to have identical support/performance across all systems |
| `DSYNC` | Request synchronous updates to content per contract | Does not mean per-record atomicity |
| `DELETE_ON_CLOSE` | Request deleting the file on close per provider semantics | Not an option for keeping long-lived logs |
| `SPARSE` | Hint to create a sparse file when suitable | Provider-dependent, unrelated to append |

**Note:** Different APIs have different valid `OpenOption` sets and defaults. You cannot say "every `Files` method opens with READ" or "every option can be passed to every API".

## 3. How Does `APPEND` Work?

Suppose `events.log` currently contains:

```text
start
```

If opened with `APPEND` and `"stop\n"` is written, the content becomes:

```text
start
stop
```

There is no automatic newline insertion. If the initial file was `"start"` (no trailing `\n`), writing `"stop\n"` in append mode yields `"startstop\n"`. Programmers must explicitly define **record format and line boundaries**.

### 3.1. `APPEND` Differs from `WRITE`

`WRITE` permits writing to a file but **does not require every write to go to the end**. If you open a channel with `WRITE` alone, the default write position is usually the start of the file (position 0); writing new data can overwrite the initial bytes without erasing the old tail.

Conceptual example:

```text
Old file:              ABCDEF
WRITE from position 0: 12CDEF    (writes two bytes; old tail stays)
TRUNCATE + WRITE:      12        (erases old content before writing)
APPEND:                ABCDEF12  (appends at the end)
```

`APPEND` is commonly used with append-capable write calls such as `Files.writeString(path, data, UTF_8, APPEND)`, or streams/channels opened with `APPEND`. Do not try to simulate concurrent append via `channel.position(channel.size())`: between reading `size()` and writing, another writer can alter the file.

### 3.2. Does `APPEND` Create the File If Missing?

**Do not assume so.** When passing `APPEND` explicitly **without** `CREATE` or `CREATE_NEW`, the file must already exist under the open contract, otherwise `NoSuchFileException` may be thrown.

Recommended pattern to create a log if missing and append if it exists:

```java
Files.writeString(
        logPath,
        "event\n",
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
```

This is an **illustrative snippet**, without `logPath` declared or imports shown. If the file does not exist yet, `CREATE` allows creating it; if it exists, `APPEND` appends data at the end. `APPEND` implies write access (for supporting APIs), and you may also include `WRITE` explicitly if you want to state intent.

## 4. Dangerous Default: Omitting `OpenOption`

With these common file-writing overloads:

```java
Files.writeString(path, text);
Files.writeString(path, text, StandardCharsets.UTF_8);
Files.write(path, bytes);
Files.newBufferedWriter(path, StandardCharsets.UTF_8);
Files.newOutputStream(path);
```

**If no open options are specified**, these write APIs default to behavior equivalent to **`CREATE` + `TRUNCATE_EXISTING` + `WRITE`**: if the file is missing it is created, if it already exists it is truncated to empty before writing, and it is opened for writing. This fits **rewriting the entire content**, but is **unsuitable for appending to a log**.

Important point: once you **pass options explicitly**, you are choosing the open mode; do not assume `CREATE` and `TRUNCATE_EXISTING` are still added automatically. For example:

```java
Files.writeString(path, "line\n",
        StandardCharsets.UTF_8, StandardOpenOption.APPEND);
```

intends to **append to an existing file**, without guaranteeing creation. If you need creation when missing, pass `CREATE` as well.

### 4.1. Comparison Table of Common Operations

| Intent | Suggested `OpenOption` | Outcome on existing file | Outcome on missing file |
| --- | --- | --- | --- |
| Overwrite entire content | Pass no options (default) | Truncates then writes | Creates and writes |
| Overwrite entire content, explicit mode | `CREATE, WRITE, TRUNCATE_EXISTING` | Truncates then writes | Creates and writes |
| Append, create if missing | `CREATE, APPEND` | Appends at end | Creates and writes |
| Append, requiring file to exist | `APPEND` | Appends at end | Fails |
| Create new file only, reject old file | `CREATE_NEW, WRITE` | Fails | Creates and writes |
| Write into existing file by position | `WRITE` | Writes from current position, no auto-truncate | Usually fails without CREATE |
| Open for reading | `READ` in corresponding byte channel API | Reads file | Usually fails if file is missing |

For `Files.newByteChannel`, **passing no options defaults to `READ`**, unlike the file-writing methods above. Do not apply a single "default" across every `Files` API.

## 5. Invalid or Misleading Combinations

### 5.1. `APPEND` + `TRUNCATE_EXISTING`

Two conflicting intents:

- `APPEND` wants to keep existing content and write at the end.
- `TRUNCATE_EXISTING` wants to erase existing content when opening for write.

For `Files.newByteChannel`/`SeekableByteChannel`, the API contract states that **`APPEND` and `TRUNCATE_EXISTING` must not be used together**; an invalid combination throws `IllegalArgumentException`. Do not expect Java to "truncate first then append" as a standard feature. Choose one clear intent.

### 5.2. `APPEND` + `READ`

For `Files.newByteChannel`, `APPEND` cannot be combined with `READ`. How `APPEND` is defined in the byte-channel open API forbids combining `READ` and `APPEND` as a single mode; an invalid combination can raise `IllegalArgumentException` or an appropriate subtype.

If you need to both inspect file content and append records:

- Open **a separate read stream** and **a separate append stream**, managing concurrency per application design.
- Or pick a position-based access and locking scheme when complex operations are needed; do not assume replacing `APPEND` with seek-to-end is safe under concurrency.
- If building a log/queue system, consider a dedicated writer and synchronization rather than arbitrary concurrent writers.

Do not pass `READ, APPEND` as a default combination and catch errors hoping a provider "might support it".

### 5.3. `APPEND` + `CREATE`

This combination is **typically valid and useful** when you want to append data if the file exists or create a new one if not:

```java
Files.writeString(logPath, message,
        StandardCharsets.UTF_8,
        StandardOpenOption.CREATE,
        StandardOpenOption.APPEND);
```

`CREATE` does not require the file to be new; if it already exists, it does not erase it. Combining it with `APPEND` is the classic logging pattern.

### 5.4. `CREATE_NEW` + `APPEND`

`CREATE_NEW` has a different goal from `CREATE`: it only permits opening a brand-new file, failing if the filename already exists. If the file exists, an exception like `FileAlreadyExistsException` is expected even when append is requested.

Therefore, never choose `CREATE_NEW` when the business requirement is **accumulating multiple records into an existing log file**. `CREATE_NEW` fits when you must create a unique output without touching prior data.

### 5.5. `SYNC`/`DSYNC` Do Not Guarantee Atomic Append

`SYNC` and `DSYNC` relate to requesting synchronized updates to the storage device per provider semantics. They do not turn multiple write calls or multiple log lines into a transaction, do not prevent interleaving between writers, and do not replace locking or serialized writing.

`BufferedWriter`'s buffer also plays a role: calling `flush()` pushes accumulated data to the underlying writer/stream, but does not mean all data is durable across power loss. When strict durability is required, study `FileChannel.force(...)`/fsync mechanisms and actual filesystem/hardware behavior.

### 5.6. Unsupported Options and Exceptions

The valid option set depends on the **method, filesystem provider, and platform**. Passing an option unsupported by the API/provider can throw `UnsupportedOperationException`; invalid combinations can throw `IllegalArgumentException`; missing permissions or open/write failures can throw `IOException` or corresponding access exceptions.

Do not lump all errors together as "file not found". In particular, an **`IOException` during writing** can occur after part of the data has already been appended to the file.

## 6. Java 17+ Example: `Files.writeString` Create, Append, and Truncate

This example intentionally creates a temporary directory so user files remain untouched, uses UTF-8 explicitly, and verifies content after each step. The program does not assume a fixed path on Windows/Linux/macOS.

Save as **`AppendOptionsDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class AppendOptionsDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("append-options-");
        Path log = directory.resolve("events.log");
        Path created = directory.resolve("new.log");

        try {
            Files.writeString(log, "first\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            Files.writeString(log, "second\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.APPEND);

            Files.writeString(log, "third\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);

            System.out.println("Appended: "
                    + Files.readAllLines(log, StandardCharsets.UTF_8));

            Files.writeString(created, "created\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);

            System.out.println("Created on append: "
                    + Files.readString(created, StandardCharsets.UTF_8)
                           .equals("created\n"));

            Files.writeString(log, "reset\n",
                    StandardCharsets.UTF_8,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING);

            System.out.println("After truncate: "
                    + Files.readAllLines(log, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(created);
            Files.deleteIfExists(log);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 AppendOptionsDemo.java
java AppendOptionsDemo
```

**Stdout when all filesystem operations succeed:**

```text
Appended: [first, second, third]
Created on append: true
After truncate: [reset]
```

**Explanation:**

1. `CREATE_NEW, WRITE` creates `events.log` and writes the first line. If the file already existed, this step would fail instead of overwriting.
2. `APPEND` adds `second\n` to the existing file; no manual seek to end is required.
3. `CREATE, APPEND` adds `third\n` while also handling the case where the file does not exist yet (as demonstrated with `new.log`).
4. After appending, `readAllLines` on the small demo file returns a list of three lines in order. For large logs, do not call `readAllLines` just to verify.
5. `WRITE, TRUNCATE_EXISTING` erases the old content in `events.log` and writes `reset\n`. The previous lines are now gone.
6. The `finally` block cleans up the created files and directory. In production code, write errors and cleanup errors should be handled per application policy.

The example uses `\n` for consistent output. Applications must specify encoding and newline format explicitly; `APPEND` does not add delimiters automatically.

## 7. Java 17+ Example: Binary Append with `newByteChannel`

When working with byte data, you can use `Files.newByteChannel` to open a `SeekableByteChannel`, passing `OpenOption`s as a `Set`. Here especially, avoid combining `READ` or `TRUNCATE_EXISTING` with `APPEND`.

Save as **`AppendByteChannelDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.EnumSet;

public class AppendByteChannelDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("append-channel-");
        Path file = directory.resolve("data.bin");

        try {
            Files.write(file, new byte[] {'A'},
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE);

            try (SeekableByteChannel channel = Files.newByteChannel(
                    file,
                    EnumSet.of(
                            StandardOpenOption.WRITE,
                            StandardOpenOption.APPEND))) {
                ByteBuffer buffer = ByteBuffer.wrap(
                        "BC".getBytes(StandardCharsets.US_ASCII));

                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }
            }

            Files.write(file, new byte[] {'D'},
                    StandardOpenOption.APPEND);

            System.out.println("Content: "
                    + Files.readString(file, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 AppendByteChannelDemo.java
java AppendByteChannelDemo
```

**Stdout:**

```text
Content: ABCD
```

The program:

- Creates a new file with one byte `A`.
- Opens the channel in `WRITE, APPEND` mode and appends bytes `B`, `C`.
- Loops while `ByteBuffer.hasRemaining()` because the channel interface may write fewer bytes than remain in the buffer in a single call; never assume one `write` always writes the entire `ByteBuffer`.
- Appends byte `D` using `Files.write`.
- Reads the small demo file to confirm the sequence `ABCD`.

**Note:** `SeekableByteChannel` allows positioning, yet with `APPEND` writing is governed by append semantics; do not rely on `position(0)` to bypass append behavior. When you need to modify bytes at arbitrary offsets, open with `READ`/`WRITE` under a different design without `APPEND`.

## 8. Using `Files.newBufferedWriter` When Writing Text Logs

`newBufferedWriter` provides a buffered writer to reduce small write calls. When appending text:

```java
// Illustrative snippet: logPath is a valid Path.
try (java.io.BufferedWriter writer =
        java.nio.file.Files.newBufferedWriter(
                logPath,
                java.nio.charset.StandardCharsets.UTF_8,
                java.nio.file.StandardOpenOption.CREATE,
                java.nio.file.StandardOpenOption.APPEND)) {
    writer.write("event=started");
    writer.newLine();
}
```

Practical notes:

- `try-with-resources` closes the writer and flushes remaining buffered data on successful close; do not omit closing.
- `newLine()` produces the platform line separator; if the file format requires consistent LF, write `"\n"` intentionally.
- If multiple threads/processes append concurrently, the buffer may batch or split writes into multiple lower-level calls. Do not treat a single `writer.write("record")` as an **atomic record** across all filesystems.
- `newBufferedWriter` opens the writer with a specific charset; appending into a file with a different encoding produces mixed-encoding unreadable files.
- If specifying **`APPEND` without `CREATE`**, the application must ensure the file exists or handle missing-file errors.
- Do not use `TRUNCATE_EXISTING` with append mode to "clear old logs": log rotation requires a dedicated rotation workflow.

### 8.1. Choosing APIs by Data Type

| Data / requirement | Suggested API | Things to watch |
| --- | --- | --- |
| Append one short text line | `Files.writeString` with `UTF_8, CREATE, APPEND` | Separator, encoding, other writers |
| Append many consecutive lines | `Files.newBufferedWriter` with `CREATE, APPEND` | `close`/`flush`, concurrency |
| Append byte blocks | `Files.newOutputStream` with `CREATE, APPEND` | Binary format, stream lifecycle |
| Need `ByteBuffer`/channel | `Files.newByteChannel` with `WRITE, APPEND` | Do not combine `READ`/`TRUNCATE_EXISTING` |
| Rewrite an entire config file | Default `Files.writeString` or explicit `CREATE, WRITE, TRUNCATE_EXISTING` | Old version can be lost on mid-write failure |
| Create new file only, avoid existing files | `CREATE_NEW, WRITE` | Handle already-existing file |
| Safe "replace" style write | Temp file → verify → `Files.move` per policy | `ATOMIC_MOVE` only when supported by provider |

`Files.writeString` is convenient for small/medium text, but has no built-in knowledge of log rotation, locking, or maximum file length.

## 9. `APPEND` When Multiple Threads or Processes Write Concurrently

### 9.1. "Writing at the End of the File" Does Not Always Mean "Whole-Record Atomicity"

`APPEND` sets the write position at the end of the file per provider contract. However, whether seeking to EOF and writing data **happens as an atomic operation** depends on the filesystem/provider; you cannot claim it applies universally to every device or write size.

A log record like:

```text
2026-10-27 INFO started
```

may be translated by a writer into one or more lower-level writes beneath the buffer layer. When multiple writers run concurrently, bytes from different records may interleave, or ordering may diverge from logical program timing. Nor does `APPEND` prevent another process from opening the file in truncate mode.

**Practical strategies:**

1. Use **one dedicated writer** for a given log file within a process, passing records through a queue if needed.
2. With multiple processes, agree on a write/locking protocol or use a multi-process-capable logging system; do not rely solely on `APPEND`.
3. Consider `FileChannel.lock()` in environments that support it and ensure every writer honors the lock. File locks can vary by OS/provider and do not necessarily block external code that ignores locks.
4. If transactional atomicity is required, choose an appropriate data store/transaction mechanism rather than treating file appending as a database transaction.
5. Measure byte counts and apply **file rotation**, retention, and storage quota policies instead of letting appends fill the disk.

### 9.2. `APPEND` Does Not Guarantee Business Message Ordering

Even when the filesystem appends bytes cleanly, multiple threads can prepare records in an order different from when they are written. If ordering matters, serialize at the application layer via sequence numbers or a single sequential writer. Never infer "event A happened before B" solely because its bytes appear earlier in the log.

### 9.3. Appending and Durability

With buffering, data may remain in heap before `flush`; after `flush`, data may sit in OS caches; after `close`, durability requirements still depend on the storage stack. `SYNC`/`DSYNC` or `FileChannel.force(...)` can be considered when specs demand durable writes, yet they do **not** replace crash recovery, record framing, checksums, or concurrent-writer coordination.

## 10. Filesystem/Provider Limitations and Exceptions

`StandardOpenOption` values are standard API contracts, but providers decide many support details. Specifically:

- **Invalid combinations:** `APPEND` with `READ` or `TRUNCATE_EXISTING` in `newByteChannel` is rejected.
- **Missing file:** `APPEND` alone without `CREATE`/`CREATE_NEW` does not create the file.
- **Permission denied:** may throw `AccessDeniedException` or `IOException` depending on operation.
- **File already exists:** `CREATE_NEW` may throw `FileAlreadyExistsException`.
- **Unsupported option:** `UnsupportedOperationException` or API/provider-specific error.
- **Path is a directory:** not a regular file for writing; opening fails.
- **Read-only filesystem, disk full, quota, flaky network:** I/O errors can occur **after some bytes have already been written**.
- **Distributed/network filesystems:** atomicity and visibility of appends may differ from local filesystems.
- **Symlinks/replaced paths:** checking "does this file exist" before opening introduces time-of-check-to-time-of-use risks; validate paths per your threat model.

When updating critical files, do not just ask "did the API throw?"—also know the **file state after an error**. Append does not roll back already-written data; direct truncation replacement can also destroy the old version on mid-way failure.

## 11. Common Mistakes

1. **Forgetting `APPEND` when writing logs:** `Files.writeString(path, line)` by default normally replaces old content with the new content.
2. **Assuming `APPEND` creates the file:** add `CREATE` if missing files should still succeed.
3. **Using `APPEND` and `TRUNCATE_EXISTING` together:** conflicting intents; invalid combination in byte-channel APIs.
4. **Using `READ` with `APPEND` on one channel:** invalid under `Files.newByteChannel`.
5. **Confusing `WRITE` with append:** plain `WRITE` has no semantics for always writing at EOF.
6. **Calling `position(size())` then writing with multiple writers:** prone to races; not equivalent to `APPEND`.
7. **Forgetting newlines:** appending `"a"` then `"b"` produces `"ab"`, without automatic line breaks.
8. **Mixing charsets:** appending UTF-8 into a file encoded in another charset produces inconsistent unreadable content.
9. **Not closing writers/streams:** data remains buffered and resources can leak.
10. **Flushing every character:** increases downstream calls and usually hurts throughput.
11. **Treating append as a transaction:** no rollback, and no universal guarantee of atomic whole-record writes across all providers.
12. **Believing `CREATE_NEW` means "append if file exists":** on the contrary, it fails if the file exists.
13. **Forgetting exception handling:** the file may already be partially written when an I/O error occurs.
14. **Ignoring unbounded growth:** long-running appending grows logs indefinitely or fills disks.
15. **Using `readAllLines` to process huge log files:** can exhaust heap; read line-by-line via streaming or use proper log tools.
16. **Confusing API open defaults:** `newByteChannel` with no options defaults differently from `writeString` and `newBufferedWriter`.

## 12. Essential Tests

For applications using append, at minimum verify:

- **Non-existent file:** `CREATE, APPEND` creates the file successfully; `APPEND` alone fails per contract.
- **Existing file:** after two appends, old content remains and new data sits at the end.
- **No options passed:** `Files.writeString` overwrites/truncates by default; avoid accidental use for logs.
- **`CREATE_NEW` on existing file:** must not overwrite.
- **Byte sequences:** binary append preserves byte order and exact size.
- **Encoding:** UTF-8 with Vietnamese accents/emojis; target file never mixes charsets.
- **Newlines:** distinguish files with a trailing LF from files without one.
- **Multiple writers:** test concurrent load, checking record counts, ordering when required, and file rotation scenarios.
- **I/O errors:** disk full/quota, permissions, stream closing; check partial records and avoid duplicate records on retry.
- **Different providers:** verify in real deployment environments (local disk, network, virtual filesystems) if special atomicity or write durability is required.

## 13. Practice Exercises

1. Explain why `Files.writeString(path, "A")` followed by `Files.writeString(path, "B")` yields a different result from `Files.writeString(path, "A", APPEND)` followed by `Files.writeString(path, "B", APPEND)` when the file already exists.
2. Write a program that creates `journal.txt` if missing, appending one UTF-8 line per run. Verify that after running three times, all three lines (old and new) are present.
3. Try `APPEND` alone on a missing file; catch and classify the exception. Fix the code using `CREATE, APPEND`.
4. Design a test distinguishing `WRITE`, `WRITE + TRUNCATE_EXISTING`, and `APPEND` on the same initial content `ABCDEF`.
5. For `Files.newByteChannel`, explain why `APPEND + READ` and `APPEND + TRUNCATE_EXISTING` are invalid. Choose separate open patterns for read and write needs.
6. Write bytes `{1, 2}` and then append `{3, 4}`; verify the file holds `[1, 2, 3, 4]` with no automatic delimiter bytes.
7. Have two threads write 1,000 records each. Why should a single passing run not be treated as proof of atomic appending across all filesystems?
8. Implement a rotation policy when a log exceeds 10 MiB. Why isn't checking `Files.size` alone a guarantee against exceeding the threshold under concurrency?
9. Explain the differences between `flush`, `close`, `SYNC`/`DSYNC`, and `FileChannel.force` from the perspective of data reaching storage; choices should depend on durability needs and the provider.
10. If an append write fails after half a record hits the file, what bug can blind retries cause? Propose framing, checksums, sequence numbers, or a dedicated writer system when consistency is required.

## 14. Summary

- `APPEND` is the option to **append at the end of a file**; it does not erase prior content, nor does it automatically add newlines, create files, or coordinate concurrent writers.
- `CREATE, APPEND` is typically appropriate for writing log files and creating them if missing; `CREATE_NEW` deliberately **rejects** existing files.
- Write methods `Files.writeString`, `Files.write`, `newBufferedWriter`, and `newOutputStream` default to **creating and truncating** when no options are given; never forget this rule.
- `Files.newByteChannel` has a different default (read) and strictly forbids `APPEND + READ` and `APPEND + TRUNCATE_EXISTING`.
- Standalone `WRITE` does not mean append; `TRUNCATE_EXISTING` clears existing content and does not belong with append goals.
- For systems requiring multiple writers, durability, quotas, or transactions, design **synchronization and error handling at the application layer**, rather than placing all expectations on `APPEND`.

**Safe selection rule:** Ask clearly whether the program intends to *create new*, *overwrite*, or *append*. Then select a consistent `OpenOption` combination, define behavior for existing vs. missing files, close resources properly, and test on the exact filesystem you will deploy to.
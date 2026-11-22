# Duplicate Events, Coalescing, and Incomplete File Contents in Java WatchService

## 1. The Problem to Understand

Java NIO.2's `WatchService` tells an application that **the state of a directory may have changed**. This API is useful for config hot-reloading, file synchronization, detecting input documents, automated file processing, or directory monitoring. However, events **are not an exact transaction log**, are not a durable queue, and **do not guarantee the file has finished being written** when the consumer receives the notification.

Three phenomena must be designed for upfront:

1. **Duplicate events:** one file save can emit multiple `ENTRY_MODIFY` events; the same path can appear across multiple rounds.
2. **Coalesced and lost events:** the provider can coalesce changes of the same kind/context into a single `WatchEvent` with `count()` greater than one; when accumulation cannot keep up, it may emit `OVERFLOW` because some events were discarded.
3. **File not yet ready:** `ENTRY_CREATE` or `ENTRY_MODIFY` can arrive before the writer closes the file or finishes the final record. Reading immediately may retrieve only partial JSON, CSV, ZIP, or binary content.

Design principle: **treat events as signals to re-inspect file state, not as once-only data ingestion commands or proof that the producer has finished.**

## 2. Scope of `WatchService` Guarantees

An application creates a `WatchService` via `FileSystems.getDefault().newWatchService()`, then registers **directories** using `Path.register(...)`. Standard events:

| Kind | What it indicates | What is NOT guaranteed |
| --- | --- | --- |
| `ENTRY_CREATE` | An entry appeared in the registered directory. | That the file contains all bytes, or the producer stopped writing. |
| `ENTRY_MODIFY` | The provider observed a change on an entry. | That only one edit happened, editing finished, or data is valid. |
| `ENTRY_DELETE` | The entry is no longer present at the observed location. | That it was definitely a business deletion rather than a move/rename. |
| `OVERFLOW` | Some notifications may not have been retained in the queue. | That remaining events suffice to reconstruct all changes. |

For standard entry events, `event.context()` is the relative path to the entry inside the registered directory. The full path is normally obtained via:

```java
// Illustrative snippet; key is a valid WatchKey.
Path watched = (Path) key.watchable();
Path relative = (Path) event.context();
Path full = watched.resolve(relative);
```

Do not cast `event.context()` to `Path` before checking `OVERFLOW`, because overflow does not represent an individual file. `Path.register` in Java SE 17/21 primarily watches entries of **a directory**, without automatically watching the subdirectory tree. To monitor a tree, each directory must be registered, including newly created subdirectories.

With network file systems, custom providers, or polling-based watchers, latency and event-detection capability can differ. The Java Javadoc explicitly notes that detection timing, event ordering, and change detection on remote file systems are **implementation-dependent**; very short-lived files sometimes go undetected. Do not assume "one write definitely delivers one event immediately".

## 3. Why Does the Same File Produce Multiple `ENTRY_MODIFY` Events?

A writer might open a file and write sequentially:

```text
open("data.csv")
write("id,amount\n")
flush()
write("1,100\n")
write("2,200\n")
close()
```

From the watcher's perspective, you may see a sequence of `ENTRY_CREATE` and multiple `ENTRY_MODIFY` events, or only a subset of events, depending on the OS and how the JDK receives native notifications.

Causes include:

- The producer writes in small chunks or flushes multiple times.
- The file is truncated and rewritten; metadata and content change at different times.
- An editor saves contents via a temporary name and then renames; the watcher may observe create/delete/modify across different paths.
- The provider batches events into rounds; the same path reappears after `WatchKey` is reset.
- Syncing, backup, antivirus, or other processes generate additional metadata/content changes.

**Mistake:** on every `ENTRY_MODIFY`, calling `importFile(path)` and inserting all records into a database. The same file can be imported multiple times, generating duplicate invoices or sending repeated notifications.

**Right design:** events only mark the path as "dirty"; a worker processes the current state under an **idempotency key** (artifact ID + version/checksum/transaction ID), recording the outcome only upon successful commit. If the same version appears across multiple events, reprocessing must produce no duplicate side effects.

## 4. Meaning of `WatchEvent.count` and Coalescing

`WatchEvent<T>` has three main components:

- `kind()`: event kind.
- `context()`: data attached to the event, usually the relative path name.
- `count()`: number of times the event was observed and represented together in this event object.

Example:

```text
kind=ENTRY_MODIFY
context=report.csv
count=4
```

This example does not say the producer called `write` exactly 4 times, nor does it mean the file has 4 valid versions. This is **the count of notifications recorded/coalesced by the provider**, not a count of business transactions.

The same `kind` and `context` can be coalesced to reduce the number of event objects. When two operations differ or arrive at different times, there is no portable rule forcing every system to coalesce them identically.

Do not loop file processing `count()` times:

```java
// Anti-pattern: notification count is not data version count.
for (int i = 0; i < event.count(); i++) {
    processFile(path);
}
```

The snippet above is only an **illustration of a bug**, not standalone code. `event.count()` is useful for metrics or alerting on burst changes, but **the file's actual contents when read are the state that must be verified**.

### Coalescing vs. `OVERFLOW`

| Phenomenon | Meaning | How to Respond |
| --- | --- | --- |
| Duplicate events | Same target notified repeatedly across one or more rounds. | Dedup/debounce and idempotent processing. |
| Coalesced event | One `WatchEvent` represents multiple observations of the same kind/context. | Do not import `count` times; determine the file version to process. |
| `OVERFLOW` | System may have dropped event information due to queue limits. | **Rescan/reconcile the directory**, do not rely on the current event list. |
| No events received after restart | `WatchService` is not a durable message log. | Startup scan; durable processed-version state. |

The `WatchService` Javadoc specifies that when an implementation knows it discarded events, it emits `OVERFLOW`. However, **not seeing** overflow is not proof that every change on every OS/remote file system was detected.

## 5. `WatchKey` Lifecycle and Proper Batch Processing

`WatchService` places a **`WatchKey`** representing a signalled registration into the queue. Consumers use:

- `watcher.take()`: waits until a key arrives.
- `watcher.poll()`: retrieves immediately or returns `null`.
- `watcher.poll(timeout, unit)`: waits with a time limit.
- `key.pollEvents()`: retrieves and removes the key's accumulated events.
- `key.reset()`: returns the key to the ready state after batch processing; returns `false` if the key is no longer valid.

Processing flow:

```text
key READY
  |
FileSystem observes change
  v
key SIGNALED -> placed into queue
  |
watcher.take / poll
  |
key.pollEvents -> iterate events
  |                ENTRY_*  -> mark path dirty
  |                OVERFLOW -> full rescan needed
  v
key.reset()
  +-> true : continue monitoring
  +-> false: registration lost, recovery needed
```

If you forget `reset()`, the watcher may not continue receiving new events as expected. If you delay `reset()` for tens of seconds to process a large file on the same thread, backlog can grow and drop events. Thus in production, the watcher should **drain events quickly, update lightweight state, and reset promptly**, while parsing/importing is handed off to workers with bounded queues.

A guiding processing snippet:

```java
// Inside the watcher loop; rescanNeeded is already declared.
WatchKey key = watcher.take();
Path dir = (Path) key.watchable();

for (WatchEvent<?> ev : key.pollEvents()) {
    if (ev.kind() == StandardWatchEventKinds.OVERFLOW) {
        rescanNeeded = true;
        continue;
    }
    Path child = dir.resolve((Path) ev.context());
    markDirty(child, ev.kind(), ev.count());
}
if (!key.reset()) {
    handleInvalidRegistration(dir);
}
```

This is an **architectural snippet**, not a standalone program: `markDirty`, `handleInvalidRegistration`, and `rescanNeeded` are defined by the application. `OVERFLOW` does not carry a valid file path to pass straight into `markDirty`. Errors like `ClosedWatchServiceException` and `InterruptedException` must be handled per application lifecycle.

## 6. A `MODIFY` Event Does Not Say the Writer Closed the File

The `WatchService` Javadoc explicitly states: when an event reports a file in a directory was modified, **there is no guarantee the program performing the modification has finished**.

Timeline illustration:

```text
Producer                     Watcher / consumer
--------                     ------------------
CREATE input.json
write("{ \"items\": [")
                             ENTRY_CREATE arrives
                             reads file, JSON not yet closed
write("{ \"id\": 1 }")
                             ENTRY_MODIFY arrives
                             retries parse, may still fail
write("] }")
close writer
                             no standard "WRITE_COMPLETED" event
```

This is only **one possible interleaving**, not a portable event count or order. Even when `Files.exists(path)` is `true` and `Files.size(path) > 0`, the producer may still be writing.

File formats prone to partial reads:

- JSON/XML missing closing braces/tags, causing parser errors.
- CSV missing the last line or trailing newline.
- ZIP/JAR whose central directory is at the end, temporarily unreadable.
- Binary records with length/header written before payload/checksum completes.
- Images/videos with headers created before all frames are written.

Do not assume every parse exception means the writer has not finished: a file can also be genuinely corrupt. Applications must have **retry limits, timeouts, structural validation, and quarantine**.

## 7. Strongest Strategy: Temporary File Then Atomic Publish

When you can modify the producer, use a **publishing protocol** instead of guessing from `ENTRY_MODIFY`:

1. Producer creates the file under a temporary name like `report.csv.tmp`; consumer ignores `.tmp`.
2. Producer writes complete contents, validates internally, and **closes the file**.
3. Producer calls `Files.move(temp, ready, StandardCopyOption.ATOMIC_MOVE)` on the same file system, if supported.
4. Consumer **only processes** `report.csv.ready` after it appears; watched events act as a trigger to scan candidates.
5. Consumer verifies version, length/checksum/schema, processes idempotently, and persists results.

`ATOMIC_MOVE` makes the rename/move atomic at the file system level when supported by the provider; it does not guarantee every file system supports it or replaces an existing target identically. When unsupported, Java throws `AtomicMoveNotSupportedException`. When atomic publication is a hard requirement, **do not silently fall back to a non-atomic copy/move**.

**Atomic rename does not mean power-loss durability.** If data and directory entries must survive crashes, appropriate `FileChannel.force`/synchronization policies per file system/OS are required. And `WatchService` still has duplicates/overflow: consumers must reconcile rather than relying entirely on events.

### Java 17+ Example: Create Temporary Copy and Publish

Create file `AtomicPublishDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class AtomicPublishDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("publish-demo-");
        Path temp = dir.resolve("message.tmp");
        Path ready = dir.resolve("message.ready");
        try {
            Files.writeString(temp, "PART", StandardCharsets.US_ASCII,
                    StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
            System.out.println("partial-temp=" + Files.readString(temp));
            Files.writeString(temp, "DONE", StandardCharsets.US_ASCII,
                    StandardOpenOption.APPEND);
            Files.move(temp, ready, StandardCopyOption.ATOMIC_MOVE);
            System.out.println("published=" + Files.readString(ready));
            System.out.println("temp-exists=" + Files.exists(temp));
        } finally {
            Files.deleteIfExists(temp);
            Files.deleteIfExists(ready);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac --release 17 AtomicPublishDemo.java
java AtomicPublishDemo
```

Verified output on a file system supporting atomic move:

```text
partial-temp=PART
published=PARTDONE
temp-exists=false
```

Initially the producer only has `PART`. The consumer must not treat temporary content as a ready artifact. Only after the app appends `DONE` and closes the stream is the name `message.ready` published. **The publishing naming rule itself** carries the completion semantics, not the number of notifications received. When pairing this model with a watcher, only enqueue valid `.ready`/manifest files—do not process every `ENTRY_CREATE`.

## 8. Marker File or Manifest with Checksum

A variant is that the producer writes the data file first, and only creates a `.done` or `.ready` marker file **after completion**:

```text
batch-0007.data
batch-0007.ready
```

A manifest can contain name, version/sequence, size, checksum, total record count, and schema version. The consumer watches for the marker, then validates the data file.

**Note:** if the producer creates the marker before finishing data or writes the marker non-atomically, the marker itself can be read partially. Thus the marker needs a clear contract: write temporarily then publish, with a verifiable metadata/manifest format; consumers must handle deleted, missing, replaced, or checksum-mismatched files.

Using producer sequence or content hash for idempotency is stronger than using path alone. If a new file replaces the same name `batch.data`, the consumer cannot assume it is the same version merely because the path matches.

## 9. When You Do Not Control the Producer: Debounce and Stability Checks Are Only Heuristics

When temp file + atomic move or markers cannot be required, the consumer can use a quiet period and metadata comparison:

1. Upon receiving create/modify, place the path into a dirty list and record the timestamp of the latest event.
2. After a source-configured quiet period (e.g., a few hundred milliseconds or a few seconds), inspect `size` and `lastModifiedTime`.
3. Wait further and re-check; if unchanged, try opening and parsing the file per its format.
4. Read/parse with bounds and verify the file did not change after processing; if it changed, mark dirty to retry.
5. After a deadline or max retries, report an error/quarantine instead of looping forever.

**Never declare a file complete solely because size/mtime stayed stable.** A writer may pause longer than the quiet period, overwrite with the same size, the OS may have coarse timestamp resolution, or the file may be replaced after reading metadata. The race between `Files.exists` and `Files.readAllBytes` also exists. If strong guarantees are required, cooperative producer protocols or formats with commit markers/transaction logs are needed.

Do not use `Thread.sleep(...)` directly inside the watch loop: it blocks processing events for other directories, grows the backlog, and increases overflow risk. Use `ScheduledExecutorService` or a dedicated worker scheduler with bounded queues and backpressure.

### Per-Path Debounce Model Using Generation

```java
// Illustrative snippet, not standalone:
// versions: ConcurrentHashMap<Path, Long>
// scheduler: ScheduledExecutorService
long generation = versions.merge(path, 1L, Long::sum);
scheduler.schedule(() -> {
    Long current = versions.get(path);
    if (current == null || current.longValue() != generation) return;
    enqueueForReadinessCheck(path);
}, 700, TimeUnit.MILLISECONDS);
```

If a new event arrives for the same path, generation increments; the older scheduled callback does not enqueue. Even so, this snippet does not cover every scenario: stale tasks still sit in the scheduler, files can keep changing without events arriving, and worker logic needs a "dirty during processing" state. Production code must bound scheduled tasks, synchronize state, and handle path deletion/recreation. Use this example solely to understand that **debouncing does not equal a readiness guarantee**.

## 10. Java 17+ Example: `WatchService` and `WatchKey` Lifecycle

The demo creates a temporary directory, registers the watcher **before creating the file**, and then waits up to 5 seconds for `ENTRY_CREATE`. Because modify event counts depend on the OS, the demo only checks creation and does not print modify counts.

Create file `WatchEventDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;

public class WatchEventDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("watch-demo-");
        Path file = dir.resolve("report.txt");
        try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
            dir.register(watcher, StandardWatchEventKinds.ENTRY_CREATE,
                    StandardWatchEventKinds.ENTRY_MODIFY,
                    StandardWatchEventKinds.ENTRY_DELETE);
            Files.writeString(file, "READY", StandardCharsets.US_ASCII,
                    StandardOpenOption.CREATE_NEW);
            boolean created = false;
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            while (!created && System.nanoTime() < deadline) {
                long remaining = deadline - System.nanoTime();
                if (remaining <= 0) break;
                WatchKey key = watcher.poll(remaining, TimeUnit.NANOSECONDS);
                if (key == null) break;
                for (WatchEvent<?> event : key.pollEvents()) {
                    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                        throw new IllegalStateException("Rescan needed after OVERFLOW");
                    }
                    if (event.kind() == StandardWatchEventKinds.ENTRY_CREATE
                            && Path.of("report.txt").equals(event.context())) {
                        created = true;
                    }
                }
                if (!key.reset()) throw new IllegalStateException("Invalid watch key");
            }
            if (!created) throw new IllegalStateException("Create event not observed");
            System.out.println("created-observed=" + created);
            System.out.println("file-content=" + Files.readString(file));
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

```bash
javac --release 17 WatchEventDemo.java
java WatchEventDemo
```

Verified result on a local file system with native notifications:

```text
created-observed=true
file-content=READY
```

**Explanation:** the watcher was registered before the file appeared, `poll(timeout)` bounds the wait, `pollEvents()` retrieves events in the batch, `event.context()` is matched by relative path, and `reset()` re-arms the key. The demo throws an error on `OVERFLOW` because it is not a production consumer; a real consumer must rescan.

What makes the file contain `READY` when read in this program is that **`Files.writeString` already returned and closed the stream before we polled the event**, not because `ENTRY_CREATE` itself guarantees the producer closed the file. On polling file systems or remote mounts, the event may not arrive before the deadline. Do not treat the stdout above as a universal promise.

## 11. Designing for Duplicates, Overflow, and Files Changing Mid-Processing

A realistic consumer should separate the watcher and processing workers:

```text
WatchService / WatchKey
   |
   +-- ENTRY_CREATE / ENTRY_MODIFY ---> markDirty(path)
   |                                      |
   |                                      v
   |                               debounce / readiness
   |                                      |
   |                                      v
   |                              validate + parse
   |                                      |
   |                                      v
   |                              idempotent commit
   |
   +-- ENTRY_DELETE -------------------> reconcile missing entry
   |
   +-- OVERFLOW -----------------------> full directory rescan

Startup scan / periodic reconciliation -> same processing pipeline
```

### Do Not Drop New Events While a Worker Is Processing

A Set of pending paths avoids duplicate queuing, but has a race:

1. Worker is reading file A.
2. Producer modifies file A again; watcher sees the event, but A is already in the Set so it does not enqueue.
3. Worker removes A from the Set when finished.
4. No task remains to process the new version.

Use explicit states:

```text
IDLE -> DIRTY -> PROCESSING
                   |
                   +-- event arrives mid-processing -> DIRTY_AGAIN
                   |
                   +-- finished and dirty_again -> PROCESSING again
                   |
                   +-- finished and not dirty -> IDLE
```

States must be updated thread-safely (`ConcurrentHashMap.compute`, per-key mutex, or a single event-loop owner). Workers can compare producer version/hash before and after import; if contents changed, re-run. **No state machine turns `WatchService` into a reliable event log**, so on restart/overflow you still must reconcile.

### Idempotency with Databases

If an input artifact has `artifactId` and `version`, use them as a unique key in processing-state storage. For example, a `processed_files` table with a unique key on the identity/version pair; a transaction writes both business data and the processed marker if permitted in the same storage. That way, reprocessing duplicate notifications does not generate duplicate invoices or dispatch the same job twice. When performing side effects outside the database (sending email, payments), add an appropriate outbox/idempotency protocol rather than relying solely on an in-memory Set.

## 12. Rescanning and Handling Lost-Event Scenarios

When `OVERFLOW` occurs, events may have been dropped for paths the consumer has never seen. You cannot use `event.count()` or the last event to reconstruct the list of lost paths. You must **scan the directory state** and reconcile against durable processed state.

When to rescan:

- After registering the watcher at startup, to discover pre-existing files and close the race gap between scan and registration.
- When `OVERFLOW` occurs.
- When `WatchKey.reset() == false`, a directory is recreated, or a mount changes.
- After application restart/redeploy.
- Periodically if reliability matters or the file system has event limits.

A sound sequence: **register watcher → scan current snapshot → start processing event queue → rescan as needed**. Even so, there is no absolute transactional snapshot over a mutating directory using `Files.list` and `WatchService` alone; idempotency, versioning, and re-verification are required. If every intermediate change must be preserved, use producer logs, message queues, or versioned manifests as the source of truth.

For very large directories, rescanning can be I/O-intensive: batch work, use bounded worker queues, persist processing state, avoid loading entire files onto the heap, and use streaming parsers.

## 13. How Operating Systems and File System Types Affect Behavior

| Environment | Differences to Check |
| --- | --- |
| Local Linux / Windows / macOS | Providers may use native notifications, yet modify event counts and delivery timing vary by OS, file system, editor, and write pattern. |
| Remote file systems NFS/SMB | Changes from other hosts **are not guaranteed by Java to always be detected**; caching, polling, and network latency can delay/drop events. |
| Containers / bind mounts / overlays | Native event propagation and permissions depend on mount/host/provider setup; test on the actual deployment configuration. |
| Polling-based providers | Very rapidly created-and-deleted files may go undetected; bursts of changes may be coalesced. |
| Virtual FS / custom providers | May not support `WatchService` or may have different semantics; handle `UnsupportedOperationException`/`IOException` and fall back appropriately. |

Do not try to infer "file is ready" from how fast or slow events arrive. Define the **producer protocol**, file type, consistency requirements, and recovery plan.

## 14. Common Pitfalls and Remedies

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Importing data on every `ENTRY_MODIFY`. | Duplicate records, repeated side effects. | Deduplicate and enforce version-based idempotency. |
| Looping `for` `event.count()` times. | Count is not business transaction count. | Process current state/manifest instead. |
| Reading immediately after `ENTRY_CREATE`. | File may still be mid-write. | Temp file + atomic publish or ready marker. |
| Treating unchanged file size for 1 second as "complete". | Writer may pause or overwrite same size. | Treat only as heuristic; validate/retry with deadline. |
| Ignoring `OVERFLOW`. | Silent event loss without recovery. | Full rescan/reconciliation. |
| Forgetting `WatchKey.reset()`. | Key is not re-armed properly for subsequent events. | Reset every batch and check boolean return. |
| Using the watcher thread to parse GB-sized files. | Backlog growth, higher overflow risk. | Offload to bounded workers; stream files. |
| Casting `OVERFLOW.context()` to `Path`. | Wrong context, possible error. | Branch on kind before reading context. |
| Watching parent directory and assuming it is recursive. | Misses files in subdirectories. | Register each directory individually. |
| Relying solely on event queue to recover after restart. | `WatchService` has no durable replay. | Startup scan + durable processed state. |
| Using atomic rename and claiming power-loss durability. | Atomic rename differs from durability. | File sync and directory sync/recovery per OS/FS. |
| Retrying every parse error forever. | Overload, stuck pipeline. | Deadlines, backoff, quarantine, and metrics. |
| New file reuses old path, deduplicating by name. | Data versions lost. | Version/sequence/hash and idempotency. |

## 15. Real-World Application Checklist

1. Register the right directories and event kinds; convert `context()` from relative to full path properly.
2. Every `WatchKey` has `pollEvents` and `reset` called; handle invalid keys.
3. Branch on `OVERFLOW` before other events and run a full rescan.
4. Watcher thread only updates lightweight dirty state; never parse large files directly in the key-polling loop.
5. Debouncing and worker queues are bounded with backpressure.
6. Prefer producer temp file + atomic move or verifiable markers/manifests.
7. If only a size/mtime quiet period is available, always document it as a **heuristic** and enforce timeouts and validation.
8. Data formats carry version/checksum/length; handle partial data properly.
9. Idempotent ingestion based on artifact/version, not event count.
10. Implement startup/periodic reconciliation and restart handling.
11. Handle `NoSuchFileException`/`IOException`, replaced files, lost permissions, and failing writers.
12. Test burst events, partial writes, overwrites, renames, network mounts, and very short-lived files on the target OS.

### Self-Check

**1. Does `ENTRY_MODIFY` with `count() == 3` mean the producer wrote three complete records?**  
No. Count is the number of corresponding events coalesced by `WatchService`, not a record count.

**2. Why is receiving `ENTRY_CREATE` not enough to parse JSON?**  
The producer may have just created the file and still be writing, so the JSON is incomplete.

**3. Can `OVERFLOW` be ignored if the last event was processed?**  
No. Other files may have changed without remaining events; you must rescan.

**4. Does a fixed 500 ms debounce guarantee excluding incomplete files?**  
No. The producer may pause longer or rewrite the same size; this is only a heuristic.

**5. What is a good cooperative pattern when you control the producer?**  
Write a temp file, close/validate, and publish via same-filesystem atomic move or a manifest/ready marker with a clear contract.

**6. Why is idempotency still needed after atomic publication?**  
Watchers still experience duplicates/coalescing/overflow/restarts; consumers may retry the same artifact/version.

**7. Does a `WatchService` provide exactly-once delivery and durable replay?**  
No. Business guarantees require durable transactions/state or an event log/message broker.

## Official Sources

- [Java SE 21 — WatchService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): platform dependency, `OVERFLOW`, and warning about files not yet completed by writers.
- [Java SE 21 — WatchEvent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchEvent.html): `kind()`, `count()`, `context()`, and coalescing.
- [Java SE 21 — WatchKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): queue, `pollEvents()`, `reset()`.
- [Java SE 21 — Path](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html): `register` and relative paths in event context.
- [Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): `move` with `ATOMIC_MOVE` and atomicity limits.
- [Oracle Java Tutorials — Watching a Directory for Changes](https://docs.oracle.com/en/java/javase/tutorial/essential/io/notification.html): directory-watching model and `WatchKey` processing loop (original guide uses JDK 8).

**Conclusion:** `WatchService` is an **observation signal**, not a transaction-commit signal. Handle duplicates/coalescing via deduplication + idempotency, recover from `OVERFLOW` via rescanning, and confirm file completion via an appropriate publishing protocol. When no producer protocol is available, debouncing/metadata checks are only best-effort bounded strategies rather than absolute guarantees.

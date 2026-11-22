# ENTRY_CREATE, ENTRY_DELETE, and ENTRY_MODIFY: Watching File Changes with Java NIO.2

## 1. Goal of This Lesson

When you need to detect when a new file is created, an old file is deleted, or a file's contents are modified, Java NIO.2 provides **`WatchService`**. This mechanism monitors changes to **entries in a registered directory**, and delivers notifications via `WatchKey` and `WatchEvent`.

The three most common events are defined in `java.nio.file.StandardWatchEventKinds`:

- **`ENTRY_CREATE`**: a new entry appears in the watched directory.
- **`ENTRY_DELETE`**: an entry disappears from the watched directory.
- **`ENTRY_MODIFY`**: an entry in the directory is observed as having changed.

This lesson explains the meaning and limitations of each kind, how to register and process events with the proper lifecycle, a runnable Java 17+ example, and common pitfalls such as missed events, missing subdirectory registrations, and reading a file while a writer is still writing.

**Core idea:** `WatchService` is a *change-notification mechanism*, **not a transaction log capable of recording every single change completely**. When an application needs accurate data state, use events as signals to **inspect actual file state** and reconcile against a snapshot/index.

## 2. Components in a Processing Flow

| Component | Role |
| --- | --- |
| `FileSystems.getDefault().newWatchService()` | Creates a service to receive file system events |
| `Path.register(watchService, kinds...)` | Registers a directory with the event kinds to watch |
| `WatchKey` | Represents a registration; gets signalled when events occur |
| `WatchService.take()` | Waits for a signalled key, potentially blocking the thread |
| `WatchService.poll()` / `poll(timeout, unit)` | Retrieves a key immediately or waits with a time limit |
| `WatchKey.pollEvents()` | Retrieves the list of accumulated events for the registration |
| `WatchEvent.kind()` | Event kind: CREATE / DELETE / MODIFY / OVERFLOW |
| `WatchEvent.context()` | Entry context; for the three standard events, a relative `Path` |
| `WatchEvent.count()` | Number of times an event has been accumulated per provider behavior |
| `WatchKey.reset()` | After processing finishes, allows the key to be signalled again; returns `false` if no longer valid |
| `WatchKey.cancel()` | Cancels the registration |
| `WatchService.close()` | Releases the service, waking waiting threads with a closed-service exception |

A basic declaration example:

~~~java
Path directory = Path.of("data");
try (WatchService watcher =
             directory.getFileSystem().newWatchService()) {
    WatchKey key = directory.register(
            watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
    // The loop for receiving and processing events goes here.
}
~~~

This is an **illustrative snippet**, not a complete program; NIO classes must be imported and the three constants in `StandardWatchEventKinds` static-imported. The directory must exist, and the provider must support the watching mechanism.

Why does the example use `directory.getFileSystem().newWatchService()` instead of always using `FileSystems.getDefault()`? Because `Path` may belong to a different `FileSystem`/provider. Creating the service from the same file system avoids pairing a `Path` with a watcher from an incompatible provider. On some virtual providers, watch service may not be supported; you must handle `UnsupportedOperationException` or corresponding errors.

## 3. ENTRY_CREATE: A New Entry Appears

`ENTRY_CREATE` is reported when the provider observes that a new entry appears **directly** in the registered directory. The entry may be a file, subdirectory, or other entry type supported by the provider.

Operations that can trigger `ENTRY_CREATE`:

- `Files.createFile(folder.resolve("a.txt"))` creates a new file.
- `Files.createDirectory(folder.resolve("child"))` creates a subdirectory.
- Another program creates a file or moves/renames an entry **into** the watched directory.

Example of a new entry:

~~~text
Before: watched/
              notes.txt
After:  watched/
              notes.txt
              report.csv   <-- ENTRY_CREATE for report.csv
~~~

For a `WatchEvent<Path>` of a standard event, `event.context()` is usually a path **relative to the registered directory**, e.g., `Path.of("report.csv")`, not the full path. To construct the path to inspect:

~~~java
Path changed = directory.resolve(relativeName).normalize();
~~~

This is **illustrative code**, assuming `directory` is the registered directory and `relativeName` is a valid context `Path`. If you need to guard against suspicious paths in sensitive systems, validate scope before reading and account for symbolic links/races during access.

**A CREATE does not prove the file has finished being written.** A writer may create the filename first, then stream many MB of content into it. The watcher sees the new entry while the file is still empty or incomplete. If you need to receive only complete files, the producer can write to a temporary file, close/flush as required, and then rename to the official name; the receiver waits for the official name to appear and validates size, checksum, or a completion marker.

Renaming an entry **into** the directory may be reported as CREATE. This is a notification about an entry change, not a claim that the file's contents were created from scratch.

Per the Java SE 17 `StandardWatchEventKinds` contract, `count()` for an `ENTRY_CREATE` event is 1; multiple creation operations may generate separate events, yet the event list still must not be treated as an immutable history in all situations (since the provider can lose events and emit `OVERFLOW`).

## 4. ENTRY_DELETE: An Entry Is No Longer in the Directory

`ENTRY_DELETE` is reported when an entry is removed from the watched directory. The cause may be:

- `Files.delete(file)` or another application deletes the entry.
- The entry is **moved out of** the watched directory.
- The entry's name changes in a way the provider reports as deleting the old name and creating the new name.

Example:

~~~text
Before: watched/
              old.log
              config.yml
After:  watched/
              config.yml
          <-- ENTRY_DELETE for old.log
~~~

A DELETE **does not necessarily prove physical data was permanently deleted**. The file may have been moved elsewhere, or a process may still hold an open handle depending on the operating system. The event only states that the name/entry in the watched directory disappeared as observed by the watcher.

At the time of receiving a DELETE event, calling `Files.readString(changed)` usually makes no sense: the path may not exist. Between receiving the event and checking, an entry with the same name might also **have been recreated**; this must be treated as current state, not proof of a sequential history of the same file object.

An application managing an index needs to handle cases where a file is deleted and rapidly recreated, or events arrive late: it should reconcile the directory listing and necessary identity/metadata rather than deleting business data solely based on a single notification.

Per Java SE 17, `count()` for an `ENTRY_DELETE` event is 1. If changes happen too quickly or the provider is overloaded, events may not be observed completely; see the `OVERFLOW` and reconciliation sections.

## 5. ENTRY_MODIFY: Entry Changed, Not Synonymous with "Finished Writing"

`ENTRY_MODIFY` is reported when the provider observes that an entry has changed. Changes can stem from content updates, metadata updates, editor save operations, or other behaviors depending on the provider/file system.

Example:

~~~text
Initial report.csv:
id,total
1,100

After a write:
id,total
1,200

The watcher may report ENTRY_MODIFY for report.csv.
~~~

Limitations to remember:

1. **One save can produce multiple MODIFY events.** An editor may write in parts, truncate, fsync, update metadata, or write a temp file/rename; the watcher may emit multiple events for a single user-level "Save" action.
2. **Multiple changes may be coalesced into one event**, with `event.count() > 1`. Java SE 17 documentation allows `count()` of `ENTRY_MODIFY` to be 1 or greater.
3. **Receiving MODIFY does not guarantee the writer has finished**. Do not read immediately and assume the data is complete. Reading a snapshot mid-write may yield an empty or partially written file.
4. **No before/after payload.** `WatchEvent` does not carry old content, new content, or a diff. To know what changed, the application must read/compare current state itself.
5. **Do not treat every MODIFY as business-meaningful.** Some applications update metadata or rewrite identical content; compare size, timestamp, hash, or actual data if filtering is needed.
6. **Do not use `count()` as an exact business write count.** Count only reflects how the provider coalesced notifications, not the number of transactions or `Files.write` calls.

A strategy upon receiving MODIFY:

~~~text
ENTRY_MODIFY
     ↓
Add path to "dirty paths" queue (deduplicating set)
     ↓
Wait for a debounce interval / confirm producer has finished
     ↓
Read new data with error and size checks
     ↓
Compare version/checksum and update index
~~~

Debouncing only reduces duplicate processing and increases the chance of stable data; **it does not prove the file has finished being written**. When stronger guarantees are required, coordinate with the producer using atomic rename where supported, completion markers, or a locking/versioning protocol.

## 6. Complete Java 17+ Example: Creating, Modifying, and Deleting a File

The following example creates a new temporary directory, registers a watcher for all three event kinds, and then performs sequentially:

1. Create `sample.txt` and wait for `ENTRY_CREATE`.
2. Write new content to that same file and wait for `ENTRY_MODIFY`.
3. Delete the file and wait for `ENTRY_DELETE`.

The example uses `poll(timeout, unit)` with a 5-second limit per event kind to avoid hanging indefinitely if the provider does not report events as expected. It **does not** assume one operation produces strictly one event; the `await` method filters by kind and name, skipping unrelated secondary events at each step. Skipping like this is only appropriate for a demo; production programs must handle all relevant events.

Save file **`WatchKindsDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

import static java.nio.file.StandardWatchEventKinds.*;

public class WatchKindsDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-kinds-");
        Path file = directory.resolve("sample.txt");
        try (WatchService watcher = directory.getFileSystem().newWatchService()) {
            directory.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
            System.out.println("Watching sample.txt");

            Files.writeString(file, "first", StandardOpenOption.CREATE_NEW);
            await(watcher, ENTRY_CREATE, file.getFileName());

            Files.writeString(file, "second",
                    StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            await(watcher, ENTRY_MODIFY, file.getFileName());

            Files.delete(file);
            await(watcher, ENTRY_DELETE, file.getFileName());
        } finally {
            if (Files.exists(file)) Files.delete(file);
            Files.delete(directory);
        }
    }

    private static void await(WatchService watcher, WatchEvent.Kind<Path> wanted,
                              Path filename) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (true) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                throw new IOException("Timed out waiting for " + wanted.name());
            }
            WatchKey key = watcher.poll(remaining, TimeUnit.NANOSECONDS);
            if (key == null) throw new IOException("Timed out waiting for " + wanted.name());
            boolean matched = false;
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == OVERFLOW) {
                    throw new IOException("WatchService overflow; rescan needed");
                }
                if (event.kind() == wanted && filename.equals(event.context())) {
                    matched = true;
                }
            }
            if (!key.reset()) throw new IOException("Watched directory unavailable");
            if (matched) {
                System.out.println(wanted.name() + ": " + filename);
                return;
            }
        }
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac WatchKindsDemo.java
java WatchKindsDemo
~~~

**Output observed when compiled and run on a test environment supporting WatchService:**

~~~text
Watching sample.txt
ENTRY_CREATE: sample.txt
ENTRY_MODIFY: sample.txt
ENTRY_DELETE: sample.txt
~~~

The lines above are **verified results on a test system**, not a guarantee that all operating systems/file systems emit events in the exact same way within 5 seconds. If a provider does not support an event or delivers it slowly, the program may end with a timeout `IOException` instead of printing all three lines; real-world applications must define retry/reconciliation policies.

**Key points in the code:**

- `Path directory` is the registered directory; `file.getFileName()` is the relative name used to match `event.context()`.
- `Files.writeString(..., CREATE_NEW)` creates a new entry; the next write on the same file requests `TRUNCATE_EXISTING, WRITE`; the third operation deletes the entry.
- `watcher.poll(timeout, NANOSECONDS)` waits for events with a timeout; `null` means the time expired without a ready key.
- `WatchKey.pollEvents()` provides the events for this processing round. `OVERFLOW` can appear even when not registered; when encountered, the demo stops to avoid treating the event sequence as complete.
- `key.reset()` is **mandatory** after processing the batch so the key can signal again. Returning `false` means the key is no longer valid; the example throws an error rather than waiting forever.
- `try-with-resources` closes the `WatchService`; the `finally` block cleans up the temporary file and directory. The code runs on its own data so it does not touch user directories.
- Watching the three operations **sequentially** reduces the risk of event coalescing making the demo hard to observe. However, extra events, observed order, and delivery timing still depend on the provider.
- The `await` method intentionally looks for one matching event; in real systems you cannot ignore other events like this because important changes could be missed.

## 7. A Long-Running Watcher Loop

In a continuously running system, one thread typically consumes events and forwards work to a queue. The proper sequence:

1. Create a `WatchService` with the appropriate file system.
2. Register an existing **directory** with the event kinds to watch.
3. Call `take()` (blocks until a key arrives) or `poll(timeout, ...)`.
4. Iterate over **all** of `key.pollEvents()`.
5. Branch on `event.kind()`; if `OVERFLOW`, mark a reconciliation scan as needed.
6. For `ENTRY_CREATE`/`ENTRY_DELETE`/`ENTRY_MODIFY`, retrieve context and resolve it against the directory corresponding to the key.
7. Enqueue the change onto an appropriate processing queue, avoiding heavy work on the watcher thread.
8. Call `key.reset()` **after iterating through the batch**. If `false`, remove the registration from the registry and handle the directory disappearing/becoming inaccessible.
9. On shutdown, close the service and stop the thread according to a defined cancellation protocol.

An illustrative loop snippet, **not a standalone program**:

~~~java
while (running) {
    WatchKey key = watcher.take();
    Path watched = (Path) key.watchable();

    for (WatchEvent<?> event : key.pollEvents()) {
        WatchEvent.Kind<?> kind = event.kind();
        if (kind == OVERFLOW) {
            scheduleFullRescan(watched);
            continue;
        }
        if (kind == ENTRY_CREATE || kind == ENTRY_DELETE || kind == ENTRY_MODIFY) {
            Path relative = (Path) event.context();
            Path absolute = watched.resolve(relative);
            enqueueChange(kind, absolute, event.count());
        }
    }
    if (!key.reset()) {
        onRegistrationInvalid(watched);
    }
}
~~~

Assumes variables `running`, `watcher`, and methods `scheduleFullRescan`, `enqueueChange`, `onRegistrationInvalid` are owned by the program; required imports come from `java.nio.file`. This snippet presents the flow, **not a program to copy and compile standalone**.

**Why check `OVERFLOW` before casting context?** Because `OVERFLOW` has type `Kind<Object>` and its context is implementation-specific and may be `null`. Do not cast all `WatchEvent<?>.context()` values directly to `Path` before classifying.

**Why must you reset after processing?** By API contract, a signalled `WatchKey` needs to be reset to be able to signal again. Without resetting, the thread may process the first batch and then fail to receive subsequent changes as expected.

If `key.reset()` returns `false`, the watched directory may have been deleted, become inaccessible, or the registration was cancelled. Do not reset repeatedly hoping the key will revive on its own; update state, drop the key, or re-register the directory when conditions allow.

## 8. WatchKey Mechanism, Reset, and Coalescing

`WatchService` does not place "one key in the queue per event". Each registration has one `WatchKey`; it is *signalled* when an event occurs and placed into the queue if not already in the signalled state. Multiple events can accumulate on the same key before the consumer retrieves it.

Diagram:

~~~text
Watchable directory
        │ create/modify/delete
        ▼
WatchService records events for WatchKey
        │ signal / queue key if not yet signalled
        ▼
watcher.take() or watcher.poll()
        │
        ▼
key.pollEvents() → [event1, event2, ...]
        │
        └── processing done → key.reset()
                             │
                             ├── true: ready to receive next rounds of events
                             └── false: registration no longer valid
~~~

Points to remember:

- `pollEvents()` may supply multiple events with the same name/kind or **coalesced** events. For `ENTRY_MODIFY`, `event.count()` can be greater than 1.
- `WatchService` may accumulate events faster than the consumer can process them; implementations are allowed to bound the queue and report `OVERFLOW` when known events have been dropped.
- `WatchEvent.count()` is not a timestamp, version, byte count, or transaction sequence number.
- A reported event does not lock the file. While the consumer is processing, the file may be modified or deleted again. The invariant "the event says the file currently still exists" **is not guaranteed**.
- Even when `OVERFLOW` is not seen, due to platform differences and I/O conditions, you should not design business logic requiring a complete event log relying solely on `WatchService`.

## 9. Distinguishing the Three Events on Rename and Move

Standard `WatchService` only specifies `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, and `OVERFLOW`; **there is no separate rename event in `StandardWatchEventKinds`**.

A rename/move operation may be reflected by entry changes:

| Operation | Observable events |
| --- | --- |
| Creating `new.txt` in the watched directory | `ENTRY_CREATE new.txt`; may include additional MODIFY during write |
| Deleting `old.txt` | `ENTRY_DELETE old.txt` |
| Renaming `a.txt` to `b.txt` in the same directory | Typically DELETE old name and CREATE new name, though details depend on provider |
| Moving a file from outside into the watched directory | Typically CREATE for the moved-in name |
| Moving a file out of the watched directory | Typically DELETE for the moved-out name |
| Rewriting file contents via temp-file replace/rename | May produce CREATE/DELETE/MODIFY for multiple names |

Do not automatically infer from a `DELETE(old)` + `CREATE(new)` pair that it is definitely **the same file being renamed**. Two unrelated files could be deleted/created close together. If an application needs to detect moves/renames accurately, it must use appropriate file identity/metadata or native APIs/application protocols; standard `WatchEvent` does not provide a source/destination pair as a transaction.

## 10. Watching Subdirectories: Not Automatically Recursive

A common mistake: registering `root` **does not automatically** watch changes deeper in the directory tree.

~~~text
root/                  <-- watcher registered for root
  a.txt                <-- changes may be reported via root
  sub/                 <-- creation/deletion of sub itself in root may be reported via root
    nested.txt         <-- changes inside sub are not automatically reported via root
~~~

If you want recursive watching:

1. Traverse existing subdirectories and register each one.
2. When observing `ENTRY_CREATE` for a new subdirectory, check whether it is actually a directory and register a corresponding watcher.
3. Account for files/directories that appeared **before** registering the new subdirectory; scan that directory to catch changes that occurred in the gap.
4. When a directory is deleted/moved or `reset()` reports invalid, update the registry and related registrations.
5. Define policies for symlinks, mount points, access permissions, and OS registration count limits.

Checking a subdirectory with `Files.isDirectory(path)` after an event has a **race**: the entry could be deleted or replaced before the check. On large systems, combine watchers with periodic snapshots/reconciliation. Do not blindly follow all symbolic links as that can cause loops or escape the data scope.

Do not use a separate blocking thread for **each file** just to wait for events when you actually want to watch entries of the same directory. `WatchService` allows one watcher to watch multiple directory registrations, though actual cost and limits depend on the platform.

## 11. OVERFLOW: Mandatory Reconciliation Scan Case

`StandardWatchEventKinds.OVERFLOW` indicates **events may have been lost or discarded**. You **do not need to register `OVERFLOW`** to receive it; it is a special signal from `WatchService`.

If you only handle the three main events and ignore `OVERFLOW`, the internal index can permanently drift from the actual directory. A safer approach:

1. Mark the directory or subtree as **dirty / needs-reconcile**.
2. Re-read the entry list and required metadata.
3. Compare against the managed snapshot/index: detect new entries, missing entries, and entries needing content inspection.
4. Update business state via an idempotent protocol; do not assume each change is delivered only once.
5. Continue listening for events and schedule periodic scans to mitigate lost or out-of-order events.

A simple-level snapshot could be `Map<Path, Metadata>`, where `Metadata` stores size and `lastModifiedTime`. However, even those two attributes do not detect **every** change (timestamp granularity, same-size writes, metadata changes, rapid operations). If content verification is required, compute a hash or use a producer-supplied version/commit marker.

### "Snapshot First or Register First?"

An initialization problem: if you scan the directory **before** registering, files created in the gap between the two steps can be missed. Registering **first**, then scanning the snapshot and consuming events still requires handling duplicates/races between the snapshot and events.

Good pattern: register → snapshot → drain events → reconcile (or an equivalent design), with all update operations idempotent. When very high accuracy is required, a dedicated data-source contract is needed rather than `WatchService` alone.

## 12. Care When Handling Files Currently Being Written

A common sequence:

~~~text
Writer:
  create("dataset.csv")
  write chunk 1
  write chunk 2
  write chunk 3
  close()

Watcher:
  ENTRY_CREATE
  ENTRY_MODIFY
  ENTRY_MODIFY ...
~~~

The watcher may run right between chunks; if the consumer parses when only the first chunk is present, it will see incomplete CSV/JSON/ZIP data. This is not a Java-specific bug, but the difference between **an entry changed** and **a committed business data unit**.

Solutions depending on requirement level:

- **Temp file + publish rename:** the producer writes to a temporary name, validates/flushes and closes the file, then moves it to the published name. If the same file system supports `StandardCopyOption.ATOMIC_MOVE`, an atomic move can be requested; if unsupported, a fallback or error must be decided. Do not assume all renames on network FSs are atomic/durable.
- **Completion marker:** the producer writes the data, then creates a sentinel file such as `dataset.csv.done`; the watcher only submits data for processing after the marker and re-validates the data.
- **Cooperative locking:** producer and consumer agree to use file locks or another locking mechanism. File locks are OS-dependent and all parties must genuinely obey them; they do not automatically turn multiple operations into a transaction.
- **Debounce:** coalesce multiple MODIFY events during a quiet period, then check size/mtime again. This is convenient for UI file watchers but **does not guarantee completion** if the writer pauses briefly and then resumes writing.
- **Checksum/version:** data is only accepted when it meets the expected format and version; helps detect partial writes or stale state.

When DELETE is followed by CREATE with the same name, treat it as potentially a new object. Caching file contents by filename without validating version/identity easily serves stale or wrong data.

## 13. Avoiding Blocking the Event Loop and Handling Duplicates

If you use `watcher.take()` in one thread, do not let the event handler perform huge file reads, network uploads, or blocking database queries directly on that thread. If the handler is slow, the event queue backs up, increasing the likelihood of `OVERFLOW`.

Recommended architecture:

~~~text
WatchService thread
   │ take/poll → pollEvents → classify
   │
   ├── OVERFLOW ────────────> schedule full rescan
   │
   └── CREATE/DELETE/MODIFY -> dirtyPaths set / bounded task queue
                                        │
                                        ▼
                              Worker checks actual state
                                        │
                                        ▼
                              Idempotent index update
~~~

Rules:

- Worker pool and queue must be **bounded** to prevent unbounded memory growth.
- You can **deduplicate by `Path`**: multiple MODIFY events for the same path only require one final state check.
- Workers must tolerate `NoSuchFileException`: a file may vanish before being read. That is normal in asynchronous watching designs.
- A file may be modified again while a worker is reading it; rechecking version/hash after processing may be needed.
- Do not share mutable `Map`/`Set` between watcher and workers without synchronized/concurrent collections.
- If a registration key has become invalid or `WatchService` is closed, workers must not casually assume another event will arrive later to make up the state.
- Handle shutdown/interrupts: `take()` can throw `InterruptedException`, and closing the watcher causes waiting threads to throw `ClosedWatchServiceException`; stop cleanly per lifecycle.

Although `WatchService` is designed to be usable by multiple consumers, simple applications usually dedicate **one thread to own retrieving keys and resetting after batch processing**, avoiding two threads handling the same registration in hard-to-control ways. With multiple consumers, ensure `reset()` is called only after the key's events have been processed per the application's protocol.

## 14. Platform and Provider Limitations

`WatchService` uses native OS notification mechanisms when available, or another mechanism such as polling if native support is lacking. This makes behavior dependent on:

| Environment / Characteristic | What to watch out for |
| --- | --- |
| Linux, Windows, macOS | Event delivery timing, coalescing behavior, and reported metadata changes may differ |
| Network FS / cloud-synced drives | May be slow, incomplete, behave differently, or fail real-time expectations |
| ZIP FS, virtual file systems / custom providers | Do not support watching by default; creation/registration may be unsupported by the provider |
| Directory deleted, renamed, or permissions lost | Registration may become invalid; `reset() == false` |
| Very rapid continuous changes | Queue may overflow, leading to `OVERFLOW` |
| Symlinks, mounted folders | Require watching-scope policies and permission checks |
| Metadata changes | No portable contract that all metadata changes are reported uniformly via MODIFY |

Do not use `WatchService` as the **sole security audit layer** or financial calculation basis requiring every operation to be recorded accurately. In those problems, you need a reliable event log/transaction system, or authoritative database state, paired with a watcher only as an optimization to detect when synchronization is needed.

## 15. Common Exceptions and Pitfalls

| Symptom | Cause or Meaning | How to Handle |
| --- | --- | --- |
| `UnsupportedOperationException` on create/register | Provider does not support watcher or event kind | Check capabilities, fall back to polling/reconciliation, or choose another provider |
| `IOException` | Cannot open, register, or access the requested resource | Log sufficient context; check path/permissions/file system |
| `ClosedWatchServiceException` | Operation on a closed watcher or waiting thread woken by close | Terminate worker/watcher loop per lifecycle |
| `InterruptedException` on `take()/poll(timeout)` | Thread was interrupted while waiting | Execute cancellation policy and preserve interrupt status where appropriate |
| `WatchKey.reset() == false` | Registration is no longer valid | Remove from registry; consider re-registering if directory recovers |
| `OVERFLOW` | Events may have been dropped | Rescan directory and reconcile snapshot |
| `ENTRY_MODIFY` emitted multiple times | Provider may report/coalesce multiple changes | Debounce, idempotent updates, rely on actual state |
| File missing in `Files.exists()` after CREATE | File rapidly deleted/renamed or race condition | Reconcile final state; do not trust event as a snapshot |
| No events seen in subdirectories | Registration is not automatically recursive | Register subdirectories appropriately |
| Only first batch received, then stops | Forgot `key.reset()` or key invalid | Reset at the right place; check boolean return |
| Waiting forever in `take()` | No events, no shutdown, or registration error | Use timeout/close/interrupt matching requirements |
| Wrong path processed | Treated `event.context()` as an absolute path | Use `((Path) key.watchable()).resolve((Path) context)` |

**Case of a file being renamed:** `Files.exists(path)` can return false due to I/O errors, missing permissions, or broken symlinks rather than only because the file was truly deleted. If an accurate decision is needed, use attribute-reading operations with exception handling and check symbolic link policies.

## 16. Checklist for Real-World Watcher Implementation

1. **Selected the right file system/provider?** Are `Path` and `WatchService` compatible?
2. **Registered the right directory?** Do not register the "target file" when the goal is watching entries in the parent directory.
3. **Chosen the three `ENTRY_*` kinds appropriately?** If modifications are not needed, you can register only CREATE/DELETE, but you must still handle OVERFLOW.
4. **Iterated over all events in the key?** Do not stop after the first event and discard the remaining entries.
5. **Handled OVERFLOW before casting context?** `OVERFLOW` can have a null/non-`Path` context.
6. **Called reset after the batch and checked for false?** Registrations can be cancelled automatically.
7. **Aware that the watcher is not automatically recursive?** If subtree watching is needed, register each directory and perform supplemental scans when new directories appear.
8. **Controlled file readiness?** MODIFY does not prove the writer finished; CREATE also does not prove the file is ready.
9. **Implemented reconciliation?** Events are not a complete event log; snapshots/dirty paths/periodic rescans are needed.
10. **Handled races?** Files can vanish, be renamed, or continue being written before reading.
11. **Separated the watcher thread from heavy processing?** Avoids backlog/OVERFLOW.
12. **Implemented clean shutdown?** Close `WatchService`, stop workers, cancel keys, and release resources properly.

## 17. Self-Check Questions

1. What is the core difference between the three event kinds? **CREATE**: an entry appears; **DELETE**: an entry disappears; **MODIFY**: an entry is observed to change.
2. File `a.txt` is created and then written with 100 consecutive data blocks. Are you guaranteed to receive exactly 1 CREATE and 100 MODIFY events? **No**. The number of MODIFY events depends on the provider and coalescing; events can also be dropped under load.
3. Does CREATE prove the file has finished being written? **No**; the entry can appear right before the writer finishes.
4. Does MODIFY provide the new/old content? **No**; you must read current state and compare if needed.
5. Does DELETE mean the file was permanently erased? **No**; it may be a move/rename out of the directory or just removal of that name from that directory.
6. Does registering `root` automatically catch MODIFY of `root/sub/x.txt`? **No**; you must register `sub` separately or implement a system-level recursive mechanism.
7. What should you do when receiving an event with `kind() == OVERFLOW`? **Perform a reconciliation scan (rescan/reconciliation)** because events may have been lost.
8. Does `event.count() > 1` for MODIFY prove the exact number of times a user clicked Save? **No**; it only reflects events coalesced by the provider.
9. What happens if you forget `key.reset()` after `pollEvents()`? The key may not be signalled again as expected; you must reset after processing.
10. Why do `key.watchable()` and `event.context()` usually need to be combined? Because a standard entry event's context is a **relative path** with respect to the registered directory.
11. Why does rename not have its own event? `StandardWatchEventKinds` only has CREATE, DELETE, MODIFY, and OVERFLOW; a move may be reflected via old-name/new-name entry changes, depending on the platform.
12. If the watcher reports MODIFY but `Files.readString(path)` throws `NoSuchFileException`, is that an API bug? **Not necessarily**; the entry may have been deleted/renamed after the event was generated.
13. Should `WatchService` be used as the sole audit source if every change must be recorded? **No**; a dedicated event log/transaction with its own guarantees is needed.
14. Can you receive OVERFLOW even without registering for it? **Yes**; it is a special signal.
15. Why does the example use `poll` with a timeout rather than an infinite `take`? So the demo **does not hang forever** if events do not arrive in a specific environment.

## Reference API Documentation

- [Java SE 17 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): official definition of `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, and `OVERFLOW`.
- [Java SE 17 — WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): watcher mechanism, queue, take/poll, closing, and platform limitations.
- [Java SE 17 — WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents`, `reset`, `cancel`, `watchable`.
- [Java SE 17 — WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): `kind`, `context`, `count`.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `register` and path handling.
- [Java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): guide to `WatchService` and event handling.

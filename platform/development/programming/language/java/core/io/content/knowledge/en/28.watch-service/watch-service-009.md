# Platform-Dependent and Network File System Limitations When Watching Changes with WatchService

## 1. Context and Goals

Java NIO.2 provides `WatchService` (`java.nio.file.WatchService`) so applications can monitor changes in registered directories. Standard event kinds commonly used are:

- `StandardWatchEventKinds.ENTRY_CREATE`: a new entry appears in the directory.
- `StandardWatchEventKinds.ENTRY_DELETE`: an entry is deleted or no longer in the directory.
- `StandardWatchEventKinds.ENTRY_MODIFY`: an entry is recorded as having changed.
- `StandardWatchEventKinds.OVERFLOW`: the detector missed one or more events because recording/accumulation capacity was exceeded.

Key point: **`WatchService` is not a complete, guaranteed-accurate, OS-independent change log.** Detection capability, latency, ordering, and event coalescing depend on the `FileSystemProvider` implementation, operating system mechanisms, the file system itself, and where the data is stored. With NFS, SMB, or mounted network directories, applications especially need to verify whether modifications made from **another machine** are detected.

This article helps you:

1. Understand which parts of the API contract are reliable and which are platform-dependent.
2. Explain why network file shares may not deliver events completely or promptly.
3. Handle `OVERFLOW`, duplicate events, files modified mid-write, and lost registrations.
4. Combine watching with **state reconciliation**, polling/snapshots, and idempotent processing.
5. Design a runnable Java 17+ program and choose an approach suited to business requirements.

## 2. Basic Mechanism of `WatchService`

An application typically creates a service, registers a **directory**, retrieves a `WatchKey`, and processes events:

~~~java
try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
    WatchKey registration = directory.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.ENTRY_DELETE);

    while (registration.isValid()) {
        WatchKey key = watcher.take(); // Wait for a key signalled with changes.
        for (WatchEvent<?> event : key.pollEvents()) {
            System.out.println(event.kind() + ": " + event.context());
        }
        if (!key.reset()) {
            break; // Registration is no longer valid.
        }
    }
}
~~~

This is an **API illustration snippet**, not a standalone program: it needs imports from `java.nio.file`, and `directory` must be a `Path` pointing to an existing directory. Real applications typically manage multiple keys and do not assume the returned key always belongs to a single directory.

Key steps:

- `directory.register(watcher, ...)` registers the directory; `WatchKey` represents the registration.
- `watcher.take()` blocks until a key is ready; `poll()` returns immediately or `poll(timeout, unit)` waits up to a specified duration.
- `key.pollEvents()` supplies the recorded events for the key. For standard `ENTRY_*` events on a directory, `event.context()` is typically a `Path` **relative to the watched directory**.
- You must call `key.reset()` after processing; if omitted, the key may remain in the signalled state and fail to be re-queued properly.
- `reset() == false` indicates the key is no longer valid: for instance, the registration was cancelled or the object is no longer accessible. Handle subsequent steps per application policy.
- When the service closes, `take()`/`poll()` can no longer be used; waiting calls may exit with `ClosedWatchServiceException`.

**Events describe what the system recorded at one moment; they are not a guarantee that the entry's state remains unchanged when the handler runs.**

## 3. Which Parts Are Platform-Dependent?

Java defines the event kinds and API for receiving events, but allows providers to use native monitoring mechanisms or polling. Consequently, two environments running the same Java 17 code can behave differently:

| Aspect | What to Understand |
| --- | --- |
| Event delivery timing | Can be fast or slow depending on provider, system load, and monitoring mechanism |
| Number of `ENTRY_MODIFY` events | One logical change may emit one or many events; do not assume exactly one |
| Observed event ordering | Do not build business workflows assuming every environment preserves one global order |
| Detecting short-lived files | Polling systems may miss files that are created and deleted quickly |
| Queue limits | Implementations may bound pending events; use `OVERFLOW` to report event loss |
| Rename/move handling | No universal standard rename event across all providers; typically treated as entry state changes |
| Directory tree watching | Registering one directory does not automatically watch all subdirectories recursively |
| Permissions and mount status | Lost permissions, inaccessible paths, or mount changes can affect monitoring |
| Network-shared directories | Changes made on another machine **are not guaranteed by Java** to be detected |

On some platforms, the provider leverages OS features; where suitable support is missing, it may fall back to periodic scanning. Do not write production code hardcoded to a specific Linux, Windows, or macOS mechanism unless you have verified the deployment environment.

For example, creating and editing `config.yml` may emit `ENTRY_CREATE` followed by multiple `ENTRY_MODIFY` events; another environment may observe fewer events. Filename, emission timing, and event count **are not a contract proving the file has finished writing**.

## 4. Network File Systems: Special Points of Caution

### 4.1. What Are NFS/SMB in This Context?

A Java application can access `/mnt/share/data` or `Z:\shared\data` via `Path` just like a local path. However, the actual data may reside on another server, accessed over a file-sharing protocol like NFS or SMB.

**The fact that `Files.exists(path)` and `Files.readString(path)` work does not prove `WatchService` will see all changes on the share.** Those APIs only confirm the file system permits the corresponding file operations, making no guarantee about cross-machine event monitoring.

### 4.2. Changes from the Same Client vs. Another Machine

Consider three components:

~~~text
Machine A: Java WatchService registers /mnt/share/inbox
              |
              | NFS/SMB mount
              v
         Storage Server
              ^
              | file modification
              |
Machine B: application creates report.csv
~~~

At least two scenarios must be tested separately:

1. **Machine A creates/writes files itself via the mount:** A's OS or provider may detect some events caused by client A itself. Support level and reporting behavior still depend on the platform.
2. **Machine B creates/writes/deletes files on the same share:** change notifications may not propagate to A's watch mechanism. **Java does not require providers to detect changes performed by another machine.**

If A only calls `watcher.take()` and no event arrives, the program may sleep forever even though `report.csv` already exists on the server. If the business flow must process that file, relying solely on events is insufficient.

Do not assume a specific Linux/Windows version or NFS/SMB version behaves identically in every configuration. Server, client caching, mount options, permissions, and providers can all produce different results.

### 4.3. Caching and Delayed Observation of Data

Network file systems commonly cache metadata or contents to reduce round-trips. Consequently, when a client sees an event or calls `Files.size`, `Files.getLastModifiedTime`, or `Files.readAllBytes`, the moment data/metadata becomes visible may differ from when the other machine wrote it.

Consequences:

- A single state read is not a transactional snapshot of the entire share.
- An `ENTRY_MODIFY` event does not prove the author closed the file or the data is stable.
- Comparing only `lastModifiedTime` can miss changes if timestamp granularity is coarse, times are rounded, or two writes yield the same observable metadata.
- A file may be replaced between check and open; handle I/O errors and verify consistency per business requirements.

Solutions depend entirely on requirements: checksums, size/mtime, versions or manifests, a "write temp file then publish" protocol, and producer-side confirmations.

## 5. `WatchService` Is Not a Guaranteed Mechanism to Detect Every Change

### 5.1. Events Can Be Coalesced or Repeated

If an application writes a file across multiple calls, do not equate "number of `ENTRY_MODIFY` events" with the number of completed file versions. Events can be coalesced or fire multiple times for a single write process.

**Good pattern:** use events as reminders to "inspect this entry", then read current state. Handlers must be idempotent: reprocessing the same file causes no unintended duplicate side effects.

### 5.2. `OVERFLOW` Is an Event-Data Loss Signal

The OS/provider may emit events faster than the application drains them. If the implementation knows it discarded some events, `WatchService` can place `OVERFLOW` into the key's event list.

~~~java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // Cannot know completely which files changed.
        // Mark directory to rescan current state.
        needsReconcile = true;
        continue;
    }

    Path changedName = (Path) event.context();
    Path changedPath = watchedDir.resolve(changedName);
    // Check actual state of changedPath; avoid blind processing.
}
~~~

This illustrates logic, requiring `key`, `watchedDir`, and `needsReconcile` to be declared. Do not assume `OVERFLOW` has a specific filename as its context. When overflow occurs, **you cannot reconstruct full history from remaining events alone**; you must run a directory reconciliation scan or consult a data source with reliable history.

### 5.3. Registrations Can Become Invalid

If a directory is deleted, permissions change, or the file system loses accessibility, `WatchKey` can be invalidated. Always check the result of `reset()`:

~~~java
boolean valid = key.reset();
if (!valid) {
    // Stop trusting the old registration.
    // Log the error and consider re-registering when the directory is ready.
}
~~~

Also do not assume a replaced mount always invalidates the key immediately. If a critical path points to a new mount while the old watch still appears valid to the provider, the application still needs state detection/reconciliation beyond events.

### 5.4. Registration Is Not Retroactive and Does Not Auto-Snapshot

`WatchService` does not automatically emit events for files already present in the directory at registration time. If `inbox` already holds 1,000 files before the application starts, do not wait for `ENTRY_CREATE` to process them.

Furthermore, between taking a snapshot and registering, a change can slip through if ordered wrongly. For systems needing maximum detection:

1. Register the watch if the provider supports it.
2. Scan actual state to establish a baseline and discover pre-existing files.
3. Continue processing events and rescanning periodically.
4. Accept duplicate events and **filter via idempotency/state**.

This shrinks the detection gap, yet **does not turn `WatchService` into a lossless event log**.

## 6. Standalone Java 17+ Example: Seeing the Difference Between Events and Actual State

The following program creates a temporary directory, registers watching, creates `report.txt` itself, waits up to two seconds to read events, and then directly verifies file existence and content. It intentionally **does not claim `ENTRY_CREATE` is always received**: that depends on the provider and environment.

Save as **`WatchServicePlatformDemo.java`**:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

public class WatchServicePlatformDemo {

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-platform-");
        Path file = directory.resolve("report.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                directory.register(
                        watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                // Create file after registration. Still do not assume
                // the provider must emit a fixed set of events.
                Files.writeString(
                        file, "ready", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW);

                WatchKey key = watcher.poll(2, TimeUnit.SECONDS);
                boolean sawCreate = false;
                boolean sawOverflow = false;

                if (key != null) {
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            sawOverflow = true;
                            continue;
                        }

                        Object context = event.context();
                        if (event.kind()
                                == StandardWatchEventKinds.ENTRY_CREATE
                                && file.getFileName().equals(context)) {
                            sawCreate = true;
                        }
                    }
                    if (!key.reset()) {
                        System.out.println("Watch key invalid");
                    }
                }

                boolean present = Files.isRegularFile(file);
                boolean correctContent = present
                        && "ready".equals(Files.readString(
                                file, StandardCharsets.UTF_8));

                System.out.println("Saw CREATE event: " + sawCreate);
                System.out.println("Saw OVERFLOW event: " + sawOverflow);
                System.out.println("Snapshot confirms file: "
                        + correctContent);
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 WatchServicePlatformDemo.java
java WatchServicePlatformDemo
~~~

**One possible result** on a local file system supporting monitoring:

~~~text
Saw CREATE event: true
Saw OVERFLOW event: false
Snapshot confirms file: true
~~~

**If the provider has not emitted an event within two seconds**, the first line may instead be:

~~~text
Saw CREATE event: false
Saw OVERFLOW event: false
Snapshot confirms file: true
~~~

These are two **illustrative sample outputs**, not a guarantee of identical stdout on every system. If the key is invalidated, the program may also print `Watch key invalid`. If `newWatchService` or `register` is unsupported or an I/O error occurs, the program may throw an exception; production applications must catch it and switch to an appropriate fallback strategy.

### Why Is the Example Written This Way?

1. `directory.register(...)` happens **before** creating `report.txt`; thus the demo does not depend on a retroactive event for an already existing file.
2. `watcher.poll(2, SECONDS)` waits with a bound; returning `null` means **no key was ready during the wait**, not proof that the directory did not change.
3. `event.kind()` is compared to `ENTRY_CREATE`, without assuming which exact events occur from a single `Files.writeString`.
4. `event.context()` is compared with `file.getFileName()`, which is the entry's relative name in the watched directory. There is no need to resolve an absolute path when comparing names alone.
5. `OVERFLOW` is checked separately because it cannot be handled like an ordinary file event.
6. `key.reset()` is called after retrieving events; if invalid, the application must examine the registration status.
7. `Files.isRegularFile` and `Files.readString` **verify actual state** instead of guessing from whether an event arrived. Even without `ENTRY_CREATE`, the snapshot still sees the file the program itself just created.
8. `try-with-resources` closes the watcher before deleting the temporary directory; cleanup is not meant to demonstrate remote-machine sync.

**Demo limitation:** the program reads only **one** key and one batch of events over a short window; it is neither a continuous watch loop nor a test covering NFS/SMB. To evaluate a network file system, run the watcher on machine A and create/modify/delete files from machine B in a dedicated scenario.

## 7. Stronger Design: Events Are Signals, Snapshots Are State

A system processing files in `inbox` should not depend on receiving strictly one event per file. You can use this architecture:

~~~text
                +----------------------+
WatchService -->| Mark path "dirty"    |----+
                +----------------------+    |
                                             v
Scheduled scan ------------------------> Reconciler
                                             |
                                             v
                                   File state snapshot
                                             |
                                             v
                                   Compare processed state
                                             |
                                  +----------+-----------+
                                  |                      |
                              New/changed            Unchanged
                                  |                      |
                         Idempotent process            Skip
                                  |
                           Save checkpoint
~~~

### 7.1. What Is Reconciliation?

**Reconciliation** is the operation of reading existing file state, comparing it against known state, and processing necessary differences. It does not need to know the entire sequence of past events; it determines **what is currently present or differs from the previous observation**.

A simple snapshot example may include:

| Attribute | Purpose | Limitations |
| --- | --- | --- |
| Name / relative path | Identifies path within the watched directory | Renamed/copied files can change identity |
| `Files.size` | Filters files whose byte length changed | Two different contents can share the same size |
| `lastModifiedTime` | Hints at updates | Timestamp resolution/caching can miss changes |
| Content hash (when needed) | Distinguishes contents with identical size/mtime | Costs reading all bytes and CPU; can hit files mid-change |
| Producer version ID/manifest | Identifies published version | Requires coordinated design with producer |
| Processing checkpoint | Prevents re-running completed side effects | Must be persisted durably with safe update mechanics |

**Note on snapshots:** scanning a directory with `DirectoryStream` or `Files.list` does not automatically provide an atomic snapshot; files can disappear/change between listing and opening. A reconciler must tolerate `NoSuchFileException`, `AccessDeniedException`, and transient network errors.

### 7.2. Simple Reconciliation Scan Pattern

~~~java
try (var entries = Files.list(inboxDirectory)) {
    for (Path candidate : entries.toList()) {
        if (!Files.isRegularFile(candidate)) {
            continue;
        }

        long size;
        try {
            size = Files.size(candidate);
        } catch (IOException transientFailure) {
            // File may have just been deleted or share temporarily unreachable.
            continue;
        }

        // Compare metadata/hash/manifest against checkpoint.
        // If a new version is ready, process idempotently.
        // Checkpoint only after business processing succeeds.
    }
}
~~~

This is an **illustrative snippet**, using a declared `inboxDirectory` and imports for `java.nio.file.Files`, `Path`, and `IOException`; it does not run standalone. For huge directories, avoid `toList()` if RAM must be bounded; iterate the stream while open or use `DirectoryStream`. On network shares, every metadata call also incurs network cost; limit frequency and concurrency.

### 7.3. Combining Watchdog Events with Fallback Polling

A realistic operating cycle:

1. On startup, attempt to register `WatchService` and perform an initial **full scan**.
2. Upon receiving `ENTRY_CREATE`/`ENTRY_MODIFY`/`ENTRY_DELETE`, mark the path/directory for inspection; do not assume events contain final state.
3. Upon receiving `OVERFLOW`, mark a **full rescan** because the event stream lost completeness.
4. Even without events, run **scheduled reconciliation** after an appropriate interval—especially important for network mounts.
5. If watching is unsupported, cancelled, or fails, keep operating via **polling** with monitoring/alerts; retry registration when appropriate.
6. After finishing a file or version, persist a durable checkpoint; prevent duplicates when additional events arrive or the app restarts.

**Polling frequency** is a trade-off based on SLA and cost: scanning every second can overload a share with millions of files; scanning every few minutes may be too slow if fast reaction is required. Use batching, directory partitioning, indexes/manifests, or producer notifications at scale.

## 8. "File Changed" Does Not Mean "File Finished Writing"

This is a major risk for both local and remote watches. When the observer receives `ENTRY_CREATE` or `ENTRY_MODIFY`, the producer may still be writing a 5 GiB file.

If the consumer processes immediately, it may read an incomplete file, fail parsing, or hash shifting data. Better coordination approaches:

### 8.1. Write Temporary File Then Publish

The producer writes to `report.csv.part`, syncs/closes as needed, and then publishes by renaming to `report.csv` **if appropriate move/rename is supported on the same file system**. The consumer only processes complete names. On network file systems, rename atomicity and visibility depend on the provider and system; do not assume every move is atomic.

If atomic move is required, Java supports `StandardCopyOption.ATOMIC_MOVE`, which may throw `AtomicMoveNotSupportedException`; the application needs an explicit fallback strategy. The system must verify actual deployment support on the share.

### 8.2. Completion Manifest or Marker

The producer writes the data, then creates a marker file `report.csv.done` or a manifest record containing name, size, hash, and version. The consumer processes only when the marker and data match.

This approach still requires defining **publication order**, sync checks, and handling cases where the marker becomes visible before all clients see the data due to network caching. When high reliability is required, use a message-distribution service or transactional database instead of inferring completion solely from file events.

### 8.3. "Wait for File Stability" Is a Heuristic

Some applications wait until `size`/`mtime` stays unchanged across several scans before processing. This is only a **guess**: the producer might pause briefly and then keep writing. Do not use it as proof of completion when business logic demands certainty.

## 9. Directory Watching and Recursion Limits

`Path.register(watcher, ...)` on one directory does not automatically register **the entire subtree**. To monitor `root/a/` and `root/b/`, you generally must register each subdirectory of interest.

Issues when new directories appear:

1. Receive `ENTRY_CREATE` for an entry in the parent.
2. Check whether that entry is actually a directory; it may vanish before the check.
3. If continued monitoring is desired, register the new directory.
4. **Immediately scan the contents of the newly registered directory**, because files inside may have been created before registration completed.

For multi-directory trees or network shares, registration counts, depth, permission changes, symlinks, and traversal errors must all be bounded. **Do not automatically follow symbolic links** to directories outside the permitted scope without an explicit policy; there is a risk of cycles or scanning outside the trusted area.

Some file system providers may support custom modifiers, but Java SE 17 **does not define a standard recursive modifier across all platforms**. Avoid relying on internal APIs just because a development environment happens to support them.

## 10. Failure Modes Commonly Seen on Network Shares

| Scenario | Symptom | How to Handle |
| --- | --- | --- |
| Machine B creates file, Machine A gets no `ENTRY_CREATE` | Consumer never processes if watcher-only | Periodic full scan, producer notification, or event bus |
| Events arrive slowly | Higher-than-expected processing latency | Measure actual latency; apply polling/notification per SLA |
| Client metadata cache | Snapshot from A lags behind what B just published | Bounded retries, manifest/versioning, consistency checks |
| Share temporarily disconnects | `IOException`, files unreachable, keys may go invalid | Health checks, backoff, reconnect, re-register/rescan |
| Mount is replaced | Watch may stay tied to old object or unexpected state | Monitor mount/file store and reconcile; reinitialize watcher if needed |
| File created and deleted very quickly | Polling never sees the file existed | If full operation history is required, use guaranteed source logs/events |
| Too many files change | `OVERFLOW`, queue overflow, or slow processing | Full rescan, load limiting, processing optimization |
| Producer writes in chunks | Consumer reads incomplete file | Publish protocol with temp files/markers/versions |
| Rename/move | Observes delete/create or varying events | Rely on actual state and business identifiers |
| Same mtime across two versions | Missed updates if comparing timestamps alone | Combine size/hash/version/manifest |
| One event processed multiple times | Duplicate records, duplicate notifications | Idempotency and durable checkpoints |

**No pure snapshot-polling approach can reconstruct the complete history of files that appeared and disappeared between two scans.** If "seeing every past create/delete operation" is required, you must use a mechanism designed as an event log/audit at the source of changes.

## 11. Testing Support Capabilities Before Production

A smoke test that creates files inside the same JVM on the watcher host is **not enough** to conclude NFS/SMB works properly. Test along a matrix:

| Operation Source | Operations to Test | What to Measure |
| --- | --- | --- |
| Same process/host as watcher | Create, modify, delete | Whether events arrive, how many, latency |
| Another machine on same mount/share | Create, modify, delete, rename | Whether detected at all or only via snapshot |
| Large data / slow writes | Multi-chunk writes, close/rename | When events fire; whether consumer reads prematurely |
| Burst of thousands of files | Rapid create/modify | `OVERFLOW` occurrence, lost events, full scan time |
| Short-lived files | Very rapid create then delete | Whether missed |
| Connection interruption | Network disconnect/reconnect, remount | Whether `WatchKey` stays valid, when re-registration is needed |
| Startup/restart | Files present before registration | Whether initial scan detects them and avoids duplicates |
| Permission changes / directory moves | Permission denied, missing directory | Errors and recovery capability |

**Measure meaningful metrics:** detection rate of published files, latency from "ready" to processing, `OVERFLOW` count, rescan count, rescan completion time, I/O errors, backlog depth, and CPU/I/O on the file server.

An implementation can look great in a 10-file test yet fail in production with 100,000 files or network drops. Tests must use the actual mount type, options, permissions, Java version, and realistic load.

## 12. Concurrency Management and Safe Lifecycle

### 12.1. Do Not Block the Event-Receiving Thread with Heavy Processing

If the watcher directly reads/parses GiBs before calling `reset()`, the event queue can back up. A better design:

- The watch thread only receives keys, forwards paths/directories to a **bounded** queue, or marks dirty flags.
- Workers/reconcilers perform I/O, validation, parsing, and business logic.
- Duplicate paths are coalesced to reduce load; when queues grow too large, prioritize controlled rescans.
- Track pending items and wait times so backpressure never turns into unbounded memory growth.

### 12.2. Terminating Properly

Use `try-with-resources` to close `WatchService`. If another thread calls `close()` while `take()` is waiting, the waiting thread may receive `ClosedWatchServiceException`; that can be an intentional stop signal.

With `watcher.take()`, the thread can also receive `InterruptedException`; restore interrupt status if not rethrowing:

~~~java
try {
    WatchKey key = watcher.take();
    // Process key.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Stop monitoring loop per application policy.
}
~~~

This is an illustrative snippet where `watcher` is already created and `WatchKey` imported. Do not call `reset()` carelessly before finishing the event batch, and do not let a handler exception silently terminate the entire watch loop forever without notice.

### 12.3. Paths and Directory Safety

`WatchEvent.context()` holds the relative path of an entry inside the registered directory, yet file system state can change after the event appears. Before opening a file, verify scope, permissions, and object type. When the watched area is controlled by untrusted actors, account for symbolic links, file replacement, and TOCTOU (time-of-check to time-of-use) risks.

`watchedDir.resolve((Path) event.context())` only **constructs a path**; it does not guarantee the entry still exists or still points to the original object. On network shares especially, handling access failures is a normal execution path.

## 13. When to Use Plain `WatchService` vs. Other Approaches?

### Plain `WatchService` (with `OVERFLOW` handling) Can Suffice If

- The application mainly needs to **refresh UI** or caches when a local directory changes.
- Missing a few notifications is acceptable and the app can re-check state when needed.
- Recording a history of every past creation/deletion is not required.
- The file system and provider behavior have been tested at appropriate scale.

Even here, include a refresh mechanism on application startup and when keys become invalid.

### `WatchService` + Polling/Reconciliation Should Be Used If

- Watching a **network share** or any storage where remote events are not proven reliable.
- The application must detect new files after restarts or temporary disconnections.
- One file can emit multiple events or large bursts occur.
- Self-recovery after `OVERFLOW`, remounts, and I/O errors is needed.
- Correctness depends on **current existing state**, not every historical step.

### Producer Notifications / Event Logs Should Be Used If

- **Every** publication must be detected, including ultra-short-lived files.
- Strict ordering, identifiers, acks, and retries with explicit contracts are required.
- Business processing demands exactly-once semantics (typically via idempotency + checkpoints).
- Multiple machines process the same directory and must avoid duplicate pickup or race processing.

In such cases, a message queue, database outbox, versioned manifest, or reliable event emitter from the file-producing system itself is usually a clearer source of truth than a directory watcher.

## 14. Common Mistakes and Fixes

**Mistake 1 — "Java uses `WatchService`, so it will receive events from every machine writing to SMB/NFS."** No such guarantee exists. Test operations from other clients and implement rescanning.

**Mistake 2 — "Receiving no events for 5 seconds proves no files exist."** False. `poll(timeout) == null` only means no key was detected during the wait window. Check snapshots and SLAs.

**Mistake 3 — "One file write emits exactly one `ENTRY_MODIFY`."** False. Events can repeat, coalesce, or be dropped.

**Mistake 4 — "Receiving modify means the file is definitely complete."** False. The producer may still be writing. Use a publish/marker protocol or readiness validation.

**Mistake 5 — "Ignore `OVERFLOW` because it has no file context."** False. It signals that the event list lost completeness; reconciliation/rescan is required.

**Mistake 6 — "Calling `pollEvents()` is enough; `reset()` is unnecessary."** False. After processing a key, call reset so the key returns to a ready state for new signals; check the boolean result.

**Mistake 7 — "Registering root automatically watches recursively."** False under the general API contract. Watching subdirectories requires registering them and handling newly created directories.

**Mistake 8 — "Comparing mtime alone cannot miss updates."** False. Mtime is affected by timestamp resolution, caching, and metadata-preserving operations; add size/hash/version as needed.

**Mistake 9 — "Full snapshots reconstruct all file history."** False. Files created and deleted between two scans may leave no state to detect.

**Mistake 10 — "After replacing a mount, the old watch definitely recovers on its own."** Not guaranteed. Use health checks, verify registrations, and re-register and rescan when environment changes are detected.

## 15. Self-Check Questions

**Question 1.** Machine A registers a watcher on NFS; Machine B creates a file. Machine A does not receive `ENTRY_CREATE`. Can we conclude the JVM has a bug?

**Answer:** No. Java does not guarantee detecting remote changes. Check the provider and set up polling/reconciliation or source-side notifications.

**Question 2.** The watcher receives three `ENTRY_MODIFY` events for one file. Did the producer successfully save the file three times?

**Answer:** No. Event count is not business commit count. Process based on file state and version-identification mechanisms.

**Question 3.** When encountering `OVERFLOW`, should you simply skip that event and continue with the remaining events?

**Answer:** No, if complete state is needed. You must run a reconciliation scan on the affected scope; you cannot reliably deduce which files were skipped.

**Question 4.** Will registering a watch after a file already exists automatically emit `ENTRY_CREATE` for that file?

**Answer:** No. An initial scan is needed to pick up entries predating registration.

**Question 5.** For a consumer processing financial reports from a shared folder, is a single `ENTRY_CREATE` event enough to confirm the file is ready?

**Answer:** No. A publishing protocol (temp file then appropriate rename, marker/manifest, or producer signal) plus content and integrity validation is needed.

**Question 6.** If you must record every ultra-short-lived file creation/deletion across multiple machines, does `WatchService` + polling guarantee no missed history?

**Answer:** No. A reliable event log/audit source at the origin of the events is required.

**Question 7.** Why should a system still scan periodically even when the watcher seems to be working fine?

**Answer:** To catch missed changes, recover from outages/overflows, and verify consistency between stored state and actual state.

## 16. Takeaways

- **`WatchService` is a change-notification mechanism with platform-dependent behavior**, not a complete event log or transaction mechanism.
- **Network file systems require special care:** changes from other machines may go undetected; test realistically over NFS/SMB with the actual deployment configuration.
- **`OVERFLOW`, duplicate events, delayed events, and invalid keys** must all have explicit handling branches.
- **Receiving an event does not mean the file has finished writing**; use a publishing protocol and state validation.
- **Combining events + periodic reconciliation + checkpoints/idempotency** is the practical pattern for critical systems; if full history must be preserved, a reliable producer-side event source is needed.

### Official References

- [Java SE 17 — WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): API contract, `OVERFLOW`, and platform/remote file system limitations.
- [Java SE 17 — WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents()`, `reset()`, valid/cancel states.
- [Dev.java — Watching a Directory for Changes](https://dev.java/learn/api/io/java-io/file-system/watching-dir-changes/): workflow for registering and processing directory watches.

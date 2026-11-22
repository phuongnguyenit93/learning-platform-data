# WatchService: Recursive Registration and Watching Newly Created Directories in Java NIO

In Java NIO, `java.nio.file.WatchService` monitors **directory change events**: entry creation, deletion, modification, and event loss due to queue overflow. When building a watcher for an entire directory tree, the biggest hurdle is: **`WatchService` does not register recursively automatically**. Registering a parent directory **does not** automatically register existing subdirectories; when a new directory appears, the application must also register it and its subdirectories.

Therefore, a proper recursive watcher requires two coordinated parts: **scanning the existing tree for initial registration** and **handling `ENTRY_CREATE` events to expand monitoring scope**. In addition, you must manage race conditions, lost events (`OVERFLOW`), the `WatchKey` lifecycle, symbolic links, and a file system reconciliation policy when accuracy matters.

## 1. What Does `WatchService` Observe?

Three main components:

| Component | Role |
| --- | --- |
| `WatchService` | Service receiving changes, created via `FileSystem.newWatchService()`. |
| `Path.register(watcher, kinds...)` | Registers **one directory** with the service to observe event kinds. |
| `WatchKey` | Represents a registration, returned on registration and placed into the queue when events occur. |

Commonly encountered event kinds:

- **`ENTRY_CREATE`**: a new entry appears in the registered directory, which may be a file or a directory.
- **`ENTRY_DELETE`**: an entry disappears from the registered directory.
- **`ENTRY_MODIFY`**: an entry has a change of the type reported by the provider per its watching mechanism.
- **`OVERFLOW`**: events may have been lost or discarded; this is a signal to reconcile against the file system.

`WatchEvent.context()` for standard entry events is usually the **entry name relative to the registered directory**, not an absolute path. Thus the application needs to store a `Map<WatchKey, Path>` relationship to resolve:

```java
Path directory = registeredDirectories.get(key);
Path affected = directory.resolve((Path) event.context());
```

This is a snippet; `event.context()` must be cast appropriately for entry events; **do not** treat `OVERFLOW` like a normal `Path` because its context may be `null`.

### Why Is Registering Only the Parent Insufficient?

```text
root/                 <- register(root) called
  report.txt          <- CREATE/DELETE/MODIFY may appear on root
  docs/               <- Not automatically watched!
    guide.md          <- Direct events in docs may not be seen
    images/           <- Also not watched
      logo.png
```

Registering `root` only watches **entries directly inside `root`**. To receive events for `docs/guide.md`, you must register `docs`; to watch `docs/images/logo.png`, you must register `docs/images`.

**There is no standard call like `watchRecursively(root)` in Java SE 17's `WatchService` API.** Recursive registration is an algorithm written by the application using APIs such as `Files.walkFileTree`.

## 2. The Two Phases of Recursive Registration

**Phase A — Register existing directories:**

1. Verify the root path is a directory and has appropriate access permissions.
2. Create a `WatchService`.
3. Traverse the directory tree with `Files.walkFileTree(root, visitor)`.
4. In `preVisitDirectory`, call `dir.register(watcher, ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY)`.
5. Store `WatchKey -> Path` so when events arrive you know which directory contains the entry.

**Phase B — Register new directories at runtime:**

1. Retrieve `WatchKey` from `watcher.take()` or `watcher.poll(...)`.
2. Look up the corresponding directory in the map and iterate over `key.pollEvents()`.
3. If `ENTRY_CREATE` is received and the newly created entry is currently a directory, call **recursive registration on that new directory itself**, not just one level.
4. Process business events as required, then call `key.reset()`.
5. If `reset() == false`, the key is no longer valid; remove it from the map and decide whether recovery/re-registration is needed.

Diagram:

```text
root/ ── walkFileTree ──> watch root, old/, old/sub/
  |
  +── ENTRY_CREATE new/ ──> isDirectory(new/, NOFOLLOW_LINKS)?
                                  |
                                 Yes
                                  |
                                  v
                         walkFileTree(new/)
                           ├── register(new/)
                           └── register(new/sub/) if already exists

Any entry under new/sub/ appearing AFTER successful registration
can be placed into the WatchService queue for new/sub/.
```

**Why `walkFileTree(newDir)` is needed instead of just `newDir.register(...)`:** another actor could create `new/sub/deep` very quickly before the `new` event is processed. Then walking the new subtree finds the subdirectories that already appeared, even if the application was not watching them yet when they were created.

## 3. Recursive Registration Function Using `Files.walkFileTree`

The `Files.walkFileTree` API traverses each directory and lets you register right when entering a directory:

```java
// Snippet: watcher is an open WatchService,
// directories is Map<WatchKey, Path>.
Files.walkFileTree(root, new SimpleFileVisitor<>() {
    @Override
    public FileVisitResult preVisitDirectory(
            Path dir, BasicFileAttributes attrs) throws IOException {
        WatchKey key = dir.register(watcher,
                StandardWatchEventKinds.ENTRY_CREATE,
                StandardWatchEventKinds.ENTRY_DELETE,
                StandardWatchEventKinds.ENTRY_MODIFY);
        directories.put(key, dir);
        return FileVisitResult.CONTINUE;
    }
});
```

This snippet is **not standalone**: it needs imports from `java.nio.file`, `java.nio.file.attribute.BasicFileAttributes`, `java.io.IOException`, and variables `root`, `watcher`, and `directories`.

By default, the overload above does not follow symbolic links. When restricting the tree within a trusted root, **do not carelessly enable `FOLLOW_LINKS`**, because symlinks can create cycles or lead outside the allowed region. If an application intentionally supports symlinks, it must solve canonical paths, permissions, cycle detection, and scope-limiting policies.

`preVisitDirectory` can throw `IOException`/`AccessDeniedException`, or the provider may not support registration. Depending on requirements, the application should log the error and continue with other branches, or treat it as an error indicating the watcher is not monitoring completely. Do not report "watching everything" if a branch failed to register.

## 4. Complete Java 17+ Program: Watching New Directories and Descendants

The program creates a temporary directory tree, performs initial registration, creates a new subtree, and waits for `ENTRY_CREATE` of the new parent directory. When handling that event, it uses `walkFileTree` to register the entire subtree (including subdirectories already created), and then creates a file deep inside to prove the watcher is now monitoring the new directory.

The example uses **a single thread**, needing no external program to create files. Results are printed as relative paths so output does not depend on the temporary directory location on Windows/Linux/macOS.

Save as **`RecursiveWatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.stream.Stream;

import static java.nio.file.StandardWatchEventKinds.*;

public class RecursiveWatchDemo {
    private static void registerTree(Path start, WatchService watcher,
                                     Map<WatchKey, Path> directories)
            throws IOException {
        Files.walkFileTree(start, new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir, BasicFileAttributes attrs) throws IOException {
                WatchKey key = dir.register(watcher,
                        ENTRY_CREATE, ENTRY_DELETE, ENTRY_MODIFY);
                directories.put(key, dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    private static void awaitCreated(Path expected, WatchService watcher,
                                     Map<WatchKey, Path> directories)
            throws IOException, InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            WatchKey key = watcher.poll(1, TimeUnit.SECONDS);
            if (key == null) {
                continue;
            }

            Path dir = directories.get(key);
            boolean seen = false;
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == OVERFLOW) {
                    throw new IOException("WatchService overflow: need rescan");
                }
                if (dir == null) {
                    continue;
                }
                Path child = dir.resolve((Path) event.context());
                if (event.kind() == ENTRY_CREATE) {
                    if (Files.isDirectory(child, LinkOption.NOFOLLOW_LINKS)) {
                        registerTree(child, watcher, directories);
                    }
                    if (child.equals(expected)) {
                        seen = true;
                    }
                }
            }

            if (!key.reset()) {
                directories.remove(key);
            }
            if (seen) {
                return;
            }
        }
        throw new IOException("Timed out waiting for " + expected.getFileName());
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("recursive-watch-");
        try {
            Files.createDirectories(root.resolve("existing/deep"));
            try (WatchService watcher = FileSystems.getDefault()
                    .newWatchService()) {
                Map<WatchKey, Path> directories = new HashMap<>();
                registerTree(root, watcher, directories);
                System.out.println("initial directories=" + directories.size());

                Path fresh = root.resolve("new");
                Files.createDirectories(fresh.resolve("sub"));
                awaitCreated(fresh, watcher, directories);
                System.out.println("after new subtree=" + directories.size());

                Path file = fresh.resolve("sub/hello.txt");
                Files.writeString(file, "hello");
                awaitCreated(file, watcher, directories);
                System.out.println("created=" +
                        root.relativize(file).toString().replace('\\', '/'));
            }
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path path : paths.sorted(Comparator.reverseOrder())
                        .toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 RecursiveWatchDemo.java
java RecursiveWatchDemo
```

Stdout verified by compiling and running on a file system supporting `WatchService`:

```text
initial directories=3
after new subtree=5
created=new/sub/hello.txt
```

**Step-by-step analysis:**

1. Before registration, the example creates `root/`, `root/existing/`, and `root/existing/deep/`. Walking the existing tree registers exactly **3 directories**.
2. `Files.createDirectories(root.resolve("new/sub"))` creates `new/` and `new/sub/`. When the observer processes `ENTRY_CREATE` for `new`, both new directories already exist.
3. `registerTree(new, ...)` descends into `new/sub/` and creates two more registrations, bringing the total to **5**.
4. The program **waits for registration to complete before creating the file** `new/sub/hello.txt`. This is crucial to avoid a race in the demo: if the file were created before `new/sub` was registered, the file's event might not be recorded.
5. When the `new/sub/` directory source emits `ENTRY_CREATE`, `context()` is the name `hello.txt`, resolved against the key's `Path` to form the exact path.
6. The method uses `watcher.poll(1, TimeUnit.SECONDS)` so the demo does not wait forever; the overall deadline is bounded at 5 seconds. If the provider/file system does not support timely events, it reports an error instead of claiming every environment produces identical output.
7. Each received key has `reset()` called. If a key becomes invalid, the map is updated. Finally, `try-with-resources` closes `WatchService` and `finally` cleans up the temporary directory tree after monitoring stops.

**Example scope:** intentionally waits for only two specific events, throws an error on `OVERFLOW`, and does not implement full recovery. To build a production watcher, see the rescan, permission-monitoring, and service-shutdown strategies in the following sections.

## 5. Why Does Registering a New Directory Still Have an Event Gap?

This is the most important point to understand deeply. Consider this sequence:

```text
T0: root is already registered.
T1: Another process creates root/new/.
T2: Another process creates root/new/a.txt.
T3: Watcher thread retrieves ENTRY_CREATE for root/new/.
T4: Watcher calls register(root/new/).
```

The `a.txt` event at **T2** occurred before `root/new/` was registered at **T4**. `WatchService` makes no promise to deliver change history prior to registration, so the application **can miss the creation event for `a.txt`**, even though the file now exists.

Registering `new/` and its subdirectories via `walkFileTree` only resolves **the scope of currently existing directories**, without reconstructing missed file events.

### Strategy: Register Then Reconcile State

When reliable file synchronization is needed, do not rely solely on `ENTRY_CREATE`:

1. Register directories in the new subtree as quickly as possible.
2. After registering, scan the current file/directory list of the subtree.
3. Compare against the **known-state snapshot/index** to detect new files, deleted files, and modified files, using metadata and, when needed, content hashes.
4. Handle events arriving during the scan alongside reconciliation; design **idempotency/deduplication** because a file may appear both in the scan and in the event queue.
5. If `OVERFLOW` occurs or missing data is suspected, rescan the subtree/root per policy.

No scan + register sequence automatically creates an **atomic snapshot of an entire file system tree being modified concurrently**. If you truly must guarantee zero lost changes across multiple processes, consider writer-coordination protocols, file system snapshots, native change journals, or transaction-history storage; `WatchService` is only a notification source, not a durable event log.

## 6. Reconciliation Instead of Trusting Every Event Is Complete

Directory-sync applications typically maintain an index:

```text
Map<Path, FileInfo> knownFiles
Map<WatchKey, Path> registeredDirectories

FileInfo may contain:
  isDirectory
  size
  lastModifiedTime
  optional fileKey / contentHash
```

One reconciliation round:

```text
Scan root file system
     |
     v
Build current observed snapshot
     |
     +-- New Path: add/index, run ingest
     +-- Missing Path: mark/handle delete
     +-- Changed metadata/hash: update/handle modify
     |
     v
Register any missing directories
     |
     v
Continue applying arrived events (dedup by state/id)
```

Important operational conditions:

- `Files.exists(path)` and `Files.isDirectory(path)` are only **state at the moment of the call**. An entry can disappear or change type immediately afterward.
- When a file has just been created, the writer may not have finished writing. If processing a complete file is required, use a publish-via-rename convention, marker/manifest, size-stability checks, or coordination with the producer.
- Timestamps/sizes have resolution limits and do not prove content is unchanged. For high correctness, consider content hashes or an appropriate protocol.
- Rename/move can be reported via different sequences of delete/create/modify across providers; standard `WatchService` does not provide a portable rename transaction carrying both source and destination.
- After scanning, the application may still receive duplicate events for the same state; handlers should be **idempotent** to avoid ingesting the same file multiple times.

## 7. `OVERFLOW`: Cannot Be Ignored as an Ordinary Event

`OVERFLOW` indicates that some events may have been missed. Never do this:

```java
// WRONG: if OVERFLOW is the only event, still assumes everything is in sync.
if (event.kind() == OVERFLOW) {
    continue;
}
```

When handling the file system for synchronization, **mark the state as no longer trustworthy** and then run reconciliation on the corresponding root or subtree, depending on what the provider reports. You can reduce pressure by handling events quickly, batching work onto a worker queue, and avoiding time-consuming tasks on the event-receiving thread.

Conceptual example:

```java
// Snippet: scanAndReconcile is implemented by the application.
if (event.kind() == OVERFLOW) {
    needsFullRescan = true;
} else {
    // Handle entry event; avoid long blocking.
}
// At an appropriate point:
if (needsFullRescan) {
    scanAndReconcile(root);
    needsFullRescan = false;
}
```

This is a **snippet**, not a built-in API. Triggering a full scan can be expensive, so quotas, coalescing, and frequency policies are needed; do not assume the event queue will hold every change indefinitely.

## 8. `WatchKey`: Retrieving, `pollEvents`, `reset`, and Invalidation Cases

Basic event-loop pattern:

```java
// Snippet: watcher and directories are already declared.
// Map is updated only on this event-loop thread.
while (running) {
    WatchKey key = watcher.take();  // Wait for a signalled key.
    Path dir = directories.get(key);

    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == OVERFLOW) {
            scheduleRescan();
            continue;
        }

        if (dir == null) {
            continue;
        }
        Path affected = dir.resolve((Path) event.context());

        if (event.kind() == ENTRY_CREATE &&
                Files.isDirectory(affected, LinkOption.NOFOLLOW_LINKS)) {
            registerTree(affected, watcher, directories);
        }

        handleChange(affected, event.kind());
    }

    if (!key.reset()) {
        directories.remove(key);
        handleInvalidRegistration(dir);
    }
}
```

The code above is **Java-style pseudocode**; `running`, `scheduleRescan`, `registerTree`, `handleChange`, and `handleInvalidRegistration` are built by the application.

**Rules not to forget:**

- One `WatchKey` can contain **multiple `WatchEvent`s**; iterate through all of them or use an explicit skip/rescan strategy.
- `WatchEvent.count()` indicates how many events of the same kind/context may have been coalesced; each change does not necessarily produce a separate event object.
- After processing, **`key.reset()`** allows signals to continue arriving. Forgetting reset can prevent the key from being re-queued as expected.
- `reset() == false` means the key is no longer valid; do not assume that directory is still protected. A deleted directory, disconnected file system, cancelled registration, or closed watcher can all be involved.
- Do not `cancel()` a key you still want to watch; `key.cancel()` terminates the registration.
- When `watcher.close()` is called, threads waiting in `take()`/`poll()` can be woken with `ClosedWatchServiceException`; manage shutdown deliberately.

An `ENTRY_DELETE` event can report that a directory was removed from its parent. It makes no sense to register that path; update the index, handle child keys that may become invalid, and prepare to re-register if the path is recreated.

## 9. New Directory Deleted or Replaced Before `register`

Another race scenario:

```text
root is registered
  |
  +-- CREATE root/tmp
  +-- DELETE root/tmp
  +-- CREATE root/tmp   (may be a different object)
  |
Watcher only now processes the first ENTRY_CREATE.
```

When the watcher executes `Files.isDirectory(root/tmp)`, it only sees **the object currently existing at that moment** (if any), with no guarantee it is the directory from the first event. Even after checking, it can still be deleted before `register`.

The right strategy is not "force register to succeed" with an infinite retry loop. Instead:

- Accept `NoSuchFileException`/`NotDirectoryException` or appropriate `IOException` as a sign the tree changed, and schedule a rescan.
- Limit retry attempts and work per cycle.
- Never use paths outside the root scope; guard against symbolic links/path traversal when user-influenced segments are involved.
- If the root directory disappears, decide whether the watcher stops, tries recovering until a deadline, or watches the parent directory to detect when root is recreated. Do not assume a deleted root's watcher will revive itself.
- Use locks/coordination with producers or file system snapshots if business logic needs stronger guarantees than "eventual reconciliation".

## 10. Do Not Follow Symlinks Unintentionally

For a tree containing symbolic links:

```text
root/
  docs/
  external -> /outside-root/private
  loop -> root/
```

If `Files.walkFileTree` is called with uncontrolled `FOLLOW_LINKS`, the crawler can escape outside the allowed area or hit path cycles. Therefore:

- By default, **do not enable `FOLLOW_LINKS`** when monitoring a root tree.
- When deciding whether an `ENTRY_CREATE` is a directory to register, use `Files.isDirectory(affected, LinkOption.NOFOLLOW_LINKS)`.
- If symlink support is required by the product, define a policy: watch the link object, watch the target, or ignore. Check permissions, true root bounds, cycle avoidance, and path-change implications.
- For trees concurrently modified by untrusted actors, `NOFOLLOW_LINKS` at a single check point still does not eliminate all TOCTOU races when paths are replaced. Use APIs/protocols managing access permissions commensurate with risk.

`WatchService` also does not guarantee that all metadata/symlink changes are reported identically across all operating systems.

## 11. Watching Many Directories Can Consume System Resources

The "register per directory" model typically consumes kernel/provider resources for **each registration**, especially on OSes with limits on watcher/inotify watches. A very deep or wide tree can hit quotas, run out of file descriptors, or fail when registering more directories.

Operational measures:

1. Count actually registered directories and failed registrations.
2. Set reasonable limits on depth, directory count, and scan duration for untrusted trees.
3. Have a degradation strategy: report that part of the tree is unwatched and run periodic scans or refuse to start the feature.
4. Mitigate event storms; process quickly and offload heavy tasks to a bounded queue.
5. Clean up invalid keys so the map does not grow unbounded; close `WatchService` on shutdown.
6. When deploying on network file systems, containers, or external devices, test on the actual provider/mount rather than extrapolating native behavior solely from local file system examples.

Excessive registrations are not solved by "just registering root once is enough": per standard API, registering root **does not provide recursive watching**.

## 12. Event Timing, Order, and Content Are Not a Reliable Log

Limitations to remember:

| Issue | Consequence | Mitigation |
| --- | --- | --- |
| Events can be delayed | File already changed on disk, but watcher processes it later. | Accept eventual consistency or coordinate with writer. |
| Events can be coalesced | Multiple edits do not produce separate individual events. | Re-read actual state; use `event.count()` for awareness. |
| `OVERFLOW` | Some events are no longer in the queue. | Rescan and reconcile against snapshot/index. |
| Subdirectories created too quickly | Changes occur before child registration. | Register entire subtree, then reconcile. |
| Rename or move | May appear as delete/create depending on provider. | Analyze state and file protocol instead of relying on one event. |
| Symlink/permission changes | Loss of access, escaping root, registration failures. | Do not follow by default; check permissions and handle `IOException`. |
| Path deleted then recreated | Old `WatchKey` does not auto-bind to the new object. | Re-register and reconcile as needed. |
| Shutdown/close | Keys invalid; waiting threads may receive exceptions. | Close service cleanly and release resources. |

**Do not infer "seeing `ENTRY_MODIFY` means the file is done writing".** The file author may still be writing, or the file may be modified further. For strict ingest pipelines, define an explicit publish contract (write temp file then rename when ready, sidecar marker, manifest, checksum...) and handle duplicates.

## 13. Handling `ENTRY_CREATE` for Both Files and Directories

A handler typically has two branches:

```java
// Snippet: affected was resolved from key directory + context.
if (event.kind() == ENTRY_CREATE) {
    if (Files.isDirectory(affected, LinkOption.NOFOLLOW_LINKS)) {
        registerTree(affected, watcher, directories);
        // Scan and reconcile subtree to find existing files.
    } else if (Files.isRegularFile(
            affected, LinkOption.NOFOLLOW_LINKS)) {
        // Enqueue file into bounded ingest queue, if eligible.
    } else {
        // Entry no longer exists / is not a regular file
        // or state cannot be checked: schedule rescan.
    }
}
```

**Register the subtree** before spending lots of time on business logic to shrink the window for missing future events. If file processing is heavy, offload it to a bounded worker queue instead of running it directly on the `WatchKey`-polling thread, while also providing backpressure and snapshot/event coordination to preserve consistency.

Do not trust a single `Files.isDirectory` check alone to claim it is the exact directory created by the event: the path may have changed between steps. Only a policy combining reconciliation and race mitigation yields adequate reliability.

## 14. Proper Watcher Lifecycle and Shutdown

A watcher can run in its own thread:

```java
// Snippet: background thread calling watcher.take() in a processing loop.
try {
    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.take();
        processKey(key);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} catch (ClosedWatchServiceException e) {
    // Service closed: exit monitoring loop.
} finally {
    // Clean up this thread's state; owner will close watcher
    // if not already closed from another control path.
}
```

`processKey` is an application method implemented to call `pollEvents`/`reset` and handle overflow. For a long-running service, a coordinator thread can call `watcher.close()` to release resources and make a waiting `take()` exit via the API mechanism.

A shutdown sequence should be explicit: stop accepting new work → signal watcher thread to stop / close service → release registrations → complete or cancel queued tasks within deadline → report final status. **Do not clear the entire map while workers are still accessing it** without a thread-safe synchronization policy.

Use `try-with-resources` with `WatchService` when the service owner has a well-defined scope. `WatchService.close()` releases resources, unlike calling `key.cancel()` on individual directories.

## 15. Distinguishing "Notification" Needs from "Complete Detection" Needs

**Just a hint to refresh UI:** `WatchService` can be a good fit. If a few events are missed, the UI can rescan when the user opens it or when a timer fires.

**Directory synchronization:** requires `WatchService` combined with snapshots/indexes and idempotent handling. Register new directories as they appear, rescan on overflow, and run periodic reconciliation to prevent long-term drift.

**Critical file ingestion:** requires a completed-file contract, bounded queues, retry/dedup handling, logging, and crash recovery. `WatchService` cannot itself prove a publisher finished writing.

**Complete audit of every change in a tree:** standard `WatchService` **is not sufficient as a lossless audit log**. You need native change journals, an appropriate audit subsystem, or producers writing durable transaction logs, depending on OS and legal/technical requirements.

Whenever you want "recursive watching", ask an important engineering question: **Is the goal fast update notification or proving total state is always consistent?** Error-handling and scanning strategies differ markedly.

## 16. Common Pitfalls

| Symptom | Cause | Fix |
| --- | --- | --- |
| Do not see files created in `root/a/b` | Only called `register(root)`. | Traverse with `walkFileTree` and register every directory. |
| See new directory, but not child files | Forgot to register new directory, or files were created before registration. | Register entire subtree; reconcile after registration. |
| Casting context causes error/null | Treated `OVERFLOW` like an entry event. | Check kind first before casting `(Path) event.context()`. |
| Watcher stops receiving after a few events | Forgot `key.reset()`. | Reset after polling/processing; check boolean return. |
| Map keeps keys of deleted directories | Did not handle `reset() == false`. | Remove key; rescan/re-register as appropriate. |
| Missing events during rapid changes | Coalesced events, `OVERFLOW`, or registration races. | Use index/snapshot + reconciliation. |
| Wrong affected path | Treated context as absolute path or resolved against root instead of key's directory. | Use `directories.get(key).resolve(context)`. |
| Watcher looks outside root area | Blindly followed symlinks. | Use `NOFOLLOW_LINKS`, define symlink policy, check permissions. |
| Partial file gets processed | Treated `ENTRY_CREATE` or `ENTRY_MODIFY` as "finished writing". | Publish/marker protocol; verify file completeness. |
| High CPU, queue overflow | Handler does heavy work or producer emits too many events. | Keep event thread short; bounded queue; budgeted rescans. |
| Closing watcher causes thread to throw | `watcher.close()` wakes waiting `take()`. | Catch `ClosedWatchServiceException` during shutdown. |
| Registration fails on large trees | Kernel/provider/permission limits. | Cap watch count, warn, fall back to rescanning. |

## 17. Practice Exercises

**Exercise 1 — Add `OVERFLOW` recovery.** Replace `throw new IOException` on `OVERFLOW` in the demo with setting `needsRescan`. Write a root-scanning function to find new files and register unwatched directories. Explain why deduplication between events and scans is needed.

**Exercise 2 — Pre-registration race.** Modify the demo: create `root/new/sub/hello.txt` **before** `awaitCreated(root/new)` processes the event. Observe the possibility of not seeing `ENTRY_CREATE` for the file. Scan right after registering so existing files are still discovered.

**Exercise 3 — Deeply nested directories.** Create `root/a/b/c/d` in a single `Files.createDirectories` call and observe how many directories get registered when receiving `ENTRY_CREATE` for `a`. Then create `d/file.txt` and verify it is detected.

**Exercise 4 — Delete then recreate.** Create a directory with a watcher, delete it, and recreate it with the same name. Observe `WatchKey.reset()` and events on the parent directory. Explain why the new object must be registered and the snapshot reconciled.

**Exercise 5 — Symlinks and security.** On a system supporting symbolic links with permission to create links, create a symlink inside root pointing outside. Verify the sample watcher does not follow the link. Write a clear policy if the product requires link support without exposing sensitive external data.

**Exercise 6 — Incremental file writes.** A producer creates a file and writes five chunks spaced apart. Observe that `ENTRY_CREATE/ENTRY_MODIFY` can vary by OS. Propose a "file ready" rule using temp-file rename to the final name or a separate marker, instead of inferring from event count.

**Exercise 7 — High-volume changes / `OVERFLOW`.** Create thousands of files in a test directory and measure event queue behavior and processing time. Do not intentionally stress production systems. When `OVERFLOW` occurs or events mismatch the snapshot, run a rescan and measure latency.

**Exercise 8 — Shutdown.** Run the watcher in a background thread, have the main thread close `WatchService`, and then `join()` with a deadline. Verify the event-polling loop exits without hanging and leaves no leaked live thread.

### Self-Check Questions

1. Does registering `root` automatically watch `root/sub/file.txt`?
2. Why must handling `ENTRY_CREATE` for a directory register **the entire new subtree**?
3. Why might a file created right after a directory have no event even if `registerTree(newDir)` succeeded?
4. Is `WatchEvent.context()` always an absolute path?
5. Why must `OVERFLOW` be handled by rescanning?
6. What problem does forgetting `key.reset()` cause, and what does `reset() == false` mean?
7. Why should `NOFOLLOW_LINKS` be used when watching a tree with a trusted boundary?
8. If a file already has `ENTRY_CREATE`, is it guaranteed to contain all contents for ingestion?
9. When lossless auditing is required, is `WatchService` a durable historical source?

## 18. Official Documentation

- [Java SE 21 — WatchService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): service lifecycle, keys, queue, closing, and provider behavior.
- [Java SE 21 — WatchKey](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents()`, `reset()`, `cancel()`, and registration validity.
- [Java SE 21 — WatchEvent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchEvent.html): `kind()`, `context()`, and `count()`.
- [Java SE 21 — StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): kinds `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW`.
- [Java SE 21 — Files.walkFileTree](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#walkFileTree(java.nio.file.Path,java.nio.file.FileVisitor)): traversing and processing directory trees.
- [Java SE 21 — Path.register](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...)): registering watches for individual directories.

**Takeaway:** `WatchService` does not watch recursively automatically. Use `Files.walkFileTree` to register all existing directories; on `ENTRY_CREATE` for a new directory, register **the entire subtree**, handle `WatchKey.reset()` and `OVERFLOW`, and **reconcile file system state** to overcome races and dropped events. When absolute data correctness is needed, add stronger protocols and sources of truth than a file system notification stream alone.

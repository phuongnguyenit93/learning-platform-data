# OVERFLOW and the Need for State Rescanning in Java NIO WatchService

## 1. Why Can WatchService Miss Changes?

`java.nio.file.WatchService` is the Java NIO.2 mechanism for receiving notifications when a directory's contents change. Applications typically register `ENTRY_CREATE`, `ENTRY_MODIFY`, and `ENTRY_DELETE` to automatically process new files, refresh indexes, reload configurations, or synchronize data.

However, `WatchService` **is not a durable transaction log**. The operating system, file system provider, and notification queue can coalesce or discard events. When events are lost, `WatchService` may emit the special event kind **`StandardWatchEventKinds.OVERFLOW`**.

~~~text
Directory: create A, modify B, delete C, create D, ...
                         |
                         v
             WatchService / provider
                         |
                   queue overloaded
                         |
                some events lost
                         |
                         v
                WatchEvent OVERFLOW
                         |
                         v
                    MARK DIRTY
                         |
                         v
               RESCAN DIRECTORY
                         |
                         v
             RECONCILE WITH SNAPSHOT
~~~

**Meaning:** after `OVERFLOW`, there is no longer any guarantee that the application knows all directory changes solely from received events. The right approach is to **rescan current state and reconcile against stored state**, rather than guessing the file list from lost events.

## 2. WatchEvent Kinds

| Event Kind | Meaning | Commonly Used Information |
| --- | --- | --- |
| `ENTRY_CREATE` | An entry appears | `event.context()` is the relative `Path` name of the entry |
| `ENTRY_MODIFY` | An entry changed | `event.context()` is the relative `Path` name |
| `ENTRY_DELETE` | An entry disappears | `event.context()` is the relative `Path` name |
| `OVERFLOW` | Events may have been lost or discarded | Do not use context to infer which files were missed |

Register a directory using:

~~~java
dir.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);
~~~

This is just an **illustrative Java snippet**, assuming `Path dir` and `WatchService watcher` have already been created.

You do not need to register `OVERFLOW` as an ordinary file event to handle event-loss situations. When retrieving events, you must check `event.kind() == StandardWatchEventKinds.OVERFLOW` **before** casting context to `Path`.

### OVERFLOW Does Not Mean One Specific File Changed

Suppose the application's snapshot is:

~~~text
a.txt = old version
b.txt = exists
~~~

While the application has not yet drained all events:

~~~text
a.txt is modified
b.txt is deleted
c.txt is created
d.txt is created and immediately deleted
~~~

The queue may retain only part of those events and emit `OVERFLOW`. Upon rescanning, the application can notice that `a.txt` differs, `b.txt` is missing, and `c.txt` is new. However, `d.txt` having been created and deleted between two observations may **be undetectable**.

Therefore:

- `OVERFLOW` indicates **loss of reliability about occurred events**, rather than listing the lost events.
- Rescanning restores the **currently observable state**.
- Rescanning **does not recover full history**, ordering, or exact modification counts.
- A single `ENTRY_MODIFY` also does not guarantee a 1-to-1 match with one file write; multiple changes can be coalesced and `WatchEvent.count()` can be greater than 1.

If a system must process every single transaction accurately even for very short-lived files, a different protocol or durable queue is needed—you cannot rely solely on `WatchService`.

## 3. WatchService, WatchKey, and Reset

Basic `WatchService` cycle:

1. Create a `WatchService` for the appropriate `FileSystem`.
2. Register a directory with `Path.register(watcher, ...)`, receiving a `WatchKey`.
3. Wait on `watcher.take()` or call `poll()`.
4. Retrieve the key's events via `key.pollEvents()`.
5. Process normally, or mark for rescan if `OVERFLOW` is encountered.
6. **Call `key.reset()`** so the key can continue reporting new events.
7. If `reset()` returns `false`, the key is no longer valid; handle directory lifecycle changes or re-register per application policy.

One `WatchService` can manage multiple directories. Each `WatchKey` corresponds to one registration; use `key.watchable()` or a `Map<WatchKey, Path>` to identify which directory an event belongs to.

In particular, **registering a parent directory does not automatically watch subdirectories recursively**. To watch an entire tree, the application must register each relevant subdirectory and maintain registrations as the tree changes.

### OVERFLOW Detection Pattern

~~~java
WatchKey key = watcher.take();
boolean dirty = false;

for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        dirty = true;
        continue;
    }

    @SuppressWarnings("unchecked")
    WatchEvent<Path> typed = (WatchEvent<Path>) event;
    Path changed = watchedDir.resolve(typed.context());

    // Can apply incremental updates per ENTRY_CREATE / MODIFY / DELETE.
    // Do not assume the file still exists when actually accessing it.
}

if (dirty) {
    // Rescan watchedDir; reconcile against stored state.
}

if (!key.reset()) {
    // Key invalid: recheck watcher and registered directory.
}
~~~

This is an **illustrative Java snippet inside an event-processing loop**, not a standalone program. `watcher` and `watchedDir` must be declared in the real application.

For `OVERFLOW`, do not cast `event.context()` to `Path`; this event kind does not supply a list of lost filenames.

`key.reset()` must be executed on normal processing paths, including after `OVERFLOW`. If code has multiple branches or may throw exceptions, structure it with `finally` so reset is never forgotten. `reset() == false` cannot be fixed by calling `reset()` in an infinite loop: check whether the directory was deleted, renamed, changed permissions, or the file system stopped watching.

## 4. Why Must a Snapshot Be Rescanned?

Applications often maintain **internal state** separate from the file system:

~~~text
In-memory state before losing events:
  config.json → version 2
  report.csv  → exists
  inbox/a.txt → exists

Actual state after losing events:
  config.json → version 3
  report.csv  → deleted
  inbox/a.txt → still exists
  inbox/b.txt → newly created
~~~

Without rescanning, the cache or index still believes `config.json` is at version 2 and `report.csv` still exists. After `OVERFLOW`, the application needs to:

- **Capture the current state** of affected directories.
- Detect new names (added), missing names (removed), and existing names whose content/attributes changed (changed).
- Update data structures, pending jobs, indexes, or caches accordingly.
- Continue consuming new events; if changes occurred during the scan, another scan pass may be needed.

The goal is **reconciliation**: making the application's representation converge toward the current file system, rather than reconstructing a lost event sequence.

### What Should Be Stored in a Snapshot?

| Snapshot Data | Pros | Limitations |
| --- | --- | --- |
| Name / path | Simple create/delete reconciliation | Does not tell whether content changed |
| `Files.size` | Cheap; detects length changes | Content can change while keeping the same size |
| `Files.getLastModifiedTime` | Relatively fast | Timestamp granularity varies; metadata may be preserved/reset |
| `BasicFileAttributes.fileKey()` | Can help identify a file system object | May be null or unstable across providers |
| Content hash | Detects many changes metadata misses | Costs disk I/O and CPU; tricky with files being written |
| Application-managed version/manifest | Can carry exact domain meaning | Requires designing the protocol upfront |

No cheap metadata signature guarantees detecting every content change on every file system. For high-accuracy requirements, build a protocol with versions/checksums and a complete-file publishing rule.

## 5. Rescan and Reconciliation Algorithm

A simple algorithm:

~~~text
known = previously stored snapshot

on ENTRY_CREATE/MODIFY/DELETE:
    update individual entry or mark entry for inspection

on OVERFLOW:
    dirty = true

if dirty:
    current = scanDirectory()
    added   = names in current but not in known
    removed = names in known but not in current
    changed = names in both with differing signatures
    update cache/index/jobs based on differences
    known = current
    clear dirty only if no new changes arrived during scan
~~~

This is pseudocode. A real application must explicitly decide how to handle file changes occurring during the scan:

- **Register first, then take the initial snapshot.** If you scan first and register later, there is a gap where changes are not reported by the watcher.
- **Scanning is not an atomic transaction.** Files can appear/disappear right after listing; `NoSuchFileException` when reading metadata is a normal case to handle.
- **Do not lose a new dirty flag.** If `OVERFLOW` happens while a worker is scanning, do not mark clean based on the old snapshot. Use a generation counter or explicit synchronization state.
- **Coalesce multiple rescan requests.** A directory should typically have only one scan running at a time; if still dirty afterward, schedule another pass.
- **Protect the event-receiving thread.** If a long scan runs on the watcher thread, the queue can keep overflowing and trigger more `OVERFLOW`s.

For small directories, rescanning whenever events arrive can be simpler and more reliable than complex incremental logic. For trees with millions of files, incremental updates plus full rescan on `OVERFLOW` or periodic schedules are usually needed.

## 6. Standalone Java 17+ Example: Simulating Event Loss and Rescanning

**You cannot portably and deterministically force a real `OVERFLOW`**, because it depends on the OS and provider. The following example creates a real `WatchService`, then **intentionally does not rely on emitted events** to simulate a missed-notification scenario. It calls `reconcile` and compares file states by text content so stdout is deterministic.

The demo only uses a few small UTF-8 files. In production, do not read entire large files into RAM on every rescan.

Save as `OverflowRescanDemo.java`:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Stream;

public class OverflowRescanDemo {
    private static Map<String, String> snapshot(Path dir)
            throws IOException {
        Map<String, String> result = new TreeMap<>();

        try (Stream<Path> paths = Files.list(dir)) {
            for (Path file : paths.filter(Files::isRegularFile).toList()) {
                result.put(file.getFileName().toString(),
                        Files.readString(file, StandardCharsets.UTF_8));
            }
        }
        return result;
    }

    private static void reconcile(Path dir, Map<String, String> known)
            throws IOException {
        Map<String, String> current = snapshot(dir);
        Set<String> allNames = new TreeSet<>();
        allNames.addAll(known.keySet());
        allNames.addAll(current.keySet());

        for (String name : allNames) {
            if (!known.containsKey(name)) {
                System.out.println("ADDED " + name);
            } else if (!current.containsKey(name)) {
                System.out.println("REMOVED " + name);
            } else if (!known.get(name).equals(current.get(name))) {
                System.out.println("CHANGED " + name);
            }
        }

        known.clear();
        known.putAll(current);
    }

    public static void main(String[] args) throws IOException {
        Path dir = Files.createTempDirectory("watch-rescan-");

        try {
            Path alpha = dir.resolve("alpha.txt");
            Path old = dir.resolve("obsolete.txt");
            Path newest = dir.resolve("new.txt");

            Files.writeString(alpha, "A", StandardCharsets.UTF_8);
            Files.writeString(old, "old", StandardCharsets.UTF_8);

            try (WatchService watcher =
                         dir.getFileSystem().newWatchService()) {
                // Register before capturing baseline.
                dir.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Map<String, String> known = snapshot(dir);
                System.out.println("BASELINE " + known.keySet());

                // Simulate the app missing notifications for three operations.
                Files.writeString(alpha, "A2", StandardCharsets.UTF_8);
                Files.delete(old);
                Files.writeString(newest, "new", StandardCharsets.UTF_8);

                System.out.println("RESCAN after missed events");
                reconcile(dir, known);
                System.out.println("CURRENT " + known.keySet());

                // If an actual OVERFLOW occurred in events delivered
                // to the queue, reconcile is also the recovery path.
                // Remaining ENTRY_* events here are intentionally not used
                // as source of truth, because snapshot was just refreshed.
                WatchKey key;
                while ((key = watcher.poll()) != null) {
                    boolean overflow = false;
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            overflow = true;
                        }
                    }
                    if (overflow) {
                        reconcile(dir, known);
                    }
                    if (!key.reset()) {
                        break;
                    }
                }
            }
        } finally {
            try (Stream<Path> files = Files.list(dir)) {
                for (Path file : files.toList()) {
                    Files.deleteIfExists(file);
                }
            }
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac OverflowRescanDemo.java
java OverflowRescanDemo
~~~

Stdout when run in a temporary directory without external changes:

~~~text
BASELINE [alpha.txt, obsolete.txt]
RESCAN after missed events
CHANGED alpha.txt
ADDED new.txt
REMOVED obsolete.txt
CURRENT [alpha.txt, new.txt]
~~~

Deterministic order thanks to `TreeMap` and `TreeSet`:

1. Initial snapshot has `alpha.txt = "A"` and `obsolete.txt = "old"`.
2. Next, `alpha.txt` changes to `"A2"`, `obsolete.txt` is deleted, and `new.txt` appears.
3. `reconcile` compares names and contents, accurately reporting the three observable differences.
4. `known` is updated, so a subsequent `reconcile` pass prints no differences if the directory has not changed.
5. The demo creates a real watcher to illustrate registration and `OVERFLOW` handling, but **does not claim a real `OVERFLOW` happened**. The rescan call is performed proactively to simulate the consequence of missing notifications.
6. `key.reset()` is called on retrieved keys, and temporary resources and files are cleaned up after use.

The demo only scans a flat directory with small text contents; it does not yet include a continuously running production event loop, retry policies when scanning encounters races, or recursive registration.

## 7. Event-Loop Pattern Needed in Real Applications

Code snippet processing a `WatchKey` with a dirty flag:

~~~java
WatchKey key = watcher.take();
boolean needsRescan = false;
Path dir = registrations.get(key);

try {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
            needsRescan = true;
            continue;
        }

        @SuppressWarnings("unchecked")
        WatchEvent<Path> typed = (WatchEvent<Path>) event;
        Path child = dir.resolve(typed.context());

        // For ENTRY_* we can update incrementally or
        // mark child as needing re-inspection.
    }

    if (needsRescan) {
        // Enqueue a rescan(dir) request onto the work queue.
    }
} finally {
    if (!key.reset()) {
        // Registration invalid: investigate and re-register if needed.
    }
}
~~~

This is an **illustrative code snippet**, requiring `registrations`, `watcher`, and application policies to be defined. If multiple directories are registered, map each key to the right directory. If `key.reset()` fails, rescanning alone is not enough to continue receiving new events: you may need to re-register the directory or watch its parent.

With large file counts, do not read hundreds of thousands of files directly inside the thread calling `watcher.take()`. Offloading scans to a worker while continuing to drain events and maintaining a dirty flag/generation reduces the risk of repeated overload.

### Do Not Lose an `OVERFLOW` Occurring Mid-Scan

A common design flaw:

~~~text
Worker sees dirty=true
Worker starts scan
Watcher sees new OVERFLOW → sets dirty=true
Worker finishes scan → sets dirty=false
The new OVERFLOW is wiped out, no more rescan!
~~~

You can manage a generation number:

~~~text
onOverflow: changeGeneration += 1

before scan: capturedGeneration = changeGeneration
scan and apply snapshot
if changeGeneration != capturedGeneration:
    must scan again
else:
    can mark caught up to observation point
~~~

This is pseudocode for **event-management logic**; across multiple threads it requires synchronization or appropriate atomic types. Do not merely swap booleans without ownership or memory-visibility rules.

## 8. Watching Directory Trees and Rescan Races

Standard `WatchService` registers **one directory at a time**, without automatically scanning deep into the tree. If an application watches a root with subdirectories:

- Traverse and register each subdirectory to watch, e.g., using `Files.walkFileTree`.
- Upon detecting a new directory, **register it immediately** and scan its contents because files inside may have appeared before registration completed.
- When a key becomes invalid or a subdirectory is deleted/renamed, update the registration mapping.
- When `OVERFLOW` occurs on a directory, rescan the affected scope. If the entire tree's state must be guaranteed, reconcile both the set of directory registrations and any newly created directories.
- Define a clear symlink policy to avoid accidentally traversing outside the root or looping through linked paths.

### Partially Written Files

`ENTRY_CREATE` can arrive when a producer has just opened a file and not finished writing. During a post-`OVERFLOW` rescan, you may also see incomplete files. If the application must process intact files, use a protocol such as:

~~~text
Producer: write report.tmp → flush/close → rename to report.ready
Consumer: only process *.ready files
~~~

This is an illustrative design model; rename atomicity also depends on the file system and API choices, and must not be assumed to hold across file systems.

### Files Disappearing Between List and Read

After `Files.list(dir)`, a file can be deleted before `Files.readAttributes(...)` or `Files.readString(...)`. `NoSuchFileException` is a normal race in environments with continuous changes. A production scanner must handle per-item errors, mark retries, and bound scan loops when a directory is unstable.

### Metadata Accuracy

If a file is modified while keeping its size and timestamp unchanged, a signature based on `size + mtime` may not change. Content hashing detects more cases, but is expensive and also faces races while a file is being written. Choose a mechanism matching business requirements rather than assuming fast metadata proves file immutability.

## 9. `OVERFLOW` Is Not Solved by Infinite Speedup

If `OVERFLOW` occurs frequently, it signals that the system is not keeping up with the change rate or the provider has specific limits. You can improve it by:

- Keeping the thread calling `WatchKey` lightweight: quickly receive, classify, and reset keys.
- Coalescing consecutive events related to the same file/directory.
- Limiting redundant rescans and staging scans of large directories.
- Tracking `OVERFLOW` counts, event-to-processing latency, backlog length, and scan duration to detect overload.
- If the system must process every task individually, move the source of truth to a durable journal/manifest/queue and use `WatchService` as a wake-up signal.
- Periodically reconciling state even without `OVERFLOW` if correctness outweighs performance.

Do not simply assume allocating a larger application-level buffer eliminates all `OVERFLOW`s: queuing and notification capacity reside in the provider and OS, not solely in the size of a `ByteBuffer` or self-made queue in Java.

## 10. Common Mistakes

**Mistake 1 — Ignoring `OVERFLOW`.** The application keeps trusting the old snapshot and misses files. Mark dirty and reconcile.

**Mistake 2 — Casting `OVERFLOW` context to `Path`.** `OVERFLOW` does not carry a list of files with lost events. Do not rely on context to guess a specific path.

**Mistake 3 — Thinking rescanning recovers all past events.** It mainly recovers current state; very rapid create-then-delete may leave no trace.

**Mistake 4 — Scanning the baseline first and registering the watcher afterward.** Events in the gap can be lost. Register first, scan afterward, and handle events arriving during the scan.

**Mistake 5 — Not resetting the key.** After `pollEvents()`, you must call `key.reset()`; if it returns false, handle the invalidated registration.

**Mistake 6 — Assuming registering root watches recursively.** Subdirectories must be registered and resynchronized when the tree changes.

**Mistake 7 — Running long scans on the watcher thread.** Delays in reading events can trigger new `OVERFLOW`s. Move heavy scans to a worker with dirty tracking.

**Mistake 8 — Clearing dirty too early.** A new `OVERFLOW` occurring while a scan is running can be overwritten. Use a generation counter or synchronization policy.

**Mistake 9 — Trusting `mtime/size` to detect every change.** Metadata can stay unchanged even when payload changes; strict applications need checksums/versions.

**Mistake 10 — Using `WatchService` as an exactly-once queue.** The API does not durably persist or replay all events; a dedicated work-processing protocol is required.

## 11. Self-Check

1. What does `OVERFLOW` indicate? **Events may have been lost or discarded**; the read event list is no longer complete.
2. Why must you rescan? **To compare current file system state against the old snapshot** to find still-observable additions/deletions/changes.
3. Can you always find a file that was created and then deleted between two scans? **Not guaranteed**.
4. Can you use `event.context()` from `OVERFLOW` to find the filenames of lost events? **No**.
5. What must be called after `key.pollEvents()`? **`key.reset()`**; handle the case when the result is false.
6. Does watching a parent directory automatically watch all child levels? **No**.
7. Why register before the baseline scan? **To reduce the gap where events cannot be received**.
8. If the file system changes during a scan, is the snapshot atomic? **No**; retry/reconcile per policy is needed.
9. If `OVERFLOW` occurs right around when a rescan finishes, how do you avoid losing the signal? **Use a dirty-generation counter and do not clear a newer flag unconditionally**.
10. If a system requires exactly-once guarantees, should it use `WatchService` alone? **No**; it needs a durable source of truth, idempotency, and processing acknowledgments.

**Takeaway:** `WatchService` is a **notification** mechanism, not a guaranteed complete change log. `StandardWatchEventKinds.OVERFLOW` is the signal to **stop trusting that every event was observed** and **rescan the actual state**. Compare snapshots, update caches/indexes, continue processing new events, and manage `WatchKey.reset()`, recursive registration if needed, and scanning races. The achievable goal is **convergence toward the file system state**, not recovering lost history.

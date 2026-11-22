# Practice: Watching a Directory with `WatchService` and Handling `OVERFLOW`

## 1. Expected Outcomes

This exercise builds a directory watcher with Java NIO.2, using `WatchService` to receive **change signals** and adding a **rescan/reconciliation** mechanism to recover state when events are lost, particularly when `StandardWatchEventKinds.OVERFLOW` occurs.

After this lesson, you will be able to:

1. Create and register a `WatchService` to monitor direct entries inside a directory.
2. Retrieve `WatchKey` instances via `take()` or `poll(timeout, unit)`.
3. Handle `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`, and `OVERFLOW`.
4. Use `WatchEvent.context()` accurately as a **relative path** against the registered directory.
5. Call `pollEvents()`, process events, and invoke `reset()` for each key.
6. Build a directory-state snapshot using `Files.newDirectoryStream` and `BasicFileAttributes`.
7. Upon receiving `OVERFLOW`, rescan the current state to reconcile the cache instead of assuming lost operations can be replayed individually.
8. Write a standalone Java 17+ example with predictable stdout **without assuming identical event ordering or counts across all OSes**.
9. Understand how to extend this into a long-running watcher supporting multiple directories, clean shutdown, testing, and resource protection.

> **Key takeaway:** `WatchService` is not a reliable transaction log or audit log. It provides signals telling the application **when to re-check the filesystem**. The actual directory state—not individual notifications—is the source of truth when synchronizing current contents.

## 2. Environment Setup

The example uses **JDK 17 or newer** and standard Java library APIs, with no Maven/Gradle or external dependencies.

Check your environment:

```bash
java -version
javac -version
```

You need permissions to create, read, modify, and delete inside the temporary directory used by the JVM. Most of the exercise runs on Windows, Linux, or macOS, though:

- Platforms/providers may differ in timing, ordering, and count of `ENTRY_MODIFY` events.
- `WatchService` may not be fully supported on network filesystems, special mounts, or sandboxed environments.
- Do not try to force the OS to emit a real `OVERFLOW` by creating massive numbers of files; that can overload the system without reproducible results.
- Critical tests must run on the **actual deployment filesystem**, not only on a developer machine.

Required imports typically come from `java.nio.file`, `java.nio.file.attribute`, `java.util`, and `java.util.concurrent`.

## 3. Recap: How `WatchService` Works

A `WatchService` maintains a queue of **signaled `WatchKey`s**. Once an application registers a directory, the filesystem/provider can detect direct changes inside it and enqueue the corresponding key.

```text
                   Filesystem
          create / modify / delete
                      |
                      v
              Register directory
                WatchKey K1
                      |
               key is signaled
                      |
                      v
              WatchService queue
                      |
                      v
         take() / poll() / timed poll()
                      |
                      v
              K1.pollEvents()
                      |
             +--------+---------+
             |                  |
         ENTRY_*             OVERFLOW
             |                  |
         event hint         events lost?
             |                  |
             +--------+---------+
                      |
                      v
             Rescan / reconcile
                      |
                      v
                key.reset()
                      |
           true: continue watching
           false: registration invalid
```

With `Path.register(watcher, kinds...)`, a `WatchKey` represents the registration of a watched path. One key can batch **multiple events**; a single `take()` returns a **key**, not necessarily a single change.

### Event Kinds

| Event kind | Typical Meaning | What to Do |
|---|---|---|
| `ENTRY_CREATE` | A direct entry in the directory appeared | Inspect the entry's state at processing time |
| `ENTRY_MODIFY` | Provider observed a modification | Re-read metadata/content if business logic requires |
| `ENTRY_DELETE` | Direct entry no longer exists under the watched name | Update cache from current state |
| `OVERFLOW` | Provider warns some events may have been lost/dropped | **Rescan the directory** and reconcile cache; do not try to reconstruct every lost operation's order |

**There is no guarantee that one user Save = one `ENTRY_MODIFY`.** Editors may write a temp file and rename; a large write may emit multiple modify events; the system may coalesce them.

## 4. What Does `OVERFLOW` Actually Mean?

`OVERFLOW` signals that the event stream **may no longer be complete**. Dropped changes cannot necessarily be queried back from `WatchService`.

Example:

```text
State the application thinks exists:
  A.txt, B.txt

Filesystem changes rapidly:
  delete A.txt
  create C.txt
  modify B.txt
  create D.txt
  delete C.txt

Event queue overflows:
  ... OVERFLOW ...

Actual current filesystem:
  B.txt, D.txt
```

Relying only on surviving events might leave the cache believing `A.txt` still exists or missing `D.txt`. Seeing overflow requires scanning the directory to see **what currently exists**.

You cannot infer the full sequence of intermediate operations from a final snapshot. For example, `C.txt` was created and deleted before the rescan: the final state retains no trace of C. If business rules require auditing **every event**, you need a source-level transaction log/journal or a tracking system with durable delivery contracts—merely adding `rescan` to `WatchService` does not yield exactly-once delivery.

### Appropriate Recovery Policy

- Mark the registration/directory as needing a **full rescan**.
- Capture a fresh snapshot from the filesystem.
- Diff against the application's previous cached state.
- Process appeared/disappeared/changed entries with **idempotent** logic.
- Replace the cache with the new snapshot once required steps complete.
- Continue watching via `reset()` if the key remains valid.
- Record metrics/logs for overflow occurrences, rescan duration, entry counts, and I/O errors.

For systems caring only about **current state**, this is a sound strategy. For systems needing complete history, use a higher-reliability event source.

## 5. Solution Design: Notifications Are Hints, Snapshot Is State

To recover even when notifications are lost, we choose a simple yet solid design:

1. Create `WatchService` and register the directory first.
2. Take an initial snapshot of direct entries inside the directory.
3. Wait for a `WatchKey`.
4. Drain events. `OVERFLOW` is detected **before** casting `context` to `Path`.
5. For **any key with events**, we **rescan the entire directory** instead of updating single items purely from events. That way, the overflow branch naturally performs reconciliation.
6. Compare old and new snapshots to identify added, removed, and metadata-changed entries.
7. Reset the key; if invalid, stop or schedule re-registration per policy.
8. Periodically rescan even without notifications if detecting drift from crashes or lost events is required.

**Trade-off:** a full rescan per notification is easy to understand and works well for small/medium directories and lessons; it can be costly for directories with millions of entries. Production systems can optimize by updating single entries on normal events and running full rescans on `OVERFLOW`, startup, and periodic intervals. Even when optimized, full reconciliation must still be kept.

### What Does a Snapshot Include?

For example, store a metadata **fingerprint** per entry:

- Relative name/`Path`.
- `size()`.
- `lastModifiedTime()`.
- `isDirectory()`.

This is an **observational state heuristic**, not a cryptographic digest. It may miss content edits if size and final mtime remain unchanged or if the filesystem has coarse timestamp resolution. If the application must detect content edits with higher certainty, add a hash/checksum or producer-supplied version, weighing I/O cost and mid-write races.

## 6. Registration and Initial Snapshot Sequence

Basic pattern:

```java
try (WatchService watcher =
         FileSystems.getDefault().newWatchService()) {

    root.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.ENTRY_DELETE);

    Map<Path, Stamp> known = scanDirectory(root);
    // Loop taking keys and reconciling snapshots...
}
```

This is **illustrative code**; `root` and helpers/imports must be declared. The reason for registering **before** the initial scan: if you scan first and a file changes in the window before registration, you might miss the notification for that change.

Still, registering before scanning **does not make the two steps an atomic transaction**. An entry may change mid-scan; events queued during the scan must still be consumed, and critical data should also have periodic reconciliation or a dedicated snapshot protocol.

In the lesson example, all changes happen inside the same process after registration, making the sequence easier to control.

## 7. `WatchKey`: `take`, `poll`, and `reset`

Three ways to retrieve a key:

```java
WatchKey a = watcher.take();                          // Wait.
WatchKey b = watcher.poll();                          // Do not wait.
WatchKey c = watcher.poll(1, TimeUnit.SECONDS);       // Wait up to 1 s.
```

These lines are illustrative; **do not call all three back-to-back as a required procedure**. Calling `take()` when no events exist can block the thread indefinitely.

- `take()` fits a dedicated watcher thread with shutdown via interrupt/close.
- `poll()` fits integration into a loop that already has other work; avoid busy spinning.
- `poll(timeout, unit)` suits watchers that periodically check stop flags, emit metrics, and run periodic rescans.
- `pollEvents()` reads/drains accumulated events for the key.
- `reset()` returns the key to the ready state if the registration is still valid.

Be careful never to forget `reset()`: a retrieved key may stop signaling further events as expected. If `reset()` returns `false`, the registration is invalid; do not keep waiting on it as if it were still active.

## 8. Complete Java 17+ Example: `WatchService` and Snapshot Recovery

This example is designed to **run self-contained in one process**:

- Creates a dedicated folder in temp.
- Registers create/modify/delete events.
- Captures an empty initial snapshot.
- Creates `item.txt`.
- Uses `WatchService.poll(timeout)` to give itself a chance to consume a `WatchKey`; if no notification arrives within the timeout, rescans anyway to reconcile.
- Deliberately clears the **in-memory cache** to simulate missed events; a full rescan rediscovers the file.
- Deletes the file, and rescans to confirm the directory is empty again.
- Cleans up resources.

**Key point:** the test **does not fake a real `OVERFLOW`**, because providers cannot reliably be forced to emit overflow. However, the branch when `OVERFLOW` actually occurs uses the **same full-rescan mechanism**, and the test explicitly verifies reconciliation independently of OS signals.

Create **`WatchOverflowRecoveryDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class WatchOverflowRecoveryDemo {

    record Stamp(long size, long modifiedMillis, boolean directory) {}

    record KeyResult(
            Map<Path, Stamp> snapshot,
            boolean valid,
            boolean overflow) {}

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-overflow-");
        Path item = directory.resolve("item.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                directory.register(
                        watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Map<Path, Stamp> known = scan(directory);
                System.out.println("Initial entries: " + known.size());

                Files.writeString(
                        item, "v1\n", StandardCharsets.UTF_8,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE);

                WatchKey key = watcher.poll(1500, TimeUnit.MILLISECONDS);
                if (key != null) {
                    KeyResult eventResult = consumeAndRescan(
                            directory, known, key);
                    known = eventResult.snapshot();

                    if (!eventResult.valid()) {
                        throw new IOException("Watch registration invalid");
                    }

                    // Overflow info can be logged/counted in a real
                    // application; the demo omits it due to OS differences.
                } else {
                    // No event within deadline: can still reconcile
                    // the current state.
                    known = scan(directory);
                }

                System.out.println("Exists after create: "
                        + known.containsKey(item.getFileName()));

                // Simulate cache data loss / missed events.
                // Does NOT claim the OS emitted a real OVERFLOW.
                Map<Path, Stamp> stale = Map.of();
                Map<Path, Stamp> recovered = scan(directory);
                System.out.println("Rescan restored entry: "
                        + (!stale.containsKey(item.getFileName())
                           && recovered.containsKey(item.getFileName())));

                Files.delete(item);
                Map<Path, Stamp> afterDelete = scan(directory);
                System.out.println("Entries after delete: "
                        + afterDelete.size());
            }
        } finally {
            Files.deleteIfExists(item);
            Files.deleteIfExists(directory);
        }
    }

    private static Map<Path, Stamp> scan(Path directory)
            throws IOException {

        Map<Path, Stamp> result = new HashMap<>();

        try (DirectoryStream<Path> entries =
                     Files.newDirectoryStream(directory)) {

            for (Path entry : entries) {
                try {
                    BasicFileAttributes attrs = Files.readAttributes(
                            entry,
                            BasicFileAttributes.class,
                            LinkOption.NOFOLLOW_LINKS);

                    result.put(
                            entry.getFileName(),
                            new Stamp(
                                    attrs.size(),
                                    attrs.lastModifiedTime().toMillis(),
                                    attrs.isDirectory()));

                } catch (NoSuchFileException ignored) {
                    // Entry disappeared between list and readAttributes:
                    // the next rescan pass will observe the new state.
                }
            }
        }

        return result;
    }

    private static KeyResult consumeAndRescan(
            Path directory,
            Map<Path, Stamp> oldSnapshot,
            WatchKey key) throws IOException {

        boolean overflow = false;

        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind()
                    == StandardWatchEventKinds.OVERFLOW) {
                overflow = true;
                continue;
            }

            if (event.context() instanceof Path relativeName) {
                // Hint only; may have been modified/deleted/renamed
                // before we actually access this entry.
                Path candidate = directory.resolve(relativeName);
                // No need to open candidate in this demo.
            }
        }

        Map<Path, Stamp> latest;
        boolean valid;

        try {
            // Full scan on every key; on OVERFLOW,
            // this serves directly as the recovery branch.
            latest = scan(directory);
        } finally {
            // Return key to ready state whenever possible,
            // even if scan throws IOException.
            valid = key.reset();
        }

        // oldSnapshot can be compared against latest to find
        // added/removed/changed entries depending on the task.
        return new KeyResult(latest, valid, overflow);
    }
}
```

Run:

```bash
javac WatchOverflowRecoveryDemo.java
java WatchOverflowRecoveryDemo
```

**Expected stdout when the filesystem supports watching, the process has temp-directory I/O permissions, and no errors occur:**

```text
Initial entries: 0
Exists after create: true
Rescan restored entry: true
Entries after delete: 0
```

The program does not print `ENTRY_CREATE` or `ENTRY_MODIFY` counts, because event counts/types **vary inconsistently across providers/OSes**. `watcher.poll(1500, MILLISECONDS)` may return a key or null; either branch still takes a current snapshot, making these output lines meaningful regardless of whether notifications arrive on time.

### Why Does the Code Still Have Limitations?

- `Map<Path,Stamp>` is a **state cache**, not a log of every operation.
- Fingerprints rely solely on `size`, `lastModifiedTime`, and `isDirectory`; edits that leave metadata unchanged cannot be reliably detected.
- Scanning can be affected by concurrent renames/deletes. Having a single writer in the demo keeps verification simple.
- If the directory is deleted or the `WatchKey` becomes invalid, the program throws an error instead of hanging silently.
- The code **does not recursively watch** subdirectories.
- The demo uses bounded-timeout polling so it finishes cleanly. Real watcher servers usually run a long-lived event loop with explicit shutdown/cancellation.
- The code does not trigger a real `OVERFLOW`; the `event.kind() == OVERFLOW` branch is implemented, while lost-state recovery is tested by emptying the `stale` cache.

## 9. Explaining Step One: Register First, Then Scan

In `main`:

```java
directory.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

Map<Path, Stamp> known = scan(directory);
```

Registering first gives `WatchService` the chance to record changes occurring after registration succeeds. Capturing the initial snapshot shows the entries **present at the time the scan observes them**.

Points to distinguish:

- `WatchService` is the notification source.
- `scan(directory)` is how the current state of directory entries is read.
- When an event arrives after the scan, processing the key triggers a rescan.
- When an event was missed, a periodic rescan can repair the cache if the change is still reflected in current state.
- Neither `scan` nor `WatchService` produces a **whole-directory atomic** filesystem snapshot against other writers. If strictly consistent snapshots are required, synchronize writers or use proper storage/versioning designs.

## 10. Explaining Step Two: Receiving Keys and Checking Overflow

Core code:

```java
WatchKey key = watcher.poll(1500, TimeUnit.MILLISECONDS);

if (key != null) {
    KeyResult result = consumeAndRescan(directory, known, key);
    known = result.snapshot();
}
```

`poll(timeout, unit)` waits for a bounded period, preventing the demo from hanging forever if a platform emits no notification. When no key is returned, it yields `null`; that **does not prove the directory did not change**.

Inside `consumeAndRescan`, you must check:

```java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    overflow = true;
    continue;
}
```

**Before** casting `event.context()` to `Path`. For `OVERFLOW`, never assume `context` holds a resolvable filename. `OVERFLOW` does not identify which exact files changed; state cannot be inferred from it.

For normal `ENTRY_*` events, `context()` on a `Path` watcher is typically a **relative name/path**, so:

```java
Path candidate = directory.resolve(relativeName);
```

is merely a candidate at processing time. The file may already have been renamed/deleted, so any open/read call must be prepared for `NoSuchFileException` and other errors.

## 11. Explaining Step Three: Safer Directory Scanning

In the `scan` helper:

```java
try (DirectoryStream<Path> entries =
         Files.newDirectoryStream(directory)) {
    for (Path entry : entries) {
        BasicFileAttributes attrs = Files.readAttributes(
                entry, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
    }
}
```

This excerpt is abbreviated; the full program catches `NoSuchFileException` per entry.

Why use `DirectoryStream`?

- Does not force loading every `Path` into a list before iteration begins.
- Easy resource closing via try-with-resources.
- Pairs cleanly with `readAttributes` to gather metadata for comparison.

### TOCTOU During Rescans

Between `Files.newDirectoryStream` and `Files.readAttributes`, an entry might be deleted. The demo catches `NoSuchFileException` and skips that entry in the current pass. A subsequent rescan converges toward the new state.

If the directory cannot be read due to permissions or I/O errors, **do not mark the directory as empty**. Having a cache flip from "1,000 files" to "empty" simply due to `AccessDeniedException` is a severe bug. Retain the old cache in a needs-retry state, emit metrics/errors, and follow a recovery policy. The demo code lets other errors propagate.

### `NOFOLLOW_LINKS`

`LinkOption.NOFOLLOW_LINKS` inspects metadata on the **link entry itself** rather than following symbolic links automatically. This helps avoid accidentally traversing symlinks outside the root during metadata snapshotting. Yet it does not create a complete sandbox; if the application later opens file contents by path, proper path/symlink policies and OS permissions are still needed.

## 12. Comparing Snapshots: Added, Removed, and Changed Fingerprints

Suppose previously:

```text
Old snapshot:
  A.txt -> size=10, mtime=100
  B.txt -> size=20, mtime=100
```

And after rescanning:

```text
New snapshot:
  B.txt -> size=35, mtime=110
  C.txt -> size=8,  mtime=105
```

Comparison:

- `A.txt`: absent from new snapshot → **removed**.
- `B.txt`: still present yet metadata differs → **changed**.
- `C.txt`: only in new snapshot → **added**.

Illustrative helper example:

```java
static void describeDifference(
        Map<Path, Stamp> previous,
        Map<Path, Stamp> current) {

    for (var entry : current.entrySet()) {
        Stamp old = previous.get(entry.getKey());

        if (old == null) {
            System.out.println("ADDED " + entry.getKey());
        } else if (!old.equals(entry.getValue())) {
            System.out.println("CHANGED " + entry.getKey());
        }
    }

    for (Path name : previous.keySet()) {
        if (!current.containsKey(name)) {
            System.out.println("REMOVED " + name);
        }
    }
}
```

This is an **additional illustrative method** using the main program's `Stamp` record, not part of the demo's fixed stdout. `HashMap` does not define iteration order, so if printing change lists, sort names first for deterministic tests.

### Never Claim Every Modification Is Detected

Metadata fingerprints do not guarantee catching every change:

- A writer might overwrite different content of the **exact same size**.
- `mtime` resolution may be too coarse on some filesystems.
- Timestamp restoration can make metadata look unchanged.
- A file might be swapped for another object with similar metadata.
- An entry could be created and deleted between two scans without ever appearing in a snapshot.

If business logic requires true content-change detection, you can hash files with `MessageDigest`; however, hashing costs I/O, and files can change mid-hash. For immutable snapshots, require producers to publish closed/immutable files, use versioned directories, or use a transactional mechanism.

## 13. Why Reconcile Even Without `OVERFLOW`?

There are two watcher implementation styles:

**A. Event-driven incremental:** update only the entry named by the event. Faster on huge directories, yet more sensitive to missed events, coalescing, and races.

**B. Rescan-driven:** events act purely as signals to rescan the directory. Slower, yet easier to reason about for **final state** and well suited to this lesson.

When the filesystem provider emits `OVERFLOW`, both approaches must fall back to a **full rescan**. With A, take a current snapshot and diff; with B, the handler already runs full rescans, so just flag/log the reason and ensure the cache updates.

A production watcher may use:

```text
START
  -> register
  -> initial full scan
  -> loop:
       wait timed poll
       if key:
         drain events
         if OVERFLOW:
           full rescan
         else:
           process changed paths as hints
         reset key
       if periodic interval elapsed:
         full rescan
       if invalid key:
         remove/re-register per policy
```

Periodic full scans serve as an extra **anti-drift layer**; they do not turn `WatchService` into a complete log or guarantee seeing every intermediate state.

## 14. Building a Continuous Watcher

Illustrative event-loop example (not a standalone class):

```java
while (running.get()) {
    WatchKey key;

    try {
        key = watcher.poll(1, TimeUnit.SECONDS);
    } catch (ClosedWatchServiceException ex) {
        break;
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        break;
    }

    if (key != null) {
        boolean overflow = false;

        try {
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
                    overflow = true;
                    continue;
                }
                // Collect path hints; do not open files blindly.
            }

            if (overflow) {
                // Full rescan + reconcile.
            } else {
                // Incremental handling or rescan per design.
            }
        } finally {
            if (!key.reset()) {
                // Cancel/remove invalid registration.
            }
        }
    }

    // On schedule: check health, stop flag, periodic rescan.
}
```

This is **illustrative code**; `running` (e.g., `AtomicBoolean`), `watcher`, and internal actions must be declared. For long-running operation, add policies for I/O exceptions, backpressure, and state control.

### Stopping the Watcher

- With `take()`, shutdown typically requires `Thread.interrupt()` or closing the `WatchService` from a control thread.
- With `poll(timeout)`, the thread can check the stop flag after timeout; still close the service upon exiting.
- `ClosedWatchServiceException` after an intentional `close()` is normally an expected shutdown condition, not necessarily an error.
- `InterruptedException` must be handled properly, typically restoring the interrupt flag unless there is a reason to swallow it.
- `finally` does not run on power loss or abrupt process kills; on restart, perform an **initial rescan** rather than assuming downtime events were queued.

## 15. Invalid `WatchKey`: Recovering Registrations

If `key.reset()` returns `false`, the `WatchKey` is no longer valid. Causes include:

- The watched directory was deleted or became inaccessible per the provider.
- The application cancelled the registration via `key.cancel()`.
- The `WatchService` was closed.
- The provider lost the ability to watch the target.

Do not simply `continue` the loop expecting more events from that key. In a multi-directory watcher, remove the key from your map and decide whether re-registration is required.

If a directory is deleted and later recreated at the same path, **the old registration does not always recover automatically**. An application needing continuous monitoring must have a timer checking the parent/root, re-registering the new path once it reappears, and rescanning.

Watch out for races: the directory can change right between existence check and registration; always handle exceptions and retry with bounds.

## 16. Watching Multiple Directories

Multiple `Path`s can be registered on the same `WatchService`. Map each `WatchKey` to its directory:

```java
Map<WatchKey, Path> registrations = new HashMap<>();

WatchKey key = directory.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

registrations.put(key, directory);
```

This is an illustrative snippet requiring `directory`, `watcher`, and corresponding imports.

When handling events:

```java
Path root = registrations.get(key);
if (root != null) {
    // Resolve event context against the matching root.
    // On OVERFLOW: rescan this exact root.
}

if (!key.reset()) {
    registrations.remove(key);
}
```

An event from directory A must **never** be resolved against root B. To keep a snapshot cache per directory, use `Map<Path, Snapshot>` or a state object associated with the key.

Do not share one `WatchService` across multiple consumer threads expecting **every thread to receive the same event**. A `WatchKey` queue is normally consumed by one consumer at a time; pick a single consumer loop with clear ownership, then dispatch heavy work to a worker pool if needed.

## 17. Watching a Directory Tree Recursively

In standard Java NIO.2, registering a directory normally delivers events only for **direct entries**:

```text
root/                  <- registered root
  a.txt                <- observed directly
  sub/                 <- notifies that sub appeared
    b.txt              <- does NOT automatically notify on b.txt modify
```

To watch recursively:

1. Walk all existing subdirectories and register **each directory**.
2. When `ENTRY_CREATE` reports a new name, check whether it is a directory (applying your symlink policy).
3. Register the new directory and rescan it.
4. When `OVERFLOW` hits a directory, rescan that directory. If unsure whether the registration tree is still complete, re-walk the tree to discover newly added or removed subdirectories.
5. When a registration becomes invalid, remove it from the map and plan re-registration.
6. Cap the number of watch registrations and I/O cost on large trees.

A race exists between walking and registering subdirectories; a recursive watcher **has no transaction** guaranteeing visibility of simultaneous changes. For workflows that must observe current state, periodic tree rescans provide a useful recovery layer.

## 18. Debouncing and Half-Written Files

An `ENTRY_CREATE` does not guarantee the producer has closed the file. Example:

```text
Producer:
  create report.csv
  write header
  write 10,000 rows
  close file

Consumer:
  sees ENTRY_CREATE right after create
  reads report.csv when producer has written only 10 rows
```

If file ingestion requires complete contents, establish a **publication protocol**:

- Producer writes to a temporary file in a staging directory.
- Producer completes write/flush/close and checks.
- Producer renames/moves to the official target name when ready; if atomicity is required, rely on that guarantee only when the provider truly supports it.
- Consumer watches for the final filename and ignores temp files being written.

Another strategy is **debouncing** `ENTRY_MODIFY`: waiting until a file's metadata stays unchanged for a set quiet window before reading. Yet debouncing does not prove completeness in all cases: a producer might pause longer between batches.

This ties directly to `OVERFLOW`: when a rescan discovers a new file, you still must confirm **the file is ready** per the business protocol before processing.

## 19. Idempotency: Preventing Duplicate Signals from Causing Wrong Results

`WatchService` can report the same file multiple times. If every event triggers "send email" or "debit account", results will be wrong.

Designing for idempotency:

- For cache synchronization, applying final-state updates repeatedly is safe.
- For file ingestion, record processed file/version/hash/transaction IDs so files are not imported twice.
- For tasks with side effects, use a queue/job state machine (`PENDING/RUNNING/COMPLETED`) and explicit retry rules.
- If a file is replaced under the same name, distinguish file versions using trusted metadata or producer-published content versions.
- Do not treat `event.count()` as the number of business actions to execute. Count can reflect coalesced events, not logical operations.

When overflow loses event ordering, a state-based/idempotent consumer recovers far more easily than a consumer executing side effects per notification.

## 20. Testing `OVERFLOW` Deterministically: Simulating Event Loss in the Processing Layer

Real `OVERFLOW` depends on system/provider limits; forcing tens of thousands of files is neither portable nor safe. Instead, test **recovery behavior** by injecting a "stale cache" state or an event-handler abstraction.

In the complete program, we deliberately do:

```java
Map<Path, Stamp> stale = Map.of();       // Cache missed an entry.
Map<Path, Stamp> recovered = scan(dir);  // Actual state.

boolean restored = recovered.containsKey(Path.of("item.txt"));
```

This is an illustrative snippet, with `dir` declared in the appropriate context; the standalone example uses `directory`.

This **does not prove the OS emitted `OVERFLOW`**, yet it proves the rescan logic rediscovers existing files when the cache is missing entries. You can expand tests:

1. Old cache holds `deleted.txt` though the real file was deleted → rescan must remove it.
2. Old cache lacks `new.txt` → rescan must add it.
3. Old cache holds stale metadata for `edited.txt` → rescan observes the new fingerprint.
4. Files created and deleted before rescan → history cannot be reconstructed; accept this boundary.
5. Scan fails with `AccessDeniedException` → keep cache in an **uncertain** state and report error; do not swap to an empty map.
6. Event handler receives a synthetic `OVERFLOW` through a test/stub abstraction (without pretending it came from the OS) → verify rescan and metrics are triggered.

What must be tested is **that reconciliation is triggered and the final state is accurate**, not "how many events" a particular OS happens to emit in a few milliseconds.

## 21. Practical Testing Under Continuous Changes

An integration suite can:

- Create/modify/delete files across multiple `poll` cycles.
- Rename files within the same directory.
- Create files in subdirectories (verifying watches are not automatically recursive).
- Create files in batches.
- Modify files while the handler is scanning.
- Restart the watcher after changes occurred offline.
- Revoke directory read permission **only inside a test environment**, confirming no false empty state is recorded.
- Stop the watcher via interrupt/close and verify resource release.
- Run on Linux/Windows/macOS and real deployment filesystems if supported.

**Never write assertions** expecting a single `Files.writeString` to always emit exactly one `ENTRY_CREATE` and one `ENTRY_MODIFY` in a fixed order. Integration tests should wait for **eventual state** within a reasonable deadline; diff/recovery algorithms should be unit-tested with synthetic snapshots for deterministic output.

### Example Sequence of Operations

```text
t0  register root
t1  initial scan: {}
t2  create a.txt
t3  event signal / rescan: {a.txt}
t4  modify a.txt
t5  event signal / rescan: {a.txt updated}
t6  delete a.txt
t7  rescan: {}
```

`t3` and `t5` may not correspond one-to-one with single `WatchKey`s across all providers. Therefore, tests should assert that the cache eventually reflects `{a.txt}` and then `{}` after deletion, rather than comparing raw event counts.

## 22. Repeated `OVERFLOW`: Performance and Backpressure

Repeated `OVERFLOW` events usually signal that the application cannot keep up with change rates, event processing is too slow, or the provider has tight limits.

Mitigations:

1. **Shorten work inside the watch loop:** only collect event hints and offload heavy work to a bounded queue.
2. **Coalesce work by path:** if the same file produces 100 modify events, schedule only one final-state check per policy.
3. **Add sensible debouncing** when producers perform bursts of small edits.
4. **Cap worker concurrency** so disk/CPU are not saturated.
5. **Coordinate rescans:** never let 1,000 overflow events launch 1,000 concurrent full scans of the same directory. Coalesce into one "dirty" flag and one in-flight rescan.
6. **Track metrics:** overflow count, queue delay, scan duration, watched directory count, entry count, and error rates.
7. **Run periodic reconciliation** to recover from missed events or downtime.
8. **Re-evaluate architecture:** if a directory sees millions of changes/sec, `WatchService` + full rescan may be the wrong tool. Pick a message queue, database change log, or proper upstream protocol.

Do not try to solve overflow merely by **increasing a `ByteBuffer` size** in Java; watch notification queues are managed by the OS/provider and lack a single portable knob for all limits.

## 23. Error Handling and Uncertain States

A production watcher must distinguish:

| Scenario | Recommended Behavior |
|---|---|
| `watcher.poll(...) == null` | No key within timeout; periodic rescan may run |
| `OVERFLOW` | Mark dirty, full rescan, reconcile |
| `key.reset() == false` | Registration invalid; remove, consider re-registering |
| `Files.newDirectoryStream` fails | Do not treat directory as empty; keep old cache and report error |
| Entry vanishes during `readAttributes` | Skip that entry on this pass; retry/reconcile per policy |
| `AccessDeniedException` | Check process OS permissions, parent directory ACLs, mount |
| `ClosedWatchServiceException` | Usually shutdown; if unintended, investigate lifecycle |
| `InterruptedException` | Restore interrupt flag and exit/retry per policy |
| `ENTRY_CREATE` on incomplete file | Wait for publish protocol, bounded retries, or debounce |
| Out of memory storing large snapshots | Bound data, use an index/state store, partition watchers |
| File modified during hashing | Data is not an atomic snapshot; requires producer contract |

If a full rescan fails, a strict design puts the watcher into **DEGRADED/NEEDS_RESCAN** state rather than replacing the cache with an incomplete snapshot. For stability, log errors and schedule retries with backoff; never spin in a hot loop where persistent I/O errors burn CPU.

## 24. Security When Handling Files from Watched Directories

Risks that `OVERFLOW` recovery does not eliminate:

- **Path traversal / symlink escape:** `directory.resolve(event.context())` is not a security boundary if an attacker controls the namespace; validate against root and restrict process permissions.
- **Symlink races:** a file can be swapped between metadata inspection and opening. `NOFOLLOW_LINKS` on a single `readAttributes` call does not secure subsequent I/O.
- **Distrust newly appeared files:** an untrusted producer may drop malformed content, oversized payloads, zip bombs, or scripts; validate format and quotas.
- **OS permissions:** `WatchService` grants no file read access. A process can receive notifications yet be denied content reads.
- **Confidential files:** never log full file contents or paths carrying sensitive data.
- **Multi-tenant:** verify business authorization before processing another tenant's files. The OS tracks process identity, not per-request tenants.
- **Executing code from watchers:** never auto-execute newly discovered files without trusted origin checks, signatures/approvals, and isolation.
- **Accidental deletion:** reconciliation is not an automatic `delete` command. When an entry disappears in a scan, apply confirmation policies and handle I/O errors before deleting records in databases or backups.

Filesystem events are **untrusted business inputs**. Validate origin, schema, and state before triggering side effects.

## 25. Extension: Designing Around a "Dirty Directory" Model

For watchers facing rapid continuous changes, a clean architecture is managing **dirty flags**:

```text
WatchService consumer:
  on ENTRY_*:
      mark path/dir as needing inspection
  on OVERFLOW:
      mark directory FULL_RESCAN_REQUIRED
  reset key

Reconciliation worker:
  if FULL_RESCAN_REQUIRED:
      scan directory
      diff snapshot
      apply idempotent changes
      clear flag only when scan + commit succeed
  else:
      inspect dirty paths
      apply state changes
```

Key concurrency rules:

- Never clear a dirty flag if a new change arrived **during** the rescan/commit. Use a version/generation counter or locked queue to avoid losing signals.
- Do not run multiple concurrent full rescans on the same directory without reason.
- Retry failed scans/commits without declaring data synchronized.
- Keep an independent periodic scan schedule to catch missed events.
- If an entry is created and deleted mid-scan, do not infer full history from the final snapshot.
- Backpressure: when downstream work slows down, prevent unbounded queues from causing OOM.

This is an advancement over the single-thread demo. You do not need a full concurrency framework to grasp the core of `WatchService` and overflow handling.

## 26. Common Mistakes in Practice Exercises

1. **Ignoring `OVERFLOW`**: caches can drift permanently after missed events.
2. **Casting `event.context()` to `Path` before checking `OVERFLOW`**: overflow data does not represent a valid file path.
3. **Believing individual events form an exact history**: events can be coalesced or lost; there is no exactly-once guarantee.
4. **Forgetting `key.reset()`**: misses all subsequent notifications.
5. **Not checking `reset() == false`**: invalid registrations linger in tracking structures.
6. **Using `take()` on the main thread with no shutdown path**: blocks forever when no events arrive.
7. **Using `poll()` in a busy loop**: spikes CPU when idle.
8. **Registering after scanning and assuming no race**: changes right before registration can be missed.
9. **Treating `ENTRY_CREATE` as "file finished writing"**: producer may still be writing.
10. **Running heavy work inside the watcher event loop**: increases backlog and triggers overflows.
11. **Using metadata snapshots and claiming all content edits are detected**: hashes/versions may be necessary.
12. **Returning `Map.of()` and wiping cache when scan fails**: confuses "unreadable" with "empty directory".
13. **Assuming watching the root is recursive**: subdirectories must be registered individually.
14. **Trying to fix `OVERFLOW` by increasing a read buffer**: does not change provider event-queue limits.
15. **Creating millions of files to "unit test overflow"**: non-portable and stresses the machine; test recovery via injection/synthetic state.
16. **Trusting test behavior on a single OS**: event counts and ordering vary across providers.
17. **Ignoring symlinks/TOCTOU**: risks reading files outside intended scope.
18. **Skipping idempotency**: a single file edit can trigger duplicate processing.
19. **Failing to recover across restarts**: downtime notifications are not persisted by `WatchService`.
20. **Closing the watcher without handling `ClosedWatchServiceException`**: raises spurious shutdown errors.
21. **Keeping invalid keys in maps**: leaks references and breaks tracking.
22. **Using `WatchService` as a financial/legal audit log**: lacks guarantees for intermediate operations.
23. **Leaving queues/concurrency unbounded**: memory/CPU exhaustion under rapid directory churn.
24. **Treating scan output as an atomic snapshot**: the filesystem can change mid-walk without a writer protocol.
25. **Reconciling cache yet forgetting to reset the key timely**: stops future notifications.

## 27. Extension Exercises

### Exercise 1 — Added/Removed/Changed Diff

Write `diff(oldSnapshot, newSnapshot)` returning three sets: `added`, `removed`, `changed`. Reuse the `Stamp` record from the example. Test with synthetic data so stdout does not depend on `WatchService`.

### Exercise 2 — Force Reconciliation on Missed Events

Create `A.txt` without feeding its event into the cache; call `scan` and update the cache. Next delete the file and rescan to remove the missing entry. Explain why this tests recovery yet **does not prove the OS emitted `OVERFLOW`**.

### Exercise 3 — 30-Second Watch Loop

Use `poll(500, TimeUnit.MILLISECONDS)` for 30 seconds while you manually create/edit/delete files. Do not print every raw event uncontrolled; summarize key count, overflow count, and rescan count.

### Exercise 4 — Debounce

Add a `Path → lastHintTime` map, coalesce multiple modify hints within 300–500 ms, and process only after the quiet window elapses; still verify file completeness using a producer contract.

### Exercise 5 — Recursive Watching

Walk the tree and register every directory. When `ENTRY_CREATE` is a directory, register it and scan its contents. Remove keys from the map when invalid. Add periodic full-tree rescans to cover race windows.

### Exercise 6 — Recovery After Restart

Start the watcher, create files, stop the process, modify/delete/add files while offline, then restart. Demonstrate that the initial scan restores **final state**, while not revealing the exact intermediate operations performed during downtime.

### Exercise 7 — Resource Bounding

Simulate 10,000 event hints for the same filename via a unit-test abstraction (without creating 10,000 real files). Verify scheduling coalesces into one final-state check and the queue never grows unboundedly.

## 28. Self-Check Questions

**1.** Does `OVERFLOW` provide the names of files whose events were lost?  
**No.** It only warns of potential lost notifications; you must rescan current state.

**2.** After a full rescan, can you always tell which files were created and deleted between two scans?  
**Not reliably.** The final state may leave no trace of intermediate operations.

**3.** Why must the event handler call `key.reset()`?  
**So the key can continue receiving signals** if the registration remains valid.

**4.** What does `key.reset() == false` mean?  
**The registration is invalid**; remove it from watcher state and consider re-registering.

**5.** Does `poll(timeout)` returning null prove no files changed?  
**No.** It only means no key was dequeued within the wait period, subject to provider limits.

**6.** Why should snapshots be read directly from the filesystem rather than trusting the event list?  
**Because events can be coalesced, delayed, or lost**, whereas a snapshot reflects state observed at scan time.

**7.** Can `ENTRY_CREATE` be handled by parsing the file immediately?  
**Not by default.** The producer may still be writing; use an appropriate publish protocol, validation, or debounce.

**8.** Does `Files.newDirectoryStream(root)` scan recursively?  
**No.** It lists only direct entries inside `root`.

**9.** Does a size + mtime fingerprint detect every content modification?  
**No.** A digest, version, or snapshot protocol may be required for stricter guarantees.

**10.** Why shouldn't you stress-create millions of files just to unit-test overflow?  
**Because results depend on the provider and can overload the environment**; test recovery independently of the event source.

**11.** When a full rescan throws `AccessDeniedException`, should you set the cache to an empty map?  
**No.** "Unreadable" does not mean "no entries"; maintain an uncertain state and retry.

**12.** Can `WatchService` act as an exactly-once audit log?  
**No.** It does not guarantee durable persistence and replay of every change.

## 29. Pre-Deployment Checklist

- [ ] Identify root directories and file types to watch.
- [ ] Verify process permissions and filesystem/provider support.
- [ ] Register roots before initial scan where appropriate.
- [ ] Define snapshot cache and required accuracy of metadata/hashes/versions.
- [ ] Receive `WatchKey`s via `take` or timed `poll`, with a shutdown policy.
- [ ] Drain `pollEvents()` and **check `OVERFLOW` before casting context**.
- [ ] On `OVERFLOW`, run a full rescan and reconcile against actual state.
- [ ] Schedule periodic reconciliation/initial scans when recovery from missed events is needed.
- [ ] Guarantee `key.reset()` and handle invalid keys.
- [ ] Maintain a registration map when watching multiple directories.
- [ ] Never assume recursive watches; register subdirectories individually.
- [ ] Use idempotent processing, bounded queues, and proper debouncing.
- [ ] Handle half-written files, renames, symlinks, and TOCTOU races.
- [ ] Never turn scan failures into false empty states.
- [ ] Track metrics for overflows, latency, rescan errors, and queue depth.
- [ ] Unit-test recovery deterministically via synthetic state and integration-test on real target OSes.
- [ ] Never assert fixed counts or ordering of `ENTRY_MODIFY` events.
- [ ] Test restarts to verify caches rebuild from snapshots.
- [ ] Close `WatchService`, handle interrupts, and cancel keys when no longer needed.
- [ ] If every single operation must be captured, choose a journal or transaction log instead.

## 30. Summary

- **`WatchService` is a directory-change notification system**, not a complete log or consistent filesystem snapshot.
- **`OVERFLOW` signals that some events may have been lost**. Dropped events cannot be queried back directly; you must **rescan current state**.
- A simpler, more reliable exercise design is **register → scan → poll/take → drain events → rescan/reconcile → reset → repeat**.
- **WatchEvent.context()` for `ENTRY_*` is normally a relative `Path`**; resolve it against the exact registered directory. For `OVERFLOW`, never cast `context` to `Path`.
- **Metadata snapshots detect only differences in what they record**; size/mtime are insufficient for all data requirements.
- **Unit-test recovery with a synthetic stale cache**, without relying on real overflows; integration tests verify eventual state rather than fixed event counts.
- For production-grade watchers: add shutdown, re-registration, periodic rescans, race handling, idempotency, resource limits, and observability.

### Java 17 References

- [WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
- [WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html)
- [WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html)
- [StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)
- [Path.register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...))
- [Files.newDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newDirectoryStream(java.nio.file.Path))
- [BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)

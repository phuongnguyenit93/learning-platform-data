# Practical Exercise: Watching Directories with `WatchService` and Handling `OVERFLOW`

## 1. Expected Outcomes

This exercise builds a directory watcher with Java NIO.2, using `WatchService` to receive **change signals** and adding a **rescan/reconciliation** mechanism to recover state when events are lost, especially upon `StandardWatchEventKinds.OVERFLOW`.

After this lesson, you will be able to:

1. Create and register a `WatchService` monitoring direct entries inside a directory.
2. Retrieve a `WatchKey` via `take()` or `poll(timeout, unit)`.
3. Handle `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`, and `OVERFLOW`.
4. Use `WatchEvent.context()` properly as a **relative path** against the registered directory.
5. Call `pollEvents()`, process events, and call `reset()` for each key.
6. Build a directory state snapshot using `Files.newDirectoryStream` and `BasicFileAttributes`.
7. Upon receiving `OVERFLOW`, rescan current state to reconcile the cache instead of assuming every lost operation can be replayed.
8. Write a standalone Java 17+ example with predictable stdout without **assuming consistent event order/counts across every OS**.
9. Understand how to scale into a long-running watcher supporting multiple directories, clean shutdown, testing, and resource protection.

> **Core idea:** `WatchService` is not a reliable transaction log or audit log. It provides signals telling the application **when to re-inspect the filesystem**. Actual directory state, not individual notifications, is the source of truth when syncing current contents.

## 2. Environment Setup

The example uses **JDK 17 or later** and Java Standard Library APIs, with no Maven/Gradle or external dependencies.

Check your environment:

```bash
java -version
javac -version
```

You need permission to create, read, modify, and delete inside the temporary directory used by the JVM. Most of this exercise runs on Windows, Linux, or macOS, however:

- Platforms/providers can differ in timing, order, and count of `ENTRY_MODIFY` events.
- `WatchService` may not be fully supported on network filesystems, special mounts, or sandboxed environments.
- Do not try to force the OS to emit a real `OVERFLOW` by creating huge numbers of files; that can overload the system without producing repeatable results.
- Critical tests should run on the **actual deployment filesystem**, not only on a development machine.

Required imports typically come from `java.nio.file`, `java.nio.file.attribute`, `java.util`, and `java.util.concurrent`.

## 3. Recap: How `WatchService` Works

A `WatchService` maintains a queue of **signalled `WatchKey`s**. Once an application registers a directory, the filesystem/provider can observe direct changes inside it and enqueue the corresponding key.

```text
                   Filesystem
          create / modify / delete
                      |
                      v
              Register directory
                WatchKey K1
                      |
               key is signalled
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
         event hint       missed events?
             |                  |
             +--------+---------+
                      |
                      v
             Rescan / reconcile
                      |
                      v
                key.reset()
                      |
           true: keep watching
           false: registration invalid
```

With `Path.register(watcher, kinds...)`, one `WatchKey` represents the registration of a watched path. One key can batch **multiple events**; one `take()` returns a **key**, not necessarily a single change.

### Event Kinds

| Event kind | Common Meaning | Recommended Action |
|---|---|---|
| `ENTRY_CREATE` | A direct entry appeared in the directory | Inspect entry state at processing time |
| `ENTRY_MODIFY` | Provider observed a modification | Re-read metadata/content if required by business logic |
| `ENTRY_DELETE` | Direct entry no longer exists under the watched name | Update cache from current state |
| `OVERFLOW` | Provider reports events may have been lost/dropped | **Rescan directory** and reconcile cache; do not try to reconstruct every change in order |

**There is no guarantee that one Save equals one `ENTRY_MODIFY`.** Editors may write a temp file and rename; one large write can emit multiple modify events; the system can coalesce them.

## 4. What Does `OVERFLOW` Really Mean?

`OVERFLOW` is a signal that the event stream **may no longer be complete**. Dropped changes generally cannot be queried back from `WatchService`.

Example:

```text
State the application thinks exists:
  A.txt, B.txt

Filesystem changes very rapidly:
  delete A.txt
  create C.txt
  modify B.txt
  create D.txt
  delete C.txt

Event queue overflows:
  ... OVERFLOW ...

Current filesystem:
  B.txt, D.txt
```

Relying solely on surviving events could leave the cache believing `A.txt` still exists or missing `D.txt`. Seeing overflow requires scanning the directory to learn **what actually exists right now**.

You cannot infer the full intermediate sequence of operations from a final snapshot. For example, `C.txt` was created and deleted before the rescan: the final state shows no trace of C. If business logic requires auditing **every event**, you need a source-side transaction log/journal or a tracking system with durable guarantees—adding `rescan` to `WatchService` does not achieve exactly-once.

### Proper Recovery Policy

- Mark the registration/directory as needing a **full rescan**.
- Capture a fresh snapshot from the filesystem.
- Diff against the application's prior cached state.
- Process added/removed/changed entries using **idempotent** logic.
- Replace the cache with the new snapshot once required steps finish.
- Resume watching with `reset()` if the key remains valid.
- Record metrics/logs for overflow, rescan duration, entry count, and I/O errors.

For systems concerned only with **current state**, this is a sound strategy. For systems needing complete history, use a higher-reliability event source.

## 5. Solution Design: Notifications Are Hints, Snapshots Are State

To ensure this exercise recovers even when notifications are lost, we choose a simple yet solid design:

1. Create `WatchService` and register the directory first.
2. Capture an initial snapshot of direct entries inside the directory.
3. Wait for a `WatchKey`.
4. Drain the event list. Detect `OVERFLOW` **before** casting `context` to `Path`.
5. For **any key with events**, **rescan the entire directory** instead of patching individual items from events. That way, the overflow branch naturally performs reconciliation.
6. Compare old and new snapshots to identify added, removed, and metadata-changed entries.
7. Reset the key; if invalid, stop or schedule re-registration per policy.
8. Periodically rescan even without notifications if you must detect drift caused by failures or dropped events.

**Trade-off:** a full rescan per notification is easy to reason about and suits small/medium directories and learning; it can be costly for directories with millions of entries. Production can optimize by updating per entry for normal events and doing full rescans only on `OVERFLOW`, startup, and periodic intervals. Even when optimized, keep full reconciliation intact.

### What Goes into a Snapshot?

For instance, store a metadata **fingerprint** per entry:

- Relative name/`Path`.
- `size()`.
- `lastModifiedTime()`.
- `isDirectory()`.

This is a **state-observation heuristic**, not a cryptographic digest. It may miss content edits if size and final mtime match or if the filesystem has coarse timestamp resolution. If the application must detect content changes more reliably, add a hash/checksum or producer-supplied version, weighing I/O cost and races while files are being written.

## 6. Sequence of Registration and Initial Snapshot

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
    // Loop polling keys and reconciling snapshots...
}
```

This is **illustrative code**, requiring `root`, helpers, and imports. Why register **before** the first scan: if you scan first and a file changes before registration completes, you might miss the notification for that change.

However, registering first then scanning **does not make the two steps an atomic transaction**. An entry can change mid-scan; events queued during that window must still be drained, and critical data should pair this with periodic reconciliation or a dedicated snapshot protocol.

In the lesson example, all changes happen in the same process after registration, making ordering straightforward to control.

## 7. `WatchKey`: `take`, `poll`, and `reset`

Three ways to retrieve a key:

```java
WatchKey a = watcher.take();                          // Wait.
WatchKey b = watcher.poll();                          // Do not wait.
WatchKey c = watcher.poll(1, TimeUnit.SECONDS);       // Wait up to 1 s.
```

These lines are illustrative; **do not call all three back-to-back as a required sequence**. Calling `take()` when no events occur can block the thread indefinitely.

- `take()` fits a dedicated watcher thread with shutdown via interrupt/close.
- `poll()` fits integrating into a loop already doing other work; avoid busy spinning.
- `poll(timeout, unit)` suits watchers that need regular intervals to check stop flags, metrics, and periodic rescans.
- `pollEvents()` reads/drains accumulated events for the key.
- `reset()` transitions the key back to ready if the registration is still valid.

Be careful never to forget `reset()`: an unreset key will stop delivering subsequent signals as expected. If `reset()` returns `false`, the registration is invalid; stop waiting on it as if it were still active.

## 8. Complete Java 17+ Example: `WatchService` and Snapshot Recovery

This example is designed to **run self-contained in one process**:

- Creates a dedicated directory in temp.
- Registers create/modify/delete events.
- Captures an empty snapshot.
- Creates `item.txt`.
- Uses `WatchService.poll(timeout)` for a chance to consume the `WatchKey`; if no notification arrives within the wait window, rescans anyway to reconcile.
- Deliberately clears the **in-memory cache** to simulate missed notifications; a full rescan rediscovers the file.
- Deletes the file and rescans to confirm the directory returns to empty.
- Cleans up resources.

**Key point:** the test **does not fake a real `OVERFLOW`**, because providers cannot be reliably forced to emit overflow. Yet the branch when a real `OVERFLOW` occurs executes the **exact same full-rescan mechanism**, and the test actively verifies reconciliation independent of OS signals.

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

                    // Overflow count could be logged/metered in a real
                    // app; this demo omits printing it as OSes vary.
                } else {
                    // No event within deadline: can still reconcile
                    // current state directly.
                    known = scan(directory);
                }

                System.out.println("Exists after create: "
                        + known.containsKey(item.getFileName()));

                // Simulate stale cache / missed events.
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
                    // Entry vanished between listing and readAttributes:
                    // the next rescan will see the updated state.
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
                // Only a hint; entry may already be modified/deleted/renamed
                // before we actually access it.
                Path candidate = directory.resolve(relativeName);
                // No need to open candidate in this demo.
            }
        }

        Map<Path, Stamp> latest;
        boolean valid;

        try {
            // Full scan for every key; on OVERFLOW,
            // this serves directly as the recovery path.
            latest = scan(directory);
        } finally {
            // Return key to ready state when possible,
            // even if scan throws IOException.
            valid = key.reset();
        }

        // oldSnapshot can be diffed against latest to find
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

**Expected stdout when the filesystem supports watching, the process has temp-directory I/O permissions, and no error occurs:**

```text
Initial entries: 0
Exists after create: true
Rescan restored entry: true
Entries after delete: 0
```

The program does not print `ENTRY_CREATE` or `ENTRY_MODIFY` counts, because event counts and kinds are **unstable across providers/OSes**. `watcher.poll(1500, MILLISECONDS)` may return a key or `null`; both paths capture the current snapshot, so the output lines remain meaningful regardless of whether notifications arrived on time.

### Why Does This Code Still Have Limitations?

- `Map<Path,Stamp>` is a **state cache**, not a log of every operation.
- The fingerprint relies only on `size`, `lastModifiedTime`, and `isDirectory`; it cannot reliably catch every edit if metadata stays unchanged.
- Scanning can be affected by concurrent renames/deletes. Only one writer exists in the demo, keeping verification straightforward.
- If the directory is deleted or the `WatchKey` becomes invalid, the program throws instead of hanging silently.
- The code **does not recursively watch** subdirectories.
- The demo polls for a bounded time to exit cleanly. Real watcher servers usually run a long-lived event loop with explicit shutdown/cancellation.
- The code does not trigger a real `OVERFLOW`; the `event.kind() == OVERFLOW` branch is implemented, while state loss is tested by emptying the `stale` cache.

## 9. Explaining Step One: Register First, Then Scan

In `main`:

```java
directory.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

Map<Path, Stamp> known = scan(directory);
```

Registering first gives `WatchService` a chance to record changes occurring after registration succeeds. Capturing the initial snapshot reveals the entries **present at the time the scan observes the directory**.

Points to distinguish:

- `WatchService` is the notification source.
- `scan(directory)` reads the current state of directory entries.
- When an event arrives after scanning, handling the key triggers a rescan.
- When an event is lost, periodic rescanning can repair the cache if the change is still visible in current state.
- Neither scanning nor `WatchService` yields a **directory-wide atomic filesystem snapshot** against external writers. If strict snapshot consistency is required, coordinate writers or use an appropriate storage/versioning design.

## 10. Explaining Step Two: Receiving Keys and Checking Overflow

Core code:

```java
WatchKey key = watcher.poll(1500, TimeUnit.MILLISECONDS);

if (key != null) {
    KeyResult result = consumeAndRescan(directory, known, key);
    known = result.snapshot();
}
```

`poll(timeout, unit)` waits with a bound so the demo does not hang forever if the platform emits no notification. When no key is ready, it returns `null`; that **does not prove the directory is unchanged**.

Inside `consumeAndRescan`, you must check:

```java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    overflow = true;
    continue;
}
```

**before** casting `event.context()` to `Path`. For `OVERFLOW`, never assume `context` holds a resolvable filename. `OVERFLOW` does not identify which files changed; state cannot be inferred from it.

For normal `ENTRY_*` events, `context()` for a directory watcher is typically a **relative name/path**, so:

```java
Path candidate = directory.resolve(relativeName);
```

is merely a candidate at handling time. The file may already have been renamed or deleted, so any open/read attempt must handle `NoSuchFileException` and other errors.

## 11. Explaining Step Three: Scanning a Directory More Safely

In helper `scan`:

```java
try (DirectoryStream<Path> entries =
         Files.newDirectoryStream(directory)) {
    for (Path entry : entries) {
        BasicFileAttributes attrs = Files.readAttributes(
                entry, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
    }
}
```

This is an abbreviated excerpt; the complete program catches `NoSuchFileException` per entry.

Why use `DirectoryStream`?

- Does not force loading all `Path` objects into a list before iteration begins.
- Easy to close via `try-with-resources`.
- Pairs cleanly with `readAttributes` to collect comparison metadata.

### TOCTOU During Rescan

Between `Files.newDirectoryStream` and `Files.readAttributes`, an entry can be deleted. The demo catches `NoSuchFileException` and skips that entry in the current pass. A subsequent rescan will converge toward the new state.

If the directory cannot be read due to permissions or I/O errors, **do not treat the directory as empty**. Flipping a cache from "1,000 files" to "empty" just because of an `AccessDeniedException` is a severe bug. Keep the prior cache marked for retry, emit metrics/errors, and apply a recovery policy. The demo lets other errors propagate.

### `NOFOLLOW_LINKS`

`LinkOption.NOFOLLOW_LINKS` inspects metadata on the **link entry itself** rather than following symbolic links automatically. This helps avoid inadvertently following a symlink outside root during metadata snapshotting. However, it does not create a complete sandbox; if the application later opens file contents by path, proper path/symlink policies and OS permissions are still needed.

## 12. Diffing Snapshots: Added, Removed, and Changed Entries

Suppose before:

```text
Old snapshot:
  A.txt -> size=10, mtime=100
  B.txt -> size=20, mtime=100
```

And after rescan:

```text
New snapshot:
  B.txt -> size=35, mtime=110
  C.txt -> size=8,  mtime=105
```

Comparison:

- `A.txt`: absent from new snapshot → **removed**.
- `B.txt`: still present with different metadata → **changed**.
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

This is an **extra illustrative method** using the main program's `Stamp` record and is not part of the demo's fixed stdout. `HashMap` does not guarantee iteration order, so sort names before printing if deterministic test output is needed.

### Do Not Claim Every Edit Is Detected

Metadata fingerprints do not guarantee detecting every change:

- A writer may write different content of the **exact same size**.
- `mtime` resolution may be too coarse on some filesystems.
- Timestamp-restoring operations can make metadata look unchanged.
- A file may be replaced with a different object bearing similar metadata.
- An entry may be created and deleted between two scans without appearing in any snapshot.

If business logic must detect true content edits, hash files with `MessageDigest`; note hashing costs I/O, and files can change mid-hash. For immutable snapshots, require producers to publish closed/immutable files, use versioned directories, or use an appropriate transactional mechanism.

## 13. Why Reconcile Even Without `OVERFLOW`?

There are two ways to implement a watcher:

**A. Event-driven incremental:** updates only the entry named by an event. Faster for huge directories, yet more sensitive to dropped events, coalescing, and races.

**B. Rescan-driven:** treats events purely as hints to rescan the directory. Slower, yet easier to reason about **eventual state** and well suited to this lesson.

When the filesystem provider emits `OVERFLOW`, both designs must support a **full rescan**. With A, you take a current snapshot and diff; with B, the handler already runs a full rescan, so you simply flag/log the reason and ensure the cache updates.

A production watcher might run:

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

Periodic full scans are an extra **anti-drift layer**; they do not turn `WatchService` into a complete log or guarantee seeing every intermediate state.

## 14. Building a Continuously Running Watcher

Illustrative event loop example (not a standalone class):

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

This is **illustrative code**; `running` (e.g. `AtomicBoolean`), `watcher`, and internal actions must be declared. In long-running services, govern I/O exception policies, backpressure, and state carefully.

### Stopping the Watcher

- With `take()`, shutdown typically requires `Thread.interrupt()` or closing the `WatchService` from a control thread.
- With `poll(timeout)`, the thread can check a stop flag after timeout; still close the service on exit.
- `ClosedWatchServiceException` after an intentional `close()` is normally a valid shutdown condition, not necessarily an error.
- `InterruptedException` must be handled cleanly, usually restoring the interrupt flag unless there is a reason to clear it.
- `finally` does not run on power loss or abrupt process kill; on restart, perform an **initial rescan** rather than assuming downtime events were saved.

## 15. Invalid `WatchKey`: Recovering Registrations

If `key.reset()` returns `false`, the `WatchKey` is no longer valid. Common causes:

- The watched directory was deleted or became inaccessible per the provider.
- The application cancelled the registration via `key.cancel()`.
- `WatchService` was closed.
- The provider lost the ability to watch the target.

Do not simply `continue` the loop expecting more events from that key. In a multi-directory watcher, remove the key from the map and decide whether to re-register.

If a directory is deleted and recreated at the same path, **the old registration does not always auto-recover**. An application needing continuous monitoring should run a timer checking parent/root, re-register the new path once it exists again, and rescan.

Watch out for races: the directory can change between checking existence and registering; always handle exceptions and use bounded retries.

## 16. Watching Multiple Directories

You can register multiple `Path`s on the same `WatchService`. Map each `WatchKey` to its directory:

```java
Map<WatchKey, Path> registrations = new HashMap<>();

WatchKey key = directory.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

registrations.put(key, directory);
```

This is an illustrative snippet requiring `directory`, `watcher`, and imports.

When handling:

```java
Path root = registrations.get(key);
if (root != null) {
    // Resolve event context against its matching root.
    // On OVERFLOW: rescan this exact root.
}

if (!key.reset()) {
    registrations.remove(key);
}
```

An event from directory A must **never** be resolved against root B. To maintain a snapshot cache per directory, use `Map<Path, Snapshot>` or a state object keyed by registration.

Do not share one `WatchService` across multiple consumer threads assuming **every thread receives the same event**. A `WatchKey` queue is consumed by whichever consumer picks it up; assign clear single-consumer ownership to the watch loop, and dispatch heavy work to a worker pool if needed.

## 17. Watching a Directory Tree Recursively

In standard Java NIO.2, registering a directory normally yields events only for **direct children**:

```text
root/                  <- register root
  a.txt                <- observed directly
  sub/                 <- sub appearance detected
    b.txt              <- does NOT automatically receive modify for b.txt
```

To watch recursively:

1. Walk all existing subdirectories and register **each directory**.
2. When `ENTRY_CREATE` reports a new name, check whether it is a directory (applying symlink policy).
3. Register the new directory and rescan its contents.
4. On `OVERFLOW` in a directory, rescan that directory. If you cannot be sure the registration tree is still complete, re-walk the tree to discover added/removed subdirectories.
5. When a registration becomes invalid, remove it from the map and schedule re-registration if applicable.
6. Cap total watch registrations and I/O cost on large trees.

There is a race between walking and registering subdirectories; a recursive watcher has **no transaction guarantee** of seeing every simultaneous change. For state-oriented workflows, periodic tree rescans provide an effective recovery layer.

## 18. Debouncing and Partially Written Files

An `ENTRY_CREATE` does not guarantee the producer has closed the file. For example:

```text
Producer:
  create report.csv
  write header
  write 10,000 rows
  close file

Consumer:
  sees ENTRY_CREATE right after create
  reads report.csv when producer has only written 10 rows
```

If a file import workflow needs complete contents, agree on a **publish protocol**:

- Producer writes to a temporary file inside a staging directory.
- Producer finishes writing/flushing/closing and validates.
- Producer renames/moves to the official target name when ready; if atomicity is required, claim guarantees only where the provider actually supports them.
- Consumer watches the final filenames and ignores in-progress temp files.

Another tactic is **debouncing** `ENTRY_MODIFY`: wait until metadata stops changing for a set interval before reading. However, debouncing never proves a file is complete in all cases: a producer might pause between batches.

This ties directly to `OVERFLOW`: when a rescan discovers a new file, you still must verify **the file is ready** per business protocol before processing it.

## 19. Idempotency: Duplicate Signals Must Not Corrupt Results

`WatchService` can report the same file multiple times. If every event triggers "send email" or "debit balance", results break.

Designing for idempotency:

- For cache synchronization, updating to the latest observed state is safely repeatable.
- For file imports, record processed file/version/hash/transaction IDs to avoid importing twice.
- For tasks with side effects, use a queue/job state machine (`PENDING/RUNNING/COMPLETED`) and explicit retry rules.
- If a file is replaced under the same name, distinguish versions using reliable metadata or producer-published content versions.
- Do not treat `event.count()` as the number of business operations to run. Count can reflect event coalescing, not logical action count.

When overflow drops event ordering, a state-based/idempotent consumer recovers far more cleanly than one executing side effects per raw notification.

## 20. Deterministic `OVERFLOW` Testing: Simulating Lost Events at the Handler Layer

Real `OVERFLOW` depends on OS/provider limits; creating tens of thousands of files is neither portable nor safe. Instead, test **recovery behavior** by injecting a "stale cache" state or an event-handler abstraction.

In the complete program, we deliberately do:

```java
Map<Path, Stamp> stale = Map.of();       // Cache lost an entry.
Map<Path, Stamp> recovered = scan(dir);  // Actual filesystem state.

boolean restored = recovered.containsKey(Path.of("item.txt"));
```

This is an illustrative snippet, assuming `dir` is declared in context; the standalone example uses `directory`.

This **does not prove the OS emitted `OVERFLOW`**, yet proves rescan logic rediscovers existing files when the cache misses them. You can expand tests to cover:

1. Stale cache holds `deleted.txt` though file is gone on disk → rescan removes it.
2. Stale cache lacks `new.txt` → rescan adds it.
3. Stale cache holds old metadata for `edited.txt` → rescan sees the new fingerprint.
4. Files created and deleted before rescan → history cannot be reconstructed; accept this limitation.
5. Scan fails with `AccessDeniedException` → keep cache in an **uncertain** state and report error; do not overwrite with an empty map.
6. Event handler receives a synthetic `OVERFLOW` via a test abstraction/stub (not claiming it is a real OS event) → confirm rescan and metrics trigger.

What matters is testing that **reconciliation triggers and final state converges**, not "how many events" an OS happened to emit in a few milliseconds.

## 21. Realistic Integration Testing Under Continuous Changes

An integration suite can:

- Create/modify/delete files across multiple `poll` cycles.
- Rename files within the same directory.
- Create files in subdirectories (confirming no automatic recursive watch).
- Create batches of files.
- Modify files while the handler is scanning.
- Restart the watcher after changes happened during downtime.
- Revoke directory read permission **only in a test environment**, verifying no false empty state is recorded.
- Stop the watcher via interrupt/close and verify resource release.
- Run on Linux/Windows/macOS and real target filesystems if the product supports them.

**Do not write assertions** expecting one `Files.writeString` call to always emit exactly one `ENTRY_CREATE` and one `ENTRY_MODIFY` in a fixed order. Integration tests should wait for **eventual state** within a reasonable deadline; diff/recovery unit tests should use synthetic snapshots for deterministic output.

### Example Operation Timeline

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

`t3` and `t5` might not map 1-to-1 to a single `WatchKey` on every provider. Thus tests should assert that the cache eventually reflects `{a.txt}` and later `{}` after deletion, rather than comparing raw event counts.

## 22. Repeated `OVERFLOW`: Performance and Backpressure

Repeated `OVERFLOW` signals usually mean the application cannot keep up with change rates, event processing is too slow, or the provider has tight queue limits.

Remediation steps:

1. **Keep the watch loop lightweight:** collect event hints only and hand heavy work to a bounded queue.
2. **Coalesce work by path:** if the same file triggers 100 modify events, schedule a single final-state check per policy.
3. **Add sensible debouncing** when producers perform bursts of small writes.
4. **Limit worker concurrency** so disk/CPU are not saturated.
5. **Coordinate rescans:** never let 1,000 overflow events kick off 1,000 concurrent full scans of the same directory. Coalesce into a single "dirty" flag and one in-flight rescan.
6. **Measure metrics:** overflow count, queue delay, scan duration, watched dir count, entry count, error rate.
7. **Run periodic reconciliation** to make up for missed events or downtime.
8. **Re-evaluate architecture:** if a directory sees millions of changes per second, `WatchService` + full rescan may be the wrong tool. Choose a message queue, database changelog, or upstream protocol instead.

Do not try to solve overflow by **increasing `ByteBuffer` sizes** in Java; watch-notification queuing lives in the OS/provider and has no universal portable tuning knob across all platforms.

## 23. Error Handling and Uncertain State

A production watcher must distinguish:

| Situation | Recommended Behavior |
|---|---|
| `watcher.poll(...) == null` | No key within timeout; eligible for periodic rescan |
| `OVERFLOW` | Mark dirty, full rescan, reconcile |
| `key.reset() == false` | Registration invalid; remove and consider re-registering |
| `Files.newDirectoryStream` fails | Do not assume directory is empty; keep old cache and report error |
| Entry disappears during `readAttributes` | Skip that entry in this pass, retry/reconcile per policy |
| `AccessDeniedException` | Check process OS permissions, parent directory ACLs, mounts |
| `ClosedWatchServiceException` | Usually shutdown; if unintentional, investigate lifecycle |
| `InterruptedException` | Restore interrupt flag and exit/retry per policy |
| `ENTRY_CREATE` on incomplete file | Wait for publish protocol, bounded retry, or debounce |
| Out of memory from large snapshots | Bound data, use an index/state store, shard watchers |
| File modified during hashing | Data is not an atomic snapshot; requires producer contract |

If a full rescan fails, a solid design puts the watcher into **DEGRADED/NEEDS_RESCAN** state rather than updating the cache with an incomplete snapshot. For stability, log the error and schedule backoff retries; never tight-loop on recurring I/O errors and burn CPU.

## 24. Security When Handling Files from Watched Directories

Risks that `OVERFLOW` recovery does not solve:

- **Path traversal / symlink escape:** `directory.resolve(event.context())` is not a security boundary if an attacker controls the namespace; validate root and restrict process privileges.
- **Symlink races:** a file can be swapped between metadata inspection and opening. `NOFOLLOW_LINKS` in one `readAttributes` call does not secure all subsequent I/O.
- **Untrusted newly created files:** an untrusted producer can drop malformed content, oversized files, zip bombs, or scripts; validate format and quotas.
- **OS permissions:** `WatchService` grants no read permission. A process can receive notifications yet be denied reading contents.
- **Confidential files:** do not print full contents or sensitive paths in logs.
- **Multi-tenant environments:** verify business authorization before processing another tenant's files. The OS only knows process identity, not per-request tenants.
- **Executing code from a watcher:** never auto-execute newly discovered files without trusted-source checks, signatures/approvals, and isolation.
- **Accidental deletion:** reconciliation is not an automatic `delete` command. When an entry vanishes from a scan, apply state-confirmation policies and proper I/O error handling before deleting database/backup records.

Filesystem events are **business-untrusted input signals**. Validate origin, schema, and state before triggering side effects.

## 25. Extension: Designing Around a "Dirty Directory" Model

For directories with continuous churn, a clean organization uses a **dirty flag**:

```text
WatchService consumer:
  on ENTRY_*:
      mark path/dir for inspection
  on OVERFLOW:
      mark directory FULL_RESCAN_REQUIRED
  reset key

Reconciliation worker:
  if FULL_RESCAN_REQUIRED:
      scan directory
      compare snapshots
      apply idempotent changes
      clear flag when scan + commit succeeds
  else:
      check dirty paths
      apply state changes
```

Key concurrency rules:

- Never clear a dirty flag if a new change arrived **during** the rescan/commit. Use a version/generation counter or locked queue so signals are not lost.
- Do not run multiple concurrent full rescans on the same directory without reason.
- Retry failed scans/commits without claiming data is synchronized.
- Keep an independent periodic scan schedule to catch missed events.
- If an entry was created and deleted mid-scan, do not infer full history from the final snapshot.
- Backpressure: when downstream work slows down, never let queues grow unbounded and cause OOM.

This steps up from the single-thread demo. You do not need to build a full concurrency framework to grasp the core of `WatchService` and overflow handling.

## 26. Common Mistakes in Practice Exercises

1. **Ignoring `OVERFLOW`**: cache can drift permanently after dropped events.
2. **Casting `event.context()` to `Path` before checking `OVERFLOW`**: overflow data does not represent a valid file path.
3. **Treating individual events as exact history**: events can be coalesced or lost, with no exactly-once guarantee.
4. **Forgetting `key.reset()`**: misses subsequent signals.
5. **Not checking `reset() == false`**: invalid registrations linger in tracking structures.
6. **Using `take()` on the main thread with no shutdown path**: blocks forever when events stop.
7. **Using `poll()` in a tight busy loop**: spikes CPU when no keys are ready.
8. **Registering after scanning and assuming no race**: changes right before registration can be missed.
9. **Reading `ENTRY_CREATE` as "file finished writing"**: producer may still be writing contents.
10. **Running heavy tasks directly inside the watch event loop**: backlog builds up and triggers overflow.
11. **Using metadata snapshots to claim all content edits are caught**: hashes/versions may be required.
12. **Returning `Map.of()` on scan failure and wiping the cache**: confuses "unreadable" with "empty directory".
13. **Assuming watching root is recursive**: subdirectories must be registered separately.
14. **Trying to fix `OVERFLOW` by enlarging read buffers**: does not change provider event-queue limits.
15. **Creating millions of files to "unit test overflow"**: non-portable and stresses the host; test recovery via injection/synthetic state.
16. **Trusting test output on a single OS**: event counts and order vary by provider.
17. **Ignoring symlinks/TOCTOU**: risks reading files outside scope.
18. **Lacking idempotency**: one file modification can trigger duplicate processing.
19. **Not recovering on restart**: downtime notifications are not durably queued by `WatchService`.
20. **Closing the watcher without handling `ClosedWatchServiceException`**: raises spurious shutdown errors.
21. **Keeping invalid keys in maps**: leaks references and breaks tracking.
22. **Using `WatchService` as a financial/legal audit log**: lacks guarantees for every intermediate operation.
23. **Unbounded queues/concurrency**: exhausts memory/CPU under rapid directory churn.
24. **Treating scan output as an atomic snapshot**: filesystem can change during enumeration; needs a writer protocol.
25. **Reconciling cache without resetting the key**: loses future notifications.

## 27. Extension Exercises

### Exercise 1 — Diff Added/Removed/Changed

Write `diff(oldSnapshot, newSnapshot)` returning three sets: `added`, `removed`, and `changed`. Use the `Stamp` record from the example. Test with synthetic data so stdout does not depend on `WatchService`.

### Exercise 2 — Force Reconciliation on Missed Events

Create `A.txt` without inserting any event into the cache; call `scan` and update the cache. Then delete the file and rescan to remove the missing entry. Explain why this tests recovery yet **does not claim the OS emitted `OVERFLOW`**.

### Exercise 3 — 30-Second Watch Loop

Using `poll(500, TimeUnit.MILLISECONDS)`, allow manual file creation/editing/deletion over 30 seconds. Do not print every event uncontrollably; aggregate key counts, overflow counts, and rescan counts.

### Exercise 4 — Debounce

Add a `Path → lastHintTime` map, coalescing multiple modify hints within 300–500 ms and processing only after quiet time elapses; afterward, still confirm file completeness via a producer contract.

### Exercise 5 — Recursive Watching

Walk the tree and register each directory. When `ENTRY_CREATE` is a directory, register and scan its contents. When a key becomes invalid, remove it from the map. Add periodic full-tree rescans to recover from race windows.

### Exercise 6 — Restart Recovery

Run the watcher, create files, stop the process, modify/delete/add files while stopped, and restart. Show that the initial scan reconstructs **final state**, yet cannot reveal every operation that happened during downtime.

### Exercise 7 — Resource Bounds

Simulate 10,000 event hints for the same filename using a unit-test abstraction (without creating 10,000 real files). Verify scheduling coalesces into one final-state check and queues do not grow unbounded.

## 28. Self-Check Questions

**1.** Does `OVERFLOW` provide the names of files whose events were dropped?  
**No.** It only signals possible notification loss; current state must be rescanned.

**2.** After a full rescan, can you tell which files were created and deleted between two scans?  
**Not reliably.** Final state may leave no trace of intermediate operations.

**3.** Why must an event handler call `key.reset()`?  
**So the key can continue receiving signals** if the registration remains valid.

**4.** What does `key.reset() == false` mean?  
**Invalid registration**; remove it from watcher state and consider re-registering.

**5.** Does `poll(timeout)` returning `null` prove no file changed?  
**No.** It only means no key was dequeued within the wait window, subject to provider limits.

**6.** Why should snapshots read directly from the filesystem rather than trusting the event list?  
**Because events can be coalesced, delayed, or dropped**, whereas a snapshot reflects state observed at scan time.

**7.** Can you handle `ENTRY_CREATE` by parsing the file immediately?  
**Not by default.** The producer may still be writing; use an appropriate publish protocol, validation, or debounce.

**8.** Does `Files.newDirectoryStream(root)` scan recursively?  
**No.** It lists direct entries inside `root` only.

**9.** Does a size + mtime fingerprint catch every content edit?  
**No.** Digests/versions/snapshot protocols may be needed for stricter requirements.

**10.** Why avoid stress-creating millions of files just to unit test overflow?  
**Because results are provider-dependent and overload the environment**; test recovery independently of the event source.

**11.** If a full rescan throws `AccessDeniedException`, should the cache be set to an empty map?  
**No.** "Unreadable" does not mean "zero entries"; preserve uncertain state and retry.

**12.** Can `WatchService` serve as an exactly-once audit log?  
**No.** It does not guarantee persisting and replaying every modification.

## 29. Pre-Deployment Checklist

- [ ] Identify root directories and file types to watch.
- [ ] Verify process permissions and filesystem/provider support.
- [ ] Register root before initial scan where appropriate.
- [ ] Define snapshot cache and required accuracy of metadata/hash/version.
- [ ] Receive `WatchKey` via `take` or timed `poll`, with a shutdown policy.
- [ ] Drain `pollEvents()` and **check `OVERFLOW` before casting context**.
- [ ] On `OVERFLOW`, run full rescan and reconcile against actual state.
- [ ] Include periodic reconciliation/initial scan where missed-event recovery is needed.
- [ ] Ensure `key.reset()` is called and handle invalid keys.
- [ ] Maintain a registration map when watching multiple directories.
- [ ] Do not assume recursive watching; register subdirectories explicitly.
- [ ] Use idempotent processing, bounded queues, and appropriate debouncing.
- [ ] Handle incomplete files, renames, symlinks, and TOCTOU.
- [ ] Never turn scan failures into a false empty state.
- [ ] Track metrics for overflows, latency, rescan errors, and queue depth.
- [ ] Test deterministically with synthetic state and on real OSes for integration.
- [ ] Do not assert fixed `ENTRY_MODIFY` counts or ordering.
- [ ] Test restarts to confirm cache rebuilds from snapshots.
- [ ] Close `WatchService`, handle interrupts, and cancel keys when no longer needed.
- [ ] If every operation must be captured exactly, choose a separate journal or transaction log.

## 30. Summary

- **`WatchService` is a directory change notification system**, not a complete log or consistent filesystem snapshot.
- **`OVERFLOW` signals that some events may have been lost**. The dropped event list cannot be recovered directly; you must **rescan current state**.
- A more reliable basic design for this exercise is **register → scan → poll/take → drain events → rescan/reconcile → reset → repeat**.
- **`WatchEvent.context()` for `ENTRY_*` is usually a relative `Path`**; pair it with the exact registered directory. For `OVERFLOW`, never cast context to `Path`.
- **Metadata snapshots only detect changes in the fields they store**; size/mtime are insufficient for all data integrity needs.
- **Unit-test recovery with a synthetic stale cache** instead of relying on real overflows; integration tests should assert eventual state rather than fixed event counts.
- For a production-grade watcher: add shutdown, re-registration, periodic rescans, race handling, idempotency, resource limits, and observability.

### Java 17 Official References

- [WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
- [WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html)
- [WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html)
- [StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)
- [Path.register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...))
- [Files.newDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newDirectoryStream(java.nio.file.Path))
- [BasicFileAttributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/BasicFileAttributes.html)
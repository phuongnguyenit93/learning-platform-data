# `WatchKey`, `pollEvents()`, and Relative Event Paths in Java NIO.2

## 1. Lesson Objectives

`java.nio.file.WatchService` (Java NIO.2) lets a program receive notifications about changes **inside a registered directory**: a new entry is created, an entry is deleted, or an entry is modified. However, the result from a watcher is not a ready-to-use absolute path string; on each notification, you receive a **`WatchKey`**, retrieve the event list via `pollEvents()`, and then combine **`WatchEvent.context()`** with the directory attached to the key.

Here are the three links that must be used correctly:

- **`WatchKey`**: represents the registration of a `Watchable` object (typically a directory `Path`) with a `WatchService`. The key manages the registration's event queue and the state requiring `reset()`.
- **`key.pollEvents()`**: returns the list of pending events for **that key** and removes the retrieved events from the key's queue.
- **`event.context()`**: for directory events via the default provider, usually a `Path` **relative to the registered directory**, such as `report.txt`, not the file's absolute path.

After this lesson, you will be able to create a watcher, understand the key lifecycle, resolve `watchable.resolve(context)` properly, avoid confusing `WatchService.poll()` with `WatchKey.pollEvents()`, handle `ENTRY_CREATE`/`ENTRY_DELETE`/`ENTRY_MODIFY`/`OVERFLOW`, manage multiple directories, and recognize the reliability limits of file system notifications.

Examples target Java 17+ and require no external libraries. Environment-dependent output is explicitly noted: `WatchService` depends on the provider, file system, OS, and event detection timing.

## 2. Key Objects and Methods

| Object / API | Role |
| --- | --- |
| `WatchService` | Central service receiving **signalled watch keys**, created by `FileSystems.getDefault().newWatchService()` |
| `Path.register(service, kinds...)` | Registers a `Path` (usually a directory) and change kinds with the service, returning a `WatchKey` |
| `WatchKey` | Specific registration: provides `watchable()`, `pollEvents()`, `reset()`, `isValid()`, `cancel()` |
| `WatchService.take()` | **Blocks** until a key is signalled or the service closes |
| `WatchService.poll()` | Attempts to retrieve a waiting key, returning `null` if none is available |
| `WatchService.poll(timeout, unit)` | Waits up to a timeout to retrieve a key; may return `null` |
| `WatchKey.pollEvents()` | Drains the list of pending events of **one key** |
| `WatchEvent.kind()` | Event kind, such as `ENTRY_CREATE` or `OVERFLOW` |
| `WatchEvent.context()` | Context attached to the event: for entry events, usually a relative `Path` |
| `WatchEvent.count()` | Number of events of the same kind/context coalesced per contract |
| `WatchKey.reset()` | Acknowledges processing and returns the key to a state where it can continue receiving signals; returns `false` if the key is no longer valid |
| `WatchKey.cancel()` | Cancels the registration; does not delete files or close the service |

One `WatchService` can serve multiple directories. Each registered directory has its own `WatchKey`; upon receiving a key, you must first identify **which directory the key belongs to** before resolving the event context.

### Two "poll" Methods Doing Two Different Jobs

```text
watcher.poll()  or watcher.take()
   |
   v
WatchKey key                 <-- retrieves a signalled key
   |
   +--> key.watchable()      <-- the registered directory
   |
   +--> key.pollEvents()     <-- retrieves List<WatchEvent<?>>
          |                       of this key
          v
      kind / context / count
   |
   +--> key.reset()          <-- allows watching to continue
```

`watcher.poll()` **does not** return an event list; it returns a `WatchKey` or `null`. Conversely, `key.pollEvents()` is not used to wait for the service to receive new events; it only retrieves events already accumulated on that key.

## 3. Registering a Directory

Basic sample snippet:

```java
Path watchedDir = Path.of("inbox").toAbsolutePath().normalize();

try (WatchService watcher =
        FileSystems.getDefault().newWatchService()) {

    WatchKey registration = watchedDir.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_DELETE,
            StandardWatchEventKinds.ENTRY_MODIFY);

    // Then call watcher.take() or watcher.poll(timeout, unit).
}
```

This is a **snippet**, not a standalone program. It assumes `inbox` already exists and is a directory supported for watching by the provider; it requires importing `java.nio.file.*` and handling `IOException`.

Meaning of each kind:

- `ENTRY_CREATE`: detects an entry created in the directory.
- `ENTRY_DELETE`: detects an entry deleted from the directory.
- `ENTRY_MODIFY`: detects an entry modified, according to provider capabilities and policy.
- `OVERFLOW`: one or more events may have been dropped or lost; **do not register `OVERFLOW` as an ordinary watch event kind**; the watcher can report it regardless of the specific kinds registered.

The registered target **is a directory** (per standard usage of the default file system provider) rather than an individual file name. Registering `inbox` means watching entries **directly** under `inbox`, not automatically watching the entire subdirectory tree.

If an application needs to monitor `inbox/a/b/file.txt` but only registers `inbox`, do not assume `ENTRY_MODIFY` will arrive for a file nested multiple levels deep. Register the needed subdirectories and handle new directories created at runtime.

## 4. What Does `WatchKey` Represent?

A `WatchKey` is a registration with a watcher. Once registered, it provides:

```java
Watchable observed = key.watchable();
boolean valid = key.isValid();
List<WatchEvent<?>> events = key.pollEvents();
boolean stillValid = key.reset();
```

**Illustrative snippet**: the variable `key` is assumed to exist, requiring imports for `Watchable`, `WatchKey`, `WatchEvent`, and `List`. For a directory watcher registered via `Path.register`, `key.watchable()` is the `Path` of the registered directory. Do not automatically assume every `Watchable` implementation is a `Path`; the scope here is a directory file system watcher.

Key points:

1. `key.watchable()` returns **the originally registered object**, not the file that just changed.
2. `key.isValid()` can become false when the registration is cancelled, the watcher is closed, or the target can no longer be watched (e.g., the directory is deleted).
3. `key.cancel()` stops watching; it does not delete or move files.
4. `key.reset()` must be called after processing events; a `false` result signals you should no longer wait on that registration.
5. When multiple changes occur rapidly before a thread retrieves the key, one key may hold **multiple events**, and events of the same kind may be coalesced with `count()`.
6. When `WatchService` is closed, waiting calls and related operations may throw `ClosedWatchServiceException`; manage the service lifecycle properly.

### Ready and Signalled States

State model of a key:

```text
Registered
    |
    v
 READY -- event occurs --> SIGNALLED and placed into WatchService queue
    |                       |
    |                       v
    |             watcher.take() / poll()
    |                       |
    |                       v
    |               key.pollEvents()
    |                       |
    |                       v
    +<--------- key.reset() if valid
                            |
                            +-- if more events are pending,
                                the key may be immediately placed
                                into the WatchService queue again
```

`pollEvents()` only retrieves events; **it does not automatically return the key to READY**. Therefore, if you forget `reset()`, the program may process one batch and then fail to be notified of new batches as expected.

Do not replace `reset()` with `cancel()` after each round of processing: `cancel()` terminates the registration, whereas `reset()` acknowledges the key and continues monitoring.

## 5. `pollEvents()`: Retrieving the Event List Properly

`WatchKey.pollEvents()` returns `List<WatchEvent<?>>`:

```java
WatchKey key = watcher.take();
for (WatchEvent<?> event : key.pollEvents()) {
    WatchEvent.Kind<?> kind = event.kind();
    Object context = event.context();
    int count = event.count();
    // Handle kind, context, and accumulated event count.
}
boolean valid = key.reset();
```

This is an illustrative snippet requiring an already created/registered `watcher` and imports. Points to remember:

- `pollEvents()` only retrieves pending events **for a single key**; the list may be empty in some situations, which does not mean the watcher is broken.
- It **removes the retrieved events from the key's queue**. Calling `pollEvents()` again immediately will normally not return the same old event objects.
- `pollEvents()` may contain multiple different kinds; do not infer "one `take` corresponds to exactly one file".
- `event.count()` may be greater than 1 because multiple identical events were coalesced. Do not design logic assuming "each event object == exactly one file modification".
- `OVERFLOW` can appear even if you only registered `ENTRY_CREATE`.
- After processing, call `reset()`, even if you ignored certain kinds; if false, remove the registration from internal state.

Do not treat the result of `pollEvents()` as an absolute list reflecting every change on the file system. It is a notification for the application to **re-inspect state** when needed.

### `WatchService.take()` / `poll()` / `poll(timeout)`

| Key Retrieval Method | When Appropriate |
| --- | --- |
| `take()` | Dedicated watch loop that can block until a key arrives |
| `poll()` | Event loop already doing other work, checking non-blockingly |
| `poll(5, TimeUnit.SECONDS)` | Waiting with a bounded timeout, handling timeout/cancellation |
| `close()` | Closes `WatchService`, releases resources, wakes waiting threads via the corresponding exception |

`take()` can throw `InterruptedException` when the thread is interrupted. `poll(timeout, unit)` can also be interrupted and returns `null` when the timeout expires without a key. Do not turn a timeout into "the file no longer exists": only conclude that **no key was retrieved during that wait period**.

## 6. `WatchEvent.context()` Is a Relative Path

This is the core focus of this lesson.

Suppose you register the directory:

```text
/opt/app/inbox
```

A file is created:

```text
/opt/app/inbox/report.csv
```

For the `ENTRY_CREATE` event, the context is typically:

```text
report.csv
```

Rather than `/opt/app/inbox/report.csv`. How to build the path to the affected entry:

```java
Path registeredDirectory = (Path) key.watchable();
Path relative = (Path) event.context();
Path changed = registeredDirectory.resolve(relative);
```

These three lines are a **snippet**, used only when `event.kind()` is an entry event with a `Path` context and the key actually came from `Path.register()`. You can add `toAbsolutePath().normalize()` when you need a uniform path form for logging or comparison.

Important:

- **Relative to the watched directory**, not relative to the Java process's current working directory.
- If the watcher registers multiple directories, you must take the directory from **the exact key** being processed; picking the wrong directory produces a wrong resolved path.
- `WatchEvent.context()` is declared with generic type `T`, but `pollEvents()` returns `List<WatchEvent<?>>`. Do not cast `OVERFLOW` context to `Path`: the context of `OVERFLOW` can be `null`.
- `ENTRY_DELETE` reports that a previously existing entry was deleted; afterward `Files.exists(changed)` may be false, so you cannot assume its contents can be opened.
- `ENTRY_CREATE`/`ENTRY_MODIFY` do not guarantee the file still exists or remains in the same state as when the event occurred by the time your code handles it.
- `normalize()` only normalizes `.`/`..` syntax; it does not prove a path is permitted to access or prevent escapes via symbolic links. For untrusted paths, add appropriate security checks.

### Keep `Path` Absolute at Registration Time

Example:

```java
Path watchedDir = Path.of("inbox").toAbsolutePath().normalize();
WatchKey key = watchedDir.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE);
```

If you register using a relative directory `Path.of("inbox")`, `key.watchable()` may be a relative `Path` matching the registered value. When used further in a complex system or stored in logs, the absolute normalized form usually prevents confusion with paths in other subsystems. It still does not eliminate race conditions/symlinks.

### Model Combining Multiple Directories

```text
WatchService
   |
   +--> WatchKey A --> watchable() = /data/a
   |                          context() = first.txt
   |                          resolved = /data/a/first.txt
   |
   +--> WatchKey B --> watchable() = /data/b
                              context() = second.txt
                              resolved = /data/b/second.txt
```

Both events could even share the same name `output.log`. Using only `context().toString()` as a unique identifier key across the whole watcher is wrong when watching multiple directories. The key may need to include the directory/watch registration plus the relative context.

## 7. Runnable Java 17+ Example: Observing Events and Resolving `Path`

The first example creates a temporary directory, registers a watch, creates `note.txt`, waits for `ENTRY_CREATE`, and prints the event kind, relative name, and whether resolving against the root directory matches. The code only prints the event with **the matching name** so it does not depend on extra `ENTRY_MODIFY` events emitted by the OS.

Save as **`WatchKeyRelativePathDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

public class WatchKeyRelativePathDemo {
    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("watch-relative-")
                        .toAbsolutePath().normalize();
        Path file = dir.resolve("note.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                dir.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY);

                Files.writeString(file, "hello");
                boolean found = false;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (!found) {
                    long left = deadline - System.nanoTime();
                    if (left <= 0) {
                        throw new IOException("ENTRY_CREATE not reported");
                    }

                    WatchKey key = watcher.poll(
                            left, TimeUnit.NANOSECONDS);
                    if (key == null) {
                        throw new IOException("Timed out waiting for event");
                    }

                    Path watchedDir = (Path) key.watchable();

                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            // A real application needs to rescan the directory.
                            continue;
                        }

                        if (event.kind()
                                != StandardWatchEventKinds.ENTRY_CREATE) {
                            continue;
                        }

                        // For entry events of a Path watcher, context is a Path.
                        Path relative = (Path) event.context();
                        if (relative.equals(Path.of("note.txt"))) {
                            Path changed = watchedDir.resolve(relative)
                                    .toAbsolutePath().normalize();
                            System.out.println("kind="
                                    + event.kind().name());
                            System.out.println("relative=" + relative);
                            System.out.println("resolvedMatches="
                                    + changed.equals(file));
                            found = true;
                        }
                    }

                    boolean valid = key.reset();
                    if (!valid) {
                        throw new IOException("Directory registration invalid");
                    }
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(dir);
        }
    }
}
```

Run:

```bash
javac WatchKeyRelativePathDemo.java
java WatchKeyRelativePathDemo
```

**Typical stdout when the file system/provider reports `ENTRY_CREATE` within the timeout:**

```text
kind=ENTRY_CREATE
relative=note.txt
resolvedMatches=true
```

This output is **conditional**, not a promise that every platform emits events identically. If the provider does not deliver `ENTRY_CREATE` within five seconds, the program throws an `IOException` stating the reason. Extra `ENTRY_MODIFY` events are not printed so they do not perturb the sample output.

Why is `resolvedMatches=true`? When registered, `dir` was already absolute and normalized. `event.context()` for the new file is `Path.of("note.txt")` relative to `dir`. `watchedDir.resolve(relative)` reconstructs the exact `file` path used to create the entry.

The example also demonstrates calling `key.reset()` **after retrieving and processing the event list**. Do not call `reset()` prematurely while the program has not yet finished handling the payload, as doing so can complicate event coordination in real applications.

## 8. Runnable Java 17+ Example: One Service, Multiple Directories

When watching multiple folders, `key.watchable()` or a `Map<WatchKey, Path>` is the way to obtain the right root. Using a separate watcher per directory wastes resources and makes management harder; one service can suffice for a group of directories on the same file system/provider.

The example has two directories, `a` and `b`. The program intentionally sorts results before printing so output does not depend on the order in which the watcher delivers keys.

Save as **`MultiDirectoryWatchDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.TimeUnit;

public class MultiDirectoryWatchDemo {
    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("multi-watch-");
        Path dirA = Files.createDirectory(root.resolve("a"));
        Path dirB = Files.createDirectory(root.resolve("b"));
        Path fileA = dirA.resolve("first.txt");
        Path fileB = dirB.resolve("second.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                Map<WatchKey, Path> roots = new HashMap<>();
                roots.put(dirA.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE), dirA);
                roots.put(dirB.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE), dirB);

                Files.createFile(fileA);
                Files.createFile(fileB);

                Set<String> found = new TreeSet<>();
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(5);

                while (found.size() < 2) {
                    long left = deadline - System.nanoTime();
                    if (left <= 0) {
                        throw new IOException("Missing create notifications");
                    }

                    WatchKey key = watcher.poll(
                            left, TimeUnit.NANOSECONDS);
                    if (key == null) {
                        throw new IOException("Watcher timeout");
                    }

                    Path watched = roots.get(key);
                    if (watched == null) {
                        throw new IOException("Unknown watch key");
                    }

                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            throw new IOException(
                                    "Overflow; directory rescan required");
                        }

                        if (event.kind()
                                != StandardWatchEventKinds.ENTRY_CREATE) {
                            continue;
                        }

                        Path relative = (Path) event.context();
                        Path changed = watched.resolve(relative);

                        if (changed.equals(fileA)) {
                            found.add("a/" + relative);
                        } else if (changed.equals(fileB)) {
                            found.add("b/" + relative);
                        }
                    }

                    if (!key.reset()) {
                        roots.remove(key);
                        throw new IOException("Watched directory invalid");
                    }
                }

                for (String item : found) {
                    System.out.println(item);
                }
                System.out.println("createdEntries=" + found.size());
            }
        } finally {
            Files.deleteIfExists(fileA);
            Files.deleteIfExists(fileB);
            Files.deleteIfExists(dirA);
            Files.deleteIfExists(dirB);
            Files.deleteIfExists(root);
        }
    }
}
```

```bash
javac MultiDirectoryWatchDemo.java
java MultiDirectoryWatchDemo
```

**Stdout when both notifications are received successfully:**

```text
a/first.txt
b/second.txt
createdEntries=2
```

Takeaways:

- `Map<WatchKey, Path>` associates a registration with its own directory. `key.watchable()` can also be cast to `Path` because the keys in this example were created via `Path.register()`.
- The two keys can be returned by the watcher in any order. `TreeSet` sorts them to illustrate deterministic output once both entries have been detected.
- `Files.createFile` creates an empty file; the `ENTRY_CREATE` event here only needs to identify entry creation, without reading file contents.
- When a key becomes invalid, the code removes it from `roots` and throws an error. Long-running applications must decide whether to re-register or stop watching the corresponding directory.
- This is not a production monitoring system capable of recovering automatically from `OVERFLOW`. In that case, you **must rescan state** and reconcile against the application's snapshot.

**Note:** OS/provider notification order, readiness timing, and `WatchService` support depend on the environment. If not enough events are received, the program throws an error instead of printing a fake success result. Sorted printing does not make a provider that drops events more reliable.

## 9. `OVERFLOW` and `count()`: Why Not Treat Events as a Complete Log?

File system changes can happen in bursts, for instance when a process copies thousands of files into a directory or another program modifies the same file repeatedly. The watch service may:

1. Coalesce multiple events with the same kind and context into a single `WatchEvent` with `count()` greater than 1.
2. Not distinguish every individual change if the system/provider lacks that detail.
3. Report `OVERFLOW` when events have been lost or discarded due to excessive event volume.

Example event check:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        System.err.println("Changes were lost; rescan required");
        continue;
    }

    System.out.println(event.kind().name()
            + " " + event.context()
            + " count=" + event.count());
}
```

This is an illustrative snippet only. `count()` is the number of times a specific event was accumulated/coalesced, **not** the number of distinct files affected. If you receive `ENTRY_MODIFY` with `count=5`, do not conclude that the user saved the file five times in a business sense.

### Proper Strategy After `OVERFLOW`

- Rescan the watched directory/subdirectories.
- Reconcile the current snapshot (names, sizes, timestamps, checksums if truly necessary) with known state.
- Resynchronize caches/work indexes or mark them for re-verification.
- Continue processing new events and calling `reset()` according to key state.
- If an absolute, ordered audit of every rename/content change is required, `WatchService` **is not enough**; you need a dedicated event protocol or log managed by the change source.

`OVERFLOW` should not have `event.context()` cast to `Path`. For this event kind, context may be `null`, and there is no guaranteed "specific file" recoverable from the event itself.

## 10. `reset()`, Key Cancellation, and Closing the Service

Commonly confused operations:

| Operation | Meaning |
| --- | --- |
| `key.pollEvents()` | Retrieves the pending event list of the key; does not automatically re-arm the key |
| `key.reset()` | Acknowledges processing and gives the key the opportunity to be signalled next round; returns false if invalid |
| `key.cancel()` | Cancels the registration; does not delete the directory or close the watcher |
| `watcher.close()` | Closes the entire `WatchService`; can no longer be used to retrieve keys |
| `key.isValid()` | Checks whether the key is currently valid; does not verify event data completeness |

Standard processing pattern:

```java
while (running) {
    WatchKey key = watcher.take();
    try {
        for (WatchEvent<?> event : key.pollEvents()) {
            // Process events, including OVERFLOW.
        }
    } finally {
        boolean valid = key.reset();
        if (!valid) {
            // Remove key from registration map, handle lost directory...
        }
    }
}
```

**Non-standalone snippet**; `running`, `watcher`, and exception handling are supplied by the application. This pattern emphasizes resetting after consuming events, even if processing encounters recoverable issues. In real programs, severe exceptions may lead to closing the watcher instead of continuing.

When `reset()` returns `false`:

- The key can no longer be used to wait for new changes.
- The directory may have been deleted, the resource may have become inaccessible, or the registration may have been cancelled.
- Remove it from `Map<WatchKey, Path>`, and close related resources if no longer needed.
- If the directory reappears, there must be an appropriate mechanism to **re-register**; the old key does not revive on its own.

Do not treat `reset() == false` as sufficient to deduce the **sole reason** was directory deletion. The exact reason can depend on provider/lifecycle.

## 11. Relative Paths, Working Directory, and Avoiding Wrong Resolution

### 11.1. Not Relative to the Current Working Directory

Example:

```text
Current working directory:  /home/app
Watched directory:          /home/data/input
WatchEvent.context():       report.csv
```

Semantically wrong:

```java
Path wrong = Path.of(event.context().toString());
// Here wrong is interpreted relative to the working directory,
// not the directory registered with the watcher.
```

Right:

```java
Path watchedDir = (Path) key.watchable();
Path changed = watchedDir.resolve((Path) event.context());
```

The two snippets above are illustrative, requiring an entry event with a `Path` context. Even if the program runs in a different directory, the right approach still obtains the root from the key rather than relying on `user.dir`.

### 11.2. Optionally Storing a Separate Mapping

If the application needs extra metadata per registration (project ID, processing type, snapshot), use a structure like:

```java
Map<WatchKey, Path> dirByKey = new HashMap<>();
WatchKey key = watchedDir.register(watcher,
        StandardWatchEventKinds.ENTRY_CREATE);
dirByKey.put(key, watchedDir);
```

In other handler methods, look up `watchedDir = dirByKey.get(key)`. Remove the mapping when the key becomes invalid or the service closes. Do not assume an old key remains valid after a directory is deleted and recreated.

### 11.3. The Resolved Path Does Not Guarantee the File Still Exists

A watcher reports `ENTRY_CREATE`, yet by the time the handler runs, the file may already have been deleted or renamed. For `ENTRY_DELETE`, the file almost always can no longer be opened. Thus a good workflow is:

1. Construct the path using the right root and context.
2. If intending to read, check the event kind and access the file with realistic exception handling.
3. Accept that `Files.exists` followed by `Files.readAllBytes` still has a race between the two calls.
4. If business logic requires guaranteeing the file has "finished writing", establish an explicit publish protocol (e.g., create temp file, finish writing, rename) instead of relying on a single `ENTRY_MODIFY`.
5. For untrusted inputs, validate paths, symlinks, and access permissions; do not rely on `normalize()` as the sole security measure.

## 12. Not Recursive by Default

A watch service typically emits events for **direct entries** of the registered directory, not every file under subdirectories.

```text
root/                      <- registered WatchKey R
  a.txt                    <- event on R
  nested/                  <- creating nested -> event on R
    b.txt                  <- modifying b.txt is NOT guaranteed by R
                              to automatically emit an event
```

To watch an entire directory tree:

- First traverse existing directories and register each one.
- When receiving `ENTRY_CREATE` for a new directory, register that directory and traverse any existing subdirectories inside it.
- When receiving an invalid key, remove the corresponding mapping.
- Handle races during scanning/registration: files may appear, disappear, or change between steps.
- Handle `OVERFLOW` by rescanning; do not assume every new directory was registered completely if events were lost.

Recursive directory watching requires significant extra logic; there is no standard `recursive=true` flag on `Path.register(...)` across all Java 17 providers. Some providers have proprietary modifiers, but do not treat platform-specific features as portable guarantees.

## 13. Event Names and Provider Behavior

### `ENTRY_CREATE`

An entry appears in the directory. This does not necessarily mean "the final file is completely written and ready to parse". A tool may create a file and continue writing over multiple steps. To process complete content, you need a protocol with the file producer, such as writing a temporary file and renaming upon completion.

### `ENTRY_MODIFY`

An entry is modified. Event counts can vary by OS/provider, including multiple events for one business operation or coalesced events. Do not treat `count()` as the number of times a document was saved.

### `ENTRY_DELETE`

An entry is deleted. The `Path` context describes **the entry name that disappeared**; usually there is no longer an object to open. Rename/move operations may be reported as a delete in one directory and a create in another, but there is no portable requirement that events be linked into a single rename transaction.

### `OVERFLOW`

Changes may have been lost. Rescan; there is no required entry `Path` in the context.

### File System / Provider Dependencies

`WatchService` may be implemented via native OS notifications or polling. Latency, feature support, continuity during network disconnects, remote mount watching, and symlink handling differ across providers.

Do not design portable tests that require:

- Every write emits exactly one `ENTRY_MODIFY`.
- Every rename operation produces events in a strictly guaranteed order.
- A fixed millisecond latency for event emission.
- Every network file system behaves like a local disk.
- `pollEvents()` serves as a complete audit trail of all changes.

A notification itself only says "re-inspect the relevant state", and does not replace data-reading/validation APIs.

## 14. Managing Events in Real Systems

In a file-ingestion application, you often have to handle a large volume of rapid changes. A useful structure:

1. One watcher thread uses `take()` or `poll(timeout)` to retrieve keys.
2. Iterate `pollEvents()`, identify the root via the key, extract the relative context, and build the full `Path`.
3. Offload expensive file reading/decoding/parsing to a bounded executor, avoiding letting the watcher loop miss too many events.
4. Call `reset()` and check the result; remove invalid registrations.
5. On `OVERFLOW`, schedule a bounded rescan and resynchronize state.
6. Design for idempotency (handling duplicate events still yields a valid result), snapshots/checksums if needed, and queue backpressure.
7. Ensure `WatchService` and worker pools are closed during shutdown.

If a callback handling `ENTRY_MODIFY` runs too slowly before resetting the key, subsequent changes may accumulate/coalesce; the watcher's queue can overflow. Keeping the watcher loop lightweight and offloading heavy work is usually a sound decision.

**Special note on races:** placing a `Path` onto a queue for a worker to open later **does not** guarantee the worker will see the exact file contents from the moment of the event. If a consistent version is needed, producer and consumer must have a coordination protocol (renaming completed files, manifests, appropriate locks, or content-addressed artifacts).

## 15. Common Pitfalls and How to Fix Them

1. **Confusing `watcher.poll()` with `key.pollEvents()`.** One retrieves a key; the other retrieves events of a key.
2. **Forgetting `key.reset()`.** After one round of signalling, the key may not be signalled again as expected.
3. **Calling `key.cancel()` instead of `reset()`.** Cancel terminates watching, rather than acknowledging processing.
4. **Assuming `event.context()` is always an absolute `Path`.** For directory entry events, it is relative to the watched directory; resolve it against the right root.
5. **Resolving against the working directory instead of `key.watchable()`.** Can open the wrong file in another location.
6. **Casting context to `Path` before checking `OVERFLOW`.** Overflow context can be null; branch on kind first.
7. **Ignoring `WatchEvent.count()`.** You do not need to reprocess repeatedly at all costs, but you must understand events can be coalesced; count is not file count.
8. **Ignoring `OVERFLOW`.** Risks missing files; you must rescan when correctness is required.
9. **Seeing `ENTRY_MODIFY` and assuming the file is done writing.** The file may still be mid-write; use a completion protocol.
10. **Assuming the watcher is recursive.** Register subdirectories explicitly if deep watching is needed.
11. **Using a single watched root for every key.** With multiple directories, identical relative filenames can lead to picking the wrong file.
12. **Trying to open a file after `ENTRY_DELETE`.** The entry may no longer exist; update indexes using the known path/context.
13. **Not checking `reset() == false`.** An invalid key must be removed from the map and a re-registration decision made.
14. **Blocking the watcher loop with long processing.** Events back up/coalesce/overflow; offload to a bounded worker executor.
15. **Using a watcher as an absolute audit system.** OS/providers can coalesce/drop events; auditing requires a separate reliable change log.
16. **Not closing `WatchService`.** Resources and waiting threads can linger longer than expected; establish a shutdown strategy.
17. **Inferring event timing via absolute ordering.** Notifications can arrive after the change, while state has continued mutating.
18. **Using `normalize()` instead of path security checks.** Syntactic normalization does not handle symlinks/races and permissions.

## 16. Practice Exercises

### Exercise A — Observe the Difference Between the Two Poll Methods

Create a watcher for a temporary directory. Call `watcher.poll()` before creating any file and observe that it can return `null`. After creating a file and receiving a `WatchKey`, call `key.pollEvents()` and then try calling it again immediately. Why is the second list usually empty? After processing, which method must be called to continue watching?

### Exercise B — Verify Relative Context

Suppose `key.watchable()` returns `/tmp/receive` and the event context is `data.csv`. What is the right path to read the file? Why is `Path.of("data.csv")` not equivalent if the program runs in `/home/app`?

### Exercise C — Multiple Registrations

Register `dirA` and `dirB` on the same `WatchService`. Create a file with the same name `data.json` in both directories. Build a `Map<WatchKey, Path>` and print the resolved paths without confusing the two files.

### Exercise D — `OVERFLOW` Scenario

Suppose the watcher misses several `ENTRY_CREATE` events because the queue overflowed. Explain why `event.count()` is insufficient to reconstruct the list of created files, and write the steps to rescan/reconcile the snapshot.

### Exercise E — Lack of Recursive Behavior

You register `inbox`, and then another program creates `inbox/newFolder/item.bin`. Why is the watcher on `inbox` insufficient to guarantee receiving the creation event for `item.bin`? What additional root would you register, and how would you handle races?

### Exercise F — Lifecycle and Shutdown

A watcher thread is blocked inside `take()`. The coordinator thread wants to shut down the application. How should `WatchService.close()`, `ClosedWatchServiceException`, and closing the executor be managed so no resources are leaked?

## 17. Self-Check Questions

1. What type does `Path.register(watcher, kinds...)` return, and what does `WatchKey.watchable()` usually represent?
2. How do `WatchService.poll()` and `WatchKey.pollEvents()` differ in return object and responsibility?
3. Is `WatchEvent.context()` for `ENTRY_CREATE` on a directory usually an absolute or relative `Path`? Relative to what?
4. If a program watches three directories, how do you determine the full `Path` for the same filename `log.txt` from three different keys?
5. Why must you check `event.kind() == OVERFLOW` before casting context to `Path`?
6. Does `pollEvents()` remove the key from the watch service or automatically `reset` it?
7. What does `key.reset()` returning `false` mean? Does it strictly prove the directory was deleted?
8. Is `WatchEvent.count()` synonymous with the number of modified files?
9. If a file is created and then deleted before the watcher processes `ENTRY_CREATE`, can you assume `Files.readAllBytes` will succeed?
10. Does `WatchService` guarantee watching an entire directory tree recursively across all providers?
11. What is the difference between `key.cancel()` and `watcher.close()`?
12. Does `ENTRY_MODIFY` guarantee the producer has closed the file and data will no longer change?
13. Why should a data-ingestion watcher have a rescan/snapshot strategy on `OVERFLOW`?
14. `watcher.take()` can block; how do you terminate the waiting thread when the application shuts down?
15. Why not use watcher events as an audit mechanism replacing an ordered transaction log?

## 18. Java SE 17 Documentation

- [`WatchService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html): `take()`, `poll()`, `poll(timeout, unit)`, service lifecycle.
- [`WatchKey`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html): `pollEvents()`, `reset()`, `cancel()`, `watchable()`, `isValid()`.
- [`WatchEvent`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html): `kind()`, `context()`, `count()`.
- [`StandardWatchEventKinds`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html): `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE`, `OVERFLOW`.
- [`Path.register`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): registering a `Path` with `WatchService`.

## 19. Key Takeaways

**`WatchService` returns a `WatchKey`; `WatchKey.pollEvents()` returns a list of `WatchEvent`s.** For directory entry change events, `event.context()` is a name/path **relative to the registered directory**, so it must be combined with `(Path) key.watchable()` or the corresponding root mapping.

After consuming events, call **`key.reset()`** and check the result to continue watching. Distinguish `reset()` from `cancel()`, handle `OVERFLOW` by rescanning state, and do not assume watching is recursive or records every change completely. A watcher is a **signal mechanism prompting file system inspection**, not a mirror of the file system or an absolute audit log.

# WatchService, Watchable, and Directory Registration in Java NIO.2

## 1. The Problem: Knowing When a Directory Changes

An application may need to refresh a file list after a user uploads images, detect a new configuration file placed in a directory, or react when a file is deleted. Repeatedly calling `Files.list()` or `Files.exists()` to scan an entire directory can waste I/O and makes it difficult to choose an appropriate polling interval.

Since Java 7, **Java NIO.2** provides a change-monitoring mechanism through `java.nio.file.WatchService`. The application **registers a directory** with the service and requests the event kinds to watch; when the file system detects a change, the service places a **`WatchKey`** into a queue for the application to retrieve and process.

A simple diagram:

```text
Path representing the directory
       |
       | register(watchService, ENTRY_CREATE, ...)
       v
     WatchKey --------------------------+
       |                                |
       | file added/deleted/modified    | tracks registration lifecycle
       v                                |
   WatchService                         |
       |                                |
       | take() / poll()                |
       v                                |
  Signalled WatchKey -------------------+
       |
       | pollEvents()
       v
 WatchEvent<?> with kind/count/context
       |
       | processing done -> key.reset()
       v
 Continue waiting for new events
```

Three objects hold three responsibilities:

- **`WatchService`**: the notification source and queue of watch keys that have pending events.
- **`Watchable`**: an object that *can be registered* with a watch service; in the directory-watching module, `Path` is the type used.
- **`WatchKey`**: a token representing **a single registration** and holding the pending events for that registration.

**Scope note:** this is a *change-notification mechanism for file system objects*, not a file-content streaming mechanism, and it does not guarantee recording one event record per physical operation on every operating system.

## 2. Core Concepts and API

Related classes/interfaces in the `java.nio.file` package:

| Component | Role | Example API |
| --- | --- | --- |
| `WatchService` | Receives signalled keys; manages watcher lifecycle | `poll()`, `poll(timeout, unit)`, `take()`, `close()` |
| `Watchable` | Allows registering for change notifications | `register(watcher, events...)` |
| `Path` | Represents a path; implements `Watchable` | `dir.register(...)` |
| `WatchKey` | Manages a registration, retrieves events, and re-enables | `pollEvents()`, `reset()`, `cancel()`, `isValid()`, `watchable()` |
| `WatchEvent<T>` | A detected event | `kind()`, `count()`, `context()` |
| `StandardWatchEventKinds` | Standard event kinds | `ENTRY_CREATE`, `ENTRY_DELETE`, `ENTRY_MODIFY`, `OVERFLOW` |
| `FileSystem` | Creates a watch service corresponding to the file system | `newWatchService()` |

Common initialization workflow:

```java
try (WatchService watcher =
         FileSystems.getDefault().newWatchService()) {
    Path dir = Path.of("watched-directory");
    WatchKey key = dir.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY
    );

    // Retrieve the key from watcher and process WatchEvent<?>.
}
```

This is an **illustrative snippet**, not a complete program: the directory must exist, and the program needs imports, exception handling, and a monitoring loop. You should use `try-with-resources` because `WatchService` is closeable and holds operating system resources.

### `Watchable` vs. `WatchService`

`Watchable` specifies the ability to **register**. `Path` implements this interface, so we call `dir.register(watcher, ...)` directly. Conversely, `WatchService` **does not contain an ordinary `register(Path)` method**; the watched object registers itself with its watcher.

The standard declaration of `Watchable` has two forms:

```java
WatchKey register(
        WatchService watcher,
        WatchEvent.Kind<?>... events) throws IOException;

WatchKey register(
        WatchService watcher,
        WatchEvent.Kind<?>[] events,
        WatchEvent.Modifier... modifiers) throws IOException;
```

The above are abbreviated API signatures. For basic usage, use the varargs version of `StandardWatchEventKinds` without modifiers. Java SE 17 does not define **standard modifiers**; if file-system/JDK-specific modifiers exist, you must evaluate compatibility separately.

## 3. You Must Register an **Existing Directory**, Not Individual Files

In Java SE 17 with the standard usage of `Path.register`, the registered path is **an existing directory**; events represent changes to **the entries of that directory**.

Example directory tree:

```text
project/
├── config.json
├── a.txt
└── nested/
    └── x.txt
```

If you register `project/`:

- Creating `project/new.txt` may produce `ENTRY_CREATE`.
- Deleting `project/a.txt` may produce `ENTRY_DELETE`.
- Modifying the contents of `project/config.json` may produce `ENTRY_MODIFY`.
- Creating `project/nested/new.txt` **is not observed by default** because `WatchService` does not automatically watch an entire directory tree.

**Registration is non-recursive by default.** To monitor subdirectories, you must register each existing directory individually, and also register new subdirectories when they appear. Changes occurring **between detecting a new directory and registering it** can be missed; therefore, a robust solution needs a scanning/reconciliation step if changes must not be lost.

If you pass a file path instead of a directory, the registration operation does not match the standard contract and may throw `NotDirectoryException` or `IOException` depending on the system. A non-existent directory also cannot be monitored by "pre-registering and waiting for it to be created" on that same path. Register **the existing parent directory** to watch for the creation of child entries.

Example:

```java
Path parent = Path.of("/data").toAbsolutePath();
Path watchedChild = parent.resolve("incoming");

// Register parent first, then receive ENTRY_CREATE for "incoming"
// if it is created directly inside parent.
```

This snippet only illustrates paths; do not assume the `/data` directory exists in every environment, and it is not a standalone runnable program.

## 4. The Three Standard Event Kinds for Directory Entries

Constants defined in `StandardWatchEventKinds`:

| Event kind | When is it typically reported? | `context()` |
| --- | --- | --- |
| `ENTRY_CREATE` | An entry is created or moved **into** the watched directory | Relative `Path` pointing to the newly appeared entry |
| `ENTRY_DELETE` | An entry is deleted or moved **out of** the watched directory | Relative `Path` pointing to the disappeared entry |
| `ENTRY_MODIFY` | An entry in the directory is modified | Relative `Path` pointing to the modified entry |
| `OVERFLOW` | Events may have been lost or discarded due to exceeding limits | Usually `null`; must not be cast as an entry event |

**Create/modify/delete events are signals, not an absolutely exact log.** The operating system may coalesce multiple modifications into a single event, generate multiple events when an application writes a file, or exhibit different ordering behavior. For example, editors often write to a temporary file and then rename it to replace the original file; you may observe create/delete instead of a single modify.

`OVERFLOW` **is registered automatically**; you do not need to and should not rely on listing it in the `events` array to receive notifications.

For `ENTRY_CREATE`, `ENTRY_DELETE`, and `ENTRY_MODIFY` when watching a directory, `event.context()` is a **relative path with respect to the registered directory**. It is usually just the entry name, such as `notes.txt`; it is not an absolute path by default.

How to determine the target path:

```java
Path watchedDir = (Path) key.watchable();

for (WatchEvent<?> event : key.pollEvents()) {
    if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
        // There is no reliable filename context in this event.
        continue;
    }

    Path relative = (Path) event.context();
    Path affected = watchedDir.resolve(relative);

    System.out.println("Event: " + event.kind()
            + ", path: " + affected);
}
```

This is an illustrative snippet that requires imports and a valid `key` variable. Casting `(Path) event.context()` is appropriate for **entry events on a `Path` registered to watch a directory**; it should not be applied indiscriminately to implementation-specific kinds or `OVERFLOW`.

## 5. Registering a Directory via `Path.register`

Common pattern:

```java
Path directory = Path.of("watch-me").toAbsolutePath();
try (WatchService service =
         directory.getFileSystem().newWatchService()) {

    WatchKey key = directory.register(
        service,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE,
        StandardWatchEventKinds.ENTRY_MODIFY);

    // Wait for notifications and call key.reset().
}
```

Here `getFileSystem().newWatchService()` ensures the watcher is created from **the same `FileSystem`** as the path. For paths on the default file system, `FileSystems.getDefault().newWatchService()` is usually equivalent. Do not mix a `Path` from one provider with a `WatchService` from another provider and assume they are compatible.

**Checks to keep in mind early:**

- `Files.isDirectory(directory)` may return `true` at check time, yet the directory could still be deleted/moved during registration.
- Process permissions must allow watching the directory.
- A `FileSystem`/provider may **not support watch service** or certain event kinds/modifiers.
- `register` may throw `IOException`, `UnsupportedOperationException`, `IllegalArgumentException`, or `ClosedWatchServiceException` depending on the situation.

### Re-registering an Object with the Same `WatchService`

According to `Watchable.register`, if an object is already registered with **the same `WatchService`**, calling `register` again retrieves the key for that registration while **updating the set of watched event kinds/modifiers**. Pending events are not automatically discarded just because the interest set changes.

Conceptual example:

```java
WatchKey first = dir.register(service,
        StandardWatchEventKinds.ENTRY_CREATE);

WatchKey second = dir.register(service,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_DELETE);

// With the same Path and service having a valid registration,
// this is the key representing the same updated registration.
```

Do not use re-calling `register` as a guaranteed way to "flush the old queue", and do not assume a key after `cancel()` can still be used to continue watching; a cancelled key becomes invalid.

## 6. `WatchKey`: The Ready, Signalled, and Reset Lifecycle

`WatchKey` is the key to understanding the mechanism:

```text
          registration succeeds
                 |
                 v
               READY
                 |
          event is detected
                 |
                 v
             SIGNALLED ------> placed into WatchService queue
                 |                        |
                 |                        v
                 |                    take()/poll()
                 |                        |
                 |                        v
                 |                 key.pollEvents()
                 |                        |
                 |                        v
                 +<------ key.reset() after processing
                             |
                      +------+-------+
                      |              |
               key still valid   key invalid
                      |              |
              returns to READY    cancel/cleanup
            or requeues immediately
            if events remain pending
```

**Once a key is signalled**, new events can continue to accumulate on the key, but the key is not re-added to the service's queue for each newly arriving event. After finishing processing the events, the application must call `key.reset()` to allow future signalling/enqueuing.

Important methods:

| API | Meaning |
| --- | --- |
| `key.pollEvents()` | Retrieves the list of accumulated events and removes them from the pending list |
| `key.reset()` | Completes the processing round and returns the key to a state where it can be signalled again; returns boolean |
| `key.isValid()` | Checks whether the key still represents a valid registration |
| `key.cancel()` | Cancels the registration; the key becomes invalid |
| `key.watchable()` | Returns the registered object, e.g., the directory `Path` |

`key.reset()` returns **`true`** if the key is still valid and has been reset; **`false`** if the key cannot be reset because it is no longer valid. If pending events remain after reset, the key may be **re-added to the queue immediately**, rather than necessarily waiting for another physical change.

A key can be cancelled automatically if the watched directory is deleted or the file system becomes inaccessible. Therefore, if `reset()` returns `false`, the application needs to remove the registration from its management structures and handle cleanup or recovery according to policy. Do not loop infinitely just because `reset()` was called once.

### Why Is Resetting Too Early Also Dangerous?

If multiple threads retrieve keys from the same watch service, you must ensure only one consumer is processing events for the same watchable at a time. Calling `reset()` **before** finishing processing can cause the key to be signalled and queued again, leading to two consumers processing the same directory concurrently and causing race conditions. Even though `WatchService` allows sharing across multiple consumers, **processing order for the same key** still needs explicit coordination.

## 7. `take()` and the Two Forms of `poll()`

`WatchService` provides three ways to retrieve a key:

| Method | Waits? | Result when no key is available |
| --- | --- | --- |
| `watcher.poll()` | No | Returns `null` immediately |
| `watcher.poll(timeout, TimeUnit.SECONDS)` | Yes, up to timeout | Returns `null` if the timeout expires |
| `watcher.take()` | Can wait until a key is available | Does not use `null` to indicate timeout, because there is no timeout |

Main processing pattern:

```java
while (running) {
    WatchKey key = watcher.take();

    for (WatchEvent<?> event : key.pollEvents()) {
        // Process event.
    }

    boolean valid = key.reset();
    if (!valid) {
        // Remove the invalid registration from the application.
    }
}
```

This is **Java-like pseudocode**; `running`, `watcher`, and the handler need to be defined. `take()` can throw `InterruptedException` if the thread is interrupted while waiting, and `ClosedWatchServiceException` if the service has been closed.

If the program needs to check a stop condition periodically, `poll(timeout, unit)` is often easier to structure than `take()` waiting indefinitely. If you want to request stopping from another thread, closing the `WatchService` wakes up the waiting thread and causes the call to throw `ClosedWatchServiceException`; handle that exception as part of the shutdown lifecycle rather than automatically treating it as an unrecoverable error.

**Do not busy-poll:**

```java
while (watcher.poll() == null) {
    // An empty loop can burn CPU!
}
```

Use `take()` or `poll(timeout, unit)` as appropriate.

## 8. Standalone Java 17+ Example: Registering, Checking, and Cancelling a `WatchKey`

To have **deterministic** stdout, the first example focuses on the registration lifecycle and does not depend on when the operating system emits events. The program creates a temporary directory, creates a watch service from the same file system, registers three event kinds, checks that the key is valid, and intentionally cancels the key.

**File `WatchRegistrationDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

public class WatchRegistrationDemo {
    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("watch-demo-");

        try {
            try (WatchService service =
                     directory.getFileSystem().newWatchService()) {

                WatchKey key = directory.register(
                        service,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_DELETE,
                        StandardWatchEventKinds.ENTRY_MODIFY);

                System.out.println(
                        "Thu muc ton tai: " + Files.isDirectory(directory));
                System.out.println("Key hop le: " + key.isValid());
                System.out.println(
                        "Watchable trung Path: "
                        + key.watchable().equals(directory));

                key.cancel();
                System.out.println(
                        "Key sau cancel: " + key.isValid());
            }
        } finally {
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run with **JDK 17+** on a file system that supports watch service:

```bash
javac WatchRegistrationDemo.java
java WatchRegistrationDemo
```

**Stdout if service creation, registration, and cleanup succeed:**

```text
Thu muc ton tai: true
Key hop le: true
Watchable trung Path: true
Key sau cancel: false
```

Explanation:

1. `Files.createTempDirectory` creates a real directory, avoiding errors from registering a non-existent path.
2. `directory.getFileSystem().newWatchService()` creates a watcher corresponding to the directory's `FileSystem`.
3. `directory.register(...)` returns a `WatchKey`; this is a registration for **the directory**, not for a child file.
4. `key.watchable().equals(directory)` verifies that the key references the registered object.
5. `key.cancel()` makes the key invalid, without needing any prior event.
6. `try-with-resources` closes the watch service, and `finally` deletes the temporary directory. If the platform does not support watchers or an I/O error occurs, the program may throw an exception instead of printing the stdout above.

**`cancel()` is not `reset()`.** `cancel` ends the registration; `reset` is used after each processing round when you still want to monitor the directory.

## 9. Java 17+ Example: Watching Directory Events

The following example creates a file inside the registered directory itself. It uses `poll(timeout)` to avoid waiting indefinitely, prints the actual event kind and entry name, handles `OVERFLOW`, calls `reset()` after reading the events, and closes all resources.

**File `WatchEventsDemo.java`:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class WatchEventsDemo {
    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watched-");
        Path file = directory.resolve("sample.txt");

        try {
            try (WatchService service =
                     directory.getFileSystem().newWatchService()) {

                directory.register(
                        service,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Files.writeString(file, "Hello WatchService");
                WatchKey key = service.poll(3, TimeUnit.SECONDS);

                if (key == null) {
                    System.out.println("Khong co key trong 3 giay");
                } else {
                    List<WatchEvent<?>> events = key.pollEvents();

                    for (WatchEvent<?> event : events) {
                        if (event.kind() ==
                                StandardWatchEventKinds.OVERFLOW) {
                            System.out.println("OVERFLOW: can quet lai");
                            continue;
                        }

                        Path entry = (Path) event.context();
                        Path absolute = directory.resolve(entry);
                        System.out.println(event.kind().name()
                                + ": " + absolute.getFileName()
                                + " (count=" + event.count() + ")");
                    }

                    boolean valid = key.reset();
                    System.out.println("Key con hop le: " + valid);
                }
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile/run:

```bash
javac WatchEventsDemo.java
java WatchEventsDemo
```

**One observable result, not guaranteed stdout:**

```text
ENTRY_CREATE: sample.txt (count=1)
ENTRY_MODIFY: sample.txt (count=1)
Key con hop le: true
```

**Why can we not claim exact stdout?** `WatchService` receives signals from file system mechanisms that are platform-dependent. One system may emit an extra `ENTRY_MODIFY`, coalesce events, or not enqueue the key within 3 seconds. Event order/count/number may vary. Therefore the program **prints actual events** rather than fabricating a forced order.

Another limitation: the example calls `poll(...)` only once, enough to demonstrate retrieving one key. If pending events remain after `reset()` or new events arrive, a real monitoring application must **continue the loop** instead of concluding that a single poll has collected all changes. Writing with `Files.writeString` can also trigger modify events in addition to create; this is not a bug.

## 10. `WatchEvent.context()`, `count()`, and Resolving the Path

Each `WatchEvent<?>` has:

- `kind()`: the event type.
- `count()`: the number of times the event has been accumulated/coalesced (not byte count or file size).
- `context()`: kind-dependent data; for standard entry events, typically the entry's relative `Path`.

Example:

```text
Registered directory: /srv/inbox
event.kind(): ENTRY_CREATE
event.context(): daily.csv
event.count(): 1

Path to process:
    /srv/inbox/daily.csv
```

Because context is a relative path, use:

```java
Path directory = (Path) key.watchable();
Path relative = (Path) event.context();
Path fullPath = directory.resolve(relative);
```

Do not use `Path.of(event.context().toString())` as though it were always an absolute path. If the registered directory is represented by a relative path, `resolve` may also produce a relative result; call `toAbsolutePath()` when you truly need an absolute path, and consider symlinks/canonicalization in security-sensitive applications.

If an application handles an event by opening or deleting a file, check its state **at the time of use**: the entry may have been deleted, moved, or replaced between when the event was detected and when the handler acts (*time-of-check to time-of-use*). An event does not grant access permissions, does not hold a lock, and does not capture a data snapshot of the file.

## 11. `OVERFLOW`: Notifications Cannot Be Treated as a Complete Change List

`WatchService` may have a limit on the number of accumulated events. When the implementation knows that events have been discarded, it provides `OVERFLOW`. You can encounter `OVERFLOW` even if you only registered create/delete/modify.

Proper handling:

```java
if (event.kind() == StandardWatchEventKinds.OVERFLOW) {
    // Mark observed state as potentially incomplete.
    // Rescan directory entries or resynchronize the index.
    continue;
}
```

The point is not to "try re-reading that exact event" because the detailed information has been lost. The application should **scan the current state** of the watched directories and reconcile it against recorded state/metadata to restore consistency.

Example of a service maintaining a file cache:

1. On startup, retrieve the list of existing files.
2. While running, apply create/delete/modify to update the cache.
3. When `OVERFLOW` occurs, mark the cache as potentially stale.
4. Rescan the directory and rebuild the cache state.
5. Continue receiving events, with a mechanism to coordinate changes occurring during the scan.

**You cannot turn `WatchService` into a lossless audit log** merely by speeding up the event-reading loop. If you need to be certain of *every* change (without missing any) for critical business logic, you need a separate event-publishing protocol/transaction log, reconciliation, or a data source with appropriate durability.

## 12. Timing Limitations and Modified File Contents

`ENTRY_MODIFY` **does not mean the file has finished being written**. Another application may still have the file open and continue writing while you receive the event. Therefore, a file watcher used for data ingestion needs a "file is ready" signal design, for example:

- The producer writes to a temporary filename, closes the file, and then renames it into the incoming directory if the file system and rename strategy are appropriate.
- The receiver waits for a "complete" marker/manifest emitted last by the producer.
- The application verifies integrity or checks that length/metadata remains stable over an appropriate interval, while accepting that this is only a **heuristic**, not an absolute guarantee.

If a file receives `ENTRY_CREATE` and then `ENTRY_DELETE` before the handler processes it, calling `Files.readAllBytes(fullPath)` may throw `NoSuchFileException`. Handlers should treat an event as a "hint to re-check state" rather than a command guaranteeing that opening the file will always succeed.

In multi-writer systems, events for the same entry can appear in rapid succession. **Application-level debouncing/coalescing** is needed if processing is expensive, but you must not simply drop events based on timing and then claim no business changes were lost.

## 13. Proper Long-Running Monitoring Loop

An event loop skeleton using `WatchService`:

```java
try (WatchService watcher =
         directory.getFileSystem().newWatchService()) {

    directory.register(
        watcher,
        StandardWatchEventKinds.ENTRY_CREATE,
        StandardWatchEventKinds.ENTRY_MODIFY,
        StandardWatchEventKinds.ENTRY_DELETE);

    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.take();

        try {
            for (WatchEvent<?> event : key.pollEvents()) {
                if (event.kind() ==
                        StandardWatchEventKinds.OVERFLOW) {
                    reconcileDirectory((Path) key.watchable());
                    continue;
                }

                Path root = (Path) key.watchable();
                Path entry = (Path) event.context();
                processEvent(event.kind(), root.resolve(entry));
            }
        } finally {
            boolean valid = key.reset();
            if (!valid) {
                break;
            }
        }
    }
}
```

**This is an illustrative skeleton, not a standalone Java program:** `directory`, `reconcileDirectory`, and `processEvent` must be declared, APIs imported, and `IOException`/`InterruptedException`/runtime exceptions handled. Using `finally` for `reset()` ensures the key lifecycle is handled even if the handler throws an error, **but it does not automatically make business errors safe**; depending on the application, you may need to mark a resync as required if the handler fails before processing all events.

If monitoring **multiple directories**, you cannot `break` out of the entire event loop just because one key becomes invalid while other keys remain valid. Instead, manage a registry and only terminate when there are no more targets to watch or when a shutdown signal arrives.

### Registry of Multiple Directories

One way to organize it:

```java
Map<WatchKey, Path> roots = new HashMap<>();

WatchKey keyA = dirA.register(watcher, ENTRY_CREATE, ENTRY_DELETE);
roots.put(keyA, dirA);

WatchKey keyB = dirB.register(watcher, ENTRY_CREATE, ENTRY_DELETE);
roots.put(keyB, dirB);
```

This is an illustrative snippet requiring `dirA`, `dirB`, and appropriate imports; it is not a standalone runnable program. The next `take()` call can return **the key of whichever directory has events**. Use `roots.get(key)` or `(Path) key.watchable()` to identify the source. If `reset()` returns false, remove the key from the map. Do not equate `watcher` with a single directory once multiple locations have been registered.

## 14. Watching Subdirectories: Clarifying the **Non-Recursive** Behavior

Suppose you need to watch `root/sub1/sub2`. `root.register(watcher, ...)` only gives you changes to entries **directly** under `root`. To observe inside `sub1` and `sub2`, you must register them themselves.

Basic workflow:

1. Walk the existing directory tree using `Files.walkFileTree` or a suitable API.
2. Register each existing directory, storing `WatchKey -> Path`.
3. When receiving `ENTRY_CREATE` for a new subdirectory, check `Files.isDirectory(path)` at processing time and register that directory.
4. You may also scan contents underneath the newly appeared directory to compensate for the window before registration.
5. When a key becomes invalid, remove it from the registry and decide whether to attempt re-registration if the directory appears at a new location.

Additional considerations:

- Rules for following symlinks: can create cycles or escape outside the root directory. Use an explicit follow/no-follow policy.
- OS watcher limits and resources when the tree has hundreds of thousands of directories.
- Race condition when a directory is deleted between `isDirectory` and `register`.
- Moving/renaming a directory: there is no guarantee that every rename event is represented in one uniform standard across all platforms.
- Virtual, network, or container volume file systems may emit events differently from local disks.

Do not call a program watching only a parent directory a "recursive watcher" if it does not actually register child levels.

## 15. Differences from `Selector` and Network I/O

Although `WatchService` and `Selector` both handle "waiting for work":

| Aspect | `WatchService` | `Selector` |
| --- | --- | --- |
| Watched target | `Watchable`, usually a directory `Path` | `SelectableChannel`, usually a socket/pipe |
| Token | `WatchKey` | `SelectionKey` |
| Data source | File system entry change events | Channel readiness for I/O |
| How to wait | `take()`, `poll()` | `select()`, `selectNow()` |
| After processing | **`WatchKey.reset()`** | Retrieve/remove keys from `selectedKeys()` per event loop |
| Kinds/ops | `ENTRY_CREATE`/`DELETE`/`MODIFY`/`OVERFLOW` | `OP_ACCEPT`/`CONNECT`/`READ`/`WRITE` |

A common mistake is thinking `WatchKey.reset()` is equivalent to `iterator.remove()` on `Selector.selectedKeys()`. They belong to **two different APIs**, with different lifecycles and event payloads. `WatchService` returns a key holding a list of pending `WatchEvent`s; `Selector` returns a key indicating **I/O readiness types**, not a list of file changes.

Also do not use `FileChannel.configureBlocking(false)` to build a watcher for directory changes. `FileChannel` is not a selectable socket channel; `WatchService` is the API designed for directory entry events.

## 16. Operating System and File System Limitations

The Java specification allows a `WatchService` implementation to use native OS notification mechanisms or alternatives such as polling when no suitable native mechanism exists. Therefore:

- **Notification timing** may differ from when the change actually occurred.
- **Event count and ordering** may vary across Linux, Windows, macOS, file system providers, or JDK vendors.
- **Coalescing** may merge events of the same kind; `event.count()` reflects the accumulated count per contract, not proof of every individual operation.
- **`OVERFLOW`** indicates events may have been lost; even without receiving overflow, you should design with reconciliation if business correctness is a strict requirement.
- **Permissions, symlinks, renames, and truncations** can cause complex or differing behavior.
- **File systems without watcher support** can throw `UnsupportedOperationException` when creating the service; do not assume every `FileSystem` supports watching.

In particular, **there is no guarantee that a modify event means "the writer has closed the file"**. An event is change-detection information, not a promise that data is stable and ready for ingestion.

High-reliability applications typically combine a watcher for early detection with **state-rescanning mechanisms**, separate logs, or synchronization protocols between components.

## 17. Common Exceptions and Pitfalls

| Issue | Result / Risk | How to Handle |
| --- | --- | --- |
| Registering a file `Path` instead of a directory | Wrong target; may throw `NotDirectoryException` | Register the existing parent directory |
| Registering a non-existent path | Cannot register the intended target | Create/check the directory before registering |
| Registering unsupported events/modifiers | `UnsupportedOperationException` or argument error | Use only standard kinds and verify the provider |
| Forgetting to call `key.reset()` | Key may not be re-queued for subsequent rounds | Reset after processing pending events |
| Calling `reset()` before finishing processing the same key | Another consumer may process concurrently | Manage one owner per key; reset afterward |
| Thinking `pollEvents()` reads events repeatedly without consuming them | Ignores the retrieve-and-clear behavior for pending events | Process the retrieved list once |
| Thinking `take()` always returns immediately | Thread may wait forever if no events occur | Provide shutdown/interrupt/close or poll timeout |
| Treating `OVERFLOW` as a filename | `context()` is not an entry `Path` | Scan and reconcile the directory |
| Casting `event.context()` to `Path` for every kind | Can have wrong type/null | Check kind first |
| Reading `ENTRY_MODIFY` as a completed file | Data not yet stable | Completion protocol, rename/marker/reconciliation |
| Watching only the parent directory and believing the whole tree is watched | Misses changes in subdirectories | Register each directory |
| Closing `WatchService` while still calling `take()` | `ClosedWatchServiceException` | Handle shutdown properly |
| Ignoring `InterruptedException` | Worker is hard to stop cleanly | Restore interrupt flag or exit per policy |
| Not handling `reset()==false` | Loop keeps an invalid key | Remove from registry, decide whether to re-register |
| Using continuous busy-polling | High CPU usage | `take()` or `poll(timeout)` |
| Not closing `WatchService` | Native resource leak | `try-with-resources` |
| Trusting events to provide a file snapshot | Race when entry is deleted/replaced | Check file state at time of use |

## 18. Self-Check Questions

**Question 1.** Is `WatchService` the object on which `register(ENTRY_CREATE)` is called directly?

**Answer:** Usually **no**. A `Watchable` (such as a `Path` representing a directory) calls `register(watcher, kinds...)` and returns a `WatchKey`.

**Question 2.** When `watcher.take()` returns a `WatchKey`, can you skip `reset()` if you want to keep watching?

**Answer:** No. After processing `pollEvents()`, you must call `reset()` and check the validity boolean. If the key remains in the signalled state, subsequent events may still accumulate, but the key will not be re-queued as you expect.

**Question 3.** Does registering `root` receive `ENTRY_CREATE` for `root/a/b.txt`?

**Answer:** Not by default. The watcher monitors direct entries of `root`; you must register `root/a` if you want to watch changes to the `b.txt` entry.

**Question 4.** When `event.kind()==ENTRY_DELETE`, can you open the file via `dir.resolve(event.context())` and expect it to still exist?

**Answer:** No. The event indicates the entry was deleted or moved away; the path may no longer exist. Handlers must handle `NoSuchFileException` and check state at time of use.

**Question 5.** When `OVERFLOW` occurs, a specific event may have been dropped. What is the right solution?

**Answer:** Mark the watched state as incomplete and **rescan the directory state**, restoring caches/indexes per design. You cannot recover the exact lost events simply by calling `pollEvents()` again.

**Question 6.** After `WatchKey.cancel()`, does `key.watchable()` still return the registered `Path`?

**Answer:** Yes, per the `WatchKey.watchable()` contract, this method still returns the watchable object even after the key has been cancelled. However, that **does not** make the key valid again or prove the directory still exists.

## 19. Summary and References

To use `WatchService` properly, remember the sequence of operations:

1. **Create** a `WatchService` from the appropriate `FileSystem`.
2. **Register** a `Path` pointing to an existing directory using `Path.register(watcher, ENTRY_...)`.
3. **Wait** for a `WatchKey` via `take()` or `poll(...)`.
4. **Iterate** over `key.pollEvents()`; handle kind, relative context, count, and `OVERFLOW`.
5. **Reset** with `key.reset()`; if false, clean up the invalid registration.
6. **Close** the watcher with proper lifecycle management; handle interrupts, races, concurrency, and unsupported providers.

**Key takeaway:** `WatchService` is a **change-detection** mechanism, not a log guaranteed to record every event. `Watchable` defines how registration works, `WatchKey` represents a registration and must be reset after each round, and `WatchEvent` carries the detected details. When accuracy matters, combine events with re-checking the **actual file system state**.

**Official references for Java SE 17:**

- [WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
- [Watchable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Watchable.html)
- [WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html)
- [Path.register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html)
- [StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)

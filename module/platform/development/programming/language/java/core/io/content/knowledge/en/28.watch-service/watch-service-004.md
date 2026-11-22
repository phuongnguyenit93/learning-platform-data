# Java WatchService: take, poll, and the Event-Processing Loop

## 1. Problem and Scope

When an application needs to know when a directory has a new file, a modified file, or a deleted entry, Java NIO.2 provides **`WatchService`** in the `java.nio.file` package. Instead of repeatedly rescanning the entire directory with `Files.list(...)`, an application can register for monitoring and consume change signals via **`WatchKey`**.

The three common ways to retrieve a key are:

- `watchService.take()`: **waits** until a key is signalled.
- `watchService.poll()`: **checks immediately**; if no key is available, returns `null`.
- `watchService.poll(timeout, unit)`: **waits with a time limit**; returns `null` if the timeout expires without a key.

The topic "take, poll, and the event-processing loop" is not just about learning three method signatures. A proper monitoring loop must also drain `pollEvents()`, resolve relative paths, always return the key to a ready state via `reset()`, watch out for `OVERFLOW`, and close the service cleanly on shutdown.

**Learning objectives:** understand the cycle register → wait for key → process events → reset → repeat; choose between `take` and `poll` based on latency and shutdown needs; avoid losing events due to misusing `WatchKey`; build a runnable Java 17+ test program.

## 2. Core Components

| Component | Meaning |
|---|---|
| `FileSystems.getDefault().newWatchService()` | Creates a watch service for the default file system |
| `Path.register(watcher, kinds...)` | Registers a directory and the event kinds of interest |
| `WatchKey` | Registration token receiving signals; linked to a watched object |
| `watchService.take()` | Waits for a signalled key |
| `watchService.poll()` | Retrieves a signalled key immediately if available |
| `watchService.poll(timeout, unit)` | Retrieves a key if available within the timeout |
| `key.pollEvents()` | Retrieves and clears the list of pending events in the key |
| `key.reset()` | Resets the key to continue receiving signals; returns `false` if no longer valid |
| `key.watchable()` | Returns the registered object (typically a directory `Path`) |
| `key.cancel()` | Cancels the key's registration |
| `watchService.close()` | Closes the service and releases resources |

Commonly used standard event kinds:

- `StandardWatchEventKinds.ENTRY_CREATE`: an entry directly appears in the registered directory.
- `StandardWatchEventKinds.ENTRY_MODIFY`: a direct entry has a change recognized by the provider.
- `StandardWatchEventKinds.ENTRY_DELETE`: a direct entry is deleted/disappears.
- `StandardWatchEventKinds.OVERFLOW`: indicates events may have been lost/discarded; requires resynchronizing state via an actual scan.

The `ENTRY_*` kinds typically carry `WatchEvent<Path>`; `context()` is the **name/path relative to the registered directory**, not an absolute path. `OVERFLOW` has different semantics and must not be assumed to provide a valid `Path`.

## 3. Register Before Waiting for Events

Example of registering an existing directory:

```java
import java.nio.file.*;
import static java.nio.file.StandardWatchEventKinds.*;

Path directory = Path.of("inbox");
try (WatchService watcher =
         FileSystems.getDefault().newWatchService()) {

    WatchKey key = directory.register(
            watcher, ENTRY_CREATE, ENTRY_MODIFY, ENTRY_DELETE);
    // Consume keys with take/poll, read events, and reset here.
}
```

This is an illustrative snippet; the code needs to be placed inside a method/class, the `inbox` directory must exist, and the provider must support registration. Often the directory is created beforehand with `Files.createDirectories(directory)` if business logic permits.

- `WatchService` **does not automatically watch every directory on the system**. Register each directory explicitly.
- `Path.register` returns the `WatchKey` for that registration; it is **not** a waiting call itself.
- Supported event kinds depend on the provider. Some file systems or runtime environments lack full support; in such cases `UnsupportedOperationException` or I/O exceptions can occur.
- Do not register a regular file path and assume directory-watch behavior across all providers: basic examples should watch **the directory containing the files**.
- Access permissions and platform details (local file system, remote mount, container...) can affect actual events.

## 4. Lifecycle of a `WatchKey`

A `WatchKey` has **ready** and **signalled** states. When a change occurs, the provider records the event into the corresponding key, and the key may then be placed into the `WatchService` queue for the application to retrieve.

```text
Register directory
      |
      v
Key READY  <------------------------+
      |                              |
Event is recorded                    |
      v                              |
Key SIGNALLED, enqueued              |
      |                              |
      v                              |
take() or poll() retrieves key       |
      |                              |
      v                              |
pollEvents(): retrieves pending      |
      |       events                 |
      v                              |
Process each event                   |
      |                              |
      v                              |
reset() -----------------------------+
      |
      +-- false: key invalid -> drop registration / stop / recover
```

A `WatchKey` can accumulate **multiple events** before the application calls `pollEvents()`. If a key is already signalled, additional signals accumulate per the provider's mechanism rather than guaranteeing a separate queue entry per event.

**The `reset()` step is mandatory for the processing cycle**: after retrieving a key, the application must read events and then reset so the key can continue being notified properly. Without resetting, the loop may fail to receive subsequent signals as expected.

`reset()` returns `boolean`:

- `true`: the key remains valid to continue watching.
- `false`: the key is no longer valid, e.g., registration was cancelled, the target is no longer eligible for watching, or the service was closed.

When `reset() == false`, remove the key from management structures, consider re-registering the directory if it is recreated and policy allows; do not keep assuming the key still works.

## 5. `take()`: Waiting Until a Key Arrives

Signature:

```java
WatchKey key = watcher.take();
```

`take()` is a **blocking** operation: if no key is signalled yet, the calling thread waits. When a key arrives, it returns the key so the application can read the event list.

Suitable when:

- A dedicated worker monitors the file system and generally does not need to do other work while waiting.
- You want to avoid a busy loop repeatedly calling `poll()`.
- Shutdown is cleanly designed via interrupt/closing `WatchService` and handling exceptions.

`take()` can throw `InterruptedException` if the waiting thread is interrupted. Once the service is closed, the operation can throw `ClosedWatchServiceException`. In event-loop design, handle shutdown proactively rather than treating all such exceptions as data errors.

**Non-standalone** illustrative example:

```java
try {
    while (!Thread.currentThread().isInterrupted()) {
        WatchKey key = watcher.take();
        try {
            processEvents(key);
        } finally {
            if (!key.reset()) {
                break;
            }
        }
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (ClosedWatchServiceException ex) {
    // Service closed, usually a normal shutdown branch.
}
```

The `watcher` variable and `processEvents` method must be declared elsewhere. In real programs, use a `WatchKey -> Path` map and decide how to handle one of many keys becoming invalid; an invalid key does not always require stopping the whole service.

## 6. `poll()`: Non-Blocking Check

```java
WatchKey key = watcher.poll();
if (key == null) {
    // No signalled key at the time of check.
}
```

`poll()` **returns immediately**:

- Key available → returns the key to the processing loop.
- No key available → returns `null`.
- Service closed → may throw `ClosedWatchServiceException`.

Suitable when the application already has a main loop doing other work and only wants to check events periodically without blocking.

**Trap:** writing an infinite loop that only calls `poll()` and checks for `null` continuously can consume heavy CPU:

```java
// NOT recommended: hot spin loop when there are no events.
while (running) {
    WatchKey key = watcher.poll();
    if (key == null) {
        continue;
    }
    // ...
}
```

If using `poll()`, embed it in a cycle that has real work, rate-limit it, or use the `poll(timeout, unit)` overload. Do not manually add a long `Thread.sleep(...)` while ignoring shutdown/latency needs; usually timed poll expresses intent more cleanly.

## 7. `poll(timeout, unit)`: Bounded Wait

```java
WatchKey key = watcher.poll(500, TimeUnit.MILLISECONDS);
```

Unlike `poll()`, this overload can wait up to the requested duration when the queue has no key. If no signal arrives before expiration, it returns `null`. It can throw `InterruptedException` and `ClosedWatchServiceException` respectively.

Suitable for a processing loop that needs to:

1. Frequently process file change events.
2. Perform background tasks every interval, such as checking a stop flag, flushing metrics, or scanning against missed events.
3. Have a latency-bounded stop mechanism without immediately closing the service.

Example:

```java
while (running) {
    WatchKey key = watcher.poll(1, TimeUnit.SECONDS);

    if (key == null) {
        // After at most 1 second without a key: do periodic work if needed.
        continue;
    }

    processEvents(key);
    if (!key.reset()) {
        // Remove this registration / decide whether to retry.
    }
}
```

This is an illustrative snippet with `running` and `processEvents` needing external definitions. Do not treat a timeout as proof that the file system has not changed—an event may have been lost, coalesced, delayed, or the directory may not have been registered.

## 8. Quick Comparison of the Three Ways to Retrieve a Key

| Criterion | `take()` | `poll()` | `poll(timeout, unit)` |
|---|---|---|---|
| Blocks when no key is available? | Yes, may wait indefinitely | No | Yes, up to timeout |
| When no key is available | Keeps waiting | Returns `null` immediately | Returns `null` after timeout |
| Usually fits | Dedicated event-processing worker | Integrating into an existing main loop | Watch loop + periodic tasks |
| CPU note | No busy spin while waiting | Easy to busy spin if looped tightly | Typically avoids busy spinning |
| Interrupt | Can throw `InterruptedException` | Does not wait, so no checked interrupt | Can throw `InterruptedException` |
| When `WatchService` closes | `ClosedWatchServiceException` | `ClosedWatchServiceException` | `ClosedWatchServiceException` |
| Needs `pollEvents()/reset()`? | Yes | Yes, if a key is returned | Yes, if a key is returned |

No single option is "always best". Choose according to waiting needs, concurrent work on the thread, shutdown latency requirements, and the actual system. **WatchKey processing** is essentially the same across all three.

## 9. Processing Events in a `WatchKey`

After retrieving a key:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    WatchEvent.Kind<?> kind = event.kind();

    if (kind == StandardWatchEventKinds.OVERFLOW) {
        // Rescan / state synchronization needed.
        continue;
    }

    Path relativeName = (Path) event.context();
    Path directory = (Path) key.watchable();
    Path changed = directory.resolve(relativeName);

    System.out.println(kind.name() + ": " + changed);
}
boolean valid = key.reset();
```

This is an illustrative example requiring imports for `Path`, `WatchEvent`, `StandardWatchEventKinds`, and a `key` declaration. Key points to understand:

- `key.pollEvents()` returns the pending event list for **that key**, while removing the retrieved events from its pending list.
- `event.kind()` distinguishes create/modify/delete/overflow.
- For `ENTRY_*` events registered on a `Path`, `context()` is typically a **relative** `Path`. `directory.resolve(relativeName)` produces the path under the watched directory.
- Do not pass `event.context().toString()` directly to build an absolute path and guess the directory.
- `OVERFLOW` must be handled **before** casting `context()` to `Path`, because overflow context is not a valid filename to resolve.
- `event.count()` indicates how many times similar events were accumulated/coalesced per watch service semantics; **do not** infer that it is the exact write count or file version number.
- After processing, call `reset()` to continue operating. Even if the handler encounters a business error, the dispatch loop must have a policy so it does not forget to reset or close the registration.

### One Name Can Emit Multiple Events

An editor saving a file might create a temporary file, write the file, rename it, and delete the old file. A single user "Save" action can generate multiple events, and the sequence differs across Windows/Linux/macOS.

Even `ENTRY_MODIFY` can fire multiple times for a single write sequence. Therefore:

- Design **idempotent** handlers: processing the same file multiple times does not corrupt business state.
- You can **debounce**: wait briefly before processing the final contents, while still verifying that the file exists and is stable enough.
- Do not assume `ENTRY_CREATE` occurring means the file has finished being written.
- When full data processing is needed, applications typically check content/metadata after the event, with bounded retries if the file is still locked or not yet ready.

## 10. Complete Java 17+ Program with Timed Poll

The example creates a temporary directory itself, registers events, creates and modifies a file inside, and then retrieves `WatchKey`s within a bounded time window. The program does not print event counts/names/order as a fixed answer, because signals depend on the file system.

Create file **`WatchServiceLoopDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.ClosedWatchServiceException;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;
import java.util.concurrent.TimeUnit;

public class WatchServiceLoopDemo {

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("watch-demo-");
        Path file = directory.resolve("sample.txt");

        try {
            try (WatchService watcher =
                         FileSystems.getDefault().newWatchService()) {

                directory.register(watcher,
                        StandardWatchEventKinds.ENTRY_CREATE,
                        StandardWatchEventKinds.ENTRY_MODIFY,
                        StandardWatchEventKinds.ENTRY_DELETE);

                Files.writeString(file, "first\n", StandardCharsets.UTF_8);
                Files.writeString(file, "second\n", StandardCharsets.UTF_8);

                int receivedKeys = 0;
                long deadline = System.nanoTime()
                        + TimeUnit.SECONDS.toNanos(2);

                while (System.nanoTime() < deadline) {
                    long remaining = deadline - System.nanoTime();
                    if (remaining <= 0) {
                        break;
                    }

                    WatchKey key = watcher.poll(
                            remaining, TimeUnit.NANOSECONDS);

                    if (key == null) {
                        break;
                    }

                    receivedKeys++;
                    for (WatchEvent<?> event : key.pollEvents()) {
                        if (event.kind()
                                == StandardWatchEventKinds.OVERFLOW) {
                            System.out.println("Event: OVERFLOW");
                            continue;
                        }

                        Path name = (Path) event.context();
                        System.out.println("Event: "
                                + event.kind().name()
                                + ", name=" + name);
                    }

                    if (!key.reset()) {
                        System.out.println("WatchKey invalid");
                        break;
                    }
                }

                System.out.println("At least one key: "
                        + (receivedKeys > 0));
            } catch (ClosedWatchServiceException ex) {
                System.out.println("WatchService closed");
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run:

```bash
javac WatchServiceLoopDemo.java
java WatchServiceLoopDemo
```

**Typical stdout** on a system emitting create/modify for the file:

```text
Event: ENTRY_CREATE, name=sample.txt
Event: ENTRY_MODIFY, name=sample.txt
At least one key: true
```

**This is illustrative output, not a guarantee of exact stdout on all systems.** The number of `ENTRY_MODIFY` events, coalescing, ordering, and observation timing can vary. In an environment that does not emit events within the 2-second limit, the program may only print:

```text
At least one key: false
```

If the provider does not support watch service, lacks directory permissions, or encounters an I/O error, the program may throw an exception instead of printing the results above. A Java 17+ compiler and runtime can run the program standalone; actual event observability depends on the file system.

Step-by-step analysis:

1. `Files.createTempDirectory` creates an isolated directory; `Files.writeString` creates and writes the file to generate observable changes.
2. Register `ENTRY_CREATE`, `ENTRY_MODIFY`, `ENTRY_DELETE` **before** writing the file, avoiding missing the operations performed by the example immediately.
3. The timed poll loop uses `System.nanoTime()` to compute a relative deadline, instead of waiting 2 seconds anew for **each** key. It stops after the maximum time allocated to the waiting phase.
4. `pollEvents()` retrieves the event list; `OVERFLOW` is checked before casting context to `Path`.
5. `key.reset()` allows the key to keep watching if still valid.
6. `WatchService` is closed via try-with-resources. The demo file and directory are deleted in `finally`. That final deletion happens after closing the watcher, so it is not an event to expect in the output.

For more thorough testing, you can put modifications on a separate writer thread spaced a few hundred milliseconds apart. Still, do not assert that every write corresponds to strictly one `ENTRY_MODIFY` across all providers.

## 11. When Watching Multiple Directories: Map `WatchKey -> Path`

One `WatchService` can receive keys from multiple registered directories. Common pattern:

```java
Map<WatchKey, Path> directories = new HashMap<>();

WatchKey keyA = pathA.register(watcher, ENTRY_CREATE, ENTRY_DELETE);
WatchKey keyB = pathB.register(watcher, ENTRY_MODIFY);

directories.put(keyA, pathA);
directories.put(keyB, pathB);
```

This is an illustrative snippet requiring imports for `Map`, `HashMap`, `Path`, and static event kinds; `pathA` and `pathB` must be valid.

When retrieving a key:

```java
Path directory = directories.get(key);
if (directory == null) {
    // Key does not belong to the registrations managed by the app.
} else {
    for (WatchEvent<?> event : key.pollEvents()) {
        if (event.kind() == OVERFLOW) {
            // Rescan directory.
            continue;
        }

        Path relative = (Path) event.context();
        Path changed = directory.resolve(relative);
        // Handle changed according to event kind.
    }
}

if (!key.reset()) {
    directories.remove(key);
}
```

This is also an illustrative snippet assuming variables and constants are already declared. `(Path) key.watchable()` can be used instead of a map when only direct `Path`s are registered. A map lets the application attach extra metadata such as tenant, project, filter configuration, retry policy, or directory state.

**Do not reset keys that do not belong to you and ignore them forever** when sharing a `WatchService`: establish clear ownership management, cleanup, and thread-safety policies.

## 12. One Directory Does Not Mean Recursive Watching

In standard Java NIO.2, registering a directory typically receives events only for **direct entries** underneath:

```text
root/              <- register root
  a.txt            <- may receive ENTRY_MODIFY for a.txt
  nested/
    b.txt          <- does not automatically receive b.txt events via root watch
```

To watch a directory tree:

1. Traverse existing subdirectories and register **each directory**.
2. When seeing `ENTRY_CREATE` for a new directory, verify it is a directory and register it.
3. For deleted/moved directories, remove or handle invalid keys.
4. Implement a strategy against races between tree traversal and registration. Some changes may have already occurred before the subdirectory was registered.
5. Account for symbolic links, path cycles, access permissions, and resource limits if the tree is very large.

Do not write `root.register(watcher, ENTRY_CREATE)` and claim it can receive every change several levels deep. If a problem requires detecting **every single change reliably**, `WatchService` usually needs to be paired with snapshots/rescans or a specialized file system monitoring mechanism with an appropriate contract.

## 13. `OVERFLOW`: Events May Have Been Lost

`StandardWatchEventKinds.OVERFLOW` reports that events may have been dropped because the queue/resource manager could not keep up with the number of changes or for other provider reasons.

Dangerous mistake:

```java
for (WatchEvent<?> event : key.pollEvents()) {
    Path p = (Path) event.context(); // Wrong for OVERFLOW.
    process(p);
}
```

This is only a **counterexample** snippet; `process` is undefined. With `OVERFLOW`, treat the watched cache state as at risk of being **out of sync with the file system**:

- Mark the directory/tree as needing a **rescan** to obtain actual state.
- Compare the new snapshot against previously stored application state if business logic requires.
- Perform idempotent processing when changes are detected.
- Log/emit metrics for overflows and monitor whether the event loop is processing too slowly.
- Avoid treating the event stream as an exact event-sourcing system: after an overflow, you **cannot reconstruct every intermediate operation** from the remaining events alone.

Even when `OVERFLOW` is not observed, file system notifications can still coalesce events and depend on the provider, and should not replace actual state checks when high accuracy is required.

## 14. Reading Files on `ENTRY_CREATE`/`ENTRY_MODIFY`

`WatchService` reports **observed changes**, not a guarantee that "the file has finished being written" or "the writer has closed the handle".

For example, a producer might:

1. Create `report.csv`.
2. Write the header.
3. Write batches of rows.
4. Flush and close the file.

A consumer could receive `ENTRY_CREATE` right after step 1 and read an incomplete file.

Better design strategies:

- The producer writes to a temporary file, closes it, and then **renames/moves** it to the official name when ready, under a suitable file system contract.
- The consumer treats `ENTRY_CREATE` as a signal to check state, not synonymous with a completed transaction.
- If only `ENTRY_MODIFY` is available, debounce and re-read once the file stabilizes per policy; handle files still being written/locked.
- Design parsers to tolerate EOF and temporarily invalid formats; use bounded retries rather than infinite loops.
- When you only need the current state, re-read the snapshot/file state instead of trying to replay every individual event.

Do not open a file assuming it still exists: the entry may have been deleted/renamed **between the event and the open call** (TOCTOU). Check/read with handling for `NoSuchFileException` and permission errors.

## 15. Stopping the Loop Cleanly

### With a `take()` Loop

`take()` can wait indefinitely if no further changes occur. Common ways to stop:

- **Interrupt the thread** blocked in `take()`; catch `InterruptedException`, restore the interrupt flag if appropriate, and exit the loop.
- **Close the `WatchService`** from the control thread; the waiting thread may receive `ClosedWatchServiceException`.
- Use a dedicated shutdown protocol, ensuring no locks are held that could cause deadlock while the watcher stops.

Illustrative example:

```java
try {
    while (running) {
        WatchKey key = watcher.take();
        try {
            handle(key);
        } finally {
            key.reset();
        }
    }
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
} catch (ClosedWatchServiceException ex) {
    // Appropriate when the controller proactively closed the service.
}
```

This snippet is **not standalone**; `running`, `watcher`, and `handle` are defined by the application. With multiple keys, you still must check the return value of `reset()` and cancel/remove invalid registrations; this minimal snippet only illustrates the exit paths.

### With Timed Poll

When using `poll(500, MILLISECONDS)`, the thread gets regular opportunities to check a stop flag even when there are no events. Use `AtomicBoolean` or appropriate synchronization for `running` when updated by another thread.

```java
while (running.get()) {
    WatchKey key = watcher.poll(500, TimeUnit.MILLISECONDS);
    if (key == null) {
        continue;
    }

    try {
        handle(key);
    } finally {
        if (!key.reset()) {
            // Cancel/remove from registration structure.
        }
    }
}
```

This pattern avoids continuous busy spinning, and the time to notice the stop flag is bounded by the timeout plus callback processing time. It does not replace closing the service when the application releases resources.

### Closing the Service

`WatchService` implements `Closeable`, so use try-with-resources. After `close()`, `take/poll` are no longer valid key-consumption operations. `WatchKey.cancel()` cancels a single registration, which is not the same as closing the entire service.

## 16. Reliability and Practical Limitations

Do not treat `WatchService` as a full transaction queue/change log like a message broker:

- **Event count and ordering depend on the provider.** Modifications may be coalesced, events dropped on overflow, or signals delayed.
- **Rename/move** may be represented as create/delete, modify, or other combinations depending on the file system.
- **Remote mounts/network drives** may have different semantics from local file systems or lack full support.
- **Crash/restart**: `WatchService` does not provide a durable event history to replay changes that occurred while the application was down. A startup rescan is required.
- **File contents** are not included in events; handlers must read them themselves and handle files modified/deleted mid-flight.
- **Bursts of changes** can cause `OVERFLOW`. Keep event handling brief and offload heavy CPU/I/O tasks to a bounded worker pool.
- **Security:** do not treat paths from events as validated input; control the root directory, symbolic links, permissions, and untrusted data.
- **Resources:** registering thousands of directories incurs OS/provider cost. Clean up maps when keys become invalid to prevent leaks.
- **Multiple consumers on the same service:** if threads call take/poll concurrently, a single key may be consumed by one consumer; coordinate ownership rather than assuming every consumer receives a copy of events.

For tasks requiring zero missed changes (e.g., legal auditing), relying solely on `WatchService` is usually insufficient. Consider a change log at the data source or a transaction log designed for that purpose.

## 17. Common Pitfalls

1. **Forgetting `reset()`**: the key may stop emitting subsequent signals as expected.
2. **Calling `reset()` before processing events and losing track of event state**: complicates control flow; prefer draining `pollEvents()` and then resetting cleanly.
3. **Ignoring `reset()==false`**: continuing with an invalid registration, resulting in silently missing changes.
4. **Confusing `poll()==null` with "the directory definitely has not changed"**: it only means no signalled key was in the queue at the moment of the check.
5. **Using `poll()` in a hot spin loop**: CPU spikes when there are no events.
6. **Using `take()` without a shutdown mechanism**: the thread may wait forever.
7. **Not catching `InterruptedException` on take/timed poll**: loses the chance to stop gracefully.
8. **Forgetting to check `OVERFLOW` before casting `event.context()`**: context may not be a valid `Path`.
9. **Assuming `event.context()` is an absolute path**: it must be resolved against the directory attached to the key.
10. **Thinking `ENTRY_CREATE` means the file has finished being written**: risk reading a file still being written.
11. **Relying on strictly one `ENTRY_MODIFY` per save**: providers may coalesce or emit multiple notifications.
12. **Assuming watching a root is recursive**: each subdirectory must be registered individually.
13. **Processing files with heavy operations directly in the watch loop**: can cause backlog growth and overflow.
14. **Not handling files deleted/renamed before the handler reads them**: TOCTOU easily occurs.
15. **Forgetting to register new directories when watching a tree**: misses changes deeper inside.
16. **Not rescanning after `OVERFLOW` or restart**: application state can become out of sync.
17. **Not closing `WatchService`**: retains OS resources or waiting threads.
18. **Treating events as an exact history**: `WatchService` is a change-notification system, not an event journal.
19. **Keeping a path map without managing invalid `WatchKey`s**: reference leaks and loss of re-registration capability.
20. **Assuming code will produce identical stdout on every OS**: ordering and counts are not deterministic; tests should rely on eventual state and appropriate timeouts.

## 18. Choosing `take` vs. `poll` in Applications

### Case A — Dedicated File-Ingestion Service

One thread watches an `incoming` directory, doing work almost exclusively when files arrive. Using `take()` sleeps while waiting for changes without periodic wakeups. On shutdown, interrupt the thread or close the service and catch the appropriate exceptions. Handlers should offload heavy import work to a queue/worker pool and handle partially written files.

### Case B — GUI Application or Program with a Main Loop

The main loop already handles input and UI/other tasks. `poll()` can fit if called at a reasonable frequency without busy spinning. However, do not block the UI thread with `take()`; you can use a dedicated watcher thread and dispatch notifications to the UI dispatcher.

### Case C — Watcher Combined with Periodic Tasks

Use `poll(1, TimeUnit.SECONDS)` to wait for events with a limit, then check health, the stop flag, and run periodic rescans if needed. Whenever a key is returned, still drain events and reset.

### Case D — Watching a Large Directory Tree

Requires mapping keys, registering each directory, registering newly created directories, and handling invalid keys and overflow. You can use one `WatchService` and one consumer loop, dispatching heavy work to an executor. For very large trees, consider resource limits and OS characteristics.

### Case E — Critical State Synchronization

`WatchService` is a **trigger** to read new state, not the sole data source. Register the watch, scan an initial snapshot, process changes, and rescan on overflow or restart. For exactly-once requirements, separate transaction/idempotency mechanisms and logs are required.

## 19. Self-Check Questions

**Question 1.** Does `take()` return `null` when there are no events?  
**No.** Normally it waits until a key arrives; when interrupted or the service closes, it can throw an exception.

**Question 2.** Does `poll()` returning `null` mean the file system has never had any changes?  
**No.** It only means no signalled key was ready in the service at the moment of the call.

**Question 3.** How does `poll(2, TimeUnit.SECONDS)` differ from `take()`?  
**It waits up to the timeout**, and can then return `null`; `take` can wait indefinitely.

**Question 4.** Why is `key.reset()` needed after processing `pollEvents()`?  
**To return the key to the ready state** for the next signal if the registration is still valid.

**Question 5.** What should you do if `reset()` returns `false`?  
**Stop relying on that registration**; remove/cancel the key per policy, and if needed wait for the directory to exist and re-register.

**Question 6.** Does a `WatchService` registered on `root` automatically receive `ENTRY_MODIFY` for `root/nested/a.txt`?  
**Do not assume so.** Java NIO.2 usually watches direct entries only; `nested` must be registered separately.

**Question 7.** Can you call `(Path) event.context()` for `OVERFLOW`?  
**No.** You must identify `OVERFLOW` first and use rescanning to synchronize state.

**Question 8.** Upon seeing `ENTRY_CREATE`, can you assume the producer has closed the file and the file is complete?  
**No.** The producer may still be writing; you need a publish/rename protocol or stability check.

**Question 9.** Why can running `poll()` in a `while(true)` loop without waiting be harmful?  
**Because of busy spinning**, continuously consuming CPU when there are no events.

**Question 10.** If a process needs to accurately audit every single file write, is `WatchService` enough?  
**Usually not.** Events can be coalesced/lost and do not survive restarts; an audit/journal mechanism at the appropriate layer is needed.

## 20. Summary

- **`WatchService.take()`**: waits for a signalled key; fits a dedicated watcher thread.
- **`WatchService.poll()`**: checks immediately, returning `null` if no key is available; avoid busy loops.
- **`WatchService.poll(timeout, unit)`**: waits with a bound; fits processing loops with periodic tasks and clean shutdown.
- **Proper cycle**: register → retrieve key → `pollEvents()` → handle `ENTRY_*`/`OVERFLOW` → `reset()` → continue.
- **`WatchEvent.context()` is a relative path** of a direct entry in the registered directory; resolve it against the key's directory.
- **Invalid keys, `OVERFLOW`, restarts, files being written, and recursive watching** must be handled explicitly to make watchers more reliable.
- **`WatchService` is a change signal, not an exact log of every file system operation.** When high consistency is required, combine actual state inspection, idempotency, and recovery.

### Java 17 Documentation

- [WatchService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchService.html)
- [WatchKey](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchKey.html)
- [WatchEvent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/WatchEvent.html)
- [StandardWatchEventKinds](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardWatchEventKinds.html)
- [Path.register](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html#register(java.nio.file.WatchService,java.nio.file.WatchEvent.Kind...))

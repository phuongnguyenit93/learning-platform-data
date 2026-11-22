# File Locks, WatchService, and Filesystem Monitoring Resources

Java applications can use file locks to coordinate access between multiple processes and use `WatchService` to receive notifications when directories or files change. Both features rely on operating system resources: `FileLock` is tied to a `FileChannel`, while `WatchService` typically uses the platform's directory watching mechanism. When an application runs with CRaC, it should not be assumed that these native handles remain valid after the process is restored.

In the checkpoint–restore workflow, the application needs to bring those resources to a safe state before checkpoint, then reopen the lock and re-register watching after restore. With `WatchService`, directory contents must be resynchronized because events may have occurred during the period when the watcher was closed. With `FileLock`, the possibility that another process acquired the lock in the gap between releasing the lock and restoring must be handled.

## 1. Why manage file locks and watchers in CRaC?

A checkpoint saves process state, including Java state and recoverable runtime state. However, resources tied to the operating system or objects outside the process have their own lifecycle. A file descriptor, an operating system lock, or a directory watch registration cannot be treated as a pure Java object.

Two common groups of resources:

| Resource | Java Component | What to do before checkpoint | What to do after restore |
|---|---|---|---|
| File lock | `FileChannel`, `FileLock` | Stop operations using the file, release the lock, and close the channel | Reopen the channel, attempt to acquire the lock, and confirm ownership |
| Directory watching | `WatchService`, `WatchKey` | Stop the event processing thread, close the watcher, and discard old keys | Create a new watcher, re-register directories, and scan to reconcile state |

Merely holding a Java reference to `FileLock` or `WatchService` on the heap does not guarantee that the underlying native handle is still usable. Treat the checkpoint as a lifecycle boundary: release resources before taking the snapshot and recreate resources after restoring.

## 2. Managing file locks with `FileChannel` and `FileLock`

Java NIO provides `FileChannel` to read, write, and lock a region of a file. Call `FileChannel.lock()` to request a lock that may block, or `tryLock()` to attempt to acquire the lock immediately. When the lock is acquired, the application receives a `FileLock` and can check its status with `isValid()`.

Basic example:

```java
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path lockPath = Path.of("/var/lib/myapp/state.lock");

try (FileChannel channel = FileChannel.open(
        lockPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {

    try (FileLock lock = channel.tryLock()) {
        if (lock == null) {
            throw new IllegalStateException("Another process owns the lock");
        }

        // Perform the work that requires lock ownership.
    }
}
```

`tryLock()` can return `null` if the lock cannot be acquired because another process is holding it. If the same JVM already holds an overlapping lock on that file region, the API may throw `OverlappingFileLockException`. `lock()` can wait until the lock is acquired; therefore, using a blocking method in an after-restore callback should be carefully considered.

### 2.1. Characteristics of file locks to remember

- A lock is tied to the channel and the locked byte region. Closing the channel releases the associated locks.
- Locks can be exclusive or shared, depending on how the channel is opened and filesystem support.
- How the operating system enforces locks can differ across platforms; some systems use advisory locks. All processes accessing the file must follow the same locking protocol.
- `FileLock` is not a distributed lock and does not replace coordination mechanisms across machines or filesystems with different semantics.
- After the channel is closed or the lock is released, the old `FileLock` object cannot be used as proof that the process still owns the lock.

In particular, releasing the lock before checkpoint creates a window of time during which another process can acquire the lock. After restore, the application must attempt to acquire the lock again and handle the case where the lock already belongs to another process. If business logic requires continuous ownership throughout the checkpoint duration, a file lock cannot guarantee that requirement on its own; an external lease or coordination mechanism with a fencing token or equivalent protocol is needed.

### 2.2. Closing and reacquiring locks according to the CRaC lifecycle

A resource can manage the channel and lock. In `beforeCheckpoint`, the resource releases the lock and closes the channel. In `afterRestore`, the resource reopens the file and attempts to acquire a new lock.

```java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileLockResource implements Resource {
    private final Path lockPath;
    private FileChannel channel;
    private FileLock lock;

    public FileLockResource(Path lockPath) throws IOException {
        this.lockPath = lockPath.toAbsolutePath().normalize();
        openAndAcquire();
        Core.getGlobalContext().register(this);
    }

    private synchronized void openAndAcquire() throws IOException {
        channel = FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE);
        try {
            lock = channel.tryLock();
            if (lock == null) {
                throw new IOException("File lock is already held: " + lockPath);
            }
        } catch (IOException | RuntimeException e) {
            try {
                channel.close();
            } catch (IOException closeFailure) {
                e.addSuppressed(closeFailure);
            }
            channel = null;
            lock = null;
            throw e;
        }
    }

    private synchronized void releaseAndClose() throws IOException {
        IOException failure = null;

        if (lock != null) {
            try {
                if (lock.isValid()) {
                    lock.release();
                }
            } catch (IOException e) {
                failure = e;
            }
            lock = null;
        }

        if (channel != null) {
            try {
                channel.close();
            } catch (IOException e) {
                if (failure == null) {
                    failure = e;
                } else {
                    failure.addSuppressed(e);
                }
            }
            channel = null;
        }

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        releaseAndClose();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        openAndAcquire();
    }
}
```

This is an illustrative example for an exclusive lock on a dedicated lock file. In a real application, synchronization with business threads using the resource, retry policies, and logging must be added. If the lock cannot be reacquired in `afterRestore`, the callback must report an error so the application does not continue processing as if it still owned the lock.

### 2.3. Choosing a reacquire strategy

After restore, another process may have already acquired the lock. Choose a policy according to business requirements:

- **Mandatory lock:** if the application is only allowed to run when holding the lock, `afterRestore` must fail when the lock cannot be acquired. Readiness must not be enabled.
- **Waitable lock:** `lock()` or a retry loop with a deadline can be used, but it must have a time limit and support cancellation when deployment stops.
- **Contended lock:** use `tryLock()` and transition the application to a waiting or standby state when the lock is not yet available.
- **Continuous ownership required:** use a lease service or external coordination mechanism; do not rely on holding `FileLock` across a checkpoint.

Do not retry infinitely in a callback. A hung callback can prevent the process from reaching a completed restore state. Explicitly specify timeouts, retry counts, and failure behavior.

### 2.4. Keeping the lock file stable

Use a lock file with a stable path and do not delete or replace the file while processes may be using it. On some filesystems, deleting and recreating a lock file can create a different file object while an existing process still holds a reference to the old object. In that case, two processes may think they are locking the same path name while actually locking two different objects.

Separate the file used as a lock from data files if possible. The lock file is only used for coordination; business data is written through a separate protocol with atomic writes, synchronization, and error recovery.

## 3. Monitoring changes with `WatchService`

`WatchService` belongs to Java NIO.2 and provides a mechanism to receive notifications about filesystem events. An application creates a watcher with `FileSystem.newWatchService()`, registers a directory with the event types to monitor, and reads events via `WatchKey`.

```java
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.StandardWatchEventKinds;
import java.nio.file.WatchService;

Path directory = Path.of("/var/lib/myapp/inbox");

try (WatchService watcher = FileSystems.getDefault().newWatchService()) {
    directory.register(
            watcher,
            StandardWatchEventKinds.ENTRY_CREATE,
            StandardWatchEventKinds.ENTRY_MODIFY,
            StandardWatchEventKinds.ENTRY_DELETE);

    // Read WatchKey from watcher and process events.
}
```

`WatchService` only monitors registered directories. Registering a directory does not automatically register all subdirectories. If a directory tree needs to be monitored, the application must traverse the tree and register each directory, as well as register new subdirectories when they are detected as created.

### 3.1. Handling WatchKey and WatchEvent

A typical watch loop calls `take()` to wait for a key to become ready, reads the events, and then calls `reset()` to continue receiving events:

```java
import java.nio.file.ClosedWatchServiceException;
import java.nio.file.Path;
import java.nio.file.WatchEvent;
import java.nio.file.WatchKey;
import java.nio.file.WatchService;

static void processEvents(WatchService watcher) {
    while (true) {
        final WatchKey key;
        try {
            key = watcher.take();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        } catch (ClosedWatchServiceException closed) {
            return;
        }

        for (WatchEvent<?> event : key.pollEvents()) {
            if (event.kind() == java.nio.file.StandardWatchEventKinds.OVERFLOW) {
                // Must rescan the directory to reconcile state.
                continue;
            }

            Path changedName = (Path) event.context();
            // Combine changedName with the corresponding registered directory and process.
        }

        if (!key.reset()) {
            // The directory is no longer watched via this key.
            break;
        }
    }
}
```

In a real application, each `WatchKey` must be mapped to its registered directory to resolve `event.context()` into a full path. If `reset()` returns `false`, the key has become invalid; remove the key from the registry and decide whether the directory needs to be re-registered if it still exists.

`OVERFLOW` means some events may have been lost. Do not treat the event queue as a complete log. Rescan the directory state or the original data source to synchronize.

## 4. Stopping and restarting WatchService across a checkpoint

A watcher typically has a background thread blocked in `WatchService.take()`. Before checkpoint, it is necessary to stop accepting new work, close the watcher to wake up the waiting thread, wait for the thread to finish, and clear the old key registry. After restore, create a new `WatchService`, re-register the directories, start a new thread, and reconcile the contents.

A resource managing a watcher can have a structure like the following:

```java
import java.io.IOException;
import java.nio.file.FileSystems;
import java.nio.file.Path;
import java.nio.file.WatchService;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DirectoryWatchResource implements Resource {
    private final Path root;
    private final ConcurrentMap<java.nio.file.WatchKey, Path> directories =
            new ConcurrentHashMap<>();

    private volatile WatchService watcher;
    private volatile Thread worker;
    private volatile boolean stopping;

    public DirectoryWatchResource(Path root) throws IOException {
        this.root = root.toAbsolutePath().normalize();
        startWatching();
        Core.getGlobalContext().register(this);
    }

    private synchronized void startWatching() throws IOException {
        WatchService newWatcher = FileSystems.getDefault().newWatchService();
        try {
            registerTree(root, newWatcher);
        } catch (IOException e) {
            try {
                newWatcher.close();
            } catch (IOException closeFailure) {
                e.addSuppressed(closeFailure);
            }
            directories.clear();
            throw e;
        }

        stopping = false;
        watcher = newWatcher;
        Thread newWorker = new Thread(
                () -> processEvents(newWatcher), "directory-watch-worker");
        newWorker.setDaemon(true);
        worker = newWorker;
        newWorker.start();
    }

    private void registerTree(Path directory, WatchService target)
            throws IOException {
        // Traverse root and subdirectories, registering each directory with target.
        // Store each WatchKey along with its directory path in directories.
    }

    private void processEvents(WatchService source) {
        // Read key, process events, reset key, and handle OVERFLOW.
        // Exit when source is closed or the thread is interrupted.
    }

    private void reconcileTree() throws IOException {
        // Rescan the directory tree and synchronize application state with actual data.
    }

    private void stopWatching() throws Exception {
        WatchService oldWatcher;
        Thread oldWorker;
        synchronized (this) {
            stopping = true;
            oldWatcher = watcher;
            watcher = null;
            oldWorker = worker;
            worker = null;
        }

        IOException closeFailure = null;
        if (oldWatcher != null) {
            try {
                oldWatcher.close();
            } catch (IOException e) {
                closeFailure = e;
            }
        }
        if (oldWorker != null) {
            oldWorker.interrupt();
            try {
                oldWorker.join(5_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                if (closeFailure != null) {
                    e.addSuppressed(closeFailure);
                }
                throw e;
            }
            if (oldWorker.isAlive()) {
                IllegalStateException e = new IllegalStateException(
                        "Directory watcher did not stop before checkpoint");
                if (closeFailure != null) {
                    e.addSuppressed(closeFailure);
                }
                throw e;
            }
        }
        directories.clear();
        if (closeFailure != null) {
            throw closeFailure;
        }
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        stopWatching();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        startWatching();
        reconcileTree();
    }
}
```

The `registerTree`, `processEvents`, and `reconcileTree` methods are left as extension points because the logic depends on the directory structure and business requirements. When implementing, `registerTree` must register `ENTRY_CREATE`, `ENTRY_MODIFY`, and `ENTRY_DELETE` for each directory to be watched; `processEvents` must handle `OVERFLOW`, invalidated keys, and the creation of new subdirectories.

When `WatchService` is closed, a thread waiting in `take()` will be woken up with `ClosedWatchServiceException`. The processing thread should treat this as a normal stop signal during checkpoint. Calling `join()` ensures the thread is no longer processing events before the JVM captures the state. If an event handler can block for a long time, set a deadline for stopping and fail the checkpoint if the worker does not stop safely.

## 5. Events may be lost during the checkpoint window

`WatchService` is not a message broker and does not guarantee storing all events while the watcher is closed. In the interval from `beforeCheckpoint` to `afterRestore`, files may be created, modified, or deleted. After re-registering, the new watcher will not necessarily replay the changes that occurred during that gap.

Therefore, the recovery process must be based on the current state of the filesystem:

1. Close the watcher and stop the event worker before checkpoint.
2. After restore, create a new watcher and re-register existing directories.
3. Scan the directory tree or read metadata from the original data source to determine the current state.
4. Compare with the application state held in the heap and apply missing changes.
5. Process new events idempotently so that events occurring during the scan do not cause duplicate updates that corrupt data.

The watcher should be registered before running the reconciliation scan. That way, changes occurring during the scan have a chance to be placed into the event queue; the application must still design synchronization operations to be idempotent because an event may be duplicated or overflowed.

For large workloads, instead of keeping a full state copy in the heap, metadata snapshots, versions, timestamps, or business cursors can be used to determine the scope that needs reconciliation. The exact mechanism depends on the data source and application semantics.

## 6. Watching directory trees and handling new directories

`WatchService` registers on a per-directory basis. If recursive watching is needed:

- Traverse the initial directory tree and register each directory.
- When receiving `ENTRY_CREATE` and the new entry is a directory, register the new directory along with any subdirectories that already exist inside it.
- When receiving `ENTRY_DELETE`, remove the corresponding keys from the registry if they are no longer valid.
- When `WatchKey.reset()` returns `false`, remove that key from the map and check whether the directory still exists.
- After restore, rebuild the entire registry from the current filesystem; do not reuse old `WatchKey` instances.

A race condition can occur when a directory is created and already contains files before the application registers a watcher for the new directory. Therefore, after registering a new directory, scan that directory to discover existing contents. Similarly, if the provider reports `OVERFLOW`, schedule a rescan instead of trying to infer state solely from the remaining events.

## 7. Coordinating multiple file resources

An application may simultaneously hold a file lock, watch a directory, and run a worker that processes files. These components have dependencies:

- The file processing worker needs the watcher to receive work signals.
- The worker may need the file lock before updating shared state.
- The watcher needs the filesystem to be ready before registering.
- Readiness must only be enabled after the watcher has re-registered, state has been reconciled, and mandatory locks have been acquired.

Order resources by dependency direction when registering with the CRaC context: foundational components before consumers. According to the global context callback rules, `beforeCheckpoint` runs in reverse registration order, while `afterRestore` runs in registration order. For example, register the lock and watcher before the worker; on checkpoint the worker stops first, and on restore the lock and watcher are restored before the worker resumes.

Do not let the worker continue processing files while the watcher or lock is in a closed state. A shared readiness gate or state machine can be used to transition the application through states `RUNNING`, `QUIESCING`, `CHECKPOINT_READY`, and `RESTORING`. Every file write operation must check the state and coordinate with the lifecycle owner.

## 8. Common errors

| Symptom | Possible Cause | How to Resolve |
|---|---|---|
| Old `FileLock` is no longer valid | Channel was closed or lock was released before checkpoint | Open a new channel and acquire a new lock in `afterRestore` |
| Unable to reacquire lock | Another process acquired the lock during the checkpoint window | Perform bounded retries or switch to standby/fail restore |
| Two processes write to the file simultaneously | Processes do not use the same locking protocol or replaced the lock file | Use a stable lock file and agree on a locking protocol |
| Watcher does not receive events after restore | Old `WatchService` was closed or old keys are no longer valid | Create a new watcher and re-register all directories |
| Missing changes that occurred during checkpoint | No watcher was active during that window | Scan and reconcile the filesystem after restore |
| Watcher stopped but thread is still running | Event handler is blocked or does not exit when service closes | Close service, interrupt, join with a deadline, and fail checkpoint if it does not stop |
| Missing new subdirectories | Only the root directory was registered | Register recursively and register additional directories on create events |
| Processing a file twice | Duplicate events or both rescan and new events received | Design idempotent processing and reconcile by version |

Another design mistake is reopening the watcher in the application's constructor after restore. Restore does not re-run `main()` like a fresh startup, so resource recovery logic must reside in the `afterRestore` callback or a lifecycle invoked by CRaC, not only in the initial startup path.

## 9. Testing checkpoint–restore for filesystem resources

Both normal behavior and contention scenarios should be tested:

1. Start the application, confirm the lock is acquired and the watcher has registered the required directories.
2. Log when the resource receives `beforeCheckpoint`; confirm the worker has stopped, the lock is released, the channel is closed, and the watcher is closed.
3. Create a checkpoint using the target CRaC runtime.
4. During the checkpoint window, try creating, modifying, and deleting files from another process to simulate external changes.
5. Restore the application; confirm a new channel is opened, the lock is reacquired according to policy, a new watcher is created, and directories are re-registered.
6. Confirm the reconcile step detects the changes made while the watcher was inactive.
7. Send new events after restore and verify the worker processes them idempotently.
8. Run a scenario where another process holds the lock during restore to confirm the application does not assume the lock is always available.
9. Repeat multiple checkpoint/restore cycles to detect duplicated watcher threads, stale keys remaining in the registry, or leaked channels.

When measuring performance, separate JVM restore time, lock reacquisition time, watcher registration time, reconciliation scan time, and time to reach readiness. Separating these milestones helps identify which step dominates application readiness time.

## 10. Implementation checklist

- [ ] Each `FileChannel` and `FileLock` is managed by an explicit CRaC resource.
- [ ] `beforeCheckpoint` stops operations using the file, releases the lock, and closes the channel.
- [ ] `afterRestore` opens a new channel and acquires a new lock according to the timeout/retry policy.
- [ ] The application handles the case where another process acquired the lock during the checkpoint window.
- [ ] The lock file has a stable path and is not deleted or replaced while in use.
- [ ] The watcher is closed and the worker thread has terminated before checkpoint.
- [ ] `afterRestore` creates a new `WatchService` and re-registers directories.
- [ ] Old `WatchKey` instances are discarded; no keys from before checkpoint are reused.
- [ ] `OVERFLOW`, invalid keys, and new subdirectories are handled.
- [ ] A rescan/reconcile step exists to make up for events that occurred while the watcher was closed.
- [ ] Event handlers are idempotent and do not process concurrently in a way that corrupts state.
- [ ] Readiness is only enabled after the lock, watcher, and data are ready.
- [ ] Restore has been tested under lock contention from another process and with filesystem changes.

## 11. References

- [Java NIO `FileLock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): state, lock region, shared/exclusive locks, and platform-dependent behavior.
- [Java NIO `FileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): opening channels, `lock()`, `tryLock()`, and channel lifecycle.
- [Java NIO `WatchService`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchService.html): creating watchers, `take()`, and closing the service.
- [Java NIO `WatchKey`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/WatchKey.html): event queue, `reset()`, and key state.
- [CRaC API — `Resource`](https://javadoc.io/doc/org.crac/crac/latest/org/crac/Resource.html): callbacks before checkpoint and after restore.

File locks and `WatchService` are both tied to filesystem resources with their own lifecycles. In CRaC, release file locks and close channels before checkpoint, then reopen and confirm ownership after restore. For watchers, stop the worker, close the service, create a new watcher, and re-register directories after restore. Because events can be lost while the watcher is inactive, always reconcile filesystem state before allowing workers to resume processing.
# Log Files, Log Rotation, and Reopening Write Destinations

Java applications often write logs to files to record activity, errors, and operational information. While the application is running, a logger or appender may hold a file descriptor and continue writing through the same file object. When CRaC creates a checkpoint, the process pauses; during that time, the operating system or operations environment can still rotate logs, rename files, create new files, change symlinks, or remount volumes.

Therefore, after restore, a file descriptor held in the heap or restored at the process level may no longer point to the current active log file. On Unix systems, when an open file is renamed, the old file descriptor still references the old inode. Subsequent writes may continue going into the renamed file, while the application's configured path already points to the new file. If the application needs to write to the current destination, it must close the old handle and reopen the path after restore.

In CRaC, this is usually organized using resource callbacks: flush and close the write destination before checkpoint, then reopen the write destination after restore. The exact approach depends on the logger being used, the operating system, the filesystem type, and how the deployment environment manages logs.

## 1. Why Do Log Files Need to Be Managed Across Checkpoints?

When an application opens a file for writing, the operating system allocates a file descriptor (on Windows, this is typically represented through a handle). Java may hold objects such as FileOutputStream, FileWriter, BufferedWriter, FileChannel, or a logging framework's appender. This Java object usually holds a reference to the corresponding operating system resource.

A path and a file descriptor are two different concepts:

- A path such as /var/log/orders/app.log is the name resolved by the filesystem when the application opens the file.
- A file descriptor is a reference to an already opened file. It does not automatically switch to a different file just because a process renames or recreates the original path.
- An inode on a Unix filesystem represents the file object. Multiple paths may sequentially reference different inodes over time.
- Buffers in Java or the logging framework may hold data that has not yet been written to the filesystem. Only proper closing or flushing helps push that data out according to the API contract.

For example, the application opens /var/log/orders/app.log. Later, logrotate renames this file to app.log.1 and creates a new app.log. The old file descriptor still points to the renamed file object. If the application continues writing using the old descriptor, new content may appear in app.log.1 instead of app.log.

This can happen if log rotation occurs while the application is checkpointed and the application restores with the old handle. The JVM may continue running, the logger may still work, and write operations may not report errors, but the logs have gone into a file that is no longer the current write destination.

Therefore, restoring the process does not mean the logging framework automatically reopens the path. The application needs an explicit lifecycle policy for file-based write destinations.

## 2. What Happens When Logs Are Rotated?

Log rotation limits the size or lifetime of a log file. When a threshold is reached, the system renames the current file, compresses or archives it, and creates a new file to receive subsequent logs.

There are two common ways rotation occurs while an application is writing.

### 2.1. Rename and create

In this approach, the rotation tool renames the file being written to, then creates a new file at the original path.

For example:

~~~text
Before rotate:
  /var/log/orders/app.log       -> inode A (opened by the application)

After rotate:
  /var/log/orders/app.log.1     -> inode A
  /var/log/orders/app.log       -> inode B (new file)
~~~

The application's file descriptor still references inode A. Renaming the path does not automatically change the object the descriptor points to. To write to inode B, the application must close the old descriptor and reopen /var/log/orders/app.log.

This is why many logging frameworks support a reopen operation or accept a signal to close and reopen files. With CRaC, this can be coordinated by closing the file in the before-checkpoint callback and reopening the current path in the after-restore callback. If rotation happens while the JVM is stopped, reopening after restore will resolve the path to the new file.

### 2.2. Copy and truncate

Some logrotate configurations copy the contents of the current file to an archive file and then truncate the original file without changing the inode. This is commonly called copytruncate.

~~~text
Before rotate:
  /var/log/orders/app.log       -> inode A (opened by the application)

After copytruncate:
  /var/log/orders/app.log.1     -> copy of contents at the time of copy
  /var/log/orders/app.log       -> inode A truncated
~~~

Because the inode does not change, the open file descriptor can still write to app.log after truncation. However, copytruncate has a race window: logs written between the copy and truncate operations may be lost or appear unexpectedly in the archive. Truncation also does not automatically synchronize buffers at all layers.

If the application proactively closes the file before checkpoint and reopens it after restore, it can still work with the current path. However, copytruncate does not solve the problem of lost log data in the copy/truncate window while the application is still writing. When high reliability is required, you should choose a rotation strategy with explicit reopen coordination or use a rolling mechanism managed by the logging framework.

### 2.3. Rotation while the application is stopped

One benefit of closing the write destination before checkpoint is that the rotation tool can rename, compress, and create a new file while the JVM is stopped without any application descriptor holding the old file open. After restore, the callback that reopens the active path will point to the current file.

Illustrative sequence:

~~~text
Application running
    |
    v
beforeCheckpoint(): flush and close app.log
    |
    v
CRaC creates checkpoint; JVM stops
    |
    v
Log rotation: archive old app.log, create new app.log
    |
    v
CRaC restore
    |
    v
afterRestore(): reopen the app.log path
    |
    v
Application writes to the current log file
~~~

If the system does not rotate logs while the application is stopped, the after-restore callback can still reopen the same path. Opening it fresh helps the application start with a new handle and verify the write destination at restore time.

## 3. Role of CRaC Callbacks

A resource managing a log file can implement the org.crac.Resource interface and register with the global context. The two callbacks have different responsibilities:

- beforeCheckpoint(): stop or drain write threads, flush remaining buffered data, and close the writer or appender holding the file descriptor.
- afterRestore(): re-read path configuration if needed, create directories if needed, reopen the file at the current path, and only allow log writing once the write destination is ready.

Registration example:

~~~java
Core.getGlobalContext().register(logFileResource);
~~~

Registration only enables the runtime to invoke the callbacks. It does not automatically detect logrotate, automatically close every FileOutputStream in the application, or automatically choose a new path. The resource must manage the exact object that owns the writer or appender.

For applications with multiple log files, it is necessary to clearly identify which logger owns each appender, which appenders are shared, and which component has the authority to close or reopen them. Avoid having two resources close the same writer or having a resource close an appender while the logging framework continues sending events to it.

## 4. Example: Managing a Log File with Resource

The example below illustrates a simple writer that writes to a fixed path. The resource closes the writer before checkpoint and reopens the same path after restore. The path is converted to an absolute path upon initialization to avoid depending on a working directory that may change when the application runtime environment is recreated.

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class LogFileResource implements Resource {
    private final Path logPath;
    private BufferedWriter writer;

    public LogFileResource(Path configuredPath) throws IOException {
        this.logPath = configuredPath.toAbsolutePath().normalize();
        openWriter();
        Core.getGlobalContext().register(this);
    }

    public synchronized void writeLine(String message)
            throws IOException {
        if (writer == null) {
            throw new IllegalStateException(
                    "Log writer is not available");
        }

        writer.write(message);
        writer.newLine();
    }

    public synchronized void flush() throws IOException {
        if (writer != null) {
            writer.flush();
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        closeWriter();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws IOException {
        openWriter();
    }

    private void openWriter() throws IOException {
        Path parent = logPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        writer = Files.newBufferedWriter(
                logPath,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND
        );
    }

    private void closeWriter() throws IOException {
        BufferedWriter current = writer;
        writer = null;

        if (current != null) {
            current.flush();
            current.close();
        }
    }
}
~~~

Initialize the resource during the bootstrap phase:

~~~java
Path logPath = Path.of("/var/log/orders/app.log");
LogFileResource logResource = new LogFileResource(logPath);
~~~

At checkpoint:

1. The application stops accepting new operations that need to write logs or waits for current operations to complete.
2. beforeCheckpoint() takes the current writer, sets the writer field to null, flushes, and closes the writer.
3. After checkpoint, the process no longer holds an open writer for this log file.

At restore:

1. afterRestore() calls openWriter().
2. Files.newBufferedWriter() resolves the current path and opens the file in APPEND mode.
3. If rotation has renamed the old file and created a new file, the new writer writes to the new file at the active path.

This is an example illustrating the mechanism, not a full logging framework. The writeLine() method and callbacks are synchronized to prevent closing the writer while a write through this same object is in progress. However, the application still must stop or drain threads sending logs before checkpoint. If a thread calls writeLine() after the writer has closed, the method will throw an error for the application to handle explicitly.

In a production environment, you should not use a custom-built writer instead of a logging framework if the application needs log levels, structured logging, async queues, MDC, rolling policies, or multiple appenders. Apply the same lifecycle principles to the actual appender through the APIs supported by the framework.

## 5. Integrating with Logging Frameworks

Frameworks such as java.util.logging, Logback, and Log4j2 manage handlers or appenders on behalf of the application. The file write destination may be held inside a framework object, so merely closing a different FileOutputStream will not affect the appender that is writing logs.

When integrating CRaC, determine:

- Which object owns the file appender or handler?
- Are there any buffers or asynchronous queues that need to be drained?
- Does the framework have an official API to flush, stop, close, reopen, or reconfigure the appender?
- After reopening, does the appender use the correct active path and preserve the formatter, filter, encoder, level, and rollover configuration?
- Does the framework or version in use have built-in CRaC support or a suitable integration module?

Do not arbitrarily close the file descriptor underlying the framework while the appender is still active. The framework may continue holding a reference to the closed writer, causing logs to fail or be dropped. Also do not initialize additional new appenders after each restore while forgetting to remove the old appender, as that can cause each event to be logged multiple times.

A resource integrating with a framework typically performs the following conceptual tasks:

~~~java
public void beforeCheckpoint(Context<? extends Resource> context) {
    stopAcceptingLogEvents();
    drainAsyncLoggingQueue();
    flushAndCloseFileAppenders();
}

public void afterRestore(Context<? extends Resource> context) {
    reopenOrReconfigureFileAppenders();
    verifyActiveLogTargets();
    resumeLogEvents();
}
~~~

This is pseudocode describing the sequence, not a built-in API of a specific framework. Method names and lifecycle management must follow the documentation of the framework version the application uses. If the framework has an official CRaC integration, prefer that integration instead of manually controlling the appender internals.

### 5.1. Asynchronous logging

Some loggers write logs through a queue and a worker thread. When the application prepares to checkpoint, closing the appender immediately can lose events still in the queue or cause the worker thread to access a closed writer.

Required sequence:

1. Stop accepting new log events from business threads in a manner appropriate for the application.
2. Ask the logging framework to drain the asynchronous queue.
3. Wait for the worker to finish writing within a time limit.
4. Flush and close the appender.
5. After restore, reopen the appender and restart the worker or logging context according to the framework's instructions.

If the queue cannot be drained within the timeout, define a clear policy: wait longer, fail the checkpoint, or accept dropping some logs according to operational requirements. Do not silently ignore errors because logs may be necessary data for incident investigation.

### 5.2. Multiple appenders and multiple destinations

A logger may send events to the console, file, socket, or a centralized service simultaneously. The resource only needs to close the write destinations that the application owns and needs to recreate. For example, a file appender may need to be closed and reopened, while a console appender remains managed by the container runtime.

If multiple loggers share an appender, only one component should own that appender's lifecycle. Registering a resource for each logger and having them all close the same appender can cause duplicate callbacks and ordering errors.

## 6. Log Paths and Storage Locations

Reopening a file is only meaningful if the path after restore points to the right filesystem and the intended destination.

### 6.1. Absolute paths and working directory

Relative paths are resolved based on the process's working directory. If the restore environment uses a different working directory, the same path string may point to a different location. For important write destinations, store absolute paths or construct paths from explicit configuration.

Do not merely store a Path object and assume the underlying filesystem remains the same. After restore, a volume may be remounted or the path configuration may change. If the write destination can change per environment, re-read the configuration from an appropriate source in the after-restore callback.

### 6.2. Persistent volumes and containers

In containers, the filesystem of the ephemeral writable layer may be replaced when the container is recreated. A persistent volume can preserve data across container recreations, but the mount point, permissions, and volume state still need to be verified.

Before reopening logs after restore, the application must ensure:

- The target directory exists or can be created.
- The volume is mounted at the expected location.
- The account running the JVM has write permission.
- The write destination has sufficient disk space and is not in read-only state.
- The path does not accidentally point to an ephemeral filesystem when long-term log storage is required.

If the volume is not ready, the restore callback should report an error or leave the application in an unready state. Do not automatically switch to another directory without an explicit policy, because logs may become scattered or lost from where operations monitors them.

### 6.3. Symlinks as write destinations

Some systems use a symlink such as current.log to point to the active file. When rotation changes the symlink, an already open descriptor still points to the file object it opened earlier. Reopening the symlink path after restore resolves the link at open time and can reach the new file.

Check permissions, the symlink target, and the rotation policy. Do not keep an old file descriptor and expect it to automatically follow the new symlink.

## 7. Writing Logs to stdout and stderr in Containers

Not every Java application should manage log files directly. In Kubernetes and many container platforms, applications typically write logs to stdout or stderr. The container runtime or log collection agent receives these streams and forwards, stores, and rotates them according to platform configuration.

With that model:

- The application does not close System.out or System.err in beforeCheckpoint().
- The application should flush the streams if appropriate for how the logging framework manages the console appender.
- Do not open a separate app.log file just to replace the stdout stream provided by the container runtime.
- Rotation and retention are usually managed by the platform or log collector.
- After restore, check how the runtime and deployment environment re-provide standard streams; do not assume an external pipe or sink has the same lifecycle as a regular file.

If the framework writes to the console through an appender, check how the framework flushes and handles callbacks. Managing stdout/stderr differs from closing and reopening a file by path. Do not close standard streams just to mimic the lifecycle of a file appender.

## 8. Common Errors When Restoring Write Destinations

| Scenario | Cause | Handling |
|---|---|---|
| Logs continue appearing in app.log.1 | Old descriptor still references the renamed inode | Close the descriptor before checkpoint and reopen the active path after restore |
| No logs appear after restore | Writer was closed but appender was not recreated | Restore the appender using the logging framework's API |
| Each log line appears twice | Resource created a new appender while the old appender remained registered | Manage a single owner and remove the old appender properly |
| Last logs before checkpoint are lost | Buffer or async queue was not drained | Drain the queue, flush, and wait for writes to complete |
| After-restore callback reports permission error | Volume, owner, or permissions changed | Verify mount and write permissions before opening the file |
| Logs written to an unexpected directory | Relative path resolved from a different working directory | Use absolute paths or re-read configuration |
| New log file is not created | Directory does not exist or filesystem is read-only | Create the directory in a controlled manner and check filesystem state |
| Logs missing around copytruncate time | Rotation has a race window between copy and truncate | Use a rotation strategy with explicit reopen or an appropriate rolling appender |
| Async logger loses events | Queue was not drained when appender was closed | Stop accepting new logs, drain the queue, then close the appender |

## 9. Recommended Operational Workflow

An applicable workflow for file appenders is as follows.

### Before checkpoint

1. Transition the application to a quiescing state to stop accepting new work if needed for log consistency.
2. Drain requests or tasks currently writing logs according to the application's policy.
3. Drain the async logger's queue and wait for the worker to finish within the defined timeout.
4. Flush appenders and writers writing to files.
5. Close file write destinations and release handles.
6. Confirm that the resource is in a state ready for checkpoint.

### While the JVM is stopped

The operations system may rotate logs, rename files, create new files, compress old files, or change mounts. The rotation process must be aware that the application has closed the file and is no longer writing to the old destination. If another rotation tool also manages the same file, ensure there are no two competing rotation mechanisms.

### After restore

1. Re-read write destination configuration if paths or mounts may change.
2. Verify directories, volumes, write permissions, and disk space.
3. Reopen the active path instead of reusing the old descriptor.
4. Restore the logging framework's appender, formatter, filter, and rolling policy.
5. Restart the async logger's worker and allow accepting new events.
6. Verify that new logs appear at the expected write destination before opening readiness if logging is a mandatory operational dependency.

Overall flow:

~~~mermaid
flowchart TD
    A[Application writes logs] --> B[Stop or drain write threads]
    B --> C[Drain async queue and flush]
    C --> D[Close file appender or writer]
    D --> E[CRaC checkpoint]
    E --> F[Log rotation while JVM is stopped]
    F --> G[CRaC restore]
    G --> H[Verify mount, path, and permissions]
    H --> I[Reopen current write destination]
    I --> J[Start logger and worker]
    J --> K[Resume logging]
~~~

Not every application needs to stop all business processing just to close log files. If the logging framework supports a safe appender close/open process while traffic is still flowing, that mechanism can be used. However, ensure no thread writes to a closed appender and have a clear policy for log events generated while the appender is temporarily paused.

## 10. Testing Log Rotation with CRaC

Testing should simulate file changes while the JVM is stopped, rather than just confirming that callbacks were invoked.

A basic scenario:

1. Start the application and write some identifiable log lines.
2. Create a checkpoint so the callback closes the file appender.
3. While the JVM is stopped, rename the current file to app.log.1 and create a new app.log.
4. Restore the application.
5. Write another log line with different identifiable content.
6. Verify that the new line is in app.log, while the pre-rotation lines are in the archive file according to policy.

Other cases to test:

- Rotation does not occur during the checkpoint period.
- Rotation occurs multiple times while the JVM is stopped.
- The log directory has its symlink changed.
- The persistent volume is remounted.
- Write permissions are changed or the filesystem becomes read-only.
- An appender using a buffer or async queue still has events when checkpoint begins.
- The callback to reopen the file fails because the directory is not ready.
- The application has multiple appenders, of which only some write to files.
- Multiple replicas restore from the same checkpoint and write to separate log files.

Check both the content and the write destination. An application may report no errors while still writing to the renamed file. Check the inode or actual path on supported platforms, the file modification time, line counts, and the location of marker lines before/after restore.

## 11. Choosing an Appropriate Logging Strategy

| Model | How rotation is managed | CRaC work to consider |
|---|---|---|
| Application writes directly to file | Application or external tool renames and creates files | Close writer before checkpoint, reopen active path after restore |
| Logging framework with rolling appender | Framework manages rotation by size or time | Use lifecycle API or CRaC integration supported by the framework |
| File appender combined with logrotate | Operating system tool rotates files | Coordinate close/reopen; avoid continuing to write to old descriptor |
| Console logging in containers | Runtime or log collector manages storage and rotation | Flush per framework mechanism; do not close stdout/stderr |
| Logs sent to a centralized service | Client sends via socket or HTTP | Close or pause client appropriately, recreate connection and authentication after restore |

For systems requiring simple operations in containers, writing structured logs to stdout/stderr often helps separate storage responsibilities from the application. For applications that need to write files directly, design a resource to manage the appender and coordinate with the rotation tool.

## 12. Key Principles to Remember

- A file descriptor references an opened file; renaming the path does not automatically switch the descriptor to a new file.
- Log rotation can happen while the JVM is checkpointed and stopped.
- Before checkpoint, drain write threads, flush buffers, and close appenders or writers that own files.
- After restore, reopen the active path to resolve the current write destination.
- For async loggers, handle the queue and worker before closing the appender.
- For logging frameworks, use supported lifecycle APIs and avoid creating duplicate appenders.
- For stdout/stderr in containers, let the runtime and log collector manage stream lifecycles and rotation.
- Verify the filesystem, volume, permissions, and path before allowing the application to resume writing.

CRaC preserves process state to reduce startup time, but it does not automatically keep log paths and file descriptors synchronized with external changes. Properly managing the log file lifecycle requires the application to prepare write destinations before checkpoint, reopen current paths after restore, and test against the actual rotation policy of the deployment environment.

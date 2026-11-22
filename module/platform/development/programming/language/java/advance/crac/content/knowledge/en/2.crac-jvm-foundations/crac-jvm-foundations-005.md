# File Descriptors and Operating-System-Managed Resources

A running JVM does not hold state only in the heap. It also uses resources provided by the kernel and operating environment: open files, sockets, pipes, file locks, timers, devices, database connections, and various other native handles. This is a part that requires careful handling when using **CRaC (Coordinated Restore at Checkpoint)**.

CRaC captures the state of an already started Java process and restores the process from the checkpoint image. After restore, the program resumes from the captured state. However, certain resources external to the process cannot be treated like ordinary Java data. Some handles cannot be safely saved by the checkpoint engine; others may point to an environment that has changed. Therefore, the application must proactively release them before checkpoint and recreate them after restore.

This article focuses on understanding file descriptors, identifying operating system resources that can affect CRaC, and organizing their lifecycles using the Resource API.

## 1. What Is a File Descriptor?

On Unix and Linux, a **file descriptor (FD)** is a non-negative integer that a process uses to reference a kernel-managed I/O object. An FD is typically created when a program opens a file, creates a socket, creates a pipe, or invokes a system call requiring an I/O handle.

In Java, developers typically work with higher-level classes such as:

- **FileInputStream**, **FileOutputStream**, **RandomAccessFile**.
- **FileChannel** and classes in Java NIO.
- **Socket**, **ServerSocket**, **DatagramSocket**.
- **SocketChannel**, **ServerSocketChannel**, **Pipe**.
- JDBC, HTTP, or native libraries that may create handles underneath.

These Java classes hide most FD details. A **FileInputStream** can hold a **FileDescriptor**, while a **Socket** or NIO channel holds corresponding native state.

### 1.1 From Java Object to Kernel

The path of a file read operation can be visualized as follows:

~~~mermaid
flowchart LR
    A["FileInputStream in Java"] --> B["FileDescriptor / native handle"]
    B --> C["Process FD table<br/>e.g., number 7"]
    C --> D["Open file description in kernel"]
    D --> E["File, socket, pipe, or device"]
~~~

An FD number is simply an index in a process's descriptor table. It is not the file or socket itself. The kernel uses that descriptor to locate the corresponding open state.

For a regular file, the open state in the kernel can hold the current read/write offset, status flags, and a reference to the file. For a socket, the kernel also manages protocol state, send/receive data queues, and connection metadata. These parts reside outside the Java heap.

Two different FDs can reference the same open file description, for instance after a **dup** operation. Therefore, closing one FD does not necessarily free the kernel object if another descriptor still references it.

### 1.2 Why Saving Only the FD Number Is Not Enough

Suppose a process has FD number 7 pointing to a file. After the file is closed, the kernel can reuse number 7 for a new socket. Thus, the number 7 does not carry a durable identity.

A checkpoint image can save process memory state, including integers and Java objects holding them. However, keeping an FD number intact in memory does not automatically guarantee that the underlying kernel object is still valid, still belongs to the same resource, or can be used safely in the restore environment.

For sockets, the issue is even clearer: a TCP connection has state on both ends. Retaining a Java reference cannot guarantee the peer is still connected, the network path remains the same as before checkpoint, or login session state remains valid after restore.

## 2. Why File Descriptors and OS Resources Matter for CRaC

During a checkpoint, CRaC coordinates with the checkpoint engine to save the process's state. Before creating the image, the application receives the **beforeCheckpoint** callback. After the image is restored, the application receives the **afterRestore** callback.

Two groups of state must be distinguished:

- **Internal application state:** Java objects, heap data, logical state, data structures, and variables within the process.
- **Resources external to the process:** kernel state, connections to other services, files on the filesystem, devices, container resources, and remote services.

The second group can change during the interval between checkpoint and restore. Even if the checkpoint engine can preserve certain resources in a specific environment, the application must still consider whether that resource remains business-valid after restore.

For example:

- A configuration file may have been updated while the application was checkpointed.
- A remote server may have closed the TCP connection.
- A database may have expired the session or reclaimed the connection.
- A container may be started on a different host, with a different IP address, route, or mount.
- A file lock may no longer be held.
- Timers and deadlines may have expired because real wall-clock time has elapsed.

CRaC therefore requires applications to prepare resources that cannot be safely recovered. Some runtimes can detect open FDs and reject the checkpoint with an error. The list of descriptors permitted to remain open may include certain standard FDs or runtime-internal FDs; details depend on the JDK build, CRaC runtime, and checkpoint engine.

## 3. Resources to Inventory

Not all OS resources are managed via the same type of FD. When preparing an application for CRaC, inventory Java, native, and remote resources alike.

| Resource | Risk at restore | Common handling |
|---|---|---|
| File input/output | File may have changed, descriptor may be invalid, buffers not fully flushed | Flush data to preserve, save logical position, close before checkpoint, and reopen after restore |
| File channel | Channel holds an FD and read/write position state | Save required position, close channel, create new channel |
| TCP/UDP socket | Peer or connection state may have changed | Close socket, reconnect, authenticate, and restore subscriptions |
| Server socket | Port or network environment may change; listener could remain in stale state | Stop accepting connections, close listener, rebind and listen after restore |
| Database connection | Session, transaction, or connection pool may expire | Finish transactions cleanly, close or invalidate pool, create new pool/connections |
| Pipe and process handle | Child process or pipe endpoint may not restore with the application | Synchronize child process, close pipe, and recreate IPC relationships as needed |
| File lock | Lock belongs to the kernel and may be released when the channel closes | Save business state, close channel, reacquire lock, and handle cases where another process took it |
| Memory mapping | Mapping depends on file and filesystem; file may be replaced or modified | Check runtime support, release or recreate mapping by design |
| epoll, eventfd, io_uring | Kernel-level I/O state, not merely Java objects | Stop event loop, release native handle, rebuild selector/event loop |
| Timer, device handle | Timer or device state may depend on host and wall-clock time | Cancel old timers, recompute deadlines, and reopen devices |
| JNI/native library handle | Native code may open FDs unknown to Java | Add hooks to manage native resources or modify library to close and recreate handles |

This table is a starting point for inventorying. Specific handling depends on the resource's semantics: some resources need exact position recovery, some need reconnection, and some should be created entirely anew.

## 4. Resource Lifecycle in CRaC

CRaC provides an API for applications to register objects interested in two points of the checkpoint/restore lifecycle.

A resource implements the **Resource** interface and is registered with a **Context**. The global context retrieved from **Core.getGlobalContext()** is usually the simplest choice.

Two primary callbacks:

- **beforeCheckpoint(Context)**: runs before the checkpoint is created. The resource stops related activity, flushes required data, saves logical state, and closes OS resources.
- **afterRestore(Context)**: runs after the process is restored. The resource recreates file channels, sockets, pools, or handles required for the application to continue operating.

Structural example:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ManagedResource implements Resource {

    public ManagedResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Stop usage and release OS resources.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Recreate resources so the application can resume operation.
    }
}
~~~

The example uses the **org.crac** package, which is the compatibility API provided by the CRaC project for applications. Some CRaC-enabled JDK builds provide the API in the **jdk.crac** package. Use the package and version matching the project's JDK/runtime.

### 4.1 Callback Ordering

For the global context in CRaC documentation, **beforeCheckpoint** callbacks are invoked in resource registration order; **afterRestore** callbacks are invoked in reverse order.

This is useful when resources depend on each other. For example, an HTTP server depends on a connection pool:

- Before checkpoint, the server should stop accepting requests and complete in-flight requests before the pool is closed.
- After restore, the pool must be ready before the server accepts new requests.

If resources are registered in the right order, reverse callback ordering can support closing and opening resources according to dependency relationships. For custom contexts or framework-specific resource management, verify that context's ordering policy.

### 4.2 Errors in Callbacks

If a resource cannot prepare safely, **beforeCheckpoint** should throw an exception so the checkpoint is rejected. Do not catch the error and ignore it, as the checkpoint could produce an inconsistent image.

Similarly, if **afterRestore** cannot recreate an essential resource, the application should not report ready status. Let the error propagate to the restore mechanism or application readiness handler. For resources recoverable via retry, clearly define the retry deadline and when traffic may be accepted.

## 5. Example: Closing and Reopening a FileChannel

A file channel holds a kernel-managed file handle. At checkpoint time, we can save the current read position, close the channel, and open a new channel after restore.

The following example assumes a reader object is the sole manager of the channel. Read operations and callbacks are synchronized on the same monitor so the position is not saved while another thread is reading.

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ResumableFileReader
        implements Resource, AutoCloseable {

    private final Path path;
    private FileChannel channel;
    private long savedPosition;

    public ResumableFileReader(Path path) throws IOException {
        this.path = path;
        openAtSavedPosition();
        Core.getGlobalContext().register(this);
    }

    public synchronized int read(ByteBuffer destination)
            throws IOException {
        if (channel == null) {
            throw new IllegalStateException("File channel is not open");
        }

        int count = channel.read(destination);
        if (count > 0) {
            savedPosition = channel.position();
        }
        return count;
    }

    private void openAtSavedPosition() throws IOException {
        FileChannel reopened = FileChannel.open(
                path, StandardOpenOption.READ);
        try {
            reopened.position(savedPosition);
            channel = reopened;
        } catch (IOException e) {
            try {
                reopened.close();
            } catch (IOException closeError) {
                e.addSuppressed(closeError);
            }
            throw e;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        if (channel != null) {
            savedPosition = channel.position();
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws IOException {
        openAtSavedPosition();
    }

    @Override
    public synchronized void close() throws IOException {
        if (channel != null) {
            channel.close();
            channel = null;
        }
    }
}
~~~

Key points to note:

1. **Save logical state.** For example, save the read position instead of trying to retain the FD number.
2. **Close the handle before checkpoint.** When the channel closes successfully, the corresponding FD is released.
3. **Create a new handle after restore.** A new channel is opened from the path and positioned to the saved offset.
4. **Synchronize access.** The same monitor protects read operations and both callbacks, preventing saving the position while a read operation is incomplete.
5. **Handle file changes.** If the file could be replaced or modified while checkpointed, saving only the byte offset may be insufficient. The application may need to store a file key, version, checksum, or business cursor, then verify the file before continuing.

In real applications, clearly decide the semantics when a file changes: continue reading from the new file, restart, or fail the restore. Do not assume a path after restore always points to the exact same content as before checkpoint.

## 6. Example: Network and Database Connections

### 6.1 Sockets

An open socket represents connection state maintained jointly by the kernel and the peer. After checkpoint, the peer may have closed the connection or the authentication session may have expired. Thus, the common practice is to close the socket before checkpoint and create a new connection after restore.

~~~java
@Override
public synchronized void beforeCheckpoint(
        Context<? extends Resource> context) throws IOException {
    if (socket != null) {
        socket.close();
        socket = null;
    }
}

@Override
public synchronized void afterRestore(
        Context<? extends Resource> context) throws IOException {
    socket = openNewSocket();
}
~~~

**openNewSocket()** must perform all required steps: create the socket, connect with a timeout, perform TLS handshake if applicable, authenticate, and re-register application-layer subscriptions or listeners.

You cannot resume an in-flight transaction or message exchange merely by reopening a socket. Design the protocol so the application can determine which messages were processed, which need resending, and which operations must be idempotent. If the new connection fails, the application must remain unready until the connection is restored.

### 6.2 Database Connections and Connection Pools

A JDBC connection typically represents a session on the database server. That session may time out or be closed by the server while the application is checkpointed.

A suitable workflow is usually:

1. Stop accepting new work and wait for running requests to finish.
2. Commit or roll back transactions according to business rules.
3. Close borrowed connections and close or invalidate the connection pool before checkpoint.
4. After restore, create a new pool or let the framework reinitialize the pool.
5. Test connectivity and open readiness only when the pool is operational.

Do not checkpoint in the middle of an open transaction if the application lacks an explicit transaction recovery mechanism. Nor should an old connection be returned to the pool after restore merely because its Java object still exists on the heap.

If a framework such as Spring Boot, Quarkus, or Micronaut already integrates CRaC, prefer the lifecycle mechanism provided by the framework. Avoid registering a separate resource that could close the same connection pool a second time or conflict with the framework's shutdown order.

## 7. Coordinating Threads and Execution Flows

Closing files and sockets is only part of preparation. The application must also ensure no thread is using a resource while the callback closes it.

A common preparation sequence:

1. **Stop accepting new work:** pause HTTP listeners, consumers, or schedulers.
2. **Drain running work:** wait for requests, message handlers, and transactions to finish within a time limit.
3. **Stop or pause workers:** ensure threads do not continue accessing resources about to close.
4. **Flush data:** write critical buffers and persist required logical state.
5. **Close resources:** close files, channels, sockets, pools, and native handles.
6. **Create checkpoint.**
7. **After restore, rebuild dependencies:** open files, create pools, connect services, and start workers.
8. **Reopen traffic:** allow accepting requests only after essential components are ready.

Design a timeout for the drain step. If a request cannot finish within the allowed time, explicitly decide whether to cancel the request, fail the checkpoint, or defer the checkpoint. Do not forcibly close a resource while another thread may still be writing to it.

In systems with multiple dependency layers, close and open ordering is critical. Traffic-receiving components should stop before the dependencies they use; upon restore, dependencies should be ready before traffic-receiving components restart.

## 8. Native Resources and FDs Not Managed Directly by Java

Not every FD originates from **FileInputStream** or **Socket**. JNI, JNA, C/C++ libraries, and certain frameworks can invoke system calls directly to create descriptors.

For example:

- Native libraries opening files via **open()** or sockets via **socket()**.
- Logging or metrics libraries managing their own file handles.
- Event loops creating epoll descriptors, eventfd, or timerfd.
- IPC libraries creating pipes or Unix domain sockets.
- Drivers or SDKs creating device handles.

If a native library does not provide an API to close and reopen resources, Java code can hardly manage their lifecycles properly. Work with the library to add lifecycle hooks, or change the integration approach so the application can stop, release, and reinitialize that component.

Resources such as memory mappings, direct memory, and native handles must be evaluated against the runtime and checkpoint engine in use. Do not infer that because a Java object still exists after restore, every native resource beneath it is also valid.

## 9. Detecting Open File Descriptors

On Linux, a process's descriptors can be inspected via the **/proc** virtual filesystem or system tools.

### 9.1 Using lsof

~~~bash
lsof -p <PID>
~~~

This command lists files, sockets, pipes, and objects currently kept open by the process. You can filter by resource type or path to find items of interest.

### 9.2 Inspecting /proc

~~~bash
ls -l /proc/<PID>/fd
~~~

Each entry in the directory is one of the process's descriptors. The symlink target typically indicates which file, socket, pipe, or object the descriptor points to. This is a quick way to inspect open FDs when lsof is unavailable.

### 9.3 Using Checkpoint Errors and Stack Traces

If a checkpoint fails due to an open FD, read the entire exception and its suppressed exceptions. A high-level error such as **CheckpointException** can contain details about the specific descriptor, resource type, and path.

With some CRaC JDK builds, you can enable:

~~~bash
-Djdk.crac.collect-fd-stacktraces=true
~~~

Depending on the runtime, this option records the stack trace at the time an FD was created via Java APIs, making it easier to locate the class that opened a file and forgot to close it.

If an FD was created directly from native code, a Java stack trace may not exist. In that case, **strace** can help locate the system call that created the descriptor:

~~~bash
strace -f -o /tmp/strace.log java -jar app.jar
~~~

Then search for system calls such as **openat**, **socket**, **accept**, **pipe**, and **dup**, and correlate with checkpoint timing. Note that tracing can produce substantial logs and alter application timing.

### 9.4 JDK Resource Policies

Some CRaC runtimes provide mechanisms to configure policies for certain FDs opened through JDK APIs. Policies can specify actions such as reporting an error, closing, or reopening certain resource types.

This is a helpful tool when a library is hard to modify, but it has limitations:

- Policies do not replace application lifecycle management.
- FDs created directly from native code may fall outside policy scope.
- Automatic closing can leave Java objects referencing already-closed handles.
- Reopening sockets or special resources may not be supported or may not preserve original semantics.

Use policies only after understanding which resources match, what actions are taken, and how Java objects will behave after restore. For critical resources, explicit **Resource** callbacks are usually easier to control.

## 10. Common Design Mistakes

### Keeping the Java object while forgetting to close the underlying resource

An instance variable remaining intact after restore does not prove the FD or socket it references is still valid. The object can retain stale state while the kernel resource has been closed or altered.

### Closing only one wrapper while another descriptor remains

If native code or another library duplicated the FD, closing one wrapper may not release the open file description. Identify all places holding handles and define clear ownership conventions.

### Closing streams without flushing data

Closing a resource may flush buffers depending on the class and usage. For critical data, flush explicitly and check for errors before checkpoint. Do not assume every library buffer has been safely written when the callback finishes.

### Leaving transactions or requests in progress

Checkpointing in the middle of a business operation can leave ambiguous state: the application side thinks the operation is incomplete while the remote service already processed it. Define safe checkpoint points and use idempotency keys or appropriate acknowledgment mechanisms.

### Swallowing exceptions inside callbacks

If closing a file or connection fails yet the callback returns normally, checkpointing may proceed in an unsafe state. Propagate errors to CRaC so the checkpoint is rejected.

### Assuming the restore environment is identical to the checkpoint environment

IP addresses, DNS, mounts, credentials, certificates, filesystems, or service sessions can change. Re-resolve and re-authenticate environment dependencies after restore when needed.

### Reopening resources without restoring business state

Creating a new socket does not automatically restore subscriptions; opening a new file does not automatically restore a meaningful cursor; creating a new connection pool does not automatically restore transactions. Save and restore business state at the appropriate layer.

## 11. Implementation Workflow for a CRaC Application

The following workflow can be applied when introducing CRaC to an existing Java service:

**Step 1 — Inventory resources.** Locate I/O classes, JDBC, HTTP clients, message consumers, schedulers, native libraries, file locks, and device resources. Check resources created automatically by frameworks as well.

**Step 2 — Define owners.** Each resource needs one component responsible for opening, closing, and reopening it. Avoid having multiple classes close the same handle without an ownership convention.

**Step 3 — Choose state to save.** Save logical data such as read positions, message offsets, configuration, or subscription state. Avoid saving FD numbers as a way to recover resources.

**Step 4 — Write controllable callbacks.** **beforeCheckpoint** stops related activity, saves state, and releases resources. **afterRestore** recreates resources and verifies them before the application operates.

**Step 5 — Check dependency ordering.** Ensure consumers stop before dependencies and dependencies are ready before consumers. Verify actual callback ordering of the context or framework.

**Step 6 — Test checkpointing under stable load.** Observe exceptions, suppressed exceptions, open FDs, and checkpoint engine logs. Repeat with different request types or workloads using distinct resources.

**Step 7 — Test restore in the target environment.** Verify files, sockets, databases, DNS, certificates, timers, and readiness. If the restore environment may be a different host, test that case as well.

**Step 8 — Monitor after restore.** Measure dependency reinitialization time, reconnection failure rates, FD counts, request errors, and latency before opening traffic.

An application should only be considered ready after restore once required dependencies have been initialized and verified successfully. This is the responsibility of the application or framework lifecycle, not solely the checkpoint engine.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and reasons why resources must be coordinated.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): registering Resources and implementing **beforeCheckpoint** / **afterRestore**.
- [CRaC — Debugging](https://crac.org/reference/debugging/): errors from open FDs, stack traces, and investigating native descriptors.
- [CRaC — File descriptor policies](https://crac.org/reference/fd-policies/): limitations and policy configuration for certain file descriptors.
- [CRaC Resource API](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/Resource.html): callback contract of the Resource interface.

# Boundaries Between Java State, Native Code, and Operating System State

When a Java application runs, its state does not reside entirely in objects on the Java heap. Part of the state is managed by the JVM, part resides in native memory or libraries loaded into the process, and another part is managed by the operating system outside the process address space. The application may also depend on state in remote systems such as databases, message brokers, or network services.

This separation is especially important when using **CRaC (Coordinated Restore at Checkpoint)**. A checkpoint saves process state so execution can resume from a prepared state. However, the fact that a Java object still remains in the heap after restore does not mean every resource that object represents still works. A Java wrapper may remain intact, while the socket, file descriptor, native handle, or connection session in an external system may have changed, expired, or cannot be restored in the new environment.

To design a CRaC-compatible application, you need to identify which layer each piece of state belongs to, who owns it, and how to verify or recreate that state after restore.

## 1. Three Layers of State in a Java Process

The state used by an application can be divided into three broad layers:

1. **Java and JVM state:** objects, classes, Java threads, stacks, heap, runtime data, and structures managed by the JVM.
2. **In-process native state:** native memory regions, C/C++ libraries, JNI, JNA, the Foreign Function & Memory API, native threads, and handles managed by libraries.
3. **Operating system state:** file descriptors, sockets, pipes, timers, system locks, namespaces, permissions, mounts, devices, and kernel objects.

Beyond these three layers, there is also state in systems external to the process. For example, database transactions, message broker consumer offsets, login sessions, or data in a remote cache do not reside in the Java process memory.

The following diagram illustrates the relationships between the layers:

~~~mermaid
flowchart TB
    subgraph P["Java Process"]
        subgraph J["JVM and Java"]
            H["Java heap: objects, collections, caches"]
            T["Java threads, stacks, class metadata"]
            R["JVM runtime, JIT, class loaders"]
        end
        subgraph N["In-process native"]
            M["Native memory, direct buffers"]
            L["JNI / JNA / FFM"]
            S["C/C++ libraries, native threads, native global state"]
        end
        H --> L
        T --> L
        L --> M
        L --> S
    end
    subgraph O["Operating system / kernel"]
        F["File descriptors, sockets, pipes"]
        K["Kernel objects, timers, locks"]
        E["Namespaces, cgroups, permissions, mounts"]
    end
    subgraph X["External systems"]
        D["Database / message broker"]
        Q["Network services / caches / identity providers"]
    end
    L --> F
    S --> K
    F --> D
    F --> Q
~~~

A single component can span multiple layers. For instance, the application holds a Socket object on the Java heap. That object is associated with a socket managed by the operating system. The socket, in turn, represents a connection to a remote server. The Java object, the kernel socket, and the session state on the server are three separate parts.

## 2. Java and JVM State

### 2.1. Java Heap

The Java heap contains objects created by the application and libraries: entities, collections, caches, parsed configuration, connection management objects, and wrappers for other resources.

For example:

~~~java
public final class ApplicationState {
    private final Map<String, String> configuration;
    private final List<String> cachedValues;
    private final UserSession currentSession;

    public ApplicationState(
            Map<String, String> configuration,
            List<String> cachedValues,
            UserSession currentSession) {
        this.configuration = configuration;
        this.cachedValues = cachedValues;
        this.currentSession = currentSession;
    }
}
~~~

Objects like those above reside in the process memory. When checkpoint and restore are performed properly with JDK support, heap state is an essential part of the restored state. The object graph, field values, and reference relationships can continue to exist without the application having to recreate each object.

However, the heap only stores the state that the objects represent. If currentSession contains an expired token or configuration holds an outdated configuration version, restore does not automatically refresh those values. The data may still be valid from a memory perspective, yet no longer valid from a business perspective.

### 2.2. Classes, Class Loaders, and Runtime Data

The JVM manages many structures outside the Java heap, such as class metadata, class loaders, constant pools, method information, and JIT-compiled code. Some regions such as Metaspace and code cache reside in the process memory space, yet are not ordinary Java objects.

With CRaC, the JDK and checkpoint mechanism must coordinate so that JVM state can be saved and restored consistently. You should not equate a CRaC checkpoint with merely writing the Java heap to disk: the JVM runtime state also participates in the process.

Class loaders and loaded libraries can also hold state. For example, an application may have loaded a native library using System.loadLibrary(). After restore, the process state may still reflect that the library is loaded. Whether the library operates safely depends on native data, operating system resources, and the library's own assumptions.

### 2.3. Java Threads and Stacks

Each running Java thread has execution state such as a program counter, stack frames, local variables, and synchronization state. The JVM coordinates with the operating system to execute these threads.

A thread may currently be:

- Executing Java bytecode.
- Making a JNI call into native code.
- Waiting on a monitor or lock.
- Waiting on I/O.
- Sleeping or waiting for a scheduled task.
- Performing work in an executor or scheduler.

Thread state is a sensitive part of checkpointing. If an application checkpoints while a thread is holding a lock, writing data, or in the middle of a native operation that depends on an external system, restore may resume in a state incompatible with the current environment.

The application needs to bring relevant threads into a safe state before checkpoint. This usually means stopping acceptance of new work, waiting for running tasks to complete, or asking threads to stop at a recoverable point.

### 2.4. Java Values Can Become Stale Even When Memory Is Restored

Some values remain structurally valid but are no longer valid over time:

- Expired authentication tokens.
- Cache entries that have exceeded their TTL.
- Session expiration timestamps that have passed.
- DNS entries or service addresses that have changed.
- Per-instance configuration that no longer matches the restore environment.
- Schedules that missed execution times while the process was inactive.

For example, the following object may still be restored intact:

~~~java
public final class CachedCredential {
    private final String token;
    private final Instant expiresAt;

    public boolean isExpired(Clock clock) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

The application needs to check expiresAt after restore and refresh the token if needed. The object remaining intact in the heap does not replace verifying the credential's validity with the identity provider.

## 3. Native State: In-Process Memory and Libraries

Java can invoke native code via JNI, JNA, or the Foreign Function & Memory API. Native libraries are typically written in C/C++, though they can also be system libraries or vendor libraries.

### 3.1. Native Memory

Native memory is memory allocated outside the Java heap, for example using malloc, mmap, library APIs, or the JVM's native allocation mechanisms. Some Java APIs allocate native memory regions while providing Java wrappers for access.

For example, ByteBuffer.allocateDirect() creates a direct buffer whose data resides outside the regular heap:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
buffer.putInt(42);
buffer.flip();
~~~

The direct buffer can still be referenced from the Java heap, while the actual data region resides in native memory. With process-level checkpointing, native memory mapped into the process address space can fall within the saved memory state. However, that does not mean every natively allocated resource is safe after restore.

You must distinguish:

- **Native memory region:** the bytes allocated within the process address space.
- **Resources represented by the memory:** file descriptors, sockets, devices, shared memory regions, or handles managed by the kernel.
- **State in another process:** the service or server with which the native library is communicating.

A buffer containing a data structure might be restored, whereas a file descriptor stored in a field of that structure still needs to be verified or reopened.

### 3.2. Internal State of Native Libraries

A native library may maintain:

- Global and static variables.
- Lookup tables or internal caches.
- Pointers to dynamically allocated memory.
- Native threads and thread-local storage.
- Mutexes, condition variables, and synchronization state.
- I/O buffers.
- File descriptors and sockets.
- Handles to devices or resources managed by other libraries.

Global variables and internal memory belong to the process address space. They may be included in the checkpointed memory state. However, the library may hold assumptions about the kernel or remote services. If those assumptions no longer hold after restore, continuing to call native functions may cause errors.

For example, a library might keep a static int connection_fd variable containing a file descriptor number. The integer value still remains in memory after restore, but the corresponding descriptor must actually be valid in the restored process. You cannot draw conclusions merely from the variable retaining its value.

### 3.3. JNI, JNA, and Foreign Function & Memory API

Three common ways to bridge Java and native code have different characteristics:

| Mechanism | Role | Points to watch during checkpoint |
|---|---|---|
| JNI | Java calls native functions and native code calls back into the JVM | Global references, native global state, thread attach/detach, pointers, and handles |
| JNA | Calls native functions through automatic mapping layers | Java proxy objects may still exist while native handles or resources are stale |
| Foreign Function & Memory API | Calls native functions and manages native memory using Java APIs | Arena/segment lifetime, native addresses, linked libraries, and resources created by native functions |

All three mechanisms can create a boundary between Java objects and native state. Checkpoint restoring memory does not replace the library's lifecycle contract.

### 3.4. Native Threads

A C/C++ library may create threads itself using pthread or an equivalent mechanism without going through Java's Thread class. These threads still belong to the operating system process, yet the JVM does not necessarily manage their lifecycle like Java threads.

The application needs to know whether a library creates native threads. Before checkpoint, use the library's API to:

1. Stop accepting new work.
2. Ask workers to finish or stop at a safe point.
3. Wait for workers to confirm they have stopped or reached a checkpointable state.
4. Release or re-prepare resources used by workers.

If a native thread is holding a mutex, waiting on I/O, or performing device operations, you must clearly understand the restore behavior of the library and platform. You should not arbitrarily terminate threads or close handles from the Java side while the library is still using them.

## 4. Operating System State

The operating system manages many objects outside the Java heap and the process's native memory. Some objects may be supported by the checkpoint/restore mechanism, others have special conditions, and some cannot be restored the way the application expects.

### 4.1. File Descriptors

On Unix/Linux, a file descriptor is an integer that a process uses to reference a kernel resource such as a file, socket, pipe, or device.

For example, Java may hold a FileInputStream. The Java object stores the information needed to call down into the I/O layer; the actual file descriptor is managed by the operating system.

During checkpointing, both sides must be considered:

- The Java object or wrapper is still referencing the descriptor.
- Whether the descriptor and the kernel resource it represents are restored by the checkpoint/restore mechanism.

You should not manually reset a descriptor field to an old number or call close() directly from Java if a library owns the descriptor and has its own cleanup mechanism. Closing the resource should go through the proper API of the owning component so that Java, native, and operating system states are all updated.

### 4.2. Sockets and TCP Connections

A socket is a kernel resource. A TCP connection also involves state at both endpoints and the network infrastructure. Situations can occur where the process is restored, yet the remote server has already closed the session, a load balancer has timed out, or the network address is no longer valid.

CRIU and checkpoint/restore platforms may support certain types of sockets under specific conditions. That capability depends on socket type, network configuration, kernel, permissions, and peer state. Therefore, applications should have a procedure to refresh connections to databases, HTTP services, and message brokers.

For sockets managed by a native library, use the library's close and reopen APIs. Closing the descriptor directly in Java may leave the library thinking the connection is still active.

### 4.3. Pipe, eventfd, epoll, and Timers

Native applications or runtime libraries may use kernel objects such as:

- Pipes or Unix domain sockets for inter-process data transfer.
- eventfd for signaling between threads or components.
- epoll to monitor multiple file descriptors.
- timerfd to receive time-based events.
- Signal handlers and signal masks.
- File locks or inter-process synchronization mechanisms.

A library may store descriptor numbers and event registration states in native memory. If restored kernel objects differ from the library's assumptions, the event loop may stop working or wait indefinitely.

Check the documentation of the library and platform. If there is no compatibility guarantee, stop the event loop before checkpoint and reinitialize it after restore.

### 4.4. Shared Memory and IPC

Shared memory allows multiple processes to access the same data region. The memory region's state may depend on other processes, access permissions, namespaces, and the operating system's IPC mechanisms.

Checkpointing one process does not mean synchronously checkpointing all processes sharing memory with it. If another process continues modifying data while the Java process is paused, the state after restore may no longer be consistent.

With shared memory, determine:

- Which process owns the memory region.
- Who is allowed to write during checkpoint.
- Whether locks or versioning mechanisms protect the data.
- Whether the memory region and synchronization mechanism are supported for restore by the platform.
- Whether the application can reattach or recreate the memory region after restore.

### 4.5. Namespaces, cgroups, Mounts, and Permissions

A process running in a container may depend on namespaces, cgroups, mounts, capabilities, seccomp, UID/GID, and resource limits. These factors affect access permissions and resource usability after restore.

A checkpoint created in a container with a specific configuration cannot necessarily be safely restored in a container with a different configuration. For example, mount paths may change, devices may not be attached, or the process may lack required capabilities.

You must check the runtime configuration of the checkpoint environment and the restore environment according to the requirements of the CRaC JDK, CRIU, and deployment platform.

## 5. State External to the Process

There is an even more important boundary: the state of other systems that do not belong to the Java process. Checkpointing the process does not freeze or roll back those systems.

For example:

- Databases continue processing transactions and timeouts.
- Message brokers continue receiving and delivering messages.
- Remote services continue mutating data.
- Token providers continue issuing or revoking credentials.
- Distributed caches continue expiring entries.
- Other systems may continue updating shared data.

Suppose an application holds a database connection in the heap. Before checkpoint, the Java object exists. While the application is inactive, the database may close the connection due to an idle timeout. Upon restore, the Java wrapper may still exist, but the database session is already lost.

Similarly, if an application sends a request to a remote service and then checkpoints before receiving a response, you cannot infer that the request was not processed. The server may have already executed the operation while the response was lost. After restore, retrying may cause duplicate effects.

Therefore, the following principles should be applied:

- Safely complete or cancel in-flight operations before checkpoint.
- Use transactions and idempotency keys for retryable operations.
- Verify business state from the system that owns the data.
- Refresh connections, sessions, and credentials after restore.
- Design bounded retries, timeouts, and explicit error handling.

## 6. What Does CRaC Save and What Must the Application Handle?

The table below provides a practical classification. Final restorability still depends on the JDK, kernel, CRIU, and environment configuration.

| State type | Examples | Handling approach |
|---|---|---|
| Java heap | Objects, collections, caches in heap | Can resume from saved state; verify whether data is still valid |
| JVM runtime | Class metadata, thread state, runtime data | Requires CRaC JDK coordination with checkpoint/restore |
| Native memory | malloc, mmap, direct buffers | Check memory regions, pointers, and library lifetime |
| Native global state | Static variables, handle tables, internal caches | Use the library's APIs to prepare and recover |
| Native thread | pthread workers, event loops | Stop or bring to a safe state according to library APIs |
| Kernel object | File descriptors, sockets, pipes, timers | Verify supported resource types; reopen when necessary |
| Container/runtime | Namespaces, mounts, cgroups, capabilities | Ensure the restore environment meets compatibility requirements |
| Remote systems | Databases, brokers, caches, APIs | Reconnect, refresh, verify, and handle retries |
| Sensitive data | Tokens, secrets, user data in heap | Protect checkpoints as artifacts containing sensitive data |

You can keep three questions in mind for every resource:

1. Does its data reside in process memory, or is it managed by the kernel/another system?
2. Which component owns and is responsible for closing or reinitializing the resource?
3. After restore, how do you verify that the resource is actually usable?

If you cannot answer these three questions, that resource needs investigation before putting the application into production with CRaC.

## 7. Coordinating Java and Native Resources with CRaC

CRaC provides the org.crac.Resource interface for applications to coordinate with resources before checkpoint and after restore. The two main callbacks are:

- beforeCheckpoint(): prepares resources before the process state is saved.
- afterRestore(): verifies or reinitializes resources after the process is restored.

### 7.1. Example of Managing a Native Handle

Suppose an application uses a native library to process data. The library provides two hypothetical functions:

- openNativeEngine() creates the engine and returns a handle.
- closeNativeEngine(handle) stops workers and frees native resources.

Java can manage the lifecycle using a Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class NativeEngineResource implements Resource {

    private final String configuration;
    private volatile long nativeHandle;

    public NativeEngineResource(String configuration) {
        this.configuration = configuration;
        this.nativeHandle = openNativeEngine(configuration);

        // Register so CRaC invokes lifecycle callbacks.
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        long handle = nativeHandle;
        if (handle != 0) {
            // The native function must stop the worker and release the handle
            // according to the library's contract.
            stopAndCloseNativeEngine(handle);
            nativeHandle = 0;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        // Create a new handle in the restored environment.
        nativeHandle = openNativeEngine(configuration);
    }

    public long getNativeHandle() {
        long handle = nativeHandle;
        if (handle == 0) {
            throw new IllegalStateException(
                    "Native engine is not available");
        }
        return handle;
    }

    private static native long openNativeEngine(String configuration);

    private static native void stopAndCloseNativeEngine(long handle);
}
~~~

This is an illustrative example. The two native methods must be implemented in the application's library. stopAndCloseNativeEngine() must stop workers, release resources, and ensure no thread is using the handle after the function returns.

The key point is that Java does not merely store a number nativeHandle. That handle represents state managed by the native library. Before checkpoint, the application calls the library's API to close the old state and sets the Java field to an invalid value. After restore, the application creates a new handle based on the valid configuration.

In real-world applications, handle usage must be protected against race conditions. You must not close the handle while another thread is still calling a native method with that handle. You can use quiescing, locking, reference counting, or the library's lifecycle APIs to guarantee this.

### 7.2. Why Not Just Keep the Pointer As-Is?

A native pointer is an address in the process address space. After restore, the memory region may be restored, but the validity of the pointer also depends on:

- Whether the allocated memory region still exists.
- Whether the library owning the memory region is still in a consistent state.
- Whether the pointer points to an expired kernel object or external resource.
- Whether the library requires reinitialization or registering internal callbacks.
- Whether other threads are still using that memory region.

A pointer should not be treated as a durable identifier usable across any environment. If a library has APIs to create and destroy handles, use those exact APIs in the CRaC lifecycle.

### 7.3. Coordinating with Libraries That Do Not Provide a CRaC Resource

Many native libraries are unaware that CRaC exists. The application may need to write a Resource adapter wrapping the library, or use an integration provided by the library vendor.

The adapter should:

1. Call the API to stop work and close resources before checkpoint.
2. Record the configuration required to recreate the resource.
3. After restore, reload or reinitialize the library if necessary.
4. Recreate handles, workers, and connections.
5. Verify that the library is ready before the application accepts requests.

If a library lacks an API for safe stopping or recovery, you must evaluate whether it is compatible with the checkpoint/restore model. Do not guess the library's internal state from external Java fields.

## 8. Sequence of Preparing and Restoring a Multi-Layer Resource

A resource may consist of a Java object, a native handle, and a kernel socket. For example, a native database client may have:

- A Java wrapper holding configuration and the handle.
- A native library managing the connection pool.
- The kernel managing the sockets.
- The database server managing sessions and transactions.

When preparing for checkpoint, the application should follow resource ownership:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant R as CRaC Resource
    participant N as Native library
    participant OS as OS / kernel
    participant DB as Database

    App->>R: beforeCheckpoint()
    R->>N: Stop accepting work
    N->>DB: Finish or cancel in-flight work
    N->>OS: Close sockets and native handles
    N-->>R: Native state released
    R-->>App: Resource prepared
    Note over App,DB: Checkpoint captures the process after preparation
    Note over App,DB: Restore reconstructs the process in a compatible environment
    App->>R: afterRestore()
    R->>N: Initialize native client
    N->>OS: Open new sockets
    N->>DB: Establish new session
    DB-->>N: Session ready
    N-->>R: Native client ready
    R-->>App: Resource available
~~~

This is a conceptual sequence. Callback ordering across multiple resources must follow the CRaC contract and the specific integration. If one resource depends on another, design explicit dependency relationships instead of relying on implicit registration order.

## 9. Common Mistakes When Failing to Distinguish State Layers

### 9.1. Wrapper Object Remains While Resource Is Lost

The application sees the connection field is non-null and assumes the connection is still active. In reality, the socket has been closed or the server has timed out.

**How to handle:** check connection status and recreate the connection pool after restore. Do not use object existence as proof that an external resource is still valid.

### 9.2. Native Handle Still Holds Old Value

The long handle field still contains a non-zero number, yet the library has freed the resource or the handle is no longer valid.

**How to handle:** close the handle via the library's API before checkpoint, set the field to an invalid state, and create a new handle after restore.

### 9.3. Closing a File Descriptor from the Wrong Layer

Java calls the close operation on a descriptor itself while the native library still stores that descriptor and continues using it.

**How to handle:** let the component that owns the descriptor close it. If coordination between Java and native code is required, provide an explicit lifecycle function on the native side.

### 9.4. Native Worker Still Running During Checkpoint

A native thread is reading from a socket or modifying data in a buffer. The Java Resource only closes the wrapper object without stopping the worker.

**How to handle:** the adapter must call the API to stop the worker and wait for the worker to reach a safe state. Only free native memory after ensuring no threads are using it.

### 9.5. Assuming Remote Systems Are Frozen Along with the Process

The application restores and resumes transactions or message processing as if the database and broker had never changed.

**How to handle:** complete or cancel operations before checkpoint, verify state after restore, and design idempotent retries.

### 9.6. Using a Shutdown Hook to Prepare for Checkpoint

Shutdown hooks are designed for normal JVM shutdown. They should not be used in place of CRaC callbacks to prepare resources.

**How to handle:** register a Resource and place the necessary logic in beforeCheckpoint() and afterRestore(). Reserve shutdown hooks for actual application shutdown.

### 9.7. Testing Only in the Development Environment

A native library may work on a developer machine yet fail in a production container due to differences in kernel, mounts, permissions, devices, or library versions.

**How to handle:** test checkpoint and restore in an environment close to production, including container configuration, system permissions, and the services the application needs to connect to.

## 10. How to Survey State Boundaries Before Adopting CRaC

You should inventory resources by application component. For each resource, record its owner, state layer, and lifecycle handling approach.

| Component | Java state | Native state | OS / external state | Pre-checkpoint action | Post-restore action |
|---|---|---|---|---|---|
| JDBC pool | Pool object, config | May have native driver state | TCP socket, DB session | Stop pool, handle transactions, close connections per integration | Start pool, verify DB |
| HTTP client | Client object, cache | TLS/native provider state depending on library | Socket, DNS, remote server | Stop new requests, close client if needed | Recreate connections, refresh DNS or credentials when needed |
| Native engine | Java wrapper, handle field | Native heap, worker, static state | File descriptor, shared memory, device | Stop worker, invoke native cleanup | Create new engine and handle |
| File watcher | Java watcher object | Native event loop depending on implementation | inotify descriptor, file system | Stop watcher per API | Create new watcher and synchronize file state |
| Scheduler | Task registry, Java thread | May use native timer | Timer, system time | Pause scheduler, handle running tasks | Recalculate schedule and resume |
| Message consumer | Consumer object, offset cache | Native client buffer if any | Broker connection, committed offset | Stop polling, handle in-flight messages, commit per policy | Create new consumer, re-read offset and resume |

A survey procedure can be carried out as follows:

1. Find JNI, JNA, and FFM call sites and loaded native libraries.
2. Find APIs that create resources: sockets, files, threads, executors, schedulers, direct buffers, native handles.
3. Identify the layer owning the resource and the official close/open APIs.
4. Determine whether the resource can persist across checkpoint or needs to be closed.
5. Write a Resource or use a CRaC-compatible integration.
6. Test checkpoint under low load, then gradually increase concurrency.
7. Restore after a sufficiently long interval to detect timeouts, expired tokens, and remote state changes.
8. Measure callback duration, recovery errors, native memory, and connection counts after restore.

Not every resource needs to be closed before checkpoint. Some resources are supported for restoration by the platform and can be kept. However, that decision must be based on documentation of the JDK, CRIU, operating system, and libraries in use, along with actual test results.

## 11. Security and Integrity of Checkpoints

A checkpoint can contain much more data than a typical configuration file. It can contain:

- Access tokens and refresh tokens.
- Decrypted passwords or secrets.
- User data in the heap.
- Encryption keys or security provider state.
- Temporary data in native memory.
- Connection information and session state.

Therefore, checkpoints must be protected like an artifact containing sensitive data:

- Restrict read, write, and distribution permissions.
- Encrypt at rest or in transit according to environment policy.
- Do not place checkpoints in public storage.
- Manage lifecycle and delete old checkpoints.
- Check credentials after restore and revoke or refresh them when necessary.
- Avoid creating checkpoints while the application holds data that should not be persisted long-term in memory.

Integrity is also important. If a checkpoint is created while a transaction is incomplete or a native buffer contains unsynchronized data, restore may resume from an inconsistent state. The application must define safe points before allowing a checkpoint.

## 12. Resource Design Checklist for Applications with Native Code

When a component uses JNI, JNA, FFM, or a native library, confirm the following points during design:

- [ ] Listed loaded native libraries and their corresponding versions/ABIs.
- [ ] Identified native memory, native global state, and native handles created by the library.
- [ ] Identified whether the library creates native threads, event loops, or timers.
- [ ] Identified file descriptors, sockets, shared memory, and kernel objects owned by the library.
- [ ] Have an official API to stop workers and release resources before checkpoint.
- [ ] No threads continue using native memory or handles once the resource is closed.
- [ ] After restore, handles are recreated or verified using the library's API.
- [ ] Connections to databases, brokers, and remote services are verified or recreated.
- [ ] Callbacks do not rely on shutdown hooks or finalizers to handle checkpoint.
- [ ] Tested restore in a production-compatible environment.
- [ ] Checkpoints are protected as sensitive data.

## 13. Conclusion

The state of a Java application spans multiple layers. The Java heap holds objects and application data; the JVM manages classes, threads, and runtime; native code can hold memory, pointers, threads, and library state; the operating system manages file descriptors, sockets, timers, namespaces, and kernel objects; remote systems continue maintaining state independently of the process.

CRaC helps save and restore process state in a compatible environment. However, each layer has its own lifecycle and owner. A restored Java object does not prove that the native handle, socket, or database session it represents is still usable.

Good CRaC design starts by mapping resources, identifying who owns each resource, and using callbacks to prepare or reinitialize them. For native code, coordinate through the library's official API, stop native workers safely, and recreate handles when needed. For operating system resources and remote systems, check compatibility, verify state, and re-establish connections after restore.

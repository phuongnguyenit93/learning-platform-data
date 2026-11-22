# JNI Resources, Native Libraries, and File Descriptors Outside the JDK

A Java application can own many resources outside the direct management scope of the JDK: sockets opened by C/C++ libraries, file descriptors created by JNI, native threads, POSIX mutexes, memory regions mapped with `mmap`, device handles, or accelerator library contexts. These resources remain tied to the process and the operating system even though most of the application logic is written in Java.

When using CRaC, the fact that the JVM can capture the heap and process state does not mean all native resources will continue to function properly after restore. Some resources can be restored by the checkpoint engine if supported by the operating system and descriptor type; some resources need to be closed before checkpoint and recreated after restore; others cannot be safely restored and must be released or reinitialized through a separate procedure.

Therefore, the application needs to bring JNI resources and native libraries into the same CRaC lifecycle management process. A common approach is to create a Java wrapper implementing `org.crac.Resource` (or the CRaC API chosen by the application), then call JNI functions to stop native operations, release handles before checkpoint, and reopen resources after restore.

## 1. Distinguishing Java State, Native Memory, and Operating System Resources

A Java process has multiple layers of state:

| State Type | Examples | Considerations during checkpoint/restore |
|---|---|---|
| Java heap | Objects, collections, service state | Usually saved in the process image; still needs business consistency checks |
| Process-owned native memory | `malloc` memory regions, C/C++ structs, native thread stacks | Memory contents may reside in the process image, but pointers to external resources can still become stale |
| Kernel resources | File descriptors, sockets, pipes, eventfd, epoll, file locks | Restorability depends on resource type, OS, checkpoint engine, and configuration |
| Device or external service resources | GPU contexts, cameras, audio devices, sessions to servers | Usually need to be verified, closed and recreated, or re-registered after restore |
| Native synchronization state | `pthread_mutex`, condition variables, native worker threads | Must stop at a safe point, avoiding threads holding locks or in the middle of non-resumable operations |

Key point to remember: **process memory and resources managed by the kernel or external systems are two different matters**. A C pointer may still exist in the memory image, but the object it once represented has been closed, changed, or not restored. Similarly, an integer storing a file descriptor number may still be intact in memory, but the corresponding descriptor no longer points to the right resource.

For example, a native library stores `socket_fd = 42`. If that socket is closed before checkpoint, after restore the `socket_fd` variable may still hold 42 if the code does not reset it to a sentinel. The operating system may have reused number 42 for another file or socket. Calling `send(42, ...)` at that point could write to the wrong new resource. Therefore, when releasing a descriptor, the ownership state in the native library must also be updated.

## 2. JNI Does Not Automatically Manage the Lifecycle of Native Resources

JNI is the bridge for Java to call native functions and for native code to interact with the JVM. JNI does not automatically know which file descriptors a C/C++ library has opened, how many threads it has created, which signal handlers it has registered, or which device handles it is holding.

A native library can initialize state in several ways:

- `System.loadLibrary(...)` loads the library into the process.
- `JNI_OnLoad` runs when the library is loaded by the JVM and can initialize global structures.
- A native method opens a socket, file, device, or creates a thread when the application starts using a feature.
- `static` variables in C/C++ hold descriptors, pointers, mutexes, cache state, or shared handles.
- Third-party libraries may create their own worker threads and connections to external services that Java does not see directly.

CRaC does not automatically invoke a new `JNI_OnLoad` just because the process is restored. If the library was already loaded at checkpoint time, its mapping state and global variables belong to the process state. Therefore, do not use `JNI_OnLoad` as a post-restore recovery callback. Clearly separate **loading the library** from **opening runtime resources** and provide native functions that can be called again in a controlled manner.

`JNI_OnUnload` is also not an appropriate hook for cleaning up resources before checkpoint. It is tied to the unload lifecycle of the native library, not the CRaC event preparing to snapshot the process. Use the `beforeCheckpoint` callback to proactively instruct the library to release resources.

### Some Native States to Inventory

- File descriptors created with `open`, `socket`, `accept`, `pipe`, `eventfd`, `epoll_create`, or similar APIs.
- Native threads created with `pthread_create`, library-internal thread pools, or background callbacks.
- Mutexes, condition variables, semaphores, and locks being used by native threads.
- `mmap` memory, shared memory, pinned memory regions, or device-allocated buffers.
- Handles for GPUs, cameras, audio, USB, serial ports, or hardware cryptographic libraries.
- Connections and sessions to databases, brokers, RPC servers, or external daemons.
- Signal handlers, OS timers, callbacks registered with an event loop, and native TLS state.

Not every library provides APIs to close and recreate these resources. If a library has no lifecycle hooks or does not document checkpoint/restore capability, evaluate adding an adapter, changing the integration approach, or excluding the library from the checkpoint process.

## 3. Bringing Native Resources into the CRaC Lifecycle

The CRaC API provides the `Resource` contract with two main callbacks:

| Callback | Goal for native resources |
|---|---|
| `beforeCheckpoint(...)` | Stop accepting work, wait for native operations to finish, stop worker threads at a safe point, flush necessary data, and close handles that cannot be kept across checkpoint |
| `afterRestore(...)` | Reopen descriptors or sessions, recreate native workers, reinitialize device contexts, and verify that resources are ready |

A Java wrapper can coordinate JNI calls as follows:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.crac.Context;
import org.crac.Resource;

final class NativeLibraryResource implements Resource {
    private final NativeBridge nativeBridge;
    private final Duration stopTimeout;

    NativeLibraryResource(
            NativeBridge nativeBridge,
            Duration stopTimeout) {
        this.nativeBridge = nativeBridge;
        this.stopTimeout = stopTimeout;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        try {
            nativeBridge.stopAcceptingWork();

            if (!nativeBridge.awaitNativeWork(stopTimeout.toMillis())) {
                throw new TimeoutException(
                        "Native work did not reach a safe point"
                );
            }

            nativeBridge.closeExternalHandles();
        } catch (Exception failure) {
            try {
                nativeBridge.resumeAfterAbortedCheckpoint();
            } catch (Exception resumeFailure) {
                failure.addSuppressed(resumeFailure);
            }
            throw failure;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        nativeBridge.reopenExternalHandles();
        nativeBridge.startNativeWorkers();
    }
}
```

`NativeBridge` is an application-defined Java class with corresponding `native` methods:

```java
final class NativeBridge {
    native void stopAcceptingWork();
    native boolean awaitNativeWork(long timeoutMillis);
    native void closeExternalHandles();
    native void reopenExternalHandles();
    native void startNativeWorkers();
    native void resumeAfterAbortedCheckpoint();
}
```

This example illustrates the coordination structure. The method names are not built-in APIs of JNI or CRaC; the C/C++ side must implement the contract properly, including thread synchronization, OS error checking, and ownership management for each handle.

In a real application, register `NativeLibraryResource` with the CRaC global context during initialization. If there are multiple native libraries, you can create a lifecycle coordinator to manage the stop and restore order instead of letting components close each other's resources arbitrarily.

### Sequence in Native Code

A C library can maintain state as follows:

```c
static int upstream_fd = -1;
static int event_fd = -1;
static bool worker_started = false;
static bool stopping = false;

/* Called from JNI before checkpoint. */
void native_prepare_checkpoint(void) {
    stopping = true;
    signal_worker_to_stop();

    if (worker_started) {
        pthread_join(worker_thread, NULL);
        worker_started = false;
    }

    if (upstream_fd >= 0) {
        close(upstream_fd);
        upstream_fd = -1;
    }

    if (event_fd >= 0) {
        close(event_fd);
        event_fd = -1;
    }
}

/* Called from JNI after restore. */
void native_restore_resources(void) {
    upstream_fd = connect_to_upstream();
    if (upstream_fd < 0) {
        throw_native_initialization_error();
        return;
    }

    event_fd = create_event_channel();
    if (event_fd < 0) {
        close(upstream_fd);
        upstream_fd = -1;
        throw_native_initialization_error();
        return;
    }

    stopping = false;
    start_worker_thread();
    worker_started = true;
}
```

This is C-like pseudocode to illustrate the lifecycle, not a complete JNI implementation. The functions `signal_worker_to_stop`, `connect_to_upstream`, `create_event_channel`, `throw_native_initialization_error`, and `start_worker_thread` are library-specific implementations. In a real JNI integration, native errors must be translated into appropriate Java exceptions, ensuring no half-opened resources are left without a cleanup path.

## 4. File Descriptors Created by Native Libraries

A file descriptor (FD) is an integer that a process uses to refer to a kernel I/O object. Java streams or NIO channels may also use FDs underneath, but this lesson focuses on descriptors opened and owned by JNI or native libraries outside the JDK.

Common FD sources:

```c
int file_fd = open("/var/lib/app/state.bin", O_RDWR);
int socket_fd = socket(AF_INET, SOCK_STREAM, 0);
int pipe_fds[2];
pipe(pipe_fds);
int event_fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
int epoll_fd = epoll_create1(EPOLL_CLOEXEC);
```

One cannot conclude that all FDs are restored or that all must be closed. Restorability depends on the descriptor type, kernel, CRIU or checkpoint engine version, container configuration, permissions, and the state of the external resource.

| Descriptor Type | Issue on restore | Common handling approach |
|---|---|---|
| Regular file | File path, mount, inode, offset, and locks may have changed or no longer be valid | Verify the file and mount in the target environment; close/reopen if needed |
| TCP socket | The peer may have timed out or the connection state may no longer match the external service | Usually prefer closing and reconnecting at the application layer, unless specific socket restore support has been verified |
| Unix domain socket | Socket attached to a daemon or local endpoint may not exist on restore | Reconnect to the daemon after restore |
| Pipe/FIFO | The other end may have closed or the peer process was not restored at the same time | Recreate the channel and re-handshake with the peer |
| `epoll`, `eventfd`, `inotify` | Registration state and related kernel objects depend on the environment | Recreate the descriptor and re-register watches/events after restore if needed |
| Device FD | The device or driver may not support state restoration | Close before checkpoint, open and reinitialize after restore |
| Shared memory or `mmap` | Backing file, mount, shared mapping, and sharing processes may be out of sync | Verify the backing resource and coordinate with all involved processes |

### Do Not Confuse the FD Number with the Resource

An FD number is only an index in the process's descriptor table. The value `17` is not a persistent identity of a socket or file. After closing an FD, the kernel can reassign that same number to another resource.

When closing an FD in a native library, update the ownership state immediately:

```c
if (socket_fd >= 0) {
    close(socket_fd);
    socket_fd = -1;
}
```

Every access path must check the open state before calling `read`, `write`, `send`, `recv`, or `ioctl`. If an FD is shared among multiple objects, a single owner or a clear reference counting mechanism is needed to avoid double-close and use-after-close.

### Do Not Accidentally Close FDs Owned by the JDK

A native library sometimes receives an FD from Java or receives a `FileDescriptor` via JNI. In that case, ownership must be clearly determined:

- If Java/JDK is the owner, the native library only borrows the descriptor and must not close it on its own.
- If the native library creates the FD and transfers ownership to Java, there must be a clear contract on which component is responsible for closing it.
- If both sides hold references, it must be determined whether the descriptor is duplicated (`dup`) or just the same FD is shared; the two cases have different closing semantics.

Closing an FD that the JDK still thinks is open can break Java streams/channels. Conversely, failing to close an application-owned native FD can leave a stale descriptor in the checkpoint. Manage ownership in a single place.

## 5. Native Threads, Mutexes, and Synchronization State

A JNI library can create threads with `pthread_create` or use its own thread pool. These threads may be:

- Waiting on a condition variable or semaphore.
- Holding a mutex while updating native data structures.
- Sending or receiving data over a socket.
- Executing callbacks into Java via JNI.
- Holding JNI global references or pointers to Java-provided buffers.
- Running inside a third-party library that the application does not directly control.

Before checkpoint, instruct workers to stop accepting work, wake up waiting threads, wait for current operations to complete, and `join` threads if the library's lifecycle allows. Do not snapshot state while a thread is holding a mutex that another thread needs to complete a callback or recovery.

If native threads are allowed to persist across checkpoint, explicitly verify that the runtime and checkpoint engine support that thread type, signals, TLS, stack, and synchronization state. A successful process restore does not prove that every native thread will continue with correct business logic. For libraries with stop/start worker APIs, it is usually easier to control by stopping workers before checkpoint and recreating them after restore.

Do not use `pthread_cancel` arbitrarily to force a thread to stop. Cancellation in the middle of a data write or while holding a lock can leave native structures inconsistent. Prefer cooperative cancellation: set a stop flag, wake up the worker, let the worker exit at a safe point, and wait for completion.

## 6. Native Memory, `mmap`, and Device Handles

### Memory Allocated Within the Process

Memory allocated by `malloc` or `new` usually resides in the process's address space. Its contents can be saved along with the memory image during checkpoint. However, preserving the bytes does not mean every native object remains valid:

- A pointer to a closed descriptor is a stale handle.
- A pointer to memory managed by a driver or device may no longer be valid.
- A native object may contain a mutex or condition variable in an unsafe state.
- A library may store the address of a mapping or resource created by another process.

### Memory Mapping and Shared Memory

With `mmap`, both the mapping and the backing resource must be checked. A file mapping may require the same file, mount, and permissions after restore. Shared memory may also be used concurrently by another process; if only one process is restored, the two sides may no longer agree on versions or locks.

If a mapping is a recreatable cache, consider unmapping it before checkpoint and remapping it after restore. If the mapping contains critical shared data, design a separate synchronization and versioning protocol; do not assume the JVM image automatically resolves consistency across multiple processes.

### GPUs, Cameras, and Peripheral Devices

Handles for GPU contexts, CUDA streams, cameras, audio devices, USB, or accelerators are usually tied to drivers and device state. Do not assume they can be restored just because the pointer remains in native memory. Use the library/driver API to release contexts before checkpoint and create new contexts after restore. If the driver does not support this lifecycle, exclude that resource from the checkpointed process or isolate the device functionality into a separate service.

## 7. Coordinating with Third-Party Native Libraries

Applications often do not directly own the C/C++ code of every library. Database drivers, message broker clients, image processing libraries, codecs, cryptographic libraries, or device SDKs may open FDs and create threads on their own.

Before enabling CRaC, determine:

1. Whether the library has documentation on CRaC/checkpoint/restore.
2. Whether there are APIs to stop operations, flush, close, and reconnect.
3. Whether there are internal native threads or timers.
4. Whether the library uses file descriptors or device handles that the application cannot access.
5. Whether the library and driver versions are in the supported environment matrix.
6. Whether state can be checked after restore and errors reported to readiness.

If the library provides its own lifecycle API, call that API in the callbacks. Do not close descriptors yourself by reading internal FD numbers or using reflection into unsupported implementations; doing so can corrupt internal state and cause hard-to-reproduce bugs.

If the library does not provide a way to recreate resources, options include upgrading the version, replacing the library, creating a vendor-supported adapter, isolating the native part into another process/service, or not using CRaC for that process. Choose an approach based on actual restorability rather than assuming all native state is handled by the checkpoint engine.

## 8. Error Handling and Idempotency

Callbacks can encounter errors on both sides:

- `beforeCheckpoint`: failing to stop workers, failing to finish draining, flush failure, or descriptor close error.
- `afterRestore`: failing to open a file, failing to connect to a server, driver failing to allocate a context, missing permissions, or incompatible native library.

Lifecycle design should follow these principles:

- Close/reopen functions should be idempotent or have clear state so repeated calls do not cause double-close.
- Use a sentinel like `-1` for unopened FDs and update it immediately after closing.
- If opening multiple resources after restore, when one step fails, clean up previously opened resources.
- Do not mark the native subsystem as ready until all required handles have been verified.
- Propagate exceptions to the CRaC callback when an essential resource cannot be restored.
- Log the resource type and OS error code, but do not log secrets or sensitive payloads.
- Have an operational procedure to replace the instance or roll back when restore cannot complete.

An important point: if `beforeCheckpoint` has completed and the checkpoint engine subsequently fails at a later stage, the application should not assume there will be a separate CRaC callback that automatically reopens all resources. It is necessary to coordinate with the application/platform's checkpoint control mechanism to handle the failure of the entire attempt and bring the instance back to a serving state or replace it. The `catch` branch in the callback can only handle errors occurring during the preparation performed by the callback itself.

## 9. Testing Native Resources in a Realistic Environment

Testing must run on the exact JDK, OS, kernel, checkpoint engine, container runtime, and drivers intended for deployment. Tests that only verify the application can restart are not enough.

A test scenario should include:

1. Starting the application and verifying the native library is loaded.
2. Opening representative resource types: files, sockets, event channels, mappings, or device contexts.
3. Generating controlled load so native workers are active.
4. Requesting a checkpoint; verifying the application stops accepting work and waits for workers to reach a safe point.
5. Observing callbacks closing descriptors and stopping native threads.
6. Performing a restore from the checkpoint.
7. Verifying callbacks reopen resources, connect to the right peers, and recreate workers.
8. Sending new requests or work, checking for no stale FDs, double-close, leaks, or writes to the wrong descriptor.
9. Testing close/reconnect failure cases to verify readiness does not transition to accepting.
10. Testing checkpoint failure after preparation to verify the rollback or instance replacement procedure works properly.

Useful observability signals:

| Signal | Purpose |
|---|---|
| FD count before and after restore by type | Detect leaks or leftover descriptors |
| Number of running native workers | Verify workers stop and reinitialize in the right count |
| Native thread stop/join duration | Detect workers not reaching a safe point |
| Reconnect result and OS error code | Distinguish permission, endpoint, driver, or checkpoint engine limit errors |
| Readiness state | Ensure the application only accepts work after the native subsystem is ready |
| Resource init/close count | Detect double-init, double-close, or repeated callback execution |

## 10. Checklist for Integrating JNI and Native Libraries with CRaC

- [ ] Listed all native libraries, FDs, native threads, mutexes, mappings, and device handles used by the application.
- [ ] Clearly identified the owner of each FD; do not accidentally close descriptors managed by the JDK.
- [ ] The library has APIs to stop accepting work and wait for native operations to finish.
- [ ] Native workers stop at a safe point and no longer hold necessary locks before checkpoint.
- [ ] Descriptors not kept across restore are closed and reset to an unopened state.
- [ ] Resources that need to be recreated have clear reopen/reinitialize functions.
- [ ] Do not rely on `JNI_OnLoad` or `JNI_OnUnload` as checkpoint/restore callbacks.
- [ ] `afterRestore` verifies connections, drivers, mappings, and handles before reporting ready.
- [ ] Cleanup and initialization functions can handle partial failures without leaking resources.
- [ ] There is a timeout for stopping native workers and a recovery path on timeout.
- [ ] Tested each FD type on the exact target kernel and checkpoint engine.
- [ ] Tested restore when external services change state or become unreachable.
- [ ] Metrics/logs are in place to detect FD leaks, hung native threads, and post-restore initialization errors.

## 11. Conclusion

JNI and native libraries extend Java's capabilities but also introduce resources outside the lifecycle that the JDK manages automatically. CRaC is only safe when the application clearly understands which resources are process memory, which belong to the kernel, and which are tied to devices or external services.

Use `Resource.beforeCheckpoint(...)` to stop native work at a safe point, wait for workers to finish, and release handles that need to be recreated. Use `Resource.afterRestore(...)` to reopen descriptors, recreate contexts, and start workers after verifying the environment. For each FD type, thread, and native library, test on the exact deployment platform; do not infer restorability merely from the fact that Java data or native pointers remain in memory.

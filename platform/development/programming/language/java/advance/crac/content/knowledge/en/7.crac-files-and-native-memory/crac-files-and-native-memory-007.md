# MappedByteBuffer, Off-Heap Memory, and Build-Specific Limitations

Java provides several ways to store data outside the Java heap: direct byte buffers, native memory regions allocated by JNI, memory-mapped files, and memory regions managed by the Foreign Function & Memory API. These regions are not managed by the Garbage Collector like regular heap objects, yet they still reside in the process's address space or depend on resources external to the process.

This matters for CRaC (Coordinated Restore at Checkpoint). A checkpoint saves the state of a running process, including many native memory regions, but restorability also depends on how the memory region was created, its backing file, the checkpoint engine, the operating system, and the JDK build. An anonymously allocated direct memory region has different characteristics from a MappedByteBuffer region mapping a file on the filesystem.

When designing a CRaC application, distinguish three questions:

1. Where does the data reside: Java heap, native memory, or a file-backed mapping?
2. Who owns the lifecycle of the memory region: Garbage Collector, Arena, file channel, or a native library?
3. After restore, can the memory region continue to be used safely, or must it be released and recreated?

## 1. Heap, direct memory, and memory mapping

### 1.1 Java heap

Regular Java objects are allocated on the heap. The Garbage Collector tracks object reachability and reclaims memory when objects are no longer used.

For example:

~~~java
byte[] data = new byte[1024 * 1024];
~~~

The byte array above resides in the heap. During checkpoint, the heap state is part of the saved process state. After restore, the object and its data continue to exist according to the checkpointed state.

However, if an object holds a reference to an external resource such as a file, socket, or native pointer, the fact that the object still exists does not prove that the external resource is still valid.

### 1.2 Direct buffer and off-heap memory

NIO provides ByteBuffer.allocateDirect() to create a buffer whose data region resides outside the Java heap:

~~~java
ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
~~~

The ByteBuffer object itself is still a Java object on the heap, but its data portion is allocated in native memory. The JVM can use this region to perform I/O more efficiently, especially with native operations that can access that memory region directly.

A direct buffer has two parts to distinguish:

- The Java object managing metadata such as capacity, position, limit, and the reference to the data region.
- The native memory region containing the actual bytes.

The Garbage Collector sees the wrapper object. The JDK's cleanup mechanism can release the native region when the buffer is no longer referenced and the cleaner runs. However, ByteBuffer does not provide a public close() method for the application to deterministically release direct memory.

Direct memory is not an independent data store outside the process. This memory region belongs to the process's address space, so the checkpoint engine may have to save those memory pages along with other memory regions. Even so, native handles or external structures that a library uses to manage the memory region still need to be considered separately.

### 1.3 File-backed memory mapping

MappedByteBuffer is a direct byte buffer representing a region of a file mapped into the process's address space. Java creates the mapping via FileChannel.map().

~~~java
try (FileChannel channel = FileChannel.open(
        Path.of("records.dat"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {

    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_WRITE,
            0,
            1024 * 1024);

    mapped.putInt(0, 42);
    mapped.force();
}
~~~

Data in MappedByteBuffer is accessed like memory, but the memory region has a relationship with a file on the filesystem. The operating system is responsible for mapping file pages into the process's address space.

Closing the FileChannel does not mean the mapping has been destroyed. According to the MappedByteBuffer contract, the mapping remains valid until the buffer is reclaimed by the Garbage Collector. Therefore, MappedByteBuffer has a different lifecycle from the FileChannel used to create it.

A file-backed mapping depends on:

- The backing file still existing and being accessible.
- Read/write permissions matching the mapping mode.
- The file not being replaced or modified in a way that corrupts application state.
- The operating system and checkpoint engine being able to restore that type of mapping.
- Modified data pages being synchronized as required by the application.

### 1.4 Comparing memory region types

| Memory region type | Where data is stored | Typical lifecycle management | Points to note at checkpoint |
|---|---|---|---|
| byte[] or heap object | Java heap | Garbage Collector | Object state is saved in the image |
| ByteBuffer.allocateDirect() | Anonymous native memory | Cleaner/GC | Native region may be saved as process memory; wrapper and native library must remain consistent |
| MappedByteBuffer | File-backed mapping | Mapping typically persists until the buffer is GC'd | Backing file and mapping must be compatible upon restore |
| MemorySegment.allocateNative() | Native memory | Arena | Arena can be closed deterministically before checkpoint and reallocated after restore |
| File-mapped MemorySegment | File-backed mapping | Arena | Close Arena to release mapping and remap after restore |
| Native allocation via JNI | Native memory or OS resource | Native library | Requires lifecycle hooks and library-specific policies |

Do not lump all of these types together under a single generic concept of off-heap and assume they share the same checkpoint behavior. Direct allocations, mappings, and native handles have different semantics.

## 2. How does MappedByteBuffer work?

### 2.1 FileChannel.map()

FileChannel.map() creates a memory region associated with a portion of a file. Parameters include:

- MapMode: READ_ONLY, READ_WRITE, or PRIVATE mode.
- Position: starting offset in the file.
- Size: number of bytes to map.

The returned region can be read or written through ByteBuffer operations.

~~~java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0,
        fileSize);
~~~

With READ_ONLY, the application only reads the mapping content. With READ_WRITE, changes in the mapping can be written back to the file. With PRIVATE, changes create a private copy with copy-on-write semantics and are not treated as updates to the shared file.

A mapping is not a regular Java array copy. The operating system may load pages from the file as the application accesses them. An untouched page may not yet be in physical RAM.

### 2.2 Page faults and physical memory

When the application accesses an address in the mapped region whose corresponding page has not yet been loaded into RAM, the CPU may raise a page fault. The kernel handles the fault and loads the required page from the file or backing store.

Therefore:

- The mapping size can be larger than the amount of data currently resident in RAM.
- Creating a mapping does not mean the entire file has been read.
- First access may trigger I/O and increase latency.
- load() can request the operating system to load pages, but this is best effort.
- isLoaded() is only a hint about whether pages are likely resident, not a guarantee.

load() can be used during warm-up to reduce later page faults, but this operation can generate significant I/O and memory pressure. At checkpoint, having called load() does not replace the requirement to verify the backing file and mapping consistency.

### 2.3 Writing data and force()

With a READ_WRITE mapping, writing to the buffer modifies the mapped memory pages. The operating system may write dirty pages back to the file according to its own policy. If the application needs to actively request synchronization, call force():

~~~java
mapped.putLong(128, 9001L);
mapped.force();
~~~

force() requests that changes in the mapped region be written to the storage device. According to the API contract, for a file on a local storage device, when force() returns, changes made since the mapping was created or since the last force() call have been written to the device.

force() does not unmap the mapping and does not close the file channel. Nor does it turn the file into immutable data. Another process can still modify the file, and the semantics of concurrent modifications depend on the operating system.

If the checkpoint needs to save a consistent file state, define the order clearly:

1. Stop threads writing to the mapping.
2. Complete write operations.
3. Call force() when content synchronization is needed.
4. Save business metadata such as version, offset, or checksum.
5. Release the mapping via a supported mechanism.
6. Create the checkpoint.

### 2.4 Mapping and FileChannel have separate lifecycles

The following code closes the channel upon exiting the try block:

~~~java
MappedByteBuffer mapped;

try (FileChannel channel = FileChannel.open(
        Path.of("records.dat"),
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    mapped = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, 4096);
}

// The channel is closed, but the mapping is still valid.
int value = mapped.getInt(0);
~~~

This is intentional behavior of the API. The mapping has its own lifecycle and continues to exist after the channel closes.

This is useful in normal applications, but creates a problem for checkpointing: simply closing the FileChannel in beforeCheckpoint does not necessarily release the mapping. The file mapping may still remain in the process's virtual memory area and depend on the backing file at restore.

## 3. Impact of MappedByteBuffer on CRaC

CRaC creates an image of the process state and restores the process from that image. The checkpoint engine must handle not only the heap, but also memory regions in the address space, descriptors, and related resources.

### 3.1 A mapping is a process VMA

On Linux, a memory mapping is represented in the process's virtual address space. Mapped regions can be viewed via:

~~~bash
cat /proc/<PID>/maps
~~~

Or view more detailed information:

~~~bash
cat /proc/<PID>/smaps
~~~

A file-backed mapping typically displays the backing file path, offset, and access permissions. An anonymous mapping does not have a backing file in the same way.

The checkpoint engine may need to record VMA information and recreate the mapping at restore. For file-backed mappings, the engine may need to reopen or verify the backing file. A checkpoint image is not a full copy of the external filesystem.

### 3.2 Backing file may change between checkpoint and restore

Suppose the application maps the file /data/index.bin. After checkpoint, the file may be:

- Deleted.
- Renamed or replaced with another file.
- Resized.
- Modified in content.
- Remounted or have its access permissions changed.
- No longer mounted at the old path in a new container.

If restore requires the backing file but the file is inaccessible or incompatible, the restore process may fail. Some checkpoint engines may report a native error while the Java stack trace only indicates that restore failed at a general level.

Do not assume that a file-backed mapping will automatically carry an independent copy of the file into the checkpoint image. Manage the backing file as an external dependency: ensure it exists, has appropriate permissions, and retains the correct version in the restore environment.

### 3.3 Mapping remains alive even though channel is closed

A common mistake is closing the FileChannel in a callback and assuming the resource has been released. If the MappedByteBuffer is still referenced, the mapping may still remain valid.

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {
    channel.close();
    channel = null;
    // mappedBuffer is still referenced and may keep the mapping.
}
~~~

Setting channel to null does not affect the mapping represented by MappedByteBuffer. Setting mappedBuffer to null also does not guarantee the mapping is unmapped immediately, because reclamation depends on the Garbage Collector.

System.gc() is only a GC request, not a guaranteed unmap API. Relying on GC to release mappings right before checkpoint can cause non-deterministic timing behavior.

### 3.4 File descriptor and memory mapping are two different things

At the operating system level, an established mapping can continue to exist after the initial descriptor used for mmap() is closed, because the kernel has created a VMA referencing the file. However, the JDK implementation may hold an internal descriptor or a duplicated descriptor in the mapping/cleaner to manage the lifecycle. Therefore, closing the FileChannel does not make the mapping disappear, and one should not infer the internal FD count solely from the descriptors opened by the application.

Consequently:

- Checking the number of open FDs does not necessarily detect all remaining mappings.
- Closing a channel does not necessarily release the mapped region.
- A mapping can still depend on the backing file during restore.
- Resource policies for file descriptors do not automatically manage all VMAs.
- Both /proc/PID/maps and /proc/PID/smaps must be inspected when investigating.

This explains why an application may no longer have a file descriptor for a file, yet restore still fails when the checkpoint engine needs to access the mapped file.

## 4. Is off-heap memory saved in the checkpoint?

It is necessary to distinguish native memory belonging to the process's address space from resources external to the process.

### 4.1 Process-owned native memory

DirectByteBuffer, memory allocated with malloc, or anonymous mapping regions typically reside within the process's address space. The checkpoint engine can save memory pages belonging to the process, including regions outside the Java heap.

Therefore, off-heap data can be preserved in the checkpoint image. This does not mean every native resource is automatically restored.

For example:

- A byte array allocated by a native allocator is a memory region.
- A pointer to that memory region is an address within the process.
- A file descriptor is a handle managed by the kernel.
- A socket is communication state jointly managed by the kernel and the peer.
- A GPU context or device handle may depend on the driver and device.

A checkpoint engine handling memory pages does not mean it can recreate every kernel, device, or remote service state.

### 4.2 Native pointers and JNI libraries

A JNI library may hold pointers to native regions, structs, thread-local data, or handles managed by the library. If the checkpoint engine restores memory regions at the required addresses, pointers may still point to those regions in some environments. However, correctness also depends on:

- The allocator and metadata managing the memory region.
- Native threads and TLS.
- File descriptors or sockets held by the library.
- Callbacks or signal handlers registered by the library.
- Drivers or devices used by the library.
- ABI, CPU architecture, and library version in the restore environment.

Do not design an application based on the assumption that every native pointer can be safely reused. Native libraries need explicit checkpoint/restore guidance or support.

### 4.3 DirectByteBuffer and memory limits

DirectByteBuffer uses native memory. This capacity is not counted as Java heap, but still consumes RAM and can increase the checkpoint image size.

Some related parameters and tools:

| Mechanism | Effect | Limitation |
|---|---|---|
| -Xmx | Limits maximum Java heap | Not a limit on total native memory |
| -XX:MaxDirectMemorySize | Limits NIO direct-buffer allocations as accounted by the JVM | Not a limit on total process native memory, JNI/malloc, or mappings created directly by native code; mapped buffer accounting must be checked against the JDK implementation |
| BufferPoolMXBean | Observes direct and mapped buffer pools | Does not replace tools measuring RSS and overall native memory |
| Native Memory Tracking | Tracks many native allocation categories managed by HotSpot | Not guaranteed to record every allocation from third-party libraries |
| /proc/PID/smaps_rollup | Summarizes process memory mappings and RSS/PSS on Linux | OS-level metrics, not fully categorized by Java objects |

Do not set MaxDirectMemorySize to the entire container RAM budget. The JVM also needs heap, metaspace, code cache, thread stacks, GC structures, and other native allocations. The checkpoint engine also needs resources to create and restore the image.

### 4.4 Checkpoint image size

The checkpoint image reflects the memory state of the process and may include many native regions. Image size does not necessarily equal Xmx because the heap may not be fully used, zero pages may be optimized, or memory regions may be compressed or directly mapped depending on the engine.

An application using many direct buffers or native memory can produce a large image even with a relatively small heap. An application mapping large files can also create many VMAs and affect restore time, depending on how the engine handles file-backed pages.

Measure image size, RSS/PSS, checkpoint time, and restore time under realistic workloads. Do not use Xmx as a proxy for total memory to be checkpointed.

## 5. MappedByteBuffer lifecycle and the unmap problem

### 5.1 No public close() on MappedByteBuffer

MappedByteBuffer does not implement AutoCloseable and has no public close() method to deterministically unmap a mapping.

The mapping is maintained until the buffer is reclaimed by the Garbage Collector. This means an application cannot rely on a standard close call to ensure a file mapping has disappeared before checkpoint.

Some JDKs have internal APIs to force unmapping, but these APIs are not part of the stable Java SE contract. Calling internal APIs via reflection or Unsafe can depend on module access, JDK version, and implementation. It should not be treated as a portable solution for CRaC.

### 5.2 Why is setting the buffer to null not enough?

~~~java
mappedBuffer = null;
System.gc();
~~~

The code above only drops the reference and requests the Garbage Collector to run. GC might not run yet, might choose not to reclaim the buffer at that time, or the cleaner might not execute immediately.

If checkpoint is invoked immediately afterward, the mapping may still exist. This is why a deterministic lifetime management mechanism is needed when the application must release mappings before checkpoint.

### 5.3 Using MemorySegment and Arena on newer JDKs

The Foreign Function & Memory API provides MemorySegment and Arena to manage native memory regions with an explicit lifetime. This API was finalized in JDK 22. In older JDKs, preview/incubator versions may have different signatures or rules.

FileChannel has a map() overload that takes an Arena and returns a MemorySegment. When the Arena closes, the mapping associated with the Arena is released.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.nio.channels.FileChannel;

MemorySegment mapped;

try (Arena arena = Arena.ofConfined()) {
    mapped = channel.map(
            FileChannel.MapMode.READ_ONLY,
            0,
            fileSize,
            arena);

    byte first = mapped.get(
            java.lang.foreign.ValueLayout.JAVA_BYTE, 0);
}
~~~

In the example above, mapped can only be accessed within the lifetime of the Arena. After exiting the try block, the Arena closes and the segment is no longer valid.

If the application needs to keep the mapping throughout the service lifecycle, hold the Arena in a resource that can close it in beforeCheckpoint and create a new Arena/mapping in afterRestore.

Arena.ofConfined() is suitable when the memory region is accessed only from the owning thread. If multiple threads need access, Arena.ofShared() may be needed, and closing the Arena must be synchronized with threads using the segment.

### 5.4 MemorySegment allocating native memory

Arena can also allocate native memory regions:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment nativeMemory = arena.allocate(1024 * 1024);

    nativeMemory.set(
            java.lang.foreign.ValueLayout.JAVA_INT,
            0,
            12345);
}
~~~

When the Arena closes, the native memory region is released according to the Arena's lifetime. This is a more deterministic management approach compared to direct buffers relying on a cleaner.

If data needs to survive across checkpoint, there are two options:

- Keep the memory region in the image if the build and engine support that workload, while ensuring all native dependencies remain valid.
- Close the Arena before checkpoint, save necessary data to a file or business state, and then reallocate and reload the memory region after restore.

Which option is suitable depends on data size, restore time, reproducibility, and consistency requirements.

## 6. Managing mappings with CRaC Resource

A Resource can own the FileChannel, Arena, and MemorySegment. Before checkpoint, it stops accessing the mapping, synchronizes necessary data, and closes the Arena and channel. After restore, it reopens the file, creates a new Arena, and creates a new mapping.

The example below illustrates a read-only file mapping:

~~~java
import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class MappedFileResource implements Resource, AutoCloseable {

    private final Path path;
    private final long offset;
    private final long size;

    private FileChannel channel;
    private Arena arena;
    private MemorySegment segment;

    public MappedFileResource(Path path, long offset, long size)
            throws IOException {
        this.path = path;
        this.offset = offset;
        this.size = size;
        openMapping();
        Core.getGlobalContext().register(this);
    }

    private synchronized void openMapping() throws IOException {
        FileChannel newChannel = FileChannel.open(
                path, StandardOpenOption.READ);
        Arena newArena = Arena.ofShared();

        try {
            MemorySegment newSegment = newChannel.map(
                    FileChannel.MapMode.READ_ONLY,
                    offset,
                    size,
                    newArena);

            channel = newChannel;
            arena = newArena;
            segment = newSegment;
        } catch (Throwable failure) {
            try {
                newArena.close();
            } catch (Throwable closeFailure) {
                failure.addSuppressed(closeFailure);
            }

            try {
                newChannel.close();
            } catch (Throwable closeFailure) {
                failure.addSuppressed(closeFailure);
            }

            throw failure;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        segment = null;

        if (arena != null) {
            arena.close();
            arena = null;
        }

        if (channel != null) {
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        openMapping();
    }

    @Override
    public synchronized void close() throws Exception {
        segment = null;

        if (arena != null) {
            arena.close();
            arena = null;
        }

        if (channel != null) {
            channel.close();
            channel = null;
        }
    }
}
~~~

The example uses the stable FFM API from JDK 22 and above and the org.crac package. If using jdk.crac, replace the CRaC imports according to the JDK version.

Some design points:

- The Resource is the sole owner of the mapping and Arena.
- Before closing the Arena, the application must ensure no thread is still accessing the segment.
- The channel is reopened from the path after restore; do not store the FD number.
- If the file changes between checkpoint and restore, the application needs to verify the version or checksum before allowing access.
- If openMapping() fails, the exception must be propagated to CRaC so restore is not considered successful.

The code snippet illustrates cleanup when mapping creation fails. In production, a specific exception type and file verification policy can be added to distinguish I/O errors, Arena errors, and incompatible data errors.

### 6.1 Writable mappings

If the mapping is opened in READ_WRITE mode, the beforeCheckpoint callback needs to stop writers and synchronize data before closing the Arena:

~~~java
@Override
public synchronized void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    stopWritersAndWait();

    if (segment != null) {
        // Perform the data synchronization step according to the API and
        // semantics of the mapping in use.
    }

    closeMapping();
}
~~~

With MappedByteBuffer, force() can be called before dropping the reference. With MemorySegment mappings, use the file synchronization mechanism appropriate for the JDK API being used; do not assume MemorySegment has the same force() method as MappedByteBuffer.

If the data is critical business data, clearly define that checkpoint is only allowed to occur after a commit point. Closing a mapping does not replace the application's transaction or data-writing protocol.

## 7. Using MappedByteBuffer in CRaC applications

If the application already uses MappedByteBuffer and cannot yet migrate to MemorySegment, determine whether the mapping can be kept across checkpoint in the exact target build and engine.

### 7.1 Inventory all mappings

Find call sites of:

- FileChannel.map().
- MappedByteBuffer or wrapper classes holding mappings.
- Indexing libraries, embedded databases, caches, or search engines.
- Native libraries calling mmap() directly.
- Mappings created implicitly by frameworks or libraries.

Do not only search for FileChannel.open(). A mapping may be created from another class or from native code.

### 7.2 Identify backing files

For each mapping, record:

- Path or file identity.
- Offset and size.
- READ_ONLY, READ_WRITE, or PRIVATE.
- Whether the file is on a local filesystem, network filesystem, volume, or tmpfs.
- Who has permission to modify or replace the file.
- Whether the mapping is used concurrently by another process.
- Whether the application needs to call force() before checkpoint.

If restore runs on a different host, the backing file must be provided at the right location and be compatible with the image. Do not rely on absolute paths from the source host if the deployment does not guarantee identical mounts.

### 7.3 Determine how to unmap

With classic MappedByteBuffer, there is no public and deterministic unmap API. If the mapping must be released before checkpoint, consider:

- Migrating to MemorySegment + Arena on a supported JDK.
- Using a library with an explicit mapping lifetime management API that has been verified with the JDK/CRaC build.
- Replacing the mapping with FileChannel or block I/O if performance permits.
- Keeping the mapping across checkpoint only if the engine and deployment environment explicitly support it and it has been tested.

Do not rely on System.gc() as a guaranteed unmap step.

### 7.4 Test actual restore

Checkpoint and restore on the exact target filesystem, container, kernel, and build. Test backing file cases:

- Intact.
- Modified content.
- Replaced.
- Missing.
- Insufficient permissions.
- Mounted at a different path.

A checkpoint that succeeds on a development machine does not prove that the mapping can restore on a production host.

## 8. Limitations by JDK, CRaC build, and checkpoint engine

CRaC is not a feature with the same level of support across all JDKs. APIs, engines, operating systems, CPU architectures, and build options can vary. When evaluating MappedByteBuffer and off-heap memory, check at least four layers.

### 8.1 JDK with CRaC integration

The CRaC API is not part of the Java SE specification. Some JDK builds integrate the jdk.crac package; the org.crac compatibility library allows compiling the application and forwarding to the implementation if the runtime supports it.

An application running with org.crac on a regular JDK does not mean that runtime can create a real checkpoint. A dummy implementation may allow registering a Resource, but the checkpoint operation will fail because there is no engine.

Therefore, test the actual runtime, not just successful compilation.

### 8.2 Foreign Function & Memory API version

The Foreign Function & Memory API has a history of incubator/preview releases in earlier JDKs and was finalized in JDK 22.

| JDK line | Approach |
|---|---|
| JDK 17 | MappedByteBuffer and DirectByteBuffer are the common NIO APIs; FFM is not yet a stable API in Java SE |
| JDK 21 | FFM is in preview; signatures and usage depend on the preview version |
| JDK 22 and above | FFM is a standard API; Arena and MemorySegment provide explicit lifetime for native memory and mapped files |
| Vendor JDK build with CRaC | Must separately check CRaC integration, API package, engine, and supported platforms |

You cannot look only at the Java version number and conclude checkpointing is possible. Use the exact build with CRaC and check that JDK's FFM version.

### 8.3 Differences between CRIU and Warp

The checkpoint engine is the component that writes and restores process state. Engines can differ in how they save memory pages, handle file mappings, store images, and enforce environment limits.

CRIU is based on Linux checkpoint/restore. It collects VMA, file descriptor, and process resource information through operating system interfaces. At restore, it needs to recreate the mappings and corresponding resources.

Warp is another engine provided in some Azul Zulu/Zing builds. How it saves and loads memory images can differ from CRIU. Engine documentation describes direct mapping modes, memory loading, and optimizations specific to the build type.

Do not assume a mapping that works with CRIU will behave identically with Warp, or vice versa. Test on the exact engine that will be deployed.

### 8.4 Differences between real Linux and simulation engine

Some builds provide simengine on Windows, macOS, and Linux for testing callbacks. The simulation engine invokes beforeCheckpoint and afterRestore within the same process, but does not create an actual process image.

Therefore, simengine is useful for testing resource close/open logic and callback repeatability. It does not prove that:

- Native memory is saved and loaded properly.
- File-backed mappings are recreated.
- Backing files are accessible on another host.
- The kernel supports the restore operations.
- The checkpoint image can be opened by a production engine.

Actual checkpoint/restore testing on Linux with the target engine is required.

### 8.5 Decision table by build

| Condition | What to verify |
|---|---|
| Regular JDK, no CRaC integration | No real checkpoint engine; compatibility API can only be used for code or test stubs |
| JDK with CRaC API but simulation engine | Callbacks can run; do not draw conclusions about VMAs, native memory, or file mappings |
| CRaC build using CRIU | Check kernel, permissions, VMAs, backing files, and mapping recreation capability |
| CRaC build using Warp | Check mapping support, backing file access permissions, image mode, and engine options |
| Linux x86_64 or ARM64 | Check the exact architecture and vendor build version |
| Windows or macOS | Can develop or simulate depending on the build; does not have a real checkpoint engine by default |
| Native library or driver | Confirm the library supports checkpoint/restore and has the right ABI/driver on the restore host |

This is a classification for planning testing, not a support commitment matrix for every vendor. Supported platforms and engines change across releases. Always check the documentation of the exact vendor, JDK build, and engine in use.

## 9. Operating system and environment limitations

### 9.1 VMAs and number of memory mappings

Linux manages a process's virtual memory areas (VMAs). An application that creates many small mappings can consume many VMAs, even when total data size is small.

The host's vm.max_map_count limit can affect applications that create very many mappings. Some runtimes and engines need additional VMAs during restore. If you encounter mapping creation errors, check:

~~~bash
sysctl vm.max_map_count
cat /proc/<PID>/maps
~~~

Increasing vm.max_map_count is a host-level change and should only be done according to the build/engine operational documentation. For example, Azul Zing documentation recommends increasing the VMA limit in some deployments; specific values should not be applied blindly to every system.

### 9.2 Backing file access permissions

Restore may need to access a mapping's backing file. If the new process's permissions differ, the mount namespace differs, or the file is no longer accessible, the engine may report an error.

One case described in Azul documentation is Warp failing to open a file mapped by the Name Service Cache Daemon due to insufficient access permissions. This shows that mappings created by the system or libraries can also affect restore, even if the application does not directly call FileChannel.map().

### 9.3 Filesystems and containers

Test on the actual filesystem type: ext4, XFS, tmpfs, overlay filesystem, NFS, or cloud platform volumes. Filesystems have different semantics and limits regarding mappings, data synchronization, and access permissions.

In containers, check:

- Mount namespaces and file paths.
- UID/GID and permissions.
- Whether volumes exist at both source and target.
- Whether files are replaced by init containers or sidecars.
- The host's VMA limit.
- Whether the engine has the required capabilities or permissions.

Do not create a checkpoint in a container with a mapping to a temporary file and then restore in another container without ensuring that file is provided again.

### 9.4 CPU, architecture, and memory configuration

A checkpoint image can depend on CPU features, architecture, and JVM configuration at the time the image was created. Restoring on a machine lacking a required CPU feature may fail before the application reaches the afterRestore callback.

Heap configuration and some internal JVM structures may also be fixed to the checkpoint environment. Restoring on a machine with fewer CPUs or less memory can cause performance or stability issues.

For off-heap memory, include both native memory usage and the number of mappings in the target host's resource budget. Checking -Xmx alone is not enough.

## 10. Monitoring direct and mapped memory

When an application encounters memory errors or slow restore, collect data from both the JVM and the operating system.

### 10.1 BufferPoolMXBean

The JVM provides BufferPoolMXBean to observe buffer pools such as direct and mapped.

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {

    System.out.printf(
            "%s: count=%d, memoryUsed=%d, totalCapacity=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed(),
            pool.getTotalCapacity());
}
~~~

Useful values:

- count: number of buffers in the pool.
- memoryUsed: estimated memory currently in use.
- totalCapacity: total capacity of the buffers.

These are metrics by JVM buffer pool, not a complete map of all native allocations. A native library calling malloc or mmap directly may not appear in these metrics.

### 10.2 Native Memory Tracking

Native Memory Tracking can be enabled when starting the JVM:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Then query:

~~~bash
jcmd <PID> VM.native_memory summary
~~~

NMT helps observe many native memory categories managed by HotSpot. It has overhead and does not necessarily record all allocations from every third-party native library.

### 10.3 Linux procfs

Useful files:

~~~bash
cat /proc/<PID>/maps
cat /proc/<PID>/smaps_rollup
cat /proc/<PID>/status
~~~

- maps shows address ranges and backing files.
- smaps_rollup provides aggregate statistics such as RSS/PSS.
- status shows memory metrics and process state.

Can be combined with pmap:

~~~bash
pmap -x <PID>
~~~

When comparing before and after restore, use the same metric types and the same load conditions. Increasing RSS does not necessarily mean direct buffers are leaking; file-mapped pages may be loaded gradually as the application accesses them.

## 11. Designing a checkpoint strategy for off-heap

There are three main strategies, depending on data type and performance requirements.

### 11.1 Keep memory regions in the image

Suitable when the native memory region belongs to the process, the build and engine support it, it does not depend on an external handle outside the process that needs recreation, and the data can continue to be used safely after restore.

For example: an immutable lookup table allocated in native memory, holding no pointers to files or devices and not depending on external native library state.

Measure image size and restore time. Large memory regions can make the image large, costing I/O or load time.

### 11.2 Close and recreate mappings

Suitable when the mapping depends on a backing file that may change or needs to be re-verified after restore.

Before checkpoint:

- Stop threads using the mapping.
- Synchronize data if needed.
- Save metadata and version.
- Close the Arena if using a MemorySegment mapping.
- Close channels and release other handles.

After restore:

- Open the backing file.
- Verify file identity/version.
- Create a new mapping.
- Reinitialize dependent structures.
- Allow thread access after verification succeeds.

### 11.3 Persist data, rebuild native cache

Suitable for caches or indexes that can be rebuilt from source data. Before checkpoint, all native cache regions can be closed, keeping only necessary metadata. After restore, reload or rebuild the cache according to a bounded strategy.

This approach reduces dependency on old native allocators and file mappings, but can increase restore time. Measure the cost of rebuilding versus the cost of keeping the memory image.

### 11.4 Strategy comparison

| Strategy | Advantage | Trade-off |
|---|---|---|
| Keep off-heap in image | Can preserve warmed-up data and reduce initialization work | Large image; depends on engine and native state |
| Close then recreate | Controls lifecycle, verifies new files/dependencies | Requires recreation time and thread synchronization |
| Persist source data then rebuild | Reduces dependency on old native state; easier to control consistency | Takes time to load or rebuild cache |

There is no single right strategy for every application. The decision is based on data reproducibility, consistency requirements, off-heap size, and actual engine support.

## 12. Common mistakes

### Closing FileChannel but forgetting the mapping

MappedByteBuffer has its own lifecycle. Closing the channel does not unmap the buffer. Check live mappings and backing files at restore.

### Using System.gc() to force unmapping

GC is not guaranteed to run immediately. Do not use it as a synchronization step before checkpoint.

### Confusing off-heap with data outside the process

Native memory still belongs to the process address space and can be checkpointed. File descriptors, sockets, device handles, and remote service state are different resources.

### Thinking a file mapping is closed along with the file descriptor

A mapping can still exist after the descriptor that created it is closed. Check VMAs, not just FDs.

### Thinking the checkpoint image carries the backing file

A file-backed mapping depends on the filesystem. Ensure the file exists, has the right version, and is accessible at restore.

### Using MappedByteBuffer for large regions without considering ByteBuffer limits

ByteBuffer uses int indices. For data larger than the capacity limit, split the mapping into multiple segments or consider the long-sized MemorySegment API on an appropriate JDK.

### Using MemorySegment after the Arena has closed

The segment's lifetime is tied to the Arena. Accessing after close will fail. Synchronize threads before closing the Arena.

### Using a confined Arena from multiple threads

Arena.ofConfined() restricts access to the owning thread. If the segment is shared, choose an appropriate Arena and manage concurrency.

### Observing only the Java heap

The heap can remain stable while direct memory, mapped memory, or native allocations grow sharply. Monitor BufferPoolMXBean, NMT, and procfs metrics as well.

### Using simulation engine to conclude mappings are restored

Simulation engine tests callbacks but does not create a real image. Must test on the target build, engine, kernel, and filesystem.

## 13. Implementation workflow

When preparing an application using MappedByteBuffer or off-heap memory for CRaC, you can follow these steps:

**Step 1 — Inventory memory regions.** Find direct buffers, mapped buffers, MemorySegment, JNI allocations, native libraries, and any mmap() calls.

**Step 2 — Classify backing.** Identify anonymous regions, file-backed, shared mappings, or driver-managed resources. Record owners and dependencies.

**Step 3 — Choose lifetime.** Decide which memory regions to keep across checkpoint, which to close and recreate, and which can be rebuilt from durable data.

**Step 4 — Identify appropriate APIs.** On newer JDKs, consider MemorySegment and Arena to manage native memory/mappings with deterministic lifetimes. For older MappedByteBuffer, do not assume immediate unmapping is possible via a public API.

**Step 5 — Write Resource callbacks.** Stop threads using the memory region, flush necessary data, close the Arena or native resources, and reopen after restore. Propagate errors outward when cleanup or recreation fails.

**Step 6 — Verify build and engine.** Confirm JDK vendor, version, OS, architecture, CRaC engine, filesystem, and VMA limits.

**Step 7 — Measure memory.** Collect direct/mapped buffer pools, NMT, RSS/PSS, VMA count, image size, and restore time.

**Step 8 — Test changing environments.** Test replaced files, missing permissions, different mounts, unavailable native dependencies, and restoring on a different host.

**Step 9 — Open traffic only after verification.** After restore, verify mappings, file versions, and native dependencies before the application accepts requests.

## References

- [Java API — MappedByteBuffer](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/MappedByteBuffer.html): mapping lifetime, load(), isLoaded(), and force().
- [Java API — FileChannel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/channels/FileChannel.html): mapping files and mapping overloads.
- [Java API — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): lifetime and closing native memory regions.
- [Java API — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): accessing native and file-backed memory regions.
- [CRaC — What CRaC is](https://crac.org/about/about-crac/): checkpoint/restore model and resource coordination requirements.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): builds, platforms, and how to test CRaC in practice.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): differences between CRIU, Warp, and simulation engines.
- [CRaC — Debugging CRaC Failures](https://docs.azul.com/crac/usage/debugging): restore failures related to mapped files and how to investigate.
- [CRaC — Concurrent Memory Loading](https://docs.azul.com/crac/operational/concurrent-memory-loading): how engines load memory images and limitations when using native code.
- [CRaC — Usage Instructions for Azul Zing](https://docs.azul.com/crac/usage/zing-specific): notes on VMA limits and system configuration.
- [CRaC — CRaC API compatibility](https://github.com/CRaC/docs/blob/master/README.md): differences between jdk.crac and org.crac.

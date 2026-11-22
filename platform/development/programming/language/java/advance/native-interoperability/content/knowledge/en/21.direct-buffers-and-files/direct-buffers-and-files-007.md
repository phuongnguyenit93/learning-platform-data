# Distinguishing Shared Memory Between Threads from Shared Memory Between Processes

## 1. At What Level Is "Shared Memory" Shared?

When programming in Java with multiple threads, multiple native workers, or multiple JVM processes, the phrase **shared memory** is very easy to misunderstand. There are two fundamentally different situations:

1. **Intra-process sharing (between threads):** multiple Java threads live in **one JVM process** and can concurrently access a Java object, a `byte[]`, a `ByteBuffer`, or a `MemorySegment` allocated from an arena that allows multiple threads.
2. **Inter-process sharing (IPC):** two OS processes have **separate address spaces**. They can only observe or modify the same data when the OS sets up **the same backing resource** (for example, file-backed memory mapping, POSIX shared-memory object, Windows named file mapping), or when using another IPC mechanism such as a pipe/socket to exchange copies of data.

The key difference is not "whether off-heap is used or not". A `ByteBuffer.allocateDirect` or `Arena.ofShared().allocate(...)` may live outside the Java heap, yet it is still memory owned by **one process**; **it does not automatically become IPC shared memory**.

This lesson belongs to the **Direct Buffers and Files** topic of Java Native Interoperability, using Java 17+ for NIO examples and Java 22+ for the Foreign Function & Memory API (FFM) integration section.

### What You Will Learn

- Identify the boundaries of a **Java thread**, **JVM process**, and **OS virtual address space**.
- Distinguish sharing the **same object/backing bytes** between threads from sharing the **same file-backed pages** between processes.
- Understand why `Arena.ofShared()` is not "shared memory between JVMs".
- Use `FileChannel.map(MapMode.READ_WRITE, ...)` so two Java processes operate on the same file.
- Distinguish `READ_WRITE`, `READ_ONLY`, and `PRIVATE` (copy-on-write).
- Understand the difference between **visibility**, **synchronization**, **atomicity**, and **durability/force**.
- Run the **two threads**, **two JVM processes**, and **FFM mapped MemorySegment** examples yourself.
- Design file sizes, binary layouts, offsets, byte order, mapping lifecycles, and proper locking rules.
- Recognize false assumptions that can cause races, stale reads, data corruption, or native crashes.

## 2. One Diagram, Two Kinds of "Share"

~~~text
CASE A: SAME PROCESS
+-------------------------------------------------------------+
| JVM PROCESS P                                               |
|                                                             |
|   Thread A -----------------+                               |
|                             |                               |
|                             v                               |
|                       [ ByteBuffer ]                        |
|                       [ MemorySegment ]                     |
|                             ^                               |
|   Thread B -----------------+                               |
|                                                             |
|  One virtual address space, same Java heap and native memory|
+-------------------------------------------------------------+


CASE B: DIFFERENT PROCESSES
+-------------------------+   +------------------------------+
| JVM PROCESS P1          |   | JVM PROCESS P2               |
| Thread A                |   | Thread B                     |
| Virtual address space 1 |   | Virtual address space 2      |
|                         |   |                              |
| Mapped view M1 ---------+---+--------- Mapped view M2       |
+-------------------------+   +------------------------------+
                 \                 /
                  \               /
                   v             v
                 [OS-backed shared resource]
                 [same file, offset, length]
~~~

In **Case A**, you can share the **Java reference** itself or the **same off-heap region** when within the same process. In **Case B**, you cannot pass a Java reference and expect another JVM to dereference it; each process must create **its own mapping** to a shared resource recognized by the OS.

The two mapped views in P1 and P2 **do not have to have the same virtual address**. The operating system can map the same backing bytes to different addresses due to ASLR, virtual memory layout, and process state. Do not exchange a raw pointer as a `long` and use it in another JVM.

### 2.1. "Same Physical Memory" Also Needs Careful Understanding

A memory-mapped file is managed by the OS through the page cache and virtual-memory mapping mechanisms. When two processes map the same file, the OS may share backing pages/caches or an equivalent mechanism. This **does not mean** Java guarantees that every write from P1 appears **immediately** in P2's `MappedByteBuffer`. The `FileChannel.map`/`MappedByteBuffer` Javadoc explicitly states that **whether changes in another program's view are visible, and when, is OS-dependent**.

Therefore, if an application needs a reliable IPC protocol, you need to add **synchronization/protocol** and verify assumptions about the OS/filesystem; simply pointing to the same file path is not enough.

## 3. Decision Comparison Table

| Criterion | Sharing Between Threads | Sharing Between Processes |
| --- | --- | --- |
| Number of processes | **One** | **Two or more** |
| JVM heap | Same JVM heap | Each JVM heap is independent |
| Java object reference | Can reference the same object | **Not** directly |
| `static` field | Same copy within one class loader of that JVM | Each JVM/process has its own state |
| `byte[]` / `ByteBuffer.allocate` | Can be shared between threads | Not automatically shared |
| `ByteBuffer.allocateDirect` | Can be shared between threads of the same process | Not automatically shared |
| `Arena.ofShared().allocate` (JDK 22+) | Can be accessed from multiple threads of the same process | Does not automatically create IPC backing |
| `FileChannel.map(READ_WRITE)` | Threads can use the same mapping | Two processes can map the same file, with OS-dependent visibility |
| POSIX `shm_open + mmap(MAP_SHARED)` | Can be used | Native IPC shared memory when sharing the same named object |
| Windows `CreateFileMapping/MapViewOfFile` | Can be used | Native IPC shared memory when sharing the same mapping object |
| Synchronization | Java Memory Model: `volatile`, locks, atomics, `Thread.join`... | OS-level protocol: interprocess locks, semaphores, pipes, sockets, process completion... |
| Cleanup | GC, `Arena.close`, native allocator ownership | Beyond process-local cleanup, must also manage the backing resource/file/name |
| Risks | Data race, visibility, premature close | All of the above risks **plus** stale views, file truncation, ABI/schema, and process crash |

A file memory-mapped in the **same JVM** both has the property that "multiple threads can share the mapping" and can be mapped by another process. You do not need to pick an absolute category for a **technology**; ask **who accesses it and which backing resource is actually shared**.

## 4. Why Can Threads in the Same JVM Share Objects?

Each Java thread has its own call stack and execution state, but threads in the same JVM can hold references to **the same Java object**. For example:

~~~java
int[] numbers = { 1, 2, 3 };

Thread worker = new Thread(() -> {
    numbers[0] = 42; // same array object as the thread that created it
});
worker.start();
worker.join();

System.out.println(numbers[0]); // 42
~~~

This is a **snippet inside a method** that handles or declares `InterruptedException`, not a standalone program file.

`worker.join()` is a synchronization operation: when main returns from a successful `join`, the worker's actions prior to termination are properly visible according to the *happens-before* relationship in the Java Memory Model (JMM). In the example, only the worker writes and then main reads **after join**, so there are no concurrent updates.

If main reads `numbers[0]` while the worker is writing and there is **no** synchronization, you cannot rely on "same object" to guarantee consistency. Sharing an **address/memory** and sharing **values with proper visibility** are two different things.

### 4.1. Direct ByteBuffer Is Still Memory Belonging to One Process

~~~java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);
~~~

A direct buffer is typically allocated by the JVM off-heap and can assist native I/O by reducing copies. **It is not the name of an OS shared-memory object**, and there is no mechanism where two independent JVMs "calling `allocateDirect(1024)` receive the same 1,024 bytes".

Two calls:

~~~java
// Process P1:
ByteBuffer a = ByteBuffer.allocateDirect(1024);

// Process P2:
ByteBuffer b = ByteBuffer.allocateDirect(1024);
~~~

create two **distinct** process-local allocations. Even if the OS happens to return the same virtual address number (which is not guaranteed), the contents still belong to different address spaces.

### 4.2. ByteBuffer Is Not Automatically Thread-Safe

When two threads share **the same `ByteBuffer` object**, the `position`, `limit`, and `mark` properties are also mutable state. Non-offset methods like `putInt()`/`getInt()` mutate `position`, leading to races in sequential operations.

A simple pattern is to use **absolute access**:

~~~java
buffer.putInt(0, 42);
int x = buffer.getInt(0);
~~~

Or create `duplicate()` / `slice()` for each worker to have **its own cursor state**, while still sharing the same backing bytes. Separating the cursor **does not** automatically synchronize the shared bytes.

## 5. Java 17+ Example 1: Two Threads Sharing a DirectByteBuffer

Standalone file **`ThreadSharedBufferDemo.java`**:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class ThreadSharedBufferDemo {
    private ThreadSharedBufferDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        ByteBuffer shared = ByteBuffer.allocateDirect(Integer.BYTES);
        shared.order(ByteOrder.BIG_ENDIAN);

        // Main prepares data before worker.start().
        shared.putInt(0, 41);

        Thread worker = new Thread(() -> {
            int oldValue = shared.getInt(0);
            shared.putInt(0, oldValue + 1);
        }, "writer");

        worker.start();
        worker.join();

        // Worker has finished; happens-before via join().
        System.out.println("thread shared value=" + shared.getInt(0));
        System.out.println("buffer is direct=" + shared.isDirect());
    }
}
~~~

Compile and run from the directory containing the file using **JDK 17 or later**:

~~~bash
javac ThreadSharedBufferDemo.java
java ThreadSharedBufferDemo
~~~

Stdout:

~~~text
thread shared value=42
buffer is direct=true
~~~

Why is the output deterministic?

1. Main creates **one** direct `ByteBuffer` and writes 41.
2. The worker receives **the same Java reference** to `shared`, reads 41, and writes 42.
3. Main waits for `worker.join()` to finish before reading the result; two threads never modify this field concurrently.
4. `allocateDirect` creates a direct buffer, so `isDirect()` is `true`.

**This demo does not involve two JVMs.** It shows that **off-heap data can be shared between threads of one process**, not an IPC mechanism.

### 5.1. What If `join()` Is Removed?

If main only calls `worker.start()` and immediately reads the value, the timing of worker execution is indeterminate. Main might read 41 or 42; if there are multiple unsynchronized writers, both atomicity and ordering also become issues.

Solutions based on purpose:

- Wait for a worker to finish: `Thread.join()` / `Future.get()` / `CountDownLatch`.
- Need multi-threaded shared mutable state: `synchronized`, `ReentrantLock`, `AtomicInteger`, or `VarHandle` memory-ordering/atomic access modes.
- With a `ByteBuffer`, do not assume `getInt` + `putInt` is an atomic increment.
- If you need to coordinate Java/native threads in the same process, you must understand both the Java Memory Model and the synchronization participated in by native code.

## 6. From Thread to Process: The Address Space Boundary

An OS process has its own virtual address space. When Java runs two commands:

~~~bash
java AppA
java AppB
~~~

the OS normally creates **two different JVM processes**. Even when the two programs use the same class name and the same variable:

~~~java
static int counter = 1;
~~~

they have **two independent copies of `counter`**. When `AppA` increments it to 10, `AppB` does not automatically see 10 just because the class name matches.

`ProcessBuilder` also launches a **child process**, not a new thread in the current JVM:

~~~java
Process child = new ProcessBuilder(
        "java", "AppB").start();
~~~

This is only for illustration; for production, use the proper Java executable, classpath, OS path, and termination conditions.

### 6.1. Java References and Native Pointers Cannot Cross Processes on Their Own

A Java reference is not a global identifier that can be sent as a `long` and dereferenced in another JVM. The same applies to native pointers:

~~~text
P1: virtual address 0x1234 --> page in process P1
P2: virtual address 0x1234 --> different page or unmapped in P2
~~~

For P2 to read the same data as P1, P2 needs an OS mapping to **the same resource** or the data must be transferred via IPC. Each process receives **its own handle/mapping/Java wrapper**.

Rare cases where the operating system and native code can share raw addresses through special techniques are not a portable contract of Java NIO/FFM; avoid designing systems based on virtual address coincidence.

### 6.2. "Same Machine" Does Not Mean "Same Application Memory"

Two JVMs on the same machine share physical RAM managed by the OS, but **private** memory pages are still isolated by virtual memory protection. "The machine has one pool of RAM" does not grant permission to automatically read another process's memory. Only intentionally designed IPC mechanisms grant shared access.

## 7. How Does the OS Create Shared Backing?

There are several options:

- **File-backed mapping:** two processes map **the same file** and **the same offset/length region** in a shareable mode. In standard Java, `FileChannel.map(FileChannel.MapMode.READ_WRITE, ...)` is the common entry point.
- **POSIX shared memory:** native code uses `shm_open` to create/open a named shared-memory object, sets the size with `ftruncate`, and calls `mmap(..., MAP_SHARED, ...)`. It can be integrated with Java via JNI/FFM and follows POSIX permissions/lifetime.
- **Windows named file mapping:** native code uses `CreateFileMapping` / `OpenFileMapping` and `MapViewOfFile`. A named mapping can be opened across multiple processes according to security attributes.
- **Fork-related anonymous mappings:** some OSes allow related processes to share pages from anonymous `mmap(MAP_SHARED)`, but this is not a portable option for two JVMs launched independently by the Java launcher.
- **Non-shared-memory IPC:** pipes, domain sockets, TCP, gRPC, message queues. They transfer **messages/bytes** between processes instead of having both sides read/write a shared region.

**Key takeaway:** shared memory **between processes** requires an **OS backing resource or mechanism that both open/reference**. Java variable names, `Arena` names, classpath paths, or being on the same CPU are not enough.

## 8. FileChannel.map and Mapping Modes

Java's `java.nio.channels.FileChannel` has had a standard API for a long time:

~~~java
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE,
        0L,
        4096L);
~~~

You must open `channel` appropriately, for example with `FileChannel.open(path, READ, WRITE)`, and ensure the file already has an appropriate size before mapping.

### 8.1. Three Different MapModes

| MapMode | Writing from View | Effect on Backing File | Use Cases Supported |
| --- | --- | --- | --- |
| `READ_ONLY` | Cannot modify (`ReadOnlyBufferException`) | Not modified from this view | Readers, shared read-only data |
| `READ_WRITE` | Can modify | Changes are propagated to the file; when and whether they are visible in **another process's** mapping depends on the OS | Shared file-backed updates / IPC with a protocol |
| `PRIVATE` | Copy-on-write, view can be modified | **Does not propagate changes to the file** and does not make private changes visible to other processes | Isolated snapshot/private calculation |

**Key point: `PRIVATE` is not shared write.** If two JVMs map the same file in `PRIVATE` mode and each writes to its view, the changes belong to their private copies and are not published back to the file for the other process to receive.

### 8.2. How Long Does a Buffer Mapping Live?

With the three-parameter API `FileChannel.map(mode, position, size)`, the `MappedByteBuffer` and underlying mapping remain valid until the buffer is garbage-collected according to the API contract. **Closing `FileChannel` does not automatically unmap the created `MappedByteBuffer`.**

This has consequences:

- File descriptors/channels and memory mappings have **different** lifetimes.
- You should not rely on `try (FileChannel ...)` to assert that the mapping has definitely been unmapped immediately.
- On Windows, a file currently mapped may not be deletable/renameable when you want; cleanup behavior depends on the OS and runtime.
- If you need **deterministic** mapping lifetime management, see `FileChannel.map(..., Arena)` in JDK 22+ in section 12.
- Do not truncate/delete a file that still has mappings in other processes without a protocol; the mapped region can unexpectedly become inaccessible.

### 8.3. Do Not Confuse a Mapped File with a Direct-Allocated Buffer

~~~java
ByteBuffer a = ByteBuffer.allocateDirect(4096);  // Off-heap process-local

MappedByteBuffer b = fileChannel.map(
        FileChannel.MapMode.READ_WRITE, 0L, 4096L);
~~~

Both can be **direct buffers**, but **only `b`** in the example has a backing resource that is **a file** which other processes can open and map. The `isDirect()` property alone does not tell you whether IPC is possible.

## 9. Java 17+ Example 2: Two JVM Processes, Same File-Backed Mapping

This is a **complete, runnable** demo using Java 17+. To avoid depending on when P1 "immediately sees" changes in an old mapped view from P2, the demo uses an **ordered protocol**:

1. Parent creates a temporary file on local storage, setting its size to exactly **4 bytes**.
2. Parent maps the file with `READ_WRITE`, writes the number 41, and calls `MappedByteBuffer.force()`.
3. Parent spawns a **child Java process** and passes the **file path** via a command-line argument.
4. Child opens the same file, maps it separately, reads 41, writes 42, calls `force()`, and exits.
5. Parent waits for `Process.waitFor()` to succeed, then **re-reads the file content through `FileChannel`**, without assuming the content was immediately reflected in the old mapped view.
6. Parent verifies the number 42 and prints to stdout.

The exercise uses a **local filesystem file** with normal read/write permissions. With network filesystems, coherence and flush semantics depend on the OS/protocol and must be tested separately.

### 9.1. File `TwoProcessesMappedFile.java`

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Locale;

public final class TwoProcessesMappedFile {
    private static final int SIZE = Integer.BYTES;

    private TwoProcessesMappedFile() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 2 && args[0].equals("child")) {
            child(Path.of(args[1]));
            return;
        }

        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Run with no arguments, or: child <file>");
        }

        Path file = Files.createTempFile("mapped-ipc-", ".bin");
        // Best-effort cleanup of the file when the parent JVM exits.
        file.toFile().deleteOnExit();

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING)) {

            // FileChannel.truncate(4) does not extend an empty file.
            // Write all 4 bytes before mapping.
            ByteBuffer initial = ByteBuffer.allocate(SIZE);
            while (initial.hasRemaining()) {
                channel.write(initial);
            }

            MappedByteBuffer mapped =
                    channel.map(FileChannel.MapMode.READ_WRITE,
                                0L, SIZE);
            mapped.order(ByteOrder.BIG_ENDIAN);
            mapped.putInt(0, 41);
            mapped.force();

            System.out.println("parent mapped write=41");
            System.out.flush();

            // Run the same current JDK to avoid depending on PATH.
            String executable = System.getProperty("os.name")
                    .toLowerCase(Locale.ROOT)
                    .startsWith("windows")
                    ? "java.exe" : "java";

            Path java = Path.of(
                    System.getProperty("java.home"),
                    "bin", executable);

            Process process = new ProcessBuilder(
                    java.toString(),
                    "-cp",
                    System.getProperty("java.class.path"),
                    TwoProcessesMappedFile.class.getName(),
                    "child",
                    file.toString())
                    .inheritIO()
                    .start();

            int exit = process.waitFor();

            if (exit != 0) {
                throw new IOException(
                        "Child JVM failed with exit code " + exit);
            }
        }

        // Read the file through a new channel after child has forced + exited.
        // No need to assume the old mapped view sees the new write immediately.
        try (FileChannel verify = FileChannel.open(
                file, StandardOpenOption.READ)) {
            ByteBuffer bytes = ByteBuffer.allocate(SIZE);
            bytes.order(ByteOrder.BIG_ENDIAN);

            while (bytes.hasRemaining()) {
                int n = verify.read(bytes);
                if (n < 0) {
                    throw new EOFException("File shorter than 4 bytes");
                }
            }

            bytes.flip();
            int value = bytes.getInt();

            if (value != 42) {
                throw new IllegalStateException(
                        "Expected 42, got " + value);
            }

            System.out.println("parent file read=42");
        }
    }

    private static void child(Path file) throws Exception {
        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE)) {

            if (channel.size() != SIZE) {
                throw new IOException(
                        "Unexpected file size: " + channel.size());
            }

            MappedByteBuffer mapped =
                    channel.map(FileChannel.MapMode.READ_WRITE,
                                0L, SIZE);
            mapped.order(ByteOrder.BIG_ENDIAN);

            int before = mapped.getInt(0);
            if (before != 41) {
                throw new IllegalStateException(
                        "Expected 41, got " + before);
            }

            mapped.putInt(0, before + 1);
            mapped.force();

            System.out.println("child mapped read=41");
            System.out.println("child mapped write=42");
        }
    }
}
~~~

### 9.2. Compile and Run Commands

~~~bash
javac TwoProcessesMappedFile.java
java TwoProcessesMappedFile
~~~

The program starts the child JVM itself using `ProcessBuilder`. You **do not need** to open a second terminal manually. The temporary file is created with `Files.createTempFile` in the default temporary directory; the parent passes the path via an argument, not the `MappedByteBuffer` Java object.

No native C compiler, JNI library, or `--enable-native-access` is needed because this is long-standing Java NIO.

### 9.3. Successful Stdout

~~~text
parent mapped write=41
child mapped read=41
child mapped write=42
parent file read=42
~~~

The line order is by design:

- Parent prints the first line and flushes before starting the child process.
- Child only runs after parent has written and called `force()`, so it reads the written data.
- Child prints two lines and terminates; parent uses `waitFor()` to wait for the child to finish.
- Parent reads the file **after** the child has called `force()` and exited, checks the number 42, and only then prints the final line.

**Important limitation:** This is an example of **ordered exchange via file-backed mapping** on a local filesystem, **not** a verification that every OS provides immediate coherence across multiple mappings when two processes read/write concurrently. The Javadoc allows different levels of visibility depending on the OS. For a concurrent IPC protocol, you need an appropriate lock/notification mechanism and platform testing.

### 9.4. Why Not Just `Thread.join()`?

Parent and child are **two JVM processes**. `Thread.join()` only waits for a thread belonging to the caller's JVM; it does not wait for a child OS process. In the example, **`Process.waitFor()`** is the barrier of the parent-child protocol.

Similarly, `synchronized(lock)` or `AtomicInteger` in the parent does not lock the child JVM, because the `lock`/`AtomicInteger` Java object in the child is a **different** object. If two processes update concurrently, **interprocess synchronization** is required.

### 9.5. Notes on Temporary Files

`deleteOnExit()` is best-effort, not part of the IPC protocol. A `MappedByteBuffer` file mapping may exist until GC; on Windows or special filesystems, the file may still be held/mapped. In real applications, have a file-cleanup lifecycle and handle cleanup failures, rather than treating closing the channel as an immediate unmap.

**Do not truncate the file while the child still has it mapped**, and do not assume deleting a file on one OS will make other processes lose their mapping immediately in a uniform way across all platforms.

## 10. `force()`, Visibility, Ordering, and Durability Are Not the Same

There are at least four distinct questions:

1. **Sharing:** Do P1 and P2 share the same backing bytes (same file, offset, and mapping mode)?
2. **Visibility:** When P1 writes, what data will P2 see, and when?
3. **Ordering/atomicity:** Could a partially written record be read? Could two processes updating a counter concurrently lose an increment?
4. **Durability:** Has the data been durably written to the storage device, or is it still in cache?

`MappedByteBuffer.force()` primarily addresses **durability** of changes on a `READ_WRITE` mapping. According to the JDK 17 API, when the file is on **local storage**, after `force` succeeds, changes to the mapping are guaranteed to be written to the storage device; on non-local storage there is no equivalent guarantee.

`force()` **is not**:

- A Java `volatile` write.
- An interprocess mutex.
- An atomic transaction for an entire record.
- A guarantee that two processes will see every write immediately in an old mapped buffer.
- A mechanism to notify a consumer that "a new message has arrived".
- A safe way to read data while a writer is truncating the file.

If `force` is called without coordination while both processes write `counter = counter + 1`, data can still suffer a lost update. `force` only pushes bytes to storage; it does not resolve races on its own.

### 10.1. `FileChannel.force` Does Not Replace `MappedByteBuffer.force`

There are two easily confused APIs:

~~~java
channel.force(true);
mapped.force();
~~~

- `channel.force(metaData)` refers to file updates made through channel methods and certain related stream types. The specification states it **does not guarantee** forcing all changes made through a `MappedByteBuffer`.
- `mapped.force()` is the API specifically for **changes made through the mapped buffer**.

In the demo, each process modifies data through the mapping, so it calls **`mapped.force()`**.

### 10.2. A Read Is Different from an Atomic Update

Suppose two JVMs both do:

~~~java
// Dangerous snippet if run concurrently in two processes:
int current = mapped.getInt(0);
mapped.putInt(0, current + 1);
mapped.force();
~~~

The two processes can **both read the same old value** and then write the same new value; the result loses one increment. There is no atomic increment guarantee from `MappedByteBuffer.getInt`/`putInt` alone.

To support concurrent updates, you need an **interprocess synchronization protocol**: cooperative `FileLock`, named OS mutex, semaphore, or an IPC memory-ordering algorithm verified on the specific ABI/platform.

## 11. How Does Synchronizing Java Threads Differ from Synchronizing OS Processes?

### 11.1. Within the Same JVM: Java Memory Model

Java has *happens-before* relationships, for example:

- Actions before `thread.start()` are published according to the start rule.
- Actions of a worker before termination are observed after a successful `thread.join()`.
- `volatile` read/write, `synchronized` lock/unlock, and `java.util.concurrent` utilities have documented semantics.
- `AtomicInteger.incrementAndGet` guarantees an atomic update for that object in that JVM.
- For shared FFM/native segments, `VarHandle` has access modes for atomic/memory-ordering operations when the carrier/layout is suitable.

These are **Java thread-level** rules. If P1 and P2 each create their own `AtomicInteger(0)`, they **do not have the same object** to synchronize on.

### 11.2. Across JVMs: An IPC Protocol Is Needed

Two JVM processes do not share Java monitors, class-loader state, or Java `AtomicInteger` instances. For file-backed IPC, straightforward choices are:

- **One writer, one reader, with a clear handoff point:** like the `Process.waitFor` example.
- **Multiple independent processes:** use `FileChannel.lock()` / `tryLock()` when appropriate, with cooperative lock rules across all participants.
- **Notifying that new data is available:** pipe/socket/message queue/event primitive; a mapping only holds bytes, not a notification mechanism.
- **Very low latency:** use native shared memory plus interprocess atomics/semaphores on a controlled platform, with careful memory ordering/ABI.

### 11.3. What Are the Limitations of FileLock?

`FileChannel.lock()` creates a `FileLock` that can be seen by the OS from other processes. However, the Java API emphasizes:

- Some OSes only support **advisory locking**: another program that does not follow the protocol can still read/write.
- File locks are held **on behalf of the entire JVM process** and should not be used to protect threads within the same JVM.
- Shared locks may be converted to exclusive by the OS if shared locking is not supported.
- Some OSes/filesystems have restrictions or bugs when **mapping a file and locking the same region**; the application must test on the target platform.
- On network filesystems there may be alignment/size limits and protocol-specific behavior.
- Do not use `FileLock` as a way to "flush data to storage". Locking and durability are different responsibilities.

A protocol pattern for **cooperating** processes (snippet inside a method, not a standalone runnable program):

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE);
     FileLock lock = channel.lock()) {

    // Both producer and consumer must follow the same lock rule.
    // Read/write a complete record inside the critical section.
    // If using mapped memory, force when durability is needed.
}
~~~

**Do not** take the example above as proof that `FileLock` will block every OS mapping access by any process: that depends on the OS. With a process that does not obey the lock, the application still risks reading/writing inconsistent data.

## 12. FFM and `Arena.ofShared()`: What Does "Shared" Mean?

Since **JDK 22**, FFM has `Arena`:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);

    // Any Java thread has permission to access this segment
    // while the arena is still open, if the synchronization algorithm is appropriate.
}
~~~

This snippet requires importing `java.lang.foreign.Arena`, `MemorySegment`, and `ValueLayout`.

`Arena.ofShared()`:

- Has no fixed owner thread; Java threads in **the same process** are allowed to access segments allocated from the arena.
- When `close()` succeeds, **every segment belonging to the arena** becomes invalid; accessing FFM after close throws `IllegalStateException`.
- Does not make `get`/`set` atomic, does not grant interprocess permissions, and does not name an OS shared-memory object.
- Does not turn `arena.allocate(1024)` into POSIX `shm_open`, Windows named mapping, or a file-backed mapped segment.
- Does not allow another JVM to obtain the same Java `MemorySegment` by knowing the variable name or the virtual address of the first process.

### 12.1. Comparing Three MemorySegment Sources (JDK 22+)

| Segment Source | Can Be Used by Multiple Threads? | Can It Be Backing Between Processes? |
| --- | --- | --- |
| `Arena.ofConfined().allocate(...)` | Owner thread only | **No**, not by this allocation alone |
| `Arena.ofShared().allocate(...)` | Yes, but requires synchronization | **No**, not by this allocation alone |
| `FileChannel.map(READ_WRITE, ..., Arena.ofShared())` | Yes, while the arena is alive | **Potentially**, due to **the same file-backed mapping** and OS protocol, not because of the Arena name |

**Formula:** *Arena policy* determines **thread access and lifetime in Java**; *mapping source* determines the **backing resource**, which can be shared by the OS between processes.

## 13. JDK 22+: `FileChannel.map(..., Arena)` Is the Clear Bridge

JDK 22 added the overload:

~~~java
MemorySegment mapped = fileChannel.map(
        FileChannel.MapMode.READ_WRITE,
        0L,
        4096L,
        arena);
~~~

This is a snippet, with `fileChannel` opened in the appropriate mode, the file large enough, and `arena` still alive.

**This API is different from `arena.allocate(...)`.** `fileChannel.map` takes bytes from a **file-backed mapped region**; `arena` only controls the **lifetime and thread access rules of the Java segment view**. When a closeable arena is closed, the mapped region is **unmapped** according to the API contract.

### 13.1. Two Sides of Ownership

~~~text
File-backed source:
  Path/OS file -> FileChannel.map(..., arena) -> MemorySegment
                  ^                             ^
                  |                             |
             OS backing                    Java view/scope
             cross-process                 arena thread policy
             per OS + protocol             + close/unmap

Native allocation:
  Arena.ofShared().allocate(...) -> MemorySegment
     |                                   |
     +--> process-local allocation       +--> Java threads share
          NOT file-backed                     same view/lifetime
~~~

Both are `MemorySegment`, yet their **source resources** are different. Therefore, do not treat the `ofShared` API name as the reason data is shared across processes.

### 13.2. Mapped MemorySegment and MappedByteBuffer

| Feature | `FileChannel.map(mode, offset, size)` | `FileChannel.map(mode, offset, size, arena)` |
| --- | --- | --- |
| JDK | Present since older Java versions, runs on Java 17 | Added in Java 22 |
| Returns | `MappedByteBuffer` | `MemorySegment` |
| View lifetime | Tied to GC of the mapped buffer | Tied to the provided `Arena` |
| Explicit-time cleanup | No direct public unmap | `Arena.close()` for closeable arenas |
| Multi-threaded | Can be shared, must be synchronized | Use a shared arena to allow multiple threads to access |
| Cross-process backing | Depends on mapped file/mode and OS | Depends on mapped file/mode and OS |
| Flush | `mapped.force()` | `mappedSegment.force()` |
| Data access | `getInt`/`putInt` / ByteBuffer APIs | `get`/`set` / ValueLayout and VarHandle |

**Note:** `FileChannel` defines a default implementation of the `map(..., Arena)` overload that may throw `UnsupportedOperationException` if the provider does not support it. Standard JDK 22+ native file channels support it, but portable code should still handle platform/provider constraints.

## 14. Java 22+ Example 3: File Mapping into MemorySegment and Explicit Unmap

File **`FFMMappedSegmentDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FFMMappedSegmentDemo {
    private FFMMappedSegmentDemo() {
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("ffm-mapping-", ".bin");
        file.toFile().deleteOnExit();

        MemorySegment segment;
        ValueLayout.OfInt layout = ValueLayout.JAVA_INT
                .withOrder(ByteOrder.BIG_ENDIAN);

        try (FileChannel channel = FileChannel.open(
                file,
                StandardOpenOption.READ,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING);
             Arena arena = Arena.ofShared()) {

            ByteBuffer initial = ByteBuffer.allocate(Integer.BYTES);
            while (initial.hasRemaining()) {
                channel.write(initial);
            }

            segment = channel.map(
                    FileChannel.MapMode.READ_WRITE,
                    0L,
                    Integer.BYTES,
                    arena);

            segment.set(layout, 0L, 17);
            segment.force();

            System.out.println(
                    "FFM mapped value=" + segment.get(layout, 0L));
        } // Arena.close(): segment scope is no longer alive, mapping is unmapped.

        System.out.println(
                "scope alive=" + segment.scope().isAlive());

        try (FileChannel verify = FileChannel.open(
                file, StandardOpenOption.READ)) {

            ByteBuffer raw = ByteBuffer.allocate(Integer.BYTES);
            raw.order(ByteOrder.BIG_ENDIAN);

            while (raw.hasRemaining()) {
                if (verify.read(raw) < 0) {
                    throw new java.io.EOFException(
                            "File shorter than 4 bytes");
                }
            }

            raw.flip();
            System.out.println("file value=" + raw.getInt());
        }
    }
}
~~~

Run on **JDK 22+**:

~~~bash
javac FFMMappedSegmentDemo.java
java FFMMappedSegmentDemo
~~~

With a standard file channel provider that supports FFM mapping, stdout:

~~~text
FFM mapped value=17
scope alive=false
file value=17
~~~

Explanation:

- The file is exactly 4 bytes before mapping; the demo **does not** rely on `FileChannel.truncate(4)` to automatically extend an empty file.
- `segment` is a mapped view of **a file**, not new memory allocated by `arena.allocate`.
- `Arena.ofShared()` allows multiple threads in the same JVM to access the segment during that lifetime, though the demo uses a single thread for deterministic results.
- `ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN)` specifies the byte order matching `ByteBuffer` during verification.
- `segment.force()` requests write-back of changes on the mapped region.
- Upon exiting `try`, the Arena closes and the mapped `MemorySegment` becomes invalid; `scope.isAlive()==false`.
- Reopening the file and reading 17 after closing shows that **the file retains the data** after the Java view ends. This is not a live read from another process, so it does not prove coherence latency between processes.

For a file-mapped region actually shared between processes, **each process must open the same file and map it itself**. Do not pass the `segment` Java object from JVM P1 to P2.

### 14.1. What If `Arena.ofConfined()` Is Used Instead of Shared?

A `MemorySegment` mapped from a file has a backing resource that can be opened by multiple processes, but **a Java view inside a confined arena can still only be accessed by its owner thread in that JVM**. Even within P1, another Java thread accessing the confined view will throw `WrongThreadException`. However, P2 can have **its own mapping** of the same file; these are two different layers of control.

This is a very good example to remember: **the same backing file does not override the confinement rules of each individual Java `MemorySegment`**.

## 15. IPC Data Format: More Than Just Four Bytes

The runnable example uses a single `int` to clarify the mechanism. When data is more complex, the two processes must agree on a **binary protocol**:

| Field | Purpose |
| --- | --- |
| Magic | Identify the file or shared-memory block as the right type |
| Version | Check layout compatibility between programs |
| Length | Actual payload size, avoiding reading past the mapped region |
| State | READY / WRITING / ACKNOWLEDGED per the protocol |
| Sequence number | Distinguish new/old records or retries |
| Payload | Data according to the published layout |
| Checksum/CRC | Detect corrupted bytes or partial writes |
| Padding/alignment | Match the ABI if using native structs or atomics |

Example layout design (illustrative, not a built-in Java API definition):

~~~text
Offset  Size  Meaning
0       4     MAGIC = 0x4A564D49 ("JVMI")
4       4     VERSION = 1
8       4     STATE (0 empty / 1 writing / 2 ready)
12      4     LENGTH
16      8     SEQUENCE NUMBER
24      ...   PAYLOAD
~~~

You must explicitly choose **big-endian** or **little-endian** for all fields. In Java, use `ByteBuffer.order(ByteOrder.BIG_ENDIAN)` or the equivalent `ValueLayout.withOrder`. For C/C++, check `sizeof`, alignment, packing, and CPU endianness; do not arbitrarily "cast" raw mapped bytes to a native struct and assume two processes with different compilers/ABIs will share the same layout.

### 15.1. Producer/Consumer Must Not See a Half-Written Record

A protocol based on a cooperative file lock might look like:

~~~text
PRODUCER                          CONSUMER
---------                         --------
acquire exclusive IPC lock       acquire same IPC lock later
STATE = WRITING                   only after producer releases
write payload                     validate MAGIC / VERSION
write LENGTH / CRC                check STATE == READY
STATE = READY                     read whole record
force mapped changes if needed    validate CRC / LENGTH
release IPC lock                  process data
                                 release IPC lock
~~~

This is a **protocol diagram**, not runnable source code. If you need immediate notification when data is available, use an additional IPC notification; do not busy-spin on a `STATE` byte in a mapped buffer and assume visibility is guaranteed by Java on every OS.

**All participants must follow the same lock/protocol rules.** On some OSes, locks are advisory, so a process that ignores the lock can still corrupt data.

### 15.2. Two Writers Incrementing One Counter Concurrently

The wrong case:

~~~text
P1 reads 10                P2 reads 10
P1 writes 11               P2 writes 11
Result is 11 even though there were two increments
~~~

A safe application-level approach is to serialize updates through **an interprocess lock** or turn increments into messages sent to **a single owner process**. Using a Java `AtomicInteger` in P1 will not save P2's independent `AtomicInteger`.

With native shared memory and interprocess atomics, you need explicit guarantees regarding **atomic alignment, memory order, process-shared synchronization primitives, ABI, and operating system**. Do not take Java `VarHandle` access modes as a portable promise of synchronization between JVM processes: the Java Memory Model describes intra-JVM threads, whereas cross-process effects depend on the OS and mapping mechanism.

## 16. Not Every IPC Should Use Shared Memory

Shared memory lets multiple processes access a backing region without necessarily copying the entire payload over a pipe/socket on every operation. However, it requires designing more complex **protocols, synchronization, schemas, lifetimes, and failure recovery**.

Choose the tool based on the need:

| Need | Suitable Solution |
| --- | --- |
| Two threads in the same JVM exchanging small state | `AtomicInteger` / concurrent queue / locks |
| Two threads in the same JVM processing a large buffer | Shared Java object/ByteBuffer, FFM `Arena.ofShared()` if native memory is needed |
| Two JVMs communicating small messages | Pipe, Unix-domain socket, TCP, gRPC, or message queue |
| Two JVMs exchanging a large batch that can be written to a file | `FileChannel` read/write, memory-mapped file when beneficial |
| Two JVMs on the same machine needing a low-latency shared backing region | Native OS shared-memory mapping + process-shared synchronization |
| Persistent dataset read by multiple processes | Read-only file mapping, versioning, and file replacement protocol |
| Only need to share information with a client on another machine | Network IPC; local shared memory does not cross machines |
| Need transactional updates/strong durability | Database or storage engine with journaling/locking |

**In practice:** Memory mapping has initialization and management overhead, so it is **not always faster** than reading/writing a few KB with `FileChannel.read/write`. Measure on real data and filesystems; avoid choosing mmap just because the name "shared memory" sounds like it saves copies.

## 17. Lifecycle and Operational Errors of Mapped Files

### 17.1. A Mapped View Is Not a File Channel

With Java 17:

~~~java
MappedByteBuffer mapped;

try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ)) {
    mapped = channel.map(
            FileChannel.MapMode.READ_ONLY, 0L, fileSize);
}

// Channel is closed, but mapped can still be valid.
~~~

The snippet assumes `path` and `fileSize` are defined and the region is within the file. Closing the channel does not automatically unmap the mapping.

With Java 22 FFM:

~~~java
MemorySegment mapped;

try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ);
     Arena arena = Arena.ofShared()) {

    mapped = channel.map(
            FileChannel.MapMode.READ_ONLY,
            0L, fileSize, arena);
}

// Arena is closed: mapped scope is no longer alive.
~~~

The Java 22 snippet also assumes `path`/`fileSize` are valid; after closing, do not read data from `mapped`. This is the **lifetime management** difference between `MappedByteBuffer` and mapped `MemorySegment`.

### 17.2. File Truncated or Replaced

If one process is mapping bytes [0, 4096) and another process **truncates the file down to 100 bytes**, the part of the mapping beyond the file can become inaccessible. Depending on the OS, this may cause an exception, a native fault, or other mapping issues. The Java Javadoc requires special care regarding concurrent changes to the backing file's content/size from other programs.

**Rule:** Do not resize or delete the backing resource until all processes have stopped using the mapping or have switched to another version according to the protocol.

### 17.3. Process Crash Mid-Write

If the producer dies after writing half the payload and before setting `STATE=READY`, the consumer must recognize incomplete data and not read it as a valid record. For data that must be durable:

- Write a format including version/length/checksum.
- Have an appropriate transaction/commit marker or journal.
- Use `force` according to durability needs.
- Consider atomic file replacement by writing a new file and renaming, according to the capabilities of the filesystem and the protocol for opening new mappings.
- Test recovery after process crash, `kill`, and power loss.

`force()` on a mapped buffer **does not turn a sequence of multiple writes into an atomic transaction**.

### 17.4. Security and File Access Permissions

If using a memory-mapped file as IPC, **security depends on file permissions, path, and OS handles**:

- A file in a world-writable directory can be opened/modified by other processes.
- Both sides should validate the path/canonical identity and permissions, avoiding symlink swaps when sensitive data is involved.
- Do not use file-backed shared memory to hold long-lived secrets without a clear lifecycle and access control.
- With POSIX named shared memory or Windows named mapping, apply appropriate permissions/security descriptors.

Do not use "same text path" as proof that two processes are opening **the same file identity**: symlinks, mount namespaces, file replacement, or container isolation can make the path point to a different object.

## 18. Common Mistakes and Misconceptions

| Misconception / Symptom | Why It Is Wrong | How to Solve It |
| --- | --- | --- |
| "`Arena.ofShared()` is RAM for all JVMs" | Shared here is the **thread-access scope within one process** | Use OS-backed named/file mapping if IPC is needed |
| "`DirectByteBuffer` is machine-wide memory" | Direct is still a process-local allocation | Distinguish direct memory from a mapped file |
| "Two `static` fields with the same name in two JVMs are the same variable" | Each process/JVM has independent state | Use IPC or shared storage |
| "Sending a native pointer from P1 to P2 will work" | Virtual address spaces differ | Exchange a resource identifier and map separately in P2 |
| "`MappedByteBuffer.PRIVATE` publishes writes to all processes" | PRIVATE is copy-on-write | Use `READ_WRITE` when shared backing updates are needed |
| "`force()` is an interprocess mutex" | Force handles write-back, not atomicity | Use a protocol and cross-process synchronization |
| "`force()` always makes P2's old mapping see it immediately" | Cross-process mapping visibility is OS-dependent | Design handoff/notification, verify/coherence per platform |
| "`Thread.join()` waits for a child process" | Join is thread-only | Use `Process.waitFor()` or IPC ack |
| "`synchronized` on a Java object locks another JVM" | Each JVM has a different object | Use `FileLock`/native mutex/IPC |
| "`FileLock` protects Java threads in the same process" | Locks are scoped to the entire JVM | Use Java locks for threads; `FileLock` between processes |
| "Every `FileLock` always forcefully blocks other processes from writing" | Many OSes use advisory locks | All participants must obey the protocol |
| "Closing `FileChannel` unmaps `MappedByteBuffer`" | The mapping lives until GC of the buffer | Manage lifecycle; consider FFM map + Arena |
| "`truncate(4096)` turns a 0-byte file into 4096" | `truncate` does not extend a file | Write bytes to ensure file size before mapping |
| "Map the file and ignore endianness" | Two processes/languages may interpret bytes differently | Standardize binary layout/`ByteOrder` |
| "A process crash does not affect mapped data" | A record can be half-written or backing not flushed | Version, commit marker, checksum, recovery |
| "The mapped file only lives until the process closes the channel" | Channel and mapped view are different resources | Clean up mappings and backing files per OS |
| "A shared arena automatically guarantees data-race freedom" | Access permission ≠ synchronization | Java atomics/locks for threads, IPC protocol for processes |

## 19. Review Questions with Answers

**Q1.** Two threads share a reference to `ByteBuffer.allocateDirect(1024)` in one JVM. Is this inter-process shared memory?

**Answer:** No. This is **shared off-heap memory between threads in one process**. A direct allocation does not automatically have a backing resource mapped by another JVM.

**Q2.** Two independent JVMs both call `Arena.ofShared().allocate(4096)` on JDK 22. Do they share the same 4,096 bytes?

**Answer:** No. Each JVM allocates its own process-local memory. `ofShared` only allows multiple threads **of the same process** to access the segment.

**Q3.** To have Java P1 and Java P2 exchange data in a mapped file, what is needed?

**Answer:** The same **file identity**, offset/length region, and a mapping mode that allows shared writes when needed; each process opens/maps it independently and has a **synchronization protocol**. Do not pass a Java `ByteBuffer` reference from one process to another.

**Q4.** Why is `FileChannel.MapMode.PRIVATE` unsuitable for P1 to write and P2 to read the result?

**Answer:** `PRIVATE` creates copy-on-write: P1's changes are not propagated back to the backing file and do not become changes visible to P2.

**Q5.** How do `MappedByteBuffer.force()` and `Thread.join()` differ?

**Answer:** `force` is for writing mapped file changes to storage. `join` creates a wait point and a happens-before relationship between threads in the JVM. They address **two different aspects**.

**Q6.** What role does `Process.waitFor()` play in the two-JVM demo?

**Answer:** The parent waits for the child to finish its operations and exit, creating an **ordered handoff** before the parent re-reads the file. It does not turn two JVMs into the same memory heap or guarantee real-time mmap coherence.

**Q7.** Why does the parent in the demo re-read using `FileChannel` after the child exits instead of using the old mapped buffer?

**Answer:** Java mapping APIs allow changes from another process to become visible at OS-dependent times. Re-reading the file after the child forces and exits fits the sequential demo and avoids attributing a guarantee to the old mapped view that is not in the Javadoc.

**Q8.** Two JVMs concurrently increment a counter in a mapped file using `getInt` then `putInt`. Will the result always be correct?

**Answer:** No. Two separate operations have a race; a protocol with an appropriate interprocess lock/atomic primitives is needed, not just `force`.

**Q9.** Does using `FileChannel.lock()` lock Java threads within the same process?

**Answer:** Not appropriate: `FileLock` is held on behalf of the JVM and is aimed at coordinating with other processes. Threads in the same JVM should use Java concurrency primitives.

**Q10.** When using `FileChannel.map(READ_WRITE, ..., arena)` in JDK 22, what makes the data capable of IPC: `Arena.ofShared()` or the backing file?

**Answer:** The **backing file** and OS mapping. The Arena only determines the temporal/thread access of the `MemorySegment` in the current JVM.

**Q11.** Does closing the `Arena` of a mapped `MemorySegment` delete the file?

**Answer:** No. Closing puts the segment out of scope and unmaps the local view. The backing file exists according to its own filesystem lifecycle until deleted per OS permissions and policy.

**Q12.** What happens if P1 and P2 map the same file, but P1 uses big-endian and P2 uses little-endian?

**Answer:** The same bytes are interpreted as **two different values**. You must agree on byte order, primitive sizes, padding, and schema across processes/languages.

**Q13.** A file is truncated while P2 still has it mapped. Is P2 guaranteed to safely read to the end of the old mapping?

**Answer:** No. Part of the mapped region can become inaccessible; Java docs do not guarantee uniform exceptions or timing. You must use a protocol to manage resize/unmap.

**Q14.** Why not use `FileChannel.force(true)` instead of `MappedByteBuffer.force()`?

**Answer:** The `FileChannel.force` Javadoc does not guarantee that it flushes all changes made through a mapped buffer; use `mapped.force()` for mapped writes.

**Q15.** If P1 and P2 run on two different machines, can P1's named OS shared memory be used as a Java object on P2?

**Answer:** No. Native shared memory and local mmap are generally confined to one host/OS environment. For two machines, use a network protocol or shared storage with appropriately designed semantics.

## 20. Official Documentation

- [Oracle Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `map`, `force`, file locks, and OS-dependent visibility limits.
- [Oracle Java SE 17 — FileChannel.MapMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.MapMode.html): `READ_ONLY`, `READ_WRITE`, `PRIVATE`.
- [Oracle Java SE 17 — MappedByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/MappedByteBuffer.html): file-backed direct buffers, `force`, mapped lifetime, and content changes from other programs.
- [Oracle Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): direct/heap buffers, absolute operations, and `ByteOrder`.
- [Oracle Java SE 17 — FileLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): process-level locks, advisory/mandatory, filesystem limitations.
- [Oracle Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`/`join`, Java threads, and lifecycle.
- [Oracle Java SE 17 — Process](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): `waitFor` and process lifecycle.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): `ofShared`, confined/shared scope, and lifetime.
- [Oracle Java SE 22 — FileChannel.map(..., Arena)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/channels/FileChannel.html): mapped `MemorySegment` tied to an Arena and explicit unmap.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): scope, native memory, and mapped segment operations.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): standardization of FFM in JDK 22.

**Conclusion:** **Sharing between threads** means multiple threads of **one JVM process** have permission to access the same object/backing bytes and must obey Java concurrency rules. **Sharing between processes** requires a **resource shared by the OS**, such as file-backed `FileChannel.map(READ_WRITE)` or a named shared-memory mapping, with each process opening its own view and coordinating via an **IPC synchronization/protocol**. `Arena.ofShared()` does not turn a process-local allocation into inter-process shared memory; and `MappedByteBuffer.force()` does not replace visibility, atomicity, or locking.

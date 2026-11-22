# Buffers and Files — Defining Ownership When Java Holds a Buffer Pointing to C-Allocated Memory

## 1. The Problem: Java Holding a Buffer Does Not Mean Java Owns the Memory

When Java and a C library exchange data via JNI or the Foreign Function & Memory (FFM) API, Java may receive a `ByteBuffer` / `MemorySegment` representing **the address of a memory region outside the Java heap**. That memory region may have been allocated by C using `malloc`, the library's own allocator, or an OS API. The Java object at this point is only a **view/handle** to the memory region.

**Questions to answer before using the buffer:** who allocated it, who currently owns it, who is allowed to read/write, who must release it, which release function to use, and how long the remaining Java views may exist?

Concepts:

- **Allocator:** where the block is created, for example `malloc`, `HeapAlloc`, `mmap`, `VirtualAlloc`, or a library-specific allocator.
- **Owner:** the component responsible for ensuring the block is freed **exactly once**, after no one is using it anymore.
- **Borrower:** has temporary permission to use it, but **must not free** it; must not keep the view longer than the owner/lifetime.
- **Transfer of ownership:** the C library creates the block and then **transfers the responsibility of freeing it** to the Java side through a clear protocol.
- **Aliasing:** two or more `ByteBuffer`, `slice()`, `duplicate()`, or `MemorySegment` instances pointing to **the same native block**. Freeing the block makes **every alias** dangerous if still accessed.
- **Lifetime:** the interval from successful allocation to successful deallocation. A Java object still being reachable **does not prove** the native block is still alive.
- **View ≠ allocation:** creating a `ByteBuffer` directly from an address does not copy bytes, and does not automatically create a free mechanism.

Ownership diagram:

```text
             Native C library                 Java
       ┌─────────────────────┐      ┌─────────────────────┐
malloc │ block 16 bytes      │◄─────│ ByteBuffer view     │
  ───► │ ptr = 0x...         │      │ MemorySegment view  │
       └─────────────────────┘      └─────────────────────┘
                 ▲                            │
                 │                     only holds address,
                 │                     does not own itself
                 │                            │
                 └── free()/release(ptr) ◄────┘
                      must have ONE owner
```

A common misconception: "Java holds a reference to `ByteBuffer`, so GC will not lose the data". False: **GC manages Java objects; native allocators have their own lifecycle**. If C has already called `free(ptr)` while Java is still using the view, that is a **use-after-free**; it can result in garbage data, memory corruption, or a JVM crash rather than necessarily a Java exception.

This lesson belongs to **Buffers and Files**: in addition to reading/writing data with `java.nio.ByteBuffer`, we must also handle ownership when a native buffer is passed into `FileChannel` or I/O APIs. The main example uses **Java 22+ FFM**, demonstrates C `malloc/free` on Windows, and has been tested with OpenJDK 24; JNI is also explained to avoid lifecycle confusion.

## 2. Establish the Ownership Contract Before Returning a Buffer to Java

Three common models:

| Model | Who allocates? | What can Java do? | Who frees? |
| --- | --- | --- | --- |
| **Borrowed native buffer** | C/library | Read/write within the scope permitted by the library; do not retain after the owner destroys it | **C/library** |
| **Transferred native buffer** | C/library | Receives ownership after the API reports success; responsible for cleanup | **Java calls the library's release API**, directly or via a scope with cleanup |
| **Caller-owned output buffer** | Java (`Arena.allocate` or another buffer) | Java allocates memory, C only fills the content and returns the number of bytes written | **Java/Arena** closes or frees according to the original allocator |

Sometimes there is **shared ownership** via reference counting: both C and Java hold a reference to a native object, and each side calls retain/release according to the contract. This is not a default consequence of `ByteBuffer`, but a protocol designed by the library.

### 2.1. Borrowed: the library remains the owner

Hypothetical C example:

```c
// Returns a pointer to an internal buffer, valid until close_device(handle).
const unsigned char *device_peek(device_handle *handle, size_t *length);
```

**This is an illustrative declaration**, not an existing library API. Java may only read between `device_peek` and `close_device` or until the contract states the pointer expires (which could be as soon as the next call). Java **does not free** the pointer. If the data is needed after the device closes, **copy** it before closing.

### 2.2. Transfer: the Java side becomes the owner upon success

Hypothetical C example:

```c
// 0 = success; the library mallocs/allocates and transfers ownership.
int image_decode(const void *encoded, size_t encoded_size,
                 unsigned char **out_bytes, size_t *out_size);
void image_release(unsigned char *ptr);
```

After `image_decode` returns `0`, Java receives the pointer, size, and **the obligation to call `image_release(ptr)` exactly once**. If C used a custom allocator, Java must not replace `image_release` with `free` from a different CRT or an arbitrary OS API. If decoding fails, the behavior of `*out_bytes` and ownership must still be checked in the library's **documentation**; do not assume every API sets the pointer to `NULL`.

### 2.3. Caller-owned: Java allocates, C only writes

```c
// Caller allocates buf; C only fills up to capacity bytes.
int read_into_buffer(file_handle *h, unsigned char *buf,
                     size_t capacity, size_t *bytes_written);
```

Java owns the buffer. C must not call `free(buf)`. If C saves the pointer for asynchronous use, Java must extend the lifetime until C reports completion, and **not** close the Arena immediately after the "submit" call. This is especially important for files, sockets, I/O completion callbacks, and native worker threads.

## 3. Seven Ownership Rules Not to Miss

1. **Whoever allocates with an allocator must have a compatible deallocation path.** `malloc/free` are a pair; `new/delete` are a pair; `HeapAlloc/HeapFree` are a pair (with the right heap handle); custom objects/handles need `library_release`; `mmap` needs `munmap`/the corresponding API. Do not mix allocators.
2. **Only one owner is responsible for freeing at the end.** If using reference counting, "once" means each owner releases one reference according to the contract, not calling free on the block multiple times.
3. **Do not free before all views/users stop accessing it.** `slice()`, `duplicate()`, and aliases in Java may hold the same native pointer. Native code might also still be reading/writing the block in a callback.
4. **Do not read past the valid size.** A C pointer is only an address; Java must know how many bytes can be read, how many bytes were initialized by C, and the exact bounds.
5. **Do not assume GC frees C `malloc`.** If the application is responsible for releasing, use `AutoCloseable`/`try-with-resources`, explicit native release, or a cleanup action attached to an Arena. `Cleaner` is only a fallback in some designs, and does not guarantee timely release.
6. **Do not borrow past the lifetime.** A borrowed pointer can be invalidated as soon as the C owner closes or reallocates; keeping a Java reference to a view does not automatically extend its lifetime.
7. **Distinguish release from invalidation.** After `free`, the old address may still be a non-`0` number, but dereferencing it is invalid. An FFM view attached to a closed scope can be rejected with `IllegalStateException`; a raw JNI `ByteBuffer` does not necessarily have a similar mechanism.

### Review matrix for a C API

Before designing a Java wrapper, clearly document:

| Question | Example of a correct answer |
| --- | --- |
| Where is the pointer received? | Return value `unsigned char*` or out-param `unsigned char**` |
| Where is the size obtained from? | `size_t *length`; check error/partial result contract |
| How many bytes are initialized? | `length` bytes on the `status == 0` branch |
| Ownership on success? | Transferred to caller |
| Ownership on error? | No block transferred; check contract |
| Exact deallocator? | `image_release(ptr)` from the same library |
| Can it be borrowed from another thread? | Only if both the library and Java wrapper support it |
| Can it be used after closing? | No; views/aliases must be discarded |
| Who closes and when? | One Java owner, after all sync/async users finish |
| What if the caller forgets to close? | C memory leak; can have a Cleaner fallback, do not rely on GC latency |

## 4. JNI: `NewDirectByteBuffer` Is a View, Not a Free Contract

With JNI, native code can expose a C pointer to Java as a **direct `java.nio.ByteBuffer`**:

```c
// JNI snippet, not a standalone native library.
void *ptr = malloc(capacity); // C allocates.
if (ptr == NULL) {
    // Report allocation failure per the application's JNI policy.
    return NULL;
}

jobject buffer = (*env)->NewDirectByteBuffer(env, ptr, (jlong)capacity);
if (buffer == NULL) {
    free(ptr); // Failed to hand off view: rollback allocation.
    return NULL;
}
// TODO in production: create an owner handle/close contract.
// Simply creating a ByteBuffer does NOT register free(ptr).
return buffer;
```

This snippet **only explains one step**, not advice to copy verbatim into a program, because it **does not yet have** a release protocol when Java finishes using it. In real code, you must provide an **owner object/opaque native handle** and a controlled `close()` method before returning the buffer to the application. Avoid exposing an API `nativeFree(ByteBuffer anyBuffer)` that blindly calls `free(GetDirectBufferAddress(anyBuffer))`: any arbitrary direct buffer could be freed by mistake or double-freed.

**JNI `NewDirectByteBuffer` does not magically transfer ownership.** It creates a view over `address` with `capacity`, with **no** "deallocator" parameter; Java `ByteBuffer` does not automatically know to call `library_release` or `free`. `GetDirectBufferAddress` retrieves the address of a direct buffer, **without certifying** which allocator can free that address.

In addition:

- Java `ByteBuffer` has `position`, `limit`, and `capacity`; **capacity is not ownership**. `slice()`/`duplicate()` create aliases pointing to the same native block.
- A buffer from `NewDirectByteBuffer` has a **default byte order of `BIG_ENDIAN`** per the JNI spec; if C structs/ints are written in machine byte order, Java must call `buffer.order(ByteOrder.nativeOrder())` before reading multi-byte values. Do not assume endianness.
- JNI `NewDirectByteBuffer` accepts a valid pointer/size per the JNI specification; do not construct a view over `NULL` or a size outside the NIO buffer range. Native code must ensure the memory is **actually accessible**.
- After C `free(ptr)`, Java may still hold the `ByteBuffer` and `isDirect() == true`, but that **does not mean** the block is still alive. Accessing it may cause a crash or write into reused memory.
- `ByteBuffer.allocateDirect(size)` is a case where **the JVM creates and manages the native allocation**, which is **different** from C `malloc` followed by JNI wrapping the pointer; do not treat all direct buffers as having a single owner.
- If `JNI NewDirectByteBuffer` is used with memory owned long-term by C, Java may only borrow it within the scope guaranteed by C. If Java is given ownership, you must build an `AutoCloseable` Java wrapper and a native release function matching the allocator.

### Designing a JNI wrapper with clear ownership responsibility

A viable API contract:

```java
// API design sketch, not a standalone program.
interface BorrowedNativeBuffer {
    // Only allows reading/writing within a controlled synchronous operation.
    <T> T withBuffer(java.util.function.Function<ByteBuffer, T> action);
}

interface OwnedNativeBuffer extends AutoCloseable {
    // Allows the callback to use the view while the object is still open.
    <T> T withBuffer(java.util.function.Function<ByteBuffer, T> action);
    @Override void close(); // Calls native library_release exactly once.
}
```

**These are conceptual interfaces**, not automatic safety guarantees: if a callback retains the `ByteBuffer` in a field, the lifecycle can still be violated. The implementation needs synchronization so `close()` does not run while `withBuffer` is using the memory, an `OPEN/CLOSING/CLOSED` state, and a clear rule that all aliases are only valid inside the callback. Objects pointing to the same C allocation must share **one owner/retained handle**, not call `close` independently. If aliases cannot be controlled, **copying bytes to the Java heap** is a safer and easier-to-verify strategy.

## 5. FFM: Binding C Allocation Ownership to an Arena

With the FFM API finalized since **JDK 22**, a C function `malloc(size_t)` returns a native pointer as a `MemorySegment` (typically a **zero-length address segment**). Java can create a view with a specific size using `reinterpret(size)`. However, **`reinterpret` does not allocate and does not automatically free memory**.

If Java receives ownership, FFM supports:

```java
MemorySegment ownedView = pointer.reinterpret(
    size, ownerArena, cleanup);
```

`cleanup` is a `Consumer<MemorySegment>` executed when the Arena scope is invalidated. It must call **the exact deallocator** for the block, not a generic free for a block from another allocator. The returned view is bound to the scope/lifetime of `ownerArena`. Once the Arena is closed, accessing the view/`asByteBuffer()` is blocked at the FFM level.

**Two extremely important points:**

1. **Reinterpret does not verify the actual allocation size.** If you pass a `size` larger than the block C allocated, FFM does not know and access can still cause memory corruption. Verify the size from the C contract, application limits, alignment, and ABI before using.
2. **FFM does not automatically block all aliases of the pointer.** Native code or another `MemorySegment.ofAddress(address)` with global scope can still access the address after `free` — which is extremely dangerous. A scoped view protects **accesses through that view**, and does not create exclusive physical ownership across the entire process.

In practice, you should only create **one cleanup owner** for a C block; do not both call `free` manually and register a cleanup action for the same block. If `reinterpret` fails **before registering the cleanup**, Java still holds ownership and must free the block in a rollback branch.

### FFM Scope and `ByteBuffer`

`MemorySegment.asByteBuffer()` creates a **direct ByteBuffer** for the native segment. According to the documentation, this ByteBuffer view **shares liveness and thread confinement** with the segment: after `ownerArena.close()`, accessing the buffer throws `IllegalStateException` (with the appropriate Java API). The initial byte order is `BIG_ENDIAN`, which can be changed with `order(ByteOrder.nativeOrder())`.

This is **different from a raw JNI `NewDirectByteBuffer`**: FFM has a scope bound to `MemorySegment` to check access, whereas a raw JNI view does not automatically know when the native owner has freed the block.

## 6. Real Runnable Java Example: C `malloc/free` + FFM `MemorySegment` + `ByteBuffer`

The following complete example **does not require compiling C yourself**. On **64-bit Windows**, Java uses FFM to call two C functions directly from **the same CRT DLL `msvcrt.dll`**:

- `malloc(16)` creates a 16-byte native block and returns a pointer. **Java receives ownership of the block after the successful call** per the demo policy.
- `free(pointer)` from **the exact same DLL** is registered as the cleanup action of a confined Arena.
- Java calls `reinterpret` on the pointer with size 16 and the Arena's scope, then creates a `ByteBuffer` view to write/read.
- Java copies the 16 bytes into a `byte[]` before closing the arena. The byte array lives independently after the native block is freed.
- When the Arena closes, the action calls `free` **once**. A subsequent access through the closed scoped ByteBuffer throws `IllegalStateException`; the Java copy remains readable.

**ABI limitation:** the `malloc(size_t)` call is described with `ValueLayout.JAVA_LONG` because `size_t` is 64 bits wide on Windows x64. `free(void*)` takes an `ADDRESS` pointer and returns nothing. Do not use this exact descriptor on a 32-bit ABI. For Linux/macOS, you must change how the C library is looked up and verify the ABI/names.

### 6.1. Complete file `NativeMallocOwnershipDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.concurrent.atomic.AtomicInteger;

public final class NativeMallocOwnershipDemo {
    private static final long LENGTH = 16;

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Keep the library loaded while ANY handle/cleanup may call it.
        try (Arena libraryLifetime = Arena.ofConfined()) {
            SymbolLookup crt =
                SymbolLookup.libraryLookup("msvcrt.dll", libraryLifetime);

            MethodHandle malloc = linker.downcallHandle(
                crt.findOrThrow("malloc"),
                FunctionDescriptor.of(ValueLayout.ADDRESS,
                    ValueLayout.JAVA_LONG));

            MethodHandle free = linker.downcallHandle(
                crt.findOrThrow("free"),
                FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            AtomicInteger releaseCount = new AtomicInteger();
            ByteBuffer expiredBuffer;
            byte[] copy;

            try (Arena owner = Arena.ofConfined()) {
                MemorySegment pointer =
                    (MemorySegment) malloc.invokeExact(LENGTH);

                if (pointer.address() == 0) {
                    throw new OutOfMemoryError("malloc failed");
                }

                boolean cleanupRegistered = false;
                try {
                    // The same C allocation gets ONE cleanup owner.
                    MemorySegment view = pointer.reinterpret(
                        LENGTH, owner, p -> {
                            try {
                                free.invokeExact(p);
                                releaseCount.incrementAndGet();
                            } catch (Throwable t) {
                                throw new IllegalStateException(
                                    "free failed", t);
                            }
                        });
                    cleanupRegistered = true;

                    // View: no new native allocation or byte copy.
                    ByteBuffer bytes = view.asByteBuffer()
                        .order(ByteOrder.nativeOrder());

                    bytes.putInt(0, 123456);
                    bytes.putInt(4, -9);
                    System.out.println("direct: " + bytes.isDirect());
                    System.out.println("first: " + bytes.getInt(0));
                    System.out.println("second: " + bytes.getInt(4));

                    // Copy data BEFORE native release.
                    copy = new byte[bytes.capacity()];
                    bytes.duplicate().clear().get(copy);
                    expiredBuffer = bytes;
                } finally {
                    // Only if reinterpret/registration failed:
                    // release ownership manually as rollback.
                    if (!cleanupRegistered) {
                        free.invokeExact(pointer);
                    }
                }
            } // owner.close() calls the registered free exactly once.

            System.out.println("release calls: "
                + releaseCount.get());

            // Java heap copy is independent from native memory.
            System.out.println("copy after close: "
                + ByteBuffer.wrap(copy)
                    .order(ByteOrder.nativeOrder()).getInt(0));

            try {
                expiredBuffer.getInt(0);
                System.out.println("after close: unexpected");
            } catch (IllegalStateException expected) {
                System.out.println(
                    "after close: IllegalStateException");
            }
        }
    }
}
```

**Why does `finally` have a fallback branch?** After `malloc` succeeds, Java has taken responsibility for releasing it. If `reinterpret` fails before attaching the cleanup action, the Arena does not automatically know about the newly malloc'd block. The `finally` branch only calls `free` when `cleanupRegistered == false`. When registration succeeds, **only `Arena.close()`** calls `free`; there is no explicit free in that branch. This prevents both **memory leaks** and **double-free** on normal execution paths.

**Why are there two Arenas?** `libraryLifetime` keeps the looked-up CRT library loaded while cleanup calls `free`. `owner` separately manages the lifetime of the malloc'd block and the view. Closing `owner` **before** `libraryLifetime` ensures the cleanup action can still call `free` from the DLL.

**Why not return `ByteBuffer`?** The demo retains the view past Arena close only to demonstrate a **controlled rejected access**. Production code must not return a native alias outside the owner scope as a long-lived buffer. `ByteBuffer` may only be used while the owner is still open and no other actor frees the block externally.

### 6.2. Compiling and running on Windows x64 / JDK 22+

Open PowerShell or a terminal with `java` and `javac` from **JDK 22+**:

```powershell
javac -encoding UTF-8 NativeMallocOwnershipDemo.java
java --enable-native-access=ALL-UNNAMED NativeMallocOwnershipDemo
```

`--enable-native-access=ALL-UNNAMED` permits restricted FFM operations from code on the classpath (creating downcall handles and `reinterpret`), while avoiding native access warnings/denials depending on the JDK in use. FFM has been final since JDK 22, so `--enable-preview` is not needed **just to use FFM**.

**Exact stdout verified on OpenJDK 24.0.2 / Windows x64:**

```text
direct: true
first: 123456
second: -9
release calls: 1
copy after close: 123456
after close: IllegalStateException
```

Because `ByteOrder.nativeOrder()` is used for both writing and reading from the heap copy, the example avoids depending on the default byte order of a direct `ByteBuffer`. `releaseCount` is only the number of times **the Java cleanup callback called free** in the demo; it is not an OS-level allocator counter. Do not treat this counter as a replacement for a memory sanitizer/profiler in large applications.

### 6.3. Step-by-step ownership in the code

| Object | Who creates it? | Who owns the native allocation? | Where does it end? |
| --- | --- | --- | --- |
| `pointer` from `malloc` | C CRT `malloc` | **Java receives ownership after success**, per demo policy | Cleanup action calls `free(pointer)` |
| `view` from `reinterpret` | FFM creates Java view | Does not allocate a new block; uses the same C allocation | Invalidated when `owner.close()` runs |
| `bytes` from `asByteBuffer` | FFM creates Java buffer view | Does not own a separate block | Invalidated with `view`'s scope |
| `bytes.duplicate()` | Java creates alias | Same block, does not own a new allocation | Invalidated with the same scope |
| `copy` of type `byte[]` | Java heap | Java GC manages the **copied** bytes | Independent of `owner.close()` |
| `owner` | Java `Arena.ofConfined()` | **Cleanup owner** per `reinterpret` registration | `try-with-resources` closes it, calling cleanup |
| `libraryLifetime` | Java `Arena.ofConfined()` | Owns the handle/lifetime of the library lookup | Closed after `owner`, preventing premature unload |

**Important note about the original pointer:** the raw pointer returned from `malloc` is only an **address**. When Java attaches the view `reinterpret(LENGTH, owner, cleanup)`, the scope protects **that view**, and does not change the lifetime of any pointers/aliases created independently by C or Java. After free, do not reuse `pointer` or a global view from the same address.

## 7. What If You Don't Use `reinterpret(..., Arena, cleanup)`?

You can manage `malloc/free` manually:

```java
// Illustrative snippet, not a standalone class.
// malloc/free are ABI-matching MethodHandles; size is valid bytes.
MemorySegment raw = (MemorySegment) malloc.invokeExact(size);
if (raw.address() == 0) throw new OutOfMemoryError("malloc failed");
try {
    MemorySegment view = raw.reinterpret(size);
    // Only use view inside try and copy data when needed.
} finally {
    free.invokeExact(raw);
}
// Must not use view or any pointer alias after free.
```

This pattern frees explicitly, but `raw.reinterpret(size)` creates a view **not bound to the lifetime of a closeable owner Arena**. If the view leaks outside, Java may not be able to block access after `free`. Therefore, the **`reinterpret(size, ownerArena, cleanup)`** pattern provides an extra layer of lifetime control for **FFM views derived from it**.

**Do not** use `Arena.ofAuto()` as a way to free deterministically: an automatic arena is managed by the runtime/GC and cannot be closed explicitly. A C allocation with transferred ownership usually needs to be freed at a clear point; **`Arena.ofConfined()/ofShared()` with cleanup + `try-with-resources`** is more appropriate.

### Should you use `Cleaner`/finalizer?

`Cleaner` can help as a fallback when a developer forgets to close, but:

- GC/Cleaner does not guarantee **when** it runs; system resources may be exhausted before heap pressure triggers cleanup.
- Cleanup state must avoid retaining reference cycles that prevent GC and avoid calling a native destructor after the library has unloaded.
- Java `finalize()` has been deprecated and should not be used for native ownership.
- If `close()` has already called release, the Cleaner fallback must not release a second time. A carefully designed state/atomic guard is required.
- Never treat `Cleaner` as a safe approach for a native **borrowed pointer** when the owner may destroy the memory earlier.

In the most controllable APIs, require callers to use `try-with-resources` and treat Cleaner only as a supplementary measure. When encountering a native resource leak, check **native memory metrics** rather than only Java heap usage.

## 8. Connecting to File I/O and NIO Buffers

An application can use a native-owned buffer to pass bytes to Java NIO:

```java
// Illustrative snippet, not yet a standalone program.
// buffer is a ByteBuffer view currently valid in the owner Arena.
// channel is a FileChannel opened synchronously for writing.
ByteBuffer toWrite = buffer.duplicate();
toWrite.position(0);
toWrite.limit(numberOfValidBytes);

while (toWrite.hasRemaining()) {
    channel.write(toWrite);
}
// Close the owner Arena only after the synchronous operation completes.
```

**Things to determine before `FileChannel.write`:**

1. `numberOfValidBytes` is the number of bytes **C successfully wrote**, not automatically `buffer.capacity()`; reading uninitialized bytes can expose old data.
2. `ByteBuffer`'s `position`/`limit` bound **the I/O pass**, but **do not determine native allocation lifetime**.
3. `FileChannel.write(ByteBuffer)` may write **fewer bytes than requested**; use a loop or handle partial writes according to the I/O contract.
4. `duplicate()` and `slice()` **do not copy** native bytes; they create new views over the same memory. Do not close/free after creating a duplicate if the duplicate is still in use.
5. When using **asynchronous native I/O** or a library that retains the pointer after submit, you must wait for actual completion before closing; submit returning **does not** mean the buffer is finished being used.
6. If Java needs to keep the file data longer than the owner Arena, **copy into a `byte[]` / owned Java buffer** before closing, then perform file I/O from the copy.
7. If C also writes to the buffer concurrently while Java is reading/writing the file, synchronization and memory visibility are required. `isDirect()` does not guarantee thread safety.

### Case of memory-mapped files or OS handles

`mmap/munmap`, `MapViewOfFile/UnmapViewOfFile`, and file handles use **their own deallocators**; **do not call `free` on a mapped address**. If C provides a mapped region, the owner contract must specify who calls `munmap`/`UnmapViewOfFile` and who closes the backing file handle. `FileChannel.map`/FFM mapped segments also have a different lifecycle from C `malloc`. Each resource type requires the proper acquire/release pair.

### When to copy instead of zero-copy

Zero-copy views are beneficial when data sizes are large and processing is synchronous, fast, and has a clear owner/lifetime. Copying to the Java heap should generally be preferred when:

- The result needs to be cached or returned to an API that does not control lifecycle;
- The native owner will close immediately, while Java still needs to use it;
- There are multiple threads, async tasks, or event queues that are hard to synchronize;
- The dataset is small to medium, where copy cost is negligible compared to use-after-free risk;
- It cannot be guaranteed that all aliases are reclaimed before native free.

Decision rule: **zero-copy is only safe when ownership, lifetime, bounds, and concurrency are all clearly defined**. If not, copy.

## 9. Designing a Java `AutoCloseable` for a C-Owned Allocation

A good wrapper class should have the following characteristics:

- **One owner instance per native allocation** or a ref-counted shared ownership protocol; do not let multiple wrappers free the same block.
- **Do not expose the raw pointer** or a long-lived `ByteBuffer` if use-after-close cannot be controlled.
- Have a clear state **OPEN → CLOSING → CLOSED**; `close()` does not run while an operation is using the buffer.
- If the wrapper chooses an idempotent `close()`, the implementation must guard with locking/atomic state, **not assuming `Arena.close()` is also idempotent**.
- Any failure during allocation/constructor before handing off ownership must roll back and call the right deallocator.
- `close()` calls cleanup with the right allocator and on the right thread. `Arena.ofConfined()` may only be closed by the owning thread; if multithreading is needed, consider `Arena.ofShared()` and synchronize closing.
- If the library has `retain/release`, the wrapper maintains the right ref count and only destroys the data when the ref-count actually reaches zero.
- Before releasing, wait for C and Java tasks still holding aliases to finish; define who waits and who signals.
- If the native deallocator can report errors, define how errors are propagated; do not silently treat a failed cleanup as freed.
- Test **double-close**, **use-after-close**, allocation failure, I/O errors, concurrent consumers, and the case where the native API only returns a borrowed view.

Example of a well-directed API design:

```java
// API idea: not yet a complete implementation.
try (OwnedNativeBuffer owner = openNativeBuffer()) {
    owner.useSynchronously(buffer -> {
        // Only borrow the ByteBuffer within this callback.
        // Do not store in a field or return the reference outside.
        return consume(buffer);
    });
} // Wait for in-flight users to finish, then call native release.
```

The callback structure communicates lifetime clearly, but **does not by itself prevent** a callback from intentionally retaining an alias. For public APIs where callers are hard to trust, you can provide read-only copies, return Java primitives/arrays, or enforce synchronized handle checks. An arbitrary raw pointer cannot be made completely memory-safe by a Java interface alone.

## 10. Common Errors and Fixes

| Error | Cause | Fix |
| --- | --- | --- |
| Native memory leak even though Java heap is fine | C `malloc` with no release path after Java holds the buffer | Identify owner; `AutoCloseable` and correct native deallocator |
| Double-free/native heap corruption | Java explicit free **and** Arena cleanup/C Cleaner both run | Only one cleanup owner; idempotent guard in wrapper |
| `ByteBuffer` is still reachable but JVM crashes | Native owner called `free` before Java stopped using it | Borrow/lifetime contract; wait for users; copy if needed |
| Calling `free` from a different CRT than the DLL that malloc'd | Allocator/heap mismatch, especially Windows CRT | Call `library_release` or the exact deallocator from the same allocator |
| Using `GetDirectBufferAddress` to free any buffer | An address does not prove ownership or allocation source | Use a controlled opaque owner handle |
| `ByteBuffer.allocateDirect` treated like C `malloc` | Confusing Java-managed direct memory with C-managed memory | Do not native free unless the API explicitly transfers ownership |
| `reinterpret(size)` larger than the actual block | Java does not know the native allocated size | Validate size/ABI; bounded cap; do not guess from pointer |
| `reinterpret` with Arena then still using raw global pointer | FFM scoped view does not revoke all aliases | Do not expose raw pointer; unified cleanup |
| `IllegalStateException` after Arena.close | Using FFM view after scope lifetime | Copy before close; do not retain scoped ByteBuffer |
| `WrongThreadException` | Confined Arena used/closed on the wrong thread | Same owner thread or shared arena + coordination |
| Native buffer writes strange bytes to file | C only wrote part of it, Java wrote the entire capacity | Write only initialized length; correct position/limit |
| Corrupted multi-byte data | ByteBuffer default byte order differs from native | `ByteOrder.nativeOrder()` or encoding per file/API contract |
| Crash during async read/write | C or Java frees while I/O is using the pointer | Use completion barrier, reference count, or copy |
| File-mapped memory freed with `free` | Acquisition/release API mismatch | Use `munmap/UnmapViewOfFile` and appropriate handle policy |

One more mistake: **receiving a `ByteBuffer` view from JNI and dropping the Java reference does not guarantee the native block is freed**. For C-owned memory, GC may collect the Java wrapper while C still holds the allocation; without a cleanup protocol, the native heap still leaks. Conversely, freeing C memory while a Java alias is still live is even more dangerous than a leak because it can crash the JVM.

## 11. Native Buffer Integration Checklist

- [ ] Confirm the C source: `malloc`, custom allocator, mapped file, or OS handle.
- [ ] Have a clear table of **owner, borrower, size, read/write rights, release function, lifetime** for each pointer.
- [ ] Check native status before trusting pointer/length; distinguish null/error/partial result.
- [ ] Validate byte count, overflow, byte order, and the number of actually initialized bytes.
- [ ] Do not call `free` on a borrowed pointer or one not belonging to that allocator.
- [ ] For transferred ownership: release **once**, even on exception; roll back if cleanup was not successfully attached.
- [ ] Do not register two deallocators for the same block; no double-free.
- [ ] JNI `NewDirectByteBuffer`: have a clear owner/release contract, do not trust GC to clean up C memory.
- [ ] FFM `reinterpret`: understand this is a restricted view, not an allocation; cleanup action attached to an Arena with the right lifetime.
- [ ] Keep the native library/deallocator loaded until cleanup finishes running.
- [ ] Do not use `slice()`/`duplicate()` after close/free; all aliases share the same backing memory.
- [ ] With FileChannel or native async I/O: wait for operations to complete before releasing.
- [ ] If the caller needs data after release, copy to a Java-owned `byte[]` or owned buffer.
- [ ] Test allocation failure, exception mid-operation, memory leak, double-close, wrong-thread, async completion, native sanitizer/profiler.

## 12. Self-Study Questions

1. Why does holding a Java variable of type `ByteBuffer` not mean the JVM will automatically call `free` for C `malloc`?
2. Does `NewDirectByteBuffer` have a cleanup/deallocator parameter? When JNI returns a direct buffer, who must be responsible for releasing it?
3. A C API returns a pointer to `static const char[]` — is Java allowed to `free` it? Why?
4. If C mallocs using DLL A's allocator and Java calls `free` from DLL B, what risk can occur?
5. Do `ByteBuffer.duplicate()` or `slice()` create an independent native allocation? When the owner frees, can the aliases still be used?
6. In the `NativeMallocOwnershipDemo` example, why must `owner` be closed **before** `libraryLifetime`?
7. Why is `cleanupRegistered` needed to roll back when `reinterpret` fails, and why not call `free` manually once cleanup registration has succeeded?
8. Why is the `byte[]` copy still usable after close, while the scoped direct `ByteBuffer` is not?
9. Does `reinterpret(size, arena, cleanup)` verify that the actual block is `size` bytes long? What can guessing the wrong size cause?
10. With `FileChannel.write`, why must you use `numberOfValidBytes` instead of writing the entire `capacity` by default?
11. A native library retains a pointer for asynchronous writing after the submit function returns. When is Java allowed to close the Arena or free the block?
12. What is the difference between **borrowed**, **transferred**, and **caller-owned** native buffers? Identify the correct side for cleanup in each case.

**Remember:** When Java holds a `ByteBuffer`/`MemorySegment` pointing to memory **allocated by C**, **ownership does not automatically move with the Java reference**. There must be a transparent contract for allocator, size, lifetime, access rights, and deallocator. If C still owns it, Java only borrows and must not free. If ownership transfers to Java, Java is responsible for releasing it using **the exact native API, exactly once**, after all users finish. Use FFM Arena + controlled cleanup, a JNI owner wrapper, or copy to the Java heap to avoid use-after-free.

### Official Documentation

- [Oracle JNI Specification JDK 24 — NewDirectByteBuffer, GetDirectBufferAddress](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html).
- [Oracle JDK 24 — MemorySegment API: reinterpret, asByteBuffer, scope](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Oracle JDK 24 — Arena API: lifetime, cleanup and thread confinement](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html).
- [Oracle JDK 24 — Linker API for downcalls](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JDK 24 — SymbolLookup.libraryLookup lifetime](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Oracle Java `ByteBuffer` API — direct buffers, order, position/limit/capacity](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/nio/ByteBuffer.html).
- [OpenJDK JEP 454 — FFM Final API (JDK 22)](https://openjdk.org/jeps/454).
- [OpenJDK JEP 442 — FFM Third Preview (JDK 21)](https://openjdk.org/jeps/442).

# Receiving Memory Allocated by C and Wrapping It in a Closeable Resource

## Practice exercise: managing native memory ownership with AutoCloseable

When a C function returns a pointer to memory created by `malloc` or a custom allocator, Java can read its contents through the Foreign Function & Memory API (FFM). However, **receiving an address does not mean Java knows how large that region is, how long it lives, or who is responsible for freeing it**. If you use the wrong free function, read after freeing, or forget to release the resource, the program can leak memory, crash the JVM, or corrupt data.

This exercise creates a C library that allocates an integer array and a Java class that implements `AutoCloseable`. When the Java object is closed, a cleanup action registered with `Arena` calls the right C function to return the memory. The example uses **Java 22+**, the finalized version of the FFM API (JEP 454); it does not use the incubator APIs from older JDKs.

After practicing, you should be able to explain:

- The difference between **C-owned memory**, **Java/FFM arena-allocated memory**, and a **borrowed C pointer**.
- Why a C pointer returned through FFM usually has `MemorySegment.byteSize() == 0`, and what conditions allow `reinterpret` into a sized view.
- How to attach a **native cleanup callback** to an `Arena`, so `try-with-resources` closes the resource and calls C release exactly once.
- How to prevent access after close, handle null pointers, handle errors during ownership transfer, and avoid double free.
- The limitations of `Arena.ofConfined()`, multithreading cases, and how to check for native memory leaks.

## 1. Designing the allocation contract before writing Java

The C library in this exercise exposes two functions:

~~~c
int32_t *allocate_numbers(int32_t count);
void release_numbers(int32_t *pointer);
~~~

Contract of this pair of functions:

| What you need to know | Specification |
| --- | --- |
| Who creates the memory? | `allocate_numbers` uses `malloc` on the C side |
| When does it succeed? | `count > 0`, allocates `count * sizeof(int32_t)` bytes and returns a non-`NULL` pointer |
| When does it fail? | Returns `NULL`; Java **must not dereference** |
| Who owns the pointer after C returns? | The Java caller, specifically the `OwnedNumbers` wrapper |
| Value of the `i`-th element? | `i + 1`, with `0 <= i < count` |
| Who frees it? | `release_numbers(pointer)` itself, exactly once |
| When does it expire? | After the wrapper closes and native cleanup has run |
| Which thread may read? | One owning thread according to `Arena.ofConfined()` in the example |

**Do not call `free` from another C library on your own** when the library's allocator returns a pointer without granting that right. On Windows, differences between CRTs or allocators can make cross-freeing invalid. The safe design approach is for C to export a `create/destroy`, `allocate/release`, or `open/close` pair, and for Java to strictly follow that contract.

`MemorySegment.reinterpret` creates an alias/view; it **does not allocate or copy**. It also cannot verify how many bytes C actually `malloc`ed. Java may only declare the size from trustworthy native contract data.

## 2. Writing the C library that allocates and returns memory

Create the file **`native/owned_numbers.c`**:

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

#if defined(_WIN32)
    #define EXPORT __declspec(dllexport)
#else
    #define EXPORT __attribute__((visibility("default")))
#endif

EXPORT int32_t *allocate_numbers(int32_t count) {
    if (count <= 0) {
        return NULL;
    }

    size_t length = (size_t) count;
    if (length > SIZE_MAX / sizeof(int32_t)) {
        return NULL;
    }

    int32_t *data = malloc(length * sizeof(int32_t));
    if (data == NULL) {
        return NULL;
    }

    for (int32_t i = 0; i < count; i++) {
        data[i] = i + 1;
    }

    return data;  // Ownership transfers from C to the caller.
}

EXPORT void release_numbers(int32_t *data) {
    free(data);
}
~~~

Points to understand:

- `count <= 0` is treated as invalid input in this exercise's contract; do not confuse `malloc(0)` potentially returning a special pointer with a usable buffer.
- The `SIZE_MAX / sizeof(int32_t)` check helps prevent overflow in the byte-count multiplication. Include the appropriate headers for types/constants (here `<stdint.h>`, `<stddef.h>`, `<stdlib.h>`).
- `malloc` allocates memory with standard alignment suitable for `int32_t`; C writes all `count` values before returning.
- `release_numbers` receives the **base address** allocated by `allocate_numbers`; do not pass an offset-incremented pointer, and do not call it twice for the same allocation.
- If a real library allocates multiple internal structures, its `destroy` function should clean up those structures itself; Java should not guess the C-side allocation layout.

Working directory:

~~~text
native-ownership/
├── native/
│   └── owned_numbers.c
└── NativeOwnershipDemo.java
~~~

### Building the shared library

Run **one** command matching your operating system, from the `native-ownership` directory:

~~~bash
# Linux:
cc -std=c11 -O2 -fPIC -shared -o native/libowned_numbers.so native/owned_numbers.c

# macOS:
cc -std=c11 -O2 -fPIC -dynamiclib -o native/libowned_numbers.dylib native/owned_numbers.c

# Windows with MinGW-w64:
gcc -std=c11 -O2 -shared -o native/owned_numbers.dll native/owned_numbers.c
~~~

You must install a suitable C compiler and build the library with the same architecture/ABI as the JVM. The library name follows the `System.mapLibraryName("owned_numbers")` convention. Do not use a 32-bit compiler to build a DLL and load it into a 64-bit JVM.

## 3. Java class wrapping the C pointer with AutoCloseable

Create **`NativeOwnershipDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Objects;

public class NativeOwnershipDemo {

    static final class OwnedNumbers implements AutoCloseable {
        private static final MethodHandle ALLOCATE;
        private static final MethodHandle RELEASE;

        static {
            try {
                Path library = Path.of(
                        "native", System.mapLibraryName("owned_numbers"))
                        .toAbsolutePath();

                // Library stays alive until the end of the process; cleanup can still be called.
                SymbolLookup symbols =
                        SymbolLookup.libraryLookup(library, Arena.global());
                Linker linker = Linker.nativeLinker();

                ALLOCATE = linker.downcallHandle(
                        symbols.find("allocate_numbers").orElseThrow(),
                        FunctionDescriptor.of(
                                ValueLayout.ADDRESS,
                                ValueLayout.JAVA_INT));

                RELEASE = linker.downcallHandle(
                        symbols.find("release_numbers").orElseThrow(),
                        FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));
            } catch (Throwable error) {
                throw new ExceptionInInitializerError(error);
            }
        }

        private final Arena arena;
        private final MemorySegment elements;
        private final int length;
        private boolean closed;

        private OwnedNumbers(
                Arena arena, MemorySegment elements, int length) {
            this.arena = arena;
            this.elements = elements;
            this.length = length;
        }

        static OwnedNumbers allocate(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException("count must be > 0");
            }

            // Compute on long, then use the exact count requested from C.
            long bytes = Math.multiplyExact(
                    (long) count, ValueLayout.JAVA_INT.byteSize());
            Arena arena = Arena.ofConfined();

            MemorySegment raw;
            try {
                raw = (MemorySegment) ALLOCATE.invokeExact(count);
            } catch (Throwable failure) {
                arena.close();
                throw new IllegalStateException(
                        "C allocation call failed", failure);
            }

            if (raw.address() == 0L) {
                arena.close();
                throw new OutOfMemoryError("C allocator returned NULL");
            }

            MemorySegment view;
            try {
                // The pointer from C does not carry the array length.
                // reinterpret creates a view with size, scope, and cleanup.
                view = raw.reinterpret(bytes, arena, pointer -> {
                    try {
                        RELEASE.invokeExact(pointer);
                    } catch (Throwable failure) {
                        throw new IllegalStateException(
                                "C release call failed", failure);
                    }
                });
            } catch (RuntimeException | Error failure) {
                // Received pointer but failed to transfer ownership
                // to cleanup: release immediately on the error path.
                try {
                    RELEASE.invokeExact(raw);
                } catch (Throwable cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
                try {
                    arena.close();
                } catch (RuntimeException closeFailure) {
                    failure.addSuppressed(closeFailure);
                }
                throw failure;
            }

            return new OwnedNumbers(arena, view, count);
        }

        int length() {
            return length;
        }

        int get(int index) {
            if (closed) {
                throw new IllegalStateException("Resource already closed");
            }
            Objects.checkIndex(index, length);
            return elements.getAtIndex(ValueLayout.JAVA_INT, index);
        }

        @Override
        public void close() {
            if (closed) {
                return;  // The wrapper class has an idempotent close.
            }

            // Close the Java scope and run C release via the cleanup action.
            arena.close();
            closed = true;
        }
    }

    public static void main(String[] args) {
        OwnedNumbers retained;

        try (OwnedNumbers numbers = OwnedNumbers.allocate(4)) {
            retained = numbers;
            int sum = 0;

            for (int i = 0; i < numbers.length(); i++) {
                sum += numbers.get(i);
            }

            System.out.println("first=" + numbers.get(0));
            System.out.println("last=" + numbers.get(3));
            System.out.println("sum=" + sum);
        }

        // Do not dereference pointer after free: only check the Java guard.
        try {
            retained.get(0);
        } catch (IllegalStateException expected) {
            System.out.println("closed=true");
        }

        retained.close();
        System.out.println("second close=ok");
    }
}
~~~

### Compiling and running

From `native-ownership` after building the shared library:

~~~bash
javac NativeOwnershipDemo.java
java --enable-native-access=ALL-UNNAMED NativeOwnershipDemo
~~~

**Expected** output when built and run properly:

~~~text
first=1
last=4
sum=10
closed=true
second close=ok
~~~

This exercise does not present benchmark numbers; the stdout above is the logical result of C initializing `[1, 2, 3, 4]` and Java summing the elements. The library path is resolved from the **current working directory** when running Java; if running from elsewhere, you must adjust the path or set the working directory. Several FFM operations including native library lookup, linker, and reinterpret are restricted; the `--enable-native-access=ALL-UNNAMED` flag enables access for classes in the unnamed module. For a named module, grant access to the exact module name.

## 4. Explaining the ownership transfer steps

### 4.1. Downcall returns a pointer, not a Java array

`FunctionDescriptor.of(ValueLayout.ADDRESS, ValueLayout.JAVA_INT)` describes a C function taking an `int32_t` and returning a pointer. `ALLOCATE.invokeExact(count)` returns a `MemorySegment` representing the native address. Java does not know the memory size from the address alone, so a segment returned from a pointer typically has **size 0**. Do not read `raw.getAtIndex(...)` directly.

Java knows the valid number of elements through the C contract: `count * sizeof(int32_t)`. After checking that the pointer is non-null, `raw.reinterpret(bytes, arena, cleanup)` creates a view over the **same memory region** with the corresponding size and scope. Declaring `bytes` larger than the actual allocation is dangerous: FFM cannot verify the `malloc` size located outside Java.

### 4.2. Arena specifies lifetime and thread confinement

`Arena.ofConfined()` creates a scope that can only be accessed from the owning thread. The `view` segment is bound to this scope; after `arena.close()`, accessing the view is no longer valid. A confined arena fits this single-threaded exercise and helps prevent accidental reads from other worker threads. In a multithreaded application, `Arena.ofShared()` allows access from multiple threads but **does not synchronize data automatically**; all readers, writers, and native callbacks must be coordinated before closing.

### 4.3. Cleanup action calls native free

In the example, the last argument of `reinterpret(bytes, arena, pointer -> ...)` registers an action to run when the arena scope closes. The callback receives a segment representing the native address prepared for cleanup, then calls `release_numbers` via `RELEASE.invokeExact(pointer)`.

**Do not combine** this cleanup action with a second `release_numbers` call inside `close()`. That causes a double free. Here, the wrapper's `close()` only calls `arena.close()`; closing the arena triggers the C cleanup. Because the C memory was not allocated by the arena, omitting the callback means simply closing the arena **will not free the malloc buffer**.

### 4.4. try-with-resources prevents forgetting to close

`OwnedNumbers` implements `AutoCloseable`, allowing:

~~~java
try (OwnedNumbers numbers = OwnedNumbers.allocate(4)) {
    System.out.println(numbers.get(0));
} // numbers.close() runs automatically, even when the try block throws an exception.
~~~

This is an **illustrative snippet** placed in the same `NativeOwnershipDemo` class or wherever `OwnedNumbers` is accessible. It does not depend on the garbage collector, finalizer, or JVM termination to release native memory. The idempotency of the wrapper's `close()` is implemented with the `closed` boolean; `Arena.close()` itself is not idempotent, and calling close on an arena twice can throw `IllegalStateException`.

### 4.5. Keeping the C library alive long enough

`SymbolLookup.libraryLookup(path, Arena.global())` ties the C library's lifetime to the global arena: the native function `release_numbers` remains available when the cleanup action runs. If you use a separate arena to load/unload the library, you must close all live resources **before unloading** the library containing the native release function. Do not retain a `MethodHandle` pointing to unloaded native code.

## 5. Resource timeline

| State | C memory | Java wrapper | Reading allowed? |
| --- | --- | --- | --- |
| Not yet allocated | Does not exist | Does not exist | No |
| `allocate_numbers` succeeds | Exists, ownership transferred | Checks null/size | Do not read via raw pointer yet |
| `reinterpret` completes | Exists, cleanup attached to arena | `OwnedNumbers` open | Yes, right thread and index |
| Inside `try-with-resources` block | Exists | Uses `get` | Yes |
| Exiting `try` block | `release_numbers` called | `closed=true` after normal close | No |
| Calling `close()` a second time | Already released | Wrapper ignores | No |
| Calling `get()` after close | Already released | Throws `IllegalStateException` | No |

A common source of leaks is allocating in C and then throwing an exception before creating the wrapper. The example handles that path by releasing `raw` if attaching cleanup fails, and closing the temporary arena. In production design, you must control every error path between "C allocated" and "ownership safely transferred". A cleanup callback throwing an exception during `Arena.close()` must also be monitored: you should not assume native release can be retried arbitrarily.

## 6. Owning, borrowing, and transferring: three cases not to confuse

| Pointer source | True owner | Release rule |
| --- | --- | --- |
| Java FFM `arena.allocate(...)` | The arena that created the segment | Close the arena; do not call C free |
| C `malloc`/allocator returning ownership | The Java wrapper after receiving | Use the exact C release once on close |
| C returns a borrowed/static pointer | The C library/object | Java **does not free**; ensure the native owner remains alive |
| C holds a Java-allocated pointer for async processing | Depends on the agreed API protocol | Keep the Java arena alive until C is truly done; close only after completion |

A native API like `get_internal_buffer` may return a pointer not owned by Java. Attaching a `free` callback to that pointer is a serious bug. If an API returns a pointer alongside a length via a struct or out-parameter, Java must read the trustworthy length and validate bounds before reinterpreting. If the data can be reallocated or invalidated by C, do not keep the old view and continue reading.

## 7. Risks and how to verify

**Null pointer:** C may return null due to allocation failure. The wrapper checks `raw.address() == 0L` and does not dereference. If an API uses `NULL` as a valid result for an empty array, you must adjust the contract and Java representation accordingly; this exercise rejects `count <= 0`.

**Size mismatch:** `reinterpret(4096, ...)` does not make C actually `malloc` 4096 bytes. Declaring a size larger than the allocation, or using the wrong layout or offset, can cause corruption/crashes even though `MemorySegment` checks bounds against the Java-declared size.

**Wrong allocator:** Memory allocated by a C custom allocator must be returned with the exact matching native destroy/release function. On some environments, using `free` from a different CRT or `delete` on `malloc` memory is undefined behavior.

**Use-after-free:** The Java API in this exercise does not expose the raw pointer and checks `closed` before `get`. However, if you have passed the raw pointer to other native C code, Java's scope cannot protect native code from dereferencing after free. You must wait for all native uses to finish before closing.

**Double free:** The `reinterpret` cleanup and `close` code must not both call C release. Each resource must have **a single responsible owner**. If multiple views share one allocation, they must not register independent cleanups that free the same address.

**Access from another thread:** The example is confined/single-threaded. If another thread calls `get`, FFM may throw `WrongThreadException`. Avoid turning an unsynchronized `closed` boolean into a multithreaded lifecycle manager. If shared access is needed, you need an ownership/concurrency protocol and must ensure closing does not happen while native downcalls, readers, or writers are still using the pointer.

**Did native cleanup actually run?** Having `closed=true` and post-close reads rejected does not by itself prove C is not leaking. Use AddressSanitizer, Valgrind (on supported platforms), a native memory profiler, or allocate/release counters in the C library. Measure across many allocate/close cycles and observe stable memory after warmup.

## 8. Self-check exercises

1. **Bounds:** Change `allocate(4)` to `allocate(8)`; the correct sum is `36`. Try `get(8)` before closing: it should throw `IndexOutOfBoundsException`.
2. **Invalid input:** Call `allocate(0)`: it should throw `IllegalArgumentException` without allocating in C.
3. **Exception safety:** Inside the try-with-resources block, intentionally throw a Java exception after the first read; verify cleanup is still called.
4. **Idempotent close:** Keep a reference variable to the wrapper and call `close()` again; verify C does not release the same pointer twice.
5. **Borrowed pointer:** Try sketching a C API that returns static memory; explain why `release_numbers` must not be used for this pointer.
6. **Complex struct:** If C returns an opaque handle containing multiple allocations, create a `destroy_handle` function that frees internals in the proper order; Java only attaches the destroy callback once.
7. **Multithreading:** If the wrapper must be passed to another thread, determine how to choose the scope and coordinate closing; do not just change `ofConfined()` to `ofShared()` and assume all accesses are safe.

## 9. Checklist before using with a real native library

- [ ] Clearly identified whether the pointer is owned or borrowed and who must release it?
- [ ] Using the exact release function from the same library/allocator that created the pointer?
- [ ] Checked null, element count, overflow, layout, byte order, and alignment?
- [ ] Only reinterpreting according to the size C actually guarantees?
- [ ] Registered **one** cleanup action or used one exact close path?
- [ ] Wrapper restricts leaking aliases/raw pointers to external code?
- [ ] Every error between alloc and attaching ownership has a cleanup path?
- [ ] `try-with-resources` is used at the caller and native double close is avoided?
- [ ] Clear policy for thread confinement, callbacks, and async behavior?
- [ ] Used native tools to check for leaks, double free, and use-after-free?

## Further reading

- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): Official API since Java 22.
- [Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): `reinterpret`, segment scope, spatial and temporal safety.
- [Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): lifecycle, confined/shared, and `close()`.
- [Java SE 24 — Linker](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Linker.html): native downcall handle and function descriptor.
- [dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/): C pointers, segment size 0, and cleanup actions.

**Core principle:** A good native-memory wrapper is a **resource owner with a clear contract**: it knows the address, size, access scope, and exact single release action. `AutoCloseable` together with `try-with-resources` brings that release responsibility into the verifiable lifecycle of Java code.
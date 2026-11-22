# Returned Pointers in FFM: Zero-Length MemorySegment and Explicit Length Contracts

When Java calls a C library through the Foreign Function & Memory API (FFM) and receives a value of type `char *`, `int32_t *`, or `void *`, the JVM usually **only knows the starting address**, and does not know how many bytes are actually permitted to be read, who owns the memory, or how long it remains alive. In standard FFM from **JDK 22**, a pointer returned from a foreign function under `ValueLayout.ADDRESS` is represented by Java as a **`MemorySegment` with `byteSize() == 0`**. This is an intentional safety boundary, not a sign that C allocated an empty buffer.

To read the contents behind the pointer, you must obtain both the **length contract** and the **ownership/lifetime contract** from the C API, verify both, and only then expand the view with `reinterpret(...)`. Expanding is a **restricted operation and unsafe if declared incorrectly**: FFM checks against the size you *declare*, and has no knowledge of how large the actual allocation is. A `reinterpret(1_000_000)` does not make the native buffer grow by one million bytes.

This article belongs to the **Pointers and Ownership** group, explaining why the size is zero, distinguishing a null address from empty data, ways of passing length, overflow/bounds checks, creating scoped views, freeing native memory, and avoiding use-after-free. At the end of the article there is a **complete Java 22+ + C11 example** for two scenarios: a borrowed pointer to a `static const` array with length via an out-parameter, and a `malloc`-allocated pointer that must invoke the matching deallocation function. Build commands for Linux, macOS, and Windows are separated clearly; Java 17/21 code does not use this exact API.

## 1. A zero-length pointer means “unknown size”, not “0-element array”

An imaginary FFM call to C:

~~~c
/* C snippet illustrating a declaration, not a complete program. */
const int32_t *get_items(int32_t *out_count);
~~~

Suppose C returns the address `0x12340000` and writes `*out_count = 3`. When Java receives the pointer with `ValueLayout.ADDRESS`, what FFM knows and **does not know** is:

| Information | Present in raw `MemorySegment`? | Notes |
| --- | --- | --- |
| Pointer address | Yes, via `address()` | A native address may be non-zero |
| `byteSize()` | Yes, but equals **0** | The API does not measure C buffers automatically |
| Element count | **No** | Must be obtained from `out_count`, return code, metadata, or another contract |
| Size of each element | Not inferred from the pointer | Must know the C type/ABI, e.g. 4-byte `int32_t` |
| Valid byte count | **No** | Need to compute checked `count * elementSize` |
| Read-only or writable | Not guaranteed by `ADDRESS` alone | C `const` is an API contract, not automatically enforced as a read-only Java view |
| Lifetime | **No** | The pointer may point to static data, a malloc block, a temporary region, or a native-managed object |
| Free function | **No** | Must determine `free`, `destroy_*`, no free, or ownership transfer |
| Thread safety | No | C may mutate/free from another thread |

In JDK 22, this kind of raw pointer segment is typically associated with the **global scope (always-alive)**, because the JVM does not yet know the native allocation's lifetime. That **does not mean** the C region is always alive. It only says Java lacks the information to expire the raw address automatically. Obtaining a scoped view managed by you prevents Java access after the arena closes, but **does not** prevent C from freeing the memory earlier.

~~~text
C:
    pointer p --------------------> [ 7 ][11 ][13 ]
                                          3 x int32_t
    *out_count = 3

FFM:
    raw = address p
    raw.byteSize() == 0        (cannot read elements)
             |
             | API contract: count=3, sizeof(int32_t)=4,
             | data remains alive until the library is unloaded
             v
    raw.reinterpret(12, arena, null)
             |
             v
    view.byteSize() == 12      (Java can bounds-check 0..11)

No step asks the JVM "how many bytes does the C buffer actually have?"
~~~

A `MemorySegment` of size 0 can be **passed as an opaque pointer** to another foreign function accepting `ADDRESS`, such as a `free_items(pointer)` function. However, `raw.get(ValueLayout.JAVA_INT, 0)` is invalid: reading 4 bytes exceeds the 0 bound, typically throwing `IndexOutOfBoundsException`. This rule forbidding immediate reads is a protective feature so the caller must explicitly state the decision “I know how many bytes there are”.

## 2. Distinguishing four commonly confused cases

- **Null pointer:** `MemorySegment.NULL` represents address 0; when C returns `NULL` through an address layout, Java receives the null-address representation. Do not dereference it. Null may mean an error, no data, or a valid case **only when the API specifies it**.
- **Non-null pointer, `byteSize()==0`:** the address may point to an entire large array, but the spatial bound of the raw view is unknown; you must query/know the length before reading.
- **Buffer with length 0:** the API may allow returning `NULL` or a non-null sentinel; at the application level, there are 0 elements. You must not and need not read the first element.
- **NUL-terminated string:** a C string may be delimited by a 0 sentinel byte instead of an out-parameter length, yet Java still **does not know the NUL position** from a raw pointer alone. Reading until NUL without a cap is an operation whose safety cannot be guaranteed.

`raw.address() == 0L` is the null-address check that matches the native-address example. Do not treat `raw.byteSize()==0` as “no data”, because all returned pointers without a target layout can have size 0.

In a Java program, a `null` reference and `MemorySegment.NULL` also differ. A `MethodHandle` declares the carrier `MemorySegment.class` for `ADDRESS`; do not pass `(MemorySegment)null` or cast an arbitrary integer to a pointer without understanding the contract. C `NULL` is a pointer value, not a Java `null` object reference.

## 3. Five types of length contracts for C pointers

| C API pattern | Where length comes from | What must be verified |
| --- | --- | --- |
| `const T *get_items(size_t *out_count)` | Out-parameter writes `count` | Function always initializes count, unit is **elements** or bytes, how long the pointer stays alive |
| `const void *get_data(size_t *out_bytes)` | Out-parameter writes byte count | Do not multiply by `sizeof(T)` when count is already in bytes |
| `size_t read_data(void *dst, size_t capacity)` | Return value or out-written | Do not read past capacity, distinguish bytes actually written from bytes needed |
| `struct Buffer { void *data; size_t size; }` | `size` field paired with pointer in struct | Padding, alignment, ABI, pointer/data lifetime, ownership |
| `const T *get_fixed_array(void)` | Fixed contract, e.g. exactly 8 `T` | Native API versioning, size of C `T` on target |
| `const char *get_name(void)` | NUL sentinel | Encoding, maximum scan limit, whether terminator truly exists within valid region |
| `void *malloc(size_t bytes)` | Size requested by caller | On success allocation satisfies request; caller must free using matching allocator family |
| `void *map_region(size_t *mapped_bytes)` | Native returns mapped length | Page/memory mapping, unmap with matching size and owner |

**The first question is always “in what unit is the length measured?”** With `int32_t *` returning 3 elements, the byte size is `3 * 4 = 12`. With `char *` returning `out_bytes=3`, the total is 3 bytes, **not** 3 Java `char`s (a Java `char` is 2 bytes / UTF-16 code unit). With `size_t count`, use the layout matching the OS C ABI (32/64-bit); do not cast blindly to `int` and assume the number remains intact.

If the API provides no length, has no reliable sentinel/bounds, and has no other guaranteed limit, **arbitrary safe reading is impossible**. The fix usually belongs in the C interface: add an out-parameter, a `get_size(handle)` function, a `{pointer,length}` struct, or a copy-into-buffer API supplied by Java with capacity. “Guessing until a read succeeds” is not a solution.

### 3.1. Case where count accompanies the pointer

~~~c
/* Snippet illustrating C contract, not standalone runnable code. */
const int32_t *get_values(int32_t *out_count);
/* Contract:
   - out_count is non-NULL and written on every return path.
   - count >= 0, measured in number of int32_t elements.
   - count > 0 => pointer != NULL and points to at least count elements.
   - if borrowed, the caller MUST NOT free.
   - data is immutable while the caller reads.
*/
~~~

In Java, read `out_count` from an `Arena`-allocated segment, then validate count and pointer. Do not use an uninitialized `count` when C returns an error. Decide explicitly on the `count==0` case: you can return an empty result without `reinterpret` or dereferencing. For large counts, compute the byte count using overflow-checked multiplication.

### 3.2. Case where the pointer is just an opaque handle

~~~c
typedef struct Context Context;
Context *context_open(void);
void context_close(Context *ctx);
int context_execute(Context *ctx, int value);
~~~

If `Context` is an opaque type and C only allows passing the pointer back to native functions, Java **does not need `reinterpret`** and should not read the memory behind it. A size-0 `MemorySegment` is the appropriate representation for a `Context *` handle; `context_execute` accepts `ADDRESS` back and `context_close` frees it per contract.

Important: not *every pointer* is a buffer. Do not feed an opaque pointer to `MemorySegment.get(JAVA_INT,0)` just to inspect “the first field”; the C struct layout may be private, change across versions, and is not part of Java's contract.

## 4. Why is `reinterpret(...)` a dangerous operation?

JDK 22 provides notable overloads:

~~~java
// Illustrative JDK 22 API signatures:
MemorySegment reinterpret(long newSize);
MemorySegment reinterpret(long newSize, Arena arena,
                          Consumer<MemorySegment> cleanup);
MemorySegment reinterpret(Arena arena,
                          Consumer<MemorySegment> cleanup);
~~~

These are **API declaration snippets**, not standalone Java code to copy into a class. `reinterpret(long)` resets the size while keeping the current scope (raw addresses usually carry the global scope). `reinterpret(long,Arena,Consumer)` sets **a new byte size and a new scope** bound to the arena, optionally registering a cleanup action if the ownership contract allows it.

These overloads are **restricted methods**. If the caller module has not been granted native access, the JDK may throw `IllegalCallerException`. When the byte size is declared incorrectly, `MemorySegment`'s bounds checker only checks within the **newly declared** region and cannot verify the C allocation. Reading `ptr.reinterpret(1024)` when C only allocated four bytes can still cause native memory corruption/JVM crash.

~~~java
// Illustrative snippet: only safe if C guarantees at least 12 bytes,
// non-null pointer, int32_t ABI matches JAVA_INT, and memory is alive.
MemorySegment raw = /* pointer from foreign function */;
MemorySegment view = raw.reinterpret(12L, arena, null);
int third = view.getAtIndex(ValueLayout.JAVA_INT, 2);
~~~

What must be true **before** reading `third`:

1. The pointer is non-null.
2. C actually has at least 3 `int32_t` elements in contiguous memory (at least 12 bytes).
3. `sizeof(int32_t)==4` and alignment matches `JAVA_INT` on the target ABI.
4. The buffer is alive and not freed/reallocated from another thread.
5. The caller is on a valid thread of `arena`, and the scope is not closed.
6. No concurrent mutator causes a data race under C language rules.
7. `reinterpret` is granted native access under JDK policy.

None of `reinterpret` checks items 2–4 automatically. Therefore “wrapping a pointer in a segment” is not a JVM safety guarantee for external data.

### 4.1. Changing scope helps but does not replace the native contract

With `Arena.ofConfined()`, a derived segment can be created using:

~~~java
MemorySegment bounded = raw.reinterpret(12, arena, null);
~~~

After `arena.close()`, Java accesses to `bounded` are rejected by scope. However, if C calls `free(raw_pointer)` **before** the arena closes, `bounded` may still appear alive even though the memory has been reclaimed: this is a use-after-free that Java's bounds/lifetime checks cannot detect. **Native free timing must be coordinated with the Java scope.**

Similarly, `reinterpret(12, arena, null)` **does not free** C data when the arena closes, because the cleanup action is `null`. If malloc-allocated data is returned for Java to own, you still must call native `destroy/free` exactly once. You can register a cleanup action on the arena, but only when you are certain about the allocator, library lifetime ordering, free count, and how long callbacks continue using the pointer.

## 5. Before expanding size: check element count, multiplication, and alignment

Standard formula for a contiguous array:

~~~text
byteCount = elementCount * elementByteSize
Conditions:
elementCount >= 0
elementCount <= LIMIT per contract
elementByteSize > 0
byteCount computed via overflow-checked multiplication
pointer != NULL if elementCount > 0
C region contains >= byteCount bytes and stays alive during access
~~~

With Java 22+:

~~~java
// Illustrative snippet, requires count to be within a checked range.
long bytes = Math.multiplyExact(
        (long) count, ValueLayout.JAVA_INT.byteSize());
~~~

`ValueLayout.JAVA_INT.byteSize() == 4`; `count==3` gives `bytes==12`. Using `Math.multiplyExact` catches Java overflow if the code changes to accept a `long` count or a more complex element layout. With a non-negative `int` count, multiplying by 4 in `long` will not exceed 64 bits, yet you still need a **business/cap limit** (for example, at most 1,000,000 elements) to avoid borrowing gigabytes of memory from an untrusted pointer.

If C outputs count via `size_t`, you cannot always read it with `ValueLayout.JAVA_INT` or `JAVA_LONG`. Consult `Linker.nativeLinker().canonicalLayouts().get("size_t")` on the target, and check the unsigned range before converting to a Java count/byteCount. On Windows x64, C `long` is typically 32-bit whereas Java `long` is 64-bit; do not choose a descriptor by “same name long”.

### 5.1. Alignment is a separate obligation

A pointer may point into a packed/unaligned region. `getAtIndex(ValueLayout.JAVA_INT,i)` requires an address compatible with the layout's alignment. When a C API genuinely guarantees an `int32_t *` to a normal, properly allocated array, element alignment usually matches. For packed wire formats or bytes at odd offsets, `JAVA_INT_UNALIGNED` may be needed **if the data is truly unaligned**, while still satisfying bounds and the right byte order.

Do not use `*_UNALIGNED` to paper over a “wrong count” or invalid pointer error. Unaligned layouts relax Java's alignment constraint; they do not enlarge the C allocation.

### 5.2. When using structs and stride

If C returns `struct Item *items`, you need both count and **`sizeof(struct Item)`** plus ABI field offsets. You cannot assume `itemSize == sum of field sizes` because the compiler may insert padding. For a struct array, `byteCount = count * sizeof(Item)`, not necessarily count times the first field's size alone. Use `MemoryLayout.structLayout` with proper padding, and verify `offsetof` and `sizeof` from the C compiler.

## 6. Ownership: who may read, who may write, and who must free?

| Pointer type | Who owns the memory | What may Java do? | How to clean up? |
| --- | --- | --- | --- |
| **Borrowed static** | C library; `static const` lives while binary remains loaded | Read while library is alive; do not mutate/free | Java does not call `free`; ensure library stays loaded while reading |
| **Borrowed view from object/handle** | C object or native context | Read/write per contract only; do not use after destroy/realloc | Close owner handle after all views/callbacks finish |
| **Caller-owned malloc block** | Ownership transfers to Java caller | Read/write within cap; free exactly once | Call `destroy_*`/`free_*` from matching allocator library |
| **Transfer-to-native** | C takes ownership after Java calls API | No longer use/free from Java after transfer | Per native contract; Java must mark handle as transferred |
| **Pointer to Arena-allocated buffer** | Java arena owns the memory | Native only borrows within valid window | `Arena.close()`, after native stops using the pointer |
| **Opaque context pointer** | Native API owns context via create/destroy | Pass opaque handle to C; do not dereference | `context_destroy` per contract |

**`Arena.close()` does not mean “`free` all addresses seen inside the arena”.** It frees memory managed by the arena and runs properly registered cleanup actions. If C uses `malloc` and returns a pointer, merely calling `raw.reinterpret(bytes, arena, null)` has no malloc cleanup; you still must invoke the destroy/free required by the C API.

**Do not use Java `Cleaner` as the sole cleanup path** when a resource must be closed promptly. `try-with-resources` and `close()` in the Java API are a more deterministic design, especially for socket/DB/GPU resources, native threads, and callbacks. A `Cleaner` can serve as a fallback with separate state/ownership tracking, but it has no guaranteed GC schedule.

### 6.1. Why should the C library that allocated memory be the one to free it?

A C library may use a custom allocator, a different CRT on Windows, a private arena, a slab/pool, or a reference-counted native API. Calling a `free` from a mismatched allocator can cause undefined behavior. A good contract should provide a pair:

~~~c
/* Illustrative C API snippet (not a full program). */
int32_t *create_items(int32_t count);
void destroy_items(int32_t *data);
~~~

Java keeps the opaque/raw pointer to pass back to `destroy_items` via `ValueLayout.ADDRESS`. Never double-free; after destroy, derived segments may still hold the same address in their representation but **are no longer valid to dereference**.

## 7. Complete example: a C library with both borrowed and owned pointers

We write a C library `pointers` with two APIs:

1. `borrow_numbers(int32_t *out_count)` returns a pointer to `static const int32_t[3] = {7,11,13}`, while writing `out_count = 3`. Java **must not free** the pointer.
2. `create_numbers(int32_t count)` allocates a `malloc` array of `count` elements (in the example `count=4`), filled with `10,20,30,40`; Java must call `destroy_numbers(ptr)` exactly once.

These are two common scenarios with different lifetimes. Java 22+ uses FFM downcalls; because C is a plain C ABI, there is no `JNIEnv`, `jobject`, or generated JNI header.

Directory structure:

~~~text
ffi-returned-pointer/
├── native/
│   └── pointers.c
├── src/
│   └── PointerLengthDemo.java
└── build/
    ├── classes/
    └── lib/
~~~

### 7.1. Complete C11 file: `native/pointers.c`

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

#if defined(_WIN32)
#define API_EXPORT __declspec(dllexport)
#else
#define API_EXPORT __attribute__((visibility("default")))
#endif

/* Contract: library-owned data, read-only, count=3, do not free.
   Valid only while the library binary remains loaded. */
API_EXPORT const int32_t *borrow_numbers(int32_t *out_count) {
    static const int32_t ITEMS[3] = {7, 11, 13};

    if (out_count == NULL) {
        return NULL;
    }

    *out_count = 3;
    return ITEMS;
}

/* Contract: count must be in 1..1000000.
   On success returns a buffer of exactly count elements.
   Ownership transfers to caller; call destroy_numbers exactly once. */
API_EXPORT int32_t *create_numbers(int32_t count) {
    if (count <= 0 || count > 1000000) {
        return NULL;
    }

    if ((size_t) count > SIZE_MAX / sizeof(int32_t)) {
        return NULL;
    }

    int32_t *data = malloc((size_t) count * sizeof *data);
    if (data == NULL) {
        return NULL;
    }

    for (int32_t i = 0; i < count; ++i) {
        data[i] = (i + 1) * 10; /* max count cap prevents overflow */
    }
    return data;
}

API_EXPORT void destroy_numbers(int32_t *data) {
    free(data);
}
~~~

**C contract to read carefully:**

- `borrow_numbers` requires `out_count != NULL`; on success it writes three elements exactly and returns a non-null pointer to `static const` data. Java may read but must not write, and must not call `destroy_numbers` on the borrowed pointer.
- `create_numbers` returns `NULL` when count is outside 1..1,000,000 or allocation fails; there is no “empty `malloc(0)` array” in the sample API. When non-null, the memory region holds **exactly count `int32_t` values**, contiguous and properly aligned. `count=4` produces 10,20,30,40. `SIZE_MAX / sizeof(int32_t)` is checked before size multiplication.
- `destroy_numbers` is the only matching release function for pointers **returned by `create_numbers`**. `free(NULL)` in C is valid, yet Java should still manage ownership so it never calls destroy on a borrowed pointer or double-frees.
- C `int32_t` is exactly 32 bits per `stdint.h` where supported; Java uses `ValueLayout.JAVA_INT` for 4 bytes on the deployment ABI. Layouts of structs, `size_t`, or C `long` in other APIs must be verified separately.
- In this API, `create_numbers` does not retain the pointer for another thread and `borrow_numbers` does not mutate static data. Therefore Java can read the elements within a deterministic scope without extra native synchronization.

The code above is a **complete C library**, without `main`; compile it into `.so`/`.dylib`/`.dll`. No `-I"$JAVA_HOME/include"` is needed because this is a plain C ABI without JNI headers.

### 7.2. Java JDK 22+: `src/PointerLengthDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class PointerLengthDemo {
    private static final int MAX_ELEMENTS = 1_000_000;

    private PointerLengthDemo() {
    }

    private static long checkedBytes(int count) {
        if (count < 0 || count > MAX_ELEMENTS) {
            throw new IllegalArgumentException("invalid element count");
        }
        return Math.multiplyExact(
                (long) count, ValueLayout.JAVA_INT.byteSize());
    }

    public static void main(String[] args) throws Throwable {
        Path library = Path.of("build", "lib",
                System.mapLibraryName("pointers")).toAbsolutePath();

        try (Arena libraryArena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, libraryArena);

            // const int32_t *borrow_numbers(int32_t *out_count)
            MethodHandle borrow = linker.downcallHandle(
                    symbols.find("borrow_numbers").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS));

            // int32_t *create_numbers(int32_t count)
            MethodHandle create = linker.downcallHandle(
                    symbols.find("create_numbers").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            // void destroy_numbers(int32_t *data)
            MethodHandle destroy = linker.downcallHandle(
                    symbols.find("destroy_numbers").orElseThrow(),
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS));

            // PART A: borrowed pointer with length from out-parameter.
            try (Arena readScope = Arena.ofConfined()) {
                MemorySegment outCount =
                        readScope.allocate(ValueLayout.JAVA_INT);
                MemorySegment raw =
                        (MemorySegment) borrow.invokeExact(outCount);

                int count = outCount.get(ValueLayout.JAVA_INT, 0);
                long byteCount = checkedBytes(count);

                if (count == 0) {
                    throw new IllegalStateException(
                            "demo expected 3 elements");
                }
                if (raw.address() == 0L) {
                    throw new IllegalStateException(
                            "null pointer with positive count");
                }

                System.out.println(
                        "borrowedRawSize=" + raw.byteSize());
                System.out.println("borrowedLength=" + count);

                // C guaranteed count int32_t elements and static lifetime.
                MemorySegment view =
                        raw.reinterpret(byteCount, readScope, null);

                StringBuilder values = new StringBuilder();
                long total = 0;
                for (int i = 0; i < count; ++i) {
                    int value =
                            view.getAtIndex(ValueLayout.JAVA_INT, i);
                    if (i != 0) {
                        values.append(',');
                    }
                    values.append(value);
                    total += value;
                }
                System.out.println("borrowedValues=" + values);
                System.out.println("borrowedSum=" + total);
                // DO NOT destroy/free raw: C still owns the static data.
            }

            // PART B: owned pointer allocated with malloc, must be released.
            try (Arena ownedScope = Arena.ofConfined()) {
                int count = 4;
                MemorySegment raw =
                        (MemorySegment) create.invokeExact(count);

                if (raw.address() == 0L) {
                    throw new IllegalStateException(
                            "native allocation failed");
                }

                boolean released = false;
                try {
                    long byteCount = checkedBytes(count);
                    System.out.println(
                            "ownedRawSize=" + raw.byteSize());
                    System.out.println("ownedLength=" + count);

                    MemorySegment view =
                            raw.reinterpret(byteCount, ownedScope, null);

                    long total = 0;
                    for (int i = 0; i < count; ++i) {
                        total +=
                                view.getAtIndex(ValueLayout.JAVA_INT, i);
                    }
                    System.out.println("ownedSum=" + total);
                } finally {
                    // Raw pointer has size 0 but is valid for ADDRESS.
                    // Do not use view after this destroy call.
                    destroy.invokeExact(raw);
                    released = true;
                }
                System.out.println("released=" + released);
            }
        }
    }
}
~~~

**Runnability:** this is a complete Java file with no package; class and filename match. Requires `JDK 22+`. Because `main` calls `MethodHandle.invokeExact`, declaring `throws Throwable` avoids separate checked-throwable handling in the example. The native call signatures are exact: `ADDRESS` maps to Java carrier `MemorySegment`, `JAVA_INT` is `int`; `destroy` returns `void`.

**Why are there two arenas?** `libraryArena` manages the lifetime of `SymbolLookup.libraryLookup` and the symbols/library; it **outlives** both sections that use native pointers, so the C code and `static const` data have not been unloaded. `readScope` sets an access deadline for the borrowed view. `ownedScope` sets a deadline for the owned view; it **does not** free C memory when cleanup is `null`. `destroy.invokeExact(raw)` in `finally` performs the actual C free before the scope/lookup closes.

**Why pass `raw` to destroy instead of `view`?** C `destroy_numbers` needs the original base address returned by `malloc`. `raw` remains a size-0 segment carrying the same address and can be passed as `ADDRESS`. Passing a sliced region at a non-zero offset or an advanced pointer different from the original base address to `free` is wrong. In the example there is no pointer slicing so both share the same address, yet the rule remains to keep the **base allocation pointer** separately for cleanup.

**Safety note:** After `destroy.invokeExact(raw)`, a Java view still inside `ownedScope` must not be dereferenced. The scope check does not know that C free has already occurred. The example never lets `view` escape the `try/finally` block; in production applications, wrap the pointer/view in an `AutoCloseable` with state preventing use-after-close or use a suitable arena cleanup action to tie Java lifetime tightly to C lifetime.

## 8. Compile and run commands on three operating systems

Run the commands from the root directory `ffi-returned-pointer`. Requires JDK **22 or newer** to compile standard `java.lang.foreign`, a C compiler with `stdint.h`/`int32_t`, and a native library architecture matching the JVM. The Java commands use the classpath, so grant native access to the **unnamed module**:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes PointerLengthDemo
~~~

`--enable-native-access=ALL-UNNAMED` is required because `libraryLookup`, `downcallHandle`, and `reinterpret` are restricted operations. For a **named module**, use the specific module name. `--enable-preview` is not needed on JDK 22+. Java 17 (FFM incubator) and Java 21 (FFM preview) cannot run this code as-is.

### 8.1. Linux (GCC or Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  native/pointers.c -o build/lib/libpointers.so

javac -d build/classes src/PointerLengthDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes PointerLengthDemo
~~~

### 8.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/lib

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  native/pointers.c -o build/lib/libpointers.dylib

javac -d build/classes src/PointerLengthDemo.java

java --enable-native-access=ALL-UNNAMED \
  -cp build/classes PointerLengthDemo
~~~

### 8.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\lib

cl /nologo /W4 /O2 /LD native\pointers.c ^
  /link /OUT:build\lib\pointers.dll

javac -d build\classes src\PointerLengthDemo.java

java --enable-native-access=ALL-UNNAMED ^
  -cp build\classes PointerLengthDemo
~~~

The Windows commands use **Command Prompt**, with `^` for line continuation. Run inside a Visual Studio Developer Command Prompt configured with `cl` for the x64 target. `System.mapLibraryName("pointers")` returns the platform-appropriate filename (typically `libpointers.so`, `libpointers.dylib`, or `pointers.dll`); Java constructs the **absolute path** to the built file. Renaming a binary's extension does not change its ABI.

### 8.4. Expected stdout

With a matching-ABI native binary and the source above, the exact stdout is:

~~~text
borrowedRawSize=0
borrowedLength=3
borrowedValues=7,11,13
borrowedSum=31
ownedRawSize=0
ownedLength=4
ownedSum=100
released=true
~~~

Reason: returned pointers (without a target layout) have a size-0 segment; `borrow_numbers` writes count 3 and provides 7+11+13=31; `create_numbers(4)` allocates 10+20+30+40=100; `finally` calls `destroy_numbers` properly and prints the result afterward. The code does not print pointer addresses because addresses vary by process/ASLR. This stdout is derived from the source; confirming at runtime requires actually running the compiler/Java on the target platform.

### 8.5. Checking exported symbols

Linux:

~~~sh
nm -D --defined-only build/lib/libpointers.so
~~~

You should see:

~~~text
borrow_numbers
create_numbers
destroy_numbers
~~~

On macOS use `nm -gU build/lib/libpointers.dylib` (Mach-O typically prefixes names with `_`); on Windows use `dumpbin /exports build\lib\pointers.dll`. If Java reports a missing symbol, check the export macro, exact function/ABI name, library path, and compiler architecture. If `UnsatisfiedLinkError` occurs on load, that is not a sign that the pointer's `byteSize` is wrong — the program has not even called C successfully yet.

## 9. Why can't you “discover the size by reading until an error”?

A common misconception: since `MemorySegment` throws `IndexOutOfBoundsException` when accessing past its size, one could `reinterpret` to a huge size and scan until catching an exception. **False.**

The bounds check only applies **to the number of bytes you supplied to `reinterpret`**. If the actual C allocation is 12 bytes and you declare 1,000,000 bytes, Java trusts that the 1,000,000-byte window is permitted; reading the 13th byte may cross into unowned memory, read sensitive data, or crash the process **without** throwing a catchable exception. Java has no allocator metadata to verify that “12 bytes is the real end”.

~~~text
C actually allocated:  [ 0 .......... 11 ]  (12 bytes)
Java misdeclared:      [ 0 ................................ 999999 ]
                                       ^ from 12 onward is unsafe
Java bounds checker:   only knows 0..999999, does not know 12
~~~

If an API only returns `void*` without recording length, provides no way to query length, and has no guaranteed sentinel/metadata, the right design fix is to change the C API or wrapper. You cannot write a “generic safe pointer length detector” over a raw address. C debugger tools or OS memory maps also cannot replace an allocation length contract; a mapped region can be larger than the allocation the app is actually allowed to use.

### 9.1. Pointer+length must also come from the same consistent snapshot

Even when C returns `pointer` together with `count`, the two values may no longer match if another native thread just called `realloc`/`free` or modified the buffer. The contract must guarantee:

- The pointer does not change until the caller finishes reading, or is protected by a lock/retain-release.
- Count matches the **snapshot** of that buffer, not the count of a newer buffer.
- No concurrent writer violates data-race rules.
- Ownership is not transferred away or freed mid-read by a callback.

A common pattern for mutable data is a `copy_into(dst,capacity)` API where Java supplies the buffer, or a handle with `retain/release` functions, instead of an unprotected borrowed pointer.

## 10. When a pointer points to a char buffer or C string

Contracts for `char *` are often easier to get wrong because there are multiple ways to count:

| Data | Correct length | Hazard |
| --- | --- | --- |
| `unsigned char *bytes` + `size_t len` | Number of **bytes**, may contain `0x00` | Using `strlen` truncates at the first NUL |
| `char *utf8` + `byte_len` | Number of UTF-8 bytes | Not Java's `String.length()` (UTF-16 units) |
| `char *cstr` NUL-terminated | Bytes before terminator | Terminator must exist within valid region and scan limit |
| `uint16_t *utf16` + `unit_count` | Number of 16-bit code units | Non-BMP code points require two units |
| `void *blob` + `size_t blob_bytes` | Payload size | Must not be inferred from bytes that look like a string |

If the C API provides pointer + **byte length**, create a `MemorySegment` of exact `byteLength`, then copy/decode using a charset/decoder with an explicit malformed-input policy. If the C API returns a NUL-terminated C string with **no verified maximum limit**, scanning for NUL remains an unbounded native access. The best approach is to change the API to provide `length` or `copy_into`. Only when a native string is known to be at most 256 bytes and C guarantees a terminator within that range can you open a view capped at 256 and search for NUL **within those 256 bytes** (after confirming the allocation actually holds 256 bytes or the contract guarantees a valid cap).

Do not use JNI `GetStringUTFLength` to measure a `char*` from FFM directly. JNI Modified UTF-8 differs from standard UTF-8 at U+0000 and supplementary Unicode characters. An FFM pointer return does not declare an encoding; Java `String` length, C buffer byte count, and terminator are three independent concepts.

### 10.1. Copy-into-buffer API: reducing the need for `reinterpret`

An alternative design:

~~~c
/* Illustrative C API snippet, not a standalone runnable file. */
size_t copy_bytes(unsigned char *dst, size_t capacity);
/* Returns actual bytes written, <= capacity; function does not retain dst after return.
   Error/output behavior when dst=NULL,capacity=0 must be specified. */
~~~

Java allocates the buffer with `Arena.allocate(capacity)` and passes the `MemorySegment` into C. When the C function honors capacity, Java already knows the exact memory region it owns and can read within the written byte count without reinterpreting a returned pointer. However, you must verify C does not write past capacity; FFM cannot stop a contract-violating foreign function from overflowing from inside C.

## 11. `AddressLayout.withTargetLayout(...)`: useful when the size is fixed

JDK 22 also offers `AddressLayout.withTargetLayout(MemoryLayout)`, a **restricted** API that declares in advance what kind of data a pointer points to. For example, a field in a C struct is always a pointer to **4 `int32_t` values**:

~~~java
// Illustrative Java snippet, not a standalone program.
AddressLayout fourInts = ValueLayout.ADDRESS.withTargetLayout(
        MemoryLayout.sequenceLayout(4, ValueLayout.JAVA_INT));

MemorySegment p = structSegment.get(fourInts, pointerFieldOffset);
// When reading the address with this layout, the target has size 4*4 = 16 bytes.
int last = p.getAtIndex(ValueLayout.JAVA_INT, 3);
~~~

Requires imports `java.lang.foreign.AddressLayout`, `java.lang.foreign.MemoryLayout`, and `ValueLayout`. This snippet assumes `structSegment` is a valid segment containing the pointer field, `pointerFieldOffset` matches the ABI, and C **guarantees** at least 4 ints remain alive long enough. `withTargetLayout` sets the size from the target layout **when reading the pointer**, yet cannot validate the actual C allocation. If the length is **dynamic**, `reinterpret(bytes, arena, null)` after reading and verifying an explicit length is usually easier to control.

Do not use an arbitrarily huge target layout to “enable reading” memory at will; a restricted API can still crash the JVM when the contract is wrong. Target layouts also do not solve ownership or freeing.

### 11.1. Distinguishing function pointers and data pointers

`SymbolLookup.find("function")` also returns a zero-length segment representing the **symbol address**. In that case use `Linker.downcallHandle(symbol, FunctionDescriptor...)` to call the C function; **do not** `reinterpret` and call `get(JAVA_INT,0)` on a code address. For a C function pointer returned by an API, build a descriptor/handle with the right calling convention and keep the library loaded. For a **data pointer**, the solution is length/layout/ownership. Even though both are described by `ADDRESS`, their purpose and safety rules are completely different.

## 12. Pre-read checklist: a concise protocol

~~~text
1) C API specification:
   pointer type, length unit, allowed null, mutability, owner, lifetime
                      |
                      v
2) FFM downcall with matching FunctionDescriptor and target ABI
                      |
                      v
3) Obtain raw MemorySegment (typically byteSize=0) along with length
                      |
                      v
4) Check error return / NULL / negative or oversized count
                      |
                      v
5) Compute byteCount using checked multiplication
                      |
                      v
6) Verify C buffer actually has enough bytes and has not been freed
                      |
                      v
7) raw.reinterpret(byteCount, arena, cleanup if appropriate)
                      |
                      v
8) Read/write using matching ValueLayout, alignment, byte order, index
                      |
                      v
9) Stop all users/callbacks, free exactly once if owned
                      |
                      v
10) Do not use view/handle after free or arena.close()
~~~

The `checkedBytes` example in the complete code checks both `count < 0` and the 1,000,000 threshold. It not only prevents overflow but also defines a business limit. A count obtained from C is treated as **data that must be validated**, not blindly trusted as reasonable simply because native code returned it. If native code has a bug or a library changes versions, Java guards help limit the blast radius on many failure paths, though they still do not replace native memory safety.

An important rule for native out-parameters: use `ValueLayout.JAVA_INT` for C `int32_t*`, rather than passing `ADDRESS` and reading the output buffer's address as an integer. `outCount = arena.allocate(ValueLayout.JAVA_INT)` creates a 4-byte Java-owned region for C to write into. The **returned** pointer is a separate `MemorySegment` value; the length lives at `outCount.get(JAVA_INT,0)`. Do not add addresses or confuse these two pointers.

## 13. Common mistakes and symptoms

| Anti-pattern | Consequence | Fix |
| --- | --- | --- |
| `raw.byteSize()==0` => assuming C returned an empty array | Data loss, API misunderstanding | Size 0 means unknown extent; read count separately |
| `raw.get(JAVA_INT,0)` on size-0 raw | `IndexOutOfBoundsException` | Read only after obtaining length and bounded view |
| `raw.reinterpret(Long.MAX_VALUE)` to bypass bounds check | Accessing memory outside allocation, crash/corruption | Only reinterpret bytes verified by the C contract |
| Reading 10 elements because “the API usually returns 10” | Version/ABI change causes out-of-bounds | Return count from API or documented fixed count |
| Treating byte count as element count | Over-reading by `sizeof(T)` | State units explicitly; multiply only element counts |
| Computing `count * size` as `int` before casting to `long` | Integer overflow before check | Use `long` + `Math.multiplyExact` |
| Reinterpreting when C pointer is `NULL` and count>0 | Null dereference/crash | Check pointer and error contract first |
| Reading element 0 as a “sentinel” when `count==0` | Accessing outside empty region | Handle empty case without dereferencing |
| Treating `Arena.close()` as automatic C `free` | Native heap leak | Call matching destroy or register proper cleanup |
| Calling destroy on a borrowed `static const` pointer | Invalid free/undefined behavior | Do not free borrowed pointers |
| Calling destroy twice | Double-free/corruption | Single owner, idempotent state, clear handle |
| Using derived view after C free | Use-after-free even while segment scope is alive | Synchronize free with users; do not expose view after close |
| Closing `libraryArena` while function pointers/borrowed views remain | Dangling pointer/code no longer loaded | Library lifetime must cover entire usage window |
| C reallocates buffer while Java keeps old view | Pointer may have moved, old length invalid | Version/lock/retain or copy-into-buffer |
| Pointer to packed ints read with aligned `JAVA_INT` | Alignment exception/ABI mismatch | Use actual layout per contract, do not “fix” blindly |
| Reading C `size_t` on Windows x64 via `JAVA_INT` | Truncated count, wrong byteCount | Use ABI canonical layout for `size_t` |
| Using Java `String.length()` to compute bytes for UTF-8 `char*` | Truncation/misread Unicode | Use byte length for the actual encoding |
| Forgetting `--enable-native-access` with restricted APIs | `IllegalCallerException`/runtime policy error | Grant access to the proper named or unnamed module |
| Relying on `MemorySegment.NULL.byteSize()==0` to detect null | Every raw pointer also has size 0 | Check `address()==0L` per context |
| Calling `free` from wrong library/CRT allocator | Heap corruption, especially on Windows | Use `destroy_numbers` from the same C API |
| Assuming `structLayout` inserts padding automatically | Wrong offset/stride, native failure | Declare padding explicitly, measure `sizeof/offsetof` with compiler |

### 13.1. Four error categories to keep separate

- **Spatial bounds:** `IndexOutOfBoundsException` when reading outside the segment range **known to Java**. If you over-declared the size relative to the C allocation, this check cannot save you.
- **Scope lifetime:** `IllegalStateException` when accessing a segment whose arena has closed. A separate native `free` can happen **before** this point and does not update the scope automatically.
- **Alignment/thread:** `IllegalArgumentException` or `WrongThreadException` for accesses incompatible with layout alignment or confined arena ownership.
- **Native-access/ABI:** `IllegalCallerException` if restricted-operation access is missing; a C ABI mismatch can cause corruption/JVM crash without necessarily throwing a Java exception.

Do not try catching `IndexOutOfBoundsException` around an over-wide reinterpreted pointer as a safety mechanism: invalid native memory reads are not guaranteed to produce a catchable Java exception.

## 14. Pointer contract test matrix

| Scenario | Expected result | Must verify |
| --- | --- | --- |
| C returns 3 ints via `borrow_numbers` | Raw size 0, count 3, sum 31 | Out-parameter and pointer share the same snapshot |
| C returns `NULL`, count 0 allowed | Return empty Java result | Do not read raw pointer |
| C returns `NULL` but count 5 | Report contract error | Do not reinterpret/dereference |
| C returns non-null pointer but negative count | Report count error | Do not convert negative to huge `size_t` |
| Count exceeds business limit | Report error before reading/allocating | Do not open an oversized view |
| Valid count, byte count overflows with large layout | `Math.multiplyExact` throws | Do not use overflowed result |
| Borrowed pointer to `static const` | Read-only and not freed | Library not yet unloaded |
| Java-owned malloc pointer | Freed exactly once, even on Java exception | `finally`/`AutoCloseable` |
| Native realloc while Java reads | Must have lock/snapshot or copy API | Do not use stale view |
| Arena closed | Derived scoped view unusable | Does not escape/get stored improperly |
| Buffer contains embedded NUL | Byte count preserves data | Do not replace length with `strlen` |
| FFM function returns opaque context | Only pass pointer back to C | Do not read private layout |
| Running Java without native-access flag | Policy error/warning depending on JDK | Configure module access properly |
| C compiler changes struct padding | Java wrapper must re-check layout | Measure `sizeof`, `offsetof` on target ABI |

The best testing combines **unit tests** for the Java contract, **integration tests** on target OS/architectures with the real native library, **sanitizers** in C when the toolchain supports them, and dedicated tests for null/zero/negative/oversized lengths. FFM tests that only exercise Java with valid segment bounds are insufficient; you must test on the C side that it does not read or write past allocations.

### 14.1. Demo variation exercises

1. Change `borrow_numbers` to return a 5-element array and write count 5. Update expected output and verify Java has no hard-coded 3 in the loop.
2. Change `create_numbers(4)` to `create_numbers(1)`; expect sum 10. Try `create_numbers(0)`: C returns NULL, Java reports an error instead of reading an empty array, because the sample contract disallows count 0.
3. On a C error path, deliberately return `NULL` while writing count 3 from the borrowed API; Java must reject it before `reinterpret`.
4. Add `copy_numbers(int32_t *dst,int32_t capacity)` so Java allocates the buffer itself. Compare using an arena-owned segment with a returned pointer of unknown size.
5. Describe a C API returning `const char *data,size_t bytes` with embedded NUL. Explain why neither `String.length()` nor `strlen` can replace `byteLength`.
6. Simulate a native callback running after Java has freed the pointer. Design a stop/in-flight/close protocol so the freed block is never read.
7. Add a struct containing `void *pointer; size_t byteCount`. Measure `sizeof`/`offsetof` on Linux x64 and Windows x64 before declaring the FFM `MemoryLayout`.
8. Create an opaque `Context *`; explain why `reinterpret` is unnecessary and why retaining the handle after destroy is dangerous.

Exercises involving null pointers and deliberately invalid sizes should **test guards before access**, not intentionally dereference bad native memory to “see what error the JVM throws”. Native pointer errors can crash the JVM and cause data loss, not a safe exception test.

## 15. Production code checklist

- [ ] Read the **C API contract**: pointer type, element size, byte order/ABI, return code, output length, allowed null.
- [ ] Length comes from a **trusted source** (out-param/struct/fixed-size/copy API), not guessed from raw pointer.
- [ ] Distinguished **zero-length pointer segment** from **0-element buffer** and **NULL pointer**.
- [ ] Count has the right **unit (bytes vs. elements)**; has a max limit and negative check?
- [ ] Byte count computed with overflow-checked multiplication, not cast after overflowing?
- [ ] `reinterpret` only creates a bounded view **of the verified size**, never expanding past the allocation.
- [ ] Target ABI matches `ValueLayout`/struct padding/alignment and native export symbols.
- [ ] Is the pointer **borrowed, owned, opaque, or transferred**? Valid for the entire Java usage window?
- [ ] For borrowed data, library/owner lives long enough; `const` data is neither mutated nor freed.
- [ ] For owned data, there is **exactly one** free/destroy path (including on exceptions), with no double-free.
- [ ] Native memory is not freed/reallocated while a Java view is reading; threads/callbacks are synchronized.
- [ ] `Arena` scope, thread ownership, and library lookup lifetime are correct; no view is used after close.
- [ ] Native access granted to the module using `libraryLookup/downcallHandle/reinterpret`; not mixing up Java 17/21 APIs.
- [ ] For C strings, encoding, terminator, and **safe scan bound** are defined; never trust `strlen` for binary data.
- [ ] Tested on target OS/CPU, toolchain, and real C ABI, including null, length 0, oversized, and failure paths.

**Conclusion:** A size-0 `MemorySegment` from a C pointer means “**FFM knows the address but not the data extent**”, not a statement that native code returned an empty buffer. Only when the C API provides **explicit size and ownership** does Java have grounds to `reinterpret` it into a bounded view for reading. Designing the `pointer + length + lifetime + destroy` tuple properly matters more than picking an FFM call that merely looks convenient.

### Official References

- Oracle, [JDK 22 `MemorySegment` — Zero-length memory segments](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): pointer returns, `byteSize()==0`, `reinterpret`, global scope, and safety restrictions.
- Oracle, [JDK 22 `Linker`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `downcallHandle`, `FunctionDescriptor`, and pointer return carrier.
- Oracle, [JDK 22 `AddressLayout`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/AddressLayout.html): `ADDRESS`, target layout, restricted resizing.
- Oracle, [JDK 22 `SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): symbol address segments and library lookup lifetime.
- Oracle, [JDK 22 `Arena`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): allocation, scope, close, and cleanup actions.
- Oracle, [JDK 22 Core Libraries — Foreign Functions That Return Pointers](https://docs.oracle.com/en/java/javase/22/core/foreign-functions-that-return-pointers.html): returned `malloc` pointer, reinterpret size, and free.
- OpenJDK, [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): standard FFM from JDK 22.
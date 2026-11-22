# Pairing Allocation and Deallocation Functions from the Same Library or Memory Manager

> **Context:** Java Advance → Native Interoperability → Pointers and Ownership. This lesson establishes resource management rules when Java interacts with C/C++/native libraries via JNI or the Foreign Function & Memory API (FFM): **a resource allocated by a given allocator/API must be returned using the exact corresponding release function of that same allocator/API**. The fact that two functions both accept `void*` does not prove they are interchangeable. JNI examples run with Java 17+ and C11 on Linux; FFM sections use the stable API from Java 22.

## 1. Why Does an Address Not Tell You Who Has the Right to Free It?

A C pointer such as `void *p` or a JNI handle `jlong` typically only represents **a location or resource identifier**. It does not carry reliable information about:

- Who allocated it, and which **allocator domain** owns the memory region.
- Whether the memory region is a single object, an array, a mapped file, a buffer from the VM, or an internal SDK resource.
- Whether it should be freed with `free`, `delete`, `delete[]`, an `sdk_release` function, or not freed manually.
- Whether the address is the start of the allocation or only an **interior pointer/view/slice**.
- How many owners the resource still has, or whether callbacks or other threads are still using it.

Dangerous example:

```c
// WRONG: this code is not a runnable example; it can cause undefined behavior.
void *p = foreign_library_create_buffer();
free(p);  // Unknown which allocator foreign_library uses!
```

`foreign_library_create_buffer` might return a pointer to a C++ object created with `new`, a structure inside an arena/pool, or memory with a custom header. Calling `free(p)` from the caller program can corrupt the heap structure, skip destructors, or cause a double-free or crash. Even if you see `malloc` in the library's source code, freeing from a different runtime/heap (especially across DLL/CRT boundaries) can still be wrong.

**Strong enough rule:** The *correct release function* is determined by **the contract of the API that allocated the resource**, not by the pointer type, file name, or what the caller guesses. "Same library" is a good design principle; **same allocator/memory manager and matching API pair** is the actual requirement.

## 2. Ownership Diagram: owned, borrowed, transferred, and shared

Before writing a JNI wrapper, you must clearly identify which category the returned pointer belongs to:

| Contract | Who has the right to dispose? | What is the caller allowed to do? |
|---|---|---|
| **Owned** / new allocation | Caller receives ownership and must call the specified destroy function | Use, then release **exactly once** |
| **Borrowed** / view | Original owner or SDK | Read/write only within the valid lifetime; **do not free it yourself** |
| **Transferred** / take ownership | New recipient per the API contract | Transferor no longer frees; recipient will release per contract |
| **Shared / reference-counted** | Multiple owners via retain/release | Each retain has a corresponding release; do not `free` the object directly |
| **Scoped / arena-managed** | Arena, context, or scope | Close the scope/context; do not free individual child pointers against the contract |
| **Static / constant storage** | Compiler, module, or process | Do not free; use only while the module/lifetime remains valid |

Correct ownership diagram:

```text
C LIBRARY  (allocator + implementation state)
    |
    | sdk_buffer_create(n)  ->  opaque SdkBuffer *p
    v
JAVA/JNI FACADE  (owns HANDLE, not allocator internals)
    |
    | nativeGet/nativeSet(p)     [only while OPEN]
    |
    | close() -> sdk_buffer_destroy(p)
    v
C LIBRARY  (uses matching free/destructors/heap)
    |
    +-- pointer invalid after release
```

Key distinctions:

- **Pointer value** can be copied arbitrarily. **Ownership** is not automatically duplicated when copying a pointer.
- **Aliasing** (`p` and `q` having the same address) does not permit both to call `free`.
- A **borrowed pointer** may be valid for a single callback or until the next API call, not necessarily until the user explicitly calls `close`.
- A **handle** can be a pointer, an integer token, a file descriptor, or an opaque ID; do not infer the release function solely from its representation.
- **Java GC** only automatically manages Java objects. It **does not** understand that a `long` storing a pointer needs `sdk_buffer_destroy`.

## 3. Pairing Table for Allocation and Deallocation

| Object / Resource Source | Creation or Acquire Function | Matching Release Function | Must Not Be Confused With |
|---|---|---|---|
| Standard C heap in the **same allocator domain** | `malloc`, `calloc`, successful `realloc` | `free` | `delete`, `delete[]`, JNI `Release...` |
| Single C++ object | `new T(...)` | `delete p` (calls destructor) | `free(p)`, `delete[] p` |
| C++ array | `new T[n]` | `delete[] p` | `free(p)`, `delete p` |
| C++ RAII | `std::make_unique<T>()`, container | Destructor of owner/smart pointer | `free(owner.get())` or `delete owner.get()` |
| Windows aligned allocator | `_aligned_malloc` | `_aligned_free` | `free` |
| Windows COM task allocator | `CoTaskMemAlloc` | `CoTaskMemFree` | CRT `free` |
| Windows virtual memory | `VirtualAlloc` | `VirtualFree` with valid flags | `free` |
| POSIX file mapping | `mmap` | `munmap` with exact address/length | `free` |
| Third-party SDK with opaque handle | `sdk_create`, `sdk_alloc` | `sdk_destroy`, `sdk_free` published by SDK | Application-side `free` if not permitted |
| JNI string chars | `GetStringChars` / `GetStringUTFChars` | Corresponding `ReleaseStringChars` / `ReleaseStringUTFChars` | C `free` |
| JNI primitive array elements | `GetIntArrayElements` (and other types) | `ReleaseIntArrayElements` with matching array/pointer/mode | C `free`, `DeleteLocalRef` |
| JNI critical array/string | `GetPrimitiveArrayCritical` / `GetStringCritical` | `ReleasePrimitiveArrayCritical` / `ReleaseStringCritical` | C `free` |
| JNI strong global reference | `NewGlobalRef` | `DeleteGlobalRef` | `free`, `DeleteLocalRef` |
| JNI local reference | Local ref provided by JNI | `DeleteLocalRef` or end of local frame | `DeleteGlobalRef`, C `free` |
| FFM native memory allocated by Arena | `arena.allocate(...)` | `arena.close()` if Arena is closeable | Calling C `free` directly on that segment |
| FFM view of external allocation | `MemorySegment.ofAddress`, `reinterpret` | **Matching SDK deallocator** per owner; can register corresponding cleanup | Assuming `reinterpret` frees automatically |
| Java `byte[]` / `int[]` | `new byte[n]`, `new int[n]` | JVM GC when no longer reachable | C `free` on Java data |

This table is a **guiding principle**; always check the specific documentation. For example, C++ may have custom `operator new/delete` or placement new, SDKs may have reference counting, and `mmap`/`VirtualAlloc` use specific flags and lengths. These cases cannot be reduced to "just call free".

**With C++**, the `void*` type hides constructor/destructor information. C++ code should ensure the `new/delete` or `new[]/delete[]` pairing itself; Java should only see an **opaque handle** and call a `destroy` API exported by the C++ wrapper.

## 4. Common Design Mistake: Letting Java Choose the Free Function

Suppose a library has the interface:

```c
// Poor interface: returns void* without ownership docs.
void *make_resource(int n);
```

The Java JNI bridge receives the address and thinks it can do:

```c
// ANTI-PATTERN: DO NOT run.
void *p = make_resource(100);
free(p);  // May have wrong allocator domain, object type, or destructor.
```

Replace it with a symmetric API:

```c
// sample_sdk.h: the library clearly specifies ownership.
typedef struct SdkBuffer SdkBuffer;

SdkBuffer *sdk_buffer_create(size_t count);
void sdk_buffer_destroy(SdkBuffer *buffer);
```

Document it: `sdk_buffer_create` returns an **owned handle**; the caller must pair it with `sdk_buffer_destroy`; each handle is destroyed **exactly once** after all operations/callbacks have finished; a `NULL` handle indicates creation failure; do not free with any other function. The internal structure of `SdkBuffer` is not exposed in the ABI, so the library can change its allocator without changing Java/JNI caller code.

Another advantage: the destroy API can close file descriptors, release GPU resources, invoke destructors, or return buffers to a memory pool—things a plain `free` cannot do.

## 5. Standard C: `malloc/calloc/realloc/free` and Specific Pitfalls

Within the **same C allocator system**, memory returned by `malloc`/`calloc` is returned using `free`. `realloc` may move the allocation to a new address; on success, the old pointer becomes invalid.

**Standalone C11 example `c_memory_demo.c`:**

```c
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

int main(void) {
    size_t count = 3;
    if (count > SIZE_MAX / sizeof(int32_t)) {
        return 1;
    }

    int32_t *items = calloc(count, sizeof(*items));
    if (items == NULL) {
        return 1;
    }

    items[0] = 7;
    items[1] = 11;
    items[2] = 13;

    printf("sum=%d\n", (int)(items[0] + items[1] + items[2]));

    size_t grownCount = 5;
    if (grownCount > SIZE_MAX / sizeof(*items)) {
        free(items);
        return 1;
    }

    // DO NOT assign directly 'items = realloc(items, ...)'.
    int32_t *grown =
            realloc(items, grownCount * sizeof(*items));
    if (grown == NULL) {
        // realloc failed: old items is still valid, must free it.
        free(items);
        return 1;
    }

    items = grown;
    items[3] = 17;  // realloc does not zero the extended part.
    items[4] = 19;

    printf("sum5=%d\n", (int)(items[0] + items[1]
            + items[2] + items[3] + items[4]));

    free(items);
    items = NULL;   // Only invalidates this local alias.
    return 0;
}
```

Compile/run on Linux or macOS with GCC/Clang:

```bash
gcc -std=c11 -Wall -Wextra -pedantic c_memory_demo.c -o c_memory_demo
./c_memory_demo
```

**Success stdout:**

```text
sum=31
sum5=67
```

A failed `realloc` **does not** automatically free the old region, so store the result in a temporary variable. A successful `realloc` requires using the new pointer from then on, even if the printed address did not change. Free the exact **original address of the allocation**; `free(items + 1)` is wrong. `free(NULL)` is safe in standard C, but **calling `free` twice on the same non-NULL pointer** is undefined behavior. Setting the local variable to `NULL` after freeing prevents a bug on that specific variable, but **does not clear other aliases**.

Do not confuse `calloc` zero-initialization with a C++ object constructor or with guaranteeing a Java object exists. For C++/SDK resources, follow the **lifecycle API** instead of applying a raw C model.

## 6. C++: Destructors and the Difference Between `new` and `new[]`

C++ allocations do not just have a "byte count"; they also have **object lifetime**:

```cpp
#include <memory>
#include <vector>

struct Widget {
    int id;
    explicit Widget(int x) : id(x) {}
    ~Widget() { /* release object-specific resources */ }
};

void example() {
    Widget *one = new Widget(42);
    delete one;               // Exact single object and destructor.

    Widget *many = new Widget[2]{Widget(1), Widget(2)};
    delete[] many;            // Exact array form.

    auto owned = std::make_unique<Widget>(7);
    // Do not delete/free owned.get(): unique_ptr is the owner.
} // owned automatically calls destructor via unique_ptr.
```

This is an **illustrative C++ function** inside a program/library; there is no `main`. The following cases are wrong:

```cpp
// ANTI-PATTERNS: DO NOT run.
Widget *one = new Widget(1);
free(one);            // Destructor does not run, allocator mismatch.

Widget *array = new Widget[2]{Widget(1), Widget(2)};
delete array;         // Wrong form; must be delete[] array.
```

If a C++ library exports a native handle to Java, you should create a *C ABI facade*:

```cpp
extern "C" {
    Widget *widget_create(int id) {
        return new Widget(id);
    }

    void widget_destroy(Widget *p) {
        delete p;  // Only this function knows the right object/allocator.
    }
}
```

In production, the C ABI boundary should not let C++ exceptions cross into JNI. Catch exceptions and convert them to error codes/null, keeping `widget_destroy` noexcept whenever possible. If a class has a custom destructor or deallocator, the library owns them and must perform cleanup as well.

### Why Are Windows DLL/CRT Boundaries Especially Prone to Mismatch?

According to Microsoft, DLLs or applications linked against different CRT versions can use **different heap managers**, causing heap corruption if allocated in one place and freed with a different allocator. Even with the same CRT, a pointer allocated from a **different heap** does not automatically become valid for cross-heap freeing.

You should not make an absolute rule that "any `free` from another DLL is wrong": if two components are designed/documented to use the same CRT allocator and the same heap, some cases are valid. However, the most resilient library interface is still to **export its own release function** so callers are not forced to depend on how the CRT is linked.

## 7. Complete JNI Example: Java Owns the Handle, SDK Owns the Allocator

We will build a small C SDK with an **opaque `SdkBuffer*`**. The SDK `calloc`s its data and frees it via `sdk_buffer_destroy`; the JNI wrapper **never calls `free`** on SDK resources. Java only holds a `long` token and provides `AutoCloseable` so every exit path calls destroy properly.

The exercise has four files:

- `sample_sdk.h` — defines the SDK API and ownership contract.
- `sample_sdk.c` — implements allocator + deallocator in the **same library**.
- `OwnershipDemo.java` — Java facade and main program.
- `OwnershipDemo.c` — JNI bridge calling the matching `sdk_buffer_*` functions.

Environment: **Linux, GCC, JDK 17+**, `JAVA_HOME` pointing to the JDK, all files in the same directory. We build the SDK as a separate shared library `libsample_sdk.so` and the JNI bridge as `libownerdemo.so` to demonstrate **a real two-library boundary**, rather than putting both functions in a single C file.

### 7.1. File `sample_sdk.h` — C ABI Contract

```c
#ifndef SAMPLE_SDK_H
#define SAMPLE_SDK_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// OPAQUE: Client does not know the structure and must not free it directly.
typedef struct SdkBuffer SdkBuffer;

// Returns owned buffer or NULL on allocation failure.
// count must be > 0. Pair EXACTLY with sdk_buffer_destroy.
SdkBuffer *sdk_buffer_create(size_t count);

// Return 0 on success, -1 on invalid buffer/index.
int sdk_buffer_put(SdkBuffer *b, size_t index, int32_t value);
int sdk_buffer_get(const SdkBuffer *b, size_t index, int32_t *out);

// Must be called exactly once for each non-NULL owned buffer,
// after all operations finish. Accepts NULL as a no-op.
void sdk_buffer_destroy(SdkBuffer *b);

#ifdef __cplusplus
}
#endif
#endif
```

**Importance of the API:** the caller **has no** valid way to know how many internal allocations `SdkBuffer` has. If the SDK later uses a memory pool, ref-counting, or a custom allocator, the JNI client still does not have to change `free`/`delete`: it only calls `sdk_buffer_destroy`.

### 7.2. File `sample_sdk.c` — The SDK Creates and Destroys Memory Itself

```c
#include "sample_sdk.h"
#include <stdlib.h>
#include <stdint.h>

struct SdkBuffer {
    size_t count;
    int32_t *items;
};

SdkBuffer *sdk_buffer_create(size_t count) {
    if (count == 0 || count > SIZE_MAX / sizeof(int32_t)) {
        return NULL;
    }

    SdkBuffer *b = malloc(sizeof(*b));
    if (b == NULL) return NULL;

    b->items = calloc(count, sizeof(*b->items));
    if (b->items == NULL) {
        free(b);
        return NULL;
    }

    b->count = count;
    return b;
}

int sdk_buffer_put(SdkBuffer *b, size_t index, int32_t value) {
    if (b == NULL || index >= b->count) return -1;
    b->items[index] = value;
    return 0;
}

int sdk_buffer_get(const SdkBuffer *b, size_t index, int32_t *out) {
    if (b == NULL || out == NULL || index >= b->count) return -1;
    *out = b->items[index];
    return 0;
}

void sdk_buffer_destroy(SdkBuffer *b) {
    if (b == NULL) return;
    free(b->items);
    free(b);
}
```

**Two levels of ownership**: the SDK allocates `SdkBuffer` with `malloc` and then allocates `items` with `calloc`. SDK destroy calls `free(items)` first, then `free(b)`. JNI cannot just call `free(b)` because that would leak `items`; nor can it know the right heap if the SDK changes its allocator.

**Thread safety:** this is a simple example SDK, **not thread-safe for concurrent get/put/destroy**. The Java facade below serializes all uses of the handle on a single instance. If a real C API has callbacks, native workers, or an SDK global handle registry, you need to add quiescence before destroy.

### 7.3. File `OwnershipDemo.java` — Java Owner with `AutoCloseable`

```java
public final class OwnershipDemo {
    static {
        System.loadLibrary("ownerdemo");
    }

    private static native long nativeCreate(int count);
    private static native void nativePut(long handle, int index, int value);
    private static native int nativeGet(long handle, int index);
    private static native void nativeDestroy(long handle);

    static final class NativeBuffer implements AutoCloseable {
        private long handle;

        NativeBuffer(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException("count must be > 0");
            }
            handle = nativeCreate(count);
            if (handle == 0) {
                throw new OutOfMemoryError("nativeCreate failed");
            }
        }

        // synchronized protects check+use of the handle against close().
        synchronized void set(int index, int value) {
            ensureOpen();
            nativePut(handle, index, value);
        }

        synchronized int get(int index) {
            ensureOpen();
            return nativeGet(handle, index);
        }

        private void ensureOpen() {
            if (handle == 0) {
                throw new IllegalStateException("buffer is closed");
            }
        }

        @Override
        public synchronized void close() {
            if (handle == 0) return;  // Idempotent.
            nativeDestroy(handle);   // sdk_buffer_destroy via JNI.
            handle = 0;              // Old pointer is no longer valid.
        }
    }

    public static void main(String[] args) {
        try (NativeBuffer buffer = new NativeBuffer(3)) {
            buffer.set(0, 7);
            buffer.set(1, 11);
            buffer.set(2, 13);

            int sum = buffer.get(0)
                    + buffer.get(1) + buffer.get(2);
            System.out.println("sum=" + sum);
            System.out.println("last=" + buffer.get(2));

            buffer.close();
            buffer.close();  // Second call does not touch native memory.

            try {
                buffer.get(0);
            } catch (IllegalStateException expected) {
                System.out.println(
                        "afterClose=IllegalStateException");
            }
        }  // try-with-resources calls close again: no-op.
        System.out.println("done");
    }
}
```

`NativeBuffer` **owns** a native handle until `close()` completes. It does not export `long handle` for clients to use arbitrarily. `synchronized` protects concurrent `get/set` and `close` on the **same Java instance**: there is no situation where one Java thread is using the handle while another Java thread frees it mid-call.

**Limitation:** this design assumes no native worker/callback uses the buffer after `nativePut/get` returns. If the SDK has asynchronous processing, you must stop/register a barrier/join before destroy; Java monitors do not automatically know about those native workers.

### 7.4. Generating the JNI Header

```bash
javac -encoding UTF-8 -h . OwnershipDemo.java
```

This generates `OwnershipDemo.h` and `OwnershipDemo.class`. Do not guess JNI symbols if you change the class/package/signature; the JNI header from the compiler is the source of truth.

### 7.5. File `OwnershipDemo.c` — JNI Only Calls the SDK API

```c
#include <jni.h>
#include <stdint.h>
#include "OwnershipDemo.h"
#include "sample_sdk.h"

static void throwJava(JNIEnv *env, const char *type,
                      const char *message) {
    if ((*env)->ExceptionCheck(env)) return;
    jclass cls = (*env)->FindClass(env, type);
    if (cls == NULL) return;  // FindClass may have already thrown an exception.
    (*env)->ThrowNew(env, cls, message);
    (*env)->DeleteLocalRef(env, cls);
}

static SdkBuffer *fromHandle(jlong handle) {
    return (SdkBuffer *)(intptr_t)handle;
}

JNIEXPORT jlong JNICALL Java_OwnershipDemo_nativeCreate(
        JNIEnv *env, jclass owner, jint count) {
    (void)owner;
    if (count <= 0) {
        throwJava(env, "java/lang/IllegalArgumentException",
                  "count must be > 0");
        return 0;
    }

    SdkBuffer *b = sdk_buffer_create((size_t)count);
    if (b == NULL) {
        throwJava(env, "java/lang/OutOfMemoryError",
                  "sdk_buffer_create failed");
        return 0;
    }

    // Demo for platforms where intptr_t can hold a pointer,
    // and jlong is wide enough to store that value.
    return (jlong)(intptr_t)b;
}

JNIEXPORT void JNICALL Java_OwnershipDemo_nativePut(
        JNIEnv *env, jclass owner,
        jlong handle, jint index, jint value) {
    (void)owner;
    if (handle == 0) {
        throwJava(env, "java/lang/IllegalStateException",
                  "handle is closed");
        return;
    }
    if (index < 0 || sdk_buffer_put(fromHandle(handle),
                                   (size_t)index,
                                   (int32_t)value) != 0) {
        throwJava(env, "java/lang/IndexOutOfBoundsException",
                  "invalid index");
    }
}

JNIEXPORT jint JNICALL Java_OwnershipDemo_nativeGet(
        JNIEnv *env, jclass owner, jlong handle, jint index) {
    (void)owner;
    if (handle == 0) {
        throwJava(env, "java/lang/IllegalStateException",
                  "handle is closed");
        return 0;
    }
    int32_t value = 0;
    if (index < 0 || sdk_buffer_get(fromHandle(handle),
                                   (size_t)index, &value) != 0) {
        throwJava(env, "java/lang/IndexOutOfBoundsException",
                  "invalid index");
        return 0;
    }
    return (jint)value;
}

JNIEXPORT void JNICALL Java_OwnershipDemo_nativeDestroy(
        JNIEnv *env, jclass owner, jlong handle) {
    (void)env;
    (void)owner;
    if (handle == 0) return;
    sdk_buffer_destroy(fromHandle(handle)); // CORRECT library/API.
}
```

**Decision point:** the JNI bridge does not include `stdlib.h` to call `free` on the SDK pointer itself. It calls `sdk_buffer_destroy` published by the same SDK that allocated it. Nor does the Java side call a "generic free" API just because `handle` is a `long` number.

In the demo, `intptr_t` is sufficient to pass a pointer via `jlong` on supported ABIs (common 64-bit JVMs). On platforms where a pointer cannot be safely represented by `jlong`, you must design an opaque handle registry instead of a pointer cast. The cast-back numeric value is only valid while the pointer is alive and belongs to the right SDK instance.

### 7.6. Compiling into Two Real Shared Libraries

On Linux, from the directory containing the four files, after running `javac -h .`:

```bash
gcc -std=c11 -fPIC -shared \
  -o libsample_sdk.so sample_sdk.c

gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -L. -Wl,-rpath,'$ORIGIN' \
  -o libownerdemo.so OwnershipDemo.c -lsample_sdk

java -Djava.library.path=. OwnershipDemo
```

`-L. -lsample_sdk` links the JNI bridge to the **SDK shared library**. `-Wl,-rpath,'$ORIGIN'` sets the ELF runtime search path next to `libownerdemo.so` so the dynamic loader finds `libsample_sdk.so` at runtime. The `'$ORIGIN'` syntax is quoted so the shell does not expand it as an environment variable. For a real packaging/deployment system, you must separately verify RPATH/RUNPATH, loader security policies, and library distribution paths.

With **JDK 24+** when the JVM requires or warns about JNI native access permissions for the classpath, run:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. OwnershipDemo
```

On macOS/Windows, adjust `.dylib`/`.dll` names, platform-specific JNI includes, and linked libraries according to the compiler/toolchain. **Especially on Windows:** ensure the SDK DLL exports functions and the Java JNI DLL imports them with the matching ABI. Do not assume Linux commands are cross-platform builds.

**Expected stdout when all steps succeed:**

```text
sum=31
last=13
afterClose=IllegalStateException
done
```

This is a deterministic Java computation and sequence, independent of scheduling order because a single main thread performs `set/get/close`. If `libsample_sdk.so` is missing, the library search path is wrong, or JNI symbol names do not match, the program will fail to load/link; that is a **deployment issue**, not a sign that you are allowed to replace `sdk_buffer_destroy` with `free`.

## 8. Failure Paths: Who Cleans Up What When Allocate/Create Fails?

A well-owned API must have an answer for **every failure state**:

```text
JNI nativeCreate(count)
    |
    +-- count <= 0      -> throw Java IllegalArgumentException
    |
    +-- malloc(SdkBuffer) fails
    |                        -> NULL; no allocation to free
    |
    +-- calloc(items) fails
    |                        -> sdk frees its partial SdkBuffer
    |                        -> NULL
    |
    +-- all success    -> return owned SdkBuffer * wrapped as handle
                             |
                             v
                       Java NativeBuffer
                             |
                      close() exactly once
                             |
                             v
                      sdk_buffer_destroy
```

**Distinctions to make**:

- Allocation did not succeed → no resource to free on the Java side.
- Allocation succeeded but a subsequent step failed → clean up with the **matching allocator** for each sub-resource. For example, `sample_sdk.c` called `free(b)` in the `calloc` failure branch.
- Ownership has been transferred to the Java facade → the C entrypoint **does not** free it before returning the handle; Java's `close` is responsible for calling destroy.
- `close` may be called multiple times in Java → the facade makes it idempotent. **Do not** call `sdk_buffer_destroy` twice on a non-null pointer.
- If create returns a pointer to borrowed/static memory instead of owned memory → **do not** register auto-close as an owned pointer; the contract must be published differently.

If an SDK API has two functions `sdk_query(..., out)` and `sdk_free_result(...)`, the caller must free the result using the SDK API. If a function only gives a **borrowed view** valid until the next call, do not keep the view long-term or free it yourself. Cases requiring a copy must use a destination buffer owned and managed separately by Java/JNI.

### Do Not Confuse a Zero Handle with an "Invalid Pointer Checker"

`if (handle == 0)` only catches the sentinel that the Java facade set. A non-zero `long` can still be an already-freed pointer if a client bypasses the wrapper. **A native function has no portable way to verify whether any arbitrary pointer is still valid just by looking at its address.** Therefore:

- Hide the handle behind a private field and synchronized methods.
- When multiple callers are needed, use a handle table + generation IDs/refcount/acquire-release barrier; do not expose raw pointers.
- If the SDK has background threads/callbacks, shutdown must stop/drain/join before destroy.
- Do not call `nativeGet`/`nativePut` after `nativeDestroy` has released it.
- Do not use `System.gc()` or `Cleaner` as a signal that SDK resources have definitely been freed.

## 9. JNI Pointers Are Not C Memory You Own

Many JNI APIs return `const char*` or `jint*`, leading developers to think they are `malloc` buffers. In reality, the pointer may be a copy allocated by the JVM, a pinned memory region, or an implementation-specific view.

**Correct example for `GetStringUTFChars`:**

```c
// Snippet inside a JNI native method.
// env and input are valid parameters of the right Java thread.
const char *chars = (*env)->GetStringUTFChars(env, input, NULL);
if (chars == NULL) {
    // OutOfMemoryError or related exception may be pending.
    return;
}

// Process JNI Modified UTF-8 bytes here.
// Do not keep pointer after release, do not call free(chars).

(*env)->ReleaseStringUTFChars(env, input, chars);
```

**Some typical JNI pairs:**

| Acquire | Release | Notes |
|---|---|---|
| `GetStringUTFChars(env,s,...)` | `ReleaseStringUTFChars(env,s,p)` | **Modified** UTF-8, not standard UTF-8 |
| `GetStringChars(env,s,...)` | `ReleaseStringChars(env,s,p)` | UTF-16 code units |
| `GetIntArrayElements(env,a,...)` | `ReleaseIntArrayElements(env,a,p,mode)` | `mode` controls copy-back/release |
| `GetByteArrayElements(env,a,...)` | `ReleaseByteArrayElements(env,a,p,mode)` | Do not `free` the pointer yourself |
| `GetPrimitiveArrayCritical` | `ReleasePrimitiveArrayCritical` | Critical region: restricts JNI calls/blocking |
| `GetStringCritical` | `ReleaseStringCritical` | Similar restrictions to critical arrays |
| `NewGlobalRef` | `DeleteGlobalRef` | JNI root, not a C heap block |
| `NewWeakGlobalRef` | `DeleteWeakGlobalRef` | Weak JNI root, not a C heap block |

JNI primitive array example:

```c
// Illustrative snippet, array is a valid jintArray.
jboolean copied = JNI_FALSE;
jint *elements = (*env)->GetIntArrayElements(env, array, &copied);
if (elements == NULL) return;

jsize n = (*env)->GetArrayLength(env, array);
for (jsize i = 0; i < n; ++i) {
    elements[i] += 1;
}

// mode 0: write changes back to the array if needed and release/unpin.
(*env)->ReleaseIntArrayElements(env, array, elements, 0);
```

**`JNI_ABORT`:** discards changes in the copy and releases; if the VM pinned directly, data modifications may have already occurred. **`JNI_COMMIT`:** copies back when needed but **does not end holding the elements** under the normal contract; you must release properly afterward to avoid leaks/prolonged pinning. **`mode=0`:** copies back (if needed) and releases.

`isCopy == JNI_FALSE` **does not exempt** you from calling `Release...`, nor does it grant permission to use `free`. Inside a critical region, do not make arbitrary JNI operations or block for long. When native code needs to keep data beyond the lifetime of a JNI acquire, **copy it into an allocation you own**, then release the JNI pointer immediately and clean up the copied allocation with the exact allocator that created it.

## 10. Global References, Local References, and Raw C Pointers Are Three Different Things

Three ways of "holding" a Java object have independent release contracts:

- **Local JNI reference** `jobject` received from a parameter or `FindClass`: typically valid only within the thread/local frame that created it; `DeleteLocalRef` or return to Java so the frame cleans it up.
- **Strong global JNI reference** created by `NewGlobalRef`: can be used across threads attached to the same JVM while alive; **must** call `DeleteGlobalRef` after all callbacks/workers stop. Do not use `free` on a `jobject`.
- **Native object pointer** such as `SdkBuffer*`: belongs to the SDK's allocation; `sdk_buffer_destroy` is the only valid release function.

A global reference only keeps the **Java object** alive from GC; it does not automatically keep alive a native pointer that the Java object stores as a `long`. Conversely, an existing native pointer does not keep a Java listener alive if the code only held an expired local reference. When the SDK holds both native state and a Java listener, shutdown must wait for all callbacks to finish, then delete global references and destroy native state with the matching API.

**Small takeaway:** Do not have a single generic `release(void*)` function applied to every JNI handle. Design **owner-specific cleanup** for each resource type.

## 11. FFM: Memory Allocated by Arena Differs from Library `malloc` Pointers

Since JDK 22, the Foreign Function & Memory API has `Arena` and `MemorySegment`. These types improve lifetime management but **do not change the allocator pairing rule**.

### 11.1. Memory Allocated by Java Arena

**File `ArenaOwnership.java` (Java 22+):**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaOwnership {
    public static void main(String[] args) {
        MemorySegment saved;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
            saved = segment;
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            System.out.println("value=" +
                    segment.get(ValueLayout.JAVA_INT, 0));
        } // Arena itself manages releasing the memory.

        try {
            saved.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("afterClose=IllegalStateException");
        }
    }
}
```

Run:

```bash
javac ArenaOwnership.java
java ArenaOwnership
```

**stdout:**

```text
value=42
afterClose=IllegalStateException
```

Here memory is created by `arena.allocate(...)`, so **`arena.close()`** is the correct management action. Do not call C `free(segment.address())`, and do not add another cleanup callback that also frees the memory. `MemorySegment.asSlice` and `asReadOnly` are views; they do not create independent allocations and must not be freed separately.

### 11.2. Pointers Returned by `malloc` or an SDK via FFM

When a native function returns `void *` via an FFM downcall, it is typically represented as a **zero-length `MemorySegment`** carrying the address, with a lifetime not automatically tied to the SDK's allocator. Simply creating a differently sized view with `reinterpret` **does not automatically call `free`** and can be dangerous if you choose the wrong size or use it after the SDK frees it.

The JDK Linker documentation shows a clear pattern: `malloc.invokeExact(size)` returns a pointer; `segment.reinterpret(size, arena, cleanup)` attaches the view to an Arena and provides a cleanup that calls **the exact `free`**. If the actual pointer was created by the SDK's `sdk_alloc`, the cleanup must call **`sdk_free` from the SDK**, **not** grab a default `free` from another CRT.

**FFM pseudocode, not a standalone runnable file:**

```java
// Handles malloc, sdkFree, and Arena have already been set up;
// sdkFree points to the matching release function of the SAME SDK.
MemorySegment rawAddress = (MemorySegment) sdkAlloc.invokeExact(100L);

MemorySegment ownedView = rawAddress.reinterpret(
        100,
        arena,
        address -> {
            try {
                sdkFree.invokeExact(address);
            } catch (Throwable error) {
                throw new RuntimeException(error);
            }
        }
);

// When Arena closes, the registered cleanup will call SDK release.
// Do not call SDK free a second time from Java.
```

This is a **restricted FFM operation**; you must configure appropriate JDK native access permissions and understand the pointer/size contract. For the example above to actually run, you must declare the exact `MethodHandle` method types, `FunctionDescriptor`, `Linker` lookup, and `sdkAlloc/sdkFree` handles according to the ABI. Do not interpret pseudocode as an out-of-the-box API.

**Especially dangerous:** if the SDK returns a **borrowed** (not owned) pointer, never attach an `sdkFree` cleanup. If the SDK only lets the pointer live until the next call, attaching the view to a longer-lived Arena **does not extend the actual lifetime**. Java scope bounds and native allocation lifetime must be compatible; `reinterpret` is restricted because the JVM cannot verify that you told the truth.

## 12. DirectByteBuffer, Java Arrays, and Pointers with an Address but No Right to Free

Some byte buffers allow direct native access, but ownership depends on the allocation source:

**Java direct buffer**

```java
import java.nio.ByteBuffer;
ByteBuffer buffer = ByteBuffer.allocateDirect(1024);
// Java/JVM manages the buffer's allocation per the API.
// Do not pass the address to an arbitrary library's free().
```

This is a snippet. `GetDirectBufferAddress` returns the access address to a direct buffer when appropriate; it **does not** grant `free` rights to the JNI caller. A buffer may be a view of memory created elsewhere; the user must keep the owner/Java reference alive for the entire duration native code uses it.

**`NewDirectByteBuffer` on the JNI side**

```c
// Illustrative snippet: p is already a valid memory region of length n bytes
// and has a clear native owner.
jobject view = (*env)->NewDirectByteBuffer(env, p, (jlong)n);
```

Creating a DirectByteBuffer **does not automatically transfer ownership** or turn the buffer into the owner of `p`. Native code must manage `p`, callbacks/workers, any live Java views, and the release timing. If `p` is freed while Java is still reading the view, a use-after-free can occur. The JNI local/global reference to `view` also has its own contract and is not a C deallocator.

**Java arrays**

`jbyteArray`, `jintArray` are Java heap objects. If you need to copy from an SDK buffer into Java, use `NewByteArray`/`SetByteArrayRegion`; after the copy succeeds, you can free the **SDK buffer using the SDK deallocator**. Do not `free` a Java array. Conversely, pointers from `GetByteArrayElements` must be released with `ReleaseByteArrayElements`, not freed. **Copying** is a clear way to change data ownership: the SDK still owns the old allocation until destroyed, while Java owns a heap array containing the copy.

## 13. Multiple Allocators in One Process: C Runtime, Pool, GPU, OS

A single process can have multiple **allocation domains**:

```text
JVM heap        -> new byte[], object     -> Java GC
JVM JNI pin/copy-> GetStringUTFChars      -> ReleaseStringUTFChars
JVM FFM Arena   -> arena.allocate         -> arena.close
SDK private heap-> sdk_buffer_create      -> sdk_buffer_destroy
C++ heap        -> new T                   -> delete T
C++ array heap  -> new T[n]                -> delete[] T
Windows COM     -> CoTaskMemAlloc         -> CoTaskMemFree
OS mapping      -> mmap                   -> munmap
GPU driver      -> gpuCreateBuffer        -> gpuDestroyBuffer
```

**Same process does not mean same allocator.** Memory regions may sit adjacent to each other in virtual address space yet use different tracking metadata and deallocation rules. For example, `VirtualAlloc` requires `VirtualFree` with the appropriate free type/address; you cannot pass a pointer to C `free` just because it has type `void*`.

**Even the same library is not enough:** a single library can provide two different allocators: pool A and pool B, or a "temporary" arena and a "persistent" heap. You still must match the exact **owner-specific pair**. In particular, many SDKs export `create`/`release`/`retain` functions with semantics very different from `malloc/free`; API names are part of the contract, but you must read the docs rather than guessing.

**Across a DLL boundary on Windows:** instead of requiring all Java runtimes and native modules to use the same CRT heap, expose a C ABI with an `sdk_buffer_destroy` function. This model reduces risk when updating compilers, switching `/MT` vs `/MD`, using third-party SDK plugins, or changing the internal allocator.

## 14. Release Order When Callbacks or Background Workers Exist

Correct allocator pairing is a **necessary but not sufficient condition**. If a callback/native thread is still using `SdkBuffer*` when the caller invokes `sdk_buffer_destroy`, it is still a use-after-free even though destroy is the right function.

A proper closing protocol:

```text
OPEN
  | stop accepting new work
  v
CLOSING
  | unregister SDK callbacks / stop queueing
  | request worker stop, wake threads
  | wait in-flight callbacks to return
  | join native workers
  v
QUIESCENT
  | sdk_buffer_destroy(ownedHandle)
  | DeleteGlobalRef(listenerRef)
  | release other native resources in dependency order
  v
CLOSED
```

Do not hold a mutex that callbacks/workers need while calling `join`. Do not unload a library/module with `dlclose`/`FreeLibrary` while callback function pointers or workers can still execute inside that module. With an external library SDK, the **SDK destroy/stop API** might wait for threads itself, or it might require the caller to do so beforehand; you must follow the SDK documentation.

**Do not use Java `finalize`/`Cleaner` as the primary shutdown mechanism.** GC does not guarantee when callbacks stop and can also be prevented from collecting by global references. Use `AutoCloseable`, an explicit lifecycle owner, shutdown barriers, and reserve leak detection as a fallback when truly needed.

## 15. Common Error Patterns and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| `sdk_create` returns handle, Java calls C `free` | Wrong allocator, missing destructor/cleanup | Export and call `sdk_destroy` |
| C++ `new T` then `free` | Destructor not called, undefined behavior | `delete p` on C++ owner side |
| C++ `new T[n]` then `delete p` | Wrong array form, undefined behavior | `delete[] p` |
| `malloc` then `delete` | Wrong allocator family | C `free` from matching allocator |
| `_aligned_malloc` then `free` on Windows | Heap corruption/mismatch | `_aligned_free` |
| `CoTaskMemAlloc` then `free` | Wrong COM memory manager | `CoTaskMemFree` |
| `mmap` then `free` | Not unmapped properly | `munmap` per OS contract |
| `GetStringUTFChars` then `free` | Corrupts JVM-managed pointer | `ReleaseStringUTFChars` |
| `GetIntArrayElements` then `free` | Breaks JNI ownership/pin | `ReleaseIntArrayElements` |
| `NewGlobalRef` then `DeleteLocalRef` | Wrong reference kind | `DeleteGlobalRef` |
| `Arena.allocate` then C `free` before `arena.close` | Potential double-free/use-after-free | Arena is the sole owner |
| SDK-owned `void*` attached to FFM cleanup calling CRT `free` | Wrong deallocator | Call SDK-specific release |
| Borrowed pointer registered with cleanup | Releases memory you do not own | Do not clean up borrowed views |
| `NewDirectByteBuffer` then forgetting native owner | Memory leak or dangling view | Explicit handle/owner + close barrier |
| Native call with closed `long handle` | Stale pointer, crash | Guard check+use/close; do not expose handle |
| Two Java threads calling `nativeGet`/`close` without lock | Check-then-use race | Monitor or native refcount/acquire-release |
| Native callback still running during destroy | Use-after-free despite right function | Stop/drain/join before destroy |
| `realloc` fails but overwrites original pointer | Loses original pointer causing leak | Use temporary pointer |
| Two aliases both call `free` | Double free/heap corruption | Single owner, release exactly once |
| Native exception/error in create ignored | Hands broken handle to Java | Check NULL/status, convert to Java exception |

### Triaging a Real Crash

When you see `EXCEPTION_ACCESS_VIOLATION`, `SIGSEGV`, or heap corruption in JNI, ask these questions in order:

1. **Where was it allocated?** API name, library, version, CRT/toolchain, thread, time.
2. **Is it an owned pointer?** Or a borrowed/local/weak/cached/static view?
3. **What is the corresponding release?** Do the SDK docs describe `sdk_free`/`destroy`/`retain/release`?
4. **Was it released exactly once?** Could an event/callback close it again, are there aliases?
5. **Is it still in use?** In-flight JNI call, callback, worker, Java DirectByteBuffer view?
6. **Is there an ABI mismatch?** Pointer type, calling convention, char encoding, size, linker?
7. **Are there instrumented tests?** AddressSanitizer/UBSan, valgrind where appropriate, CRT debug heap, `-Xcheck:jni`, owner-state logs?

**Do not fix a crash** by removing the free call altogether except to temporarily isolate an issue during testing. The right fix is to **identify the owner and cleanup path**; omitting release indefinitely will cause native memory leaks and can exhaust off-heap memory for the JVM.

## 16. Testing the Contract in Practice: Not Just "Runs Without Crashing"

A useful test suite for an ownership boundary:

1. **Create → use → destroy:** reads/writes expected values, reports no allocator errors.
2. **Create failure:** inject `malloc/calloc` failure; no half-valid Java handle or leaked sub-allocation.
3. **Close twice:** second call does not invoke native destroy again; no double free.
4. **Use after close:** Java facade throws `IllegalStateException` before native dereference.
5. **Repeated open/close:** run in a loop to detect native leaks via RSS/heap profiler.
6. **Two Java threads using/closing concurrently:** ensure check+use is atomic relative to close.
7. **Callback/worker running:** close waits for all consumers before destroy.
8. **API returning borrowed pointer:** verify caller does not delete/free it.
9. **C++ destructor:** test that destructor/resource cleanup happens exactly once via the destroy ABI.
10. **Windows DLL with different CRT:** use the exact exported release instead of cross-freeing.
11. **FFM external view:** test that the cleanup callback calls the SDK deallocator exactly once and is not attached to borrowed memory.
12. **Library unload/reload:** no remaining handles/function pointers pointing to unloaded library code.

In native test builds, AddressSanitizer usually catches use-after-free/double-free better than observing "correct stdout". On Java, `-Xcheck:jni` helps catch some JNI errors but **does not check every deallocator mismatch across native libraries**. Combine it with instrumentation on the C/C++/SDK side.

### Operational Checklist

- [ ] Every native pointer/handle has a documented **allocator owner**.
- [ ] Classified as **owned / borrowed / transferred / shared / scope-owned**.
- [ ] Each owned resource has exactly one release path with the matching API.
- [ ] Never put `free` where only the pointer is known without knowing the allocator.
- [ ] `new/delete` and `new[]/delete[]` are properly paired by C++ code.
- [ ] JNI acquires are returned with the matching JNI Release, not `free`.
- [ ] `NewGlobalRef` is deleted with `DeleteGlobalRef` once all workers/callbacks have stopped.
- [ ] Arena-owned memory is cleaned up only by Arena; external pointers are cleaned up only by the owner-specific deallocator.
- [ ] Java facade keeps the opaque handle private, closes idempotently, and prevents use-after-close.
- [ ] If background threads/callbacks exist, stop/drain/join before destroy/unload.
- [ ] Native library and JNI bridge have tested ABI and linker contracts.
- [ ] Failure paths, race paths, and long-running leak tests are all verified.

## 17. Self-Check Exercises (with Answers)

**Exercise 1 — SDK buffer.** Function `sdk_alloc_result()` returns `void*` and docs state "caller owns result; call `sdk_free_result`". The C JNI bridge is calling `free(result)`. Right or wrong?

**Answer:** Wrong. You must call `sdk_free_result(result)`, even if the library internally uses C `malloc`: the contract can change, and the heap/CRT may differ.

**Exercise 2 — JNI string.** `const char *s = GetStringUTFChars(env, jstr, NULL)`. After using it, can you call `free((void*)s)`?

**Answer:** No. Call `ReleaseStringUTFChars(env, jstr, s)` with the exact `jstring` and `JNIEnv` per the contract. The pointer may be a copy or JVM-managed memory; do not decide the deallocator yourself.

**Exercise 3 — Java long handle.** `long h` is returned from `nativeCreate`, Java `close` has called native destroy, yet another thread is still running `nativeGet(h)`. What needs to be done?

**Answer:** Not safe enough. Use synchronized check+use/close, or a native handle table with in-flight refcounts; if the native side has internal workers/callbacks, you must also wait for quiescence before destroy.

**Exercise 4 — C++ array.** A C++ API creates `new Widget[8]` and exports the pointer via JNI. Should Java call `free` or `delete[]` directly?

**Answer:** Do not call directly from Java. The SDK/C++ wrapper exports `widget_array_destroy` which performs `delete[]` in the right runtime/allocator. The JNI bridge calls that function.

**Exercise 5 — FFM Arena.** `MemorySegment s = arena.allocate(1024)`; you want to clean up `s` immediately with a `free(s)` downcall and let `arena.close()` run later. Is that allowed?

**Answer:** No. Arena owns the allocation; freeing out-of-band can break the lifetime, and then Arena will clean up again, leading to a double-free. Redesign the scope to close at the right time.

**Exercise 6 — FFM external pointer.** An SDK returns a borrowed pointer that lives until the next call. Java uses `reinterpret(n, arena, cleanup -> sdk_free)`. What is wrong?

**Answer:** The borrowed pointer does not belong to Java; attaching a cleanup that releases it is wrong. Use a view only within its valid lifetime, or copy into a separate segment owned by Arena. A Java scope does not extend the actual native lifetime.

**Exercise 7 — realloc.** `p = realloc(p, newSize)` returns `NULL`. What is the problem?

**Answer:** The old allocation pointer is lost because `p` was overwritten, causing a leak. Use `tmp = realloc(p,...); if(tmp) p=tmp; else /* handle with old p still valid */`.

**Exercise 8 — Windows DLL.** A DLL allocates data using a private heap and returns `void*`. The app calls `free` from its own CRT. Why is this dangerous?

**Answer:** Different heap managers have different metadata/freeing logic; cross-freeing causes heap corruption. The DLL must provide a matching destroy/free API and the app must call that exact API.

**Exercise 9 — premature release.** The caller uses the right `sdk_buffer_destroy`, but an SDK callback still holds `SdkBuffer*`. Is there still a bug?

**Answer:** Yes. Using the right deallocator **does not permit** freeing a resource that is still in use. You must prevent new callbacks and wait for all in-flight callbacks/workers to finish.

**Exercise 10 — Java reference.** A JNI wrapper creates `jobject global = NewGlobalRef(env,obj)`, then calls C `free(global)`. How to fix?

**Answer:** `global` is a JNI global reference handle, not a C-heap allocation; after all threads/callbacks stop using it, call `DeleteGlobalRef(env,global)` on a thread attached to the same JVM.

## 18. Conclusion and Primary References

**Three mandatory questions before every release call:**

1. **Who created it?** What is the exact allocation source and memory manager?
2. **Who owns it?** Owned, borrowed, transferred, shared, or arena-managed; has ownership changed?
3. **Who is still using it?** Are there any unfinished Java/JNI calls, native callbacks, or workers?

A correct destroy call must satisfy **all three**. Using `sdk_buffer_destroy` for `sdk_buffer_create` instead of `free` is how you keep the contract clear across Java–JNI–native SDK. Use `ReleaseStringUTFChars` after `GetStringUTFChars`; `DeleteGlobalRef` after `NewGlobalRef`; close `Arena` for Arena-allocated memory; `delete[]` for C++ arrays. These pairs **do not share a common deallocator**.

### Official References

- [Oracle JNI Specification — String operations, primitive array release, global/local refs](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Oracle JNI Specification — Invocation API and lifecycle](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html)
- [Java SE 25 — Arena: ownership, lifetime, and close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 25 — MemorySegment: `reinterpret`, scope, and cleanup callback](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 25 — Linker: `malloc/free` and `reinterpret(...,arena,cleanup)` example](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html)
- [JEP 454 — Foreign Function & Memory API, Java 22](https://openjdk.org/jeps/454)
- [Microsoft Learn — Potential Errors Passing CRT Objects Across DLL Boundaries](https://learn.microsoft.com/en-us/cpp/c-runtime-library/potential-errors-passing-crt-objects-across-dll-boundaries)
- [C++ language — delete expression, scalar/array forms](https://en.cppreference.com/w/cpp/language/delete)

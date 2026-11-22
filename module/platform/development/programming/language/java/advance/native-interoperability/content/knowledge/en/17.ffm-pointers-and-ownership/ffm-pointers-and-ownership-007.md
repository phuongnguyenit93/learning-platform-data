# Rules for Borrowed, Transferred, or Caller-Freed Memory in Java Native Interoperability

When Java interacts with native C/C++ code via JNI or the Foreign Function & Memory API (FFM), a pointer can be valid as an address yet **have no ownership**. The exact same signature `void *`, `char *`, `MemorySegment`, or `long handle` can represent three completely different contracts:

1. **Borrowed:** the recipient may only use it temporarily and **must not free it**; the original owner guarantees that the memory region stays alive for the duration of the borrow.
2. **Transferred (ownership transfer):** the current owner hands over responsibility for destroying the resource to the other side; after a successful transfer, the previous owner **must not use or free it** as if it were still the owner.
3. **Caller-owned / caller-frees:** the API allocates and **returns a resource whose owner is the caller**; the caller must use the exact published deallocation function, typically the `create/destroy` pair of **the allocating library itself**, rather than arbitrarily choosing `free`.

This article is about **ownership and lifetime contracts**. The `const` qualifier in `const char *` may indicate read-only access through that pointer, **not** who must call `free`. Similarly, the fact that Java holds a `ByteBuffer` or `MemorySegment` does not by itself prove that it owns the native region described by the object.

**One-line principle:** for every resource, answer precisely **who allocates it**, **who currently owns it**, **who may use it**, **until when it may be used**, **who frees it**, **which API frees it**, and **where ownership lies if an error occurs**.

## 1. Ownership Is a Contract, Not a Pointer Type

C often represents all cases as pointers:

```c
const unsigned char *get_bytes(void);
unsigned char *create_bytes(size_t size);
void consume_bytes(unsigned char *bytes);
```

These are **illustrative declarations**, not a standalone C program. Looking only at the signatures, we **do not know**:

- Does `get_bytes()` return a pointer to static memory, borrow from an object, or allocate new memory?
- Can `create_bytes()` be freed with `free`, or must `destroy_bytes` be called?
- Does `consume_bytes` only read, write data, or **take ownership** as well?
- When `consume_bytes` fails, does the caller still own the buffer?
- Is the pointer still valid after a callback or after `close`?
- Can it be called from another thread?

A good design must publish these conditions in the API contract, rather than forcing users to experiment to infer them.

### Basic Classification Table

| Contract type | Allocator/owner before the call | Recipient's rights | Who frees? | Typical example |
| --- | --- | --- | --- | --- |
| Borrowed, read-only | Data provider | Read within the published duration | **Original owner**; borrower does not `free` | C receives `const uint8_t *` and `size` only for the duration of the call |
| Borrowed, writable | Original owner | Read/write within the published duration | **Original owner** | C function writes into a caller-allocated buffer |
| Caller-allocated output | Caller allocates buffer and capacity | Callee writes at most capacity | **Caller** | `fill_bytes(out, cap, &written)` |
| Callee-allocated, caller-frees | Library allocates, returns ownership outward | Caller uses after the API returns | **Caller**, using the exact destructor/free API | `create_blob` + `destroy_blob` |
| Ownership transfer to callee | Caller currently owns | Callee retains and manages upon success | **Callee** after transfer | `adopt_blob`, `take_buffer` |
| Shared ownership | Multiple owners per protocol | Use while a valid shared reference/lease exists | Last owner per ref-count/contract | Native handle with `retain/release` |
| JNI borrowed elements | JVM manages Java array/string and Get privilege | C temporarily uses pointer provided by JNI | **C must call JNI Release to return the borrow lease**, not `free` | `GetByteArrayElements` → `ReleaseByteArrayElements` |
| Java-owned off-heap region via FFM | `Arena` manages | Use segment within allowed scope/thread | **Owner arena**, not freed arbitrarily with C `free` | `Arena.ofConfined().allocate(...)` |

**Distinguish the data owner from the responsibility to end a lease:** `GetByteArrayElements` may return a pointer into JVM data or a VM-managed copy. Native code **does not own the allocation to call `free`**, yet **still has the obligation to call `ReleaseByteArrayElements`** to return the usage right. This is a borrowed resource with a Get/Release pair, not a `malloc`-style caller-owned allocation.

## 2. Six Mandatory Questions for Every Pointer/Handle

When reviewing a native call, ask the following questions:

1. **Origin:** Does the pointer come from `malloc`, `new`, a Java array, `GetStringUTFChars`, `Arena.allocate`, `mmap`, an OS handle, or a third-party allocator?
2. **Owner:** Before the call, who is the owner? After a successful call, does the owner change?
3. **Lifetime:** Does the pointer live across **a single function**, **a callback**, **a request**, **a Java object**, or **until an explicit release call**?
4. **Allowed operations:** Is the pointer read-only/writable? Can it be retained, used from another thread, resized in capacity, or used to create another view?
5. **Failure:** If the API returns an error or a Java exception occurs, must the caller still free it? Could the callee have taken partial ownership?
6. **Deallocator:** Must we use `free`, `delete[]`, `destroy_blob`, `ReleaseStringUTFChars`, `DeleteGlobalRef`, `munmap`, or `Arena.close()`? Is a specific thread/allocator required?

Missing **even one** answer can lead to a memory leak, double-free, use-after-free, heap corruption, race condition, or JVM crash. An address within a valid numeric range is not enough to prove access rights: it also requires a live object, valid bounds, and a matching ABI.

## 3. Borrowed Rules: Do Not Free, Do Not Retain Past Expiration

A C function receiving read-only data:

```c
/* Contract: 'data' is borrowed from caller for the duration of the call.
 * length is the actual byte count; callee MUST NOT retain the pointer.
 * Callee MUST NOT free or write to data.
 */
unsigned long checksum_borrowed(const unsigned char *data,
                                size_t length);
```

**Correct contract:**

- The caller must ensure `data` points to at least `length` valid bytes for **the entire duration of the function call**.
- The callee only reads bytes within bounds.
- The callee **must not** store the pointer for use after the function returns, unless another contract permits it and has a separate lifetime mechanism.
- The callee must not call `free(data)`.
- After returning, the caller still owns the memory region and continues to control its lifecycle.

`const` is a signal about **mutability**, not sufficient documentation for ownership. A `const char *` pointer can still point to newly `malloc`ed memory that the caller must free with a dedicated API; conversely, `char *` does not necessarily allow the callee to free it.

### Borrowing for Callbacks and Async

If C receives:

```c
/* Illustrative C API; not a standalone implementation. */
typedef void (*bytes_callback)(void *ctx,
                               const unsigned char *data,
                               size_t length);
void register_callback(bytes_callback callback, void *ctx);
```

It is necessary to define whether **the callback only borrows data while the callback is executing** or **retains the pointer/ctx to invoke later**. If native code saves `ctx` pointing to a temporary Java/FFM buffer to use hours later, the synchronous borrowing contract has been violated.

For asynchronous callbacks, there must be a mechanism ensuring that **the data**, **the context**, **the native library/code**, and **the callback function pointer** all stay alive until the final callback completes. Merely holding a raw pointer in C does not make the Java GC treat that buffer as a strong Java reference.

## 4. Caller-Frees Rules: Use the Matching Allocate/Free Pair

Example of a C library owning an internal allocator:

```c
/* Example contract: create_blob returns ownership to the caller.
 * Returns NULL on failure. Caller calls destroy_blob exactly once
 * after use; never arbitrarily choose free/delete[].
 */
typedef struct Blob Blob;
Blob *create_blob(size_t length);
size_t blob_size(const Blob *blob);
const unsigned char *blob_data(const Blob *blob); /* borrowed */
void destroy_blob(Blob *blob);
```

In this example:

- The `Blob *` pointer returned from `create_blob` belongs to the **caller**.
- The `blob_data` function returns a **borrowed view** that lives at most until `destroy_blob(blob)` or a mutation that invalidates the view per contract.
- The caller must call `destroy_blob(blob)` **once** when finished (unless the contract allows `NULL` or transfers ownership elsewhere).
- Do not call `free(blob)` from Java/JNI code if the contract requires `destroy_blob`: the library may use an arena/pool allocator, memory-mapped storage, C++ `new`, or need to close other handles before freeing.
- Do not call `destroy_blob` and then continue reading `blob_data`: that is use-after-free.

**Allocator matching is a critical invariant:** whoever allocates through allocator X must free through the corresponding API of X. `malloc/free`, `new/delete`, `new[]/delete[]`, `CoTaskMemAlloc/CoTaskMemFree`, library `create/destroy`, and `Arena.allocate/Arena.close` **are not arbitrarily interchangeable**.

### Create–Destroy Pair Table

| Resource source | Allocate function/API | Return/release function/API |
| --- | --- | --- |
| Native C heap | `malloc` / `calloc` / `realloc` | `free` per contract; after `realloc` the owner pointer may change |
| C++ object | `new T` | `delete` or `std::unique_ptr<T>` |
| C++ array | `new T[n]` | `delete[]` or RAII container |
| Library opaque handle | `lib_create(...)` | `lib_destroy(handle)` published by the library |
| OS file/descriptor | `open` / `fopen` / platform API | `close` / `fclose` / platform-specific close |
| JNI byte elements | `GetByteArrayElements` | `ReleaseByteArrayElements` with the same array/pointer |
| JNI UTF string lease | `GetStringUTFChars` | `ReleaseStringUTFChars` with the same `jstring`/pointer |
| JNI global reference | `NewGlobalRef` | `DeleteGlobalRef` |
| FFM confined/shared memory | `Arena.allocate` | `Arena.close()` by the proper owner/lifetime |
| DirectByteBuffer wrapping C malloc | `malloc` and `NewDirectByteBuffer` | Native `free` per owner protocol; **not** auto-freed on buffer GC |

This table shows illustrative contracts; specific allocators/OSes/libraries have their own rules. Do not rely on pointer types or Java object names to infer the deallocator.

## 5. Ownership Transfer Rules: Both Sides Must Not Be Owners Simultaneously

When an API **takes ownership** (take/adopt), the contract must specify **the moment of handoff**:

```c
/* C API pattern with ownership transfer:
 *
 * SUCCESS:
 *   The function takes ownership of *inout and sets *inout = NULL.
 *   Caller no longer has the right to use/free the old object.
 *
 * ERROR:
 *   Ownership DOES NOT change; *inout remains the original pointer.
 *   Caller retains the obligation to destroy it.
 *
 * The function itself must implement this exact contract.
 */
int adopt_blob(Blob **inout);
```

The signature above is only a **design hint**; it does not automatically turn the contract into reality. The implementation must ensure that if it fails midway, it does not leave both caller and callee thinking they own the same buffer, or conversely **neither side owning it**.

### On Success

```c
Blob *owner = create_blob(128);
if (owner == NULL) {
    /* Handle allocation failure. */
} else if (adopt_blob(&owner) == 0) {
    /* Per contract: owner == NULL; callee has taken responsibility. */
} else {
    /* Per contract: owner is still owned by caller. */
    destroy_blob(owner);
    owner = NULL;
}
```

This snippet is **illustrative**; there is no implementation of `Blob`, `create_blob`, or `adopt_blob` here. The convention that `0` means success only applies if the API you design defines it that way.

### Failure Atomicity and Partial Transfer

The crucial question: **if the callee starts processing but returns an error, who frees it?** There are three common policies:

1. **Transfer only on success:** failure leaves ownership with the caller unchanged.
2. **Consume always:** the callee takes ownership immediately upon call, regardless of success or failure; the caller must not free after the call.
3. **Partial transfer:** each accepted part has its own owner, and the API must clearly indicate which parts were consumed. This style is hard to use and error-prone (leaks); avoid it if unnecessary.

Do not guess the policy from the return value. Document it and write unit tests. For untrusted native FFI or changing plugin ABIs, it is better to use **opaque handles**, **two-phase prepare/commit**, and easily verifiable error contracts.

### Shared Ownership Is Not Simple Transfer

A `retain(handle)`/`release(handle)` API can manage a reference count; in that case each owner holds one reference and only the final release destroys the object. Concurrency/atomic refcounting must be handled, cycles avoided, and which callbacks are allowed to retain must be specified. Do not create multiple `jlong` values containing the same pointer and treat each wrapper as an independent owner.

## 6. JNI: `Get...` Is a Borrowed Lease Paired with `Release`

In JNI, a Java array or Java `String` is managed by the JVM. A native method wanting to read values can borrow the data region via `Get...`. The returned pointer **is not a malloc pointer that the caller can free**.

### Array Elements: The JVM May Pin or Copy

```c
/* JNI C function pattern; env and byteArray are valid. */
jsize length = (*env)->GetArrayLength(env, byteArray);
jbyte *elements = (*env)->GetByteArrayElements(env, byteArray, NULL);
if (elements == NULL) {
    /* Get failed: no valid lease to release. */
    return; /* Only valid for a C function returning void. */
}
for (jsize i = 0; i < length; ++i) {
    /* Read elements[i] here. */
}
(*env)->ReleaseByteArrayElements(
        env, byteArray, elements, JNI_ABORT);
```

**The contract here:**

- The Java array remains managed by the JVM.
- `GetByteArrayElements` may create a copy or return a pointer into a pinned array; `isCopy` must not be used as a condition to skip `Release`.
- `ReleaseByteArrayElements` returns the usage right. For read-only processing, `JNI_ABORT` is appropriate to avoid copying back a copy; it does not automatically mean all changes to pinned memory can be rolled back.
- Do not retain `elements` after `Release` and do not store it in a global C variable for asynchronous use.
- Do not `free(elements)`; do not pass `elements` to a C API that **takes ownership** if that API will free it itself.
- `Get...ArrayCritical` has its own `ReleasePrimitiveArrayCritical` pair and the constraint **no blocking / no arbitrary JNI calls** inside the critical region.

#### Three Release Mode Values

| Mode | When JNI created a copy | Ownership meaning |
| --- | --- | --- |
| `0` | Copy back data, then free the copy | **Ends lease** |
| `JNI_ABORT` | Do not copy back; free the copy | **Ends lease**; commonly used for read-only |
| `JNI_COMMIT` | Copy back, but **do not free** the copy | **Does not end lease**; requires a final Release with `0`/`JNI_ABORT` |

According to the JNI Specification, if elements are not a copy, the mode does not magically create an "undo" for bytes modified directly. Do not use `JNI_ABORT` as a transaction rollback mechanism after writing to pinned data.

### String Access: Release with the Exact Pair

```c
/* jstring text is a Java reference, not char*. */
const char *utf = (*env)->GetStringUTFChars(env, text, NULL);
if (utf == NULL) {
    return; /* Illustrative snippet for a native void method. */
}

/* Read modified UTF-8 bytes up to the appropriate JNI length. */

(*env)->ReleaseStringUTFChars(env, text, utf);
```

`GetStringUTFChars` returns **modified UTF-8**, not necessarily the standard UTF-8 expected by C libraries. The borrowed pointer must end with `ReleaseStringUTFChars` regardless of whether the JVM allocated a copy. `GetStringChars` uses `const jchar*` in UTF-16 and **`ReleaseStringChars`**. Do not mix pairs, do not retain the pointer after Release, and do not use `free`.

**Important:** `DeleteLocalRef(text)` only manages the JNI reference; it **does not** replace `ReleaseStringUTFChars` for the pointer obtained via Get. Local ref expiration when a native frame returns to Java also does not make a Get without Release valid.

### If You Do Not Want a Lease, Use Region/Copy

`GetByteArrayRegion(env, array, 0, length, nativeBuffer)` **copies** into a C-allocated buffer. It does not create a borrowed pointer like `GetByteArrayElements`, so there is **no** `ReleaseByteArrayRegion`. The caller owns `nativeBuffer` according to its allocator.

`SetByteArrayRegion` copies data from a native buffer into a Java array; the Java array remains managed by the JVM afterward. A very safe ownership-conversion strategy is to **copy bytes at the boundary** instead of passing pointers directly. This usually incurs copy overhead, but cleanly separates lifetimes.

## 7. JNI References and Native Allocations Are Two Different Kinds of Ownership

JNI references are not identical to C pointers:

| JNI operation | What does it create? | Lifetime/cleanup |
| --- | --- | --- |
| `NewStringUTF` | Java `jstring` local reference | `DeleteLocalRef` when no longer needed; do not `free` Java object |
| `NewObject` | Java `jobject` local reference | JVM manages object; local ref scoped to JNI frame |
| `NewGlobalRef` | Global reference keeping Java object reachable | `DeleteGlobalRef` when finished |
| `NewWeakGlobalRef` | Weak global ref | `DeleteWeakGlobalRef` |
| `GetStringUTFChars` | Lease of a character region / MUTF-8 representation | `ReleaseStringUTFChars`, **distinct from** `DeleteLocalRef` |
| `malloc` in native library | C allocation | `free` / appropriate destructor |
| `jlong` holding malloc address | Integer representing a pointer, **does not imply ownership** | Wrapper/owner must define explicit close |

A C callback saving a `jobject` local reference into a global C variable and using it after the native method returns is a lifetime bug. To keep a Java object across calls, use `NewGlobalRef` and `DeleteGlobalRef` with the proper owner. Even with a global ref, another thread needs its own `JNIEnv*` via attach when appropriate; do not pass `JNIEnv*` across threads.

Do not use `DeleteGlobalRef` in place of `free` for a native allocation, or `free` in place of `DeleteGlobalRef`. They belong to two different resource management systems.

## 8. DirectByteBuffer: A Java View Does Not Implicitly Own a C Pointer

JNI provides:

```c
jobject NewDirectByteBuffer(
        JNIEnv *env, void *address, jlong capacity);
```

This API creates a direct `java.nio.ByteBuffer` viewing native memory at `address`, with `capacity` bytes. **It is not an implicit ownership transfer** to the JVM or a promise that GC of the buffer will call `free(address)` on C-allocated memory.

Dangerous example:

```c
/* Illustrative design bug, do not run as production code. */
void *mem = malloc(4096);
jobject view = (*env)->NewDirectByteBuffer(env, mem, 4096);
free(mem); /* WRONG: view still points to freed memory. */
return view; /* Only matches the native function signature returning jobject. */
```

Conversely, **not freeing** a C-allocated pointer while expecting `NewDirectByteBuffer` to auto-free when Java stops using it can also cause a leak.

A proper design requires an **owner handle** that stays alive at least until all views/callbacks using the buffer have finished; a Java `AutoCloseable` or native `destroy(handle)` takes responsibility. When the owner closes, old ByteBuffer aliases must be treated as invalid; since a standard ByteBuffer does not check the full C allocation lifetime, the wrapper API should not let views escape outside owner control.

The JDK's `ByteBuffer.allocateDirect(...)` has its own allocation and reclamation mechanism managed by the JDK; do not assume the same contract applies to **`NewDirectByteBuffer` wrapping a C pointer you `malloc`ed**. `GetDirectBufferAddress` returns the address of a direct buffer with valid backing memory per the API; it does not mean the caller may `free` that address.

## 9. Complete Java 17+ / JNI C11 Example: Borrowed Data vs. Caller-Closed Copied Memory

This exercise separates **two contract styles in the same program**:

- `borrowedSum(byte[])`: native code **borrows** Java bytes via `GetByteArrayElements`, computes the sum, and calls `ReleaseByteArrayElements(..., JNI_ABORT)` before returning. Native code does not own the array and does not retain the pointer.
- `nativeCopy(byte[])`: native code creates an **independent copy with `malloc`**, returning an opaque-ish `jlong` handle to the Java wrapper. Java **becomes the owner**, obligated to call `nativeFree` exactly once; `try-with-resources` does this reliably.
- `nativeChecksum(handle)`: **borrows** the native block from the wrapper for the duration of the call, without freeing or retaining the pointer.
- `nativeFree(handle)`: destroys the allocation with `free` in the **same native module** that allocated it.

Key result: modifying the Java input after copying causes a new borrow call to see the new Java data, while the native copy keeps the old contents.

**Example limitations:** runs on Linux/JDK 17+ where CPU pointers can convert via `intptr_t`/`jlong` (valid on common 64-bit Linux architectures). This is a **lesson on ownership**, not how to build a secure API; raw pointers wrapped in `jlong` must not be trusted if received from untrusted sources. Input is capped at 1 MiB so the sum of unsigned bytes is guaranteed not to overflow `jint` in the example.

### File 1 — `NativeOwnershipDemo.java`

```java
public final class NativeOwnershipDemo {
    static {
        System.loadLibrary("ownershipdemo");
    }

    private static final class OwnedBuffer implements AutoCloseable {
        // Only this wrapper owns the handle.
        // synchronized protects read/close on the SAME instance.
        private long handle;

        OwnedBuffer(byte[] input) {
            if (input == null) {
                throw new NullPointerException("input");
            }
            handle = nativeCopy(input);
            if (handle == 0) {
                throw new OutOfMemoryError("nativeCopy returned null");
            }
        }

        synchronized int checksum() {
            if (handle == 0) {
                throw new IllegalStateException("buffer closed");
            }
            return nativeChecksum(handle);
        }

        @Override
        public synchronized void close() {
            if (handle != 0) {
                long old = handle;
                handle = 0; // No longer owns the handle after this line.
                nativeFree(old);
            }
        }
    }

    // Native code borrows the Java array for the duration of the call.
    private static native int borrowedSum(byte[] source);

    // Native code allocates and transfers ownership to OwnedBuffer.
    private static native long nativeCopy(byte[] source);

    // Only reads native data while the owner is alive.
    private static native int nativeChecksum(long handle);

    // Closes the memory region allocated by nativeCopy.
    private static native void nativeFree(long handle);

    public static void main(String[] args) {
        byte[] source = {1, 2, (byte) 0xFF};

        System.out.println(
                "borrowedBefore=" + borrowedSum(source));

        OwnedBuffer owned = new OwnedBuffer(source);
        try (owned) {
            System.out.println(
                    "ownedBefore=" + owned.checksum());

            source[0] = 9;

            System.out.println(
                    "borrowedAfter=" + borrowedSum(source));
            System.out.println(
                    "ownedAfter=" + owned.checksum());
        } // owned.close() is automatically called once.

        try {
            owned.checksum();
            System.out.println("unexpectedUseAfterClose");
        } catch (IllegalStateException expected) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }

        owned.close(); // Idempotent on the Java wrapper.
        System.out.println("closeTwice=ok");
    }
}
```

Points to read carefully:

1. `OwnedBuffer` implements `AutoCloseable`, holds **one** handle and `close()`. The owner is the Java wrapper, not GC of a `long` number.
2. `try (owned)` is Java 9+ syntax, supported on Java 17 (effectively final resource variable). Even if code inside the block throws a Java exception, `close()` still runs.
3. `checksum()`/`close()` are `synchronized`, preventing two Java threads using **this same instance** from colliding during close. It does not protect if native code retains the pointer outside the wrapper, multiple wrappers share the same handle, or a callback uses the pointer after the call.
4. `close()` sets `handle = 0` before calling `nativeFree` to prevent double-free through the same wrapper. This demo does not assume native freeing is always recoverable on OS/native errors; production needs its own contract.
5. A `jlong` by itself provides no validity-checking capability. Do not expose pointer handles to untrusted code; production should consider an opaque registry with id/generation and a state machine.

### File 2 — `ownership_demo.c`

```c
#include "NativeOwnershipDemo.h" /* generated by javac -h, includes jni.h */
#include <stdint.h>             /* intptr_t, SIZE_MAX */
#include <stddef.h>             /* size_t */
#include <stdlib.h>             /* malloc, free */

/* Linux 32/64-bit demo where intptr_t fits in jlong. */
_Static_assert(sizeof(intptr_t) <= sizeof(jlong),
               "pointer does not fit into jlong");

/* Do not use input over 1 MiB to avoid jint sum overflow. */
#define MAX_INPUT (1024 * 1024)

typedef struct {
    jsize length;
    unsigned char bytes[]; /* Flexible array: copy-owned content */
} NativeBlock;

static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    jclass cls = (*env)->FindClass(env, class_name);
    if (cls != NULL) {
        (*env)->ThrowNew(env, cls, message);
        (*env)->DeleteLocalRef(env, cls);
    }
}

/* BORROWED: get Java array elements then Release; do not retain pointer. */
JNIEXPORT jint JNICALL
Java_NativeOwnershipDemo_borrowedSum(JNIEnv *env, jclass clazz,
                                     jbyteArray source) {
    (void)clazz;

    if (source == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "source");
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, source);
    if (length > MAX_INPUT) {
        throw_if_no_pending(env, "java/lang/IllegalArgumentException",
                            "demo limit: 1 MiB");
        return 0;
    }
    if (length == 0) {
        return 0;
    }

    jbyte *elements = (*env)->GetByteArrayElements(env, source, NULL);
    if (elements == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "GetByteArrayElements failed");
        return 0;
    }

    jint sum = 0;
    for (jsize i = 0; i < length; ++i) {
        sum += (jint)(unsigned char)elements[i];
    }

    /* Whether isCopy is true or false, C MUST return the lease. */
    (*env)->ReleaseByteArrayElements(
            env, source, elements, JNI_ABORT);
    return sum;
}

/* CALLEE ALLOCATES -> CALLER OWNS:
 * C creates a copy, returns handle; Java OwnedBuffer must nativeFree.
 */
JNIEXPORT jlong JNICALL
Java_NativeOwnershipDemo_nativeCopy(JNIEnv *env, jclass clazz,
                                    jbyteArray source) {
    (void)clazz;

    if (source == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "source");
        return 0;
    }

    jsize length = (*env)->GetArrayLength(env, source);
    if (length > MAX_INPUT) {
        throw_if_no_pending(env, "java/lang/IllegalArgumentException",
                            "demo limit: 1 MiB");
        return 0;
    }

    if ((size_t)length > SIZE_MAX - sizeof(NativeBlock)) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "allocation size overflow");
        return 0;
    }

    NativeBlock *block = (NativeBlock *)malloc(
            sizeof(NativeBlock) + (size_t)length);
    if (block == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "native malloc failed");
        return 0;
    }

    block->length = length;
    if (length > 0) {
        /* Copy into C-allocated memory. Do not borrow array pointer. */
        (*env)->GetByteArrayRegion(
                env, source, 0, length, (jbyte *)block->bytes);
        if ((*env)->ExceptionCheck(env)) {
            free(block); /* Error before transfer -> C is still the owner. */
            return 0;
        }
    }

    /* Upon successful return, ownership transfers to Java wrapper. */
    return (jlong)(intptr_t)block;
}

/* BORROWED handle: read-only, caller does not transfer ownership away. */
JNIEXPORT jint JNICALL
Java_NativeOwnershipDemo_nativeChecksum(JNIEnv *env, jclass clazz,
                                        jlong handle) {
    (void)clazz;

    if (handle == 0) {
        throw_if_no_pending(env, "java/lang/IllegalStateException",
                            "buffer closed");
        return 0;
    }

    NativeBlock *block = (NativeBlock *)(intptr_t)handle;
    jint sum = 0;
    for (jsize i = 0; i < block->length; ++i) {
        sum += (jint)block->bytes[i];
    }
    return sum;
}

/* CALLER-FREES: exact same allocator/module that created the block. */
JNIEXPORT void JNICALL
Java_NativeOwnershipDemo_nativeFree(JNIEnv *env, jclass clazz,
                                    jlong handle) {
    (void)env;
    (void)clazz;

    if (handle != 0) {
        NativeBlock *block = (NativeBlock *)(intptr_t)handle;
        free(block);
    }
}
```

**Branch-by-branch ownership explanation:**

- In `borrowedSum`, `GetByteArrayElements` succeeds → C holds **one JNI lease**. After computing the sum, `ReleaseByteArrayElements(..., JNI_ABORT)` completes the lease. If Get fails and returns `NULL`, C **does not** Release an unallocated pointer.
- In `nativeCopy`, immediately after `malloc`, C is the **owner**. If `GetByteArrayRegion` encounters an error, C must `free(block)` and not return an incomplete owned handle to Java.
- Only when `nativeCopy` returns a non-zero handle successfully does Java `OwnedBuffer` take responsibility for calling `nativeFree`. Do not add `free(block)` after a successful return.
- `nativeChecksum` only borrows the handle for the duration of the JNI call and does not free the pointer. The Java wrapper holds the `synchronized` monitor, so `close` on the same object cannot concurrently free while checksum is reading.
- `nativeFree` only accepts a handle that was successfully returned by `nativeCopy` **and not yet freed**. JNI has no built-in way to verify that a forged `jlong` points to a valid region. This is a precondition of the demo, not a security boundary.

### Build and Run on Linux

Create the two files `NativeOwnershipDemo.java` and `ownership_demo.c` in the same directory. JDK 17+ and a C compiler matching the JVM architecture are required. Set `JAVA_HOME` to point to a JDK with `include/jni.h`:

```bash
javac -encoding UTF-8 -h . NativeOwnershipDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libownershipdemo.so ownership_demo.c

java -Djava.library.path=. NativeOwnershipDemo
```

`javac -h .` generates `NativeOwnershipDemo.h` with exported JNI method declarations. Linux maps the logical name `ownershipdemo` from `System.loadLibrary` to `libownershipdemo.so`. Windows/macOS require different build flags and native binary names; this program is a demo for Linux/JDK 17+.

### Expected Stdout

```text
borrowedBefore=258
ownedBefore=258
borrowedAfter=266
ownedAfter=258
afterClose=IllegalStateException
closeTwice=ok
```

Why?

- `source` contains unsigned byte values 1, 2, 255. Although in Java `(byte)0xFF` is displayed as signed -1, the C code explicitly casts to `unsigned char`, so `1 + 2 + 255 = 258`.
- `nativeCopy` copies the **initial three bytes** into newly `malloc`ed memory. `ownedBefore=258`.
- After Java changes `source[0]` from 1 to 9, `borrowedSum` on the new call borrows the **current** array and returns `9 + 2 + 255 = 266`.
- The independent native block still contains 1, 2, 255, so `ownedAfter=258`.
- Upon exiting `try (owned)`, `close()` calls `nativeFree`. Any subsequent `checksum()` calls are blocked by the Java wrapper with `IllegalStateException`, without dereferencing the old pointer.
- Calling `owned.close()` again has no effect because the wrapper already set the handle to 0, so it prints `closeTwice=ok`. This only protects **the same wrapper**; it does not prove that two wrappers sharing a pointer is safe.

The program does not use `System.gc()`, does not rely on finalizers or Cleaner, and does not automatically "move" the Java array onto the native heap; it **intentionally copies** to decouple lifetimes.

## 10. Limitations of `jlong` Holding a Pointer: Demo vs. Production

In the demo, `jlong handle` holds a native address to focus on the ownership lesson. However, a function receiving `long handle` from a public API cannot automatically know:

- Was the handle allocated by this exact allocator/library?
- Has it already been `free`d (stale handle)?
- Were any address bits modified?
- Do two wrappers both think they are the owner?
- Is another thread reading the block while the owner closes it?
- Is the native module/library containing the free code still loaded?

Dereferencing an invalid pointer in C **can crash the JVM**; it is not always converted into a Java exception. Therefore, production should use an **opaque handle registry** instead of directly trusting an address supplied by the caller. A safer model can assign an id/generation, guard the registry under a lock, count active borrows, and only free when no borrowers remain.

```text
Java AutoCloseable owner
      |
      +-- handle id + generation (not a raw address)
               |
               v
Native registry (lock/ref-count/state)
      |
      +-- OPEN: allows temporary pointer checkout
      +-- CLOSING: rejects new borrows
      +-- CLOSED: frees native allocation exactly once
```

The registry/lock must also have a policy for handling callbacks and reentrancy. `synchronized` in the demo protects one Java instance; it does not replace a registry mechanism if multiple handles point to one allocation, C retains pointers asynchronously, or users can invoke JNI directly via reflection/native APIs.

**Do not use `Cleaner` as the primary deallocation mechanism** for resources requiring deterministic cleanup. It can be used as a safety net if the state/deallocator is designed properly, but cleanup timing is decided by GC and has no deadline. `finalize()` is not an option for native owners. `AutoCloseable` + `try-with-resources` or C++ RAII is a clearer approach.

## 11. C++ RAII and Per-Resource Contracts

C++ often turns ownership into a **non-copyable** object whose destructor calls the right deleter. Illustrative example:

```cpp
#include <memory>

/* 'Blob' and 'destroy_blob' are hypothetical native APIs. */
struct BlobDeleter {
    void operator()(Blob *p) const noexcept {
        if (p != nullptr) {
            destroy_blob(p);
        }
    }
};

using UniqueBlob = std::unique_ptr<Blob, BlobDeleter>;

void example() {
    UniqueBlob owned(create_blob(128));
    if (!owned) {
        return;
    }

    // blob_data(owned.get()) returns a BORROWED pointer.
    const unsigned char *view = blob_data(owned.get());
    // Use view while owned is alive, per contract.

} // ~unique_ptr automatically calls destroy_blob exactly once.
```

This is **illustrative C++ code**; it requires a header declaring `Blob`, `create_blob`, `destroy_blob`, and `blob_data` before compiling standalone. Meaning:

- `UniqueBlob` is a unique owner, preventing double-destroy via copying.
- `view` is only borrowed from the object owned by `owned`; it must not be used after the destructor runs.
- `owned.release()` (if called) transfers the raw pointer out of `unique_ptr` **without destroying it**: from then on there must be a clear new owner; discarding the pointer will leak.
- `owned.reset(newPointer)` destroys the old object and takes ownership of the new one (using the configured deleter).

To **transfer** from a unique owner into a native API:

```cpp
/* Conceptual pattern: take_blob has a contract to take ownership
 * only when returning success; the transfer must preserve the owner
 * on failure. Do not call raw.release() before knowing
 * the API has actually consumed the object!
 */
```

If the `take_blob` API always consumes ownership whether it succeeds or fails, `release` can be used per contract. If transfer occurs only on success, design an adapter or an API taking pointer-to-pointer to ensure the owner is not lost on failure. **Do not assume** every `void*` accepted by a C function automatically becomes callee-owned.

## 12. FFM Java 22+: Arena Is the Owner, MemorySegment Is a Lifetime-Bound View

FFM finalized in JDK 22 uses `java.lang.foreign.Arena` and `MemorySegment` to make ownership/lifetime **explicit** on the Java side:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeData =
            arena.allocate(ValueLayout.JAVA_INT);

    nativeData.set(ValueLayout.JAVA_INT, 0, 42);
    int answer = nativeData.get(ValueLayout.JAVA_INT, 0);
    System.out.println(answer); // 42
} // arena.close() frees the backing native memory.
```

This is an illustrative snippet that must be placed inside a class/method; it only runs on JDK 22+. Java 17 uses a different FFM incubator API.

**Ownership mechanics:**

- `Arena.ofConfined()` creates an owner with deterministic lifetime; only the owner thread may access and close it.
- `Arena.ofShared()` allows multiple threads to access, but the caller must still coordinate when to close; it does not automatically eliminate data races.
- `Arena.ofAuto()` lets GC manage lifetime with **non-deterministic release timing** and does not support explicit close.
- `Arena.global()` has an unbounded lifetime for the life of the VM.
- `MemorySegment.asSlice(...)`, `asReadOnly()`, and `asByteBuffer()` are views; they **do not turn into owners with independent lifetimes**.

Do not manually `free` `nativeData.address()` using an arbitrary C function: the allocation belongs to the arena. When `arena.close()` succeeds, segments/views from that arena lose access rights per contract; calling `get` after close may throw `IllegalStateException`. If C retains the raw address past expiration, Java checks cannot protect dereferences from C.

### When a C Library Returns a Pointer and Tells Java to Free It

FFM can interact with pointers returned by C libraries. However, Java cannot guess the **true length**, **alignment**, **owner**, and **correct deallocator** from an address alone. Restricted operations such as `MemorySegment.reinterpret(...)` attach bounds/lifetime per contract; an incorrect declaration can allow out-of-bounds access past the backing allocation or use after C `free`.

A safe design is to provide a `native_alloc(...)`/`native_free(...)` pair in the native library itself, wrap the pointer in a Java `AutoCloseable` owner, and prevent the pointer from escaping its lifetime. If an FFM downcall invokes C `free`, it must use the matching allocator and function descriptor. A reinterpret operation **does not transfer ownership** unless the C API permits it.

**Distinguishing FFM from JNI:** `MemorySegment` has bounds/scope checks when accessed via FFM, whereas the demo's `jlong` pointer has no such checks. Even so, both still require understanding exact ownership when crossing the boundary and when C retains pointers.

## 13. Exception Safety and Cleanup on Every Branch

A resource can be acquired successfully and then subsequent logic fails. You cannot only free on the "happy path".

A suitable C pattern is **a single cleanup block at the end of the function**:

```c
/* JNI C pseudocode; env, javaArray, and parameters are valid. */
jbyte *borrowed = NULL;
unsigned char *owned = NULL;
jint result = 0;

borrowed = (*env)->GetByteArrayElements(env, javaArray, NULL);
if (borrowed == NULL) {
    goto cleanup;
}

owned = (unsigned char *)malloc(1024);
if (owned == NULL) {
    goto cleanup;
}

/* Process data; may fail or a JNI callback may throw an exception. */
result = 1;

cleanup:
free(owned); /* free(NULL) is valid. */
if (borrowed != NULL) {
    (*env)->ReleaseByteArrayElements(
            env, javaArray, borrowed, JNI_ABORT);
}
return result;
```

This is **illustrative code**, not a complete exported JNI function. In production, malloc failures must be converted into a Java exception when no exception is pending, and the original Java error must be preserved if a JNI callback throws. `ReleaseByteArrayElements` is a JNI cleanup call permitted while an exception is pending.

With C++, an RAII wrapper holding `JNIEnv*`, `jbyteArray`, and the pointer from `GetByteArrayElements` has a `noexcept` destructor calling `ReleaseByteArrayElements`; forbid copying the wrapper to avoid releasing twice. A pending Java exception **does not automatically unwind the C++ stack**: native code must proactively check `ExceptionCheck` and `return` or enter the cleanup path. Never let a C++ exception cross the JNI boundary.

**Ownership on error branches must be clear:**

- Before a successful transfer, the C allocator is still the owner; if initialization fails, it frees.
- After a successful transfer, the Java caller is the owner; if a Java method later throws an exception, `try-with-resources` still calls close.
- Borrowed JNI elements/string leases must be Released exactly once on every branch where Get succeeded.
- If cleanup also fails, there must be a policy not to mask the original Java error; JNI cleanup functions are permitted during a pending exception, but arbitrary unsafe JNI operations must not be called.

## 14. Concurrent Access: Who May Free While Borrowers Remain?

An ownership design can be correct on one thread yet wrong across multiple threads:

```text
Thread A: owner.checksum()
           |
           +-- borrowed pointer is being read
                                Thread B: owner.close()
                                          |
                                          +-- free(pointer)
           |
           +-- continues reading => use-after-free
```

In the demo, the Java methods `checksum()` and `close()` are both `synchronized` **on a single owner instance**, so those two operations do not run concurrently through that wrapper. However:

- If C retains the pointer beyond the duration of `nativeChecksum`, the wrapper lock no longer protects it.
- If two Java wrappers share one pointer, wrapper A's lock does not synchronize with wrapper B's lock.
- If a callback receives a pointer and runs asynchronously, appropriate lifetime extension/registration is required.
- If a thread calls native `free` directly, a Java lock cannot stop it.
- If a foreign library unloads before the owner closes, the deallocator may also no longer be valid.

A better protocol for async: **stop accepting new borrows → wait for active operations/callbacks → release owner once**. Borrow leases can be counted with a refcount under a mutex or state machine. Do not close an arena/free a buffer just because a `Future` was created or a Java request returned.

### Do Not Share `JNIEnv*` Across Threads

`JNIEnv*` is only valid in its corresponding thread. When another native thread must call back into the JVM, attach the thread via the Invocation API to obtain its own `JNIEnv*` and detach appropriately. JNI local references also have frame/thread lifetimes; if storing a Java object for long-lived callbacks, use `NewGlobalRef`/`DeleteGlobalRef` with a separate lifecycle. A global ref does not replace native pointer ownership.

## 15. Distinguishing Copyable Data from Mandatory Zero-Copy Data

| Context | Copy | Borrow/zero-copy |
| --- | --- | --- |
| Small string/byte[], synchronous processing | Easy-to-understand lifetime, less aliasing | Can avoid copy, but must Release properly and not retain pointer |
| Asynchronous native callback | Copy into native-owned buffer with explicit free | Only when owner and active-borrow protocol are clear |
| Large performance-sensitive buffer | Has copy cost, can use a pool | Requires proper scope/lifetime, synchronization, and deallocator |
| Java caller needs to keep result for hours | Return Java array/object or clear owner handle | Cannot return a JNI Get pointer that was Released |
| C API returns allocated string | Copy into Java String then call library's free | Keeping raw pointer forces Java to manage native owner long-term |
| FFM using temporary native buffer | Confined/shared Arena with exact close | Shared scope stays alive and native does not retain pointer after close |

**There is no rule that zero-copy is always better.** The copy cost of a few KiB can be smaller than the risk of holding a large native region, pinning, GC pressure, or concurrency complexity. Choose based on actual lifetime and measured benchmarks.

## 16. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `free` pointer from `GetByteArrayElements` | Wrong allocator/ownership, may crash | Call matching `ReleaseByteArrayElements` |
| `ReleaseStringChars` for `GetStringUTFChars` pointer | Wrong lease type | Use `ReleaseStringUTFChars` |
| Skipping Release because `isCopy == JNI_FALSE` | Holds pin/lease too long | Always Release when Get succeeds |
| Using `JNI_COMMIT` then treating buffer as freed | Lease remains open if copied | Final Release with `0`/`JNI_ABORT` |
| `DeleteLocalRef` instead of `free`ing native block | JNI reference does not own malloc block | Use the native owner's proper deallocator |
| `NewDirectByteBuffer` then `free` immediately | Java ByteBuffer points to freed memory | Keep native owner alive until all views finish |
| Assuming ByteBuffer GC auto-`free`s C malloc | Leak | Explicit owner `close`/native destroy |
| Passing borrowed pointer to `adopt` function | Callee may free memory it does not own | Copy or transfer from real owner per contract |
| Calling `destroy_blob` twice | Double-free | Unique ownership, set handle to 0, registry/state |
| Native function fails midway and both sides free | Heap corruption | Document transfer-on-success/failure atomicity |
| Native function fails and neither side frees | Leak | Caller retains ownership on error or callee consumes always per contract |
| Saving JNI local ref for another thread | Ref expired/wrong thread | Global ref + valid thread attach |
| `Arena.close()` while C uses raw pointer | Use-after-free | Wait for active native calls, define valid scope |
| Native C retains pointer, Java uses `Arena.ofAuto()` and drops owner | GC does not know C pointer is a strong ref | Explicit lifetime/handshake, do not rely on GC |
| Trusting `jlong` handle from client as safe | Forged/stale pointer may crash | Opaque registry id/generation and ownership checks |
| Two wrappers owning one pointer | Double-free or UAF | Factory creates only one owner, or shared refcount |
| Ignoring allocation/exception errors | Returns incomplete handle, leak | Cleanup before transfer; do not swallow pending exceptions |

## 17. Checklist for Reviewing Contracts Between Java and C

**Before publishing a native API**, each pointer/handle should have documentation for:

1. **Direction:** Java → C or C → Java?
2. **Type:** Java array/String, JNI reference, JNI elements lease, C heap, OS handle, direct ByteBuffer, or FFM segment?
3. **Ownership at entry:** Who is the owner before the call?
4. **Ownership at exit:** Who is the owner on success? On failure?
5. **Borrow lifetime:** Only during the call, only during the callback, or until an explicit release?
6. **Mutation:** Read-only, writable, what does copy-back mode mean?
7. **Size:** Is there a pointer + byte length; bytes, UTF-16 code units, or element count?
8. **Allocator:** Which `free`/`delete`/`destroy`/JNI Release/`Arena.close` API is used?
9. **Null/error:** Does null mean empty, failure, or ownership not transferred?
10. **Thread:** Can the owner move between threads? JNI environment, lock/refcount, callbacks?
11. **Exceptions:** Have all error branches freed/released previously acquired resources?
12. **Concurrency:** Is there a mechanism preventing free while a borrow is in use?
13. **Multiple owners:** Is there a real refcount or just two variables pointing to the same address?
14. **Observability:** Are there leak/double-free tests, active-handle counts, and appropriate sanitizer/JNI checks?
15. **Security:** Can forged/stale pointers be sent by the caller? Is a registry needed?
16. **Version/ABI:** Are binary, pointer width, alignment, allocator, and library module consistent?

A short contract written alongside the API is more useful than a vague promise like "caller takes care of memory".

## 18. Self-Check Questions

**Question 1.** `GetStringUTFChars` succeeds and `isCopy == JNI_FALSE`. Can native code skip `ReleaseStringUTFChars`?

**No.** `isCopy` describes the implementation; the obligation to end the lease still exists. The pointer must not be `free`d with the C allocator.

**Question 2.** `NewDirectByteBuffer` wraps a C `malloc`. Will Java GC automatically `free` that pointer?

**Do not assume so.** JNI creates a view into native memory provided by the caller; the API must have a clear owner/lifetime and deallocator. JVM-allocated `ByteBuffer.allocateDirect` has a different contract.

**Question 3.** `create_blob()` returns `Blob *` and the docs require `destroy_blob()`. Can `free(blob)` be used instead?

**No.** The library may use a custom allocator, close other handles, or use `new`. Strictly follow `destroy_blob`.

**Question 4.** `adopt_blob(&p)` fails. Must the caller free `p`?

Under the **transfer only on success** policy published in the example, failure keeps ownership with the caller and the caller must destroy it. However, with another library, the policy might be **consume always**; you must read the specific contract rather than guessing from the function name.

**Question 5.** Does `GetByteArrayElements` followed by `Release(..., JNI_COMMIT)` end the borrow?

**Not yet** if elements are a copy: `JNI_COMMIT` copies back but does not free the buffer, requiring a final Release. Only use `JNI_COMMIT` when you need to continue using the pointer per contract.

**Question 6.** Why does `borrowedSum` change its result after modifying Java `source[0]`, while `nativeChecksum` stays the same?

Because `borrowedSum` borrows the Java array's contents on **each call**, whereas `nativeCopy` created an independent native copy and **transferred ownership** to the Java wrapper.

**Question 7.** Does setting `handle = 0` in a wrapper's `close()` guarantee the whole program cannot double-free?

**No.** It makes that individual wrapper idempotent. If there are multiple wrappers with the same address, C callbacks retaining the pointer, or clients able to forge handles, full registry/refcount/locking is needed.

**Question 8.** Is it valid to use `Arena.ofConfined()` to return a `MemorySegment` and close the arena before the caller uses it?

**No.** The scope is closed so the segment/view loses access rights; you must copy the data, or transfer the ownership design to the caller with an arena of appropriate lifetime.

**Question 9.** A Java callback retains a borrowed pointer to run 10 seconds later. Is that valid?

Only if the API contract **permits retention** and there is an ownership/lifetime handshake ensuring the owner stays alive. A normal call/callback borrow **must not** be extended like that on its own.

**Question 10.** FFM `MemorySegment` has bounds/scope checks, so does that guarantee a pointer allocated by a C library will not be freed prematurely?

**No.** FFM metadata does not replace the C allocator contract. Restricted `reinterpret` can declare the wrong size/lifetime; C can still free without Java knowing.

## 19. Official Documentation

- Oracle JNI Specification — [Get/Release primitive array elements, `JNI_ABORT` and `JNI_COMMIT`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#getprimitivetypearrayelements-routines).
- Oracle JNI Specification — [String operations: `GetStringUTFChars` and `ReleaseStringUTFChars`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#string-operations).
- Oracle JNI Specification — [Direct Byte Buffers, `NewDirectByteBuffer`/`GetDirectBufferAddress`](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#nio-support).
- Oracle JNI Specification — [JNI global/local references and lifetime](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html#global-and-local-references).
- Oracle Java SE 17 — [`AutoCloseable` and `try-with-resources`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html).
- Oracle Java SE 22 — [FFM `Arena`, ownership/scope and `close()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- Oracle Java SE 22 — [FFM `MemorySegment`, bounds, scope and views](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- OpenJDK JEP 454 — [FFM finalized in JDK 22](https://openjdk.org/jeps/454).

**Takeaway:** *borrowed* means **temporarily usable without ownership**; *ownership transferred* means **the new owner is responsible for destruction after a defined handoff point**; *caller-frees* means **the caller must use the exact deallocator per the allocator's contract**. JNI Get/Release is **a special JVM lease**, not malloc. Prefer **single ownership, explicit lifetimes, cleanup on all error branches, and never freeing memory that does not belong to you**.
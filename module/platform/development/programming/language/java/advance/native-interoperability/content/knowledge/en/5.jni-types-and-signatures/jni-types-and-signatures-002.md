# Distinguishing `jlong`, native addresses, and C pointer types

In the Java Native Interface (JNI), a Java `long` argument is represented on the C side by `jlong`. Meanwhile, the address of a native memory region is usually stored in a variable of type `void *`, `char *`, `struct T *`, or another C pointer type. On 64-bit machines, these values often share the same 64-bit width, but **they do not have the same type, do not have the same meaning, and do not have the same lifetime**.

A very common misconception is: “Java `long` is 64 bits, so it can be treated as an address everywhere.” This is dangerous on 32-bit platforms, Windows 64-bit, when the memory region has already been freed, when the GC moves a Java object, or when an arbitrary number is converted into a pointer. This lesson presents how to accurately distinguish the concepts, how to design JNI signatures, conditions for controlled conversion, and a runnable Java 17 + C11 example.

## 1. Three concepts that must be kept separate

| Concept | Where is the type? | Nature | Width/characteristics | Who manages the lifetime? |
| --- | --- | --- | --- | --- |
| `long` | Java language | Signed integer | **Always 64-bit** per Java | JVM manages primitive values |
| `jlong` | JNI header `jni.h` | Native primitive type corresponding to Java `long` | **Signed, 64-bit** per JNI | A normal C value, does not own memory |
| Native address | Not a separate C type | Value referencing a location in the process's address space | Depends on ABI/architecture and pointer representation | The memory behind the address has its own lifetime |
| `T *` / `void *` | C/C++ | Typed pointer or generic object pointer | `sizeof(void *)` is typically 4 or 8 bytes on common platforms | Must follow the allocation's contract |
| `intptr_t` / `uintptr_t` | C99+ `<stdint.h>` | Integer type capable of holding a pointer-to-object representation for round-trip if provided by the implementation | Matches pointers on that implementation; **not required to be supported** by every C implementation | Only holds a number, does not extend lifetime |
| `jobject` / `jstring` | JNI | **Opaque reference** of the JVM to a Java object | Must not be treated as a stable address of the object | JVM and local/global JNI reference rules |

Three examples to remember:

- `jlong n = 123;`: this is **the number 123**; no native memory region is created.
- `int *p = malloc(sizeof *p);`: `p` holds a **pointer** to native memory, if `malloc` succeeds; it must be freed according to the contract.
- `jlong handle = (jlong)(intptr_t)(void *)p;`: this is an **application-defined convention for encoding a pointer as a number**. JNI does not automatically track or validate this handle.

In particular, Java `Long` (uppercase L) is a **wrapper object**: if it is passed into a native method, JNI receives a `jobject` (with an object signature), not a primitive `jlong`. Do not cast a JVM object reference to `void *` to obtain a “Java object address”.

## 2. Type widths by ABI

Do not infer the size of C `long` from Java `long`. On common ABIs:

| Common platform | Data model | C `int` | C `long` | `void *` | `intptr_t` | JNI `jlong` |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Linux 32-bit x86 | ILP32 | 32 | 32 | 32 | 32 | 64 |
| Common Linux/macOS 64-bit | LP64 | 32 | 64 | 64 | 64 | 64 |
| Windows 64-bit | LLP64 | 32 | **32** | 64 | 64 | 64 |

The numbers in the table are **bits**; these are common ABIs, not a guarantee for every CPU or every C implementation. Some environments use pointers with special representations or wider than 64 bits; the sample code below intentionally does not support such environments.

Consequences:

1. `(long)ptr` can **truncate the upper half of the address on Windows 64-bit** because C `long` is only 32 bits.
2. `(jint)ptr` is also unsafe for 64-bit pointers. `jint` is a signed 32-bit integer.
3. `sizeof(jlong) == sizeof(void *)` on many 64-bit machines **does not turn `jlong` into a pointer**; equal size does not guarantee access rights, validity, or ownership.
4. `size_t` represents object sizes, `ptrdiff_t` represents the difference between two pointers in valid cases; neither is a “JNI pointer type”. On many ABIs they have a width close to pointers, but the specific contract must be checked.
5. `jlong` is signed. If a handle is negative after conversion, do not arbitrarily conclude it is an error just because `handle < 0`.

In JNI, the JVM signature for Java primitive `long` is **`J`**; for `int` is **`I`**; for `void` is **`V`**. They describe **the data type passed across JNI**, not whether a `long` number contains a pointer.

## 3. `intptr_t` and `uintptr_t`: when can they be used?

The C header `<stdint.h>` may define:

- `intptr_t`: a **signed integer** type capable of representing a pointer **to an object** according to the implementation's round-trip rules.
- `uintptr_t`: the **unsigned integer** version, useful when manipulating/displaying bits or checking address values according to platform conventions.

These two types are **optional in the C standard**: some implementations may not provide them. When they exist, you can convert `void *` → corresponding integer type → `void *` and get back a pointer that compares equal to the original pointer, provided there is no data loss and no lifetime violation. This is a guarantee about the **pointer value**, not a promise that the pointer still points to a living object.

An important limitation: conversion via `intptr_t`/`uintptr_t` is described for **pointers to objects**, not a universal rule for **function pointers**. Do not assume casting a function pointer to `jlong`/`void *` works across all C ABIs.

### 3.1. Controlled convention for object pointer ↔ `jlong`

For implementations that have `intptr_t` and pointers no wider than 64 bits:

```c
#include <jni.h>
#include <stdint.h>

#ifndef INTPTR_MAX
#  error "This C implementation has no intptr_t"
#endif

_Static_assert(sizeof(intptr_t) <= sizeof(jlong),
               "This JNI handle cannot hold a native pointer");

typedef struct NativeState NativeState;

static jlong encode_pointer(NativeState *p) {
    return (jlong)(intptr_t)(void *)p;
}

static NativeState *decode_pointer(jlong raw) {
    return (NativeState *)(void *)(intptr_t)raw;
}
```

Step-by-step explanation:

1. `NativeState *` → `void *`: converts an **object pointer** to a generic object pointer.
2. `void *` → `intptr_t`: converts through the **integer type matching the pointer width** of the implementation; supports round-trip when used under the right conditions.
3. `intptr_t` → `jlong`: converts a **signed integer** to the 64-bit signed JNI type. Because the example requires `sizeof(intptr_t) <= sizeof(jlong)` and both types are signed, on common 32/64-bit ABIs the value is preserved.
4. When reading back, convert `jlong` → `intptr_t` → `void *` → `NativeState *`. Only dereference if it is **the exact original pointer, the object is still alive, the type matches, and there is no data race**.

Important condition: **only decode numbers produced by the encode function itself within the same process**, with the same ABI convention, within the object's lifetime. A `long` value entered from Java, read from a database, sent over the network, or copied from a log is not implicitly a valid pointer.

### 3.2. Why not use a direct cast?

The following snippets are risky:

```c
/* Avoid: C long can be only 32 bits on Win64. */
jlong bad1 = (long)some_pointer;

/* Avoid: casting a pointer to a 32-bit integer will lose data. */
jint bad2 = (jint)(intptr_t)some_pointer;

/* Avoid using a random number as an address. */
void *bad3 = (void *)(intptr_t)123456;
```

The code above only illustrates **anti-patterns**, not a standalone C program. When converting a pointer through an integer type incapable of holding it, data can be truncated/altered; decoding it back to a pointer and dereferencing it can lead to undefined behavior or a JVM crash.

Another common path is `(jlong)(uintptr_t)ptr`. `uintptr_t` is unsigned, while `jlong` is signed; on 64-bit platforms, an unsigned number with the high bit set to 1 may fall outside the range of `jlong`. The rule for converting to a signed type when out of range is **implementation-defined** in C. Therefore, for round-trip on environments that support `intptr_t`, going through **signed `intptr_t`** as in the example is clearer.

Do not treat `sizeof(intptr_t) <= 8` as the sole sufficient condition for all architectures: the example only applies when the implementation supports converting object pointers via `intptr_t` and guarantees round-trip. For platforms with capability pointers, separate address spaces, or pointers wider than 64 bits, a different handle design must be used.

### 3.3. Printing addresses for debugging

C uses the `%p` format specifier with a `void *` argument:

```c
#include <stdio.h>

void show_address(const void *ptr) {
    printf("native address=%p\n", (const void *)ptr);
}
```

The output after the `=` sign depends on the process, ASLR, C library, and platform; **there is no fixed stdout address**. Using `%ld` to print a pointer is the wrong argument type and can cause undefined behavior. The value printed by `%p` is for diagnostics, not a primary key or stable data transfer format.

## 4. What parameters does JNI receive and how are they denoted?

Java example:

```java
class NativeBridge {
    private static native long open(int size);
    private static native int read(long handle);
    private static native void close(long handle);
}
```

Correspondence in **types** (signature illustration only, no JNI implementation yet):

| Java method | Method descriptor in JVM | Corresponding C parameter/return types |
| --- | --- | --- |
| `open(int) : long` | `(I)J` | Takes `jint`, returns `jlong` |
| `read(long) : int` | `(J)I` | Takes `jlong`, returns `jint` |
| `close(long) : void` | `(J)V` | Takes `jlong`, returns `void` |

For **static** native methods, the exported C signature usually starts with `JNIEnv *env, jclass clazz` followed by the Java parameters. For **instance** native methods, the second parameter is `jobject self` instead of `jclass`. The `JNIEXPORT` and `JNICALL` macros in the JNI header help use the correct visibility and calling convention. Symbol names can encode the package, class, method name, and overload signature; the least error-prone way is to run **`javac -h .` to generate the C header** and include the generated file.

`jlong` **does not carry ownership on its own**. The same `long` type in Java can be used to hold a timestamp, counter, file offset, randomly generated ID, encoded pointer, or a token into a registry table. How the value is interpreted must be defined by **each method's contract**.

## 5. Runnable example: Java 17 + JNI + C11 with a native handle

The example manages a small struct on the C heap, wrapped by a Java `AutoCloseable`. The `get()/set()` operations access the same native object. Java only holds a `long handle` and does not dereference memory. Only C has the authority to turn an issued handle into a pointer and use it.

**Runnable scope:** Common Linux x64, JDK 17+, GCC/Clang supporting C11, `intptr_t` available. Java code does not use FFM or internal `Unsafe`.

### 5.1. File `NativeCounter.java`

```java
public final class NativeCounter implements AutoCloseable {
    static {
        System.loadLibrary("nativecounter");
    }

    // 0 is the closed / no valid handle state.
    private long handle;

    private static native long nativeCreate(int initial);
    private static native int nativeGet(long handle);
    private static native void nativeSet(long handle, int value);
    private static native void nativeDestroy(long handle);

    public NativeCounter(int initial) {
        long created = nativeCreate(initial);
        if (created == 0L) {
            throw new OutOfMemoryError("Cannot allocate native counter");
        }
        handle = created;
    }

    private void requireOpen() {
        if (handle == 0L) {
            throw new IllegalStateException("NativeCounter is closed");
        }
    }

    public synchronized int get() {
        requireOpen();
        return nativeGet(handle);
    }

    public synchronized void set(int value) {
        requireOpen();
        nativeSet(handle, value);
    }

    @Override
    public synchronized void close() {
        long toRelease = handle;
        handle = 0L; // No longer call native with this handle from the wrapper.
        if (toRelease != 0L) {
            nativeDestroy(toRelease);
        }
    }

    public static void main(String[] args) {
        try (NativeCounter counter = new NativeCounter(41)) {
            System.out.println("before=" + counter.get());
            counter.set(42);
            System.out.println("after=" + counter.get());
        }
        System.out.println("closed");
    }
}
```

On the Java side:

- `handle` is **a signed 64-bit integer**. Only the class's own native methods understand the convention that this number is an encoded pointer.
- `nativeCreate` is **the only place that allocates**. In the example's contract, `0L` means allocation failed; this is the example's convention on the chosen ABI.
- `get()` and `set()` check that the object is not closed. `synchronized` ensures calls through **the same instance** do not interleave with `close()`.
- `close()` clears the handle field and calls the native destructor exactly once; calling `close()` multiple times on **the same instance** will not double-free.
- `try-with-resources` guarantees `close()` when exiting the block even if a Java exception occurs; GC does not automatically know that a primitive `long` is holding a C heap allocation.

### 5.2. Generating the JNI header from Java

Run in the directory containing only the example code:

```bash
javac -h . NativeCounter.java
```

This command creates `NativeCounter.class` and `NativeCounter.h`. The generated header has declarations like the following (this is a **signature illustration**; include the exact header generated by `javac -h`, do not overwrite it manually):

```c
JNIEXPORT jlong JNICALL Java_NativeCounter_nativeCreate
    (JNIEnv *, jclass, jint);

JNIEXPORT jint JNICALL Java_NativeCounter_nativeGet
    (JNIEnv *, jclass, jlong);

JNIEXPORT void JNICALL Java_NativeCounter_nativeSet
    (JNIEnv *, jclass, jlong, jint);

JNIEXPORT void JNICALL Java_NativeCounter_nativeDestroy
    (JNIEnv *, jclass, jlong);
```

Note that `jlong` is a **value type** in these prototypes. The signatures do not contain `void *` because the Java methods do not declare pointer-type parameters.

### 5.3. File `NativeCounter.c`

```c
#include "NativeCounter.h"

#include <stdint.h>
#include <stdlib.h>

#ifndef INTPTR_MAX
#  error "JNI handle example requires intptr_t"
#endif

_Static_assert(sizeof(intptr_t) <= sizeof(jlong),
               "Native pointer does not fit in jlong");

struct NativeState {
    jint value;
};

static jlong encode_state(struct NativeState *state) {
    return (jlong)(intptr_t)(void *)state;
}

static struct NativeState *decode_state(jlong handle) {
    return (struct NativeState *)(void *)(intptr_t)handle;
}

/*
 * Handles only the closed/null sentinel.
 * A forged nonzero handle CANNOT be validated by this test.
 */
static struct NativeState *require_state(JNIEnv *env, jlong handle) {
    if (handle == 0) {
        jclass exceptionClass =
            (*env)->FindClass(env, "java/lang/IllegalStateException");
        if (exceptionClass != NULL) {
            (*env)->ThrowNew(
                env, exceptionClass, "Native handle is closed");
        }
        return NULL;
    }
    return decode_state(handle);
}

JNIEXPORT jlong JNICALL
Java_NativeCounter_nativeCreate(JNIEnv *env,
                                jclass clazz,
                                jint initial) {
    (void)env;
    (void)clazz;

    struct NativeState *state = malloc(sizeof *state);
    if (state == NULL) {
        return (jlong)0;
    }

    state->value = initial;
    return encode_state(state);
}

JNIEXPORT jint JNICALL
Java_NativeCounter_nativeGet(JNIEnv *env,
                             jclass clazz,
                             jlong handle) {
    (void)clazz;
    struct NativeState *state = require_state(env, handle);
    if (state == NULL) {
        return (jint)0; // JNI exception is pending.
    }
    return state->value;
}

JNIEXPORT void JNICALL
Java_NativeCounter_nativeSet(JNIEnv *env,
                             jclass clazz,
                             jlong handle,
                             jint value) {
    (void)clazz;
    struct NativeState *state = require_state(env, handle);
    if (state == NULL) {
        return;
    }
    state->value = value;
}

JNIEXPORT void JNICALL
Java_NativeCounter_nativeDestroy(JNIEnv *env,
                                 jclass clazz,
                                 jlong handle) {
    (void)env;
    (void)clazz;

    if (handle != 0) {
        struct NativeState *state = decode_state(handle);
        free(state);
    }
}
```

Ownership explanation for the C code:

1. `malloc()` creates `struct NativeState` on the native heap; it is **not** on the Java heap and is not a JNI `jobject`.
2. `encode_state()` converts the pointer value through `intptr_t` then to `jlong` for Java to store temporarily. **No extra memory is allocated** during the encode step.
3. `get/set` decode the handle and operate on the **already allocated and still living** struct. Checking `handle == 0` only detects the sentinel; **it cannot verify that a nonzero handle actually points to valid memory**.
4. `nativeDestroy()` calls `free()` on the same C side that called `malloc()`. After freeing, any old copy of the handle is a **dangling handle**, even though its numeric value remains the same.
5. Native code does not retain the pointer across async calls or return it to a second wrapper object. That condition together with `synchronized` in Java gives the example a clear lifetime when operations only go through the defined wrapper.

In C, `jint` is signed 32-bit per JNI. Storing a Java `int` value directly into a `jint` field is unrelated to pointer mapping. `JNIEnv *` is the JNI interface pointer used in the thread calling the native method; do not save `env` to use from another thread.

### 5.4. Building the shared library and running

Place `NativeCounter.java` and `NativeCounter.c` in the same directory. On Linux, set `JAVA_HOME` to point to the actual JDK directory being used, then:

```bash
javac -h . NativeCounter.java
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -shared NativeCounter.c -o libnativecounter.so
java -Djava.library.path=. NativeCounter
```

**Exact stdout** on the success path:

```text
before=41
after=42
closed
```

If Java reports `UnsatisfiedLinkError`, check the library name, native path, JDK architecture (32/64-bit), JNI headers, and symbol names. `System.loadLibrary("nativecounter")` corresponds to `libnativecounter.so` on Linux, `nativecounter.dll` on Windows, and the corresponding platform library name on macOS. The example build command is for **Linux**; you cannot copy the `linux` include path and `-fPIC` flag verbatim to MSVC/Windows.

On JDK versions with policies restricting native access, loading or calling JNI may require appropriate configuration to allow native access, such as `--enable-native-access=ALL-UNNAMED` for classpath applications; consult the documentation for the JDK version being run. On standard JDK 17, the run command above is sufficient to demonstrate basic JNI.

## 6. Visualizing the data flow and lifetime

```text
Java NativeCounter(41)
    |
    | nativeCreate(41)        Java int -> JNI jint
    v
C malloc(sizeof NativeState)
    |
    | NativeState *p
    | encode: p -> void* -> intptr_t -> jlong
    v
Java handle : long           (holds only a number, does not keep the allocation alive)
    |
    | nativeGet(handle)       Java long -> JNI jlong
    v
C decode: jlong -> intptr_t -> void* -> NativeState*
    |
    | dereference while the object is alive
    v
C state->value : jint = 41
    |
    v
Java int = 41
    |
    | close() -> nativeDestroy(handle)
    v
C free(p)
    |
    v
Java handle = 0              (old handle is no longer valid)
```

Two important distinctions:

- **Pointer value ≠ memory region:** copying a pointer or encoding it into `jlong` does not copy the pointed-to data and does not create a second ownership.
- **Holding a number ≠ keeping an object alive:** Java can keep `handle` forever, but if C has already called `free(p)`, decoding it does not bring the memory back. The pointer may collide in address with a new allocation (ABA trap).

Because Java `long` is a signed number, **only compare `handle != 0L`** when the contract uses 0 as the sentinel; do not check `handle > 0L`. An address encoded into a negative signed value can still be a valid issued handle on platforms that allow such encoding.

The example also assumes that native methods only perform synchronous work and finish before returning to Java. If a C library spawns its own worker thread, queues a pointer, and processes it later, Java calling `close()` right after the native call can free it prematurely. In that case, reference counting, synchronization mechanisms, or ownership transfer rules must be added according to the library's contract.

## 7. When is pointer-as-`jlong` not safe enough?

The sample wrapper clarifies the conversion concepts, but **cannot validate an arbitrary handle**. Suppose a public native entry point receives a `long` from JSON or untrusted Java code:

```java
// Dangerous illustration: number chosen by caller, not issued by native.
long forgedHandle = 0x1234L;
```

If C treats it as `NativeState *` and dereferences it, the result can be a segmentation fault or memory corruption. `handle != 0` offers no protection at all against forged values, stale handles, or type-confused pointers. `synchronized` only prevents races between methods on **the same wrapper**, not against a handle copied to another object or thread.

For APIs that must accept handles from multiple clients/modules or where misuse is possible, use an **opaque ID registry**:

1. Native code creates the resource and stores the actual pointer in a table under a mutex (or concurrent-safe structure).
2. Returns an ID/token number in a library-owned format, possibly including index + generation to prevent reuse of old IDs.
3. Each operation looks up the table, checking that the ID is still valid, resource type, ownership, and closed state **before** touching the pointer.
4. The destructor removes the registry entry and releases the resource once; concurrent operations must hold an appropriate lease/refcount or lock so the pointer is not freed while in use.
5. Do not treat a predictable token as proof of authorization: for sensitive data, independent access control is still required.

In that design, `jlong` is an **ID**, with no need to cast it to a C pointer in the JNI entry point at all. A registry adds overhead and synchronization design, in exchange for detecting invalid/stale handles and centralizing lifetime management. Depending on the problem, a Java wrapper object, direct `ByteBuffer`, or FFM `MemorySegment` can be used instead of exposing an integer handle.

### 7.1. Choosing an API by need

| Need | Suitable design | Notes |
| --- | --- | --- |
| Private native object, wrapper controls lifetime, single-process internal use | `jlong` holding encoded pointer + `AutoCloseable` | Only accept handles issued by the library; release exactly once |
| Callers may pass forged or stale IDs, multiple threads/owners | `jlong` holding **opaque ID**, looked up via registry | Validate + generation + synchronization before dereferencing |
| Working with byte buffers readable/writable from Java | JNI direct `ByteBuffer` or array copy | Do not let the buffer access memory already freed by C |
| Need native memory lifetime and bounds modeled in modern Java | FFM `MemorySegment` / `Arena` (JDK 22+) | Follow FFM's scope and API, still must manage C-side allocations by proper owner |
| Only need a 64-bit integer from C | `jlong` as a **number**, do not convert to pointer | Avoid “pointerizing” a data value |

With `NewDirectByteBuffer(env, nativeAddress, capacity)`, JNI can create a Java direct buffer viewing the provided address. This call **does not automatically transfer ownership of the C allocation to the JVM**; the library side must ensure the memory remains alive until the buffer is no longer accessed. `GetDirectBufferAddress` can return a pointer to the direct buffer's native memory (or `NULL` under conditions specified by JNI). Do not retain the pointer when the lifetime of the buffer or native allocation has not been established.

FFM `MemorySegment` does not mean “every address is safe”; a raw native pointer still needs a contract on size, access permissions, alignment, and lifetime. A `long` returned from `MemorySegment.address()` (when supported by the API) is also just a numeric address, and does not automatically carry the segment's bounds checks.

## 8. How do `jobject`, `jmethodID`, and pointers returned by JNI differ?

Typedef names in `jni.h` can easily cause confusion when reading C code. They should be categorized:

**1. `jobject`, `jclass`, `jstring`, `jarray`.** These are JNI references to objects on the Java heap; the objects are managed by the JVM and may be moved by the GC. Do not take the numeric value of a JNI reference as the address of a Java object, and do not store it as a `jlong` for later use. Local references have a lifetime tied to the call/thread; to keep a Java object across multiple calls, use `NewGlobalRef`, then `DeleteGlobalRef` at the right time. A global reference is a mechanism to keep a **Java object** alive, not C native `malloc`.

**2. `jfieldID` and `jmethodID`.** These are opaque IDs used to access fields/methods via JNI. They are not regular Java object references; their lifetime is tied to the class containing the field/method. Do not use them as pointers to application structs, and do not serialize them into arbitrary longs.

**3. `GetByteArrayElements`, `GetStringUTFChars`, `GetPrimitiveArrayCritical`.** JNI can give native code a pointer to Java object contents or a copy buffer. The caller must follow the corresponding `Release...` pair. This pointer does not implicitly belong to C's `free()` and cannot be held indefinitely. The critical API also has specific restrictions on what JNI operations can be performed inside a critical region.

**4. C pointers created from `malloc()`.** These are actual native allocations; the JVM does not know about them just because Java stores the address as a `jlong`. Ownership must be managed separately by the Java/C contract.

**5. `JNIEnv *`.** This is the JNI interface pointer for **the calling thread**. Do not save and reuse the same `JNIEnv *` from another native thread; a separate native thread must attach to the JVM according to JNI rules and obtain its own thread's interface pointer.

## 9. Common mistakes and fixes

| Problematic code/pattern | Why it is wrong | Fix |
| --- | --- | --- |
| `jlong h = (long)ptr;` | C `long` can be only 32 bits on Win64 | Use `intptr_t` then `jlong` with ABI check |
| `jint h = (jint)(intptr_t)ptr;` | 32 bits can truncate a 64-bit address | Do not use `jint` to hold a 64-bit address |
| `void *p = (void *)(intptr_t)userLong;` with arbitrary number | No guarantee the pointer is valid | Only decode issued handles or use a registry |
| `if (h > 0) ...` | Encoded pointer can have a negative `jlong` | Use the exact sentinel per the contract |
| `free(pointer)` after already freeing once | Double free, heap corruption | Single owner; idempotent `close()`; clear ownership |
| Using `h` after `close()` | Use-after-free; `h` is still a valid number | Invalidate handle and guard every operation |
| Storing `jobject` cast to `jlong` | GC reference is not a stable C pointer | `NewGlobalRef/DeleteGlobalRef` if the object must be kept |
| Keeping `GetStringUTFChars` pointer without releasing | Leak/pin/copy held too long | Use the matching `ReleaseStringUTFChars` pair |
| Using `sizeof(void*) == 8` to claim all ABIs are identical | Ignores alignment, pointer representation, special ABIs | Check the actual platform and design the contract |
| Saving pointer handle to a database and reusing after restart | Process address space changes; ASLR, different lifetime | Use persistent IDs, not runtime addresses |
| Two wrappers both own one pointer and both close | Double free | Single ownership or reference counting/registry |
| Closing native resource while native thread still uses it | Data race/use-after-free | Lease/lock/refcount and explicit synchronization |
| Confusing `Java long` with C `long` in prototypes | Size mismatch on LLP64 | C native methods use `jlong` from `jni.h` |
| Hand-writing JNI symbols in code after changing package/overload | JVM cannot resolve the function | Re-run `javac -h`; include the generated header |

From a security standpoint, a memory address is not an unforgeable credential or capability. Logging addresses arbitrarily can leak address space layout information (ASLR). In public APIs, only issue managed opaque tokens, and enforce access control when needed.

## 10. Testing the Java/C boundary

For the `NativeCounter` example, test across the following groups:

1. **Success path:** create `41` → get `41` → set `42` → get `42` → close; exact stdout as shown.
2. **After closing:** `get()/set()` must throw `IllegalStateException` in Java before calling native; a second `close()` is a no-op.
3. **Threads on the same wrapper:** multiple Java threads calling `get/set/close` must be serialized via `synchronized`; if the application lets native code retain the pointer across calls, additional synchronization is needed.
4. **Allocation failure:** trigger `malloc` failure via fault injection or a mock allocator to confirm `nativeCreate` returns `0` and the Java constructor throws `OutOfMemoryError`. Do not test by allocating an infinite size.
5. **32-bit/64-bit:** build on the actual supported ABIs; check `sizeof(jlong)`, `sizeof(intptr_t)`, `sizeof(void*)` in C, and test encode → decode on a live object.
6. **Heap management:** run AddressSanitizer/LeakSanitizer when the toolchain permits; verify there are no leaks, double frees, or use-after-frees on exit paths.
7. **Invalid handle:** do not try to dereference `12345L` just to “test”; with a registry, invalid/stale IDs can be tested without touching an invalid pointer.
8. **Library compatibility:** check `UnsatisfiedLinkError`, native export names, correct JDK headers, matching architecture and compiler ABI between JVM and native library.

A useful C check for CI on the target platform is:

```c
#include <jni.h>
#include <stdint.h>
#include <stdio.h>

int main(void) {
#ifdef INTPTR_MAX
    printf("jlong_bytes=%zu\n", sizeof(jlong));
    printf("void_ptr_bytes=%zu\n", sizeof(void *));
    printf("intptr_bytes=%zu\n", sizeof(intptr_t));
#else
    puts("intptr_t unavailable");
#endif
    return 0;
}
```

This is a **standalone** program; it needs JNI headers included with `-I` flags similar to the native build command above. On common Linux x64, expected stdout:

```text
jlong_bytes=8
void_ptr_bytes=8
intptr_bytes=8
```

Measuring sizes alone does not test the entire contract. Whether the pointer is still alive, which allocation it belongs to, and how it can be freed must still be verified through design/lifetime.

## 11. Rules to remember when designing JNI

- **Numeric type:** `Java long` ↔ `JNI jlong` ↔ signed 64-bit. It is just data.
- **Address type:** `void *`/`T *` describes a C pointer, with a specific ABI and lifetime. Do not infer a pointer from the type name `long`.
- **Conditional conversion:** `pointer → intptr_t → jlong → intptr_t → pointer` for object pointers when supported by the implementation and while the value is within the same lifetime/process. Do not generalize to function pointers or pointers >64 bits.
- **Address space and GC:** C allocations and Java objects are two different management mechanisms. `jobject` is an opaque JNI reference, not a direct address of a Java object.
- **Ownership:** a `jlong` number does not keep a C allocation alive; the caller must close the right resource, with the right destructor, at the right time.
- **Public APIs:** if a native resource must be validated, closed, and shared across multiple parties, use an opaque ID registry instead of raw pointers.

References: [JNI Types and Data Structures (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html), [JNI Design Overview, native signatures and lifetime references](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html), [C pointer conversions](https://en.cppreference.com/w/c/language/conversion), [`javac -h` native headers](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
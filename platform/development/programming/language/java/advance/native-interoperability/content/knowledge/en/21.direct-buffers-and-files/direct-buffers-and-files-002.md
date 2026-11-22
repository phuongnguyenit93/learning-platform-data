# Sharing Buffers via NewDirectByteBuffer and GetDirectBufferAddress in JNI

## 1. The Problem: Java and Native Code Working Together on One Byte Region

When Java communicates with C/C++ via JNI, transferring data using `byte[]` sometimes incurs one or more copies. For large data such as video frames, network packets, audio, encrypted data, or block I/O, you may need to let **Java and native operate directly on the same storage region**.

A standard solution in JNI is to use a `java.nio` **direct buffer**:

- **`NewDirectByteBuffer(JNIEnv*, void*, jlong)`**: from an **existing native memory address**, creates a Java direct `ByteBuffer` referencing that region.
- **`GetDirectBufferAddress(JNIEnv*, jobject)`**: from a Java **direct buffer**, retrieves the address of the memory region that the buffer represents for C/C++ to read/write.
- **`GetDirectBufferCapacity(JNIEnv*, jobject)`**: retrieves the capacity of the buffer region in **number of elements**. For `ByteBuffer`, each element is one byte, so the capacity is the **number of bytes**.

This is a mechanism for sharing **backing memory** rather than copying data every time it crosses the JNI boundary. If Java modifies a byte, native can read that exact modified byte; if native writes a new byte, Java can see it through the same buffer. However, **sharing a memory region does not mean it is automatically safe with respect to lifetime, threads, or synchronization**.

> Two common directions:
>
> **Native allocates → Java uses**: `malloc`/native allocator → `NewDirectByteBuffer` → Java `ByteBuffer` → native owner proactively frees it once everyone has stopped using it.
>
> **Java allocates → Native uses**: `ByteBuffer.allocateDirect(...)` → pass buffer through native method → `GetDirectBufferAddress` → C/C++ reads/writes during the period Java guarantees the buffer is still alive.

This lesson belongs to the **Direct Buffers and Files** group of the *Java Advance - native-interoperability* module. The examples use **JNI and Java 17 or later**, and do not require the FFM API or `--enable-native-access` from JDK 22. You only need a JDK with the `jni.h` header, a compatible native compiler, and a JVM that supports JNI direct-buffer access.

## 2. Three Core APIs and the JNI Contract

### 2.1. `NewDirectByteBuffer`

C signature:

```c
jobject NewDirectByteBuffer(
        JNIEnv *env, void *address, jlong capacity);
```

In C, calling via `JNIEnv`:

```c
jobject view =
    (*env)->NewDirectByteBuffer(env, address, (jlong)capacity);
```

In C++ with `jni.h`:

```cpp
jobject view = env->NewDirectByteBuffer(address, capacity);
```

The snippets above are **illustrative**, requiring a valid `JNIEnv*` on the current thread and a live `address` memory region. The function creates a direct Java `java.nio.ByteBuffer` pointing to the exact `address` region of length `capacity` **bytes**, without copying those bytes to a separate backing array.

Important conditions:

- `address` must be **non-NULL** and point to a real, valid memory region for as long as Java may access the buffer.
- `capacity` is the number of bytes in the provided region. For good practical compatibility, this lesson uses a **positive capacity** that does not exceed `Integer.MAX_VALUE`; `ByteBuffer.capacity()` in Java is `int`. Do not pass a negative number or a size larger than the Java buffer limit.
- The function returns a `jobject` local reference to the `ByteBuffer`; when returned to Java, the result becomes a regular Java reference.
- If the object cannot be created or the JVM does not support JNI direct-buffer access, the result may be `NULL`; if there is a pending Java exception, it must be preserved or handled appropriately.
- **NewDirectByteBuffer does not allocate backing memory and has no obligation to call `free(address)`.** The native owner itself must decide when it can be freed. This is the most common source of use-after-free bugs.
- The initial byte order of a buffer created by JNI is **`BIG_ENDIAN`** according to the specification, not automatically the native CPU byte order.

**Dangerous example:**

```c
JNIEXPORT jobject JNICALL Java_Example_bad(
        JNIEnv *env, jclass ignored) {
    unsigned char stackData[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    return (*env)->NewDirectByteBuffer(
            env, stackData, (jlong)sizeof(stackData));
}
```

This is **intentionally wrong code**. `stackData` reaches the end of its lifetime after the function returns; the Java `ByteBuffer` still exists, but its backing pointer is dangling. Reading from Java can return garbage data, cause a crash, or other errors. Do not use this pattern.

### 2.2. `GetDirectBufferAddress`

C signature:

```c
void* GetDirectBufferAddress(JNIEnv *env, jobject buffer);
```

When Java passes a `ByteBuffer.allocateDirect(...)` or a buffer created with `NewDirectByteBuffer` into JNI, native gets the start address of the buffer region:

```c
void *base = (*env)->GetDirectBufferAddress(env, buffer);
```

- `base` points to the **start position of the region represented by the buffer object itself**, and does not automatically shift by `position()`.
- For a `ByteBuffer.slice()`, the slice's region starts at the offset that the slice represents, so the `base` of the slice may differ from the `base` of the original buffer.
- Do not use the address if the result is `NULL`. The cause may be that the buffer is not direct, the region is undefined, or the JVM does not support JNI direct-buffer access.
- JNI `GetDirectBufferAddress` does not create a snapshot, does not pin a Java heap array, and does not allocate new native memory.
- This JNI function accepts a `jobject` representing a **direct `java.nio.Buffer`**, not only `ByteBuffer`; however, the interpretation of size/stride differs for typed view buffers such as `IntBuffer`. The complete runnable example in this lesson only accepts **ByteBuffer** for easy byte-by-byte verification.

### 2.3. `GetDirectBufferCapacity`

C signature:

```c
jlong GetDirectBufferCapacity(JNIEnv *env, jobject buffer);
```

In C:

```c
jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);
```

- Returns `-1` when the object is not a direct buffer, when the platform does not support the corresponding access, or in some cases when a typed view buffer is misaligned on a CPU that does not support unaligned access.
- Returns the **number of elements that can be held**. For `ByteBuffer`, 1 element = 1 byte; for `IntBuffer`, 1 element = 1 `int`, **not** 1 byte.
- **`capacity` is not `limit`, `position`, or `remaining`**. Native must have its own convention if it is only allowed to operate on the `position..limit` region.
- `jlong` needs to be checked before converting to `size_t` or a smaller numeric type in C, to avoid overflow/signedness issues.

A check pattern for `ByteBuffer`:

```c
if (buffer == NULL) {
    // Report NullPointerException in Java.
    return;
}

void *base = (*env)->GetDirectBufferAddress(env, buffer);
jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);

if (base == NULL || capacity < 0) {
    // Do not use base; a Java exception can be thrown here.
    return;
}
```

This is a **snippet**, not a standalone C function. The complete example in section 6 will throw a Java exception properly instead of returning silently.

### 2.4. Not Every JVM Is Required to Support JNI Direct-Buffer Access

The JNI Specification requires the JVM to provide these three entry points, but allows an implementation **not to support direct buffer access from JNI**. When unsupported:

- `NewDirectByteBuffer` and `GetDirectBufferAddress` return `NULL`.
- `GetDirectBufferCapacity` returns `-1`.

Common HotSpot JVMs support this well, but portable code must handle the error path instead of calling `memcpy` with `NULL` or returning a null `ByteBuffer` and treating it as a success. If the environment needs to support other JVMs, test the feature or implement a fallback based on `byte[]`.

## 3. Comparing Direct Buffer, Heap Buffer, and Byte Array

| Characteristic | `ByteBuffer.allocateDirect(n)` | `ByteBuffer.allocate(n)` | `ByteBuffer.wrap(byte[])` | `NewDirectByteBuffer(nativePtr,n)` |
| --- | --- | --- | --- | --- |
| `isDirect()` | `true` | `false` | `false` | `true` if creation succeeds |
| Backing storage | Usually in native/off-heap memory, managed by JVM | Java heap array | Java heap array provided by caller | Native memory provided by **caller** |
| `GetDirectBufferAddress` | Can retrieve address if JVM supports it | `NULL` | `NULL` | Can retrieve the same original address if JVM supports it |
| Copies on creation? | Allocates new region, does not copy from `byte[]` | Allocates new array | Does not copy source array, but is heap-backed | Does not copy native backing |
| Who frees backing? | JVM/cleaner according to buffer's mechanism | Java heap GC | Java heap GC | **Native owner of the address** |
| Use `ByteBuffer.array()`? | Should not assume a backing array exists | Yes | Yes | Should not assume a backing array exists |
| Points to note | Keep Java buffer reachable while native holds pointer | Not direct; JNI needs copy/another approach | `wrap` does not make the array off-heap | Java reference still existing **does not guarantee** native backing has not been `free`d |

**`ByteBuffer.wrap(array)` is not "zero-copy JNI direct access".** It shares a Java heap array, but C cannot use `GetDirectBufferAddress` to get a pointer to that array. If you need JNI with a heap array, use `GetByteArrayRegion`/`SetByteArrayRegion` or `GetByteArrayElements`/`ReleaseByteArrayElements` with the appropriate pin/copy contract.

Direct buffers help avoid **some data copies across the JNI boundary**, but there is still JNI transition overhead, Java API bounds checks, and the cost of allocating/freeing native memory. They are not automatically faster than heap arrays for every small workload.

## 4. Java → Native Path: `allocateDirect` and `GetDirectBufferAddress`

A Java method can allocate a direct buffer itself:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(4);

buffer.put(0, (byte)3);
buffer.put(1, (byte)4);
buffer.put(2, (byte)5);
buffer.put(3, (byte)6);

int total = nativeSum(buffer, 0, 4);
```

This is a snippet inside a class with the corresponding `nativeSum` native method. Native code:

1. Receives `jobject buffer`.
2. Gets the pointer via `GetDirectBufferAddress`.
3. Gets the capacity via `GetDirectBufferCapacity`.
4. Checks `offset`, `length` against capacity.
5. Reads `uint8_t` from address `base + offset`, returns the sum.

For the Java array `{3,4,5,6}`, the result is `3+4+5+6 = 18`. Java and native are reading the same backing of the direct buffer; `GetByteArrayElements` is not needed.

### 4.1. Native Modifies Bytes and Java Sees It Immediately

If C uses `memset(base+1, 8, 2)`, after the JNI method returns, Java reading the bytes will see:

```text
[3, 8, 8, 6]
```

It is still the **same backing region**, not JNI creating a `byte[]` with the result and copying it back.

### 4.2. The Address Is Only Safe While the Backing Is Alive

A direct buffer allocated by Java usually has its backing memory managed by the JVM. If native **only uses the pointer synchronously within a single JNI call**, the `jobject buffer` object is being passed as an argument and the JVM guarantees the reference is valid for the call; this is an easy model to control.

If native **stores the pointer for use after the JNI call returns**, an additional ownership protocol is needed:

- Hold a **strong global reference** to the direct buffer (`NewGlobalRef`) so it is not considered unreachable by GC just because Java drops its reference.
- When the native worker stops using the pointer, delete the global ref (`DeleteGlobalRef`).
- Synchronize the time the owner is destroyed and the time native stops accessing it; **a global ref prevents collection of the Java object, it does not prevent another owner from `free`ing external memory**.

Do not simply cache `void*` and let Java `ByteBuffer.allocateDirect` lose all strong references; the cleaner/GC may free the memory region.

## 5. Native → Java Path: `malloc` and `NewDirectByteBuffer`

For a memory region allocated by C:

```c
uint8_t *data = (uint8_t *)malloc(8);
if (data == NULL) {
    // Handle OutOfMemoryError.
    return NULL;
}

for (int i = 0; i < 8; ++i) {
    data[i] = (uint8_t)(10 + i);
}

jobject view = (*env)->NewDirectByteBuffer(
        env, data, (jlong)8);

if (view == NULL) {
    free(data);  // Do not leak memory if view creation fails.
    // Preserve pending exception if JVM threw one.
}
return view;
```

This is an illustrative **snippet**, inside a JNI function with a valid `env`. After returning `view` to Java, accesses `view.get(0)` and `view.put(0,...)` operate directly on `data` allocated by `malloc`.

**Important:** when `view` goes out of Java scope, **there is no guarantee that `NewDirectByteBuffer` will automatically call `free(data)`**. The memory belongs to the C owner, so there must be a release protocol such as `nativeRelease(buffer)`, a native handle with `close()`, or a dedicated callback/native allocator with lifecycle management.

### 5.1. Why Does the Example Need `AutoCloseable`?

For learning purposes, a Java wrapper `NativeOwner implements AutoCloseable` allows:

```java
try (NativeOwner owner = new NativeOwner(8)) {
    ByteBuffer bytes = owner.buffer();
    // Only use bytes within this scope.
}
// close() requests native to free the backing region.
```

However, a simple wrapper **cannot automatically invalidate** every `ByteBuffer.duplicate()`, `slice()`, or reference held externally. If Java keeps a view after `close()`, the view is still a Java object, but the native pointer is dangling: **subsequent reads are use-after-free**. Production code must control view escaping, outstanding operations, and concurrency; one can choose a design that only grants access via a short-lived callback rather than returning a raw buffer to arbitrary code.

### 5.2. Do Not Use Stack Memory to Create a Long-Lived Direct Buffer

Some C callbacks have local stack arrays, for example `char tmp[4096]`. You may only create a direct buffer on this region if Java completes all accesses **before the stack frame ends**, such as a synchronous callback with a strict contract. Do not return a `NewDirectByteBuffer` pointing to a stack array from a native method for Java to use after the method returns.

Similarly, do not create a long-lived view pointing to an unmapped memory-mapped file, a freed library pointer, or data belonging to an arena that will be closed.

## 6. Runnable Example: Bidirectional Buffer Sharing with Java 17 + C

The program below executes two data flows in **a single Java process**:

- **Native → Java**: `malloc` 8 bytes, fill `10..17`, return direct buffer via `NewDirectByteBuffer`. Java modifies bytes, C computes sum and fills a range; Java sees the changes. A `slice` is passed back to JNI, showing that address and capacity are relative to the slice.
- **Java → Native**: `ByteBuffer.allocateDirect(4)`, write `3,4,5,6`, C computes sum, writes back two bytes, Java reads the result. The heap-backed `ByteBuffer.wrap` case is explicitly rejected.

The example chooses **positive capacity** and **small lengths**, controlling `free` with `AutoCloseable`. This is a standalone demo independent of FFM and runs on **Java 17+** with a C compiler. It assumes the JVM has JNI direct-buffer support; the code handles the unsupported case with an exception.

### 6.1. Java File: `DirectBufferBridge.java`

```java
import java.nio.ByteBuffer;
import java.util.Arrays;

public final class DirectBufferBridge {
    static {
        System.loadLibrary("directbufferbridge");
    }

    // Native allocates capacity bytes then uses NewDirectByteBuffer.
    private static native ByteBuffer nativeAllocate(int capacity);

    // Only NativeOwner calls this method ONCE
    // on the original buffer returned from nativeAllocate.
    private static native void nativeRelease(ByteBuffer original);

    // Checks direct, offset/length then reads the same backing.
    private static native int nativeSum(
            ByteBuffer buffer, int offset, int length);

    // Writes a byte pattern 0..255 into a buffer range.
    private static native void nativeFill(
            ByteBuffer buffer, int offset, int length,
            int unsignedValue);

    private DirectBufferBridge() {
    }

    // Wrapper describing ownership, prevents use after close
    // through the wrapper's buffer() API.
    private static final class NativeOwner implements AutoCloseable {
        private ByteBuffer original;

        NativeOwner(int capacity) {
            original = nativeAllocate(capacity);
            if (original == null) {
                throw new IllegalStateException(
                        "JNI direct buffer unavailable");
            }
        }

        ByteBuffer buffer() {
            if (original == null) {
                throw new IllegalStateException("Native memory closed");
            }
            return original;
        }

        @Override
        public void close() {
            if (original != null) {
                nativeRelease(original);
                original = null;
            }
        }
    }

    // Creates a Java snapshot of the full capacity.
    // duplicate + clear only modifies position/limit of the secondary view.
    private static int[] snapshot(ByteBuffer buffer) {
        ByteBuffer view = buffer.duplicate();
        view.clear();

        int[] result = new int[view.remaining()];
        for (int i = 0; i < result.length; i++) {
            result[i] = Byte.toUnsignedInt(view.get());
        }
        return result;
    }

    public static void main(String[] args) {
        // Direction 1: C malloc -> NewDirectByteBuffer -> Java.
        try (NativeOwner owner = new NativeOwner(8)) {
            ByteBuffer data = owner.buffer();

            System.out.println("native-backed direct="
                    + data.isDirect());
            System.out.println("native-backed initial="
                    + Arrays.toString(snapshot(data)));
            System.out.println("native-backed order="
                    + data.order());

            // Java writes to the same native memory.
            data.put(0, (byte) 42);
            System.out.println("sum after Java write="
                    + nativeSum(data, 0, data.capacity()));

            // Native writes 7 into byte offsets [2,5).
            nativeFill(data, 2, 3, 7);
            System.out.println("after native fill="
                    + Arrays.toString(snapshot(data)));

            // Slice represents original region [2,5).
            ByteBuffer cursor = data.duplicate();
            cursor.position(2);
            cursor.limit(5);
            ByteBuffer slice = cursor.slice();

            // Native sees the slice's own base address/capacity.
            nativeFill(slice, 0, slice.capacity(), 9);
            System.out.println("after slice fill="
                    + Arrays.toString(snapshot(data)));
            System.out.println("slice sum="
                    + nativeSum(slice, 0, slice.capacity()));

            // position/limit is ByteBuffer state,
            // JNI nativeSum here intentionally checks against capacity.
            data.position(1);
            data.limit(7);
            System.out.println("full-capacity sum="
                    + nativeSum(data, 0, 8));
            System.out.println("position=" + data.position()
                    + ", limit=" + data.limit());
        }
        // All views up to here must not be accessed anymore:
        // nativeRelease has freed their backing memory.

        // Direction 2: Java allocateDirect -> C reads/writes.
        ByteBuffer javaAllocated = ByteBuffer.allocateDirect(4);
        javaAllocated.put(new byte[]{3, 4, 5, 6});
        javaAllocated.flip();

        System.out.println("java-allocated direct="
                + javaAllocated.isDirect());
        System.out.println("java-allocated sum="
                + nativeSum(javaAllocated, 0,
                        javaAllocated.remaining()));

        nativeFill(javaAllocated, 1, 2, 8);
        System.out.println("java-allocated after native fill="
                + Arrays.toString(snapshot(javaAllocated)));

        // ByteBuffer.wrap is heap-backed, not direct.
        try {
            nativeSum(ByteBuffer.wrap(new byte[]{1, 2}), 0, 2);
            System.out.println("heap buffer rejected=false");
        } catch (IllegalArgumentException expected) {
            System.out.println("heap buffer rejected=true");
        }
    }
}
```

**Important note about the demo:** `NativeOwner.buffer()` returns a raw view to code **inside** `try`. This wrapper prevents calling `buffer()` after `close`, but cannot stop a user from intentionally keeping `data` or `slice` and accessing it after `close`. That is the API usage responsibility in the example, not an automatic Java feature against stale pointers.

### 6.2. C File: `DirectBufferBridge.c`

```c
#include <jni.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

// JNI helper: attempts to throw a Java exception by class name.
static void throw_java(JNIEnv *env,
                       const char *class_name,
                       const char *message) {
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

// Only accepts direct ByteBuffer with valid address/capacity.
// offset and length are measured in BYTES.
// Does not automatically use ByteBuffer's position()/limit().
static int valid_range(JNIEnv *env,
                       jobject buffer,
                       jint offset,
                       jint length,
                       uint8_t **range_start) {
    if (buffer == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "buffer is null");
        return 0;
    }

    void *base = (*env)->GetDirectBufferAddress(env, buffer);
    jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);

    if (base == NULL || capacity < 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "direct ByteBuffer access unavailable");
        return 0;
    }

    // Use jlong to avoid overflow of offset + length.
    if (offset < 0 || length < 0
            || (jlong)offset > capacity
            || (jlong)length > capacity - (jlong)offset) {
        throw_java(env, "java/lang/IndexOutOfBoundsException",
                   "invalid buffer range");
        return 0;
    }

    *range_start = (uint8_t *)base + offset;
    return 1;
}

// Java: private static native ByteBuffer nativeAllocate(int);
JNIEXPORT jobject JNICALL
Java_DirectBufferBridge_nativeAllocate(
        JNIEnv *env, jclass ignored, jint capacity) {
    (void)ignored;

    if (capacity <= 0) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "capacity must be positive");
        return NULL;
    }

    uint8_t *data = (uint8_t *)malloc((size_t)capacity);
    if (data == NULL) {
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native malloc failed");
        return NULL;
    }

    for (jint i = 0; i < capacity; ++i) {
        data[i] = (uint8_t)(10 + (i % 40));
    }

    jobject view = (*env)->NewDirectByteBuffer(
            env, data, (jlong)capacity);

    if (view == NULL) {
        // No Java owner to release if creation fails.
        free(data);
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/IllegalStateException",
                       "JVM direct-buffer access unsupported");
        }
    }
    return view;
}

// Java: private static native void nativeRelease(ByteBuffer);
// ONLY the owner wrapper calls with the ORIGINAL view from nativeAllocate.
JNIEXPORT void JNICALL
Java_DirectBufferBridge_nativeRelease(
        JNIEnv *env, jclass ignored, jobject original) {
    (void)ignored;

    uint8_t *base = NULL;
    if (!valid_range(env, original, 0, 0, &base)) {
        return;
    }

    // This region was allocated by nativeAllocate malloc.
    // Caller must ensure no one else is accessing view/slice.
    free(base);
}

// Java: private static native int nativeSum(ByteBuffer,int,int);
JNIEXPORT jint JNICALL
Java_DirectBufferBridge_nativeSum(
        JNIEnv *env, jclass ignored, jobject buffer,
        jint offset, jint length) {
    (void)ignored;

    uint8_t *data = NULL;
    if (!valid_range(env, buffer, offset, length, &data)) {
        return 0; // JVM throws exception so Java does not use the 0 value.
    }

    jlong total = 0;
    for (jint i = 0; i < length; ++i) {
        total += data[i];
    }
    if (total > 2147483647LL) {
        throw_java(env, "java/lang/ArithmeticException",
                   "sum does not fit Java int");
        return 0;
    }
    return (jint)total;
}

// Java: private static native void nativeFill(ByteBuffer,int,int,int);
JNIEXPORT void JNICALL
Java_DirectBufferBridge_nativeFill(
        JNIEnv *env, jclass ignored, jobject buffer,
        jint offset, jint length, jint unsigned_value) {
    (void)ignored;

    if (unsigned_value < 0 || unsigned_value > 255) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "unsignedValue must be 0..255");
        return;
    }

    uint8_t *data = NULL;
    if (!valid_range(env, buffer, offset, length, &data)) {
        return;
    }

    memset(data, unsigned_value, (size_t)length);
}
```

**Why is the C code written this way?**

1. Every JNI native function receives `JNIEnv*` and a `jclass` argument because the Java methods are `static native`.
2. `nativeAllocate` calls `malloc` itself, initializes the backing, calls `NewDirectByteBuffer`, and **frees immediately on the failure path**.
3. `valid_range` checks `NULL`, direct access capability, offset, and length within **capacity**, using the form `length > capacity - offset` to avoid addition overflow.
4. `nativeSum` reads `uint8_t` so values 128..255 are treated as unsigned; accumulates the sum in `jlong` and then verifies it fits in `jint`.
5. `nativeFill` only accepts values 0..255 and uses `memset` to modify the backing. `memset` itself does not automatically apply `ByteBuffer.position`/`limit`.
6. `nativeRelease` is only valid when passed the **exact original buffer** created by `nativeAllocate`, exactly once, and when no native/Java operations are still accessing related views.
7. `throw_java` creates an appropriate Java exception instead of continuing to use an invalid pointer. If `FindClass` fails, JNI preserves the resulting exception; the program does not silently dereference `NULL`.
8. The functions accept `ByteBuffer`, but a JNI `jobject` is only partially checked by the Java type system; native address/capacity are still validated before access.

**Production boundary:** the `nativeRelease` helper is intentionally minimal to demonstrate the mechanism. It **does not** check a native registry that this address was ever `malloc`ed by the module; therefore, **it must not be exposed** for arbitrary code to pass in a direct buffer from `allocateDirect` or `slice` and `free` it. A production library should use an opaque native handle/registry, clear ownership, and protection against double-free/use-after-free, rather than relying solely on the `ByteBuffer` type.

### 6.3. Compiling Java and Generating the JNI Header

From the directory containing the two files:

```bash
javac -h . DirectBufferBridge.java
```

The command generates `DirectBufferBridge.class` and the header `DirectBufferBridge.h` containing matching prototypes. The C example in section 6.2 uses standard JNI symbol names for a **class in the default package**; if you move the class into a package such as `com.example`, the JNI symbol names will differ. In a real project, you should set an explicit package and **use the header generated by `javac -h`** to avoid wrong names/signatures.

JDK 22 or FFM is not required to compile this sample; use **JDK 17+**.

### 6.4. Linux — GCC

Assuming `JAVA_HOME` points to a JDK 17+ directory containing `include/jni.h` and `include/linux/jni_md.h`:

```bash
javac -h . DirectBufferBridge.java

gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  DirectBufferBridge.c \
  -o libdirectbufferbridge.so

java -Djava.library.path=. DirectBufferBridge
```

The JNI shared library is loaded by the JVM via `System.loadLibrary("directbufferbridge")`, corresponding to `libdirectbufferbridge.so` on Linux. The C example does not need to link `-ljvm` because this is a JNI library loaded by the JVM, not a native executable using the Invocation API to create a JVM itself.

If `JAVA_HOME` is not set, point it to the **JDK being used by `javac`/`java`** and verify the matching architecture. If the linker cannot find a dependency of `libdirectbufferbridge.so`, check dynamic loader diagnostics, not just `java.library.path`.

### 6.5. macOS — Clang

With JDK 17+ and Xcode Command Line Tools:

```bash
javac -h . DirectBufferBridge.java

clang -std=c11 -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  DirectBufferBridge.c \
  -o libdirectbufferbridge.dylib

java -Djava.library.path=. DirectBufferBridge
```

`JAVA_HOME` can be obtained from `/usr/libexec/java_home` if appropriate. Use a JDK/clang and native library of the same architecture (Apple Silicon vs Intel).

### 6.6. Windows — MSVC x64

Open **x64 Native Tools Command Prompt**, using JDK 17+ x64:

```bat
javac -h . DirectBufferBridge.java

cl /nologo /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  DirectBufferBridge.c ^
  /link /OUT:directbufferbridge.dll

java -Djava.library.path=. DirectBufferBridge
```

The `cl /LD` command compiles and links into a DLL. Note that `JNIEXPORT`/`JNICALL` in the C code help export the correct JNI calling convention and symbols; do not rename functions arbitrarily. A 64-bit JVM must load a 64-bit DLL, and a 32-bit JVM needs a corresponding DLL.

### 6.7. Exact Stdout on the Success Path

With JDK 17+ on a JVM supporting JNI direct-buffer access, with the two source files above and no native load errors:

```text
native-backed direct=true
native-backed initial=[10, 11, 12, 13, 14, 15, 16, 17]
native-backed order=BIG_ENDIAN
sum after Java write=140
after native fill=[42, 11, 7, 7, 7, 15, 16, 17]
after slice fill=[42, 11, 9, 9, 9, 15, 16, 17]
slice sum=27
full-capacity sum=128
position=1, limit=7
java-allocated direct=true
java-allocated sum=18
java-allocated after native fill=[3, 8, 8, 6]
heap buffer rejected=true
```

**Verification calculations:**

- Native creates bytes 10,11,...,17 so the initial Java snapshot gives that exact sequence.
- Java sets index 0 to `42`, the sum native reads is `42+11+12+13+14+15+16+17 = 140`.
- Native fills `7` into offsets 2,3,4 so the sequence becomes `[42,11,7,7,7,15,16,17]`.
- Slice represents exact offsets 2..4, native fills `9` into the slice's three bytes, so the original region changes to `[42,11,9,9,9,15,16,17]`.
- Sum of the slice alone `9+9+9 = 27`.
- Sum of the full capacity `42+11+9+9+9+15+16+17 = 128`. Having `position=1` and `limit=7` **does not** cause native `GetDirectBufferCapacity` to change to 6 or enforce a limit of 7.
- Java creates the second direct buffer with `3,4,5,6`, native computes sum `18` then writes `8` into the two bytes at indices 1,2 → Java sees `[3,8,8,6]`.
- Heap `ByteBuffer.wrap(...)` is rejected by native validation with `IllegalArgumentException`, so the last line prints `true`.

**Byte order does not affect byte values** in stdout. For `getInt/getLong`, you need to pay attention to byte order as in section 8.

## 7. Why Are `position`, `limit`, and `capacity` Not Synonymous?

Java `Buffer` has three numbers:

- **`capacity()`**: the maximum number of elements that can be held in the backing region.
- **`limit()`**: the access limit of the corresponding ByteBuffer operations.
- **`position()`**: the next position of a relative read/write operation.

`remaining() = limit() - position()`.

Example:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(16);
direct.position(4);
direct.limit(12);
```

Result:

```text
capacity = 16
position = 4
limit    = 12
remaining = 8
```

Native calling `GetDirectBufferAddress(direct)` still gets the start address **of this buffer**, and `GetDirectBufferCapacity(direct)` returns **16** (for ByteBuffer). JNI **does not automatically shift to address `base+4`, does not automatically shrink capacity to 8**, and writing via a raw pointer **does not automatically update `position`**.

### 7.1. How to Have Native Process the `remaining()` Region?

**Approach A — Java passes explicit offset/length:**

```java
int offset = direct.position();
int length = direct.remaining();

int checksum = nativeSum(direct, offset, length);
```

This is a snippet with the corresponding variables and native method. Native must check offset/length and not blindly trust the data passed in by the caller.

**Approach B — Java creates a slice of the remaining region:**

```java
ByteBuffer slice = direct.slice();
int checksum = nativeSum(slice, 0, slice.capacity());
```

`slice` represents the exact `position..limit` range of the source buffer at **the time of creation**. `GetDirectBufferAddress(slice)` points to the start of the slice region, and `GetDirectBufferCapacity(slice)` returns the number of bytes in the slice, not the capacity of the original buffer.

**Approach C — native calls Java NIO methods?** Technically it is possible to get `position`/`limit` via JNI method calls, but that adds JNI lookup/method call overhead and complexity. For APIs needing high throughput, passing explicit offset/length or creating a slice in Java is usually simpler and more controllable.

### 7.2. `duplicate()` and `slice()` Share Backing but Have Different Cursors

- `duplicate()`: creates a new view sharing the backing, with independent position/limit/mark.
- `slice()`: creates a view limited to the `remaining` region of the buffer at the time of slicing.
- Modifying bytes through any view is observed through other views, provided the backing is still alive and there is no data race.
- Modifying `position/limit` of one view **does not automatically change** the position/limit of another view.

In the example, `cursor = data.duplicate()` then `cursor.position(2); cursor.limit(5); slice = cursor.slice()`. Creating a slice from `cursor` avoids changing the state of the original `data`; native `nativeFill(slice,0,3,9)` modifies bytes at offsets 2,3,4 of `data`.

### 7.3. Do Not Use Capacity as Unlimited Access Permission

At the JNI level, `GetDirectBufferCapacity` returns capacity. However, if the Java API only authorizes native to read `remaining`, native must respect the granted offset/length or only accept the narrowed slice. Operating past `limit` may still be within native capacity, but may violate the application's **data contract**.

## 8. Byte Order: Direct Buffers Created from JNI Default to `BIG_ENDIAN`

The JNI specification explicitly states that a ByteBuffer returned from `NewDirectByteBuffer` has byte order **`ByteOrder.BIG_ENDIAN`** at creation. `ByteBuffer.allocateDirect` also initializes the order to `BIG_ENDIAN` per Java NIO. However, the native CPU may be little-endian.

If you place a C `uint32_t` into backing memory by directly writing the native representation, and then call Java `buffer.getInt(0)` with the default BIG_ENDIAN, the result may have its byte order reversed compared to the C value.

### 8.1. Choose Endianness According to the Data Protocol

If both sides want to use the **machine's native endianness**, Java must choose:

```java
import java.nio.ByteOrder;

// Snippet in a scope with a valid ByteBuffer buffer.
buffer.order(ByteOrder.nativeOrder());
int number = buffer.getInt(0);
```

If the data is a **big-endian file/network protocol**, you can keep `BIG_ENDIAN` instead of native order. Do not automatically change `order` just because the buffer is direct: **choose byte order according to the data format**, not the storage location.

For 16/32/64-bit data, consider:

- C `uint32_t`/`int32_t` have fixed sizes, but C `long`/`size_t` depend on the ABI.
- Alignment and pointer validity when C casts `uint8_t*` to a multi-byte type.
- Java `ByteBuffer.getInt` accesses according to the configured byte order; this does not mean a raw C pointer will automatically endian-swap.
- If using `asIntBuffer()`, the byte order is taken from the ByteBuffer when the view is created; check alignment/capacity in elements.

### 8.2. Specific Rules for JNI Typed Direct Buffers

JNI `GetDirectBufferCapacity` reports **the number of elements**, not the absolute number of bytes for every Buffer object. For example, an `IntBuffer` with capacity 4 means 4 `int` values; if native treats it as 4 bytes, it will read insufficient data. Only use a JNI native API accepting `ByteBuffer` when the contract counts in bytes. If accepting `IntBuffer`/`ShortBuffer`, type, stride, and alignment must be verified separately.

## 9. Lifecycle Management: More Important Than the "Zero-Copy" Trick

### 9.1. A JNI Object Reference Does Not Own `malloc`

A `ByteBuffer` created from `NewDirectByteBuffer` is a Java object pointing to a native address; it **does not** carry a built-in rule to automatically free `malloc`. Java GC may collect the object; however, that does not mean the corresponding C allocator has had `free` called on it.

Conversely, calling `free` while Java still holds a reference to the buffer does not turn the Java object into "null" or automatically prevent `get/put`. It becomes a dangerous view over an address that is no longer valid.

Therefore, define a clear **owner and release protocol**:

```text
nativeAllocate()
   |
   | malloc(backing)
   | NewDirectByteBuffer(backing, n)
   v
Java NativeOwner  ----- owns ------> backing memory
   |
   | Java/JNI use views synchronously
   v
stop accepting new uses
   |
   | wait for active JNI operations to finish
   | invalidate views at application level
   v
nativeRelease(original) -> free(backing)
   |
   v
CLOSED: no Java/JNI code may read/write old views
```

The `NativeOwner` wrapper in section 6 uses `try-with-resources` for a simple single-threaded flow. There is no reference counting or allocation registry in the demo; **that is an intentional limitation of the example**. In a real product, it must be designed so that an `allocateDirect` buffer or `slice` cannot be accidentally `free`d and double-free is impossible.

### 9.2. Do Not Use `GetDirectBufferAddress` and Store the Pointer Indefinitely

For `ByteBuffer.allocateDirect` managed by the JVM, the backing lifetime is tied to the reachability of the ByteBuffer/cleaner. If C keeps the address after the Java native method returns:

1. C needs to hold a **global JNI ref** to the buffer, e.g., `NewGlobalRef`, if it must ensure the Java object remains reachable.
2. Have a state for registering/stopping/unregistering pointer usage rights.
3. Use the correct `JNIEnv*` of each native thread attached to the JVM if JNI APIs are needed.
4. When native is certain it no longer uses the pointer, call `DeleteGlobalRef` on a valid attached thread.
5. Do not store the pointer past JVM shutdown or after another native owner frees the memory region.

A global reference is a **strong reference to a Java object**, not a memory protection lock and not a substitute for synchronization.

### 9.3. What If Sharing Across Multiple Native/Java Threads?

A direct buffer can be a shared memory region, but does not automatically guarantee:

- Atomicity of multi-byte reads/writes.
- Memory visibility between threads.
- Execution ordering of producer/consumer.
- Safety when one thread calls `free` while another calls `get/put`.
- Thread-safety of `position`/`limit` shared among multiple consumers.

The solution is **proper synchronization**: locks, handoff queues, memory barriers/atomic operations according to the Java and C models, ownership transitions, or non-overlapping partitioning. Do not use `memset`/`GetDirectBufferAddress` as a mechanism to publish a complete record across threads.

A practical design for producer-consumer typically has two regions/states: backing bytes + a "ready" signal published via a proper synchronization mechanism. The producer finishes writing the payload and then publishes; the consumer receives the signal before reading. If native and Java use cross-language atomics, the memory model and ABI of both sides must be verified.

### 9.4. Do Not Rely Solely on `finalize`

An approach relying on `finalize()` to call `free` for C-allocated regions is unpredictable and unsuitable for native resources. Prefer `AutoCloseable` and `try-with-resources`, or a well-designed cleaner/handle mechanism when a safety net is needed, while still requiring **explicit close** for resources with critical lifecycles.

## 10. Buffers and Files: Connection with `FileChannel`

NIO APIs can read file data into a direct `ByteBuffer` and pass it straight to JNI for processing without creating an intermediate `byte[]`. Example snippet inside a Java method with imports and native method already declared:

```java
try (var channel = java.nio.channels.FileChannel.open(
        java.nio.file.Path.of("payload.bin"),
        java.nio.file.StandardOpenOption.READ)) {

    ByteBuffer direct = ByteBuffer.allocateDirect(64 * 1024);

    int count = channel.read(direct);
    if (count > 0) {
        direct.flip(); // position=0, limit=count

        // C reads the exact n bytes actually written by FileChannel.
        int sum = nativeSum(direct, direct.position(),
                            direct.remaining());
        System.out.println("sum=" + sum);
    }
}
```

This is **not a standalone runnable file**: it requires `payload.bin` to exist and `nativeSum` to be declared/loaded as in the previous program. `FileChannel.read` may read less than capacity or return `-1` at EOF. Therefore, do not call native to read the entire 64 KiB just because the buffer has a 64 KiB capacity; **only process the exact `remaining()` after `flip()`**.

**Do not infer that simply passing a direct buffer always yields zero-copy from the kernel to Java**. The JDK and OS may still perform internal copies or buffering during I/O. What we know for sure at the JNI layer is that **the Java direct buffer and the native pointer point to the same backing**, avoiding a manual conversion step through `byte[]`.

### 10.1. MappedByteBuffer and File Mapping

`MappedByteBuffer` is usually also a direct buffer, which can be accessed by JNI via `GetDirectBufferAddress` if the JVM supports it. However, mmap has its own lifetime/unmap semantics; do not cache a raw pointer after the mapping is unmapped or the buffer no longer has valid ownership.

With file mapping, avoid calling `free` on the mapping address. Memory managed by mmap/OS/JVM must be released by the proper owner mechanism (unmap/cleaner/runtime), not by calling `free` out of habit.

## 11. Handling JNI and Java Errors in the Right Place

### 11.1. Checking After `NewDirectByteBuffer`

If `NewDirectByteBuffer` returns `NULL`:

- If there is a pending exception (e.g., object allocation failure), **preserve the exception** or handle it intentionally.
- If the JVM does not support JNI direct buffers and there is no exception, throw a Java `UnsupportedOperationException`/`IllegalStateException` or switch to a fallback.
- Most importantly: **free the native backing that was `malloc`ed** because Java did not receive an owner to release it later.

In the demo, after `view == NULL`, C calls `free(data)` first and then checks `ExceptionCheck` and may throw `IllegalStateException`.

### 11.2. Checking `NULL`/`-1` When Receiving a Buffer from Java

If a native method receives a `ByteBuffer`, do not assume the argument is always direct. Java could pass `null`, `ByteBuffer.allocate(...)`, or `ByteBuffer.wrap(...)`. Check:

```c
void *p = (*env)->GetDirectBufferAddress(env, buffer);
jlong cap = (*env)->GetDirectBufferCapacity(env, buffer);

if (p == NULL || cap < 0) {
    // Reject, do not dereference p.
}
```

This snippet is only valid when `buffer != NULL`; missing the null check may violate the JNI contract. The complete example always checks first.

**Note:** there are situations with capacity equal to 0 on some JVMs/versions where address handling is special. The demo uses positive capacity and treats a NULL address as unsupported/invalid; if a product needs **zero-length direct buffers**, test on the exact target JDK/OS and design a dedicated handling path.

### 11.3. Bounds and Overflow

It is necessary to verify:

```text
0 <= offset
0 <= length
offset <= capacity
length <= capacity - offset
```

Checking `offset + length <= capacity` with small integers can overflow; the pattern `length <= capacity - offset` after confirming non-negative offset is usually safer. Use `jlong` when receiving `GetDirectBufferCapacity` to avoid narrowing to `jint` too early.

If a native method has an `int unsignedValue` parameter and uses `memset`, validate 0..255 so the protocol is clear; the demo follows this exact principle.

### 11.4. Do Not Call Arbitrary JNI Functions When There Is a Pending Exception

JNI functions have rules regarding which ones are allowed to be called when an exception is pending. When `FindClass`/`ThrowNew` fails, return to Java or handle according to the JNI-permitted list, do not continue arbitrary JNI calls or operate on invalidated pointers.

When a native method returns with a pending exception, the JVM delivers that exception to the Java caller per the JNI mechanism. A primitive native return value on the error path should not be used by Java; in the demo `nativeSum` returns `0` after throwing an exception, so the Java caller actually receives the exception instead of treating 0 as a successful result.

## 12. Common Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Calling `GetDirectBufferAddress` on `ByteBuffer.wrap(byte[])` | Returns `NULL`, no direct backing | Use a direct `ByteBuffer` or JNI array APIs |
| Assuming `NewDirectByteBuffer` also calls `malloc` | Using an invalid address | Allocate native backing first |
| Returning a ByteBuffer pointing to a C stack array that has ended | Use-after-return/crash | Use heap/native allocation that lives long enough |
| Not `free`ing the `malloc` region after Java is done | Native memory leak | Owner/AutoCloseable matching the allocator |
| Calling `free` while Java still holds/uses a `slice` | Use-after-free | Revoke access, wait for active users, then release |
| Calling `free` on the address of Java's `allocateDirect` | Corrupts memory not belonging to your malloc | Only free allocations created by the native owner itself |
| Native stores pointer of a Java buffer without keeping a ref | GC may free the backing | Manage strong global ref and lifecycle |
| Treating `GetDirectBufferCapacity` as `remaining()` | Native processes bytes outside payload | Pass offset/length or a slice |
| Assuming `GetDirectBufferAddress` automatically shifts by `position` | Reading wrong bytes | Use `base + position` with bounds |
| Confusing `IntBuffer` capacity with byte count | Reading insufficient/wrong data | Use the proper element size and buffer type |
| Forgetting to consider `BIG_ENDIAN` when reading `getInt` | Wrong multi-byte integer values | Choose byte order according to data/protocol |
| Ignoring `NULL`/`-1` JNI results | Null dereference/crash | Check both address/capacity and exceptions |
| Calling `get/put` after owner closes arena/`free` | Dangling view | Do not let raw buffer escape scope |
| Concurrent `nativeFill` and Java `get` without synchronization | Race/no snapshot | Use synchronization/ownership |
| Using a direct buffer as an atomic primitive | No ordering guarantees | Appropriate locks/atomics/queues |
| Modifying `position/limit` of a buffer from multiple threads | Race on Buffer object state | Each thread uses duplicate/slice + data sync |
| Using `GetByteArrayElements` as a zero-copy guarantee | JVM may copy/pin depending on implementation | For direct buffers, use proper JNI direct APIs |
| Running JNI code on a different thread from the original `JNIEnv*` | Violates thread affinity | Each native thread attaches/gets its own env |
| Using a file mapping pointer after unmap | Invalid memory | Track mapping lifetime |
| Assuming every JVM supports direct-buffer JNI | Not portable | Handle errors/fallback mechanism |

## 13. Synchronous Read/Write Differs from Java Memory Object Ownership

A practical scenario is that `ByteBuffer.allocateDirect` is created by Java in a method and passed to JNI. The JNI method gets the pointer and processes it immediately before returning. This is a case with simple ownership: Java still holds a local reference to the ByteBuffer during the JNI call.

Another scenario: a native driver has a worker thread holding `void *buffer_addr` and Java code no longer has any strong reference to the buffer. In that case, even if the pointer "looks valid" in C, the backing may be reclaimed by the JVM. Holding `NewGlobalRef` to root the buffer is necessary if native wants to use it beyond the call, followed by explicit unregister/free ref handling.

Conversely, when native backing is created by `malloc` and the Java `ByteBuffer` lives for days, the native owner may forget to `free`. A Java reference does not determine that native memory is automatically cleaned up according to `malloc`. Even if Java GCs the object, the backing remains the responsibility of the C allocator unless you design a controlled cleanup hook.

**In summary, there are two different rules:**

- **Java-owned direct memory**: keep the Java buffer reachable while native still uses the pointer.
- **Native-owned memory**: keep the native allocation valid while Java still uses the ByteBuffer; free it exactly once after all users have stopped.

Do not track only one side of the JNI boundary.

## 14. When Should You Use a Direct Buffer and When Not?

**Consider a direct buffer when:**

- Large payloads or repeated reuse across multiple native processing steps.
- The native interface/I/O API genuinely needs a `void*` pointing to a contiguous region.
- Clear owner and lifecycle can be designed.
- Benchmarks show that avoiding copies across JNI improves throughput/latency.
- Data is partitioned into regions that Java and native can own alternately.

**Consider `byte[]`/`GetByteArrayRegion` when:**

- Small data, no need to retain a native pointer.
- Managing native lifecycle is too complex relative to the data size.
- Only a one-time copy into the Java heap is needed and processing is mostly in Java.
- Portability to JVMs that do not support JNI direct-buffer access must be guaranteed.
- The upper-level API inherently accepts `byte[]`, so a direct buffer might force another copy.

**Do not treat zero-copy as an end-to-end promise:** using a direct buffer shares backing between Java and JNI, but upstream/downstream I/O (files, network, codecs, drivers, devices) may still perform copies. Use a profiler/benchmark instead of guessing.

## 15. Extended Exercises

### Exercise 1 — Offset and Limit

In `DirectBufferBridge.java`, create `ByteBuffer.allocateDirect(16)`, set `position(4)` and `limit(12)`. Compare `nativeSum(buffer,4,8)` with `nativeSum(buffer.slice(),0,8)` when the bytes have been initialized. Verify that both read the same 8 bytes, and `GetDirectBufferCapacity(buffer)` in C is still 16.

### Exercise 2 — Java Buffer and Native Buffer

Create two 8-byte buffers: one with `allocateDirect`, one with `nativeAllocate`. Modify byte index 3 from Java and then let JNI read it. Observe that the Java API is the same, but **the release rules are different**: Java-owned direct backing must not be sent to `nativeRelease`, while native-owned must be freed by its owner.

### Exercise 3 — Byte Order

Have native write 4 bytes `01 02 03 04` into a direct buffer. Print `getInt(0)` when the order is `BIG_ENDIAN` and then `LITTLE_ENDIAN`, and explain the two results `0x01020304` and `0x04030201`. Do not cast a misaligned pointer just for convenience.

### Exercise 4 — Catching Errors on a Heap Buffer

Pass `ByteBuffer.wrap(new byte[]{1,2,3})` into `nativeSum`. Verify that native receives `GetDirectBufferAddress == NULL` and Java catches `IllegalArgumentException` per validation. Do not switch to `GetByteArrayElements` unless a fallback has been designed.

### Exercise 5 — Native Fill Out of Bounds

Call `nativeFill(direct, 7, 2, 9)` when capacity is only 8. C must throw `IndexOutOfBoundsException` instead of writing past the byte region. Try `unsignedValue=300` and verify `IllegalArgumentException`.

### Exercise 6 — Safer Release API

Extend the lesson with a native registry mapping an **opaque handle** to pointer/size/state. The Java owner holds the handle and Buffer; `close` records the CLOSED state and calls release only once when there are no outstanding accesses. Native `free`s only a pointer confirmed by the registry to be ALLOCATED. Do not trust an arbitrary `ByteBuffer` passed by the caller to `free`.

### Exercise 7 — FileChannel Reading in Chunks

Open a binary file, read chunk by chunk into `ByteBuffer.allocateDirect`, `flip`, and call JNI to process the exact `remaining`. After each chunk, call `clear` on the buffer for reuse. Do not let native read past `limit` or exceed capacity.

## 16. Practical Implementation Checklist

1. Identify the data owner: **Java `allocateDirect`** or **native `malloc`/allocator**.
2. For native → Java, ensure `address != NULL`, `capacity > 0` and not exceeding `Integer.MAX_VALUE`, and the backing is alive.
3. For Java → native, check `GetDirectBufferAddress != NULL` and `GetDirectBufferCapacity >= 0` before using.
4. Only process `ByteBuffer` in **byte** units; if using a typed buffer, recalculate element count/stride.
5. For offset/length, check bounds and avoid overflow; do not use `capacity` instead of `remaining` if data only extends to limit.
6. Know that `GetDirectBufferAddress` points to the start of the **buffer object/view**, not automatically adding `position`; `slice` is a view with its own base.
7. Choose `ByteOrder` matching the protocol; `NewDirectByteBuffer` starts as `BIG_ENDIAN`.
8. For native backing, define explicit owner release, prevent double-free, and never use a view after free.
9. For Java-owned direct backing used beyond the call, hold an appropriate strong/global reference and delete it when done.
10. Control **concurrent access**, memory visibility, read/write ownership, and shutdown before freeing.
11. Do not use `GetDirectBufferAddress` on heap-backed `ByteBuffer.wrap`; design a JNI arrays fallback if needed.
12. Handle missing JNI support, allocation failures, and pending Java exceptions.
13. Test on the exact OS/ABI/JDK/native compiler; use `javac -h` to generate headers to avoid wrong JNI symbols.
14. Benchmark with real data before concluding a direct buffer is better than all other options.

## Official References

- [Oracle Java 17 — JNI Specification, NIO Support](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#nio-support): `NewDirectByteBuffer`, `GetDirectBufferAddress`, `GetDirectBufferCapacity`, NULL/-1 contract and byte order.
- [Oracle Java 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocateDirect`, `wrap`, `slice`, `duplicate`, `order`, absolute/relative reads/writes.
- [Oracle Java 17 — `Buffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): `capacity`, `position`, `limit`, and `remaining`.
- [Oracle Java 17 — `ByteOrder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html): BIG_ENDIAN/LITTLE_ENDIAN/nativeOrder.
- [Oracle Java 17 — `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): reading/writing data into `ByteBuffer`.
- [Oracle Java 17 — JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): rules for naming JNI native methods and JNI libraries.
- [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): comparing direct buffer usage with byte arrays and native/managed access costs.
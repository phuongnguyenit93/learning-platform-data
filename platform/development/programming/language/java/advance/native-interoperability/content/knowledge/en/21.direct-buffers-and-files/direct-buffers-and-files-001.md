# Direct ByteBuffer and the Difference Between the Java Object and Backing Memory

`java.nio.ByteBuffer` is **a Java object that provides a view and operations over a region of bytes**. With `ByteBuffer.allocateDirect(n)`, the `ByteBuffer` object is still a Java object managed by the JVM, but **the byte contents** may reside in a backing memory region (*backing storage*) outside the Java heap, suitable for interacting with I/O or native libraries.

Distinguishing these two layers determines how to write correct code:

- **The ByteBuffer object** holds metadata and access state: `position`, `limit`, `capacity`, `mark`, read-only, byte order, and the link to the backing region.
- **The backing memory** holds the actual bytes, which can be a Java array, native memory managed by the JVM, a file mapping, or an allocation owned by a C library.
- **Ownership/lifetime** specifies who has the right to free the backing region, when freeing is valid, and whether any Java/native users still hold references to that region.

Therefore, two `ByteBuffer` objects can **differ in identity yet share the same bytes**; conversely, a Java ByteBuffer object can still exist even though the native backing memory source it wraps has been freed improperly. A direct buffer is an access tool, **not automatically an ownership contract**.

This article belongs to the **Buffers and Files** group of Java Advance — native-interoperability. The content focuses on direct/heap, NIO cursors, aliasing via `duplicate()/slice()/asReadOnlyBuffer()`, copy versus view, off-heap memory and GC, JNI direct-buffer APIs, native-owned buffers, file mapping, FFM, threading, performance, and **Java 17+ and C11** example programs.

## 1. Two-layer diagram: wrapper and backing bytes

```text
             Java heap                    backing byte region
  +--------------------------------+     +---+---+---+---+---+---+---+---+
  | ByteBuffer object A            |     |10 |20 |30 |40 | 0 | 0 | 0 | 0 |
  |  capacity = 8                  |     +---+---+---+---+---+---+---+---+
  |  position = 1                  |                   ^
  |  limit = 4                     |                   |
  |  isDirect() = true             |                   |
  |  metadata + backing reference ---------+
  +--------------------------------+
```

The diagram only illustrates the conceptual relationship, **not the private fields or actual layout of `DirectByteBuffer`**. The JDK has the right to change how handles, attachments, or cleanup are stored. What matters are the public API properties:

| Concept | Meaning |
| --- | --- |
| `capacity()` | Total number of bytes **this view** can index |
| `position()` | Next relative read/write index |
| `limit()` | Exclusive end point of the access window |
| `remaining()` | `limit - position` |
| `isDirect()` | Whether it is a direct buffer according to Java NIO |
| `isReadOnly()` | Whether this view forbids writing via Java NIO APIs |
| `order()` | How multi-byte values such as `int`/`long` are interpreted |
| Backing region | The actual bytes and their ownership/deallocation mechanism |

**Object identity is not backing identity.** Using `a == b` to compare two Java ByteBuffer objects may return `false` even though they read/write the same byte region.

### 1.1. Heap buffer and direct buffer

| Property | Heap ByteBuffer | Typical Direct ByteBuffer |
| --- | --- | --- |
| Created with | `ByteBuffer.allocate(n)` or `wrap(byte[])` | `ByteBuffer.allocateDirect(n)` |
| Java wrapper | Java heap object | **Still a Java heap object** |
| Byte storage | Usually a `byte[]` array on the heap | Usually a native/off-heap allocation |
| `isDirect()` | `false` | `true` |
| `hasArray()` | Usually true for writable array backing | False |
| Native I/O | May require an intermediate copy buffer | JVM tries to operate more directly |
| Backing deallocation | GC manages the byte array | According to the JVM/allocator of the direct memory source |
| Allocation cost | Usually lower | Usually higher; benchmark/pool if beneficial |

The Javadoc states that a direct buffer **may** store data outside the ordinary garbage-collected heap, without promising that every implementation uses the exact same malloc or cleaner mechanism. Avoid writing code that depends on implementation class names or reflection to access private address/cleaner fields.

### 1.2. Allocation and array access

```java
ByteBuffer heap = ByteBuffer.allocate(8);
ByteBuffer wrapped = ByteBuffer.wrap(new byte[8]);
ByteBuffer direct = ByteBuffer.allocateDirect(8);

System.out.println(heap.isDirect());    // false
System.out.println(wrapped.isDirect()); // false
System.out.println(direct.isDirect());  // true
System.out.println(direct.hasArray());  // false
```

This is **a snippet inside a Java method**, not a standalone file.

`hasArray()` asks whether a Java backing array can be accessed; **`hasArray() == false` does not prove direct**, because a read-only heap view is also not required to expose its array. Only if `hasArray()` is true do `array()` and `arrayOffset()` help compute the position within the array. If you want to know whether it is direct, use `isDirect()`.

## 2. Cursors are metadata; `flip()` and `clear()` are not copy/free

A ByteBuffer has four main cursor concepts: `capacity`, `position`, `limit`, `mark`. Normally:

```text
0 <= position <= limit <= capacity
         |--------------|
          remaining bytes
```

Operations:

| API | Effect on cursor | Modifies byte data? |
| --- | --- | --- |
| `position(n)` | Sets position | No |
| `limit(n)` | Sets limit | No |
| `flip()` | `limit = old position; position = 0` | No |
| `clear()` | `position = 0; limit = capacity` | **Does not erase bytes** |
| `rewind()` | `position = 0` | No |
| `mark()/reset()` | Saves/restores position | No |
| Relative `get()/put()` | Advances position by number of bytes | Reads/writes bytes |
| Absolute `get(index)/put(index,value)` | Does not change position | Reads/writes at index |
| `compact()` | Moves remaining bytes to the beginning and updates cursor | **Moves/copies bytes** |

Example:

```java
ByteBuffer input = ByteBuffer.allocateDirect(8);

input.put((byte) 10);
input.put((byte) 20);
input.put((byte) 30);

System.out.println(input.position()); // 3
System.out.println(input.limit());    // 8

input.flip();
System.out.println(input.position()); // 0
System.out.println(input.limit());    // 3
System.out.println(input.remaining());// 3
```

This is a Java code snippet inside a method. `flip()` **does not move the three bytes anywhere**: it only switches the view from the producer-writing state to the consumer-ready-to-read state. A subsequent `clear()` opens the window to reuse the full capacity, but the old bytes may still be there. **`clear()` is not secure for erasing sensitive information.**

In file/network code, do not use `capacity()` as the “number of valid payload bytes”. If 3 bytes were read into a buffer with capacity 8192, the payload may only be 3 bytes; `remaining()` after `flip()` is what reflects the written window.

## 3. One backing region, multiple view objects: aliasing

### 3.1. `duplicate()` creates a new object and cursor, does not copy bytes

```java
ByteBuffer parent = ByteBuffer.allocateDirect(8);
parent.put(1, (byte) 20);

ByteBuffer duplicate = parent.duplicate();

System.out.println(parent == duplicate); // false

duplicate.put(1, (byte) 25);
System.out.println(parent.get(1));       // 25

duplicate.position(4);
System.out.println(parent.position());   // 0
```

The two objects share bytes: changing a byte via `duplicate` is visible from `parent`. However, their positions are independent. `duplicate()` is suitable when two readers need separate cursors, **not** for creating an immutable snapshot.

### 3.2. `slice()` creates a window with a new 0 offset

```java
ByteBuffer parent = ByteBuffer.allocateDirect(8);

parent.put(2, (byte) 30);
parent.position(2);
parent.limit(5);

ByteBuffer view = parent.slice();

System.out.println(view.capacity()); // 3
System.out.println(view.position()); // 0

view.put(0, (byte) 99);
System.out.println(parent.get(2));   // 99
```

The slice only covers byte indices 2, 3, and 4 of the parent. Offset 0 of the slice is at byte index 2 of the parent. From a JNI perspective, the backing region for the slice is still direct, but **the starting address of the view** may be offset, differing from the parent's address.

Changing the parent's position/limit **after the slice is created** does not automatically change the length or cursor of the slice.

### 3.3. A read-only view still shares data

```java
ByteBuffer parent = ByteBuffer.allocateDirect(2);
ByteBuffer readOnly = parent.asReadOnlyBuffer();

System.out.println(readOnly.isReadOnly()); // true

parent.put(0, (byte) 9);
System.out.println(readOnly.get(0));       // 9
```

A read-only view blocks writes through that view's own Java NIO API, but the writable parent can still modify the backing bytes. This is not an “immutable snapshot”. If a C library holds a writable pointer to the same backing region, Java read-only metadata does not force C to obey it. Do not use a read-only view as a security boundary against untrusted native code.

### 3.4. A true copy must allocate new data

```java
ByteBuffer direct = ByteBuffer.allocateDirect(3);
direct.put(0, (byte) 1);
direct.put(1, (byte) 2);
direct.put(2, (byte) 3);

ByteBuffer reader = direct.duplicate();
reader.position(0);
reader.limit(3);

byte[] snapshot = new byte[reader.remaining()];
reader.get(snapshot);

direct.put(0, (byte) 9);
System.out.println(snapshot[0]); // 1
System.out.println(direct.get(0)); // 9
```

This is an **independent copy**: `snapshot` no longer aliases the direct buffer. Accept the copy cost if the caller must use the bytes after the original owner buffer is released/reused or must preserve immutable state.

## 4. Complete Java 17+ example: different wrappers, shared backing

The main program **does not require JNI, C, FFM, or preview features**. All results are deterministic numbers or strings from buffer operations, not relying on raw addresses or GC timing.

### 4.1. File `DirectBackingDemo.java`

```java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ReadOnlyBufferException;
import java.util.Arrays;

public final class DirectBackingDemo {
    private DirectBackingDemo() {}

    public static void main(String[] args) {
        ByteBuffer heap = ByteBuffer.allocate(6);
        ByteBuffer direct = ByteBuffer.allocateDirect(8);

        System.out.println("heap-direct=" + heap.isDirect());
        System.out.println("direct-direct=" + direct.isDirect());
        System.out.println("direct-has-array=" + direct.hasArray());

        direct.put(0, (byte) 10);
        direct.put(1, (byte) 20);
        direct.put(2, (byte) 30);
        direct.put(3, (byte) 40);

        ByteBuffer alias = direct.duplicate();
        System.out.println("same-object=" + (direct == alias));

        alias.put(1, (byte) 25);
        System.out.println(
            "shared-byte=" + Byte.toUnsignedInt(direct.get(1)));

        alias.position(4);
        System.out.println(
            "direct-position-after-alias=" + direct.position());

        direct.position(1);
        direct.limit(4);
        ByteBuffer slice = direct.slice();
        System.out.println("slice-capacity=" + slice.capacity());

        slice.put(1, (byte) 33);
        System.out.println(
            "slice-updated-origin="
                + Byte.toUnsignedInt(direct.get(2)));
        System.out.println("parent-position=" + direct.position());

        ByteBuffer readOnly = direct.asReadOnlyBuffer();
        System.out.println("read-only=" + readOnly.isReadOnly());

        direct.put(2, (byte) 44);
        System.out.println(
            "read-only-sees="
                + Byte.toUnsignedInt(readOnly.get(2)));

        try {
            readOnly.put(2, (byte) 99);
        } catch (ReadOnlyBufferException expected) {
            System.out.println("read-only-write=blocked");
        }

        ByteBuffer transport = ByteBuffer.allocateDirect(5);
        transport.put((byte) 1)
                 .put((byte) 2)
                 .put((byte) 3);

        System.out.println(
            "before-flip="
                + transport.position() + "/" + transport.limit());

        transport.flip();
        System.out.println(
            "after-flip="
                + transport.position() + "/" + transport.limit());

        byte[] snapshot = new byte[transport.remaining()];
        transport.get(snapshot);
        System.out.println("snapshot=" + Arrays.toString(snapshot));

        transport.put(0, (byte) 9);
        System.out.println("snapshot-first=" + snapshot[0]);
        System.out.println(
            "direct-first="
                + Byte.toUnsignedInt(transport.get(0)));

        ByteBuffer endian = ByteBuffer.allocateDirect(4);
        endian.order(ByteOrder.LITTLE_ENDIAN);
        endian.putInt(0, 0x01020304);

        System.out.println(
            "little-endian="
                + Byte.toUnsignedInt(endian.get(0)) + " "
                + Byte.toUnsignedInt(endian.get(1)) + " "
                + Byte.toUnsignedInt(endian.get(2)) + " "
                + Byte.toUnsignedInt(endian.get(3)));
    }
}
```

Explanation:

1. `heap` is non-direct, `direct` is direct; direct usually does not expose a Java `byte[]`.
2. `duplicate()` does not copy the backing, so writing byte 1 through `alias` shows up in `parent`.
3. `alias.position(4)` does not move `direct.position()`.
4. `direct.position(1), limit(4)` creates a slice with capacity 3; offset 1 of the slice points to byte 2 of the root.
5. The read-only view reads byte 44 just written by the parent, but rejects `put`.
6. `flip()` changes the cursor from 3/5 to 0/3; the snapshot created from `byte[]` has independent data.
7. `putInt` with `LITTLE_ENDIAN` produces bytes 4 3 2 1 in index order.

### 4.2. Compile, run, and output

```bash
javac DirectBackingDemo.java
java DirectBackingDemo
```

**Deterministic stdout of the program:**

```text
heap-direct=false
direct-direct=true
direct-has-array=false
same-object=false
shared-byte=25
direct-position-after-alias=0
slice-capacity=3
slice-updated-origin=33
parent-position=1
read-only=true
read-only-sees=44
read-only-write=blocked
before-flip=3/5
after-flip=0/3
snapshot=[1, 2, 3]
snapshot-first=1
direct-first=9
little-endian=4 3 2 1
```

There is no line printing a raw address: a native address typically changes across JVMs, allocations, ASLR, and runs; it is not a stable output to verify “same backing region”. **Testing by writing through one view and reading back through the other** is a clearer aliasing test.

## 5. Why is direct beneficial for native I/O yet does not guarantee end-to-end zero-copy?

The `ByteBuffer` Javadoc states that the JVM will make a **best effort** to perform native I/O directly on direct buffers to avoid copying to/from an intermediate buffer. There is no guarantee that every end-to-end data path is zero-copy:

- The OS may still copy between kernel and user space.
- TLS, encryption, compression, framing, checksums, and protocol transformations may require copying or other processing.
- A native library may intentionally copy bytes into another buffer.
- A Java application layer may convert encodings or create a `byte[]` snapshot.
- Direct allocation/deallocation generally costs more than heap buffer allocation.
- For small data, the benefit does not outweigh the overhead; benchmark on the actual workload before optimizing.

A `ByteBuffer.allocateDirect(8192)` is only **a container of at most 8192 bytes**; not all 8192 bytes are necessarily valid payload. Channel I/O typically operates only on `remaining()` bytes between position and limit. C code with a raw pointer **does not automatically have NIO update cursors or protocol length**.

### 5.1. FileChannel and buffer state

```java
// Structural example: a FileChannel channel is already open for reading.
ByteBuffer buffer = ByteBuffer.allocateDirect(8192);

int n = channel.read(buffer);
if (n > 0) {
    buffer.flip(); // Read the exact n bytes just written to the buffer.
    while (buffer.hasRemaining()) {
        byte value = buffer.get();
        // Process value according to the application protocol.
    }
    buffer.clear(); // Reset cursor, DO NOT zero bytes.
}
```

This is **illustrative code**, not a standalone program. For partial protocol frames, the buffer should not be `clear()`ed arbitrarily if undecoded bytes remain; `compact()` can be used to preserve the unconsumed portion.

## 6. Lifecycle: who keeps the backing memory valid?

### 6.1. Buffers from `allocateDirect`

With `ByteBuffer.allocateDirect(n)`, the backing memory is managed by the JVM/implementation. On common JVMs, native memory cleanup is tied to reachability/cleaners and may happen later than when the local variable goes out of scope.

**There is no standard `ByteBuffer.close()` in Java 17** for this kind of buffer. None of the following are safe ways to release it:

- Calling C `free(address)` on a backing region allocated by the JVM.
- Accessing internal cleaner/`Unsafe` via reflection to force deallocation.
- Assigning `buffer = null` and assuming native bytes are immediately returned to the OS.
- Relying on `System.gc()` as an API with a deadline.
- Keeping a `slice` in a cache while expecting the parent's backing allocation to have been cleaned up.

A 10-byte `slice` can keep a 64 MiB direct buffer backing region alive. This is why a cache that is small by **payload size** is not necessarily small by **backing allocation size**.

### 6.2. Native C retaining a pointer after the Java method returns

Suppose Java calls a “start async” native function and passes a direct buffer. If C stores the pointer in a native queue and returns immediately, **the GC does not see a raw C pointer as a Java strong reference**. In that case, a Java owner must keep the ByteBuffer/view reachable, while ensuring the buffer is not reused/freed until C signals actual completion/cancellation.

Do not assume `Reference.reachabilityFence(buffer)` at the end of the submit method is sufficient for asynchronous native work running later. A fence only keeps the reference alive **up to the point where the fence is called**. To keep it alive longer, there must be a Java owner tracking the in-flight record/handle or a native-owned allocation with a clear cleanup protocol.

### 6.3. Reachability fence in a synchronous JNI call

```java
import java.lang.ref.Reference;
import java.nio.ByteBuffer;

static void withFence(ByteBuffer buffer) {
    try {
        synchronousNativeUse(buffer); // Application-defined native method.
    } finally {
        Reference.reachabilityFence(buffer);
    }
}
```

This is an **illustrative snippet**, without a definition of `synchronousNativeUse`. The fence ensures the buffer remains strongly reachable up to that point, not that the backing region “lives forever”. For a C allocation outside the JVM, Java reachability also cannot stop another native library from proactively calling `free()` at the wrong time.

## 7. JNI can obtain the byte address, but does not own the memory

JNI NIO support consists of three functions:

```c
jobject NewDirectByteBuffer(JNIEnv *env,
                            void *address,
                            jlong capacity);

void *GetDirectBufferAddress(JNIEnv *env,
                             jobject buffer);

jlong GetDirectBufferCapacity(JNIEnv *env,
                              jobject buffer);
```

These are illustrative prototypes; in C they are called via `(*env)->...`.

- `GetDirectBufferAddress` returns **the starting address of the region referenced by the buffer view** when supported; for a slice, the address may already include the offset from the parent.
- `GetDirectBufferCapacity` returns the number of elements of the associated region. For **ByteBuffer** itself, one element = one byte; for typed direct buffers, note the different unit.
- These two functions do not automatically apply Java `position/limit` per request. C must use a validated offset and length.
- Standard JNI has no `ReleaseDirectBufferAddress` function: do not `free` the returned pointer just because you are done accessing it.
- A JVM is permitted not to support JNI direct-buffer access; in that case `GetDirectBufferAddress` may return `NULL`, and `GetDirectBufferCapacity` may return `-1`.
- `NewDirectByteBuffer` creates a Java object **wrapping an existing native region**; ownership still belongs to the original allocator/contract, not implicitly transferred to the GC.

### 7.1. Address and offset protocol

If Java passes a direct `ByteBuffer` with `position=5`, C calling `GetDirectBufferAddress` typically receives **the base address of the view** rather than automatically `address + position`. If you want C to see only bytes from `position..limit`, you can pass `buffer.slice()` after setting the cursor properly; the new slice has capacity equal to `remaining` and offset 0 at the parent's current position.

Do not confuse `GetDirectBufferCapacity` with “the number of payload bytes of the request”. With a newly allocated direct buffer of capacity 4096 where only 17 bytes were received via I/O, C must not assume all 4096 bytes are a valid message.

### 7.2. Reading/writing raw pointers and byte order

A C pointer can be treated as `unsigned char*` to access bytes. When wanting to read/write `int32_t` via cast, you must consider alignment, ABI, byte order, and strict-aliasing rules. It is safer to define a byte-level protocol, use `memcpy` into a local C variable, or encode/decode explicitly.

Java `buffer.order(ByteOrder.LITTLE_ENDIAN)` changes how Java `getInt/putInt` interpret bytes; **it does not automatically switch the C pointer to little-endian**. C must also adhere to the defined format.

## 8. Runnable Java 17 + C11 example: native writing directly into the backing region

The JNI example below only writes a byte during **a single synchronous call** and does not store the pointer after returning. The buffer is created with `allocateDirect` in Java, so the backing region is managed by the JVM; C only **borrows access**, without owning the allocation.

### 8.1. File `DirectBufferJniDemo.java`

```java
import java.lang.ref.Reference;
import java.nio.ByteBuffer;

public final class DirectBufferJniDemo {
    static {
        System.loadLibrary("directbufdemo");
    }

    private DirectBufferJniDemo() {}

    private static native void nativeWriteByte(
        ByteBuffer buffer, int index, byte value);

    public static void writeChecked(
        ByteBuffer buffer, int index, byte value) {

        if (buffer == null || !buffer.isDirect()
                || buffer.isReadOnly()) {
            throw new IllegalArgumentException(
                "writable direct ByteBuffer required");
        }

        if (index < 0 || index >= buffer.capacity()) {
            throw new IndexOutOfBoundsException(
                "index outside buffer capacity");
        }

        try {
            nativeWriteByte(buffer, index, value);
        } finally {
            Reference.reachabilityFence(buffer);
        }
    }

    public static void main(String[] args) {
        ByteBuffer direct = ByteBuffer.allocateDirect(4);

        writeChecked(direct, 1, (byte) 77);
        System.out.println(
            "jni-value=" + Byte.toUnsignedInt(direct.get(1)));

        try {
            writeChecked(ByteBuffer.allocate(4), 0, (byte) 1);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                "heap-rejected=IllegalArgumentException");
        }

        try {
            writeChecked(direct.asReadOnlyBuffer(), 0, (byte) 1);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                "readonly-rejected=IllegalArgumentException");
        }

        try {
            writeChecked(direct, 4, (byte) 1);
        } catch (IndexOutOfBoundsException expected) {
            System.out.println(
                "bounds-rejected=IndexOutOfBoundsException");
        }
    }
}
```

`writeChecked` checks direct, writable, and index in `[0, capacity)`. If your API only allows writing within `position..limit`, it must check the window or pass a slice instead of using the full capacity. `Reference.reachabilityFence` is placed after the synchronous call; it does not replace an owner for native async.

### 8.2. JNI header generated by javac

```bash
javac -h . DirectBufferJniDemo.java
```

The prototype in the header has the form:

```c
JNIEXPORT void JNICALL
Java_DirectBufferJniDemo_nativeWriteByte(
    JNIEnv *, jclass, jobject, jint, jbyte);
```

This is a prototype excerpt; the C file should include **the actual header** generated by `javac -h .`. Because the native method is `static`, the second parameter is `jclass`.

### 8.3. File `DirectBufferJniDemo.c`

```c
#include "DirectBufferJniDemo.h"

static void raise_exception(JNIEnv *env,
                            const char *class_name,
                            const char *message) {
    jclass type = (*env)->FindClass(env, class_name);
    if (type == NULL) {
        /* Usually a Java exception is already pending. */
        return;
    }

    (void)(*env)->ThrowNew(env, type, message);
    (*env)->DeleteLocalRef(env, type);
}

JNIEXPORT void JNICALL
Java_DirectBufferJniDemo_nativeWriteByte(
    JNIEnv *env,
    jclass clazz,
    jobject buffer,
    jint index,
    jbyte value) {

    (void)clazz;

    if (buffer == NULL) {
        raise_exception(
            env, "java/lang/IllegalArgumentException",
            "buffer is null");
        return;
    }

    jlong count = (*env)->GetDirectBufferCapacity(env, buffer);
    void *address = (*env)->GetDirectBufferAddress(env, buffer);

    if (count < 0 || address == NULL) {
        raise_exception(
            env, "java/lang/IllegalArgumentException",
            "direct-buffer JNI access unavailable");
        return;
    }

    if (index < 0 || (jlong)index >= count) {
        raise_exception(
            env, "java/lang/IndexOutOfBoundsException",
            "index outside direct buffer capacity");
        return;
    }

    unsigned char *bytes = (unsigned char *)address;
    bytes[index] = (unsigned char)value;
}
```

In the C code, `count` is the capacity in bytes because `buffer` is always a Java `ByteBuffer` (not an `IntBuffer`). `address` points to the backing region, and C only writes one byte after checking bounds. **Do not `free(address)`** and do not cache the pointer. The Java facade already blocked read-only views; native C with a raw pointer should not be relied upon as the enforcement mechanism for Java read-only policy if another API calls directly into it.

### 8.4. Build/run on Linux

Place both files `DirectBufferJniDemo.java` and `DirectBufferJniDemo.c` in the same directory, with `JAVA_HOME` pointing to a JDK 17+ that has headers:

```bash
javac -h . DirectBufferJniDemo.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  DirectBufferJniDemo.c -o libdirectbufdemo.so

java -Djava.library.path=. DirectBufferJniDemo
```

**Exact stdout on a Linux JVM supporting JNI direct-buffer access:**

```text
jni-value=77
heap-rejected=IllegalArgumentException
readonly-rejected=IllegalArgumentException
bounds-rejected=IndexOutOfBoundsException
```

The three error paths trigger in the Java facade before calling C; the success path shows C modifying the bytes seen by Java `get(1)`. The code is written for Java 17+ and JNI C11, without using preview FFM APIs. On Windows/macOS, change the shared library name, include folder, and build flags. If you encounter `UnsatisfiedLinkError`, check `java.library.path`, the library name, and the ABI.

## 9. Reverse direction: `NewDirectByteBuffer` wrapping C-owned memory

A C library can call:

```c
jobject view = (*env)->NewDirectByteBuffer(env, ptr, capacity);
```

This is an **illustrative snippet**, not a standalone C program. `ptr` must point to a valid native memory region at least `capacity` bytes long and meet JNI direct buffer requirements. Java will get a `ByteBuffer` **pointing to the existing region**, not a copy, and it does not automatically turn C's `malloc` into JVM-allocated memory.

Anti-pattern that is **wrong and must not be used**:

```c
void *p = malloc(256);
jobject b = (*env)->NewDirectByteBuffer(env, p, 256);
free(p); /* WRONG: b still holds a view pointing to the freed region. */
return b;
```

Never copy this anti-pattern into a program. If Java still reads/writes `b` after `free(p)`, it may receive garbage data, undefined behavior, or crash the JVM.

Safer production organization:

1. The native owner holds the allocation handle and open/closed state.
2. The Java wrapper has an explicit lifecycle (for example, an `AutoCloseable` component holding the handle and view).
3. Do not let a raw `ByteBuffer` continue to be used after the owner closes. If the data must be kept, **copy before closing**.
4. C and Java coordinate so `free` is not called while native async operations or Java consumers are still using the region.
5. Release with the matching allocator, exactly once. A Cleaner can be used as a fallback, but it has no exact deadline and does not replace explicit close.
6. Do not use `ByteBuffer.isDirect()` as a sign that “the JVM will free it automatically”: the allocation source is what determines ownership.

### 9.1. Lifetime table by allocation source

| Source | Backing bytes | Who has the right to release? |
| --- | --- | --- |
| `ByteBuffer.allocate(n)` | Java heap array | Java GC |
| `ByteBuffer.wrap(array)` | Caller's Java array | Java GC, caller owns the data |
| `ByteBuffer.allocateDirect(n)` | Usually off-heap | JVM/direct-buffer allocation mechanism |
| `duplicate()/slice()` of a direct buffer | **Same** backing region as parent | Owner of the parent's backing region, not the new view |
| `NewDirectByteBuffer(ptr,n)` | Existing C/native memory | Native owner per `ptr`'s contract |
| `MappedByteBuffer` | File-backed mapping | Corresponding mapping/OS/JVM lifecycle |
| `MemorySegment.asByteBuffer()` (JDK22+) | Segment's region | Scope/Arena owner, does not outlive close |

In all cases, **having a reference to a Java ByteBuffer** and **having valid access rights to the backing region** are two different conditions. C can free a native allocation at the wrong time even while the Java object is still reachable; conversely, a reachable slice can keep a large direct backing allocation alive longer than expected.

## 10. File mapping and FFM: direct does not mean the same owner

`FileChannel.map(...)` returns a `MappedByteBuffer`, which is usually direct. It points to a file mapping, not an ordinary `malloc` region for the Java caller to free directly. Closing the `FileChannel` should not be assumed to invalidate the mapped buffer immediately; check the Javadoc for mapping lifetime, persistence, `force()`, and OS behavior when integrating.

Since JDK 22, FFM provides `MemorySegment.ofBuffer(buffer)`. **Illustrative example inside a Java 22+ method**:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(8);
direct.position(2);
direct.limit(5);

MemorySegment view = MemorySegment.ofBuffer(direct);
System.out.println(view.isNative()); // true
System.out.println(view.byteSize()); // 3
```

The FFM Javadoc states that the segment covers the window from position to limit. For a regular direct buffer, an automatic scope keeps the buffer reachable while the segment or its slices remain reachable. However, for a `ByteBuffer` created from `MemorySegment.asByteBuffer()` of an Arena, the `ofBuffer` segment **inherits the exact same scope** as the original segment:

```java
MemorySegment returned;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeMemory = arena.allocate(8);
    ByteBuffer nioView = nativeMemory.asByteBuffer();
    returned = MemorySegment.ofBuffer(nioView);
}

System.out.println(returned.scope().isAlive()); // false
```

This is a JDK 22+ snippet with `java.lang.foreign.*` imported; **it does not compile on JDK 17**. When the Arena closes, views sharing the scope are no longer permitted to be accessed, **even if the view's Java object has not yet been collected by GC**. This is a vivid illustration that a direct buffer is a view, not a license to extend native memory lifetime.

## 11. Byte order, alignment, and C layout

`ByteBuffer` holds bytes; operations like `getInt/putInt/getLong/putLong` use the view's own `ByteOrder` to encode/decode. A C raw pointer does not automatically read the ByteBuffer's `order()` metadata. Example:

```java
ByteBuffer b = ByteBuffer.allocateDirect(4);
b.order(ByteOrder.LITTLE_ENDIAN);
b.putInt(0, 0x01020304);

System.out.println(Byte.toUnsignedInt(b.get(0))); // 4
System.out.println(Byte.toUnsignedInt(b.get(1))); // 3
System.out.println(Byte.toUnsignedInt(b.get(2))); // 2
System.out.println(Byte.toUnsignedInt(b.get(3))); // 1
```

When passing a buffer containing a C struct, you must agree on **byte order, field widths, alignment, padding, and ABI**. On one system, C `long` may be 8 bytes, on another 4 bytes. Do not arbitrarily cast a byte address to `struct*` just because Java sees enough bytes; there must be a contract from the native header/compiler.

`duplicate/slice` views may start with `BIG_ENDIAN` per the JDK API; do not assume every view inherits the `ByteOrder` set on its parent. Configure `order(...)` explicitly on each view that performs typed access. `ByteOrder.nativeOrder()` helps determine the hardware byte order, but a portable protocol should use an agreed-upon order rather than depending on the local CPU.

## 12. Observing native memory, limits, and operational failures

Java heap metrics do not fully reflect direct buffer memory and native allocations. These sources should be used together:

| Observation source | What it is used for | Limitations |
| --- | --- | --- |
| `BufferPoolMXBean` | Buffer count, total capacity, memory used of direct/mapped pools | Does not necessarily cover all native allocations |
| Java Flight Recorder | Allocation, GC, related native memory per JVM-supported events | Event availability varies by JDK |
| HotSpot Native Memory Tracking | Summary of native memory accounted for by the JVM | Does not cover all external library `malloc` calls |
| OS RSS/memory maps | Total physical memory and mappings of the process | Does not directly show which Java object holds the backing |
| Heap dump/retention analysis | Finding ByteBuffer/slice/views retained by caches | Not a measure of total off-heap bytes |

Example of reading Java management counters (placed inside a method):

```java
for (java.lang.management.BufferPoolMXBean pool :
     java.lang.management.ManagementFactory.getPlatformMXBeans(
         java.lang.management.BufferPoolMXBean.class)) {

    System.out.println(pool.getName()
        + " count=" + pool.getCount()
        + " capacity=" + pool.getTotalCapacity()
        + " memory=" + pool.getMemoryUsed());
}
```

This is illustrative code with **stdout varying by JVM and measurement time**; do not use it as golden stdout. Some HotSpot versions support:

```bash
java -XX:NativeMemoryTracking=summary MyServer
jcmd <PID> VM.native_memory summary
```

In these two operational commands, replace `MyServer` and `<PID>` according to the actual program. NMT must be enabled at startup and has overhead. `-XX:MaxDirectMemorySize=64m` is an example JVM flag that limits JVM-managed direct-buffer memory on runtimes that support it; **it does not limit all allocations by native C libraries**. Do not recommend 64 MiB as a production default.

When encountering a direct-buffer-related `OutOfMemoryError`, the heap may not be full yet. Investigate in-flight buffers, live views, queues, pooling policies, GC cleanup latency, file mappings, and unfreed C allocations.

## 13. Pooling, aliasing, and concurrency

Creating direct buffers can be more expensive than heap buffers. Pooling bounded by count and total bytes can reduce churn in heavy I/O workloads, but comes with ownership rules:

1. Borrow a buffer with its cursor state appropriately reset.
2. Producer writes, `flip()`s before consumer reads.
3. Consumer processes within `remaining()` bounds or an explicit slice.
4. Do not return the buffer to the pool while any Java view or native operation is still using the old bytes.
5. For sensitive data, **actually overwrite** it before reassigning the buffer; `clear()` does not zeroize.
6. Bound the pool by **total native backing bytes**, not just by the number of wrapper objects.
7. If C uses the pointer asynchronously, a Java timeout does not mean C has stopped. Do not reuse/free before native completion.

`ByteBuffer` is not an automatically synchronized structure for two threads modifying position or bytes concurrently. `duplicate()` gives each thread its own cursor, **but does not eliminate data races on the backing storage**. A reader/writer protocol needs proper synchronization, ownership transfer, or memory ordering.

A 16-byte slice can keep an entire 64 MiB parent allocation reachable. If a slice must be stored long-term, copy the 16 bytes into an independent region to reduce retained native memory. However, copying has a cost, so choose based on lifecycle and measured performance.

## 14. Common mistakes

| Misconception | Correct fact to remember |
| --- | --- |
| “A direct buffer has no Java object” | The wrapper and metadata are still a Java object |
| “`isDirect` means C owns the memory” | No, ownership depends on the allocation source |
| “Two different `ByteBuffer` objects mean two copies” | `duplicate/slice/asReadOnlyBuffer` still alias |
| “`clear()` erases data” | Only resets cursors; not a secure wipe |
| “`flip()` copies bytes” | Only changes position/limit |
| “`GetDirectBufferAddress` adds position for C” | Pointer points to the base of the **view**; handle position separately |
| “`GetDirectBufferCapacity` is the payload length” | It reports the view's capacity, without knowing the protocol |
| “`hasArray()==false` guarantees direct” | A read-only heap buffer can also return false |
| “A read-only view is an immutable snapshot” | The view still sees backing changes made by another owner |
| “Java read-only automatically stops C from writing via raw pointer” | Native code must obey the contract; NIO metadata is not a sandbox |
| “C may `free` a pointer obtained via JNI from `allocateDirect`” | No; the JVM manages that allocation |
| “Java GC will free any pointer from `NewDirectByteBuffer`” | No; the native owner must design cleanup |
| “As long as the object is reachable, C's native pointer is valid” | If C frees it at the wrong time, the object becomes dangling |
| “Calling `System.gc()` closes direct buffers” | No GC/cleanup deadline is guaranteed |
| “Keeping a tiny slice only costs a few bytes” | A slice can extend the lifetime of a large allocation |
| “Direct = end-to-end zero-copy” | The JVM only makes a best effort on certain native I/O paths |
| “One buffer used across threads is automatically thread-safe” | Cursors and bytes require synchronization/ownership |
| “C closes an async buffer as soon as a Future times out” | Native code may still be using the pointer |
| “Changing `ByteOrder` on the parent definitely changes all views” | Explicitly set order on the view doing typed access |
| “A MemorySegment view extends Arena lifetime” | An Arena's view becomes invalid when the Arena closes |

## 15. Implementation checklist

**Before creating a buffer:** decide whether heap or direct is needed, the size, payload length, byte order, and actual native I/O need. Do not allocate direct out of habit; measure throughput, latency, GC, and native memory footprint.

**Before sharing a view:** ask whether `duplicate/slice/asReadOnlyBuffer` aliases the old owner, who is allowed to write, who has their own cursor, when data is allowed to be overwritten, and whether a copy/snapshot is needed to decouple lifetimes.

**Before calling JNI:** check direct, read-only, bounds, position/limit contract, `GetDirectBufferAddress/Capacity` results, and ABI. Is the pointer used synchronously or stored by C across return? If async, an owner must keep the allocation valid until completion.

**When releasing:** identify the exact allocator that created the backing region. Do not `free` JVM-managed allocations; do not forget native `malloc`. If the owner is an Arena, all related views become invalid when the Arena closes. Do not let callbacks or request retries touch the buffer after the owner releases it.

**In operations:** bound pools, in-flight buffers, and queues; check off-heap memory counters, RSS, caches holding slices, delayed cleaners, native allocations, and cancellation paths. Do not use `clear()` as a secure wipe.

**Key takeaway:** **A direct ByteBuffer is a Java object used to view a region of bytes; the byte region itself has its own owner and lifetime.** Creating additional views does not allocate additional data, and native C obtaining a pointer does not transfer ownership. A safe design always answers: **Who owns it? Who is using it? When does the backing region become invalid?**

### Official references

- [Java SE 17 — ByteBuffer, direct buffers, duplicate, slice, read-only, and ByteOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java SE 17 — Buffer, position, limit, flip, clear, compact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html)
- [Java SE 17 — JNI Functions, NewDirectByteBuffer/GetDirectBufferAddress/GetDirectBufferCapacity](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Java SE 17 — Reference.reachabilityFence](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html)
- [Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Java SE 22 — MemorySegment.ofBuffer/asByteBuffer scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)

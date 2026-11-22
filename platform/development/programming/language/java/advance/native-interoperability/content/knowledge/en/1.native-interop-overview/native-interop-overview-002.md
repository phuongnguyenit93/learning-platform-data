# Relationship between the JVM, Java code, C/C++ libraries, and off-heap memory

## 1. The big picture

A Java program runs on the **JVM (Java Virtual Machine)**, but the JVM itself is native software (mainly written in C/C++) running inside an operating system process. Therefore, **Java code, the JVM, and C/C++ libraries can coexist in the same process and share that process's memory**.

There are three questions to separate:

1. **Who executes?** Java bytecode is interpreted or JIT-compiled by the JVM into machine code; C/C++ code is already compiled into machine code for a specific operating system and CPU architecture.
2. **How do they communicate?** Java can call native functions via **JNI** or the **Foreign Function & Memory API (FFM)**. Java APIs such as NIO can also rely on the JVM to perform I/O using native code.
3. **Where does the data live, and who frees it?** Java objects usually live on the **Java heap**; memory allocated with `malloc`, direct buffers, or native `MemorySegment`s can live **outside the Java heap (off-heap)**. Lifecycle management mechanisms differ depending on the allocation source.

Conceptual diagram:

~~~text
An operating system process
|
+-- JVM runtime (native code)
|   +-- Class loading, bytecode verification, interpreter/JIT, GC
|   +-- Java heap: regular Java objects
|   +-- Memory serving the JVM: metaspace, code cache, thread stack, ...
|   +-- Running Java code
|        +-- Pure Java APIs
|        +-- Java NIO / direct ByteBuffer
|        +-- JNI / FFM ----> native function in C/C++ library
|
+-- Native library loaded into the same process (.dll/.so/.dylib)
|   +-- Machine code and data of the library
|   +-- Memory regions managed by malloc/new/mmap or other allocators
|
+-- Shared virtual address space of the process (managed by the OS)
~~~

The blocks in the diagram represent **management roles**, not strictly separated physical memory partitions. For example, both the JVM and native libraries can request memory from the operating system. **Normal JNI/FFM calls do not create a new process**: they are calls across language and ABI boundaries within the same process. A pointer access bug in a native library can crash the entire JVM.

## 2. The JVM is the bridge between Java and the operating system

The execution flow is typically:

~~~text
NativeBridge.java
    -- javac --> bytecode (.class)
    -- JVM load/verify --> Interpreter or JIT
    -- call native method / foreign function -->
    compiled C/C++ library (machine code)
    -- return result --> Java
~~~

- **Java compiler (`javac`)** produces portable bytecode according to the JVM specification.
- **JVM** is responsible for object management, class loading, GC, Java threads, and verifying and executing bytecode; the JIT can compile hot code paths into machine code.
- **Native library** is compiled specifically per platform: Linux is usually `.so`, macOS is `.dylib`, Windows is `.dll`. A library may depend on the C runtime, system libraries, or other native libraries.
- **ABI (Application Binary Interface)** specifies how arguments are passed, how values are returned, data layout, calling conventions, and how function names appear at the machine-code level. Choosing the right ABI and CPU architecture is a prerequisite for safe native calls.

C++ libraries have name mangling and many compiler-dependent ABI characteristics. When stable interoperability from Java is needed, you should design a **C ABI function layer** (such as `extern "C"` functions) wrapping the C++ implementation; do not treat C++ method names or C++ object layouts as a stable interop interface.

## 3. How do Java heap and off-heap differ?

| Region/allocation type | Typical data | Lifecycle and responsibility |
| --- | --- | --- |
| **Java heap** | Object, array, String, `ByteBuffer` wrapper object | GC tracks object reachability; the main limit is usually related to `-Xmx`. |
| **Direct buffer** | Byte data of `ByteBuffer.allocateDirect(...)` | Usually uses native memory; the buffer object itself is still a Java object; reclaiming the native part is usually tied to reachability/cleaner, **with no guarantee of immediate release at the end of scope**. |
| **Native memory allocated by C/C++** | `malloc`/`free`, `new`/`delete`, regions from native libraries | The owner must free it using the proper API at the proper time; GC does not automatically know how to free arbitrary C/C++ pointers. |
| **FFM native segment** (JDK 22+) | `MemorySegment` allocated by `Arena` | `Arena` defines the lifecycle; the arena can be closed explicitly and invalidate the segment. |
| **Memory serving the JVM** | Metaspace, JIT code cache, thread stacks, GC structures | Managed by the JVM/runtime process; not identical to the Java heap. |
| **Memory-mapped file** | File region mapped through the OS | Can reside outside the Java heap; memory pages and data synchronization depend on the mapping mechanism and OS. |

**Off-heap** only means a storage region located outside the Java heap. It **does not mean** “outside the process”, “consumes no RAM”, “always faster”, “never indirectly affected by GC”, or “unlimited”. Virtual addresses, physical memory, memory-mapped file data, and RSS figures are different concepts.

In particular:

- `-Xmx` limits the maximum **Java heap**, not the entire process memory. The process can consume more than `-Xmx` due to thread stacks, metaspace, JIT, direct buffers, and native libraries.
- `-XX:MaxDirectMemorySize` is a limit related to the JVM's direct-buffer allocation (depending on the JVM/version); it is **not a ceiling for every `malloc` call from C/C++**.
- A Java object holding a reference to a native address only keeps the *wrapper* alive. If the native library has already `free`d that region, the reference does not make the memory valid again; conversely, forgetting to `free` can cause a native memory leak even when the Java heap is small.

## 4. Java 17+ example: direct `ByteBuffer` without writing custom JNI

Create the file `DirectMemoryDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class DirectMemoryDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocateDirect(8)
                .order(ByteOrder.nativeOrder());

        buffer.putInt(40);
        buffer.putInt(2);
        buffer.flip();

        int result = buffer.getInt() + buffer.getInt();
        System.out.println("direct=" + buffer.isDirect());
        System.out.println("sum=" + result);
        System.out.println("remaining=" + buffer.remaining());
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac DirectMemoryDemo.java
java DirectMemoryDemo
~~~

Stdout:

~~~text
direct=true
sum=42
remaining=0
~~~

Explanation:

1. `allocateDirect(8)` creates a buffer with a capacity of 8 bytes to hold two `int` values (4 bytes each); `isDirect()` reports that this is a direct buffer.
2. `order(ByteOrder.nativeOrder())` selects the byte order of the machine architecture. When exchanging data in practice, **both sides must agree on the byte order** rather than assuming “native” is the same on every machine.
3. `putInt` writes data, advancing `position`; `flip` switches the buffer from write mode to read mode by resetting `position` and `limit` appropriately.
4. The two `getInt` calls read the two values in order; 0 bytes remain readable within the current limit.
5. `clear()` (if called) only resets the buffer's logical pointers; **it does not erase the data and does not free the native part**. Nor should you hold onto a large direct buffer indefinitely just because only a few bytes are currently in use.

**When to use it?** Direct buffers are useful for certain native I/O paths, files/channels, or libraries that support direct buffers. They have higher allocation/deallocation overhead than heap buffers; measure the workload before concluding they are faster. If native code receives an address from a direct buffer, you must ensure the memory remains alive for the entire duration the native code uses it.

## 5. JNI: Java calling a C function in the same process

**JNI (Java Native Interface)** is the long-standing JVM interface that allows native code to interact with Java methods, objects, and arrays. Below is a standalone example on JDK 17+, requiring no frameworks.

Create `NativeBridge.java`:

~~~java
public class NativeBridge {
    static {
        System.loadLibrary("arithnative");
    }

    private static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println("2 + 3 = " + add(2, 3));
    }
}
~~~

Create `nativebridge.c`:

~~~c
#include <jni.h>
#include "NativeBridge.h"

JNIEXPORT jint JNICALL Java_NativeBridge_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
~~~

**Steps on Linux** (with JDK 17+ and a C compiler installed; `JAVA_HOME` pointing to the JDK directory):

~~~bash
javac -h . NativeBridge.java
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libarithnative.so nativebridge.c
java -Djava.library.path=. NativeBridge
~~~

Stdout:

~~~text
2 + 3 = 5
~~~

On macOS, use the file `libarithnative.dylib`, header directory `$JAVA_HOME/include/darwin`, and linker option `-dynamiclib`; on Windows, build `arithnative.dll` with an appropriate C toolchain and add `%JAVA_HOME%\include` and `%JAVA_HOME%\include\win32` to the include path. The exact file name is determined by the platform's `System.mapLibraryName(...)` rule.

**How the example works**:

1. `javac -h .` both compiles Java and generates the header file `NativeBridge.h` with the corresponding JNI declaration.
2. The JVM runs `System.loadLibrary("arithnative")` and searches for the native library according to its library loading mechanism, which includes the `java.library.path` configuration path.
3. Java calls `add(2, 3)`, and the JVM dispatches to the JNI entry point `Java_NativeBridge_add`; `jint` is JNI's 32-bit integer type.
4. The C function returns `5` to Java; the entire call happens in the same process. The example intentionally uses small numbers to avoid signed integer overflow issues on the C side.

**Why are `JNIEnv*` and `jclass` needed?** `JNIEnv*` provides the JNI function table for native code to access the JVM according to contract; the `jclass` parameter is the class of the `static` native method. For an instance native method, the second parameter is typically `jobject`.

**When using C++:** the generated JNI header includes appropriate C linkage guards when compiled under C++. Implementation code usually needs to clearly separate JNI-exported functions, handle C++ exceptions on the native side, and translate errors into Java exceptions or appropriate error codes; do not let C++ exceptions arbitrarily cross the JNI boundary.

## 6. Passing data across JNI: copying, pinning, and lifecycle

Calling a native method only passes arguments; **there is no zero-copy by default**. Typical approaches:

| Java data | How native code accesses it | What to watch out for |
| --- | --- | --- |
| `int`, `long`, `double`, and primitive types | Passed by JNI value such as `jint`, `jlong`, `jdouble` | Standard C types like `long` vary in size by platform; use JNI/fixed-width types. |
| `byte[]` / primitive array | JNI APIs such as `GetByteArrayElements`, `ReleaseByteArrayElements` | The JVM may **copy or pin**; you must release properly and must not assume the pointer stays valid forever. |
| `String` | JNI APIs for UTF or UTF-16 strings | Encoding and length conventions matter; `GetStringUTFChars` uses JNI's *modified UTF-8*, which is not identical to all standard UTF-8 data. |
| Direct `ByteBuffer` | `GetDirectBufferAddress` / `GetDirectBufferCapacity` when supported | Can access the data region directly; must keep the buffer and backing region valid throughout usage. |
| `jobject` | Local/global JNI references | Local references have their own lifecycle; to keep one longer, you must create and release a global reference using the proper API. |

Examples of **memory ownership**:

~~~text
Java byte[] -> JNI requests elements -> C processes
                                     -> JNI Release... -> Java continues

Java direct buffer -> native gets address -> C reads/writes
                   -> must keep backing memory valid
                   -> do not reuse address after lifetime ends

C malloc(...) -> native address -> Java wrapper holds handle
              -> native free(...) when done
              -> wrapper must not access the freed address again
~~~

In JNI, `JNIEnv*` is a thread-bound interface; do not share it arbitrarily across threads. A thread created by native code itself that wants to call JNI APIs must normally attach to the JVM first and detach when appropriate. When crossing JNI frequently with small amounts of data, call-transition overhead, copying/conversion, and synchronization can outweigh the native computation; measure total end-to-end time before optimizing.

## 7. FFM API from JDK 22: managing native memory with clearer lifecycle

The **Foreign Function & Memory API (FFM)** is a standard API in the `java.lang.foreign` package starting from **JDK 22** (JEP 454). FFM provides two groups of capabilities:

- **Foreign memory:** `MemorySegment` describes a memory region with size/bounds; `Arena` governs allocation, thread access permissions, and lifecycle.
- **Foreign function:** `Linker`, `SymbolLookup`, `FunctionDescriptor`, and method handles can be used to call native functions according to the appropriate ABI; certain operations related to native linkage are *restricted* and require configuring native access permissions according to the JDK/packaging method.

Example of managing **off-heap memory**, without compiling a C library, for **JDK 22+**. Create `ForeignMemoryDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ForeignMemoryDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            long size = 2L * ValueLayout.JAVA_INT.byteSize();
            MemorySegment data = arena.allocate(
                    size, ValueLayout.JAVA_INT.byteAlignment());

            data.setAtIndex(ValueLayout.JAVA_INT, 0, 40);
            data.setAtIndex(ValueLayout.JAVA_INT, 1, 2);

            int sum = data.getAtIndex(ValueLayout.JAVA_INT, 0)
                    + data.getAtIndex(ValueLayout.JAVA_INT, 1);
            System.out.println("sum=" + sum);
        }
    }
}
~~~

Run with JDK 22 or later:

~~~bash
javac ForeignMemoryDemo.java
java ForeignMemoryDemo
~~~

Stdout:

~~~text
sum=42
~~~

`Arena.ofConfined()` binds segment access permissions to the thread that created the arena; closing the arena at the end of `try-with-resources` invalidates the native segments managed by the arena and frees the memory according to contract. Access from the wrong thread, out of bounds, or after closing the arena is checked and rejected by the API; **this does not make arbitrary native code memory-safe**. Distinguish `MemorySegment.ofArray(...)` (whose data can live on the heap) from segments allocated by a native arena (off-heap).

When using FFM to **call C functions** from Java, you must accurately describe the function signature, struct layout, calling convention, symbol lookup, pointer lifecycle, and native access permissions. **Do not use JDK 22 FFM syntax in a project that only runs on JDK 17**; in JDK 17, `java.lang.foreign` is not yet a stable standard API.

## 8. Ownership, deallocation, and synchronization: three mandatory contracts

For Java and native code to share a memory region, there must be an explicit agreement:

1. **Ownership (who owns it):** Which side allocates, which side may read/write, and which side is responsible for freeing? A memory region must have a single deallocation rule or a clearly designed sharing rule.
2. **Lifetime (how long it lives):** May native code keep the address after the function returns? Is keeping the Java wrapper alive enough to protect the backing memory? After `free`/closing an `Arena`, all related pointers, views, or handles must be considered invalid.
3. **Concurrency (who may access concurrently):** If both Java and C/C++ modify the same memory region, there must be compatible synchronization and memory ordering mechanisms. Do not assume Java `volatile` is sufficient to synchronize all native accesses.

There is also **layout**: byte order, integer width, alignment, struct padding, null-termination, and string encoding. For example, the C `long` type can differ in size between 64-bit Windows and Linux; do not blindly map Java `long` to C `long`. For platform-independent data exchange, prefer fixed-size types and explicit layout descriptions.

Typical failure scenario:

~~~text
C malloc 100 bytes
   -> return address to Java
   -> C frees address
   -> Java calls native to read the old address again
   -> use-after-free: wrong data, crash, or memory corruption
~~~

This is a **native memory safety** bug; Java type checking and GC cannot save you once a native API allows using an address that is no longer valid. Conversely, failing to call `free` after the Java wrapper disappears can cause a **native memory leak**.

## 9. Choosing a technology for the problem

| Approach | Suitable when | Limitations to consider |
| --- | --- | --- |
| **Pure Java + heap objects/arrays** | Business logic, small/medium data, no OS API or native library needed | Depending on the I/O path, copying may occur; still measure actual performance. |
| **NIO direct `ByteBuffer`** | High-performance I/O or libraries accepting direct buffers; Java 17 compatibility needed | Lifecycle management is less explicit than arenas; allocation has overhead; no built-in interface to call C directly. |
| **JNI** | Integrating existing native libraries, callbacks/accessing Java objects, supporting older JDKs | Requires wrapper code and per-platform builds; prone to pointer, reference, copy/pin, and thread bugs. |
| **FFM (JDK 22+)** | Wanting to describe native memory/functions with a standard Java API and clear segment lifecycle | Must design ABI/layout/native access permissions accurately; native libraries can still cause dangerous errors. |
| **Separate native process + IPC/RPC** | Need to isolate crashes/failures and permissions of the native component | Has serialization, data transfer, and operational overhead; no longer an in-process call. |

**Choose off-heap for a measurable need** (I/O, native library interop, controlled large memory regions), not on the assumption that “if GC doesn't touch it, it's always fast”. When C++ integration is needed, design a small, stable C ABI interface and clearly document memory ownership in the API documentation.

## 10. Observing and diagnosing memory

Suppose an application sets `-Xmx512m`, yet the process RSS is much larger. This **does not by itself prove a Java heap leak**. Order of investigation:

1. Measure actual Java heap usage, thread count, and GC; compare against the `-Xmx` limit.
2. Check direct-buffer allocations, metaspace, code cache, and native/JVM memory; at the same time, monitor process memory from the OS.
3. If using JNI or C/C++ libraries with their own `malloc`, use an appropriate native profiler/leak detector; a Java heap dump may only show wrappers and miss native-allocated regions.
4. Review handle/buffer/arena lifecycles, call counts, error branches, and release timing.

For example, enable HotSpot's Native Memory Tracking when starting the application:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <PID> VM.native_memory summary
~~~

`<PID>` is the actual PID of the JVM process. **NMT has overhead and primarily tracks allocations managed by the JVM**; do not treat it as a complete measurement tool for every `malloc` made by C/C++ libraries. Combine it with OS metrics (RSS, mappings) and appropriate native analysis tools when needed.

Common symptoms:

| Symptom | Suspects to verify |
| --- | --- |
| `OutOfMemoryError: Java heap space` | Heap region or live objects exceed the limit/allocation capacity. |
| Message that a direct buffer cannot be allocated | Direct memory limit/pressure; buffers held too long, bursty allocations, or configured limit. |
| RSS grows while heap stays stable | Direct/off-heap/native allocations, thread stacks, mmap, runtime memory, or memory accounting. |
| `UnsatisfiedLinkError` | Wrong library path/name/symbol, missing native dependencies, wrong architecture/ABI, or linking error. |
| JVM crash with native signal or access violation | Bad pointer, buffer overflow, use-after-free, race condition, or native/JVM bug; inspect `hs_err_pid*.log` and native stack when available. |

`-Xcheck:jni` can help HotSpot detect **some** JNI usage errors; it is not a tool that proves all native code is safe.

## 11. Misconceptions to avoid

- **“The JVM is pure Java, so it has nothing to do with C/C++.”** False: JVM implementations contain native code and call many OS services through the runtime layer.
- **“Java calling C means spawning a separate C process.”** False for normal JNI/FFM: the library runs in the same process; IPC/RPC is the separate-process architecture.
- **“Everything outside `-Xmx` is a memory leak.”** False: the Java heap is only one part of process memory.
- **“Off-heap has no GC.”** C `malloc` regions are managed by C; however, a direct buffer can be reclaimed indirectly when its Java wrapper is no longer reachable. Distinguish these two mechanisms.
- **“Once you have a pointer, Java automatically guarantees safety.”** False: native APIs can bypass the protections normally seen in Java; you must check bounds, ownership, and lifetime.
- **“JNI arrays are always zero-copy.”** False: JNI may copy or pin depending on the API and JVM; you must release and measure performance.
- **“FFM replaces every reason to use JNI.”** Not quite: FFM supports native functions/memory with a standard API; JNI still has scenarios tightly coupled to JVM objects, VM tooling, and legacy integration.
- **“Use C++ directly just like calling a Java method.”** False: you need a bridge and contracts for ABI, mangling, layout, exceptions, and ownership.
- **“Just calling `free` is enough.”** False if buffers/views/pointers are still being used by another thread or Java wrapper; all uses must end before freeing.

## 12. Knowledge self-check

1. When `-Xmx` is set to 512 MB, why can the process RSS be 1 GB without necessarily having a heap leak?
2. In the `DirectMemoryDemo` program, does `flip()` modify the data, free native memory, or only change the read/write pointers?
3. Why can a JNI library crash the entire JVM process?
4. The C side returns a pointer allocated by `malloc`. What must the API documentation between C and Java specify at a minimum?
5. If native code needs to keep data after a JNI method returns, why must it not arbitrarily keep the `byte[]` address obtained via JNI?
6. What is the main difference between `ByteBuffer.allocateDirect` and `Arena.ofConfined` regarding the ability to proactively determine when validity ends?

**Reference answers:** (1) The JVM and native code also use memory outside the heap; (2) it only changes the position/limit state; (3) they share the same address space and a native pointer can be invalid; (4) ownership, lifetime, layout, errors, and synchronization; (5) JNI copy/pin and lifecycle are not guaranteed after release; (6) an arena is closed explicitly, whereas a direct buffer usually depends on the wrapper/cleaner lifecycle.

## 13. Standard references for deeper study

- Oracle JDK 17, `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Oracle, Java Native Interface Specification: https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html
- OpenJDK, JEP 454 – Foreign Function & Memory API (finalized in JDK 22): https://openjdk.org/jeps/454
- Oracle JDK 22, package `java.lang.foreign`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html

**Key takeaway:** The JVM executes Java code, uses native code to interact with the OS, and can directly call C/C++ libraries. The Java heap is managed by GC, while off-heap memory has multiple allocation/deallocation mechanisms. The safety and performance of the Java–native path depend on **ABI, data passing, ownership, lifecycle, and synchronization**.

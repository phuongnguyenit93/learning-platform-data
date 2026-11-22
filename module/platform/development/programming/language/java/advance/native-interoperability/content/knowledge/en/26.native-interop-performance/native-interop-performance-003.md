# Trade-offs of Copying, Array Pinning, Direct Buffers, and Off-Heap Allocation

## 1. The Performance Problem at the Java and Native Code Boundary

When Java exchanges data with a C/C++ library, the operating system, a driver, or a device via JNI, JNA, or the Foreign Function & Memory API (FFM), the data must reside in a memory region that the native side can validly access. The decision to **copy data**, **pin heap memory**, use a **direct buffer**, or use **off-heap allocation** affects transfer speed, GC latency, safety, and data lifecycle.

Imagine a Java application has a large **byte[]** and periodically passes it to C for compression or decoding. There are at least four designs:

1. **Copy:** copy bytes from the Java array into a native memory region; C works on the copy, then copies the result back when needed.
2. **Pin:** for a short duration, allow C to access the Java array's data without the JVM moving the associated memory region. JNI provides APIs to request array access, but **the JVM has the right to choose copying instead of pinning**; not every call can be assumed to be zero-copy.
3. **Direct ByteBuffer:** place data in a direct buffer so native code can access the memory address directly, while Java has a **ByteBuffer** object to read/write. If the original data still resides in a **byte[]**, the **put(byte[])** step is usually already a copy.
4. **Application-managed off-heap:** allocate native memory using a C/C++ library or FFM **Arena/MemorySegment** (standard API since Java 22), controlling size, alignment, ownership, and release timing.

**There is no single choice that is always fastest.** When payloads are small, the number of Java/native crossings and buffer preparation overhead can exceed the cost of copying. When data is large, reusing a memory region multiple times can save copy bandwidth. When GC is sensitive to tail latency, avoiding prolonged pinning can be more important than saving one copy pass. When native code operates asynchronously, memory lifecycle management often determines correctness before it determines speed.

### 1.1. Four Questions to Answer Before Optimizing

- **Where is the data produced?** If the input is a heap **byte[]**, creating a direct buffer and calling **put** does not eliminate the first copy. If a network/native API writes directly into a direct buffer, a heap staging step can be avoided.
- **Who owns and is allowed to modify the data?** A copy creates an independent snapshot; a shared memory region requires conventions on read/write timing and synchronization.
- **How long does native code hold the pointer?** Is it used only during a synchronous call, or retained after JNI/FFM returns, running on another thread, or in a delayed callback?
- **Which metric needs to be optimized?** Throughput, median latency, p99 latency, bytes copied, GC pauses, native RSS, allocation rate, or safety level? A benchmark that only measures native loop time does not answer enough.

## 2. Memory Map and Comparison Table

**Java Heap:** arrays like **byte[]** are managed by the JVM and the GC can move objects. C cannot arbitrarily store a heap address permanently. JNI must use the appropriate APIs; JNI object references are also not direct C pointers to the data region.

**Native/off-heap memory:** typically resides outside the Java heap, with an address suitable for passing to C APIs. It is not subject to movement by the Java GC, but still consumes RAM and can cause **OutOfMemoryError** or native allocation failures. Address validity depends on the owner and the time of deallocation.

| Technique | Typical Trade-off / Cost | Strengths | Risks or Limitations |
| --- | --- | --- | --- |
| **Region copying** via **GetByteArrayRegion/SetByteArrayRegion** | Copy cost proportional to data size; may need a staging area | Clear exchange boundary; does not hold heap pointer for long; easy to chunk | Repeated copying; must determine copy-back and state |
| **GetByteArrayElements/ReleaseByteArrayElements** | JVM may copy or pin; acquire/release overhead | Convenient API when a temporary C pointer is needed | No guarantee of pinning; requires release; GC and copy-back depend on branch |
| **GetPrimitiveArrayCritical/ReleasePrimitiveArrayCritical** | Strict restrictions inside the critical region | Can allow heap access with low overhead | May still copy; holding too long can hinder GC; cannot block or make other JNI calls in the region |
| **ByteBuffer.allocateDirect** | Allocation/reclamation is usually more expensive than heap buffers; Java access cost may differ | Useful for direct native I/O and buffer reuse | Reclamation lifecycle is tied to GC, cannot be treated as instant close; still copies if source is heap |
| **Native malloc/free or self-managed wrapper** | Manual allocation, pointer management, and cleanup | Ownership, alignment, and protocol with C libraries can be very flexible | Leaks, double-free, use-after-free, or overflow can crash the JVM |
| **FFM Arena/MemorySegment** (Java 22+) | Scope/bounds/lifetime check overhead and ownership design | Native region with clear lifecycle; Java checks bounds and scope on MemorySegment operations | A pointer already handed to C is not automatically blocked by Java if C accesses it after the arena closes |

Distinguish **zero-copy at the Java/native boundary** from **zero-copy across the entire data path**. A direct buffer can avoid copying at a specific JNI API, but there may still be copies from a decoder into the direct buffer, from user-space to kernel, or performed by a driver/library. A value of **isDirect() = true** only describes the buffer type; it does not prove the final I/O path is copy-free.

## 3. Copy: Paying Bandwidth Cost for a Clear Data Boundary

Copying is often simpler than pinning when native code processes for a long time or retains data after the Java call. After copying, the heap array can be moved by the GC, while native code works on its own memory region. If native code only reads, no copy-back is needed. If native code writes results, you must decide whether to copy back the entire region or only the modified bytes.

### 3.1. JNI Region API

**GetByteArrayRegion(env, array, start, len, dst)** transfers a slice of a Java array into a **dst** region provided by C; **SetByteArrayRegion** transfers in the reverse direction. Functions of the form **Get/Set<Type>ArrayRegion** exist for the corresponding primitive types. They are suitable when you want to transfer a clearly bounded range of data and do not need to keep a pointer tied to the Java array.

Example of a chunked read flow:

~~~text
byte[] (Java heap) ---> JNI GetByteArrayRegion ---> staging buffer (C)
                                                    |
                                                    +--> native processes chunk by chunk
                                                    |
                                          no pointer held to heap
~~~

The advantage of the region API is avoiding holding a **Get...Elements/Release...Elements** pointer pair across multiple error branches, especially when the application already needs to copy into a native region. Do not infer that region is faster in every case: when copying many times or executing very many small JNI calls, the overhead can be large.

**Chunk size** is a benchmark parameter: too small a chunk wastes crossings and loop iterations; too large a chunk increases footprint, cache pressure, and per-step latency. If the protocol supports streaming, processing chunk by chunk can avoid holding all the data at once.

### 3.2. JNI Elements API May Copy or Pin

**GetByteArrayElements** returns a **jbyte\***, but the JVM is allowed to provide either a copy or a pointer to a stabilized array. The **isCopy** parameter (if provided) can help observe the mechanism a call used; it is **not an option that forces the JVM to pin**. **ReleaseByteArrayElements** is the mandatory part to release resources or synchronize results.

Release modes:

- **mode = 0:** if there is a copy, copy changes back to the original array and then free the copy; if pinned, end access according to the JVM's mechanism.
- **JNI_ABORT:** do not copy back the copy; suitable if native code only reads. **Do not treat JNI_ABORT as a rollback of changes** if the pointer actually points directly to a pinned array, because modifications to the original memory may have already occurred.
- **JNI_COMMIT:** if there is a copy, commit results back to the array but **do not free the copy yet**; a proper final release must still be performed. Do not use it in place of a terminating release.

For read-only code, **JNI_ABORT** can avoid unnecessary copy-back. For mutating code, choose explicit copy-back, handle error cases, and avoid holding pointers past the point where native ownership is no longer defined.

### 3.3. When Copying Is Better Than Pinning

Copying is a reasonable choice if native code will block on file/network reads, perform long GPU/driver calls, call back into Java, dispatch work to other native workers, or retain data across multiple requests. Although copying costs bandwidth, it decouples the native lifecycle from the JVM heap. Some designs copy once into a **reusable native region** and perform thousands of operations on it; the total cost can even be lower than many short pins.

## 4. Pinning and JNI Critical Regions: Saving Copies May Trade Off GC Latency

### 4.1. GetPrimitiveArrayCritical Does Not Guarantee No-Copy

**GetPrimitiveArrayCritical** and **ReleasePrimitiveArrayCritical** create a critical region for a primitive array. The JVM may provide a direct pointer **if possible**, but still reserves the right to use a copy. You must not assume **isCopy == JNI_FALSE** across all JVMs, collectors, array types, and heap states.

Important constraints while holding a critical pointer:

- Native code **must not run for long** before releasing.
- **Do not call other JNI functions** inside the critical region.
- **Do not make system calls that can block waiting for another Java thread**, such as reading a stream whose data is supplied by another Java thread.
- Avoid lock contention, unbounded I/O, Java callbacks, sleep, or calling libraries with unknown execution time.

These restrictions exist because the JVM may need to defer certain GC activities or incur other pinning costs. Prolonged pinning degrades throughput and especially the **tail latency** of the entire application; the exact impact varies by JVM/GC. Even when using a collector that supports pinning efficiently, the critical region must still be kept **short and with a measurable maximum duration**.

### 4.2. Proper Ordering Sketch for Using the JNI Critical API

This is **a C fragment inside a JNI native method**, illustrating a very short summation. It is **not a standalone C program**; the **env** and **input** variables are existing JNI parameters, and **GetArrayLength** is called **before** entering the critical region:

~~~c
jsize n = (*env)->GetArrayLength(env, input);
jbyte *p = (*env)->GetPrimitiveArrayCritical(env, input, NULL);
if (p == NULL) {
    return 0; // JNI may have thrown OutOfMemoryError.
}

jlong sum = 0;
for (jsize i = 0; i < n; ++i) {
    sum += (unsigned char)p[i];
}

(*env)->ReleasePrimitiveArrayCritical(env, input, p, JNI_ABORT);
return sum;
~~~

Inside the region, only a non-blocking C loop and **ReleasePrimitiveArrayCritical** are executed; no auxiliary JNI calls are made. In production, for very large arrays or loops with unpredictable duration, you should split the work or use copy/direct/off-heap instead of holding a prolonged critical region.

**Systematically optimizing with pinning:** record critical region duration, p99/p999 GC pauses, GC frequency, allocation pressure, and overall efficiency. Looking only at the throughput of a single native thread can miss its impact on other Java threads.

## 5. Direct ByteBuffer: Stable Address for Native, Yet Still Has Costs and Ownership

### 5.1. Mechanism

**ByteBuffer.allocateDirect(size)** creates a **direct ByteBuffer**; the backing data is typically in native memory outside the Java heap. Java still keeps a ByteBuffer object on the heap to manage read/write positions (**position**, **limit**, **capacity**) and the reference to the memory region. JNI has **GetDirectBufferAddress** and **GetDirectBufferCapacity** to inspect/access the direct data region if supported by the JVM.

- **GetDirectBufferAddress** returns the starting address of the passed buffer's backing region; it **does not automatically add the Java position**. When processing a valid range, pass **offset** and **length** separately, or use **slice()** and re-establish the view's offset.
- **GetDirectBufferCapacity** reports **capacity**, not **remaining()** or the business boundary (**limit**). Native code must check **offset >= 0**, **length >= 0**, **offset + length <= capacity**, while the Java caller must maintain the valid data window.
- **GetDirectBufferAddress** can return NULL and **GetDirectBufferCapacity** can return -1 for non-direct buffers or JVMs that do not support JNI direct-buffer access. Do not dereference if the check fails.
- **ByteBuffer** has mutable state. **duplicate()** creates an independent position/limit but **shares the backing content**, without cloning the data. Multiple threads reading/writing the backing memory concurrently require synchronization conventions.
- The default byte order of a new ByteBuffer is **BIG_ENDIAN**; when sharing multi-byte integers or C structs, explicitly decide byte order, alignment, padding, and ABI. **order(ByteOrder.nativeOrder())** does not automatically guarantee that a C struct layout is mapped correctly.

If native code processes the same payload multiple times, a direct buffer can reduce copying on subsequent JNI calls. If all the data was just created in a **byte[]**, **direct.put(array)** still copies from the heap into the direct buffer. If the result must return to a **byte[]**, **direct.get(array)** copies back again. The optimal approach is to design the entire pipeline so that data is produced, transformed, and consumed in the appropriate memory region, with minimal format/ownership transitions.

### 5.2. Reusing Direct Buffers and Managing Capacity

Creating and destroying a direct buffer for every small item is rarely worthwhile. Direct buffer allocation/cleanup is usually more expensive than for heap buffers, whereas a buffer pool can reduce allocation churn. However, an oversized or unbounded pool increases native memory/RSS, fragmentation, and the lifetime of sensitive data. You can choose a pool with a **maximum size**, a concurrency-limiting policy, proper **clear()/flip()** resets, and avoid returning a buffer to the pool while native code is still using its address.

Do not let native code keep a pointer after Java has dropped the managing buffer reference or returned the buffer to a pool for another request. If the native call is asynchronous, you must maintain a **strong reference** and an in-use state until native confirms completion; **Reference.reachabilityFence** can help keep reachability within a synchronous scope, but **does not make a pointer stored indefinitely in native code valid**.

**NewDirectByteBuffer(env, address, capacity)** is the reverse direction: JNI creates a Java view over an existing native region. This Java view **does not implicitly own and automatically free** C-allocated memory. The party that allocates the memory must define when it is freed; accessing the view after free can corrupt the JVM process.

## 6. Off-Heap Allocation: Lifecycle Control and Implementation Cost

### 6.1. JNI with malloc/free or C/C++ Libraries

C can allocate using **malloc**, a custom allocator, or a device API and return a handle to Java. This model is convenient when native code retains data across multiple calls, but it requires an ownership protocol: which function creates the handle, which function closes it, whether it can be shared across threads, whether it can be canceled mid-flight, and whether it can be reallocated while a Java view is still alive.

A **long** handle is just a number holding an address or token; it **does not protect against use-after-free**. Do not arbitrarily cast any Java long value to a pointer and dereference it. Production APIs need to check that the handle is still alive, enforce data bounds, guard against double-close, and clearly define how to handle native task failures before close.

If using a C-created direct ByteBuffer, the ownership descriptor must live alongside a Java wrapper, such as a **NativeBuffer** object with **close()** that ensures native workers have finished before freeing. A **Cleaner** can serve as a last-resort safety net, **not a replacement for deterministic close**.

### 6.2. Java 22+: FFM MemorySegment and Arena

The **Foreign Function & Memory API** became a standard API in **Java 22**. Earlier Java releases used different incubating/preview APIs; for example, **java.lang.foreign.Arena** below requires **JDK 22+** and cannot be compiled with JDK 17 just by adding an import.

- **Arena.ofConfined():** memory is accessed/closed by the owning thread; suitable for a synchronous native call with a clear scope.
- **Arena.ofShared():** allows sharing segments across threads, but the user must still synchronize and ensure all operations using the pointer have finished before closing.
- **Arena.ofAuto():** lifetime is determined by reachability; there is no explicit close, so reclamation timing is non-deterministic.
- **Arena.global():** has an unbounded lifetime until process termination; unsuitable for accumulating per-request allocations without a management strategy.

**MemorySegment** provides address bounds checking, layout-based alignment, scope-based accessibility, and lifetime checks for Java operations through this API. **It is not a sandbox protecting C**: if a raw pointer already passed to native code is accessed after the arena closes, native code can still cause severe errors despite Java having marked the segment expired.

**MemorySegment.ofArray(byte[])** is a segment backed by the Java heap, **not the same as** an off-heap segment allocated by an Arena. When using FFM downcalls and pointer parameters, you must follow the heap/native-address rules of the linker and specific API; do not treat a Java heap segment as a stable native address just because it has a MemorySegment view.

### 6.3. Choosing an Allocation Type by Lifecycle

| Actual Lifecycle | Usually Reasonable Solution |
| --- | --- |
| Small buffer, primarily Java processing | **byte[]** or heap ByteBuffer; copy if native needs it |
| Native needs direct access across multiple synchronous calls | Reusable direct ByteBuffer with bounds and ownership |
| Single native call with short-lived scratch memory | FFM **Arena.ofConfined()** on JDK 22+, closed after the call completes |
| Multiple native worker threads sharing a memory region | **Arena.ofShared()** or C-owned region with synchronization and join before free |
| Native library allocates and returns a handle | AutoCloseable wrapper + library's **destroy** API, ensuring no Java view outlives free |
| Native code may block indefinitely or crash | Consider isolating in another process; direct/off-heap cannot handle untrusted/unreliable native code |

## 7. Complete Java 17 Example: Seeing the Exact Copies Into and Out of a Direct Buffer

The following example runs **without a native library**. It demonstrates that creating a direct buffer does not automatically move the original payload off-heap for free.

~~~java
// BufferTransferDemo.java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferTransferDemo {
    public static void main(String[] args) {
        byte[] payload = "JNI FFM".getBytes(StandardCharsets.US_ASCII);
        ByteBuffer heap = ByteBuffer.wrap(payload);
        ByteBuffer direct = ByteBuffer.allocateDirect(payload.length);

        // Copy 1: Java heap -> direct buffer (typically off-heap).
        direct.put(payload);
        direct.flip();

        // A JNI function can read the direct region directly at this step.
        // Java copies it back here to illustrate the data path.
        byte[] received = new byte[direct.remaining()];
        direct.get(received); // Copy 2: direct buffer -> Java heap.

        System.out.println("heap direct = " + heap.isDirect());
        System.out.println("native direct = " + direct.isDirect());
        System.out.println("round trip = "
                + new String(received, StandardCharsets.US_ASCII));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac BufferTransferDemo.java
java BufferTransferDemo
~~~

Exact stdout:

~~~text
heap direct = false
native direct = true
round trip = JNI FFM
~~~

In a pipeline that uses direct buffers **end-to-end**, both illustrated copies can be eliminated if both the data producer and the consumer operate on the direct region. If Java still needs to process the data as a **byte[]**, the conversion cost must be included in the benchmark. Reuse sufficiently large direct buffers, but do not reuse them concurrently for another request while native code is reading/writing.

## 8. End-to-End JNI Example: Comparing Region, Elements, and Direct Buffer

This example uses **Java 17 + JNI + C11 on Linux**, performing the same byte summation via three different entry points. The results are identical; the code **does not prove which approach is faster**. When benchmarking, you must measure the different costs using a real workload.

**File NativeMemoryTradeoff.java**:

~~~java
import java.nio.ByteBuffer;

public final class NativeMemoryTradeoff {
    static {
        System.loadLibrary("memorytradeoff");
    }

    private static native long sumWithRegion(byte[] input);
    private static native long sumWithElements(byte[] input);
    private static native long sumDirect(ByteBuffer input, int offset, int length);

    public static void main(String[] args) {
        byte[] input = {1, 2, 3, 4};

        ByteBuffer direct = ByteBuffer.allocateDirect(input.length);
        direct.put(input); // This is still a heap -> direct copy.
        direct.flip();

        System.out.println("region=" + sumWithRegion(input));
        System.out.println("elements=" + sumWithElements(input));
        System.out.println("direct=" + sumDirect(
                direct, direct.position(), direct.remaining()));
    }
}
~~~

**File memorytradeoff.c**:

~~~c
#include <jni.h>
#include <stdint.h>

static void illegal_argument(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalArgumentException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
    }
}

/* Choose to copy data from Java in 256-byte stack chunks. */
JNIEXPORT jlong JNICALL
Java_NativeMemoryTradeoff_sumWithRegion(
        JNIEnv *env, jclass ignored, jbyteArray input) {
    (void)ignored;
    jsize length = (*env)->GetArrayLength(env, input);
    jlong sum = 0;
    jbyte chunk[256];

    for (jsize start = 0; start < length; ) {
        jsize count = length - start;
        if (count > 256) {
            count = 256;
        }
        (*env)->GetByteArrayRegion(
                env, input, start, count, chunk);
        if ((*env)->ExceptionCheck(env)) {
            return 0;
        }
        for (jsize i = 0; i < count; ++i) {
            sum += (unsigned char)chunk[i];
        }
        start += count;
    }
    return sum;
}

/* JVM may copy OR pin. Release with JNI_ABORT since it is read-only. */
JNIEXPORT jlong JNICALL
Java_NativeMemoryTradeoff_sumWithElements(
        JNIEnv *env, jclass ignored, jbyteArray input) {
    (void)ignored;
    jsize length = (*env)->GetArrayLength(env, input);
    jbyte *pointer = (*env)->GetByteArrayElements(
            env, input, NULL);
    if (pointer == NULL) {
        return 0; // For example, JNI may have thrown OutOfMemoryError.
    }

    jlong sum = 0;
    for (jsize i = 0; i < length; ++i) {
        sum += (unsigned char)pointer[i];
    }
    (*env)->ReleaseByteArrayElements(
            env, input, pointer, JNI_ABORT);
    return sum;
}

/* Access backing memory directly if the JVM supports it. */
JNIEXPORT jlong JNICALL
Java_NativeMemoryTradeoff_sumDirect(
        JNIEnv *env, jclass ignored, jobject buffer,
        jint offset, jint length) {
    (void)ignored;
    unsigned char *base = (unsigned char *)
            (*env)->GetDirectBufferAddress(env, buffer);
    jlong capacity = (*env)->GetDirectBufferCapacity(env, buffer);

    if (base == NULL || capacity < 0 ||
            offset < 0 || length < 0 ||
            (jlong)offset + (jlong)length > capacity) {
        illegal_argument(env, "Invalid direct buffer window");
        return 0;
    }

    jlong sum = 0;
    for (jint i = 0; i < length; ++i) {
        sum += base[offset + i];
    }
    return sum;
}
~~~

On **Linux**, set **JAVA_HOME** to a JDK 17+ directory containing **include/jni.h** and install the GCC compiler. In the same directory containing the two source files:

~~~bash
javac -h . NativeMemoryTradeoff.java
gcc -std=c11 -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  memorytradeoff.c -o libmemorytradeoff.so
java -Djava.library.path=. NativeMemoryTradeoff
~~~

Stdout on a JVM supporting JNI direct buffers:

~~~text
region=10
elements=10
direct=10
~~~

**Why this example is valuable:** region transfers data in C chunks; elements uses a pointer that the JVM may provide via copy or pin; direct lets JNI sum directly over the ByteBuffer's backing memory. **direct.put(input)** on the Java side is still a copy, so if a benchmark only measures **sumDirect** while omitting the cost of **put**, the end-to-end conclusion will be wrong. All three functions execute synchronously and do not retain pointers after returning. You must not turn **base** into a global variable and use it after Java has discarded the buffer.

In this JNI code, **sumDirect** checks the backing region size (**capacity**), but the Java caller is also responsible for ensuring **offset, length** match a meaningful data window (**position, limit**) and are not modified mid-flight by another thread. For data beyond this small example, summing with **jlong** is only valid within non-overflowing ranges; overflow/result semantics must be designed according to actual requirements.

## 9. FFM Example on Java 22+: Arena and Scope-Based Deallocation

The snippet below is a **standalone program for JDK 22+** using the standard **java.lang.foreign** API; it does not call native functions so no linker configuration is needed. FFM downcalls require checking the JDK/module native access permissions and the corresponding **--enable-native-access** flag.

~~~java
// NativeArenaDemo.java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class NativeArenaDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment region = arena.allocate(
                    ValueLayout.JAVA_LONG.byteSize(),
                    ValueLayout.JAVA_LONG.byteAlignment());
            region.set(ValueLayout.JAVA_LONG, 0, 42L);

            System.out.println("bytes=" + region.byteSize());
            System.out.println("value=" + region.get(
                    ValueLayout.JAVA_LONG, 0));
        }
        // Scope ends: region is no longer valid for Java access.
    }
}
~~~

Commands with JDK 22+:

~~~bash
javac NativeArenaDemo.java
java NativeArenaDemo
~~~

Stdout:

~~~text
bytes=8
value=42
~~~

**Do not close the arena before native code finishes using it.** If you pass an address from a segment to an **asynchronous** native call and exit the **try** block, C may still access the pointer after the memory has been freed. To use a shared arena or keep a region longer, you must have a completion notification mechanism, join/cancel, cross-thread access rules, and deterministic cleanup.

## 10. Cost Model: Looking at the Whole Data Path Instead of One Copy

A useful mental formula:

**Total time ≈ crossing cost + allocation/reclamation cost + total copy cost + native processing time + synchronization/cache cost + GC impact.**

For a copy of size **N** and effective bandwidth **B**, the ideal component is roughly **N/B**, but in practice it depends on cache, NUMA, parallelism, memory type, copy method, and machine state. Therefore, do not use a fixed threshold like "above 4 KB always choose direct" for every application.

In practice, different scenarios arise:

| Scenario | Initial Decision to Try | Reason |
| --- | --- | --- |
| Very small payload, infrequent native calls | **byte[] + region/Elements** with proper release | Direct/arena allocation and lifecycle management can be more expensive than a copy |
| Large payload, fast native read, Java does not need a snapshot | Benchmark **reusable direct** vs. **Elements** | Copy savings can be significant if producer/consumer work directly on that region |
| Long native processing, waiting on I/O or callbacks | **Copy to a native region with its own owner**, or direct/off-heap with a lifetime contract | Avoids holding an array critical while blocking and avoids long-lived heap pointers |
| Thousands of small native calls per request | Batch if the API allows | Reducing crossing overhead can be more effective than trading copy for pin |
| Native returns a C-owned block as result | Wrapper + owner/close; consider **NewDirectByteBuffer** or MemorySegment view | Avoids copy-back when Java can process directly, but must manage free |
| Multiple threads accessing concurrently | Per-thread buffer or synchronized shared memory | Avoids data races and reusing a buffer while a call is still running |
| p99 priority, GC-sensitive | Measure **critical-region duration** and GC pauses; consider copying | A small copy can trade for more stable latency |
| Limited memory, high load | Bounded direct/off-heap pool and in-flight limit | Excessive native memory can get the process killed even while Java heap has room |

**Measure data conversion separately**: if a native library expects a C struct that requires packing fields from Java objects, serialization, byte order conversion, alignment, and allocation costs still exist even if the buffer is direct. "No byte copying" does not mean "no data conversion".

### 10.1. CPU and GC Considerations

- **Cache locality:** continuously copying data can evict useful data from cache, yet an optimized sequential copy can also be faster and simpler than many scattered accesses.
- **Allocation frequency:** per-request direct allocation can increase native memory pressure and prolong reclamation; reusing buffers is often helpful, but the pool must be bounded.
- **GC interference:** pinning can hinder object relocation/collection depending on the JVM and collector; the key metric is **GC pause p99**, not just average JNI call time.
- **Thread contention:** a shared direct buffer is not automatically thread-safe; data races or lock contention can wipe out any copy-reduction benefit.
- **Native library internals:** the library may copy data itself or allocate internal buffers. Benchmarking only the Java wrapper without looking end-to-end will miss those costs.

## 11. Using Resources Safely: Ownership Matters More Than Micro-Optimization

An ownership table should be written explicitly in the API design:

| Memory and API | Who Allocates? | When Is It Freed? | Unsafe Cases |
| --- | --- | --- | --- |
| **byte[]** + **GetByteArrayElements** | JVM owns the array; JNI may create a copy | Release pointer using the proper JNI API; Java GC manages the array | Holding pointer after release; forgetting release; native using array outside contract |
| **GetPrimitiveArrayCritical** | JVM | Release critical immediately after short processing | Performing I/O or long locks while critical |
| **ByteBuffer.allocateDirect** | JVM/NIO direct buffer | When the buffer's management mechanism determines it can be reclaimed; timing should not be assumed immediate | Async native holding address with no Java owner left; returning buffer to pool too early |
| **malloc + NewDirectByteBuffer** | C library / native owner | Native owner frees after all views/calls complete | Java view still accessing after free |
| **FFM Arena.ofConfined/ofShared** | Arena | When closed after all tasks using the segment have finished | Closing while C still holds pointer; accessing from wrong thread in confined arena |

When native processing is asynchronous, a good flow is usually **allocate → submit → native acknowledgment → release**. A caller-side timeout only means the caller stops waiting; it does not allow automatically freeing memory that a native worker is still using. If the library does not support reliable cancel/join, consider isolating it in another process. Do not arbitrarily try to kill a C thread while it holds pointers/locks.

**Native memory is not free just because it is off-heap.** The **-Xmx** limit primarily controls the Java heap, not total RSS. **-XX:MaxDirectMemorySize** primarily applies to JVM-tracked NIO direct-buffer allocations, not as an absolute cap on third-party **malloc** or all FFM allocations. Java object wrappers, metadata, thread stacks, code cache, and other native regions still consume memory.

**Useful measurements:** Java heap used, direct buffer count/total capacity/memory used via **BufferPoolMXBean** or JMX, native memory tracking (NMT) if enabled, RSS/container memory, GC pauses, native allocation count/size, number of unclosed pointers/handles, and number of running native tasks. NMT does not necessarily record all manual allocations by libraries outside the JVM. Do not mechanically add metrics from different frames of reference to infer total footprint.

## 12. Benchmarking Properly to Choose a Strategy

A valid comparison requires **the same workload, the same payload, and the same level of correctness**:

1. **Identify the real data path:** is the source Java heap, network, mapped file, or native allocator? Is the result used further in Java or in C? How many native calls occur per payload?
2. **Define four approaches:** copy via region, Elements (may copy/pin), critical region **only when processing is short and valid**, and direct/off-heap reuse. Do not assume the Elements approach will definitely pin.
3. **Measure end-to-end and per component:** allocation, heap-to-direct staging, JNI crossing, native work, copy-back, cleanup; separate initial pool creation time from steady-state performance.
4. **Use JMH or a reliable harness:** warm up JVM/JIT, run enough iterations and multiple forks; prevent dead-code elimination by consuming results. When measuring JNI/GC, observe metrics from both native and the whole JVM.
5. **Vary data and concurrency:** multiple payload sizes (small/medium/large), worker counts, call frequencies, batch sizes, and direct memory pressure levels; use realistic data rather than overly cache-friendly cases.
6. **Monitor latency and resources:** throughput, p50/p95/p99, allocation/GC, RSS/direct capacity, pool exhaustion, native memory errors; run sustained tests to detect leaks.
7. **Verify correctness:** checksum/byte-by-byte with inputs containing negative bytes per Java signed byte semantics, in-place modification and copy-back, boundary offset/length, concurrent access, lifetime, and cancel operations.

**Do not use** a **System.nanoTime()** loop run a few times to draw general conclusions. Do not compare a **sumDirect** function that omits **direct.put(byte[])** against **sumWithRegion** that includes the full copy; that measurement compares two different pipelines. Do not interpret **isCopy** on one test machine as a guaranteed behavior across other JVMs/GCs.

When changing collectors or JDK versions during benchmarks, re-verify pin/GC assumptions: the JNI API itself does not guarantee a fixed memory access strategy across all implementations. With FFM, also check the JDK version and native access options when testing downcalls.

## 13. Common Mistakes

| Misconception / Practice | Why It Is Wrong or Dangerous | How to Fix |
| --- | --- | --- |
| "**GetByteArrayElements** is always zero-copy" | The JVM may create a copy | Read the JNI contract, check and release properly, benchmark |
| "**GetPrimitiveArrayCritical** always pins" | JNI may still return a copy | Do not rely on pinning for correctness and keep the region extremely short |
| Reading files/network inside a critical region | Can block and impede GC | Copy to a native region or direct buffer before doing I/O |
| **Get...Elements** without **Release** | Resource leak or prolonged pinning | Use cleanup paths covering all branches |
| Using **JNI_ABORT** to undo writes already made | If the pointer pinned the real array, the data was already modified | Do not write to read-only regions; use a separate copy when rollback is needed |
| "**allocateDirect** = no copy from **byte[]**" | **put(byte[])** still performs a copy | Account for all steps from source to destination |
| Confusing **capacity** and **remaining** | Native code may process bytes outside the valid window | Pass offset/length and validate bounds |
| Keeping a native address after returning buffer to pool | Another request may overwrite it or the buffer may be reclaimed | Ownership/lease and native completion acknowledgment |
| Freeing C malloc while a **NewDirectByteBuffer** view is still in use | Dangling pointer / use-after-free | Define owner and close after all views are done |
| Closing an FFM arena while a native worker has not finished | Java scope checks do not protect C from a dead pointer | Await/join/cancel first, then close |
| Creating unbounded direct buffers, only watching **-Xmx** | Off-heap RSS grows uncontrollably | Bound pool/direct memory, measure RSS and BufferPoolMXBean |
| Sharing a ByteBuffer with mutable position across threads | Data race on position/limit and backing memory | Per-thread view with synchronization, or explicitly allocate separate regions |
| Benchmarking JNI alone while omitting staging/cleanup | Wrong conclusions for the real pipeline | Measure end-to-end, GC tail latency, and footprint |

## 14. Implementation Decision Checklist

Before switching **byte[]** to pinning, direct buffers, or off-heap memory, verify:

- **Source, destination, and format:** is data on heap or native from the start; are there extra copy/serialization steps?
- **Duration native holds the data:** within a short JNI call or asynchronous, waiting on I/O, holding pointers long-term?
- **Ownership protocol:** who allocates, who frees, when is completion confirmed, can the handle be double-closed?
- **Data modification semantics:** is native read-only or does it need copy-back; are **JNI_ABORT**, **JNI_COMMIT**, **mode 0** chosen appropriately?
- **GC constraints:** is the critical region strictly short, non-blocking, and free of other JNI calls?
- **Window and layout:** are position/limit/capacity, byte order, padding, alignment, bounds, and pointer width consistent?
- **Performance measurement:** do you have actual p95/p99, throughput, copy bytes, memory footprint, and GC results?
- **Resource limits:** is the direct/off-heap pool bounded with cleanup, and does async native have acknowledgment?
- **Version portability:** direct ByteBuffer/JNI work on Java 17+, FFM Arena/MemorySegment are standard from Java 22; have you checked native access requirements for the target JDK?
- **Is the simpler approach good enough?** If copying already meets latency/throughput and is safe, do not add complex ownership just for an unmeasured zero-copy promise.

**Technical conclusion:** copying consumes bandwidth but creates a clear ownership boundary; pinning can reduce copying but must not be held long or relied upon as a guarantee; direct buffers reduce staging at some I/O boundaries when reused properly; off-heap/FFM enables active native memory management but places lifecycle responsibility on the design. A good decision is based on **the entire pipeline, pointer safety, and actual benchmark results**, not on API names alone.

## 15. Standard Reference Documentation

- [JNI Specification — Array Access, GetPrimitiveArrayCritical and Release modes](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/functions.html)
- [JNI Specification — NIO direct buffer access](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Java 17 ByteBuffer API — direct vs non-direct](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java 22 java.lang.foreign API — MemorySegment and Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [Java 17 java launcher — MaxDirectMemorySize](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)

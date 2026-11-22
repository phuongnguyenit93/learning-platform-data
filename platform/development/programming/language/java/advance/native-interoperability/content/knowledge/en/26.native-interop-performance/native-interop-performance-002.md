# Batching Work to Reduce JNI, Downcall, and Callback Counts

## 1. Why Does Batching Work Help Optimize Java/Native Interop?

Java can call C/C++ using **JNI (Java Native Interface)** or using a **downcall** of the Foreign Function & Memory API (FFM). In the reverse direction, native code calls Java via a JNI callback or an **FFM upcall stub**. When processing a large number of very small elements, crossing the Java/native boundary many times can incur a relatively high cost compared to the operation itself.

A crossing may include preparing the signature/arguments and result according to the ABI, switching the JVM/native execution context, checking state/lifetime, accessing arrays/objects, copying data (if needed), dispatching callbacks, and handling errors. The actual cost depends on the JVM, API, CPU, JIT, function signature, data state, and workload; there is no constant "JNI takes X ns" that holds true for every environment.

Example of two ways to process 10,000 integers:

```text
Individual calls:
Java ──transformOne(x0)──► C ──result──► Java
Java ──transformOne(x1)──► C ──result──► Java
... total 10,000 Java → C calls

Batching:
Java ──transformBatch(int[10_000])──► C
                    C loops to process 10,000 elements
Java ◄────────────── result array ──── C
... total 1 Java → C call
```

Both can perform the same 10,000 computations. The batching approach **reduces crossing count**, but is not automatically faster by the same ratio: buffer allocation/copy time, latency waiting to accumulate a full batch, per-element processing, and memory pressure still exist.

Learning objectives: identify "chatty" calls, place loops appropriately on the native side, choose bulk data structures, batch callbacks, preserve correct semantics, and measure results with proper benchmarks.

### Three Crossing Directions to Distinguish

| Direction | Mechanism | Chatty Call Pattern | Batch Suggestion |
| --- | --- | --- | --- |
| Java → native | JNI native method | `nativeGet(index)` per element | `nativeGetRange(start, count, output)` |
| Java → native | FFM downcall via `MethodHandle` | `process_one(pointer, index)` repeatedly | `process_many(pointer, count)` over one buffer |
| Native → Java | JNI callback / FFM upcall | `onSample(value)` per event | `onSamples(batch, count)` once per batch |

Switching from JNI to FFM only changes the communication API; if you still downcall/upcall per small record, the boundary-crossing count problem is not solved.

## 2. Cost Model and Break-Even Point

Suppose `N` elements need to be processed and each batch has at most `B` elements. If `N > 0`, the number of batches is `K = ceil(N / B)`. Conceptual estimate:

```text
T_total ≈ K_down × C_down
        + K_up   × C_up
        + T_native_compute
        + T_copy/serialize
        + T_allocation
        + T_queue/wait
```

Here `C_down` and `C_up` are the average boundary-crossing costs in each direction; `K_down` and `K_up` are the corresponding call counts. The formula is a model to help locate bottlenecks, **not** a formula to derive exact speed.

With `N=10,000` and `B=512`, the number of batches is 20: consisting of 19 batches of 512 elements and one batch of 272 elements. Compared to 10,000 individual JNI calls, there are 20 calls remaining, i.e., **a 500x reduction in call count**; this does not mean the application is 500x faster. If native compute is very expensive, the benefit from reducing crossings may be small; if data copying spikes, batching may even be slower.

Three goals must be checked together:

1. **Throughput:** how many elements are processed per second.
2. **Latency:** how long each element waits until a result is available; especially p95/p99.
3. **Memory/concurrency:** how much heap/off-heap memory pending batches and buffers use, and whether they cause backpressure or hold resources for too long.

Large batches usually reduce fixed overhead per element but can lengthen wait time to fill a batch. Small batches respond faster but incur more crossings. The optimal size depends on SLA/SLO, workload, memory, and processing type.

## 3. Designing a Batch API Before Writing Code

A common anti-pattern:

```java
// Illustrative snippet; each iteration performs one native call.
for (int i = 0; i < input.length; i++) {
    output[i] = nativeTransformOne(input[i]);
}
```

Moving the same loop to native:

```java
// Illustrative signature; full runnable JNI example is in section 4.
private static native void nativeTransformBatch(int[] values);

nativeTransformBatch(values); // One crossing for the entire array.
```

If the input is too large or arrives as a stream, split it into bounded chunks:

```java
// Illustrative contract; native MUST check offset/length.
private static native void nativeTransformRange(int[] values, int offset, int length);

for (int offset = 0; offset < values.length; offset += batchSize) {
    int length = Math.min(batchSize, values.length - offset);
    nativeTransformRange(values, offset, length);
}
```

You must handle remainders and avoid infinite loops: `batchSize` must be positive; for very large arrays, consider index overflow risk and pagination. The example above illustrates design, not a standalone Java class with a native implementation.

A good bulk contract clearly specifies:

- **Input and layout:** element type, size, byte order, alignment, offset, length, null/empty, encoding for strings or record structures.
- **Output:** in-place or separate output buffer, ordered by input or unordered, result count, per-element status.
- **Errors:** whole-batch failure or partial success; how failed indices are reported, JNI/OS errors, whether retries are idempotent.
- **Ownership:** who allocates, who frees, how long pointers are held, whether the buffer can be used after the function returns.
- **Concurrency:** shared handle, thread affinity, synchronization, limit on concurrent batches.
- **Cancellation and timeout:** handling the last record, flushing on end-of-stream, shutdown, and late callbacks.

Do not arbitrarily combine operations with independent transactional semantics and assume they become one atomic transaction. Side-effect and partial-failure semantics must be clearly defined.

## 4. Runnable Example with Java 17+ and JNI: Scalar vs. Bulk

The example uses the transformation `x ^ 0x5A` on an integer array. Java calls a native function per element in the scalar path; in the batch path, native receives the entire `int[]` and runs the loop. The results of both paths must be equal.

**File `JniBatchDemo.java`:**

```java
import java.util.Arrays;

public final class JniBatchDemo {
    static { System.loadLibrary("jnibatch"); }

    private static native int transformOne(int value);
    private static native void transformBatch(int[] values);

    public static void main(String[] args) {
        int[] input = {1, 2, 3, 4, 5, 6, 7};
        int[] scalar = input.clone();
        int[] batch = input.clone();

        for (int i = 0; i < scalar.length; i++) {
            scalar[i] = transformOne(scalar[i]);
        }
        transformBatch(batch);

        if (!Arrays.equals(scalar, batch)) {
            throw new AssertionError("Different results");
        }
        System.out.println("scalar JNI calls=" + scalar.length);
        System.out.println("batch JNI calls=1");
        System.out.println("result=" + Arrays.toString(batch));
    }
}
```

**File `jni_batch.c`:**

```c
#include <jni.h>
#include <stdint.h>
#include <stddef.h>

static jint transform(jint value) {
    return value ^ 0x5A;
}

JNIEXPORT jint JNICALL
Java_JniBatchDemo_transformOne(JNIEnv *env, jclass cls, jint value) {
    (void)env;
    (void)cls;
    return transform(value);
}

JNIEXPORT void JNICALL
Java_JniBatchDemo_transformBatch(JNIEnv *env, jclass cls, jintArray values) {
    (void)cls;
    jsize length = (*env)->GetArrayLength(env, values);
    jint *items = (*env)->GetIntArrayElements(env, values, NULL);
    if (items == NULL) return; // OutOfMemoryError pending.

    for (jsize i = 0; i < length; i++) {
        items[i] = transform(items[i]);
    }
    (*env)->ReleaseIntArrayElements(env, values, items, 0);
}

// Same library used for the FFM example in the next section.
int transform_buffer(int32_t *items, int32_t length) {
    if (length < 0 || (items == NULL && length != 0)) return -1;
    for (int32_t i = 0; i < length; i++) {
        items[i] ^= 0x5A;
    }
    return length;
}
```

On **Linux** with GCC and JDK 17 or later, open a terminal in the directory containing both files:

```bash
javac -h . JniBatchDemo.java
gcc -std=c11 -O2 -shared -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libjnibatch.so jni_batch.c
java -Djava.library.path=. JniBatchDemo
```

`JAVA_HOME` must point to the JDK in use. `javac -h .` generates the JNI header to verify function names; because the class has no package, the C symbols are `Java_JniBatchDemo_...`. On Windows/macOS, JNI header paths, library names, and compiler/linker commands differ.

**Stdout:**

```text
scalar JNI calls=7
batch JNI calls=1
result=[91, 88, 89, 94, 95, 92, 93]
```

This is a **call count within the program**, not a runtime measurement. The XOR operation is always performed 7 times on the same data.

`GetIntArrayElements` mechanism: the JVM may return a pinned pointer or a pointer to a copy; `ReleaseIntArrayElements(..., 0)` commits modified data and releases it. Therefore, "fewer JNI calls" does not necessarily mean "fewer copies"; to choose between a JNI array or another buffer, you must measure. The illustrative C code assumes the array is non-null and ownership is valid throughout the call; production code needs full validation, error handling, and resource bounds.

### JNI Critical Regions Are Not the Default Batching Solution

`GetPrimitiveArrayCritical` sometimes reduces copy/pinning overhead, but it is a region with special constraints: do not call other JNI functions or operations that may block waiting for a Java thread between `Get...Critical` and `Release...Critical`; hold time must be short. Do not process a very long batch under critical, hold a mutex for long, wait on I/O, or invoke a Java callback while still inside this region. `GetIntArrayElements`, `GetIntArrayRegion`, and direct buffers have different costs/lifetimes: test on the real workload.

## 5. FFM Downcall: Grouping Buffers and Creating MethodHandle Once

**FFM is stable as of Java 22** in `java.lang.foreign` (JEP 454). `Linker.nativeLinker().downcallHandle(...)` calls a native function via a `MethodHandle`; if you call a native function to process each integer, you still have many crossings. A `MemorySegment` holding multiple elements allows one downcall to a C function taking a pointer and a length.

The complete example below uses the same `libjnibatch.so` built in section 4 and the C symbol `transform_buffer` already declared. Run with **JDK 22+**.

**File `FfmBatchDemo.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;
import java.util.Arrays;

public final class FfmBatchDemo {
    public static void main(String[] args) throws Throwable {
        int[] values = {1, 2, 3, 4, 5, 6, 7};
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup library = SymbolLookup.libraryLookup(
                    Path.of("./libjnibatch.so").toAbsolutePath(), arena);
            MemorySegment symbol = library.find("transform_buffer").orElseThrow();
            MethodHandle process = Linker.nativeLinker().downcallHandle(
                    symbol,
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS, ValueLayout.JAVA_INT));
            MemorySegment buffer = arena.allocate(
                    (long) values.length * ValueLayout.JAVA_INT.byteSize(),
                    ValueLayout.JAVA_INT.byteAlignment());
            for (int i = 0; i < values.length; i++) {
                buffer.setAtIndex(ValueLayout.JAVA_INT, i, values[i]);
            }
            int processed = (int) process.invokeExact(buffer, values.length);
            if (processed != values.length) throw new IllegalStateException("Native failure");
            for (int i = 0; i < values.length; i++) {
                values[i] = buffer.getAtIndex(ValueLayout.JAVA_INT, i);
            }
        }
        System.out.println("FFM downcalls=1");
        System.out.println("result=" + Arrays.toString(values));
    }
}
```

In the same directory containing `libjnibatch.so`:

```bash
javac FfmBatchDemo.java
java --enable-native-access=ALL-UNNAMED FfmBatchDemo
```

When the native library is linked and loaded properly, the output is:

```text
FFM downcalls=1
result=[91, 88, 89, 94, 95, 92, 93]
```

Detailed explanation:

1. `SymbolLookup` finds the symbol, `FunctionDescriptor` describes the C ABI, and `downcallHandle` creates a handle for `int transform_buffer(int32_t*, int32_t)` on common Linux (32-bit C `int`). Real applications should resolve symbols and create handles **once per appropriate lifetime**, reusing them across batches.
2. `MemorySegment` holds a contiguous off-heap array of `int`s; Java copies the input into the buffer and reads it back after the downcall. There is only one crossing, but allocation and copy time still exist.
3. `Arena.ofConfined()` restricts the lifetime and the thread allowed to access it. Close the arena when the pointer is no longer used by native workers/callbacks; do not pass a pointer to an asynchronous thread and close it before that thread finishes processing.
4. `--enable-native-access=ALL-UNNAMED` fits classpath examples; named-module applications must configure native access appropriately. Do not use this stable API verbatim on JDK 17 or 21.

FFM upcall is the reverse direction: C can call Java via a pointer created by `Linker.upcallStub`. If C invokes an upcall for each record, overhead still repeats. Design the upcall to accept a pointer to multiple elements along with `count`, while ensuring layout, lifetime, synchronization, callback rules, and error handling. Do not retain a Java `MemorySegment` or C pointer beyond its valid scope.

## 6. Batching Callbacks: Reducing C → Java Calls

In the callback direction, instead of `onEvent(e)` per element, native code accumulates events and calls `onEvents(batch, count)`. Example with 7 events split into batches of 3 elements:

```text
Without batching:
onEvent(1), onEvent(2), ..., onEvent(7)
=> 7 C → Java callbacks

Batch size = 3:
onEvents([1,2,3])
onEvents([4,5,6])
onEvents([7])             <- must flush the remainder
=> 3 C → Java callbacks
```

Three ways to trigger a flush:

- **Count threshold:** once `B` events are accumulated, emit a callback.
- **Time threshold:** the first element must not wait longer than `maxWait` even if `B` has not been reached.
- **Lifecycle threshold:** flush on end-of-stream, close, or shutdown if the contract requires no lost events.

When changes with the same key need to be collapsed (sending only the final state), that is **semantic coalescing**, which is only valid if the receiver does not need to see every intermediate event. Do not coalesce away transactional, audit, or strictly ordered events.

Illustrative C interface, not a standalone program:

```c
#include <stddef.h>
#include <stdint.h>

typedef void (*event_batch_callback)(
    const int32_t *events, size_t count, void *context);

/* Contract:
 * events is valid while the callback is executing;
 * a callback that wants async processing must copy or retain with clear ownership;
 * the producer does not hold a native mutex when calling into Java;
 * count, layout, and event order are defined.
 */
```

**Do not hold a C mutex when calling back into Java**: the callback can re-enter C to access the same resource and cause a deadlock. If processing the callback on another executor, the data must be copied or held in a still-live memory region; a stack/native pointer that is only valid until the caller returns cannot be kept for an arbitrary async task. Queue bounds and backpressure must be defined.

### Java 17 Example: Count-Based Callback Batching

This is a **standalone Java program simulating callbacks**, without wiring JNI itself. Its purpose is to show how to accumulate events and invoke the listener **after releasing the lock**. File `CallbackBatchingDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public final class CallbackBatchingDemo {
    private static final class Batcher {
        private final int limit;
        private final Consumer<List<Integer>> callback;
        private final List<Integer> pending = new ArrayList<>();

        Batcher(int limit, Consumer<List<Integer>> callback) {
            if (limit <= 0) throw new IllegalArgumentException("limit");
            this.limit = limit;
            this.callback = callback;
        }

        void accept(int event) {
            List<Integer> ready = null;
            synchronized (pending) {
                pending.add(event);
                if (pending.size() >= limit) {
                    ready = List.copyOf(pending);
                    pending.clear();
                }
            }
            if (ready != null) callback.accept(ready);
        }

        void flush() {
            List<Integer> ready = null;
            synchronized (pending) {
                if (!pending.isEmpty()) {
                    ready = List.copyOf(pending);
                    pending.clear();
                }
            }
            if (ready != null) callback.accept(ready);
        }
    }

    public static void main(String[] args) {
        int[] callbackCount = {0};
        Batcher batcher = new Batcher(3, events -> {
            callbackCount[0]++;
            System.out.println("callback " + callbackCount[0] + ": " + events);
        });
        for (int event = 1; event <= 7; event++) batcher.accept(event);
        batcher.flush();
        System.out.println("total callbacks=" + callbackCount[0]);
    }
}
```

```bash
javac CallbackBatchingDemo.java
java CallbackBatchingDemo
```

**Stdout:**

```text
callback 1: [1, 2, 3]
callback 2: [4, 5, 6]
callback 3: [7]
total callbacks=3
```

`List.copyOf` creates a separate snapshot; the callback is not invoked while holding the `pending` monitor. The example only has count-based batching and assumes a sequential producer. A real system needs a `maxWait` timer, close/cancel, an exception policy, and a bounded queue. If multiple producers call `accept` concurrently, callback **dispatch** order is not automatically guaranteed just because batch accumulation is inside `synchronized`; you can use a single-threaded dispatcher or sequence numbers. If a callback throws an exception after the batch has already been cleared, you need retry/idempotency or explicit error reporting.

## 7. Buffers and Lifetimes: Avoiding Optimizing Call Count While Breaking Memory

| Data Transfer Method | When Useful | Cost or Limitation |
| --- | --- | --- |
| JNI `int[]` + `GetIntArrayElements` / `Release...` | Processing a batch of Java primitives | JVM may copy or pin; must release with the right mode |
| JNI `GetIntArrayRegion` / `SetIntArrayRegion` | Exchanging chunks by offset/length | Region copy, requires bounds checking |
| Direct `ByteBuffer` / `GetDirectBufferAddress` | Sharing reads of an off-heap buffer within a controlled lifetime | Requires a true direct buffer, capacity, alignment/endianness, ownership |
| FFM `MemorySegment` + `Arena` | Native buffer with clear bounds and lifetime, convenient for downcalls | Alloc/copy, thread confinement, and native access |
| Native callback with pointer and count | Returning a batch instead of per-event | Must keep buffer alive until callback finishes; async must copy/retain |

"Zero-copy" is a claim that must be verified, not a default label for direct buffers or FFM. Each technique differs in copy count, pinning scope, GC pressure, safety, and latency.

If a batch runs asynchronously, a memory region created in a Java method and closed/destroyed right after scheduling the task is **unsafe** if native still holds the pointer. Ownership design must document who creates, where it is used, when it completes, and who frees it. Do not use a `JNIEnv*` from thread A on thread B; if a native thread calls Java on its own, it must attach per JNI and manage global references for objects living across asynchronous calls.

**Synchronization:** snapshot input/state under a short lock, release the lock, then perform the JNI/downcall or callback. The callback commits state briefly and then dispatches listeners outside the lock; do not wait on a worker/future while holding a Java monitor or native mutex. Batching reduces crossing count but can create deadlocks if it increases lock hold time.

## 8. Semantics When Batches Have Errors and Partial Results

Bulk APIs must not trade correctness for throughput:

1. **All-or-nothing:** commit only when every element is valid; if external side effects have already occurred, a clear transaction/compensation mechanism is needed.
2. **Partial success:** return the processed count along with `status[]`/`failedIndices[]` or `(requestId, status)` per item; handle remainders and output order according to the contract.
3. **Retry:** retry only the parts that can be safely repeated, using an idempotency key if there are side effects; do not blindly rerun the entire batch without knowing what already completed.
4. **Duplicate or late callbacks:** attach batchId/sequence/generation, complete a request only once, and recognize events from a cancelled/closed session.
5. **JNI/FFM/native exceptions:** translate native status into contextual Java exceptions; do not ignore a pending JNI exception and arbitrarily call disallowed APIs; do not rely on Java exceptions propagating automatically across FFM's C ABI.
6. **Backpressure:** bounded queue; if the producer is too fast, block, reject, drop, or coalesce depending on data requirements. For events that must not be lost, do not arbitrarily choose drop.

A `processBatch` interface should clearly describe execution order, side effects, buffer lifetime, and per-item status. A fast result that drops an event or double-writes a transaction is a wrong optimization.

## 9. Choosing Batch Size and Flush Policy

Candidate test levels can be `B = 1, 16, 64, 256, 1024, 4096`, but these are **only measurement points**. There is no single best configuration.

| Application Type | Priority | What Easily Happens |
| --- | --- | --- |
| Offline batch, no early response required | Larger batches, fixed chunks | Peak memory, long native calls |
| Stream with response SLA | Batch by count **and** maxWait | Waiting for a full batch increases p99 |
| Very light native compute | Reduce crossings, reuse buffers | Copy/alloc may still dominate |
| Very heavy native compute | Balance batching with fair scheduling/cancel | Reduced call count but little improvement in total time |
| Sparse callback events | Time-based or lifecycle flush | Final batch held indefinitely |
| Multiple producers, slow consumer | Bounded queue and backpressure | RAM grows, callbacks reorder |

For example, the payload of 512 32-bit integers is 2,048 bytes. If there are 100 concurrent batches, each owning both 2,048-byte input and output buffers, the payload alone is about 400 KiB, not counting object metadata, alignment, queues, and intermediate copy buffers. Peak memory matters just as much as the size of a single batch.

To avoid losing data, flush the final batch when the stream ends; to avoid waiting forever, flush after `maxWait` from the first event if the batch is not full; to avoid unbounded buffers, block/shed load according to policy. Callbacks may return results after a request is cancelled, so `requestId`/generation is needed.

## 10. Proper Benchmarking: Proving Throughput and Latency

**Separate correctness testing from performance measurement.** First compare scalar and batch on empty input, single element, size boundaries, incomplete final batch, null/bounds, exceptions, duplicate/late callbacks, multithreading, and cancellation. You should verify the **actual native call count**, but do not equate this count with time saved.

Then use **JMH** for Java microbenchmarks and end-to-end benchmarks for queues/callbacks/I/O. Measurement dimensions:

| Test Dimension | Levels to Try |
| --- | --- |
| API | Pure Java reference; JNI scalar/batch; FFM scalar/batch |
| Item count | 0, 1, 32, 512, 10,000, 100,000 |
| Batch size | 1, 16, 64, 256, 1024, 4096, whole array if appropriate |
| Data transport | Java primitive array, region copy, direct/off-heap segment |
| Native work | No-op, lightweight op, real business compute |
| Callback | Per event; by count; count + maxWait |
| Concurrency | 1 thread, production load, and bursts |

Measure throughput (items/s or ops/s with **equivalent units of work**), CPU, allocations/GC, native memory, bytes copied, crossing count, queue depth, and p50/p95/p99 event latency. Include warmup and multiple iterations/forks, consume results so JIT does not optimize away the computation; do not present a single `System.nanoTime` measurement as primary evidence.

Especially for callbacks: reducing callback invocation time is not enough if the first event waits a long time in the buffer. **End-to-end latency measured from when the event appears** is what reflects effectiveness for the user. Do not claim "X times faster" without measuring in a real environment.

### An Example of Reading Results

If measurements show JNI scalar consumes high CPU when processing 1–2 byte records, while JNI bulk significantly reduces time but pushes callback p99 past SLA, keep bulk for the offline path and use `maxWait`/smaller batches for the real-time path. If native computation per element takes milliseconds, crossing may not be the main bottleneck; optimizing the C algorithm first may be more effective than changing the API.

## 11. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| JNI/downcall per element in a Java loop | Each item causes a crossing | Accept array/segment/range, move the loop into native |
| Resolving symbol/creating `downcallHandle` per item | Unnecessary setup | Create/reuse within the proper lifetime and call in batches |
| C calling back Java per small record | Many upcalls, scheduler/listener overhead | Event batching, count/maxWait/close flush |
| Flushing only when `B` is full | Final batch is held forever | Time-based and end-of-stream flush |
| Always batching the entire dataset | High memory, poor latency and fairness | Bounded chunks, observe p99 |
| Using `GetPrimitiveArrayCritical` for a long batch | Violates critical region rules/may block GC | Short critical, no callbacks/blocking, consider region/direct |
| Batching without defining partial errors | Wrong retries, duplicated side effects | Per-item status, batchId, idempotency |
| Holding Java/C mutex across native call/callback | Reentrancy/deadlock | Snapshot → unlock → crossing → commit state |
| Using native pointer after arena/buffer expires | Use-after-free/crash | Clear lifetime, async copy/retain, and orderly close |
| Seeing fewer calls and concluding it is faster | Ignores copy, alloc, queue latency | JMH + real end-to-end measurement and correctness check |

## 12. Practical Workflow to Improve a Real API

1. **Count crossings and map the data flow:** Java → JNI/downcall → C → callback/upcall → Java, items per request, and state/threads.
2. **Identify bottlenecks:** CPU profile, work heaviness, copy/alloc, callback volume, queues, and latency.
3. **Choose the batch unit:** group elements sharing the same contract, preserve order and semantics; design a `processBatch(data, count, statuses)` API.
4. **Design buffers:** define ownership, offset, alignment, thread, lifetime; avoid per-item allocation if safe reuse is possible.
5. **Batch callbacks:** only when semantics allow; add count + maxWait + end flush and a bounded queue.
6. **Verify correctness:** scalar/bulk produce the same output, remainder handling, single-item errors, timeouts, cancellation, duplicate/reentrant callbacks.
7. **Benchmark and tune:** test multiple `B` values, compare throughput, CPU, memory, p95/p99; accept only if service requirements are met and semantics are preserved.

**Principle:** reduce boundary crossings by passing **a coherent group of work** per JNI/downcall or callback. Fewer calls is a property of the design; being faster and safer must be proven through correctness, performance measurement, and lifetime control.

### References

- [Oracle JNI Specification — JNI Functions, Array Elements, and Critical Arrays](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Java SE 22 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454)
- [Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)

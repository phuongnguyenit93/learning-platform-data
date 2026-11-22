# Waiting for Asynchronous Work to Finish Before Returning a Buffer or Handle

In Java native interoperability (JNI, Foreign Function & Memory API – FFM, C/C++ libraries, devices, or drivers), the call that **starts** an asynchronous operation often finishes before the native operation actually stops using the resource. Therefore, the moment a Java method returns **is not synonymous** with the moment a buffer or handle can be freed, closed, or returned to a pool.

**Goal:** correctly identify resource lifetimes; recognize the true completion signal; coordinate between Java and native code; handle multiple concurrent tasks, errors, timeouts, and cancellation without causing use-after-free or leaks.

## 1. Distinguishing Operations, Resources, and Ownership

- **Buffer:** an off-heap address allocated by an FFM Arena or `malloc`, a `DirectByteBuffer` from which native code can obtain an address, a memory region used for I/O/DMA, or memory returned by a native library.
- **Handle:** an identifier or pointer representing a native resource such as a request, session, stream, file, socket, decoder, or GPU command queue; it may require a separate close/release/free call.
- **In-flight operation:** work that has been accepted or submitted and may still read/write the buffer, use the handle, or fire callbacks. A single submit call may create multiple internal tasks.
- **Owner:** the component responsible for releasing the resource. You must know whether the resource is owned by Java or native code, borrowed, transferred in ownership, or copied.
- **Quiescence (cessation of use):** the state in which it is guaranteed that no worker, DMA, completion callback, or native execution path is allowed to access the resource to be freed.

Lifecycle management principle:

> **Only close/free/recycle when all tasks authorized to use the resource have actually finished and the native API guarantees it will no longer access it.** If native code receives an independent copy, the original can be freed earlier, but only when the API documentation confirms that copying is already complete.

This is a **lifetime/ownership** problem, not simply a matter of calling a Java wait method.

## 2. Why Returning a Resource Immediately After Submit Is a Bug

Suppose a C library provides an asynchronous operation `writeAsync(pointer, size, callback)` and only returns the **request accepted** status:

~~~text
Wrong:
t0 Java allocates buffer at address p
t1 Java calls nativeWriteAsync(p) → returns "accepted"
t2 Java calls free(p), Arena.close(), or returns buffer to pool
t3 native worker/DMA continues reading p          ← use-after-free
t4 callback reports result (if the program has not failed yet)

Correct:
t0 allocate buffer/handle
t1 submit native work; keep owner and lifetime intact
t2 wait for completion signal meaning "no longer using p/handle"
t3 process result and ensure no callbacks still access the resource
t4 close/free/recycle exactly once
~~~

If the newly freed memory region is reallocated to another request, the bug can manifest as corrupted data, cross-request data leaks, random errors, or a JVM crash. Bounds and lifetime checks of **MemorySegment** from Java cannot protect a C operation that is using a raw pointer that has already been freed.

**Returning a buffer to a pool is just as dangerous as freeing it:** a new request can overwrite the region currently being read by native code, even though the address remains valid.

## 3. Read the Native Library's Completion Contract Before Writing a Wrapper

Do not guess the meaning of callback names or return values. The following milestones are very different:

| Milestone | What is known | Can buffer/handle be freed? |
| --- | --- | --- |
| submit returns | Native has accepted or rejected the request | **Not yet**, unless the API has already copied all data and explicitly states so |
| queued/enqueued | Work is in the queue | **Not yet** |
| I/O completed / device event signaled | One layer of work is done | **Only if** the contract guarantees all layers have stopped using the resource |
| true completion callback | Library confirms the operation has quiesced | **Yes**, after other callbacks/users also no longer access it |
| close/abort request completes | Library confirms it has canceled, drained, and stopped all access | **Yes**, in the release order specified by the documentation |

Mandatory questions when integrating an API:

1. Does submit **copy the input** or only keep a **pointer**? Can the output buffer still be written after submit returns?
2. Is the callback invoked **before, at the time of, or after** the last access? After the callback, are there any secondary callbacks or workers still using the handle?
3. When reporting an error, timeout, or cancel, does the library guarantee that **the operation has already stopped**?
4. Can multiple requests share one buffer/handle? Can new requests be submitted during close?
5. In **what order** must release request, unmap, unregister callback, close handle, and free buffer be called?

Without finding a clear promise about quiescence, you cannot infer when to free solely from a **CompletableFuture** created by the wrapper itself.

## 4. Basic Safe Pattern: Submit → True Completion → Cleanup

An ideal wrapper separates two concepts:

- **Business result:** success, error, canceled upon request, or caller timeout.
- **Safe-to-free signal (noMoreNativeAccess / quiesced):** completes only when native code guarantees it is no longer using the resource, including error and cancellation paths.

Procedure:

1. Allocate the buffer and initialize the handle; record who the owner is.
2. Submit the request while the resource is still alive. Native code holds a reference, usage right, or copy according to the contract.
3. Track the request using a callback, completion queue, event, wait function, or native request handle. Each mechanism must be able to produce a reliable **quiesced** signal.
4. Stop accepting new requests on a handle about to close and wait for all in-flight requests to reach quiescence.
5. Retrieve the result, release each request according to the API, then release the buffer/handle once; release everything even when an error occurs.
6. Complete the Future provided to the caller and report errors appropriately. If the caller's Future is allowed to cancel/timeout early, keep a **separate internal quiesced signal** and do not use that Future as the condition to free.

The required ordering relationship is:

~~~text
every last use by native
            ↓
      native quiesced
            ↓
    Java sees completion
            ↓
     close/free/recycle
~~~

A Future is only safe when the provider guarantees it accurately represents the **native quiesced** milestone, not merely “queued”, “cancellation requested”, or “result ready for UI”.

## 5. Java 17+: Runnable Example Demonstrating Waiting Before Closing a Handle

The following example simulates a native worker using a Java thread to verify lifecycle ordering; the **NativeHandle** class is not a real JNI binding. The **completion** signal is emitted **after the last access** to the handle. In a real project, replace the simulation with a native callback or wait that has an equivalent quiescence contract.

**File: AsyncHandleLifecycle.java**

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class AsyncHandleLifecycle {
    static final class NativeHandle implements AutoCloseable {
        private boolean released;

        synchronized int read() {
            if (released) throw new IllegalStateException("released");
            return 7;
        }

        @Override
        public synchronized void close() {
            released = true;
            System.out.println("handle released");
        }
    }

    static CompletableFuture<Integer> submitSimulatedNativeWork(
            NativeHandle handle, ExecutorService worker) {
        CompletableFuture<Integer> completion = new CompletableFuture<>();
        worker.execute(() -> {
            try {
                int result = handle.read() * 6;
                // From here on, the worker no longer reads/writes the handle.
                completion.complete(result);
            } catch (RuntimeException ex) {
                completion.completeExceptionally(ex);
            }
        });
        return completion;
    }

    public static void main(String[] args) {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (NativeHandle handle = new NativeHandle()) {
            CompletableFuture<Integer> completed =
                    submitSimulatedNativeWork(handle, worker);
            System.out.println("result=" + completed.join());
        } finally {
            worker.shutdown();
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac AsyncHandleLifecycle.java
java AsyncHandleLifecycle
~~~

Stdout:

~~~text
result=42
handle released
~~~

**Why is the ordering correct?** **join()** waits for the simulated task's Future to complete; the worker performed its last access **before** calling **completion.complete(...)**. Only upon exiting the **try-with-resources** block is the handle closed. This is a lifecycle simulation exercise and **does not prove** that an arbitrary C library's callback has actually stopped using a pointer; that API contract must be verified.

If the task reports an error after the last access, **join()** throws **CompletionException**, but **try-with-resources** still calls close. This is only safe when **both success completion and error completion are emitted after quiescence**. In the example, there is no path calling **cancel()** that causes the Future to complete early.

## 6. FFM Since Java 22: Keeping an Arena Alive Across Work on Another Thread

The FFM API is officially in **java.lang.foreign** since JDK 22. **Arena** determines the lifetime of off-heap memory it allocates; closing an Arena invalidates associated MemorySegments and frees the native backing region.

- **Arena.ofConfined():** MemorySegment access via Java is only from the owner thread. Do not pass the MemorySegment to another Java worker for reading/writing.
- **Arena.ofShared():** multiple Java threads can access the segment; however, you must still coordinate when they read/write shared data. Shared does **not** mean automatically waiting for native workers to stop.
- **Arena.ofAuto()** or **Arena.global()** does not replace a timely close procedure for native resources that require deterministic release.

The example below runs on JDK 22+ and uses **Arena.ofShared()** because the asynchronous Java task uses the segment on another thread. This is still a **simulation of native work**, intended to show where to place the wait point:

**File: ForeignMemoryWait.java**

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.CompletableFuture;

public class ForeignMemoryWait {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment buffer = arena.allocate(ValueLayout.JAVA_INT);
            CompletableFuture<Integer> operation =
                    CompletableFuture.supplyAsync(() -> {
                        buffer.set(ValueLayout.JAVA_INT, 0, 42);
                        return buffer.get(ValueLayout.JAVA_INT, 0);
                    });

            int result = operation.join(); // wait for completion before closing Arena
            System.out.println("result=" + result);
        }
        System.out.println("arena closed");
    }
}
~~~

Run:

~~~bash
javac ForeignMemoryWait.java
java ForeignMemoryWait
~~~

Stdout:

~~~text
result=42
arena closed
~~~

For real asynchronous FFM downcalls, you must check whether the native library **stores the address** for use after the downcall returns. **MemorySegment** lifetime checks apply to FFM-managed operations; they **cannot detect** native C code accessing a pointer stored outside Java. Only close the Arena after a true native quiescence signal. If the library retains a callback/upcall stub or user-data pointer, their lifetimes must also extend until native code stops invoking them.

## 7. JNI, DirectByteBuffer, and Callbacks from Native Threads

With JNI, native code often obtains an address from **GetDirectBufferAddress** or retains a **jobject** to invoke a callback later. Two types of lifetimes must be distinguished:

| Object | Rule |
| --- | --- |
| Java DirectByteBuffer | Keep the Java object alive for the entire time native code uses the backing memory; a raw address alone does not guarantee the object remains alive |
| JNI local reference | Only valid within the appropriate native method/frame and thread; do not retain past the return of the native method |
| JNI global reference | Use **NewGlobalRef** if native code must keep a Java object/callback across multiple calls; **DeleteGlobalRef** when all callbacks are finished |
| JNIEnv* | Thread-local; a native worker must attach the thread to the JVM before making JNI calls and detach properly when finished |
| Native malloc pointer / handle | Free using the matching allocator or provided API, after workers and callbacks have stopped using it |

**Do not retain a JNI local reference as long-lived callback state.** If C stores a Java callback to invoke from another thread, create a global reference per the JNI contract, manage thread attachment, and delete the global reference only after the final callback. Do not manually free a DirectByteBuffer using the address obtained from GetDirectBufferAddress: backing memory ownership must be determined separately; if it is external memory allocated by native code, use the owner's proper release API.

Be careful with callbacks: some libraries invoke the callback while internal callbacks are still running or while a worker still has a final cleanup step. If the wrapper closes the handle **directly inside the callback** while native code continues referencing it after the callback returns, that is still a use-after-free. Rely on a contract stating “once the callback finishes, there is no more access”, or use a separate drain/join request before freeing.

## 8. Multiple Requests Sharing a Buffer or Handle

For requests r1, r2, … sharing a single handle, you may close only when **all** have reached quiescence. If each request provides a signal that **cannot be canceled early** and completes after the last native access, they can be combined:

~~~java
// Illustration inside a resource management method; not a standalone program.
CompletableFuture<Void> allQuiesced = CompletableFuture.allOf(
        request1.noMoreNativeAccess(),
        request2.noMoreNativeAccess(),
        request3.noMoreNativeAccess());

try {
    allQuiesced.join();
} finally {
    nativeHandle.close();
}
~~~

**Condition:** the three signals above must accurately reflect native completion (including error/cancel paths). If **join()** throws an exception, **allOf** still only completes once every input future has completed; the finally block is safe when each input future completes only after quiescence. If a future is **cancel()**ed to report an early timeout, this condition is broken: **do not** use it to release resources.

In a dynamic system, waiting on a snapshot list is insufficient if new requests can still be submitted. Use a **lifecycle gate**:

~~~text
OPEN: allow accepting new requests; increment in-flight count before submit
       ↓ close is requested
DRAINING: block all new submits; wait for in-flight to reach 0 after native quiesced signal
       ↓
CLOSED: free buffer/close handle once
~~~

You must synchronize the **OPEN → DRAINING** transition with request registration to avoid the race “thread A sees in-flight = 0 and closes, while thread B just submitted a new request”. You can use a lock, a state machine with proper atomic/CAS operations, or the library's reference counting mechanism. If C has separate request handles, release each request in the order required by the API; the parent handle is closed only when all child requests have drained.

## 9. Timeout, Cancel, Errors, and Shutdown: The Most Critical Milestones

- **CompletableFuture.cancel(true)** only changes the Future's state; CompletableFuture itself **does not** use interrupts to stop work. For native I/O, GPU, DMA, or C workers, there is even less guarantee that work has stopped.
- **orTimeout(...)**, **completeOnTimeout(...)**, **Future.get(timeout, ...)**, or a Java thread being interrupted only indicate that the caller stopped waiting or the Future was completed by policy. **Do not infer** that native code is no longer using the buffer.
- On timeout: return an error/timeout to the caller if needed, request **nativeCancel(request)** per the contract, but continue holding the buffer/handle until there is a **cancel acknowledgement or terminal completion confirming quiescence**.
- When native reports an error or the completion callback throws an exception: transition the request state into the cleanup flow, do not forget to decrement in-flight and release references; ensure the callback marks quiesced **only once**.
- On shutdown: block new requests, request cancellation or drain old requests, wait for the native completion signal, then close request handles, buffers, parent handles, and executors in order. If the API does not support safe cancellation, resources must be kept until the operation finishes, or you must accept process-lifetime isolation/management instead of freeing early.

A useful way to organize this is with two separate Futures: **resultForCaller** can timeout/cancel, while **nativeQuiesced** is resolved only by the true native completion event and kept private inside the resource management layer. **Do not allow external consumers to complete/cancel nativeQuiesced**. Native code may report business-level cancellation success yet still require a drain step before freeing.

## 10. Data Synchronization and Thread Safety

Waiting for completion solves **lifetime**; it does not automatically solve all data races.

- Java thread A writes input and submits to native: ensure native sees the written data in the way specified by the interop API (memory barrier, fence, pin/map, driver synchronization, or appropriate synchronized accesses).
- Native finishes writing output: ensure the data is published to Java before Java reads it. Java callback/Future ordering **cannot arbitrarily replace** memory/device requirements in the C/driver contract.
- A Shared Arena allows Java threads to access the segment, but does not automatically make reads/writes to the same address atomic or data-race-free.
- Do not use one mutable buffer for two overlapping requests unless partitioning, synchronization, or library-guaranteed safety is in place.

When designing a wrapper, clearly document the contract: who writes, who reads, when data is ready, and from which milestone memory may be reused.

## 11. Anti-Patterns and Fixes

| Anti-pattern | Consequence | Replace with |
| --- | --- | --- |
| Closing Arena/handle immediately after **submitAsync(...)** | Native still holds pointer → use-after-free | Keep owner alive until terminal quiescence |
| Placing **try-with-resources** only around the submit call | Scope ends before the worker | Place wait/cleanup point within the scope that still holds the resource |
| Using **cancel()** or timeout as the free signal | Native may still be running | Cancel native, then wait for true ack/drain |
| Returning DirectByteBuffer to pool after enqueue | Another request overwrites input/output in use | Return to pool after API-guaranteed completion |
| Holding a JNI local ref for a late callback | Reference becomes invalid | NewGlobalRef, delete after the final callback |
| Using Arena.ofConfined() for a Java worker on another thread | WrongThreadException on Java access | ofShared when cross-thread Java access is needed; synchronize data |
| Waiting on one Future while other requests share the handle | Closed too early | Wait for all in-flight + block new submits |
| Letting a callback both release and call APIs on the same handle without a convention | Deadlock/reentrancy/use-after-free | Standardize callback, drain, and cleanup order per contract |

## 12. How to Verify a Wrapper in Practice

1. Draw the **allocate → submit → native use → true completion → cleanup** timeline for each buffer and handle.
2. Document what completion means and cite where it appears in the native documentation; check success, error, cancel, and shutdown paths.
3. Stress test with fast/slow callbacks, many requests, timeouts, cancellations, native errors, and concurrent closes; log request ID, owner ID, in-flight count, and free timestamp.
4. Verify no new requests during **DRAINING**, no double-close, no pooled buffer reused while still in use, and no leaks on error paths.
5. When compiling custom C/C++, consider AddressSanitizer/ThreadSanitizer, leak detectors, JNI checks, and native crash dumps. These tools help find bugs but do not replace verifying the completion contract.

**Self-check exercise:** A library returns a Future indicating “request sent to device”, while a callback reports “DMA complete”. Where should you return the buffer to the pool? **Answer:** after the **DMA complete** callback if the documentation confirms that is also the final use by the device/native code and no secondary callback still uses the buffer; if unconfirmed, you must wait for a later drain/quiescence milestone.

## Authoritative References

- Oracle, Java SE 22 FFM package: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html
- Dev.java, managing Arena and MemorySegment lifetimes: https://dev.java/learn/api/io/ffm/access-memory/
- Oracle, Java SE 17 CompletableFuture (especially cancel, join, allOf): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle, JNI Design Overview (global/local references): https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html

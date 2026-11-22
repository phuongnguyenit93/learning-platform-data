# Native Library Rules: Is Concurrent Calling Safe or Must a Single Thread Be Used?

When Java calls a native library via JNI, JNA, or the Foreign Function & Memory API (FFM), **the ability to call concurrently is determined by the native library itself and each of its resources**. The fact that Java code uses multiple threads, uses a wrapper with immutable objects, or has safe memory management mechanisms does not automatically make the underlying C/C++ functions thread-safe.

The goal of the integration step is to write a verifiable **concurrency contract**: which functions may be called in parallel, on which handles, from which threads; who manages resource initialization/closing; whether callbacks may call back into the library; and how the program will handle cancellation, timeouts, or shutdown.

## 1. Distinguishing Easily Confused Policies

| Library policy | What is allowed | Common integration approach |
| --- | --- | --- |
| **Thread-safe / concurrent** | Calls confirmed by documentation to be executable in parallel within the stated scope | Allow direct calls; still coordinate object lifecycle and shared state |
| **Library-wide serialized** | Only one call into the library at a time, even when using multiple handles | One shared lock for the entire wrapper or a single execution queue |
| **Per-handle/context serialized** | Different handles can run in parallel; the same handle allows only one call at a time | One lock or one queue per handle; manage closing under the same lock |
| **Thread-confined / thread-affine** | A handle must be created, used, and destroyed on the **same owning thread**; sometimes the entire library requires using one specific thread | Assign an owner thread and route all operations to that thread's executor/dispatcher |
| **Main-thread-only** | May only be called on the main/UI/event thread as mandated by the native environment | Dispatch to the proper thread/framework; a self-created executor cannot replace the main thread |
| **Non-reentrant** | Must not re-enter the same function/state while a previous call has not finished, even from a callback on the same thread | Forbid or defer re-entry; control the callback path, not just add locks |

**Core difference:** "only one call at a time" only speaks to **temporal overlap**; "only one thread" also speaks to **thread identity**. A Java lock can serialize two calls from thread A then thread B, but it **does not turn B into A**. Therefore, a lock is not sufficient for an API with thread affinity.

It is also necessary to distinguish "thread-safe" from "reentrant": an API may allow multiple threads to call on independent contexts, yet not allow a callback to call back into the very context being processed. Conversely, a function may be reentrant yet still access unsynchronized global state when running on different threads.

## 2. The Scope of Guarantees Must Be Determined

Before designing a wrapper, read the documentation for the exact **library version, operating system, backend, and functions** being used. Statements like "library is thread-safe" are only useful when you know exactly what is guaranteed.

For each group of functions, clarify:

1. **State scope:** does the data reside in a process-global singleton, static buffer, a session/context/handle, thread-local storage (TLS), or memory passed in by Java?
2. **Read/write:** can two read-only operations run concurrently? Does reading touch cache/lazy initialization state? Does writing configuration require exclusivity?
3. **Handle independence:** are two handles truly independent, or do they share an allocator, device, global error buffer, registry, or native connection?
4. **Owning thread:** may a handle be moved to another thread between calls? Do create, use, destroy, and callback functions have the same constraint?
5. **Initialization/closing:** is init/shutdown process-wide, singleton, per-thread, or per-handle? Is it allowed to init/close while calls are still running?
6. **Callbacks:** does the library invoke callbacks from the calling thread itself, an internal thread, or a thread it creates itself? Is it allowed to call back into the API from a callback?
7. **Errors and cancellation:** is error message/last-error stored in TLS? Does a cancelled or timed-out call continue using the handle/buffer on the native side?

For example, the statement "multiple contexts are processed in parallel" **does not imply** "the same context is processed in parallel". Similarly, "the process function is thread-safe" **does not imply** "calling destroy while process is running is safe".

If the documentation does not state this clearly, record the policy as **unknown** and verify through official documentation, headers, vendor examples, or discussion with the library owner. While unverified, you may choose conservative serialization to reduce risk during integration, but do not declare it as a true thread-safe guarantee. Stress tests do not replace a contract from the library author.

## 3. Choosing the Right Synchronization Boundary for Native State

Suppose a library provides conceptual functions of the form:

~~~c
NativeHandle *native_create(void);
int native_process(NativeHandle *handle, const unsigned char *data, size_t length);
void native_destroy(NativeHandle *handle);
~~~

These are **illustrative signatures**, not the API of a real library. Depending on the contract, the same three functions above may require three different designs:

- If **all handles share unsafe process-wide state**, you must lock create/process/destroy and any functions touching that state together.
- If **each handle has independent state but cannot be used concurrently**, use a separate lock per handle. Two different handles are processed in parallel only when the documentation permits.
- If **a handle is bound to the thread that created it**, create, process, and destroy the handle on the same owning thread; use a queue to receive requests from other Java threads. Locking around each call does not solve this constraint.

A common mistake is locking only the process call while letting destroy run outside the lock. In that case, thread A may be executing process(handle) while thread B frees the handle; the consequence can be use-after-free, a JVM crash, or memory corruption. **Handle lifecycle is part of the concurrency policy.**

## 4. Serialization Policy: Using Locks When the Library Allows Thread Switching

If the library allows consecutive calls on different threads but forbids overlap, an adapter can place a lock matching the scope of the native state:

~~~java
// Illustrative snippet inside an adapter class; not yet a standalone program.
private final Object nativeLock = new Object();

public int process(long handle, byte[] data) {
    synchronized (nativeLock) {
        ensureOpen(handle);
        return nativeProcess(handle, data); // Native binding declared elsewhere.
    }
}

public void destroy(long handle) {
    synchronized (nativeLock) {
        ensureOpen(handle);
        nativeDestroy(handle);
        markClosed(handle);
    }
}
~~~

The lock above is **global to one adapter instance**. It is only equivalent to a library-wide lock if all access paths to the library go through **the same instance/same lock**. If the application creates multiple adapters, uses multiple bindings, or the native code has global state shared with other code, you must organize a shared lock according to the actual scope of the library. For APIs that only need per-handle serialization, use a lock residing in the object owning the handle so as not to accidentally block independent handles.

Hold the lock for the entire duration that native code uses the handle and buffer. Do not hold the lock during unrelated Java tasks. Establish a consistent acquisition order for multiple locks; avoid calling back into the application arbitrarily while holding the lock, because callbacks or listeners can create a wait cycle.

**Do not use a Java lock to fix an API that requires the same OS thread.** Java synchronized or ReentrantLock guarantees mutual exclusion, not thread identity.

## 5. Single-Thread Policy: Putting the Entire Lifecycle into an Owner Executor

For APIs requiring a handle to be created, used, and destroyed only on the same thread, a single-thread executor is a common implementation in background Java applications. Multiple Java callers can submit work to the gateway; the gateway sequentially executes all native operations on a single thread.

The following Java 17 example **runs standalone**. The native part is simulated with a counter variable so learners can verify the thread confinement mechanism without needing a C library or JNI. In real integration, replace the simulated operations with binding calls and keep the owner thread constraint intact.

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class NativeCallPolicyDemo implements AutoCloseable {
    private final ExecutorService owner = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "native-owner"));
    private final Object lifecycle = new Object();

    private volatile Thread ownerThread;
    private boolean closed;              // Only accessed under the lifecycle lock.
    private int simulatedNativeCounter;  // Only accessed on the owner thread.

    public NativeCallPolicyDemo() throws InterruptedException, ExecutionException {
        owner.submit(() -> {
            ownerThread = Thread.currentThread();
            simulatedNativeCounter = 0;  // Simulate nativeCreate().
        }).get();
    }

    private void rejectOwnerReentry() {
        if (Thread.currentThread() == ownerThread) {
            throw new IllegalStateException("Blocking reentry from native-owner");
        }
    }

    public int increment(int delta) throws InterruptedException, ExecutionException {
        rejectOwnerReentry();
        Future<Integer> result;
        synchronized (lifecycle) {
            if (closed) {
                throw new IllegalStateException("Gateway closed");
            }
            result = owner.submit(() -> {
                if (Thread.currentThread() != ownerThread) {
                    throw new IllegalStateException("Wrong native thread");
                }
                simulatedNativeCounter += delta; // Simulate nativeProcess(delta).
                return simulatedNativeCounter;
            });
        }
        return result.get();
    }

    @Override
    public void close() throws InterruptedException, ExecutionException {
        rejectOwnerReentry();
        Future<?> cleanup;
        synchronized (lifecycle) {
            if (closed) {
                return;
            }
            closed = true;
            cleanup = owner.submit(() -> {
                simulatedNativeCounter = 0; // Simulate nativeDestroy().
            });
        }
        try {
            cleanup.get();
        } finally {
            owner.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        try (NativeCallPolicyDemo gateway = new NativeCallPolicyDemo()) {
            System.out.println(gateway.increment(1));
            System.out.println(gateway.increment(2));
        }
    }
}
~~~

Save to the file **NativeCallPolicyDemo.java**, then run:

~~~bash
javac NativeCallPolicyDemo.java
java NativeCallPolicyDemo
~~~

Deterministic output:

~~~text
1
3
~~~

**Why does the example satisfy the single-thread rule?**

- The constructor submits the creation operation to the executor; each increment also runs on that thread; close enqueues the destruction operation onto the same queue.
- The lifecycle lock ensures that tasks already accepted into the queue **precede** the destruction task and prevents accepting new calls after closing begins. It does not replace the owner executor.
- ownerThread is recorded once; the thread check is meant to detect integration errors. The simulated state variable is only accessed by the owner thread.
- rejectOwnerReentry prevents a callback running on the owner thread from calling increment/close and then waiting on Future.get(), causing a deadlock: the executor cannot execute the new task while its thread is waiting on that very task.
- try-with-resources ties the closing operation to the object lifecycle. Other callers can invoke the gateway, but **the ordering of calls from concurrent callers is not guaranteed**; the application must define business ordering if needed.

This is a synchronous example to illustrate the policy. In real systems, use an asynchronous API (e.g., CompletableFuture) or an appropriate dispatcher to avoid blocking the UI/event loop; have error-handling procedures for initialization failure, shutdown control, timeouts, and threads stuck in native calls. If the library requires a **framework-designated main thread**, do not replace it with a self-created executor named native-owner.

## 6. JNI, JNA, and FFM Do Not Determine Thread Safety on Behalf of the Library

### JNI

Java can call the same native method from multiple Java threads at the same time. JNI does not automatically add a mutex around C/C++ code. The **JNIEnv*** pointer belongs to the executing JNI thread; do not store a global JNIEnv* and use it from another thread. If a native-created thread needs to call Java, it must be attached to the JVM before using JNI, obtain the JNIEnv* for that thread itself, and detach appropriately when the thread finishes if the native code itself attached it. Local JNI references also have their own scope and lifetime; when a reference needs to be kept across calls, global references must be managed according to the rules.

These requirements are **JNI/JVM** rules, distinct from whether a C function is safe to run in parallel. A JNI function called with a valid JNIEnv* can still cause a data race in the C library.

### JNA

JNA helps map native functions and data types into Java, but creating bindings and calling methods on a proxy **does not prove** that the C library is thread-safe. The decision to serialize library-wide, per-handle, or dispatch to an owner thread must still be based on the library's contract. When callbacks are present, you must consider the thread invoking the callback and the possibility of the call re-entering the adapter while it holds a lock.

### Foreign Function & Memory API (FFM)

FFM is a standard API as of **JDK 22**; do not use JDK 22 FFM syntax as if it were already available on Java 17. A downcall from Java into a native function cannot fix data races in that function itself. For off-heap memory, **Arena.ofConfined()** has access constraints tied to the owning thread, while **Arena.ofShared()** allows access from multiple threads but does not guarantee that the native library synchronizes itself. You must coordinate both **memory segment access/lifecycle rules** and **native function concurrency rules**; one rule does not replace the other.

## 7. Callbacks, Reentrancy, Timeouts, and Closing Resources

### Callbacks Can Break the "Only Called from One Place" Assumption

A scenario prone to deadlock:

1. Thread A holds a Java lock and calls nativeProcess().
2. Native code invokes a Java callback before returning.
3. The Java callback calls another API that needs the very resource being processed, or waits for work submitted to the owner executor that the current thread is occupying.
4. The native call cannot finish because the callback is waiting; the callback also cannot complete because the resource/owner thread has not been released.

The contract must clearly state **whether a callback may re-enter the library**. If not, the callback should record the event, copy still-valid data if needed, and then defer further processing to another queue once the native call has returned. Do not assume that Java's reentrant locks make a native API reentrant. If the callback arrives from a native-created thread, verify the JVM attach mechanism and the lifetime/scope of callback data.

### Timeout Does Not Mean Native Code Has Stopped Working

With Future.get(timeout), timing out only means **the caller will not wait any longer**. Calling Future.cancel(true) also does not guarantee stopping a running C function: native code may not respond to Java interrupts. Therefore, do not free handles, memory segments, callbacks, or input buffers just because Java receives a TimeoutException. Clean up only when there is confirmation that the call has finished or via a cancellation mechanism clearly defined by the library. If the library can hang permanently, it may be necessary to isolate it in a child process for a stronger recovery boundary.

### Closing Must Align with the Calling Policy

Define when the adapter transitions from OPEN to CLOSING and then CLOSED; reject new operations; wait for accepted operations to complete; destroy on the right thread in the right order. With per-handle locking, close must use that same lock. With an owner executor, close must be queued after accepted tasks. Do not call library-wide shutdown while live handles or calls remain, unless the documentation allows it.

### Buffers and Data Ownership

Even when a native API is thread-safe, Java callers can still cause a race by concurrently modifying a byte[] or ByteBuffer that native code is reading. Documentation must clearly state whether native code **copies the data immediately** or **retains the pointer for later use**, who owns the memory region, and when it may be modified or freed. For asynchronous operations, keep the data and handle alive until native code confirms completion.

## 8. Writing a Clear Contract at the Java–Native Boundary

A wrapper should have specific documentation by operation group, for example:

| Component | Example contract to declare |
| --- | --- |
| Initialization | Called once per process, before any handle; locked if needed |
| Handle creation | On the owner thread or any thread? Can they be created in parallel? |
| Handle read/write | Are read–read, read–write, write–write allowed in parallel on the **same handle**? |
| Different handles | Truly independent or sharing a global lock? |
| Callbacks | Source thread, data lifetime, reentrancy allowed/forbidden |
| Handle destruction | Only when no calls are running, on the proper owner thread if required |
| Shutdown | Close all handles, wait for callbacks/calls to finish, then shutdown |
| Timeout/cancellation | What does the native cancellation mechanism guarantee? When is the caller allowed to close? |

The policy can be expressed directly in the adapter's Javadoc:

~~~java
/**
 * Example rules (use only when confirmed by native documentation):
 * - Each Handle has only one native operation at a time.
 * - Two independent Handles are processed in parallel.
 * - close() waits for the running operation of the same Handle to finish.
 * - Do not call back into the Handle API from a native callback.
 * - No constraint requiring the same OS thread.
 */
~~~

The snippet above is a **contract template**, not a conclusion about a specific library. If the vendor states "each session must stay on its initialization thread", replace the per-handle locking policy with owner-thread dispatch and explicitly document create/call/destroy.

A Java API can avoid having callers hold locks themselves by encapsulating the entire policy inside a gateway: callers only receive methods that are safe per the contract, without direct access to the raw handle. Separating the interface/handle API helps prevent call paths that bypass the lock or executor; however, if native code has global state shared across multiple gateways, coordination must happen at that global scope.

## 9. Verifying the Policy Before Using in Production

Start with the official documentation/contract; then verify the adapter implementation with targeted scenarios:

- **Same handle, multiple callers:** submit multiple operations from different Java threads; confirm no two calls on the same handle overlap when the policy forbids it.
- **Multiple handles:** if documentation allows, confirm the adapter does not unnecessarily serialize globally; if native code has global state, confirm a shared lock exists.
- **Thread affinity:** log the thread ID at create/use/destroy and check that they match; test calling from the wrong thread in a test environment to confirm it is rejected.
- **Lifecycle:** run close concurrently with process, close twice, submit after close, failing constructor, shutdown while tasks remain in the queue; no use-after-free or leaks occur.
- **Callbacks:** test callbacks fired directly inside a native call, callbacks from a native worker, and re-entrant call scenarios; detect deadlocks and holding data past its lifetime.
- **Timeout:** intentionally let a call take longer than the wait time; verify resources are not destroyed while native code is still using them.

Minimum logs should include operation, handle ID (without exposing pointers/secrets), thread ID/name, start/end timestamps, OPEN/CLOSING/CLOSED state, and native error code. For C/C++ code under your control, you can add ThreadSanitizer or an appropriate data-race detection tool; successful stress test results still **do not prove** safety for all schedules.

## 10. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | Fix |
| --- | --- | --- |
| "The Java wrapper is synchronized so the native API is thread-safe" | The lock may have the wrong scope; other direct calls may bypass it; thread affinity is still violated | Determine the native scope and wrap all necessary call paths |
| Using a mutex for an API requiring the same thread | Two sequential calls can still run on two different OS threads | Use the proper owner thread/dispatcher for create–use–destroy |
| Locking process but not locking destroy | May free the handle while a call is running | Put close into the same coordination and lifecycle mechanism |
| Using a separate lock per wrapper when native code has global state | Two different wrappers still call into global state in parallel | One shared lock at the library/process scope |
| Treating all handles as dependent on each other | Loses concurrency even when the library allows independent handles | Lock per handle when confirmed by the contract |
| Callback synchronously calling back into the owner executor | The owner thread waits for the very work it must execute | Forbid synchronous re-entry, defer to a safe phase |
| Freeing the buffer after a timeout | The native call may still be running even though the caller stopped waiting | Wait for confirmed native completion/cancellation |
| Using thread A's JNIEnv* on thread B | Violates JNI thread rules | Obtain the current thread's JNIEnv*, attach when needed |

## 11. Quick Selection Rules

1. **Is there a clear guarantee that the relevant functions and handles are safe when concurrent?** Allow parallelism within that exact scope; still synchronize lifecycle and shared input buffers.
2. **Is overlap forbidden while allowing subsequent calls on a different thread?** Use a lock or queue; choose **library-wide** or **per-handle** locking based on native state.
3. **Is the same thread that created the handle or the framework's main thread required?** Dispatch all create/use/destroy operations to the right thread; design callbacks and close to avoid self-waiting.
4. **Missing or conflicting information?** Keep the policy in an unverified state, prefer conservative behavior, and record specific questions for the vendor to confirm before declaring thread-safety.

**Technical conclusion:** The concurrency policy must adhere to **the native library's contract, state scope, and resource lifecycle**. Java locks solve mutual exclusion; an owner-thread executor solves thread affinity; callbacks and cleanup must follow the same policy. Only when these boundaries are clearly defined can a Java adapter provide a safe and verifiable native-calling API.

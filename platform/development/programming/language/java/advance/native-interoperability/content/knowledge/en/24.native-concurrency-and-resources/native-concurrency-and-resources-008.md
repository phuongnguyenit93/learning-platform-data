# Closing Order of Callbacks, Native Objects, Memory, and Libraries

When Java calls C/C++ via JNI or the Foreign Function & Memory API (FFM), calling `close()` on a Java object does not automatically guarantee that the native side has stopped using the callback address, object pointer, or memory. A callback may still be running on another thread while Java begins cleanup. Freeing resources in the wrong order can lead to *use-after-free*, *double-free*, deadlocks, or crashing the entire JVM.

The goal of this article is to identify **who owns each resource, who can still access it, and what condition proves the resource is no longer in use**, and then design a verifiable shutdown protocol. The overarching principle is: **stop the source of new work → unregister and wait for running callbacks to finish → release dependent objects → free memory → unload the library last**, adjusted according to the contract of the actual native API.

## 1. Distinguishing Four Types of Resources

| Resource | Examples | Who usually owns it? | May only be freed when |
| --- | --- | --- | --- |
| Callback registration and callback function pointer | `register_listener(handle, fn, user_data)`; FFM `Linker.upcallStub(...)`; JNI calling back into Java | Registration is managed by the native library; stub and Java references are managed by the bridge | Native cannot start new callbacks **and** all callbacks currently using the stub/context have finished |
| Native object (native object/handle) | `NativeSession*`, `JNI jlong handle`, C++ pointer | Allocated by the library or a wrapper that takes ownership | No Java calls, callbacks, or native threads are accessing it; the destructor still exists |
| Off-heap memory | `malloc`/`free`, `MemorySegment`, buffers passed to the library | May be managed by a Java arena, C library, or native object | All parties holding pointers/slices/views have stopped reading or writing; freed with the matching allocator |
| Native library | `.so`, `.dll`, `.dylib`, function addresses in the library | JNI class loader or FFM `SymbolLookup.libraryLookup` bound to an `Arena` | No code, destructor, worker thread, callback, or function pointer needs to execute from the library |

**Ownership cannot be guessed from function names.** `create()` might return a handle that the caller must `destroy()`, or return a borrowed reference retained by the library. `get_buffer()` might return a borrowed pointer that is only valid until the next call; `take_buffer()` might transfer ownership. Read the C ABI documentation on “owned/borrowed/transferred”, the corresponding allocator, thread affinity, and whether unregister waits for running callbacks. A pointer being present in Java does not mean Java has the right to `free` it.

Example of a native session with dependency relationships:

```text
Native library L (provides register/unregister/destroy/free)
    ├── Native session H
    │     ├── holds a pointer to buffer B (allocated by Java)
    │     └── registers callback R
    │             ├── upcall stub S (allocated by callback Arena)
    │             └── user_data/context U (Java/JNI or native)
    └── worker thread T may invoke R(S, U) asynchronously
```

The validity condition must be `lifetime(B) >= last use of B by H/T`, `lifetime(S,U) >= last callback`, and `lifetime(L) >= last call to a function of L`. The `>=` sign here denotes temporal ordering, not pointer arithmetic. If the destructor of `H` still invokes a callback, then `S/U` must live **past the point where the destructor finishes**. Therefore, do not impose a rigid closing order without knowing the C API contract.

## 2. “No Longer Registered” vs. “No Longer Running Callbacks”

Suppose thread A executes `unregister_callback(h)`, while thread B has already obtained the callback address and is about to call `fn(user_data)`. There are three common API situations:

1. `unregister` only prevents new events but **does not wait** for already-scheduled callbacks: an additional `stop + join/drain` or library synchronization mechanism is required.
2. `unregister` is a *synchronous quiescence* function: upon returning, the library guarantees no callbacks are running or can start; in that case, the stub/context can be closed immediately afterward.
3. `destroy(h)` unregisters and waits for callbacks itself: only apply that order if guaranteed by the API, while keeping the stub, user data, and memory alive until `destroy` returns.

You cannot assume `unregister` falls into case 2. A Java-side `AtomicBoolean stopping` flag only makes the Java callback skip work; it **does not prevent** the C library from jumping to a freed function pointer address. An `inFlight` counter in Java also has a gap if a native callback has been dispatched but has not yet incremented the counter. A **barrier from the source side** is needed: native stops generating new callbacks, unregisters according to the API, and guarantees all dispatched callbacks have completed or been joined.

Shutdown states can be represented as:

```text
RUNNING ── stop accepting operations ──> QUIESCING
QUIESCING ── unregister + drain/join ──> QUIESCENT
QUIESCENT ── destroy handles + free memory ──> RELEASED
RELEASED ── release/unload library when supported ──> CLOSED
```

States must be protected by appropriate synchronization/atomics. Do not allow new calls to borrow the handle after transitioning to `QUIESCING`; already-started calls must finish before `destroy`. This is **a separate barrier** from the callback barrier: both Java-to-native *downcalls* and native-to-Java *upcalls* must be blocked simultaneously.

## 3. Recommended Shutdown Protocol, Step by Step

### Step 1 — Close the gate for new work

Mark the session as `CLOSING` using a state machine, lock, or CAS; reject new Java calls from borrowing the native handle, block new listener registrations, and cancel Java-owned timers/producers. Use primitives that guarantee *happens-before* (such as locks, `AtomicReference`) so threads observe consistent state. A single `volatile` flag is insufficient if a “check then borrow handle” operation needs to happen atomically.

If a callback itself calls `close()`, do not let `close()` wait for that same callback to finish; perform the state transition and delegate cleanup to another thread, or design `close` not to block inside the callback.

### Step 2 — Request native to stop emitting callbacks

Call the appropriate API such as `stop_events`, `disable_notifications`, `unregister_callback`. Do not hold a Java monitor that the callback needs to acquire while calling an API that might wait or call back into Java; otherwise, close holds the lock, native waits for the callback, and the callback waits for the lock, causing a deadlock.

The contract needs to clearly answer:
- After `unregister` returns, can any new callbacks still start?
- Is a running callback allowed to call back into `unregister/destroy`?
- Can `unregister/destroy` synchronously invoke a final callback?
- Which worker threads will be joined, and can they be joined from that same thread?
- Until what point is the `user_data` context retained by native?

If the answers are unclear, **it is not yet safe** to free the stub/context. You need to read the API documentation, add `stopAndDrain` in the C bridge layer, or change the ownership protocol.

### Step 3 — Wait for all in-flight work to leave native

Wait for native threads/queues/workers to stop and running callbacks to finish. Also wait for Java downcalls that have already borrowed the handle. When using a counter/refcount, the increment must be inside the mutual exclusion region with the stop operation; do not “check state → release lock → increment counter” because `close` might see 0 and free resources before the counter increments.

With timeouts, **do not** arbitrarily free pointers just because the timeout expired. If the library has not proven quiescence, report a shutdown failure, isolate the session, and prefer keeping resources alive (potentially a controlled leak) over causing a use-after-free. Design a hard-cancellation mechanism only when the API vendor guarantees safety.

### Step 4 — Destroy native objects while dependencies are still alive

Once there is no concurrent access, call the appropriate `native_destroy(handle)` or `release_handle` according to ownership. Any buffers read by the destructor, callbacks/contexts still invoked by the destructor, and the library containing the destructor itself must remain alive **until destroy completes**.

If the native object owns the buffer itself, the destructor may have already freed the buffer: **do not call `free` again**. If the buffer is owned by Java and only borrowed by the object, keep the buffer until after destroy. If the object is independent of the buffer, the two resources may be freed in a different order; decide based on the actual dependency graph.

### Step 5 — Free callback stubs, contexts, and off-heap memory

When certain that native will not call back again:
- FFM: close the `Arena` owning `upcallStub`, `MemorySegment`s, and corresponding data regions at the right time. `Arena.close()` is **not idempotent**; do not close it twice or from the wrong thread for a confined arena.
- JNI: delete `NewGlobalRef` with `DeleteGlobalRef` **after** callbacks/native workers are done using it; do not store `JNIEnv*` and use it on another thread. Free `malloc` with `free` and C++ memory with the owner's corresponding mechanism.
- Native handles, pointers, stubs, and memory views in Java should be marked invalid immediately in the wrapper; do not pass freed pointers to other APIs again.

Note: closing an arena invalidates access through `MemorySegment`s belonging to that scope, but **cannot revoke** raw C pointers already copied outside Java. FFM's safety does not replace synchronization with asynchronous native code.

### Step 6 — Unload the library last, if the loading model allows

A `destroy/free/unregister` function still needs machine code residing in the library. Unloading the library before they finish will cause function calls or callbacks to jump into unloaded code.

- **FFM from Java 22:** `SymbolLookup.libraryLookup(path, libraryArena)` ties library lifetime to an arena; keep `libraryArena` alive longer than all arenas containing callbacks/data and all objects/downcalls using the library's symbols. Close `libraryArena` last. If the library has been loaded/retained elsewhere, whether the OS actually unloads the module depends on reference counts and the platform.
- **JNI via `System.loadLibrary` / `System.load`:** there is no public `System.unloadLibrary` counterpart to call like a normal resource close. The library is tied to the class loader and may be unloaded when the loader is no longer retained; `JNI_OnUnload` is not a reliable session shutdown point, and arbitrary Java callbacks should not be made from this hook.
- **Process-wide library or static linking:** sometimes there is no active unload. Still close sessions, callbacks, handles, and memory; document clearly that the library remains until the process terminates.

## 4. Two Dependency Patterns That Invert Local Order

**Case A — Callback is attached to the session, destructor needs the buffer:**

```text
stop accepting → native.stop → unregister + drain
→ destroy(session) → release callback stub/context
→ free(sessionBuffer) → unload library
```

If `destroy(session)` can invoke a final callback, the stub/context must be kept until after `destroy`, even if asynchronous callbacks have been prevented. If the destructor never invokes callbacks and no longer uses the context, the stub/context can be released right after unregister + drain. Choosing between the two must be based on native documentation.

**Case B — Native object owns the buffer and unregisters itself in the destructor:**

```text
stop accepting → native.stopAndJoin
→ destroy(session)  [unregisters + frees buffer per contract]
→ release Java GlobalRef/upcall stub
→ unload library
```

Do not separately free a buffer already owned by the destructor. If the API does not provide `stopAndJoin` and `destroy` does not guarantee waiting for callbacks, a synchronization step must be added in the bridge; do not assume the destructor is a quiescence barrier.

A useful rule of thumb is **tearing down dependencies in the reverse order of creation**, but an async object is only eligible for teardown when all tasks using it have finished; creation order alone does not prove that.

## 5. Common Race and Deadlock Bugs

| Mistake | What can happen | Fix |
| --- | --- | --- |
| Closing `callbackArena` right after async `unregister` | Native still calls old stub address; JVM crash | Native unregister + guaranteed drain/join |
| Freeing buffer before `destroy(handle)` | Destructor or worker reads freed memory | Destroy/stop buffer usage first, per ownership |
| `dlclose` before calling `destroy/free` | Function pointer points to unloaded library | Close library after all final native calls |
| Setting `AtomicBoolean closed` and closing immediately | Callback was already dispatched but hasn't entered Java to increment counter | Place quiescence barrier at callback source and wait for in-flight |
| Holding `synchronized` lock during `unregisterAndJoin` | Callback must acquire the same lock to finish: deadlock | Transition state under lock, release lock before waiting |
| Calling `close()` from a callback and waiting for `inFlight == 0` | Waiting on the currently running callback itself | Offload cleanup to a coordinator thread, handle reentrancy |
| Storing `JNIEnv*` in a field used on another thread | Thread-local JNI interface is invalid | Store `JavaVM*`; attach/detach on the right thread |
| Deleting `GlobalRef` while callback still uses it | Accessing a Java reference no longer guaranteed alive | Delete after native drain, use clear lifetimes |
| Letting an exception escape an FFM upcall target | Can abruptly terminate the JVM | Catch, log, and translate into an ABI-appropriate error code |
| Calling `Arena.close()` twice / from wrong thread | `IllegalStateException` / `WrongThreadException` | Idempotent wrapper, single close owner, right arena |

**Dangerous reverse path:** `close` holds lock M → calls `unregister` → native waits for callback → callback calls Java and waits for M. No timeout makes this lock cycle safe. Release the lock before waiting for callbacks and avoid calling `close` back from inside a callback.

## 6. Runnable Java 17+ Sample: Simulating Shutdown with an Active Callback

The following sample only **simulates** a native worker with a Java thread to verify ordering. It does not register a real JNI/FFM callback; in an application, `unregisterAndDrain()` must be implemented using the corresponding C API contract and guarantee no new callbacks. `CountDownLatch` ensures the running callback completes before simulating handle destruction.

Create file `ShutdownOrderDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class ShutdownOrderDemo {
    private final CountDownLatch entered = new CountDownLatch(1);
    private final CountDownLatch release = new CountDownLatch(1);
    private volatile boolean accepting = true;
    private Thread callbackThread;

    void startOneCallback() {
        callbackThread = new Thread(() -> {
            if (!accepting) {
                return;
            }
            entered.countDown();
            try {
                release.await(); // simulate callback processing
                System.out.println("callback: completed");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "native-callback-sim");
        callbackThread.start();
    }

    void awaitCallbackStarted() throws InterruptedException {
        entered.await();
    }

    void stopAccepting() {
        accepting = false;
        System.out.println("1. stop accepting");
    }

    void unregisterAndDrain() throws InterruptedException {
        System.out.println("2. unregister and drain");
        release.countDown();
        callbackThread.join(); // wait for callback to exit completely
    }

    void destroyHandle() {
        System.out.println("3. destroy native handle");
    }

    void freeMemory() {
        System.out.println("4. free native memory");
    }

    void unloadLibrary() {
        System.out.println("5. unload library (if supported)");
    }

    public static void main(String[] args) throws InterruptedException {
        ShutdownOrderDemo demo = new ShutdownOrderDemo();
        demo.startOneCallback();
        demo.awaitCallbackStarted();

        demo.stopAccepting();
        demo.unregisterAndDrain();
        demo.destroyHandle();
        demo.freeMemory();
        demo.unloadLibrary();
    }
}
```

Compile and run:

```bash
javac ShutdownOrderDemo.java
java ShutdownOrderDemo
```

Stdout (in deterministic order thanks to `await` and `join`):

```text
1. stop accepting
2. unregister and drain
callback: completed
3. destroy native handle
4. free native memory
5. unload library (if supported)
```

**Key takeaway:** before line 3 is printed, `join` has returned, so the simulated callback thread has finished. The sample does not demonstrate native ownership or the possibility of new callbacks after unregister; those are guarantees that must be obtained from the real native library. Do not copy `accepting` + `join` as a general-purpose safety algorithm for every C API.

## 7. FFM Java 22+: Lifetime of Upcall Stubs, MemorySegment, and Libraries

FFM was finalized as an official API in JDK 22 (`java.lang.foreign`). `Linker.upcallStub(target, descriptor, arena)` creates a function pointer whose lifetime is tied to `arena`; `MemorySegment`s managed by an arena cannot be validly accessed after the arena is closed. `Arena.ofConfined()` can only be accessed/closed by the owning thread; `Arena.ofShared()` allows multi-thread access but **does not automatically make the native callback protocol thread-safe**. `Arena.global()` cannot be closed explicitly. `Arena.ofAuto()` depends on GC and is unsuitable for precise shutdown requirements.

The FFM example below runs on **JDK 22+**, creating an upcall stub and buffer but **not passing the pointers to a native library**. It only illustrates arena lifecycles; if registering the stub with a real library, `unregister + drain` must be performed before closing `callbackArena`.

Create file `FfmArenaOrderDemo.java`:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class FfmArenaOrderDemo {
    public static void onEvent(int value) {
        try {
            // In practice: handle event; never let errors escape across the ABI.
            if (value < 0) {
                throw new IllegalArgumentException("negative event");
            }
        } catch (Throwable error) {
            System.err.println("callback error: " + error.getMessage());
        }
    }

    public static void main(String[] args) throws Throwable {
        Arena libraryArena = Arena.ofShared();
        Arena dataArena = Arena.ofShared();
        Arena callbackArena = Arena.ofShared();

        try {
            MethodHandle target = MethodHandles.lookup().findStatic(
                FfmArenaOrderDemo.class,
                "onEvent",
                MethodType.methodType(void.class, int.class));

            MemorySegment stub = Linker.nativeLinker().upcallStub(
                target,
                FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT),
                callbackArena);

            MemorySegment data = dataArena.allocate(ValueLayout.JAVA_LONG);
            data.set(ValueLayout.JAVA_LONG, 0, 42L);
            System.out.println("data=" + data.get(ValueLayout.JAVA_LONG, 0));

            // Stub was never registered: no in-flight callbacks.
            // In a real application: register(stub, data), then stop/unregister/drain.
            if (stub.address() == 0) {
                throw new AssertionError("unexpected null stub");
            }
        } finally {
            callbackArena.close();
            System.out.println("callback arena closed");
            dataArena.close();
            System.out.println("data arena closed");
            libraryArena.close();
            System.out.println("library arena closed");
        }
    }
}
```

Command to run the code above (JDK 22+):

```bash
javac FfmArenaOrderDemo.java
java --enable-native-access=ALL-UNNAMED FfmArenaOrderDemo
```

Expected stdout:

```text
data=42
callback arena closed
data arena closed
library arena closed
```

`libraryArena` in the example is an empty arena and **does not load any library**. In real integration, you can create a lookup with `SymbolLookup.libraryLookup(path, libraryArena)`, obtain downcall handles, and keep the library alive until after native destructors. Closing the library arena must come after all calls using the library's symbols. `System.loadLibrary` belongs to the separate JNI/class loader model; closing an empty `libraryArena` does not unload a library loaded via JNI.

In FFM, if Java invokes a downcall holding a segment from a shared arena, closing the arena concurrently may throw `IllegalStateException`; this is **not** a mechanism for stopping unmanaged running callbacks. For callback targets, do not let Java exceptions cross the upcall boundary: the `Linker` API specifies that unhandled exceptions can abruptly terminate the JVM. Callbacks should catch errors, log/record metrics, encode error states into return values matching the C ABI, and keep work brief.

## 8. JNI: Native Threads, GlobalRef, and Unload Timing

With JNI, a Java wrapper typically holds a `long nativeHandle`, while C holds a `jobject` from `NewGlobalRef` so callbacks can call Java. Note the distinctions:

- `JNIEnv*` is only valid for the **current thread**. Native workers created outside the JVM need to obtain `JavaVM*`, call `AttachCurrentThread` when JNI is needed, and `DetachCurrentThread` before the thread exits; do not share `JNIEnv*` across threads.
- A `jobject` local reference must not be stored for use beyond the lifetime of the JNI call that created it. If an asynchronous callback needs a Java object to live longer, create a `NewGlobalRef` and delete it exactly once with `DeleteGlobalRef` after callbacks have stopped.
- When C holds `JavaVM*`, global refs, workers, and class loaders, reference cycles can be created that prevent the library from unloading. Do not use GC or `finalize` as the shutdown coordinator.
- `JNI_OnUnload` is tied to the library/class loader lifecycle and is called in an unpredictable context; it should only perform conservative cleanup. Close sessions, unregister listeners, join native workers, and delete GlobalRefs via explicit APIs beforehand.
- Java 17 can use JNI; whereas the `Arena`, `Linker`, and `MemorySegment` syntax shown above requires JDK 22+ and cannot be compiled verbatim with Java 17.

C/JNI logic template **for illustration, not a standalone program** (`native_*` function names depend on your library):

```c
/* Pseudocode for a session. Do not assume unregister drains automatically. */
void close_session(JNIEnv *env, Session *s) {
    native_stop_new_events(s);
    native_unregister_callback(s);
    native_join_callback_workers(s); /* only returns when in-flight callbacks = 0 */
    native_destroy_object(s->handle); /* still keeps buffer/library valid */
    if (s->listener_global != NULL) {
        (*env)->DeleteGlobalRef(env, s->listener_global);
        s->listener_global = NULL;
    }
    native_free_owned_buffer(s->buffer); /* only if the session truly owns it */
    /* library unload is coordinated after all sessions and native calls */
}
```

If `native_destroy_object` still emits callbacks, `listener_global`, the callback function pointer, and the context must be kept alive until after this call. When a C API cannot separate stop/unregister/destroy, the bridge must enforce the right order and guarantee quiescence per its contract. A C function named `native_join_callback_workers` is only meaningful if it actually waits for **all** relevant callback sources, including callbacks already queued.

## 9. Designing a Single-Owner Wrapper and Handling Close Errors

A wrapper should have clear ownership: one session owns the handle and corresponding arenas; objects that only *borrow* the handle must not close it themselves. You can design `AutoCloseable` with `OPEN → CLOSING → CLOSED` states so that multiple concurrent `close()` calls result in only one thread actually performing cleanup. However, state is only part of it: the code must wait for downcalls currently holding the handle before destroying, and native must guarantee callbacks have stopped.

When multiple cleanup steps can throw errors, do not ignore the consequences of an earlier step. Record the first error, continue with independent steps **that are already safe to run**, and attach subsequent errors as suppressed exceptions; steps that depend on a successful shutdown **must not be run recklessly**. For example, if `unregisterAndDrain` fails and callbacks may still run, do not proceed to free stubs/buffers just to “clean up at all costs”. Report the incomplete close state and how to handle the incident.

`try-with-resources` automatically closes in the reverse order of declaration. It is useful for synchronous resources with clear ownership, but if JNI/FFM has registered asynchronous callbacks, relying solely on the `close()` order of arenas is not enough. A `close` method with stop/drain logic before arenas are closed is required. Do not use `Cleaner`/GC as the mechanism to stop native workers; `Cleaner` is only a fallback reclamation path and offers no timing guarantees.

When a library is shared across multiple sessions, **all** sessions must be closed before unloading the library, typically via a reference count or a module/process-level owner. A single session must not unload a library that is still serving other sessions.

## 10. How to Test Release Order

1. **One running callback:** use a latch/barrier to pause the callback, call `close` from another thread; verify `destroy/free/unload` has not run before the callback finishes.
2. **Registration right around close time:** have threads concurrently register, call native, and close repeatedly; verify no call uses the handle after destroy and release happens only once.
3. **Nested callbacks / reentrant close:** a callback calls a session API or requests close; verify no deadlock and no self-joining of the callback thread.
4. **Unregister failure / timeout:** verify resources still used by native are not freed; log errors clearly and provide a path to isolate or retry cleanup when safe.
5. **Destructor emits a final callback:** verify context/stub/GlobalRef remain alive until the destructor returns.
6. **Multiple sessions sharing a library:** close sessions in arbitrary order, verify the library remains loaded while the last session uses it.
7. **Native instrumentation:** build C/C++ with AddressSanitizer when feasible, use JNI checks (`-Xcheck:jni` on supporting JVMs), run shutdown stress tests, and log `STOP/UNREGISTER/DRAIN/DESTROY/FREE/UNLOAD` milestones; do not treat a single successful run as proof of no races.

Notable symptoms include random crashes in callback stubs, `SIGSEGV/EXCEPTION_ACCESS_VIOLATION` on stop, double-free errors, native threads remaining alive after close, `WrongThreadException` with confined arenas, or `IllegalStateException` when closing an arena still in use. Thread dumps help find lock cycles; native debuggers and sanitizers help verify the source accessing freed addresses.

## 11. Pre-Production Checklist for the Bridge

- Have an ownership table for **every** handle, buffer, callback stub, `user_data`, and library; know the corresponding allocator/free function.
- Know exactly whether the `unregister` API guarantees **quiescence** or only stops new registrations; have a drain/join plan for the latter case.
- All new Java downcalls are blocked; already-started downcalls have finished before destroy.
- Java/native callbacks are no longer running and cannot start anew; no callback is waiting on a lock held by close.
- Native destructors have completed while buffers, callback contexts, and the library are still valid.
- Stub `Arena`s, `GlobalRef`s, and memory are returned only by the owner, exactly once; no borrowed pointers are freed by mistake.
- The library is unloaded only when no sessions or functions need its code; with JNI, accept the class loader lifecycle instead of expecting immediate unload.
- Shutdown errors and timeouts do not lead to unconditional freeing; race, reentrancy, and repeated shutdown tests are in place.

**Conclusion:** safety is not determined merely by the order of calling `close/free/dlclose`. Resources may only be freed after **the source of work has stopped**, **all active users have exited**, and **dependent objects have been destroyed according to ownership**. Callbacks and native workers are what must prove quiescence first; the library containing the cleanup functions is the resource that must live the longest.

### References

- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454).
- [Oracle JDK 22 — Foreign Function and Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).
- [JDK 25 — `Linker` (upcall stubs and callback constraints)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html).
- [JDK 25 — `Arena` (scope, threading, and close)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Arena.html).
- [JDK 22 — `SymbolLookup` (library lifetime and lookup)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [JNI Specification — Invocation API, `AttachCurrentThread`, and `JNI_OnUnload`](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/invocation.html).

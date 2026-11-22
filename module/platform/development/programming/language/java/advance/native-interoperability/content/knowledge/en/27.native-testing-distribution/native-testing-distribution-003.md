# Testing Allocation Failures, Library Error Codes, Callback Exceptions, and Partial Cleanup

A Java program communicating with a C/C++ library can fail **after partially allocating resources**: a native memory region is created but the handle is not opened; the handle is opened but callback registration fails; a callback throws a Java exception while processing; or `close()` only releases half of the resources. Testing the happy path cannot prove these cases are safe.

This lesson presents how to design *failure injection* (controlled, intentional fault induction), classify native error codes, contain callback exceptions at the ABI boundary, and verify *partial cleanup* on Java 17+ with JNI, as well as the Foreign Function & Memory API (FFM) finalized in Java 22. The focus is on **ownership state after each failure**: which resources have been created, who can still use them, who has the right to release them, and what evidence permits moving to the next cleanup step.

## 1. Error Model Across the Java/Native Boundary

| Origin | Typical Symptom | How to Observe | Impact to Test |
| --- | --- | --- | --- |
| Allocation in Java | `OutOfMemoryError`, failure to create wrapper or tracking structures | Java throwable; test injector instead of exhausting RAM | Do not leave already-created native handles orphaned |
| C/C++ memory allocation | `malloc/calloc` returns `NULL`, C++ allocation reports error per contract | Return code, `errno` if API uses it | Release already-owned steps; do not dereference NULL |
| FFM allocation | `Arena.allocate` fails, closed arena/wrong thread, invalid size | Java exception/error matching the corresponding cause | Do not mistake every FFM error for native `ENOMEM` |
| Library returns error code | Non-zero return code, sentinel like `-1` or null pointer | Return value; error state per the C API | Do not treat a resource as successfully created when the result is not guaranteed |
| OS/runtime state | POSIX `errno`, Windows `GetLastError`/Winsock `WSAGetLastError` | Capture immediately per each function's specification | Do not read stale, wrong-thread, or overwritten state |
| Native → Java callback | Listener throws `RuntimeException`, `Error`, callback fails | Bridge catches and records throwable, returns ABI error code | Do not let exceptions escape across FFM upcalls; do not leave JNI pending exceptions unhandled |
| Partial cleanup | `unregister`, `destroy`, `free`, or `close` fails | Actual state and result of each release step | Do not free memory still used by native; do not double-free on retry |
| ABI / native access error | Wrong descriptor, corrupt pointer, use-after-free, race | May crash JVM/process, sanitizer, dump | Run dangerous tests in an isolated process |

**Not every error can be recovered with `try/catch`.** Java errors in wrapper logic can be thrown and handled. However, C access to a freed address, ABI mismatch, or use-after-free can kill the entire JVM before Java can catch an exception. Native testing requires deterministic unit tests, integration tests, and out-of-process tests.

### 1.1. Distinguishing Three Concepts

- **Failure signal:** the function signals failure via a return code, `errno`, null pointer, Java exception, or callback status.
- **Ownership state:** has the resource transitioned from *not acquired* to *owned*, *borrowed*, *released*, or *unknown*?
- **Safety to release:** have all users of the resource finished? In particular, are any callbacks or native workers still running?

A failure return code does not always mean “no change occurred”. For example, `register_callback` might complete registration and then fail when starting a worker; `native_destroy` might release part of a structure before returning an error. Only assume **fail-before-effect** when the C API documentation or your own wrapper guarantees it. If the state after failure is undetermined, mark it **UNKNOWN / QUARANTINED**, and do not speculatively call `free` or `destroy` again.

## 2. Error and Ownership Contracts Must Be Written Before Testing

Consider a native session with these steps:

```text
Java wrapper
  ├─ 1. allocate buffer B                 [Java/C/FFM owner]
  ├─ 2. create native handle H            [native object owner]
  ├─ 3. create callback context/stub U/S   [Java/arena owner]
  ├─ 4. register callback R with H        [library registration]
  ├─ 5. start worker / perform operation  [asynchronous users]
  └─ close: stop → unregister/drain → destroy H → free U/S/B
                           → unload library when allowed
```

The dependency graph must be explicitly documented:

```text
Callback R still running  ──needs──> U/S + H + library
Native handle H           ──may need──> buffer B + library
destroy/free function     ──needs──> library still loaded
```

If a final callback can occur during `destroy(H)`, the context/stub must stay alive until **after** `destroy`; if the destructor uses buffer B, then B can only be freed **after** the destructor returns. The exact order depends on the native contract, not merely the allocation order.

Each bridge function should be specified using five questions:

1. Which value signals success? Should `errno` or an error object also be retrieved?
2. On failure, could output resources have been partially allocated or registered?
3. Is the output **owned**, **borrowed**, or transferred in ownership to the library?
4. Are there asynchronous side effects (threads, callbacks, queues) after the function returns?
5. Is cleanup **idempotent**, retryable, and does it guarantee quiescence?

A sample table:

| Illustrative API | Success | On Failure | Owner After Success | Cleanup Condition |
| --- | --- | --- | --- | --- |
| `native_alloc(n, &p)` | `OK`, `p != NULL` when `n > 0` | `ERR_NOMEM`; **if** contract guarantees `p == NULL` | Caller | No remaining borrowed pointers; `native_free(p)` once |
| `native_create(p, &h)` | `OK` and valid handle | May have already taken ownership of `p` depending on API | Caller or library | All downcalls finished; call the right destructor |
| `native_register(h, fn, ctx)` | `OK` | May have a half-registered callback if API is not atomic | Owner of registration | Unregister **and** drain, per contract |
| `native_close(h)` | `OK` | Resource may still be alive or partially closed | Unknown if API does not specify | Do not retry before knowing the actual state |

*Function names and `ERR_*` codes in the table are design models, not standard Java or C APIs.*

## 3. Testing Allocation Failures: Inject Failures Precisely Instead of Exhausting Memory

### 3.1. Failing at Every Allocation Point

In native tests, replace `malloc` or an allocator you own with a gate that can fail on the Nth call:

```c
/* C11: illustrative fault injector; use in a test bridge you own. */
#include <stddef.h>
#include <stdlib.h>

typedef struct {
    size_t calls;
    size_t fail_at; /* 0 = do not inject failure */
} AllocFault;

static void *test_malloc(AllocFault *fault, size_t size) {
    ++fault->calls;
    if (fault->fail_at != 0 && fault->calls == fault->fail_at) {
        return NULL;
    }
    return malloc(size);
}
```

For an initialization path with N allocations, run N+1 scenarios: 1st fails, 2nd fails, ..., Nth fails, and (N+1)th does not inject failure. **Do not test by allocating massive amounts of RAM**: the OS may overcommit, kill the process, or break CI determinism.

When the wrapper uses `errno`, the injector must accurately simulate the allocator's *contract*: if native code expects `errno == ENOMEM` after `malloc` returns NULL, the injector must set `errno` accordingly. Do not apply that rule to every custom allocator: many libraries return their own error codes and do not use `errno`.

When allocating `n * sizeof(T)`, check for integer overflow **before** multiplying; 0-byte allocations also need separate handling because `malloc(0)` may return NULL or a freeable pointer depending on the implementation. Do not automatically interpret every `NULL` as `ENOMEM` if size 0 was passed.

### 3.2. Verification After Each Failure Injection

After each case, verify:

- Every resource that was actually allocated is released exactly once **when safety conditions are met**.
- Do not call `destroy` on an uncreated handle or `free` on memory owned by another party.
- Output pointers/handles are in a valid state per the contract (e.g., null when opening fails before creation).
- The original error is not replaced by an exception thrown during rollback.
- No callback or worker still holds a pointer to freed memory.
- A subsequent successful initialization after a previous failed attempt still works properly.

**Distinguish JVM heap from native memory.** `OutOfMemoryError` is not only about the Java heap: some off-heap or runtime operations can also throw OOME. Conversely, `malloc` returning NULL in C does not automatically turn into `OutOfMemoryError` in Java. A JNI wrapper may return an error code or throw an exception depending on the design. Real out-of-memory errors often cause exception/log creation or tracking structures to fail as well; test this separately with a controlled fault hook and keep the cleanup path as allocation-free as possible.

### 3.3. FFM and JNI Boundaries

- FFM `Arena.allocate(...)` has a lifetime tied to the arena. Accessing after closing the arena or from the wrong confined thread is a scope/thread error; do not lump it into “native out-of-memory allocation” reports. C functions called via `Linker.downcallHandle` can still return NULL/error codes; FFM does not automatically map them into meaningful domain Java exceptions.
- JNI `NewGlobalRef` can fail and report a JVM allocation error. Check return values/pending exceptions per JNI; do not try to continue a callback with an uncreated global reference. A `jobject` local reference must not be kept as an asynchronous context; only use a global ref when the contract requires it and delete it after native stops using it.
- Memory created by `malloc` must be freed using the corresponding allocator; memory owned by a native object must be released by its destructor. Avoid calling `free` on a region managed by an `Arena` or another library.

## 4. Native Error Codes: Return Value, `errno`, and Platform State

### 4.1. Return Code Is the Primary Signal of a C API

For example, a custom C API might define:

```c
/* Illustrative ABI: not a standard OS API. */
enum {
    NATIVE_OK = 0,
    NATIVE_ERR_NO_MEMORY = 1001,
    NATIVE_ERR_INVALID_STATE = 1002,
    NATIVE_ERR_CALLBACK = 1003,
    NATIVE_ERR_IO = 1004
};

int native_open_session(const char *path, void **out_handle);
```

The Java bridge must check `rc` before using `out_handle`; only map documented codes to specific exceptions. For unknown codes, preserve the code and operation name for diagnostics. Do not assume `rc < 0` means error: some libraries use negative numbers, positive numbers, null sentinels, or error objects. Tests must include unrecognized codes and boundary values per the contract.

Errors should include context: **operation, call path, library code, OS code if valid, ownership state**. Do not put secrets, raw pointers, access tokens, or sensitive content into logs.

### 4.2. `errno` Must Be Read at the Right Time and Under the Right Conditions

`errno` is the platform-specific thread-local error state of the C runtime; many functions only define its value **when returning failure**. Success does not mean `errno` is reset to 0. Another native function called afterward may overwrite `errno` before Java/the bridge reads it.

```c
/* C POSIX: illustrative immediate capture after a C function documented to use errno. */
#include <errno.h>

int rc = operation_using_errno();
int captured_errno = errno; /* capture immediately, before another C call */
if (rc == -1) {
    /* Use captured_errno; do not re-read errno after logging/formatting the error. */
}
```

Here `operation_using_errno()` is an illustrative function name, **not a complete C example to compile**. Always prefer APIs that return explicit error codes if the library provides them. Do not infer an error from `errno` when the return value indicates success.

For Windows, only use `GetLastError()` after Win32 calls specified by the documentation; for Winsock there is the `WSAGetLastError()` API. Do not treat `errno`, `GetLastError`, and `WSAGetLastError` as an equivalent error code pool. Error numbers and names may differ across operating systems and C libraries.

### 4.3. FFM Java 22+: Capturing Error State Alongside Downcalls

FFM provides `Linker.Option.captureCallState("errno")` to capture `errno` immediately after a native downcall. A capture-state `MemorySegment` argument is added to the method handle per the signature generated by the linker; the capture region must have a layout compatible with `Linker.Option.captureStateLayout()`. For fixed functions not needing an implicit allocator/result buffer, the capture-state argument precedes regular C arguments. Read the value using a `VarHandle` to the field named `errno`.

```java
// Java 22+ illustrative snippet; functionAddress/descriptor/arguments
// must be resolved from your real C ABI and handle signature.
Linker linker = Linker.nativeLinker();
Linker.Option capture = Linker.Option.captureCallState("errno");
StructLayout stateLayout = Linker.Option.captureStateLayout();
VarHandle errnoField = stateLayout.varHandle(
    MemoryLayout.PathElement.groupElement("errno"));

MethodHandle call = linker.downcallHandle(
    functionAddress, descriptor, capture);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment state = arena.allocate(stateLayout);
    // Invoke call with state as the first argument,
    // then pass the exact C arguments per descriptor.
    // Only read errnoField when the return code indicates failure and the API uses errno.
}
```

This is an **integration snippet** requiring imports of `java.lang.foreign.*`, `java.lang.invoke.*`, and a valid symbol with `FunctionDescriptor`; it is not a standalone program. Supported capture names depend on the platform; use `captureStateLayout()` to inspect fields rather than assuming `GetLastError` always exists. For downcalls on native threads or asynchronous callbacks, errors must be captured from the **exact call/exact thread**.

### 4.4. Do Not Retry Blindly

An `EINTR` may allow retry **if** the function and side-effect state permit it. `EAGAIN` may require a retry schedule, whereas `ENOMEM` usually requires throttling/canceling the request. Functions that have partially created a session, partially sent a packet, or committed changes are not necessarily safe to call again. Every retry must have a defined idempotency and ownership of the previous call.

## 5. Callback Exceptions: Block at the ABI Boundary, Record to Report Back

### 5.1. A Failing Java Listener Is Not a C Error Code

Native code may hold a function pointer to call Java later. The C ABI requires the callback to return `int` or `void` per its signature; a Java exception is not a C return value form. With FFM upcalls, **do not let exceptions from the MethodHandle target escape**: the Linker documentation warns that uncaught exceptions can cause the JVM to terminate abruptly.

A Java callback wrapper can convert the error into an ABI code and store the first error for Java to actively inspect at a safe point:

```java
// Logic pattern (non-standalone): eventHandler is the application callback.
private static final int CALLBACK_FAILED = -700;
private final java.util.concurrent.atomic.AtomicReference<Throwable>
    firstCallbackFailure = new java.util.concurrent.atomic.AtomicReference<>();

int dispatchEventSafely(int eventCode) {
    try {
        eventHandler.accept(eventCode);
        return 0;
    } catch (Throwable ex) {
        // Do not let a Java Throwable cross the upcall boundary.
        firstCallbackFailure.compareAndSet(null, ex);
        return CALLBACK_FAILED;
    }
}
```

The value `-700` is only an **example code**, and must match the C API contract in real implementations. Catching `Throwable` at the upcall boundary prevents exceptions from escaping across the ABI; specifically for `OutOfMemoryError`, `ThreadDeath`, and serious JVM errors, a fail-safe policy is needed, avoiding allocating more objects/logs when the system is starved of resources. Saving the throwable into a stable reference is the minimum; do not promise normal continuation after every `Error`.

Do not invoke the listener infinitely on repeated failures; specify whether a callback failure causes native code to stop the session, reject events, report an error on the next downcall, or push into an error queue. Test those exact semantics. When multiple callbacks run concurrently, decide whether to keep the first error, aggregate errors, or record all within memory bounds.

### 5.2. JNI Callbacks: Checking Pending Exceptions

After `CallVoidMethod` / `CallObjectMethod` into Java, native C must check `ExceptionCheck`. There are two valid strategies:

1. For **native methods called synchronously by Java**, stop work and return so the pending exception propagates back to Java, if the contract allows and no invalid cleanup occurs.
2. For **callbacks on native workers**, actively capture/record the exception via JNI and then `ExceptionClear` before continuing JNI operations disallowed while an exception is pending; deliver the error through a separate error channel.

```c
/* C/JNI pseudocode: env, listener, and on_event are validly initialized. */
(*env)->CallVoidMethod(env, listener, on_event, event_code);
if ((*env)->ExceptionCheck(env)) {
    jthrowable thrown = (*env)->ExceptionOccurred(env); /* local ref */
    (*env)->ExceptionClear(env);                        /* clear before normal JNI */
    /* record thrown via a valid error channel, may need NewGlobalRef */
    /* delete local ref; check for errors when creating global ref */
    (*env)->DeleteLocalRef(env, thrown);
    return CALLBACK_FAILED; /* this value belongs to the illustrative ABI */
}
return CALLBACK_OK;
```

The snippet above only shows the handling order; `CALLBACK_FAILED`/`CALLBACK_OK`, error channel, and JNI objects are application-provided. Do not retain the `thrown` local reference across different callbacks; if a longer lifetime is needed, create a `NewGlobalRef` and `DeleteGlobalRef` at the right time. If `NewGlobalRef` also fails due to out-of-memory, have a fallback error reporting path without continuing to use a null reference.

When a thread is created on the C side, it must attach using `JavaVM.AttachCurrentThread` before obtaining `JNIEnv*` and detach according to the corresponding rules. `JNIEnv*` **is not shared across threads**. In particular, test callback errors on both Java-created threads and attached native workers.

### 5.3. Callback Tests Must Check More Than One Exception

- Listener throws `IllegalArgumentException`; native receives the expected error code, JVM does not die, error can be retrieved by Java.
- Listener throws before updating state; rollback/ack of the event follows the contract, without assuming the event was processed.
- Listener throws when a callback occurs concurrently with close; context stays alive until native is quiescent.
- Callback fails right during unregister/destroy if the destructor can call back; do not free stub/global ref too early.
- Exceptions during error reporting (logging, secondary listener) must also be blocked from the ABI boundary; do not mask the original error.
- Wrong function pointer/ABI signature is not a business exception to catch; test in an isolated process and use native sanitizers.

## 6. Partial Cleanup: Safety Rules When Cleanup Itself Fails

**Cleanup is a conditional sequence of operations**, not a `finally { freeEverything(); }` list regardless of state. A common order:

```text
OPEN
  │
  ├─ stop accepting Java calls / transition to CLOSING
  ├─ stop native producer
  ├─ unregister callbacks + drain/join existing callbacks
  │      └─ if NOT quiescent: keep stub/context/handle/buffer alive
  ├─ destroy handle (when no users remain; destructor dependencies still alive)
  │      └─ if result is UNKNOWN: do not free buffers that might still be used
  ├─ release callback context + GlobalRef + upcall stub (at the right time)
  ├─ free externally owned buffer, close its Arena
  └─ release/unload library (if loading model allows)
CLOSED
```

There is no single order for all libraries: if `destroy` can invoke a final callback, the callback must be kept alive until after `destroy`. If the native object owns the buffer itself, the destructor frees the buffer, and Java must not free it a second time. A cleanup failure must halt **dependent steps that are no longer safe**, while independent cleanup steps proven safe may proceed.

### 6.1. States to Track

| State | Meaning | Allowed to Release Dependent Resources? |
| --- | --- | --- |
| `NOT_ACQUIRED` | Allocation step has not run or guaranteed fail-before-effect | No need to free |
| `ACQUIRED` | Caller owns a valid resource | Only when all borrowers have stopped |
| `BORROWED` | Library/other object owns it | Do not free directly |
| `QUIESCING` | Stopping producer, callbacks may still exist | Do not free stub/context yet |
| `QUIESCENT` | Native guarantees no new/in-flight callbacks | May release callback resources per remaining dependencies |
| `RELEASED` | Release succeeded unambiguously | Do not release again |
| `UNKNOWN` | Cleanup returned an error and may have partial side effects | Quarantine, do not speculatively retry |

Track state per resource, not just a session-wide `boolean closed`. A session may have unregistered callbacks yet still hold a handle/buffer because destroy failed. If a `free` API returns `void` and has undefined behavior on double free, you cannot “test retry” in the same process on a pointer suspected of already being freed.

### 6.2. Original Error and Cleanup Error

Java `try-with-resources` has a suppressed exceptions mechanism: when the body throws an error and `close()` also throws an error, the error from close is attached to the body error. When writing manual rollback:

```java
Throwable original = ...; // illustrative snippet, not a standalone method
try {
    releaseResourcesWhosePreconditionsHold();
} catch (Throwable cleanupFailure) {
    original.addSuppressed(cleanupFailure);
}
```

The snippet above only illustrates **preserving the original error**; it does not permit running cleanup regardless of safety conditions. Ensure `releaseResourcesWhosePreconditionsHold()` only selects independent steps valid for the state. In real applications, avoid guessing the order from function names; specify the exact behavior for each native API.

When cleanup fails and the state is uncertain, do not declare `CLOSED` and drop the last reference to the resource. You can keep the session in `CLOSE_FAILED/QUARANTINED`, emit a warning, and let a pre-designed recovery mechanism handle it; sometimes keeping a resource until process exit is safer than use-after-free.

## 7. Runnable Java 17+ Example: Fault Matrix and Partial Cleanup

The example below uses `FakeNative` in place of a C library. The injector **intentionally fails before modifying the state of the corresponding operation**; therefore the test can retry after clearing the injection. Real native APIs do not inherently have this property. `drain()` in the fake does not spawn a worker: it represents a native API that guarantees no in-flight callbacks remain; this is an ownership and error simulation, and **does not prove** an asynchronous callback protocol in practice. The example runs sequentially to focus on failure injection; a production wrapper must synchronize when multiple threads concurrently call native/close.

Create `NativeFailureMatrixDemo.java`:

```java
public final class NativeFailureMatrixDemo {
    static final int CALLBACK_ERROR = -700;

    static final class NativeFailure extends Exception {
        final int code;
        NativeFailure(String operation, int code) {
            super(operation + " failed, code=" + code);
            this.code = code;
        }
    }

    static final class FakeNative {
        String failAt;
        boolean buffer, handle, callbackRegistered;
        int freed, destroyed, unregistered;
        Throwable callbackFailure;

        FakeNative(String failAt) {
            this.failAt = failAt;
        }

        void maybeFail(String operation) throws NativeFailure {
            if (operation.equals(failAt)) {
                throw new NativeFailure(operation,
                    operation.equals("alloc") ? 12 : 5);
            }
        }

        void allocate() throws NativeFailure {
            maybeFail("alloc");
            buffer = true;
        }

        void create() throws NativeFailure {
            if (!buffer) throw new IllegalStateException("no buffer");
            maybeFail("create");
            handle = true;
        }

        void register() throws NativeFailure {
            if (!handle) throw new IllegalStateException("no handle");
            maybeFail("register");
            callbackRegistered = true;
        }

        int fireCallback(Runnable listener) {
            if (!callbackRegistered) {
                throw new IllegalStateException("callback not registered");
            }
            try {
                listener.run();
                return 0;
            } catch (Throwable failure) {
                callbackFailure = failure;
                return CALLBACK_ERROR;
            }
        }

        void drain() throws NativeFailure {
            maybeFail("drain");
            // Real native API: must prove no in-flight or future callbacks.
        }

        void unregister() throws NativeFailure {
            if (!callbackRegistered) return;
            maybeFail("unregister");
            callbackRegistered = false;
            unregistered++;
        }

        void destroy() throws NativeFailure {
            if (!handle) return;
            if (callbackRegistered) {
                throw new IllegalStateException("callback still registered");
            }
            maybeFail("destroy");
            handle = false;
            destroyed++;
        }

        void free() throws NativeFailure {
            if (!buffer) return;
            if (handle) {
                throw new IllegalStateException("handle still uses buffer");
            }
            maybeFail("free");
            buffer = false;
            freed++;
        }
    }

    static final class Session implements AutoCloseable {
        private final FakeNative api;
        private boolean closed;

        private Session(FakeNative api) {
            this.api = api;
        }

        static Session open(FakeNative api) throws NativeFailure {
            try {
                api.allocate();
                api.create();
                api.register();
                return new Session(api);
            } catch (NativeFailure original) {
                try {
                    api.drain();
                    api.unregister();
                    api.destroy();
                    api.free();
                } catch (NativeFailure cleanupError) {
                    original.addSuppressed(cleanupError);
                }
                throw original;
            }
        }

        @Override
        public void close() throws NativeFailure {
            if (closed) return;
            api.drain();
            api.unregister();
            api.destroy();
            api.free();
            closed = true;
        }
    }

    static void checkClean(FakeNative api) {
        if (api.buffer || api.handle || api.callbackRegistered
                || api.freed > 1 || api.destroyed > 1
                || api.unregistered > 1) {
            throw new AssertionError("invalid ownership or double cleanup");
        }
    }

    public static void main(String[] args) throws Exception {
        for (String phase : new String[] {"alloc", "create", "register"}) {
            FakeNative api = new FakeNative(phase);
            try {
                Session.open(api);
                throw new AssertionError("expected " + phase + " failure");
            } catch (NativeFailure expected) {
                if (!expected.getMessage().startsWith(phase + " failed")) {
                    throw expected;
                }
            }
            checkClean(api);
            System.out.println(phase + " failure: rollback OK");
        }

        FakeNative api = new FakeNative(null);
        try (Session session = Session.open(api)) {
            int status = api.fireCallback(() -> {
                throw new IllegalArgumentException("bad event");
            });
            if (status != CALLBACK_ERROR
                    || !(api.callbackFailure instanceof IllegalArgumentException)) {
                throw new AssertionError("callback exception escaped");
            }
        }
        checkClean(api);
        System.out.println("callback exception: contained and cleaned");

        for (String phase : new String[] {
                "drain", "unregister", "destroy", "free"}) {
            FakeNative failing = new FakeNative(phase);
            Session session = Session.open(failing);
            try {
                session.close();
                throw new AssertionError("expected " + phase + " failure");
            } catch (NativeFailure expected) {
                if (!expected.getMessage().startsWith(phase + " failed")) {
                    throw expected;
                }
            }
            // Must retain every resource still needed by the failed phase.
            if (phase.equals("drain") || phase.equals("unregister")) {
                if (!failing.buffer || !failing.handle
                        || !failing.callbackRegistered) {
                    throw new AssertionError("released while callbacks possible");
                }
            } else if (phase.equals("destroy")) {
                if (!failing.buffer || !failing.handle
                        || failing.callbackRegistered) {
                    throw new AssertionError("invalid partial destroy state");
                }
            } else {
                if (!failing.buffer || failing.handle
                        || failing.callbackRegistered) {
                    throw new AssertionError("invalid partial free state");
                }
            }

            // The fake guarantees fail-before-effect; a real API may not.
            failing.failAt = null;
            session.close();
            session.close();
            checkClean(failing);
            System.out.println(phase + " failure: retained, recovered");
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac --release 17 NativeFailureMatrixDemo.java
java NativeFailureMatrixDemo
```

Exact stdout of the program:

```text
alloc failure: rollback OK
create failure: rollback OK
register failure: rollback OK
callback exception: contained and cleaned
drain failure: retained, recovered
unregister failure: retained, recovered
destroy failure: retained, recovered
free failure: retained, recovered
```

In the first pass, failures at `alloc/create/register` cause `open()` to properly roll back owned resources. In the callback pass, the Java exception is captured in `callbackFailure` and converted into `CALLBACK_ERROR`; afterward the session closes. The last four passes prove **you must not delete resources that are still dependencies**:

- `drain` or `unregister` failure: retain registration, handle, and buffer.
- `destroy` failure: callback has been unregistered, but handle and buffer remain.
- `free` failure: handle has been destroyed, buffer remains recorded as owned.

After the injector is turned off, the fake allows retry and guarantees each destructor runs at most once. **Do not apply this retry to a real native destructor without knowing whether it is fail-before-effect**; some APIs return an error after partially freeing. The program only checks artificial state logic; real JNI/FFM tests with a real native implementation are needed to prove quiescence, allocators, and lifetimes.

## 8. Essential Native Failure Test Matrix

| Injection Point / Scenario | Expected Result | Invariant to Verify |
| --- | --- | --- |
| 1st...Nth malloc/calloc fails | Out-of-memory error code, no crash | Each previously created resource is cleaned up appropriately |
| `malloc(0)` and overflowing size multiplication | Explicit size handling; reject overflow | Do not mistake NULL from size 0 for a definite error |
| Native create returns error **before** side effect | No valid handle | Do not call destroy with a non-existent handle |
| Native create returns error **after** partial side effect | Uncertain state is exposed | Do not mistakenly free a buffer still held by native |
| Register callback returns error when worker already started | Quiescence is still performed | Stub/context stays alive until the last callback completes |
| Native returns unknown error code | Exception preserves code and operation | Do not coerce unrecognized code into success |
| Return success but `errno` is non-zero | Success per return code | Do not produce false positive from stale errno |
| Return error with `errno` changed after logging | Snapshot remains accurate | Read/capture before any other C call |
| Java callback throws `RuntimeException` | Returns callback error per ABI | No exception escapes FFM upcall |
| Java callback throws `Error` | Fail-safe policy is triggered | Do not rely on logger/allocator when out of RAM |
| JNI callback has pending exception | Propagated or intentionally cleared | Do not call arbitrary JNI while pending |
| Callback and close race | Shutdown waits for native quiescence | No use-after-free of callback/global ref |
| Unregister/drain fails | Dependent steps are blocked | Do not destroy/free while native may still use them |
| Destroy fails with unknown side effect | Session transitions to `UNKNOWN` | Do not auto-retry or speculatively free |
| Free fails | Ownership is marked per contract | No double-free or false CLOSED marking |
| Cleanup fails again after original error | Original error preserved, later error suppressed | Diagnostic info and partial state available |
| Close called twice/concurrently | Single owner releases, close ends consistently | Do not break resources currently borrowed by another thread |
| Multiple sessions share the same library | Independent sessions are closed individually | Do not unload library while another session still uses it |

A test case should verify **API result + resource ledger + event ordering**, rather than only asserting the exception class. Example per-session log:

```text
session=17 ACQUIRE_BUFFER
session=17 CREATE_HANDLE
session=17 REGISTER_CALLBACK
session=17 INJECT_ERROR operation=UNREGISTER
session=17 CLOSE_FAILED retains=callback,handle,buffer
```

In real products, this log should only contain logical IDs; avoid logging raw pointers, sensitive content, or addresses of user data.

## 9. JNI/FFM Integration Testing Scenarios with Real Libraries

### 9.1. Test Seams in C/C++ and Java

To avoid altering production behavior, place injectors behind a dedicated test/build flag or an internal allocator adapter. You can replace:
- Allocator: `malloc/calloc/realloc` or custom allocator, controlling failure on the Nth call.
- Native operations: `open/register/read/destroy`, intentionally forcing error codes and determining whether side effects occurred.
- Callback: listener intentionally throws, sleeps on a latch, calls nested close, or keeps callback active while another thread closes.
- Cleanup: release operations with independent fault injection points and a post-error state ledger.

Do not modify third-party library behavior by assuming it has built-in hooks; you can write a **test-only shim** that owns the C ABI and forwards to the real library. The shim must be built with the exact calling convention, layout, pointer width, and clearly labeled so it is never mistakenly packaged in production artifacts.

### 9.2. Deterministic Asynchronous Testing

Use a latch/barrier before the callback critical section to stage races:

```text
NATIVE thread: callback starts → signal ENTERED → wait for RELEASE
JAVA thread:   wait for ENTERED → close() → verify not freed yet
TEST thread:   signal RELEASE → wait for close to finish → verify freed once
```

Set timeouts for **test orchestration**, but do not turn a timeout into permission to free non-quiescent native resources. An `unregister` function returning early does not prove callbacks have finished. Also test callbacks that are already queued but have not started yet, because a Java-side `inFlight` counter may not have incremented yet. Native shutdown must have a barrier preventing new callbacks and wait for already-dispatched callbacks.

If the native destructor can call back into Java, keep the callback context alive until the destructor finishes and test cases where the destructor throws an error or the callback returns an error. Avoid having `close` hold a Java monitor that the callback must acquire; that situation can deadlock.

### 9.3. Out-of-Process Testing for Dangerous Errors

Errors such as ABI mismatch, freeing with the wrong allocator, use-after-free, and double-free in native code can kill the JVM. Run separate tests as **subprocesses** with timeout/exit code/stdout/stderr and core/minidump when needed, so they do not bring down the entire test suite. Use AddressSanitizer/UndefinedBehaviorSanitizer when supported by the C/C++ build, `-Xcheck:jni` on supported JVMs, native debuggers, and checks for surviving threads and still-owned memory regions.

Do not rely solely on `System.gc()` or `Cleaner` to detect and fix lifetime bugs. GC does not decide when native callbacks stop and does not replace explicit close. Leak detection tools must also recognize valid process-wide allocations; compare deltas after create/destroy cycles against a warm-up and baseline.

### 9.4. Multi-Environment Distribution Testing

The parent topic is **Testing and Distribution**: a native library is an artifact dependent on OS, CPU architecture, compiler/ABI, and JDK. A test suite passing on Windows x64 is not enough to prove Linux x64, macOS arm64, or C runtime differences are safe. A CI matrix should distinguish:

| Variable | What to Check |
| --- | --- |
| OS/runtime | Linux/macOS/Windows: loader, errno/Win32 error, allocator, library name |
| Architecture | 32/64-bit if supported, alignment, `size_t`/pointer size |
| JDK | Java 17+ JNI; Java 22+ for FFM final API |
| Build | Debug + sanitizer, release/optimized if needed |
| Concurrency | Single thread, native worker callback, concurrent close |
| Packaging | Correct library version and dependencies; artifact contains no test shim |
| Lifecycle | Init failure, normal shutdown, shutdown on error, process restart |

FFM native access has permission mechanisms depending on JDK version/execution mode; configure `--enable-native-access` appropriately when needed. Passing JNI runs do not translate to FFM: the two paths have different lifetimes, exception handling, and library loading mechanisms.

## 10. Commonly Missed Design Errors

**1. Only testing that an exception is thrown.** An `assertThrows` test confirms the error signal but does not prove memory was freed properly, callbacks stopped running, or handles did not leak. Check the ledger/event sequence and sanitizer warnings.

**2. Reading `errno` after building the error message.** Formatters, loggers, or other native calls can overwrite `errno`. Capture it immediately alongside the native operation and only use it if the return code indicates failure per the contract.

**3. Setting `closed=true` at the very start of `close()`.** If `unregister` fails, the wrapper is already marked closed while the native callback still holds a reference. Separate `CLOSING/CLOSE_FAILED` states and remaining resource owners are needed.

**4. A `finally` calling all destructors regardless of drain results.** When callbacks can still run, freeing the stub/context is a use-after-free. Cleanup is conditional; an initial failure may require deferring subsequent steps.

**5. Retrying destroy after an error with unknown side effects.** The destructor may have already freed the pointer and then reported an error due to flush or external I/O. Only retry if the API guarantees it is safe/idempotent or there is a state verification procedure.

**6. Believing Java exceptions cross the C ABI automatically.** An FFM upcall target throwing an uncaught exception is dangerous behavior; JNI requires checking pending exceptions and deciding to propagate/clear. C callback status must be a valid value per the ABI.

**7. Confusing a controlled leak with completed cleanup.** When native is still running and cannot drain, keeping memory alive may be a temporary safe choice. However, you must report the failure, retain ownership/diagnostics, and determine when the process is restarted or recovered; never silently treat the session as closed.

**8. Ignoring errors when cleaning up another error.** If `open()` fails and `close()` also fails, report both the original error and suppressed/secondary diagnostics. There may be unreleased resources; track both.

**9. Testing races with unsynchronized `Thread.sleep`.** Sleep does not prove a callback has started or finished using a pointer. Use latches, barriers, native handshakes, and thread-joins per the contract.

**10. Looking only at the Java heap.** Native allocations, shared libraries, global references, and worker threads do not automatically show up as equivalent Java heap objects. Monitor both native memory and release timing.

## 11. Application Checklist for a Java/Native Module

- [ ] Each function documents return codes/`errno`/Win32 errors and specifies side effects on failure.
- [ ] Each handle, buffer, callback stub, GlobalRef, and library has a single owner; borrowed pointers are distinguished from transferred ownership.
- [ ] Deterministic injectors exist for every acquire point; the test matrix runs each failure individually plus a no-failure pass.
- [ ] Integer overflow, size 0, null pointers, native allocator errors, and JVM reference creation errors are tested where relevant.
- [ ] Java callback errors are caught at the ABI boundary, converted into status codes, and recorded to report back; JNI pending exceptions are handled properly.
- [ ] There is a stop/unregister **and** quiescence step per contract before freeing callback contexts.
- [ ] Failed destructors have a defined state; no automatic retry when side effects are unknown.
- [ ] Rollback preserves the original error and records secondary cleanup errors; no dependent cleanup when unsafe.
- [ ] Unit tests verify the ownership ledger and release counts; integration tests verify native lifetime and recoverability after failure.
- [ ] Stress/concurrency tests use exact barriers; native sanitizers and subprocess tests cover potentially crashing cases.
- [ ] Distribution pipeline runs on supported OSes/architectures and does not package test injectors into production.

**Conclusion:** native error testing meets the bar when it answers two questions simultaneously: **“Was the error accurately reported across the Java/native boundary?”** and **“After the error, what state is each resource in, and is there sufficient evidence to release it?”** Error codes, callback exceptions, and rollback must all be tied to ownership and lifetime; a right exception that leaves a callback pointing to freed memory is still a failing test.

### References

- [OpenJDK JEP 454 — Foreign Function & Memory API (Java 22)](https://openjdk.org/jeps/454).
- [Oracle Java 22 — Foreign Function & Memory API, native errors with errno](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html).
- [dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/).
- [Oracle Java 22 — Linker.Option / captureCallState](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.Option.html).
- [Oracle Java 22 — Linker / upcall exception handling](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [Oracle JNI Specification — Exception Handling](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/design.html).
- [Oracle JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html).

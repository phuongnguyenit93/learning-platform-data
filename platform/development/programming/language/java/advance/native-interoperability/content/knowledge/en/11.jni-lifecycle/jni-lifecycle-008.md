# Stopping Callbacks and Background Threads Before Releasing Libraries or Handles

> **Context:** Java Advance → Native Interoperability → JNI Lifecycle. This lesson explains why shutdown is an ordered synchronization protocol: **prevent new callbacks → stop accepting work → wait for running callbacks/workers to finish → release handles, JNI global references, and native libraries**. If the order is reversed, common failures include use-after-free, JVM crashes, deadlocks, or the JVM being unable to exit.

## 1. Why Is a Simple Free Not Enough?

In JNI, Java can open a **native session**, create a C/C++ handle, register callbacks into an SDK, create a thread pool or `pthread`, and let native code call back into Java. These resources do not share the same lifecycle:

- **Native handle:** a pointer/ID allocated by C/C++/SDK; it may contain mutexes, queues, state, and pointers to OS resources.
- **Callback registration:** the SDK holds a function pointer and often a `void* userData` pointing to the application's context. The SDK may invoke the callback from threads the application does not control.
- **Native worker:** a background thread still executing C/C++ code, possibly sleeping, processing buffers, calling JNI, or invoking callbacks.
- **JNI global reference:** keeps a Java listener/object alive across JNI frame and native thread boundaries; requires `DeleteGlobalRef` when no longer used by anyone.
- **Dynamic library:** `.so` / `.dylib` / `.dll` containing the callback/worker function code; if the library is unloaded while a thread is still executing its code, the instruction pointer/function pointer can become invalid.
- **Java facade:** an `AutoCloseable`/service class that holds the native handle and provides the API to Java callers.

A dangerous example:

```text
Java calls nativeClose(handle)
   -> free(handle) IMMEDIATELY
   -> DeleteGlobalRef(listener) IMMEDIATELY
   -> dlclose(nativeLibrary) IMMEDIATELY
                           |
                           v
     SDK callback or worker still running:
       onEvent(handle->listener)
       accesses freed handle / calls code in unloaded library
                           |
                           v
                  crash / memory corruption / UB
```

Even a single late callback is enough for a failure to occur. Java's `try/catch` cannot save a JVM that has encountered native memory corruption. What must be guaranteed is that **no execution path can touch the resource before it is released**.

## 2. Four Activity Types to Distinguish

| Type | Where does the callback happen? | Correct termination condition |
|---|---|---|
| **Synchronous callback during a native call** | The SDK invokes the callback before the native API returns | Wait for all active native calls to finish; the callback has returned |
| **Asynchronous callback from the SDK** | The SDK manages its own worker/event loop | Unregister, understand the exact guarantee of unregister, wait for *running* callbacks and callbacks still in the queue |
| **Application-created native worker** | `pthread`, `std::thread`, worker pool | Set stop flag/cancel, wake, join/await termination, ensure no native instructions are still using the state |
| **Java callback dispatcher/Executor** | Java `ExecutorService` or message queue | Stop enqueuing, wait for accepted tasks/callbacks to finish, shut down the Java executor according to contract |

**Unregister does not necessarily mean quiescent.** Some SDKs guarantee that after `unregister` returns, callbacks have completely stopped; others only prevent new registrations while a callback that has already started is still running. You must read the specific contract; if there is no clear guarantee, use an `inFlight` counter, a signal/barrier, or a separate stop-acknowledgement.

**Joining a single worker is also not enough** if callbacks from other SDK threads still remain. You must identify all sources that call into the handle and library: Java calls, native workers, external callbacks, timers, queued tasks, and Java executors.

## 3. State Machine and Standard Shutdown Order

A usable model:

```text
                  open/start success
                          |
                          v
                       OPEN
               accepts requests, callbacks
                          |
                          | close() / stop request
                          v
                      CLOSING
         reject new work, unregister/cancel
                          |
                          | callbacks in-flight = 0
                          | workers joined, Java tasks drained
                          v
                     QUIESCENT
                no one uses state anymore
                          |
                          | DeleteGlobalRef
                          | free native handle/buffer
                          | unload library if managed
                          v
                       CLOSED
```

Specific sequence:

1. **Transition state** `OPEN → CLOSING` under a mutex/atomic/CAS. From that point on, new API calls return `closed`/`shutting down`. Repeated `close` operations must be idempotent or have a clear policy on which caller performs the cleanup.
2. **Cut off callback sources:** stop timers, withdraw registrations from the SDK, prevent new tasks from being enqueued, send a stop signal to workers; **wake up** threads waiting on condition variables/I/O queues.
3. **Finish in-progress work:** let in-flight operations complete or cancel according to contract; wait for counters to reach 0, queues to drain, or drop according to policy. Do not free `userData` while a callback may still dereference it.
4. **Join/await workers:** wait for threads to actually exit; for workers attached to the JVM, they must clean up local refs/exceptions and call `DetachCurrentThread` before returning.
5. **Release low-level resources:** only after quiescence should you call `DeleteGlobalRef`, `free/delete` native state, close sockets/files/contexts, and tear down callback trampolines. If the application owns a `dlopen`/`LoadLibrary` handle, consider calling `dlclose`/`FreeLibrary` **last**, after ensuring no function pointers or instructions point into the library.
6. **Publish CLOSED:** the Java facade sets the handle to 0 or marks it CLOSED and ensures all callers waiting on shutdown have completed. Do not announce "closed" before workers/callbacks are actually quiescent.

This is a **logical order**; not every system needs to call all six APIs. An SDK might combine stop+join; a session without workers does not need a join. However, the invariant "no one is still using it before free/unload" always applies.

### Two Synchronization Rules

- **Do not hold a mutex that a callback needs while waiting for the callback or joining.** For example, thread A holds `state.mutex` and calls `pthread_join`, while worker B wants to lock the mutex to check `stopping` → deadlock.
- **Do not call a blocking close from the very worker/callback that close is waiting for.** `pthread_join(pthread_self())` is a deadlock/error; a synchronous callback calling `close()` while close is holding another Java monitor can also hang. Separate non-blocking `requestStop()` from `awaitStopped()` run on an independent control thread.

## 4. In-Flight Callbacks and the Release Boundary

Suppose an SDK uses a function pointer `nativeCallback(void *ctx, Event *ev)`. A callback needs "permission to use" the context from the moment it starts until it returns.

The model below **is C pseudocode**, not a standalone compilable file:

```c
// protected by mutex state->lock
bool beginCallback(State *state) {
    lock(state->lock);
    if (state->closing) {
        unlock(state->lock);
        return false;
    }
    state->inFlight++;
    unlock(state->lock);
    return true;
}

void endCallback(State *state) {
    lock(state->lock);
    state->inFlight--;
    if (state->closing && state->inFlight == 0) {
        signal(state->drained);
    }
    unlock(state->lock);
}

// shutdown thread:
lock(state->lock);
state->closing = true;
unlock(state->lock);

sdk_unregister_callback(); // must check the SDK's guarantee
lock(state->lock);
while (state->inFlight != 0) {
    wait(state->drained, state->lock);
}
unlock(state->lock);
// Only after being certain the SDK cannot start new callbacks
// and inFlight==0, may state/userData be destroyed.
```

**Subtle point:** `beginCallback(state)` also dereferences `state`. If the SDK can still call into `ctx=state` after `free(state)`, even incrementing the counter is already a use-after-free. Therefore, a counter alone does **not** replace the SDK's unregister/quiescence contract. You must prevent callbacks from starting before destroying the context, or keep the callback trampoline/context alive under an independent owner with reference counting and a safe release point.

If SDK unregister prevents new invocations but does not wait for old ones, you can use a counter to wait for active callbacks. If the SDK provides no barrier guaranteeing the last callback has been dispatched, you must build a dispatch layer with its own lifetime, or avoid unloading/freeing until the callback source is actually stopped.

## 5. JNI Resources: Before and After Workers Stop

### `JNIEnv*` and `JavaVM*`

`JNIEnv *env` is valid only for the **owning thread**; do not pass `env` from a Java caller to a worker. Obtain `JavaVM*` via `GetJavaVM` or `JNI_OnLoad`, then on the native worker call:

```c
// Illustrative snippet in a native-created thread:
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);
if (rc == JNI_EDETACHED) {
    if ((*vm)->AttachCurrentThread(vm, (void **)&env, NULL) != JNI_OK) {
        // Do not call JNI before attaching.
        return;
    }
    // This thread must call DetachCurrentThread before exiting.
} else if (rc != JNI_OK) {
    // No valid JNIEnv.
    return;
}
```

When the thread finishes, it must clean up all JNI local references and acquired memory, resolve any pending Java exception, and then call `DetachCurrentThread` **if the native thread itself attached**. Never detach a Java-created thread that still has Java frames. Using `AttachCurrentThreadAsDaemon` does not make a worker "automatically clean"; a daemon still needs to stop and clean up resources according to contract.

### Strong Global Reference

If a callback wants to call `listener.onEvent(...)` after the Java→native JNI method returns, the `jobject listener` parameter in the native method is only a **local reference**. Before handing it off to a worker:

```c
// In the native entrypoint on the Java thread, env belongs to this thread.
jobject listenerGlobal = (*env)->NewGlobalRef(env, listener);
if (listenerGlobal == NULL) {
    // Handle JNI error/pending exception; do not start worker.
}
// If successful: the attached worker can use listenerGlobal.
// Only call DeleteGlobalRef after being certain all callbacks have stopped.
```

`jmethodID` and `jfieldID` are not local/global references, but they also depend on class loader lifetime. Holding a global ref to a listener/class can keep the loader alive; if not deleted, the JNI library may never meet the conditions for the JVM to unload it.

**Do not use `DeleteGlobalRef` as a "cancel all callbacks" command.** It only deletes a JNI root. If a worker is still using the object, it may use a deleted handle. You must stop/join/drain first and delete only afterward.

### Exceptions in Callbacks

If a native worker calls Java via `CallVoidMethod` and the Java callback throws an exception, the exception will be **pending on the worker JNI thread**; it does not automatically transfer to the Java thread calling `close`. The worker must check `ExceptionCheck`, log/translate it, or pass the exception back to the owner using a lifecycle-managed global reference. Do not continue calling arbitrary JNI APIs while an exception is pending; do not silently call `ExceptionClear` without an error-reporting policy.

## 6. Complete Java 17+ / JNI C Example: Close Waits for Callbacks and Worker

This example creates **one background pthread** in the JNI library. Java registers a callback; Java sends values `1`, `2`, `3` one by one to the native worker; the worker attaches to the JVM, calls `listener.onEvent(value)`, and waits for the next event. When `Session.close()` is called on the control thread, JNI sets a stop flag, wakes the worker, **joins** it, deletes the global reference, and frees the state.

The design is intentionally **simple and bounded** so the ordering is clear:

- A session has one worker and at most **one pending request** (single-slot mailbox). Java waits for the callback before sending the next request.
- `submit` and `close` on the Java session are serialized with `synchronized`, preventing the handle from being freed while a `submit` is using it. The sample callback only writes to a `BlockingQueue` and **does not call back into `submit` or `close`**.
- When closing, the worker processes any remaining request in the mailbox and then exits. A successful `close` guarantees the worker has finished; no callbacks are running after `close` returns.
- This is a native handle management example and **does not call `dlclose` directly**. The JVM manages libraries loaded via `System.loadLibrary`. Section 8 discusses actual unloading.
- Build environment below: **Linux, GCC, pthread, JDK 17+**, with `JAVA_HOME` pointing to the JDK; do not apply Linux commands verbatim on Windows.

### 6.1. Java Facade: `JniLifecycleDemo.java`

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class JniLifecycleDemo {
    static {
        System.loadLibrary("lifecyclejni");
    }

    @FunctionalInterface
    public interface Listener {
        void onEvent(int value);
    }

    private static native long nativeOpen(Listener listener);
    private static native void nativeSubmit(long handle, int value);
    private static native int nativeClose(long handle);

    static final class Session implements AutoCloseable {
        // Only access handle within synchronized methods.
        private long handle;

        Session(Listener listener) {
            if (listener == null) {
                throw new IllegalArgumentException("listener is null");
            }
            handle = nativeOpen(listener);
            if (handle == 0L) {
                throw new IllegalStateException("nativeOpen failed");
            }
        }

        synchronized void submit(int value) {
            if (handle == 0L) {
                throw new IllegalStateException("session is closed");
            }
            nativeSubmit(handle, value);
        }

        @Override
        public synchronized void close() {
            if (handle == 0L) {
                return; // idempotent
            }

            // nativeClose blocks until the worker has joined and freed state.
            // If it throws before freeing, keep handle to fix/retry.
            int workerError = nativeClose(handle);
            handle = 0L;

            if (workerError != 0) {
                throw new IllegalStateException(
                        "worker failed: " + workerError);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<Integer> received = new LinkedBlockingQueue<>();

        try (Session session = new Session(received::offer)) {
            for (int expected = 1; expected <= 3; expected++) {
                session.submit(expected);
                Integer actual = received.poll(5, TimeUnit.SECONDS);
                if (actual == null || actual != expected) {
                    throw new IllegalStateException(
                            "unexpected callback: " + actual);
                }
                System.out.println("event = " + actual);
            }
        }

        // Only print after close has joined the worker and released state.
        System.out.println("closed");
    }
}
```

`received::offer` adapts to `Listener.onEvent(int)`: the `boolean` return type of `offer` is discarded for a functional method returning `void`. `BlockingQueue` is a thread-safe structure. `poll(5, TimeUnit.SECONDS)` bounds the time **waiting for an event in the demo**; it is not a timeout for `close`, because waiting for a native thread to finish may require its own policy.

**An important constraint of the pattern:** the callback is invoked on the native worker and **must not call `Session.close()` or any synchronized method on Session**. Calling close from the callback can cause a self-join; if main is holding the Session monitor during join, a callback attempting to acquire the monitor can also deadlock. Applications that need to stop from a callback should **post a stop request to another control executor**; a production design can separate `requestStop` and `awaitStopped`.

### 6.2. Generating the JNI Header

```bash
javac -encoding UTF-8 -h . JniLifecycleDemo.java
```

The compiler generates `JniLifecycleDemo.h`. The three `native` methods are `static`, so the second parameter of the JNI C function is `jclass`. Java's `long handle` parameter corresponds to `jlong` in JNI.

### 6.3. Native Implementation: `JniLifecycleDemo.c`

```c
#include <jni.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include "JniLifecycleDemo.h"

typedef struct {
    JavaVM *vm;
    jobject listenerGlobal;
    jmethodID onEventId;
    pthread_t worker;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    int stopping;
    int hasPending;
    jint pendingValue;
    int workerError;
} State;

static void throwState(JNIEnv *env, const char *message) {
    // If a Java exception is already pending, preserve the original cause.
    if ((*env)->ExceptionCheck(env)) return;
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalStateException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

static void *workerMain(void *arg) {
    State *state = (State *)arg;
    JNIEnv *env = NULL;

    // Native-created thread must attach and obtain its own JNIEnv.
    if ((*state->vm)->AttachCurrentThread(
            state->vm, (void **)&env, NULL) != JNI_OK) {
        pthread_mutex_lock(&state->mutex);
        state->workerError = 1;
        state->stopping = 1;
        state->hasPending = 0;
        pthread_mutex_unlock(&state->mutex);
        return NULL;
    }

    for (;;) {
        pthread_mutex_lock(&state->mutex);
        while (!state->stopping && !state->hasPending) {
            pthread_cond_wait(&state->changed, &state->mutex);
        }

        // When closing but an event is still pending: finish processing the event.
        if (!state->hasPending) {
            pthread_mutex_unlock(&state->mutex);
            break;
        }

        jint value = state->pendingValue;
        state->hasPending = 0;
        pthread_mutex_unlock(&state->mutex);

        // Do not hold the mutex while calling back into Java.
        (*env)->CallVoidMethod(
                env, state->listenerGlobal, state->onEventId, value);

        if ((*env)->ExceptionCheck(env)) {
            // In the demo: report error via workerError, avoid ignoring it.
            (*env)->ExceptionDescribe(env);
            (*env)->ExceptionClear(env);
            pthread_mutex_lock(&state->mutex);
            state->workerError = 2;
            state->stopping = 1;
            state->hasPending = 0;
            pthread_mutex_unlock(&state->mutex);
            break;
        }
    }

    // No more Java callbacks/frames running on the worker.
    if ((*state->vm)->DetachCurrentThread(state->vm) != JNI_OK) {
        pthread_mutex_lock(&state->mutex);
        state->workerError = 3;
        pthread_mutex_unlock(&state->mutex);
    }
    return NULL;
}

JNIEXPORT jlong JNICALL Java_JniLifecycleDemo_nativeOpen(
        JNIEnv *env, jclass owner, jobject listener) {
    (void)owner;

    if (listener == NULL) {
        throwState(env, "listener is null");
        return 0;
    }

    State *state = (State *)calloc(1, sizeof(*state));
    if (state == NULL) {
        throwState(env, "out of native memory");
        return 0;
    }

    if (pthread_mutex_init(&state->mutex, NULL) != 0) {
        free(state);
        throwState(env, "mutex init failed");
        return 0;
    }

    if (pthread_cond_init(&state->changed, NULL) != 0) {
        pthread_mutex_destroy(&state->mutex);
        free(state);
        throwState(env, "condition init failed");
        return 0;
    }

    if ((*env)->GetJavaVM(env, &state->vm) != JNI_OK) {
        goto fail;
    }

    jclass listenerClass = (*env)->GetObjectClass(env, listener);
    if (listenerClass == NULL) goto fail;

    state->onEventId = (*env)->GetMethodID(
            env, listenerClass, "onEvent", "(I)V");
    (*env)->DeleteLocalRef(env, listenerClass);
    if (state->onEventId == NULL) goto fail;

    // Convert local listener to global before starting pthread.
    state->listenerGlobal = (*env)->NewGlobalRef(env, listener);
    if (state->listenerGlobal == NULL) goto fail;

    if (pthread_create(&state->worker,
                       NULL, workerMain, state) != 0) {
        goto fail;
    }

    // Java long is an opaque native handle; valid only until close.
    return (jlong)(intptr_t)state;

fail:
    // Only enters this branch before the worker is created.
    if (state->listenerGlobal != NULL) {
        (*env)->DeleteGlobalRef(env, state->listenerGlobal);
    }
    pthread_cond_destroy(&state->changed);
    pthread_mutex_destroy(&state->mutex);
    free(state);
    throwState(env, "nativeOpen failed");
    return 0;
}

JNIEXPORT void JNICALL Java_JniLifecycleDemo_nativeSubmit(
        JNIEnv *env, jclass owner, jlong handle, jint value) {
    (void)owner;

    if (handle == 0) {
        throwState(env, "closed handle");
        return;
    }
    State *state = (State *)(intptr_t)handle;
    int failure = 0;

    pthread_mutex_lock(&state->mutex);
    if (state->stopping || state->workerError != 0) {
        failure = 1;
    } else if (state->hasPending) {
        // Demo has exactly one slot, do not overwrite an unprocessed request.
        failure = 2;
    } else {
        state->pendingValue = value;
        state->hasPending = 1;
        pthread_cond_signal(&state->changed);
    }
    pthread_mutex_unlock(&state->mutex);

    if (failure == 1) throwState(env, "session stopping");
    if (failure == 2) throwState(env, "pending slot is full");
}

JNIEXPORT jint JNICALL Java_JniLifecycleDemo_nativeClose(
        JNIEnv *env, jclass owner, jlong handle) {
    (void)owner;
    if (handle == 0) return 0;

    State *state = (State *)(intptr_t)handle;

    // Never join the callback/worker thread itself.
    if (pthread_equal(pthread_self(), state->worker)) {
        throwState(env, "close from callback thread");
        return -1;
    }

    pthread_mutex_lock(&state->mutex);
    state->stopping = 1;
    pthread_cond_broadcast(&state->changed);
    pthread_mutex_unlock(&state->mutex);

    // Join must not hold the mutex: the worker needs the mutex to exit.
    if (pthread_join(state->worker, NULL) != 0) {
        // Do not free state: the worker may still be using it.
        throwState(env, "pthread_join failed");
        return -1;
    }

    int result = state->workerError;

    // No more workers/callbacks using listener or State.
    (*env)->DeleteGlobalRef(env, state->listenerGlobal);
    pthread_cond_destroy(&state->changed);
    pthread_mutex_destroy(&state->mutex);
    free(state);
    return result;
}
```

**Why is there no use-after-free in the demo when used according to contract?**

- Java's `Session.submit` and `Session.close` are `synchronized`, so only one of them is passing the handle into JNI at a time; `close` does not free while a `submit` is still inside the native function.
- `nativeOpen` creates the JNI strong global reference and initializes the mutex/condition **before** launching the worker. On failure before `pthread_create`, the code cleans up the allocated resources.
- The worker obtains `JNIEnv*` on its **own** thread and calls the Java listener via the global ref. The callback finishes before the worker proceeds; the mutex is not held while entering Java.
- `nativeClose` sets `stopping` and calls `pthread_cond_broadcast` to wake the waiting worker; the worker processes any event remaining in the single slot and exits.
- `pthread_join` is the **barrier**: after joining, the worker can no longer use `State` or the listener global ref. Only then does the caller invoke `DeleteGlobalRef`, destroy the mutex/condition, and call `free`.
- Java `close` sets the handle to `0` **after** `nativeClose` completes. If the callback throws a Java exception, the worker logs/clears it and sets `workerError`; `nativeClose` finishes cleanup and returns the error code so Java throws an exception after the handle has been set to 0.
- If `pthread_join` fails, the code **does not free** state to avoid use-after-free. In a real program, a recovery mechanism and control-plane shutdown are needed to avoid resource leaks; do not assume join always succeeds and ignore the return code.

**Pedagogical limitation:** the example protects **one worker** and the three JNI methods of **Session**. It does not support multiple native producers calling the same handle directly, callbacks invoking `Session` methods, or an external SDK holding a function pointer. Those cases require ownership/refcounting, callback-registration barriers, and separate shutdown mechanisms described in sections 4, 7, and 9.

### 6.4. Compile and Run

```bash
gcc -std=c11 -fPIC -pthread -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o liblifecyclejni.so JniLifecycleDemo.c

java -Djava.library.path=. JniLifecycleDemo
```

With JDK 24+ on the classpath, native access can be granted explicitly:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniLifecycleDemo
```

**stdout on successful run:**

```text
event = 1
event = 2
event = 3
closed
```

`System.loadLibrary("lifecyclejni")` maps the logical name `lifecyclejni` to `liblifecyclejni.so` on Linux. For macOS, `.dylib`/`include/darwin` and appropriate flags are needed; for Windows, use a DLL, `include/win32` JNI headers, and the corresponding thread API. The Linux `pthread`/GCC command cannot be used verbatim as a single cross-platform build.

## 7. Handle and Concurrency Limitations That Real Systems Must Solve

### 7.1. `long` Is an Address with No Automatic Lifetime Mechanism

A Java class often holds a `long nativeHandle` to pass into JNI. A cast like `(State*)(intptr_t)handle` **does not check** whether the pointer has already been freed. The number `0` is merely a sentinel by convention; a non-zero handle can still be a stale pointer.

If multiple Java threads use the session concurrently, you must guard **every native entrypoint**:

- Lock the same lifecycle monitor around the check+use of the handle; or
- Use a handle table with generation/tokens and reference counting, ensuring `acquire(handle)` increments in-flight usage before close removes the entry; or
- Use a native wrapper with shared ownership, a CAS/atomic state machine, and cleanup after the last reference leaves scope.

Do not separate `if (handle != 0) nativeUse(handle)` from a `close` operation that can happen concurrently. That is a check-then-use race. Java `volatile` or `AtomicLong.get()` **alone** does not keep the native pointer alive; `AtomicLong.getAndSet(0)` only prevents double-close and is insufficient if another operation has already read the handle and is still running.

### 7.2. Callbacks Can Enter Concurrently with Close

Do not guard only `nativeSubmit` if an external SDK can still invoke callbacks. You need the same lifecycle guard for SDK callback registrations, timers, and native observers. Distinguish counts of `inFlightJavaCalls`, `inFlightNativeCallbacks`, and `workerThreads` across all paths that use state.

### 7.3. Repeated or Concurrent Shutdown

A proper idempotent close should guarantee that **all callers observe closed only when cleanup is complete**. If caller A starts cleanup while caller B calls close, B should wait for the same completion (or receive a future/closed status with a clear contract), rather than just seeing handle=0 and returning while A's worker is still running.

In the example Java class, `synchronized close` makes caller B wait for A to finish before entering the method, satisfying this. However, callbacks must not lock on the same Session monitor while A is joining. More complex production designs can use `CompletableFuture<Void> stopped` with no synchronization on the callback path.

## 8. Unloading Native Libraries: The JVM Differs from `dlclose`/`FreeLibrary`

### `System.loadLibrary` Does Not Create a Per-Session "Close Library"

`System.loadLibrary(...)` loads and links a native library for a class loader; the standard Java API **does not provide** a symmetric `System.unloadLibrary` per `Session.close`. `Session.close` should clean up its own **session resources**; the JVM manages the library's lifetime per runtime/class loader.

According to the JNI Invocation API, a library can export:

```c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}

// If JNI_OnUnload is exported, the JVM may call it when the class loader
// containing the library is garbage-collected.
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    // Perform only cautious cleanup; avoid calling arbitrary Java callbacks.
}
```

This is an **illustrative snippet**; there is no need to add these two functions to the section 6 example. `JNI_OnUnload` runs in an unspecified context, may not be called at the time of `Session.close`, and should not be used as the sole place to wait for callbacks/workers to finish or to call arbitrary Java code. Unreleased global references can keep the class loader alive, making reliance on `JNI_OnUnload` even less reliable.

### Library Handles Loaded by the Application Itself

If your JNI wrapper uses `dlopen`/`dlsym` or `LoadLibrary`/`GetProcAddress` to load a second C/C++ plugin, the **plugin handle** has a lifetime independent of the JNI wrapper library and each native session. You must ensure:

1. No remaining requests/callbacks/workers can enter the plugin.
2. No callback function pointers, vtables, code pointers, or pending tasks belonging to the plugin can be invoked again.
3. Resources created by the plugin have been destroyed using the corresponding API while the plugin code **is still loaded**.
4. All native threads capable of executing plugin code have joined/become quiescent.
5. Only after those steps should you release the plugin library reference via `dlclose`/`FreeLibrary`.

Do not call unload directly from a callback or from a currently executing function belonging to the plugin. `dlclose`/`FreeLibrary` does not replace the quiescence protocol; the dynamic linker itself may keep the module loaded due to other references, but you must not rely on that to legitimize an incorrect lifetime.

## 9. Deadlocks and Reentrant Callbacks: Why Stop Must Be Separated from Wait

Typical deadlock example:

```text
Thread A (controller)                Thread B (native worker)
lock(state.mutex)
state.stopping = true
pthread_join(B)  ---------------->    lock(state.mutex)  (blocked)
   A waits for B                        B waits for A
                        => DEADLOCK
```

Correct approach: set the stop flag under the mutex, signal/broadcast, **unlock the mutex**, and then join. If a callback from B into Java can require a Java lock that A is holding in `close`, a similar deadlock occurs **across the JNI boundary**.

A production API can separate:

```java
// Java pseudocode: concrete implementation depends on executor and native SDK.
session.requestStop();          // Non-blocking, no self-join.
session.stopped().join();       // Called only by the control thread to wait for the barrier.
session.releaseResources();     // Only after the stopped barrier.
```

The important thing is controlling **who waits for whom**, not necessarily that every API has these exact names.

Callback rules:

- A callback may signal `stopRequested` or enqueue a command onto a control thread.
- A callback must not self-join the current thread or contend for the lifecycle monitor held by close.
- The native callback trampoline should avoid holding internal mutexes when calling Java, because the Java callback might call back into native, creating reentrancy.
- If the SDK requires the callback to return quickly, do not block waiting for the entire shutdown inside the callback; record the event and let the controller perform cleanup.
- If the callback throws an exception, transition to an error state and shut down in an orderly fashion; do not free the context immediately in the middle of a native callback.

## 10. Timeouts, Cancellation, and Errors During Shutdown

"Waiting for workers to finish" does not mean waiting forever is acceptable in production. However, **a timeout must not turn into a forced `free` while a worker is still running**.

Cases:

| Situation | Correct handling |
|---|---|
| Worker waiting on a condition variable | Set stop flag, `signal`/`broadcast`, then join |
| Worker stuck in blocking I/O | Use contracted I/O cancel/close/socket shutdown; then wait for actual exit |
| Worker running a native call that does not support cancellation | Report shutdown incomplete, keep state/library alive; consider isolating native work in a helper process |
| SDK unregister returns but an in-flight callback remains | Wait for the quiescence barrier/counter before freeing |
| Java callback throws an exception | Handle/record on the JNI thread, propagate error to owner; do not continue arbitrary JNI calls while pending |
| `pthread_join` fails | Do not destroy state that may still be in use by the worker; recovery/diagnostics needed |
| `close` called multiple times | Only one caller cleans up; other callers wait for completion or receive a true closed status |
| JVM is shutting down | Stop accepting tasks, close sessions from the lifecycle owner, bound and log timeouts; do not rely solely on shutdown hooks |

If a user requires "close within 2 seconds" while a plugin can hang indefinitely, the **in-process** model has a safety limit: you cannot guarantee both immediate return and freeing state without a stop acknowledgement. The typical solution is a separate helper **process** so the process can be terminated after a timeout and crashes are isolated, or an SDK with a strong cancellation/quiescence contract.

**POSIX `pthread_cancel` is not a safe reset button either**: cancellation occurs at specific points, requires cleanup handlers, and easily leaves behind mutexes/global refs/SDK state. `Thread.stop` in Java carries similar risks to invariants. Prefer cooperative stop and an explicit protocol.

## 11. Cleaner, AutoCloseable, and Application Startup/Shutdown

`AutoCloseable` and `try-with-resources` are the right choice for sessions scoped to Java:

```java
// Illustrative snippet, using Session from section 6.
try (var session = new JniLifecycleDemo.Session(value -> {
    System.out.println(value);
})) {
    session.submit(42);
    // In a real application, wait for callbacks and follow thread rules.
}
// AutoCloseable.close() performs stop/join/free according to the contract.
```

`Cleaner`/finalizers are **not** suitable as the primary shutdown mechanism for native background workers:

- GC/Cleaner timing is non-deterministic; still-running code may hold a JNI global ref to the Java object, preventing GC from collecting that object.
- The Cleaner thread may run in a context unsuitable for joining a callback that needs Java resources/locks.
- Even using Cleaner as a safety net still requires ownership/refcounting and a quiescence path; do not directly `free(pointer)` if a native worker is still using it.

In servers, place `close` in an explicit lifecycle owner: a controlled component `stop`/shutdown hook, `@PreDestroy` if managed by a framework that guarantees dependency order, or a centralized native session manager. Do not rely solely on OS process exit to excuse handle leaks during application hot-reload/plugin-reload.

**Shutdown order across components also matters:** stop upstream producers first, stop callbacks/workers next, release plugin sessions, and only then stop dependent executors/VMs. Shutting down a Java executor while a native callback still needs it can cause lost events or exceptions during teardown.

## 12. Testing Strategies and Observing Lifecycle Bugs

Some tests that can verify behavior:

1. **Normal close:** open a session, send a few events, wait for receipt, close; verify no callbacks occur after close succeeds.
2. **Close while mailbox has an event:** send an event then close; clearly define the drain/drop policy and callback count, with no use-after-free.
3. **Double close:** close twice; the second call must not invoke `DeleteGlobalRef`/`free` again.
4. **Submit after close:** receive a clear exception/closed state; do not dereference a stale handle.
5. **Parallel submit vs close:** create a controlled race; ensure the entrypoint either acquired the handle before close or returns closed, without crashing.
6. **Slow/blocked callback:** make the callback wait on a latch; verify close waits on the barrier and releases only after the callback is released. The test needs an independent control thread to avoid self-deadlock.
7. **Callback throws exception:** the native worker reports the error to the lifecycle owner, cleans up JNI references, and exits the thread.
8. **Native worker startup failure:** inject thread-creation/allocation errors and ensure no global refs/mutexes leak.
9. **SDK callback after unregister:** simulate a late callback and verify the dispatcher's lifetime protocol.
10. **Plugin reload/unload:** open/close across multiple cycles with an appropriate class loader or plugin handle, ensuring no callback calls unloaded code.

Useful tools:

- **`-Xcheck:jni`:** helps detect certain JNI errors (reference/thread/method usage), but does not prove C memory safety.
- **AddressSanitizer / UndefinedBehaviorSanitizer:** finds use-after-free, out-of-bounds, and UB in native code; configure the toolchain and process accordingly.
- **ThreadSanitizer / race detectors:** useful for C/C++ data races (running with the JVM may have compatibility limitations; usually test the native component standalone first).
- **Heap/native memory monitoring:** track global refs, native allocations, thread counts, and ACTIVE/CLOSING session counts to detect leaks.
- **Structured logs:** log session ID, thread ID, lifecycle state, `inFlight` count, queue depth, callback start/end, stop requests, and join completions. Do not log raw pointers as the sole business identifier.

Repeated tests and interleaved schedules can uncover races, but **do not prove the absence of races**. You need ownership invariants along with results from checking tools.

## 13. Common Mistakes and Fixes Table

| Mistake | Consequence | Fix |
|---|---|---|
| `DeleteGlobalRef(listener)` while callback is running | Stale reference/use-after-delete | Unregister, wait for callbacks to become quiescent, then delete |
| `free(state)` immediately upon setting stop flag | Worker still dereferences state | Signal, join/await, then free |
| `dlclose` while threads/callbacks are still in the library | Calling invalid code, crash | Ensure all code paths are quiescent before unloading |
| Only calling SDK unregister then freeing, without knowing its guarantee | In-flight callback accesses freed userData | Verify SDK contract, barrier/refcount |
| `pthread_join` while holding a mutex the worker needs | Deadlock | Unlock before joining |
| `close` inside a running native callback | Self-join or lock inversion | Callback only calls requestStop; controller thread awaits |
| Java `long` handle read without locking during concurrent close | Check-then-use race, stale pointer | Monitor/acquire-release/refcount or handle registry |
| Treating `AtomicLong.getAndSet(0)` as protecting all native calls | In-flight calls may still hold the old pointer | Track in-flight entrypoints, close after draining |
| Failing to wake a worker waiting on a queue | `join` hangs | Signal/broadcast/sentinel event after stop |
| Worker fails to call `DetachCurrentThread` | Thread attachment leak; JVM may fail to exit | Clean up local refs and detach when native-created thread leaves JVM |
| Relying solely on Cleaner/`JNI_OnUnload` | Cleanup happens at the wrong time or never | Explicit owner lifecycle and `AutoCloseable` |
| Java callback throws exception and native continues normally | Pending exception masks errors, inconsistent state | Log/translate, stop orderly and report error |
| Timing out and freeing even though the worker has not stopped | Destroys resources still in use | Timeout returns not-stopped status, keep resource or isolate process |

## 14. Self-Check Exercises (with Answers)

**Exercise 1 — Determine the order.** A plugin registers `sdk_register(callback, state)` and starts two workers. On shutdown, the development team writes `free(state); sdk_unregister(callback); join(workers);`. What is wrong?

**Answer:** `state` is freed before the SDK stops callbacks and the workers finish. You must prevent new work, unregister with a guarantee that prevents new callbacks, wait for in-flight callbacks, signal/join workers, then free state, and finally unload the plugin if applicable.

**Exercise 2 — Prevent double free.** Java holds `AtomicLong handle`; close uses `getAndSet(0)` then frees. Is this safe enough when `submit` runs concurrently?

**Answer:** **Not yet.** The submit thread could have read the old handle before `getAndSet` and then entered JNI after the free. You need a lock around check+use or a native handle registry/refcount/acquire barrier.

**Exercise 3 — Callback closes itself.** A native worker calls a Java listener, and the listener immediately calls `session.close()`; `nativeClose` attempts `pthread_join` on the worker. What happens?

**Answer:** The callback thread may self-join or suffer lock inversion. The callback should only send `requestStop`; an independent controller performs `awaitStopped` and releases after the callback returns.

**Exercise 4 — JNI_OnUnload.** Why does putting all stop/join/free logic into `JNI_OnUnload` not guarantee the right lifecycle when a user clicks "close session"?

**Answer:** `JNI_OnUnload` is tied to the class loader/native library lifecycle, not the moment the Java session closes; it may run in a context unsuitable for Java callbacks or not be called in time. Sessions must have an explicit close.

**Exercise 5 — Timeout.** A callback is stuck in a native function that does not support cancellation. Can you call `dlclose` after waiting 1 second and let Java continue?

**Answer:** **Unsafe.** The callback can still execute unloaded code/resources. Report a timeout status, keep the library/state alive until quiescence, or isolate it in a helper process with a process-termination policy.

**Exercise 6 — Release reference.** A worker has called `DetachCurrentThread`, but another SDK callback still holds a pointer to the global listener. Can `DeleteGlobalRef` be called yet?

**Answer:** **Not yet.** Detaching one worker does not guarantee all other callback sources have stopped. You must stop the remaining callback sources and barrier across all in-flight paths.

## 15. Decision Checklist Before Releasing

Before any `free`, `DeleteGlobalRef`, `dlclose`/`FreeLibrary`, or SDK handle destruction, verify in order:

- [ ] State has transitioned out of `OPEN` and the API no longer accepts new requests/registrations.
- [ ] SDK callbacks/timers/event sources cannot initiate new callbacks according to a verified contract.
- [ ] Running callbacks and requests using the handle have completed, been safely canceled, or have their resources kept alive.
- [ ] Queues/workers have received stop, been woken up, and all required threads have joined/awaited.
- [ ] No Java/native method is still holding a pointer about to be freed.
- [ ] JNI workers have handled pending exceptions and detached if attached from native.
- [ ] JNI local refs, global refs, and native buffers have a single owner and are released in the right order.
- [ ] No callback code/function pointer can still be called in a plugin about to be unloaded.
- [ ] Close calls from callbacks/reentrant threads do not wait on themselves and do not hold mutexes that cause deadlock.
- [ ] Only when all of the above are met are handles/libraries released and the session published as CLOSED.

**Conclusion:** Proper JNI shutdown is a **quiescence protocol**. `stop` only expresses intent; `join`, callback barriers, and in-flight tracking establish proof that no users remain; **`free`/`DeleteGlobalRef`/library unload must come after that proof**.

### Official References

- [JNI Specification — Invocation API: Attach/Detach/GetEnv, JNI_OnLoad and JNI_OnUnload](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html)
- [JNI Specification — JNI Functions: NewGlobalRef, DeleteGlobalRef, exception APIs](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [JNI Specification — Design Overview: JNI Interface Pointers and Reference Management](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html)
- [Java 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html)
- [Java 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [POSIX — pthread_join](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_join.html)

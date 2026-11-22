# Registering Java Callbacks and Stopping Safely When a Library Calls from a Background Thread

## 1. Practice Task and Target Outcome

An SDK written in C/C++ often creates a background thread to read devices, receive data, or observe events. After Java registers a callback, the SDK needs to call back into a Java method when an event occurs. The challenge does not lie solely in the `CallVoidMethod` call, but in the **lifecycle**: how the native thread is attached to the JVM, whether the callback object is still alive, and what the application does when a stop is requested right while a callback is running.

This practice uses **Java 17+**, **JNI**, and **C++17** to:

1. Have Java register a callback-receiving object with the native library.
2. Have the library create a background `std::thread` and use `JavaVM` to obtain a `JNIEnv` belonging to **that exact thread**.
3. Have the native thread call the Java method `onNativeEvent(7)` exactly once, putting the event into a Java queue.
4. Have Java wait to receive the event, request a stop, have native wake up the background thread, wait for `join()`, and only then release the `GlobalRef`.
5. Ensure that once `close()` returns successfully, no native thread belonging to that registration session can start a new callback.

The example program runs on Linux/macOS/Windows when a suitable C++17 compiler is available. The output on a successful run is:

~~~text
event=7
closed
~~~

This is a minimal **single-event** simulation to verify the lifecycle. In a real SDK, the background thread typically receives multiple events, requiring a bounded queue, backpressure, error policies, shutdown timeouts, and a mechanism to manage multiple listeners.

## 2. Two Critical Boundaries: Thread and Lifetime

### 2.1. `JavaVM*` Is Not `JNIEnv*`

- `JavaVM*` is used to access the JVM attach/detach API and can be stored in native state shared across threads over the JVM lifecycle.
- `JNIEnv*` is the JNI interface **bound to each individual thread**. Do not keep a `JNIEnv*` obtained from the `nativeStart()` call and pass it into `std::thread`: that is an incorrect use of JNI and can cause a crash or undefined behavior.
- A thread created by native code must call `AttachCurrentThread(...)` or `AttachCurrentThreadAsDaemon(...)` before calling Java, and then `DetachCurrentThread()` when there are no longer any Java frames on the stack and before the thread terminates.
- The example uses `AttachCurrentThreadAsDaemon` so that the native worker does not keep the JVM alive indefinitely if the program forgets to stop. **Daemon does not replace `close()`**: you still must stop receiving data, wait for callbacks to finish, and release resources.

A newly attached thread typically has the **bootstrap loader as its context class loader**. In practice, `FindClass("com/company/MyListener")` from a self-created native thread can fail if the application class is not on the default class loader. This pattern solves that by receiving the **Java object upon registration**, calling `GetObjectClass` and `GetMethodID` directly on the registering Java thread, and storing the method ID together with the global reference.

### 2.2. The Java Callback Must Outlive the Registration Call

The `jobject` argument passed to a native method is a **local reference**. It is only guaranteed to remain valid within the scope/thread containing the native call; do not store a local reference in a struct for another thread to use after `register0` returns.

Instead:

- Call `NewGlobalRef(listener)` before starting the worker. A global reference keeps the listener visible to the GC until `DeleteGlobalRef` is called.
- Only release the global reference after new events have been blocked and the thread that can invoke callbacks has **finished `join()`**.
- Do not turn `jobject` into a regular C++ pointer to dereference; it is an opaque handle managed by JNI.
- `jmethodID` is a method ID, **not** a `jobject`. In the example, the listener has a live global reference so its class will not be unloaded mid-way; the looked-up method can still be used when the callback occurs.
- If a callback receives/creates many Java objects on a long-lived worker, manage local references per loop iteration using `DeleteLocalRef` or `PushLocalFrame`/`PopLocalFrame`. A long-attached worker does not automatically clean up local references after each native loop iteration.

### 2.3. Ensuring a True Shutdown

Merely setting a flag `stopping = true` and returning is **not enough**: a callback may have already passed the flag check and be currently running. To guarantee "no callbacks after `close()` completes", you need:

~~~text
Java                     Native manager                   Native worker
 | start()                  |                                 |
 |------------------------->| create GlobalRef / state        |
 |                          | create std::thread -----------> |
 |                          |                                 | Attach JVM
 |                          |                                 | Java callback
 |<-------------------------| return opaque handle            | wait on stop condition
 | receive event via queue  |                                 |
 | close()                  |                                 |
 |------------------------->| set stop=true; notify --------> |
 |                          | join() wait for worker          | Detach JVM, exit
 |                          |<--------------------------------|
 |                          | DeleteGlobalRef, free state     |
 |<-------------------------| return after cleanup            |
~~~

Four rules that prevent common bugs: **(1)** do not hold a native mutex during `CallVoidMethod`, **(2)** do not hold a native mutex during `join`, **(3)** do not let a synchronous callback call `close()` and then join its own thread, **(4)** do not call `DeleteGlobalRef` before the callback finishes.

Distinguish clearly: completing `close()` guarantees **no new callback invocations from that native session**; events **already enqueued into Java before close** may still remain in the queue. If the API requires "clearing all old events", a drain/drop policy must be defined and handled separately at the Java layer.

## 3. Creating the Practice Project

In a separate directory, create two files:

~~~text
native-callback-demo/
├── NativeCallbackDemo.java
└── native_callbacks.cpp
~~~

The build commands will generate `NativeCallbackDemo.class`, `NativeCallbackDemo.h`, and the library corresponding to the operating system. The example uses **one listener per registration session** and one native `std::thread` per session. Do not use a process-global singleton for all listeners; that way two sessions can stop independently.

### 3.1. Java Code: `NativeCallbackDemo.java`

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public final class NativeCallbackDemo implements AutoCloseable {
    static {
        System.loadLibrary("nativecallbacks");
    }

    private static final ThreadLocal<Boolean> IN_CALLBACK =
            new ThreadLocal<>();

    private final BlockingQueue<Integer> events =
            new ArrayBlockingQueue<>(8);

    // Opaque native pointer; Java does not dereference it.
    private long handle;
    private boolean closed;

    public NativeCallbackDemo() {
    }

    private static native long register0(NativeCallbackDemo receiver);
    private static native boolean unregister0(long nativeHandle);

    // JNI calls this method on the attached native worker thread.
    private void onNativeEvent(int value) {
        IN_CALLBACK.set(Boolean.TRUE);
        try {
            // Short callback: only forwards the event to the Java queue.
            if (!events.offer(value)) {
                throw new IllegalStateException("Event queue is full");
            }
        } finally {
            IN_CALLBACK.remove();
        }
    }

    public synchronized void start() {
        if (closed || handle != 0L) {
            throw new IllegalStateException(
                    "Already started or closed");
        }
        handle = register0(this);
        if (handle == 0L) {
            throw new IllegalStateException("Registration failed");
        }
    }

    public Integer pollEvent(long timeout, TimeUnit unit)
            throws InterruptedException {
        return events.poll(timeout, unit);
    }

    @Override
    public synchronized void close() {
        // Prevent self-join if the callback is modified to call close() directly.
        if (Boolean.TRUE.equals(IN_CALLBACK.get())) {
            throw new IllegalStateException(
                    "Close from a separate Java owner thread");
        }
        if (closed) {
            return; // Calling close multiple times does not double-free.
        }
        closed = true;
        long oldHandle = handle;
        handle = 0L;
        if (oldHandle != 0L && unregister0(oldHandle)) {
            throw new IllegalStateException(
                    "Native callback or attach failed; see stderr");
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (NativeCallbackDemo demo = new NativeCallbackDemo()) {
            demo.start();
            Integer value = demo.pollEvent(10, TimeUnit.SECONDS);
            if (value == null) {
                throw new IllegalStateException("Callback timed out");
            }
            System.out.println("event=" + value);
        }
        System.out.println("closed");
    }
}
~~~

**Rationale behind the decisions in Java:**

- `start()` and `close()` are `synchronized` to prevent two Java threads from initializing/releasing the handle concurrently. This monitor is not held in `onNativeEvent`, so the worker does not have to wait for a lock held by `close()` while it is `join`ing.
- `onNativeEvent` does not directly invoke slow business code, does not hold native locks, does not wait on UI/HTTP/DB, and does not call `close()`. It only `offer`s to the queue; the Java thread owning the component decides when to process or stop.
- A bounded queue of 8 elements exposes the **backpressure** issue. When the queue is full, the method throws; native code must detect the exception instead of continuing to make JNI calls while a pending exception exists.
- `handle` transitions from an opaque value to 0 upon closing. Do not pass that handle to any native API after it has been closed.
- `try-with-resources` always calls `close()` when exiting the block, even if waiting for the callback times out or an `InterruptedException` occurs. If stopping can block for a long time in a real application, build a shutdown API with timeout/cancellation and a dedicated handling policy.
- In the demonstration, the Java callback is not exposed as public for users to override. If providing third-party callbacks, you must clearly define the execution thread and offload long-running work to an appropriate executor.

### 3.2. Native Code: `native_callbacks.cpp`

~~~cpp
#include "NativeCallbackDemo.h"

#include <condition_variable>
#include <cstdint>
#include <exception>
#include <mutex>
#include <thread>

struct WorkerState {
    JavaVM* vm = nullptr;
    jobject receiver = nullptr;    // JNI global reference
    jmethodID onEvent = nullptr;
    std::thread worker;
    std::mutex mutex;
    std::condition_variable wake;
    bool stopping = false;
    bool callbackFailed = false;
};

static void throwState(JNIEnv* env, const char* message) {
    jclass type = env->FindClass("java/lang/IllegalStateException");
    if (type != nullptr) {
        env->ThrowNew(type, message);
        env->DeleteLocalRef(type);
    }
}

static void workerLoop(WorkerState* state) {
    JNIEnv* env = nullptr;
    if (state->vm->AttachCurrentThreadAsDaemon(
            reinterpret_cast<void**>(&env), nullptr) != JNI_OK) {
        std::lock_guard<std::mutex> guard(state->mutex);
        state->callbackFailed = true;
        return;
    }

    bool shouldDeliver;
    {
        std::lock_guard<std::mutex> guard(state->mutex);
        shouldDeliver = !state->stopping;
    }

    if (shouldDeliver) {
        // Do not hold the mutex when transitioning from native to Java.
        env->CallVoidMethod(state->receiver, state->onEvent, 7);

        if (env->ExceptionCheck()) {
            // Demo: log error + clear pending exception to detach safely.
            // Production: forward error to Java / structured error channel.
            env->ExceptionDescribe();
            env->ExceptionClear();
            std::lock_guard<std::mutex> guard(state->mutex);
            state->callbackFailed = true;
        }
    }

    {
        std::unique_lock<std::mutex> lock(state->mutex);
        state->wake.wait(lock, [state] {
            return state->stopping;
        });
    }

    // Only detach after the Java callback has returned.
    state->vm->DetachCurrentThread();
}

extern "C" JNIEXPORT jlong JNICALL
Java_NativeCallbackDemo_register0(
        JNIEnv* env, jclass, jobject listener) {
    JavaVM* vm = nullptr;
    if (env->GetJavaVM(&vm) != JNI_OK) {
        throwState(env, "Cannot obtain JavaVM");
        return 0;
    }

    jclass type = env->GetObjectClass(listener);
    if (type == nullptr) {
        return 0; // Pending exception from JNI.
    }
    jmethodID method =
            env->GetMethodID(type, "onNativeEvent", "(I)V");
    env->DeleteLocalRef(type);
    if (method == nullptr) {
        return 0; // E.g. NoSuchMethodError is pending.
    }

    jobject global = env->NewGlobalRef(listener);
    if (global == nullptr) {
        return 0; // Usually due to OutOfMemoryError.
    }

    WorkerState* state = nullptr;
    try {
        state = new WorkerState();
        state->vm = vm;
        state->receiver = global;
        state->onEvent = method;
        state->worker = std::thread([state] {
            workerLoop(state);
        });
        return static_cast<jlong>(
                reinterpret_cast<std::intptr_t>(state));
    } catch (const std::exception&) {
        // No joinable worker yet when std::thread constructor fails.
        delete state;
        env->DeleteGlobalRef(global);
        throwState(env, "Cannot start native worker");
        return 0;
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_NativeCallbackDemo_unregister0(
        JNIEnv* env, jclass, jlong rawHandle) {
    if (rawHandle == 0) {
        return JNI_FALSE;
    }
    auto* state = reinterpret_cast<WorkerState*>(
            static_cast<std::intptr_t>(rawHandle));

    {
        std::lock_guard<std::mutex> guard(state->mutex);
        state->stopping = true;
    }
    state->wake.notify_one();

    // Caller is the Java owner thread, not the callback thread.
    // Join outside the mutex, waiting for any CallVoidMethod to finish.
    try {
        state->worker.join();
    } catch (const std::exception&) {
        // Do not free state/global ref if worker stop is not guaranteed.
        throwState(env, "Cannot join native worker");
        return JNI_FALSE;
    }

    bool failed = state->callbackFailed;
    env->DeleteGlobalRef(state->receiver);
    delete state;
    return failed ? JNI_TRUE : JNI_FALSE;
}
~~~

The native code intentionally does not call `FindClass` for the application class inside `workerLoop`. The listener and `jmethodID` were already obtained in `register0` when Java called in. The C++ worker only uses `JavaVM*`, the global reference, and the `JNIEnv*` received **after attaching itself**.

The code uses `std::mutex`/`std::condition_variable` so the worker does not busy-spin. The `wait(lock, predicate)` operation avoids lost signals if `close()` sets `stopping=true` **before** the worker reaches the wait point. Under any interleaving order:

- If close happens before the `shouldDeliver` check, the callback may be skipped.
- If the worker has already decided to deliver the callback, close will wait until the callback actually completes.
- The worker only exits the wait loop when it observes `stopping`; afterward it calls `DetachCurrentThread` and terminates.
- `unregister0` calls `join` before `DeleteGlobalRef` and deleting `WorkerState`, preventing **use-after-free**.
- Java callback throws an exception: native uses `ExceptionCheck` → `ExceptionDescribe` → `ExceptionClear`, and sets the `callbackFailed` flag. After cleanup, `close()` reports an error if that flag is true. Do not silently ignore a pending Java exception.
- If attach fails, the worker marks `callbackFailed` and exits; `unregister0` still calls `join`, cleans up the global reference, and reports the error back.

**Intentional limitation of the example:** the extremely rare failure branch where `std::thread::join()` itself throws stops cleanup to avoid deleting resources that might still be in use by the worker; production applications need dedicated error state management, retry/diagnostics, and ownership mechanisms. The pattern relies on the convention that `close()` is only called from the Java thread owning the session, not directly from the native callback. `IN_CALLBACK` prevents the synchronous `close()` call path from the example's callback.

## 4. Compiling and Running

You need **JDK 17 or higher**, a C++17 compiler, and the `JAVA_HOME` environment variable pointing to the right JDK. Place `NativeCallbackDemo.java` and `native_callbacks.cpp` in the same directory and run the commands there.

### 4.1. Linux (GCC/Clang C++)

~~~bash
javac -h . NativeCallbackDemo.java
g++ -std=c++17 -O2 -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  native_callbacks.cpp -o libnativecallbacks.so
java -Djava.library.path=. NativeCallbackDemo
~~~

`javac -h .` generates `NativeCallbackDemo.h` defining the two JNI symbols `Java_NativeCallbackDemo_register0` and `Java_NativeCallbackDemo_unregister0`; `g++` builds the exact binary `libnativecallbacks.so` for Java to load via `System.loadLibrary("nativecallbacks")`.

### 4.2. macOS (Clang)

~~~bash
javac -h . NativeCallbackDemo.java
clang++ -std=c++17 -O2 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  native_callbacks.cpp -o libnativecallbacks.dylib
java -Djava.library.path=. NativeCallbackDemo
~~~

### 4.3. Windows (MSVC x64 Native Tools Command Prompt)

~~~bat
javac -h . NativeCallbackDemo.java
cl /std:c++17 /EHsc /O2 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" native_callbacks.cpp /link /OUT:nativecallbacks.dll
java -Djava.library.path=. NativeCallbackDemo
~~~

On Windows, you must use a compiler matching the JVM architecture (x64 ↔ x64, ARM64 ↔ ARM64). Across all operating systems, if the library cannot be found, check the working directory, `java.library.path`, binary name, and dynamic dependencies. If `UnsatisfiedLinkError` occurs even though the file exists, check JNI symbols, library format, ABI, and the libraries it depends on.

### 4.4. JVM Native Access Starting in JDK 24

Starting in **JDK 24**, JEP 472 places JNI library loading and native method binding under the restricted native access mechanism. When running code in the unnamed module (class path), run with:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  --illegal-native-access=deny \
  -Djava.library.path=. NativeCallbackDemo
~~~

On Windows, use the equivalent single-line command:

~~~bat
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -Djava.library.path=. NativeCallbackDemo
~~~

These `--illegal-native-access=deny`/`--enable-native-access` flags apply to **JDK 24+** in the context of JNI restrictions; do not add `--illegal-native-access` to JDK 17/21 commands because older JDKs do not recognize that option. When migrating to a named module, grant permission to the **module that actually invokes restricted operations** rather than opening `ALL-UNNAMED` for the entire class path.

### 4.5. Stdout on Success

~~~text
event=7
closed
~~~

The two lines do not depend on the scheduler on the **success path**: native emits exactly one event with value `7`, Java only prints after taking the event from the queue; the `closed` line only prints after `try-with-resources` finishes calling `close()`. If attach or callback fails, or if an overloaded machine causes the 10-second wait to expire, the program produces an exception/diagnostic instead of the two lines above. Do not assume a fixed callback arrival time.

## 5. Testing Early-Stop Races and Cleanup

### 5.1. Closing Immediately After Registration

Also create `EarlyCloseCheck.java`:

~~~java
public final class EarlyCloseCheck {
    public static void main(String[] args) {
        for (int i = 0; i < 200; i++) {
            try (NativeCallbackDemo demo =
                         new NativeCallbackDemo()) {
                demo.start();
                // May close before or after the worker's callback.
            }
        }
        System.out.println("early_close_ok");
    }
}
~~~

Compile and run (JDK 17–23):

~~~bash
javac EarlyCloseCheck.java
java -Djava.library.path=. EarlyCloseCheck
~~~

On JDK 24+, add the native access flags as in section 4.4. The output on success is:

~~~text
early_close_ok
~~~

This test is useful for catching `start() → close()` races, broken `join()`, or crashes from releasing the global reference too early. Run it multiple times and combine with `-Xcheck:jni` (HotSpot) during test runs, as well as appropriate memory/thread sanitizer tools for the native build when available. **A single pass does not prove the absence of race conditions**; accurate observation also requires fault injection and variants with multiple producer/consumer threads.

### 5.2. Calling `close()` Twice

`close()` is written to be idempotent. After the first call, `closed=true` and `handle=0`. The second call returns without calling `unregister0` again. This prevents double-free. However, the API still needs protection against the native side being called directly with a freed pointer: do not expose the native handle externally, and ensure all lifecycle paths go through the synchronized Java owner.

### 5.3. Stopping While a Callback Is Executing

In practice, the native worker may have already passed `shouldDeliver` when another thread calls `close()`. Because native does not hold the mutex across `CallVoidMethod`, the close call can set the `stopping` flag and wait for `join`. The worker finishes the callback, observes the flag, detaches, and exits. This creates a **barrier**: after close returns, the global reference is no longer used by the worker.

If the Java callback tries to lock the monitor of `close()` or call `close()` directly, a deadlock/self-join can occur. The pattern uses a queue and does not synchronize the callback on the owner monitor, while also forbidding `close()` from the same callback thread. When an SDK has external user-registered callbacks, dispatch them on a separate Java executor and design a `stopAsync()` if the callback might request unregistration.

## 6. Callback Management Checklist for Real Projects

| Issue | Common Mistake | Safe Design |
| --- | --- | --- |
| Crossing into JVM from native thread | Using a `JNIEnv*` obtained from another thread | Store `JavaVM*`, attach the native worker, use its own `JNIEnv*`, detach on exit |
| Keeping a Java callback | Keeping a local `jobject` after the native method returns | `NewGlobalRef` at registration, `DeleteGlobalRef` after the worker stops |
| Looking up the callback class | Calling `FindClass` on the native worker and failing to find the app class | `GetObjectClass`/`GetMethodID` on the Java caller at registration, store ID and global ref |
| Event handling | Doing slow I/O inside `CallVoidMethod` | Forward data to a bounded queue/executor, define backpressure |
| Callback throws an exception | Continuing JNI with a pending exception or clearing and forgetting the error | `ExceptionCheck`, log/forward error to owner, clear properly and stop/mark failure |
| Releasing the listener | Deleting the global ref before the callback has returned | Signal stop → prevent new work → `join` → delete global ref |
| Synchronization | Holding a native mutex during callback/`join` | Hold mutex briefly to update state, release before calling Java/waiting for worker |
| Running `close()` in callback | Worker waits to `join` itself or waits on a Java lock | Forbid synchronous self-close; send stop request to owner/executor |
| Multiple registrations | One static global listener for all sessions | Each session has its own handle, its own state, and closes once |
| JVM shutdown | Relying on daemon threads/`JNI_OnUnload` | Close before the JVM lifecycle ends; prevent the SDK from emitting late callbacks |
| Newer JDK configuration | Not granting native access when needed | Test JDK 24+ with `--illegal-native-access=deny` and `--enable-native-access` on the right module |
| Testing | Only verifying that the callback was received | Test early stop, stop after callback, attach failure, callback exception, full queue, and multiple registrations |

### When the Library Has Multiple Events and Multiple Workers

The single-event pattern is sufficient to verify the attach/callback/stop protocol. If expanding into a continuous SDK, additional design is needed:

- Use a **producer-count or in-flight callback counter** and the condition `inFlight == 0` (or join all workers) before deleting refs. A `stopping` flag alone does not mean all callbacks have finished.
- If multiple callbacks run concurrently, define whether ordering is guaranteed or not; received events should not be reordered by scheduling without being documented.
- Do not store a single `JNIEnv*` in shared state. Each worker attaches to get its own env. If JNI is already invoked on a Java-created thread (Java→native), you can use that invocation's env and must not arbitrarily attach/detach a thread managed by the JVM.
- For callbacks with large payloads, consider buffer pinning/copying, memory segment lifetimes, and ownership rules. Do not pass freed native pointers into a Java queue.
- A bounded queue needs a clear policy: block producer, drop oldest/newest, coalesce events, or report an error. Blocking callbacks can make stopping take a long time or deadlock if the consumer is stopped first. The demo intentionally uses non-blocking `offer`.
- Store errors as structured status and provide an error-reading API; `ExceptionDescribe` is only suitable for simple observation, not as a production logging/telemetry protocol.
- For native SDKs with cancel/stop APIs that **block indefinitely**, there is no guarantee that `join` will finish. You need a worker stop contract, timeout/cancellation according to the SDK API, and handling for when the event source cannot be interrupted.

## 7. Common Error Diagnostics

**`UnsatisfiedLinkError: no nativecallbacks in java.library.path`**: The JVM cannot find the binary. Check `-Djava.library.path=.`, working directory, file name, and architecture. If the name is right but loading still fails, check native dependencies or exported JNI symbols.

**`UnsatisfiedLinkError: 'long NativeCallbackDemo.register0(...)'`**: The library loaded, but the JVM could not find the corresponding JNI function. Check `javac -h`, class/package, native signature, `extern "C"` to avoid C++ name mangling, and exported function names.

**`NoSuchMethodError: onNativeEvent(I)V`**: `GetMethodID` could not find an instance callback with the exact signature. For `(I)V`, the parameter is one `int` and the return type is `void`. Changing it to `long` makes it `(J)V`; if the method is static, you must use `GetStaticMethodID` and `CallStaticVoidMethod`.

**JVM crashes after running for a while**: Suspect caching `JNIEnv*` across threads, using a local reference after the native call has returned, freeing state/global ref before callbacks stop, ABI mismatch, or a race in the C++ library.

**No event seen / timeout**: Check JVM attach, the `stopping` flag, callback/queue errors, and whether a Java thread is blocking events; enable `-Xcheck:jni` on HotSpot during diagnostic runs. Do not increase the timeout to mask a real deadlock bug.

**Application does not exit**: The native worker has not received the stop signal, `join()` is waiting on a stuck thread, or a non-daemon attach has not detached. Capture Java and native stack dumps; release locks before invoking callbacks/waiting for workers, and ensure any blocking native API has a wakeup mechanism.

**JDK 24+ warnings or `IllegalCallerException`**: Separate this from threading errors. Identify the module performing restricted operations and add the appropriate `--enable-native-access` to the **actual JVM launch**; if using `--illegal-native-access=deny` without permission, the load/binding step itself can be blocked.

## 8. Extension Exercises and Completion Criteria

1. Replace the fixed value `7` with an event carrying an incrementing sequence number in a worker loop. Add a stop flag, queue bound, and backpressure design; verify there are no new callbacks after `close()` and no global reference leaks.
2. Have an event intentionally trigger a Java exception. Verify that `ExceptionCheck` detects it properly, native does not make arbitrary JNI calls while an exception is pending, and the error is propagated back to the Java owner after resource cleanup.
3. Create two independent `NativeCallbackDemo` instances; stop the first session while the second session continues running. Compare this with a design using a single native listener singleton.
4. Stress-test repeated `start() → close()`, running under `-Xcheck:jni` and native thread/memory sanitizers when possible. Record the types of bugs caught.
5. Extend to asynchronous callbacks dispatched to a Java `ExecutorService`; verify that shutting down the executor and shutting down the native worker have a clear ordering without cross-locking.

**Completion criteria:** (a) callback from a native background thread into Java succeeds, (b) `JNIEnv*` is not used on the wrong thread, (c) the listener stays alive via `GlobalRef` until the worker terminates, (d) `close()` guarantees `join` finishes before freeing, (e) no deadlock occurs when callbacks and shutdown race, (f) callback/attach errors are detected, (g) both normal and early-close tests run on the chosen JDK/platform.

## Official References

- Oracle JNI Specification — *Invocation API*, `AttachCurrentThreadAsDaemon`/`DetachCurrentThread`: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html
- Oracle JNI Specification — *Design Overview*, local/global references and method IDs: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html
- Oracle JNI Specification — *JNI Functions*, `NewGlobalRef`, `DeleteGlobalRef`, `CallVoidMethod`, and exception handling: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html
- OpenJDK JEP 472 — Native access restrictions starting in JDK 24: https://openjdk.org/jeps/472

**Remember:** successfully registering a callback is only the first half of JNI integration. The other half is a **bounded shutdown protocol**: signal stop, let any running callback finish, join the native worker, detach, and only then release the global reference and native state.
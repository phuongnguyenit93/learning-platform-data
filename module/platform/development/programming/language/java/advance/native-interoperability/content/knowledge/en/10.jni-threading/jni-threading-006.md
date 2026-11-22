# Callbacks from Native Threads and How to Find the Right Application Class in JNI

## 1. The Real-World Problem

A Java application can call a C/C++ library via JNI, and then the library creates a **native worker thread** using `pthread_create` or `std::thread`. When a result is ready, the worker wants to call back into a Java method to notify an event, update state, or return a result. In JNI terms, this is not a normal Java call: a thread newly created in C/C++ **does not automatically have permission to use JNI** and may **not see application classes through the appropriate class loader**.

Two groups of problems often appear together:

1. **Thread rules:** `JNIEnv *` belongs to **one specific thread**. A native worker must attach to the right `JavaVM`, obtain its own `JNIEnv *`, perform the callback, and then detach when finished. Do not pass a `JNIEnv *` obtained from a Java calling thread to a worker.
2. **Class loader rules:** `FindClass` uses a class loader depending on the call context. On a native thread without an active Java native-method frame, looking up `com/example/plugin/Handler` can fail if the class was loaded by a plugin's **custom class loader** instead of the system class loader. Simply changing the thread context class loader does not guarantee fixing `FindClass`.

In addition, native code must properly maintain the lifetime of `jobject`/`jclass` across threads, prevent callbacks from running after a plugin is unloaded, manage exceptions thrown from Java callbacks, and clearly decide who is responsible for stopping the worker.

Example scenario:

```text
Java thread
  │
  └── nativeStart(callback)
         │
         ├── Save JavaVM*
         ├── Create global reference to callback
         └── Create C/C++ worker thread
                    │
                    ├── AttachCurrentThread → own JNIEnv*
                    ├── CallVoidMethod(callback, onEvent, ...)
                    ├── Handle Java exception if any
                    ├── Delete local refs, release state
                    └── DetachCurrentThread
```

The goal of this article is to understand the mechanism properly and implement a safe callback, especially when classes belong to separate modules, plugins, or loaders.

## 2. Distinguishing `JavaVM *` and `JNIEnv *`

JNI has two related interfaces with different roles.

| Interface | Meaning | Can be used on another thread? |
| --- | --- | --- |
| `JavaVM *` | Interface to the JVM, used for `GetEnv`, `AttachCurrentThread`, `DetachCurrentThread` | **Can** be saved and used across multiple native threads belonging to the same VM |
| `JNIEnv *` | JNI interface of the **current thread**, used for `FindClass`, `CallVoidMethod`, `NewGlobalRef`... | **No**; a `JNIEnv *` must be obtained for each attached thread |

In a JNI method called from Java into C:

```c
JNIEXPORT void JNICALL Java_demo_Bridge_start(
        JNIEnv *env, jclass declaringClass) {

    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        return; /* Need to report the error to Java per application contract. */
    }

    /* vm can be passed to a native worker.
       MUST NOT pass env to another thread to use JNI. */
}
```

This is an **illustrative fragment**, without the Java class `demo.Bridge` or a full implementation. The `GetJavaVM` method retrieves the JVM interface from a valid `JNIEnv *`; a native library can also receive `JavaVM *` in `JNI_OnLoad`.

### 2.1. A worker must attach before calling Java

C invocation of the JNI Invocation API:

```c
JNIEnv *workerEnv = NULL;
jint rc = (*vm)->AttachCurrentThread(
        vm, (void **)&workerEnv, NULL);

if (rc == JNI_OK) {
    /* Call JNI through workerEnv on this thread. */

    (*vm)->DetachCurrentThread(vm);
}
```

In C++:

```cpp
JNIEnv *workerEnv = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void **>(&workerEnv), nullptr);

if (rc == JNI_OK) {
    // workerEnv is only used on this thread.
    vm->DetachCurrentThread();
}
```

After attaching successfully, the native thread can call JNI methods and Java methods, provided it follows reference lifetime, synchronization, and pending-exception rules.

- `AttachCurrentThread` returns `JNI_OK` on success; if it fails, **do not use** `workerEnv`.
- `DetachCurrentThread` must be called **before the native thread you attached exits**, after there are no longer any Java methods on that thread's stack.
- An already-attached thread calling `AttachCurrentThread` again retrieves that thread's `JNIEnv *`; re-attaching does not change its daemon status.
- `AttachCurrentThreadAsDaemon` attaches a new native thread as a daemon. Daemon/non-daemon affects whether the JVM waits for the thread to exit; it **does not solve** class lookup or callback lifetime issues.
- `GetEnv` returns `JNI_OK` if the current thread is already attached, `JNI_EDETACHED` if not, or `JNI_EVERSION` if the version is unsupported. It **does not attach automatically**.

Do not arbitrarily detach a Java thread already managed by the JVM just because it is passing through a native method. If a library can be called from both Java threads and native threads, you must track **which specific threads you attached** so you detach with proper ownership.

### 2.2. Local refs and global refs when crossing thread boundaries

The `jobject callback` parameter received from Java is a **local JNI reference** inside the native method. Do not store it directly in a C struct, return to Java, and let a worker read it later:

```c
/* WRONG if cb is a local ref from another native call. */
struct Context { jobject cb; };
context.cb = cb;
/* Another thread uses context.cb after the native call returns. */
```

Hold it with a global reference instead:

```c
jobject globalCallback = (*env)->NewGlobalRef(env, cb);
if (globalCallback == NULL) {
    /* If cb != NULL, there may be an allocation error to handle. */
    return;
}

/* Pass globalCallback to the attached worker. */

/* Delete only after ensuring the worker is no longer using the callback. */
(*env)->DeleteGlobalRef(env, globalCallback);
```

`NewGlobalRef` creates a strong reference to a Java object and can be used from appropriately attached threads. It prevents the object from being garbage-collected while the callback is still needed. In return, if you forget `DeleteGlobalRef`, the callback and its defining class loader can be kept alive forever, causing leaks when redeploying plugins.

**`jmethodID` is not a `jobject`.** You can cache a method ID for use on a worker, but the ID is only valid while the method's defining class remains loaded. In a design that holds the callback with a global ref, the object's class also stays alive for the needed duration; after teardown, do not reuse method IDs from an old plugin version.

## 3. Why can `FindClass` on a native worker find the wrong class?

JNI `FindClass` takes a **slash-separated JNI class name**, for example:

```c
jclass type = (*env)->FindClass(
        env, "com/example/plugin/EventHandler");
```

However, **the right class name is not enough**. The right class loader must be used.

According to the JNI specification, behavior depends on where it is called from:

| `FindClass` call context | Class loader used |
| --- | --- |
| Inside a native method declared by a Java class | The loader associated with **the class declaring the native method** (the current JNI native frame), not automatically the callback object's loader |
| Inside `JNI_OnLoad`/`JNI_OnLoad_L` | The loader of the class loading the native library |
| Via the Invocation Interface, with no current native method associated with a loader | `ClassLoader.getSystemClassLoader()` |
| Inside `JNI_OnUnload`/`JNI_OnUnload_L` | The system class loader, because the loader at load time may no longer exist |

A native worker that has just attached via `AttachCurrentThread` and then calls `FindClass` does not have a normal Java native-method context. In this case, JNI does not automatically know to use the plugin loader that Java previously selected. Therefore, for a class that only resides in a `URLClassLoader`, OSGi loader, servlet/container loader, or separate module loader, `FindClass("com/example/plugin/EventHandler")` can fail with `NoClassDefFoundError` or an equivalent lookup error.

### 3.1. Distinguishing `FindClass` from the thread context class loader

When attaching a new native thread, the **thread context class loader** defaults to the bootstrap loader (per the JNI Invocation API). This is the state of `Thread.currentThread().getContextClassLoader()`.

`FindClass`, on the other hand, has its own loader-selection rules based on the JNI context as shown in the table above. Therefore, changing:

```java
Thread.currentThread().setContextClassLoader(pluginLoader);
```

only affects Java frameworks that **actively look up the thread context class loader**. It is not a method that guarantees `FindClass` will pick the right plugin loader, nor does it automatically synchronize class identity when callbacks cross multiple plugins.

If a framework needs an appropriate context class loader when running a Java callback, it can set and **restore** it inside a Java callback wrapper. Do this intentionally; do not use it as a substitute for storing the right `Class<?>` or callback object.

### 3.2. Two classes with the same name can still be two different types

`plugin.Handler` defined by `LoaderA` is different from `plugin.Handler` defined by `LoaderB`:

```text
LoaderA ──► plugin.Handler (Class object A)
LoaderB ──► plugin.Handler (Class object B)

Same binary name, different class identity.
```

If a native cache uses only the string `"plugin/Handler"` as its key, reloading a plugin can cause callbacks to be invoked with a method ID from an old version, or cause `ClassCastException`/`NoSuchMethodError`/severe JNI errors. Do not "fix" the error by trying multiple random class loaders. Instead, **tie the cache to the actual callback instance / `jclass` and loader with a clear lifecycle**.

## 4. Three Correct Ways to Call Application Classes from a Native Worker

### Approach A — Preferred: Java passes a callback object; native holds a global ref

In Java, instead of asking native code to find `plugin.Handler` itself, provide a stable Java interface:

```java
@FunctionalInterface
interface EventSink {
    void onEvent(int code);
}
```

Java creates the callback instance from the right plugin loader and passes it to native code. Before creating the worker, JNI does three things on the **Java thread calling the native method**:

1. `GetObjectClass(callback)` gets the object's actual class.
2. `GetMethodID(..., "onEvent", "(I)V")` gets the method ID with the right signature.
3. `NewGlobalRef(callback)` creates a strong reference to use across the native thread.

The worker only needs `CallVoidMethod` on the global callback, along with the looked-up method ID. It **does not need `FindClass` on the worker thread**. This approach works for callbacks belonging to a custom loader, as long as the object/method remains valid, the callback exposes the right signature, and the lifecycle is managed.

### Approach B — Pass `Class<?>` from Java, hold `jclass` with a global ref

When needing to call a plugin's **static method**, the Java side can resolve the class with the right loader and pass it to JNI:

```java
Class<?> pluginHandler =
        Class.forName("plugin.Handler", true, pluginLoader);

// nativeRegisterHandler(pluginHandler) is a custom-defined API.
nativeRegisterHandler(pluginHandler);
```

This is a **Java fragment**; `pluginLoader` and `nativeRegisterHandler` are defined by the application. On the JNI side, create `NewGlobalRef` for the `jclass` parameter, look up `GetStaticMethodID` for the right method, and then call `CallStaticVoidMethod` on the worker. After stopping the worker and cleaning up, delete the global class ref.

Do not cache a local `jclass` from a previous call for long-term use. A strong global `jclass` can keep the **plugin class loader** alive, so teardown must be proactive.

### Approach C — Save the right `ClassLoader` and call `loadClass` (when many classes need to be loaded dynamically)

When the worker does not know in advance which classes it will need to use, Java can pass the **loader object** and native code stores a `NewGlobalRef` to it. Once attached to the JVM, native code can call `ClassLoader.loadClass(String)` via JNI on the right loader; **the name passed here uses dots**, for example `"plugin.Handler"`, unlike `FindClass("plugin/Handler")`.

An approach that is often easier to control is to have Java write a helper method to perform `Class.forName(name, initialize, pluginLoader)` and return `Class<?>`, while native code calls the helper through an existing reference. When working with module encapsulation, visibility, and security policies, normal Java rules still apply.

Approach C is flexible but more complex than A/B: you must handle `ClassNotFoundException`, JNI signatures, load/initialize logic, loader locks, and the lifetime of the global loader ref. Only use it when dynamic class resolution is genuinely needed.

### Which approach should you choose?

| Need | Recommendation |
| --- | --- |
| Native worker notifies events to Java | **A**, pass a callback instance down |
| Native worker calls a fixed static entry point of a plugin | **B**, pass the right `Class<?>` |
| Native needs to look up many classes through a plugin loader | **C**, call the loader passed by Java |
| Same native core serves multiple plugins | Shared Java bridge + per-plugin callback, following lifecycle |
| Plugin can be reloaded | Registry keyed by plugin instance/loader, stop/drain/cleanup before dropping the old loader |

## 5. Complete Example: Native `std::thread` Callback Back to Java

The example below uses **Java 17+**, JNI, and C++17. We create a real worker using `std::thread`, attach it to the JVM, call `onEvent(42)` on the Java callback, and then detach. For **deterministic stdout**, the Java method `runOnce` waits for the worker to finish with `join` before returning. In a real application, a long-lived worker might use a queue/scheduler, but stop and ownership must be clearly defined.

The example also handles the case where the Java callback throws an exception: the native worker **cannot let its own thread's pending exception automatically appear on the Java caller thread**. The worker retrieves the exception object, clears it on the worker thread, and creates a global ref to transfer it across threads; after `join`, the original JNI method calls `Throw` on that exact throwable so the Java caller can catch it. This is an important point in multithreaded callbacks.

Directory structure:

```text
jni-callback/
├── src/
│   └── demo/
│       └── NativeEvents.java
├── native/
│   └── native_events.cpp
└── build/
    ├── classes/
    └── headers/
```

### 5.1. Java: defining the callback and native entry

**File `src/demo/NativeEvents.java`:**

```java
package demo;

public final class NativeEvents {
    static {
        System.loadLibrary("native_events");
    }

    private NativeEvents() {
    }

    @FunctionalInterface
    public interface EventSink {
        void onEvent(int code);
    }

    private static native void runOnce(EventSink sink);

    public static void main(String[] args) {
        runOnce(code ->
                System.out.println("callback event: " + code));

        System.out.println("native worker finished");

        try {
            runOnce(code -> {
                throw new IllegalStateException("sink failed");
            });
        } catch (IllegalStateException error) {
            System.out.println(
                    "propagated: " + error.getMessage());
        }
    }
}
```

`EventSink` is a nested interface so its Java binary name is `demo.NativeEvents$EventSink`; however, native code **does not need to `FindClass` that name itself**. It receives the callback instance and uses `GetObjectClass`.

### 5.2. C++: holding the right callback object, attaching separately, and propagating errors in a controlled manner

**File `native/native_events.cpp`:**

```cpp
#include "demo_NativeEvents.h"
#include <exception>
#include <thread>

/* Only for helpers called when there is no pending exception. */
static void throwStateError(JNIEnv* env, const char* message) {
    jclass type = env->FindClass("java/lang/IllegalStateException");
    if (type == nullptr) {
        return;  // Keep the error created by FindClass if any.
    }
    env->ThrowNew(type, message);
    env->DeleteLocalRef(type);
}

struct WorkerState {
    JavaVM* vm;
    jobject sinkGlobal;
    jmethodID onEvent;
    jthrowable failureGlobal;
    bool workerFailed;
};

JNIEXPORT void JNICALL Java_demo_NativeEvents_runOnce(
        JNIEnv* env, jclass /*declaringClass*/, jobject sink) {

    if (sink == nullptr) {
        jclass type = env->FindClass(
                "java/lang/IllegalArgumentException");
        if (type != nullptr) {
            env->ThrowNew(type, "sink must not be null");
            env->DeleteLocalRef(type);
        }
        return;
    }

    JavaVM* vm = nullptr;
    if (env->GetJavaVM(&vm) != JNI_OK) {
        throwStateError(env, "cannot get JavaVM");
        return;
    }

    // Look up the method on the ACTUAL CLASS of the callback,
    // right inside the native call from Java.
    jclass sinkClass = env->GetObjectClass(sink);
    if (sinkClass == nullptr) {
        return;  // Keep the JNI exception if any.
    }

    jmethodID onEvent = env->GetMethodID(
            sinkClass, "onEvent", "(I)V");
    env->DeleteLocalRef(sinkClass);

    if (onEvent == nullptr) {
        return;  // JNI may have already set a pending exception.
    }

    // Local ref 'sink' must not be used directly from the worker.
    jobject sinkGlobal = env->NewGlobalRef(sink);
    if (sinkGlobal == nullptr) {
        return;  // OutOfMemoryError may be pending.
    }

    WorkerState state{
        vm, sinkGlobal, onEvent, nullptr, false
    };

    try {
        std::thread worker([&state]() {
            JNIEnv* workerEnv = nullptr;
            jint attached = state.vm->AttachCurrentThread(
                    reinterpret_cast<void**>(&workerEnv), nullptr);

            if (attached != JNI_OK) {
                state.workerFailed = true;
                return;
            }

            workerEnv->CallVoidMethod(
                    state.sinkGlobal, state.onEvent, (jint)42);

            if (workerEnv->ExceptionCheck() == JNI_TRUE) {
                // The exception is pending on the WORKER thread,
                // and cannot automatically propagate to the Java caller thread.
                jthrowable original =
                        workerEnv->ExceptionOccurred();
                workerEnv->ExceptionClear();

                if (original != nullptr) {
                    // Keep the exception object across detach.
                    state.failureGlobal =
                            (jthrowable)workerEnv->NewGlobalRef(
                                    original);
                    workerEnv->DeleteLocalRef(original);

                    if (state.failureGlobal == nullptr) {
                        state.workerFailed = true;
                        // In case of out-of-memory,
                        // avoid leaving an error pending on detach.
                        if (workerEnv->ExceptionCheck()) {
                            workerEnv->ExceptionClear();
                        }
                    }
                } else {
                    state.workerFailed = true;
                }
            }

            if (state.vm->DetachCurrentThread() != JNI_OK) {
                state.workerFailed = true;
            }
        });

        // join ensures the callback and worker finish before
        // releasing sinkGlobal or reading state.
        worker.join();
    } catch (const std::exception&) {
        env->DeleteGlobalRef(sinkGlobal);
        throwStateError(env, "cannot start native worker");
        return;
    }

    if (state.failureGlobal != nullptr) {
        // Set the callback's exact exception object as
        // pending on the JAVA CALLER thread.
        env->Throw(state.failureGlobal);
        // DeleteGlobalRef is allowed while an exception is pending.
        env->DeleteGlobalRef(state.failureGlobal);
    } else if (state.workerFailed) {
        throwStateError(env, "native worker failed");
    }

    // By now the worker has stopped and no longer uses sink.
    env->DeleteGlobalRef(state.sinkGlobal);
}
```

Key points to understand in the code:

- `GetJavaVM` gets an interface that can be passed to a native thread. **Do not pass the Java caller's `env`** into the lambda.
- `GetObjectClass(sink)` and `GetMethodID` are called **before** the worker is created, so the method ID is retrieved on the callback's exact runtime class. This avoids `FindClass` lookups using the wrong loader in the worker.
- `NewGlobalRef(sink)` keeps the Java callback alive while the native thread runs. `DeleteGlobalRef` only happens **after `worker.join()`** and all accesses to the callback have finished.
- `AttachCurrentThread` returns a separate `JNIEnv *`. The worker only calls Java after attaching successfully and calls `DetachCurrentThread` once the callback has completed.
- A Java callback can throw an error. `ExceptionOccurred` creates a local `jthrowable` on the worker; `ExceptionClear` clears the pending exception on the worker to continue using JNI; `NewGlobalRef` holds the `Throwable` object across the thread boundary. The Java calling thread rethrows it via `Throw`. **Do not pass a raw local `jthrowable` to another thread**.
- `WorkerState` lives on the stack of the JNI entry; thanks to `join`, the worker no longer accesses the struct before the entry method returns. Reading the `workerFailed`/`failureGlobal` flags after `join` has proper synchronization ordering.
- This code serves as a **short-lived single-worker demo**. If a thread runs long-term, you need a struct with an independent lifetime (heap/RAII), a stop/ownership mechanism, locks, and shutdown state; do not hold the address of a stack frame from a function that has already returned.
- `std::thread` can fail to construct; the example catches `std::exception` right inside the entry and converts it into a Java exception. Rare system errors during `join` need to be handled separately in a production application that monitors worker lifecycles; the demo assumes `join` of a newly created joinable thread completes as expected.
- If out-of-memory occurs right when converting the callback exception into a global ref, the example reports a general worker error back to Java; a production implementation may have its own critical-error policy. **A C++ exception must never escape directly across the JNI boundary**.

### 5.3. Build and run

From the `jni-callback` directory on **Linux**, use JDK 17+ and a C++17 compiler such as `g++`/`clang++`. The `JAVA_HOME` variable must point to the JDK.

```bash
mkdir -p build/classes build/headers

javac -h build/headers -d build/classes \
  src/demo/NativeEvents.java

g++ -std=c++17 -O2 -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_events.cpp -o libnative_events.so

java -Djava.library.path=. -cp build/classes \
  demo.NativeEvents
```

`javac -h` generates `build/headers/demo_NativeEvents.h`, containing the native symbol name from the Java declaration. On Linux, `System.loadLibrary("native_events")` maps the logical name to `libnative_events.so` in the library search path.

**Expected stdout when the operation succeeds:**

```text
callback event: 42
native worker finished
propagated: sink failed
```

The first time, the worker invokes the Java lambda and prints event 42, after which `join` completes so Java prints the next line. The second time, the callback intentionally throws `IllegalStateException`. JNI transfers **that exact throwable** back to the thread calling `runOnce`, so the Java `catch` prints the message.

Some newer JDKs have a policy for granting native access and may print warnings to **stderr**; on JDK 24+ when running on the classpath, you can add `--enable-native-access=ALL-UNNAMED` before `-cp` if needed. Native access rules do not change thread/class-loader semantics. On Windows/macOS, the dynamic library name and compile/include commands differ; `pthread` is also not a mandatory standard thread API on every platform.

## 6. A Common Mistake Example: Calling `FindClass` Directly in a Worker

Suppose a Java plugin runs from a `URLClassLoader` and has the class `plugin.Handler`. The following native code is risky:

```cpp
// Fragment: running on a native-created attached thread.
jclass handler = workerEnv->FindClass("plugin/Handler");
if (handler == nullptr) {
    // May not see the plugin loader's class:
    // the worker has no corresponding native-method frame.
}
```

In an application run directly on the classpath, this code sometimes works because the system loader happens to find the class. Once the application is moved into a container/plugin loader, the same code can fail. This is why a bug **only appears in production deployments** and does not reproduce in a simple JAR demo.

A more robust solution:

```java
// Java fragment: pluginLoader is provided by the application.
Class<?> exactClass = Class.forName(
        "plugin.Handler", true, pluginLoader);

// Custom-defined native API receives this Class<?>:
nativeRegisterHandler(exactClass);
```

Native code uses `NewGlobalRef` on `exactClass` and `GetStaticMethodID`, or uses a callback instance already created by Java. It no longer asks the worker to pick a loader by class name on its own.

### 6.1. Why not cache a local `jclass`?

`FindClass`/`GetObjectClass` typically returns a **local JNI reference**. If you write:

```cpp
static jclass cachedHandler = nullptr;

void badRegistration(JNIEnv* env, jclass clazz) {
    cachedHandler = clazz; // WRONG: clazz may expire after the JNI call.
}
```

then another thread using `cachedHandler` after the native method returns is a use-after-lifetime bug. Proper caching:

```cpp
// Fragment: called inside a JNI method with a valid clazz.
jclass globalHandler =
        (jclass)env->NewGlobalRef(clazz);
if (globalHandler == nullptr) {
    return; // A Java exception may be pending.
}

// Tie globalHandler to the plugin lifecycle.
// Attached workers can use it with valid JNI APIs.

// After stopping/draining all workers still using it:
env->DeleteGlobalRef(globalHandler);
```

A global ref keeps the class (and indirectly the defining loader) alive across multiple calls. Do not turn a JVM-wide shared cache into a place that keeps piles of old plugin loaders from ever being garbage-collected.

## 7. Which Thread Does an Exception in a Callback Belong To?

**A pending Java exception is state of the current thread.** If a Java callback runs on a native worker and throws an exception, that exception is pending on the worker. The original Java thread **does not automatically know** about it; if the native worker simply calls `DetachCurrentThread` and exits, the error may be lost or logged by the JVM depending on the implementation.

Deliberate strategies include:

1. **The callback handles errors itself in Java** with `try/catch` and sends an explicit result back to native code; suitable for event notifications.
2. **Forward the error to the Java caller** if the caller is waiting on the worker (like `join` in the example): capture `Throwable` with `ExceptionOccurred`, clear pending on the worker, hold it with `NewGlobalRef`, and then call `Throw` on the JNI caller thread after joining.
3. **Report errors asynchronously** via `CompletableFuture`, a queue, an error listener, or an application state machine. Do not try to "throw into" an arbitrary other Java thread.
4. **Log and continue** only when the contract accepts errors being handled at the worker; do not use `ExceptionDescribe` without knowing that it **clears the pending exception**.

When `ExceptionCheck` returns true, do not continue calling `FindClass`, `GetMethodID`, or `CallVoidMethod` as if the callback succeeded. A limited set of JNI functions is allowed to be called with a pending exception, including `ExceptionOccurred`, `ExceptionClear`, `DeleteLocalRef`, `DeleteGlobalRef`, and resource-release functions. If you need new JNI APIs to build a wrapper, clear the exception as planned, preserve the right cause, and only then continue.

**Do not call `DetachCurrentThread` while Java frames from the callback have not yet returned.** In the example, `CallVoidMethod` has completed (even though a pending exception was captured/cleared) before the worker detaches.

## 8. Lifecycle, Synchronization, and Avoiding Keeping Plugin Class Loaders Alive Forever

### 8.1. The problem when workers are long-lived

A plugin is shut down, yet a native thread still holds a global callback reference:

```text
Native worker / native global callback ref
                    │
                    ▼
              Callback object
                    │
                    ▼
            Callback Java class
                    │
                    ▼
           Plugin ClassLoader
```

Even though the application has called `close()` on `URLClassLoader` and dropped the plugin instance in Java, a global reference on the native side can still keep the plugin/class loader reachable. Over multiple reloads, Metaspace leaks, retained old JARs/classes, or callbacks running into a stopped plugin version can occur.

A controlled lifecycle typically looks like this:

1. **Registration:** Java passes the actual callback/class/loader into JNI; native code holds the needed strong global references.
2. **Start:** create the worker and attach to the right JVM; only invoke callbacks when the plugin is in the active state.
3. **Stop accepting new work:** block new scheduling/callbacks.
4. **Drain:** wait for in-flight callbacks to finish or cancel per contract; ensure no thread is still using the refs.
5. **Cleanup:** detach native threads that were attached, delete global refs, destroy queues/handles, and clear `jmethodID` caches per plugin version.
6. **Drop the loader:** Java removes listeners, registries, executors, and any remaining strong references before expecting GC to have a chance to reclaim the loader.

Do not call `DeleteGlobalRef` on thread A while thread B is still using the callback, unless a synchronization/ownership protocol protects it. A strong global reference keeps an object alive, but **does not replace a mutex, lock, or memory ordering** for shared native state.

### 8.2. Do not store `JNIEnv *` or local JNI references in static state

```cpp
// WRONG regarding thread and lifetime.
static JNIEnv* globalEnv;
static jobject callbackLocal;

void registerBad(JNIEnv* env, jobject cb) {
    globalEnv = env;
    callbackLocal = cb;
}
```

`globalEnv` is invalid for a worker thread; `callbackLocal` does not have a cross-call lifetime. If the library needs long-term state, store `JavaVM*` and separate global references with synchronization/cleanup.

### 8.3. When a native thread only needs to run Java logic, consider creating the thread from Java

If the goal is an async Java callback, a less error-prone option is to let Java manage an `ExecutorService`/`Thread.start()` and have native code only signal results. A Java thread is already managed by the VM and has clearer thread groups, exception handlers, thread context class loader, and cancellation management. Only create threads from C/C++ when a native library or an external SDK genuinely imposes its own thread.

This is especially beneficial when a framework relies on the context class loader or security/correlation context of Java worker threads. With a native thread, you must intentionally initialize/restore those contexts.

## 9. Common Errors and How to Diagnose Them

| Symptom | Cause to check | Action |
| --- | --- | --- |
| Crash when using `JNIEnv*` in `pthread` | Using a `JNIEnv*` obtained from another thread | Save `JavaVM*`, attach the worker, and get its own env |
| `FindClass("plugin/Handler")` returns `NULL` on worker | Default loader does not know the plugin class | Pass callback/class/loader from Java; hold a global ref |
| Class is found, but callback method is not found | Wrong JNI signature or using a class from a different loader | Check `javap -s`, `GetObjectClass`, and loader identity |
| Callback runs for a while and then crashes | Local `jobject`/`jclass` was saved across a native return | Use `NewGlobalRef`; release after stop/drain |
| Callback throws, but Java caller cannot catch it | Pending exception resides on the worker thread | Define an error channel; capture+global+`Throw` on caller or future |
| JVM does not exit | Native attached non-daemon thread is still alive | Stop thread, detach; consider daemon when appropriate |
| Plugin still does not unload after redeploy | Global JNI refs, callbacks/threads/registries hold the loader | Explicit teardown, use heap/GC roots analysis |
| `FindClass` works when Java calls JNI, fails from C worker | Lookup context changes based on JNI invocation path | Do not rely on the worker's implicit loader |
| Native deadlock waiting on callback | Callback tries to acquire a Java/native lock held by caller during `join` | Do not hold locks across blocking native calls; design asynchronous handoff |
| `GetMethodID` returns null | No method with the right name/descriptor, or a Java exception is pending | Read the error, check the interface and signature `(I)V` |

### 9.1. Systematic loader debugging

In Java, record:

```java
Class<?> type = callback.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

This is a **fragment**; `callback` is provided by the application. With multiple class loaders having the same name, compare **loader object identity** (not just `toString()`). On the JNI side, you can use `GetObjectClass` and the Java `getClassLoader()` method if diagnosis is genuinely needed, though it is usually simpler to log from Java before passing the callback.

You can use `javap -s` to inspect the descriptor `(I)V` or multi-parameter types; `javac -h` to generate the right JNI symbol; `-Xcheck:jni` on HotSpot to catch many JNI reference and thread usage errors. When debugging a native crash, run the JVM with appropriate logging options and a native debugger.

### 9.2. Some advanced pitfalls

**Class init and deadlock:** `FindClass` can trigger class loading/linking/initialization in a JNI context. On a worker, an unexpected lookup can hold a class-loading lock or wait on a Java thread that is simultaneously waiting on the worker. Resolving classes and methods during a registration phase on a Java thread usually reduces this risk.

**Callbacks and C++ exceptions:** If a Java callback throws `Throwable`, JNI reports it via a pending exception, not via a C++ `throw`. Conversely, a `std::exception` raised in a C++ library must never escape across a JNI frame; catch it and convert it into an appropriate Java exception or a structured asynchronous error.

**Thread context:** A native-attached thread does not automatically inherit the MDC, transaction, tracing, security context, or application context of the Java thread that created the work. Pass context via parameters/events if needed; do not implicitly expect it to appear.

**Multiple JVMs:** A native thread cannot be simultaneously attached to two Java VMs. Do not use a `JavaVM*` belonging to another process/JVM. In most ordinary Java applications there is only one JVM in the process, but the responsibility of keeping the right VM remains mandatory.

## 10. Self-Check Questions

**Question 1.** A JNI method receives `JNIEnv* env` and creates a `std::thread`, and then the lambda uses that same `env` to call `CallVoidMethod`. What is wrong?  
**Answer:** `JNIEnv*` is only valid on the thread that provided it. The lambda must call `AttachCurrentThread` with `JavaVM*` to obtain the worker's env.

**Question 2.** `FindClass("com/app/PluginHandler")` succeeds when called from a Java native method, but fails on a native-attached worker. Is it because the class name is wrong?  
**Answer:** Not necessarily. `FindClass` may use a different class loader when there is no native method frame. Pass the right callback or `Class<?>` from Java instead of relying on implicit lookup.

**Question 3.** Can you save a `jobject callback` received by JNI as a local ref into a C global variable and use it a few minutes later?  
**Answer:** No. You must create a `NewGlobalRef` and only call `DeleteGlobalRef` after the worker is guaranteed to no longer be using the callback.

**Question 4.** A worker Java callback throws `IllegalStateException`. Why does the Java caller thread not see the exception?  
**Answer:** The pending exception is attached to the worker thread. There must be an error-propagation channel; when the caller is waiting, capturing `Throwable` on the worker, converting it to a global ref, and calling `Throw` on the caller after joining is one approach.

**Question 5.** Does calling `Thread.currentThread().setContextClassLoader(loader)` on a worker guarantee that `FindClass` will use that loader?  
**Answer:** No. `FindClass` follows class-loader rules based on the JNI call context; the context class loader only affects Java code/frameworks that actively look it up.

**Question 6.** Is caching `jmethodID` by method name safe after a plugin class loader unloads and reloads?  
**Answer:** No. The ID is tied to the loaded declaring class; after the class unloads, the ID is no longer valid. Each class/loader version must have a clear registration and cleanup lifecycle.

**Question 7.** A native thread attaches but never detaches; what is the impact?  
**Answer:** It can hold resources and cause the JVM to wait on a non-daemon thread. It needs to be stopped/detached according to the lifecycle; attaching a new thread as a daemon when appropriate does not remove the cleanup obligation.

**Question 8.** What is the benefit of `GetObjectClass(callback)` + `GetMethodID` + a global ref during registration?  
**Answer:** It uses the Java callback's exact runtime class, resolves the right loader, keeps the object alive for as long as the worker needs it, and reduces reliance on `FindClass` on native threads.

## 11. Production Deployment Checklist

- [ ] Identify which threads are created from Java and which are created by the native library; only detach threads you actually attached.
- [ ] Every native worker calling JNI has **its own thread's** `JNIEnv*`; store `JavaVM*` instead of sharing `env`.
- [ ] Callbacks and classes/loaders needed after the native method returns are held via **global JNI references** with a clear owner and deletion point.
- [ ] Resolve classes/methods at registration in the right Java/class-loader context; check JNI method signatures and pending exceptions.
- [ ] Avoid `FindClass` for app/plugin classes from a native worker without actively determining the right loader.
- [ ] When a Java callback throws, have a clear **error channel** (caller, future, queue, or listener); do not swallow errors silently.
- [ ] The worker has a stop/drain/join or shutdown protocol; do not delete global refs while callbacks are still running.
- [ ] Do not hold locks that can create a wait cycle when the Java caller and native worker call back and forth.
- [ ] After stopping, clean up references/threads/native handles/caches and drop references holding old plugin loaders.
- [ ] Test both the simple Java classpath case **and** the app loaded through a real class loader (container/plugin), including reload.

## 12. Key Takeaways and Reference Materials

- **`JavaVM*` is tied to the VM; `JNIEnv*` is tied to the thread.** A native thread must attach before any JNI call and detach when finished.
- **`FindClass` selects a loader based on the JNI context**, not by default according to the desired plugin loader or the thread context class loader.
- For callbacks, **passing an instance or `Class<?>` from Java and holding a global ref** is the easiest way to establish the right class identity.
- **Local refs do not outlive the native frame**, while global refs must be deleted according to lifecycle to avoid leaks and class-loader retention.
- **Pending exceptions are thread-local**; if the Java caller should receive errors from a worker, an explicit handoff mechanism is required.
- **Stop/drain before deleting global refs**, maintain synchronization, and do not let native callbacks continue running into an unloaded plugin.

Official sources:

- [Oracle JNI Specification — Invocation API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `AttachCurrentThread`, `DetachCurrentThread`, `GetEnv`, thread context loader, and thread rules.
- [Oracle JNI Specification — Functions: FindClass (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): how `FindClass` selects a class loader from the current native method or Invocation Interface.
- [Oracle JNI Specification — Functions: Object/Global Reference/Method Operations](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, `GetObjectClass`, `GetMethodID`, and `CallVoidMethod`.
- [Oracle JNI Specification — Design Overview (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): class-name conventions, Java/native exceptions, and reference lifetime.
- [Android NDK — JNI Tips (Google)](https://developer.android.com/ndk/guides/jni-tips): practical experience with callbacks, attached threads, and class-loader lookup on the Android runtime; treat as an ecosystem example, not a replacement for the Java SE JNI standard.

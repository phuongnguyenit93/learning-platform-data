# Attaching Native Threads with AttachCurrentThread or AttachCurrentThreadAsDaemon (JNI)

## 1. When Must a Native Thread Attach to the JVM?

In JNI (Java Native Interface), a Java thread calling a `native` method already has a JNI context to execute C/C++ code. However, an application can also create **threads from the native side** using `std::thread`, `pthread_create`, `CreateThread`, or a C/C++ library's thread pool. Such a thread does not automatically have permission to use `JNIEnv` to access objects, classes, or invoke Java methods.

For a **library-created native thread** to call back into Java, that thread must **attach to the JVM** using one of two functions from the **JNI Invocation API**:

- `JavaVM::AttachCurrentThread`: attaches the current thread to the JVM in **non-daemon (user thread)** state.
- `JavaVM::AttachCurrentThreadAsDaemon`: attaches the current thread to the JVM in **daemon thread** state.

Both provide a `JNIEnv*` pointer **belonging to the exact thread that called attach**. When the native thread finishes its work and has no Java frames left on the stack, it must call `JavaVM::DetachCurrentThread` before terminating. You should not keep a thread permanently attached just because you do not see an immediate error.

**Important rule:** attaching is an operation of the **currently running thread**. You cannot call `AttachCurrentThread` from thread A to attach on behalf of thread B. Whichever thread needs JNI access must **itself** call attach, obtain its own `JNIEnv*`, and then detach itself at the proper time.

### 1.1. Timing Model

```text
Java main thread                         Native worker (std::thread)
       |                                            |
       | calls native launch(...)                   |
       |          |                                 | (newly created, not yet attached)
       |          +---- creates worker ------------>|
       |                                            |
       |                                  JavaVM.AttachCurrentThread(...)
       |                                  or AttachCurrentThreadAsDaemon(...)
       |                                            |
       |                                  receives worker's JNIEnv*
       |                                            |
       |                                  looks up class/method, calls Java
       |<---------------------- Java callback ------+
       |                                            |
       |                                  JavaVM.DetachCurrentThread()
       |                                            |
       |<---------------------- worker finishes ----+
       |          |
       |   join worker, complete
       |
```

In the usual **Java → native** call direction, the JNI runtime passes `JNIEnv*` into the C function. In the **native-created thread → Java** direction, the worker must attach before it is allowed to use the JNI API.

## 2. How Does `JavaVM*` Differ from `JNIEnv*`?

| Object | Scope of Use | Purpose |
| --- | --- | --- |
| `JavaVM*` | Can be stored/shared across native threads for the lifetime of the JVM | Call `GetEnv`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread` |
| `JNIEnv*` | **Valid only in the thread that owns it** | `FindClass`, `GetMethodID`, `Call...Method`, create/read JNI references, check exceptions |

Do not pass or cache a `JNIEnv*` obtained from thread A and use it on thread B. Each thread must obtain **its own** interface pointer. Conversely, you can store `JavaVM*` from `JNIEnv::GetJavaVM` or the `JNI_OnLoad` parameter so that native workers can obtain a `JNIEnv*` when needed.

In **C++** (wrapper-style JNI API):

```cpp
JavaVM* vm = nullptr;
jint result = env->GetJavaVM(&vm);
```

The snippet above is an **excerpt inside a JNI function that already has `JNIEnv* env`**; it is not a standalone program. If `result == JNI_OK`, `vm` can be retained to call Invocation API functions in other native threads. It must not be inferred that `env` on the first line can be retained for shared use.

In **C**, instead of the C++ syntax `vm->...`, it typically takes the form:

```c
JavaVM *vm = NULL;
jint result = (*env)->GetJavaVM(env, &vm);
/* In the C native worker: */
JNIEnv *thread_env = NULL;
jint rc = (*vm)->AttachCurrentThread(vm, (void **)&thread_env, NULL);
```

Both call styles perform the same functionality but differ in wrapper syntax in `jni.h`.

## 3. Distinguishing AttachCurrentThread from AttachCurrentThreadAsDaemon

| Criterion | `AttachCurrentThread` | `AttachCurrentThreadAsDaemon` |
| --- | --- | --- |
| State on **first attach** | Non-daemon | Daemon |
| Returned pointer | `JNIEnv*` of the current thread | `JNIEnv*` of the current thread |
| Ability to call Java/JNI | Yes | Yes |
| Thread already attached? | Returns existing `JNIEnv*`; does not change daemon status | Also returns existing `JNIEnv*`; does not change daemon status |
| Impact on JVM shutdown | A non-daemon thread can make the JVM wait before exiting | A daemon thread **does not keep the JVM alive merely because it is still running** |
| Cleanup | Must detach before the native thread exits | Must also detach before the native thread exits |
| Typical use | Workers that must complete critical work before shutdown | Background workers where the system has its own cancellation/shutdown procedure |

**Daemon does not mean “the thread is automatically freed”.** It only affects the rule of **whether the JVM must still wait for non-daemon threads**. A daemon thread must still have its resources managed, errors reported, be stopped, and be detached. If the JVM is shutting down while a daemon native thread still wants to call Java, you must not assume callbacks will continue to work normally.

### 3.1. Choosing Correctly on the Very First Attach

If the thread is not yet attached:

```cpp
JNIEnv* threadEnv = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void**>(&threadEnv), nullptr);
```

Creates a non-daemon attachment.

If the thread is not yet attached and you want a daemon:

```cpp
JNIEnv* threadEnv = nullptr;
jint rc = vm->AttachCurrentThreadAsDaemon(
        reinterpret_cast<void**>(&threadEnv), nullptr);
```

Creates a daemon attachment.

In both examples above, `vm` is a valid `JavaVM*` and the code runs **inside the native thread that needs to attach**. After the call, you must check `rc == JNI_OK` and `threadEnv != nullptr` before using `threadEnv`.

**Case when already attached:** JNI specifies that calling attach again returns the existing `JNIEnv*` and **does not convert** non-daemon to daemon or vice versa. Therefore, if `AttachCurrentThread` has already been called, calling `AttachCurrentThreadAsDaemon` afterward **does not turn that thread into a daemon**; if you want a different choice, design the lifecycle from the start (do not detach/re-attach while Java frames remain).

### 3.2. Specific Shutdown Scenarios

Suppose Java `main` finishes, but there is still an attached native worker:

- If the worker is **non-daemon**, the JVM counts it among non-daemon threads that can prevent the Java process from exiting until the thread exits/detaches according to the appropriate lifecycle.
- If the worker is **daemon**, its existence alone does not keep the JVM running. The JVM may begin shutting down while it has not finished.
- A `std::thread::join()` call on the Java/JNI side **actively waits for the worker to finish**, regardless of whether the worker attached as daemon or non-daemon. Therefore, you must distinguish **waiting caused by the program calling join** from **the JVM-keeping rule of daemon status**.

Do not choose daemon just to “fix” a thread leak; the right thing to do is design explicit stop signals, resource teardown, and detach.

## 4. Lifecycle: attach → use JNI → detach

Workflow for a C/C++-created worker:

1. Obtain or store `JavaVM*` in a valid JNI context.
2. Create the native worker. **Inside the worker's body**, call `AttachCurrentThread` or `AttachCurrentThreadAsDaemon`, depending on requirements.
3. Check the return code; only when `JNI_OK` should you use the returned `JNIEnv*`.
4. When needed, store `jobject`/`jclass` used across multiple threads using a **global reference**; do not bring a local reference over from another thread.
5. Look up methods, call Java, check and handle any pending Java exception.
6. Ensure all Java methods have returned to native, all related JNI resources have been resolved, and no Java frames remain running on the worker's stack.
7. Call `DetachCurrentThread` from **the worker itself** before the native worker exits. After detaching, do not use the old `JNIEnv*`.

If `AttachCurrentThread` fails, there is no successful attachment to detach. If the worker was **already attached beforehand**, you must know who owns that attachment; do not arbitrarily detach a thread serving another Java framework just because you called `GetEnv` or called attach again.

### 4.1. Detach Condition That Is Easy to Forget

The JNI Specification states that a thread **cannot detach itself while Java methods are still on the call stack**. For example:

- Correct: native worker attaches → calls Java callback → callback returns to native → native worker detaches.
- Incorrect: requesting detach while the Java callback is still running on the same stack (or calling detach before unwinding nested Java call stacks).

If a native thread exits while still attached, JVM resources associated with the thread may be retained or behavior may violate the API contract. The native worker needs cleanup even on failure branches. Do not treat detach as an optional operation.

## 5. GetEnv: Checking Whether a Thread Is Already Attached

`JavaVM::GetEnv` **does not automatically attach**. It queries the attachment status of the **current thread** for a requested JNI version:

```cpp
JNIEnv* threadEnv = nullptr;
jint rc = vm->GetEnv(
        reinterpret_cast<void**>(&threadEnv),
        JNI_VERSION_1_6);

if (rc == JNI_OK) {
    // Thread is already attached; threadEnv is valid on this exact thread.
} else if (rc == JNI_EDETACHED) {
    // Thread is not attached yet; can attach yourself if needed.
} else if (rc == JNI_EVERSION) {
    // JVM does not support the requested JNI version.
}
```

This is an **illustrative C++ snippet placed in code that already has a valid `JavaVM* vm`**. `JNI_VERSION_1_6` is supported by JDK 17 and commonly used in JNI examples; it does not mean the Java program must run on Java 6.

A useful attachment-ownership pattern:

```cpp
JNIEnv* env = nullptr;
bool attachedHere = false;

jint status = vm->GetEnv(
        reinterpret_cast<void**>(&env), JNI_VERSION_1_6);

if (status == JNI_EDETACHED) {
    status = vm->AttachCurrentThread(
            reinterpret_cast<void**>(&env), nullptr);
    if (status == JNI_OK) {
        attachedHere = true;
    }
}
if (status != JNI_OK || env == nullptr) {
    // Report error to the work owner.
    return;
}

// Access JNI using env on this exact thread.
// ... Complete all Java callbacks and resolve exceptions ...

if (attachedHere) {
    (void) vm->DetachCurrentThread();
}
```

This pattern is **not a standalone program**; in real code, cleanup should be placed in a construct guaranteed to run on every exit path, such as a C++ RAII guard. It avoids detaching a thread that was already attached beforehand and managed by Java/runtime.

## 6. Complete Java 17 + C++17 Example: Native Thread Calling Back into Java

This example demonstrates **two different attaches**, one non-daemon and one daemon. Java calls a JNI entry point to create a `std::thread`; that `std::thread` itself invokes a Java callback, then detaches. The JNI entry point calls `join()` before returning, so stdout order is deterministic.

The example uses C++17 instead of `pthread` to unify cross-platform logic; build separately for Linux, macOS, and Windows. The library must be compiled for the matching OS/CPU/JDK headers.

### 6.1. File `NativeAttachDemo.java`

```java
public final class NativeAttachDemo {
    static {
        System.loadLibrary("nativeattachdemo");
    }

    private NativeAttachDemo() {
    }

    // Implemented in NativeAttachDemo.cpp.
    private static native void launch(boolean daemon);

    // The native worker will call this method after attaching.
    private static void onNativeThread() {
        System.out.println(
                "callback: daemon=" + Thread.currentThread().isDaemon());
    }

    public static void main(String[] args) {
        launch(false);  // AttachCurrentThread (non-daemon).
        launch(true);   // AttachCurrentThreadAsDaemon.
        System.out.println("finished");
    }
}
```

`Thread.currentThread()` here is the `java.lang.Thread` object representing the attached native thread. The `isDaemon()` method reflects how the native worker's **first attach** was performed.

### 6.2. Generating the JNI Header from Java

In the directory containing `NativeAttachDemo.java`, run with JDK 17+:

```bash
javac -h . NativeAttachDemo.java
```

The result is `NativeAttachDemo.class` and `NativeAttachDemo.h`. The header confirms the JNI native symbol `Java_NativeAttachDemo_launch` and parameters `JNIEnv*`, `jclass`, and `jboolean`. Do not guess symbol names when classes/packages change; use the header generated by `javac -h`.

### 6.3. File `NativeAttachDemo.cpp`

```cpp
#include "NativeAttachDemo.h"

#include <atomic>
#include <exception>
#include <thread>

static void throwIllegalState(JNIEnv* env, const char* message) {
    jclass errorClass = env->FindClass("java/lang/IllegalStateException");
    if (errorClass != nullptr) {
        env->ThrowNew(errorClass, message);
        env->DeleteLocalRef(errorClass);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_NativeAttachDemo_launch(
        JNIEnv* callerEnv, jclass javaClass, jboolean daemon) {

    // Java calls native: callerEnv belongs only to the calling Java thread.
    JavaVM* vm = nullptr;
    if (callerEnv->GetJavaVM(&vm) != JNI_OK || vm == nullptr) {
        throwIllegalState(callerEnv, "Cannot obtain JavaVM");
        return;
    }

    // Local jclass is only valid in the incoming JNI call context.
    // Only a global reference can be safely held across a native thread.
    jclass globalClass = static_cast<jclass>(
            callerEnv->NewGlobalRef(javaClass));
    if (globalClass == nullptr) {
        return;  // The JVM may have already set OutOfMemoryError.
    }

    std::atomic<int> workerStatus{0};

    try {
        std::thread worker([vm, globalClass, daemon, &workerStatus]() {
            JNIEnv* workerEnv = nullptr;
            char name[] = "jni-native-worker";

            JavaVMAttachArgs args{};
            args.version = JNI_VERSION_1_6;
            args.name = name;
            args.group = nullptr;

            jint attached = (daemon == JNI_TRUE)
                    ? vm->AttachCurrentThreadAsDaemon(
                            reinterpret_cast<void**>(&workerEnv), &args)
                    : vm->AttachCurrentThread(
                            reinterpret_cast<void**>(&workerEnv), &args);

            if (attached != JNI_OK || workerEnv == nullptr) {
                workerStatus.store(1);
                return;
            }

            // Both JNI lookup and callback run inside the attached worker.
            jmethodID callback = workerEnv->GetStaticMethodID(
                    globalClass, "onNativeThread", "()V");

            if (callback != nullptr) {
                workerEnv->CallStaticVoidMethod(globalClass, callback);
            }

            if (workerEnv->ExceptionCheck()) {
                // Demo: print details to stderr and report error back to caller.
                // In real production code, you can forward the throwable via
                // a global reference or send the error to an event queue.
                workerEnv->ExceptionDescribe();
                workerEnv->ExceptionClear();
                workerStatus.store(2);
            } else if (callback == nullptr) {
                workerStatus.store(2);
            }

            // Ensure the Java callback has returned to C++ before detaching.
            if (vm->DetachCurrentThread() != JNI_OK) {
                workerStatus.store(3);
            }
            // workerEnv must no longer be used from this point on.
        });

        // Both modes wait for the worker to finish for a deterministic example.
        worker.join();
    } catch (const std::exception&) {
        callerEnv->DeleteGlobalRef(globalClass);
        throwIllegalState(callerEnv, "Cannot create/join native worker");
        return;
    }

    // Worker has finished; globalClass is no longer used.
    callerEnv->DeleteGlobalRef(globalClass);

    if (workerStatus.load() != 0) {
        throwIllegalState(callerEnv, "Native worker failed");
    }
}
```

This is **the complete code of a JNI shared library** used in this example; `JNI_OnLoad` is not needed because `JavaVM*` is obtained via `callerEnv->GetJavaVM(&vm)` right when Java calls the native method.

Key points to understand:

- `callerEnv` belongs to the **Java calling thread**. It is only used outside the lambda; the worker **does not use** it.
- `vm` belongs to the JVM and can be shared across threads while the JVM exists. The worker uses `vm` to attach and then receives its own `workerEnv`.
- `javaClass` is a **local reference** of the initial call. `NewGlobalRef` creates `globalClass` that can be used in the worker; it is deleted with `DeleteGlobalRef` once `join` completes.
- `GetStaticMethodID` and `CallStaticVoidMethod` happen after attaching. The callback has descriptor `()V` because it takes no parameters and returns `void`.
- `ExceptionCheck` is called inside the worker because a callback exception belongs to **the JNI environment on that worker**, and does not automatically surface as a Java exception in the thread calling `launch`. The example logs to stderr and converts it into a generic `IllegalStateException` on the original calling thread; production code should propagate a clearer cause if needed.
- `DetachCurrentThread` runs **inside the worker**, after the callback has finished; `std::thread::join` runs on the original calling thread to synchronize lifecycles.
- `workerStatus` is atomic to exchange error status between the two threads; normal output ordering does not depend on scheduler speed.

### 6.4. Compiling and Running on Linux

Requires JDK 17+ with `JAVA_HOME` set properly, the `g++` compiler, and pthread support:

```bash
javac -h . NativeAttachDemo.java

g++ -std=c++17 -shared -fPIC -pthread \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    NativeAttachDemo.cpp -o libnativeattachdemo.so

java -Djava.library.path=. NativeAttachDemo
```

### 6.5. Compiling and Running on macOS

Requires JDK 17+ with `JAVA_HOME` set properly and Clang/Xcode Command Line Tools:

```bash
javac -h . NativeAttachDemo.java

clang++ -std=c++17 -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    NativeAttachDemo.cpp -o libnativeattachdemo.dylib

java -Djava.library.path=. NativeAttachDemo
```

### 6.6. Compiling and Running on Windows

Open the Developer Command Prompt for Visual Studio matching the JDK architecture (for example, x64). Configure `JAVA_HOME` and run with `cmd.exe`:

```bat
javac -h . NativeAttachDemo.java

cl /nologo /std:c++17 /EHsc /LD ^
    /I"%JAVA_HOME%\include" ^
    /I"%JAVA_HOME%\include\win32" ^
    NativeAttachDemo.cpp /link /OUT:nativeattachdemo.dll

java -Djava.library.path=. NativeAttachDemo
```

The `^` in the Windows example is the line-continuation character of `cmd.exe`; if running in PowerShell, use a single-line `cl` command or the appropriate PowerShell syntax.

### 6.7. Output and Analysis

If compilation, library loading, and callbacks succeed, the **exact stdout** of both attaches is:

```text
callback: daemon=false
callback: daemon=true
finished
```

Explanation:

1. `launch(false)` creates a new worker. The worker calls `AttachCurrentThread`, so `Thread.currentThread().isDaemon()` in the callback is `false`.
2. The first worker detaches and exits, and `join` returns.
3. `launch(true)` creates another new worker, which calls `AttachCurrentThreadAsDaemon`, so the callback prints `true`.
4. The second worker detaches, `join` returns; Java prints `finished`.

Because each `launch` waits for `join`, the line order is always deterministic on the success path. **Do not take this example as proof that a daemon thread is automatically joined or automatically detached**: both actions are explicitly written by the program.

**JDK 24+ Note:** Some configurations/JDKs may warn or restrict native access under the mechanism introduced in JDK 24 (JEP 472). When running on the classpath on a JDK that supports it, you can grant permission explicitly:

```bash
java --enable-native-access=ALL-UNNAMED \
     -Djava.library.path=. NativeAttachDemo
```

This command is for JDKs that support that option; for JDK 17, use the original run command above. JVM warning messages, if any, normally go to stderr and are not part of the example's stdout.

## 7. JavaVMAttachArgs: Setting Name and ThreadGroup for a Native Worker

The last parameter of attach can be `nullptr` for the JVM to use defaults, or a `JavaVMAttachArgs` struct:

```cpp
char name[] = "camera-callback";

JavaVMAttachArgs args{};
args.version = JNI_VERSION_1_6;
args.name = name;
args.group = nullptr;

JNIEnv* env = nullptr;
jint rc = vm->AttachCurrentThreadAsDaemon(
        reinterpret_cast<void**>(&env), &args);
```

This is a **code snippet used inside a native thread**, with an already valid `JavaVM* vm`.

- `version`: the JNI version specified in the struct. Do not confuse it with the Java language level or JVM version number (`17` is not a value to assign directly).
- `name`: the name used for the representing Java thread; the name data follows JNI's **modified UTF-8** convention. Use a valid char array during the attach call; if no name is needed, set `nullptr`.
- `group`: a global reference (`global reference`) to a `ThreadGroup`, or `nullptr` to use the default. Do not pass a local reference from another thread.
- If the thread is **already attached**, calling attach again only returns the existing interface pointer; do not use a second attach as an API to change the name, group, or daemon status.

On a newly attached thread, the initial context class loader according to the specification is the **bootstrap loader**. Therefore, if native callback code uses `FindClass` to look up an arbitrary application class, the result may not be as expected when there is no Java calling frame.

## 8. Class Loaders and References: Common Errors After a Successful Attach

### 8.1. `FindClass` Cannot Find Application Classes

A native-created thread after attaching has no Java caller to determine the loader like a Java→native call. Therefore, code like:

```cpp
jclass cls = env->FindClass("com/example/MyCallback");
```

may fail even though `MyCallback.class` is on the classpath of a specific application class loader.

**A reliable approach in many cases:** from a Java thread that already knows the right class, create a **`NewGlobalRef` for the `jclass` or callback object**; pass that global reference into the worker as in the `NativeAttachDemo` example. You can cache `jmethodID` after looking up the right class, provided you still manage the corresponding class/loader lifecycle. In complex plugin/class loader systems, you can also intentionally set an appropriate context class loader, but you should not expect it to be right by default.

### 8.2. Local JNI References Do Not Survive Across Threads

`jobject` and `jclass` received in a JNI method are typically **local references** of the current context. Capturing a local ref directly into a `std::thread` and using it after the native method returns can lead to an invalidated reference. When access from a worker is needed:

1. Call `NewGlobalRef` before transferring usage rights.
2. Let the worker use the global ref throughout its valid lifetime.
3. Call `DeleteGlobalRef` when you are certain no thread is still using it.

Not all JVM objects should be held with a global ref forever; a strong reference can also prevent the GC from collecting the object.

### 8.3. Do Not Call Java When the Thread Is Not Attached

Incorrect example:

```cpp
// WRONG: callerEnv obtained from another Java thread!
std::thread worker([callerEnv]() {
    callerEnv->FindClass("java/lang/String");
});
```

This is **error-illustrating code**, not an example to run. `callerEnv` belongs to the Java calling thread; bringing that pointer into the worker violates the JNI contract and can cause unpredictable errors or crashes.

Correct: capture `JavaVM*` (with a valid lifetime), attach inside the worker, and use the newly returned `JNIEnv*` in that exact worker.

## 9. Exceptions, Shutdown, and Cleanup in Real Applications

### 9.1. When a Java Callback Throws an Exception

If a Java method invoked via `Call...Method` throws an exception, **the native worker's JNIEnv** will have a pending exception. Do not assume it automatically propagates to the thread that created the worker on the Java side. Handling options:

- Detect using `ExceptionCheck()`.
- Capture the cause and forward it to the product's error-reporting mechanism (logging, dedicated error callback, event queue, future/promise). If passing a `jthrowable` across threads, manage references properly.
- Only call `ExceptionClear()` when you have **actively decided how to handle it**; do not clear exceptions silently.
- Clean up and detach in the proper order when no Java calls remain on the stack.

In the example above, `ExceptionDescribe` writes diagnostics to stderr and the exception is intentionally cleared so the worker can detach; the original calling thread receives a generic `IllegalStateException` if the worker reports an error. This is an educational path, not a full cross-thread stack-trace preservation mechanism.

### 9.2. Stopping Native Workers Before the JVM Exits

Especially with daemon workers, a teardown sequence is needed:

1. The Java or native owner emits a stop signal.
2. The worker stops issuing new callbacks, exits its loop, and cleans up JNI resources.
3. The worker detaches and exits the native thread.
4. The owner joins or waits for completion while the JVM is still valid; deletes global references of cached objects/classes.

Do not call attach/callbacks after the VM has shut down. Do not confuse “daemon does not block shutdown” with “daemon is guaranteed to be waited on by Java until completion”.

### 9.3. Do Not Arbitrarily Detach a Java-Created Thread

When Java calls down into a native method, the thread is already **attached**. Do not call `DetachCurrentThread` inside that native method: Java frames are still on the call stack and detaching under those circumstances is invalid. Only detach native-created threads that your code actually owns, after Java callbacks have returned to C/C++.

### 9.4. Performance and Thread Pools

Attach/detach has runtime cost; creating and destroying a native thread for every small event can be too expensive. For heavy workloads, you can use a native thread pool: each worker attaches once at startup, handles callbacks over an appropriate lifecycle, and detaches when the thread exits. However:

- Do not let an **unbounded/infinite non-daemon worker** block JVM exit.
- Do not hold JNI local references or global Java objects longer than necessary.
- Do not keep callbacks on daemon workers active after shutdown.
- Measure latency, GC, thread count, and clean shutdown capability in the actual runtime environment.

## 10. Common Mistakes and How to Fix Them

| Mistake | Why Is It Dangerous? | Correct Approach |
| --- | --- | --- |
| Using a Java thread's `JNIEnv*` in a native worker | `JNIEnv*` is only valid in its owning thread | Share `JavaVM*`, attach the worker to obtain its own `JNIEnv*` |
| Calling `GetEnv` and thinking the JVM will auto-attach | `GetEnv` may return `JNI_EDETACHED` | If detached, call the appropriate Attach and manage detach yourself |
| Not checking the Attach result | `JNIEnv*` may not be valid | Only use if `rc == JNI_OK` and the pointer is non-null |
| Calling AttachAsDaemon after Attach to change state | Re-attaching an already attached thread does not change daemon status | Choose the right type before the first attach |
| Calling `DetachCurrentThread` from another thread | Detach belongs to the current thread itself | The worker detaches itself inside the worker's own body |
| Detaching before a Java callback has returned | Cannot detach while Java frames remain on the stack | Wait for the callback to return to C/C++, then detach |
| Forgetting to detach when a native worker exits | Resource leak / broken JVM lifecycle | Design cleanup for every success and error branch |
| Capturing a local `jobject` from another thread | Local refs cannot be used arbitrarily across threads/lifetimes | `NewGlobalRef` and `DeleteGlobalRef` according to ownership |
| `FindClass` in an attached worker not finding app classes | The context class loader may differ, typically bootstrap | Pass a `jclass`/object global ref from the right loader |
| Ignoring Java exceptions after a callback | The error may sit in the worker env; further JNI calls are invalid | `ExceptionCheck` and propagate/report the error clearly |
| Using daemon to “avoid having to clean up” | Daemon only affects keeping the JVM alive | Manage stop, join, references, and detach |
| Using an infinite non-daemon without a stop mechanism | The JVM may be unable to shut down | Provide a mechanism to stop the worker and detach |
| Keeping `JavaVM*` and using it after shutdown | The JVM lifecycle has ended | Synchronize shutdown before the VM stops |

## 11. Knowledge Check Q&A

**1. If a native thread already has `JavaVM*`, does it still need to attach?** If the thread is not yet attached and wants to call JNI, **yes**. `JavaVM*` lets you **obtain** the environment; it does not replace `JNIEnv*`.

**2. Is `GetEnv` returning `JNI_EDETACHED` a critical error?** Not necessarily. It indicates that **the current thread is not attached yet**. If you need to perform JNI calls, call the corresponding Attach and check the result.

**3. Will calling `AttachCurrentThreadAsDaemon` on a non-daemon thread convert it to daemon?** No. For an already attached thread, attach only returns the current interface pointer and preserves the existing daemon status.

**4. Can one `JNIEnv*` be used for an entire native thread pool?** No. Each thread in the pool needs its own environment and proper cleanup.

**5. Is a daemon native worker required to call `DetachCurrentThread`?** Yes. The detach rule is not waived due to daemon status.

**6. Right after the worker finishes calling `CallStaticVoidMethod`, can it detach immediately?** Yes, once the callback has returned to native and the necessary cleanup/exception conditions have been satisfied; it must not detach while the Java method is still on the call stack.

**7. Why does the example print stdout in exact order even though it creates native threads?** Because `launch` calls `join()` on each worker before returning to Java. This is not an automatic property of daemon threads.

**8. Why might `FindClass("app/MyClass")` fail after attaching?** The context class loader of a newly attached thread does not automatically match the application class loader; you need to pass a class/global ref or configure lookup appropriately.

## 12. Production Checklist

1. Identify whether a thread is **Java-created** or **native-created** and who owns the attachment.
2. Store/share `JavaVM*` properly, **never share `JNIEnv*`**.
3. If needed, call `GetEnv` to distinguish `JNI_OK` / `JNI_EDETACHED` / `JNI_EVERSION`.
4. Choose **non-daemon** or **daemon** according to the application's liveness requirements **before the first attach**.
5. Check the `JNI_OK` return code and use the right `JNIEnv*` on the attached thread.
6. Use **global references** for cross-thread data, paying attention to class loaders and JNI exceptions.
7. Finish Java callbacks before detaching; do not detach threads owned by Java/runtime.
8. Clean up resources, release global refs, **detach inside the worker itself**, and do not use the env afterward.
9. Design stop/join during JVM shutdown, especially for native daemon workers.
10. Use tests and monitoring for the success path, attach failures, callback errors, Java shutdown, and resource leaks.

## Official References

- [Oracle Java 17 — JNI Specification, Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `GetEnv`, and `DetachCurrentThread` functions.
- [Oracle Java 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `GetJavaVM`, local/global references, method lookup, Java callbacks, and exception handling.
- [Oracle Java 17 — JNI Types](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `JNIEnv`, `jobject`, `jclass`, JNI signatures.
- [Oracle Java 17 — Thread.isDaemon](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#isDaemon()): how to read a thread's daemon status in Java.
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): warning/native access permission mechanism for JNI starting in JDK 24.

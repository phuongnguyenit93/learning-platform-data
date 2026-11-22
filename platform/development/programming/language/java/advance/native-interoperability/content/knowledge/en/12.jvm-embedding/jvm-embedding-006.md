# Attaching Host Application Threads and Coordinating Their Lifecycle When Embedding the JVM

## 1. Context: C/C++ Application as Host, JVM as Embedded Component

When **embedding the JVM**, the root program is a native application (for example, a C++ server, desktop software, media processor, or device control application). This application **initializes the JVM itself** via the **JNI Invocation API**, rather than running from the `java Main` command. Once it has a `JavaVM*`, it can invoke Java classes and methods from its own multiple native threads.

Common scenario:

- The host coordinator thread initializes the JVM, configures the classpath, and creates the necessary Java objects.
- Native workers are created by `std::thread`, `pthread`, Win32 threads, or a native thread pool.
- Each worker needs to call Java (business processing, rule checking, callbacks, Java logging...) so it must **attach to the host's JVM**.
- After the work is complete, the host asks the workers to stop accepting work, waits for them to finish returning all Java callbacks, **detaches the appropriate threads**, cleans up JNI references, and only then calls **DestroyJavaVM**.

The key point of this article: **performing the attach operation correctly is not enough**. You must design **who creates the JVM, who owns each thread, who is allowed to use `JNIEnv*`, who closes the work intake gate, who waits for `join`, and when DestroyJavaVM may be called**. The wrong order can cause deadlocks at shutdown, native thread leaks, or crashes from using JNI after the JVM no longer exists.

> Core rule: **`JavaVM*` is shared among workers while the JVM is alive; `JNIEnv*` belongs only to the thread that obtained it. Whichever native worker needs JNI, that worker itself attaches and detaches. The host destroys the JVM only when all native workers that might call Java have stopped and been reclaimed.**

## 2. From Host Application to JVM: Initialize Once

### 2.1. `JNI_CreateJavaVM`

The native application initializes the JVM with:

```cpp
jint JNI_CreateJavaVM(
        JavaVM** p_vm, void** p_env, void* vm_args);
```

This is an **illustrative API signature**. In C++ with `jni.h`, you pass the address of `JavaVM*`, the address of `JNIEnv*`, and a configured `JavaVMInitArgs`:

```cpp
JavaVM* vm = nullptr;
JNIEnv* hostEnv = nullptr;

char classpath[] = "-Djava.class.path=.";
JavaVMOption option{};
option.optionString = classpath;

JavaVMInitArgs args{};
args.version = JNI_VERSION_1_6;
args.nOptions = 1;
args.options = &option;
args.ignoreUnrecognized = JNI_FALSE;

jint rc = JNI_CreateJavaVM(
        &vm, reinterpret_cast<void**>(&hostEnv), &args);
```

This code snippet is an **excerpt inside a C++ host function**, not a separately compiled program. The complete example is in section 7.

When successful (`rc == JNI_OK`), the thread calling `JNI_CreateJavaVM` becomes the **main thread of the JVM** and is already attached; `hostEnv` is the `JNIEnv*` dedicated to **that thread itself**. You must not take `hostEnv` and share it with other workers.

**Two fundamental limitations:**

1. An application must not be designed as if it can call `JNI_CreateJavaVM` every time it receives a request. The JNI Invocation API **does not support creating multiple independent JVMs within the same process** as a normal mechanism.
2. Do not rely on **DestroyJavaVM and then creating another JVM** in the same process to reuse the runtime: it is not a guaranteed restart lifecycle for embedded applications. If isolation is needed, consider **a separate process**, not repeatedly creating/destroying a VM in a shared process.

According to the JNI Specification, on some operating systems the **primordial process thread** may have stack restrictions or special management requirements. For a production host, consider creating a **coordinator thread with an appropriate stack** to initialize and own the JVM lifecycle; the learning example in section 7 uses the native process `main` to keep the configuration easy to understand.

### 2.2. Who Manages the JVM?

There should be a clear owner, such as `JvmManager`, with states:

```text
NOT_STARTED
    |
    | JNI_CreateJavaVM succeeds
    v
RUNNING
    |
    | receive stop/shutdown request
    v
STOPPING      (do not allow spawning new Java calls)
    |
    | worker detach + native join
    | release global references
    v
READY_TO_DESTROY
    |
    | DestroyJavaVM
    v
STOPPED
```

This is an **application design model**, not state constants provided by JNI itself. The software needs to protect state transitions with mutex/atomic or an equivalent coordination mechanism so that a worker does not "just manage to attach" when the host has already started shutting down.

## 3. `JavaVM*` and `JNIEnv*`: Two Pointer Types Not to Confuse

| Component | Shared across threads? | What is it used for? | Lifecycle |
| --- | --- | --- | --- |
| `JavaVM*` | **Yes**, while the VM still exists | `GetEnv`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread`, `DestroyJavaVM` | Created by the JVM; do not use after Destroy succeeds |
| `JNIEnv*` | **No** | Look up class/method, create strings, call Java, manage local refs, check Java exceptions | Belongs to an attached thread; do not use after detach |
| `jobject`/`jclass` local ref | Do not pass arbitrarily across threads | Reference to a Java object/class within a JNI context | Expires with the local reference scope |
| `jobject`/`jclass` global ref | Can be used from attached threads while still valid | Hold Java object/class across JNI calls and across workers | Created with `NewGlobalRef`, destroyed with `DeleteGlobalRef` before the VM stops |

Incorrect example:

```cpp
// Incorrect: hostEnv belongs to the thread that initialized the VM.
std::thread worker([hostEnv]() {
    hostEnv->FindClass("java/lang/String");
});
```

This is an **error illustration**, not code to run. `JNIEnv*` belongs to the initializing thread; using it in a worker violates the JNI contract. Symptoms may be crashes, corruption, or errors that only appear when running with `-Xcheck:jni`.

Correct usage direction example (code snippet **inside a native worker** that already has a valid `JavaVM* vm`):

```cpp
JNIEnv* env = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void**>(&env), nullptr);

if (rc != JNI_OK || env == nullptr) {
    // Report error and do not call JNI if not attached.
    return;
}

// Only the current thread uses env.
// Complete Java calls before detaching.

(void)vm->DetachCurrentThread();
```

You must ensure releasing local resources/resolving pending exceptions on the actual execution path. `DetachCurrentThread` is called by **the worker itself**, not the host "detaching on its behalf".

## 4. Checking Before Attaching: `GetEnv`

A host native thread may already have been attached by another library. It is necessary to distinguish between a **borrowed attachment** and an **attachment created by your own code**.

```cpp
JNIEnv* env = nullptr;
bool attachedHere = false;

jint rc = vm->GetEnv(
        reinterpret_cast<void**>(&env), JNI_VERSION_1_6);

if (rc == JNI_EDETACHED) {
    rc = vm->AttachCurrentThread(
            reinterpret_cast<void**>(&env), nullptr);
    if (rc == JNI_OK) {
        attachedHere = true;
    }
}

if (rc != JNI_OK || env == nullptr) {
    // JNI_EVERSION or attach error: stop work.
    return;
}

// Perform JNI on this thread, complete all Java callbacks.

if (attachedHere) {
    (void)vm->DetachCurrentThread();
}
```

This is an **illustrative pattern inside the body of a C++ function returning `void`**, not a standalone example. When implementing, you should use a guard/RAII to ensure cleanup on all exit paths.

Status explanation:

- `JNI_OK`: the current thread **is already attached** and can use `env`.
- `JNI_EDETACHED`: the current thread **is not attached**; `GetEnv` **does not attach automatically**.
- `JNI_EVERSION`: the requested JNI version is not supported by the JVM.
- `AttachCurrentThread` succeeds: creates a non-daemon attachment if the thread was not attached.
- If already attached, calling attach again **does not change the state** and does not convert it from daemon to non-daemon or vice versa.

**Ownership:** if `GetEnv` initially returns `JNI_OK`, the attachment already existed. Library code that only "borrows" `JNIEnv*` **must not detach** while the original owner still needs it. Only detach if your own code attached within a clearly owned scope; a thread also cannot detach while there are still Java methods on the call stack.

## 5. Choosing Non-Daemon or Daemon for Host Threads

An unattached native thread has two options:

```cpp
// Create a non-daemon attachment for the current thread.
vm->AttachCurrentThread(
        reinterpret_cast<void**>(&env), nullptr);

// Or, on another/unattached thread:
// Create a daemon attachment for the current thread.
vm->AttachCurrentThreadAsDaemon(
        reinterpret_cast<void**>(&env), nullptr);
```

These are **two alternative calls**, not a recommendation to call both on the same thread. If the thread is already attached, calling again only returns `JNIEnv*` and **does not change the daemon status**.

| Criterion | `AttachCurrentThread` | `AttachCurrentThreadAsDaemon` |
| --- | --- | --- |
| Initial attachment | Non-daemon | Daemon |
| Allowed to call Java/JNI | Yes | Yes |
| Can make `DestroyJavaVM` wait | **Yes** — it is a non-daemon thread | A daemon itself **does not keep the JVM alive** |
| Needs to stop, release, and detach | **Yes** | **Yes** |
| Appropriate use | Workers performing transactions/tasks that must complete | Background workers that can be cancelled but still have explicit stop/cleanup |

**Do not choose daemon as a way to bypass shutdown bugs.** Daemon only changes the rule for the VM waiting on non-daemon user threads; it **does not automatically finish work, does not automatically release resources, and does not automatically clean up global references**. When the VM begins shutting down, a daemon thread may not have finished its Java callback yet, so the host application must coordinate it itself.

Conversely, a native non-daemon worker running an infinite loop can make `DestroyJavaVM` **wait indefinitely**. The host application must signal stop and wait for the worker to detach before destroying the VM.

### 5.1. `JavaVMAttachArgs` When Naming Is Needed

`AttachCurrentThread` and `AttachCurrentThreadAsDaemon` can accept `JavaVMAttachArgs`:

```cpp
char workerName[] = "host-jni-worker";
JavaVMAttachArgs attachArgs{};
attachArgs.version = JNI_VERSION_1_6;
attachArgs.name = workerName;
attachArgs.group = nullptr;

JNIEnv* env = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void**>(&env), &attachArgs);
```

This is a code snippet **running in an unattached thread**, with a valid `JavaVM* vm`.

- `name` is the Java thread name displayed during debugging, in **modified UTF-8** format; if not needed, use `nullptr`.
- `group` can be a global reference to a `ThreadGroup` or `nullptr`; do not pass a local reference from another thread.
- `version` is a JNI interface constant, **not** a Java version integer like `17`.
- Calling attach again on an already attached thread will **not** change the daemon status, and should not be treated as a mechanism to rename or change thread group.

## 6. Coordinating the Lifecycle of Multiple Native Workers

What matters is not just each attach/detach pair, but **the mechanism controlling the entire pool**.

### 6.1. Correct Startup Sequence

1. The host initializes the JVM **once** and checks `JNI_CreateJavaVM == JNI_OK`.
2. On the JVM-initializing thread, load the appropriate Java classes and methods; if they need to be passed to workers, create **global references**.
3. Open the worker pool. Each native worker attaches itself before its first JNI call, or uses `GetEnv` to know whether it is already attached.
4. Each worker processes work on its own `JNIEnv*`, resolving Java exceptions directly on the thread where they occurred; do not store `JNIEnv*` in a shared object.
5. The host only accepts new work when the JVM is in the `RUNNING` state and the owner still guarantees the VM stays alive until the work finishes.

### 6.2. Safe Shutdown Sequence

```text
Host receives shutdown request
          |
          v
Close new work intake gate / set STOPPING
          |
          v
Broadcast stop signal to worker pool
          |
          v
Running workers finish current Java calls
          |
          v
Each worker deletes necessary local refs, detaches from its own thread
          |
          v
Host joins all native threads (no callbacks running anymore)
          |
          v
Host deletes global references it owns
          |
          v
Host calls DestroyJavaVM when no workers depend on the JVM
          |
          v
JVM stops; no more new JNI calls from host
```

**Why you must lock the work source before joining:** if a producer keeps pushing work into the pool, workers may continue attaching/calling Java right when the host wants to Destroy. Shutdown synchronization must guarantee **no new attach/callback from the moment work intake is cut off**.

**Why you must join before `DestroyJavaVM`:** you want to be certain that all application-owned native workers have stopped. Even if workers attach as daemon, the host still needs to reclaim threads and memory; `DestroyJavaVM` is not a call that "joins on behalf of" the native worker pool. For non-daemon, if a worker has not stopped, Destroy may be blocked.

### 6.3. Do Not Force Detach on Behalf of Others and Do Not Close the JVM Under Workers

Some anti-patterns:

- The host keeps a list of each worker's `JNIEnv*` and calls `DetachCurrentThread` on the host: **wrong**, because the API detaches the **calling** thread, not a thread selected by pointer.
- The host closes the JVM first, and then a native worker uses `JavaVM*` or `JNIEnv*`: **wrong lifecycle**, may crash.
- A worker is created after the stop signal but before calling Destroy: causes an attach-vs-shutdown race.
- The host waits for a worker while holding a mutex that the worker needs to acquire/release in a Java callback: easily deadlocks; you must analyze lock order and not hold the shutdown lock while waiting to join if the worker needs it to exit.

### 6.4. Clear Thread Pool Ownership

For long-lived workers, the usual model is:

```text
worker thread start
    -> Attach once
    -> repeat:
         await native work
         call Java when needed
         clear local refs/resolve exceptions per job
         stop if shutdown requested
    -> Detach once
worker thread exit
```

You do not have to attach and detach on every callback; you can attach once for the **entire lifetime of the worker**, but you must ensure the worker terminates in a controlled manner. For a thread pool owned by a third-party library, determine whether thread-start/thread-stop hooks can be registered; if you do not know who owns the attachment, use `GetEnv` + an ownership flag and **do not detach a thread that was already attached beforehand**.

### 6.5. The JVM-Initializing Thread Also Has a Lifecycle

The thread that calls `JNI_CreateJavaVM` already has a `JNIEnv*` from the start; it can call Java without attaching again. According to the specification, `DestroyJavaVM` can be called from an appropriate thread; do not let multiple threads contend for destroy rights. You should designate a single **JVM owner** responsible for shutdown.

If the host uses a **dedicated JVM management thread**, send initialization/shutdown requests to it via a queue and use a barrier/future mechanism to ensure workers do not start before the VM is ready or continue after the VM stops. The stack of the initializing thread must meet environmental requirements.

## 7. Complete Example: C++17 Host Embedding the JVM and Coordinating Two Workers

This example focuses on **the entire lifecycle**. The host program (without Java `public static void main`) will:

1. Use `JNI_CreateJavaVM` to start the JVM in the same process.
2. Load the `EmbeddedService` class, look up the Java method, and create a `jclass` global reference.
3. Create **two native `std::thread`s**: one non-daemon attach, one daemon attach.
4. Both workers call `EmbeddedService.report(String)` via their own `JNIEnv*` and then detach.
5. The host `join`s both, releases the global ref, destroys the JVM, and prints deterministic output.

Note: the demo uses a thread created from C++ `main` for brevity. For production with special primordial thread/stack requirements, you should place the JVM owner on a **dedicated management thread** as recommended by the JNI Invocation API. The attach/stop/join/destroy principles below remain the same.

### 7.1. Java: `EmbeddedService.java`

```java
public final class EmbeddedService {
    private EmbeddedService() {
    }

    public static String report(String label) {
        return label + ":daemon=" + Thread.currentThread().isDaemon();
    }
}
```

Java here is **a service class**, needing no `main` because **the C++ application is the startup program**. `report` returns a string; Java itself does not print to stdout, so all output lines of the host program can be ordered deterministically.

### 7.2. C++ host: `EmbeddedHost.cpp`

```cpp
#include <jni.h>

#include <functional>
#include <iostream>
#include <string>
#include <system_error>
#include <thread>

struct JobResult {
    bool ok = false;
    std::string text;
};

// Runs on a native thread created by std::thread.
static void runWorker(JavaVM* vm,
                      jclass serviceClass,
                      jmethodID reportMethod,
                      const char* label,
                      bool daemon,
                      JobResult* out) {
    JNIEnv* env = nullptr;

    // A newly created worker must be unattached.
    jint before = vm->GetEnv(
            reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
    if (before != JNI_EDETACHED) {
        out->text = "unexpected thread attachment state";
        return;
    }

    jint attachStatus = daemon
            ? vm->AttachCurrentThreadAsDaemon(
                    reinterpret_cast<void**>(&env), nullptr)
            : vm->AttachCurrentThread(
                    reinterpret_cast<void**>(&env), nullptr);

    if (attachStatus != JNI_OK || env == nullptr) {
        out->text = "attach failed";
        return;
    }

    // From here on, only the env belonging to this worker is used.
    jstring jlabel = env->NewStringUTF(label);
    jstring reply = nullptr;

    if (jlabel != nullptr) {
        reply = static_cast<jstring>(env->CallStaticObjectMethod(
                serviceClass, reportMethod, jlabel));

        if (!env->ExceptionCheck() && reply != nullptr) {
            const char* chars = env->GetStringUTFChars(reply, nullptr);
            if (chars != nullptr) {
                out->text = chars; // Copy to host-owned std::string.
                out->ok = true;
                env->ReleaseStringUTFChars(reply, chars);
            }
        }
    }

    if (env->ExceptionCheck()) {
        // Java exceptions do not automatically propagate to the calling C++ thread.
        // The demo logs to stderr and marks failure.
        env->ExceptionDescribe();
        env->ExceptionClear();
        out->ok = false;
        out->text = "Java callback failed";
    }

    if (reply != nullptr) {
        env->DeleteLocalRef(reply);
    }
    if (jlabel != nullptr) {
        env->DeleteLocalRef(jlabel);
    }

    // Java callback has returned to C++; no active Java frames remain.
    if (vm->DetachCurrentThread() != JNI_OK) {
        out->ok = false;
        out->text = "detach failed";
    }
    // env becomes invalid after detach.
}

int main() {
    char classpath[] = "-Djava.class.path=.";
    JavaVMOption option{};
    option.optionString = classpath;

    JavaVMInitArgs args{};
    args.version = JNI_VERSION_1_6;
    args.nOptions = 1;
    args.options = &option;
    args.ignoreUnrecognized = JNI_FALSE;

    JavaVM* vm = nullptr;
    JNIEnv* ownerEnv = nullptr;

    jint created = JNI_CreateJavaVM(
            &vm, reinterpret_cast<void**>(&ownerEnv), &args);

    if (created != JNI_OK || vm == nullptr || ownerEnv == nullptr) {
        std::cerr << "JNI_CreateJavaVM failed\n";
        return 1;
    }

    // Find the Java class on the attached owner thread.
    jclass localClass = ownerEnv->FindClass("EmbeddedService");
    if (localClass == nullptr) {
        ownerEnv->ExceptionDescribe();
        ownerEnv->ExceptionClear();
        vm->DestroyJavaVM();
        return 1;
    }

    // Global ref is safely usable across attached workers.
    jclass serviceClass = static_cast<jclass>(
            ownerEnv->NewGlobalRef(localClass));
    ownerEnv->DeleteLocalRef(localClass);

    if (serviceClass == nullptr) {
        if (ownerEnv->ExceptionCheck()) {
            ownerEnv->ExceptionDescribe();
            ownerEnv->ExceptionClear();
        }
        vm->DestroyJavaVM();
        return 1;
    }

    jmethodID reportMethod = ownerEnv->GetStaticMethodID(
            serviceClass,
            "report",
            "(Ljava/lang/String;)Ljava/lang/String;");

    if (reportMethod == nullptr) {
        if (ownerEnv->ExceptionCheck()) {
            ownerEnv->ExceptionDescribe();
            ownerEnv->ExceptionClear();
        }
        ownerEnv->DeleteGlobalRef(serviceClass);
        vm->DestroyJavaVM();
        return 1;
    }

    JobResult jobs[2];
    std::thread threads[2];

    // Create native workers. If a thread constructor fails,
    // still join already-created workers before destroying the VM.
    try {
        threads[0] = std::thread(
                runWorker, vm, serviceClass, reportMethod,
                "job-A", false, &jobs[0]);
        threads[1] = std::thread(
                runWorker, vm, serviceClass, reportMethod,
                "job-B", true, &jobs[1]);
    } catch (const std::system_error& ex) {
        for (auto& thread : threads) {
            if (thread.joinable()) {
                thread.join();
            }
        }
        ownerEnv->DeleteGlobalRef(serviceClass);
        vm->DestroyJavaVM();
        std::cerr << "Cannot start workers: " << ex.what() << '\n';
        return 1;
    }

    // Join waits for native threads; independent of daemon status.
    for (auto& thread : threads) {
        thread.join();
    }

    // Read results only after join; no concurrent writes remain.
    bool allOk = jobs[0].ok && jobs[1].ok;

    if (allOk) {
        std::cout << jobs[0].text << '\n';
        std::cout << jobs[1].text << '\n';
    } else {
        std::cerr << "One or more workers failed\n";
    }

    // No worker uses the class/method or JavaVM anymore.
    ownerEnv->DeleteGlobalRef(serviceClass);

    jint destroyed = vm->DestroyJavaVM();
    if (destroyed != JNI_OK) {
        std::cerr << "DestroyJavaVM failed\n";
        return 1;
    }

    if (!allOk) {
        return 1;
    }
    std::cout << "shutdown=ok\n";
    return 0;
}
```

**Design keys in the example:**

- `JNI_CreateJavaVM` returns `ownerEnv` to native `main`; it is **not** passed to `runWorker`.
- `runWorker` receives the shared `JavaVM* vm` and calls `GetEnv` to verify the thread is unattached; next, it attaches itself according to the `daemon` flag.
- `serviceClass` is a **global reference** created before workers run; the local `jclass` from `FindClass` is deleted early, never carrying a local ref across threads.
- `reportMethod` is a `jmethodID` looked up from the corresponding class and used while `serviceClass` is kept alive. It is not a `JNIEnv*`, so there is no "one method ID per thread" rule.
- Each worker creates and deletes **its own local references** (`jlabel`, `reply`), releases the `GetStringUTFChars` string with the matching `ReleaseStringUTFChars` function, and checks for Java exceptions.
- The worker detaches itself after the Java method has returned. `ownerEnv` **does not** call detach on its behalf.
- `std::thread::join` brings both workers to a stopped state before deleting `serviceClass`; only then is the JVM destroyed.
- Native results are placed into two separate `JobResult`s; the host only prints after `join`, so displaying output does not depend on scheduler ordering.

This is a **small example for learning the lifecycle**. It does not implement VM retry/restart systems, continuous work-intake pools, or systems that pass full Java throwables across threads; production code should add resource-management wrappers and a stop strategy when the process is interrupted/killed.

### 7.3. Compiling Java

Place `EmbeddedService.java` and `EmbeddedHost.cpp` in the same directory, and run with JDK 17+:

```bash
javac -encoding UTF-8 EmbeddedService.java
```

The command creates `EmbeddedService.class`. `javac -h` is not needed here because **Java does not declare any `native` methods**: the call direction is C++ host **→ Java static method** via the JNI Invocation API. Conversely, if Java declares `native` and you want JNI symbols in a C/C++ library, then `javac -h` is needed.

### 7.4. Linux — g++/HotSpot JDK

Assuming `JAVA_HOME` points to a JDK 17+ directory containing `include` and `lib/server/libjvm.so`:

```bash
javac -encoding UTF-8 EmbeddedService.java

g++ -std=c++17 -O2 -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  EmbeddedHost.cpp \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embedded-host

./embedded-host
```

`-I` helps the compiler find `jni.h` and Linux-specific headers; `-L` specifies the directory containing the JVM library; `-ljvm` links the JVM Invocation API. `-Wl,-rpath,...` embeds a runtime search path for `libjvm.so`. You may choose another dynamic loader management approach depending on packaging, but you must ensure the OS finds the exact `libjvm.so` from the same JDK.

### 7.5. macOS — clang++/JDK

Assuming the JDK has `lib/server/libjvm.dylib`:

```bash
javac -encoding UTF-8 EmbeddedService.java

clang++ -std=c++17 -O2 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  EmbeddedHost.cpp \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embedded-host

./embedded-host
```

On macOS, the JDK location can be determined with `/usr/libexec/java_home` if a suitable JDK is installed. Do not try to use a JVM library from a JDK with a different architecture than the compiler/host.

### 7.6. Windows — MSVC

Open **x64 Native Tools Command Prompt** or Developer Command Prompt matching the JDK architecture, point `JAVA_HOME` to the JDK, and run in the directory containing both source files:

```bat
javac -encoding UTF-8 EmbeddedService.java

cl /nologo /std:c++17 /EHsc ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  EmbeddedHost.cpp ^
  /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embedded-host.exe

set "PATH=%JAVA_HOME%\bin\server;%PATH%"
embedded-host.exe
```

`jvm.lib` is the **import library** used at link time; at runtime Windows needs to find the corresponding `jvm.dll` (with the common JDK layout at `%JAVA_HOME%\bin\server`). The `set PATH` command applies to **cmd.exe**; PowerShell has a different environment variable syntax. The 64-bit/32-bit architecture of the host, JDK, and JVM native library must match.

### 7.7. Exact Stdout on Success

```text
job-A:daemon=false
job-B:daemon=true
shutdown=ok
```

Explanation:

- `job-A` is attached via `AttachCurrentThread`, so `Thread.currentThread().isDaemon()` in Java returns `false`.
- `job-B` is attached via `AttachCurrentThreadAsDaemon`, so Java returns `true`.
- Both workers run in parallel, but **the host only prints after joining both** and prints in index order, so the standard output on the success path is fixed.
- The `shutdown=ok` line is printed only after `DestroyJavaVM` returns `JNI_OK`.

The example command does not depend on JNI symbols of the form `Java_package_Class_method` because there is no Java→native declaration. If running the command reports class not found, check the **working directory** because `-Djava.class.path=.` is configured in the host. If linking the JVM fails, check `JAVA_HOME`, the dynamic loader, the ABI, and the correct `jvm` library of the JDK.

## 8. Class Loader and References When Host Threads Call Java

### 8.1. `FindClass` on a Native-Created Worker Is Often Harder Than Expected

A thread attached from the native side **has no Java caller on the call stack**. According to the JNI Invocation API, the context class loader upon attaching defaults to the **bootstrap class loader**. Calling:

```cpp
// Illustration on an attached worker.
jclass type = env->FindClass("com/example/Plugin");
```

may fail if the `Plugin` class was loaded by an application/custom class loader and cannot be found by the lookup rules at that point. Do not assume that merely calling `AttachCurrentThread` gives a worker the same classpath/loader context as any other Java thread.

A stable design approach is to **resolve the class while in a known context**, hold the `jclass` with a global ref, and pass it to the worker. That is why `EmbeddedHost.cpp` calls `FindClass("EmbeddedService")` **on the JVM owner thread**, creates a `NewGlobalRef`, and only then creates the workers.

If the application has multiple plugin class loaders or hot-reloads Java modules, you must manage the lifecycle of the corresponding classes and loaders. A global ref keeps the class/loader alive; if not released, class loader unloading will be affected.

### 8.2. Distinguishing Local / Global / Weak Global

- **Local ref**: usually belongs to a JNI call/thread context; do not transfer to another native thread for use after the context ends.
- **Global ref**: created with `NewGlobalRef`, usable on attached threads while alive; it is a strong reference, so it can keep objects/classes alive unintentionally.
- **Weak global ref**: used when a weak reference is needed, but it can be collected by GC, so you must check/acquire a strong local reference properly before using it.

Do not turn every Java object in the project into global refs; only keep objects that are truly needed for callbacks longer than a JNI call scope and always establish a clear **ref-cleanup owner**.

### 8.3. Do Not Cache `JNIEnv*` in a Singleton

A common architectural mistake is a `JniBridge` singleton having a `JNIEnv* env` field. When multiple workers call in, the singleton returns the same env for different threads. **Wrong**. A singleton manager can hold **`JavaVM* vm`**, while workers use `GetEnv` or attach to get their own `JNIEnv*`.

A useful API pattern:

```cpp
// Design signature only, not a standalone C++ program.
class JvmManager {
public:
    JavaVM* vm() const;
    bool isStopping() const;
    // JNI context must be obtained per current thread.
};
```

The `isStopping()` state must be properly synchronized if multiple threads call it, and `vm()` may only be used while the owner still guarantees the JVM is alive (for example, via a lease/reference-counted lifecycle token with a clear contract).

## 9. Java Errors, Attach Errors, and Handling Across Thread Boundaries

### 9.1. Java Exceptions Do Not Automatically Appear on the Owner Thread

If a native worker calls:

```cpp
env->CallStaticVoidMethod(serviceClass, method);
```

and Java throws an exception, **the pending exception belongs to the worker's `JNIEnv*`**. It **does not automatically become an exception in the C++ host thread** or get thrown into another Java thread. The worker must detect it with `ExceptionCheck`, report/log the error, handle or forward the throwable through an intentional mechanism, and then release local resources and detach when valid.

In the demo, `ExceptionDescribe` prints the stack trace to stderr; `ExceptionClear` is called intentionally to proceed with cleanup. Production applications may use a message queue, a result object, or a failure callback back to Java through a defined path. **Do not silently clear an exception and report the work as successful**.

### 9.2. Attach Failure

`AttachCurrentThread`/`AttachCurrentThreadAsDaemon` returns codes such as `JNI_OK` or a negative error. If unsuccessful or `env == nullptr`, you must not call JNI through env. The worker returns an error status to the host. The host still has to decide whether to retry, cancel the job, or shut down, and must not call detach if the worker itself did not attach successfully.

### 9.3. Detach Only After Java Callbacks Have Finished

A thread cannot call `DetachCurrentThread` while there are still Java methods on its own call stack. Therefore, the valid sequence is:

```text
native worker
  -> attach
  -> CallStaticObjectMethod
      -> Java report(...)
      <- report returns
  -> release string/local references
  -> detach
  -> return from std::thread
```

If Java code calls back into native and native tries to detach right inside that nested call, there is still an active Java frame running, so it is invalid.

### 9.4. Thread Stack and Deep JNI Callbacks

A native worker has a stack size determined by the **operating system/native threading API**. If a Java callback goes deep or uses recursion, a stack that is too small can cause a `StackOverflowError` or a system error. For embedded applications, you must choose an appropriate stack size, measure with real workloads, and control recursion. This is also one reason the JNI Specification recommends considering avoiding the primordial thread for initializing the VM on some OSes.

## 10. Shutdown, Deadlocks, and Contention Issues

### 10.1. `DestroyJavaVM` Is Not a Tool to Terminate All Native Threads

According to the JNI Invocation API, the JVM must wait on conditions related to **non-daemon user threads** before completing destroy. These threads include both **Java threads** and **non-daemon attached native threads**.

**Consequence:** if a non-daemon worker is still running and has not detached, the destroy call may **hang waiting**. Conversely, a daemon worker does not force the VM to wait, but may still have uncleaned native resources. Therefore, the host should **stop accepting work, signal stop, wait for workers to detach/join, and then destroy** for both thread types.

Do not use JVM shutdown to replace shutting down native subsystems. For hosts that have Java threads created inside Java, those non-daemon Java threads must also have a stop mechanism; joining native workers alone is not necessarily enough if Java workers are still alive.

### 10.2. Race: Worker Attaches Right When Host Destroys

If you only use a plain unsynchronized bool variable, the host might see "no workers" while a native thread has just been created but has not yet attached. The host calls `DestroyJavaVM`, and the worker subsequently tries to attach to a stopping JVM.

**Design solution:**

- Have a `RUNNING/STOPPING` state protected by a mutex or atomic with proper memory ordering.
- Each job/worker acquires a **permission to use the JVM** (lifecycle lease) while the owner is still `RUNNING`; do not issue new leases after `STOPPING`.
- The owner waits for all active leases to finish and all native workers to join before `DestroyJavaVM`.
- Once `STOPPING`, new callbacks are not allowed to start, except final cleanup callbacks already managed by the owner with the VM guaranteed alive.

The demo creates workers right after the VM is ready and then explicitly `join`s, so it does not have to solve complex queues/leases; production needs this mechanism if the pool continuously accepts work.

### 10.3. Deadlock From Waiting With the Wrong Lock

Suppose the host holds a `shutdownLock` mutex when calling `join`, while a worker needs that lock to update "stopped". The worker waits for the lock, the host waits for the worker: **deadlock**.

Practical rule: broadcast the stop signal while holding the lock if needed, **release the lock before `join`**, and only reacquire the lock afterward to update the overall state. Similarly, avoid holding native locks for a long time when a Java callback might call back into native and contend for the same lock.

### 10.4. The "Destroy Then Re-Init" Mistake

Some applications assume they can call `JNI_CreateJavaVM`/`DestroyJavaVM` per session and initialize a new VM. The JNI Invocation API is not designed for multiple independent JVMs in a single process. If a product needs to restart the Java runtime frequently, look at a model where **the host spawns a Java subprocess** or a separate Java service, where process lifetime is the true isolation and restart boundary.

### 10.5. Using `std::thread::detach()` Is Completely Different From JNI `DetachCurrentThread`

The two names look similar, but their functions are different:

| API | Meaning |
| --- | --- |
| `std::thread::detach()` | **Relinquishes join ownership** of the C++ thread object; the OS thread continues running independently |
| `JavaVM::DetachCurrentThread()` | **Detaches the current thread's JNI attachment from the JVM** |

A worker can have its C++ thread object `detach()`ed yet **still be attached to the JVM**; or be JNI-detached while the C++ thread is still joinable. Avoid using `std::thread::detach()` for workers whose shutdown the host needs to manage, unless you have another strict lifecycle mechanism.

## 11. Common Mistakes

| Mistake | Cause | Fix |
| --- | --- | --- |
| Using the `JNIEnv*` received by the host from `JNI_CreateJavaVM` in a worker | `JNIEnv*` is only for the current thread | Worker calls `AttachCurrentThread` or `GetEnv` to obtain its own env |
| Calling `GetEnv` without handling `JNI_EDETACHED` | `GetEnv` does not attach | Attach the appropriate thread, check `JNI_OK` |
| Using `AttachCurrentThreadAsDaemon` to change the state of an already attached thread | Calling attach again does not change daemon status | Choose daemon/non-daemon before the first attachment |
| Passing a `jclass` local ref from host to worker | Local JNI references do not have a valid cross-thread lifetime | Create `NewGlobalRef`, clean up with `DeleteGlobalRef` after join |
| Worker calls `FindClass` and cannot find an application class | No Java caller, different loader context | Resolve the class in the right context and pass a global ref |
| Forgetting `ReleaseStringUTFChars` or `DeleteLocalRef` | Native/JNI resource leak | Guaranteed per-job/per-thread cleanup |
| Worker encounters a Java error without checking pending exceptions | False success result, invalid JNI state | `ExceptionCheck`, log/propagate error and clean up |
| Worker does not call `DetachCurrentThread` before exiting | Thread attachment is not cleaned up properly | Use a worker cleanup guard |
| Host calls detach on behalf of a worker | JNI detach always applies to the current thread | Have the worker detach itself before terminating |
| Host calls `DestroyJavaVM` before join | Worker might use the JVM after shutdown | Stop, detach, join, destroy JVM in order |
| Infinite non-daemon worker does not stop | Destroy may wait forever | Have a stop signal and appropriate shutdown deadline |
| Simply changing a worker to daemon to avoid hanging | Daemon may be abandoned mid-work when the VM stops | Still need stop/join/resource cleanup |
| Not locking the work-creation gate at shutdown | Race of worker attaching during Destroy | Atomic RUNNING→STOPPING, wait for active jobs |
| Using `std::thread::detach` instead of `DetachCurrentThread` | Two unrelated APIs | Manage both C++ thread lifecycle and JNI attachment |
| Running `embedded-host` cannot find JVM library | Missing runtime loader path/link library | Check `JAVA_HOME`, `libjvm`/`jvm.dll`, and ABI |
| `FindClass("EmbeddedService")` fails | Wrong classpath/current working directory | `-Djava.class.path=.` and build class in the right directory |

## 12. Extension Exercises to Understand Coordination

### Exercise 1 — Add a Third Worker

Create a `job-C` worker that attaches non-daemon and calls Java like the first two workers. Add a separate slot in the `JobResult` array, create the thread, and `join` all of them. Observe that stdout is only printed after all three workers finish. **Do not** let all three threads write to the same `std::string` unsynchronized.

### Exercise 2 — Simulate a Long-Running Worker

Have a native worker sleep for a short duration before the Java callback, then join. Observe that the host still does not call `DestroyJavaVM` before the worker returns and detaches. Do not add sleep to "solve a race"; sleep is only for observation, while the guarantee comes from join and shutdown ordering.

### Exercise 3 — Long-Lived Native Worker Pool

Replace each "one job then exit" worker with a loop pulling jobs from a queue. Design the STOPPING state to reject new jobs, wake waiting workers, finish running jobs or cancel per policy, and then detach each worker. Use a condition variable for the stop signal, avoiding infinite polling.

### Exercise 4 — Java Callback Throws an Exception

Modify Java `report` to conditionally throw `IllegalStateException`. Verify that the native worker calls `ExceptionCheck`, does not report `ok=true`, and still detaches. The host must receive a clear error status, not let the exception silently disappear in the worker.

### Exercise 5 — Verify JNI Thread Rules

Try running with `-Xcheck:jni` as an additional option for `JNI_CreateJavaVM` if the JVM supports it. Verify that the program **does not** use an env from another thread, does not use expired local refs, and does not skip releases. The purpose of the exercise is to use an error-checking tool, not to replace ownership and lifecycle analysis.

## 13. Pre-Implementation Design Checklist

1. Who is the **JVM owner**? Who is allowed to call `JNI_CreateJavaVM` and `DestroyJavaVM`?
2. Is **one JVM living one clear cycle** guaranteed, without creating multiple JVMs or assuming restarts in one process?
3. Which workers are created by native? Does each worker have its own `JNIEnv*` after `AttachCurrentThread`/`AttachCurrentThreadAsDaemon`?
4. Are `GetEnv` and attachment ownership checked to avoid accidentally detaching a third-party thread?
5. Do Java classes/objects passed across threads use **global refs** properly, with the appropriate class loader?
6. Are null checks, JNI error codes, pending Java exceptions, and cleanup of every obtained local ref/string handled?
7. Does the worker detach **in its own thread**, after the Java callback finishes?
8. Does the host close the work-intake gate before stopping, synchronize active jobs, and wait for all native threads to `join`?
9. Are all global refs deleted after workers stop using them and **before** destroying the JVM?
10. Are Java-created non-daemon threads, GC, stack size, class loaders, and native ABI/loader paths considered?
11. Are failure paths and shutdown measured in integration tests, not just the happy path?
12. Is using `JavaVM*`/`JNIEnv*` after the VM has been destroyed avoided?

## Official Documentation

- [Oracle Java 17 — JNI Specification: Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `JNI_CreateJavaVM`, `GetEnv`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread`, `DestroyJavaVM`, and warnings regarding the primordial thread.
- [Oracle Java 17 — JNI Specification: JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `FindClass`, `GetStaticMethodID`, `CallStaticObjectMethod`, `NewGlobalRef`, `DeleteGlobalRef`, managing local refs, strings, and Java exceptions.
- [Oracle Java 17 — JNI Specification: JNI Types](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `JNIEnv`, `JavaVM`, `jclass`, `jobject`, and other data types.
- [Oracle Java 17 — Thread.isDaemon](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#isDaemon()): confirming daemon status via a Java callback.
- [Oracle Java 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): creating class files for the embedded JVM.
# Getting JavaVM with GetJavaVM and Checking Thread Status with GetEnv

## 1. The Problem: From a Native Method, Wanting to Know Whether the Current Thread Is Attached to the JVM

In **JNI (Java Native Interface)**, a C function called by Java receives `JNIEnv *env`. This pointer allows the **calling** thread to perform JNI operations, but **it is not a JVM access ticket shared across threads**. When a C library spawns its own thread using `pthread_create` or `CreateThread`, that thread does not naturally have a valid `JNIEnv *`. To call Java or manipulate Java objects on that thread, native code must know which **JavaVM** to work with and the attach status of **the current thread itself**.

Two APIs answer two different questions:

- **`GetJavaVM`**: from a valid `JNIEnv *` of a running native method, obtains the `JavaVM *` representing the associated JVM. `JavaVM *` is used for the **Invocation API** (including `GetEnv`, `AttachCurrentThread`, and `DetachCurrentThread`).
- **`GetEnv`**: asks `JavaVM *` whether **the thread calling `GetEnv` right now** is attached to the JVM and can obtain a `JNIEnv *` for the requested JNI version. This function **does not attach automatically**.

This lesson focuses on **getting `JavaVM` with `GetJavaVM` and checking thread status with `GetEnv`**, and placing the result into the proper native/Java control flow. The complete example includes Java 17+, C11, and run instructions for Linux, macOS, and Windows. Complex GC steps or callbacks are omitted so they do not distract from the main topic.

After this lesson, you will be able to:

1. Distinguish the lifetime and usage scope of `JavaVM *` from `JNIEnv *`.
2. Call `(*env)->GetJavaVM(env, &vm)` in C and explain why `&vm` has type `JavaVM **`.
3. Call `(*vm)->GetEnv(vm, (void **)&thread_env, JNI_VERSION_1_6)` and correctly interpret `JNI_OK`, `JNI_EDETACHED`, and `JNI_EVERSION`.
4. Determine when to simply use the existing `JNIEnv *`, and when a native-created thread must call `AttachCurrentThread` and then `DetachCurrentThread`.
5. Write deterministic tests on Java threads and on OS native threads; know where JNI cannot yet be called.
6. Avoid storing/sharing `JNIEnv *` across the wrong thread, mistakenly detaching a Java-owned thread, using a pointer after detach, or guessing status from `NULL`.

## 2. The Right Model: Shared JVM, Thread-Bound JNI Environment

~~~text
                      One Java Virtual Machine
                           JavaVM *vm
                                |
                     Invocation API function table
                     /          |           \
           GetEnv(vm,...)  AttachCurrentThread  DetachCurrentThread
                      for the current CALLING THREAD

   Java main thread           Java-created Thread          C-created OS thread
   JVM attached               JVM attached                 NOT attached
        |                           |                           |
   JNIEnv *envA              JNIEnv *envB             GetEnv => JNI_EDETACHED
        |                           |                           |
   GetEnv => JNI_OK          GetEnv => JNI_OK          AttachCurrentThread
                                                             |
                                                        JNIEnv *envC
                                                             |
                                                        GetEnv => JNI_OK
                                                             |
                                                        DetachCurrentThread
                                                             |
                                                   GetEnv => JNI_EDETACHED
~~~

`JavaVM *` is the interface to the JVM and can be passed to native threads so they can query/attach **themselves**. `JNIEnv *` is a JNI interface valid **only in the thread that received it**; do not copy `envA` to thread B or thread C and call `(*envA)->...` there. Some JVMs may return pointer values that look identical in certain situations; **do not infer cross-thread usability from comparing pointer bit values**.

When the JVM calls a native method, that thread is already attached; the input parameter `JNIEnv *env` is valid for the current call. Conversely, a thread created directly via an OS API is not attached and needs to use `JavaVM *` to query its status and attach before touching Java objects.

**Key point:** `GetJavaVM` answers “Which JVM?”, while `GetEnv` answers “Does the running thread already have a compatible JNI environment?”. A `JavaVM *` does not allocate a `JNIEnv *` for another thread simply by sharing the pointer.

## 3. Reading the `GetJavaVM` Prototype Correctly

The JNI specification defines:

~~~c
/* Interface signature, not a user-implemented function. */
jint GetJavaVM(JNIEnv *env, JavaVM **vm);
~~~

In a C file, when already inside a JNI method:

~~~c
/* C snippet inside a JNI method that has a valid JNIEnv *env. */
JavaVM *vm = NULL;
jint result = (*env)->GetJavaVM(env, &vm);

if (result != JNI_OK || vm == NULL) {
    /* Do not use vm. Return an error according to the native method contract. */
    return;
}
/* vm is now the JVM interface associated with the calling thread. */
~~~

Explanation of the pointer levels:
- `env` has type `JNIEnv *` passed by the JVM into the JNI function; the notation `(*env)->...` is how calls through the JNI function table are made **in C**.
- `vm` is a **variable** storing a `JavaVM *` value.
- `&vm` is the address of that variable, of type `JavaVM **`, so that `GetJavaVM` **writes the result** into it.
- The return value has type `jint`. `JNI_OK` equals `0`. Negative values indicate errors, so both the return code and the output pointer must be checked before use.
- `GetJavaVM` is only valid when a thread-appropriate `JNIEnv *` already exists. **You cannot call `GetJavaVM` from a detached thread using a non-existent `JNIEnv *`**, nor may you use another thread's `env` to “fetch it on behalf of” a detached thread.

The C++ JNI syntax looks like `env->GetJavaVM(&vm)` because the `JNIEnv` wrapper type in C++ supports a method-style API. **This lesson uses C code**, so keep the `(*env)->...` and `(*vm)->...` syntax consistent.

A JNI implementation can receive `JavaVM *` in `JNI_OnLoad(JavaVM *, void *)`. That is another path provided by the JVM, but when you are **inside a native method with `JNIEnv *`**, `GetJavaVM` is the direct approach aligned with this lesson's goal. Do not create another JVM yourself just to use `GetEnv` in a library already loaded by a JVM.

## 4. Reading the `GetEnv` Prototype Correctly and Three Statuses to Remember

`GetEnv` resides on the Invocation API function table:

~~~c
/* Specification signature, not a user-implemented function. */
jint GetEnv(JavaVM *vm, void **env, jint version);
~~~

In C:

~~~c
/* vm has been validly obtained from GetJavaVM. */
JNIEnv *thread_env = NULL;
jint status = (*vm)->GetEnv(
        vm, (void **)&thread_env, JNI_VERSION_1_6);
~~~

`(void **)&thread_env` passes **the address of the pointer storage slot** to `GetEnv`. Do not pass `(void **)thread_env` because at that moment it is the pointer's value (currently `NULL`); the function needs a location to write the output. The `version` parameter is the desired **JNI interface** version, not the Java language version or bytecode target. `JNI_VERSION_1_6` is supported by JDK 17+ and is sufficient for this lesson.

| Return code | JNI constant value | Meaning of `GetEnv` | `thread_env` after the call |
|---|---|---|---|
| `JNI_OK` | `0` | Current thread **is attached** and the requested JNI version is supported | Valid `JNIEnv *` for this thread itself |
| `JNI_EDETACHED` | `-2` | Current thread **is not attached** to that JVM | Set to `NULL` |
| `JNI_EVERSION` | `-3` | The requested JNI version is not supported by the JVM | Set to `NULL` |

If another error status is returned depending on the platform/API contract, treat it as an error; **do not assume every negative code means the thread is detached**. Do not use `thread_env` if the result is not `JNI_OK`. `GetEnv` only checks and retrieves the interface when already attached; **it does not attach automatically**, does not change thread state, and does not switch `JavaVM *` to another JVM.

### Proper Handling Order by Status

~~~c
/* Illustrative fragment used in a function of a native-created thread.
   vm is a valid JavaVM *, provided by the caller. */
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);

if (rc == JNI_OK) {
    /* Thread is already attached. Use env, but DO NOT detach it yourself if you do not own the attach. */
} else if (rc == JNI_EDETACHED) {
    /* Only this branch can call AttachCurrentThread if JNI is needed. */
} else if (rc == JNI_EVERSION) {
    /* Fix the requested JNI version; do not attempt to dereference env. */
} else {
    /* Other error that must be reported and handled. */
}
~~~

Distinguish **status** from **attach ownership**. `JNI_OK` says the thread is currently attached; it does not mean this piece of code has the right to detach the thread. A Java-created thread is managed by the JVM; a native library should not call `DetachCurrentThread` on that Java thread. A native-created thread that the library successfully attached must be detached by the native worker's own lifecycle.

### Important Counterexample: `GetEnv` Does Not Turn an Unknown Pointer into a Valid One

~~~c
/* WRONG — example only to recognize an anti-pattern, do not run. */
JNIEnv *env = NULL;
(*env)->GetJavaVM(env, &vm);
~~~

Without a valid `JNIEnv *`, it cannot be dereferenced. A native-created thread can only start with a **`JavaVM *` validly provided by the JVM through another path**; then call `GetEnv` and, if needed, `AttachCurrentThread`. Recognizing and handling each stage avoids crashes even before checking the status.

## 5. When to Attach/Detach: Ownership Rules and State Machine

| Running thread | Expected `GetEnv(JNI_VERSION_1_6)` | Who attaches? | Who detaches? |
|---|---|---|---|
| Java `main` calling JNI | `JNI_OK` | JVM | JVM manages lifecycle; **do not detach in the JNI method** |
| `new Thread(...).start()` calling JNI | `JNI_OK` | JVM | JVM manages; **do not detach in the JNI method** |
| Newly created C thread before JNI interaction | `JNI_EDETACHED` | Native code calls `AttachCurrentThread` if needed | Native code that attached must call `DetachCurrentThread` before the thread exits |
| Native thread already attached earlier | `JNI_OK` | Somewhere else attached it | Do not detach “on its behalf” if not responsible for ownership |
| Unsupported JNI version requested | `JNI_EVERSION` | Do not infer that the thread is detached | Choose the right interface version and handle the error |

A proper native worker has this lifecycle:

~~~text
Native OS thread begins
    |
    v
GetEnv(vm, &env, JNI_VERSION_1_6)
    |
    +-- JNI_OK ---------> use existing env; do not claim attach ownership
    |
    +-- JNI_EVERSION ---> stop/adjust version, do not use env
    |
    +-- JNI_EDETACHED --> AttachCurrentThread(vm, &env, NULL)
                              |
                        attach failure --> return error, do not use env
                              |
                          JNI_OK
                              |
                       valid JNI operations
                              |
                       cleanup references
                              |
                       DetachCurrentThread(vm)
                              |
                          worker exits
~~~

`AttachCurrentThread` can return the existing `JNIEnv *` if the thread is already attached; calling it again **does not grant detach permission** to a caller that did not own the thread's lifecycle. On a Java thread, you should only use the `JNIEnv *` passed by the JVM into the native method. In a native worker, keep a flag such as `attached_by_us` and only detach when this code path actually performed a successful attach.

`AttachCurrentThreadAsDaemon` is an option to attach a native thread as a Java daemon if that fits the lifecycle. `AttachCurrentThread` normally creates a non-daemon attached thread; failing to detach a long-lived native worker can prevent normal JVM shutdown. Do not work around this by arbitrarily detaching a Java thread that the library did not create.

An attached native thread can run JNI APIs and call Java, but it must:
- Only use `JNIEnv *` on **the attached thread**, never passing the env pointer to another thread.
- Return Java object refs following local/global rules, cleaning up local refs on a native-attached thread in long loops (since there is no outer Java native frame that auto-cleans them like in a Java-triggered call).
- Handle pending Java exceptions per contract, never silently continuing JNI calls that are disallowed in a pending-exception state.
- Never detach while Java frames are still on the stack, monitors/resources still need releasing, or callbacks are still running.

## 6. Complete Java 17+ + C11 Program: Observing Both Java Threads and a Native Thread

This example has three native methods:
1. `callingThreadStatus()` obtains `JavaVM` using `GetJavaVM` and calls `GetEnv` on the Java main thread or a Java-created worker thread.
2. `unsupportedVersionStatus()` calls `GetEnv` with an intentionally invalid version to receive `JNI_EVERSION`.
3. `nativeWorkerRoundTrip()` obtains `JavaVM` via `GetJavaVM`, creates **a new OS thread**, checks `JNI_EDETACHED` before attach, `JNI_OK` after attach, and `JNI_EDETACHED` again after detach.

The example uses **a single synchronous run**: Java waits for the native worker to finish before using the result. Only `JavaVM *` is passed to the worker; the Java caller's `JNIEnv *` is **not** passed to that thread.

### 6.1. Project Tree and Java Source

~~~text
jni-vm-probe/
├─ src/demo/jni/VmProbe.java
├─ native/demo_jni_VmProbe.h      # Generated by javac -h
├─ native/vm_probe.c
├─ out/demo/jni/VmProbe.class     # Generated by javac
└─ libvmprobe.so                 # Linux;
                                # macOS: libvmprobe.dylib
                                # Windows: vmprobe.dll
~~~

Create `src/demo/jni/VmProbe.java`:

~~~java
package demo.jni;

import java.util.concurrent.FutureTask;

public final class VmProbe {
    static {
        System.loadLibrary("vmprobe");
    }

    private VmProbe() {}

    private static native int callingThreadStatus();
    private static native int unsupportedVersionStatus();
    private static native int nativeWorkerRoundTrip();

    public static void main(String[] args) throws Exception {
        int mainStatus = callingThreadStatus();

        FutureTask<Integer> result =
                new FutureTask<>(VmProbe::callingThreadStatus);
        Thread worker = new Thread(result, "java-created-worker");
        worker.start();
        int javaWorkerStatus = result.get();

        int unsupportedStatus = unsupportedVersionStatus();
        int nativeWorkerResult = nativeWorkerRoundTrip();

        if (mainStatus != 0 || javaWorkerStatus != 0
                || unsupportedStatus != -3 || nativeWorkerResult != 1) {
            throw new AssertionError(
                    "JNI status mismatch: " + mainStatus + ", "
                    + javaWorkerStatus + ", " + unsupportedStatus
                    + ", " + nativeWorkerResult);
        }

        System.out.println("javaMain=JNI_OK");
        System.out.println("javaWorker=JNI_OK");
        System.out.println("unsupportedVersion=JNI_EVERSION");
        System.out.println(
                "nativeWorker=JNI_EDETACHED -> JNI_OK -> JNI_EDETACHED");
        System.out.println("RESULT: PASS");
    }
}
~~~

`FutureTask.get()` waits for the Java-created worker and converts any exception in the worker into an `ExecutionException`, avoiding a case where the secondary thread fails yet the test still passes. A JVM-created `Thread` is already attached when entering a native method, so `callingThreadStatus()` is expected to return `JNI_OK` on both main and the Java worker. The lesson intentionally does not compare the bit values of `JNIEnv *` between two Java threads: doing so is not a valid way to verify thread ownership.

### 6.2. Generating the Header from Real Signatures

From the `jni-vm-probe` root:

~~~sh
mkdir -p src/demo/jni native out
javac --release 17 -h native -d out src/demo/jni/VmProbe.java
javap -s -p -classpath out demo.jni.VmProbe
~~~

On Windows CMD you can use `mkdir src\demo\jni`, `mkdir native`, `mkdir out` and then run `javac --release 17 -h native -d out src\demo\jni\VmProbe.java`; the `javap` command is the same. `-h native` generates the header file `native/demo_jni_VmProbe.h`; do not hand-type JNI function names.

All three native methods take no Java arguments and return `int`, so the bytecode descriptor for each method is **`()I`**. Because they are `static native`, the C side receives `JNIEnv *` and `jclass` as the first two parameters. The JNI-specified symbol names have the form:

~~~c
/* Key prototypes in the generated header: */
JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_callingThreadStatus
  (JNIEnv *, jclass);

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_unsupportedVersionStatus
  (JNIEnv *, jclass);

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_nativeWorkerRoundTrip
  (JNIEnv *, jclass);
~~~

### 6.3. Complete C Source

Create `native/vm_probe.c`:

~~~c
#include "demo_jni_VmProbe.h"

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#endif

typedef struct {
    JavaVM *vm;
    jint result;
} WorkerArgs;

static jint get_vm(JNIEnv *env, JavaVM **out_vm) {
    *out_vm = NULL;
    jint status = (*env)->GetJavaVM(env, out_vm);
    if (status != JNI_OK || *out_vm == NULL) {
        return JNI_ERR;
    }
    return JNI_OK;
}

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_callingThreadStatus(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    JavaVM *vm = NULL;
    if (get_vm(env, &vm) != JNI_OK) {
        return JNI_ERR;
    }

    JNIEnv *thread_env = NULL;
    jint status = (*vm)->GetEnv(
            vm, (void **)&thread_env, JNI_VERSION_1_6);

    if (status == JNI_OK && thread_env == NULL) {
        return JNI_ERR;
    }
    return status;
}

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_unsupportedVersionStatus(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    JavaVM *vm = NULL;
    if (get_vm(env, &vm) != JNI_OK) {
        return JNI_ERR;
    }

    JNIEnv *unused_env = NULL;
    /* Version is not among the defined JNI versions. */
    return (*vm)->GetEnv(vm, (void **)&unused_env, 0x7fffffff);
}

static jint probe_native_thread(JavaVM *vm) {
    JNIEnv *env = NULL;
    jint before = (*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6);

    if (before != JNI_EDETACHED || env != NULL) {
        return 0;
    }

    jint attach_status = (*vm)->AttachCurrentThread(
            vm, (void **)&env, NULL);
    if (attach_status != JNI_OK) {
        return 0;
    }

    /* After a successful attach, must detach even on error paths. */
    JNIEnv *again = NULL;
    jint after = (*vm)->GetEnv(
            vm, (void **)&again, JNI_VERSION_1_6);

    jint valid = (after == JNI_OK && env != NULL && again != NULL)
            ? JNI_TRUE : JNI_FALSE;
    if (valid) {
        jint version = (*again)->GetVersion(again);
        valid = (version >= JNI_VERSION_1_6)
                ? JNI_TRUE : JNI_FALSE;
    }

    jint detach_status = (*vm)->DetachCurrentThread(vm);

    /* After detach, only use JavaVM; never use env/again. */
    JNIEnv *after_detach = NULL;
    jint detached_status = (*vm)->GetEnv(
            vm, (void **)&after_detach, JNI_VERSION_1_6);

    return (valid && detach_status == JNI_OK
            && detached_status == JNI_EDETACHED
            && after_detach == NULL) ? 1 : 0;
}

#if defined(_WIN32)
static DWORD WINAPI worker_entry(LPVOID argument) {
    WorkerArgs *args = (WorkerArgs *)argument;
    args->result = probe_native_thread(args->vm);
    return 0;
}
#else
static void *worker_entry(void *argument) {
    WorkerArgs *args = (WorkerArgs *)argument;
    args->result = probe_native_thread(args->vm);
    return NULL;
}
#endif

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_nativeWorkerRoundTrip(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    JavaVM *vm = NULL;
    if (get_vm(env, &vm) != JNI_OK) {
        return JNI_ERR;
    }

    WorkerArgs args = {vm, 0};

#if defined(_WIN32)
    HANDLE thread = CreateThread(
            NULL, 0, worker_entry, &args, 0, NULL);
    if (thread == NULL) {
        return JNI_ERR;
    }

    DWORD wait_status = WaitForSingleObject(thread, INFINITE);
    CloseHandle(thread);
    if (wait_status != WAIT_OBJECT_0) {
        return JNI_ERR;
    }
#else
    pthread_t thread;
    if (pthread_create(&thread, NULL, worker_entry, &args) != 0) {
        return JNI_ERR;
    }
    if (pthread_join(thread, NULL) != 0) {
        return JNI_ERR;
    }
#endif

    return args.result;
}
~~~

The entire file is compiled as C (not C++). `WorkerArgs` is placed on the stack of the **JNI caller**, and the caller **joins/waits** for the native worker before reading `args.result`; therefore, the context normally stays alive for the duration of the worker. The demo uses a short-lived worker; in a real system, thread-wait error handling and context ownership must be safe for rare error paths, because if a join/wait operation fails while the worker may still be running, **you must not free/unwind the stack context and leave the worker referencing it**. A heap-allocated context + completion protocol can handle that case.

Breakdown of the key calls:
1. `get_vm(env, &vm)` executes `GetJavaVM` from the proper Java-caller `JNIEnv *`. The valid `JavaVM *vm` is placed into `WorkerArgs`.
2. `callingThreadStatus` executes `GetEnv` directly in the thread called by the JVM: the result is `JNI_OK` when the version is supported, and the output `thread_env` is non-null.
3. `unsupportedVersionStatus` requests an intentionally unsupported version code (`0x7fffffff`); `JNI_EVERSION` is expected, not `JNI_EDETACHED`. This experiment shows that **attach status and version compatibility are two different things**.
4. `worker_entry` is the entry point of the **new OS thread**. It is only given `JavaVM *`, and does not receive the Java thread's `JNIEnv *`.
5. `probe_native_thread` queries `GetEnv` before attach: `JNI_EDETACHED`. After `AttachCurrentThread` succeeds, it calls `GetEnv` again: `JNI_OK` and a valid `JNIEnv *`; only then does it call `GetVersion` through `env`.
6. After `DetachCurrentThread`, any `JNIEnv *` previously obtained in the worker becomes forbidden to use. Calling `GetEnv` again after detach is still valid because it is called through **`JavaVM *`**, not through the old `env`.
7. Once `AttachCurrentThread` has succeeded, the code performs detach even if `GetEnv` or the post-attach version check fails, preventing the native thread from exiting while leaving an attach behind.
8. Java only receives a test code of `1` when the native worker has gone through the exact states and cleanup. Any other code causes Java to throw `AssertionError`, so `RESULT: PASS` cannot be printed when a native step fails.

**Important limitation:** for a long-lived native worker, if `GetEnv` initially returns `JNI_OK` because the thread was attached elsewhere, do not use this demo function as a “detach on behalf of someone else” helper: the code above actively **requires the initial state to be detached** and only attaches under that condition. On a previously attached thread, you must have a multi-branch helper separating a `borrowed env` from an `attached_by_us env`.

### 6.4. Build and Run Commands by Platform

**Linux** (GCC/Clang, JDK 17+, with pthreads):

~~~sh
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o libvmprobe.so native/vm_probe.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.VmProbe
~~~

If `JAVA_HOME` is already set to the JDK root, the `export` line is not needed. `-pthread` requests compilation and linking appropriate for the POSIX threads library. `-Djava.library.path=.` looks for `libvmprobe.so` in the working directory; `-cp out` looks for `VmProbe.class` by package.

**macOS** (Clang, Xcode Command Line Tools):

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home)"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -dynamiclib -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o libvmprobe.dylib native/vm_probe.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.VmProbe
~~~

Choose a compiler target compatible with the JVM: arm64 with arm64 on Apple Silicon, x86-64 with x86-64 when the JVM runs accordingly.

**Windows** (MSVC Developer Command Prompt, same architecture as the JVM):

~~~bat
javac --release 17 -h native -d out src\demo\jni\VmProbe.java

cl /nologo /W4 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /Inative ^
  native\vm_probe.c /Fe:vmprobe.dll

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.VmProbe
~~~

`^` is line continuation in **CMD**; do not use this exact command as-is in PowerShell. `/LD` creates a DLL; `CreateThread` is a Windows API, whereas `pthread_create` belongs to the POSIX branch. You do not need to link the Java application against `libjvm` to run this JNI program, because the JVM provides `JNIEnv *` through the native call.

### 6.5. Expected Output and What Is Actually Proven

With the right JDK, compiler, headers, architecture, and loaded library, the program will print:

~~~text
javaMain=JNI_OK
javaWorker=JNI_OK
unsupportedVersion=JNI_EVERSION
nativeWorker=JNI_EDETACHED -> JNI_OK -> JNI_EDETACHED
RESULT: PASS
~~~

This is the **stdout of the success path** implied by the assertions in the Java code. If any status is wrong, Java throws `AssertionError` instead of printing the lines above; if the library fails to load, the program throws `UnsatisfiedLinkError` before running the checks. The `nativeWorker` output indicates that the stages were checked by C and Java confirmed `1`, rather than being a transcript of C directly printing the three status codes.

Note that `JNI_VERSION_1_6` in the `GetEnv` calls is completely valid on JDK 17+. `JNI_EVERSION` in the example is an **intentional error** from version code `0x7fffffff`, not a failure caused by JDK 17 lacking support for a new Java API. The example uses Java 17 as the compilation target, but the JNI native API definitions are read from `jni.h` of the **JDK used to build**, and the binary must match the platform at runtime.

## 7. Why Does This `GetEnv` Check Matter in Real Systems?

A native library is often called by the JVM through a Java wrapper, and then spawns its own worker threads to poll sockets, monitor devices, perform computations, or call back into Java. Those workers do not receive a `JNIEnv *` from a JVM-native method, so they cannot “stash the main thread's env” for reuse. Instead:

~~~text
Java calls init()
   |
   +-- native method has JNIEnv *env
   |      GetJavaVM(env, &vm)
   |      create native context storing vm (for JVM lifetime)
   |      start native workers
   |
   +-- C worker uses vm:
          GetEnv(vm, &env, version)
             |
             +-- JNI_OK       -> use current thread's env
             +-- JNI_EDETACHED-> AttachCurrentThread; track ownership
             +-- JNI_EVERSION -> report error/update version requirement
          ...
          call Java API/callback if valid
          clean up local/global references
          detach if we attached it ourselves
~~~

To encode this contract, you can use an RAII pattern in C++ or a symmetric helper in C. Below is a **C pseudocode fragment** for a worker function that can **be called on both attached and detached threads**, not a standalone compilable/runnable file:

~~~c
JNIEnv *env = NULL;
int attached_by_us = 0;

jint status = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);
if (status == JNI_EDETACHED) {
    status = (*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
    if (status != JNI_OK) {
        /* Report error and stop before any JNI call. */
        return;
    }
    attached_by_us = 1;
} else if (status != JNI_OK) {
    /* JNI_EVERSION or other error: must not use env. */
    return;
}

/* Reach here only when env is valid for the current thread.
   Perform JNI work, release local refs, handle exceptions. */

if (attached_by_us) {
    (*vm)->DetachCurrentThread(vm);
}
~~~

In an application, **every return/goto/exception branch after attach** must pass through a common cleanup point before the thread exits. If native code returns early and skips `DetachCurrentThread`, the attached thread can prolong resource lifetimes and prevent VM shutdown. If the code detaches immediately after spawning an asynchronous callback that still needs `env`, the callback will use an invalid `env`; you must manage when work finishes before detaching.

Some architectures only need `GetEnv` without attaching: for example, a library registers callbacks that are invoked **from Java-created threads** via JNI. If `GetEnv` is already `JNI_OK`, use the existing `env`. Not every native entry point needs to call `AttachCurrentThread`.

## 8. Common Mistakes When Using `GetJavaVM` / `GetEnv`

| Mistake | Possible outcome | Correct approach |
|---|---|---|
| Saving `JNIEnv *env` from Java main for another C thread to use | Wrong thread, crash/undefined behavior | Pass **`JavaVM *`**, worker calls `GetEnv` and if needed `AttachCurrentThread` |
| Calling `GetEnv` and assuming `env != NULL` without checking the status code | Using `NULL` on a detached thread or unsupported JNI version | Check `JNI_OK` before any JNI call |
| Thinking `GetEnv` auto-attaches on `JNI_EDETACHED` | No valid interface, JNI call fails | Attach only via `AttachCurrentThread`/daemon variant |
| Passing `(void **)env` instead of `(void **)&env` | Output written to the wrong address | Pass the **address** of the pointer variable |
| Calling `(*env)->GetJavaVM` with `env == NULL` | NULL dereference | Call only from a JNI method or an attached thread with a valid `env` |
| Treating `JNI_EVERSION` the same as `JNI_EDETACHED` | Masks a version mismatch | Choose a supported JNI version or report an error |
| Calling `DetachCurrentThread` directly inside a Java native method | Breaks the lifecycle of a JVM-owned Java thread | Detach only native threads that the code actually attached |
| Automatically detaching whenever `GetEnv==JNI_OK` | Detaches a thread not owned by the code | Use an `attached_by_us` flag |
| Using `JNIEnv *` after `DetachCurrentThread` | Invalid environment | Discard the old `env`; re-attach validly if the worker still needs JNI |
| Leaving a non-daemon native worker attached permanently | Holds resources/affects shutdown | Design stop/join/detach, or daemon attach if appropriate |
| Using JNI local refs throughout a long loop of a native-attached worker | Local ref table/resource overflow | `DeleteLocalRef`, `PushLocalFrame`/`PopLocalFrame` |
| Using `JavaVM *` after JVM shutdown/unload | Invalid JVM lifetime | Stop native workers and clean up before teardown |
| Passing JNI pointer addresses via Java `long` without a contract | Unclear ABI/lifetime/provenance | Use JNI handoff through native context/`JavaVM *` in native code |

### A Particularly Subtle Bug: Mixing C and C++ Syntax

In C, call:

~~~c
jint status = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);
~~~

In C++ JNI headers, there is a wrapper call:

~~~cpp
jint status = vm->GetEnv((void **)&env, JNI_VERSION_1_6);
~~~

Both are functionally equivalent, but **cannot be freely swapped in C/C++ source**. When converting `.c` to `.cpp`, use the syntax matching the types in that file, and use the generated header to avoid C++ name mangling for JNI exported methods.

### Another Mistake: Inferring from the Java Thread Name

The name `Thread.currentThread().getName()` does not prove whether an OS native thread is attached or not. JNI status is checked directly with `GetEnv`. Similarly, `JavaVM *` can exist and be valid even when **the current thread** is detached; that is precisely why `GetEnv` is meaningful.

## 9. Ordered Diagnostics When the Example Does Not Run

### A. Failed to Generate the Header or Native Binary

- `javac: file not found`: check `src/demo/jni/VmProbe.java`, the package, and the working directory.
- Missing `native/demo_jni_VmProbe.h`: check `-h native` and the three `native` methods.
- C reports `jni.h: No such file or directory`: `JAVA_HOME` must point to a JDK; add includes for the root and platform directory.
- `conflicting types` signature error: implement according to the generated header, including the two hidden parameters `JNIEnv *` and `jclass`.
- `pthread.h` does not exist on Windows/MSVC: the code must enter the `_WIN32` branch with `windows.h`; do not use POSIX flags on MSVC.

### B. Binary Exists, but the JVM Cannot Load It

- `UnsatisfiedLinkError: no vmprobe in java.library.path`: check `libvmprobe.so`/`libvmprobe.dylib`/`vmprobe.dll` and `-Djava.library.path=.`.
- `wrong ELF class` / architecture mismatch: align OS/CPU/JVM/toolchain.
- `UnsatisfiedLinkError` when calling one of the three native methods: compare `javap -s -p`, the generated header, and exported symbols. A library may load yet still lack a native method with the exact name.
- If the error comes from the native loader **missing a dependent library**, use `ldd libvmprobe.so` (Linux), `otool -L libvmprobe.dylib` (macOS), or `dumpbin /DEPENDENTS vmprobe.dll` (Windows) as appropriate. Do not confuse the Java classpath with the native library search path.

### C. Loaded, but Status Codes Are Wrong

If the assertion displays something like `JNI status mismatch: 0, 0, -3, 0`, the two Java threads and the unsupported version check passed, but the native round trip returned `0`. Check:
- Is the native-created thread truly new/detached?
- Did `GetEnv` receive `JNI_EDETACHED` and output `env==NULL` before attach?
- Did `AttachCurrentThread` return `JNI_OK`, and was `env` non-NULL?
- Did `GetEnv` after attach return `JNI_OK`?
- Was `DetachCurrentThread` called after JNI work completed?
- Did the join/wait call actually wait for the thread to finish, and was the binary rebuilt from source?

Do not replace this with “just printing the `JNIEnv *` address,” because the address is not a contract. To investigate, log **the status code and thread identifier** at the exact checkpoints, avoiding printing sensitive or uncontrolled-lifetime information. When native code has many JNI calls, try `-Xcheck:jni` on HotSpot to catch part of improper JNI usage; the tool is not guaranteed to catch every race or lifetime bug.

## 10. Production Scenario: Storing `JavaVM *` and Shutting Down Properly

A native module that creates asynchronous workers typically obtains `JavaVM *` once during JNI initialization and keeps it in a native context. Storing `JavaVM *` is meaningful **for the lifetime of that JVM**; do not call `free(vm)` and do not treat it as valid after the JVM has stopped. Workers must be stopped/joined and JNI refs/native resources must be cleaned up before the context is freed.

### Decisions That Must Be Documented in the Native Subsystem Contract

| Concern | Design question |
|---|---|
| JVM lifetime | Who guarantees the JVM is still alive when a worker calls `GetEnv`/`AttachCurrentThread`? |
| Attach ownership | Is the thread Java-created or native-created? Where is `AttachCurrentThread` called, and where must detach happen? |
| Callback | If calling back into Java, where are exceptions checked/handled? |
| Local reference lifetime | Does the worker have a long loop? Are `DeleteLocalRef`/local frames used? |
| Class loading | An attached native thread may initially have the bootstrap loader as its context class loader; looking up application classes via `FindClass` may require explicit class loader handling |
| Termination | On JVM shutdown, are there a stop flag, join, timeout, and a guarantee not to start new callbacks? |
| Resource ownership | `JavaVM *` is not an object to `free`; global refs need `DeleteGlobalRef`; native allocations need their own cleanup |

For an attached native worker calling Java static/object methods, ensure class/method IDs have been properly resolved; `jclass` is a JNI reference with a lifetime, and if cached long-term, an appropriate global ref must be used. Do not send a Java caller's local ref to a worker as a shared pointer. Reference ownership/callback topics have additional rules of their own, but **the first unlocking step is always the thread status from `GetEnv`**.

## 11. Acceptance Checklist for `GetJavaVM` and `GetEnv`

- [ ] A valid `JNIEnv *` from a JNI method or an already-attached thread exists before calling `GetJavaVM`.
- [ ] Called `(*env)->GetJavaVM(env, &vm)` and checked `JNI_OK` together with `vm != NULL`.
- [ ] Passed only `JavaVM *` to the native worker, not the Java caller's `JNIEnv *`.
- [ ] Called `GetEnv` with `(void **)&env` and a supported version, such as `JNI_VERSION_1_6`.
- [ ] Branched on `JNI_OK` (already attached), `JNI_EDETACHED` (not attached), and `JNI_EVERSION` (unsupported version).
- [ ] `GetEnv` does not auto-attach; `env` is used only when the status permits.
- [ ] Native worker only uses JNI after a successful attach, then detaches **only when the worker/code owns the attach**.
- [ ] Does not detach a Java-owned thread; does not use `JNIEnv *` after detach or cross-thread.
- [ ] JNI local refs, Java exceptions, and callback lifetimes are managed before detach.
- [ ] Java class/header/C export/binary match in version; Java and native tests for expected statuses pass.
- [ ] Shutdown stops/joins native workers before the JVM/context is freed.

## 12. Self-Check Questions

**Question 1.** A native method has `JNIEnv *env` and wants another pthread to call Java. Can it store `env` in a global variable?  
**Answer:** No. `JNIEnv *` is bound to the current thread. Obtain `JavaVM *` via `GetJavaVM` and have the worker call `GetEnv`; if detached, attach and use the `env` received by the worker itself.

**Question 2.** On a Java `new Thread(...)` entering a native method, what does `GetEnv` return?  
**Answer:** With a supported JNI version and the thread executing a JNI method, this thread is already attached, so it returns `JNI_OK` along with a valid `JNIEnv *` for that thread.

**Question 3.** A C-created thread receives `JNI_EDETACHED`. After calling `GetEnv`, can it call `GetVersion` through `env` yet?  
**Answer:** Not yet. `GetEnv` does not attach, and the output `env` is set to NULL. `AttachCurrentThread` must succeed before making JNI calls.

**Question 4.** Why does version `0x7fffffff` in the demo produce `JNI_EVERSION` even though the Java thread is attached?  
**Answer:** `GetEnv` has two conditions: the thread is attached **and** the JNI interface version is supported. The test value is intentionally unsupported, so it returns `JNI_EVERSION`. It does not mean the Java bytecode is incompatible.

**Question 5.** Calling `GetEnv` returns `JNI_OK`; is it always right to detach when finished?  
**Answer:** No. `JNI_OK` only describes the status; the caller may be “borrowing” an attach managed by the JVM or elsewhere. Detach only native threads that the code itself attached per the lifecycle contract.

**Question 6.** After `DetachCurrentThread`, can the old `JNIEnv *env` pointer be reused to obtain `JavaVM`?  
**Answer:** No. The old `env` is no longer valid. If a valid `JavaVM *` is still held and the worker needs JNI again, it must check/re-attach following the procedure; do not dereference the old `env`.

## 13. Summary and Technical References

**`GetJavaVM`** retrieves the JVM interface from an **already valid** `JNIEnv *`; **`GetEnv`** queries the status **of the current thread**, returning `JNI_OK`, `JNI_EDETACHED`, or `JNI_EVERSION`. Having `JavaVM *` does not mean every thread automatically has a `JNIEnv *`. Clearly decide who owns attach/detach, never use `env` on the wrong thread, never continue JNI calls after detach, and clean up references/callbacks before the native worker exits.

Official references: [Oracle JNI Functions — GetJavaVM](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html), [Oracle JNI Invocation API — GetEnv, AttachCurrentThread, DetachCurrentThread](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html), [Oracle JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html). Rules regarding versions, thread state, and ABI should be verified directly against `jni.h` and the running JVM/toolchain.
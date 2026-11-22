# Distinguishing JavaVM Used to Access the JVM from Per-Thread JNIEnv in JNI

## Learning Objectives

In the Java Native Interface (JNI), **JavaVM** and **JNIEnv** are both interface types for native code to work with the Java Virtual Machine, but **their usage scope, functionality, and lifecycle differ**. Confusing the two types can lead to wrong-thread access errors, invalid references, JNI crashes, difficulty handling asynchronous callbacks, or preventing the process from exiting.

After this lesson, you can:

1. Explain the role of **JavaVM \*** as a JVM-level handle and **JNIEnv \*** as the JNI interface of the **currently running thread**.
2. Identify the sources for obtaining JavaVM/JNIEnv: native method parameters, **JNI_OnLoad**, **GetJavaVM**, **GetEnv**, and **AttachCurrentThread**.
3. Distinguish threads **created by Java** from threads **created by native code**; know when to attach and detach.
4. Properly handle **JNI_OK**, **JNI_EDETACHED**, and **JNI_EVERSION** statuses.
5. Design callbacks from a native thread back to Java with the **thread-appropriate JNIEnv**, valid references, clear class loader handling, and complete cleanup.
6. Run a Java 17+ combined with C/JNI example on Linux/macOS to see both Java threads and native pthread threads using the same JavaVM while having to obtain JNIEnv in each thread.

## 1. Mental Model: One JVM, Many Threads, Each Thread with One Valid JNI Environment

Suppose a Java application calls a C library. The JVM manages multiple Java threads, while the C library can create its own OS threads to process work. You need to view the JNI boundary in two layers:

~~~text
                 Running JVM
                 JavaVM* (VM-level interface)
                         |
        +----------------+----------------+
        |                |                |
 Java thread A      Java thread B    Native pthread C
   attached           attached       initially DETACHED
        |                |                |
  JNIEnv* A         JNIEnv* B       AttachCurrentThread
        |                |                |
  Call JNI API      Call JNI API        JNIEnv* C
                                          |
                                     Call JNI API
                                          |
                                   DetachCurrentThread
~~~

**JavaVM \*** can be kept in a native region with a managed lifecycle and shared among threads that need to connect to the **same JVM**. It provides virtual-machine-level operations such as **GetEnv**, **AttachCurrentThread**, **AttachCurrentThreadAsDaemon**, and **DetachCurrentThread**.

**JNIEnv \*** is the interface for the **current thread** to call JNI functions: looking up classes, creating Strings, reading/writing fields, calling Java methods, checking exceptions, and managing Java references. A JNIEnv pointer is **only valid in the thread that received it**. Never pass that pointer to another thread even if both threads run in the same process.

This is a difference in **threading contract**, not just different type names. The fact that two pointers might look similar or point to the same function table on a specific JVM does not make them arbitrarily interchangeable.

### Core Comparison Table

| Criterion | **JavaVM \*** | **JNIEnv \*** |
| --- | --- | --- |
| Represents | Interface at the level of an existing JVM | Valid JNI interface for the **current thread** |
| Scope | Used to manage access to the VM from threads | **Used only in the thread that received it** |
| How to obtain | **JNI_OnLoad(vm, ...)** or **env->GetJavaVM** (C++ syntax), Invocation API | First parameter of native method; **vm->GetEnv** when already attached; **AttachCurrentThread** when attach is needed |
| Characteristic APIs | **GetEnv**, **AttachCurrentThread**, **DetachCurrentThread** | **FindClass**, **NewStringUTF**, **GetFieldID**, **CallVoidMethod**, **ExceptionCheck**... |
| Shareable across threads? | **Yes**, within the proper VM lifecycle and scope | **No** |
| Can be stored globally? | Can be cached with library/VM lifecycle control | **Do not cache globally for use by multiple threads** |
| When native thread is unattached | Can use JavaVM to query/access the attach step | **No valid JNIEnv yet** to call JNI APIs |
| When native thread detaches | JavaVM still exists if the VM is still alive | JNIEnv of the detached thread **must not be used further** |

**JavaVM is not java.lang.Thread**, and **JNIEnv is not a Java object** that can be put into Java's ThreadLocal to replace the entire JNI contract. They are native interface types provided by the JVM.

## 2. Why Is JNIEnv Tied to a Thread?

JNIEnv is a pointer to an interface structure of JNI functions. The JVM may attach **thread-specific data** to that environment: pending exception state, local references, data for Java–native transitions, and other runtime mechanisms.

Therefore:

- When Java thread A calls a native method, the JVM passes a **valid JNIEnv for A**.
- When Java thread B calls the same native method, the JVM passes a **valid JNIEnv for B**.
- Native code calling **GetEnv** on JavaVM in A only retrieves **A's** environment, not B's environment.
- A JNIEnv pointer from A must not be placed in a global variable and then used from B.
- Native thread C must be in an attached state before calling functions via JNIEnv; **GetEnv does not attach automatically**.

The JNI Specification guarantees that a native method called repeatedly **on the same Java thread** receives the same JNI interface pointer. However, you should not write algorithms that depend on the numeric address of JNIEnv to identify a thread; use real thread identity and synchronization mechanisms instead.

### Two Common C Signatures

~~~c
/* Native method called from Java. */
JNIEXPORT void JNICALL
Java_Demo_nativeOperation(JNIEnv *env, jobject self) {
    /* env is valid in the thread executing this method. */
    (void)self;
}

/* Hook when the JNI library is loaded by the JVM. */
JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}
~~~

These are **two signature-describing snippets**, not standalone JNI programs. An instance native method receives **JNIEnv \*** and **jobject self**; if the Java method is declared **static native**, the second parameter is **jclass**, not an instance jobject.

**JNI_OnLoad** is passed JavaVM, whereas a native method is normally passed JNIEnv. The two entry points complement each other: JavaVM helps identify the VM/attach threads, while JNIEnv helps execute specific Java APIs on an attached thread.

### C and C++ Differ in Syntax, Not in Thread Rules

In **C**:

~~~c
JavaVM *vm = NULL;
jint status = (*env)->GetJavaVM(env, &vm);
~~~

In **C++**, you can write:

~~~cpp
JavaVM *vm = nullptr;
jint status = env->GetJavaVM(&vm);
~~~

These are equivalent snippets in terms of API. C syntax typically repeats **env** as the first argument; C++ syntax uses inline member functions. Regardless of which language is used, **JNIEnv remains thread-specific** and JavaVM can still be used to obtain/attach the environment in each thread.

## 3. Obtaining JavaVM Properly

### 3.1. JNI_OnLoad: Obtaining the VM at Library Load Time

A library loaded by **System.loadLibrary** can export **JNI_OnLoad**:

~~~c
#include <jni.h>

static JavaVM *g_vm = NULL;

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)reserved;
    g_vm = vm;
    return JNI_VERSION_1_6;
}
~~~

**g_vm** holds the JVM handle so native workers started later can use it. **JNI_OnLoad** returns the minimum JNI version required by the library; for example, requesting JNI 1.6, which is supported by JDK 17+.

Notes:

1. Storing the JavaVM handle in a global variable can be valid **within the JVM/library lifecycle**. Do not use it after the VM has terminated.
2. Only use **g_vm** once the library has loaded successfully and the initialization flow ensures the value is ready. When there are multiple native workers, manage spawn/stop timing and synchronization appropriately.
3. If the library supports unloading/hot reload, you must stop workers and release references/caches before the library is unloaded; do not leave threads running code from a library that has disappeared.
4. **JNI_OnLoad** is not the place to create and keep a shared JNIEnv to hand out to all threads.

### 3.2. GetJavaVM: Obtaining the VM from the Current JNIEnv

In a native method that has received a valid **JNIEnv \***:

~~~c
JavaVM *vm = NULL;

jint status = (*env)->GetJavaVM(env, &vm);
if (status != JNI_OK || vm == NULL) {
    return; /* Example inside a void native method. */
}

/* Store or pass vm according to an appropriate lifecycle. */
~~~

**GetJavaVM** returns the JavaVM associated with the current JNIEnv. If you only need the VM from a Java callback and then pass that information to a native worker, this is the right direction. The reverse direction does not use a cast: to get a JNIEnv from a JavaVM, call **GetEnv** or attach the thread conditionally.

**Wrong:**

~~~c
/* INTENTIONALLY WRONG: never treat JavaVM as JNIEnv. */
JNIEnv *wrong = (JNIEnv *)vm;
/* Do not call JNI APIs on wrong. */
~~~

The pointer types do not have an interchangeable layout contract. A C cast may make the compiler accept the statement, but executing it violates JNI and can crash the JVM.

## 4. Obtaining JNIEnv Properly: Three Scenarios

### 4.1. Thread Created by Java, Currently Calling a Native Method

The JVM **has already attached** the Java thread. The native method is passed a valid JNIEnv:

~~~c
JNIEXPORT jboolean JNICALL
Java_Demo_isAttached(JNIEnv *env, jclass type) {
    (void)type;
    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        return JNI_FALSE;
    }

    JNIEnv *again = NULL;
    jint result = (*vm)->GetEnv(
        vm, (void **)&again, JNI_VERSION_1_6
    );

    return (result == JNI_OK && again == env)
            ? JNI_TRUE : JNI_FALSE;
}
~~~

This is a **snippet** in class Demo declaring **static native boolean isAttached()**. Calling GetEnv returns the environment of the exact calling Java thread; there is no need to call **AttachCurrentThread**.

**Do not call DetachCurrentThread inside a native method called by Java**. Normally this thread still has Java frames on the stack, and it does not belong to the lifecycle ownership of that native code. To continue calling Java after the native method returns, the JVM still needs this thread attached.

### 4.2. Unattached Native Thread

A thread created with **pthread_create** (Linux/macOS), Windows thread APIs, or a thread pool in a native library typically starts in the **JNI_EDETACHED** state with respect to the JVM, even in the same process:

~~~c
JNIEnv *env = NULL;
jint status = (*vm)->GetEnv(
    vm, (void **)&env, JNI_VERSION_1_6
);

if (status == JNI_EDETACHED) {
    if ((*vm)->AttachCurrentThread(
            vm, (void **)&env, NULL) != JNI_OK) {
        return; /* No valid JNIEnv yet. */
    }

    /* From here, env belongs to the current native thread. */
    /* Call Java/JNI, release local refs, and handle exceptions. */

    (*vm)->DetachCurrentThread(vm);
} else if (status == JNI_OK) {
    /* Thread already attached; use env, do not own detaching. */
} else {
    /* JNI_EVERSION or another error: handle explicitly. */
}
~~~

This is an illustrative snippet inside a **native worker**, assuming a valid **JavaVM *vm** variable. Once attached successfully, the native thread becomes a thread that can use JNI and Java. It must detach **before that thread itself terminates**; the detach call must not be executed on another thread.

### 4.3. Previously Attached Native Thread

**GetEnv** returns **JNI_OK** and the JNIEnv of that same thread. Calling **AttachCurrentThread** again on an already attached thread returns the current environment without performing a new attach. However, you should not infer that just because a caller called Attach, it always has the right to Detach.

Track **ownership** explicitly:

- If **GetEnv == JNI_EDETACHED**, your code calls attach successfully: mark **attachedHere = true**, then detach in the cleanup branch of the same worker.
- If **GetEnv == JNI_OK**, the thread was already attached by someone else/the JVM: **attachedHere = false**; use the valid env and return without detaching a thread you do not own.
- If **GetEnv == JNI_EVERSION**, the JVM does not support the JNI version you requested; **do not assume** it is simply unattached.
- For any other status, handle the error specifically instead of accessing an **env == NULL**.

## 5. GetEnv, AttachCurrentThread, and DetachCurrentThread

### 5.1. GetEnv Only Checks Status and Retrieves the Current Environment

C signature (from the JavaVM table):

~~~c
jint GetEnv(JavaVM *vm, void **env, jint version);
~~~

| Result | Meaning | Action |
| --- | --- | --- |
| **JNI_OK** | Current thread is attached and version is supported | Use the **JNIEnv** just obtained on **this thread** |
| **JNI_EDETACHED** | Current thread is not yet attached | If Java is truly needed, call **AttachCurrentThread** or its daemon variant |
| **JNI_EVERSION** | Requested JNI version is not supported | Review the version contract; do not use env |
| Other error | Operation did not succeed | Do not proceed with an unverified env |

**GetEnv does not "retrieve another thread's JNIEnv"** and does not accept a thread ID. There is no standard API like **GetEnv(vm, javaThreadId)**.

### 5.2. AttachCurrentThread and AttachCurrentThreadAsDaemon

~~~c
JNIEnv *env = NULL;
jint code = (*vm)->AttachCurrentThread(
    vm, (void **)&env, NULL
);
~~~

When successful, the native thread is attached as a **non-daemon Java thread**. You can use **AttachCurrentThreadAsDaemon** if the worker is designed as a daemon.

Important point: **daemon status** determines the thread's impact on JVM shutdown waiting behavior; it does not make JNI references or callbacks automatically safe. A non-daemon native worker that does not terminate/detach can cause the JVM to keep waiting on shutdown; a daemon worker should not by default skip lifecycle cleanup.

If the thread is already attached, calling AttachCurrentThread or AttachCurrentThreadAsDaemon again **does not change its daemon status**. Therefore, choose daemon/non-daemon intentionally at attach time, and document whether the process needs to wait for the thread to finish.

**JavaVMAttachArgs** allows setting a name and thread group in valid contexts, with fields such as **version**, **name** (modified UTF-8), and **group**. Not every application needs this option; **NULL** uses the default values in the example.

### 5.3. DetachCurrentThread: Call on the Attached Thread Itself

~~~c
jint code = (*vm)->DetachCurrentThread(vm);
~~~

A native thread that attached itself needs to call detach after it has:

1. Completed all Java callback calls and has no Java methods remaining on that thread's stack.
2. Cleaned up local/global references it owns according to the data management flow.
3. Handled any pending Java exceptions thrown during callbacks, because there is no natural Java caller to receive exceptions from a native background thread.
4. Exited critical regions/locks and other JNI states requiring cleanup.

JNI does not allow a thread to detach while **Java methods are still on the call stack**. After detaching, the old JNIEnv pointer is **invalid**. If the thread needs to use JNI again later, it must GetEnv/Attach again and receive a new valid JNIEnv.

**Do not call DetachCurrentThread "on behalf of" another thread.** The function operates on the **current thread**.

## 6. VM-Level and Thread-Level Do Not Equal Reference-Level

A design bug that goes hand in hand with storing JNIEnv globally is **storing Java local references and sending them to a worker thread**.

| Item to Keep | Shareable? | Valid Lifecycle |
| --- | --- | --- |
| **JavaVM \*** | Can be passed between threads | Within the JVM lifecycle |
| **JNIEnv \*** | No | Only the thread that received it, while still attached |
| **jobject/jclass/jstring local reference** | Must not be passed across threads | Only the thread that created/received it and its corresponding local scope |
| **global reference** created with NewGlobalRef | Can be used from another attached thread | Until DeleteGlobalRef; still requires concurrency protection at the Java level |
| **jmethodID/jfieldID** | Metadata ID, not a Java object reference | Only within the corresponding class lifecycle; class unloading must be considered |

### Example of Passing a Callback Properly

Suppose Java passes a Runnable into a native method, but C wants to call **Runnable.run()** on a worker after the initial native method has returned.

**Wrong:** storing the raw **jobject callback**, which is a local reference, and using it on a native worker. The reference may expire when the JNI method finishes and is inherently invalid on another thread.

**Right:** if an asynchronous callback is truly needed, create a **global reference** with clear ownership:

~~~c
/* Snippet inside a native method that has a valid env and callback. */
jobject callbackGlobal = (*env)->NewGlobalRef(env, callback);
if (callbackGlobal == NULL) {
    return;  /* OutOfMemoryError may be pending. */
}

/* Pass callbackGlobal and JavaVM* to the worker using a synchronized
   protocol; must DeleteGlobalRef at the right time when finished. */
~~~

Inside the attached worker, use the **worker's own JNIEnv** to call Java; when all callbacks are finished and no one uses the global reference anymore, call **DeleteGlobalRef** on a valid attached thread.

A global reference only ensures the object remains recognized by the JVM; **it does not make the Java object thread-safe**. If the callback contains mutable state, Java code must still follow normal synchronization, visibility, and lifecycle rules.

### Local References on Long-Lived Native-Attached Workers

In a Java-originated native method, local references are automatically cleaned up when the method returns. However, a worker attached from C running a long loop may **not have a corresponding native method return boundary** for each callback iteration. Therefore, you should call **DeleteLocalRef** after each task or use **PushLocalFrame/PopLocalFrame** with error checking.

Do not accumulate tens of thousands of **jclass/jstring/jobject** local references just because the application has not called DetachCurrentThread yet. This can exhaust local reference capacity and retain many unnecessary Java objects.

## 7. Runnable Java 17+ and C/JNI Example: Two Thread Sources

This example uses **one JNI library** and tests two scenarios:

- **Java-originated calls:** the main thread and two Java threads call a native method; the JVM passes the thread-appropriate JNIEnv. Native code uses **GetJavaVM** and then **GetEnv** to verify whether the retrieved JNIEnv matches the calling thread's env.
- **Native-originated thread:** JNI creates a **pthread** (POSIX). The new thread initially receives **JNI_EDETACHED**, calls **AttachCurrentThread**, checks GetEnv, and then calls **DetachCurrentThread**.

**Runnable example on Linux/macOS**, where pthread is available. On Windows, the Java side and JNI rules remain the same, but the pthread creation part needs to be ported to the Windows native thread API; you cannot simply change the library extension and compile pthread code with MSVC.

### Step 1 — Write ThreadVmDemo.java

~~~java
public final class ThreadVmDemo {
    static {
        System.loadLibrary("threadvmdemo");
    }

    private ThreadVmDemo() {
    }

    private static native boolean checkCaller();
    private static native boolean checkNativeThread();

    public static void main(String[] args) throws InterruptedException {
        // Call from the already attached Java main thread.
        boolean mainOk = checkCaller();

        // Each Java Thread has its own JNI context.
        boolean[] results = new boolean[2];

        Thread first = new Thread(
                () -> results[0] = checkCaller(), "java-first"
        );
        Thread second = new Thread(
                () -> results[1] = checkCaller(), "java-second"
        );

        first.start();
        second.start();

        // join() ensures both results are written before printing.
        first.join();
        second.join();

        System.out.println("main=" + mainOk);
        System.out.println("java-first=" + results[0]);
        System.out.println("java-second=" + results[1]);
        System.out.println("native-worker=" + checkNativeThread());
    }
}
~~~

**Thread.join()** provides the visibility guarantee needed for main to see each element's value after the threads finish. The execution order of the two workers may vary, but **the stdout print order is fixed**, because main only prints after both join.

### Step 2 — Generate the Class and JNI Header

~~~bash
javac -h . ThreadVmDemo.java
~~~

The command generates **ThreadVmDemo.class** and **ThreadVmDemo.h**. The header file helps ensure the two JNI function names match the Java native methods. Both methods are static, so the C functions receive **JNIEnv \*** and **jclass**.

### Step 3 — Create thread_vm_demo.c

~~~c
#include "ThreadVmDemo.h"
#include <pthread.h>

/*
 * Shared JVM handle, obtained when the library is loaded.
 * Do not store JNIEnv* in a global or pass it across pthread.
 */
static JavaVM *g_vm = NULL;

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)reserved;
    g_vm = vm;
    return JNI_VERSION_1_6;
}

/*
 * Called from an arbitrary Java thread.
 * env is only valid for the Java thread executing this method.
 */
JNIEXPORT jboolean JNICALL
Java_ThreadVmDemo_checkCaller(JNIEnv *env, jclass unused) {
    (void)unused;

    JavaVM *from_env = NULL;
    JNIEnv *same_thread_env = NULL;

    if ((*env)->GetJavaVM(env, &from_env) != JNI_OK) {
        return JNI_FALSE;
    }
    if (from_env != g_vm) {
        return JNI_FALSE;
    }

    jint result = (*g_vm)->GetEnv(
        g_vm, (void **)&same_thread_env, JNI_VERSION_1_6
    );

    return (result == JNI_OK && same_thread_env == env)
            ? JNI_TRUE : JNI_FALSE;
}

/* Each worker run has its own result struct. */
typedef struct WorkerResult {
    jint before_attach;
    jint after_attach;
    jint detach_result;
    int env_matches;
} WorkerResult;

/* Function running on a pthread created entirely by native code. */
static void *worker_main(void *argument) {
    WorkerResult *result = (WorkerResult *)argument;

    JNIEnv *env = NULL;
    result->before_attach = (*g_vm)->GetEnv(
        g_vm, (void **)&env, JNI_VERSION_1_6
    );

    if (result->before_attach != JNI_EDETACHED) {
        return NULL;
    }

    jint attach_result = (*g_vm)->AttachCurrentThread(
        g_vm, (void **)&env, NULL
    );
    if (attach_result != JNI_OK) {
        return NULL;
    }
    if (env == NULL) {
        result->detach_result =
                (*g_vm)->DetachCurrentThread(g_vm);
        return NULL;
    }

    /* After attach, GetEnv returns the JNIEnv of this pthread itself. */
    JNIEnv *again = NULL;
    result->after_attach = (*g_vm)->GetEnv(
        g_vm, (void **)&again, JNI_VERSION_1_6
    );

    result->env_matches =
            (result->after_attach == JNI_OK && again == env);

    /* Do not retain the pthread's env or references after detach. */
    result->detach_result =
            (*g_vm)->DetachCurrentThread(g_vm);
    return NULL;
}

/* Run a native worker and wait for completion. */
JNIEXPORT jboolean JNICALL
Java_ThreadVmDemo_checkNativeThread(
        JNIEnv *env, jclass unused) {
    (void)env;
    (void)unused;

    WorkerResult result = {
        JNI_ERR, JNI_ERR, JNI_ERR, 0
    };

    pthread_t native_thread;
    if (pthread_create(
            &native_thread, NULL, worker_main, &result) != 0) {
        return JNI_FALSE;
    }

    if (pthread_join(native_thread, NULL) != 0) {
        return JNI_FALSE;
    }

    return (
        result.before_attach == JNI_EDETACHED &&
        result.after_attach == JNI_OK &&
        result.env_matches &&
        result.detach_result == JNI_OK
    ) ? JNI_TRUE : JNI_FALSE;
}
~~~

### Analyzing Each C Part

**JNI_OnLoad:** receives the process's JavaVM and keeps it in **g_vm**. All workers operate with this JVM, but do not share a single JNIEnv pointer.

**checkCaller:** receives **env** from the JVM because Java called the native method. **GetJavaVM** retrieves that env's JavaVM; **GetEnv** is called **on the current Java thread itself**, so it returns the same valid JNI interface pointer. This verifies per-thread consistency; **it never shares the main thread's env to another thread**.

**worker_main:** starts on a POSIX thread not created by the JVM. **GetEnv** returns **JNI_EDETACHED** as expected in the demo scenario. **AttachCurrentThread** returns the **native worker's env**, and the subsequent GetEnv returns JNI_OK with the same env. Finally, **DetachCurrentThread** runs **on the native worker itself**, before the pthread exits.

**checkNativeThread:** this method starts on a Java thread with its own env, but **does not pass env to the pthread**. It only waits for the pthread to finish, then inspects the result codes stored in the C struct. The result struct lives on the caller's stack for the entire duration the worker runs and is read after **pthread_join**.

**Intentional limitation:** the demo uses **pthread_join** directly inside the native method to keep the result struct lifecycle short and easy to verify. It is not an architecture for a long-lived asynchronous native worker system. In production, you need a thread manager, shutdown handling, pthread error handling, and proper memory ownership; never let a worker continue accessing a pointer into the stack after the caller has returned.

### Step 4 — Build the Native Library

Requires JDK 17+ with **JAVA_HOME** pointing to a JDK containing JNI headers, a C compiler, and POSIX pthread.

**Linux, GCC:**

~~~bash
gcc -std=c11 -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  thread_vm_demo.c -o libthreadvmdemo.so
~~~

**macOS, Clang:**

~~~bash
clang -std=c11 -fPIC -dynamiclib -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  thread_vm_demo.c -o libthreadvmdemo.dylib
~~~

Both outputs match the logical name **threadvmdemo** used in **System.loadLibrary("threadvmdemo")** on their respective platforms. If the JVM runs on a different CPU architecture than the C binary, you must rebuild for the same architecture/ABI.

### Step 5 — Run

~~~bash
java -Djava.library.path=. ThreadVmDemo
~~~

**Exact stdout when build/load and pthread succeed:**

~~~text
main=true
java-first=true
java-second=true
native-worker=true
~~~

This is the result based on **actual JNI state**, independent of whichever order the thread scheduler runs: the Java workers do not print directly; main only prints after join.

Starting from JDK 24, JNI versions/configurations have restricted native access mechanisms. If you need to allow native access for a classpath application, run with the appropriate option:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. ThreadVmDemo
~~~

On some configurations, missing the permission flag may produce a **stderr** warning or be denied by policy, not as part of the stdout above. Only enable access for the modules that need it when the application runs on the module path.

### Step 6 — When the Program Returns False or Errors

| Symptom | Check Suggestion |
| --- | --- |
| **UnsatisfiedLinkError** before printing | Missing/wrong library name, ABI, or dependency; check java.library.path and binary build |
| **main=false** | JNI_OnLoad did not receive the proper VM, GetJavaVM/GetEnv failed, or the wrong library is running |
| **java-first/second=false** | Native method's GetEnv call failed or returned an env for the wrong thread; check JNI correctness |
| **native-worker=false** | pthread_create/join error, GetEnv before attach did not have the expected status, Attach/Detach error |
| JVM crash | Violation of native memory/thread API or incompatible binary; check crash log and run -Xcheck:jni |

You can enable HotSpot's JNI checking mechanism in a test environment:

~~~bash
java -Xcheck:jni -Djava.library.path=. ThreadVmDemo
~~~

Depending on the JDK, combine this with the appropriate native access flag. **-Xcheck:jni** helps detect many incorrect JNI usages, but does not replace checking ownership, synchronization, or memory safety in C code.

## 8. Calling a Java Callback Safely from a Native Worker

The previous runnable example only verifies attach status. In real systems, a native worker often also needs to **call a Java method** or send results back to the application.

A safe callback requires all four conditions simultaneously:

1. **JavaVM \*** is still valid in the current lifecycle.
2. The worker has its own **JNIEnv \***, already attached.
3. The callback object is held by a reference with an appropriate lifetime, such as a **global reference** if the callback runs after the initial native method.
4. The Java callback, class loader, exceptions, and synchronization are handled explicitly.

The following snippet assumes **callbackGlobal** is a **global reference to a java.lang.Runnable** that was properly created and is still alive. This is a **helper called from a previously created native worker**, not a complete program; thread creation/callback ownership is coordinated by the system.

~~~c
static void call_runnable_on_worker(
        JavaVM *vm, jobject callbackGlobal) {
    JNIEnv *env = NULL;
    int attached_here = 0;

    jint status = (*vm)->GetEnv(
        vm, (void **)&env, JNI_VERSION_1_6
    );

    if (status == JNI_EDETACHED) {
        if ((*vm)->AttachCurrentThread(
                vm, (void **)&env, NULL) != JNI_OK) {
            return;
        }
        attached_here = 1;
    } else if (status != JNI_OK) {
        return; /* Example: JNI_EVERSION. */
    }

    jclass cls = (*env)->GetObjectClass(env, callbackGlobal);
    if (cls != NULL) {
        jmethodID run_id = (*env)->GetMethodID(
            env, cls, "run", "()V"
        );

        if (run_id != NULL) {
            (*env)->CallVoidMethod(
                env, callbackGlobal, run_id
            );
        }

        (*env)->DeleteLocalRef(env, cls);
    }

    /*
     * A background native thread has no natural Java caller
     * to receive callback exceptions.
     * The demo chooses to log the error to stderr and then clear it for cleanup.
     */
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }

    /*
     * This function does NOT own callbackGlobal;
     * the caller is responsible for DeleteGlobalRef once
     * no worker uses that reference anymore.
     */
    if (attached_here) {
        (*vm)->DetachCurrentThread(vm);
    }
}
~~~

**Note:** the demo code intentionally handles exceptions with **ExceptionDescribe/ExceptionClear** to illustrate cleanup on a native background thread. Production needs to route errors to an appropriate logging/response/monitoring mechanism; do not silently ignore exceptions. If the caller is in a native method called by Java, **do not detach** because **attached_here = 0**.

### Why Does a Callback Need a Global Reference?

If Java calls a native method and passes a **Runnable callback** object, the jobject parameter in the native method is a **local reference** of the calling thread and is only valid within that scope. Native code that wants to retain it for an asynchronous callback must create **NewGlobalRef** before the method returns. The worker receives this reference through a queue with proper synchronization/ownership, uses its own env to CallVoidMethod, and then the reference is deleted by the owner with **DeleteGlobalRef** when no one uses it anymore.

**Do not use the env of the thread that created the callback** to call Java from the worker, even when callbackGlobal is a valid global reference. Global references and JNIEnv have two separate contracts: a reference can be shared, whereas JNIEnv remains restricted per thread.

## 9. Class Loader When a Native Worker Attaches Itself

There is a subtle risk: **a newly attached native thread typically has the bootstrap loader as its default thread context class loader**. When calling **FindClass** from a thread with no active Java native method frame, JNI does not necessarily search for the class via the loader of the module/plugin that called a method earlier. According to the JNI Invocation API, the FindClass case with no current native method typically uses the **system class loader**, which may not see classes from a custom/module/plugin class loader.

Thus, the same call:

~~~c
jclass cls = (*env)->FindClass(
    env, "com/example/plugin/Callback"
);
~~~

may work when called from a native method of a specific Java class, yet fail on a native background thread if the class only exists in a custom class loader.

Approaches to handle this:

- The Java caller **passes the callback object or Class** into JNI in the appropriate class loader context.
- When long-term use is needed, native code creates a **global reference** to the Class/callback provided by Java, and releases it according to lifecycle.
- Or store a **ClassLoader** in a controlled manner and call **loadClass** through JNI on the proper worker thread; avoid relying on default FindClass.
- If you need to look up system classes such as **java/lang/String**, handle them separately, but do not conclude from this that every application class can be found with FindClass from any native thread.

Caching a jclass global reference also affects class loader unloading. In plugin/hot-reload systems, there must be a path to **DeleteGlobalRef** and stop native workers before unloading; otherwise, it will keep the class loader alive or leave callbacks pointing to code that has disappeared.

## 10. Thread Safety, Synchronization, and Business Invariants

Having a valid JNIEnv per thread **does not make shared Java data thread-safe**.

For example, a native callback uses **SetIntField** to write to the same field of an object accessed by multiple threads. Even though each thread calls SetIntField through its own JNIEnv and with the right field type, a race condition can still occur. Similarly, two native threads concurrently calling a Java method that mutates an unsynchronized List can leave state inconsistent.

Three levels must be managed:

| Level | Verification Question |
| --- | --- |
| **JNI thread affinity** | Was the JNIEnv in use issued to this exact thread? |
| **JNI reference lifecycle** | Is the jobject/jclass local or global? Is it still valid and not deleted prematurely? |
| **Java data synchronization** | Do threads concurrently reading/writing Java state have appropriate locks, volatile, atomics, or immutable design? |

**JavaVM is not a mutex** and **JNIEnv is not a lock**. They are merely interfaces to perform JNI operations in the proper context.

### Asynchronous Callbacks Need a Shutdown Protocol

If a native library creates long-lived threads:

1. Initialize the VM handle/callback global references before workers start.
2. Workers attach properly, process requests, and clean up local references after each turn.
3. When the application shuts down, stop accepting new work, signal cancellation/termination to workers, and wait for workers to finish.
4. Workers release JNI resources they own, handle callback exceptions, and then detach.
5. The owner deletes global references once certain no worker is using them anymore.
6. Only then allow class loader/native library unloading or the JVM shutdown process to complete.

Do not let g_vm or callback references become dangling pointers just because a thread is configured as daemon. Daemon affects shutdown waiting, **it does not cancel cleanup requirements**.

## 11. Common Mistakes and Direct Causes

| Wrong Pattern | Consequence | Right Approach |
| --- | --- | --- |
| **static JNIEnv *g_env;** and using it on all threads | Uses another thread's JNI interface; can crash | Cache JavaVM, obtain JNIEnv per thread |
| Passing **JNIEnv \*** from a native method to a pthread | JNI pointer leaves its original thread scope | Pass **JavaVM \***; pthread calls GetEnv/Attach |
| Calling **GetEnv** and assuming env always has a value | JNI_EDETACHED returns an invalid env | Check status and attach when needed |
| Treating every GetEnv error as a trigger to Attach | JNI_EVERSION does not mean "unattached" | Distinguish JNI_EDETACHED/JNI_EVERSION |
| Calling **DetachCurrentThread** in a native method called by Java | Java thread still has Java frames; wrong ownership | Do not detach a Java-originated thread |
| Calling attach repeatedly and then detaching unconditionally | May detach a thread owned by the caller/JVM | Track **attached_here** |
| Calling DetachCurrentThread on thread A to clean up thread B | The function only affects the current thread | Worker B detaches itself |
| Using a **local jobject** on a worker after the native call | Local reference is wrong-thread/expired lifetime | NewGlobalRef and DeleteGlobalRef with proper lifecycle |
| Caching a local jclass for later use | Reference expires or is wrong-thread | Global class reference with cleanup |
| Creating many local refs on a long-lived worker | Accumulates handles/GC roots | DeleteLocalRef or local frames |
| Calling **FindClass** for a plugin class from a native worker and assuming it is always found | Different class loader context | Pass Class/callback, cache global ref, or use proper ClassLoader |
| Ignoring pending exceptions in CallVoidMethod | Worker continues JNI in an error state | Check, handle/log/clear intentionally |
| Keeping a non-daemon native worker without shutdown | JVM waits for the thread to finish | Implement stop/join/detach or choose daemon responsibly |
| Using a global reference as a synchronization mechanism | Java state races still occur | Use appropriate lock/volatile/atomic/immutable state |
| Comparing JNIEnv address numbers from two threads to identify threads | Pointer value is not a thread ID contract | Use official thread identity and lifecycle |

## 12. Checklist Before Taking Multithreaded JNI to Production

- [ ] Clearly separated where **JavaVM \*** is held from where **JNIEnv \*** is obtained per current thread.
- [ ] Never store or share JNIEnv across multiple threads; never put JNIEnv into a global queue for native workers.
- [ ] Java-originated native methods use the **env passed by the JVM** and do not detach this thread.
- [ ] Native-created workers call **GetEnv** and handle **JNI_OK/JNI_EDETACHED/JNI_EVERSION** completely.
- [ ] Workers only call **AttachCurrentThread** or **AttachCurrentThreadAsDaemon** when needed; track **attached_here**.
- [ ] Detach runs on the **worker itself**, after callbacks and resource cleanup, before the thread terminates.
- [ ] JNI_OnLoad or GetJavaVM provides a JVM handle managed according to library lifecycle.
- [ ] Asynchronous callbacks receive valid **global references**; never use local refs from another thread.
- [ ] Each worker cleans up local refs/frames and handles pending exceptions within proper scope.
- [ ] The class loader of callbacks/Classes is controlled, especially with plugins/hot reload.
- [ ] Shared Java state has a clear synchronization and memory visibility policy.
- [ ] There is a mechanism to stop/join workers, clean up global refs, and manage native library lifecycle.
- [ ] Tests exist for missing library, attach failure, multiple Java workers calling JNI concurrently, and native worker shutdown.
- [ ] Ran -Xcheck:jni and smoke tests on each supported OS/CPU/ABI/JDK.

## 13. Self-Check Questions

**Question 1.** Can **JavaVM \*** be stored in a global variable for native workers to share?

**Answer:** Yes, if the handle belongs to the current JVM, is properly initialized, and is only used while the VM/library is alive. Each worker uses that JavaVM to obtain or attach **its own JNIEnv**.

**Question 2.** Why must you not store **JNIEnv \*** from Java thread A and send it to pthread B?

**Answer:** JNIEnv is only valid in the thread that received it. B must use JavaVM to call **GetEnv/AttachCurrentThread** to obtain a valid JNIEnv for B.

**Question 3.** Does **GetEnv** automatically attach an unattached native thread?

**Answer:** No. It returns **JNI_EDETACHED** and does not provide a usable JNIEnv; you must call **AttachCurrentThread** or its daemon variant if B needs to use Java/JNI.

**Question 4.** Should a native method called by Java call **DetachCurrentThread** in a finally block?

**Answer:** No. The Java thread is already attached by the JVM and still has Java frames; the native method does not own detaching that thread.

**Question 5.** Does calling AttachCurrentThread on an already attached thread turn that thread into a non-daemon?

**Answer:** No. On an already attached thread, it returns the existing JNIEnv and does not change the current daemon status.

**Question 6.** To call a Java Runnable from a native worker after the initial native method returns, what is needed?

**Answer:** A valid JavaVM, the worker's attached JNIEnv, a valid **global reference** to the Runnable, callback via thread-appropriate JNI APIs, exception handling, reference cleanup, and detaching according to ownership.

**Question 7.** Calling **GetEnv** returns **JNI_EVERSION**. Should you treat it as JNI_EDETACHED and attach immediately?

**Answer:** No. JNI_EVERSION says the requested JNI version is not supported. You must fix the version/contract first, and not proceed with an invalid env.

**Question 8.** Why does **FindClass** find a plugin class in a JNI method, yet may fail to find it from a native pthread?

**Answer:** A self-attached native pthread does not necessarily have the class loader context of the Java caller/plugin. You need to provide the Class/callback in the right context, use a global ref, or use a managed class loader.

**Question 9.** Can two threads that already have valid JNIEnvs concurrently write to a Java field without synchronization?

**Answer:** The thread-appropriate JNIEnv rule does not guarantee data safety. Java state operations must still use synchronization, atomics, or an appropriate data model.

## Official References

- [Oracle JNI Specification — Invocation API: Attaching, Detaching, GetEnv, daemon threads, and JNI_OnLoad](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html).
- [Oracle JNI Specification — Design Overview: JNI interface pointer and local/global reference rules](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle JNI Specification — JNI Functions: GetJavaVM, FindClass, and reference management](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [Oracle javac — generating native headers with javac -h](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).

**Core takeaway:** **JavaVM is the JVM access gateway that can be shared within a valid lifecycle; JNIEnv is the JNI environment valid only for the thread that owns it**. Java threads calling native code are already attached and receive env automatically. Native-created threads must obtain their own env via GetEnv/AttachCurrentThread, manage references/callbacks properly, and detach when finished. Distinguishing these two levels is the foundation for safe multithreaded JNI operation.

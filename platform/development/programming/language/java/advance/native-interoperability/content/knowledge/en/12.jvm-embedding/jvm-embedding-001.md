# When Does a C/C++ Application Need to Create a JVM Instead of Being Called by Java?

## Learning Objectives

An application can combine Java and C/C++ in two different directions: **Java starts first and calls native code**, or **a C/C++ application starts first and creates a Java Virtual Machine (JVM) itself to execute Java code**. Both directions can use the Java Native Interface (JNI), but they differ in **process ownership, JVM creation timing, runtime configuration, thread management, error handling, and operations**.

After this lesson, you will be able to:

1. Identify the right time to **embed a JVM (embedded JVM)** into a C/C++ application using the **JNI Invocation API**.
2. Distinguish the **Java → native (JNI or Foreign Function & Memory API)** direction from the **native host → JVM → Java** direction.
3. Use the core APIs **JNI_CreateJavaVM**, **JavaVMInitArgs**, **JavaVMOption**, **JNIEnv**, **JavaVM**, and **DestroyJavaVM** in their proper roles.
4. Evaluate startup cost, resources, stability, portability, packaging, class loaders, and application lifecycle before choosing an architecture.
5. Compile a **Java 17+ and C** example: a C program creates a JVM, finds a Java class, calls a static method, and terminates the JVM in a controlled manner.
6. Recognize design anti-patterns: creating a JVM per request, attempting to create multiple JVMs in the same process, forgetting to attach a native thread, calling JNI with an expired local reference, and shutting down while non-daemon threads still exist.

## 1. Where Do the Two Integration Directions Differ?

First, it is necessary to determine **who owns the process and who calls whom**.

### Direction A — Java Is the Main Application, Java Calls a C/C++ Library

~~~text
[OS launches java / Java service]
                |
                v
              [JVM]
                |
           Java code
                |
        JNI / FFM API
                |
                v
        [C/C++ native library]
~~~

The Java host typically has a **main()** written in Java, or is started by a container such as a Java application server. The JVM already exists. When it needs to access a C API, driver, codec, or acceleration library, Java calls down into native code. A JNI native method automatically receives **JNIEnv \*** from the JVM; there is no need to call **JNI_CreateJavaVM** itself.

Example of Java calling native (only a skeleton, requires a library with an actual implementation):

~~~java
public final class JavaOwnsProcess {
    static {
        System.loadLibrary("native_math");
    }

    private static native int nativeMultiply(int a, int b);

    public static void main(String[] args) {
        System.out.println(nativeMultiply(6, 7));
    }
}
~~~

This is a **structural snippet**, and cannot run standalone because the **native_math** binary and JNI implementation are not provided yet. In this direction, **Java is the lifecycle coordinator**; the C/C++ library only provides functionality upon Java calls. If the C side wants to call back into Java within the same call, it already has the JNIEnv of the current Java thread.

### Direction B — C/C++ Is the Main Application, the Native Host Creates the JVM

~~~text
[OS launches C/C++ executable]
                  |
             native host
                  |
          JNI_CreateJavaVM()
                  |
                  v
              [JVM resides
          in the same process]
                  |
       JNI FindClass / Call...
                  |
               Java code
                  |
         returns result to C/C++
~~~

The **C/C++ application decides when Java is needed**, creates the JVM via the **Invocation API**, receives the **JavaVM \*** and the **JNIEnv \*** of the initializing thread, and then calls Java code via JNI. The JVM is loaded into the **same process**. The JVM does not spawn a separate Java process just because JNI_CreateJavaVM is called.

Typical example: a legacy C++ desktop application that has a business module written in Java; the product must keep the **C++ main loop, UI, or engine** as the entry point and needs to run some Java components inside that process.

**Important rule:** If the JVM is already running and a native method is **called by Java**, do not create a second JVM to "call back into Java". The native method already receives JNIEnv and can use the existing JVM directly. If a native worker thread needs to call Java later, it must obtain the **JNIEnv for the worker** using JavaVM/GetEnv/AttachCurrentThread, not create a new VM.

## 2. When Should C/C++ Proactively Create a JVM?

Treat embedding as an **architectural decision**, rather than just an API choice.

### 2.1. The Native Host Must Control the Product Lifecycle

Example: a C++ application already has **main()**, an event loop, a user interface, a simulation loop, or a native task pipeline. Switching the entire entry point to Java is very costly or does not fit distribution requirements. Yet a Java component is genuinely required for product functionality.

Embedding the JVM allows keeping the native host as the **process owner**, while calling the Java component through an adapter with a clear contract.

This decision is appropriate if the native host truly needs to:

- Coordinate the product's **startup/shutdown** and choose when the Java component is active.
- Reuse a complex Java library or an already stable module, instead of rewriting it in C/C++.
- Maintain the lifecycle, configuration, or native integration points that the organization already owns.
- Accept the JVM as a dependency and a runtime living in the same process.

### 2.2. There Is a Java Component That Native Code Must Call Directly and Frequently

A Java library may provide a rules engine, data formatter, algorithm, or module that interacts with the Java ecosystem. If the native host continuously calls these APIs and the call model is fairly small, keeping a JVM in-process can avoid some costs of **starting a separate process and IPC/serialization**.

However, **JNI crossing still has overhead**: type conversion, data copying, reference management, method/field lookup, and thread synchronization. You should not choose embedding just because of an assumption that "in-process is always faster"; you must benchmark the actual workload.

### 2.3. A Native Product Needs a Java-Based Extension Mechanism

Example: an application has a C++ core, while third parties provide Java plugins. The host can initialize the JVM once, load plugins through a **class loader** designed for the system, and call clearly versioned entry points.

This architecture only makes sense if there is a plan to:

- Manage **class loaders**, dependencies, versions, and plugin lifecycles.
- Restrict the communication API and plugin permissions; do not treat the traditional Java sandbox as a complete security measure.
- Load/unload plugins without assuming the JVM can be created/destroyed arbitrarily many times.
- Block or isolate untrusted extensions when process safety is a critical requirement.

### 2.4. The Startup Mechanism of the Integrated System Cannot Be Changed

Some native hosts are loaded by specialized environments: CAD software, graphics software, hardware devices, or industrial software with a C/C++ plugin SDK. The host always starts in its own way, but the plugin needs a Java component.

When **the host actually allows embedding a JVM** and resources/dependencies are controlled, the Invocation API can serve as the bridge. Before choosing it, you must verify that the host does not already have a JVM, as well as the shared library loading policy, threads/stacks, class loaders, JDK distribution, and permission to initialize a runtime in the process. If the plugin runs inside an application that already has a JVM, prefer using the existing JVM through the host's mechanism.

## 3. When Should Java Call C/C++ Instead?

The following cases generally fit the **Java host → native** direction better:

| Context | Usually Appropriate Direction | Reason |
| --- | --- | --- |
| A Java/Spring service is running and needs a C library for acceleration | Java calls JNI/FFM | The JVM already exists; Java coordinates the service, lifecycle, and configuration |
| A Java application needs a driver, codec, or OS API | Java calls native | Native is a supporting capability of the Java application |
| A Java application is required to ship with a known JDK/runtime | Java calls native | Eliminates an extra VM bootstrap layer self-managed by C |
| A C++ application coordinates a GUI/engine and only needs a Java rules engine | C/C++ embeds JVM or uses a separate Java service | The native host is an unchangeable entry point |
| A C++ host uses a Java module very rarely, independently, and crashes must be isolated | Separate Java **process** via IPC | Fault isolation and independent scaling/deployment may outweigh IPC overhead |
| A small C program only wants to call a simple calculation that already has a C library | Pure C | Not worth bringing along a JVM just for a feature that has a simple native alternative |

If the software is primarily written in Java and uses native code as an **implementation detail**, creating a JVM from C usually adds unnecessary responsibilities: choosing Java home, memory, GC, classpath/module path, lifecycle, and packaging.

Conversely, if the native host is the primary component and Java is only a module that needs to be called, embedding can make sense.

## 4. Embedding the JVM vs. Running Java in a Separate Process

A C/C++ application **does not have to embed a JVM** just to use a Java library. It can launch a separate Java process and communicate over stdin/stdout, pipes, sockets, HTTP/gRPC, or an IPC protocol.

| Criterion | Embedded JVM **in the same process** | Java running in a **separate process** |
| --- | --- | --- |
| Who launches the Java runtime? | Native host calls **JNI_CreateJavaVM** | Native host/OS launches **java** or a Java service |
| Communication | JNI, shared address space | IPC/network protocol |
| Latency per call | Can be lower when calling small APIs with normalized data | Has additional serialization, context switching, or network overhead |
| JVM/native crash | Can bring down the **same process** | Has a separate fault boundary; can restart the Java worker |
| Heap/GC management | JVM shares process resources | Java heap belongs to a separate process; monitoring is easy to separate |
| Deployment/upgrade | Native host must carry VM libraries and binaries matching OS/ABI | Can update the Java service independently |
| Security isolation | No process boundary exists | Can apply OS user, sandbox, container, and quotas |
| Class loading | Host must manage JVM/classloaders | Java process organizes classpath/modules itself |
| Debugging | C/C++ + JVM in one process; mixed stacks | Logs/tracing between two processes |
| Shutdown | Native host must coordinate **DestroyJavaVM** and Java threads | Manage Java process lifecycle, health checks, and signals |

Do not view embedding as "zero data copy": JNI may still require **marshalling**, String conversion, memory allocation, or reference creation. Nor should you view a separate process as "always slow"; with sufficiently large requests, batch APIs, or production isolation requirements, IPC can be the better option.

**Decision hint:** If the primary goal is **fault isolation for untrusted plugins**, a **separate Java process** is usually worth considering. If the native host needs deep system control and calls a trusted Java component very frequently, embedding is worth benchmarking.

## 5. Invocation API: How Does Creating a VM Differ from a JNI Native Method?

The JNI Specification divides functionality into two related parts:

1. **JNI functions** called through **JNIEnv \*** to manipulate objects, classes, fields, methods, and exceptions.
2. **Invocation API** for a native application to create and manage a VM, including **JNI_CreateJavaVM**, **DestroyJavaVM**, **GetEnv**, **AttachCurrentThread**, etc.

### Core Data Types

~~~c
JavaVM *jvm = NULL;
JNIEnv *env = NULL;

JavaVMOption options[1];
JavaVMInitArgs args;
~~~

- **JavaVM \***: handle to the JVM, used to request attach/detach and VM lifecycle operations.
- **JNIEnv \***: JNI interface valid **only for the current thread**; used to call FindClass, GetStaticMethodID, CallStaticIntMethod, etc.
- **JavaVMOption**: each JVM configuration option is represented by **optionString** (and extraInfo for special cases).
- **JavaVMInitArgs**: desired JNI version, list of options, and rule for handling unrecognized options.

Minimal configuration example:

~~~c
JavaVMOption options[1];
options[0].optionString = "-Djava.class.path=.";
options[0].extraInfo = NULL;

JavaVMInitArgs args;
args.version = JNI_VERSION_1_8;
args.nOptions = 1;
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;
~~~

Explanation:

- **-Djava.class.path=.** makes the classpath include the current working directory; suitable for a demo with `.class` files there. In production, use absolute paths or controlled packaging.
- **JNI_VERSION_1_8** requests JNI interface version 1.8; it does not mean Java code is limited to Java 8. JDK 17+ still supports this JNI interface.
- **JNI_FALSE** causes failure when encountering an unrecognized option instead of silently ignoring it; specific behavior also depends on the Invocation API specification and VM version.
- Performance parameters such as heap size, GC, module options, and system properties must be determined according to the **actual JDK used in deployment**. Do not copy options from a different JDK without testing.

### The JVM Creation Call

~~~c
jint status = JNI_CreateJavaVM(
    &jvm,
    (void **)&env,
    &args
);
~~~

If **status == JNI_OK**, the JVM has initialized successfully, and **env is the JNIEnv of the exact thread that called JNI_CreateJavaVM**. This thread is considered the **main thread of the JVM** under the Invocation API.

If status is not JNI_OK, do not call FindClass or other JNI functions with an invalid env. Log the error code, and check libjvm dependencies, runtime options, resource limits, and JNI version.

VM-level JNI errors may be represented by **JNI_ERR, JNI_EVERSION, JNI_ENOMEM, JNI_EEXIST, or JNI_EINVAL** depending on the situation/implementation. Do not assume a specific negative code always points to a single cause.

## 6. What Does a C Program Calling a JVM Need to Prepare?

### 6.1. JDK/JVM Binary Matching the Native Host

The C/C++ application must **link or dynamically load the VM library** of the corresponding JDK/Java runtime, for example **libjvm.so**, **libjvm.dylib**, or **jvm.dll** on common platforms. Having only Java source/JAR files is not enough to embed the runtime.

You need to control:

- **OS/CPU architecture and ABI:** a 64-bit C executable needs a compatible JVM binary matching the OS and architecture.
- **Dependent libraries:** the OS loader must be able to find libjvm and its transitive dependencies.
- **Version/JDK distribution:** configuration, flags, Java APIs, and runtime policies must be tested on the release version.
- **Deployment process:** the native executable, JVM runtime, Java classes/JARs, libraries, and configuration travel together in a verified artifact/deployment area.
- **Process resources:** heap, native memory, thread stacks, JVM code cache, GC, JIT, and the native host share the memory limit of a single process.

When embedding a VM, the product becomes a **product distributing an entire Java runtime**, unless the deployment environment already provides and commits to supporting the runtime. You must review JDK/runtime distribution terms and vendor security updates.

### 6.2. Classpath and Module Path

To call **FindClass("com/example/Engine")**, the JVM must see this class according to the **class loader context** at lookup time. For a packageless example, the **-Djava.class.path=.** option allows FindClass("EmbeddedRule") to find the class in the current directory.

In production, determine:

- Does the class belong on the **classpath** or the module path?
- Which modules does the host need; are **--module-path** and **--add-modules** declared accordingly?
- Are the Java component's dependencies supplied with the right version/path?
- Is there a custom plugin class loader? If so, FindClass from a native thread may not resolve the class in the context you expect.
- Do relative paths change meaning when the service runs from a different working directory?

A common deployment issue is that **native code creates the VM successfully** but **FindClass** does not find the Java class because of a wrong classpath. This is a class loading error, not evidence that JNI_CreateJavaVM failed.

### 6.3. Choose a Single Place to Manage the VM

The application should have a **VM manager** at the native host boundary, responsible for:

1. Initializing the VM **once**.
2. Holding `JavaVM *` and necessary handles.
3. Providing a Java invocation API for native workers using **each thread's own JNIEnv**.
4. Tracking initialized, ready, stopping, stopped states and bootstrap errors.
5. Blocking new requests, finishing callbacks/workers, cleaning up references, and then shutting down.

Avoid letting each C module call JNI_CreateJavaVM on its own. **The JNI Specification does not support creating multiple JVMs in the same process**. **JNI_GetCreatedJavaVMs** can query already created VMs, but finding a VM does not automatically grant lifecycle ownership or resolve class loader/ownership issues; the host must still have a protocol for who owns the VM.

## 7. Complete Example: C Host Creates a JVM and Calls Java 17+

This example is intentionally small, has deterministic output, and does not require a separate JNI library containing native methods. **The native executable is the main program**, linking to **libjvm** to create the VM; it then calls a Java static method using JNI.

Runs on **JDK 17+**, with a C compiler and the target JDK's JNI headers.

### Step 1 — Create EmbeddedRule.java

~~~java
public final class EmbeddedRule {
    private EmbeddedRule() {
    }

    public static int calculate(int units) {
        if (units < 0) {
            throw new IllegalArgumentException("units must be nonnegative");
        }
        return units * 3 + 7;
    }
}
~~~

The method has JVM signature **(I)I**, meaning it takes one **int** and returns one **int**. The demo calls **calculate(5)**, so the result is **5 × 3 + 7 = 22**. This is a complete Java class, **declaring no native methods** because the call direction is C → Java.

Compile from the directory containing the file:

~~~bash
javac EmbeddedRule.java
~~~

When running the C host later, the working directory must contain **EmbeddedRule.class**, because the demo JVM uses **-Djava.class.path=.**.

### Step 2 — Create embed_host.c

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

/* Diagnose Java exception before destroying the JVM. */
static void report_java_exception(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env); /* Print details to stderr. */
        (*env)->ExceptionClear(env);
    }
}

int main(void) {
    JavaVM *jvm = NULL;
    JNIEnv *env = NULL;
    jclass rule_class = NULL;
    jmethodID method = NULL;
    jint result = 0;
    int exit_code = EXIT_FAILURE;

    JavaVMOption options[1];
    options[0].optionString = "-Djava.class.path=.";
    options[0].extraInfo = NULL;

    JavaVMInitArgs args;
    args.version = JNI_VERSION_1_8;
    args.nOptions = 1;
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    /* C executable creates the JVM itself in the same process. */
    jint create_status = JNI_CreateJavaVM(
        &jvm, (void **)&env, &args
    );
    if (create_status != JNI_OK || jvm == NULL || env == NULL) {
        fprintf(stderr, "Cannot create JVM: %d\n", create_status);
        return EXIT_FAILURE;
    }

    puts("C host: JVM started");

    /* Class is in the configured "." classpath. */
    rule_class = (*env)->FindClass(env, "EmbeddedRule");
    if (rule_class == NULL) {
        goto shutdown;
    }

    method = (*env)->GetStaticMethodID(
        env, rule_class, "calculate", "(I)I"
    );
    if (method == NULL) {
        goto shutdown;
    }

    /* Call the Java method directly in the created JVM. */
    result = (*env)->CallStaticIntMethod(
        env, rule_class, method, (jint)5
    );
    if ((*env)->ExceptionCheck(env)) {
        goto shutdown;
    }

    printf("C host: Java returned %d\n", (int)result);
    exit_code = EXIT_SUCCESS;

shutdown:
    /* Preserve exception details on stderr then clean up before shutdown. */
    report_java_exception(env);

    if (rule_class != NULL) {
        (*env)->DeleteLocalRef(env, rule_class);
    }

    /* Do not use env or jvm after DestroyJavaVM succeeds. */
    jint destroy_status = (*jvm)->DestroyJavaVM(jvm);
    if (destroy_status != JNI_OK) {
        fprintf(stderr, "Cannot destroy JVM: %d\n", destroy_status);
        return EXIT_FAILURE;
    }

    if (exit_code == EXIT_SUCCESS) {
        puts("C host: JVM stopped");
    }
    return exit_code;
}
~~~

### Step 3 — Compile the C Executable Linking libjvm

**Linux (GCC, x86-64 or ARM64 matching the JVM):**

~~~bash
gcc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /nologo /W4 /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" embed_host.c /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embed_host.exe
~~~

On Windows, at runtime make sure the OS can find **jvm.dll** of the right JDK (usually in **%JAVA_HOME%\bin\server** for common JDKs). For example in **Command Prompt**:

~~~bat
set "PATH=%JAVA_HOME%\bin\server;%PATH%"
embed_host.exe
~~~

The build commands assume **JAVA_HOME** is configured properly and the machine has the corresponding toolchain. Build separately for each OS/CPU/ABI; do not use an executable or libjvm from a different operating system.

**Why does the build need -I and -L?** The two include paths help the compiler find **jni.h** and platform-dependent JNI declarations. The `lib/server` path helps the linker find **libjvm**, while **rpath** in the Linux/macOS examples helps the dynamic loader find libjvm at runtime. For production, you should not hardcode build-machine paths into a widely distributed binary; design appropriate runtime paths, packaging, and patching.

### Step 4 — Run from the Right Directory

**Linux/macOS:**

~~~bash
./embed_host
~~~

**Windows:** run **embed_host.exe** after configuring PATH in Command Prompt.

**Exact stdout output** in a build environment where loading succeeds, with no extra logging/VM options:

~~~text
C host: JVM started
C host: Java returned 22
C host: JVM stopped
~~~

In the example, **Java does not create a native library to call down into C**. The C executable itself creates the JVM, uses JNIEnv to look up the class/method and call Java, and then requests shutdown.

### Execution Flow Analysis

1. **C main()** starts before any Java method.
2. **JavaVMOption** specifies the location of Java classes via the classpath.
3. **JNI_CreateJavaVM** loads/initializes the VM and attaches the current thread, returning both JavaVM and JNIEnv.
4. **FindClass** locates EmbeddedRule, and **GetStaticMethodID** locates the method with descriptor **(I)I**.
5. **CallStaticIntMethod** runs the Java code and receives **jint 22**.
6. **ExceptionCheck** prevents C code from treating a Java exception as a valid result.
7. **DeleteLocalRef** cleans up the reference to the Class in native code.
8. **DestroyJavaVM** requests VM termination; upon success, the native host continues and prints the stop message.

**Native build has not been executed in this document's environment**: the code and output above are samples conditioned on success and must be compiled/run on the target toolchain/JDK to verify integration and the actual libjvm path.

## 8. Why Does the Demo Need to Check for Java Exceptions?

From C, calling a Java method can fail due to **class not found**, **method descriptor mismatch**, **an exception in the Java body**, class initialization errors, or resource errors.

Examples:

- If **EmbeddedRule.class** is not on the classpath, **FindClass** can return NULL with a pending Java exception.
- If the Java method is changed from **calculate(int)** to **calculate(long)** while C still looks up **(I)I**, **GetStaticMethodID** will fail to find the matching method.
- If **calculate(-1)** is called, Java code throws **IllegalArgumentException**. C needs to detect the pending exception after **CallStaticIntMethod**, rather than using an arbitrary return value as a valid result.

**ExceptionDescribe** writes error details to stderr for diagnosis, while **ExceptionClear** clears the pending state. The demo code does this before calling DestroyJavaVM. In production, you must have a strategy to translate errors into error codes, log with a correlation ID, or return errors via the native host API; never silently swallow exceptions.

You should not call regular JNI APIs in sequence while a **pending exception** has not been handled. Some cleanup APIs such as **DeleteLocalRef** are allowed while an exception is pending, but the cleanest approach is to check for errors after operations that can fail and use a consistent cleanup branch.

## 9. Special Pitfalls of the Embedded JVM Lifecycle

### 9.1. Do Not Create a JVM per Request

Initializing a JVM is expensive: loading runtime libraries, initializing classloaders, heap, GC, JIT, runtime threads, and the called Java classes. A JVM is not like a function object that can be quickly created and destroyed on every request.

**Wrong architecture:**

~~~text
for each incoming C request:
    JNI_CreateJavaVM()
    call Java once
    DestroyJavaVM()
~~~

Consequences: high latency, growing/fluctuating resources, hard-to-control shutdown, and the risk of relying on an unsupported assumption of recreating a VM in the same process. For products that need to handle many requests, **initialize the VM once and reuse it in a controlled manner** or use a long-lived **Java worker process**.

### 9.2. Do Not Rely on Multiple JVMs in the Same Process

According to the JNI Specification, **creating multiple JVMs in the same process is not supported**. A native plugin cannot guarantee opening a second JVM alongside an existing VM in a "one VM per plugin" setup.

**JNI_GetCreatedJavaVMs** allows listing already created JVMs per API capability; it can help detect an existing VM. However, do not treat this API as a registry with ownership, permission, or classloader isolation features. If the product may already run inside a host with a JVM, it must coordinate lifecycle with that host or separate into another process.

### 9.3. Do Not Assume DestroyJavaVM Is a Restart

**DestroyJavaVM** is a request to terminate the VM, **not a lightweight reset to immediately create a VM again afterward**. The design should not require multiple **create → destroy → create** cycles in the same native process. A separate process is needed if the product wants reliable Java runtime restarts.

If the JVM or a JNI library has already corrupted native memory, catching a Java exception and calling DestroyJavaVM is also not a crash recovery mechanism.

### 9.4. DestroyJavaVM May Have to Wait for Live Java/Native Threads

Per the Invocation API, DestroyJavaVM waits for **non-daemon threads** to become inactive (with rules regarding the current thread) before proceeding with shutdown. This includes Java threads and native threads attached as non-daemon. If workers or thread pools keep running and do not stop, the native host can hang at the shutdown step.

Therefore:

1. Stop accepting new work.
2. Signal Java executors and native workers to stop.
3. Wait for tasks to complete with a timeout according to product policy.
4. Ensure native-created threads call **DetachCurrentThread** before exiting.
5. Delete global JNI references/caches when no longer needed.
6. Only then call DestroyJavaVM and handle the returned status.

Java libraries can create unexpected background threads; inspect thread dumps and logs if DestroyJavaVM waits for a long time.

### 9.5. The Thread Calling JNI_CreateJavaVM Is the JVM Main Thread

The native thread that executes **JNI_CreateJavaVM** is attached as the **JVM main thread** and receives its JNIEnv. In the demo code, that is the C main thread. However, the JNI Specification notes that some operating systems treat the **primordial process thread** unusually, such as stack restrictions causing StackOverflowError risks. For production hosts, consider creating **a dedicated native thread for initializing the JVM** with sufficient stack size, if it fits the design.

Do not, because of this, pass the JNIEnv returned to that dedicated thread to another C thread. **JNIEnv belongs only to the thread that received it**. Other native workers must call GetEnv/AttachCurrentThread to get their own env.

## 10. Native Threads When the JVM Is Created by C

Suppose the C host has its own thread pool and workers want to call Java. **JavaVM \*** can be shared within its valid lifecycle, but **JNIEnv \*** must not be shared across threads.

C helper pattern:

~~~c
/*
 * Snippet: used in a native worker that received a valid JavaVM*.
 * Only illustrates obtaining JNIEnv and detach ownership.
 */
static int get_env_for_worker(
        JavaVM *vm, JNIEnv **out_env, int *attached_here) {
    *out_env = NULL;
    *attached_here = 0;

    jint status = (*vm)->GetEnv(
        vm, (void **)out_env, JNI_VERSION_1_8
    );

    if (status == JNI_OK) {
        return 1; /* Worker is already attached. */
    }

    if (status != JNI_EDETACHED) {
        return 0; /* Possibly JNI_EVERSION. */
    }

    if ((*vm)->AttachCurrentThread(
            vm, (void **)out_env, NULL) != JNI_OK) {
        return 0;
    }

    *attached_here = 1;
    return 1;
}
~~~

When the worker finishes Java calls, if **attached_here == 1**, it calls **DetachCurrentThread** **on that same worker thread**. If GetEnv returned JNI_OK initially, the worker should not detach a thread attached by the JVM or another component that it does not own.

Do not store the JNIEnv of the JVM-initializing thread in a global variable for workers to use. Passing **JavaVM \*** is right, while JNIEnv must be obtained **per current thread**.

### Local/Global References

JNI **jobject**, **jclass**, and **jstring local references** of one thread are not automatically valid on another native thread or after the JNI call/frame ends. For Java objects that need to live across multiple callbacks from workers, create a **NewGlobalRef** on a validly attached thread and release it with **DeleteGlobalRef** when truly no longer needed.

A global reference does not make an object thread-safe; if multiple workers mutate Java state concurrently, locks, volatile, atomics, or an appropriate immutable design are still required.

### Class Loader of a Native Worker

A native thread that attaches itself does not necessarily have the class loader context of a Java plugin. **FindClass** called from a thread with no associated Java native-method frame may use a default class loader different from the context that loaded the plugin. If you need to call an application class from a custom class loader, obtain the **Class**, **ClassLoader**, or callback object from the Java side in the right context and hold a controlled reference.

Avoid assuming that just because FindClass works in a Java-originated native method, it works identically on every native thread of the C host.

## 11. Managing Observability and Operations of an Embedded JVM

Embedding causes the VM and native host to share a process, so diagnosis requires observing both sides:

| Category | What to Monitor |
| --- | --- |
| **Startup** | JDK distribution/version, VM options, java.class.path, module configuration, JNI_CreateJavaVM status |
| **Native loader** | libjvm location, dependencies, OS/CPU/ABI, dynamic linker error codes |
| **Java component** | Class/Method lookup, exception message/stack, Java call duration, properly lifecycle-managed cached method IDs |
| **Threads** | Attached native threads, Java non-daemon workers, thread leaks, shutdown blockers |
| **Memory** | Heap, off-heap/native allocations, **whole-process** RSS, stacks, GC, JIT/code cache |
| **Release** | Native host version, JVM runtime, Java classes/JARs, binary checksums, rollback, and CVEs |
| **Crashes** | JVM crash log, native core dump, Java stack + corresponding native stack/symbols |

**Do not assume Java heap metrics describe total memory usage.** When the JVM lives inside a C++ host with a large native engine, both C++ and JVM memory contribute to RSS and container/process limits.

For production, consider designing a **health check**:

- Has the JVM been created?
- Can the target class be found?
- Does the method signature match?
- Does a safe invocation return the right result?
- Are worker threads/callbacks functioning and able to shut down?

A **successful JNI_CreateJavaVM** does not guarantee the Java library is usable. Similarly, a **successful FindClass** does not guarantee class initialization or method calls will not fail.

### Shutdown and System.exit

Java code running inside an embedded JVM can still call **System.exit** or an API that triggers process shutdown. This is why a contract between the host and the Java component must be defined: normally the embedded Java component **does not independently control terminating the entire process**.

Do not build a system on the assumption that calling System.exit in Java only "shuts down the Java plugin" while keeping the C++ host normal. When process control isolation is needed, a separate Java process is architecturally safer.

## 12. Testing the Architecture Before Choosing Embedding

Design tests to validate the rationale for choosing the architecture:

1. **Baseline:** compare a C-native implementation, an embedded JVM, and a Java child process under the same workload/semantics if all options are viable.
2. **Startup time:** measure libjvm loading, VM initialization, class loading, and warm-up before the first request.
3. **Per-call latency:** measure crossing, lookup, data conversion, GC, p50/p95/p99, batch size, and concurrency—not just the Java method body.
4. **Memory:** measure whole-process RSS, Java heap, native allocations, code cache, thread stacks, and startup spikes.
5. **Failure injection:** missing classpath/JDK, wrong libjvm, changed method signature, Java exceptions, and native crashes in a test environment.
6. **Concurrency:** native worker attach/detach, per-thread JNIEnv, local/global references, and class loaders.
7. **Shutdown:** with Java thread pools/non-daemon threads, in-flight callbacks, and running native workers; measure stop/destroy capability.
8. **Distribution:** run on each target OS/architecture/ABI/JDK, including actual containers and transitive dependencies.
9. **Upgrade/rollback:** test Java components and JVM binaries across a version matrix, enabling full-package rollback.
10. **Security:** verify JDK source/patches, native library permissions, and trusted data boundaries. When running untrusted Java code, evaluate process isolation.

If **crash isolation** and version independence are dominant requirements, evaluation results may favor a child Java process even if IPC is slower in some microbenchmarks.

## 13. Common Conceptual and Implementation Mistakes

| Mistake | Why It Is Wrong | Solution |
| --- | --- | --- |
| "Using JNI means C must create a JVM itself" | When Java calls native, the JVM already exists and passes JNIEnv | Use the existing JNIEnv; only embed the VM when the native host owns the entry point |
| "Create a JVM per request to avoid stale state" | Startup is expensive; multiple/recreating VMs in one process is not supported as expected | One long-lived VM or a Java worker process |
| "A C++ host can create multiple JVMs, one per plugin" | The JNI spec does not support multiple VMs in the same process | One VM with controlled class loaders/lifecycle or multiple processes |
| "JNI_CreateJavaVM creates a separate Java process" | The JVM is loaded in the **same process** | Use IPC/process spawning if a process boundary is needed |
| "Having JavaVM means FindClass can be called immediately on any native thread" | FindClass is a JNIEnv function; the thread must be attached | GetEnv/AttachCurrentThread and obtain a thread-specific JNIEnv |
| "Have one global JNIEnv for all workers" | JNIEnv is thread-specific | Store JavaVM; obtain JNIEnv on the current thread |
| "C only needs to find libjvm and the Java class will work automatically" | Still need classpath, dependencies, method signatures, and initialization | Full health check and integration smoke tests |
| "DestroyJavaVM always returns immediately" | Must coordinate non-daemon threads and the shutdown sequence | Stop/join/detach before destroying |
| "After destroying, it can be easily recreated" | No reliable VM restart contract within a single process | Restart the native process or worker process |
| "An embedded JVM does not use significant extra RAM" | Heap, native memory, JIT, GC, and thread stacks all share the process | Set a resource budget and measure RSS |
| "C can pass JNIEnv to a pthread" | The JNIEnv pointer is invalid on another thread | Share JavaVM and attach each worker separately |
| "A Java plugin can call System.exit without affecting the C++ host" | The Java runtime lives in the same process | Establish a shutdown contract; isolate the process if needed |
| "A single JNI call is fast so embedding is definitely better than IPC" | Ignores startup, marshalling, memory, and incident costs | Benchmark end-to-end and factor in operational costs |

## 14. Quick Decision Checklist

Before **C/C++ creates a JVM itself**, answer these questions:

- [ ] Is C/C++ **truly the unchangeable entry point** of the product?
- [ ] Is the Java component valuable enough to justify packaging/operating an entire JVM in-process?
- [ ] Is there already a JVM running in the host? If so, has a mechanism to use the existing VM been identified?
- [ ] Have JNI embedding and a Java child process/IPC been compared on latency, isolation, versioning, and deployment?
- [ ] Has a single owner been designated for **JNI_CreateJavaVM**, **JavaVM \***, and **DestroyJavaVM**?
- [ ] Is there a plan to configure **classpath/module path, heap, GC, and JVM options** for the target JDK?
- [ ] Can the native executable locate the right **libjvm** and its dependencies on each OS/ABI?
- [ ] Are **FindClass/GetMethodID/call** checked and Java exceptions handled in the right branches?
- [ ] If using multiple native threads, does each worker obtain its own JNIEnv, attach/detach, and clean up properly by lifecycle?
- [ ] Are classloader rules, local/global reference ownership, and synchronization defined?
- [ ] Is there a shutdown policy for Java non-daemon threads, executors, callbacks, and native workers?
- [ ] Does the design avoid relying on multiple JVMs or create/destroy/recreate cycles in the same process?
- [ ] Have startup, RSS, p95 latency, GC, crash behavior, and rollback capability been measured in a real environment?
- [ ] Does the Java component avoid calling System.exit and taking process control away from the host?

If these conditions are not met, **do not embed a JVM yet** just because there is a Java library to use; re-evaluate the process boundary or entry point organization.

## 15. Self-Check Questions

**1. A Java server is already running and a JNI native method needs to call another Java method. Is JNI_CreateJavaVM needed?**

**Answer:** No. The JVM already exists; the native method receives the **JNIEnv of the current thread** and can use the JNI API to call Java in the same JVM. If a native thread created by C wants to call Java, it needs to attach to the existing JVM.

**2. A C++ application owns the UI and main loop, but a business algorithm only exists in Java. Should embedding be considered?**

**Answer:** Yes. When the native host must keep the entry point and the Java component needs to be called directly, the JNI Invocation API is an option. However, compare it against a separate Java process in terms of latency, crash isolation, maintenance, startup, and packaging.

**3. What does JNI_CreateJavaVM return on success?**

**Answer:** A **JavaVM \*** for VM-level operations and a valid **JNIEnv \*** for the **thread that called VM creation**, along with status code **JNI_OK**. That JNIEnv must not be used on another thread.

**4. Why should a JVM not be created on every request?**

**Answer:** JVM startup is resource-intensive and there is no reliable contract for creating multiple/recreating VMs in one process. Maintain a single long-lived managed VM or use a Java worker process if restarts/isolation are needed.

**5. If JNI_CreateJavaVM succeeds but FindClass fails, what should be investigated?**

**Answer:** Classpath/module path, working directory, dependencies/class loader, JNI-style class name (**/** instead of **.**), and pending Java exceptions. This is not necessarily a VM initialization error.

**6. When the host calls DestroyJavaVM and it blocks for a long time, what could be the cause?**

**Answer:** Java non-daemon threads or native threads attached as non-daemon have not stopped; shutdown hooks/cleanup may be taking a long time. Proper lifecycle stop/join/detach is needed.

**7. Why does an embedded JVM not provide crash isolation?**

**Answer:** The native host and JVM share the **same process**. A C/JNI bug or a severe runtime crash can bring down the entire application. Only a separate Java process creates a useful process boundary.

**8. Can a JNI local reference obtained from the JVM-creating thread be passed to a C worker thread and used?**

**Answer:** No. A **global reference** is needed if the object must be shared across threads/calls and the worker must have its **own JNIEnv**; the owner must delete the global ref when it is no longer needed.

**9. In the example, does the JVM have to run a Java main()?**

**Answer:** No. The C host uses **FindClass** and **GetStaticMethodID** to directly call the Java static method **calculate(int)**. The JVM only needs to be created and able to see the class.

**10. When might a child Java process be better than embedding despite IPC?**

**Answer:** When crash/memory isolation, independent Java upgrades, permission/resource limits, or handling untrusted plugins are needed; operational benefits can outweigh IPC overhead.

## Official Documentation

- [Oracle JNI Specification — The Invocation API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html).
- [Oracle JNI Specification — The Invocation API (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html).
- [Oracle JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [Java SE Runtime — Shutdown and embedded JVM considerations](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html).

**Key Takeaway:** **A C/C++ application should only create a JVM itself when the native host genuinely needs to own the process and run Java code inside that process**. If Java is already the main application, let Java call native code; if fault isolation or independent upgrades are needed, consider a separate Java process. When choosing embedding, treat **JNI_CreateJavaVM, per-thread JNIEnv, classloaders, resources, and DestroyJavaVM** as a long-term lifecycle contract that must be managed, tested, and operated.

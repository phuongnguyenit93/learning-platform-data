# Looking Up Created JVMs and Understanding the Multiple-JVM-Per-Process Limit

## Learning Outcomes

When a **C/C++ program embeds a Java Virtual Machine (JVM)**, it needs to distinguish between two situations: whether a JVM is already running inside the process or whether the host needs to initialize the JVM for the first time. The **JNI Invocation API** provides `JNI_GetCreatedJavaVMs` to find JVMs that have been created **within the calling process itself**. Although the API uses an array and a count parameter, **creating multiple JVMs in the same process is not supported** according to the JDK 17 JNI specification.

After this lesson, you will understand the exact signature and results of `JNI_GetCreatedJavaVMs`, how to perform lookups before/after `JNI_CreateJavaVM`, how to choose between `JavaVM *` and `JNIEnv *`, why class loaders/threads are not separate JVMs, and how to organize a native host when multiple components need Java at the same time.

## 1. Where Does the JVM Reside When Embedded?

A process is an execution unit managed by the operating system with its own address space and resources. A **native executable** can load the JVM runtime, initialize a JVM inside **the same process**, and then call Java code through JNI.

~~~text
Process A: native host application (illustrative PID 1001)
    |
    +-- C/C++ code, native libraries
    +-- one embedded JVM
    |      +-- Java heap and GC
    |      +-- Java threads
    |      +-- multiple class loaders / modules
    |      +-- Java classes of multiple components
    +-- native threads (attach to the JVM when needing to call JNI)

Process B: java -jar worker.jar (illustrative PID 1002)
    |
    +-- another JVM, belonging to process B
~~~

Two processes A and B can each have a JVM. `JNI_GetCreatedJavaVMs` running in A **cannot** find B's JVM, because the API is not a machine-wide JVM enumeration tool. Tools such as `jps`, `jcmd`, or OS process lists serve out-of-process observation needs and have different access permissions.

Distinguishing the concepts:

| Concept | What is it? | Does it create an additional independent JVM? |
| --- | --- | --- |
| Process | Address space/lifecycle managed by the operating system | A separate process can contain its own JVM |
| JavaVM instance | Java runtime created via the launcher/Invocation API | Cannot create multiple VMs in the same process per JNI/JDK 17 |
| Java thread | Thread executing code inside the JVM | No |
| Class loader | Mechanism for loading and distinguishing the identity of classes | No |
| Module layer | Module configuration within the same Java runtime | No |
| JNI native library | Native code loaded or linked with the runtime | No |

One JVM can logically run multiple Java applications, but those applications still share the JVM runtime and several global resources. A class loader does not mean having a separate heap, GC, or VM startup options.

## 2. Invocation API: Three Easily Confused Functions

The prototypes declared by `jni.h`:

~~~c
jint JNI_GetCreatedJavaVMs(JavaVM **vmBuf,
                           jsize bufLen,
                           jsize *nVMs);

jint JNI_CreateJavaVM(JavaVM **p_vm,
                      void **p_env,
                      void *vm_args);

jint JNI_GetDefaultJavaVMInitArgs(void *vm_args);
~~~

The snippet above **only describes the prototypes**; it is not a standalone C program and does not need to redefine the functions.

- **`JNI_GetCreatedJavaVMs`** finds the JVMs currently reported by the Invocation API as created in the process.
- **`JNI_CreateJavaVM`** initializes a new JVM and, on success, populates `JavaVM *` along with the initializing thread's `JNIEnv *`. According to JNI, creating multiple JVMs in one process **is not supported**.
- **`JNI_GetDefaultJavaVMInitArgs`** is intended to retrieve default initialization information for the requested JNI version. On modern JDKs, calling it is not a mandatory precondition before `JNI_CreateJavaVM`.

The three functions above are exported from the JVM runtime and are not in the method table of `JavaVM *`. After obtaining a valid `JavaVM *vm`, the application calls functions such as `(*vm)->GetEnv(...)`, `(*vm)->AttachCurrentThread(...)`, and `(*vm)->DestroyJavaVM(...)` through this interface.

## 3. Reading `JNI_GetCreatedJavaVMs` Correctly

The standard signature is:

~~~c
jint JNI_GetCreatedJavaVMs(JavaVM **vmBuf,
                           jsize bufLen,
                           jsize *nVMs);
~~~

| Parameter | Meaning | Usage rules |
| --- | --- | --- |
| `vmBuf` | Output buffer to write `JavaVM *` pointers into | Allocate a valid buffer; per the JDK 17 specification, do not pass NULL |
| `bufLen` | Buffer capacity measured in **number of `JavaVM *` elements** | Do not confuse with byte count or `sizeof(buffer)` |
| `nVMs` | Output: **total number** of JVMs reported by the API | Use `jsize count` and pass `&count` to get the count; the spec allows NULL if the count is not needed |
| Return value `jint` | Status code | `JNI_OK` on success; JNI errors are negative numbers; check before using outputs |

Minimal call example:

~~~c
#include <jni.h>

JavaVM *found[1] = { NULL };
jsize total = 0;
jint rc = JNI_GetCreatedJavaVMs(found, 1, &total);

if (rc == JNI_OK && total == 1 && found[0] != NULL) {
    /* found[0] is a valid JavaVM * reported by the API. */
}
~~~

This is a **snippet** to be placed inside a C function linked with the VM runtime. It intentionally allocates a one-element array because standard JNI/JDK only supports **one VM per process**.

Three points to understand clearly:

1. **`nVMs` is the total count**, while the actual number of elements written into `vmBuf` does not exceed `bufLen`. In case the total exceeds the buffer capacity, you must check bounds and not read past the array.
2. **`bufLen` is measured in number of elements**. With `JavaVM *found[1]`, `sizeof(found)` is the size in bytes. Use `1` or the expression `sizeof found / sizeof found[0]`.
3. **`JNI_OK` does not mean a VM exists**. It can succeed with `total == 0` when the process has no VM yet. Conversely, when the API returns an error code, do not use `total` or `found[0]` to make any decision.

Situation interpretation table:

| State in the same process | On successful lookup, typical result |
| --- | --- |
| Native host just started, JVM not yet created | `total == 0`; no VM pointer to use |
| JVM already created and existing | `total == 1`; `found[0]` holds `JavaVM *` when the buffer has at least one slot |
| Wanting a second VM | Not supported; buffer size does not change this limit |
| Lookup error | Handle the return code; do not trust unverified outputs |

### What Do the C Pointer Types Mean?

`JavaVM *` is a pointer to a VM's Invocation API interface. `JavaVM **` is a pointer to a variable or array holding `JavaVM *`. For example:

~~~c
JavaVM *one = NULL;       /* one slot */
JavaVM *slots[1] = {0};   /* one-slot array */

/* Both &one and slots match the parameter type for vmBuf:
   JNI_GetCreatedJavaVMs(&one, 1, &count);
   JNI_GetCreatedJavaVMs(slots, 1, &count);
*/
~~~

A `JavaVM *` pointer is not a `jobject`: a `jobject` is a handle to a **Java object** with different GC/reference rules; `JavaVM *` is the JVM's interface. For two `JavaVM *` pointers returned by the same VM in a process, those pointers can be compared in an example to verify the same VM. Do not turn this conclusion into a rule for comparing Java objects by C pointer equality; for two JNI object references, `IsSameObject` is required.

## 4. Full Practice: Looking Up the VM Before and After Creation

The following example consists of **one Java class** and **one C executable**. The C executable must run in a **fresh native process**, look up to see 0 VMs, create exactly 1 VM, look up again, verify the VM pointer, and invoke a Java method. **There is no** second VM creation call.

### 4.1. Java File `EmbeddedHello.java`

~~~java
public final class EmbeddedHello {
    private EmbeddedHello() {}

    public static void sayHello() {
        System.out.println("java-in-host=yes");
    }
}
~~~

This is an ordinary Java 17+ class. The native host finds it from the embedded JVM's classpath; the class will be compiled before running the C executable.

### 4.2. C File `JvmLookupDemo.c`

~~~c
#include <jni.h>
#include <stdio.h>

/* Return JNI error code, and also return the VM count and the first VM if present. */
static jint lookup(JavaVM **out_vm, jsize *out_count) {
    JavaVM *buffer[1] = { NULL };
    jsize count = 0;

    jint status = JNI_GetCreatedJavaVMs(buffer, 1, &count);
    if (status != JNI_OK) {
        return status;
    }
    *out_count = count;
    *out_vm = count > 0 ? buffer[0] : NULL;
    return JNI_OK;
}

int main(void) {
    JavaVM *existing = NULL;
    jsize count = -1;

    jint rc = lookup(&existing, &count);
    if (rc != JNI_OK) {
        fprintf(stderr, "first lookup failed: %d\n", (int) rc);
        return 1;
    }
    printf("before=%d\n", (int) count);

    if (count != 0) {
        fputs("Run this example in a fresh native process.\n", stderr);
        return 1;
    }

    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    JavaVMOption options[1] = {
        { "-Djava.class.path=.", NULL }
    };
    JavaVMInitArgs args = {
        JNI_VERSION_1_8,
        1,
        options,
        JNI_FALSE
    };

    rc = JNI_CreateJavaVM(&vm, (void **) &env, &args);
    if (rc != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "create failed: %d\n", (int) rc);
        return 1;
    }

    existing = NULL;
    count = -1;
    rc = lookup(&existing, &count);
    if (rc != JNI_OK) {
        fprintf(stderr, "second lookup failed: %d\n", (int) rc);
        (*vm)->DestroyJavaVM(vm);
        return 1;
    }

    int same_vm = count == 1 && existing == vm;
    printf("after=%d\n", (int) count);
    printf("same-vm=%s\n", same_vm ? "yes" : "no");

    JNIEnv *thread_env = NULL;
    rc = (*vm)->GetEnv(vm, (void **) &thread_env, JNI_VERSION_1_8);
    int attached = rc == JNI_OK && thread_env != NULL;
    printf("thread-attached=%s\n", attached ? "yes" : "no");

    /* C stdio and System.out have separate buffers: stabilize output order. */
    fflush(stdout);

    int ok = same_vm && attached;
    if (ok) {
        jclass cls = (*env)->FindClass(env, "EmbeddedHello");
        if (cls == NULL) {
            (*env)->ExceptionDescribe(env);
            (*env)->ExceptionClear(env);
            ok = 0;
        } else {
            jmethodID method = (*env)->GetStaticMethodID(
                    env, cls, "sayHello", "()V");
            if (method == NULL) {
                (*env)->ExceptionDescribe(env);
                (*env)->ExceptionClear(env);
                ok = 0;
            } else {
                (*env)->CallStaticVoidMethod(env, cls, method);
                if ((*env)->ExceptionCheck(env)) {
                    (*env)->ExceptionDescribe(env);
                    (*env)->ExceptionClear(env);
                    ok = 0;
                }
            }
            (*env)->DeleteLocalRef(env, cls);
        }
    }

    rc = (*vm)->DestroyJavaVM(vm);
    if (rc != JNI_OK) {
        fprintf(stderr, "shutdown failed: %d\n", (int) rc);
        return 1;
    }
    return ok ? 0 : 1;
}
~~~

How it works:

- `lookup` uses `JNI_GetCreatedJavaVMs` and only returns the pointer after status is `JNI_OK`. The buffer has one slot because this environment supports at most one running VM per process.
- `JNI_CreateJavaVM` provides the VM interface and the initializing thread's `JNIEnv *`; the `(void **) &env` argument follows the Invocation API signature.
- `count == 1 && existing == vm` confirms that the looked-up VM object is the exact VM just created. `GetEnv` confirms that the initializing thread is attached.
- `FindClass`/`GetStaticMethodID`/`CallStaticVoidMethod` invoke the real Java method and check for exceptions. `DeleteLocalRef` releases the JNI local reference created for the class.
- Finally, `DestroyJavaVM` requests JVM termination. This function does not turn a process that has already had a JVM into an environment guaranteed to be able to **initialize a second JVM**.

### 4.3. Compiling and Running on Linux

Requires **JDK 17+** and a C compiler supporting C11, with `JAVA_HOME` pointing to the JDK directory containing `include/jni.h` and `lib/server/libjvm.so`. Place both files in the same directory and run in that directory:

~~~bash
javac -encoding UTF-8 EmbeddedHello.java

cc -std=c11 -Wall -Wextra -Werror \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  JvmLookupDemo.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o jvm-lookup-demo

./jvm-lookup-demo
~~~

Expected output when all operations succeed in a **fresh native process**:

~~~text
before=0
after=1
same-vm=yes
thread-attached=yes
java-in-host=yes
~~~

To understand stdout: before `JNI_CreateJavaVM`, the API sees no VM in the process. After creation, the API returns one VM and the pointer matches the created VM. The thread calling `main` is attached; the Java method runs via JNI. `fflush(stdout)` before the Java call helps keep the order of C and Java lines stable under normal execution conditions.

**Environment limitations:** the linker command uses `libjvm.so`, the `linux` include directory, and rpath specific to Linux. On Windows/macOS, you need to adapt the paths, library name, linker flags, and the OS's library search mechanism. Do not guess the ABI by only changing the file extension. For example, an incorrect `JAVA_HOME` or missing JVM runtime will cause compile/link/load errors, **not** prove `count == 0`.

## 5. Important Limit: Do Not Create Multiple JVMs in the Same Process

The JDK 17 *JNI Invocation API* specification explicitly states that **creating multiple VMs in a single process is not supported** in the descriptions of both `JNI_GetCreatedJavaVMs` and `JNI_CreateJavaVM`. Understand that as an **architectural constraint**:

- A native library/plugin wanting to run Java must not arbitrarily create a new JVM if the host process already has a JVM.
- The fact that `JNI_GetCreatedJavaVMs` has `vmBuf` and `bufLen` parameters only says the API knows how to write **a list of results**; it does not promise that multiple JVMs are implemented.
- Do not attempt to call `JNI_CreateJavaVM` a second time to obtain an "expected" error code. In real code, errors may vary by implementation/version; you must check the return code without relying on specific assumptions.
- Increasing `bufLen` to 2, 10, or 100 does not allow creating more VMs.
- If process B also has a JVM, process A does not see that JVM through A's Invocation API.
- Do not treat the count of "created" VMs as the count of Java classes, threads, class loaders, or modules.

### One JVM, Multiple Class Loaders: Not Equivalent to Multiple JVMs

Java can create separate class loaders to isolate class namespaces, but they still run on **the same JVM instance**. Standalone Java 17+ example:

~~~java
public final class LoaderScopeDemo {
    public static void main(String[] args) {
        ClassLoader first = new ClassLoader(null) {};
        ClassLoader second = new ClassLoader(null) {};
        System.out.println("two-loaders=" + (first != second));
    }
}
~~~

Commands:

~~~bash
javac LoaderScopeDemo.java
java LoaderScopeDemo
~~~

Stdout:

~~~text
two-loaders=true
~~~

What is demonstrated here is only two different class-loader objects. It **does not count JVMs**. Class loaders share the JVM runtime and do not provide two independent heaps/GCs/VM options.

If two independent JVMs are truly needed, the standard solution is **two processes** (for example, two `java` commands or two native hosts) exchanging data via IPC, sockets, HTTP/gRPC, or message queues. Each process has its own lifecycle, memory, and JVM configuration; communication between them does not use `JavaVM *` from the other process.

## 6. When a JVM Already Exists, How Do You Obtain `JavaVM *`?

Not all code needs `JNI_GetCreatedJavaVMs`.

| Where are you? | Appropriate way to obtain the JVM |
| --- | --- |
| Native host before deciding to initialize | `JNI_GetCreatedJavaVMs` |
| Native host that just initialized successfully | Keep the `JavaVM *` returned by `JNI_CreateJavaVM` |
| Inside a JNI native method that already has `JNIEnv *env` | Call `(*env)->GetJavaVM(env, &vm)` |
| In a JNI library hook loaded by the JVM | Receive the `JavaVM *vm` parameter from `JNI_OnLoad` |

Example **JNI method fragment**, not a standalone C program:

~~~c
JavaVM *vm = NULL;
jint rc = (*env)->GetJavaVM(env, &vm);
if (rc != JNI_OK || vm == NULL) {
    /* Return an error according to the native method's contract. */
}
~~~

And a hook in a JNI shared library:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;
    /* The VM already exists and is passed to the library by the runtime. */
    (void) vm;
    return JNI_VERSION_1_8;
}
~~~

`JNI_OnLoad` is only called by the runtime when the JNI library is loaded properly; the hook does not create a JVM itself. In real library code, manage the lifetime of `vm` and all related resources.

### `JavaVM *` Differs from `JNIEnv *`

`JavaVM *` represents the VM interface and can be shared across native threads while the JVM is alive. `JNIEnv *` is the JNI interface **specific to the current thread**. When a new native thread wants to call Java code, it must obtain the `JNIEnv *` of **that thread itself**, for example:

~~~c
/* Snippet: vm is a valid JavaVM *. */
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **) &env, JNI_VERSION_1_8);

if (rc == JNI_EDETACHED) {
    rc = (*vm)->AttachCurrentThread(vm, (void **) &env, NULL);
    if (rc == JNI_OK) {
        /* The thread was just attached: use env for JNI work. */
        (*vm)->DetachCurrentThread(vm);
    } else {
        /* Handle attach error; do not call JNI through a NULL env. */
    }
} else if (rc == JNI_OK) {
    /* The thread is already attached: use env; do not detach on behalf of another owner. */
} else {
    /* May be JNI_EVERSION or another error. */
}
~~~

This is a flow-explanation snippet, not a standalone function. In practice, you must clean up properly on both success and error paths, and not detach while Java frames are still on the stack. `GetEnv` returning `JNI_EDETACHED` on an unattached thread **does not mean the process has no JVM**. It only indicates that this thread does not yet have a JNI environment.

**Do not** copy thread A's `JNIEnv *` to thread B, and do not use the result of looking up `JavaVM *` as if it were `JNIEnv *`. Native threads can use the same VM but have their own separate JNI environments.

## 7. Looking Up and Creating a JVM Carries Race Risks

Two native components in the same process can do:

~~~text
Thread A: lookup -> count 0
Thread B: lookup -> count 0
Thread A: JNI_CreateJavaVM(...)
Thread B: JNI_CreateJavaVM(...)    // attempts to create a second time: unsupported
~~~

This is a classic **check-then-act race**. `JNI_GetCreatedJavaVMs` is a lookup operation; it **does not provide an application-wide mutex** and does not make the lookup/create pair atomic. A proper architecture needs a **single owner** to initialize and shut down the JVM, coordinating components via a lock or a synchronized state machine.

Example design states:

~~~text
NOT_STARTED -> INITIALIZING -> RUNNING -> SHUTTING_DOWN -> TERMINATED
        |            |
        |            +-- initialization error -> FAILED
        +-- existing VM found -> RUNNING (after determining ownership)
~~~

One thread is responsible for transitioning from `NOT_STARTED` to `INITIALIZING`. Other threads wait/converge on the created VM according to the host contract. **Do not** call `JNI_CreateJavaVM` from individual plugins. If a lookup finds an existing VM created by another component, you must determine **who owns the JVM** and who is allowed to shut it down; seeing the pointer does not automatically grant lifecycle ownership.

### Startup Options Cannot Be Changed Like Creating a New VM

For example, the host has already initialized the JVM with the `-Xmx` heap option or classpath. A later plugin cannot change those startup options by "looking up and then creating a second VM." A running JVM has the startup configuration from its initial init. Components must use the configuration provided by the host, or move workloads requiring a different JVM configuration to a separate process.

## 8. Shutdown Is Not a Guaranteed JVM Restart Mechanism

After obtaining `JavaVM *vm`, the host can request shutdown with:

~~~c
/* Snippet: vm must be valid and the caller must be the lifecycle owner. */
jint rc = (*vm)->DestroyJavaVM(vm);
if (rc != JNI_OK) {
    /* Handle shutdown error. */
}
~~~

According to the Invocation API, shutdown must account for Java threads and attached native threads; `DestroyJavaVM` may wait while **non-daemon user threads** are still running. A native library should not shut down the VM itself while other components are still using it.

**Do not infer that after calling `DestroyJavaVM`, you can call `JNI_CreateJavaVM` again in the same process.** The JDK 17 specification notes limitations on VM unloading; even if shutdown returns success on an implementation, JNI does not guarantee that a new create–destroy–recreate cycle in one process is supported. If a completely clean JVM environment is needed, **terminate the process and create a new process**.

Other risks when treating the JVM as something that can be toggled on/off at will: uncleaned global JNI references and native callbacks, un-detached native threads, class loader/native library resources, and external services still depending on the runtime. The owner must define the system's shutdown sequence.

## 9. Decision Flow for a Native Host

~~~text
Native host needs Java
    |
    v
Look up using JNI_GetCreatedJavaVMs
    |
    +-- rc != JNI_OK --> report error; do not use output
    |
    +-- count == 1 --> obtain existing JavaVM *
    |                   verify owner + RUNNING state
    |
    +-- count == 0 --> single owner considers JNI_CreateJavaVM
                        if rc == JNI_OK, keep JavaVM * for host
                        if error, report cause; do not assume VM was created
    |
    v
Native threads obtain their own JNIEnv * via GetEnv/AttachCurrentThread
    |
    v
Call Java/JNI while the runtime remains valid
    |
    v
Lifecycle owner coordinates shutdown once when the system exits
~~~

**If the API returns a total count greater than 1** on a special environment/implementation, do not apply arbitrary automatic VM-selection logic to code designed for standard JDK 17. That falls outside the contract of supporting multiple JVMs in one process; treat this as an out-of-assumption environment, verify the documentation/runtime, and refuse to operate without a proper design.

## 10. Common Mistakes and How to Fix Them

| Mistake or assumption | Consequence | How to handle |
| --- | --- | --- |
| "There is a `JavaVM **` array so multiple JVMs can be created" | Hits the unsupported multiple VMs limit | One JVM per process; use another process when an independent runtime is needed |
| Passing `sizeof(buffer)` for `bufLen` | Size in bytes, not number of elements | Use `sizeof(buffer) / sizeof(buffer[0])` |
| Reading `found[0]` when `count == 0` | Reading a slot that does not hold a valid VM | Check `JNI_OK`, count, and buffer first |
| Ignoring the return code of lookup/create | Processing unverified output | Stop and report the JNI error code |
| Treating `count == 0` as a promise that create will succeed | Race, insufficient resources, invalid VM options | Use an owner/lock, check create's return code |
| Using `JNIEnv *` from another thread | Violates the thread-local nature of the JNI environment | `GetEnv` or attach the right thread |
| Calling `JNI_CreateJavaVM` from a plugin loaded by Java | Attempting to create a second JVM | Receive the VM in `JNI_OnLoad` or `GetJavaVM` |
| Saving `JavaVM *` and using it after Destroy | VM interface is past its allowed lifetime | Bind lifetime to the lifecycle owner |
| Trying to call Destroy–Create to "reset the JVM" | In-process restart is not guaranteed | Create a new process for a new runtime |
| Using count to measure Java threads or class loaders | Two different kinds of objects | Use APIs/metrics at the right level |
| Using JNI lookup to find another process's JVM | The API is scoped to the process | Use OS tools to observe, IPC to interact |
| Plugin itself Destroys the JVM the host is using | Can break the entire host | Only the lifecycle owner may shut down |

### Analyzing a Few Scenarios

**Scenario A: `count == 1` but `GetEnv` reports `JNI_EDETACHED`.** Both results can be completely true at the same time: a JVM exists in the process, while the calling thread is not yet attached. You need to obtain `JNIEnv *` via `AttachCurrentThread`, not create another VM.

**Scenario B: C executable fails to link with `undefined reference to JNI_CreateJavaVM`.** Including `jni.h` alone is not enough: the executable must link against the JNI Invocation API implementation in the VM runtime (for example `libjvm.so` for the corresponding JDK/Linux). This is a build/link error; it does not tell you whether the process has a JVM or not.

**Scenario C: C executable runs, but `FindClass` cannot find the Java class.** Check the classpath passed via `JavaVMInitArgs`, the directory where the executable is run, and whether `javac` produced the `.class` file. Do not create another JVM just to change the classpath; configure the owner properly at init time or use a contracted class-loading strategy.

**Scenario D: A native plugin in a Java application already has `JNIEnv *env`.** Obtaining the VM directly with `GetJavaVM` from the JNI environment or the `JNI_OnLoad` parameter is usually more appropriate than an enumeration call. The plugin does not create a second VM.

**Scenario E: Wanting 2 workloads with different `-Xmx` and independent GCs.** Class loaders/threads in the same JVM do not provide such VM isolation. Two processes with two runtime configs are the appropriate choice; exchange data via IPC/network.

## 11. Self-Check Questions

**1.** `JNI_GetCreatedJavaVMs` returns `JNI_OK` and `nVMs == 0`. Does that mean no JVM has been reported in the process, or that the machine has no JVM?

**Answer:** It only speaks about **the current process**. The machine may have other Java processes.

**2.** What should `bufLen` be for the buffer `JavaVM *vms[1]`? Should `sizeof(vms)` be used?

**Answer:** Equal to **1** or `sizeof vms / sizeof vms[0]`. `sizeof(vms)` is measured in bytes.

**3.** Why does the prototype accept a list yet you still cannot call `JNI_CreateJavaVM` twice in the same process?

**Answer:** A general signature does not promise support for running multiple VMs; the JNI/JDK 17 specification explicitly states **multiple VMs in one process unsupported**.

**4.** A VM exists, but a native worker thread calling `GetEnv` gets `JNI_EDETACHED`; how to handle?

**Answer:** This thread is not attached yet. Call `AttachCurrentThread`, use the `JNIEnv *` returned specifically for that thread, and then detach when the work is finished if this code itself is the attach owner.

**5.** Do two class loaders mean two JVMs?

**Answer:** No. The same JVM can have multiple class loaders with different class identities.

**6.** Does a successful `DestroyJavaVM` guarantee that a VM can be recreated in the same process?

**Answer:** No. There is no guarantee of restarting/recreating a JVM in the same process from the Invocation API; if a clean new JVM is needed, create a new process.

**7.** A JNI library loaded by the Java launcher needs the JVM; should it use `JNI_CreateJavaVM` or `JNI_OnLoad`/`GetJavaVM`?

**Answer:** The JVM already exists; it should use `JNI_OnLoad(JavaVM *vm,...)` or `(*env)->GetJavaVM` from a running native method.

**8.** Why can't `JNI_GetCreatedJavaVMs` let a native application in process A control process B's JVM?

**Answer:** It only reports VMs in process A. `JavaVM *` is a process-local pointer, not a handle to control a JVM across OS boundaries; IPC/network is needed when interacting between processes.

## Practice Checklist

- [ ] Distinguish between process, JVM, Java thread, and class loader.
- [ ] `JNI_GetCreatedJavaVMs` receives a valid `JavaVM *` buffer, `bufLen` measured in number of elements, and `nVMs` as `jsize *`.
- [ ] Check `JNI_OK`, count, and buffer bounds before using the pointer.
- [ ] Only one owner performs JVM initialization and coordinates lookup/create to avoid races.
- [ ] When a JVM already exists, reuse the valid VM; do not create a second JVM in the process.
- [ ] Only use `JNIEnv *` on the right thread; check `JNI_EDETACHED` and attach/detach according to ownership.
- [ ] Set up classpath, JNI version, and VM startup options before creating the JVM.
- [ ] Shut down via the owner, without relying on Destroy–Create capability within the process.
- [ ] When multiple independent JVMs are needed, design multiple processes and an inter-process protocol.
- [ ] Verify build/run on the target OS, JDK, compiler, and ABI; do not infer unsupported capabilities from prototypes.

## Official Documentation

- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): sections on `JNI_GetCreatedJavaVMs`, `JNI_CreateJavaVM`, `DestroyJavaVM`, `GetEnv`, `AttachCurrentThread`, and the multiple-JVMs-per-process limit.
- [Oracle Java SE 17 — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `JavaVM`, `JNIEnv`, `jint`, `jsize`.
- [Oracle Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): JNI operations from an attached thread's environment.
- [Oracle Java SE 17 — Java Compiler](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiling the sample Java program.

**Key takeaway:** `JNI_GetCreatedJavaVMs` only **looks up the current process's JVM**. Use `JavaVM *` properly to manage the VM, a separate `JNIEnv *` for each thread, one lifecycle owner for the process, and create **another process** if an independent JVM is needed.

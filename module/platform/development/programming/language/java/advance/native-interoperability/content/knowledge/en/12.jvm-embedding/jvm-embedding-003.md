# Creating a JVM with JNI_CreateJavaVM and obtaining the creation thread's JNIEnv

## 1. When do you need to embed a JVM in a native application?

Normally we run `java -cp ... Main` so that the **JVM starts first**, and then the JVM calls down into C/C++ libraries through the Java Native Interface (JNI). In the **JVM embedding** model, the order is reversed: a C/C++ application is the *host process*, initializes the Java Virtual Machine itself inside the process, and uses JNI to invoke Java classes/methods.

Examples: desktop software written in C++, a game engine with Java scripting, a data-processing tool with a native entry point, or a host program wanting to reuse a Java library without spawning a separate Java process.

In Java SE, the main entry point is the **JNI Invocation API**:

```c
jint JNI_CreateJavaVM(
        JavaVM **p_vm,
        void **p_env,
        void *vm_args);
```

When creation succeeds:

- `*p_vm` receives **`JavaVM *`**, the interface to the newly created JVM, used to manage attaching/detaching native threads and destroying the VM.
- `*p_env` receives **`JNIEnv *` of the exact thread that called `JNI_CreateJavaVM`**. That thread is treated by the JVM as the main thread (in the Invocation API sense) and **is already attached**. You do not need to call `AttachCurrentThread` again just to use JNI immediately on this thread.
- The function returns `JNI_OK` on success, or a negative JNI error code if the VM could not be created. On the error path, do not use `vm`/`env` as valid interfaces.
- From `env`, you can call `FindClass`, `GetStaticMethodID`, `CallStatic...Method`, create Java strings/arrays, handle exceptions, and perform normal JNI operations.

Diagram:

```text
C/C++ application (host executable)
  │
  │  JavaVMInitArgs / JavaVMOption
  ▼
JNI_CreateJavaVM(&vm, (void **)&env, &args)
  │
  ├── JavaVM *vm ───────────────────────► JVM instance
  │                                        │
  └── JNIEnv *env ─► VM creation thread ────┤
                        │                  │
                        └── FindClass      │
                            GetMethodID    │
                            Call...Method ─► Java classes / methods
  │
  └── DestroyJavaVM(vm) when the host has finished its work
```

**Most important topic:** distinguish the *VM management interface* (`JavaVM *`) from the *JNI interface for the VM creation thread* (`JNIEnv *`); these are two pointers with different roles and different cross-thread usage rules.

## 2. Preparing configuration with JavaVMInitArgs

`JNI_CreateJavaVM` does not accept `String[] args` like Java's `main`. It takes `JavaVMInitArgs` containing the JNI version and startup options.

```c
typedef struct JavaVMOption {
    char *optionString;
    void *extraInfo;
} JavaVMOption;

typedef struct JavaVMInitArgs {
    jint version;
    jint nOptions;
    JavaVMOption *options;
    jboolean ignoreUnrecognized;
} JavaVMInitArgs;
```

The types above are defined by `jni.h`; **do not copy these declarations manually** into production code. They are shown only to explain the required fields.

### 2.1. Meaning of each field

| Field | What to understand |
| --- | --- |
| `version` | The **requested JNI interface** version, e.g. `JNI_VERSION_1_8`; **not** the running JDK version number |
| `nOptions` | The actual number of elements in the `options` array |
| `options` | Array of `JavaVMOption` containing each JVM startup option string |
| `ignoreUnrecognized` | Policy for handling unrecognized options per the Invocation API; typically set to `JNI_FALSE` to catch misconfigurations |

C example:

```c
char classPathOption[] = "-Djava.class.path=build/classes";

JavaVMOption options[1];
options[0].optionString = classPathOption;
options[0].extraInfo = NULL;

JavaVMInitArgs vmArgs = {0};
vmArgs.version = JNI_VERSION_1_8;
vmArgs.nOptions = 1;
vmArgs.options = options;
vmArgs.ignoreUnrecognized = JNI_FALSE;
```

The value `JNI_VERSION_1_8` is supported by JDK 17. Do not use `JNI_VERSION_17`: JNI constant names are not derived by appending the Java version number to the name. An application can request a lower JNI API level than the actual JDK version to maintain compatibility.

The `-Djava.class.path=build/classes` option helps the system/application class loader find bytecode compiled into the `build/classes` directory. In a native host model there is **no automatic `java -cp` command**; without configuring the classpath properly, `FindClass("demo/Calculator")` will easily fail.

Other JVM options can be added:

```c
/* Illustrative example: declare 3 options when actually needed. */
JavaVMOption options[3];
options[0].optionString = "-Djava.class.path=build/classes";
options[1].optionString = "-Xmx256m";
options[2].optionString = "-Xcheck:jni";

JavaVMInitArgs args = {0};
args.version = JNI_VERSION_1_8;
args.nOptions = 3;
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;
```

This is a **fragment**, not a complete program. `-Xmx256m` caps the maximum heap and `-Xcheck:jni` helps detect many JNI usage errors on supporting JVMs. Options like `-X...` are implementation/JVM details: verify them on your target runtime; with `ignoreUnrecognized = JNI_FALSE`, invalid options can prevent the VM from starting.

**Encoding note:** `JavaVMOption.optionString` is interpreted according to the default platform encoding of the VM/JNI implementation; do not automatically assume every C byte string passed in is UTF-8. Use ASCII for examples and carefully design encoding conversion if you must pass paths or arguments containing Unicode characters.

### 2.2. Allocation order and options lifetime

`JNI_CreateJavaVM` needs to read `JavaVMInitArgs` and the options array during initialization. Keep this data valid throughout the entire call. The pattern using local variables above is suitable because nothing is freed before `JNI_CreateJavaVM` returns.

In C, use `char[]` arrays that can be assigned to `char *optionString`. In C++, string literals have type `const char[]`; when passing to an API with a `char *` field, manage a mutable buffer or follow the API's guidance—avoid arbitrarily casting away `const char *` and letting another API modify read-only memory.

## 3. Analyzing the three parameters of JNI_CreateJavaVM

Typical call in **C**:

```c
JavaVM *vm = NULL;
JNIEnv *env = NULL;

jint rc = JNI_CreateJavaVM(
        &vm,
        (void **)&env,
        &vmArgs);
```

Explanation of each argument:

1. **`&vm`** has type `JavaVM **`, where the VM writes back the JVM management interface.
2. **`(void **)&env`** is cast because the `p_env` prototype uses `void **`, while the application variable is `JNIEnv *`. The function stores the `JNIEnv *` value of the exact *thread that called CreateJavaVM* here. Do not pass a bare `env` or an unallocated/improperly pointed `JNIEnv *`.
3. **`&vmArgs`** is the address of the struct containing the JNI version and startup options.

Success is verified via the return code:

```c
if (rc != JNI_OK) {
    fprintf(stderr, "JNI_CreateJavaVM failed: %d\n", (int)rc);
    return 1;
}

/* Here vm and env returned by JNI_CreateJavaVM can be used. */
```

This is a fragment for a C function returning `int`. Do **not** dereference `vm` or `env` on the VM creation failure branch. JNI return codes vary by error: for example `JNI_EVERSION` (unsupported version), `JNI_ENOMEM` (out of memory), `JNI_EINVAL` (invalid arguments), or `JNI_ERR` (general error). In practice, the runtime may print additional details on stderr; keep stderr intact when diagnosing.

### 3.1. Is the newly received `JNIEnv *` an "unattached" thread?

**No.** The JNI specification clearly states that the thread calling `JNI_CreateJavaVM` is considered the main thread of the VM. The returned `env` is already that thread's JNI interface. It can be used immediately:

```c
jclass cls = (*env)->FindClass(env, "java/lang/String");
```

No need for:

```c
/* No need to re-attach just because VM creation succeeded. */
(*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
```

Attaching an already attached thread may be a no-op returning that thread's interface, but adding an unnecessary call easily obscures ownership/lifecycle confusion. More importantly, **`JNIEnv *env` is not a "global" variable that can be passed to any thread** just because it was obtained at VM creation time.

## 4. Runnable example: C host creates a JVM and invokes a Java method

The example uses **JDK 17+**, **C11**, GCC or Clang on **Linux x86-64/aarch64** matching the installed JDK. Java contains a static `add` method. The C program creates the VM, confirms `GetEnv` on the initialization thread, looks up the class, invokes the Java method, and destroys the VM.

This is a **native C program calling Java**, not a JNI shared library loaded via `System.loadLibrary`. Therefore, building the host **links against the JVM library (`libjvm.so`)**.

### 4.1. Project structure

```text
embed-jvm/
├── src/
│   └── demo/
│       └── Calculator.java
├── native/
│   └── embed.c
└── build/
    ├── classes/              # generated by javac
    └── embed                 # generated by the C compiler
```

### 4.2. Java class

**File `src/demo/Calculator.java`:**

```java
package demo;

public final class Calculator {
    private Calculator() {}

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }
}
```

The `add` method is `public static int add(int,int)`, with JNI descriptor **`(II)I`**:

- `(II)`: two Java `int` arguments.
- `I` after the parentheses: Java `int` return value.

`Math.addExact` throws `ArithmeticException` if addition overflows the signed 32-bit Java `int` range, helping illustrate the need to check Java exceptions from the native side. On the example's success path, `20 + 22 = 42`.

### 4.3. C host initializes the VM and obtains the creation thread's env

**File `native/embed.c`:**

```c
#include <jni.h>
#include <stdio.h>

int main(void) {
    char cp[] = "-Djava.class.path=build/classes";

    JavaVMOption opts[1];
    opts[0].optionString = cp;
    opts[0].extraInfo = NULL;

    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_8;
    args.nOptions = 1;
    args.options = opts;
    args.ignoreUnrecognized = JNI_FALSE;

    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    jint createRc = JNI_CreateJavaVM(
            &vm, (void **)&env, &args);

    if (createRc != JNI_OK) {
        fprintf(stderr, "Cannot create JVM: %d\n", (int)createRc);
        return 1;
    }

    printf("JNI_CreateJavaVM: JNI_OK\n");

    int exitCode = 1;
    jclass calcClass = NULL;

    /* Verify that the thread that just created the VM has its own JNIEnv. */
    JNIEnv *checkedEnv = NULL;
    jint getRc = (*vm)->GetEnv(
            vm, (void **)&checkedEnv, JNI_VERSION_1_8);

    if (getRc != JNI_OK || checkedEnv == NULL) {
        fprintf(stderr, "GetEnv failed: %d\n", (int)getRc);
        goto shutdown;
    }

    printf("GetEnv(init thread): JNI_OK\n");

    calcClass = (*env)->FindClass(env, "demo/Calculator");
    if (calcClass == NULL) {
        fprintf(stderr, "Cannot find demo.Calculator\n");
        if ((*env)->ExceptionCheck(env)) {
            (*env)->ExceptionDescribe(env);
        }
        goto shutdown;
    }

    jmethodID add = (*env)->GetStaticMethodID(
            env, calcClass, "add", "(II)I");
    if (add == NULL) {
        fprintf(stderr, "Cannot find Calculator.add(int,int)\n");
        if ((*env)->ExceptionCheck(env)) {
            (*env)->ExceptionDescribe(env);
        }
        goto shutdown;
    }

    jint result = (*env)->CallStaticIntMethod(
            env, calcClass, add, (jint)20, (jint)22);

    if ((*env)->ExceptionCheck(env)) {
        fprintf(stderr, "Java method threw an exception\n");
        (*env)->ExceptionDescribe(env);
        goto shutdown;
    }

    printf("Java add(20, 22): %d\n", (int)result);
    exitCode = 0;

shutdown:
    if (calcClass != NULL) {
        (*env)->DeleteLocalRef(env, calcClass);
    }

    jint destroyRc = (*vm)->DestroyJavaVM(vm);
    if (destroyRc == JNI_OK) {
        printf("DestroyJavaVM: JNI_OK\n");
    } else {
        fprintf(stderr, "DestroyJavaVM failed: %d\n",
                (int)destroyRc);
        exitCode = 1;
    }

    return exitCode;
}
```

### 4.4. Step-by-step walkthrough

- `JNI_CreateJavaVM` takes the addresses of `vm` and `env`. After `JNI_OK`, **there is no need to re-attach the VM creation thread**.
- `GetEnv` on the **same thread** returns `JNI_OK` and a valid `JNIEnv *`. The example does not print the pointer address because addresses depend on the runtime/process.
- `FindClass(env, "demo/Calculator")` uses the **JNI internal** class name with slashes. When called from a native application via the Invocation Interface without a Java native-method frame, JNI uses the **system class loader**. Because `-Djava.class.path=build/classes` was set, that loader finds the class.
- `GetStaticMethodID` uses the exact name `add` and descriptor `(II)I`. If the name or signature is wrong, JNI may have a pending exception; do not proceed to call the method when `add == NULL`.
- `CallStaticIntMethod` executes the Java code and returns `jint`. You must call `ExceptionCheck` **before treating `result` as a valid result**.
- `ExceptionDescribe` in the error branch prints the stack trace to stderr and **clears the pending exception**; this is intended only for demo diagnostics. In a production host, you can retrieve the exception object, extract details, and map it to a C/C++ error according to your own protocol.
- `DeleteLocalRef` releases the local reference to the class. `DestroyJavaVM` is called when no more work remains and the thread has no pending JNI calls.
- `DestroyJavaVM` may wait for **non-daemon Java threads / natively-attached threads** to finish. Do not view it as a `free()` function that always returns immediately; the demo does not spawn extra workers.

### 4.5. Compile and run commands on Linux

Run from inside the `embed-jvm` directory. Requires a JDK with `jni.h` and `libjvm.so`. Assuming `JAVA_HOME` points to the right JDK directory:

```bash
mkdir -p build/classes

javac -d build/classes src/demo/Calculator.java

cc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/embed.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o build/embed

./build/embed
```

Because the host executable calls `JNI_CreateJavaVM` directly, the linker must find **`libjvm.so`**. `-L` supplies the library path at link time; `-Wl,-rpath,...` embeds the shared library path into the executable so the dynamic loader can typically locate `libjvm.so` at runtime. Some packaging environments use the `LD_LIBRARY_PATH` environment variable or a dedicated loader path mechanism instead of rpath; do not hardcode a system JDK path into a shipped product without controlling versions and update permissions.

With a relative Java classpath like `build/classes`, you must **run the executable from the `embed-jvm` directory**. If invoking `build/embed` from another directory, adjust the classpath configuration accordingly or use an absolute path.

**Expected stdout on the success path:**

```text
JNI_CreateJavaVM: JNI_OK
GetEnv(init thread): JNI_OK
Java add(20, 22): 42
DestroyJavaVM: JNI_OK
```

The program does not need a Java `public static void main(String[] args)`: the entry point here is **C's `main(void)`**. JNI can invoke any valid Java method with an appropriate signature and visibility. If you want to invoke Java's `main`, use `GetStaticMethodID(..., "main", "([Ljava/lang/String;)V")` and construct the corresponding `String[]` argument before calling `CallStaticVoidMethod`.

Platform note: macOS and Windows require different JNI include paths, different JVM library names/formats, and corresponding linker flags; do not reuse Linux's `-L.../lib/server -ljvm` verbatim across every OS. The C binary and JDK must match in architecture/ABI (for example, an x64 host requires an x64 JVM).

## 5. The creation thread's JNIEnv and JNIEnv on other threads

### 5.1. What happens if the host spawns another native thread?

`JNIEnv *` is a **thread-local interface**. It is valid only on the thread that obtained it, even though the VM can operate concurrently across multiple threads.

```text
Native host process
│
├── Thread T0: JNI_CreateJavaVM
│   ├── JavaVM *vm ───────────────────────┐
│   └── JNIEnv *env0 (T0 only)            │
│                                         │
└── Thread T1: pthread/std::thread        │
    ├── GetEnv → JNI_EDETACHED (if not attached)
    ├── AttachCurrentThread(vm) ◄─────────┘
    ├── JNIEnv *env1 (T1 only)
    ├── Perform JNI calls
    └── DetachCurrentThread(vm) before exiting
```

`JavaVM *vm` can be passed to other threads to use the Invocation API. **Do not pass T0's `env0` to T1** and call `(*env0)->FindClass(env0, ...)` on T1. Some JVMs may detect the error and abort; no JNI contract permits this operation.

### 5.2. `GetEnv` checks attachment status; it does not attach automatically

C signature:

```c
jint GetEnv(
        JavaVM *vm, void **p_env, jint version);
```

There are three key results:

| Result | Meaning |
| --- | --- |
| `JNI_OK` | Current thread is already attached; `*p_env` holds a valid `JNIEnv *` |
| `JNI_EDETACHED` | Current thread is not attached; must call `AttachCurrentThread` to make JNI calls |
| `JNI_EVERSION` | Requested JNI version is not supported |

C helper example illustrating a host worker scenario:

```c
/* Fragment: vm is a valid JavaVM*; caller is on a native worker.
   Do not use vm after the VM has called DestroyJavaVM. */
JNIEnv *workerEnv = NULL;

jint rc = (*vm)->GetEnv(
        vm, (void **)&workerEnv, JNI_VERSION_1_8);

if (rc == JNI_EDETACHED) {
    rc = (*vm)->AttachCurrentThread(
            vm, (void **)&workerEnv, NULL);
    if (rc != JNI_OK) {
        /* Do not use workerEnv if attach fails. */
        return;
    }

    /* ... JNI operations on the current worker thread ... */

    (*vm)->DetachCurrentThread(vm);

} else if (rc == JNI_OK) {
    /* Thread already attached: use workerEnv, do not detach arbitrarily
       if the attach lifecycle belongs to another component. */

} else {
    /* JNI_EVERSION or another error. */
}
```

This is a **hypothetical fragment inside a C function returning `void`** with no specific worker task. In production, track an `attachedHere` flag to ensure you detach **only threads attached by this logic**. When a self-created native thread exits, it must detach if still attached, and must not detach while Java methods remain on the call stack.

**Key takeaway:** `JNI_CreateJavaVM` already attaches its calling thread, whereas `AttachCurrentThread` is for other threads that need to join the VM. `GetEnv` checks the current thread, and is not a way to obtain a single shared `JNIEnv *` for everyone.

### 5.3. Creating a JVM from the "primordial thread"

The JNI specification notes that on some operating systems, the **primordial process thread** (typically the thread running the initial C `main`) has special stack configuration that can affect its ability to act as a normal Java thread. The documentation **recommends creating a dedicated native thread to initialize the JVM** instead of always using the primordial thread.

The example in section 4 intentionally uses `main(void)` to keep the API presentation short and easy to run. For real-world host applications requiring high reliability, spawn a dedicated thread with an appropriate stack size, call `JNI_CreateJavaVM` and dispatch Java code on that thread, and coordinate `DestroyJavaVM` with the lifecycle of non-daemon threads. This choice must align with GUI libraries, event loops, and the host's thread-affinity requirements.

**Do not think of the "creation thread" as a process-wide singleton thread authorized to make all JNI calls on behalf of other threads**. Each thread still needs its own env and must respect the JVM's state.

## 6. Handling exceptions when C is the host program

When C calls Java via `CallStaticIntMethod`/`CallObjectMethod`, a Java method can **throw a Java exception**. The JVM places the exception in a pending state on the JNI calling thread. C code **does not automatically run a Java `catch`**, does not automatically receive a C++ `std::exception`, and cannot infer an error solely from the JNI call's return value.

How to check:

```c
jint value = (*env)->CallStaticIntMethod(
        env, clazz, methodId, (jint)1, (jint)2);

if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
    /* There is a pending Java exception. Do not treat value as a result. */
    (*env)->ExceptionDescribe(env);  /* Print stack trace AND CLEAR. */
    /* Branch to cleanup / host error path. */
}
```

**This is a fragment**; `clazz` and `methodId` must have been properly looked up and remain valid. `ExceptionDescribe` is a diagnostic utility **with the side effect of clearing the pending exception**; if you want to preserve the error for another Java layer, do not call it inadvertently.

In a production host, you can:

1. Call `ExceptionOccurred` to get a local ref to the pending `Throwable`.
2. Deliberately call `ExceptionClear` if you need to invoke other JNI functions to extract the message/cause or convert the error.
3. Map the information into a C/C++ status/error object, preserve contextual logging, and return the error through the host API.
4. Call `DeleteLocalRef` at the right lifetime; do not retain a local `jthrowable` past the native frame/thread unless you create a global ref and manage its lifecycle.

**While an exception is pending, only a limited set of JNI APIs is permitted**, such as `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, and `DeleteLocalRef`. Do not continue calling `FindClass`/`GetMethodID`/`Call...Method` arbitrarily on the pending branch; clean up or clear according to a clear strategy.

### 6.1. Triggering a Java error in the example

If you want to observe an error from Java's `Math.addExact` yourself, *temporarily* replace the call with:

```c
/* Fragment replacing the successful call in section 4. */
jint result = (*env)->CallStaticIntMethod(
        env, calcClass, add, (jint)2147483647, (jint)1);
```

Java will throw `ArithmeticException` due to overflow. The host's `ExceptionCheck` branch writes the stack trace to stderr and does not print the result line `Java add(20, 22): 42`. **There is no fixed expected stderr**, because stack traces and error details can vary by JDK/implementation. After observing, restore the `20, 22` call to run the happy path again.

## 7. FindClass in a native host and class loaders

`FindClass` inside a Java native method usually selects the loader of **the class declaring the native method**. However, when called **through the Invocation Interface without a Java native method on the stack**, such as calling `FindClass` right after `JNI_CreateJavaVM` from a C host, JNI uses the **system class loader**.

Therefore, in the example:

```c
jclass cls = (*env)->FindClass(env, "demo/Calculator");
```

succeeds when the `demo.Calculator` bytecode is on the proper classpath. If a Java class resides only in a **custom `ClassLoader`/module layer** unknown to the system loader, looking it up by name may fail. Do not assume `FindClass` automatically knows about the plugin or container loader your host wants to use.

When you need a custom loader:

- Call a Java bootstrap/entry class visible to the system loader to build the module/plugin layer, and have Java return a `Class<?>` or callback object.
- Or store a **global ref to a valid `ClassLoader`**, call `loadClass(String)` with the dotted Java name (for example `"plugin.Service"`), and then call `GetMethodID`/`Call...Method` on the returned class.
- Maintain ownership and cleanup for `jclass`/`jobject` references; do not cache a local ref across threads or across multiple JNI calls.

Fixing `-Djava.class.path=...` or the loader design in the right place is the solution for class lookup issues; switching to `Class.forName` in C code without the proper helper/loader will not solve it.

### 7.1. Formatting JNI signatures accurately

JNI uses JVM-structured method descriptors rather than Java source-syntax type names:

| Java declaration | JNI descriptor |
| --- | --- |
| `int add(int a, int b)` | `(II)I` |
| `void log(String message)` | `(Ljava/lang/String;)V` |
| `String format(int n)` | `(I)Ljava/lang/String;` |
| `void main(String[] args)` | `([Ljava/lang/String;)V` |

A wrong descriptor causes `GetStaticMethodID`/`GetMethodID` to fail, usually leaving a pending `NoSuchMethodError`. `javap -s` is useful when method signatures are complex; dots in JNI class names use slashes, and array types use `[` notation.

## 8. JVM lifecycle and practical deployment limits

### 8.1. `DestroyJavaVM` is a lifecycle step, not an arbitrary reset command

After creating the VM successfully, the C/C++ application should have **one clear owner** managing termination. `(*vm)->DestroyJavaVM(vm)` initiates VM shutdown and waits for the appropriate shutdown conditions. If non-daemon Java threads or natively-attached threads are still running, the operation may **wait a long time** or fail to complete as the application expects.

Therefore, the normal shutdown sequence is:

1. Stop sending new requests to Java.
2. Tell Java services, executors, and natively-attached workers to shut down.
3. Wait for in-flight callbacks to complete, delete global JNI refs/handles, and clean up native resources.
4. Ensure no thread will still attempt to use `JNIEnv *` or `JavaVM *` of the terminated VM.
5. Call `DestroyJavaVM` according to the runtime's rules and check the return code.

**Do not design an application that repeatedly creates and destroys JVMs in the same process** as a cheap restart loop. The JNI specification explicitly states that **creating multiple JVMs in a single process is not supported**. Re-initializing after destroy is not a portable contract to rely on; if you need a completely fresh state, restart the host process or run the JVM in a separate process.

### 8.2. What is `JNI_GetCreatedJavaVMs` used for?

The JNI Invocation API also provides:

```c
jint JNI_GetCreatedJavaVMs(
        JavaVM **vmBuf, jsize bufLen, jsize *nVMs);
```

This API lets you inspect already-existing VMs via the runtime's interface; it is **not a way to create additional VMs**. Even though the interface uses an output array, Java SE JNI does not support creating multiple independent VMs in the same process.

If a native library is embedded into another host application and does not own the process, it must not arbitrarily call `JNI_CreateJavaVM` or `DestroyJavaVM` when the VM belongs to another component. The process/VM owner must define the lifecycle contract.

### 8.3. Differences between embedding a JVM and loading a JNI shared library

| Aspect | Native host embedding JVM | Java loading shared JNI library |
| --- | --- | --- |
| Entrypoint | C/C++ `main` or native host | Java `main`/framework |
| Who creates the JVM? | Host calls `JNI_CreateJavaVM` | Java launcher/framework already created it |
| Who gets the first `JNIEnv *`? | Returned by `JNI_CreateJavaVM` on the creation thread | JVM passes `JNIEnv *` as a parameter when calling a native method |
| Main library linking/loading | Host links/dynamically loads `libjvm` | Java calls `System.loadLibrary` to load the application library |
| VM shutdown management | Host owns and coordinates `DestroyJavaVM` | JVM launcher/runtime coordinates it |
| Class lookup | Usually via the system loader when called from Invocation Interface | Loader of the class declaring the native method in a native-frame context |

`JNI_OnLoad` is a hook for **a JNI library loaded by a Java VM**, not a replacement for `JNI_CreateJavaVM` to initialize a VM from a C executable.

## 9. Common errors and troubleshooting

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| Linker reports `undefined reference to JNI_CreateJavaVM` | Not linking against the JVM library or wrong linker flag order | Add `-L.../lib/server -ljvm` after source/object files |
| Running binary reports missing `libjvm.so` | Dynamic loader cannot find the JVM library | Check rpath/`LD_LIBRARY_PATH`, architecture, and JDK path |
| `JNI_CreateJavaVM` returns a negative error | Invalid JNI version/option/path/memory | Log error code and stderr; start with minimal configuration |
| `GetEnv` returns `JNI_EDETACHED` on a native worker | Worker has not been attached | Call `AttachCurrentThread` before JNI calls |
| Crash when passing `JNIEnv *` to another thread | Using the interface on the wrong thread | Share only `JavaVM *`; each thread gets its own env |
| `FindClass("demo/Calculator")` fails | Wrong classpath, JNI name, or loader | Check `-Djava.class.path`, `javap`, system/custom loader |
| `GetStaticMethodID` returns `NULL` | Wrong name/descriptor or method is not static | Check `javap -s`, `(II)I`, pending exception |
| Java method returns strange value after an error | Host did not call `ExceptionCheck` | Check for pending exceptions before using the result |
| `DestroyJavaVM` does not return | Non-daemon Java/natively-attached thread still running | Coordinate shutdown and detach workers |
| Calling `JNI_CreateJavaVM` multiple times in one process | Mistakenly assuming creating a second VM or restarting the JVM is portable | Only one JVM per JNI contract; use a process boundary if a reset is needed |
| C host works in the project directory but fails when deployed | Classpath set relative to cwd | Construct absolute classpath/VM paths in deployment |
| JVM initializes but Java callback cannot find plugin classes | `FindClass` from Invocation Interface uses system loader | Have Java bootstrap choose the plugin loader and pass the right `Class<?>`/object |

### 9.1. Pre-delivery checklist for JVM embedding

- [ ] The host targets the right JDK version and CPU/ABI; JNI headers and the JVM shared library match the environment.
- [ ] `JavaVMInitArgs.version` uses an actually supported JNI constant, not confused with the Java language version.
- [ ] `options` and `nOptions` match; classpath/module path configuration is sufficient to look up application classes.
- [ ] `JNI_CreateJavaVM` is called once in the host lifecycle and `JNI_OK` is verified before using `vm`/`env`.
- [ ] The JVM creation thread's `JNIEnv *` is **used only on that thread**.
- [ ] Other native threads use `JavaVM*` to call `GetEnv`/`AttachCurrentThread` and detach according to ownership.
- [ ] Check `ExceptionCheck` after JNI calls that can throw Java exceptions, and clean up local/global refs with proper lifetimes.
- [ ] Shutdown includes a stop/drain mechanism for non-daemon threads and never uses VM interfaces after destroy.
- [ ] Does not rely on creating multiple JVMs or restarting the JVM inside a single process.
- [ ] Tested against invalid classpath, invalid JVM options, linker/libjvm errors, Java exceptions, and shutdown with workers.

## 10. Self-check questions

**1.** `JNI_CreateJavaVM(&vm, (void **)&env, &args)` succeeds. Which thread does `env` belong to?  
**Answer:** The exact thread that called `JNI_CreateJavaVM`. That thread is already attached to the VM; no second attach is needed to make JNI calls on that thread.

**2.** Can you store `JNIEnv *env` in a global C variable and use it from any `pthread`?  
**Answer:** No. `JNIEnv *` is valid only on its owning thread; store `JavaVM*` and obtain a new env via `AttachCurrentThread` on each native worker.

**3.** Is `args.version = JNI_VERSION_1_8` on Java 17 wrong because "1.8 differs from 17"?  
**Answer:** No. That is the **JNI specification/API** version, not the JDK release number.

**4.** Why does `FindClass("demo/Calculator")` work in the example's C host?  
**Answer:** The JVM was initialized with `-Djava.class.path=build/classes`, and `FindClass` via the Invocation Interface with no native Java frame uses the system class loader, which sees that class.

**5.** The C host calls `CallStaticIntMethod`, and Java throws `ArithmeticException`. Can `jint result` be used as a successful addition result?  
**Answer:** No. You must check `ExceptionCheck`. When a Java exception is pending, the return value does not represent a valid business result.

**6.** Can you create a second JVM to run another Java version in the same process?  
**Answer:** Not under the portable contract of the Java SE JNI Invocation API. Multiple VMs in the same process are not supported.

**7.** `GetEnv` returns `JNI_EDETACHED`. Does that mean no JVM exists?  
**Answer:** Not necessarily. It usually indicates that the **current thread is not yet attached** to the existing VM; you must attach before using JNI.

**8.** Why can `DestroyJavaVM` block and wait?  
**Answer:** The JVM must coordinate shutdown with non-daemon Java/natively-attached threads. If those threads have not exited, you cannot assume `DestroyJavaVM` returns immediately.

## 11. Core knowledge summary

- **`JNI_CreateJavaVM` both creates the VM and returns `JavaVM *` along with the calling thread's `JNIEnv *`.** This is the mechanism for embedding a JVM from C/C++, distinct from `System.loadLibrary`.
- **Configure with `JavaVMInitArgs`**, notably `JNI_VERSION_1_8` for Java 17+ examples and `-Djava.class.path=...` for class lookup.
- **`JavaVM*` manages the VM and supports attach/detach; `JNIEnv*` is used only on its own thread.** The VM creation thread is already attached; other workers must attach separately.
- **JNI lookup requires internal class names and standard descriptors**: `demo/Calculator`, `add`, `(II)I`.
- **After a Java call, check for pending exceptions** before using the return value. `ExceptionDescribe` has the effect of printing and clearing the exception, so use it intentionally.
- **Create only one VM per process**, and manage shutdown, threads, references, and linkage to `libjvm` as core parts of product design.

### Official references

- [Oracle — JNI Invocation API, Creating the VM / JNI_CreateJavaVM (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): parameters, `JavaVMInitArgs`, `JNIEnv *` interface, main thread, multiple-VM limitation, `GetEnv`, and `DestroyJavaVM`.
- [Oracle — JNI Design Overview (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): thread-bound `JNIEnv *` and using JNI interfaces.
- [Oracle — JNI Functions (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `FindClass`, `GetStaticMethodID`, `CallStaticIntMethod`, `ExceptionCheck`, and `ExceptionDescribe`.
- [Oracle — Java SE 17 javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting method descriptors with `javap -s` for JNI lookups.

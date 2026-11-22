# Library Initialization via JNI_OnLoad and Return Code Handling

## 1. What Problem Does `JNI_OnLoad` Solve?

When Java needs to call C/C++ code through the **Java Native Interface (JNI)**, the JVM must **load the native library** and link the `native` methods to their corresponding machine functions. A library may need to perform preparatory work before Java invokes any native method, for example:

- Specifying the JNI version that the library requires.
- Obtaining the `JNIEnv *` of the thread loading the library.
- Finding Java classes using the appropriate class loader.
- Registering native methods using `RegisterNatives`.
- Initializing `jmethodID`/`jfieldID` caches, global references, or native resources, with a cleanup mechanism on failure.

The primary hook is the **`JNI_OnLoad`** function, exported from a **dynamically linked JNI library**. The JVM calls this function when loading the library (such as via `System.loadLibrary`).

~~~c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved);
~~~

A successful `JNI_OnLoad` must return a **JNI version constant supported by the JVM**, such as `JNI_VERSION_1_6`. The return value is not the result of a regular native method and **is not** `JNI_OK`. If the returned version is not recognized by the JVM, the JVM refuses to load the library.

This lesson presents the flow from Java to native, how to obtain `JNIEnv *`, method registration, how to report errors and clean up resources, common mistakes when returning the wrong code, and a complete **Java 17+ / C11** example.

## 2. Lifecycle from `System.loadLibrary` to the First Native Call

Suppose Java has:

~~~java
static {
    System.loadLibrary("onload_demo");
}
~~~

The flow can be visualized as:

~~~text
JVM initializes the class containing the static initializer
                    |
                    v
System.loadLibrary("onload_demo")
                    |
                    v
OS loader opens the file matching OS/CPU
(lib*.so / lib*.dylib / *.dll)
                    |
                    v
JVM looks up the JNI_OnLoad symbol (if present)
                    |
                    v
JNI_OnLoad(JavaVM *, void *)
    |-- GetEnv -> obtain JNIEnv* of the current thread
    |-- FindClass / RegisterNatives / prepare state
    |-- return JNI_VERSION_1_6  (success)
    |-- or return JNI_ERR       (failure)
                    |
       +------------+-------------+
       |                          |
       v                          v
JVM accepts the version   JVM rejects loading the library
       |                          |
       v                          v
loadLibrary returns       Java receives a library load error
       |
       v
Java invokes the linked native method
       |
       v
C/C++ processes and returns the result to Java
~~~

**Separating the three steps:**

1. **Load library:** `System.loadLibrary` requests the JVM to load the library. This is when the `JNI_OnLoad` hook can run.
2. **Initialize/register:** `JNI_OnLoad` can optionally check the environment and call `RegisterNatives`, then return the required JNI version.
3. **Invoke native method:** a call like `plusOne(41)` is what actually transfers control to the C/C++ business logic function.

Simply loading the library **does not automatically** execute every native method. If the library **does not export `JNI_OnLoad`**, the JVM assumes the library only requires JNI `JNI_VERSION_1_1` per the specification; native methods can still be found via JNI naming conventions. For modern libraries that need explicit setup, proactively defining the hook is usually easier to control.

A class can call `System.load` (absolute file path) instead of `System.loadLibrary` (logical name without prefix/extension). Both can lead to the JVM loading the library and processing `JNI_OnLoad`. Calling `dlopen` directly in C code **is not fully equivalent** to loading a JNI library through the JVM mechanism.

## 3. Signature and Meaning of Each Component

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;
    return JNI_VERSION_1_6;
}
~~~

This is a **minimal hook** example, without any business methods yet.

| Component | Meaning |
| --- | --- |
| `JNIEXPORT` | Ensures the symbol is exported according to JNI on the target platform |
| `jint` | JNI integer type used as the **version value to return** |
| `JNICALL` | ABI calling convention according to the target's JNI header |
| `JNI_OnLoad` | **Fixed symbol name** that the JVM looks for in a dynamically linked library |
| `JavaVM *vm` | Invocation API pointer to the JVM, passed into the hook |
| `void *reserved` | Parameter reserved for future use; currently unused |
| `return JNI_VERSION_1_6` | The library requires at least JNI interface version 1.6; the JVM must support it |

**There is no `JNIEnv *env` in the parameters of `JNI_OnLoad`.** To call JNI functions such as `FindClass`, first use `JavaVM->GetEnv` to get the interface of the **current thread**.

In C:

~~~c
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **) &env, JNI_VERSION_1_6);
if (rc != JNI_OK) {
    return JNI_ERR;
}
~~~

In C++:

~~~cpp
JNIEnv *env = nullptr;
jint rc = vm->GetEnv(reinterpret_cast<void **>(&env),
                      JNI_VERSION_1_6);
if (rc != JNI_OK) {
    return JNI_ERR;
}
~~~

The two snippets above are **illustrative fragments inside `JNI_OnLoad`**, not standalone programs. `GetEnv` is used to retrieve `JNIEnv *` if the thread is already attached; it **does not automatically attach** a new thread.

Some `GetEnv` results:

- `JNI_OK`: success, `env` can be used.
- `JNI_EVERSION`: the requested JNI version is not supported.
- `JNI_EDETACHED`: the calling thread is not attached to the JVM.
- Other error values according to the Invocation API specification.

In `JNI_OnLoad` called by the JVM on the library-loading thread, `GetEnv` usually succeeds if a valid version is requested. Otherwise, return an appropriate failure code and avoid dereferencing `env == NULL`. **`JNIEnv *` is thread-bound**; do not cache it as a global variable to call from other threads. If communication from a native worker thread is needed, you must use `JavaVM *` and a separate attach/detach mechanism outside the scope of this example.

## 4. Distinguishing Status Codes and JNI Version Codes

This is the most error-prone part of `JNI_OnLoad`.

| Constant/Value | Role | Should it be returned directly from `JNI_OnLoad`? |
| --- | --- | --- |
| `JNI_OK` (typically `0`) | **Success** status code of many JNI/Invocation APIs, such as `GetEnv` and `RegisterNatives` | **No.** `0` is not a required JNI version constant |
| `JNI_ERR` (typically `-1`) | Generic failure status code | **Can** be used to signal initialization failure; the JVM will not treat this as a valid version |
| `JNI_VERSION_1_1` | Legacy JNI version constant | Only when the library genuinely requires that interface level |
| `JNI_VERSION_1_2`, `JNI_VERSION_1_4` | Corresponding JNI version constants | Allowed if matching the API used and the target JVM |
| `JNI_VERSION_1_6` | Common version, supported by JDK 17 | **Yes** in this lesson's example |
| `JNI_VERSION_1_8` | JNI 1.8 version | **Yes** if the code requires it and the JVM supports it |
| An arbitrary integer or `0xDEADBEEF` | Not a recognized JNI version | **No.** The JVM refuses to load |

**Key decision point:** `JNI_OnLoad` does not return `JNI_OK` just because initialization steps succeeded. It must return a **valid JNI version required by the library**.

Standard logic example:

~~~c
JNIEnv *env = NULL;

if ((*vm)->GetEnv(vm, (void **) &env,
                  JNI_VERSION_1_6) != JNI_OK) {
    return JNI_ERR;       /* Cannot set up JNI */
}

/* Perform other initialization steps ... */

return JNI_VERSION_1_6;   /* Accept the required JNI version */
~~~

If the JVM **does not recognize the version** returned by `JNI_OnLoad`, the specification states that the JVM will **unload the library and behave as if the library had not been loaded**. When returning `JNI_ERR` or encountering an internal error while the hook runs, the Java application will not have a valid native library to use; on common JVMs, the load operation typically throws `UnsatisfiedLinkError`. The exact message and wrapped cause depend on the JVM and situation. Do not try to match a fixed error message string.

**Do not conflate:** `JNI_VERSION_1_6` is strictly **version negotiation**, not the running JDK version, nor a value indicating how many native methods were registered or how many native resources were allocated.

## 5. Complete Practical Example: Initializing and Registering a Native Method

We will build an illustrative C11 library:

1. Java loads the library via `System.loadLibrary("onload_demo")`.
2. The JVM looks up `JNI_OnLoad` and calls the hook.
3. The hook uses `GetEnv`, `FindClass`, and `RegisterNatives` to register the native method before Java calls it.
4. The hook checks the return code at each step and returns `JNI_VERSION_1_6` on success.
5. Java calls `plusOne(41)` and receives `42`.

The benefit of this example is making clear that **`RegisterNatives` returns `JNI_OK`**, whereas **`JNI_OnLoad` must return `JNI_VERSION_1_6`**.

### 5.1. Java File: `JniOnLoadDemo.java`

~~~java
public final class JniOnLoadDemo {
    static {
        System.loadLibrary("onload_demo");
        System.out.println("Java: library ready");
    }

    private JniOnLoadDemo() {
    }

    private static native int plusOne(int input);

    public static void main(String[] args) {
        int result = plusOne(41);
        System.out.println("Java: plusOne(41) = " + result);
    }
}
~~~

Notes:

- `native` only declares the method, **without** a Java method body.
- When the `JniOnLoadDemo` class is initialized, `System.loadLibrary` runs before printing `"library ready"`. If loading fails, that line **is not printed**.
- In this example, `plusOne` is `private static native`. The `RegisterNatives` mechanism can still register it by name and descriptor.
- Java `int` corresponds to the JNI type `jint`; `plusOne(41)` avoids overflow issues in the example.

Compile the Java file and generate the header from the directory containing the file:

~~~bash
javac -h . JniOnLoadDemo.java
~~~

The command creates `JniOnLoadDemo.class` and `JniOnLoadDemo.h`. The generated header contains a prototype with the traditional JNI name:

~~~c
/* Summary of declaration style generated by javac -h. */
JNIEXPORT jint JNICALL Java_JniOnLoadDemo_plusOne(
        JNIEnv *, jclass, jint);
~~~

**Important point to understand:** because the example chooses **`RegisterNatives`** to bind the name `plusOne` to the C pointer `native_plus_one`, **there is no need to export the function `Java_JniOnLoadDemo_plusOne`** in the library. Both linking approaches are allowed by JNI. The generated header helps verify the correct types; registration is a design choice of this example.

### 5.2. C File: `onload_demo.c`

~~~c
#include <jni.h>

/* Correct C signature for Java static native int plusOne(int). */
static jint JNICALL native_plus_one(
        JNIEnv *env, jclass declaringClass, jint input) {
    (void) env;
    (void) declaringClass;
    return input + 1;
}

/*
 * JVM calls this hook when loading the library via the JNI load mechanism.
 * Returns JNI_VERSION_1_6 when setup succeeds.
 */
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(vm, (void **) &env,
                      JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    /*
     * When called from JNI_OnLoad, FindClass uses the class loader
     * of the class loading the library.
     */
    jclass localClass = (*env)->FindClass(
            env, "JniOnLoadDemo");
    if (localClass == NULL) {
        /* FindClass may have left a pending Java exception. */
        return JNI_ERR;
    }

    JNINativeMethod methods[] = {
        {
            "plusOne",
            "(I)I",
            (void *) native_plus_one
        }
    };

    jint registerStatus = (*env)->RegisterNatives(
            env, localClass, methods, 1);

    (*env)->DeleteLocalRef(env, localClass);

    if (registerStatus != JNI_OK) {
        /* Registration failed: do not report load success. */
        return JNI_ERR;
    }

    /* Return VERSION, do not return registerStatus/JNI_OK. */
    return JNI_VERSION_1_6;
}
~~~

This is **all the C code required**; there is no need to define `Java_JniOnLoadDemo_plusOne`. `#include <jni.h>` provides the JNI types/functions. Once `JniOnLoadDemo.h` exists, you can also include that header so the compiler compares types at the traditional declaration level, but since registration is used here, the C file focuses on the `JNINativeMethod` signature.

Step-by-step explanation:

1. `GetEnv` obtains the JNI interface appropriate for **the thread running the hook**; if it returns anything other than `JNI_OK`, the hook rejects initialization.
2. `FindClass("JniOnLoadDemo")` finds the Java class to register. Because the code runs inside `JNI_OnLoad`, the selected loader is **the loader of the class loading the native library**.
3. `JNINativeMethod` describes three parts: the name `plusOne`, the JNI method descriptor `"(I)I"`, and the pointer to the C function `native_plus_one`.
4. `RegisterNatives` registers one entry. `registerStatus == JNI_OK` means the operation succeeded; any other error code means you should not proceed as if setup were valid.
5. `DeleteLocalRef` frees the local `jclass` after use. Do not cache a local reference beyond the hook.
6. The hook returns `JNI_VERSION_1_6` after all conditions are met. Afterward, `System.loadLibrary` returns to Java and the program can then call `plusOne`.

**Note on function pointers:** the `fnPtr` field of `JNINativeMethod` has type `void *` per the JNI C API, and the example casts the function pointer to `void *` as commonly done in JNI implementations; this cast may not be strictly portable under pure ISO C outside supported JNI ABIs. Therefore, always use a compiler/ABI matching the target JVM and avoid blindly suppressing warnings.

**Note on pending exceptions:** if `FindClass` or `RegisterNatives` fails, there may be a pending Java exception. The example returns `JNI_ERR` so it does not report load success; the exact error Java sees may depend on the JVM. In production, log error details via appropriate native logging, reclaim owned resources, and avoid arbitrarily calling JNI APIs while a pending exception exists. `DeleteLocalRef` is permitted in related cleanup situations.

### 5.3. Compiling the Library for Each Operating System

`JAVA_HOME` must point to the **JDK 17+** root directory containing `include/jni.h`. Use a compiler with the same architecture/ABI as the JVM, for example both x64 or both ARM64.

**Linux (GCC/Clang):**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  onload_demo.c -o libonload_demo.so
~~~

**macOS (Clang):**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  onload_demo.c -o libonload_demo.dylib
~~~

**Windows x64 (x64 Native Tools Command Prompt for Visual Studio):**

~~~bat
cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" onload_demo.c /link /OUT:onload_demo.dll
~~~

Run only **one command group for your platform**. Place the output library in the directory containing `JniOnLoadDemo.class`. If using MSVC x64, make sure to open the x64 Developer Command Prompt; do not load a binary with a different architecture from the JVM. On operating systems with controlled lookup for dependent libraries, you may also need to configure paths to the library's own dependencies.

### 5.4. Running the Program and Checking stdout

~~~bash
java -Djava.library.path=. JniOnLoadDemo
~~~

Stdout output when loading and registration succeed:

~~~text
Java: library ready
Java: plusOne(41) = 42
~~~

The first line is only printed **after `System.loadLibrary` has completed**, because the `println` statement comes after the load in the same static initializer. The second line proves `RegisterNatives` bound `plusOne(int)` to the C function returning `42`.

**When calling `plusOne`, the JVM passes two implicit arguments:** `JNIEnv *` of the current thread and `jclass` because this is a static native method; only then comes `jint input`. Thus the C function has three parameters even though the Java method declares only one `int`.

If you omit `RegisterNatives` without exporting a function following JNI naming rules, the library may still **load successfully**, but when calling `plusOne` it will fail to find the native implementation. That is a **method linking error**, distinct from an error occurring inside `JNI_OnLoad`.

## 6. Handling Step-by-Step Results and Recovering on Error

In native initialization, you must not look at one successful step and assume the entire library is initialized. Different types of results:

| Call | Success indicator | How to handle failure |
| --- | --- | --- |
| `GetEnv(vm, ..., JNI_VERSION_1_6)` | `JNI_OK`, valid `env` | Stop hook, return `JNI_ERR` |
| `FindClass(env, name)` | `jclass != NULL` | Check pending exception and class loader reason; stop hook |
| `GetMethodID` / `GetStaticMethodID` if caching methods | ID not `NULL` | Check descriptor, release created resources |
| `NewGlobalRef` if creating persistent references | Reference not `NULL` | Clean up previous resources and stop |
| `RegisterNatives` | `JNI_OK` | Check name, signature, static/instance method; stop |
| `JNI_OnLoad` | Returns a `JNI_VERSION_*` supported by the VM | Invalid JNI version or failed initialization causes load to fail |

Diagram form:

~~~text
GetEnv?
  +-- fail --> cleanup if needed --> JNI_ERR
  |
  v
FindClass?
  +-- fail --> handle exception/cleanup --> JNI_ERR
  |
  v
RegisterNatives?
  +-- fail --> release local/global resources --> JNI_ERR
  |
  v
return JNI_VERSION_1_6
~~~

### 6.1. When an Initialization Step Fails

For example, `FindClass` cannot find a class because the internal name is wrong, a custom loader cannot see the class, or a dependency is missing. `FindClass` may return `NULL` and leave a `NoClassDefFoundError`. `RegisterNatives` may return an error code or have a Java exception such as `NoSuchMethodError` if the method/descriptor does not match.

After an error:

1. **Do not dereference** a `NULL` pointer or use an uninitialized method ID.
2. Clean up previously allocated **native resources** (buffers, mutexes, file handles, opened connections) before returning.
3. Clean up JNI local/global references per contract; cleanup functions allowed while an exception is pending must be chosen carefully.
4. Return a value indicating that loading **did not complete**, such as `JNI_ERR`, instead of a valid version.
5. Avoid calling `ExceptionClear` by default to hide errors; only clear when there is a clear error-translation policy and diagnostic information is preserved.

`JNI_OnUnload` **is not the sole place to fix `JNI_OnLoad` mistakes**: when loading has not succeeded, do not rely on the JVM calling the unload hook to free every resource you allocated. Design local step-by-step cleanup and clear ownership management.

### 6.2. If Caching Multiple Items, Design "All-or-Nothing" State

For example, a library needs to cache `jclass` and `jmethodID`:

~~~c
/* Illustrative algorithm snippet; not standalone source. */
jclass local = (*env)->FindClass(env, "com/example/Bridge");
if (local == NULL) {
    return JNI_ERR;
}

jclass global = (jclass) (*env)->NewGlobalRef(env, local);
(*env)->DeleteLocalRef(env, local);
if (global == NULL) {
    return JNI_ERR;
}

jmethodID callback = (*env)->GetStaticMethodID(
        env, global, "callback", "(I)V");

if (callback == NULL) {
    (*env)->DeleteGlobalRef(env, global);
    return JNI_ERR;
}

/* Only here publish the complete state for other workers:
   storedClass = global;
   storedMethod = callback;
   return JNI_VERSION_1_6; */
~~~

In real code, you must define the state structure, thread synchronization, and cleanup policy clearly. **`jclass` is a JNI reference**; to keep it across multiple calls it must be a **global reference**; `jmethodID` is not an object reference and is only valid while the associated class remains alive. Do not store `JNIEnv *` globally because it is tied to a specific thread.

Strings passed to `FindClass` use JNI names like `"com/example/Bridge"` (with slashes). `GetStaticMethodID` uses method descriptor `"(I)V"` if the static callback takes `int` and returns `void`. Every descriptor must match the actual loaded class.

### 6.3. Should You Catch/Clear Exceptions During `JNI_OnLoad`?

A failed JNI API call may leave a Java exception in a **pending** state. Native code can check for it using `ExceptionCheck`; in debug environments, use `ExceptionDescribe` in a controlled manner. However, while an exception is pending, you must not continue calling arbitrary JNI functions: only a specific set of cleanup/exception operations is valid. Returning a failure code from `JNI_OnLoad` while an exception is pending can produce different behaviors across JVMs, so production error paths should have a consistent policy.

A useful rule of thumb:

- **Error information for Java to handle:** let the JVM/Java receive the cause per the JNI contract when appropriate.
- **Error information to log natively:** log before/after safe cleanup without losing the original exception.
- **Error translation:** if you genuinely want to convert it into a single native initialization error, do so intentionally and record the cause; do not call `ExceptionClear` unconditionally.

Do not attempt to create more Java objects, invoke callbacks, or look up more classes after a JNI call has failed unless the exception state has been handled.

## 7. `JNI_OnUnload` and Resource Cleanup Responsibilities

A dynamically linked library can export the hook:

~~~c
JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;

    /* Clean up only resources owned by the library
       and guaranteed no longer used by any thread. */
}
~~~

`JNI_OnUnload` is called by the JVM when the class loader containing the native library is garbage-collected per the specification. However, **do not rely on it as a guarantee that it will run at JVM exit or after every `System.loadLibrary`**. Many applications use the application/system class loader for the lifetime of the process; do not expect the unload hook to always run before the process terminates.

For special resources such as native worker threads, sockets, and global references, proactively provide an application-level **close/cleanup API** when deterministic release is required. `JNI_OnUnload` is only a supplementary cleanup point aligned with the GC/class-loader lifecycle.

### 7.1. Limitations of the Unload Hook

- `JNI_OnUnload` receives `JavaVM *`, with no `JNIEnv *` passed directly.
- The JVM may invoke unload in an **unspecified context**. You should not perform arbitrary Java callbacks or operations that depend on a class loader that has already disappeared.
- `FindClass` inside `JNI_OnUnload` uses the **system class loader**, differing from the rule in `JNI_OnLoad`.
- A strong global `jclass` reference can **prevent the class and class loader from being collected**, so waiting until `JNI_OnUnload` to delete references can create unintended lifecycles.
- Do not free resources while native methods or background threads are still using them.

For the running example in section 5, we **do not allocate global JNI references or separate OS resources**, so `JNI_OnUnload` is not needed for the program to work properly. `RegisterNatives` in the example only creates registrations tied to the lifecycle of the library and class when loading succeeds.

## 8. Class Loaders: Why `FindClass` in `JNI_OnLoad` Is Often Preferred

When `JNI_OnLoad` runs, `FindClass` uses the loader of **the class loading the library**. This is very useful in plugin applications: `FindClass("com/example/PluginBridge")` can find a class defined by a plugin loader, whereas a native worker thread that attaches later on its own might only see the system loader.

The difference:

| `FindClass` Context | Associated Loader |
| --- | --- |
| `JNI_OnLoad` | Loader of the class invoking the library load operation |
| Normal native method | Loader of the class declaring the native method |
| Self-attached native thread with no native method context | System loader per the Invocation Interface |
| `JNI_OnUnload` | System class loader |

Therefore, a common strategy is to look up classes/methods at load time, and only **cache valid references** for use from other threads. If caching `jclass`, you must create a global reference via `NewGlobalRef` and manage `DeleteGlobalRef`. Do not keep a local `jclass` in a static variable for use after `JNI_OnLoad` finishes.

**Class initialization reentrancy warning:** `JNI_OnLoad` typically runs directly inside the `static` initializer that calls `System.loadLibrary`. Code inside the hook should not call back into Java methods or trigger circular initialization dependencies while the relevant classes are still being initialized. For example, only `FindClass` and `RegisterNatives` a simple method, avoiding nested callbacks.

According to the JNI Specification, **a native library cannot be arbitrarily loaded simultaneously by two independent class loaders** in the same JVM. Attempting to reload the same library from another loader can cause `UnsatisfiedLinkError`. When using plugins/hot-reload, consider having a native bridge class loaded by a stable loader, or structuring libraries/modules to match each loader's lifecycle.

## 9. Do Not Use `JNI_OnLoad` to Replace the Entire Program

`JNI_OnLoad` is an **initialization hook**, not the place to put everything the application will do.

Do:

- Obtain `JNIEnv *` and verify API capabilities.
- Register the required native methods.
- Look up known IDs/classes within a small scope.
- Initialize minimal native resources, with rollback/cleanup on error.
- Return a supported JNI version when all conditions are valid.

Limit or avoid:

- Calling Java callbacks too early while classes are initializing.
- Starting threads and letting them use partially initialized state.
- Performing network RPCs, loading remote configurations, or long I/O that blocks `System.loadLibrary` for a long time.
- Holding a mutex and calling complex Java code/loaders leading to deadlock.
- Allocating global references without lifecycle cleanup.
- Putting business logic that needs to run on every invocation into a hook that normally runs only when loading the library.

There is no specific timeout imposed by the JNI Specification for `JNI_OnLoad`, but the hook runs during library loading, so any delay here delays **class initialization / library readiness** for the application. Put time-consuming operations or ones prone to network failure into a more explicit initialization API when actually needed.

## 10. C++: Preserving the Export Name and Calling Convention

If written in C++, you must ensure the `JNI_OnLoad` symbol is exported with **C linkage** so the JVM finds the exact name; default C++ code can undergo name mangling.

Example of a **conceptually standalone minimal C++ hook**:

~~~cpp
#include <jni.h>

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void **>(&env),
                   JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}
~~~

In C++, use `vm->GetEnv(...)` and `env->FindClass(...)` instead of C's two-level syntax `(*vm)->GetEnv(vm, ...)`/`(*env)->FindClass(env, ...)`.

For JNI methods registered with `RegisterNatives`, the function pointer must point to a function with the correct JNI signature. Typically, a matching `static` or `extern "C"` C++ function is used with `reinterpret_cast<void *>(...)` per JNI toolchain conventions; do not let C++ exceptions escape across the JNI boundary. If C++ initialization can throw exceptions, catch them, clean up, log the native error, and return an appropriate error code per application policy.

**Do not confuse:** the export name of `JNI_OnLoad` must be exact; whereas the name of a C++ function **registered via `RegisterNatives`** does not have to take the form `Java_package_Class_method`. The declared JNI method descriptor and function pointer are the contract used by the JVM in the dynamic registration case.

## 11. When the Hook Does Not Exist or Is Not Called

There are several cases:

- **`JNI_OnLoad` is not defined:** the JVM can still load the library and look up native methods by JNI name. Per the specification, the JVM assumes the library only requires JNI `JNI_VERSION_1_1`.
- **Defined, but the symbol is not exported:** due to missing `JNIEXPORT`/C linkage or an incorrect build toolchain; the JVM may not see the hook and treat it as absent.
- **Library file exists, `System.loadLibrary`/`System.load` has not been called yet:** the JNI load hook has no reason to run yet.
- **Java loads the library once, then calls many native methods:** do not expect `JNI_OnLoad` to run again **before every method call**.
- **Library is statically linked into the JVM:** the JNI specification distinguishes the `JNI_OnLoad_L` hook for a static library named `L` (and requires JNI version at least `JNI_VERSION_1_8`), which differs from `JNI_OnLoad` for dynamic libraries. Do not apply this static-link rule to `.so/.dylib/.dll` examples.

To diagnose the hook, inspect the actual symbols:

~~~bash
# Linux ELF
nm -D libonload_demo.so

# macOS Mach-O
nm -gU libonload_demo.dylib
~~~

Windows (Developer Command Prompt):

~~~bat
dumpbin /exports onload_demo.dll
~~~

Look for the `JNI_OnLoad` symbol. The name may appear decorated on some older ABIs/architectures; follow `JNIEXPORT`/`JNICALL` and the target toolchain. If built for the wrong architecture, the JVM may fail **before calling the hook**.

## 12. Common Errors and Symptoms

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `UnsatisfiedLinkError: no onload_demo in java.library.path` | JVM cannot find the library file | OS-specific logical/file name, `-Djava.library.path` path, architecture |
| `UnsatisfiedLinkError` about JNI version at load time | `JNI_OnLoad` returned `JNI_OK`, `JNI_ERR`, or an unsupported version | Return the proper supported `JNI_VERSION_*` constant when setup succeeds |
| `UnsatisfiedLinkError` only when native method runs | Registration failed/no exported `Java_*` symbol | Compare `JNINativeMethod`, `javac -h` header, name/signature, and linking |
| `RegisterNatives` returns error or leaves pending exception | Method does not exist, wrong descriptor, wrong class | Check `"(I)I"` and verify the method is `static native int plusOne(int)` |
| `FindClass` cannot find class at load time | Wrong internal name, loader cannot see class, missing dependency | Use slash-separated name; check the class calling `loadLibrary`/loader context |
| JVM crash or hard-to-reproduce error from native worker | Cached `JNIEnv *`/local `jclass` out of scope or race with init | Each thread obtains its own `JNIEnv *`; use valid global ref/cleanup |
| C++ hook is in source but JVM does not call it | Name mangling or symbol not exported | `extern "C" JNIEXPORT jint JNICALL JNI_OnLoad`; verify exports |
| Error only on plugin hot reload | Global refs keep class loader alive or same library loaded by another loader | Design owner loader, explicit cleanup, and bridge |
| Expecting `JNI_OnUnload` but not seeing it | Loader is still alive; JVM may exit before unloading | Do not use unload hook as a shutdown guarantee; close resources proactively |

### 12.1. JNI Checking Tool

On HotSpot/OpenJDK, you can re-run the example with:

~~~bash
java -Xcheck:jni -Djava.library.path=. JniOnLoadDemo
~~~

`-Xcheck:jni` helps detect many JNI usage errors, but does not guarantee catching every memory/ABI/lifecycle error; combine it with Java stack traces, symbol exports, JDK version, and native logs. Correct code still prints the two stdout lines in section 5.

When encountering `ExceptionInInitializerError` or `NoClassDefFoundError` about failing to initialize a class, look for the **initial error** originating from `System.loadLibrary` in the static initializer; subsequent uses of the class may produce a different message than the first time.

## 13. Checklist for Applying to Real JNI Libraries

- Which class owns `System.loadLibrary` and which class loader loads it?
- Does the shared library properly export `JNI_OnLoad`, using `JNIEXPORT`/`JNICALL` and C linkage if C++?
- Does the hook call `GetEnv` with the version actually required by the library?
- Do all `FindClass`, `RegisterNatives`, and `NewGlobalRef` operations check their results?
- Are status codes `JNI_OK`/`JNI_ERR` distinguished from the **JNI_VERSION** returned from the hook?
- When partial setup fails, are **all owned resources** released without continuing with half-initialized state?
- Are long callbacks/I/O and reentrancy into initializing classes avoided?
- Do local/global references, method IDs, and JNI env have the correct thread/lifetime scope?
- Is there a proactive unload/cleanup policy when plugins need reloading?
- Does the build have the right OS/ABI, paths, and symbols? Were `javac -h`/JNI descriptors used to verify registered methods?
- When the app encounters a load error, were **load library**, **JNI_OnLoad initialization**, and **native method resolution** diagnosed as three separate steps?

## 14. Self-Check Questions

**1.** `RegisterNatives` returns `JNI_OK`. Can you `return JNI_OK;` from `JNI_OnLoad`?  
**Answer:** **No.** `JNI_OnLoad` must return a JNI version supported by the JVM, such as `JNI_VERSION_1_6`, if initialization succeeds.

**2.** Does `JNI_OnLoad` receive `JNIEnv *` directly?  
**Answer:** No; it receives `JavaVM *` and obtains the current thread's `JNIEnv *` via `GetEnv`.

**3.** What must the JVM do if the hook returns an unrecognized version?  
**Answer:** Refuse to load, unload the library, and behave as if the library had not been loaded per the specification.

**4.** Why can `FindClass` find a plugin class inside `JNI_OnLoad` but fail from a self-attached worker thread?  
**Answer:** In `JNI_OnLoad`, JNI uses the loader of the class loading the library; a native thread with no native method context typically uses the system loader.

**5.** Can you store the `JNIEnv *` returned by `GetEnv` and use it across all worker threads?  
**Answer:** No. `JNIEnv *` is thread-bound; store `JavaVM *` and obtain a separate `JNIEnv *` for each thread.

**6.** What happens if `plusOne` is registered with descriptor `"(J)I"` while Java declares `native int plusOne(int)`?  
**Answer:** Signature mismatch (Java `long` vs `int`); `RegisterNatives` fails to register the Java method properly and the hook must handle the error rather than returning a success version.

**7.** Why should you not expect `JNI_OnUnload` to run to roll back when `JNI_OnLoad` fails?  
**Answer:** Incomplete loading does not guarantee the unload hook will clean up resources you allocated; initialization must have cleanup on error paths.

**8.** Should `JNI_OnLoad` invoke Java callbacks to start all tasks immediately?  
**Answer:** Not by default. The hook runs while the class/library is initializing; callbacks can cause reentrancy, deadlocks, or load delays. Perform only small, reliable setup there, and place longer logic in another API.

## 15. References

- [Oracle Java SE 17 — JNI Invocation API: JNI_OnLoad, JNI_OnUnload](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): hook signature, invocation timing, version return requirement, absent hook, and unload.
- [Oracle Java SE 17 — JNI Invocation API: GetEnv](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html#getenv): obtaining the thread's `JNIEnv *`, `JNI_OK`/`JNI_EVERSION`/`JNI_EDETACHED`.
- [Oracle Java SE 17 — JNI Functions: RegisterNatives](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#registernatives): `JNINativeMethod`, name, signature, function pointer, and results.
- [Oracle Java SE 17 — JNI Functions: FindClass](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): loader by native method and `JNI_OnLoad`, internal name.
- [Oracle Java SE 17 — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `jint`, `jclass`, `JavaVM`, method descriptors.
- [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): `RegisterNatives` practices in `JNI_OnLoad` and managing class loaders/refs.

**Rule of thumb:** In `JNI_OnLoad`, check each step's result using the appropriate status code, clean up resources on failure, and **return a supported JNI_VERSION** only when the entire initialization has succeeded.
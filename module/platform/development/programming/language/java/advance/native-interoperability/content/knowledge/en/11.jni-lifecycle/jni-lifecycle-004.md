# Scope and Limitations of Using UnregisterNatives in JNI

`UnregisterNatives` is a rarely needed function in JNI (Java Native Interface). It **unlinks the `native` methods of a specific Java class from the native functions currently implementing them**, returning that class to the state before its native methods were linked or registered. It does **not** mean unloading the `.so`/`.dll` file from the process, destroying Java objects, freeing any C/C++ memory regions, or safely hot-swapping native code while the program is running.

The JNI specification explicitly states that this API **should not be used in normal native code**; it is intended for certain special programs that need a reloading/relinking mechanism. Therefore, using it properly requires understanding **its scope by `jclass`**, how it interacts with `RegisterNatives`, the name-based native symbol lookup mechanism, library lifecycle, and the risks when multiple threads are calling native methods concurrently.

## 1. Exact API and Meaning

In `jni.h`, via the `JNIEnv` function table:

```c
jint UnregisterNatives(JNIEnv *env, jclass clazz);
```

In C, it is typically called via:

```c
jint rc = (*env)->UnregisterNatives(env, targetClass);
```

In C++:

```cpp
jint rc = env->UnregisterNatives(targetClass);
```

Parameters and return codes:

| Component | Meaning | What to ensure |
| --- | --- | --- |
| `env` | JNI environment of the current thread | Do not pass `NULL`; do not use a `JNIEnv*` from another thread |
| `clazz` | A `java.lang.Class` object represented by `jclass` | Must be a valid target class, not a `jobject` instance or a string name |
| Returns `0`, i.e., `JNI_OK` | JNI operation succeeded | Do not infer that the library has been unloaded or that resources have been freed |
| Returns a negative value | Operation failed | Check for a pending JNI exception and apply a clear error-reporting policy |

There is no `methodName`, `jmethodID`, or `nMethods` parameter in `UnregisterNatives`. Thus, this is **not** an API to “unregister just one method”. The scope of the call is **the native methods of the passed class**.

The JNI specification states: the class returns to the state before it was linked or registered with its native functions. This phrasing is more important than the simplistic description “clears the pointer”: a subsequent Java native method call may go through the normal JNI native function lookup/linking process again, if a suitable implementation is available.

**Do not confuse with `RegisterNatives`:**

```c
jint RegisterNatives(
    JNIEnv *env,
    jclass clazz,
    const JNINativeMethod *methods,
    jint nMethods);
```

`RegisterNatives` takes an array of `JNINativeMethod` containing the name, descriptor, and C/C++ function address; `UnregisterNatives` **does not take that array** and instead operates on the native linkage state of the target class.

## 2. Exact Scope: Which Java Class Is Affected?

Consider two different Java classes:

```java
final class AudioNative {
    static native int decode(byte[] bytes);
}

final class VideoNative {
    static native int decode(byte[] bytes);
}
```

Even though both methods are named `decode` and have the same descriptor `([B)I`, they belong to **two different classes**. Calling:

```c
(*env)->UnregisterNatives(env, audioClass);
```

only aims to change the native linkage of `AudioNative`. It is not a command to remove every method named `decode` in the JVM; it does not automatically scan all class loaders, does not destroy regular Java methods, and does not send a request to close all native libraries.

| Scope question | Conclusion |
| --- | --- |
| Is it limited to the class passed via `clazz`? | **Yes**; this is an API that operates on the native methods of a single class |
| Is there a parameter to select only one native method in the class? | **No**; if you want to design per-feature operations, you must use another mechanism |
| Does it remove bytecode, method declarations, fields, or classes from the JVM? | **No**; the Java class definition still exists |
| Does it remove native methods of another class with the same name in another class loader? | Not such a global operation; each runtime class has its own identity |
| Does calling `System.loadLibrary` a second time load a different binary? | **No**; this call does not control native library loading |
| Does it stop currently executing native stack frames? | **No such guarantee**; do not treat it as a cancel/stop mechanism |
| Does it automatically free `malloc`, file descriptors, or `NewGlobalRef`? | **No**; the respective owner must clean them up per contract |
| Does it force `JNI_OnUnload` to run? | **No**; that is a different lifecycle hook |

At the Java level, **class identity is not just the class name**: a class is identified by its name and its defining class loader. Two classes with the same binary name defined by two different loaders are two different runtime classes. Passing the exact `jclass` to `UnregisterNatives` is essential; do not use name-based heuristics and assume all copies of a plugin's class have been affected.

When a class has multiple native methods, treat `UnregisterNatives` as an operation that changes **the entire group of native bindings of that class**. If you want an API that can disable feature A individually while keeping feature B, a more common approach is to keep bindings fixed and use Java/native dispatch with controlled state, rather than unregistering the whole class.

## 3. Three Very Different Lifecycles

```text
                     Java VM / process
                            |
         +------------------+------------------+
         |                  |                  |
   Java Class         Native method        Native library
 (Class identity)       bindings            (.so/.dll)
         |                  |                  |
   defined by loader  RegisterNatives      System.loadLibrary
   may be unloaded    UnregisterNatives    JNI_OnLoad / JNI_OnUnload
   with its loader    method resolution    OS/JVM library handles
         |                  |                  |
         +------------------+------------------+
                            |
             Native heap / file / global refs
             separate, owner must clean up
```

These three lifecycles are related but **not equivalent**:

1. **Java class definition:** The JVM has the class, method declarations, and class loader. Unregistering does not remove the class.
2. **Native method linkage:** The JVM knows or is resolving the C/C++ address for a Java `native` declaration. This is the layer that `UnregisterNatives` affects.
3. **Native library lifecycle:** `System.load`/`System.loadLibrary` manages loading the library into the JVM; `JNI_OnLoad` is called when the library is loaded if exported, while `JNI_OnUnload` is tied to library/class loader unloading conditions per the specification. Unregistering **does not invoke** these operations.

Therefore, you must not infer:

```text
UnregisterNatives(clazz)
    != reverse of System.loadLibrary(...)
    != dlclose(...) / FreeLibrary(...)
    != immediate JNI_OnUnload(...)
    != free(nativeState)
    != System.gc() or class unloading
    != replacing the running native file with another build
```

Even when a class's native methods have been unregistered, the previously loaded C/C++ library may still be retained by the JVM. Other symbols in the same library can still serve other classes; global variables, native threads, callbacks, and memory allocations are not automatically reclaimed by JNI just by unregistering.

### What is the role of `JNI_OnUnload`?

`JNI_OnUnload` is an **optional function exported by the native library**, called by the JVM according to the library unload lifecycle associated with the class loader, rather than a direct callback of `UnregisterNatives`. A class loader being collected by GC and a native library becoming eligible for unloading is a separate matter; the timing/possibility of GC and unloading is not something an application is allowed to rely on to immediately free resources.

If a native library has state that needs to be destroyed, provide an explicit lifecycle API such as `close()`/`shutdown()` with clear ownership, managing threads and handles properly. Do not use unregister to “close” a database client, socket, GPU context, or native object.

## 4. After Unregistering: Why Are You Not Guaranteed to Always Get UnsatisfiedLinkError?

You must distinguish between **explicit registration** and **JNI name-based linking**.

### Linking with `RegisterNatives`

```c
static jint JNICALL impl(JNIEnv *env, jclass clazz, jint x) {
    (void)env;
    (void)clazz;
    return x + 1;
}

JNINativeMethod methods[] = {
    {"next", "(I)I", (void *)impl}
};

jint rc = (*env)->RegisterNatives(env, targetClass, methods, 1);
```

This is a **C illustrative snippet** that requires `env`, `targetClass`, the JNI header, and a Java class declaring `static native int next(int)`. The `JNINativeMethod` array contains:

- `name`: the Java native method name (modified UTF-8).
- `signature`: the JNI descriptor; `(I)I` means taking an `int` and returning an `int`.
- `fnPtr`: the address of the implementing C/C++ function, which must have the appropriate ABI/calling convention.

When `RegisterNatives` succeeds, the JVM uses the registered native pointer for that method.

### Dynamic linking by symbol name

JNI also has a mechanism to resolve a native function from an exported symbol name in the corresponding native library, for example in Java:

```java
final class NativeTarget {
    static native int twice(int value);
}
```

The library can export a corresponding JNI symbol such as:

```c
JNIEXPORT jint JNICALL
Java_NativeTarget_twice(JNIEnv *env, jclass clazz, jint value);
```

This is a **declaration**, not a standalone implementation. In this case, when the native binding is returned to the unlinked state, the JVM can **find the symbol** to re-link it on the next Java call. Therefore:

> “Because `UnregisterNatives` was called, the method will definitely throw `UnsatisfiedLinkError` forever” is a **false** conclusion.

Conversely, if the implementation is registered via `RegisterNatives` and **there is no corresponding exported JNI symbol for the JVM to find automatically**, a Java call after unregistering **will normally fail to find an implementation** and throw `UnsatisfiedLinkError`. The hands-on example below intentionally constructs that exact condition, then re-registers to prove that the method still exists and can be linked again.

### Unregister is not a security lock mechanism

If the goal is “do not allow users to call the native function anymore”, unregister is not a security boundary. The method can be re-registered by sufficiently privileged native code or re-linked by name; the native library and other function pointers still exist. Access control must be enforced at the Java API, module/boundary, native access configuration, authentication, and proper ownership design.

## 5. Proper Usage Model in Special Programs

The specification treats `UnregisterNatives` as an API for specialized cases that coordinate relinking, **not a default shutdown routine**. When a binding-swap cycle is genuinely needed in a framework or test harness, at a minimum you must:

1. **Identify the owner class clearly:** the target `jclass`, class loader, and list of involved native methods.
2. **Stop accepting new calls:** the application owns a quiescence/coordination mechanism; do not let other Java code freely invoke the target during the state transition.
3. **Wait for in-flight calls to finish:** handle native callbacks, tasks, background threads, and related references as well. Unregister does not stop them on its own.
4. **Keep the old code/library valid while there are still users:** do not `dlclose`/unmap/overwrite the binary just because you just unregistered.
5. **Call unregister on the exact class:** check the return code; do not treat `0` as proof of unloading.
6. **If needed, re-register/re-resolve intentionally:** use `RegisterNatives` with the exact name, descriptor, ABI, and function pointers. Check the result.
7. **Restore traffic only when the state is complete:** the classes and all native dependencies have consistent versions; have a recovery path if any step fails.
8. **Track resource ownership and class loaders separately:** do not use JNI linkage as a lifecycle manager for `malloc`, global refs, and native subsystems.

Even the process above is only a **safe design principle**, not a guarantee that every JVM supports hot swapping live native code. If you need to change the binary/ABI of a production service, a more stable strategy is usually a **JVM restart/rolling deployment** with the new binary.

## 6. Complete Example: Register → Unregister → Re-register (Java 17+)

The example demonstrates the exact class-level scope, consisting of three Java files and one C file. Two classes must be separated:

- **`NativeRegistry`:** the **controller** class with two native methods linked by the JVM via the symbol name `Java_NativeRegistry_...`. This class is **not** unregistered.
- **`NativeTarget`:** the **target** class with two native methods linked **only via `RegisterNatives`**, without exporting `Java_NativeTarget_...` symbols. `UnregisterNatives(env, NativeTarget.class)` will break the bindings of both.
- **`UnregisterNativesDemo`:** the Java program that runs a sequential cycle for observation.

The example is written for **Linux, OpenJDK/HotSpot JDK 17+, and a C compiler with shared library support**. Newer JDK versions may require additional native access/module configuration; running with JDK 17 or 21 is a straightforward way to practice. Do not perform unregister while another thread is using the target.

### File A — `NativeTarget.java`

```java
public final class NativeTarget {
    private NativeTarget() {
    }

    static native int twice(int value);
    static native int add(int left, int right);
}
```

This is the class on which unregister is performed. Note that we do not place `System.loadLibrary` here and do not write native implementations with standard JNI symbol names `Java_NativeTarget_twice`/`Java_NativeTarget_add`. The two methods can be registered with `RegisterNatives` from the controller's library.

### File B — `NativeRegistry.java`

```java
public final class NativeRegistry {
    static {
        System.loadLibrary("unregisterdemo");
    }

    private NativeRegistry() {
    }

    static native void registerTarget(Class<?> targetClass);
    static native void unregisterTarget(Class<?> targetClass);
}
```

The controller class loads the `unregisterdemo` library and has its own native methods. Separating the classes is necessary because if `registerTarget` and `unregisterTarget` were in the same class as the target native methods, unregistering the whole class could remove **the bindings of the controller methods themselves**, making re-registration impossible as planned.

### File C — `UnregisterNativesDemo.java`

```java
public final class UnregisterNativesDemo {
    public static void main(String[] args) {
        // Loading NativeRegistry for the first time will call System.loadLibrary.
        NativeRegistry.registerTarget(NativeTarget.class);

        System.out.println(
                "beforeUnregister=" + NativeTarget.twice(21));
        System.out.println(
                "sum=" + NativeTarget.add(3, 4));

        // Unregister all native methods of NativeTarget.
        NativeRegistry.unregisterTarget(NativeTarget.class);

        try {
            NativeTarget.twice(21);
            System.out.println("unexpected=linked");
        } catch (UnsatisfiedLinkError expected) {
            // The demo intentionally does not export Java_NativeTarget_twice.
            System.out.println(
                    "afterUnregister=UnsatisfiedLinkError");
        }

        // The controller belongs to a different class, so it can still be called.
        NativeRegistry.registerTarget(NativeTarget.class);

        System.out.println(
                "afterReRegister=" + NativeTarget.twice(21));
        System.out.println(
                "sumAgain=" + NativeTarget.add(3, 4));
    }
}
```

The code contains no loops or multiple threads. `UnsatisfiedLinkError` is caught solely to demonstrate the case where **there is no fallback native symbol after unregister**; this exception should not be used as on/off logic for a production API.

### File D — `unregister_demo.c`

```c
#include "NativeRegistry.h"  /* Header generated by javac -h. */

/* Two implementations with only internal linkage to the C file. */
static jint JNICALL target_twice(JNIEnv *env, jclass owner, jint x) {
    (void)env;
    (void)owner;
    return x * 2;
}

static jint JNICALL target_add(JNIEnv *env, jclass owner,
                              jint a, jint b) {
    (void)env;
    (void)owner;
    return a + b;
}

/*
 * Name/descriptor must match the two Java declarations exactly:
 * NativeTarget.twice(int)    -> (I)I
 * NativeTarget.add(int,int)  -> (II)I
 *
 * JNI uses void* for fnPtr per the JNINativeMethod definition.
 */
static JNINativeMethod target_methods[] = {
    {"twice", "(I)I", (void *)target_twice},
    {"add",   "(II)I", (void *)target_add}
};

/* Only throw an additional error if there is no pending Java exception. */
static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

/* Dynamic symbol export of the CONTROLLER CLASS NativeRegistry. */
JNIEXPORT void JNICALL
Java_NativeRegistry_registerTarget(JNIEnv *env, jclass owner,
                                   jclass target) {
    (void)owner;
    if (target == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "targetClass");
        return;
    }

    jint result = (*env)->RegisterNatives(
            env, target, target_methods, 2);
    if (result != JNI_OK) {
        /* If JNI has already thrown NoSuchMethodError, preserve the exception. */
        throw_if_no_pending(env, "java/lang/UnsatisfiedLinkError",
                            "RegisterNatives failed");
    }
}

/* Dynamic symbol export of the CONTROLLER CLASS NativeRegistry. */
JNIEXPORT void JNICALL
Java_NativeRegistry_unregisterTarget(JNIEnv *env, jclass owner,
                                     jclass target) {
    (void)owner;
    if (target == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "targetClass");
        return;
    }

    jint result = (*env)->UnregisterNatives(env, target);
    if (result != JNI_OK) {
        throw_if_no_pending(env, "java/lang/UnsatisfiedLinkError",
                            "UnregisterNatives failed");
    }
}
```

**Notes on C signature types:**

- `NativeRegistry.registerTarget(Class<?>)` is a Java `static native void`, so the JNI entry has the first two parameters `JNIEnv*` and `jclass` of the controller class, followed by `jclass target` (a `Class` reference).
- `target_twice` and `target_add` are C functions for the **static** native methods of `NativeTarget`, so the second parameter is also `jclass`. If changed to instance native methods, the second parameter must be `jobject` and the signature must be checked accordingly.
- `JNINativeMethod.name` and `signature` must match the Java declarations **exactly**; a wrong method or a non-`native` declaration can cause `RegisterNatives` to fail and throw `NoSuchMethodError`.
- The two implementations `target_twice`/`target_add` are declared `static` in C so they **do not export** symbols with standard JNI names for `NativeTarget`. Therefore, after unregister, Java calls to the target cannot find them via the `Java_NativeTarget_...` convention; this creates an observable failure branch.
- The two exported entry points of `NativeRegistry` **are not unregistered**, because `clazz` passed to `UnregisterNatives` is `NativeTarget.class`, not `NativeRegistry.class`.

The `throw_if_no_pending` helper checks for a pending exception before calling `FindClass`/`ThrowNew`. If `RegisterNatives` has already left a `NoSuchMethodError`, you should not mask the root cause with another error. This function is only used when an error needs to be reported to the caller; do not create an exception for an `UnregisterNatives` that succeeded.

### Compile and Run (Linux)

Place all four files in the **same directory**. `JAVA_HOME` must point to a JDK that has `include/jni.h` and `include/linux/jni_md.h`, and a `cc` compiler compatible with the Java process architecture.

```bash
javac -encoding UTF-8 -h . \
  NativeTarget.java NativeRegistry.java UnregisterNativesDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libunregisterdemo.so unregister_demo.c

java -Djava.library.path=. UnregisterNativesDemo
```

`javac -h .` generates `NativeRegistry.h` in the same directory, containing the prototypes of the two JNI entry points. With JDK 17/21 and a suitable Linux setup, `System.loadLibrary("unregisterdemo")` looks for the file `libunregisterdemo.so`. For Windows/macOS, different native file names and build commands are needed. On JDKs with newer restricted native access policies, you may need to enable native access for the application's module according to that JDK's documentation.

**Expected stdout when there is no fallback JNI symbol:**

```text
beforeUnregister=42
sum=7
afterUnregister=UnsatisfiedLinkError
afterReRegister=42
sumAgain=7
```

Timeline interpretation:

1. `NativeRegistry.registerTarget(NativeTarget.class)` links the two Java native methods to `target_twice` and `target_add`. Results: `twice(21)=42` and `add(3,4)=7`.
2. `UnregisterNatives(env, NativeTarget.class)` returns the native methods group of the **target class** to the unlinked state. Because `Java_NativeTarget_twice` is not exported, the subsequent call to `twice` fails to find a native implementation and throws `UnsatisfiedLinkError` (in the described demo environment).
3. `NativeRegistry` still has its two controller methods because it is a **different class**, so the subsequent `registerTarget` call can re-register the same pointers. `twice` and `add` continue running as before.
4. No step requires unloading or reloading the `libunregisterdemo.so` file. The same native binary can remain loaded throughout the entire process.

To see that the demo does not rely on exported target symbols, on Linux you can inspect the dynamic symbol table (optional command):

```bash
nm -D --defined-only libunregisterdemo.so
```

In the output you should see the symbols `Java_NativeRegistry_registerTarget` and `Java_NativeRegistry_unregisterTarget`. You **should not see** the symbols `Java_NativeTarget_twice`/`Java_NativeTarget_add`, because the example does not define those two symbols. The type/number of additional symbols depends on the compiler/linker and runtime.

The hands-on exercise above is a **demonstration of native method linkage**, not a hot-reload pattern to be applied as-is in a multithreaded application.

## 7. Why Not Call Unregister Inside the Target Class Itself?

A design that easily fails is:

```java
// Risky design: do not use as a production framework.
final class BadTarget {
    static native int calculate(int x);
    static native void unregisterSelf();
    static native void registerSelf();
}
```

If `unregisterSelf()` calls `UnregisterNatives(env, BadTarget.class)`, this operation affects the native methods of the **entire class**, including `calculate`, `unregisterSelf`, and `registerSelf`. Afterward, if there is no native symbol that can be dynamically linked again for `registerSelf`, Java will not be able to call the recovery function itself.

That is why the demo separates:

```text
NativeRegistry (control plane)
  ├── registerTarget(...)     [binding intact]
  └── unregisterTarget(...)   [binding intact]
                     |
                     v
NativeTarget (target plane)
  ├── twice(...)              [binding removed]
  └── add(...)                [binding removed]
```

Even with separate classes, a real framework still needs **synchronization coordination**. Having a re-register method does not guarantee that all threads stop calling the native target during the state transition. If using a new `RegisterNatives` version with different pointers, you must ensure the old code is not unloaded while there are active native calls/callbacks.

## 8. Class Loaders and Native Library Ownership

Each runtime `Class<?>` is associated with a defining class loader. Two plugins can both define a class named `com.example.NativeTarget` through two different class loaders. When calling `UnregisterNatives`, you need to know exactly which class object is being passed; do not just store the class name and assume the API handles all copies of that class.

JNI native libraries also have a lifecycle governed by the class loader mechanism. According to the JNI Invocation API, the same JNI native library cannot arbitrarily be loaded into two different class loaders. A second `System.loadLibrary` from a different loader may throw `UnsatisfiedLinkError` stating that the library is already loaded in another loader. **`UnregisterNatives` does not bypass this library ownership rule.**

If building a plugin host with multiple class loaders:

- Clearly manage which loader loads the native library and which loader holds the classes with native bindings.
- Do not store `jclass`/`jobject` local references across the lifetime of a native call. Use `NewGlobalRef` and `DeleteGlobalRef` when long-lived retention is genuinely needed, with a clear release policy.
- Do not treat unregister as an operation that makes the old class loader immediately eligible for GC. Global refs, native threads, callbacks, or other Java references can still keep the class loader alive.
- Do not assume creating a new class loader and loading the same native library will bypass the one-library-per-loader limit; you may need a separate-process architecture or distinct identifiers/libraries with an appropriate ABI contract.

For **ordinary applications**, configuring and loading native libraries stably at startup and keeping method bindings fixed throughout the JVM's lifetime carries far less risk than unregister/re-register cycles.

## 9. Concurrency Risks and Running Native Code

Unregister is not an **application-controlled stop-the-world API**. One thread may be executing a JNI method while another thread requests unregister. The API specification does not provide a portable guarantee that:

- Currently running native stack frames will be aborted or terminated immediately.
- The JVM will automatically wait for all native calls from the target class to exit before reporting success.
- Swapping function pointers, unloading the binary, or freeing state can happen safely right after returning `JNI_OK`.
- Calls starting between unregister and re-register will always be handled according to a single state predicted by the application.
- Native callbacks or threads outside the current Java call path have stopped running.

**Do not infer a fixed concurrency policy** from the return code of `UnregisterNatives`. When JNI/native code is holding memory or executing instructions in the old shared library, unloading or overwriting the binary too early is an OS loader, JVM, and native lifetime issue that the unregister function does not solve.

One application-level coordination approach, if you genuinely have a specialized framework:

```text
RUNNING
  |
  +-- Block new calls to target (application gate)
  |
  +-- Wait for active calls + callbacks + native tasks to reach 0
  |
  +-- UnregisterNatives(targetClass)
  |
  +-- Perform binding changes if the JVM model allows
  |
  +-- RegisterNatives(targetClass, matching signatures, pointers)
  |
  +-- Check status/recover on error
  |
  +-- Reopen application gate
  |
  v
RUNNING
```

This is only a **coordination design**, not a guaranteed hot-swap sequence for every VM or every library. The gate must cover **all** call sites; holding a regular Java lock may not be enough if native code has callbacks or background threads outside the gate's scope. For significant native ABI/binary/logic changes, **restarting the JVM** is usually the reliable operational choice.

## 10. When to Use and When Not to Use

| Need | Is `UnregisterNatives` suitable? | What to consider instead |
| --- | --- | --- |
| Specialized framework needing to test register/unregister cycles in an isolated environment | **Possibly**, with strict coordination/lifecycle | Test harness, serial execution, return code checking |
| Runtime/framework you control wanting to swap native linkage in a managed way | **Only when** contract/JVM and quiescence are verified | Dedicated binding state design, per-JVM testing |
| Ordinary JNI application loading a library and calling a few methods | **Not needed** | `System.loadLibrary` + `RegisterNatives` when needed, keep bindings stable |
| Wanting to unregister a single method while keeping other methods in the class | **Not directly supported** | Split classes or dispatch by application state |
| Wanting to unload `.so`/`.dll` and free native heap | **No** | Manage resource ownership, library/classloader lifecycle, and restart if needed |
| Wanting to enable/disable native call permission as a security boundary | **Unreliable** | Validate at Java API, native access policy, sandbox/process boundary |
| Wanting to replace native binary while threads are still running | **No safety guarantee** | Graceful shutdown + rolling restart |
| Plugin unloaded but old class loader is still held by global refs | **Does not solve root cause** | Release refs/threads and manage plugin lifecycle properly |
| Wanting to reset a C `static`/global state | **No** | Dedicated native cleanup/reset API |
| Wanting to handle `UnsatisfiedLinkError` due to wrong architecture or missing dependency | **No** | Diagnose ABI/OS loader/dependencies |

The JNI specification further warns about **`RegisterNatives`**: registering function pointers can significantly alter system behavior, including functions with security, correctness, or type safety implications. Therefore, combining register/unregister is even less suitable as an extension point for untrusted native code.

## 11. What If `UnregisterNatives` or `RegisterNatives` Fails?

### Return value is not a Java boolean

`UnregisterNatives` returns `jint`, with `JNI_OK`/`0` meaning success and a negative value meaning failure. Do not use a check like `if (rc) success`; the correct condition is `rc == JNI_OK`. JNI may leave a Java exception pending when another operation in the call path fails. Native code must check `ExceptionCheck` before calling APIs that are not allowed in a pending-exception state.

In the demo, `registerTarget`/`unregisterTarget` are `void native methods`, so failures are converted into a Java error if there is no pending exception; if there is already an original error, the helper preserves that error. A production API can return an explicit status or use a more contextual exception, depending on the contract.

### `RegisterNatives` checks names/descriptors

Common errors during registration:

- The Java method does not exist in the target class.
- The method exists but is not declared `native`.
- The descriptor is wrong: `(I)I` differs from `(J)J`; `String` uses `Ljava/lang/String;`, arrays use `[...`.
- The C function pointer name or signature does not match the static/instance kind, parameter order, or carrier type; this can cause a crash when called even if the registration step appears to succeed.
- A controller registers bindings for a **different class loader/class** with the same name.
- The binary has the wrong CPU, 32/64-bitness, native ABI, or missing dependent libraries.

`RegisterNatives` can throw `NoSuchMethodError` if a registered method is not found or is not native. Check JNI signatures with:

```bash
javap -s -p NativeTarget
```

The two descriptors in the demo will be `(I)I` and `(II)I`. You should use the header generated by `javac -h` for exported entry points, rather than guessing C function names if the class has a package, overloads, or special characters.

### When “unregistered but still callable”

Do not rush to conclude the VM is buggy: the method may have been relinked via a **JNI name-based exported native symbol**, some code may have re-registered it, or you may actually have called unregister on a **different class** from the class containing the invoked Java method. You should also rule out log output from an active call that started **before** unregister.

When practicing, ensure:

1. The native target implementation is registered only via `RegisterNatives` (no exported `Java_NativeTarget_*`).
2. The unregister call uses the exact `NativeTarget.class`.
3. There are no concurrent Java/native tasks.
4. The `UnregisterNatives` return code is `JNI_OK`.
5. No other code re-registers before testing a target call.

### When “unregistered and then the JVM crashes”

Do not treat this as normal behavior to accept. Check whether the code freed native state/library while active code was still running, called JNI on the wrong thread, used the wrong function pointer/ABI, mishandled a JNI pending exception, or called native code when the classloader/lifetime was invalid.

Enable `-Xcheck:jni` on a supporting JVM to detect many JNI interface errors; inspect `hs_err_pid*.log` and native backtraces, and use AddressSanitizer/UndefinedBehaviorSanitizer in environments where available. `-Xcheck:jni` does not prove the absence of all races or the safety of hot swapping.

## 12. Self-Check Questions

**Question 1.** Does calling `UnregisterNatives(env, SomeClass.class)` free the shared library file in the process?

**No.** It changes the native method linkage of the class; native library lifecycle belongs to a different load/unload mechanism. Global refs, threads, and native heap must be cleaned up by their owners.

**Question 2.** Why is `UnregisterNatives` not suitable for disabling `getValue()` alone in a class with two native methods `getValue()` and `setValue()`?

Because the function takes **`jclass`**, not `jmethodID` or a method name. You need to design separate classes, stateful dispatch, or a dedicated control API if you want to select individual features.

**Question 3.** After unregistering, is `NativeTarget.twice(1)` guaranteed to throw `UnsatisfiedLinkError`?

**Not necessarily.** If the VM can find a matching exported native symbol again or bindings have been re-registered, the method can be relinked. In the demo, because the implementations are only private C functions registered explicitly and there are no exported JNI symbols for `NativeTarget`, the post-unregister branch is designed to produce `UnsatisfiedLinkError`.

**Question 4.** In the demo, why can `NativeRegistry.registerTarget(...)` still be called after unregistering?

Because `UnregisterNatives` was called with `NativeTarget.class`, while `NativeRegistry` is a **different controller class**, has its own exported JNI symbols, and was not unregistered.

**Question 5.** `UnregisterNatives` returns `JNI_OK` while another thread is running a native call. Can you `dlclose` the library immediately?

**No safety guarantee.** `JNI_OK` does not prove that all active frames/native callbacks have stopped or that the code is no longer in use. You must have separate quiescence/lifecycle management, and it is best to restart when replacing a production binary.

**Question 6.** Does unregister solve the error “native library already loaded in another classloader”?

**No.** That error relates to how the JVM associates a native library with a class loader, which is different from a class's native bindings. Proper class loader/library ownership design is required.

**Question 7.** `RegisterNatives` has two entries; only one entry has a wrong descriptor. Can you assume the remaining entry was definitely registered and proceed?

**No.** You must check for `RegisterNatives` failure and exception state; do not rely on a partial state not guaranteed by the contract. Fix the name/descriptor table and only open the Java call path when registration completes successfully.

**Question 8.** What should a framework that must swap native implementations at runtime do before unregistering?

Block new calls, wait for in-flight calls/callbacks/tasks to finish, verify the exact target class and ownership, prepare a recovery plan, and only perform the operation on environments/JVMs that the framework has verified. Unregister does not do the synchronization and memory-safety work for you.

## Official Documentation

- Oracle JNI Specification — *UnregisterNatives* (prototype, class scope, and warning for special programs): https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#unregisternatives
- Oracle JNI Specification — *RegisterNatives* (`JNINativeMethod`, name/descriptor/pointer, return codes): https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html#registernatives
- Oracle JNI Specification — *Compiling, Loading and Linking Native Methods* and native/class loader: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html
- Oracle JNI Specification — *Invocation API, Library and Version Management, JNI_OnLoad/JNI_OnUnload*: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html#library-and-version-management
- Oracle Java 17 — `javac -h` generating JNI headers: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java Language Specification — *Unloading of Classes and Interfaces*: https://docs.oracle.com/en/java/javase/25/docs/specs/jls/jls-12.html#jls-12.7

**Takeaway:** `UnregisterNatives` is a **class-scoped native method unlinking** operation for specialized cases. It does **not** unload libraries, remove classes, free resources, provide hot-swap/concurrency guarantees, or unlink a single method individually. For a stable JNI application, keep native bindings fixed; if you must change the binary or ABI, prefer a controlled JVM restart process.
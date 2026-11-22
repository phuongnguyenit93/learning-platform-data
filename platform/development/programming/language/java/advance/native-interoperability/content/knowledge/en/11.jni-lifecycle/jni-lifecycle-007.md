# JNI_OnUnload, class loader unloading, and what to avoid when unloading a native library

In JNI, the question “when is a native library unloaded?” cannot be answered merely by when Java exits `main` or when an object is no longer used. **`JNI_OnUnload` is an optional hook that the JVM calls when the class loader owning the native library is garbage-collected**, not a callback guaranteed to run after every `System.loadLibrary`, when `close()` is called, or right when the process terminates. The hook is called in an **unknown context**; the JNI specification advises restricting the use of JVM services and **avoiding arbitrary Java callbacks**.

In the **JNI Lifecycle** module, this lesson distinguishes three lifecycles that are often conflated: the resource lifecycle of a Java/native handle object, the lifecycle of class definitions and `ClassLoader`, and the lifecycle of a loaded native library. We go from the `JNI_OnLoad/JNI_OnUnload` contract to the problem of a class loader being kept alive by global references, the danger points in the library unload hook, and then build a Java 17 + C11 example with **explicit resource cleanup** and a minimal unload hook. The most important goal: **the application is correct even if `JNI_OnUnload` is never called**.

## 1. Lifecycle diagram: three independent milestones

~~~text
Java ClassLoader L starts using the JNI library
      |
      | System.loadLibrary("lifecycle")
      v
JVM/OS loads liblifecycle.so / liblifecycle.dylib / lifecycle.dll
      |
      | If the library exports the hook and the JVM accepts the version:
      +----> JNI_OnLoad(JavaVM *, void *)          [on LOAD]
      |
      v
Java calls native functions / creates native resources
      |
      +----> nativeOpen(): allocates C memory
      |      nativeUse():  uses C memory
      |      nativeClose(): frees C memory         [INITIATED BY APPLICATION]
      |
      +----> There may still be objects/threads/global refs keeping L alive
      |
      v
No more strong reachability to loader L and related classes
      |
      | If GC actually determines the loader can be reclaimed
      | and the JVM performs unloading of the corresponding library
      v
JNI_OnUnload(JavaVM *, void *)                 [AT UNLOAD; NO TIMING GUARANTEE]
      |
      v
JVM/OS handles unloading the native library per runtime/platform
~~~

The stages are not synonymous:

| Event | Who decides? | Guaranteed to run `JNI_OnUnload` immediately? |
| --- | --- | --- |
| `new Resource()` creates a native handle | Application and JNI function | No |
| `Resource.close()` frees the handle | Application | No |
| Java method ends, object goes out of scope | Java program / GC eligibility | No |
| `System.gc()` is called | Only a GC hint request | No |
| Class is no longer referenced, but loader is still alive | Reachability / VM | No |
| The class loader owning the library is actually garbage collected | GC and VM's loader/library management | The hook may be called by the VM during the unload process |
| JVM shutdown / `main` return | JVM/runtime/OS | Must not be treated as a commitment to run the hook |
| `JNI_OnUnload` starts running | JVM | Must not assume an environment like a normal JNI call |

**Design rule:** Resources such as file descriptors, sockets, native heap, thread pools, large buffers, callback registrations, or GPU handles with a Java owner must be released via a deterministic close/destroy API before losing control. Do not defer them to a hook whose execution timing the program does not control.

## 2. Exact contract of the two lifecycle hooks

A dynamically linked JNI library can export two functions with standard names:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Not required to do anything here. */
}
~~~

This is a standalone C snippet illustrating **hook signatures**, not a complete Java+JNI program. A real library must also have JNI functions corresponding to the Java native methods. `JNIEXPORT` ensures the required export/visibility; `JNICALL` provides the calling convention; if `JNI_OnLoad` is present, it returns the JNI version supported by the VM. `reserved` is a reserved parameter and is unused.

### 2.1. `JNI_OnLoad`

- Is an **optional hook** called by the JVM when the dynamic library is loaded via `System.loadLibrary` or an equivalent mechanism.
- Receives `JavaVM *`, **does not receive `JNIEnv *` directly**; if JNI is used, a valid environment for the thread/context is required.
- Returns a version such as `JNI_VERSION_1_8` to indicate the minimum required JNI API; the VM rejects unsupported versions and behaves as a load failure.
- Useful for brief native-only state initialization and `RegisterNatives` when truly needed; initialization code must have an error cleanup path.
- Is not a Java class constructor, and does not replace per-object resource management.

If a dynamic library does not define `JNI_OnLoad`, the specification states that the VM assumes it only requires JNI version `JNI_VERSION_1_1`. Do not return `JNI_OK` in place of a JNI version; `JNI_OK` is a success code for other APIs, not a requested version.

### 2.2. `JNI_OnUnload`

- Is an **optional hook** called by the JVM when the class loader containing the native library is garbage-collected.
- The prototype **returns `void`**; there is no “unload consent value” for the application to use.
- Called in an **unknown context** (for example, a context related to finalization). The specification advises caution when using VM services and not making arbitrary Java callbacks.
- Does not receive `JNIEnv *` ready-made; do not assume there is a Java caller, a specific Java thread, the original context class loader, or that the JVM is ready to call any Java API.
- Is not guaranteed to align with application `close`, is not a public Java API to “unload right now”, and should not be used as the sole shutdown hook.

Calling `System.loadLibrary` **does not return a handle with an `unload()` method**. The unload mechanism belongs to the JVM and the class-loader lifecycle. Java calling `System.gc()` itself or setting a variable to `null` does not force the VM to run `JNI_OnUnload`.

### 2.3. `JNI_OnLoad_L` / `JNI_OnUnload_L`: the static linking case

The JNI specification also has hooks for **libraries statically linked into the VM image**, named with the library suffix: `JNI_OnLoad_L` and `JNI_OnUnload_L` (where `L` is the library name). This is a different mechanism from `JNI_OnLoad`/`JNI_OnUnload` for dynamic libraries. For examples using normal `.so`, `.dylib`, or `.dll`, we use the **unsuffixed** version.

Do not confuse `JNI_OnUnload_L` (the JNI unload hook for a static library) with a Java `ClassLoader` method of a similar name. The specification states that `JNI_OnUnload_L` also runs in an unknown context and requires the same cautious approach.

## 3. Who owns a native library? ClassLoader and namespaces

Each `ClassLoader` has its own class namespace. In JNI, libraries are managed per the loader that loaded them. According to the specification, **the same native library cannot be loaded simultaneously into multiple class loaders in the normal way**; requesting to load it again in another loader can throw `UnsatisfiedLinkError`. This rule prevents JNI namespaces from mixing across classloaders and allows a library to be unloaded when its corresponding loader can be reclaimed.

Example:

~~~text
ApplicationClassLoader
    |
    +-- loads liblifecycle.so
    |
    +-- class demo.LifecycleExample

PluginClassLoader A
    |
    +-- plugin classes (may refer to native integration)
    |
PluginClassLoader B
    |
    +-- plugin classes
~~~

If the library is loaded from a class in **ApplicationClassLoader**, reclaiming another plugin class loader **does not automatically unload** that library. If the library is loaded by a separate plugin loader, unloading depends on whether this plugin loader is still reachable and how the JVM/OS manages the corresponding image.

Classes with the same name defined by two different loaders are **two different class identities**. Cached `jmethodID`/`jfieldID` must be tied to the defining class and must not be transferred from an old load to a same-named class after reload. Nor should one infer that just because there is the same library path, every class loader instance can all call `System.loadLibrary` successfully.

### 3.1. When is a classloader reclaimed?

GC can typically only unload a class loader when there is no longer the required strong reachability to it and its associated classes/objects, and JVM conditions allow it. Things that often accidentally keep a loader alive:

- A Java object, thread, or task still holding an instance of a class defined by that loader.
- A thread context class loader (`Thread.currentThread().getContextClassLoader()`) still pointing to the plugin loader.
- A static registry, event bus, callback list, or executor of the parent application holding a class instance, `Class<?>`, `Method`, or listener from the plugin.
- C/C++ storing a **strong JNI global reference** to a class/object/plugin loader and not calling `DeleteGlobalRef`.
- A native thread still active/performing callbacks, or the JVM still having related stack frames/method executions.
- A framework/service still holding resources or metadata that keep the loader reachable.

**Specifically:** `jclass` is a JNI object reference to `java.lang.Class`. `NewGlobalRef(env, clazz)` creates a strong global reference that can keep the class and loader alive. If you intend to call `DeleteGlobalRef` only inside `JNI_OnUnload`, the hook may **never be called precisely because that strong reference is preventing the loader from becoming collectible**. This is a dependency cycle that cannot be fixed by “waiting longer for GC”.

### 3.2. Unload does not equal “releasing the DLL file immediately”

Even when a loader becomes eligible for GC, the timing of GC, class unloading, the JNI unload hook, and OS-level library handle release is runtime/platform behavior. The mechanism by which the JVM calls `JNI_OnUnload` is part of the JNI contract; you should not write business logic that depends on the detailed ordering of every GC phase or on whether a `.dll` file can be deleted immediately on each operating system.

Do not manually call `dlclose`/`FreeLibrary` on the library image loaded by the JVM inside `JNI_OnUnload` to “speed things up”: the JVM manages the corresponding handle, and manual unloading can cause a double unload or code running from an already unmapped binary.

## 4. What **not to do** in `JNI_OnUnload`

There are very small native-only C operations that can be used for final memory cleanup **if** ownership is certain and no users remain; however, the hook is not a safe place to run anything you would normally run from Java. Risk categories:

| Do not do in the hook | Why | Where to move that work? |
| --- | --- | --- |
| `FindClass` to look up a class of the unloading plugin | The original loader may no longer exist; `FindClass` in `JNI_OnUnload` uses the **system class loader** per the spec, not the loader at `JNI_OnLoad` | Look up before unload in a normal native call; obtain the right `Class<?>` from Java |
| `CallVoidMethod`/`CallStaticVoidMethod` to run Java cleanup | Unknown context; the callback may initialize classes, acquire locks, allocate, or re-enter the VM | Java `close()` while application state is still valid |
| Create Java objects, register listeners, access Java loggers | Can resurrect the class/loader, throw exceptions, or deadlock | Normal initialization and close paths |
| Launch/attach a new thread to the JVM | Can block, depend on VM lifecycle, or keep code/loader alive | Manage threads from `open/start`, stop/join before `close` |
| Use a `JNIEnv *` saved from an old callback | `JNIEnv *` belongs to the old thread and is invalid for another thread | Obtain a valid env during an active JNI call |
| Wait on Java thread locks/conditions | The hook has no fixed ordering with the Java lifecycle; the waiting thread may already have stopped | Orderly shutdown at the application layer |
| Long-blocking I/O, RPC/network calls, DB queries | No guaranteed SLA/timing; deadlock/hang during unload | Stop/flush from Java or native close beforehand |
| `System.gc()`, `System.exit()`, `DestroyJavaVM()` | Reentrancy or VM-wide impact from an unknown context | Lifecycle decisions belong only at the application/host layer |
| Manually `dlclose`/`FreeLibrary` one's own library | The JVM/OS is managing the native image, risk of unloading at the wrong time | Let the VM/loader do its job |
| Rely on unload ordering between JNI libraries | No contract for the desired application ordering | Manage dependencies and teardown before unloading loaders |
| Destroy native pointers still used by callbacks/threads | Use-after-free/dangling function pointers if asynchronous work remains | Stop accepting work, drain, join, then free in explicit close |
| Keep a global `jclass` until `JNI_OnUnload` | A strong ref can pin the loader, preventing the hook from running | `DeleteGlobalRef` at explicit shutdown |

The “do not” actions in the table are primarily **unsafe design decisions**, not a claim that JNI forbids the entire C standard library. Calling `free` on a **pure C** allocation, exclusively owned by the library and no longer used by anyone, can be an appropriate small cleanup. Conversely, calling `free` on a pointer borrowed from `GetStringChars` or `Get<Type>ArrayElements` is wrong: those pointers must be returned via the corresponding JNI Release function, and ideally no borrowed pointers exist by the time of unload.

### 4.1. Why is `FindClass` during unload especially dangerous?

Oracle JNI Functions states clearly: calling `FindClass` from `JNI_OnLoad` uses the class loader of the class loading the library; calling it from `JNI_OnUnload` uses the result of `ClassLoader.getSystemClassLoader()`, because the loader at load time may no longer exist.

Example you should not write:

~~~c
/* WRONG: DO NOT run; this only illustrates an anti-pattern. */
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    JNIEnv *env = NULL;
    (void)reserved;
    if ((*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_8) == JNI_OK) {
        jclass plugin = (*env)->FindClass(env, "plugin/PluginMain");
        /* Assumes the plugin class must still be findable from the old loader! */
        (void)plugin;
    }
}
~~~

The snippet above illustrates **why the logic is wrong**, not a recommended hook. It can fail, use the wrong loader, or raise a JNI exception; even if `GetEnv` succeeds, it does not turn the unload context into a normal Java callback. Do not replace `FindClass` with `Class.forName` and consider it solved: that only moves callback/class loading to an unsafe time.

### 4.2. Avoiding dependency resurrection

If the hook calls back into a Java logger, event listener, or a framework singleton, those systems may retain the class/object/loader that the JVM is trying to unload; this can create lifetime cycles, deadlocks, or partial shutdown states. You also should not throw a Java exception from the hook because it is not a Java method with a clear caller to handle exceptions per application logic.

Instead of complex code in the hook, provide a `shutdown/close` method called while the plugin is still active, able to call the Java/native services it needs, synchronously finish in-flight work, remove registrations and global refs, and only then let the loader become unreachable.

## 5. The right strategy: clean up resources **before** the classloader disappears

An application/plugin with native resources should follow this order:

~~~text
ACTIVE: Java object / plugin / native library is active
  |
  | 1. Stop accepting new requests or callbacks
  | 2. Wait for in-flight requests/native calls to finish
  | 3. Stop and join native workers; detach native threads properly
  | 4. Close file/socket/DB/GPU/native handles, return borrowed JNI refs
  | 5. Cancel native callback registrations, DeleteGlobalRef, clear caches
  | 6. Clear Java references, context classloader, and registries
  v
CLOSED: resources are freed; no native code is using old handles
  |
  | 7. If the loader becomes collectible, VM/GC may unload
  v
JNI_OnUnload: small hook, not responsible for business logic or main cleanup
~~~

A clear lifecycle in Java can rely on:

- `AutoCloseable` and `try-with-resources` for instances holding native handles.
- `close()`/`stop()` at the plugin manager layer before dropping the `ClassLoader`.
- `ExecutorService.shutdown()` and `awaitTermination()` with a reasonable timeout; native worker threads must have their own stop/join mechanism.
- Clear owner/lifetime structures for `NewGlobalRef`, `NewWeakGlobalRef`, malloc/new, callback function pointers, and OS resources.
- Idempotent cleanup: calling `close()` twice does not double-free, and every initialization error path returns acquired resources.
- Java's `Cleaner` used only as a last-resort **fallback**, not replacing `close()`, because when Cleaner runs is not guaranteed.

**The unload hook is not a destructor for every Java object.** One library may serve thousands of native handles within the same loader; closing one object does not unload the library, and library unload is not the primary place to free individual objects if those objects still need cleanup beforehand.

### 5.1. Global references and JNI caches

When C creates:

~~~c
/* Illustrative snippet in a native method with a valid env. */
jclass global_class = (jclass)(*env)->NewGlobalRef(env, local_class);
/* ... use while the class is alive ... */
(*env)->DeleteGlobalRef(env, global_class);
~~~

Each successfully created reference must be matched with exactly one deletion, after ensuring no code is still using it. Deleting too early causes a dangling reference; not deleting can keep the class/loader alive. `jmethodID` and `jfieldID` are **not** JNI object references: they must not be passed to `DeleteGlobalRef` and are only valid while the class defining the method/field remains loaded. If using a weak global `jclass` to allow unloading, you must promote the weak ref to a strong local via `NewLocalRef` for the duration of use, revalidate identity, and rebuild IDs if the old class was unloaded.

Do not trade a “fast cache” for pinning the loader for the rest of the process if the plugin needs hot reload. These references/pointers should belong to a resource owner or registry with explicit clear, rather than relying on automatic `JNI_OnUnload` cleanup.

## 6. Runnable example: Java 17 proactively calls `close`, JNI_OnUnload intentionally makes no callbacks

We create a small library with logical name `lifecycle`. Java opens a native counter, calls C to increment the value, then closes it. The C implementation has **both `JNI_OnLoad` and `JNI_OnUnload`**, but does not use the unload hook to free the Java instance's counter: the counter is freed by `nativeRelease` right inside `close()`. The result can be verified **without depending on GC**.

Structure:

~~~text
jni-lifecycle-demo/
├── src/
│   └── demo/
│       └── LifecycleExample.java
├── native/
│   └── lifecycle.c
└── build/              (created during build)
    ├── classes/
    ├── include/
    └── lib/
~~~

### 6.1. Java: full source `src/demo/LifecycleExample.java`

~~~java
package demo;

public final class LifecycleExample implements AutoCloseable {
    static {
        System.loadLibrary("lifecycle");
    }

    // 0 means not opened or already closed; only the wrapper owns the handle.
    private long nativeHandle;

    public LifecycleExample(int seed) {
        if (seed < 0) {
            throw new IllegalArgumentException("seed must be non-negative");
        }
        long opened = nativeCreate(seed);
        if (opened == 0L) {
            throw new IllegalStateException("native creation failed");
        }
        nativeHandle = opened;
    }

    public synchronized int next() {
        long current = nativeHandle;
        if (current == 0L) {
            throw new IllegalStateException("resource is closed");
        }
        return nativeNext(current);
    }

    @Override
    public synchronized void close() {
        long current = nativeHandle;
        if (current != 0L) {
            nativeHandle = 0L;
            nativeRelease(current);
        }
    }

    private static native long nativeCreate(int seed);
    private static native int nativeNext(long handle);
    private static native void nativeRelease(long handle);

    public static void main(String[] args) {
        try (LifecycleExample counter = new LifecycleExample(10)) {
            System.out.println("value=" + counter.next());
            System.out.println("value=" + counter.next());
        }
        System.out.println("closed");
    }
}
~~~

Key points to understand:

- `try (...)` calls `close()` when leaving the block, even if an exception occurs in the block body.
- `synchronized` per instance ensures `next` and `close` cannot run concurrently through the public wrapper of the same instance. `nativeHandle` is not used after being set to 0.
- `nativeCreate` is a C function that creates the resource; if a Java exception is already pending, native returns 0 and the exception is propagated back to Java. The constructor only throws `IllegalStateException` if it receives 0 with no other exception.
- `close` is idempotent in Java: if the handle is already 0, it does not release again.
- **Does not** declare `finalize()`, does not call `System.gc()`, and does not depend on whether the JVM unloads the library before or after the `closed` line.
- Making native methods `private` helps prevent ordinary Java callers from passing a fake `long` as a pointer. This is not a security boundary; production native APIs need stronger handle validation when data may come from untrusted clients.

### 6.2. C11: full source `native/lifecycle.c`

~~~c
#include "demo_LifecycleExample.h"
#include <stdint.h>
#include <stdlib.h>

_Static_assert(sizeof(void *) <= sizeof(jlong),
               "This demo requires native pointer to fit in jlong");

typedef struct {
    jint value;
} NativeCounter;

static void raise_java(JNIEnv *env, const char *class_name,
                       const char *message) {
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

/* Hook when library is loaded: do not create Java classes or threads. */
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

/* Hook when VM unloads library: do not call Java and do not wait for GC. */
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Each object's NativeCounter MUST have been closed beforehand.
       Do not run arbitrary Java callbacks in this hook. */
}

JNIEXPORT jlong JNICALL
Java_demo_LifecycleExample_nativeCreate(JNIEnv *env, jclass owner,
                                        jint seed) {
    (void)owner;

    if (seed < 0) {
        raise_java(env, "java/lang/IllegalArgumentException",
                   "seed must be non-negative");
        return 0;
    }

    NativeCounter *counter = malloc(sizeof *counter);
    if (counter == NULL) {
        raise_java(env, "java/lang/OutOfMemoryError",
                   "cannot allocate native counter");
        return 0;
    }

    counter->value = seed;
    return (jlong)(intptr_t)counter;
}

JNIEXPORT jint JNICALL
Java_demo_LifecycleExample_nativeNext(JNIEnv *env, jclass owner,
                                      jlong handle) {
    (void)owner;

    if (handle == 0) {
        raise_java(env, "java/lang/IllegalStateException",
                   "native handle is closed");
        return 0;
    }

    NativeCounter *counter = (NativeCounter *)(intptr_t)handle;
    if (counter->value == INT32_MAX) {
        raise_java(env, "java/lang/ArithmeticException",
                   "counter overflow");
        return 0;
    }

    return ++counter->value;
}

JNIEXPORT void JNICALL
Java_demo_LifecycleExample_nativeRelease(JNIEnv *env, jclass owner,
                                         jlong handle) {
    (void)env;
    (void)owner;

    if (handle != 0) {
        NativeCounter *counter = (NativeCounter *)(intptr_t)handle;
        free(counter);
    }
}
~~~

This is a **complete C11** JNI library for the example, **with no `main` in C**. Function names must match the header generated by `javac -h`. `_Static_assert` restricts the pointer-as-`jlong` usage to targets where a pointer fits in `jlong`; on unsuitable platforms or when forged/dangling handle protection is needed, replace it with an opaque handle table, generation IDs, and reference counting management.

Notice the **timing** difference:

- `JNI_OnLoad` only returns the JNI version; it does not open a resource that needs `close`. It does not need `JNIEnv *`, so it does not call `GetEnv`/`AttachCurrentThread`.
- `nativeCreate` creates a resource owned by the Java instance and returns a native handle.
- `nativeNext` only works with an open handle. Java synchronizes `next/close` calls at the instance level. If another path bypasses the wrapper and uses a raw handle, native still has no way to validate the pointer: this example is a demo, not a boundary against untrusted data.
- `nativeRelease` frees the native allocation **in a call with a clear lifecycle**.
- `JNI_OnUnload` **is not used to track down NativeCounters**: there is no registry; if an object forgets `close`, this code will leak the native allocation until the JVM/OS cleans up the process. That is why the contract requires close.

Putting `free` in `nativeRelease` rather than `JNI_OnUnload` avoids depending on GC, and avoids holding a global `jclass` that prevents the loader from ever unloading. Even if `JNI_OnUnload` does not run during the entire session, each closed instance still frees its allocation on time.

## 7. Compiling and running on Linux, macOS, Windows

The following commands run from the `jni-lifecycle-demo` directory. Requires JDK 17+, a C compiler supporting C11, and an architecture matching the JVM. `JAVA_HOME` must point to the JDK directory containing `include/jni.h`.

### 7.1. Linux (GCC or Clang)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/LifecycleExample.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/lifecycle.c -o build/lib/liblifecycle.so

java -Djava.library.path=build/lib -cp build/classes demo.LifecycleExample
~~~

### 7.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/LifecycleExample.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  native/lifecycle.c -o build/lib/liblifecycle.dylib

java -Djava.library.path=build/lib -cp build/classes demo.LifecycleExample
~~~

### 7.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib
javac -h build\include -d build\classes src\demo\LifecycleExample.java

cl /nologo /std:c11 /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" ^
  native\lifecycle.c ^
  /link /OUT:build\lib\lifecycle.dll

java -Djava.library.path=build\lib -cp build\classes demo.LifecycleExample
~~~

The lines above are Windows **Command Prompt**, with `^` for line continuation; use MSVC supporting `/std:c11` (a sufficiently recent Visual Studio 2019 or newer). `System.loadLibrary("lifecycle")` takes the **logical** name, which the JVM maps according to the OS; do not pass `.so`/`.dll` in the logical name string.

The **exact stdout** output of the example, after a successful build/load:

~~~text
value=11
value=12
closed
~~~

There is no `unloaded` line. Because the program normally uses the application class loader that lives for the entire process, `JNI_OnUnload` may **not run before the JVM exits**. Even if you print a line from the hook, it is not part of stable stdout to put in a unit test.

### 7.4. Checking that symbols are actually exported

Linux:

~~~sh
nm -D --defined-only build/lib/liblifecycle.so | \
  grep -E 'JNI_On(Load|Unload)|Java_demo_LifecycleExample'
~~~

`JNI_OnLoad`, `JNI_OnUnload`, `Java_demo_LifecycleExample_nativeCreate`, `Java_demo_LifecycleExample_nativeNext`, and `Java_demo_LifecycleExample_nativeRelease` must be present. Addresses, order, and symbol type characters depend on the binary. A native lib that has `JNI_OnUnload` in the source but does not export it due to wrong visibility will not provide the hook to the JVM.

On macOS use `nm -gU build/lib/liblifecycle.dylib` (Mach-O tools usually show a leading underscore on symbol names); on Windows use `dumpbin /exports build\lib\lifecycle.dll`. If you encounter `UnsatisfiedLinkError`, check the right file/architecture, `java.library.path`, dependencies, generated JNI header, and export table. A library load error does not mean the unload hook has run.

## 8. When does `JNI_OnUnload` actually get a chance to run?

In the example above, `demo.LifecycleExample` is loaded by the normal application class loader. This loader may live until the end of the process, so **a single-run program cannot be used to deterministically test `JNI_OnUnload`**.

An advanced test can use a **child-first/isolated URLClassLoader** that defines the plugin class containing `System.loadLibrary` itself, without loading that library first in the parent. After calling the plugin:

1. Perform `stop/close` on all native handles and stop callbacks first.
2. Clear listeners, tasks, TCCL, and strong references in parent registries to the plugin.
3. Drop the Java references held in the harness (plugin object, `Class<?>`, `Method`, loader).
4. Use `WeakReference<ClassLoader>` to observe the reachability of the loader, combined with VM class unloading logs.
5. Suggest GC and wait **with a bound**, recording the result without treating not unloading in a given run as a bug in the `JNI_OnUnload` function.

Illustration of a **non-standalone** Java harness snippet:

~~~java
// Illustrative snippet: pluginLoader is actually created/loaded externally.
WeakReference<ClassLoader> witness =
        new WeakReference<>(pluginLoader);

// Must close all plugin resources and drop all strong references.
pluginInstance = null;
pluginClass = null;
pluginLoader = null;

System.gc();  // Hint only, does not guarantee GC/unload.
System.out.println("loaderGone=" + (witness.get() == null));
// Both true and false are observable states, not assertions.
~~~

Requires `import java.lang.ref.WeakReference;`, variables `pluginLoader`, `pluginClass`, `pluginInstance` declared in a real harness, and avoiding references remaining on the stack/JIT locals. In a reliable test, perform plugin load/unload in a separate helper method, return the `WeakReference`, and only then perform the observation in the caller, avoiding locals accidentally keeping the loader alive. `System.gc()` may be disabled or deferred; class unloading logs/flags depend on the VM/version.

**Do not implement a test by loading the exact same `liblifecycle.so` file simultaneously in two class loaders and expecting both to succeed.** JNI specifies not loading the same native library into multiple class loaders simultaneously; doing so can actively throw `UnsatisfiedLinkError`. To test sequential reloads, wait for the old loader to be reclaimed and the library unloaded by the VM, or use separate library copies following proper procedures and namespaces.

### 8.1. Using HotSpot logs for diagnostics

On HotSpot/JDK 17, you can run with class-unloading-related logging; for example:

~~~sh
java -Xlog:class+unload=info \
  -Djava.library.path=build/lib \
  -cp build/classes demo.LifecycleExample
~~~

This command still only runs the **app-loader demo**, so unload logs may not appear. `-Xlog:class+unload=info` is a **HotSpot diagnostic feature**, not a standard contract required to be supported by every JVM. For a plugin-loader test, use it together with native logging designed with no side effects (for example, a small non-blocking C diagnostic) instead of taking calling `System.gc()` as definitive proof.

You should not use `JNI_OnUnload` to increment a counter in Java and wait for Java to see the counter: right when the Java class/loader is unloaded, there is no longer a reliable Java lifecycle relationship to callback and observe.

## 9. Reference cycles that prevent the hook from running: wrong example and fix

### 9.1. Wrong: `NewGlobalRef` holds the class forever, waiting for the hook to release it

~~~c
/* ANTI-PATTERN ILLUSTRATION ONLY — DO NOT MERGE INTO THE DEMO. */
static jclass cached_plugin_class;

static void remember_class(JNIEnv *env, jclass clazz) {
    cached_plugin_class =
        (jclass)(*env)->NewGlobalRef(env, clazz);
}

/* Design flaw: whether the hook can run depends on
   this very global ref having already been released! */
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    /* Cannot rely on ever reaching here to delete the ref. */
}
~~~

In this code, the strong global reference makes the class reachable. If the class is defined by a plugin loader, the reference also keeps the associated loader's lifecycle alive. Because the loader does not become collectible, the hook expected to clean up the ref may never run. This is not a GC bug, but an **ownership bug**.

### 9.2. Right: owner-driven cleanup in a normal JNI method

~~~c
/* Illustrative snippet while the Java caller is alive and calling JNI. */
static jclass cached_class;

static int init_cache(JNIEnv *env, jclass clazz) {
    jclass global = (jclass)(*env)->NewGlobalRef(env, clazz);
    if (global == NULL) {
        return 0;
    }
    cached_class = global; /* Publish only under appropriate synchronization. */
    return 1;
}

static void clear_cache(JNIEnv *env) {
    jclass old = cached_class;
    cached_class = NULL;
    if (old != NULL) {
        (*env)->DeleteGlobalRef(env, old);
    }
}
~~~

This is an **illustrative snippet**, not a standalone thread-safe implementation. It needs the same lock or owner as the active-call stop protocol so there is no race between deleting the ref and a native callback using it. When a library serves multiple class loaders or multiple owners, do not use a single global variable; use a registry keyed by class identity and avoid overwrites/leaks.

The right protocol: the application stops calling the cache, stops callbacks/workers, waits for all readers to finish, calls `clear_cache(env)` from a native method with a valid `JNIEnv *`, and then lets the loader/objects become unreachable. When GC decides to unload, there is no longer a strong global ref pinning the loader.

### 9.3. If using weak references

`NewWeakGlobalRef(env, clazz)` does not pin the referent like a strong global reference, but a weak handle can lose its object. On each use, you must create a strong local `NewLocalRef` and check for `NULL`; you must not check a weak ref and then assume it remains unchanged across GC:

~~~c
/* Illustrative snippet: weak_class is a jweak still owned by the registry. */
jclass strong = (jclass)(*env)->NewLocalRef(
    env, (jobject)weak_class);
if (strong == NULL) {
    /* Class was reclaimed or local ref could not be created:
       check for exceptions and discard old IDs when no longer valid. */
} else {
    /* Use the class's IDs while the strong local is alive. */
    (*env)->DeleteLocalRef(env, strong);
}
~~~

When there is a new class with the same name after a reload, old `jmethodID`/`jfieldID` must not be reused. The weak/global registry also has its own cleanup such as `DeleteWeakGlobalRef` per owner; do not defer indefinitely to the hook.

## 10. Native threads and callbacks: must be stopped before unload

A native worker thread may hold function pointers into the JNI library's code, be calling back into Java via `JavaVM *`, or be using objects belonging to the plugin. If the runtime unloads the binary while that thread is still executing code in the binary, the consequences can be severe. Teardown must be managed **outside the hook**:

1. Signal stop and stop accepting new work.
2. Wait for in-flight Java→native calls to complete.
3. Cancel registered native timers, callbacks, or OS event hooks.
4. Join joinable worker threads; avoid infinite waits, design an appropriate timeout.
5. Each attached native thread calls `DetachCurrentThread` itself before exiting, per the Invocation API contract.
6. Release global/weak references, owner-cached method IDs, and memory once no users remain.
7. Drop Java references to the plugin so the loader can become collectible.

`JNIEnv *` is not thread-safe to pass from one thread to another. If a worker needs JNI calls, it must obtain the environment of **that thread itself** via `GetEnv`/`AttachCurrentThread` per the rules. Attached native threads that remain alive can block VM shutdown and keep other dependencies alive. Do not pick `JNI_OnUnload` as the first place to signal stop and then wait to join: the hook may occur in an incompatible context, and the loader may be kept alive by the very workers the hook is waiting for.

If using `RegisterNatives`, the registered function pointers must also match the exact class/loader and must not allow JNI callbacks to run against unloaded code. Handle registration in init/destroy with a clear owner, rather than arbitrarily calling `UnregisterNatives` from an unknown unload context.

## 11. Can `Cleaner`, shutdown hooks, and VM termination replace `close()`?

**No.** All three are useful in their own contexts, but do not provide the same guarantee as close:

| Mechanism | When it runs | Not guaranteed |
| --- | --- | --- |
| `try-with-resources` / `AutoCloseable.close` | When Java control leaves scope or calls close | Only works when the caller actually applies it and cleanup is not interrupted by a process crash |
| `Cleaner` (Java 9+) | When the object is determined eligible and the cleaner is processed | Timing/whether it runs before process exit; ordering; Java object has already been GC'd |
| `Runtime.addShutdownHook` | During the shutdown sequence when the JVM supports it | Running on forced kill, VM crash, power loss; ordering relative to native unload |
| `JNI_OnUnload` | When the loader owning the library is GC'd/unloaded per JNI | Being called right when a Java object closes, when `main` returns, or after every library load |
| C `atexit` | C runtime process termination per platform/termination path | Being tied to the Java class-loader lifecycle; timing while the JVM is still safe |
| OS reclaiming process memory | When the process actually terminates | Flushing/closing application protocols, preserving data, cleaning up device/remote state |

`Cleaner` should be a fallback if native memory needs to be reclaimed when a caller forgets to close, but the cleaning action must not hold a strong reference to the object being cleaned. Therefore, the native handle/lifetime must be managed through a separate cleaning state and synchronized to avoid double-free with `close()`. Do not assume a native pointer is safe to free from a Cleaner if another native callback is still using it.

Shutdown hooks also have limitations: any JVM error/crash/killed process can bypass the hook; the ordering of shutdown hooks and library unloading is not a mechanism for cleaning up dependent native resources. Put **resource semantics** in `close()` and **library lifecycle semantics** in `JNI_OnLoad/OnUnload`.

## 12. Analysis of real-world scenarios

### 12.1. Servlet server hot redeploy

A plugin or web application creates a C callback using ClassLoader version A. Redeploy creates loader version B, but the callback/native registry still holds a global ref to class A. Result: loader A does not unload, memory and metadata grow steadily. Even with `JNI_OnUnload` trying to clear refs, the hook may never be called.

**Fix:** the application's lifecycle hook calls `stop()` before undeploy, stops callbacks, deletes global references, clears Java listeners/thread context loader, and only then drops loader A. Do not reload the same native binary from loader B while A has not actually been released per JNI rules; design a common native layer in the parent loader if sharing is needed.

### 12.2. A C library caches a global `JNIEnv *`

Native code saves `JNIEnv *` at load time and reuses it in the unload hook. Invalid because an env belongs to a specific thread. Even if `GetEnv` in the hook returns success, you are still in an unknown context unsuitable for making arbitrary Java calls.

**Fix:** do not cache `JNIEnv *`; each JNI entry point receives a valid env. For native workers, attach/detach before explicit shutdown. Only cache `JavaVM *` when there is a reason and VM lifetime is controlled; `JavaVM *` does not turn the hook into a safe place for callbacks.

### 12.3. Native library managing sockets/files

A library keeps a socket for repeated use; the development team only calls `close(socket)` in `JNI_OnUnload`. The server application runs for months, the loader lives for the entire process, and the socket is never closed after a session ends.

**Fix:** the native socket belongs to the session/resource owner; close it in `AutoCloseable.close()` right when the work is done. The unload hook, if present, only cleans up remaining pure-native library state that is certainly unused by anyone, and is not responsible for closing every session.

### 12.4. Hook logging via Java and deadlock

`JNI_OnUnload` tries to call a Java logging framework. The logging class may need to initialize or wait on a lock that an application thread is holding during stop, leading to deadlock or class-loader resurrection.

**Fix:** necessary logs are emitted while `stop/close` is still running in normal Java. Keep the unload hook minimal; a small, non-blocking native diagnostic with no Java callbacks if truly needed.

### 12.5. JVM exits without an "onUnload" log line

Do not jump to the conclusion that the JNI hook is broken: a default application uses the application loader, which is not GC'd during the session. JVM process exit is not a timed classloader unload test. Put unit tests properly on the public close contract and leave unloading verification to a separate harness with conditions, logs, and timeouts.

## 13. Checklist for a library with `JNI_OnUnload`

- **Owner:** Know which ClassLoader called `System.loadLibrary` and which loader manages the library; do not assume the same file can be loaded by multiple loaders simultaneously.
- **Hook signature:** `JNIEXPORT void JNICALL JNI_OnUnload(JavaVM*,void*)` properly exported; `JNI_OnLoad` returns a supported `JNI_VERSION_*`.
- **Unknown context:** No arbitrary Java callbacks, do not assume `JNIEnv *` or the original class loader is available; do not call `FindClass` to look up plugin classes during unload.
- **Reachability:** Do not hold strong global `jclass`, Java objects, TCCL, or native callbacks past their lifetime; in particular, do not rely on the unload hook to delete the very global refs pinning the loader.
- **Deterministic cleanup:** Java `AutoCloseable/close/stop` closes native resources, clears registrations/caches, stops/joins threads, and releases refs before dropping the loader.
- **No active code:** No native threads, JNI callbacks, or function pointers still running from the library when unload is possible. Do not manually `dlclose/FreeLibrary` a library managed by the JVM.
- **Concurrency:** Cleanup guards against double-free/use-after-free; resolves in-flight work and locks using an orderly stop protocol, without waiting indefinitely in the unload hook.
- **ID lifetime:** `jmethodID/jfieldID` are tied to class identity and become invalid after class unload; do not reuse across classloader reloads.
- **Failures:** Every failed init branch returns allocated resources, rather than hoping for unload fallback. App code must continue to be correct even when the VM does not call the hook.
- **Tests:** Unit test deterministic `close()`; keep class-loader unload tests separate and observational only, without asserting GC timing; check exported hook symbols and JNI version on the target JDK.
- **Observability:** Do not treat stdout from `JNI_OnUnload` as a required program output. GC, shutdown, and JNI unload do not share a clock.

**Final rule:** `JNI_OnUnload` is **an opportunity to clean up leftovers at a time decided by the VM**, not a safe place to create new Java work or handle the entire shutdown. Clean up resources while **the owner still exists**, so the class loader can actually disappear; afterward, the unload hook, if it occurs, should be as simple and Java-independent as possible.

### Official references

- Oracle, [JNI Invocation API — Library and Version Management](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): per-class-loader library mechanism, `JNI_OnLoad`, `JNI_OnUnload`, and unknown context warnings.
- Oracle, [JNI Functions — FindClass](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): classloader selection rules when `FindClass` runs from `JNI_OnLoad` and `JNI_OnUnload`.
- Oracle, [JNI Functions — Global and Weak References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, `NewWeakGlobalRef`, `NewLocalRef`, JNI reference ownership.
- Oracle, [Java SE 17 AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): explicit close contract and try-with-resources.
- Oracle, [Java SE 17 Cleaner](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html): fallback cleanup and non-guaranteed timing limitations.

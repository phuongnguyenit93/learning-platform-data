# Relationship Between JNI References, GC, and Class Unloading in Java

## 1. Three Related but Distinct Lifecycles

A Java program using JNI can hold Java objects on the C/C++ side, while the application may want the GC to reclaim objects and unload plugin classes to save memory or deploy a new version. To predict the consequences accurately, three lifecycles must be distinguished:

1. **Java objects (object lifetime):** The Garbage Collector (GC) determines which objects are still reachable through reference roots (GC roots), including valid JNI references. Objects that are no longer strongly held *may* be reclaimed according to GC policy.
2. **Classes and class loaders (class unloading):** A Java class is identified by *binary name + defining class loader*. According to the Java Language Specification (JLS `12.7), a class can only **possibly** be unloaded when its defining loader can be reclaimed by the GC. Even when eligible, the JVM is not required to unload the class immediately.
3. **JNI native libraries (native-library unloading):** For dynamic JNI libraries loaded via `System.loadLibrary`/`System.load`, the JVM manages the library per class loader. JNI specifies that a library may be unloaded when the loader containing it is GC'd; the `JNI_OnUnload` hook (if exported) is called during that process. This is not an "unload immediately" API that an application can invoke on demand.

The connection is that **a strong JNI reference can keep a Java object or `Class` alive → keep the associated class loader alive → make the class ineligible for unloading → indirectly delay unloading of the JNI library belonging to that loader**. Dropping Java variables or calling `System.gc()` cannot break a strong reference still held on the native side.

The key point: ***being eligible for GC/unloading* is different from *having been GC'd/unloaded***. Writing code or tests that rely on exact class-unloading timing is a false assumption about the Java/JNI contract.

## 2. Which JNI References Does the GC See?

`jobject`, `jclass`, `jstring`, and `jarray` are **JNI object references** managed by the JVM, not stable Java object addresses. The JVM uses them to track reachability, even when the GC moves objects in the heap. Never cast a reference to a C pointer and assume it is the object's heap location.

| JNI reference type | Common ways to create | Keeps object from GC? | Scope and release |
| --- | --- | --- | --- |
| **Local reference** | Native method object parameters, `FindClass`, `GetObjectClass`, `NewLocalRef` | **Yes**, while valid | Tied to native frame/thread; usually auto-released when the native method returns; can call `DeleteLocalRef` early |
| **Global reference** | `NewGlobalRef` | **Yes**, until the global ref is deleted | Usable across multiple JNI calls and across attached threads following synchronization rules; **must** call `DeleteGlobalRef` |
| **Weak global reference** | `NewWeakGlobalRef` | **No**; referent can be reclaimed by GC | Can be used to track an object without holding it strongly; requires `DeleteWeakGlobalRef` to release the handle itself |
| **`jmethodID`/`jfieldID`** | `GetMethodID`/`GetFieldID` and static variants | **Not an object reference, does not keep class from unloading** | Valid while the defining class remains loaded; invalid after the class is unloaded |

A local reference that remains until the end of a native call can still prevent an object from being reclaimed by the GC, even if the C code no longer reads that variable. Therefore, in long loops, calling `DeleteLocalRef` as soon as an object is done being processed reduces GC pressure and the number of JNI handles.

Example of objects passing through a native call:

```text
Java stack / Java heap / JNI roots
             │
             ├─ Java local / field / array element ──► Object X
             │
             ├─ JNI local ref (in native frame) ─────► Object X
             │
             ├─ JNI global ref (until Delete) ───────► Object Y
             │
             └─ JNI weak global ref - - - - - - - - -> Object Z
                                          not strongly held
```

The diagram shows reference relationships, not a physical layout that HotSpot or a specific JVM is required to use. `NULL` or a deleted reference is not a valid GC root. A standalone `malloc` native pointer does not automatically become a Java root; if C needs to hold a Java object, it must use the appropriate JNI reference type.

### 2.1. Local Reference: Holding an Object While a Native Frame Is Active

```c
/* JNI C fragment: env is valid on the current thread. */
jclass cls = (*env)->GetObjectClass(env, obj);
if (cls == NULL) {
    return; /* There may be a pending Java exception. */
}

/* ... use cls ... */

(*env)->DeleteLocalRef(env, cls);
```

`cls` is a local `jclass` to a Java `Class` object. While the local ref is valid, it is a strong reference. Deleting the ref **does not mean the `Class` object is unloaded immediately**: the object/class may still have many other strong reachability paths.

Do not cache `cls` in a static C variable to use after the method finishes: once the local ref expires, that value is no longer a valid JNI reference. For attached native threads, local refs must be managed within the attach/local frame scope; `PushLocalFrame`/`PopLocalFrame` also help define lifetimes clearly.

### 2.2. Global Reference: A Long-Lived Retention Source

```c
/* C fragment: obj is a valid, non-NULL local/global ref. */
jobject kept = (*env)->NewGlobalRef(env, obj);
if (kept == NULL) {
    return; /* If out of memory, an OOME may be pending. */
}

/* kept continues to keep the Java object reachable. */

/* When the object no longer needs to be held: */
(*env)->DeleteGlobalRef(env, kept);
kept = NULL;
```

A global reference is a strong root **even when no Java-side variable points to the object anymore**. `DeleteGlobalRef` only releases one reference; if other strong references remain, the object stays alive. Once all strong refs are gone, the object becomes a candidate for GC, not necessarily reclaimed immediately.

**Management rule:** every global ref creation must have an owner, a release point, and a policy to prevent double-delete or use-after-delete. You cannot call `free(kept)` to delete a JNI reference.

### 2.3. Weak Global Reference: Does Not Keep an Object Alive

```c
/* Fragment: obj is a valid JNI object reference. */
jweak weak = (*env)->NewWeakGlobalRef(env, obj);
if (weak == NULL) {
    return; /* NULL due to null input or allocation failure. */
}

/* weak does not itself prevent GC from reclaiming the referent. */

/* Clean up the handle, even if the referent has been reclaimed by GC: */
(*env)->DeleteWeakGlobalRef(env, weak);
```

Once the referent has been reclaimed by GC, the weak global reference becomes effectively equivalent to `NULL`. `IsSameObject(env, weak, NULL)` can check the state at a point in time, but GC can run immediately after the check. If you need to **use the object** afterward, first promote it to a strong local reference:

```c
/* Safe fragment for continuing to use the referent of a valid
   jweak. */
jobject strong = (*env)->NewLocalRef(env, weak);
if (strong != NULL) {
    /* The object is strongly held while strong ref is valid. */
    /* ... use strong ... */
    (*env)->DeleteLocalRef(env, strong);
} else {
    /* Referent may have been reclaimed; also check for a
       pending exception if allocation failed. */
}
```

**Do not use `jweak` as a way to "remember an object forever without costing memory."** Once the referent is gone, dereferencing through the weak ref is no longer safe; when the weak handle is no longer needed, it must also be deleted.

## 3. From JNI References to Class Unloading Conditions

A Java class is not just source code on disk. The JVM creates metadata for the class, associates the class with its defining loader, and has a `java.lang.Class` object representing that class. The class loader plays a role in identifying the class type in the JVM; for example, two different loaders can produce two classes both named `plugin.Widget` that are **not the same type**.

Consider a plugin system:

```text
GC root: JNI global reference
          │
          ▼
java.lang.Class object: plugin.Widget
          │
          ▼
Class metadata / defining loader relationship
          │
          ▼
PluginClassLoader (L)
          │
          ▼
Other classes defined by L
```

If native code creates a global ref to `Class<?>` of `plugin.Widget`, that class still needs to remain alive; the loader that defined that class cannot be considered a loader eligible to be reclaimed for class unloading. The same effect can occur when native code holds a global ref to **an instance** of a plugin class, because a live instance requires its class to exist.

In addition, the reachability chain can take another path:

```text
GC root: thread / static registry / JNI global reference
                   │
                   ▼
        plugin instance / callback
                   │
                   ▼
      plugin class and defining loader
```

Therefore, when a server application "closes a plugin" yet memory usage keeps growing after multiple deployments, the cause is not necessarily a GC bug. The plugin loader may **still be reachable** via a global JNI ref, a thread context class loader, a thread running plugin code, a listener, a Java cache, or an unregistered callback.

### 3.1. A Necessary Condition, Not an Automatic Promise

JLS `12.7 states that a class/interface **may be unloaded if and only if its defining class loader may be reclaimed by the GC**. Classes of the bootstrap loader are not unloaded under that rule. Unloading is a transparent optimization; an application must not assume the JVM will unload on time, or even choose to unload within a predictable timeframe.

For a custom loader like `URLClassLoader` to have a chance to be reclaimed, in practice it is necessary to break the reachability paths keeping the class, instances, metadata, and associated loader alive; these paths may go indirectly through **JNI strong references**.

Distinguish the operations:

| Operation | What does it actually mean? | Guarantees immediate class unloading? |
| --- | --- | --- |
| `DeleteLocalRef` | Removes a local JNI reference in a native frame | No |
| `DeleteGlobalRef` | Removes a strong global JNI reference | No |
| `DeleteWeakGlobalRef` | Removes a weak JNI handle, does not necessarily affect the referent | No |
| `URLClassLoader.close()` | Closes file/JAR resources for loading new classes per the loader contract | No |
| Dropping Java variables pointing to the loader | Removes one strong reference path; other paths may still exist | No |
| `System.gc()` | Suggests that the JVM perform GC; the JVM has the right not to comply as desired | No |
| JVM GC actually determines the loader is reclaimable | May free the loader and unload classes per VM policy | **No guaranteed schedule for the application** |

**An internal reference cycle does not by itself keep objects alive forever.** For example, a static field of a plugin class points to a plugin singleton, and the singleton points back to the loader: if the entire group has no remaining path from GC roots, the GC can still reclaim that group. What needs investigation are **paths from external roots** such as long-lived JVM threads, application registries, or JNI global refs.

### 3.2. `jmethodID` and `jfieldID` Are Not Global References

Native code often caches the results of `GetMethodID` and `GetFieldID`:

```c
/* Fragment: clazz is a valid jclass. */
jmethodID mid =
        (*env)->GetMethodID(env, clazz, "execute", "()V");
```

A `jmethodID` is not a `jobject`, **cannot be passed to `NewGlobalRef` to turn it into a strong reference**, and **does not itself prevent the JVM from unloading the class**. After the class is unloaded, the previous ID is no longer valid. If an ID needs to be used across multiple lifecycles, you must keep a live reference to the underlying class for the proper scope, or look up the ID again for the new class after reload.

Holding a global `jclass` to guarantee the ID stays alive trades off by **blocking class unloading**. Cache design must make a deliberate choice: a fixed process-wide cache (accepting that the loader stays alive), or a plugin-lifecycle cache with an explicit teardown command.

## 4. Java 17+ and JNI C Example: Global `jclass` Holding a Class Loader

This example clarifies the reachability relationship without relying on whether `System.gc()` runs. A class `host.NativeRoots` defined by the application loader loads the JNI library **once**; the class `plugin.Widget` is defined by a temporary loader. Native code creates a **global `jclass`** pointing to `plugin.Widget` and stores it in a static C variable.

Crucially, **the JNI library belongs to the host's loader**, while the plugin class belongs to a different loader. That way, the example focuses on the retention path caused by the global reference, without confusing it with native library lifecycles tied to the plugin's loader.

File structure:

```text
project/
├── src/
│   ├── host/
│   │   ├── NativeRoots.java
│   │   └── Demo.java
│   └── plugin/
│       └── Widget.java
├── native/
│   └── native_roots.c
└── build/               # created by compile commands
```

### 4.1. Class Declaring JNI in the Host

**File `src/host/NativeRoots.java`:**

```java
package host;

public final class NativeRoots {
    static {
        System.loadLibrary("native_roots");
    }

    private NativeRoots() {
    }

    public static native void hold(Class<?> type);

    public static native boolean holds(Class<?> type);

    public static native boolean hasRoot();

    public static native void release();
}
```

`Class<?>` is passed down to JNI as `jclass`. In this example, `hold` is only called with a non-null class. To keep the code easy to verify, the example runs on a single thread; real applications must synchronize reference replacement/deletion operations if multiple threads access the native cache concurrently.

### 4.2. Plugin Loaded by a Separate Loader

**File `src/plugin/Widget.java`:**

```java
package plugin;

public final class Widget {
    public String message() {
        return "Hello from plugin";
    }
}
```

Do not put `build/plugin` on the application classpath when running the driver: that directory is only given to the plugin's `URLClassLoader`.

### 4.3. Driver Creates the Plugin Loader, Then Holds Only a Weak Reference to the Loader in Java

**File `src/host/Demo.java`:**

```java
package host;

import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Demo {
    private static WeakReference<ClassLoader> install(Path pluginDir)
            throws Exception {

        URL[] urls = {pluginDir.toUri().toURL()};

        try (URLClassLoader loader = new URLClassLoader(
                urls, ClassLoader.getPlatformClassLoader())) {

            Class<?> type = Class.forName(
                    "plugin.Widget", true, loader);

            NativeRoots.hold(type);
            System.out.println(
                    "JNI holds plugin class: " + NativeRoots.holds(type));

            return new WeakReference<>(loader);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: host.Demo <plugin-class-directory>");
        }

        WeakReference<ClassLoader> loaderRef =
                install(Path.of(args[0]).toAbsolutePath());

        try {
            System.out.println(
                    "JNI global root exists: " + NativeRoots.hasRoot());
            System.out.println(
                    "Plugin loader reachable: " +
                    (loaderRef.get() != null));
        } finally {
            NativeRoots.release();
        }

        System.out.println(
                "JNI global root after release: " + NativeRoots.hasRoot());
    }
}
```

`Class.forName(..., true, loader)` forces the class to be defined by the plugin loader (because `build/plugin` is not on the application classpath and is not contained in the platform loader). The `install` method finishes, so its local Java variables are no longer in use; the driver keeps only a `WeakReference` to the loader.

After `NativeRoots.hold(type)` succeeds, the global JNI reference to `plugin.Widget.class` keeps the class and its defining loader alive. `URLClassLoader.close()` in `try-with-resources` closed the loader's lookup resources, but **did not delete the global JNI ref**.

### 4.4. Native Implementation with Global Reference and Cleanup

**File `native/native_roots.c`:**

```c
#include "host_NativeRoots.h"

/* Example is called from one thread only; production requires synchronization. */
static jclass held_class = NULL;

JNIEXPORT void JNICALL Java_host_NativeRoots_hold(
        JNIEnv *env, jclass ignored, jclass type) {
    (void)ignored;

    /* type must be valid non-null per the example's contract. */
    jclass replacement =
            (jclass)(*env)->NewGlobalRef(env, type);

    if (replacement == NULL) {
        /* If allocation fails, return with a pending exception. */
        return;
    }

    if (held_class != NULL) {
        (*env)->DeleteGlobalRef(env, held_class);
    }
    held_class = replacement;
}

JNIEXPORT jboolean JNICALL Java_host_NativeRoots_holds(
        JNIEnv *env, jclass ignored, jclass type) {
    (void)ignored;

    if (held_class == NULL) {
        return JNI_FALSE;
    }
    return (*env)->IsSameObject(env, held_class, type);
}

JNIEXPORT jboolean JNICALL Java_host_NativeRoots_hasRoot(
        JNIEnv *env, jclass ignored) {
    (void)env;
    (void)ignored;
    return held_class != NULL ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL Java_host_NativeRoots_release(
        JNIEnv *env, jclass ignored) {
    (void)ignored;

    if (held_class != NULL) {
        (*env)->DeleteGlobalRef(env, held_class);
        held_class = NULL;
    }
}
```

**Explanation:** `NewGlobalRef` creates a new strong JNI reference. `IsSameObject` checks the actual identity of the `Class` object rather than comparing two `jclass` handle values. `DeleteGlobalRef` ends the native cache's retention of the object and sets the C pointer back to `NULL` to avoid reusing a deleted reference.

Note on errors: if `NewGlobalRef` fails due to out-of-memory, it may return `NULL` with a pending `OutOfMemoryError`; in that case the Java driver receives the exception and does not produce the successful stdout shown below. The illustrative code does not implement `hold(null)` handling or concurrent access; in production, validate inputs and manage mutex/ownership.

### 4.5. Compiling and Running on Linux

From the `project` directory, use JDK 17 or later and GCC/Clang. `JAVA_HOME` must point to a JDK directory containing `include/jni.h`.

```bash
mkdir -p build/host build/plugin build/headers

javac -h build/headers -d build/host \
  src/host/NativeRoots.java \
  src/host/Demo.java

javac -d build/plugin src/plugin/Widget.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_roots.c -o libnative_roots.so

java -Djava.library.path=. -cp build/host \
  host.Demo build/plugin
```

**Expected stdout** (without forcing GC; Java/JNI code completes normally):

```text
JNI holds plugin class: true
JNI global root exists: true
Plugin loader reachable: true
JNI global root after release: false
```

The last line only confirms that **the example's global reference has been deleted**; it does not confirm that the class or loader has been unloaded. Other strong references may still remain, or the JVM may not have performed class unloading yet. To actively observe GC, you can add a separate test after `release` using `System.gc()` and reading `loaderRef.get()`; the result **is not stable across runs and should not be written as a fixed expected stdout**.

On JDKs enforcing newer native-access policies, depending on packaging and JDK version, `--enable-native-access=ALL-UNNAMED` may be needed for code on the classpath. This option **does not change GC rooting or class unloading**. On Windows/macOS, the native library must be rebuilt with the platform-appropriate file extension and JNI includes.

## 5. Why Deleting a Global Ref Is Still Not Enough to Guarantee Unloading

A global reference is **one** edge in the reachability graph. Deleting it does not guarantee that other edges are also removed. For example:

```text
Host static Map<String, Object> registry
                 │
                 ▼
       plugin callback object
                 │
                 ▼
          plugin class
                 │
                 ▼
        PluginClassLoader
```

Even if native code has called `DeleteGlobalRef`, the host registry still holds the callback, so the plugin loader remains alive. Similarly, a thread still running inside plugin code or `Thread.contextClassLoader` still referencing the old loader can keep it alive.

Retention paths to examine include:

- **JNI:** unreleased global `jobject`/`jclass`; local refs of a long-running native call; callbacks from C holding Java objects; attached native threads still creating/holding references via JNI.
- **Java application:** caches/static registries defined by classes in a long-lived loader, listeners, scheduled tasks, executors, MBeans, logging registries, reflection `Class<?>`/`Method`/`MethodHandle`; plugin objects still being held.
- **Threads:** unfinished tasks, threads running plugin code, thread context class loaders, `ThreadLocal`/inheritable values still containing plugin objects.
- **Native resources:** native heap allocations, file descriptors, callbacks, and C-side threads need cleanup, even though they are not automatically Java GC roots if no JNI reference or Java object holds them.

One notable point: **merely having a C-side `malloc` buffer does not prevent a Java object from being GC'd**. A raw native pointer is not treated as a Java reference. Conversely, if a buffer stores a number cast from a `jobject` and uses it as a reference later, that is a JNI bug, not a valid object-retention technique.

### 5.1. Regarding ID Caches and Class Loaders

`jmethodID` and `jfieldID` are method/field identifier tokens returned by JNI; **by themselves they do not prevent class unloading**. If you store them longer than the class's lifetime without holding a strong class reference, after the class is unloaded the IDs become invalid. If you hold a strong global `jclass` for the cache, you keep the class/loader alive until cleanup. The cache lifetime must be defined to match the plugin lifecycle.

In particular, avoid a **JVM-wide** native cache keyed only by class name. Two classes with the same name in two different loaders are still two different types. Any cache of `jclass`, IDs, or callbacks must distinguish the defining loader and have a teardown step when the plugin leaves the system.

## 6. Class Unloading and Native-Library Unloading Are Two Different Events

**Class unloading** is the JVM releasing the runtime representation of a class when the JVM allows it and GC conditions are met. **Native library unloading** is the process where the JVM manages a JNI module owned by a loader and releases that module when the loader's lifecycle permits. They are related via the loader, but they are not the same operation.

JNI specifies that **each class loader manages its own JNI libraries and the same JNI native library cannot be loaded into multiple loaders simultaneously**; reloading from another loader while the library still belongs to a previous loader can cause `UnsatisfiedLinkError`. If the old loader is reclaimed by the GC, that loader's library *may* be unloaded by the JVM mechanism, but there is no public `System.unloadLibrary()` call to force the event immediately.

### 6.1. `JNI_OnLoad` and `JNI_OnUnload`

For dynamic libraries, JNI supports two optional hooks:

```c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Simple native cleanup in an unspecified context. */
}
```

This is a **standalone fragment illustrating the two hooks**, not the full implementation of `native_roots.c` in Section 4. `JNI_OnLoad` is called when the VM loads the JNI library. `JNI_OnUnload` is called when the loader containing the native library is GC'd, if the library provides the hook. The JNI specification warns that the unload callback may run in an unspecified context; you should limit use of JVM services and avoid arbitrarily calling back into Java.

**Do not use `JNI_OnUnload` as the sole business cleanup step.** If a global reference or application thread keeps the loader alive indefinitely, the unload hook may never occur within the observed lifetime of the process. If native data needs to be released when a plugin is disabled, provide an explicit `close()/dispose()/release()` API and perform cleanup before dropping the loader.

In the Section 4 example, the `native_roots` library belongs to the **application loader**, so even if the plugin loader is later GC'd, **do not infer that `libnative_roots.so` will unload**. This is an important distinction between a reference holding a class and library ownership.

### 6.2. Common False Assumptions

- **"Closing `URLClassLoader` unloads all classes."** `close()` only closes the data sources and resources that the loader manages; already-loaded classes can continue to be used.
- **"Deleting `jclass` with `DeleteGlobalRef` destroys the class."** It only removes one reference. The class may still be used from Java, a native frame, or another root.
- **"`System.gc()` guarantees freeing Metaspace."** It is a GC suggestion; class unloading depends on the JVM/GC, reachability, and runtime options.
- **"There are no Java instances left, so the class will definitely unload."** A `Class<?>` global ref, reflection cache, method handle, class loader reference, or another class using it can still keep the loader alive.
- **"`jmethodID` cache keeps the class alive by itself."** An ID is not a strong Java object reference; if the class unloads, the ID becomes invalid.
- **"Seeing native memory grow means a class loader leak."** It could be a global JNI ref leak, growing JNI local tables, unfreed `malloc` buffers, direct buffers, JIT/code cache, OS library mappings, or other causes. You must measure the right type of memory.

## 7. Designing Teardown So Plugins Have a Chance to Unload

For applications that can load/unload plugins multiple times, a consistent lifecycle design matters more than a "force GC" call:

1. **Stop activity:** reject new requests, complete or cancel running tasks; prevent new native callbacks from accessing the plugin.
2. **Unregister from the host:** remove listeners, event handlers, schedulers, registries, caches, MBeans, and thread-local data held by the host.
3. **Stop native work:** stop native worker threads, wait for in-flight callbacks to finish; for native threads attached to the JVM, detach at the right time. Do not let one thread's `JNIEnv *` be used on another thread.
4. **Release references:** `DeleteGlobalRef` for strong global roots, `DeleteWeakGlobalRef` for weak handles; clear `jclass`/method ID caches according to the plugin lifecycle.
5. **Release native resources:** close files/sockets, free `malloc` buffers, release JNI array elements/critical regions with the proper APIs; do not mix `free` with JNI reference deletion.
6. **Close the loader and drop strong references:** `URLClassLoader.close()` when appropriate, then drop object/class/loader references still held on the host.
7. **Observe GC/class unloading:** use diagnostic tools to find remaining live roots; do not treat a single GC that did not unload as proof of a program bug.

The ordering must respect concurrency: **do not delete a global ref while another thread is still using it without an ownership/synchronization mechanism**. A "stop → drain callbacks → release handles → release loader" protocol is required, especially when JNI callbacks call back into Java asynchronously.

If operational requirements demand **unloading a C/C++ library at an exact point in time**, isolating the native worker into a separate process and restarting that process usually provides a clearer lifecycle boundary. Class unloading in the JVM is not designed as a hot-swap mechanism for native code with hard deadlines.

## 8. How to Verify in Practice

### 8.1. Tracking a Class Loader Without Strongly Holding It

A Java-side `WeakReference<ClassLoader>` can be used to observe whether the loader is still strongly reachable or has been reclaimed by the GC. However, do not hold `Class<?>` variables or plugin instances in the measurement tool itself for too long; those variables can inadvertently prevent unloading.

```java
import java.lang.ref.WeakReference;

// Fragment: loader is an existing custom ClassLoader.
WeakReference<ClassLoader> watch = new WeakReference<>(loader);

// After cleaning up all strong references, at a point in time:
boolean alreadyCollected = watch.get() == null;
```

The snippet above **is not a standalone program** and does not require the JVM to have run GC. If `watch.get() != null`, the loader may still have a root or simply may not have been reclaimed by GC yet. If `watch.get() == null`, the loader object had been reclaimed at that observation point, but do not infer when the OS-level library was unmapped.

### 8.2. Checking via JVM Tools

On supported HotSpot/JDK versions, you can:

```bash
# Observe class unloading events (when the JVM actually performs them).
java -Xlog:class+unload=info -cp build/host \
  -Djava.library.path=. host.Demo build/plugin

# On a running JVM process (substitute the actual PID):
jcmd <PID> VM.classloader_stats
```

`<PID>` is a **command-line placeholder**; do not type the angle brackets into the shell. The `-Xlog`/`jcmd` options and output format are HotSpot/JDK details, not an API guaranteed to be identical across all JVMs.

The demo finishes quickly and does not actively trigger GC, so seeing no class-unload log is normal. When diagnosing a real plugin leak, run a load test with multiple plugin lifecycles, observe loader/class counts over time, and combine heap dump/GC roots analysis; do not rely solely on a single Metaspace number.

You can also use `-Xcheck:jni` (where supported by the JVM) to detect many JNI reference usage errors; JNI checking helps find bugs, but cannot replace strong reachability path analysis.

### 8.3. Locating Bugs from Symptoms

| Symptom | Priority checks |
| --- | --- |
| Many old `PluginClassLoader` instances remain alive after redeploy | Host registries, listeners, class caches, thread context loaders, undeleted JNI `NewGlobalRef`s |
| JVM reports an error when loading the same JNI library from a new loader | Library still belongs to the old loader; distinguish classloader leak from JNI loading policy |
| Java heap grows even while the plugin is idle | Global refs to plugin objects, native threads holding local refs long-term, host caches |
| Metaspace grows when reloading a plugin multiple times | Loader/class is ineligible for unloading or JVM has not performed class unloading yet |
| Native memory grows while Java heap is stable | `malloc`, JNI resources, direct buffers, C/C++ libraries, and other types of native allocations |
| `JNI_OnUnload` does not appear | The loader owning the library may still be alive or not yet GC'd; hook is missing or not in the right library |

**You cannot diagnose with certainty from a single symptom alone.** What matters is identifying the actual root holding an object/loader alive; for native references, inspect with tools that support JNI handles/heap roots and verify ownership in code.

## 9. Self-Check Questions

**Question 1.** Java has dropped all variables pointing to a `plugin.Widget` object, but JNI still has `jobject cached = NewGlobalRef(env, widget)`. Is the object eligible for GC yet?  
**Answer:** Not yet, because the global JNI reference still strongly holds the object. That reference can also indirectly keep the plugin's defining class loader alive.

**Question 2.** Does converting a global ref into a weak global ref automatically guarantee class unloading?  
**Answer:** No. A weak ref does not strongly hold its referent, but the class/loader may still have other strong roots, and the JVM is not required to unload immediately once eligible.

**Question 3.** Once `DeleteGlobalRef` has been called, is `JNI_OnUnload` guaranteed to run before the function returns?  
**Answer:** No. Deleting a reference is not an unload request. `JNI_OnUnload` is tied to when the VM GCs the class loader **that owns the native library**, and the library must define that hook.

**Question 4.** A C static cache stores only `jmethodID`, not `jclass`. Does this keep the class from unloading?  
**Answer:** No. `jmethodID` is not a root. Once the class unloads, the ID becomes invalid and must not be reused for the new class after reload.

**Question 5.** Why is `URLClassLoader.close()` not enough to release a plugin?  
**Answer:** It only closes the resources managed by the loader. Existing classes, instances, callbacks, and global JNI refs can still be reachable and keep the loader alive.

**Question 6.** To use an object stored only via `jweak` inside a native callback, what should you do?  
**Answer:** Create a strong local reference with `NewLocalRef`, check for null/exception, operate through the strong ref, and then call `DeleteLocalRef`. Merely checking `IsSameObject(weak, NULL)` beforehand does not protect the object from a GC race.

**Question 7.** If a native library is loaded from the application loader but holds a global `jclass` from a plugin loader, does unloading the plugin loader imply that the native library unloads?  
**Answer:** No. Cleaning up the global `jclass` only removes one reason keeping the plugin loader alive. A library belonging to the application loader has its own lifecycle, typically lasting until the JVM terminates.

## 10. Key Takeaways

- JNI local/global references can act as **strong GC roots**; weak global refs do not keep objects alive.
- A **global `jclass` or `jobject` of a plugin** can keep the defining class loader alive, preventing class unloading.
- `jmethodID`/`jfieldID` are IDs, **not object roots**; IDs become invalid after class unloading.
- **Dropping a reference ≠ reclaiming an object ≠ unloading a class ≠ unloading a native library**. These are distinct lifecycle milestones.
- Class unloading can only occur when the defining loader can be reclaimed by GC, and the JVM retains the decision of when to unload.
- Plugin teardown design must simultaneously clean up Java callbacks, threads, JNI strong/weak refs, native handles, and caches. Do not force GC as a resource-management mechanism.
- `JNI_OnUnload` occurs according to the lifecycle of the loader owning the dynamic JNI library; perform active cleanup as soon as the plugin stops, rather than waiting for this hook.

### Official Documentation

- [Oracle JNI Design Overview — Referencing Java Objects, Local/Global References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): how JNI references retain objects and the validity of method/field IDs.
- [Oracle JNI Functions — Local, Global, Weak Global References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, `NewLocalRef`, `NewWeakGlobalRef`, `DeleteWeakGlobalRef`.
- [Oracle JNI Invocation API — Library Lifecycle and JNI_OnUnload](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): native library association with loaders and native library lifecycle upon loader GC.
- [Java Language Specification — `12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): necessary conditions for class unloading to occur.
- [Java SE 17 API — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()): limits of loader closing behavior.

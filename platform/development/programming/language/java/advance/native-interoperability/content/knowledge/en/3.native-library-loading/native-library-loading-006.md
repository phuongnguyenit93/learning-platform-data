# Native Libraries Bound to Class Loaders and Reloading Limitations in Java

## 1. Why is a native library not like a Java class?

A Java application can create multiple `ClassLoader` instances to load different class versions, for example when running plugins, application servers, or a hot deployment system. However, **JNI native libraries** (`.so`, `.dll`, `.dylib`) cannot be loaded and replaced flexibly in the same simple way as Java bytecode.

According to the Java Native Interface (JNI) contract, **each class loader manages its own set of native libraries; the same JNI library cannot be loaded simultaneously by two different class loaders**. When a second loader attempts to load the same library that already belongs to the first loader, the JVM throws `UnsatisfiedLinkError`. This rule protects Java type separation across class loaders: two classes with the same name but defined by two different loaders are two different types, while native code may store `jclass`, `jmethodID`, or references that are only meaningful within the context that created them.

Practical consequence: **replacing a plugin's JAR or creating a new class loader does not automatically replace the running native library**. The ability to unload a native library depends on the lifecycle of the class loader that owns the library and any live references; there is no public `System.unloadLibrary()` call for an application to request unloading a JNI library immediately.

This article focuses on the **JNI native library loading mechanism within a single JVM**. The loading mechanism using the Foreign Function & Memory API (FFM) has its own API and lifecycle, and must not be mechanically inferred from the JNI ownership rules below.

## 2. Class loaders determine the JNI namespace

### 2.1. A class has an identity consisting of its name and defining loader

Suppose there are two class loaders `L1` and `L2` that both define a class named `plugin.NativeProbe`. Then:

- `plugin.NativeProbe` defined by `L1` and `plugin.NativeProbe` defined by `L2` **are not the same Java class**; their `Class<?>`, object types, static fields, and type cast checks are also separate.
- A JNI library may use symbol names such as `Java_plugin_NativeProbe_doubleValue` or `RegisterNatives` to bind methods to their implementations. If the library were shared across classes from different loaders, native caches and JNI references could bind to the wrong object/type.
- Therefore, the JVM tracks native libraries per loader and blocks re-registering the same JNI library for another loader.

This remains true even when both loaders read from **the same JAR file or the same directory containing `.class` files**. Having the same bytecode file location does not give two classes the same identity when their defining loaders differ.

### 2.2. Common mechanisms when loading a library

```java
// Load by logical name; the JVM maps the name according to the operating system.
System.loadLibrary("native_probe");

// Load by absolute path to a specific library file.
System.load("/opt/app/native/libnative_probe.so");
```

- `System.loadLibrary("native_probe")` takes a **logical library name**, without adding a path or file extension. With common naming conventions, Linux uses `libnative_probe.so`, and Windows uses `native_probe.dll`. The JVM searches for the library according to the loader/JVM/platform native search mechanism; a custom `ClassLoader.findLibrary` can return an absolute path chosen by the loader itself.
- `System.load("/.../libnative_probe.so")` takes an **absolute path** to the native file. It helps specify the exact file requested, but **does not bypass the constraint that each JNI library belongs to only one loader at a time**.
- Which Java class **actually calls** `System.load`/`System.loadLibrary` is very important: in the normal case, the JNI library is bound to the class loader that defines the class making the call. Do not confuse this with the **thread context class loader**: changing `Thread.currentThread().setContextClassLoader(...)` does not automatically transfer ownership of the JNI library.
- Reloading the same library within **the same loader that already owns it** is usually treated by the JVM as already loaded and does not create a new active instance. A second call does not replace the machine code with a different version just written to disk.

`System.mapLibraryName("native_probe")` helps determine the corresponding native file name on the current platform, but does not by itself guarantee that the file exists, has the right ABI, or can be loaded.

### 2.3. Ownership model

```text
JVM process
│
├── ClassLoader L1
│   ├── plugin.NativeProbe (class defined by L1)
│   └── JNI library: /path/libnative_probe.so   ← loaded by L1
│
└── ClassLoader L2
    └── plugin.NativeProbe (different class, defined by L2)
        └── System.load(same library) → UnsatisfiedLinkError
```

This is a **JVM JNI linking rule**, not merely a “file not found” error from the operating system's library loader. Changing `java.library.path`, retrying in another class loader, or changing the Java class name usually does not fix the root cause.

## 3. Reloading scenarios: what actually happens?

| Scenario | Result / what to understand |
| --- | --- |
| `L1` calls `System.load` for the library for the first time | The JVM checks and loads the JNI library if the path, architecture, dependencies, permissions, and entry point are valid |
| `L1` continues to call load for the same library | Usually treated as already loaded; does not automatically initialize a new code instance or hot swap |
| `L2` (different from `L1`) tries to load **that same library** while `L1` still owns it | `UnsatisfiedLinkError`, usually accompanied by information that it is already loaded in another class loader |
| Closing `URLClassLoader` with `close()` | Closes class/JAR lookup resources per the `URLClassLoader` contract; **already-loaded classes can still be used**, with no guarantee of immediate native unloading |
| Dropping all references to `L1` and related classes/instances | `L1` *may* become eligible for GC; this does not yet prove the library has been unloaded |
| GC actually reclaims the loader owning the library | JNI specifies that the library **may be unloaded** along with the loader's lifecycle, with `JNI_OnUnload` if provided by the library; the exact timing of GC/unloading is not precisely controlled by the application |
| Overwriting the `.so`/`.dll` file on disk after it has been loaded | Already-loaded code does not automatically switch to the new version; the operation may fail or be dangerous depending on the OS/filesystem |
| Renaming or copying to another native file | May change how the JVM/OS identifies the library, but **does not guarantee isolation of symbols, C global state, dependencies, or ABI**; not a reliable hot-reload strategy |

Key takeaway: **being theoretically unloadable does not mean you can command an unload at a specific point in time**. Readiness for replacing a native version must be designed in, not implicitly inferred from creating a new loader.

## 4. Runnable example: two class loaders loading the same JNI library

The example uses **JDK 17 or later, Linux, GCC/Clang, and a JDK with JNI headers**. A Java class in a plugin loads `libnative_probe.so`, and then the program creates two different `URLClassLoader` instances pointing to the same bytecode directory. Using `parent = null` ensures each loader defines `plugin.NativeProbe` itself, rather than accidentally delegating to the application class loader to load a shared class.

Create the file tree:

```text
project/
├── src/
│   ├── LoaderCollisionDemo.java
│   └── plugin/
│       └── NativeProbe.java
├── native/
│   └── native_probe.c
└── build/                    # generated by the build command
```

### 4.1. Java class directly calling `System.load`

**File `src/plugin/NativeProbe.java`:**

```java
package plugin;

public final class NativeProbe {
    static {
        String path = System.getProperty("demo.native.path");
        if (path == null || path.isBlank()) {
            throw new IllegalStateException(
                    "Set -Ddemo.native.path to an absolute native library path");
        }
        System.load(path);
    }

    private NativeProbe() {
    }

    public static native int doubleValue(int number);
}
```

When `NativeProbe` is **initialized for the first time**, the static initializer runs `System.load`. Because each loader defines `NativeProbe` independently, they trigger two independent class initializations. Using the same native path intentionally creates a collision on the second attempt.

### 4.2. Java driver creating two genuinely different class loaders

**File `src/LoaderCollisionDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderCollisionDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderCollisionDemo <classes-directory>");
        }

        URL classesUrl = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader first =
                     new URLClassLoader(new URL[]{classesUrl}, null);
             URLClassLoader second =
                     new URLClassLoader(new URL[]{classesUrl}, null)) {

            Class<?> inFirst =
                    Class.forName("plugin.NativeProbe", true, first);
            Object result = inFirst
                    .getMethod("doubleValue", int.class)
                    .invoke(null, 21);
            System.out.println("L1 -> " + result);

            try {
                Class.forName("plugin.NativeProbe", true, second);
                System.out.println("L2 -> unexpectedly loaded");
            } catch (UnsatisfiedLinkError expected) {
                System.out.println("L2 -> UnsatisfiedLinkError");
            }
        }
    }
}
```

`Class.forName(name, true, loader)` both loads and requests to **initialize** the class, so the `System.load` static initializer is guaranteed to execute in the example. Calling `getMethod(...).invoke(null, 21)` verifies that the JNI method in the first loader actually works, not just that the file was loaded successfully.

`try-with-resources` closes both `URLClassLoader` instances when exiting the scope; as seen later, this operation **does not confirm that the native library has unloaded**. Catching `UnsatisfiedLinkError` in the second loader is intended to demonstrate the expected error in a valid build environment; if the first loader fails, check for file/ABI errors rather than interpreting it as a class loader collision.

### 4.3. Native implementation

**File `native/native_probe.c`:**

```c
#include "plugin_NativeProbe.h"

JNIEXPORT jint JNICALL Java_plugin_NativeProbe_doubleValue(
        JNIEnv *env, jclass clazz, jint number) {
    (void)env;
    (void)clazz;
    return number * 2;
}
```

The C function uses the prototype from the header generated by `javac -h`. `JNIEXPORT` and `JNICALL` preserve the JNI export/calling convention; because the method is `static`, the second hidden parameter is `jclass`. With an input of 21, the result 42 is within the `jint` range, so the multiplication does not overflow.

### 4.4. Compiling and running on Linux

In the `project` directory, assuming the `JAVA_HOME` environment variable points to the JDK in use:

```bash
mkdir -p build/classes build/headers

javac -h build/headers -d build/classes \
  src/plugin/NativeProbe.java \
  src/LoaderCollisionDemo.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_probe.c -o build/libnative_probe.so

java -Ddemo.native.path="$(pwd)/build/libnative_probe.so" \
  -cp build/classes LoaderCollisionDemo build/classes
```

**Expected stdout output when running on JDK 17 with a proper JNI environment:**

```text
L1 -> 42
L2 -> UnsatisfiedLinkError
```

To see the original message when troubleshooting, you can add `System.err.println(expected.getMessage());` in `catch`; the message text may vary by JDK and operating system, so the example only fixes the error type name on stdout.

**JDK 24 and later:** loading/linking JNI falls under controlled native access operations; a warning may appear on stderr if permission has not been granted. For classes on the **classpath** in the example, add the `--enable-native-access=ALL-UNNAMED` option before the main class name:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Ddemo.native.path="$(pwd)/build/libnative_probe.so" \
  -cp build/classes LoaderCollisionDemo build/classes
```

The native access option only handles the policy allowing native operations; **it does not eliminate the error of a single JNI library belonging to two loaders**. For named modules, restrict permission using `--enable-native-access=<module-name>` according to the JDK version in use.

On macOS or Windows, you must rebuild the native library for that system's ABI, replacing the file name and compile/link commands accordingly; **do not directly use** the Linux `.so` build for a JVM on another platform.

### 4.5. Why can't the example be “fixed” with `System.gc()`?

When the second loader is initialized, `first` and `inFirst` still have strong references in the program. The first loader's native library still belongs to that loader. Even after exiting `try`, closing the loader does not automatically turn all classes/objects into unreferenced ones; GC/reclamation is the JVM's decision. Calling `System.gc()` is only a **suggestion to collect**, and does not provide synchronous “library unloading completed” behavior. There is no reliable upgrade mechanism based on a `System.gc()` loop followed by reloading the same library.

## 5. JNI library lifecycle and management hooks

For **dynamically linked** JNI libraries, the following hooks are optional:

```c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Initialize resources needed for this JNI load. */
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Only perform simple native cleanup, safe in an indeterminate context. */
}
```

- `JNI_OnLoad` is called by the JVM when loading a JNI library that provides this hook; it returns the JNI version required by the library. When using `RegisterNatives`, registering methods with the right class/loader is usually organized during loading.
- `JNI_OnUnload` is called by the JVM when the loader containing the library is garbage-collected according to the JNI lifecycle. The hook may run in an indeterminate context; the JNI specification requires caution when using JVM services, **avoiding arbitrary callbacks into Java**.
- Do not rely for application functional correctness on `JNI_OnUnload` occurring immediately after an event such as “plugin disabled”. Important cleanup needs an **explicit close/dispose** API, called when the application still knows who owns the resources.
- A library loaded by a loader that lives for the entire process (for example, the application's shared loader) usually continues to exist until the JVM terminates; expecting an in-process native hot reload is an unsafe assumption.

**Note:** `JNI_OnLoad_L`/`JNI_OnUnload_L` are used for **JNI libraries statically linked with the VM** per the JNI specification; do not confuse them with `JNI_OnLoad`/`JNI_OnUnload` for dynamic libraries in the example.

### 5.1. What keeps a class loader alive

A loader may fail to be reclaimed due to seemingly minor references:

- Plugin objects, `Class<?>`, `Method`, `MethodHandle`, singletons, or caches in application code still pointing to classes defined by that loader.
- Threads still running plugin code, tasks in executors, timers, listeners, callbacks, `ThreadLocal`, or thread context class loaders still holding links to the plugin.
- A `jobject`/`jclass` stored by JNI as a **global reference** and not yet released with `DeleteGlobalRef` can keep the corresponding object/class alive. Native caches that store class and method IDs without lifecycle control also easily become a source of bugs during reload.
- Native threads created/attached to the JVM, callbacks, or C-side handles still using resources of the old plugin version; unloading should not happen while a thread can still execute code in the library.
- Frameworks, registries, MBeans, schedulers, or logging appenders still holding references to the old loader.

`WeakReference<ClassLoader>` can help **observe** whether a loader has become collectible after releasing references; by itself, it does not force the loader to be GC'd and does not prove the native file has actually been released by the operating system.

### 5.2. Native memory does not belong exclusively to the “plugin's heap”

Class loaders organize **type identity** and JNI bindings within the JVM; they **do not create a process-level sandbox**. C code can hold native heap pointers, file descriptors, sockets, threads, process-global data, and dependencies on system libraries. These resources do not disappear automatically when Java objects are no longer in use. A buggy native library can even crash the entire JVM.

Therefore, the dispose mechanism must clearly describe the lifecycle of native handles, callbacks, threads, and buffers; dropping the class loader is only one part of the entire teardown process.

## 6. Designing for plugin systems and hot reload

### 6.1. Recommended design: a fixed JNI bridge, with plugins only calling a shared Java API

If multiple plugins need **the same JNI library** within the same process, place the class declaring `native` and the `System.loadLibrary` call in a **shared Java module defined by a stable parent loader**. Child plugin loaders delegate to share that bridge's Java API.

```text
Application / shared parent loader
└── shared.NativeBridge
    ├── static { System.loadLibrary("native_core"); }
    └── public static native int compute(int value);
         ↑
         ├── Plugin loader A → calls shared.NativeBridge.compute(...)
         └── Plugin loader B → calls shared.NativeBridge.compute(...)
```

Java bridge example (only a fragment for the architectural structure; the `native_core` library and corresponding JNI function need to be implemented):

```java
package shared;

public final class NativeBridge {
    static {
        System.loadLibrary("native_core");
    }

    private NativeBridge() {}

    public static native int compute(int value);
}
```

Both plugins call **the native method declared on the same `shared.NativeBridge`**, because that is the parent loader's class. Note: having the library loaded by the parent loader **does not automatically guarantee** that a `native` method *declared separately in a class defined by a child loader* can link to that library. Therefore, place the native entry points themselves in the shared bridge and communicate through a stable Java interface/API.

**Benefit:** plugins can reload Java logic without needing to reload the same JNI library. **Limitation:** the native core is a component with the parent loader's lifecycle; replacing the native core version still usually requires restarting the JVM or changing the processing architecture.

### 6.2. When plugins need different native versions

Do not rush to copy the same library to another name and call `System.load` as an isolation mechanism. Depending on the OS/linker, the copies may still share dependencies on global symbols, shared libraries, or system state; JNI code and C code are usually not designed to coexist in multiple versions within one process. It is especially dangerous if two versions have different C++ ABIs, different native singletons, or overlapping resource management.

There are three approaches to consider:

1. **Design the native API to allow multiple independent instances** within the same library: each instance uses an opaque handle, without relying on static global mutable state; plugins call the shared Java bridge to create/destroy handles. This is a simple approach if the need is for multiple plugins to own different **state** rather than multiple different machine-code versions.
2. **A separate child process for the native component** when independent version upgrades are needed. Java communicates with the worker via IPC/RPC; when updating the native library, stop/restart the worker process. This provides the clearest lifecycle boundary and reduces the impact of native crashes on the main JVM.
3. **Separate class loader and separate native library** only when the architecture, deployment mechanism, and dependencies have been verified for all target platforms. You must still accept that unloading is not immediate and “replace while running” is not an API guaranteed by JNI.

If the requirement is to **frequently reload Java plugins** while the JNI library is stable, approach (1) or a parent bridge is usually suitable. If the requirement is to **replace running native code without restarting the Java application**, the child-process approach is usually easier to control.

### 6.3. Procedure for stopping a plugin before attempting to release the loader

For a plugin that genuinely owns its own JNI library, a reasonable teardown order is:

1. Stop routing new requests to the plugin and wait for/cancel running tasks according to the application contract.
2. Call `close()`/`dispose()` APIs in Java and native code to stop callbacks, threads, executors, and timers; release native handles, buffers, and related resources.
3. Unregister listeners/registries, clean up `ThreadLocal`, clear caches, and properly delete JNI global references; avoid leaving thread context class loaders pointing to the old loader.
4. Close `URLClassLoader` (if used) to release file/JAR lookup resources; drop any remaining strong references to the loader, classes, and plugin objects.
5. Monitor whether the loader can be GC'd and check the library state using diagnostic tools. **Do not** design loading the new version based on the assumption that step 4 has completed native unloading.

These steps help reduce leaks, but **do not turn the JVM into an instantaneous native library replacement system**. If switching versions at a deterministic point in time is mandatory, use a restart of the process hosting the library or a dedicated, verified version-handoff protocol.

## 7. Distinguishing commonly misdiagnosed errors

`UnsatisfiedLinkError` does not have just one cause. Classify by timing and error details:

| Symptom | What to check |
| --- | --- |
| `no native_core in java.library.path` | Logical name, file location, search path, `findLibrary`, and packaging |
| `Native Library ... already loaded in another classloader` | Which class called `System.load`, that class's defining loader, and which library was loaded earlier |
| `Can't find dependent libraries` or linker dependency error | Dependent libraries, OS loader path, C/C++ runtime, architecture |
| `wrong ELF class`, `not a valid Win32 application`, wrong machine type | CPU/OS/bitness/ABI of the JVM and the native library |
| `'...nativeMethod(...)'` / `Native method not found` after loading the library | JNI symbol name, `javac -h`, descriptor, static/instance, `RegisterNatives`, symbol visibility |
| JVM crash or data corruption despite successful load | JNI signature, pointer/reference lifetime, synchronization, native memory safety |

Some cases report errors at **file load time**, while others only report at **the first time the JVM needs to link the native method**. Preserve the full stack trace and original message, then inspect the library actually loaded; do not draw conclusions from the exception name alone.

### Observation tips

- In Java, print `someClass.getClassLoader()` and identify the class performing `System.load`; if needed, compare the loader's object identity rather than just the class loader name.
- Use `javap -s` to inspect Java descriptors; `javac -h` to generate JNI prototypes; use `nm -D`/`readelf -Ws` on Linux or `dumpbin /exports` on Windows to inspect native symbols.
- JFR events `jdk.NativeLibraryLoad` and `jdk.NativeLibraryUnload` can help observe library lifecycles on supported JDKs; check the recording configuration and JDK version. An observed unload event is evidence, whereas **not seeing an event** is not sufficient to conclude there is only a class loader leak.
- With the HotSpot JVM, `jcmd <pid> VM.classloader_stats` can help investigate surviving loaders; specific commands/diagnostics depend on the JDK.

### Two common misconceptions

**“Renaming the native file isolates the plugin.”** There is no guarantee: native code lives in the same process and can share symbols, dependencies, native globals, and memory; a loader with a new name only partially addresses how the JVM identifies the path.

**“Calling `URLClassLoader.close()` means the library has unloaded.”** False. `close()` closes the resources the loader uses to search for classes/JARs; already-loaded classes can still be used. Reclaiming the class loader and releasing the JNI library are separate lifecycle steps, depending on GC and live references.

## 8. Self-check questions

**1.** Two plugins have identical `plugin.NativeProbe` classes defined by two independent class loaders. Both call `System.loadLibrary("native_core")`. The first plugin has loaded successfully. Is the second plugin guaranteed to be able to load?  
**No.** If both resolve to the same JNI native library while the first loader still owns it, the second loader is blocked with `UnsatisfiedLinkError`.

**2.** A plugin's JAR is updated and a new loader is created, but the existing `native` methods still have to use the same library. Is there an approach to reduce conflicts?  
**Yes.** Move the `native` declaration/entry point into a **shared bridge loaded by a parent loader**, so plugins call it through a unified Java API. Reloading a plugin then does not require reloading the native library.

**3.** Why shouldn't `System.gc()` be part of the native version update flow?  
Because GC provides no guarantee about **when** the loader will be reclaimed or the library unloaded. As long as a single strong reference, thread, or global JNI ref remains, the old lifecycle can continue.

**4.** If an application needs to upgrade the C/C++ code itself per plugin without restarting the main JVM, which architectural direction is clearest?  
Use a native worker **in a separate process** and communicate over IPC/RPC; restarting the worker releases its binary, heap, threads, and libraries along the process boundary.

**5.** Does enabling `--enable-native-access=ALL-UNNAMED` on JDK 24+ allow loading the same JNI library into two class loaders?  
**No.** This option concerns permission to use native APIs, while the rule that **one JNI library cannot simultaneously belong to two class loaders** still applies.

## 9. Takeaways and reference documentation

- **The ownership unit of a JNI library is the class loader**, so you must know which class performs the load and which loader defined that class.
- **A JNI library cannot be simultaneously loaded by multiple class loaders**. The typical error is `UnsatisfiedLinkError`; do not confuse it with a missing file or missing JNI symbol error.
- **Classloader reload is not equivalent to native-library hot reload**. `URLClassLoader.close()`, replacing JARs, replacing native files, and calling `System.gc()` all do not guarantee synchronous unload/reload.
- To reload Java code easily, use a **shared Java/native bridge**. To upgrade native code at a deterministic point in time, use a **process boundary** or a dedicated lifecycle design.
- JNI cleanup requires an explicit procedure for callbacks, threads, native handles, and global references; do not rely on `JNI_OnUnload` to handle critical business logic in a timely manner.

Authoritative sources to verify the relevant contracts:

- [Oracle JNI Specification — Invocation API, Library and Version Management (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): the rule that each class loader manages native libraries and `JNI_OnLoad`/`JNI_OnUnload`.
- [Oracle JNI Specification — Design Overview (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): native method linking, naming, `System.loadLibrary`.
- [Java SE 17 API — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): the actual meaning of `close()`.
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): `--enable-native-access` and changes starting in JDK 24.

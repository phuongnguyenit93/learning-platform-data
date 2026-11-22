# UnsatisfiedLinkError and Native Libraries in Multiple ClassLoaders

## 1. The Problem: Java Classes Can Be Isolated, but a JNI Library Cannot Be Arbitrarily Loaded into Multiple Loaders

In a plugin system, a common architecture is for each plugin to own a `URLClassLoader` to load its own implementation classes and dependencies. Classes with the same *binary name* can still coexist simultaneously if defined by **two different defining class loaders**. However, if each plugin executes `System.loadLibrary("nativecodec")` or `System.load("/absolute/path/libnativecodec.so")` on **the same JNI native library**, a subsequent load into another loader can fail with:

~~~text
java.lang.UnsatisfiedLinkError: Native Library ... already loaded in another classloader
~~~

This is not necessarily a missing-file error. In the typical case, **the library was found and successfully loaded**, but it is already associated with a different class loader.

The Java 17 JNI specification states clearly: **each class loader manages its own set of native libraries; the same JNI native library cannot be loaded into multiple class loaders**. When attempting to do so, the JVM throws `UnsatisfiedLinkError`. This rule is intended to protect *class-loader namespace separation*, preventing native code from mixing classes that have the same name but different runtime identities.

Therefore, the right question is not only "has `java.library.path` been configured?" but also:

1. **Which native library** is being loaded: logical name, absolute path, actual binary, native dependencies?
2. **Which Java class** calls `System.load`/`System.loadLibrary`? Which **defining loader** does it belong to?
3. **Has that library already been loaded into another loader?** Has the lifecycle of the previous loader truly ended?
4. Does the error occur when **loading the native library**, or when **linking the `native` call to its symbol**?
5. Can plugins use **a shared JNI bridge in the parent loader** instead of reloading the library in each child?

This lesson distinguishes the root causes, designs the right loader architecture, and builds a runnable **Java 17 + C/JNI** example to reproduce accurately the loading of the same library from two class loaders.

## 2. Where Does `UnsatisfiedLinkError` Sit in Java's Error Hierarchy?

Inheritance hierarchy:

~~~text
java.lang.Object
  └── java.lang.Throwable
      └── java.lang.Error
          └── java.lang.LinkageError
              └── java.lang.UnsatisfiedLinkError
~~~

`UnsatisfiedLinkError` is an **`Error`**, not a checked `Exception`. It can arise when the JVM fails to link a native method declaration to a suitable implementation, or when a `System.load`/`System.loadLibrary` operation fails.

Example:

~~~java
public final class NativeCodec {
    static {
        System.loadLibrary("nativecodec");
    }

    public static native int encode(int value);
}
~~~

This is an **illustrative code snippet**, not standalone runnable code because it requires an actual native library containing the implementation for `NativeCodec.encode`.

One of several error forms you may see:

~~~text
java.lang.UnsatisfiedLinkError: no nativecodec in java.library.path: ...
~~~

Cause: the library was not found in the configured search path.

Another form:

~~~text
java.lang.UnsatisfiedLinkError: Native Library ... already loaded in another classloader
~~~

Cause: the same JNI library is already associated with another loader.

Yet another form:

~~~text
java.lang.UnsatisfiedLinkError: 'int NativeCodec.encode(int)'
~~~

This is an **illustrative form** for the case where a native method has no matching entry point/signature; the exact exception message text depends on the JDK and signature.

All three are `UnsatisfiedLinkError`, yet they require **three different investigation strategies**. It is not automatically resolved by adding JARs, increasing reflection permissions, or renaming the Java class.

## 3. How JNI Mechanisms Work with ClassLoaders

Java provides two related models that we need to distinguish.

**Java bytecode loading:**

~~~text
App class loader
  |
  +-- PluginLoader A -> (plugin.NativeBridge, Loader A)
  |
  +-- PluginLoader B -> (plugin.NativeBridge, Loader B)
~~~

Two `Class<?>` instances named `plugin.NativeBridge` are two runtime types if each child defines its own.

**JNI native library management:**

~~~text
PluginLoader A
      |
  System.load("/opt/native/libbridge.so")
      |
      v
JVM native-library registry / loader A
      |
      +--> libbridge.so  [loaded]

PluginLoader B
      |
  System.load("/opt/native/libbridge.so")
      |
      v
JVM detects the same JNI library belongs to loader A
      |
      +--> UnsatisfiedLinkError
~~~

**Fundamental rule:** loading a Java class into loader B **does not turn a native library already bound to A into a library of B**. The JVM manages information about native libraries, JNI entry points, and classloader ownership according to the JNI specification.

### Why Is This Limitation Necessary?

JNI receives references to Java objects/classes and can cache `jclass`, `jmethodID`, `jfieldID`, global references, or register native methods using `RegisterNatives`. Two Java classes with the **same binary name** but different defining loaders **are not the same runtime type**.

If a native binary were arbitrarily bound to two classloader namespaces, native code could mix up metadata/type references and break the type isolation that the JVM seeks to maintain. For this reason, JNI does not simply treat native code as a "process-wide library usable by any class" in a classloader-independent sense.

**Do not confuse this with parent loader behavior:** if both plugins actually delegate to **the same Java JNI wrapper class in the parent**, then the native method is invoked through **a single runtime class** and a single native library loaded in the parent. This is an important architectural solution, explained in a later section.

## 4. Two Ways to Load a Library: `System.load` and `System.loadLibrary`

| API | Argument | Example | Important Notes |
|---|---|---|---|
| `System.load(String absoluteFilename)` | **Absolute path** to the native binary | `System.load("/opt/demo/libbridge.so")` | Do not pass a relative path |
| `System.loadLibrary(String libname)` | **Logical name**, without path, prefix, or extension | `System.loadLibrary("bridge")` | Relies on JVM/OS library search rules and `findLibrary` when applicable |
| `System.mapLibraryName(String libname)` | Logical name | `System.mapLibraryName("bridge")` | Returns the platform-specific filename; does not load the library itself |

Examples of mapped names:

~~~text
Linux:   bridge -> libbridge.so
macOS:   bridge -> libbridge.dylib
Windows: bridge -> bridge.dll
~~~

These are **typical names**, while actual naming conventions and binary formats may vary depending on the platform/implementation.

### `System.load`

~~~java
import java.nio.file.Path;

String absolute = Path.of("native", "libbridge.so")
        .toAbsolutePath().normalize().toString();

System.load(absolute);
~~~

This is an **illustrative snippet** for Linux, requiring the file `libbridge.so` to exist and be a valid native binary. On macOS/Windows, the filename differs. This operation **does not bypass the restriction on loading a JNI library across multiple loaders**: passing a valid absolute path to both child loaders can still cause the second loader to fail.

### `System.loadLibrary`

~~~java
System.loadLibrary("bridge");
~~~

Do not write:

~~~java
System.loadLibrary("libbridge.so");   // Wrong way to call the standard API
System.loadLibrary("/opt/native/libbridge.so");  // Wrong: contains a path
~~~

Depending on the system, the JVM searches native library locations associated with `java.library.path`, custom `ClassLoader.findLibrary`, and the operating system. If the `bridge` library is not present where the JVM searches, an `UnsatisfiedLinkError` of the form "no bridge in java.library.path" will be thrown.

### `findLibrary` in a Custom Loader

`ClassLoader` provides a hook:

~~~java
@Override
protected String findLibrary(String libname) {
    if ("bridge".equals(libname)) {
        return "/opt/my-plugin/native/libbridge.so";
    }
    return null;
}
~~~

This is an **illustrative override snippet in a ClassLoader subclass**. The method must return a valid **absolute path**; return `null` to fall back to the default search mechanism. The hook helps the loader locate the right binary; **it does not allow** loading the same JNI binary into countless independent loaders.

### Do Not Treat `java.library.path` as "Loader Ownership"

`java.library.path` solves **the native library search path**, not the problem where the same binary is already registered under another loader. Placing the file in the right path can fix "no library in path" errors, but it **does not** fix "already loaded in another classloader" errors.

Changing `System.setProperty("java.library.path", "...")` after the program is already running **is not guaranteed** to alter the search path that the JVM has already prepared/cached. Prefer configuring it at startup or passing an absolute path via `System.load` with a clear loader ownership mechanism.

## 5. Main Causes of UnsatisfiedLinkError

| Typical Symptom / Message | Cause | Resolution Approach |
|---|---|---|
| `no bridge in java.library.path` | Native binary is not in the search path | Check startup flags, `findLibrary`, absolute path |
| `already loaded in another classloader` | Native binary is already owned by another loader | Single shared JNI bridge in parent; change lifecycle/loader policy |
| `Can't load ...` or "wrong ELF class" | Binary has wrong architecture/bitness or OS | Use a binary matching the OS/CPU/ABI |
| `... cannot open shared object file ...` | Native binary or **a downstream native dependency** was not found | Check the OS loader and transitive native dependencies |
| `undefined symbol` / `symbol not found` | Export/symbol ABI mismatch | Check JNI header, C exports, linker, overloads |
| Native method fails to link | Correct JNI name not exported, library not loaded yet, wrong signature | Use `javac -h`, `JNIEXPORT`, `JNICALL`, `RegisterNatives` if designed that way |
| `JNI_OnLoad` returns an unsupported JNI version | Startup hook reports a version unsupported by the VM | Return a valid JNI version according to the JNI spec |
| Fails only on plugin redeploy | Old loader is still alive and holding the library | Stop threads, drop references, inspect class unloading/native unloading |
| Fails only on CI/server machine | Different OS, CPU, permissions, runtime image, loader paths | Collect environment and native dependency reports |
| Fails only when both plugin A and B are enabled | Two separate plugin loaders both call `System.load` on the library | Inspect the wrapper's defining loader and native registry |

**Note:** exact wording and nested causes depend on the platform/JDK. The rows above are diagnostic patterns, **not guaranteed byte-for-byte messages**.

### Distinguishing Missing Native Binary Errors from Java Class Loading Failures

`ClassNotFoundException` occurs when code fails to look up a Java class by name.

`NoClassDefFoundError` typically occurs when the JVM needs a Java class definition but fails to find/link/initialize it from a bytecode reference; it can have various causes.

`UnsatisfiedLinkError` occurs during **native linking/loading**, for example when a native binary cannot be found or a native method has not yet been linked. A class `plugin.NativeBridge` may have been found completely validly by the Java classloader, yet its `System.loadLibrary` initializer still throws `UnsatisfiedLinkError`.

## 6. Java 17 + JNI/C Example Reproducing the Error in the Second Loader

This example uses **a real native library**, rather than simulating the error by writing `throw new UnsatisfiedLinkError(...)` manually. Two different `URLClassLoader` instances each define the Java wrapper `plugin.NativeBridge`. The wrapper contains a static initializer that calls `System.load(absolutePath)`.

Experiment flow:

~~~text
                     Host: NativeLoaderLab
                               |
       +-----------------------+-----------------------+
       |                                               |
 URLClassLoader A                                URLClassLoader B
       |                                               |
 plugin.NativeBridge (A)                        plugin.NativeBridge (B)
       |                                               |
 System.load(native shared lib)                 System.load(SAME lib)
       |                                               |
       v                                               v
 First load succeeds                         UnsatisfiedLinkError
       |
 NativeBridge.answer() -> 42
~~~

**Requirements:** JDK 17+, a C compiler/linker capable of producing a compatible JNI shared library, and no copy of `plugin.NativeBridge` on the host's application classpath.

### 6.1. Directory Structure

~~~text
project/
  src/
    plugin/
      plugin/
        NativeBridge.java
    host/
      NativeLoaderLab.java
    native/
      nativelab.c
  out/                       (generated during build)
    plugin/
    host/
  native/                    (header and .so/.dylib/.dll generated during build)
    plugin_NativeBridge.h
    libnativelab.so
~~~

On macOS, the native output can be `libnativelab.dylib`; on Windows, it is `nativelab.dll`. Do not attempt to use a Linux `.so` on Windows.

### 6.2. File `src/plugin/plugin/NativeBridge.java`

~~~java
package plugin;

public final class NativeBridge {
    static {
        String absolutePath =
                System.getProperty("demo.native.path");

        if (absolutePath == null) {
            throw new IllegalStateException(
                    "Missing demo.native.path");
        }

        System.load(absolutePath);
    }

    private NativeBridge() {
    }

    public static native int answer();
}
~~~

- Each loader defines `plugin.NativeBridge` itself because this class **is not on the application classpath**.
- The static initializer runs **when the class is initialized**, not merely because of `Class.forName(name, false, loader)`.
- `System.load` receives the absolute path set by the host from the command-line argument.
- `answer()` is a native method with no Java method body; the JVM links it to the JNI function in the library.

### 6.3. File `src/native/nativelab.c`

~~~c
#include "plugin_NativeBridge.h"

JNIEXPORT jint JNICALL
Java_plugin_NativeBridge_answer(JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    return 42;
}
~~~

The header `plugin_NativeBridge.h` is automatically generated by the `javac -h` tool from the Java declaration. Using the generated header avoids guessing the signature manually; the native implementation receives `JNIEnv *` and `jclass` because `answer()` is a **static native method**.

This is the complete JNI C implementation for the example's method. There is no need to call `RegisterNatives` because the symbol is exported following the **JNI naming convention**.

### 6.4. File `src/host/NativeLoaderLab.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class NativeLoaderLab {
    private static final String BRIDGE = "plugin.NativeBridge";

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: NativeLoaderLab <plugin-dir> <native-lib>");
        }

        URL pluginRoot = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();

        String nativePath = Path.of(args[1])
                .toAbsolutePath().normalize().toString();

        System.setProperty("demo.native.path", nativePath);

        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loaderA = new URLClassLoader(
                    "plugin-A", new URL[]{pluginRoot}, parent);
             URLClassLoader loaderB = new URLClassLoader(
                    "plugin-B", new URL[]{pluginRoot}, parent)) {

            // Load only, without running the static initializer yet.
            Class<?> classA = Class.forName(BRIDGE, false, loaderA);
            Class<?> classB = Class.forName(BRIDGE, false, loaderB);

            System.out.println("same binary name: "
                    + classA.getName().equals(classB.getName()));
            System.out.println("same runtime type: "
                    + (classA == classB));
            System.out.println("A owns class: "
                    + (classA.getClassLoader() == loaderA));
            System.out.println("B owns class: "
                    + (classB.getClassLoader() == loaderB));

            // Initializing class A calls System.load(nativePath).
            Class.forName(BRIDGE, true, loaderA);
            Object answer = classA.getMethod("answer").invoke(null);
            System.out.println("first native answer: " + answer);

            // Initializing class B tries to load SAME JNI library
            // but the library already belongs to loader A.
            try {
                Class.forName(BRIDGE, true, loaderB);
                System.out.println("second native load: success");
            } catch (UnsatisfiedLinkError error) {
                System.out.println(
                        "second native load: UnsatisfiedLinkError");
            }
        }
    }
}
~~~

**Explanation of each technique:**

1. The parent is the **platform class loader** so that the two plugin loaders do not accidentally pick up `plugin.NativeBridge` from the application classpath. In production, the parent typically needs to contain shared APIs; the demo does not need a separate API.
2. `Class.forName(BRIDGE, false, loader)` returns the runtime `Class<?>` **without running the static initializer yet**; this allows observing the same name with different defining loaders.
3. `Class.forName(BRIDGE, true, loaderA)` runs class A's initializer, calling `System.load`; the native lib is loaded under loader A.
4. Invoking `answer()` via reflection calls the JNI function and returns the integer 42.
5. `Class.forName(BRIDGE, true, loaderB)` runs class B's **separate** initializer, attempting to load the same library; the JVM detects that the library belongs to loader A and throws `UnsatisfiedLinkError`.
6. The program prints only **the error type**, without depending on the text of `error.getMessage()` or the actual path on the machine.
7. `URLClassLoader.close()` closes Java loader resources such as JAR/file handles; **it does not guarantee that the native library is unloaded immediately**.

### 6.5. Building on Linux (Bash + GCC)

Run from the `project` directory. First, you need a **JDK** and `gcc`; `JAVA_HOME` must point to the JDK in use:

~~~bash
mkdir -p out/plugin out/host native

javac -h native -d out/plugin \
    src/plugin/plugin/NativeBridge.java

javac -d out/host src/host/NativeLoaderLab.java

gcc -fPIC -shared \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    -Inative \
    -o native/libnativelab.so \
    src/native/nativelab.c

java -cp out/host NativeLoaderLab \
    out/plugin native/libnativelab.so
~~~

If `JAVA_HOME` is not set yet, determine it from the installed JDK directory, for example on many Linux systems:

~~~bash
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
~~~

This command **depends on the system's JDK layout**; on other systems, set `JAVA_HOME` manually. To verify: the files `"$JAVA_HOME/include/jni.h"` and `"$JAVA_HOME/include/linux/jni_md.h"` must exist.

**Important:** `-cp out/host` contains only the host class. **Do not add `out/plugin` to the application classpath**, otherwise the parent/caller could see the Java wrapper first and the two-defining-loaders experiment would no longer hold.

### 6.6. Building on macOS (Bash + Clang)

After the two `javac` commands above, replace the Linux GCC command with:

~~~bash
clang -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    -Inative \
    -o native/libnativelab.dylib \
    src/native/nativelab.c

java -cp out/host NativeLoaderLab \
    out/plugin native/libnativelab.dylib
~~~

You can use `/usr/libexec/java_home` to determine `JAVA_HOME` when the JDK is installed in the standard macOS layout. On Apple Silicon machines, you must build the native binary for the exact architecture of the running Java process.

### 6.7. Building on Windows

Use **Visual Studio Developer Command Prompt** with the MSVC C compiler `cl` and `JAVA_HOME` set to the JDK:

~~~bat
mkdir out\plugin
mkdir out\host
mkdir native

javac -h native -d out\plugin src\plugin\plugin\NativeBridge.java
javac -d out\host src\host\NativeLoaderLab.java

cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" /I "native" src\native\nativelab.c /Fe:native\nativelab.dll

java -cp out\host NativeLoaderLab out\plugin native\nativelab.dll
~~~

These commands are for **Command Prompt**, not PowerShell; the prerequisites are that `cl`/the linker/SDK are configured, the output native file is generated successfully, and the DLL architecture matches the JVM. On Windows, dependent libraries may need to reside in the operating system's DLL search path.

### 6.8. Expected Stdout

For a fresh program run in a clean JVM, with the correct library and without `plugin.NativeBridge` on the parent classpath:

~~~text
same binary name: true
same runtime type: false
A owns class: true
B owns class: true
first native answer: 42
second native load: UnsatisfiedLinkError
~~~

**This is the expected output according to the JNI specification**; C compiler/linker or launcher failures will prevent the program from reaching this step. The detailed message string of `UnsatisfiedLinkError` may vary across JDKs/OSes; the demo avoids printing it.

This error is not caused by the `answer()` function being missing: class A's call returns 42, proving that the native library and JNI symbol work. The second error occurs when **registering the same library under a different defining loader**.

### 6.9. Should You Catch `UnsatisfiedLinkError` and Continue Like the Demo?

In the demo, catching the error is strictly to **classify the outcome intentionally**. In production, you should not catch it and pretend that the plugin initialized successfully: **initialization of class B has failed**, which can leave that class in an erroneous state. Subsequent uses may throw `NoClassDefFoundError: Could not initialize class ...`.

If native loading fails, **abort activating that plugin generation**, log the full error/cause, and fix the loader architecture or native packaging before retrying with a new generation. Do not blindly loop `System.load` or re-instantiate a class whose initialization has already failed.

## 7. Preferred Solution: A Single JNI Bridge Owned by the Parent Loader

If multiple plugins in the same JVM use **a native implementation with shared state**, it is usually best to load the JNI wrapper and native library **once in a shared parent loader**:

~~~text
                 Application loader (parent)
                   |
            api.NativeBridge
            static { System.loadLibrary("bridge"); }
            public static native int answer();
                   |
            libbridge.so / bridge.dll
                   |
       +-----------+-----------+
       |                       |
 PluginLoader A            PluginLoader B
  plugin.ImplA              plugin.ImplB
       |                       |
       +---------call----------+
                 |
           api.NativeBridge
        (the same Class object)
~~~

Both plugins delegate loading `api.NativeBridge` to the parent; the parent defines **a single runtime class** containing the native method declaration. When calling the native bridge, they do not attempt to call `System.loadLibrary` on the same JNI binary from two separate defining loaders.

### 7.1. Shared API and Separate Implementations

For a cleaner design, split them as follows:

~~~text
shared-api.jar (application classpath)
  api.NativeCodec                    <- public interface

shared-native-bridge.jar (parent)
  bridge.JniNativeCodec              <- class calling System.loadLibrary

plugin-a.jar (child A)
  plugin.a.ServiceA                   <- uses api.NativeCodec

plugin-b.jar (child B)
  plugin.b.ServiceB                   <- uses api.NativeCodec
~~~

The parent owns both **the JNI wrapper with native methods** and the native binary; the shared interface also belongs to the parent. When a plugin needs a native function, it calls through the parent's public API or a service object provided by the parent.

This offers these benefits:

- Avoids reloading the same native library across each plugin classloader.
- Minimizes duplicate JNI-related Java wrapper classes.
- Places the initialization/shutdown point of native state in a component with a clear lifecycle.
- Makes it easier to diagnose and control the shared JNI ABI version.

**Trade-off:** plugins cannot simultaneously use native library versions with incompatible ABIs by pretending they are two separate class versions. If true version isolation is needed, **process isolation** or completely independent native binaries with controlled names/paths and state may be required. There is no guarantee that copying the same `.so`/.dll and renaming it into two files is sufficiently safe.

### 7.2. Why Is "Putting Only the Shared Interface in the Parent" Not Enough?

Suppose the parent has `api.NativeCodec`, but each plugin child still defines its own `plugin.NativeBridge` with a static initializer calling `System.loadLibrary("bridge")`.

Even though both plugins can cast to `api.NativeCodec`, the native bridge classes are still owned by **two separate defining loaders**; they can still contend over the same JNI library.

Instead, it is better to place **the class that actually calls `System.load/System.loadLibrary` and declares the native methods** in the parent or a sufficiently stable shared loader, and then expose the method/service to plugins.

### 7.3. When Should You Not Load a Native Library into the Parent?

Not every native library can be shared:

- Two plugins require **genuinely different native ABIs or versions**.
- The native code maintains **process-global state**, does not support multi-tenancy, has singletons/worker threads, or makes callbacks into plugin classes.
- The wrapper API in the parent cannot configure separate state per plugin.
- A plugin is untrusted or requires different operating system privileges.
- The native library has a lifecycle tied to a single plugin and is not used by the rest of the application.

In these cases, you must design an explicit boundary, possibly using a separate process. A different classloader **is not equivalent to a separate native process**.

## 8. Why Is "Copying the Library into Multiple Files" Not the Default Solution?

Some applications extract the same native binary into multiple temp directories under different names so that each plugin calls `System.load` on a different path.

This approach **may change path identity in some implementations**, but it is not a portable or JNI-guaranteed solution for isolating native state, because:

- The OS dynamic loader may have different image canonicalization/deduplication policies.
- Internal native dependencies may still be **the exact same shared libraries** with global/static state.
- The native code itself may use process-global singletons, locks, network ports, temp files, or C runtime state.
- The native code may store `JNIEnv*` or `jclass` with an invalid lifecycle, causing crashes/undefined behavior.
- Two identical binaries can still export duplicate JNI symbols or point to the same downstream native runtime.
- On Windows, it is often difficult to delete/overwrite a DLL currently held open by a process.
- Packaging multiple copies leaves behind temp-file clutter, library handle leaks, and makes security audits harder.

If a library has official documentation confirming support for **multi-classloader JNI instances**, follow the vendor's specific mechanism. Otherwise, a **shared parent bridge** or **separate process** are two options that are easier to prove correct.

## 9. `JNI_OnLoad`, `JNI_OnUnload`, and Opportunities to Unload a Library

JNI has optional lifecycle callbacks:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_8;
}

JNIEXPORT void JNICALL
JNI_OnUnload(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    // Only clean up resources that can be cleaned up safely.
}
~~~

This is an **illustrative C snippet for hooks**, and does **not** need to be merged into the demo's `nativelab.c` file to run; if you add hooks, ensure these symbols are not defined twice in the same library.

- `JNI_OnLoad` is called by the VM when a dynamic native library is loaded if the library exports the hook. The hook returns the JNI version required by the library.
- `JNI_OnUnload` may be called when the class loader owning the library is collected by GC. **There is no universal Java command that guarantees calling the hook at the exact moment desired**.
- The specification advises `JNI_OnUnload` to use Java VM services **with caution** because the callback may execute in an unpredictable context. Avoid arbitrary callbacks into Java inside the cleanup hook.
- Do not store `JNIEnv*` across threads: `JNIEnv` is bound to a thread. For native threads, use the proper attach/detach JVM API mechanism.
- Do not hold Java object/class references long-term without managing local/global/weak global references according to the JNI contract.

### Does `URLClassLoader.close()` Unload a JNI Library Immediately?

**There is no such guarantee.** `URLClassLoader.close()` closes the file/JAR handles that the URLClassLoader opened. It is **not** an arbitrary `dlclose`/`FreeLibrary` API for JNI libraries.

A native library associated with a loader may have an opportunity to be unloaded when the loader is genuinely no longer reachable and is collected by GC, but:

1. Running threads, callbacks, TCCL, static caches, or application registries may keep the loader/class/plugin objects alive.
2. The JVM does not guarantee that GC/unloading occurs immediately after `System.gc()` or `close()`.
3. The native library may hold resources, threads, and global references that require dedicated cleanup.
4. Unloading policies and native dependency behavior also depend on the JVM/OS.

**Do not use `System.gc()` as a promise that you can immediately reload the library into another loader.** Manage lifecycles proactively, and design a shared native bridge if Java plugins need to be redeployed frequently.

## 10. `RegisterNatives`, JNI Symbols, and Native Method Linkage

`UnsatisfiedLinkError` does not only occur when loading a library. After the library is loaded, when Java code invokes a `native` method, the JVM still must find the corresponding implementation.

### 10.1. JNI Naming

For the Java declaration:

~~~java
package plugin;

public final class NativeBridge {
    public static native int answer();
}
~~~

The standard JNI C symbol (no overloads in this example) is:

~~~c
JNIEXPORT jint JNICALL
Java_plugin_NativeBridge_answer(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return 42;
}
~~~

Use `javac -h native ...` to generate the exact header. If a native method has **overloads**, the symbol name may include signature information mangled according to JNI rules; you should not guess it manually.

With C++, you must export symbols with the proper linkage (JDK-generated JNI headers typically handle `extern "C"` via appropriate macros/structures). With a C#/.NET native shim or Rust, you must export the ABI/symbol according to the JNI contract and the respective toolchain.

### 10.2. `RegisterNatives`

A native library can register function pointers using `RegisterNatives`. This approach can be useful for generated/proxy JNI integrations, but it also requires:

- Using the exact `jclass` of the **runtime class to be registered**.
- Method names/signatures matching the Java declaration.
- Not confusing two classes with the same binary name that belong to different defining loaders.
- Managing JNI references and thread-safe native state.

**Do not** use `RegisterNatives` as a trick to bypass the rule "same JNI library cannot be loaded into more than one classloader". Library ownership according to JNI must still be respected.

### 10.3. Distinguishing the Two Failure Types by Timing

~~~text
Java class initialization
       |
       +--> System.loadLibrary("bridge")
       |         |
       |         +--> no library / dependency failure
       |         +--> already loaded in another loader
       |         +--> bad architecture / JNI_OnLoad failure
       |
       v
native method invocation
       |
       +--> JNI symbol / RegisterNatives lookup
                 |
                 +--> symbol missing or incompatible signature
~~~

The `UnsatisfiedLinkError` messages from these branches can look similar, so log **which operation failed** along with the stack trace, defining loader, and lib path.

## 11. JNI Class Loader Lookup and Callbacks from Native Code

Native code sometimes calls JNI `FindClass` to look up Java types. The class loader selection rules in JNI can vary depending on the **call context**, for example whether it is running inside a Java native method or from a native-attached thread without an appropriate Java frame.

Common problems:

- The same `plugin.Dto` may be defined separately by each plugin loader.
- Native code incorrectly caches a `jclass` and reuses it for another plugin.
- A native thread that attaches itself to the JVM may not see the plugin's class if it looks up the name using the wrong loader.
- Java's thread context class loader **does not automatically fix all JNI `FindClass` cases on native threads**.

**Recommended design:**

1. Have the Java side pass the appropriately validated `Class<?>`/`ClassLoader`/object into the native bridge when needed; the native code receives a valid JNI object.
2. If native code needs to retain a class/object beyond a single call, create a global/weak global reference using the proper API and clean it up afterward.
3. Do not store `JNIEnv*` in a global variable and use it from another thread.
4. Avoid callbacks across retired plugin generations.
5. If using `RegisterNatives`, register against the exact runtime class, rather than relying solely on name strings.
6. Ensure that APIs/DTOs exchanged by the native bridge with multiple plugins are **defined in the parent loader** or converted into neutral data.

These principles help prevent hard-to-observe JNI bugs, but **they do not make a single JNI library reloadable into multiple defining loaders**.

## 12. Native Library Dependencies on Operating System and CPU Architecture

The classloader may be able to locate the Java wrapper, yet the native binary still needs to be compatible with **the running JVM process**:

| Factor | Example |
|---|---|
| OS | Linux `.so`, macOS `.dylib`, Windows `.dll` |
| CPU instruction set | x86_64, arm64/AArch64 |
| Process bitness | A 64-bit JVM requires a compatible 64-bit native binary |
| Calling convention/ABI | Matching JNI macros and compiler toolchain |
| C/C++ runtime dependencies | Matching glibc/libstdc++/MSVC runtime |
| Transitive native libraries | `libcrypto.so`, runtime DLLs, other native frameworks |
| OS library search path | `LD_LIBRARY_PATH`, rpath, loader configuration, Windows DLL search |
| Security restrictions | File permissions, executable mapping, system policy, hardened runtime/codesigning when applicable |

A file that actually exists yet lacks a **transitive dependency** can still cause `System.load` to fail. Therefore, "file exists = true" does not prove that the loader can map the binary into the process.

### Diagnostic Tools by Operating System

**Linux:**

~~~bash
file native/libnativelab.so
ldd native/libnativelab.so
nm -D native/libnativelab.so
~~~

**macOS:**

~~~bash
file native/libnativelab.dylib
otool -L native/libnativelab.dylib
nm -gU native/libnativelab.dylib
~~~

**Windows:**

~~~text
dumpbin /DEPENDENTS native\nativelab.dll
dumpbin /EXPORTS native\nativelab.dll
~~~

The commands above are **diagnostic commands**, not guaranteed output on every machine; depending on the toolchain, additional flags may be required. `ldd` against untrusted binaries carries risks in some environments; do not run it arbitrarily on artifacts whose provenance has not been verified.

### Checking the Java Process and Library Path

~~~java
System.out.println("java.version="
        + System.getProperty("java.version"));
System.out.println("os.name="
        + System.getProperty("os.name"));
System.out.println("os.arch="
        + System.getProperty("os.arch"));
System.out.println("java.library.path="
        + System.getProperty("java.library.path"));
System.out.println("mapped="
        + System.mapLibraryName("nativelab"));
~~~

This is an **illustrative snippet**. These properties are useful for debugging, but they do not replace analyzing native dependencies and the defining loader.

## 13. Plugin Lifecycle and Redeploy Scenarios

Suppose an application server creates:

~~~text
Generation 1:
  PluginLoader-A
      |
      +-- NativeBridge loads libnativecodec.so
      |
      +-- Plugin A active

Redeploy:
  PluginLoader-A should retire
  PluginLoader-B created
      |
      +-- NativeBridge attempts same libnativecodec.so
      |
      +-- UnsatisfiedLinkError
~~~

Because the JVM cannot yet unload the library belonging to loader A (loader A is still reachable), loader B cannot acquire the same JNI native library as if it had never been used.

**Many indirect references keep loader A alive:**

- Threads created by the plugin have not stopped.
- A `ThreadLocal` or thread context class loader of a thread pool points to the old class/loader.
- The host caches `Class<?>`, plugin objects, `Method`, `MethodHandle`, or provider instances.
- Listeners, registries, scheduled tasks, event subscriptions, MBeans, or classpath framework caches have not been unregistered.
- Native code retains global references or callbacks into the plugin's Java objects.

### Recommended Lifecycle

~~~text
ACTIVE
  |
  | Stop accepting new work
  v
DRAINING
  |
  | Complete in-flight calls
  | Stop plugin threads/background executors
  | Cancel callbacks/listeners, reset TCCL
  | Close streams/URLClassLoader
  | Drop strong references in caches/registries
  v
RETIRED
  |
  | GC/unloading according to JVM conditions
  v
MAY BE UNLOADED  (no timing guarantee)
~~~

If plugins need to be redeployed frequently, **place the JNI bridge in the parent** and manage separate native state per plugin at the Java/native API layer if the library supports it. Do not rely on the old loader being collected by GC at a specific deterministic point in time.

### When Native State Does Not Support Multi-Tenancy

If the native code only has a process-global singleton or does not support multiple versions/instances, a shared API in the parent **still does not solve every requirement**. You need:

- A shared native process managing state according to an explicit contract, or
- Each plugin running in a separate process/container, or
- Redesigning the JNI library to support multiple independent *handles/contexts* when the vendor permits.

## 14. Practical Diagnostic Workflow for UnsatisfiedLinkError

### Step 1 — Identify Which Operation Failed

Inspect the stack trace/cause chain:

- `System.loadLibrary`: lookup by logical name or ownership conflict.
- `System.load`: absolute path/mapping or ownership conflict.
- Invocation of a `native` method: JNI symbol/method registration.
- Static initializer: can cause the entire class initialization to fail.
- Plugin restart: consider classloader leak/native lifecycle.

### Step 2 — Log the Classloader of the Java Wrapper

~~~java
Class<?> wrapper = plugin.NativeBridge.class;
ClassLoader owner = wrapper.getClassLoader();

System.out.println(wrapper.getName());
System.out.println(owner);
System.out.println(wrapper.getModule());
~~~

This is an **illustrative snippet** for an environment that can reference `plugin.NativeBridge` directly; a host that does not have the wrapper on its compile classpath like in the demo must use the `Class<?>` obtained from the explicit loader.

If debugging from the host:

~~~java
Class<?> type = pluginLoader.loadClass("plugin.NativeBridge");

System.out.println(type.getClassLoader() == pluginLoader);
System.out.println(type.getModule());
~~~

**Do not print only the loader name**: two different instances can be given the same name. Compare references using `==` when possible and attach logical generation IDs for logging.

### Step 3 — Check the Native File and Dependencies

- Verify the **actual absolute path** when calling `System.load`.
- If calling `System.loadLibrary`, check that the name **contains no prefix/path/extension**.
- Use OS tools to check architecture, dependencies, and exports.
- Check the actual JDK/JVM process that is running, not just `JAVA_HOME` at build time.
- If the program runs in a container, verify that the library is inside the container image and matches the libc/ABI.
- If duplicate loading is suspected, log the Java wrapper class, owner loader, and plugin generation directly inside the static initializer.

### Step 4 — Confirm an Ownership Conflict

If **loader A already loaded the same JNI binary successfully** and loader B is newly introduced, this is a very strong indicator of the "already loaded in another classloader" cause.

In particular, if restarting **the entire JVM** makes the error disappear while hot-redeploying a plugin triggers it, prioritize investigating **native library ownership + old classloader references**. Restarting the JVM is an operational workaround, not a sustainable lifecycle solution.

### Step 5 — Choose a Fix Using the Table

| Diagnostic Finding | Appropriate Fix |
|---|---|
| Native binary not found | Fix path/packaging and startup configuration |
| Missing native dependency | Package/install native dependencies, fix OS loader path |
| Wrong CPU/OS/bitness | Rebuild for the correct target platform |
| Wrong JNI symbol or missing export | `javac -h`, check `JNIEXPORT`/`JNICALL`/symbol mangling |
| Duplicate load across 2 plugin loaders | Shared JNI bridge in parent or explicit native isolation architecture |
| Cannot unload on reload | Clean up old-loader references; avoid treating GC as deterministic |
| Native library ABI cannot be shared | Separate processes or handle-based multi-instance if the library supports it |
| Untrusted plugin | Isolate at the process/OS boundary, not just the classloader |

### Step 6 — Test in a Clean Environment

A reproduction test should:

1. Use a **fresh JVM**.
2. Log a classloader owner/generation ID every time the native binary is loaded.
3. Load a Java wrapper from loader A and invoke the native method successfully.
4. Create loader B and attempt to load the same binary; classify `UnsatisfiedLinkError`.
5. Test the parent-owned bridge approach: both plugins call the same wrapper runtime type.
6. Test redeploy/shutdown without relying on `System.gc()` as a guarantee of unloading.

## 15. Relationship to ClassNotFoundException and NoClassDefFoundError

In the plugin lifecycle, these errors can appear sequentially, yet they are not identical:

~~~text
Host/Plugin ClassLoader
    |
    +-- loadClass("plugin.NativeBridge")
           |
           +-- Java class not found -> ClassNotFoundException
           |
           +-- Java class found -> Class<?> is created
                    |
                    +-- initialize class
                           |
                           +-- System.load(...)
                                  |
                                  +-- Native binary missing
                                  |     -> UnsatisfiedLinkError
                                  |
                                  +-- Already loaded by other loader
                                  |     -> UnsatisfiedLinkError
                                  |
                                  +-- JNI library loaded
                                          |
                                          +-- native method called
                                                 |
                                                 +-- JNI symbol missing
                                                       -> UnsatisfiedLinkError
~~~

If `System.load` throws `UnsatisfiedLinkError` inside a static initializer, since it is an `Error`, **it can be thrown directly**; it does not necessarily get wrapped in `ExceptionInInitializerError` as happens when an initializer throws a non-Error exception.

Once class initialization has failed, the JVM marks the class as erroneous according to initialization rules; subsequent calls on that class may receive a `NoClassDefFoundError` such as "Could not initialize class ...". Therefore, **do not retry loading the same class indefinitely** after static initialization fails.

Debugging steps must preserve **the first error**, not merely the error from a later retry.

## 16. JNI in the Context of JPMS and Newer Java Releases

JNI native loading and JPMS modularity are **two different control dimensions**:

- `requires`, `exports`, `opens`, and module layers govern readability/access across Java modules.
- `System.loadLibrary` and native method resolution relate to native-library ownership and ABI.
- Adding `--add-opens` does not allow a native library to be loaded into two class loaders at the same time.
- Creating a new `ModuleLayer` does not guarantee that a native library already loaded in another layer/loader can be reloaded independently.
- On newer JDKs with a **restricted native access** mechanism, you must comply with the corresponding native access flags policy (for example, `--enable-native-access` when required by the environment). The demo targets **JDK 17** and does not assume every newer version keeps the exact same warning/denial policy.
- The Foreign Function & Memory API (FFM) or other bridging libraries can change how native code is invoked, but **they do not by default turn native global state into isolated state across plugins**. Do not treat FFM as an "automatic fix" for the lifecycle/ABI of every JNI library.

It is necessary to distinguish **classloader namespace separation**, **JPMS module access**, and **process/OS isolation**; these three concepts serve different needs.

## 17. Safety When Using Native Code and Common Mistakes

JNI code executes with the privileges of the Java process, can access memory, and can spawn native threads. **ClassLoader does not isolate native memory or operating system privileges**; if a plugin is untrusted, a process boundary along with appropriate resource limits and IPC is needed.

Five important misconceptions to avoid:

1. **"Adding `java.library.path` fixes every `UnsatisfiedLinkError`."** The file search path does not resolve JNI symbol/ABI mismatches, native dependencies, CPU architecture, or *already loaded in another classloader*.
2. **"A native library loaded for plugin A is automatically usable by plugin B."** JNI tracks library ownership per loader; if two children each call `System.load`, the library can conflict.
3. **"`URLClassLoader.close()` or `System.gc()` definitely unloads immediately."** Class/native unloading depends on reachability, lifecycle, and JVM choices, with no guaranteed timing.
4. **"Putting only the shared interface in the parent is enough."** If **the JNI wrapper that actually calls `System.load`** still resides in each child, two native loads still occur. The parent needs to own the native bridge or provide an explicit separate-state design.
5. **"Native code can keep `JNIEnv*` across any thread or hold a local `jclass` reference forever."** `JNIEnv*` is thread-bound; JNI object/class references have specific lifecycles and require proper global/weak-global management.

APIs such as `RegisterNatives`, `--add-opens`, or copying `.so` files into multiple directories do **not automatically** bypass JNI library ownership rules. When handling runtime failures, preserve the original stack trace and classify whether the failure occurred during **native binary loading**, **symbol resolution**, or **Java class initialization**.

## 18. Practical Checklist for Plugin Systems Using JNI

- [ ] Clearly identify the **Java class declaring native methods** and that class's defining loader.
- [ ] Identify the **Java class directly calling `System.load`/`loadLibrary`**, without guessing solely by plugin ID.
- [ ] Choose a shared JNI wrapper in the parent if multiple plugins share the same native library.
- [ ] Keep shared public APIs/DTOs in the appropriate loader so runtime types are not duplicated.
- [ ] Do not accidentally bundle an extra copy of the JNI wrapper inside each plugin child under a child-first policy.
- [ ] `System.loadLibrary` uses a **logical name**; `System.load` uses an **absolute path**.
- [ ] Correct native binaries for the target JVM's OS/CPU/bitness.
- [ ] Thoroughly verify **transitive native dependencies** and JNI symbols.
- [ ] Headers are generated using `javac -h` or signatures are verified with the corresponding toolchain.
- [ ] Do not attempt to load a JNI library already owned by loader A into loader B.
- [ ] Design whether native state can be shared or requires per-plugin contexts.
- [ ] Have a restart/redeploy policy without relying on GC timing.
- [ ] Stop plugin threads/callbacks and clear TCCL/caches before retiring the old loader.
- [ ] Log the classloader/generation, native absolute path, JNI ABI, and full root cause.
- [ ] Test clean startup, two simultaneous plugins, hot redeploy, and `JNI_OnLoad` failure.
- [ ] Test broken native symbol, missing native dependency, and wrong platform binary.
- [ ] Do not run untrusted native code in the same JVM under the assumption that ClassLoader protects you.
- [ ] If using JPMS/newer JDKs, separately verify the restricted native access policy.

## 19. Self-Check Questions

**Question 1.** Two different `URLClassLoader` instances both define `plugin.NativeBridge`, and both execute `System.load("/same/path/libx.so")`. Why can the second loader throw `UnsatisfiedLinkError`?

**Answer:** Because the same JNI native library has already been associated with the first loader. The JNI specification does not allow loading the same library into two classloaders.

**Question 2.** Is `System.loadLibrary("libx.so")` proper usage?

**Answer:** Not according to the standard contract: `loadLibrary` takes a logical name without prefix/extension/path. If the logical name is `x`, call `System.loadLibrary("x")`. For an absolute path, use `System.load(...)`.

**Question 3.** The native binary exists at the exact path, yet `UnsatisfiedLinkError` still occurs. What other causes could there be?

**Answer:** Wrong OS/CPU/bitness, missing transitive native library, wrong symbols/ABI, unsupported JNI version, or duplicate ownership between loaders.

**Question 4.** A shared API is placed in the parent, but each plugin defines its own JNI wrapper. Has duplicate loading been solved?

**Answer:** No. You need to place **the JNI wrapper native owner** in an appropriate shared loader or design a different native state/lifecycle.

**Question 5.** Does `URLClassLoader.close()` guarantee that `JNI_OnUnload` is called immediately?

**Answer:** No. JNI_OnUnload may be called when the loader owning the library is collected by GC; the exact timing cannot be controlled by the Java app using close.

**Question 6.** Can you copy the same native file into multiple directories and treat them as two independent native versions?

**Answer:** There is no portable guarantee. The OS loader, dependencies, singleton native state, and JNI ownership can still cause conflicts or lifecycle bugs.

**Question 7.** When `UnsatisfiedLinkError` occurs in a static initializer, why can a subsequent call turn into `NoClassDefFoundError`?

**Answer:** Because initialization of the runtime class failed, the JVM may mark the class as erroneous; a subsequent active use will not re-run the initializer as if it were a new class.

**Question 8.** In the demo, why is `classA == classB` `false` even though both binary names are `plugin.NativeBridge`?

**Answer:** Because A and B are two different defining loaders, resulting in two different runtime types.

**Question 9.** Does a "native method not found" error necessarily mean "already loaded in another classloader"?

**Answer:** No. The native library may have been loaded successfully, yet exported the wrong JNI symbol, signature, or registration. You need to inspect which stage failed.

**Question 10.** When a native library does not support multi-instance and each plugin needs a different version, what is a stronger boundary than a classloader?

**Answer:** A separate process/container with a clear IPC contract. A classloader does not create an independent native process-global namespace.

## 20. Decision Flow

~~~text
             UnsatisfiedLinkError
                     |
                     v
       Occurs during System.load* or
         when calling native method?
                /          \
          System.load*     native invocation
                |               |
                v               v
       Library found?       JNI export/signature/
           /    \            RegisterNatives?
         No      Yes
          |       |
     Fix path,    v
     OS deps    Already loaded elsewhere?
                /                  \
              Yes                   No
               |                      |
        Check owner loader         Check ABI,
               |                  dependency, arch
               v
     Multiple plugins share lib?
           /            \
         Yes             No
          |                |
   Shared JNI wrapper    Clean up lifecycle/
      in parent           check native state
          |
          v
       Test two loaders / redeploy
          |
          v
     Do not rely on GC or
     copying files as default solution
~~~

**Conclusion:** `UnsatisfiedLinkError` across multiple classloaders is not merely "library not found." A native binary may exist, have the right JNI symbol, and have already run successfully with plugin A, yet still fail to load again into plugin B because of the **per-class-loader native-library ownership** rule. A generally sustainable solution is **a parent-owned JNI bridge**, a clear shared contract, or **process isolation** when native state/ABI cannot be shared. Combining identification of the defining loader, native path, OS dependencies, and lifecycle helps distinguish the true root cause rather than blindly modifying the classpath.

### Official References

- [Java 17 JNI Specification — Invocation API / Library and Version Management](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Java 17 JNI Specification — Design Overview / Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Java SE 17 — System.load, System.loadLibrary, System.mapLibraryName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Java SE 17 — ClassLoader.findLibrary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String))
- [Java SE 17 — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close())
- [Java SE 17 — UnsatisfiedLinkError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsatisfiedLinkError.html)
- [Java SE 17 — JNI Types and Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)

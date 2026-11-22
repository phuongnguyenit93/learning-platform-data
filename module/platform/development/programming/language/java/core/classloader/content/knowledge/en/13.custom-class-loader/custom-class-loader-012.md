# `findLibrary` and Native Library Lookup Responsibility in Custom ClassLoader

When a Java application uses JNI (*Java Native Interface*), a Java class can request loading a native library via `System.loadLibrary("codec")`. The JVM must then find the corresponding **operating system library file**, for example `codec.dll` on Windows or `libcodec.so` on Linux. However, a native library is not a regular `.class` or Java resource: it is loaded by the operating system/JVM into the process address space, with its own lifecycle and linking errors.

For a **custom class loader**, Java provides the extension point:

```java
protected String findLibrary(String libname)
```

**`findLibrary` lets the loader specify the absolute location of a native library required by classes loaded by that loader.** It does not perform the loading of the DLL/SO/DYLIB into memory, does not define Java classes, and does not automatically look up libraries inside JARs. When it returns `null`, the JVM can continue searching via `java.library.path`. When it returns a path, the JVM uses that result to attempt to load the library via the native mechanism.

This lesson belongs to the **Custom Loader** group in Java core – classloader. Objectives: properly understand the `findLibrary` invocation, distinguish `findClass`/`findResource`/`findLibrary`, choose an appropriate native loading method, build a Java 17+ loader with an override, analyze JNI errors, and safely manage libraries for plugins.

## 1. Why Must a Class Loader Care About Native Libraries?

A framework/plugin can be packaged into two parts:

- **Java classes:** bytecode in `plugin.jar` or a classes directory, for example `plugin.NativeEngine`.
- **Native library:** machine code specific to the operating system and CPU architecture, for example `libengine.so`, `engine.dll`, or `libengine.dylib`.

Java can define plugin classes via `URLClassLoader` or a custom loader. However, the `System.loadLibrary` call must locate a **compatible native binary**. If you only configure the path to the Java class files, the JVM **does not automatically know** where the native library resides.

Diagram:

```text
Host application
      |
      v
PluginLoader  ---- loadClass("plugin.NativeEngine") ---> bytecode .class
      |
      | plugin class executes System.loadLibrary("engine")
      v
JVM native-library loader
      |
      +-- asks PluginLoader.findLibrary("engine")
      |        |
      |        +-- returns absolute path ----> attempts to open DLL/SO/DYLIB
      |        |
      |        +-- returns null ------------> tries java.library.path
      |
      v
Links native library into the process
      |
      v
JNI method is registered/looked up according to JNI linking rules
```

That is why the `ClassLoader` API has two distinct responsibilities: **defining/finding Java classes** and **assisting the JVM in finding native libraries associated with classes loaded by the loader**.

## 2. The Java 17 Contract of `ClassLoader.findLibrary`

Signature:

```java
protected String findLibrary(String libname)
```

According to the Java SE 17 API:

1. **The JVM invokes this method** when it needs to locate a native library for classes that have been loaded by that loader.
2. The `libname` parameter is the **logical name of the library** requested by the `loadLibrary` call, not an absolute path.
3. A valid result when found is an **absolute path string to the native library**.
4. If the result is **`null`**, the VM searches for the library along the standard search path represented by the `java.library.path` property.
5. **The default implementation returns `null`**. Subclasses that want to manage native libraries in their own location need to override the method.
6. `findLibrary` is **`protected`**: it is not a public API for applications to call directly like `ClassLoader.loadClass`.

Important: `findLibrary` is a **path-lookup hook**, not a factory initializing a class, and also not a place where `System.loadLibrary` should be called again for `libname` itself. Doing so can create a library lookup loop. The JVM is already responsible for performing the actual loading step after receiving the path.

### Comparing Common Hooks in a Custom Loader

| Hook/API | Lookup target | Result type | Who uses it? |
| --- | --- | --- | --- |
| `findClass(String)` | Java binary name, for example `plugin.Engine` | `Class<?>` | `loadClass`/JVM during the class loading process |
| `findResource(String)` | Resource path, for example `config/default.json` | `URL` or `null` | `getResource`/`getResources` following delegation rules |
| `findLibrary(String)` | Native library logical name, for example `engine` | **Absolute file path** or `null` | JVM when handling native library loading |
| `System.mapLibraryName(String)` | Logical native library name | Platform-specific file name | Applications needing to map `engine` → OS file name |
| `System.loadLibrary(String)` | Logical native library name | `void` or error | Java code requesting the JVM to load a native library |
| `System.load(String)` | **Absolute native library path** | `void` or error | Java code that already knows the target file, not requiring a logical-name lookup hook the way `loadLibrary` does |

**Do not replace `findClass` with `findLibrary`**: the JVM does not treat a `.dll` path as a Java class. Also, `findLibrary` **is not invoked just because** code reads a `.so` using `ClassLoader.getResourceAsStream`.

## 3. Logical Name, Operating System File Name, and Absolute Path

When code writes:

```java
System.loadLibrary("engine");
```

the argument must be the library name **without** a directory path, platform prefix, or extension. The JVM processes the logical name according to platform rules. Common examples:

| Operating System | Logical name | Common file name |
| --- | --- | --- |
| Windows | `engine` | `engine.dll` |
| Linux | `engine` | `libengine.so` |
| macOS | `engine` | `libengine.dylib` or a compatible form supported by the runtime |

Do not manually concatenate `".dll"` or `"lib" + name + ".so"` for all platforms. Use the API:

```java
String nativeFileName = System.mapLibraryName("engine");
System.out.println(nativeFileName);
```

This is an **illustrative snippet meant to be placed inside a method**; the output depends on the OS/JVM, so there is no single fixed stdout shared across all machines.

Example of constructing the path:

```java
Path nativeDir = Path.of("plugins", "engine", "native");
Path fullPath = nativeDir
        .toAbsolutePath()
        .resolve(System.mapLibraryName("engine"))
        .normalize();

System.out.println(fullPath.isAbsolute());
```

This is an **illustrative snippet** (requires `import java.nio.file.Path;`). On a normal filesystem, the last line prints `true`. Merely constructing a path string **does not prove** that the file exists or can be loaded.

Inside `findLibrary`, you typically need to check whether the file actually exists as a regular file, whether the path escapes the allowed root, and whether the OS/CPU architecture matches. If there is no corresponding binary, **return `null` if the policy allows fallback**; or when you want to fail closed, you can return the path to the expected artifact and let the JVM report an error, provided this is done intentionally. Do not return a relative string such as `"native/libengine.so"`.

## 4. Execution Flow and Which Loader Is Queried?

The subtle part is the **loader of the class that performs the native loading call**.

Suppose:

```text
                  System/Application loader
                       |  host.NativeHelper
                       |
                       v parent
                 PluginClassLoader
                       |  plugin.NativeEngine
                       |
                       +-- native/engine.dll, native/libengine.so ...
```

If **`plugin.NativeEngine`** (defined by the plugin loader) calls `System.loadLibrary("engine")` from a static initializer, the native lookup is associated with the loader of that calling class; the JVM can invoke **`PluginClassLoader.findLibrary("engine")`**.

However, if a method **`host.NativeHelper.loadIt()`** defined by the system loader is the one directly executing `System.loadLibrary("engine")`, the runtime uses the context of the helper caller class and **does not automatically infer the plugin loader** from a plugin object higher up on the stack. Therefore, the `findLibrary` override in the plugin loader may **not be called** when a host helper performs the native load.

This distinction often leads to the question “why did I override `findLibrary` but see no log?”. Check **which defining loader loaded the class containing the `System.loadLibrary` statement**.

Also, do not confuse this with the **thread context class loader (TCCL)**: `Thread.currentThread().getContextClassLoader()` is actively used by some SPI frameworks, but the JVM does not **by default** switch the native library lookup loader to the TCCL for every `System.loadLibrary`. If the application wants to use the plugin context, design the load method inside a class defined by the plugin loader, or use a `System.load(absolutePath)` strategy with clear ownership.

### Requested Loader and Defining Loader

A class `plugin.Entry` requested via `customLoader.loadClass(...)` is not necessarily **defined by** the custom loader if the parent already has a class with the same name. Native calls from `Entry` will operate according to the class's **actual defining loader**. Always verify:

```java
Class<?> entry = customLoader.loadClass("plugin.Entry");
System.out.println(entry.getClassLoader() == customLoader);
```

This is an **illustrative snippet**, assuming `customLoader` has already been created and the method handles `ClassNotFoundException`. If it prints `false`, you must investigate parent delegation or duplicate classpath entries before concluding that `findLibrary` on the custom loader takes effect.

## 5. Runnable Java 17+ Example Without Installing a Native Compiler

This example intentionally **does not provide a valid native library**. The goal is to prove that the JVM actually invokes the custom loader's `findLibrary`, that the selected path is an absolute path, and that the error for loading a non-existent file is reported in the expected form. We will **catch the anticipated error**, so the overall program exits normally.

### 5.1 Structure

```text
native-demo/
├── src/
│   └── plugin/
│       └── Entry.java
├── NativeLookupDemo.java
├── plugin-classes/        (plugin output)
└── host-classes/          (host output)
```

Create the two output directories before compiling. Run all commands from `native-demo`. Do **not** include `plugin-classes` on the host classpath.

### 5.2 The Plugin Class Where `System.loadLibrary` Is Called

File `src/plugin/Entry.java`:

```java
package plugin;

public final class Entry {
    public static void attemptLoad() {
        System.loadLibrary("step4_missing_native_demo_159");
    }
}
```

The long, distinctive library name here is intentionally chosen so it **does not collide** with any real library on the machine. There is no JNI method to execute: the purpose of this test is solely **native lookup**.

### 5.3 Custom Loader Overriding `findLibrary`

File `NativeLookupDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.lang.reflect.InvocationTargetException;

public class NativeLookupDemo {
    static class PluginLoader extends URLClassLoader {
        private final Path nativeDirectory;

        PluginLoader(URL[] urls, ClassLoader parent, Path nativeDirectory) {
            super(urls, parent);
            this.nativeDirectory = nativeDirectory;
        }

        @Override
        protected String findLibrary(String name) {
            System.out.println("findLibrary: " + name);

            if (!name.equals("step4_missing_native_demo_159")) {
                return null;
            }

            return nativeDirectory
                    .resolve(System.mapLibraryName(name))
                    .toAbsolutePath()
                    .toString();
        }
    }

    public static void main(String[] args) throws Exception {
        Path classes = Path.of("plugin-classes");
        Path nativeDir = Path.of("intentionally-empty-native-dir");

        try (PluginLoader loader = new PluginLoader(
                new URL[] {classes.toUri().toURL()},
                ClassLoader.getPlatformClassLoader(),
                nativeDir)) {

            Class<?> entry = loader.loadClass("plugin.Entry");
            System.out.println("custom defining loader: "
                    + (entry.getClassLoader() == loader));

            try {
                entry.getMethod("attemptLoad").invoke(null);
                System.out.println("unexpected success");
            } catch (InvocationTargetException e) {
                System.out.println("native load error: "
                        + e.getCause().getClass().getSimpleName());
            }
        }
    }
}
```

Notes:

- `PluginLoader` extends `URLClassLoader` to locate `plugin.Entry.class` from `plugin-classes`.
- Parent = `ClassLoader.getPlatformClassLoader()`, which in this example does not contain `plugin.Entry`, ensuring that the plugin class is **actually defined** by the custom loader.
- `findLibrary` receives the logical name `step4_missing_native_demo_159` and returns an absolute path to a **non-existent** native file. Do not call `System.loadLibrary` again inside the override.
- `getMethod(...).invoke(null)` invokes a **static method defined by the plugin class**. Because the `System.loadLibrary` call is inside `plugin.Entry`, the JVM selects the plugin loader's context.
- Reflective method invocation wraps errors thrown by the target method in `InvocationTargetException`; the test only prints the class name of `getCause()`. It does not treat the simulated native error as a success.

### 5.4 Compiling and Running

```bash
javac --release 17 -d plugin-classes src/plugin/Entry.java
javac --release 17 -d host-classes NativeLookupDemo.java
java -cp host-classes NativeLookupDemo
```

The application stdout result verified when compiling with `javac --release 17` and running:

```text
custom defining loader: true
findLibrary: step4_missing_native_demo_159
native load error: UnsatisfiedLinkError
```

Newer JDKs may **additionally print a native access warning to stderr** when calling `System.loadLibrary`, while the three lines of application stdout above remain valid. The native access permission warning and `UnsatisfiedLinkError` are **two separate issues**; see the Java 17+/JPMS section at the end of this lesson.

**Do not conclude that the override succeeded merely because `UnsatisfiedLinkError` appears:** you must observe the `findLibrary: ...` line and confirm that the plugin class is truly defined by the custom loader. If the loader is never queried, the error might come from `java.library.path` or another helper loader.

## 6. Why Is Returning `null` Meaningful?

The default implementation of `ClassLoader.findLibrary` returns `null`. The JavaDoc specifies that when this method returns `null`, the VM searches for the library along the path described by the `java.library.path` property.

A custom implementation often wants to prioritize a separate native directory while keeping a fallback:

```java
@Override
protected String findLibrary(String name) {
    Path file = nativeDir.resolve(System.mapLibraryName(name));

    if (java.nio.file.Files.isRegularFile(file)) {
        return file.toAbsolutePath().toString();
    }
    return null; // JVM uses the standard lookup mechanism.
}
```

This is an **illustrative code snippet inside a `ClassLoader` subclass**, assuming `nativeDir` is available. You should normalize/validate the path and verify trusted library sources before using it in a real application.

Three outcomes to distinguish:

| `findLibrary` returns | Interpretation | Possible outcome |
| --- | --- | --- |
| Existing absolute path, matching architecture, and complete dependencies | The JVM attempts to load the target library | Success or another linking/native error |
| Non-existent absolute path, wrong bitness, or corrupted | The JVM already has an explicit candidate but cannot load it | `UnsatisfiedLinkError`; do not assume it will keep searching all directories |
| `null` | The loader does not provide a custom path | The JVM performs the default lookup according to `java.library.path` rules |

**Do not use returning `null` as a mechanism to signal “skip native support completely”.** It only means the custom loader does not propose a path; the JVM may still find and load another version from the system library path. If a plugin requires a **specific, mandatory** native version, the design must not allow a fallback that accidentally picks up a different file with the same name from the environment.

### How `java.library.path` Differs from `java.class.path`

| Property / Option | Role |
| --- | --- |
| `java.class.path`, `-cp` | Java classes and resources of the application classpath |
| `java.library.path`, typically configured at startup with `-Djava.library.path=...` | Search path for native libraries when the native lookup mechanism uses it |
| `System.mapLibraryName` | OS-specific native file name for a logical name |
| `PATH` on Windows, `LD_LIBRARY_PATH` on Linux, `DYLD_*` on macOS | Environment variables belonging to the operating system's shared libraries/dependencies lookup mechanism; behavior depends on the platform/launcher and protection policies |
| `java.home` | Path to the Java runtime installation, not the plugin native directory |

Example of a native search path at startup:

```bash
java -Djava.library.path=./native -cp host-classes NativeLookupDemo
```

This command only illustrates the **syntax for configuring the native search path**. Because the `NativeLookupDemo` test actively returns an absolute path to a non-existent dummy file, you should not expect `-Djava.library.path` to rescue that overridden load attempt.

In a Java 17 application, `java.library.path` should be decided from **startup configuration**; do not write code that changes `System.setProperty("java.library.path", ...)` at runtime and assume the JVM will immediately use the new path. The JVM may cache the native-library search configuration, and behavior depends on the runtime.

## 7. How Does `System.loadLibrary` Differ from `System.load`?

The two APIs have different responsibilities:

```java
System.loadLibrary("engine");
```

- The input is a **logical name** without path, prefix, or extension.
- The library is searched using the appropriate native-library lookup mechanism, including the `findLibrary` hook of the corresponding loader when requested by the JVM.
- Easy to write portably if the library is placed in the proper search path.

```java
System.load("/opt/myapp/native/libengine.so");
```

- The input is an **absolute path** to the library (the example above is for Linux).
- Does not require a logical name for `findLibrary` to determine the location.
- Suitable when the application has already verified the exact file and wants to specify a particular native binary; the path is not portable if hard-coded.

The above is an **API illustration** and cannot run successfully if the native file does not exist and has not been built appropriately. Do not call `System.load("engine")` expecting Java to automatically locate the file from `java.library.path` like `loadLibrary`; if the path is not absolute, the API may throw `UnsatisfiedLinkError`.

### Why Not Call `System.load` Directly Inside `findLibrary`?

`findLibrary` is called by the JVM **while** it is attempting to load a native library. It must only return a **path string**. If you also call `System.load` or `System.loadLibrary` inside the hook, you trigger another load operation while the current lookup has not yet finished. This increases the risk of reentrancy, duplicate load errors, deadlocks, or hard-to-diagnose exceptions.

Proper design:

```text
Java class requests System.loadLibrary("engine")
                    |
                    v
JVM -> customLoader.findLibrary("engine")
                    |
                    v
customLoader returns "/trusted/native/.../libengine.so"
                    |
                    v
JVM performs loading and JNI linking
```

## 8. How Does JNI Relate to Class Loader Identity?

Native code **does not run inside the Java bytecode sandbox**. JNI functions use pointers/handles to the JVM and bind symbol names or register native methods. Therefore, JNI must preserve boundaries between class loaders.

The JNI Specification states: **each class loader manages the set of native libraries associated with it**; the same JNI native library **cannot be loaded into more than one class loader simultaneously**. If you attempt to do so, `System.loadLibrary` may throw `UnsatisfiedLinkError`.

Example scenario:

```text
PluginLoader A ----loadLibrary("engine")----> /opt/plugin/native/libengine.so
PluginLoader B ----loadLibrary("engine")----> /opt/plugin/native/libengine.so
                                                   |
                                                   v
                                  Possible error: library already loaded
                                  in another classloader
```

This is an **illustrative scenario**, not a fixed exact output. The specification rule is not to use the same JNI library concurrently across two different loader namespaces. In practice, the detailed message of `UnsatisfiedLinkError` and path/canonicalization behavior depend on the JVM/OS.

This strongly affects plugin reloading:

- New Java classes can be defined in a new loader, but the JNI library at the old path may still be bound to the old loader.
- Calling `URLClassLoader.close()` only closes the classpath URL sources; **it is not a JNI unload command**.
- For a native library to be unloaded, the old loader and its associated classes/objects must become eligible for GC collection according to JVM rules.
- JNI `JNI_OnUnload` is a lifecycle hook that may be called by the JVM when the loader containing the native library is garbage-collected; do not treat it as a callback that occurs immediately upon calling `close()`.
- When native state still holds global references, threads, or OS resources, shutdown must have an explicit contract independent of JVM GC.

**Do not resolve JNI class loader conflicts by arbitrarily copying a DLL/SO into dozens of new paths** if the native library does not support multiple instances within the same process. That approach can lead to state duplication, crashes, and data corruption. Check whether the native library supports multi-loader/multi-instance usage; if not, consider a stable shared JNI layer owned by a shared loader.

## 9. `UnsatisfiedLinkError` Does Not Have Only a Single Cause

| Issue Category | Example Cause | How to Check |
| --- | --- | --- |
| **Library not found** | `findLibrary` returns `null`, `java.library.path` does not contain the file | Print logical name, mapped filename, startup native path |
| **Invalid path returned** | `findLibrary` returns a relative path or a non-existent absolute path | `Path.isAbsolute()`, `Files.isRegularFile`, normalized/canonical path |
| **Architecture mismatch** | Running a 64-bit JVM while only a 32-bit native DLL/SO is available | Verify `os.arch`, file architecture, and ABI |
| **Missing native dependency** | Main `engine.dll` exists, but a C/C++ library it depends on is absent | OS loader tools, appropriate dependency inspection commands |
| **Wrong JNI symbol/signature** | The library loads successfully, but calling the `native` method cannot find a matching entry | `javac -h`, JNI naming, or `RegisterNatives` |
| **Library already bound to another loader** | Two custom loaders attempt to load the same JNI library | Identify the caller's defining loader and plugin lifecycle |
| **Native access restrictions** | Newer runtimes require granting native access permission to the caller module | Check JDK version, flags, and native access warnings/errors |
| **Statically linked library vs. dynamic** | The runtime integrates the native library and defines `JNI_OnLoad_<L>` | Refer to the JNI Invocation API; do not infer from a physical file not existing |
| **Blocked by OS permissions** | The file is not permitted to load, or is blocked by quarantine/policy/antivirus | Check OS permissions and security logs |

`UnsatisfiedLinkError` is a subclass of `LinkageError`. **Do not catch and swallow it silently** in production systems: log the library name, expected path, caller defining loader, OS/architecture, and root cause. If native setup is called inside a `static` initializer, the failure can leave the class in an erroneous state; subsequent uses may surface `NoClassDefFoundError`.

### A Library Present on Disk Can Still Fail

Suppose `findLibrary("engine")` returns `C:\app\native\engine.dll`. That only resolves *the location of the primary library*. The Windows loader may still fail to locate a secondary dependency DLL, or the library may not be a valid DLL for the current CPU architecture.

Similarly, a `libengine.so` that exists on Linux can still fail due to a missing compatible `libstdc++.so`, wrong ELF class, missing symbols, or dynamic linker configuration. **Do not merely see “file exists” and conclude that `findLibrary` has completed every end-to-end responsibility.**

## 10. Designing a Safe `findLibrary` for Plugins

A plugin loader can have its own native root path:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.net.URL;
import java.net.URLClassLoader;

public final class NativePluginLoader extends URLClassLoader {
    private final Path nativeRoot;

    public NativePluginLoader(
            URL[] classUrls, ClassLoader parent, Path nativeRoot) {
        super(classUrls, parent);
        this.nativeRoot = nativeRoot.toAbsolutePath().normalize();
    }

    @Override
    protected String findLibrary(String logicalName) {
        // Only allow known libraries of the plugin.
        if (!logicalName.equals("engine")
                && !logicalName.equals("codec")) {
            return null;
        }

        String fileName = System.mapLibraryName(logicalName);
        Path candidate = nativeRoot.resolve(fileName).normalize();

        if (!candidate.startsWith(nativeRoot)) {
            return null;
        }
        if (!Files.isRegularFile(candidate)) {
            return null;
        }
        return candidate.toString();
    }
}
```

This is a **standalone Java class that compiles with JDK 17+**; actual native loading cannot yet be tested unless the `engine`/`codec` native files are provided. The allowlist, path normalization, and regular-file check help reduce misplaced-file mistakes or path traversal. However, in untrusted environments, **they are not sufficient to prevent symlink races**, file replacement after validation, or malicious binaries. You must verify the artifact source, filesystem permissions, and integrity before the JVM loads the library.

**Key design responsibilities:**

1. **Establish clear ownership:** which plugin is entitled to own/claim which native library? Should a shared JNI library be loaded once by a common loader?
2. **Identify platform artifacts:** compatible OS, CPU architecture, ABI, and runtime C/C++ dependencies.
3. **Map names portably:** use `System.mapLibraryName` instead of hard-coding extensions.
4. **Return only absolute paths:** `findLibrary` follows the API contract. Use a canonical/real path once the artifact exists to avoid confusion across equivalent locations.
5. **Fail closed when required:** if falling back to a system library with the same name is disallowed, an explicit policy is needed; `return null` is not fail-closed.
6. **Do not hold heavy locks inside the hook:** native library loading can happen during initialization and interact asynchronously; avoid recursive loads/deadlocks.
7. **Log appropriately:** record the logical name and mapping without leaking sensitive paths into public logs.
8. **Manage lifecycle:** do not unload/reload prematurely while native methods, global references, or running threads still remain.

If native libraries are **packaged inside a JAR** under `native/windows-x64/engine.dll` or `native/linux-x64/libengine.so`, the JVM cannot simply accept a `jar:file:...!/...` URL via `findLibrary` and treat it as a native file on disk. Typically, the plugin manager must **extract it to a secure directory**, verify its name/architecture/integrity/access permissions, and then have `findLibrary` return the absolute path. File cleanup must be managed after no library/OS handles remain in use; some operating systems do not allow deleting or replacing a file that is currently loaded.

## 11. Where Do `findLibrary` and Native Loading Methods Fit in the Architecture?

A maintainable design:

```text
Application host
  |
  +-- Shared Java API (interface/DTO) in parent loader
  |
  +-- PluginManager
        |
        +-- verifies platform + signatures/native artifacts
        +-- prepares trusted native directory
        +-- creates PluginClassLoader(class URLs, parent, native directory)
        +-- loads plugin.Entry defined by PluginClassLoader
        |
        v
     plugin.Entry (plugin's Java code)
        |
        +-- static { System.loadLibrary("engine"); }
        |             |
        |             v
        |        PluginClassLoader.findLibrary("engine")
        |             |
        |             v
        |        return absolute path
        |             |
        |             v
        |        JVM/OS native loader
        |
        +-- native method / JNI entry
```

**Intent:** the plugin's Java logic should have one clear point responsible for calling `System.loadLibrary`. The plugin manager manages artifacts and loaders, while the `findLibrary` hook only maps name → valid file. Additional verification layers for signatures, versioning, and platform compatibility can be separated out.

If a shared Java host class contains the `System.loadLibrary` call, consider structuring the JNI bridge in the corresponding **shared loader**, or using an explicit absolute load with an ownership policy. Do not arbitrarily change the TCCL hoping to make the native loader pick the plugin's path: that is not the contract of `findLibrary`.

## 12. Why Does Adding `-Djava.library.path` Still Fail to Fix the Error?

An illustrative sequence:

```text
1. plugin.Entry calls System.loadLibrary("engine")
2. PluginClassLoader.findLibrary("engine") returns C:\plugins\engine-v2.dll
3. That file does not exist or has the wrong architecture
4. UnsatisfiedLinkError occurs
5. Change -Djava.library.path to another directory
6. It can still fail because findLibrary continues returning the old absolute path
```

If `findLibrary` returns a specific candidate, the debugger needs to inspect that exact path. Only if it returns `null` should you closely examine `java.library.path` and the default native lookup rules.

Another misconception: users only add the DLL directory to the **Java classpath `-cp`**. That enables the `ClassLoader` to locate **Java classes/resources**, **without guaranteeing** that the JVM native linker will locate DLL/SO files through the classpath itself. The native library path is a separate mechanism.

### When Running in a Container Environment

Inside a container/Docker:

- The JNI file must be copied/mounted into the right container filesystem path, not a host OS path.
- A Linux container requires libraries built for the **Linux ABI/CPU**; a Windows DLL will not work merely because the logical name is the same.
- The dynamic linker also needs the native dependencies of the primary file.
- The native file might be a resource from an image layer without write or execute permissions; consider an appropriate extraction directory.
- If using a custom loader, `findLibrary` should return an existing and verified path **inside the container**.

## 13. Managing Native Libraries When Reloading/Unloading a Custom Loader

The native lifecycle differs from the lifecycle of Java classes:

| Event | Outcome |
| --- | --- |
| `ClassLoader.loadClass` | Finds/defines the Java class; does not automatically load native libraries unless the class executes an operation that requests one |
| Successful `System.loadLibrary` | The JVM records the native library as loaded for the appropriate loader context |
| `URLClassLoader.close()` | Closes the classpath/JAR sources owned by the URL loader; **this is not a JNI unload API** |
| Loader becomes unreachable and is collected by GC | The JVM **may** unload classes/native libraries attached to the loader according to runtime rules |
| `JNI_OnUnload` if provided | Hook that may be invoked when the runtime unloads the native lib; not a mandatory callback immediately after close |
| Creating a new loader for a new plugin version | Creates a new Java namespace, yet still requires handling conflicts with a JNI native library bound to the old loader |

Safe plugin reloading typically requires:

1. Stop accepting new requests and wait for all in-flight Java/native tasks to complete.
2. Disconnect callbacks, shut down native services according to the native library's API, and release JNI global refs if any.
3. Unregister listeners, caches, thread locals, and context loader references still holding onto the plugin.
4. Close the loader's URL sources when loading new classes/resources is no longer needed.
5. Drop strong references to the old classes/loader; accept that GC/class unloading has no guaranteed timing.
6. Open the new version only after resolving the reuse/exclusivity rules of the native lib; if hard isolation is required, a **separate process** may be necessary.

Do not do this:

```java
oldLoader.close();
System.gc();          // Does not guarantee unloading the native lib.
newLoader.loadClass("plugin.Entry"); // Does not guarantee being able to reload the same JNI.
```

The snippet above is **illustrative code** and does not compile standalone without declaring `oldLoader` and `newLoader`. `System.gc()` is a hint, not a JNI unload operation. An `already loaded in another classloader` conflict requires proper ownership/lifecycle design, not trying to force a speculative GC.

## 14. Testing `findLibrary` Without Breaking the Machine Environment

There are three testing levels that should be distinguished:

**Level A – unit test for path mapping only.** Give the loader a temporary `nativeRoot` and a known logical name; verify that the hook returns an absolute path, does not escape the root, and returns `null` for names outside the allowlist. Because the method is `protected`, the test can reside in a subclass in the same package/test helper to call it via a test-only wrapper.

**Level B – integration test with an intentionally missing library.** For example, `NativeLookupDemo` in Section 5 confirms that the JVM **actually goes through** `findLibrary` and reports `UnsatisfiedLinkError` when the file is absent. This tests JVM lookup, not real JNI symbols.

**Level C – integration test with a real JNI library.** Compile the Java native declaration and use `javac -h` to generate a C header; build a compatible DLL/SO/DYLIB and place it in the mapped directory; test the native method end-to-end, checking ABI, dependencies, and unload/reload semantics. These should be run separately per OS/architecture in CI, without predicting exact stdout when native code and platforms differ.

### Example of Declaring a Native Method

```java
package plugin;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    public static native int add(int a, int b);
}
```

This is a **compilable Java class**, though calling `NativeMath.add(...)` will require an actual native library with a JNI implementation matching the name/signature. You can generate the header:

```bash
javac --release 17 -h headers -d plugin-classes src/plugin/NativeMath.java
```

If executed, you must create the exact `src/plugin/NativeMath.java` file, output directory, and native implementation before using the method; this snippet illustrates the mechanism and **does not claim to have tested a real C library**.

Using `javac -h` avoids guessing JNI mangled names for overloaded methods. When module/native access restrictions of future JDKs apply, you will also need to launch the JVM with native access permissions according to that JDK version's documentation.

## 15. Misconceptions to Avoid

| Misconception | Correct Understanding |
| --- | --- |
| “`findLibrary` loads and links the DLL itself.” | It **returns a path**; the JVM/OS performs native loading and linking. |
| “Every `ClassLoader` subclass must override `findLibrary`.” | No; by default it returns `null`, and the JVM uses the standard native lookup path. |
| “`findLibrary` must return the `URL` of a resource inside a JAR.” | The contract returns an **absolute file path string** to the native library. |
| “`System.loadLibrary("engine.dll")` is portable.” | `loadLibrary` takes a logical name such as `engine`, without an extension or path. |
| “`System.load` and `System.loadLibrary` are completely identical.” | `load` takes an **absolute path**; `loadLibrary` takes a **logical name**. |
| “If classpath `-cp` contains a JAR, the JVM will automatically find the DLL inside that JAR.” | No. Native libraries require their own file/path/loading mechanism. |
| “Changing the TCCL makes the JVM use the plugin's `findLibrary`.” | Not by default; you must check the defining loader of the class performing native loading. |
| “`findLibrary` returning `null` means an immediate failure.” | It allows the JVM to use lookup via `java.library.path`. |
| “If the native file exists, loading will succeed.” | ABI, dependencies, symbol exports, OS permissions, or loader duplication can still fail. |
| “Two class loaders can load the same JNI library independently.” | The JNI spec restricts loading the same library into multiple class loaders; this can cause `UnsatisfiedLinkError`. |
| “`URLClassLoader.close()` releases the native lib immediately.” | Closing classpath sources differs from JNI/native unloading; GC/lifecycle is what matters. |
| “`System.gc()` guarantees unloading JNI and reloading a new version.” | There is no such guarantee. |

## 16. Self-Check with Answers

**1.** What should `findLibrary("codec")` return when the library is located at `C:\app\native\codec.dll` on Windows?

**Answer:** The **absolute path** string to that file if it is a valid candidate. Do not return the logical name `codec` or a relative path `native/codec.dll`.

**2.** If `findLibrary` returns `null`, does the JVM immediately throw `UnsatisfiedLinkError`?

**Answer:** No. According to the Java 17 API, the JVM searches for the library via `java.library.path`; only if the library cannot be found/loaded can the load fail.

**3.** What does `System.mapLibraryName("engine")` return?

**Answer:** A **platform-dependent file name**; for example, on Windows it is typically `engine.dll`, and on Linux `libengine.so`. Do not hard-code a single output for all OSes.

**4.** Why does the `findLibrary` override in the plugin loader not run if `host.NativeHelper` calls `System.loadLibrary`?

**Answer:** The loader used during native lookup is tied to the caller class directly requesting the load. If `NativeHelper` is defined by the system loader, that is not the plugin loader; the TCCL does not automatically alter that selection.

**5.** Why can a native library that was already found still throw `UnsatisfiedLinkError`?

**Answer:** It may have the wrong CPU bitness/ABI, a missing native dependency, a mismatched JNI symbol, already be loaded by another loader, or be restricted by the OS/JVM. Read the message and inspect the specific cause.

**6.** A plugin wants to load JNI from a JAR resource. Can `findLibrary` return `"jar:file:/...!/libengine.so"`?

**Answer:** That violates the absolute native file path contract. Typically, you must extract it to a real file in a trusted directory, verify it, and return the absolute path.

**7.** Does `URLClassLoader.close()` immediately resolve the library already loaded in another classloader error?

**Answer:** No. It closes the classpath/JAR sources managed by the loader, which is not equivalent to native library unloading. An old class loader that is still alive or not yet collected by GC can still remain bound to the native library.

**8.** What is the purpose of `System.load("/abs/path/libengine.so")`?

**Answer:** It specifies the native file by an **absolute pathname**, without needing `findLibrary` to map from a logical name like `System.loadLibrary`. The actual path must still match the OS/ABI and be loadable.

**9.** If `findLibrary` returns the path to the right file, but inside an untrusted plugin directory, is that safe?

**Answer:** No. Native code has direct access to affect the process. You must check the artifact source, write/replace permissions, symlinks/path traversal, signatures/hashes, and isolation if the code is untrusted.

**10.** When should you consider placing the JNI bridge in a shared loader instead of having each plugin load it independently?

**Answer:** When the native library does not support multiple class-loader instances or needs to share native state within a single JVM. A shared bridge needs a stable API contract, clear ownership, and proper handling of concurrent access and the native lifecycle.

## 17. Pre-Operation Checklist for a Custom Loader with JNI

1. **Right caller:** Which defining loader defined the class containing the `System.loadLibrary` call?
2. **Right hook:** Is `findLibrary` overridden on that loader and returning an absolute path/`null` according to the contract?
3. **Right mapping:** Do the logical name, `System.mapLibraryName`, and OS-specific file name match?
4. **Secure root:** Is the directory normalized/canonicalized, is the artifact from a trusted source, and can it not be replaced after verification?
5. **Compatible artifact:** Have OS, architecture, ABI, native dependencies, and JNI exports been checked?
6. **Module/runtime:** Do native access permissions and runtime policies permit JNI for the running JDK?
7. **No loader duplication:** Is the JNI library already loaded by another defining loader?
8. **Error reporting:** Do you log the error type and cause instead of hiding `UnsatisfiedLinkError` behind a generic “class not found” message?
9. **Lifecycle:** Does the plugin stop tasks/native resources, release references, and close the URL loader at the appropriate time?
10. **Reloading:** Do you need a new loader/process or a shared JNI bridge to manage native library versions?
11. **Tests:** Unit mapping + missing-file integration + real native tests per platform are present in CI.
12. **Clear fallback:** Is `return null` allowed to lead to a system library with the same name but a different version?

## Conclusion

**`ClassLoader.findLibrary` is responsible for answering: “where is the absolute path of the native library with this logical name for classes defined by this loader?”**. The JVM is responsible for **loading, linking, and managing the native library**. The hook returns an **absolute path** when a valid file is known, returns **`null`** when delegating to the default lookup mechanism, and does not replace `findClass`, `findResource`, `System.load`, or `System.loadLibrary`.

In a plugin application, success is not just “finding the file”: you also need the right caller loader, to avoid JNI duplication across loaders, the right OS/ABI, proper management of native files/threads/global refs, and a reload/shutdown policy. This is the boundary between the **Java class loader** and the **native linker/OS** that anyone building a custom loader must master.

**Official Documentation (Java SE 17 / JNI):**

- [`ClassLoader.findLibrary` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String)).
- [`System.load`, `System.loadLibrary`, and `System.mapLibraryName` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html).
- [JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html).
- [JNI Specification — Invocation API, Library and Version Management](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html).

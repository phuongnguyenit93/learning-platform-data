# Limitations of Changing the Library Search Path After JVM Startup

When integrating Java with native libraries via JNI, a confusing situation is: the application starts running, loads a new configuration pointing to a directory containing `.so`/`.dll`/`.dylib`, calls `System.setProperty("java.library.path", newPath)`, reads it back and sees the new value, yet `System.loadLibrary("foo")` still reports that the library cannot be found.

**Cause:** `java.library.path` is the search path configuration for native libraries by name; changing the *system property string* after JVM startup does not mean changing the search path already used by the JVM/class loader. On modern OpenJDK/HotSpot builds, this search path is cached during initialization. Java does not provide a standard API to force the JVM to reload that list at runtime.

**How to choose correctly:** if you control the startup command, pass `-Djava.library.path=...` before the class/JAR name; if you must load a native file at a path determined after startup, use `System.load(absolutePath)` and manage dependent libraries using the operating system's mechanism. The two approaches have different limitations; both require a native file with the right architecture, ABI, and access permissions.

## 1. Paths That Are Easily Confused

| Component | What is it used to find? | Example | When is it set? |
| --- | --- | --- | --- |
| Java `-cp` / `--class-path` | Java classes and JARs on the class path | `java -cp app.jar com.example.Main` | At program startup |
| `java.library.path` | Directories used by Java's native library loading mechanism for `loadLibrary` | `-Djava.library.path=/opt/app/native` | Should be configured before JVM startup |
| `System.loadLibrary("foo")` | **Logical name** of the native library, not the file name/path | `"foo"` → usually `libfoo.so` on Linux, `foo.dll` on Windows | At call time, but uses the existing search configuration/mechanism |
| `System.load("/opt/app/native/libfoo.so")` | **Specific native file** by absolute path | `/opt/app/native/libfoo.so` | Can be called after the JVM is running, if the file is valid |
| OS dynamic loader search path | Dependent libraries required by the native binary, and native lookups handled by the OS | Linux `LD_LIBRARY_PATH`, ELF `RPATH/RUNPATH`; Windows DLL search; macOS `@rpath` | According to loader rules and process environment, not a Java system property |

`java.library.path` is **different** from `java.class.path`. Placing `libfoo.so` next to `app.jar` does not automatically make `System.loadLibrary("foo")` find the file. Similarly, calling `System.load` pointing to the main file does not automatically guarantee that all `.so`/`.dll` files it depends on will be found.

The native file name is platform-dependent; `System.mapLibraryName("foo")` returns how the name is mapped by the current JVM. Do not manually concatenate `"lib" + name + ".so"` and use it for all operating systems.

## 2. Why `System.setProperty` After Startup Does Not Work as Expected

Suppose the Java startup process proceeds in this order:

```text
Shell / service / container
    │
    ├── Set environment and -D JVM arguments
    ▼
JVM initializes
    │
    ├── Reads initial system properties
    ├── OpenJDK caches/fixes some internal configuration values
    │   (including the native library search path)
    ▼
main(...) starts
    │
    ├── System.setProperty("java.library.path", "/new/native")
    │   └── Changes the value seen by System.getProperty(...)
    │
    └── System.loadLibrary("foo")
        └── Does not necessarily re-read the newly changed property;
            the search path already established at startup is still used
```

In OpenJDK, the internal class `jdk.internal.util.StaticProperty` explicitly notes that values cached from initialization will not change with `System.setProperty`; the current source code has the field `JAVA_LIBRARY_PATH` and the method `javaLibraryPath()`. This is an **OpenJDK implementation detail**, not an application interface permitted to be called directly. The `java.lang.System` API documentation itself also warns that changing standard system properties after initialization may not have the intended effect because values may be cached.

Common wrong example:

```java
String newDirectory = "/opt/new-native";
System.setProperty("java.library.path", newDirectory);

System.out.println(System.getProperty("java.library.path"));
// Prints /opt/new-native, but does not prove the loader changed where it searches.

System.loadLibrary("foo");
// On common OpenJDK/HotSpot, you CANNOT rely on this call
// to start searching in /opt/new-native.
```

This is an **illustrative snippet**, not a standalone program. Two states must be distinguished:

1. **The property value read via the Java API:** may have changed; `getProperty` reflects the newly assigned value.
2. **The actual state of the native loader:** may have been established earlier and does not change with the property string.

There is no promise in Java SE that “reassigning `java.library.path` will make the next `loadLibrary` call use the new directory.” Therefore, do not use this approach for hot reload logic, for native plugins installed after startup, or as a mechanism to switch the version of a running library.

### What if `loadLibrary` has never been called before?

Do not rely on the assumption that “the first call to `loadLibrary` reads the property, so it can be set right before the first call.” The JDK may have already initialized and retained the search path during the bootstrap phase. The exact timing is an implementation detail; the library mechanism has no standard contract for updating `java.library.path` mid-execution.

Similarly, `System.setProperties(...)`, `System.clearProperty("java.library.path")`, or mutating `System.getProperties()` is not an API to refresh the native loader.

## 3. Choosing `loadLibrary` or `load`?

### `System.loadLibrary(String libname)`

- The argument is a **logical name**, for example `System.loadLibrary("pathlesson")`.
- Do not pass `libpathlesson.so`, `pathlesson.dll`, a directory, or a path; the API does not accept OS-dependent prefixes/suffixes.
- The JVM mechanism applies name mapping and searches for the library according to the class loader/platform configuration. A custom `ClassLoader` can override `findLibrary(String)` to return an **absolute path**; otherwise, Java uses the native search path from `java.library.path`.
- Suitable for applications where the library location is fixed and properly configured **before the JVM runs**.

Example of configuring from the command line:

```bash
java -Djava.library.path=/opt/myapp/native -cp app.jar com.example.Main
```

The command above is valid on Unix systems when the directory exists. The JVM argument `-D...` must be placed **before** the main class name or `-jar`; if placed after the class name, it usually becomes an argument to `main`. For multiple paths, use the OS-appropriate `File.pathSeparator` (`:` on common Unix, `;` on Windows). Avoid forcing a Unix path onto Windows or vice versa.

### `System.load(String filename)`

- The argument is the **absolute path to the native file**, including the file name and platform-appropriate extension; `System.load` does not accept just a logical name.
- The file can be determined at runtime, for example after reading a configuration directory or extracting a trusted native artifact to disk.
- Loading still must pass architecture checks, access permissions, dependent libraries, native symbols, and class loader rules. An absolute path only solves **identifying the main file**.
- Changing `java.library.path` is not needed for `System.load`.

Example:

```java
import java.nio.file.Path;

Path library = Path.of("/opt/myapp/native/libfoo.so")
        .toAbsolutePath()
        .normalize();

System.load(library.toString());
```

This is an illustrative snippet **for Linux only** with an actually existing file; do not automatically apply the `.so` extension on Windows/macOS. `Path.toAbsolutePath()` is useful to ensure the absolute path contract, but it does **not** verify that the file is trusted, has the right ABI, or does not contain symlinks outside the intended directory.

## 4. Complete JNI Hands-On on Linux + JDK 17+

This hands-on uses a very small native library with the logical name `pathlesson`. We keep the same native file and run **three fresh JVMs**, comparing when changing the property in `main`, when specifying an absolute file, and when setting the search path at startup. The example is designed for **Linux x64 or Linux matching the architecture of the JDK in use, GCC/Clang, JDK 17+**; other systems need platform-specific compilation/linking steps.

### Step A — Java file `NativeLoadDemo.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class NativeLoadDemo {
    private static native int answer();

    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: java NativeLoadDemo name|file <library-file>");
        }

        String mode = args[0];
        Path library = Path.of(args[1])
                .toAbsolutePath()
                .normalize();

        if (!Files.isRegularFile(library)) {
            throw new IllegalArgumentException(
                    "Native library file does not exist: " + library);
        }

        String directory = library.getParent().toString();

        // Set after the JVM has entered main: only proves the property changes.
        System.setProperty("java.library.path", directory);
        System.out.println("property updated="
                + directory.equals(System.getProperty("java.library.path")));

        try {
            switch (mode) {
                case "name" -> System.loadLibrary("pathlesson");
                case "file" -> System.load(library.toString());
                default -> throw new IllegalArgumentException(
                        "Mode must be name or file");
            }

            System.out.println("result=" + answer());
        } catch (UnsatisfiedLinkError e) {
            // Only for observation in this lesson; real applications must log the cause.
            System.out.println("load failed: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

The program does not place `System.loadLibrary` inside `static { ... }` so that each execution mode can be explicitly selected in `main`. The `answer()` method is defined in the native library in the next step.

### Step B — C file `native_path.c`

```c
#include "NativeLoadDemo.h"

JNIEXPORT jint JNICALL Java_NativeLoadDemo_answer(
        JNIEnv *env, jclass clazz) {
    (void)env;
    (void)clazz;
    return 42;
}
```

The function name and signature follow JNI conventions for `static native int answer()` in a class without a package declaration named `NativeLoadDemo`. The header `NativeLoadDemo.h` is **automatically generated by javac**; there is no need to write the JNI prototype manually.

### Step C — Compile

Run in the same directory containing the two files above:

```bash
# JAVA_HOME points to the JDK being used for compilation, e.g. /usr/lib/jvm/... .
javac -h . NativeLoadDemo.java

mkdir -p native-out

cc -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o native-out/libpathlesson.so \
  native_path.c
```

`javac -h .` both compiles `NativeLoadDemo.class` and generates `NativeLoadDemo.h`. `cc -shared -fPIC` builds a shared library on Linux; the two `include` paths provide JNI declarations. Before this step, you need a native compiler and `JAVA_HOME` pointing to the right JDK. When loading in another environment, the library must be compiled for the exact architecture/ABI of the target Java process.

### Step D — Three independent runs

**Run 1 — change the property inside `main` and then call by name:**

```bash
java NativeLoadDemo name native-out/libpathlesson.so
```

When the `native-out` directory **is not in the initial native search path** and there is no library with the same name elsewhere, the standard output is:

```text
property updated=true
load failed: UnsatisfiedLinkError
```

This is a **conditional result**, because the default search path can vary by system/JVM. The file `libpathlesson.so` still exists and the readable property did change. The error comes from `loadLibrary` using the previously configured name-based search mechanism, not taking the new directory from `System.setProperty`.

**Run 2 — load the file using an absolute path created by Java:**

```bash
java NativeLoadDemo file native-out/libpathlesson.so
```

Expected output:

```text
property updated=true
result=42
```

`Path.toAbsolutePath()` converts the relative file name from the argument into an absolute path; `System.load(...)` uses that exact file. There is no need to change the JVM's search path to locate the main file.

**Run 3 — configure `java.library.path` at startup:**

```bash
java -Djava.library.path=native-out \
  NativeLoadDemo name native-out/libpathlesson.so
```

Expected output:

```text
property updated=true
result=42
```

Even though `main` sets the property again to an absolute path value, `loadLibrary` succeeds because the JVM startup **already had** the `native-out` directory to search for the file. Comparing the three runs shows the difference between **the visible value of the system property**, **the search path used by the JVM**, and **the absolute path to the file**.

If the library fails to load in run 2 or 3, do not immediately conclude it is due to `java.library.path`: check the compiler/JDK arch, output file, access permissions, dependent libraries, and the `UnsatisfiedLinkError` message. The `catch` block in the example only prints the exception type to keep stdout short; in a real system, keep the message/stack trace for diagnosis.

## 5. Two Layers of Library Lookup: JVM Finds the Main File, OS Finds Dependencies

Suppose `libengine.so` is built to require `libcodec.so`:

```text
Java
  └─ System.load("/opt/product/native/libengine.so")
       │
       ├─ Java already knows the exact libengine.so file
       ▼
     OS dynamic loader (Linux)
       └─ Needs to find libcodec.so next
            ├─ ELF RPATH/RUNPATH (depending on the binary)
            ├─ LD_LIBRARY_PATH used by the loader according to OS rules
            ├─ cache/system locations...
            └─ Does not automatically use java.library.path
```

If `libengine.so` is found but `libcodec.so` cannot be found, `System.load` can still throw `UnsatisfiedLinkError`. Setting `java.library.path` correctly for the main file does not automatically resolve dependencies. The OS library lookup strategy also differs across platforms:

- **Linux/ELF:** inspect `DT_NEEDED`, `RPATH`/`RUNPATH`, `$ORIGIN`, and search paths applied by the dynamic linker. `LD_LIBRARY_PATH` is typically a process environment setting at startup. `readelf -d libengine.so` helps view dependencies and embedded paths; `ldd` is useful for **trusted binaries**.
- **Windows:** the Windows loader applies its own DLL search order (affected by the application directory, loader policies, and system configuration). `PATH` is a factor in some cases, but it is **not** a copy of `java.library.path`. You can use `dumpbin /DEPENDENTS` or an appropriate dependency inspection tool.
- **macOS:** `@rpath`, `@loader_path`, `@executable_path`, and Mach-O load commands determine the link paths; some environment variables are affected by OS protection mechanisms. `otool -L libengine.dylib` shows dependent libraries.

**General rule:** updating `System.setProperty("java.library.path", ...)` does not control the OS dynamic loader. Java `System.getenv()` also does not provide a standard API to rewrite the environment of the current process. Configure the environment before running Java or package dependencies using supported native loader mechanisms.

For Linux, `$ORIGIN` in RUNPATH/RPATH (depending on linker and packaging policy) can help `libengine.so` find `libcodec.so` located next to it. This is generally more reliable than arbitrarily mutating the environment while the application is running. Check the specific security and precedence rules of your OS/toolchain.

## 6. Valid Approaches When the Library Directory Is Only Known at Runtime

### Approach A — Location known in advance: set JVM argument before startup

For example, in a startup script, service manager, container entrypoint, or Gradle/Maven launch config:

```bash
java -Djava.library.path=/opt/product/native -jar product.jar
```

If you need to change the search path for the entire application, update the startup configuration and launch a **new JVM**. In containers, configure the image/mount/command and native dependencies so they are available at startup; changing the container environment after Java is already running does not automatically update the old JVM.

### Approach B — File name only known after startup: use `System.load`

Read the configuration, determine the right native build file matching the OS/CPU, verify it is a file in an allowed area, and then call an absolute path:

```java
// Illustrative snippet, running in trusted library management code.
Path nativeFile = Path.of(configuredDirectory, "libengine.so")
        .toAbsolutePath()
        .normalize();

if (!Files.isRegularFile(nativeFile)) {
    throw new IllegalArgumentException("Missing native file: " + nativeFile);
}

System.load(nativeFile.toString());
```

The code above is for Linux and requires the corresponding `import` statements. Do not arbitrarily construct file names from untrusted input. Verify a trusted directory, access permissions, provenance, and architecture compatibility before loading. `normalize()` alone is not enough to prevent symlinks pointing elsewhere; environments with security requirements need verification via path policies and the real filesystem.

**Limitation:** `System.load` is not equivalent to “unloading/reloading” a library currently in use, and does not automatically resolve transitive dependencies.

### Approach C — Packaging native libraries inside a JAR

`System.load` does not directly load an entry inside a JAR via a `jar:file:...!/...` path like a regular native file. An implementation mechanism is:

1. Select the native resource corresponding to the OS/architecture.
2. Extract it from the JAR into a dedicated, trusted native directory, with a specific file name/path; pay attention to permissions, contention between processes, and cleanup.
3. `System.load(absoluteExtractedFilePath)` once the file is complete.
4. Properly provide native dependencies according to OS rules.

Do not create libraries in a shared directory where someone else could replace the file while the program is loading it. If the application has multiple native versions, you need a file naming/version partitioning strategy and must avoid loading a binary incompatible with the Java code.

### Approach D — Custom class loader (framework cases)

`ClassLoader.findLibrary(String libname)` can be overridden so the JVM receives an **absolute path** for libraries belonging to classes loaded by that class loader. This mechanism is useful when you **own the framework/class loader**, but it is not a way to globally change `java.library.path` for all class loaders. It also does not bypass the rule that each JNI native library is tied to one class loader, or the inability to freely unload/hot-swap a binary in use.

Do not create a new class loader just to work around `java.library.path` unless you genuinely need class/native isolation and complex plugin lifecycle management.

### Approach E — FFM API when the application uses the Foreign Function & Memory API

In Java 22+, an application using FFM can select a library with `SymbolLookup.libraryLookup(Path, Arena)` and obtain symbol addresses via the FFM API. This is a **different mechanism** from `System.loadLibrary` for JNI; it does not automatically link JNI `native` methods. A Java 22+ illustrative snippet:

```java
// Illustrative, does not create a downcall yet; requires import java.lang.foreign.*.
try (Arena arena = Arena.ofConfined()) {
    SymbolLookup lookup = SymbolLookup.libraryLookup(
            Path.of("/opt/product/native/libengine.so"), arena);
    // lookup.find("exported_function").orElseThrow()
    // requires the correct C signature and FunctionDescriptor before calling.
}
```

`libraryLookup` is a restricted method and may require `--enable-native-access` configured appropriately for the module/JDK (for example, a classpath application uses `--enable-native-access=ALL-UNNAMED`). The lifecycle of the symbol/library lookup is tied to the `Arena`; do not retain a native address and call it after the arena is no longer valid. This mechanism also does not bypass the OS having to resolve dependencies.

## 7. Why Reloading After Modifying a File Is Not Native “Hot Reload”

Native libraries are not like Java classes that can change versions through a new class loader. Practical rules:

- Once a class loader has loaded a JNI library, loading the same binary again does not necessarily re-read the file or re-run initialization code. The JVM and OS may keep the already loaded library.
- The JNI specification stipulates that a JNI native library cannot be loaded simultaneously into **two different class loaders**; you may encounter `UnsatisfiedLinkError: ... already loaded in another classloader`. This often happens when redeploying a web app/plugin while the old class loader is still alive.
- Replacing the `.so`/`.dll` on disk while it is in use does not guarantee changing the native code currently executing, and may violate OS file management mechanisms.
- A library can only be released under appropriate lifecycle conditions; there is no symmetric standard Java API `System.unloadLibrary(...)` for an application to arbitrarily unload a JNI library in use.

For changing the **global native search path**, updating a **binary version**, or modifying the **native ABI**, the most verifiable management approach is usually to stop the process and start a new JVM with the exact libraries/configuration. For a plugin framework that must run continuously, versioning, class loader/native isolation, and specific unload limits must be designed from the start; do not use `System.setProperty` as a hot swap solution.

## 8. Diagnosing `UnsatisfiedLinkError` by Cause

`UnsatisfiedLinkError` can arise at different steps. Read the **entire message/cause/stack trace**; do not conclude every error is “wrong `java.library.path`.”

| Symptom | Cause to check | Remediation |
| --- | --- | --- |
| `no foo in java.library.path: ...` | Logical name cannot be resolved via the search path the JVM is using | Configure `-Djava.library.path` before startup or use `System.load` with an absolute path |
| `Expecting an absolute path of the library` | Passed a relative path to `System.load` | Use `Path.toAbsolutePath()`/an absolute path |
| Message reporting missing `libbar.so` or `bar.dll` | Main file found, but missing a native dependency | Adjust the OS dependency search mechanism, build RUNPATH/rpath/packaging |
| `wrong ELF class`, `not a valid Win32 application`, architecture message | JVM/native binary mismatch in 32/64-bit or CPU/ABI | Use a native artifact matching the target and Java process |
| `already loaded in another classloader` | JNI library was loaded from another class loader that is still alive | Design loader ownership/lifecycle, avoid duplicate loads, consider restart |
| `... symbol not found`, `undefined symbol`, or `'...NativeMethod...'` | Missing symbol, wrong export/signature, mismatched binary or dependency version | Check JNI header, function name, ABI, exported symbols, and dependency versions |
| Loads successfully, but native call crashes | Wrong signature, native memory bug, ABI or lifecycle error | Use native debugging, crash logs/hs_err, check JNI/FFM signatures, not just path fixes |

A short checklist:

1. **Confirm the API:** is the code currently calling `System.loadLibrary`, `System.load`, or FFM lookup?
2. **Confirm the timing:** was the path set in the `java -D...` command or assigned in `main` after the JVM had started?
3. **Confirm the file:** which OS file does the logical name `foo` correspond to, does the file exist, and is the path valid for the calling class loader?
4. **Confirm the binary:** are the architecture/OS/ABI of the library compatible with the JVM? Use `file libfoo.so` on Linux; for dependencies inspect `readelf -d`, `ldd` (trusted binaries).
5. **Confirm dependencies:** can the OS loader find the dependent libraries?
6. **Confirm lifecycle:** was the library already loaded by another class loader, or is the application trying to replace a binary currently in use?

In particular, `System.out.println(System.getProperty("java.library.path"))` is configuration information viewed through the Java API, **not final proof** of the search path used by the JVM at the time of the error. Combine the actual command line, JDK build/version, full stack trace, and native loader evidence.

## 9. Online “Refresh Path” Tricks: Why Should They Be Avoided?

Some older guides suggest using reflection on internal fields such as `ClassLoader.sys_paths` or `usr_paths`, setting them to `null`, and then calling `System.loadLibrary` again. Those fields are **not public API**; they may differ or not exist on newer JDKs. Module encapsulation since Java 9+, implementation changes, access permissions, and thread safety issues make this trick non-portable and unsupported.

Similarly:

- Setting `System.setProperty("java.class.path", ...)` does not fix the native search path.
- Putting `-Djava.library.path=...` as a **`main` argument** after the JVM has started is the wrong timing.
- Changing `user.dir` is not an officially supported way to change the OS loader's current directory.
- Changing `LD_LIBRARY_PATH`/`PATH` “inside Java” via non-standard tricks does not make already initialized subsystems update in sync, and does not work across all OS/JVM versions.
- Using `System.load` for a specific `.so` does not make the JVM forget a previous JNI library with the same name.

When portability is needed, use public mechanisms: **startup options**, **absolute file paths**, **loaders/frameworks with clear contracts**, or **starting a new process**.

## 10. Applying to Real-World Application Design

| Need | Recommended choice | Limitations to remember |
| --- | --- | --- |
| Fixed native lib per release | `-Djava.library.path=...` at startup, then `loadLibrary` | Requires a new JVM to change cached configuration |
| User selects native file at runtime | Verify path, `System.load(absolutePath)` | Dependencies/lifecycle still follow the OS and class loader |
| Ship library as a JAR resource | Extract to a trusted file path, `System.load` | Cannot load JAR entry directly; handle multi-architecture and cleanup |
| Native lib has multiple dependent libraries | Package together with matching ABI; configure OS loader / `RUNPATH` properly | `java.library.path` is not a universal dependency resolver |
| Plugin needs isolated classes and JNI | Design class loader and native ownership from the start | The same JNI binary cannot arbitrarily attach to multiple loaders |
| Deploying a new native version to server | Deploy artifact then restart/roll JVM | Replacing a loaded file does not guarantee changing executing code |
| Application uses Java 22+ FFM | `SymbolLookup.libraryLookup(Path, Arena)` with appropriate native access | Different from JNI linking, has arena lifecycle, and still depends on OS loader |

When receiving a request to “change the library search directory right now without restarting,” the deciding question is: **do you need to load a new native file that has never been used, or do you need to replace a native build already linked in the JVM?** The first case can be handled with an absolute `System.load` if native conditions permit. The second case has heavier constraints around JNI/class loaders, OS mapped libraries, symbol resolution, and ABI; it usually requires a restart/rolling deployment process.

## 11. Self-Check

**Question 1.** `System.setProperty("java.library.path", "/tmp/libs")` returns normally. Is it certain that `loadLibrary("foo")` afterward will find `/tmp/libs/libfoo.so`?

**No.** That only changed the property at the Java layer, while OpenJDK's search path may have been cached since startup. Pass `-Djava.library.path=/tmp/libs` right at startup or use `System.load("/tmp/libs/libfoo.so")` if you explicitly identify the exact file.

**Question 2.** You called `System.load("/opt/native/libfoo.so")` but still received `UnsatisfiedLinkError` reporting `libbar.so` is missing. Should you change `java.library.path`?

**Not a direct solution.** The error is in a dependent library of the main file. You must check the OS loader's search mechanism, build flags/RUNPATH/RPATH, the environment, and how `libbar.so` is packaged.

**Question 3.** You used `-Djava.library.path=./native` but `System.loadLibrary("foo")` still cannot find it. What three things should be verified?

The `./native` directory is interpreted relative to the working directory **in the actual environment at startup**; the file has the corresponding native name (e.g., `libfoo.so` on Linux) and the right architecture; and dependencies and class loader ownership are not causing errors. Then check the full error text.

**Question 4.** Does replacing `libfoo.so` on disk with a new build while the JVM is using the old library immediately swap the implementation for all subsequent JNI calls?

**Not guaranteed.** The JNI library is already loaded/linked and has its own lifecycle. A deployment/restart process or a dedicated plugin native lifecycle design is required.

**Question 5.** Why can `loadLibrary("foo")` and `load("/absolute/path/libfoo.so")` produce different results in the same JVM?

The first starts with a **logical name** and the JVM/class loader's search path; the second already specifies **the main file by an absolute path**. Both are still subject to OS loader, ABI, and JNI lifecycle constraints.

## Official Documentation for Reference

- Java SE 17 — `ClassLoader.findLibrary(String)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#findLibrary(java.lang.String)
- Java SE 21 — `System`, standard properties, and caching notes: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html
- Java SE 21 — `Runtime.load` and `Runtime.loadLibrary`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html
- OpenJDK — `StaticProperty.javaLibraryPath()` (implementation characteristic): https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/jdk/internal/util/StaticProperty.java
- JNI Specification — Library and Version Management: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html#library-and-version-management
- Java 22+ — `SymbolLookup.libraryLookup(Path, Arena)`: https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html

**Remember:** to change the `loadLibrary` search path for the next run, adjust the **JVM startup configuration**. To load a **specific native file** after the JVM is already running, use an **absolute path** with the appropriate mechanism. Do not confuse changing a system property with reconfiguring the native loader, and do not forget dependent libraries and the JNI lifecycle.
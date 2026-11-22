# Diagnosing Native Errors vs. Java Class Linkage Errors

## 1. Why Are These Two Error Groups Easily Confused?

When upgrading the JDK, switching container base images, or updating libraries, a Java application can fail right at startup, when calling a native method, or hours into processing. Error messages frequently share similar words like *library*, *class*, *symbol*, *link*, *load*, or *not found*. Looking at only one exception line makes it very easy for teams to fix the wrong layer.

For example:

~~~text
java.lang.UnsatisfiedLinkError: no nativecalc in java.library.path
~~~

differs fundamentally from:

~~~text
java.lang.NoClassDefFoundError: com/example/api/Request
~~~

and also differs from:

~~~text
java.lang.NoSuchMethodError:
  'void com.example.api.Request.setId(java.lang.String)'
~~~

In the first case, the application failed to load a **native library** by the requested name. In the second case, the JVM could not find or could not define/initialize a required **Java class**. In the third case, caller bytecode pointed to a **method descriptor that no longer matches** the Java class present at runtime.

However, the boundary does not align cleanly with the exception inheritance tree: `UnsatisfiedLinkError` is itself a subclass of `LinkageError`. Hence, seeing "LinkageError" is **not enough** to conclude an error is Java-only; check the error subtype, failing phase, stack trace, message, and loaded libraries.

This lesson provides a systematic diagnostic method for Java Advance Compatibility Migration under the **Agents and Native Code** chapter: spanning classpath/module path, JNI/JNA, JVM loaders, and the OS dynamic linker through crash dumps, class-file versions, dependency resolution, and agent integration.

## 2. The Big Picture: Multiple Loaders and Linkage Layers

A Java program moves through these stages:

~~~text
Source Java (.java)
        |
        v
Compiler (javac)  --->  Class files (.class)
                               |
                    Java ClassLoader / Module Layer
                               |
                     JVM link / verify / resolve
                               |
                     Java class initialization
                               |
                     Native method or library call
                               |
                System.load / System.loadLibrary / FFI
                               |
                     OS dynamic loader
                               |
                    Native .dll / .so / .dylib
                               |
                Dependent libraries + exported symbols
                               |
                       Native execution
~~~

Distinguish **at least four kinds of linkage**:

1. **Java class loading:** locating and defining a class from the classpath, module path, or a custom class loader.
2. **JVM linkage:** verifying/resolving constant-pool references to classes, fields, and methods with matching descriptors, accessibility, and static/instance kinds.
3. **Native library loading:** the OS dynamic loader locating the binary and its native dependencies; the JVM bringing the library into the process context.
4. **JNI/FFM symbol resolution:** the runtime binding a native method or foreign function to the corresponding symbol/address.

An error in an earlier step can **cascade into a different error reported later**. For instance, a Java class static initializer calls `System.loadLibrary` and throws `UnsatisfiedLinkError`; subsequent uses of that class may only show `NoClassDefFoundError: Could not initialize class...`. Always find the **first error** in the logs, not just the final exception.

## 3. Quick Symptom Differentiation Table

| Symptom | Typical Layer Involved | First Investigation Clue |
| --- | --- | --- |
| `UnsatisfiedLinkError: no X in java.library.path` | Native library lookup | Library name, path, OS/architecture |
| `UnsatisfiedLinkError: ... cannot open shared object file` | OS dynamic loader | Native file or dependent library, ELF dependencies |
| `UnsatisfiedLinkError: ... wrong ELF class: ELFCLASS32` | Native binary ABI | 64-bit JVM vs. 32-bit native library mismatch |
| `UnsatisfiedLinkError: '... nativeMethod(...)'` | JNI native symbol/method binding | JNI symbol name, method signature, JAR/native version |
| `NoClassDefFoundError: com/.../Type` | Class loading/initialization | Runtime classpath/module path, first root cause |
| `ClassNotFoundException` | Dynamic class lookup | `Class.forName`, class loader, module/dependency |
| `NoSuchMethodError` | Java binary method linkage | Method descriptor and resolved JAR |
| `NoSuchFieldError` | Java binary field linkage | Field name/descriptor and runtime class |
| `IllegalAccessError` | Java access/module linkage | Access modifiers and module exports |
| `IncompatibleClassChangeError` | Class/method/field shape change | Static/instance, interface/class, ABI |
| `UnsupportedClassVersionError` | Java class-file version | Major version and JVM runtime |
| `ExceptionInInitializerError` | Class initialization | Original exception inside `<clinit>` |
| `SIGSEGV` / `EXCEPTION_ACCESS_VIOLATION`, `hs_err_pid*.log` | JVM fatal/native/unsafe | Problematic frame, native stack, JDK/agent/JNI |
| `ClassCastException` between two "same-named" classes | Runtime type identity / class loaders | Defining class loader of each type; this is not a `LinkageError` |

These are **starting points**, not rules proving a single root cause. For example, a native library may load inside a static initializer; if the native loader fails, later logs can contain both Java initialization and linkage errors.

## 4. Understanding the Exception Hierarchy Precisely

In Java, `Error` generally indicates serious problems that business code should not catch broadly and swallow. Key classes:

~~~text
Throwable
  +-- Error
       +-- LinkageError
            +-- UnsatisfiedLinkError
            +-- NoClassDefFoundError
            +-- IncompatibleClassChangeError
            |    +-- NoSuchMethodError
            |    +-- NoSuchFieldError
            |    +-- AbstractMethodError
            |    +-- IllegalAccessError
            +-- ClassFormatError
            |    +-- UnsupportedClassVersionError
            +-- VerifyError
       +-- ExceptionInInitializerError
  +-- Exception
       +-- ClassNotFoundException
       +-- RuntimeException
            +-- ClassCastException
~~~

This diagram focuses on key branches rather than listing every subtype.

**Common misunderstanding:** `UnsatisfiedLinkError` extends `LinkageError`, yet its causes normally involve **native libraries or native method binding**. Conversely, `NoSuchMethodError` is normally Java bytecode-level method linkage. Grouping by *where the JVM failed* is more helpful than grouping solely by base class.

### 4.1. Why You Must Not `catch (LinkageError)` to Hide Failures

~~~java
try {
    service.start();
} catch (LinkageError ignored) {
    // Dangerous: continues running with an invalid class/native state.
}
~~~

This is an anti-pattern. Swallowing linkage errors lets the program fail unpredictably elsewhere while erasing first-failure evidence. For optional components, design an explicit fallback *before* calling into them or handle specific expected exceptions while logging the root cause and restricting capability cleanly.

## 5. `UnsatisfiedLinkError` Has Multiple Distinct Causes

Never lump every `UnsatisfiedLinkError` into "missing DLL." Separate them into:

1. The JVM cannot find a native library matching the name.
2. The JVM finds the file, yet the OS loader refuses to load it due to architecture, ABI, permissions, or native dependencies.
3. The library loads, yet a native method cannot bind to its implementation.
4. The library shares the name yet has the wrong version, misses an exported symbol, or uses incompatible calling convention/visibility.
5. Class loader / native library ownership conflicts or load-order errors.
6. Native code loads yet fails during initialization/hooks or rejects binding.

Example:

~~~text
java.lang.UnsatisfiedLinkError:
  no nativecalc in java.library.path: ...
~~~

typically indicates `System.loadLibrary("nativecalc")` could not locate a matching file on the search path.

~~~text
java.lang.UnsatisfiedLinkError:
  'int example.nativebridge.NativeMath.add(int, int)'
~~~

typically indicates native method `add` was declared without a linked native implementation, even when both JAR and library are present.

### 5.1. Read the Whole Message, Not Only the Exception Class Name

With JNI, the method name, parameter types, and return type in the message are crucial signals. With OS loaders, the filename, `cannot open shared object file`, `undefined symbol`, or missing native dependency name holds the real clue.

On Windows, the message may say "The specified module could not be found" even when the main DLL exists: **a dependent DLL** may be missing. Never blame `java.library.path` before checking the native dependency graph.

## 6. `System.load` and `System.loadLibrary`

Two representative APIs:

~~~java
System.load("/absolute/path/libnativecalc.so");
System.loadLibrary("nativecalc");
~~~

**`System.load`** accepts an absolute path to a native library file. **`System.loadLibrary`** accepts a **logical library name** and lets the JVM map the name and search using platform rules.

Typical mapping examples:

| OS | Logical name `nativecalc` | Typical Filename |
| --- | --- | --- |
| Windows | `nativecalc` | `nativecalc.dll` |
| Linux | `nativecalc` | `libnativecalc.so` |
| macOS | `nativecalc` | `libnativecalc.dylib` |

Do not include `lib` or extensions like `.so` inside `loadLibrary` when following standard logical naming, unless a vendor API specifies otherwise.

### 6.1. `java.library.path` Is Not `java.class.path`

`java.class.path` governs where Java classes and JARs are searched on the classpath. `java.library.path` influences how `System.loadLibrary` locates native libraries on supporting JVMs.

~~~bash
java -Djava.library.path=/opt/app/native \
     -cp app.jar example.Main
~~~

This command is illustrative. `-Djava.library.path` is a JVM option passed before the entry point. Calling `System.setProperty("java.library.path", "...")` after the JVM is already running **is not a reliable way** to make the JVM re-read native search paths because internal loader state may already be initialized or cached.

For deterministic environments, prefer `System.load` with a **managed, verified absolute path** rather than relying on incidental OS paths. Even then, loading by absolute path does not automatically locate transitive native dependencies required by the OS dynamic loader.

## 7. The OS Loader: Finding a File Does Not Guarantee Loading It

Native files normally link against companion libraries:

~~~text
Java app
   |
   v
libnativecalc.so
   +-- libc.so
   +-- libstdc++.so
   +-- libvendorcrypto.so
   +-- platform runtime libraries
~~~

If `libnativecalc.so` exists yet `libvendorcrypto.so` is absent, loading fails.

### 7.1. Linux

Reference commands when inspecting **trusted** libraries:

~~~bash
file /opt/app/native/libnativecalc.so
readelf -h /opt/app/native/libnativecalc.so
readelf -d /opt/app/native/libnativecalc.so
ldd /opt/app/native/libnativecalc.so
~~~

`file`/`readelf` inspect ELF type, architecture, shared dependencies, and `RPATH`/`RUNPATH` metadata. `ldd` shows how dependencies resolve in the current environment, yet exercise caution with **untrusted binaries**; for binaries of unknown provenance, use static tools such as `readelf` first.

Linux native dependency lookup involves `RPATH`, `RUNPATH`, `LD_LIBRARY_PATH`, dynamic linker config, and system library directories. Never assume `java.library.path` governs OS resolution of transitive native dependencies.

### 7.2. macOS

~~~bash
file /opt/app/native/libnativecalc.dylib
otool -L /opt/app/native/libnativecalc.dylib
~~~

Check architecture, install names, dependencies, `@rpath`/`@loader_path`, and runtime rules. `DYLD_*` environment variables may be stripped under System Integrity Protection, so setting env vars is not a universal fix.

### 7.3. Windows

In a Developer Command Prompt / Visual Studio toolchain:

~~~text
dumpbin /HEADERS nativecalc.dll
dumpbin /DEPENDENTS nativecalc.dll
dumpbin /EXPORTS nativecalc.dll
~~~

These commands require the corresponding Windows developer tools. Besides the primary DLL, verify dependent DLLs and runtimes such as Microsoft Visual C++ Redistributable required by the compiler toolchain that built the DLL.

Never download a same-named DLL off the Internet to fix "module not found": doing so creates supply-chain risks and loads mismatched binaries.

## 8. Architecture, ABI, libc, and Platform Runtime Mismatches

A native library can bear the expected filename while mismatching the platform:

- 64-bit JVM paired with a 32-bit DLL/SO.
- Container running `linux/arm64` while the native library exists only for `x86_64`.
- Binary linked against `glibc` running inside a `musl` container image, or vice versa.
- Binary requiring OS library symbol versions newer than the container image provides.
- Windows DLL compiled with a toolchain whose C++ runtime is missing on the host.
- macOS binary lacking an architecture slice for the active CPU/runtime.

Sample error messages:

~~~text
wrong ELF class: ELFCLASS32
~~~

or:

~~~text
version 'GLIBC_2.xx' not found
~~~

Neither error can be fixed by adding Java JARs. Pick binaries matching platform/architecture/ABI, install permitted native dependencies, or align the image/toolchain.

### 8.1. Container Base Images Are Part of the Equation

Switching base images from Debian/Ubuntu to Alpine swaps `glibc` for `musl` even when the JDK version stays identical. Switching from `amd64` to `arm64` can break JNI libraries while pure Java bytecode runs unaffected.

In Java compatibility migrations, record **JDK vendor + release + OS image + libc + CPU architecture** together as one baseline tuple rather than writing only "Java 21."

## 9. JNI Native Method Linking: Present Library, Missing Method

Java example:

~~~java
package example.nativebridge;

public final class NativeMath {
    static {
        System.loadLibrary("nativecalc");
    }

    private NativeMath() {}

    public static native int add(int left, int right);
}
~~~

The JVM looks up the implementation when `add` is called or bound. If the library loaded yet provides no matching symbol or registration, the JVM throws `UnsatisfiedLinkError` naming that method.

Common causes:

- Renaming the Java package, class, or method without rebuilding the native library.
- Changing parameter counts/types, `static` vs. instance, or method signatures.
- Native function not exported properly.
- C/C++ name mangling or calling convention mismatch.
- Java wrapper JAR and native artifact come from different versions.
- Native method expects `RegisterNatives` yet registration failed or never ran.
- Class loader loaded a different `Class` instance than native registration targeted.

**Crucially:** matching the Java method name alone is **insufficient** for JNI linkage. Method descriptors include parameter and return types at the JVM level; overloaded native methods require matching JNI mangling or explicit registration.

## 10. Generating JNI Headers with `javac -h`

Never guess JNI function names when packages, overloads, special characters, or renamed symbols are involved. On modern JDKs, let the compiler generate headers:

~~~bash
javac -h build/headers \
      -d build/classes \
      src/main/java/example/nativebridge/NativeMath.java
~~~

The compiler emits an illustrative header `example_nativebridge_NativeMath.h` containing:

~~~c
JNIEXPORT jint JNICALL
Java_example_nativebridge_NativeMath_add(
    JNIEnv *, jclass, jint, jint);
~~~

For `static` methods, the second parameter is `jclass`; for instance native methods, it is `jobject`. `JNIEnv*` is the JNI interaction handle inside native code.

Sample native implementation with small values:

~~~c
#include "example_nativebridge_NativeMath.h"

JNIEXPORT jint JNICALL
Java_example_nativebridge_NativeMath_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
~~~

Production C code must handle overflow checks, input validation, error propagation, allocation, and memory safety per requirements. This snippet demonstrates **JNI signature matching** only, not a production-hardened native library.

### 10.1. Compiling the Sample Library on Linux

With a matching C compiler and JDK headers:

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/native/libnativecalc.so \
  src/native/nativecalc.c
~~~

Assuming the output directory exists. Compiler flags and header paths differ across Windows, macOS, and Linux; do not paste Linux commands on Windows and blame compiler/JNI breakage.

Run:

~~~bash
java -Djava.library.path=build/native \
     -cp build/classes example.nativebridge.Main
~~~

`Main` is an illustrative application entry point calling `NativeMath.add(2, 3)`. For real libraries, maintain reproducible CI build scripts with pinned toolchains instead of ad-hoc manual compiles.

## 11. Inspecting JNI Symbols and Method Descriptors

On the Java side:

~~~bash
javap -classpath build/classes \
      -private -s example.nativebridge.NativeMath
~~~

Output excerpt:

~~~text
public static native int add(int, int);
  descriptor: (II)I
~~~

`(II)I` means taking two `int`s and returning `int`. Switching Java types to `long` changes the descriptor; rebuilding Java without rebuilding the native library breaks binding.

On Linux, check exported symbols:

~~~bash
nm -D --defined-only build/native/libnativecalc.so
readelf -Ws build/native/libnativecalc.so
~~~

On macOS, inspect Mach-O binaries with `nm`/`otool`. On Windows, check `dumpbin /EXPORTS`. Look for exported JNI symbols or check whether the library relies on `RegisterNatives`.

### 11.1. Dynamic Registration Uses Different Rules from Exported Names

JNI supports `RegisterNatives` to bind Java native methods to function pointers explicitly. In that case, native functions need not be exported under long `Java_package_Class_method` names.

Therefore, **not seeing JNI function names in export tables is insufficient** to prove a library is broken. Determine whether the library uses **name-based resolution** or **explicit registration**. For explicit registration, inspect method names/descriptor strings and `RegisterNatives` return values.

### 11.2. Overloaded Native Methods

Suppose you have:

~~~java
public static native int convert(int value);
public static native long convert(long value);
~~~

JNI name mangling for overloaded methods encodes parameter signatures distinctly. Never copy a symbol name from an old Java method and tweak C typedefs by hand. Regenerate headers and inspect actual exported symbols.

## 12. `JNI_OnLoad` and Native Library Initialization

A native library can define `JNI_OnLoad` to run initialization hooks and return its supported JNI version. This hook is optional; **not every JNI library implements `JNI_OnLoad`**.

C example:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    return JNI_VERSION_1_8;
}
~~~

Real libraries often use `JNI_OnLoad` to acquire `JNIEnv`, register native methods, initialize caches, or validate runtime invariants. Initialization failures must be correlated across JVM logs and native implementation behavior.

Never change the returned JNI version arbitrarily just "to make a new JDK start"; confirm the actual JNI API version used and supported JVM specifications.

### 12.1. Native Libraries Have Their Own Initialization Dependencies

`JNI_OnLoad` or C++ static constructors may invoke other native libraries or subsystems. When failures occur inside `System.loadLibrary`, check:

- Native constructors/initializers and `JNI_OnLoad`.
- Secondary native dependencies and environment variables.
- Locking and threading during initialization.
- Pending JNI exceptions or failed return statuses.
- JDK/JNI versions and vendor support.

Never dismiss every initialization-phase failure as a missing `.so`/`.dll` file.

## 13. Java Class Linkage: Pure Java Errors Have Distinct Mechanisms

The JVM links classes, methods, and fields via class file metadata and constant pools. A JAR compiled against library v1 may run alongside an incompatible v2 lacking binary compatibility.

Example:

~~~java
// Library v1
public class UserService {
    public String load(String id) {
        return id;
    }
}
~~~

The consumer compiled against `load(String):String`. Library v2 changes it:

~~~java
// Library v2: incompatible method descriptor
public class UserService {
    public long load(long id) {
        return id;
    }
}
~~~

Running precompiled consumer bytecode against v2 triggers `NoSuchMethodError`. This has **nothing to do with JNI** despite containing the word "linkage."

Fix it by preserving binary-compatible overloads/adapters while legacy consumers persist, or recompiling consumers against the updated API and shipping a consistent artifact set.

### 13.1. `NoSuchFieldError` and `IncompatibleClassChangeError`

Renaming, retyping, or deleting a field triggers `NoSuchFieldError`. Turning a static method into an instance method or changing a class/interface relationship triggers `IncompatibleClassChangeError` or its subtypes.

Setting `java.library.path` or copying DLLs will not fix this. Inspect **Java ABI compatibility and JAR resolution**.

## 14. `NoClassDefFoundError` Differs from `ClassNotFoundException`

### 14.1. `ClassNotFoundException`

A checked exception normally thrown when code dynamically looks up a class by name:

~~~java
Class<?> type = Class.forName(
        "com.example.optional.Plugin");
~~~

If the loader cannot locate the class, `ClassNotFoundException` is thrown. Inspect the class name string, active class loader, module path, and packaged dependencies.

### 14.2. `NoClassDefFoundError`

`NoClassDefFoundError` extends `LinkageError`. It occurs when a class present at compile time cannot be located or defined at runtime, or when that class previously **failed initialization**.

Example:

~~~text
java.lang.NoClassDefFoundError:
  com/example/shared/Request
~~~

Check runtime artifacts, classpath/module path, dependency exclusions, shading, and class loaders.

### 14.3. `Could not initialize class`

Example:

~~~java
public final class NativeClient {
    static {
        System.loadLibrary("nativecalc");
    }
}
~~~

The first access fails inside `System.loadLibrary` with `UnsatisfiedLinkError`. Class initialization fails; subsequent accesses in the same JVM report:

~~~text
java.lang.NoClassDefFoundError:
  Could not initialize class com.example.NativeClient
~~~

Looking only at the final `NoClassDefFoundError` leads investigators to hunt for missing JARs while missing the real native error. Find the **earliest stack trace in that JVM process** and read the initialization failure.

## 15. `ExceptionInInitializerError` and Failures Inside `<clinit>`

The JVM executes static initializers in an internal method shown as `<clinit>`.

~~~java
final class Config {
    static final String VALUE = initialize();

    static String initialize() {
        throw new IllegalStateException("invalid configuration");
    }
}
~~~

If static initialization throws a normal exception, the JVM wraps it in `ExceptionInInitializerError`. If static initialization throws an `Error` (such as `UnsatisfiedLinkError`), do not assume it will always be wrapped in `ExceptionInInitializerError`.

When seeing:

~~~text
java.lang.ExceptionInInitializerError
    at ...
Caused by: java.lang.IllegalStateException: ...
~~~

inspect `Caused by`. When seeing `NoClassDefFoundError: Could not initialize class`, hunt down the initial failed `<clinit>` event in that JVM.

### 15.1. Why Can Restarting Change the Error Message?

Once a class fails initialization, that class definition enters a failed state for the lifetime of the JVM/classloader. After a restart, the first call executes `<clinit>` anew and reveals the original error again. Therefore, "seeing a different exception after restart" does not mean the underlying defect changed.

## 16. Classpath/Module Path and Transitive Dependency Mismatches

Two versions of one library can appear in the dependency graph:

~~~text
app
  +-- library-a
  |    +-- common-api:2.x
  +-- library-b
       +-- common-api:1.x
~~~

Which version wins depends on resolution rules, BOMs, or constraints. `library-a` may have been compiled against `common-api:2.x` while runtime loads `1.x`, causing `NoSuchMethodError` or `NoSuchFieldError`.

### 16.1. Gradle

Project diagnostic commands:

~~~bash
./gradlew :app:dependencies \
  --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
  --dependency common-api \
  --configuration runtimeClasspath
~~~

These commands apply to live project diagnostics. Read **resolved versions**, not merely declared versions.

### 16.2. Maven

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Verify deployed runtime classpaths including scopes, BOMs, exclusions, shading, and server-supplied libraries.

### 16.3. Module Path

With JPMS, inspect `module-info.java`, `requires`, module resolution, and exported packages. A `ClassNotFoundException` or `IllegalAccessError` may reflect module-path differences rather than traditional classpath absence.

Never scatter broad `--add-opens` flags to cure `NoSuchMethodError`: opening reflection cannot restore a method deleted from a JAR.

## 17. `UnsupportedClassVersionError` Is Not a Native Architecture Error

When an older JVM tries loading a class file built with a newer class-file version, it throws:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version
  of the Java Runtime
~~~

Common version mapping:

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Check with:

~~~bash
javap -verbose -classpath app.jar \
  com.example.Main
~~~

Look for `major version`. If an artifact targets Java 21 while production runs Java 17, either upgrade the runtime JVM or compile with `--release 17` if code, APIs, and dependencies permit.

Conversely, a native message like `wrong ELF class` indicates a **native binary architecture** mismatch, not Java class-file major versions. Never tweak `--release` when the failure is a wrong-arch ELF or DLL.

## 18. Multiple Class Loaders: Same Class Name Does Not Guarantee Same Type

In application servers, plugin engines, OSGi, or isolated containers, runtime type identity includes both binary name and defining class loader. Two classes with identical fully qualified names loaded by different loaders are distinct incompatible types.

Symptom:

~~~text
java.lang.ClassCastException:
  class com.example.Model cannot be cast
  to class com.example.Model
~~~

Real messages often print class loader/module details. This is a type-identity conflict, **not `UnsatisfiedLinkError`**.

Native libraries also interact with class loaders: the JVM associates native libraries with defining class loaders upon loading. Messages like:

~~~text
Native Library ... already loaded in another classloader
~~~

indicate the same native binary was loaded across incompatible loaders causing ownership conflicts. Resolve it by centralizing library loading, fixing classloader architecture, or isolating runtimes rather than duplicating DLLs/SOs into random folders.

### 18.1. Class Loader Debugging

On modern JDKs supporting unified logging:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

This logs loaded classes and sources. Because output is huge, limit capture scope and protect sensitive information. On other JVM releases, run `java -Xlog:help` to see supported tags and levels.

## 19. Distinguishing Native Load Errors from JVM Crashes

A native library **that fails to load** normally surfaces as a Java exception/error such as `UnsatisfiedLinkError`. A native library **that loads and executes unsafe native code** can crash the JVM process outright:

~~~text
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=..., pid=..., tid=...
# Problematic frame:
# C  [libnativecalc.so+0x...]
~~~

Or on Windows:

~~~text
EXCEPTION_ACCESS_VIOLATION
Problematic frame: C [nativecalc.dll+...]
~~~

These are fundamentally different failures:

- **Java error with stack trace:** the JVM remained intact long enough to throw a `Throwable`.
- **Fatal VM/native crash:** the process terminates; evidence resides in fatal error logs, core/minidumps, or OS event logs.

Never expect `try/catch (Throwable)` to catch native `SIGSEGV` crashes. Segmentation faults terminate the process without entering Java exception handlers.

### 19.1. Not Every JVM Crash Comes from Your JNI Code

The problematic frame can reside in:

- Application JNI/JNA native libraries.
- Native JVMTI profilers or agents.
- JVM, JIT compiler, or GC runtime code.
- JNI helpers or OS platform libraries.
- Drivers, SSL/crypto, or native compression dependencies.

Inspect frames, native stacks, JDK vendor/builds, agent versions, and reproduction steps. Never assume a JVM bug merely because a Java process crashed; likewise, never blame JNI blindly when the problematic frame sits inside JVM code without investigation.

## 20. `hs_err_pid*.log` and Fatal Error Evidence

HotSpot typically creates a fatal error log named like:

~~~text
hs_err_pid12345.log
~~~

Key sections to inspect:

| Section | Purpose |
| --- | --- |
| Signal/exception | Identifies `SIGSEGV`, `SIGBUS`, access violation, etc. |
| Problematic frame | Native library or JVM frame closest to fault |
| Current thread | Faulting thread and state |
| Native frames | Native call stack if symbols exist |
| Java frames | Java call path if captured |
| Loaded libraries | List of loaded native modules and paths |
| JVM arguments | JDK flags, agents, GC, module settings |
| VM/version/OS/CPU | Exact environment context for reproduction |
| Memory/thread information | Memory layout and crash context clues |

Not every log is complete; severe crashes or read-only filesystems can truncate or prevent file creation.

### 20.1. Specifying Fatal Error Log Location

On HotSpot builds supporting it:

~~~bash
java -XX:ErrorFile=/var/log/java/hs_err_pid%p.log \
  -jar app.jar
~~~

`%p` expands to the process ID. Ensure the directory exists, is writable by the process, and persists across container restarts.

Fatal error logs can include paths, environment variables, arguments, and sensitive data. Always **redact** them before sharing outside authorized channels.

### 20.2. Core Dumps

A core dump lets native debuggers inspect stacks and memory at crash time, subject to OS limits, permissions, `core_pattern`, container runtimes, and JVM flags.

Example on Linux:

~~~bash
ulimit -c unlimited
~~~

This is only one prerequisite, not a guarantee a core file will be produced. Core dumps can contain **every secret residing in process memory**, requiring strict retention, encryption, access control, and deletion policies.

## 21. Symbolication and Native Stack Traces

Messages such as:

~~~text
Problematic frame:
C [libnativecalc.so+0x16a4]
~~~

report an offset inside a native binary without necessarily showing function names or source lines. Deeper analysis requires:

- The exact binary matching the running **build ID**.
- Corresponding debug symbols (e.g., compiled with `-g` where available).
- Platform-compatible native debuggers (`gdb`, `lldb`, `WinDbg`).
- A core/minidump or valid loaded-address map.
- ASLR base addresses to translate addresses accurately.

Linux example:

~~~bash
readelf -n /opt/app/native/libnativecalc.so
addr2line -e /opt/app/native/libnativecalc.so 0x16a4
~~~

`addr2line` works only when offsets are translated accurately against unstripped/matching debug binaries. Never blindly treat an offset lookup against a different or stripped build as proof.

### 21.1. Live Debuggers Alter Runtime Behavior

Attaching a debugger to a production JVM pauses threads and perturbs timing. Follow strict operational authorization. Reproduce failures in staging with the exact native binary, JDK, architecture, and inputs whenever feasible.

## 22. JNI Memory and Threading Bugs That Do Not Raise `LinkageError`

Not every native error surfaces as `UnsatisfiedLinkError`. A properly linked JNI library can still corrupt memory or crash due to:

- Using a `JNIEnv*` pointer on the wrong thread.
- Retaining a local reference after its native frame exits.
- Failing to release `GetStringUTFChars` / `Get*ArrayElements` per contract.
- Array/buffer overruns, use-after-free, or double free.
- Misusing `NewGlobalRef` / `DeleteGlobalRef`.
- Dereferencing stale native pointers after Java object or segment lifetimes end.
- Calling further JNI APIs while a Java exception is pending.
- Calling into Java from unattached native threads.
- Alignment, calling convention, string encoding, or signed integer bugs.

These manifest as crashes, silent corruption, or deadlocks rather than clean Java exceptions.

### 22.1. `JNIEnv*` Is Thread-Affined

Native code must never share one `JNIEnv*` across threads. Native threads calling back into Java must attach/detach via JNI thread-attachment APIs and obtain a thread-local `JNIEnv*`. Existing latent bugs often surface during JDK upgrades because timing, thread scheduling, or GC behavior shifts.

### 22.2. Java Reference Lifetimes vs. Native Pointers

A JNI global reference keeps a Java object alive until explicitly deleted. Raw native pointers do not automatically share lifetimes with Java objects or `MemorySegment`s. Define ownership clearly: who allocates, who frees, and when pointers become invalid.

Never assume a memory-safety bug is "fixed" merely because re-running a test did not crash.

## 23. `-Xcheck:jni` and Diagnosing JNI Contract Violations

HotSpot offers extra JNI checks:

~~~bash
java -Xcheck:jni \
  -Djava.library.path=/opt/app/native \
  -jar app.jar
~~~

`-Xcheck:jni` detects and warns or aborts on invalid JNI usage. It is a **diagnostic tool**, not proof of bug-free code, and adds overhead or changes timing.

Use it in reproducible test/staging runs rather than enabling it indiscriminately on latency-sensitive production nodes.

### 23.1. Native Sanitizers

For first-party C/C++ JNI code, tools like AddressSanitizer (ASan) or UndefinedBehaviorSanitizer (UBSan) detect memory and undefined-behavior bugs when compiled with instrumentation. Pair them with boundary-value tests and native code coverage.

Native sanitizers do not replace JVM linkage diagnostics, and running sanitized binaries inside a JVM process requires compatible toolchains and OS setups. Never assume any compiler flag works out of the box on production images.

## 24. Native Memory Tracking and Memory Leaks

An application may avoid instant crashes yet grow in RSS until the OS OOM-kills the process due to:

- Java heap exhaustion.
- Direct buffers or off-heap native allocations.
- Native thread stacks.
- JIT code cache, class metadata, or GC/JVM internal structures.
- JNI/JNA allocations or third-party native library leaks.
- Agent or telemetry exporter buffers.

With HotSpot Native Memory Tracking (NMT), launch with:

~~~bash
java -XX:NativeMemoryTracking=summary \
  -jar app.jar
~~~

and query via authorized tooling:

~~~bash
jcmd <pid> VM.native_memory summary
~~~

Replace `<pid>` with the actual PID. NMT tracks JVM/HotSpot-accounted regions; **it does not necessarily account for direct `malloc`/native allocations performed inside third-party native libraries**. Thus, clean NMT output never rules out a native library leak.

When investigating container OOM kills, compare container RSS, heap/direct buffers, loaded native libraries, thread counts, and kernel OOM logs. Never blame Java heap leaks merely because JVM process memory climbed.

## 25. Agents and JVMTI Can Transform the Entire Diagnosis

Under "Agents and Native Code," a vital factor is JVM startup with Java or native JVMTI agents:

~~~bash
java -javaagent:/opt/agent/apm.jar \
     -agentpath:/opt/agent/libprofiler.so \
     -jar app.jar
~~~

If the process crashes inside a profiler's native library or an agent's bytecode parser fails on newer class files, the defect sits outside business JNI code even if class loading appears on the stack.

Inventory:

- `-javaagent`, `-agentlib`, and `-agentpath`.
- Agent versions, binary architectures, and vendor JDK support.
- Bundled ASM, Byte Buddy, or native dependencies.
- Java Module System permissions and JVM flags.
- Dynamic attach performed by operational or testing tools.
- Instrumented framework/JDK libraries whose versions changed.

### 25.1. Comparing With vs. Without Agents

In an approved isolated test environment:

1. Run the target artifact/JDK with agents attached and record behavior.
2. Run without agents—or one agent at a time—to isolate variables.
3. Compare startup, memory growth, crash logs, and native frames.
4. Identify which agent introduces the difference.
5. Restore required security/observability configs using compatible agent releases.

Never disable production security or monitoring agents permanently merely because disabling them hides an error. A/B testing isolates causes; final remediation must satisfy operational policy.

## 26. JDK 21 Dynamic Attach Differs from Native Linkage Errors

On JDK 21, JEP 451 emits warnings on dynamic Java agent attachment where applicable. Test mocking or profiling tools can self-attach and produce warnings. This reflects **instrumentation policy**, not:

- Missing `libX.so`.
- Unresolved JNI symbols.
- Java bytecode `NoSuchMethodError`.
- JVM native crashes.

When logs emit dynamic-attach warnings, identify which agent loaded, whether via startup or dynamic attach, and read vendor guidance. Never throw random native libraries or unrelated module flags at it.

If dynamic attach is blocked by policy, verify JVM flags, privileges, and startup `-javaagent` support. Succeeding at attach also does not guarantee the native library or bytecode transformer is compatible.

## 27. FFM API: Does Replacing JNI Eliminate All Native Risks?

The Foreign Function & Memory (FFM) API, finalized in Java 22, lets Java code invoke native libraries and manage off-heap memory without hand-writing JNI C glue in many cases. Yet moving from JNI to FFM **does not erase native compatibility constraints**:

- Native shared libraries must still match OS, architecture, and ABI.
- Exported symbols and function descriptors must align.
- Memory allocation, lifetimes, and thread confinement/ownership require strict management.
- Native access policies on the runtime still apply.
- Confirm JDK versions and differences between preview/incubator vs. finalized FFM APIs.

If targeting Java 17 or 21, examples written for finalized Java 22 FFM will not compile verbatim; verify API availability for your JDK. For JDK 22+ migrations, FFM can be strategic yet still demands tests for native loading, symbol resolution, resource scopes, and performance.

### 27.1. Distinguishing Errors Across the FFM Boundary

With FFM, symbol lookup failures, descriptor mismatches, or lifetime violations raise diagnostics distinct from JNI. Never force them mechanically into `System.loadLibrary` `UnsatisfiedLinkError` runbooks. Inspect foreign call bindings alongside OS loader behavior.

## 28. Diagnostic Flow: Always Start from the First Symptom

~~~mermaid
flowchart TD
  A[Application fails to start or crashes] --> B{hs_err / core / fatal signal present?}
  B -->|Yes| C[Inspect problematic frame, native stack, libraries]
  B -->|No| D{What is the first Throwable?}
  D -->|UnsatisfiedLinkError| E{Library load or native method error?}
  E -->|Load| F[Check files, dependencies, ABI, search paths]
  E -->|Method| G[Check JNI symbols, descriptors, RegisterNatives]
  D -->|NoClassDefFoundError or ClassNotFoundException| H[Check runtime classpath, modules, init cause]
  D -->|NoSuchMethodError or NoSuchFieldError| I[Check Java ABI and dependency graph]
  D -->|UnsupportedClassVersionError| J[Check major version and JVM]
  D -->|Other| K[Inspect root cause and failing layer]
  C --> L[Reproduce with exact JDK, OS, native binary, and agents]
  F --> L
  G --> L
  H --> L
  I --> L
  J --> L
  K --> L
  L --> M[Apply minimal fix and run integration tests]
~~~

This flowchart guides investigation. A class-initialization failure can wrap or mask an earlier native failure; when multiple layers are suspect, reconstruct the **earliest-failure timeline** inside that process.

## 29. Minimum Evidence Set for an Incident Report

An incident record should capture:

~~~text
Incident ID:
First error timestamp:
JDK vendor/version/build:
OS/container image/architecture/libc:
Application artifact/hash:
Java classpath/module path:
Native library paths/versions/checksums:
JNI/JNA/FFM dependency versions:
Startup JVM flags (secrets redacted):
Java agents and JVMTI agents:
Reproduction inputs/steps:
First Java stack trace or fatal error log:
Native loader error text:
Suspected class/method/native symbol:
Baseline working combination:
Target failing combination:
Owner and next diagnostic action:
~~~

Do not paste raw environment blocks, secrets, or unredacted core dumps into tickets. Share only protected, redacted diagnostic excerpts, and handle user-data incidents per security policy.

### 29.1. Preserve the First Error

When multiple threads initialize concurrently and `<clinit>` fails, trailing threads only see `NoClassDefFoundError`. Retain startup/stderr logs from initial process launch rather than only the tail of a crash-restart loop.

## 30. Practical Runbook: Native Library Fails to Load on Linux

Suppose:

~~~text
java.lang.UnsatisfiedLinkError:
  /app/native/libencoder.so: libcodec.so: cannot open shared object file
~~~

The main binary `libencoder.so` was found on path, yet its dependency `libcodec.so` is missing or unresolvable.

### 30.1. Investigation

1. Confirm `libencoder.so` exists inside the **final runtime container**.
2. Inspect architecture and binary type with `file` / `readelf -h`.
3. Inspect `NEEDED` dependencies with `readelf -d`.
4. For trusted binaries, run `ldd` and look for `not found`.
5. Check `RPATH`/`RUNPATH` and dynamic linker configuration.
6. Identify which OS package or artifact should supply `libcodec.so`.
7. Confirm version/ABI match rather than filename match alone.
8. Re-run inside the target container image, not only on a developer workstation.

### 30.2. Remediation Options

Package the matching native dependency into the image, configure loader paths per policy, use binaries compiled for the target ABI, or align the native dependency stack. Never try fixing this by adding unrelated Java JARs or changing `--release`.

### 30.3. Verification

Tests must execute functionality reaching the native library. Tests constructing only Java DTOs may never hit lazy `System.loadLibrary` calls, creating false confidence that native packaging succeeded.

## 31. Practical Runbook: Library Loads Yet `nativeMethod` Fails

Suppose:

~~~text
java.lang.UnsatisfiedLinkError:
  'long example.nativebridge.NativeMath.add(long, long)'
~~~

An earlier version took `int` and returned `int`; the new version uses `long` for larger numbers. If the native library remains old, JNI mangled names or `RegisterNatives` signatures mismatch.

### 31.1. Investigation

1. Inspect the actual runtime Java class with `javap -s -p`.
2. Confirm the active JAR is not an outdated cached build.
3. Regenerate headers with `javac -h` from matching source.
4. Check native exported symbols with `nm` / `dumpbin` for name-based JNI.
5. For `RegisterNatives`, check name/descriptor registration tables.
6. Verify native binary files, checksums, and resolved load paths.
7. Rebuild Java JAR and native binary as a **consistent paired release**.
8. Test boundary values rather than one small input.

### 31.2. Avoid Blindly Casting Java/JNI Types

Changing `long` back to `int` to match an outdated native binary risks integer overflow or altered semantics. Instead, manage compatibility contracts explicitly across Java wrappers and native ABIs. If legacy public Java APIs must persist, write explicit adapters/overloads with range validation.

## 32. Practical Runbook: `NoSuchMethodError` After Framework Changes

Suppose:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.User.getName()'
~~~

The consumer compiled against an older API. Deployment picked another library version where `getName()` changed or disappeared.

### 32.1. Investigation

1. Locate the exact JAR serving `com.example.api.User` at runtime.
2. Check method descriptors via `javap -s`.
3. Inspect the resolved dependency graph, BOMs, and constraints.
4. Inspect classloaders when duplicate JARs appear.
5. Compare old vs. new APIs: parameters, return types, `static`/instance modifiers.
6. Either restore binary-compatible methods/bridges or recompile consumers cleanly.
7. Test the final packaged artifact rather than relying on IDE classpaths.

**Do not waste time checking `LD_LIBRARY_PATH`** when stack traces point to a missing pure-Java method with no native code on the failing path.

## 33. Practical Runbook: Static Initializer Masks the Real Native Error

Class:

~~~java
public final class CryptoEngine {
    static {
        System.loadLibrary("cryptobackend");
    }

    public static byte[] encrypt(byte[] input) {
        // Logic using native backend.
        throw new UnsupportedOperationException("example");
    }
}
~~~

A JVM starts with the native dependency missing.

**First attempt:**

~~~text
java.lang.UnsatisfiedLinkError:
  no cryptobackend in java.library.path
    at java.lang.System.loadLibrary(...)
    at com.example.CryptoEngine.<clinit>(...)
~~~

**Subsequent attempts in the same runtime:**

~~~text
java.lang.NoClassDefFoundError:
  Could not initialize class com.example.CryptoEngine
~~~

Reading only the final log misleads investigators into thinking the Java class vanished from the classpath, whereas the root cause was native loading failing.

Resolution:

1. Preserve startup logs showing the first exception.
2. Trace the `<clinit>` call path.
3. Inspect native search paths and native binary dependencies.
4. Fix deployment packaging/container images.
5. Start a fresh JVM to test rather than expecting the broken class to recover.

## 34. Experimental Matrix When Upgrading JDK and Native Dependencies

To separate JDK effects from native libraries or agents, test combinations systematically:

| Experiment | JDK | Java JARs | Native Libraries | Agent | Purpose |
| --- | --- | --- | --- | --- | --- |
| A | Old JDK | Old graph | Old binary | Old agent | Baseline |
| B | New JDK | Old graph | Old binary | Old agent | See whether new JDK exposes issues directly |
| C | New JDK | Old graph | New binary | Old agent | Isolate native binary changes |
| D | New JDK | New graph | New binary | Old agent | Isolate Java dependency graph changes |
| E | New JDK | New graph | New binary | New agent | Full target stack |
| F | New JDK | New graph | New binary | No agent (staging only) | Isolate instrumentation impact |

Not every matrix cell is valid or supported. For example, new native binaries may require newer `libc`/JDK or old agents may fail on new JDKs; mark **unsupported combinations** rather than running broken pairs and treating crashes as meaningful test data.

### 34.1. Hold Everything Else Constant

When comparing runs, keep OS images, CPU architecture, configs, databases/drivers, input data, and startup flags constant wherever possible. Swapping the JDK and base OS image from glibc to musl simultaneously prevents isolating which change broke native loading.

## 35. When to Upgrade Libraries vs. Change Architecture?

| Investigation Finding | Usually Appropriate Action |
| --- | --- |
| Missing native binary | Package/deploy exact native binary |
| Missing native dependency | Supply compatible native dependency and loader path |
| Wrong OS/CPU/ABI/libc | Select or compile binary matching image |
| JNI signature mismatch | Rebuild JAR and native binary in sync; verify descriptors |
| Native API unmaintained by vendor | Evaluate replacement libraries, pure-Java APIs, or FFM on matching JDK |
| Java `NoSuchMethodError` | Fix dependency resolution and binary compatibility |
| `NoClassDefFoundError` after init fail | Find earliest `<clinit>` cause, potentially native loading |
| Agent/parser fails on new class files | Upgrade agent/tooling per support matrix |
| Native memory corruption / crash | Analyze `hs_err`/core via debuggers/sanitizers; fix native code |
| Dynamic attach blocked by policy | Use startup instrumentation or approved operational mechanism |

Choose the smallest fix addressing the **root cause** without breaking support policies. If a native library is abandoned, temporary flags only buy time while planning migration.

## 36. Investigation and Migration Checklist

- [ ] Captured the **very first exception/fatal error**, not just trailing errors.
- [ ] Separated Java class loading, Java linkage, native loading, and native method binding.
- [ ] Recognized `UnsatisfiedLinkError` as a `LinkageError` subtype.
- [ ] Distinguished `ClassNotFoundException`, `NoClassDefFoundError`, and `<clinit>` failures.
- [ ] Ran `javap -s -verbose` when suspecting Java method descriptors or class-file versions.
- [ ] Checked resolved JARs, runtime classpath/module path, and class loaders.
- [ ] Verified native logical names, absolute paths, and binary checksums.
- [ ] Checked 32/64-bit architecture, OS, libc, and container base images.
- [ ] Audited transitive native dependencies with platform tools.
- [ ] Verified `java.library.path` separately from OS transitive library lookup.
- [ ] Verified `javac -h` headers, exported symbols, or `RegisterNatives` tables.
- [ ] Confirmed Java wrapper JAR and native binary share consistent versions.
- [ ] Preserved `hs_err`/core dumps under security rules when `SIGSEGV`/fatal errors occur.
- [ ] Inspected problematic frames, native stacks, and loaded library lists.
- [ ] Used `-Xcheck:jni` or native sanitizers in test environments when needed.
- [ ] Checked Java/JVMTI agents and bytecode tools when failures hit only on newer JVMs.
- [ ] Confirmed exact JDK vendor/version, OS image, and architecture in production.
- [ ] Executed functional tests **exercising real native paths**, not just startup checks.
- [ ] Built an A/B matrix separating JDK, Java dependencies, native binaries, and agents.
- [ ] Confirmed fixes do not rely on relaxing security permissions blindly.
- [ ] Obtained owner approval on rollout, canary, and rollback/roll-forward plans.
- [ ] Kept incident tickets free of secrets, raw core dumps, and unauthorized sensitive data.

## 37. Common Misconceptions

**"`UnsatisfiedLinkError` is not a `LinkageError`."** False. It subclasses `LinkageError`, yet its root causes typically stem from native loading or binding.

**"If the DLL/SO exists, the native method will work."** False. The binary may mismatch ABI, miss transitive dependencies, lack exported symbols, misconfigure registration, or hit classloader conflicts.

**"Just add the folder to `java.library.path`."** Insufficient when the OS dynamic loader lacks transitive native dependencies or the binary has the wrong architecture.

**"`NoClassDefFoundError` always means a missing JAR."** False. Earlier class initialization may have failed due to native errors.

**"`ClassNotFoundException` and `NoClassDefFoundError` are identical."** False. They belong to different checked/error hierarchies and signal different failure mechanisms.

**"`NoSuchMethodError` requires fixing JNI."** Wrong when stack traces point to a pure-Java method ABI mismatch. Check resolved JARs and descriptors instead.

**"Java 21 runs Java 17 class files so native code is automatically compatible."** False. Native binaries also depend on ABI, libc, OS, JDK integration, and bundled dependencies.

**"`UnsupportedClassVersionError` and `wrong ELF class` share the same cause."** False. One is Java bytecode class-file version; the other is ELF native architecture.

**"`try/catch Throwable` catches every JNI crash."** False. Native fatal signals kill the entire JVM process.

**"`hs_err_pid` proves a JVM bug."** Not necessarily. Problematic frames often sit inside JNI/native libraries, agents, or platform libraries.

**"`ldd` is safe to run on any downloaded file."** Unsafe. Evaluate binary provenance and prefer static inspection tools on untrusted binaries.

**"`-Xcheck:jni` reporting nothing means zero memory bugs."** False. It catches selected JNI contract violations, not every native memory-safety defect.

**"NMT shows every third-party native allocation."** Not guaranteed.

**"Disabling the agent is a valid production fix."** Never when agents serve mandatory security, observability, or quality policies. Use A/B staging to isolate and upgrade properly.

**"Replacing JNI with FFM eliminates all native issues."** False. Shared libraries, ABIs, symbols, and memory lifetimes still require careful engineering.

## 38. Reference Documentation for Live Investigations

Technical references aligned to your deployed JDK and OS:

- **Java SE API — `UnsatisfiedLinkError`, `LinkageError`, `NoClassDefFoundError`, and `ClassNotFoundException`:** error distinctions.
- **Java Virtual Machine Specification:** class loading, linking, initialization, method/field resolution, and class-file formats.
- **Java Native Interface Specification:** name resolution, JNI types, `JNIEnv`, `RegisterNatives`, and library lifecycles.
- **`javac` and `javap` tool guides:** `javac -h`, method descriptors, and class-file versions.
- **JDK Troubleshooting Guide and HotSpot Fatal Error Log docs:** `hs_err_pid`, native crashes, and core dumps.
- **HotSpot `-Xcheck:jni` and Native Memory Tracking documentation:** diagnosing JNI and native memory.
- **Linux dynamic linker / ELF documentation:** `readelf`, `ldd`, `RPATH`/`RUNPATH`, and symbol resolution.
- **macOS dynamic loader / Mach-O documentation:** `otool`, install names, and `@rpath`.
- **Microsoft PE/DLL loading documentation:** search paths, runtime/architecture, and debug symbols.
- **Java Instrumentation / JVMTI and agent vendor documentation:** class loading and Java/native agent JDK support.
- **FFM API documentation on supporting JDKs:** foreign symbol lookups, descriptors, and memory lifetimes when migrating off JNI.

JDK releases, vendors, libc, container images, and native toolchains all shift failure symptoms; check exact release documentation rather than copying assumptions blindly across environments.

## 39. Conclusion

In Java Advance Compatibility Migration, **native errors** and **Java class linkage errors** can surface side by side while requiring completely different investigations. `UnsatisfiedLinkError` normally leads to native search paths, ABIs, native dependencies, and JNI symbol binding; `NoSuchMethodError` or `NoSuchFieldError` leads to Java descriptors and resolved JARs; `NoClassDefFoundError` may signal missing classes or earlier `<clinit>` failures. Fatal JVM crashes require `hs_err_pid`, native frames, or core dumps rather than Java stack traces alone.

A dependable approach is **capturing the earliest error, isolating the failing layer, recording the exact runtime environment, aligning Java/JNI/native artifacts by version, and reproducing via a controlled matrix**. Whenever Java agents or native JVMTI agents are present, include agents, bytecode parsers, module access, and container architecture together in compatibility checks. Once root causes are verified and fixed at the right layer, upgrading to newer JDKs proceeds safely rather than shifting failures from one exception to another.

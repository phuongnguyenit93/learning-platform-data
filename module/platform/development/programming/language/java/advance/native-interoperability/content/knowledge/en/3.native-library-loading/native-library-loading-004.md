# Distinguishing Primary Library Lookup from OS Dynamic Dependency Lookup When Java Loads a Native Library

## 1. The Distinction to Make

When a Java application calls `System.loadLibrary("bridge")`, two things happen in sequence:

1. **Finding the primary library (top-level/native library):** Java/JVM locates the library requested by the Java code, for example `libbridge.so` (Linux), `bridge.dll` (Windows), or `libbridge.dylib` (macOS). This is the part that `java.library.path`, `System.loadLibrary`, `System.load`, and sometimes `ClassLoader.findLibrary` directly involve.
2. **Finding dynamic dependencies (transitive/native dependencies):** the **operating system's** dynamic linker/loader must locate and load the libraries that `libbridge.so`/`bridge.dll`/`libbridge.dylib` needs, such as `libadder.so`. These dependencies reside in the library's native metadata (e.g., ELF `DT_NEEDED`, Mach-O load commands, PE import table) and are resolved according to the specific rules of Linux/macOS/Windows.

The two steps have **different sets of search rules**. The fact that Java finds the primary library **does not guarantee** that the operating system can find all of that library's dependencies.

For example:

```text
Java: System.loadLibrary("bridge")
            │
            ▼  [Step 1: Java/JVM finds the primary library]
       /opt/app/native/libbridge.so
            │
            ▼  [Step 2: Linux dynamic loader reads DT_NEEDED]
       needs: libadder.so
            │
          ┌─┴───────────────┐
          ▼                 ▼
   libadder.so found      not found
          │                 │
          ▼                 ▼
   load and link          loading libbridge.so fails
          │                 │
          ▼                 ▼
   JNI can run            UnsatisfiedLinkError
```

**Key question when debugging:** “Was the library requested by Java not found, or was that library found but the operating system could not find a library that it needs?”

## 2. Step 1: Java/JVM Finds the Primary Library

### `System.loadLibrary(String libname)`

`System.loadLibrary("bridge")` takes a **logical name**, not a filename with a prefix/suffix or a path. Java/JVM typically maps that name to a platform-appropriate native name:

| Platform | Logical name | Common filename |
| --- | --- | --- |
| Linux | `bridge` | `libbridge.so` |
| macOS | `bridge` | `libbridge.dylib` |
| Windows | `bridge` | `bridge.dll` |

You can observe the mapping rule on the running platform using `System.mapLibraryName("bridge")`. This is the name of the requested **primary** library; it does not tell you the names or locations of the library's dependencies.

For a program running on a standard JVM, `java.library.path` is the property containing the directories the JVM uses to search for native libraries by name. Set it at **Java startup**:

```bash
java -Djava.library.path=/opt/app/native -cp app.jar com.example.Main
```

In this example, Java searches for `bridge` via the JVM mechanism, with the directory `/opt/app/native` specified. `-Djava.library.path=...` must appear **before the main class name or `-jar`**; paths are separated by the OS-dependent character (`:` on Linux/macOS, `;` on Windows). Java modules and custom ClassLoaders can introduce additional search rules into this flow; therefore, understand `java.library.path` as an **input to Java's native library lookup mechanism**, not a unified linker rule across all operating systems.

### `System.load(String filename)`

`System.load("/opt/app/native/libbridge.so")` (for the Linux example) takes an **absolute path** to the primary library, thus bypassing the logical name lookup step in `java.library.path`. However, **step 2 still remains**: if `libbridge.so` needs `libadder.so`, passing an absolute path to `System.load` **does not automatically provide the path to `libadder.so`**.

Avoid confusion:

- `java.class.path`/`-cp` searches for **Java classes/JARs**; it is not a search path for `.so`/`.dll`.
- `java.library.path` serves the lookup mechanism for the **primary native library** requested by Java.
- `System.load` specifies the primary library target by path; it does not replace the OS's dependency resolution logic.
- `System.setProperty("java.library.path", "...")` after the program is already running is **not a reliable way** to change the load search path already initialized or cached by the JVM. Configure it at startup or use `System.load` with a deterministic path.

## 3. Step 2: The Operating System's Dynamic Linker/Loader Finds Dependencies

After the JVM has identified a library and handed loading off to the OS native API, the **dynamic linker/loader** reads the dependency references in the binary:

- **Linux (ELF):** `DT_NEEDED` contains the names of dependent shared objects. `ld.so`/`ld-linux` handles lookup and linking.
- **macOS (Mach-O):** library load commands and *install names* determine the libraries to load; `dyld` handles paths such as `@loader_path`, `@rpath`, etc.
- **Windows (PE):** the import table and the DLL loader mechanism determine dependent DLLs. Search order depends on process configuration, DLL policies, and how `LoadLibrary`/`LoadLibraryEx` is called.

A dependency can in turn need **its own dependencies**. Success in step 1 does not mean the entire dependency tree is valid, matches the architecture, matches the ABI, or has been loaded.

### Search Paths on Linux (glibc, ELF)

When a dependency name such as `libadder.so` does not carry a specific path, the linker consults multiple sources according to ELF/`ld.so` rules, including:

1. Legacy `DT_RPATH` on the relevant object, if there is no corresponding `DT_RUNPATH` (order and scope are specifically defined).
2. The `LD_LIBRARY_PATH` environment variable provided **before the process runs** (there are security modes such as *secure execution* where this variable is ignored).
3. `DT_RUNPATH` embedded in the object that needs the dependency, applying to **direct dependencies** in that object's `DT_NEEDED`; deeper transitive dependencies must have their own appropriate search paths.
4. The `/etc/ld.so.cache` cache and default system library directories (which can vary by distro, architecture, and configuration).

A very useful RUNPATH value when packaging libraries side by side:

```text
RUNPATH = $ORIGIN
```

In ELF, `$ORIGIN` is expanded by the loader to the **directory containing the referencing ELF file itself**, rather than defaulting to the current working directory. As a result, `libbridge.so` can find `libadder.so` placed next to it without needing to place the libraries in system directories.

**Common pitfall:** placing `libbridge.so` and `libadder.so` in the same directory, and then only adding that directory to `-Djava.library.path`, **does not by default** make the Linux dynamic linker search there for dependencies. The Linux mechanism generally does not automatically search the directory of the just-loaded object if `RUNPATH`/`RPATH` or a corresponding OS search path is missing.

### Search Paths on macOS (dyld, Mach-O)

Libraries typically carry an *install name* and references containing:

- `@loader_path`: the directory of the binary/image containing that reference.
- `@executable_path`: the directory containing the main executable.
- `@rpath`: resolved according to the appropriate *runpaths* embedded in the object/load chain.

You can inspect dependency references with `otool -L libbridge.dylib` and check `LC_RPATH` with `otool -l`. The `DYLD_LIBRARY_PATH` variable can affect lookup in some environments, but macOS protections such as SIP, hardened runtime, or launch methods can restrict or strip `DYLD_*` environment variables. In distributed applications, prefer properly packaged and signed install names/runpaths rather than relying on environment variables.

### Search Paths on Windows (DLL loader, PE)

`bridge.dll` can declare a dependency on `adder.dll`. Even if an application uses a **full path** to load `bridge.dll`, Windows can still search for `adder.dll` **by module name** based on the process's DLL search policy.

The search path is not just "the directory next to the primary DLL": depending on the application type and how it is loaded, Windows may check the application directory (`java.exe` or the application executable), system directories, current directory, `PATH`, already-loaded DLLs, Known DLLs, manifest/SxS, package graph, or directories set via API. The order and set of directories vary with **Safe DLL Search Mode** and `LoadLibraryEx`/`LOAD_LIBRARY_SEARCH_*` flags. For example, `LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR` can include the directory containing the DLL being loaded in the search for **dependencies**, but one cannot assume every DLL load call uses that flag.

Therefore, adding a path to `-Djava.library.path` may help Java find `bridge.dll` without **fixing** Windows failing to find `adder.dll`. When diagnosing, inspect the import table with `dumpbin /DEPENDENTS bridge.dll` (Visual Studio Developer Command Prompt) and check the actual DLL search policy of the process. For production applications, use controlled library locations and safe search mechanisms; do not arbitrarily add untrusted directories to `PATH`.

## 4. Linux Experiment: Primary Library Found, Dependency Missing

This is a complete JNI example on **Linux x86-64 or a compatible Linux architecture**, with JDK 17+ and GCC. We intentionally create **two libraries**:

```text
NativeProbe.java
    │ System.loadLibrary("bridge")
    ▼
libbridge.so           ← primary JNI library
    │ DT_NEEDED
    ▼
libadder.so            ← native dependency
    │
    ▼
int add_in_c(int, int)
```

### Step A — Write the Java Code

File `NativeProbe.java`:

```java
public final class NativeProbe {
    static {
        System.loadLibrary("bridge");
    }

    private static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println("7 + 5 = " + add(7, 5));
    }
}
```

Compile Java and generate the JNI header at the same time:

```bash
javac -h . NativeProbe.java
```

The command generates `NativeProbe.class` and `NativeProbe.h`. `NativeProbe` is in the default package, so the JNI symbol has the form `Java_NativeProbe_add`.

### Step B — Write the Dependency `libadder.so`

File `adder.c`:

```c
int add_in_c(int a, int b) {
    return a + b;
}
```

Compile into a Linux shared library with an explicit SONAME:

```bash
gcc -fPIC -shared -Wl,-soname,libadder.so \
    -o libadder.so adder.c
```

### Step C — Write the Primary JNI Library `libbridge.so`

File `bridge.c`:

```c
#include <jni.h>
#include "NativeProbe.h"

extern int add_in_c(int a, int b);

JNIEXPORT jint JNICALL Java_NativeProbe_add(
        JNIEnv *env, jclass clazz, jint a, jint b) {
    (void) env;
    (void) clazz;
    return (jint) add_in_c((int) a, (int) b);
}
```

Compile `libbridge.so` and link it against `libadder.so`, **without configuring RUNPATH yet**:

```bash
gcc -fPIC -shared \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    -L. -o libbridge.so bridge.c -ladder
```

`JAVA_HOME` must point to the JDK directory containing `include/jni.h`; GCC must be in `PATH`. The order `bridge.c -ladder` lets the linker find the needed `add_in_c` symbol. Inspect the metadata of the **primary library**:

```bash
readelf -d libbridge.so | grep NEEDED
```

An important line in the output will contain:

```text
Shared library: [libadder.so]
```

That is a **dependency of `libbridge.so`**, not the library passed to `System.loadLibrary`. The `readelf` output may include additional `NEEDED` entries depending on how it was compiled.

### Step D — Intentionally Specify Only the Primary Library Search Path

Standing in the directory containing the three source files, the compiled files, and the two shared libraries, run:

```bash
env -u LD_LIBRARY_PATH \
    java -Djava.library.path="$PWD" NativeProbe
```

We have provided the exact **primary** path: Java can find `libbridge.so` in `java.library.path`. If `libadder.so` is not installed in a system directory, has no `RUNPATH`, and has no other OS configuration helping locate it, the program **typically fails** with a cause similar to:

```text
java.lang.UnsatisfiedLinkError: ... libadder.so: cannot open shared object file: No such file or directory
```

The `...` here merely omits paths/stack traces that can vary by JDK and distro; it is an **illustrative error pattern**, not a claim that the stderr line will be identical. What is noteworthy is that **`libadder.so`**, not `libbridge.so`, is reported missing.

If the machine already has `libadder.so` in a location searched by the OS, step D may succeed; reproducing the failure requires a clean test environment and a library name that does not collide with an installed version.

### Step E — Fix Using the OS Search Path (Experimental)

On Linux, pass `LD_LIBRARY_PATH` to the **Java process at startup**:

```bash
LD_LIBRARY_PATH="$PWD" \
    java -Djava.library.path="$PWD" NativeProbe
```

**stdout when loading and linking succeed:**

```text
7 + 5 = 12
```

The command succeeds because the two settings solve **the two steps**: `-Djava.library.path` helps the JVM locate `libbridge.so`, while `LD_LIBRARY_PATH` gives the dynamic linker a location containing `libadder.so`. This is a useful way to prove the cause during development; one should not default to exporting arbitrary directories into `LD_LIBRARY_PATH` on all production machines.

### Step F — A More Durable Packaging Approach with `$ORIGIN`/RUNPATH

Instead of relying on environment variables, rebuild **`libbridge.so` itself** with a GNU linker RUNPATH pointing to its containing directory:

```bash
gcc -fPIC -shared \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    -L. -Wl,--enable-new-dtags -Wl,-rpath,'$ORIGIN' \
    -o libbridge.so bridge.c -ladder
```

Inspect `DT_NEEDED` and `RUNPATH` of the linked library:

```bash
readelf -d libbridge.so | grep -E 'NEEDED|RUNPATH|RPATH'
```

Expected essential information includes:

```text
Shared library: [libadder.so]
Library runpath: [$ORIGIN]
```

Now you can omit the environment variable and still load the dependency placed next to the primary library:

```bash
env -u LD_LIBRARY_PATH \
    java -Djava.library.path="$PWD" NativeProbe
```

**stdout:**

```text
7 + 5 = 12
```

`$ORIGIN` is a token expanded by the dynamic linker; write `-Wl,-rpath,'$ORIGIN'` with **single quotes** so the shell does not expand `$ORIGIN` as a shell environment variable. `-Wl,--enable-new-dtags` instructs the GNU linker to emit the new tag style (typically `DT_RUNPATH`). The `RUNPATH` rule applies only to **direct** dependencies of the object containing the tag; if `libadder.so` also depends on another library placed elsewhere, the next-level search path must be resolved accordingly.

### The Error Story in the Experiment

- If you delete/rename `libbridge.so` or specify the wrong `java.library.path`, Java cannot find the primary library: you typically see `no bridge in java.library.path`.
- If `libbridge.so` exists but `libadder.so` is not in the OS search path, the JVM has passed the primary library selection step, but **the OS loader did not complete loading**: you typically see the name `libadder.so` in `UnsatisfiedLinkError`.
- If both are found, other conditions such as architecture, ABI, symbol exports, and JNI method binding must still be right. Both lookup steps succeeding is **not sufficient** to guarantee all native methods will work.

JDK version note: on newer JDKs with stricter **native access** policies, classpath code using `System.loadLibrary` may need the `--enable-native-access=ALL-UNNAMED` argument (or declaring native access per module) if the runtime warns/blocks. The example above uses traditional JNI and describes the outcome when native access permission is granted.

## 5. Quick Comparison Table

| Question | Primary library lookup | Native dependency lookup |
| --- | --- | --- |
| Who initiates it? | Java calls `System.loadLibrary`/`System.load`, or a Java library makes the call | Native loader reads import/dependency metadata from the binary |
| Name being searched | `bridge` → `libbridge.so`/`bridge.dll`/`libbridge.dylib` | `libadder.so`/`adder.dll`/`libadder.dylib` and subsequent dependent libraries |
| Responsible component | JVM/ClassLoader/native loading mechanism | `ld.so` (Linux), `dyld` (macOS), Windows DLL loader |
| Main search path/location | `java.library.path` for `loadLibrary`, or absolute path for `load` | `LD_LIBRARY_PATH`/RUNPATH on Linux; install names/`@rpath` on macOS; DLL search policy on Windows |
| Observation tools | `System.mapLibraryName`, `System.getProperty("java.library.path")`, JVM error messages | `readelf`/`LD_DEBUG` (Linux), `otool` (macOS), `dumpbin` and loader tools (Windows) |
| Typical error | “no bridge in java.library.path” | “libadder.so cannot open”, “adder.dll was not found”, missing symbol/ABI mismatch |
| How to fix | Specify the correct name, directory, or absolute path of the primary lib | Package all dependencies and configure platform-appropriate native search paths |

## 6. Troubleshooting Workflow in Real Projects

**Step 1 — Read the exact error and identify the missing library name.**

- `UnsatisfiedLinkError: no bridge in java.library.path` usually indicates the **primary library** could not be located by logical name.
- `UnsatisfiedLinkError: ... libadder.so: cannot open shared object file` usually indicates a **dependency** was requested by the OS linker but not found.
- `wrong ELF class`, `bad CPU type`, `%1 is not a valid Win32 application`, or similar: the library exists, but **its format/architecture is invalid**.
- `undefined symbol`, `symbol not found`, or versioned symbol errors: the library exists, but **it does not satisfy symbols/ABI**.
- `java.lang.UnsatisfiedLinkError: ... native method ...` when calling a JNI method can also be a **wrong JNI symbol name/signature**, distinct from library path lookup.

`UnsatisfiedLinkError` is an **error category**; it does not by itself state whether it is step 1 or step 2. You must rely on the library name and details from the loader.

**Step 2 — Check the primary library with Java.**

- Print `System.mapLibraryName("bridge")` to see the expected filename on the current OS.
- Print `System.getProperty("java.library.path")` or check the `-D` option at startup.
- With `System.load`, check the **absolute** path, file permissions, architecture, and binary type.
- Ensure `-Djava.library.path` is placed before the main class name in the launch command and that the JVM/IDE/container environment is actually using that value.

**Step 3 — List native dependencies.**

```bash
# Linux: list DT_NEEDED / DT_RUNPATH / DT_RPATH declarations
readelf -d /opt/app/native/libbridge.so | grep -E 'NEEDED|RUNPATH|RPATH'

# Linux: ask the dynamic linker where it actually looks for libraries (very long output)
LD_DEBUG=libs java -Djava.library.path=/opt/app/native -cp app.jar com.example.Main
```

For trusted binaries, `ldd libbridge.so` is also useful to spot “not found” libraries; avoid running `ldd` casually on untrusted binaries because in some situations it can cause code execution.

```bash
# macOS: referenced libraries and runpath metadata
otool -L libbridge.dylib
otool -l libbridge.dylib
```

```bat
rem Windows, in Visual Studio Developer Command Prompt
dumpbin /DEPENDENTS bridge.dll
```

On Windows, ProcMon or an appropriate dependency analysis tool can also help show the paths the process attempts to access; the static import list does not always show every library dynamically loaded via `LoadLibrary`.

**Step 4 — Verify matching architecture, ABI, and permissions.**

Check 32/64-bit, CPU architecture, glibc/Visual C++ runtime, version/SO name, exported symbols, nested dependencies, and OS library loading restrictions (file permissions, sandbox, code signing). A file “existing” does not guarantee “the loader can use it”.

**Step 5 — Choose a reasonable fix for the deployment target.**

- **Dev/Test:** configure `java.library.path` for the primary library; adjust the OS search path (`LD_LIBRARY_PATH` or equivalent environment) to quickly pinpoint the cause.
- **Linux production:** package the primary/dependent libs at the right versions and use relative `RUNPATH` `$ORIGIN` when appropriate; remember each dependency level needs its own search path.
- **macOS production:** bundle Mach-O dependencies with proper `@loader_path`/`@rpath` and satisfy macOS signing and packaging requirements.
- **Windows production:** place DLLs in a directory searched by the loader under the actual policy or configure safe DLL search APIs; avoid relying on system-wide `PATH` containing uncontrolled directories.
- **CI/Docker/Service:** pass both the Java property and the OS environment completely at startup, matching OS/CPU; do not just check that files are present in the source tree.

## 7. Misconceptions to Avoid

1. **“Adding `-Djava.library.path` makes the OS automatically find all dependent DLLs/`.so`s.”** False. This property serves Java's library loading mechanism; the native loader has its own rules.
2. **“`System.load` with an absolute path guarantees all dependencies are resolved.”** False. It locates the primary library; dependencies still must be resolved by the OS loader.
3. **“Two `.so` files sitting next to each other means Linux will always load them.”** False. An appropriate loader search path is needed, such as `RUNPATH=$ORIGIN`.
4. **“Windows always searches for dependencies right next to the loaded DLL.”** You cannot assume that; search mode and load flags have an effect.
5. **“`LD_LIBRARY_PATH` and `java.library.path` are the same thing.”** False. One is a Linux dynamic loader environment variable, the other is a Java system property.
6. **“If Java finds the file, JNI is guaranteed to be callable.”** False. Architecture, symbol exports, ABI, access policy, and JNI signature can still be wrong.
7. **“Adding every directory to PATH/LD_LIBRARY_PATH is the best fix.”** That approach can cause version conflicts and library preloading risks. Prefer explicit packaging, trusted directories, and scoped loading mechanisms.

## 8. Self-Check Exercises

**Scenario A:** `libbridge.so` is in `/srv/app/native`, Java runs with `-Djava.library.path=/srv/app/native`, and the error reports `libhelper.so: cannot open shared object file`. Which step are you at? **Step 2**: Java has gone far enough to load the primary library, but the OS has not found the dependency `libhelper.so`. Check `DT_NEEDED` and `RUNPATH`, not just changing `java.library.path`.

**Scenario B:** The application uses `System.load("/srv/app/native/libbridge.so")` but still reports `libhelper.so` is missing. Is there a contradiction? **No**: the absolute path only applies to `libbridge.so`; check the loader mechanism for dependencies.

**Scenario C:** Two `.so` files sit side by side and work when `LD_LIBRARY_PATH` is set, but fail when run as a service. Why? The interactive shell may have environment variables configured that the service does not receive; or an appropriate `RUNPATH` is missing. Compare the environment at startup and the ELF metadata, avoiding the assumption that every launch method uses the same variables.

## Official Documentation and Reference Sources

- [Java SE — `System.load` / `System.loadLibrary`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [JNI Specification — Loading and Linking Native Methods](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Linux `ld.so(8)`: dependency lookup, RPATH/RUNPATH, `$ORIGIN`](https://man7.org/linux/man-pages/man8/ld.so.8.html)
- [Linux `dlopen(3)`: shared object search order](https://man7.org/linux/man-pages/man3/dlopen.3.html)
- [Apple — Run-Path Dependent Libraries](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/100-Articles/RunpathDependentLibraries.html)
- [Microsoft — Dynamic-link library search order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)
- [Microsoft — Dynamic-link library security](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-security)

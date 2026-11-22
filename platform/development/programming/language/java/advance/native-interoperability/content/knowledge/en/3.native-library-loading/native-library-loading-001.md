# Dynamic Libraries .dll, .so, .dylib and the Architecture of the Java Process

## 1. What are dynamic libraries and why does Java need them?

A typical Java program compiles `.java` source code into `.class` bytecode, and then the JVM loads the classes, verifies the bytecode, and executes it using the interpreter/JIT. However, some functionality requires machine code native to the operating system or hardware: calling C/C++ libraries, drivers, OS APIs, existing native algorithms, or integrating with other software. In those cases, Java can call a **dynamic/shared library** through a mechanism for linking with native code, typically **JNI (Java Native Interface)**.

A dynamic library is a machine-code file that can be mapped by the operating system's library loader into the address space of a running process. Unlike a `.jar` containing Java classes/bytecode, a native file is compiled for **a specific operating system, CPU architecture, and ABI**. Renaming a `.so` extension to `.dll` cannot turn Linux code into Windows code.

A few things to distinguish right away:

- **JAR**: where Java classes/resources are packaged; the JVM/class loader understands its structure and bytecode.
- **Dynamic library**: machine code and native symbols; the **OS dynamic loader** loads it, and then the JVM or native bridge uses it.
- **JNI**: the contract between Java and native code, including data types like `jint`, the `JNIEnv` object, function names/method registration, and how data is passed.
- **Java process**: the operating system process hosting the JVM. Native libraries are loaded into **this exact process**, not automatically into a separate process.

## 2. Three common formats: DLL, SO, and DYLIB

| Operating System | Common Binary Format | Dynamic Library Extension | Example Name for Logical Library `nativecalc` | Notes |
|---|---|---|---|---|
| Windows | PE/COFF | `.dll` | `nativecalc.dll` | The Windows loader resolves the DLL and dependent DLLs. |
| Linux | ELF | `.so`, sometimes with a version like `.so.1` | `libnativecalc.so` | `ld.so`/dynamic linker handles `DT_NEEDED`, `SONAME`, and library search paths. |
| macOS | Mach-O | `.dylib` | `libnativecalc.dylib` | `dyld` resolves libraries; `@rpath`, `@loader_path`, and `@executable_path` are commonly used. |

The names in the table are **typical conventions**; a library may have a different name, version, and symlinks. Java provides `System.mapLibraryName("nativecalc")` to obtain the platform-specific native filename, but finding a file with a matching name does not guarantee it is compatible or that all dependencies exist.

**Compiling differs from loading:** the compiler/linker produces a library with a specific format and ABI; when the program runs, the OS loader maps the library into the process and resolves dependencies. On Linux, `libfoo.so` is often the name used for linking or loading, while the actual runtime file may carry a version (`libfoo.so.2`). On macOS, a library may contain multiple *architecture slices* (universal binary), but it still must have a slice compatible with the process.

## 3. Where does the library reside in the Java process architecture?

Conceptual diagram (regions are not necessarily contiguous or fixed in size):

~~~text
Operating System
└── "java" Process (one PID, one virtual address space)
    ├── JVM/HotSpot runtime
    │   ├── Java heap (Java objects)
    │   ├── Metaspace, code cache/JIT, and JVM structures
    │   └── Java threads and associated stacks
    ├── Native memory, native stacks, OS resources
    ├── System libraries used by the process
    └── Application native library
        ├── nativecalc.dll        (Windows) OR
        ├── libnativecalc.so      (Linux)   OR
        └── libnativecalc.dylib   (macOS)
~~~

When Java calls a `native` method:

1. The Java execution thread crosses the JNI boundary (or corresponding native interop mechanism).
2. The JVM passes arguments according to the JNI contract and transfers control to the machine-code function mapped in the **same process**.
3. The native function can use the CPU, native memory, OS APIs, or call further into other libraries.
4. The function returns a result/exception according to the bridge protocol; the thread resumes executing Java code.

A shared library does not mean memory is automatically shared between **processes**. Each process has its own virtual address space; the operating system may share read-only code pages at the physical level, but a memory pointer from one process cannot be arbitrarily used in another process.

**A very important safety consequence:** native code is not protected by the JVM like Java bytecode. Invalid pointer access, buffer overflows, synchronization bugs, or ABI mismatches can crash the **entire Java process** (e.g., SIGSEGV/Access Violation). The Java GC manages Java objects, but does not automatically free memory allocated by C/C++.

## 4. "Right operating system" is not enough: CPU, bitness, ABI, and dependencies

A library can only be loaded successfully when **the OS loader and the process** understand that binary.

| Factor | Needs to match / be checked | Typical error |
|---|---|---|
| Operating system and format | Windows/PE, Linux/ELF, macOS/Mach-O | Moving a Windows `.dll` to Linux without a compatibility environment cannot be loaded as a `.so`. |
| CPU instruction architecture (ISA) | `x86_64`/`amd64`, `aarch64`/`arm64`, `x86`… | An ARM64 JVM cannot load a library containing only x86_64 machine code normally. |
| Process bitness | A 64-bit JVM requires a 64-bit native library of the right architecture | A 64-bit JVM cannot directly load a 32-bit DLL/SO. |
| ABI and symbols | Calling convention, exported function names, data types, C/C++ runtime, JNI signature | `undefined symbol` or native method not found even though the file was found. |
| Dependent libraries | `libc`, C++ runtime, other DLL/SO/DYLIBs, compatible versions | Main file exists, but the loader reports a missing dependency or version. |
| Environment constraints | OS version, code signing policies/permissions, loader paths | Loading is blocked even though the path and architecture are correct. |

For example: a 64-bit Linux machine being able to run 32-bit applications if supported does not mean a **64-bit JVM** can load a 32-bit `libfoo.so`. The library is loaded *into the current JVM process*, so it must be compatible with the process's architecture/ABI, not just the physical CPU. On Apple Silicon macOS, you need to check whether the JVM is running the arm64 or x86_64 build (via compatibility translation) and choose the matching slice.

ABI (Application Binary Interface) defines how arguments are passed, return values, data layout, and calling conventions at the machine level. The same function name and the same C/C++ source code do not necessarily produce interchangeable binaries across different systems. C++ also has *name mangling* and compiler-specific ABI differences; when building a JNI bridge, you should rely on the header generated by `javac -h` to declare symbols correctly.

## 5. The loading process from Java to the OS loader

With JNI and a call to `System.loadLibrary("nativecalc")`, the sequence can be pictured as follows:

1. The JVM executes the load command when the corresponding class initializes (if placed in a `static` block) or when the application calls it explicitly.
2. The JVM's native loading mechanism searches for a candidate by logical name and appropriate search paths (`java.library.path`, along with JVM/OS-specific rules).
3. The OS loader checks the binary format, architecture, and permissions; maps the code/data segments and handles relocations, dependencies, and symbols as needed. Some symbols may be bound lazily.
4. If a `JNI_OnLoad` function is present, the JVM may call it per the JNI contract for initialization/registration. **This function is optional**; not every JNI library needs it.
5. The JVM binds the `native` method in Java to the corresponding entry point (by JNI naming rules or `RegisterNatives`). After that, Java calls can transfer into native code.

Here are the two common loading calls:

~~~java
System.loadLibrary("nativecalc");  // Logical name, WITHOUT lib/.dll/.so/.dylib
System.load("/absolute/path/to/libnativecalc.so"); // Absolute path to the file
~~~

The lines above **illustrate the API**, not a standalone program, and the `System.load` path is a Unix-style example. `System.loadLibrary` does not accept an arbitrary file path like `./libnativecalc.so`; `System.load` takes a full filename via an absolute path. Both can fail if a dependent library is not found.

**Distinguish between two path layers:**

- `java.library.path` helps **the JVM find the initial JNI library** using the JVM's mechanism. Specify it at startup, for example `java -Djava.library.path=/opt/app/native ...`. Do not rely on `System.setProperty("java.library.path", ...)` after the JVM has started to change the search mechanism.
- **The OS loader's dependency search path** may be different: `PATH` and Windows DLL search rules; `LD_LIBRARY_PATH`, `RUNPATH`/`RPATH`, and loader cache on Linux; `@rpath`/`@loader_path` and `dyld` policies on macOS. `java.library.path` does not automatically resolve all nested dependent libraries.

When deploying, prefer placing libraries in a clear location and configuring search paths in a controlled way. On Windows, pay attention to the DLL search order to avoid loading the wrong file with the same name; on macOS, some `DYLD_*` environment variables may be restricted by security policies (such as SIP), so do not treat them as a universal solution.

## 6. Hands-on JNI: Java calling an addition function in a native library

This example demonstrates the full **Java → JNI → C → Java** path, running on Java 17+ with a **JDK**, a suitable C compiler, and a library compiled **on the same platform being run**. Create both files in the same directory, without a `package` declaration so the JNI name is easy to observe.

**Step 1 — `NativeCalc.java`:**

~~~java
public class NativeCalc {
    static {
        System.loadLibrary("nativecalc");
    }

    private native int add(int left, int right);

    public static void main(String[] args) {
        NativeCalc calculator = new NativeCalc();
        System.out.println("3 + 4 = " + calculator.add(3, 4));
    }
}
~~~

The `native` keyword declares a method implemented by code outside the JVM. The `static` block requests loading the library when `NativeCalc` is initialized; if loading fails, the program will not reach the `add` call.

**Step 2 — Generate the JNI header from the JDK:**

~~~bash
javac -h . NativeCalc.java
~~~

This command creates `NativeCalc.class` and `NativeCalc.h`. The generated header declares a function corresponding to the instance method `add(int, int)`, conceptually shaped like:

~~~c
JNIEXPORT jint JNICALL Java_NativeCalc_add(
    JNIEnv *, jobject, jint, jint
);
~~~

`JNIEnv *` is the JNI interface for the calling thread, `jobject` represents the `this` object, and the two `jint`s are the Java `int` arguments. If the method were changed to `static native`, the second reference parameter would be `jclass` instead of `jobject`.

**Step 3 — `nativecalc.c` (C code):**

~~~c
#include "NativeCalc.h"

JNIEXPORT jint JNICALL Java_NativeCalc_add(
    JNIEnv *env, jobject receiver, jint left, jint right
) {
    (void) env;
    (void) receiver;
    return left + right;
}
~~~

The function name and types must follow the header generated by the JDK; do not arbitrarily alter the signature by guesswork. This is plain C; with C++, keep name mangling/`extern "C"` in mind according to the contract in the JNI header. The example only adds two small numbers so as not to encounter differences in signed integer overflow between C and Java.

**Step 4 — Compile the library for the corresponding operating system.** The commands below are **three alternatives**, do not run all three. `JAVA_HOME` must point to a JDK containing the `include` directory; Windows uses *Developer Command Prompt for Visual Studio* which has the `cl` command.

Linux (GCC):

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  nativecalc.c -o libnativecalc.so
java -Djava.library.path=. NativeCalc
~~~

macOS (Clang):

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  nativecalc.c -o libnativecalc.dylib
java -Djava.library.path=. NativeCalc
~~~

Windows (MSVC, in **Developer Command Prompt**, `cmd.exe` environment variable syntax):

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativecalc.c /Fe:nativecalc.dll
java -Djava.library.path=. NativeCalc
~~~

**Stdout output of the Java program when built/loaded successfully on each platform:**

~~~text
3 + 4 = 7
~~~

With this naming, `System.loadLibrary("nativecalc")` selects `nativecalc.dll` on Windows, `libnativecalc.so` on Linux, and `libnativecalc.dylib` on macOS. `-Djava.library.path=.` is placed **before** the class name so the JVM looks for the library in the current directory. In real production applications, use a dedicated native directory and explicit configuration instead of relying on the current directory.

**What happens at runtime?** Java calls `add(3, 4)`; JNI converts the two `int`s to `jint` and calls `Java_NativeCalc_add` in the loaded library; C returns 7; the JVM passes the result back to Java to print. This is a synchronous call thread within the same process, with no IPC/network and no separate C process spawned.

## 7. Diagnosing library loading errors

Distinguish between **file not found**, **wrong architecture file**, **missing dependency**, and **wrong JNI symbol**. All of them can appear as `UnsatisfiedLinkError`, but the troubleshooting steps differ.

| Symptom | Primary Possibility | Check / Fix |
|---|---|---|
| `no nativecalc in java.library.path` | The JVM has not found the main library | Check the logical name, filename, actual directory, and `-Djava.library.path`. |
| `wrong ELF class: ELFCLASS32` or wrong machine type error | Bitness/CPU architecture does not match the JVM | Check the architecture of the Java process and the binary; rebuild for the right target. |
| `cannot open shared object file` or "module not found" even though the main file exists | Missing dependent library, wrong OS loader path | Check dependencies and runtime loader paths, not just `java.library.path`. |
| `undefined symbol` or missing entry point error | Incompatible ABI/symbol/dependency version | Check exported symbols, C++ mangling, JNI header, library versions. |
| Native method declared but not linked | JNI function has wrong name/signature or missing `RegisterNatives` | Regenerate the header with `javac -h` and export the exact function. |
| JVM crash (SIGSEGV/Access Violation) while calling native | Pointer, memory, thread, or data/ABI error | Inspect native code, `hs_err_pid...log` crash log if available, native debugger. |

Commands to help observe:

~~~bash
java -version
java -XshowSettings:properties -version
# View JVM version, os.arch, java.library.path...
~~~

Linux:

~~~bash
file libnativecalc.so
readelf -h libnativecalc.so
readelf -d libnativecalc.so
ldd libnativecalc.so
~~~

macOS:

~~~bash
file libnativecalc.dylib
lipo -info libnativecalc.dylib
otool -L libnativecalc.dylib
~~~

Windows (Developer Command Prompt):

~~~bat
dumpbin /HEADERS nativecalc.dll
dumpbin /DEPENDENTS nativecalc.dll
~~~

`file`/`readelf -h` show the ELF type and architecture; `readelf -d`/`ldd` inspect dependencies on Linux. `otool -L` shows Mach-O links; `lipo -info` shows architecture slices. `dumpbin` inspects PE headers and dependent DLLs. Interpret the results against the **actual JVM architecture**, not just the machine's OS name or CPU.

If the error occurs right in the `static` block, class loading can fail before `main` executes application statements. The full log including the underlying root cause, dependent library names, and binary architecture is more useful than randomly changing path variables.

## 8. Packaging, distribution, and maintenance

Native libraries are **not automatically loaded just by being present inside a JAR**. When releasing an application that runs on multiple platforms:

1. Build **binaries matching each OS/architecture** (e.g., Linux x86_64, Linux arm64, Windows x64, macOS arm64) using a supported toolchain. Consider `glibc`/`musl` compatibility, C/C++ runtimes, and minimum OS version.
2. Distribute native binaries under a well-defined structure, e.g., `native/linux-x86_64/`, `native/windows-x86_64/`. Select the right file based on the verified runtime environment, not just by looking at directory names.
3. Place the library at a path accessible to the JVM/OS loader. If extracting the library from a JAR to the filesystem before loading, carefully manage location, permissions, integrity, and file lifecycle.
4. Manage native library dependencies and versions alongside Java artifacts; test on actual target systems. Code signing/checksum verification and trusted binary sources help avoid loading unintended code.
5. Design a clean JNI boundary: convert strings/arrays/buffers with proper types, release native resources, and do not hold pointers or JNI references past their valid lifetime. Native code shares the process and can affect the entire JVM when wrong.

**Class loaders also have their own lifecycle:** the JVM tracks native libraries associated with a loader; loading the same native library through independent class loaders can hit errors like "already loaded in another classloader". Do not treat loading/unloading as an operation you can hot-swap arbitrarily; design clear ownership for the library.

Beyond JNI, Java has native interop options such as **JNA** (third-party library) and **Foreign Function & Memory API (FFM)** (standard API since JDK 22). They reduce or change how the bridge is written, but **do not eliminate the requirements for binary, ABI, CPU architecture, and OS loader compatibility**. When learning process architecture, you must understand these constraints first regardless of which bridge you choose.

## 9. Self-check questions

- Why can't a 64-bit JDK/JVM load a 32-bit DLL directly, even when Windows supports running 32-bit processes?
- Why can `libnativecalc.so` exist in the configured directory while the loader still reports `libdependency.so` is missing?
- What is the difference between `System.loadLibrary("nativecalc")` and `System.load("/absolute/path/libnativecalc.so")`?
- If Java is running on macOS ARM64 but the native library only has an x86_64 slice, what needs to change in the binary or runtime environment?
- If a native pointer error causes the JVM to crash, why can't a Java `try/catch` guarantee recovering the process?

**Key takeaway:** `.dll`, `.so`, and `.dylib` are machine-code libraries brought into the **address space of the Java process** by the OS loader. Successful loading depends simultaneously on **OS format, JVM architecture and bitness, ABI/symbols, dependencies, and path rules**. JNI is one way for Java to call into those libraries; it does not turn native code into bytecode or isolate native code from the JVM.

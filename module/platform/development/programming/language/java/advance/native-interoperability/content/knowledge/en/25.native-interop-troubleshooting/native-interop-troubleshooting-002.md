# Troubleshooting — Comparing OS, CPU, Bitness, and ABI Versions When Library Loading Fails

## 1. Goal: Diagnose the Right Layer Before Fixing

When Java calls `System.loadLibrary("nativedoctor")`, `System.load("...")`, or uses **FFM `SymbolLookup.libraryLookup(...)`**, Java/JVM must work with the operating system's **native binary loader**. A valid C/C++ library on machine A will not necessarily load into the JVM on machine B, even if both sides have the same Java version or the same file name.

There are four independent questions to verify:

1. **OS and binary format:** Is the JVM running on Windows, Linux, or macOS? Is the library a PE/COFF `.dll`, ELF `.so`, or Mach-O `.dylib`? Can the binary actually be loaded by the current operating system?
2. **CPU architecture:** Is the JVM x86 (32-bit), x86-64/AMD64, ARM64/AArch64, or another type? Does the native image contain machine code for the **architecture of the JVM process itself**?
3. **Bitness / pointer width:** Is the JVM process running 32-bit or 64-bit? Do the native library and its dependencies have the same width and compatible format? **A 64-bit OS does not mean the JVM is running 64-bit.**
4. **ABI and dependency versions:** Are the calling convention, C/JNI symbols, `size_t`, `long`, struct layout, C/C++ runtime, versioned symbols, and `JNI_OnLoad` compatible with the JVM/OS/native dependencies in use?

This is a **native interoperability troubleshooting** guide, not instructions for disabling safety checks. The fix is to **select/compile the right library for the target JVM process and ABI**, check dependencies, and fix the linkage contract; do not arbitrarily change the JVM architecture or copy random DLLs from the Internet.

### Root Cause Flow

```text
Java calls loadLibrary / load / FFM libraryLookup
                  │
                  ▼
       Target file found?
         │ NO                    │ YES
         ▼                       ▼
 java.library.path /       Binary matches OS format?
 classloader search         │ NO       │ YES
                            ▼          ▼
                         Choose     Library CPU/bitness
                       right binary matches JVM process?
                                       │ NO       │ YES
                                       ▼          ▼
                                  Build/download  Dependencies and
                                  right arch      runtime ABI sufficient?
                                                 │ NO       │ YES
                                                 ▼          ▼
                                           Fix dep/rpath   JNI_OnLoad,
                                           CRT/glibc       export symbol,
                                                           signature correct?
                                                        │ NO       │ YES
                                                        ▼          ▼
                                                   Fix JNI/ABI   Run
```

**The same `UnsatisfiedLinkError` can have many origins.** Keep the **full error message, OS diagnostics, and actual native library path**. Do not guess the cause based solely on the exception name.

## 2. Understanding the 5 Distinct Stages of Native Library Loading

A native method typically goes through:

1. **Java selects the library:** `System.loadLibrary("nativedoctor")` uses a logical name to look up a platform-appropriate library. `System.mapLibraryName("nativedoctor")` typically returns `nativedoctor.dll` (Windows), `libnativedoctor.so` (Linux), `libnativedoctor.dylib` (macOS).
2. **JVM locates the file:** A Java classloader may use its own `findLibrary`; otherwise, the JVM searches using the default mechanism and `java.library.path` for the target library. `System.load(absolutePath)` takes an **absolute path** and skips this logical-name lookup step.
3. **OS loader loads the binary + dependencies:** The Windows loader, ELF loader, or dyld verifies the format/CPU and locates the libraries that the binary depends on. **`java.library.path` does not directly replace the operating system's dependency search path.**
4. **Native library initialization:** The OS runs certain initializers, and the JVM may call `JNI_OnLoad` (if provided by the library); a JNI version unsupported by the JVM can cause loading to fail.
5. **JNI method binding / FFM downcall creation:** A Java `native` method requires the correct export name or `RegisterNatives`; FFM requires the correct symbol/`FunctionDescriptor`. This error can appear **after library loading has already succeeded**.

Example of a correct library name but wrong JNI symbol:

```text
System.loadLibrary("nativedoctor")   -> load: OK
NativeLoadDoctor.ping()              -> UnsatisfiedLinkError
```

The second case is not necessarily "DLL not found"; the DLL may exist and already be loaded, yet be missing an export, the Java class/package name may have changed, the native function may not use `JNIEXPORT`, the C++ name may be mangled, or `RegisterNatives` may not be registered properly.

**Note on classloaders:** per the JNI specification, native libraries are managed per classloader. Attempting to load **the same JNI library** into **two different classloaders** can throw `UnsatisfiedLinkError` even if the path and CPU are both correct. Do not solve that case by copying an arbitrary binary.

## 3. OS, CPU, and Bitness: What Exactly to Compare?

### 3.1. Target OS and native binary format

| OS the JVM is running on | Common native format | Example name for `nativedoctor` | Inspection tools |
| --- | --- | --- | --- |
| Windows | PE/COFF, typically a DLL | `nativedoctor.dll` | `dumpbin /headers`, PowerShell reading PE header, `dumpbin /dependents` |
| Linux | ELF shared object | `libnativedoctor.so` | `file`, `readelf -h`, `readelf -d`, `objdump -p` |
| macOS | Mach-O dynamic library/bundle | `libnativedoctor.dylib` | `file`, `lipo -archs`, `otool -L` |

The file name is only an **external** indicator: renaming `libnativedoctor.so` to `nativedoctor.dll` **does not turn an ELF into a PE**. Check the **magic number** and header of the actual file; do not trust the extension.

A Linux container must still load a **Linux ELF** compatible with the container runtime/CPU; it cannot use a Windows DLL just because the physical host is running Windows. WSL runs a Linux environment, so inside WSL a Linux ELF is required. On Apple Silicon macOS, a JVM running via Rosetta under the `x86_64` architecture needs an **x86_64 Mach-O slice**, not arbitrarily taking the `arm64` slice just because the physical CPU is ARM64.

### 3.2. Process CPU differs from physical machine CPU

`System.getProperty("os.arch")` reflects the JVM/implementation environment architecture, typically `amd64` or `x86_64` for an x64 JVM, `aarch64` for an ARM64 JVM. The names `amd64` and `x86_64` both refer to the x86-64 architecture; do not treat the string difference as an error. `arm64` and `aarch64` generally belong to the same ARM64 family.

Distinguish between:

- **Physical CPU** of the machine.
- **JVM process architecture** actually running, which can differ from the physical CPU when using Rosetta, Windows-on-ARM emulation, or compatibility layers.
- **Architecture of the native binary and child DLLs/SOs**, which must be compatible with the **loading process**, not just the physical machine.
- **Instruction-set extensions** such as AVX2/AVX-512: an x86-64 library may load successfully but crash with `Illegal instruction`/`SIGILL` at runtime on a CPU lacking the extension. That is **not** a library-not-found error.

**Do not take `uname -m` or `PROCESSOR_ARCHITECTURE` and immediately conclude the Java process has the same ISA.** Read both the JVM version/architecture and the header of the library you intend to load.

### 3.3. 32/64-bit

**Bitness** is the width of the process ABI/pointer, not the bitness of the operating system. A 64-bit OS can still run a 32-bit JVM (depending on the platform). A 32-bit JVM cannot directly load a 64-bit DLL/SO; a 64-bit JVM also cannot directly load a 32-bit library.

Examples:

| JVM process | Library | Loads directly? | Issue |
| --- | --- | --- | --- |
| Windows x64 Java 64-bit | PE x64 DLL | Possible, if dependencies/ABI are right | Machine and bitness match |
| Windows x64 Java 64-bit | PE x86 32-bit DLL | **No** | Mismatched bitness |
| Windows ARM64 Java ARM64 | PE x64 DLL | Does not cross-arch load by default into an ARM64 process | Needs an ARM64 library or running an appropriate x64 JVM |
| Linux x86-64 Java 64-bit | ELF x86-64 64-bit SO | Possible, if dependencies/ABI are right | Architecture matches |
| Linux x86-64 Java 64-bit | ELF x86 32-bit SO | **No** | `wrong ELF class: ELFCLASS32` |
| macOS Apple Silicon Java arm64 | Universal Mach-O with arm64 slice | Possible, if ABI and dependencies are right | OS selects the arm64 slice |
| macOS Apple Silicon Java x86_64 via Rosetta | Mach-O arm64-only | **No** | Missing x86_64 slice |

**`sun.arch.data.model`** typically returns `32`/`64` on HotSpot/Azul OpenJDK, but it is an **implementation-specific property**, not a Java SE portability guarantee. Use it together with `java -version`, `os.arch`, and the binary header to prove bitness.

## 4. Record the JVM Environment Before Touching the Native Library

In the exact **failing** environment (IDE, Maven Surefire, Gradle Test, container, or Java service), run:

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

Look for `os.name`, `os.arch`, `java.version`, `java.home`, `java.library.path`; record the Java executable the application is actually running, not just the terminal's `JAVA_HOME`. `javac` is used to build source; **the `java` of the running process determines the native architecture**.

On Windows PowerShell:

```powershell
Get-Command java | Select-Object -ExpandProperty Source
Get-Command javac | Select-Object -ExpandProperty Source
[Environment]::Is64BitProcess
[Environment]::Is64BitOperatingSystem
$env:JAVA_HOME
```

On Linux/macOS:

```bash
command -v java
command -v javac
uname -s
uname -m
echo "$JAVA_HOME"
```

**Note:** `command -v java` may point to a symlink/launcher wrapper; check the actual target file and real Java runtime. Installing multiple JDKs easily causes the IDE to build with a different JDK than the one the server runs. If diagnostics print `os.arch=amd64` while the release artifact contains an `arm64` binary, that is a sign to re-select the artifact.

To reproduce, save four key fields along with the error: **OS name/version, JVM CPU architecture, JVM process bitness, full loader error**, then compare against the header of the **actual library file used** and its dependencies.

## 5. Runnable Java 17+ Example: `NativeLoadDoctor.java`

This example lets you:

- Print OS/JVM architecture, process bitness via the HotSpot property when available, Java version, byte order, and the mapped native library name.
- `--bind-only` calls an unbound `native` method to demonstrate a **JNI binding** error without needing to create a library.
- `--name <logicalName>` attempts `System.loadLibrary`, demonstrating name-based lookup issues.
- `--file <path>` attempts `System.load` with an absolute path (automatically converted from the given path), demonstrating binary/OS loader issues even when `java.library.path` is bypassed.
- If loading succeeds, calls native `ping()` to distinguish **library loading** from **JNI symbol resolution**.

The Java source does not need a JNI C compiler to **test the error branches**. For actually running with the `nativedoctor` native library, the C code and build commands are in section 6.

### 5.1. Full file: `NativeLoadDoctor.java`

```java
import java.nio.ByteOrder;
import java.nio.file.Path;

public final class NativeLoadDoctor {
    private static native int ping();

    public static void main(String[] args) {
        System.out.println("os.name: " + System.getProperty("os.name"));
        System.out.println("os.arch: " + System.getProperty("os.arch"));
        System.out.println("VM bitness (vendor-specific): "
                + System.getProperty("sun.arch.data.model", "unknown"));
        System.out.println("java.version: " + System.getProperty("java.version"));
        System.out.println("mapped native name: "
                + System.mapLibraryName("nativedoctor"));
        System.out.println("native byte order: " + ByteOrder.nativeOrder());

        if (args.length == 0) {
            System.out.println("mode: metadata only");
            return;
        }
        if (args[0].equals("--bind-only")) {
            tryPing();
            return;
        }
        if (args.length != 2) {
            System.err.println(
                "Usage: --name logicalName | --file path | --bind-only");
            return;
        }

        try {
            if (args[0].equals("--name")) {
                System.loadLibrary(args[1]);
            } else if (args[0].equals("--file")) {
                String absolute = Path.of(args[1]).toAbsolutePath()
                        .normalize().toString();
                System.load(absolute);
            } else {
                System.err.println("Unknown mode: " + args[0]);
                return;
            }
            System.out.println("library load: OK");
        } catch (UnsatisfiedLinkError error) {
            System.out.println("library load: UnsatisfiedLinkError");
            System.err.println("loader detail: " + error.getMessage());
            return;
        }
        tryPing();
    }

    private static void tryPing() {
        try {
            System.out.println("JNI ping: " + ping());
        } catch (UnsatisfiedLinkError error) {
            System.out.println("JNI bind: UnsatisfiedLinkError");
            System.err.println("symbol detail: " + error.getMessage());
        }
    }
}
```

**Diagnostic design, not production error handling:** the program **intentionally catches** `UnsatisfiedLinkError` and prints a status line; therefore the exit code can be `0` even when load/bind fails. CI must inspect stdout or use another process with a **nonzero exit** when loading fails. Do not swallow errors in a real application and assume native functionality is ready.

### 5.2. Compile and generate the JNI header

With JDK 17+:

```bash
mkdir -p build/classes build/headers
javac -encoding UTF-8 -h build/headers \
  -d build/classes NativeLoadDoctor.java
```

Use `javac -h` rather than the obsolete `javah` tool. In `build/headers/NativeLoadDoctor.h`, the compiler generates the signature:

```c
JNIEXPORT jint JNICALL Java_NativeLoadDoctor_ping
  (JNIEnv *, jclass);
```

This signature was verified with `javac -h` on **OpenJDK 24**. Because the Java method is `private static native int ping()`, C receives `JNIEnv*` and `jclass` (not `jobject`) and returns `jint`.

### 5.3. Test commands without a DLL/SO

With **JDK 24+**, because `System.load`/`System.loadLibrary` are restricted operations, pass the native-access flag when attempting to load:

```bash
# Print JVM information only (no library required).
java -cp build/classes NativeLoadDoctor

# Call native method with no linked library.
java -cp build/classes NativeLoadDoctor --bind-only

# Attempt to load an intentionally nonexistent name.
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeLoadDoctor \
  --name __nativedoctor_really_missing_w3_2026__
```

With **JDK 17–23**, `--enable-native-access` is not enforced under the JDK 24 JNI rules; run `java -cp build/classes ...` and check the policy of the current JDK. `--illegal-native-access` also does not exist on all older JDKs.

**Full stdout in no-argument mode, run on Windows 11/OpenJDK 24.0.2 x64:**

```text
os.name: Windows 11
os.arch: amd64
VM bitness (vendor-specific): 64
java.version: 24.0.2
mapped native name: nativedoctor.dll
native byte order: LITTLE_ENDIAN
mode: metadata only
```

In the same environment, `--bind-only` prints the **six fingerprint lines above** and the final line:

```text
JNI bind: UnsatisfiedLinkError
```

`stderr` has detail of the form `int NativeLoadDoctor.ping()` — exact wording/quoting may vary by JDK vendor.

With `--name __nativedoctor_really_missing_w3_2026__`, the six fingerprint lines stay the same, and the final line is:

```text
library load: UnsatisfiedLinkError
```

`stderr` has the form `no __nativedoctor_really_missing_w3_2026__ in java.library.path: ...` (trailing path depends on the machine). **Do not treat this string as proof of wrong bitness**: in this test the JVM simply did not find the target library.

Testing a nonexistent absolute path:

```bash
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes NativeLoadDoctor \
  --file missing_native.dll
```

The `--file` command converts the path to absolute and then calls `System.load`. It also prints `library load: UnsatisfiedLinkError`, but `stderr` reports `Can't load library: <absolute path>`. This is a **target file does not exist** error, distinct from a missing native dependency error when the target file actually exists.

**Shell type note:** in Windows PowerShell, write the entire `java` command on one line or use PowerShell's line continuation character. The trailing `\` in the `bash` examples is only for shells that support POSIX-style line continuation. A single-line command has the same meaning.

## 6. Sample JNI C Library: Deterministic ABI and Symbol Verification

To have a "correct" library to compare against failure cases, use the small source below. The Java source and JNI header have been compiled/tested in practice; the C code below was reviewed **against the generated header**, but **C was not compiled/run in the Windows test environment because no C compiler was on PATH**. Treat the output of the native call when building it yourself as **expected**, not claimed as executed here.

### 6.1. File `nativedoctor.c`

```c
#include <jni.h>

// Java declaration: private static native int ping();
JNIEXPORT jint JNICALL Java_NativeLoadDoctor_ping
  (JNIEnv *env, jclass clazz) {
    (void) env;
    (void) clazz;
    return 42;
}

// This export is optional, but demonstrates the required JNI API version.
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;
    return JNI_VERSION_1_8;
}
```

**ABI significance:**

- `#include <jni.h>` pulls in the exact JNI typedefs `jint`, `JNIEnv`, `jclass`, and macros.
- `JNIEXPORT` marks symbol export/visibility appropriate for the platform.
- `JNICALL` uses the calling convention required by JNI (especially important on Windows x86 32-bit).
- `Java_NativeLoadDoctor_ping` must match the **package/class/method** generated by `javac -h`. Whenever you change the Java package/class or overload a method, you must regenerate the header and rebuild.
- `JNI_OnLoad` provides the minimum JNI API version. `JNI_VERSION_1_8` is supported on JDK 17+; if `JNI_OnLoad` returns a version not recognized by the JVM, loading is rejected, **even when architecture and path are both correct**.
- Do not replace `JNI_OnLoad` with `JNI_OnLoad_libName` for a **dynamic** library; the suffixed variant is for libraries statically linked into the VM.

**If building with a C++ compiler**, ensure exported native functions use **C linkage** (`extern "C"`) instead of C++ name mangling, or implement `RegisterNatives` properly. Use the prototype from `javac -h` as the source of truth; do not guess JNI names manually.

### 6.2. Build for the right OS and CPU

**Linux x86-64 / AArch64** with GCC, run in the directory containing `nativedoctor.c`:

```bash
gcc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libnativedoctor.so nativedoctor.c
```

**macOS** with Clang:

```bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -o libnativedoctor.dylib nativedoctor.c
```

**Windows** with MSVC in a **Developer Command Prompt** or **Developer PowerShell** containing the C/C++ toolchain matching x64/x86/ARM64:

```bat
cl /LD /W4 /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativedoctor.c /link /OUT:nativedoctor.dll
```

The Windows command above uses `cmd.exe/Developer Command Prompt` syntax for `%JAVA_HOME%` expansion; when using PowerShell, replace it with properly quoted `$env:JAVA_HOME` paths. Choose a **compiler target architecture** matching the JVM process: if Java is x64, use the MSVC x64 target; if Java is ARM64, use the ARM64 toolchain. Only add `-m32` when you actually have a complete 32-bit toolchain and a 32-bit JVM.

If `JAVA_HOME` is not set to a JDK that has `include/jni.h`, set it properly before compiling. When a library has dependencies beyond `jni.h`, they must also be built/linked for the right OS/CPU/ABI.

### 6.3. Run the built native binary

After placing the library in the current directory:

```bash
# JDK 24+: explicit native access for code on the classpath.
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. -cp build/classes \
  NativeLoadDoctor --name nativedoctor
```

**Expected final output when the C source is built/loaded properly:**

```text
library load: OK
JNI ping: 42
```

This is the **expected result from the C source**, not a log from a complete C/Java run. If `library load: OK` but `JNI bind: UnsatisfiedLinkError`, stop tweaking `java.library.path`: check the symbol name/export/ABI and `RegisterNatives`.

## 7. How to Read the Target Library Header on Each OS

### 7.1. Windows: PE Machine and PE32/PE32+

Open **Visual Studio Developer Command Prompt** (includes `dumpbin`):

```bat
dumpbin /headers nativedoctor.dll
dumpbin /dependents nativedoctor.dll
dumpbin /exports nativedoctor.dll
```

How to read it:

- `FILE HEADER VALUES ... machine` indicates the ISA: `14C` is typically **Intel 386/x86 32-bit**, `8664` is **AMD64/x86-64**, `AA64` is **ARM64**.
- `OPTIONAL HEADER VALUES` indicates magic: `10B` = **PE32**, `20B` = **PE32+** (typically 64-bit).
- `/dependents` gives the names of DLL dependencies; **it does not prove all those dependencies are available in the right version at runtime**.
- `/exports` shows whether `Java_NativeLoadDoctor_ping`, `JNI_OnLoad`, and the C functions you are looking for are actually exported.

If `dumpbin` is unavailable, PowerShell can read the **PE header itself**. The following script **was run on OpenJDK 24 Windows x64** against `java.exe` and returned `0x8664` / `0x020B`:

```powershell
$path = (Get-Command java).Source
$fs = [System.IO.File]::OpenRead($path)
try {
    $reader = New-Object System.IO.BinaryReader($fs)
    if ($reader.ReadUInt16() -ne 0x5A4D) {
        throw "Not a PE/MZ file"
    }
    [void]$fs.Seek(0x3C, [System.IO.SeekOrigin]::Begin)
    $peOffset = $reader.ReadInt32()
    [void]$fs.Seek($peOffset, [System.IO.SeekOrigin]::Begin)
    if ($reader.ReadUInt32() -ne 0x00004550) {
        throw "Invalid PE signature"
    }
    $machine = $reader.ReadUInt16()
    [void]$fs.Seek($peOffset + 24, [System.IO.SeekOrigin]::Begin)
    $magic = $reader.ReadUInt16()
    "PE Machine: 0x{0:X4}" -f $machine
    "OptionalHeader Magic: 0x{0:X4}" -f $magic
} finally {
    $fs.Dispose()
}
```

**Test machine output:**

```text
PE Machine: 0x8664
OptionalHeader Magic: 0x020B
```

To inspect a **DLL instead of java.exe**, set `$path` to the actual DLL path. This script only reads the header, **without loading or executing the DLL**; it is safer than trying to load an untrusted binary. `PE32+` indicates the format, while the `Machine` field is the CPU information you must compare. An `arm64` library can have 64-bit bitness and still be incompatible with an **x86-64 JVM**.

### 7.2. Linux: ELF class, machine, NEEDED, symbol versions

```bash
file libnativedoctor.so
readelf -h libnativedoctor.so
readelf -d libnativedoctor.so
readelf --version-info libnativedoctor.so
readelf -Ws libnativedoctor.so | grep Java_NativeLoadDoctor_ping
```

Read these fields:

- `Class: ELF64` or `ELF32` — **bitness**, not synonymous with CPU.
- `Machine: Advanced Micro Devices X86-64` / `AArch64` — **CPU architecture**.
- `NEEDED` in the dynamic section — list of native libraries this ELF requires.
- `RPATH`/`RUNPATH` — dependency search paths embedded in the ELF.
- Version requirements such as `GLIBC_2.xx` or `GLIBCXX_3.4.xx` — the C/C++ runtime ABI level required by the binary, which the target system may not provide.
- Symbol table confirms the JNI export exists and has the right linkage; if built with hidden visibility or C++ mangling, the export may be missing.

`ldd libnativedoctor.so` is useful for checking where dependencies resolve on a Linux system, **but only run `ldd` on trusted libraries**, because some `ldd` mechanisms/versions carry a risk of executing code. When inspecting untrusted artifacts, prefer static inspection with `readelf`/`objdump` and an isolated environment.

**glibc vs musl:** both typically use the `.so` name and ELF format, but their C library/runtime ABIs differ. A binary built in a glibc image may not run in an Alpine/musl image. Use the right base image/toolchain or provide compatible dependencies; renaming the SO will not fix the libc ABI.

### 7.3. macOS: Mach-O architecture slices and dependencies

```bash
file libnativedoctor.dylib
lipo -archs libnativedoctor.dylib
otool -L libnativedoctor.dylib
nm -gU libnativedoctor.dylib | grep Java_NativeLoadDoctor_ping
```

- `file` shows the Mach-O format and CPU.
- `lipo -archs` lists slices in a **universal/fat binary**. There must be a slice **matching the process architecture** (arm64 or x86_64).
- `otool -L` lists dependent dylibs and install names.
- `nm -gU` helps confirm exports; C symbols in Mach-O may display a leading underscore depending on platform tools.
- Check `@rpath`, `@loader_path`, `@executable_path` if the dynamic loader cannot find a dependent dylib. macOS also has constraints around code signing, quarantine, and hardened runtime/SIP depending on the situation.

On Apple Silicon macOS, check whether the JVM is **arm64** or **x86_64 via Rosetta** and compare against the slices in the dylib. An arm64-only library cannot be loaded directly into an x86_64 JVM process running via Rosetta.

## 8. Distinguishing Search Paths for the TARGET Library vs. DEPENDENT Libraries

This is a very commonly overlooked cause:

```text
Java
 └── loadLibrary("codec")
       └── JVM finds libcodec.so / codec.dll
             └── OS loader finds dependencies:
                   ├── libz.so / zlib.dll
                   ├── libstdc++.so.6 / C++ runtime
                   └── nativecodechelper.so / helper.dll
```

`java.library.path` helps the JVM find the **target library** when using name-based lookup. Once the OS loader opens the target library, **dependent DLLs/SOs/dylibs** are typically searched according to the **OS's own rules**. Therefore, fixing `-Djava.library.path` can resolve `no codec in java.library.path` but **will not** resolve a missing `libstdc++.so.6` or `VCRUNTIME140.dll`.

Inspection approach by OS:

| OS | Checking dependencies and search paths |
| --- | --- |
| Windows | `dumpbin /dependents`, `where.exe` to inspect PATH, OS DLL search order, application directory, system DLLs; note load APIs and DLL search flags |
| Linux | `readelf -d` to check `NEEDED/RUNPATH/RPATH`, inspect loader cache `ldconfig -p` where appropriate, `LD_LIBRARY_PATH` and `$ORIGIN` environment, libc version |
| macOS | `otool -L`, `@rpath/@loader_path`, code signature/quarantine when relevant; do not rely blindly on `DYLD_LIBRARY_PATH` due to SIP/hardened runtime |

**Sustainable fixes:** package dependencies correctly per OS/CPU/ABI; use an app-private library directory or appropriate RPATH/RUNPATH; check the versions of runtime dependencies. Do not copy similarly named DLLs from untrusted sources into `System32`, do not arbitrarily disable signature/code-signing checks, and do not modify global PATH when only one application needs configuration.

### `System.loadLibrary` vs. `System.load`

| Characteristic | `System.loadLibrary("nativedoctor")` | `System.load("/abs/path/native.dll")` |
| --- | --- | --- |
| Input | **Logical name**, without extension/path | **Absolute path** to binary |
| Primary file lookup rules | ClassLoader/Java library search | Primary file already specified |
| `System.mapLibraryName` | Involved in OS-specific native name | No name mapping needed |
| `java.library.path` | Can affect finding the primary file | Does not replace the absolute path |
| OS dependent libraries | **Still** follows OS loader | **Still** follows OS loader |
| OS/CPU/bitness/ABI | Must match | Must match |
| JNI/FFM symbols | Still must have the right symbols | Still must have the right symbols |

Use `System.load(absolutePath)` **only to isolate primary-file lookup errors**; do not treat it as a substitute for packaging/ABI/versioning. Avoid modifying `System.setProperty("java.library.path", ...)` at runtime and assuming the classloader will immediately update its search path: the mechanism may already have been cached/initialized earlier. Prefer configuring the launcher or loader properly before loading.

## 9. ABI and Versions: Why Can a Correct-Bitness Binary Still Fail to Load?

The **ABI (Application Binary Interface)** defines how data and functions are laid out at the binary level: calling convention, registers/stack, type and struct layout, alignment, symbol/linkage, C/C++ runtime compatibility, and versioned exports. **Being 64-bit is not enough**.

### 9.1. Windows LLP64 vs. Linux LP64

On most Windows x64 (**LLP64**):

- `int` is 32-bit, C `long` is **32-bit**, pointer and `size_t` are **64-bit**.
- JNI `jlong` is always 64-bit, but do **not** blindly map C `long` to Java `long`.

On most Linux x86-64 (**LP64**):

- `int` is 32-bit; C `long`, pointer, and `size_t` are all **64-bit**.

A JNI or FFM `FunctionDescriptor` using the wrong return/argument layout may **load the binary successfully** and then cause wrong data/crashes **when called**, rather than throwing `UnsatisfiedLinkError` at load time. `wchar_t`, `long double`, struct padding, C++ vtable/RTTI, and calling convention must also be checked against the C header and target compiler/ABI.

### 9.2. JNI symbol name, export, and `RegisterNatives`

For Java:

```java
private static native int ping();
```

The header generates `Java_NativeLoadDoctor_ping(JNIEnv*, jclass)`. If C implements `Java_OldClass_ping`, the package changed, the JNI signature changed, or the C++ compiler mangled the name, Java may load the library but fail at **native method binding**.

How to check:

- Use `javac -h` to generate the header **from the current Java source**.
- Use `dumpbin /exports`, `nm -D` / `readelf -Ws`, or `nm -gU` to inspect **actual exports**.
- When using `RegisterNatives` instead of inferred JNI names, verify the exact **method name** and **descriptor**, e.g. `()I` for `int ping()`; the registration code must actually execute successfully.
- Check `JNIEXPORT`, `JNICALL`, `extern "C"` (if C++), toolchain, and compiler options that hide symbols.
- With Java modules/modern JDKs, native method binding may also be subject to **native-access restrictions**; distinguish a denial `IllegalCallerException` from the loader's `UnsatisfiedLinkError`.

### 9.3. JNI API version and `JNI_OnLoad`

`JNI_OnLoad(JavaVM*,void*)` is called by the JVM when loading a JNI library that exports it. It must return a `JNI_VERSION_*` supported by the JVM. For example, `JNI_VERSION_1_8` is compatible with JDK 17+. If `JNI_OnLoad` returns an unrecognized version code, the JVM rejects the library and treats it as a load failure, **even when OS/CPU/bitness already match**.

**Do not confuse three types of "version":**

1. **JNI API version:** `JNI_VERSION_1_8`, `JNI_VERSION_9`, `JNI_VERSION_10` ... is the **interface** version between the JVM and the native library.
2. **Native library/application ABI version:** e.g., the API of `libcodec.so.2` or symbols of `codec.dll` — determined by the library, which can break compatibility if functions/structs change.
3. **OS C/C++ runtime ABI version:** e.g., versioned symbols `GLIBC_2.xx`, `GLIBCXX_3.4.xx` on Linux, or MSVC/UCRT runtime requirements on Windows.

Using `JNI_VERSION_1_8` **does not guarantee** that a binary compiled on newer glibc Linux will run on Alpine/musl, or that a newer MSVC DLL will have its runtime dependencies on another Windows machine.

### 9.4. C++ and versioned symbols

C++ name mangling, compiler ABI, `libstdc++` vs. `libc++`, compiler toolset, visibility flags, and C++ exceptions crossing the FFI boundary can all cause failures. For an API exported to JNI/FFM, design a **stable C ABI**, wrap the C++ implementation with `extern "C"`, and avoid passing STL types/vtables directly across the boundary.

If Linux reports:

```text
version 'GLIBCXX_3.4.xx' not found
```

The error is the **libstdc++ runtime version**, not Java data types or bitness. Check `readelf --version-info`, the actual runtime version selected by the OS loader, and then build on a compatible distro baseline or package dependencies according to product policy. Do not fix it by randomly copying `libstdc++.so.6` into system directories.

**ARM64 and x86_64 are both 64-bit, yet do not share the same ABI**. Bitness is only one part of binary compatibility.

## 10. Common Error Matrix and Diagnostic Direction

| Symptom (example) | Stage | Likely cause | Next step |
| --- | --- | --- | --- |
| `no nativedoctor in java.library.path` | JVM locating primary file | File missing or wrong search path | `System.mapLibraryName`, classloader, `-Djava.library.path`, artifact packaging |
| `Can't load library: /abs/path/...` | `System.load` | Primary file does not exist, wrong path/permissions, or loader cannot open it | Check actual file, permissions, and OS message |
| `wrong ELF class: ELFCLASS32` | OS ELF loader | 64-bit JVM tried to load a 32-bit ELF | `readelf -h` + JVM architecture |
| `wrong ELF class: ELFCLASS64` | OS ELF loader | 32-bit process tried to load a 64-bit ELF | Choose 32-bit artifact or matching 64-bit JVM |
| `%1 is not a valid Win32 application` / OS error 193 | Windows loader | May be wrong format/machine/bitness or file is not a valid DLL | `dumpbin /headers`, machine and PE32/PE32+ |
| `mach-o file, but is an incompatible architecture` | macOS dyld | Dylib missing slice matching JVM | `lipo -archs`, determine Rosetta/process CPU |
| `The specified module could not be found` even though primary DLL exists | Windows loader | May be missing a dependent DLL | `dumpbin /dependents`, OS DLL search path |
| `libcodec.so: cannot open shared object file` | Linux loader | Target/dependency search path incorrect | `readelf -d`, `LD_LIBRARY_PATH`, `RUNPATH` |
| `undefined symbol: ...` | Dynamic linker | Missing export or wrong ABI/dependency | `nm`, `readelf -Ws`, runtime dependency |
| `GLIBC_2.xx not found` / `GLIBCXX_3.4.xx not found` | ELF symbol versions | glibc/libstdc++ runtime older than required | Compare build baseline and deployed runtime |
| `UnsatisfiedLinkError: ...NativeLoadDoctor.ping()I` | JNI native method binding | DLL loaded but missing symbol/registration | `javac -h`, `dumpbin /exports`, `RegisterNatives` |
| `JNI_OnLoad returned invalid JNI version` | JNI init | Native requests JNI version unsupported by VM | Check `JNI_OnLoad` and target JDK |
| `Native Library ... already loaded in another classloader` | JNI classloader | One JNI lib attempted to load in two classloaders | Choose a single classloader owner or redesign lifecycle |
| `IllegalCallerException` on JDK 24+ | Native access policy | Module lacks restricted JNI/FFM permission | `--enable-native-access=<module>`, review `--illegal-native-access` |
| Load succeeds, native call crashes with `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION` | During native execution | Wrong ABI/calling convention/pointer/lifetime | Header, alignment, native debugger/ASan |
| Load succeeds, native call crashes with `SIGILL` | During native execution | Binary uses CPU instruction unsupported by actual CPU | Compare CPU flags/compile target such as AVX2 |

**Actual messages vary by OS/JDK vendor:** the table above provides indicative clues, not a guaranteed 1-to-1 mapping. For example, Windows error 193 can be a corrupted binary format rather than just "wrong 32/64-bit". Read the entire cause chain and loader diagnostics before concluding.

## 11. Repeatable Debugging Workflow Locally and in CI

### Step 1 — Pin down the exact process and error

Record the actual `java` command, `java -version`, `os.name`, `os.arch`, `sun.arch.data.model` if available, OS/container image, and **stack trace / exact error message**. If the application runs through Gradle, Maven, an IDE, or Docker, run the probe **in that environment**, not just in your personal terminal.

### Step 2 — Identify the exact native file being loaded

From `System.loadLibrary("codec")`, predict `System.mapLibraryName("codec")` and find the **actual file**. If the application uses files packed inside a JAR, check the **extract-to-temp** code and whether the path is set correctly before loading. If using `System.load(absolutePath)`, verify that exact path. Do not tweak `java.library.path` when the error belongs to the OS dependent loader.

### Step 3 — Inspect OS/format/CPU/bitness without loading the binary

On Windows use `dumpbin /headers` or PowerShell PE header; on Linux use `readelf -h` and `file`; on macOS use `file`/`lipo -archs`. Match against the **process ABI**, not just host hardware. If mismatched: choose an artifact with a variant matching the JVM or rebuild with the right target toolchain.

### Step 4 — List native dependencies and runtime symbol versions

Use `dumpbin /dependents`, `readelf -d / --version-info`, `otool -L`. Verify child DLLs/SOs/dylibs **where it actually runs**; check libc/libstdc++/UCRT and OS search policy. Do not fix this error with the Java classpath, because the Java classpath only holds classes/JARs.

### Step 5 — Verify JNI symbols and API version

Regenerate the header with `javac -h`; compare `Java_<class>_<method>`, signatures, `JNIEXPORT`, `JNICALL`, `RegisterNatives`, and `JNI_OnLoad`. If `System.loadLibrary` already succeeded but the native method call fails, start from **export/binding** instead of rebuilding every library.

### Step 6 — Fix the right root-cause layer and re-verify

- Wrong OS/CPU/bitness: distribute the right library variant; do not rename.
- Wrong dependency or runtime ABI version: change runtime environment/dependency or build on a compatible baseline.
- Wrong JNI symbol: fix C function prototype/export or registration; rebuild.
- Wrong FFM ABI: fix `FunctionDescriptor` against the C header; add native call tests.
- Missing native access permission: grant permission to the right module on supported JDKs.
- Same JNI lib loaded in multiple classloaders: fix ownership/classloader lifecycle.

Then re-run the exact command in CI and a production-like image. Only consider it successful when **the library loads, the symbol binds, and the smoke-test call runs properly**.

## 12. Build/Release: Choosing Platform-Specific Artifacts Instead of One Shared File

A cross-platform Java release typically needs **multiple native artifacts**. Example layout of libraries by variant:

```text
app.jar
native/
  windows-x86_64/nativedoctor.dll
  windows-aarch64/nativedoctor.dll
  linux-x86_64-glibc/libnativedoctor.so
  linux-aarch64-glibc/libnativedoctor.so
  linux-x86_64-musl/libnativedoctor.so
  macos-aarch64/libnativedoctor.dylib
  macos-x86_64/libnativedoctor.dylib
```

**This is an illustrative package structure; it does not mean every project must ship all variants.** Choose the platforms supported and tested by the product. On macOS you can use a universal binary containing both arm64/x86_64 slices, but you must still verify dependent dylibs for **each slice**.

Useful release metadata:

| Attribute | Meaning |
| --- | --- |
| `os` | Windows/Linux/macOS |
| `arch` | x86_64/aarch64/x86… |
| `bits` | 32/64 |
| `binaryFormat` | PE/ELF/Mach-O |
| `cAbi` | LLP64/LP64/ILP32 per platform |
| `libcOrCrt` | glibc/musl/MSVC CRT version policy |
| `jniApi` | Minimum JNI API version if the library depends on it |
| `nativeAbiVersion` | Version of the C interface published by the library |
| `dependencies` | Native libraries and version requirements |
| `checksums` | Detect corrupted binary/wrong artifact |

A CI check should cover: Java process OS+CPU+bitness → binary header → native dependencies → `System.loadLibrary`/`System.load` smoke test → native symbol call → ABI/data roundtrip. Test failure conditions in a **separate process** because a wrong native ABI can crash the JVM; do not run intentionally malformed/mismatched binaries in a production server.

### Cross-compiling does not mean runtime-tested

A Linux host can cross-compile Windows ARM64 or Linux AArch64 binaries, but a successful build only proves the compiler produced a file. **Runtime tests are still required on the exact OS/CPU (or a supported and verified emulation environment)**. Java unit tests that do not call native code cannot detect missing child DLLs, symbol version mismatches, or wrong calling conventions.

## 13. Final Checklist Before Closing the Issue

- [ ] Identified the **exact Java process** using `java -version` and the actual application launcher.
- [ ] Recorded `os.name`, `os.arch`, process bitness (knowing `sun.arch.data.model` is not portable).
- [ ] Inspected the **actual library file** instead of relying on the extension or JAR name.
- [ ] OS format matches PE/ELF/Mach-O.
- [ ] CPU ISA and bitness match the JVM process; not just the host OS.
- [ ] Checked x86_64/AMD64 and AArch64/ARM64 aliases, Rosetta/containers.
- [ ] Header/loader tools confirm CPU, PE magic/ELF class/Mach-O slices.
- [ ] Correct native dependencies, OS search paths, and C/C++ runtime versions.
- [ ] Correct ABI: calling convention, C `long`, `size_t`, struct layout, and alignment.
- [ ] `javac -h` generates header for current Java source; C has proper exports/`RegisterNatives`.
- [ ] `JNI_OnLoad` only requests a JNI version supported by the JVM.
- [ ] No classloader ownership conflict for the JNI library.
- [ ] Did not confuse `--enable-native-access` with fixing CPU/ABI/format errors.
- [ ] Did not download DLL/SO from untrusted sources to "see if the error goes away".
- [ ] Ran end-to-end native smoke test in CI with the exact target image/OS/JVM.

## 14. Exercises and Self-Check Questions

1. A machine runs 64-bit Windows, but `sun.arch.data.model=32`; how many bits should the DLL you build for this JVM be?
2. Linux Java x86-64 reports `wrong ELF class: ELFCLASS32`. Which two files/headers do you check before modifying Java code?
3. An Apple Silicon Mac is running Java `os.arch=x86_64` via Rosetta. Is an arm64-only dylib suitable?
4. Why does `System.load(absolutePath)` help rule out part of `java.library.path` but **not rule out** missing dependency errors?
5. `dumpbin /headers` reports `Machine: 0xAA64` and `PE32+`. Can an `amd64` JVM running on Windows ARM64 load this DLL directly?
6. `System.loadLibrary` reports load OK, but Java calling `native int ping()` gets `UnsatisfiedLinkError`. Which tools and metadata should you inspect?
7. Why can `JNI_OnLoad` returning the wrong JNI version cause library loading to fail even when OS/CPU/bitness are all correct?
8. Does C `long` have the same width on Windows x64 and Linux x86-64? How does this affect FFM descriptors?
9. Why can a program load the right library yet crash with `SIGILL` when calling a native function?
10. An Alpine/musl environment fails to load an ELF built on glibc even though both are x86-64/ELF64. What do you inspect?
11. Does `jnativescan` or `--enable-native-access` solve `wrong ELF class`? Why or why not?
12. A JAR works in the IDE but fails in Docker: which fields should you compare first?
13. Why should **exit code 0** from a demo that intentionally catches `UnsatisfiedLinkError` not be treated as proof of successful loading?
14. When you see a loader error, by what signs do you determine whether it belongs to **search path**, **binary format**, **dependency**, **JNI initialization**, or **JNI method binding**?

**Remember:** When native library loading fails, compare in order: **OS/format → JVM process CPU architecture → bitness → native dependencies and ABI versions → JNI/FFM exports/signatures**. Keep the full error message to distinguish *file not found*, *wrong architecture file*, *missing/wrong-version dependency*, and *unbound native method*. A right library name and a 64-bit JVM do not prove ABI compatibility.

### Official Documentation and Further Reading

- [Oracle JDK 24 — JNI Design Overview: native loading, method naming, and linkage](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/design.html).
- [Oracle JDK 24 — JNI Invocation API: classloader, JNI_OnLoad, JNI versions](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/invocation.html).
- [Oracle JDK 24 — ClassLoader.findLibrary and java.library.path](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ClassLoader.html).
- [Oracle JDK 24 — Runtime.load: absolute library path](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Runtime.html).
- [Oracle JDK 24 — javac: -h header generation](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html).
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472).
- [Microsoft Learn — /HEADERS (DUMPBIN)](https://learn.microsoft.com/en-us/cpp/build/reference/headers?view=msvc-170).
- [Microsoft Learn — /DEPENDENTS (DUMPBIN)](https://learn.microsoft.com/en-us/cpp/build/reference/dependents?view=msvc-170).
- [Linux man-pages — ld.so(8): ELF loader and dependencies](https://man7.org/linux/man-pages/man8/ld.so.8.html).
- [Apple — Dynamic Library Programming Topics](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/000-Introduction/Introduction.html).

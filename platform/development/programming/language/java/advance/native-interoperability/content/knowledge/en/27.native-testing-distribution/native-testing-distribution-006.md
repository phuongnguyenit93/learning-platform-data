# Running the Supported JDK, OS, CPU, and Compiler Matrix

When a Java application calls a native library using **JNI (Java Native Interface)** or the **Foreign Function & Memory API (FFM)**, the Java part can compile and run on multiple platforms, while the C/C++ part is compiled into machine code that depends on the **operating system, CPU, ABI, and compiler**. Therefore, a successful `javac` run or a test running on a developer's machine **does not prove** that the native library works across all environments declared as supported.

**Objective:** identify the axes of the compatibility matrix; select meaningful JDK/OS/CPU/compiler combinations; design build, load, ABI, and behavior tests; run real JNI smoke tests across multiple platforms; automate CI; interpret results and decide when there is sufficient release evidence. The JDKs/OSes listed below are **examples of support policies**, not automatically the support list of a specific product.

## 1. What Does a Cell in the Compatibility Matrix Represent?

A native case corresponds to the tuple:

`(JDK vendor + version + patch, OS + OS version + libc, CPU + native ABI, compiler + version + flags, build type, native artifact version)`.

| Axis | Example | Risk if not tested |
| --- | --- | --- |
| **JDK** | Temurin 17, 21, 25; patch `17.0.x` | Java classfile/API, JNI/FFM behavior, module policy, runtime native access |
| **OS** | Ubuntu 24.04, Windows Server 2022, macOS 15 | ELF/PE/Mach-O, loader, library dependencies, minimum supported OS |
| **CPU** | AMD64/x86-64, AArch64/arm64 | Instruction set, calling convention, alignment, endianness, native binary architecture |
| **ABI / data model** | LP64, LLP64; glibc, musl | C `long`/`size_t`, struct layout, symbol names, ABI compatibility |
| **Compiler** | GCC, LLVM Clang, Apple Clang, MSVC | Compiler flags, optimizations, standard-library/CRT compatibility |
| **Build mode** | Debug, Release, sanitizer variants | Optimization-dependent undefined behavior, instrumented runtime requirements |
| **Distribution** | `libfoo.so`, `foo.dll`, `libfoo.dylib` | Packaging, dependency, code signing, search path, installed artifact |

Four pieces of evidence must be distinguished:

1. **Compile Java:** `javac` proves that the source conforms to a given Java release/API.
2. **Compile/link native:** the C/C++ compiler and linker can produce a library for the specific target OS/CPU/ABI.
3. **Load/link at runtime:** the JVM together with the OS loader can find the library, its dependencies, and JNI/FFM symbols.
4. **Execute + assert:** an actual JVM calls the native code and receives the expected result; additionally verifying layout, memory ownership, boundary errors, and concurrency.

**Cross-compiling for arm64 from an x64 machine only proves the build**, not that the library can execute on an arm64 CPU. If an emulator is used, clearly record it as **emulation evidence**; for critical targets, verify on appropriate hardware/runners.

## 2. Select Supported Combinations Before Multiplying the Matrix

Only build **valid and meaningful** tuples: do not pair MSVC to build an ELF library on Linux in a normal workflow; nor claim Linux/arm64 support just because Linux/x64 passed. Suppose there is a requirement to test JNI on **JDK 17, 21, 25**, sample environments could be:

| Target | Sample GitHub-hosted Runner | CPU | Compiler | Expected `sizeof(long)` on 64-bit target |
| --- | --- | --- | --- | --- |
| Linux/glibc | `ubuntu-24.04` | x64 | GCC | 8 (LP64) |
| Linux/glibc | `ubuntu-24.04` | x64 | Clang | 8 (LP64) |
| Linux/glibc | `ubuntu-24.04-arm` | arm64 | GCC | 8 (LP64) |
| Windows | `windows-2022` | x64 | MSVC/Visual Studio 2022 | 4 (LLP64) |
| macOS | `macos-15` | arm64 | Apple Clang | 8 (LP64) |
| macOS | `macos-15-intel` | x64 | Apple Clang | 8 (LP64) |

There are **3 JDKs × 6 targets = 18 jobs** for the JNI smoke test. The runner labels are examples based on GitHub-hosted runners and may change over time or depending on repository permissions. Read the **actual runner and toolchain information inside the job**, avoiding assumptions from `-latest`.

**JNI and FFM have different JDK scopes:** JNI works on JDK 17/21/25 in the example. FFM's `java.lang.foreign` API became a standard API starting in **JDK 22**; tests using the official FFM API must run on a compatible JDK ≥22. Do not pass Java FFM source meant for JDK 22+ to JDK 17/21 `javac` and treat compile errors as native ABI errors.

If **Alpine/musl** is supported, there must be a separate musl target: Linux/glibc x64 does not prove compatibility with Linux/musl x64. If **Windows/arm64**, **macOS/x64**, minimum OS versions, or CPU-specific optimizations are supported, all of them need evidence for the actual target.

## 3. Why Do Data Model and Compiler Matter?

Java `long` is always a 64-bit signed integer; C `long` varies across common ABIs:

| Type | Linux/macOS 64-bit (LP64) | Windows 64-bit (LLP64) |
| --- | --- | --- |
| `int` | 32 bit | 32 bit |
| `long` | 64 bit | 32 bit |
| `long long` | 64 bit | 64 bit |
| `void*`, `size_t` | Usually 64 bit | Usually 64 bit |
| JNI `jint` / `jlong` | 32 / 64 bit | 32 / 64 bit |

Therefore, do not declare Java `long` or FFM `ValueLayout.JAVA_LONG` for a C function based solely on the name `long`. With JNI, `jint` and `jlong` have fixed widths; with FFM, map according to the header, C ABI, and `Linker.nativeLinker().canonicalLayouts()` where applicable. For struct-by-value, callbacks, varargs, alignment, signedness, return types, and lifetime, mismatches can lead to wrong results or JVM crashes.

Differences beyond type sizes:

- **x64 vs arm64:** calling conventions, layout/alignment, vector instructions, and architecture-specific intrinsics differ; do not run an x64 binary as native arm64 just by renaming the file.
- **GCC vs Clang:** differ in code generation, optimizations, warnings, and extensions; C/C++ undefined behavior may only surface on one compiler or in Release mode.
- **MSVC vs MinGW:** both are on Windows, but may differ in compiler/CRT/C++ ABI and dependent libraries; do not arbitrarily mix C++ objects or allocator ownership.
- **macOS:** Xcode/Apple Clang, minimum deployment target, Mach-O architecture, universal binary slices, and signing policies can affect loading.
- **Linux:** glibc version, musl, `libstdc++`/`libc++`, `RPATH`/`RUNPATH`, and dependent `.so` files are part of compatibility.
- **JDK Distribution:** test the supported build (vendor/build/patch) and record `java -version`, because `--release` checks Java API/classfile rather than guaranteeing JVM/native loader behavior.

## 4. Complete Example: Java 17+ Calling JNI via a C Library

To have a **real** checkpoint on each OS/CPU/compiler, we use two native functions:

- `add(7, 5)` takes/returns JNI `jlong` and must return `12` on every target.
- `cLongBytes()` uses **the target's own C compiler** to measure `sizeof(long)`. On Linux/macOS x64/arm64 LP64 it expects `8`; on Windows/x64 LLP64 it expects `4`.

Standalone project structure:

~~~text
jni-matrix-demo/
├── CMakeLists.txt
├── src/demo/nativebridge/NativeMath.java
├── native/nativemath.c
├── .github/workflows/native-compatibility.yml
├── headers/       # generated from javac -h
├── out/           # generated from javac -d
└── build/         # generated from CMake
~~~

### 4.1. Java source — `src/demo/nativebridge/NativeMath.java`

~~~java
package demo.nativebridge;

import java.util.Locale;

public final class NativeMath {
    private NativeMath() {
    }

    static {
        System.loadLibrary("nativemath");
    }

    private static native long add(long left, long right);
    private static native int cLongBytes();

    public static void main(String[] args) {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: NativeMath <c-long-bytes> <x64|arm64>");
        }

        int expectedBytes = Integer.parseInt(args[0]);
        String expectedCpu = args[1];
        String actualArch = System.getProperty("os.arch", "")
                .toLowerCase(Locale.ROOT);

        boolean cpuMatches = switch (expectedCpu) {
            case "x64" -> actualArch.equals("amd64")
                    || actualArch.equals("x86_64");
            case "arm64" -> actualArch.equals("aarch64")
                    || actualArch.equals("arm64");
            default -> throw new IllegalArgumentException(
                    "Unknown expected CPU: " + expectedCpu);
        };

        if (!cpuMatches) {
            throw new AssertionError("Expected CPU " + expectedCpu
                    + " but JVM reports " + actualArch);
        }

        long result = add(7, 5);
        int actualBytes = cLongBytes();
        if (result != 12 || actualBytes != expectedBytes) {
            throw new AssertionError("JNI/ABI mismatch: result=" + result
                    + ", C long bytes=" + actualBytes
                    + ", expected=" + expectedBytes);
        }

        System.out.println("PASS sum=12; C long=" + actualBytes
                + " bytes; CPU=" + expectedCpu);
    }
}
~~~

`System.loadLibrary("nativemath")` looks up the library name appropriate for the target: typically `libnativemath.so` (Linux), `nativemath.dll` (Windows), `libnativemath.dylib` (macOS). `System.mapLibraryName("nativemath")` returns the name mapped by Java; **the loader must also be able to find native dependencies**. `os.arch` is the JVM architecture property, actively checked against the expected CPU from the CI matrix.

### 4.2. Generate JNI Header Directly from Java Source

Run in the root directory, with JDK 17+ and a shell with `mkdir -p`:

~~~bash
mkdir -p headers out
javac --release 17 -h headers -d out src/demo/nativebridge/NativeMath.java
~~~

`javac -h` generates `headers/demo_nativebridge_NativeMath.h`. Every time `native` declarations change, regenerate the header to avoid mismatched symbol names or parameter/calling conventions. `--release 17` locks Java API/classfile usage to Java 17 across JDK 17/21/25; it **does not affect the target's C binary ABI**.

### 4.3. C source — `native/nativemath.c`

~~~c
#include "demo_nativebridge_NativeMath.h"

JNIEXPORT jlong JNICALL
Java_demo_nativebridge_NativeMath_add(
        JNIEnv *env, jclass cls, jlong left, jlong right) {
    (void) env;
    (void) cls;
    return left + right;
}

JNIEXPORT jint JNICALL
Java_demo_nativebridge_NativeMath_cLongBytes(
        JNIEnv *env, jclass cls) {
    (void) env;
    (void) cls;
    return (jint) sizeof(long);
}
~~~

Because both Java methods are `static native`, the receiver parameter in C is `jclass`. The `JNIEXPORT` and `JNICALL` macros provided by the JNI headers ensure the correct symbol export/calling convention on the target. JNI's `jlong` is distinct from C `long`, so the test can genuinely verify the LP64/LLP64 difference. The example adds small numbers to avoid C signed overflow; for a real library, behavior at data type boundaries must be specified.

### 4.4. CMake — `CMakeLists.txt`

~~~cmake
cmake_minimum_required(VERSION 3.24)
project(jni_matrix LANGUAGES C)

find_package(JNI REQUIRED COMPONENTS JVM)

add_library(nativemath SHARED native/nativemath.c)
target_include_directories(nativemath PRIVATE
    "${PROJECT_SOURCE_DIR}/headers"
    ${JNI_INCLUDE_DIRS}
)

set_target_properties(nativemath PROPERTIES
    C_STANDARD 11
    C_STANDARD_REQUIRED YES
)
~~~

CMake `FindJNI` locates headers such as `jni.h` and `jni_md.h`, accepting `JAVA_HOME` as a hint to select the JDK; here there is no need to link a second JVM into the library. `COMPONENTS JVM` avoids unrelated AWT dependencies. Ensure the toolchain is actually the target's compiler; `add_library(... SHARED ...)` produces the library type appropriate for the platform.

### 4.5. Commands to Run on Linux/macOS and Windows

Linux/macOS x64, after generating the header:

~~~bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
java -Djava.library.path=build -cp out demo.nativebridge.NativeMath 8 x64
~~~

Expected output when running on **Linux/macOS x64 LP64**:

~~~text
PASS sum=12; C long=8 bytes; CPU=x64
~~~

For Linux/macOS arm64, replace `8 x64` with `8 arm64`. On **JDK 24+**, use `--enable-native-access=ALL-UNNAMED` with the JNI classpath to grant permission explicitly:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=build -cp out demo.nativebridge.NativeMath 8 arm64
~~~

The last command only succeeds when the JVM actually reports `arm64/aarch64`; on x64, `arm64` must be replaced with `x64`.

Windows/x64 with **Visual Studio 2022 C++ build tools** and **JDK 25**, running in PowerShell:

~~~powershell
New-Item -ItemType Directory -Force headers,out | Out-Null
javac --release 17 -h headers -d out src/demo/nativebridge/NativeMath.java
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
java --enable-native-access=ALL-UNNAMED -Djava.library.path=build/Release -cp out demo.nativebridge.NativeMath 4 x64
~~~

Expected output on Windows/x64:

~~~text
PASS sum=12; C long=4 bytes; CPU=x64
~~~

With JDK 17/21 on Windows, you can run the corresponding Java command **without** `--enable-native-access`. The CMake Visual Studio generator typically outputs `nativemath.dll` into `build/Release`; whereas Ninja or single-config generators may produce a different path. Check the actual output instead of hardcoding one path for all generators.

**Fixture limitations:** these two assertions prove part of the JNI/ABI load path and native execution. They do not verify struct padding, C++ ABI, buffer overflow, callbacks, ownership, races, packaged dependencies, or the security of another library.

## 5. 18-Job CI Matrix with GitHub Actions

The workflow example below runs the **3 JDKs × 6 platform/compiler targets** from section 2. The repository needs permission to use the runner labels, have CMake and the corresponding compiler on the image, and have the Temurin JDK for the selected CPU. Labels must be checked against the current runner list before use.

Create `.github/workflows/native-compatibility.yml`:

~~~yaml
name: Native compatibility

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  jni-smoke:
    name: "${{ matrix.platform.name }} / JDK ${{ matrix.jdk }}"
    runs-on: ${{ matrix.platform.runner }}
    strategy:
      fail-fast: false
      matrix:
        jdk: ['17', '21', '25']
        platform:
          - { name: linux-x64-gcc, runner: ubuntu-24.04, cc: gcc, cpu: x64, c_long: 8 }
          - { name: linux-x64-clang, runner: ubuntu-24.04, cc: clang, cpu: x64, c_long: 8 }
          - { name: linux-arm64-gcc, runner: ubuntu-24.04-arm, cc: gcc, cpu: arm64, c_long: 8 }
          - { name: windows-x64-msvc, runner: windows-2022, cc: none, cpu: x64, c_long: 4 }
          - { name: macos-arm64-clang, runner: macos-15, cc: none, cpu: arm64, c_long: 8 }
          - { name: macos-x64-clang, runner: macos-15-intel, cc: none, cpu: x64, c_long: 8 }

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ matrix.jdk }}

      - name: Compile Java and JNI header
        shell: bash
        run: |
          java -version
          javac -version
          cmake --version
          mkdir -p headers out
          javac --release 17 -h headers -d out src/demo/nativebridge/NativeMath.java

      - name: Compile native library
        shell: bash
        run: |
          if [ "$RUNNER_OS" = "Windows" ]; then
            cmake -S . -B build -G "Visual Studio 17 2022" -A x64
          elif [ "$RUNNER_OS" = "Linux" ]; then
            cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
              -DCMAKE_C_COMPILER=${{ matrix.platform.cc }}
          else
            cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
          fi
          cmake --build build --config Release

      - name: Exercise native library on target
        shell: bash
        run: |
          libdir=build
          if [ "$RUNNER_OS" = "Windows" ]; then
            libdir=build/Release
          fi

          native_access=()
          if [ "${{ matrix.jdk }}" -ge 24 ]; then
            native_access=(--enable-native-access=ALL-UNNAMED)
          fi

          java "${native_access[@]}" \
            -Djava.library.path="$libdir" \
            -cp out demo.nativebridge.NativeMath \
            ${{ matrix.platform.c_long }} ${{ matrix.platform.cpu }}
~~~

Explanation of the key parts:

- `matrix.jdk` creates three JDKs; `matrix.platform` contains six **valid combinations** of OS/CPU/compiler (Linux/x64 has two compilers). Each combination of the two lists creates one job.
- `runs-on` selects the **target runner**, not just the output file. `ubuntu-24.04-arm` and `macos-15` here are arm64 runners; `macos-15-intel` is an x64 runner.
- `actions/setup-java` installs Java on the runner. `javac --release 17` builds the shared Java API, while C is built per target/compiler.
- Windows selects `Visual Studio 17 2022 -A x64`. Linux GCC/Clang differ via `CMAKE_C_COMPILER`; Apple Clang is used on the macOS runner.
- The run step passes the expected `sizeof(long)` and CPU. If the JVM architecture does not match or the C ABI is wrong, Java throws `AssertionError`, causing the job to fail.
- JDK 24+ enables native access for the classpath to satisfy the JNI restricted operation policy. With named modules, a real product can use `--enable-native-access=<module>` for narrower grants.
- `fail-fast: false` keeps independent targets running to completion for a full report. **Do not** use `continue-on-error` for targets committed as supported; a failing target must fail the overall test suite.

The example CI does not yet pin **compiler patch version** or runner image revision. For reproducible releases, record `java -version`, CMake compiler identification/version, runner image revision, native dependencies, build flags, commit SHA, and binary hash. The label `ubuntu-24.04` does not guarantee a fixed compiler version forever.

## 6. Separate Matrix Required for FFM and New JDK Policies

JNI is a long-standing API; FFM in `java.lang.foreign` was standardized in **JDK 22**. FFM tests need to cover:

| Area | Why it must be tested separately |
| --- | --- |
| `Linker.nativeLinker()`/`SymbolLookup` | Symbol lookup and downcall handle creation according to the target's ABI |
| `FunctionDescriptor` | Parameter count, Java carriers, and C types must match the prototype/ABI |
| `canonicalLayouts()` | Widths of C `long`, `size_t`, and layouts under the current ABI |
| `MemorySegment`/`Arena` | Lifetime, allocation, alignment, bounds, and thread confinement |
| Struct/union/pointer | Padding, signedness, nullability, ownership, and return-by-value ABI |
| Callback/upcall | Calling convention, callback reference/lifetime, threads, exceptions |
| Native access | JDK 24+ JNI load/link, restricted FFM operations, and module permissions |

Do not use official JDK 22+ FFM source in JDK 17/21 jobs. If the product supports JDK 25 and newer JDKs, only add versions whose API/runtime usability has been confirmed.

**JDK 24** introduced a warning policy for native access when JNI loads/links a library without granted permission; in future releases, the policy may tighten. On supporting JDKs, test with `--illegal-native-access=deny` alongside the required `--enable-native-access` to ensure no module accidentally relies on ignored warnings. The native access flag permits native behavior; it **does not** certify C prototypes, native library safety, or ABI.

For C++, issues around `extern "C"` façades, name mangling, C++ exception boundaries, compiler runtimes, and cross-runtime memory ownership require separate testing. A simple C fixture passing **does not** certify C++ binary interoperability across MSVC, GCC, MinGW, and Apple Clang.

## 7. Practical Test Layers to Attach to Each Target

| Gate | What to run | PASS criteria |
| --- | --- | --- |
| **Toolchain** | Collect `java -version`, compiler/OS/CPU, build flags | Versions and architecture match the support list |
| **Java build** | `javac --release`, pure Java tests | Classfiles and Java APIs match baseline |
| **Native build/link** | `javac -h`, compiler warnings, linker, exported symbols | Binary matches OS/CPU, has required exports |
| **Loader smoke** | Actual `System.loadLibrary` or FFM `SymbolLookup` | No dependency, architecture, or naming errors |
| **ABI/behavior** | Type widths, struct layout, buffers, encoding, null, error codes | Correct results on each ABI |
| **Memory/lifetime** | JNI refs, FFM arenas/segments, malloc/free, callback cleanup | No use-after-free, double-free, or leaks |
| **Stress/concurrency** | Multi-threaded JNI/FFM, reentrant callbacks, cancellation | No races, deadlocks, crashes, or wrong results |
| **Distribution** | Test packaged artifact on clean machine/container | No accidental build-environment dependencies |
| **Diagnostics** | Save `hs_err_pid`/core when occurring, native symbols, and test reports | Failing jobs can be reproduced/investigated |

A test passing on a developer's machine does not replace CI. A test using **native code linked into the unit-test process** does not replace testing the **packaged artifact**. Tests with a risk of crashing the JVM should run in separate processes so one crash does not take down the rest of the test suite.

AddressSanitizer/UndefinedBehaviorSanitizer, compiler warning levels (e.g., `-Wall -Wextra` on GCC/Clang and `/W4` on MSVC), Debug/Release, heavy load, fuzzing, and native memory tools are very useful, but supported tool flags vary by compiler/OS. Use conditional supplementary jobs instead of forcing a single flag across all targets.

## 8. Verify the Actual Released Artifact

This is a frequently missed step: build and smoke tests succeed in `build/`, but the packaged file has the wrong path or is missing a runtime dependency.

1. **Clear naming and metadata:** `libfoo-linux-x64-glibc.so`, `foo-windows-x64.dll`, `libfoo-macos-arm64.dylib` are only naming examples. A name does not prove the file has the right architecture; metadata checks are required.
2. **Inspect binary/dependencies:** on Linux use `file`, `readelf -h/-d`, `nm -D`; on macOS use `file`, `otool -L`, `lipo -info` (if universal); on Windows use `dumpbin /HEADERS`/`DEPENDENTS`/`EXPORTS` or equivalent tools.
3. **Check native runtime:** Windows may be missing VC++ redistributable/dependent DLLs; Linux may be missing a glibc version or `libstdc++`; macOS may be missing a slice or be invalid for the minimum deployment target/signing.
4. **Run from the installation directory:** test the final JAR/binary in a clean environment, **without** pointing `java.library.path` to the build directory. If the JAR embeds native resources and extracts them to disk, also test extraction, file permissions, concurrency, integrity, and cleanup.
5. **Record provenance:** build SHA, compiler/build ID, native hash, version, supported target, tested JDK, and dependent libraries to reproduce post-release issues.

A release containing only a Linux/x64 binary cannot be labeled Linux/arm64 just because the Java JAR runs on both CPUs. A macOS universal binary may include multiple slices, yet loading and invocation must still be tested on **each CPU**.

## 9. Identifying Common Failures by Matrix Axis

| Symptom | Likely area to investigate | Evidence |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Built classfiles with a higher JDK than the runtime target | `javac --release` and `java -version` |
| `UnsatisfiedLinkError: no nativemath in java.library.path` | Wrong name/path or binary not found | `System.mapLibraryName`, output directory, installed artifact |
| `wrong ELF class`, Mach-O incompatible architecture, `not a valid Win32 application` | Wrong OS, CPU, or bitness of the native binary | `file`, `readelf`, `lipo`, `dumpbin`, JVM `os.arch` |
| Unresolved JNI function / symbol | C header does not match Java, wrong export name/mangling | `javac -h`, symbol table, C function name |
| Library present but still fails to load | Missing native dependency, compiler runtime, loader/signing policy | `readelf -d`, `otool -L`, `dumpbin /DEPENDENTS`, loader diagnostics |
| Fails only on Windows/x64 | Mistaking C `long` for 64-bit, calling convention, or MSVC CRT/C++ ABI | `sizeof(long)`, headers, structs, compile flags |
| Fails only on arm64 | CPU instructions/ABI, alignment, built for wrong architecture | Runner CPU, binary architecture, native tests |
| Java 24+ native access warning or `IllegalCallerException` | Module not granted JNI/FFM permission | `--enable-native-access`, `--illegal-native-access` |
| `SIGSEGV`, `EXCEPTION_ACCESS_VIOLATION` | Wrong pointer/lifetime/ABI or native memory corruption | `hs_err_pid`, native frames, core, sanitizers |
| Debug PASS, Release FAIL | Undefined behavior, race, optimizer, or uninitialized memory | Repro build flags, native sanitizers |
| CI PASS but customer FAIL | Did not test package/dependencies/min OS/libc | Clean VM/container test, artifact hashes |

Do not "fix" a failing job by disabling the test, accepting the error, or only re-running an easy-to-pass target. Determine whether the failure relates to JDK, OS, CPU, compiler, or a **combination** of axes; sometimes there is no single culprit.

## 10. Managing Matrix Cost While Preserving the Support Contract

A matrix of hundreds of jobs can be costly in time and money. It can be split:

- **PR smoke:** minimum JDK, primary deployment JDK, latest supported JDK; all critical OS/CPUs and primary compilers. Changes to JNI/FFM/headers/ABI require a fuller matrix.
- **Nightly/weekly:** compiler variants, JDK patch levels, Debug/Release, sanitizers, stress/fuzz, less common targets; retain historical results to spot regressions.
- **Pre-release:** run on **all tuples actually declared as supported** and the exact candidate artifact being released. Block the release if a required tuple FAILs or has no result.
- **Toolchain/JDK upgrades:** run old and new versions in parallel, comparing compiler flags, runtime loader, ABI layout, and crash signatures; only update the support statement once evidence is in place.

Pairwise/combinatorial reduction is useful for **secondary variables** when the matrix is too large, but does not automatically substitute for an OS/CPU/JDK/compiler target declared as supported. A combination that has not been run must report **NOT_VERIFIED**, never be treated as PASS.

The table below is **illustrative mock data**, not actual CI results:

| JDK | Target | Build | Load | ABI | Package | Conclusion |
| --- | --- | --- | --- | --- | --- | --- |
| 17 | linux-x64-gcc | PASS | PASS | PASS | PASS | SUPPORTED |
| 21 | windows-x64-msvc | PASS | PASS | PASS | PASS | SUPPORTED |
| 25 | macos-arm64-clang | PASS | PASS | PASS | NOT_RUN | NOT_VERIFIED |
| 25 | linux-arm64-gcc | PASS | FAIL | NOT_RUN | NOT_RUN | FAIL |

CI should record **actual versions** (JDK vendor/build, compiler identity/version, OS image revision, native artifact checksum), signal/crash logs if any, and pass/fail for each gate. `fail-fast: false` helps reveal all failures across targets; it is not a reason to ignore errors.

## 11. Decision Process for "Supported"

1. **Lock the support contract:** list JDK distribution/version, minimum OS and libc, CPU, compiler/toolchain, native library version, and actual combinations.
2. **Generate the native contract:** keep Java `native` declarations and `javac -h` headers in sync; for FFM, verify C prototypes, `FunctionDescriptor`/layouts, and ownership.
3. **Build for the right target:** verify Java baseline, compiler version/flags, binary architecture, exported symbols, and dependencies.
4. **Run JVM-native smoke:** load on the actual target, invoke methods, and assert results/ABI; do not just run the compiler.
5. **Run substantive tests:** buffers/structs/callbacks, boundary errors, multithreading, memory lifetime, JNI references/FFM arenas, and negative tests in isolated processes.
6. **Verify the package:** install the exact artifact to be released in a clean environment, checking runtime dependencies and loading paths.
7. **Evaluate each tuple:** PASS when all gates pass, FAIL if any gate fails, NOT_VERIFIED if evidence is missing. Do not infer PASS from a similar OS/CPU/JDK.
8. **Keep an audit trail:** versions, SHA/build IDs, CI job logs, and test artifacts to distinguish regressions from JDK/compiler/OS vs native source when incidents occur.

## 12. Self-Check

**1.** Java builds on Windows/x64, but `libfoo.so` from Linux/x64 fails to load. Why?  
Because Java bytecode is more platform-independent, whereas a Linux ELF native binary is not a Windows DLL/PE, even though both use an x64 CPU.

**2.** Is C `long` the same size on Linux/x64 and Windows/x64?  
No. LP64 common on 64-bit Linux/macOS has an 8-byte `long`, while LLP64 on 64-bit Windows has a 4-byte `long`; Java `long` is always 8 bytes.

**3.** Does a successful ARM64 cross-compile prove that ARM64 runtime will PASS?  
No. You must verify the loader and actually run on an appropriate ARM64 target, explicitly noting emulation if only run under an emulator.

**4.** Does JNI smoke PASS on JDK 17/21 prove FFM compatibility on JDK 25?  
No. The official FFM API is in JDK 22+ and requires separate tests for linkers, descriptors, layouts, arenas, and callbacks.

**5.** Why run both GCC and Clang on the same Linux/x64?  
Compiler optimizations, diagnostics, extensions, and undefined behavior can differ; one compiler passing does not guarantee the other will.

**6.** Compile/load passes across the matrix, but the package is missing a dependent DLL; can it be declared SUPPORTED yet?  
Not yet. You must run the distributed artifact in a clean environment and verify dependencies.

**7.** There is no macOS/arm64 runner, yet the product documentation commits to supporting it; what result should be recorded?  
`NOT_VERIFIED`; add the runner/hardware and test or adjust the support statement—do not substitute macOS/x64 results.

## References

- [Oracle – JNI Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/index.html) — JNI types, native method names/binding.
- [Oracle – `javac` tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — `--release` and `-h`.
- [OpenJDK JEP 454 – Foreign Function & Memory API](https://openjdk.org/jeps/454) — FFM standardized in JDK 22.
- [OpenJDK JEP 472 – Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472) — JNI native access restrictions starting in JDK 24.
- [CMake FindJNI](https://cmake.org/cmake/help/latest/module/FindJNI.html) — finding JNI headers and libraries.
- [GitHub Actions – Choosing runners](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) — runner OS/CPU labels.
- [GitHub Actions – Matrix strategy](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs) — how to create a CI matrix.

**Technical conclusion:** a JDK/OS/CPU/compiler combination is only considered supported when there is evidence of **build, load, ABI, execution, and distribution** on that exact target. A compatibility matrix is a verifiable QA contract, not a list of operating system names.
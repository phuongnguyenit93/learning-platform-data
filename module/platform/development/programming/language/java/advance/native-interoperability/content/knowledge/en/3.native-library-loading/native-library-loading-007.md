# Selecting a native library version based on the actual operating system, CPU, and ABI

## Objectives

When a Java program needs to load a native library via JNI, JNA, or the Foreign Function & Memory API, having the same library name is not enough to guarantee it can be loaded. A `bridge.dll`, `libbridge.so`, or `libbridge.dylib` file must be compatible with the **running JVM process** and the operating system's library loader.

After this lesson, you can:

- Distinguish between the operating system, CPU architecture, the architecture of the **JVM process**, ABI, C runtime, and dependent libraries.
- Select the right binary according to the actual set of conditions, even when the operating system or physical CPU supports emulating another architecture.
- Understand why even on the same Linux/x86-64, there can still be incompatibilities between glibc and musl, or between two sets of native libraries with different symbols/runtimes.
- Establish packaging conventions, version checks, and library loading with `System.load`/`System.loadLibrary` in a diagnosable manner.
- Write a clear Java 17 variant selector, check for unsupported cases, and handle loading errors instead of blindly trying multiple binaries.

## 1. What does a native variant actually depend on?

A native library is compiled machine code, unlike `.class` bytecode in a JAR. The JVM does not recompile `.so`/`.dll`/`.dylib` files to fix an incompatible architecture or ABI. Check at least the following dimensions:

| Dimension | What to match | Example |
|---|---|---|
| **OS and binary format** | Windows PE/COFF, Linux ELF, macOS Mach-O, Android's own environment | Windows DLL cannot be loaded directly like Linux ELF |
| **Process architecture** | x86 32-bit, x86-64, AArch64/ARM64; the architecture on which the current JVM is executing | An x86-64 JVM needs x86-64 native code or a compatible slice |
| **ABI and calling convention** | Platform C ABI, data types, alignment, symbol names, parameter passing/returning convention, JNI convention | Windows x86 has calling convention differences compared to x64 |
| **Runtime and dependencies** | glibc/musl, MSVC runtime, libstdc++/libc++, dependent libraries, and required release versions | `GLIBC_2.34 not found` even though both are Linux x86-64 |
| **Additional constraints** | Minimum OS version, CPU instruction set (AVX2, NEON…), security/code signing, and library API/ABI version | A binary compiled with AVX2 may fail on older x86-64 CPUs |

**Decision principle:** the selected target must be compatible with the **process and runtime loader**, not just the machine name or a “64-bit” label. Operating system, architecture, libc, ABI, dependencies, and minimum CPU level combine into **a variant that has been built and tested**.

A general naming convention is `<os>-<arch>-<abi>`, for example `linux-x86_64-glibc`, `linux-aarch64-musl`, `windows-x86_64-msvc`, or `macos-aarch64-darwin`. This is a **project-defined distribution convention**, not a mandatory standard that the JVM automatically understands.

## 2. The operating system does not determine the entire variant

### Windows

- The library is usually `bridge.dll` (PE/COFF); it must match the exact x86, x86-64, or ARM64 architecture of the executing JVM.
- The binary may depend on Microsoft Visual C++ Runtime or other DLLs. A DLL with the right architecture but missing dependencies still cannot be loaded.
- On Windows x86 32-bit, calling conventions, export/decorated names, and `JNICALL` must be respected; do not assume C++ mangling or exported symbol names are identical across all toolchains.
- Windows ARM64 can support emulated processes; an **x64 JVM running via emulation** still needs an x64 DLL matching that process, and does not automatically switch to an ARM64 DLL just because the physical CPU is ARM64.

### Linux

- The library is usually `libbridge.so` (ELF); it must match the process's ELF class/`e_machine` and ABI.
- **glibc and musl are two different runtime/ABI choices.** Two files both for `linux-x86_64` and named `libbridge.so` are not interchangeable by default; the dynamic loader, symbols, and dependent libraries may differ.
- For binaries built on glibc, pay attention to the **minimum glibc level** and the linked symbol versions. Building on a newer distro and running on an older distro can fail immediately upon loading.
- A `.so` file may depend on `libstdc++.so`, `libgcc_s.so`, OpenSSL, or other `.so` files. Compatibility with the JVM is not enough if the dependency tree does not match.
- `linux-armv7` can also distinguish between hard-float/soft-float ABIs; ARM 32-bit, AArch64, and x86-64 are different targets. Do not lump all ARM or all Linux into a single binary.

### macOS

- JNI libraries typically use `libbridge.dylib` (Mach-O); an x86-64 JVM and an arm64 JVM need the appropriate architecture slice.
- A **universal/fat binary** can contain multiple slices, such as both x86_64 and arm64; you must check which slices the binary actually contains.
- An Apple Silicon Mac running an x86-64 JVM via Rosetta 2 still loads the **x86_64 slice**; running an arm64 JVM loads the arm64 slice.
- Minimum macOS version, dependencies, code signing, and the application's runtime policies can affect loading. A Mach-O file for the right CPU may still be unusable.
- `System.mapLibraryName` gives a filename suitable for the current platform, but does not evaluate slices, deployment target, or dependent libraries.

### Android is not synonymous with desktop Linux

Android uses ELF, but its libc is typically **Bionic**, with JNI packaged inside APK/AAB according to Android ABIs (`arm64-v8a`, `armeabi-v7a`, `x86_64`...). Do not take `linux-aarch64-glibc` and treat it as a valid Android binary. When developing for Android, choose Android's packaging model and loading APIs instead of applying the desktop/server JDK workflow verbatim.

## 3. Physical CPU, OS, and JVM architecture: which one is the source of truth?

A 64-bit machine can run multiple types of processes. For native code loaded **into the same Java process**, the most important factor is the binary architecture of that JVM:

~~~text
Physical machine                 JVM process                Library to load
--------------------------------------------------------------------------------
Windows x64                      JVM x64                    DLL x64
Windows x64 (if still supported) JVM x86 32-bit             DLL x86 32-bit
Apple Silicon arm64              JVM arm64                  Mach-O arm64
Apple Silicon arm64 + Rosetta    JVM x86_64                 Mach-O x86_64
Linux aarch64 + emulation        Emulated JVM x86_64        ELF x86_64 matching that environment
~~~

`System.getProperty("os.arch")` is a useful starting point for the **Java runtime architecture**; do not replace it with a CPU marketing name, the host's `uname -m` info, or just looking at the OS bitness. The property has aliases: `amd64` and `x86_64` usually both refer to x86-64; `aarch64` and `arm64` both refer to ARM64. Normalize aliases and **reject unsupported architectures**.

Check with Java directly in the target runtime environment:

~~~java
System.out.println("os.name = " + System.getProperty("os.name"));
System.out.println("os.arch = " + System.getProperty("os.arch"));
System.out.println("os.version = " + System.getProperty("os.version"));
System.out.println("java.vm.name = " + System.getProperty("java.vm.name"));
~~~

In the terminal, you can also inspect the runtime:

~~~bash
java -XshowSettings:properties -version
~~~

These properties **do not fully prove the ABI**: there is no portable Java SE `native.libc` property for glibc/musl, and `os.arch` does not check symbol versions, CPU features, or dependencies. The missing pieces must come from build/deployment target configuration, trusted native metadata, or verified environment checks.

Do not modify `-Dos.arch` or `-Dos.name` just to force Java to pick another variant: changing the property string **does not change the actual architecture of the JVM**.

## 4. Actual ABI: why checking only the CPU name is still insufficient?

The ABI defines the machine-level contract between compiled code: data type sizes and alignment, how arguments are placed, return values, stack/register usage, calling convention, symbol names/linkage, and runtime conditions. JNI enforces the `JNIEnv*` interface and corresponding conventions, but the native library is still an ELF/PE/Mach-O subject to target rules.

Even with the same `x86_64`, the following cases can differ:

1. **Linux glibc versus Linux musl:** different loader/runtime; confirm which libc type the build variant actually links against.
2. **Newer versus older glibc:** a file using `GLIBC_2.xx` symbols that the target lacks will fail; do not just compare `ldd --version` and conclude all dependencies are valid.
3. **C++ runtime/ABI:** `libstdc++`/`libc++`, `GLIBCXX_*` versions, compiler flags, and exported C++ APIs can impose their own constraints. A stable JNI/C wrapper API helps reduce C++ ABI coupling between sides, but does not eliminate dependencies.
4. **ARM32 hard-float/soft-float:** both may carry an ARM 32-bit label, yet have different floating-point parameter passing conventions.
5. **Instruction set:** building with `-march=native` or AVX2 can produce code that cannot run on CPUs that only meet the baseline of the same architecture family.

For libraries exchanging C structs or callbacks, you also need C type widths, alignment, padding, byte order, function signatures, and memory ownership. Do not use `os.arch` to infer all of these. If the library publishes its own ABI version, check that version **in addition to** OS/CPU/libc.

## 5. Release conventions: clear, verifiable variants

Package multiple binaries side by side with fixed paths; do not place variants at the same path and swap them at runtime:

~~~text
distribution/
└── native/
    ├── linux/
    │   ├── x86_64/
    │   │   ├── glibc/libbridge.so
    │   │   └── musl/libbridge.so
    │   └── aarch64/
    │       ├── glibc/libbridge.so
    │       └── musl/libbridge.so
    ├── windows/
    │   └── x86_64/msvc/bridge.dll
    └── macos/
        ├── x86_64/darwin/libbridge.dylib
        └── aarch64/darwin/libbridge.dylib
~~~

The diagram represents **the planned release variants**; each path only exists if the corresponding target has been built and tested. `msvc` is the label for the Windows package using the MSVC runtime chosen by the project. `darwin` is a packaging label in the example; macOS also has its own deployment target and slice checks.

A release should include a manifest or metadata for **each artifact**, containing:

- Library API/ABI version and release version; target OS, CPU, libc/toolchain, and process bitness.
- Minimum runtime such as glibc, macOS deployment target, MSVC runtime, or specific dependencies; baseline CPU features.
- File name/path, list of required accompanying dependent libraries, and the artifact's SHA-256 hash for integrity verification.
- CI status indicating it was built/tested on the corresponding target. **Do not create an entry if the artifact does not exist yet**, and do not pick the “closest” version when no matching entry is found.

A package may contain a universal binary on macOS or a statically linked library for the right target; in that case, the manifest must accurately describe the actual structure. The paths above are a transparent organizational scheme, not a hard Java requirement.

### Sample support matrix

| Target runtime | Selected binary | Additional conditions |
|---|---|---|
| Linux JVM x86-64 + glibc | `linux/x86_64/glibc/libbridge.so` | Check glibc version and dependencies |
| Linux JVM x86-64 + musl | `linux/x86_64/musl/libbridge.so` | Built/linked for musl |
| Linux JVM ARM64 + glibc | `linux/aarch64/glibc/libbridge.so` | Do not use ARMv7 build |
| Windows JVM x64 | `windows/x86_64/msvc/bridge.dll` | Matching runtime DLL and exports |
| macOS JVM arm64 | `macos/aarch64/darwin/libbridge.dylib` | arm64 slice, deployment target, and code signing if needed |
| macOS x86-64 via Rosetta | `macos/x86_64/darwin/libbridge.dylib` | Verify the JVM is running x86-64 |

If there is no package in the matrix, the application reports that the target is unsupported rather than trying a file from another OS/ABI.

## 6. Java 17 example: selecting a binary by explicit target

The following program normalizes OS/CPU names, requires explicitly specifying glibc/musl for Linux, allows previewing the selection result **without needing a native library**, and provides a method to load from a verified distribution directory. The library name is `bridge`; `relativePath()` follows the example structure above.

Save to `NativeVariantSelector.java`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class NativeVariantSelector {

    record Target(String os, String arch, String abi) {
        String relativePath() {
            String fileName = switch (os) {
                case "linux" -> "libbridge.so";
                case "windows" -> "bridge.dll";
                case "macos" -> "libbridge.dylib";
                default -> throw new IllegalStateException(os);
            };
            return "native/" + os + "/" + arch + "/" + abi + "/" + fileName;
        }
    }

    static String normalizeOs(String value) {
        String os = value.toLowerCase(Locale.ROOT);
        if (os.startsWith("windows")) {
            return "windows";
        }
        if (os.startsWith("mac") || os.startsWith("darwin")) {
            return "macos";
        }
        if (os.equals("linux")) {
            return "linux";
        }
        throw new IllegalArgumentException("Unsupported OS: " + value);
    }

    static String normalizeArch(String value) {
        return switch (value.toLowerCase(Locale.ROOT)) {
            case "amd64", "x86_64" -> "x86_64";
            case "aarch64", "arm64" -> "aarch64";
            case "x86", "i386", "i486", "i586", "i686" -> "x86";
            default -> throw new IllegalArgumentException(
                    "Unsupported JVM architecture: " + value);
        };
    }

    static Target choose(String osName, String archName, String linuxLibc) {
        String os = normalizeOs(osName);
        String arch = normalizeArch(archName);

        String abi = switch (os) {
            case "linux" -> switch (linuxLibc.toLowerCase(Locale.ROOT)) {
                case "glibc" -> "glibc";
                case "musl" -> "musl";
                default -> throw new IllegalArgumentException(
                        "Linux requires native.libc=glibc or musl");
            };
            case "windows" -> "msvc";
            case "macos" -> "darwin";
            default -> throw new IllegalStateException(os);
        };

        return new Target(os, arch, abi);
    }

    static void loadFromDistribution(Path directory, Target target)
            throws IOException {
        // Use a path that has been normalized and actually exists.
        Path root = directory.toRealPath();
        Path binary = root.resolve(target.relativePath()).toRealPath();

        // Disallow symbolic links leading outside the distribution directory.
        if (!binary.startsWith(root) || !Files.isRegularFile(binary)) {
            throw new IOException("Invalid native binary path: " + binary);
        }

        // Call only after the artifact, checksum, and ABI conditions have been verified.
        System.load(binary.toString());
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 0) {
            // Dry run of selection logic: fixed result across all JVMs.
            System.out.println(choose("Linux", "amd64", "glibc")
                    .relativePath());
            System.out.println(choose("Linux", "aarch64", "musl")
                    .relativePath());
            System.out.println(choose("Mac OS X", "arm64", "")
                    .relativePath());
            System.out.println(choose("Windows 11", "amd64", "")
                    .relativePath());
            return;
        }

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java NativeVariantSelector [distributionDir]");
        }

        // Actual load: select according to the current JVM, do not use a simulated target.
        Target runtime = choose(
                System.getProperty("os.name"),
                System.getProperty("os.arch"),
                System.getProperty("native.libc", ""));
        loadFromDistribution(Path.of(args[0]), runtime);
        System.out.println("Loaded: " + runtime.relativePath());
    }
}
~~~

Compile and run the **selection logic check**:

~~~bash
javac NativeVariantSelector.java
java NativeVariantSelector
~~~

Exact output:

~~~text
native/linux/x86_64/glibc/libbridge.so
native/linux/aarch64/musl/libbridge.so
native/macos/aarch64/darwin/libbridge.dylib
native/windows/x86_64/msvc/bridge.dll
~~~

This is a **variant selection dry run**, not proof that any native file has been loaded or can run. The inputs are explicitly specified so that the sample run output does not depend on the learner's OS.

When you have a real library and a `distribution/` directory containing the matching package, for example on **Linux glibc**:

~~~bash
java -Dnative.libc=glibc NativeVariantSelector distribution
~~~

If the binary is loaded successfully, the last line looks like:

~~~text
Loaded: native/linux/x86_64/glibc/libbridge.so
~~~

This illustrative output applies to a **Linux x86-64 glibc JVM**, when the file and dependencies actually exist. In another environment, the message reflects the running target, or the program may fail intentionally when no matching artifact is available.

### Key points to understand about the example

1. Pure Java `choose(...)` only **selects a path name**. It does not auto-detect Linux libc, check the CPU instruction set, dependencies, or binary format. `native.libc` must be provided by a trusted build/deployment; if unclear, fail fast.
2. Common aliases are normalized intentionally. Other targets (`riscv64`, `ppc64le`, ARM32…) report unsupported, **without guessing**. `choose` also does not verify that the release manifest has all packages; `toRealPath` at the load step will report missing files.
3. During actual loading, `System.load(...)` takes an absolute path to an **existing native file**. `toRealPath` resolves the real path and checks that symlinks stay within root, but **does not replace signature/SHA-256 verification or artifact source auditing**.
4. The example uses the project's hypothetical `msvc` and `darwin` paths. In a real build, the manifest must record the available variants and the runtime conditions that these three labels do not express.
5. Do not try loading another variant after a load failure: the error message should be preserved to determine whether there is an architecture mismatch, missing dependency, or faulty native build. Trying the wrong variant can cause hard-to-diagnose errors.

## 7. How do `System.loadLibrary` and `System.load` differ?

The two APIs are related, but have different input contracts:

~~~java
// Logical name, without prefix/suffix and not a file path.
System.loadLibrary("bridge");

// Absolute path to a specific native file.
System.load("/opt/app/native/linux/x86_64/glibc/libbridge.so");
~~~

| API | Advantages | What needs to be controlled |
|---|---|---|
| `System.loadLibrary("bridge")` | Concise library name; the JVM locates the file using the platform/JVM native library search mechanism and maps the name | `java.library.path`, search path, actual file selected, dependencies; hard to express the entire ABI matrix through a single name |
| `System.load("/absolute/path/...")` | Specifies the exact top-level file decided by the selector | Must resolve the file/path and verify a trusted source; the OS linker still needs to find dependencies |

`System.mapLibraryName("bridge")` helps obtain the conventional filename for the **current platform** (for example `libbridge.so` on Linux), but **does not automatically choose glibc/musl, another architecture, CPU features, or library version**.

`java.library.path` is not a smart repository containing native build metadata; mutating this property at runtime should not be used as a version selection mechanism. Furthermore, a binary may already be loaded or bound to a class loader; loading/unloading/hot-swapping is not as free as replacing a JAR file. If a major ABI version change is needed, the safe approach is usually to start a new process with the tested set of binaries.

### Libraries inside a JAR

A native file placed at `src/main/resources/native/...` and packaged into a JAR is a **resource**, not yet a file on the filesystem that `System.load` can directly use as a DLL/ELF/Mach-O. The typical workflow is:

1. Select the matching resource entry according to the verified target and manifest.
2. Extract to a file location with appropriate permissions and a name separated by version/architecture; verify the binary's hash.
3. Handle file paths, symbolic links, and write permissions to prevent another process from replacing the library between verification and loading.
4. Call `System.load` with the absolute path; clean up temporary files according to the application lifecycle, noting that Windows may hold a loaded DLL until the process exits.

Do not download and execute native libraries from an untrusted URL at startup, and do not extract multiple versions with the same name into a shared directory prone to race conditions.

## 8. Inspecting binaries and dependencies before loading

A build must carry **evidence of the actual target**. Folder names can be mislabeled; inspecting the header is an independent check.

### Linux (ELF)

~~~bash
file libbridge.so
readelf -h libbridge.so
readelf -d libbridge.so
readelf --version-info libbridge.so
~~~

In `readelf -h`, look at `Class` (ELF32/ELF64) and `Machine`; in the dynamic section, look at `NEEDED`, and `RPATH`/`RUNPATH` if present; in version info, check `GLIBC_*` or other symbol version requirements. `readelf` displays metadata and does not need to execute the file being inspected. For binaries from untrusted sources, do not run `ldd` on them by default: some `ldd` environments/implementations can lead to code execution.

### macOS (Mach-O)

~~~bash
file libbridge.dylib
lipo -info libbridge.dylib
otool -hv libbridge.dylib
otool -L libbridge.dylib
~~~

`lipo -info` lists the available architecture slices, and `otool -L` lists dependencies; when needed, check the minimum OS and code signature with tools appropriate for the macOS environment. A universal binary does not guarantee that every slice has the right ABI/dependencies required.

### Windows (PE)

In a Developer Command Prompt with Visual Studio tools:

~~~bat
dumpbin /headers bridge.dll
dumpbin /dependents bridge.dll
dumpbin /exports bridge.dll
~~~

Check the machine type (x86/x64/ARM64), dependent DLLs, and exported JNI symbols. The exact runtime DLL is required; having the same `.dll` filename and extension does not prove the same architecture.

### Matching against the JVM

- Check `java -XshowSettings:properties -version` to know the architecture/JVM that is running; do not just read the host OS architecture.
- In Linux containers, check the libc and runtime of the **container/process** where the JVM actually runs. The host using glibc does not mean an Alpine container using musl does as well.
- If the app uses multiple `.so` files in the same bundle, check **transitive dependencies** and the system libraries actually found by the loader. A top-level file with the right target can still fail because a dependent file has the wrong architecture.

## 9. Handling load errors: going from message to root cause

Java typically throws `UnsatisfiedLinkError` when it cannot load/resolve a native library, but the specific errors vary widely:

| Message/symptom | Possibilities to check | Remediation |
|---|---|---|
| `no bridge in java.library.path` | `System.loadLibrary` did not find the top-level library on the search path | Confirm logical name, mapping, path/packaging |
| `Can't load IA 32-bit .dll on a AMD 64-bit platform` or equivalent | 32/64-bit architecture mismatch between JVM and DLL | Match machine type with the current JVM |
| `wrong ELF class: ELFCLASS32` | Loading ELF32 into a process requiring ELF64 | Select the right architecture/bitness |
| `invalid ELF header`, `not a valid Win32 application`, `wrong architecture` | Wrong format, corrupted binary, or wrong target | Read PE/ELF/Mach-O header and checksum |
| `GLIBC_2.xx not found` | Binary requires newer glibc symbols than the environment provides | Rebuild on an appropriate baseline or upgrade the runtime per policy |
| `libstdc++.so.6: cannot open shared object file` | Missing dependency or loader cannot find it | Check `NEEDED` and package/configure dependency search paths |
| `undefined symbol` | Missing/mismatched exported symbol or ABI/native dependency | Check exports, JNI name/signature, linked versions |
| `SIGILL` after load or when calling a function | Binary uses unsupported CPU instructions | Confirm baseline/CPU features and build flags |
| JNI symbol error only appears when calling a method | JNI entry point/signature mismatch even though the library loaded | Use `javac -h` to generate JNI headers, check `JNIEXPORT`/`JNICALL` |

Sample messages are indicators **to be verified**, not the sole diagnosis for every platform. Even when the OS loader reports that `bridge.dll` cannot be found, the top-level file may exist while **a dependency** is missing; you must inspect the message and dependency tools.

Application handling pattern:

~~~java
try {
    System.load(absoluteTrustedLibraryPath);
} catch (UnsatisfiedLinkError error) {
    // Log os.name, os.arch, target/variant, the selected path,
    // error code, and full message; do not swallow the cause.
    throw new IllegalStateException(
            "Cannot load native variant for current JVM", error);
}
~~~

This is an **illustrative snippet** inside a method that already has the `absoluteTrustedLibraryPath` variable; it is not a standalone Java program. Avoid automatically catching every `UnsatisfiedLinkError` to try a file of another ABI, as that hides incompatibilities and can make startup unpredictable.

## 10. Testing with a matrix instead of just a successful build

A successfully compiled artifact is not yet proven compatible at load time. There should be two independent test groups:

**Selector tests (no native library required):**

| Input OS/arch/libc | Expected result |
|---|---|
| `Linux` / `amd64` / `glibc` | `linux/x86_64/glibc` |
| `Linux` / `aarch64` / `musl` | `linux/aarch64/musl` |
| `Mac OS X` / `arm64` / empty | `macos/aarch64/darwin` |
| `Windows 11` / `amd64` / empty | `windows/x86_64/msvc` |
| `Linux` / `amd64` / empty | Clear error: missing libc selection |
| `Linux` / `riscv64` / `glibc` | Clear error: unsupported architecture |

**Native tests on real targets:** for each release variant, run the corresponding JVM, call `System.load` or `System.loadLibrary`, execute a JNI/FFM function with fixed input–output, and check dependencies, minimum runtime, and missing/wrong artifact scenarios. If Windows ARM64, macOS Rosetta, or Alpine musl is supported, there must be corresponding tests rather than inferring from a single x86-64 glibc CI.

In CI, retain the manifest, SHA-256, compiler/toolchain, sysroot, architecture flags, output of binary inspection tools, and smoke test results. Updating a `.so` file without updating this information will make ABI bugs difficult to reproduce.

## 11. Workflow for applying to an application

1. **Define the support matrix**: OS, JVM arch, libc/runtime, minimum OS, CPU baseline, and released ABI version; explicitly list unsupported environments.
2. **Build for the right target and verify**: compile with a controlled toolchain/sysroot; inspect headers, symbols/dependencies, and run real smoke tests for each target.
3. **Package explicitly**: each variant has its own resource path/name, manifest/version/checksum; do not mix binaries from different platforms.
4. **Identify the runtime**: normalize `os.name` and `os.arch`; obtain libc/ABI information from a trusted configured source, do not guess from the physical CPU.
5. **Match against the manifest**: only accept a variant with an existing artifact, compatible runtime/CPU level, and valid checksum; reject unsupported targets with a specific message.
6. **Load one selected file**: extract if inside a JAR, resolve the path safely, call `System.load` once; ensure the loader can find the corresponding dependencies.
7. **Log useful diagnostics and run regression tests**: log target and version, real path, and loader messages; test on all declared supported JVMs/OSes.

## 12. Practical scenarios

**Scenario A — running Docker Alpine.** On an Ubuntu x86-64 host, a Java application runs **inside an Alpine Linux container**. `os.name=Linux` and `os.arch=amd64` may look the same as the host, but Alpine typically uses musl. The selector must obtain the container runtime's libc info and select `linux/x86_64/musl` (if built) or report unsupported. Do not select glibc just because the host is Ubuntu.

**Scenario B — Apple Silicon Mac running Rosetta.** The physical Mac is ARM64, but the application runs an x86-64 JVM under Rosetta 2. The native library needs the x86_64 slice; switching to an arm64 JDK/JVM requires the arm64 slice. Do not use a rule that reads machine hardware info to force loading arm64 inside an x86-64 JVM process.

**Scenario C — same x86-64/glibc but different distro.** A `.so` file built on a very new Linux release requires `GLIBC_2.37`, while the runtime only has older symbols. Both the architecture and libc family match, yet the loader still rejects it. The solution is to build against a supported glibc baseline, or intentionally change the runtime requirement, then run smoke tests.

**Scenario D — Windows x64 missing a dependent DLL.** `bridge.dll` matches the JVM's x64 architecture but fails to load. `dumpbin /dependents` shows that the runtime DLL or a companion library is not present; the corresponding dependency must be added/configured. Trying a 32-bit x86 `bridge.dll` will not fix that error.

## 13. Self-check questions

1. An ARM64 machine runs an x86-64 JVM under an emulator. Which native binary should be selected? **The binary for the process's x86-64**, with compatible OS/ABI and dependencies.
2. Does `os.arch=amd64` prove that a Linux library requires glibc instead of musl? **No.** Independent libc/runtime information is required.
3. Does `System.mapLibraryName("bridge")` determine the right ABI version? **No.** It only maps the library name according to the current platform's rules.
4. Why might `linux-x86_64-glibc` still be insufficient to identify a loadable artifact? **It lacks the glibc level, C++/native dependencies, ABI version, and CPU baseline.**
5. When `System.loadLibrary("bridge")` throws an error, should you loop through other DLLs/SOs in an arbitrary order? **No.** Diagnose the cause and select using a verified manifest.
6. Does placing `libbridge.so` inside a JAR allow `System.load` to accept a resource path inside the JAR? **No.** An actual file on the filesystem or another appropriate packaging/loading method is required.

## Key takeaways

- **The native library must match the JVM process**, OS loader, ABI, runtime dependencies, and supported CPU level. “Both 64-bit” is not a sufficient condition.
- On Linux, **distinguish glibc/musl** and check symbol versions; on macOS, consider the JVM's slice and deployment target; on Windows, consider the PE machine type, runtime DLLs, and exports.
- `System.loadLibrary` and `System.load` load libraries using two different identification methods; neither **automatically fixes an ABI mismatch**.
- **Select the variant using a clear manifest, verify the real binary, then load in a controlled manner**. If no matching build exists, report unsupported instead of guessing or forcing a load.

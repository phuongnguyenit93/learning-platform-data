# Missing C Compiler, Linker, Headers, or System Libraries

## 1. Why Does Native Image Need a C/C++ Toolchain?

Building a Spring Boot application into a GraalVM Native Image is not just compiling Java source code. Spring AOT prepares initialization code and metadata; Native Image performs reachability analysis, generates machine code, and links it into an executable for the target OS/architecture. This process requires a compatible native toolchain, typically including a C compiler, linker, system headers, and platform development libraries.

Consequently, a project can compile Java and run its JAR successfully yet fail the native build because the machine lacks GCC/Clang, a linker, the Windows SDK, Xcode Command Line Tools, or system libraries. This is a build environment issue, not necessarily a Spring AOT or RuntimeHints bug.

Within the **SPRING_BOOT_NATIVE_IMAGE** module, this lesson helps identify each toolchain component, install the right ones for Linux/Windows/macOS, check PATH and environment variables, distinguish compiler errors from dependency errors, and standardize native builds in CI. Exact requirements vary by GraalVM distribution, version, OS, and target architecture; always consult the documentation for your specific version.

## 2. Components of the Native Toolchain

| Component | Role | Examples |
|---|---|---|
| C compiler | Compiles C code and runtime/native support components | GCC, Clang, MSVC |
| Linker | Combines object files and libraries into an executable | GNU ld, lld, Apple ld, MSVC linker |
| Assembler | Converts assembly into object code | GNU as, integrated assembler |
| System headers | Declare OS and library APIs/structs/constants | libc headers, Windows SDK headers |
| System libraries | Provide implementations for the linker to link against | libc, libpthread, or platform-specific runtime libraries |
| Development packages | Provide headers, linker metadata, and symlinks | libc-dev, zlib-devel |
| Build utilities | Supporting toolchain utilities | make, pkg-config, archiver |
| SDK/platform tools | Target platform APIs and libraries | Windows SDK, Xcode SDK |

Not every project needs every package in this table installed separately. Some distributions bundle or require specific toolchains; some native builds use the system compiler/linker. Check the official prerequisites before installing packages.

## 3. Distinguish the Java Compiler from the C Compiler

The JDK provides `javac` to compile Java source code into bytecode. The fact that `javac -version` works does not prove a C compiler or linker is present.

Different verification commands:

```bash
java -version
javac -version
native-image --version
cc --version
gcc --version
clang --version
ld --version
```

Some commands may not exist if the distribution does not use that tool. For instance, a machine using Clang may not have GCC; macOS uses Apple's linker rather than GNU ld. On Windows, the MSVC toolchain is checked via the Developer Command Prompt and `cl.exe`, not `gcc`.

Identify the compiler that Native Image actually detects from the build log. Do not arbitrarily install multiple compilers at once hoping the build picks the right one.

## 4. Read Error Messages to Identify Which Component Is Missing

Common errors:

| Message or symptom | Likely missing component |
|---|---|
| `C compiler not found` | GCC/Clang/MSVC or compiler is not on PATH |
| `Unable to execute gcc` | Compiler not installed, wrong PATH, or incomplete shell environment |
| `linker command failed` | Missing linker, wrong toolchain, or incompatibility |
| `ld: cannot find -l...` | Missing library or development package |
| `fatal error: ...h: No such file` | Missing system/development headers |
| `cannot find crt1.o` / `Scrt1.o` | Missing C runtime development files or linker search path |
| `undefined reference to ...` | Missing library, wrong link order/flags, or ABI mismatch |
| `cannot find -lz` | Missing zlib development library/linker metadata |
| `Windows SDK not found` | Missing or unselected Windows SDK |
| `xcrun: error: invalid active developer path` | Xcode Command Line Tools not installed or not selected |
| `unsupported target architecture` | Toolchain/SDK does not support the chosen target |

Messages may vary by GraalVM version and linker. Look for the first error in the build log, not just the final "build failed" line. Later errors may simply be consequences of an initial missing prerequisite.

## 5. Linux: Install Basic Compiler and Linker

On Debian/Ubuntu, the standard toolkit is `build-essential`:

```bash
sudo apt-get update
sudo apt-get install -y build-essential
```

This package typically installs GCC/G++, make, and core build components. Depending on Native Image prerequisites and dependencies, you may need extra development packages such as zlib:

```bash
sudo apt-get install -y zlib1g-dev
```

On Fedora/RHEL-family distributions, equivalent package groups may include:

```bash
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y zlib-devel
```

Package names and package managers vary by distribution/version. Some Enterprise Linux releases require enabling specific repositories or installing compiler packages separately. Check the GraalVM documentation and the OS image being used.

Do not install packages into a production runtime image just to fix a build. The C compiler and headers normally belong in the builder stage or CI runner and do not need to be included in the final container image.

## 6. Linux: Verify Compiler, Linker, and Headers

After installing the toolchain:

```bash
which cc
which gcc
which ld
cc --version
gcc --version
ld --version
```

Test that the compiler can compile and link a minimal program:

```bash
cat > /tmp/toolchain-check.c <<'EOF'
#include <stdio.h>

int main(void) {
    puts("native toolchain ready");
    return 0;
}
EOF

cc /tmp/toolchain-check.c -o /tmp/toolchain-check
/tmp/toolchain-check
```

If the compiler runs but cannot find `stdio.h`, system headers or development packages may be missing. If compilation succeeds but linking fails, inspect the linker, C runtime files, and library search paths.

This is a smoke test for the C toolchain. It does not prove every prerequisite of GraalVM Native Image or specific dependencies is satisfied; the actual native build remains the final verification step.

## 7. zlib and System Development Libraries

Some Native Image toolchains or dependencies may require zlib development files. Distinguish between:
- Runtime library: shared object used when the executable runs.
- Development package: headers and linker metadata needed at build time.
- Static library: `.a` archive if the build/link mode requires it.
- Runtime package: package providing files needed in the final image.

For example, on Debian/Ubuntu it is `zlib1g-dev`; on Fedora/RHEL it is typically `zlib-devel`. Exact names and requirements depend on the OS and GraalVM version.

Do not install a list of libraries out of habit if the compiler does not ask for them. Read the `-lxxx` or missing header error, identify the package providing that file, and install the corresponding development package. Then verify that the linker finds the library for the right architecture and sysroot.

## 8. pkg-config and Library Search Paths

Some native dependencies use `pkg-config` to obtain compiler/linker flags:

```bash
pkg-config --version
pkg-config --cflags --libs zlib
```

If the command cannot find a package, the development package may be missing or the `.pc` file may not be in the search path. The `PKG_CONFIG_PATH` environment variable adds metadata directories, but avoid setting arbitrary paths before locating the package.

Variables such as `CPATH`, `C_INCLUDE_PATH`, `LIBRARY_PATH`, or `LD_LIBRARY_PATH` can affect compiler/linker/runtime resolution. Use them intentionally, document them in CI, and avoid global overrides that make local builds diverge from CI.

Do not use `LD_LIBRARY_PATH` to patch a build-time linker error when the real problem is a missing development package. The linker search path and the dynamic loader runtime path are two different stages.

## 9. Linux: Check Architecture and Sysroot

The toolchain must produce binaries for the appropriate target. Inspect:

```bash
uname -m
cc -dumpmachine
file /usr/bin/cc
```

If the build container is `linux/amd64` but you want to produce a `linux/arm64` artifact, a standard host-native compiler may not cross-compile automatically. You need a toolchain/sysroot and cross-compilation setup supported by GraalVM/Native Image for that target.

Do not confuse the host architecture with the builder container or target image architecture. In multi-arch CI, declare the platform explicitly for each job and verify the executable's ELF machine type.

## 10. Windows: Visual Studio Build Tools and Windows SDK

On Windows, Native Image typically requires the Microsoft C/C++ toolchain corresponding to the GraalVM release, including the MSVC compiler/linker and Windows SDK. Install Visual Studio or Visual Studio Build Tools with the **Desktop development with C++** workload and the appropriate Windows SDK component.

After installation, open **x64 Native Tools Command Prompt for Visual Studio** or the corresponding Developer PowerShell. Check:

```powershell
cl
where.exe cl
where.exe link
where.exe rc
```

`cl.exe` is the compiler, `link.exe` is the linker, and `rc.exe` is the resource compiler typically bundled with the SDK. These tools must belong to the same desired toolchain/architecture.

A regular terminal may lack Visual Studio environment variables such as INCLUDE/LIB/PATH. If the build fails saying the compiler cannot be found even though it is installed, try the proper Developer Command Prompt before reinstalling.

## 11. Windows: Check SDK Headers and Libraries

MSVC requires Windows SDK headers/libraries. If errors report missing `windows.h`, missing system libraries at link time, or missing SDK versions, inspect Visual Studio Installer:

- Desktop development with C++ workload.
- MSVC toolset matching the architecture.
- Supported Windows 10/11 SDK version.
- CMake/Ninja if required by the build workflow.
- Environment variables configured by the Developer Command Prompt.

Do not manually copy SDK directories into PATH/INCLUDE when Visual Studio provides official environment scripts. Use the installer and corresponding command prompt to avoid mixing SDK versions.

Native Image on Windows has specific prerequisites per GraalVM distribution/version. Check official documentation before choosing a Visual Studio toolset; do not assume every JDK/GraalVM release supports the same compiler version.

## 12. macOS: Xcode Command Line Tools

On macOS, the native toolchain typically comes from Xcode or Xcode Command Line Tools, containing Clang, the linker, and macOS SDK headers/libraries.

Install if missing:

```bash
xcode-select --install
```

Check:

```bash
xcode-select -p
xcrun --find clang
clang --version
xcrun --show-sdk-path
```

If the developer directory points to an old or non-existent Xcode, reselect the Xcode/Command Line Tools path via `xcode-select` per Apple's instructions. Do not manually set SDKROOT to an incompatible SDK.

macOS supports both Intel and Apple Silicon. Verify the architecture of GraalVM, the JDK, the compiler, and the target binary; avoid mixing an x86_64 toolchain with an arm64 build outside supported cross-compilation workflows.

## 13. PATH and Environment Variables in CI

A common issue is that the compiler is installed, yet the native job cannot see it because its PATH differs from the installation shell. Check directly inside the exact job and step running the build:

Linux/macOS:

```bash
command -v cc
command -v gcc
command -v clang
printf '%s\n' "$PATH"
```

Windows PowerShell:

```powershell
Get-Command cl -ErrorAction SilentlyContinue
Get-Command link -ErrorAction SilentlyContinue
$env:PATH
```

Do not check only on the runner host if the build runs inside a container. The compiler must exist in the exact build environment where the Native Image compiler executes. In multi-job CI pipelines, each job has its own filesystem/environment; installing a toolchain in an earlier job does not automatically make it available in a later job.

## 14. Distinguish Compiler Errors from Linker Errors

The compiler translates source code into object files; the linker combines object files and libraries into an executable. Signs to distinguish them:

- Compiler not found: error occurs before compilation starts.
- Header not found: compiler starts, but preprocessing/compilation fails.
- Undefined symbol: object files were produced, but the linker cannot find an implementation.
- Library not found: linker cannot locate a library file.
- ABI mismatch: library was found, but symbols/architecture/version are incompatible.

When the linker reports `undefined reference`, find the symbol and the library that provides it. Check library argument ordering if using static linking, architecture, and ABI. Do not add random libraries or disable linker checks to bypass the error.

## 15. Verify the Native Toolchain GraalVM Actually Uses

Having multiple compilers on one machine can cause the build to pick the wrong toolchain. Check:
- GraalVM distribution/version and `native-image` executable path.
- The compiler detected by Native Image in the build log.
- PATH/INCLUDE/LIB/SDKROOT inside the build process.
- Target architecture and linker.
- Whether the compiler version falls within the supported range of the GraalVM release.

On Linux, you can check:

```bash
command -v native-image
command -v cc
command -v ld
native-image --version
```

On Windows:

```powershell
Get-Command native-image
Get-Command cl
Get-Command link
native-image --version
```

If the Maven/Gradle plugin runs inside a daemon or separate process, ensure the daemon was started from an environment with the right toolchain. After changing PATH/toolchains, stop/restart the build daemon so the old process does not retain stale environment variables.

## 16. Toolchain in the Docker Builder Stage

If the native build runs inside Docker, the compiler and development packages must be in the builder stage:

```dockerfile
FROM build-image AS build
WORKDIR /workspace

# Install compiler and development packages for the builder OS.
# Then run Maven/Gradle and the Native Image build.
COPY . .
RUN ./mvnw -Pnative -DskipTests package

FROM runtime-image AS runtime
WORKDIR /app
COPY --from=build /workspace/target/orders-service /app/orders-service
USER 10001:10001
ENTRYPOINT ["/app/orders-service"]
```

This is an illustrative structure; `build-image` must contain GraalVM and the required native toolchain prerequisites. Do not copy compilers, headers, or package managers into the final runtime image if the application does not need them at runtime.

The builder and runtime images can differ, but binary ABI, libc, and shared library dependencies must be compatible. Succeeding in the builder does not guarantee the final image has all runtime libraries; test the final image separately.

## 17. CI Runner: Standardize Prerequisites

A reliable native job should include a toolchain check step before running Maven/Gradle:

```bash
set -euo pipefail

java -version
native-image --version
cc --version
ld --version

./mvnw -Pnative -DskipTests package
```

This example is for a Linux runner with `cc` and `ld`; on macOS use `clang`/Apple linker, and on Windows use MSVC checks. Do not use the same compiler check script across all OSes without appropriate platform branches.

Pin the builder image or runner image by version. If installing packages inside the job, record package versions and repository sources. This keeps native builds reproducible and helps investigate issues when runner images update.

## 18. Diagnose Missing Header or Library Errors

When encountering a specific error:

1. Grab the first error line naming the header/library.
2. Identify the running compiler/linker and target architecture.
3. Find the OS package providing that file.
4. Install the development package in the builder/CI environment.
5. Verify that the header and library files exist.
6. Check compiler/linker search paths.
7. Run a minimal C smoke test if needed.
8. Re-run the native build and save the logs.

Linux example:

```bash
# Search package by filename on Debian-family if apt-file is installed/updated
apt-file search zlib.h
```

Package lookup tools depend on the distribution and repository. Do not install a runtime package when the compiler needs headers; install the corresponding development package.

If a symbol is missing, the package may already be installed, but its version/ABI does not match. Verify library version and architecture before altering linker flags.

## 19. Common Errors and Remedies

| Symptom | Likely cause | Remedy |
|---|---|---|
| Java compile passes, native build reports compiler missing | JDK has javac but no C toolchain | Install compiler/linker for the OS |
| GCC exists on host but job cannot see it | Build runs in a different container/job or different PATH | Check inside the exact process environment |
| `stdio.h` not found | Missing libc development headers | Install development package |
| `zlib.h` not found | Missing zlib development package | Install the OS-appropriate package |
| `cannot find -lz` | Missing zlib library/linker metadata | Install zlib development package, check architecture |
| `crt1.o` missing | Incomplete C runtime development files or sysroot | Install toolchain/libc dev packages and check sysroot |
| Windows cannot find `cl.exe` | Terminal does not have MSVC environment initialized | Use Developer Command Prompt |
| macOS invalid developer path | Xcode tools not installed or wrongly selected | Install/select Command Line Tools |
| Linker undefined symbols | Missing library, ABI mismatch, or wrong link flags | Identify symbol/provider and version |
| Binary builds but final container fails | Missing runtime shared libraries/loader | Inspect ELF dependencies and final image |

## 20. Hands-on Exercise: Prepare the Toolchain for a Native Build

**Context:** Order API builds a JAR successfully in CI, but the native job fails because the compiler or system libraries are missing.

**Step 1 — Identify the platform.** Record OS, architecture, GraalVM distribution/version, and build tool version.

**Step 2 — Check compiler/linker.** Run the appropriate commands: `cc/gcc/clang/ld`, MSVC `cl/link`, or Xcode `clang/xcrun`.

**Step 3 — Check headers.** Create a C smoke test including `stdio.h`; if it fails, check development headers.

**Step 4 — Resolve missing libraries.** Read the specific `-l...` or header error, install the development package for the right distribution/architecture.

**Step 5 — Verify build environment.** Verify PATH, INCLUDE/LIB, or SDK path inside the same job/container running Native Image.

**Step 6 — Run native build.** Run the Maven/Gradle native task with pinned toolchains; save the build log and compiler identity.

**Step 7 — Inspect executable.** Verify architecture, dynamic loader, and shared library dependencies.

**Step 8 — Verify final image.** Run the executable inside the runtime image and confirm all required runtime libraries are present.

Completion criteria: platform-appropriate compiler/linker/headers; Native Image detects the right toolchain; native build completes; binary has the right architecture; final image runs with minimal runtime dependencies.

## 21. Conclusion

A Native Image build requires a native toolchain alongside the JDK: a C compiler, linker, system headers, and appropriate development libraries. Linux typically uses GCC/Clang with development packages; Windows requires MSVC and the Windows SDK; macOS uses Xcode Command Line Tools. Exact versions and prerequisites must match the GraalVM distribution/release in use.

When a build fails, distinguish between compiler, header, linker, library, ABI, and PATH errors. Check directly inside the runner/container performing the native build, install development packages in the builder stage, and verify both the executable and the final runtime image separately. A successful JAR build only proves the Java pipeline works; it does not prove the native toolchain is ready.

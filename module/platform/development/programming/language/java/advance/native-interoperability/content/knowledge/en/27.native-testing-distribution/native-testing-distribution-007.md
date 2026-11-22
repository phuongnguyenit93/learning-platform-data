# Packaging Native Libraries with Dependencies and Runtime Access Guidelines

## 1. Why does native Java need a separate release package?

Java code in a JAR is relatively independent of the operating system, whereas code running through **JNI** (Java Native Interface) or **FFM** (Foreign Function & Memory API) depends on platform binaries and dynamic loaders. In addition to `app.jar`, a product may require `.so` (Linux), `.dll` (Windows), `.dylib` (macOS), dependent native libraries, C/C++ runtimes, the appropriate CPU/ABI, a launcher, and JVM **native access** configuration.

A program that runs on the build machine can still fail after distribution: copying only the JNI bridge while forgetting a dependency, building for the wrong CPU, requiring a newer `glibc` version than the target machine, placing a DLL in a directory not searched by the loader, extracting libraries to storage that blocks executable mapping, or failing to grant native access permission to the Java module on newer JDKs.

There are **three distinct layers** that must be configured and verified:

1. **Distribution:** releasing all native artifacts for the right OS, CPU, ABI, version, license, and checksum.
2. **Library loading:** the JVM locates the *primary library* via `System.load`/`System.loadLibrary` or FFM; the OS loader locates *dependent libraries* according to its own rules.
3. **Runtime permissions:** the JVM allows the Java module to perform native operations; the operating system permits reading/mapping binaries, verifies signatures, and enforces sandboxing if present.

This article guides you through a Linux package that runs on **Java 17+**, then compares Windows, macOS, resource-embedded JARs, `jpackage`, and JDK 24+.

## 2. Clearly defining artifacts and the platform matrix

A Linux release with native libraries can be laid out as follows:

```text
demo-release/
├── app.jar
├── native/
│   ├── libbridgejni.so
│   └── libhelper.so
├── licenses/
│   └── THIRD_PARTY_NOTICES.txt
└── bin/
    └── run.sh
```

Use a separate package for each supported platform combination, rather than assuming a JAR makes native binaries portable:

```text
artifacts/
├── demo-linux-x86_64-glibc.tar.gz
├── demo-linux-aarch64-glibc.tar.gz
├── demo-linux-x86_64-musl.tar.gz
├── demo-windows-x86_64.zip
├── demo-macos-aarch64.zip
└── demo-macos-x86_64.zip
```

This is an **example naming convention**, not an implication that a project must build every variant. For macOS, a universal binary can be chosen if all dependencies are compatible. A release bundle needs to record:

| Attribute | Must be known before release |
| --- | --- |
| OS/CPU | Linux, Windows, macOS; `x86_64`, `aarch64`, standardized architecture names |
| ABI | `glibc`/`musl`, minimum macOS, MSVC runtime, calling convention, and library versions |
| JDK | Java bytecode target, JNI/FFM version used, launcher, and actual runtime |
| Native dependencies | Direct/transitive dependencies that must be bundled or provided by the target environment |
| Security & compliance | Hashes/signatures, build provenance, file permissions, dependency licenses/notices |
| Lifecycle | Who loads/unloads, installation path, whether a class loader/FFM Arena is still using the binary |

Having the same `os.arch` value is not enough to determine compatibility: two Linux `x86_64` systems with different `glibc`/`musl` or CPU baselines may still fail to run the same binary. When distributing via Maven/Gradle, classifiers or variants by OS/arch/ABI are a clear way to represent different builds.

## 3. Distinguishing primary library lookup from dependency lookup

For example, consider two C libraries:

```text
Java class NativeMath
    |
    | System.load("/opt/demo/native/libbridgejni.so")
    v
libbridgejni.so              <- JNI bridge
    |
    | ELF DT_NEEDED: libhelper.so
    v
libhelper.so                 <- dependency
    |
    v
libc / OS runtime
```

**Stage 1 – JVM loads the bridge:** `System.load("/absolute/path/libbridgejni.so")` loads the specified file; `System.loadLibrary("bridgejni")` uses a logical name and the JVM/class loader's native library lookup rules.

**Stage 2 – Dynamic loader loads dependencies:** the OS reads the bridge's metadata and locates `libhelper.so` on its own. `java.library.path` serves the JVM when locating the primary library in many situations, but **does not replace the OS's dependency lookup mechanism**. Passing an absolute path to `System.load` also **does not guarantee** that dependencies will be found.

| API | Correct input | Meaning |
| --- | --- | --- |
| `System.load` | **Absolute** path to the native file | Selects the exact file to load |
| `System.loadLibrary` | Logical name such as `"bridgejni"` | JVM resolves the platform-specific native filename |
| `System.mapLibraryName` | `"bridgejni"` | Returns `libbridgejni.so` on Linux, `bridgejni.dll` on Windows, etc. |
| `SymbolLookup.libraryLookup` | `Path` or library name and `Arena` (FFM, JDK 22+) | Loads and looks up symbols via the OS; lifecycle tied to Arena |

Do not pass `"libbridgejni.so"` or `"/opt/app/native/libbridgejni.so"` to `System.loadLibrary`. With JNI, the specification states that a JNI native library is bound to a class loader; the same JNI library cannot be loaded as a JNI library for **two different class loaders**. Therefore, plugin/hot-reload applications need to design a layer that owns the native bridge, rather than relying on repeatedly loading the same library from every plugin.

FFM `SymbolLookup.libraryLookup` has its own lifecycle mechanism via `Arena` and is a restricted operation; it **does not** eliminate requirements around ABI, dependencies, and runtime permissions.

## 4. Operating system dependency lookup rules

### 4.1. Linux: `DT_NEEDED`, `RUNPATH`, `RPATH`, and `$ORIGIN`

On Linux systems using ELF, direct dependencies are typically recorded in `DT_NEEDED`. The dynamic linker searches sources such as `DT_RPATH`/`DT_RUNPATH`, `LD_LIBRARY_PATH`, the loader cache, and system directories, depending on configuration and secure-execution mode.

A good layout when bundling a helper alongside a JNI bridge is to link the bridge with:

```bash
-Wl,-rpath,'$ORIGIN'
```

At runtime, `$ORIGIN` represents the **directory containing the ELF object being examined**, not the current working directory. Single quotes protect the token from shell expansion at build time. With common GNU linkers, this flag records `DT_RUNPATH=$ORIGIN`, enabling the bridge to find **direct** dependencies in the same directory.

**Common pitfall:** `DT_RUNPATH` only applies to finding direct dependencies of the object that has the RUNPATH; if `libhelper.so` needs `libthird.so`, you must check `libhelper.so`'s search path or choose an appropriate loader strategy. Do not assume a RUNPATH on the bridge guarantees all transitive dependencies.

Use `readelf -d` to inspect `NEEDED`, `SONAME`, `RPATH`, and `RUNPATH`. You can set `LD_LIBRARY_PATH` for debugging, but avoid using it as the sole deployment mechanism: it easily collides with system versions and can be ignored in secure-execution mode.

### 4.2. macOS: install name, `@loader_path`, and `@rpath`

macOS uses Mach-O and `dyld`. Dependent binaries have an install name or references using tokens:

- `@loader_path`: relative to the location of the binary making the reference.
- `@rpath`: resolved against declared runpaths.
- `@executable_path`: relative to the main executable where applicable.

If a library needs a helper located next to it, a relative dependency like `@loader_path/libhelper.dylib` can be suitable. Use `otool -L` to read dependencies and `otool -l` to read load commands; when releasing, also consider **codesign, hardened runtime, notarization, and loader rules**. Do not expect `DYLD_LIBRARY_PATH` to work in all protected modes.

### 4.3. Windows: DLL search order and native runtime

Windows has KnownDLLs, API sets, SxS, application/system directories, the process search path, and `LoadLibraryEx` modes. **An absolute path to the primary DLL does not guarantee that all dependent DLLs will automatically be found in the same directory.** When you control the native launcher/loader, consider safe mechanisms such as `LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR`, `SetDefaultDllDirectories`, and `AddDllDirectory` to establish the search path.

Do not add directories writable by untrusted users to `PATH` or the process-wide search path. For C++ binaries requiring the Microsoft Visual C++ runtime, you must verify versions and redistributable rules; `jpackage` does not automatically resolve every extra dependency an application has.

## 5. Working demo: JNI bridge depending on another shared library

The following demo creates **app.jar + libbridgejni.so + libhelper.so**, running on Linux with JDK 17+ and a GNU-compatible C toolchain.

### 5.1. File `src/NativeMath.java`

```java
import java.nio.file.Files;
import java.nio.file.Path;

public final class NativeMath {
    static {
        String nativeDir = System.getProperty("demo.native.dir");
        if (nativeDir == null || nativeDir.isBlank()) {
            throw new IllegalStateException(
                    "Set -Ddemo.native.dir to the native directory");
        }

        Path bridge = Path.of(nativeDir)
                .toAbsolutePath()
                .normalize()
                .resolve(System.mapLibraryName("bridgejni"));

        if (!Files.isRegularFile(bridge)) {
            throw new IllegalStateException(
                    "JNI library is missing: " + bridge);
        }
        System.load(bridge.toString());
    }

    private static native int answer();

    public static void main(String[] args) {
        System.out.println("Native answer = " + answer());
    }
}
```

The code proactively takes the path from the launcher, converts it to an absolute path, and loads the exact library. `Files.isRegularFile` only reports missing files early; **it does not prove the file is safe or has the right architecture**.

### 5.2. File `native/helper.c`

```c
/* Native dependency, does not use JNI. */
int helper_answer(void) {
    return 42;
}
```

### 5.3. File `native/bridgejni.c`

```c
#include "NativeMath.h"

/* Exported by libhelper.so. */
extern int helper_answer(void);

JNIEXPORT jint JNICALL
Java_NativeMath_answer(JNIEnv *env, jclass cls) {
    (void)env;
    (void)cls;
    return (jint)helper_answer();
}
```

The `NativeMath.h` header is generated by `javac -h`, ensuring JNI names match the bytecode. The example uses the Java default package so the JNI symbol here is `Java_NativeMath_answer`; with packages or overloads, use the corresponding generated header and do not guess symbol names.

### 5.4. Building Java and C on Linux

Requires `javac`, `jar`, `cc`/`gcc`, `readelf`, and `JAVA_HOME` pointing to a JDK with `include` headers.

```bash
mkdir -p build/classes build/headers dist/native

# Compile Java 17-compatible class and generate JNI header.
javac --release 17 \
  -h build/headers -d build/classes src/NativeMath.java

# Build the dependency library.
cc -fPIC -shared \
  -Wl,-soname,libhelper.so \
  -o dist/native/libhelper.so native/helper.c

# Build the JNI bridge; link to helper and set RUNPATH next to the bridge.
cc -fPIC -shared \
  -Ibuild/headers \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/bridgejni.c \
  -Ldist/native -lhelper \
  -Wl,-rpath,'$ORIGIN' \
  -o dist/native/libbridgejni.so

# JAR contains classes, while native libraries remain separate files.
jar --create --file dist/app.jar \
  --main-class NativeMath -C build/classes .

# Inspect ELF dependencies and runtime path.
readelf -d dist/native/libbridgejni.so | grep -E 'NEEDED|RUNPATH|RPATH'
```

With common GNU-compatible linkers, `readelf` should show `NEEDED` referencing `libhelper.so` and `RUNPATH` containing `$ORIGIN`. Output may include additional system libraries depending on the toolchain. If `NEEDED` is missing, check symbol linkage, object/library order, and the `--as-needed` linker option.

Package after build:

```text
dist/
├── app.jar
└── native/
    ├── libbridgejni.so
    └── libhelper.so
```

### 5.5. Running and verifying stdout

On **JDK 17–23** with the JNI demo:

```bash
java -Ddemo.native.dir=dist/native -jar dist/app.jar
```

On **JDK 24+**, when native access restrictions apply to JNI:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Ddemo.native.dir=dist/native \
  -jar dist/app.jar
```

**Exact Java stdout when running successfully:**

```text
Native answer = 42
```

Explanation: Java loads the bridge from an absolute path; the ELF loader reads the bridge's `DT_NEEDED: libhelper.so`; `RUNPATH=$ORIGIN` helps locate `libhelper.so` in the same directory; `helper_answer()` returns `42`. There is no need to add this dependency to `java.library.path` in the demo.

To test why the dependency is required, create a **copy** of `dist`, rename `libhelper.so` in the copy, and run it again; the bridge exists, but the dependency loading step fails. Restore the test package to its proper state before release. Do not modify native files currently used by a production system.

**Compatibility limits:** `javac --release 17` only guarantees the target Java bytecode/API; it **does not** guarantee C binaries are compatible across all glibc versions, CPUs, and OSes. Build and test native code against your declared baseline distro and ABI.

## 6. Granting native access in the JVM at runtime

### 6.1. Rules by JDK version

| Version | Scope to note |
| --- | --- |
| JDK 17/21 | Traditional JNI does not have JDK 24-style native access warnings; FFM in these releases has various incubator/preview forms |
| JDK 22/23 | FFM API standardized in JDK 22 has restricted operations; JNI does not yet enforce the same mechanism as JDK 24 |
| JDK 24+ | **JEP 472** applies native access restrictions to JNI library loading and native method binding, aligning principles with FFM |

For JDK 24+ according to OpenJDK/Oracle documentation, `--illegal-native-access` can be `allow`, `warn`, or `deny`. Current JDK releases are documented as using `warn` by default, with the future direction being `deny`. Grant permission upfront when designing the launcher and test in deny mode, avoiding reliance on ignored warnings.

**Applications running on the classpath** (all unnamed modules, like the demo):

```bash
java --enable-native-access=ALL-UNNAMED \
  --illegal-native-access=deny \
  -Ddemo.native.dir=dist/native \
  -jar dist/app.jar
```

The command above is for **JDK 24+** because it includes `--illegal-native-access`; do not carry these exact flags into older JDK versions without checking support.

**Modular applications**: grant minimal permission to the module that **calls restricted APIs or declares native methods**. If the module is `com.example.nativebridge`, you can launch using the pattern:

```bash
java --enable-native-access=com.example.nativebridge \
  --illegal-native-access=deny \
  --module-path mods \
  --module com.example.nativebridge/com.example.nativebridge.Main
```

This is a **command template** requiring the module, entrypoint, and `mods` directory to actually exist, not a command for the default-package demo. A module calling business APIs through another module is not necessarily the module needing native access: identify the **module containing the native loading/linking code**.

Other valid configuration methods include:

- Placing flags in a launcher script, `JDK_JAVA_OPTIONS`, or a Java argument file `@argsfile` managed at deployment time.
- For **executable JARs run with `java -jar`**, the manifest can contain `Enable-Native-Access: ALL-UNNAMED`; specific module names are **not supported** in this attribute.
- For runtime images, appropriate startup options can be configured via `jlink`/`jpackage` and verified in the generated launcher.

**Do not confuse JVM native access with OS permissions.** `--enable-native-access` confirms that the application intentionally performs native operations that carry risks to JVM integrity; it does not grant filesystem permissions, nor does it bypass `noexec`, Gatekeeper/Code Signing, Windows DLL policies, sandboxes, or container restrictions.

### 6.2. Using FFM instead of JNI

From **JDK 22**, `java.lang.foreign.SymbolLookup.libraryLookup(Path/String, Arena)` is the way to load and look up symbols in a native library recognized by the OS. This is a restricted API; permission is granted to the module calling the method. Lookup lifetime is tied to `Arena`: avoid using function pointers or memory segments after the arena is closed/invalidated. Dependency closure, ABI, and OS loader **must still be packaged properly** just as with JNI. Do not confuse the stable FFM API in JDK 22+ with incubator/preview APIs in JDK 17/21.

## 7. Packaging strategies for production

### 7.1. Shipping native files alongside the JAR

Keep native libraries as real files in the installation directory and configure the path from the **launcher**, making it easy to verify checksums, permissions, ABI, and dependencies. Example `bin/run.sh` in the directory tree from section 2:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_HOME="$(cd -- "$(dirname -- "$0")/.." && pwd)"

exec java --enable-native-access=ALL-UNNAMED \
  -Ddemo.native.dir="$APP_HOME/native" \
  -jar "$APP_HOME/app.jar" "$@"
```

This script illustrates **JDK 24+**, executed directly via the script's real path (not accounting for symlinks that need separate resolution). `APP_HOME` is computed from the launcher's location, avoiding dependence on the current working directory. For JDK 17–23 and the JNI demo, `--enable-native-access` can be omitted. The directory containing native libraries should only be modifiable by trusted installation processes.

### 7.2. Embedding native libraries in a JAR and extracting them

A library distributed as a JAR can place resources by OS/ABI:

```text
META-INF/native/linux-x86_64-glibc/libbridgejni.so
META-INF/native/linux-x86_64-glibc/libhelper.so
META-INF/native/windows-x86_64/bridgejni.dll
META-INF/native/windows-x86_64/helper.dll
META-INF/native/macos-aarch64/libbridgejni.dylib
META-INF/native/macos-aarch64/libhelper.dylib
```

This is only a **suggested layout**; actual filenames and artifacts must match the platform. `System.load` cannot directly open a `jar:file:...!/libbridgejni.so` resource URL. You must extract **to an OS file**, verify it, and call `System.load(absolutePath)`.

An extraction flow should:

1. Normalize OS, CPU, and libc/ABI; only select tuples on an allowlist, and do not trust user-supplied path values.
2. Create a private cache directory, **not writable by other users**, that allows executable mapping. Do not assume `java.io.tmpdir` or shared `/tmp` is always suitable: a `noexec` mount can cause loading to fail.
3. Extract **the entire dependency closure** to locations the OS loader can find. Verify checksums/signatures if applicable; close streams, and prevent path traversal and symlink replacement.
4. Use version/content-hash directories so old and new versions do not overwrite each other; write to a temp file then atomic move where the filesystem supports it, and handle races if multiple processes start simultaneously.
5. Maintain loader metadata: Linux `$ORIGIN`, macOS install name/rpath, Windows DLL search setup. Call `System.load` only after all files are stably in place.
6. Do not delete or overwrite native binaries currently in use by a process. Clean up cache by version/lifecycle, especially on Windows where open files may be locked.

`System.loadLibrary` can integrate with `ClassLoader.findLibrary` returning an absolute path, but you still need a distribution and ownership strategy for libraries across multiple class loaders.

### 7.3. `jpackage`, `jlink`, and installers

`jpackage` creates an application image or OS-native installer that can bundle the Java runtime, JARs, and payloads. The following example **only illustrates packaging**; afterward you must verify where the native directory is placed and configure the launcher's path:

```bash
jpackage --type app-image \
  --name NativeMathDemo \
  --input dist \
  --main-jar app.jar \
  --main-class NativeMath \
  --java-options "--enable-native-access=ALL-UNNAMED"
```

The `--java-options` flag is appropriate for **JDK 24+**; you must also configure `-Ddemo.native.dir` with the native path inside the **actual image**, as layouts vary across OSes and tool versions. Do not treat this command as producing a ready-to-run demo without configuring that path.

`jpackage` **does not automatically detect and copy all transitive native dependencies** from a JAR. You must include files in the payload, verify the actual installer on the target OS, and check C/C++ runtimes and application signing. Packages like `.deb`/`.rpm`, `.msi`/`.exe`, and `.pkg`/`.dmg` must be built and smoke-tested on the platforms supported by the tool. `jlink` helps create custom runtimes, but also does not replace resolving C/C++ application dependencies.

## 8. Testing the release in a clean environment

### 8.1. Static and dependency checks

On Linux:

```bash
file dist/native/libbridgejni.so dist/native/libhelper.so
readelf -d dist/native/libbridgejni.so
readelf -d dist/native/libhelper.so
nm -D dist/native/libbridgejni.so
nm -D dist/native/libhelper.so
sha256sum dist/app.jar dist/native/*.so
```

Look for `NEEDED` and `RUNPATH` on both the primary library and dependencies. `ldd` can help observe resolved libraries on a test machine, but use it only on **trusted binaries** because some `ldd` implementations can execute code. Output on the build machine does not prove correctness on the target machine. Equivalent tools: `otool -L`/`codesign` on macOS, `dumpbin /DEPENDENTS` and PE dependency tools on Windows.

### 8.2. Dynamic smoke tests

1. Run the real package and verify stdout `Native answer = 42`, exit code `0`.
2. Run from a different current working directory via the standard launcher to catch relative-path dependencies.
3. Verify dependencies are not accidentally resolved from the dev machine via `LD_LIBRARY_PATH`/`PATH`, system-wide installs, or toolchain caches.
4. On JDK 24+, test `--illegal-native-access=deny` with your chosen `--enable-native-access` list.
5. Run on a clean image/VM for every supported OS + CPU + ABI, using the real Java runtime users will have.
6. Test upgrades/downgrades and multiple processes to catch stale binary/cache reuse or overwriting in-use files.

On JDKs that include `jnativescan`, use the static tool to inspect which classes/JARs use JNI/restricted methods:

```bash
jnativescan --class-path dist/app.jar
```

This tool **does not** confirm that `.so`/`.dll` files have all dependencies or will succeed when the OS loader runs. When a timeline is needed, HotSpot JDK 22+ provides the JFR events `jdk.NativeLibraryLoad` and `jdk.NativeLibraryUnload`; on JDK 17/21 you can use the `jdk.NativeLibrary` snapshot. Always cross-check messages from the OS dynamic loader.

## 9. Common errors and how to classify them

| Symptom | Cause to check | Fix |
| --- | --- | --- |
| `no ... in java.library.path` | JVM cannot find the logical name used for `loadLibrary` | Configure primary library/launcher; or use `System.load` with an absolute path |
| `Can't load library ...`, wrong path | Wrong release structure, reliance on working directory | Configure path relative to installation location and test the real launcher |
| `libhelper.so: cannot open shared object file` even though bridge exists | OS loader cannot find dependency | Check `DT_NEEDED`, `RUNPATH=$ORIGIN`, bundled libraries |
| `wrong ELF class`, `bad CPU type` | Wrong CPU or 32/64-bit ABI | Select the right binary/target tuple |
| `GLIBC_2.xx not found` | Built on too-new a distro, missing minimum ABI | Use an appropriate build baseline, check symbol versions |
| `undefined symbol` or `symbol not found` | Wrong ABI/JNI name, missing symbol, dependency version mismatch | Check `nm`, JNI header, `extern "C"` for C++ exports, dependency linking |
| DLL exists but Windows still reports missing | A dependent DLL/MSVC runtime is missing, incorrect search order | Check PE dependencies, bundle redistributable and DLL search policy |
| `Permission denied`, signature rejected, `noexec` | Filesystem permissions, mount/sandbox, or OS code signing | Fix according to OS policy; do not expect JVM flags to bypass it |
| `IllegalCallerException` on newer JDK | Module not granted native access when set to deny | Use `--enable-native-access` for the right module, check scope |
| `already loaded in another classloader` | Multiple class loaders trying to load the same JNI library | Define which class loader owns the native bridge and its lifecycle |
| Works in IDE, fails in release | Local environment implicitly adds libraries/paths | Test standalone artifact on a clean machine with the final launcher |

## 10. Pre-distribution checklist

- [ ] Complete OS/CPU/ABI/JDK matrix; only release variants that were actually built and tested.
- [ ] All required direct and transitive dependencies are bundled, along with licenses/notices.
- [ ] Primary library has a clear load path; dependencies have proper Linux/macOS/Windows search metadata.
- [ ] Native files are in a trusted location, non-modifiable by unauthorized parties, with checksum/signature verification where appropriate.
- [ ] Currently loaded files are not overwritten/updated in place; JNI class loader/FFM Arena lifecycles are handled.
- [ ] On newer JDKs, the launcher explicitly specifies `--enable-native-access` for permitted modules; smoke-test deny policy on JDK 24+.
- [ ] Installer/JAR extraction/`jpackage` are tested in practice, not relying on the developer environment.
- [ ] Separate diagnostic instructions exist for missing bridge, missing dependency, wrong ABI, OS permissions, and JVM native access.

## References

- [JNI Specification — Library and Version Management](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html) on class loaders and native libraries.
- [OpenJDK JEP 472](https://openjdk.org/jeps/472) on JNI/FFM native access and JDK 24.
- [Oracle JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html) on `--enable-native-access`, `--illegal-native-access`, and manifests.
- [Java SE SymbolLookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/foreign/SymbolLookup.html) on FFM library lookup and `Arena`.
- [Linux ld.so](https://man7.org/linux/man-pages/man8/ld.so.8.html) on `DT_NEEDED`, `RUNPATH`, and `$ORIGIN`.
- [Apple Run-Path Dependent Libraries](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/100-Articles/RunpathDependentLibraries.html) on `@rpath`/`@loader_path`.
- [Microsoft DLL Search Order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order) on dependency lookup and search flags.
- [Oracle jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html) on applications with runtime images/installers.

A Java application with native code must be distributed as **a single unit comprising JAR + native libraries + dependency closure + launcher/runtime policy**. Verifying all four parts on the target environment is the practical prerequisite for a stable release.

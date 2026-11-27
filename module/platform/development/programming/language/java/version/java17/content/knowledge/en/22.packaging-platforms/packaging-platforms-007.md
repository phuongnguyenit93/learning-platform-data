# macOS/AArch64 JDK and Matching-Architecture Native Libraries

Macs powered by Apple Silicon have 64-bit ARM CPUs. Java 17 provides macOS/AArch64 JDK builds to run the JVM natively on this architecture. When a Java application calls native libraries via JNI, JNA, or another native integration layer, the library's architecture must match **the architecture of the running JVM process**.

This is the core principle when packaging applications for macOS:

- A JDK running natively on Apple Silicon is an ARM64 process.
- An Intel JDK running via Rosetta 2 is an x86_64 process, even on physical Apple Silicon hardware.
- A JVM process can only load native code containing a slice compatible with that process's architecture.
- Every transitive native library dependency must also have a compatible architecture.
- A universal binary can contain both ARM64 and x86_64 slices; macOS selects the matching slice at load time.

A pure Java JAR is normally independent of CPU architecture. However, an application packaging a JAR alongside `.dylib` files, frameworks, or bundled native libraries must select the exact native artifacts matching the JVM process. Switching only the JDK to ARM64 while keeping x86_64 native libraries causes library loading failures.

## 1. Apple Silicon, AArch64, and x86_64

Apple Silicon refers to Apple's SoC family using the 64-bit ARM architecture. Across documentation and tooling, the same architecture may be called ARM64 or AArch64. On macOS, native tools commonly display `arm64`; in certain Java properties or metadata, it may appear as `aarch64`.

Intel Macs use the x86-64 architecture, typically written as `x86_64`. Apple Silicon can run Intel applications through Rosetta 2. Consequently, an Apple Silicon machine can simultaneously run:

- A native ARM64 JVM.
- An x86_64 JVM translated by Rosetta 2.

Those two JVMs are processes with different architectures. Neither can load native libraries compiled exclusively for the other architecture.

### Compatibility Matrix

| Hardware | JVM Process | Required Native Library |
| --- | --- | --- |
| Apple Silicon | Native ARM64 | ARM64 or universal with an ARM64 slice |
| Apple Silicon | x86_64 via Rosetta 2 | x86_64 or universal with an x86_64 slice |
| Intel Mac | Native x86_64 | x86_64 or universal with an x86_64 slice |
| Intel Mac | Cannot run an ARM64 JVM | Cannot load ARM64 native code into an Intel process |

Therefore, the question to answer when selecting libraries is: **Which architecture is the current JVM running under?** Knowing the machine is Apple Silicon is not enough, because the JVM might be running under Rosetta.

## 2. What Is the macOS/AArch64 JDK?

A macOS/AArch64 JDK is a JDK distribution whose native binaries are compiled for macOS on the ARM64 architecture. Its JVM runs directly on Apple Silicon without needing Rosetta to translate the JVM process.

JDKs are typically installed as bundles with a layout like:

~~~text
/Library/Java/JavaVirtualMachines/
  <jdk-name>.jdk/
    Contents/
      Home/
        bin/
        lib/
        include/
~~~

Directory names and packaging details can differ across vendors, but the Java launcher and JVM libraries reside inside the JDK home.

### Listing Installed JDKs

macOS provides the `java_home` utility:

~~~bash
/usr/libexec/java_home -V
~~~

This lists JDKs recognized by the system along with version and path details. You can request a JDK 17 for ARM64:

~~~bash
/usr/libexec/java_home -v 17 -a arm64
~~~

If multiple JDK 17 builds exist or a custom installation is not registered with the system, inspect the exact JDK path directly instead of assuming `PATH` picks the right one.

Set `JAVA_HOME` and `PATH` for the current shell:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17 -a arm64)
export PATH="$JAVA_HOME/bin:$PATH"

java -version
javac -version
~~~

The architecture flag in `java_home` helps pick the right JDK when multiple architectures are installed. If the system cannot find the matching JDK, verify installed JDKs and the path provided by your vendor.

## 3. Determining the Actual Architecture of the Running JVM

Do not infer JVM architecture from the machine name or Mac model alone. Inspect the Java process itself.

### Checking the os.arch System Property

Run:

~~~bash
java -XshowSettings:properties -version 2>&1 | grep -E 'os.arch|os.name|java.home'
~~~

On a native ARM64 JDK, `os.arch` typically reports `aarch64` or the corresponding ARM64 identifier for that distribution. For an Intel JVM running under Rosetta, the value is typically `x86_64`.

You can also inspect it from code:

~~~java
public class RuntimeArchitecture {
    public static void main(String[] args) {
        System.out.println("os.name = "
                + System.getProperty("os.name"));
        System.out.println("os.arch = "
                + System.getProperty("os.arch"));
        System.out.println("java.home = "
                + System.getProperty("java.home"));
        System.out.println("java.version = "
                + System.getProperty("java.version"));
    }
}
~~~

`os.arch` describes the architecture the active JVM is running under, rather than probing physical CPU hardware directly. This is the right signal for choosing native libraries to load into that process. When comparing values, normalize aliases such as `arm64` and `aarch64` to a consistent internal label.

### Checking Whether a Process Runs Under Rosetta

You can check the current shell process architecture:

~~~bash
arch
~~~

On macOS, `sysctl.proc_translated` can indicate whether the current process is translated by Rosetta:

~~~bash
sysctl -in sysctl.proc_translated
~~~

A value of `1` indicates the process is running under Rosetta. On native environments, this key may not be present; do not treat a missing key error as sole proof of architecture. For Java applications, checking `System.getProperty("os.arch")` inside the JVM is the most direct and useful check when choosing libraries.

### Inspecting JDK Binaries

Once `JAVA_HOME` is selected, inspect the launcher and JVM shared library:

~~~bash
file -L "$JAVA_HOME/bin/java"
file -L "$JAVA_HOME/lib/server/libjvm.dylib"
lipo -archs "$JAVA_HOME/lib/server/libjvm.dylib"
~~~

The path to `libjvm` may vary in some JDK packaging layouts; if not found, locate `libjvm.dylib` inside the JDK home. The `file` command displays binary type and architecture; `lipo -archs` lists the slices contained in a Mach-O binary.

Not every JDK is a universal binary. Many vendors distribute separate JDK builds for ARM64 and x86_64. Selecting the right JDK package upfront is easier to manage than assuming a single package runs both architectures.

## 4. Why Native Libraries Must Match the JVM Architecture

Java bytecode is designed for the JVM to execute across architectures. Native libraries contain machine code compiled for one or more specific architectures.

When Java calls:

~~~java
System.loadLibrary("native_math");
~~~

the JVM asks the macOS dynamic loader to map a native library into the process's address space. The dynamic loader must find a Mach-O image with a slice compatible with the running process.

For example:

- An ARM64 JVM cannot load a dylib that only has an x86_64 slice.
- An x86_64 JVM under Rosetta cannot load a dylib that only has an ARM64 slice.
- Both can load a universal dylib containing both ARM64 and x86_64 slices.

There is no automatic translation step converting an Intel dylib to ARM64 during a JNI call. Rosetta translates an entire Intel process; it does not allow arbitrarily mixing ARM64 modules into an x86_64 process.

### Example Architecture Mismatch Error

A common error seen in stack traces:

~~~text
java.lang.UnsatisfiedLinkError:
  dlopen(...): tried: ... (mach-o file, but is an incompatible architecture
  (have 'x86_64', need 'arm64'))
~~~

The message indicates the JVM needs ARM64, while the located file only contains x86_64. Fix it by installing or packaging a native library with an ARM64 slice, or running an x86_64 JVM alongside x86_64 libraries if that is an intentional deployment choice.

### Not Only the Direct JNI File Needs the Right Architecture

A JNI library can depend on other dylibs. For example:

~~~text
Java application
    |
    v
libnative_math.dylib
    |
    +---- libimagecodec.dylib
    |
    +---- libcrypto_adapter.dylib
              |
              +---- libvendor_runtime.dylib
~~~

Even if `libnative_math.dylib` has an ARM64 slice, loading still fails if `libimagecodec.dylib` or a deeper dependency is x86_64-only. The entire chain of native libraries must match the JVM process architecture.

## 5. Common Native Formats on macOS

macOS uses the Mach-O format for executables and native libraries. Common file types include:

| File / Format | Role |
| --- | --- |
| `.dylib` | Dynamic library on macOS |
| `.framework` | Framework bundle; binary lives inside the bundle |
| `.bundle` | Native bundle/plugin on macOS |
| Mach-O executable | Program or helper executable |
| `.jar` | Java archive; usually holds bytecode, resources, and optionally native payloads |
| `.so` | Typically used for Linux shared libraries; not the standard macOS native library extension |

JNI libraries on macOS are typically packaged as `.dylib`. Do not take Linux or Windows extensions and assume macOS can load the same file. A JAR may bundle multiple native binaries by OS/architecture, but the extracted and loaded file must match the active JVM.

### Universal Binaries

A universal binary is a Mach-O binary holding multiple architecture slices in one file. For example, a dylib containing both ARM64 and x86_64:

~~~bash
lipo -archs libnative_math.dylib
~~~

Output might be:

~~~text
arm64 x86_64
~~~

When an ARM64 JVM loads the file, the dynamic loader uses the ARM64 slice. When an x86_64 JVM loads the same file, the loader uses the x86_64 slice.

Universal binaries simplify distributing one native file for both architectures, but they do not automatically make single-architecture dependencies universal. Every linked dependency must still provide slices for each supported architecture.

## 6. Inspecting the Architecture of Native Libraries

Before placing a dylib into an application package, inspect the actual binary.

### Using file

~~~bash
file libnative_math.dylib
~~~

Output indicates whether it is a Mach-O 64-bit dynamically linked shared library and lists its architecture(s).

### Using lipo

~~~bash
lipo -info libnative_math.dylib
lipo -archs libnative_math.dylib
~~~

`lipo -archs` is particularly useful for universal binaries because it prints the exact slices present. Do not trust file names like `libnative_math-arm64.dylib` alone; names can be wrong or artifacts mispackaged.

### Checking Dependencies with otool

~~~bash
otool -L libnative_math.dylib
~~~

This lists the dynamic libraries referenced by the binary. Inspect the architecture of each dependency found in the bundle or installation paths.

Example:

~~~bash
file /path/to/native/libnative_math.dylib
lipo -archs /path/to/native/libnative_math.dylib
otool -L /path/to/native/libnative_math.dylib

file /path/to/native/libimagecodec.dylib
lipo -archs /path/to/native/libimagecodec.dylib
~~~

Perform this check recursively on all dependencies packaged by the application. `otool -L` only lists direct dependencies; inspect each referenced library to uncover deeper dependencies.

### Checking Frameworks

Frameworks are bundles whose binaries usually reside under `Versions/Current` or a path designated by the framework. Locate the binary and run:

~~~bash
find SomeFramework.framework -type f -maxdepth 5
file SomeFramework.framework/Versions/Current/SomeFramework
lipo -archs SomeFramework.framework/Versions/Current/SomeFramework
~~~

Exact paths depend on framework layout. Do not inspect only the bundle directory and guess the architecture; inspect the Mach-O binary inside.

## 7. Matching JDK and Native Libraries to the Same Architecture

A macOS application may support multiple configurations. What matters is keeping the full artifact set consistent.

| Release Configuration | JDK | Native Payload |
| --- | --- | --- |
| Native Apple Silicon | macOS/AArch64 JDK 17 | ARM64 dylib/framework and ARM64 dependencies |
| Intel Mac | macOS/x86_64 JDK 17 | x86_64 dylib/framework and x86_64 dependencies |
| Single bundle for both | Architecture-specific JDKs or explicit runtime selection | Universal native libraries or payloads selected by process architecture |

Do not put an ARM64 JDK and an x86_64 JNI library into the same bundle expecting macOS to translate the library. To support both Intel and Apple Silicon, you can:

1. Release two separate installers by architecture.
2. Use a bundle carrying JDK/native payloads per architecture and choose the matching set at install/launch time.
3. Use universal native binaries for native components while supplying the matching JDK per architecture.

Universal native binaries do not imply the bundled JDK is also universal. Inspect every component.

## 8. Checking and Normalizing os.arch in Java

An application can read:

~~~java
String os = System.getProperty("os.name");
String arch = System.getProperty("os.arch");

System.out.println("OS: " + os);
System.out.println("Architecture: " + arch);
~~~

Common architecture values:

| Value | Interpretation |
| --- | --- |
| `aarch64` | 64-bit ARM |
| `arm64` | 64-bit ARM, common alias in the Apple ecosystem |
| `x86_64` | 64-bit Intel/AMD |

Do not compare strings against only one rigid literal. You can normalize:

~~~java
static String normalizedMacArchitecture() {
    String arch = System.getProperty("os.arch")
            .toLowerCase(java.util.Locale.ROOT);

    return switch (arch) {
        case "aarch64", "arm64" -> "arm64";
        case "x86_64", "amd64" -> "x86_64";
        default -> throw new IllegalStateException(
                "Unsupported architecture: " + arch);
    };
}
~~~

This snippet recognizes only the two architectures supported by the application. If the product adds another architecture, expand the tested allowlist rather than silently picking a similar-looking library.

### Using JVM Architecture to Select Native Resources

For example, a JAR contains:

~~~text
native/
  macos-aarch64/
    libnative_math.dylib
  macos-x86_64/
    libnative_math.dylib
~~~

The application selects the resource:

~~~java
String arch = normalizedMacArchitecture();
String resource = "/native/macos-" + arch
        + "/libnative_math.dylib";
~~~

Then extract the resource to a real file on the filesystem and load it by absolute path:

~~~java
try (var input = NativeLoader.class.getResourceAsStream(resource)) {
    if (input == null) {
        throw new UnsatisfiedLinkError(
                "Native library not packaged: " + resource);
    }

    Path extracted = Files.createTempFile(
            "native-math-", ".dylib");
    Files.copy(input, extracted, StandardCopyOption.REPLACE_EXISTING);
    extracted.toFile().deleteOnExit();
    System.load(extracted.toAbsolutePath().toString());
}
~~~

This is a minimal pattern. Production code must manage file permissions, unique names, cleanup, checksums, and extracted file lifecycles. If the native library depends on other dylibs, their dependency paths must also be configured so the loader can find them.

Never choose resources based on hardware architecture guessed from the Mac model. Use the JVM process architecture to select the binary to load.

## 9. JNI on macOS/AArch64

JNI (Java Native Interface) is the JDK's public interface enabling Java to call native code and native code to call back into the JVM. JNI headers ship with the JDK, usually at:

~~~text
$JAVA_HOME/include/jni.h
$JAVA_HOME/include/darwin/jni_md.h
~~~

Native code is compiled into a Mach-O dylib for the target architecture. The same C/C++ source can be compiled separately for ARM64 and x86_64 if the compiler, SDK, and all dependencies support both targets.

### Java Declaration

Example Java class:

~~~java
package demo;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    private NativeMath() {}

    public static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println(add(20, 22));
    }
}
~~~

`System.loadLibrary("native_math")` takes a logical library name, not a full file path. On macOS, `System.mapLibraryName("native_math")` typically maps it to `libnative_math.dylib`.

### Native Implementation

File `native_math.c`:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL
Java_demo_NativeMath_add(
        JNIEnv *env,
        jclass type,
        jint left,
        jint right) {
    return left + right;
}
~~~

### Building an ARM64 Dylib

Point `JAVA_HOME` to the ARM64 JDK 17:

~~~bash
export JAVA_HOME=$(/usr/libexec/java_home -v 17 -a arm64)

clang -dynamiclib \
  -arch arm64 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

Depending on the project, add include paths, linker flags, dependent native libraries, and the macOS deployment target. Use the selected JDK/toolchain as your target and verify native dependencies also have ARM64 slices.

### Compiling Java and Running

~~~bash
javac --release 17 -d out NativeMath.java
java -Djava.library.path="$PWD" -cp out demo.NativeMath
~~~

This assumes the source sits in the matching package directory or is resolved via source path. Adjust file paths to match your project.

After building, inspect:

~~~bash
file libnative_math.dylib
lipo -archs libnative_math.dylib
~~~

Ensure the output includes the ARM64 slice when the JVM runs natively on Apple Silicon.

### Building for Intel

To produce an x86_64 build, compile with the matching target:

~~~bash
clang -dynamiclib \
  -arch x86_64 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

In an Intel build pipeline, `JAVA_HOME` should point to an x86_64 JDK 17 or a clearly defined toolchain/header setup. Verify every linked library also has an x86_64 slice.

### Building a Universal Dylib

If the compiler and all dependencies support both architectures, Clang can build a universal binary:

~~~bash
clang -dynamiclib \
  -arch arm64 \
  -arch x86_64 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

Or build each architecture separately and merge them:

~~~bash
lipo -create \
  -output libnative_math.dylib \
  libnative_math-arm64.dylib \
  libnative_math-x86_64.dylib
~~~

Verify the result:

~~~bash
lipo -archs libnative_math.dylib
~~~

A universal build only succeeds from a packaging standpoint when each slice is built properly and its matching dependencies are available. You cannot take an x86_64 dependency and attach it to an ARM64 slice with `lipo`.

## 10. System.loadLibrary and System.load

Java provides two common ways to load native libraries:

| API | Input | Usage |
| --- | --- | --- |
| `System.loadLibrary(name)` | Logical name without path | JVM searches native library paths using OS conventions |
| `System.load(path)` | Absolute file path | Loads the exact specified file |

Example:

~~~java
System.loadLibrary("native_math");
~~~

Or:

~~~java
System.load("/opt/myapp/native/arm64/libnative_math.dylib");
~~~

With `System.loadLibrary`, you can configure:

~~~bash
java -Djava.library.path=/opt/myapp/native/arm64 \
     -cp app.jar \
     com.example.Main
~~~

`java.library.path` helps the JVM locate the first-level JNI library. It **does not automatically fix the paths or architectures of dependencies referenced by that dylib**. If `libnative_math.dylib` links against `libimagecodec.dylib` via an install name or rpath, the macOS dynamic loader still must locate that dependency.

### Distinguishing java.library.path from dyld Search Paths

There are two separate lookup stages:

1. The JVM locates the JNI file requested by the application via `System.loadLibrary` or `System.load`.
2. The macOS dynamic loader resolves dylibs required by that JNI file using install names, rpaths, and `dyld` search rules.

Therefore, adjusting `java.library.path` can fix missing primary JNI files, but may not resolve `Library not loaded` for a dependent dylib. Inspect `otool -L` and rpaths when encountering the second failure.

## 11. Rpath and Dependency Placement on macOS

Mach-O binaries can record dependency paths using:

- `@rpath`: searches declared run-path search paths.
- `@loader_path`: relative to the directory containing the binary referencing the dependency.
- `@executable_path`: relative to the directory containing the main executable.

For instance, an app bundle might place native libraries in the same directory:

~~~text
MyApp.app/
  Contents/
    MacOS/
      MyApp
    Frameworks/
      libnative_math.dylib
      libimagecodec.dylib
    app/
      application.jar
~~~

A dylib inside `Contents/Frameworks` can use an appropriate install name/rpath, such as one based on `@loader_path`, to find sibling dylibs. Exact settings depend on the referencing binary's location and how the linker sets install names.

Inspect load commands:

~~~bash
otool -L libnative_math.dylib
otool -l libnative_math.dylib
~~~

`otool -L` shows dependencies and install names. `otool -l` displays load commands, including any `LC_RPATH` entries.

### Do Not Confuse java.library.path with rpath

`java.library.path` is the JVM search path for libraries loaded via Java. Rpath is Mach-O metadata used by the dynamic loader to resolve native dependencies. Both play a role during loading, but they do not replace each other.

Bundling dylibs inside the app bundle with relative rpaths is generally easier to deploy and control than relying on a global install directory on user machines.

## 12. JNA and Java Libraries Calling Native Code

JNA is a third-party library allowing Java to call native functions without writing extensive JNI boilerplate. JNA's Java code can run across architectures if bytecode is compatible, but JNA's native dispatcher and the system/third-party native libraries it invokes still must match the architecture.

When using JNA on Apple Silicon:

- Choose a JNA version supporting macOS ARM64.
- Ensure the native dispatcher loaded by JNA includes a slice matching the JVM.
- Ensure the target native libraries opened by JNA also support the JVM process architecture.
- Verify transitive native dependencies.
- Do not assume a pure-looking Java JAR contains no native code.

Other libraries using JNI or native bridges follow the same rules. Check the library's distribution notes and inspect native payloads inside the JAR or installation folder if loading errors occur.

### Native Payloads Bundled Inside a JAR

A Java library may pack multiple native resources:

~~~text
META-INF/
  native/
    macos-aarch64/
      libdispatch.dylib
    macos-x86_64/
      libdispatch.dylib
~~~

The library's loader selects the resource based on OS/architecture, extracts it to a temporary folder, and loads it. When upgrading a library, inspect the actual JAR to confirm it includes the payload for your target architecture; do not look solely at the Java dependency version.

## 13. Packaging Native Dependencies by OS and Architecture

If an application supports both macOS ARM64 and Intel, native artifacts should be organized clearly. One naming convention is:

~~~text
native/
  macos-aarch64/
    libcodec.dylib
    libcrypto_adapter.dylib
  macos-x86_64/
    libcodec.dylib
    libcrypto_adapter.dylib
~~~

Or package a universal library if every dependency has all required slices:

~~~text
native/
  macos-universal/
    libcodec.dylib
    libcrypto_adapter.dylib
~~~

These directory names are application conventions, not mandatory macOS or Maven/Gradle standards. What matters is that artifact metadata clearly identifies the OS and architecture.

### Maven/Gradle Dependencies

In a build system, native artifacts can be published separately using classifiers or variants, for example:

| Artifact Variant | Contents |
| --- | --- |
| macOS ARM64 | Dylibs and dependencies for ARM64 |
| macOS x86_64 | Dylibs and dependencies for x86_64 |
| macOS universal | Dylibs containing both slices and matching dependencies |

There is no single mandatory classifier string across all projects. Pick a consistent convention in your repository and ensure dependency resolution selects the right variant.

When building native dependencies, use a CI matrix for ARM64 and x86_64 or a universal pipeline that verifies both slices. Never let the current build host implicitly decide the target architecture if artifacts will ship for multiple platforms.

### Distinguishing Build Host from Target Architecture

The compiler host may differ in architecture from the release target. For example, an ARM64 Mac can cross-compile native code for x86_64 if the toolchain and dependencies support it. Conversely, building on an Intel machine does not automatically produce ARM64 binaries.

Pass the target architecture as an explicit build parameter:

~~~bash
./build-native.sh arm64
./build-native.sh x86_64
~~~

The build script should select the right compiler target, SDK, dependencies, and output directory. Do not use the build JVM's `os.arch` as the default target when a pipeline cross-compiles.

## 14. Verifying Architecture in the Packaging Pipeline

A macOS release pipeline might include:

1. Select the ARM64 or x86_64 JDK 17 matching the target artifact.
2. Compile Java with the appropriate target release.
3. Build the native library for the target architecture.
4. Build or fetch native dependencies of the same architecture.
5. Inspect every Mach-O binary using `file` and `lipo`.
6. Check dependencies with `otool -L`.
7. Place dylibs/frameworks into the right location in the app bundle.
8. Configure install names and rpaths.
9. Run a smoke test on the JVM of matching architecture.
10. Code-sign and package once binaries are finalized.

### Automated Verification Example

A simple shell script can require the ARM64 slice:

~~~bash
#!/bin/bash
set -euo pipefail

LIB="dist/native/libnative_math.dylib"

file "$LIB"
ARCHS="$(lipo -archs "$LIB")"
echo "Architectures: $ARCHS"

case " $ARCHS " in
  *" arm64 "*) ;;
  *)
    echo "Missing arm64 slice: $LIB" >&2
    exit 1
    ;;
esac
~~~

For universal artifacts, verify both slices:

~~~bash
ARCHS="$(lipo -archs dist/native/libnative_math.dylib)"
case " $ARCHS " in
  *" arm64 "*"x86_64 "*) ;;
  *)
    echo "Expected arm64 and x86_64 slices" >&2
    exit 1
    ;;
esac
~~~

For multiple libraries, run checks across the entire list of packaged native binaries. The sample script verifies slices of a single file; it does not replace recursive dependency inspection.

## 15. Code Signing and macOS Packaging

macOS applications distributed to users may require code signing and notarization depending on product distribution channels. Native executables, dylibs, and frameworks inside the app bundle must be packaged and signed according to application policy.

Key principles:

- Complete builds and universal slice merging before signing.
- Verify binaries after copying them into the app bundle.
- Sign nested code according to bundle structure and release guidelines.
- Never modify Mach-O binaries after signing.
- Complete notarization per Apple's distribution requirements.

Verify signatures:

~~~bash
codesign --verify --verbose=4 path/to/libnative_math.dylib
codesign -dv --verbose=4 path/to/libnative_math.dylib
~~~

Running `lipo -create` or a tool that edits a Mach-O binary after signing can invalidate the signature. Finalize slice merging, install names, and dependency layout before the final signing step.

Hardened Runtime, Library Validation, and application signing policies can affect native code loading. When signature errors occur, inspect OS logs and your product's signing/notarization configuration. Do not instruct users to disable Gatekeeper or turn off macOS protections as a default workaround.

## 16. Common Errors and Diagnostics

| Error / Symptom | Possible Cause | Inspection and Fix |
| --- | --- | --- |
| `UnsatisfiedLinkError` with incompatible architecture | Dylib lacks the JVM process's slice | Check `os.arch`, `file`, `lipo -archs`; swap in matching artifact |
| `Library not loaded` | Dependent dylib not found | Run `otool -L`, check rpath and dependency placement |
| `image not found` | Wrong path or install name | Check `System.load`/`java.library.path`, `otool -L` |
| `Symbol not found` | ABI/symbol mismatch or wrong dependency version | Verify exported symbols, versions, and dependency graph |
| `no suitable image found` | Binary lacks compatible slice or is invalid | Inspect Mach-O with `file` and `lipo` |
| `code signature invalid` | Binary modified after signing or invalid signature | Build/sign in proper order and verify nested code |
| ARM64 JVM fails to load JNA dispatcher | JNA native payload lacks ARM64 support or wrong artifact | Upgrade/select JNA supporting ARM64 and inspect payload |
| Works when Terminal opened via Rosetta, fails natively | Two runs use different JVM architectures | Check `os.arch`; bundle the matching native slice |
| JNI library has ARM64 but still fails to load | A deeper dependency is x86_64-only | Walk dependencies from `otool -L` and check each binary |
| `java.library.path` is right yet still `Library not loaded` | JVM found JNI library, `dyld` could not find a dependency | Inspect install name/rpath rather than just expanding `java.library.path` |
| ARM64 build host accidentally outputs Intel artifacts | Target architecture not explicitly configured | Set `-arch`/target explicitly in native builds |

### Step-by-Step Debugging Workflow

When encountering a native loading error on Apple Silicon:

1. Print `java.home`, `java.version`, and `os.arch` from the failing process itself.
2. Determine whether the JVM is native ARM64 or x86_64 via Rosetta.
3. Identify the exact native file being loaded, not just the file expected in the build.
4. Run `file` and `lipo -archs` on that file.
5. Run `otool -L` to locate its dependencies.
6. Check the architecture of every dependency.
7. Check rpaths/install names if the loader cannot locate a file.
8. Check code signatures if errors involve binary validation.
9. Re-test on the exact runtime and environment of the release package.

Do not toggle randomly between ARM64 and x86_64 JDKs to mask errors. Define which product configurations you support and keep a consistent runtime/native combination during testing.

## 17. Should You Use Rosetta 2 for Java Applications?

Rosetta 2 allows running Intel applications on Apple Silicon where appropriate. Thus, you can run an x86_64 JDK and x86_64 native libraries on an ARM64 Mac if the application still relies on a library available only for Intel.

This can serve as a transitional option while dependencies lack ARM64 builds. However:

- Every native library in that process must be x86_64-compatible.
- You cannot load an ARM64 dylib into an x86_64 JVM running under Rosetta.
- An application running under Rosetta is not a native ARM64 JVM application.
- Performance and resource usage may differ from native ARM64.
- Verify support policies of your JDK and native library vendors.

Once dependencies support ARM64, prefer running a native ARM64 JDK so the entire stack shares the same architecture without relying on a translation layer.

Do not treat Rosetta as a way to convert an ARM64 library into an Intel library or vice versa. Rosetta translates an x86_64 process; it does not let a single process mix Mach-O images of differing architectures.

## 18. Testing Both Architectures

If the application ships for both Apple Silicon and Intel, test on both configurations:

| Test | Native Apple Silicon | Intel Mac |
| --- | --- | --- |
| Matching-architecture JDK 17 | ARM64 | x86_64 |
| `os.arch` | ARM64/AArch64 | x86_64 |
| Native library | ARM64 or universal | x86_64 or universal |
| Dependency graph | All have ARM64 slices | All have x86_64 slices |
| JNI/JNA smoke test | Yes | Yes |
| File loading/rpath | Yes | Yes |
| Code signing | Verify native bundle | Verify native bundle |

If CI lacks physical Intel hardware, you can build/test the x86_64 target in a compatible environment and inspect slices with tooling. However, running x86_64 via Rosetta on Apple Silicon does not fully replace testing on real Intel Macs; OS, driver, SDK, and native dependency differences can still arise.

### Native Smoke Test

A smoke test should minimally do the following:

- Launch the JVM using the exact target JDK.
- Print `os.arch` and `java.home`.
- Load the native library.
- Invoke a simple native method.
- Verify the return value.
- Log full loader errors if any occur.

Example:

~~~java
public class NativeSmokeTest {
    public static void main(String[] args) {
        System.out.println("JVM architecture: "
                + System.getProperty("os.arch"));
        System.out.println("JDK home: "
                + System.getProperty("java.home"));

        System.loadLibrary("native_math");

        int result = NativeMath.add(20, 22);
        if (result != 42) {
            throw new AssertionError("Unexpected native result: " + result);
        }
        System.out.println("Native library loaded successfully");
    }
}
~~~

A smoke test confirms the loading path and a basic JNI invocation. It does not replace functional, concurrency, memory ownership, or error-handling tests for native code.

## 19. ABI and macOS Deployment Target

Matching architecture is necessary, but not sufficient. Native libraries must also be compatible with the macOS versions supported by the application.

Factors to check:

- **macOS deployment target**: a dylib may have been compiled with a minimum OS version newer than the user's machine.
- **SDK and compiler**: binaries may depend on symbols present only in newer SDKs/runtimes.
- **ABI**: calling conventions, struct layouts, symbol visibility, and assumptions between Java and native code must align.
- **Dependency versions**: dependent native libraries may require different versions.
- **Code signing**: binaries must satisfy the app's signing policy.

When compiling with Clang, set the deployment target explicitly if the project specifies one:

~~~bash
clang -dynamiclib \
  -arch arm64 \
  -mmacosx-version-min=<minimum-supported-version> \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -o libnative_math.dylib \
  native_math.c
~~~

The `<minimum-supported-version>` value must match the oldest macOS version your product commits to supporting, along with the SDK, JDK, and dependencies. Do not copy an arbitrary value from a build machine.

You can inspect build version metadata and load commands with:

~~~bash
otool -l libnative_math.dylib
~~~

Look for load commands regarding platform version, minimum OS, and rpath. Matching architecture with too new a minimum OS requirement will still prevent the library from running on older machines.

## 20. Checklist for Packaging macOS/AArch64 JDKs

Before releasing an Apple Silicon build:

1. Select a macOS/AArch64 JDK 17 from an organization-supported distribution.
2. Check `java -version`, `java.home`, and `os.arch`.
3. Confirm the JVM runs native ARM64, not x86_64 under Rosetta unintentionally.
4. Inspect launcher and `libjvm` in the JDK bundle using `file`/`lipo`.
5. Choose JNI/JNA/native payloads with ARM64 slices.
6. Verify every direct and transitive dylib/framework dependency.
7. Configure `java.library.path` or absolute paths for the primary JNI library.
8. Configure install names/rpaths so `dyld` can locate dependencies.
9. Verify macOS deployment targets and ABI of native libraries.
10. Run a smoke test on the ARM64 JDK.
11. Complete any universal merges before code signing.
12. Verify code signatures and package/notarize following your product's macOS release process.

If releasing for both Intel and Apple Silicon, repeat the process for x86_64 or verify universal binaries contain both slices. Never mark an artifact universal based on its file name alone.

## 21. Practical Guidelines

When packaging a Java 17 application with native dependencies on macOS:

1. Distinguish hardware architecture from JVM process architecture.
2. On Apple Silicon, use a native ARM64 JDK once dependencies support it.
3. Select native libraries by the JVM's `os.arch`, normalizing ARM64/AArch64 aliases.
4. Ensure JNI/JNA libraries and all Mach-O dependencies contain matching slices.
5. Use `file`, `lipo`, and `otool` to inspect actual binaries.
6. Use universal binaries when all dependencies provide both slices and the build pipeline verifies them.
7. Distinguish `java.library.path` from `dyld` rpath/install names.
8. Set target architecture explicitly in native builds; do not confuse build host with target.
9. Verify minimum macOS version, ABI, and code signing in addition to architecture.
10. Run smoke tests on the exact JDK and architecture supported by the release package.

A macOS/AArch64 JDK paired with matching-architecture native libraries allows the JVM to execute natively on Apple Silicon and load corresponding native code cleanly. Decisions must be based on the JVM process architecture, not hardware alone. By inspecting the main binary, dependency graph, `dyld` paths, and signatures before release, architecture mismatch errors are caught at the build/package stage instead of on user machines.

# .so, .dll, .dylib Libraries and Target Platforms

When Spring Boot is compiled into a **GraalVM Native Image**, the result is an executable built for a specific operating system and CPU architecture. However, the application may still need to call external native code: vendor C/C++ libraries, drivers, image processing libraries, computation code, or system integration components. These shared libraries typically have the extension **.so on Linux, .dll on Windows, and .dylib on macOS**.

For the application to run, simply having the library file is not enough. The executable, JNI libraries, and the system libraries they depend on must be compatible in **OS, CPU architecture, ABI, calling convention, libc/runtime, and symbol versions**. A file that builds successfully on a development machine may still fail to load in a production container if the platform differs or a dependency is missing.

This lesson belongs to the **Serialization and JNI** chapter of the `SPRING_BOOT_NATIVE_IMAGE` module. We will distinguish the native executable from a JNI shared library, compile a small JNI library, load the library by name or path, inspect dynamic dependencies, and select matching build/container platforms.

## 1. Distinguishing the Native Executable from Shared Libraries

GraalVM Native Image produces a native program from a Java application. If the application uses JNI to call C/C++ code, the JNI library usually remains a separate file loaded at runtime.

| Component | Role | Example on Linux |
| --- | --- | --- |
| Native executable | Spring Boot program after GraalVM compilation | `orders-service` |
| JNI shared library | C/C++ code providing native functions for Java | `libimagecodec.so` |
| Native dependencies of the JNI library | Libraries that the JNI library links against or loads further | `libjpeg.so`, `libstdc++.so` |
| System runtime | Loader, libc, and system libraries | glibc, dynamic linker |

A JNI library is not automatically embedded into the native executable merely because the application declares `native` methods. When using `System.loadLibrary(...)`, the library file and its required dependencies must be present in the runtime environment, unless the project explicitly configures a different linking mechanism.

Three common file types:



| Operating system | Common format | Example names |
| --- | --- | --- |
| Linux | ELF shared object, `.so` suffix | `libimagecodec.so`, `libimagecodec.so.2` |
| Windows | PE/COFF dynamic-link library, `.dll` suffix | `imagecodec.dll` |
| macOS | Mach-O dynamic library, `.dylib` suffix | `libimagecodec.dylib` |

You cannot rename `libimagecodec.so` to `imagecodec.dll` to use it on Windows. File contents, object formats, symbols, ABIs, and loaders differ across platforms.

### 1.1. Shared Libraries and Static Libraries

The `.so`, `.dll`, and `.dylib` suffixes normally denote dynamically loaded libraries. On Linux, static archives are typically `.a`; on Windows, typically `.lib`. Static archives are used by the native linker at build time to embed object code into an executable or shared library; you cannot pass a `.a` file to `System.loadLibrary(...)`. If a JNI `.so` links against a static archive, that code becomes part of the `.so`; if it links against another shared library, that dynamic dependency must still be present at runtime.

## 2. Native Libraries Must Match the Target Platform

A native artifact can be characterized by the combination of:

- **Operating system:** Linux, Windows, or macOS.
- **CPU architecture:** x86_64/AMD64, AArch64/ARM64, and architectures supported by the toolchain.
- **Binary format:** ELF, PE/COFF, or Mach-O.
- **ABI and calling convention:** how arguments are passed, results returned, and stack/symbols managed.
- **C runtime:** for example, glibc or musl on Linux; corresponding runtimes on Windows/macOS.
- **Runtime dependencies:** versions of system libraries the binary requires when loading.

Example matrix:

| Build target | Executable | JNI library | Can run directly on |
| --- | --- | --- | --- |
| Linux x86_64, glibc | Linux ELF x86_64 | ELF x86_64 .so | Linux x86_64 with compatible runtime |
| Linux AArch64, glibc | Linux ELF AArch64 | ELF AArch64 .so | Compatible Linux ARM64 |
| Windows x86_64 | PE x86_64 .exe | PE x86_64 .dll | Windows x86_64 |
| macOS ARM64 | Mach-O ARM64 | Mach-O ARM64 .dylib | Compatible macOS ARM64 |

A Linux x86_64 application cannot load a Windows x64 or macOS ARM64 JNI library. Matching CPU architecture alone is not enough either: Linux glibc and Linux musl are two different ABI environments, and a binary built with newer glibc symbol versions may fail to run on older systems.

### 2.1. Which Target Does GraalVM Build For?

Native Image normally builds an executable for the **OS and architecture of the build environment**, using the corresponding native toolchain. Do not assume you can build a Linux ARM64 executable on Windows x86_64 simply by renaming a file or setting a Maven property.

For different targets, the most predictable approach is to build on a matching runner/container:

- Linux x86_64: Linux AMD64 runner with GraalVM and an appropriate compiler.
- Linux ARM64: ARM64 runner or a build environment with genuine ARM64 target support.
- Windows: Windows runner with the corresponding C/C++ toolchain.
- macOS: macOS runner for the target architecture.

Cross-compilation support depends on the GraalVM distribution, version, target, and toolchain. Only use it when the version's documentation explicitly confirms the supported configuration. In multi-platform CI, produce separate artifacts per target and test them on the target environment.

### 2.2. Do Not Confuse the Build Machine Architecture with the Container Architecture

A developer machine may be Apple Silicon ARM64, while production images must run on Linux AMD64. Docker Desktop can emulate certain targets, but native compilation and performance testing under emulation can behave significantly differently.

Document the actual target in your pipeline, for example:

- `linux/amd64`
- `linux/arm64`
- `windows/amd64`
- `darwin/arm64`

The target name only describes OS/architecture; you still need to verify libc, ABI, and dependencies.

## 3. How Does JNI Work?

JNI (Java Native Interface) is the mechanism allowing Java to invoke functions written in C/C++ and allowing native code to interact back with the JVM/Java runtime through the JNI API.

A basic call flow:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot bean
    participant Java as Java native method
    participant Loader as OS dynamic loader
    participant C as JNI shared library
    App->>Java: calculate(...)
    Java->>Loader: System.loadLibrary(...)
    Loader->>C: load .so / .dll / .dylib
    Java->>C: call JNI function
    C-->>Java: return result via JNI
    Java-->>App: Java result
~~~

Java declares a method with the `native` modifier:

~~~java
package com.example.nativebridge;

import java.nio.file.Path;

public final class NativeMath {

    private NativeMath() {
    }

    // Called at runtime startup after the Spring context begins initializing.
    public static void loadLibrary() {
        String path = System.getenv("APP_NATIVE_LIBRARY");
        if (path == null || path.isBlank()) {
            System.loadLibrary("nativecalc");
        }
        else {
            System.load(Path.of(path).toAbsolutePath().toString());
        }
    }

    public static native long add(long left, long right);
}
~~~

Library loading can be invoked from a bean initialized at runtime:

~~~java
import org.springframework.beans.factory.InitializingBean;
import org.springframework.stereotype.Component;

@Component
class NativeLibraryInitializer implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        NativeMath.loadLibrary();
    }
}
~~~

This bean illustrates loading the library during Spring's initialization lifecycle. If native functions are not required immediately at startup, the library can be loaded at a more suitable lifecycle point.

With `System.loadLibrary("nativecalc")`, pass the **logical name** of the library without the `lib` prefix or file suffix. The JVM/native runtime searches for the filename following platform conventions, for example:

- Linux: `libnativecalc.so`
- macOS: `libnativecalc.dylib`
- Windows: `nativecalc.dll`

If you need to load a file by absolute path, use `System.load("/absolute/path/to/library")`. This method requires the full path and relies on the file actually existing on the machine/container.

### 3.1. C-Side JNI Function

You can use `javac -h` to generate a C header from the Java native method. The header ensures function names and signatures match the Java declarations.

Corresponding C code example:

~~~c
#include <jni.h>
#include "com_example_nativebridge_NativeMath.h"

JNIEXPORT jlong JNICALL
Java_com_example_nativebridge_NativeMath_add(
        JNIEnv *env,
        jclass type,
        jlong left,
        jlong right) {
    return left + right;
}
~~~

Because the method in the example is `static native`, the second parameter is `jclass`. For an instance native method, that parameter is `jobject`. Do not guess symbol names by hand; use the generated header or `RegisterNatives` and verify the JNI signature.

### 3.2. Generating the JNI Header

Example with the corresponding JDK:

~~~bash
mkdir -p build/classes build/include build/native
javac -h build/include -d build/classes src/main/java/com/example/nativebridge/NativeMath.java
~~~

This command generates the class and header inside the build directory. When a project uses Maven/Gradle, configure a dedicated native build task to generate headers and compile C; avoid committing generated files into the source tree if the pipeline can regenerate them.

## 4. Compiling the JNI Library on Each Platform

The C code from the previous section can be compiled into a shared library, though the compiler, include directories, and linker flags depend on the OS.

### 4.1. Linux: Creating `.so`

Example using GCC or Clang on Linux x86_64:

~~~bash
cc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -Ibuild/include -o build/native/libnativecalc.so src/main/c/nativecalc.c
~~~

Option meanings:

- `-fPIC`: generates position-independent code, usually required for shared objects.
- `-shared`: creates a shared library instead of an executable.
- `-I`: adds JNI header directories and the generated header directory.
- `-o`: names the output following Linux conventions.

Inspect the file:

~~~bash
file build/native/libnativecalc.so
readelf -h build/native/libnativecalc.so
nm -D build/native/libnativecalc.so
~~~

### 4.2. macOS: Creating `.dylib`

Example using Apple Clang on macOS:

~~~bash
mkdir -p build/native
clang -dynamiclib -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" -Ibuild/include -o build/native/libnativecalc.dylib src/main/c/nativecalc.c
~~~

Inspect the binary and dependencies:

~~~bash
file build/native/libnativecalc.dylib
otool -L build/native/libnativecalc.dylib
nm -gU build/native/libnativecalc.dylib
~~~

macOS uses Mach-O and its own install name / `@rpath` rules. If a dylib depends on another dylib, ensure install names and run paths point to valid packaged locations. Simply placing files next to the executable may not resolve all nested dependencies.

### 4.3. Windows: Creating `.dll`

Example using Microsoft Visual C++ Build Tools in a Developer Command Prompt:

~~~bat
if not exist build\native mkdir build\native
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" src\main\c\nativecalc.c /link /OUT:build\native\nativecalc.dll
~~~

Depending on the shell and project layout, create the output directory beforehand. MSVC may require appropriate runtime configuration, and dependent DLLs (such as the Visual C++ runtime) must be present on the target machine.

Inspect:

~~~bat
dumpbin /HEADERS build\native\nativecalc.dll
dumpbin /DEPENDENTS build\native\nativecalc.dll
dumpbin /EXPORTS build\native\nativecalc.dll
~~~

These illustrative commands assume Visual Studio Build Tools are installed and you are using a developer environment with `cl.exe`/`dumpbin.exe` in `PATH`.

## 5. Loading the Library by Name or Path

There are two main ways.

### 5.1. System.loadLibrary

~~~java
static {
    System.loadLibrary("nativecalc");
}
~~~

This approach uses a logical name, letting the runtime/loader find the library according to platform conventions and search paths. It is convenient when the library is installed in a standard location or the search path is already configured.

### 5.2. System.load

~~~java
static {
    String path = System.getProperty("app.native.library");
    if (path == null || path.isBlank()) {
        throw new IllegalStateException("Missing app.native.library");
    }
    System.load(Path.of(path).toAbsolutePath().toString());
}
~~~

This approach uses an absolute path. It is useful when the application manages libraries in a dedicated directory, such as a mount path in a container. Check that the file exists, has read permissions, and its own dependencies are present.

Never pass a path from an HTTP request into `System.load`. Only allow deployment-configured paths, restrict valid directories, and protect write permissions on directories holding libraries. Loading a native library brings native code into the process with that process's privileges.

## 6. Where Does the Runtime Loader Look for Shared Libraries?

Finding the JNI library file alone is not enough; the OS loader must also locate the dependencies that the library needs.

| Platform | Common mechanisms | Inspection tools |
| --- | --- | --- |
| Linux | RPATH/RUNPATH, loader cache, standard directories, `LD_LIBRARY_PATH` | `ldd`, `readelf -d`, `ldconfig -p` |
| macOS | install name, `@rpath`, `@loader_path`, `DYLD_LIBRARY_PATH`, and system security mechanisms | `otool -L`, `otool -l` |
| Windows | DLL search order, application directory, system directories, and `PATH` | `dumpbin /DEPENDENTS`, Process Monitor |

### 6.1. Linux

You can run:

~~~bash
LD_LIBRARY_PATH=/opt/orders/native-libs ./target/orders-service
~~~

This example is for a process launched in a shell with that environment variable set. For production, consider appropriate RPATH/RUNPATH, a managed library directory, and consistent packaging. Do not rely on the current working directory to locate libraries.

Inspect dependencies:

~~~bash
ldd /opt/orders/native-libs/libnativecalc.so
readelf -d /opt/orders/native-libs/libnativecalc.so
~~~

`ldd` is useful on trusted artifacts in test environments. For untrusted binaries, prefer tools that read static metadata like `readelf -d` instead of running through the system loader mechanism.

### 6.2. macOS

macOS has its own install name and run path rules. You can use:

~~~bash
otool -L /opt/orders/native-libs/libnativecalc.dylib
otool -l /opt/orders/native-libs/libnativecalc.dylib
~~~

Tokens like `@rpath`, `@loader_path`, and `@executable_path` specify relative dependency search locations. `DYLD_LIBRARY_PATH` can help during debugging, but is not a universal deployment choice; macOS security protections can affect loader environment variables in some situations.

### 6.3. Windows

Windows searches for DLLs following loader search order rules. Placing DLLs in the application directory or configuring `PATH` in a controlled manner is usually more predictable than relying on the working directory. Avoid adding directories writable by untrusted users to `PATH`, as doing so introduces DLL search-order hijacking risks.

Inspect direct dependencies using:

~~~bat
dumpbin /DEPENDENTS build\native\nativecalc.dll
~~~

If a dependent DLL is missing, an error can occur when loading the main library even though the main file exists.

## 7. ABI, libc, and Runtime Dependencies

Sharing the `.so` format does not mean two libraries are compatible. Linux shared libraries also depend on ABI, symbol versions, and the C runtime.

### 7.1. glibc and musl

Popular Linux distributions like Debian/Ubuntu typically use glibc; Alpine Linux uses musl. A library built in a glibc environment cannot run by default on Alpine musl. Errors may include the loader failing to find the interpreter, missing symbols, or libc incompatibility.

Resolution approach:

- Build and run in environments with a compatible libc.
- Use deliberately chosen builder/runtime base images.
- If musl is required, use a toolchain and Native Image configuration that properly supports that musl version.
- Inspect actual dependencies instead of assuming a `.so` file is portable across all Linux distributions.

### 7.2. Symbol Versions and System Versions

A library built on a newer distribution may reference newer symbol versions of glibc or system libraries. When running on an older distribution, the loader may report missing symbols even though both architectures are x86_64.

To reduce risk, build on the lowest compatible baseline supported by the product, or use builder/runtime images from a tested matrix. Never build on the latest personal workstation and assume every older server can run it.

### 7.3. C++ ABI and Runtime

If a JNI wrapper calls a C++ library, also consider:

- Compiler/toolchain ABI and the C++ runtime library.
- Versions of libstdc++/libc++ or Microsoft Visual C++ runtime.
- Symbol export conventions and name mangling.
- Memory ownership across both sides; avoid allocating in one runtime and freeing in another incompatible runtime.

Where possible, expose a stable C ABI at the JNI/C++ boundary: accept simple data types, and define ownership, error codes, and API versions clearly.

## 8. JNI Metadata in Spring AOT and Native Image

A JNI library can call back into Java via the JNI API, such as finding classes, obtaining method IDs, accessing fields, or invoking Java methods. During a Native Image build, types/members accessed dynamically by native code require appropriate metadata.

Spring Framework provides the Runtime Hints API for JNI. Illustrative example when C code needs to invoke public methods on a Java callback:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(CallbackJniHints.class)
class NativeCallbackConfiguration {
}

class CallbackJniHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.jni().registerType(
                NativeCallback.class,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

You can attach the registrar to a configuration class via `@ImportRuntimeHints` or register it using the appropriate AOT mechanism. This example applies when native code uses JNI to look up/invoke methods on `NativeCallback`. There is no need to register every application class if C code only performs calculations and does not call back into Java.

Distinguish the two directions:

- **Java calling native methods:** requires the library to be loaded and the native method to be properly linked/registered.
- **Native code accessing Java via JNI:** requires the types/members accessed by C code to be retained with matching JNI metadata.

Runtime Hints do not replace `.so`/`.dll`/`.dylib` files and do not fix ABI errors. If the loader cannot load the shared library, adding reflection/JNI hints will not solve that root cause.

## 9. Packaging the Native Executable with JNI Libraries

A clear deployment layout:

~~~text
orders-native/
├── bin/
│   └── orders-service
└── lib/
    ├── libnativecalc.so
    └── libvendorcodec.so
~~~

On Windows/macOS, corresponding files and layout will use `.dll`/`.dylib`. Clearly decide:

- Whether the binary loads JNI libraries by name or absolute path.
- Where libraries reside inside the image/package.
- Where transitive dependencies of the libraries reside.
- How loader path/RPATH/install name/PATH are configured.
- Whether the user running the application has appropriate read/execute permissions.
- Whether library versions are pinned and released alongside the application.

Avoid placing native libraries in temporary directories where another process could replace them. Directories holding native code need restricted write permissions, and artifacts should have checksums/signatures verified per your release process.

## 10. Packaging a Linux Container

The native executable and JNI `.so` must be built for the same target OS/architecture and runtime ABI. Multi-stage Dockerfile example:

~~~dockerfile
# Builder must match the target Linux/CPU and GraalVM toolchain.
FROM ghcr.io/graalvm/native-image-community:21 AS builder
WORKDIR /workspace

COPY . .
RUN ./mvnw -Pnative -DskipTests package
RUN mkdir -p target/native-libs build/include build/classes && javac -h build/include -d build/classes src/main/java/com/example/nativebridge/NativeMath.java && cc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -Ibuild/include -o target/native-libs/libnativecalc.so src/main/c/nativecalc.c

# Runtime image must have ABI/system libraries compatible with the builder output.
FROM debian:bookworm-slim
WORKDIR /app

COPY --from=builder /workspace/target/orders-service /app/orders-service
COPY --from=builder /workspace/target/native-libs/ /app/lib/

ENV APP_NATIVE_LIBRARY=/app/lib/libnativecalc.so
ENV LD_LIBRARY_PATH=/app/lib
EXPOSE 8080
ENTRYPOINT ["/app/orders-service"]
~~~

This Dockerfile is illustrative; builder tags, native output paths, and library locations must be adapted to your project. The runtime image must include any system libraries that the executable/JNI library depends on. Do not use `scratch` if the binary or JNI libraries require a dynamic loader, libc, or unpackaged dependencies.

The `target/native-libs/` directory in the example must be produced by a separate Maven/Gradle task compiling C code in a prior step; the Spring Boot Maven/Gradle plugin does not automatically compile C files in the source tree. The builder must also have a C compiler and matching JNI headers. If the library has transitive dependencies in the same `/app/lib` directory, `LD_LIBRARY_PATH` helps the Linux loader locate them; on other platforms, use the corresponding loader mechanism.

In the Java example above, the application reads `APP_NATIVE_LIBRARY` via `System.getenv(...)` and calls `System.load(...)`. You can run the container as follows:

~~~bash
docker run --rm -p 8080:8080 -e APP_NATIVE_LIBRARY=/app/lib/libnativecalc.so orders-service:native
~~~

If using `System.loadLibrary("nativecalc")`, configure an appropriate search path in the image or design RPATH/RUNPATH. After building the image, run smoke tests inside the container and inspect dependencies with available tools or a compatible debug stage.

### 10.1. Multi-Platform Container Builds

If releasing for both AMD64 and ARM64, you must build separate native executables and JNI libraries for each architecture. A Docker manifest list can point to multiple platform images, but a manifest list does not convert binaries inside an image.

Conceptual example:

~~~text
registry.example.com/orders-service:1.0
├── linux/amd64 -> AMD64 executable + AMD64 JNI .so
└── linux/arm64 -> ARM64 executable + ARM64 JNI .so
~~~

Do not copy an AMD64 `.so` file into an ARM64 image just because the filename and path match. Verify the architecture of every shared library in each image.

## 11. Diagnosing Library Load Errors

| Symptom | Possible cause | How to inspect |
| --- | --- | --- |
| `UnsatisfiedLinkError: no ... in java.library.path` | JNI library not found by name | Check logical name, filename, search path, and read permissions |
| `UnsatisfiedLinkError: ... wrong ELF class` | Wrong architecture or bitness | Use `file`/`readelf -h` to check the executable and `.so` |
| `cannot open shared object file` | Missing file or transitive dependency, wrong loader path | Use `ldd`/`readelf -d` and inspect directories |
| `undefined symbol` | ABI/symbol version or dependency library mismatch | Check exported/required symbols, versions, and load order |
| `GLIBC_x.y not found` | Build requires newer glibc than runtime provides | Choose a compatible baseline or rebuild |
| macOS reports image not found | Incorrect install name/`@rpath` or dylib dependency | Use `otool -L` and `otool -l` |
| Windows reports DLL load failed | Missing dependent DLL, C++ runtime, or wrong architecture | Use `dumpbin /DEPENDENTS` and check `PATH` |
| Native executable runs but JNI call crashes | Wrong JNI signature, ownership, memory, or thread handling | Check `javac`-generated header, JNI signature, and native debugger |

Investigation flow:

~~~mermaid
flowchart TD
    A["Native app cannot load/call library"] --> B{"Does the library file exist?"}
    B -- "No" --> C["Check packaging, mount, and path"]
    B -- "Yes" --> D{"Do OS/CPU/binary format match?"}
    D -- "No" --> E["Rebuild JNI library for the right target"]
    D -- "Yes" --> F{"Are dependencies and ABI compatible?"}
    F -- "No" --> G["Check libc, symbol versions, runtime, and loader path"]
    F -- "Yes" --> H{"Do JNI symbol/signature match?"}
    H -- "No" --> I["Regenerate header, fix signature/RegisterNatives"]
    H -- "Yes" --> J["Check JNI metadata, memory, threads, and native crash"]
~~~

Always capture logs and output from the exact binary being executed. Inspecting files on the build machine does not prove files in the production container are identical or share the same dependencies.

## 12. Platform-Specific Artifact Inspection Commands

| Goal | Linux | macOS | Windows |
| --- | --- | --- | --- |
| View format/architecture | `file libnativecalc.so` | `file libnativecalc.dylib` | `dumpbin /HEADERS nativecalc.dll` |
| View dependencies | `ldd libnativecalc.so` | `otool -L libnativecalc.dylib` | `dumpbin /DEPENDENTS nativecalc.dll` |
| View symbols | `nm -D libnativecalc.so` | `nm -gU libnativecalc.dylib` | `dumpbin /EXPORTS nativecalc.dll` |
| View dynamic section/paths | `readelf -d libnativecalc.so` | `otool -l libnativecalc.dylib` | PE/loader diagnostics tools |

Run checks on both the executable and JNI libraries. A `.so` may match the architecture yet depend on another `.so` with the wrong architecture or absent from the runtime image.

## 13. Multi-Platform Release Checklist

- [ ] Identified OS and CPU architecture for each target.
- [ ] Native executable is built for the right target.
- [ ] JNI shared libraries are built for the same OS/architecture/ABI.
- [ ] JNI headers and signatures match Java declarations.
- [ ] Library names follow OS conventions or use a managed absolute path.
- [ ] Transitive dependencies are present and loader paths are configured.
- [ ] Verified glibc/musl, symbol versions, and C/C++ runtimes.
- [ ] JNI callbacks into Java have required metadata if accessed dynamically.
- [ ] Container base image is compatible with the executable and shared libraries.
- [ ] Runtime user has read permission on libraries without arbitrary write access to replace files.
- [ ] Tested native calls on each real target, not only on the build machine.
- [ ] Recorded checksums, versions, and architectures of the executable and each JNI library.

### Self-Assessment Questions

1. How do a native executable and a JNI shared library differ during build and deployment?
2. Why can an x86_64 `.so` file not be loaded on Linux ARM64?
3. How does `System.loadLibrary("nativecalc")` differ from `System.load("/path/libnativecalc.so")`?
4. Why can glibc and musl still be incompatible even on the same Linux x86_64 architecture?
5. If a JNI library exists yet reports a missing symbol, which dependencies and ABI aspects should be checked?
6. When C code calls back into Java via JNI, what role do Runtime Hints play?
7. Why does a multi-platform Docker image need separate executables and JNI libraries for each architecture?
8. Why should `scratch` not be used as a runtime image when an application still depends on unpackaged dynamic libraries?

## References

- [GraalVM Native Image — JNI](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/): JNI support and metadata for access from native code.
- [GraalVM Native Image — Build Configuration](https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildConfiguration/): native-image builder and toolchain configuration.
- [Spring Framework — Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): Runtime Hints API, including reflection/JNI/resource capabilities.
- [JNI Design Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): Java Native Interface architecture and interaction rules.
- [Linux dynamic linker](https://man7.org/linux/man-pages/man8/ld.so.8.html): rules for locating shared objects on Linux.

**Expected outcome:** able to choose the right `.so`/`.dll`/`.dylib` library for the target, compile and load a JNI library, verify dependencies/ABI, and package it alongside the native executable. When deploying across platforms, each artifact must be built and tested on a compatible OS, architecture, and runtime combination; identical filenames do not guarantee binaries are interchangeable.

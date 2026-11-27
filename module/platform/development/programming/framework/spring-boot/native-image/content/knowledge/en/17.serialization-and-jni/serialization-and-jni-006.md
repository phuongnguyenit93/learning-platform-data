# Managing Paths, Loading Mechanisms, and Distributing Native Libraries

## 1. Why Does a Spring Boot Native Image Application Need to Manage Native Libraries?

A Java application can invoke C/C++ code through the **Java Native Interface (JNI)**. Native libraries are typically distributed as operating-system shared libraries: `.so` on Linux, `.dylib` on macOS, or `.dll` on Windows. For example, a Spring Boot application may use libraries for cryptography, image processing, data compression, device drivers, or vendor SDKs.

When running on the JVM, libraries are usually loaded with `System.loadLibrary()` or `System.load()`. When compiled into a **GraalVM Native Image**, the application can still use JNI, but three layers must be addressed together:

1. **Java/JNI loader:** locating the library requested by Java code.
2. **OS dynamic loader:** locating the dependent libraries required by that newly loaded native library.
3. **Artifact distribution:** ensuring the executable, JNI libraries, and native dependencies are present in the deployment environment with the matching OS, architecture, and ABI.

A common error occurs when `libcodec.so` is placed in the right location yet the application still throws `UnsatisfiedLinkError`. The cause could be that Java cannot find the file, or that Java found the file but the OS loader cannot find one of its dependencies. These two failures require different diagnostic steps.

In the **SPRING_BOOT_NATIVE_IMAGE** module, this lesson helps you organize native libraries so the executable runs reliably on development machines, CI, and containers. The content focuses on **paths, loading mechanisms, and distributing native libraries**; reachability metadata for JNI is covered as needed to distinguish metadata from library files.

After this lesson, you will be able to:

- Distinguish `System.loadLibrary` from `System.load`.
- Determine how GraalVM Native Image locates JNI libraries.
- Distinguish the Java library path from the OS loader's dependency search path.
- Register JNI metadata for Java types/members accessed by C/C++ code.
- Package native libraries and dependencies alongside the native executable.
- Diagnose missing library, architecture mismatch, ABI mismatch, or missing symbol errors.

## 2. Distinguishing Native Integration Directions

Before configuring paths, clarify **who calls whom**. There are two common directions:

| Integration direction | Call flow | Typical mechanism |
|---|---|---|
| Java calls native code | Java/Spring Boot → C/C++ function | Java declares a `native` method; the JNI library implements that method |
| Native code calls back into Java | C/C++ → Java class/method/field | Native code uses JNI functions such as `FindClass`, `GetMethodID`, `Call<Type>Method` |

With the first direction, Java needs to load the library containing the native method implementations. Native Image generates a wrapper for methods declared with the `native` keyword; when the method is called, the wrapper looks up the JNI symbol in loaded libraries. The library must be distributed and loaded properly.

With the second direction, Native Image cannot automatically infer every class, method, or field that C/C++ code will look up by name at runtime. Those elements must be declared via **JNI reachability metadata** at build time. This metadata describes Java accessibility from JNI; it is not a `.so`/`.dll` file and does not replace packaging the native library.

Another easily confused concept is **building Native Image as a shared library**. The `native-image --shared` option builds a native library from a Java program so a C/C++ application can call into Java via the Native Image C API or the JNI Invocation API. That is the reverse integration direction compared to a Spring Boot executable loading an external JNI library. This lesson primarily covers **Spring Boot Native Image calling existing native libraries**.

## 3. Choosing the Right Loading API: loadLibrary or load?

Java provides two primary APIs:

| API | Argument | Rule |
|---|---|---|
| `System.loadLibrary("codec_jni")` | Logical name, without prefix, extension, or path | Java maps the name to platform conventions and searches library paths |
| `System.load("/opt/app/lib/libcodec_jni.so")` | Absolute path to the library file | Requires an absolute path; suitable when the application manages a fixed location |

The logical name `codec_jni` can be mapped to:

| Platform | Typical filename | Java call |
|---|---|---|
| Linux | `libcodec_jni.so` | `System.loadLibrary("codec_jni")` |
| macOS | `libcodec_jni.dylib` | `System.loadLibrary("codec_jni")` |
| Windows | `codec_jni.dll` | `System.loadLibrary("codec_jni")` |

You can inspect the filename mapped by the JDK:

```java
String logicalName = "codec_jni";
String platformName = System.mapLibraryName(logicalName);
System.out.println(platformName);
```

The output depends on the OS and running JDK. Do not manually prepend prefixes or append extensions to the `System.loadLibrary` argument.

### Example of Declaring a JNI Method

Suppose a C/C++ library provides a data compression function:

```java
package com.example.codec;

public final class NativeCodec {

    static {
        System.loadLibrary("codec_jni");
    }

    private NativeCodec() {
    }

    public static native byte[] compress(byte[] input);
}
```

The static initializer loads the library before the first invocation of the native method. The `compress` method is declared `native`, so its implementation resides in the native library rather than in Java bytecode.

With JNI name mangling based on class/package/method names, a corresponding C function has the general form:

```c
#include <jni.h>
#include "com_example_codec_NativeCodec.h"

JNIEXPORT jbyteArray JNICALL
Java_com_example_codec_NativeCodec_compress(
    JNIEnv *env,
    jclass type,
    jbyteArray input
) {
    /* Read input data, call the compression library, and create a jbyteArray to return. */
    return input; /* Placeholder solely to illustrate the JNI signature. */
}
```

In real projects, use headers generated by `javac -h` to avoid symbol name and JNI signature mistakes. If a library uses `RegisterNatives`, mapping methods to function pointers happens explicitly at initialization; in that case, JNI mangled symbol names are not strictly required.

### When to Use an Absolute Path?

If the file location is provided by the deployment environment, you can use `System.load`:

```java
String libraryDirectory = System.getenv("APP_NATIVE_LIB_DIR");
if (libraryDirectory == null || libraryDirectory.isBlank()) {
    throw new IllegalStateException("APP_NATIVE_LIB_DIR is not configured");
}

String libraryFile = Path.of(
    libraryDirectory,
    System.mapLibraryName("codec_jni")
).toAbsolutePath().normalize().toString();

System.load(libraryFile);
```

This example requires importing `java.nio.file.Path`. The `APP_NATIVE_LIB_DIR` variable must point to a trusted directory with appropriate read permissions containing the platform-matching library file. `System.load` requires an absolute path; relative paths or reliance on the current working directory easily cause the application to behave differently between local environments and containers.

### Notes on Newer JDKs

On newer JDKs, `System.load` and `System.loadLibrary` are classified as restricted methods because they allow Java code to load and execute native code outside the runtime. When testing on the JVM, pay attention to native-access warnings and configure native access permissions for the calling module according to your JDK's policy. For classpath applications, the JDK may use `--enable-native-access=ALL-UNNAMED`; modular applications should specify the exact module needing access. Do not disable checks globally as a long-term fix.

## 4. Where Does Native Image Search for Libraries?

According to GraalVM's JNI documentation, when a Native Image application calls `System.loadLibrary()` or related APIs, Native Image searches **the directory containing the native executable first**, and only then searches the Java library path. Thus, if the JNI library sits in the same directory as the executable, additional Java path configuration is often unnecessary.

Simple layout example:

```text
/opt/service/
├── service
└── libcodec_jni.so
```

In this Linux example, `service` is the native executable and `libcodec_jni.so` is the JNI library. When code calls `System.loadLibrary("codec_jni")`, Native Image can find the library right in the executable's directory.

If libraries are organized in a separate directory:

```text
/opt/service/
├── bin/
│   └── service
└── lib/
    └── libcodec_jni.so
```

you must configure the Java library path at startup or use `System.load` with an absolute path. For example, with `System.loadLibrary`, you can pass the property when running the native executable if your Native Image version supports it:

```bash
./bin/service -Djava.library.path=/opt/service/lib
```

Verify the runtime option and property behavior in your project's exact GraalVM release. Do not call `System.setProperty("java.library.path", ...)` after application class loading has started and expect the loader to refresh all library lookup caches.

**Important point:** The Java library path only helps locate the JNI library requested by Java. It does not automatically resolve all dependencies of that library. For instance, `libcodec_jni.so` may depend on `libvendorcodec.so`; after finding the first file, the Linux dynamic loader must still locate the second file using OS-specific rules.
## 5. Distinguishing JNI Library Loading from JNI Reachability Metadata

Two configurations are often confused:

- **Native paths/libraries:** specify where `.so`, `.dylib`, or `.dll` files live and how the OS loader locates their dependencies.
- **JNI reachability metadata:** specifies which Java types/members native code is permitted to look up, instantiate, or invoke when the Native Image application runs.

Having the library file in the right place is insufficient if C/C++ code calls back into Java without metadata. Conversely, complete metadata cannot compensate for a `libcodec_jni.so` file that is missing from the package or fails to load.

### 5.1. When Java Calls Native Methods

For example, `NativeCodec.compress(byte[])` is declared with the `native` keyword. Native Image recognizes this declaration and generates a wrapper to transition from Java to native code. When invoked, the wrapper searches for the matching symbol across loaded libraries. You need:

- The JNI library compiled for the matching OS/architecture/ABI.
- The library loaded before the native method is called.
- Matching JNI symbol name and signature, or initialization code calling `RegisterNatives`.
- Dependent libraries of the JNI library also discoverable by the OS loader.

If C/C++ only performs computations on passed-in data and returns results to Java, JNI metadata for Java callbacks may not be needed. However, if the C/C++ library invokes `FindClass`, `GetMethodID`, `GetFieldID`, or `Call<Type>Method` functions to access Java, continue to the steps below.

### 5.2. When Native Code Accesses Java

Suppose the C/C++ library receives a callback and invokes `onComplete(String)` on a Java object:

```c
jclass callbackType = (*env)->FindClass(
    env,
    "com/example/codec/NativeCallback"
);

jmethodID onComplete = (*env)->GetMethodID(
    env,
    callbackType,
    "onComplete",
    "(Ljava/lang/String;)V"
);

/* Once a valid callback object is available: */
(*env)->CallVoidMethod(env, callbackObject, onComplete, message);
```

Native Image cannot predict every class/member name native code will look up. Therefore, provide JNI metadata for the exact types and members. With current reachability metadata, you can place a `reachability-metadata.json` file under `META-INF/native-image/<groupId>/<artifactId>/` on the classpath:

```json
{
  "jni": [
    {
      "type": "com.example.codec.NativeCallback",
      "jniAccessible": true,
      "methods": [
        {
          "name": "onComplete",
          "parameterTypes": [
            "java.lang.String"
          ]
        }
      ]
    }
  ]
}
```

The entry above permits JNI access to the listed type and method. If C/C++ also uses `GetFieldID` to read or write fields, add those exact field names to `fields`. If native code instantiates objects via `NewObject`, register the corresponding constructor. Do not enable `allDeclaredMethods` or `allDeclaredFields` just to fix a single call.

### 5.3. Contributing JNI Hints via Spring RuntimeHints

Spring Framework provides `RuntimeHints.jni()` to register Java types/members accessed via JNI. You can write a registrar and attach it to the bean using the native library:

```java
import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.TypeReference;
import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.stereotype.Component;

public class NativeCallbackRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.jni().registerType(
            NativeCallback.class,
            typeHint -> typeHint.withMethod(
                "onComplete",
                List.of(TypeReference.of(String.class)),
                ExecutableMode.INVOKE
            )
        );
    }
}

@Component
@ImportRuntimeHints(NativeCallbackRuntimeHints.class)
class NativeCodecService {
    // Calls NativeCodec and receives callbacks from the native library.
}
```

The Java class accessed by JNI can be declared as follows:

```java
package com.example.codec;

public class NativeCallback {
    public void onComplete(String message) {
        // Handle the result returned from the native library.
    }
}
```

This example illustrates one callback method. If native code requires additional constructors or fields, add those exact members using the API matching your Spring Framework version. After AOT processing, inspect the generated metadata to confirm the JNI entry is present in the output.

**Distinction from serialization:** if the application uses `ObjectInputStream`/`ObjectOutputStream` to serialize Java objects, use the corresponding serialization metadata (such as `RuntimeHints.serialization()` or the `serializable` field in reachability metadata). Do not register JNI hints merely because the application uses serialization; these are two independent mechanisms.

## 6. OS-Specific Dependency Search Paths

Once the Java loader finds the primary JNI library, the operating system must load every dependency referenced by that library. For example:

```text
Native Image executable
    |
    | System.loadLibrary("codec_jni")
    v
libcodec_jni.so
    |
    | DT_NEEDED: libvendorcodec.so
    v
libvendorcodec.so
    |
    | next dependency
    v
system libraries
```

`java.library.path` does not replace the OS loader's dependency resolution mechanism. Configure both layers if the JNI library has its own dependencies.

### 6.1. Linux

On Linux, shared libraries are typically named `lib<name>.so`. The dynamic linker (usually `ld-linux`) searches for shared objects declared in ELF metadata. For dependencies without slashes in their names, the common search order includes:

1. `DT_RPATH` if present and `DT_RUNPATH` is absent.
2. `LD_LIBRARY_PATH` (except in certain secure-execution modes).
3. `DT_RUNPATH` of the object directly needing the dependency.
4. The `/etc/ld.so.cache` cache.
5. Default directories such as `/lib` and `/usr/lib` (architecture-dependent).

A relocatable packaging approach across directories is to use `$ORIGIN` in `RUNPATH`. The dynamic linker expands this token to the directory containing the executable or corresponding shared object. For example, when linking `libcodec_jni.so` with dependencies in the same `lib` directory:

```bash
gcc -shared -fPIC \
  -Wl,-rpath,'$ORIGIN' \
  -o libcodec_jni.so codec_jni.c
```

`$ORIGIN` is intentionally single-quoted so the shell does not expand it before passing it to the linker. If `libcodec_jni.so` depends on libraries in a sibling directory, such as `../vendor`, you can configure `$ORIGIN/../vendor` to match your chosen layout.

You can use `LD_LIBRARY_PATH` for testing or controlled environments:

```bash
LD_LIBRARY_PATH=/opt/service/lib:/opt/service/vendor \
  ./service -Djava.library.path=/opt/service/lib
```

Do not rely on operators manually setting this variable across every environment. For distributed products, prefer an appropriate RPATH/RUNPATH or managed system configuration.

Diagnostic commands:

```bash
# Inspect dependencies and RPATH/RUNPATH recorded in the ELF.
readelf -d /opt/service/lib/libcodec_jni.so

# Inspect dependencies that the loader can resolve on the current machine.
ldd /opt/service/lib/libcodec_jni.so

# Trace library search at runtime.
LD_DEBUG=libs ./service
```

Only run `ldd` on trusted binaries; when inspecting untrusted files, prefer static ELF inspection tools such as `readelf`.

### 6.2. macOS

On macOS, dynamic libraries typically end in `.dylib`. The dynamic loader is `dyld`. Install names can use tokens:

- `@executable_path`: directory containing the main executable.
- `@loader_path`: directory containing the image (executable or dylib) referencing the dependency.
- `@rpath`: a path resolved through declared run-path search paths.

When packaging bundled applications, configure relative install names and runpaths, such as `@rpath/libcodec_jni.dylib` with a suitable `LC_RPATH`. Avoid hardcoding absolute paths to build directories on a developer machine.

Inspect dependencies and runpaths:

```bash
file ./service
otool -L ./libcodec_jni.dylib
otool -l ./libcodec_jni.dylib
```

`otool -L` lists the install names referenced by the library; `otool -l` displays load commands, including runpath entries. If you need to modify the install name of an existing binary, `install_name_tool` can help, but prefer fixing linker flags in the build pipeline so future builds reproduce the right result.

### 6.3. Windows

On Windows, dynamic libraries typically end in `.dll`. Distinguish:

- The Java loader must locate the DLL requested by `System.loadLibrary`.
- The Windows loader must locate any DLL dependencies of that DLL.

Windows enforces its own DLL search order rules, affected by the application directory, system directories, explicitly added directories, and `PATH` depending on load mode/flags. A controllable distribution pattern is placing the JNI DLL and its private dependencies in a write-protected application directory.

Example layout:

```text
C:\apps\service\
├── service.exe
├── codec_jni.dll
└── vendorcodec.dll
```

You can inspect dependencies using Visual Studio tools:

```powershell
dumpbin /DEPENDENTS C:\apps\service\codec_jni.dll
```

Or use an appropriate PE/DLL analysis tool in the build environment. Avoid placing libraries with the same name in a current working directory writable by other users, as loading the wrong DLL can lead to unintended code execution. When loading from a custom directory, prefer Windows APIs that configure safe search directories in native loader code, or place libraries in the application directory per deployment policy.
## 7. Packaging Libraries with the Native Executable

Native Image does not automatically turn external native library files into part of the executable. If the application calls `System.loadLibrary("codec_jni")`, ensure the JNI library and its dependencies are distributed in the installation package or runtime container.

### 7.1. Simple Layout: Placing JNI Libraries Next to the Executable

This requires the least configuration with GraalVM Native Image:

```text
/opt/service/
├── service
├── libcodec_jni.so
└── libvendorcodec.so
```

`service` is the native executable; `libcodec_jni.so` is the library Java loads; `libvendorcodec.so` is a dependency of the JNI library. Native Image searches for JNI libraries in the executable's directory before checking the Java library path. For the OS loader to locate `libvendorcodec.so`, configure an appropriate RUNPATH on `libcodec_jni.so` (for example, `$ORIGIN` if dependencies sit in the same directory).

This layout adapts per platform:

- Linux: `service`, `libcodec_jni.so`, and `.so` dependencies.
- macOS: `service`, `libcodec_jni.dylib`, and `.dylib` dependencies.
- Windows: `service.exe`, `codec_jni.dll`, and `.dll` dependencies.

Do not share a single native binary across all platforms. Each OS/architecture needs matching artifacts.

### 7.2. Separating `bin` and `lib` Directories

If you prefer separating executables from libraries:

```text
/opt/service/
├── bin/
│   └── service
└── lib/
    ├── libcodec_jni.so
    └── libvendorcodec.so
```

You can launch with separate Java library path and OS loader path:

```bash
LD_LIBRARY_PATH=/opt/service/lib \
  /opt/service/bin/service \
  -Djava.library.path=/opt/service/lib
```

In this example:

- `-Djava.library.path` helps Native Image locate the JNI library requested by Java code via `System.loadLibrary`.
- `LD_LIBRARY_PATH` helps the Linux dynamic linker locate dependencies of the JNI library.
- The two variables serve different roles; setting one does not replace the other.

For production environments, prefer relative RUNPATH settings and application-managed paths. `LD_LIBRARY_PATH` is helpful for experimentation or controlled deployments, though relying on it should be documented clearly in manifests/run scripts.

### 7.3. If Native Libraries Are Packaged Inside a JAR

Some Java libraries package binaries by classifier or as resources, for example:

```text
META-INF/native/linux-x86_64/libcodec_jni.so
META-INF/native/linux-aarch64/libcodec_jni.so
META-INF/native/windows-x86_64/codec_jni.dll
```

The OS loader cannot directly load a resource inside a JAR or a resource embedded in a Native Image. If a library is distributed this way, the application must:

1. Select the matching resource for the OS/architecture.
2. Read the resource using `getResourceAsStream`.
3. Write its contents to a temporary file or a safely writable application directory.
4. Call `System.load` with the absolute path of the extracted file.
5. Ensure transitive dependencies of the library are also discoverable.

Abbreviated example:

```java
Path extractedLibrary = Files.createTempFile(
    "codec-jni-",
    System.mapLibraryName("codec_jni")
);

try (InputStream input = NativeCodec.class.getResourceAsStream(
        "/META-INF/native/linux-x86_64/libcodec_jni.so")) {
    if (input == null) {
        throw new IllegalStateException("Native library resource is missing");
    }
    Files.copy(input, extractedLibrary, StandardCopyOption.REPLACE_EXISTING);
}

extractedLibrary.toFile().deleteOnExit();
System.load(extractedLibrary.toAbsolutePath().toString());
```

This only illustrates a single Linux x86_64 platform. Real applications must pick resources based on verified platform checks, handle file permissions and temp-file lifecycles, and extract any needed dependencies. For native executables running in containers, **placing libraries alongside the executable or in a configured runtime directory** is usually easier to operate and diagnose than dynamic extraction.

Do not use `URL.getFile()` to get a filesystem path from a resource embedded in a Native Image. Embedded resources may use the `resource:` URL scheme instead of `file:`; read them via streams.

## 8. Packaging in Docker/Containers

The runtime container must include the native executable, JNI libraries, and all required native dependencies. A minimal Linux Dockerfile might look like this, assuming all files sit side by side and the JNI library's RUNPATH is configured:

```dockerfile
FROM debian:bookworm-slim

WORKDIR /opt/service

COPY service ./service
COPY libcodec_jni.so ./libcodec_jni.so
COPY libvendorcodec.so ./libvendorcodec.so

RUN chmod 0555 ./service \
    && chmod 0444 ./*.so

USER 10001:10001

EXPOSE 8080

ENTRYPOINT ["./service"]
```

This Dockerfile only illustrates the layout. Choose a base image compatible with the built binaries:

- The native executable and JNI libraries must match the Linux architecture, such as `amd64` or `arm64`.
- If binaries depend on glibc, the run image must provide a compatible glibc; musl-based images cannot be swapped in arbitrarily.
- If JNI libraries use a C++ runtime or other system libraries, the run image must supply those exact runtime dependencies.
- Copy only required runtime libraries into the final image; omit compilers, headers, or build tools from production if unneeded.
- Run as a user without write permissions to the directory containing installed libraries to prevent runtime library replacement.

### With Cloud Native Buildpacks

Spring Boot can build container images via Maven `spring-boot:build-image` or Gradle `bootBuildImage`. However, having the native executable inside the image **does not automatically guarantee** external `.so` files are included in the run image.

If the application depends on custom native libraries, specify explicitly how they enter the final image:

- Use an additional or custom buildpack to copy libraries into the runtime layer.
- Use an organization-provided builder/run image that already contains the required libraries, if distribution policy permits.
- Or use a Dockerfile/multi-stage build for exact control over copied files.

After building the image, inspect the final image's filesystem and run smoke tests inside that container itself. Do not inspect only the builder container, since the builder may contain libraries absent from the run image.

### Distinguishing Build Artifacts from the Runtime Package

| Component | Present in runtime package? | Purpose |
|---|---|---|
| Native executable | Yes | Starts the application |
| JNI library (`.so`, `.dylib`, `.dll`) | Yes, if called by the application | Implements native methods |
| Transitive native dependencies | Yes, if required by the loader | Supplies symbols referenced by the JNI library |
| `reachability-metadata.json` | Usually build input only, not a runtime library | Registers dynamic access during Native Image creation |
| GraalVM compiler, C compiler, linker | Not needed in normal runtime | Used during the build phase |
| Full JDK/JRE | Native executables normally do not need a separate JVM | Only needed for JVM workflows or other tooling |

## 9. Compiling and Verifying a JNI Library on Linux

Suppose Java code declares `NativeCodec.compress(byte[])` and C code implements that method. An abbreviated development workflow:

```bash
mkdir -p build/classes build/include build/native

# Compile Java and generate JNI headers.
javac -h build/include \
  -d build/classes \
  src/main/java/com/example/codec/NativeCodec.java

# Compile the JNI implementation into a shared library.
cc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -Wl,-rpath,'$ORIGIN' \
  -o build/native/libcodec_jni.so \
  src/main/c/codec_jni.c
```

Key points to note:

- `javac -h` generates headers with JNI declarations matching method signatures.
- `-fPIC -shared` builds a shared library on Linux.
- `JAVA_HOME/include` and the platform-specific directory contain `jni.h` and `jni_md.h`.
- `-Wl,-rpath,'$ORIGIN'` sets a relative RUNPATH so the library can find dependencies sitting alongside it; use only if it matches your dependency layout.
- Compiler, headers, and ABI must match the target OS/architecture.

Inspect the generated file:

```bash
file build/native/libcodec_jni.so
readelf -h build/native/libcodec_jni.so
readelf -d build/native/libcodec_jni.so
nm -D build/native/libcodec_jni.so
```

`file` and `readelf -h` check ELF format/architecture; `readelf -d` inspects dependencies and RPATH/RUNPATH; `nm -D` lists exported symbols. Verify that JNI symbol names match the header generated by `javac -h` or that the library registers methods with `RegisterNatives`.

Next, place `libcodec_jni.so` in the chosen runtime directory, build the Spring Boot Native Image, and run tests on the executable. Exact build commands depend on the Maven/Gradle plugin; what must be verified is that the native executable is built with the matching classpath/AOT metadata and the JNI file is supplied at runtime.

## 10. Layer-by-Layer Testing and Diagnostics

Do not start by adding dozens of directories to `PATH` or switching base images blindly. Identify which loader is reporting the failure.

| Symptom | Likely failing layer | Diagnostic direction |
|---|---|---|
| `no codec_jni in java.library.path` or library name not found | Java/JNI loader | Check logical name, `java.library.path`, and executable directory |
| `cannot open shared object file: libvendorcodec.so` | Linux dynamic loader | Check `DT_NEEDED`, RUNPATH, `LD_LIBRARY_PATH`, and whether the library exists in the image |
| `UnsatisfiedLinkError: no ... in java.library.path` | Java cannot locate the library or cannot load it | Check both the file path and nested loader errors |
| `undefined symbol` | Linker/symbol resolution | Check ABI, library versions, exported symbols, and dependencies |
| `wrong ELF class` or architecture mismatch | Native file does not match target | Check `file`, `readelf -h`, host and container architectures |
| `GLIBC_x.y not found` | Incompatible ABI/libc runtime | Build for the right target or use a run image with compatible glibc |
| `The specified module could not be found` on Windows | Missing main DLL or a dependent DLL | Check all DLL dependencies, not just the primary JNI file |
| `MissingJNIRegistrationError` | Native code accesses Java member lacking JNI metadata | Check `FindClass`, `GetMethodID`, `GetFieldID`, and reachability metadata |
| `UnsatisfiedLinkError: '...native method...'` | Native method symbol not found | Check JNI name mangling, signature, `RegisterNatives`, and loaded libraries |
| Works locally but fails in container | Runtime image missing files or different ABI/architecture | Inspect the final image, not just the builder image |

### Quick Inspection Commands

On Linux:

```bash
# Inspect architecture and dynamic dependencies.
file ./service ./libcodec_jni.so
readelf -d ./libcodec_jni.so
ldd ./libcodec_jni.so

# Observe how the loader locates libraries.
LD_DEBUG=libs ./service
```

On macOS:

```bash
file ./service ./libcodec_jni.dylib
otool -L ./libcodec_jni.dylib
otool -l ./libcodec_jni.dylib
```

On Windows PowerShell:

```powershell
Get-Item .\service.exe, .\codec_jni.dll
dumpbin /DEPENDENTS .\codec_jni.dll
where.exe codec_jni.dll
```

`where.exe` searches directories currently in `PATH`; it does not replace checking DLL dependencies along the Windows loader search order. Whenever possible, use a PE dependency analysis tool to find missing secondary DLLs.

## 11. Testing JNI and Metadata Before Release

A solid verification workflow progresses from JVM to Native Image, and then to the exact distribution environment.

### Step 1: Test JNI on the JVM

Run the application on a JVM with the same OS/architecture as the native library. Confirm:

- `System.loadLibrary` or `System.load` loads the expected file.
- Native methods execute and return valid results.
- Callbacks from native code into Java succeed.
- No missing dependency or symbol errors occur.

JVM tests only prove the library works in that JVM environment. They do not prove the native executable has sufficient JNI metadata.

### Step 2: Check JNI Metadata

If the library calls back into Java, inspect `reachability-metadata.json` or hints generated by Spring AOT. Native Image supports exact reachability metadata mode in corresponding releases:

```text
--exact-reachability-metadata
```

When running the native executable or tests, you can enable missing registration reporting:

```text
-XX:MissingRegistrationReportingMode=Warn
```

Exercise every branch involving JNI callbacks: success, error, asynchronous callbacks, field reads/writes, and object instantiation if the library uses those operations. A test that only invokes a native method without triggering callbacks does not prove callback Java members are registered.

### Step 3: Build and Run the Native Executable

Once metadata is verified:

1. Run Maven/Gradle AOT and native build per project configuration.
2. Inspect build logs and output metadata.
3. Place JNI libraries in the runtime location or configure the library path.
4. Run the executable directly on the target OS/architecture.
5. Trigger JNI paths and verify results.

If metadata is missing for a Java member invoked from native code, GraalVM may report `MissingJNIRegistrationError`. If a library or symbol cannot be found, errors typically surface as `UnsatisfiedLinkError` or OS loader errors. Read the message and stack trace carefully to pinpoint the failing layer.

### Step 4: Verify in the Final Container

Build the image, then run that built image itself. Do not test only the native executable on the host. Inside the container, verify:

- Does the JNI file actually exist in the final image?
- Does the container user have read and load permissions for the library?
- Are transitive native dependencies present?
- Are OS, CPU architecture, libc, and C/C++ runtimes compatible?
- Does the container successfully run the endpoint/task requiring JNI?

A library might exist in the builder stage yet never be copied to the final stage. Only testing the final container catches this reliably.

## 12. Distinguishing Path, Metadata, and ABI Errors

When a native app fails, classify the error before fixing it:

| Question | If the answer is “no” | Resolution |
|---|---|---|
| Did the Java loader find the main JNI file? | Logical name or path not found | Check `System.loadLibrary`, `System.load`, and `java.library.path` |
| Did the OS loader find dependencies of the JNI library? | Missing dependent `.so`/DLL | Check RUNPATH, `LD_LIBRARY_PATH`, app directory, or dependency packages |
| Does the native method symbol exist? | JNI symbol not found | Check JNI headers, package/class/method names, signatures, or `RegisterNatives` |
| Can native code access Java types/members? | Missing JNI registration | Add the right JNI metadata/hints |
| Does the binary match the platform? | Wrong ELF/PE/Mach-O, CPU, or ABI | Rebuild for the target and pick a compatible run image |
| Can the file be read/loaded? | Incompatible permissions or policy | Check owner, mode, mount flags, and runtime user privileges |

Do not use `LD_LIBRARY_PATH` to fix `MissingJNIRegistrationError`. Nor should you add JNI metadata to solve a `cannot open shared object file` error. Each layer requires its own configuration.

## 13. Security and Operations for Native Libraries

Native libraries execute with the privileges of the application process and can access memory, files, networks, or devices like ordinary native code. Path management is therefore also part of security:

- Load libraries only from organization-controlled directories; avoid temporary directories or working directories writable by other users.
- Never derive native library filenames or paths directly from external requests.
- Pin library versions and checksums in the build pipeline; verify provenance and licenses.
- Distribute inventoried native dependencies alongside the app; avoid relying on files accidentally present on developer machines.
- Keep write permissions on library directories minimal. The runtime process typically only needs read/load access.
- Update native libraries under the same vulnerability-patching workflow as Java dependencies.
- Avoid leaving multiple versions with the same name across unpredictable search paths; the loader may pick the wrong version.

If the application must support multiple architectures, create separate artifacts per target, such as `linux-amd64-glibc` and `linux-arm64-glibc`. Document the ABI and C/C++ runtime versions required by the library. A file sharing the name `libcodec_jni.so` built for ARM64 cannot substitute for an x86_64 build.

## 14. Hands-On Exercises

### Exercise A — Loading a JNI Library Next to the Executable

Create a `NativeCodec` class with a simple native method. Compile the JNI library for Linux, place `libcodec_jni.so` beside the native executable, and use `System.loadLibrary("codec_jni")`.

**Completion criteria:** both JVM and Native Image invoke the method and return the expected result; logs and library architecture details are recorded.

### Exercise B — Separating the Library into a `lib` Directory

Move the JNI library to `/opt/service/lib`. Configure `java.library.path` for the Java loader and RUNPATH/`LD_LIBRARY_PATH` for the dependency loader. Intentionally omit a dependency to observe the error, then restore it and document the error messages from each loader layer.

**Question:** why does setting `LD_LIBRARY_PATH` not necessarily make `System.loadLibrary` locate the primary JNI library in Native Image?

### Exercise C — Callback from Native Code into Java

Write a Java callback `NativeCallback.onComplete(String)` invoked via JNI. Register the exact type and method in `reachability-metadata.json` or Spring `RuntimeHints.jni()`. Build native, trigger the callback, and verify the output.

**Completion criteria:** the callback works on the native executable and metadata does not expose all members of the package.

### Exercise D — Container Packaging

Build a final image containing the native executable, JNI library, and transitive dependencies. Verify architecture, libc, file permissions, and load paths. Run the container in a production-like environment and invoke an endpoint exercising the JNI task.

**Completion criteria:** the image runs without relying on library files present only on the host or in the builder stage.

## 15. Pre-Release Checklist

- [ ] Identified the call direction: Java calling native methods vs. native code calling back into Java.
- [ ] Chose `System.loadLibrary` or `System.load` appropriately for the scenario.
- [ ] Verified OS filename conventions.
- [ ] JNI library resides in a searchable directory or a valid absolute path.
- [ ] Java library path and OS dynamic-loader path are configured separately.
- [ ] Transitive dependencies are distributed with the product or present in the run image.
- [ ] JNI metadata covers the exact Java types/members accessed by native code.
- [ ] Distinguished JNI metadata from Java serialization metadata.
- [ ] Native executable, JNI libraries, and container share the same OS/architecture/ABI.
- [ ] Tested on both the native executable and the final container image.
- [ ] Verified symbols, dependencies, permissions, and checksums of libraries.
- [ ] Library paths do not allow untrusted users to substitute loaded files.

## References

- [GraalVM Native Image — Java Native Interface (JNI)](https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/JNI/): loading shared libraries, finding libraries beside the executable, JNI wrappers, and metadata for native-to-Java access.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): structure of `reachability-metadata.json`, JNI metadata, tracing agent, and missing-registration diagnostics.
- [Oracle Java SE — System](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html): contracts of `System.load`, `System.loadLibrary`, and `System.mapLibraryName`.
- [Linux man-pages — ld.so(8)](https://www.man7.org/linux/man-pages/man8/ld.so.8.html): shared object search order, `LD_LIBRARY_PATH`, `RPATH`, `RUNPATH`, and `$ORIGIN`.
- [Apple Developer — Run-Path Dependent Libraries](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/100-Articles/RunpathDependentLibraries.html): install names and runpaths for dynamic libraries on macOS.
- [Microsoft Learn — Dynamic-link library search order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order): how the Windows loader locates DLLs and dependencies.

## Conclusion

Managing native libraries in Spring Boot Native Image requires addressing **Java library loading**, **OS dynamic linking**, and **runtime packaging** simultaneously. `System.loadLibrary` takes a logical name and `System.load` takes an absolute path; Native Image checks the executable's directory before the Java library path. Once the primary JNI library is found, the OS loader must still resolve every transitive dependency according to Linux, macOS, or Windows rules. If native code calls back into Java, declare JNI metadata for the exact types/members; this metadata does not replace the library files. Only when the executable, JNI libraries, dependencies, and container are built for the same OS/architecture/ABI and verified in the final image can the application be distributed and operated reliably.

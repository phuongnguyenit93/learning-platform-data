# Native Libraries in JMOD

A native library is a library compiled into machine code for a specific operating system and CPU architecture. Java can invoke native code through JNI (Java Native Interface), intermediate libraries such as JNA, or native access APIs appropriate for the JDK version. In the Java module ecosystem, JMOD can package native libraries alongside Java classes for use by the runtime linking tool.

This article focuses on the role of native libraries in JMOD: how to prepare a native library, include it in a JMOD using `jmod --libs`, inspect and extract the archive, and link the module into a runtime image using `jlink`. It is important to distinguish between packaging a native file and Java's ability to load and invoke that library: JMOD only stores the artifact, while the Java code, native ABI, load path, and runtime platform must all be compatible.

## 1. What is a native library?

A native library is code compiled for a target OS/CPU. Some common formats include:

| Platform | Common filename |
|---|---|
| Windows | `acme.dll` |
| Linux | `libacme.so` |
| macOS | `libacme.dylib` |

Unlike `.class` files that contain Java bytecode, a native library contains machine code that the operating system loads into the process. The library can provide image processing, cryptography, device communication, audio processing, system library calls, or reuse existing C/C++ code.

A native library is commonly referred to as a shared library or dynamic library. Static files such as `.a` on Linux/macOS or `.lib` static libraries on Windows are typically linked into a shared library during the native build process; the JVM does not load such static archive files directly via `System.loadLibrary`.

A native library depends on:

- The operating system and binary format.
- The CPU architecture, such as x86-64 or AArch64.
- The ABI and calling convention of the compiler/native toolchain.
- Other system libraries or shared libraries it links against.
- The JNI/native API version it uses.

Therefore, an `.so` file built for Linux x86-64 cannot be used in place of a `.dll` on Windows or an AArch64 binary. Simply renaming the file cannot convert a binary between platforms.

## 2. Where does JMOD store native libraries?

JMOD is an archive format designed for packaging Java modules during development and runtime linking. It can contain classes, resources, and additional components used to build a runtime image.

A JMOD typically has sections such as:

| Section in JMOD | Contents |
|---|---|
| `classes/` | Class files, module descriptor, and module resources. |
| `lib/` | Native libraries provided for the module. |
| `bin/` | Native commands bundled with the module. |
| `include/` | Header files, typically used for native integration. |
| `conf/` | Configuration files. |
| `legal/` | License notices and legal content. |
| `man/` | Command manual pages. |

The `jmod create --libs` option specifies the directory containing native libraries to be placed into the `lib/` section of the JMOD. The `--header-files` option is for header files; `--cmds` is for native commands. You should not mistakenly place headers or executables into the native library directory and expect them to be treated as the same type of content.

An example JMOD might contain:

~~~text
com.acme.nativebridge.jmod
├── classes/
│   ├── module-info.class
│   └── com/acme/nativebridge/NativeBridge.class
└── lib/
    └── libacme.so
~~~

Actual entry names and paths depend on the input contents and how the JMOD is created. Use `jmod list` to inspect a specific archive rather than assuming every JMOD has the same set of entries.

## 3. How does JMOD differ from JAR?

JAR is a common format for packaging Java classes and resources, and can be used on the classpath or module path when running an application. JMOD is designed for module development and runtime image linking, and also supports additional sections such as native libraries, commands, headers, and legal notices.

| Criterion | Modular JAR | JMOD |
|---|---|---|
| Contains classes and resources | Yes | Yes |
| Contains module descriptor | Can include `module-info.class` | Can include in the `classes` section |
| Contains native libraries in a dedicated section | No equivalent dedicated section | Has a `lib` section |
| Used directly on the runtime module path | Yes | Not its intended use |
| Input for `jlink` | Possible | Yes |
| Packages headers, native commands, and legal notices in sections | No equivalent JMOD section structure | Yes |

Key point: A JMOD is not a JAR file that can be executed with `java -jar`. JMOD is used as input for tools such as `jlink`. After linking, the application runs using the Java launcher inside the generated runtime image.

If you only need to distribute a pure Java library or a standard Java application, a modular JAR is usually more appropriate. JMOD makes sense when you need to package components for building a runtime image, especially when the module includes native libraries.

## 4. Calling a native library from Java using JNI

JNI allows Java methods to be implemented in native code. A method declared with the `native` keyword has no Java body; the JVM looks up the corresponding implementation in a loaded native library.

Example module:

~~~text
native-module/
├── src/
│   ├── module-info.java
│   └── com/acme/nativebridge/NativeBridge.java
├── native/
│   ├── src/
│   │   └── acme.c
│   └── linux-x86_64/
└── build/
~~~

File `src/module-info.java`:

~~~java
module com.acme.nativebridge {
    exports com.acme.nativebridge;
}
~~~

File `src/com/acme/nativebridge/NativeBridge.java`:

~~~java
package com.acme.nativebridge;

public final class NativeBridge {
    static {
        System.loadLibrary("acme");
    }

    private NativeBridge() {
    }

    public static native String platformName();

    public static void main(String[] args) {
        System.out.println(platformName());
    }
}
~~~

The call `System.loadLibrary("acme")` instructs the JVM to load the library by its logical name. On common platforms, this logical name is mapped to the appropriate filename, such as `libacme.so` on Linux, `libacme.dylib` on macOS, or `acme.dll` on Windows. Do not pass prefixes or suffixes in the argument to `loadLibrary`.

If you already have the absolute path to the native file, the `System.load("/absolute/path/to/library")` API can be used instead. `System.load` requires an absolute path; `System.loadLibrary` accepts a logical library name.

Declaring a `native` method does not automatically generate an implementation. You must compile the C/C++ code into a shared library containing the corresponding JNI symbols and ensure the binary is compatible with the JVM.

## 5. Generating JNI headers and native implementation

`javac -h` generates C/C++ headers from declared native methods. From the project root directory, compile the module and generate the header:

~~~bash
mkdir -p build/classes build/include

javac -h build/include -d build/classes src/module-info.java src/com/acme/nativebridge/NativeBridge.java
~~~

The generated header is named based on the package and class, for example:

~~~text
build/include/com_acme_nativebridge_NativeBridge.h
~~~

Create `native/src/acme.c`:

~~~c
#include "com_acme_nativebridge_NativeBridge.h"

JNIEXPORT jstring JNICALL
Java_com_acme_nativebridge_NativeBridge_platformName(JNIEnv *env, jclass type) {
    return (*env)->NewStringUTF(env, "native library loaded");
}
~~~

The JNI function name must follow JNI's package, class, and method mapping rules. When method names are overloaded or contain special characters, the symbol naming rules can be more complex; use the header generated by `javac -h` instead of guessing the signature manually.

On Linux x86-64, an illustrative command to compile the shared library:

~~~bash
mkdir -p native/linux-x86_64

cc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -Ibuild/include -o native/linux-x86_64/libacme.so native/src/acme.c
~~~

The command above assumes a compatible C compiler is installed, `JAVA_HOME` points to the active JDK, and the source/header paths exist. Native compiler flags vary by toolchain. On Windows, you need a compiler that produces a DLL and platform headers in `include/win32`; on macOS, you need to build a suitable dynamic library and use headers in `include/darwin`.

`jmod` does not compile C/C++ and does not produce DLL/SO/DYLIB files. The native build must be completed beforehand; `jmod` only packages existing binaries.

## 6. Creating a JMOD and placing the library in the lib section

Once you have:

- `build/classes/module-info.class` and the Java classes.
- `native/linux-x86_64/libacme.so` as the compiled shared library.

You can create the JMOD:

~~~bash
mkdir -p build

jmod create --class-path build/classes --libs native/linux-x86_64 --module-version 1.0.0 --target-platform linux-x86_64 build/com.acme.nativebridge.jmod
~~~

Meaning of the options:

- `create` creates a new JMOD archive.
- `--class-path build/classes` takes the module descriptor, classes, and resources from the compiled directory.
- `--libs native/linux-x86_64` adds the native library to the `lib/` section.
- `--module-version 1.0.0` records the module version.
- `--target-platform linux-x86_64` records the target platform for the JMOD.
- The final argument is the output JMOD path.

The `build/classes` directory must contain `module-info.class` and the appropriate package hierarchy. If the module descriptor is missing, the archive may not represent the module that `jlink` expects.

`--target-platform` only records target platform metadata; it does not convert or recompile native binaries. Platform names should be consistent across the project's build pipeline and must match the packaged binary. For native code, you typically need to create a separate JMOD for each supported OS/architecture.

If the module needs to provide C/C++ headers for integrators, you can use `--header-files`. If there are bundled native commands, use `--cmds`. These content types have their own dedicated sections and do not replace `--libs`.

## 7. Listing and describing native libraries in a JMOD

After creating the archive, inspect the entry list:

~~~bash
jmod list build/com.acme.nativebridge.jmod
~~~

You will see entries under the classes and lib sections. In the example above, the native library entry will be located under the `lib/` section.

Use `describe` to view module information:

~~~bash
jmod describe build/com.acme.nativebridge.jmod
~~~

This command displays module details such as name, version, requires/exports, and target platform if recorded. It does not validate the full correctness of the native code or guarantee that the library can be loaded successfully.

If you need to inspect the archive contents on the filesystem, use `extract`:

~~~bash
jmod extract --dir build/extracted build/com.acme.nativebridge.jmod
~~~

After extracting, you can inspect the files:

~~~text
build/extracted/
├── classes/
│   ├── module-info.class
│   └── com/acme/nativebridge/NativeBridge.class
└── lib/
    └── libacme.so
~~~

On PowerShell, you can list the extracted directory contents with `Get-ChildItem -Recurse build/extracted`. On Linux/macOS, use `find build/extracted -type f`.

Extracting a JMOD only helps inspect or retrieve its entries. It does not install the native library into the operating system, register the library with the JVM, or create a runtime image.

## 8. Linking a JMOD into a runtime image with jlink

A JMOD containing native libraries is designed to be consumed by the runtime linking tool. `jlink` reads the input modules, resolves module dependencies, and builds a custom runtime image.

For example, on Linux/macOS, if the current JDK has a `jmods` directory and the application JMOD is in `build`:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:build" --add-modules com.acme.nativebridge --output build/runtime
~~~

On Windows, the separator between module path entries is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;build" --add-modules com.acme.nativebridge --output build/runtime
~~~

`--module-path` specifies where to find JMOD/JAR modules. `--add-modules` selects the root modules to include in the image; dependent modules are resolved via the module graph. `--output` specifies the runtime image directory.

Native libraries belonging to selected modules can be placed into the runtime image according to the platform layout generated by the JDK. Check the image's `lib` directory and the `java.library.path` property of the new runtime to confirm where libraries are searched on the target platform.

Run the application using the runtime image:

~~~bash
build/runtime/bin/java -m com.acme.nativebridge/com.acme.nativebridge.NativeBridge
~~~

Expected output if the native library is linked, located, and loaded successfully:

~~~text
native library loaded
~~~

On Windows, the launcher is at `build/runtime/bin/java.exe`. You must run the runtime image on a platform compatible with the packaged JMOD and native binary.

## 9. JMOD does not replace the native library loading mechanism

There are three distinct steps:

1. **Packaging:** `jmod --libs` places the native binary into the JMOD.
2. **Runtime linking:** `jlink` consumes the JMOD when building the runtime image and includes the necessary components in the image.
3. **Runtime loading:** The JVM loads the library when Java code calls `System.loadLibrary` or `System.load`.

Merely creating a JMOD without including the module in a runtime image does not automatically make the library appear on the native library search path of an arbitrary JVM. Nor can a JMOD be used as a native library directory by adding it directly to `java.library.path`.

`System.loadLibrary` looks up libraries according to JVM and platform native library rules. The `java.library.path` property represents the directories the JVM searches when loading libraries by name. In addition, a shared library may depend on other native libraries; the operating system's dynamic loader must be able to locate those dependencies as well.

When you need to determine the actual search paths at runtime, the application can print:

~~~java
System.out.println(System.getProperty("java.library.path"));
~~~

This property helps diagnose where libraries are being searched. It does not prove that a native file has the right architecture, ABI, or all required dependencies.

## 10. Native libraries and target platforms

A JMOD with a native library is tied to a specific platform. For example:

| JMOD | Native binary | Platform |
|---|---|---|
| com.acme.nativebridge-linux-x64.jmod | libacme.so | Linux x86-64 |
| com.acme.nativebridge-linux-aarch64.jmod | libacme.so | Linux AArch64 |
| com.acme.nativebridge-windows-x64.jmod | acme.dll | Windows x86-64 |
| com.acme.nativebridge-macos-aarch64.jmod | libacme.dylib | macOS AArch64 |

The JMOD filenames in the table are merely a project naming convention. `--target-platform` should be set to match the platform that the native binary actually supports.

A cross-platform release pipeline typically produces separate artifacts:

- Compile the Java module.
- Compile the native library using the toolchain for each OS/architecture.
- Create the JMOD corresponding to that native binary.
- Link the runtime image in a compatible environment.
- Run library-loading tests and functional tests on each platform.

You should not package a single native binary and label it as supporting multiple operating systems. Cross-compilation, if used, must be supported by the native toolchain and tested on the actual target platform.

## 11. Differences between header files, native commands, and native libraries

JMOD supports multiple types of native content, but they serve different purposes:

| Content | jmod option | Role |
|---|---|---|
| JNI shared library | `--libs` | `.dll`, `.so`, or `.dylib` files that the JVM can load. |
| C/C++ headers | `--header-files` | Headers for compilers or native developers to use during integration. |
| Native executable/command | `--cmds` | OS commands bundled with the module. |

For example, headers generated by `javac -h` can be included in the JMOD if the module needs to distribute headers for downstream native builds:

~~~bash
jmod create --class-path build/classes --libs native/linux-x86_64 --header-files build/include --module-version 1.0.0 --target-platform linux-x86_64 build/com.acme.nativebridge.jmod
~~~

Header files are not shared libraries and cannot be loaded with `System.loadLibrary`. Similarly, a native command is a standalone executable, not a JNI library.

## 12. Common errors when packaging and loading native libraries

| Error or symptom | Common cause | How to check and resolve |
|---|---|---|
| `UnsatisfiedLinkError: no acme in java.library.path` | The JVM cannot find the library file by its logical name. | Check `System.loadLibrary`, `java.library.path`, and the runtime image directory. |
| `UnsatisfiedLinkError` reporting a missing JNI method | The native binary lacks the JNI symbol with the exact name/signature or was built from an outdated header. | Regenerate headers with `javac -h`, verify symbols, and rebuild the library. |
| `wrong ELF class` or binary format error | The library's architecture/bitness does not match the JVM or OS. | Check the architecture of the native binary and JDK; build for the right target. |
| DLL/SO found but fails to load | Missing dependent shared library or incompatible ABI. | Inspect dependencies with OS tools and provide the required native dependencies. |
| JMOD has the file in `lib/`, but the application still cannot find it | The JMOD was not linked into the runtime image, the module was not selected, or the native path does not include that location. | Check the `jlink` command, module path, runtime image, and `java.library.path`. |
| `jlink` reports module not found | The JMOD is not on the module path, or the module descriptor is invalid/named differently. | Use `jmod describe` and check `--module-path`. |
| JMOD created successfully but fails to link on another machine | The JMOD/native library is for a different target platform or the binary is incompatible. | Produce per-platform artifacts and use a matching JDK/linker. |
| Works on the build machine but fails on the user's machine | The build machine has pre-installed native dependencies that the distributed image does not contain. | Audit native dependencies and package/install them according to product policy. |

Some native errors only surface when the JVM actually loads the library or invokes a method. A successful `jmod list` only proves the archive can be read; it does not verify symbols, ABI, or native code logic.

## 13. Safety and operations for native libraries

Native code runs in the same process as the JVM and can access memory, OS resources, or low-level system APIs. A bug in native code can corrupt memory, hang the process, or crash the JVM instead of throwing a standard Java exception.

Principles to follow:

- Only package native binaries from controlled sources and build pipelines.
- Verify artifact checksums/signatures according to your release process.
- Build separately for each supported OS, architecture, and ABI.
- Check transitive native dependencies, not just the primary JNI file.
- Test on the final runtime image, not only on a development machine with many pre-installed libraries.
- Manage native memory lifecycles and handles carefully; do not assume the garbage collector frees all native resources.
- Record the compiler version, native SDK, and target platform so artifacts can be reproduced.

JMOD does not sandbox native libraries and does not make native code safer. Placing a file into a module is purely for organizing and packaging artifacts; the execution privileges and risks of native code remain.

## 14. Checklist for a JMOD workflow with native libraries

Before releasing a module with native code, verify:

1. The Java module has `module-info.class` and the required classes/resources.
2. Native methods have accurate Java declarations and JNI headers are generated from the matching source version.
3. The native library is built as a shared library in the correct format for the target.
4. `jmod create --libs` points to the directory containing the built binary.
5. `--target-platform` accurately reflects the target OS/CPU.
6. `jmod list` shows the native library under the `lib/` section.
7. `jmod describe` displays the expected module and metadata.
8. `jlink` selects the module and builds the runtime image from the proper module path.
9. The runtime image contains the native library in the appropriate layout; `java.library.path` can locate it.
10. The application can actually invoke the JNI method on the target machine or environment.
11. All dependent shared libraries can be located by the dynamic loader.
12. CI runs tests separately for each supported platform.

Native libraries in JMOD provide a way to package native code alongside a module for building runtime images. `jmod --libs` places the shared library into the archive; `jlink` links the module into the runtime image; and `System.loadLibrary` or `System.load` is the step where the JVM loads the library at runtime. Understanding these three steps and controlling the target platform, ABI, dependencies, and load paths enables Java applications to integrate native code in a testable and reproducible manner.

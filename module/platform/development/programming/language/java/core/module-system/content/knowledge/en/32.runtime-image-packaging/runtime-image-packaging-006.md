# jmod create and Module Native Commands

JMOD is a JDK archive format used to package module contents for linking a runtime image. In addition to Java classes and the module descriptor, a JMOD can contain native commands, native libraries, configuration files, headers, legal notices, and man pages.

The `jmod create` command creates a `.jmod` file from prepared inputs. When using `jlink` to build a runtime image, the appropriate contents inside the JMOD are placed into the image. This topic is especially important when a Java module needs to distribute a native program that can be invoked from a shell or from `ProcessBuilder`.

Distinguish two types of native artifacts:

- A **native command** is a standalone executable, such as `acme-check` or `acme-check.exe`. Package it with `jmod create --cmds`; when linking the module, the command is placed in the `bin` directory of the runtime image.
- A **native library** is a library used from Java code via JNI or a corresponding native mechanism, such as `libacme.so`, `acme.dll`, or `libacme.dylib`. Package it with `--libs`, not `--cmds`.

## 1. Structure of a JMOD

A JMOD can contain the following sections:

| Section | Contents | jmod create Option |
|---|---|---|
| `classes/` | Java classes, resources, and `module-info.class` | `--class-path` |
| `bin/` | Native command executables | `--cmds` |
| `conf/` | Module configuration files | `--config` |
| `include/` | Native header files | `--header-files` |
| `legal/` | Licenses and legal notices | `--legal-notices` |
| `lib/` | Native libraries | `--libs` |
| `man/` | Man pages | `--man-pages` |

Not every module needs all sections. A pure Java module might only need `classes/`; a module providing a native command will also have `bin/`.

The module descriptor remains an essential part of a JMOD. For a module used as input to `jlink`, the input classes directory must contain a valid `module-info.class` so the tool can determine the module name and dependencies.

## 2. jmod create Syntax

General syntax:

~~~bash
jmod create [OPTIONS] <jmod-file>
~~~

Commonly used options:

| Option | Meaning |
|---|---|
| `--class-path <path>` | Directory containing module classes and resources |
| `--cmds <path>` | Directory containing native command executables |
| `--libs <path>` | Directory containing native libraries |
| `--config <path>` | Directory containing configuration files |
| `--header-files <path>` | Directory containing headers used for native integration |
| `--legal-notices <path>` | Directory containing license/legal notices |
| `--man-pages <path>` | Directory containing man pages |
| `--main-class <class>` | Main class of the module, if the module has a Java entry point |
| `--module-version <version>` | Version recorded in module metadata |
| `--target-platform <target-platform>` | Target platform for which the JMOD is created |

Example creating a JMOD with Java classes only:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

Example adding a native command:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --cmds native/bin \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

The JMOD filename usually reflects the module name, but the official module name resides inside `module-info.class`. Renaming the file does not change the module name inside the descriptor.

## 3. Preparing a Java Module for Packaging

Example module named `com.acme.tools`:

~~~text
project/
├── src/
│   └── com.acme.tools/
│       ├── module-info.java
│       └── com/acme/tools/ToolInfo.java
├── native/
│   ├── acme-check.c
│   └── bin/
└── build/
    ├── classes/
    └── jmods/
~~~

Descriptor:

~~~java
module com.acme.tools {
    exports com.acme.tools;
}
~~~

Java class:

~~~java
package com.acme.tools;

public class ToolInfo {
    public static String version() {
        return "1.0.0";
    }
}
~~~

Compile the module:

~~~bash
javac \
  -d build/classes/com.acme.tools \
  src/com.acme.tools/module-info.java \
  src/com.acme.tools/com/acme/tools/ToolInfo.java
~~~

After compiling, the `build/classes/com.acme.tools` directory should have the structure:

~~~text
build/classes/com.acme.tools/
├── module-info.class
└── com/
    └── acme/
        └── tools/
            └── ToolInfo.class
~~~

This is the input for `--class-path`. Do not put `.java` source files into a JMOD in place of compiled classes.

## 4. Preparing a Native Command

A native command is an executable program specific to the operating system. Simple C example:

~~~c
#include <stdio.h>

int main(void) {
    puts("acme-check from the linked runtime image");
    return 0;
}
~~~

Save the file as `native/acme-check.c`.

On Linux or macOS, use a C compiler appropriate for the platform:

~~~bash
mkdir -p native/bin
cc -O2 -o native/bin/acme-check native/acme-check.c
~~~

Verify the executable file:

~~~bash
file native/bin/acme-check
./native/bin/acme-check
~~~

On Windows with Microsoft C/C++ Build Tools, you can build the corresponding executable:

~~~powershell
New-Item -ItemType Directory -Force native/bin
cl /O2 /Fe:native/bin/acme-check.exe native/acme-check.c
native/bin/acme-check.exe
~~~

The directory passed to `--cmds` contains **compiled binaries**, not C source files. The command filename will be preserved in the runtime image; on Windows it typically has the `.exe` extension.

The native command must match the operating system and CPU architecture of the target runtime image. A Linux binary cannot run in a Windows runtime image merely because it was packaged in a JMOD.

## 5. Packaging the Module and Native Command with jmod create

Create the directory for JMODs:

~~~bash
mkdir -p build/jmods
~~~

Create the JMOD:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --cmds native/bin \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

In the command above:

- `--class-path` takes `module-info.class`, Java classes, and module resources.
- `--cmds` takes native executables in `native/bin`.
- `--module-version` records the version in module metadata.
- The final argument is the path of the JMOD file to create.

If the module also has native libraries, configs, headers, licenses, or man pages, you can add the corresponding options:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --cmds native/bin \
  --libs native/lib \
  --config config \
  --header-files native/include \
  --legal-notices legal \
  --man-pages man \
  --module-version 1.0.0 \
  build/jmods/com.acme.tools.jmod
~~~

Pass only the directories that are genuinely needed. Input directories must contain the exact artifact types described by the options.

If packaging binaries for a specific platform, you can attach platform metadata with `--target-platform`. The value must follow a target platform identifier supported by the JDK/toolchain in use. Keep the JDK, architecture, and operating system consistent when creating JMODs and runtime images.

## 6. Distinguishing --cmds, --libs, and --header-files

These three options are easy to confuse because all relate to native code, but their purposes differ.

### --cmds: Executables Invoked as Commands

Example:

~~~text
native/bin/
└── acme-check
~~~

After linking the module, the command is placed in:

~~~text
runtime/
└── bin/
    ├── java
    ├── jlink
    └── acme-check
~~~

It can be run directly from the shell:

~~~bash
runtime/bin/acme-check
~~~

On Windows:

~~~powershell
runtime/bin/acme-check.exe
~~~

This command can be a standalone utility and does not necessarily have to be invoked by a Java class. Nor does it become the module's main class just because it is packaged in the JMOD.

### --libs: Native Libraries Loaded by Java

Example:

~~~text
native/lib/
├── libacme_native.so
├── libacme_native.dylib
└── acme_native.dll
~~~

Actual names and formats depend on the operating system. A Java class can call a native library via JNI, for example:

~~~java
public final class NativeBridge {
    static {
        System.loadLibrary("acme_native");
    }

    public static native int calculate(int value);
}
~~~

The library is packaged with:

~~~bash
jmod create \
  --class-path build/classes/com.acme.tools \
  --libs native/lib \
  build/jmods/com.acme.tools.jmod
~~~

`System.loadLibrary` loads the native library according to the JVM's library path search mechanism. Packaging the library into a JMOD ensures it is included in the runtime image when the module is linked; you still need to verify library naming, architecture, ABI, and how the JVM locates the library in the image.

### --header-files: Headers Used for Native Integration

C/C++ headers can be generated by `javac -h` when a Java class declares native methods:

~~~bash
javac -h native/include \
  -d build/classes/com.acme.tools \
  src/com.acme.tools/com/acme/tools/NativeBridge.java
~~~

The `native/include` directory can be packaged with `--header-files` to distribute headers alongside the module. Headers are neither executables nor native libraries; they support compiling native code compatible with the Java API/JNI.

## 7. Linking JMODs into a Runtime Image with jlink

JMOD is an input for the linker tool. The Java launcher does not load a `.jmod` file directly as a runtime module. Use `jlink` to create a runtime image containing the required modules.

On Linux/macOS:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/jmods" \
  --add-modules com.acme.tools \
  --output runtime
~~~

On Windows PowerShell:

~~~powershell
$jmods = Join-Path $env:JAVA_HOME "jmods"
jlink --module-path "$jmods;build/jmods" --add-modules com.acme.tools --output runtime
~~~

`--module-path` contains both JDK JMODs and application JMODs. `--add-modules` selects the modules to include in the image; dependencies are resolved from descriptors. `--output` specifies the runtime image directory.

After linking succeeds, run the native command in the image:

~~~bash
runtime/bin/acme-check
~~~

On Windows:

~~~powershell
runtime/bin/acme-check.exe
~~~

Verify the modules in the image:

~~~bash
runtime/bin/java --list-modules
runtime/bin/java --describe-module com.acme.tools
~~~

If the JMOD contains a native library, verify that the library was also linked into the image and test loading it from a Java program in that runtime.

## 8. Inspecting JMOD Contents

Use `jmod list` to view entries:

~~~bash
jmod list build/jmods/com.acme.tools.jmod
~~~

You may see entries similar to:

~~~text
classes/module-info.class
classes/com/acme/tools/ToolInfo.class
bin/acme-check
~~~

Use `jmod describe` to view module metadata:

~~~bash
jmod describe build/jmods/com.acme.tools.jmod
~~~

The output can show the module name, version, exports, requires, and target platform if declared in metadata. `jmod describe` focuses on the descriptor; use `jmod list` to inspect packaged files.

To extract the archive to inspect each section:

~~~bash
jmod extract --dir extracted build/jmods/com.acme.tools.jmod
~~~

Then inspect:

~~~text
extracted/
├── classes/
├── bin/
├── lib/
├── conf/
├── include/
├── legal/
└── man/
~~~

Only sections that have content appear. Extracting is useful to confirm the binary command was placed in the right section before creating the runtime image.

## 9. Native Commands vs. jlink --launcher

Do not confuse a native command packaged in a JMOD with a launcher generated by `jlink --launcher`.

- `jmod create --cmds` packages **an existing native executable** into the JMOD. This can be a standalone C/C++ tool.
- `jlink --launcher` creates a launcher to start a Java module and its main class.

Example creating a Java launcher:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/jmods" \
  --add-modules com.acme.tools \
  --launcher acme-java=com.acme.tools/com.acme.tools.ToolMain \
  --output runtime
~~~

The command above creates the launcher `runtime/bin/acme-java` to run the Java main class. It does not replace a native command packaged via `--cmds`; both kinds of commands can coexist as long as their names do not collide.

If a module only provides a native command without a Java main class, there is no need to specify `--launcher` for that module.

## 10. Common Errors

**jmod create reports that the module descriptor cannot be found.** Check whether `--class-path` points to the root directory containing `module-info.class`. Do not mistakenly point to a subpackage or source directory.

**JMOD was created, but the native command is missing after jlink.** Check that the command actually resides in the directory passed to `--cmds`, `jmod list` shows the `bin/...` entry, and the module containing the JMOD was selected in `--add-modules`.

**Command is present in the runtime but fails to execute.** Check the executable bit on Unix, binary format, CPU architecture, dynamic dependencies, and required OS libraries. On Windows, verify the `.exe` file and compiler runtime dependencies.

**Used --libs but expected the command to appear in bin.** `--libs` packages native libraries; command executables must be included using `--cmds`.

**Used --cmds to package a JNI library.** A JNI library is not a standalone command. Put it in `--libs`, then verify `System.loadLibrary` and native library loading configuration.

**JMOD works on the build machine but fails on the target machine.** Native content depends on OS, CPU architecture, and ABI. Build JMODs/runtime images for the exact target platform; do not copy a Linux binary into a Windows image or vice versa.

**Java launcher reports module not found when pointing directly to a JMOD.** JMODs are for link time. Use `jlink` to create a runtime image, then run the application from that image.

**Command name collision across multiple modules.** Multiple native commands linked into the same runtime image can collide on filenames in `bin`. Give commands clear namespaced names, such as `acme-db-check`, and avoid having two modules own the same executable name.

## 11. Recommended Packaging Workflow

1. Compile the Java module to produce `module-info.class` and classes/resources.
2. Build the native command separately for the exact target OS and architecture.
3. Categorize native artifacts: executables in `--cmds`, JNI/shared libraries in `--libs`, headers in `--header-files`.
4. Create the JMOD with `jmod create` and pass only the required sections.
5. Use `jmod list` to confirm entries, especially `bin/<command>` and `lib/<library>`.
6. Use `jmod describe` to confirm the module name, version, and descriptor.
7. Use `jlink` to create a runtime image from the JMOD along with JDK JMODs.
8. Run the native command from `runtime/bin` and test the Java application on the same runtime image.
9. Run tests on the exact operating system and architecture to be deployed.

## 12. Practice

1. Create module `com.acme.tools` with `module-info.java` and class `ToolInfo`.
2. Compile the module into `build/classes/com.acme.tools`.
3. Write the C program `acme-check.c` and compile it into an executable in `native/bin`.
4. Use `jmod create --class-path ... --cmds ...` to create `com.acme.tools.jmod`.
5. Use `jmod list` to verify the presence of `classes/module-info.class` and `bin/acme-check`.
6. Use `jlink` to create a runtime image containing only the required modules.
7. Run `runtime/bin/acme-check` and `runtime/bin/java --describe-module com.acme.tools`.
8. If you have a JNI library, create an additional native library, package it with `--libs`, write a Java bridge, and test `System.loadLibrary` inside the runtime image.
9. Try building a JMOD for a different target platform using the corresponding toolchain; note why native binaries cannot be used arbitrarily across operating systems.

When packaging native content for a module, distinguish executables, shared libraries, and headers. `--cmds` places native commands in `bin` of the runtime image; `--libs` places native libraries into the image for Java to load; `--header-files` distributes headers for native integration. JMOD bundles these components with the descriptor and Java classes, while `jlink` creates the final deployable runtime image.

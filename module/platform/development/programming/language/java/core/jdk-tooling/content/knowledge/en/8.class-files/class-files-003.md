# Java class file magic and version

After compilation, each Java class is stored as a **class file** with a binary structure defined by the JVM specification. At the beginning of every class file is a fixed identifier called the **magic number** `CAFEBABE`. Immediately following it are two version fields: `minor_version` and `major_version`.

The two version fields indicate the class file format produced by the compiler. The JVM uses them to decide whether the class file is in a format supported by the runtime. If an application is compiled with a JDK newer than the running runtime, a common error is `UnsupportedClassVersionError`.

## 1. Magic number CAFEBABE

The first four bytes of a valid class file are:

~~~text
CA FE BA BE
~~~

This is the hexadecimal value of the magic number `0xCAFEBABE`. It is the binary identifier of a Java class file, not text code or a Java version.

When the JVM or an analysis tool reads a class file, the magic number helps identify whether the data is in valid class file format. If the first four bytes do not match, the file may not be a class file, may be corrupted, or you may be reading the wrong data format. Renaming a file's extension to .class does not turn its contents into a valid class file.

The magic number does not indicate which vendor's JDK compiled the class. To know the format version, you need to read the minor and major fields immediately after the four magic bytes.

## 2. Header structure and version location

The beginning of a class file is organized in the following order:

| Byte offset | Size | Field | Meaning |
|---:|---:|---|---|
| 0–3 | 4 bytes | `magic` | Magic number `0xCAFEBABE` |
| 4–5 | 2 bytes | `minor_version` | Minor version |
| 6–7 | 2 bytes | `major_version` | Major version |
| 8 onward | Variable | `constant_pool_count` and constant pool | Start of the next structure |

Multi-byte values are stored in **big-endian** order: the most significant byte comes first. Therefore, the two bytes `00 3D` represent the hexadecimal number `0x003D`, which is decimal 61.

After the header, a class file also contains the constant pool, access flags, class and superclass names, interface list, fields, methods, and attributes. Because the version is located in the header, it can be inspected without parsing the entire bytecode.

## 3. Mapping major version to Java version

Each Java SE generation has a corresponding major class-file version. Common milestones:

| Java SE | Major version | Hexadecimal |
|---:|---:|---:|
| 1.0.2–1.1 | 45 | `0x002D` |
| 1.2 | 46 | `0x002E` |
| 1.3 | 47 | `0x002F` |
| 1.4 | 48 | `0x0030` |
| 5 | 49 | `0x0031` |
| 6 | 50 | `0x0032` |
| 7 | 51 | `0x0033` |
| 8 | 52 | `0x0034` |
| 9 | 53 | `0x0035` |
| 10 | 54 | `0x0036` |
| 11 | 55 | `0x0037` |
| 12 | 56 | `0x0038` |
| 13 | 57 | `0x0039` |
| 14 | 58 | `0x003A` |
| 15 | 59 | `0x003B` |
| 16 | 60 | `0x003C` |
| 17 | 61 | `0x003D` |
| 18 | 62 | `0x003E` |
| 19 | 63 | `0x003F` |
| 20 | 64 | `0x0040` |
| 21 | 65 | `0x0041` |
| 22 | 66 | `0x0042` |
| 23 | 67 | `0x0043` |
| 24 | 68 | `0x0044` |
| 25 | 69 | `0x0045` |
| 26 | 70 | `0x0046` |

From Java 1.2 onward, the major version increases by 1 with each Java SE release. For modern releases, you can calculate it quickly: `major = Java feature version + 44`. For example, Java 17 has major 61; Java 21 has major 65; Java 26 has major 70.

For very old class files with major 45, the minor version may have historical non-zero values. You should not apply the minor-equals-0 rule to every historical class file format.

## 4. Minor version and preview features

For modern Java class files that do not use preview features, the minor version is typically `0`. For example, a standard Java 17 class file has version `61.0`.

Since the preview feature mechanism was introduced in Java 12, class files compiled with preview features enabled carry minor version `65535` (hexadecimal `0xFFFF`). This value signals that the class file depends on preview features of that exact Java release.

To compile and run code that uses preview features, preview must be enabled in both steps and the same corresponding Java release must be used. For example, with JDK 21:

~~~sh
javac --release 21 --enable-preview -d out src/com/example/PreviewExample.java
java --enable-preview -cp out com.example.PreviewExample
~~~

A Java 21 preview class file has major version 65 and minor version 65535. A Java 21 JVM must be launched with `--enable-preview` to load that class. A JVM of a different Java release cannot use that preview class file as a normal class file, even if the major version might otherwise be format-compatible.

`--enable-preview` must be paired with `--release` or `-source` set to the compiler's current version. You cannot use a JDK 26 compiler to produce a Java 21 preview class file by passing `--release 21 --enable-preview`; preview only applies to the compiler's own release.

## 5. Example: checking version with javac and javap

Create `src/com/example/VersionInfo.java`:

~~~java
package com.example;

public class VersionInfo {
    public static void main(String[] args) {
        System.out.println("class-file-check");
    }
}
~~~

Compile targeting Java 17:

~~~sh
mkdir -p out
javac --release 17 -d out src/com/example/VersionInfo.java
~~~

Run with Java 17 or a newer runtime:

~~~sh
java -cp out com.example.VersionInfo
~~~

Stdout output:

~~~text
class-file-check
~~~

Use `javap -verbose` to inspect the class file version information:

~~~sh
javap -verbose -classpath out com.example.VersionInfo
~~~

Near the top of the output, look for two lines similar to:

~~~text
minor version: 0
major version: 61
~~~

Because the compiler used `--release 17`, the regular class file has major 61 and minor 0. This output reflects the version of the actual class file, not merely the version of the installed `javac` command.

You can run `javap -verbose` with a fully qualified class name or pass the path to a class file. When multiple classes with the same name exist across different directories or JARs, specify the exact classpath so you do not inspect the wrong copy.

## 6. Reading the first eight bytes with a hex tool

On Linux or macOS, if `xxd` is available, you can read the first eight bytes:

~~~sh
xxd -g 1 -l 8 out/com/example/VersionInfo.class
~~~

For a standard Java 17 class file, the leading bytes are:

~~~text
ca fe ba be 00 00 00 3d
~~~

Interpretation:

- `ca fe ba be`: magic number.
- `00 00`: minor version equal to 0.
- `00 3d`: major version equal to 61, i.e. Java 17.

On Windows PowerShell, you can read the bytes directly without installing a hex utility:

~~~powershell
$bytes = [System.IO.File]::ReadAllBytes('out\com\example\VersionInfo.class')
$bytes[0..7] | ForEach-Object { $_.ToString('X2') }
~~~

The eight printed values should be `CA FE BA BE 00 00 00 3D` in order for a regular Java 17 class file. If they differ, check the file path, compiler target, and whether you are reading the right artifact.

Hex inspection is useful when you need to verify a file directly, such as in build scripts, artifact verification pipelines, or when `javap` is unavailable. However, `javap -verbose` is usually easier to read because it decodes the version fields instead of requiring the reader to convert hexadecimal numbers manually.

## 7. Why the class file version is not necessarily equal to the installed JDK version

The JDK used for compilation can be newer than the minimum runtime the application supports. For example, JDK 26 can compile source targeting Java 17 with:

~~~sh
javac --release 17 -d out src/com/example/VersionInfo.java
~~~

The resulting class file has major version 61 instead of 70. Thus, the JDK version running the compiler and the output class file version are two separate concepts.

`--release` is recommended when compatibility with an older Java release is needed. It sets the language level, target bytecode, and corresponding platform API set. Using `-source` and `-target` alone does not guarantee that source code avoids calling APIs introduced only in newer JDKs.

For example, a newer compiler may accept an API introduced in Java 21 even if you only set `-target 17`. The class file has major 61, yet when run on Java 17 it can still fail with missing method or class errors. `--release 17` prevents compiling references to Java SE APIs that do not exist in release 17.

Beyond the command-line compiler, Gradle Java Toolchains, Maven compiler plugin configuration, and IDEs can also choose a separate JDK or target release. When the class file version is not what you expect, check the actual configuration of the build task that produced the artifact.

## 8. UnsupportedClassVersionError

Common error message:

~~~text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
(class file version 65.0), this version of the Java Runtime
only recognizes class file versions up to 61.0
~~~

In this example:

- `65.0` is a Java 21 class file.
- `61.0` is the maximum level supported by the Java 17 runtime.
- The Java 17 runtime cannot load that Java 21 class file.

How to resolve it depends on your goal:

1. **Upgrade the runtime** to Java 21 or newer if the application requires Java 21 bytecode.
2. **Recompile** with `javac --release 17` if the application must run on Java 17 and its source and dependencies are compatible.
3. **Check dependencies** because a library JAR may have been compiled with a newer Java version even though the main application's classes still target an older Java version.
4. **Check the actual process** to ensure scripts, containers, services, IDEs, and CI all use the right runtime version.

Changing `JAVA_HOME` does not always resolve the error. An application may be launched via a different `java` binary path than the `java` command in your terminal. Inspect the exact process running the application.

## 9. Distinguishing version errors from class file format errors

| Error | Common meaning | What to check |
|---|---|---|
| `UnsupportedClassVersionError` | Major/minor version is not supported by the runtime, or preview is not properly enabled | Compare the class-file version with the runtime and check the preview flag |
| `ClassFormatError` | Class file is malformed, invalid, or contains unacceptable data | Check the magic number, size, artifact source, and packaging process |
| `NoClassDefFoundError` | The JVM cannot find a required class during loading or linking | Check the classpath/module path and dependencies |
| `ClassNotFoundException` | The requested class-loading mechanism cannot find the class name | Check the class name, classloader, and classpath |

`UnsupportedClassVersionError` is a subtype of `ClassFormatError`, but its specific cause is an unsupported version. Do not assume every class-loading error is caused by the major version; read the exception type and details.

## 10. Workflow for checking class file versions

When a class fails to run in the target environment, you can follow this workflow:

1. Identify the exact .class file or JAR that the runtime is loading.
2. Use `javap -verbose` to read `minor version` and `major version`.
3. If needed, read the first eight bytes to confirm the magic number and version in hex.
4. Match the major version against the Java release supported by the runtime.
5. Check the minor version; if it is 65535, confirm the class uses preview features and runs with the matching Java release and `--enable-preview`.
6. Check `java -version` of the exact process running the application.
7. Check `javac -version`, `--release`, toolchain, and compiler plugin settings of the build process.
8. Check all dependency JARs because a dependency may require a higher Java version than the application itself.
9. Rebuild the artifact with the appropriate target or upgrade the runtime as required.

If using Gradle, check both the JVM running Gradle and the compilation toolchain; these two configurations can differ. If using Maven, check Maven's JDK and the compiler plugin configuration. For applications packaged in containers, also check the runtime image because it determines the actual JVM.

## 11. Checklist

- [ ] The first four bytes of the class file are `CA FE BA BE`.
- [ ] Read the minor version at bytes 4–5 and the major version at bytes 6–7 correctly.
- [ ] Match the major version against the target Java release.
- [ ] Understand that minor version 65535 indicates a class file using preview features.
- [ ] Use `javap -verbose` to inspect artifacts.
- [ ] Use `--release` to compile compatibly for older releases when needed.
- [ ] Check dependencies and class files inside JARs.
- [ ] Verify the exact runtime used to launch the application.
- [ ] Only enable `--enable-preview` when required by a preview class file and supported by the matching release.

The magic number `CAFEBABE` confirms the class file identifier; the major version indicates the format generation; the minor version adds minor version details and preview status. By reading these three parts correctly, you can quickly determine which Java version a class file was built for and pinpoint the cause when a runtime refuses to load it.
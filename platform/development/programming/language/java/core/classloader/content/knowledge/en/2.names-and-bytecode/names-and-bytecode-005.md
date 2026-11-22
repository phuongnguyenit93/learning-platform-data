# Major, Minor Versions, and JDK Bytecode Support Limits

## 1. Why Does Bytecode Version Matter?

When compiling Java, `javac` transforms source code into a **class file** (typically with the `.class` extension). The JVM/ClassLoader reads the binary format of the class file to load, verify, and use the class. Each class file declares its own **format version** in the form `major.minor`; this is the information the JVM uses to decide whether it understands that class file.

Three concepts need to be separated:

- **JDK version used for compilation:** the version of the `javac` tool being run, such as JDK 21.
- **Class file version:** the pair of numbers `major_version` and `minor_version` actually recorded in each `.class` file, such as `61.0` (Java 17).
- **JVM/JRE version running the program:** the environment that must load the class file, such as Java 17 or Java 21.

For example, using `javac` from **JDK 21** with `--release 17` typically produces a **61.0** class file, which can be loaded by a Java 17 JVM if other classes and libraries are also compatible. If compiled with default settings on JDK 21, the class file normally has version **65.0**, and a Java 17 JVM does not understand it.

**Core rule:** The JVM must support the version *of each class file being loaded*, not just the JDK version on the developer's machine. A custom ClassLoader does not by itself make the JVM understand a newer format.

## 2. Location of Major and Minor in the `.class` Structure

The beginning of every standard class file has the following structure:

```text
Offset (byte)    Size           Field            Example for Java 17 class
0                4 bytes        magic            CA FE BA BE
4                2 bytes        minor_version    00 00  (= 0)
6                2 bytes        major_version    00 3D  (= 61)
8                2 bytes        constant_pool_count
...              ...            remaining structures
```

According to the Java Virtual Machine Specification (JVMS), `u2` values are **16-bit unsigned integers** written in **big-endian** order. Therefore, the 8 opening bytes `CA FE BA BE 00 00 00 3D` correspond to a valid magic number, minor 0, and major 61. The `minor_version` field comes **before** `major_version`, even though when referring to the version we write **61.0** (major before minor).

- `magic` confirms the Java class file signature; having the right magic number does not guarantee the rest is valid.
- `major` identifies the class file format generation the JVM needs to support.
- `minor` adds compatibility rules, which is especially significant for **preview features** since Java 12.
- New bytecode instructions, constant pool entries, attributes, and other structures may require the JVM of the corresponding Java version. You cannot simply edit the 2 major bytes to turn a new class into a valid older class.

## 3. Java ↔ Major Version Conversion Table

The table below shows the **major version introduced** in each Java release; older Java 1.x versions used a different naming scheme from Java 5 onward.

| Java/JDK | Major | Java/JDK | Major | Java/JDK | Major |
|---|---:|---|---:|---|---:|
| JDK 1.0.2, 1.1 | 45 | Java 9 | 53 | Java 18 | 62 |
| JDK 1.2 | 46 | Java 10 | 54 | Java 19 | 63 |
| JDK 1.3 | 47 | Java 11 | 55 | Java 20 | 64 |
| JDK 1.4 | 48 | Java 12 | 56 | Java 21 | 65 |
| Java 5 | 49 | Java 13 | 57 | Java 22 | 66 |
| Java 6 | 50 | Java 14 | 58 | Java 23 | 67 |
| Java 7 | 51 | Java 15 | 59 | Java 24 | 68 |
| Java 8 | 52 | Java 16 | 60 | Java 25 | 69 |
| Java 17 | 61 | Java 26 | 70 | — | — |

For **Java 5 and later**, you can remember the formula:

```text
major = Java version number + 44
Java 8  → 52
Java 17 → 61
Java 21 → 65
Java 26 → 70
```

This formula does not apply mechanically to the historical version names `1.0`–`1.4`: for example, both JDK 1.0.2 and 1.1 are associated with major 45. Nor is it a way to calculate the minor version.

As of Java SE 26, the JVMS specifies that a Java SE 26–compliant JVM supports **major versions 45 through 70**. Each JVM version has its own upper limit: Java 8 is 52, Java 11 is 55, Java 17 is 61, Java 21 is 65, Java 25 is 69, and Java 26 is 70. Standard JVMs also support many older major versions (according to the JVMS support table), but being able to *load a class file* does not guarantee that all older libraries/APIs or all program behaviors remain compatible.

## 4. Minor Version and Preview Bytecode

### 4.1. Normal Class Files

In modern Java releases, class files compiled without relying on preview features usually have `minor=0`, such as `52.0`, `61.0`, `65.0`. However, one should not claim that **every** Java class file in history has minor 0:

- For major **45–55** (up to Java 11), the JVMS allows minor values from 0 to 65535. Historically, JDK 1.0.2 supported `45.0`–`45.3`; early versions had their own compatibility rules.
- For major **56 and above** (from Java 12 onward), minor **may only be 0 or 65535**. Any other minor value, such as `61.1`, is invalid under this rule.

### 4.2. The Value 65535 (0xFFFF) for Preview

Since Java 12, a class file with `major=M` (M ≥ 56) and `minor=65535` indicates that it **depends on preview features of the exact Java release associated with M**. For example:

- `61.65535` is tied to preview features of **Java 17**.
- `65.65535` is tied to preview features of **Java 21**.
- `70.65535` is tied to preview features of **Java 26**.

To load a preview class file, the JVM must be **that exact Java version** and preview must be enabled at runtime (`--enable-preview`). A Java 21 JVM cannot load `61.65535` from Java 17, **even when `--enable-preview` is enabled**. Likewise, a Java 17 JVM cannot load `65.65535`. This is a major difference from a normal `61.0` class file, which can run on a newer JVM when other conditions are met.

Example command when compiling **code that actually uses a preview feature provided by JDK 21** (the file and syntax must conform to Java 21):

```bash
javac --enable-preview --release 21 PreviewDemo.java
java --enable-preview PreviewDemo
```

To use `--release 21`, the `javac` version must support that target. This is an example of how to invoke the commands, not a standalone runnable program, because the contents of `PreviewDemo.java` depend on the preview feature you choose. Not every invocation with `--enable-preview` means every resulting class has minor 65535: you need to inspect the actual class file.

**Compatibility warning:** Preview APIs and preview language features may change or be removed in a later Java release. Do not apply the "newer JVM runs all older classes" rule to preview class files.

## 5. Checking Major/Minor with JDK Tools

### 5.1. Using `javap -verbose`

Create the file `VersionDemo.java`:

```java
public final class VersionDemo {
    public static void main(String[] args) {
        System.out.println("Bytecode target demo");
    }
}
```

On **JDK 17 or newer** that supports `--release 17`, run:

```bash
javac --release 17 VersionDemo.java
javap -verbose VersionDemo
java VersionDemo
```

Near the top of the `javap -verbose` output, look for these two lines:

```text
  minor version: 0
  major version: 61
```

This is an **excerpt** of the `javap` output; the constant pool and other metadata have been omitted. The Java program prints a single line to stdout:

```text
Bytecode target demo
```

You can use `javap -verbose -classpath out ten.goipackage.VersionDemo` when the `.class` file is in the `out` directory and has a `package`. `javap` reads the class file to inspect its metadata; it is not a way to verify that all runtime dependencies are compatible.

### 5.2. Reading the First 8 Bytes Directly with Java 17+

A small program shows the major/minor actually stored in the file, without relying on the JDK name:

Create `ClassVersionReader.java`:

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ClassVersionReader {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java ClassVersionReader <file.class>");
        }

        try (DataInputStream in =
                     new DataInputStream(Files.newInputStream(Path.of(args[0])))) {
            int magic = in.readInt();
            if (magic != 0xCAFEBABE) {
                throw new IOException("Not a Java class file");
            }

            int minor = in.readUnsignedShort();
            int major = in.readUnsignedShort();
            System.out.printf("major=%d, minor=%d%n", major, minor);
        }
    }
}
```

In the same directory as `VersionDemo.class` from section 5.1, run:

```bash
javac --release 17 ClassVersionReader.java
java ClassVersionReader VersionDemo.class
```

Exact stdout when `VersionDemo.class` was created with the `javac --release 17` command above and without preview:

```text
major=61, minor=0
```

`DataInputStream.readInt()` reads the 4-byte magic number, and `readUnsignedShort()` reads each big-endian `u2` into an integer from 0 to 65535. The program above only reads the **header**; it does not check the validity of the constant pool, methods, verifier, or whether the class can run.

### 5.3. Reading Errors and Confirming the Tools in Use

Check both the compiler and the JVM in your actual environment:

```bash
javac -version
java -version
```

The two commands may point to **two different JDK/JRE installations**, especially in IDEs, CI/CD, Docker, IDE Gradle daemons, or `PATH` configurations. Seeing that the compiler is JDK 21 **does not mean** the bytecode is necessarily major 65: check `--release` and `javap`. Similarly, selecting Java 17 in an IDE does not guarantee every build task or launcher is running JVM 17.

## 6. How Far Does JDK Bytecode Support Go?

The simple rule for **non-preview** class files: a Java N JVM can only load class files whose major version is within N's supported set. Look at **major** to check the format limit, then also check **minor**, file structure, libraries, and APIs at runtime.

| Class file | JVM Java 8 | JVM Java 17 | JVM Java 21 | JVM Java 26 |
|---|---|---|---|---|
| `52.0` (Java 8) | Supported | Supported | Supported | Supported |
| `61.0` (Java 17) | No | Supported | Supported | Supported |
| `65.0` (Java 21) | No | No | Supported | Supported |
| `70.0` (Java 26) | No | No | No | Supported |
| `61.65535` (Java 17 preview) | No | Only with preview enabled | No | No |

"Supported" in the table means **class file version support** per the standard JVM; it is not a promise that the application will run successfully. For example, a `52.0` class calling a library that is absent at runtime can still encounter `ClassNotFoundException`, `NoClassDefFoundError`, or `NoSuchMethodError`. A corrupted file structure can also lead to `ClassFormatError` or verification errors.

A JVM **does not automatically downgrade** a newer format to an older one. When 100 class files exist in the same process, it only takes one loaded class with a major version exceeding what the JVM supports for the application to fail at the time that class is loaded; some errors therefore do not appear immediately at startup.

## 7. Producing Bytecode for the Target JVM

### 7.1. Prefer `--release`

If deploying on Java 17 while the build machine uses JDK 21, choose:

```bash
javac --release 17 VersionDemo.java
```

`--release 17` coordinates the **source language**, **target class file**, and **standard APIs exposed for Java 17**. It helps prevent generating major 61 code that accidentally calls standard APIs only introduced in Java 21. This still does not replace checking third-party library compatibility and running actual tests on Java 17.

For example, with JDK 21:

```bash
javac VersionDemo.java
```

Without any other target configuration, the class is normally **65.0**. Whereas:

```bash
javac --release 17 VersionDemo.java
```

produces **61.0**. You can verify this with `javap -verbose`.

### 7.2. Distinguishing `--source`, `--target`, and `--release`

- `--source 17`: applies Java 17 syntax/language level during compilation.
- `--target 17`: requests the target class file version corresponding to Java 17.
- `--release 17`: aligns source, target, and the Java 17 platform API set that the compiler allows; usually the safest choice for cross-compilation.

Setting **only** `--target 17` does not prove the application will run on Java 17: the code can still reference standard APIs introduced in a newer Java release if APIs are not constrained at compile time, and dependent libraries can also have a higher class version. `--release` does not recompile already-packaged libraries or fix behavioral compatibility issues between two JVMs.

With Maven/Gradle, the equivalent compiler release configuration must be applied to the appropriate build module; after building, verify the actual `.class` artifacts and run integration tests on the **lowest supported JVM**.

## 8. When a ClassLoader Loads Incompatible Bytecode

The class loading process can be viewed conceptually:

```text
ClassLoader is requested to load a class name
    ↓
Locate / obtain the class file bytes
    ↓
JVM reads the header (magic, minor, major) and class structure
    ↓
Check format and JVM limits
    ├─ Unsupported version → UnsupportedClassVersionError
    ├─ Invalid structure → ClassFormatError / related error
    └─ Valid → create class; link, verify, and initialize at the appropriate time
```

This is a *conceptual* diagram; the exact sequence and timing of load/link/verify/init depend on the situation. A custom ClassLoader can read bytes from a file, network, JAR, or dynamically generated data and call `defineClass(...)`, but ultimately the JVM still checks the format against its current version limits.

**Error example:** a class compiled with JDK 21 using defaults (major 65) cannot be loaded when run on a Java 17 JVM (maximum major 61). The message typically mentions `UnsupportedClassVersionError`, `class file version 65.0`, and that the JVM only recognizes up to `61.0`; the exact wording varies across JVM versions or vendors. The fix is to **run on an appropriate JVM** or **recompile the class and all related dependencies for Java 17**, if the code and APIs allow it. Do not manually edit the header to "downgrade the version".

Quickly distinguish commonly confused error families:

| Symptom | What to check |
|---|---|
| `UnsupportedClassVersionError` | `.class` major/minor vs. JVM limit; for preview, whether it matches the exact Java release and preview is enabled |
| `ClassFormatError` | Structural or format error in class file data; `UnsupportedClassVersionError` is a specific case in this family |
| `VerifyError` | Bytecode violates verifier rules; not necessarily because the class file is too new |
| `ClassNotFoundException` / `NoClassDefFoundError` | Missing class on classpath/module path, linking/loading failure, or a prior error; do not immediately blame version |
| `NoSuchMethodError` | Runtime API/library version mismatch even when the class major version is valid |

### Real-World Scenario: A Java 17 Service Using a Java 21 Library

Suppose a service is compiled with `--release 17`, but a dependency JAR contains `SomeLibrary.class` with major 65. The build *might* fail to use that dependency depending on how it is compiled; if the artifact is still packaged and the Java 17 JVM has to load class 65.0, runtime will fail with a version error. Inspect the classes inside the JAR or use dependency analysis/build compatibility tools; checking only the entry-point class is not enough.

A **Multi-Release JAR** can carry different classes under `META-INF/versions/<N>/` and select the appropriate variant for the running JVM when the JAR is properly configured as multi-release. This helps libraries provide multiple compatibility levels, but it does not make an older JVM understand a newer class file version on its own.

## 9. Diagnostic Workflow for Bytecode Version Errors

1. Record the **actual JVM** of the failing process (terminal, service, test runner, Docker/CI); run `java -version` in the exact environment.
2. Find the **failing class name** in the stack trace; determine whether that class belongs to your module or a dependency JAR.
3. Inspect `major/minor` of **that specific class file** using `javap -verbose` or a header-reading program; do not infer it solely from `pom.xml`/Gradle targets.
4. Compare the class version against the JVM limit and check `minor=65535` for preview.
5. If the class is too new, upgrade the runtime per system requirements or build/publish the artifact for the appropriate target; check transitive dependencies as well.
6. Verify API availability on the lowest runtime and run smoke/integration tests on the exact deployment JVM.

**Common mistakes to avoid:** confusing the JDK version with the bytecode version; assuming minor does not matter; thinking a `low major` guarantees all APIs will run; believing that enabling `--enable-preview` on a newer JVM will run preview classes from an older JVM; hex-editing the major version instead of recompiling; upgrading only the build JDK while forgetting the production JVM.

## 10. Self-Check Questions

1. What version do the first 8 bytes `CA FE BA BE 00 00 00 41` indicate? **Answer:** major `0x41=65`, minor 0, i.e., a normal Java 21 class file.
2. Can a Java 17 JVM load a `65.0` class? **No**; Java 17 supports up to major 61.
3. Can a Java 21 JVM with `--enable-preview` run a `61.65535` class? **No**; Java 17 preview classes can only be loaded on Java 17 with preview enabled.
4. Can JDK 21 produce a `61.0` class? **Yes**, for example with `javac --release 17` for compatible code.
5. Does a `61.0` class running on a Java 21 JVM prove the app will definitely work? **No**; dependencies, APIs, linking, and runtime behavior must also be satisfied.
6. Why is `minor=1` on a `61.1` class invalid? **Because** for major versions 56 and above, minor is only allowed to be 0 or 65535.

## Standard Reference Documentation

- [Java Virtual Machine Specification, Java SE 26 — §4.1: The ClassFile Structure](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html): header format, major table, supported set, and minor/preview rules.
- [JVMS Java SE 26 — §1.5: Preview Features](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-1.html): enabling conditions and preview version binding.
- [Java `javac` tool reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): meaning of `--release`, `--source`, and `--target`.
- [Java `javap` tool reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): how to inspect class file details.

A **normal** class file is designed to be supported by a JVM of the same or a newer version; a **preview** class file is bound to its exact release. In both cases, the class file version is only a **necessary condition** for loading and running Java code.

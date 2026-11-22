# UnsupportedClassVersionError and Java Bytecode Versions

> **Java Core → ClassLoader → Common Errors.** `UnsupportedClassVersionError` occurs when the JVM attempts to read a class file with a **major/minor version** that the current JVM does not support. The most common scenario is **compiling with a newer JDK and then running with an older Java runtime**. In addition, the error is also related to **preview features**, dependencies/JARs containing bytecode of a different version, or classes generated/transformed by tools. This lesson focuses on understanding the `.class` header, identifying the JDK actually running, fixing it properly at build/deploy time, and preventing recurrence.

## 1. Identifying the Error from an Actual Message

A typical error when running a class compiled targeting Java 21 on Java 17:

```text
java.lang.UnsupportedClassVersionError: com/example/App
has been compiled by a more recent version of the Java Runtime
(class file version 65.0), this version of the Java Runtime only
recognizes class file versions up to 61.0
```

The message above is an **illustrative example of the error format**; the JVM may print the class name with `.` or `/`, and details and stack traces vary depending on the JDK. The data to read is:

- `com/example/App`: the class the JVM is trying to read, **not necessarily the class containing `main`**.
- `class file version 65.0`: the class file requires the format version corresponding to Java 21.
- `up to 61.0`: the runtime in the example supports up to major 61, corresponding to Java 17.
- The JVM refuses to read the **class file format** before it can execute that class's bytecode.

There are two direct solution directions **depending on project constraints**:

1. Run on a **sufficiently new runtime** to support the compiled class version (Java 21+ for major 65.0, with preview caveats).
2. If production must use **Java 17**, compile **all compatible code and dependencies** targeting Java 17 using `javac --release 17` or the equivalent build tool configuration.

Do **not** fix it by renaming the JAR, arbitrarily changing the classpath, changing the TCCL, forcing `URLClassLoader`, or editing the version number in the `.class` header. Those actions do not give an older JVM the bytecode instructions, constant pool tags, and JDK APIs of the newer version.

## 2. Where Does UnsupportedClassVersionError Sit in the JVM Error Family?

Inheritance hierarchy according to the Java API:

```text
java.lang.Object
  └── java.lang.Throwable
        └── java.lang.Error
              └── java.lang.LinkageError
                    └── java.lang.ClassFormatError
                          └── java.lang.UnsupportedClassVersionError
```

`UnsupportedClassVersionError` is thrown when the JVM **reads a class file** and detects that the major/minor version combination is not supported. It is an `Error`, **not a checked exception**, and does not belong to `ClassNotFoundException`.

Easily confused errors:

| Error | Common Scenario | Same Root Cause? |
| --- | --- | --- |
| `UnsupportedClassVersionError` | The JVM does not support the `major_version`/`minor_version` of the loaded class file. | **This exact topic.** |
| `ClassNotFoundException` | A class-lookup API by name (`Class.forName`, `ClassLoader.loadClass`) cannot find a matching definition. | No; the class may not be on the search path. |
| `NoClassDefFoundError` | The JVM needs a class during linking/execution but has no matching definition, or the class previously failed initialization. | Not by default; inspect the cause and details. |
| `ClassFormatError` | Invalid bytecode/constant pool/header/classfile. | Parent error family; version mismatch is a sub-branch. |
| `VerifyError` | Bytecode fails verifier rules. | Different from format version, though it can occur after the class-reading step. |
| `NoSuchMethodError` | Runtime method/signature is incompatible with the compiled class. | May result from mixing Java APIs/versions; not fixed by changing the major version. |
| `UnsupportedOperationException` | An operation valid with respect to class loading, but not supported by the application API. | Completely different. |
| `IllegalAccessError` | Runtime access/linkage checks fail. | Usually caused by module or class/member access. |

A `ClassLoader` can find the **right file** and read its bytes successfully, yet `defineClass` still throws `UnsupportedClassVersionError`. Therefore, do not equate “class not found” with “the JVM does not understand the class file version”.

## 3. Class-File Header: CAFEBABE, minor, and major

A `.class` file begins with a header according to JVM Specification `4.1`:

```text
Offset (byte)    Size         Meaning
0..3             u4           magic = 0xCAFEBABE
4..5             u2           minor_version
6..7             u2           major_version
8..               ...          constant_pool_count and the rest
```

These integers use **big-endian**. For example, a class compiled with `javac --release 17` typically starts with:

```text
CA FE BA BE 00 00 00 3D ...
| magic   |minor|major|
                 0x003D = 61 (Java 17)
```

Do not confuse version numbers in `MANIFEST.MF` (`Implementation-Version`, `Bundle-Version`, etc.) with the `major_version` stored in **each `.class` entry**. A single JAR can contain multiple class files with different major versions; a nested dependency on the classpath may even have a different version from the `Main` class.

### Major Version Conversion Table

According to the version table in the Java Virtual Machine Specification, Java SE 26:

| Java release | Standard class file major |
| --- | ---: |
| Java 8 | 52 |
| Java 9 | 53 |
| Java 10 | 54 |
| Java 11 | 55 |
| Java 12 | 56 |
| Java 13 | 57 |
| Java 14 | 58 |
| Java 15 | 59 |
| Java 16 | 60 |
| Java 17 | 61 |
| Java 18 | 62 |
| Java 19 | 63 |
| Java 20 | 64 |
| Java 21 | 65 |
| Java 22 | 66 |
| Java 23 | 67 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |

For **Java 5 and above**, the quick lookup rule for release `N` is `major = N + 44` (and `N = major - 44` within this range). **Do not mechanically apply this formula to legacy versions 1.0–1.4**: Java 1.0/1.1 use major 45 and Java 1.2–1.4 have 46–48.

According to Java SE 26, a compliant JVM supports major versions in the range 45–70; Java 17 or 21 JVMs have a **lower upper bound**. Newer JVMs tend to support older formats, **but that does not mean every older application always runs identically on a newer JDK**, because runtime APIs, modules, native libraries, and other changes also apply.

### How to Read the Version in the Message?

`65.0` means **major=65, minor=0**, corresponding to the standard format of Java 21. It does not mean “Java 65” or JDK 6.5. `61.0` means the Java 17 class-file format. Reading these two numbers first will avoid wasting time fixing the wrong library.

## 4. Minor Version and Preview Features: An Important Exception

A class using preview features can carry **minor version 65535**. Rules from Java 12 onward in the JVM Specification:

- For class-file major versions 56 and above, valid minor versions are generally **0 or 65535**.
- `M.65535` indicates a class that **depends on preview features** of the exact release corresponding to major `M`.
- A preview class of release `N` can only be loaded on a JVM of the **exact release `N`**, when preview is enabled for the runtime (typically `java --enable-preview ...`).
- A **newer** JVM version does not automatically accept a preview class file from an **older** version, even when `--enable-preview` is enabled.
- Do not use `--enable-preview` as a fix for every `UnsupportedClassVersionError`; a major-too-new error and a preview-minor error are different.

Example:

```text
61.0      = standard class-file targeting Java 17
61.65535  = preview class-file of Java 17
65.0      = standard class-file targeting Java 21
65.65535  = preview class-file of Java 21
70.0      = standard class-file targeting Java 26
70.65535  = preview class-file of Java 26
```

A `61.65535` class can be used on exact Java 17 with preview enabled, but **cannot be used on Java 21/24/26** simply by enabling the flag. The sustainable solution is to **recompile the preview source for the target Java release**, modifying the code to use stable features if possible.

### Compiling and Running Preview on the Same Release

General syntax (example for a JDK using preview):

```bash
javac --enable-preview --release 26 Demo.java
java --enable-preview Demo
```

This is a **syntax example for JDK 26**, assuming the source contains preview features supported by that JDK; it **does not run as-is on JDK 17/21/24** and does not replace the standalone test in section 8 of this lesson. The compiler only supports `--enable-preview` combined with the source/release of the **current compiler version**; do not use JDK 26 to emit a Java 17 preview class using `--release 17`.

For older class files prior to Java 12, minor rules have a different history; when diagnosing modern Java applications, focus on the major/minor pairs stated in the message.

## 5. Why Does Compiling with a Newer JDK and Running on an Older JVM Fail?

Suppose:

```text
Developer machine / CI:
    javac 21 -> App.class major=65

Production server:
    java 17 -> supports max major=61

ClassLoader reads App.class
    -> JVM rejects version 65
    -> UnsupportedClassVersionError
```

By default, the compiler usually generates class files according to the Java release of the **compiler itself** if no target is configured. Therefore, if someone on the team uses JDK 21 while the production runtime is Java 17, simply running `javac App.java` or using the default configuration can produce an incompatible artifact.

Common failure scenarios:

1. **The JDK is upgraded on the build machine, but production has not been upgraded.** The Docker base image or VM JRE is still Java 17.
2. **Inconsistent Maven/Gradle toolchains.** The Java compiler uses a newer version, while the runtime launcher uses an older version.
3. **A third-party library bumps its major version.** The application source still builds against the older target, but the new dependency release only supports a newer JVM.
4. **The IDE compiles with a Project SDK different from the runtime.** IntelliJ/Eclipse have separate project language levels, compiler SDKs, and run configurations.
5. **A plugin loader loads a JAR from a newer plugin.** The older host runtime cannot read the plugin's classes, even though the main host starts successfully.
6. **A framework generates or instruments bytecode.** Byte Buddy, ASM, proxy generators, or build plugins may generate a class-file major version beyond the current JVM's capability.
7. **Multi-release JAR packaged or read incorrectly.** Classes under `META-INF/versions` need to be selected by the runtime according to Multi-Release JAR rules; custom tools may mistakenly pick the entry for a newer JDK.
8. **Mixed-up PATH, JAVA_HOME, and toolchains.** The `javac` and `java` executables actually invoked may come from two different JDKs.

Having a `Main` class with major 61 does not guarantee that all `.class` files on the classpath are major 61. The JVM checks only when each class is loaded; therefore, an app may start up, run several features, and then fail when accessing a newer class in a dependency or plugin.

## 6. Checking the Actual Compiler and Runtime Versions in Use

### Distinguishing java, javac, and the Running Process

Commands:

```bash
java -version
javac -version
java --version
javac --version
```

Typically, `java -version` prints runtime information and `javac -version` prints compiler information. **Do not conclude that they point to the same installation** just because the commands do not report errors.

If you need to check the executable path:

```bash
# Linux/macOS:
command -v java
command -v javac
echo "$JAVA_HOME"

# PowerShell:
Get-Command java
Get-Command javac
$env:JAVA_HOME
```

These are environment-dependent shell commands; there is no fixed stdout because paths vary. `JAVA_HOME` is a configuration variable and **does not necessarily match** the executable chosen by PATH, an IDE, a Gradle daemon, or a container.

For containers or production processes, run the commands inside the **exact environment running the application** instead of only from a developer's machine terminal. Check the service's JVM using startup logs or `jcmd` if you have permission; running `java -version` from a host terminal does not prove that the JVM running inside the container is the same version.

### Inspecting an Actual Class File

JDK command:

```bash
javap -verbose path/to/App.class
```

In the header section, you will see:

```text
minor version: 0
major version: 65
```

This is **illustrative output** of a major 65 class, not the result of running on the artifact in section 8 (the example artifact in section 8 is major 61). If `javap` is an older version than the class file, the tool may not parse all newer structures; directly reading the 8 header bytes still determines the version.

For a class inside a JAR:

```bash
jar tf my-library.jar
javap -verbose -classpath my-library.jar com.example.Widget
```

`my-library.jar` and `com.example.Widget` are placeholders. `javap` must target the right JAR and class for the output to be meaningful. `jar tf` lists entries but **does not automatically list the major version** of each `.class`. If multiple JARs contain the same class, check the exact archive selected by the runtime; `javap -classpath ...` alone does not prove that the running loader loaded that class from that JAR.

## 7. How to Fix It Properly: Upgrade the Runtime or Build for an Older Target?

### Option A — Upgrade the JVM Runtime

When Java 21 APIs/language features/bytecode are required:

```text
Compile target: Java 21
Runtime:        Java 21 or higher with appropriate compatibility conditions
```

For major 65.0, upgrading from Java 17 to Java 21 resolves the **class-file major version limit**. However, you still need to test dependencies, JPMS encapsulation, native code, JVM flags, and behavioral changes. Upgrade the JDK only if approved by the project and operations, updating the Docker image/VM/container/service configuration as well.

If the class is preview `65.65535`, running on Java 21 with preview enabled is the appropriate requirement; **Java 25 cannot automatically use** a preview class from Java 21.

### Option B — Compile to Support an Older Java Version

When production must run Java 17, you should use:

```bash
javac --release 17 -d out src/com/example/App.java
```

This command snippet assumes the Java file is in the expected location. `--release 17` simultaneously:

- Uses syntax and language features according to **release 17**.
- Generates class files corresponding to **target Java 17** (major 61).
- Checks against the public documented Java SE/JDK APIs available in release 17, preventing accidental calls to JDK APIs that only exist in newer releases.

Compared to using `--target 17` alone, `--release 17` is safer for cross-compilation because it aligns **source, target, and platform APIs**.

For example, a program using an API added after Java 17 cannot “run on Java 17” merely by forcing major 61. The `--release 17` compiler will reject APIs not present in the target release when resolving them via their corresponding symbols.

### Why Are Separate --source and --target Not Enough?

`--source 17` selects language syntax. `--target 17` specifies the class-file output target. If compiled on a newer JDK with **newer JDK APIs** visible, a source file may still compile and produce major 61, yet fail at runtime on Java 17 due to missing classes/methods (for example, `NoSuchMethodError`), depending on the program.

```bash
# Usually RECOMMENDED:
javac --release 17 -d out src/com/example/App.java

# Not completely equivalent regarding platform API constraints:
javac --source 17 --target 17 -d out src/com/example/App.java
```

These two commands are templates applicable to an appropriate project structure, not copy-and-run commands when `src/com/example/App.java` does not yet exist. `--release` cannot be combined with `--source` or `--target` in the same invocation.

Important: `--release 17` on the **application module** does not automatically force **precompiled dependency JARs** down to major 61. If a dependency contains major 65, you must choose a **dependency version that supports Java 17**, build the dependency yourself for the right release from valid source, or upgrade the runtime.

### Choosing a Supported Compile Version

Not every JDK allows `--release` down to arbitrarily old versions. Check with:

```bash
javac --help
```

The `javac` documentation states that each JDK only supports the current release and a set of previous releases. You must choose an appropriate compiler/toolchain rather than arbitrarily passing `--release 1.4` on JDK 26.

## 8. Runnable Practice: Reading major/minor and Reproducing UnsupportedClassVersionError

To avoid needing two JDK versions installed side by side, the experiment below:

1. Compiles the `demo.Greeting` class with `--release 17`, producing a class header with **major 61, minor 0**.
2. Uses a custom loader to load the original bytes successfully.
3. Creates an **in-memory copy** of the bytes and intentionally modifies **the two major bytes to 32767**, far beyond supported Java releases, to test `UnsupportedClassVersionError`.
4. Creates another copy keeping major 61 but setting **minor to 65535**, equivalent to a Java 17 preview class header, and then attempts to load it on a runtime of a **different release** or with preview disabled; it is rejected according to the preview rules.
5. Does not overwrite the original class file on disk. Editing the header here is **only an experiment to illustrate the condition the JVM checks**, **not a way to fix the error**.

The experiment is compatible with Java 17+; the results below were verified on OpenJDK 24 with preview disabled. If run on exact JDK 17 **and with** `--enable-preview` enabled, the minor 61.65535 scenario may differ, as noted in section 4.

### Directory Structure

```text
src/
  demo/
    Greeting.java
  app/
    VersionProbe.java
out/
  plugin/     (created by javac)
  app/        (created by javac)
```

**File `src/demo/Greeting.java`:**

```java
package demo;

public class Greeting {
    public String say() {
        return "hello";
    }
}
```

**File `src/app/VersionProbe.java`:**

```java
import java.nio.file.Files;
import java.nio.file.Path;

public class VersionProbe {
    static final class DemoLoader extends ClassLoader {
        DemoLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> define(byte[] bytes) {
            return defineClass(
                    "demo.Greeting", bytes, 0, bytes.length);
        }
    }

    static int u2(byte[] b, int offset) {
        return ((b[offset] & 0xff) << 8)
                | (b[offset + 1] & 0xff);
    }

    public static void main(String[] args) throws Exception {
        byte[] original = Files.readAllBytes(
                Path.of("out/plugin/demo/Greeting.class"));

        System.out.println("magic: "
                + String.format("%02X%02X%02X%02X",
                        original[0], original[1],
                        original[2], original[3]));
        System.out.println("minor: " + u2(original, 4));
        System.out.println("major: " + u2(original, 6));
        System.out.println("normal load: "
                + new DemoLoader().define(original).getName());

        byte[] future = original.clone();
        future[6] = (byte) 0x7F;
        future[7] = (byte) 0xFF;  // major = 32767

        try {
            new DemoLoader().define(future);
            System.out.println("future-major rejected: false");
        } catch (UnsupportedClassVersionError expected) {
            System.out.println("future-major rejected: true");
        }

        byte[] oldPreview = original.clone();
        oldPreview[4] = (byte) 0xFF;
        oldPreview[5] = (byte) 0xFF; // minor = 65535

        try {
            new DemoLoader().define(oldPreview);
            System.out.println("old-preview rejected: false");
        } catch (UnsupportedClassVersionError expected) {
            System.out.println("old-preview rejected: true");
        }
    }
}
```

**Compile commands** (from the directory containing `src`):

```bash
javac --release 17 -d out/plugin src/demo/Greeting.java
javac --release 17 -d out/app src/app/VersionProbe.java
javap -verbose out/plugin/demo/Greeting.class
java -cp out/app VersionProbe
```

On Windows PowerShell/CMD, you can run the same single-line commands if the current directory is correct. `javap -verbose` prints extensive information; the relevant part:

```text
minor version: 0
major version: 61
```

**Exact stdout of `java -cp out/app VersionProbe` on OpenJDK 24:**

```text
magic: CAFEBABE
minor: 0
major: 61
normal load: demo.Greeting
future-major rejected: true
old-preview rejected: true
```

### Why Did Both define Calls Fail?

- `future[6]` and `future[7]` are the byte positions of **major_version**, big-endian. `0x7FFF = 32767` is not supported by the JVM in use.
- `oldPreview[4]` and `oldPreview[5]` are **minor_version**. With major 61, minor `65535` denotes a preview class for Java 17; the OpenJDK 24 JVM running the test cannot load a Java 17 preview class.
- A different `DemoLoader` instance is created each time to avoid duplicate-definition errors for the same binary name and ensure we observe the **version** error properly. The `demo.Greeting` class is not in `out/app`, and the parent platform loader does not see `out/plugin`.
- The JVM detects and throws `UnsupportedClassVersionError` at `defineClass`; the code intentionally catches it so the demo can continue. **Production applications should not catch and silence it**, because that is a sign of an incompatible artifact.
- The original `byte[]` still retains the `61.0` header and can be loaded. No `.class` file is patched on disk.

**Do not take the number 32767 to identify a real Java version**. It only serves as an unsupported major version in the experiment, not a version you should put into an artifact.

## 9. Why Can the Error Come from a Dependency, Plugin, or Generated Bytecode?

A stack trace may name:

```text
com/vendor/library/SomeHelper
```

even though your `main` class has already finished the startup phase. The reason is that the JVM performs **on-demand loading and resolution**: only when the program touches a new class does the JVM need to read its class-file bytes.

### Dependency Compiled for a Newer Version

Example:

```text
application.jar          (major 61, Java 17)
  -> logging-core.jar    (major 61)
  -> new-feature.jar     (major 65, Java 21)
runtime: Java 17
```

`new-feature.jar` contains a major 65 class, whereas Java 17 supports at most major 61; the error appears when the JVM needs a class from that library. Lowering the target of the **application** does not automatically recompile `new-feature.jar`.

How to handle it:

- Find the exact class name in the stack trace and the artifact containing it.
- Check the dependency tree (Maven/Gradle) and the minimum supported Java version of that release.
- Choose a dependency version that still supports Java 17 or upgrade the runtime.
- If building the dependency yourself, recompile the entire dependency with `--release 17` and verify it does not call newer APIs.

### Custom Plugin Loaders

A `URLClassLoader` can locate a class successfully yet `defineClass` throws `UnsupportedClassVersionError`. A custom loader cannot make Java 17 support major 65 by overriding `getClassLoadingLock`, changing the parent, adding URLs, or calling `definePackage`: the class format is a limit **of the JVM receiving the bytecode**, not of the lookup path.

For multi-version plugin systems, specify the **minimum supported Java runtime** in plugin metadata and validate the artifact before activation to fail early with a clear message.

### Bytecode Generators/Transformers

Tools such as ASM/Byte Buddy or runtime proxy generators must emit a class-file version supported by the running JVM, and must also understand newer JDK features. If a library generates bytes with a major version that is too new or invalid, the error may lie in a dynamically generated class (with no pre-existing `.class` on the filesystem). Check the generator version, target, JDK runtime, and configuration; do not assume changing `javac --release` affects bytecode generated by a library at runtime.

## 10. Multi-Release JARs: Multiple Classfile Versions in the Same Archive

A **multi-release JAR** can contain base classes and alternative versions for different Java releases:

```text
library.jar
├── META-INF/MANIFEST.MF
├── com/example/Feature.class
├── META-INF/versions/17/com/example/Feature.class
└── META-INF/versions/21/com/example/Feature.class
```

The manifest contains the attribute:

```text
Multi-Release: true
```

With valid version-selection behavior, the runtime selects the matching version-specific entry—typically the **highest release not exceeding the runtime feature version**—and falls back to the base entry if necessary. Therefore, **merely seeing `META-INF/versions/21` does not mean Java 17 will attempt to load the Java 21 class**.

However, errors can happen when:

- Packaging/shading tools drop or corrupt the `Multi-Release` attribute.
- The JAR's base classes themselves are compiled at a major version too high for the runtime that needs to be supported.
- A custom loader directly reads the raw entry `META-INF/versions/21/...` instead of honoring multi-release JAR semantics.
- A framework reads class bytes from the archive via ZIP APIs and applies overrides incorrectly.
- The dependency JAR does not support the runtime despite having a `META-INF/versions` folder.

Do not patch this by blindly deleting versioned directories. Check how the artifact is packaged and how the **actual loader** selects entries.

Helpful commands:

```bash
jar tf library.jar
jar xf library.jar META-INF/MANIFEST.MF
```

`jar xf` extracts an entry into the current directory, so run it only when you know the target and appropriate working directory. If you only want to inspect the manifest contents without modifying the workspace, you can use an appropriate ZIP/JAR viewer tool. These commands do not by themselves determine which class version is selected; runtime behavior must be verified.

## 11. Configuring Maven/Gradle and CI to Prevent Recurrence

### Maven: Consistent Release Configuration

In `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

This property is used by the Maven Compiler Plugin in supported versions/configurations. For complex projects, you should specify a supported compiler plugin version and use toolchains if the build machine has multiple JDKs. The **Java running Maven** can differ from the **JDK used to compile** under toolchains; check both.

Inspection commands:

```bash
mvn -version
mvn dependency:tree
```

Requires Maven and the corresponding plugins/dependencies. `mvn -version` mainly describes the JDK running the Maven process, **not always proof of the selected compiler toolchain**.

### Gradle: Java Toolchain and Release

An illustrative Gradle Groovy DSL configuration:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

The toolchain explicitly defines the compiler/JDK that Gradle uses for Java work; `options.release` requests class files and API compatibility for the target release when supported by the compiler. Do not simply set `sourceCompatibility` and assume the production JDK will automatically match. The Gradle/plugin version in use must support the target JDK; update tooling if needed.

### CI: Build and Test on the Lowest Supported Java Version

CI checklist:

1. **Define the runtime baseline** (for example, Java 17) in the build configuration.
2. Compile with `--release 17` or the equivalent option.
3. **Run integration tests on Java 17**, rather than only using JDK 21 and hoping for backward compatibility.
4. Check the major version of **all released artifacts and critical dependencies**, not just the main class.
5. On a matrix if multiple versions are supported, test Java 17/21/25... according to the support policy.
6. If there is preview code, bind it to the exact Java release with a migration plan; do not publish preview classes ambiguously for other runtimes.
7. Verify the Docker base image and the actual deployment JVM, because the build JDK does not dictate the production JVM.
8. Explicitly document the minimum Java version in documentation/plugin manifests so the host detects mismatches early.

A JAR whose base class is major 61 but uses native code, JNI, or APIs with behavioral differences still requires real runtime tests; scanning major versions **is not a complete compatibility test**.

## 12. Decision Tree for Fixing Errors Based on the Message

```text
See java.lang.UnsupportedClassVersionError
         |
         v
1. Get the class name and class-file M.m pair
         |
         v
2. Identify the actual running JVM: java -version / runtime logs
         |
         +--> M > runtime max major?
         |       |
         |       +-- YES:
         |           Choose:
         |            - upgrade the runtime to a supported release
         |            - OR rebuild all code/dependencies
         |              for the older release with --release
         |
         +--> M <= runtime max major?
                 |
                 v
3. Check minor:
      - m = 65535? preview on exact same release + enabled?
      - unusual/invalid m? check generator/transformer
                 |
                 v
4. Verify the specific JAR/class and actual classloader
                 |
                 v
5. Rebuild/redeploy + test on the actual baseline JVM
```

**If the runtime is Java 17 and you see class file 65.0:** No classloader flag resolves a format mismatch. Choose to upgrade the Java runtime to an appropriate level (Java 21+) or lower the target/rebuild the dependency for Java 17.

**If the runtime is Java 24 and you see class file 61.65535:** This is not an error due to a major version being too high; the cause lies in a **preview class file from Java 17**, which cannot be used on Java 24 according to the JVM Specification. You must rebuild from source for the release you want to run, or run on exact Java 17 with preview enabled if supported and acceptable.

**If the runtime is Java 21 and you see class file 65.0 yet still get another error:** Check the exact JVM actually running, the exact class source selected, and then see what the **exact** exception is. If it is `NoSuchMethodError` or `IllegalAccessError`, do not call it `UnsupportedClassVersionError`.

## 13. Common Mistakes

| Mistake | Why It Does Not Work | Right Approach |
| --- | --- | --- |
| Changing `JAVA_HOME` and concluding production switched JVMs | PATH, service wrappers, Docker images, or the Gradle daemon may use a different Java. | Identify the actual runtime executable/process. |
| Only setting `javac --source 17` | Does not guarantee both class target and platform APIs are correct. | Use `--release 17` and test on JVM 17. |
| Only setting `javac --target 17` | May still compile against newer APIs from the running JDK. | Use `--release` or toolchain/API matching. |
| Rebuilding only the app while keeping a major 65 dependency | JVM 17 still cannot read major 65 classes. | Change the dependency/build from source or upgrade the runtime. |
| Changing the major byte 65→61 with a hex editor | Newer bytecode may use unsupported instructions/features/constant pool entries; the class may break. | Recompile the source for the target; do not patch the header as a workaround. |
| Catching `ClassNotFoundException` to handle version errors | `UnsupportedClassVersionError` is a different `Error`. | Fix the artifact/JVM mismatch; log the version. |
| Adding a URLClassLoader to the classpath | The class may be found, but the JVM still does not support the version. | Determine the JVM's supported major version. |
| Enabling `--enable-preview` for a class with a major version newer than the runtime | The preview flag does not make the runtime understand newer release formats. | Use the right runtime or rebuild appropriately. |
| Using a newer JDK to run a preview class from an older JDK | Preview classes are strictly tied to the exact release. | Recompile the source for the newer release. |
| Believing `jar tf` displays class versions | It only lists entry names. | Use `javap -verbose` or read the header. |
| Seeing `Main.class` major 61 and concluding all plugins are Java 17 compatible | Dependencies/plugins/generated bytes may be higher. | Inspect the actual artifacts loaded by the JVM. |
| Believing a green CI build on JDK 25 means it runs on Java 17 | Tests passing on a newer JVM do not prove compatibility with an older JVM. | Use a test matrix including the baseline runtime. |
| Fixing any `LinkageError` by upgrading the JDK | LinkageError has many other causes. | Analyze the exception subtype and message. |

## 14. Self-Check Questions

1. **What does the message “class file version 65.0, runtime up to 61.0” mean?**  
   The class file is in Java 21 format, whereas the runtime supports at most Java 17.

2. **Is `UnsupportedClassVersionError` a checked exception?**  
   No. It inherits from `ClassFormatError → LinkageError → Error`.

3. **Which two bytes in a class file store the major version?**  
   Offsets 6 and 7, in big-endian; offsets 4 and 5 store the minor version.

4. **What major versions do Java 17 and Java 21 typically have?**  
   61 and 65, respectively.

5. **What does `--release 17` guarantee differently from `--target 17` alone?**  
   It coordinates source rules, class format, and the Java 17 platform APIs.

6. **Can an app whose main class is major 61 fail due to a major 65 dependency?**  
   Yes, when the runtime needs to load a class from the newer dependency.

7. **Is `61.65535` the same as `61.0`?**  
   No. Minor 65535 marks a Java 17 preview class; it has special runtime requirements.

8. **Can Java 24 run preview `61.65535` simply with `--enable-preview`?**  
   No. Preview classes from Java 17 cannot be loaded on Java 24.

9. **Does `jar tf library.jar` report the major version of all classes?**  
   No. Use `javap -verbose` for a specific class or a tool that scans class headers.

10. **Why does catching `ClassNotFoundException` fail to handle a version mismatch?**  
    The JVM already found/read the bytes, but does not support the version; it throws `UnsupportedClassVersionError`.

11. **Should you edit the header byte from 65 to 61 to run on Java 17?**  
    No. It does not make newer bytecode semantics or APIs compatible with Java 17.

12. **Does a multi-release JAR containing `META-INF/versions/21` automatically fail on Java 17?**  
    No, if the archive and loader follow multi-release selection and the base classes support Java 17.

13. **Why does testing on a newer Java version not prove an app runs on an older Java version?**  
    Newer runtimes typically understand older formats, whereas older runtimes do not understand newer formats; APIs and dependencies also differ.

14. **When production runs in a container, where should you check the Java version?**  
    Inside the actual container/process running the application, not only on the developer's machine.

## 15. Official Documentation

- [Java SE 26 — JVMS `1.2, class-file major versions table](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-1.html#jvms-1.2): Java 1.0–26 mapping and format compatibility.
- [Java SE 26 — JVMS `4.1, class file structure](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html#jvms-4.1): magic, minor/major version, preview rules, and format.
- [Java SE 26 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): official error class description.
- [Java SE 25 — javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `--source`, `--target`, and cross-compilation conditions.
- [Java SE 26 — ClassFileVersion](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFileVersion.html): major/minor and preview interpretation.
- [Java SE 21 — ClassLoader.defineClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): when the loader converts bytes into a runtime class.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): multi-release JAR, manifest, and versioned entries.
- [Java SE 21 — javap](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): using `-verbose` to read major/minor.

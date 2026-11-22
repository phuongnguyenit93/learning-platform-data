# Target version limits supported by each javac

When a Java project needs to support multiple JDK versions, the development team often wants to use a newer compiler to compile source code while still generating bytecode that runs on an older runtime. For example, building with JDK 21 while releasing a library for applications running on Java 17, or building with JDK 26 while still supporting the Java 8 runtime.

This capability is called *cross-compilation* or compiling for another platform version. However, each `javac` version only supports a specific set of target versions. That set varies by JDK and by the option used. One cannot assume that a new compiler can always compile for every older Java version.

What needs to be understood is the difference between `-source`, `-target`, and `--release`; the lowest/highest limits of each compiler; and how to inspect the exact list of targets supported by the `javac` on the machine.

## 1. Three concepts to distinguish

### 1.1. Source version

`-source N` instructs the compiler to accept the syntax and Java language rules of release `N`.

For example, when compiling with `-source 8`, source code must follow Java 8 language rules. Syntax introduced only in Java 9 or later will not be accepted.

`-source` controls the input language. It does not by itself guarantee that every API called by the source code exists on Java 8.

### 1.2. Target version

`-target N` instructs `javac` to generate class files suitable for JVM version `N`.

Example:

```bash
javac -source 8 -target 8 Hello.java
```

The compiler accepts Java 8 syntax and generates bytecode in a format compatible with the Java 8 JVM. However, if the source code calls an API introduced only in Java 11, the command above can still compile successfully when the compiler sees that API in the JDK currently being used. When running on Java 8, the program may fail due to a missing method or class.

### 1.3. Release version

`--release N` was introduced in JDK 9 under JEP 247. This option combines three requirements:

1. Accept the syntax and language rules of Java release `N`.
2. Generate class files with the target corresponding to release `N`.
3. Compile against the public, supported, and documented API set of release `N`.

Example:

```bash
javac --release 8 -d out src/main/java/com/example/Hello.java
```

If using a newer JDK that supports `--release 8`, the compiler will reject platform APIs that appeared only after Java 8. This is why `--release` is usually the most appropriate choice when using a newer JDK to build artifacts that run on an older JDK.

Do not combine `--release` with `-source` or `-target` in the same `javac` invocation.

## 2. General limits of a javac

There are two main limits:

- **Upper limit:** the compiler cannot produce a target for a Java SE release newer than the release to which the compiler itself belongs. To emit bytecode for Java 26, a compiler that understands Java 26 is required, typically `javac` from JDK 26 or newer.
- **Lower limit:** each `javac` version only retains support for a certain number of older releases. Targets that are too old may be deprecated and then removed. The lowest limit varies across JDK 8, 9, 11, 17, 25, 26, and other versions.

Therefore, the question "from which Java version to which Java version does javac support targets?" must always be accompanied by the compiler version and option under consideration. A machine with multiple JDKs can also produce different results depending on which `javac` path is invoked.

## 3. Support milestones by JDK version

The following table summarizes some representative milestones from JDK documentation. These are examples by compiler generation, not a guarantee that every vendor or every build has the exact same list. Especially with newer JDKs, the exact `--release` list must be obtained from `javac --help` of the compiler currently in use.

| Compiler | `-source` / `-target` | `--release` | Notes |
|---|---|---|---|
| JDK 8 | `-source`: 1.3 to 1.8; `-target`: 1.1 to 1.8. | Option does not exist. | To cross-compile, `-bootclasspath` and platform libraries of the exact version are required. |
| JDK 9 | Under the new policy, supports 6, 7, 8, and 9. | 6, 7, 8, 9. | `--release` was introduced in JDK 9. |
| JDK 10 | 6 to 10; value 6 is deprecated and emits a warning. | 6, 7, 8, 9, 10. | JDK 10 migration documentation lists source/target 6 to 10. |
| JDK 11 | 6 to 11; value 6 is deprecated and emits a warning. | 6, 7, 8, 9, 10, 11. | Oracle JDK 11 documentation explicitly lists this set of releases. |
| JDK 17 | 7 to 17. | Per the compiler's release support policy; check via help. | JDK 17 migration documentation lists source/target from 7 to 17. |
| JDK 25 | 9 to 25; value 8 is deprecated and emits a warning. | Current release and a certain number of supported older releases; see help for the exact list. | Oracle JDK 25 documentation explicitly states the source/target limits and instructs checking help for `--release`. |
| JDK 26 | 9 to 26; value 8 is deprecated and emits a warning. | Current release and a certain number of supported older releases; see help for the exact list. | Check the actual compiler/build being run rather than inferring from another JDK. |
| JDK 27 | 9 to 27; value 8 is deprecated and emits a warning. | Current release and a certain number of supported older releases; see help for the exact list. | JDK 27 migration documentation continues to state these source/target limits. |

### 3.1. JDK 8: older compiler without `--release`

JDK 8 `javac` has source levels from 1.3 to 1.8 and target levels from 1.1 to 1.8. The options are used in the form:

```bash
javac -source 1.8 -target 1.8 Hello.java
```

JDK 8 does not have `--release`. When cross-compiling, setting only `-source` and `-target` is not enough. You need to provide the correct platform classes of the target version via `-bootclasspath` (and related options if needed). If the compiler sees the platform libraries of the running JDK 8, it may inadvertently allow calling APIs that do not exist in the older target version.

### 3.2. JDK 9: introducing `--release`

JDK 9 introduced `--release` via JEP 247. The supported target list includes 6, 7, 8, and 9. JEP 182 also established that JDK 9 drops support for source/target 5 and earlier and applies a policy limiting old levels.

Example:

```bash
javac --release 8 Hello.java
javac --release 9 Hello.java
```

The first command generates an artifact targeting the Java 8 platform; the second generates an artifact targeting Java 9. You cannot use `--release 10` with JDK 9 `javac` because target 10 is a future version relative to the compiler.

### 3.3. JDK 10 and JDK 11

JDK 10 extended the `--release` list to 10; JDK 11 extended it to 11. Oracle JDK 10 documentation lists source/target 6 to 10, where 6 is deprecated and emits a warning. Oracle JDK 11 documentation lists source/target 6 to 11 and also marks 6 as deprecated.

This illustrates a principle: a compiler for a new release typically adds that release to its target set, but does not necessarily retain every old target forever. Read the list published by that exact compiler version.

### 3.4. JDK 17

JDK 17 migration documentation lists `-source` and `-target` values from 7 to 17. This is an example showing that the lowest limit changed compared to JDK 11.

If a project needs Java 6, one cannot assume that JDK 17 `javac` still supports that target. An older compiler may be needed, or the runtime baseline must change if business requirements permit.

### 3.5. JDK 25, JDK 26, and JDK 27

Oracle JDK 25, JDK 26, and JDK 27 documentation states that supported source/target values range from the current release down to Java 9; Java 8 is deprecated and emits a warning. When upgrading the compiler, a build previously using `-source 8 -target 8` may start emitting warnings or need to switch to a supported configuration under the new compiler policy.

For `--release`, the documentation states the general rule of the current release and a certain number of previous releases, while the specific list is found in command-line help. Therefore, do not infer the `--release` list from the `-source/-target` table; check each option individually.

## 4. Viewing the list of targets that javac actually supports

This is the most reliable way to know which releases a specific compiler accepts.

### 4.1. Check the exact executable

Run:

```bash
javac -version
```

If the machine has multiple JDKs, invoke the compiler using its full path to avoid confusion:

```bash
"$JAVA_HOME/bin/javac" -version
"$JAVA_HOME/bin/javac" --help
```

On Windows PowerShell:

```powershell
& "$env:JAVA_HOME\bin\javac.exe" -version
& "$env:JAVA_HOME\bin\javac.exe" --help
```

### 4.2. Read the `--release`, `--source`, and `--target` sections

```bash
javac --help
```

In the help output, look for the description lines:

```text
--release <release>
    Compile for the specified Java SE release.
    Supported releases: ...

--source <release>
    Provide source compatibility with the specified Java SE release.
    Supported releases: ...

--target <release>
    Generate class files suitable for the specified Java SE release.
    Supported releases: ...
```

The actual output may be abbreviated or formatted differently across versions. Read all three lines because the supported value set of each option should not be assumed to be identical.

If the compiler only displays a general description, you can test the desired target directly using a small Java file. However, the verification result must be obtained with the exact compiler of the build pipeline, not a different compiler on a personal machine.

### 4.3. Record the results in CI

To prevent a developer machine and CI from using two different compilers, log the version and help output when diagnostics are needed:

```bash
javac -version
javac --help
```

If the pipeline has multiple toolchains, print the compiler path and corresponding version for each compile task. When a target is dropped from a newer JDK, logs help identify which compiler is rejecting the configuration.

## 5. Why is `--release` safer than `-source` and `-target`?

Suppose the development team is using JDK 21 but needs to release a library that runs on Java 8. A class might be written as follows:

```java
public class TextHelper {
    public static String normalize(String value) {
        return value.strip();
    }
}
```

`String.strip()` has only existed since Java 11. If using:

```bash
javac -source 8 -target 8 TextHelper.java
```

the compiler can accept the `strip()` call because the visible API is the JDK 21 API. The output bytecode may carry a class file version suitable for Java 8, but when running on Java 8, that method will not be found.

If using:

```bash
javac --release 8 TextHelper.java
```

the compiler only allows using platform APIs published for Java 8. The `strip()` call will be rejected during compilation.

This is the core difference:

| Configuration | Checks language syntax | Controls target bytecode | Restricts platform API by target |
|---|---|---|---|
| `-source N` | Yes | No | No |
| `-target N` | No | Yes | No |
| `-source N -target N` | Yes | Yes | Not automatically |
| `--release N` | Yes | Yes | Yes |

If `-source/-target` must be used, the correct set of platform classes must be configured using `-bootclasspath` for targets before Java 9 or `--system` for Java 9 and later targets. This configuration is more complex and more error-prone than `--release`.

## 6. Class file version and target JVM version

The JVM uses the major version number in the class file to determine the bytecode format. Some common milestones:

| Java release | Class file major version |
|---:|---:|
| 8 | 52 |
| 9 | 53 |
| 10 | 54 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| 27 | 71 |

For example, class file major version 61 corresponds to Java 17. A Java 17 JVM understands Java 17 class files and supported older formats; a Java 8 JVM does not understand class file major version 61.

You can view the major version with:

```bash
javap -verbose -classpath out com.example.Hello
```

In the output, look for `major version`. This command confirms the generated class file format, but does not prove that the program only uses APIs present in the target runtime. To control platform APIs, `--release` or proper cross-compilation configuration is still required.

## 7. Target limits and class-file reading limits are two different things

A newer `javac` can read and process class files from many older JDKs, even very old class files. That does not mean the compiler can emit class files for every older release.

Distinguish between:

- **Input compatibility:** whether the compiler can read class files or libraries compiled from earlier versions.
- **Output target support:** which target releases the compiler can generate class files for.
- **API compatibility:** whether the source code only uses APIs present in the target release.
- **Runtime compatibility:** whether the application and all dependencies actually run on the target JVM.

A successful build only verifies part of these conditions. Tests must be run on the lowest runtime that the project commits to supporting.

## 8. When the target is too old and no longer supported

Suppose a project needs to release for Java 6, but a newer compiler no longer supports `--release 6`. There are several approaches:

1. **Use an appropriate older JDK compiler.** This is the direct approach if the project truly must keep the old baseline and can maintain the corresponding toolchain.
2. **Re-evaluate the runtime baseline.** If users and deployment environments allow, raise the baseline to a release still supported by compilers and libraries.
3. **Split artifacts by baseline.** A legacy branch or artifact can use an older toolchain, while modern artifacts use a newer toolchain. The APIs and dependencies of each variant must be clearly controlled.
4. **Use another compiler that supports the required language level.** Choose this only when that compiler can generate bytecode and restrict APIs accurately for the target runtime; real testing is still required.

Do not simply lower `-source` or `-target` to a removed value and try to force the compiler to accept it. That does not solve the fact that the compiler no longer has the necessary historical language models or APIs.

## 9. Configuring multi-version compilation in a project

### 9.1. Direct compilation with javac

To generate a Java 17 artifact using a newer JDK:

```bash
javac --release 17 -d build/classes \
    src/main/java/com/example/App.java
```

To generate a Java 8 artifact if supported by the current compiler:

```bash
javac --release 8 -d build/classes \
    src/main/java/com/example/App.java
```

Both commands use the same compiler, but set different language, API, and bytecode target contracts.

### 9.2. Maven

With the Maven Compiler Plugin, configure `release` in `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Ensure the Maven Compiler Plugin version in use supports this property and Maven is invoking the right JDK/toolchain. Having JDK 17 installed on the machine does not automatically guarantee Maven uses JDK 17.

If you need to build with a specific JDK, you can use the Maven Toolchains Plugin to select the toolchain according to project configuration and the build machine.

### 9.3. Gradle

With Gradle, you can set the release for Java compilation tasks:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

Or configure a Java toolchain to select the compiler:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
```

In this example, the toolchain selects the JDK 21 compiler; `options.release = 17` requests generating an artifact targeting Java 17. The two configurations have different roles: the toolchain decides which compiler runs, while release decides the target platform.

## 10. Testing matrix for multiple runtimes

If a library commits to supporting Java 8, 17, and 21, succeeding in a single build with JDK 21 is not enough. You should test on each committed runtime:

| Step | Java 8 | Java 17 | Java 21 |
|---|---|---|---|
| Compile artifact | Can use `--release 8` if supported by compiler. | Can use `--release 17`. | Can use `--release 21`. |
| Check class files | Major 52 | Major 61 | Major 65 |
| Unit tests on runtime | Yes | Yes | Yes |
| Integration tests | Yes | Yes | Yes |
| Check dependencies | Library version must support Java 8. | Library version must support Java 17. | Library version must support Java 21. |

In CI, you can use a single newer JDK compiler to generate artifacts using the lowest `--release`, and then run tests on each supported JDK. There should also be separate build jobs on key LTS JDKs if the project needs to detect compiler or toolchain changes early.

## 11. Common errors and how to handle them

### `error: release version N not supported`

The compiler does not support the requested target. Check `javac -version`, `javac --help`, and the compiler path actually invoked by the build tool. If the target is lower than the compiler's limit, use an older toolchain or adjust the baseline after assessing the impact.

### `Source option N is no longer supported`

The source level has been removed from the compiler. Do not assume that a new compiler supports every old source level. Check the support list and the removal policy of JEP 182.

### Compilation succeeds but runtime reports `NoSuchMethodError` or `NoClassDefFoundError`

The build may have used `-source/-target` without restricting the platform API, or an external dependency was compiled for a newer Java version. Use `--release`, inspect dependency bytecode, and run tests on the lowest runtime.

### `UnsupportedClassVersionError`

The running JVM does not support the class file's major version. Check the major version using `javap -verbose`, identify the target used, and check the process's actual runtime.

### IDE builds succeed but CI fails

The IDE and CI may use different compilers or different Maven/Gradle versions. Print the `javac` path, `javac -version`, toolchain configuration, and release in the logs of both environments.

## 12. Process for determining an appropriate target

1. **Identify the lowest runtime that needs to be supported.** This is a product and deployment environment requirement, not an arbitrary compiler decision.
2. **Choose the compiler/toolchain.** Use a JDK new enough to support the language and APIs the project needs, while checking whether the old target is still supported.
3. **Read the actual target list.** Run `javac --version` and `javac --help` from the exact executable.
4. **Prefer `--release`.** Use it to synchronize source language, class files, and platform APIs.
5. **Check external dependencies.** Each library must support the lowest runtime; `--release` does not automatically control the bytecode of all dependent JARs.
6. **Check bytecode.** Use `javap -verbose` to confirm the class file major version.
7. **Run tests on the lowest runtime.** Test unit, integration, service loading, reflection, and environment-dependent code paths.
8. **Record the toolchain in CI.** Log the JDK, compiler, release target, and build plugin versions so results can be reproduced.

## 13. Key principles to remember

- A compiler only generates targets for releases it supports; it cannot generate bytecode for a future Java release.
- The lowest limit varies by `javac` version and may be raised when old targets are removed.
- `-source` controls syntax; `-target` controls class file format; these two options do not by themselves restrict platform APIs.
- `--release` is the preferred choice from JDK 9 onward when cross-compilation is needed.
- `--release` only accepts a set of releases supported by the compiler; see `javac --help` for the exact list.
- Do not combine `--release` with `-source` or `-target`.
- Being able to read old class files does not mean the compiler can emit class files for every old target.
- Successful compilation does not replace testing on the lowest runtime and checking external dependencies.

## References

- [JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): introduces `--release` in JDK 9.
- [JEP 182 — Policy for Retiring javac -source and -target Options](https://openjdk.org/jeps/182): policy for retiring old source/target levels.
- [Oracle JDK 8 javac Tool Reference](https://docs.oracle.com/javase/8/docs/technotes/tools/unix/javac.html): source and target list for the JDK 8 compiler.
- [Oracle JDK 9 Preparing for Migration](https://docs.oracle.com/javase/9/migrate/): the "one plus three back" policy and the introduction of `--release`.
- [Oracle JDK 10 Migration Guide](https://docs.oracle.com/javase/10/migrate/toc.htm): source/target and release limits of JDK 10.
- [Oracle JDK 11 javac Tool Reference](https://docs.oracle.com/en/java/javase/11/tools/javac.html): `--release` targets supported by JDK 11.
- [Oracle JDK 17 Preparing for Migration](https://docs.oracle.com/en/java/javase/17/migrate/preparing-migration.html): source/target limits of JDK 17.
- [Oracle JDK 26 Preparing for Migration](https://docs.oracle.com/en/java/javase/26/migrate/preparing-migration.html): source/target policy and recommendation to use `--release` on JDK 26.
- [Oracle JDK 26 javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): syntax and limits of compiler options.
- [Oracle JDK 27 Preparing for Migration](https://docs.oracle.com/en/java/javase/27/migrate/preparing-migration.html): source/target limits of JDK 27.

## Conclusion

The target version supported by `javac` depends on the compiler version and compilation options. JDK 8 does not yet have `--release`; from JDK 9 onward, `--release` helps synchronize language rules, bytecode, and platform APIs. Older targets are gradually deprecated or removed, so check `javac --help` of the exact toolchain running. When building for multiple versions, combine `--release`, checking external dependencies, verifying class files, and running tests on the lowest runtime the product commits to supporting.
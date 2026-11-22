# Testing `--release`, Preview, and Supported JDK Versions in Java

## 1. The Problem to Solve

A project may be **compiled with JDK 17** while promising support for the **Java 11 runtime**; another project uses a **Java 17 preview** feature and therefore runs only with a very specific configuration. If testing only runs `javac` once on a developer's machine, you do not know whether that compatibility promise holds true.

This lesson focuses on three questions that must be verified separately:

1. **Compiling for the target Java version:** Does `javac --release N` reject syntax/APIs newer than Java N and generate class files at the right level?
2. **Preview:** Is code that depends on a preview feature compiled with the exact JDK that released that feature, using `--enable-preview`, and run with the right runtime/flag?
3. **Supported JDK matrix:** Does the artifact actually run and pass tests on **the JDK versions that the project claims to support**?

Two conclusions are often confused:

- “A successful build on JDK 17 with `--release 11`” **does not prove** that the program has been tested on JDK 11.
- “Running preview on JDK 17” **does not prove** that the preview class runs on JDK 21 or on any newer JDK.

To get solid evidence, you need to combine **compile tests**, **runtime tests**, **negative tests** (verifying cases that must be rejected), and reproducible toolchain information.

## 2. Distinguishing Four Version Numbers

| Concept | Meaning | How to check |
|---|---|---|
| **JDK running the compiler** | The actual `javac` installation in use, e.g., JDK 17 | `javac -version` and executable path |
| **`--release N`** | The Java SE language level, standard APIs, and class file level that the compiler must target | `javac --release N`, negative compile test |
| **JDK running the program** | The actual JVM loading classes and executing code | `java -version`, running smoke/integration tests |
| **JDK running the build tool** | The JVM running Gradle/Maven or its daemon, which may differ from the compiler and the test JVM | `./gradlew -version`, `mvn -version`, toolchain configuration |

For example: the Gradle daemon may run on JDK 21, the JavaCompile task may use a JDK 17 toolchain with `options.release = 11`, and a dedicated `Test` task may use a Java 11 launcher. These are **four roles**, even though some may share the same version in a simple project.

**What does “supporting JDK 11” mean?** Define it up front: must the project compile for Java 11, run unit/integration tests on JDK 11, and have compatible dependencies/application; or does it only need a *library* generating bytecode that can be loaded on Java 11? Testing goals differ depending on the product commitment.

## 3. What Does `--release` Actually Guarantee?

`javac --release N` instructs the compiler to be compatible with Java SE version N across three main dimensions:

- **Language rules:** reject Java syntax or features introduced after release N.
- **Available Java SE APIs:** prevent source code from mistakenly calling standard APIs newer than Java N, even when using a newer JDK compiler.
- **Class file level:** generate bytecode in the format for release N.

For example, running JDK 17's `javac` with `--release 11` is a form of **cross-compilation** for Java 11. It does not require a JDK 11 compiler on the machine, provided the current compiler supports release 11.

However, `--release` **does not** by itself prove that:

- Third-party dependencies and native libraries support Java 11.
- Runtime paths involving reflection, service loading, JNI, networking, or OS dependencies work properly.
- The output has actually been tested on JVM 11.
- Any arbitrary Java release is supported by every compiler version. `javac` only supports a set of releases, may drop targets that are too old, and cannot compile for a release **newer than the compiler**.

Run:

```bash
javac -version
javac --help
```

Check the **Supported releases** line in the `javac --help` output of the exact JDK in use, instead of assuming every JDK accepts `--release 8`, `11`, `17`, `21`.

### 3.1. Why Aren't `-source` / `-target` Enough?

`-source 8` checks Java 8 grammar; `-target 8` requests the corresponding class file format. When using a newer compiler **without** configuring an appropriate bootclasspath, these two flags do not reliably block calls to standard APIs introduced only in newer Java versions.

The following example uses ordinary Java 8 syntax, yet the `String.isBlank()` method has existed only since Java 11:

**File `ApiGate.java`:**

```java
public class ApiGate {
    public static void main(String[] args) {
        System.out.println(" ".isBlank());
    }
}
```

On **JDK 17**, run in the directory containing the file:

```bash
javac --release 8 -d out8 ApiGate.java
```

**Expected:** compilation **fails** because the `String.isBlank()` API does not exist in Java SE 8. Do not test by requiring stderr to match the compiler's exact English wording; check the non-zero status and the corresponding cause.

Still on JDK 17, run:

```bash
javac --release 11 -d out11 ApiGate.java
java -cp out11 ApiGate
```

**Stdout of the `java` command:**

```text
true
```

If compiled with `-source 8 -target 8` **on JDK 17** without using `--release` or a matching bootclasspath, the compiler may accept the `isBlank()` call even though the target bytecode is Java 8. Running that bytecode on Java 8 will fail to find the method at runtime, typically leading to `NoSuchMethodError`. This is a concrete example of why you must test the **API gate**, rather than merely reading the class file's major version.

You also need to test **syntax**: a file declaring `record Item(String name) {}` is valid in Java 17, but must be rejected by `--release 11` because records only became a standard feature in Java 16. `--release` guards both the language and the standard APIs.

### 3.2. Compiler Flags Cannot Be Combined Arbitrarily

`--release` cannot be used together with `-source` / `-target` in a normal `javac` invocation: they are competing ways of setting the compilation level. It also restricts certain options that interfere with the module system's APIs, such as exporting unexported packages of a system module in some cases. You should not “patch” compilation errors under `--release` by opening access to JDK internal APIs.

If you need a newer compiler targeting an older runtime, prefer a **deterministic toolchain/compiler + `--release N`** and let the build tool generate the proper arguments.

## 4. Command-Line Testing: Positive and Negative Cases

A good test checks not only that valid source compiles, but also that the compiler **correctly rejects** source that exceeds the contract.

| Case | JDK compiler | Flags | Fixture | Expected |
|---|---:|---|---|---|
| A | 17 | `--release 8` | `ApiGate.java` calling `String.isBlank()` | **FAIL**, API does not exist in Java 8 yet |
| B | 17 | `--release 11` | Same fixture | **PASS** |
| C | 17 | `--release 11` | File using `record` | **FAIL**, syntax does not exist in Java 11 yet |
| D | 17 | `--release 17` | File using `record` | **PASS** |
| E | 17 | `--release 21` | Any valid Java file | **FAIL**, compiler 17 does not support future release 21 |

Case E fails because of an **invalid release configuration**, which differs from a syntax error in the fixture. The test suite must distinguish between **no appropriate toolchain available** and **source rejected as expected**.

### 4.1. POSIX Shell Checking Status Instead of Text

On macOS/Linux with JDK 17, when fixture `ApiGate.java` exists:

```bash
if javac --release 8 -d out8 ApiGate.java; then
    echo "FAIL: Java 8 unexpectedly accepted the API"
    exit 1
else
    echo "PASS: Java 8 target rejected the API"
fi

javac --release 11 -d out11 ApiGate.java
java -cp out11 ApiGate
```

**Stdout produced by the commands/script**, if the case behaves correctly:

```text
PASS: Java 8 target rejected the API
true
```

`javac` may still print diagnostics to stderr. Even though the illustrative script accepts a non-zero code from the first case, in a **real test runner** you must ensure the `javac` executable can run and the fixture exists; otherwise, a “command not found” error would also trigger the `else` branch and produce a false positive.

In PowerShell, read `$LASTEXITCODE` **immediately after `javac`**, then compare it against 0. Avoid making tests depend on the exact phrase `cannot find symbol` or a specific file path.

### 4.2. Reading the Class File Major Version

You can inspect the class file generated by `--release 11`:

```bash
javap -verbose out11/ApiGate.class
```

Look for `major version: 55`. Some common milestones:

| Java release | Major version of a normal class file |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

This milestone checks the **bytecode format** and cannot replace API compatibility testing. As in the `-source/-target` example, a matching class file version does not mean all methods/libraries it calls actually exist on the older JVM.

## 5. Java 17+: Automating API Gate Testing with the Java Compiler API

Using `javax.tools.JavaCompiler` and `DiagnosticCollector` helps test compilation by **status and structured diagnostics**. You can test both `--release 8` and `--release 11` targets from the same JDK 17 without parsing the entire stderr output.

**File `ReleaseMatrixCheck.java` — standalone runnable Java 17 program:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class ReleaseMatrixCheck {
    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }

        Path root = Files.createTempDirectory("release-matrix-");
        Path source = root.resolve("ApiGate.java");

        Files.writeString(source,
                "public class ApiGate {"
                + " public static void main(String[] args) {"
                + " System.out.println(\" \".isBlank());"
                + " }"
                + "}");

        boolean on8 = compile(compiler, source, root, "8");
        boolean on11 = compile(compiler, source, root, "11");

        if (on8 || !on11) {
            throw new AssertionError(
                    "Expected --release 8 to reject and 11 to accept");
        }

        System.out.println("release 8 accepted: " + on8);
        System.out.println("release 11 accepted: " + on11);
    }

    private static boolean compile(
            JavaCompiler compiler,
            Path source,
            Path root,
            String release) throws IOException {

        Path out = Files.createDirectories(
                root.resolve("classes-" + release));
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             diagnostics, null, null)) {

            Iterable<? extends JavaFileObject> units =
                    files.getJavaFileObjects(source.toFile());

            Boolean success = compiler.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", release,
                            "-d", out.toString(),
                            "-proc:none"),
                    null,
                    units
            ).call();

            boolean hasError = diagnostics.getDiagnostics()
                    .stream()
                    .anyMatch(d -> d.getKind()
                            == Diagnostic.Kind.ERROR);

            if (Boolean.FALSE.equals(success) && !hasError) {
                throw new AssertionError(
                        "Compilation failed without ERROR diagnostic");
            }
            return Boolean.TRUE.equals(success);
        }
    }
}
```

Compile and run with **JDK 17** (or a newer JDK that still supports both releases 8 and 11; check `javac --help`):

```bash
javac ReleaseMatrixCheck.java
java ReleaseMatrixCheck
```

**Stdout when running with JDK 17:**

```text
release 8 accepted: false
release 11 accepted: true
```

The program creates temporary source and output in the system directory to run two independent compilations. The fact that it does not automatically delete the temporary directory **does not affect the test logic**, though in a real test suite you should add safe cleanup (e.g., JUnit `@TempDir`) to avoid accumulating files when running frequently.

You need to distinguish:

- The `--release 8` case fails because `isBlank()` does not belong to the Java 8 API.
- The `--release 11` case succeeds.
- Both only test **compilation**; neither has run the class with a JDK 8/11 runtime yet.
- The example **does not** invoke the `javac` executable directly by path, using the system compiler of the JDK running the program instead. You must pin the JDK running `ReleaseMatrixCheck` so results are reproducible.

Do not use a test like the one above to claim “support for all JDK versions”; it is a small part of a compatibility test suite.

## 6. What Is Preview and Why Is It Special?

Java introduces certain language, VM, or API features in **preview** form so users can try them before they are modified, finalized, or removed. Preview is specified **per Java SE release**. A feature may have different syntax across preview rounds; once finalized, how it is enabled and its compatibility rules may change.

Points to remember:

1. Preview features are not enabled by default like standard features.
2. When compiling source using a **preview language feature**, you need `--enable-preview` **and** `--release N` or `-source N` where N is the **current version of the compiler itself**.
3. When running a class file that depends on a preview feature of release N, you need a JVM of **specifically Java SE N** together with `java --enable-preview`.
4. A preview class with minor version **65535** is tied to that release's major version. A JVM of another release **cannot** load a class depending on that preview merely by adding `--enable-preview`.
5. A feature becoming standard in a newer Java release does not automatically turn an old preview class into a stable class; you must recompile the source according to the target specification/version.

**Do not understand `--enable-preview` as a flag to “enable all new features of other Java versions.”** For example, a JDK 17 `javac` cannot use `--enable-preview --release 21` to understand Java 21 syntax; nor can it use release 17 preview features when compiling for target `--release 11`.

### 6.1. A Practical Preview Example in Java 17

**Pattern matching for switch** is a preview feature in **Java 17** (JEP 406). The snippet below must be run with **JDK 17**; do not assume another compiler version still treats that syntax as preview under the same rules.

**File `PreviewSwitch.java`:**

```java
public class PreviewSwitch {
    static String describe(Object value) {
        return switch (value) {
            case Integer number -> "int: " + number;
            case String text -> "string: " + text;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(7));
    }
}
```

**On JDK 17**, compile and run:

```bash
javac --enable-preview --release 17 -d out-preview PreviewSwitch.java
java --enable-preview -cp out-preview PreviewSwitch
```

**Expected stdout:**

```text
string: Java
int: 7
```

The compiler may print preview warning notes on **stderr**, though you do not need to compare that message verbatim when a test only wants to prove that the code works.

Two important negative tests:

```bash
# On JDK 17: missing --enable-preview, expected compilation FAIL.
javac --release 17 -d out-no-preview PreviewSwitch.java

# On JDK 17: preview cannot be used to target release 11, expected FAIL.
javac --enable-preview --release 11 -d out-old-preview PreviewSwitch.java
```

The comment lines describe **expectations**, not part of `javac`'s syntax. Before running each experiment, make sure `javac -version` returns 17. On newer compilers, pattern switch may already be a standard feature and the “missing preview must fail” test no longer carries the same meaning. **Preview negative tests must be tied to a specific release.**

### 6.2. Testing at Runtime

If `PreviewSwitch.class` was compiled using JDK 17 with preview:

```bash
# JDK 17: missing runtime flag, expected program failure to load class.
java -cp out-preview PreviewSwitch

# JDK 17: flag enabled, expected successful run.
java --enable-preview -cp out-preview PreviewSwitch
```

If you try to run a Java 17 preview class on **JDK 21**, even `java --enable-preview` does not turn a JDK 17 preview class into a Java 21 artifact. If you want to use Java 21, **recompile the source** with a Java 21 compiler and test against Java 21's specification.

Read the class version:

```bash
javap -verbose out-preview/PreviewSwitch.class
```

For a class depending on a Java 17 preview feature, expect `major version: 61` and `minor version: 65535`. A class that does not use preview may have minor version 0 even if the compiler ran with `--enable-preview`; do not conclude that merely passing the flag turns every class into a preview class.

## 7. Designing a JDK Matrix: Compile Target Differs from Runtime Target

The matrix should start from the **project's support policy**. For example, a library promises to run on Java **11, 17, and 21** while targeting Java **11** at compile time:

| Run | Compiler JDK | `--release` | Runtime JDK | What it proves |
|---|---:|---:|---:|---|
| 1 | 17 | 11 | 11 | Compiles compatibly for Java 11 and runs/tests on the oldest supported JVM |
| 2 | 17 | 11 | 17 | Same artifact operates on runtime 17 |
| 3 | 17 | 11 | 21 | Same artifact operates on runtime 21 |
| 4 (additional) | 21 | 11 | 11 | Newer compiler still produces output compatible with the 11 baseline |
| 5 (additional) | 21 | 11 | 21 | Tests interaction between newer toolchain/compiler and newer runtime |

The matrix is an **example**, not a claim that all projects must support these three versions. If the compiler JDK no longer supports the target release, you must use an appropriate toolchain or intentionally update the policy.

**Key takeaway:** Build **one artifact at the lowest compatibility level**, then run **that same artifact** on the supported runtime JVMs. If you rebuild separately on each JDK with different implicit targets, you are testing different artifacts and may miss compatibility bugs in the actual distribution.

An ordinary Java 21 class has major version 65 and will not run on JVM 17 (max major 61), even if the source code uses no Java 21 APIs. That is why **runtime testing does not replace setting `--release` properly**, and a compile target does not replace runtime testing.

### 7.1. Checklist for Each Cell in the Matrix

For each chosen compiler/runtime pair, record:

- Actual version and vendor/compiler (`javac -version`, `java -version`), not just the intended `JAVA_HOME`.
- Source set, `--release`, compiler arguments, dependency versions, and artifact hash.
- Compilation status, error count, and necessary diagnostics.
- Program/test runner exit code, test pass/fail/skip counts, and linkage/runtime errors.
- Whether preview is used; if so, flags for both the compiler **and** runtime, plus the exact release.
- OS and architecture if the project has JNI, file encoding, or OS-specific dependencies.

If there are Java-version-dependent code paths (`Runtime.version()`, multi-release JAR, custom service providers), tests need to check **behavior** on each JVM, not just “main method exit 0”.

### 7.2. Failure Cases to Include

| Expected failure | Test case |
|---|---|
| Calling standard API newer than target | Older `--release` must reject |
| Using syntax newer than target | Older `--release` must reject |
| Compiler too old for target | Report configuration/toolchain error; do not count as a source language failure |
| Runtime older than major version | Runtime must reject newer class |
| Runtime missing preview flag | Runtime must reject preview class of its own release |
| Using preview class of release N on JVM M other than N | Runtime must reject class depending on preview |
| New runtime and external API incompatible | Tests/integration tests must detect runtime error, not infer solely from `--release` |
| Build tool runs right JDK but tests run wrong JDK | Check the task's Java launcher and toolchain logs |

**Each expected failure should be defined as “test passes when the compiler/runtime rejects for the right reason.”** An error due to a missing file, Java executable failing to launch, or a missing dependency cache must be classified as *infrastructure*, not a pass.

## 8. Gradle Integration: Pinning Compiler and Release

With the Gradle Java plugin, you can use a toolchain to choose the compiling JDK, combined with `options.release` to set the compatibility level.

**Fragment `build.gradle` (Groovy DSL):**

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
    options.release = 11
}
```

This configuration requests the JDK 17 compiler while generating classes targeting Java 11. It **does not configure tests to run on Java 11**: the default test task may use the JDK 17 toolchain's Java launcher.

Inspection commands:

```bash
./gradlew -version
./gradlew javaToolchains
./gradlew clean test --info
```

Windows uses `gradlew.bat`. `javaToolchains` provides information about JDKs discovered by Gradle; `--info` helps observe which tool is selected and which tasks run.

If tests must run on JDK 11, you can add a Java Test task using launcher 11:

```groovy
// Fragment extending build.gradle for a project with a test source set.
// With JUnit Jupiter, appropriate dependencies and useJUnitPlatform() are required.
tasks.register('testOn11', Test) {
    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
    useJUnitPlatform()
}
```

This is an **illustrative configuration**; to run it for real, JDK 11 must be available to Gradle toolchains along with appropriate JUnit/test dependencies. If a library in the test runtime requires Java 17, the task above can still fail even though the application's classes set `--release 11`. That is a useful compatibility bug caught by the runtime matrix.

### 8.1. Gradle and Preview

When intentionally using preview **on JDK 17**, both the compile task and the test JVM need the corresponding flags:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.compilerArgs.add('--enable-preview')
}

tasks.withType(Test).configureEach {
    jvmArgs '--enable-preview'
}
```

If the project runs via a `JavaExec` task or is packaged as a JAR for users to run from the terminal, that runtime must also have `--enable-preview`. Enabling it only on `Test` does not make a released JAR know to turn preview on automatically.

If the project needs a Java 11 baseline, do not set `options.release = 11` and then enable JDK 17 preview. Separate the preview experimental module/branch from the artifact promised to support JDK 11.

### 8.2. Distinguishing the JVM Running Gradle from the Toolchain JDK

`./gradlew -version` displays the environment running Gradle, which **is not always the compiler of `compileJava`** when a toolchain has been configured. You should inspect `javaToolchains` and task `--info`. When a build fails because the toolchain JDK is unavailable, do not change `--release` to force it through: you need to install/configure a valid toolchain or an appropriate provisioning policy.

Gradle maintains a Gradle ↔ JDK version matrix: a JDK may be supported for toolchain compilation while **not yet supported for running Gradle itself** at a specific version. When upgrading the JDK, check the compatibility matrix of the Gradle Wrapper version in use.

## 9. Maven Integration: Target Release and Preview

With the Maven Compiler Plugin, you can specify the release in `pom.xml`. Example **fragment for Maven 3 and Compiler Plugin 3.x**:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
```

The Maven 3 plugin supports the `release` option, though exact behavior may depend on the compiler plugin and JDK versions. Maven Compiler Plugin 3.13.0+ also includes a mechanism to translate `release` into `source/target` when running a JDK 8 compiler; **that translation does not guarantee an API gate as strict as a real `javac --release` on JDK 9+**. For this test, prefer a newer JDK with native `--release`.

Check the environment:

```bash
mvn -version
mvn clean test
```

`mvn -version` typically reports the JDK running Maven. To check the JDK used for compilation when special toolchains/plugin configurations exist, inspect the compiler plugin output and actual configuration. The Maven reactor or Surefire still needs the right JVM environment to test supported runtimes.

### 9.1. Maven and Preview

Maven Compiler Plugin 3.x has `enablePreview` (since 3.10.1), for example with JDK 17:

```xml
<!-- Configuration fragment in pom.xml, not a complete POM. -->
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <maven.compiler.enablePreview>true</maven.compiler.enablePreview>
</properties>
```

**A compiler flag does not automatically enable the flag on the test JVM.** With Maven Surefire, you need to configure `argLine` appropriately, for example:

```xml
<!-- Fragment belonging to maven-surefire-plugin configuration. -->
<configuration>
    <argLine>--enable-preview</argLine>
</configuration>
```

If the project already uses `argLine` for JaCoCo or other JVM arguments, you must **merge** with the existing configuration instead of overwriting it. Preview when running the application outside Surefire also needs to be passed to `java`.

Maven 4/Compiler Plugin 4.x has changes in how sources and targetVersion are declared, so do not mechanically copy Maven 3 configuration into every project. When exact details are needed, consult the documentation for the plugin version in use.

## 10. Organizing Practical CI Testing

For a project requiring Java 11/17/21 runtimes and targeting `--release 11` in its deliverable, the pipeline can be divided into:

**A. Checking the compiler contract.** Run the API gate fixture with a pinned compiler (e.g., JDK 17), verifying that Java 8 is rejected and Java 11 is accepted. Check the class major version and run the baseline unit tests.

**B. Building the artifact once.** Produce the JAR with `--release 11`, store the artifact and its fingerprint/hash. If build reproducibility is needed, lock plugins/dependencies and ensure stable inputs.

**C. Runtime matrix.** Run smoke/integration tests with the same artifact on JVMs 11, 17, and 21 (the JDKs included in the commitment). Do not recompile into separate artifacts per runtime and treat that as the same test.

**D. Additional compiler matrix.** You can re-run source compilation with JDK 21 `--release 11` to detect warnings, processors, or compiler changes when upgrading the toolchain. Explicitly note this is a **different artifact/compile job** from the runtime matrix in step C.

**E. Separate preview lane.** If the project has an experimental preview branch/module, pin the exact JDK release, enable flags, test the missing-flag case as well, and do not claim portability to another JDK for the preview class file.

An easy-to-read CI results table:

| Job | Compiler | Target | Runtime | Expected |
|---|---|---|---|---|
| `compat-compile` | JDK 17 | 11 | — | PASS, bytecode major 55 |
| `api-negative` | JDK 17 | 8 | — | Expected FAIL for new API fixture |
| `runtime-11` | built artifact | 11 | 11 | PASS |
| `runtime-17` | same artifact | 11 | 17 | PASS |
| `runtime-21` | same artifact | 11 | 21 | PASS |
| `preview-17` | JDK 17 | 17 + preview | 17 + preview | PASS |
| `preview-no-flag` | JDK 17 | 17 + preview | 17 without preview | Expected runtime FAIL |

If not all required JDKs are installed on the runner, use a matrix/container/toolchain to supply the exact versions, instead of silently skipping part of the matrix and claiming full coverage.

### 10.1. Distinguishing Compatibility from Support Policy

A Java 11 class file can be loaded by a newer JVM under the JVM's backward compatibility rules, yet the product may still fail due to dependencies, changed APIs, module access errors, native libraries, or different behavior. Conversely, a dependency requiring Java 17 makes the application **not** support JDK 11 even if the application's own source compiles with `--release 11`.

**Support commitments** must be verified by real tests across **all target runtimes** and with the actual dependency/distribution versions, rather than inferred solely from the class major version.

## 11. How to Verify Failures for the Right Reason

There are three kinds of failures to distinguish:

| Type | Example | How to confirm |
|---|---|---|
| **Source rejected as expected** | `String.isBlank()` with `--release 8` | Compiler ran, valid source used as fixture, appropriate `ERROR` diagnostic |
| **Wrong configuration/toolchain** | JDK 17 given `--release 21`, missing JDK 11 launcher | Classify as infrastructure/config failure; do not pass as a negative source test |
| **Incompatible runtime** | Running major 65 class on JVM 17 or missing preview flag | Appropriate artifact, Java launcher, exit code, and exception type recorded |

Do not test by comparing verbatim phrases like `invalid source release`, `UnsupportedClassVersionError: ...`, or the entire stderr. Wording and formatting vary by JDK, vendor, and locale. You can assert **status** and, when the test truly needs it, the **exception/diagnostic kind** or structured information.

Common errors:

- **`UnsupportedClassVersionError`:** the JVM received a class file with an unsupported version or a preview class without valid loading conditions. Check major/minor versions and the actual JVM.
- **`NoSuchMethodError` / `NoClassDefFoundError`:** may result from an incompatible runtime API/dependency even when the class file loads.
- **`invalid source release` / `release version ... not supported`:** the compiler does not accept the target release; check the actual compiler rather than assuming a source bug.
- **Preview feature disabled:** source/bytecode depends on preview, yet the compiler or runtime lacks the appropriate flag.

Before concluding a language bug, confirm that `java` and `javac` come from the expected toolchain paths; on a machine with multiple JDKs, they can easily come from different installations.

## 12. Hands-On Exercises

### Exercise 1 — API Boundary

Using `ApiGate.java` from section 3, run `javac --release 8`, `--release 11`, and `--release 17` with the JDK 17 compiler. Record pass/fail, class major version, and main diagnostics.

**Expected answer:** `--release 8` FAIL; 11 and 17 PASS; class compiled for 11 has major 55, and for 17 major 61. Do not confuse failures from a missing file or calling the wrong executable with expected API rejection.

### Exercise 2 — Syntax Boundary

Create `Item.java`:

```java
public record Item(String name) {
}
```

Compile under `--release 11` and `--release 17` with the JDK 17 compiler. Why do they differ?

**Expected answer:** Java 11 does not have records as a standard language feature so it is rejected; Java 17 supports records officially. This is a syntax barrier, distinct from an API barrier such as `String.isBlank()`.

### Exercise 3 — Preview Lane

Use `PreviewSwitch.java` with JDK 17. Try (1) compiling without preview, (2) compiling with preview and running without the flag, (3) compiling and running with the flag, (4) trying the JDK 17 compiler with `--enable-preview --release 11`.

**Expected answer:** (1) FAIL, (2) runtime FAIL, (3) PASS with stdout as in section 6, (4) FAIL because JDK 17 preview cannot target Java 11.

### Exercise 4 — Runtime Matrix

Library `utils.jar` is compiled on JDK 17 with `--release 11`. The team runs unit tests with JDK 17 and claims Java 11 support. What evidence is still missing?

**Expected answer:** Running **the exact distributed artifact** on JVM 11 with the corresponding runtime dependencies, including necessary smoke/integration tests. Compiling for target 11 alone does not test every runtime branch or dependency.

### Exercise 5 — Finding a CI Configuration Bug

CI has jobs `JDK 17 -> --release 11` PASS and `JDK 21 -> --release 21` PASS. However, the released artifact is built with JDK 21 target 21, and Java 17 users encounter class-loading errors. Why?

**Expected answer:** The target-21 artifact carries class major version 65, higher than JVM 17 supports. If Java 17 is promised, the released artifact must be built with the corresponding minimum target and tested on runtime 17. A separate job compiling for target 11 does not alter the classes of the released artifact.

## 13. Common Misconceptions

**“`--release` is a way to install a JDK.”** False: it is a compiler option. It does not download a JDK, replace the JVM running tools/tests, or make an older `javac` understand future Java syntax.

**“Just having the right `-target` major version is enough.”** Insufficient: classes can link to Java SE APIs newer than the target if compiled on a newer JDK without controlling bootstrap APIs.

**“With `--release 11`, there is no need to run tests on Java 11.”** False: release checks the compile-time standard platform, not runtime dependencies and behavior.

**“`--enable-preview` lets preview classes run on any newer JDK.”** False: preview class files depend on a specific release. You must use the same Java SE release and runtime flag, or recompile the source for the newer release.

**“Code that was once preview always needs the preview flag.”** False: the feature may have become standard in a later release. You must evaluate against the Java release being used.

**“A negative test passes when the command returns non-zero.”** Insufficient: non-zero can be caused by a missing tool, missing file, or invalid flags. Check the cause matching the fixture.

**“If the CI machine has JDK 11, 17, 21, tests automatically run on all three.”** False: you must explicitly configure the right launcher for each job and log the running version.

**“Every Java version can use `--release 8`.”** Do not assume that: each `javac` has a list of supported releases; check `javac --help`.

## 14. Checklist Before Claiming Support for a JDK

- [ ] Have a list of JDK/runtime versions actually committed to support.
- [ ] Build explicitly records the compiler/toolchain version and `--release`.
- [ ] Check `javac --help` to confirm the release target is supported by the compiler.
- [ ] Include valid-source positive tests and negative tests for APIs/syntax exceeding the target.
- [ ] Do not confuse `-source/-target` with the API compatibility of `--release`.
- [ ] Check class major/minor versions when needed, understanding the limits of this metric.
- [ ] Artifact is tested on the lowest runtime and all runtimes promised for support.
- [ ] Runtime dependencies are also compatible with the lowest JVM.
- [ ] Preview lane, if any, locks the exact JDK release, compile/runtime flags, and tests expected failures.
- [ ] Logs distinguish whether failures are due to source, toolchain, or runtime.
- [ ] CI actually executes each matrix cell and does not automatically pass “skip”.
- [ ] When upgrading a JDK or Gradle/Maven plugin, re-run both the compiler and runtime matrices.

## Official Documentation

- [Oracle Java SE — `javac` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Oracle Java SE 17 — Preview features](https://docs.oracle.com/en/java/javase/17/language/preview-language-and-vm-features.html)
- [OpenJDK — JEP 406: Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406)
- [OpenJDK — JEP 12: Preview Features](https://openjdk.org/jeps/12)
- [Gradle — Building Java & JVM projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Maven Compiler Plugin — Setting `--release`](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Maven Compiler Plugin — Compiler parameters](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)

When choosing a specific matrix, prioritize your project's support policy and the documentation for the **exact version** of the JDK, Gradle Wrapper, or Maven Compiler Plugin being deployed. Compatibility testing is valuable when it proves the **source/API boundary, class file boundary, and runtime behavior** of the actual artifact.
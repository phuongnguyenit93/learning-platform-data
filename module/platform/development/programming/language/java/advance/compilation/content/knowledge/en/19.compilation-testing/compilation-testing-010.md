# Hands-On Lab: From Configuring `javac` to Automated Build Verification

> **Scope:** Java Advance – compilation → Compilation Testing. This lab guides you through building a small Java project with **plain `javac`**, testing real execution output, checking compilation errors with the **Java Compiler API**, comparing **bytecode/JAR** across two builds, and wiring the entire workflow into CI. All Java examples use Java 17 syntax/APIs; **JDK 17 or later** is required to run.

## 1. Expected Outcomes

After this lesson, you can:

1. Select a compiler and pin `--release`, encoding, annotation processing, classpath, and output directory.
2. Create a working **positive fixture** and an intentionally mistyped **negative fixture**; never confuse “compilation errored” with “test succeeded”.
3. Automatically verify **class-file major version 61** (Java 17), execution result, and diagnostic kind/location.
4. Compile twice into **two independent directories** to compare `.class` bytes.
5. Package a test JAR with fixed metadata, compare JAR contents byte-for-byte, and accurately state the limits of the verification.
6. Run everything in a single script and integrate it into CI; a single failed condition makes the job fail.

**Acceptance criterion:** the test command outputs `BUILD AUDIT: PASS` with exit code `0`; editing the source to violate an assumption must stop the script or throw `AssertionError`. Only after checking both pass and fail directions can you trust the test suite.

### 1.1. Why Verify Both the Build and Behavior?

`javac` returning exit code `0` means compilation succeeded, yet does not prove the Java class has the right bytecode target, prints the expected stdout, or yields a reproducible JAR. Conversely, an intentionally invalid source must fail compilation **for the right reason**. We use multiple verification layers because no single check covers everything.

```text
Source / JDK version / configuration
                 │
         javac --release 17
                 │
        ┌────────┴─────────┐
        ▼                  ▼
   build/a/classes    build/b/classes
        │                  │
        └───── byte equality ─────┐
                                  │
           run demo.Hello ────────┤
                                  ├─► BuildAudit ─► PASS / FAIL
         class version = 61 ──────┤
                                  │
     JAR with fixed metadata ─────┤
                                  │
       negative compile ERROR ────┘
```

This is a **local verification**: two builds with the same JDK on one machine producing identical bytes is solid evidence for a small fixture. Independent reproducibility across different machines additionally requires pinning the compiler, dependencies, and all generators.

## 2. Preparing the Environment

You need a **full JDK** containing the `java` and `javac` commands and the `jdk.compiler` module; not merely a minimal Java runtime. Check:

```bash
java -version
javac -version
```

The commands print the machine's actual versions; **there is no fixed stdout** in this lesson. Make sure `java` and `javac` come from the intended toolchain; IDEs, shells, and CI may pick different JDKs.

In the lab we use:

- `--release 17`: restricts language, class-file target, and Java platform APIs to Java 17.
- `-encoding UTF-8`: interprets `.java` file bytes using the right charset.
- `-proc:none`: disables annotation processors to prevent unexpected codegen; appropriate since the lesson uses no processors.
- `-Xlint:all`: enables `javac` warning categories for positive sources. If a “warnings are errors” policy is desired, you can add `-Werror` after checking the fixture.
- `-d <dir>`: separates class files from source and across build runs.

**Important limitation:** `--release 17` **does not guarantee** that two JDK 17/21/24 compilers will always emit identical bytes; it pins language/API compatibility levels, not compiler implementations/patches. For release builds, pin the JDK distribution/vendor/patch and build tool as well.

## 3. Creating a Minimal Project

Structure to create manually:

```text
javac-build-lab/
├── src/
│   ├── main/
│   │   └── java/
│   │       └── demo/
│   │           └── Hello.java
│   └── test/
│       ├── java/
│       │   └── BuildAudit.java
│       └── fixtures/
│           └── demo/
│               └── BadHello.java
├── verify.sh
└── build/                         # Generated when run, do not commit
```

All `.java` files are saved as **UTF-8 without BOM**. `BuildAudit.java` sits in the default package to simplify running the lab; in real applications, use an explicit package for test code. `build/` is an output directory, not a source of truth.

### 3.1. Positive Source

Create **`src/main/java/demo/Hello.java`**:

```java
package demo;

public class Hello {
    public static void main(String[] args) {
        // Comment with diacritics: tiếng Việt, cà phê.
        System.out.println("Hello from Java 17");
    }
}
```

The stdout string intentionally uses ASCII for easy comparison across Windows, Linux, and CI; the comment containing Vietnamese forces saving/reading the source in proper UTF-8. Because the source declares package `demo`, the class output must be `demo/Hello.class` under `-d`.

### 3.2. Negative Source: Intentional Error

Create **`src/test/fixtures/demo/BadHello.java`**:

```java
package demo;
public class BadHello {
    public static void main(String[] args) {
        int count = "not a number";
    }
}
```

Line 4 assigns a `String` to an `int`, so `javac` must reject it. The test does not assert the verbatim error message (which can change with compiler and locale), checking instead for `Diagnostic.Kind.ERROR` on line 4, a valid column, and the right source.

**Do not** place `BadHello.java` in `src/main/java`: if you compile all regular sources together, the negative fixture will break the positive build too, preventing the lab from separating the two branches.

## 4. Running `javac` Manually and Understanding Each Flag

From the root directory `javac-build-lab/`, in Bash:

```bash
mkdir -p build/a/classes build/b/classes
javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/a/classes src/main/java/demo/Hello.java

java -cp build/a/classes demo.Hello
```

**Stdout of the `java` command:**

```text
Hello from Java 17
```

On success, `javac` normally prints nothing and returns exit code `0`. When source has errors, `javac` normally prints diagnostics to stderr and returns a non-zero exit code. Do not write scripts relying on grepping verbatim stderr when you can rely on exit codes and the Compiler API.

Create a second independent output:

```bash
javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/b/classes src/main/java/demo/Hello.java
```

The two compilations **do not share an output directory**; that way one pass does not accidentally read leftover classes from the other. This lab has only one source, making all inputs easy to identify. Larger projects must clean outputs, handle generated sources, and supply a complete classpath.

### 4.1. Inspecting Bytecode Structure

You can verify the class-file major version using standard tools:

```bash
javap -verbose -classpath build/a/classes demo.Hello
```

The long output will contain the line:

```text
major version: 61
```

Class-file major **61** corresponds to Java 17. If using `--release 21`, the target becomes major 65. Checking major version alone is insufficient to verify all semantics/APIs used by the program; `--release` and running tests form additional verification layers.

### 4.2. Why Not Package `jar` Immediately?

A JAR is a ZIP archive: entry timestamps, entry ordering, manifest, and packaging metadata can make **JAR SHA-256 hashes differ** even when `.class` files are byte-identical. Instead of relying on system timestamps, in the next step we create **a JAR containing a single class** and fix the entry's timestamp using the Java 17 API.

On newer JDKs, the `jar` tool supports `--date=TIMESTAMP`, yet **you should not assume this flag exists on JDK 17**. Because the lab requires running from JDK 17, packaging with `JarOutputStream` works consistently.

## 5. Writing the Automated Verification Suite `BuildAudit`

Create the following **`src/test/java/BuildAudit.java`**. This is a **complete standalone Java program** run from the project root after positive sources have been compiled into `build/a/classes` and `build/b/classes`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class BuildAudit {
    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static void packageClass(Path classes, Path jar)
            throws IOException {
        try (JarOutputStream output =
                 new JarOutputStream(Files.newOutputStream(jar))) {
            JarEntry entry = new JarEntry("demo/Hello.class");
            entry.setTime(1704067200000L); // 2024-01-01 UTC
            output.putNextEntry(entry);
            Files.copy(classes.resolve("demo/Hello.class"), output);
            output.closeEntry();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] firstClass = Files.readAllBytes(
                Path.of("build/a/classes/demo/Hello.class"));
        byte[] secondClass = Files.readAllBytes(
                Path.of("build/b/classes/demo/Hello.class"));
        require(Arrays.equals(firstClass, secondClass),
                "Class files differ");
        int major = ((firstClass[6] & 0xff) << 8)
                | (firstClass[7] & 0xff);
        require(major == 61, "Expected Java 17 class-file version 61");

        packageClass(Path.of("build/a/classes"), Path.of("build/a/app.jar"));
        packageClass(Path.of("build/b/classes"), Path.of("build/b/app.jar"));
        byte[] firstJar = Files.readAllBytes(Path.of("build/a/app.jar"));
        byte[] secondJar = Files.readAllBytes(Path.of("build/b/app.jar"));
        require(Arrays.equals(firstJar, secondJar), "JAR files differ");

        String javaExecutable = Path.of(
                System.getProperty("java.home"),
                "bin",
                System.getProperty("os.name").startsWith("Windows")
                        ? "java.exe" : "java").toString();
        Process process = new ProcessBuilder(
                javaExecutable, "-cp", "build/a/classes", "demo.Hello")
                .redirectErrorStream(true)
                .start();
        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).strip();
        int exit = process.waitFor();
        require(exit == 0, "Application exited with " + exit);
        require(output.equals("Hello from Java 17"),
                "Unexpected stdout: " + output);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        require(compiler != null, "System Java compiler is unavailable");
        Files.createDirectories(Path.of("build/negative/classes"));
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        boolean compiled;
        try (StandardJavaFileManager fileManager =
                 compiler.getStandardFileManager(
                         null, Locale.ROOT, StandardCharsets.UTF_8)) {
            Iterable<? extends JavaFileObject> files =
                    fileManager.getJavaFileObjectsFromPaths(
                            List.of(Path.of(
                                    "src/test/fixtures/demo/BadHello.java")));
            compiled = Boolean.TRUE.equals(compiler.getTask(
                    null, fileManager, diagnostics,
                    List.of("--release", "17", "-encoding", "UTF-8",
                            "-proc:none", "-d", "build/negative/classes"),
                    null, files).call());
        }

        require(!compiled, "Invalid source unexpectedly compiled");
        boolean expectedError = diagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR
                        && d.getLineNumber() == 4
                        && d.getColumnNumber() > 0
                        && d.getSource() != null
                        && d.getSource().toUri().getPath()
                                .endsWith("/BadHello.java"));
        require(expectedError, "Expected ERROR at BadHello.java:4");

        System.out.println("Class bytes: MATCH");
        System.out.println("Java 17 class version: 61");
        System.out.println("JAR bytes: MATCH");
        System.out.println("Application stdout: PASS");
        System.out.println("Negative compilation diagnostic: PASS");
        System.out.println("BUILD AUDIT: PASS");
    }
}
```

**Explanation of the main checks:**

- `Arrays.equals(firstClass, secondClass)` compares both `.class` files byte-for-byte, not merely file name or size. `major` reads two bytes at offsets 6–7 of the class file header in big-endian order; the class format starts with magic `CAFEBABE`. In this fixture, the bytecode needs to be Java 17 compatible.
- `packageClass` builds a JAR with a single fixed `JarEntry`, named `demo/Hello.class` and with timestamp `1704067200000L` (2024-01-01T00:00:00Z), without adding a dynamic manifest. With the same input bytes and JAR packer in the same environment, the JAR contents must match.
- `ProcessBuilder` runs the **real** application via the current JDK's `java` executable, checking exit code `0` and exact stdout. The example code prints ASCII to avoid discrepancies between console charsets and pipes on some systems.
- `ToolProvider.getSystemJavaCompiler()` obtains the internal compiler. `DiagnosticCollector` captures errors from the **negative fixture** instead of parsing stderr. Combining `!compiled` with `ERROR` at `BadHello.java:4` prevents the case where “compilation failed due to a setup error yet the test still passes”.
- `getSource()` can be `null` and `getLineNumber()/getColumnNumber()` can return `Diagnostic.NOPOS` for unpositioned errors. Therefore, position is compared only after filtering kind/source and checking a positive column.
- `require(...)` throws `AssertionError` when a mismatch is detected; the Java process terminates with a non-zero exit code, failing the CI script. A few `println` statements **do not replace** assertions.
- `StandardJavaFileManager` is closed after the compile pass. The negative fixture has its own output directory and does not run annotation processors.

In large applications, compare the entire list of `.class`/resources using normalized ordering and per-file hashes, not just a single class as in this lab.

### 5.1. Compiling and Running the Verification Suite

```bash
mkdir -p build/tools
javac --release 17 -encoding UTF-8 -proc:none \
  -d build/tools src/test/java/BuildAudit.java

java -cp build/tools BuildAudit
```

**Exact stdout when the project and environment are configured properly:**

```text
Class bytes: MATCH
Java 17 class version: 61
JAR bytes: MATCH
Application stdout: PASS
Negative compilation diagnostic: PASS
BUILD AUDIT: PASS
```

The example was run and produced those exact six lines with OpenJDK 24.0.2, compiler target Java 17. When an assertion fails, the error is printed via stack trace with a non-zero exit code; do not read `PASS` from an earlier build or ignore the exit code.

## 6. Automating Everything with `verify.sh`

Create **`verify.sh`** in the root directory; this script freshly compiles both sets of classes, compiles `BuildAudit`, and runs the test. It uses Bash (Linux/macOS or environments with Bash):

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p build/a/classes build/b/classes build/tools

javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/a/classes src/main/java/demo/Hello.java

javac --release 17 -encoding UTF-8 -proc:none -Xlint:all \
  -d build/b/classes src/main/java/demo/Hello.java

javac --release 17 -encoding UTF-8 -proc:none \
  -d build/tools src/test/java/BuildAudit.java

java -cp build/tools BuildAudit
```

Run:

```bash
bash verify.sh
```

`set -e` stops when a compile or Java command returns a non-zero code; `-u` reports undeclared variables; `pipefail` does not mask pipeline errors. The script `cd`s to its own location so relative paths in the harness stay stable.

**Note on clean builds:** the example only generates three `.class`/JAR files with fixed names, with each compile overwriting the `Hello` class; yet this is still a **smoke test** within the current workspace. To verify strict reproducibility, run two passes from **two clean checkouts** of the same commit or two fresh containers without reusing outputs and caches. In a real repo, dedicate a separate workspace for the lab and put `build/` in `.gitignore`.

### 6.1. Equivalent Execution on Windows PowerShell

In PowerShell, run the following lines one by one from the project root:

```powershell
New-Item -ItemType Directory -Force build/a/classes,build/b/classes,build/tools | Out-Null
javac --release 17 -encoding UTF-8 -proc:none -Xlint:all -d build/a/classes src/main/java/demo/Hello.java
if ($LASTEXITCODE -ne 0) { throw "compile a failed" }

javac --release 17 -encoding UTF-8 -proc:none -Xlint:all -d build/b/classes src/main/java/demo/Hello.java
if ($LASTEXITCODE -ne 0) { throw "compile b failed" }

javac --release 17 -encoding UTF-8 -proc:none -d build/tools src/test/java/BuildAudit.java
if ($LASTEXITCODE -ne 0) { throw "compile audit failed" }

java -cp build/tools BuildAudit
if ($LASTEXITCODE -ne 0) { throw "build audit failed" }
```

These are equivalent commands to run, not a separate `verify.ps1` file. With **Windows PowerShell 5.1**, writing Java sources via `Set-Content -Encoding UTF8` can add a UTF-8 BOM; use an editor configured for UTF-8 without BOM or `[System.IO.File]::WriteAllText(path, text, (New-Object System.Text.UTF8Encoding($false)))` to avoid `illegal character: '\ufeff'`.

### 6.2. Hashing to Compare or Publish Evidence

The harness compares bytes with `Arrays.equals`; when publishing artifacts, also record SHA-256:

```bash
sha256sum build/a/app.jar build/b/app.jar
```

In PowerShell:

```powershell
Get-FileHash build/a/app.jar -Algorithm SHA256
Get-FileHash build/b/app.jar -Algorithm SHA256
```

Both hash values **must match in a PASSing run**, yet there is no single universal fixed hash across all JDKs and environments. A hash alone does not prove a trustworthy source or library; you must clearly know the commit, toolchain, and corresponding inputs.

## 7. CI Integration: A Bad Build Must Fail the Job

Example GitHub Actions workflow, placed at **`.github/workflows/verify-javac.yml`** when adding the lab to a GitHub repository:

```yaml
name: Verify javac build

on:
  push:
  pull_request:

jobs:
  build-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Compile, run, verify diagnostics and artifacts
        run: bash verify.sh
```

The workflow is an **example configuration**, not yet executed on GitHub Actions in this lesson. If the repository requires supply-chain protection, pin actions by an approved **commit SHA**, use a runner image/toolchain with provenance, and avoid relying on floating tags. `java-version: '17'` selects the Java 17 line but does not pin the exact patch/vendor artifact; to compare bytes across multiple runners, pin the distribution/version and verify them.

Additions for practical CI:

- Run the workflow from a clean checkout without reusing output artifacts from a previous build.
- Record `java -version`, `javac -version`, commit ID, options, output checksums, and failure reports.
- For third-party dependencies, pin versions/lockfiles and checksums, and control repositories, classpath, and annotation processors.
- If tests have cross-platform requirements, also run a Windows/macOS matrix, though **do not rush to conclude that JARs from every OS/JDK are bit-identical**; each distinct environment can expose non-reproducible sources.
- Check PRs with the same `bash verify.sh` command as local runs to minimize discrepancies between developers and CI.

## 8. Making Tests Fail Intentionally: Checking If Tests Have “Teeth”

A test that only passes green is not necessarily effective. Change **one input at a time**, observe the relevant failure, and revert the change.

| Experiment | Single change | Exact expectation |
| --- | --- | --- |
| Class-file target | Change one of the two compile commands from `--release 17` to `--release 21` (compiler supporting 21) | Different class bytes or assertion `major == 61` fails |
| Runtime output | Edit `Hello.java` to print `"Unexpected"` | `Unexpected stdout`, non-zero exit code |
| Negative error “fixed” | Change `int count = "not a number";` to `int count = 1;` | `Invalid source unexpectedly compiled` |
| Error location shifts | Insert a real line above the erroneous assignment in `BadHello.java` | `Expected ERROR at BadHello.java:4` |
| Artifact comparison | Modify a byte in one `app.jar` **after creation** in a test harness or add a post-packaging check step | JAR byte comparison must fail if mutation occurs before assertion |
| Compile flag check | Remove `--release 17` and run on a newer JDK | Major version is no longer guaranteed to be 61; the assertion should catch it if the compiler generates the current target |

**Technical warning about the last experiment:** `BuildAudit` regenerates `app.jar` itself before comparing, so modifying the JAR file **before running the harness** gets overwritten and is not a valid mutation test. To test the ability to detect differing JAR bytes, change a packager input/logic between the two runs, or split packaging and auditing into two separate programs. The goal is to test **the exact step under verification**, avoiding “green-light tests” from modifying a file that gets rebuilt.

### 8.1. Why Must Diagnostics Be Checked by Location?

If you only check `compiled == false`, source failing due to a **missing classpath** would also make the test pass. This lesson additionally requires:

```java
d.getKind() == Diagnostic.Kind.ERROR
    && d.getLineNumber() == 4
    && d.getColumnNumber() > 0
    && d.getSource() != null
```

That is a **snippet extracted from the verification method in section 5**, not a standalone program. You also need the source URI check shown in the complete code because multiple different files may report an error on line 4. When testing an **annotation processor**, replace `-proc:none` with a pinned processor path/selection and add assertions for processor diagnostics; the current lab intentionally skips doing that.

## 9. Reliability Analysis and Technical Limitations

### 9.1. Single-Machine Repeatability vs. Independent Reproducibility

Achieving `Class bytes: MATCH` across two runs on one machine proves the fixture produces consistent bytecode under those conditions. Achieving `JAR bytes: MATCH` proves the packaging method within the same environment produces identical archive bytes. To elevate to a true **reproducible build**, it must be rebuilt from the same proven source/inputs in an independent environment without relying on hidden caches.

Frequently overlooked inputs:

| Input | Risk missed by small tests | How to control in large projects |
| --- | --- | --- |
| `javac` vendor/patch | Same `--release` yet bytecode/diagnostics may differ | Pin JDK distribution, patch, and image digest |
| JDK module/toolchain | CI selects different `java`/`javac` than developers | Use toolchains and print versions |
| Compile classpath | Transitive versions, ordering, and file contents change | Dependency locks/checksums and explicit classpath |
| Annotation processors | Generate code with timestamps, options, or different processor versions | Pin processor path/version/options |
| Sources/resources | Different encodings, newlines, line endings | UTF-8, `.gitattributes`, standard resource plugins |
| Packaging | Different ZIP timestamps/order, manifest, or resource hashes | Fixed timestamp, stable ordering, pinned packager |
| Generated files | Clock, random UUID, hostname, absolute paths | Inject provenance-tracked inputs or omit dynamic metadata |
| Runtime/integration tests | Locale/time zone, environment, test ordering | Isolate processes, pin locale/time zone when needed |
| Build cache | Holds stale outputs, causing false passes | Run cold builds in CI, verify task inputs |
| Native dependencies | Binary files depend on OS/architecture | Dedicated native environment/toolchain, store provenance |

### 9.2. What Is Pinned in the Demo JAR?

`packageClass` writes **exactly one entry** with a fixed name, bytes from `Hello.class`, and a fixed timestamp. It does not automatically solve every complex JAR case:

- If packaging multiple entries, **sort names before** calling `putNextEntry`.
- Do not embed a manifest containing current build time, hostname, username, absolute path, or random UUID.
- Entries/resources must have deterministic bytes; identical class bytes say nothing about dynamically generated JSON/configs.
- The same ZIP compressor implementation/version must be used when bit-identity across environments is required. Two different JDKs may use different compression components.
- Using a fixed timestamp from the lab is an illustrative choice; release builds can use a deterministic release timestamp, `SOURCE_DATE_EPOCH`, or commit metadata, provided the input is specified.
- This test compares two `app.jar` files containing entry `demo/Hello.class`; it is not a guide replacing Maven/Gradle JAR packaging for multi-module projects.

### 9.3. Do Not Conflate Verification Types

| Check | Proves | Does not prove |
| --- | --- | --- |
| `javac` exit code `0` | Compilation task succeeded | App runs properly |
| `javap` major = 61 | Class file targets Java 17 | All dependencies avoid incompatible APIs |
| App stdout/exit | Specific run scenario works | All application logic is correct |
| Negative `Diagnostic` | Compiler caught right kind and fixture source/line | All potential bugs are caught |
| `Arrays.equals` of two `.class` files | Two classes are byte-identical | All resources/JAR metadata match |
| `Arrays.equals` of two JARs | Two JARs are byte-identical | Artifact was built from trusted or independent sources |
| `sha256sum` | Artifact fingerprint for storage/comparison | Alone validates provenance/reproducibility |

## 10. Moving the Lab onto Maven or Gradle

In large projects, do not use ad-hoc `javac` scripts that bypass the real dependency graph and plugins; keep the verification mindset of the lab while moving compile/test/package steps into the build system:

**Maven:**

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
```

This is an **illustrative POM snippet**, requiring Maven Compiler/JAR/Resources Plugin versions with proper support, a wrapper, and pinned dependencies; `project.build.outputTimestamp` does not automatically handle every generator. Check the JAR file by hash in CI as well.

**Gradle Kotlin DSL:**

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

This is also a **configuration snippet**, not a standalone `build.gradle.kts`. Gradle `Jar` also has a manifest, resources, plugins, and a dependency graph that need control. Annotation processors must have their own configuration and run when needed; do not apply `-proc:none` to modules with codegen.

**Shared mindset:** wrapper + JDK/toolchain + compile flags + reproducible archives + tests/diagnostics + cross-environment hash comparison. Only claim complete reproducibility after verifying the **actual artifact** from designated independent environments.

## 11. Troubleshooting Common Failures

| Symptom | Likely cause to check | Resolution |
| --- | --- | --- |
| `invalid target release: 17` | `javac` older than Java 17 | Use JDK 17+, verify `javac -version` |
| `error: package ... does not exist` | Classpath undeclared or wrong sources | Pin dependencies and appropriate `-classpath`/module path |
| `Could not find or load main class demo.Hello` | Wrong `-d`, wrong package, or `-cp` | Check `build/a/classes/demo/Hello.class` |
| Java source starts with stray character `\ufeff` | UTF-8 BOM from old editor/PowerShell | Save as UTF-8 without BOM |
| `Class files differ` | Two compiles did not use the same sources/options/toolchain or nondeterministic generator | Diff bytecode, inspect `javac` and inputs |
| `Expected Java 17 class-file version 61` | Forgot `--release 17` or build used another target | Use the right `--release` on every pass |
| `JAR files differ` | Different entry timestamp/order, manifest, resources, compressor | Pin metadata/entry order and packager |
| `Application stdout: PASS` fails | App printed wrong text, newline/charset, or different runtime | Check stdout/exit, pin encoding |
| `Invalid source unexpectedly compiled` | Negative fixture was edited into valid code | Restore the mistyped assignment |
| `Expected ERROR at BadHello.java:4` | Different error diagnostic/line shift/wrong source | Verify right source and line in fixture |
| `System Java compiler is unavailable` | Runtime image does not include compiler | Run tests with a full JDK |
| Passes locally but fails in CI | Different Java version, charset, working directory, or environment | Log toolchain and run the same verify script |

## 12. Progressive Extension Exercises

**Level 1 – compiler flags:** add `-Werror` to the positive compile, write a source that intentionally emits a warning via `-Xlint:deprecation`, and observe the exit code. Distinguish `WARNING`/`MANDATORY_WARNING` from `ERROR`; do not assume every warning turns into an `ERROR` diagnostic at the same line.

**Level 2 – compiler API:** replace `BadHello.java` with two sources, one valid and one erroneous. Assert the exact URI/line/column of the error; handle `getSource() == null` or `getLineNumber() == Diagnostic.NOPOS` for diagnostics without a location. Tests should not depend on verbatim `getMessage(Locale)`.

**Level 3 – multiple artifacts:** add `demo/Maths.java` and a UTF-8 resource. Sort entry names deterministically, package them into the JAR, and compare byte-for-byte across two checkouts. Only after modifying `packageClass` code to add entries should you check the whole-artifact hash.

**Level 4 – environment independence:** create two clean containers with **the same JDK image digest**, same source commit, and build commands, save SHA-256 hashes, and compare. Then intentionally change the JDK patch or time zone to evaluate whether the artifact stays identical; record empirical results instead of guessing.

**Level 5 – project with dependencies:** add a real library, pin versions/checksums, configure an explicit compiler classpath, and explain why compiling against an ad-hoc classpath from an IDE is not a trustworthy reproducibility test.

## 13. Acceptance Checklist and Self-Assessment Questions

- [ ] `src/main/java/demo/Hello.java` runs and prints exactly `Hello from Java 17`.
- [ ] Both compile runs use the same `--release 17 -encoding UTF-8 -proc:none`, outputting to `build/a` and `build/b`.
- [ ] `BuildAudit.java` compiles and gives the **six PASS/MATCH lines** shown in the example.
- [ ] `BadHello.java` intentionally errors on line 4 and the diagnostic matches kind/source/line; fixing the error makes the test fail.
- [ ] Changing stdout or changing the compile target makes verification fail.
- [ ] The script returns a non-zero exit code when an assertion fails.
- [ ] Do not confuse “two runs on the same machine match” with proving reproducibility across independent environments.
- [ ] Do not include `build/`, generated JAR files, or erroneous source fixtures in production source lists.
- [ ] Checked JDK, compiler, and hash logs during CI runs and understood JAR timestamp/metadata limits.

**Self-check:** Why is `--release 17` needed even if you are using JDK 24? Why is comparing `.class` files alone insufficient for a JAR artifact? Why must erroneous-source tests check `Diagnostic.Kind`, source URI, and location instead of only checking `call() == false`? What must change to conclude that two CI runners genuinely rebuilt the same artifact?

## References

- Java SE 17 – `javac` options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Java SE 17 – Java Compiler API: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17 – `Diagnostic`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Java SE 17 – `JarOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html
- Java SE 17 – class file format (JVMS): https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html
- Java SE 17 – `jar` tool: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html
- Apache Maven – Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Gradle – Reproducible Archives: https://docs.gradle.org/current/userguide/working_with_files.html
- Reproducible Builds – SOURCE_DATE_EPOCH: https://reproducible-builds.org/docs/source-date-epoch/
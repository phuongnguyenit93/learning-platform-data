# Verifying the Build JDK and Target Java Environment Matrix

A Java application that **compiles successfully** on a newer JDK is not guaranteed to **run** on an older Java environment. Conversely, using `javac --release` to generate older bytecode also **does not automatically guarantee** that all libraries, annotation processors, runtime features, or deployment configurations are compatible. When releasing software, you must simultaneously verify **the JDK used to build**, **the Java release targeted by the compiler**, **the APIs called**, **the class files of every dependency**, and **the Java runtimes that will execute the application**.

This Knowledge article presents how to build and verify a **build JDK – target Java compatibility matrix** from simple cases to multi-version CI, complete with Java 17+ examples, `javac`/`java` commands, how to read class-file versions, error scenarios, and a release checklist. The focus is on **evidence-based compatibility**, not simply changing a `target` number and assuming older Java versions are supported.

## 1. Separating Four Concepts Before Building the Matrix

**Build JDK** is the toolset actually running the `javac` command, for example JDK 17, 21, or 25. Check it with `javac -version`. It determines which `--release` targets the compiler supports, the compiler version, and the environment for build tools/annotation processors.

**Target platform release** is the Java level with which we want the program's class files and platform APIs to be compatible. The recommended choice when using modern `javac` is `--release N` (if the compiler supports N). It constrains **syntax/language**, **class file format**, and **the Java/JDK APIs documented for release N**.

**Deployment runtime (Runtime/JRE/JVM)** is the environment actually executing the `java` command. A Java 11 runtime is not expected to understand Java 17 class files; a Java 17 or newer runtime can in principle read class files generated for Java 11, provided other compatibility conditions are also satisfied.

**Dependencies and platform** include libraries/JARs, Java modules, OS APIs, native libraries, processors, build tools, startup configurations, and behaviors the application relies on. Checking only the main class while ignoring dependencies can lead to failures when loading classes or calling APIs.

~~~text
Build JDK (javac version)
       │
       ├── --release N
       │       ├── Java source rules
       │       ├── class-file major version
       │       └── documented platform API of release N
       │
       ▼
  App classes + dependencies + resources + metadata
       │
       ├── Runtime Java N  ───► compile-time/linkage/runtime tests
       ├── Runtime Java N+ ───► compile-time/linkage/runtime tests
       └── OS/CPU variants ───► integration/platform tests
~~~

For example: `JDK 21 javac` compiling with `--release 17` does not mean the program will run **on JDK 21** upon release; it is intended to build an application capable of running on **Java 17** or newer. You must actually use a Java 17 runtime to prove it.

## 2. How Do the Three Flags --release, --source, and --target Differ?

| Configuration | Primary rule | Risk if misused |
| --- | --- | --- |
| `javac --release 17` | Java 17 language, Java 17 target class file, Java/JDK APIs permitted in Java 17 | Still does not lock external library versions, runtime flags, or native dependencies |
| `javac --source 17` | Java 17 language rules | By itself, does not prove class files and platform APIs match Java 17 |
| `javac --target 17` | Class-file version suitable for Java 17 | By itself, does not restrict APIs used from a newer JDK |
| `javac -source 17 -target 17` | Restricts source language and class-file target | Without proper platform API configuration, there is still a risk of using APIs introduced after Java 17 |
| No flag | Defaults to the current compiler | Switching the build JDK can accidentally raise the minimum runtime requirement |

**Practical rule:** when using a newer `javac` to build an application for an older Java release, prefer `--release N`. It prevents a common bug: a `.class` file looks compatible yet contains a call to a method **only available in newer Java versions**.

For example, on JDK 21:

~~~bash
javac --release 17 -d out src/example/App.java
~~~

This means the compiler must reject syntax or platform APIs outside Java 17, and emit Java 17 target class files upon successful compilation. However, `--release` **does not force** all non-Java-platform JARs on `-cp` to have been compiled with target 17, nor does it downgrade third-party library APIs.

**Do not combine** `--release` with `--source` or `--target` in the same invocation; they are two different configuration mechanisms. Supported releases depend on the exact `javac` being used: run `javac --help` to list them, and do not assume any given JDK can always cross-compile to every historical release.

## 3. Class-File Major Version: Knowing the Minimum JVM Required by Code

Class files have major/minor versions. For modern Java releases, the numbers commonly needed are:

| Java release | Class file major version | Target example |
| --- | ---: | --- |
| Java 8 | 52 | `javac --release 8` on a supporting JDK |
| Java 11 | 55 | `javac --release 11` |
| Java 17 | 61 | `javac --release 17` |
| Java 21 | 65 | `javac --release 21` |
| Java 25 | 69 | `javac --release 25` |
| Java 26 | 70 | `javac --release 26` |
| Java 27 | 71 | `javac --release 27` |

Specific releases since Java 9 increment the major version with each Java release; the table above selects only common milestones. An older `javac` cannot target an unknown future release; for example, JDK 17 `javac` will not accept `--release 21`. The class-file **major version is a necessary condition**, but not a sufficient condition for an application to run successfully.

### How to verify in practice

**File `HelloMatrix.java`:**

~~~java
public class HelloMatrix {
    public static void main(String[] args) {
        System.out.println("Compatibility OK");
    }
}
~~~

On a machine whose `javac` supports releases 11 and 17:

~~~bash
mkdir -p out11 out17
javac --release 11 -d out11 HelloMatrix.java
javac --release 17 -d out17 HelloMatrix.java
javap -verbose -classpath out11 HelloMatrix
javap -verbose -classpath out17 HelloMatrix
~~~

In the output of `javap -verbose`, look for the two lines `minor version` and `major version`. For this **non-preview** code, the expected result is:

~~~text
out11: major version: 55
out17: major version: 61
~~~

The two lines above are **the values to cross-check**, not the entire stdout of `javap`. The same source code and the same build JDK with different `--release` selections can yield class files with different minimum runtime requirements.

If run with a Java 17 runtime:

~~~bash
java -cp out11 HelloMatrix
java -cp out17 HelloMatrix
~~~

Each command prints:

~~~text
Compatibility OK
~~~

If a Java 11 runtime is actually available, run:

~~~bash
/path/to/jdk11/bin/java -cp out11 HelloMatrix
~~~

The command should also print `Compatibility OK` under normal configuration; however, running `out17` with Java 11 will be rejected because major 61 is newer than the maximum major 55 supported by Java 11. The typical error type is `UnsupportedClassVersionError`. **Only run the command with an actually installed runtime path**; `/path/to/jdk11/bin/java` is an illustrative placeholder, not an executable present on every machine.

## 4. Example Checking the Java API Barrier: The Right Target Is Not Enough When Using Only -target

A classic mistake: restricting the class-file target while accidentally calling an API from the build JDK that does not exist on the target Java version.

**File `ApiGuard.java`:**

~~~java
public class ApiGuard {
    public static void main(String[] args) {
        System.out.println("   ".isBlank());
    }
}
~~~

`String.isBlank()` was introduced in Java 11 and does not exist in Java 8. When using a newer JDK with `--release 8`:

~~~bash
javac --release 8 ApiGuard.java
~~~

The compiler **must reject** the `isBlank()` call on `String` because the API does not exist in Java 8. The message is typically `cannot find symbol`; do not rely on a fixed diagnostic text across compiler versions.

Still on that same newer JDK:

~~~bash
javac --release 11 ApiGuard.java
java ApiGuard
~~~

With an appropriate Java 11+ runtime, stdout:

~~~text
true
~~~

Key point: a configuration like `-source 8 -target 8` on a JDK that has `String.isBlank()` **can** compile the code if the compiler still sees the current platform APIs (accompanied by a warning about bootstrap/system classes). The class file has major 52, yet when run on Java 8 and reaching the `isBlank()` call it may throw `NoSuchMethodError`. Therefore, **do not verify compatibility solely by major version**.

Do not use standalone `-source`/`-target` to evade `--release` errors. If forced to use the older option pair due to special circumstances, configure the platform classes/APIs matching the target version and test on the actual runtime.

## 5. Example Checking the Source Syntax Barrier

Java syntax evolves across releases. An available API does not mean all new syntax is accepted by the compiler when targeting an older Java version.

**File `RecordGuard.java`:**

~~~java
public record RecordGuard(int x, int y) {
    public static void main(String[] args) {
        System.out.println(new RecordGuard(2, 3).x());
    }
}
~~~

`record` became a standard feature in Java 16. With JDK 17 or newer supporting the corresponding release:

~~~bash
javac --release 17 RecordGuard.java
java RecordGuard
~~~

Stdout:

~~~text
2
~~~

However:

~~~bash
javac --release 11 RecordGuard.java
~~~

will fail because the Java 11 language does not have record declarations. Do not wait until the Java 11 JVM to discover the mismatch: the compiler already rejects it according to `--release 11` source language rules.

Additional milestones to remember: `var` for local variables (Java 10), switch expressions (standardized in Java 14), pattern matching for `instanceof` and records (standardized in Java 16), sealed classes (standardized in Java 17). Many features spent time in *preview* before standardization; **do not use an old preview version to infer the source API or bytecode of the standardized version**.

## 6. Theoretical Matrix: Build JDK × Release × Runtime

An initial matrix helps detect configurations that **cannot** or **possibly can** run. For an ordinary Java program without preview features, with compatible dependencies, and with a JDK compiler supporting `--release` as shown in the table:

| Build JDK | `--release` | JVM 11 | JVM 17 | JVM 21 | JVM 25 | Interpretation |
| --- | --- | --- | --- | --- | --- | --- |
| 17 | 11 | Possible | Possible | Possible | Possible | Class major 55; requires API/runtime testing |
| 17 | 17 | **No** | Possible | Possible | Possible | Java 11 cannot read major 61 |
| 17 | 21 | Does not compile | — | — | — | JDK 17 `javac` cannot target Java 21 |
| 21 | 11 | Possible | Possible | Possible | Possible | Newer compiler cross-compiles to Java 11 |
| 21 | 17 | **No** | Possible | Possible | Possible | Runtimes 17 and above in principle support major 61 |
| 21 | 21 | **No** | **No** | Possible | Possible | Class major 65 |
| 25 | 17 | **No** | Possible | Possible | Possible | Platform APIs restricted to `--release 17` |
| 25 | 25 | **No** | **No** | **No** | Possible | Class major 69 |

**"Possible" does not mean "PASSED".** It only states that the class-file version condition does not preclude running the program. The real runtime can still fail due to dependencies, service providers, reflection/module access, native libraries, encoding/timezone, security policies, or application behavior.

This matrix treats runtimes 11/17/21/25 as **potential deployment environments**, without forcing every application to support all four versions. When product policy states "minimum Java 17", the Java 11 column is out of support scope; there is no need to build a separate branch forcing Java 17 code down to 11 just to make the table look complete.

### How to select a useful matrix instead of infinite combinatorial multiplication

- **Rows:** JDKs allowed for building in CI/dev/release, e.g., 17 and 21.
- **Columns:** runtimes the product declares to support, e.g., 17 and 21.
- **Fixed conditions:** `--release 17` for production artifacts, the same lockfile/dependency versions, and the same critical test suite.
- **Add a platform axis** when native dependencies or OS/CPU differences have an impact (Linux, Windows, ARM/x86_64...).
- **Do not test future JDKs just because they are installed:** choose based on support policy and real risk; very new runtimes still need behavioral verification.

## 7. Minimum Runtime Does Not Mean "Runs on Every Newer Java"

Although Java strives to maintain backward compatibility, an old bytecode artifact has no absolute guarantee that every function will still work on every newer JVM. Causes to watch out for:

1. **Java libraries removed or no longer bundled with the JDK**. For example, Java EE/JAXB modules were once bundled with some older JDKs but removed in JDK 11; if an old app depends on them, the old class files will still lack the dependency at runtime.
2. **Strong encapsulation/JDK internals**. Code accessing `sun.*` or internal packages may fail on newer JDKs or require `--add-exports`/`--add-opens` workarounds (not a sustainable solution).
3. **Runtime flags or GC**. A launcher/VM option may change or be removed; the app may fail to start even if class files are compatible.
4. **External libraries**. A newer JAR may use a higher class-file major version, or a dependency's API may change incompatibly.
5. **Native code/JNI, TLS/crypto, locale, timezone, file permissions**. Components outside bytecode depend on the OS, security policies, and the JDK runtime image.
6. **Reflection, proxies, service loading, and module boundaries**. Some errors only happen when executing a specific code path, not when verifying `main` startup.

Therefore, a support matrix should include **compilation** tests, **execution on target runtimes**, **integration with dependencies**, and **regression** tests for sensitive functionality. The class file format is only the first barrier.

## 8. Dependencies Determine the Minimum JVM of the Entire Application

Suppose `app.jar` is compiled with `--release 11` (major 55), but `lib-x.jar` contains a major 61 class (Java 17). If a Java 11 runtime must load that major 61 class, the result can be `UnsupportedClassVersionError` even though `app.jar` itself is valid.

**Compatibility is a property of the entire set of runtime artifacts**, not just a single class created by the project. For external dependencies, also cross-check:
- Minimum Java version declared by the library publisher.
- Class-file versions of classes actually loaded, including indirect/transitive dependencies.
- System module APIs or JDK internals called by the library.
- Initialization conditions and binary compatibility across library versions.
- Dynamically loaded dependencies: JDBC drivers, service providers, servlet containers, plugins, agents, bytecode transformers.

Example of inspecting class files in a JAR:

~~~bash
jar tf libs/example.jar
javap -verbose -classpath libs/example.jar com.example.SomeClass
~~~

**The commands are illustrative examples:** replace `libs/example.jar` and `com.example.SomeClass` with a real JAR/class name. `jar tf` lists entries; `javap` shows major/minor version **for one class** and does not scan the entire JAR automatically. To verify every class as well as multi-release entries, use an appropriate JAR/CI analysis tool rather than drawing conclusions about the whole library from one class.

### Multi-release JAR

A JAR can contain versioned classes under `META-INF/versions/N/` via the **multi-release JAR** mechanism. An appropriate runtime selects the entry matching its version. This provides different implementations per release, but **does not mean** an arbitrary major 61 class inside a JAR can run on Java 11.

Valid base classes for the minimum runtime, a proper manifest/JAR format, and verification of versioned entry selection are required. When analyzing class files with `javap`, note the option to select a multi-release version where appropriate; inspecting only the base entry can miss bytecode chosen by a newer runtime.

## 9. Preview Features Are a Different Test Axis from Normal Releases

Some Java features are provided in preview status in specific JDKs and may change or be withdrawn before standardization. Compiling preview features has its own rules regarding `--enable-preview`, the compiler release, and execution.

General example for **code that actually uses preview features of the exact JDK currently compiling**:

~~~bash
javac --enable-preview --release 21 PreviewDemo.java
java --enable-preview PreviewDemo
~~~

The commands above are a **syntax template** for a scenario using JDK 21; `PreviewDemo.java` is not provided here because its contents must match a specific preview feature of that release. On a different newer `javac`, do not assume it supports compiling previews from historical releases.

Normally, preview class files use the special minor version `65535` along with the major version of the corresponding release; the JVM only permits preview under matching conditions, including `--enable-preview` and the matching release. For example, Java 21 preview bytecode is not treated as an ordinary portable artifact for a Java 25 runtime.

**Recommendation:** if the goal is a widely distributed library, avoid preview features in artifacts supporting multiple runtimes. If using preview, clearly define **the build JDK + exact runtime release + flags pair**, separated from the general compatibility matrix. Passing tests on Java 21 with preview enabled does not prove the application runs on Java 21 without preview enabled.

## 10. Hands-on Mini-Project Example: Build Once, Run on Multiple Runtimes

Create a dedicated directory:

~~~text
matrix-demo/
├── src/
│   └── demo/
│       ├── Calculator.java
│       └── Main.java
└── out17/
~~~

**`src/demo/Calculator.java`**

~~~java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static long add(long a, long b) {
        return Math.addExact(a, b);
    }
}
~~~

**`src/demo/Main.java`**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("result=" + Calculator.add(20, 22));
    }
}
~~~

From the `matrix-demo` directory, using JDK 17+ supporting release 17:

~~~bash
mkdir -p out17
javac --release 17 -encoding UTF-8 -d out17 \
  src/demo/Calculator.java src/demo/Main.java
java -cp out17 demo.Main
~~~

Stdout:

~~~text
result=42
~~~

`Math.addExact(long, long)` has existed since Java 8, so it causes no API issues when targeting Java 17. The example deliberately uses simple syntax and an API that already existed before the target so learners can focus on the **runtime matrix**, not syntax changes.

If the machine has multiple JDKs, replace the `java` command in the final step with the path to a **specific runtime**:

~~~bash
/opt/jdk17/bin/java -cp out17 demo.Main
/opt/jdk21/bin/java -cp out17 demo.Main
/opt/jdk25/bin/java -cp out17 demo.Main
~~~

The paths `/opt/jdk17`, `/opt/jdk21`, `/opt/jdk25` are **examples** and must be replaced with where JDKs are installed on your machine/runner. Each valid environment should print `result=42`; when running, make sure to invoke the `java` binary of the exact JDK rather than just checking `JAVA_HOME` in the terminal.

**Separate build from run:** if you use JDK 25 `javac` to compile with `--release 17`, the run step on JDK 17 must still be tested with `/opt/jdk17/bin/java`. Running `java` from PATH can accidentally use JDK 25 and give a false green result for Java 17 support.

## 11. Verification Matrix by Command: One Artifact, Multiple Runtimes

To run a small matrix manually, prepare an environment with Java 17 and Java 21 at two different paths. Try the sample code from section 10. After compiling:

~~~bash
/opt/jdk17/bin/java -version
/opt/jdk17/bin/java -cp out17 demo.Main

/opt/jdk21/bin/java -version
/opt/jdk21/bin/java -cp out17 demo.Main
~~~

**Conclude "PASS"** only when the command uses the right runtime, returns exit code 0, and produces the expected stdout (for this case, `result=42`). `java -version` typically writes to stderr; do not compare `-version` output against program stdout.

Sample matrix for a `--release 17` artifact:

| Test | Expectation |
| --- | --- |
| Build with JDK 17, `--release 17` | Compiles successfully if the environment is complete |
| Build with JDK 21, `--release 17` | Compiles successfully, class-file major 61 |
| Run on Java 17 | `result=42`, exit 0 |
| Run on Java 21 | `result=42`, exit 0 |
| Run on Java 11 | **Unsupported**, class major 61 |
| Run with an incompatible dependency | Test must **fail clearly**, must not be marked PASS |

If a newer build JDK produces different warnings or a different class file structure that are still valid under `--release 17`, do not assume the artifact is broken. However, annotation processors/generators may behave differently when changing JDKs, so the artifact pipeline needs to test the output as new, not merely confirm `javac` returned 0.

## 12. Automating Tests with Bash on a CI Runner

This is an example script running on Linux/macOS, assuming `out17/` has already been compiled successfully and two environment variables **`JAVA17_HOME`**, **`JAVA21_HOME`** point to the installation directories of the corresponding Java runtimes. The script tests exit code and application stdout without installing JDKs:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

for home in "$JAVA17_HOME" "$JAVA21_HOME"; do
    "$home/bin/java" -version

    actual="$("$home/bin/java" -cp out17 demo.Main)"
    if [[ "$actual" != "result=42" ]]; then
        printf 'FAIL: unexpected output: %s\n' "$actual" >&2
        exit 1
    fi

    printf 'PASS: %s\n' "$home"
done
~~~

Run this script from the project directory containing `out17`. With `set -e`, a Java command returning a non-zero exit code stops the pipeline, even if the `actual` variable is not fully assigned. The output comparison checks this exact short string; for complex programs use JUnit/integration tests instead of relying on single stdout strings.

**Script limitations:** if `JAVA17_HOME` or `JAVA21_HOME` is unset, the script errors; CI/runner configuration is required. If the variables mistakenly point to the same JDK, the two tests do not actually cover two different runtimes. Therefore, at the start of each job **log and verify the actual version**, rather than just printing a "Java 17" label.

A common CI approach is **matrix strategy**: each job runs one runtime, such as Java 17 and 21, to reduce the risk of picking the wrong `java`. This allows reporting PASS/FAIL per Java version separately and running multiple jobs in parallel.

## 13. Distinguishing the Build Matrix from the Runtime Matrix

There are two forms of testing that need to be separated:

**Build matrix** answers "Which JDKs can build the source/build pipeline?" For example, running the same source with JDK 17 and JDK 21, always setting `--release 17`. It detects differences in compilers, processors, generators, and build tools when the JDK changes.

**Runtime matrix** answers "Can the same built artifact run on the Java runtimes we claim to support?" For example, building one artifact with JDK 21 `--release 17`, then running that exact artifact under Java 17 and 21.

If each runtime job rebuilds the artifact itself, you are testing **a build JDK–runtime pair** rather than purely testing **the same artifact across multiple runtimes**. Both are useful; design them deliberately:

~~~text
                  build JDK 17 ──┐
source + deps ────┤             ├──► build validation
                  build JDK 21 ──┘

source + deps ──► canonical build JDK 21 --release 17
                            │
                            ▼
                   SAME artifact (hash)
                    │               │
                    ▼               ▼
                Java 17          Java 21
                    │               │
                    └──► runtime/test matrix
~~~

For releases, the **canonical release artifact** is the file actually deployed. Use the same SHA-256/artifact identifier across runtime jobs instead of each job producing a slightly different build. At the same time, run a separate job to verify that switching the build JDK does not break the toolchain.

## 14. Configuring Maven and Gradle for Target Release

With Maven, you can declare in `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

This property is supported by appropriate versions of the Maven Compiler Plugin. The selected compiler must still support `--release 17`; Maven configuration **does not install JDK 17**. If CI requires a specific JDK, use the Maven Toolchains Plugin or configure the runner/IDE accordingly.

Gradle (Groovy DSL) can declare:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Meaning: **select JDK 21 as the compiler toolchain** (when Gradle/toolchain resolution has that JDK), while only **emitting class files and referencing platform APIs according to Java 17**. These are two independent axes. Gradle runtime test/task configurations must be checked separately: the compiler's target release does not automatically change the `java` launcher used in every test task or at deployment.

**Common warning:** `sourceCompatibility = '17'` and `targetCompatibility = '17'` do not provide the same API guarantee as `options.release = 17`. Inspect the actual `javac` command invoked by Gradle/Maven and check the class-file version in the artifact.

### Annotation processors and build plugins also have their own JDK requirements

For example, a project targets Java 17, but an annotation processor or build plugin requires JDK 21. When building under JDK 17, the toolchain may fail even though the main source code is completely valid for Java 17. Processors/plugins are **programs running inside the build environment**, not necessarily constrained by the `--release` of the application output.

In newer JDK versions, the annotation processing activation policy has also changed (starting in JDK 23, processing must be configured more explicitly). When testing the build matrix, ensure processors are explicitly enabled and the processor path is set clearly if the build depends on code generation. If this step is missed, the build may "succeed" while missing auto-generated classes.

## 15. Dependency Versions, Packaging Tools, and Runtime Images

**The Maven/Gradle dependency graph** should be properly pinned using dependency locking/BOM/reproducible builds depending on the project. If the Java 17 job pulls one dependency version and the Java 21 job pulls another, you cannot simply attribute a failure to the JDK.

**Fat JAR or shaded JAR:** scan every class merged into the artifact, not just classes in the project's main source directory. Libraries may be relocated, yet their bytecode version is not automatically downgraded.

**jlink runtime image:** a custom runtime image may omit modules. An application compiled with `--release 17` can still fail if the runtime image lacks a required module. Test on **the actual published image**, not only on a developer's full JDK.

**Containers:** a "Java 21 build image" and "Java 17 runtime image" pair can be valid if the target is right, dependencies are compatible, and entrypoint/classpath are correct; verify image tags, digests, and the runtime version inside the container. If the runtime image is Java 11, a Java 17 artifact will fail even though the Docker build completes.

**Native dependencies:** the Java source level does not determine binary compatibility of native `.dll`/`.so`/`.dylib` libraries. Add an OS/architecture and JNI/FFM version (if used) test axis when deploying across multiple platforms.

## 16. Typical Matrix Errors and How to Read Them

### UnsupportedClassVersionError

For example, a Java 11 runtime loading `HelloMatrix.class` compiled with `--release 17`. The reason is that class file major 61 exceeds Java 11's support (55). Fix it by **using an appropriately newer runtime** or **recompiling the source/dependency with a genuinely supported lower target**, then retest. Do not edit major bytes with a hex editor: bytecode/APIs can still be incompatible.

### NoSuchMethodError or NoSuchFieldError

The class file may have the right major version, yet the runtime loads a **library version** lacking a method/field the code was compiled to call, or the runtime JDK API is older. Inspect classpath/module path, version conflicts, shadowing, and whether the API exists in the target release. For platform APIs, `--release` helps prevent accidental calls to newer APIs.

### NoClassDefFoundError and ClassNotFoundException

A dependency may be missing at runtime, the runtime image may have trimmed modules, or the class failed to load. This is not evidence of a wrong class-file major version. Inspect the actual artifact, dependency resolution, plugins/service loaders, and paths.

### IllegalAccessError, InaccessibleObjectException

May result from changes in module boundaries/strong encapsulation across JDKs or reflection code accessing internals. Verify `module-info.java`, `exports`/`opens`, or replace with public APIs; enabling special flags on the compiler does not ensure the runtime receives the same options.

### NoSuchAlgorithmException, TLS/cipher errors, encoding changes

These are typically runtime environment/security/provider or data issues. Older/newer Java versions have different defaults and policies. A "Hello World" unit test does not cover these interactions; add integration tests matching real workloads.

### Test differences due to timezone, locale, and default charset

An application does not depend solely on bytecode. For example, Java 18 switched the JDK default charset to UTF-8 under JEP 400; legacy code relying on the OS default encoding can yield different results. For tests handling text data, specify the charset (`StandardCharsets.UTF_8`) and locale/timezone when stability is required.

## 17. Using javap and Runtime Versions for Consistent Diagnostics

When reporting matrix failures, keep at minimum this set of evidence:

~~~bash
javac -version
java -version
javac --help
javap -verbose -classpath out17 demo.Main
~~~

`javap` is useful for major/minor versions, signatures, method descriptors, references, and metadata. However, it only inspects **the specified class**. For complex JAR files, inspect the dependencies/transitive classes that actually need to be loaded.

When running in CI, log the exact **paths** and versions of `java`/`javac`, not just reading `JAVA_HOME`. Runners can have multiple JDK installations; `PATH`, build tool toolchains, plugins, or IDEs sometimes select different ones. The same source and flags can also produce different output across compiler versions, yet what determines runtime compatibility is the ability to load, link, and execute properly—not byte-for-byte identical bytecode.

Catch version errors at **both the compilation step** and **the execution step**. An environment with only JDK 21 can run `javac --release 17` and execute on Java 21, yet that does not prove a Java 17 runtime can deploy all real-world functionality.

## 18. Release Checklist and PASS/FAIL Decision

Before declaring "we support Java 17+":

1. **Lock the minimum Java target**, rather than choosing based on whatever JDK a developer happens to have.
2. **Check all permitted build JDKs**, `javac -version`, and the releases the compiler actually supports.
3. **Set `--release N`**, or the build tool's equivalent mechanism, in each module/compile task; do not use standalone `-target N`.
4. **Inspect the artifact**: major/minor versions, dependency JARs, generated classes, fat JARs, multi-release entries, and the module graph.
5. **Test the lowest target runtime** (e.g., Java 17), since missing APIs/classfile errors are most likely to surface there.
6. **Also test newer supported runtimes** (e.g., Java 21/25) to catch module reflection errors, JDK removals, default security/provider/encoding differences, and behavior changes.
7. **Run integration smoke tests, unit tests, I/O, DB/TLS, serialization, reflection, and native code** matching product scope, not just string-printing commands.
8. **Separate the build matrix and runtime matrix**; use **the same release artifact** across runtime jobs if you want to prove portability of a release.
9. **Document the preview policy**, recommending against use in general-purpose library/runtime matrices; if mandatory, pin the exact version and `--enable-preview`.
10. **Report qualified results**: PASS on which JDK, which OS, which artifact digest, and with which test suite. Do not turn "class major version is supported by the JVM" into "all functionality has been proven".

### Sample empirical results table

| Artifact | Build JDK | Release | Runtime | Test type | Result |
| --- | --- | --- | --- | --- | --- |
| `app.jar` (fixed SHA) | 21 | 17 | 17 | Smoke + unit + integration | Measured PASS/FAIL |
| Same `app.jar` | 21 | 17 | 21 | Smoke + unit + integration | Measured PASS/FAIL |
| Same `app.jar` | 21 | 17 | 25 | Smoke + unit + integration | Measured PASS/FAIL |
| Trial build of same source | 17 | 17 | 17 | Build tool + processor | Measured PASS/FAIL |

The `Measured PASS/FAIL` cells are **placeholders for recording results after running CI**, not pre-determined conclusions. If runtime 25 is not yet in the support policy, the corresponding row can be marked "experimental" instead of publishing an unverified promise.

## 19. Self-Check Questions

**Question 1.** Built with JDK 21 using `--release 17`: must it necessarily run on a Java 21 runtime?  
**Answer:** No. The artifact targets the Java 17 platform; test it with Java 17 and the supported runtimes.

**Question 2.** `javap` reports major 55, yet the application calls `String.isBlank()`. Is it guaranteed to run on Java 8?  
**Answer:** No. Java 8 does not have `String.isBlank()`; `-source 8 -target 8` with newer platform APIs can emit a major 52 file that still contains references to newer APIs. With major 55 (Java 11), it is even less able to run on Java 8.

**Question 3.** Why is `--release 8` from a newer JDK more reliable than `-source 8 -target 8`?  
**Answer:** It constrains the language, class-file target, and platform APIs permitted in Java 8, not just syntax/bytecode.

**Question 4.** An `app.jar` has major 61 classes, while a dependency has major 65. Can a Java 17 runtime load that dependency?  
**Answer:** No. Java 17 only supports up to major 61; when the major 65 class must be loaded, a version error will occur.

**Question 5.** What reasons can cause code compiled with `--release 17` to still fail on a Java 21 runtime?  
**Answer:** Dependencies, JDK internals, module access, runtime flags, native libraries, security/providers, or behavior outside the class-file format may differ; actual runtime testing is needed.

**Question 6.** Why do two jobs both labeled "Java 17" not yet prove the matrix has two runtimes?  
**Answer:** Both might accidentally point to the same `java` binary; log `java -version` and the actual path, and separate the build toolchain from the runtime.

**Question 7.** Should a preview class file from Java 21 be considered normally portable to every newer runtime?  
**Answer:** No. Preview features have activation flags and special version constraints; do not treat them like stable class files.

**Question 8.** Why must you test both the lowest runtime and newer runtimes?  
**Answer:** The lowest runtime catches class/API requirements that are too high; newer runtimes catch dependency changes, module encapsulation, security, environment, and integration behavior issues.

## 20. Key Takeaways and Reference Sources

- **Build JDK**, **`--release`**, **class-file major version**, **dependency runtime requirement**, and **actual runtime** are distinct axes.
- Use **`--release N`** when you need to cross-compile to a supported Java N; `-source`/`-target` alone are not enough to guarantee platform API compatibility.
- The class-file matrix indicates basic capability and **does not replace runtime tests** with Java N itself and the actual artifact.
- **Do not inspect only app classes**: libraries, generated classes, shaded JARs, Java modules, and runtime images can raise the minimum Java requirement.
- **Preview features, native code, reflection, and JDK internals** require separate support policies and corresponding tests.
- Keep builds reproducible, verify `java -version` in every CI job, and store artifact digests and test results before declaring PASS.

Official documentation: [javac command (Oracle JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html), [Class file format / JVM specification](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html), [JEP 247: Compile for Older Platform Versions](https://openjdk.org/jeps/247), [JEP 238: Multi-Release JAR Files](https://openjdk.org/jeps/238), [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400).
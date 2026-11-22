# Compiling and Running Tests Using a Specified Toolchain

When a Java project must support multiple JDK versions, build results are reliable only when the team knows precisely which compiler compiled the source code and which JVM executed the tests. A developer machine may have multiple JDKs installed; CI might run Gradle or Maven on one JDK while compiling with another; production may run a third version. Leaving tools to pick based on `PATH` or `JAVA_HOME` without control can lead to differing results across environments.

Java toolchains let you explicitly specify the JDK a task should use. In Gradle and Maven, toolchains select a compiler or runtime by version, and in certain cases also by vendor. When combining toolchains with release-level configuration such as `--release`, a team can separate three questions:

1. Which JDK is the build tool running on?
2. Which JDK compiler compiled the source code and which Java version does it target?
3. Which JVM executed the tests?

Separating these questions clearly is the foundation for multi-version compatibility testing and reproducing build results across personal machines, CI, and deployment environments.

## 1. What Is a Toolchain and What Problem Does It Solve?

A toolchain is a set of tools and runtime deliberately selected for a development task. In a Java project, a toolchain typically refers to a specific JDK installation used by the compiler, test runner, or Javadoc tool.

Without specifying a toolchain, a build can depend on whichever JDK happens to come first on `PATH`, `JAVA_HOME`, or local machine settings. For example:

```text
Developer A's machine: JAVA_HOME -> JDK 17
Developer B's machine: JAVA_HOME -> JDK 21
CI:                    JAVA_HOME -> JDK 21
Production:            runtime -> JDK 17
```

If the build does not explicitly mandate the compiler and test runtime, the same commit can be compiled or tested in different environments. Some bugs appear only on one JDK version, making reproduction difficult.

Toolchains allow declaring clear requirements, such as "use JDK 21 to compile" or "run tests on JDK 17." The build tool locates a JDK satisfying that requirement and assigns it to the configured task.

### 1.1. Distinguishing Build JDK, Compiler, and Test Runtime

These three roles are frequently confused:

| Role | Responsibility | How to identify |
|---|---|---|
| Build JVM | Runs Gradle or Maven itself along with build tool plugins | `./gradlew -version`, `mvn -version`, or CI logs. |
| Java compiler | Compiles main and test sources into bytecode | Toolchain/compiler configured for the compile task. |
| Test JVM | Executes tests and application code during testing | Launcher/runtime configured for the test task or test plugin. |

For example, Gradle might run on JDK 21, use the JDK 21 compiler to produce Java 17-compatible bytecode, and run tests on JDK 17. These three choices serve three distinct purposes.

### 1.2. Toolchain Is Not Synonymous with `JAVA_HOME`

`JAVA_HOME` typically selects the JDK for starting the shell process or build tool. However, when a project uses toolchains, a task can be delegated to a different JDK than the one running Gradle/Maven.

For instance, `./gradlew -version` reports the JVM running Gradle. It does not automatically prove every `JavaCompile` task uses that same JVM. Likewise, `mvn -version` reports the JDK running Maven; Maven Compiler Plugin may invoke a compiler selected via a toolchain.

Therefore, when investigating multi-version builds, inspect both the build JVM and the JDK selected per task. Checking only `JAVA_HOME` is insufficient.

## 2. Distinguishing Toolchains from Source/Target and `--release`

This is the most crucial distinction when setting up multi-version builds. A toolchain picks the JDK executing the tool; `source`, `target`, and `--release` determine the Java level that source code may use or the emitted bytecode level.

### 2.1. `sourceCompatibility` and `targetCompatibility`

These two settings are often used to specify the language level and target bytecode version in a Java build. However, they do not select the JDK compiler on their own and do not fully constrain the standard APIs that source code can reference.

For example, if compiling with JDK 21 while setting only `targetCompatibility = 17`, the compiler may emit Java 17-level class files while source code still references an API introduced in Java 21. When running on Java 17, the application can fail with missing method or class errors.

### 2.2. `--release` Constrains Language, Bytecode, and Standard APIs Together

The `javac --release N` option instructs the compiler to compile against a supported Java release N. It combines constraints on the language level, class-file format, and permitted Java SE API set for that version.

For example, using a JDK 21 compiler while targeting Java 17:

```bash
javac --release 17 -d out src/com/example/App.java
```

The compiler rejects standard APIs introduced after Java 17. This helps catch certain Java 17 runtime compatibility errors early.

`--release` does not inspect external dependencies, native libraries, runtime behavior, or deployment configurations on its own. Nor does it select the JVM to run tests. Those require toolchains and dedicated testing.

### 2.3. Comparison Table

| Configuration | What it determines | What it does not determine |
|---|---|---|
| Build JVM / `JAVA_HOME` | JDK running Gradle or Maven | Does not necessarily decide compiler/test launcher when toolchains are configured. |
| Java toolchain | JDK used by the corresponding compile, test, or tool task | Does not automatically restrict APIs/bytecode down to a lower version. |
| `sourceCompatibility` | Java syntax/language level | Does not pick the JDK or fully constrain standard APIs. |
| `targetCompatibility` | Target class-file level | Does not guarantee referenced APIs exist on the target runtime. |
| `--release` | Java language level, class file, and standard APIs | Does not cover non-JDK dependencies or runtime behavior. |
| Test launcher/toolchain | JVM executing tests | Does not alter the compiler that compiled sources. |

A reliable setup typically picks a toolchain for the compiler, uses `--release` when targeting APIs/bytecode older than the compiler, and selects the matching runtime to run tests.

## 3. Selecting JDKs for Tasks with Gradle Java Toolchains

Gradle supports Java toolchains for tasks such as compile, test, and Javadoc. You can declare the desired JDK version in the build script to avoid relying on a machine's default JDK.

### 3.1. Project-Wide Toolchain Declaration

With Groovy DSL in `build.gradle`:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

This declaration instructs Gradle to pick a JDK with Java language version 21 for toolchain-aware Java tasks. Tasks such as `JavaCompile`, `Test`, and `Javadoc` can use the corresponding toolchain per Gradle configuration.

If you need to constrain the vendor, add a condition:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

Specify a vendor only when the project genuinely requires a specific distribution. Without that requirement, specifying only the language version keeps builds more portable across developer machines and CI.

### 3.2. Explicitly Specifying the Compiler for Compile Tasks

Gradle also allows selecting the compiler directly:

```groovy
tasks.withType(JavaCompile).configureEach {
    javaCompiler = javaToolchains.compilerFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

This is useful when a project has multiple task groups or needs separate compilers per source set. Check main, test, and generated-source compile tasks to verify all of them use the intended JDK.

### 3.3. Selecting a Separate Runtime for Tests

Tests can run on a different JDK from the compiler:

```groovy
tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

In this example, the test task executes on JDK 17. If the compiler uses JDK 21, ensure the emitted bytecode and used APIs can run on JDK 17, typically by setting `options.release = 17` on the appropriate compile tasks.

Combined example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.withType(Test).configureEach {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

This illustrates compiling with JDK 21 while preserving Java 17 compatibility and executing tests on JDK 17. In a real project, confirm that test sources, annotation processors, plugins, and dependencies also support this setup.

### 3.4. Inspecting JDKs Detected by Gradle

Gradle provides the `javaToolchains` task to list JDKs it detects:

```bash
./gradlew javaToolchains
```

You can inspect verbose logs when running a build:

```bash
./gradlew clean test --info
```

Read the logs to confirm which compiler and launcher were picked. `./gradlew -version` remains helpful for identifying the JVM running Gradle, yet task toolchain info is necessary to verify which JDK executes each task.

### 3.5. Missing Toolchain on the Machine

Gradle must find a JDK satisfying the requirement. Depending on configuration, the JDK may be discovered from existing installations or downloaded via a configured toolchain resolver. If no matching JDK is available and no download mechanism exists, the task may fail because no matching toolchain was found.

In CI, pre-install the required JDKs or configure a resolver/download mechanism in a controlled way. Do not let builds depend on a JDK path that exists only on one developer's machine.

Note that toolchains do not automatically enable an old Gradle version to run on a new JDK. The Gradle daemon itself must still run on a JDK supported by that Gradle wrapper version. Check Gradle's compatibility matrix before switching the build JVM.

## 4. Selecting JDKs for Compiler and Tests with Maven Toolchains

Maven also offers a toolchain mechanism so supporting plugins can use a selected JDK independently of the JDK running Maven. Setup usually has two parts: declaring installed JDKs on the machine and requesting the toolchain in the project.

### 4.1. Declaring Installed JDKs in `toolchains.xml`

The toolchain file typically resides at the user's `~/.m2/toolchains.xml` or a corresponding Maven configuration path. Example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
```

The path above is merely an example; replace it with the actual JDK path on your machine or CI agent. This file describes toolchains available to Maven locally; do not commit machine-specific local paths to the repository if other machines differ in layout.

### 4.2. Requesting a Toolchain in the Project

Use the Maven Toolchains Plugin to request a matching JDK:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <goals>
                <goal>toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>21</version>
                <vendor>temurin</vendor>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
```

The plugin finds a toolchain matching the request in `toolchains.xml` and binds it to the Maven session. Plugins supporting Maven Toolchains can then use the selected JDK.

### 4.3. Configuring the Compiler and Release Level

Maven Compiler Plugin can use the selected toolchain to invoke the compiler. At the same time, set `release` to constrain target APIs and bytecode:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
```

In this example, the toolchain can pick JDK 21 as the compiler while `release` compiles for Java 17. Ensure the compiler version is recent enough to support `--release 17`.

### 4.4. Running Tests on the Selected JDK

Maven Surefire and Failsafe can use Maven toolchains when supported by the corresponding plugin/provider. Check the actual configuration of your plugin version and verify the forked JVM running tests. If tests must run across multiple JDK versions, create separate CI jobs, each provisioning the corresponding toolchain/runtime.

Do not infer the test JVM solely from `mvn -version`. That command reports the JDK running Maven; tests may be forked under a JDK chosen by a toolchain or plugin configuration. Use Maven debug logs and runtime info printed inside tests to verify.

## 5. Multi-Version Compilation: Compiler and Runtime Can Differ

In projects supporting multiple Java versions, the compilation target often needs to be separated from the test execution environment. Three scenarios are common.

### 5.1. Build on a New JDK, Ship Bytecode for a Lower JDK

For instance, a team builds on JDK 21 while the product still supports Java 17 at runtime. Use a JDK 21 toolchain paired with `--release 17` (or the equivalent build-tool configuration).

```text
JDK 21 compiler
       |
       v
--release 17
       |
       v
Java SE level 17 bytecode and APIs
       |
       v
Run tests on JDK 17
```

`--release 17` makes the compiler reject standard APIs introduced in Java 18 or later. However, if external dependencies were built for Java 21 or require APIs missing in Java 17, the application can still fail at runtime. Check class-file versions and minimum JDK requirements across all dependencies.

### 5.2. Compiling and Testing on the Same JDK

This is the straightforward configuration when a product supports only one runtime version. Choose a unified toolchain for compilation and testing to minimize environment drift.

```text
JDK 21 compiler ---> Java 21 bytecode
       |
       v
JDK 21 test runtime ---> test suite
```

This setup confirms the application runs on the target JDK, yet does not prove it still runs on older JDKs if the product still claims support for them.

### 5.3. Running the Same Test Suite Across Multiple Runtimes

If the product supports Java 17 and Java 21, compile against the lowest supported API level and execute tests on both runtimes:

```text
                 Compile once
                 --release 17
                      |
            17-compatible artifact
                 /          \
                v            v
           Test on 17     Test on 21
```

Running on both versions exposes differences in standard libraries, security, charsets, timezones, GC, and runtime behavior. If the product supports only the new runtime, the test matrix can focus on the target version and deployed updates.

## 6. Designing a Toolchain Matrix for CI

A CI matrix should clearly state compiler, release level, and test runtime. Example:

| Job | Build JVM | Compiler toolchain | Release target | Test runtime | Purpose |
|---|---|---|---|---|---|
| Compatibility 17 | JDK 21 | JDK 21 | 17 | JDK 17 | Verify bytecode and behavior on minimum runtime. |
| Runtime 21 | JDK 21 | JDK 21 | 21 | JDK 21 | Verify target JDK environment. |
| Runtime update | JDK 21 | JDK 21 | 21 | Deployed JDK 21 update | Verify actual build/vendor release. |

This matrix is illustrative. Projects must pick versions based on their published support policy. When supporting multiple JDKs, test at least the minimum and target versions; intermediate versions are needed only when driven by product commitments or specific risks.

### 6.1. Keeping Compiler and Test Runtime Independent

A CI job can build the artifact once and then run tests across multiple runtimes, provided the artifact is built with matching bytecode/API levels. This helps distinguish compiler failures from runtime failures.

If each runtime job rebuilds the artifact itself, record the compiler and dependencies used. Otherwise, differing results may stem from different artifacts rather than solely from the JVM.

### 6.2. Checking Tasks Beyond Compile and Test

Toolchains can affect many other tasks:

- Javadoc: tool versions may interpret tags, modules, and APIs differently.
- Annotation processors: run inside the compiler environment and can depend on JDK version.
- Code generators: may call JDK APIs or emit source/bytecode for specific versions.
- Integration tests: may spawn child JVMs or external processes whose JDKs must be identified separately.
- Bytecode analysis tools: may not yet understand newer class-file versions.
- Packaging and signing: may invoke JDK tools such as `jar`, `jarsigner`, or `jlink`.

Do not assume selecting a compile toolchain automatically configures every child process or plugin. Check plugin documentation and actual logs.

## 7. Verifying Which Toolchain Is Actually Used

Declaring configuration is only a request. Verify the build tool located the right JDK and assigned it to the right task.

### 7.1. Checking in Gradle

Run:

```bash
./gradlew -version
./gradlew javaToolchains
./gradlew clean test --info
```

These three commands provide three perspectives:

- `-version`: JVM running Gradle and Gradle wrapper version.
- `javaToolchains`: JDKs detected by Gradle.
- `clean test --info`: detailed logs during compile and test runs, revealing selected compilers/launchers.

If a toolchain is not found, inspect installed JDKs, discovery paths, vendor specs, and toolchain-download resolver settings. Do not arbitrarily change `JAVA_HOME` until you understand which toolchain each task uses.

### 7.2. Checking in Maven

Run:

```bash
mvn -version
mvn -X clean verify
```

`mvn -version` shows the JVM running Maven. Debug logs show how toolchains and plugins pick compilers/test runtimes. You can print `java.version`, `java.vendor`, and `java.home` from inside a test to confirm the JVM executing tests.

Example:

```java
import org.junit.jupiter.api.Test;

class RuntimeInfoTest {
    @Test
    void printRuntime() {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
```

In a real project, log this information at the start of the test job rather than keeping a test whose sole purpose is printing versions. The goal is explicit evidence of which JVM ran the tests.

### 7.3. Verifying Class Files and API Level

Use `javap -verbose` to inspect class-file major versions:

```bash
javap -verbose -classpath build/classes/java/main com.example.App
```

In the output, locate `major version`. Common levels:

| Java | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Class-file metadata confirms which Java version the bytecode targets. It does not prove external dependencies or APIs are compatible; running on the target runtime remains mandatory.

## 8. Common Errors When Using Toolchains

### 8.1. Build Tool Running on an Unsupported JDK

Toolchains select compilers/test runtimes for tasks, yet the Gradle daemon or Maven still needs a JDK supported by that build tool version. Running an older Gradle wrapper on a newer unsupported JDK can fail before Java toolchain tasks ever run.

Consult the Gradle/Maven compatibility matrix and upgrade the build tool when needed. Do not confuse a Gradle daemon startup failure with a missing Java toolchain error.

### 8.2. Setting Only Target Version Without Constraining APIs

Setting `targetCompatibility = 17` does not guarantee sources use only Java 17 APIs. If a JDK 21 compiler allows calling a new API, bytecode gets emitted yet fails at runtime on JDK 17.

When older runtimes must be supported, use `--release` or corresponding `options.release` configuration, then run tests on the oldest supported runtime.

### 8.3. Right Compiler, Wrong Test JDK

A build might compile with JDK 17 while the test task defaults to JDK 21, or vice versa. This causes tests to pass while production runs a different version.

Configure a dedicated test launcher/toolchain and verify `java.version` inside the test process. For integration tests spawning child processes, check those child process JDKs as well.

### 8.4. Requested Toolchain Not Installed or Downloadable

When no matching JDK is found, the build tool reports no matching toolchain exists. Pre-install JDKs on agents or configure toolchain provisioning. In CI, explicitly fix download sources, vendors, and versions to avoid accidental environment drift.

### 8.5. Unpinned Vendor or Update Build

Specifying only a language version allows machines to pick different distributions. That is flexible and suits many projects. However, if production requires a specific vendor/build, constrain that condition and verify CI agents have the exact JDK installed.

Do not hardcode absolute local JDK directory paths inside shared build scripts. Use toolchain criteria and provision installations per environment.

### 8.6. Annotation Processors or Plugins Using a Different JDK

Some plugins and annotation processors run inside the compiler process, while others spawn separate processes. Selecting a toolchain for `JavaCompile` does not mean every plugin in the build uses that same JDK.

When errors appear only in generated code, inspect processor versions, plugin versions, and the JVM of that process. Upgrade plugins or configure separate toolchains if supported by the plugin.

## 9. Workflow for Implementing Toolchains in a Project

A controlled rollout consists of these steps:

1. **List JDKs to support.** Explicitly record minimum version, build version, test version, and production runtime.
2. **Verify the build tool.** Confirm the Gradle wrapper or Maven and plugins support the build JDK.
3. **Configure the compiler toolchain.** Choose JDK and vendor if required; eliminate dependence on per-machine `PATH`.
4. **Configure release level.** Use `--release` when compiling on a newer JDK while shipping for a lower runtime.
5. **Configure the test runtime.** Pick launchers/toolchains for unit tests, integration tests, and child processes.
6. **Provision JDKs in CI.** Pre-install or configure toolchain download resolvers; record versions and builds.
7. **Verify via logs and class files.** Check build JVM, compiler, test JVM, and bytecode major versions.
8. **Run the test matrix.** Test on the minimum supported runtime and target runtime; expand where specific risks exist.
9. **Record results.** Archive configuration, verification outputs, and test results so builds are reproducible.

## 10. Pre-Acceptance Checklist for Multi-Version Builds

- [ ] JDK running Gradle/Maven identified and verified supported by the build tool.
- [ ] Compiler toolchain declared in build scripts or Maven toolchains.
- [ ] Target API/bytecode level set with `--release` if lower runtimes must be supported.
- [ ] Test launcher/runtime configured separately for each version to test.
- [ ] Annotation processors, generators, plugins, and child processes verified on appropriate JDKs.
- [ ] CI provisions exact JDKs or toolchain resolvers; no reliance on personal local setups.
- [ ] Toolchain logs and `java.version` verified inside test processes.
- [ ] Artifact class-file versions verified.
- [ ] Tests executed on minimum runtime and target runtime per support policy.
- [ ] Configuration and evidence saved to reproduce build outputs.

## 11. Conclusion

Toolchains let Java projects explicitly select JDKs for compilers, tests, and supporting tasks. They eliminate reliance on each machine's default JDK and keep CI, developer workstations, and test environments aligned under consistent rules.

To build accurately across multiple versions, distinguish the build JVM, compiler toolchain, bytecode/API release level, and test JVM. Toolchains select the tools; `--release` constrains language, class file, and standard APIs; test launchers define the executing runtime. Combining these configurations with log checks, class-file inspection, and test matrices delivers clear evidence that artifacts are compiled and executed on the exact specified JDK versions.

# Choosing Verification Methods When Designing a Java Toolchain

Designing a Java toolchain is not just choosing a JDK and configuring Maven or Gradle. A team needs to prove that the compiler, target APIs, bytecode, runtime, dependencies, and build process all meet product requirements. Each requirement needs an appropriate kind of evidence; a single `java -version` command or a syntactically valid POM configuration cannot prove that the entire toolchain works properly.

Choosing verification methods starts from what needs to be proven and the risk if it is wrong. Then select configuration checks, compile-time checks, bytecode checks, runtime checks, behavioral tests, dependency compatibility checks, or reproducibility checks. This article explains how to build an evidence matrix, use `javac` and JDK tools, inspect Maven/Gradle, design a CI matrix, and determine when deeper verification is needed.

## 1. What to Verify in a Java Toolchain?

A Java toolchain has many independent components:

- The JDK used to run Maven, Gradle, or scripts.
- The JDK/compiler used to compile source code.
- The Java release that the source code is allowed to use.
- The generated class-file version.
- The lowest runtime supported by the product.
- Compatible dependencies and annotation processors.
- Tests, packaging, and artifacts being produced properly.
- Operating system, CPU architecture, and CI environment.
- Reproducibility of build outputs.

Before choosing verification methods, clearly state requirements as verifiable propositions. For example:

| Requirement | Proposition to Prove |
|---|---|
| Build uses JDK 17 | The compiler actually selected is JDK 17 |
| Product supports Java 17 | Source only uses Java 17-compatible APIs and bytecode |
| Minimum runtime is 17 | Artifact runs on a real JVM 17 |
| Supports Windows and Linux | Build/tests pass on runners for both operating systems |
| Dependencies are compatible | Required libraries work on the target runtime |
| Reproducible build | Same source and toolchain produce equivalent artifacts according to defined criteria |

Avoid using a single check to answer multiple different questions. For example, class-file major version 61 proves the bytecode has Java 17's version; it does not prove the code only uses Java 17 APIs or runs on every operating system.

## 2. Choosing Verification by Risk

A practical approach is to rank risks by impact and likelihood. Changes involving the JDK, compiler, foundational dependencies, or minimum runtime usually require more layers of evidence than a minor configuration change.

| Risk | Appropriate Verification |
|---|---|
| Maven/Gradle selects the wrong JDK | Print runtime version, Java home, and toolchain selection |
| Accidentally using APIs newer than target release | Compile with `javac --release` |
| Generating wrong bytecode target | Inspect with `javap -verbose` |
| Failing on minimum runtime | Run tests/smoke tests on the minimum JDK |
| Dependency calls internal JDK APIs | `jdeps --jdk-internals` and dependency checks |
| Differences across OS | CI matrix by OS/architecture |
| Unintended changes in build output | Build twice and compare artifacts |
| Incorrect business behavior | Unit, integration, and acceptance tests |

Not every project needs every verification on every commit. Put cheap and fast checks on every pull request; more time-consuming checks can run on a schedule, at release time, or when upgrading the JDK/dependencies.

## 3. Distinguishing Configuration, Inspection, and Execution Evidence

Three types of evidence are often confused:

1. Declarative configuration states what the team wants the toolchain to do. For example, a POM declaring release 17 or Gradle requesting `JavaLanguageVersion` 17.
2. Configuration and toolchain selection inspection shows which configuration the tool actually read and selected. For example, effective POM, Maven toolchain logs, or Gradle `javaToolchains`.
3. Execution evidence shows what the compiler/runtime actually did. For example, compiling with `javac`, inspecting class files, running tests on JDK 17, and reading the results.

A valid configuration may still not take effect due to a parent POM, profile, Gradle property, IDE, or CI override. Therefore, it is necessary to check both the declared values and what the tool actually selected.

## 4. Identifying the Actual JDK of the Shell and Build Tool

Start by recording versions and paths:

Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java -All | Select-Object Source
Get-Command javac -All | Select-Object Source
java -version
javac -version
mvn -version
~~~

Linux/macOS:

~~~bash
printf 'JAVA_HOME=%s\n' "${JAVA_HOME:-<unset>}"
command -v java
command -v javac
java -version
javac -version
mvn -version
~~~

`mvn -version` displays the Java version and Java home that the Maven runtime is using. Gradle Wrapper `--version` displays the JVM running Gradle. This checks the build tool's runtime; the compiler toolchain may be selected separately.

Save the output in CI so that when a build changes, the team can compare the JDK vendor, version, Java home, Maven/Gradle version, and OS. Only print the necessary variables; do not dump the entire environment because it may contain secrets.

## 5. Checking the JDK Compiler and Java Release

If the product supports Java 17, a reliable way to verify target APIs is to compile with `--release 17`:

~~~powershell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d out src\main\java\demo\App.java
~~~

`--release` controls the Java language, class-file target, and the set of Java SE APIs allowed for that release. This is an important difference compared to only setting `-source` and `-target`.

For example:

~~~powershell
javac -source 17 -target 17 App.java
~~~

The two options above control syntax and bytecode target, but when the compiler runs on a newer JDK, the code can still reference APIs newer than Java 17. As a result, it may compile successfully but fail when running on JVM 17.

Use `--release` so the compiler also checks target APIs. If the project needs to verify a specific JDK compiler, explicitly record the actual JDK via `mvn -version`, `javac -version`, or toolchain logs.

## 6. Checking Class-File Version with javap

Every class file has a major version. Some common milestones:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

After compiling, run:

~~~powershell
javap -verbose out\demo\App.class | Select-String "major version"
~~~

If the build targets Java 17, the expected output is:

~~~text
major version: 61
~~~

Bytecode inspection is useful when verifying artifacts, especially when a build has multiple modules or plugins. However, the right major version alone is not enough to prove API compatibility. A class file with version 61 can still contain references to APIs that do not exist on Java 17 if compiled with an improper source/target configuration.

## 7. Verifying APIs and JDK Dependencies

Some APIs were added after the target release. For example, `List.getFirst()` belongs to the `SequencedCollection` API from Java 21. If the product supports Java 17, source code calling this API must be rejected when compiling with `--release 17`.

Check dependencies and internal JDK references with `jdeps`:

~~~powershell
jdeps --jdk-internals app.jar
~~~

This command helps detect reliance on JDK internal APIs, which may change or have access restricted in newer JDKs. It does not replace running tests on the target runtime.

For dependencies, inspect the library tree:

Maven:

~~~powershell
.\mvnw.cmd dependency:tree
~~~

Gradle:

~~~powershell
.\gradlew.bat dependencies
~~~

When upgrading the JDK or foundational libraries, review release notes, compatibility matrices, and warnings from dependencies. An application that compiles does not mean every library runs properly on the new runtime.

## 8. Verifying the Minimum Runtime

Compiling on a newer JDK with `--release 17` does not prove the application runs on JVM 17. The runtime can differ from the compiler, and some errors only surface when classes are loaded or when code executes.

The direct way to verify is to run the artifact on the lowest supported JDK:

~~~powershell
$env:JAVA_HOME = 'C:\Java\jdk-17'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
java -version
.\mvnw.cmd clean verify
~~~

If the product supports Java 17 and 21, CI should have jobs running tests on both runtimes. For server applications, add a smoke test that starts the application, runs a health check, and sends a representative request.

Do not use the current JDK as evidence for an older runtime. If the local environment only has JDK 24, compiling with `--release 17` and running on JDK 24 only proves the artifact works on JDK 24; a JDK 17 runner is still needed to confirm the minimum runtime.

## 9. Verifying Behavior with Unit, Integration, and Smoke Tests

Choose test levels according to risk scope:

| Test Type | When to Use | What It Proves |
|---|---|---|
| Unit test | Independent class/method logic | Small rules work correctly |
| Integration test | Connecting DB, filesystem, HTTP, or messaging | Components coordinate properly |
| Smoke test | Starting the app and calling main flows | Artifact can launch in a representative environment |
| End-to-end test | User flows across multiple services | System satisfies end-to-end scenarios |
| Compatibility test | Upgrading JDK or dependencies | Behavior is supported on target runtime/version |

A toolchain might compile successfully yet tests fail due to reflection, serialization, locale, timezone, TLS, encoding, or native libraries. Select tests based on the risk areas when changing JDKs.

Keep tests as stable and environment-independent as possible. If tests depend on clock, timezone, or filesystem, configure explicit values and document assumptions in CI.

## 10. Configuring and Verifying Maven Toolchains

The Maven runtime and compiler JDK can be different. Maven Toolchains allows selecting the compiler JDK based on project requirements.

Example `toolchains.xml` settings:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
  <toolchain>
    <type>jdk</type>
    <provides>
      <version>17</version>
      <vendor>any</vendor>
    </provides>
    <configuration>
      <jdkHome>C:\Java\jdk-17</jdkHome>
    </configuration>
  </toolchain>
</toolchains>
~~~

This is an example for Windows; on Linux/macOS, `jdkHome` must be the runner's actual JDK path. The `toolchains.xml` file is usually located in the build user's `.m2` directory.

The POM can request a JDK toolchain and set the release:

~~~xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
  <plugins>
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
            <version>17</version>
          </jdk>
        </toolchains>
      </configuration>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <version>3.13.0</version>
      <configuration>
        <release>${maven.compiler.release}</release>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Verifying Maven:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd help:effective-pom
.\mvnw.cmd -X clean verify
~~~

- `-version` shows the JVM running Maven.
- `effective-pom` shows the compiler configuration after parent/profile inheritance.
- `-X` shows detailed toolchain/compiler selection in the debug log.

Do not conclude that the compiler uses JDK 17 solely from `mvn -version`; that command reports Maven's JVM. Check the toolchain and compiler plugin logs to confirm the JDK used for compilation.

## 11. Configuring and Verifying Gradle Java Toolchains

Gradle can select the JDK for compilation and testing via Java toolchains.

Groovy DSL:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Kotlin DSL:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Verification:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat javaToolchains
.\gradlew.bat clean test
~~~

`--version` shows the JVM running Gradle; `javaToolchains` lists the toolchains Gradle detects; `test` confirms the tasks actually run. Also check `org.gradle.java.home`, the Gradle JVM in the IDE, and toolchain config if results differ from expectations.

The Gradle daemon may continue running with a previously started JVM. After changing the environment, you can stop the daemon and run again:

~~~powershell
.\gradlew.bat --stop
~~~

## 12. Checking Annotation Processors and Generated Sources

Annotation processors run during compilation and can depend on JDK/compiler APIs. When upgrading the JDK or changing toolchains, verify:

- Whether the processor version supports the target JDK/compiler.
- Whether the processor is declared in `annotationProcessorPath` or the corresponding configuration.
- Whether generated sources compile cleanly.
- Whether generated sources produce warnings or use APIs newer than the target release.
- Whether the build produces consistent results across runs.

Do not edit generated files manually and treat that as evidence. Fix the configuration or processor version, then run a clean build so sources are regenerated from scratch.

## 13. Verifying Dependency and Module Compatibility

A new toolchain can expose issues in dependencies:

- Libraries using JDK internal APIs.
- Libraries not yet supporting the new runtime.
- Module descriptors requiring modules not present in the runtime image.
- Native libraries lacking binaries matching the OS/architecture.
- Multi-release JARs selecting different implementations by Java version.

Use the dependency tree, `jdeps`, and integration tests to pinpoint the source of issues. If the application uses JPMS, check the module path and module descriptors using `javac`/`java` with the appropriate module options.

For native dependencies, a CI matrix covering the actually supported OSes and architectures is required. A passing build on Windows x64 does not prove a native library works on Linux ARM64.

## 14. Verifying Build Reproducibility

A reproducible build is the ability to produce identical artifacts according to defined criteria when using the same source and equivalent toolchain environment.

A basic workflow:

1. Check out the same commit into two clean workspaces.
2. Use the same JDK, Maven/Gradle, and dependency locks/versions.
3. Run a clean build in both workspaces.
4. Compare artifact checksums.
5. If they differ, check timestamps, file ordering, generated metadata, absolute paths, and environment-dependent content.

With Maven, you can set `project.build.outputTimestamp` to standardize archive timestamps when plugins support it:

~~~xml
<properties>
  <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

The timestamp example above only illustrates a fixed value; projects should choose an appropriate timestamp policy, usually derived from source-control commit metadata.

Not every artifact has to be byte-for-byte identical. Define the criteria upfront: exact checksum match, identical archive contents after stripping variable metadata, or merely equivalent API/behavior.

## 15. Choosing an Appropriate CI Matrix

The CI matrix should cover combinations that are meaningful for the product:

| Axis | Example Choices |
|---|---|
| Java Runtime | Minimum supported JDK, current supported LTS |
| OS | Windows, Linux, macOS if supported |
| Architecture | x64, ARM64 if native dependencies exist |
| Build tool | Maven Wrapper or Gradle Wrapper |
| Test scope | Unit on every commit; integration/smoke on PR or release |

Example policy:

- Every pull request: compile with target `--release`, unit tests, and lint.
- Every pull request: run tests on the minimum supported runtime.
- Scheduled: run on a newer LTS JDK to detect deprecations/removals early.
- Before release: full integration, smoke tests, dependency analysis, and reproducible build check.
- When upgrading JDK: run the full relevant OS/architecture matrix.

There is no need to run every combination on every commit if CI time becomes too high. Choose the matrix based on risk, then place remaining checks on a nightly schedule or release gate.

## 16. Java Probe Example for Toolchain

Create `ToolchainProbe.java`:

~~~java
public final class ToolchainProbe {
    private ToolchainProbe() {
    }

    public static void main(String[] args) {
        int feature = Runtime.version().feature();
        if (feature < 17) {
            throw new IllegalStateException("Java 17 or newer is required");
        }
        System.out.println("Toolchain check OK");
    }
}
~~~

Compile with Java 17 APIs and bytecode:

~~~powershell
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d out ToolchainProbe.java
~~~

Run:

~~~powershell
java -cp out ToolchainProbe
~~~

Stdout:

~~~text
Toolchain check OK
~~~

Inspect bytecode:

~~~powershell
javap -verbose out\ToolchainProbe.class | Select-String "major version"
~~~

For release 17, the expected major version is 61. The program checks the minimum runtime feature version, but to confirm a real Java 17 runtime, it still must be run on JDK/JRE 17 in CI.

## 17. Negative Testing: Proving Newer APIs Are Rejected

Create `NewerApiProbe.java`:

~~~java
import java.util.List;

public final class NewerApiProbe {
    public static void main(String[] args) {
        List<String> names = List.of("Java");
        System.out.println(names.getFirst());
    }
}
~~~

`List.getFirst()` was added in Java 21. When the product targets Java 17, the following command must fail:

~~~powershell
javac --release 17 NewerApiProbe.java
~~~

If running a newer compiler with only `-source 17 -target 17`, APIs on the compiler's JDK might still be visible. That is why API verification needs `--release` rather than just checking the class-file version.

Negative testing is very useful: it proves the compiler policy actually blocks an API beyond the target release, rather than only proving that a valid example compiles.

## 18. Verification Selection Matrix

| Question | Minimum Check | Stronger Evidence |
|---|---|---|
| Which JDK is the tool running on? | `java -version`, `mvn/gradle --version` | Compiler toolchain selection logs |
| Does the compiler have the right release? | POM/Gradle config | Compile with `--release` and negative test |
| Is the bytecode the right version? | `javap` major version | Check artifacts of all modules |
| Are APIs compatible? | `javac --release` | Dependency analysis and runtime tests |
| Does the minimum runtime run? | Smoke test | Full test suite on minimum JDK |
| Are dependencies compatible? | Dependency tree | `jdeps`, integration tests, vendor matrix |
| Are OS/architectures supported? | CI matrix | Native integration tests on each runner |
| Is the build reproducible? | Build twice | Compare checksums from two clean workspaces |

If risk is low, choose the minimum check that can prove the requirement. If risk is high or the change is wide-reaching, combine multiple independent layers of evidence.

## 19. Mistakes When Verifying a Toolchain

| Mistake | Why It Is Insufficient | Correct Approach |
|---|---|---|
| Only running `java -version` | Does not show compiler JDK or separate toolchain | Check compiler selection and build tool |
| Only reading POM/`build.gradle` | Parent, profile, or IDE may override | Inspect effective config and execution logs |
| Only checking major version | Does not prove API compatibility | Compile with `--release` |
| Compiling with a new JDK and running on that same JDK | Does not prove minimum runtime | Run on the lowest supported runtime |
| Only running unit tests | May miss integration, native libraries, and startup | Add integration/smoke tests based on risk |
| Only testing on Windows | Does not prove Linux/macOS | CI matrix for target OSes |
| Only checking dependency tree | Does not prove dependencies actually run | `jdeps` and integration tests |
| Only building once | Does not detect environment-induced artifact changes | Build in two clean workspaces and compare |
| Using `source`/`target` instead of `--release` | Can reference newer APIs | Use `--release` |

## 20. Process for Designing a Verification Plan

When starting to design a toolchain, follow these steps in order:

1. Record the minimum runtime, compiler JDK, supported OS/architecture, and build tool.
2. Identify which requirements can be verified by configuration and which require actual execution.
3. Choose fast checks for every pull request.
4. Choose runtime/dependency/OS checks for nightly or release.
5. Add negative tests to prove policies block wrong configurations/APIs.
6. Save versions and toolchain logs in CI.
7. Define which artifacts or outputs must be archived as evidence.
8. Write clear pass/fail criteria for each check.
9. When upgrading JDK/plugins, re-run affected checks.
10. Review the verification plan alongside toolchain changes, not just the configuration files.

A good verification plan has an owner, runner, command, expected result, and log storage location. When a build fails, others can reproduce it and understand exactly which proposition has not been proven.

## 21. Verification Selection Checklist

- [ ] Minimum runtime and compiler JDK are defined separately.
- [ ] Actual JDK of Maven/Gradle is recorded.
- [ ] POM/Gradle effective config is inspected.
- [ ] Compilation uses `--release` for target Java APIs.
- [ ] Negative tests exist for APIs newer than the release when appropriate.
- [ ] Class-file major version is checked on important artifacts.
- [ ] Minimum runtime is tested with actual execution.
- [ ] Dependencies and JDK internal APIs are checked when there is risk.
- [ ] Annotation processors and generated sources are verified.
- [ ] Target OS/architectures have appropriate CI runners.
- [ ] Unit/integration/smoke tests exist according to risk.
- [ ] Reproducible build verification process exists if required.
- [ ] Logs record JDK vendor/version, build tool, and OS.
- [ ] Each verification has an expected result and owner.
- [ ] Verification plan is re-run when upgrading the JDK or build plugins.

Choose verification methods by starting from the requirement to be proven. Configuration states what the team wants; toolchain selection logs show what the tool chose; compilation, bytecode inspection, runtime tests, and CI matrices show the actual result. Combining layers of evidence according to risk makes a Java toolchain explainable, reproducible, and trustworthy when changes occur.

## References

- Oracle Java SE 17 — The javac Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Oracle Java SE 17 — The javap Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle Java SE 17 — The jdeps Command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html
- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains.html
- Apache Maven Compiler Plugin: https://maven.apache.org/plugins/maven-compiler-plugin/
- Apache Maven — Guide to Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Gradle — Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — JavaCompile: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html

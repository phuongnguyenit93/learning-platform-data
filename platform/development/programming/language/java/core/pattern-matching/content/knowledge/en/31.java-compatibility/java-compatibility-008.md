# Checking a Project's Toolchain When Using Java Pattern Matching

A piece of code using a `record pattern` or `case Type variable when ...` may **compile successfully on a developer's machine** yet fail in CI, the IDE, or the deployment container. The cause often lies not in the pattern matching logic itself, but in the **toolchain**: the actual JDK version used for compilation, the `--release` language level, the JDK selected by Maven/Gradle, the JVM running the program, and IDE/test-specific configurations.

This lesson belongs to **Java Core Pattern Matching → Java Compatibility**, guiding how to **check a project's toolchain end-to-end** before using new language features. The focus is on Java 16–21 features commonly encountered in pattern matching, especially **record patterns** and **pattern matching for switch** finalized in **Java 21**.

> **Important principle:** "Having JDK 24 installed on the machine" does not mean "the project is compiling for Java 24"; "`javac --release 21` succeeds" also does not mean "the application will definitely run on JVM 17". You must separate **the JDK running the compiler**, **the target level**, **the dependencies**, and **the JVM actually running the application**.

## 1. What Does a Java Project's Toolchain Consist Of?

A **Java toolchain** is not just a single `java` command in the terminal. For a typical project, you need to know:

1. **The JDK running the compiler**: for example, `javac` from JDK 21 or JDK 24.
2. **The source/release level**: which version's syntax and APIs the Java compiler is instructed to accept.
3. **The build tool and wrapper**: which version of Maven or Gradle is executing the build; whether the wrapper is pinned in the repo.
4. **The JDK selected by the build tool**: this may differ from the JDK running Maven/Gradle itself.
5. **The JVM running unit/integration tests**: tests may run with a different JVM than the compilation JVM.
6. **The production JVM**: which version the Docker image, server, CI/CD runtime, or customer's device is running.
7. **The IDE project SDK / language level**: IntelliJ IDEA, Eclipse, or VS Code may select a different SDK from the shell environment variables.
8. **Dependencies and plugins**: libraries built on a different Java version, or build plugins too old to understand a new target.

A configuration must align **across all stages**:

~~~text
Source code + language level
          |
          v
JDK compiler --release + build plugins
          |
          v
.class bytecode + dependencies
          |
          v
Test JVM ---------> CI JVM ---------> Deployment JVM
~~~

If even one stage is misaligned, a project can be "green" on a personal machine yet "red" on another system.

## 2. Know Exactly Which Java Version Each Pattern Matching Feature Requires

| Language feature | First stable release | Sign in source code |
| --- | --- | --- |
| Classic `instanceof` + cast | Available before Java 8 | `if (x instanceof String) { String s = (String) x; }` |
| Switch expression | Java 14 (JEP 361) | `return switch (x) { case 1 -> "one"; default -> "other"; };` |
| Pattern matching for `instanceof` | Java 16 (JEP 394) | `if (x instanceof String text)` |
| Records | Java 16 (JEP 395) | `record Point(int x, int y) {}` |
| Sealed classes/interfaces | Java 17 (JEP 409) | `sealed interface Shape permits Circle, Square` |
| Record patterns | Java 21 (JEP 440) | `case Point(var x, var y) -> ...` |
| Pattern matching for `switch` | Java 21 (JEP 441) | `case String text -> ...` and `when` guard |

These milestones are **stable feature versions**, not the first experimental preview appearances. For instance, pattern matching for switch went through preview releases, but the finalized syntax in Java 21 includes the `when` guard. If you need to use the finalized syntax, choose **Java 21 or later** and do not enable preview just to use a feature that is already standard.

**Note on APIs:** `String.isBlank()` has existed since Java 11. Code using type patterns might only need the Java 16 language level, but if it also calls an API introduced in a newer version, the target must also support that API. The toolchain must verify **both syntax and APIs**.

### Do Not Guess the Version From the `.java` Extension

A `.java` file does not carry language version metadata. The exact same source code can be:
- Valid in Java 21 but invalid in Java 17.
- Valid in Java 17 syntax yet calling an API unavailable in Java 17.
- Compiled on a new JDK and producing bytecode that an older runtime cannot load.

To confirm, you must run the compiler **with the actual configured target**.

## 3. First Step: Check `java`, `javac`, and `JAVA_HOME`

Open the terminal **used to build the project** and run:

~~~bash
java -version
javac -version
~~~

`java -version` shows the launcher/runtime being invoked; `javac -version` shows the compiler being invoked. Both should be checked because `PATH` may contain different JDKs.

On Linux/macOS:

~~~bash
echo "$JAVA_HOME"
command -v java
command -v javac
java -version
javac -version
~~~

On Windows PowerShell:

~~~powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
where.exe java
where.exe javac
java -version
javac -version
~~~

**How to interpret:**

- `JAVA_HOME` is the JDK location used by certain tools; its value **does not automatically change the `PATH`** of every shell.
- `java` and `javac` may come from different paths; you need to see which command the shell actually resolves.
- The IDE may launch with different environment variables than the terminal.
- Maven/Gradle may use a **separately configured JDK toolchain**, even if the launcher runs from another JDK.

If `javac` is not found, the machine may only have a runtime installed or `PATH` may not point to the compiler. The Java Compiler API and `javac` require an environment with compilation tools; having only an old JRE will not suffice.

**Do not draw conclusions from a single version line.** Check the project's actual build command as well.

## 4. Distinguish Between the Running JDK and the `--release` Target

With `javac` from a sufficiently new JDK, you can instruct it to compile for an older Java version using:

~~~bash
javac --release 21 ToolchainSmokeTest.java
~~~

`--release 21` controls the **syntax level**, **target class file format**, and the **public Java Platform APIs** available for the supported release. This is the preferred approach when cross-compiling with a newer JDK.

Comparison:

| Option | Role | Limitations to remember |
| --- | --- | --- |
| `javac --release 21` | Compiles with Java 21 language/API/platform target within the capabilities of the current JDK | Does not turn the running JVM into Java 21; does not verify dependencies outside the Java Platform |
| `javac -source 21 -target 21` | Selects source grammar and bytecode target | Does not provide the same guarantee against using newer Java Platform APIs as `--release` |
| `java -version` | Shows the JVM selected by the launcher | Does not definitively show the compiler used in Maven/Gradle |
| `javac -version` | Shows the compiler version invoked directly | Does not definitively show which compiler the IDE/toolchain selected |
| `java --enable-preview` | Enables matching preview features at runtime when genuinely needed | Does not automatically make Java 21 syntax supported on JVM 17 |

**Key takeaway:** If the machine has JDK 24 installed, `javac --release 21` can still produce class files that run on Java 21, provided the source/APIs/dependencies are compatible. You must **test on JVM 21** to confirm the real system, because building on JDK 24 is not a JDK 21 runtime test.

Conversely, `javac --release 17` **cannot compile** source code containing record patterns and pattern matching for switch using Java 21 syntax. No flag automatically "backports" the Java 21 language down to Java 17.

### The Trap of a Failed Compilation

After a successful compilation, if you re-run `javac --release 17 ...` and the compiler reports an error, an old `.class` file from the previous build may still remain in the directory. **Do not run an old class file and assume the Java 17 build succeeded.** Always use a clean build directory for each check.

## 5. A Java 21 Example for Smoke-Testing the Toolchain

A smoke test should use **the exact features the module needs**, rather than just printing `"Hello World"`. The example below simultaneously tests:

- `sealed interface` and `record` implementations.
- Record pattern `Greet(User(var name))` and `when` guard.
- `switch expression` returning results from subtypes.
- A fallback branch when a nested record does not match.
- Handling a `null` selector with `case null`.

Create the file **`ToolchainSmokeTest.java`**:

~~~java
public class ToolchainSmokeTest {
    sealed interface Task permits Greet, Add, Ping {}

    record User(String name) {}
    record Greet(User user) implements Task {}
    record Add(int left, int right) implements Task {}
    record Ping() implements Task {}

    static String handle(Task task) {
        return switch (task) {
            case Greet(User(var name))
                    when name != null && !name.isBlank() ->
                    "Hello, " + name;
            case Greet(var user) -> "Invalid greeting";
            case Add(var left, var right) -> "Sum: " + (left + right);
            case Ping() -> "Pong";
            case null -> "No task";
        };
    }

    public static void main(String[] args) {
        System.out.println(handle(new Greet(new User("Mai"))));
        System.out.println(handle(new Greet(new User("   "))));
        System.out.println(handle(new Greet(null)));
        System.out.println(handle(new Add(2, 3)));
        System.out.println(handle(new Ping()));
        System.out.println(handle(null));
    }
}
~~~

### Compile and Run With JDK 21 or Later

~~~bash
javac --release 21 -encoding UTF-8 ToolchainSmokeTest.java
java ToolchainSmokeTest
~~~

Output:

~~~text
Hello, Mai
Invalid greeting
Invalid greeting
Sum: 5
Pong
No task
~~~

**Explanation:**

- `Greet(User("Mai"))` matches the nested record pattern, passes the valid-name guard, and returns `"Hello, Mai"`.
- `Greet(User("   "))` matches the structure but fails the guard, so it selects `case Greet(var user)`.
- `Greet(null)` does not match the nested `User(var name)`; the fallback matches the `Greet` record and returns `"Invalid greeting"`.
- `Add(2,3)` is deconstructed into two integers; `Ping()` is a record with no components.
- The `null` selector is handled explicitly. The `switch expression` does not need `default` because the subtypes exhaustively cover a sealed hierarchy and a null branch is present.

### Negative Check: Older Targets Must Be Rejected

On a sufficiently new JDK that supports both releases, run separately:

~~~bash
javac --release 17 ToolchainSmokeTest.java
~~~

**Expected:** The compiler **rejects** it because the example's patterns and `switch` patterns require Java 21. Exact error messages vary by JDK version; do not rely on a fixed diagnostic wording.

In a check with the Java Compiler API on **JDK 24**, a stripped-down version using `sealed + record pattern + switch` produced:

~~~text
release 21: COMPILED; errors=0
release 17: REJECTED; errors=2
~~~

This is a **version-target verification result**, not a performance benchmark. The exact error count may differ if source code, flags, or compiler change; the essential point is the expected pass/fail outcome.

## 6. Understanding Class-File Version Errors and Runtime Mismatch

Java compiles into `.class` bytecode containing a **class file major version**. A JVM that is too old cannot load bytecode targeted for a newer version. Common milestones include:

| Java target | Class file major version |
| --- | --- |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

You can inspect the compiled class file version with:

~~~bash
javap -verbose ToolchainSmokeTest
~~~

Look for the line `major version: 65` when the class is built with target Java 21; if you use a newer JDK and compile **without setting a target**, the bytecode may carry a newer major version.

On Linux/macOS you can filter with `grep`, while on Windows PowerShell you can filter with `Select-String`:

~~~powershell
javap -verbose ToolchainSmokeTest | Select-String "major version"
~~~

When running a Java 21 class on a JVM 17, you will typically encounter `UnsupportedClassVersionError`, with a message stating that the JVM does not support class file version 65. **This is a runtime error**: the source compiled, but the deployment JVM does not support the bytecode.

### `--release` Does Not "Downgrade" All Dependencies

Even if your code compiles with `--release 17`, an external library distributed with Java 21 bytecode may **fail to run on JVM 17**. When auditing compatibility, check the **major version and runtime requirements of dependencies**, as well as agent, framework, or plugin versions. `--release` restricts the Java Platform APIs of the code being compiled; it does not recompile dependent libraries.

**Do not fix this wrongly by manually editing the class file major version.** Lowering the number in bytecode does not convert new syntax, bytecode instructions, or APIs into a form an older JVM understands.

## 7. Checking the Maven Toolchain

For a Maven project, start with:

~~~bash
mvn -version
~~~

If the repo has a **Maven Wrapper**, use the wrapper:

~~~bash
./mvnw -version
./mvnw clean test
~~~

On Windows PowerShell, the wrapper file is typically `mvnw.cmd`:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean test
~~~

`mvn -version` or `mvnw -version` displays the Java runtime used to **launch Maven**; it does not guarantee that the compiler and test JVM use that same JDK.

### Configuring Java Release in `pom.xml`

A common approach:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

The project needs a **Maven Compiler Plugin** version that supports the corresponding release configuration and a sufficiently new JDK. You can also configure the plugin explicitly:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

In a real project, **pin a compatible plugin version** in the parent POM or plugin management. The illustration focuses on `<release>`; the specific plugin version should be chosen according to the project's build lifecycle.

### Maven Toolchains: The Compiler Can Use a Different JDK From the Launcher

If the build needs to select JDK 21 while Maven runs under another JDK, you can configure the **Maven Toolchains Plugin** together with `~/.m2/toolchains.xml` describing available JDKs. Example metadata structure for an installed JDK:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/absolute/path/to/jdk-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

**Replace `/absolute/path/to/jdk-21` with the actual path**; on Windows this is a Windows JDK directory. Having this file alone is **not enough**: the build must also configure appropriate plugin/toolchain selection so the relevant plugins actually use that JDK.

In a real Maven configuration, check separately:
- Where does the Maven Compiler Plugin get its compiler, and what is the effective `release`?
- Which JVM does Maven Surefire/Failsafe run tests on? Is there a separate fork/JDK configuration?
- Do source-generation plugins, annotation processors, or code-generation tools require a specific JVM?
- Do the parent POM and CI profiles override `maven.compiler.release`?

**Short Maven checklist:** verify wrapper → `mvnw -version` → effective POM/active profiles if needed → run `clean test` → verify compiler target and test runtime. The error `release version 21 not supported` is usually a sign that the compiler being used is **too old** to accept target 21, even if a newer JDK is installed elsewhere on the machine.

## 8. Checking Gradle Java Toolchains

For Gradle projects, prefer the **Gradle Wrapper**:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
~~~

On Windows PowerShell, use `.\gradlew.bat`. The `javaToolchains` task (in a project with the Java plugin properly configured) lets you inspect the JDKs Gradle detects. `gradlew --version` shows the runtime/daemon used to run Gradle, which is **not necessarily** the same as the compiler toolchain.

In `build.gradle` (Groovy DSL):

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
~~~

In `build.gradle.kts` (Kotlin DSL):

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
~~~

Separate the two concepts:

- `java.toolchain.languageVersion = 21`: asks Gradle to select a matching **JDK 21** to compile/run Java tasks that use toolchains.
- `options.release = 21`: sets the Java Platform level and bytecode target for Java compilation tasks.

Gradle toolchains can auto-detect pre-installed JDKs; **automatic JDK downloading** additionally depends on whether the project has configured a suitable provisioning resolver. Do not assume every machine/CI can always download a JDK just because `toolchain` is declared.

**Note on Gradle compatibility:** a Gradle version that is too old may not support running on a new JDK or may not fully support your chosen Java toolchain target. Therefore, in addition to the JDK version, check the actual **Gradle Wrapper version** in the repo. In multi-project builds, configuration may differ across subprojects, test tasks, and plugins.

### Common Gradle Errors

- `No matching toolchains found`: Gradle cannot find a suitable JDK or has no resolver configured to provision one.
- The Gradle daemon is running on an old JDK even though the shell changed `JAVA_HOME`: check the daemon and the IDE Gradle JVM.
- `Unsupported class file major version` from Gradle/plugin: the Gradle or plugin version may not understand the bytecode of a newer dependency/plugin.
- The build script selects Java 21, but tests or deployment use Java 17: the build succeeds, while runtime may fail.

## 9. IDE: Do Not Let the Editor Be "Green" While CI Is "Red"

Each IDE can have **its own JDK for source analysis**, **project language level**, **Gradle/Maven JVM**, and **Run/Debug JRE**. When a conflict occurs, do not just change a single dropdown.

| Environment | Places to check | Key questions |
| --- | --- | --- |
| IntelliJ IDEA | Project SDK; Project language level; Gradle JVM or Maven runner/importer; Run configuration | Does the IDE use the same JDK/release as the build wrapper? |
| Eclipse | Installed JREs/JDKs; compiler compliance level; Execution Environment; project JRE | Is project compliance set to Java 21? Is the launch runtime correct? |
| VS Code Java | Java runtime settings/extension; Maven/Gradle project import; terminal JDK | Which JDK does the extension use; do the terminal and build wrapper share the same configuration? |
| CI server | Setup JDK step; `JAVA_HOME` env; image/container; build commands | Does the CI toolchain have the right and complete JDK? |
| Production container | Base image tag/digest; `java -version` inside container; classfile target | Does the runtime support the bytecode and dependencies? |

**Practical workflow:** select the appropriate SDK/Gradle JVM, **re-import the project**, run the build via the wrapper directly in the terminal, and then run the application using the corresponding runtime. Do not rely solely on code highlighting or a "project SDK 21" indicator to assume CI is using JDK 21.

When IDE and CI differ, record reproducible lines of evidence:
- `java -version` and `javac -version` commands in the failing environment.
- Wrapper `-version` command.
- Compiler `--release` option or `maven.compiler.release`/Gradle `options.release` configuration.
- Class file major version (if it is a class loading error).
- Plugin versions, container runtime, and the first meaningful stack trace.

## 10. CI/CD: Testing the Target in a Real Environment

An example GitHub Actions job illustrating how to run the Maven Wrapper with JDK 21:

~~~yaml
name: Java 21 verification
on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven
      - name: Inspect toolchain
        run: |
          java -version
          javac -version
          ./mvnw -version
      - name: Build and test
        run: ./mvnw -B -ntp clean verify
~~~

This is a **configuration example**, not a claim that the GitHub Actions major versions shown are the latest. In production, choose action versions according to your organization's security policy and consider **pinning by commit SHA**.

If the repo uses Gradle, replace the Maven command with `./gradlew --no-daemon clean test` and configure the corresponding cache.

### Why Test on the Target JVM?

Compiling with JDK 24 using `--release 21` is a useful compile-time check. However, to ensure the application runs on **Java 21**, you still need a test run on **JVM 21**. Factors beyond syntax can depend on the runtime: JNI libraries, JVM flags, the module system, dependencies, and environment configuration.

In projects that must support multiple Java runtimes, define a **compatibility matrix** based on product requirements and run tests on each committed runtime. Do not inadvertently claim "Java 17 support" when Java 21 source code already uses record patterns and switch patterns that cannot compile with `--release 17`.

## 11. Preview Mode and Finalized Features

A common source of confusion is taking preview instructions from older Java versions and applying them to Java 21:

- `record patterns` and `pattern matching for switch` **do not require preview** in Java 21.
- `--enable-preview` is only for preview features of the **release being used** and requires matching compile/run configuration.
- Enabling preview on JDK 17 **does not make the finalized Java 21 syntax fully available**. Earlier previews had different syntax/rules, especially with guards.
- If a real project uses a preview feature, it must explicitly document the **JDK release**, compiler flags, runtime flags, upgrade policy, and how CI runs tests.
- Avoid enabling preview by default in a codebase that does not need it, as it makes feature contracts and lifecycle harder to control.

**Recommendation for the modern Pattern Matching module:** choose **Java 21** as the minimum target when standard record patterns and `switch` patterns are needed; use `--release 21` (or equivalent configuration) and do not enable preview unless another preview feature is used.

## 12. Quick Diagnosis of Common Toolchain Errors

| Symptom | Possible cause | How to check and fix |
| --- | --- | --- |
| `patterns in switch ... not supported in -source 17` or similar message | `source/release` is too low for pattern switch | Use release 21+ if permitted, or write Java 17-compatible code |
| `release version 21 not supported` | Selected `javac` is too old | Check `javac -version` and build toolchain; select a sufficiently new JDK |
| `UnsupportedClassVersionError` | Runtime JVM is too old for the class-file major version | Check `java -version` and `javap -verbose`; align target/runtime |
| CLI build succeeds but IDE reports error on `case ... when` | IDE SDK/language level/importer is out of sync | Check project SDK, language level, re-import Gradle/Maven |
| Runs in IDE but fails in CI | CI JDK or compiler target differs | Print version/target in CI; use wrapper and explicit toolchain |
| Gradle cannot find JDK 21 | JDK not installed or resolver not configured | Specify toolchain and configure provisioning if needed |
| Maven uses wrong JDK despite `JAVA_HOME` change | Maven runner/toolchains/forked compiler differs from shell env | Check Maven runtime, compiler plugin, toolchains, and test JVM |
| Class built with Java 21 but dependency requires newer Java | `--release` does not downgrade dependency bytecode | Check library minimum Java version and class major version |
| Source uses `String.isBlank()` with `--release 8` | Java 11 API not present in Java 8 | Switch to Java 8-compatible API or raise target as required |
| Code compiles by mistake after testing lower release | Old `.class` files remain in build output | Clean output, rebuild in a separate directory |
| Toolchain works on one machine but is not reproducible | Wrapper/JDK/dependencies are not pinned | Use wrapper, toolchain version, and CI verification |

Exact error messages may vary by JDK and plugin. Prioritize **finding the root cause** rather than blindly fixing by enabling preview, removing `--release`, or forcing the IDE to accept new syntax.

## 13. Step-by-Step Toolchain Verification Process

A process you can follow during project handover or before merging a PR that uses Java Pattern Matching:

**Step 1 — Record the minimum Java requirement.** Determine whether customer-facing APIs must run on JVM 17, JVM 21, or newer. If code must run on Java 17, you cannot arbitrarily introduce Java 21 record patterns.

**Step 2 — Check the shell JDK.** Run `java -version`, `javac -version`, `JAVA_HOME`, and check launcher paths. Distinguish between Windows/Unix terminals, the IDE terminal, and the CI shell.

**Step 3 — Check the wrapper and build config.** For Maven, inspect `mvnw`, compiler release, toolchains, and test plugins. For Gradle, inspect `gradlew`, `java.toolchain`, `options.release`, and the daemon environment.

**Step 4 — Check whether preview is used.** If the code requires stable Java 21, `--enable-preview` is normally unnecessary. If preview is enabled, confirm which feature it serves.

**Step 5 — Compile from clean output.** Run a clean build and smoke test with the required target. Avoid drawing conclusions from stale `.class` files.

**Step 6 — Run on the target JVM.** Run tests using the **lowest supported runtime**. If targeting 21, verify it actually runs on JVM 21 when Java 21 compatibility must be guaranteed.

**Step 7 — Check dependencies/runtime image.** Inspect the minimum Java version of frameworks and libraries; verify that the Java image used in deployment is not pinned to another version.

**Step 8 — Sync IDE and CI.** Re-import the project, update run configs, and print JDK versions in CI logs.

**Step 9 — Record evidence.** Save JDK versions, wrapper, release, smoke test results, and environment constraints in build documentation or CI logs.

**Step 10 — Put checks into the pipeline.** CI should run automatically whenever a module adds new pattern matching or upgrades the toolchain, rather than relying on a single developer's local run succeeding.

## 14. Practice Exercises and Answers

### Exercise 1 — New JDK but Old `--release`

A machine has JDK 24 installed. The Maven project configures `<maven.compiler.release>17</maven.compiler.release>`. A developer adds `case Point(var x, var y) -> ...`. What is the error?

**Answer:** Record patterns in `switch` were finalized in Java 21, whereas the project target is Java 17. Having JDK 24 installed on the machine **does not remove the `--release 17` constraint**. You must either get approval to raise the project target to 21, or write Java 17-compatible handling according to the product contract.

### Exercise 2 — Compiles, Fails to Run

A `.class` file with `major version 65` is run on JVM 17. What happens?

**Answer:** JVM 17 only supports class files up to the level matching Java 17 (major 61); loading a Java 21 class (major 65) can throw `UnsupportedClassVersionError`. To run on JVM 17, the build/source/dependencies must be Java 17-compatible; otherwise, the runtime must be upgraded to a version supporting Java 21.

### Exercise 3 — Maven and Terminal Report Different Versions

`java -version` reports 21, but `./mvnw -version` reports running Java 17. What should be checked first?

**Answer:** Check `JAVA_HOME`, the Maven Wrapper launcher, and the Maven runner/toolchains configuration. Do not conclude the compile target is 21 just because a `java` command outside Maven reports 21. Check both the compiler plugin and the test JVM in use.

### Exercise 4 — Gradle Wrapper and `toolchain`

`build.gradle` declares Java toolchain 21, but `./gradlew -q javaToolchains` does not list JDK 21 and the build reports no matching toolchain found. Should you remove the toolchain so the build can temporarily run with the default JDK?

**Answer:** No. Install JDK 21 or configure an appropriate JDK provisioning/resolver, and check the Gradle Wrapper version and JDK paths. Removing the constraint can cause different machines to use different compilers, reducing reproducibility and causing the build to produce bytecode with the wrong target.

### Exercise 5 — Is `--enable-preview` Needed for Java 21 Record Patterns?

**Answer:** No. Record patterns (JEP 440) and pattern matching for switch (JEP 441) were **finalized in Java 21**. Select the appropriate JDK/release; only enable preview if the application uses **another preview feature** from that same release.

### Exercise 6 — Checking Source and Runtime

A team only runs `javac --release 21` on JDK 24 and announces "Java 21 production support verified". Is this sufficient?

**Answer:** No. That is compile-time evidence. You need to run tests on JVM 21, verify dependencies, check the CI/deployment runtime launcher, class-file versions, and the production environment. `--release` does not replace real runtime testing.

## 15. Pre-Merge Checklist for Pattern Matching Code

- [ ] Know exactly which features require Java 16, 17, or 21.
- [ ] Identify the minimum Java runtime committed for the product.
- [ ] `java -version`, `javac -version`, and the build wrapper's JDK are recorded.
- [ ] Maven `maven.compiler.release` or Gradle `options.release` matches the target.
- [ ] Maven Toolchains/Gradle Java Toolchains actually locate the required JDK.
- [ ] IDE language level and Run/Debug runtime align with the target.
- [ ] Preview is not enabled unless needed, and old preview syntax is not relied upon.
- [ ] Compiled from clean output; Java 21 smoke test source runs properly.
- [ ] CI/deployment runtime is not lower than the classfile/dependency target.
- [ ] Tests are run on the lowest supported runtime.
- [ ] Dependencies and build plugins have been checked to ensure they do not require a different JDK.
- [ ] Logs/documentation record the JDK, wrapper, target, and smoke test results.

## 16. Key Takeaways and References

**Three questions to answer first:**
1. **Who is compiling?** Which `javac`, selected by which wrapper/toolchain?
2. **Which Java version is being targeted?** What is `--release`/source/target, and is preview enabled?
3. **Who is running it?** Are the test, CI, and production JVMs compatible with the classfiles/dependencies?

For modules using **record patterns + pattern matching for switch**, Java **21+** is the minimum level for the finalized syntax. A well-managed toolchain not only helps code compile, but also helps **detect configuration drift early**, reduce "works on my machine" issues, and clarify compatibility contracts when the project upgrades its JDK.

**Official sources:**
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394).
- [JEP 395 — Records](https://openjdk.org/jeps/395).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
- [javac — Java Development Kit Tool Specifications](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
- [Maven Compiler Plugin: compile with a different Java version](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html).
- [Maven Toolchains Plugin](https://maven.apache.org/plugins/maven-toolchains-plugin/).
- [Gradle Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).

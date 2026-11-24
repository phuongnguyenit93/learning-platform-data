# Synchronizing the JDK Across Personal Machines, IDEs, and CI Runners

## 1. Goal and Real-World Scenario

A Spring Boot project can build cleanly in a developer's terminal, show red errors in the IDE, and then fail in CI on the very same commit. A common cause is that **different environments are using different JDKs**, or confusing the JDK used to run the build tool with the JDK used to compile and run the application.

After this lesson, you will be able to:

1. Distinguish `JAVA_HOME`, the JDK running Gradle/Maven, the compile JDK (toolchain), the target Java version, and the application runtime JDK.
2. Pick a JDK version compatible with Spring Boot and the existing Gradle Wrapper or Maven Wrapper, and declare it clearly in the project.
3. Verify and align the JDK on Windows/Linux machines, in IntelliJ IDEA or other IDEs, and on GitHub Actions CI.
4. Read evidence from commands/build logs, spot JDK mismatches, and fix the right configuration layer.
5. Distinguish **build reproducibility by Java version** from **bit-for-bit byte reproducibility** of artifacts.

**Running example:** a team chooses **Eclipse Temurin JDK 21** as the standard version for building the application. Both `21` and the Temurin vendor are illustrative choices; in practice, follow the version required by your **real project**, rather than upgrading to 21 by default.

## 2. Four Version Layers to Understand Before Synchronizing

| Layer | Role | Who Decides? | How to Check |
| --- | --- | --- | --- |
| Terminal JDK / `JAVA_HOME` | JVM and `javac` found by the shell; often used to launch the Wrapper | Machine environment, `PATH`, `JAVA_HOME` | `java -version`, `javac -version`, actual path |
| JVM running the build tool | JVM running the Gradle client/daemon or Maven; may differ from compile JDK | Wrapper, Gradle daemon settings, `JAVA_HOME`, IDE, or CI | `./gradlew --version` / `./mvnw --version` |
| Compile JDK and `--release` version | `javac` executing compilation and the Java/API version bytecode targets | Gradle Java toolchain, Maven Toolchains, Maven Compiler Plugin | Build config, toolchain info, compiler logs, class files |
| JVM running the program | JVM executing the JAR, tests, or Spring Boot app | Run configuration, container image, server, CI test runtime | `java -version`, startup logs, process `java.home` |

**Do not conflate these values.** For instance, a machine may have `JAVA_HOME` pointing to JDK 17 while Gradle uses a **JDK 21 toolchain** to compile. A Maven project setting `maven.compiler.release=21` still needs a compiler that supports release 21; the `release` property alone does not install JDK 21 for you.

`--release 17` on a newer compiler constrains syntax, standard libraries, and class files to Java 17 compatibility; it does not mean the build itself is running on JDK 17. Conversely, Java 21 bytecode normally has **class file major version 65**, whereas Java 17 is **61**. Running version 65 classes on JVM 17 can produce `UnsupportedClassVersionError`.

**Gradle also has two separate JVMs:** the client JVM launching the Wrapper and the daemon JVM executing the build. The daemon can be controlled by the IDE, `org.gradle.java.home`, or Gradle Daemon JVM criteria. Therefore, checking only `java -version` is not enough to prove which JDK Gradle is actually using.

## 3. Agreeing on a JDK Standard for the Whole Team

Before tweaking IDEs or CI, agree on a **version contract** recorded in project configuration and team documentation:

- **Primary Java version:** e.g., Java 21, used for compilation/testing and supported runtime environments.
- **JDK distribution:** e.g., Eclipse Temurin; this reduces vendor-to-vendor differences, though not strictly mandatory for Java unless the project requires it.
- **Build tool and Wrapper:** whether the project uses Gradle or Maven, and the Wrapper version committed alongside source.
- **Target Java level:** usually equal to the standard JDK; if the app must run on Java 17, target 17 must be designed and tested intentionally.
- **CI enforcement:** build/test steps must run with the chosen version rather than relying on the runner's default Java.

### Checking Compatibility Before Picking a JDK

1. Check **the project's actual Spring Boot version** and its Java/Gradle/Maven requirements in that version's official documentation. For example, Spring Boot 3.3 requires at least Java 17; do not blindly apply a newer Spring Boot version's requirements to an older project.
2. Inspect the Gradle Wrapper in `gradle/wrapper/gradle-wrapper.properties`. To **run Gradle on Java 21**, official support begins in Gradle **8.5**; supporting Java 21 as a *compile/test toolchain* begins in Gradle **8.4**. The Spring Boot plugin and other plugins may require higher Gradle versions.
3. For Maven, check `pom.xml`, Maven Wrapper, compiler plugin version, and the JDK running Maven. Do not assume the compiler plugin supports a release merely because the OS has a newer JDK installed.
4. If the organization still runs apps on JDK 17, do not casually build with target 21. Choose the actual runtime threshold and prove it with tests on that JDK.

**Principle:** upgrading the JDK, upgrading Gradle/Maven, and upgrading Spring Boot are three changes with distinct compatibility risks. Change one piece at a time only after confirming the compatibility matrix—do not tweak multiple versions to guess at an unclassified error.

## 4. Checking the JDK on a Personal Machine (Windows and Linux)

Run these from the project root directory containing `gradlew[.bat]` or `mvnw[.cmd]` and `build.gradle[.kts]` or `pom.xml`.

### Windows PowerShell

~~~powershell
java -version
javac -version
$Env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

`java -version` and `javac -version` show the Java versions on `PATH`. `Get-Command` shows which executables are invoked, which is very helpful when multiple JDKs or an older `java.exe` are installed. `JAVA_HOME` should point to the **JDK root directory**, not into `bin`.

Also check the matching Wrapper (**choose only one**):

~~~powershell
# Gradle project
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains

# Or Maven project
.\mvnw.cmd --version
~~~

Gradle's `javaToolchains` task displays discovered Java installations and their capabilities; a requested JDK may be absent if detection or toolchain downloading is not configured properly.

If using `cmd.exe` on Windows, run `echo %JAVA_HOME%`, `where java`, `where javac`, `gradlew.bat --version`, or `mvnw.cmd --version`. The two shells have different syntax; do not paste PowerShell commands verbatim into `cmd`.

### Linux (bash)

~~~bash
java -version
javac -version
printf '%s\n' "$JAVA_HOME"
command -v java
command -v javac
~~~

To see the final resolved path after symlinks on Linux:

~~~bash
readlink -f "$(command -v java)"
~~~

Check the Wrapper:

~~~bash
# Use only if this is a Gradle project
./gradlew --version
./gradlew -q javaToolchains

# Or if this is a Maven project
./mvnw --version
~~~

If `Permission denied` occurs when running the Wrapper on Linux, check script execute permissions. In a Git-managed repository, commit the proper executable bit for `gradlew` or `mvnw` so Linux CI can run it too; `chmod +x` locally does not guarantee Git metadata was updated.

### How to Interpret Results

- `java -version` is 21 yet `javac -version` is 17: `PATH` or multiple JDK installs are mixed; fix this before assuming builds use 21.
- `JAVA_HOME` is 21 yet `Get-Command java` / `command -v java` points elsewhere: check `PATH` ordering and the current terminal.
- Shell uses 21 yet `./gradlew --version` shows the Gradle daemon uses 17: inspect daemon JVM config, `org.gradle.java.home`, IDE settings, and daemon criteria for your Gradle version.
- `./mvnw --version` shows Maven running on 17: Maven can still run on 17 even if the project compiles with 21 via Toolchains; check the toolchain setup separately. Without Toolchains, Maven must run on a JDK supporting release 21.

After updating environment variables, **open a new terminal** and re-check. An IDE opened before the change may still hold the old environment: update its settings or restart the IDE if needed.

## 5. Declaring the JDK Standard in a Gradle Project

The configurations below are **snippets to add to an existing build file**, not full-file replacements. They require the Java or Java Library plugin and a Gradle Wrapper supporting the chosen toolchain.

### Groovy DSL: `build.gradle`

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
~~~

### Kotlin DSL: `build.gradle.kts`

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

This instructs standard Java tasks to use a matching JDK 21 for compiling, testing, or Javadoc (for supporting tasks). Gradle auto-detects installed JDKs; **automatic JDK downloading is not guaranteed by default** because it depends on toolchain repository/resolver configuration and Gradle version. When a toolchain is missing, install the matching JDK or configure a resolver per Gradle's documentation.

**Distinguishing toolchain from bytecode target:** when using JDK 21 yet needing Java 17 bytecode/APIs, you can add to `build.gradle`:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

This snippet illustrates **intentionally supporting a Java 17 runtime**; do not add it if the project standard is Java 21 everywhere. Dependencies and frameworks must also be Java 17-compatible; `options.release` alone cannot make a dependency compiled for Java 21 run on Java 17.

### Wrapper and the JDK Running Gradle

Commit the Wrapper files according to project layout, including `gradlew`, `gradlew.bat`, and the files under `gradle/wrapper/`. `distributionUrl` in `gradle-wrapper.properties` determines the Gradle version downloaded, not any globally installed Gradle on the machine.

If a team wants the Gradle **daemon** itself to always require a specific JDK, modern Gradle versions provide **Daemon JVM criteria** stored in `gradle/gradle-daemon-jvm.properties`. That configures the JVM *running Gradle*, distinct from `java.toolchain` which *compiles the project*. When criteria are not used, align `JAVA_HOME` and the IDE's Gradle JVM; never assume a `java.toolchain` block changes the JVM running Gradle.

Practical verification:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean build
~~~

In Windows PowerShell, replace `./gradlew` with `.\gradlew.bat`. `BUILD SUCCESSFUL` only confirms the task chain completed; inspect JVM and compile toolchain output separately to prove JDK alignment.

## 6. Declaring the JDK Standard in a Maven Project

### Maven Compiler and Spring Boot Parent

If the project uses `spring-boot-starter-parent`, `pom.xml` can usually specify the Java version via properties:

~~~xml
<properties>
    <java.version>21</java.version>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
~~~

`java.version` is a key Spring Boot Parent convention for build settings. `maven.compiler.release` tells the Maven Compiler Plugin to target Java 21 for syntax, standard APIs, and bytecode. A POM **not inheriting from Spring Boot Parent** must configure the compiler plugin explicitly; do not assume every POM honors `java.version`.

These two properties **do not install JDK 21** and do not change the JVM running Maven. When running:

~~~bash
./mvnw --version
./mvnw --batch-mode clean verify
~~~

check `Java version` and `Java home` in `--version`. In Windows PowerShell, use `.\mvnw.cmd --version` and `.\mvnw.cmd --batch-mode clean verify`.

### When Maven Runs on a Different JDK Than the Compile JDK: Maven Toolchains

When a machine has multiple JDKs or a build must compile with JDK 21 even though Maven launches on another JDK, use **Maven Toolchains**. Plugin snippet in `pom.xml`:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
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
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

This `<plugin>` block goes inside `<build><plugins>...</plugins></build>` of the POM; do not place it directly at the POM root. The build machine must have the matching JDK and expose it to Maven, such as in the **local** file `~/.m2/toolchains.xml` (on Windows, `.m2` inside the user home directory):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>21</version>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/temurin-21</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

**The `/opt/jdks/temurin-21` path here is an example:** replace it with the actual JDK 21 path on each machine; do not commit one person's local path into the POM. The Toolchains plugin locates the matching entry, and *toolchain-aware* plugins such as Maven Compiler draw the compiler from that toolchain. If Maven already runs on JDK 21 and multiple JDKs are unnecessary, `JAVA_HOME` + compiler release is usually sufficient for a simple project.

Some newer Toolchains setups can auto-discover JDKs; the setup above clearly illustrates the contract between the POM and the machine. In GitHub Actions, `actions/setup-java` can also generate Maven Toolchains configuration; still verify that requirements and version/vendor labels truly match.

## 7. Configuring the IDE to Avoid Picking the Wrong JDK

IDEs usually have at least three **independent** settings: **Project SDK** (code analysis/editor), **JDK running Gradle/Maven** (import and build), and **Run/Debug configuration JDK** (running the app/tests). Changing one does not guarantee the others changed.

### IntelliJ IDEA

1. Open **Project Structure → Project** to inspect and select Project SDK as JDK 21 (or the project's standard version). Verify the matching language level, especially if the IDE sets a different level than the build compiler.
2. For Gradle: open **Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle**, choose the **Gradle Wrapper** distribution and appropriate **Gradle JVM**. If the project has Gradle Daemon JVM criteria, check the criteria rather than assuming manual Gradle JVM always takes precedence.
3. For Maven: inspect **Maven Runner/Importer JDK** or related Maven settings in your IDE version; compare `mvnw --version` inside the IDE terminal with an external terminal.
4. In **Run/Debug Configurations**, inspect the JRE/JDK running the Spring Boot app, tests, or plain Java apps. Project SDK may be 21 while a run configuration still points to Java 17.
5. **Reload/reimport the Gradle or Maven project**, then run the build task via the Wrapper in the terminal to compare against CI. Depending on settings, the IDE's **Build Project** button may invoke an internal compiler instead of the full Gradle/Maven lifecycle.

### Eclipse or VS Code

- **Eclipse:** check **Preferences → Java → Installed JREs** (select an appropriate JDK), **Project → Properties → Java Compiler**, and the JRE in **Run Configurations**. For Gradle projects using Buildship, separately check the Gradle JDK and Wrapper usage.
- **VS Code Java:** run **Java: Configure Java Runtime** to inspect project runtimes, and check the JDK used by extensions/build tools. Integrated terminals inherit environments depending on how VS Code was launched; still run the Wrapper and `--version` for evidence.

Do not change the **global IDE SDK** if only one project requires a different Java version. Prefer per-project configuration and source-controlled toolchains/Wrappers.

## 8. Synchronizing the JDK in CI: GitHub Actions Examples

CI must **provision the JDK explicitly before the build step**. Do not rely on whatever Java happens to be pre-installed on the runner image, as images can be updated without any code changes. A workflow typically lives at `.github/workflows/build.yml`.

### Gradle Project

The following standalone workflow uses Temurin 21, Gradle Wrapper, and a GitHub-hosted Ubuntu runner:

~~~yaml
name: Gradle build
on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: gradle

      - name: Verify Java and Gradle
        run: |
          java -version
          javac -version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Build and test
        run: ./gradlew clean build
~~~

`actions/setup-java` installs the JDK, updates `JAVA_HOME`/`PATH`, and can cache dependencies; `checkout` pulls the Wrapper files from the repository. `./gradlew` uses the **Wrapper-managed Gradle version** instead of an arbitrary Gradle installation on the runner. On `ubuntu-latest`, `gradlew` must retain execute permission in Git; otherwise CI can fail with `Permission denied`.

### Maven Project

This is an **alternative** workflow to the Gradle example above; pick the workflow matching your project's build tool:

~~~yaml
name: Maven build
on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Verify Java and Maven
        run: |
          java -version
          javac -version
          ./mvnw --version

      - name: Build and test
        run: ./mvnw --batch-mode clean verify
~~~

Both examples use the major action versions shown in current `actions/setup-java` documentation; in real deployments, check which action versions GitHub supports at the time and follow your organization's SHA-pinning policy.

**Explanation of choices:**

- `java-version: '21'` pins the **feature/major version** and selects a matching JDK 21 from the distribution, which may vary in patch version across runs. When you need to freeze the exact patch version for debugging or strict reproduction, specify a full version and use a controlled update process.
- `distribution: temurin` makes the JDK vendor explicit. Vendors pass Java compliance tests, yet vendor-specific or native-tooling quirks can still occur.
- `cache: gradle` or `cache: maven` saves dependency download time; **caching does not replace declaring the JDK or Wrapper**.
- `./gradlew clean build` and `./mvnw clean verify` execute the build and tests per actual config. If the project has integration tests, profiles, or quality gates, CI should run the project's designated tasks/goals.
- In a monorepo, set `working-directory` to the folder containing the Wrapper, or invoke the Wrapper via its proper path. Do not assume every repository has a single app at root.

On Windows CI runners, run `.\gradlew.bat` / `.\mvnw.cmd` in PowerShell and pick an appropriate Windows runner. OS differences affect paths, line endings, permissions, and native dependencies; **synchronizing the JDK does not guarantee OS differences disappear**.

## 9. Hands-On Cross-Check Across All Three Environments

Suppose the repository declares Java 21 in the Gradle toolchain or Maven `release`, and commits the corresponding Wrapper.

| Check Step | Personal Machine | IDE | CI |
| --- | --- | --- | --- |
| 1. Current Java | `java -version`, `javac -version`, `JAVA_HOME` | Project SDK / Java runtime settings | `setup-java` logs, `java -version` |
| 2. Build-tool JVM | `gradlew --version` or `mvnw --version` | Gradle JVM/daemon criteria or Maven Runner | Wrapper `--version` in the job |
| 3. Actual compiler | Gradle `javaToolchains`, Java config; or Maven release/Toolchains | Reimport project and run build via Wrapper | Build and toolchain task/goal logs |
| 4. Build result | Gradle `clean build` / Maven `clean verify` | Same task/goal via Wrapper | Job finishes with exit code 0 |
| 5. Appropriate runtime | JDK used for `java -jar` or tests | Run/Debug configuration JDK | Test JDK, container/deploy if applicable |

When all three select JDK 21, expect to see Java 21 for the JVM compiling/testing and the intended runtime. If the **Gradle daemon uses Java 17 while the compiler toolchain uses Java 21**, that is not necessarily a bug; document that design clearly, verify your Gradle version supports JVM 17 and toolchain 21, and verify CI supports the same. If the **project requires JDK 21 everywhere**, synchronize the actual daemon and runtime rather than looking only at a compile-21 message.

### Runtime Compatibility Verification Exercise

Run an executable Spring Boot JAR produced by the build on the **runtime JDK committed to by the project**, not just any available JDK. If class files are compiled at level 21 and then run on JDK 17, a class-file compatibility error is predictable. Changing only `JAVA_HOME` in a terminal while the IDE still launches the app with a different JDK will skew the test.

You can run `javap -verbose` on a `.class` file compiled by the project to check `major version`, making sure to inspect a class **built by the project itself**: `65` for Java 21, `61` for Java 17. That reveals the class-file level, **not which JDK ran Gradle/Maven**, and does not prove every dependency is compatible with the target runtime.

## 10. Common Errors and Root-Cause Fixes

| Symptom | Correct Interpretation | Action |
| --- | --- | --- |
| Terminal shows Java 21, IntelliJ Gradle build reports JVM 17 | IDE/daemon picks a different JVM than the terminal | Check Gradle JVM/daemon criteria, `org.gradle.java.home`, and Gradle Wrapper; reload project |
| `error: release version 21 not supported` | Actual `javac` is too old, often JDK 17 | Check `javac -version`, Maven `--version`, toolchain/IDE compiler; use a JDK supporting release 21 |
| `No matching toolchains found` or `No Java installation matching` | Required JDK is missing or not discovered/provisioned | Check installed JDKs, Gradle toolchain resolver, or Maven `toolchains.xml`; do not change `release` to bypass the error |
| `Unsupported class file major version 65` inside Gradle/plugin | A component reading bytecode does not support Java 21 | Read stack trace to identify Gradle/plugin/processor; upgrade the right component per its support matrix |
| `UnsupportedClassVersionError`: runtime up to 61, class is 65 | Java 21 artifact running on Java 17 | Use a Java 21 runtime or recompile for a committed runtime supported by dependencies |
| CI fails immediately when calling `./gradlew`/`./mvnw` | Missing Wrapper files or missing executable bit | Commit all Wrapper files and Git permission bits; check `working-directory` |
| `java -version` differs from `javac -version` | `PATH` mixes multiple Java installs | Inspect resolved paths for both commands and `JAVA_HOME`; open a new terminal |
| Maven Toolchains reports JDK 21 not found | POM requirement does not match machine's Toolchains file | Check declared version/vendor and actual `jdkHome`; configure CI to match |
| CI compiles yet tests fail; local passes | Different runtime, timezone, locale, external dependency, or test state | Compare JDKs first, then inspect test reports and full environment; do not blame Java for every test failure |
| IDE shows red errors while Wrapper build passes | IDE uses a different SDK/import/compiler model than the build tool | Align Project SDK, language level, import JDK, and reload project; treat the Wrapper build as primary evidence |

Do not wipe caches or blindly upgrade dependencies at the first sign of an error. First record the **command, JDK versions, build-tool JVM, compile toolchain, first error line, and OS**. For errors unrelated to JDK versions (proxies, repositories, secrets, database config, network ports), troubleshoot at the appropriate layer.

## 11. Pre-Acceptance Checklist for Team CI

- [ ] Team agreed on a Java version and, if needed, JDK vendor matching Spring Boot/Gradle/Maven and deployment environments.
- [ ] Java version is codified in `build.gradle[.kts]` or `pom.xml`; matching Wrapper files are committed in Git.
- [ ] Windows/Linux machines can access the JDK, `javac`, and Wrapper with no unintended `PATH`/`JAVA_HOME` mismatch.
- [ ] IDE selects matching Project SDK, Gradle JVM/Maven Runner, and Run/Debug JDK; Wrapper builds match the terminal.
- [ ] CI uses `setup-java` or an equivalent JDK provisioning step rather than relying on the runner's default JDK.
- [ ] CI build/tests pass; `--version` and toolchain logs confirm the project's required JDK.
- [ ] Production runtime or container uses a Java version able to execute the artifact's bytecode and dependencies.
- [ ] If strict reproducibility is required, JDK patch versions, plugins/dependencies, Wrapper, OS, and build environment are also intentionally managed.

You have completed this lesson when you can explain why **a matching `java -version` is not enough**, pinpoint the exact compiler JDK and the JVM running Gradle/Maven, and reconcile results across personal machines, IDEs, and CI on the same commit.

## Official Documentation

- [Gradle – Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle – Gradle Daemon and JVMs running Gradle](https://docs.gradle.org/current/userguide/gradle_daemon.html)
- [Gradle – Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html)
- [Apache Maven – Guide to Using Toolchains](https://maven.apache.org/guides/mini/guide-using-toolchains.html)
- [Apache Maven Compiler Plugin – Compiler Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [GitHub Actions – actions/setup-java](https://github.com/actions/setup-java)
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [IntelliJ IDEA – Gradle settings](https://www.jetbrains.com/help/idea/gradle-settings.html)

# Distinguishing the JVM Running the Gradle Daemon from the Compilation Toolchain

When upgrading Java in a Gradle project, asking “Which JDK is the project using?” is often not enough to diagnose issues. A single build may have the **Gradle daemon running on JDK 17**, while source code is **compiled by JDK 21**, the compiler is configured to allow only **Java 11** APIs, and integration tests run on **JDK 11**. All four details can simultaneously be true in one pipeline.

If these roles are confused, development teams easily run into situations such as: changing `JAVA_HOME` without the class-file version changing; configuring `sourceCompatibility = 11` while code still calls Java 17 APIs; `gradle --version` reporting one JDK while the compiler belongs to another; builds passing on developer machines yet failing on CI; or unit tests passing on a newer JDK while the production application runs on an older JDK and throws `NoSuchMethodError`.

This lesson in the **Java Advance Compatibility Migration** series explains in detail the difference between the JVM running the Gradle daemon and the Java toolchain used for the compiler, distinguishes them from the JVMs running tests/applications, provides Groovy/Kotlin DSL configurations, gives practical ways to observe reality, and outlines a migration workflow reproducible on both developer workstations and CI.

## 1. Overview Model: One Build, Multiple JVMs

Consider a hypothetical example:

```text
Terminal / IDE
    |
    | ./gradlew build
    v
Gradle launcher / client
    |
    v
Gradle daemon JVM (JDK 17)
    |-- Gradle core, build scripts, and build plugins
    |-- Dependency resolution, configuration, and task orchestration
    |
    +--> JavaCompile task
    |       |
    |       +--> Java compiler toolchain: JDK 21
    |                 |
    |                 +--> options.release = 11
    |                 +--> Java 11 bytecode and Java 11 platform APIs
    |
    +--> Test task
    |       |
    |       +--> Test worker JVM: JDK 11
    |
    +--> JavaExec / application run
            |
            +--> Launcher JVM: configured separately per task
```

Here, **JDK 17 does not automatically determine the bytecode target** and **JDK 21 does not automatically prove the application runs on Java 11**. Each choice governs a different scope.

| Component | What Runs? | Common Selection Mechanism | Risk If Confused |
|---|---|---|---|
| Gradle launcher/client | Starts the Gradle command and communicates with the daemon | Shell/IDE JVM, wrapper, and Gradle config | Command fails to start or uses wrong environment |
| Gradle daemon JVM | Gradle engine, build scripts, and plugins | Gradle JVM settings, daemon criteria, `org.gradle.java.home`, environment per Gradle version | Plugins/build logic incompatible with JDK |
| Java compiler toolchain | `javac` or Java compiler selected by the task | `java.toolchain` and `JavaCompile.javaCompiler` | Compiling with an unintended JDK |
| Language/bytecode/API target | Source syntax level, class file, platform Java APIs | `options.release`, source/target compatibility | Artifact fails on target runtime |
| Test worker JVM | JUnit/TestNG and tested code | `Test.javaLauncher`, toolchain/default task settings | Tests run on a different JDK than production |
| JavaExec/application JVM | Main class, integration utilities, app runtime | `JavaExec.javaLauncher` or corresponding launcher | Errors appear only upon deployment |
| Production runtime JVM | Released application | Container image, installer, app server, or target JRE/JDK | Bytecode, API, or behavioral incompatibility |

Some compilation tasks may invoke compiler APIs in-process or in a separate worker/daemon depending on plugins and configuration. Hence, **“compiler toolchain” is the JDK chosen by Gradle for the compilation task**, not necessarily always a separate `javac` process in every case.

## 2. What Is the Gradle Daemon JVM?

The Gradle daemon is a persistent JVM process handling builds, reusing state, and reducing startup overhead. It executes most of Gradle's own logic:

- Parsing and evaluating `settings.gradle`/`build.gradle` or their Kotlin DSL equivalents.
- Loading Gradle core and build plugins.
- Resolving dependency graphs and configuring tasks.
- Managing caches, incremental compilation, and task execution.
- Launching or coordinating compilers, test processes, worker processes, and external tools.
- Executing custom tasks and code running directly inside the Gradle build process.

**The JDK running the daemon must be compatible with the Gradle version and build plugins.** For example, an older Gradle version may fail to start under a very new JDK, even if the toolchain the project wants to use for compilation is an older JDK.

### 2.1. Daemon JVM Is Not Automatically the Compiler JVM

Suppose a machine has:

```text
C:\jdks\jdk-17
C:\jdks\jdk-21
```

The Gradle daemon launches on JDK 17. The project declares a JDK 21 toolchain for compilation. Then:

- Gradle/build plugins run on JVM 17.
- `JavaCompile` can invoke `javac` from JDK 21.
- `options.release = 11` can instruct the compiler to emit bytecode and validate platform APIs for Java 11.
- The test JVM must be verified separately.

Therefore, inspecting the daemon JVM **is not** a standalone method for determining the compiler version.

### 2.2. Why Can a Gradle Daemon Persist After Changing the Environment?

A daemon can be reused across builds whenever compatibility criteria match. Changing environment variables, Gradle JVM settings, or daemon criteria may cause Gradle to select a different daemon. During investigations, developers often need to check the actual JVM selected rather than relying on a previously opened terminal session.

Helpful commands:

```bash
./gradlew --status
./gradlew --stop
```

`--status` reports the state of Gradle daemons within the relevant management scope; `--stop` requests stopping matching daemons. Stopping the daemon should not be mistaken for a root-cause fix for compiler/API errors, yet it helps eliminate confusion when changing JVM settings.

## 3. Choosing the JDK for the Gradle Daemon

The configuration path depends on the Gradle version and how it is launched.

### 3.1. `JAVA_HOME` and Java on `PATH`

When launching Gradle from a terminal, `JAVA_HOME` typically participates in determining the Java installation used to start Gradle unless a higher-priority JVM configuration overrides it.

On Linux/macOS:

```bash
echo "$JAVA_HOME"
which java
java -version
./gradlew --version
```

On Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java
java -version
.\gradlew.bat --version
```

Distinguish clearly:

- `java -version` in a terminal usually reflects the Java found via shell/PATH.
- `$JAVA_HOME` or `%JAVA_HOME%` is merely an environment variable.
- `./gradlew --version` reports Gradle details and the JVM seen/chosen by Gradle, yet **does not confirm every JavaCompile task uses that JDK**.
- An IDE can launch Gradle using its own Gradle JVM setting, differing from the terminal.

### 3.2. `org.gradle.java.home`

In supporting Gradle environments, you can specify the Java home for the Gradle build daemon via the property:

```properties
# gradle.properties
org.gradle.java.home=/opt/jdks/jdk-17
```

This is a Linux path example. On Windows, use a path format appropriate for properties files and the environment; do not copy Linux paths verbatim.

Crucial point: **`org.gradle.java.home` picks the JDK for the Gradle process/daemon under that mechanism**, rather than instructing “generate Java 17 bytecode” for every module.

If Gradle daemon JVM criteria, IDE settings, or other JVM selection mechanisms coexist, check the precedence rules of **the exact Gradle version in use** instead of guessing.

### 3.3. Gradle JVM in the IDE

IntelliJ IDEA or other IDEs may maintain separate choices:

- Project SDK: the JDK used by the IDE to analyze code or run certain project operations.
- Gradle JVM: the JDK used to execute Gradle builds/imports.
- Run configuration JRE: the JDK used when running a program directly from the IDE.
- Toolchains in Gradle scripts: the JDK chosen by `JavaCompile`, `Test`, and corresponding tasks.

These four values can differ completely. For instance, the IDE displays Project SDK 21, while Gradle JVM is 17 and the `JavaCompile` toolchain requests 11. Concluding the build uses Java 21 just by looking at Project SDK would be wrong.

### 3.4. Gradle Wrapper and Version Limits

`gradlew`/`gradlew.bat` invokes **the Gradle version pinned by the project in the wrapper**. The wrapper does not automatically upgrade Gradle merely because a newer JDK is installed on the machine.

Example of a real constraint:

1. The machine has JDK 21 installed.
2. The project uses a Gradle version too old to support running on JDK 21.
3. Running Gradle can fail immediately at startup/configuration.
4. Even if the build script declares a Java 11 toolchain, that cannot rescue a Gradle engine that cannot boot.

Check the **compatibility matrix across Gradle wrapper version, daemon JDK, and compiler toolchain JDK**. Some Gradle releases support using a new JDK as a toolchain before supporting that JDK to run the Gradle engine itself; do not conflate those two capabilities.

### 3.5. Daemon JVM Criteria

Modern Gradle releases support **Daemon JVM criteria** to declare requirements for the JVM running the Gradle daemon, commonly via metadata under `gradle/` such as `gradle-daemon-jvm.properties`. This is a separate configuration from Java toolchains used for compilation.

If the project uses this mechanism:

- Identify the JVM version/vendor required by the criteria.
- Check how JVMs are discovered or provisioned.
- Check interaction rules with `JAVA_HOME`, `org.gradle.java.home`, and IDEs for the exact Gradle version.
- Do not treat the daemon criteria file as a substitute for configuring `java.toolchain`.

The goal is ensuring the JVM running Gradle is selected reproducibly in CI while compilation remains managed independently.

## 4. What Is a Gradle Java Toolchain?

A Java toolchain is a mechanism enabling Gradle to **locate or provision a JDK satisfying requirements for Java tasks** without forcing the use of the same JDK as the daemon.

Basic Groovy DSL configuration:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

In Kotlin DSL:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

This example requests a Java 17 toolchain for Java tasks using that setting. **It does not force the Gradle daemon to run on JDK 17.**

### 4.1. A Toolchain Describes More Than a Version Number

Beyond `languageVersion`, some configurations can specify vendor or implementation per the Gradle APIs supported by your version.

Groovy DSL example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
        vendor = JvmVendorSpec.ADOPTIUM
    }
}
```

Exact configuration depends on vendor matchers supported by that Gradle version. Projects with FIPS, HSM/native provider, or specific vendor requirements should state selection policy explicitly rather than picking “any JDK 17.”

### 4.2. Where Does Gradle Look for JDK Toolchains?

Depending on the Gradle release and configuration:

- JDKs installed in standard OS directories.
- `JAVA_HOME` and other JDK locations probed by Gradle.
- Paths declared in Gradle properties.
- Integration with Java environment managers such as SDKMAN!/asdf/IDEs when Gradle discovers them appropriately.
- Automatic toolchain provisioning via resolvers/repositories configured for the corresponding Gradle version.

For projects requiring offline builds or strict supply-chain controls, pin download/provisioning sources and know the exact JDKs installed on CI runners.

Example property declaring multiple installation paths:

```properties
org.gradle.java.installations.paths=/opt/jdk-11,/opt/jdk-17,/opt/jdk-21
```

Path lists vary by OS. These paths tell Gradle where to find toolchain JDKs; **they do not mean the daemon JVM automatically switches to a JDK in the list**.

Gradle JDK discovery can be customized for enterprise environments, though exact behavior must be checked against your Gradle version and settings.

### 4.3. Toolchains Do Not Automatically Guarantee Runtime Compatibility

If the compiler toolchain is JDK 21, by default it can compile Java 21 sources and call Java 21 APIs unless further constrained. If the application must run on Java 11, setting only a JDK 21 compiler toolchain **is not enough** to produce a Java 11-compatible artifact.

You must specify language/bytecode/API release targets and test on the target runtime as explained next.

## 5. Distinguishing Compiler JDK, `sourceCompatibility`, `targetCompatibility`, and `options.release`

This is the single most common point of confusion during JDK upgrades.

| Option | Primary Control | What It Does Not Automatically Guarantee |
|---|---|---|
| `java.toolchain.languageVersion` | JDK selected as toolchain for Java tasks | Does not restrict to older APIs/bytecode when compiler is newer |
| `sourceCompatibility` | Java source language syntax level | Does not restrict platform JDK APIs visible to the compiler |
| `targetCompatibility` | Generated class-file version | Does not prove newer APIs were not called |
| `options.release` | Constrains source language, class files, and platform APIs to the specified Java release | Does not guarantee third-party dependencies or runtime behavior are compatible |
| `Test.javaLauncher` | JDK running the test worker | Does not change compiled bytecode produced by the project |
| `JavaExec.javaLauncher` | JDK running the application/JavaExec task | Does not change the daemon JVM or default compiler |

### 5.1. Risks of Using `sourceCompatibility` and `targetCompatibility` Alone

Gradle example:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_1_8
    targetCompatibility = JavaVersion.VERSION_1_8
}
```

If the actual compiler is JDK 17 and only source/target 8 is set, code can still accidentally reference APIs added after Java 8. The class file has major version 52 yet contains a call to `List.of()` from Java 9, failing on Java 8.

Example:

```java
import java.util.List;

public class ApiLeak {
    public static void main(String[] args) {
        System.out.println(List.of("A", "B"));
    }
}
```

`List.of` was added in Java 9; a newer JDK compiler without platform API constraints accepts the source despite targeting Java 8 bytecode. A Java 8 JVM reads the bytecode format yet lacks the method, throwing `NoSuchMethodError`.

### 5.2. `options.release` to Also Constrain Java APIs

With a JDK compiler supporting `--release`:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

When compiling with JDK 17 or 21, `options.release = 11` enforces:

1. Java syntax matching release 11.
2. Class files matching Java 11.
3. Platform APIs matching Java 11 as accepted by the compiler.

It prevents new code from accidentally calling Java SE APIs introduced only in newer JDKs, though it does not control APIs or bytecode inside third-party dependencies.

**Do not set `sourceCompatibility`, `targetCompatibility`, and `options.release` simultaneously on the same compile task when they overlap in meaning.** For cross-compilation, prefer one clear target source, verify against your Gradle/compiler version, and avoid conflicting settings.

### 5.3. `--release` Is Not the Runtime JDK

`options.release = 11` does not mean tests also run on JDK 11. If the `Test` task defaults to JDK 21, tests may still pass even when runtime dependencies carry Java 11-incompatible class files or behavior.

If a library must support Java 11, test on an actual JDK 11 or equivalent environment in addition to targeting release 11 at compile time.

### 5.4. The Compiler JDK Must Support the Release Target

You cannot use a JDK 8 compiler with `--release 11`. `--release` was introduced in JDK 9 `javac`, and a compiler cannot target a Java release newer than its own capabilities.

Conversely, very new JDKs may drop support for very old releases, so confirm the target remains within the compiler's supported release list.

## 6. Complete Gradle Groovy DSL Configuration

Suppose an organization runs the Gradle daemon on JDK 17, wants to compile with JDK 21, yet ships a library that runs on Java 11 and uses JDK 11 for compatibility tests.

In `build.gradle`:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    // Use javac from the toolchain, yet enforce source/API against Java 11.
    options.release = 11
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    // Run tests using JDK 11 to verify the runtime target.
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

Key points to note:

- `java.toolchain` affects the compiler toolchain of applicable Java tasks.
- `options.release = 11` sets the source/bytecode/platform API target.
- `Test.javaLauncher` specifies the JDK running the test worker JVM.
- `useJUnitPlatform()` fits projects using JUnit Platform; if not using JUnit Platform, configure the appropriate test framework.
- The daemon JVM is chosen via Gradle execution settings, **not via `java.toolchain`**.
- The Gradle version must support this toolchain setup and Java release; the environment must provide or be able to provision JDK 21 and JDK 11.

The example above does not rewrite a dependency already compiled for Java 17 down to Java 11 bytecode. You must inspect the entire runtime graph.

### 6.1. Why Compile with JDK 21 While Targeting Release 11?

This setup is helpful when CI standardizes on a modern JDK as the compiler and the team wants one uniform toolchain compiling modules that support differing runtime floors.

However, if the project relies on annotation processors or compiler plugins supporting only a specific JDK range, selecting a newer `javac` can break them. Check compatibility of annotation processors and build plugins against the compiler toolchain.

### 6.2. Switching the Compiler to JDK 17

If JDK 21 is unnecessary for compilation and the project wants fewer differences:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

This remains a **JDK 17 compiler, Java 11 target** model. The test JVM must still be set explicitly if the goal is verifying runtime 11.

## 7. Equivalent Gradle Kotlin DSL Configuration

In `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(11))
    })
}
```

Semantically, this matches the Groovy DSL configuration; only Kotlin syntax and `Property.set(...)` calls differ.

In multi-module projects, agree on which modules support Java 11, 17, or 21. Do not apply `options.release = 11` across the entire repository if some modules intentionally use Java 17 APIs.

### 7.1. Per-Module Configuration

Groovy DSL multi-project build example:

```groovy
project(':shared-api') {
    tasks.withType(JavaCompile).configureEach {
        options.release = 11
    }
}

project(':desktop-client') {
    tasks.withType(JavaCompile).configureEach {
        options.release = 17
    }
}
```

A module compiled for target 11 can be consumed by a Java 17 application. However, a target-11 module must not depend on an artifact providing only Java 17 bytecode/APIs if it must run on JDK 11.

### 7.2. Toolchains May Reside in Convention Plugins

In large repositories, configuration may live in `buildSrc`, an included build, or a convention plugin rather than directly in `build.gradle`.

When diagnosing issues, inspect the actual resolved task configuration instead of reading only one module-level script. A plugin can override the compiler, launcher, or release of individual tasks.

## 8. The JVM Running `Test` Differs from the Daemon JVM

Gradle's `Test` task typically executes tests in one or more separate JVM processes. This allows selecting a test JDK distinct from the daemon/compiler, yet also introduces confusion.

Example:

```text
Gradle daemon: JDK 17
JavaCompile:   JDK 21, --release 11
Test worker:   JDK 21
Production:    JDK 11
```

A green build here does not prove the app runs on Java 11: tests executed on JDK 21.

An explicit compatibility test configuration:

```groovy
tasks.named('test', Test) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }
}
```

Depending on the project, the test task might require a newer JDK because test frameworks or test dependencies dropped Java 11 support. In that case, create a **dedicated test job** executing the Java 11 verification suite with compatible dependencies while keeping a newer test job for other features. Never claim “Java 11 support” without Java 11 runtime execution evidence.

### 8.1. Test JVM Arguments Are Not Daemon JVM Arguments

Example:

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens', 'java.base/java.lang=ALL-UNNAMED'
}
```

This is a JVM argument for the test worker. If the failure occurs inside a Gradle plugin running inside the daemon, this setting will not fix it; conversely, adding an argument to the daemon does not ensure forked test JVMs receive it.

This is especially important for reflection, instrumentation agents, TLS, heap limits, and systems using multiple classloaders.

### 8.2. Test JDK Can Differ from JavaCompile Toolchain JDK

If a project sets a Java 17 toolchain, Java tasks may inherit defaults related to that toolchain, yet **always declare `Test.javaLauncher` explicitly** when running a matrix verifying multiple runtimes. Do not depend on implicit defaults the team does not clearly understand.

## 9. `JavaExec` and the `application` Plugin JVM

A `JavaExec` task executes a main class on a Java launcher. It can be configured independently from the daemon JVM and compiler:

```groovy
tasks.register('runCompatibilityProbe', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(11)
    }

    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'com.example.app.Main'
}
```

This is an illustrative example. When a project applies the `application` plugin, the `run` task is created by the plugin and may inherit defaults from the Java plugin/toolchain. To guarantee a specific version, inspect or set `javaLauncher` on the actual task.

### 9.1. `java -jar` Outside Gradle Is a Different World

After packaging an artifact, running:

```bash
java -jar build/libs/app.jar
```

uses the `java` binary in the executing shell/container environment. It **does not read `java.toolchain` configuration** from Gradle scripts to choose a JVM.

In Docker:

```dockerfile
FROM eclipse-temurin:11-jre
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

The container's runtime determines whether the app executes on JDK/JRE 11. Ensure the artifact and dependencies are Java 11-compatible regardless of whether the Gradle daemon uses JDK 17 or 21.

### 9.2. `jlink`/`jpackage` Are Separate Operations

If a project builds runtime images or desktop installers with `jlink`/`jpackage`, the JDK used by those tools must also be selected intentionally. Configuring a toolchain for `JavaCompile` does not automatically guarantee custom packaging tasks pick the same JDK.

Verify command lines and the final runtime image. Compiling Java 11 bytecode and bundling a JDK 21 runtime still produces an application running on JDK 21, not a Java 11 runtime test.

## 10. Special Cases: Kotlin, Scala, Annotation Processors, and Code Generation

Gradle Java plugin's toolchain is important, yet polyglot projects involve additional compilers.

### 10.1. Kotlin Compilation

The Kotlin Gradle plugin has its own toolchain and target bytecode configuration per plugin version. Verify `jvmTarget` or `compilerOptions` appropriately, along with the Java toolchain used by the Kotlin compiler.

Setting:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

**does not automatically apply `--release 11` to Kotlin compilation**. When an artifact mixes Java and Kotlin, inspect bytecode targets and APIs used across both languages.

### 10.2. Kotlin Daemon and Worker Processes

The Kotlin compiler may run in a separate Kotlin daemon or worker process depending on plugin/configuration. That is a different process/JVM from the Gradle daemon and test workers. Therefore, a log saying “Kotlin daemon started with JDK ...” cannot prove the Gradle daemon or `JavaCompile` compiler uses that same JDK.

### 10.3. Scala Compiler and Groovy

Scala/Groovy plugins have their own compiler and target selections; they do not necessarily follow every `JavaCompile.options.release` setting.

When publishing a JAR containing bytecode from multiple compilers, inspect the final artifact to ensure no class was accidentally compiled for a higher release.

### 10.4. Annotation Processors and Compiler Plugins

Annotation processors typically execute inside the Java compiler's context. A processor built for a newer JDK can fail when an older compiler toolchain loads its classes; an older processor using `com.sun.tools.javac` internals can also break heavily when changing compiler JDKs.

Distinguish clearly:

- Gradle plugins loaded by the daemon JDK.
- Annotation processors executed by the compiler during `JavaCompile`.
- Test dependencies loaded by test workers.
- Runtime dependencies loaded by the application when running.

Each carries different version requirements.

## 11. Inspecting the Real Gradle Daemon and Toolchains

### 11.1. Viewing the Gradle Version and Active Gradle JVM

```bash
./gradlew --version
```

On Windows:

```powershell
.\gradlew.bat --version
```

Depending on the release, output may report Launcher JVM, Daemon JVM, or the JVM Gradle is using. This gives clues for investigating the daemon/launcher, **not proof of per-task compiler toolchains**.

### 11.2. Listing JDK Installations Discovered by Gradle

In a project with the Java plugin and toolchain task support:

```bash
./gradlew -q javaToolchains
```

This lists known JVM installations along with relevant metadata. If a needed JDK is missing, inspect installation paths, toolchain resolvers/provisioning, permissions, and CI configuration.

This command shows JDKs available for selection, not which JDK a specific task actually picked.

### 11.3. Printing the Real Compiler of a `JavaCompile` Task

When analyzing issues, you can temporarily add diagnostics in `build.gradle`:

```groovy
tasks.withType(JavaCompile).configureEach {
    doFirst {
        println "Task ${path}"
        println "Java compiler: ${javaCompiler.get().executablePath}"
        println "Release target: ${options.release.orNull}"
    }
}
```

This is purely for observing execution when the Gradle task runs. Avoid keeping noisy diagnostic logs permanently in production builds.

If custom `JavaCompile` setups, convention plugins, or special compiler daemons are used, inspect those tasks' output and toolchain settings as well.

### 11.4. Checking Output Bytecode

Use `javap` from an appropriate JDK:

```bash
javap -verbose \
  -classpath build/classes/java/main \
  com.example.app.Main
```

Look for `major version`:

| Java target | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Class-file versions confirm one part of compiler output, yet do not prove every dependency or runtime API is compatible.

### 11.5. Observing the Test Runtime

To be certain which JVM executes tests, a test can print system properties:

```java
System.out.println("java.version = " +
        System.getProperty("java.version"));
System.out.println("java.home = " +
        System.getProperty("java.home"));
System.out.println("java.vendor = " +
        System.getProperty("java.vendor"));
```

Place this logging inside the test worker itself rather than only in the build script so you observe the real test JVM.

### 11.6. Comparing Against Production

Inside the container or application host:

```bash
java -version
```

If the app ships its own runtime image, inspect the Java binary inside that image rather than Java on the host. You can log `java.runtime.version` at startup per operations policy.

## 12. Common Errors When Selecting the Wrong JVM

### 12.1. `Unsupported class file major version`

This error occurs when a component attempts to read a class file of a newer version than it supports.

This can happen in multiple places:

- Gradle or embedded Groovy/ASM does not support newer class files of a build script/plugin.
- An older runtime JDK tries to load classes compiled for a newer Java version.
- An annotation processor/plugin tries to read a dependency compiled with a newer JDK.
- A test worker uses an older JDK than the artifact/test classes.

Identify **which component is reading the class file**. Raising the compiler/toolchain will not fix every case; sometimes the Gradle wrapper or a plugin needs upgrading, while other times the artifact's own bytecode target must be lowered.

### 12.2. `No matching toolchains found`

Gradle may report no JDK matching the requested `languageVersion`, vendor, or implementation.

Investigation steps:

1. Check `./gradlew -q javaToolchains`.
2. Confirm the JDK is installed and has a valid Java home.
3. Check auto-download policies and toolchain resolvers.
4. Check access permissions, network, and CI caches if provisioning is enabled.
5. Verify the Gradle version actually supports that toolchain release.

Pointing `JAVA_HOME` to an arbitrary JDK will not resolve this if the build requires a specific vendor or installation.

### 12.3. Gradle Runs, Yet the Compiler Reports Unsupported Syntax

For example, source code uses `record` while the compiler target is Java 11. Records are not part of the Java 11 language, so compilation fails.

This can be **correct configuration protecting compatibility**. Decide the true runtime target before bumping source/release merely to silence compiler errors.

### 12.4. Compilation Succeeds, Yet Older Java Runtime Fails on APIs

If you only set `targetCompatibility = 8` without constraining JDK APIs, code can reference Java 9+ APIs and fail on Java 8.

Use `options.release` when cross-compiling, inspect third-party dependencies, and test on the target runtime.

### 12.5. Tests Pass in the IDE, Fail in CI

IDEs may choose a different Gradle JVM and test runtime than terminals/CI. Compare:

- Gradle wrapper version.
- IDE Gradle JVM.
- Daemon JVM criteria or `org.gradle.java.home`.
- Compiler toolchain and release.
- Test JVM launcher.
- Dependency graph.
- CI container/base image.

Avoid assuming “same test code means same JVM.”

### 12.6. Setting `org.gradle.java.home` Leaves Class Versions Unchanged

This is usually expected behavior when `JavaCompile` still uses a different JDK toolchain with a fixed `options.release`. Inspect the compiler toolchain rather than altering the daemon JVM to downgrade class-file targets.

### 12.7. Gradle Plugin Fails After Upgrading the Daemon JDK

A Gradle plugin executing inside the daemon can be impacted by a newer JDK even when the compiler toolchain stays on JDK 11. Verify compatibility across the Gradle wrapper, plugin versions, and daemon JVM. This is independent of the source APIs being compiled.

## 13. Thinking Properly When Using Maven Alongside Gradle

This lesson focuses on Gradle, yet in Maven–Gradle transition environments you must distinguish the corresponding roles.

| Concern | Gradle | Maven |
|---|---|---|
| JVM running build tool | Gradle daemon JVM | JVM executing Maven process |
| Selecting a separate compiler JDK | Gradle Java toolchain, `JavaCompile` compiler | Maven Toolchains + toolchain-aware plugins or compiler configuration |
| Controlling source/bytecode/API | `JavaCompile.options.release` | Maven Compiler Plugin `<release>` / `maven.compiler.release` |
| JDK running tests | Gradle `Test.javaLauncher` | Maven Surefire/Failsafe corresponding JVM/toolchain config |
| JDK running the app | `JavaExec.javaLauncher`, runtime deploy | Exec/plugin launcher or runtime deploy |

`mvn -version` shows the JDK running Maven, yet just like `gradlew --version`, it does not prove every compiler/test task uses that JDK if the project configures toolchains or forks.

### 13.1. Maven Compiler Plugin `<release>`

Example:

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
</properties>
```

This sets the compilation release target according to Maven Compiler Plugin and the real JDK/compiler capabilities, yet does not mean the JVM running Maven must be JDK 11.

### 13.2. Maven Toolchains

Maven provides a toolchains mechanism to select a JDK distinct from the JVM running Maven for supporting plugins. When migrating from Maven to Gradle or vice versa, map **build JVM, compiler JDK, test JDK, and target release** into independent settings.

Do not copy a legacy `JAVA_HOME` value directly into Gradle and assume you have reproduced Maven toolchains semantics.

## 14. Designing CI/CD for Java Compatibility Migration

### 14.1. Pin the Gradle Wrapper

Use the version-controlled Gradle Wrapper alongside the project. Update the wrapper per the daemon JDK and compiler toolchain JDK support matrix rather than relying on whatever arbitrary “preinstalled Gradle” exists on the runner.

### 14.2. Explicitly Choose the Daemon JVM

CI must explicitly set the JDK running Gradle via project-supported environment/criteria/methods. Avoid letting the JDK depend on incidental `PATH` ordering on runners.

### 14.3. Declare Toolchains in the Build

Example module supporting Java 11:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 11
}
```

CI needs JDK 17 for the compiler and, if testing the Java 11 target, JDK 11 for the test launcher. If toolchain provisioning is enabled, ensure trusted download sources, reproducibility, and managed caching.

### 14.4. Build a Runtime Compatibility Matrix

A matrix might run:

```text
Build/compile:
  Gradle daemon JDK 17
  Compiler toolchain JDK 17
  --release 11

Runtime tests:
  JDK 11
  JDK 17
  JDK 21 (if within supported scope)
```

Not every module must support every JDK. State the **minimum runtime and supported runtimes**, then design the matrix around that contract.

### 14.5. Ensure the Final Artifact Is Tested

If the build creates a WAR, fat JAR, Docker image, or installer, testing must cover the actual released artifact. A successful Gradle build on a JDK 17 daemon does not prove the WAR runs inside a JDK 11 application server.

### 14.6. Record Traceable Metadata

Store in build reports:

- Gradle wrapper version.
- Daemon JVM version/vendor.
- Compiler toolchain version/vendor.
- `options.release`.
- Test JVM version.
- Production/runtime image version.
- Artifact checksums, dependency locks, and resolved dependency graph when applicable.

These details help trace root causes when a release succeeds in environment A yet fails in environment B.

## 15. Real-World Scenarios and Configuration Options

### Scenario A: Upgrading the Build Server JDK While Keeping a Java 11 Runtime

Requirements:

```text
Gradle daemon: JDK 17
Compiler:      JDK 17
Bytecode/API:  Java 11
Production:    JDK 11
```

Approach:

1. Select a Gradle wrapper supporting daemon execution on JDK 17.
2. Use a JDK 17 toolchain.
3. Set `options.release = 11`.
4. Point compatibility tests to a Java 11 JVM.
5. Verify runtime dependencies contain no bytecode/APIs newer than Java 11.

### Scenario B: Developers Use JDK 21 While CI Keeps a JDK 17 Daemon

Requirement: compile with JDK 21 in both environments:

```text
Developer:
  Gradle daemon: JDK 17
  JavaCompile:   JDK 21

CI:
  Gradle daemon: JDK 17
  JavaCompile:   JDK 21
```

Configure toolchains and ensure JDK 21 is discovered/provisioned in both environments. The Gradle wrapper version must support that compiler toolchain release even while the daemon stays on JDK 17.

### Scenario C: Legacy Gradle Plugin Fails on JDK 21

The application wants to compile with JDK 21, yet a build plugin is not yet compatible with a JDK 21 daemon.

Consider keeping a plugin-supported daemon JDK paired with a JDK 21 compiler toolchain **if your Gradle version supports this combination**. This separates the plugin runtime from the compiler runtime.

However, if the Gradle wrapper/plugin still lacks support for a Java 21 language toolchain, you must upgrade toolchain support in Gradle/plugins rather than merely switching the daemon JDK.

### Scenario D: App Compiles for Java 11, Yet Tests Only Run on JDK 21

When Java 11 support must be declared, this is a verification gap. Set a JDK 11 test launcher or add a dedicated CI job testing Java 11 compatibility. Setting `options.release = 11` alone is insufficient.

### Scenario E: A Multi-Module Build Supporting Multiple Java Releases

Example:

```text
shared-legacy: --release 8
core-service:  --release 17
desktop-app:   --release 21
```

Appropriate compiler toolchains per module and a shared Gradle daemon can work if supported by Gradle/plugins. Yet dependency directions must make sense:

- A Java 17 service can depend on a Java 8 library.
- A Java 8 library must not depend on a service/artifact with Java 17 bytecode if it still must run on Java 8.
- Each module must have tests at its declared minimum runtime level.

## 16. Step-by-Step Diagnostic Workflow

When encountering a Java-version-related error in Gradle, resist changing random properties blindly.

**Step 1 — Identify which phase failed.** Did Gradle fail to boot, plugin configuration fail, `JavaCompile` fail, test worker fail, or production runtime fail?

**Step 2 — Record the Gradle daemon JDK.** Use Gradle version output, environment details, and daemon settings.

**Step 3 — Identify the compiler toolchain.** Check `javaToolchains`, `JavaCompile` task metadata, or build logs; do not guess from `JAVA_HOME`.

**Step 4 — Check the release target.** Inspect `options.release` or source/target settings, including convention plugins and subproject configs.

**Step 5 — Identify the test JVM.** Check `Test.javaLauncher` and the actual `java.home` reported inside the test worker.

**Step 6 — Identify the final runtime.** Inspect the Dockerfile, application server, desktop image, or actual `java -jar` command deployed.

**Step 7 — Check artifacts/dependencies.** Inspect class-file major versions, dependency bytecode, and compatible APIs. `--release` constrains only Java platform APIs for compiled sources, not automatically every dependency.

**Step 8 — Re-test with a reproducible setup.** Pin the wrapper, toolchains, CI runners, and runtime images; run the exact test suite matching migration goals.

**Step 9 — Document the configuration sources.** Record daemon JDK, compiler JDK, release target, test JVM, and production runtime clearly in operations docs.

## 17. Pre-JDK-Migration Checklist

- [ ] Identified the actual JVM running the Gradle daemon.
- [ ] Verified the Gradle wrapper supports the chosen daemon JDK.
- [ ] Distinguished the IDE's Gradle JVM from Project SDK.
- [ ] Identified the `JavaCompile` toolchain JDK rather than assuming `JAVA_HOME`.
- [ ] Verified Gradle discovers/provisions the toolchain in CI.
- [ ] Set explicit release targets for modules needing older JDK compatibility.
- [ ] Distinguished `sourceCompatibility`, `targetCompatibility`, and `options.release`.
- [ ] Checked annotation processors and compiler plugins.
- [ ] Configured the test-running JVM to match supported runtimes.
- [ ] Checked separate JVMs running `JavaExec`, Spring Boot run, or custom Java tasks.
- [ ] Configured Kotlin/Scala compilers if the project uses multiple languages.
- [ ] Checked dependencies and bytecode of the final artifact.
- [ ] Tested the application on the target runtime image or application server.
- [ ] Recorded daemon/compiler/test/runtime JDK details in CI build reports.
- [ ] Avoided misusing `org.gradle.java.home` as a way to lower bytecode targets.
- [ ] Avoided treating `gradlew --version` as sole evidence of compiler/toolchain choices.

## 18. Conclusion

**The JVM running the Gradle daemon and the compilation toolchain are two distinct components.** The daemon JVM executes the Gradle engine, build scripts, and plugins; the compiler toolchain supplies the JDK for `JavaCompile` tasks. In addition, there are the source/bytecode/API release target, the test JVM, `JavaExec`, and the production runtime. They can use different JDKs within the same build.

During Java Compatibility Migration, assign **the right JVM to the right job**: choose a Gradle wrapper and daemon JDK so the build tool boots reliably; select a compiler toolchain for compilation tasks; use `options.release` to preserve the platform API/bytecode floor; test on the lowest supported runtime; and verify the actually released artifact. By keeping these roles separate, teams can upgrade JDKs incrementally without conflating “which Java runs Gradle” with “which Java versions the application supports.”

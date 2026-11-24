# Distinguishing `sourceCompatibility`, `targetCompatibility`, and `--release` in Java

When configuring Java for a project using Gradle, Maven, or Spring Boot, the three names `sourceCompatibility`, `targetCompatibility`, and `--release` frequently appear next to a number like `8`, `11`, `17`, or `21`. They all relate to Java versions, yet **control different aspects**. Misunderstanding them can lead to a scenario where the build reports success, `.class` files look like they are for Java 8, yet deploying on Java 8 fails.

This lesson belongs to the **Java and Wrapper** topic in **Spring Boot Build Tooling Packaging**. The focus is on choosing and verifying Java versions for source code, bytecode, platform APIs, and build tools—especially the consequences of compiling with a newer JDK to run on an older JVM.

## 1. Separating Four Frequently Confused Concepts

Before looking at configuration, distinguish:

1. **Java language version (source level)** determines which syntax is allowed: `var` (Java 10), `record` (Java 16), pattern matching, and other version-specific features.
2. **Bytecode version (class-file target)** determines the minimum JVM capable of reading the `.class` file format. For example, Java 8 uses class-file major version **52**, Java 17 uses **61**.
3. **Callable platform API set** determines whether code may reference Java SE/JDK methods and classes introduced in the target release. `String.repeat(int)` exists only from Java 11 onward; a program calling this API cannot work properly on Java 8, even if bytecode was emitted at level 8.
4. **Actual JDK used to compile** provides the `javac` version and build environment, while the **actual JVM used to run** provides the runtime. Those two versions can differ.

A brief comparison:

| Setting | Primary Control | What Does It Not Guarantee Yet? |
| --- | --- | --- |
| Gradle `sourceCompatibility = 8` | Java 8 syntax in source, corresponding to `javac -source 8` | Does not restrict APIs from newer JDKs; does not choose the compile JDK |
| Gradle `targetCompatibility = 8` | Class file format for a Java 8 JVM, corresponding to `javac -target 8` | Does not guarantee all APIs and libraries exist on Java 8 |
| `javac --release 8` / Gradle `options.release = 8` | Simultaneously constrains syntax, class-file target, and **supported Java SE/JDK APIs** to release 8 | Does not select which JDK runs `javac`; does not automatically check all third-party dependencies or the runtime environment |
| Gradle **Java toolchain 17** | Selects the JDK 17 toolset for matching Java tasks | If you need platform API guarantees for a Java version **older than 17**, you still need `--release` or an equivalent control |

Remember: **`sourceCompatibility` answers "which syntax can be written?"; `targetCompatibility` answers "for which JVM should bytecode be emitted?"; `--release` answers "compile as if targeting which Java version, including platform APIs?"** Toolchains answer a different question: **"Which JDK should actually be used to compile/run tasks?"**

## 2. `sourceCompatibility`: Constraining Java Syntax

In the Gradle Java plugin, `sourceCompatibility` specifies the Java source language version the compiler must accept. A Groovy DSL example in `build.gradle`:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
}
```

At the `javac` level, the approximate equivalent is:

```bash
javac -source 17 Hello.java
```

If you pick Java 8, you cannot use `record` syntax introduced in Java 16. However, **Java 8 syntax can still call APIs introduced in Java 11** when compiling with a newer JDK and setting only `-source 8`: syntax and APIs are two separate concerns.

`sourceCompatibility` **does not install or select JDK 17**. If the machine runs Gradle on a JDK that does not support the requested source level, the compilation task may fail. What determines which compiler runs is the toolchain configuration or the build execution environment.

Do not confuse `sourceCompatibility` with the `src/main/java` path: `src/main/java` is where source files live; `sourceCompatibility` is the permitted source syntax version.

## 3. `targetCompatibility`: Bytecode Format, Not Complete Runnability

Gradle's `targetCompatibility` property sets the class file version produced by the compiler, corresponding to `javac -target`. Example:

```groovy
java {
    targetCompatibility = JavaVersion.VERSION_17
}
```

Some common class-file major versions:

| Java | Major version |
| --- | ---: |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

If a Java 8 JVM encounters a class file with major version 61, it cannot read that bytecode format and typically throws `UnsupportedClassVersionError`. However, the converse is **not sufficient**: a major 52 class file can still contain a call to a method that only exists starting in Java 11. The Java 8 JVM can read the file, then fails when linking that call.

With `javac`, **target must not be lower than source**; asking for source 17 with target 8 is invalid. A source 8 / target 17 configuration may have niche technical meaning in rare cases, yet it is confusing and does not help support JVM 8. Normally both should target the same version unless there is a verified special requirement.

Note: `targetCompatibility` only affects classes compiled by that task. It **does not downgrade bytecode versions of external dependencies** and does not turn an entire application JAR into something runnable on an older JVM.

## 4. `--release`: Locking Syntax, Bytecode, **and** Platform APIs

Since JDK 9, `javac` provides the `--release` option to target a Java version supported by the compiler:

```bash
javac --release 8 Hello.java
```

When `--release 8` is specified, the compiler simultaneously:

1. Accepts only language features valid in Java 8.
2. Emits class files in Java 8 bytecode format (major 52).
3. Checks references against Java SE/JDK APIs supported in Java 8, rejecting platform APIs that only exist in newer releases.

That third point is what **`-source` + `-target` does not automatically guarantee**. The compiler consults API data for the target release, catching errors early that would otherwise surface only when running on the older JVM. `--release` does not grant access to internal/unsupported APIs of the target JDK.

When invoking `javac` directly, **do not combine `--release` with `-source` or `-target`**; they are mutually exclusive ways to express the compatibility level. In Gradle, prefer configuring `options.release` on compile tasks rather than mixing redundant settings. Which `--release` versions are supported depends on the actual JDK; run `javac --help` to see what the compiler supports.

**Important limitation:** `--release` protects **Java platform** API compatibility during compilation; it does not prove that external libraries, reflection, JNI, OS resources, or runtime execution are compatible with the target Java version.

## 5. Experiment 1: Java 8 Class File Still Calling a Java 11 API

This experiment runs with **JDK 17** (or any newer JDK supporting target 8). No Spring Boot, Maven, or Gradle is needed to see the root problem.

Create `ApiTrap.java`:

```java
public class ApiTrap {
    public static void main(String[] args) {
        System.out.println("ha".repeat(2));
    }
}
```

`String.repeat(int)` is a `java.lang.String` API added in Java 11. Normal method-call syntax is already valid at source level 8.

### 5.1. Compiling the Old Way

```bash
javac -source 8 -target 8 ApiTrap.java
java ApiTrap
```

On JDK 17, the compiler may emit a **warning** about `bootclasspath`, yet the code typically compiles because the compiler sees `String.repeat` in JDK 17's platform library. Running on Java 17 prints exactly:

```text
haha
```

Inspect the bytecode:

```bash
javap -verbose ApiTrap
```

In the output is the line:

```text
major version: 52
```

This proves the class file uses Java 8 format; it is **not** proof that the code works on Java 8. If you run this `ApiTrap.class` file on a Java 8 JVM, executing the `String.repeat` call raises a linkage error such as `java.lang.NoSuchMethodError` because Java 8's `String` has no such method. This "right bytecode version, wrong API version" failure is the exact loophole in `sourceCompatibility` + `targetCompatibility`.

### 5.2. Compiling with `--release`

Keep `ApiTrap.java` as-is and run:

```bash
javac --release 8 ApiTrap.java
```

The JDK 17 compiler **refuses to compile** because `String.repeat(int)` does not exist in Java 8's APIs. The defect is caught early, right during the build. The main `javac` diagnostic looks like:

```text
cannot find symbol
  symbol:   method repeat(int)
  location: class java.lang.String
```

Line numbers and warning/error formatting may vary by JDK. Because a **failed compilation can leave behind a `.class` file from a prior successful run**, do not accidentally run the stale artifact and conclude `--release` succeeded; clean old outputs or use a clean build directory when testing.

### 5.3. An Example That Can Compile and Actually Run on Java 8

Create `HelloRelease.java`:

```java
public class HelloRelease {
    public static void main(String[] args) {
        System.out.println("Hello Java 8");
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 8 HelloRelease.java
java HelloRelease
```

Exact stdout:

```text
Hello Java 8
```

`javap -verbose HelloRelease` also shows `major version: 52`. Because the program only uses APIs and syntax present in Java 8, this class **can** run on Java 8 using a normal Java 8 JVM. To confirm an entire real application is compatible, you must still run tests on the target JVM and inspect all dependencies.

## 6. Proper Configuration in Gradle

Projects using the **Gradle Wrapper** should run via `./gradlew` (macOS/Linux) or `.\gradlew.bat` (Windows PowerShell) so every machine runs Gradle per the project's configuration. **The Wrapper pins the Gradle version**; it does not guarantee which JDK Gradle or the compiler uses.

The examples below are alternative configuration snippets by goal; **do not merge all of them into the same build file**. Keep existing plugins and dependencies in `build.gradle`, and add/update only the needed block.

### 6.1. Legacy Approach: `sourceCompatibility` + `targetCompatibility`

Gradle Groovy DSL example:

```groovy
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
```

This setup usually generates Java 17 code when the compiler is new enough, but it does not pin the compile JDK and gives no lower-Java API guarantee when the compiler is newer than the target. It still appears in many older projects and must be understood accurately when reading build files.

### 6.2. Recommended Approach for a Spring Boot App Running on Java 17

Gradle Groovy DSL configuration in a project with the Java plugin applied (directly or via the build setup):

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Meaning:

- **Toolchain 17:** Gradle locates/uses a Java 17 compiler and tools for matching tasks. If the machine lacks a matching JDK and no toolchain download source is configured, the build reports a missing toolchain.
- **`options.release = 17`:** `JavaCompile` tasks enforce Java 17 language level, bytecode, and platform APIs. Using `tasks.withType(JavaCompile)` covers the main Java compile task as well as other applicable Java compile tasks, including tests if present.
- **Deployment runtime:** the machine/container running the app must still have a JVM compatible with **all** classes and dependencies in the artifact.

In a project with toolchain 17 that does not target a lower version, the toolchain alone is usually enough for consistent builds. Writing `options.release = 17` makes the API baseline explicit and clarifies intent to readers. It is unnecessary to also declare `sourceCompatibility` and `targetCompatibility` for the same target.

### 6.3. Java 21 Compiler, While Library Output Targets Java 17

Example of a **plain Java library** needing a JDK 21 compiler while targeting Java 17 APIs/class files:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.named('compileJava', JavaCompile) {
    options.release = 17
}
```

Here: **JDK 21 is the tool**, while **Java 17 is the compatibility contract of classes produced by `compileJava`**. Constraining only `compileJava` allows tests or another task to have separate settings if needed; testing on Java 17 must still be arranged intentionally. A JDK 21 compiler cannot produce valid output for a `--release` version that the compiler itself does not support.

Do not lower `options.release` to 8 or 11 for a **Spring Boot 3.x** application just to run on an old JVM: Spring Boot 3.x requires at least Java 17. Application classes with major version 52 will not make Spring Boot 3.x libraries run on JVM 8.

### 6.4. Comparing with Kotlin DSL (`build.gradle.kts`)

If the project uses Kotlin DSL, the equivalent syntax is:

```kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release = 17
}
```

Both DSLs configure equivalent Gradle APIs. Do not copy Groovy DSL `JavaVersion.VERSION_17` syntax verbatim into Kotlin DSL where it doesn't belong and expect Gradle to translate it automatically.

## 7. Maven: `maven.compiler.source`, `target`, and `release`

In Maven, the corresponding concepts are passed to `javac` by the Maven Compiler Plugin. Property names differ from Gradle:

| Meaning | Gradle (Java plugin) | Maven Compiler Plugin |
| --- | --- | --- |
| Source syntax | `sourceCompatibility` | `maven.compiler.source` |
| Bytecode version | `targetCompatibility` | `maven.compiler.target` |
| Constrain syntax + bytecode + platform APIs | `options.release` | `maven.compiler.release` |

Maven example in `pom.xml` targeting Java 17:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

A suitable Maven Compiler Plugin version passes `--release 17` to a supporting compiler. With older plugins, non-`javac` compilers, or overly old JDKs, behavior can vary; check the plugin version and actual compiler command.

Traditional approach:

```xml
<properties>
    <maven.compiler.source>17</maven.compiler.source>
    <maven.compiler.target>17</maven.compiler.target>
</properties>
```

It shares the same limitations as `-source`/`-target`. On JDK 9+, prefer `release` when target Java API safety matters. In direct `javac` invocations, do not mix `--release` with `-source`/`-target`. In Maven, avoid setting all three properties simultaneously without a verified plugin-specific reason.

Build verification commands:

```bash
# macOS / Linux
./mvnw clean verify

# Windows PowerShell
.\mvnw.cmd clean verify
```

**Maven Wrapper** selects the Maven version; **Maven Toolchains Plugin** (if configured) can help select the JDK for the compiler. Maven Wrapper, like Gradle Wrapper, does not set the API target or download the right Java runtime for your application.

## 8. Why You Still Must Distinguish Toolchain, Wrapper, `JAVA_HOME`, and Runtime

Four items can carry four different versions:

| Component | What It Determines | Common Way to Check / Set |
| --- | --- | --- |
| Gradle Wrapper | Version of **Gradle** running the build | `gradle/wrapper/gradle-wrapper.properties`; `./gradlew --version` |
| Maven Wrapper | Version of **Maven** running the build | `.mvn/wrapper/maven-wrapper.properties` or matching Wrapper config; `./mvnw -version` |
| Compile JDK/toolchain | Actual `javac` compiler used in tasks | `java.toolchain` in Gradle; Maven toolchains/compiler config |
| `--release` / `options.release` | Target syntax, bytecode, and platform APIs | `javac --release` or task/compiler plugin config |
| Production JVM | Runtime loading and executing classes | `java -version` on deploy host/container; base runtime image |

`JAVA_HOME` typically affects the JDK used to launch the build tool when no separate selection mechanism exists. However, the Gradle Daemon, toolchains, IDE settings, and CI configuration can select a different JVM/JDK than the terminal window. Thus **`java -version` does not prove `compileJava` is using the right JDK**.

In a Gradle project, you can inspect the environment with:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean compileJava --info
```

On Windows, change `./gradlew` to `.\gradlew.bat`. The `javaToolchains` task name and log format depend on Gradle, plugins, and versions; inspect the actual output to see discovered installations/toolchains and which compiler the task uses. If the required JDK is not installed and no provisioning mechanism is configured, do not expect `options.release` to supply that JDK.

CI/CD rule of thumb: explicitly select **Gradle/Maven version**, **compiler JDK**, **release target**, and **runtime image JDK**, then verify the entire chain with a build and tests on the target runtime. The Java compile target never replaces choosing the right runtime.

## 9. Verifying via Bytecode, APIs, and Real Execution

A verification workflow is more reliable than just reading config files:

**Step 1 — Confirm compiler and release target.** Inspect the Java toolchain or Maven compiler settings and check compile task logs. When invoking `javac` directly, run `javac -version` and `javac --help` to see available releases.

**Step 2 — Confirm bytecode.** For a compiled Java class, run:

```bash
javap -verbose HelloRelease
```

Look for `major version`: 52 is Java 8, 55 is Java 11, 61 is Java 17, 65 is Java 21. Run `javap` on the exact class file from the latest build's output directory; if multiple copies share the same name on the classpath, pass the exact class file path or `-classpath`.

**Step 3 — Check Java platform APIs.** Compile with `--release <target-version>`; for Gradle check `options.release`; for Maven check `maven.compiler.release`. Avoid concluding API safety solely from class major version.

**Step 4 — Check dependencies.** An external library compiled on Java 21 may have major 65 classes; even if your code compiles with `--release 17`, a Java 17 JVM still cannot run a Java 21 dependency. Check the minimum Java requirement of each major dependency/plugin and the final artifact.

**Step 5 — Run on the target JVM.** Run unit/integration tests and the packaged artifact on the target JVM (e.g., JDK/JRE 17). Execution paths through reflection, native libraries, or runtime-only features may not show up during compilation. Never treat a passing `compileJava` as sufficient proof of deployment compatibility.

After changing target settings, run a **clean build** to prevent stale classes from skewing conclusions:

```bash
# Gradle
./gradlew clean test bootJar

# Maven
./mvnw clean verify
```

`bootJar` is for Spring Boot projects with the task/plugin creating an executable JAR; not every Java library project has that task. Output files appear in `build/libs/` or `target/` depending on the tool and plugins.

## 10. Choosing Configuration by Scenario

| Scenario | Reasonable Choice | Why? |
| --- | --- | --- |
| Spring Boot 3.x app deployed on Java 17 | Toolchain 17; target/release 17 | Aligns with Spring Boot 3.x's Java 17 runtime baseline; more reproducible builds |
| Plain Java code written for Java 8, compiled on JDK 17 | JDK/compiler 17 + `--release 8` | Catches Java 8 syntax, bytecode, and API issues at compile time |
| Java library targeting runtime 17 while CI uses JDK 21 | JDK 21 toolchain + `options.release = 17`; check dependencies and test on Java 17 | Compiler and target Java level are two independent variables |
| Project has `sourceCompatibility = 8`, `targetCompatibility = 8`, builds on JDK 17 | Audit used APIs; consider switching to `options.release = 8` | Source/target pairs do not block newer JDK APIs |
| JAR has major 61 classes yet runs on JVM 11 | Deploy Java 17+ runtime or rebuild for a version **supported by the entire framework and dependencies** | JVM 11 cannot read Java 17 classes |
| Using Gradle Wrapper yet build machines pick different JDKs | Configure Java toolchain; audit CI/IDE | Wrapper fixes the Gradle version, not the compile JDK |

For **Spring Boot**, always check the **system requirements of the exact Spring Boot version you use** before trying to lower the Java target. For example, Spring Boot 3.3 requires Java 17 or higher; setting `--release 8` on application code will not make Spring Boot 3.3 run on Java 8. Framework classes may already use Java 17 class files even if your own code targets Java 8.

## 11. Common Misconceptions and Errors

**"I have `targetCompatibility = 8`, so it definitely runs on Java 8."** No. That only sets the class-file target for classes compiled by that task. `String.repeat`, newer dependencies, or runtime-specific code can still break. Solution: `--release 8` and test on JVM 8, if all dependencies allow it.

**"`sourceCompatibility = 17` means Gradle uses JDK 17."** No. It describes the source level. Use a Java toolchain to pick the compiler JDK; check the JVM running Gradle and the compile task when debugging.

**"Just setting `--release 17` means I don't need to install the JDK."** No. `--release` is an option passed to the compiler in use. The compiler must exist and support release 17; Gradle/Maven do not materialize Java 17 from that number.

**"`sourceCompatibility = 17` and `targetCompatibility = 8` is how to run on Java 8."** Invalid because target is lower than source. Use a source/release matching a genuinely supported runtime version, and never force modern Spring Boot onto an unsupported runtime.

**"I have Java 17 in my terminal, yet CI builds with Java 21."** Likely a different toolchain, Gradle Daemon, or runner setting. Check `./gradlew --version`, `javaToolchains`, and `compileJava` logs; read the CI config instead of looking only at the local shell version.

**"`--release` checks the entire JAR."** No. It constrains how `javac` compiles the sources at hand and platform Java APIs; **it does not recompile or verify bytecode/APIs of external dependencies**. Check minimum Java requirements of frameworks/libraries and test on the target JVM.

**"I changed `--release` yet `javap` still shows the old class."** You may be inspecting the wrong output/path or stale classes from an earlier build. Run `clean`, recompile, and inspect the newly generated class or JAR.

**"Can I combine `javac --release 8 -source 8 -target 8` directly to be extra sure?"** No. `javac` forbids combining `--release` with `-source`/`-target`. Pick one clear mechanism; when safe cross-compilation is needed, prefer `--release`.

## 12. Checklist Before Locking In a Java Target

- [ ] Know the **minimum JVM** needed to run the app and the minimum Java required by Spring Boot, frameworks, and dependencies.
- [ ] Know which compiler JDK **Gradle/Maven actually selects**; do not infer it from the Wrapper or `sourceCompatibility`.
- [ ] Use **`options.release`/`maven.compiler.release`** when you need to lock syntax, bytecode, and platform APIs to a target.
- [ ] Never set `sourceCompatibility` higher than `targetCompatibility`; avoid duplicate, conflicting Java target declarations.
- [ ] Verify the class-file major version with `javap -verbose` on fresh build output.
- [ ] Verify dependencies and frameworks support the target Java version, in both class files and runtime APIs.
- [ ] Run build/tests on CI and test the artifact on the **target JVM**, not only on a developer's newer JDK.

**Conclusion:** `sourceCompatibility` locks **source syntax**; `targetCompatibility` locks **bytecode format**; `--release` locks **syntax + bytecode + Java platform APIs** to the target Java version. For stable Spring Boot builds, pair the right compile target with a **Java toolchain** and verify the actual Java versions of your **framework, dependencies, and deployment environment**.

## Official Technical Documentation

- [Gradle — Building Java & JVM projects: targeting a specific Java version](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [Oracle — `javac`: `--release`, `--source`, and `--target`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [Apache Maven — Guide to Targeting a Java Version](https://maven.apache.org/guides/mini/guide-java-target.html)
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)

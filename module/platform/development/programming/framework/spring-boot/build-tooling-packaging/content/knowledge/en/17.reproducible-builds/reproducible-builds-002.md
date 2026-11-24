# Locking Java, Wrapper, Plugin, and Dependency Versions for Reproducible Builds

## 1. The Problem: Why Do Two Machines Build Differently from the Same Source?

A Spring Boot project runs fine on a developer's machine, yet CI fails with `UnsupportedClassVersionError`; or yesterday's build succeeded, and today Maven/Gradle automatically selects a newer library version that breaks tests. In other cases, both machines build successfully, yet the resulting JAR files have different timestamps, ZIP entry ordering, or metadata.

For a stable build, you must manage **four version groups** and understand inputs beyond versions:

1. **Java/JDK:** compiler, runtime JDK, `--release` API level, vendor, and patch level when strict reproducibility is required.
2. **Build tool via Wrapper:** specific Apache Maven or Gradle distribution, wrapper scripts/JAR, and integrity checksum.
3. **Build plugins:** Spring Boot Maven/Gradle Plugin, compiler/test/package plugins, annotation processors, quality plugins.
4. **Dependencies:** direct libraries, transitive dependencies, BOM/version constraints, and test/runtime/annotationProcessor classpaths.

Remaining factors include repositories, artifact bytes, operating system, locale/time zone, environment variables, build configuration, build-time data, and native tools. **Locking versions is a critical condition, but it does not by itself guarantee byte-for-byte identical output**.

### Expected Outcomes

After this lesson, you will be able to:

- Read and configure `maven.compiler.release`, Maven Toolchains, Gradle Java Toolchains, and `options.release`.
- Generate the Maven Wrapper and Gradle Wrapper, and run the exact tool version locally and in CI.
- Inspect `distributionUrl`, `distributionSha256Sum`, and wrapper integrity.
- Pin plugin versions and Spring Boot parent/BOM, avoiding arbitrary `LATEST`, `RELEASE`, `1.+`, or `-SNAPSHOT` in release builds.
- Create standalone Spring Boot Maven and Gradle projects with Java 17 code, tests, and executable JARs.
- Enable **Gradle dependency locking** to generate `gradle.lockfile` and update it in a controlled manner.
- Know that **Maven 3 has no built-in dependency lockfile equivalent to Gradle dependency locking**; use managed versions, dependency tree, Enforcer, and repository policies to reduce nondeterminism.
- Control JVM runtime versions in containers/CI, compare dependency graphs, and distinguish reproducibility levels.
- Analyze “local OK, CI FAIL” or “same source, different output” before bumping versions by guesswork.

**Chosen example baseline:** Spring Boot **3.5.16**, Java **17**, Maven **3.9.16**, Gradle **8.14.3**. These are specific compatible releases for illustration: Spring Boot 3.5.x requires Java 17+ and supports Maven 3.6.3+ and Gradle 8.4+ in the 8.x line. These patch/version choices **are not mandatory for every project**; teams must maintain support policies and evaluate security updates.

## 2. “Version Locking” and “Reproducible Build” Have Three Distinct Levels

### 2.1. Stable Dependency Resolution

The baseline goal is that **for the same project state, the build tool resolves the same set of dependency coordinates**:

~~~text
org.springframework.boot:spring-boot-starter:3.5.16
org.springframework:spring-context:6.2.x
org.junit.jupiter:junit-jupiter:5.x
...
~~~

The `6.2.x`/`5.x` versions above are **pattern illustrations**, not verified version numbers for the sample build. Use `dependency:tree`/`dependencyInsight` to read the exact selected versions.

Pinning direct dependencies **does not guarantee** the transitive graph if dynamic ranges are used, if a BOM changes, if a dependency POM is altered after publishing, or if a repository serves inconsistent bytes for the same GAV.

### 2.2. Consistent Build Behavior

Beyond dependencies, you must use the exact Maven/Gradle, JDK, plugins, and build flags:

~~~text
source + tests + config
         |
         v
JDK 17 + Maven 3.9.16 / Gradle 8.14.3
         |
         v
Spring Boot plugin 3.5.16 + pinned build plugins
         |
         v
dependency graph controlled by BOM / Gradle locks
         |
         v
JAR + reports + test results
~~~

If Jenkins uses system `mvn` (3.8.x) while a laptop uses Maven 3.9.x, or CI picks JDK 21 while local uses JDK 17, identical source code is not enough to claim the build tools are locked.

### 2.3. Bit-for-Bit Reproducible Artifact

The higher goal: **for identical defined inputs, the produced JAR must have an identical hash**. This requires addressing additional factors:

- Timestamps in ZIP entries and build metadata.
- File ordering inside the archive.
- Absolute paths or hostnames written into generated files.
- Build-time dates, random identifiers, Git metadata, and clock-dependent resources.
- Java vendor/patch version when compilers, annotation processors, or tooling produce differing output.
- Encoding, locale, time zone, and filesystem behavior.
- Dependencies with mutable bytes despite identical version coordinates.
- Plugins or native toolchains with platform-dependent output.

**Never claim “reproducible = pom.xml just has versions.”** This lesson locks the primary tools first, then provides an appropriate hash/metadata verification checklist at the end.

## 3. Separation of Responsibilities: Where Is Each Version Locked?

| Component | Maven | Gradle | Key takeaway |
| --- | --- | --- | --- |
| Java language/API level | `maven.compiler.release=17` | `options.release.set(17)` | Constrains bytecode/API, **does not select the exact JDK installation** |
| JDK running compiler/tests | Maven Toolchains/JAVA_HOME/CI JDK | Java Toolchains + JDK running Gradle | Vendor and patch level may still differ |
| Build tool version | `mvnw` + `.mvn/wrapper/maven-wrapper.properties` | `gradlew` + `gradle/wrapper/gradle-wrapper.properties` | Must commit Wrapper and verify checksums |
| Spring Boot build plugin | Parent/pluginManagement/explicit plugin version | `plugins { id(...) version "..." }` | Plugin version differs from dependency BOM version |
| Spring libraries | `spring-boot-starter-parent`/imported BOM | `platform("...spring-boot-dependencies:...")` | BOM manages versions, **does not add dependencies automatically** |
| Other plugins | Pin versions in `build/plugins`/`pluginManagement` | Pin plugin IDs in `plugins`/`pluginManagement` | Do not leave plugin resolution floating to latest |
| Transitive libraries | Maven dependency mediation, management, repository policy | Gradle constraints + `gradle.lockfile` | Gradle has a built-in lockfile; Maven 3 has no default equivalent |
| Artifact bytes | Reproducible archive/plugin options | Reproducible archive task options | Must verify hashes, not infer from resolved versions |

A `BOM` or version catalog is only **part** of the strategy. Wrapper and JDK must be managed by both the repository and CI; a BOM cannot replace them.

## 4. Locking Java: Java 17 Does Not Always Mean the Same JDK

### 4.1. The JDK Running Maven/Gradle

On Linux/macOS:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
mvn -version
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
mvn -version
~~~

`java -version` shows Java on PATH; `mvn -version` shows the Java runtime Maven is using. They can differ if the launcher or environment is configured differently. For Gradle, check:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
~~~

`javaToolchains` lists the JDKs Gradle detects; `--version` shows the Gradle distribution and JVM running the build. The toolchain chosen for compilation can **differ from the JVM running the Gradle daemon**.

### 4.2. Maven Compiler Release

In `pom.xml`, declare:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

When the compiler plugin supports `--release`, compiling with `--release 17` restricts the Java API and class-file target to Java 17. It **does not** install JDK 17 and does not force the Maven JVM to run only Java 17.

For example, a compiler running on JDK 21 can still compile for target Java 17 thanks to `--release 17`. The output can run on Java 17 if **all runtime dependencies** are also Java 17 compatible. `--release` does not downgrade the target of an existing dependency JAR.

### 4.3. Maven Toolchains Selects a Different JDK from the Maven Launcher

The Maven Toolchains Plugin lets the compiler and toolchain-aware plugins use a dedicated JDK. A Maven declaration might include:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-toolchains-plugin</artifactId>
    <version>3.3.0</version>
    <executions>
        <execution>
            <goals>
                <goal>select-jdk-toolchain</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <toolchains>
            <jdk>
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

This is a **plugin snippet inside `<build><plugins>`**, not a complete POM file; the full Maven project example in Section 6 uses a simpler approach: requiring the Maven JVM itself to run Java 17 in CI and enforcing it with Enforcer.

Depending on setup, JDK toolchains are described in `~/.m2/toolchains.xml` or via Maven Toolchains 3.2+ auto-discovery. `toolchains.xml` contains **machine-specific** JDK paths, so never commit one developer's absolute path as a company-wide standard. Build tooling should be configured to **fail explicitly if a matching JDK is not found**, rather than silently choosing a newer out-of-contract JDK.

**Important distinction:** Maven Enforcer's `requireJavaVersion` checks the Java running Maven. It does not replace selecting/checking a separate toolchain JDK if compilation/tests use a different JDK.

### 4.4. Gradle Java Toolchain and options.release

In `build.gradle.kts`:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
~~~

This block requires the `java` plugin or a plugin providing the Java extension. The toolchain selects a **JDK with language version 17** for compilation and tasks supported by the Java plugin; `--release 17` prevents the compiler from using newer JDK APIs than targeted. Gradle can auto-provision a toolchain **when toolchain download repositories are configured**; if no matching JDK exists and provisioning is unconfigured, the build can fail.

**Locking to Java 17 major ≠ pinning the exact JDK binary**: Adoptium 17.0.x and another vendor's 17.0.y are both Java 17, yet bytecode/tool behavior may differ. When bit-for-bit reproducibility is required, also pin vendor, patch, and artifact digest in CI/container/toolchain provisioning per team policy.

### 4.5. Java Running the Packaged Application

A project built with JDK 17 may run on Java 21 in production. That is sometimes valid, though compatibility testing is required. If the goal is **running strictly on Java 17 in production**, you must configure the specific runtime image/`JAVA_HOME`/container tag, not infer it from the compiler's Java release. Use a container image digest instead of a mutable tag for strict reproducibility requirements.

## 5. Maven Wrapper: Locking the Maven Distribution in the Repository

### 5.1. What Problem Does the Wrapper Solve?

You should not rely on “every developer manually installs the right Maven version” based only on README instructions. Apache Maven Wrapper adds `mvnw`/`mvnw.cmd` scripts and configuration under `.mvn/wrapper/`. When invoked, the wrapper downloads or reuses the **selected Maven distribution**.

Typical layout:

~~~text
version-lock-maven/
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
├── pom.xml
└── src/...
~~~

Different Maven Wrapper distribution types use `maven-wrapper.jar`, `MavenWrapperDownloader.java`, or scripts only; **do not assume every version contains all three files**.

### 5.2. Generating Maven Wrapper with Maven 3.9.16

If the initial machine has Maven installed:

~~~bash
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper \
  -Dmaven=3.9.16 -Dtype=only-script
~~~

In Windows PowerShell, put it on a single line:

~~~powershell
mvn -N org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper "-Dmaven=3.9.16" "-Dtype=only-script"
~~~

`-N` is non-recursive (useful at multi-module roots). `-Dmaven=3.9.16` chooses the Maven distribution; `only-script` is a Maven Wrapper type that does not require committing a wrapper JAR. **Running this goal is a setup/upgrade step**, not a command run on every build.

Once generated, use:

~~~bash
./mvnw -version
./mvnw clean verify
~~~

Windows:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
~~~

Commit the generated wrapper scripts/config properly. If no wrapper exists in the project, `./mvnw` is not a valid command—use `mvn` to **generate** the wrapper first.

### 5.3. The maven-wrapper.properties File

A configuration might contain:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.16/apache-maven-3.9.16-bin.zip
~~~

**Never type an arbitrary checksum** into `distributionSha256Sum`. Maven Wrapper supports `distributionSha256Sum` to verify the Maven distribution and (for applicable wrapper JAR types) `wrapperSha256Sum` to verify the wrapper JAR. Obtain the **official SHA-256 hash of that exact file** from a trusted release source and add it to the properties or pass the parameter supported by Maven Wrapper Plugin. Only set checksums when you have verified values; a bogus string breaks the wrapper and gives a false sense of security.

**Locking a version does not replace verifying the download source**. Review wrapper scripts/JAR and the distribution URL on every update; CI should only use the committed wrapper rather than downloading replacement scripts from uncontrolled network commands.

### 5.4. Locked Maven Version Differs from Maven Plugins

Running Maven 3.9.16 **does not** force Maven Compiler Plugin or Spring Boot Maven Plugin to a fixed version. Plugin versions are separate artifacts with their own lifecycle/config. Never confuse the Maven distribution version with `maven-compiler-plugin`'s version.

## 6. Complete Maven Project: Java 17 + Parent/BOM + Pinned Plugins

### 6.1. Directory Tree

The standalone Maven exercise uses:

~~~text
version-lock-maven/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/maven-wrapper.properties
└── src/
    ├── main/java/com/example/lockdemo/
    │   └── VersionLockApplication.java
    └── test/java/com/example/lockdemo/
        └── VersionLockApplicationTest.java
~~~

Wrapper files are generated using the command in Section 5; if you created the project manually with only `pom.xml` and `src/`, use an installed Maven to generate the wrapper.

### 6.2. Complete pom.xml File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>version-lock-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>verify-build-runtime</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireMavenVersion>
                                    <version>[3.9,4.0)</version>
                                </requireMavenVersion>
                                <requireJavaVersion>
                                    <version>[17,18)</version>
                                </requireJavaVersion>
                            </rules>
                            <fail>true</fail>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Why is this configuration more controlled than a default POM?**

- `spring-boot-starter-parent:3.5.16` fixes the Spring Boot parent and manages a set of dependency/plugin versions. The parent also configures `spring-boot-maven-plugin:repackage` in the lifecycle when the plugin is declared.
- `maven.compiler.release=17` and `java.version=17` specify the project's Java target by Boot convention.
- Compiler/Surefire/Enforcer/Boot build plugins have **explicit versions**, rather than drifting if Maven selects another plugin release.
- `requireMavenVersion [3.9,4.0)` rejects Maven older than 3.9 or Maven 4+; **Wrapper 3.9.16** further pins down to the exact Maven release.
- `requireJavaVersion [17,18)` requires the **JDK/JRE running Maven** to be in the Java 17 line. This is a strict policy of the example, not a Spring Boot requirement that every build run on Java 17.
- `project.build.outputTimestamp` provides a declared timestamp for archive plugins supporting reproducible archives. It does not automatically fix other nondeterministic sources such as generated code containing the current time.

**Important note on Enforcer:** with JDK toolchains, the plugin may check the Java launcher without verifying every toolchain. If you intentionally run Maven on JDK 21 to compile target 17 source, the `[17,18)` rule will fail, even though compiling with `--release 17` would technically succeed. This is an intentional policy choice for the example, not a bug.

### 6.3. Complete Java Source

Create `src/main/java/com/example/lockdemo/VersionLockApplication.java`:

~~~java
package com.example.lockdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class VersionLockApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionLockApplication.class, args);
    }

    public static String message() {
        return "LOCKED_OK: hello";
    }

    @Bean
    ApplicationRunner showMessage() {
        return args -> System.out.println(message());
    }
}
~~~

This is a complete Java file, runnable with `spring-boot-starter` and Java 17. `ApplicationRunner` prints one line after the Spring context initializes. The exact line **printed by this code** is:

~~~text
LOCKED_OK: hello
~~~

Spring Boot normally prints additional startup logs depending on the environment; do not assume total stdout is only a single line.

### 6.4. Unit Test Independent of External Services

Create `src/test/java/com/example/lockdemo/VersionLockApplicationTest.java`:

~~~java
package com.example.lockdemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class VersionLockApplicationTest {

    @Test
    void messageIsStable() {
        assertEquals("LOCKED_OK: hello",
                     VersionLockApplication.message());
    }
}
~~~

`spring-boot-starter-test` provides JUnit Jupiter. The test does not start a database, HTTP server, or container, verifying version locking and compiler/test plugins without external nondeterminism interfering. Maven Surefire from the sample POM runs the test during `mvn test`/`mvn verify`.

### 6.5. Running Maven via Wrapper

~~~bash
./mvnw -version
./mvnw clean verify
java -jar target/version-lock-maven-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd clean verify
java -jar .\target\version-lock-maven-1.0.0.jar
~~~

If you have no Wrapper because you skipped step 5, run `mvn clean verify` **after confirming a compatible Maven/JDK** to build the artifact, then generate the wrapper before committing the project.

Things to verify:

1. `./mvnw -version` displays Maven **3.9.16** and Maven's JVM is in Java **17.x**.
2. Enforcer runs in the `validate` phase and fails early if Maven/Java versions violate policy.
3. Unit test `messageIsStable` passes.
4. `target/version-lock-maven-1.0.0.jar` is an executable Spring Boot JAR, not a plain thin JAR.
5. `java -jar` runs and prints the `LOCKED_OK: hello` line.

### 6.6. Custom Parent and Spring Boot BOM

If your company already has a Maven corporate parent, **do not declare two parents**. A POM can have only one direct parent. You can import the Boot BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

And you must manage Maven plugins/executions in the parent or app module. **Importing the BOM only manages dependency versions; it does not automatically import plugin management or the `repackage` execution** from `spring-boot-starter-parent`.

## 7. Maven dependencyManagement/BOM Is Not a Complete Lockfile

### 7.1. What a BOM Actually Solves

A BOM is a POM containing a set of managed dependency coordinates/versions. When a child declares a Spring Boot starter without specifying a version, Maven selects the version managed by the parent/imported BOM. This keeps Spring libraries aligned within a tested compatible release train.

Example in `pom.xml`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

The starter's version is managed by the parent. However, the BOM **does not automatically add** the starter to the classpath; the child must declare the dependency.

### 7.2. Why Maven Does Not “Lock Everything” with Just a BOM

An application includes libraries outside the Boot BOM or new dependencies entering via the transitive graph. Maven dependency mediation, `dependencyManagement`, scopes, and version ranges determine the outcome. When a BOM version changes or the dependency graph shifts, transitive versions can change. **Maven 3 does not emit a transitive lockfile by default** equivalent to `gradle.lockfile`.

To stay in control:

- Pin direct dependencies outside the BOM and pin the BOM/parent version.
- Avoid version ranges/dynamic/latest and `SNAPSHOT` in production release graphs.
- Pin build plugins and plugin dependency versions when needed.
- Store the dependency graph and artifact checksums/SBOM for releases.
- Enforce a repository mirror/immutable release artifact policy.
- Use Maven Enforcer rules like `dependencyConvergence`/`requireUpperBoundDeps` **where appropriate** to catch certain conflicts; these rules **do not generate a dependency lockfile**.
- Evaluate third-party lock/dependency verification tools for maintenance posture, but do not assume Maven natively provides Gradle's `--write-locks`.

### 7.3. Using Dependency Tree to Inspect Actual Versions

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
./mvnw clean verify
~~~

`dependency:tree` shows Maven's resolved graph, including transitive versions and scopes. `help:effective-pom` shows parent inheritance, BOM/management, and plugins after merging. Invoking goals from CLI may resolve plugin versions via parent plugin management or Maven's plugin resolution; in strict reproducible workflows, pin versions of frequently used **reporting plugins** as well.

**Do not treat `dependency:tree` output as an input file that Maven automatically verifies on subsequent runs.** It is a report, not a built-in lock. For CI drift detection, compare normalized reports/SBOMs via a dedicated process or enforcement plugin.

## 8. Gradle Wrapper: Locking the Distribution and Verifying Checksums

### 8.1. Why Commit the Wrapper?

The Gradle Wrapper consists of scripts and configuration for a chosen Gradle version:

~~~text
version-lock-gradle/
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── settings.gradle.kts
├── build.gradle.kts
└── src/...
~~~

**Commit the scripts, properties, and wrapper JAR** generated by official Gradle tooling. The Gradle wrapper JAR is an executable binary at the build bootstrap layer: verify its source/signature or checksum per Gradle's guidelines rather than only reviewing text files.

### 8.2. Generating the Wrapper with Gradle 8.14.3

If the first environment already has a suitable Gradle installed:

~~~bash
gradle wrapper --gradle-version=8.14.3 --distribution-type=bin
~~~

Once the wrapper is present:

~~~bash
./gradlew wrapper --gradle-version=8.14.3 --distribution-type=bin
./gradlew --version
~~~

Gradle documentation recommends running the wrapper task a second time after upgrading versions so the wrapper JAR/scripts are updated to the new release if existing files were not yet upgraded. In real repositories, review the diff of `gradle/wrapper`, and do not run this task arbitrarily inside a release pipeline.

### 8.3. The gradle-wrapper.properties File

A generated file might contain lines like:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

Properties may vary slightly by Gradle Wrapper release. The **version-locking** part is `gradle-8.14.3-bin.zip`. For integrity, add `distributionSha256Sum` with the **real, full SHA-256 value of that distribution ZIP**, obtained from Gradle release checksums:

https://gradle.org/release-checksums/

You can view the official checksum file:

~~~bash
curl -fsSL https://services.gradle.org/distributions/gradle-8.14.3-bin.zip.sha256
~~~

**Do not fill in sample/unverified hard-coded hashes**. Gradle Wrapper verifies `distributionSha256Sum` when downloading a new distribution; if the ZIP is already cached, verification behavior differs, and the wrapper checksum must not be treated as verifying all build dependencies. Gradle documentation stresses verifying **`gradle-wrapper.jar`** separately because that binary runs before Gradle distribution download/verification occurs.

### 8.4. Running Consistently Across Environments

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean build
~~~

**Never replace `./gradlew` with system `gradle` in CI** if the goal is using the locked distribution. The wrapper does not pin the JDK running Gradle; Java must be managed separately.

## 9. Complete Gradle Project: Plugin, BOM, Toolchain, and Dependency Locking

### 9.1. Structure

This is a **standalone project separate from the Maven example**, reusing the same Java application/test files from Sections 6.3 and 6.4:

~~~text
version-lock-gradle/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/gradle-wrapper.jar
├── gradle/wrapper/gradle-wrapper.properties
├── gradle.lockfile            # Generated after creating locks
└── src/
    ├── main/java/com/example/lockdemo/
    │   └── VersionLockApplication.java
    └── test/java/com/example/lockdemo/
        └── VersionLockApplicationTest.java
~~~

The Java source files **must be placed in the exact package paths** as in Section 6; do not place Maven POM and Gradle build scripts in one directory and assume the same artifact will be published.

### 9.2. The settings.gradle.kts File

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "version-lock-gradle"
~~~

This is a complete Kotlin DSL file. Gradle plugin resolution and dependency resolution can use different repositories; declaring both makes auditing easier. In enterprises, replace/wrap them with trusted artifact repository proxies, manage repositories centrally, and fail builds that attempt to use out-of-policy repositories.

### 9.3. Complete build.gradle.kts File

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )

    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

dependencyLocking {
    lockAllConfigurations()
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

**Inspect each lock carefully:**

- The `org.springframework.boot` plugin is pinned to **3.5.16**; never leave versions floating via dynamic plugin versions.
- The `java` core plugin provides `compileJava`, `test`, and `jar`. The Boot plugin recognizes the Java project and creates `bootJar`.
- The Java toolchain selects Java **17**; `options.release=17` restricts API/bytecode and enforces UTF-8 encoding.
- `platform(...)` imports the Spring Boot BOM into Gradle dependency resolution; **it does not add starters automatically**.
- `spring-boot-starter`/`spring-boot-starter-test` omit versions because the BOM manages them. If a dependency is not managed by the BOM, declare an explicit version/constraint.
- `junit-platform-launcher` is included in test runtime per Gradle/JUnit guidance, with its version managed by the BOM.
- `dependencyLocking.lockAllConfigurations()` enables Gradle locking for resolved configurations. The lockfile appears **after running the lock-generation command**, not merely by adding this block.
- `AbstractArchiveTask` drops per-file timestamps and normalizes file ordering for supported Gradle archive tasks. It aids reproducible archives, though **it cannot guarantee bit-for-bit identity** if generated file contents depend on the environment.

**Do not add `io.spring.dependency-management` to this project just to get the BOM**: the example already uses Gradle's native `platform`. Having the Boot plugin version and Spring Boot BOM both at `3.5.16` is an **auditable illustrative convention**; upgrades must consider both together.

### 9.4. Java Source and Run Output

Copy the exact two Java files from Sections 6.3/6.4 into this Gradle project. `VersionLockApplication.message()` returns `LOCKED_OK: hello`; the test asserts that exact value without depending on build time or network.

Once Gradle has resolved dependencies, run:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/version-lock-gradle-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\version-lock-gradle-1.0.0.jar
~~~

If the archive name/classifier is customized in your project, use the actual file under `build/libs/`. The line printed by the application itself:

~~~text
LOCKED_OK: hello
~~~

Additional Boot startup logs may appear; the output above is not the entirety of stdout.

## 10. Gradle Dependency Locking — Creating and Maintaining gradle.lockfile

### 10.1. Why Isn't a BOM Enough?

Suppose dependencies declare:

~~~kotlin
implementation(
    platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
)
implementation("org.springframework.boot:spring-boot-starter")
~~~

A BOM selects a set of versions, yet Gradle still performs dependency graph resolution across module constraints and conflicts. With `lockAllConfigurations`, Gradle can persist the **final resolved versions** of direct and transitive dependencies per configuration. Next time, if the graph attempts to pick a different version without a valid lock update, Gradle fails instead of drifting silently.

### 10.2. Initializing the Lockfile

In a project **with `dependencyLocking` enabled**, run:

~~~bash
./gradlew dependencies --write-locks
./gradlew clean test bootJar
~~~

`dependencies --write-locks` creates/updates lock state for **resolved lockable configurations**. On a basic single-module project, this command works well for initial generation; you can also run:

~~~bash
./gradlew test bootJar --write-locks
~~~

to ensure configurations used by real tasks are resolved while writing locks. `--write-locks` commands **are allowed to modify lockfiles**; do not use them in routine CI verification.

Once created, commit `gradle.lockfile` alongside build scripts. Lockfiles normally live at the root of each project/subproject; a multi-project build can have multiple separate `gradle.lockfile` files. **Note:** in a multi-project build, `./gradlew dependencies` at the root often reports only on the root, without guaranteeing all subproject configurations were resolved. Call `:service:dependencies`, `:shared:dependencies`, or define a dedicated resolve-all task, then inspect all generated lockfiles.

### 10.3. What Does gradle.lockfile Look Like?

This is a **structural model example**, not byte-for-byte output of the Section 9 project; exact versions must be generated by Gradle from real dependency resolution:

~~~text
# This is a Gradle generated file for dependency locking.
com.example:library-a:1.2.3=compileClasspath,runtimeClasspath
com.example:library-b:2.4.6=runtimeClasspath
empty=annotationProcessor
~~~

Each line lists a locked `group:name:version` and the participating configurations; the `empty` line lists configurations that were resolved with no dependencies. **Do not copy this example file** as a real project's lockfile. Run Gradle `--write-locks` to generate the file with real dependencies, then review the diff and commit.

### 10.4. Building After Having a Lockfile

In normal CI runs:

~~~bash
./gradlew --no-daemon clean test bootJar
~~~

Do not include `--write-locks`: if dependency resolution conflicts with the locked state, the build must **fail** and flag that a change requires review. Note that Gradle lock state only applies to configurations that are resolved and have locking enabled.

### 10.5. Intentional Dependency Updates

When upgrading Boot from one release to another, update:

1. Plugin `id("org.springframework.boot") version "..."`.
2. BOM `spring-boot-dependencies:...`.
3. Dependencies/constraints pinned outside the BOM, if any.
4. Regenerate locks on the **affected configurations**, then inspect the full diff and run tests.

Example selective lock update:

~~~bash
./gradlew dependencies \
  --update-locks org.apache.commons:commons-lang3
~~~

`--update-locks` tells Gradle to update a specific module (which may pull related transitive changes); it does not guarantee all related modules stay at old versions if the resolver requires changes. **Do not use this command to upgrade the Spring Boot BOM plugin itself**; it applies only to dependency locks and does not update plugin versions pinned in `plugins`.

### 10.6. What a Lockfile Does Not Lock

Gradle dependency locking **does not**:

- Pin the Gradle Wrapper/JDK distribution.
- Pin all plugin versions resolved in the `plugins` block.
- Verify the SHA of every downloaded artifact.
- Lock source dependencies, local file dependencies, or external tools.
- Guarantee the output JAR stays unchanged if build scripts generate content from dates/times.
- Prevent drift if the project uses changing modules (`-SNAPSHOT`, mutable coordinates) whose bytes changed under the same version.

Gradle documentation warns **against using dependency locking with changing versions** to expect content reproducibility. Locking a GAV cannot control artifact bytes republished under the same coordinate.

## 11. Plugin Versions: Separate from Library Dependency Versions

### 11.1. Maven: Plugin Versions and Plugin Dependencies

A Maven build invokes lifecycle-bound compiler/Surefire/JAR plugins plus additionally configured plugins. The version of `spring-boot-maven-plugin` **does not equal** “the version of all application dependencies”; some plugins carry their own dependencies.

Controls:

- Use `spring-boot-starter-parent` or a maintained corporate parent with `pluginManagement`.
- Pin plugins used directly under `<build><plugins>` or manage them in `pluginManagement`.
- Run `mvn help:effective-pom` and inspect plugin goals/versions in build logs.
- Avoid invoking CLI plugins as “latest,” which can accidentally pick newer versions on CI machines.
- For tightly controlled builds, evaluate Maven Enforcer `requirePluginVersions` and plugin dependency policies; do not blindly enable that Enforcer rule before lifecycle/super-POM plugins are properly managed.

A project's Maven `dependencyManagement` **does not automatically manage dependencies inside plugin realms**. When a plugin pulls its own dependencies, inspect plugin metadata/config if auditing or conflict resolution is needed.

### 11.2. Gradle: Plugin Marker Versions and Classpath

In Gradle Kotlin DSL:

~~~kotlin
plugins {
    id("org.springframework.boot") version "3.5.16"
}
~~~

The version pinned in the `plugins` block is the **plugin version**. In multi-module projects, versions can be managed in root settings `pluginManagement`, a version catalog, or convention plugin classpath, and applied per module. **An application configuration's Gradle dependency lockfile does not automatically lock all plugin implementation artifacts or the wrapper distribution**.

Avoid:

~~~kotlin
plugins {
    id("org.springframework.boot") version "+"
}
~~~

This configuration is an **illustrative anti-pattern**; never copy it. Fix versions and verify plugin repository/provenance.

### 11.3. Annotation Processors and Test Tools

If the project uses Lombok, MapStruct, or `spring-boot-configuration-processor`, dependencies on the `annotationProcessor` path **also affect compile output**. In Maven, configure compiler annotation processor paths with explicit/managed versions; in Gradle, declare `annotationProcessor(...)` and enable locking for resolved configurations.

An unchanged Java class can generate different code when a Lombok/MapStruct processor version changes. Similarly, test engine/Surefire/Gradle Test worker versions can alter which tests run and how reports are produced.

## 12. Never Use Dynamic, SNAPSHOT, or Mutable Repositories for Release Builds

### 12.1. Declarations Prone to Drift

| Configuration | Issue | Replace with |
| --- | --- | --- |
| Maven `<version>[1.0,2.0)</version>` | Version range can select a newer release when repository updates | Explicitly chosen/approved version |
| Maven `LATEST` or `RELEASE` | Depends on current metadata, unsuitable for fixed builds | Literal version or BOM with explicit version |
| Maven `1.0-SNAPSHOT` | Bytes can change under the same coordinate | Immutable release version or digest/provenance |
| Gradle `implementation("x:y:1.+")` | Picks newer versions per metadata/cache | Explicit version + Gradle locking |
| Gradle `latest.release` | Depends on repository state | Explicit version |
| Gradle `changing = true` | Allows artifact bytes to change for the same coordinates | Immutable release repositories |
| Container image tag `jdk:17` | Tag can change its underlying image digest | Image digest when high reproducibility is required |
| Plugin version `+` | Build tasks can change without source changes | Pinned plugin release |

During development, SNAPSHOT/dynamic versions can help integrate quickly. However, **when preparing a release**, produce immutable release artifacts and audit versions/graphs rather than treating local caches as the source of truth.

### 12.2. Pinning a Version Is Insufficient If Artifact Bytes Change

Suppose an internal repository allows re-uploading `com.example:lib:1.0.0` with different contents. Maven/Gradle today and yesterday may both report **version 1.0.0** yet use two different JARs. The solution is **repositories that disallow overwriting releases**, artifact checksums/signatures, trusted mirrors, provenance, and byte-level dependency verification.

Running `--offline` does not prove build reproducibility: it merely uses cached items, potentially masking stale metadata or missing dependencies. **A reproducible build must be able to fully explain the origin and identity of every resolved artifact**, including on a clean runner accessing trusted repositories.

### 12.3. Repository Order and Caches

Two Maven settings files with different mirrors, or Gradle repositories containing the same GAV with different bytes, introduce nondeterminism. In enterprises, establish a consistent repository proxy/mirror and enforce rules separating releases from snapshots.

Do not use `mvn -U` or `./gradlew --refresh-dependencies` as a “version lock.” They affect cache/revalidation, not dependency management or lock policy. After refreshing, still inspect the graph and ensure bytes match trusted sources.

## 13. Comparing the Dependency Graph and Actual Artifacts

### 13.1. Maven Diagnostics

~~~bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
jar tf target/version-lock-maven-1.0.0.jar
~~~

`effective-pom` shows parent, plugins, and management after Maven model merging. `dependency:tree` shows version selection and scopes. `jar tf` inspects **the files actually packaged into the archive**, not just graph metadata.

A Boot executable JAR typically contains:

~~~text
BOOT-INF/classes/com/example/lockdemo/VersionLockApplication.class
BOOT-INF/lib/spring-boot-*.jar
org/springframework/boot/loader/launch/JarLauncher.class
~~~

The `*` in the Spring Boot file line merely denotes “multiple versioned filenames” in the example. Inspect actual filenames with `jar tf`; do not treat `spring-boot-*.jar` as a literal entry name.

### 13.2. Gradle Diagnostics

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency spring-boot
./gradlew clean test bootJar
jar tf build/libs/version-lock-gradle-1.0.0.jar
~~~

If running in Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency spring-boot
.\gradlew.bat clean test bootJar
~~~

`dependencyInsight` explains why the resolver picked a version. `gradle.lockfile` captures the lock state; it does not replace dependency graph reports or runtime test verification.

### 13.3. Checking Hashes Across Two Builds

Linux/macOS:

~~~bash
sha256sum target/version-lock-maven-1.0.0.jar
sha256sum build/libs/version-lock-gradle-1.0.0.jar
~~~

On macOS without `sha256sum` installed by default, use:

~~~bash
shasum -a 256 target/version-lock-maven-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash .\target\version-lock-maven-1.0.0.jar -Algorithm SHA256
Get-FileHash .\build\libs\version-lock-gradle-1.0.0.jar -Algorithm SHA256
~~~

**Do not directly compare the Maven JAR hash against the Gradle JAR hash from two different build recipes and call it a bug**: names/layouts/metadata/plugin packaging can differ. Compare **the same recipe** across two environments, with identical source and tools/inputs, and investigate if checksums diverge.

## 14. Achieving Bit-for-Bit Reproducibility: Handling Timestamps and Generated Contents

### 14.1. Maven Reproducible Archive Timestamp

Example POM configuration:

~~~xml
<properties>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Modern Maven plugins, including archive plugins and the Spring Boot repackager, use this property to normalize timestamps in outputs. `2026-01-01T00:00:00Z` is an **illustrative fixed value**; teams can use commit time or `SOURCE_DATE_EPOCH` standardized by their workflow.

**Never promise absolute reproducibility from this property alone**: a generated resource writing `System.currentTimeMillis()`, Git dirty state, file order, or custom metadata will still change the JAR.

### 14.2. Gradle Archive Tasks

Example from Section 9:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

This configuration ensures supported Gradle archive tasks produce normalized file timestamps and stable file ordering, reducing ZIP/JAR differences across machines. Still, `.class` contents or generated files can differ due to compiler/JDK/annotation processors or build script logic.

### 14.3. Inspect Actual Output, Not Just SUCCESS Logs

Verification flow:

1. Check out the same commit in two clean environments.
2. Use the Wrapper, exact JDK/toolchain/CI image, and repositories.
3. Run tests/build with the exact same commands.
4. Inspect dependency graphs and plugin versions.
5. Compute SHA-256 of output artifacts and compare.
6. If different, inspect ZIP entries, timestamps, generated resources, build-info, manifest, and bytecode; do not compare file size alone.

When artifacts differ while business tests pass, it can still be a reproducibility failure **if** the release contract requires identical digests. Conversely, some builds intentionally embed commit timestamps or release signing data so outputs differ by design; document **which inputs are allowed to vary**.

## 15. Protecting Supply Chain and Integrity When Locking Versions

### 15.1. The Wrapper Is Code Executed Before the Build

`mvnw`, `gradlew`, and wrapper JARs/scripts can execute commands on local/CI machines. Therefore:

- Commit Wrapper files into source control.
- Review diffs when upgrading Maven/Gradle releases.
- Check `distributionUrl` does not point to an unapproved mirror.
- Obtain official SHA-256 checksums for the distribution; verify the wrapper JAR separately where applicable.
- Never download/execute wrapper scripts directly from an untrusted URL on every CI job.
- Manage repository credentials via a secret store; never commit tokens into properties.

### 15.2. Dependency Verification Is a Separate Layer

Gradle provides **dependency verification** (`gradle/verification-metadata.xml`) to check checksum/signature metadata of resolved artifacts. It **complements** `gradle.lockfile`: the lockfile pins coordinates/versions, while verification metadata detects when bytes/signatures fail expectations.

Standard Maven builds check checksum consistency per repository/download policy and can add artifact verification/signing in supply-chain workflows. Do not claim a BOM or `dependency:tree` provides comprehensive default SHA verification.

### 15.3. A Build Can Become “Too Old”

Pinning versions forever does not equal security. When a dependency has a critical CVE, **upgrade in a planned way**. Good policy combines:

- Stable, reviewable dependency upgrades.
- Vulnerability scanning/SBOM and license checks.
- CI regression/security tests.
- Marking release artifacts immutable.
- Recording upgrade rationale and rollback strategies.
- A single source of truth for Java, wrapper, plugins, and BOM/lockfile per repo.

Version locking makes **changes easier to control**, not an excuse to delay security fixes.

## 16. CI/CD: Verify Versions Rather Than Trusting READMEs

### 16.1. Maven Workflow

A CI-provider-neutral pipeline might include these shell steps:

~~~bash
java -version
./mvnw -version
./mvnw -B -ntp clean verify
jar tf target/version-lock-maven-1.0.0.jar
sha256sum target/version-lock-maven-1.0.0.jar
~~~

CI should provision JDK 17 per policy (when Enforcer enforces `[17,18)`) **before** invoking the wrapper. Maven Wrapper only selects the Maven version; it does not install or select Maven's Java runtime.

### 16.2. Gradle Workflow

~~~bash
java -version
./gradlew --version
./gradlew -q javaToolchains
./gradlew --no-daemon clean test bootJar
jar tf build/libs/version-lock-gradle-1.0.0.jar
sha256sum build/libs/version-lock-gradle-1.0.0.jar
~~~

CI must have an appropriate Java toolchain or configured toolchain download repositories. Never add `--write-locks`, because verification jobs **must not update reviewed dependency state**. If the lock fails, the build should fail and maintainers should open a PR to update locks.

### 16.3. When Using Container Images

An example policy:

~~~text
Source commit:
    fixed Git revision

Build command:
    ./mvnw -B -ntp clean verify
    or ./gradlew --no-daemon clean build

Build image:
    pinned by immutable digest

JDK:
    Java 17 vendor + patch stated in image manifest

Artifacts:
    published with SHA-256 and build provenance
~~~

This is a **policy description**, not a standalone runnable Dockerfile or CI config. Never place a fake container digest in documentation; obtain the digest from the real image after your organization selects and verifies its source.

## 17. Troubleshooting: Why Do Locked Builds Still Differ?

| Symptom | Common cause | Check / resolution |
| --- | --- | --- |
| Local Maven 3.9.x, CI Maven 3.8.x | CI invokes `mvn` instead of `./mvnw` | Run `./mvnw -version` in both; fix pipeline |
| Maven wrapper downloads unexpected Maven version | Wrong `distributionUrl` or uncommitted wrapper properties | Review `.mvn/wrapper`, verify version/SHA |
| Gradle wrapper reports 8.14.3 but CI runs Gradle 9 | CI calls system `gradle` | Switch to `./gradlew`, print `--version` |
| Plugin upgrades automatically while dependency BOM stays unchanged | Dynamic/unmanaged plugin version | Pin plugin in `plugins`/`pluginManagement`, inspect effective config |
| Java compile passes locally, fails CI `invalid target release: 17` | Compiler JDK lacks release 17 | Print Java/Javac versions; use JDK 17+ or proper toolchain |
| Artifact throws `UnsupportedClassVersionError` | Runtime Java older than classfile or dependency compiled with newer Java | Check runtime JDK, `--release`, and dependency requirements |
| Maven Enforcer Java rule fails under JDK 21 | Policy requires `[17,18)` | Provision JDK 17 to build or update policy with review |
| Maven Spring Boot BOM locked, yet transitives changed | Dependency outside BOM, range, mutable repo, graph shift | `dependency:tree`, effective POM, pin offending deps |
| Gradle reports dependency lock out of date | POM/BOM/dependency changed without updating lockfile | Review change; run `--write-locks` in PR, never silently in CI |
| Gradle lockfile missing | Forgot `--write-locks` or configuration unresolved | Run `dependencies --write-locks` and test/bootJar; verify generated file |
| Multi-project has root lockfile, app not locked | Root `dependencies` did not resolve subprojects | Resolve `:app:dependencies`/relevant tasks, commit per-module lockfiles |
| Boot Gradle plugin pinned, starter lacks version | Missing Boot BOM via platform/dependency management | Add `platform(...)`/appropriate plugin and check `dependencyInsight` |
| Build uses `-SNAPSHOT` with differing bytes for same GAV | Snapshot/changing dependency republished | Use immutable releases, verification, and versioned artifacts |
| Wrapper SHA fails | Mismatched checksum/version/URL or tampered bytes | Verify against official source; never disable integrity checks |
| JAR hash differs while dependency graph matches | ZIP timestamps, file ordering, generated build-info, JDK patch | Enable reproducible archive options, check generated files |
| Offline repo passes, CI clean fails | Local cache masked missing dependencies/repos or stale metadata | Check repository access/credentials, use clean runner with trusted sources |
| Maven root and child use different Boot versions | Mismatched parent/BOM/plugin versions or child override | `help:effective-pom`, centralized management, tests |
| Gradle `--refresh-dependencies` changes the build | Repository metadata changed, dynamic/changing modules | Fix versions, lock and verify artifacts, do not rely on cache |
| Same artifact filename has different contents | Build output overwritten without bumping version | Immutable artifact repositories, SHA/provenance, fail on overwrite |
| After updating Java major, tests behave differently | JDK runtime/locale/time zone/crypto providers differ | Run tests on target runtime, lock environment, document release notes |

### 17.1. Six Diagnostic Questions in Order

**1. Is the source truly the exact same commit?** Check Git commit and working tree, submodules, and generated source inputs.

**2. Is the build tool using the right wrapper?** Run `./mvnw -version`/`./gradlew --version` instead of just `mvn -version` or reading the README.

**3. Are the Java compiler/runtime correct?** Compare `java -version`, `javac -version`, Maven Enforcer/Toolchains, and Gradle Toolchains.

**4. Are plugin versions fixed?** Read effective POM, Gradle plugins/settings/build-logic; inspect annotation processors and test plugins.

**5. Do dependency graphs/bytes match?** Check Maven tree/Gradle lockfile, resolved versions, repositories, and artifact verification.

**6. Where does the output differ?** If the build passes yet hashes differ, inspect the archive for timestamps, file ordering, and generated content; do not assume version management caused it.

## 18. Practice Exercises with Guided Answers

**Exercise 1 — Wrapper vs System Maven.** Local machine has Maven 3.9.16; CI has a different system Maven version. Which command ensures the project uses the Maven Wrapper version?  
**Answer:** `./mvnw clean verify` or `.\mvnw.cmd clean verify`; you must commit the Wrapper and chosen distribution config, then check `./mvnw -version`.

**Exercise 2 — Java --release.** Maven runs on JDK 21 with `maven.compiler.release=17`. Does this mean the app is guaranteed to run under JDK 17 in production?  
**Answer:** No. The compiler targets 17, while the production Java runtime is a separate deployment setting. Furthermore, the example's Enforcer requires Maven to run on Java 17, so Maven on Java 21 will be rejected by policy.

**Exercise 3 — BOM vs Dependency.** Parent imports `spring-boot-dependencies:3.5.16`, but child does not declare `spring-boot-starter`. Will the starter be present at runtime?  
**Answer:** No. A BOM supplies managed versions; the child still has to declare the dependencies it uses.

**Exercise 4 — Does Maven Have gradle.lockfile?** A Maven 3 project imports the BOM and wants to lock all transitive GAVs. Is there a native `mvn --write-locks` command equivalent to Gradle?  
**Answer:** No. Maven 3 lacks a built-in dependency lockfile mechanism like Gradle's. Use pinned versions/BOM/Enforcer, archive the tree/SBOM, and adopt auxiliary tools where needed.

**Exercise 5 — Gradle Version Locking.** You added `dependencyLocking { lockAllConfigurations() }` but see no `gradle.lockfile`. What step is missing?  
**Answer:** Resolve configurations via appropriate tasks with `--write-locks`, inspect generated lockfiles, and commit; merely adding the DSL block is not enough.

**Exercise 6 — Unlocked Plugin.** `gradle.lockfile` contains all Spring library versions, while Spring Boot Gradle Plugin uses a dynamic version. Is this safe?  
**Answer:** No. Plugin resolution/implementation classpath needs an explicit version; application dependency locking does not pin the Boot plugin.

**Exercise 7 — SNAPSHOT.** Two builds have the same `com.example:client:1.0-SNAPSHOT` yet differing bytes. Is the lockfile enough to declare reproducibility?  
**Answer:** No. Coordinates do not guarantee artifact immutability; you need release versions/digest verification/repository policies.

**Exercise 8 — Different Hashes.** Maven/Gradle dependency versions match, yet JAR hashes differ. What should you inspect first?  
**Answer:** Verify identical source/recipe/toolchains, timestamps/ZIP file ordering, generated resources, Git metadata, and environment; then compare archive entries. Do not blame dependencies for everything.

**Exercise 9 — Security Updates.** A pinned library has a CVE. Should you keep it pinned forever because of the lockfile?  
**Answer:** No. Upgrade in a controlled manner, update lock/BOM, run security scans/regression tests, and review the diff.

**Exercise 10 — Multi-Module Gradle.** Root has a `gradle.lockfile`, and subproject `:service` resolves its own dependencies. Are all subprojects guaranteed locked?  
**Answer:** No. Locking is per project/configuration; inspect lock state for every subproject and resolve the configurations actually used.

## 19. Build-Locking Checklist

- [ ] Source revision, build scripts, and generated inputs are controlled in Git.
- [ ] JDK compiler/runtime are explicitly selected; Java language/API target set via `--release` where appropriate.
- [ ] Maven/Gradle Wrapper is fully committed and CI **actually executes via the wrapper**.
- [ ] Wrapper distribution URL/version is pinned and SHA-256 verified against official release sources.
- [ ] Spring Boot build plugin and other plugins have explicit versions, not dynamic releases.
- [ ] Spring Boot parent/BOM version is explicit; dependencies outside the BOM are managed explicitly.
- [ ] Gradle dependency locking is enabled, `gradle.lockfile` generated for the right configurations/projects and committed.
- [ ] For Maven, team understands BOM/dependencyManagement is not equivalent to an auto-generated dependency lockfile.
- [ ] No version ranges/dynamic/SNAPSHOT outside approved release policies.
- [ ] Dependency repositories disallow overwriting immutable releases; checksums/signatures/provenance checked as needed.
- [ ] Reproducible build archive options considered; generated files do not embed uncontrolled mutable data.
- [ ] CI prints tool versions, checks dependency graphs, runs tests, and records artifact SHA-256/release metadata.
- [ ] Controlled PR review and rollback process exists for upgrading Java/Wrapper/plugins/BOM/dependency locks.
- [ ] No secrets stored in `pom.xml`, `gradle.properties`, wrapper properties, or logs.

## 20. Official Documentation

- Spring Boot 3.5 — System Requirements (Java/Maven/Gradle): https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Apache Maven — Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven — Maven Wrapper Plugin Usage: https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html
- Apache Maven — Compiler Plugin / --release: https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- Apache Maven — Toolchains Plugin: https://maven.apache.org/plugins/maven-toolchains-plugin/
- Apache Maven — Enforcer RequireJavaVersion: https://maven.apache.org/enforcer/enforcer-rules/requireJavaVersion.html
- Apache Maven — Enforcer RequireMavenVersion: https://maven.apache.org/enforcer/enforcer-rules/requireMavenVersion.html
- Apache Maven — Reproducible Builds: https://maven.apache.org/guides/mini/guide-reproducible-builds.html
- Gradle — Wrapper and Checksum Verification: https://docs.gradle.org/8.14.3/userguide/gradle_wrapper.html
- Gradle — Java Toolchains: https://docs.gradle.org/8.14.3/userguide/toolchains.html
- Gradle — Dependency Locking: https://docs.gradle.org/8.14.3/userguide/dependency_locking.html
- Gradle — Managing Dependencies/Platforms: https://docs.gradle.org/8.14.3/userguide/platforms.html
- Gradle — Dependency Verification: https://docs.gradle.org/8.14.3/userguide/dependency_verification.html
- Gradle — Reproducible Archives: https://docs.gradle.org/8.14.3/userguide/working_with_files.html#sec:reproducible_archives

**Summary:** Locking **Java**, **Wrapper**, **plugins**, and **dependencies** is a system, not a single number. Maven relies on parent/BOM, plugin versions, Wrapper, and policy checks; Gradle adds `gradle.lockfile` for resolved dependencies. For genuinely reproducible builds, lock and verify artifact sources, toolchains, environments, and archive contents; after every reviewed update, re-run tests and inspect outputs rather than trusting the feeling that “it built fine yesterday.”
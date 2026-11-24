# Configuring Java Toolchains in Maven and Gradle

## 1. What Problem Do Java Toolchains Solve?

When developing Spring Boot applications, a single computer may have both JDK 17 and JDK 21 installed. Running **java -version** in a terminal might show Java 21; the IDE might use JDK 17; CI might use another JDK. Without explicit build configuration, code may compile on one machine yet fail on another, or accidentally call APIs too new for the real runtime environment.

A **Java Toolchain** is the mechanism by which a build tool selects a Java toolset matching the project's requirements—for example, **javac 17** for compilation, JDK 17 for running tests, and `javadoc` for generating documentation. A toolchain typically consists of tools drawn from a single JDK installation. The goal is to make the JDK requirement explicit for **toolchain-aware build tasks**.

In Spring Boot, four concepts must be distinguished:

| Concept | Meaning | Example |
| --- | --- | --- |
| **JDK running the build tool** | The JVM that launches the Maven or Gradle daemon process and runs build-tool logic/plugins. | Maven starts on JDK 21. |
| **Toolchain JDK** | The JDK selected for supporting tasks/plugins, such as compiling Java or running tests. | Maven Compiler Plugin uses javac 17. |
| **Output compatibility level** | The syntax, API, and bytecode version targeted by the application. | Java 17, bytecode major version 61. |
| **JVM running the deployed app** | The actual `java` command running the JAR after the build, on a server, container, or user machine. | Compatible Java 17 or Java 21 runtime. |

**A toolchain does not change `JAVA_HOME`, does not replace the JDK running Maven/Gradle, and does not automatically switch the JVM of an independent `java -jar` invocation.** A task or plugin that does not support toolchains may keep using the build-tool JVM, the JDK from `PATH`, or its own settings.

This lesson uses **Java 17** as the target because Spring Boot 3.x requires Java 17 or higher. The examples are set in the context of **Spring Boot 3.3.5**; that version number is an illustrative sample configuration and does not imply it is the latest Spring Boot release.

## 2. When Should You Configure Toolchains?

- **Multiple JDKs on one machine:** the system default is Java 21, while the project must compile against Java 17.
- **Aligning developer machines and CI:** developers and pipelines both select JDK 17 for Java tasks.
- **Multi-module repositories:** module A needs Java 17, module B needs Java 21; each module declares its requirement.
- **Compiling with a newer JDK for an older runtime:** you can use `javac` 21 with **--release 17** to allow only Java 17 language features, APIs, and bytecode.
- **Investigating environment errors:** identifying whether an error originates from the JVM running Maven/Gradle, the compile JDK, the test-running Java, or the app-running JDK.

Toolchain configuration does not replace verifying **compatibility across Spring Boot, Gradle/Maven, plugins, JDKs, and the deployment environment**. For instance, if a plugin requires JVM 17 just to start, you cannot run it on JVM 11 and expect a toolchain of 17 to fix it.

## 3. Maven: Selecting a JDK with Maven Toolchains Plugin

In Maven, most project configuration lives in **pom.xml**. Toolchains is an additional mechanism: **maven-toolchains-plugin** selects a matching JDK and places it into the build context for **toolchain-aware** plugins to consume. **maven-compiler-plugin** is the primary example.

Starting in Maven Toolchains Plugin **3.2.0**, the **select-jdk-toolchain** goal supports discovering JDKs in common locations and via environment variables. The examples below use plugin version **3.3.0**.

### 3.1. Complete pom.xml Example for a Spring Boot Application

Save this as **pom.xml** at the root of a Maven project. The example requests a JDK from the **17.x** line for toolchain-aware plugins:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>toolchain-maven</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <toolchain.jdk.version>[17,18)</toolchain.jdk.version>
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
                <artifactId>maven-toolchains-plugin</artifactId>
                <version>3.3.0</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>select-jdk-toolchain</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Exact explanation of each part:**

1. **java.version = 17:** states the Java baseline of the Spring Boot Maven parent. Since the project intends to run on Java 17, keep this value at 17.
2. **maven.compiler.release = 17:** instructs `javac` to emit code at Java 17 level, including syntax, standard APIs, and bytecode. With `spring-boot-starter-parent`, this property is typically already linked to `java.version`; writing it explicitly highlights the compatibility target.
3. **toolchain.jdk.version = [17,18):** picks a JDK whose version is at least 17 (inclusive) and below 18. This range is used because an actual JDK might report itself as **17** or **17.0.12**. A single value **17** does not always match **17.0.x** in manual toolchains.
4. **select-jdk-toolchain:** goal that automatically selects a matching JDK from discovered or declared JDKs; bound to Maven's **validate** phase. Running later phases like `compile`, `package`, or `verify` passes through `validate`.
5. **spring-boot-maven-plugin:** handles building and packaging the Boot application; this plugin is not the JDK toolchain selection mechanism itself.

**Note on execution requirements:** Maven and the Spring Boot Maven Plugin must still launch on a compatible JVM. A clear real-world example is Maven running on **JDK 21** while the compiler comes from **JDK 17**. If a machine only has JDK 21 while the configuration requires **[17,18)**, Maven cannot conjure JDK 17 just from `select-jdk-toolchain`; you must install JDK 17 or adjust the requirement to fit the project.

### 3.2. Checking Which JDKs Maven Discovers

From the project directory with Maven Wrapper:

~~~bash
./mvnw -version
./mvnw org.apache.maven.plugins:maven-toolchains-plugin:3.3.0:display-discovered-jdk-toolchains
./mvnw clean verify
~~~

- **-version** prints the Maven version and the JVM **running Maven**, which is not enough to prove the compiler toolchain.
- **display-discovered-jdk-toolchains** lists the JDKs found by the plugin along with metadata; this is a diagnostic command, **not** a goal that sets a toolchain for the whole build.
- **clean verify** executes the required phases and uses the selected toolchain if plugins/tasks support it.
- On Windows, use **mvnw.cmd** instead of **./mvnw**; if there is no wrapper, run **mvn** from the installed Maven.

When troubleshooting toolchain selection, you can run **./mvnw -X compile** to inspect detailed logs. Do not infer the compiler JDK solely from **java -version** or **./mvnw -version**.

### 3.3. Alternative Option: Manual toolchains.xml

When JDKs live in non-discovered paths, or an organization wants to pin a fixed path on a build agent, Maven supports the personal configuration file **~/.m2/toolchains.xml**. This file resides in the Maven user home; the exact path depends on the OS. Example for a Linux machine with JDK 17 at **/opt/jdks/jdk-17**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<toolchains>
    <toolchain>
        <type>jdk</type>
        <provides>
            <version>17</version>
            <vendor>temurin</vendor>
        </provides>
        <configuration>
            <jdkHome>/opt/jdks/jdk-17</jdkHome>
        </configuration>
    </toolchain>
</toolchains>
~~~

**Replace `jdkHome` with the real JDK installation path**. The file above describes available JDKs; to use the legacy **toolchains:toolchain** mechanism, configure the plugin in `pom.xml` with the **replacement snippet** below. The following snippet is **not a complete pom.xml** and is used **in place of** the `maven-toolchains-plugin` block with `select-jdk-toolchain` in Section 3.1:

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
                <version>[17,18)</version>
            </jdk>
        </toolchains>
    </configuration>
</plugin>
~~~

**Selection mechanism:** Maven finds a **jdk**-type entry with a matching version and supplies that toolchain to supporting plugins. Metadata such as **vendor** in `toolchains.xml` is a matching string, not proof that Maven verified the JDK genuinely came from that vendor. Make sure `jdkHome` points to a real JDK containing **bin/javac**. Having `toolchains.xml` does not mean Maven automatically uses a toolchain in every build unless a goal or plugin requests it.

**Do not put personal machine JDK paths into a shared pom.xml.** Each machine/CI environment declares its own JDKs; the POM only expresses version constraints. The newer discovery mechanism is more convenient when JDKs are auto-detected; manual configuration fits environments where automatic discovery is difficult.

## 4. Gradle: Java Toolchains in build.gradle

Gradle Java Toolchains is a built-in capability of the Java plugins. With Gradle Groovy DSL, a project typically has two files:

- **settings.gradle**: root project name, subprojects, and optional JDK resolver configuration when needed.
- **build.gradle**: JDK requirements and Java task configuration for each project.

In the examples below, use **Gradle Wrapper 8.5** or a newer version that supports the corresponding Java and Spring Boot plugins. Gradle 8.5 supports running Gradle on Java 21 and using Java 21 via toolchains; for Java 17, it is also a suitable baseline.

### 4.1. Simple settings.gradle

~~~groovy
rootProject.name = 'toolchain-gradle'
~~~

This is the entire `settings.gradle` needed for a single-module project when JDK 17 is already installed and recognized by Gradle. No download resolver is needed when JDK 17 is already present.

### 4.2. Complete build.gradle for Spring Boot

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **complete Groovy DSL `build.gradle`** for the demo project. For **build.gradle.kts** (Kotlin DSL), plugin, dependency, and task syntax must be rewritten in Kotlin style; do not just rename the file extension and leave Groovy syntax.

**Distinguishing the two Java settings:**

- **java.toolchain.languageVersion = 17:** Gradle locates JDK 17 and provides its tools to supported Java tasks such as **JavaCompile**, **Test**, and **Javadoc** created by the Java plugin.
- **options.release = 17:** the compiler may only use Java 17 language features and APIs and produces Java 17-compatible class files. This safeguards the Java 17 runtime target even if one day the project intentionally switches its toolchain to JDK 21.

Setting **sourceCompatibility = 17** or **targetCompatibility = 17** does not guarantee code won't use APIs that exist only in Java 21. With newer `javac`, `-source`/`-target` pairs do **not** restrict the entire standard API the way **--release** does.

### 4.3. Checking Which JVM and JDK Gradle Uses

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean build
./gradlew compileJava --info
~~~

- **--version** reports Gradle and the JVM/daemon Gradle uses; it is not sole proof of the JDK used by `compileJava`.
- **javaToolchains** lists the JDKs Gradle detected along with their details.
- **build** compiles, runs tests, and builds artifacts per the task graph; the Spring Boot plugin provides the **bootJar** task.
- **compileJava --info** is helpful for seeing the selected JDK/toolchain, compiler, and why the task executed or was skipped.

On Windows, replace **./gradlew** with **gradlew.bat**. The Gradle Wrapper locks the project's Gradle version; **the wrapper does not lock or pre-install a JDK**.

### 4.4. When a Machine Lacks JDK 17: Auto-Provisioning

Gradle can **automatically download a matching JDK when needed**, provided a **toolchain download repository/resolver** is configured. For a project using Gradle 8.5, for example, you can use the Foojay resolver convention plugin **0.8.0** in **settings.gradle**:

~~~groovy
plugins {
    id 'org.gradle.toolchains.foojay-resolver-convention' version '0.8.0'
}

rootProject.name = 'toolchain-gradle'
~~~

This is the **complete `settings.gradle` replacing** the simple one in Section 4.1; `build.gradle` from Section 4.2 stays unchanged. The Foojay plugin is a **settings plugin**, not placed in `build.gradle` like an application plugin. When no matching JDK is found locally, Gradle can download a matching JDK from the configured resolver, subject to network access and environment policies. Auto-downloading a JDK **does not mean** Gradle switches the JVM currently running the Gradle daemon.

If CI blocks downloading JDKs from the internet, **pre-install JDK 17** and ensure Gradle detects it. Do not rely on auto-provisioning working offline.

### 4.5. When Gradle Does Not Auto-Detect an Installed JDK

Check **./gradlew -q javaToolchains** first. Gradle supports properties such as **org.gradle.java.installations.paths** to list JDK paths outside standard auto-discovery locations. Example for a Linux machine, placed in an environment or project **gradle.properties** when the paths genuinely apply to all build machines:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

Paths are illustrative; do not copy verbatim if your real JDKs live elsewhere. Avoid committing machine-specific paths into shared team config. You can place this option inside **~/.gradle/gradle.properties** on a specific machine.

If you change JDK locations yet the daemon retains stale detection results, run **./gradlew --stop** and re-run. There is no need to edit build scripts when only local installation paths differ.

## 5. Practice: Same Java Class Compiled with Both Tools

We use a plain Java class to directly observe the effect of Java Toolchains. This class is valid on Java 17+ with no framework dependencies:

**src/main/java/com/example/demo/ToolchainDemo.java**

~~~java
package com.example.demo;

public class ToolchainDemo {
    public static void main(String[] args) {
        System.out.println("Toolchain demo OK");
    }
}
~~~

The Java file above is a **complete program** whose package and class match its path. Place it in the Maven project from Section 3.1 **or** the Gradle project from Section 4.2.

**With Maven**, compile using the wrapper and run the class from the project directory:

~~~bash
./mvnw clean compile
java -cp target/classes com.example.demo.ToolchainDemo
~~~

**With Gradle**, run:

~~~bash
./gradlew clean classes
java -cp build/classes/java/main com.example.demo.ToolchainDemo
~~~

When the JVM of the final **java** command is Java 17 or higher, both examples print **one exact stdout line from the program**:

~~~text
Toolchain demo OK
~~~

Maven/Gradle logs may appear from the preceding build commands and are not counted as `ToolchainDemo`'s stdout.

**Why does the `java` command still need attention?** `java -cp ...` is resolved by the shell via `PATH`/`JAVA_HOME` and is **not automatically controlled by Maven or Gradle toolchains**. Therefore, a class can compile cleanly for Java 17 and still fail with **UnsupportedClassVersionError** if someone tries to run it with Java 11.

### 5.1. Verifying the Class File Compiled to the Right Target

After compiling, use **javap** from a sufficiently new JDK to inspect the class file metadata:

~~~bash
javap -verbose target/classes/com/example/demo/ToolchainDemo.class
~~~

With Gradle, change the path to:

~~~bash
javap -verbose build/classes/java/main/com/example/demo/ToolchainDemo.class
~~~

In the long output, find the line:

~~~text
major version: 61
~~~

**61** is the class file major version for **Java 17** (Java 21 is **65**). This checks the bytecode level; it **does not definitively prove which compiler ran**, nor does it prove all plugins/tests used the same JDK. To confirm the compiler JDK, inspect Maven's toolchain logs or **compileJava --info** in Gradle.

### 5.2. Scenario: JDK 21 Compiling Java 17 Bytecode

Suppose a build server has JDK 21 installed and wants to use the 21 compiler while still targeting a Java 17 runtime:

- **Maven:** change the toolchain selection constraint to **[21,22)**, while **keeping `maven.compiler.release = 17`** and `java.version` aligned with the app's runtime level.
- **Gradle:** change **JavaLanguageVersion.of(17)** to **JavaLanguageVersion.of(21)**, while **keeping `options.release = 17`**.

`javac` 21 with **--release 17** emits Java 17 bytecode and blocks project code from calling standard APIs added after Java 17. This example proves that the **toolchain JDK** and the **release level** are two separate decisions. The reverse is invalid: **`javac` 17 cannot perform `--release 21`**.

To keep things simple and avoid surprises, a Spring Boot project running on Java 17 can generally use **toolchain 17 + release 17** as the primary setup shown in this lesson.

## 6. Maven/Gradle: Similarities and Differences in Selecting a JDK

| Question | Maven Toolchains | Gradle Java Toolchains |
| --- | --- | --- |
| Which file declares the JDK requirement? | **pom.xml**, via `maven-toolchains-plugin` or a plugin's own `jdkToolchain`. | **build.gradle**, via `java.toolchain` or task configuration. |
| Where are JDKs found? | Maven Toolchains Plugin 3.2.0+ supports discovery; traditional method uses **~/.m2/toolchains.xml**. | Gradle discovers recognized JDK installs; can configure paths and a download resolver. |
| Automatically downloads missing JDKs? | Maven Toolchains Plugin's discovery goal **does not install new JDKs**. | **Yes, optionally**, if a toolchain download repository is configured and the environment permits. |
| Must replace the build-tool JVM? | **No**; Maven's JVM is a separate choice. | **No**; Gradle daemon JVM differs from the task toolchain. |
| Compile/test automatically use the toolchain? | Depends on whether the plugin is **toolchain-aware**. | Java plugin covers standard Java tasks; other tasks/plugins need checking. |
| Block APIs newer than target runtime? | **maven.compiler.release** for `javac`. | **options.release** for `JavaCompile`. |
| List discovered JDKs? | Goal **display-discovered-jdk-toolchains**. | Task **javaToolchains**. |

For tests with custom setups, **do not conclude** tests are running on JDK 17 solely because the compiler uses JDK 17. In Maven, Surefire/Failsafe and plugins may support toolchains or their own **jdkToolchain** depending on version and settings. In Gradle, the Java plugin's **Test** task normally gets its launcher from the toolchain configuration; if a custom task spawns Java itself, you must wire the launcher explicitly.

## 7. Toolchains vs. sourceCompatibility, targetCompatibility, --release, and JAVA_HOME

This is the most confusing area when moving a project from JDK 17 to JDK 21.

| Setting | Selects JDK Install? | Restricts Syntax/Bytecode? | Restricts Standard Java APIs by Version? |
| --- | --- | --- | --- |
| **Toolchain JDK 17** | Yes, for supporting tasks/plugins. | The default compiler from JDK 17 cannot emit Java 21 classes. | Does not by itself enforce a target runtime older than the selected JDK. |
| **--release 17** | No. | Yes. | Yes, per Java 17 standard APIs. |
| **-source 17 / -target 17** | No. | Yes, at the respective syntax/bytecode level. | Not guaranteed when compiling with a newer JDK. |
| **JAVA_HOME** | Can determine the default JVM for Maven/Gradle and shell. | Not a standardized per-project build requirement setting. | No. |

**Real-world bug example:** code uses an API introduced in Java 21 while intending to run on Java 17. On JDK 21, a configuration setting only **-source 17 -target 17** can still compile that new API call and then crash at runtime on Java 17. **--release 17** catches the error at compile time.

For Maven, standard configuration targeting Java 17 is:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

This is a **snippet inside `pom.xml`**, not a standalone file. For Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

This Gradle snippet is also **a fragment** of `build.gradle`. Both release settings must be supported by the compiler JDK. **--release** alone does not select a JDK; a **toolchain** alone does not replace committing to the application's target runtime level.

## 8. Using Toolchains in Multi-Module Spring Boot Projects

In Gradle multi-project builds, **settings.gradle** defines the modules:

~~~groovy
rootProject.name = 'learning-system'
include 'api', 'core'
~~~

Example **core/build.gradle** using Java 17:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

For **api/build.gradle** to use Spring Boot and depend on `core`, `api`'s `build.gradle` must declare its plugins, dependencies, and matching toolchain. A dependency between the two subprojects can be written:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

This is a **fragment of `api/build.gradle`**; a real project must include the necessary plugins, repositories, and dependencies as in Section 4.2. **`include`** in `settings.gradle` only registers modules in the build; it does not wire dependencies between them.

Multi-module Maven builds typically place **maven-toolchains-plugin** in the parent POM according to proper inheritance rules. However, **pluginManagement** only manages configuration/plugin versions—not every plugin declared there runs automatically; ensure the goal is activated as intended. When modules have different Java baselines, verify each module's toolchain requirement and compatibility whenever one module consumes classes from another.

**Critical scenario:** if `core` is built with Java 21 bytecode, `api` or a runtime running Java 17 cannot read `core`'s classes. A toolchain on `api` alone cannot fix bytecode incompatibility already baked into a dependency artifact.

## 9. CI, IDE, and Deployment: Maintaining Consistency

### 9.1. Suggested CI Workflow

1. **Choose the target Java runtime**, e.g., Java 17 for Spring Boot 3.x apps; encode that target in the build configuration.
2. **Install the matching JDK** on CI; if using Maven discovery or Gradle local toolchains, ensure JDK 17 resides in a discoverable location.
3. **Use Maven Wrapper/Gradle Wrapper** from the repository to lock the build tool version. Wrappers lock Maven/Gradle; **they do not replace Java toolchains**.
4. **Verify the build tool's JVM** using **./mvnw -version** or **./gradlew --version**; inspect selectable JDKs via toolchain listing commands.
5. **Run the full build**: **./mvnw clean verify** or **./gradlew clean build**; inspect the actual compiler/test launcher used when diagnosing issues.
6. **Verify the artifact and runtime environment**: an executable Spring Boot JAR still requires an appropriate Java runtime. Running **java -jar ...** in production uses the container/server's JVM, not the laptop's toolchain JDK.

A container image with Java 17 can run a JAR compiled with **--release 17** and compatible dependencies even if CI used JDK 21 to build it. Still, you must check **third-party libraries**, native code, and other runtime requirements, not just the application class major version.

### 9.2. IDE and Terminal Can Use Different JDKs

IntelliJ IDEA/Eclipse/VS Code have separate settings for **Project SDK**, **Gradle JVM**, **Maven runner JDK**, and language level. When the IDE shows red errors while the command-line build succeeds (or vice versa), check the IDE's build-runner JVM setting and the project's toolchain requirement. Setting **Project SDK 21** does not guarantee Gradle will compile with JDK 21 if `build.gradle` requests toolchain 17.

### 9.3. Do Not Commit Personal System Paths to Shared Source Code

- Maven should keep version requirements in `pom.xml`; machine-specific JDK paths go in **~/.m2/toolchains.xml** when using the manual method.
- Gradle should keep version requirements in `build.gradle`; machine-specific installation paths can live in **~/.gradle/gradle.properties** when machines differ.
- When CI must install a JDK automatically, configure provisioning steps in the pipeline rather than assuming a hardcoded Windows/Linux path across all machines.
- If network policy blocks external downloads, install and manage JDKs centrally; do not expect the Gradle resolver to bypass network restrictions.

## 10. Common Troubleshooting Issues and Fixes

**1. Maven reports it cannot find a JDK 17 toolchain.** Check that JDK 17 is installed, run **display-discovered-jdk-toolchains**, check environment variables, and verify the version spec. If `toolchains.xml` lists **17.0.12** while the POM requires the bare string **17**, switch the constraint to **[17,18)**. For manual config, verify **jdkHome** actually points to a valid JDK folder.

**2. `mvn -version` shows Java 21 even though the POM requires Java 17.** This is not necessarily an error. **mvn -version** shows the Java **running Maven**, while toolchain 17 is selected for supporting plugins. Inspect toolchain selection and compiler logs instead of blindly changing `JAVA_HOME`.

**3. Maven runs on Java that is too old and crashes loading the Spring Boot plugin.** Toolchains do not change the JVM running Maven itself. Upgrade or select a JVM for running Maven that is compatible with Spring Boot and its plugins, then let Maven Toolchains manage the compile JDK.

**4. Gradle reports no matching Java installation found.** Run **./gradlew -q javaToolchains**, install the right JDK version, or configure a resolver (if the environment permits downloads). Check **org.gradle.java.installations.paths**; after changes you can stop the daemon with **./gradlew --stop**.

**5. Gradle still runs its daemon on JDK 21.** **java.toolchain.languageVersion = 17** selects the JDK for supported tasks; it does not change the JVM that launched the Gradle daemon. If your Gradle/plugin version cannot run on the current daemon JVM, change the JVM launching Gradle or upgrade Gradle to a compatible version.

**6. Java 21 APIs slip into an app meant for Java 17.** Set **maven.compiler.release = 17** (Maven) or **options.release = 17** (Gradle). Do not rely only on **targetCompatibility**.

**7. `java -jar` after the build throws `UnsupportedClassVersionError`.** Check the actual Java runtime running the app and the artifact's class level. A Java 21 class (major 65) will not run on JVM 17 (which accepts up to major 61). Adjust the build target and dependencies or upgrade the runtime per project policy.

**8. Tests or custom tasks still use a different JDK than the compiler.** Check whether the plugin supports toolchains. Maven Surefire/Failsafe can choose a separate JDK depending on version; Gradle **Test/JavaExec** tasks have **javaLauncher** to configure the JDK explicitly if needed. Toolchains do not automatically apply to every script or subprocess.

**9. Cannot auto-download JDKs on Gradle CI.** Auto-provisioning requires a resolver and network connectivity. If network access is restricted or no resolver is configured, pre-install the JDK and declare its location instead of only adding `languageVersion`.

**10. `settings.gradle` has a resolver yet fails on an older Gradle version.** Check compatibility across **Gradle Wrapper**, the Foojay plugin version, and the JVM running Gradle. The resolver plugin in Section 4.4 targets the Gradle 8.5 context; projects on another version must pick a compatible resolver version.

## 11. Self-Verification Checklist

- [ ] Target runtime identified: Java 17 or Java 21?
- [ ] Know which build tool is in use: Maven or Gradle?
- [ ] Checked that the **JVM running Maven/Gradle** fits the Spring Boot plugin and Gradle/Maven version?
- [ ] Configured the **JDK toolchain** in the right place: `pom.xml` or `build.gradle`?
- [ ] Selected **--release** matching the target runtime, not just source/target?
- [ ] Checked discovered JDKs and logs confirming the compiler?
- [ ] Checked test tasks and custom tasks where they might use a different JDK?
- [ ] Compiled and test-run, checking the class **major version** if needed?
- [ ] Confirmed CI and production actually have a compatible Java runtime?

## 12. Official Reference Documentation

- Apache Maven — Guide to Using Toolchains: https://maven.apache.org/guides/mini/guide-using-toolchains
- Apache Maven Toolchains Plugin — JDK Discovery: https://maven.apache.org/plugins/maven-toolchains-plugin/toolchains/jdk-discovery.html
- Apache Maven Toolchains Plugin — select-jdk-toolchain: https://maven.apache.org/plugins/maven-toolchains-plugin/select-jdk-toolchain-mojo.html
- Gradle — Java Toolchains for JVM projects: https://docs.gradle.org/current/userguide/toolchains.html
- Gradle — Building Java & JVM projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Gradle 8.5 Release Notes: https://docs.gradle.org/8.5/release-notes.html

**Conclusion:** **Which JDK builds** (toolchain), **which Java level may appear in the artifact** (`--release`), **which JVM runs the build tool**, and **which JVM runs Spring Boot in production** are four related yet distinct choices. Configuring each layer clearly, combined with wrappers and real verification, prevents JDK drift across IDEs, developer laptops, and CI.

# Building the Same Application with Maven and Gradle and Comparing the Artifacts

## 1. Practice Objectives

A Spring Boot application can be built with either **Maven** or **Gradle**. Both can compile Java code, run tests, resolve dependencies, and create an executable JAR to launch with **java -jar**.

This lab uses a **single set of source code** and creates two build configurations for the same application. We will:

1. Lock the same Java, Spring Boot, and dependencies versions.
2. Create Maven POM and Gradle Kotlin DSL configurations.
3. Build, test, and package the application using each tool.
4. Compare the dependency graph, filenames, output directories, manifest, and JAR contents.
5. Run both artifacts and verify the same HTTP response.
6. Compare file sizes, checksums, reproducibility, and build times.
7. Draw meaningful differences when choosing a tool for a project.

**Do not aim for both JARs to have identical SHA-256 digests.** Maven and Gradle use their own plugins, processing order, metadata, and packaging approaches. Two artifacts can differ in bytes while still having the same application, the same dependency set, and the same runtime behavior. We need to inspect each layer of the artifact properly.

## 2. Version Matrix and Comparison Conditions

Use a set of versions supported by Spring Boot 3.5.16:

| Component | Version used in this lab | Reason |
| --- | --- | --- |
| Java | 17 | Spring Boot 3.5.16 requires Java 17 or later |
| Spring Boot | 3.5.16 | Same dependency management and loader |
| Maven Wrapper | 3.9.9 | Higher than the minimum Maven 3.6.3 |
| Gradle Wrapper | 8.14.3 | In the Gradle 8.x branch, meeting the 8.4 or later requirement |
| Gradle DSL | Kotlin DSL | Configured in build.gradle.kts |
| Packaging | Executable JAR | Both artifacts run with java -jar |
| Application | Spring MVC | Same endpoint and test |

Spring Boot 3.5.16 supports Maven 3.6.3 or later and Gradle 7.6.4 or later in the 7.x branch or 8.4 or later in the 8.x branch. Check the exact versions before running; do not rely on a globally installed Maven/Gradle if the project already has a Wrapper.

For a fair comparison, keep the following factors identical:

- Same source files and resources.
- Same Java major version; even better, same JDK vendor and patch release.
- Same Spring Boot version and same dependency versions.
- Same profile, environment variables, and application arguments.
- Same repository, network, and cache state when measuring build time.
- Same test suite and build success criteria.
- Same artifact type: executable JAR versus executable JAR.

If Maven uses Spring Boot 3.5.16 while Gradle uses 3.4.x, or one side adds a different dependency, the comparison no longer isolates the effect of the build tool.

## 3. Shared Project Structure

Place both build files in the same root directory. The source code exists only once:

~~~text
build-compare/
├── pom.xml
├── settings.gradle.kts
├── build.gradle.kts
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       ├── maven-wrapper.properties
│       └── ...
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/com/example/buildcompare/
    │   │   ├── BuildCompareApplication.java
    │   │   └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/buildcompare/
            └── HelloControllerTest.java
~~~

Both Maven and Gradle use the standard layout **src/main/java**, **src/main/resources**, and **src/test/java**. Do not create two separate copies of the source code to avoid one build having newer code than the other.

Generate the Maven Wrapper and Gradle Wrapper with the following commands after installing the respective tools for the first time:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
~~~

Then commit both the Wrapper scripts and Wrapper configuration files to the repository. Anyone cloning the project can build without installing Maven/Gradle globally, provided they have a compatible JDK and permission to download the distribution.

On Windows use **mvnw.cmd** and **gradlew.bat**. On Linux/macOS use **mvnw** and **gradlew**. If the scripts do not have execute permission on Linux/macOS:

~~~bash
chmod +x mvnw gradlew
~~~

Minimal **.gitignore** file:

~~~gitignore
/target/
/build/
/.gradle/
~~~

Keep the Maven/Gradle Wrappers in Git; only ignore outputs and caches generated during the build.

## 4. Creating a Shared Spring Boot Application

The application has a GET **/hello** endpoint that returns a fixed string. Both build tools will compile these exact files.

### 4.1. Main class

File **src/main/java/com/example/buildcompare/BuildCompareApplication.java**:

~~~java
package com.example.buildcompare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildCompareApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildCompareApplication.class, args);
    }
}
~~~

### 4.2. REST controller

File **src/main/java/com/example/buildcompare/HelloController.java**:

~~~java
package com.example.buildcompare;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "build-comparison-ok";
    }
}
~~~

### 4.3. Application properties

File **src/main/resources/application.properties**:

~~~properties
spring.application.name=build-compare
server.port=8080
~~~

### 4.4. Shared test

File **src/test/java/com/example/buildcompare/HelloControllerTest.java**:

~~~java
package com.example.buildcompare;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void helloReturnsExpectedBody() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("build-comparison-ok"));
    }
}
~~~

The test starts the Spring context, calls the controller via MockMvc, and checks the status/body. If one build passes while the other fails, first check test dependencies, JUnit Platform configuration, and the Java version.

## 5. Configuring Maven with pom.xml

File **pom.xml**:

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
    <artifactId>build-compare</artifactId>
    <version>1.0.0</version>
    <name>build-compare</name>
    <description>One Spring Boot application built with Maven and Gradle</description>

    <properties>
        <java.version>17</java.version>
        <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Explanation:

- **spring-boot-starter-parent** provides dependency management and plugin management aligned with Spring Boot 3.5.16.
- **groupId/artifactId/version** identify the Maven project and artifact name.
- **java.version=17** sets the Java version that the Spring Boot parent uses for compiler configuration.
- **spring-boot-starter-web** provides Spring MVC and the embedded web server.
- **spring-boot-starter-test** provides JUnit Jupiter, Spring Test, and MockMvc for the test scope.
- **spring-boot-maven-plugin** creates the executable archive via the repackage goal.

Because the project inherits from **spring-boot-starter-parent**, the **repackage** execution is already configured by the parent. Declaring the plugin is sufficient. Maven runs this goal in the package phase; when invoking **clean verify**, the lifecycle passes through package and creates the executable JAR.

If you do not use the Spring Boot parent, you must declare the plugin version and explicitly configure the repackage execution. Importing the **spring-boot-dependencies** BOM only manages dependency versions; it does not automatically replace the plugin management of the starter parent.

The **project.build.outputTimestamp** property sets a stable timestamp for archive plugins that support it. The date-time value in the example is an illustrative point; a real project should derive a fixed timestamp from release/source metadata and keep it consistent across builds. It does not by itself guarantee that every byte of the artifact is reproducible.

## 6. Configuring Gradle with Kotlin DSL

### 6.1. settings.gradle.kts

~~~kotlin
rootProject.name = "build-compare"
~~~

The project name helps Gradle name the archive with the same artifact name **build-compare**.

### 6.2. build.gradle.kts

~~~kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.api.tasks.testing.Test

plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Explanation:

- **java** adds Java source sets, compile tasks, the test task, and the JAR task.
- **org.springframework.boot** adds the Spring Boot Gradle Plugin and tasks such as bootRun and bootJar.
- **io.spring.dependency-management** lets the Spring Boot plugin automatically import the BOM matching the plugin version, so dependency versions are managed similarly to the Maven parent.
- **java.toolchain** selects JDK 17 for compile/test tasks instead of relying on whatever JAVA_HOME happens to be set on the machine.
- **implementation** declares a dependency needed on the main runtime/compile classpath.
- **testImplementation** is only used for test compile/runtime.
- **useJUnitPlatform()** configures the Gradle test task to run JUnit 5.
- **AbstractArchiveTask** applies stable timestamp and entry ordering settings to archive tasks, including the plain JAR and Boot JAR.

The Spring Boot Gradle Plugin also supports using Gradle's native BOM support via **platform** instead of the dependency-management plugin. The dependency-management plugin is convenient when you want property-based BOM customization; native BOM often has an advantage in configuration/build speed. This lab chooses the dependency-management plugin to stay close to Maven's dependency management experience.

Versions are not declared for the two Spring Boot starters in Gradle because the BOM manages them. The plugin, Wrapper, and Java toolchain versions are still pinned explicitly.

## 7. Building with Maven

From the root directory:

~~~bash
./mvnw --version
./mvnw -B -ntp clean verify
~~~

On Windows:

~~~powershell
.\\mvnw.cmd --version
.\\mvnw.cmd -B -ntp clean verify
~~~

Maven walks through lifecycle phases. In this project, the main steps are:

| Phase | Work performed |
| --- | --- |
| validate | Validates the project structure and required information |
| compile | Compiles the main Java sources |
| test | Runs unit/integration tests in the test phase |
| package | Creates the JAR and runs Spring Boot repackage |
| verify | Runs additional checks bound to the lifecycle |

After succeeding, the default executable artifact is:

~~~text
target/build-compare-1.0.0.jar
~~~

Maven repackage replaces the main JAR with the executable archive. The regular JAR before repackage is renamed to:

~~~text
target/build-compare-1.0.0.jar.original
~~~

The **.jar.original** file is the artifact before Spring Boot adds the loader and nested dependencies. It is not a standalone file runnable with java -jar in this example.

Run the application directly with Maven:

~~~bash
./mvnw spring-boot:run
~~~

The **spring-boot:run** goal runs the application from the project classpath, which is useful for development. When you need to test the release artifact, you must still run the packaged JAR file itself.

## 8. Building with Gradle

From the same root directory:

~~~bash
./gradlew --version
./gradlew clean build
~~~

On Windows:

~~~powershell
.\\gradlew.bat --version
.\\gradlew.bat clean build
~~~

Gradle organizes work as a task graph. With the Java and Spring Boot plugins, the main tasks include:

| Task | Work performed |
| --- | --- |
| compileJava | Compiles the main Java sources |
| processResources | Copies resources |
| classes | Aggregates outputs of the main source set |
| compileTestJava | Compiles the test sources |
| test | Runs tests |
| jar | Creates the plain JAR |
| bootJar | Creates the executable Spring Boot JAR |
| assemble | Aggregates build artifacts |
| check | Runs verification tasks |
| build | Depends on assemble and check |

The **build** task runs tests and packaging. The Spring Boot plugin configures assemble to depend on bootJar, so **clean build** creates the executable archive.

Default executable output:

~~~text
build/libs/build-compare-1.0.0.jar
~~~

Gradle also creates a plain archive:

~~~text
build/libs/build-compare-1.0.0-plain.jar
~~~

The Spring Boot Gradle plugin sets the **plain** classifier on the jar task by default to distinguish it from the executable bootJar. The plain JAR contains the application output in standard Java layout without the Boot loader or nested runtime dependencies; do not use it in place of the executable JAR for deployment.

Run the application directly with Gradle:

~~~bash
./gradlew bootRun
~~~

The **bootRun** task runs the application from Gradle's runtime classpath. When comparing released artifacts, use java -jar on the output of bootJar.

## 9. Comparing Maven and Gradle Configurations

| Item | Maven | Gradle |
| --- | --- | --- |
| Main build file | pom.xml | build.gradle.kts |
| Project/root file | POM coordinates | settings.gradle.kts + group/version |
| Main dependency | dependencies | implementation |
| Test dependency | scope test | testImplementation |
| Dependency management | spring-boot-starter-parent | Spring Boot Gradle plugin + dependency-management BOM |
| Spring Boot plugin | spring-boot-maven-plugin | org.springframework.boot |
| Compile | compile phase | compileJava task |
| Test | test phase | test task |
| Executable JAR | spring-boot:repackage | bootJar task |
| Run app during development | spring-boot:run | bootRun |
| Wrapper | mvnw / mvnw.cmd | gradlew / gradlew.bat |
| Default output | target/ | build/ |

Maven expresses the process through lifecycle phases and plugin goals. Gradle models the process through tasks and task dependencies. Both can be extended with plugins, custom tasks/goals, test reports, code generation, and publishing.

Do not compare a **mvn package** command with a **gradle build** command and draw conclusions about speed. Maven package might not run all the verifications that Gradle build runs. Choose commands with the same scope: compile, test, and create the executable archive.

## 10. Comparing the Dependency Graph

Both build files declare the same Spring Boot 3.5.16, spring-boot-starter-web, spring-boot-starter-test, and Java 17. Maven gets dependency versions from the Spring Boot parent. Gradle gets versions from the BOM that the Spring Boot Gradle plugin imports via the dependency-management plugin.

### 10.1. Inspecting the dependency tree with Maven

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

This command displays runtime dependencies and transitive paths. To inspect test dependencies as well:

~~~bash
./mvnw dependency:tree
~~~

### 10.2. Inspecting the dependency graph with Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

To find out why a specific version was selected:

~~~bash
./gradlew dependencyInsight --dependency spring-web --configuration runtimeClasspath
~~~

### 10.3. Reading the results properly

Compare:
- Same artifact coordinates and versions.
- Same runtime dependencies.
- Same test dependencies.
- No dependency appearing in only one build due to differing declarations.
- No unexpected version overrides.
- No missing optional or runtime-only dependencies.

Maven and Gradle have different conflict resolution rules and graph output formats. If there is a version conflict or override, read the **resolved version** rather than only looking at the version written in the build file. With the Spring Boot BOM, do not arbitrarily override a dependency without evaluating compatibility.

## 11. Comparing Executable JARs

This is the most important part of the lab. We need to be sure we are comparing two executable archives and not accidentally comparing the Maven executable JAR against the Gradle plain JAR.

### 11.1. Checking output files

Linux/macOS:

~~~bash
ls -lh target/build-compare-1.0.0.jar
ls -lh build/libs/build-compare-1.0.0.jar
ls -lh build/libs/build-compare-1.0.0-plain.jar
~~~

Windows PowerShell:

~~~powershell
Get-Item target/build-compare-1.0.0.jar, build/libs/build-compare-1.0.0.jar, build/libs/build-compare-1.0.0-plain.jar |
    Select-Object Name, Length
~~~

Maven's **.jar.original** and Gradle's **-plain.jar** are the two artifacts commonly used to inspect the JAR before Spring Boot builds the executable layout. However, they are produced by two different archive plugins, so they are not byte-for-byte identical by default either.

### 11.2. Listing JAR contents

~~~bash
jar tf target/build-compare-1.0.0.jar
jar tf build/libs/build-compare-1.0.0.jar
~~~

A Spring Boot executable JAR typically contains these sections:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/
BOOT-INF/classes/
BOOT-INF/lib/
BOOT-INF/classpath.idx
BOOT-INF/layers.idx
~~~

Specific metadata names depend on configuration. Key points:

- **BOOT-INF/classes** contains application classes and resources.
- **BOOT-INF/lib** contains runtime dependencies as nested JARs.
- **spring-boot-loader** provides the launcher to read nested JARs.
- **META-INF/MANIFEST.MF** specifies Main-Class and Start-Class.
- **layers.idx** describes layer groups if layered archives are enabled.

If the executable JAR has no nested dependencies or loader, you may be looking at a plain JAR or the build did not run repackage/bootJar properly.

### 11.3. Inspecting the manifest

Use an unzip tool or extract **META-INF/MANIFEST.MF** individually from each archive.

The manifest of an executable Spring Boot JAR typically looks like:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.buildcompare.BuildCompareApplication
Spring-Boot-Version: 3.5.16
~~~

Attribute order and auxiliary fields may differ. Two fields to pay attention to:
- **Main-Class** is the Boot launcher.
- **Start-Class** is the application's main class.

Maven repackage rewrites the manifest and manages Main-Class/Start-Class. Gradle BootJar also automatically finds the main class with public static void main or allows explicit configuration. If the main class cannot be found, declare it explicitly in the plugin/task configuration.

### 11.4. Comparing plain archives

Maven saves the regular version as **.jar.original** when repackage replaces the main artifact. Gradle creates **-plain.jar** via the jar task.

A plain JAR typically contains:

~~~text
com/example/buildcompare/BuildCompareApplication.class
com/example/buildcompare/HelloController.class
application.properties
~~~

It does not have a BOOT-INF/lib structure containing all dependencies and does not have the Boot launcher. Do not run the plain JAR with java -jar to evaluate executable packaging.

## 12. Checking Size and Checksum

File size indicates total storage size, but does not explain what is inside the file. Combine size, dependency list, and archive entries.

Linux/macOS:

~~~bash
du -h target/build-compare-1.0.0.jar
du -h build/libs/build-compare-1.0.0.jar
sha256sum target/build-compare-1.0.0.jar
sha256sum build/libs/build-compare-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash target/build-compare-1.0.0.jar -Algorithm SHA256
Get-FileHash build/libs/build-compare-1.0.0.jar -Algorithm SHA256
~~~

Record actual measurements in a table:

| Metric | Maven | Gradle |
| --- | --- | --- |
| Executable JAR path | target/build-compare-1.0.0.jar | build/libs/build-compare-1.0.0.jar |
| File size | Record actual measurement | Record actual measurement |
| SHA-256 | Record actual digest | Record actual digest |
| Main-Class | Check manifest | Check manifest |
| Start-Class | Check manifest | Check manifest |
| Runtime dependencies | dependency:tree | runtimeClasspath |
| HTTP smoke test | PASS/FAIL | PASS/FAIL |

Do not fill in assumed numbers. Size and digest depend on resolved dependencies, JDK, plugin versions, archive metadata, and build configuration.

**Two different SHA-256 hashes do not prove that the applications behave differently.** A hash only identifies bytes. Inspect archive entries, manifest, dependencies, and runtime behavior to find the cause of differences.

## 13. Why Can Two JARs Differ in Bytes?

Even when source and dependencies are identical, Maven and Gradle can produce different archives due to:
- Entry ordering inside the ZIP/JAR.
- Entry timestamps.
- Compression level or how ZIP metadata is written.
- Manifest attributes and attribute ordering.
- Maven/Gradle archive plugin and Spring Boot plugin versions.
- Boot loader, classpath index, and layer metadata.
- Different bytecode if the two builds use different JDK patches/vendors.
- Generated resources, build-info, or timestamps generated by the project/plugins.

Distinguish three levels of comparison:

1. **Source equivalence:** both builds use the exact same sources/resources.
2. **Functional equivalence:** both executable artifacts run and return the same results according to tests/smoke-tests.
3. **Byte-for-byte reproducibility:** the same build process with the same inputs produces the exact same bytes across multiple builds.

The main goal of this lab is to demonstrate functional equivalence and verify resolved dependencies. Byte-for-byte equality across two build tools is a higher bar that requires deep standardization of archive metadata and toolchains; it is not a Spring Boot default.

## 14. Reproducible Builds for Each Tool

### 14.1. Maven

The Spring Boot Maven Plugin supports **outputTimestamp** and defaults to the value of the **project.build.outputTimestamp** property.

~~~xml
<properties>
    <java.version>17</java.version>
    <project.build.outputTimestamp>2026-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>
~~~

Use a fixed timestamp or a timestamp derived from commit/release metadata. Do not use the current wall-clock time on every build if you want to compare archive bytes across builds.

You must also control the Maven Wrapper, JDK, Maven plugins, dependencies, generated resources, and build environment.

### 14.2. Gradle

Gradle archive tasks have two relevant properties:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

This configuration drops wall-clock timestamps from entries and sorts entry order deterministically. Gradle 9 sets these archive defaults toward reproducibility; since this lab uses Gradle 8.14.3, declare them explicitly so results are easier to control.

Gradle also needs a fixed Java toolchain:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

The toolchain locks the Java major version; for strict comparison, use the same JDK vendor/patch and the same OS/architecture. A different JDK 17 patch can produce different bytecode or metadata.

### 14.3. Verifying reproducibility

1. Build from the same commit in a clean directory.
2. Save the SHA-256 digest.
3. Delete outputs and rebuild with the same Wrapper/JDK/configuration.
4. Compare digests.
5. Repeat on another machine/runner if policy requires it.
6. If the hash differs, compare archive entries/timestamps/manifest and generated files.

When comparing Maven against Gradle, verify functional equivalence first. Achieving identical hashes across two tools requires standardizing both compilation and packaging; that is a separate goal.

## 15. Running Both Artifacts to Verify Behavior

Do not run both on the same port simultaneously. Run one artifact, check the HTTP response, and stop the process before testing the other artifact.

### 15.1. Running the JAR from Maven

First terminal:

~~~bash
java -jar target/build-compare-1.0.0.jar --server.port=8081
~~~

Second terminal:

~~~bash
curl --fail --silent --show-error http://localhost:8081/hello
~~~

Expected body:

~~~text
build-comparison-ok
~~~

### 15.2. Running the JAR from Gradle

Stop the Maven process, then:

~~~bash
java -jar build/libs/build-compare-1.0.0.jar --server.port=8081
~~~

Verify:

~~~bash
curl --fail --silent --show-error http://localhost:8081/hello
~~~

Expected body:

~~~text
build-comparison-ok
~~~

### 15.3. Checking on Windows PowerShell

~~~powershell
Invoke-RestMethod http://localhost:8081/hello
~~~

Output:

~~~text
build-comparison-ok
~~~

If one artifact returns 200 while the other fails to start, check logs, Java version, manifest, nested dependencies, server port, and runtime configuration. Do not rely solely on the build task reporting SUCCESSFUL.

## 16. Comparing Test Reports

Maven Surefire typically writes test results to:

~~~text
target/surefire-reports/
~~~

Gradle writes test results and the HTML report to:

~~~text
build/test-results/test/
build/reports/tests/test/index.html
~~~

Compare total test count, passed/failed/skipped, test class/method names, stack traces, and the test runtime environment.

If Gradle does not run tests, check the task graph and JUnit Platform configuration. If Maven does not run tests, check the Surefire configuration, test naming conventions, and test-scope dependencies.

Builds should only be considered equivalent when both execute the same test suite and meet the same PASS criteria.

## 17. Comparing Build Times Fairly

Gradle has incremental task execution, a daemon, and a build cache. Maven has a local repository cache for dependencies and plugin artifacts; a standard Maven build does not keep a live daemon running like Gradle. These mechanisms make cold builds and warm builds behave very differently.

### 17.1. Cold build

A cold build measures the first run in an environment without dependencies/caches. It is affected by network speed, the number of artifacts downloaded, Wrapper distribution download, JDK provisioning, and CI runner startup.

Do not use a single cold build to conclude that one tool is faster.

### 17.2. Warm clean build

After dependencies have been downloaded, run the same clean build operation multiple times:

~~~bash
./mvnw -B -ntp clean verify
./gradlew clean build
~~~

Each tool should have a warm-up run. Then measure at least 5 runs and take the median. Use the same machine, JDK, source commit, network, and repository state.

### 17.3. Incremental build

Make a small change to one Java file and rebuild without clean. This is a useful metric for the developer loop, but it is not equivalent to a clean build.

Gradle may mark tasks as UP-TO-DATE or FROM-CACHE. Read task output to see what work was actually performed. Maven may also skip some compilation work depending on compiler plugin configuration, so observe logs rather than assuming every phase recompiles everything.

### 17.4. Reporting results

| Measurement | Maven | Gradle |
| --- | --- | --- |
| Cold build | Actual measurement | Actual measurement |
| Warm clean build median | Measure 5 runs | Measure 5 runs |
| Incremental build median | Measure 5 runs | Measure 5 runs |
| Tests | Same test count | Same test count |
| Executable JAR size | Actual measurement | Actual measurement |
| Runtime smoke test | PASS/FAIL | PASS/FAIL |

There is no universal conclusion that Maven is always slower or Gradle is always faster. Efficiency depends on the build graph, plugins, cache, daemon, project size, CI setup, and level of customization.

## 18. How to Interpret Dependency and Packaging Differences

| Observation | Could this be normal? | How to evaluate |
| --- | --- | --- |
| Maven output in target, Gradle in build/libs | Yes | Different output directory conventions |
| Maven has .jar.original, Gradle has -plain.jar | Yes | Different ways of keeping the plain archive |
| Different SHA-256 | Yes | Compare manifest, entries, dependencies, and behavior |
| One archive is larger | Yes | Check nested libraries, metadata, compression |
| Different dependency version | Needs investigation | Compare BOM, overrides, and resolved dependency graph |
| Different Main-Class | Needs investigation | Check Spring Boot plugin and archive type |
| Different Start-Class | Needs investigation | Check main class discovery/configuration |
| A JAR lacks BOOT-INF/lib | Incorrect for a standard executable JAR | May be comparing a plain JAR by mistake |
| One artifact does not run | Failed | Check manifest, loader, and runtime dependencies |
| Different test count | Needs investigation | Check test filters, JUnit Platform, and task execution |

If the two runtime dependency trees do not match, resolve that difference before comparing file sizes. One side may be packaging an extra optional dependency or a different version due to conflict resolution.

## 19. Additional Configuration When Keeping Plain JAR or Renaming

### 19.1. Maven classifier

By default, Maven repackage replaces the main artifact and saves the original with the **.original** suffix. If you want to publish both the plain JAR and the executable JAR as two artifacts, set a classifier for the executable archive:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>repackage</id>
            <configuration>
                <classifier>exec</classifier>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

With the starter parent, the repackage execution already exists; just configure the classifier on that execution. This allows installing/publishing the plain artifact and executable artifact separately.

### 19.2. Gradle classifier

Gradle sets the **plain** classifier on the regular JAR by default. If you want to change the classifier of the executable JAR, you can configure the BootJar task:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveClassifier.set("exec")
}
~~~

When changing the classifier, update output paths in comparison scripts and CI. Do not accidentally compare stale files left over in the build directory.

## 20. Organizing CI to Build the Same Source with Both Tools

A matrix pipeline can run two independent jobs from the same commit:

~~~text
Checkout one source commit
          |
          +-------------------------+
          |                         |
          v                         v
      Maven job                 Gradle job
          |                         |
     Maven Wrapper             Gradle Wrapper
          |                         |
      clean verify               clean build
          |                         |
     Maven executable JAR       Gradle bootJar
          |                         |
          +------------+------------+
                       |
                       v
             Compare test reports
             Compare dependency graphs
             Compare JAR layout/manifest
             Run both smoke tests
                       |
                       v
                Release decision
~~~

Conditions to maintain:
- Same source commit.
- Same JDK vendor/version.
- Pinned Wrapper distributions.
- Pinned plugin versions.
- Dependency versions managed with the same Spring Boot BOM.
- Same repository/mirror and credentials policy.
- Do not share output directories between the two jobs.
- Save test reports, dependency reports, artifact sizes, and checksums.

If CI only needs one build tool for releasing, you can keep the other job as a scheduled compatibility check or run it prior to migration. There is no need to build twice on every release if the cost is not justified.

## 21. Common Pitfalls During Comparison

| Symptom | Cause | Fix |
| --- | --- | --- |
| Maven JAR runs, Gradle JAR does not | Picked -plain.jar instead of bootJar | Use build/libs/*-1.0.0.jar |
| Gradle does not produce executable JAR | Only ran jar task or plugin was not applied | Check Spring Boot plugin and bootJar |
| Maven has no executable JAR | Did not run package/repackage or plugin execution was skipped | Check starter parent/plugin configuration |
| Different dependency versions | Inconsistent BOM/version overrides | Compare dependency tree and Gradle runtimeClasspath |
| Gradle tests do not run | Missing useJUnitPlatform or task disabled/filtered | Check test task and JUnit config |
| Maven tests do not run | Wrong Surefire/test naming/scope | Check Surefire logs and test dependencies |
| Main class not detected | Multiple main classes or class not in proper layout | Explicitly configure mainClass/Start-Class |
| Hash differs on every build | Different timestamps/generated metadata/toolchain | Standardize timestamps, archive order, and JDK |
| Two servers on the same port | Previous artifact is still running | Stop the process before the next test |
| File size increases unexpectedly | Extra dependency or different scope/packaging | Compare runtime dependency graph and BOOT-INF/lib |
| Unstable build times | One cold run, one warm run, or differing caches | Warm up, measure multiple runs, take median |
| CI differs from local | Different Wrapper/JDK/settings/profiles | Use Wrapper and pin toolchain/configuration |

## 22. Lab Completion Checklist

- [ ] Both build files are located in the same project root.
- [ ] Only one set of Java sources and resources exists.
- [ ] Same Spring Boot 3.5.16.
- [ ] Same Java 17 toolchain/runtime.
- [ ] Maven Wrapper and Gradle Wrapper are generated, pinned, and committed.
- [ ] Maven parent manages dependency/plugin versions.
- [ ] Gradle uses the corresponding Spring Boot BOM.
- [ ] Maven clean verify PASS.
- [ ] Gradle clean build PASS.
- [ ] Maven executable JAR is properly identified.
- [ ] Gradle bootJar is properly identified; not confused with plain JAR.
- [ ] Runtime dependency graphs are compared.
- [ ] Manifest Main-Class and Start-Class are inspected.
- [ ] BOOT-INF/classes and BOOT-INF/lib are inspected.
- [ ] Test reports have the same test count and results.
- [ ] Both JARs run with java -jar.
- [ ] Both return HTTP body build-comparison-ok.
- [ ] File sizes and SHA-256 digests are recorded from actual results.
- [ ] Build times are measured under identical cold/warm/incremental conditions.
- [ ] Differences in metadata/ZIP layout are explained.

## 23. Self-Check Exercises

**Question 1.** Can Maven and Gradle share the same source directory?

**Answer:** Yes. Both support the standard Java project layout src/main/java, src/main/resources, and src/test/java. Simply place both build files in the same project root.

**Question 2.** Why does Maven use spring-boot:repackage while Gradle uses bootJar?

**Answer:** The Maven Spring Boot plugin runs the repackage goal on the JAR/WAR created in the package phase. The Gradle Spring Boot plugin creates the bootJar task to build the executable archive.

**Question 3.** Why does Gradle also create a -plain.jar file?

**Answer:** Gradle keeps the jar task for the plain archive and uses the plain classifier to distinguish it from the executable bootJar.

**Question 4.** Why can two executable JARs run identically yet have different SHA-256 digests?

**Answer:** Archive entries, timestamps, compression, manifest metadata, plugin implementations, or bytecode may differ even though runtime behavior and dependency sets are equivalent.

**Question 5.** Does the spring-boot-dependencies BOM automatically add starter-web to the project?

**Answer:** No. The BOM manages versions. The project must still declare starter-web in dependencies or implementation.

**Question 6.** Why compare dependency trees before comparing file sizes?

**Answer:** If one artifact includes extra or different versions of runtime dependencies, the size difference may come from the dependency set rather than the build tool.

**Question 7.** Can both JARs be run on the same port for comparison?

**Answer:** Not simultaneously on the same address/port. Run them sequentially or use two separate ports.

**Question 8.** Does Maven clean delete Gradle outputs?

**Answer:** No. Maven clean deletes target; Gradle clean deletes build. Each build tool must be cleaned separately.

**Question 9.** Is Gradle faster than Maven in every project?

**Answer:** No. Speed depends on the task graph, cache, daemon, plugins, project size, CI, and how it is measured. Benchmark under identical conditions.

**Question 10.** What proves functional equivalence between the two artifacts in this lab?

**Answer:** Identical sources/dependencies, the test suite passing with the same results, and both executable JARs running successfully and returning the same HTTP response. Hash equality is a separate check and does not replace smoke testing.

## 24. Conclusion

Both Maven and Gradle can build the same Spring Boot application into an executable JAR. With Maven, the Spring Boot Maven Plugin uses **repackage** in the package lifecycle; with Gradle, the Spring Boot Gradle Plugin creates **bootJar** and the Gradle build task invokes it via assemble.

When comparing, do not stop at filename or size. Verify identical sources, Java version, Spring Boot BOM, resolved dependency versions, executable archive layout, manifest, test reports, and runtime HTTP behavior. When evaluating build performance or reproducibility, separate cold builds, warm clean builds, and incremental builds into distinct measurements.

## 25. Official References

- Spring Boot 3.5.16 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Spring Boot 3.5 — Gradle Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Spring Boot 3.5 — Gradle Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Gradle — Building Java & JVM Projects: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Task Basics: https://docs.gradle.org/current/userguide/task_basics.html
- Gradle — Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Best Practices for Reproducible Build Output: https://docs.gradle.org/current/userguide/best_practices_security.html#build-output-should-be-byte-for-byte-reproducible
- Apache Maven — Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — POM Reference: https://maven.apache.org/pom.html

# Creating an Executable JAR with Gradle bootJar

## 1. Lesson Goal

When building a Spring Boot application with Gradle, you typically want **a single JAR file that can be started with `java -jar`** on a machine without Gradle installed. The `bootJar` task from the Spring Boot Gradle Plugin serves this purpose: it packages classes, resources, runtime dependencies, and the Spring Boot loader into an executable archive.

This lesson guides you from configuration to verification, focusing on these questions:

- When does `bootJar` appear, which plugin provides it, and how does it differ from Gradle's `jar` task?
- Which source outputs and dependency classpaths does the task use to build the executable JAR?
- Why do `./gradlew bootJar`, `./gradlew assemble`, `./gradlew build`, and `./gradlew bootRun` have different effects?
- How do you create a working Spring Boot project using **Groovy DSL** or **Kotlin DSL**, run `bootJar`, and execute the resulting artifact?
- How do you identify the right file in `build/libs`, `BOOT-INF` layout, manifest, main class, and layered JARs?
- How do you configure the JAR name, classifier, main class, runtime dependencies, and launch script without breaking the artifact?
- How do you diagnose common issues, especially in multi-module projects or when CI/CD picks up the plain JAR by mistake?

**Scope:** Java 17 and Spring Boot Gradle Plugin 3.3.13 are used as a consistent example; these are illustrative versions, **not a claim about the latest Spring Boot release**. For real projects, use the version and Gradle wrapper approved by your team, and consult the documentation matching that version.

## 2. What Is `bootJar`, and Why Do You Need It?

An ordinary Java JAR can contain `.class` files and `META-INF/MANIFEST.MF`; however, a JAR containing application classes **does not automatically include all runtime libraries**. A Spring Boot web app needs many libraries such as Spring Framework, logging, a JSON mapper, and an embedded web server. If the JAR only has the project's own code, `java -jar` easily fails due to missing dependencies or missing an appropriate main manifest.

`bootJar` is a task of type `org.springframework.boot.gradle.tasks.bundling.BootJar`, provided by the **Spring Boot Gradle Plugin**. When an application applies both the Spring Boot plugin and the Java plugin, this task by default builds an executable JAR containing:

- Compiled classes from the `main` source set.
- Resources from the `main` source set.
- Required runtime JAR dependencies.
- The Spring Boot loader to load nested JAR dependencies and invoke the application's main class.
- Manifest metadata; under Spring Boot 3.3 configuration, the archive typically includes application main class and layer information.

`bootJar` is not a renamed Java `jar` task: it produces a **Spring Boot-structured archive format**. Unlike many "shaded JARs" that unpack and merge library classes into a flat namespace, a Boot executable JAR normally **keeps libraries as nested JARs** inside `BOOT-INF/lib`.

### 2.1. Conditions for Gradle to Create the `bootJar` Task

The Spring Boot Gradle Plugin reacts to the Java plugin. With this configuration:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}
~~~

Gradle provides the `main` source set, compile/resource tasks, and the `jar` task; the Spring Boot plugin adds `bootJar` and wires it into the `assemble` lifecycle. If you only apply the Spring Boot plugin without an appropriate Java/JVM plugin, **do not assume** that the project has `bootJar`.

A web starter is not required: an executable JAR can also be a CLI, batch application, or background consumer, provided the application has a main class and appropriate dependencies.

### 2.2. Difference from Maven `repackage`

Maven typically uses the `spring-boot:repackage` goal to process **a base JAR/WAR already produced by the standard packaging plugin** during the `package` lifecycle. Gradle's `bootJar` is a task that builds the executable archive directly from classes/resources/runtime classpath in Gradle's task graph. There is no default workflow of "Maven repackage then Gradle bootJar"; a project chooses the build tool used by its repository and CI.

## 3. `bootJar` in the Gradle Task Graph

Distinguish between artifact-producing tasks, lifecycle tasks, and application-running tasks.

~~~text
Java plugin + Spring Boot Gradle Plugin
                  |
                  +--> compileJava / processResources
                  |       |
                  |       +--> classes + runtimeClasspath
                  |                    |
                  |                    +--> bootJar
                  |
                  +--> jar           (plain JAR)
                  |
                  +--> assemble     (depends on outputs of archive tasks)
                  |       |
                  |       +--> bootJar
                  |
                  +--> check        (verifications; usually includes test)
                          |
build ---------------------+---- assemble
~~~

The diagram shows only the key relationships. Gradle may schedule additional tasks depending on plugins and configuration; verify exact ordering via the task graph.

| Command | Behavior Under Standard Configuration |
| --- | --- |
| `./gradlew bootJar` | Builds the executable Boot JAR and runs its required task dependencies; **does not run JUnit tests by default** |
| `./gradlew jar` | Builds a plain JAR via the Java plugin; does not replace `bootJar` |
| `./gradlew assemble` | Builds archives attached to assemble, including `bootJar`; may also build the plain JAR |
| `./gradlew build` | Per the Java lifecycle, depends on `assemble` and `check`, so it usually packages and runs tests |
| `./gradlew test` | Runs the test task; does not produce an executable JAR |
| `./gradlew bootRun` | Runs the application via Gradle using the main runtime classpath; not an archive release step |
| `./gradlew bootBuildImage` | Builds an OCI container image using Cloud Native Buildpacks; a different task from `bootJar` |

**Important for QA:** a passing `bootJar` is not proof that tests passed. In CI, if release criteria require tests, run `build`/`check` or a workflow configured to verify before publishing.

### 3.1. Inspecting the Task Graph Instead of Guessing by Name

~~~bash
./gradlew tasks --all
./gradlew bootJar --dry-run
./gradlew assemble --dry-run
./gradlew build --dry-run
~~~

`--dry-run` only shows which tasks would be scheduled; **it does not create a new JAR or execute test actions**. After inspecting the graph, run an actual build to confirm outputs. Depending on the Gradle version and build cache, tasks may display `UP-TO-DATE` or `FROM-CACHE`; that status differs from a task action having just run.

## 4. Preparing a Runnable Spring Boot Project

We will create a small `bootjar-demo` project with a `GET /artifact` endpoint returning the string `bootjar-ready`. The same Java code works with either Gradle Groovy DSL or Kotlin DSL; **choose only one DSL per project instance**.

Structure:

~~~text
bootjar-demo/
├── settings.gradle            # if using Groovy DSL
├── build.gradle               # if using Groovy DSL
│   or settings.gradle.kts   # if using Kotlin DSL
│   or build.gradle.kts      # if using Kotlin DSL
├── src/
│   ├── main/
│   │   ├── java/com/example/packaging/
│   │   │   ├── PackagingApplication.java
│   │   │   └── ArtifactController.java
│   │   └── resources/         # can be empty
│   └── test/
│       └── java/com/example/packaging/
│           └── ArtifactControllerTest.java
└── build/                     # generated by Gradle during build
~~~

If generated by Spring Initializr, the project may also include `gradlew`, `gradlew.bat`, `gradle/wrapper/...`, and other configuration files. **The wrapper is not generated automatically just because you create `build.gradle`**. Only run `./gradlew` when the wrapper exists; if absent, generate the wrapper per team procedures or use a preinstalled compatible `gradle`.

## 5. Complete Configuration in Groovy DSL

Create `settings.gradle`:

~~~groovy
rootProject.name = 'bootjar-demo'
~~~

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Explanation:

- `java` creates Java source sets and the `compileJava`, `processResources`, `classes`, `jar`, `test`, `assemble`, and `build` tasks.
- `org.springframework.boot` adds Spring Boot-related tasks, including `bootJar` and `bootRun` when the Java plugin is present.
- `io.spring.dependency-management` enables Spring Boot to automatically import its matching BOM version, allowing you to omit versions on BOM-managed starters.
- `group`, `version`, and `rootProject.name` help form the archive base name and version; in this example the default executable artifact is usually `bootjar-demo-0.1.0.jar`.
- The Java toolchain requests Java 17 for relevant tasks; a matching JDK must be available or Gradle must have a toolchain provisioning mechanism configured.
- `mavenCentral()` is where Gradle resolves application dependencies; it does not automatically replace plugin repository configuration.
- `testImplementation` is for the test classpath only; Spring Boot Test does not belong in the production executable JAR.
- `useJUnitPlatform()` tells Gradle to run tests on JUnit Platform.

**This is a ready-to-use build file**, not a partial fragment. It requires a compatible Gradle version, JDK, plugin repositories, and dependency resolution access. In offline environments or behind a corporate mirror without direct Maven Central access, adjust `repositories` per policy while keeping the rest of the syntax valid.

## 6. Equivalent Kotlin DSL Configuration

If the project uses Kotlin DSL, **replace** the two Groovy files with the pair below. Do not place both build files side by side assuming their effects combine.

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "bootjar-demo"
~~~

File `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

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

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

In Kotlin DSL, `languageVersion` is a Gradle property configured via `set`; `tasks.named<Test>("test")` specifies the task type to access `useJUnitPlatform()`. Using `build.gradle.kts` does not mean Java code must be written in Kotlin. **The same Java sources in the next section work with both DSLs.**

## 7. Java Sources and Test to Verify the Executable

### 7.1. Single Application Main Class

Create `src/main/java/com/example/packaging/PackagingApplication.java`:

~~~java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
~~~

Because this project has only **one** class with `public static void main(String[])` in the main output, the plugin usually detects the main class automatically. Spring Boot starts the application context with component scanning from package `com.example.packaging`.

### 7.2. Endpoint to Verify Execution

Create `src/main/java/com/example/packaging/ArtifactController.java`:

~~~java
package com.example.packaging;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ArtifactController {

    @GetMapping("/artifact")
    public String artifact() {
        return "bootjar-ready";
    }
}
~~~

This source requires `spring-boot-starter-web` for Spring MVC annotations and the embedded server. Without the web dependency, `GetMapping`/`RestController` will not be on the compile classpath.

### 7.3. JUnit Test Independent of the `bootJar` Task

Create `src/test/java/com/example/packaging/ArtifactControllerTest.java`:

~~~java
package com.example.packaging;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ArtifactControllerTest {

    @Test
    void returnsExpectedText() {
        ArtifactController controller = new ArtifactController();
        assertEquals("bootjar-ready", controller.artifact());
    }
}
~~~

This test does not need a Spring context because it invokes a plain Java method. It illustrates the role of the `test` task: JUnit runs assertions and reports pass/fail status.

The `bootJar` task does not need to run `ArtifactControllerTest` to build an executable JAR. Test code resides in test outputs and is normally **not packaged** into the release JAR. Run tests via `./gradlew test` or `./gradlew build` per your build policy.

## 8. Running `bootJar` End-to-End

Open a terminal at the project root, where the build script and settings file for your chosen DSL reside.

### 8.1. Checking the Environment

~~~bash
java -version
./gradlew --version
./gradlew tasks --all
~~~

Use `.\gradlew.bat` on Windows PowerShell, or use a preinstalled compatible `gradle` command if no wrapper is present. `./gradlew --version` shows the Gradle distribution and the JVM running Gradle; the toolchain used to compile may differ from the daemon JVM. If configuring Java toolchain 17 fails to locate a matching JDK 17, inspect `./gradlew javaToolchains`.

Look for the `bootJar` task under the application module in the `tasks --all` output. If it is missing, verify that both the Java plugin and Spring Boot plugin are applied to the right project.

### 8.2. Packaging the JAR from a Clean Project

~~~bash
./gradlew clean bootJar
~~~

Conceptual execution flow:

~~~text
clean
   ↓
compileJava + processResources
   ↓
classes
   ↓
resolve runtimeClasspath
   ↓
bootJar
   ↓
build/libs/bootjar-demo-0.1.0.jar
~~~

Gradle executes tasks based on the dependency graph and up-to-date checks; exact ordering can vary by configuration. `clean` typically deletes the `build` directory, helping avoid stale files.

`./gradlew clean bootJar` **does not require the `test` task**, so a build can produce an executable JAR even when unit tests have not run. To ensure tests run before release:

~~~bash
./gradlew clean build
~~~

By the default Java plugin lifecycle, `build` typically requires both `assemble` and `check`; `check` usually depends on `test`. If an organization customizes or disables the test task, inspect the task graph and logs to see actual execution conditions.

### 8.3. Running the Resulting File

In this illustrative configuration without custom archive name or classifier changes, the file is typically at:

~~~text
build/libs/bootjar-demo-0.1.0.jar
~~~

Run it:

~~~bash
java -jar build/libs/bootjar-demo-0.1.0.jar --server.port=18080
~~~

In another terminal:

~~~bash
curl -fsS http://localhost:18080/artifact
~~~

The expected HTTP body is:

~~~text
bootjar-ready
~~~

This is the **body** returned by the controller, not the full Spring Boot or Gradle logs. `curl` may not display a trailing newline because the controller returns a string without one. If port 18080 is already in use, choose another port and update the request accordingly. Stop the application with Ctrl+C.

The machine running the JAR needs a **compatible Java runtime** (for this example, Java 17+ compatible with the dependencies), plus required network/OS/resources and application configuration. That machine does not need Gradle installed to run the built archive.

### 8.4. What Can Be Concluded from These Results?

- `bootJar` succeeded: the plugin produced an archive according to task configuration.
- `jar tf` shows the Boot layout and runtime dependencies: evidence of packaging structure.
- `java -jar` startup succeeded: confirms the JVM can read the launcher and application main class in the current environment.
- HTTP `/artifact` returned the expected body: confirms the minimal application path works.
- `./gradlew test` passed: evidence that declared tests ran and passed.

**Do not treat one conclusion as proof of all the others.** An archive may build successfully yet fail at runtime due to environment/config; tests may pass yet the published artifact might accidentally be the plain JAR.

## 9. Inspecting the Contents of an Executable JAR

### 9.1. Why Does `BOOT-INF` Matter?

For an executable Spring Boot JAR in 3.3, the typical structure is:

~~~text
META-INF/
  MANIFEST.MF
BOOT-INF/
  classes/
    com/example/packaging/PackagingApplication.class
    com/example/packaging/ArtifactController.class
  lib/
    spring-boot-3.3.13.jar
    spring-context-....jar
    ... other runtime dependencies ...
  layers.idx                  # layer metadata under standard config
org/springframework/boot/loader/
  launch/JarLauncher.class
  ... Boot loader classes ...
~~~

This is a simplified diagram; actual JAR names and counts inside `BOOT-INF/lib` depend on the resolved dependency graph. If an application uses a custom Boot loader or altered layer configuration, archive details may differ.

**Application classes** sit in `BOOT-INF/classes`, while **nested JAR dependencies** sit in `BOOT-INF/lib`. The Boot loader knows how to construct the runtime classpath to invoke the main class; there is no need to unpack all nested JARs conventionally before starting.

### 9.2. Using JDK `jar` to List Entries

~~~bash
jar tf build/libs/bootjar-demo-0.1.0.jar
~~~

In the long listing, look for:

~~~text
BOOT-INF/classes/com/example/packaging/PackagingApplication.class
BOOT-INF/classes/com/example/packaging/ArtifactController.class
BOOT-INF/lib/
org/springframework/boot/loader/launch/JarLauncher.class
META-INF/MANIFEST.MF
~~~

If the JAR only has a few project classes at the root package and no `BOOT-INF/lib`, check whether you are inspecting the **plain JAR** instead of the Boot executable archive. Do not rely solely on byte size or file extension to tell them apart.

To inspect the manifest on Linux/macOS when `unzip` is available:

~~~bash
unzip -p build/libs/bootjar-demo-0.1.0.jar META-INF/MANIFEST.MF
~~~

If `unzip` is not installed, extract into **a temporary directory** using a ZIP/JAR tool and open `META-INF/MANIFEST.MF`; do not run `jar xf` directly in the project root if you want to avoid scattering untracked files in your workspace.

The manifest of a Spring Boot 3.3 executable JAR typically contains attributes like:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.packaging.PackagingApplication
~~~

`Main-Class` is the Spring Boot launcher; `Start-Class` is the class containing the application's main method. The Boot launcher name in **other versions** can differ; for instance, `org.springframework.boot.loader.JarLauncher` belongs to older lines and should not be hardcoded for 3.3. If you customize the launcher, verify against what you configured.

### 9.3. `jar` Is Not `bootJar`

With the Java plugin and Spring Boot 3.3, Gradle normally has two tasks:

- `jar` creates a **plain JAR**, containing application classes and resources per the Java plugin standard.
- `bootJar` creates an **executable Spring Boot JAR**, containing the Boot loader and runtime dependencies in the Boot layout.

To allow both archives to coexist, the Spring Boot plugin sets `plain` as the **convention classifier** on the `jar` task. After `./gradlew assemble` or `./gradlew build`, you may see:

~~~text
build/libs/
├── bootjar-demo-0.1.0.jar           # bootJar: executable
└── bootjar-demo-0.1.0-plain.jar     # jar: plain
~~~

**Verification note:** running `./gradlew bootJar` alone does not guarantee Gradle just created `-plain.jar`; the plain file could be left over from an earlier build or come from a customized task graph. To know which tasks ran in this invocation, read the build log and task graph.

A plain JAR can be the intended output when a module is a reusable library, but normally it is **not** a file runnable with `java -jar` with all Spring Boot dependencies included. CI/CD must not pick the first file matching `build/libs/*.jar` and assume it is the executable archive.

## 10. Customizing `bootJar` with Groovy DSL and Kotlin DSL

The snippets in this section are **additive fragments** for `build.gradle` or `build.gradle.kts`, not standalone build scripts. In Kotlin DSL, import the task type to access task-specific properties. If applying multiple fragments that both modify `archiveFileName` or `mainClass`, keep only one active naming/entry-point policy.

### 10.1. Explicitly Naming the JAR File

**Groovy — add to `build.gradle`:**

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'app-service.jar'
}
~~~

**Kotlin — add the import at the top of `build.gradle.kts`:**

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("app-service.jar")
}
~~~

`archiveFileName` controls this task's output file name without changing the project's group or version in dependency metadata. With this fragment, run:

~~~bash
./gradlew bootJar
java -jar build/libs/app-service.jar
~~~

Stop hardcoding `build/libs/bootjar-demo-0.1.0.jar` once the task file name changes. In CI, prefer referencing the explicit task output or controlled path rather than an ambiguous glob.

### 10.2. Setting the Main Class When Auto-Detection Is Not Enough

In the single-entry-point example, `bootJar` usually discovers `PackagingApplication` automatically. In a project with multiple `public static void main(String[])` methods, the plugin may require explicit configuration.

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    mainClass = 'com.example.packaging.PackagingApplication'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    mainClass.set("com.example.packaging.PackagingApplication")
}
~~~

This configures the application main class that the executable JAR will invoke. The value must match the actual package and Java class name; do not use a file path like `src/main/java/...` as `mainClass`.

The Spring Boot Gradle Plugin also supports configuring the main class on the project-level extension:

**Groovy:**

~~~groovy
springBoot {
    mainClass = 'com.example.packaging.PackagingApplication'
}
~~~

**Kotlin:**

~~~kotlin
springBoot {
    mainClass.set("com.example.packaging.PackagingApplication")
}
~~~

This is an **alternative option**; do not set conflicting values in both places. When Gradle's Application plugin is also applied, `application.mainClass` exists too; the key is avoiding conflicting configuration sources.

### 10.3. Changing the Executable JAR Classifier

Sometimes a team wants the plain JAR to keep the default name and the Boot JAR to carry the `-boot.jar` suffix. If both need to be published, ensure **distinct output names**.

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}
tasks.named('jar') {
    archiveClassifier = ''
}
~~~

**Kotlin:**

~~~kotlin
import org.gradle.jvm.tasks.Jar

tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("boot")
}
tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}
~~~

With the example's project/version and without overriding `archiveFileName`, the outputs can be:

~~~text
bootjar-demo-0.1.0.jar           # plain jar
bootjar-demo-0.1.0-boot.jar      # bootJar executable
~~~

Now **the unclassified file is no longer the executable**. This is an important reason to identify artifacts by the task that produced them, not merely by name.

If `archiveFileName='app-service.jar'` was set earlier, the fixed name can override classifier composition; pick one clear naming policy rather than copying both fragments at once.

### 10.4. Disabling the Plain `jar` Task When Truly Unneeded

**Groovy:**

~~~groovy
tasks.named('jar') {
    enabled = false
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<org.gradle.jvm.tasks.Jar>("jar") {
    enabled = false
}
~~~

This option only disables the `jar` task; it does not alter the `bootJar` definition. However, **do not disable `jar` by default** when a module also needs to publish a plain library artifact or when a native image workflow needs the `jar` task. Spring Boot 3.3 documentation specifically notes not disabling the `jar` task when building native images.

When both a plain JAR and an executable JAR are needed, keep both tasks and manage classifiers/publishing transparently.

### 10.5. Customizing the Output Directory

`BootJar` inherits Gradle archive task capabilities, including `destinationDirectory`. Example (additive fragment):

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    destinationDirectory = layout.buildDirectory.dir('release-artifacts')
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    destinationDirectory.set(layout.buildDirectory.dir("release-artifacts"))
}
~~~

After changing the output directory, stop looking in `build/libs` out of habit; in this illustrative config the file sits in `build/release-artifacts`. Note that downstream tasks, CI uploads, image builds, or publications must reference the new output. Avoid writing outputs directly into the source tree.

## 11. Dependency Classpath of `bootJar`

### 11.1. What Does `bootJar` Pull from the Project?

By default, `bootJar` uses **the runtime classpath of the `main` source set**. Simply put:

~~~text
main classes/resources
       +
runtime libraries on main.runtimeClasspath
       +
Spring Boot loader
       =
executable Boot JAR
~~~

The runtime classpath is shaped by `implementation`, `runtimeOnly`, project dependencies, Gradle resolution, and certain Spring Boot-specific configurations. There is no rule that "every dependency declared in `build.gradle` goes into the JAR".

| Configuration | Usually Included in Executable Boot JAR? | Explanation |
| --- | --- | --- |
| `implementation` | Yes, per resolved runtime graph | Main compile/runtime libraries |
| `runtimeOnly` | Yes | Libraries needed at runtime |
| `compileOnly` | No by default | Compile-time only; runtime expects another source or does not need it |
| `testImplementation` | No | For the test source set |
| `testRuntimeOnly` | No | For test runtime |
| `developmentOnly` | Excluded from Boot archive by default | For development environments per Spring Boot plugin |

If an application needs a JDBC driver at runtime but mistakenly places the dependency in `testImplementation`, `./gradlew test` may pass while the executable JAR fails to find the driver. Place required dependencies in the proper runtime scope; do not manually copy external JARs into the archive to mask resolution errors.

### 11.2. Example Adding a `runtimeOnly` Library

**Groovy:**

~~~groovy
dependencies {
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Kotlin:**

~~~kotlin
dependencies {
    runtimeOnly("org.postgresql:postgresql")
}
~~~

This fragment applies if the application **actually** uses PostgreSQL; it is not needed for the basic `/artifact` endpoint example. With the Spring Boot BOM, the compatible driver version is typically managed. To verify the library is in the production runtime graph, run `dependencies --configuration runtimeClasspath` or `dependencyInsight`, then inspect `BOOT-INF/lib` inside the JAR.

### 11.3. `developmentOnly` Dependencies

Some projects include:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

`spring-boot-devtools` aids development; the Spring Boot plugin excludes dependencies in the `developmentOnly` configuration from the executable archive by default. If DevTools is needed during `bootRun`, configure it for development; **do not include development-only libraries in release JARs out of habit**.

If you intentionally want to alter the classpath of the `bootJar` task, the Spring Boot Plugin lets you configure its classpath; however, that is an advanced option requiring careful testing and review because it can pull unwanted libraries into the artifact. Do not alter the classpath merely to avoid understanding dependency scopes.

## 12. Layered JARs: Meaning and Limitations

Spring Boot 3.3 supports layered executable JARs so layers with different rates of change can be processed/cached more efficiently when building container images. **A layered JAR is still an executable JAR**: classes and nested libraries still use the `BOOT-INF/classes` and `BOOT-INF/lib` layout, with added metadata describing the layers.

Default layers typically include:

| Layer | Typical Contents | Relative Change Frequency |
| --- | --- | --- |
| `dependencies` | Non-project dependencies without SNAPSHOT versions | Usually changes infrequently |
| `spring-boot-loader` | Spring Boot loader classes | Changes rarely across releases |
| `snapshot-dependencies` | Non-project SNAPSHOT dependencies | Can change frequently |
| `application` | Classes, resources, and project dependencies | Changes frequently during development |

Layer information is stored in `BOOT-INF/layers.idx` under standard configuration. **Layers are not an automatically created container image**; building an OCI image requires another task or tool, such as `bootBuildImage` or an appropriate Dockerfile.

In Spring Boot 3.3, a layered JAR may include `spring-boot-jarmode-tools` to support working with layers; consult the exact documentation because tool names and parameters vary across Boot releases.

### 12.1. Disabling Layer Metadata When Truly Required

**Groovy fragment:**

~~~groovy
tasks.named('bootJar') {
    layered {
        enabled = false
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    layered {
        enabled.set(false)
    }
}
~~~

This option alters layer metadata organization; it does not drop runtime dependencies or turn a Boot JAR into a plain JAR. In Spring Boot 3.3, disabling layering **does not automatically omit jarmode tools**; if tools must be excluded by artifact policy, configure `includeTools` separately per the exact version.

Do not disable layers merely because you do not understand `layers.idx`; if your organization uses container layer caching, disabling it can forfeit those benefits.

### 12.2. When Should You Customize Layers?

Advanced scenarios:

- An application includes multiple project dependencies with different change cadences.
- A container image build pipeline needs to split modules/libraries to optimize caching.
- Organizational build logic defines custom application/config/resource layers.

Before customizing layers, understand `intoLayer`, `include`/`exclude`, and `layerOrder` rules; ordering directly affects caching. Do not arbitrarily relocate files inside `BOOT-INF` since the Boot loader has archive layout requirements.

## 13. JARs Run with `java -jar` vs. "Fully Executable" JARs Are Not the Same Concept

**Normally:** an executable Spring Boot JAR built by `bootJar` is run using:

~~~bash
java -jar build/libs/bootjar-demo-0.1.0.jar
~~~

A **fully executable JAR** is a variant that prepends a **launch script at the beginning of the file** so it can be run directly like a script on certain Unix/Linux systems:

~~~bash
./build/libs/bootjar-demo-0.1.0.jar
~~~

To enable the launch script in Spring Boot 3.3:

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    launchScript()
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootJar>("bootJar") {
    launchScript()
}
~~~

`launchScript()` is an **advanced option**, not required for `java -jar` to work. Making an archive fully executable can prevent some ZIP/JAR tools from extracting it like a standard ZIP archive; Spring Boot documentation gives the example that `jar -xf` may not behave as expected when a script is prepended. Enable it only if your deployment environment genuinely needs to run the file directly as a script/service.

In standard containerized CI workflows, using `java -jar` or building images per organizational policy generally causes fewer surprises. Note that executable permissions (`chmod`) and shell execution apply only on supported systems; do not instruct Windows users to directly execute a Linux launch script.

## 14. Multi-Module Projects and Guidelines on Where to Use `bootJar`

Example:

~~~text
workspace/
├── settings.gradle(.kts)
├── shared-model/
│   └── build.gradle(.kts)       # library module
├── persistence/
│   └── build.gradle(.kts)       # library module
└── api-service/
    └── build.gradle(.kts)       # Spring Boot application
~~~

Common organization:

- `shared-model` and `persistence` apply Gradle's `java-library` plugin, producing **plain JARs** for other modules to consume.
- `api-service` applies the Spring Boot plugin and Java plugin, has a main class, and builds an **executable JAR** via `:api-service:bootJar`.
- The root aggregator may manage plugin versions or build conventions without necessarily applying the Spring Boot plugin to every subproject.
- Project dependencies pull subproject libraries onto `api-service`'s runtime classpath when declared via Gradle `implementation(project(":shared-model"))` or equivalent.

Invoke the task on the right module:

~~~bash
./gradlew :api-service:bootJar
./gradlew :api-service:build
~~~

**The name `api-service` is just an example**; run it only if the actual project defines that module in settings. Output file names, package/classpath paths, and source roots depend on the module.

If the Spring Boot plugin is applied across libraries that have no main class, the `bootJar` task may fail unable to find an entry point, or produce an artifact unsuitable for publishing as a reusable library. Keep clear boundaries between libraries and executable applications.

## 15. Verifying Tasks and Artifacts in CI/CD

A reliable release pipeline distinguishes **building the artifact**, **validation**, and **publication**:

1. Verify the JDK and Gradle wrapper from the repository.
2. Run validation steps per policy (typically `./gradlew clean build`).
3. Confirm `bootJar` appeared and succeeded in the task graph.
4. Identify **the exact output of the `bootJar` task**, rather than grabbing an arbitrary JAR file in `build/libs`.
5. Inspect the archive layout/manifest and, where appropriate, smoke-test startup.
6. Only after verifying the artifact, publish it to an artifact repository, image build, or deployment system under authorized credentials.

`bootJar` **does not automatically upload files to a Maven repository, deploy to a server, or build a Docker image**. Those steps require separate Gradle publishing/tasks, CI workflows, or deployment platforms.

An illustrative local command sequence:

~~~bash
./gradlew clean build
jar tf build/libs/bootjar-demo-0.1.0.jar
java -jar build/libs/bootjar-demo-0.1.0.jar --server.port=18080
~~~

The third command keeps the process running (for a web application); therefore, the HTTP smoke test must run in a separate terminal/process with proper cleanup and timeouts. Do not run the third command directly in a CI script expecting the pipeline to move on without process management.

If your workflow requires artifact checksums, SBOMs, signing, vulnerability scanning, or provenance, add those checks per organizational process; a runnable executable JAR does not by itself prove dependencies are secure or approved for release.

## 16. Diagnosing Common Errors

| Symptom | Common Cause | Proper Check |
| --- | --- | --- |
| `Task 'bootJar' not found` | Spring Boot plugin/Java plugin not applied to target module, or wrong task path | Check `plugins`, `./gradlew projects`, and `tasks --all` in the right module |
| `Main class name has not been configured` or main not found error | No `public static void main(String[])` in main source set, or multiple candidates | Check sources/package, explicitly configure `mainClass` |
| `bootJar` produces a file, yet `java -jar` says no main manifest | Might be running the plain JAR, or wrong manifest/task | Identify `bootJar`'s output file, inspect `META-INF/MANIFEST.MF` |
| `ClassNotFoundException` when running the archive | Missing runtime dependency, wrong file, or customized classpath | Check `runtimeClasspath`, `BOOT-INF/lib`, and build log |
| Tests pass, executable JAR misses JDBC driver | Driver declared only in `testImplementation`/`compileOnly` | Check `runtimeOnly` and Gradle dependency resolution |
| `-plain.jar` present so unclear which file to deploy | Both `jar` and `bootJar` exist with different classifiers | Check task outputs/manifest; do not pick the first glob match |
| `./gradlew bootJar` passes yet tests did not run | Packaging task does not depend on `test` by default | Run `build`/`test` and inspect task graph |
| `./gradlew build` has no new executable JAR | `bootJar` disabled, `assemble` config changed, or wrong module | `--dry-run`, task logs, check `outputDirectory`/cache |
| JAR has a different name than the tutorial | Project name/version/classifier/`archiveFileName` customized | Check settings, archive task properties, `build/libs` |
| `bootJar` fails when dependencies cannot download | Offline, wrong repository/mirror/proxy, or BOM version conflict | Check `repositories`, `dependencies`, `dependencyInsight`, Gradle diagnostics |
| Machine A runs it, Machine B fails on Java version | Runtime JDK is older than compiled bytecode/dependencies | `java -version` on target host, compare with Java toolchain |
| Library module has no main yet `bootJar` fails | Boot plugin applied to a library that should not be executable | Apply the Spring Boot plugin only to application modules |
| Published file fails to run | Pipeline published plain `jar` output instead of `bootJar` | Check publication task, artifact classifier, and manifest |
| `jar tf` fails to extract a fully executable JAR | Embedded launch script is present | Use documentation-supported tools/formats or omit launch script |
| Docker image build misses expected layers | Layer metadata/tools or image workflow customized | Check Boot 3.3 packaging config, `bootBuildImage`/Dockerfile |
| JAR runs yet HTTP endpoint does not respond | Port/profile/config/env, controller mapping, or startup error | Check Spring Boot logs and `curl` the exact URL; not necessarily a `bootJar` bug |

Do not try to fix issues by deleting dependencies indiscriminately, disabling tests, hardcoding `Main-Class` from another Boot version, or copying the entire `build/libs` directory to production. Start from **task logs**, **runtimeClasspath**, **artifact output**, and **runtime stack trace**.

## 17. Valuable Investigation Tools

### 17.1. Proving Plugin and Task Presence

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew bootJar --dry-run
~~~

`projects` identifies project paths; `tasks --all` lists tasks; `--dry-run` previews the execution plan. Do not treat `--dry-run` as proof that a new JAR was created.

### 17.2. Proving Runtime Dependencies

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

`dependencies` shows the dependency graph; `dependencyInsight` shows why a version was selected in that configuration. For multi-project builds, prefix the subproject path, e.g., `:api-service:dependencies` with `--configuration runtimeClasspath`.

A dependency appearing in the graph is not sufficient proof it made it into the final file if `bootJar` has custom classpath/excludes; when advanced configurations exist, cross-check the actual archive.

### 17.3. Proving Archive Layout

~~~bash
./gradlew clean bootJar
jar tf build/libs/bootjar-demo-0.1.0.jar
~~~

After verifying the manifest and Boot layout, run `java -jar` with an appropriate JVM and verify behavior. A good investigation order is **build task → output archive → runtime**, rather than editing application code first when the process fails to start.

## 18. Hands-On Exercises with Answers

### Exercise 1 — Minimal Packaging

**Task:** use either build script from Sections 5–6 with the three Java source files from Section 7. Run `./gradlew clean bootJar` and `java -jar build/libs/bootjar-demo-0.1.0.jar --server.port=18080`, then request `/artifact`.

**Expected outcome:** body `bootjar-ready`. You should be able to explain which class is the entry point, which task built the archive, and which file to deploy.

### Exercise 2 — Distinguishing Plain and Executable

**Task:** run `./gradlew clean assemble`; observe `build/libs`. Use `jar tf` and the manifest to distinguish `bootjar-demo-0.1.0.jar` from `bootjar-demo-0.1.0-plain.jar`.

**Answer:** Under Spring Boot Gradle Plugin 3.3 conventions, `bootJar` creates the unclassified file and `jar` creates `-plain.jar`. The Boot executable typically has `BOOT-INF/classes`/`BOOT-INF/lib` and the Boot launcher. If a build customizes classifiers, inspect actual outputs rather than relying on fixed suffixes.

### Exercise 3 — Are Tests Included in `bootJar`?

**Task:** run `./gradlew clean bootJar --dry-run` and `./gradlew clean build --dry-run`, and explain why one graph includes or omits `test`. Then run `./gradlew clean build` to confirm tests actually execute.

**Answer:** `bootJar` builds the executable artifact and runs packaging dependencies; it does not inherently depend on JUnit `test`. The Java lifecycle `build` typically includes `assemble` and `check`, and `check` typically triggers `test`. `--dry-run` only proves tasks are scheduled, without executing test actions.

### Exercise 4 — Naming and Classifiers

**Task:** rename the executable to `service.jar` using `archiveFileName`. Run `bootJar` and launch it with the right command.

**Answer:** After renaming, the runtime path is `build/libs/service.jar` if `destinationDirectory` was not changed. Do not continue referencing `bootjar-demo-0.1.0.jar` in release documentation.

**Follow-up question:** if you change `bootJar`'s classifier to `boot` and set `jar`'s classifier to empty, which file is executable?

**Answer:** The `bootJar` output carrying the `-boot.jar` suffix is the executable. The file without a classifier suffix is now the plain JAR.

### Exercise 5 — Multiple Main Class Candidates

**Scenario:** the main source set has both `PackagingApplication` and `ToolApplication` declaring `public static void main(String[])`; `bootJar` fails unable to pick a main class.

**Answer:** Explicitly select the main class via `tasks.named<BootJar>("bootJar") { mainClass.set("com.example.packaging.PackagingApplication") }` in Kotlin DSL or the equivalent Groovy syntax. Do not delete the other main class if that tool is genuinely needed in the codebase.

### Exercise 6 — Clean Release

**Task:** verify the Boot JAR contains `ArtifactController.class` and does not contain `ArtifactControllerTest.class`. If a test class appears in the artifact, investigate which parts of the build could pull test output into main packaging.

**Answer:** Under standard Java plugin configuration, `bootJar` uses main output/`runtimeClasspath` and excludes test sources/outputs. If test classes leak in, inspect `sourceSets`, `bootJar.classpath`, custom `from(...)`/`copy` logic, and which artifact was selected.

### Exercise 7 — Checking Layer Understanding

**Question:** Should you disable `layered` to fix a missing main class error?

**Answer:** No. Layer metadata organizes contents for image caching; it does not determine whether the application has a main method. Main class errors must be resolved in the source set and `mainClass`/plugin configuration, not by toggling `layered`.

## 19. Pre-Release Checklist

- [ ] Correct application module has the Spring Boot Gradle Plugin and Java plugin.
- [ ] Java main class is valid and in the right package; if multiple candidates exist, `mainClass` is configured.
- [ ] Gradle wrapper/JDK match requirements; dependency repositories resolve cleanly.
- [ ] Runtime dependencies are declared in proper scopes, not relying on test-only dependencies.
- [ ] Required verification steps ran and passed; `bootJar` is not treated as a test suite.
- [ ] `bootJar` task succeeded; output filename/classifier are clearly identified.
- [ ] Release file contains Boot loader, `BOOT-INF/classes`, `BOOT-INF/lib`, and valid manifest.
- [ ] `java -jar` starts in a test environment and key endpoints/flows work.
- [ ] Plain JAR (if present) and executable JAR are not mixed up in the publish pipeline.
- [ ] Test fixtures, development-only dependencies, or secrets are not accidentally packaged into production JARs.
- [ ] Any changes to `archiveFileName`, directory, layers, or launchScript are reflected in CI/ops.

**Completion criteria:** from a Java Spring Boot project, you can build an executable JAR with Gradle `bootJar`, accurately explain the task graph and how it differs from `jar`, prove the contents/manifest, launch it with `java -jar`, and resolve common configuration errors.

## 20. Official Reference Documentation

- Spring Boot 3.3.13 — Packaging Executable Archives with Gradle (`bootJar`, plain/classifier, main class, layers, launch script): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3.13 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot 3.3.13 — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 — First Application / Gradle executable JAR: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Gradle Java Plugin (`jar`, `test`, `assemble`, `build`, and source sets): https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle Java Toolchains: https://docs.gradle.org/current/userguide/toolchains.html

Whenever a project changes its Spring Boot Plugin or Gradle wrapper, consult documentation for the **exact version** before copying commands and version-specific properties. The goal is not merely to produce a `.jar` file, but to produce **the right executable archive from the right module, with the right runtime dependencies, tested and ready to launch**.
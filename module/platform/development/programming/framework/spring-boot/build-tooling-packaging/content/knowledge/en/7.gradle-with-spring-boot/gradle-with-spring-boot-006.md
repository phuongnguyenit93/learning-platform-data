# Customizing `springBoot.mainClass` and Boot Tasks in Gradle

In a Spring Boot project using Gradle, the class containing `public static void main(String[] args)` is usually discovered automatically by the plugin. When a project has **multiple entry points**, multiple modules, or wants to run one main class during development while packaging another, automatic discovery may no longer be unambiguous. The Spring Boot Gradle plugin lets you declare **`springBoot.mainClass` project-wide** and configure individual tasks such as `bootRun`, `bootJar`, `bootWar`, and `bootBuildImage`.

This lesson explains how main class selection works, how to configure **Groovy DSL (`build.gradle`)** and **Kotlin DSL (`build.gradle.kts`)**, how to pass arguments/JVM options, the difference between running and packaging, and how to inspect the output artifact. Examples use **Spring Boot 3.3.13, Java 17, Gradle 8.x** for consistency; these are instructional versions, **not an implication of the latest Spring Boot release**. Check the corresponding documentation if your project uses a different Spring Boot or Gradle branch.

## 1. From Plugin to Boot Tasks

`org.springframework.boot` is a **Gradle plugin** that adds capabilities to build and run Spring Boot applications. It reacts to other Java/WAR/application plugins to register, wire, and configure appropriate tasks.

| Task | Function | Main conditions or notes |
| --- | --- | --- |
| `bootRun` | Runs the app directly from the main classpath; no need to build an executable JAR first | Created when the Spring Boot plugin is applied with the Java plugin |
| `bootJar` | Packages an executable JAR containing the app and runtime dependencies | Available with the Java plugin; distinct from regular `jar` |
| `bootWar` | Packages an executable WAR | Available when the `war` plugin is applied; needs suitable deployment config |
| `bootBuildImage` | Uses Cloud Native Buildpacks to build an OCI container image from the packaged app | Requires a supported Docker daemon/container endpoint; does not run merely from calling `build` |
| `bootTestRun` | Runs a main class from the **test source set** with the test runtime classpath | Useful for test launchers; not a unit test runner |
| `bootBuildInfo` | Generates build metadata `META-INF/build-info.properties` | Usually requires `springBoot { buildInfo() }` to register/use |
| `bootAot`, `bootTestAot`, `processAot` | AOT-related tasks when provided by matching version/plugins/config | Do not assume they always exist in every project; verify via actual task list |

**Distinguishing tasks:** `test` runs JUnit tests; `bootTestRun` runs a **program with `main` in the test source set**. `bootJar` produces an artifact; `bootRun` runs directly; `bootBuildImage` builds a container image. They share some settings but have different purposes and outputs.

Typical flow:

```text
src/main/java + src/main/resources
                |
            compileJava
                |
       classes / resources
                |
          +-----+---------------------+
          |                           |
       bootRun                       bootJar
    (JavaExec)              (Boot executable archive)
          |                           |
      JVM runs                    build/libs/*.jar
                                      |
                                      v
                               bootBuildImage
                                (OCI image)

src/test/java + src/test/resources
                |
           test classes
                |
          +-----+------+
          |            |
         test       bootTestRun
        (JUnit)      (main test)
```

This is a **conceptual diagram**, not a complete task dependency list. To view actual tasks in a project, run `./gradlew tasks --all` or `./gradlew help --task bootJar`. A library project that does not apply the Spring Boot plugin will not have Boot tasks.

## 2. What Is `mainClass`? Where to Choose the Startup Class?

### 2.1. Meaning of the Main Class

A Java program starts at the method:

```java
public static void main(String[] args)
```

With Spring Boot, the startup class is usually annotated with `@SpringBootApplication` and calls `SpringApplication.run(...)`. However, a **Java main class does not have to carry `@SpringBootApplication`**: a command-line utility in the same project can also declare `main`.

The name used in Gradle is the **fully qualified class name including package**, for example:

```text
com.example.launch.LaunchApplication
```

Do not use the file path `src/main/java/com/example/launch/LaunchApplication.java`, do not append `.java` or `.class`, and do not write the short name `LaunchApplication` when the actual package is `com.example.launch`.

### 2.2. How Does Gradle Boot Discover the Main Class Automatically?

In Spring Boot 3.3, `bootRun`, `bootJar`, and `bootWar` can determine the main class by searching for a class with a `public static void main(String[])` method in the **main source set output**. When there is **one clear candidate**, the default configuration usually suffices. When **there are multiple candidates**, the plugin may fail to pick uniquely or pick an unintended one; the solution is explicit declaration.

If a project only has a test main class in `src/test/java`, it does not become the main class of the main executable JAR; `bootTestRun` is a separate case that searches the **test source set**.

### 2.3. Project-Wide Setting: `springBoot.mainClass`

With **Groovy DSL** (`build.gradle`):

```groovy
springBoot {
    mainClass = 'com.example.launch.LaunchApplication'
}
```

With **Kotlin DSL** (`build.gradle.kts`):

```kotlin
springBoot {
    mainClass.set("com.example.launch.LaunchApplication")
}
```

This configures the **project's Spring Boot plugin extension**. It supplies a shared main class selection for Boot tasks that follow that convention, notably `bootRun` and executable archive tasks. Prefer this approach when you want **local runs and production JAR/WAR builds to share the same entry point**.

**Do not confuse with `spring.main.*` in `application.yml`:** `springBoot.mainClass` is a **Gradle build** configuration selecting which class contains `main`. `spring.main.*` is a group of **Spring Application runtime** properties with different meanings; it does not select the class for `bootJar`.

## 3. Runnable Example: A Project with Two Main Classes

Suppose a project has a real REST application and a console utility for quick checks. Structure:

```text
launcher-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/main/java/com/example/launch/
    ├── LaunchApplication.java
    └── DiagnosticMain.java
```

Create `settings.gradle`:

```groovy
rootProject.name = 'launcher-demo'
```

Create the complete `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

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

springBoot {
    mainClass = 'com.example.launch.LaunchApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Explanation:** The Java toolchain requests Java 17 for compilation/tests; the Spring Boot plugin provides Boot tasks; the dependency-management plugin manages dependency versions using the corresponding Spring Boot BOM. `springBoot.mainClass` uniquely selects `LaunchApplication` even though the project also has `DiagnosticMain`. The plugin versions in the example are a **specific illustrative pair**; when upgrading, check compatibility for the plugins in use.

Create `src/main/java/com/example/launch/LaunchApplication.java`:

```java
package com.example.launch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LaunchApplication {

    public static void main(String[] args) {
        SpringApplication.run(LaunchApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping("/ping")
    String ping() {
        return "boot-main-ok";
    }
}
```

Create `src/main/java/com/example/launch/DiagnosticMain.java`:

```java
package com.example.launch;

public final class DiagnosticMain {

    private DiagnosticMain() {
    }

    public static void main(String[] args) {
        System.out.println("diagnostic:" + String.join(",", args));
    }
}
```

Both files are valid Java 17; the public class filenames and packages are consistent. `PingController` is a package-private class in `LaunchApplication.java`, which Spring scans via `@SpringBootApplication`'s package.

Run the **REST application** with the default task:

```bash
./gradlew bootRun --args='--server.port=8091'
```

Once the app has started, open another terminal and send:

```bash
curl -s http://localhost:8091/ping
```

Expected HTTP response body:

```text
boot-main-ok
```

This is the response **body**; Spring Boot/Gradle logs do not have fixed stdout. `--args` passes **application arguments** (here, Spring Boot property `server.port`) for that `bootRun` invocation; it does not rewrite `application.yml` and does not change the entry point inside the JAR built later.

Package:

```bash
./gradlew clean test bootJar
```

With the configuration above, the artifact is normally named `build/libs/launcher-demo-1.0.0.jar`. Run:

```bash
java -jar build/libs/launcher-demo-1.0.0.jar --server.port=8091
```

Send `GET /ping` again and observe the body `boot-main-ok`. **Stop the `bootRun` process first** to avoid a port 8091 conflict. The commands above are for Linux/macOS; on Windows PowerShell use `.\gradlew.bat` instead of `./gradlew` when the project has a Gradle Wrapper.

## 4. Configuring a Separate Main Class per Task

Set `springBoot.mainClass` as the default and only override when a task genuinely needs a different entry point.

### 4.1. `bootRun` Running a Different Main than the Executable JAR

Append to the end of `build.gradle` in the example above:

```groovy
tasks.named('bootRun') {
    mainClass = 'com.example.launch.DiagnosticMain'
    args 'alpha', 'beta'
}
```

Run:

```bash
./gradlew bootRun
```

Here is the **stdout from `DiagnosticMain`** (ignoring surrounding Gradle logs):

```text
diagnostic:alpha,beta
```

Now `bootRun` executes the console main and exits quickly; **`bootJar` still uses `com.example.launch.LaunchApplication`** per the project-wide setting, because you only overrode `bootRun`. To run the REST app as in section 3, remove this override block or switch `bootRun`'s `mainClass` back.

This technique is useful for running internal tools, migration launchers, or config checks without packaging that tool as the production entry point. Still, an application should have a clear deployment entry point; avoid letting local config diverge from packaged builds without good reason and testing.

### 4.2. `bootJar` Using a Different Main than `bootRun`

To override only the JAR's entry point, configure:

```groovy
tasks.named('bootJar') {
    mainClass = 'com.example.launch.LaunchApplication'
}
```

When there is only one right main class, this block is unnecessary. It is especially helpful in projects with multiple programs or when setting up per-artifact configurations. If you set `bootJar.mainClass` to `DiagnosticMain` instead of `LaunchApplication`, the JAR will run the console program; the Spring Boot web server will not start automatically merely because the web dependency is present.

**Scope of effect:** a task override affects **only that task**. `bootRun.mainClass` does not automatically change `bootJar.mainClass`, and vice versa. `bootBuildImage` builds an image from the archive it consumes, so **the image's actual entry point is tied to the packaged artifact**, not necessarily the local `bootRun` task.

### 4.3. Customizing `bootWar` When Packaging as WAR

For a project that has applied the Gradle `war` plugin and needs an executable WAR:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

springBoot {
    mainClass = 'com.example.launch.LaunchApplication'
}

tasks.named('bootWar') {
    archiveFileName = 'launcher-demo.war'
}
```

This is an **illustrative snippet for a separate WAR project configuration**—do not insert a second `plugins` block into section 3's `build.gradle`. For WAR applications that must run in an external servlet container, you also need a launcher/`SpringBootServletInitializer`, proper dependency scope (e.g., `providedRuntime` for the container), and deployment setup; declaring `bootWar` alone does not complete external servlet container deployment. When deploying solely via executable JAR, keep using `bootJar`.

## 5. Configuring `bootRun`: Program Arguments, JVM, and Runtime Environment

`bootRun` is a task of type `BootRun`, extending Gradle's `JavaExec`. Thus you can customize **arguments passed to `main`**, JVM arguments, system properties, working directory, and environment variables for the test run process.

### 5.1. Application Args vs. JVM Args vs. Gradle Args

| Argument type | Example | Who receives it? |
| --- | --- | --- |
| Gradle task/option | `./gradlew bootRun --info` | Gradle, used to control/log the build process |
| Application arguments | `./gradlew bootRun --args='--server.port=8091'` | The `String[] args` array of the main class |
| App JVM system property | `systemProperty 'app.mode', 'local'` in `bootRun` | The JVM launched by `bootRun` |
| JVM argument | `jvmArgs '-Xmx512m'` in `bootRun` | The JVM running the app; sets heap, module flags... |
| Environment variable | `environment 'DEMO_FLAG', 'on'` | Process environment of the launched JVM |

Groovy configuration:

```groovy
tasks.named('bootRun') {
    systemProperty 'app.mode', findProperty('runMode') ?: 'local'
    jvmArgs '-Xmx512m'
    environment 'DEMO_FLAG', 'on'
}
```

Then:

```bash
./gradlew bootRun -PrunMode=dev --args='--server.port=8091'
```

`-PrunMode=dev` creates a **Gradle project property**. The `systemProperty` line passes it as the Java system property `app.mode=dev` into the application JVM. `--args` goes into `String[] args`. If `-PrunMode` is omitted, `app.mode` takes the value `local`.

**Distinguish the JVM running Gradle from the `bootRun` JVM:** `org.gradle.jvmargs` tunes the Gradle daemon, whereas `bootRun.jvmArgs` tunes the application Java process. Also do not confuse `jvmArgs` with application args.

### 5.2. Reading Resources Directly During Development

By default, resources are processed/copied from `src/main/resources` into the classpath output before `bootRun` uses them. You can allow `bootRun` to read certain static resources directly from source directories:

```groovy
tasks.named('bootRun') {
    sourceResources sourceSets.main
}
```

This lets you see static resource changes while running. It **does not automatically hot-reload Java source** and does not change how `bootJar` packages files; automatic restart on class changes normally requires devtools/IDE/build integration.

### 5.3. Startup Optimization in `bootRun`

`bootRun` enables `optimizedLaunch` by default to improve startup speed during development. Disable it only for measurement or debugging reasons:

```groovy
tasks.named('bootRun') {
    optimizedLaunch = false
}
```

This is a **`bootRun` task** setting, not a way to toggle Spring Boot auto-configuration, and is not equivalent to bytecode/JVM optimizations for production JARs.

## 6. `bootJar`: JAR Name, Main Class, and Manifest

### 6.1. `bootJar` vs. `jar`

When using the Spring Boot Gradle plugin with the Java plugin:

- `bootJar` creates the **Spring Boot executable JAR** containing app classes/resources and runtime dependencies.
- `jar` is Gradle's Java task creating a **plain JAR** (typically assigned the `plain` classifier to distinguish it).
- `assemble` / `build` are normally wired to `bootJar`. When verifying only a specific artifact, you can invoke `bootJar` directly.

Typical executable JAR structure:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...       # Spring Boot launcher
BOOT-INF/classes/...                      # application classes and resources
BOOT-INF/lib/...                          # runtime dependency JARs
```

**Do not manually overwrite the manifest's `Main-Class` with your application class.** In an executable Boot JAR, `Main-Class` is normally the Spring Boot launcher, while `Start-Class` points to **the application's entry point**. Configuring `springBoot.mainClass` or `bootJar.mainClass` lets the plugin manage `Start-Class` and the launch layout properly. In specialized cases you can tweak `Start-Class` via manifest configuration, though `mainClass` is the cleanest way.

### 6.2. Renaming the Artifact Without Changing the Main Class

Add to `build.gradle`:

```groovy
tasks.named('bootJar') {
    archiveFileName = 'launcher-demo.jar'
}
```

Run:

```bash
./gradlew bootJar
jar tf build/libs/launcher-demo.jar
java -jar build/libs/launcher-demo.jar
```

`archiveFileName` changes the **output filename**; it does not change `springBoot.mainClass`, Java source packages, or endpoint paths. To alter the classifier or output directory, use Gradle's corresponding archive properties and verify the actual artifact. If the project runs both `jar` and `bootJar`, pick the right artifact when deploying; plain JARs generally cannot run with `java -jar` like executable Boot JARs.

### 6.3. About `launchScript()` and Layered JARs

`bootJar` supports advanced packaging customization, for example:

```groovy
tasks.named('bootJar') {
    // Enable only if direct execution as a shell script on compatible systems is needed
    launchScript()
}
```

`launchScript()` prepends a shell script to the archive so it can be executed directly on compatible Unix systems. Some ZIP/JAR tools may not handle this format as expected; do not enable it merely to change the main class. Standard executable JARs already work with `java -jar` without a launch script.

Spring Boot 3.3 also supports **layered archives** to optimize image caching; `mainClass` still identifies the entry point, while layers define how classes/dependencies are grouped. These two concepts are independent.

## 7. `bootBuildImage`: From Packaging Task to OCI Image

`bootBuildImage` uses Cloud Native Buildpacks to build a container image from the executable archive, typically from `bootJar` or `bootWar`. If you set a main class on the archive, the image carries the entry point inside the built artifact. It **does not run a local server via `bootRun`**.

Example customizing the image name:

```groovy
tasks.named('bootBuildImage') {
    imageName = 'example/launcher-demo:1.0.0'
}
```

Command:

```bash
./gradlew bootBuildImage
```

The task requires access to a Docker daemon and a supported builder/run image; downloading builders/buildpacks may require network access. This example **builds a local image**; it does not push the image to a registry unless publishing is configured. To confirm the artifact has the right main class, inspect `bootJar`/`bootWar` first, then check the generated image and test running it in a matching container environment.

**Do not assume `./gradlew build` always builds an OCI image.** `build` normally covers verification and JAR/WAR packaging; `bootBuildImage` is a separate task that must be invoked explicitly or wired intentionally into the graph.

## 8. `bootTestRun` and `bootBuildInfo` Do Not Share `bootRun`'s Role

### 8.1. `bootTestRun`

Spring Boot 3.3 registers `bootTestRun` to run a main class in the **test source set** with the test runtime classpath. For example, create `src/test/java/com/example/launch/TestLauncher.java`:

```java
package com.example.launch;

public final class TestLauncher {

    private TestLauncher() {
    }

    public static void main(String[] args) {
        System.out.println("test-launcher");
    }
}
```

Run:

```bash
./gradlew bootTestRun
```

If there are no other test main classes causing ambiguity, stdout from the program includes:

```text
test-launcher
```

To avoid relying on entry-point auto-detection, configure it explicitly:

```groovy
tasks.named('bootTestRun') {
    mainClass = 'com.example.launch.TestLauncher'
}
```

**Do not use `bootTestRun` to replace `./gradlew test`.** The `test` task runs tests via the test framework; `bootTestRun` merely executes the chosen test main class and may exit or stay running depending on the program.

### 8.2. `bootBuildInfo`

The Spring Boot plugin can generate build metadata via DSL:

```groovy
springBoot {
    buildInfo()
}
```

When enabled, the `bootBuildInfo` task generates metadata such as name, version, and build time (configurable) to support exposing application build information. This task **does not select the main class**, does not directly compile Java, and does not replace `bootJar` for building an executable JAR.

Depending on your project and reproducible build practices, you may need to control or exclude the build timestamp so artifact contents do not vary on every build. Only enable build info if an actual consumer uses the metadata.

## 9. Kotlin DSL Equivalent

The snippets above use Groovy DSL. With `build.gradle.kts`, configure specific tasks using typed task methods:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    java
    id("org.springframework.boot") version "3.3.13"
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

springBoot {
    mainClass.set("com.example.launch.LaunchApplication")
}

tasks.named<BootRun>("bootRun") {
    systemProperty("app.mode", findProperty("runMode") ?: "local")
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("launcher-demo.jar")
}

tasks.test {
    useJUnitPlatform()
}
```

This is a **complete `build.gradle.kts` file** working with the two Java classes in section 3. Key differences:
- Groovy: `mainClass = '...'`. Kotlin: `mainClass.set("...")`.
- Groovy: `tasks.named('bootJar') { ... }`. Kotlin: `tasks.named<BootJar>("bootJar") { ... }`.
- Groovy allows method-call syntax `jvmArgs '-Xmx512m'`; Kotlin uses `jvmArgs("-Xmx512m")`.
- Do not copy Groovy syntax directly into `build.gradle.kts`, and do not copy Kotlin DSL into `build.gradle`.

To switch **`bootRun` to the diagnostic main** in Kotlin DSL, add:

```kotlin
tasks.named<BootRun>("bootRun") {
    mainClass.set("com.example.launch.DiagnosticMain")
    args("alpha", "beta")
}
```

This snippet **overrides `bootRun` configuration on the same task**; in a complete file, merge properties into one `tasks.named<BootRun>("bootRun")` block or edit the existing block for readability rather than scattering configuration across multiple blocks for the same purpose.

## 10. Multi-Module Projects: Apply Boot Tasks Only to Runnable Modules

Example of a Gradle multi-project build:

```text
root-project/
├── settings.gradle
├── build.gradle
├── shared-lib/
│   └── build.gradle
└── api-service/
    └── build.gradle
```

`shared-lib` is a library; `api-service` is a Spring Boot application. Tasks belong to the **projects that own them**: `:api-service:bootRun`, `:api-service:bootJar`, `:shared-lib:jar`.

Place `springBoot.mainClass` **inside the runnable application project**:

```groovy
// api-service/build.gradle (module configuration snippet)
springBoot {
    mainClass = 'com.example.api.ApiApplication'
}
```

Do not assume every module in a repository has `bootJar` or a `main` class. Applying the Boot plugin to all subprojects including libraries may create unnecessary Boot tasks or fail builds due to missing main classes. Instead, pure libraries usually need only `java-library`; application modules apply `org.springframework.boot` where appropriate.

Run from the root directory:

```bash
./gradlew :api-service:bootJar
./gradlew :api-service:bootRun
```

These two commands are **examples for a module actually named `api-service`**. Colons denote Gradle project paths. When running `bootRun` on a different module, do not change a global main class across all projects just to switch the target being executed.

## 11. Verifying the Actual Main Class in the JAR and Task Graph

### 11.1. Viewing the Task List

```bash
./gradlew tasks --all
./gradlew help --task bootRun
./gradlew help --task bootJar
```

If `bootJar` is missing, check `java`/`org.springframework.boot` plugins in the right project. If `bootWar` is missing, check the `war` plugin. To view dependent tasks without executing them:

```bash
./gradlew bootJar --dry-run
```

`--dry-run` shows which tasks are planned to run; it **does not inspect JAR contents**, so you must actually build to verify the main class and dependencies.

### 11.2. Distinguishing `Start-Class` and `Main-Class`

Build:

```bash
./gradlew clean bootJar
```

Use the JDK command:

```bash
jar tf build/libs/launcher-demo-1.0.0.jar
```

Look for `META-INF/MANIFEST.MF`, `BOOT-INF/classes/com/example/launch/LaunchApplication.class`, and `BOOT-INF/lib/`. For a Spring Boot 3.3 executable JAR, a typical manifest has:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.launch.LaunchApplication
```

These are **two illustrative properties to cross-check**, not the entire manifest; ordering and other fields may vary. You can inspect manifest contents with a suitable ZIP/JAR viewer, or extract `META-INF/MANIFEST.MF` into a temporary directory and open it. `jar tf` **only lists entries** and does not print manifest contents.

- **`Main-Class`**: the Boot launcher, telling Java which program handles the initial `java -jar` invocation.
- **`Start-Class`**: the application's actual `main` class, to which the Boot launcher delegates control.

If the manifest shows an unexpected `Start-Class`, inspect `springBoot.mainClass`, `tasks.named('bootJar')`, `application.mainClass` (if present), and any manifest overrides. When using `bootWar`, layout/launchers differ from JAR, so verify against the actual artifact.

### 11.3. Running the Artifact Itself

```bash
java -jar build/libs/launcher-demo-1.0.0.jar --server.port=8091
```

Test the `GET /ping` endpoint as in section 3. This is crucial when `bootRun` and `bootJar` are intentionally configured with different main classes: local `bootRun` success does not prove the executable JAR chose the right main class.

## 12. Common Errors

| Symptom | Possible cause | How to check / fix |
| --- | --- | --- |
| `bootJar` cannot determine main class | Multiple `main` classes exist or entry point is not in the main source set | Set `springBoot.mainClass` to the exact fully qualified class |
| `bootRun` runs a different main than the JAR | Separate `tasks.named('bootRun')` override exists | Compare `bootRun` and `bootJar` config, check `Start-Class` |
| `ClassNotFoundException` on `java -jar` | Wrong package/class name or class was not compiled/packaged | Verify source path, package, and `jar tf` |
| `bootJar` succeeds but no HTTP endpoint responds | JAR uses a console main; or missing web dependency/config | Check `Start-Class` and test running the exact artifact |
| `bootBuildImage` fails to run | Docker daemon unreachable, builder/buildpack or plugin error | Check Docker and task logs; verify `bootJar` first |
| `bootWar` is missing | Gradle `war` plugin not applied | Enable `war` on the module actually packaging a WAR |
| `bootRun` missing in a library module | Module does not apply Spring Boot/Java plugin | Identify the application module; do not force a library to become an app |
| Set `spring.main.class` in YAML yet JAR picks wrong main | Confused Spring runtime config with Gradle entry point | Use `springBoot.mainClass` or `bootJar.mainClass` |
| `--args` not included in deployed JAR | `--args` applies only to **that `bootRun` invocation** | Pass arguments on `java -jar`/container startup |
| Changed `archiveFileName` and CI cannot find JAR | Pipeline artifact path still uses the old name | Synchronize the exact output filename and path |
| `bootTestRun` does not run unit tests | It runs a test main class, not the JUnit test task | Use `./gradlew test` and `useJUnitPlatform()` when needed |
| Local JVM differs from production | Java toolchain, Gradle JVM, and runtime JDK differ | Check `java -version`, `./gradlew --version`, and image/JAR runtime |
| Manually set `Main-Class` = application class | Accidentally replaced Spring Boot archive launcher | Configure `mainClass`; inspect `Main-Class` and `Start-Class` |

## 13. Configuration and Testing Checklist

- [ ] Identify which class is the production entry point, with its exact **fully qualified** Java package name.
- [ ] If multiple main classes exist, set `springBoot.mainClass` on the application project.
- [ ] Only override `bootRun.mainClass`, `bootJar.mainClass`, or `bootWar.mainClass` when tasks **genuinely need different entry points**.
- [ ] Test during development with `bootRun`; verify packaged JAR behavior with `bootJar` and `java -jar`.
- [ ] Pass application args via `--args` or `args`; pass JVM settings via `jvmArgs`/`systemProperty` for their intended purpose.
- [ ] Distinguish `bootJar` from plain `jar` and `bootBuildImage` from `bootRun`.
- [ ] If packaging as WAR, verify the `war` plugin and deployment requirements instead of just renaming the file.
- [ ] In multi-project builds, invoke tasks with the proper Gradle project path and do not apply the Boot plugin indiscriminately to pure libraries.
- [ ] Run `./gradlew tasks --all`, `bootJar --dry-run`, an actual build, and inspect `jar tf` / manifest.
- [ ] Confirm `Start-Class` is right, endpoints/console output are right, and CI collects the right artifact.

**Remember:** `springBoot.mainClass` is the **project-level default entry point**; `bootRun.mainClass`, `bootJar.mainClass`, and `bootWar.mainClass` are **task-level overrides**. `bootRun` runs from the classpath, `bootJar`/`bootWar` builds an executable archive, and `bootBuildImage` builds an image from the artifact. Inspecting the deployed artifact itself is the most reliable way to know whether the final main class is right.

## References

- [Spring Boot 3.3 Gradle Plugin — Running Your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Gradle User Manual — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
# Comparing Running from an IDE vs. Running with Build Tools in Spring Boot

## 1. Purpose and Scope

When developing with Spring Boot, the same application can be started in several ways:

1. Clicking **Run/Debug** on the class with `public static void main(String[] args)` in IntelliJ IDEA, Eclipse/STS, or VS Code.
2. Invoking the **Spring Boot Maven Plugin** via `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`).
3. Invoking the **Spring Boot Gradle Plugin** via `./gradlew bootRun` (Windows: `gradlew.bat bootRun`).
4. Packaging with Maven/Gradle and running `java -jar` on the executable JAR.

The first three ways usually serve the development loop; the fourth verifies the packaged deliverable, which is closer to how a JAR is deployed on a server or inside a container. All of them can start the same `@SpringBootApplication`, but **run configuration, Java version, classpath, profiles, environment variables, working directory, and pre-run build steps** may differ.

This guide aims to **compare behaviors and diagnose differences**, without assuming either the IDE or the command line is always better. Practical goal: after importing a project from Spring Initializr, you can run the same example in both the IDE and the terminal, and ensure the application receives the exact same configuration inputs.

## 2. Full Comparison Table

| Criterion | IDE running Java `main` directly | Maven `spring-boot:run` | Gradle `bootRun` | Executable JAR `java -jar` |
|---|---|---|---|---|
| Where invoked | IDE Run Configuration | Terminal / IDE Maven panel | Terminal / IDE Gradle panel | Terminal / container |
| Compiled source required? | The IDE may compile internally or delegate before running | The Maven plugin prepares class output per lifecycle/goal | The task graph usually runs compile/resources prerequisites | **Requires a pre-packaged JAR** |
| Runtime classpath | Class/module outputs and libraries resolved by the IDE | Output classes/resources and corresponding Maven dependencies | Default `sourceSets.main.runtimeClasspath` | Contents and dependencies packaged inside the executable JAR |
| Typical class output | `out/...`, `target/classes`, or `build/classes/...` depending on IDE delegation | `target/classes` | `build/classes/java/main` and `build/resources/main` | Inside the JAR |
| Run Configuration | Main class, module, VM options, program args, env, cwd | Goal and plugin parameters/properties | Task, `--args`, task config, env | Java/JVM options and app arguments |
| Debug | Direct Debug button and breakpoints | Attach remote debugger via JVM arguments or launch config | `bootRun --debug-jvm` or configured debug options | `java -agentlib:jdwp=... -jar ...` |
| HotSwap/restart | IDE debugger/compilation and devtools if present | Recompile and devtools if present | Recompile and devtools if present | Typically does not support a dev loop from a classpath directory |
| Best suited for | Editing code, setting breakpoints, inspecting objects | Verifying behavior via Maven, sharing the same plugin in CI | Verifying behavior via Gradle, using unified tasks | Testing the released artifact |

**Important note:** "Run from IDE" only describes the UI trigger. Many IDEs offer an option to **delegate build/run to Gradle or Maven**. When delegation is enabled, clicking Run in the IDE may actually execute a build-tool task or goal under the hood. Check the Run/Build logs and the "Build and run using..." setting to see which process is actually being used.

## 3. Execution Mechanics: Compiler, Classpath, and JVM

### 3.1. Running in an IDE Does Not Skip the Build

Application classes still need to be compiled into bytecode. The IDE can:

- Run its own internal compiler after resolving Maven/Gradle dependencies.
- Invoke Maven/Gradle according to delegation settings to compile and run.
- Reuse valid previously compiled output if configured to do so.

A Run Configuration typically specifies **main class**, **module/classpath**, **JRE/JDK**, **VM options**, **program arguments**, **environment variables**, and **working directory**. If the imported project is out of sync with `pom.xml` or `build.gradle`, the IDE classpath may **differ** from the build tool's classpath.

In an IDE, choosing the class containing `@SpringBootApplication`'s `main` usually produces a launch equivalent to invoking Java with a classpath of classes and dependencies:

```text
java [JVM options] -cp [classes + resources + dependency jars]
     com.example.demo.DevRunApplication [application arguments]
```

This is a **conceptual model**, not a copy-pasteable command line, because `[classes + resources + dependency jars]` must be resolved and properly escaped by the IDE.

### 3.2. Maven `spring-boot:run` Uses Class Output

The Spring Boot Maven Plugin provides the `spring-boot:run` goal to compile and run the application **in place**, usually from exploded classes/resources and dependencies without packaging a JAR first:

```bash
./mvnw spring-boot:run
```

While the application is running, the goal typically holds the terminal until you stop the application with `Ctrl+C`. The Maven Wrapper guarantees the Maven version declared by the project is used, if configured properly; the plugin version comes from the POM/parent.

In Maven, `spring-boot:run` is a **plugin goal**, distinct from the Maven lifecycle phase `package`. Running `./mvnw spring-boot:run` is not equivalent to `./mvnw package`: `package` builds the artifact, whereas it does not start the server by default. If used in a project without the Spring Boot Maven Plugin or where the plugin cannot be resolved, the goal will fail.

### 3.3. Gradle `bootRun` Uses `main`'s `runtimeClasspath`

The Spring Boot Gradle Plugin adds the `bootRun` task when paired with the Java plugin:

```bash
./gradlew bootRun
```

`bootRun` is a task of type `BootRun`, extending `JavaExec`. By default, it uses the **runtime classpath of the `main` source set**, consisting of compiled classes, resources, and runtime dependencies. Prerequisite tasks such as `classes`/compile/resources are scheduled by Gradle's task graph. `bootRun` **does not require creating `bootJar` beforehand**.

Gradle tracks task inputs/outputs and may skip certain compile tasks as `UP-TO-DATE`. However, `bootRun` is a process-launching task: skipping compilation because it is up-to-date **does not mean the application is not started**.

To run from the root of a multi-module build, target the specific module's task:

```bash
./gradlew :orders-api:bootRun
```

This example only applies if `settings.gradle` includes the `:orders-api` project and the Boot plugin is applied to that module. Do not assume `bootRun` always exists at the root.

### 3.4. `java -jar` Uses the Packaged Artifact

With Maven:

```bash
./mvnw clean package
java -jar target/dev-run-demo-0.1.0-SNAPSHOT.jar
```

With Gradle:

```bash
./gradlew bootJar
java -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar
```

The JAR paths are examples matching the project's group/name/version in the hands-on section. The actual file depends on `finalName`, `archiveFileName`, classifier, and plugin configuration; inspect `target/` or `build/libs/` to confirm.

**Only an executable JAR properly packaged by Spring Boot runs under this model.** A regular Java library JAR missing an entry point or runtime dependencies cannot run standalone on its own. In Spring Boot, Maven `spring-boot:repackage` or Gradle `bootJar` handles packaging the executable archive as configured.

A packaged JAR captures a snapshot of classes and resources at build time. Editing source files after creating the JAR **does not change the existing JAR file**. To see edits under `java -jar`, rebuild the artifact and restart.

## 4. Java 17+ Example: One Application Running Three Ways

Create a project named `dev-run-demo` with Spring Initializr, choosing Java 17 (or a valid JDK for your Boot version), Maven **or** Gradle, and the **Spring Web** dependency. Below are the shared source files; choose **one** build tool matching your project.

### 4.1. Main Application Class

File `src/main/java/com/example/demo/DevRunApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevRunApplication {
    public static void main(String[] args) {
        SpringApplication.run(DevRunApplication.class, args);
    }
}
```

This is the entry point for the IDE, `spring-boot:run`, `bootRun`, and the manifest inside the executable JAR. When running from the IDE, choose Run/Debug on `DevRunApplication.main`; when running with Maven/Gradle, the plugin can auto-detect the main class if the project has a single suitable main class.

### 4.2. Controller for Observing Configuration

File `src/main/java/com/example/demo/ModeController.java`:

```java
package com.example.demo;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ModeController {
    private final Environment environment;

    public ModeController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/mode")
    public String mode() {
        return "mode=" + environment.getProperty("app.mode", "unset");
    }
}
```

Spring injects `Environment` via the constructor because it is a framework-provided bean. The controller is in the same package as `DevRunApplication`, so it falls within `@SpringBootApplication`'s default component scan scope.

File `src/main/resources/application.properties`:

```properties
spring.application.name=dev-run-demo
app.mode=base
server.port=8080
```

File `src/main/resources/application-dev.properties`:

```properties
app.mode=dev
```

When the **`dev` profile is not enabled**, the HTTP response body at `GET /mode` is:

```text
mode=base
```

When `dev` is enabled, Spring Boot loads the profile-specific configuration and `app.mode=dev` from the profile file overrides the base value, so the response body is:

```text
mode=dev
```

That is the **response body**, not the entire server stdout: startup logs also depend on the Spring Boot version, logger, and environment configuration. Tools like `curl -s` may not print a trailing newline after the response.

### 4.3. Gradle Groovy DSL (Choose if Project Uses Gradle)

`settings.gradle`:

```groovy
rootProject.name = 'dev-run-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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
}
```

Here both the Spring Boot and dependency-management plugins are applied, so the corresponding BOM is imported and the Web starter needs no separate version. A real project may use different plugin versions matching its wrapper/JDK; the versions above ensure consistency for the example.

Run:

```bash
./gradlew bootRun
```

Once the server reports it is ready, in another terminal:

```bash
curl -s http://localhost:8080/mode
```

The response body is `mode=base`. After stopping the run with `Ctrl+C`, enable the `dev` profile and run again:

```bash
./gradlew bootRun --args="--spring.profiles.active=dev"
```

The response body is now `mode=dev`. `--args` supplies **application arguments** to the `bootRun` task, not JVM options for the Gradle daemon.

### 4.4. Maven POM (Choose if Project Uses Maven)

A minimal yet complete `pom.xml` for running the example:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>dev-run-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

With the Java source structure from Sections 4.1–4.2 and a valid Maven Wrapper, run:

```bash
./mvnw spring-boot:run
```

Enable the `dev` profile using the **Spring Boot Maven Plugin** property:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

If your shell or Maven version handles quoting differently, wrap `-Dspring-boot.run.profiles=dev` in quotes. On Windows, use `mvnw.cmd`. The endpoint responds according to the active profile, matching the Gradle path.

**Do not mix `pom.xml` and `build.gradle` just to run the same example.** A repository might contain both build scripts, but learners should pick one primary build system and understand that it dictates dependency versions, the compiler, and the classpath.

### 4.5. Running the Same Example Directly in the IDE

After **importing the Maven/Gradle project** into your IDE and waiting for dependencies to sync:

1. Select the class `com.example.demo.DevRunApplication`.
2. Create an **Application/Spring Boot Run Configuration** with that main class and the right module.
3. Choose a compatible JDK, such as JDK 17.
4. Set the working directory to the project root containing `pom.xml` or `build.gradle` for easy comparison.
5. Leave program arguments empty to see `mode=base`, or add `--spring.profiles.active=dev` to see `mode=dev`.
6. Click **Run** or **Debug**; open `http://localhost:8080/mode`.

IDE menu names and build/delegation policies vary across versions. What matters is the **actual configuration**, not the button name.

The Java project above requires Spring Boot libraries on the classpath; you cannot simply run `javac DevRunApplication.java` with a bare JDK. The `java -jar` examples only run after a build has produced the executable JAR.

## 5. Three Parameter Types Very Easily Put in the Wrong Place

### 5.1. Application Arguments

These are passed into `String[] args`, and Spring Boot processes options in `--key=value` format.

**IDE:** Program arguments field:

```text
--spring.profiles.active=dev --server.port=8081
```

**Gradle:**

```bash
./gradlew bootRun --args="--spring.profiles.active=dev --server.port=8081"
```

**Maven:** either use the profiles shortcut, or pass command-line arguments to the Spring Boot Maven Plugin:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=8081
```

**JAR:**

```bash
java -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar --spring.profiles.active=dev --server.port=8081
```

The JAR path in the last command corresponds to the Gradle variant in this guide. If using Maven, change it to `target/dev-run-demo-0.1.0-SNAPSHOT.jar` after packaging. When `server.port=8081` is set, use `http://localhost:8081/mode`; when unset, the example uses 8080.

### 5.2. JVM Options

JVM options such as `-Xmx512m` or `-Dapp.mode=dev` are processed by the **application's JVM** and usually appear **before the main class or before `-jar`**:

```bash
java -Xmx512m -Dapp.mode=dev -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar
```

In an IDE, enter `-Xmx512m -Dapp.mode=dev` under **VM options**, not Program arguments. For Gradle `bootRun`, you can configure:

```groovy
// Snippet added to build.gradle in a project with the Spring Boot Gradle plugin.
tasks.named('bootRun') {
    jvmArgs '-Xmx512m'
    systemProperty 'app.mode', 'dev'
}
```

If you want to parameterize it, read a project property via `findProperty` or an environment variable, and avoid committing secrets in build scripts.

With Maven, use the JVM parameter of the **Spring Boot Maven Plugin**, such as `spring-boot.run.jvmArguments`. Do not assume `MAVEN_OPTS` solely modifies the application JVM: Maven runs its own process for the build, and the plugin may fork the application process.

### 5.3. Environment Variables

Spring Boot can read configuration from OS environment variables, such as `SPRING_PROFILES_ACTIVE=dev` or `APP_MODE=dev` (Spring relaxed binding translates underscore-formatted variables into the appropriate property names in this context).

**IDE:** configure under Environment variables in the Run Configuration.

**Unix/Linux/macOS (applies only to this single invocation):**

```bash
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun
```

**PowerShell:**

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\gradlew.bat bootRun
```

The PowerShell environment variable here persists for the shell session until changed or removed. When comparing results, ensure the IDE, shell, and CI receive the exact same values. For secrets, use appropriate security mechanisms; avoid printing credentials in logs or committing them in `application.properties`.

### 5.4. Equivalence Mapping Table by Goal

| Goal | IDE Run Config | Maven plugin | Gradle task | JAR |
|---|---|---|---|---|
| Enable `dev` profile | Program args `--spring.profiles.active=dev` | `-Dspring-boot.run.profiles=dev` | `--args="--spring.profiles.active=dev"` | `--spring.profiles.active=dev` after JAR |
| Change server port | Program args `--server.port=8081` | `-Dspring-boot.run.arguments=--server.port=8081` | `--args="--server.port=8081"` | `--server.port=8081` after JAR |
| Set JVM system property | VM options `-Dapp.mode=dev` | `spring-boot.run.jvmArguments` or plugin system properties | `bootRun.systemProperty(...)` | `-Dapp.mode=dev` before `-jar` |
| Set heap | VM options `-Xmx512m` | Plugin `jvmArguments` | `bootRun.jvmArgs(...)` | `-Xmx512m` before `-jar` |
| Change environment | Env vars | Shell env / plugin env configuration | Shell env / `bootRun.environment` | Shell env / container env |
| Debug | IDE Debug | Remote JDWP of the app JVM | `bootRun --debug-jvm` | `-agentlib:jdwp=...` before `-jar` |

**Do not mix flags** between Maven `-Dspring-boot.run.*` and Gradle `--args`. Also do not place `-Dspring.profiles.active=dev` in a Gradle project property slot expecting it to automatically become an application JVM property.

## 6. Classpath and Resources: The Source of Many Differences

### 6.1. Development Classpath Differs from Packaged JAR

In an IDE/`spring-boot:run`/`bootRun`, the application typically runs directly from compiled directories and dependency JARs:

```text
IDE (depends on delegation)  out/... or target/classes or build/classes/...
Maven plugin                 target/classes + runtime dependencies
Gradle bootRun               build/classes/java/main + build/resources/main + runtime dependencies
Packaged Boot JAR            BOOT-INF/classes + BOOT-INF/lib in executable JAR
```

These paths are **common conventions**, not guarantees for every customized build. A file existing under `src/main/resources` is not necessarily present in the runtime output if resource processing has not run or excluded it.

In Spring Boot, resources like `application.properties`, templates, and static files are normally loaded from the classpath. If the IDE copies them to a different output directory or Gradle/Maven filters resources by custom rules, runtime behavior can differ even when Java code has not changed.

### 6.2. Dependency Scope Also Matters

- Gradle `implementation` and `runtimeOnly` participate in the runtime classpath where appropriate; `testImplementation` is only for the test classpath.
- Maven `compile` and `runtime` scopes contribute at runtime; `test` scope normally does not belong to the main application's runtime classpath.
- An IDE may pick an unexpected module/classpath or test runtime setup. If only the IDE succeeds because of a test-only dependency, fix the **dependency scope** and verify with the build tool rather than adding libraries manually in the IDE.
- Maven profiles (build profiles) and Spring profiles (runtime config) are **two distinct concepts**. Maven's `-Pdev` does not mean `spring.profiles.active=dev` unless the POM wires them together; Gradle's `-Pdev` is a project property and likewise does not enable a Spring profile on its own.

### 6.3. Working Directory and Relative Paths

A file outside the classpath opened via a relative path, such as:

```java
Path path = Path.of("config/local-data.csv");
```

will be resolved relative to the **JVM's working directory**, not the location of the Java file. The IDE may use the module root while the terminal is at the repository root; Maven/Gradle plugins may have different defaults or explicit configurations. Hence a file path may work under one launch method and fail under another.

To read resources packaged inside the JAR, use a classpath resource:

```java
try (InputStream in =
        DevRunApplication.class.getResourceAsStream("/config/template.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing classpath resource");
    }
    // Read bytes from InputStream; do not assume the resource has a File path.
}
```

This is an **illustrative snippet** that must be placed in a method handling checked exceptions/`IOException` properly and importing `InputStream`. `getResourceAsStream` works with resources packaged on the classpath/JAR; do not confuse a resource inside a JAR with a file on the filesystem.

## 7. Java Version, Compiler Options, and Project Synchronization

IDEs have at least two Java settings that are easy to confuse:

- **The JDK used by the IDE to build/run the project** (project SDK, module SDK, Run Configuration JRE).
- **The JDK used by the build tool**: Maven runtime/Toolchains or Gradle daemon/toolchain.

For instance, Gradle `java.toolchain.languageVersion = 17` selects the appropriate compiler/toolchain for tasks; the JVM running the IDE application could still be JDK 21 if the Run Configuration selects 21. Maven `maven.compiler.release=17` controls the compilation target but does not automatically switch `java -jar` to JDK 17.

Check in the terminal:

```bash
java -version
./mvnw -version
./gradlew --version
```

Run only the command matching the build tool actually present in the project. In the IDE, open settings to inspect the Gradle/Maven JDK and the Run Configuration JRE. `java -version` in a terminal only shows the Java used by that terminal, not whether the IDE chose the same JDK.

If **it runs in the IDE but fails to compile in CI**, inspect `--release`/`sourceCompatibility`, Java Toolchains, compiler args (`-parameters`), and annotation processors. The IDE compiler can produce different classes than the Gradle/Maven compiler when build delegation is inconsistent. Libraries using annotation processing (such as Lombok or MapStruct) especially require proper plugin and processor configuration in the build file rather than merely enabling an IDE plugin.

## 8. Debugging: IDE Button and Remote Attach

### 8.1. Direct Debugging

With an IDE Run Configuration pointing to the right main class, click **Debug** to launch the JVM with the debugger attached. Set a breakpoint in `ModeController.mode()`, call `GET /mode`, and inspect `Environment` and property values. This is the fastest path for local bug fixing.

### 8.2. Gradle `bootRun --debug-jvm`

`bootRun` is a `JavaExec` task, so it supports:

```bash
./gradlew bootRun --debug-jvm
```

By Gradle `JavaExec` default configuration, the application JVM suspends and waits for a debugger on port **5005**. Create a Remote JVM Debug configuration in your IDE to attach to `localhost:5005`, then call the endpoint and verify the breakpoint. The port and suspend behavior can be customized via `JavaExec/BootRun`'s `debugOptions` when needed.

**Distinguish the two flags:** `--debug-jvm` on the `bootRun` task targets the application JVM, whereas `-Dorg.gradle.debug=true` debugs the **Gradle build process/daemon** for debugging build logic. They are not equivalent. Never expose a debugger port to untrusted networks.

### 8.3. Debugging Maven `spring-boot:run`

With the Maven Boot Plugin, configure JDWP for the **application JVM** via `spring-boot.run.jvmArguments`. A local-only example on a JVM supporting the corresponding syntax:

```bash
./mvnw spring-boot:run "-Dspring-boot.run.jvmArguments=-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
```

The JVM will wait for the IDE remote debugger to attach. If your OS command-line parser or shell uses different quoting rules, configuring plugin parameters in the POM or an IDE Run Configuration is easier to manage. Open the debugger locally only when needed and close it after testing.

### 8.4. Debugging an Executable JAR

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 \
     -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar
```

On Windows, enter the command on a single line (without `\` line continuations). When debugging an artifact, use source code from the exact version/commit that built the JAR so breakpoints match line numbers.

## 9. Edit-Run Loop Speed: HotSwap and Spring Boot DevTools

### 9.1. JVM HotSwap

During a Debug session, the IDE can replace bytecode inside certain methods without restarting the JVM. This capability depends on the JVM, compiler, type of change, and IDE configuration. Structural class changes, bean registrations, annotations, or resource edits usually exceed normal HotSwap capabilities.

### 9.2. Spring Boot DevTools

If a project declares `spring-boot-devtools`, this module can automatically restart the development application when it detects **classpath output changes**. Gradle example:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

These are **snippets added** to a build that already has Spring Boot dependency management; they are not full build files. The Spring Boot Gradle Plugin defines `developmentOnly` for development-time dependencies and omits them from the executable archive by default per plugin configuration. With Maven and DevTools, verify how the plugin excludes devtools during repackaging, which by default keeps devtools out of the release deliverable.

Key point: **DevTools watches the classpath, not every edited `.java` file directly**. You must update the compiled output for the restart mechanism to detect changes:

- Eclipse/STS may auto-build on save depending on configuration.
- IntelliJ IDEA may require **Build Project** or enabling appropriate auto-build/delegation settings.
- While running `bootRun` or `spring-boot:run`, you can recompile in another terminal/IDE to update the classpath while the server session stays up.
- For static resources/templates, depending on DevTools settings and resource locations, the browser may reload without restarting the entire context.

**Do not conclude "Running from IDE always hot-reloads while Gradle does not."** Both can use DevTools if the module is on the runtime classpath, output is updated, and the launcher supports it. Packaged production JARs are not expected to auto-restart from local source files like the development classpath.

### 9.3. When Should You Stop and Restart?

If you update bean definitions, dependencies, compiler flags, build scripts, Java version, runtime VM options, or Spring profiles, it is usually best to **stop the old process and start it again** to ensure the new classpath and configuration are applied. A running Gradle/Maven task does not re-evaluate the entire build script when sources change.

## 10. Choosing the Right Launch Method for Each Goal

| Need | Suitable Choice |
|---|---|
| Set breakpoints and fix code quickly | Direct IDE Debug with the exact module/classpath |
| Reproduce a bug from CLI so teammates can rerun easily | `./mvnw spring-boot:run` or `./gradlew bootRun` using the wrapper |
| Verify compile, dependency, and plugin tasks per official build | Maven/Gradle Wrapper running the appropriate goal/task |
| Verify packaging, JAR manifest, and archive resources | Build `package`/`bootJar`, then run `java -jar` |
| Run a multi-module application | Gradle `:app-module:bootRun` or Maven `-pl` after identifying the module |
| Verify different profile/port/env configurations | Run each launcher with the **same** app args, VM args, env, and cwd |
| Reproduce CI behavior | Use the wrapper, JDK/toolchain, and CI scripts matching the CI environment |
| Asking "which runs fastest?" | IDEs are often convenient for debugging; build-tool tasks can leverage cache/incremental compilation; actual speed depends on the project with no fixed winner |

An IDE is a UI and debugger tool; Maven/Gradle is the source of truth for dependencies, compilers, and tasks. An effective team practice keeps **reproducible build configuration**, using the IDE for productivity without hiding secret logic solely inside personal Run Configurations.

## 11. Controlled Comparison Experiment

Run this on the project from Section 4, allowing only **one application instance** on port 8080 per round.

**Round A – Default IDE.** Import the project, run `DevRunApplication` without enabling any profile, and call `http://localhost:8080/mode`. Record the body `mode=base`.

**Round B – Default Build Tool.** Stop the IDE run. Use `./gradlew bootRun` **or** `./mvnw spring-boot:run`. Call the same endpoint; expect `mode=base`.

**Round C – Equivalent Configuration.** Stop Round B. In the IDE, set Program arguments to `--spring.profiles.active=dev` and run; response is `mode=dev`. Stop the IDE. Run `./gradlew bootRun --args="--spring.profiles.active=dev"` or `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev`; response is also `mode=dev`.

**Round D – Packaged Artifact.** Stop the server. Build the JAR using Maven `package` or Gradle `bootJar`. Run `java -jar <actual-jar-path> --spring.profiles.active=dev` with the exact filename, call the endpoint, and expect `mode=dev`.

**Round E – Intentional Difference.** Select the `dev` profile in the IDE but omit it when running from CLI. The differing results `mode=dev` and `mode=base` are **caused by the configuration inputs**, not because Spring Boot behaves differently inside an IDE.

Conditions for a fair comparison: same Git commit, dependency versions, compatible JDK, freshly compiled sources, relevant environment variables, working directory, profiles, JVM options, and the same database/external services if any.

## 12. Diagnosing When the IDE Runs Fine but Maven/Gradle Fails

Follow this order from the specific error back to the configuration source:

### 12.1. Compilation Errors or Missing Classes

Symptoms: `package ... does not exist`, `cannot find symbol`, `ClassNotFoundException`, annotation processor errors.

- Check whether the IDE has imported/synced Maven/Gradle; are the classpath and module correct?
- Check dependency scopes in `pom.xml` or `build.gradle`; avoid dependencies added manually only inside the IDE.
- Check the JDK/toolchain, Lombok/MapStruct processors, and generated sources.
- Run the build from the wrapper to observe the real compiler error, e.g., `./gradlew compileJava` or `./mvnw compile`.
- The IDE successfully running old compiled classes does not prove new sources compile cleanly.

### 12.2. IDE Runs Fine, CLI Reports Missing Environment

Symptoms: missing database URL, access token, or cloud credentials; Spring fails to resolve placeholders.

- Check Environment variables in the IDE Run Configuration.
- Check terminal shell variables, properties, and Spring profiles across each launcher.
- If the IDE uses an `.env` plugin that loads files automatically, shells do not load `.env` files automatically on every OS.
- Do not copy secrets into Git to "sync" two launchers; configure a secret manager or env variables per environment.

### 12.3. Port Already in Use

Symptoms: `Web server failed to start. Port 8080 was already in use` or a similar bind exception.

- Usually caused by an IDE instance still running when you start `bootRun`/`spring-boot:run`.
- Stop the old instance or pass `--server.port=8081` for the second run.
- Identify the process occupying the port before killing it; avoid assuming a source code bug.
- Test the endpoint on the exact declared port.

### 12.4. CLI Runs Fine, IDE Cannot Find the Main Class

- Verify `main(String[] args)` and `@SpringBootApplication` reside in the selected module.
- Select the proper Run Configuration, module classpath, and project SDK.
- Reimport/sync Gradle/Maven so the IDE picks up generated sources, dependencies, and updated compiler settings.
- In a multi-module project, only the application module needs the Spring Boot plugin and appropriate entry point; library modules do not have a main class by default.

### 12.5. One Launch Method Reads a File, Another Reports It Missing

- Check the actual working directory instead of guessing.
- Check whether the file is opened via a filesystem relative path or as a classpath resource.
- Ensure `processResources` ran and the resource is in the output/JAR without being excluded or mis-filtered.
- If the file lives outside the JAR, pass an explicit absolute/external config path when deploying.

### 12.6. Different HTTP Responses Despite Using the Same Source

- Compare Spring profiles, `app.mode`, property source precedence, program args, system properties, and environment variables.
- Check whether the dependency graph has different versions due to an unsynced IDE or a different build profile.
- Check whether the JAR was rebuilt after the latest source edit.
- Check external services and databases used in each environment rather than blaming every issue on the launcher.

## 13. Clarifying Common Misconceptions

**"Running in an IDE means you don't need Maven/Gradle."** The IDE still relies on build metadata for dependencies and compiler settings. Some IDEs even delegate Run directly to the build tool.

**"`bootRun` always builds a JAR before running."** Incorrect; it runs from the `main` source set's runtime classpath and does not require `bootJar`.

**"`spring-boot:run` is a packaging command."** Incorrect; `package`/repackage handles packaging. `run` starts the app in place.

**"`java -jar` is the only way to run Spring Boot properly."** Spring Boot supports running from IDEs and build plugins; the paths mainly differ in how classpaths, processes, and configuration are assembled.

**"Enable the Spring `dev` profile with `-Pdev`."** That is build-tool syntax (Maven profile or Gradle project property) and is not automatically equivalent to `--spring.profiles.active=dev`.

**"JVM options and program args can go anywhere."** `-Xmx` and `-D` JVM options must reach the application JVM in the right position; `--spring.*` are application arguments processed by Spring Boot.

**"With DevTools, saving immediately triggers a restart."** It watches classpath output: the editor/IDE/build task must update the actual compiled classes/resources.

**"Seeing different results in the IDE vs. CLI must be a compiler bug."** Profiles, env, cwd, ports, dependency scopes, and stale classes are far more common causes; compare each input first.

**"`java -jar` after editing source code will use the new code."** A packaged JAR does not update automatically. You must rebuild and restart it.

**"Debugging Gradle with `-Dorg.gradle.debug=true` hits controller breakpoints."** That flag targets the Gradle build process. To debug the `bootRun` application JVM, use `--debug-jvm` or IDE Debug / remote attach to the right process.

## 14. Checklist Before Confirming Two Launch Methods Are Equivalent

1. **Build source:** same Git commit and no stale classes or old JARs causing confusion.
2. **JDK:** compatible compiler target, Java runtime, and Gradle/Maven toolchain.
3. **Classpath:** dependencies in proper configurations/scopes; IDE synced; no accidental test dependencies leaked into the main app.
4. **Entry point:** same `DevRunApplication` or explicitly configured main class; in multi-module builds, the right app module selected.
5. **Application arguments:** same `--spring.profiles.active`, `--server.port`, and other options.
6. **JVM options:** same required values like `-Xmx` and `-D...` passed to the **application JVM**.
7. **Environment:** same required variables and secure secret sources.
8. **Working directory:** relative paths resolved from the intended location.
9. **Resources:** `application*.properties` and resources copied/packaged properly without differing filtering.
10. **Lifecycle:** clear awareness of whether running IDE direct, Maven goal, Gradle task, or packaged JAR; clear stop and restart steps.
11. **Debug/restart:** target the right process; do not confuse compiler cache/HotSwap/DevTools with container restarts.
12. **Observation:** measure the same HTTP endpoint, appropriate log levels, resolved config, and test results before concluding.

### Official Documentation

- [Spring Boot 3.5 — Running Your Application](https://docs.spring.io/spring-boot/3.5/reference/using/running-your-application.html)
- [Spring Boot — Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot — Running Your Application with Maven](https://docs.spring.io/spring-boot/maven-plugin/run.html)
- [Spring Boot — Developer Tools and Automatic Restart](https://docs.spring.io/spring-boot/reference/using/devtools.html)
- [Gradle JavaExec — JVM debugging](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html)

**Takeaway:** IDE, Maven `spring-boot:run`, and Gradle `bootRun` can all launch Spring Boot during development; equivalence depends on having the **same main class, classpath, JDK, profile, JVM options, environment, and working directory**. `java -jar` tests the packaged artifact itself. When results diverge, compare these factors in order before editing code.
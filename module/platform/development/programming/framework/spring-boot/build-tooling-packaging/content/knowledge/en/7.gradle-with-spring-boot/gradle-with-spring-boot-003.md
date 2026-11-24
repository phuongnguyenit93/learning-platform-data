# Applying the org.springframework.boot Plugin Together with java or war

## Lesson Objectives

In Gradle, `org.springframework.boot` is the plugin that adds the ability to **run** and **package Spring Boot applications**. However, applying that plugin alone does not fully configure a Java or WAR project: it needs to be paired with an appropriate language/packaging plugin. This lesson focuses on two important combinations:

- `org.springframework.boot` + `java`: compiles Java, runs tests, runs the application with `bootRun`, and packages an **executable JAR** with `bootJar`.
- `org.springframework.boot` + `war`: uses the Servlet web application model, packages an **executable WAR** with `bootWar`, and can be prepared for deployment to an external servlet container.

After this lesson, you will be able to identify which plugin creates which task, read `build.gradle`/`build.gradle.kts` accurately, build a minimal Java Spring Boot app using both approaches, understand `providedRuntime`, inspect actual JAR/WAR outputs, and fix common errors when switching from JAR to WAR.

**Example scope:** the build files below pin `Spring Boot 3.3.13` and `io.spring.dependency-management 1.1.7` to illustrate a specific published combination, alongside Java 21 and a compatible Gradle 8.x. This is not a version prescription for other projects. Spring Boot 4.x introduces changes in some starters and tooling requirements; when using another version, consult the documentation for your **project's exact version**. Do not copy versions from examples into an active project without checking compatibility.

## 1. What Does Each Plugin Contribute to the Project?

Three plugins are often mentioned together, yet **their roles are not the same**:

| Plugin | What does it provide? | Does it produce a Spring Boot executable archive on its own? |
| --- | --- | --- |
| `java` (Gradle core) | `sourceSets`, `compileJava`, `processResources`, `classes`, `test`, `jar`, `assemble`/`build` lifecycle, Java classpaths | No; standard `jar` only packages classes/resources |
| `war` (Gradle core) | Extends Java, adds `war`, `src/main/webapp` layout, `providedCompile`, and `providedRuntime` | No; the `war` task creates a standard WAR |
| `org.springframework.boot` | Reacts to Java/WAR plugins, adding `bootRun`, `bootJar` or `bootWar` plus Boot-specific tasks/settings | Yes, **when combined with the appropriate plugin** |
| `io.spring.dependency-management` (optional) | Manages library versions via a BOM, can use `spring-boot-dependencies` matching the Boot plugin | No; manages dependencies, does not package |

**Core relationship:**

```text
plugins { id 'org.springframework.boot' ... }
        |
        +-- applied together with java
        |       +-- compileJava / test / jar (Gradle)
        |       +-- bootRun / bootJar (Spring Boot)
        |       \-- assemble -> bootJar
        |
        \-- applied together with war
                +-- war automatically applies java
                +-- compileJava / test / war (Gradle)
                +-- bootWar (Spring Boot)
                \-- assemble -> bootWar
```

The diagram shows **the primary added/registered tasks**, not the full DAG of every Gradle/Spring Boot version. Because `war` builds on `java`, combining it with Boot may still expose `bootJar` and Java tasks. Inspect your own project's task graph, and explicitly invoke `bootWar` when you want a WAR artifact. Do not conclude "applying war definitely deletes bootJar".

### "Applying a Plugin" vs. "Declaring Without Applying"

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.13'
    id 'java'
}
```

Both plugins are **applied to the current project**. By contrast:

```groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
}
```

`apply false` only declares the plugin/version so it can be applied elsewhere; it **does not create** `bootJar` for the current project. This is useful at the root of a Gradle multi-project build, where library modules can use just `java-library` while only application modules need the Spring Boot plugin.

Applying the Spring Boot plugin **by itself** has very little effect. It does not infer "this project must be a Java JAR or WAR" without the corresponding base plugin.

## 2. The `org.springframework.boot` + `java` Combination: Executable JAR

### Complete `build.gradle` Example (Groovy DSL)

Suppose we create a Gradle Groovy DSL project with `settings.gradle`:

```groovy
rootProject.name = 'demo'
```

The `build.gradle` file:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **usable Java Spring Boot 3.3.x configuration** if the Gradle Wrapper, JDK, and network/library repository meet the requirements. The project needs application code (section 5); a build script alone does not generate a controller or `main` class.

Part-by-part explanation:

1. `id 'java'` applies compilation conventions, `main/test` source sets, and creates basic Gradle tasks.
2. `id 'org.springframework.boot' version '3.3.13'` applies the Spring Boot Gradle plugin to **this project**. Seeing `java`, Boot creates `bootJar` and `bootRun`.
3. `io.spring.dependency-management` manages versions based on the `spring-boot-dependencies` BOM; in this model you can omit versions on managed starters. This plugin is **distinct** from the Spring Boot plugin and must be applied, or replaced with Gradle's `platform(...)` mechanism.
4. `toolchain` requests Java 21 for configured Java tasks; it does not guarantee the machine runs Gradle itself on that exact JDK if the Gradle daemon is configured separately.
5. `implementation`, `testImplementation`, `testRuntimeOnly` specify dependencies for main code and tests. JUnit Platform must be configured on the `test` task as shown.
6. `rootProject.name` affects the default archive name along with `version`; filenames can change if the project configures `archiveBaseName` or `archiveVersion`.

In Gradle **Kotlin DSL**, the equivalent way to apply the three plugins is:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}
```

This is a **snippet** of `build.gradle.kts`: `group`, `version`, `java`, `repositories`, `dependencies`, and `tasks.test` must also be declared equivalently if creating the entire project from scratch. Do not mix Groovy syntax such as `id 'java'` into a `.gradle.kts` file.

### Which Tasks Are Created When `java` Is Present?

| Task | Meaning | Key notes |
| --- | --- | --- |
| `compileJava` | Compiles Java source in the `main` source set | Created by Gradle Java plugin, not Boot alone |
| `processResources` / `classes` | Processes resources, gathers compiled classes | Usually upstream dependencies of packaging tasks |
| `test` | Runs tests (if configured and tests exist) | Belongs to Java plugin; Spring Boot test starter provides test libraries |
| `jar` | **Plain** JAR, does not bundle all runtime dependencies | With modern Boot versions, typically gets the `plain` classifier |
| `bootJar` | Executable JAR containing app code and runtime dependencies | Added by Spring Boot plugin when `java` is applied |
| `bootRun` | Runs Spring Boot from the main source set and runtime classpath | Used during development, does not require building a JAR first |
| `assemble` / `build` | Packaging lifecycle / verification + packaging | Boot wires `bootJar` into `assemble`; `build` also runs `check`/`test` |

With Spring Boot 3.3, **`bootJar` is not synonymous with the `jar` task**. By default, tasks may produce both the Boot archive and the plain archive, so you may also see `-plain.jar`. Do not mistake `-plain.jar` for an executable Boot JAR.

### Why Can `bootJar` Run via `java -jar`?

A typical executable Boot JAR organizes its contents roughly like this:

```text
demo-0.0.1-SNAPSHOT.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/demo/DemoApplication.class
│   │   └── com/example/demo/HelloController.class
│   └── lib/
│       └── ... runtime dependency jars ...
└── org/springframework/boot/loader/...
```

The tree is **illustrative**; the actual file list depends on versions and dependencies. Boot provides the launcher, manifest, and classpath for nested JARs inside. A plain JAR contains only the project's classes/resources; calling `java -jar` on `-plain.jar` may lack `Main-Class` or the dependencies required to start.

You can inspect it with `jar tf` (a JDK tool) after building:

```bash
./gradlew bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

The path may differ if you changed `rootProject.name`/`version`/classifier. The filename must be taken from **the actual output in `build/libs`**, not guessed when running on a different project.

## 3. The `org.springframework.boot` + `war` Combination: Executable WAR

### When to Choose WAR?

Choose WAR when a **Servlet** web application must be deployed to an external servlet container such as a compatible Tomcat, or when deployment workflows require a `.war` file. If you only need a standalone Spring Boot service, an executable JAR is usually simpler because the application carries its own embedded server.

**A WAR deployed to an external servlet container requires more than just changing the JAR extension to WAR.** You need the Gradle configuration, a Servlet initializer class, and the right runtime dependency scope.

### Complete `build.gradle` Example for WAR (Groovy DSL)

`settings.gradle` can remain `rootProject.name = 'demo'`. The build file:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Intent of the example:**

- `id 'war'` applies the **Gradle War plugin**, which implicitly applies the Java plugin as well. Listing `id 'java'` explicitly is not required, though projects can do so if desired by convention.
- Seeing `war`, the Spring Boot plugin creates `bootWar`; it also sees `java` pulled in by `war` and creates Java-related tasks.
- `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` is appropriate for **Spring Boot 3.3.x** when preparing a WAR for an external servlet container. Other Spring Boot lines may change starter/runtime names; use coordinates matching your actual version.
- `providedRuntime` keeps dependencies available at runtime and in tests without placing them into `WEB-INF/lib` for the external container. A Spring Boot executable WAR places them in `WEB-INF/lib-provided` so it can still run via `java -jar`.
- `testImplementation` and `testRuntimeOnly` serve testing; they do not become application runtime libraries.
- This WAR setup is for Spring MVC/Servlet. **Pure WebFlux applications using the reactive Netty model are not supported for traditional WAR deployment** in Spring Boot's guides.

In Kotlin DSL, the corresponding plugin application and WAR dependencies are:

```kotlin
plugins {
    war
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

This is a **Kotlin DSL snippet**, not a complete file: when building a full project you still need `group`, `version`, `java toolchain`, `repositories`, and test configuration. Do not use Groovy syntax `providedRuntime '...'` in `build.gradle.kts`.

### How `war` and `bootWar` Tasks Differ

| Task | Source | Result |
| --- | --- | --- |
| `war` | Gradle War plugin | Standard WAR conforming to Java web application conventions |
| `bootWar` | Spring Boot plugin when `war` is applied | **Executable Boot WAR** with launcher and appropriate layout |
| `jar` | Gradle Java plugin (applied by `war`) | Standard JAR if the task runs and is not disabled |
| `bootJar` | Spring Boot plugin combined with Java plugin | May be present because `war` also applies Java; check the task graph before deciding to disable |

A standard WAR organizes `WEB-INF/classes`, `WEB-INF/lib`, and web resources. `bootWar` builds an executable WAR with additional components enabling `java -jar` and `WEB-INF/lib-provided` when `providedRuntime` is used.

```text
demo-0.0.1-SNAPSHOT.war
├── META-INF/
├── WEB-INF/
│   ├── classes/
│   │   ├── com/example/demo/DemoApplication.class
│   │   └── com/example/demo/HelloController.class
│   ├── lib/
│   │   └── ... application runtime jars ...
│   └── lib-provided/
│       └── ... embedded servlet container runtime jars ...
└── org/springframework/boot/loader/...
```

This is a **conceptual structure**; exact files depend on dependencies and the Spring Boot version. The `WEB-INF/lib-provided` directory prevents the external container from loading duplicate JARs that it already provides, while the executable WAR can still use them when launched with `java -jar`.

### Why Not Use `compileOnly` Instead of `providedRuntime`?

`compileOnly` only puts a library on the compile classpath; it **does not put the library on the runtime/test runtime classpath** in the way the WAR plugin does. When a web application needs the embedded servlet container during integration tests, `compileOnly` can cause context loading / web server initialization failures. `providedRuntime` is designed for dependencies **provided by the external container at deployment time**, while Spring Boot places them into `WEB-INF/lib-provided` of the executable WAR.

Do not mistakenly put all application dependencies into `providedRuntime`: libraries the application genuinely needs that the container does not supply must remain in `WEB-INF/lib` via `implementation`/runtime dependencies.

## 4. When Deploying a WAR to an External Container, `SpringBootServletInitializer` Is Required

A `main` class using `SpringApplication.run` enables standalone execution. When an external container starts the application from a WAR, it needs a way to bootstrap Spring through the Servlet mechanism. Spring Boot provides `SpringBootServletInitializer` for this case.

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(DemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

**This is a complete Java class within a Spring Boot project with declared dependencies**, compiled via `./gradlew classes` or `./gradlew build`. You cannot run `javac DemoApplication.java` standalone without providing Spring Boot dependencies on the classpath.

- `@SpringBootApplication` marks the root/bootstrap configuration and enables component scanning.
- `main` is used for standalone startup (`bootRun`, `java -jar`).
- `configure(SpringApplicationBuilder)` is used when deploying a WAR and an external servlet container initializes the application via `SpringBootServletInitializer`.
- `DemoApplication.class` specifies the configuration source for both launch modes; the package/class name in the file path must match what you declare.

To observe verifiable HTTP output, create `src/main/java/com/example/demo/HelloController.java`:

```java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
```

With Boot 3.3.x `spring-boot-starter-web`, these two classes create a Servlet Spring MVC application with a `GET /hello` endpoint. If run standalone on the default port without configuring a custom context path, accessing `http://localhost:8080/hello` returns the exact response body:

```text
Hello from Spring Boot
```

This is **the response from the example controller**, not the full stdout/logs of Gradle or Spring Boot. When deploying the WAR to an external Tomcat, the URL depends on **the context path chosen by the container** (e.g., `/demo/hello`), the port, and container settings; it does not default to `/hello` like standalone execution.

**Note:** a `DemoApplication` class extending `SpringBootServletInitializer` still works for both executable JAR and WAR. Extending the initializer primarily matters when **deploying a WAR to an external servlet container**, and is not required for pure JAR applications.

### Testing Context Startup

Create `src/test/java/com/example/demo/DemoApplicationTests.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

The `./gradlew test` command runs tests as configured in the build script. `contextLoads` verifies Spring application context startup; it **does not automatically test all endpoints or business flows**. Having proper `providedRuntime` avoids missing the servlet runtime on the test classpath when using WAR.

## 5. Running, Packaging, and Inspecting Outputs

### Running via the Wrapper and Viewing Actual Tasks

From the root directory containing `gradlew` and the build script:

```bash
# Check the Gradle Wrapper version, not the Spring Boot version
./gradlew --version

# View available tasks after plugins are applied
./gradlew tasks --all

# View task descriptions
./gradlew help --task bootJar
./gradlew help --task bootWar

# Preview tasks Gradle plans to run without executing them
./gradlew build --dry-run
```

If only `java` is applied, `help --task bootWar` may report that the task is not found. If `war` is applied, inspect the actual task list because `war` applies Java and some JAR tasks may coexist.

Execution commands for the **JAR project**:

```bash
./gradlew clean test
./gradlew bootRun
# In a separate terminal window, after the app starts:
curl http://localhost:8080/hello
# Stop the application with Ctrl+C, then:
./gradlew bootJar
```

When `bootRun` runs in the current terminal, it blocks the terminal until the application stops; `curl` in the example requires a separate terminal. If port 8080 is already used by another app or the project configures another port, read the logs and configuration rather than assuming the endpoint is always on port 8080.

Execution commands for the **WAR project**:

```bash
./gradlew clean test
./gradlew bootWar
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
java -jar build/libs/demo-0.0.1-SNAPSHOT.war
```

The `java -jar` line targets the **executable WAR created by Spring Boot**. A standard WAR generated by the `war` task will not necessarily run this way. The example archive name is based on `rootProject.name=demo` and `version=0.0.1-SNAPSHOT`; check the actual filename in `build/libs`.

On Windows PowerShell, run equivalently:

```powershell
.\gradlew.bat clean test
.\gradlew.bat bootJar
.\gradlew.bat bootWar
jar tf .\build\libs\demo-0.0.1-SNAPSHOT.war
java -jar .\build\libs\demo-0.0.1-SNAPSHOT.war
```

Invoke only `bootJar` or `bootWar` corresponding to the artifact you want to test. These tasks **do not require** a project to always produce both artifact types.

### Verification Levels: Task Exists, Build Succeeds, and App Runs

Distinguish between:

1. `./gradlew tasks --all` showing `bootWar`: proves the task is registered in the Gradle model, not that the WAR configuration works at execution time.
2. `./gradlew bootWar` succeeding and producing `build/libs/*.war`: proves packaging finished, not that deploying to an external container succeeds.
3. `jar tf` showing `WEB-INF/classes`, `WEB-INF/lib`, and (with provided runtime) `WEB-INF/lib-provided`: proves the actual archive layout.
4. `java -jar ...war` starting and the endpoint responding: verifies the executable WAR in embedded mode.
5. Deploying the WAR to a **compatible Servlet container** and calling the endpoint through the container-assigned context path: only this proves traditional deployment works.

Gradle/Spring Boot logs vary by Java, dependencies, configuration, and environment. Do not copy a simulated `BUILD SUCCESSFUL` line as evidence if you have not actually run the build.

### Two Archives Appearing Together in `build/libs`

When the Spring Boot plugin is applied, the archive created by `bootJar`/`bootWar` usually has no classifier; the regular archive created by `jar`/`war` may carry a `-plain.jar` or `-plain.war` suffix. This is **the convention of modern plugin versions**, not a build error or a requirement to delete one of them.

Check `jar tf`, the task that produced the file, and the classifier before picking an artifact to run/deploy. Do not manually rename file extensions. If you only want the Boot artifact and clearly understand publishing needs, you can disable the plain task, for example:

```groovy
tasks.named('jar') {
    enabled = false
}
```

This is an **optional Groovy DSL snippet**, to be used only after checking task dependencies, library/publishing requirements, and native image needs. Do not disable `jar` indiscriminately: some native image or publishing workflows require the regular JAR. For WAR projects, disabling `bootJar` or `war` also requires careful review of `assemble` and other task interactions before editing.

## 6. Properly Converting an Application from JAR to WAR

Suppose a Spring MVC application currently uses `java` and builds an executable JAR. When converting to a WAR for an external Tomcat, follow this sequence:

1. **Confirm deployment intent:** the target is a Servlet container compatible with the application's Spring Boot/Jakarta API versions. If the system runs pure WebFlux on Netty, do not apply this Servlet WAR recipe.
2. **Replace `id 'java'` with `id 'war'`** in `plugins` (or apply `war` alongside Java if the project has a specific reason). Keep the Spring Boot plugin and appropriate dependency management.
3. **Add `providedRuntime` for the embedded servlet container** matching your Spring Boot line. For the 3.3.x Tomcat example: `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'`.
4. **Have the application class extend `SpringBootServletInitializer`** and override `configure(...)` as in section 4, while keeping `main` for standalone execution.
5. **Run `./gradlew test` then `./gradlew bootWar`**, inspect `build/libs`, `jar tf`, and the `WEB-INF/lib-provided` layout.
6. **Test running the executable WAR** with `java -jar`, then test **deploying the WAR on an external container** and check the endpoint using the real context path.
7. **Check the task and artifact used by CI**: deployment scripts must pick the `*.war` from the `bootWar` task, not mistakenly grab `-plain.war` or `-plain.jar`.
8. **Update operational documentation**: ports, context paths, configuration environments, and external servlet container runtimes can differ from the embedded model.

During this conversion, `HelloController` code does not need to change just because JAR became WAR; the key changes lie in **plugins, packaging, the servlet starter, and the external container entry point**.

## 7. Easily Misunderstood Relationships and Limitations

### Does the Spring Boot Plugin Manage All Dependencies Automatically?

**Do not infer that from `id 'org.springframework.boot'` alone.** According to the documentation, the Spring Boot Gradle plugin can be paired with:

- `io.spring.dependency-management`: when applied together with the Spring Boot plugin, the corresponding `spring-boot-dependencies` BOM is imported automatically, letting you omit versions on BOM-managed dependencies.
- **Gradle native BOM**: declaring `platform(...)` or `enforcedPlatform(...)` with the appropriate BOM coordinates. `platform` provides constraints/recommendations; resolution may still pick another version when required. `enforcedPlatform` is stricter and should be used with caution.

Example Groovy DSL **snippet** using native BOM without `io.spring.dependency-management`:

```groovy
dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

This is a dependency version management mechanism; **it does not create `bootJar`/`bootWar` by itself**. To know the final resolved version of a library, use `./gradlew dependencies --configuration runtimeClasspath` and `./gradlew dependencyInsight --dependency ... --configuration runtimeClasspath` rather than only reading the BOM.

### Spring Boot Plugin Version Differs from Gradle Version

`id 'org.springframework.boot' version '3.3.13'` pins the **Spring Boot plugin version**. Meanwhile, the `distributionUrl` line in `gradle/wrapper/gradle-wrapper.properties` pins the **Gradle version** executed. `java.toolchain` specifies the **Java language version for applicable compilation/test tasks**. They must be compatible, but none replaces another.

Spring Boot 3.3.13 requires Java 17+ and supports Gradle 7.5+ in the 7.x line or Gradle 8.x per that version's documentation. Gradle 8.5 can run on Java 21. This explains the Java 21/Gradle 8.5 example here; real projects on other versions must verify their own compatibility conditions.

### Switching to `war` Does Not Deploy to a Container Automatically

The `bootWar` task packages an archive. Running inside an external servlet container still depends on:

- Compatible Servlet/Jakarta support level of the target container.
- A valid `SpringBootServletInitializer` class and initialization configuration.
- Properly classifying the embedded container as `providedRuntime` to prevent library conflicts.
- The WAR name/context path, environment resources, security config, ports, and container logging.
- Actual testing on the exact container type and configuration being deployed.

Do not conclude from `./gradlew bootWar` succeeding that the WAR file is guaranteed to run on any version of Tomcat.

### When to Use Only `java-library`?

If a module only contains a shared Java library with no runnable `main` application, `java-library` and a plain JAR are usually more appropriate. Do not apply `org.springframework.boot` to every module in a repository just to share dependency versions; BOM management can be separated from applying the Boot plugin. When a module has no `main` class, `bootJar` may fail to locate an entry point if you try to package it as an executable app.

## 8. Quick Comparison Table: JAR vs. WAR

| Criterion | Boot + `java` | Boot + `war` |
| --- | --- | --- |
| Base Gradle plugin | `java` | `war` (implicitly includes `java`) |
| Main executable archive | `bootJar` | `bootWar` |
| Regular archive | `jar` | `war` |
| Artifact extension | `.jar` | `.war` |
| Default build path | `build/libs/` | `build/libs/` |
| Application classes | `BOOT-INF/classes` | `WEB-INF/classes` |
| Runtime libraries | `BOOT-INF/lib` | `WEB-INF/lib` |
| "Provided" embedded servlet runtime | Usually not separated | `WEB-INF/lib-provided` when using `providedRuntime` |
| Run via `java -jar` | Yes, with Boot executable JAR | Yes, with Boot executable WAR |
| Deploy to external servlet container | Not via traditional WAR model | Yes, when Servlet/initializer/dependency conditions are met |
| Recommended default for standalone microservices? | Usually suitable and simple | Use when an external WAR/Servlet container is required |

**There is no "WAR is better than JAR" in every case.** Choose the archive type according to your operational model; the base plugin determines the structure and tasks, while the Spring Boot plugin adds the corresponding executable capability.

## 9. Common Errors and How to Self-Diagnose

| Symptom | Common cause | How to verify or fix |
| --- | --- | --- |
| `Task 'bootJar' not found` | Spring Boot plugin not applied or missing `java`/base plugin | Check `plugins`, `apply false`, correct module, run `tasks --all` |
| `Task 'bootWar' not found` | Only `java` applied, missing Gradle `war` | Add `id 'war'` to the application module, re-run Gradle import |
| `bootJar` cannot find main class | Project has no `main(String[])` or task is running on a library module | Add main class, check package/`mainClass`, select the right project |
| `bootWar` exists but fails to deploy | Missing `SpringBootServletInitializer`, incompatible external container, wrong classpath | Check `configure`, WAR layout, server logs, and Servlet compatibility |
| `NoClassDefFoundError` when running the app | Dependency missing at runtime or placed in wrong configuration | Check `runtimeClasspath` and `jar tf` on the archive |
| `providedRuntime` does not exist | Gradle `war` plugin not applied | Check `plugins` and module configuration |
| WAR lacks embedded Tomcat on `java -jar` | Wrong dependency/packaging or non-Boot WAR task | Check `WEB-INF/lib-provided`, invoke `bootWar` |
| Extra `-plain.jar` / `-plain.war` appears | Regular and Boot packaging tasks both ran | Check which task created each file and classifier; pick the Boot artifact for `java -jar` |
| Plugin reported not found | Wrong plugin version/repository, network error, incompatible Gradle Wrapper | Check `settings.gradle` plugin repositories, Plugin Portal, wrapper, and resolution errors |
| Versionless starter causes error | Missing BOM/dependency management mechanism | Apply `io.spring.dependency-management` or matching platform BOM |
| `bootRun` works but WAR fails | Differences between embedded mode and external container | Test real WAR deployment, read servlet container logs and context path |
| Build passes but endpoint returns 404 | Missing controller, wrong path/port/context path | Check `@RestController`, `@GetMapping`, and actual application URL |
| WAR deploys but classes conflict | Embedded servlet container still inside `WEB-INF/lib` or incompatible server/API | Check `providedRuntime` and WAR contents |
| Using `compileOnly` instead of `providedRuntime` breaks tests | Library is absent from the test runtime classpath | Use `providedRuntime` properly for the servlet container |
| Boot applied to both library and application modules | Library has no `main` yet receives executable archive tasks | Apply Boot plugin only to application modules; keep `java-library` on libraries |

### Example Error-Checking Sequence

If `./gradlew bootWar` reports the task is not found, **first** confirm the `war` plugin is applied and you are in the right module. If the task exists but the build fails on Java, read the compiler error/JDK version. If the build produces a WAR but `java -jar` fails, verify you are running the executable WAR and that `WEB-INF/lib-provided` is properly populated. If `java -jar` succeeds but external Tomcat fails, investigate `SpringBootServletInitializer`, Servlet API compatibility, context path, and container configuration.

This layered approach prevents changing plugin versions arbitrarily when the root cause lies in Java code or the deployment environment.

## 10. Hands-On Practice: Proving the Effect of Each Plugin

### Exercise 1 – Java JAR

Create a Groovy DSL project with `id 'java'`, the Spring Boot plugin, and a BOM mechanism. Add the two Java classes from section 4 and the `contextLoads` test. Perform:

1. Run `./gradlew tasks --all`, noting `bootRun`, `bootJar`, `jar`, and `test`.
2. Run `./gradlew test`, explaining how tests are created by the Gradle Java plugin and use test dependencies.
3. Run `./gradlew bootJar`, open `build/libs`, and use `jar tf` to find `BOOT-INF/classes`/`BOOT-INF/lib`.
4. Launch with `java -jar` and call `/hello`. If `-plain.jar` is present, compare its structure against the Boot executable JAR.

### Exercise 2 – WAR and Servlet Container

On a separate copy/branch of the project, replace `java` with `war`, add `providedRuntime` for the servlet container, and keep the main class extending `SpringBootServletInitializer`.

1. Run `./gradlew tasks --all`, noting `bootWar`, `war`, and whether `bootJar` is present.
2. Run `./gradlew bootWar`, inspect `WEB-INF/classes`, `WEB-INF/lib`, and `WEB-INF/lib-provided` inside the WAR.
3. Run `java -jar build/libs/demo-0.0.1-SNAPSHOT.war` (using the exact filename you built), calling `/hello` in embedded mode.
4. If you have a **compatible** servlet container, deploy the WAR and call the endpoint through the container-selected context path. Compare the two execution modes.
5. Answer: why does `id 'war'` already have Java capabilities, why is the initializer needed, why does `providedRuntime` differ from `compileOnly`, and why is `war` not equivalent to `bootWar`?

### Exercise 3 – Explaining Configuration

Without running additional code, answer from the build file and task reports:

- If only `id 'org.springframework.boot' version '3.3.13' apply false` is present, can you use `bootJar` in that module by default? Why?
- What changes when `id 'war'` is applied to a Java Spring Boot project?
- Is `io.spring.dependency-management` responsible for packaging the executable JAR? If you remove it, how must dependency versions be managed?
- Why is seeing `-plain.jar` insufficient to conclude the build is broken?
- When the artifact runs in an external container, what requirements must be verified beyond `bootWar` succeeding?

**Pass criteria:** you can accurately state **which plugin creates which task**, run at least one Java/JAR set of exercises and one WAR build in an appropriate environment, inspect actual archive contents, and explain the difference between executable packaging and WAR deployment.

## Official Documentation

- Spring Boot 3.3 Gradle Plugin – Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot Gradle Plugin – Reacting to Other Plugins: https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html
- Spring Boot Gradle Plugin – Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot Gradle Plugin – Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot – Traditional Deployment: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Gradle – Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle – War Plugin: https://docs.gradle.org/current/userguide/war_plugin.html

**Remember:** `org.springframework.boot` adds Spring Boot tasks when it sees the corresponding base plugin; `java` and `war` determine the Java/Servlet model; `io.spring.dependency-management` or native BOM determines dependency version management. Inspect your own project's tasks, archives, and execution mode to confirm plugin application matches your goal.

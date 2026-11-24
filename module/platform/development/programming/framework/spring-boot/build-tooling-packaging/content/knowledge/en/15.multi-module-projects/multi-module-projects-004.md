# Organizing Gradle Multi-Project Builds via `settings` and `project dependency`

As a Spring Boot system grows, a single Gradle project quickly becomes hard to manage: all classes share one source set, the boundary between business libraries and runnable applications blurs, tests take longer, and dependencies get pulled into places where they are not needed. A **Gradle multi-project build** solves this by placing multiple **subprojects** inside **one build**, declared centrally in `settings.gradle` or `settings.gradle.kts`, with each subproject having its own build script and dependencies.

Two distinct operations must be separated:

- **`include('core', 'app')` in settings:** tells Gradle **which projects belong to the build** and their names/paths.
- **`implementation project(':core')` in `app`'s build script:** tells Gradle that **app consumes core's outputs/library**. It is the project dependency that enables Gradle to select artifacts/variants, build the proper classpaths, and schedule producer tasks before consumer tasks.

**Including alone does not create a dependency.** And **writing a project dependency to an un-included path** does not cause Gradle to create that project automatically. Both structure and usage relationships must be configured.

In Spring Boot, a common design uses `java-library` for the `:core` library and `org.springframework.boot` + `java` for the `:app` application. Normally, only modules that actually produce executable archives need `bootJar` or `bootWar`; library modules should produce plain JARs.

Examples throughout use **Java 17**, **Spring Boot 3.3.5**, **Gradle 8.7**, and **Groovy DSL** to present a deterministic build, without claiming these are the latest versions. Multi-project principles also apply to other versions, though plugin/JDK compatibility must be verified.

## 1. Understanding Build, Project, Subproject, and Task

A **Gradle build** can consist of:

~~~text
multi-demo/                    <- build root
├── settings.gradle            <- project list and build-level configuration
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...         <- Gradle Wrapper (if already generated)
├── core/                      <- project path :core
│   ├── build.gradle
│   └── src/main/java/...
└── app/                       <- project path :app
    ├── build.gradle
    └── src/main/java/...
~~~

The build above has a **root project** and two **subprojects**. The root project can have its own `build.gradle` to define root-level build logic, though it is **not required** for this example. `settings.gradle` defines the build hierarchy; child build scripts define plugins, dependencies, and tasks for each project.

In Gradle, **project paths** use colons:

| Project | Project Path | Example Task |
| --- | --- | --- |
| Root | `:` | `:help` |
| Core library | `:core` | `:core:jar` |
| App application | `:app` | `:app:bootJar` |
| Nested module (if included) | `:services:billing` | `:services:billing:test` |

**A project path is not a Java package.** `:core` can contain package `com.example.core`; the Java source directory structure must follow packages, whereas project paths are managed by Gradle settings.

**Projects differ from tasks:** `:app` is a project; `:app:bootJar` is a task inside that project. The leading `:` denotes an absolute path from the build root, preventing ambiguity with similarly named projects elsewhere.

### Measurable Benefits

- **Clear dependency boundaries:** `app` depends on `core`, while `core` knows nothing about `app`.
- **Graph-driven build order:** Gradle automatically builds the `core` outputs needed by `app` before `app` compiles/packages.
- **Per-module appropriate plugins:** `java-library` in `core`, Spring Boot plugin in `app`.
- **Variant-aware resolution:** the consumer receives the proper compile/runtime variant from the library project.
- **Targeted testing and building:** you can run `:core:test` or `:app:bootJar` instead of operating on everything.
- **Clean packaging:** the app's Boot archive includes the core JAR as a runtime dependency; `core` is not forced into an executable Boot application.

Multi-project builds do not automatically guarantee fast builds or good architecture. If modules have circular dependencies, rely heavily on eager cross-project configuration, or lack clear API boundaries, builds can still become complex. Both the project graph and dependency graph must be designed deliberately.

## 2. Role of `settings.gradle`: Declaring Which Projects Exist

The **`settings.gradle`** file (Groovy DSL) at the build root:

~~~groovy
rootProject.name = 'multi-demo'
include 'core', 'app'
~~~

Equivalent method-call syntax:

~~~groovy
rootProject.name = 'multi-demo'
include('core', 'app')
~~~

The two snippets are **two ways of writing the same configuration**; do not copy both. Gradle reads settings during the initialization phase to determine the build root and participating projects. With default paths, `include 'core'` maps project `:core` to directory `./core`, and `include 'app'` maps `:app` to `./app`.

**Key points to remember:**

1. `rootProject.name` sets the root project name, not a Java package name.
2. `include` adds a **project descriptor** to the build; it does not make that module a dependency of any other module.
3. Each subproject should have its own build script, such as `core/build.gradle` and `app/build.gradle`.
4. Deeply nested projects can be included using colon-separated paths.
5. Project directories must exist and be accessible. Newer Gradle versions strictly validate missing or non-writable included directories.
6. One settings file at the root defines the hierarchy; you do not need separate settings files in each child for a standard multi-project build.

### `include` vs `includeBuild`

- **`include('core')`:** adds `:core` as a **subproject within the same build**. You can use `implementation project(':core')`.
- **`includeBuild('build-logic')`:** brings in **another build** as a **composite build/included build**, typically to share build logic or substitute dependencies across builds. It does not make `:build-logic` a subproject in the sense of `include`.

A configuration using `includeBuild` belongs to a different architectural pattern; do not change `include 'core'` to `includeBuild 'core'` just to separate a library. This lesson focuses on a **single settings hierarchy** with `project(...)` dependencies.

## 3. Project Dependency: Consuming Another Project's Output

In `app/build.gradle`, the statement:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

creates a dependency from **app** to **core**. `:core` refers specifically to the Gradle project included in settings, not a Maven artifact name, not a file path, and not a package name.

Gradle uses **variant-aware dependency management**: depending on whether the consumer needs the compile classpath or runtime classpath, Gradle selects the matching outgoing variant exposed by project `:core` (typically via the Java/Java Library plugin). Hence a project dependency is more than "attaching an arbitrary JAR file".

Graph:

~~~text
settings.gradle
    rootProject = multi-demo
    include :core
    include :app
          |
          v
:app build.gradle
    implementation project(':core')
          |
          v
  Dependency graph: :app ----> :core
          |
          v
  Gradle wires the compile/runtime classpath and corresponding producer tasks
          |
          v
  :app:bootJar uses application output + runtime dependencies
~~~

**Practical consequences:**

- When compiling source in `:app` that uses a public class from `:core`, Gradle supplies core's API artifact/variant to the compile classpath.
- When the app runs/packages, Gradle supplies core's runtime variant along with appropriate runtime dependencies.
- Gradle creates the necessary task dependencies on core's output producers. You do not need to manually run `./gradlew :core:jar` before every `:app:bootJar`.
- When `core` changes, Gradle decides which tasks actually need to rerun based on inputs/outputs/variants; there is no rule that "all modules always rebuild".
- Internal dependencies of `core` are not arbitrarily leaked onto `app`'s compile classpath; the `api`/`implementation` rules of the Java Library plugin matter greatly.

### Do Not Confuse a Project Dependency with an External Module Dependency

~~~groovy
dependencies {
    implementation project(':core') // Project in the same Gradle build
    implementation 'org.springframework.boot:spring-boot-starter' // External module
}
~~~

The first line **does not require publishing core to Maven Central** before using it; Gradle knows the project and its outputs within the same build. The second line resolves an external artifact via repositories/dependency management. If project `:core` is not included, Gradle cannot resolve `project(':core')`.

Writing `implementation files('../core/build/libs/core.jar')` instead of a project dependency is an error-prone file/path dependency: it loses variant and transitive dependency information and forces manual build ordering. When the source is a Gradle subproject, use `project(...)` semantically.

## 4. Complete Hands-On Exercise: `:core` as Library, `:app` as Spring Boot Application

Objectives:

1. Create a two-module multi-project build with one settings file.
2. Module `:core` provides `GreetingService` in Java 17.
3. Module `:app` depends on `:core`, registers a bean, and calls the library in a `CommandLineRunner`.
4. Run the application with `bootRun` and then build an executable `bootJar`.
5. Prove that `core`'s class is found in `app`'s runtime without publishing `core` or manually copying JARs.

Directory structure:

~~~text
multi-demo/
├── settings.gradle
├── core/
│   ├── build.gradle
│   └── src/
│       └── main/
│           └── java/
│               └── com/example/core/GreetingService.java
└── app/
    ├── build.gradle
    └── src/
        └── main/
            └── java/
                └── com/example/app/MultiDemoApplication.java
~~~

If using the Gradle Wrapper, the root also contains `gradlew`, `gradlew.bat`, and `gradle/wrapper/`. Those are files controlling the Gradle version, not subprojects.

### 4.1. Root `settings.gradle`

~~~groovy
rootProject.name = 'multi-demo'
include 'core', 'app'
~~~

There is **not yet** any dependency between `app` and `core` here: settings only make the two projects present.

### 4.2. `core/build.gradle` — Library Project

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Because `:core` uses no external libraries in this exercise, it does not need `repositories`. If external dependencies are added later, configure repositories in `core` or centralize repositories in settings.

Why `java-library` instead of the Spring Boot plugin?

- This is a plain Java library with no `@SpringBootApplication` or entry point.
- `java-library` provides `api`/`implementation` separation along with standard Java tasks.
- `:core:jar` creates a **plain library JAR**; `core` does not need the Boot launcher or nested dependencies.
- If `core` later needs to publish an artifact for another application, the Java Library plugin is the natural foundation.

Do not apply `id 'org.springframework.boot'` to every module just because the final application uses Spring Boot. Doing so creates inappropriate `bootJar` tasks on library modules and causes distribution artifact confusion.

### 4.3. `core/src/main/java/com/example/core/GreetingService.java`

~~~java
package com.example.core;

public final class GreetingService {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Valid Java 17 code. The public `greet` method is the API consumed by `app`; the class has no Spring annotations. Bean management is handled in the `app` module to illustrate the boundary: **an ordinary Java library can still be used by a Spring Boot application through a project dependency**.

### 4.4. `app/build.gradle` — Executable Spring Boot Application

~~~groovy
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation project(':core')
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.app.MultiDemoApplication'
}

tasks.named('bootJar', BootJar) {
    archiveFileName.set('multi-demo-app.jar')
}
~~~

**Configuration breakdown:**

- `java` creates Java source sets and tasks such as `compileJava`, `test`, and `jar`.
- The Spring Boot plugin creates `bootJar` and `bootRun` when paired with the Java plugin.
- `io.spring.dependency-management` manages library versions according to the Spring Boot BOM in this sample. Another project could use Gradle's native BOM via `platform(...)` instead.
- `implementation project(':core')` is the **decisive line** allowing `app` to consume `core`'s API and runtime artifact.
- `spring-boot-starter` provides the basic Spring Boot runtime **without starting a web server**. This example is a command-line application.
- `springBoot.mainClass` configures the application entry point so the build plugin does not have to guess if multiple main classes exist.
- `bootJar.archiveFileName` fixes the executable JAR name for easy inspection, avoiding confusion with plain JARs and default classifiers.
- `repositories { mavenCentral() }` resolves `app`'s external dependencies; the project dependency `:core` does not fetch `core` from Maven Central.

Note: versions `3.3.5` and `1.1.6` are pinned for the example. Verify compatibility and support policies before applying them to a new project.

### 4.5. `app/src/main/java/com/example/app/MultiDemoApplication.java`

~~~java
package com.example.app;

import com.example.core.GreetingService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MultiDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiDemoApplication.class, args);
    }

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }

    @Bean
    CommandLineRunner showMessage(GreetingService greetingService) {
        return args -> System.out.println(
                "GREETING=" + greetingService.greet("Gradle")
        );
    }
}
~~~

**Note on module boundaries:**

- `GreetingService` is in package `com.example.core`, module `:core`. `:app`'s Java compiler sees the class thanks to `implementation project(':core')`.
- `@SpringBootApplication` in `com.example.app` scans that package and its subpackages by default; it **does not automatically scan sibling package `com.example.core`**. Thus the example creates the `GreetingService` bean via a `@Bean` method in `app` rather than expecting component scanning to find classes outside the root package.
- `CommandLineRunner` receives the bean via dependency injection and calls `core`'s public method.
- `spring-boot-starter` includes no web server; once the runner completes and the context has no other long-lived processes, the application exits.
- The filename matches the public class `MultiDemoApplication.java`, and the package matches the directory structure.

### 4.6. Inspect the Project Hierarchy

From root `multi-demo/` with the Gradle Wrapper:

~~~bash
./gradlew projects
~~~

The command shows the root project and subprojects `:core`, `:app`. Exact log wording, tree rendering, and versions in the output depend on Gradle, so no single static stdout template should be hardcoded. A valid hierarchy displays the projects matching settings.

If there is no Gradle Wrapper yet but a compatible Gradle is installed, you can run once at root:

~~~bash
gradle wrapper --gradle-version 8.7
~~~

This generates wrapper files; from then on use `./gradlew` on Linux/macOS and `.\gradlew.bat` on Windows PowerShell. Downloading the distribution/dependencies the first time requires appropriate repository network access.

### 4.7. Run the Application Using `bootRun`

~~~bash
./gradlew :app:bootRun --args='--spring.main.banner-mode=off --logging.level.root=OFF'
~~~

The line printed **by the program itself** when starting successfully:

~~~text
GREETING=Hello, Gradle!
~~~

This is not a promise that the entire terminal has only one line: Gradle/Spring Boot can still print startup/task logs. What needs verification is that `core`'s `GreetingService` class ran from `app`.

Gradle handles compiling/outputting `:core` via task dependencies and supplies it to `:app`. There is no need to run `:core:jar` manually before `:app:bootRun`.

### 4.8. Create the Executable JAR for `app`

~~~bash
./gradlew :app:bootJar
~~~

With explicit `archiveFileName`, output:

~~~text
app/build/libs/multi-demo-app.jar
~~~

Run that exact artifact:

~~~bash
java -jar app/build/libs/multi-demo-app.jar --spring.main.banner-mode=off --logging.level.root=OFF
~~~

Line printed by the application:

~~~text
GREETING=Hello, Gradle!
~~~

`bootJar` packages runtime dependencies into a Spring Boot executable archive, including the `:core` library artifact supplied via the project dependency. In the standard executable JAR layout, app classes sit in `BOOT-INF/classes` and the core JAR appears under `BOOT-INF/lib`.

Inspect with the JDK:

~~~bash
jar tf app/build/libs/multi-demo-app.jar
~~~

In the long output, look for:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/com/example/app/MultiDemoApplication.class
BOOT-INF/lib/core-1.0.0.jar
~~~

These are the **expected entries** from `:core`'s version configuration above; the archive also holds many Spring Boot libraries. If the core JAR name differs due to changing `archiveBaseName`, `archiveVersion`, or plugin configuration, check the actual name in `BOOT-INF/lib` rather than asserting a hardcoded pattern.

`jar tf` only lists **outer archive entries**; it does not automatically list classes inside the nested `core-1.0.0.jar`. To confirm Java classes are actually inside it, build `:core:jar` separately and list the file in `core/build/libs/`, or unpack the nested JAR with an appropriate tool.

### 4.9. Partial Tests and Builds

~~~bash
./gradlew :core:jar
./gradlew :core:test
./gradlew :app:test
./gradlew :app:build
~~~

The sample has no test sources yet, so `test` may report `NO-SOURCE` or equivalent. `:app:build` runs the app's lifecycle tasks and required dependencies; it does not mean every task in every subproject runs. When you want to build the entire multi-project according to conventions, invoke a task from root with matching semantics such as `./gradlew build` and inspect the actual task graph.

## 5. Why Does a Project Dependency Not Need Manual Task Dependencies?

A common mistake is trying to write:

~~~groovy
// Not needed for ordinary Java library relationships:
tasks.named('compileJava') {
    dependsOn(':core:jar')
}
~~~

This snippet is an **anti-pattern**, not part of the exercise. It hard-couples a consumer task to a specific task in another module. Meanwhile:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

expresses a **data relationship**: `app` needs `core`'s library. Gradle can automatically select the compile artifact or runtime artifact along with the producer tasks matching the variant. The task graph is inferred from dependency metadata rather than manually writing each `dependsOn` edge.

This mechanism pays off later when you change how `core` builds, add classes/resources, or change packaging. The project dependency still states the exact business/build intent: **app consumes core**.

### Variant-Aware Dependency Management

With the Java Library plugin, project `:core` typically exposes variants such as:

- **`apiElements`:** serves consumers on the compile classpath, prioritizing APIs and dependencies required by the public API.
- **`runtimeElements`:** serves consumers on the runtime classpath, containing the runtime artifact and appropriate runtime dependencies.

Gradle uses attributes/capabilities/variant selection to match consumer requirements with producer publications. Do not grab files directly from `core/build/libs` in build scripts just because you know an artifact will be generated there; doing so bypasses the rich semantic dependency model.

**No need to run `core` manually beforehand.** When `app` needs `core` outputs, Gradle wires the required task edges. Exact ordering of intermediate tasks can vary by Gradle version/caching/variants, so inspect `--dry-run` or `--info` rather than asserting a fixed log sequence.

## 6. `api` and `implementation` in a `java-library` Module

`java-library` adds API and implementation separation:

| Configuration in `core` | Can Appear on `app` Compile Classpath? | Can Appear in `app` Runtime? | When to Use |
| --- | --- | --- | --- |
| `api` | Yes (exposed to consumers) | Yes, via runtime dependencies | Another library's types appear in the public API/ABI |
| `implementation` | Not automatically exposed on consumer compile classpath | Yes, as a runtime dependency | Internal logic not exposed in the public API |
| `compileOnly` | Only for `core` compilation, not exported to `app` | Does not become a runtime dependency | Annotations or compile-only APIs |
| `runtimeOnly` | Not part of compile API | Yes, when the runtime variant is consumed | JDBC drivers, runtime integrations |
| `testImplementation` | No | Not in `app` runtime | Testing `core` itself |

These are the **default semantics of the Java Library plugin**; a build customizing variants/attributes may differ. In our simple hands-on exercise, `core` has no external dependencies, so `api` is not used yet.

### Classification Example

Suppose a public method in `core` returns an interface from SLF4J:

~~~java
// Java API illustration snippet; not a complete file.
public org.slf4j.Logger logger() {
    // Implementation can return a Logger from the logging library.
    return org.slf4j.LoggerFactory.getLogger(getClass());
}
~~~

Because `org.slf4j.Logger` appears in the public signature, the library may need to place `slf4j-api` in `api` so consumers can compile against the public API:

~~~groovy
// Illustration snippet added to core/build.gradle, not used in
// the build.gradle of the previous exercise.
repositories {
    mavenCentral()
}

dependencies {
    api 'org.slf4j:slf4j-api:2.0.16'
}
~~~

Conversely, if a library such as `commons-lang3` is only used inside a private method body in `core`, it usually belongs in `implementation`:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

These versions only illustrate clear artifact coordinates; no claim is made that they are the latest. Do not add them to the exercise with `GreetingService` because that code does not use these libraries.

**Rule:** prefer `implementation` and only use `api` when the public ABI requires types from the dependency to be exposed to consumers. Putting every dependency in `api` bloats the consumer compile classpath, increases coupling, and reduces incremental compilation benefits.

### Core API and Spring Component Scan Are Two Separate Things

A public class that `app` can compile/instantiate does not automatically become a Spring bean. In the example, `core` uses a plain Java class and `app` uses `@Bean` to register it in the Spring container. If `core` has `@Component` in a package outside `app`'s scan region, you must configure scanning/imports appropriately or use module auto-configuration; **a project dependency only puts bytecode on the classpath and does not automatically register beans**.

## 7. `settings.gradle` with Nested Directories and Project Paths

When default directories match project paths:

~~~text
multi-demo/
├── settings.gradle
├── services/
│   └── billing/
│       └── build.gradle
└── libraries/
    └── pricing/
        └── build.gradle
~~~

Settings can use:

~~~groovy
rootProject.name = 'multi-demo'
include 'services:billing'
include 'libraries:pricing'
~~~

The corresponding project paths are `:services:billing` and `:libraries:pricing`. A build script in `billing` can declare:

~~~groovy
dependencies {
    implementation project(':libraries:pricing')
}
~~~

This is a **separate configuration illustrating nested project paths**, not a continuation edit to the `:core`/`:app` exercise. Project `:libraries:pricing` must actually exist and publish a suitable artifact/variant if `billing` needs a Java library. Gradle can synthesize intermediate project descriptors for multi-level paths; keep directory and project structures consistent.

### When the Project Path Differs from the Physical Directory

Project `:core` does not always live at `./core`. Example layout:

~~~text
multi-demo/
├── settings.gradle
└── modules/
    └── shared-core/
        └── build.gradle
~~~

You can map it via the project descriptor in settings:

~~~groovy
rootProject.name = 'multi-demo'
include 'core'

project(':core').projectDir = file('modules/shared-core')
~~~

Then the dependency remains:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

Gradle uses the included **logical project path** `:core`, while taking the actual directory from `projectDir`. Do not rewrite it as `project('modules/shared-core')` thinking "path means filesystem path", because `project(...)` looks up a **Gradle project path**, not an arbitrary filesystem path.

**Do not create empty directories to mask settings mistakes.** If a project path points to the wrong directory, the build may miss needed build scripts and sources; fix the mapping properly. In Gradle 9+, including projects with missing or read-only directories is checked more strictly.

## 8. Root Build Script, Versions, and Repositories: Where Should Configuration Live?

A multi-project build can have a root `build.gradle` for shared configuration. However, the runnable two-module example in section 4 **does not need a root build script**, because:

- `settings.gradle` manages the project hierarchy.
- `core/build.gradle` manages the library.
- `app/build.gradle` manages the application.
- Only `app` needs Maven Central and the Spring Boot plugin.

When multiple modules share external dependencies, you can centralize repositories in `settings.gradle` via Gradle's `dependencyResolutionManagement`. This is an **alternative to per-module repository configuration**, not to be mixed with `repositories { ... }` inside `app` when project repos are disallowed.

### Example: Managing Repositories in Settings (Alternative Option)

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

rootProject.name = 'multi-demo'
include 'core', 'app'

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

**To use this option**, remove `repositories { mavenCentral() }` from `app/build.gradle` and from every other project build script. Otherwise, `FAIL_ON_PROJECT_REPOS` will throw an error whenever a project/plugin adds a project-level repository. The code above is a **complete alternative settings variant** replacing the file in section 4, not an unconditional snippet to append.

`dependencyResolutionManagement.repositories` controls **repositories used for project dependencies/artifacts**; it **differs from** repositories used to resolve Gradle plugins. To configure plugin sources, see `pluginManagement.repositories`.

### `pluginManagement` and How to Manage Plugin Versions

In multi-project builds, multiple Java/Boot modules may need consistent plugin versions. Settings supports:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
    plugins {
        id 'org.springframework.boot' version '3.3.5'
        id 'io.spring.dependency-management' version '1.1.6'
    }
}

rootProject.name = 'multi-demo'
include 'core', 'app'
~~~

This is **another settings option** (not a mandatory requirement). When versions are managed via `pluginManagement.plugins`, modules can declare plugin IDs inside `plugins` without repeating versions:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
~~~

`pluginManagement` manages **plugin resolution/default versions**; it does not apply the Spring Boot plugin to every subproject. Each module needing it must still declare `plugins { id '...' }`. Do not confuse Gradle's `pluginManagement` with `dependencyResolutionManagement`; they handle two different kinds of artifacts.

### Should You Write `subprojects { apply plugin: ... }`?

Configuring all subprojects from the root is possible, yet this approach tends to:

- apply the Boot plugin unnecessarily to library modules;
- make project configuration order-dependent and harder to isolate;
- obscure where build logic is owned;
- hinder optimizations like configuration cache and isolated projects.

In larger projects, consider **convention plugins** or dedicated build logic to share rules for the Java toolchain, tests, repositories, and publishing; each module then applies only the conventions it needs. Avoid arbitrary config duplication, yet **do not force all subprojects into one root closure** when their semantics differ.

## 9. Kotlin DSL: Same Structure, Different Syntax

If a project uses `settings.gradle.kts` and `build.gradle.kts`, the concepts remain unchanged. Pick **one consistent DSL** for your example; do not paste Groovy syntax into a Kotlin script.

### Root `settings.gradle.kts`

~~~kotlin
rootProject.name = "multi-demo"
include("core", "app")
~~~

### `core/build.gradle.kts`

~~~kotlin
plugins {
    `java-library`
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

In the Kotlin code block example, writing ``java-library`` uses backticks for a **Kotlin backtick identifier**; the exact line to type into the real file is:

~~~kotlin
plugins {
    `java-library`
}
~~~

When using Kotlin DSL, `java-library` is a Kotlin DSL plugin accessor enclosed in backticks, not a bare string. It differs from Groovy DSL `id 'java-library'`. The backticks here are **actual Kotlin syntax**; all other backticks in prose are merely for Markdown formatting.

### `app/build.gradle.kts`

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
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
    implementation(project(":core"))
    implementation("org.springframework.boot:spring-boot-starter")
}

springBoot {
    mainClass.set("com.example.app.MultiDemoApplication")
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("multi-demo-app.jar")
}
~~~

Java files in `src/main/java` do not change when switching Gradle DSLs. Note:

- Groovy: `implementation project(':core')`.
- Kotlin: `implementation(project(":core"))`.
- Groovy: `archiveFileName.set('...')`.
- Kotlin: `archiveFileName.set("...")`.
- Kotlin uses generic `tasks.named<BootJar>(...)`; Groovy uses `tasks.named('bootJar', BootJar)`.
- Do not leave both `build.gradle` and `build.gradle.kts` explaining conflicting setups for one project; choose one clear configuration.

## 10. Task Paths and Build Order in Multi-Project Builds

Common commands from root:

| Command | Purpose |
| --- | --- |
| `./gradlew projects` | View the hierarchy of projects included by settings |
| `./gradlew tasks --all` | List tasks recognized by Gradle, grouped by project |
| `./gradlew :core:jar` | Build the core library JAR |
| `./gradlew :app:compileJava` | Compile app along with producer tasks required by the dependency graph |
| `./gradlew :app:bootRun` | Run the Spring Boot application in app |
| `./gradlew :app:bootJar` | Package the app's executable archive |
| `./gradlew :app:build` | Run the app build lifecycle with related dependencies |
| `./gradlew build` | Request the `build` task according to Gradle's task-selection semantics across the hierarchy |
| `./gradlew :app:dependencies --configuration runtimeClasspath` | Inspect the resolved runtime dependency graph of app |

An absolute path command like `:app:bootJar` targets the task specifically in `app`. That avoids invoking same-named tasks across multiple modules unintentionally. When running from a subproject directory, Gradle also applies relative task paths and build discovery rules; using full project task paths from root is usually easier to read and reproduce in CI.

### `build` Is Not the Same as `bootJar`

- `:core:build` on a Java Library project typically includes compile, test, and jar/assemble according to its lifecycle.
- `:app:build` on a Spring Boot project typically includes tests and integrated archive tasks, though exact setup can be customized by the project.
- `:app:bootJar` only requests the executable archive and its task dependencies; it does not inherently equate to running the entire suite of tests/quality checks.
- `:app:bootRun` runs the application from the development runtime classpath rather than verifying the packaged archive.

In production pipelines, choose tasks according to QA and output needs: for instance, run tests first, then package the executable archive, and then execute an integration smoke test against the real artifact.

### View the Task Graph Without Executing Actions

~~~bash
./gradlew :app:bootJar --dry-run
~~~

`--dry-run` shows the planned task execution in many cases, yet **creates no new JARs**. Do not mistake seeing `:core:jar` in dry-run output for proof that the current archive holds the right version of core. To verify for real, run the build and inspect the archive.

### Do You Need to Call `dependsOn(':core:jar')`?

No, if `app` uses the standard `implementation project(':core')` dependency. Gradle has the project dependency metadata to construct the required task graph automatically. Only configure manual cross-project task dependencies for special tasks that cannot be represented via standard artifact/variant dependencies, while weighing coupling and maintenance.

## 11. Build Graph Differs from Dependency Graph and Package Graph

Three concepts are often conflated:

1. **Project hierarchy:** settings declares the root and subprojects, such as `:core`, `:app`.
2. **Dependency graph:** `app` uses `core`; `core` may use external libraries; Gradle resolves variants and transitive dependencies.
3. **Task graph:** when running `:app:bootJar`, Gradle selects tasks needed to create `app`'s outputs and dependent producer outputs.
4. **Artifact composition:** `bootJar` gathers application classes and runtime dependencies to assemble the executable archive.

With `include('core')` alone, Gradle knows `core` belongs to the hierarchy, yet **still does not know `app` uses `core`**. With `implementation project(':core')` alone, Gradle knows `app` uses `core`, yet still requires `:core`'s **project descriptor** in settings to resolve it.

### The Boundary Between `app` and `core` Affects Packaging

With:

~~~groovy
// app/build.gradle
dependencies {
    implementation project(':core')
}
~~~

Gradle places the project dependency on `app`'s runtime. When `bootJar` creates the executable Boot JAR, the `core` library is a typical runtime dependency and is usually placed under `BOOT-INF/lib`. `core` does not need its own executable Boot JAR. This differs from copying `core/src/main/java` source into `app/src/main/java`, which breaks module boundaries.

If `core` has resources under `src/main/resources`, the Java Library JAR includes those resources per build rules; the Boot application's classloader can read them from the nested library JAR. Do not rely on `new File("../core/src/main/resources/...")` in production, since source trees are absent from production artifacts.

## 12. Unit Tests, Integration Tests, and Per-Module Packaging

One benefit of multi-project builds is testing along boundaries:

- **Core unit tests:** verify business logic without starting a Spring context.
- **App tests:** verify bean wiring, Spring configuration, starter integration, and startup.
- **Artifact smoke tests:** run the actual executable `app/build/libs/multi-demo-app.jar` to catch packaging/classpath differences from an IDE.

If you want to add JUnit 5 tests to `core`, you can add to `core/build.gradle`:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.3'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.3'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

This is an **optional extension** for the `core` project; pinned versions are illustrative, not the latest. A Java test in `core` can look like:

~~~java
package com.example.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void greetsByName() {
        String actual = new GreetingService().greet("Gradle");
        assertEquals("Hello, Gradle!", actual);
    }
}
~~~

Place the file at `core/src/test/java/com/example/core/GreetingServiceTest.java`. Then run:

~~~bash
./gradlew :core:test
~~~

When assertions pass, the test task succeeds (Gradle output may omit detailed test results). This is not a mandatory part of the project in section 4; without adding test dependencies/files, do not expect JUnit tests to appear automatically.

For `app`, you can add the Spring Boot test starter and appropriate test annotations **inside `app` itself**, without letting `core`'s test dependencies leak into `app`. `core`'s `testImplementation` does not become a runtime dependency of `app` merely via `implementation project(':core')`.

## 13. Plugin Versions and Dependency Versions in Multi-Project Builds

There are three distinct management layers:

| Subject | Where It Can Be Managed | Example |
| --- | --- | --- |
| Project list | `settings.gradle(.kts)` | `include 'core', 'app'` |
| Gradle plugin versions/resolution | `plugins` or `pluginManagement` in settings | `org.springframework.boot` version |
| External dependency resolution | `repositories`, `dependencies`, BOM/platform, `dependencyResolutionManagement` | `spring-boot-starter`, JUnit |
| Inter-project dependency | `dependencies { implementation project(...) }` | App depends on core |

**The Spring Boot BOM does not create project dependencies.** A BOM manages versions of external modules within a configuration; if `app` needs code from `:core`, you must still declare `project(':core')` and include `:core` in settings.

**Place the Boot plugin in the right spot:** only the `app` application needs `bootJar`. Sharing Java toolchain or test conventions in root/settings can be valuable, yet do not apply the Boot plugin to `core` simply because every project sits inside one multi-project build.

### Does a Project Dependency Have a Version?

Within the same build, you write `project(':core')` rather than coordinates like `com.example:core:1.0.0`. `core`'s version can serve artifact naming/publishing or resolution metadata, yet you are not asking to download a `core` release from a repository. If modules are released independently and consumed via a Maven repo, external dependency coordinates and versioning become a different model.

### Avoiding Circular Dependencies

Do not declare:

~~~groovy
// core/build.gradle (doing this is architecturally wrong for the example)
dependencies {
    implementation project(':app')
}
~~~

when `app` already has `implementation project(':core')`. The graph `:app → :core → :app` creates a dependency cycle, which can lead to task dependency cycle errors or invalid resolution/compilation. Design modules directionally: domain/core stands independently, and applications depend on core. If two modules need each other's types, extract a shared contract into a third module instead of creating a cycle.

## 14. Diagnosis: Gradle Cannot Find a Project, Class, or Artifact

### Essential Commands

~~~bash
./gradlew projects
./gradlew :app:tasks --all
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:bootJar --dry-run
./gradlew :app:bootJar --info
jar tf app/build/libs/multi-demo-app.jar
~~~

- `projects`: checks that settings included the right modules/paths.
- `:app:tasks --all`: confirms whether `app` has `bootJar`.
- `compileClasspath`: checks that `app` compiles against `core`'s API and required external dependencies.
- `runtimeClasspath`: inspects the runtime graph, including project dependencies and matching transitives.
- `--dry-run`: previews the task graph without executing task actions.
- `--info`: analyzes why tasks ran, were skipped, or were up-to-date; logs depend on version.
- `jar tf`: inspects contents of the **generated artifact**, not just the Gradle graph.

### Common Errors Table

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| `Project with path ':core' could not be found in project ':app'` | Forgot `include 'core'`, wrong path, or wrong settings root | Check `settings.gradle` and `./gradlew projects` |
| `:core` has the right name yet has no sources/tasks | Wrong `projectDir` mapping, empty directory, or plugin not applied | Check `core`'s directory/`build.gradle` and project descriptor |
| `Could not find method implementation()` | Java/Java Library plugin not applied in module | Apply the appropriate plugin to create dependency configurations |
| `ClassNotFoundException` for core class at runtime | App lacks project dependency at runtime or wrong package output | Check `:app:runtimeClasspath`, `BOOT-INF/lib`, and runtime logs |
| App Java compiler cannot see public core class | Missing `implementation project(':core')` or class not public/wrong package | Check dependencies, imports, and `core/src/main/java` |
| App compile fails to see type from core's external API | Core used `implementation` for a type exposed in a public signature | Review `java-library` `api` vs `implementation` |
| Both `core` and `app` have `bootJar` causing wrong JAR selection | Spring Boot plugin applied to library unnecessarily | Only `app` uses Boot plugin; `core` uses `java-library` |
| `bootJar` does not exist at root | Root is not an app module | Invoke `:app:bootJar`; do not assume root has Boot tasks |
| Core builds repeat too often | Eager build logic, poorly declared inputs/outputs, or suboptimal shared config | Inspect task graph/`--info`; avoid hard-coded task dependencies |
| `:app:bootJar` runs yet artifact misses core module | Wrong configuration/variant, packaging exclusion, or opened plain JAR by mistake | Check project runtime dependency and exact Boot artifact |
| Build runs wrong task in multi-project | Invoked task name without path or from wrong directory | Use full task path `:app:bootJar` |
| Duplicate classes or resources across modules | Copied sources, broken shadow/merge, or overlapping dependencies | Inspect JAR contents, dependency graph, and module responsibilities |
| Module A depends on B and B depends on A | Project dependency cycle | Refactor dependency direction or extract a shared API module |
| Plugin resolution fails while project dependencies work | Misconfigured plugin repositories/settings or missing network | Distinguish `pluginManagement` from `repositories` for external libraries |
| IDE sees module yet Gradle CLI does not | IDE imported stale settings, opened wrong root, or needs Gradle refresh | Run `./gradlew projects` from root; reload Gradle in IDE |

### Do Not Hack Around Errors with `implementation files(...)`

If an error says "`:core` could not be found", the cause is usually in `settings.include` or the project path. Avoid patching it with:

~~~groovy
implementation files('../core/build/libs/core-1.0.0.jar')
~~~

because this bypasses the project graph, makes the build rely on a pre-existing output file, and fails to model producer tasks and transitive dependencies properly. Using a project dependency lets Gradle link modules consistently.

### Why Can the IDE Succeed While CI Fails?

An IDE may hold onto classpaths from older imports or user-configured module dependencies, whereas CI relies strictly on Gradle settings and build scripts in the repository. **Gradle CLI is the standard for verifying reproducible builds.** When discrepancies occur, run from root with the Wrapper and inspect `projects`, `dependencies`, and the task graph before modifying Java code.

## 15. Designing Spring Boot Modules in Practice

An application can scale into:

~~~text
enterprise-app/
├── settings.gradle
├── domain/           (java-library)
├── application/      (java-library)
├── persistence/      (java-library or suitable plugin)
├── web-api/          (Spring Boot executable application)
└── batch-job/        (Spring Boot executable application)
~~~

Example relationships:

~~~text
:web-api  ----> :application ----> :domain
                  ^
                  |
:persistence ------+
:batch-job ------> :application
~~~

This is a conceptual diagram, **not the single project graph every system must adopt**. Avoid letting `:domain` depend back on `:web-api`. Modules producing executable services (`:web-api`, `:batch-job`) can apply the Boot plugin; library modules should have their own appropriate plugins/build targets.

### How to Split from a Large Spring Boot Project

1. **Identify the public boundary:** which service/domain types must `app` use?
2. **Create the module directory** and appropriate `build.gradle`, e.g. `core` applying `java-library`.
3. **Add `include 'core'`** in root settings.
4. **Move code** keeping packages intact or changing them deliberately, adjusting imports/tests.
5. **Add `implementation project(':core')`** to the `app` module.
6. **Eliminate reverse dependencies** from `core` back to `app`; if needed, extract interfaces/contracts into a shared module.
7. **Verify Spring component scan/auto-configuration:** can `app` see beans from the extracted module? A project dependency only provides classpath, not guaranteed bean registration.
8. **Run tests for both modules**, build `app`'s Boot archive, inspect the JAR, and smoke test `java -jar`.
9. **Clean up duplicated configuration** gradually using convention plugins/BOM/repository management if many subprojects exist.
10. **Clarify CI/CD paths:** task `:web-api:bootJar` differs from `:domain:jar`; never accidentally publish a library as an executable application.

### Boundary Between Source Module and Deployment Unit

Multi-project does not mean deploying every module individually. In the example, `:core` is a **code module**, not a standalone runnable service. `:app` is the **deployment unit**. The app's executable archive bundles application code and needed dependencies, including `core`. When deploying `app`, you do not launch a separate Java process for `core`.

Conversely, if a project truly is an independent microservice, it has its own main class and deployment artifact; do not treat it as a `java-library` merely because it lives in the same repository.

## 16. Practical Checklist for Developers and CI

Before declaring a multi-module build healthy, verify:

- **Settings:** intentional root name, `include` lists every required module.
- **Project paths:** `:app`, `:core`, and nested paths match directories or configured `projectDir`.
- **Plugins:** libraries use `java-library`, Boot executable modules apply the Spring Boot plugin; no unnecessary plugins applied.
- **Dependencies:** `app` uses `implementation project(':core')`, without copying JARs via hard-coded paths.
- **API boundary:** `core` uses `api` only for dependencies genuinely exposed in the public ABI, and `implementation` for internal logic.
- **Build order:** Gradle resolves producer tasks automatically, with no gratuitous cross-project `dependsOn`.
- **Tests:** `core` and `app` maintain separate test scopes without leaking test-only libraries into production runtime.
- **Artifact:** `:app:bootJar` builds an executable JAR containing `core` and runtime dependencies.
- **Runtime:** actually run `java -jar` to confirm classpath, bean wiring, and deployment environment.
- **Reproducibility:** use Gradle Wrapper, consistent project repositories, and pinned plugin versions; do not rely on IDE state or stale JARs from prior builds.

## 17. Self-Check Questions

**Question 1:** Does adding `include 'core'` in `settings.gradle` automatically make `app` depend on `core`?

**Answer:** No. `include` only declares that a project participates in the build; you must add `implementation project(':core')` in `app` or an equivalent dependency relationship.

**Question 2:** How does `implementation project(':core')` differ from `implementation 'com.example:core:1.0.0'`?

**Answer:** The former consumes project `:core` within the same Gradle build, where Gradle selects outputs/variants and task dependencies automatically. The latter resolves an external module by coordinates and version from repositories/resolution mechanisms.

**Question 3:** Why should `:core` not necessarily apply the Spring Boot plugin?

**Answer:** Because `:core` is a Java library with no deployment entry point. `java-library` is the appropriate plugin for creating plain JARs and separating API/implementation; only the app needs `bootJar`/launcher.

**Question 4:** When `app` runs `:app:bootJar`, do you have to run `:core:jar` manually first?

**Answer:** Not with a standard project dependency. Gradle links producer/consumer tasks via the dependency graph/variants and builds the necessary outputs.

**Question 5:** What is the difference between `:core` and `core/src/main/java`?

**Answer:** `:core` is the Gradle logical project path. `core/src/main/java` is the physical directory for Java sources belonging to that module under default mapping.

**Question 6:** When a public method in `core` returns a type from an external dependency, should that dependency be declared as `api` or `implementation`?

**Answer:** Usually `api`, because consumers need that type to compile against the public ABI. If the type is only used internally inside method bodies, prefer `implementation`.

**Question 7:** Why don't beans in package `com.example.core` appear automatically just because `app` has a project dependency on `core`?

**Answer:** A project dependency only places classes/resources on the classpath. Spring bean registration still depends on component scanning, annotations, configuration, or explicit `@Bean` definitions; the example registers the bean in `app`.

**Question 8:** Can you use `includeBuild('core')` instead of `include 'core'` and still call `project(':core')` as usual?

**Answer:** Not by default. `includeBuild` is for composite builds/included builds with different semantics; a project dependency via `:core` requires `core` to be a subproject in the same settings hierarchy.

**Question 9:** To build the executable JAR for the right module when the root has no Boot plugin, what should you run?

**Answer:** `./gradlew :app:bootJar`, rather than blindly running `./gradlew bootJar` at the root without understanding task-selection behavior.

## 18. Official Documentation

- Gradle — [Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `settings.gradle`, `include`, project descriptors, and project dependencies.
- Gradle — [Structuring Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): subproject structure and task paths.
- Gradle — [The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): `api`, `implementation`, and outgoing variants.
- Gradle — [Declaring Dependencies Between Subprojects](https://docs.gradle.org/current/userguide/declaring_dependencies_between_subprojects.html): project dependencies and build relationships.
- Gradle — [Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement` and `RepositoriesMode`.
- Gradle — [Sharing Build Logic Between Subprojects](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): convention plugins for large builds.
- Spring Boot — [Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): `bootJar`, Java plugin, and runtime dependencies.
- Spring Boot — [Gradle Running Your Application](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun` and development classpath.

**Remember:** `settings.gradle` decides **which modules exist in the build**; `implementation project(':core')` decides **which module `app` depends on**; the Java Library plugin defines **API and runtime variants**; the Spring Boot plugin packages the **application module** into an executable artifact. To know everything truly works together, verify **project hierarchy → dependency graph → task graph → executable JAR**.
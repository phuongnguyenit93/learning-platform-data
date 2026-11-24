# Comparing Groovy DSL and Kotlin DSL Syntax for Common Gradle Configuration in Spring Boot

## 1. Goal and Prerequisites

Gradle lets you write build configuration logic using **Groovy DSL** or **Kotlin DSL**. Both DSLs control the same Gradle model: projects, plugins, repositories, dependencies, configurations, tasks, toolchains, and the build lifecycle. The main differences lie in **the scripting language, API invocation style, typing, syntax checking capabilities, and accessor mechanisms**.

This guide helps you:

- Identify the matching pairs `build.gradle`/`settings.gradle` (Groovy DSL) and `build.gradle.kts`/`settings.gradle.kts` (Kotlin DSL).
- Write two **behaviorally equivalent** configurations for a Spring Boot application using Java 17.
- Convert syntax for `plugins`, `repositories`, `dependencies`, Java toolchain, tests, task configuration, Spring Boot packaging, Gradle properties, subprojects, and version catalogs.
- Distinguish places that only change syntax from places that require understanding **Gradle data types or semantics**.
- Verify via the wrapper, task graph, and dependency resolution; avoid converting scripts with mechanical find-and-replace.

**Context:** illustrates a Java + Spring Boot project, Spring Boot Gradle Plugin `3.3.13`, Spring dependency-management plugin `1.1.7`, and Java 17. These versions are used as a comparison example, not a claim of the latest release. When working on a real repository, keep the versions approved by the project/CI and choose a compatible Gradle wrapper.

**Common misconception:** using `build.gradle.kts` **does not mean application source code must be written in Kotlin**. A Java application can still be built with Kotlin DSL; writing the application in Kotlin additionally requires the Kotlin compiler plugin and appropriate dependencies.

## 2. Same Project, Different Configuration File Extensions

| Purpose | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| Project configuration | `build.gradle` | `build.gradle.kts` |
| Root configuration, include modules | `settings.gradle` | `settings.gradle.kts` |
| Reusable build logic | `.gradle` script or Groovy plugin | `.gradle.kts` script or Kotlin plugin |
| Running tasks | `./gradlew build` | `./gradlew build` |
| Key-value properties | `gradle.properties` | `gradle.properties` (identical) |
| Version catalog | `gradle/libs.versions.toml` | `gradle/libs.versions.toml` (identical) |
| Script language | Groovy, often dynamic | Kotlin, compiled/type-checked |

Gradle **chooses the DSL by file extension**, not by the contents written inside the script. Do not rename `build.gradle` to `build.gradle.kts` and leave all Groovy syntax unchanged. Kotlin DSL requires parentheses, double quotes, type declarations, and matching Kotlin API syntax.

A multi-module build can have subprojects using two different DSLs; however, within the **same project**, you should maintain one clear primary build file to avoid two confusing configuration sources. The examples below use two independent directories for comparison, rather than placing two identically named logical scripts into the same module simultaneously.

## 3. Complete Pair of Examples with Equivalent Behavior

Goals of both configurations:

1. Build a Java 17 and Spring Boot 3.3.13 application.
2. Download `spring-boot-starter-web` and `spring-boot-starter-test` dependencies.
3. Manage dependency versions via `io.spring.dependency-management` and the Spring Boot BOM.
4. Use Maven Central; enable JUnit Platform.
5. Produce an executable JAR with `bootJar` and run `test`/`build` using the Gradle wrapper.

### 3.1. Settings Pair: Project Name

**Groovy DSL — `settings.gradle`**

~~~groovy
rootProject.name = 'demo'
~~~

**Kotlin DSL — `settings.gradle.kts`**

~~~kotlin
rootProject.name = "demo"
~~~

Both lines have the same meaning. The difference here is mainly quotation marks: Groovy accepts single-quoted strings; Kotlin uses double-quoted strings. `rootProject.name` is not the Java package name; it defines the Gradle root project name, which can affect archive naming conventions.

### 3.2. Complete Groovy Build — `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 3.3. Complete Kotlin Build — `build.gradle.kts`

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

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

**The two scripts above have the same build goal.** In the Kotlin version, `Test` is the Gradle test task type; declaring `tasks.named<Test>("test")` informs the Kotlin compiler that the task has the `useJUnitPlatform()` method. In the Groovy version, `tasks.named('test')` is handled more dynamically by the Groovy/Gradle DSL.

**Why does the Kotlin version use `languageVersion.set(...)`?** The Gradle API represents toolchain configuration with `Property<JavaLanguageVersion>`. Calling `set` is explicit and broadly compatible with Gradle 8.x. Newer Gradle versions support lazy property assignment, so you may also encounter `languageVersion = JavaLanguageVersion.of(17)` in Kotlin DSL; use a style consistent with your project's Gradle wrapper.

**Do not add versions to the two Spring Boot starters in the example:** the `io.spring.dependency-management` plugin works with the Spring Boot Gradle Plugin to import the appropriate BOM; therefore, versions managed by the BOM can be omitted. Applying the Spring Boot Gradle Plugin alone **does not mean** all dependency versions are automatically managed if the project does not use the dependency-management plugin or a Gradle BOM.

### 3.4. Shared Java Source for Both Projects

To demonstrate that the DSL does not dictate the application language, both projects use the exact same Java code below. Create `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Create `src/main/java/com/example/demo/PingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

When the project has a suitable JDK, Gradle wrapper, and repository connectivity, both scripts configure a Spring MVC application. Commands in the project directory:

~~~bash
./gradlew --version
./gradlew test
./gradlew bootJar
./gradlew build
./gradlew bootRun
~~~

On Windows PowerShell, use `.\gradlew.bat` instead of `./gradlew`. If there is no Gradle wrapper yet, you need to generate/provide the wrapper or use a compatible installed Gradle; **a build.gradle file does not generate gradlew on its own**.

With `bootRun` running on the default HTTP port 8080, a `GET http://localhost:8080/ping` request returns the exact body:

~~~text
pong
~~~

`bootJar` creates an executable Boot JAR in `build/libs` (named according to project/version/classifier). `build` normally runs both `assemble` and `check` in the Java lifecycle; calling `bootJar` alone does not guarantee that the test suite has run.

## 4. Core Syntax Conversion Rules

| Intent | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| String literal | `'demo'` or `"demo"` | `"demo"` |
| Plugin id | `id 'java'` | `id("java")` or accessor `java` |
| Plugin with version | `id 'org.springframework.boot' version '3.3.13'` | `id("org.springframework.boot") version "3.3.13"` |
| Configuration call | `implementation 'g:a:v'` | `implementation("g:a:v")` |
| Named parameters | `someMethod key: 'value'` when supported by Groovy API | `someMethod(key = "value")` when Kotlin API has matching parameter |
| Local variable declaration | `def env = 'dev'` | `val env = "dev"` or `var env = "dev"` |
| Boolean | `enabled = false` | `enabled = false` |
| Typed test task | `tasks.named('test') { ... }` | `tasks.named<Test>("test") { ... }` |
| Property API | `languageVersion = JavaLanguageVersion.of(17)` | `languageVersion.set(JavaLanguageVersion.of(17))` |
| Lazy property read | `providers.gradleProperty('env')` | `providers.gradleProperty("env")` |
| Comment | `// note` or `/* ... */` | `// note` or `/* ... */` |

This is a **table of common comparisons**, not a text converter guaranteed to work for every plugin. Kotlin DSL operates with static types: sometimes Groovy writes `foo 'bar'`, while Kotlin must locate the exact function/property, `Provider` type, or plugin-defined extension. Some Groovy dynamic methods do not have a corresponding Kotlin accessor; in those cases, use the official Gradle API or typed `configure<T>`.

**Important point about `val`:** Kotlin `val` prevents reassigning the variable itself, but the object it points to can still be a mutable `Property` changed via `set`. "Using `val`" does not mean every Gradle configuration value is immutable.

## 5. Plugins: Same Plugin ID, Different Declaration Style

### Groovy DSL

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}
~~~

### Kotlin DSL

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}
~~~

Both approaches apply the Java plugin, Spring Boot plugin, and dependency-management plugin. The Spring Boot plugin creates tasks like `bootJar` when it detects the Java plugin. Without an appropriate Java/Kotlin JVM/War plugin applied, the Spring Boot plugin alone does not guarantee a complete source model or packaging tasks.

In Kotlin DSL you may see `java` written instead of `id("java")` inside `plugins`, thanks to Gradle's typed accessors for core plugins. However, you cannot arbitrarily write a third-party plugin name as a Kotlin identifier without an accessor; `id("org.springframework.boot")` is consistent and readable.

**Do not confuse the Groovy plugin with Groovy DSL:** a project using only the Java plugin can still be configured with `build.gradle`. "Groovy DSL" is the build script language, while `id 'groovy'` is the plugin that supports **compiling Groovy source** of the application.

### Using `apply` Instead of `plugins`

In Groovy you may encounter:

~~~groovy
apply plugin: 'java'
~~~

In Kotlin:

~~~kotlin
apply(plugin = "java")
~~~

However, for standard Spring Boot configurations, prefer `plugins { ... }` because Gradle resolves plugins early and Kotlin DSL can generate **type-safe accessors** during script compilation. When a plugin is applied imperatively after accessors are generated, Kotlin DSL may not expose the expected accessors; you must then use the Gradle API by name/type appropriately.

**Do not paste both `apply(plugin=...)` and `plugins` for the same plugin without a specific reason.** One clear application method is enough for common examples.

## 6. Repositories: DSL Changes, Artifact Source Stays the Same

**Groovy DSL:**

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.example.com/releases')
    }
}
~~~

**Kotlin DSL:**

~~~kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://repo.example.com/releases")
    }
}
~~~

The repository `https://repo.example.com/releases` is an **illustrative address** with no guarantee that it exists; in a real project, replace it with a managed repository. There is no need to add this dummy repository to the two complete build scripts in section 3. Both DSLs use `mavenCentral()` identically.

Note the two separate repository systems:

- `pluginManagement.repositories` in settings specifies the source for resolving plugins in `plugins`.
- `repositories` in build or `dependencyResolutionManagement.repositories` in settings specifies the source for resolving application dependencies.

For example, to specify plugin repositories in `settings.gradle`:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
rootProject.name = 'demo'
~~~

Corresponding `settings.gradle.kts`:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
rootProject.name = "demo"
~~~

These are **two alternative settings files** replacing the minimal one in section 3.1, not content to append simultaneously after existing settings blocks. When configuring a corporate mirror, place the right type of repository in the right block: `mavenCentral()` in the dependencies block will not automatically resolve every plugin version published on the Plugin Portal.

## 7. Dependencies: Different Syntax, Same Gradle Scopes

**Groovy:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

**Kotlin:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    runtimeOnly("org.postgresql:postgresql")
}
~~~

These are two **illustrative fragments**; add PostgreSQL `runtimeOnly` only when the application actually uses JDBC/PostgreSQL. `spring-boot-starter-web`, `spring-boot-starter-test`, and `org.postgresql:postgresql` are managed by the Spring Boot 3.3 BOM in the example configuration.

| Configuration | Meaning | Notes |
| --- | --- | --- |
| `implementation` | Needed to compile/run main code | Does not automatically expose library API dependencies like `api` |
| `compileOnly` | Needed at compile time but not a runtime dependency | E.g., annotation APIs/runtimes provided by another environment |
| `runtimeOnly` | Needed only at runtime, not directly needed to compile main code | JDBC drivers are a common case |
| `testImplementation` | Used when compiling and running tests | Spring Boot test starter |
| `testRuntimeOnly` | Needed only at test runtime | When configuring a separate test engine/runtime |
| `api` | Exposes dependency to library consumers | Requires `java-library` plugin; not present in minimal Java plugin |

**Caution:** Groovy's `implementation 'g:a:v'` is not "an implementation variable assigned a string"; it is a Gradle DSL method call. Kotlin's `implementation("g:a:v")` is a function/type-safe accessor call generated by Gradle when the configuration exists.

If Kotlin DSL reports `Unresolved reference: implementation`, the cause may be that the Java/JVM plugin has not been applied yet when the script is compiled, the block is placed in the wrong location, or Gradle sync has not completed; do not try to fix it by randomly changing quotation marks.

### 7.1. Version Management: Plugin or Gradle Native BOM?

In section 3's example, `io.spring.dependency-management` together with the Spring Boot plugin imports the Spring Boot BOM. That is one popular approach. Another approach is using **Gradle native platform**; both DSLs look like this.

**Groovy — alternative example; do not use both mechanisms simultaneously just to "double up" the BOM:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**Kotlin — equivalent configuration:**

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    implementation("org.springframework.boot:spring-boot-starter-web")

    testImplementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

In this approach, import the BOM separately for `implementation` and `testImplementation` so that configurations have the proper constraints (according to each configuration's inheritance). `platform` applies the constraints provided by the BOM; **it does not strictly force every version** if there is a conflict or stronger constraint. `enforcedPlatform` has stricter forcing semantics and can affect consumers, so it should not be used as the default choice.

**A BOM does not automatically add starters to the classpath.** Regardless of which approach you choose, you must still declare the dependencies you need. If you manually declare a version incompatible with the Spring Boot BOM, inspect the dependency graph and version selection reason instead of blaming DSL syntax.

## 8. Java Version and Toolchain

**Groovy:**

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**Kotlin:**

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Both set the Java toolchain language version to 17. Gradle toolchains let the build use the configured JDK for compile/test/tasks, which can differ from the JVM running the Gradle daemon. Declaring a toolchain **does not guarantee** JVM 17 is installed or that a toolchain resolver is configured to download the JDK; check `./gradlew javaToolchains` to see which JDKs Gradle detects.

If you need to set compilation encoding:

**Groovy:**

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

**Kotlin:**

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

These are fragments added to a build script that applies the Java plugin. Groovy passes the `JavaCompile` task class as an argument to `withType`; Kotlin uses the generic `withType<JavaCompile>()`. In standard Gradle Kotlin DSL scripts, `JavaCompile` is available via default Gradle imports; in other build logic contexts, use the full class `org.gradle.api.tasks.compile.JavaCompile`.

Distinguish this from `sourceCompatibility = JavaVersion.VERSION_17` and `targetCompatibility`: those properties specify compilation/bytecode levels and do not replace selecting the right JVM/toolchain to run the compiler. With modern Gradle, toolchains are the clearer option when build environment consistency is needed.

## 9. Tests: Syntax Differences Because Kotlin Needs the Task Type

**Groovy:**

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<Test>("test") {
    useJUnitPlatform()
    testLogging {
        events("passed", "failed", "skipped")
    }
}
~~~

This snippet configures JUnit Platform and test logging events. With Spring Boot 3.3, `spring-boot-starter-test` provides JUnit Jupiter; calling `useJUnitPlatform()` tells Gradle to run JUnit 5 tests.

Why does Kotlin need `<Test>`? With an untyped `tasks.named("test")`, the task variable may only be typed as the generic `Task`, which does not expose `useJUnitPlatform()` or `testLogging`. Declaring `tasks.named<Test>("test")` specifies the exact Gradle task type. An alternative that does not require a specific task name is:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Groovy equivalent:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

`configureEach` is lazy configuration and is generally preferred over `tasks.all` when you want to avoid realizing all tasks early. If the project uses plugins that create additional test tasks, `withType<Test>()` applies to **every Test task**, whereas `named<Test>("test")` configures only the task named `test`.

**Behavior verification:** run `./gradlew test` and observe whether Gradle compiles and runs tests on JUnit Platform. Success of `bootJar` does not prove that tests ran; `build` in the Java plugin normally wires `assemble` and `check`.

## 10. Spring Boot Archive Naming: `bootJar` and Task Typing

An example customizing the executable JAR filename to `demo-app.jar`.

**Groovy:**

~~~groovy
tasks.named('bootJar') {
    archiveFileName = 'demo-app.jar'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveFileName.set("demo-app.jar")
}
~~~

The Kotlin snippet uses the fully qualified `BootJar` class name so it can be copied without adding an import. To make it cleaner, add `import org.springframework.boot.gradle.tasks.bundling.BootJar` **at the top** of `build.gradle.kts`, then use `tasks.named<BootJar>("bootJar")`.

Things to know:

- `bootJar` produces a Spring Boot executable JAR; `jar` is the standard JAR task from the Java plugin.
- Spring Boot Gradle Plugin 3.3 typically sets the `plain` classifier on the regular JAR to avoid overwriting the executable JAR. For example: `demo-0.0.1-SNAPSHOT.jar` and `demo-0.0.1-SNAPSHOT-plain.jar`.
- `bootWar` appears when the War plugin is configured. Groovy/Kotlin differ in DSL, **not in the packaging mechanism**.
- Only change `archiveFileName` on `bootJar` when a specific output name is genuinely required; ensure publishing tasks or CI reference the right artifact.

To customize the main class used by the Boot plugin, you can use:

**Groovy:**

~~~groovy
springBoot {
    mainClass = 'com.example.demo.DemoApplication'
}
~~~

**Kotlin:**

~~~kotlin
springBoot {
    mainClass.set("com.example.demo.DemoApplication")
}
~~~

These fragments are added to a script that applies the Spring Boot plugin. For a single-entrypoint example like section 3, the plugin usually detects the main class automatically; explicit declaration is helpful when there are multiple main classes or for clarity in CI. Providing the wrong package/class will prevent Boot run/packaging from finding the entry point.

### WAR and Provided Runtime

If a Servlet application needs to produce an executable WAR, apply the `war` plugin in both DSLs.

**Groovy fragment:**

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

**Kotlin fragment:**

~~~kotlin
plugins {
    id("java")
    id("war")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
}
~~~

**These two snippets are fragments illustrating the parts that differ from JAR.** When converting section 3's build example to WAR, edit the existing `plugins` and `dependencies` blocks while keeping the required project/repository/toolchain sections; do not add a second `plugins` block to a build script. If you need to deploy the WAR to an external servlet container, a Servlet application normally also needs `SpringBootServletInitializer` and a compatible container version. Simply changing the DSL does not change this runtime requirement.

## 11. Gradle Properties, Environments, and Conditional Logic

For build environment choices, read **Gradle project properties** using the Provider API, which supports lazy evaluation and the configuration cache.

In `gradle.properties` (shared by both DSLs):

~~~properties
buildFlavor=local
org.gradle.caching=true
~~~

**Groovy fragment:**

~~~groovy
def buildFlavor = providers.gradleProperty('buildFlavor').orElse('local')

tasks.register('showBuildFlavor') {
    doLast {
        println 'Build flavor: ' + buildFlavor.get()
    }
}
~~~

**Kotlin fragment:**

~~~kotlin
val buildFlavor = providers.gradleProperty("buildFlavor").orElse("local")

tasks.register("showBuildFlavor") {
    doLast {
        println("Build flavor: " + buildFlavor.get())
    }
}
~~~

Run identically:

~~~bash
./gradlew showBuildFlavor
./gradlew showBuildFlavor -PbuildFlavor=ci
~~~

With `buildFlavor=local` in `gradle.properties`, the log line printed by the custom task will be:

~~~text
Build flavor: local
~~~

Passing `-PbuildFlavor=ci` on the CLI produces the line:

~~~text
Build flavor: ci
~~~

Other Gradle log lines may appear around that output. The `orElse("local")` provider supplies a default value if the property is absent. Groovy's `def` syntax differs from Kotlin's `val`, but underneath both are `Provider<String>` from the Gradle API.

**Semantic warning:** Gradle `-PbuildFlavor=ci` is a project property; it does not automatically activate the **Spring profile** `ci` when running the application. To enable a Spring Boot profile, pass the appropriate Spring runtime configuration (e.g., application arguments) via `bootRun`/`java -jar` as configured by the build. Do not confuse a "build environment property" with a "Spring Environment profile".

For sensitive values like repository passwords/tokens, avoid hardcoding them in `build.gradle`/`build.gradle.kts` or committing `gradle.properties` with real credentials; use a team-managed secret mechanism and do not print them to logs.

## 12. Multi-Project Settings: `include`, Project Dependencies, and Root/Subproject

**Groovy `settings.gradle`:**

~~~groovy
rootProject.name = 'demo-multi'
include 'common', 'app'
~~~

**Kotlin `settings.gradle.kts`:**

~~~kotlin
rootProject.name = "demo-multi"
include("common", "app")
~~~

Both settings files define the `:common` and `:app` projects if the corresponding directories/project descriptors exist. Do not put `include("common", "app")` in `build.gradle` instead of settings: Gradle establishes the build/project tree via settings before evaluating build scripts.

If `app` needs to use `common`:

**Groovy `app/build.gradle` fragment:**

~~~groovy
dependencies {
    implementation project(':common')
}
~~~

**Kotlin `app/build.gradle.kts` fragment:**

~~~kotlin
dependencies {
    implementation(project(":common"))
}
~~~

Here `project(":common")` represents a **project dependency**, not Maven module coordinates on the Internet. `:common` must be included by `settings` and provide an appropriate variant/artifact (typically via the Java/Java Library plugin). A library-only project can use `java-library` without applying the Spring Boot plugin or building a Boot executable archive.

Example running tasks on the `app` module:

~~~bash
./gradlew :app:bootJar
./gradlew :app:build
~~~

If the root build mixes Groovy/Kotlin DSL across subprojects, each file's syntax must match its own extension; the task path `:app:bootJar` remains the same.

## 13. Version Catalog Shared Across Both DSLs

Gradle can group dependency/plugin coordinates in `gradle/libs.versions.toml`. The TOML file **does not change syntax between Groovy or Kotlin build scripts**.

Example `gradle/libs.versions.toml`:

~~~toml
[versions]
springBoot = "3.3.13"
springDependencyManagement = "1.1.7"

[plugins]
springBoot = { id = "org.springframework.boot", version.ref = "springBoot" }
springDependencyManagement = { id = "io.spring.dependency-management", version.ref = "springDependencyManagement" }

[libraries]
commonsLang3 = { module = "org.apache.commons:commons-lang3", version = "3.14.0" }
~~~

Groovy version using aliases:

~~~groovy
plugins {
    id 'java'
    alias(libs.plugins.springBoot)
    alias(libs.plugins.springDependencyManagement)
}

dependencies {
    implementation libs.commonsLang3
}
~~~

Kotlin version:

~~~kotlin
plugins {
    id("java")
    alias(libs.plugins.springBoot)
    alias(libs.plugins.springDependencyManagement)
}

dependencies {
    implementation(libs.commonsLang3)
}
~~~

These are **fragments solely to illustrate the version catalog**, not full replacements for the two complete `build.gradle` files in section 3. In a real project, keep `repositories`, starter dependencies, and Java/toolchain settings. In the example, the version of `commons-lang3` is declared explicitly to demonstrate the catalog; before introducing it into a real Spring Boot app, verify whether this version aligns with dependency constraints/BOM and source code needs.

Version Catalogs provide **type-safe accessors** (like `libs.plugins.springBoot`), enabling IDE completion and centralized declarations, but **they do not force the final selected version** in every dependency conflict. Gradle still resolves according to the graph/constraints; inspect using `dependencies` or `dependencyInsight`.

Do not assume a catalog makes the two DSLs identical: calling `implementation libs.commonsLang3` vs. `implementation(libs.commonsLang3)` still differs, while accessor names come from the aliases in the TOML file.

## 14. Task Registration and Avoiding Early Configuration

A simple custom task:

**Groovy:**

~~~groovy
tasks.register('hello') {
    group = 'verification'
    description = 'Print a message line'
    doLast {
        println 'Hello Gradle'
    }
}
~~~

**Kotlin:**

~~~kotlin
tasks.register("hello") {
    group = "verification"
    description = "Print a message line"
    doLast {
        println("Hello Gradle")
    }
}
~~~

When run:

~~~bash
./gradlew hello
~~~

Output line printed by the task itself:

~~~text
Hello Gradle
~~~

In the Gradle API, `tasks.register` uses lazy task registration; `tasks.named` retrieves a `TaskProvider` for an existing task; `configureEach` configures matching tasks only when needed. Do not convert every call to `tasks.create`/`tasks.getByName` just to copy Groovy syntax to Kotlin, because eager methods can degrade configuration performance.

If you need to access specialized task properties, Kotlin must specify the exact generic/class. Example:

**Groovy:**

~~~groovy
tasks.named('jar') {
    archiveFileName = 'library.jar'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<Jar>("jar") {
    archiveFileName.set("library.jar")
}
~~~

`Jar` is the Java plugin's task type in Gradle. Kotlin can write the fully qualified `org.gradle.jvm.tasks.Jar` if imports do not recognize it; in standard Gradle Kotlin DSL scripts, `Jar` is available in default imports. The `jar` task must exist and requires the appropriate plugin.

## 15. Common Errors When Converting from Groovy to Kotlin DSL

| Symptom | Root cause | How to fix |
| --- | --- | --- |
| `Expecting an element` on `id 'java'` | Copied Groovy syntax into `.gradle.kts` | Write `id("java")` |
| `Too many characters in a character literal` | Kotlin treats single quotes as a `Char` (single character) | Use double-quoted strings like `"java"` |
| `Unresolved reference: implementation` | Plugin creating the configuration is missing or script is misplaced | Apply Java/JVM plugin in `plugins`, check sync |
| `Unresolved reference: useJUnitPlatform` | `tasks.named("test")` only sees the `Task` type | Write `tasks.named<Test>("test")` or `tasks.withType<Test>()` |
| `Unresolved reference: bootJar` | Spring Boot/Java plugin not applied or typed accessor unavailable | Check plugins, use typed `tasks.named<BootJar>("bootJar")` |
| `No value passed for parameter` | Kotlin requires explicit method arguments and specific APIs | Check Gradle Kotlin DSL API; replace Groovy named-arg syntax properly |
| `Cannot set the value of read-only property` | Confused property/provider API or setter does not exist | Use `.set(...)` on `Property<T>` or check plugin API for your version |
| `Could not find method implementation()` in Groovy | Plugin creating the configuration not applied or misplaced `dependencies` block | Check Java plugin and script structure |
| `Plugin [id: ...] was not found` | Wrong plugin repository/version, offline/proxy | Check `pluginManagement.repositories` and wrapper |
| `Could not find ... artifact` | Missing dependency repository or BOM/managed version | Check `repositories`, dependencyManagement/BOM, `dependencyInsight` |
| JVM error despite toolchain set to Java 17 | JVM running Gradle differs from compiler JDK, or toolchain not detected | Run `./gradlew --version`, `./gradlew javaToolchains` |
| Groovy IDE build passes but Kotlin import fails | Kotlin scripts are compiled/type-checked; plugin accessors/APIs need explicit types | Read compile error at the `.kts` line, fix using typed Gradle API |
| Artifacts/versions change after DSL switch | Conversion altered semantics, plugins/order/properties | Compare plugins, dependencies, task graph, and outputs of both versions |

**There is no universal "just add parentheses and change single quotes to double quotes" rule that works for every plugin.** When a build uses Groovy metaprogramming or plugins create dynamic extensions, check that plugin's Kotlin DSL documentation or write proper typed configuration. Avoid relying on Groovy bridges when the Gradle API provides a clear typed alternative.

## 16. Verifying Both DSLs for the Same Build Requirements

Create two separate directories, each containing a settings/build script pair from section 3 and the same Java source code. Use the **same Gradle wrapper version, JDK, Spring Boot plugin version, and dependency repositories** before comparing.

### 16.1. Diagnosing Configuration and Tasks

~~~bash
./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew javaToolchains
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

- `--version`: Gradle distribution and JVM currently running Gradle.
- `projects`: root and included subprojects.
- `tasks --all`: tasks in the model, including `bootRun`/`bootJar` if plugins are applied.
- `javaToolchains`: JDKs detected or configured by Gradle.
- `dependencies`: resolved dependency graph for the configuration.
- `dependencyInsight`: why Gradle selected a module version (e.g., `spring-core`).

If the CLI lacks `gradlew` because the project has not generated a wrapper yet, generate/provide the wrapper properly rather than assuming a `.gradle` file creates a wrapper. On Windows, switch to `.\gradlew.bat`.

### 16.2. Running Tests, Packaging, and the Application

~~~bash
./gradlew clean test
./gradlew bootJar
./gradlew build
./gradlew bootRun
~~~

Each line illustrates a verification point; you do not have to run all four sequentially if you already have the corresponding evidence. `bootJar` creates the executable JAR but does not automatically run tests; `build` normally includes both `assemble` and `check`. When running `bootRun`, call `/ping` to verify the Spring Boot app actually runs.

Groovy and Kotlin DSL projects are considered equivalent when, given the same inputs/environment and the same task types, they produce **semantically equivalent outputs**, not necessarily byte-for-byte identical JARs due to timestamps, metadata, caches, or packaging order. Compare the task graph, dependency versions, Java target, and runtime functionality.

### 16.3. Converting an Existing Repository

Practical workflow:

1. Record the current Gradle wrapper, JDK, and build/CI commands; keep plugin/dependency versions unchanged.
2. Create a safe copy or branch before editing build scripts; do not delete original files until the new build is verified.
3. Convert `settings.gradle` → `settings.gradle.kts` and `build.gradle` → `build.gradle.kts` block by block: plugins → repositories → dependencies → toolchain → tasks.
4. For each dynamic Groovy API, check the corresponding Kotlin type/generic. Do not assume every `foo bar` translates to `foo("bar")`.
5. Run `./gradlew help` or `./gradlew tasks` to check script compilation/configuration; then run `dependencies`/`dependencyInsight` and `build`.
6. Compare task names, dependency graphs, artifact names/types, and test results before removing the old scripts. Update CI/IDEs if they directly reference script filenames or conventions.

Use `--stacktrace` when hitting compile/configuration errors that need details; there is no need to escalate to `--debug` on every check.

## 17. Practice Exercises

**Exercise 1 — Syntax Conversion:** convert the following Groovy fragment to Kotlin DSL and explain each change.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Answer:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
}
tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

Precondition: the project already applies the Java/JVM plugin and Spring Boot dependency management/BOM so the dependency resolves. Changes include function call syntax, quotation marks, and the `Test` type parameter; the `implementation` dependency scope does not change.

**Exercise 2 — Fixing Kotlin DSL Errors:** why is the following snippet wrong?

~~~kotlin
plugins {
    id 'java'
}
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Answer:** `id 'java'` and `implementation '...'` are Groovy syntax. In `.gradle.kts` you must use `id("java")` and `implementation("...")`; you must also configure the Spring Boot plugin/BOM or dependency version for a complete Spring Boot build.

**Exercise 3 — Toolchain:** why might `./gradlew --version` report JVM 21 while `java.toolchain` requests Java 17?

**Answer:** The Gradle daemon/client can run on JVM 21, while the Java toolchain controls the compiler/test launcher used by configured tasks. Inspect `./gradlew javaToolchains` and task logs to see which JDK Gradle is actually using.

**Exercise 4 — Packaging:** `build.gradle.kts` has `bootJar` and `jar`. Which file is meant for `java -jar` when both `demo-0.0.1-SNAPSHOT.jar` and `demo-0.0.1-SNAPSHOT-plain.jar` exist?

**Answer:** Under default Spring Boot Gradle Plugin 3.3 configuration, the output of `bootJar` is normally the file without a classifier, while `jar` normally creates `-plain.jar`. Still, verify the output configuration, Boot archive structure, and logs before publishing.

**Exercise 5 — Version Catalog:** explain why `libs.commonsLang3` can appear in both `build.gradle` and `build.gradle.kts`.

**Answer:** Gradle generates type-safe accessors from aliases in `gradle/libs.versions.toml`. Both DSLs share the same catalog and dependency coordinates; only the configuration invocation syntax differs.

**Exercise 6 — Gradle Property vs. Spring Profile:** does running `./gradlew bootRun -PbuildFlavor=dev` automatically set `spring.profiles.active=dev`?

**Answer:** No. `buildFlavor` is only a Gradle project property; build logic or JVM/application arguments must pass the appropriate Spring runtime configuration for the Spring profile to change.

**Completion criteria:** you can write two equivalent pairs of `settings.gradle`/`build.gradle` and `settings.gradle.kts`/`build.gradle.kts`; convert common blocks; explain why Kotlin DSL needs typed `Test`/`BootJar` or `Property.set`; and verify the task graph, dependency versions, and executable Boot JAR.

## 18. Official Documentation

- Gradle Kotlin DSL Primer: https://docs.gradle.org/current/userguide/kotlin_dsl.html
- Gradle Migrating Build Logic from Groovy to Kotlin: https://docs.gradle.org/current/userguide/migrating_from_groovy_to_kotlin_dsl.html
- Gradle Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Gradle Build Environment Configuration: https://docs.gradle.org/current/userguide/project_properties.html
- Spring Boot 3.3.13 Gradle Plugin — Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot Gradle Plugin — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

Gradle "current" documentation changes across releases; when a project uses a specific Gradle wrapper, consult the exact version of Gradle and the Spring Boot plugin before applying new APIs/syntax. **Converting Groovy DSL to Kotlin DSL changes how the same Gradle build model is expressed; the final behavior must be proven through executed tasks, dependencies, and artifacts.**

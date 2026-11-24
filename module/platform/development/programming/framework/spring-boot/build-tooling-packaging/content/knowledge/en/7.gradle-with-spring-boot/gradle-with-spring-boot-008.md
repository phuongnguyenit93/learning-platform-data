# Managing Shared Configuration via Convention Plugins and Version Catalogs in Gradle

## 1. Goal: Assigning Build Configuration Responsibilities Properly

In a Spring Boot repository with multiple Gradle modules, repeating `plugins`, `java.toolchain`, `repositories`, `tasks.test`, `bootJar` settings, and dependency version numbers across every `build.gradle` makes modules drift out of sync. This lesson introduces two complementary mechanisms:

- **Convention plugins** encapsulate **reusable build behavior and conventions**: applying plugins, configuring Java toolchains, JUnit Platform, compiler options, quality checks, and shared tasks. A module opts into a convention by applying a clear plugin ID.
- **Version catalogs** centralize **library coordinates, versions, and plugin aliases**: typically in `gradle/libs.versions.toml`, accessed via `libs` accessors to avoid repeating names and versions across build scripts.

Both mechanisms solve different problems. A version catalog **does not automatically apply plugins, does not add dependencies to classpaths, and does not create quality gates**. A convention plugin can establish those rules, but should not arbitrarily hardcode the same version literals across many files.

### Target Outcomes

After this lesson, you will be able to:

1. Classify what belongs in a version catalog, what belongs in a convention plugin, and what stays in an individual application module.
2. Create `build-logic` as an **included build** containing precompiled Groovy convention plugins.
3. Have `build-logic` read the same `libs.versions.toml` as the main build without assuming the two builds automatically share every extension.
4. Put the Spring Boot Gradle plugin onto the convention plugin's classpath properly.
5. Create a library module and a Spring Boot application module adhering to Java 17, JUnit, BOM, and executable JAR conventions.
6. Use the task graph, dependency reports, and actual tests/artifacts to prove the conventions take effect.
7. Explain the catalog's limits: **aliases are neither a dependency lockfile nor a version-forcing mechanism**.

The documentation and examples use **Gradle Groovy DSL**, Java 17, Gradle Wrapper 8.10.2, and Spring Boot 3.3.13 to maintain a consistent set of version numbers. This is an illustrative configuration, not a claim of the latest current version. Real projects should pin compatible, supported versions according to their own policies.

## 2. Organizational Model: Who Owns What?

| Component | Typical location | What does it hold? | Not responsible for |
| --- | --- | --- | --- |
| `settings.gradle` | root build | Project name, subproject list, included builds, plugin/dependency repositories. | Should not contain full per-module compile/test config. |
| `gradle/libs.versions.toml` | root build | Version keys, library aliases, plugin aliases, bundles. | Does not apply plugins or add actual dependencies. |
| `build-logic` | an included build | Precompiled convention plugins and build-time dependencies to implement them. | Not a runtime module of the Spring Boot application. |
| `acme.java-conventions` | plugin in `build-logic` | Java plugin, Java 17 toolchain, test task/JUnit, shared Java rules. | Does not force every library into an executable Boot JAR. |
| `acme.spring-boot-app` | plugin in `build-logic` | Applies Java convention + Spring Boot plugin for executable modules. | Does not decide every business dependency a module needs. |
| `core/build.gradle` | library module | Picks Java library/convention plugins, declares module-specific dependencies. | Not the place to declare global Spring Boot versions. |
| `app/build.gradle` | app module | Picks app convention, imports Spring Boot BOM, declares starters and dependency on `core`. | Does not repeat Java toolchain and test setup already in conventions. |

**Design principle:** each module states **what kind of module it is** via a plugin ID; conventions define **rules for that kind**; the catalog holds **identities/versions of dependencies and plugins**. Keep genuinely module-specific customizations in the module's own build script instead of stuffing everything into a monolithic plugin.

### 2.1. Why Avoid Repeated Configuration via `subprojects { ... }`?

A quick initial shortcut is placing configuration in root:

~~~groovy
// Anti-pattern example of applying configuration across all modules:
subprojects {
    apply plugin: 'java'
    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

This creates **cross-project configuration**: when opening `app/build.gradle`, a reader cannot easily tell which rules are injected from root. Module configuration becomes tightly coupled to other projects and harder to optimize for configuration cache and parallelism. A library, a Boot app, and a platform/aggregator module should not all be forced to apply the exact same plugins either.

With the convention approach:

~~~groovy
// app/build.gradle
plugins {
    id 'acme.spring-boot-app'
}
~~~

A reader immediately sees what kind of build the module requests. `subprojects` is not forbidden in all scenarios, but for shared plugin/test/Java conventions, convention plugins keep boundaries much cleaner.

## 3. Version Catalog: Structure, Accessors, and Limits

Gradle automatically loads the default catalog from `gradle/libs.versions.toml` in the **main build**. The TOML file has four common sections:

- `[versions]`: version names and values.
- `[libraries]`: aliases pointing to `group:artifact`, optionally referencing a version key or omitting the version.
- `[plugins]`: aliases pointing to plugin ID + version, used in `plugins { alias(...) }` in regular build scripts.
- `[bundles]`: groups multiple library aliases for concise declarations; does not add them unless referenced.

Minimal example:

~~~toml
[versions]
spring-boot = "3.3.13"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
~~~

Accessor mapping is typically generated from hyphens: `spring-boot-bom` → `libs.spring.boot.bom`, `spring-boot-starter-web` → `libs.spring.boot.starter.web`, `spring-boot` in plugins → `libs.plugins.spring.boot`.

Example usage from a normal `build.gradle`:

~~~groovy
plugins {
    alias(libs.plugins.spring.boot)
}

dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation(libs.spring.boot.starter.web)
}
~~~

This is merely an **illustrative snippet showing accessor syntax**. Do not add the Boot plugin alias into a module that already applies `acme.spring-boot-app` if that convention already applies the Boot plugin. In the complete example below, `app` applies the convention to centralize plugin management.

### 3.1. Aliases Can Omit Versions

The two starters in the TOML above **have no versions**. That is intentional: the Spring Boot module imports the BOM via `platform(...)`. The BOM supplies the relevant constraints/versions; Gradle resolves the dependency graph with the BOM and other constraints.

A common error is omitting both the BOM and versions in the catalog, then writing:

~~~groovy
dependencies {
    implementation(libs.spring.boot.starter.web)
}
~~~

In that case, the module has no source managing the starter's version, so dependency resolution may fail with a missing-version error. Simply creating an alias does not make Gradle "read the version from the Spring Boot Gradle plugin".

### 3.2. Catalogs Do Not Force the Selected Version

Even if the catalog declares version X for library A, Gradle can still select Y due to the dependency graph, constraints/platforms, and conflict resolution. An alias only inserts **dependency notation** and a requested version where it is used.

- `platform(BOM)` feeds version constraints into the graph, usually as recommendations that can be upgraded by the graph.
- `enforcedPlatform(BOM)` enforces versions more strictly and can impact downstream consumers; use only when intentionally making that tradeoff and understanding its impact.
- `version catalogs` do not replace **dependency locking**, dependency verification, vulnerability scanning, or runtime compatibility analysis.
- `bundles` only group aliases for shorter syntax; they do not establish dependency scope boundaries or verify compatibility among members.

Use `dependencyInsight` to inspect the **actually selected** version and **why it was chosen**, rather than just reading version numbers in TOML.

## 4. Convention Plugins: Build Logic Acting as a Real Plugin

Gradle supports two common ways to share build logic:

- **`buildSrc/`:** a special build automatically recognized by Gradle, suitable for small projects, though changes to build logic can trigger broad configuration invalidation.
- **Included build `build-logic/`:** explicitly registered in settings, independently testable and publishable if needed; suitable for multi-project setups and larger teams.

This lesson uses an **included build** with **precompiled Groovy script plugins**. A file:

~~~text
build-logic/src/main/groovy/acme.java-conventions.gradle
~~~

becomes a plugin with ID:

~~~text
acme.java-conventions
~~~

The `.gradle` extension selects Groovy DSL; switching to `.gradle.kts` requires rewriting in Kotlin DSL and using the `kotlin-dsl` plugin in `build-logic`. **Do not mix `def`/Groovy closures into `.gradle.kts` files.**

### 4.1. Precompiled Plugins Have Their Own Classpath

An important Gradle rule:

- Core plugins like `java` and `java-library` are built-in for precompiled convention plugins.
- For external plugins like `org.springframework.boot`, the build compiling the convention plugin must declare the **plugin implementation dependency** on its classpath (e.g., `org.springframework.boot:spring-boot-gradle-plugin`).
- Inside the `plugins` block of the precompiled script plugin itself, apply the external plugin using `id 'org.springframework.boot'` **without a version**. The version is determined by `build-logic`'s dependency.
- `alias(libs.plugins.spring.boot)` **cannot be used directly inside the `plugins` block of a precompiled script plugin** the way it is used in regular build scripts.
- The main build and `build-logic` are two **separate builds**. The main build's `libs` does not automatically appear inside `build-logic`; to share the same catalog, import the TOML file into `build-logic`'s settings.

This is the most common stumbling block when migrating configuration from `app/build.gradle` into a convention plugin.

## 5. End-to-End Example: A Spring Boot App and a Java Library Sharing Conventions

### 5.1. File Tree

The project models an HTTP service `app` calling a Java method from a `core` library:

~~~text
shared-build-demo/
├── settings.gradle
├── gradle/
│   ├── libs.versions.toml
│   └── wrapper/...
├── gradlew
├── gradlew.bat
├── build-logic/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/
│       ├── acme.java-conventions.gradle
│       └── acme.spring-boot-app.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/com/example/core/Greeting.java
└── app/
    ├── build.gradle
    ├── src/main/java/com/example/app/Application.java
    └── src/test/java/com/example/app/ApplicationTest.java
~~~

The Wrapper files (`gradle-wrapper.jar`, `gradle-wrapper.properties`, `gradlew`, `gradlew.bat`) must exist in the project for the commands below to work. This example assumes Wrapper version 8.10.2 has been generated and saved—a Gradle 8.x release compatible with Spring Boot 3.3. Binary JAR contents are omitted from the article.

### 5.2. Shared Catalog File

`gradle/libs.versions.toml`:

~~~toml
[versions]
spring-boot = "3.3.13"

[libraries]
# Plugin artifact so build-logic can apply org.springframework.boot.
spring-boot-gradle-plugin = { module = "org.springframework.boot:spring-boot-gradle-plugin", version.ref = "spring-boot" }

# BOM as the dependency version management source for the application.
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }

# Versionless starters and launcher: receive versions from the BOM.
spring-boot-starter-web = { module = "org.springframework.boot:spring-boot-starter-web" }
spring-boot-starter-test = { module = "org.springframework.boot:spring-boot-starter-test" }
junit-platform-launcher = { module = "org.junit.platform:junit-platform-launcher" }

[plugins]
# Used when a module applies Boot directly, not alongside the app convention.
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
~~~

**Why do we need both `spring-boot-gradle-plugin` and `spring-boot-bom`?** One is the **plugin executing at Gradle configuration/build time**, and the other is the **BOM supplying version constraints for runtime/test dependencies**. Sharing the `spring-boot` key ensures we do not accidentally use plugin 3.3.13 with a BOM from a different Boot release line.

### 5.3. Main `settings.gradle`: Declaring Modules and Locating Convention Plugins

Root `settings.gradle`:

~~~groovy
pluginManagement {
    // Included plugin build must be registered before app uses its plugin ID.
    includeBuild('build-logic')

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

rootProject.name = 'shared-build-demo'
include('core', 'app')
~~~

- `includeBuild('build-logic')` lets Gradle find plugins provided by the included build when resolving subproject `plugins`.
- `include('core', 'app')` creates **two subprojects** in the main build. `build-logic` is an **included build**, not equivalent to `include('build-logic')` as a runtime library subproject.
- `pluginManagement.repositories` resolves plugins; `dependencyResolutionManagement.repositories` resolves libraries/BOMs. These are two separate scopes.
- The default version catalog resides at `gradle/libs.versions.toml`, so Gradle loads it automatically for the main build; there is no need to call `from(...)` again in main settings.

### 5.4. `build-logic/settings.gradle`: Re-Importing the Catalog Because This Is a Separate Build

`build-logic/settings.gradle`:

~~~groovy
rootProject.name = 'build-logic'

dependencyResolutionManagement {
    versionCatalogs {
        libs {
            from(files('../gradle/libs.versions.toml'))
        }
    }
}
~~~

`../gradle/libs.versions.toml` is the root build's file seen from inside `build-logic`. Within **build-logic**, there is no separate `gradle/libs.versions.toml` auto-loaded, so this catalog is created from **an existing file**.

Note:

1. `from(...)` takes a single file per catalog import; do not call `from(...)` multiple times for the same `libs` catalog.
2. When splitting `build-logic` into a separate repository, this relative path must change to a published catalog or another sharing mechanism.
3. This shares **version definitions**; it does not put all main-build dependencies/plugins onto `build-logic`'s classpath automatically.

### 5.5. `build-logic/build.gradle`: Enabling Convention Plugin Compilation

`build-logic/build.gradle`:

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

dependencies {
    // This alias is imported into build-logic in build-logic/settings.gradle.
    // The Boot plugin version comes from a single key in the root TOML.
    implementation(libs.spring.boot.gradle.plugin)
}
~~~

`groovy-gradle-plugin` is the standard plugin for precompiled Groovy script plugins. `implementation(libs.spring.boot.gradle.plugin)` places the **Spring Boot Gradle plugin artifact** onto the convention plugin's compile/runtime classpath; it does not add this artifact onto the Web application's runtime classpath.

Without that declaration, `acme.spring-boot-app.gradle` below would fail to resolve `org.springframework.boot` when Gradle builds `build-logic`. Do not work around it by adding `version '3.3.13'` inside the `plugins` block of a precompiled script plugin: explicit versions on external plugins are not supported there.

### 5.6. First Convention: Java Toolchain and JUnit

`build-logic/src/main/groovy/acme.java-conventions.gradle`:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

// Applies to every Test task created in the module.
// Configured lazily so tasks registered later also receive the convention.
tasks.withType(org.gradle.api.tasks.testing.Test).configureEach {
    useJUnitPlatform()
}
~~~

**Line-by-line meaning:**

- `id 'java'` provides main/test source sets and tasks such as `classes`, `test`, `check`, `jar`, and `build`.
- `java.toolchain` tells Gradle to use an appropriate Java 17 compiler/runtime toolchain; it does not install a JDK itself if the environment lacks one and toolchain provisioning is unconfigured.
- `tasks.withType(Test).configureEach` establishes the JUnit Platform convention for all existing and future `Test` tasks.
- This plugin **does not create an executable Boot JAR**, so it works cleanly for Java libraries too.

If an organization wants to enforce Checkstyle, JaCoCo, compiler options, or test logging, place those rules in this convention or a dedicated convention, wiring into `check` only the gates the project actually intends to run. Do not inject every test library dependency into modules that do not need them.

### 5.7. Second Convention: Applying Spring Boot for Apps

`build-logic/src/main/groovy/acme.spring-boot-app.gradle`:

~~~groovy
plugins {
    id 'acme.java-conventions'
    id 'org.springframework.boot'
}
~~~

These two lines carry significant weight:

1. `acme.java-conventions` applies the Java plugin, Java 17, and JUnit Platform.
2. `org.springframework.boot` is resolved from the plugin artifact declared in `build-logic/build.gradle`, so no version is written here.
3. Seeing the Java plugin present, the Spring Boot plugin adds its tasks and integrations, notably `bootJar` and `bootRun`.
4. The app plugin is **opted into explicitly by `app/build.gradle`**; it is never accidentally applied to `core`.

**Important question:** why not write `dependencies { implementation spring-boot-starter-web }` inside this convention? That is allowed if an organization intentionally requires every Boot app to be a Web app, but this example preserves each module's freedom to choose between **Web, Batch, CLI, or non-HTTP apps**. Thus the convention defines *how to build*, while each app selects its *runtime capabilities*, imports the BOM, and declares appropriate starters.

## 6. Java Library Module and Spring Boot App Module

### 6.1. The `core` Library

`core/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
    id 'acme.java-conventions'
}

group = 'com.example'
version = '0.1.0'
~~~

Both `java-library` and the Java convention can apply `java`; Gradle handles plugin application idempotently and will not compile twice simply because both plugins require Java. `java-library` brings `api`/`implementation` configurations for libraries; the Java convention brings the Java toolchain and JUnit.

`core/src/main/java/com/example/core/Greeting.java`:

~~~java
package com.example.core;

public final class Greeting {
    private Greeting() {
    }

    public static String reply() {
        return "pong";
    }
}
~~~

This is a standalone Java class without Spring. Running `./gradlew :core:build` produces a regular JAR for other modules to consume; **there is no reason to build a Boot executable JAR** from this module.

### 6.2. The `app` Application

`app/build.gradle`:

~~~groovy
plugins {
    id 'acme.spring-boot-app'
}

group = 'com.example'
version = '0.1.0'

dependencies {
    implementation(project(':core'))

    // Both classpaths need the BOM: runtime/main and test.
    implementation(platform(libs.spring.boot.bom))
    testImplementation(platform(libs.spring.boot.bom))

    implementation(libs.spring.boot.starter.web)
    testImplementation(libs.spring.boot.starter.test)
    testRuntimeOnly(libs.junit.platform.launcher)
}
~~~

**Explanation:**

- The module applies **one app convention ID**, without repeating `java`/`org.springframework.boot`/toolchain/JUnit setup.
- `implementation(project(':core'))` creates a real dependency on the Java library in the main build.
- `implementation(platform(libs.spring.boot.bom))` adds Boot version constraints to the main dependency graph.
- `testImplementation(platform(libs.spring.boot.bom))` does the same for the test dependency graph. Configuration inheritance may propagate the BOM indirectly, but declaring it explicitly keeps the setup crystal clear for learners.
- Starter/library aliases omit versions because the BOM manages them.
- `testRuntimeOnly(libs.junit.platform.launcher)` ensures the JUnit Platform launcher is present when Gradle runs tests. It does not place the test engine into the production artifact.
- The Spring Boot plugin from the convention generates an executable `bootJar` for `app`; `core` keeps producing a library JAR.

**Relationship between catalog and BOM:** the catalog provides *coordinates/paths to the BOM and starters*; `platform(...)` itself adds the BOM to the graph. Dependency alignment does not happen automatically just from having a TOML file.

### 6.3. Main Class of `app`

`app/src/main/java/com/example/app/Application.java`:

~~~java
package com.example.app;

import com.example.core.Greeting;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return Greeting.reply();
    }
}
~~~

`@SpringBootApplication` is the app's entry point; `@RestController` and `@GetMapping` expose `GET /ping`. The handler calls `Greeting.reply()` from the `core` module, proving the **internal dependency is wired properly** into `app`. Source files must sit at the matching paths/packages above; running bare `javac Application.java` will lack Spring dependencies and is not the right compile command.

### 6.4. Lightweight Integration Test with MockMvc

`app/src/test/java/com/example/app/ApplicationTest.java`:

~~~java
package com.example.app;

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
class ApplicationTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingDelegatesToCore() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("pong"));
    }
}
~~~

This test loads the Spring test context and exercises request mapping via MockMvc; it **does not open a real HTTP port** and **does not test the packaged binary JAR**. Its goal is to prove that JUnit Platform from the convention works, the BOM manages test dependencies, `core` is usable, and the endpoint returns the expected body.

Once the test passes, a complete verification still requires `bootJar` and a `java -jar` smoke test to confirm the packaged artifact.

## 7. Dependency Map Across Configuration Layers

The following diagram is a causal model, **not Gradle task execution order**:

~~~mermaid
flowchart TD
    TOML["gradle/libs.versions.toml"]
    ROOT["main settings.gradle"]
    LOGIC["build-logic/settings.gradle + build.gradle"]
    JAVA["acme.java-conventions"]
    BOOT["acme.spring-boot-app"]
    CORE["core/build.gradle"]
    APP["app/build.gradle"]
    BOM["Spring Boot BOM / platform"]
    JAR["app:bootJar"]

    ROOT -->|"includeBuild"| LOGIC
    ROOT -->|"include subprojects"| CORE
    ROOT -->|"include subprojects"| APP
    TOML -->|"auto-import in main build"| APP
    TOML -->|"explicit import"| LOGIC
    LOGIC -->|"plugin artifact classpath"| BOOT
    LOGIC --> JAVA
    JAVA --> CORE
    JAVA --> BOOT
    BOOT --> APP
    APP -->|"platform(libs...)"| BOM
    CORE -->|"project dependency"| APP
    APP --> JAR
~~~

**Important semantic distinctions:** library alias ≠ actual dependency; plugin alias ≠ applied plugin; plugin build classpath ≠ runtime application classpath; included build ≠ regular subproject.

In this example, updating `[versions] spring-boot` in TOML affects:
- The Spring Boot plugin artifact version applied by `build-logic`.
- The Spring Boot BOM version used by `app` to select dependencies.
- The `libs.plugins.spring.boot` plugin alias version for any module applying it directly.

However, changing the version does not automatically make application code compatible; always build, test, and inspect artifacts after upgrading.

## 8. Verification Steps Using the Gradle Wrapper

Run from the `shared-build-demo` root after ensuring JDK 17, Gradle Wrapper 8.10.2, and dependency download access. On Linux/macOS use `./gradlew`; on Windows use `gradlew.bat`.

### 8.1. Step A: Do Configuration and Plugins Resolve?

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all
./gradlew :core:tasks --all
~~~

Expect `:app` and `:core` listed as subprojects. In `app`, `bootJar`/`bootRun` from the Spring Boot plugin appear. In `core`, `jar`/`test` from the Java plugins appear, without `bootJar` since nothing applied the Boot plugin there. Listing a task proves only that it is **registered**, not that tests or packaging succeeded.

If `Plugin [id: 'acme.spring-boot-app'] was not found` occurs, inspect `pluginManagement.includeBuild('build-logic')`, filenames/IDs, and `build-logic` compilation output before looking at `app`'s libraries.

### 8.2. Step B: Preview the Task Graph Without Running

~~~bash
./gradlew :app:build --dry-run
./gradlew :core:build --dry-run
~~~

Expect `:app:build` to include compile/test/check/assemble branches with Boot packaging (since the app convention applies the Boot plugin). `:core:build` has only Java library packaging and declared test/verification tasks. `--dry-run` does not run tests; simulated lines must never be recorded as a PASS result.

### 8.3. Step C: Run Real Tests and Build

~~~bash
./gradlew clean :core:build :app:build
~~~

Expect:

- `core` Java source compiles.
- `app` compiles cleanly against `Greeting` from `project(':core')`.
- `:app:test` runs `pingDelegatesToCore` and reports test pass.
- `:app:bootJar` produces an executable Spring Boot JAR.
- `:core:jar` produces a regular library JAR.

Note that `clean` does not automatically clean all subprojects if your task path/configuration targets only root; to clean both modules explicitly in a project with custom root setup, use:

~~~bash
./gradlew :core:clean :app:clean :core:build :app:build
~~~

This cleans outputs per module cleanly; there is no need to wipe machine-wide caches or `.gradle`.

App reports normally reside at:

~~~text
app/build/test-results/test/
app/build/reports/tests/test/
~~~

If `NO-SOURCE` or `0 tests` appears on a module that should have tests, check `src/test/java` paths, class names, JUnit dependencies/launcher, and `useJUnitPlatform()`. `BUILD SUCCESSFUL` alone does not tell you how many tests were discovered.

### 8.4. Step D: Inspect Actual Dependency Resolution

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath

# Example checking which Spring Web version Gradle selected
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency spring-web
~~~

Expect to see Spring Boot BOM/platform constraints applied and matching Spring libraries in the dependency graph. `dependencyInsight` distinguishes **requested version**, **selected version**, constraints/BOMs, and conflict resolution.

Do not describe this state as "the catalog locks every dependency". If a version outside the BOM gets selected, Gradle reports/`dependencyInsight` are the right source of truth. If the project demands stricter version immutability, investigate dependency locking or explicit constraints.

### 8.5. Step E: Inspect the Actual Executable Artifact

~~~bash
./gradlew :app:bootJar
jar tf app/build/libs/app-0.1.0.jar
~~~

With the example's default settings, `app/build/libs/app-0.1.0.jar` is the typical Boot JAR name (unless archive name/classifier is customized). Inside the Spring Boot executable JAR for this example line, look for `BOOT-INF/classes/`, `BOOT-INF/lib/`, and a manifest with the proper launcher.

To verify real execution:

~~~bash
java -jar app/build/libs/app-0.1.0.jar --server.port=18085
~~~

In a second terminal, once the app has started:

~~~bash
curl -i http://localhost:18085/ping
~~~

Expect: HTTP status **200** and exact response body **`pong`**. Filename and startup messages must be taken from real build outputs; if your JAR name differs, use the real path rather than changing module names back to match the example. Stop the server with Ctrl+C and verify the process terminated.

**Summary of evidence:** the catalog resolves the right versions; conventions apply Java/Test/Boot plugins to the right modules; `core` produces a library JAR; `app` tests pass; `app` builds an executable JAR; the binary runs and serves HTTP. Together, these proofs demonstrate the value of shared configuration.

## 9. When Should a Rule Go into a Convention vs. a Module?

Centralize **repetitive, stable rules categorized by project type**:

| Rule | Appropriate place | Reason |
| --- | --- | --- |
| Shared JDK toolchain | `acme.java-conventions` | Both `core` and `app` need compatible Java versions. |
| JUnit Platform and shared test logging/timeouts | Java/testing convention | Modules avoid repeating rules while still choosing their own test dependencies. |
| Applying the Spring Boot plugin | `acme.spring-boot-app` | Apply only to runnable modules with a main class. |
| Boot plugin artifact version | Catalog + `build-logic/build.gradle` | Single version key, placed on the plugin build classpath. |
| Starter Web/Test dependencies | Catalog defines aliases; app chooses them | Not every module is an HTTP app. |
| Internal project dependency `:core` | `app/build.gradle` | That is a domain/architectural relationship of `app`. |
| Publishing, coverage, formatting, static analysis | Dedicated per-capability conventions | Apply only when opted into by a module or policy. |
| Secrets, DB URLs, prod Spring profiles | Runtime configuration/secret store | Not a build convention or TOML catalog entry. |
| Spring Boot BOM | Catalog provides coordinates; `platform`/plugin imports it | Version alignment must participate in dependency resolution. |

**Do not build an "all-in-one" convention** that attaches Spring Boot to library modules, forces Web starters onto batch apps, or hardcodes credentials into plugin sources. A maintainable convention represents a single clear capability: Java base, Java library, Boot app, publishing, quality gates...

### 9.1. Allowing Controlled Overrides

Conventions can establish defaults while modules customize within allowed bounds. For example, if a module genuinely needs extra compiler arguments or a custom test task, provide a well-scoped rule rather than scattering unapproved Java target overrides. When a requirement repeats across multiple modules, promote it to a convention; if it only applies to one app, keep it in that module.

Prefer Gradle lazy APIs (`tasks.named`, `configureEach`, Providers) so tasks are not configured/realized unnecessarily early. If a convention needs configurable options from consumers, define a **typed extension** rather than reading environment variables at configuration time without declaring inputs.

## 10. Changing Versions and Governing the Catalog

### 10.1. Upgrading Spring Boot Safely

Suppose you want to upgrade Boot to a team-approved version:

1. Update `spring-boot` in `gradle/libs.versions.toml`.
2. In the sample layout, both the plugin artifact alias and the BOM alias automatically point to the new version.
3. Verify **JDK/Gradle Wrapper** compatibility with the new plugin; do not assume every plugin release line still supports Gradle 8.10.2.
4. Run `dependencyInsight`, `test`, `build`, and a smoke test on the executable JAR to catch behavior changes.
5. Where dependencies have explicit overrides, re-verify the reason and compatibility; changing a catalog version does not rewrite constraints applied by other modules.

**Do not update only the `org.springframework.boot` plugin version and forget the BOM**, as that easily creates a mismatch between build plugin behavior and runtime dependency versions. A single shared key reduces risk, though it never replaces QA.

### 10.2. Plugin Aliases and Plugin Artifacts Are Two Different Patterns—Do Not Mix Them

A small standalone app project **without conventions** can use:

~~~groovy
plugins {
    id 'java'
    alias(libs.plugins.spring.boot)
}
~~~

Once **conventions exist**, `app` only needs:

~~~groovy
plugins {
    id 'acme.spring-boot-app'
}
~~~

Inside the convention, Spring Boot is applied via `id 'org.springframework.boot'` (versionless), and the version comes from `implementation(libs.spring.boot.gradle.plugin)` in `build-logic`. These are **two distinct plugin resolution paths**. Do not try to write `alias(libs.plugins.spring.boot)` or add `version '...'` inside a precompiled convention plugin.

### 10.3. Version Catalogs in Multi-Build / Monorepo Setups

A repository with multiple included builds (e.g., `build-logic`, test fixtures, custom Gradle plugins) must decide how to share the catalog:

- Within a single repo, import the **same TOML file** into each included build as needed.
- Across multiple repos, publish a catalog artifact and import it by version to decouple release lifecycles.
- Each included build has its own **settings** and dependency/plugin classpath; never assume root's `libs` automatically appears inside included builds.
- Plugin/dependency repository scopes can differ across builds. If `app` downloads dependencies fine yet `build-logic` fails to download the Boot plugin, inspect **`build-logic`'s repositories**, not just root.
- Test complex convention plugin behavior with Gradle TestKit/functional tests when appropriate; matching TOML filenames alone does not prove task wiring is accurate.

### 10.4. Relationship with the dependency-management Plugin

In Spring Boot Gradle builds, there are two ways to manage dependency versions:

- **Gradle native BOM**: `implementation(platform(libs.spring.boot.bom))` and likewise for tests, as shown in this example. Easy to inspect dependency constraints via Gradle reports.
- **`io.spring.dependency-management` plugin**: when applied with the Spring Boot plugin, imports the Boot BOM and supports property-based customization. This is a separate external plugin; if applied inside a precompiled convention, ensure its plugin artifact is also on `build-logic`'s classpath.

You do not need **both** to accomplish the same job. Choose one mechanism aligned with system needs and avoid overlapping configurations that obscure version resolution. Libraries that do not apply the Boot plugin are not automatically governed by the Boot BOM; if a library declares Boot starters or versionless dependencies, it also needs its own version management foundation.

## 11. Common Errors: Symptoms, Root Causes, and Fixes

| Symptom | Common root cause | How to fix |
| --- | --- | --- |
| `Plugin [id: 'acme.spring-boot-app'] was not found`. | Forgot `includeBuild('build-logic')` in `pluginManagement`, wrong filename/plugin ID, or `build-logic` failed to compile. | Check root settings, `src/main/groovy` paths, and `build-logic` logs. |
| `Plugin [id: 'org.springframework.boot'] was not found` when compiling convention. | External plugin missing from `build-logic` implementation classpath. | Add `spring-boot-gradle-plugin` artifact to `build-logic/build.gradle`. |
| Cannot find `libs` inside `build-logic`. | Main build catalog is not automatically shared with included builds. | Import `../gradle/libs.versions.toml` in `build-logic/settings.gradle`. |
| `alias(libs.plugins.spring.boot)` fails in precompiled `plugins` block. | Catalog aliases are not supported there like ordinary build scripts. | Apply `id 'org.springframework.boot'` and depend on it in `build-logic`'s classpath. |
| `libs.spring.boot.bom` accessor missing. | Wrong alias name, invalid TOML syntax, catalog not imported, or stale Gradle sync. | Check TOML and path, re-run Gradle sync/configuration. |
| Starter dependency lacks a version. | Added a versionless alias without a BOM/`platform` or dependency management. | Add `platform(libs.spring.boot.bom)` to the appropriate configurations. |
| Version catalog says X, yet Gradle picks Y. | Constraints/BOM/transitive dependency conflict. | Use `dependencyInsight` to inspect requested vs. selected and constraint sources. |
| `:core:bootJar` appears or demands a main class. | Boot plugin applied to library via an overly broad convention. | Scope Boot plugin to the app convention; libraries use `java-library`. |
| `:app:bootJar` is missing. | App did not apply Boot/Java plugin or plugin was disabled. | Inspect `:app:tasks --all` and convention plugin IDs. |
| `:app:test` reports `NO-SOURCE` or skips JUnit tests. | Wrong file path, `useJUnitPlatform` not applied, missing `starter-test`/launcher. | Check `src/test/java`, convention task config, and test runtime classpath. |
| Build passes but JAR lacks runtime dependencies. | Picked plain JAR, or custom build script altered artifact/scope. | Check `bootJar`, manifest, `BOOT-INF/lib`, and test with `java -jar`. |
| Version bump breaks `build-logic`. | Newer plugin does not support current Gradle/JDK or lacks repository access. | Check release compatibility notes and upgrade toolchain/Wrapper deliberately. |
| Root `allprojects`/`subprojects` overrides module values. | Cross-project config conflicts with conventions. | Move capability rules into conventions and remove duplicate root blocks. |
| Catalog used, yet dependencies are not fully locked down. | Catalogs are not lockfiles or strict enforcement policies. | Use BOMs, constraints, and locking/verification when required. |

### Layered Diagnostic Approach

1. **Plugin resolution**: check root `pluginManagement`, `includeBuild`, and plugin ID filenames.
2. **Build-logic compilation**: check `build-logic/settings.gradle` catalog import, repositories, and plugin artifact dependencies.
3. **Module plugin wiring**: inspect `:core:tasks --all` and `:app:tasks --all` to see which module gets Java/Boot tasks.
4. **Dependency resolution**: read `runtimeClasspath`, `testRuntimeClasspath`, and `dependencyInsight`; spot missing BOMs or version conflicts.
5. **Compilation/test**: check the Java toolchain selected by Gradle, Test/JUnit reports, and `NO-SOURCE`/`FAILED` tasks.
6. **Packaging/runtime**: confirm `bootJar` and the executable file, then verify with `java -jar` and a smoke test.

Diagnosing at the right layer avoids "fixing" issues by copying plugins/versions back into every module, which defeats the purpose of conventions and catalogs.

## 12. Practice Exercises and Completion Criteria

### Practice Exercise A — Proving Shared Configuration Works

1. Create the directory tree and both modules as in the example.
2. Run `./gradlew projects`, `:core:tasks --all`, and `:app:tasks --all`.
3. Prove that **only `app`** has `bootJar`, while both `core` and `app` have Java/Test tasks.
4. Run `./gradlew :core:clean :app:clean :core:build :app:build`.
5. Inspect the `ApplicationTest` report (status 200, body `pong`), executable archive contents, and run the `GET /ping` smoke test.

### Practice Exercise B — Testing a Convention Change

Change the Java toolchain in `acme.java-conventions.gradle` to another **project-supported** version with an installed JDK on your machine, then observe the change affecting compilation of both `core` and `app`. Restore Java 17 after experimenting. Do not pick an arbitrary newer JDK unsupported by the Spring Boot plugin or Gradle Wrapper in this lesson.

### Practice Exercise C — Testing a Catalog Version Change

Change the `spring-boot` key in TOML to a verified compatible version, run Gradle configuration/build, and compare plugin/BOM versions from reports. Restore the example version afterward. If dependency resolution fails due to an offline environment or missing repository, record that exact blocker rather than blaming Java code.

### Self-Assessment Checklist

- [ ] Explain how **convention plugins manage build behavior**, while version catalogs manage coordinates/versions/aliases.
- [ ] Distinguish the main build, subprojects, and the `build-logic` included build.
- [ ] Create precompiled Groovy conventions whose plugin IDs match their filenames.
- [ ] Apply Java 17 + JUnit Platform via convention to both `core` and `app`.
- [ ] Apply the Boot plugin only to `app` and confirm `bootJar` exists on the right module.
- [ ] Put the Boot plugin artifact onto **`build-logic`'s classpath** without leaking it into app runtime.
- [ ] Import the shared TOML in `build-logic/settings.gradle`, understanding why explicit import is required.
- [ ] Use the BOM via `platform(...)` and versionless starter aliases properly.
- [ ] Avoid using plugin aliases inside the `plugins` block of precompiled conventions.
- [ ] Verify requested vs. selected dependency versions with `dependencyInsight`.
- [ ] Distinguish version catalogs from BOMs, constraints, and dependency locking.
- [ ] Distinguish a library `jar` from an executable `bootJar`, and run the packaged artifact.
- [ ] Produce test reports and a `GET /ping` smoke test for `app`.
- [ ] Explain when dedicated conventions are preferable to root `subprojects` configuration.

**Lesson completion criteria:** the learner presents a complete set of files, identifies which convention contains each Java/test/Boot rule, demonstrates that both the plugin and BOM share the same Boot version from the catalog, explains `app`'s dependency declarations, and provides logs/reports covering build, tests, and packaged runtime. If any piece of evidence is missing, state clearly what remains unverified instead of assuming `BUILD SUCCESSFUL` covers everything.

## Official Documentation

- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html)
- [Gradle — Precompiled Script Plugins and Applying External Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html)
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html)
- [Gradle — Platforms and Maven BOM](https://docs.gradle.org/current/userguide/platforms.html)
- [Gradle — Catalogs and Platforms](https://docs.gradle.org/current/userguide/centralizing_catalog_platform.html)
- [Spring Boot 3.3 Gradle Plugin — Getting Started](https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html)
- [Spring Boot 3.3 Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html)

Example files are instructional configurations. Verification commands must be run in a project with proper Wrapper/JDK/dependency repositories; do not treat expected outputs as measured logs without executing them.
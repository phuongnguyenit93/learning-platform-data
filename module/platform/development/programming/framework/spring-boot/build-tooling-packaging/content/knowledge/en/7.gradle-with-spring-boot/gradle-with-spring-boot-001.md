# Structure of settings.gradle and build.gradle in a Spring Boot Project

## 1. The Big Picture

A Spring Boot project using Gradle typically has two important configuration files:

- **`settings.gradle`**: describes the *entire build*, including the root project name, participating subprojects, how to find plugins, shared dependency repositories, and build-level dependency management configurations.
- **`build.gradle`**: describes *a specific project*, including which plugins to apply, which dependencies to use, what version/group it has, which Java version to compile with, and which tasks to create/run.

The two files above use **Groovy DSL**. If you choose **Kotlin DSL**, the corresponding file names are `settings.gradle.kts` and `build.gradle.kts`; the syntax differs slightly, but the responsibilities are fundamentally the same. **Do not use Groovy syntax and save it in a `.kts` file, or vice versa.**

Quick comparison table:

| Configuration concern | Typical location | Example |
|---|---|---|
| Build/root project name | `settings.gradle` | `rootProject.name = 'orders-api'` |
| Add modules to the build | `settings.gradle` | `include 'orders-api', 'shared-domain'` |
| Where to download Gradle plugins | `settings.gradle` → `pluginManagement.repositories` | `gradlePluginPortal()` |
| Shared library repository for modules | `settings.gradle` → `dependencyResolutionManagement.repositories` | `mavenCentral()` |
| Plugins of a module | `build.gradle` → `plugins` | `id 'java'`, `id 'org.springframework.boot'` |
| Artifact group and version | `build.gradle` | `group = 'com.example'`, `version = '0.1.0-SNAPSHOT'` |
| Java toolchain | `build.gradle` → `java` | `JavaLanguageVersion.of(17)` |
| Source/test/runtime dependencies | `build.gradle` → `dependencies` | `implementation '...starter-web'` |
| Testing, packaging, running the app | `build.gradle` and plugin-provided tasks | `test`, `bootJar`, `bootRun` |
| Gradle version downloaded by the wrapper | `gradle/wrapper/gradle-wrapper.properties` | `distributionUrl=...gradle-8.14.3-bin.zip` |
| Build and daemon properties | `gradle.properties` | `org.gradle.parallel=true` |

**Easy mental model:** `settings.gradle` answers "which projects belong to this build and where do we find the components?"; `build.gradle` answers "with which plugins, dependencies, and tasks is this project built into an application/library?".

## 2. Single-Module Directory Structure from Spring Initializr

Suppose you create an application named `orders-api`, Java 17, Gradle Groovy, Spring Boot 3.5.x. The directory typically has this structure:

```text
orders-api/
├── settings.gradle                         # Build identity and structure
├── build.gradle                            # Build logic for the root project
├── gradle.properties                       # Optional, not required
├── .gitignore
├── gradlew                                 # Wrapper script for Unix/macOS
├── gradlew.bat                             # Wrapper script for Windows
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar              # Wrapper bootstrap code
│       └── gradle-wrapper.properties        # Gradle version/distribution
├── src/
│   ├── main/
│   │   ├── java/com/example/orders/
│   │   │   ├── OrdersApplication.java
│   │   │   └── HelloController.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/com/example/orders/
│           └── OrdersApplicationTests.java
└── build/                                  # Generated after running Gradle
    ├── classes/
    ├── resources/
    ├── reports/
    ├── test-results/
    └── libs/
```

This is an **illustrative structure with an added controller and test**; Spring Initializr may generate different structures or files depending on the dependencies. The `build/` directory appears after running tasks and is normally excluded from Git. Both `settings.gradle` and `build.gradle` sit at the root in a single-module project; you do not need a separate `build.gradle` file for `src/main`.

`gradlew` / `gradlew.bat` are scripts that invoke the exact Gradle version via the wrapper. You should use the wrapper instead of a globally installed `gradle` when working in teams and CI, and commit the necessary wrapper files.

## 3. settings.gradle: Contents and Meaning

### 3.1. Minimal Case

A simple **single-module** Spring Boot project might only need:

```groovy
// settings.gradle (Groovy DSL)
rootProject.name = 'orders-api'
```

`rootProject.name` sets the root project name. This value is used by Gradle in reports, task structure, and typically affects the default archive file name if not customized. It **does not automatically change** the Java package (`package com.example.orders;`), `group`, or the Spring property `spring.application.name`.

If the root name is not explicitly specified, Gradle may fall back to the directory name; when checking out the project into a different path, the implicit name can easily change. Setting a stable name in `settings.gradle` helps CI and developers get consistent results.

### 3.2. Declaring Repositories and Centralized Repository Policy

A `settings.gradle` suitable when you want to control both plugin and dependency repositories:

```groovy
// settings.gradle: complete example for a single-module application

pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'orders-api'
```

Exact explanation of each part:

1. `pluginManagement.repositories` tells Gradle **where to find plugins** declared via `plugins { ... }`. `gradlePluginPortal()` is a repository for plugins, distinct from the repository holding application runtime libraries.
2. `dependencyResolutionManagement.repositories` tells Gradle **where to find libraries** such as `spring-boot-starter-web`, Jackson, JUnit…
3. `repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS` requires projects not to declare additional repositories in `build.gradle`; if they do, Gradle reports an error. This rule is useful when an organization wants to manage library sources centrally. It is a deliberate choice, **not mandatory**.
4. `rootProject.name` is the name of the root project.

**Very important:** `pluginManagement { ... }`, if present, must appear at the top of `settings.gradle`, before regular configuration statements. Do not place `rootProject.name` or `include` before `pluginManagement` and then configure plugin repositories afterwards.

In the example above, **do not add** `repositories { mavenCentral() }` in `build.gradle`, because `FAIL_ON_PROJECT_REPOS` intentionally forbids project-level repositories. If you do not want to centralize, you can omit `dependencyResolutionManagement` and declare `repositories { mavenCentral() }` in `build.gradle` as seen in many simple projects generated by Initializr. These two patterns are **two alternative ways of organizing**, not to be combined arbitrarily.

Gradle's three main repository modes:

| Mode | Meaning |
|---|---|
| `PREFER_PROJECT` | Default; project-level repositories can take precedence over repositories declared in settings |
| `PREFER_SETTINGS` | Prefers repositories in settings and warns when a project declares other repositories |
| `FAIL_ON_PROJECT_REPOS` | Fails if a project declares repositories, forcing management in settings |

When the system uses an internal artifact registry, declare the trusted repository in the appropriate place; **do not hardcode passwords/tokens** into Git. You can use credentials retrieved from environment variables, secure Gradle properties, or CI secrets.

### 3.3. Where to Place the Plugin Version?

You can declare the plugin version directly in `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}
```

Or centralize plugin versions in `pluginManagement.plugins` of `settings.gradle`:

```groovy
// Alternative configuration snippet at the top of settings.gradle
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id 'org.springframework.boot' version '3.5.16'
        id 'io.spring.dependency-management' version '1.1.7'
    }
}
```

When using the second approach, `build.gradle` can apply plugins by ID **without repeating the version**:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
```

**Choose one clear source of truth for versions** of the same plugin, especially in multi-module builds. `pluginManagement` manages how plugins are resolved and their default versions; declaring a plugin here **does not mean automatically applying the plugin** to every project. A project only receives Spring Boot tasks when the `org.springframework.boot` plugin is actually applied to that project.

## 4. build.gradle: Key Blocks in Spring Boot

In a Java project, `build.gradle` is the script that configures the project and tasks. Common blocks:

| Block / property | Role |
|---|---|
| `plugins { ... }` | Applies the Java plugin, Spring Boot Gradle plugin, dependency management, and other test/quality plugins |
| `group` and `version` | Artifact coordinates: organization and release version |
| `java { toolchain { ... } }` | Selects the JDK for compilation/testing according to toolchain configuration |
| `repositories { ... }` | Where to download dependencies **if not managed centrally in settings** |
| `dependencies { ... }` | Dependencies by configuration: `implementation`, `runtimeOnly`, `testImplementation`… |
| `tasks.named('test') { ... }` | Customizes the test task, e.g., enabling JUnit Platform |
| `tasks.named('bootJar') { ... }` | Customizes the Boot executable artifact if truly needed |
| `configurations { ... }` | Advanced customization of dependency groups/configurations |

### 4.1. The plugins Block

`id 'java'` applies the Java plugin: conventions for `src/main/java`, `src/test/java`, and tasks such as `compileJava`, `test`, and `jar`.

`id 'org.springframework.boot'` applies the Spring Boot Gradle plugin: when used alongside the Java plugin, it provides `bootRun`, `bootJar`, and appropriate packaging/running tasks.

`id 'io.spring.dependency-management'` adds a Maven-style dependency version management mechanism. When both the Spring Boot plugin and the dependency management plugin are applied, Spring Boot **automatically imports** the `spring-boot-dependencies` BOM matching the Spring Boot plugin version, allowing many starters to be declared **without specifying a version**.

Using `io.spring.dependency-management` is not mandatory: Gradle's native `platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)` is also an option. If neither the dependency management plugin nor native BOM/constraints are used, dependencies without a version may fail to resolve. The Spring Boot plugin **by itself** does not guarantee that every dependency already has a version.

### 4.2. Project Coordinates, JDK, and Dependency Configurations

`group = 'com.example'` is not a Java package. `version = '0.1.0-SNAPSHOT'` is the version of your application/artifact, **not the Spring Boot version**.

Java toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

The toolchain lets Gradle select a JDK for compilation/testing according to Gradle's policy; the Gradle runtime/daemon itself still needs a JDK compatible with the Gradle version in use. If the machine does not have JDK 17 installed and no toolchain download repository is configured, Gradle may report that no matching toolchain was found; do not treat that as a Spring Boot bug.

Common configurations:

- `implementation`: dependencies needed in main code; does not expose compile API dependencies to consumers like `api` in `java-library`.
- `compileOnly`: needed only for compilation, not automatically present at runtime.
- `runtimeOnly`: needed at runtime, not directly needed to compile main source.
- `testImplementation`: used to compile/run tests; not promoted to a main dependency just because it appears in tests.
- `testRuntimeOnly`: needed only at test runtime.
- `annotationProcessor` and `testAnnotationProcessor`: code-generation processors (e.g., Lombok) during compile time; should not be added indiscriminately to `implementation`.

This configuration mechanism is why `spring-boot-starter-test` normally sits in `testImplementation`, while `spring-boot-starter-web` sits in `implementation`.

## 5. Complete Single-Module Example with Groovy DSL

Below is **a Java 17 Spring Boot project that can build/run** when using a valid Gradle Wrapper and having JDK 17, with plugins/versions chosen for illustration. The example uses **centralized repositories in settings** and `io.spring.dependency-management` to avoid specifying versions for starters.

### 5.1. The settings.gradle File

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'orders-api'
```

### 5.2. The build.gradle File

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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this example:

- `repositories` is not declared in `build.gradle` because settings enabled `FAIL_ON_PROJECT_REPOS`.
- `3.5.16` is the Spring Boot plugin version used for the example, and `1.1.7` is the dependency management plugin version. Check compatibility with the wrapper/JDK and your system's version policy when applying in practice.
- Starters omit versions because the Spring Boot BOM is imported when both corresponding plugins are applied.
- `useJUnitPlatform()` directs the `test` task to run the JUnit Jupiter/JUnit Platform test suite, matching modern `spring-boot-starter-test` versions.

### 5.3. Runnable Java Source Code

**`src/main/java/com/example/orders/OrdersApplication.java`**

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

**`src/main/java/com/example/orders/HelloController.java`**

```java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello Spring Boot";
    }
}
```

**`src/test/java/com/example/orders/OrdersApplicationTests.java`**

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrdersApplicationTests {
    @Test
    void contextLoads() {
    }
}
```

These are standalone Java files by name/class, but they require **Spring Boot/JUnit dependencies downloaded by Gradle**; simply running `javac OrdersApplication.java` with a bare JDK will not find Spring Boot classes.

The `OrdersApplication` class is in the `com.example.orders` package, so Spring Boot scans `HelloController` in the same package by default. Run the application using the wrapper:

```bash
# Unix/macOS, from the project root directory
./gradlew test
./gradlew bootRun
```

In another terminal, once the server has started on the default port 8080:

```bash
curl --silent http://localhost:8080/hello
```

**Expected HTTP response body:** `Hello Spring Boot`. The `curl --silent` command does not necessarily print a trailing newline. If port 8080 is already in use or a different `server.port` is configured, adjust the URL accordingly. On Windows PowerShell, you can use `curl.exe http://localhost:8080/hello` or `Invoke-WebRequest`; the wrapper is `gradlew.bat`.

Package the application:

```bash
./gradlew bootJar
```

Typically the file appears under `build/libs/orders-api-0.1.0-SNAPSHOT.jar` if archive naming has not been customized. It can be run with:

```bash
java -jar build/libs/orders-api-0.1.0-SNAPSHOT.jar
```

The actual JAR name should be checked in `build/libs/`. For a Boot project with the Java plugin applied, `bootJar` creates an executable JAR; regular `jar` creates a different JAR. `build` runs the assemble/check task set configured by plugins, while `bootRun` directly launches the application from the development classpath.

### 5.4. Included Gradle Wrapper

Example `gradle/wrapper/gradle-wrapper.properties` file (illustrating only the relevant field):

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

This is a published Gradle 8.x version that matches the platform requirements of the Spring Boot 3.5.x example. Real wrapper files may include additional parameters such as timeout, SHA-256 verification, base path…; use the files generated by Initializr or the Gradle Wrapper command and commit them along with the required scripts/JAR.

Do not modify `distributionUrl` to switch to an arbitrary Gradle version before checking the requirements of the **Spring Boot plugin** and other build plugins. The `./gradlew --version` command helps verify which Gradle version is actually running.

## 6. Kotlin DSL: Changing the File Extension Comes with Changing Syntax

If you choose **Gradle Kotlin** when using Spring Initializr, the two files are `settings.gradle.kts` and `build.gradle.kts`. They still describe the same structure and behavior, but use Kotlin syntax.

**Equivalent `settings.gradle.kts`:**

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "orders-api"
```

**Equivalent `build.gradle.kts`:**

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

This example uses the same Java files from section 5. You need to understand the difference between `id 'java'` (Groovy) and `java` (Kotlin DSL), `implementation 'group:artifact'` versus `implementation("group:artifact")`, as well as property setters `repositoriesMode = ...` and `repositoriesMode.set(...)`.

**Do not create both `build.gradle` and `build.gradle.kts` at the same time for the same project.** Pick one consistent DSL to avoid ambiguity over which script is used. Do not copy a Kotlin snippet into a Groovy file just because both are called "Gradle configuration".

## 7. settings.gradle in a Multi-Module Build

As the project grows, you can separate shared code (`shared-domain`) from the standalone runnable application (`orders-api`). In that case `settings.gradle` is where the **project graph** is defined.

Example:

```text
store-platform/
├── settings.gradle
├── build.gradle                 # Shared: plugin versions, do not apply Boot at root
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── orders-api/
│   ├── build.gradle             # Boot application module
│   └── src/main/java/...
└── shared-domain/
    ├── build.gradle             # Java library module
    └── src/main/java/...
```

**`settings.gradle` at root:**

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode = RepositoriesMode.FAIL_ON_PROJECT_REPOS
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'store-platform'
include 'orders-api', 'shared-domain'
```

After `include`, Gradle knows two project paths `:orders-api` and `:shared-domain`; their names are not Java packages. By default each name maps to a directory of the same name under root. If creating nested projects, `include 'services:orders-api'` normally maps to `services/orders-api/`. With modern Gradle, make sure subproject directories exist, especially when using Gradle 9+, to avoid initialization errors.

**`build.gradle` at root:** uses `apply false` so plugin versions are available to modules without applying the Boot plugin to root.

```groovy
plugins {
    id 'org.springframework.boot' version '3.5.16' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
```

**`orders-api/build.gradle`:** applies the Boot plugin to the actual runnable application module.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation project(':shared-domain')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`shared-domain/build.gradle`:** declares a plain Java library module without creating an executable Boot JAR.

```groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

In this example, `shared-domain` declares no external dependencies; if you later add versionless dependencies, you must manage versions separately via a BOM/platform or shared rule. Do not infer that a BOM applied in `orders-api` will automatically apply to every dependency declaration **of the `shared-domain` project**.

Run tasks for a specific module:

```bash
./gradlew projects
./gradlew :orders-api:bootJar
./gradlew :shared-domain:jar
```

`:orders-api:bootJar` invokes only the Boot task on the application module and its dependent tasks; `shared-domain:jar` produces a regular library JAR. When `orders-api` declares `implementation project(':shared-domain')`, Gradle determines the appropriate build order and classpath to consume the library module's output.

Do not apply `org.springframework.boot` to every module if some modules are only libraries. The Boot plugin is normally needed only in modules producing a Boot executable application. If multiple modules share build rules, use convention plugins or deliberate build-logic sharing mechanisms rather than copy-pasting configuration everywhere.

## 8. How Gradle Reads Configuration

Gradle processes a build in three main phases:

```text
Command: ./gradlew bootJar
            |
            v
  INITIALIZATION
  Read settings.gradle
  -> Determine rootProject and subprojects
  -> Set up plugin/dependency resolution rules
            |
            v
  CONFIGURATION
  Read build.gradle of projects to configure
  -> Apply plugins
  -> Create/configure task graph
  -> Determine task dependencies
            |
            v
  EXECUTION
  Run requested tasks + dependent tasks
  -> compileJava, processResources,...
  -> bootJar
            |
            v
  build/libs/*.jar
```

This diagram is a conceptual model; configuration cache and Gradle optimizations can change the amount of work performed without changing the purpose of each file. Do not call `bootJar` a phase in `settings.gradle`: `bootJar` is a **task** provided by the Spring Boot Gradle plugin in an appropriate project.

A `settings.gradle` file can have `includeBuild` to attach build logic or a composite build; that is a different concept from `include` for subprojects. For beginners, simply understand that `include` creates modules within the same multi-project build, whereas `includeBuild` connects a separate build.

## 9. Understanding Plugin Repositories, Dependency Repositories, and BOMs Correctly

Three components may appear together, yet each solves a distinct problem:

| Component | Example | Meaning |
|---|---|---|
| Plugin repository | `pluginManagement { repositories { gradlePluginPortal() } }` | Finds and downloads Gradle plugins |
| Dependency repository | `dependencyResolutionManagement { repositories { mavenCentral() } }` | Finds Java libraries used by the project |
| BOM / dependency management | `io.spring.dependency-management` or `platform(...)` | Selects versions for requested dependencies |

**Common mistake:** declaring only `pluginManagement.repositories { gradlePluginPortal() }` and wondering why `spring-boot-starter-web` fails to download. Plugin Portal and Maven Central serve two different needs; if the dependency repository is missing or has network/auth errors, dependency resolution will still fail.

If choosing a native BOM instead of the `io.spring.dependency-management` plugin, the build configuration can look like this (this is an **alternative approach**, not to be pasted on top of the `build.gradle` sample in section 5):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

With this approach, complete the file with `group`, `version`, `java { ... }`, `tasks.named('test') { ... }`, and a matching `settings.gradle` like the single-module example. `platform` feeds the BOM's versions into Gradle's dependency constraints; other version requirements in the graph may cause the selected version to differ from the BOM. `enforcedPlatform` is a stricter variant that can cause conflicts or affect consumers; do not use it without understanding its impact.

If the Spring Boot plugin is applied together with `io.spring.dependency-management`, Boot automatically imports the BOM; there is no need to add `platform` just to "guarantee dependencies". Using one clear management approach makes version analysis much easier.

## 10. Related Files with Different Responsibilities

### 10.1. gradle.properties

`gradle.properties` stores Gradle properties, for example:

```properties
org.gradle.parallel=true
org.gradle.caching=true
```

In a multi-module build there can be root-level properties as well as user-level properties. Do not store real API tokens or passwords in a committed `gradle.properties`; place secrets in a secure location and reference them only when needed. `gradle.properties` does not replace `settings.gradle` or `build.gradle`.

### 10.2. gradle/libs.versions.toml

A version catalog can centralize aliases and versions:

```toml
[versions]
spring-boot = "3.5.16"

[libraries]
spring-boot-web = { module = "org.springframework.boot:spring-boot-starter-web" }

[plugins]
spring-boot = { id = "org.springframework.boot", version.ref = "spring-boot" }
```

When placed under `gradle/libs.versions.toml`, Gradle automatically provides a default catalog named `libs`. Build scripts can reference plugin and library aliases using the corresponding DSL syntax, but **a version catalog does not automatically import a BOM, does not automatically apply plugins, and does not resolve all dependency conflicts**. This is an additional organizational step after you understand `settings.gradle` and `build.gradle`.

### 10.3. application.properties / application.yml

`src/main/resources/application.properties` is **runtime application configuration**, for example:

```properties
spring.application.name=orders-api
server.port=8080
```

It is completely different from a build script: `server.port` is read by Spring Boot when running the application, whereas `rootProject.name` belongs to Gradle. Do not write `server.port=8080` in `settings.gradle` and expect Spring to pick it up automatically. Also, do not store real passwords in `application.properties` committed to Git or packaged into a JAR.

### 10.4. .gitignore and the build/ Directory

`build/`, `.gradle/`, and log files are local outputs/caches, normally ignored in Git. Conversely, `settings.gradle`, `build.gradle`, `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, and `gradle/wrapper/gradle-wrapper.jar` are critical inputs for others to reproduce the build and usually need to be committed.

## 11. How to Read and Inspect an Unfamiliar Spring Boot Gradle Project

When opening an unfamiliar repository, read and inspect in order:

1. **`settings.gradle[.kts]`**: What is the root name? Which modules are `include`d? Are there `pluginManagement`, `dependencyResolutionManagement`, or internal repositories?
2. **`gradle/wrapper/gradle-wrapper.properties`**: Which Gradle version is used? Is it compatible with Spring Boot/Java/plugins?
3. **`build.gradle[.kts]` of the module to run**: Are `java` and `org.springframework.boot` applied? Is the dependency management plugin or `platform` declared?
4. **`group` / `version` / `java.toolchain`**: Are they configured for the project's release and JDK?
5. **`dependencies`**: Do dependencies go into main, test, or runtime? Which BOM/constraint provides their versions?
6. **`src/main/java`**: Is the `@SpringBootApplication` main class in a sensible root package?
7. **Task graph**: Do `bootRun` and `bootJar` exist on the right module? Do build and tests run?

Useful diagnostic commands, run from the root project:

```bash
./gradlew --version
./gradlew projects
./gradlew tasks
./gradlew dependencies --configuration runtimeClasspath
./gradlew test
./gradlew bootJar
```

With multi-module builds, target the specific module explicitly rather than assuming tasks exist at root:

```bash
./gradlew :orders-api:tasks
./gradlew :orders-api:dependencies --configuration runtimeClasspath
./gradlew :orders-api:bootRun
```

These commands print different output depending on the project/Gradle version; there is no single fixed stdout across all projects. The `bootRun` command keeps the application process running until you stop it—this is not a hung build error. Check the Java/Gradle version if a command fails before randomly changing plugin versions.

## 12. Common Errors and How to Handle Them

| Symptom | Possible cause | How to check/fix |
|---|---|---|
| `Plugin [id: 'org.springframework.boot'] was not found` | Missing plugin repository, wrong ID/version, network or proxy issue | Check `pluginManagement.repositories`, plugin version, and Plugin Portal access |
| `Could not find ... spring-boot-starter-web` | Missing dependency repository or missing version management for versionless dependency | Check `dependencyResolutionManagement.repositories`/`repositories` and BOM |
| `Build was configured to prefer settings repositories...` or forbidden repository error | `FAIL_ON_PROJECT_REPOS` is set but `build.gradle` still has `repositories` | Remove the project-level repository block or intentionally change settings policy |
| `Task 'bootRun' not found` | Boot plugin not applied to the target project, or invoked on the wrong module | Check `plugins` and `./gradlew :module:tasks` |
| `Task 'bootJar' not found` | Missing Java/Boot plugin or invoked task at root instead of the subproject app | Check module configuration and invoke `:orders-api:bootJar` |
| `Project with path ':shared-domain' could not be found` | Forgot `include 'shared-domain'` or module name mismatch | Fix `settings.gradle` and directory structure |
| `Could not find method implementation()` | Java plugin not applied or dependency declared at the wrong level | Check `plugins { id 'java' }` and `dependencies` placement |
| Kotlin DSL errors on `id 'java'` or `implementation '...'` | Copied Groovy syntax into `.kts` | Change to `id("java")` / `implementation("...")` or use a `.gradle` file |
| `No matching toolchains found` | Machine lacks the required JDK or no toolchain resolver is configured | Check JDK 17, Java toolchain, and `./gradlew --version` |
| Tests do not run on JUnit Jupiter | Missing `useJUnitPlatform()`, missing test dependencies, or no tests | Check `tasks.named('test')`, `testImplementation`, and test reports |
| Library module unexpectedly builds a Boot executable | Boot plugin applied to every project | Apply Boot plugin only to application modules; use `java-library` for libraries |
| JAR filename differs from expected | Different root/project name, version, or `bootJar.archiveFileName` | Check `rootProject.name`, `version`, and `build/libs/` |

Two important troubleshooting principles:

**Do not change versions arbitrarily.** If a build fails, classify the error: plugin resolution, dependency resolution, Java toolchain, source compilation, test, or packaging. Each layer has its own logs and inspection steps.

**Do not run `clean` to fix every configuration error.** `clean` deletes outputs; it does not fix a missing `include`, wrong repository, missing plugin, wrong DSL, or wrong Java version. Read the configuration in the right file first.

## 13. Checklist for Designing a Clean Gradle Structure

- **Settings**: declare a stable root name; `include` all required modules; ensure plugin and dependency repositories match team policy.
- **Project build**: each module applies the right plugins; Boot apps have the Java plugin + Spring Boot plugin; libraries typically do not need the Boot executable plugin.
- **Dependencies**: starters/third-party libraries are in the proper configurations; versions are intentionally managed via BOM/platform/constraints.
- **Java**: toolchain matches the Spring Boot version, Gradle Wrapper, and deployment environment.
- **Tests**: projects have test dependencies and the test task is configured for the right test framework.
- **Build output**: know how to run `bootRun`, `bootJar`, `test`, `build`; know where to inspect `build/libs` and reports.
- **Multi-module**: root settings lists all modules; each build file manages its own role; inter-module dependencies use `project(':...')`.
- **Reproducibility**: commit the wrapper, settings, build scripts, and source code; avoid committing outputs/caches/secrets; CI uses the wrapper.

### Official Documentation

- [Gradle User Manual — Structuring and Organizing Projects](https://docs.gradle.org/current/userguide/organizing_gradle_projects.html)
- [Gradle User Manual — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle User Manual — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html)
- [Gradle User Manual — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Spring Boot 3.5 Gradle Plugin — Getting Started](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html)
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)

**Remember:** `settings.gradle` **defines the build and its projects**; `build.gradle` **defines how to build a single project**. When scaling from single-module to multi-module, keep each file's role clear, configure repositories/plugins consistently, apply the Spring Boot plugin only to the right modules, and verify through the Gradle Wrapper.

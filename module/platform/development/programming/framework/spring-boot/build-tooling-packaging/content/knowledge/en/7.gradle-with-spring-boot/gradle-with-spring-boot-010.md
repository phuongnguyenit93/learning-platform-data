# Distinguishing Plugin Repositories from Library Repositories in Gradle and Spring Boot

## 1. Goal and Opening Scenario

In a Spring Boot project using Gradle, adding `mavenCentral()` to `build.gradle` sometimes **fails to resolve** the error `Plugin [id: 'org.springframework.boot'] was not found`. Conversely, configuring `gradlePluginPortal()` to download the Spring Boot Gradle plugin **does not mean** libraries like `spring-boot-starter-web`, Jackson, or JDBC drivers now have a repository.

The reason: Gradle has distinct **artifact resolution scopes**. Some repositories serve **plugins that run build logic**; other repositories serve **libraries that the application compiles against, tests against, and runs with**.

After this lesson, you will be able to:

1. Distinguish Gradle **plugin ID**, **plugin marker**, **plugin implementation**, and **application library**.
2. Recognize that `pluginManagement.repositories` in settings serves `plugins { }`; `dependencyResolutionManagement.repositories` or project `repositories` serves `dependencies { }`.
3. Identify `buildscript.repositories` as a separate mechanism for legacy plugin configuration.
4. Write a runnable Spring Boot Gradle configuration on Linux/Windows and verify which repositories are actually used.
5. Fix missing plugin, missing dependency, missing authentication, bad metadata, or version incompatibility errors without randomly sprinkling repositories everywhere.

**Example versions:** Spring Boot Gradle plugin `3.3.5`, Dependency Management plugin `1.1.6`, Java 17. They illustrate a consistent configuration, **not a recommendation for the latest release**. For real projects, follow the Spring Boot, Gradle Wrapper, and JDK versions approved by your project.

## 2. Two Core Artifact Types and One Commonly Confused One

| Item | Example | When is it used? |
| --- | --- | --- |
| **Gradle plugin** | `id 'org.springframework.boot' version '3.3.5'` | When Gradle configures the build, creating `bootJar`, `bootRun`, and needed integrations |
| **Plugin marker** | `org.springframework.boot:org.springframework.boot.gradle.plugin:3.3.5` | Helps Gradle find the plugin's implementation from a plugin ID and version |
| **Plugin implementation** | `org.springframework.boot:spring-boot-gradle-plugin:3.3.5` | JAR containing plugin code running in the build environment, possibly with its own dependencies |
| **Library dependency** | `org.springframework.boot:spring-boot-starter-web` | Added to the classpath of app/test code along with transitively pulled dependencies |

A plugin and a library may both be published as Maven artifacts, yet they **do not share the same job**. Sharing the `org.springframework.boot` prefix does not turn a plugin into a Spring Boot starter.

**Plugin markers** typically follow the coordinate convention `<plugin-id>:<plugin-id>.gradle.plugin:<version>`, pointing to the implementation module. For example, the marker for `org.springframework.boot` points to the `spring-boot-gradle-plugin` JAR. Some plugins use different resolution setups, so not every plugin has a marker discoverable in an arbitrary Maven repository.

Conversely, `implementation 'org.springframework.boot:spring-boot-starter-web'` only requests an application library. It **does not apply** the `org.springframework.boot` Gradle plugin. If you need `bootJar` or `bootRun`, you must apply the plugin separately.

## 3. Diagram of Repository Scopes

~~~text
Gradle Wrapper (gradlew / gradlew.bat)
    |
    v
settings.gradle or settings.gradle.kts
    |
    +-- pluginManagement {
    |       repositories { ... }
    |   }                           -> Resolves plugins { id(...) version ... }
    |                                -> Plugin marker + implementation + transitives
    |
    +-- dependencyResolutionManagement {
    |       repositories { ... }
    |   }                           -> implementation / runtimeOnly / testImplementation ...
    |                                -> Direct and transitive project libraries
    v
build.gradle or build.gradle.kts
    |
    +-- plugins { ... }             -> Uses plugin resolver from settings
    +-- dependencies { ... }        -> Uses dependency resolver from project/settings
    +-- repositories { ... }        -> Library source, if policy allows
    |
    +-- buildscript {
            repositories { ... }    -> Legacy build script classpath
            dependencies { ... }
        }
~~~

Three key independent scopes to remember:

- **Plugin DSL:** configured in `pluginManagement.repositories` inside `settings.gradle[.kts]`. `plugins { }` in projects uses this mechanism.
- **Project dependencies:** configured in `dependencyResolutionManagement.repositories` in settings or project `repositories` (governed by `repositoriesMode`).
- **Legacy buildscript classpath:** `buildscript.repositories` configuration serves artifacts declared via `buildscript.dependencies.classpath`.

Do not confuse those scopes with `distributionUrl` of the **Gradle Wrapper**, sources for **Java toolchain** provisioning, or `publishing.repositories` which is the **publish target** for artifacts. Those configurations have distinct roles.

## 4. Where to Find Gradle Plugins: `pluginManagement.repositories`

Example Spring Boot build script using the Plugins DSL:

~~~groovy
// build.gradle (excerpt)
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}
~~~

Gradle must resolve two external plugins by plugin ID/version. The place to specify repositories for this request is **settings**:

~~~groovy
// settings.gradle - Groovy DSL
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

Corresponding Kotlin DSL:

~~~kotlin
// settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
~~~

`gradlePluginPortal()` accesses the Gradle Plugin Portal, where many markers and plugins are published. `mavenCentral()` is Maven Central, which may be needed for a plugin's implementation or dependencies under certain publishing setups. **Adding Maven Central here does not provide a dependency repository for the application.**

If a project **does not declare** `pluginManagement.repositories`, the Gradle Plugins DSL normally defaults to the Gradle Plugin Portal for external plugins. If a project **explicitly declares** a custom repository list, do not assume the plugin portal is still appended automatically after your list; list every source your project/mirror actually requires.

The `pluginManagement { }` block must appear at the top of the settings file per Gradle rules (except valid `import` statements). In Kotlin DSL, `import` statements go at the top followed by this block. Putting other configuration statements before `pluginManagement` can cause settings compilation/parsing to fail.

**Plugin testing note:** `plugins { id 'java' }` working does not prove plugin repositories are configured right: `java` is a **Gradle core plugin** requiring no external download. Test an external plugin like `org.springframework.boot` to verify actual connectivity.

## 5. Where to Find Application Libraries: Project Repositories

Example libraries in `build.gradle`:

~~~groovy
// build.gradle (excerpt)
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    runtimeOnly 'com.h2database:h2'
}
~~~

These are **libraries**, not plugins. Gradle uses dependency repositories in settings or the project to resolve requested/BOM-managed versions along with metadata and transitive artifacts.

### Approach A: Centralizing in Settings

~~~groovy
// settings.gradle - after pluginManagement
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
~~~

This lets a multi-project build share one library download source list. Maven Central hosts standard Spring Boot starters; internal systems can replace it with a trusted mirror per organizational requirements.

To **enforce that every project uses settings repositories**, add:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

When `FAIL_ON_PROJECT_REPOS` is active, **do not also declare** `repositories { mavenCentral() }` in `build.gradle`: even with the same URL, Gradle treats it as a forbidden project repository. Plugins that inject repositories automatically can trigger the same error; locate the source configuration and handle it properly.

`PREFER_SETTINGS` and `PREFER_PROJECT` modes follow different precedence rules; choose based on your project's governance strategy. Do not treat `FAIL_ON_PROJECT_REPOS` as a "Maven Central error": it is a **repository policy violation**.

### Approach B: Declaring Separately in `build.gradle`

~~~groovy
// build.gradle, if settings does not forbid project repositories
repositories {
    mavenCentral()
}
~~~

Approach B works well for simple Gradle builds or legacy setups. Do not combine it with `repositoriesMode.FAIL_ON_PROJECT_REPOS` in settings.

**Kotlin DSL:** `repositories { mavenCentral() }` works in `build.gradle.kts`; in `settings.gradle.kts`, `dependencyResolutionManagement { repositories { mavenCentral() } }` has the same meaning. When using `RepositoriesMode`, import `org.gradle.api.initialization.resolve.RepositoriesMode` at the top of Kotlin settings.

### BOM Differs from Repository

In Spring Boot, **a BOM manages versions** of many starters/libraries, yet **does not specify where to download artifacts**. For instance, `org.springframework.boot:spring-boot-dependencies` supplies dependency versions, while the build still needs Maven Central/a mirror to download actual modules.

Declaring `spring-boot-starter-web` without a version works when the Spring Boot BOM is managed via an appropriate plugin or `platform()`. Still, a BOM **does not add** libraries by itself: a direct or transitive dependency must bring the module onto the classpath.

## 6. A Buildable Spring Boot Gradle Example in Groovy DSL

This example includes enough files to verify plugin resolution and library resolution independently. It assumes a **compatible Gradle Wrapper**, Internet or valid mirror access, and JDK 17 to compile/run. Version numbers are chosen consistently for learning. If your project already has build files, merge only the necessary parts instead of overwriting the entire configuration.

### 6.1 `settings.gradle`

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'repository-scopes-demo'
~~~

This is the single place defining plugin repositories and dependency repositories. `pluginManagement` precedes other configuration blocks; `FAIL_ON_PROJECT_REPOS` prevents project modules from inserting off-policy repositories.

### 6.2 `build.gradle`

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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Spring Boot Gradle plugin integrates with `io.spring.dependency-management`: when both plugins are applied together, the `spring-boot-dependencies` BOM matching the Spring Boot plugin version manages many library versions. Hence `spring-boot-starter` and `spring-boot-starter-test` do not need explicit versions in this example.

**Do not** add a top-level `repositories { mavenCentral() }` in this file, because settings enabled `FAIL_ON_PROJECT_REPOS`. The Spring Boot plugin **does not replace** library starters, and library starters **do not apply** the Gradle plugin.

### 6.3 `src/main/java/com/example/demo/DemoApplication.java`

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

This is a complete Java class with matching filename and package. Because the only starter is `spring-boot-starter`, the application may start and exit rather than opening an HTTP port; that is **not a dependency download failure**.

### 6.4 Running via the Gradle Wrapper

Linux/bash:

~~~bash
./gradlew --version
./gradlew help
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean build
ls -lh build/libs/
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat help
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat clean build
Get-ChildItem .\build\libs\
~~~

- `--version`: prints the active Gradle and JVM versions, helping detect incompatibilities.
- `help`: makes Gradle read settings/build scripts, forcing resolution of plugins needed for configuration. It **does not guarantee** all runtime libraries are downloaded.
- `dependencies --configuration runtimeClasspath`: resolves and prints the application's dependency graph. Requires an appropriate Java plugin creating `runtimeClasspath`.
- `clean build`: compiles, tests, and packages per the task graph; with the Spring Boot plugin and a valid main class, produces the executable JAR in `build/libs/`.

Logs and task counts vary by environment; success is typically indicated by `BUILD SUCCESSFUL`, though there is no fixed stdout. If running offline/cached, a passing build **does not prove** remote repositories are currently reachable.

## 7. Kotlin DSL Equivalent

Choose **one DSL** for the project; do not place both `settings.gradle` and `settings.gradle.kts` in the same root simultaneously.

**File `settings.gradle.kts`:**

~~~kotlin
import org.gradle.api.initialization.resolve.RepositoriesMode

pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}

rootProject.name = "repository-scopes-demo"
~~~

**File `build.gradle.kts`:**

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Reuse the Java file from section 6. Even in Kotlin DSL, `plugins` and `dependencies` still resolve from **two distinct repository scopes** in settings; the DSL only changes declaration syntax.

## 8. Plugin Markers: Why Can a Plugin Still Be Not Found Even When Its JAR Exists?

When encountering:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}
~~~

Gradle's Plugin DSL typically looks up:

~~~text
org.springframework.boot:org.springframework.boot.gradle.plugin:3.3.5
                    -> marker POM
                    -> org.springframework.boot:spring-boot-gradle-plugin:3.3.5
                    -> plugin implementation + transitive dependencies
~~~

An internal Maven mirror might store `spring-boot-gradle-plugin` yet **lack the plugin marker**. The result is `Plugin ... was not found` when requested by ID, even though the implementation JAR is downloadable by exact coordinates.

Proper solutions:

1. Mirror/publish **the complete marker, implementation, and related dependencies** into the plugin repository.
2. Configure `gradlePluginPortal()` or another marker-hosting repository per organizational policy.
3. If a plugin implementation has no marker, use `pluginManagement.resolutionStrategy` to map the plugin ID to a specific module; use only when you know the exact implementation/version.

**Standalone snippet** illustrating option 3 for the Spring Boot plugin when Maven Central is the approved implementation source:

~~~groovy
// settings.gradle - alternative to standard pluginManagement when genuinely needed
pluginManagement {
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'org.springframework.boot') {
                useModule(
                    'org.springframework.boot:spring-boot-gradle-plugin:' +
                    requested.version
                )
            }
        }
    }
    repositories {
        mavenCentral()
    }
}
~~~

This assumes the plugin request specifies a version. `useModule` redirects resolution to the implementation module instead of the marker for that ID; other plugins still need appropriate repositories/markers. This **is not a required setup** for normal Spring Boot projects with access to the Plugin Portal.

## 9. Plugins DSL vs. Legacy `buildscript.repositories`

Before the modern `plugins { }` block, many projects used:

~~~groovy
// build.gradle - snippet illustrating the legacy style
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath 'org.springframework.boot:spring-boot-gradle-plugin:3.3.5'
    }
}

apply plugin: 'java'
apply plugin: 'org.springframework.boot'
~~~

This resolves the implementation artifact directly on `buildscript.classpath` using **`buildscript.repositories`**, then applies the plugin with `apply plugin`. **It does not require a plugin marker under Plugins DSL rules.**

The legacy snippet above only illustrates plugin resolution; a full application build still needs dependency repositories and dependency management/BOM as required by the project. Do not mix both plugin application styles for the same plugin just to troubleshoot errors.

Comparison:

| Mechanism | Plugin declaration | Repository supplying plugin artifacts |
| --- | --- | --- |
| Plugins DSL | `plugins { id("org.springframework.boot") version "..." }` | `pluginManagement.repositories` in settings |
| Legacy `buildscript` | `buildscript.dependencies.classpath(...)` then `apply plugin` | `buildscript.repositories` in build script |
| Application libraries | `dependencies { implementation(...) }` | `dependencyResolutionManagement.repositories` or project `repositories` |

Thus, if an error mentions configuration `classpath`, inspect the **classpath context**: is it the legacy buildscript classpath or another part of the build/plugins? If the error mentions `Plugin [id...]`, start at the plugin resolver. If it occurs on `runtimeClasspath` or `compileClasspath`, inspect library repositories and versions.

## 10. Why Does `repositoriesMode` Make a Seemingly Correct Configuration Fail?

When designing multi-module builds, teams often place dependency repositories **centrally in settings**:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
    }
}
~~~

While a submodule still contains:

~~~groovy
// app/build.gradle - invalid when settings forbids project repositories
repositories {
    mavenCentral()
}
~~~

Gradle rejects the build for **disallowing project repositories**, even though both say `mavenCentral()`. This is a policy violation, not a DNS error or missing artifact. The fix is to **move required sources into settings**, remove project-level declarations, and address any plugins that inject repositories.

Other Gradle modes offer different policies:

- `PREFER_SETTINGS`: prefers repositories declared in settings; project repositories do not control resolution in the same way.
- `PREFER_PROJECT`: project repositories take precedence when declared.
- `FAIL_ON_PROJECT_REPOS`: enforces centralized policy by failing whenever a project adds repositories under this rule.

Pick a mode based on build reproducibility and download-source governance needs. **Do not use `repositoriesMode` as a substitute for `pluginManagement`**; the plugin resolver is a separate flow.

## 11. Repositories for Wrapper, Java Toolchain, Publishing, and Version Catalogs

### Gradle Wrapper

`gradle/wrapper/gradle-wrapper.properties` uses `distributionUrl` to download the **Gradle distribution**, e.g., as configured by the `wrapper` task. If the Wrapper fails to download the Gradle distribution, editing `dependencyResolutionManagement.repositories` will not fix the distribution URL; inspect network, proxy, CA certificates, or your internal Gradle mirror.

### Java Toolchain

When `java.toolchain.languageVersion` requests an uninstalled JDK, Gradle uses detection or **JDK provisioning** via configured resolvers. Maven Central for application libraries **does not supply** JDKs. `No matching Java installation` belongs to the toolchain/JDK layer, not a missing `spring-boot-starter`.

### Publishing Repositories

`publishing.repositories` from the `maven-publish` plugin specifies **where to upload artifacts** when publishing; it is not where plugins or runtime libraries are downloaded. When publishing artifacts, choose which JAR to publish and configure proper credentials rather than reusing publish destinations as resolution repositories.

### Version Catalogs

In `gradle/libs.versions.toml`, teams can define aliases for plugins and libraries:

~~~toml
[versions]
boot = "3.3.5"

[plugins]
boot = { id = "org.springframework.boot", version.ref = "boot" }

[libraries]
boot-starter = { module = "org.springframework.boot:spring-boot-starter" }
~~~

When `build.gradle.kts` invokes `alias(libs.plugins.boot)`, resolution still uses **`pluginManagement.repositories`**. When it invokes `implementation(libs.boot.starter)`, resolution still uses **dependency repositories**. Catalogs manage **coordinates/versions**, without altering repository scopes. The library example omits a version assuming the project already configures a Spring Boot BOM/dependency management.

## 12. Enterprise Mirrors, Credentials, and Managing Download Sources

In companies using Artifactory/Nexus or internal mirrors, two download paths usually differ:

- **Plugin mirror:** must contain plugin markers, implementations, and transitive dependencies. Configured in `pluginManagement.repositories`.
- **Library mirror:** must contain POMs/Gradle module metadata/JARs and application transitive dependencies. Configured in `dependencyResolutionManagement.repositories` or project repositories.
- **Credentials:** obtained from securely supplied Gradle properties, environment variables, or CI secret stores. Never commit usernames/passwords/tokens inside URLs, `settings.gradle`, or `build.gradle`.
- **Content filters:** when filtering by group/module, remember that markers and implementations can have different groups or coordinates. Overly narrow filters can break plugin resolution even when the implementation JAR is in the repository.
- **Gradle init scripts:** developer machines and CI runners may apply external repository configuration via init scripts; this explains why identical Gradle files can pass locally yet fail on clean CI.

Do not assume a **second** repository automatically rescues every failure from the first. Once Gradle receives module metadata from one repository yet fails to fetch the artifact, or when an exclusive content rule binds a module to a specific source, resolution does not simply "try every remaining URL". Inspect actual logs and mirror rules.

For CI, prefer projects with **explicitly declared, auditable download sources** that do not require developers to secretly add repositories in their IDE. Avoid pulling dependencies/plugins from untrusted repositories merely because one URL responds faster.

## 13. Diagnose by Error Category, Not Guesswork

On Linux/bash, from the project root directory:

~~~bash
./gradlew --version
./gradlew help --info
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency org.springframework.boot:spring-boot-starter --configuration runtimeClasspath
./gradlew clean build
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat help --info
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency org.springframework.boot:spring-boot-starter --configuration runtimeClasspath
.\gradlew.bat clean build
~~~

**Explaining the exact scope of each command:**

- `--version` prints the Gradle version and active JVM; vital for spotting Gradle/Java/plugin incompatibilities.
- `help --info` parses and configures the project, normally forcing resolution of plugins needed to configure tasks; it does not ensure all runtime dependencies are downloaded.
- `dependencies --configuration runtimeClasspath` displays the app's dependency graph and clarifies missing dependencies or selected versions.
- `dependencyInsight` traces the path and version selection reason for a module, distinguishing repository issues from conflicts/constraints.
- `clean build` verifies the full compilation, test, and packaging flow as configured.

In multi-project builds, you may need `:app:dependencies` or `:app:dependencyInsight` to inspect the right module. If a project has not applied the matching Java/JVM plugin, `runtimeClasspath` may not exist; that is a configuration issue, not a repository error.

### Common Errors Table

| Symptom | Check first | Resolution |
| --- | --- | --- |
| `Plugin [id: 'org.springframework.boot', version: '...'] was not found` | `pluginManagement.repositories`, plugin ID, version, marker | Provide Plugin Portal/mirror properly; confirm marker and implementation exist |
| `Could not find org.springframework.boot:spring-boot-starter-...` | Dependency repository and BOM/version | Provide Maven Central/mirror for dependencies; verify module has a valid version |
| `Could not resolve all files for configuration ':classpath'` | `buildscript.classpath` or actual plugin classpath | Read full error; determine whether legacy buildscript or Plugins DSL |
| `Build was configured to prefer settings repositories` or project repo error | `repositoriesMode` | Move repos to settings / remove non-compliant project repositories |
| `401 Unauthorized` or `403 Forbidden` | Authentication, repo permissions, CI secrets | Verify credentials/permissions; avoid leaking secrets into logs |
| Timeout / TLS / DNS to Plugin Portal | Network to plugin repo, proxy, certificates | Fix network/mirror properly; do not add arbitrary libraries |
| Plugin marker found, yet implementation/dependency fails | Mirror lacks module or content filter blocks it | Mirror the full artifact chain of the plugin into plugin repositories |
| `No matching variant of ...` | Gradle/JVM/plugin versions and variant metadata | Inspect Gradle API/JVM attributes in the error; likely a version incompatibility |
| `No matching Java installation` | Java toolchain/JDK | Install/configure a JDK resolver; library repos do not supply JDKs |
| Wrapper fails to download distribution | `distributionUrl` and network | Check Gradle distribution URL/proxy, not just Maven Central |

A build can "pass locally" from cache yet "fail on CI" when CI fetches fresh artifacts. To verify online resolution when warranted and connected, `--refresh-dependencies` tells Gradle to re-verify dependency metadata/cache. `--offline` relies strictly on cached artifacts, so **it never proves** remote repositories are reachable. Do not wipe all caches or enable verbose logs that expose credentials as a first step.

## 14. Experiment: Separating the Plugin Repo and Library Repo

Use the sample project from section 6 on an experimental branch; record each result and revert after completing the exercise. If artifacts are already cached, test on a clean CI runner or isolated environment to avoid misleading conclusions.

**Case A — plugin repository present, library repository missing.** Keep `pluginManagement.repositories { gradlePluginPortal() }` while removing dependency repositories in the test copy. In an uncached environment, Gradle can configure the plugins and pass `help`, then fail when `compileJava` or a task needing starters tries to resolve compile/runtime dependencies. Takeaway: resolving the plugin **does not mean** libraries can be downloaded.

**Case B — library repository present, plugin cannot resolve.** Keep `dependencyResolutionManagement.repositories { mavenCentral() }` while configuring the plugin resolver without a real marker source; the build fails **before** reaching starter resolution. Note: merely deleting `pluginManagement` usually **won't fail**, because Gradle defaults to the Plugin Portal. For a meaningful test, know which plugin resolver source is actually queried in your environment.

**Case C — both repositories in their proper scopes.** Restore `pluginManagement.repositories { gradlePluginPortal(); mavenCentral() }` and `dependencyResolutionManagement.repositories { mavenCentral() }`. With `FAIL_ON_PROJECT_REPOS` enabled, ensure build scripts declare no project repos. Then run `help`, `dependencies`, and `clean build` to verify in order: **plugins → libraries → build/tests**.

For every experiment, read the actual error: missing artifact, blocked network, authentication failure, missing marker, wrong Java/Gradle variant, or configuration typo can all look similar at first glance.

## 15. Common Misconceptions and Key Takeaways

| Misconception | Accurate understanding |
| --- | --- |
| "Having `mavenCentral()` in `build.gradle` finds every Gradle plugin." | Plugins DSL uses `pluginManagement.repositories` in settings. |
| "Only `gradlePluginPortal()` is enough for starters and drivers to resolve." | Starters/drivers need dependency repositories, typically Maven Central or a mirror. |
| "`buildscript.repositories` and `pluginManagement.repositories` are the same." | Legacy classpath and Plugins DSL use different resolution paths. |
| "Plugin `java` resolving proves Plugin Portal works." | `java` is a Gradle core plugin and is not downloaded externally. |
| "If `FAIL_ON_PROJECT_REPOS` errors, turning it off is the fix." | Find which project/plugin added a repo and standardize per settings policy first. |
| "A BOM provides the repository too." | A BOM manages dependency **versions**; repositories locate **artifacts**. |
| "A version catalog automatically specifies where to download plugins and libraries." | Catalogs hold IDs/modules/versions; repository scopes remain independent. |
| "`gradlew help` succeeding guarantees `gradlew build` will succeed." | `help` does not validate all compile/runtime/test dependencies. |
| "Errors downloading the JDK or Gradle Wrapper mean Maven Central lacks starters." | JDK provisioning and Gradle distributions use separate download flows. |
| "Every `No matching variant` error is a repository problem." | Many are JDK/Gradle/plugin API compatibility or variant metadata issues. |

## 16. Checklist for Real Projects

- [ ] Know whether the project uses `settings.gradle` or `settings.gradle.kts`, `build.gradle` or `build.gradle.kts`, and its Gradle Wrapper version.
- [ ] Configure `pluginManagement.repositories` appropriately for external plugins like the Spring Boot Gradle plugin and dependency management plugin.
- [ ] Have explicit dependency repositories in settings **or** project; check `repositoriesMode` before adding a new repository.
- [ ] Check whether the project uses legacy `buildscript { }` so you do not edit the wrong scope.
- [ ] If using corporate mirrors, verify plugin markers, implementations, transitive dependencies, and app libraries are completely mirrored.
- [ ] Distinguish plugin resolution, library resolution, network/auth, Wrapper distribution, and Java toolchain errors.
- [ ] Confirm Gradle configures plugins via `help`, resolves libraries via `dependencies`/`dependencyInsight`, and builds via `clean build`.
- [ ] Compare on CI with compatible Gradle/JDK versions; do not treat a local developer cache as proof that remote repositories work.
- [ ] Never commit secrets, add untrusted repositories, or bypass governance policies just to mask a specific error.

You have mastered this lesson when, upon seeing `Plugin ... was not found` and `Could not find ...starter...`, you can **immediately explain why they belong to two different repository scopes** and pinpoint the exact file/configuration to fix in a Spring Boot Gradle project.

## Official Documentation

- [Gradle – Working with Plugins](https://docs.gradle.org/current/userguide/plugins.html)
- [Gradle – Plugin Management](https://docs.gradle.org/current/userguide/plugins_intermediate.html#sec:plugin_management)
- [Gradle – Declaring Repositories](https://docs.gradle.org/current/userguide/declaring_repositories.html)
- [Gradle – Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle – Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Spring Boot – Gradle Plugin: Getting Started](https://docs.spring.io/spring-boot/gradle-plugin/getting-started.html)
- [Spring Boot – Gradle Plugin: Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
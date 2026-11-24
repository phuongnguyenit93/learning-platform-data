# Managing Plugin Versions via pluginManagement and apply false in Gradle

## 1. Goal and Context

A Spring Boot project may consist of multiple Gradle subprojects: **:app** is the Spring Boot application producing an executable JAR; **:core** is a standard Java library. When each module declares plugin versions independently, they may accidentally use different versions of the Spring Boot Gradle Plugin, or a library module might have the Boot plugin applied and receive unnecessary tasks.

Gradle provides two common ways to **centralize plugin version management**:

1. **pluginManagement { ... }** in **settings.gradle**: defines plugin resolution repositories, default versions per plugin ID, and build plugin resolution rules.
2. **apply false** in **plugins { ... }** of the **root build.gradle**: Gradle resolves the plugin and places it on the plugin classpath, **without applying** it to the root; each subproject that needs the plugin requests it by ID.

Both mechanisms share versions while letting **each project decide which plugins are applied**. They do not replace declaring application dependencies, BOMs, or Java configuration.

This lesson uses **Gradle 8.5, Java 17, Spring Boot Gradle Plugin 3.3.5, and io.spring.dependency-management 1.1.6** as an illustrative version set. This is an intentional example for Gradle 8.x/Spring Boot 3.3, not a claim of the latest release. When using newer versions, verify compatibility requirements across the Gradle Wrapper, JDK, Spring Boot, and plugins.

## 2. Plugins vs. Application Dependencies

Look at part of a Spring Boot application's **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

In this example:

- **plugins** holds **Gradle plugins**. Plugins can create tasks, extensions, and build rules. **id 'java'** is a core plugin bundled with Gradle, so it has no version. **org.springframework.boot** is an external plugin that needs a specific version or version information from shared configuration.
- **dependencies** holds **application libraries**. Starters are dependencies used by Java code at runtime, not Gradle plugins.
- **repositories { mavenCentral() }** in `build.gradle` resolves project dependencies. The repository for resolving the **plugins DSL** is configured separately via **pluginManagement.repositories** (or defaults to the Gradle Plugin Portal).
- **io.spring.dependency-management** is a plugin that helps manage dependency versions via a BOM; do not confuse its name with the **pluginManagement** block in `settings.gradle`.

**Fundamental rule:** **Plugin** versions affect the Gradle logic used to build. **Dependency** versions affect the libraries appearing on the compile/runtime classpath. You cannot change one by editing the configuration of the other.

## 3. In What Order Does Gradle Process Configuration Blocks?

~~~text
./gradlew :app:bootJar
          |
          v
Initialization
  ├── Read settings.gradle
  ├── pluginManagement: plugin repos, versions, resolution rules
  └── Read rootProject.name, include 'app', 'core'
          |
          v
Configuration
  ├── Read build.gradle of root and subprojects
  ├── Resolve/apply plugins in each project's plugins block
  ├── :app receives Java, Spring Boot, dependency-management
  └── :core only receives java-library
          |
          v
Execution
  └── Run task graph for :app:bootJar
~~~

**pluginManagement must be the first block in settings.gradle(.kts)** when present, because it configures plugin resolution early. A **plugins { ... }** block in a **build.gradle** requests applying plugins on **that corresponding Project**. A **plugins { ... }** block placed directly in **settings.gradle** is for **Settings plugins** and does not automatically apply the Boot plugin to subprojects.

**Syntax note:** The Plugins DSL in `build.gradle` has strict rules on placement and expressions. It must appear at the top of the script as specified and cannot be placed inside arbitrary loops or conditionals. When you need to read versions from properties or dynamic logic, **pluginManagement** is the appropriate place.

Plugin resolution typically follows **plugin ID → plugin marker artifact → plugin implementation**. Gradle searches allowed repositories, selects a version, puts the plugin on the classpath, and applies the plugin as requested by the build script. Each step has a distinct meaning when diagnosing errors.

## 4. Approach A: Declaring Default Versions with pluginManagement

Create a build with two modules: **app** running Spring Boot, and **core** as a Java library. Root **settings.gradle** (Groovy DSL):

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
    plugins {
        id 'org.springframework.boot' version '3.3.5'
        id 'io.spring.dependency-management' version '1.1.6'
    }
}

rootProject.name = 'plugin-versions-demo'
include 'app', 'core'
~~~

Each part has its own role:

1. **pluginManagement.repositories**: tells Gradle where to search for plugins. Here, it is the Gradle Plugin Portal. If you declare a custom repository list, include **gradlePluginPortal()** when you still want to use the portal.
2. **pluginManagement.plugins**: maps **plugin ID → default version** for plugin requests that omit a version.
3. **rootProject.name**: root project name; does not dictate plugin versions.
4. **include 'app', 'core'**: informs Gradle of the two subprojects in the build; does not mean both subprojects automatically use the Boot plugin.

Key point: **pluginManagement.plugins does not apply plugins automatically**. Declaring the Spring Boot version in settings only supplies the version for projects that later declare **plugins { id 'org.springframework.boot' }**.

### 4.1. app/build.gradle: Spring Boot Application

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is the **complete sample build.gradle** for `app`. The two external plugins **omit versions in app** because `settings.gradle` provides default versions. `app` actually applies **org.springframework.boot**, so it receives Boot tasks such as **bootJar** and **bootRun** when paired with the Java plugin.

Because `app` also applies **io.spring.dependency-management**, the Spring Boot Gradle Plugin automatically integrates the **spring-boot-dependencies BOM** for `app`. Spring Boot dependencies managed by the BOM can omit versions in the `dependencies` block; this is **dependency version management**, completely distinct from `pluginManagement`.

### 4.2. core/build.gradle: Pure Java Library

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

This is the **complete build.gradle** for `core` in this example with no external dependencies. The **java-library** plugin already brings Java plugin capabilities; `core` can build a regular **jar** and be depended upon by `app` via **project(':core')**.

`core` **does not apply** the Boot plugin even though `settings` defines the Boot version. Therefore `core` **does not have bootJar**. This is the proper boundary: the application produces an executable Spring Boot JAR; the shared library outputs a plain JAR.

### 4.3. "Default Version" Does Not Mean "Hard Lock"

`pluginManagement.plugins` provides a **default** when a plugin request omits a version. It **is not a mechanism that strictly prevents every module from requesting a different version**. If you need to enforce a repository-wide policy, apply build conventions, convention plugins, configuration checks, or properly designed resolution rules.

Avoid having a module explicitly specify a different version from the default in settings without clear intent, as it can cause inconsistent versions or classpath conflicts.

## 5. Approach B: Defining Plugins at Root with apply false

An alternative approach is **not declaring default versions in pluginManagement**, and instead declaring plugins in the **root build.gradle**:

**settings.gradle**:

~~~groovy
rootProject.name = 'plugin-versions-demo'
include 'app', 'core'
~~~

**Root build.gradle**:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5' apply false
    id 'io.spring.dependency-management' version '1.1.6' apply false
}
~~~

The two files **app/build.gradle** and **core/build.gradle** from section 4 remain unchanged. Root `build.gradle` specifies versions and uses **apply false** so the plugins are **not applied to root**. The `app` subproject continues to write:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}
~~~

The plugin lines without versions in `app` work because those versions are already on the plugin classpath provided by the parent/root build. `core` does not request the Boot plugin, so Boot is not applied to it.

**What does apply false mean exactly?**

- Gradle **resolves the plugin** by ID/version and places it on the plugin classpath.
- Gradle **does not apply the plugin** to the project containing the `apply false` request (here, the root).
- The plugin will be **applied** in another project if that project explicitly requests **id 'org.springframework.boot'**.
- `apply false` **does not automatically apply to all subprojects**, nor does it mean "disable the plugin for everyone".

If root omits **apply false**:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}
~~~

then the Boot plugin is **applied to root**, even though root is not an application. This can create unnecessary Boot tasks/configurations, or even packaging errors when root has no suitable main class. Avoid applying the Boot plugin to root just to share its version.

**A note on resolution timing:** A root **plugins { id ... apply false }** block is still a **plugin request**, so Gradle may have to download the plugin during configuration even if root does not use tasks provided by that plugin. By contrast, **pluginManagement.plugins** primarily declares default versions in Settings and does not create plugin requests for every listed plugin.

## 6. Comparing pluginManagement and apply false

| Criterion | pluginManagement | root plugins + apply false |
| --- | --- | --- |
| Location | **settings.gradle**, first block | Root **build.gradle** |
| Defines default version? | Yes, via **pluginManagement.plugins** | Selects version of plugin resolved at root |
| Resolves plugin just from declaration? | Declaring default versions does not apply or force resolving every plugin | **plugins request** may resolve the plugin despite `apply false` |
| Applies plugin to root? | No | **No** when using `apply false` |
| Applies plugin to subprojects? | No, subprojects must request it | No, subprojects must request it |
| Declares plugin repositories? | Yes, via **repositories** | Not a function of `apply false` |
| Customizes plugin ID → implementation mapping? | Yes, via **resolutionStrategy** | Not a function of `apply false` |
| Suitable for multi-project builds? | Yes | Yes |
| Replaces dependency BOM? | No | No |

**Which approach to choose?** If your goals include internal plugin repositories, versions from `gradle.properties`, and plugin resolution policies, use **pluginManagement**. If your main goal is letting root share an explicit set of plugins/versions without running a Boot application at root, **apply false** is concise. Both approaches can coexist with a clear purpose, but do not duplicate versions in two places where they can drift out of sync.

In a **single-module** project, you can declare plugins and their versions directly in the application's **build.gradle** without needing either mechanism. They become much more valuable when multiple projects share plugins.

## 7. Runnable Practice Exercise: A Spring Boot App Using a Core Library

### 7.1. Directory Structure

~~~text
plugin-versions-demo/
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── app/
│   ├── build.gradle
│   └── src/
│       ├── main/java/com/example/app/PluginVersionApplication.java
│       └── test/java/com/example/app/MessageServiceTest.java
└── core/
    ├── build.gradle
    └── src/main/java/com/example/core/MessageService.java
~~~

With **Approach A**, use **settings.gradle + app/build.gradle + core/build.gradle** from section 4. With **Approach B**, use **settings.gradle + root build.gradle** from section 5 and keep the `app`/`core` build scripts unchanged. Do not create both version sets in the same project.

The example requires **Gradle Wrapper 8.5**, **JDK 17**, and repository connectivity to download plugins/dependencies. If creating the directory manually, the wrapper must be generated from an installed Gradle or copied from a compatible Gradle skeleton; merely writing **gradlew** in a directory tree does not create a working wrapper.

### 7.2. Java Class in the core Library

File **core/src/main/java/com/example/core/MessageService.java**:

~~~java
package com.example.core;

public final class MessageService {
    public String message() {
        return "PLUGIN_VERSION_OK";
    }
}
~~~

This is a plain Java class with no Spring Boot dependency. **core** uses the `java-library` plugin, compiles the class, and packages it into a regular JAR.

### 7.3. Spring Boot Application in app

File **app/src/main/java/com/example/app/PluginVersionApplication.java**:

~~~java
package com.example.app;

import com.example.core.MessageService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PluginVersionApplication implements CommandLineRunner {
    public static void main(String[] args) {
        SpringApplication.run(PluginVersionApplication.class, args);
    }

    @Override
    public void run(String... args) {
        System.out.println(new MessageService().message());
    }
}
~~~

**@SpringBootApplication** bootstraps the Spring Boot application. The class implements **CommandLineRunner**, so Spring Boot calls **run** after the application context is initialized. `MessageService` is a plain Java class instantiated directly; no separate Spring bean declaration is required.

File **app/src/test/java/com/example/app/MessageServiceTest.java**:

~~~java
package com.example.app;

import com.example.core.MessageService;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageServiceTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("PLUGIN_VERSION_OK", new MessageService().message());
    }
}
~~~

The test belongs to the `app` module and uses JUnit Jupiter via **spring-boot-starter-test**. With **tasks.named('test') { useJUnitPlatform() }**, Gradle runs tests using JUnit Platform.

### 7.4. Verification and Execution Commands

From the root directory:

~~~bash
./gradlew projects
./gradlew :app:tasks --all
./gradlew :core:tasks --all
./gradlew :app:test :app:bootJar
./gradlew :app:bootRun
~~~

On Windows, replace **./gradlew** with **gradlew.bat**.

Expected **build structure** results:

- **projects** lists **:app** and **:core**.
- **:app:tasks --all** includes **bootJar** and **bootRun** because `app` actually applies the Boot plugin and Java plugin.
- **:core:tasks --all** includes Java library tasks such as **jar**, but **does not have bootJar**, because `core` does not apply the Boot plugin.
- **:app:test** runs JUnit tests and confirms `app` can access classes from `core`.
- **:app:bootJar** builds an executable Spring Boot JAR in **app/build/libs/**; the filename depends on version/project configuration.
- **:app:bootRun** executes the `CommandLineRunner`; alongside Gradle/Spring Boot logs, the program prints the line produced by code:

~~~text
PLUGIN_VERSION_OK
~~~

This example creates no HTTP endpoints and does not require port 8080, so `curl` is unnecessary. Full Gradle/Spring Boot output includes environment-dependent logs; only the `System.out.println` line above is fixed.

**Negative check:** **./gradlew :core:bootJar** will report that task `bootJar` does not exist in `:core` under the example configuration. That is proof that `core` has not applied the Spring Boot plugin, not an error to fix.

### 7.5. Verifying Dependency Versions Independently from Plugin Versions

Run:

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Both commands display the resolved dependency graph of `app`. The **io.spring.dependency-management** plugin, when paired with the Spring Boot Gradle Plugin, manages starter/test dependency versions via the Spring Boot BOM. Managing plugin versions in settings/root does not automatically alter the versions of unrelated libraries and does not mean every module automatically receives a BOM.

## 8. Reading Versions from gradle.properties in pluginManagement

In multi-person teams, putting plugin versions into **gradle.properties** can make upgrades convenient:

~~~properties
springBootPluginVersion=3.3.5
springDependencyManagementVersion=1.1.6
~~~

**settings.gradle** can use `pluginManagement` to read those properties:

~~~groovy
pluginManagement {
    def bootVersion = providers.gradleProperty('springBootPluginVersion').get()
    def depMgmtVersion = providers.gradleProperty('springDependencyManagementVersion').get()

    repositories {
        gradlePluginPortal()
    }
    plugins {
        id 'org.springframework.boot' version bootVersion
        id 'io.spring.dependency-management' version depMgmtVersion
    }
}

rootProject.name = 'plugin-versions-demo'
include 'app', 'core'
~~~

This is an **alternative version** of `settings.gradle` from section 4. Reading properties via **providers.gradleProperty** makes the version source explicit. If a property is undefined, **.get()** will fail with a missing value error; you can intentionally set a default with the Provider API if the project needs one.

**Do not copy Groovy logic with def/if into the plugins block of app/build.gradle**: project `plugins` blocks have strict syntax constraints. **pluginManagement** is designed to handle early version selection and allows more flexible version computation.

If the project uses **gradle/libs.versions.toml** (version catalog), plugin aliases are another version management option. Even when declaring plugins via aliases, **apply false** still makes sense when bringing a plugin into shared scope without applying it to root. Choose one consistent version source for the team.

## 9. Distinguishing Plugin Repositories and Dependency Repositories

These two configurations **do not substitute for each other**:

**Plugin repository** in `settings.gradle`:

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
    }
}
~~~

**Application library repository** in `app/build.gradle`:

~~~groovy
repositories {
    mavenCentral()
}
~~~

Plugin resolution uses plugin markers, while dependencies use Maven/Gradle module metadata based on dependency coordinates. Thus **Plugin [id: 'org.springframework.boot'] was not found** will generally not be fixed by simply adding **mavenCentral()** to `app/build.gradle`.

If an organization uses a private plugin repository, an illustrative configuration looks like:

~~~groovy
pluginManagement {
    repositories {
        maven {
            url = uri('https://plugins.example.org/maven')
        }
        gradlePluginPortal()
    }
}
~~~

**plugins.example.org is an example URL, not a live server**. In practice, use a real URL, proper plugin markers/implementations, and your organization's credential policy. Do not hardcode tokens/passwords into committed Gradle files.

When explicitly declaring `pluginManagement.repositories`, include all repositories you want to use; if you omit **gradlePluginPortal()**, Gradle will not automatically add the portal back.

## 10. resolutionStrategy and Internally Developed Plugins

**pluginManagement.resolutionStrategy** lets you customize how a plugin request is resolved; for example, an internal plugin with ID **com.example.build-conventions** whose implementation artifact resides at an organization-chosen Maven coordinate.

~~~groovy
pluginManagement {
    resolutionStrategy {
        eachPlugin {
            if (requested.id.id == 'com.example.build-conventions') {
                useModule('com.example.tools:build-conventions-plugin:1.0.0')
            }
        }
    }
    repositories {
        maven {
            url = uri('https://plugins.example.org/maven')
        }
    }
}
~~~

This is an **illustrative snippet** without a real artifact/repository, so it is not runnable as-is. **useModule** maps a plugin ID to the artifact implementing the plugin. For the public Spring Boot Plugin, `resolutionStrategy` is usually unnecessary; specifying the version in `pluginManagement.plugins` or root `apply false` suffices.

If internal plugins are built in a separate included build, Gradle also supports **pluginManagement.includeBuild('build-logic')**. Use it only when an actual `build-logic` project defines a plugin with a matching ID; `includeBuild` does not generate plugins or projects on its own.

## 11. Common Errors When Configuring pluginManagement and apply false

**Error 1 — pluginManagement is not the first block of settings.gradle.** Place `pluginManagement` at the top of the file, before `rootProject.name` and `include`; Gradle needs plugin resolution rules from the initialization phase.

**Error 2 — Omitting the version in a subproject without declaring a default version or root apply false.** Gradle will not know the version of the external plugin in the `plugins` DSL and may report **Plugin not found**. Supply the version centrally or put it directly in the module if it is a single-module project.

**Error 3 — Using both root apply false and a different version in app.** The plugin is already placed on the classpath by root, so requesting the plugin again with a version in a subproject can cause an **already on the classpath** error or version conflict. `app` should declare only the plugin ID.

**Error 4 — Thinking apply false automatically applies the plugin to every subproject.** `apply false` does not attach the Boot plugin to `app`/`core`. Modules needing the plugin must explicitly request it via their `plugins` block or a convention plugin.

**Error 5 — Unnecessarily applying the Boot plugin to root.** If root is just an aggregator, use `apply false` when declaring the plugin at root. Do not apply the plugin to root and manually disable `bootJar` afterward just to clean up side effects.

**Error 6 — Using apply false with the core java plugin.** The core **java** plugin is distributed with Gradle itself; it needs no separate version and does not need `apply false`. Simply apply **id 'java'** or **id 'java-library'** in the appropriate module.

**Error 7 — Confusing settings.plugins with pluginManagement.plugins.** A **plugins** block directly in `settings.gradle` is for Settings plugins; a **plugins** block inside `pluginManagement` declares default plugin versions. Do not treat them as equivalent.

**Error 8 — Only declaring pluginManagement.plugins and expecting bootJar.** Settings only provides default versions, not plugin application. Check whether `app/build.gradle` actually requests **org.springframework.boot** and the Java plugin.

**Error 9 — Missing plugin repositories or blocked plugin repo.** Add the right repository to **pluginManagement.repositories**; verify network, proxy, marker artifacts, and credentials for private repos. Project repositories serve a different purpose.

**Error 10 — Correct plugin version but incompatible Gradle/JDK.** Check **./gradlew --version** and the Java runtime executing Gradle, and read the Spring Boot Gradle Plugin release notes. `pluginManagement` does not upgrade the Gradle Wrapper or JDK automatically.

**Error 11 — Invalid syntax inside a project plugins block.** Do not put **plugins { ... }** arbitrarily inside `if`/loops or place script statements before it in the wrong position. Use version literals, aliases, or version policies in `pluginManagement`.

**Error 12 — Confusing the plugin version with the Spring Boot dependency BOM.** Having the Boot plugin in `app` does not mean every dependency is managed if the dependency-management plugin or a native BOM platform is missing. Scope the BOM to projects that actually need it.

**Error 13 — Thinking core must have bootJar.** `core` is a `java-library` and should produce a library JAR; `app` applies the Boot plugin to build an executable JAR. Use **:core:jar** and **:app:bootJar** instead of trying to run every task at root.

**Error 14 — Combining two conflicting version sources.** If you declare both `settings.pluginManagement` and root `apply false`, keep versions and goals consistent; avoid updating one place and forgetting the other.

**Error 15 — Fetching a plugin from a private repository that lacks markers.** The Plugins DSL normally resolves the plugin marker and then the implementation artifact. When a repository has the implementation without a marker, publish the marker properly or use `pluginManagement.resolutionStrategy` to map it explicitly.

## 12. When to Choose Which Strategy?

| Context | Usually sensible choice |
| --- | --- |
| A single Spring Boot application | Declare versions directly in `app/build.gradle` for simplicity. |
| Multi-project where apps share versions and root is not an app | Root **plugins ... apply false** or **settings.pluginManagement**. |
| Need custom plugin repositories, proxies, or resolution rules | **pluginManagement**. |
| Want to load versions from `gradle.properties` | **pluginManagement.plugins**. |
| Many repeated Java/test/quality rules | **Convention plugin** to encapsulate shared logic. |
| Library module not running Spring Boot | Just **java-library**, do not apply Boot plugin unless needed. |

Verification workflow after editing:

1. Ensure the Gradle Wrapper/JDK are compatible with the chosen Spring Boot plugin version.
2. Decide on one place to manage plugin versions, then remove duplicate versions from `app`/`core`.
3. Verify that plugin resolution repositories and dependency resolution repositories are configured properly.
4. Run **./gradlew projects** to confirm the multi-project setup.
5. Run **./gradlew :app:tasks --all** and **:core:tasks --all** to verify plugins are applied to the right modules.
6. Run **./gradlew :app:test :app:bootJar** to catch version/plugin resolution errors early.
7. Run **./gradlew :app:bootRun** to verify application behavior.
8. When upgrading plugins, check build/test results, the dependency graph, and compatibility requirements rather than only verifying that Gradle downloaded the plugin.

## 13. Official References

- Gradle — Working with Plugins: https://docs.gradle.org/current/userguide/plugins_intermediate.html
- Gradle — Build Lifecycle: https://docs.gradle.org/current/userguide/build_lifecycle.html
- Gradle — Best Practices for Structuring Builds: https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html
- Gradle — Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html
- Spring Boot 3.3 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.3/gradle-plugin/getting-started.html
- Spring Boot — Gradle Plugin Managing Dependencies: https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html

**Remember:** **pluginManagement** in settings defines where to find plugins and their default versions; **apply false** in root `build.gradle` resolves plugins for child modules to use without applying them to root. **Subprojects must still request a plugin to receive its tasks and features.** Separating these three responsibilities keeps multi-module Spring Boot builds consistent without attaching the Boot plugin to Java libraries.
# Configuring group, version, repositories, and dependencies in Gradle with Spring Boot

## 1. Four Configuration Groups That Determine What a Build Fetches and Produces

When starting a Spring Boot application with Gradle, developers routinely see lines like **group = 'com.example'**, **version = '1.0.0'**, **repositories { mavenCentral() }**, and **dependencies { implementation '...' }**. They are concise, yet each handles a different responsibility:

- **group**: identifies the organizational group of the **project/artifact** being built.
- **version**: specifies the version of the **project/artifact** being built.
- **repositories**: specifies **where Gradle looks for dependency artifacts** when resolving libraries.
- **dependencies**: declares **which modules, libraries, or other projects the project needs** and which classpath/usage scope they belong to.

With Spring Boot, there is another crucial piece: the **Spring Boot Gradle Plugin** provides capabilities to run and package the application; **BOM/dependency management** supplies the curated set of library versions managed by Spring Boot. Configuring the project's `group`/`version` **does not replace** choosing a Spring Boot plugin version or managing dependency versions.

Goal after this lesson: read and write these configurations in **build.gradle** (Groovy DSL) or **build.gradle.kts** (Kotlin DSL); understand the difference between project identity, library coordinates, and plugin repositories; choose appropriate dependency scopes; use the Spring Boot BOM properly; inspect the dependency graph; and run a real project.

## 2. Configuration Map of a Gradle Project

A basic Java/Spring Boot Gradle project has this structure:

~~~text
order-service/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/...
    │   └── resources/...
    └── test/
        └── java/...
~~~

**settings.gradle** determines the root project name, subprojects, and can centralize repository/plugin resolution configuration. **build.gradle** describes plugins, group/version, Java toolchain, repositories, dependencies, and project tasks. **gradlew / gradlew.bat** is the Gradle Wrapper, ensuring the project uses its chosen Gradle version instead of whatever happens to be installed on a machine.

If the project uses **Kotlin DSL**, the corresponding files are **settings.gradle.kts** and **build.gradle.kts**. Groovy/Kotlin syntax differs, while the concepts of group, version, repository, dependency configuration, and BOM are identical.

A short diagram of the data flow:

~~~text
settings.gradle : rootProject.name / included projects / repository policy
                        |
                        v
build.gradle : plugins + group + version + repositories + dependencies
                        |
                        v
Gradle resolves plugins and dependency metadata/artifacts
                        |
                        v
Java compile/test -> Spring Boot bootJar -> build/libs/<name>-<version>.jar
                        |
                        v
java -jar + runtime configuration -> application runs
~~~

Do not assume this entire flow happens merely from declaring `group` or `version`. Gradle must have the appropriate plugins, tasks, and dependencies; you must actually invoke tasks such as **build** or **bootJar** to create an artifact.

## 3. group: Identity of the Project, Not the Java Package

### 3.1. Declaring group

In **build.gradle** (Groovy DSL):

~~~groovy
group = 'com.example.training'
~~~

In **build.gradle.kts** (Kotlin DSL):

~~~kotlin
group = "com.example.training"
~~~

**group** is a property on the Gradle **Project**. When the project is published in Maven format, it normally becomes the **groupId** in the artifact coordinates. It helps distinguish modules with the same name belonging to different organizations.

For example, a project with:
- group = **com.example.training**
- name = **order-service**
- version = **1.0.0-SNAPSHOT**

Has Maven-style module coordinates:

~~~text
com.example.training:order-service:1.0.0-SNAPSHOT
          group       :    name     :     version
~~~

**group is not a mandatory Java package name.** The Java directory structure can be **com/example/orders/** with **package com.example.orders;**. For maintainability, teams often align the package name with `group`, but Gradle does not automatically alter package declarations, Spring component scanning, or source file locations based on `group`.

**group is not the Spring application name.** The runtime property **spring.application.name** is read separately by Spring Boot from **application.properties**, YAML, environment variables, or other configuration sources. Assigning `group` does not automatically change URLs, ports, or the service name in operational systems.

### 3.2. What If group Is Not Set?

Gradle can still build an internal Java project when `group` is unconfigured, but its publishing identity will be missing or take an unintended default. For projects whose artifacts will be stored or consumed as dependencies by other projects, choose a stable `group` aligned with your organization's namespace.

Choosing `group` is a publishing identity decision. Do not arbitrarily change `group` for an artifact that already has consumers; from Maven/Gradle dependency resolution's perspective, **com.example:a:1.0** and **com.other:a:1.0** are two distinct modules even if their code is identical.

## 4. version: Version of the Artifact Being Built

### 4.1. Declaring version

In **build.gradle**:

~~~groovy
version = '1.0.0-SNAPSHOT'
~~~

In **build.gradle.kts**:

~~~kotlin
version = "1.0.0-SNAPSHOT"
~~~

The **project.version** property is the release identifier of the project. When using the Spring Boot **bootJar** task, the default archive filename typically derives from **project.name** and **project.version**, such as **order-service-1.0.0-SNAPSHOT.jar** in **build/libs**. This name can be customized when configuring the archive task.

If `version` is omitted, Gradle defaults to **unspecified**; do not treat that as a stable release version. For services entering CI/release pipelines, establish a clear versioning policy.

### 4.2. Where Is project.name?

The project name is typically set in **settings.gradle**:

~~~groovy
rootProject.name = 'order-service'
~~~

Or **settings.gradle.kts**:

~~~kotlin
rootProject.name = "order-service"
~~~

The **group:name:version** triplet describes module identity in Maven-style coordinates. **name** here comes from the Gradle project name, not automatically from **spring.application.name**. Changing **rootProject.name** can alter default output names and project/task paths; changing **version** alters archive names and version metadata.

### 4.3. Project Version vs. Three Easily Confused Versions

| Configuration | Example | Whose version is being selected? |
| --- | --- | --- |
| **version = '1.0.0-SNAPSHOT'** | Project | Artifact of the application/module being built |
| **id 'org.springframework.boot' version '3.5.16'** | Plugin | Spring Boot **Gradle Plugin** and associated Boot line |
| **implementation 'com.example:some-lib:2.4.0'** | Dependency | External library **some-lib** |
| **java.toolchain.languageVersion = 17** | JDK | JDK used for toolchain-aware Java tasks |

Changing the project's **version = '2.0.0'** **does not upgrade Spring Boot from 3.5 to 4.0**, does not update Jackson, and does not change the JVM running the app. You must update the corresponding setting for each.

### 4.4. Should You Use SNAPSHOT?

The **-SNAPSHOT** suffix typically represents a development build that may change prior to a fixed release. For production artifacts, teams should follow a commit/tag-based versioning policy and store immutable outputs. Gradle does not automatically publish to Maven Central or a registry just because you set `version`; publishing requires separate plugins/tasks, target repositories, and write credentials.

If you want CI to supply the version, you can **replace** the static version line with configuration reading a Gradle property:

~~~groovy
version = providers.gradleProperty('releaseVersion')
        .orElse('1.0.0-SNAPSHOT')
        .get()
~~~

Then run, for example:

~~~bash
./gradlew -PreleaseVersion=1.1.0 bootJar
~~~

In this run, `project.version` is **1.1.0**. This is an **alternative** to the static version line in the demo—do not keep both version assignments at once and guess which one wins. Versioning must go hand in hand with release and testing policies to avoid mixing different artifacts under the same identifier.

## 5. repositories: Where Does Gradle Find Libraries?

### 5.1. Maven Central as a Common Source

In **build.gradle** (Groovy):

~~~groovy
repositories {
    mavenCentral()
}
~~~

In **build.gradle.kts** (Kotlin):

~~~kotlin
repositories {
    mavenCentral()
}
~~~

**mavenCentral()** declares a public Maven-compatible repository hosting many Java libraries. When a project declares a dependency, Gradle uses metadata, module coordinates, and the repository list to locate the artifact and its transitive dependencies.

**repositories is not where Gradle publishes project outputs by default.** The **repositories** block here is for **downloading/resolving**. Upload targets when applying **maven-publish** or another publishing mechanism are configured separately inside **publishing.repositories**.

### 5.2. Plugin Repositories Differ from Dependency Repositories

These are two separate resolution paths:

| What to find? | Usually configured where? | Example |
| --- | --- | --- |
| **Gradle plugins** such as **org.springframework.boot** | **pluginManagement.repositories** in settings, or default Gradle Plugin Portal | `gradlePluginPortal()` |
| **Libraries** such as `spring-boot-starter-web`, Jackson, JUnit | **repositories** in build script, or **dependencyResolutionManagement.repositories** in settings | `mavenCentral()` |
| **Artifacts to publish** | `publishing.repositories` or corresponding pipeline/registry | Maven repository receiving outputs |
| **JDK/toolchain distributions** | Dedicated toolchain provisioning mechanism | Not replaced by `mavenCentral()` by default |

If you get **Plugin [id: 'org.springframework.boot'] was not found**, adding **mavenCentral()** to the dependency `repositories` block may not fix it: the issue can lie in plugin repositories, plugin version, or network access. Conversely, if the plugin resolves but **org.springframework.boot:spring-boot-starter-web** cannot be resolved, inspect dependency repositories/BOM/network.

Normally, **plugins { ... }** can fetch plugins from the **Gradle Plugin Portal** by default without declaring `pluginManagement`. However, an enterprise using an internal mirror or proxy may need to configure plugin repositories in **settings.gradle(.kts)**.

### 5.3. Multi-Module Projects: Centralizing Declarations in Settings

When you want all modules to share an approved repository list, configure it in **settings.gradle** as an **alternative** to **repositories { mavenCentral() }** in each `build.gradle`:

~~~groovy
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

rootProject.name = 'order-service'
~~~

**FAIL_ON_PROJECT_REPOS** requires dependency repositories to be declared in settings and throws an error if any project/build script tries to add its own repository. When adopting this pattern, **remove the repositories block from build.gradle**; keeping both will cause the build to be rejected under the chosen policy.

Gradle also offers **PREFER_SETTINGS** and **PREFER_PROJECT** (default) to govern repository precedence between settings and projects. Choosing a mode is an organizational build policy; do not mix centralized and scattered configurations without understanding how Gradle picks sources.

Documentation: https://docs.gradle.org/current/userguide/centralizing_repositories.html

### 5.4. Private Repositories and Authentication

For internal libraries, an organization may use a private Maven-compatible repository:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.example.invalid/releases')
        credentials {
            username = providers.gradleProperty('repoUser')
                    .orElse(providers.environmentVariable('REPO_USER'))
                    .orNull
            password = providers.gradleProperty('repoPassword')
                    .orElse(providers.environmentVariable('REPO_PASSWORD'))
                    .orNull
        }
    }
    mavenCentral()
}
~~~

**This is only an illustrative snippet**: the hostname **example.invalid** is not a working repository. Use the real URL provided by your organization, pick an authentication mechanism supported by your infrastructure, and do not commit passwords or tokens into `build.gradle`/`gradle.properties` in the repository. Secrets can be supplied via environment variables, user-level Gradle properties, or CI secret stores.

Repository order and scope affect resolution. A library may exist in multiple places, leading to differing artifact sources; with internal repositories, consider **content filters/exclusive content** and verified mirrors to prevent artifacts from being fetched from unintended sources.

### 5.5. Sources to Avoid Using Indiscriminately

- **mavenLocal()**: may pull artifacts installed in an individual developer's local Maven repository that do not match CI; generally unsuitable as a default source for release builds.
- **flatDir / files('libs/x.jar')**: uses local JARs but lacks metadata for transitive dependencies and version constraints; harder to control/update than published modules.
- **jcenter()**: should not be used as a default repository for new Spring Boot projects; use Maven Central or repositories currently supported by your project/libraries.
- **Maven snapshot repositories**: add only when snapshot artifacts are genuinely needed; dynamic or snapshot dependencies can make build results change over time.

A reproducible build requires controlling **versions, repositories, caches, metadata, and dynamic dependency state**, not just writing `mavenCentral()`.

## 6. dependencies: Declaring What Goes onto Each Classpath

### 6.1. External Library Coordinates

In Gradle, an external dependency typically uses the form:

~~~text
group:name:version
~~~

Example:

~~~groovy
dependencies {
    implementation 'com.google.guava:guava:33.4.8-jre'
}
~~~

Explanation:
- **com.google.guava** is the group of the **Guava library**, not the group of the project being built.
- **guava** is the artifact/module name.
- **33.4.8-jre** is the requested version of the library.
- **implementation** is the dependency configuration for the project's main source.

Gradle also resolves **transitive dependencies** declared by that artifact, then applies version selection rules, constraints, and conflict resolution. Hence a single dependency line can bring in many JARs.

### 6.2. Dependency Configurations Express When a Library Is Needed

When a project applies the Java plugin, common configurations are:

| Configuration | Included in main compile? | Included in main runtime? | Purpose |
| --- | --- | --- | --- |
| **implementation** | Yes | Yes | Application libraries used in code and at runtime |
| **compileOnly** | Yes | No | Needed only for compiling, such as annotations or APIs provided by the environment |
| **runtimeOnly** | No | Yes | Drivers/providers needed only at runtime; e.g., a database driver when code uses JDBC abstractions |
| **annotationProcessor** | For annotation processing, not the regular business classpath | No | Compile-time processors, e.g., Lombok |
| **testImplementation** | For compiling tests, not added to main compile | For test runtime | JUnit, Spring Boot Test, test helpers |
| **testRuntimeOnly** | No (not for test compile) | For test runtime | Test engine/launcher or components needed only during test execution |

Extended example, **not a list to copy-paste wholesale into a simple application**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Only if actually writing an app accessing a database via JDBC:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    // Only if the project actually uses Lombok:
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    // Testing:
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

These versionless dependencies **assume the project has configured Spring Boot dependency management/BOM** for each necessary configuration. Without a version management mechanism, Gradle may report **Could not find ...** or fail to determine versions. Furthermore, blindly adding **spring-boot-starter-jdbc** to a demo with no datasource may cause Spring Boot to demand datasource configuration at startup; do not add dependencies just because you saw them in an example.

**api** is a configuration commonly seen with the **java-library** plugin to expose dependencies that appear in a library's public API. A Spring Boot application using the Java plugin normally uses **implementation**; do not invoke **api** unless the project applies a plugin that defines that configuration.

### 6.3. Do Not Confuse runtimeClasspath with runtimeOnly

**runtimeOnly** is where you **declare** dependencies needed only at runtime. **runtimeClasspath** is a resolvable configuration used to **resolve** the complete runtime classpath, combining dependencies from `implementation`, `runtimeOnly`, and applicable sources. Likewise, **compileClasspath** is the resolved result for compilation, not a scope name used for declaring libraries.

Spring Boot's **bootJar** task packages runtime dependencies based on the appropriate classpath defined by the plugin. Consequently, **compileOnly** normally does not enter the executable archive, whereas `implementation`/`runtimeOnly` normally do when needed. Still check custom plugins, exclusions, and actual packaging configuration.

## 7. Spring Boot Gradle Plugin and Dependency Version Management

### 7.1. The Boot Plugin Does Not Mean Every Starter Automatically Has a Version

In **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}
~~~

The Spring Boot plugin provides **bootRun**, **bootJar**, **bootWar**, and other integrations when combined with the appropriate Java/War plugin. However, per Spring Boot documentation, to omit versions on Boot-managed dependencies, a project needs **a dependency management approach**:

1. Apply the **io.spring.dependency-management** plugin; when paired with the Spring Boot plugin, the corresponding Spring Boot BOM is imported automatically.
2. Use **Gradle native BOM support** via **platform(...)** or **enforcedPlatform(...)**.

Writing only **implementation 'org.springframework.boot:spring-boot-starter-web'** in a project without a suitable BOM/management setup may fail to resolve a version. **The project's own group/version does not solve this either.**

### 7.2. Option A — Gradle Native platform (Used in the Complete Example Below)

In **dependencies**:

~~~groovy
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
~~~

**BOM_COORDINATES** comes from the Spring Boot Gradle Plugin and points to the exact **spring-boot-dependencies** matching the plugin version. **platform(...)** brings the BOM's version constraints into that configuration and appropriately inheriting configurations. Because scopes can differ, the example declares `platform` on both **implementation** and **testImplementation** to be explicit across main and test.

**platform** applies BOM-recommended versions as constraints; if stronger requirements/constraints exist in the dependency graph, the resolved version may differ from the BOM. **enforcedPlatform** imposes stricter forcing and can impact consumers when publishing a library; do not switch to `enforcedPlatform` casually to "fix" conflicts without analyzing the cause.

**Strength:** uses Gradle's native mechanism, often reducing overhead. **Point to remember:** do not use property overrides like **ext['slf4j.version']** from the Spring dependency-management plugin to change versions inside the BOM; use Gradle's dependency constraints/overrides properly and inspect the graph.

### 7.3. Option B — Spring Dependency Management Plugin

Another choice in Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

When the Spring Boot plugin and **io.spring.dependency-management** are applied together, Boot integrates to import the corresponding **spring-boot-dependencies** BOM; starters in the example do not need explicit versions. This mechanism allows overriding certain managed versions via BOM properties, such as **ext['slf4j.version']** for properties present in that Boot release line. Only override after verifying compatibility, because Spring Boot tests a curated set of dependency versions together.

This is an **alternative** to Option A. Do not apply both mechanisms to the same dependency set just to "be safe": the final resolution may be governed by multiple constraint/management systems that are hard to reason about. Pick one clear policy for the project, and remember **Gradle has no parent POM feature equivalent to Maven**.

### 7.4. A BOM Does Not Add Libraries Automatically

Whether using Option A or B, a BOM only manages **candidate versions**, not automatically adding every starter. If **spring-boot-starter-web** is not declared, the application will not automatically get Spring MVC controllers/server. If **spring-boot-starter-test** is not declared, the project will not automatically have the testing toolkit merely because a BOM was imported.

A BOM also does not manage every library on the Internet. For dependencies outside the managed set, choose explicit versions/constraints or a version catalog entry appropriately. Do not omit versions from every dependency expecting Gradle to fill them all in.

Spring Boot source: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html

## 8. Complete, Runnable Example: A Spring Boot Gradle Application

This technical example selects **Spring Boot 3.5.16**, **Java 17**, and **Gradle Wrapper 8.14**. This is an illustrative combination within the compatibility range published by Boot 3.5 documentation; real projects must check organization-supported versions and additional plugins. It uses **Gradle Groovy DSL** and **native BOM platform**, including only dependencies needed for the endpoint and test.

### 8.1. Creating the Project and Wrapper

Create a Java 17 Gradle project, for example via Spring Initializr, named **order-service**, then keep the generated Wrapper files and select Gradle 8.14 following the Wrapper update process documented by Gradle. The example below provides the configuration and Java source files; **./gradlew** commands assume the Wrapper already exists at the right version.

Exact structure:

~~~text
order-service/
├── settings.gradle
├── build.gradle
├── gradlew                 # Wrapper provided by project generator
├── gradlew.bat
├── gradle/wrapper/...      # distributionUrl and Wrapper JAR
└── src/
    ├── main/java/com/example/orders/
    │   ├── OrderServiceApplication.java
    │   └── PingController.java
    └── test/java/com/example/orders/
        └── PingControllerTests.java
~~~

### 8.2. settings.gradle

~~~groovy
rootProject.name = 'order-service'
~~~

This defines the Gradle project name. If the build script does not override the archive name, the Boot JAR uses **order-service** as its base name by default. It does not create the Java package **com.example.orders**; packages are declared in Java source files.

### 8.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example.training'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Why is this configuration sufficient?**

- **java** plugin creates Java source sets, classpaths, and tasks such as `compileJava`/`test`.
- **org.springframework.boot** plugin adds `bootJar`/`bootRun` for the application.
- **group + version + rootProject.name** defines the service's own artifact identity.
- **Java 17 toolchain** requests an appropriate JDK to compile/test; it does not automatically change the JVM running the Gradle daemon.
- **repositories { mavenCentral() }** enables fetching published libraries; the Boot plugin is resolved via separate plugin repositories.
- **platform(BOM_COORDINATES)** supplies managed version constraints matching the Boot plugin.
- **starter-web** brings web components needed for the controller; **starter-test** and the JUnit launcher support testing.
- **useJUnitPlatform()** tells the Gradle test task to run on JUnit Platform.

No explicit version is needed for the Boot starters here because the platform manages them. **./gradlew --version** should show the right Gradle/JVM running. Use JDK 17+ compatible with Spring Boot 3.5 and Gradle 8.14; for this guide, test on JDK 17 to match the target runtime.

### 8.4. Java Application Class

File **src/main/java/com/example/orders/OrderServiceApplication.java**:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~

### 8.5. Controller Returning a Fixed Response

File **src/main/java/com/example/orders/PingController.java**:

~~~java
package com.example.orders;

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

The main class is in package **com.example.orders**, so Spring Boot component scanning discovers the controller in the same package by default. The Java package does not depend on the Gradle project declaring `group` as **com.example.training**.

### 8.6. Testing the Endpoint with Spring Boot Test

File **src/test/java/com/example/orders/PingControllerTests.java**:

~~~java
package com.example.orders;

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
class PingControllerTests {

    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

**testImplementation** makes JUnit/Spring Boot Test and MockMvc available on the test classpath. Test libraries are not part of the application's HTTP runtime and normally do not enter the executable JAR. If you remove **starter-test**, main Java code can still compile, but test code will lack required libraries.

### 8.7. Building, Testing, and Running

On Linux/macOS, from the root directory:

~~~bash
./gradlew --version
./gradlew clean test bootJar
java -jar build/libs/order-service-1.0.0-SNAPSHOT.jar
~~~

On Windows, run **gradlew.bat** instead of **./gradlew**. **build/libs/order-service-1.0.0-SNAPSHOT.jar** is the expected name given the current name/version and default archive settings; check the real name if the project has custom archive settings.

After the application starts on default port 8080, in a second terminal:

~~~bash
curl http://localhost:8080/ping
~~~

Exact expected response body:

~~~text
pong
~~~

Build logs are not fixed across environments, Gradle caches, or plugin versions. Only the **/ping** endpoint produces output strictly determined by the source code. If the application sets a different **server.port**, adjust the URL accordingly.

The **bootJar** command packages an executable Spring Boot archive containing the app and its runtime dependencies. It does not publish to a Maven repository; `project.version` and `group` alone do not make a release appear outside the build machine.

## 9. Same Idea in Kotlin DSL

If a project uses **build.gradle.kts**, do not paste Groovy syntax verbatim. An equivalent Kotlin DSL configuration for the core settings (completely replacing the demo's `build.gradle`) is:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example.training"
version = "1.0.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )
    testImplementation(
        platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

In **settings.gradle.kts**:

~~~kotlin
rootProject.name = "order-service"
~~~

Visible differences: Kotlin uses function calls like **implementation("...")**, whereas Groovy typically uses **implementation '...'**. Similarly, Groovy uses **group = '...'** and Kotlin uses **group = "..."**; do not mix Gradle task syntax or quoting from the two DSLs when copying configurations.

The Java files from section 8 work with both DSLs because how the build is declared does not change Java source contents.

## 10. Project Dependencies and Multi-Project Builds

Not every dependency is downloaded from Maven Central. If a Gradle build has **api** and **common** subprojects, you can declare a dependency edge using **project(...)**.

Example **settings.gradle** of a multi-module project:

~~~groovy
rootProject.name = 'business-system'
include 'api', 'common'
~~~

In **api/build.gradle**, once the Java plugin and necessary configurations are applied:

~~~groovy
dependencies {
    implementation project(':common')
}
~~~

Gradle consumes outputs/variants of **:common** through build relationships rather than looking up **:common** as an external artifact on Maven Central. This sets up the proper build order, classpath, and transitive project dependencies.

Each subproject has its own **name** (usually from **settings.gradle**), and can have its own **group/version** if it needs to be published. Do not assume **root's group/version** are automatically set on every child project under all policies; define them in each module or your organization's convention plugin when needed.

For Java library modules, generally apply **java-library** and use **api** for dependencies truly exposed in public types; Boot application services mostly use **implementation**. In multi-project builds, applying the Boot plugin to every module when only the `app` module needs `bootJar` creates awkward packaging/lifecycle behavior, so choose plugins according to each module's role.

## 11. Seeing Which Dependencies Gradle Actually Resolves

A declared dependency is an **input request**; the final version may not match what the author initially expects because Gradle has transitive dependencies, constraints, platforms, and conflict resolution.

### 11.1. Listing Configurations and Resolved Dependencies

At the root of the single-module demo project:

~~~bash
./gradlew dependencies
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Read each tree by its purpose:

- **compileClasspath**: libraries the compiler sees when compiling main code.
- **runtimeClasspath**: libraries available to the application at runtime and typically packaged into the executable Boot JAR.
- **testRuntimeClasspath**: classpath for running tests; usually broader because it includes test tools.
- **implementation**, if inspected directly, normally describes **declarations**, not always a fully resolvable configuration. When checking final versions, prefer resolvable configurations like `runtimeClasspath`.

Dependency branches may carry markers indicating a selected version differs from the requested one, constraints, or duplicate dependencies. Formatting and details vary by Gradle version, so do not copy a fixed tree output as proof for another project.

### 11.2. Why Is a Library's Version Different from Expected?

Use:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

**dependencyInsight** focuses on a single dependency and the reason for its selected version and dependency path within a configuration. If a project does not use a given module, the query may find nothing; that does not prove the repository is broken.

For multi-project builds, include the project path, e.g., **./gradlew :api:dependencyInsight --dependency spring-core --configuration runtimeClasspath** when the **:api** module has that configuration.

### 11.3. Inspecting Actual group/version/name

~~~bash
./gradlew properties
./gradlew --version
./gradlew tasks --all
~~~

Look for **group**, **name**, and **version** in `properties`. **--version** reports the running Gradle/JVM; it does not print the service's `project.version`. **tasks --all** helps verify whether **bootJar**, **test**, **dependencies**, or tasks from other plugins exist.

Do not confuse **group/version shown in project properties** with **group/version of libraries in the dependency graph**. Those two property levels are completely distinct.

## 12. Changing Dependency Versions Properly

### 12.1. Dependencies with Explicit Versions

For a module outside the BOM-managed set, you can declare a fixed version:

~~~groovy
dependencies {
    implementation 'com.google.guava:guava:33.4.8-jre'
}
~~~

Fixed versions make requests easier to trace than dynamic versions like **1.+**, **latest.release**, or uncontrolled snapshots. Still, a requested version may not be the final resolved version if the graph has other constraints/selection rules; confirm with **dependencyInsight**.

### 12.2. Libraries Managed by the Spring Boot BOM

For starters or libraries covered by the BOM, prefer letting the BOM manage versions unless there is a clear reason to override. Spring Boot tests a compatible set of libraries per release; manually bumping a core library can break a related API even if **bootJar** still builds successfully.

If an override is needed:
1. Identify the library and its current version with **dependencyInsight**.
2. Check **Spring Boot Dependency Versions** for your exact release.
3. Choose the target version and check compatibility notes.
4. Apply the version/constraint according to the chosen BOM mechanism (native platform or dependency-management plugin).
5. Re-run compilation, unit/integration tests, and test the real artifact/runtime.

**Native BOM** does not use Maven BOM property-override syntax like a Maven parent. **Spring dependency-management plugin** may support property overrides per its documentation. Do not mix both mechanisms arbitrarily.

### 12.3. Version Catalogs Help Centralize, Not Replace BOMs

Multi-module projects can store aliases in **gradle/libs.versions.toml**. Example version catalog file:

~~~toml
[versions]
guava = "33.4.8-jre"

[libraries]
guava = { module = "com.google.guava:guava", version.ref = "guava" }
~~~

When the version catalog is picked up by Gradle at the default location, in Groovy DSL:

~~~groovy
dependencies {
    implementation libs.guava
}
~~~

This is convenient when multiple modules need the same external library. **A version catalog only centralizes declarations/aliases; it does not add repositories and does not replace Gradle BOM conflict resolution**. For dependencies already managed by the Boot BOM, you generally do not need to hardcode versions into the catalog unless your organization intentionally manages them differently.

## 13. Reproducibility and Safety of Dependency Resolution

A stable build requires more than `group`/`version` and a `mavenCentral()` line:

- **Pin the Gradle Wrapper** in VCS so laptops and CI use the same Gradle distribution; manage the Java toolchain/JDK separately.
- **Pin the Spring Boot plugin version** and verify the Boot line is compatible with the selected Gradle/Java versions.
- **Prefer fixed/verified BOM versions**; avoid uncontrolled dynamic versions or snapshots in release builds.
- **Verify repository sources**. Do not randomly add unverified repositories, since the same coordinates could be served from different sources.
- **Keep secrets out of the repository**; use env vars, Gradle user-home, or CI secret management to authenticate against private repositories.
- **Inspect the actual graph** with `dependencies` and `dependencyInsight`; track CVEs/updates via your organization's security process.
- **Consider dependency locking and dependency verification** when strict reproducibility/checksum checking is needed. Lock files, verification metadata, and repository policies should be managed and reviewed like source code.
- **Do not equate build success with deployment success**: JVM, datasource configuration, networking, secrets, and readiness still belong to the runtime environment.

Documentation:
- https://docs.gradle.org/current/userguide/dependency_locking.html
- https://docs.gradle.org/current/userguide/dependency_verification.html

### Do Not Try to Fix Every Error with --refresh-dependencies

**./gradlew --refresh-dependencies** tells Gradle to recheck/redownload metadata/artifacts according to cache rules. It is useful when suspecting a stale cache, but it cannot fix wrong coordinates, a missing BOM, a blocked repository, missing credentials, or a nonexistent version. Read the resolution error first and verify source/version.

## 14. Common Errors and How to Handle Them

| Symptom | Issue to consider | How to verify |
| --- | --- | --- |
| **Plugin [id: 'org.springframework.boot'] was not found** | Missing plugin repository, wrong plugin version, or network/proxy | `settings.pluginManagement.repositories`, Plugin Portal, version, and connectivity |
| **Could not find org.springframework.boot:spring-boot-starter-web** | Repository or BOM/version management misconfigured | `repositories` / `dependencyResolutionManagement` and BOM |
| Gradle reports **Could not find :...:.** or no version | Dependency lacks a version and is unmanaged | `platform`/BOM, dependency-management plugin, or explicit version |
| Tests pass but **java -jar** throws missing class | Library placed in **testImplementation** or **compileOnly** instead of runtime/implementation | `runtimeClasspath`, `dependencyInsight`, `bootJar` contents |
| **Cannot resolve external dependency ... because no repositories are defined** | No library download source declared | `repositories { mavenCentral() }` or settings `dependencyResolutionManagement` |
| **Build was configured to prefer settings repositories over project repositories** | Centralized repository policy conflicts with project repos | `repositoriesMode` and where repos are declared |
| **401/403** on a private Maven repository | Missing/wrong credentials, permissions, or expired token | CI secrets, repo URL, credentials, proxy |
| **404** resolving a library | Wrong `group:name:version` or source lacks artifact | Coordinates from publisher, right URL, and repository support |
| Output JAR has an unexpected name | Different `project.name`/`version` or custom archive settings | `settings.gradle`, Gradle properties, `bootJar` archive settings |
| Changed **version** but Spring Boot stayed on the old version | Changed `project.version` instead of Boot plugin/BOM version | `plugins` block, dependency graph |
| **No signature of method: api()** | Used **api** in a project without `java-library` plugin/configuration | `plugins` block, dependency configurations |
| **No matching toolchains found** | Missing required JDK and no provisioning configured | `java.toolchain`, installed JDKs, toolchain repositories |
| Compilation passes but tests lack JUnit | Insufficient test dependency scope or JUnit Platform task config | `testRuntimeClasspath`, `starter-test`, `useJUnitPlatform` |
| Internal module fails to resolve via **project(':x')** | Subproject name/path does not exist or is not included | `settings.gradle`, `./gradlew projects` |
| Build only passes on laptops with **mavenLocal()** | Relied on an artifact existing only on a local machine | Repository policy, remove local source or publish properly |

When encountering an error, identify whether **plugin resolution**, **dependency resolution**, **compile**, **test**, **packaging**, or **runtime** failed. Analyzing at the right layer prevents changing unrelated things.

## 15. Worked Practice Exercises

### Exercise 1: Changing the Application's Own Version

You have:

~~~groovy
group = 'com.example.training'
version = '1.0.0-SNAPSHOT'
~~~

Requirement: build the application with the same source as **1.1.0-SNAPSHOT**. Change the **version** line to **1.1.0-SNAPSHOT** and run **./gradlew bootJar**. Keeping archive defaults, the corresponding JAR name changes from **order-service-1.0.0-SNAPSHOT.jar** to **order-service-1.1.0-SNAPSHOT.jar**.

**There is no need to change** the Spring Boot plugin version just to change the application's own identifier. If you change `project.name` in settings, the new archive base name will change accordingly.

### Exercise 2: Adding a Test-Only Library

Add a test library managed by the project/BOM to **testImplementation**, then run:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Observe: the test-only library normally appears in **testRuntimeClasspath** but not in main **runtimeClasspath** unless another main dependency also pulls it in. Therefore, test libraries are normally excluded from the Boot JAR.

### Exercise 3: Which Repository Affects starter-web?

If a project resolves the Spring Boot plugin yet reports failing to download **starter-web**, inspect **dependency repositories**, network permissions, and BOM/version management. Adding a plugin repo to **pluginManagement.repositories** does not automatically supply a download source for `starter-web`. Two separate repository chains serve two different artifact types.

### Exercise 4: Reading Why a Version Was Selected

Run:

~~~bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Find which dependency path pulls the module onto the classpath and which constraint/version determines the version actually used. Then cross-check with the imported Spring Boot BOM; when multiple versions are requested, analyze the conflict before forcing a version.

### Exercise 5: Spotting Errors in a Configuration Snippet

Broken snippet:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

group = 'com.example'
version = '2.0.0'

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**At least two things are missing**: a dependency repository (e.g., **mavenCentral()** if settings does not already provide one), and a BOM/dependency management mechanism so the starter can omit its version. Defining the project's **group/version** cannot replace these two items.

One solution using native BOM:

~~~groovy
repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

In a real project, if dependency repositories are centralized in settings with **FAIL_ON_PROJECT_REPOS**, **do not** add the `repositories` block in `build.gradle`; only add the appropriate BOM/dependencies section.

## 16. Pre-Finalize Configuration Checklist

- [ ] **settings.gradle** sets the right **rootProject.name** and included subprojects if any.
- [ ] **group** and **version** represent the artifact's own identity; distinct from Java package names, Spring app names, and plugin versions.
- [ ] **plugins** applies Java and Spring Boot Gradle Plugin versions compatible with the project's Gradle/JDK.
- [ ] **repositories** declared at project or settings level per policy; plugin repos and dependency repos configured separately.
- [ ] **dependencies** use the right configurations: `implementation`, `runtimeOnly`, `compileOnly`, `annotationProcessor`, `testImplementation`, `testRuntimeOnly`.
- [ ] Use **native platform BOM** or **io.spring.dependency-management**, avoiding versionless dependencies without a BOM.
- [ ] Analyze final versions with **dependencies/dependencyInsight**; evaluate any overrides of Spring Boot managed versions.
- [ ] Commit the Wrapper; verify actual build/test, **bootJar**, and **java -jar**.
- [ ] Do not commit repository credentials; avoid uncontrolled dynamic versions/repositories.
- [ ] In multi-module builds, choose proper project dependencies and apply the Boot plugin according to module role.

**Remember:** **group/version** answers "what identity does this project's artifact carry"; **repositories** answers "from which sources can Gradle fetch libraries"; **dependencies** answers "which libraries are needed and on which classpath"; and **Spring Boot plugin + BOM** determines how to build the application and the matching Spring Boot library version set. Understanding these boundaries lets you read configurations quickly, fix resolution errors in the right place, and produce stable artifacts.

## Official References

- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
- Spring Boot 3.5 — Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Spring Boot 3.5 — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html
- Gradle — Declaring Dependencies: https://docs.gradle.org/current/userguide/declaring_dependencies_basics.html
- Gradle — Dependency Configurations: https://docs.gradle.org/current/userguide/dependency_configurations.html
- Gradle — Declaring Repositories: https://docs.gradle.org/current/userguide/declaring_repositories.html
- Gradle — Centralizing Repository Declarations: https://docs.gradle.org/current/userguide/centralizing_repositories.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Gradle — Dependency Locking: https://docs.gradle.org/current/userguide/dependency_locking.html
- Gradle — Dependency Verification: https://docs.gradle.org/current/userguide/dependency_verification.html
- Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
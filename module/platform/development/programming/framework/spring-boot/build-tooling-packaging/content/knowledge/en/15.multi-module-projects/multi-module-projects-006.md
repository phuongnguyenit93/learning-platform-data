# Distributing Shared Configuration via Maven Parent POM or Gradle Convention Plugins

## 1. Learning Objectives and the Multi-Module Problem

In a Spring Boot repository with multiple modules, copying Java, compiler, Surefire/JUnit, dependency version, build plugin, publishing, and quality-gate configurations into every module causes **configuration drift**: module A uses Java 17 while module B silently changes its compiler version; a library module gets packaged as an executable Boot JAR; a new service misses its test engine or BOM. A better practice is to **define build policy in one place and apply it intentionally to each group of modules**.

The two tools solve this problem via different mechanisms:

- **Maven:** uses a **parent POM** to *inherit configuration* and can combine an **aggregator POM** to *build multiple modules in one reactor*.
- **Gradle:** uses **convention plugins** (often *precompiled script plugins* in `build-logic`) to *encapsulate and reuse configuration*; each subproject **explicitly opts into plugins**.

After this lesson, you will be able to:

1. Distinguish Maven `<parent>` from `<modules>`, and Gradle `include(...)` from `includeBuild(...)`.
2. Use Maven `<properties>`, `<dependencyManagement>`, and `<pluginManagement>` to share configuration without pulling in every dependency or running every plugin automatically.
3. Create a **Maven multi-module Spring Boot project** consisting of `shared` (library JAR) and `service` (Boot executable JAR) from complete POMs.
4. Create an equivalent **Gradle multi-project build**, organizing build logic using an *included build* and convention plugins.
5. Distinguish **library modules** from **application modules** so you never accidentally run `spring-boot:repackage` or `bootJar` on a library.
6. Understand how the Spring Boot BOM, Gradle platforms, and version catalogs relate to — yet **are not synonymous with** — a Maven parent or Gradle convention plugin.
7. Inspect effective configuration, applied tasks/plugins, and the dependency graph via CLI; troubleshoot multi-module configuration errors.
8. Decide when to place policies in a root, an intermediate parent, or a specialized convention plugin, with a safe CI change workflow.

**Example scope:** Java 17+, Maven 3.9+ or Gradle 8.14.x, Spring Boot `3.5.16`. These are defined illustrative baselines, **not a requirement that every project use these exact versions**. For Spring Boot 3.5, official documentation supports Maven 3.6.3+ and Gradle 7.x/8.x lines meeting minimum requirements. When upgrading Gradle/Boot, consult the official compatibility docs for **that exact release** rather than inferring from version numbers alone.

## 2. Concept Map: Shared Policy Differs from Inter-Module Dependencies

A repository having:

~~~text
repository
├── shared     # Java library: Greeter class
└── service    # Spring Boot app: depends on shared
~~~

has at least **two independent relationships**:

1. **Build configuration relationship:** `shared` and `service` share Java release, encoding, and plugin/test conventions.
2. **Source/runtime dependency relationship:** `service` calls `Greeter` from `shared`.

In Maven, relationship (1) is typically expressed via `<parent>`; relationship (2) via `<dependency>com.example:shared:...`. In Gradle, relationship (1) uses `plugins { id("company.java-conventions") }`; relationship (2) uses `implementation(project(":shared"))`.

Do not confuse them:

- "Modules share the same parent" does **not** mean modules automatically see each other's classes.
- "Modules share the same convention plugin" does **not** automatically create a Java dependency between them.
- "Modules are listed in reactor/settings" does **not** mean the application project will automatically include bytecode from every other module.
- "A dependency version is managed" does **not** mean that dependency is declared on the classpath.

## 3. Maven: Parent POM and Aggregator POM Are Not the Same Concept

### 3.1. Maven Inheritance: A Child Has Only One Direct Parent

A Maven module has only **one direct `<parent>`**:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Maven inherits allowed elements from the parent, which can include `groupId`, `version`, `properties`, `dependencyManagement`, `pluginManagement`, certain plugin executions, repositories, and various build settings.

You cannot write two `<parent>` elements to inherit both `company-parent` and `spring-boot-starter-parent`. If an organization already has its own parent, you typically **keep that parent and import the Spring Boot BOM** under `dependencyManagement`, then manage the Spring Boot Maven Plugin explicitly.

### 3.2. Maven Aggregation: Root Knows Which Modules Are Built

A POM with `pom` packaging can declare:

~~~xml
<packaging>pom</packaging>

<modules>
    <module>shared</module>
    <module>service</module>
</modules>
~~~

`<modules>` tells the Maven reactor which projects participate when running Maven at the root. **Aggregation does not replace inheritance**: a module can belong to the reactor while having a different parent. Conversely, a child can inherit a repository parent without being listed in that parent's `<modules>`.

| Maven Concept | Where Declared? | Purpose |
| --- | --- | --- |
| Parent inheritance | Child `<parent>` | Inherit shared configuration |
| Aggregation | Root `<modules>` | Build multiple Maven projects in the same reactor |
| Inter-module dependency | Child `<dependencies>` | Consume code/libraries from another module |
| Dependency management | Parent/child `<dependencyManagement>` | Manage versions/scopes when dependencies are used |
| Plugin management | Parent/child `<build><pluginManagement>` | Manage plugin versions/configuration; does not trigger goals automatically |
| Actual plugin execution | `<build><plugins>` and lifecycle bindings | Activate appropriate build plugins/goals |

A root POM **can simultaneously** be both parent and aggregator as in section 5, yet those are **two distinct roles**. In a large monorepo, an organization might publish a separate versioned corporate parent to a Maven repository while the root aggregator solely coordinates modules.

### 3.3. dependencyManagement vs dependencies

Example in a parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.5.16</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The `spring-boot-dependencies` BOM manages many compatible versions. Yet `<dependencyManagement>` **does not automatically add `spring-boot-starter` to `shared` and `service`**. The application module must declare the starter it actually needs.

If the parent puts a starter inside **`<dependencies>`**, that dependency can be **inherited by every child**, including libraries that do not use Spring Boot. Therefore, manage versions in `dependencyManagement` and keep actually needed libraries in each module's POM. This avoids bloating compile/runtime classpaths.

### 3.4. pluginManagement vs plugins

In a parent:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <version>3.5.16</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

This snippet **manages the version**, yet **does not automatically make both `shared` and `service` run `repackage`**. `service` must declare the Spring Boot Maven Plugin inside `<build><plugins>` and bind the `repackage` goal if the corporate parent does not already supply an execution.

Conversely, putting `spring-boot-maven-plugin` with an execution directly inside **`<build><plugins>` of the parent** lets children inherit that execution and forces an inappropriate goal onto library `shared`. Thus in a shared parent, **prefer `pluginManagement`**; each module type activates plugins when needed.

The Maven lifecycle still invokes plugin goals bound by default to its packaging (such as compiler/surefire for `jar`), picking up managed versions/config where present. The rule that "`pluginManagement` runs nothing" means **it does not trigger executions not already invoked by the lifecycle or a plugin declaration**.

## 4. Gradle: Convention Plugins as the Unit of Policy Sharing

### 4.1. Projects Do Not Automatically Inherit the Root Script Like a Maven Parent

In a Gradle multi-project build:

~~~kotlin
// settings.gradle.kts
rootProject.name = "company-gradle-sample"
include("shared", "service")
~~~

`include(...)` creates Gradle subprojects. These modules **do not have an XML `<parent>` model like Maven**. Gradle has a project hierarchy and a root build, yet Java toolchain, test, compiler, and plugin configurations must be applied via appropriate scripts/plugins.

The older pattern was putting `subprojects { ... }` blocks in root; that encourages cross-project configuration coupling and impedes configuration cache/isolated projects. **Convention plugins** allow selective sharing: libraries apply the Java convention; executable apps apply Java + Spring Boot conventions.

### 4.2. Precompiled Script Plugin

A file:

~~~text
build-logic/src/main/kotlin/company.java-conventions.gradle.kts
~~~

is compiled by the Gradle Kotlin DSL plugin into a **plugin with ID `company.java-conventions`** (unless another package is declared). Modules consume it via:

~~~kotlin
plugins {
    id("company.java-conventions")
}
~~~

**Key difference from a Maven parent:** any module that does **not** apply this plugin does **not** automatically inherit policies from it. A convention plugin can apply core/community plugins, create tasks, set toolchain defaults, configure test tasks, and declare required dependencies.

### 4.3. `buildSrc` vs `build-logic` Included Build

| Way to Share Gradle Logic | Characteristics | When to Use |
| --- | --- | --- |
| Copy-paste into each build script | Simple at first, quickly suffers drift | Very small projects |
| Root `allprojects/subprojects` block | Cross-cuts all modules, high coupling | Legacy builds; avoid extending if possible |
| `buildSrc` | Automatically compiled by Gradle and added to buildscript classpath | Small prototypes before introducing an included build |
| Included build `build-logic` | Dedicated build for convention plugins, registered via `includeBuild` | Large multi-projects, clear structure, scoped change impact |
| Published binary plugins | Versioned plugin in an internal Maven/Plugin Portal repo | Sharing policies across multiple repositories/teams |

Gradle recommends an **included build** for complex build logic. If writing a settings plugin, including it in `pluginManagement` follows specific early-lifecycle rules; the hands-on section builds **project convention plugins** only, not settings plugins.

### 4.4. `include` vs `includeBuild`

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "company-gradle-sample"
include("shared", "service")
~~~

- `include("shared", "service")`: creates **subprojects of the main multi-project build** to hold source/module code.
- `includeBuild("build-logic")`: attaches an **independent Gradle build** as a source of plugins/build logic. `build-logic` does not become a runtime dependency module `:build-logic` of the app.
- `pluginManagement.includeBuild(...)`: allows Gradle to resolve plugin IDs directly inside `plugins { }`, even for unpublished plugins. Block order and placement must follow the Gradle Settings DSL.

An included build has its **own** `settings.gradle.kts` and `build.gradle.kts`. Dependencies/repositories of `build-logic` are not automatically shared with `service`'s runtime classpath.

## 5. Complete Maven Example: Parent POM + Library + Spring Boot Service

### 5.1. Directory Tree

The example uses a **Maven reactor** at the root, with two modules having a real dependency between them:

~~~text
company-maven-sample/
├── pom.xml                              # Parent + aggregator
├── shared/
│   ├── pom.xml
│   └── src/main/java/com/example/shared/
│       └── Greeter.java
└── service/
    ├── pom.xml
    ├── src/main/java/com/example/service/
    │   └── ServiceApplication.java
    └── src/test/java/com/example/service/
        └── ServiceApplicationTests.java
~~~

The example uses the **core Spring Boot starter** without a web server or database, so checking stdout does not depend on port 8080. The exact same Java sources here are reused in the equivalent Gradle project in section 7.

### 5.2. Root `pom.xml` — Shared Configuration

Create `company-maven-sample/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>shared</module>
        <module>service</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>3.5.16</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.5</version>
                </plugin>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <version>${spring-boot.version}</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

**Maven property `${spring-boot.version}`** is interpolated from `<properties>`. Only the BOM and Boot Maven Plugin versions are centralized into one property; other Maven plugins carry explicit versions per policy.

At the root, note:

- `<packaging>pom</packaging>` lets the root act as both parent and module aggregator.
- `<modules>` specifies a list order, yet the **Maven reactor also inspects dependencies to compute build order**. `service` depends on `shared`, so Maven builds `shared` before `service` when needed.
- `<dependencyManagement>` imports the Spring Boot BOM without making both modules depend on all Spring libraries.
- `<pluginManagement>` aligns compiler, Surefire, and Boot Maven Plugin versions, yet Boot `repackage` is **not automatically activated** on the library.
- `maven.compiler.release=17` applies to the compiler plugin invoked by the lifecycle in Java modules.
- Do not put `<dependencies><dependency>spring-boot-starter...</dependency>` in the parent, because the `shared` library does not need the Spring Boot runtime.

### 5.3. `shared/pom.xml` — Library JAR

Create `company-maven-sample/shared/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shared</artifactId>
    <packaging>jar</packaging>
</project>
~~~

This module inherits `groupId`, `version`, encoding, Java release, and plugin management. It does **not** declare any Spring Boot starter or the Boot Maven Plugin. The output is typically a thin/library JAR such as `shared/target/shared-1.0.0-SNAPSHOT.jar`.

### 5.4. `shared/Greeter.java` — Plain Java

Create `shared/src/main/java/com/example/shared/Greeter.java`:

~~~java
package com.example.shared;

public final class Greeter {

    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

`Greeter` is a valid public Java 17 class requiring no Spring annotations. This file compiles standalone with the JDK:

~~~bash
javac -d /tmp/greeter-classes \
  shared/src/main/java/com/example/shared/Greeter.java
~~~

The example command is for Linux/macOS, assuming a JDK and write permission to `/tmp/greeter-classes`. It produces no stdout on success. In multi-module projects, **prefer Maven/Gradle builds**, because the build tool manages classpaths, compiler flags, and final packaging.

### 5.5. `service/pom.xml` — Spring Boot Application

Create `company-maven-sample/service/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>company-parent</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>service</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>shared</artifactId>
            <version>${project.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <executions>
                    <execution>
                        <goals>
                            <goal>repackage</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Notes:

1. `shared` is a **versioned dependency** (`${project.version}`) of `service`, not "same parent so they see each other automatically".
2. Both Spring Boot starters **omit versions** because the BOM is already imported into dependency management by the parent.
3. The Boot Maven Plugin **omits its version in the child** because the parent manages it in `pluginManagement`.
4. `repackage` is declared **only in `service`**; `shared` is not turned into an executable Boot JAR.
5. When not inheriting `spring-boot-starter-parent`, do not assume the `repackage` execution exists automatically. Bind it explicitly as shown above.

### 5.6. `ServiceApplication.java` — Consuming the Library Bean

Create `service/src/main/java/com/example/service/ServiceApplication.java`:

~~~java
package com.example.service;

import com.example.shared.Greeter;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceApplication.class, args);
    }

    @Bean
    Greeter greeter() {
        return new Greeter();
    }

    @Bean
    ApplicationRunner printGreeting(Greeter greeter) {
        return args -> System.out.println(greeter.greet("team"));
    }
}
~~~

This is a complete Java file in a project that already has Spring Boot and the `shared` module on the classpath. `Greeter` belongs to package `com.example.shared`, different from the Spring Boot app's package, so the example **registers it via an explicit `@Bean`** instead of relying on component scanning to discover plain Java classes.

The **line printed by the application** after the Spring context initializes is:

~~~text
Hello, team!
~~~

Spring Boot may print additional startup logs, so this line is the `ApplicationRunner` output rather than the entire immutable stdout.

### 5.7. `ServiceApplicationTests.java` — Testing the Spring Context

Create `service/src/test/java/com/example/service/ServiceApplicationTests.java`:

~~~java
package com.example.service;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ServiceApplicationTests {

    @Test
    void contextLoads() {
        // Test passes when Spring ApplicationContext initializes successfully.
    }
}
~~~

Surefire gets its version from the parent, and JUnit Jupiter/Boot testing dependencies come from `spring-boot-starter-test`. `@SpringBootTest` verifies context configuration, though this test is not an integration test for every endpoint or external service. Because the sample app has no Web starter, no HTTP server starts and no port is needed.

### 5.8. Build and Run the Maven Reactor

At `company-maven-sample/`, where the root POM lives:

~~~bash
java -version
mvn -version
mvn clean verify
java -jar service/target/service-1.0.0-SNAPSHOT.jar
~~~

If the project includes a properly generated Maven Wrapper, use `./mvnw` on Linux/macOS or `.\mvnw.cmd` on Windows PowerShell. **A hand-written example tree does not include a Wrapper by default**, so `mvn` works when Maven is installed.

Single-module command that builds reactor dependencies automatically:

~~~bash
mvn -pl service -am clean package
~~~

- `-pl service` selects only the `service` module in the reactor.
- `-am` (also make) lets Maven also build the reactor projects `service` needs, specifically `shared`.
- If you enter the `service` directory and run `mvn package` before `shared` has been built/installed into the local repository, Maven may **fail to resolve dependency `com.example:shared`**. That is a reactor-scope/dependency-resolution error, not a Spring Boot bug.

**Final artifacts:** `shared` builds a thin JAR. `service` builds a Boot executable JAR via `repackage`, where `shared-1.0.0-SNAPSHOT.jar` typically sits under `BOOT-INF/lib/`. When executing `java -jar`, the Boot Loader reads nested dependencies and the Spring app prints `Hello, team!`.

## 6. Verifying Maven Inherited the Right Configuration

### 6.1. Effective POM

Inspect `service` specifically:

~~~bash
mvn -pl service help:effective-pom
~~~

In the output, look for:

- `parent = com.example:company-parent:1.0.0-SNAPSHOT`.
- `maven.compiler.release=17` or equivalent effective compiler configuration.
- `spring-boot-dependencies` contributing managed dependencies.
- `maven-compiler-plugin` and `maven-surefire-plugin` receiving exact versions from parent management.
- `spring-boot-maven-plugin` having a version and `repackage` execution in `service`.

`help:effective-pom` does not prove the runtime artifact runs, yet it reveals the merged configuration after inheritance and profiles. Read `shared`'s effective POM as well to confirm **no** Boot `repackage` execution applies to the library module.

### 6.2. Dependency Tree and Reactor Order

~~~bash
mvn -pl service dependency:tree
mvn -pl service dependency:tree -Dincludes=com.example:shared
mvn -pl service -am package
~~~

`dependency:tree` shows which version of `shared` module `service` actually depends on. The reactor must build `shared` before packaging `service` given the dependency in the sample POM.

Do not assume `<modules>` order is the sole build order; Maven evaluates **actual dependency relationships**, so even if `service` appears before `shared` in the list while depending on `shared`, Maven still sorts them properly.

### 6.3. Distinguishing Thin Library from Boot Executable JAR

~~~bash
jar tf shared/target/shared-1.0.0-SNAPSHOT.jar
jar tf service/target/service-1.0.0-SNAPSHOT.jar
~~~

In the thin library JAR, look for `com/example/shared/Greeter.class` at the root package path. In the Boot executable JAR, look for:

~~~text
BOOT-INF/classes/com/example/service/ServiceApplication.class
BOOT-INF/lib/shared-1.0.0-SNAPSHOT.jar
org/springframework/boot/loader/launch/JarLauncher.class
~~~

Other versioned filenames depend on the actual build. **If `shared` contains `BOOT-INF/classes` and the Boot Loader**, you may have accidentally bound `repackage` in the parent or library module, which is usually wrong when `service`'s Java compiler needs to consume it as an ordinary library.

## 7. Complete Gradle Example: `build-logic` + Two Convention Plugins

This example uses **Gradle Kotlin DSL** and the Spring Boot Gradle Plugin. Unlike Maven, modules do not inherit a parent POM. Shared configuration is **compiled into plugins** from the included build `build-logic`.

### 7.1. Repository Structure

~~~text
company-gradle-sample/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       ├── company.java-conventions.gradle.kts
│       └── company.boot-app.gradle.kts
├── shared/
│   ├── build.gradle.kts
│   └── src/main/java/com/example/shared/
│       └── Greeter.java
└── service/
    ├── build.gradle.kts
    ├── src/main/java/com/example/service/
    │   └── ServiceApplication.java
    └── src/test/java/com/example/service/
        └── ServiceApplicationTests.java
~~~

Reuse the **exact same three Java source files** from sections 5.4, 5.6, and 5.7. Those files are independent of Maven APIs; Spring Boot dependencies and JUnit are managed by Gradle. The hand-written example tree omits the Gradle Wrapper, though in real projects you should generate and commit `gradlew`/`gradlew.bat` and `gradle/wrapper/*`.

### 7.2. Root `settings.gradle.kts` — Plugin Resolution and Modules

Create `company-gradle-sample/settings.gradle.kts`:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
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

rootProject.name = "company-gradle-sample"
include("shared", "service")
~~~

**Exact explanation:**

- `pluginManagement.includeBuild("build-logic")` lets `plugins { id("company...") }` in subprojects resolve unpublished plugins.
- `pluginManagement.repositories` resolves Gradle plugins and plugin markers.
- `dependencyResolutionManagement.repositories` resolves **application/library dependencies** in the root build.
- `include("shared", "service")` creates the Java subprojects.
- Do not declare `include("build-logic")`: it is **not** an application code module, but an included build with its own lifecycle and build scripts.

### 7.3. `build-logic/settings.gradle.kts`

Create `build-logic/settings.gradle.kts`:

~~~kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

rootProject.name = "build-logic"
~~~

An included build has its own settings; the root main build's `dependencyResolutionManagement` **does not automatically configure repositories for `build-logic`**. That is why the next `build-logic` file also defines the needed repositories.

### 7.4. `build-logic/build.gradle.kts`

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

dependencies {
    implementation(
        "org.springframework.boot:spring-boot-gradle-plugin:3.5.16"
    )
}
~~~

`kotlin-dsl` is the core Gradle plugin for compiling precompiled Kotlin DSL script plugins. `spring-boot-gradle-plugin` sits on **`build-logic`'s plugin implementation classpath** so `company.boot-app.gradle.kts` can apply `org.springframework.boot` **without repeating its version** inside the precompiled script.

**Important note from Gradle documentation:** precompiled script plugins **do not support** `version "..."` or `apply false` syntax inside their script `plugins { }` block. External/community plugin versions must come from **`build-logic`'s dependencies**, as shown above. Do not write `id("org.springframework.boot") version "3.5.16"` inside `company.boot-app.gradle.kts`.

### 7.5. Java Convention Plugin: `company.java-conventions.gradle.kts`

Create `build-logic/src/main/kotlin/company.java-conventions.gradle.kts`:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    `java-library`
}

group = "com.example"
version = "1.0.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

When a module applies `company.java-conventions`, it receives:

- The `java-library` plugin (including Java compilation, JAR, and dependency configurations).
- A target Java 17 **toolchain** for supported tasks.
- UTF-8 compiler encoding and `--release 17`.
- `Test` tasks configured with JUnit Platform.
- Shared `group`/`version` setting artifact coordinates.

This is the **example's policy**, not the only formula: in multi-product organizations, avoid hardcoding shared `group/version` if modules need independent versioning. You can use Gradle properties/version catalogs or extension conventions, letting each module opt into exceptions explicitly for good reasons.

**Do not add `org.springframework.boot` to this Java convention**, because the `shared` library is not an executable app. Also do not add Spring Boot starters to every Java module simply because service modules use Spring Boot.

### 7.6. Boot Convention Plugin: `company.boot-app.gradle.kts`

Create `build-logic/src/main/kotlin/company.boot-app.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:3.5.16")
    )
}
~~~

The `company.boot-app` plugin brings:

- The Spring Boot Gradle Plugin (version managed via `build-logic/build.gradle.kts`).
- The Java plugin so Boot recognizes the Java project and creates the `bootJar` task.
- The Spring Boot BOM as a **Gradle native platform** for production and test dependencies. This is a version management mechanism and does **not** automatically add starters.

Because this file is precompiled and **applies `java` in the same script**, dependency configurations like `implementation` and `testImplementation` are available in the script's Kotlin DSL. `company.java-conventions` also applies `java-library` (which includes the Java plugin); Gradle plugin application with the same ID/type is idempotent, so it does not create duplicate Java compiler tasks.

A BOM on `implementation` already participates in related classpaths; declaring it explicitly on `testImplementation` in the example makes test dependency management intent unmistakable without relying on how custom projects structure configurations.

**Keep in mind:** Gradle `platform` treats the BOM as dependency version constraints. Do not assume a Gradle native BOM forces every version regardless of conflicts; Gradle uses its own version selection rules. If an organization needs strict version locking, evaluate `constraints`/`strictly`/`enforcedPlatform` along with their impact on consumers.

### 7.7. `shared/build.gradle.kts` — Apply Only the Java Convention

~~~kotlin
plugins {
    id("company.java-conventions")
}
~~~

`shared` does not apply `company.boot-app`, so it **has no `bootJar` task from the Boot plugin**, does not import the Boot BOM unless requested separately, and produces only a normal Java library JAR.

`shared/src/main/java/com/example/shared/Greeter.java` matches section 5.4. Gradle does not require Spring Boot dependencies to compile that Java source.

### 7.8. `service/build.gradle.kts` — Apply Both Conventions

~~~kotlin
plugins {
    id("company.java-conventions")
    id("company.boot-app")
}

dependencies {
    implementation(project(":shared"))
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
~~~

Spring Boot dependencies omit versions because `company.boot-app` already declared the BOM platform. `implementation(project(":shared"))` is the **inter-module dependency** — not implied by applying the same convention plugin.

`testRuntimeOnly("org.junit.platform:junit-platform-launcher")` supplies the test runtime launcher per modern Gradle/JUnit recommendations; its version can be managed by the BOM. `company.java-conventions` already enabled `useJUnitPlatform()`, so JUnit Jupiter `@Test` methods are discovered. There is no need to install the Spring Boot plugin in `shared`.

In `service`, the Spring Boot plugin sees the Java plugin and provides `bootJar`. In Boot 3.x lines, a plain JAR task may still exist with a different classifier (such as `plain`); **the deployable application artifact is the `bootJar` output**, rather than grabbing any arbitrary JAR in `build/libs`.

### 7.9. Build and Run Gradle

Use the Gradle Wrapper properly generated and committed for the project:

~~~bash
./gradlew clean build
./gradlew :service:bootJar
java -jar service/build/libs/service-1.0.0-SNAPSHOT.jar
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean build
.\gradlew.bat :service:bootJar
java -jar .\service\build\libs\service-1.0.0-SNAPSHOT.jar
~~~

If a self-created example **does not have a Wrapper yet**, run `gradle clean build` and `gradle :service:bootJar` with a compatible Gradle release. Boot 3.5.16 requires Java 17+ and a compatible Gradle release per Spring Boot 3.5 docs; the example selects **Gradle 8.14.x**, rather than switching to Gradle 9 simply because current Gradle docs mention 9.x.

**Line printed by the application:** `Hello, team!`, matching the business logic in the Maven demo. Do not expect identical full stdout to Maven because Gradle/Maven are not running during `java -jar` and Boot log formats depend on the environment.

### 7.10. Inspect Gradle Configuration and Dependency Resolution

~~~bash
./gradlew projects
./gradlew :shared:tasks --all
./gradlew :service:tasks --all
./gradlew :service:dependencies --configuration runtimeClasspath
./gradlew :service:dependencyInsight \
  --dependency spring-boot-starter \
  --configuration runtimeClasspath
~~~

`projects` shows subprojects `shared` and `service`. `tasks` shows `bootJar` in `service`, yet **there must be no `bootJar` in `shared`** because `shared` does not apply the Boot convention. `dependencies` and `dependencyInsight` show resolved versions after BOM platforms, constraints, and transitive dependencies.

The `build-logic` directory is an **included build**, so it does not appear as a `:build-logic` subproject; that is normal. If `Plugin [id: 'company...'] was not found` occurs, inspect `pluginManagement.includeBuild(...)`, script names, file paths, and `build-logic` compilation before editing application code.

### 7.11. Inspect the Library JAR and Boot JAR

~~~bash
./gradlew :shared:jar :service:bootJar
jar tf shared/build/libs/shared-1.0.0-SNAPSHOT.jar
jar tf service/build/libs/service-1.0.0-SNAPSHOT.jar
~~~

In the thin library JAR, `com/example/shared/Greeter.class` sits at the archive root. In the Boot executable JAR, application classes sit in `BOOT-INF/classes` and the shared dependency typically sits at `BOOT-INF/lib/shared-1.0.0-SNAPSHOT.jar`, alongside Spring Boot runtime libraries.

If output filenames differ because `archiveBaseName`, `archiveClassifier`, or `version` was overridden, use the **actual paths inside `build/libs`** instead of relying on example names.

## 8. Comparing the Same Policy Between Maven and Gradle

| Common Goal | Maven Parent/Aggregator | Gradle Convention Plugin / Included Build |
| --- | --- | --- |
| Select Java release 17 | Parent `maven.compiler.release` + Compiler Plugin | Java toolchain + `JavaCompile.options.release` in Java convention |
| UTF-8 | Parent `project.build.sourceEncoding` | `JavaCompile.options.encoding` |
| JUnit 5 | Parent Surefire version; module declares test dependency | Java convention `useJUnitPlatform()`; module declares test deps |
| Manage Spring Boot versions | Parent `dependencyManagement` imports Boot BOM | Boot convention `platform("...spring-boot-dependencies...")` |
| Manage Boot build plugin version | Parent `pluginManagement` | `spring-boot-gradle-plugin` dependency of `build-logic` |
| Enable executable packaging | Only `service` declares plugin + `repackage` goal | Only `service` applies `company.boot-app` → `bootJar` |
| Build library JAR | `shared` packaging `jar`, no `repackage` | `shared` applies Java convention, `jar` task |
| Define modules | Root `<modules>` | Root `settings.gradle.kts include(...)` |
| Inter-module dependency | `<dependency>shared</dependency>` with GAV | `implementation(project(":shared"))` |
| Share logic across repositories | Parent POM published to Maven repository | Publish binary convention plugin or use included build/versioned plugin |
| Inspect effective configuration | `help:effective-pom`, `dependency:tree` | `tasks`, `dependencies`, `dependencyInsight`, build reports |

This is a **functional comparison table**, not a 1-to-1 syntax translation. Maven's parent inheritance and Gradle's plugin application have different merge, override, evaluation, and resolution rules.

## 9. Dependency Versions: Maven BOM, Gradle Platform, and Version Catalog

### 9.1. Version Policy and Build Policy Are Two Layers

**Version policy** answers "which version of `spring-context`/JUnit are we using?". **Build policy** answers "how do compiler, tests, packaging, and quality tasks run?".

One parent POM or convention plugin can handle both, yet they should not be conflated:

- Maven `dependencyManagement` and an imported BOM manage versions; `dependencies` adds libraries.
- Gradle `platform(...)` imports BOM constraints; `implementation(...)` adds libraries.
- A Gradle **version catalog** (such as `gradle/libs.versions.toml`) defines aliases/versions for dependencies/plugins, letting modules reference them via `libs....`. A catalog **does not apply Java compiler conventions**, does not create Boot tasks, and does not add dependencies unless a build script uses those aliases.
- Gradle convention plugins apply/configure plugins and tasks; they can use a version catalog, yet those remain two distinct concepts.

### 9.2. Maven BOM Does Not Replace a Parent

If your organization's parent is `company-parent`, you can import the Spring Boot BOM inside `dependencyManagement` in the parent or in the Boot module. Choose an impact scope that fits: a corporate parent shared across all Java projects probably should not force every module onto the same Boot release.

If multiple modules are Spring Boot apps, you can create an **intermediate parent** inheriting the corporate parent and adding Boot conventions/version management, while the root aggregator stays independent. A Maven project still has only **one direct parent**, yet the parent inheritance chain can have multiple levels.

### 9.3. Gradle Does Not Import the BOM Simply by Applying `org.springframework.boot`

The Spring Boot Gradle Plugin provides tasks and integration with dependency management, yet **applying only the Boot plugin does not mean every versionless dependency is automatically managed**. Per documentation, you either use `io.spring.dependency-management` (with which the Boot plugin integrates to import the BOM) or Gradle's native `platform(...)`.

In this example, `company.boot-app` intentionally uses a **native platform**, so adding `io.spring.dependency-management` is unnecessary. Do not mix both mechanisms just to "make sure the BOM is there"; doing so can create conflicts or hard-to-explain resolution differences.

### 9.4. Overriding Managed Versions Requires Control

A Boot BOM is a tested set of compatible versions. When an enterprise overrides a library for a security patch, use appropriate dependency management/Gradle constraints, inspect the dependency tree, and run regression tests. **Do not define a Maven property with the same name as one in an imported BOM assuming it will override**, as happens when inheriting starter parent; configure explicit management instead.

In Gradle, `platform` provides **constraints** and does not turn BOM-recommended versions into hard requirements if the graph contains other constraints/conflicts. Do not use `enforcedPlatform` broadly without understanding its impact on consumers.

## 10. Organizing Multiple Module Types Without Sharing All Plugins

An enterprise repository may contain:

~~~text
platform
├── domain-api/                 # Java library
├── core-data/                  # Java library
├── http-service/               # Spring Boot executable app
├── batch-worker/               # Spring Boot executable app
└── integration-tests/          # Tests / fixtures / performance
~~~

Put Java toolchain, encoding, and basic test setup in a **base convention**. Put specialized packaging/lifecycle rules into targeted groups:

- **Java library convention:** `java-library`, Java release, test tasks, publishing conventions; never package Boot executable JARs.
- **Spring Boot app convention:** apply Boot plugin, BOM/dependency management, `bootJar`, integration smoke-test packaging; only for real services/workers.
- **Integration-test convention:** test suites, testcontainers dependencies, resource limits, and CI reporting when needed.
- **Publishing convention:** signing, Maven publication/group/version policies when actually publishing; do not force every module to publish.

In Maven, you can achieve similar layering via parent inheritance tiers, parent `pluginManagement`, appropriate profiles, or company Maven plugins. **Do not cram every execution into one parent so it runs automatically on every module type**; for example, `spring-boot:repackage` in a parent can turn a Java library into an artifact unsuitable for other modules to compile against.

## 11. Override Rules and Blast Radius

### 11.1. Parent POM: Children May Override Configuration

A Maven child can add to or override parent-managed configuration per model-merging rules. Attributes like `<inherited>false</inherited>` on a plugin execution can limit inheritance per the parent's intent, yet should not be used as a widespread "band-aid" after putting an execution at the wrong level.

A versioned and published enterprise parent creates a **change boundary**: children bump the parent version when opting into a new policy. In a monorepo, sharing the same parent version across modules keeps one build consistent. With a Maven reactor using a local parent `../pom.xml`, the parent must have the exact version/coordinates declared by children.

### 11.2. Gradle: Conventions and Project-Specific Overrides

Convention plugins typically set **defaults**. Modules can explicitly add custom config:

~~~kotlin
// In service/build.gradle.kts, after plugins { ... }
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-Xlint:unchecked")
}
~~~

This is a **Gradle Kotlin DSL snippet** in a project with the Java plugin; it adds a lint warning while preserving Java 17, encoding, and Test conventions. **Do not arbitrarily change the Java version for a single service** without verifying compatibility across library boundaries.

Plugin application/configuration order and Gradle's lazy Provider API affect a property's final value. A convention should use `Property.convention(...)` when exposing overridable extensions rather than calling `set(...)` after module values if you genuinely want defaults. In the example, `options.release.set(17)` is an **enforced policy** for every module applying the Java convention; a module can still override it at an appropriate phase, yet should not rely on accidental ordering.

### 11.3. Why Avoid `subprojects { ... }` at Root

A root `subprojects { apply(plugin = "java") ... }` can misconfigure non-Java modules, increase cross-project coupling, complicate test/plugin isolation, and create obstacles for configuration cache and isolated projects. Convention plugins let modules **declare their own type**. If global constraints genuinely apply to all projects, place them in settings/plugin management/enterprise policy appropriately rather than using a root script to replace every convention plugin.

## 12. CI and Build Logic Governance

### 12.1. Execute the Right Modules in CI

Maven:

~~~bash
mvn -B -ntp clean verify
mvn -B -ntp -pl service -am package
~~~

Gradle:

~~~bash
./gradlew --no-daemon clean build
./gradlew --no-daemon :service:bootJar
~~~

In CI, prefer the Maven/Gradle Wrapper (when present in the repo) to pin tool versions and reduce local/runner drift. You do not have to build the entire repository on every step if affected-module detection is used, yet you must keep the dependency graph intact: `service` requires `shared`.

### 12.2. Inspect Artifacts Alongside Modules

A release pipeline should:

- Clearly distinguish whether an artifact is a **service executable JAR** or a library JAR.
- Run tests across both library and service according to required scope.
- Verify the Boot executable JAR has `BOOT-INF/classes` and `BOOT-INF/lib`.
- Inspect the manifest when needed (Boot loader `JarLauncher` and `Start-Class`).
- Run `java -jar` on the exact artifact to be deployed, not just `mvn test` or `gradlew test`.
- Pin versions and check the dependency graph so a module does not inadvertently pull a different Boot release.

### 12.3. Controlling Changes to Parents/Convention Plugins

A seemingly small edit to a Java convention (e.g., bumping `--release`, enabling parallel tests, changing dependency constraints) can impact dozens of modules. Process:

1. Document the scope of the policy change and affected modules.
2. If publishing a Maven parent, choose a new parent version with changelog/migration notes; never overwrite an already published release artifact.
3. If using a Gradle included build in the same repo, review code in `build-logic` like production/CI code; any plugin change executes during configuration time.
4. Maintain integration tests covering at least one **library module** and one **Boot app module** to catch packaging regressions.
5. Use dependency reports/effective POM to diff before and after.
6. Run a clean build in CI and test the release artifact.
7. Prefer small version increments with a rollback plan.

**Security:** build scripts/convention plugins are **executable code running on developer machines and CI**, with access to environment variables, credentials, and the filesystem. Only use plugins/dependencies from trusted sources, review changes carefully, and never hardcode secrets in `pom.xml`, `build.gradle.kts`, or `gradle.properties` committed to the repository.

### 12.4. When to Publish a Convention Plugin?

If an organization has dozens of repositories sharing policies, copy-pasting an included build across repos causes drift. You can turn convention plugins into **binary Gradle plugins** published to an internal plugin repository, letting each repo upgrade versions deliberately.

For a single multi-project repo, the included build `build-logic` is usually simpler: it lives in the same source control with no separate plugin release cycle. A versioned Maven parent POM can be published relatively easily to a Maven artifact repository to serve multiple repos. There does not have to be "one single Maven parent for the entire company"; when requirements diverge, consider lower-tier parents or group-specific build extensions/conventions.

## 13. Multi-Module Troubleshooting: 15 Practical Scenarios

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| Maven `service` reports `com.example:shared` not found | Built `service` standalone, `shared` not installed; wrong GAV | Run `mvn -pl service -am package` from aggregator; check dependency coordinates |
| Maven `Non-resolvable parent POM` | Wrong `<parent>` version/`relativePath` or parent missing from repo | Check `../pom.xml`, GAV, and settings repositories |
| Parent has BOM yet child starter lacks version | Wrong type/import scope, or parent not actually inherited | Check `help:effective-pom` and `dependencyManagement` |
| Maven builds all modules yet Java release is not inherited | Root only aggregates via `<modules>`, child uses another parent | Inspect child `<parent>` and effective POM instead of inferring from root location |
| `shared` turns into a Boot executable JAR | Boot plugin execution in parent `build/plugins` or in child `shared` | Put Boot plugin version in parent `pluginManagement`, execution in app |
| `spring-boot:repackage` does not run on `service` | Not using starter parent; child only has BOM/plugin version | Declare Boot plugin + `repackage` goal in `service` |
| Gradle reports `Plugin [id: 'company.java-conventions'] was not found` | Wrong `includeBuild`, mismatched filename/ID, or `build-logic` fails to compile | Check settings `pluginManagement.includeBuild("build-logic")` and `build-logic` logs |
| Gradle errors on `version "..."` inside a precompiled plugin | External plugin version placed in the wrong file | Add plugin artifact to `build-logic` `implementation(...)`; use versionless ID in convention script |
| Gradle `shared:bootJar` appears and fails looking for main class | Boot convention applied to library | Apply only Java convention in the library |
| Gradle `service` starter lacks version | Boot plugin applied without importing BOM | Add `implementation(platform(...spring-boot-dependencies...))` or dependency-management plugin |
| `useJUnitPlatform` set yet no tests discovered | Missing JUnit engine/launcher or test deps | Check `testRuntimeClasspath`, starter-test, launcher, and Gradle Test reports |
| Local build passes, CI reports `invalid target release` | Maven/Gradle JVM/toolchain lacks matching JDK | Check `java -version`, `mvn -version`, `./gradlew --version`, and toolchains |
| Gradle included build uses different repositories from main build | `build-logic` is an independent build and does not inherit settings repos | Declare repositories in the included build or share policy intentionally |
| `service` JAR lacks `shared` at runtime | Gradle `compileOnly`/Maven `provided` used wrongly, or deployed thin JAR | Check runtime dependency graph and `BOOT-INF/lib` |
| Modules resolve different library versions | Parent/BOM/Gradle platform not applied consistently | Inspect `dependency:tree`, `dependencyInsight`, and effective configuration |

### 13.1. Step-by-Step Debugging Method

**Step A — Module topology:** Does the root declare Maven `<modules>`/Gradle `include` properly? Does `service` have an actual dependency on `shared`?

**Step B — Policy propagation:** Does the Maven child have the right parent? Does the Gradle subproject apply the right convention plugin?

**Step C — Versions:** Are Maven `dependencyManagement` and `pluginManagement`, or Gradle `platform`/plugin classpaths selecting expected versions?

**Step D — Execution:** Is the Boot plugin/execution activated **only** on `service`? Does `shared` remain a normal library JAR?

**Step E — Artifact:** Run tests and inspect the exact executable JAR. If output differs from expectations, do not edit Java code before checking the build graph and tasks.

## 14. Practice Exercises with Answers

**Q1.** The root POM has `<modules><module>shared</module>...`, yet `shared/pom.xml` omits `<parent>`. Does the module automatically inherit parent properties?  
**Answer:** No. Aggregation and inheritance are independent; you must declare `<parent>` properly or receive policy through another mechanism.

**Q2.** The parent has `spring-boot-dependencies` in `dependencyManagement`. `shared` declares no Spring dependencies. Does it automatically pull in the Spring Boot runtime?  
**Answer:** No. Dependency management only manages metadata for dependencies that are actually used.

**Q3.** The parent manages `spring-boot-maven-plugin`'s version inside `pluginManagement`. Why might `mvn package` in `service` still build a plain JAR?  
**Answer:** Because the `repackage` goal has not been activated. `service` needs the plugin/execution configured or inherited as an actual execution from the parent.

**Q4.** Gradle `settings.gradle.kts` has `include("shared","service")`. Why can't both modules use the `company.java-conventions` convention yet?  
**Answer:** Either the plugin source has not been declared (`pluginManagement.includeBuild("build-logic")` or publishing/resolution), or the modules have not applied the plugin.

**Q5.** Inside a Gradle precompiled plugin, is adding `id("org.springframework.boot") version "3.5.16"` valid?  
**Answer:** No. For precompiled script plugins, add the external plugin artifact as a dependency of `build-logic` and apply the plugin ID without a version in the script.

**Q6.** Does applying the same `company.java-conventions` let `service` see `shared`'s `Greeter` class?  
**Answer:** No. You need `implementation(project(":shared"))` in Gradle, or a `com.example:shared:...` dependency in Maven.

**Q7.** Why should a library not run Boot `repackage`?  
**Answer:** Executable Boot JARs use a `BOOT-INF/classes` layout; that is not an ordinary library JAR classpath root for dependent compilers to read directly. Libraries should use thin JARs.

**Q8.** You want to change the Java release across 30 modules. Where should you edit?  
**Answer:** Maven: parent `maven.compiler.release`/compiler configuration; Gradle: Java convention plugin/toolchain. Verify both library modules and Boot apps afterward.

**Q9.** Once a dependency is listed in the BOM, is it automatically present on the app classpath?  
**Answer:** No. The BOM only provides version constraints/managed versions; the dependency must be declared by a module or brought in via a valid transitive path.

**Q10.** Should you use `subprojects { ... }` to enforce the Spring Boot plugin on every Gradle module?  
**Answer:** No. Java libraries, tools, and Boot apps have different packaging needs. Create role-specific conventions and apply them only to appropriate modules.

## 15. Practical Pre-Merge Checklist

- [ ] Module structure is properly defined: Maven `<modules>` or Gradle `include(...)`.
- [ ] Inter-module dependencies exist explicitly, rather than relying on sharing a parent/convention.
- [ ] Maven children declare `<parent>` with accurate GAV/relativePath when inheritance is needed.
- [ ] Maven parent configures `dependencyManagement` and `pluginManagement` properly without accidentally adding Boot starters or `repackage` to all modules.
- [ ] Gradle `build-logic` has its own settings/build files and is registered in plugin management via `includeBuild`.
- [ ] Precompiled scripts have matching plugin IDs and filenames; external plugin artifacts/versions are declared on `build-logic`'s classpath.
- [ ] Java release/encoding/test framework are consistent and verified per module.
- [ ] Spring Boot BOM/platform manages versions; modules add only dependencies they truly use.
- [ ] Spring Boot plugin/packaging is activated only on executable apps; thin libraries keep proper layout.
- [ ] Full reactor/multi-project build succeeds using Wrapper or team-managed tool versions.
- [ ] Effective POM/dependency tree or Gradle tasks/dependencyInsight were compared whenever differences appeared.
- [ ] CI inspects the exact final artifact and never deploys a thin JAR or `plain` artifact by mistake.
- [ ] Build logic is reviewed like executable code; no secrets are committed into scripts.
- [ ] Regression tests cover at least one library module and one Spring Boot app module.

## 16. Official Documentation

- Apache Maven — Introduction to the POM (Inheritance vs Aggregation): https://maven.apache.org/guides/introduction/introduction-to-the-pom.html
- Apache Maven — POM Reference (dependencyManagement, pluginManagement): https://maven.apache.org/pom.html
- Apache Maven — Introduction to Dependency Mechanism (BOM import): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Compiler Plugin — Setting compiler release: https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html
- Maven Help Plugin — Effective POM: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Gradle — Best Practices for Structuring Builds: https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html
- Gradle — Implementing Precompiled Script Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
- Gradle — Convention Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html
- Gradle — Sharing Build Logic between Subprojects: https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html
- Gradle — Composite Builds: https://docs.gradle.org/current/userguide/composite_builds.html
- Gradle — BOM/Platform Dependency Management: https://docs.gradle.org/current/userguide/platforms.html
- Spring Boot 3.5 — Maven Using Boot without Parent POM: https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html
- Spring Boot 3.5 — Gradle Plugin Managing Dependencies: https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html
- Spring Boot 3.5 — Gradle Plugin Getting Started: https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html

**Conclusion:** In Maven, use **parent POMs for inheritance**, **aggregators for the reactor**, and declare **inter-module dependencies** separately. In Gradle, encapsulate policies into **convention plugins** inside `build-logic`, then let subprojects explicitly apply the right conventions. With Spring Boot, keep **library JARs** and **executable Boot JARs** strictly distinct: shared version management does not mean every module should receive the same starters or executable packaging.
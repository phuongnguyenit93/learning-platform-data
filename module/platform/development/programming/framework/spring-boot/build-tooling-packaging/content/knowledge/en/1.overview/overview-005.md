# Relationship Between Starters, BOMs, and Packaging Plugins in Spring Boot

## 1. Objectives

After this lesson, you will be able to distinguish three roles in building a Spring Boot application:

- **Starter** answers **"Which libraries does the application need to enable a set of capabilities?"**
- **BOM (Bill of Materials)** answers **"Which versions of those libraries should be used so they work together?"**
- **Packaging plugin** answers **"How do we turn compiled code and runtime libraries into an executable, releasable artifact or container image?"**

These three components complement each other without replacing one another. An application can declare the right starter and have its versions managed by a BOM yet still produce only a plain JAR if executable JAR packaging is not configured.

**Scope:** Maven and Gradle, focusing on understanding and verifying dependencies, builds, and artifacts. Examples use **Spring Boot 4.1.2 and Java 17** for consistency; when upgrading versions, update and check compatibility against official documentation.

## 2. Concept Map

| Component | Category | What Does It Do? | What Does It Not Do Automatically? |
| --- | --- | --- | --- |
| Starter, e.g., `spring-boot-starter-webmvc` | Dependency | Declares a cohesive dependency group for writing MVC apps and pulls in required transitive dependencies. | Does not dictate the entire versioning strategy, compile code, or create a JAR runnable via `java -jar`. |
| BOM, `org.springframework.boot:spring-boot-dependencies` | Dependency management / platform | Provides a curated set of versions managed and tested together by Spring Boot. | Does not add libraries to the classpath on its own, contains no application code, and does not directly control packaging. |
| Maven plugin `spring-boot-maven-plugin` | Build plugin | Provides goals like `repackage`, `run`, and `build-image`; converts a JAR/WAR into an executable archive when configured. | Does not replace declaring starters or importing a BOM; is not a runtime dependency of the application. |
| Gradle plugin `org.springframework.boot` | Build plugin | Adds and configures tasks like `bootJar`, `bootRun`, and `bootBuildImage` when combined with the Java plugin. | Does not automatically manage all dependency versions unless an appropriate BOM mechanism is applied. |
| Maven `spring-boot-starter-parent` | Parent POM | Bundles Maven defaults, dependency management, and plugin management; preconfigures the `repackage` execution when the Boot plugin is used. | Not a starter declared under `<dependencies>`; does not directly pull web libraries into the application. |

Overall flow:

```text
Declare starter ──> direct dependencies + transitive dependencies
                              │
                              ▼
                    BOM manages versions
                              │
                              ▼
                    Resolve dependency graph
                              │
                              ▼
                  Compile + run tests
                              │
                              ▼
             Maven/Gradle packaging plugin
                              │
                              ▼
        Executable JAR/WAR (or container image)
                              │
                              ▼
                     java -jar / deploy
```

Note: this is a responsibility diagram, not a claim that the BOM "executes" as a separate build step. The build tool applies BOM information **when resolving dependencies**; plugins execute according to configured lifecycles/tasks.

## 3. Starter: Selecting Capabilities, Pulling the Right Library Set

A starter is typically an artifact with a POM declaring related dependencies. Rather than hand-picking individual versions of Spring MVC, logging, an embedded container, and supporting libraries, you add the corresponding starter. In Spring Boot 4, the recommended starter for Servlet MVC apps is `spring-boot-starter-webmvc`; the older name `spring-boot-starter-web` has been deprecated. For reactive applications, consider `spring-boot-starter-webflux`. Starters for persistence, validation, or testing serve specific needs, such as `spring-boot-starter-data-jpa`, `spring-boot-starter-validation`, and `spring-boot-starter-test`.

Maven dependency example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

The two dependencies above **omit `<version>`** only when the project already inherits appropriate dependency management from a parent or BOM. A starter puts libraries onto the classpath; then Spring Boot's **auto-configuration** evaluates the classpath, beans, and properties to configure matching components. Therefore, "adding a starter" does not mean every feature is unconditionally active: auto-configuration is conditional and can be altered by properties, excluded dependencies, and developer-defined beans.

You can remove an unwanted transitive dependency using `<exclusions>` (Maven) or `exclude` (Gradle), though you must evaluate the impact. For example, excluding the embedded server without declaring a replacement server can prevent a web application from running as expected.

## 4. BOM: Aligning Versions

A **BOM** is a POM listing managed versions of dependencies. `spring-boot-dependencies` manages numerous Spring and third-party libraries tested with a given Spring Boot release line. When declaring a dependency managed by the BOM, you can omit its version at the declaration site.

Key points to remember:

1. A BOM **manages versions**; it does not add dependencies by itself. Importing a BOM without declaring a starter will not make Spring MVC appear.
2. A dependency with an explicit `<version>` (or another Gradle rule/constraint) can alter the resolved version; do not assume the BOM always overrides every constraint.
3. A Spring Boot release is tested against a matching set of dependency versions. Overriding foundational versions like Spring Framework, Jackson, or logging requires thorough testing because linkage or compatibility errors can easily arise.
4. **Importing a Maven BOM does not bring along a parent's plugin management.** This is a critical distinction when a project must inherit from an organization's own parent POM.
5. Keep the BOM release line, Boot build plugin, and Spring Boot artifacts aligned; share a common version property if your build config allows.

### Maven: Two Ways to Receive the BOM

**Approach A — inherit from `spring-boot-starter-parent`:** the parent already imports dependency management from the BOM and supplies compiler/plugin defaults. Typically, you declare the version only in `<parent>`.

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>
```

**Approach B — import the BOM when using another parent or no Boot parent:**

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

In Approach B, **you must explicitly configure plugins and needed build defaults**. Simply importing `spring-boot-dependencies` does not tell Maven the version of `spring-boot-maven-plugin`, does not set up the `repackage` execution, and is not equivalent to inheriting `spring-boot-starter-parent`.

### Gradle: Two Dependency Management Mechanisms

- **Gradle native BOM:** add `platform(...)` to the dependency configurations that need version management. This is a clean option without needing a separate dependency management plugin.
- **`io.spring.dependency-management` plugin:** when used alongside the Spring Boot Gradle plugin, the BOM matching the Boot plugin version is imported automatically; this mechanism supports customizing certain versions via BOM properties.

With Gradle's native `platform`, the BOM applies **constraints**. Applying a constraint to `implementation` does not mean every independent configuration receives it; apply the BOM to configurations like `testImplementation` as needed. `enforcedPlatform` forces versions more aggressively, which can affect downstream consumers, so use it only with clear justification.

## 5. Packaging Plugin: Creating a Runnable Deliverable

In Maven, `spring-boot-maven-plugin` provides the `repackage` goal. It processes the built JAR/WAR to produce an **executable archive** containing application classes, runtime libraries, and the Spring Boot loader. When using the Boot parent, the `repackage` execution is already defined; you only declare the plugin under `<build><plugins>`. When only importing the BOM, declare the plugin version and appropriate execution.

In Gradle, the `org.springframework.boot` plugin works with the `java` plugin to register the `bootJar` task; for WARs, `bootWar` is available when the WAR configuration is applied. The standard `jar` task produces a plain JAR; `bootJar` produces an executable JAR. In common configurations, the plain JAR receives the `plain` classifier to distinguish it from the runnable archive.

A typical executable JAR contains:

```text
demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/classes/      # application .class files and resources
├── BOOT-INF/lib/          # runtime dependencies as nested JARs
└── org/springframework/boot/loader/...  # Boot launcher
```

Accordingly, a Spring Boot executable JAR is **neither** a thin JAR containing only classes, nor necessarily a shaded JAR that unpacks and merges all dependencies into one class tree. Runtime dependencies are packaged as nested JARs so the Boot launcher can load them. The plugin can also include layer metadata to optimize container images; when needed, it provides tasks/goals to create OCI images using buildpacks, subject to environment prerequisites.

## 6. Runnable Example: Maven with `starter-parent`

Create the following three files. This example uses Spring Boot 4.1.2 and Java 17; Maven must be a version supported by Spring Boot. Filenames and package paths must match.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

**`src/main/java/com/example/demo/DemoApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello Boot";
    }
}
```

**Commands:**

```bash
mvn clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

In another terminal:

```bash
curl http://localhost:8080/hello
```

The exact HTTP response body is `Hello Boot` (there is no trailing newline in the string returned by the controller). Startup logs depend on the environment, so do not treat them as fixed stdout. Actual flow: the starter brings MVC dependencies; the parent manages versions; Maven compiles the code; the Boot Maven plugin repackages the JAR; and the Boot launcher starts the app with embedded Tomcat handling the endpoint.

**Switching from parent to standalone BOM:** if the project does not inherit from the Boot parent, use `<dependencyManagement>` from section 4, keep the `spring-boot-starter-webmvc` dependency, and explicitly add plugin configuration like this:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.14.1</version>
        </plugin>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>4.1.2</version>
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
```

This is a **supplementary configuration snippet for a BOM-based POM**, not a complete standalone `pom.xml`. In a real POM, there is only **one** `<build>` block and **one** `<properties>` block; merge these with existing sections. Without configuring the `repackage` execution, `mvn package` may produce only a plain JAR even though the app compiles. You can run `mvn package spring-boot:repackage` explicitly if the plugin is declared and resolved properly.

## 7. Equivalent Configuration with Gradle

Using the same Java file from section 6, replace the Maven build with the following two Gradle Groovy DSL files.

**`settings.gradle`**

```groovy
rootProject.name = 'demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Here:

- `id 'java'` handles base compilation, testing, and JAR tasks.
- `id 'org.springframework.boot' version '4.1.2'` provides Boot tasks, including `bootJar`.
- `platform(SpringBootPlugin.BOM_COORDINATES)` imports the BOM matching the plugin version without repeating the version string.
- `implementation` declares the required starter; `testImplementation` declares testing libraries.

If the project has a Gradle Wrapper, run:

```bash
./gradlew clean bootJar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

On Windows, you can use `gradlew.bat clean bootJar` instead of `./gradlew`. The `bootRun` command runs the app from the development configuration and **does not require creating a JAR first**; `bootJar` is the task that packages the executable JAR. A project using the 4.1.2 Gradle plugin must run with a Gradle version supported by Spring Boot 4.1.x (Gradle 8.14+ in the 8.x line or Gradle 9.x).

If you choose `io.spring.dependency-management` instead of native `platform`, apply that plugin and remove the redundant `platform` declarations; the Boot plugin automatically imports the corresponding BOM. Avoid mixing multiple version management mechanisms unintentionally.

## 8. Verifying Each Responsibility During the Build

| What to Verify | Maven | Gradle | Expected Evidence |
| --- | --- | --- | --- |
| Which dependencies does the starter pull in? | `mvn dependency:tree` | `./gradlew dependencies --configuration runtimeClasspath` | Spring MVC, embedded server, and related artifacts appear in the dependency graph. |
| Did the BOM/parent manage versions? | `mvn help:effective-pom` | `./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath` | Dependencies resolve to concrete versions without specifying versions on each starter declaration. |
| Are the packaging plugin and task present? | Check effective POM and `spring-boot:repackage` log during `mvn package` | `./gradlew tasks --all` looking for `bootJar` | There is a step creating the executable artifact. |
| Does the JAR contain runtime dependencies? | `jar tf target/demo-0.0.1-SNAPSHOT.jar` | `jar tf build/libs/demo-0.0.1-SNAPSHOT.jar` | Contains `BOOT-INF/classes/`, `BOOT-INF/lib/`, and the Spring Boot loader. |
| Does it run standalone? | `java -jar target/demo-0.0.1-SNAPSHOT.jar` | `java -jar build/libs/demo-0.0.1-SNAPSHOT.jar` | Application starts up and returns `Hello Boot` at `/hello`. |

To diagnose overridden versions, inspect the **resolved dependency graph** rather than just reading `pom.xml`/`build.gradle`; resolution results are also shaped by transitive dependencies, constraints, project config, and conflict-resolution rules.

## 9. Practical Usage Scenarios

**Scenario A — new application:** pick the needed starters, use the Boot parent (Maven) or Boot plugin + BOM (Gradle), enable executable artifact packaging, run tests, and test `java -jar`. This is the minimal baseline for a Spring Boot service.

**Scenario B — Maven with a corporate parent:** keep the corporate parent, import `spring-boot-dependencies` into `dependencyManagement`, specify the Boot Maven plugin version, and configure `repackage` explicitly. Since Maven allows only one direct parent, you cannot declare both a corporate parent and the Boot parent as two `<parent>` tags.

**Scenario C — multi-module project:** `domain`/`common` modules are typically standard library JARs; the `service` module contains `main` and needs an executable JAR. You can share BOM version management at an appropriate level, but apply `repackage`/`bootJar` only to modules meant to run standalone. Packaging a library module as an executable JAR and consuming it as a dependency causes problems because classes live under `BOOT-INF/classes` rather than the standard library JAR layout.

**Scenario D — upgrading Spring Boot version:** update the Boot parent or BOM and Boot plugin together to a matching line; review renamed starters, APIs, Java, Maven/Gradle, and managed libraries. Notably, Spring Boot 4 uses `spring-boot-starter-webmvc` instead of the deprecated `spring-boot-starter-web`; do not copy dependency lists blindly from Boot 3 examples without checking the migration guide.

## 10. Common Errors and Root Causes

1. **"I added a starter, why does Maven complain about a missing version?"** The project did not receive an appropriate BOM/parent, declared the dependency in the wrong scope, or used an artifact not managed by the BOM. Inspect `dependencyManagement` and the effective POM.
2. **"I imported the BOM, why isn't Spring MVC available?"** A BOM does not add dependencies. You need to declare `spring-boot-starter-webmvc` and check the dependency tree.
3. **"`mvn package` succeeded, why won't `java -jar` run?"** It may have built only a plain JAR; missing Boot Maven plugin or `repackage` execution (when not using the Boot parent). Check the manifest, `BOOT-INF`, and build logs.
4. **"Why did Gradle generate both `-plain.jar` and another JAR?"** Those are typically the two artifacts from `jar` and `bootJar`. Run the executable JAR produced by `bootJar`.
5. **"I declared the Boot Gradle plugin, why are dependency versions still messy?"** The build plugin alone does not replace BOM configuration; use native `platform` or `io.spring.dependency-management` consistently.
6. **"Why does runtime fail with `NoSuchMethodError`/`ClassNotFoundException`?"** A dependency may have been overridden or excluded incompatibly, or the JAR lacks required runtime libraries. Inspect the resolved graph, scopes/configurations, packaged artifact, and Java version.
7. **"I have the starter, why is a bean missing?"** Auto-configuration depends on the classpath, conditions, properties, and existing beans. Check auto-configuration conditions and active config rather than immediately blaming the BOM or plugin.
8. **"Can I import a service's executable JAR into a library module?"** Usually inappropriate. Separate executable modules from library modules; use plain JARs for libraries.

## 11. Self-Check Exercises

1. If you add only the `spring-boot-dependencies` BOM without `spring-boot-starter-webmvc`, does the app get a web server automatically? **No**; a BOM only manages versions.
2. If you add `spring-boot-starter-webmvc` but omit the Boot Maven plugin in a project using `starter-parent`, is `mvn package` guaranteed to produce an executable JAR? **No**; the parent supplies execution configuration, while the plugin itself must still be declared in the build to run.
3. With another Maven parent, does importing the BOM replace configuring `spring-boot-maven-plugin`? **No**; importing a BOM does not import plugin management or executions.
4. In Gradle, are `jar` and `bootJar` synonymous? **No**; `bootJar` builds an executable archive with the Boot loader and runtime dependencies.
5. To find out the final version of Jackson or Spring Framework, should you inspect declared configuration or the resolved dependency result? The **resolved dependency result** is the decisive evidence.

**Takeaway:** **Starter = select library set; BOM = align versions; packaging plugin = produce executable artifact.** Maven's parent POM can bundle dependency management and plugin configuration together, yet those remain distinct responsibilities.

## 12. Official References

- [Spring Boot — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Boot Gradle Plugin — Getting Started](https://docs.spring.io/spring-boot/gradle-plugin/getting-started.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
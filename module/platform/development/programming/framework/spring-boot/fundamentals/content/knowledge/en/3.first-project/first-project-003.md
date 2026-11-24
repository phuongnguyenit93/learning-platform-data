# Group, Artifact, Package, Versions, and Choosing a Build Tool

When creating your **first Spring Boot project**, one of the most important screens is the project metadata section: **Group**, **Artifact**, **Name**, **Package name**, **Version**, **Java**, **Spring Boot**, and **Build tool**. These fields look similar because they are all names or versions, yet each has a distinct responsibility. Choosing them well from the start keeps source code cleanly structured, manages dependencies consistently, and gives packaged artifacts a clear identity.

This lesson explains the meaning of each field, the relationships among them, how to choose between Maven and Gradle, and how to identify the corresponding values in a generated project.

## 1. A Spring Boot project has multiple kinds of identity

Suppose you need to create a product catalog service for a fictional company Acme. You might declare:

| Field | Example Value | Primary Role |
| --- | --- | --- |
| Group | `com.acme` | Group/organization owning the artifact in the build ecosystem |
| Artifact | `catalog-service` | Identifier of the module or product being built |
| Name | `Catalog Service` | Human-readable display name of the project |
| Package name | `com.acme.catalog` | Namespace of the Java classes |
| Project version | `0.1.0-SNAPSHOT` | Version of the artifact produced by the project |
| Packaging | `Jar` | Packaging type of the application |
| Java | `21` | Target Java version of the example project |
| Spring Boot | `3.3.5` | Boot framework version used in the example |
| Build tool | `Maven` or `Gradle` | Tool for dependency management, testing, and packaging |

**Version numbers in this lesson are only used to illustrate a consistent configuration, not to claim they are the latest releases.** When creating a real project, pick a supported Spring Boot version and verify compatibility with your Java version, plugins, and libraries.

The most important relationship is:

```text
Maven/Gradle project
  Group:    com.acme
  Artifact: catalog-service
  Version:  0.1.0-SNAPSHOT
        |
        +--> Artifact coordinates: com.acme:catalog-service:0.1.0-SNAPSHOT
        |
        +--> Source code: src/main/java/com/acme/catalog/...
                               ^^^^^^^^^^^^^^^^
                             Separate package name
        |
        +--> Application built and run with Java + Spring Boot
```

In the first three parts of artifact coordinates, **group + artifact + version** identifies one build/release of the product in a dependency management system. **Package name**, on the other hand, defines the namespace of Java source code. The two concepts may align by naming convention, but they are not the same value and cannot substitute for each other.

## 2. Group: identifying the project owner

### 2.1. What does Group mean?

In Maven, group is declared via `groupId`; in Gradle, it is usually declared via the `group` property. Group distinguishes artifacts belonging to one organization, team, or product suite from artifacts of another organization.

The standard convention uses reverse domain notation:

- A company owning `acme.com` can use `com.acme`.
- An organization owning `example.org` can use `org.example`.
- A product team can choose a more specific group, such as `com.acme.platform`.

This is a **naming convention**, not a requirement that the project must run on that domain. The goal is to reduce identifier collisions across libraries and systems.

For example, an organization develops three modules:

```text
com.acme:catalog-service:0.1.0-SNAPSHOT
com.acme:order-service:0.2.0-SNAPSHOT
com.acme:common-utils:1.0.0
```

All three share the same group while having different artifacts. If published to an internal Maven repository, the group helps organize and look up artifacts by owning group.

### 2.2. Choosing a group for your first project

For personal exercises, you can use `com.example`, `org.example`, or a study-oriented group. For long-lived projects, choose a stable group belonging to an organization or scope you actually manage. If your team already has a convention, follow that exact convention so modules in the same product do not end up under different groups.

**Group does not determine which port the application listens on, what REST API URLs look like, or which environment runs the application.** It is metadata for artifact identification and management.

## 3. Artifact: identifying the built product

### 3.1. How does Artifact differ from Group?

In Maven, `artifactId` is the name of the product being built. In Gradle, the project name is declared via `rootProject.name` for a single-project build or subproject names in a multi-module build; that name normally serves as the artifact identifier when publishing.

Example:

```text
Group:    com.acme
Artifact: catalog-service
Version:  0.1.0-SNAPSHOT
```

Maven coordinates of the artifact:

```text
com.acme:catalog-service:0.1.0-SNAPSHOT
```

The generated JAR filename typically contains the artifact and version, such as:

```text
catalog-service-0.1.0-SNAPSHOT.jar
```

However, the output filename can be reconfigured. **Do not treat the observed JAR filename as the sole definition of `artifactId`**; read the build configuration to know the project's identity.

### 3.2. Artifact naming conventions

Choose short, meaningful, readable names that reflect the module's responsibility:

| Name | Remark |
| --- | --- |
| `catalog-service` | Clearly describes a catalog service |
| `billing-api` | Indicates an API related to billing |
| `shared-validation` | Suitable for a shared validation library |
| `project1` | Hard to tell the purpose when there are many projects |
| `spring-boot-demo-final-v2-new` | Contains too much temporary clutter, hard to maintain |

The hyphen `-` is very common in `artifactId`. However, it is **invalid in Java package names**. Thus `catalog-service` is a valid artifact, whereas `com.acme.catalog-service` cannot be a Java package declaration.

### 3.3. Artifact and Name are not synonymous

The `Name` field is typically a display name or project label used by project generators to produce metadata. For example:

```text
Artifact = catalog-service
Name     = Catalog Service
```

In Maven, `<name>Catalog Service</name>` may appear in `pom.xml`. In Gradle, project name and description are properties that can be configured separately. Changing the display name does not automatically rename all Java packages, published artifact names, URLs, or listening ports.

If there is a `Description` field, you can enter a descriptive sentence such as `Service for product catalog management`. The description helps human readers understand the project; it adds no business functionality.

## 4. Package name: namespace of the Java code

### 4.1. What is a package?

Java uses packages to organize classes, avoid name conflicts, and support access visibility among components. For example:

```java
package com.acme.catalog;

public class CatalogApplication {
}
```

The `package` declaration at the top of the file indicates that the class belongs to the `com.acme.catalog` namespace. The corresponding standard source path is:

```text
src/main/java/com/acme/catalog/CatalogApplication.java
```

Package names are typically lowercase, with segments separated by dots, and each segment must be a valid Java identifier. Do not use hyphens `-`, spaces, or Java keywords as package segment names.

### 4.2. Why does Package name not have to equal Group + Artifact?

Many initializers suggest a package name based on group and artifact. For instance, if the artifact is `catalog-service`, the tool might convert the hyphenated part into a valid Java identifier. Still, a team can intentionally choose:

```text
Group        com.acme
Artifact     catalog-service
Package name com.acme.catalog
```

This is completely valid. Changing `artifactId` does not require changing the package; conversely, refactoring packages does not automatically change published artifact coordinates. Treat them as **two separate decisions**.

### 4.3. How does the root package affect Spring Boot?

A Spring Boot application typically places the class annotated with `@SpringBootApplication` in the root package. Illustrative layout:

```text
com.acme.catalog
├── CatalogApplication
├── product
│   ├── ProductService
│   └── ProductController
└── config
    └── CatalogConfiguration
```

```java
package com.acme.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

In standard organization, `@SpringBootApplication` includes component scanning starting from this class's package and its subpackages. Therefore, components placed under `com.acme.catalog.product` can be discovered when annotated appropriately. A `@Service` in a sibling package `com.acme.shared` **does not automatically fall inside the default scan scope** of `com.acme.catalog`.

This explains why the location of the startup class matters. When you need to adjust scan scope, configure it explicitly according to the project structure; do not edit group or artifact hoping component scanning will automatically change.

### 4.4. Is the package a deployment address?

No. For example, `com.acme.catalog` is a Java package name, not the real domain of the API. An address like `https://catalog.acme.com` belongs to DNS, networking, proxy, and deployment configuration. A service can change domains while keeping the same Java package; and multiple services can share package conventions while running on different hostnames.

## 5. Distinguishing the different kinds of versions

When you see multiple numbers like `0.1.0-SNAPSHOT`, `3.3.5`, `21`, and `8.x`, identify **which product** each refers to:

| Version Type | Example | What It Describes |
| --- | --- | --- |
| Project version | `0.1.0-SNAPSHOT` | The release/build version of `catalog-service` itself |
| Spring Boot version | `3.3.5` | The version of the Spring Boot plugin, parent/BOM, and related Boot components |
| Java version | `21` | Configured target Java / compiler version |
| Maven/Gradle version | Per Maven or Gradle Wrapper | Version of the program executing the build |
| Dependency version | e.g. a library `x.y.z` | Version of a specific dependency |

These versions **do not have to match**. A project at version `0.1.0-SNAPSHOT` can use Spring Boot `3.3.5` and Java `21`. When upgrading Spring Boot, the application version only changes if the team proactively updates it. When releasing application version `1.0.0`, there is no requirement to change the Java version to `1.0.0`.

### 5.1. Project version and the SNAPSHOT suffix

A common versioning format is `MAJOR.MINOR.PATCH`, such as:

- `0.1.0`: initial experimental build assigned by the team.
- `0.2.0`: build with additional features according to team convention.
- `1.0.0`: stable build per the chosen release policy.
- `1.0.0-SNAPSHOT`: under active development, not yet treated as a fixed release.

`-SNAPSHOT` has special meaning in the Maven ecosystem: the same snapshot coordinates can refer to evolving builds in a snapshot repository. Gradle can also consume `-SNAPSHOT` coordinates when working with Maven repositories.

Rules for incrementing versions under semantic versioning are a **policy applied by the team**, not behavior verified automatically by Spring Boot. Spring Boot does not inspect your source code and bump versions for you. Building `0.1.0` also does not mean that build has been published to a repository or deployed to production.

### 5.2. Spring Boot version

The Spring Boot version determines capabilities, compatibility requirements, and the set of dependencies managed by Boot per release line. When choosing a version, consider:

- Minimum Java level and Java versions supported by that Boot line.
- Related libraries/frameworks and compatibility.
- Maintenance support status and the project's upgrade policy.
- Requirements from the team, template, or existing build system.

Do not pick a version solely because it has the largest number and assume every old dependency will still work. When upgrading from one Boot line to another, read the migration guide and run appropriate tests.

### 5.3. Java version

The Java value in project generators is usually used to configure compilation targets or toolchains. For example, selecting Java `21` means the example project is configured to target the Java 21 toolset.

This is **different** from the Java version actually used to run Maven/Gradle or the application on your machine:

```bash
java -version
```

The command above shows the Java executable currently selected in your command environment. For reliable builds, ensure an appropriate JDK is available for the build tool, toolchain, and application as required by the chosen Spring Boot version. Choosing a Java target higher than what your active JDK supports or lacking a compatible toolchain can cause the build to fail.

### 5.4. Dependency versions and BOM

A Spring Boot project typically uses dependency management from `spring-boot-starter-parent`/`spring-boot-dependencies` (Maven) or an equivalent mechanism in Gradle. A BOM (*Bill of Materials*) defines a coordinated set of library versions tested together for that Boot line.

For example, dependencies usually do not need individual versions specified:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

In a project with proper dependency management, versions are managed centrally. Not every external library is included in the BOM; for unmanaged libraries, you may need to specify an explicit version. Overriding many BOM-managed versions manually without checking compatibility can introduce conflicts.

## 6. Build tool: Maven or Gradle?

A **build tool** reads project configuration, resolves dependencies, compiles source code, runs tests, processes resources, and packages artifacts. Spring Boot works with both Maven and Gradle; picking one tool does not change the meaning of `@SpringBootApplication` or how DI works.

### 6.1. Maven

Maven uses `pom.xml` to describe project metadata, dependencies, plugins, and builds through familiar phases/lifecycles. Common commands include:

```bash
./mvnw test
./mvnw package
./mvnw spring-boot:run
```

Notable characteristics:

- XML configuration file with clear structure; many enterprise Java projects already have Maven conventions and publishing pipelines.
- Standard phases such as `compile`, `test`, `package`, and `verify` provide a shared way to execute tasks.
- Maven plugins handle tasks like compiling, testing, packaging, and repackaging an executable Boot JAR.
- Configuration can become verbose when a project needs many custom build rules.

Maven fits well when the team already uses Maven, prefers convention-heavy configuration, or is learning Java builds through Maven's lifecycle model.

### 6.2. Gradle

Gradle uses `build.gradle` (Groovy DSL) or `build.gradle.kts` (Kotlin DSL), while `settings.gradle`/`settings.gradle.kts` typically defines the project name and structure. Common commands:

```bash
./gradlew test
./gradlew bootJar
./gradlew bootRun
```

Notable characteristics:

- Supports a flexible task model, convenient when a project has custom build steps.
- Features incremental builds, caching, and multi-project configuration; actual effectiveness depends on plugins and configuration.
- Offers two DSLs to choose from; Groovy and Kotlin differ in syntax even when configuring the same functionality.
- Requires understanding tasks, plugins, and dependency configurations when customizing the build process.

Gradle fits well when the team standardizes on Gradle, has multi-module projects, or needs custom build logic. **There is no universal rule that Maven or Gradle is always faster or always better**; any specific build depends on scale, dependencies, caching, plugins, and hardware.

### 6.3. Practical comparison table

| Criterion | Maven | Gradle |
| --- | --- | --- |
| Primary build file | `pom.xml` | `build.gradle` or `build.gradle.kts` |
| Description style | XML and lifecycle/plugin model | DSL and task/plugin model |
| Common build command | `./mvnw package` | `./gradlew build` or `./gradlew bootJar` |
| Running Boot in development | `./mvnw spring-boot:run` | `./gradlew bootRun` |
| Dependency management | `<dependencies>`, parent/BOM | `dependencies { ... }`, platform/plugin |
| Custom build tasks | Via plugins and configuration | Via tasks and plugins |
| Guidance for beginners | Good when following Maven lifecycle or team templates | Good when learning task DSL or working in existing Gradle setups |

When building your first project, the best choice is usually **the tool already used by your documentation, team, or target repository**. Just master one tool first; you can always learn the other later. Do not mix `pom.xml` and `build.gradle` in the same project and expect the two files to sync dependencies automatically.

## 7. Hands-on: creating a project with Spring Initializr

<https://start.spring.io/> is a tool for generating Spring Boot project skeletons. During setup, you might choose:

| Option | Example Value | Reason |
| --- | --- | --- |
| Project | Maven | Start with `pom.xml` |
| Language | Java | Use Java as the source language |
| Spring Boot | A version compatible with the chosen Java version | Fix the Boot platform for the example |
| Group | `com.acme` | Organization identifier |
| Artifact | `catalog-service` | Artifact identifier |
| Name | `Catalog Service` | Descriptive name |
| Description | `Learning Spring Boot project metadata` | Explains the purpose |
| Package name | `com.acme.catalog` | Root package for source code |
| Packaging | Jar | Common packaging format for standalone apps |
| Java | `21` | Target Java version for the example |
| Dependencies | Spring Web (if you want to test HTTP) | Includes web starter to run an HTTP app |

The options available in the UI depend on the versions currently offered by Initializr. To inspect the two concrete configuration files in the following sections, this lesson uses **Spring Boot 3.3.5 and Java 21 as a consistent example set**.

After clicking Generate and extracting the archive, you will have a project with build files, wrapper scripts, source directories, and an application class. The generator prepares **the skeleton**; it does not write your product's business workflows.

### 7.1. Identifying the generated structure

A Maven project might look like this:

```text
catalog-service/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
├── src/
│   ├── main/
│   │   ├── java/com/acme/catalog/
│   │   │   └── CatalogServiceApplication.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/com/acme/catalog/
│           └── CatalogServiceApplicationTests.java
└── ...
```

With Gradle, `pom.xml` is typically replaced by `build.gradle` or `build.gradle.kts` and the corresponding settings file; the wrapper consists of `gradlew`, `gradlew.bat`, and the `gradle/wrapper/` directory.

The exact name of the startup class may be derived by the generator from the artifact or name; it **does not have to be** `CatalogServiceApplication`. The important rules are valid package/class declarations and proper placement of the class containing `@SpringBootApplication`.

### 7.2. Packaging: Jar or War?

For new Spring Boot applications, `Jar` is usually the appropriate choice for standalone execution via `java -jar` when the project is configured to package an executable JAR. Common web starters can provide an embedded server, allowing the web app to run independently.

`War` is typically considered when a Servlet application must be deployed into a compatible external application server due to environment requirements. Choosing WAR may require adjustments to dependencies and startup configuration. **Packaging is a decision about how the application is distributed**, not another way to name group, artifact, or package.

## 8. Viewing the same project as Maven

Here is a condensed `pom.xml` example that illustrates all major fields of a Maven project with Spring Web:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>catalog-service</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <name>Catalog Service</name>
    <description>Learning Spring Boot project metadata</description>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
            </plugin>
        </plugins>
    </build>
</project>
```

Analyzing each layer of information:

1. The `<parent>` section states that the project uses the Spring Boot starter parent version `3.3.5`. This parent provides plugin configuration and dependency management to keep project declarations concise.
2. `<groupId>`, `<artifactId>`, and `<version>` directly under `<project>` establish the identity of **the application being built**. Do not confuse them with the parent coordinates `org.springframework.boot:spring-boot-starter-parent:3.3.5`.
3. `<java.version>21</java.version>` declares the Java target per Boot parent conventions; the actual JDK must still match when building/running.
4. `spring-boot-starter-web` provides the dependency group for web applications; it has no separate `<version>` because version management is handled by the parent.
5. `spring-boot-starter-test` is declared with `test` scope because it serves test code.
6. `spring-boot-maven-plugin` supports Boot tasks such as running and packaging an executable application.

Common confusion: there are multiple `<version>` tags in the same POM. `<parent><version>...` is the parent's version, while `<project><version>...` of the child project is the version of the artifact you are building.

### 8.1. Running the Maven project

On macOS/Linux, at the project root directory:

```bash
./mvnw test
./mvnw spring-boot:run
./mvnw package
java -jar target/catalog-service-0.1.0-SNAPSHOT.jar
```

On Windows PowerShell, the corresponding wrapper commands are:

```powershell
.\mvnw.cmd test
.\mvnw.cmd spring-boot:run
.\mvnw.cmd package
java -jar target\catalog-service-0.1.0-SNAPSHOT.jar
```

`test` runs the tests configured for Maven. `spring-boot:run` runs the application in development mode. `package` produces the packaged build in `target/`; with proper Spring Boot Maven plugin configuration, the JAR is repackaged to run via `java -jar`.

If Spring Web is selected without writing any controllers yet, the application can start the HTTP server successfully while requests to `/` still receive a 404 response. **Successful startup does not mean business endpoints exist yet.**

## 9. Viewing the same project as Gradle

If you select **Gradle - Groovy** in Initializr, the equivalent metadata may appear as follows.

`settings.gradle`:

```groovy
rootProject.name = 'catalog-service'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.acme'
version = '0.1.0-SNAPSHOT'
description = 'Learning Spring Boot project metadata'

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
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Here:

- `rootProject.name` is the project name, corresponding to `catalog-service`.
- `group` and `version` serve roles similar to `groupId` and `version` in a Maven application.
- The `org.springframework.boot` plugin carries the Boot version in the Gradle configuration.
- The `io.spring.dependency-management` plugin in the example helps apply dependency management aligned with the Boot plugin. Gradle also supports using BOMs via `platform(...)`; do not combine multiple version-management approaches before understanding them.
- `java.toolchain` sets the target Java language version for toolchain-aware tasks; Gradle may require a matching JDK or toolchain provisioning mechanism.
- `implementation` and `testImplementation` separate dependencies used by application code from dependencies used by test code.
- `bootRun` and `bootJar` are tasks provided by the Spring Boot Gradle plugin.

`1.1.6` in the example is the **dependency-management plugin version**, not the project version or the Spring Boot version. In a real project, use the plugin pair and versions confirmed compatible by the generator or project team.

### 9.1. Running the Gradle project

On macOS/Linux:

```bash
./gradlew test
./gradlew bootRun
./gradlew bootJar
java -jar build/libs/catalog-service-0.1.0-SNAPSHOT.jar
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
.\gradlew.bat bootJar
java -jar build\libs\catalog-service-0.1.0-SNAPSHOT.jar
```

With the example configuration, `bootJar` creates the executable Boot JAR in `build/libs/`. `build` typically runs a broader lifecycle of tasks including appropriate verification checks; `bootJar` focuses on building the executable artifact. The path and JAR name above are typical results and can change when build configuration is customized.

### 9.2. Do Maven and Gradle build the same application?

Yes. If group, project version, package, Java, Spring Boot, and dependencies are configured equivalently, both tools can produce an application with the exact same business behavior. The main difference is **how the build is defined and executed**.

Do not create both build setups and update one while forgetting the other. When switching tools for a repository, treat it as a deliberate build migration rather than just changing file extensions.

## 10. Wrappers: why should you use them in your first project?

In an Initializr project, the Maven Wrapper or Gradle Wrapper is a set of scripts and configuration files that allow a team to invoke a fixed build tool version without relying entirely on a globally installed Maven or Gradle distribution.

| Build Tool | macOS/Linux Script | Windows Script | Common Wrapper Config |
| --- | --- | --- | --- |
| Maven | `mvnw` | `mvnw.cmd` | `.mvn/wrapper/` |
| Gradle | `gradlew` | `gradlew.bat` | `gradle/wrapper/gradle-wrapper.properties` |

For example, when running `./gradlew bootJar`, the wrapper selects the Gradle distribution defined by the project's wrapper configuration. When running `gradle bootJar`, the system typically uses whatever Gradle installation is found in the current environment. That difference can cause two machines to build with two different Gradle versions.

Wrappers improve build reproducibility, yet **they do not automatically solve every environmental factor**: JDKs, initial download network access, reachable repositories, credentials, and operating systems can still affect outcomes. In team projects, commit the required wrapper files to the repository and only use trusted download sources.

## 11. Project names at build time, runtime, and deployment

A common point of confusion is that **`artifactId` does not automatically become every name of the application across the system**. Consider this example:

| Context | Typical Value | Configuration / Meaning |
| --- | --- | --- |
| Dependency coordinates | `com.acme:catalog-service:0.1.0-SNAPSHOT` | Group, artifact, and version |
| Executable JAR file | `catalog-service-0.1.0-SNAPSHOT.jar` | Build artifact naming convention |
| Java main class | `com.acme.catalog.CatalogApplication` | Java package and class |
| Spring application name | `catalog-service` | Can be declared via `spring.application.name` |
| HTTP port | `8080`, or another port | Web server / environment configuration |
| Production hostname | `catalog.acme.com` | DNS and deployment infrastructure |
| Container image | e.g. `registry.example/catalog-service:0.1.0` | Registry/container convention, configured separately |

You can set the Spring application name in `application.yml`:

```yaml
spring:
  application:
    name: catalog-service
```

This value is runtime metadata read by Spring, not a replacement for changing `artifactId` in `pom.xml` or `build.gradle`. Although we often choose matching names for easier traceability, **each value has its own lifecycle and configuration location**.

## 12. Common mistakes when declaring project metadata

### Mistake 1: using hyphens in a Java package

```text
Group        com.acme
Artifact     catalog-service
Package name com.acme.catalog-service  <- invalid in Java
```

Fix: keep the artifact `catalog-service` and choose package `com.acme.catalog` or `com.acme.catalogservice`.

### Mistake 2: thinking the project version is the Spring Boot version

```text
Project version     0.1.0-SNAPSHOT
Spring Boot version 3.3.5
Java version        21
```

These three numbers have separate roles. Changing the application version does not upgrade Spring Boot; changing the Boot version does not alter your project release policy.

### Mistake 3: changing package in the UI while placing source code in a different package

If the class annotated with `@SpringBootApplication` is in `com.acme.catalog.app` while other components are in `com.acme.catalog.service`, default scanning from the application class may miss them. Place the startup class in an appropriate root package, such as `com.acme.catalog`, or explicitly define scan scope with a clear reason.

### Mistake 4: choosing plugins/dependencies without checking compatibility

A project can declare incompatible Java version, Spring Boot version, and Gradle/Maven plugins. In that case, build errors typically appear before any business code runs. Identify a **supported combination of tool and framework versions** rather than randomly changing a version until the build passes.

### Mistake 5: believing a starter automatically creates full features

Adding `spring-boot-starter-web` provides the standard web stack, but you still need controllers to have a useful API. Adding a data access starter does not automatically create a database or business data. The build tool pulls dependencies into the project; actual features still require configuration and source code.

### Mistake 6: changing Group/Artifact as casually as renaming a folder

In projects that publish libraries or have dependent modules, group/artifact/version are part of the **dependency contract**. Changing one of these values can require consumers to update coordinates. Renaming a local folder does not necessarily update publish metadata, and editing publish metadata does not automatically move Java packages.

### Mistake 7: using global tools while ignoring the wrapper

One developer uses a locally installed Maven/Gradle while another uses the wrapper, leading to differing tool versions. In shared projects, consistently running commands through the wrapper makes builds much easier to reproduce.

## 13. Applied exercises

### Exercise A: reading artifact coordinates

Given the declaration:

```text
Group        org.school.learning
Artifact     student-api
Version      0.2.0-SNAPSHOT
Package name org.school.student
```

Determine:

1. The artifact coordinates.
2. The typical JAR name under default rules.
3. The Java source path for the `StudentApplication` class.
4. Why `org.school.student-api` is not suitable as a package name.

**Verification hints:** coordinates are `org.school.learning:student-api:0.2.0-SNAPSHOT`; the JAR is typically named `student-api-0.2.0-SNAPSHOT.jar`; the class resides at `src/main/java/org/school/student/StudentApplication.java`; hyphens are invalid in Java package names.

### Exercise B: finding where to change configuration

You want to:

- Change the application's release version to `0.3.0-SNAPSHOT`.
- Keep the current Java package unchanged.
- Change the runtime display/logical name of the application to `student-catalog`.
- Only switch from Maven to Gradle if the team has a clear reason.

Identify which files to inspect. **Hint:** the artifact version lives in `pom.xml` or `build.gradle`; the Spring application name can live in `application.properties`/`application.yml`; the Java package lives in `package` declarations across source files. Changing build tools is a build-configuration migration, not a project version change.

### Exercise C: comparing two choices

Team 1 has a Maven repository, CI already runs `./mvnw verify`, and members are comfortable with `pom.xml`. Team 2 has multiple Gradle modules, shares convention plugins, and has standardized on `./gradlew build`. Given the exact same Spring Boot feature, which build tool should each team choose? Explain your choice based on **existing structure and workflows**, rather than vague claims that one tool is always faster or more modern.

## 14. Self-check before writing features

After this lesson, you should be able to explain:

- Why `Group` + `Artifact` + `Version` form an artifact's identity, while `Package name` defines the Java namespace.
- Why an artifact name can contain `-` while a package name cannot.
- The differences among application version, Spring Boot version, Java version, build plugin versions, and dependency versions.
- The differences between `pom.xml` and `build.gradle`/`settings.gradle`, along with corresponding build commands.
- Why wrappers matter when team members use different machines.
- Why a project that builds and runs successfully does not automatically have HTTP features, a database, or production deployment configuration.

Once these identities and build choices are clear, adding controllers, services, repositories, tests, or subsequent packaging steps becomes much easier to manage: every change goes into the right **source code layer, metadata, dependency, or runtime environment**.

# Managing Dependencies with the Spring Boot BOM or Spring Data BOM

## Objectives

After this lesson, you will be able to explain the role of a BOM (Bill of Materials), choose the right BOM for a Spring Data REST application, configure dependencies using Maven or Gradle, upgrade versions in a controlled manner, and inspect the actual versions resolved by your build tool.

## 1. Why Centralize Dependency Management?

A Spring Data REST application typically uses several tightly coupled libraries: Spring Framework, Spring Data REST, Spring Data Commons, Spring Data JPA or another store module, along with foundational libraries. Spring Data modules are developed on their own release cadence, so their version numbers do not necessarily match. For example, do not assume that Spring Data REST 5.x must be paired with Spring Data JPA 5.x.

If you assign versions to each dependency manually, a project can easily run into version mismatches, compatibility errors, or tedious multi-file edits during upgrades. A BOM solves this by providing a curated set of versions selected and tested together.

A BOM is a specialized POM that declares dependency management metadata. When you import a BOM, Maven or Gradle learns the default versions to use for the libraries included in that BOM. A BOM **does not automatically add libraries to the classpath**. You still must declare the dependencies your application actually uses; the BOM only manages their versions.

## 2. Comparing the Two BOMs

| Criterion | Spring Boot BOM | Spring Data BOM |
|---|---|---|
| Artifact | `org.springframework.boot:spring-boot-dependencies` | `org.springframework.data:spring-data-bom` |
| Scope | Curated set of versions by Spring Boot: Spring Framework, Spring Data, and many third-party libraries | Modules belonging to the Spring Data ecosystem |
| Purpose | Keep a Spring Boot application's dependencies compatible with the Boot version in use | Keep Spring Data modules compatible within the same release train |
| Typical use case | Spring Boot applications | Spring MVC / Spring Framework applications without Spring Boot, or cases requiring explicit management of the Spring Data release train |

### Spring Boot BOM

The `spring-boot-dependencies` artifact is the BOM provided by each Spring Boot release. Its version list is curated and tested for that specific Boot release. Therefore, when using Spring Boot, this is usually the primary version management source for the entire application.

Spring Boot provides a starter for Spring Data REST: `spring-boot-starter-data-rest`. This starter declares the required group of dependencies and works with Spring Boot auto-configuration. You still must declare the starter in your project; importing the BOM does not automatically add the starter.

### Spring Data BOM

The `spring-data-bom` artifact is the BOM for Spring Data. It bundles compatible versions of modules such as Spring Data Commons, Spring Data REST, Spring Data JPA, MongoDB, Redis, JDBC, and others within the same release train.

Spring Data uses CalVer for its release train, in the form `YYYY.MINOR.MICRO`. For example, `2026.0.2` is a release train version listed in official documentation at the time of writing. Individual member modules have their own version numbers; the BOM selects the right combination rather than requiring them to share the same version number.

If you are not using Spring Boot, you typically declare the Spring Data REST module `spring-data-rest-webmvc` directly and use the Spring Data BOM to manage its version alongside other Spring Data modules.

## 3. Which BOM Should You Choose?

- **Projects using Spring Boot:** prefer the Spring Boot BOM. Use the `spring-boot-starter-data-rest` starter and let the BOM manage versions.
- **Spring MVC / Spring Framework projects not using Spring Boot:** use the Spring Data BOM to align Spring Data modules, while also configuring Spring MVC and appropriate foundational dependencies.
- **Spring Boot projects needing to upgrade Spring Data separately:** first check the Spring Data version managed by Boot and the compatibility matrix. Only override the release train when you have a specific reason and have verified compatibility.
- **Projects using multiple Spring Data modules:** do not pick individual module versions manually. Use a single release train BOM as the shared management source.

A practical rule is to choose one primary source of version management. In a typical Spring Boot application, that source is the Spring Boot BOM. Only bring in the Spring Data BOM additionally when you intentionally override the release train and have verified dependency management precedence.

## 4. Configuring with Maven

### 4.1. Spring Boot with `spring-boot-starter-parent`

This is the most concise approach when a project can inherit from Spring Boot's parent POM. The parent already inherits dependency management from `spring-boot-dependencies`, so there is no need to import the BOM again.

Example of the relevant section in `pom.xml`:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>

    <!-- Add only if the application uses JPA as its persistence layer -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

You do not need to declare versions for these two starters because the Spring Boot BOM already manages them. If your application uses MongoDB, Redis, or another store, choose the corresponding starter rather than blindly adding the JPA starter.

### 4.2. Spring Boot Without Inheriting the Parent POM

A project may have to inherit from an organization's internal parent POM. In that case, you can still use the Spring Boot BOM by importing it inside `dependencyManagement`:

~~~xml
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

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
</dependencies>
~~~

Importing the BOM this way provides dependency management but does not inherit plugin management from the Spring Boot parent. If you need Maven plugin configurations, declare or manage those plugins separately.

### 4.3. Non-Spring Boot Applications: Importing the Spring Data BOM

For Spring MVC / Spring Framework applications not using Spring Boot, you can import the Spring Data BOM and declare the required modules without attaching individual versions:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>2026.0.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-rest-webmvc</artifactId>
    </dependency>

    <!-- Add only if using Spring Data JPA -->
    <dependency>
        <groupId>org.springframework.data</groupId>
        <artifactId>spring-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

The Spring Data BOM manages Spring Data module versions. It does not replace Spring MVC, Spring Framework, transaction, or database connection configuration. When integrating Spring Data REST into an existing Spring MVC application, you must configure MVC for Spring Data REST according to the corresponding documentation. With Spring Boot, this MVC configuration step is usually handled by auto-configuration.

### 4.4. Overriding the Spring Data Release Train in a Spring Boot Project

When using `spring-boot-starter-parent`, Spring Boot provides the `spring-data-bom.version` property to select a different Spring Data release train than the default:

~~~xml
<properties>
    <spring-data-bom.version>2026.0.2</spring-data-bom.version>
</properties>
~~~

Only set this property after confirming that the chosen release train is compatible with your project's Spring Boot and Spring Framework versions. Do not upgrade `spring-data-rest` or `spring-data-jpa` individually using arbitrary versions.

If you do not use the Spring Boot parent and must import both BOMs, Spring Boot instructs placing the Spring Data BOM override **before** the `spring-boot-dependencies` import in `dependencyManagement`. This order matters for dependencies managed by both BOMs. Use overrides intentionally, document the reason clearly, and inspect the effective POM after making changes.

## 5. Configuring with Gradle

### 5.1. Spring Boot with Gradle Native BOM Support

Gradle supports importing BOMs via the `platform()` function. The example below uses the Spring Boot plugin for application build tasks and declares the Boot BOM to manage dependency versions:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter-data-rest'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
~~~

Once the BOM is applied, dependencies managed by it can be declared without versions. If your project applies the `io.spring.dependency-management` plugin, the Spring Boot Gradle plugin can automatically import the `spring-boot-dependencies` BOM; in that case, you do not need to declare the same BOM again with `platform()`.

### 5.2. Non-Spring Boot Applications with the Spring Data BOM

For a Gradle project without Spring Boot, you can use the Spring Data BOM directly:

~~~groovy
dependencies {
    implementation platform('org.springframework.data:spring-data-bom:2026.0.2')

    implementation 'org.springframework.data:spring-data-rest-webmvc'
    implementation 'org.springframework.data:spring-data-jpa'
}
~~~

Add the store module matching your actual storage system. The Spring Data BOM aligns Spring Data module versions; the application still needs appropriate Spring MVC and foundational configurations.

### 5.3. `platform()` and `enforcedPlatform()`

- `platform()` brings the BOM versions into the dependency graph as constraints. This is the appropriate default choice for most projects.
- `enforcedPlatform()` forces the BOM versions as strict requirements and can override other versions in the dependency graph.

Only use `enforcedPlatform()` when your project genuinely needs to force all dependencies onto a specific version set. If misused, it can impose versions on transitive dependencies and cause conflicts with other libraries.

## 6. Inspecting Resolved Versions

Configuration in `pom.xml` or `build.gradle` is only the input specification. Inspect the dependency graph after the build tool resolves dependencies to verify the actual versions in use.

With Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw clean verify
~~~

- `help:effective-pom` shows the POM configuration after parent inheritance and dependency management imports.
- `dependency:tree` shows direct dependencies, transitive dependencies, and the selected versions.
- `clean verify` verifies the build process and configured test phases.

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath
./gradlew build
~~~

`dependencyInsight` helps trace which dependency requested a module, which version constraints apply, and why Gradle selected the final version.

When inspecting, focus on Spring Data REST, Spring Data Commons, the active store module, and Spring Framework. If you see multiple versions or an unexpected override, check the BOMs, import order, directly declared versions, and transitive dependencies.

## 7. Common Mistakes

1. **Placing the BOM in `dependencies` instead of Maven's `dependencyManagement`.** A BOM must be imported with `type` `pom` and `scope` `import` inside `dependencyManagement`.
2. **Assuming the BOM automatically adds libraries.** A BOM only manages versions; you still have to declare the starters or modules your application needs.
3. **Assigning individual versions to each Spring Data module.** Doing so can break the version combination tested by the release train.
4. **Arbitrarily combining a newer Spring Data BOM with the Spring Boot BOM.** Both managers may specify versions for the same dependencies. Use the override mechanism supported by Spring Boot documentation and inspect the effective POM/dependency graph.
5. **Confusing the starter with the Spring Data REST module.** Spring Boot applications typically use `spring-boot-starter-data-rest`; non-Boot Spring MVC integrations typically declare `spring-data-rest-webmvc`.
6. **Checking only the build file without inspecting the dependency graph.** Final resolved versions can be affected by transitive dependencies, constraints, or Gradle resolution rules.

## 8. Recommended Workflow

1. Determine whether the project uses Spring Boot or plain Spring Framework / Spring MVC.
2. Choose the Spring Boot BOM for Boot applications; choose the Spring Data BOM for non-Boot applications.
3. Declare the starters or modules actually needed, omitting versions when managed by the BOM.
4. Only override the release train when there is a clear requirement and compatibility has been verified.
5. Run `dependency:tree` or `dependencyInsight`, then run the build and tests.
6. When upgrading, update the BOM or Spring Boot version in one controlled step and re-verify the entire dependency graph.

## 9. References

- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Spring Boot — Maven Plugin: Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot — Gradle Plugin: Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html)
- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST — Dependencies and Spring Data Release Train BOM](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html)

**Version note:** `4.1.2` and `2026.0.2` in the examples are illustrative versions listed in Spring documentation at the time of writing (11/11/2026). When applying this to a real project, select a stable version compatible with your platform and re-check the documentation for the exact release you are using.

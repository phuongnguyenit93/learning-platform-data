# Managing Spring Boot, Spring Data, and Hibernate Versions with BOM

## Objectives

After this lesson, you will be able to:

- Explain how a BOM manages dependency versions and why libraries in a Spring Data JPA application must stay synchronized.
- Choose the right BOM when a project uses Spring Boot or uses Spring Data standalone.
- Configure a BOM using Maven or Gradle.
- Inspect the actual resolved versions and handle dependency conflicts methodically.

## 1. Why Must Versions Be Managed Synchronously?

A Spring Data JPA application typically involves multiple related library layers:

- Spring Boot provides auto-configuration, starters, and a curated set of dependencies tested together.
- Spring Data JPA provides repositories, abstractions, and data access following the Spring Data model.
- Spring Framework provides foundations such as dependency injection, transactions, and ORM integration.
- Hibernate is typically the JPA provider executing persistence operations.
- Jakarta Persistence provides the standard API used jointly by Spring Data JPA and Hibernate.

These components interact at both compile time and runtime. A Hibernate version that is too new or too old relative to Spring Boot and Spring Data can prevent the application from starting, fail when creating EntityManagerFactory, cause method linkage errors, or fail during query execution.

For example, a project might compile cleanly yet fail at runtime with NoSuchMethodError. This error usually indicates that one library is calling an API that does not exist in the version of the library actually loaded. The cause can be a direct dependency overriding the version managed by the BOM.

The safe rule is to choose a set of versions tested for compatibility and let a single version-management source coordinate related dependencies. When the project uses Spring Boot, that source is usually the Spring Boot BOM.

## 2. What Is a BOM?

BOM stands for Bill of Materials. In the Maven ecosystem, a BOM is a POM with packaging set to pom that contains version-management rules inside its dependencyManagement section.

A BOM lets a project declare the versions of a group of libraries in one place. When a dependency is declared without specifying a version, the build tool can pull the version managed by the BOM.

Two sections must be distinguished:

- dependencies: declares the libraries that the module actually needs to use.
- dependencyManagement: defines default versions and certain management attributes for dependencies when a module declares those libraries.

Importing a BOM does not automatically add every library in the BOM to the classpath. A BOM only provides management rules. The module must still declare the dependencies it uses.

### Related BOMs

| BOM | Management Scope | When to Use |
|---|---|---|
| Spring Boot BOM: spring-boot-dependencies | Dependencies curated by Spring Boot, including Spring Framework, Spring Data, and Hibernate for each Spring Boot release | Applications using Spring Boot |
| Spring Data BOM: spring-data-bom | Spring Data modules belonging to the same release train | Projects using Spring Data without Spring Boot, or needing to manage multiple Spring Data modules independently |
| Hibernate platform BOM: hibernate-platform | Hibernate ORM modules belonging to the same version line | Projects declaring multiple Hibernate modules directly and needing to keep them aligned |

Do not import multiple BOMs with overlapping scopes just to force individual libraries to separate versions. If the project uses Spring Boot, start with the Spring Boot BOM. Only add override rules when there is a specific reason and compatibility has been verified.

## 3. Configuring the Spring Boot BOM with Maven

There are two common approaches. Choose the one that fits your project's POM structure.

### Approach A: Inherit from spring-boot-starter-parent

If the project can use Spring Boot as its parent, declare the parent in the root POM:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
</parent>
~~~

The version 3.5.0 only illustrates the syntax. Replace it with the Spring Boot version chosen by your project that matches Java and the libraries in use.

Then declare the starter without specifying a version:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

The starter brings the necessary dependencies for Spring Data JPA into the project. The Spring Boot BOM manages the versions of the corresponding components. Normally, you do not need to declare separate versions for spring-data-jpa or hibernate-core.

The Spring Boot parent also provides default configuration and Maven plugin management. This is a convenient choice if the project is not constrained by a different parent POM.

### Approach B: Import spring-boot-dependencies

If your organization already has its own parent POM and cannot inherit from the Spring Boot parent, import the BOM inside dependencyManagement:

~~~xml
<properties>
    <spring-boot.version>3.5.0</spring-boot.version>
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

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Key points:

1. The BOM must be inside dependencyManagement.
2. type must be pom.
3. scope must be import.
4. The BOM version is placed in a property so it can be upgraded centrally.
5. Dependencies used in the module must still be placed inside dependencies.

Importing the BOM fits projects that have their own parent POM or want explicit control over dependency management. However, importing the BOM does not automatically supply all plugin configurations that the Spring Boot parent provides.

### Managing Multi-Module Maven Projects

For multi-module projects, place the BOM in the root POM so child modules share the same version set.

~~~xml
<!-- Root POM -->
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
~~~

A module needing JPA only declares the dependency:

~~~xml
<!-- Persistence module POM -->
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

This prevents modules from independently picking different versions of Spring Data or Hibernate. If a module needs to specify its own version, treat it as an intentional change and inspect the impact across the entire dependency graph.

## 4. Configuring a BOM with Gradle

Gradle supports BOMs through platform. The example below uses Gradle's native BOM mechanism:

~~~groovy
plugins {
    id 'java'
}

ext {
    springBootVersion = '3.5.0'
}

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:${springBootVersion}"))

    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
}
~~~

Replace the illustrative version with the Spring Boot version chosen by the project. Once the platform is imported, dependencies managed by the BOM can be declared without specifying separate versions.

If the project uses the io.spring.dependency-management plugin, you can import the BOM as follows:

~~~groovy
plugins {
    id 'java'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.0'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
~~~

The two examples above demonstrate two different BOM management mechanisms. Use the mechanism appropriate to your project's current setup, and avoid declaring the same BOM redundantly in multiple ways.

Gradle provides both platform and enforcedPlatform:

- platform adds constraints from the BOM into dependency resolution.
- enforcedPlatform forces versions in the BOM to apply more strongly, even when another dependency requests a different version.

Only use enforcedPlatform when the project truly needs forced version rules and has evaluated the impact on other libraries. For standard applications, platform is the better starting point.

## 5. When a Project Does Not Use Spring Boot

If a project uses Spring Data standalone, the Spring Data BOM keeps Spring Data modules on the same release train.

Example importing the Spring Data BOM with Maven:

~~~xml
<properties>
    <spring-data.release>2025.0.0</spring-data.release>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.data</groupId>
            <artifactId>spring-data-bom</artifactId>
            <version>${spring-data.release}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The version 2025.0.0 only illustrates the structure. Choose a release train compatible with your project's Spring Framework, Java, and Spring Data modules. Do not pick an arbitrary release train just because it has a newer version number.

If the project declares multiple Hibernate components directly, the Hibernate platform BOM can keep Hibernate modules on the same version:

~~~xml
<properties>
    <hibernate.version>6.6.15.Final</hibernate.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.hibernate.orm</groupId>
            <artifactId>hibernate-platform</artifactId>
            <version>${hibernate.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The Hibernate platform artifact and version must match the Hibernate line chosen by the project. Check the documentation for the exact major version before using it.

The Spring Data BOM manages Spring Data modules; the Hibernate platform BOM manages Hibernate modules. These two BOMs do not automatically guarantee that any given Spring Data version is compatible with any given Hibernate version. Without Spring Boot coordinating them, the development team must select Spring Framework, Spring Data, Hibernate, and Jakarta Persistence versions according to the compatibility matrices of those respective projects.

## 6. Should You Override BOM-Managed Versions?

By default, do not specify a version directly for a dependency already managed by the BOM. For example, if the Spring Boot BOM manages Hibernate, do not add an arbitrary version to the hibernate-core dependency.

Only consider overriding when there is a clear reason, such as:

- Needing a security patch not yet managed by the current Spring Boot version.
- Needing a fix for an identified bug in a dependency.
- Having a specific compatibility requirement from a library or deployment platform.

Safe workflow:

1. Check whether a newer Spring Boot release already updates the needed dependency. Prefer upgrading to an appropriate Spring Boot patch release.
2. Read the release notes and compatibility matrices for Spring Boot, Spring Data, and Hibernate.
3. If an override is still necessary, only use an override property supported by the BOM of the version in use or declare dependencyManagement explicitly.
4. Inspect the effective POM or dependency insight to verify the actual resolved version.
5. Run the build, repository tests, transaction tests, and persistence-related integration tests.

Some Spring Boot versions provide properties to adjust the version of a dependency managed by the BOM. Property names depend on the specific BOM. For example, you may encounter a hibernate.version property in some Spring Boot lines. Verify that the property exists in your project's BOM before overriding; do not guess property names.

A dependency declaring a direct version can alter version management results. Therefore, when you see a library not using the expected version, look for both direct dependencies and transitive dependencies requesting that version.

## 7. Notes on Java and the Jakarta Namespace

Library versions must match the Java platform and persistence namespace used by the application.

- Spring Boot 3 and higher use Jakarta EE APIs, where JPA uses the jakarta.persistence package.
- Older Spring Boot 2 applications typically use the javax.persistence package.
- Spring Boot 3 requires Java 17 or higher.

Do not mix entities or libraries compiled against javax.persistence with the Jakarta stack of Spring Boot 3+. When upgrading from Boot 2 to Boot 3, review imports, dependencies, plugins, and JPA integration libraries, not just the Hibernate version number.

## 8. Checking the Actual Resolved Versions

Do not simply look at the POM or build.gradle file and conclude that dependencies are aligned. Inspect the build tool's dependency resolution output.

### Maven

View the POM after applying parent and BOMs:

~~~bash
./mvnw help:effective-pom
~~~

View the relevant dependency tree:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework.data,org.hibernate.orm
~~~

Read the output and verify:

- spring-boot-starter-data-jpa uses the version set managed by Spring Boot.
- org.springframework.data modules belong to a compatible release train.
- org.hibernate.orm:hibernate-core has one clearly resolved version.
- No direct dependency accidentally overrides the project's desired version.

### Gradle

View all runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find out why Gradle selected the Spring Data JPA version:

~~~bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
~~~

Find out why Gradle selected the Hibernate version:

~~~bash
./gradlew dependencyInsight --dependency hibernate-core --configuration runtimeClasspath
~~~

dependencyInsight helps identify which dependency requests a version, which constraints apply, and why Gradle picked the final version.

After confirming the dependency tree, run the build and persistence tests. A clean dependency tree is a necessary condition, but it does not replace functional testing.

## 9. Common Errors

| Symptom | Common Cause | How to Handle |
|---|---|---|
| One Spring Data module has a different version from the rest | Direct version specified or multiple release trains used | Remove the individual version and manage via the same BOM |
| Hibernate has an unexpected version | Transitive dependency or another dependencyManagement overriding it | Use dependency tree or dependencyInsight to locate the requesting source |
| NoSuchMethodError or NoClassDefFoundError | Libraries are incompatible at runtime | Check resolved versions, align the BOM, and re-run integration tests |
| Application fails to create EntityManagerFactory | Incompatible Hibernate, JPA API, or persistence configuration | Inspect stack trace, Hibernate version, Jakarta API, and datasource configuration |
| jakarta.persistence import not found | Project is using an older stack or JPA dependencies were not upgraded together | Check Spring Boot version and JPA dependencies |
| javax.persistence import not found after upgrade | Source code still uses the old namespace | Migrate imports and related libraries to Jakarta when using Boot 3+ |

Some errors may come from datasource configuration, entity mapping, or transactions rather than the BOM. Use the stack trace and dependency tree to isolate the cause, and avoid changing versions by guesswork.

## 10. Recommended Version Upgrade Process

When upgrading Spring Boot, Spring Data, or Hibernate:

1. Identify the target Spring Boot version and the corresponding minimum Java version.
2. Read the release notes to understand changes in Spring Data, Hibernate, Spring Framework, and Jakarta APIs.
3. Bump the BOM in one central management location.
4. Remove individual versions that have become redundant, except intentional overrides.
5. Run dependency tree or dependencyInsight to inspect the actual resolved versions.
6. Run the build and tests, especially repository, mapping, transaction, pagination, locking, and custom query tests.
7. Document the reason if a dependency override must be kept so it can be re-evaluated on the next upgrade.

Avoid using dynamic versions such as latest.release or plus signs in Gradle for production dependencies. Dynamic versions can cause the same commit to resolve different dependencies at different times. Use explicit BOM versions and dependency locking if your project's build pipeline requires strict reproducibility.

## Pre-Merge Checklist

- [ ] The project clearly identifies the primary BOM managing dependencies.
- [ ] Spring Boot, Spring Data, and Hibernate are on compatible versions.
- [ ] Dependencies managed by the BOM do not have arbitrary versions set in child modules.
- [ ] Spring Data modules use the same release train.
- [ ] javax.persistence and jakarta.persistence are not mixed.
- [ ] The dependency tree or dependencyInsight has been inspected.
- [ ] The build and JPA-related integration tests have passed.
- [ ] Any version override has a documented reason, compatibility source, and test verification.

## Conclusion

For Spring Data JPA applications using Spring Boot, prefer the Spring Boot BOM as the shared version-management source. Declare starters without versions so Spring Boot selects Spring Data and Hibernate versions tested together. Only manage the Spring Data BOM and Hibernate platform BOM separately when the project does not use Spring Boot or has a well-defined need for independent management. Always verify the dependency tree and test persistence after every version change.

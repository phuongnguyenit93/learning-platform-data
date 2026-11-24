# Choosing Group, Artifact, Version Coordinates, and Package Name for a Spring Boot Project

## 1. Why Choose Them Properly at Initialization?

When creating a project with Spring Initializr, you typically fill in **Group**, **Artifact**, **Name**, **Description**, **Package name**, and select several versions (Spring Boot, Java). Among the four core fields covered in this lesson:

- **group** identifies the organization or project namespace in the dependency management system (Maven/Gradle).
- **artifact** identifies the specific software product within the group; it is also usually the base name of the generated JAR file.
- **version** identifies the release version of the artifact.
- **package name** is the Java namespace for classes in the source code, and also affects Spring Boot's default component scanning scope.

These four values are related, yet **not identical**. For example, an application can have the Maven coordinate `com.acme.platform:order-service:1.2.0` while its main class resides in the package `com.acme.orders`. This configuration is valid; what matters is a clear, consistent convention that avoids naming collisions.

## 2. Group: Choosing a Namespace for the Artifact

In Maven, **groupId** together with **artifactId** and **version** form the full coordinate `groupId:artifactId:version`. In Gradle, the trio `group:name:version` serves an equivalent role; `name` is the project name and can be used as the module artifact name when publishing.

The recommended convention for group is a reversed domain name owned by the organization:

| Entity | Example group | Meaning |
|---|---|---|
| Company owning `acme.com` | `com.acme` | Shared namespace |
| Internal platform | `com.acme.platform` | Grouping artifacts by domain/area |
| Organization with domain `example.org` | `org.example` | Domain-based namespace |
| Individual/learning | `io.github.username` | Can be used when aligned with publishing identity |

**Do not arbitrarily use someone else's domain name** if you plan to publish artifacts publicly. For internal projects, follow the convention managed by your organization; the group does not have to match the Java package.

The group should remain stable across releases of the same product. Changing the group alters how other projects declare the dependency, even if the application's filename or API remains unchanged.

## 3. Artifact: Naming the Module/Product Properly

Maven's **artifactId** typically uses lowercase letters and hyphens, such as `order-service`, `payment-api`, or `inventory-worker`. Name it by **function or deployment boundary**, avoiding vague names like `project1` or `backend` when an organization has multiple backends.

Examples within the same group `com.acme.shop`:

- `catalog-api`: catalog API.
- `order-service`: order processing.
- `billing-worker`: billing worker.
- `shared-contracts`: shared DTO/contract library.

In Spring Initializr, Artifact is usually suggested as the project name and influences the default value of Package name. However, **artifact and package name do not follow the same character rules**: `order-service` is a valid artifact, whereas `-` is invalid in a Java package identifier; the package should be `com.acme.shop.orders` or `com.acme.shop.orderservice`.

Maven produces a file like `order-service-1.2.0.jar` by default (depending on `finalName`, classifier, and plugin configuration). With a Spring Boot executable JAR, repackaging changes the internal JAR layout so it can run via `java -jar` without losing the meaning of the Maven coordinates.

## 4. Version: Distinguishing Application Version from Tool Versions

**Project version** is the version of **your** artifact; it is not the Spring Boot or Java version. For example:

- `1.0.0-SNAPSHOT`: a development build not yet stably released under Maven conventions.
- `1.0.0`: a release milestone build.
- `1.1.0`: a newer build adding features according to the team's versioning scheme.
- `2.0.0`: a major milestone when incompatible changes occur under Semantic Versioning conventions.

If applying **Semantic Versioning**, the common structure is `MAJOR.MINOR.PATCH`: major for incompatible changes, minor for backward-compatible functionality, and patch for backward-compatible bug fixes. Do not assume every project must use SemVer: it is a convention that the team must agree upon.

The `-SNAPSHOT` suffix is an important Maven repository convention, typically allowing snapshot builds to be updated throughout development; for release builds, a clear artifact publishing policy is needed to avoid overwriting already-released versions. Gradle can also use version strings with `-SNAPSHOT`, though update semantics depend on the repository and resolution configuration.

**Distinguishing four versions:**

| Property | Example | Role |
|---|---|---|
| Project version | `1.0.0-SNAPSHOT` | Version of `order-service` |
| Spring Boot version | `3.x.y` | Selected framework/plugin/dependency management version |
| Java version | `17` or `21` | Target Java version used by the build tool |
| Dependency version | Per BOM or explicit declaration | Version of a library used by the project |

Choose a specific Spring Boot release based on compatibility requirements, support policy, and deployment environment at project creation time; do not choose solely based on the highest number. Similarly, Java 17/21 are familiar LTS examples, but you must verify the minimum Java requirement of the **actual Spring Boot version** you are using.

## 5. Package Name: Namespace and Where to Place the Application Class

Java packages typically consist of lowercase segments separated by dots: `com.acme.shop.orders`. Each segment must be a **valid Java identifier**, cannot contain hyphens, spaces, or start with a digit; avoid Java keywords and overly generic names. Use meaningful names consistent with your organization's conventions.

In Spring Boot, the location of the class annotated with `@SpringBootApplication` is especially important. By default, this annotation includes component scanning starting from **the package containing the main class and its subpackages**. Therefore, place the main class at the root package of the Spring-managed part of the application:

```text
src/main/java/
└── com/acme/shop/orders/
    ├── OrdersApplication.java          // @SpringBootApplication
    ├── web/
    │   └── OrderController.java
    ├── service/
    │   └── OrderService.java
    └── repository/
        └── OrderRepository.java
```

With this layout, `com.acme.shop.orders.web` and `com.acme.shop.orders.service` lie under `com.acme.shop.orders` and are therefore picked up by default component scanning. A `@Service` placed in a sibling package `com.acme.shop.billing` **will not be scanned automatically** solely from having the main class in `com.acme.shop.orders`. Scan scope can be configured manually when truly needed, but placing the main class in the right place is usually simpler and easier to maintain.

The package name is also **not the runtime application display name**, does not determine `spring.application.name`, and does not have to match `groupId` or `artifactId`. For instance, `spring.application.name=order-service` can be configured separately in `application.properties`.

## 6. Example of Choosing the Four Values in Spring Initializr

Suppose a team is developing an independent order service for Acme using Maven:

| Field | Selected Value | Reason |
|---|---|---|
| Group | `com.acme.shop` | Group owned by the organization |
| Artifact | `order-service` | Clearly states the deployment responsibility |
| Version | `0.1.0-SNAPSHOT` | Initial development build; replace according to team versioning policy |
| Package name | `com.acme.shop.orders` | Valid and concise Java identifier; main class sits at the root |
| Name (optional) | `order-service` | Friendly project name |
| Java | `17` | Example for a baseline compatible with Spring Boot 3.x |

**Note:** Project `version` sometimes does not have an input box in the Initializr UI; edit it in `pom.xml` or `build.gradle` after generating the project. The Initializr UI may vary across versions.

An illustrative Maven `pom.xml` showing the module coordinates:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.shop</groupId>
    <artifactId>order-service</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <packaging>jar</packaging>
</project>
```

This is a **minimal POM snippet to illustrate coordinates**, not a standalone runnable Spring Boot project: building an actual Spring Boot application requires adding parent or dependency management configuration, dependencies, and appropriate plugins. In a Maven project generated by Initializr, keep the generated Boot configuration and edit just those three fields.

Equivalently, in Gradle Groovy DSL, `build.gradle` may contain:

```groovy
group = 'com.acme.shop'
version = '0.1.0-SNAPSHOT'
```

And `settings.gradle`:

```groovy
rootProject.name = 'order-service'
```

The Gradle snippets above only represent project identity; they must reside inside a project that declares the appropriate Spring Boot plugins and dependencies. When publishing, the artifact name can be customized via publication configuration, so check the actual published coordinates.

For Java, create `src/main/java/com/acme/shop/orders/OrdersApplication.java` in the generated Spring Boot project:

```java
package com.acme.shop.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

This class runs when the appropriate Spring Boot dependencies are present in the project. You cannot run `javac OrdersApplication.java` with a bare JDK alone because it imports classes from Spring Boot libraries.

## 7. How to Verify After Creating the Project

1. Open `pom.xml` (Maven) or `build.gradle` and `settings.gradle` (Gradle) to verify group, artifact/project name, and version.
2. Check the `package ...;` statement in `*Application.java` and its corresponding directory path under `src/main/java`.
3. Confirm that controllers/services/repositories intended to be scanned reside under the `@SpringBootApplication` class's package or have an explicit scan configuration.
4. Verify that the Java runtime/toolchain and Spring Boot version are compatible with each other and with the target runtime infrastructure.
5. In a fully generated project, run `./mvnw clean package` (macOS/Linux), `mvnw.cmd clean package` (Windows), or `./gradlew build` / `gradlew.bat build` depending on the build tool. The output filename, tests, and executable JAR generation depend on project configuration.

Maven can also inspect coordinates using `./mvnw help:evaluate -Dexpression=project.groupId -q -DforceStdout` (similarly `project.artifactId`, `project.version`) if the plugin is supported and dependencies are resolved; you do not need this command to verify the Java package.

## 8. Common Mistakes and How to Fix Them

**Using a hyphenated artifact directly as a package.** `com.acme.order-service` is invalid in Java. Keep the artifact `order-service` and use `com.acme.orders` for the package.

**Confusing project version with Boot version.** Changing `<version>` at the project level does not upgrade Spring Boot. Locate the Spring Boot version at `spring-boot-starter-parent` or in the plugin/version catalog and dependency management configuration of the build.

**Placing the main class too deep in the package hierarchy.** If the main class is in `com.acme.shop.orders.bootstrap`, default component scanning will not cover `com.acme.shop.orders.service`. Move the main class up to `com.acme.shop.orders` or explicitly configure scanning.

**Changing group/artifact after consumers already exist.** Other modules' dependencies still point to the old coordinates. When changing them, update builds, publications, registries, CI/CD, and deployment docs; consider a transition policy.

**Overly generic or duplicate artifact names within the same group.** `com.acme:service:1.0.0` is hard to distinguish when a system has multiple services. Choose functional names and check your organization's registry before publishing.

**Equating the package with the Spring application name.** Java packages use dots whereas `spring.application.name` is typically a service name like `order-service`; configure the two independently.

## 9. Decision Checklist Before Clicking Generate

- Is the group namespace owned by the organization and aligned with repository conventions?
- Does the artifact clearly identify the functionality and avoid colliding with other products in the same group?
- Does the initial version fit the development cycle and snapshot/release policy?
- Is the package a valid Java identifier, easy to extend, and placing the main class at the appropriate root?
- Have you distinguished between the artifact version, Spring Boot version, and Java version?
- Are the project name, publishing coordinates, Java package, and runtime service name **semantically consistent**, even if not identical?

**Complete example to remember:** `com.acme.shop:order-service:0.1.0-SNAPSHOT` is the Maven coordinate, while `com.acme.shop.orders` is the Java package containing `OrdersApplication`. Choose each value for its exact role, then verify the generated build before starting feature development.
# Managing Versions with the Spring Cloud BOM in Maven or Gradle

## Lesson Objectives

Spring Cloud CircuitBreaker helps applications prevent cascading failures when a dependent service is slow or unavailable. When implementing it, an application often needs components from multiple groups: Spring Boot, Spring Cloud CircuitBreaker, Resilience4j, and an HTTP or reactive communication library. If each library is assigned an independent version, the project can easily run into API conflicts, bean initialization failures, or behavioral differences between development and deployment environments.

The Spring Cloud BOM (Bill of Materials) solves version management by providing a set of aligned versions for a Spring Cloud release train. Maven and Gradle can import the BOM so that Spring Cloud dependencies use compatible versions without repeating version declarations on every dependency line.

After this lesson, you will be able to:

- Explain how a BOM manages versions and why a BOM does not automatically add libraries to an application.
- Select a Spring Cloud release train compatible with your project's Spring Boot version.
- Import the Spring Cloud BOM in Maven using `dependencyManagement`.
- Import the BOM in Gradle using the dependency management plugin or the built-in `platform` mechanism.
- Declare synchronous or reactive CircuitBreaker starters without specifying separate versions.
- Inspect the dependency tree and resolve overridden or conflicting versions.

## 1. Why Is Centralized Version Management Needed?

A Spring Boot application may use many libraries simultaneously. For example, `order-service` calls `inventory-service` and needs a circuit breaker to protect the call. The integration may include:

- Spring Boot providing the application foundation, auto-configuration, and Actuator.
- Spring Cloud CircuitBreaker providing the abstraction API to create circuit breakers.
- Resilience4j providing the implementation with `CLOSED`, `OPEN`, `HALF_OPEN` states, sliding window, timeout, or bulkhead.
- `WebClient`, `RestClient`, or another HTTP client making network calls.

Each library may release its own versions. A given version of Spring Cloud CircuitBreaker may be built to work with a specific range of Spring Framework and Spring Boot versions. If versions are mixed arbitrarily, the project may compile yet fail at runtime—for example, with missing methods, inability to create beans, or incompatibilities between configuration classes.

A manual approach is writing versions on each dependency. This quickly becomes hard to maintain: when upgrading, you must find every place using the same library, check transitive dependencies, and ensure everything remains compatible. A BOM consolidates managed versions into a single configuration point so the build tool resolves them more consistently.

## 2. What Is a BOM and How Does It Work?

A BOM is a POM file with `pom` packaging that contains dependency management declarations. When a project imports the BOM, Maven or Gradle reads the version rules inside it to choose versions for the corresponding dependencies.

A BOM has two roles that should be distinguished:

1. **Version management:** provides default versions for dependencies managed by the BOM.
2. **Adding dependencies to the application:** performed separately in the project's `dependencies` section.

Therefore, merely importing the Spring Cloud BOM does not put Spring Cloud CircuitBreaker on the classpath. The project still needs to declare the corresponding starter. Conversely, when the starter is already managed by the BOM, you normally do not need to write a version on that dependency itself.

The Spring Cloud BOM has the coordinates:

    org.springframework.cloud:spring-cloud-dependencies:<release-train-version>

The version part here is the Spring Cloud release train version. It is not the Spring Boot version and should not be chosen by copying the Boot version number. Choose the release train according to the official Spring Cloud compatibility matrix for the Spring Boot line in use.

A BOM helps synchronize components within the scope it manages. It does not replace choosing the JDK version, Maven/Gradle plugin versions, or libraries outside the BOM's scope. If a project has multiple BOMs, you must understand the build tool's precedence rules and verify the final resolved versions.

## 3. Choosing a Compatible Spring Cloud Version

Before editing the build file, identify the project's existing baseline:

- The Spring Boot version declared in the parent POM or Gradle plugin.
- The Java version the project compiles and runs on.
- Other Spring Cloud modules already in use.
- The supported Spring Cloud release train version for that Spring Boot line.

Look up the compatibility table and release guide of Spring Cloud in the official documentation. Select a release train published as compatible with your project's Spring Boot line, and then use a patch version approved by your organization within that release train. Do not deduce the Cloud version by using the same number as Boot.

Some principles when choosing:

- Keep Spring Boot and Spring Cloud within a compatible version pair.
- Do not upgrade a single Spring Cloud module to a version different from the release train just to fix one bug without verifying related dependencies.
- Prefer versions that are currently supported and tested by the project.
- Define the BOM version in a single place so upgrades and reviews are easy to track.
- When upgrading the release train, also check API changes, configuration changes, and Java requirements stated in the release notes.

Strings such as `BOOT_VERSION` and `SPRING_CLOUD_RELEASE_TRAIN_VERSION` in the examples below are placeholders. Replace them with specific versions verified for compatibility before building.

## 4. Importing the Spring Cloud BOM in Maven

With Maven, the BOM is imported in the `dependencyManagement` section. A project using the Spring Boot parent can keep its current parent and add the Spring Cloud BOM as follows:

    <properties>
        <java.version>YOUR_JAVA_VERSION</java.version>
        <spring-cloud.version>SPRING_CLOUD_RELEASE_TRAIN_VERSION</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

The elements in the declaration mean:

- `groupId` and `artifactId` identify the Spring Cloud BOM.
- `version` comes from a property so only one place needs editing when upgrading the release train.
- `type` `pom` tells Maven this is a POM.
- `scope` `import` instructs Maven to import the dependency management rules from the BOM.

Next, declare the needed starter in `dependencies`. For example, an application making synchronous service calls:

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
        </dependency>
    </dependencies>

There is no need to specify a version for the starter if its version is managed by the imported BOM. Maven will pull the corresponding managed version.

If the application uses `WebClient` and Reactor, the reactive starter can be declared instead of the synchronous starter:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>

Only add the starters that the application actually needs. An application with only synchronous calls does not need to add the reactive starter just to use a circuit breaker. If an application has both call styles, verify the resolved dependencies and how each style is configured.

If a project does not use `spring-boot-starter-parent`, it can still import the Spring Cloud BOM in `dependencyManagement`. In that case, the project team needs to decide how to manage Spring Boot dependencies, build plugins, and other BOMs. Avoid omitting the baseline BOM just because the Spring Cloud BOM was imported.

## 5. Importing the BOM in Gradle

Gradle can import a Maven BOM using the Spring dependency management plugin or the built-in `platform` mechanism. Choose one clear approach for the project so readers know where versions come from.

### Approach A: Using the io.spring.dependency-management Plugin

In a `build.gradle` file using Groovy DSL, declare the plugins and the release train version:

    plugins {
        id 'java'
        id 'org.springframework.boot' version 'BOOT_VERSION'
        id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_PLUGIN_VERSION'
    }

    ext {
        set('springCloudVersion', 'SPRING_CLOUD_RELEASE_TRAIN_VERSION')
    }

    dependencyManagement {
        imports {
            mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
        }
    }

    dependencies {
        implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    }

The dependency management plugin reads the BOM and applies managed versions to Gradle dependencies. The starter is declared in `dependencies` without specifying a version.

With Kotlin DSL in `build.gradle.kts`, the equivalent declaration is:

    plugins {
        java
        id("org.springframework.boot") version "BOOT_VERSION"
        id("io.spring.dependency-management") version "DEPENDENCY_MANAGEMENT_PLUGIN_VERSION"
    }

    extra["springCloudVersion"] = "SPRING_CLOUD_RELEASE_TRAIN_VERSION"

    dependencyManagement {
        imports {
            mavenBom(
                "org.springframework.cloud:spring-cloud-dependencies:${property("springCloudVersion")}"
            )
        }
    }

    dependencies {
        implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")
    }

Replace the placeholder strings with actual verified versions. The dependency management plugin version is also the build plugin's version, not the Spring Cloud release train version.

### Approach B: Using Gradle's Built-in platform

Gradle supports importing a BOM via `platform` without the dependency management plugin. With Groovy DSL:

    plugins {
        id 'java'
        id 'org.springframework.boot' version 'BOOT_VERSION'
    }

    ext {
        springCloudVersion = 'SPRING_CLOUD_RELEASE_TRAIN_VERSION'
    }

    dependencies {
        implementation platform(
            "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
        )

        implementation 'org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j'
    }

With Kotlin DSL:

    plugins {
        java
        id("org.springframework.boot") version "BOOT_VERSION"
    }

    val springCloudVersion = "SPRING_CLOUD_RELEASE_TRAIN_VERSION"

    dependencies {
        implementation(
            platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
        )

        implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")
    }

`platform` brings dependency constraints from the BOM into the Gradle configuration. This approach suits projects that want to use Gradle's native dependency management mechanism. If you need to force every dependency to follow the BOM constraints, Gradle provides `enforcedPlatform`, but this is a stronger option and can override version choices from other dependencies. Only use it when the project team understands its impact.

There is no need to import the same BOM with both the dependency management plugin and `platform` in the same configuration without a specific reason. Having two mechanisms manage the same group of dependencies can make configuration confusing when conflicts occur.

## 6. Managing Synchronous and Reactive Starters

Spring Cloud CircuitBreaker provides different starters depending on the programming model. With Resilience4j, the two common coordinates are:

| Call Style | Dependency | Use Case |
| --- | --- | --- |
| Synchronous | spring-cloud-starter-circuitbreaker-resilience4j | Blocking calls, such as a gateway using `RestClient` or a synchronous HTTP client. |
| Reactive | spring-cloud-starter-circuitbreaker-reactor-resilience4j | Asynchronous Reactor-based flows, such as `WebClient` returning `Mono` or `Flux`. |

The BOM provides appropriate versions for managed dependencies. The application still must choose the right starter for its communication model. Importing the BOM does not automatically turn synchronous calls into reactive ones, nor does it replace timeout, fallback, bulkhead, or sliding window configuration.

When there are multiple Maven or Gradle modules in the same repository, it is good practice to manage the release train at the shared build level if the project structure allows. Submodules sharing a single Spring Cloud version reduce the risk of each module picking a different set of dependencies. In projects with multiple independent applications, each application can have its own BOM, provided compatible versions for each application are clearly documented.

## 7. Understanding Precedence and Avoiding Version Overrides

Importing a BOM does not mean every version in the project is hard-locked. A direct dependency declaration with an explicit version usually expresses an intent to select a custom version and can override the managed version. This is sometimes necessary to address a verified issue, but doing so arbitrarily breaks the consistency provided by the BOM.

For example, the following declaration loses the benefit of centralized management for the starter:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
        <version>ANOTHER_VERSION</version>
    </dependency>

When the BOM already manages this dependency, omit the `version` tag unless there is a controlled decision to upgrade or downgrade it separately. If an override is unavoidable, document the reason, scope of impact, and plan to return to the managed version.

Common situations:

- **BOM not imported:** the dependency lacks a version and Maven reports a missing version, or Gradle cannot find the desired constraint. Check `dependencyManagement` or `platform`.
- **Incompatible release train selected:** the application may encounter Spring Boot/Spring Framework compatibility errors. Re-check the compatibility table instead of randomly trying to upgrade individual libraries.
- **Explicit version specified:** the resolved version differs from the BOM. Look for version declarations in the module or convention plugin.
- **Multiple BOMs managing the same dependency:** Maven or Gradle precedence rules may yield unexpected results. Inspect the effective POM or dependency insight.
- **Incompatible build plugin:** errors may appear before the application compiles. Distinguish between the Maven/Gradle plugin version and the runtime library versions in the application.

The Spring Cloud BOM and Spring Boot BOM have different management scopes. A project can use both via a parent or dependency management. When importing multiple BOMs, read the build tool's final output; do not assume a BOM declared later always replaces all rules of an earlier BOM in every situation.

## 8. Verifying Dependencies After Configuration

After importing the BOM and declaring the starter, check the actual versions chosen by the build tool. The goal is to confirm that the CircuitBreaker starter and related dependencies resolve properly, without a stray declaration pulling in another version.

With Maven, you can view the dependency tree:

    ./mvnw dependency:tree -Dincludes=org.springframework.cloud,io.github.resilience4j

If the project does not have Maven Wrapper, use the corresponding `mvn` command. To inspect the POM after parents and BOMs are merged, you can generate the effective POM:

    ./mvnw help:effective-pom

Find the `spring-cloud-starter-circuitbreaker-resilience4j` dependency in the output and confirm its managed version matches expectations. If multiple versions of the same transitive library exist, inspect the dependency paths leading to each version.

With Gradle, view the dependencies of `runtimeClasspath`:

    ./gradlew dependencies --configuration runtimeClasspath

You can inspect a single dependency with `dependencyInsight`:

    ./gradlew dependencyInsight --dependency spring-cloud-starter-circuitbreaker-resilience4j --configuration runtimeClasspath

The commands above are only verification steps in the development workflow. They do not replace running the application and testing the actual CircuitBreaker configuration. Once versions are correct, continue verifying that the application starts, beans are created, calls are protected, and breaker states are properly observed in a test environment.

## 9. Spring Cloud Release Train Upgrade Process

When you need to upgrade Spring Cloud, follow a reviewable sequence:

1. Record the current Spring Boot, Java, and release train versions.
2. Look up the release train compatible with the target Spring Boot version.
3. Choose an approved patch release and update the BOM property or variable in one place.
4. Check modules sharing the BOM and any dependencies with version overrides.
5. Inspect the dependency tree or dependency insight to spot transitive version changes.
6. Read the release notes for compatibility, API, or configuration changes.
7. Run the build and integration tests for calls to dependent services.
8. Test failure, slow-response, and recovery scenarios to verify the circuit breaker still works as expected.

Do not simultaneously upgrade Spring Boot, Spring Cloud, Resilience4j, and build plugins without a clear testing plan. When multiple layers change at once, pinpointing the cause of an error becomes much harder. If multiple components need upgrading, split them into changes that can be evaluated and tested separately.

## 10. Hands-on Exercise: Configuring the BOM for a CircuitBreaker Application

Suppose `order-service` uses Maven and needs to protect synchronous calls to `inventory-service`. Perform the following steps:

1. Identify the Spring Boot and Java versions the project is currently using.
2. Look up the compatible Spring Cloud release train.
3. Add the `spring-cloud.version` property and import `spring-cloud-dependencies` in `dependencyManagement`.
4. Add `spring-cloud-starter-circuitbreaker-resilience4j` to `dependencies`, without specifying a separate version.
5. Inspect the dependency tree and confirm the starter version is managed.
6. If the application uses `WebClient`, try configuring the reactive starter in an experimental branch or module and verify the dependency tree.
7. Start the application in a test environment and run integration checks before merging changes into the release branch.

For a Gradle project, repeat the exercise using either the dependency management plugin or `platform`. Clearly document which mechanism is used in the build file and do not import the BOM twice. Compare `dependencyInsight` output before and after the change to see how the BOM affects the selected versions.

The expected outcome is that the development team can upgrade the Spring Cloud version from a single configuration point, keep starters within the same release train, and explain why a dependency is using a specific version. With a stable dependency foundation, configuring Resilience4j, fallbacks, timeouts, bulkheads, reactive calls, and metrics becomes much easier to control.

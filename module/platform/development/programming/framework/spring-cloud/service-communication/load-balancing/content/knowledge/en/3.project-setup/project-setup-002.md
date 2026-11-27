# Managing Dependency Versions with the Spring Cloud BOM

A Spring Cloud application often uses several modules together: Spring Cloud LoadBalancer to select instances on the client side, a discovery provider to find instances, and optionally OpenFeign or other components to call services. These modules are released under release trains that have compatibility relationships with Spring Boot. If you manually choose versions for each dependency, the project can easily end up with Spring Cloud libraries from different generations or incompatible with the Spring Boot foundation in use.

The Spring Cloud BOM solves centralized version management. A BOM declares a managed set of versions for dependencies belonging to a release train. When you import the BOM into Maven or Gradle, the project can declare Spring Cloud starters without repeating the version on each dependency.

In the client-side load balancing module, the BOM helps keep versions consistent across Spring Cloud Commons, Spring Cloud LoadBalancer, discovery integration, and integration libraries such as OpenFeign. The BOM manages library versions; configuring discovery, instance selection, health checks, retries, or timeouts still needs to be done in their respective configuration sections.

## 1. What Is a BOM and What Problem Does It Solve?

BOM stands for *Bill of Materials*. In the Java ecosystem, a BOM is typically a Maven POM with `pom` packaging that contains dependency version management rules inside its `dependencyManagement` section.

Instead of declaring a version on each dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    <version>...</version>
</dependency>
```

the project imports a BOM at the dependency management level, then declares dependencies without specifying a version:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Maven looks up the managed version in the BOM when resolving dependencies. This approach has three main benefits:

- **Consistency:** Spring Cloud modules are selected from the same release train.
- **Easier upgrades:** you usually only need to update a single BOM version property instead of editing many dependencies.
- **Easier reviews:** reviewers can check one place to see which Spring Cloud release train the project is using.

A BOM only provides version rules. Importing a BOM does not automatically add libraries to the classpath, nor does it initialize service discovery or a load balancer. To use a feature, the project must still declare the corresponding starter.

## 2. Version Relationship Between Spring Boot and Spring Cloud

Spring Boot and Spring Cloud have separate release cycles. Spring Cloud organizes its modules into release trains; each release train is tested and published as compatible with one or more specific Spring Boot lines.

Therefore, when setting up a project, select versions in this order:

1. Identify the Spring Boot version the application uses.
2. Consult the official Spring Cloud compatibility matrix to choose an appropriate release train.
3. Obtain the version of the `org.springframework.cloud:spring-cloud-dependencies` BOM artifact belonging to that release train.
4. Import the BOM and declare the required Spring Cloud starters.

Do not take the Spring Boot version number and assign it to the Spring Cloud BOM. These two versioning systems have separate conventions. The release train name is also not the version of each individual submodule; the BOM manages the corresponding module versions.

For example, a project can store the Spring Boot and Spring Cloud versions in two separate properties:

```text
spring-boot.version  = <boot-version>
spring-cloud.version = <compatible-cloud-release-train>
```

The values in angle brackets are placeholders to be replaced with actual versions confirmed in the project's compatibility matrix. Do not copy a version pair from another project without checking the Spring Boot line and release train in use.

### 2.1. Why Should You Not Mix Multiple Release Trains?

Suppose a project imports the BOM of release train A, but manually sets the version of a Spring Cloud module from release train B. In that case, the overridden module may use different APIs or behaviors from the remaining modules.

Several errors can occur:

- `NoSuchMethodError` when one module calls a method that does not exist in the version of another module.
- `ClassNotFoundException` or bean initialization errors because classes and configurations are no longer synchronized.
- Auto-configuration failures or runtime errors that only appear when a specific integration flow is executed.
- Different behavior between local, CI, and production environments because the dependency trees are not identical.

Keeping a single unified release train reduces this risk. If you must override a module's version, there must be a clear technical reason, compatibility verification, and documentation of that decision.

## 3. Importing the Spring Cloud BOM with Maven

In Maven, the Spring Cloud BOM is imported inside the `dependencyManagement` section with `type` set to `pom` and `scope` set to `import`.

The following example illustrates the `pom.xml` structure. The version values are placeholders; replace them with versions compatible with your project:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_COMPATIBLE_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>REPLACE_WITH_SUPPORTED_JAVA_VERSION</java.version>
        <spring-cloud.version>REPLACE_WITH_COMPATIBLE_CLOUD_RELEASE_TRAIN</spring-cloud.version>
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

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>

        <!-- Only add if the application uses Eureka as its discovery provider. -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
        </dependency>

        <!-- Only add if the application declares clients using OpenFeign. -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-openfeign</artifactId>
        </dependency>
    </dependencies>
</project>
```

In the example above:

- The `spring-boot-starter-parent` parent manages many dependencies and plugins in the Spring Boot ecosystem.
- `spring-cloud-dependencies` manages dependency versions belonging to the Spring Cloud release train.
- `spring-cloud-starter-loadbalancer` brings LoadBalancer integration onto the classpath.
- The discovery starter is a separate component that must be chosen based on the system's discovery platform.
- The OpenFeign starter is only needed when the application uses Feign clients.

Using `spring-boot-starter-parent` is not mandatory. If the project uses an internal parent POM or cannot inherit from this parent, you can import the Spring Boot dependencies BOM inside `dependencyManagement` and manage plugins with custom configuration. The important thing is to keep the version management source clear for each dependency group.

### 3.1. dependencyManagement Does Not Automatically Add Dependencies

A common point of confusion in Maven is that `dependencyManagement` only manages dependency metadata, such as versions and default scopes. It does not automatically add dependencies to a module's classpath.

For example, merely importing the Spring Cloud BOM does not mean the application has Spring Cloud LoadBalancer. To use LoadBalancer, you still need to declare:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

When a dependency is declared inside `<dependencies>`, Maven looks up the matching version from the imported dependency management section.

### 3.2. When a Dependency Declares Its Own Version

If a direct dependency specifies `<version>`, that value can override the BOM-managed version for that dependency. This is useful in verified exceptional cases, but it is also a common source of version drift.

In standard configurations, omit the version from Spring Cloud dependencies managed by the BOM. If an override is unavoidable, document the reason and verify that related modules work together with the chosen version.

## 4. Importing the Spring Cloud BOM with Gradle

Gradle supports importing Maven BOMs via a platform dependency. With Groovy DSL, you can declare it as follows:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_COMPATIBLE_BOOT_VERSION'
}

ext {
    set('springCloudVersion', 'REPLACE_WITH_COMPATIBLE_CLOUD_RELEASE_TRAIN')
}

dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'

    // Choose a provider based on your actual discovery infrastructure.
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'

    // Only add when the application uses OpenFeign.
    implementation 'org.springframework.cloud:spring-cloud-starter-openfeign'
}
```

The `platform(...)` function brings version constraints from the BOM into Gradle's dependency configuration. Spring Cloud dependencies declared afterward can use the BOM-managed versions without specifying individual versions.

If the project uses Kotlin DSL (`build.gradle.kts`), the equivalent syntax is:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "REPLACE_WITH_COMPATIBLE_BOOT_VERSION"
}

extra["springCloudVersion"] = "REPLACE_WITH_COMPATIBLE_CLOUD_RELEASE_TRAIN"

dependencies {
    implementation(
        platform(
            "org.springframework.cloud:spring-cloud-dependencies:${property("springCloudVersion")}"
        )
    )

    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
```

Another option is to use the `io.spring.dependency-management` plugin and a `dependencyManagement { imports { mavenBom(...) } }` block. Choose one consistent BOM management approach in your project and follow existing build conventions.

### 4.1. platform vs. enforcedPlatform

Gradle provides two commonly referenced ways to import a platform:

- `platform(...)` introduces constraints from the BOM into dependency resolution and lets Gradle resolve conflicts according to dependency resolution rules.
- `enforcedPlatform(...)` forces versions from the platform with higher precedence, even when another dependency requests a different version.

Usually, `platform(...)` is the right choice to start with. Only use `enforcedPlatform(...)` when you understand the impact of forcing versions across the entire dependency graph, especially if the module is shared or published for other applications to consume.

## 5. Selecting Dependencies for a Client-Side Load-Balanced Application

The BOM manages versions; starters are chosen based on the capabilities the application needs. A service calling another service may need several of the following dependency groups:

| Need | Commonly Used Dependency | Role |
|---|---|---|
| Synchronous HTTP calls | `spring-boot-starter-web` | Provides the web foundation and synchronous HTTP components of Spring Boot. |
| Reactive HTTP calls | `spring-boot-starter-webflux` | Provides WebFlux and WebClient. |
| Client-side load balancing | `spring-cloud-starter-loadbalancer` | Integrates Spring Cloud LoadBalancer's ServiceInstance selection mechanism. |
| Discovery with Eureka | `spring-cloud-starter-netflix-eureka-client` | Connects the application with Eureka discovery. |
| Declarative client with OpenFeign | `spring-cloud-starter-openfeign` | Provides OpenFeign integration for Spring Cloud. |
| Calling services by logical name | LoadBalancer with an appropriate instance source | Resolves a service ID into a connectable instance. |

Dependency names should be verified against the release train and module documentation in use. Do not add all starters to every service. For instance, a service that only exposes APIs may not need OpenFeign; a service using WebClient does not necessarily need a WebFlux server if the project only needs a client and already manages dependencies according to its architecture.

### 5.1. LoadBalancer Does Not Replace a Discovery Provider

LoadBalancer needs a list of instances to choose from. That list can come from a discovery provider or a `ServiceInstanceListSupplier` configured through another mechanism.

Therefore, adding `spring-cloud-starter-loadbalancer` does not mean the application already has Eureka, Consul, or Kubernetes discovery. If the system uses Eureka, you must add and configure the Eureka client. If using another discovery platform, select the integration matching that platform.

For OpenFeign, inspect the dependency tree to ensure the load-balanced client has the required LoadBalancer components. Declaring `@FeignClient(name = "inventory-service")` only defines the client name; it does not automatically provide a registry or instance list.

### 5.2. Avoid Adding Redundant Dependencies

Before adding a starter, determine whether the application needs:

- An API server to receive requests.
- An HTTP client to call other services.
- A discovery client to look up instances.
- A LoadBalancer to select instances.
- A declarative client such as OpenFeign if you want to define interfaces.

An application may need multiple roles, but do not add starters just because they appear in another example. Unnecessary dependencies increase classpath size, the number of auto-configurations initialized, and the surface area that must be checked during upgrades.

## 6. Version Setup Process for a New Project

You can apply the following workflow when initializing a new service:

1. **Choose the foundation:** determine the Spring Boot line, Java version, and build tool the project will use.
2. **Confirm compatibility:** look up the Spring Cloud release train compatible with the selected Spring Boot version.
3. **Declare the BOM:** import `spring-cloud-dependencies` once in the shared dependency management location.
4. **Select starters:** add LoadBalancer, discovery provider, and HTTP client matching the service's actual role.
5. **Synchronize modules:** if the repository has multiple Maven or Gradle modules, place the BOM at the appropriate level so modules share the same version rules.
6. **Inspect the dependency graph:** confirm actual versions resolve properly and there are no unexpected overrides.
7. **Verify at runtime:** run the application and verify discovery, instance lists, and the ability to invoke services by service ID.

For multi-module repositories, decide where to place the BOM based on the build structure. If each module declares a different BOM on its own, the project can produce an inconsistent dependency graph. Manage the release train centrally in a parent POM or shared Gradle convention/plugin where appropriate.

## 7. Verifying Dependencies After Importing the BOM

After editing the build file, inspect the dependencies that Maven or Gradle actually resolves. Do not rely solely on looking at the configuration file, because transitive dependencies can pull in unexpected versions or modules.

### 7.1. Maven

View the Spring Cloud dependency tree:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud
```

View the effective POM to inspect the configuration after Maven merges the parent POM, properties, and BOM:

```bash
mvn help:effective-pom
```

When you need to trace the source of a version or conflict, view the dependency tree in verbose mode:

```bash
mvn dependency:tree -Dverbose
```

In the output, check whether Spring Cloud artifacts such as Commons, LoadBalancer, discovery client, and OpenFeign belong to the same version set managed by the release train. If an artifact has an unusual version, trace the direct or transitive dependency that brought that version in.

### 7.2. Gradle

List runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Query why Gradle selected a specific dependency:

```bash
./gradlew dependencyInsight \
    --dependency spring-cloud-loadbalancer \
    --configuration runtimeClasspath
```

On Windows, you can use `gradlew.bat` instead of `./gradlew`. When reading the output, pay attention to the selected version, constraints from the platform, and which dependencies request a different version.

### 7.3. Application-Level Verification

A correct dependency tree is necessary, but not sufficient to confirm service communication works. After a successful build, verify the runtime steps:

- The application starts up and HTTP client beans are created successfully.
- The discovery client connects to the provider if using a registry.
- The service ID returns a valid list of instances.
- The HTTP client is integrated with LoadBalancer.
- Requests can select an instance and receive a response.
- Logs and metrics allow distinguishing discovery errors, instance selection errors, and connection errors.

The BOM does not configure these behaviors. It only ensures dependencies are resolved from the managed version set.

## 8. Common Issues When Managing Versions

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Maven cannot resolve the BOM | Incorrect group/artifact/version, unreachable repository, or non-existent version. | Check `spring-cloud-dependencies` coordinates, repositories, and property values. |
| Spring Cloud dependencies have mismatched versions | Explicit version specified directly, multiple BOMs imported, or transitive dependency pulls in a different version. | Check the effective POM and dependency tree; remove unnecessary overrides. |
| `NoSuchMethodError` or class errors at startup | Incompatible Spring Boot/Spring Cloud modules or Cloud modules from mixed versions. | Re-select the release train from the compatibility matrix and inspect the dependency graph. |
| LoadBalancer present but no instances found | Discovery provider not configured or no instance source available. | Configure discovery integration or an instance-providing supplier. |
| OpenFeign calls service ID without load balancing | Missing LoadBalancer integration component or misconfigured client. | Check starters, dependency tree, and Feign/LoadBalancer configuration. |
| Works locally but fails in CI or production | Dependency cache, profiles, or build files differ between environments. | Compare effective POM/dependency reports and use the same lock/configuration in the pipeline. |

When upgrading, change Spring Boot and Spring Cloud versions together as a compatible pair, then re-run dependency graph checks and integration tests. Avoid updating a single Spring Cloud JAR in isolation to fix a runtime error before identifying the root cause.

## 9. Principles for Maintaining the BOM Long-Term

To keep the dependency graph stable as the project grows, follow these principles:

- Manage Spring Boot and Spring Cloud versions in a central, easy-to-find, and reviewable location.
- Each application or related module group should use a consistent Spring Cloud release train.
- Do not specify individual versions for BOM-managed Spring Cloud dependencies unless there is a verified exception.
- Only add starters corresponding to the service's actual role.
- Check the dependency tree when adding libraries, changing the BOM, or upgrading the framework.
- Document the reason whenever overriding a dependency or using `enforcedPlatform`.
- Update according to the compatibility matrix and official release notes, then run builds and integration tests.

In an enterprise environment, you can standardize the BOM in a shared parent POM or convention plugin so services do not independently pick different release trains. However, sharing configuration must account for each application's upgrade lifecycle and the possibility that they are on different Spring Boot lines.

## 10. Summary

The Spring Cloud BOM is the central version management mechanism for Spring Cloud modules. Importing `org.springframework.cloud:spring-cloud-dependencies` ensures starters such as LoadBalancer, discovery integration, and OpenFeign use versions from the same release train while reducing repetitive version declarations in build files.

When setting up a project, choose the release train from the Spring Boot compatibility matrix, import the BOM using Maven's `dependencyManagement` or Gradle's `platform(...)`, and declare only the starters the service actually needs. Finally, inspect the dependency graph and verify the discovery-to-HTTP-request flow at runtime. This practice establishes a consistent version foundation for developing and operating inter-service communication.

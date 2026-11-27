# Managing Library Versions with Spring Cloud BOM

A Spring Cloud application typically uses multiple libraries with interdependent versions: Spring Boot, Spring Cloud Commons, Spring Cloud LoadBalancer, Eureka or Consul clients, and other foundational libraries. If you manually choose versions for individual dependencies, a project can easily end up with incompatible components even when every library downloads and compiles without error.

**Spring Cloud BOM (Bill of Materials)** solves this by publishing a curated set of versions managed under a Spring Cloud release train. When you import the BOM in Maven or Gradle, the project can declare dependencies without specifying a version for each Spring Cloud starter. The BOM ensures components in the same release train work properly together; the developer is still responsible for choosing a release train compatible with the Spring Boot version in use.

## 1. Why Centralized Version Management?

An application performing service discovery may need dependencies such as:

- Spring Boot to bootstrap the application and provide the Spring foundation.
- Spring Cloud Commons to use abstractions like DiscoveryClient and ServiceRegistry.
- Spring Cloud Netflix Eureka Client or Spring Cloud Consul Discovery to connect to a registry.
- Spring Cloud LoadBalancer to select an instance when calling a service by name.
- HTTP, configuration, and observability libraries used indirectly by the components above.

Each dependency can pull in many transitive dependencies. For example, a starter may depend on Spring Cloud Commons and other Spring libraries. If versions drift, compilation errors, `NoSuchMethodError`, `ClassNotFoundException`, bean creation failures, or inconsistent runtime behavior can occur.

| Management Approach | Characteristics | Consequences |
|---|---|---|
| Specifying versions per dependency | Each starter and library has its own version | Hard to upgrade, easy for versions to drift |
| Using Spring Cloud BOM | Versions are centrally managed per release train | Spring Cloud dependencies stay synchronized, cleaner build files |
| Mixing BOM with arbitrary version overrides | Some libraries follow the BOM, others are pinned manually | Can break the set of versions tested together |

Example of manual declarations that easily introduce inconsistency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    <version>VERSION_A</version>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    <version>VERSION_B</version>
</dependency>
~~~

If the two versions belong to different release trains, they may be incompatible. A BOM lets the project pick one release train and rely on dependency management to supply matching versions for the artifacts managed by that BOM.

## 2. What Is a BOM?

A BOM is a Maven POM with `pom` packaging containing dependency management rules. In Spring Cloud, the main BOM artifact is:

~~~text
org.springframework.cloud:spring-cloud-dependencies
~~~

This artifact's version represents the Spring Cloud release train. A release train may have multiple service releases; projects usually select an appropriate, supported release according to the official compatibility matrix.

A BOM provides **dependency management**:

- Declares managed versions for multiple artifacts.
- Synchronizes Spring Cloud components belonging to the same release train.
- Manages certain related dependencies to minimize conflicts.
- Allows modules to declare dependencies without repeating versions.

A BOM does not automatically add libraries to the application. The project must still declare the needed dependencies in the `dependencies` section.

For example, importing a BOM only establishes version management rules:

~~~xml
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
~~~

Then, the actual dependency is declared separately:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
~~~

In this example, the Eureka Client version is resolved from dependency management if that artifact is managed by the BOM. If you only import the BOM without declaring the starter, the application will not automatically have Eureka Client on the classpath.

## 3. Distinguishing Spring Boot BOM and Spring Cloud BOM

Spring Boot and Spring Cloud are two projects with separate release cadences:

| BOM | Management Scope | Example Artifacts |
|---|---|---|
| Spring Boot dependency management | Spring Boot and the ecosystem of libraries Boot manages | `spring-boot-starter-web`, logging, Jackson |
| Spring Cloud dependency management | Components belonging to a Spring Cloud release train | Eureka Client, Consul Discovery, LoadBalancer, Config |
| Other library BOMs | Specific scope of that library or platform | Observability, testing, or cloud SDK suites |

A Spring Cloud project typically needs both management layers: Spring Boot provides the application foundation, and Spring Cloud adds microservice components compatible with that foundation.

Do not choose a Spring Cloud version just because the version number looks similar to the Spring Boot version. For example, a release train may be named by year while Spring Boot uses a different numbering scheme. The two versions must be paired according to the compatibility matrix published by the Spring Cloud project.

## 4. Choosing a Compatible Release Train

Before importing the BOM, identify the Spring Boot and Java versions your project uses. Then consult the Spring Cloud compatibility matrix to choose the appropriate release train.

Version selection workflow:

1. Identify the Spring Boot version managed in the root project or parent POM.
2. Identify the Java version and platform constraints of the project.
3. Consult the Spring Boot ↔ Spring Cloud release train compatibility table in the official Spring Cloud documentation.
4. Select a compatible release train and an appropriate service release within that train.
5. Lock the choice in centralized configuration so modules use the same version set.
6. Verify resolved dependencies, build, and test critical application flows.

Do not independently pick the latest Spring Cloud release train and pair it with an older Spring Boot. Similarly, do not upgrade Spring Boot while keeping a Spring Cloud train that is no longer compatible.

The example below uses placeholders for illustration. Replace `BOOT_VERSION_COMPATIBLE` and `CLOUD_TRAIN_VERSION` with concrete versions verified against your project's compatibility matrix:

| Value | Where Used | Meaning |
|---|---|---|
| `BOOT_VERSION_COMPATIBLE` | Spring Boot parent or plugin | The application's Spring Boot version |
| `CLOUD_TRAIN_VERSION` | `spring-cloud-dependencies` | A service release belonging to a compatible release train |
| Java version | Maven compiler or Gradle toolchain | JDK version meeting Boot and Cloud requirements |

Check the official documentation on every upgrade. The compatibility table changes across release trains; an old version example in an online tutorial is not guaranteed to remain suitable for a current project.

## 5. Importing Spring Cloud BOM in Maven

### 5.1. Declaring Properties and Importing the BOM

If the project uses `spring-boot-starter-parent`, you can set the Spring Cloud version in `properties` and import the BOM in `dependencyManagement`:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>BOOT_VERSION_COMPATIBLE</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>inventory-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>JAVA_VERSION</java.version>
        <spring-cloud.version>CLOUD_TRAIN_VERSION</spring-cloud.version>
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
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

In the configuration above:

- `spring-cloud.version` is the single place storing the Spring Cloud BOM version.
- `spring-cloud-dependencies` is imported with `type` set to `pom` and `scope` set to `import`.
- Eureka Client and LoadBalancer do not need explicit versions if the BOM manages them.
- `spring-boot-starter-web` is managed by the Spring Boot parent.
- Dependencies are added to the application because they are listed in `dependencies`, not because the BOM was imported.

### 5.2. Without Using Spring Boot Parent

Some projects use an internal parent POM or another parent. In that case, you can still import both the Spring Boot BOM and the Spring Cloud BOM in `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>BOOT_VERSION_COMPATIBLE</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>CLOUD_TRAIN_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This preserves the existing parent POM while keeping centralized version management. When multiple BOMs manage the same artifact, inspect the effective POM to determine the final rule. Direct management rules in the project can override versions from a BOM; import order and parent structure also affect mediation results. Do not resolve conflicts by adding arbitrary versions before understanding which dependency provides that version.

## 6. Using the BOM in Gradle

Gradle can import a Maven BOM via the dependency management plugin or Gradle's native platform mechanism. Choose one approach consistently according to your project conventions.

### 6.1. Using the Spring Dependency Management Plugin

Example with Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION_COMPATIBLE'
    id 'io.spring.dependency-management' version 'DEPENDENCY_MANAGEMENT_PLUGIN_VERSION'
}

ext {
    set('springCloudVersion', 'CLOUD_TRAIN_VERSION')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

The plugin reads the BOM and applies managed versions to matching dependencies. Once managed by the BOM, Spring Cloud dependencies do not need version declarations on individual lines.

With Kotlin DSL, the equivalent configuration can be written as follows:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "BOOT_VERSION_COMPATIBLE"
    id("io.spring.dependency-management") version "DEPENDENCY_MANAGEMENT_PLUGIN_VERSION"
}

val springCloudVersion = "CLOUD_TRAIN_VERSION"

dependencyManagement {
    imports {
        mavenBom(
            "org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"
        )
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

### 6.2. Using Gradle's Native Platform

Gradle supports importing a BOM directly via `platform()`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'BOOT_VERSION_COMPATIBLE'
}

ext {
    springCloudVersion = 'CLOUD_TRAIN_VERSION'
}

dependencies {
    implementation platform(
        "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

`platform()` brings the dependency constraints in the BOM into Gradle's dependency configuration. Dependencies managed by the BOM can be declared without individual versions.

Gradle also offers `enforcedPlatform()`. This mechanism applies versions in the platform with higher enforcement and can affect transitive dependencies of other components. Use it only when there is a clear reason and you have evaluated its impact on the entire dependency graph. For most applications, `platform()` is the better choice to start with.

If a project already uses the Spring dependency management plugin to import the BOM, do not add a duplicate platform for the same BOM. Mixing multiple version management mechanisms unintentionally makes tracing the final resolved version harder.

## 7. Managing the BOM in Multi-Module Projects

A microservice system or a multi-module repository may have multiple modules using Spring Cloud. If each module chooses its own BOM version, services may build individually yet end up using different sets of libraries.

With multi-module Maven:

- Define the `spring-cloud.version` property in the shared parent POM.
- Import the Spring Cloud BOM in the parent's `dependencyManagement`.
- Declare actual dependencies in the modules that need them.
- Child modules inherit version management from the parent and do not re-import a different BOM version.
- If a module genuinely requires a different release train, clearly isolate the management boundary and test compatibility independently.

Example parent managing the BOM:

~~~xml
<properties>
    <spring-cloud.version>CLOUD_TRAIN_VERSION</spring-cloud.version>
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
~~~

The child module only declares the dependencies it needs:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-consul-discovery</artifactId>
    </dependency>
</dependencies>
~~~

With multi-project Gradle, you can declare the platform in a root convention plugin or shared configuration for subprojects that need Spring Cloud. Avoid applying every starter to all modules if a module does not use them. Each service should carry only the dependencies required for its role.

## 8. Version Overrides and Transitive Dependencies

The BOM manages default versions for artifacts within its scope. However, a project can still specify a version directly or add another dependency management rule. In that case, the resolved version may differ from the BOM version.

A few principles:

- Do not declare explicit versions for Spring Cloud starters without a specific reason.
- Avoid overriding Spring Framework, Spring Cloud Commons, or foundational libraries individually just to work around an undiagnosed error.
- If a special patch is needed, check the release notes, dependency tree, and Spring's override guidelines.
- Document the reason for the override, its impact scope, and the condition for removing it.
- Re-verify the entire dependency graph after every BOM upgrade.

Example where declaring a version directly can alter the selected version:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    <version>ANOTHER_VERSION</version>
</dependency>
~~~

Configuration like the above bypasses the BOM-managed version for that direct dependency. Only do this after confirming the alternative version is compatible with the release train and related dependencies.

Distinguish two situations:

1. **The BOM does not manage the artifact:** the dependency needs a version declared according to that library's documentation.
2. **The BOM manages the artifact, but the version is overridden:** locate where a direct version, parent POM, another platform, or resolution rule is taking effect.

Not every transitive dependency has its version in the Spring Cloud BOM. Some libraries are managed by the Spring Boot BOM or a third-party BOM. When resolving conflicts, identify the version management source of each artifact rather than assuming every version comes from the Spring Cloud BOM.

## 9. Verifying Resolved Versions

After importing the BOM, check the actual versions selected by Maven or Gradle. Configuration that looks right is not enough to prove the dependency graph has no conflicts.

### Maven

View the dependency tree:

~~~bash
mvn dependency:tree
~~~

Filter by the Spring Cloud group:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud
~~~

View the POM after Maven applies parent, properties, and dependency management:

~~~bash
mvn help:effective-pom
~~~

You can write the effective POM output to a file for comparison during upgrades. When investigating a specific dependency, run `dependency:tree` with appropriate `includes` and inspect which dependency introduces that artifact into the graph.

### Gradle

View the dependency graph for the runtime classpath:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Check why a specific version was selected:

~~~bash
./gradlew dependencyInsight \
    --dependency spring-cloud-commons \
    --configuration runtimeClasspath
~~~

On Windows, you can use `gradlew.bat` instead of `./gradlew`.

After confirming versions, proceed to:

- Build the module to catch compilation or dependency resolution errors.
- Run a Spring context startup test to catch bean creation errors.
- Check whether the application can connect to Eureka or Consul in the test environment.
- Test service-by-name call flows if the application uses LoadBalancer.
- Check logs for warnings about versions, classpath, or incompatible configurations.

## 10. Common Errors When Using Spring Cloud BOM

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Maven reports a missing version for a dependency | BOM is not imported properly or artifact is not in the BOM | Check `dependencyManagement`, `type`, `scope`, and the artifact |
| Gradle fails to resolve a version | BOM is not imported into the appropriate configuration | Check the plugin or `platform()` |
| `NoSuchMethodError` at runtime | Related libraries have mismatched versions | Inspect the dependency tree and release train |
| Application fails to initialize beans | Spring Boot and Spring Cloud are incompatible or a starter is missing | Cross-check the compatibility matrix and inspect the classpath |
| One module uses a different version from the rest | BOM is declared inconsistently or overridden | Consolidate version into shared configuration and audit modules |
| Actual version differs from expected | Parent, another BOM, direct dependency, or resolution rule overrides it | Inspect effective POM or dependencyInsight |
| Upgrading the BOM causes configuration errors | New release train has API changes or removals | Read release notes and upgrade step by step |

A dependency error should not be fixed by adding random versions until the build passes. Identify which library is resolved, what manages that version, and why the selected version is incompatible.

## 11. Workflow for Upgrading Spring Cloud BOM

Upgrading the BOM can bring changes across multiple components at once. Perform it in a controlled manner:

1. Record the current Spring Boot version, Spring Cloud train, and Java version.
2. Look up the release train compatible with the target Spring Boot version.
3. Read the release notes for Spring Cloud and the components your service uses.
4. Change the property or platform version at a single centralized management point.
5. Re-resolve the dependency graph and verify key versions.
6. Run the build, unit tests, integration tests, and application startup checks.
7. Test registration, discovery, and service calls if the service uses those features.
8. Monitor logs and metrics after deployment; retain the previous version for rollback per your organization's release process.

If upgrading both Spring Boot and Spring Cloud, select a compatible version pair and upgrade in a controlled manner. When errors occur, compare the dependency graph before and after the upgrade to isolate the root cause.

## 12. Key Takeaways

- Spring Cloud BOM manages versions for dependencies belonging to a Spring Cloud release train.
- Importing a BOM only provides dependency management rules; it does not automatically add starters to the application.
- Spring Boot BOM and Spring Cloud BOM have different management scopes and are typically used together.
- Choose the Spring Cloud train based on the compatibility matrix with your project's Spring Boot and Java versions.
- Maven imports the BOM via `dependencyManagement` with `type=pom` and `scope=import`; Gradle can use the dependency management plugin or `platform()`.
- Managing the BOM in a single shared place keeps modules on the same version set.
- After changing the BOM, verify the dependency tree, build, tests, and service discovery flows before deploying.

When managing versions with Spring Cloud BOM, the project gets a consistent dependency foundation for developing DiscoveryClient, ServiceRegistry, Eureka, Consul, and LoadBalancer. Selecting the right release train and verifying resolved versions are two essential steps to prevent conflicts when operating microservices.

# Managing Dependencies with the spring-cloud-dependencies BOM

In a Spring Boot system using multiple Spring Cloud components, an important question arises before writing code: **which versions should be chosen so that Spring Cloud Commons, Context, Config, LoadBalancer, and other integrations work together and stay compatible with Spring Boot?** If each library is declared with its own independent version, the application may compile successfully yet fail at startup or when calling APIs because libraries rely on differing contracts.

Spring Cloud solves most version-management problems through **release trains** and a **BOM (Bill of Materials)** with coordinates **org.springframework.cloud:spring-cloud-dependencies**. This lesson belongs to the **Versions and Dependencies** chapter of the **SPRING_CLOUD_CORE** module. It explains BOM principles, how to declare it in Maven and Gradle, how to coordinate with the Spring Boot BOM, how to inspect the dependency graph, and a safe upgrade workflow.

## 1. Learning Objectives

After this lesson, you can:

- Explain how **release train**, **BOM**, **dependency management**, and **starter** are distinct concepts.
- Choose a Spring Cloud release train based on the Spring Boot version, rather than manually assembling version numbers for individual projects.
- Import the Spring Cloud BOM in Maven or Gradle and declare starters without copying separate versions.
- Analyze the versions actually resolved, including transitive dependencies and overrides.
- Recognize failures caused by missing BOMs, version mismatches, duplicate dependencies, or conflicts between management rules.
- Apply a testing process when upgrading Commons/Context abstractions, discovery, service registry, inter-service clients, and externalized configuration.

## 2. What Is a BOM and What Does It Not Do?

A **BOM** is a POM containing a list of managed artifacts alongside compatible versions. It is a **version-selection rulebook** for the dependencies a project uses; it is not a library with business functionality.

For instance, an application needs Spring Cloud Config Client and Spring Cloud LoadBalancer. If the project already imports the appropriate Spring Cloud BOM, both starters can be declared without writing separate version numbers. The build tool uses the rules in the BOM to determine the versions published by that release train.

| Concept | Role | Does it automatically add runtime code to the app? |
| --- | --- | --- |
| **Spring Cloud release train**, e.g., 2025.1.x | Groups Spring Cloud project versions released and managed together | No |
| **spring-cloud-dependencies BOM** | Manages dependency versions in the corresponding release train | No |
| **spring-boot-dependencies BOM** | Manages Spring Boot library versions and many related dependencies | No |
| **Starter**, e.g., spring-cloud-starter-loadbalancer | Adds the libraries and auto-configuration needed for a feature | Yes, when declared in dependencies |
| **Spring Boot Maven parent / Gradle plugin** | Provides build settings and integration for a Spring Boot application | Does not replace the Cloud BOM |

Crucially: **importing the BOM does not automatically enable service discovery, service registry, refresh scope, or HTTP communication**. Those capabilities only appear after you add the proper dependencies, configure integrations, and run the application.

Spring Cloud consists of projects with independent release cadences and version numbers. For example, release train version **2025.1.2** does not mean every Spring Cloud JAR must carry the number **2025.1.2**. The BOM defines the corresponding version set for each project. Therefore, avoid inferring the version of **spring-cloud-commons**, **spring-cloud-context**, or **spring-cloud-config** from the release train name.

~~~mermaid
flowchart TD
    BOOT[Spring Boot version] --> BOOTBOM[spring-boot-dependencies BOM]
    BOOT --> CHOOSE[Select compatible release train]
    CHOOSE --> CLOUDBOM[spring-cloud-dependencies BOM]
    BOOTBOM --> RESOLVE[Resolve dependency graph]
    CLOUDBOM --> RESOLVE
    STARTERS[Starters actually declared] --> RESOLVE
    RESOLVE --> RUNTIME[Application classpath]
~~~

The diagram shows that the **BOM manages versions**, while **dependencies determine which libraries appear** on the classpath. The two steps cannot substitute for each other.

## 3. Selecting the Right Release Train for Spring Boot

Before adding the Cloud BOM, determine the project's actual Spring Boot version. Spring Cloud publishes the **compatibility matrix between release trains and Spring Boot generations** on its official project page. You cannot assume the release train with the newest year is always compatible with every Boot line.

Examples based on published Spring Cloud information:

| Spring Cloud release train | Compatible Spring Boot generation | Notes |
| --- | --- | --- |
| **2025.1.x (Oakwood)** | **4.0.x**; **4.1.x from Spring Cloud 2025.1.2** | For example, Spring Cloud 2025.1.2 was announced compatible with Spring Boot 4.1.0 |
| **2025.0.x (Northfields)** | **3.5.x** | Historical line; check support status before using for new projects |
| **2024.0.x (Moorgate)** | **3.4.x** | Historical line; not supported by default |

Lines marked end-of-life on the Spring Cloud page should not be treated as default recommendations for new projects. The table here helps illustrate how to read version relationships; it **does not replace the live compatibility matrix and support notices at deployment time**.

Selection workflow:

1. Check the Spring Boot version in the application's parent POM, BOM, or Gradle plugin.
2. Consult **Release Train Spring Boot Compatibility** at https://spring.io/projects/spring-cloud/.
3. Choose the matching release train and a stable **service release** of that train.
4. Read the release notes for Boot patch prerequisites, API changes, or renamed starters.
5. Use **a specific BOM version** that is reproducible across builds; isolate upgrades in dedicated pull requests.

In subsequent examples, **Spring Boot 4.1.0** and **Spring Cloud 2025.1.2** are used because this pair was announced as compatible when Spring Cloud 2025.1.2 was released. This is a **verified illustrative version pair**, not a claim that these are the newest versions at all times.

## 4. Maven: Using the Spring Boot Parent and Importing the Spring Cloud BOM

This is the common path for Spring Boot applications using Maven. The Spring Boot parent supplies build configuration and dependency management for Spring Boot. We additionally import **spring-cloud-dependencies** inside **dependencyManagement** to manage Spring Cloud modules.

Minimal POM example for learning purposes:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cloud-bom-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2025.1.2</spring-cloud.version>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Explanation of the key lines:

- **groupId + artifactId** pinpoint the Spring Cloud BOM.
- **version** picks the service release of the release train. The **spring-cloud.version** property lets you change the version in one place.
- **type=pom** indicates the imported artifact is a POM.
- **scope=import** is only valid for POM-type dependencies inside **dependencyManagement**. Maven merges version-management rules from the BOM into effective dependency management.
- Starters in **dependencies** omit version declarations because versions are managed by their respective BOMs.

Do not add **spring-cloud-dependencies** as a runtime application dependency. Nor does it replace **spring-boot-starter-parent**; the Cloud BOM only manages dependencies and does not provide plugin configuration in place of the Boot parent.

### 4.1. When a Project Uses a Different Parent

Many organizations use an internal parent POM and cannot directly inherit from **spring-boot-starter-parent**. In that case, import both **spring-boot-dependencies** and **spring-cloud-dependencies** inside **dependencyManagement**:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>4.1.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>2025.1.2</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The snippet above is a section placed into a POM with its own parent, not a complete POM. Importing **spring-boot-dependencies** does not automatically configure compiler, packaging, test plugins, or other defaults normally supplied by the Boot parent. Manage build plugins separately as needed.

### 4.2. Multi-Module Maven

If application modules inherit from the same internal parent, place both BOM rules in that parent so child modules share a single version policy. Each module declares only the starters it needs. A module that does not inherit that parent's dependency management must import the BOMs appropriately; simply sitting in the same Maven reactor **does not guarantee** identical effective dependency management.

For reusable libraries consumed by multiple applications, carefully consider whether to impose dependency management on consumers. A BOM controls an application's versions only when applied in the consuming project; do not assume every consumer will inherit a library's internal parent.

## 5. Gradle: Two Common Ways to Use BOMs

Gradle can use Spring's dependency management plugin or Gradle's **native platform** support. The two approaches differ in how BOMs are imported and how version selection rules apply. Clarify which approach your team uses so multiple places do not manage the same artifact with unclear precedence.

### 5.1. Groovy DSL with io.spring.dependency-management

Example **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

ext {
    springCloudVersion = '2025.1.2'
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

When **org.springframework.boot** and **io.spring.dependency-management** are applied together, the Spring Boot Gradle plugin automatically imports **spring-boot-dependencies** matching the Boot plugin version. We import the Cloud BOM using **mavenBom**. This is the approach illustrated on the Spring Cloud project page.

### 5.2. Kotlin DSL with Gradle Native Platform

If not using the **io.spring.dependency-management** plugin, declare both the Boot BOM and Cloud BOM as **platform dependencies**. Example **build.gradle.kts**:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.0"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

repositories {
    mavenCentral()
}

val springBootVersion = "4.1.0"
val springCloudVersion = "2025.1.2"

dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:${springBootVersion}"))
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"))

    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

With Gradle native platforms, managed versions become **dependency constraints**. With **platform(...)**, they usually act as preferred versions; Gradle can still pick another version during conflict resolution. Therefore, **never infer the final outcome solely from build script code**: verify with **dependencyInsight**.

Gradle also offers **enforcedPlatform(...)** to enforce versions more strictly, though it should not be used out of habit. Strict constraints can conflict with other dependencies and leak to consumers if publishing a library. Use it only when genuinely needed and after checking its impact.

**Note on configurations:** the example uses **implementation**. For custom configurations (e.g., a specialized source set), verify whether that configuration inherits platform constraints. In multi-module Gradle projects, BOMs are commonly applied via a convention plugin or shared configuration so related modules follow a unified policy.

## 6. Choosing Starters According to Functional Needs

After importing the BOM, the next step is adding the **exact dependencies** for the features needed. For example:

~~~xml
<dependencies>
    <!-- Discovery/LoadBalancer for calls by service ID -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Add only if the app fetches config from Config Server -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
</dependencies>
~~~

Each starter pulls in required transitive dependencies, which may include **Spring Cloud Commons** and **Spring Cloud Context**. If the application directly uses APIs from those modules, inspect the dependency tree and consider declaring direct dependencies per project conventions.

Scenarios within **SPRING_CLOUD_CORE**:

| Problem | Relevant Spring Cloud part | Role of the BOM |
| --- | --- | --- |
| Querying **DiscoveryClient**, **ServiceInstance** | Spring Cloud Commons and chosen discovery integration | Manages Commons module versions alongside the discovery adapter |
| Using **ServiceRegistry** | Commons and specific registry adapter (if supported) | Keeps Cloud modules within the same coordinated version set |
| Client calls by **service ID** | Spring Cloud LoadBalancer | Manages starter dependencies and related modules |
| Reading external config via Config Server | Spring Cloud Config Client and Context | Keeps Config Client aligned with the selected Spring Cloud set |
| Using **@RefreshScope** and refresh events | Spring Cloud Context | Manages Context compatibly with the Boot/Cloud environment |
| Coordinating service calls and fault tolerance | Communication starter and appropriate resilience integration | Supplies version management; **does not configure** timeouts, retries, or circuit breakers automatically |

Importing the BOM and adding starters **does not spin up a registry server**, auto-register instances into specific infrastructure, or open management endpoints by itself. Those parts still require the appropriate dependencies, configuration, and permissions.

## 7. How Do Maven and Gradle Actually Select Versions?

A common point of confusion is that the BOM **manages** versions, while the build tool still has to **resolve** a dependency graph that may contain transitive dependencies, explicitly written versions, and other BOMs.

### 7.1. Maven Example

Suppose the Cloud BOM manages a Cloud module at version **A**, a starter omits a version, and another transitive dependency requests version **B**. **dependencyManagement** rules can govern the version selected for the managed module. However:

- A dependency with a **directly specified version** in the project's POM can override the BOM default.
- Dependency management rules declared directly in the current POM can take precedence over rules inherited from a parent.
- When multiple BOMs manage the same coordinates, **declaration order and placement can affect effective dependency management**.
- Maven also applies dependency mediation rules for dependencies not covered by management rules.

Hence, never rely on "we already imported the BOM so everything must be right." Verify the **effective POM** and **dependency tree** of the module actually running.

### 7.2. Gradle Example

Gradle native platforms turn managed versions into constraints; conflicts can lead to selecting a version other than the BOM's preferred one. Spring's dependency management plugin has its own BOM-import mechanism. These two management styles **are not completely equivalent**; when switching tools or updating plugins, compare the resolved graph before and after.

The common truth across both build systems: **a BOM does not protect against an uncontrolled upgrade if you force versions, import conflicting BOMs, or allow multiple dependency paths to pull incompatible APIs**.

## 8. Inspecting the Dependency Graph

The following commands are **examples to run in the learner's sample project**, not mandatory actions for this document. When using Maven Wrapper or Gradle Wrapper, prefer the version-committed wrapper in the repository.

### 8.1. Maven

~~~bash
# View effective POM and inherited/imported dependencyManagement
mvn help:effective-pom

# View the full dependency tree
mvn dependency:tree

# Filter Spring Cloud dependencies
mvn dependency:tree -Dincludes=org.springframework.cloud

# Inspect a dependency group when suspecting conflicts
mvn dependency:tree -Dincludes=org.springframework:spring-core
~~~

In the output, cross-check **spring-cloud-commons**, **spring-cloud-context**, **spring-cloud-config-client**, or the failing module against the chosen release train. Also inspect Boot/Framework modules; a graph whose Cloud names look right does not guarantee compatibility with Spring Boot.

### 8.2. Gradle

~~~bash
# View resolved dependency graph at runtime
./gradlew dependencies --configuration runtimeClasspath

# Explain why a module's version was selected
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath

# Inspect selection for a dependency with multiple version requests
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

On Windows, substitute **gradlew.bat** for **./gradlew** if needed. The **dependencyInsight** command is especially helpful for seeing which dependency requested another version and which constraints influenced the result.

Do not look only at versions in **pom.xml** or **build.gradle**. What needs verification is the **final version on the compile/runtime classpath of the deployed module**.

## 9. Common Errors and How to Handle Them

| Symptom | Common cause | Check and fix |
| --- | --- | --- |
| Maven reports a dependency is missing a version | Starter unmanaged due to missing BOM, misplaced import, or wrong coordinates | Ensure BOM is inside **dependencyManagement** with **type=pom** and **scope=import** |
| **Non-resolvable import POM** | BOM version does not exist or repository/proxy cannot download it | Check BOM coordinates, repositories, and network; do not swap to a random version |
| App reports Spring Boot incompatible with Spring Cloud | Wrong release train or Boot patch outside Cloud's supported range | Consult the official matrix, upgrade Cloud train/service release, or adjust Boot to match |
| **NoSuchMethodError**, **ClassNotFoundException**, **NoClassDefFoundError** | Possibly JAR conflict, forced version, or changed API; other causes also possible | Inspect dependency tree/insight, stack trace, and release notes; remove conflicting overrides |
| Two internal modules use different Commons/Context versions | Modules don't inherit the same BOM/convention, or an override exists | Compare effective POM / resolved runtimeClasspath of **each module** |
| BOM imported but no **DiscoveryClient** or load-balanced client bean | BOM doesn't add starters/adapters, or feature not configured | Verify dependencies and feature config; BOM only manages versions |
| Config Client runs but doesn't read config as expected | Missing import config, empty server data, or initialization change across versions | Inspect Config Data, startup logs, profile/label, and train-specific docs |
| Build passes yet failure occurs only at runtime | Binary compatibility / auto-configuration not exercised at runtime | Add integration and smoke tests; don't treat dependency resolution as sufficient |

### 9.1. Spring Cloud Compatibility Verifier

Spring Cloud Commons includes a **Compatibility Verifier** to catch certain incompatible Spring Boot–Spring Cloud pairings when the app runs, potentially reporting **APPLICATION FAILED TO START** alongside compatible Boot versions. This is a safeguard, **not a guarantee that every dependency and API is compatible**.

When hitting this error, the preferred fix is **re-selecting a Boot/Cloud pair that matches the matrix**. Documentation mentions **spring.cloud.compatibility-verifier.enabled** to control the check in supported versions; do not disable verification merely to mask a version mismatch. Always check the default configuration of the documentation branch you are using as well.

### 9.2. Why Not Force a Single JAR's Version?

Suppose a project uses a Cloud BOM tested across a cohesive group of modules, yet you manually pin a newer version for **spring-cloud-commons** in direct dependencies. Meanwhile, **spring-cloud-context** and registry adapters may still call APIs expecting the older version. The failure only surfaces when Spring instantiates beans or invokes a method.

When needing to fix a specific CVE or bug:

1. Look for a patch within the **same release train** or a recommended upgrade train.
2. Evaluate release notes and functional changes impacting the application.
3. If overriding a library is unavoidable, document the reason, scope, affected versions, and runtime tests.
4. Remove the override once an official BOM manages the corresponding fix.

Forcing a version may be technically valid, yet it creates extra maintenance responsibility.

## 10. Safe BOM Upgrade Workflow

Upgrading a release train can impact areas outside the feature you are modifying: Commons APIs, Context lifecycle, Config Client, registry adapters, LoadBalancer, auto-configuration rules, and transitive dependencies.

~~~mermaid
flowchart TD
    A[Identify Boot in use] --> B[Look up matching release train]
    B --> C[Pick a specific service release]
    C --> D[Update BOM centrally]
    D --> E[Diff resolved dependency graph]
    E --> F[Run compile and tests]
    F --> G[Test startup, discovery, and config]
    G --> H[Canary or monitored rollout]
    H --> I[Finalize version and rollback plan]
~~~

### 10.1. Tests You Should Have

| Test group | Scenario | Why it is needed |
| --- | --- | --- |
| **Build** | Resolve dependencies, compile, run existing tests | Catches artifact, version, and API errors at compile time |
| **Startup** | Run app with simulated production profile | Catches auto-configuration, bean creation, and Compatibility Verifier failures |
| **Commons / discovery** | Query instances by service ID; registry unavailable | Confirms adapters and abstractions still work together |
| **LoadBalancer / communication** | Call a service, instance disappears, timeout, or error response | Confirms call path and error policy didn't silently change |
| **Config Client** | Startup when Config Server is healthy and when unreachable | Checks fail-fast/optional behavior and active config sources |
| **Context / refresh** | Update config, trigger refresh in a safe environment | Verifies beans refresh cleanly without losing consistency |
| **Operations** | Health, metrics, log correlation, rollback | Detects unexpected post-deployment changes |

For libraries exposing **public APIs**, test consumers as well. For multi-service applications, upgrade in cohesive groups with clear interactions, monitoring HTTP errors, latency, registry connectivity, and config sources. Never push an entire cluster onto a new release train just because one module's build turned green.

### 10.2. Measuring Before-and-After Differences

A useful upgrade record should include:

- **Old/new version pairs:** Spring Boot, Spring Cloud release train, Java, and build tools.
- **Resolved graph:** Commons, Context, Config, LoadBalancer artifacts, and key integration modules.
- **Remaining overrides:** reasons to keep or remove them.
- **Test results:** startup, discovery, communication, config, refresh, and failure scenarios.
- **Operational signals:** error rate, P95/P99, retry counts, registry connection errors, and startup duration.

If rollback is required, restore **the entire tested version set**, rather than downgrading a single starter while keeping other Cloud modules on newer versions.

## 11. Self-Practice Exercise

You have an **order-service** Spring Boot application and want to add **Spring Cloud LoadBalancer** to call **inventory-service** by service ID. Later, the team wants to use **Config Client** to pull externalized configuration.

Perform the following in a sandbox project:

1. From your chosen Spring Boot version, check the compatibility matrix and record the **release train + service release**.
2. Import **spring-cloud-dependencies** in Maven or Gradle without putting versions directly on Cloud starters.
3. Add only **spring-cloud-starter-loadbalancer**; inspect the dependency tree and identify Commons/Context if present on the classpath.
4. Add **spring-cloud-starter-config**; compare the dependency graph before and after.
5. Try an incompatible Spring Cloud train on a test branch; record any resolution/startup errors, then restore the matching version set.
6. Write a short checklist covering startup when Config Server is unreachable, calling inventory when instances disappear, and verifying refresh scope when configuration changes.

**Completion criteria:** ability to explain why a starter resolves to a specific version from the BOM, prove it with the dependency graph, and state runtime risks that compilation checks alone cannot catch.

## 12. Summary

**spring-cloud-dependencies** is the standard mechanism for managing a Spring Cloud dependency set by release train. It reduces per-JAR version pinning and prevents Commons, Context, Config, discovery, registry, or LoadBalancer combinations that were not designed to work together. However, the BOM **does not add functionality by itself** and **does not guarantee** full runtime compatibility when overrides or misconfigurations exist.

When adding Spring Cloud to Spring Boot, always start from the compatibility matrix, import the right train's BOM, declare only needed starters, inspect the resolved dependency graph, and test distributed behaviors as well. Version management is part of a system's **testability and operability**, not just an XML snippet or Gradle script.

## References

- [Spring Cloud — Release Trains, Compatibility, and Getting Started](https://spring.io/projects/spring-cloud/): Boot/Cloud matrix, Maven and Gradle BOM import examples.
- [Spring Cloud 2025.1.2 release announcement](https://spring.io/blog/2026/06/11/spring-cloud-2025-1-2-aka-oakwood-has-been-released/): confirms Spring Boot 4.1.0 support in the illustrative train release.
- [Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): dependencyManagement, import scope, transitive dependencies, and dependency mediation.
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): using io.spring.dependency-management or native BOMs.
- [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html): platform, dependency constraints, enforcedPlatform, and how to inspect results.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): DiscoveryClient, ServiceRegistry, and Compatibility Verifier.

**Note:** version examples in this lesson are for learning purposes. When setting up a real project, verify the official documentation at deployment time, the release train's support status, and applicable security patches.

# Azure BOM and Spring Boot Compatibility Matrix

A Spring Boot project integrating with Azure often depends simultaneously on Spring Boot, Spring Framework, Spring Cloud Azure, and multiple Azure SDK for Java libraries. If each dependency is declared with its own version, the application may still compile yet fail when initializing the Spring context or calling cloud services. A **Bill of Materials (BOM)** helps manage a set of versions released together; the **compatibility matrix** helps you pick the right BOM *line* for your Spring Boot version, Java version, and other Spring components.

This lesson belongs to the **Azure Platform** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. In the context of practicing Spring Boot with managed services across AWS, Azure, and Google Cloud, version management is a foundational step before implementing authentication and authorization, storage, messaging, data, secret protection, integration testing, and cross-provider comparison.

## 1. Objectives

After this lesson, learners can:

1. Distinguish **Spring Boot BOM**, **Spring Cloud BOM**, **Spring Cloud Azure BOM**, and **Azure SDK BOM**.
2. Read the compatibility matrix to select a valid combination of Spring Boot, Spring Cloud Azure, and Java.
3. Configure Maven or Gradle so that starters and Azure SDK libraries are version-managed consistently.
4. Analyze the dependency tree / effective dependency management and resolve dependency conflicts.
5. Establish a verified upgrade workflow, distinguishing library compatibility issues from Azure identity/RBAC or network errors.

## 2. What Is a BOM and What Problem Does It Solve?

A **BOM (Bill of Materials)** is a POM-type artifact that publishes a curated set of dependency versions. When an application imports a BOM, the build tool can infer versions for dependencies included in the managed list.

For example, instead of setting separate versions for **azure-core**, **azure-identity**, **azure-storage-blob**, and related libraries, a project can use an appropriate BOM and declare dependencies without specifying versions.

A BOM helps:

- Reduce duplicate version declarations.
- Keep the SDK set aligned to versions tested together by the publisher.
- Simplify upgrades through a central control point.
- Improve build reproducibility across development, CI, and production environments.

However, a BOM has **limitations**:

- **It does not automatically add dependencies** to the project. Only artifacts declared directly or pulled in transitively appear in the build.
- **It does not guarantee that every combination works at runtime.** You still need to check the compatibility matrix, Java version, API changes, runtime behavior, and actual tests.
- **It does not configure identity, RBAC permissions, endpoints, or Azure resources.**
- **It does not update build plugins** such as the Spring Boot Gradle plugin, Maven Compiler, or Surefire without appropriate separate configuration.
- **It does not automatically fix security vulnerabilities.** You must monitor advisories and update the BOM to a supported patch version.

### Dependency Management vs. Dependency Declaration

~~~mermaid
flowchart TD
    A[Spring Boot application] -->|declares| B[Spring Cloud Azure starter Blob]
    A -->|imports BOM| C[Spring Cloud Azure dependencies BOM]
    C -.->|manages version| B
    B -->|transitive dependency| D[Azure Storage Blob SDK]
    D --> E[Azure Core / Identity]
    C -.->|manages compatible version set| D
    C -.->|manages compatible version set| E
~~~

Dashed arrows show that the BOM **selects versions**, while solid arrows represent **dependencies brought into the application**. Importing a BOM does not mean adding all Azure starters.

## 3. Four Commonly Confused Version Management Layers

| Layer | Common Artifact / Component | Primary Responsibility | When Needed |
| --- | --- | --- | --- |
| **Spring Boot** | **org.springframework.boot:spring-boot-dependencies** or parent **spring-boot-starter-parent** | Versions of libraries managed by the Spring Boot ecosystem | Nearly every Spring Boot application |
| **Spring Cloud** | **org.springframework.cloud:spring-cloud-dependencies** | Aligns versions of multiple Spring Cloud projects per release train | When the application uses Spring Cloud components requiring that release train |
| **Spring Cloud Azure** | **com.azure.spring:spring-cloud-azure-dependencies** | Aligns Spring Cloud Azure starters and related Azure dependencies | When integrating Azure via Spring Cloud Azure |
| **Azure SDK for Java** | **com.azure:azure-sdk-bom** | Aligns the Azure SDK library set for Java applications | When using the Azure SDK directly, especially without Spring Cloud Azure |

**Spring Cloud Azure BOM and Azure SDK BOM are not interchangeable.** Both may manage some of the same Azure SDK coordinates, but Spring Cloud Azure BOM is released to support the **Spring Cloud Azure starter suite** in a Spring environment. Azure SDK BOM targets the general SDK library set.

### When Do You Need Both Spring Cloud Azure BOM and Azure SDK BOM?

For a Spring Boot application already using **spring-cloud-azure-dependencies**, start with this BOM alone and declare only the starters you need. If you need an Azure SDK not covered by the starters, first check the version currently managed by Spring Cloud Azure BOM. Only consider adding **azure-sdk-bom** after verifying the impact of overlapping versions.

Do not import two BOMs and assume Maven/Gradle will automatically pick the best combination: each tool has different version reconciliation rules. A later-imported BOM or a directly declared dependency can change the effective version depending on the management mechanism; check the **effective POM / dependency insight** to see the actual result.

### A Starter May Require Additional Spring Components

Starters integrating Spring Data, Spring Security, Spring Integration, or Spring Cloud Stream have relationships with the corresponding Spring release trains. Therefore, seeing a starter with a valid version is not enough to conclude it is compatible with every Spring Boot version.

For example, when upgrading a project from Spring Boot 2 to 3, beyond the BOM there is the move to Java 17, Spring Framework 6, and the **jakarta.*** namespace; these changes are not resolved merely by changing a BOM version number.

## 4. Spring Boot – Spring Cloud Azure Compatibility Matrix

### 4.1. Matrix by *Release Line* for Orientation

The table below is a **map by major line**, intended for orientation while learning. It is **not a certification table for every minor/patch release** and does not replace the official compatibility documentation for the version in use.

| Application Line | Typical Corresponding Spring Cloud Azure Line | Java / Spring Baseline to Check | Selection Caveats |
| --- | --- | --- | --- |
| **Spring Boot 2.x** (especially 2.5–2.7) | **Spring Cloud Azure 4.x** | Java and Spring Framework from the Boot 2 generation | Legacy line; check support status and upgrade needs |
| **Spring Boot 3.x** | **Spring Cloud Azure 5.x** | **Java 17+**, Spring Framework 6, Jakarta namespace | Check **each Boot minor** and the specific Azure 5.x patch release |
| **Spring Boot 4.x** | **Spring Cloud Azure 6.x** | Check Boot 4's Java baseline, Spring Framework 7, and the appropriate Spring Cloud release train | Do not assume all starters or APIs from the 5.x line are compatible with Boot 4 |

The line numbers above help narrow down the investigation. Official documentation may state exact ranges such as **from Boot version A to B**, excluding certain versions or requiring a newer Azure release. When a requirement asks to "upgrade to Spring Boot 3.5.x" or "4.x", **you must re-check the table for the exact release**, not just look at 3.x or 4.x.

Support status changes over time. A release that was once compatible is not guaranteed to still receive security patches or vendor support at deployment time.

### 4.2. How to Look Up a Supported Combination

When selecting a version set, proceed sequentially:

1. **Lock down the Spring Boot version** you intend to use based on application needs and support policy.
2. From the **Spring Cloud Azure documentation**, locate the overview page, dependency management guide, release notes, and **Spring Boot compatibility** for the corresponding Azure release.
3. Verify that the Spring Boot version falls within the **explicitly documented range** of that specific Spring Cloud Azure release, not merely the same major version.
4. If the project uses a separate Spring Cloud release train, cross-check **Spring Cloud compatibility** against that Boot version.
5. Verify the **Java baseline**, as well as Spring Data/Security/Integration/Stream if used.
6. Record the **exact versions** in the build file, inspect the dependency tree, and run the application/integration tests.

**Sources to check before locking versions:**

- Microsoft Learn, Spring Cloud Azure documentation: https://learn.microsoft.com/azure/developer/java/spring-framework/
- Spring Cloud Azure repository, documentation/release notes: https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/spring
- Spring Boot: https://spring.io/projects/spring-boot
- Spring Cloud and release train compatibility: https://spring.io/projects/spring-cloud
- Azure SDK for Java BOM: https://learn.microsoft.com/azure/developer/java/sdk/get-started#manage-dependencies

An older guide may use group/artifact names from the previous generation. With modern Spring Cloud Azure, prefer **com.azure.spring** artifacts and the properly versioned **spring-cloud-azure-dependencies** BOM.

### 4.3. Version Decision Sheet for a Project

Before opening an upgrade pull request, you can fill out a table:

| Decision | Value to Record |
| --- | --- |
| Spring Boot | Specific **major.minor.patch** version |
| Spring Cloud Azure | Specific **major.minor.patch** version, from the compatibility matrix |
| Spring Cloud release train | Version confirmed by Spring Cloud (if the project needs it) |
| Build JDK and runtime JDK | Minimum version and actual version in CI/production |
| Build tool | Maven/Gradle version and Spring Boot plugin |
| Azure starters | List of starters actually used, e.g., Blob and Service Bus |
| Direct Azure SDKs | Individual artifacts and their corresponding effective versions |
| Compatibility evidence | Documentation URL + check date + dependency tree/test results |

Keeping this decision table alongside upgrade notes helps pinpoint the exact cause when an application only fails after a dependency change.

## 5. Maven: Managing the BOM with Spring Boot

### 5.1. Integrating via the Spring Boot Parent

If the POM already inherits **spring-boot-starter-parent**, the Spring Boot BOM is managed by the parent. Add the Spring Cloud Azure BOM inside **dependencyManagement**:

~~~xml
<properties>
    <!-- Replace with a Spring Cloud Azure release verified
         to be compatible with your project's Spring Boot version. -->
    <spring-cloud-azure.version>REPLACE_WITH_VERIFIED_VERSION</spring-cloud-azure.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

This is a **POM snippet**, not a complete Maven file. The project needs a Spring Boot parent/dependency management, appropriate build plugins, and **REPLACE_WITH_VERIFIED_VERSION** replaced with an actual version. The **version** on the Blob starter is intentionally omitted: the BOM manages it.

If the project **does not use the Spring Boot parent**, you can import **org.springframework.boot:spring-boot-dependencies** as a BOM in dependencyManagement. In that case, you must manage build plugins separately; importing a BOM does not inherit plugin configuration from a parent.

### 5.2. When the Project Also Uses a Spring Cloud Release Train

A system with Spring Cloud Gateway, Config, or other Spring Cloud components may need to import the appropriate **spring-cloud-dependencies** BOM. Snippet example:

~~~xml
<dependencyManagement>
    <dependencies>
        <!-- Only add the Spring Cloud BOM when the project needs the corresponding
             Spring Cloud modules; choose the version matching Spring Boot. -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The two properties here must be declared with their **chosen versions**, not the same value. When BOMs contain overlapping dependency coordinates, **the import order and dependency management in parent/child POMs can affect** the effective version in Maven. Rely on the effective POM and dependency tree rather than guessing from the order in a snippet.

Maven typically prioritizes dependency management in the current POM over inherited management; among BOMs imported at the same level that manage the same artifact, **the first declaration wins** under Maven's import rules. Therefore, adding the Azure SDK BOM just to "ensure the latest" can inadvertently introduce versions incompatible with the starters.

### 5.3. Spring Cloud Azure BOM vs. Azure SDK BOM

Two typical configurations:

**Spring Boot application using Spring Cloud Azure starters**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

**Java application using Azure SDK directly, without starters**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure</groupId>
            <artifactId>azure-sdk-bom</artifactId>
            <version>${azure-sdk-bom.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
<dependencies>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-identity</artifactId>
    </dependency>
</dependencies>
~~~

In the second configuration, **azure-sdk-bom.version** must also be given a verified value. Do not treat the two blocks above as a requirement to import both BOMs in the same POM.

## 6. Gradle: Platform and Dependency Management

In Gradle, **platform** is a way to import version constraints from a BOM. Example using **Gradle Kotlin DSL** in a project already configured with a compatible Spring Boot plugin:

~~~kotlin
// build.gradle.kts, dependency illustration section
val springCloudAzureVersion = providers
    .gradleProperty("springCloudAzureVersion")
    .get()

dependencies {
    implementation(
        platform(
            "com.azure.spring:spring-cloud-azure-dependencies:$springCloudAzureVersion"
        )
    )

    implementation("com.azure.spring:spring-cloud-azure-starter-storage-blob")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Declare the value in **gradle.properties**:

~~~properties
# Replace the value with a version verified against the Spring Boot matrix.
springCloudAzureVersion=REPLACE_WITH_VERIFIED_VERSION
~~~

For projects using the **io.spring.dependency-management** plugin, you can also import a Maven BOM via the **dependencyManagement** block. That is **a different mechanism** from Gradle native platform: choose a consistent management approach and inspect resolution results when combining them.

In Gradle, **platform** introduces constraints; version resolution can still be influenced by other dependency constraints or direct versions. **enforcedPlatform** strictly forces versions and can affect downstream consumers' dependency graphs; apply it only if you understand its blast radius, not as a default way to "fix" every conflict.

**Note:** importing the Spring Cloud Azure BOM does not automatically select the **org.springframework.boot** plugin version, Gradle wrapper version, Java toolchain, or every artifact in the Spring ecosystem. Those components must be explicitly configured according to the compatibility matrix.

## 7. Verifying the Versions Actually Selected

A build file that looks reasonable can still pull in the wrong version through transitive dependencies or manual overrides. Inspect the **effective** result, especially after adding a new starter or upgrading the BOM.

### Maven

~~~bash
# View the dependency tree and locations of Azure libraries.
mvn dependency:tree -Dincludes=com.azure.spring,com.azure

# View the effective POM, including inherited/imported dependencyManagement.
mvn help:effective-pom

# Check the project for dependency conflicts shown by Maven.
mvn dependency:tree -Dverbose
~~~

The **dependency:tree** command may display many different artifacts; check at least **azure-core**, **azure-identity**, the SDK of the service in use, and the **com.azure.spring** starters. Some omitted/conflict details depend on the Maven Dependency Plugin version.

### Gradle

~~~bash
# Linux/macOS; on Windows use gradlew.bat.
./gradlew dependencies --configuration runtimeClasspath

# See why a specific version of azure-core was selected.
./gradlew dependencyInsight --dependency azure-core --configuration runtimeClasspath

# Can be repeated for azure-identity and a specific starter.
./gradlew dependencyInsight --dependency azure-identity --configuration runtimeClasspath
~~~

Read the "selected by rule", "by constraint", or dependency path entries to see which dependency determines the version. For errors that occur only at runtime, inspect **runtimeClasspath** rather than just the compile classpath.

### A Concrete Verification Checklist

| What to Inspect | Why |
| --- | --- |
| Actual versions of Spring Boot and Spring Framework | Establishes the baseline and runtime APIs |
| Version of each **spring-cloud-azure-*** | Avoids mixing two starter lines |
| Versions of **azure-core** and **azure-identity** | Foundational dependencies shared by many SDKs |
| Versions of **azure-storage-blob**, **azure-messaging-***, **azure-cosmos** | Ensures the right APIs and business capabilities |
| Duplicate dependencies and manual overrides | May shadow versions managed by the BOM |
| JDK used for building, testing, and running | Avoids compiling with newer Java and deploying to an older runtime |

## 8. Typical Compatibility Errors and How to Distinguish Them

| Symptom | Primary Suspect | How to Verify |
| --- | --- | --- |
| **NoSuchMethodError** or **NoClassDefFoundError** after upgrade | Incompatible APIs between library versions, overridden version | Inspect stack trace and dependency tree; check which jar contains the class/method |
| **ClassNotFoundException** during Spring startup | Missing dependency or Spring Framework / Jakarta mismatch | Check starter, Java namespace, and Boot matrix |
| **BeanCreationException** / auto-configuration failure | Configuration, dependency, or auto-configuration API no longer compatible | Read the root cause, conditions report, and release notes |
| **UnsupportedClassVersionError** | Java runtime older than library/application bytecode | Check Java runtime, toolchain, and Boot baseline |
| Build reports missing version for starter | BOM not imported, wrong group/artifact imported, or missing version property | Check dependencyManagement or Gradle platform |
| **401** / **403** when calling Azure | Incorrect token, RBAC, scope, or access policy | Check principal, data-plane role, audience, firewall; do not rush to change the BOM |
| Timeout / Azure connection failure | DNS, firewall, proxy/private endpoint, or retries | Check network path, SDK diagnostics, and Azure metrics |

Error messages are **clues**, not final diagnoses. For example, **NoSuchMethodError** may arise from a specific dependency override, whereas **403** usually points to authentication/authorization or network policy rather than a BOM version.

**Scenario example:** an application uses Spring Boot 3.x and the Azure 5.x starter line. A developer individually updates **azure-core** to a higher version without consulting the BOM. The build succeeds, but at runtime a **NoSuchMethodError** occurs from the SDK. The fix is to find the effective version and transitive path, remove the override if there is no verified reason for it, and re-run tests—not to randomly swap individual artifacts.

## 9. A Verified Upgrade Workflow

Upgrades should follow verifiable and reversible steps:

1. **Capture the current state:** Java/Boot/Cloud/Azure versions, dependency tree, Azure APIs in use, connectivity tests, and deployment environment.
2. **Choose the target:** consult the compatibility matrices for Spring Cloud Azure, Spring Cloud, and the JDK baseline; record the exact supported patch versions.
3. **Upgrade from the central management point:** update the BOM and Spring Boot version in the appropriate location; avoid forcing individual Azure SDK versions. For major upgrades, read the migration guide.
4. **Build and inspect the dependency graph:** detect mixed old/new starters, conflicts, dropped dependencies, or package renames.
5. **Test locally:** business unit tests, Spring context smoke tests, profile configurations, and client instantiation.
6. **Test against managed services:** use a test Azure environment with real identities, real RBAC, endpoints/private networking, and the corresponding Blob/Service Bus/Cosmos/Key Vault resources.
7. **Observe during rollout:** metrics, latency, error rates, retries, message redelivery, and logs free of secrets; prepare a rollback path to the previous BOM/Boot version.

Avoid bundling a Spring Boot major upgrade, a Spring Cloud Azure major upgrade, and a messaging redesign into a single oversized change when verification steps can be separated.

### Designing Appropriate Tests

- **Unit tests:** mock the Azure client adapter/repository; prove business logic does not depend on live cloud services.
- **Local integration tests:** for Blob, **Azurite** supports part of the Storage API but does not fully represent Microsoft Entra ID, RBAC, private networking, or every real Azure behavior.
- **Integration tests on Azure:** verify credentials, least-privilege roles, data operations, timeouts/retries, quotas, and test resource cleanup.

**A library compatibility matrix does not replace an environment matrix:** a valid version combination can still fail if workload identity is unconfigured, a service principal lacks roles, private DNS is misconfigured, or the Azure resource does not exist yet.

## 10. Comparing Dependency Management Across the Three Clouds

| Platform | Java SDK | Spring Integration Library | Version Management Principle |
| --- | --- | --- | --- |
| **Azure** | Azure SDK for Java, **azure-sdk-bom** | Spring Cloud Azure, **spring-cloud-azure-dependencies** | Prefer Spring Cloud Azure BOM when using starters; check the Boot/Java matrix |
| **AWS** | AWS SDK for Java v2 and its SDK BOM | Spring Cloud AWS and the corresponding line's BOM | Pick a Spring Cloud AWS release matching Boot; verify AWS SDK alignment |
| **Google Cloud** | Google Cloud Java client libraries and appropriate BOM | Spring Cloud GCP and the project's dependency management | Align the Spring Cloud GCP line with Boot, Google Cloud SDK, and Java |

Sharing the name "BOM" does not mean the three providers share release cadences or full compatibility semantics. When switching providers, review the **starter catalog**, credential chains, RBAC/IAM, retry semantics, storage/messaging resources, consistency, and testing strategies. Spring libraries reduce wiring code, but they do not make managed services behave identically.

## 11. Lab Exercise: Choosing the Right BOM and Detecting Conflicts

**Scenario:** the development team has a Spring Boot 3.x application that writes files to Azure Blob Storage and sends events via Service Bus. A feature branch proposes adding a new SDK with a hard-coded version.

Steps:

1. Identify the **specific Spring Boot version**, runtime JDK, and a Spring Cloud Azure release documented as compatible with that Boot version.
2. Declare only the **spring-cloud-azure-dependencies** BOM in dependency management, add the two corresponding starters, and omit versions on the starters.
3. Run Maven dependency:tree or Gradle dependencyInsight to record the actual versions of **azure-core**, **azure-identity**, **azure-storage-blob**, and **azure-messaging-servicebus**.
4. On an experimental branch, add a version override for one Azure SDK; observe how the dependency graph changes, then remove the override.
5. Write a smoke test that boots the Spring context, followed by uploading a blob and sending/receiving a message against properly authorized test resources.
6. Write a one-page upgrade decision record: compatibility source, selected versions, rationale for removing the override, and test evidence.

### Self-Check Questions

1. Why does importing a BOM without declaring a starter leave the application without a Blob client?
2. Should a Spring Boot project using Azure starters import **azure-sdk-bom** as well by default? What must be checked when two BOMs are present?
3. Why is matching the same major version of Spring Cloud Azure not enough to confirm compatibility with a new Spring Boot minor version?
4. When should you inspect **dependencyInsight/dependency:tree**, and when should you check **Azure RBAC**?
5. What changes besides the BOM version might upgrading from Spring Boot 2 to 3 require?

## 12. Key Takeaways

- **A BOM manages versions**, whereas dependency declarations determine which libraries are added. A BOM does not grant Azure permissions or guarantee runtime compatibility.
- For Spring Boot applications using **Spring Cloud Azure starters**, start with **com.azure.spring:spring-cloud-azure-dependencies**. For Java applications using the SDK directly, consider **com.azure:azure-sdk-bom**.
- The line-level mapping **Boot 2 ↔ Azure 4**, **Boot 3 ↔ Azure 5**, **Boot 4 ↔ Azure 6** is only for orientation; always verify the **exact minor/patch versions**, release docs, and Java baseline before deciding.
- Inspect **effective dependency versions**, avoid arbitrary overrides, and confirm with builds, Spring context tests, and integration tests on real cloud resources.
- Separate dependency issues from **identity, RBAC, endpoints, DNS, network, and Azure service** issues so you fix the right root cause.

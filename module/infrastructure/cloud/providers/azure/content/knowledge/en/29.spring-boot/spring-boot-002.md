# Managing Dependencies with Spring Cloud Azure

A Spring Boot service needs to read configuration from Azure Key Vault, upload documents to Azure Blob Storage, and send order events through Azure Service Bus. A developer adds three Azure libraries to `pom.xml`, yet when deploying the application, it throws a `NoSuchMethodError` related to Azure Core; in another environment, the app starts up but fails to acquire a token from Microsoft Entra ID. Someone suggests "upgrading every dependency to the latest version," while another suggests "copying the connection string into application.yml for speed."

Both workarounds carry risk. **A Spring Boot project on Azure must manage two independent yet related concerns:**

1. **The right libraries and compatible version alignment** so the classpath and auto-configuration work.
2. **The right operational configuration, identity, and access permissions** so the application can actually connect to Azure.

**Spring Cloud Azure** provides starters, Spring Boot integrations, and a **Bill of Materials (BOM)** that help manage library versions across the Azure ecosystem. A BOM reduces conflicts and the number of versions you have to specify manually, but it **does not guarantee that every combination of Spring Boot, Spring Cloud, Java, Azure SDK, and Azure services is compatible**. Developers still must choose a verified release set and maintain the software supply chain.

This lesson belongs to the **Spring Boot on Azure** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module introduces all of Azure from subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, and data through deployment, monitoring, protection, and cost optimization. Therefore, this lesson does not stop at Maven/Gradle syntax; it also guides you on deciding which dependencies to include, using managed identity, mastering transitive dependencies, testing, and deploying across environments.

> **Version policy:** No single fixed Spring Cloud Azure version fits every project. Spring Boot, Spring Cloud, Java, Spring Cloud Azure, and Azure SDK release lines change over time. Entries marked `REPLACE_WITH_APPROVED_*` are **placeholders that must be replaced with compatible versions verified against current policies and release documentation**. Do not copy placeholders verbatim into a real build. Commands in this lesson are examples for learners to run in their own lab projects; authoring this document does not run Maven/Gradle or modify files in the current repository.

## 1. Learning Objectives

After this lesson, you can:

1. Explain the roles of **Spring Boot dependency management**, the **Spring Cloud BOM**, and the **Spring Cloud Azure BOM**.
2. Distinguish between a **starter**, **auto-configuration**, **direct Azure SDK**, **BOM**, and **runtime configuration**.
3. Add `spring-cloud-azure-dependencies` to Maven/Gradle with the proper scope.
4. Select appropriate starters for **Key Vault Secrets, Blob Storage, Service Bus, and App Configuration**.
5. Avoid pinning individual versions on Azure starters when the BOM already manages them.
6. Understand why you cannot blindly pick the newest Spring Cloud Azure line for your current Spring Boot version.
7. Read the **effective POM**, **dependency tree**, and **Gradle dependencyInsight** to locate version conflicts.
8. Recognize `NoSuchMethodError`, `ClassNotFoundException`, auto-configuration failures, and authentication errors.
9. Apply **DefaultAzureCredential/managed identity**, service-specific RBAC, Key Vault, and per-environment configuration.
10. Design unit, integration, smoke, and CI tests to catch dependency drift before Production.
11. Distinguish between the **Azure Service Bus starter, JMS, Spring Integration, and the Spring Cloud Stream binder**.
12. Plan a safe **upgrade/migration** from older versions to a new release train.
13. Use SBOMs and dependency/security scanning without blindly forcing library upgrades.
14. Complete a lab adding the BOM and at least two starters, then explain the entire resolved classpath.

## 2. Typical Scenario: Order Processing API

Suppose the `order-api` application has the following architecture:

```text
Client
  |
  v
Spring Boot order-api (Java)
  |
  +-- Azure Key Vault
  |     +-- retrieve authorized secrets
  |
  +-- Azure Blob Storage
  |     +-- store invoice files
  |
  +-- Azure Service Bus
  |     +-- publish OrderCreated
  |
  +-- Application Insights / Azure Monitor
  |     +-- application telemetry
  |
  v
Azure Container Apps or AKS/App Service
      |
      +-- Managed Identity / Workload Identity
      +-- Network + DNS + private access by design
```

The development team wants to:

- Avoid manually writing boilerplate for every HTTP client, token acquisition, and retry per service.
- Never hard-code access keys in source code.
- Manage dependencies from a single unified point.
- Use Spring Boot configuration binding/auto-configuration when appropriate.
- Inspect the classpath and upgrade versions in a controlled way.
- Separate **classpath** errors from **RBAC/network** errors during troubleshooting.

Spring Cloud Azure supports those goals, **but it does not provision Azure resources for you**, create role assignments automatically, or verify business logic on its own.

## 3. What Is a Dependency and Why Does Version Alignment Matter?

A Java application does not contain only the libraries you list directly in `pom.xml`.

```text
order-api
  |
  +-- spring-boot-starter-web
  |     +-- Spring Web/MVC
  |     +-- Jackson and related libraries
  |
  +-- spring-cloud-azure-starter-storage-blob
  |     +-- Spring Cloud Azure auto-configuration
  |     +-- Azure Storage Blob SDK
  |     +-- Azure Core / Identity / HTTP pipeline dependencies
  |
  +-- spring-cloud-azure-starter-servicebus
        +-- Spring Cloud Azure Service Bus integration
        +-- Azure Messaging Service Bus SDK
        +-- Azure Core / AMQP/Reactor dependencies
```

The libraries underneath are called **transitive dependencies**. If two branches require two different versions of the same `azure-core` or Reactor artifact, Maven/Gradle will **resolve a single final version** according to the build tool's rules. That version may not match what another library was compiled against.

Common symptoms include:

- `NoSuchMethodError`: runtime invokes a method that no longer exists or lacks the expected signature.
- `ClassNotFoundException` or `NoClassDefFoundError`: missing class/module at runtime.
- `IllegalAccessError`, `LinkageError`: incompatible classpath/APIs.
- Auto-configuration fails even though code did not change.
- Netty/Reactor/HTTP client conflicts.
- One library changes its contract while the app still uses an older starter.

**Dependency management aims to produce a consistent version graph**. It cannot make two incompatible API versions compatible simply by forcing them to the same version number.

## 4. Distinguishing Five Easily Confused Components

| Component | What does it do? | Example |
|---|---|---|
| **Spring Boot starter** | Pulls in a group of foundational Spring Boot dependencies/config. | `spring-boot-starter-web`. |
| **Spring Cloud Azure starter** | Adds Spring/Azure integration and auto-configuration for the target service. | `spring-cloud-azure-starter-storage-blob`. |
| **Azure SDK for Java** | Provides client APIs to interact directly with Azure. | `azure-storage-blob`, `azure-messaging-servicebus`. |
| **BOM** | Synchronized catalog of managed versions for artifacts within the BOM's scope. | `spring-cloud-azure-dependencies`. |
| **Runtime configuration** | Specifies endpoints, namespaces, credentials, resource names, and policies. | `spring.cloud.azure.storage.blob.account-name`. |

**A BOM is not a runtime library.** Importing a BOM does not put the Blob SDK on your classpath. You still need the actual starter or SDK dependency.

**A starter is not an Azure resource.** Adding the Service Bus starter does not create a namespace or queue for you. Resources, IAM/RBAC, networking, quotas, and costs must be managed separately.

## 5. Three Layers of Version Management

A typical application involves at least:

```text
Java runtime / toolchain
           |
Spring Boot release + Boot dependency BOM
           |
Spring Cloud release train (if using Spring Cloud components)
           |
Spring Cloud Azure release + Azure BOM
           |
Azure SDK libraries + HTTP/identity dependencies
           |
Java application and Azure configuration
```

**Spring Boot BOM** manages many Spring, Jakarta, Jackson, testing, logging, Reactor, and related libraries.

**Spring Cloud BOM** manages a Spring Cloud ecosystem such as Config/Gateway/Stream and modules in that release train; include it only when the project truly uses them and requires alignment with that release.

**Spring Cloud Azure BOM** manages Spring Cloud Azure artifacts and a curated set of related Azure dependencies per release.

These three BOMs **cannot substitute for one another**. If multiple BOMs manage the same artifact, **import order and direct dependencyManagement entries can affect which version is selected**; inspect the effective POM or Gradle resolved graph rather than guessing.

## 6. Choose the Release Matrix Before Writing Dependencies

Before selecting `spring-cloud-azure.version`, confirm:

1. Java runtime/JDK: version and vendor supported by the organization.
2. Spring Boot major/minor/patch version.
3. Spring Framework/Jakarta namespace matching the Spring Boot version.
4. Spring Cloud release train if used by the project.
5. Spring Cloud Azure line officially supporting that Boot/Cloud pair.
6. Azure SDK versions managed by the BOM.
7. Required Azure services and starters.
8. Maven/Gradle plugins, compiler toolchain, and test framework.
9. Security advisories and end-of-support policies.
10. Production hosting constraints (App Service, Container Apps, AKS, Java native image if applicable).

### Compatibility Rules

**Do not assume:** "Spring Boot 4 works with Spring Cloud Azure 5 because both have newer numbers." Major version transitions can change Spring Framework, Jakarta APIs, auto-configuration metadata, Reactor, and dependencies.

**Do not assume:** "The latest Azure SDK works with an older starter." A starter may have been compiled against APIs from a different SDK line.

Build a **compatibility matrix** from the official release notes and support tables for Spring Cloud Azure and Spring Boot; lock that version set in the project build, test it, and upgrade periodically.

## 7. A Verifiable Version-Selection Process

| Step | What to ask? | Evidence to record |
|---|---|---|
| 1. Fix Boot | Which Boot major/minor is the project using? | Parent/plugin version in the build file. |
| 2. Choose Spring Cloud | Are Gateway/Config/Stream components used? | Release train compatible with Boot. |
| 3. Choose Spring Cloud Azure | Which line is supported for this Boot/Cloud pair? | Official compatibility table and release notes. |
| 4. Check Java | Which JDK does the target release require? | Java baseline/toolchain. |
| 5. Verify starters | Do the artifacts exist in the chosen release line? | Artifact coordinates from the actual release. |
| 6. Import BOM | Which Azure artifacts does the BOM align? | Effective POM/resolved dependencies. |
| 7. Test build/run | Any compilation/linkage/auto-config errors? | CI output and integration tests. |
| 8. Security scan | Any CVEs or out-of-support releases? | SBOM and vulnerability report. |
| 9. Write ADR | Why lock this version set? | Architecture decision record. |
| 10. Plan upgrades | When to upgrade and how to roll back? | Cadence, owner, acceptance criteria. |

Specific lines/versions **must not be invented or arbitrarily hardcoded** in this guide. The code below uses placeholders to force learners to substitute **versions backed by compatibility evidence**.

## 8. Maven: Importing the Spring Cloud Azure BOM

Minimal `pom.xml` example for a Spring Boot app using **Key Vault Secrets** and **Blob Storage**. Placeholders are text to be replaced; **do not run the template verbatim**.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_APPROVED_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>order-api</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <spring-cloud-azure.version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</spring-cloud-azure.version>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
        </dependency>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
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

### Why Omit Versions on Individual Starters?

Because the BOM manages the versions, dependencies can be declared **without `<version>`**. Putting arbitrary versions on individual starters weakens alignment and can create an uncontrolled classpath.

### Breakdown of Each Section

- `spring-boot-starter-parent` supplies Boot's dependency/plugin management.
- `dependencyManagement` imports the Spring Cloud Azure BOM with `pom`/`import`.
- `spring-cloud-azure-starter-keyvault-secrets` enables Key Vault integration.
- `spring-cloud-azure-starter-storage-blob` provides Blob Storage integration.
- The test starter has `scope=test`, keeping the test framework out of the production runtime.
- Azure credentials and endpoints **are not written in pom.xml**.

**Java 17 in the example is illustrative only** and does not guarantee every Boot/Spring Cloud Azure pair targets that baseline. Pick the JDK from the real compatibility matrix.

## 9. Maven: A BOM Does Not Automatically Pull All Services

If you only declare:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

then **no Azure Blob SDK/starter is on the runtime classpath yet**. A BOM only manages versions **when the corresponding dependency is requested** directly or transitively.

To use Blob, you must add:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

and then configure the resource/identity properly. The same applies to Key Vault, Service Bus, and other integrations.

### Dependency Management vs. Dependency Declaration

| Block | Meaning |
|---|---|
| `<dependencyManagement>` | Defines default version/scope/exclusions when an artifact is used. |
| `<dependencies>` | Actually requests the dependency in the project. |
| `<scope>test</scope>` | Used at compile/test time per Maven semantics; excluded from production runtime. |
| `<scope>provided</scope>` | Supplied by the runtime/environment per contract; use cautiously. |
| `<exclusions>` | Intentionally removes a transitive dependency; can cause missing-class errors. |

**Do not use exclusions to "patch" a linkage error before proving which dependency is wrong.**

## 10. Gradle Groovy DSL: Importing the BOM via Plugin

A common approach using the `io.spring.dependency-management` plugin:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_APPROVED_BOOT_VERSION'
    id 'io.spring.dependency-management' version 'REPLACE_WITH_APPROVED_PLUGIN_VERSION'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencyManagement {
    imports {
        mavenBom "com.azure.spring:spring-cloud-azure-dependencies:REPLACE_WITH_COMPATIBLE_SCA_VERSION"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.azure.spring:spring-cloud-azure-starter-keyvault-secrets'
    implementation 'com.azure.spring:spring-cloud-azure-starter-storage-blob'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### Notes

- The Spring Boot plugin and dependency-management plugin require compatible versions.
- `dependencyManagement.imports.mavenBom` manages versions similarly to Maven through the plugin's mechanism.
- Do not copy snippets from older plugin versions after Boot/Gradle major versions change.
- With Gradle's native BOM platform, import semantics and conflict resolution differ; choose one consistent strategy.

**Do not assume Maven and Gradle always resolve the exact same transitive versions** when multiple BOMs or constraints exist. Inspect the actual runtime classpath.

## 11. Gradle Kotlin DSL: BOM via Native Platform

Another approach is Gradle's native `platform(...)`, illustrated in `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "REPLACE_WITH_APPROVED_BOOT_VERSION"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(
        platform(
            "com.azure.spring:spring-cloud-azure-dependencies:REPLACE_WITH_COMPATIBLE_SCA_VERSION"
        )
    )
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("com.azure.spring:spring-cloud-azure-starter-storage-blob")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

**Version resolution warning:** if a project does not use the Boot dependency-management plugin, the Spring Boot Gradle plugin has specific BOM expectations; depending on the project, you may also need to import the Spring Boot BOM as a Gradle `platform("org.springframework.boot:spring-boot-dependencies:...")` or use equivalent BOM management. Check the **resolved dependency graph** to confirm all Spring/Jackson/Reactor versions are properly managed.

### Do Not Mix Strategies Arbitrarily

These two approaches do not behave identically:

1. The `io.spring.dependency-management` plugin with `dependencyManagement.imports.mavenBom`.
2. Gradle native `platform(...)` with Gradle version constraints and conflict resolution.

Choose one clear configuration and document it in repository conventions. If both must coexist, understand version resolution precedence and test thoroughly—never guess.

## 12. Which Starters Should Be Included in the Application?

| Need | Spring Cloud Azure artifact to evaluate | Notes |
|---|---|---|
| Read secrets from Key Vault as a configuration source. | `spring-cloud-azure-starter-keyvault-secrets` | Requires secrets read permissions, endpoint, and property-source config. |
| Use Blob Storage with Spring integration. | `spring-cloud-azure-starter-storage-blob` | Storage Blob data-plane RBAC and account config. |
| Integrate Azure Service Bus SDK/Spring Boot. | `spring-cloud-azure-starter-servicebus` | Distinct from JMS/Stream binders. |
| App Configuration with the Spring configuration model. | `spring-cloud-azure-starter-appconfiguration-config` | Artifact/config import depends on release line; verify module in release. |
| Service Bus via Spring JMS. | `spring-cloud-azure-starter-servicebus-jms` | Choose when code truly uses the JMS contract and supported features. |
| Service Bus with Spring Integration. | `spring-cloud-azure-starter-integration-servicebus` | Choose when the app uses Spring Integration channels. |
| Service Bus via Spring Cloud Stream. | `spring-cloud-azure-starter-stream-servicebus` | Verify binder compatibility with the Spring Cloud release train. |

**These coordinates represent common Spring Cloud Azure release lines.** Specific releases may rename, split, or remove artifacts or change configuration style. Verify published artifacts in your exact release line; never force Maven to fetch nonexistent artifacts or mix an old starter with a new BOM.

### Do Not Add Every Starter "Just in Case"

If the application only uses Key Vault and Blob, do not add JMS, Service Bus, Cosmos DB, Redis, Event Hubs, and other integrations. Unused starters bloat the classpath, widen the attack surface, increase unwanted auto-configuration, and complicate debugging.

**Principle:** every dependency must have a use case, an owner, and a clear reason to exist.

## 13. BOM, Starter, and Azure SDK: Three Usage Patterns

Suppose you only need Azure Blob Storage.

**Option A — Spring Cloud Azure starter:**

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Suitable when you want Spring Boot property binding, auto-configuration, and client beans provided by the starter.

**Option B — Direct Azure SDK:**

```xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
    <version>REPLACE_WITH_APPROVED_AZURE_SDK_VERSION</version>
</dependency>
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>REPLACE_WITH_APPROVED_IDENTITY_VERSION</version>
</dependency>
```

Suitable when you want to construct clients manually without Spring integration; if an approved Azure SDK BOM exists, prefer the BOM over pinning individual SDK versions.

**Option C — Combining starter and custom client:**

You can use the starter for the main service while defining a custom `BlobServiceClient` when you need a second account/endpoint, a special proxy/HTTP transport, or a distinct credential policy.

**Point to verify:** multiple client beans of the same type can break autowiring or inject the wrong account. Use `@Qualifier`, explicit bean names, and tests.

## 14. Understanding Spring Cloud Azure Auto-Configuration

Starters typically ship auto-configuration classes and Spring Boot configuration metadata. When conditions match, Spring can instantiate clients/beans based on:

- Presence of required Azure SDK classes on the classpath.
- Configured service endpoints/accounts/namespaces.
- Credential providers/identities.
- Conditional annotations and properties.
- Presence or absence of an application-defined bean.
- Active Spring profiles.
- Property source import mechanisms when using Key Vault/App Configuration.

```text
pom.xml / Gradle
     |
     +-- Starter available on classpath
     |
     v
Spring Boot starts
     |
     v
Auto-configuration conditions evaluated
     |
     +-- match + config valid -> Azure client bean
     |
     +-- no match -> no bean or startup failure (depending on module)
     |
     v
Application services inject clients
```

**Not every starter automatically generates every type of bean**. Exposed API beans and auto-configuration vary by release; inspect the actuator conditions report/diagnostics and the documentation for your chosen version.

### When to Configure Manually?

- Multiple storage accounts in a single application.
- Custom retries/timeouts, HTTP proxies, transports, and diagnostics.
- Connecting through special endpoints or sovereign clouds.
- Separating identities per service.
- Starter-created beans do not match a specific contract.

When creating clients manually, manage **credential lifecycle, thread safety, close/shutdown, telemetry, and testability**.

## 15. Key Vault Secrets Starter

Key Vault stores secrets/keys/certificates; the **Secrets starter** primarily supports retrieving secrets/configuration via the provided APIs and property-source integrations.

Maven dependency:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-keyvault-secrets</artifactId>
</dependency>
```

Example `application.yml` with a common property source configuration:

```yaml
spring:
  cloud:
    azure:
      keyvault:
        secret:
          property-sources:
            - endpoint: https://REPLACE_WITH_VAULT_NAME.vault.azure.net/

app:
  payment:
    # Never put real passwords or tokens in YAML.
    mode: sandbox
```

**Property syntax must be checked against your actual Spring Cloud Azure version**. Some lines support multiple property sources and ordering; older generations use different naming/auto-config conventions.

### Key Distinctions

- Key Vault **management permissions** do not grant data-plane permission to read secrets.
- `@Value("${secret-name}")` only works if the secret name maps into the Spring Environment under the active configuration.
- Secret name normalization (hyphens, dots) may differ from app property conventions.
- Secret refresh/rotation does not automatically update every singleton bean that read the value at startup.
- Never assume the app will "always stay up" if the vault/identity/network transiently fails during startup.

### Safe Startup Design

For **mandatory** secrets, consider failing startup explicitly if retrieval fails, while setting reasonable timeouts/retries. For optional secrets, use an approved fallback—never fall back to plaintext credentials in source code.

## 16. Blob Storage Starter

Dependency:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Illustrative configuration:

```yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: REPLACE_WITH_STORAGE_ACCOUNT

app:
  storage:
    container: documents-lab
```

Spring Cloud Azure can create Blob SDK client(s) from configuration and appropriate identity depending on the release.

Example service bean using the client:

```java
package com.example.orders;

import com.azure.storage.blob.BlobServiceClient;
import org.springframework.stereotype.Service;

@Service
public class BlobAccountInfoService {
    private final BlobServiceClient blobServiceClient;

    public BlobAccountInfoService(BlobServiceClient blobServiceClient) {
        this.blobServiceClient = blobServiceClient;
    }

    // This method only reads metadata from the client object.
    public String configuredAccountName() {
        return blobServiceClient.getAccountName();
    }
}
```

**This code requires** that the selected auto-configuration version actually exposes a `BlobServiceClient` bean; otherwise, define an explicit bean or use the SDK per its contract. Having the bean in the Spring context **does not prove the identity has permission to upload blobs**. A data-plane role such as `Storage Blob Data Contributor` must be assigned at the proper scope for write operations.

### Separate Container Names from SDK Dependencies

Read container names, endpoints, and account names from per-environment configuration. Never build a different JAR just to change a storage account from lab to Production.

## 17. Service Bus Starter and Integration Paths

Azure Service Bus supports queues/topics/subscriptions, and how a Spring application consumes it depends on the programming model:

| Integration approach | Programming style | Related dependency |
|---|---|---|
| **Azure SDK** | `ServiceBusClientBuilder`, `ServiceBusSenderClient`, processor client. | `azure-messaging-servicebus`. |
| **Spring Cloud Azure starter** | Boot-style configuration and client integration. | `spring-cloud-azure-starter-servicebus`. |
| **Spring JMS** | `JmsTemplate`, `@JmsListener` where supported. | `spring-cloud-azure-starter-servicebus-jms`. |
| **Spring Integration** | Message channels/adapters. | `spring-cloud-azure-starter-integration-servicebus`. |
| **Spring Cloud Stream** | Function/message binder patterns. | `spring-cloud-azure-starter-stream-servicebus` per compatibility. |

**Do not attach all starters** just because the app "uses Service Bus." Pick the one abstraction that fits your processing model, error semantics, transactions, and team skills.

Maven:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-servicebus</artifactId>
</dependency>
```

Example property:

```yaml
spring:
  cloud:
    azure:
      servicebus:
        namespace: REPLACE_WITH_SERVICEBUS_NAMESPACE
```

Namespace/transport/entity property configurations differ by starter and integration type, so for JMS/Stream read the exact property mappings of that artifact.

### Things Dependencies Do Not Decide

- Whether the entity is an actual queue or topic.
- Whether the receiver uses peek-lock or receive-and-delete.
- Dead-lettering, retries, TTL, and duplicate handling.
- Whether the Service Bus data-plane role has send/receive rights.
- Which AMQP port the connection uses, or whether proxies/firewalls block it.
- Whether the consumer has an idempotent business handler.

## 18. Direct Service Bus SDK Example to Understand the Dependency Layer

When not using starter auto-configuration, the Azure SDK can create a sender using a Microsoft Entra credential.

```java
package com.example.orders;

import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusMessage;

public final class OrderPublisher {
    private OrderPublisher() {}

    public static void sendLabMessage(
            String fullyQualifiedNamespace,
            String queueName) {

        try (ServiceBusSenderClient sender =
                 new ServiceBusClientBuilder()
                     .credential(
                         fullyQualifiedNamespace,
                         new DefaultAzureCredentialBuilder().build()
                     )
                     .sender()
                     .queueName(queueName)
                     .buildClient()) {

            ServiceBusMessage message =
                new ServiceBusMessage("OrderCreated:ORD-LAB-1042");
            message.setMessageId("evt-lab-1042-created");
            sender.sendMessage(message);
        }
    }
}
```

**This is a Java SDK example**, not a requirement to add Azure starters just to run it. It requires compatible `azure-identity` and `azure-messaging-servicebus` versions, Azure Service Bus Data Sender permission on the right queue/namespace, and working network connectivity.

- Use a **stable message ID** and business-level idempotency.
- Do not send real messages inside constructors or uncontrolled startup hooks.
- Clients can be managed as singleton beans instead of recreating one per message; try-with-resources here merely illustrates lifecycle.
- Never treat send success as downstream processing success.

## 19. App Configuration and Key Vault Are Not the Same Resource

**Azure App Configuration** suits governed application settings and feature flags. **Key Vault** suits managing secrets, keys, and certificates.

```text
App Configuration
  ├── feature toggle
  ├── pricing-policy-version
  └── endpoint/name/reference to secrets
         |
         v
Key Vault
  ├── external-api-key
  └── service credential when managed identity cannot be used
```

Spring Cloud Azure offers an integration for App Configuration, such as `spring-cloud-azure-starter-appconfiguration-config` in supported release lines. When choosing it, verify:

- Whether the artifact exists in your locked version.
- Whether Spring Config Data import requires `spring.config.import` or equivalent configuration.
- Feature flag refresh/watch semantics of that release.
- Labels/filters separating dev/staging/prod.
- Where Key Vault references are resolved and which identity needs permissions.
- Whether runtime refresh, consistency, and rollback mechanisms exist.

**Do not use App Configuration as the default store for raw secrets** when Key Vault is available. **Do not use Key Vault as a dump for every non-sensitive setting** just because it is already provisioned.

## 20. Dependency Alignment and Credentials Are Separate Problems

Example:

```text
Classpath OK:
  Spring Cloud Azure starter load successful
  BlobServiceClient created

Azure call FAIL:
  403 AuthorizationPermissionMismatch
```

This is **not evidence of a broken BOM**. The error may come from a managed identity missing a Blob data role, a wrong endpoint/account, a firewall, or a missing resource.

Conversely:

```text
Application fails at startup:
  java.lang.NoSuchMethodError on azure-core/HTTP pipeline
```

This error **likely** stems from version alignment/classpath issues and will not be fixed by granting broader Azure RBAC permissions.

### Error Classification Map

| Error category | Symptoms | First check |
|---|---|---|
| Dependency/linkage | `NoSuchMethodError`, missing class. | Dependency tree, BOM/version overrides. |
| Auto-config | No qualifying bean, property bind failure. | Conditions report and starter module. |
| Authentication | 401, credential chain failed. | Principal, token, env/config. |
| Authorization | 403, forbidden. | Data-plane RBAC/scope and propagation. |
| Resource/config | 404, invalid namespace/account. | Endpoint/entity names, environment. |
| Network | Timeout/DNS/TLS/AMQP connection. | Private DNS, outbound rules, TLS. |
| Throttling | 429/quota/exceeded. | Azure service quota/capacity/retry. |
| Business semantics | Duplicate message, stale secret, wrong container. | Idempotency, ownership, validation. |

## 21. Passwordless Identity: DefaultAzureCredential

Prefer Microsoft Entra authentication or managed identity whenever supported by the Azure service and Java SDK.

A typical chain:

```text
Local developer
  → az login / IDE-supported credential
  → DefaultAzureCredential (per chain and SDK)
  → Azure service data plane

Cloud runtime
  → Managed identity / Workload Identity
  → Azure service data plane
```

`DefaultAzureCredential` may attempt multiple credential sources depending on the environment and SDK version. Therefore:

- Dev/test can use Azure CLI/IDE login when configured.
- Production should rely on **one known identity** provided by the hosting platform.
- Never allow a production container to accidentally pick up a developer credential.
- If the runtime supports multiple user-assigned identities, select the exact client ID per policy.
- Never log access tokens or credential values.
- Assign roles for **each service** individually.
- Verify the tenant/subscription of the active principal.
- If the chain fails to acquire a credential, investigate identity configuration instead of expanding permissions indefinitely.

**Spring Cloud Azure starters can automatically construct credentials/clients** per their configuration; in custom code, use the Azure SDK `DefaultAzureCredentialBuilder`. Do not assume every starter version exposes a credential bean directly.

## 22. Entra RBAC: Control Plane Differs from Data Plane

| Service | Example data-plane role to evaluate | Conditions |
|---|---|---|
| Key Vault Secrets | Role allowed to read secrets, e.g., `Key Vault Secrets User` under RBAC mode. | Does the vault use RBAC or access policies? |
| Blob Storage | `Storage Blob Data Reader/Contributor`. | Read or write? Account or container scope? |
| Service Bus | `Azure Service Bus Data Sender/Receiver`. | Send or consume? Namespace or entity scope? |
| App Configuration | Data Reader role for the data plane. | Read-only config/feature flags? |
| Application Insights/Monitor | Permissions to configure or export telemetry per method. | Does not equate to reading the whole workspace. |

**These are common role names, not guarantees that permissions exist in your subscription**. Verify the actual role, scope, access mode, and propagation.

A service principal with **Contributor on a resource group** does not automatically have permission to read secrets or Blob data through the SDK. On a 403 error, do not switch SDK versions before verifying RBAC.

## 23. Organizing Configuration by Environment

One rule: **same JAR, different configuration and identity per environment**.

```text
order-api.jar
    |
    +-- local   → developer login + lab resources
    |
    +-- staging → staging managed identity + staging resources
    |
    +-- prod    → prod managed identity + production resources
```

Values can come from `application.yml`, profiles, environment variables, or a configuration service.

```yaml
app:
  storage:
    container: ${APP_STORAGE_CONTAINER:documents-lab}

spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}
      servicebus:
        namespace: ${AZURE_SERVICEBUS_NAMESPACE}
```

In Spring configuration, `${ENV_NAME:default}` reads an environment variable with a fallback default; `${ENV_NAME}` requires a supplied value (or an explicit missing-config handling mechanism).

### Keep Secrets Out of Git

- Never store real connection strings in `application-prod.yml`.
- Never echo `AZURE_CLIENT_SECRET` into CI logs.
- Never commit `.env` files containing secrets.
- Use Key Vault/secret managers, managed identity, and pipeline secret handling.
- Protect runtime environments, crash dumps, and diagnostic reports.
- Do not share the same identity/key across all environments just for testing convenience.

### Property Source Precedence

Spring Boot and its integrations follow specific precedence rules across property sources. Key Vault and App Configuration may participate in resolution depending on the module/version and import mode. When two sources define the same key, know **which source wins**. Inspect effective property resolution (sanitized names/sources only—never print secrets) and define clear ownership.

## 24. Investigating a Missing Bean

Suppose a controller constructor requires `BlobServiceClient` and startup reports:

```text
Parameter 0 of constructor required a bean of type
'com.azure.storage.blob.BlobServiceClient'
that could not be found.
```

How to analyze it:

1. Is the Blob starter on the resolved runtime classpath?
2. Is `spring-cloud-azure.version` compatible with Spring Boot?
3. Does the artifact name match the chosen release line?
4. Was the starter's auto-configuration excluded or disabled?
5. Are account/endpoint properties binding properly?
6. Is there a custom Bean override or multiple Beans?
7. Is an active profile preventing configuration from loading?
8. Are other condition annotations unmet?
9. Does `@ComponentScan` include your service?
10. Only after the Bean exists should you check RBAC/networking when invoking the SDK.

### Spring Boot Conditions Report

In a lab, you can enable startup debugging:

```properties
debug=true
```

Spring Boot can print the **conditions evaluation report** showing auto-config matches and non-matches. Do not enable broad debug logs in Production without reviewing logging risks. With Actuator, `/actuator/conditions` can be helpful, but protect the endpoint with auth/roles—never expose it publicly to the Internet.

## 25. Inspecting Maven Resolved Dependencies

When working in an authorized **lab project**, the commands below read build metadata:

```bash
mvn help:effective-pom

mvn dependency:tree

mvn dependency:tree -Dincludes=com.azure.spring,com.azure

mvn dependency:analyze
```

### Explanation

- **effective-pom:** Maven configuration after parent/profile/dependencyManagement inheritance.
- **dependency:tree:** actual dependency graph and resolved versions.
- **includes:** narrows output to find Azure/Spring packages.
- **dependency:analyze:** helps detect declared-but-unused or used-but-undeclared dependencies, with limitations around reflection/auto-configuration.

In a multi-module project, inspect the **exact module being deployed**. A dependency visible in the parent BOM does not mean every module includes it at runtime.

### What to Look for in the Tree

```text
com.azure.spring:spring-cloud-azure-starter-storage-blob:jar:<resolved>
  +- com.azure:azure-storage-blob:jar:<resolved>
  +- com.azure:azure-core:jar:<resolved>
  ...
```

Compare resolved versions against the chosen BOM. If an Azure artifact is overridden by a direct version or another BOM, determine **why** before fixing it.

## 26. Inspecting Gradle runtimeClasspath

In a lab Gradle project:

```bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency azure-core \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-cloud-azure \
  --configuration runtimeClasspath
```

On Windows, use `gradlew.bat` depending on your shell.

`dependencyInsight` shows why Gradle selected a specific version and which constraints/requests influenced it.

### Important Notes

- `compileClasspath` and `runtimeClasspath` can differ.
- Dependency constraints, `platform`, and `enforcedPlatform` have distinct semantics.
- `resolutionStrategy.force` can mask conflicts rather than properly resolving them.
- A clean test classpath does not prove the production runtime is clean.
- Gradle dependency locking (when configured) records resolved versions, though locks must still be upgraded deliberately.
- After changing a BOM, re-inspect the graph instead of looking only at the build script.

**Do not force an Azure Core version "to silence warnings"** without verifying compatibility across every Azure SDK on the classpath.

## 27. BOM Import Order and Managing Overrides

In Maven, parent/inherited dependencyManagement, direct entries, and imported BOMs follow specific precedence rules; **multiple imported BOMs can manage the same artifact**.

Suppose a project uses:

```xml
<dependencyManagement>
    <dependencies>
        <!-- Spring Cloud BOM, if required components are used -->
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_CLOUD_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>

        <!-- Spring Cloud Azure BOM -->
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

**There is no single right order for every release train combination**. Follow the compatibility guide of your chosen Spring Cloud Azure and Spring Cloud releases, then verify the effective POM. In Maven, the order of imported BOMs can determine the selected version when declarations overlap; direct dependencyManagement entries also carry higher precedence.

### Deliberate Overrides

Sometimes a library must be overridden due to a CVE or SDK requirement. Process:

1. Confirm the new version genuinely fixes the issue.
2. Identify artifacts that depend on its API.
3. Run compatibility tests (unit/integration/contract).
4. Write an ADR stating the reason, owner, and expiration date of the override.
5. Limit the override to the narrowest scope; do not force the whole ecosystem.
6. Remove the override once the BOM catches up.
7. Regenerate the SBOM and re-run security scans.

## 28. Multi-Module Maven and Organizing Dependency Management

A repository with multiple modules:

```text
company-parent
  |
  +-- api-gateway
  +-- order-api
  +-- billing-worker
  +-- notification-worker
```

You can place **shared dependencyManagement in the parent**:

```xml
<properties>
    <spring-cloud-azure.version>REPLACE_WITH_COMPATIBLE_SCA_VERSION</spring-cloud-azure.version>
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
```

Modules only add the dependencies they actually need:

```xml
<!-- order-api: Blob Storage -->
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Benefits:

- A single place to manage the Spring Cloud Azure version.
- Avoids four different Azure SDK versions inside one repository.
- Easier to evaluate platform-wide upgrades.

However, avoid **adding starters to the parent's `<dependencies>`**, which forces every child module to pull in Azure clients it does not use. Put version management in parent `dependencyManagement`, and declare dependencies **per module's actual needs**.

## 29. Gradle Version Catalog and Convention Plugins

For multi-module Gradle builds, you can use a version catalog (e.g., `gradle/libs.versions.toml` in a learning project) and convention plugins to manage versions, plugins, and dependency policies.

Illustrative example:

```toml
[versions]
spring-boot = "REPLACE_WITH_APPROVED_BOOT_VERSION"
spring-cloud-azure = "REPLACE_WITH_COMPATIBLE_SCA_VERSION"

[libraries]
spring-cloud-azure-bom = {
  module = "com.azure.spring:spring-cloud-azure-dependencies",
  version.ref = "spring-cloud-azure"
}
azure-blob-starter = {
  module = "com.azure.spring:spring-cloud-azure-starter-storage-blob"
}
```

Used in Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation(platform(libs.spring.cloud.azure.bom))
    implementation(libs.azure.blob.starter)
}
```

**This is a configuration pattern**; synchronize aliases with the actual accessors Gradle generates and your convention plugins. Not every project already uses a catalog; do not add tooling solely to add layers to a small application.

### Useful Policies

- Propose dependency releases via PRs and CI.
- Never use dynamic `+` or `latest.release` versions in Production.
- Never change the BOM directly on the main branch without validation.
- Track dependencies pulled in transitively or via auto-configuration.
- Maintain SBOMs and repository access controls.

## 30. Prioritizing Security and Supply Chain

Even a compatible dependency set can contain vulnerabilities. Design a lifecycle:

```text
Developer updates BOM / starter
            |
            v
Resolve effective classpath
            |
            v
SBOM + vulnerability/license scan
            |
            v
Unit + integration + authentication tests
            |
            v
Canary deployment
            |
            v
Monitor, approve or rollback
```

### Things to Check

- Vulnerabilities in Azure SDK/Spring Framework/Jackson/Reactor/Netty.
- Severity, **exploitation conditions**, and real impact on your application.
- Package provenance, artifact repositories, and checksum/signature policies.
- Licenses and obligations.
- End-of-support versions.
- Unmaintained transitive libraries.
- Dependency confusion and repository trust.
- Secrets accidentally packaged into artifacts/images.

### Tools

You can use OWASP Dependency-Check, your organization's SCA platform, CycloneDX SBOM generation, Dependabot/Renovate, or approved equivalents. Scanners can emit false positives; **do not blindly force a new version just because a CVE scanner flags one**. Evaluate the fix, compatibility, and regression risk.

## 31. Dependency Locking and Reproducible Builds

A reproducible build requires controlling:

1. Spring Boot and Spring Cloud Azure BOM versions.
2. Maven/Gradle plugin versions.
3. JDK/toolchain.
4. Dependency repositories and cache policies.
5. No dynamic/range versions in Production.
6. Test dependencies and optional classifiers.
7. Generated code and annotation processors.
8. Gradle lockfiles or equivalent mechanisms where available.
9. Container base images and runtime JDK versions.
10. SBOMs and build provenance.

**A BOM is not a lockfile**. A BOM manages many versions, yet if the project declares dependencies outside the BOM, uses dynamic versions, or applies resolution constraints, the classpath can still drift from expectations.

### Maven vs. Gradle Differences

Maven normally resolves declared versions and specific mediation rules without a built-in lockfile equivalent to Gradle dependency locking. Do not claim "importing a BOM guarantees identical builds from today until next year" when repositories, plugins, metadata, or dependency scopes can still change.

## 32. Unit Tests, Integration Tests, and Cloud Smoke Tests

Three testing layers:

| Layer | Objective | Azure resource needed? |
|---|---|---|
| **Unit tests** | Verify business logic and config binding/beans using mocks. | Usually no. |
| **Integration tests** | Verify SDK/client/serialization/auto-config against a lab environment or suitable emulator. | Depends on the service. |
| **Cloud smoke tests** | Verify identity, data-plane RBAC, DNS, and real resources post-deploy. | Yes, in an approved environment. |

### Unit Test Example Without Calling Azure

```java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class OrderKeyTest {

    @Test
    void stableMessageIdIsDerivedFromBusinessOperation() {
        String orderId = "ORD-LAB-1042";
        String eventType = "OrderCreated";

        String messageId = eventType + ":" + orderId;

        assertEquals("OrderCreated:ORD-LAB-1042", messageId);
    }
}
```

Additional things to test:

- Spring context successfully creates Beans with lab config.
- Key Vault property source works under the assigned role.
- Blob SDK reads/writes to the lab container per permissions.
- Service Bus sender/receiver works with a lab test queue/entity.
- No credentials leak into logs.
- Retries, idempotency, and backoff behave properly.
- Distinct dev/staging/prod configurations do not point to the wrong endpoint.

### Emulators and Test Doubles

Azurite can exercise several Blob Storage APIs, but **it does not fully replicate Azure Storage authentication, RBAC, networking, or every feature**. For Key Vault and other integrations, do not assume a production-equivalent emulator always exists. Use mocks/stubs for unit tests, and run **integration smoke tests against authorized real resources** to validate identity and networking paths.

## 33. Spring Cloud Azure Configuration and Spring Profiles

A profile-based configuration:

```yaml
# application.yml
spring:
  application:
    name: order-api

app:
  storage:
    container: ${APP_STORAGE_CONTAINER:documents-lab}
```

In `application-local.yml`, you can point to Azure lab resources using developer identity **with no secrets**.

In `application-prod.yml`, configure only non-secret resource names/settings, obtaining identity from the managed runtime. Avoid putting access keys directly in profile files because those files enter JARs or repositories.

**Do not use Spring profiles as a security boundary.** If someone accidentally runs the `prod` profile on a personal laptop while holding production credentials, data can still be accessed. IAM and network controls must be independent of profiles.

### Configuration Validation

You can define `@ConfigurationProperties` with validation to catch missing `container` or namespace values at startup. Still, having a non-empty property string does not prove the Azure resource exists or permissions are valid.

## 34. Networking, Private Endpoints, and DNS

Correct dependencies will not fix network failures. A Spring Boot app on Azure may rely on:

```text
Spring Boot runtime (VNet-integrated)
    |
    +-- DNS resolves Key Vault private endpoint
    |
    +-- DNS resolves Blob Storage private endpoint
    |
    +-- Azure Service Bus namespace/AMQP connectivity
    |
    +-- Entra identity token endpoint as supported
```

Verify:

- Does the service support Private Endpoints/private access in your tier/region?
- Do VNet/subnet/NSG/UDR/Azure Firewall rules allow the required traffic?
- Are Private DNS zones linked properly to the VNet and endpoints?
- Do hostnames/FQDNs and certificate/TLS validation succeed?
- Does Service Bus transport use AMQP/TLS or WebSockets per config and network rules?
- Do proxies or environments block outbound identity/token calls?
- Do Staging and Production use separate DNS setups?
- Do service endpoints/firewall policies actually permit the identity/resource network?
- Are timeouts caused by networking or by quotas/busy servers?
- Could logs accidentally capture SAS tokens or connection strings?

**Do not change Azure SDK versions to fix an unresolvable DNS name**; and never open a firewall to the entire Internet to hide a configuration mistake.

## 35. Startup and Secret Refresh: Designing the Right Lifecycle

Some Azure dependencies and configuration sources initialize **as soon as the Spring ApplicationContext starts**.

```text
Spring Boot startup
     |
     v
Resolve property sources (local/env/Key Vault/App Config)
     |
     v
Bind properties and create beans
     |
     v
Start service
```

Risks:

- Transient Key Vault failures prevent the app from starting.
- Newly assigned roles have not propagated yet, causing 403s.
- Unexpected property source precedence.
- A secret rotates, yet existing singleton Beans keep the old value.
- A client built at startup reads the wrong namespace.
- Asynchronous refresh breaks configs that require atomic transitions.

### How to Handle It

1. Classify configs as **mandatory** vs. **optional**.
2. Bound startup timeouts and retries.
3. Choose an explicit failure policy.
4. Design for secret rotation/restarts or supported refresh mechanisms.
5. Do not let cached credentials live indefinitely after permissions are revoked.
6. Test cold start when Key Vault/App Configuration is unreachable.
7. Monitor startup latency and config retrieval failures.
8. Maintain a rollback plan if a config update breaks schemas.

**Do not assume starters automatically refresh every `@Value` or singleton bean** after rotation. Verify the official semantics of your version.

## 36. Observability, Health, and Telemetry Dependencies

Spring Boot Actuator can expose health and metrics, though you must be careful when publishing endpoints and defining probes.

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Azure Monitor/Application Insights/OTel integration has different libraries, instrumentation, and configuration styles by version and runtime. Pick one consistent observability pipeline instead of stacking multiple agents that emit duplicate spans.

Signals to measure:

| Signal | Why it matters |
|---|---|
| Boot startup success/failure | Dependency/Bean/config errors. |
| Azure credential failure count | Identity or token-chain issues. |
| Key Vault lookup latency/failures | Impact on startup or runtime? |
| Blob operations p95/403/404/429 | Storage performance and RBAC. |
| Service Bus send/receive errors | Delivery and namespace/network health. |
| JVM heap/threads/GC | Azure client and backend performance. |
| Retry counts/throttling | Quotas/capacity and cost. |
| Deployment/build metadata | Traceability to BOM/SDK/version. |
| Security alerts | Credential/log leaks and vulnerability status. |
| Cost per request/outcome | Budget governance. |

**Do not publicly expose `/actuator/env`, `/actuator/beans`, or sensitive endpoints**; expose only what is needed behind authentication/authorization. Metric labels must never contain PII or raw connection strings.

## 37. Optimizing Dependency Footprint and Runtime Cost

Adding many starters affects more than JAR size; it can impact:

- Startup/cold start time.
- Class count and memory footprint.
- Auto-configuration evaluation overhead.
- Number of Beans, threads, and HTTP clients.
- Container image build times and vulnerability surface.
- CI dependency downloads and caching.
- AOT/native-image compatibility if used.
- Debugging complexity and library versions to maintain.

However, **removing dependencies by guesswork** can strip runtime classes loaded via reflection or Spring autoconfig metadata. Combine dependency analysis **with tests** before deleting anything.

### Avoid Premature Optimization

An app reading Blobs 100 times a day does not need a hand-rolled SDK HTTP pipeline just to trim a few MB from the JAR when the starter already handles credentials/config clearly and is well supported. Conversely, a short-lived serverless function with a strict cold-start SLO may benefit from pulling only the minimal SDK.

Decide based on **measurement**, not dependency count.

## 38. Common Error: Azure Core / Reactor Conflict

**Symptom:** after adding Service Bus and Blob, the app throws `NoSuchMethodError` in `com.azure.core.*` or `reactor.*`.

### Investigation

1. Capture the stacktrace and Spring Boot/Spring Cloud Azure versions.
2. Inspect the effective POM/dependency tree or Gradle `runtimeClasspath`.
3. Identify the resolved versions of Azure Core, Identity, Netty/Reactor.
4. Look for direct SDK versions or `resolutionStrategy.force`.
5. Check whether Spring Cloud Azure starters from **different majors** were mixed.
6. Check whether another BOM overrides Azure artifacts.
7. Verify against the official compatibility matrix.
8. If the issue started in a dependency-bump PR, diff the dependency graph before/after.
9. Verify the packaged JAR/image actually reflects the new build.
10. Run regression integration tests on the target JDK/runtime.

### Remediation

- Align all starters onto the same supported release/BOM.
- Remove unnecessary overrides.
- If an override is mandatory due to a CVE, pick a version with verified compatibility.
- Upgrade release trains using migration guides rather than bumping a single loose JAR.
- Use canary rollouts and rollback readiness.

**Never run `mvn clean` mechanically and declare the problem fixed**. Cleaning only removes build outputs; it does not repair a broken dependency graph.

## 39. Common Error: Key Vault Startup 403

**Symptom:**

```text
Failed to resolve Key Vault property source
403 Forbidden
```

### Checklist Sequence

1. Verify the Spring Cloud Azure Key Vault Secrets starter version.
2. Check the Vault endpoint/URI and active profile.
3. Identify the app's actual principal (managed identity vs. developer).
4. Does the Vault use Azure RBAC or access policies?
5. Does the principal have **read secret** permission at the right scope?
6. Are policies, firewalls, or Private Endpoints blocking the data plane?
7. Does the secret exist, is it enabled, and are its name/version correct?
8. Has a newly assigned role finished propagating?
9. Do property-source naming/ordering settings match the starter version?
10. Are logs inadvertently printing secret values?

### Remediation

- Grant approved least-privilege permissions.
- Fix endpoint/DNS/networking if connectivity fails.
- Align naming and configuration properties.
- Re-verify startup in lab/staging.
- Never fall back to hard-coded secrets in source.

**A 403 is not automatically a dependency bug**. Version alignment should still be checked, but prioritize identity/RBAC evidence first.

## 40. Common Error: Service Bus Client Connects but Cannot Send

**Symptom:** Spring context starts cleanly, but publishing `OrderCreated` is rejected or times out.

### Investigation

1. Are the namespace and queue/topic name accurate?
2. Are you using the base starter, JMS, Integration, or Stream binder?
3. Does the principal hold the **Azure Service Bus Data Sender** role?
4. Does the Service Bus namespace have matching network policies/firewalls?
5. Is AMQP/TLS/outbound networking or WebSocket transport properly configured?
6. Is the entity disabled or over quota/capacity?
7. Does the SDK retry policy use sensible backoff?
8. Is the exception/status due to authentication, authorization, network, or busy state?
9. Are MessageId and business idempotency stable?
10. Can you test against a lab queue/entity?

### Remediation

- Separate transport issues from permission errors.
- Adjust namespace/entity names, roles, or networking based on evidence.
- Use bounded retries to avoid duplicating business events.
- Never publish real messages inside unit tests.
- Track send success separately from downstream processing.

## 41. Upgrading Spring Boot / Spring Cloud Azure Safely

A major/minor upgrade can affect:

- Java baseline, Spring Framework/Jakarta APIs.
- Spring Boot auto-configuration metadata.
- Spring Cloud release train compatibility.
- Azure SDK HTTP/Identity dependencies.
- Property names, default values, and client beans.
- Key Vault configuration loading/refresh.
- Service Bus integration APIs.
- Test annotations and lifecycle.
- Observability and Spring Actuator.
- Authentication behavior even when security permissions stay unchanged.
- Container base images/runtimes.

### Upgrade Runbook

1. Snapshot current versions and the dependency tree.
2. Consult the compatibility matrix and release notes of the target line.
3. Select aligned Boot/Spring Cloud/Spring Cloud Azure versions.
4. Update BOM/plugin versions in a cleanly scoped PR.
5. Migrate deprecated or renamed properties.
6. Remove direct SDK overrides only with supporting evidence.
7. Run compile/unit/integration tests on the target JDK.
8. Test managed identity, Key Vault, Blob, and Service Bus in staging.
9. Compare startup latency, 429s, 403s, memory, and throughput.
10. Generate an SBOM and run security/license scans.
11. Deploy as a canary, observe, and roll back on regression.
12. Record an ADR/version inventory so future maintainers know the rationale.

**Never upgrade Spring Boot major + every Azure starter + network configuration simultaneously without a plan to isolate root causes.**

## 42. Migrating from Legacy Starters or Self-Managed Azure SDKs to Spring Cloud Azure

Long-lived projects may contain:

- Artifact coordinates/namespaces from older Spring Cloud Azure generations.
- Legacy Azure Spring Boot starter packages.
- Direct SDK dependencies pinned individually.
- Spring Boot 2.x/Java 8/11 alongside Spring Boot 3.x/Jakarta migrations.
- Code constructing clients with connection strings.
- Service Bus JMS/binder code from an older integration model.

### Migration Approach

1. Inventory **current libraries and their purposes**, not just artifact names.
2. Pick a supported target Spring Boot/Cloud/Azure line.
3. Read official migration notes for that exact version pair.
4. Update coordinates when required by the target release.
5. Import the BOM and remove individual versions now managed by the BOM.
6. Replace connection strings with identity/passwordless auth where supported.
7. Update property keys and Spring bean injections to match new APIs.
8. Test message semantics, concurrency, retries, and secret refresh.
9. Confirm the runtime classpath does not contain overlapping old and new starters.
10. Deploy to staging and observe before Production.

Do not run a blind "find-and-replace artifact name" and assume all JMS/Stream/Storage logic remains compatible.

## 43. Hands-On Exercise: Adding the BOM and Two Starters Properly

**Context:** the development team has a Spring Boot project `order-api-lab` with no Azure integration yet. It needs to read a lab Key Vault secret and instantiate a Blob Storage client; the exercise verifies both classpath integrity and access permissions.

### Simulated Environment

| Component | Value |
|---|---|
| Java | JDK supported by the chosen release pair. |
| Spring Boot | Version confirmed in the compatibility matrix. |
| Spring Cloud Azure | Version compatible with Boot/Cloud. |
| Build | Maven or Gradle, choose one. |
| Key Vault | `kv-orders-lab`, containing non-sensitive lab data. |
| Storage account | `storderslabexample` (must substitute a real name if using Azure). |
| Blob container | `documents-lab`. |
| Local identity | Developer principal granted lab permissions. |
| Cloud identity | Managed identity/user-assigned identity granted permissions. |
| Do not do | Do not put connection strings/keys in source; do not modify Production. |

### Tasks

1. Record the selected versions of Java, Spring Boot, Spring Cloud (if used), and Spring Cloud Azure.
2. Check the compatibility matrix and record **evidence** showing why they work together.
3. Import `spring-cloud-azure-dependencies` in `dependencyManagement` or via Gradle platform/plugin.
4. Add `spring-cloud-azure-starter-keyvault-secrets` without an individual version.
5. Add `spring-cloud-azure-starter-storage-blob` without an individual version.
6. Add `spring-cloud-azure-starter-servicebus` only if extending the lab for message queues.
7. Inspect the effective POM or Gradle `runtimeClasspath` and record resolved Azure SDK versions.
8. Check whether any artifact was unexpectedly overridden.
9. Configure the vault endpoint/account name via config/env matching your starter version.
10. Authenticate as the authorized developer identity; do not create secrets in code.
11. Assign Key Vault Secrets Reader/User per lab data-plane requirements.
12. Assign Storage Blob Data Reader/Contributor depending on operations.
13. Run the Spring context smoke test in the lab project.
14. Verify the Blob SDK Bean/Client is created properly.
15. Test reading a non-sensitive lab Key Vault secret.
16. Run a safe Blob operation allowed by the assigned role.
17. Intentionally revoke data-plane permission in the lab environment, observe the 403 error, and distinguish it from dependency errors.
18. Deliberately set an invalid account/endpoint and recognize resource/network errors.
19. On a controlled test branch, add an incompatible direct Azure SDK version and inspect the dependency graph; **do not deliberately distribute CVE/vulnerable artifacts**.
20. Restore BOM alignment and re-run tests.
21. Generate an SBOM/library version report.
22. Write runbooks for startup 403 and `NoSuchMethodError`.
23. Estimate lab environment costs including Key Vault, Storage, compute, and logging if applicable.
24. Clean up lab resources per permissions; never delete shared resources.

### Deliverables

- A `pom.xml` or `build.gradle(.kts)` with the BOM and minimal starters.
- A sourced and approved version matrix.
- Dependency tree/effective POM or Gradle `dependencyInsight` output.
- Configuration free of keys/secrets.
- Unit/context smoke tests and integration test evidence.
- Results from the 403 test proving separation of RBAC vs. dependency issues.
- SBOM and justified list of any overrides.
- Security, logging, and budget checklist.

## 44. Practical Troubleshooting Exercises

**Scenario A:** `mvn dependency:tree` shows `spring-cloud-azure-starter-storage-blob` coming from a BOM, yet a submodule declares a different `azure-core` version.

Question: how do you fix it?

**Guidance:** identify the direct override and resolved version, comparing against the supported BOM. Do not force `azure-core` to "latest"; align everything consistently, test, and document the rationale.

**Scenario B:** the app has all dependencies declared yet fails with `No qualifying bean of type BlobServiceClient`.

**Guidance:** inspect the actual starter on `runtimeClasspath`, the conditions report, config binding, custom Beans, version alignment, and active profiles. Only after the Bean appears should you inspect the storage data plane.

**Scenario C:** the Bean exists, yet Blob reads return 403.

**Guidance:** this points to data-plane permissions or authentication, not merely dependencies. Check principal, role, scope, account, and networking.

**Scenario D:** a Key Vault secret rotates, yet `@Value` in a singleton Bean keeps the old value.

**Guidance:** verify the refresh contract, lifecycle, caching, and whether your starter version requires a restart, rebind, or refresh event.

**Scenario E:** intending to use the Spring Cloud Stream binder, someone adds the base Service Bus starter and cannot find the binder.

**Guidance:** pick the right integration artifact/binder, Spring Cloud release train, bindings config, and compatibility. Do not treat all Service Bus starters as interchangeable.

**Scenario F:** upgrading from an older Spring Boot version to a newer one by changing only the Boot parent.

**Guidance:** plan upgrades across Spring Cloud/Spring Cloud Azure along with the JDK/framework, migrate properties, run compile/integration/security tests, and prepare a rollback plan.

## 45. Pre-Production Checklist

**Dependencies and versioning**

- [ ] Spring Boot/Cloud/Azure/JDK versions verified as compatible.
- [ ] One single source manages Azure artifact versions via the appropriate BOM.
- [ ] No individual versions pinned on starters without justification.
- [ ] No dynamic versions or `latest.release` in Production.
- [ ] Dependency tree/effective POM reviewed.
- [ ] No overlapping old and new starters.
- [ ] No unused starters triggering unintended auto-config.
- [ ] Every exclusion/override has an ADR and tests.
- [ ] SBOM, vulnerability/license scans, and upgrade cadence established.
- [ ] JDK, build plugins, and container images are versioned.

**Identity and configuration**

- [ ] No connection strings/keys in source, Git, or logs.
- [ ] Managed identity/workload identity and data-plane roles scoped properly.
- [ ] Key Vault/property sources configured for the actual starter version.
- [ ] Config precedence and secret refresh tested.
- [ ] No mix-ups between dev/staging/prod resources.
- [ ] Storage/Service Bus/App Config endpoints verified.
- [ ] Private DNS/TLS/networking verified from the real runtime.
- [ ] Client Beans clearly disambiguated when multiple accounts/namespaces exist.
- [ ] Sensitive Spring Actuator/diagnostic endpoints not exposed publicly.

**Quality and operations**

- [ ] Build/unit/context smoke/integration tests PASS on the target JDK.
- [ ] Cloud smoke tests validate real identity and data plane.
- [ ] Retries/backoff/idempotency designed deliberately.
- [ ] Observability tracks 403s, 429s, latency, startup, and build versions.
- [ ] Canary/rollback tested when upgrading major/minor BOM versions.
- [ ] Runbooks exist for linkage, config, identity, and network failures.
- [ ] Budget/quota alerts and clear ownership configured for Azure resources.
- [ ] No assumption that a BOM alone solves security or business correctness.

## 46. Self-Check Questions

**Question 1.** Is the Spring Cloud Azure BOM a runtime client library?

**Answer:** No. A BOM manages versions; it does not add Azure service dependencies without an actual dependency declaration.

**Question 2.** Why should you use `spring-cloud-azure-dependencies`?

**Answer:** To align versions across Spring Cloud Azure artifacts and the Azure SDK dependencies managed by the BOM for that release.

**Question 3.** Can you import the BOM and skip adding the Blob starter?

**Answer:** No. The BOM only manages versions; you must add the starter or direct SDK if you need Blob.

**Question 4.** Are the Spring Boot BOM and Spring Cloud Azure BOM the same?

**Answer:** No. They manage different sets of artifacts and must be compatible with each other.

**Question 5.** Why not pick the latest individual version of every dependency?

**Answer:** Libraries require compatible APIs/ABIs and transitive dependencies, so arbitrary mixing can cause linkage errors.

**Question 6.** When do you need to add the Spring Cloud BOM?

**Answer:** When using Spring Cloud components and their corresponding release train, following the compatibility matrix with Boot and Spring Cloud Azure.

**Question 7.** Does Maven `dependencyManagement` automatically download every dependency?

**Answer:** No. It only governs resolution when a dependency is declared directly or pulled transitively.

**Question 8.** What are the Maven coordinates of the Spring Cloud Azure BOM?

**Answer:** groupId `com.azure.spring`, artifactId `spring-cloud-azure-dependencies`.

**Question 9.** Why omit versions on individual Azure starters when managed by the BOM?

**Answer:** To prevent accidental overrides and maintain a single consistent version set.

**Question 10.** Which Maven commands inspect the version graph?

**Answer:** `mvn dependency:tree`; use `mvn help:effective-pom` to inspect dependency management after inheritance.

**Question 11.** In Gradle, which command shows why a specific version of `azure-core` was chosen?

**Answer:** `dependencyInsight --dependency azure-core --configuration runtimeClasspath`.

**Question 12.** Are Gradle `platform(...)` and the `io.spring.dependency-management` plugin identical?

**Answer:** No. Their constraints and precedence rules differ; inspect the resolved graph.

**Question 13.** Does adding the Key Vault starter automatically let the app read any secret?

**Answer:** No. It still needs the endpoint, identity, data-plane permissions, and proper networking.

**Question 14.** Why is a 403 error not automatically fixed by upgrading the BOM?

**Answer:** A 403 usually involves authentication, authorization/permissions, or service policies rather than Java linkage.

**Question 15.** Can Developer Azure CLI identity be used in a local lab?

**Answer:** Yes, when permitted and supported by the credential chain; Production should rely on a clearly configured managed/workload identity.

**Question 16.** What does `NoSuchMethodError` typically indicate?

**Answer:** An API/ABI mismatch between compile-time and runtime versions, usually due to classpath/transitive conflicts.

**Question 17.** Is adding the base Service Bus starter equivalent to the JMS starter?

**Answer:** No. JMS, Integration, and Spring Cloud Stream have separate contracts and artifacts.

**Question 18.** Does having a `BlobServiceClient` Bean prove Blob uploads are permitted?

**Answer:** No. You also need data-plane roles, the right account/container, and network connectivity.

**Question 19.** Why does enabling managed identity not grant all Azure permissions?

**Answer:** The identity must still be assigned RBAC/data-plane roles at the proper resource/scope.

**Question 20.** Should App Configuration and Key Vault be used interchangeably for every config?

**Answer:** No. App Configuration fits non-secret settings/feature flags; Key Vault centralizes secrets, keys, and certificates.

**Question 21.** Does rotating a Key Vault secret automatically update every singleton Bean?

**Answer:** Do not assume so. Check refresh semantics and Bean lifecycles for your starter version.

**Question 22.** Should you put a connection string in `application-prod.yml` to bypass identity errors?

**Answer:** No. Prefer managed identity/Key Vault and fix the underlying RBAC/network issue.

**Question 23.** Why inspect `runtimeClasspath` rather than only `compileClasspath`?

**Answer:** Runtime versions/classes can differ from compile classpath; linkage errors surface at execution time.

**Question 24.** Is a BOM a lockfile guaranteeing strictly reproducible builds?

**Answer:** No. Builds also depend on plugins, repositories, constraints, and other dependency declarations.

**Question 25.** When a CVE appears in a transitive Azure SDK dependency, should you `force` any newer version to pass a scan?

**Answer:** No. Evaluate the remediation, compatibility, and run tests.

**Question 26.** Why avoid putting every Azure starter in parent `<dependencies>` of a multi-module repo?

**Answer:** It forces every module to pull unnecessary libraries/auto-config; manage versions in the parent and declare starters only in modules that use them.

**Question 27.** Are unit tests enough to prove managed identity works in the Azure runtime?

**Answer:** No. You need cloud smoke/integration tests under the real environment's identity and network.

**Question 28.** Does adding the Blob starter create an Azure Storage account?

**Answer:** No. Resource provisioning, RBAC, networking, and costs must be managed separately.

**Question 29.** Why use a canary when upgrading a Spring Cloud Azure release train?

**Answer:** Auto-configuration, property names, SDK behavior, and latency can change even when lab compilation and tests PASS.

**Question 30.** What is the core principle of managing dependencies with Spring Cloud Azure?

**Answer:** **Select a supported combination of Java/Spring Boot/Spring Cloud/Spring Cloud Azure, import the BOM, add only the minimal required starters/SDKs, inspect the resolved dependency graph, test identity/RBAC/networking, and upgrade in a controlled manner.**

**Summary:** **Spring Cloud Azure** helps integrate Spring Boot with Azure via starters and the `spring-cloud-azure-dependencies` BOM. The BOM manages versions, yet it **does not replace a compatibility matrix, classpath inspection, Azure resource provisioning, or data-plane authorization**. A reliable deployment properly manages **Java/Spring Boot/Cloud/Azure SDK alignment, Maven/Gradle resolution, managed identity/Key Vault, tests/CI, SBOM/security scans, observability, and migration runbooks**. Once you distinguish **dependency issues from configuration, permission, and network errors**, your team can deploy Spring Boot apps to Azure safely, upgrade smoothly, and keep costs under control.

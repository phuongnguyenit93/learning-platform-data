# Spring Cloud Azure, Azure SDK for Java, and Starter Scope

In a Spring Boot application deployed on Azure, there are two common ways to communicate with cloud services: using the **Azure SDK for Java** directly or using **Spring Cloud Azure** to integrate the SDK into Spring's configuration and bean management mechanisms. Understanding the difference helps you choose just enough dependencies, configure authentication consistently, and avoid confusing auto-configuration conveniences with the actual capabilities of Azure services.

This lesson belongs to the **Azure Platform** chapter within the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing how to connect Spring Boot with managed services on AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; focusing on identity, access control, storage, messaging, data, secrets, integration testing, and cross-provider comparison.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain the distinct roles of the Azure SDK for Java, Spring Cloud Azure, and a Spring Cloud Azure starter.
2. Identify the appropriate starter group for Blob Storage, Service Bus, Event Hubs, Key Vault, Cosmos DB, App Configuration, and Microsoft Entra ID integration.
3. Configure dependency management to reduce version conflicts and use Azure identity instead of embedding keys in source code.
4. Implement Blob Storage integration in two ways: Spring Cloud Azure auto-configuring the client or Azure SDK creating the client directly.
5. Define the boundary of responsibilities between the application, library, IAM/RBAC system, cloud resources, and integration testing.

## 2. Three Layers to Distinguish

| Component | Primary Responsibility | Typical Unit | When to Choose |
| --- | --- | --- | --- |
| **Azure SDK for Java** | Calls data/management APIs of Azure services; manages HTTP pipeline, authentication, retries, and client objects per SDK API | Libraries **azure-storage-blob**, **azure-messaging-servicebus**, **azure-identity** | Plain Java applications or when fine-grained SDK control is needed, including inside Spring Boot |
| **Spring Cloud Azure** | Connects Azure SDKs to the **Spring Boot auto-configuration** model, externalized configuration, dependency injection, and Spring ecosystem integrations | Modules under group **com.azure.spring** | Spring Boot projects wanting to reduce boilerplate configuration code and follow Spring conventions |
| **Spring Cloud Azure starter** | Dependency bundle for a specific integration need, typically pulling in auto-configuration along with the required SDKs | **spring-cloud-azure-starter-storage-blob** | When the target service or integration style is clearly identified |

The first two layers are not mutually exclusive. **Spring Cloud Azure uses the Azure SDK underneath**: when injecting a **BlobServiceClient** from Spring, the application still invokes Azure SDK APIs. A starter handles registering, configuring, and managing the client; it does not create a Blob container, Service Bus namespace, Cosmos DB account, or grant Azure permissions on behalf of the operations team.

~~~mermaid
flowchart TD
    A[REST API / Spring Boot service] --> B[Azure client bean auto-configured by Spring Cloud Azure]
    B --> C[Azure SDK for Java]
    C --> D[azure-identity / TokenCredential]
    C --> E[Azure Blob / Service Bus / Cosmos DB ...]
    F[application.yml + environment variables] --> B
    G[Microsoft Entra ID and Azure RBAC] --> D
    D --> E
~~~

**Boundary summary:** the starter decides *how to wire the SDK into Spring*; the Azure SDK decides *how to call the service*; Azure identity/RBAC and infrastructure decide *whether the call is permitted and can connect*.

## 3. What Does Azure SDK for Java Include?

Azure SDK for Java is a collection of service-specific libraries, not a single monolithic client for all of Azure.

- **azure-core**: shared components such as pipeline, HTTP, responses, policies, errors, and retry mechanisms.
- **azure-identity**: **TokenCredential** implementations, such as **DefaultAzureCredential**, **ManagedIdentityCredential**, and **ClientSecretCredential**.
- **azure-storage-blob**: **BlobServiceClient**, **BlobContainerClient**, **BlobClient**, and async variants for working with objects in Blob Storage.
- **azure-messaging-servicebus**: sending/receiving messages, handling queues or topics/subscriptions.
- **azure-messaging-eventhubs**: high-throughput event streaming via Event Hubs.
- **azure-security-keyvault-secrets**: **SecretClient** for Azure Key Vault Secrets.
- **azure-cosmos**: client for interacting with Azure Cosmos DB.

Most SDK clients offer **synchronous** and/or **asynchronous** types. Choose the client based on the execution model: a standard Spring MVC application can use a synchronous client; a non-blocking processing pipeline needs to evaluate the async client and backpressure mechanisms. Do not call blocking SDK operations directly on the WebFlux event loop.

SDK clients are typically designed to be **reusable**, so their lifecycle should be managed centrally (as a singleton/bean) rather than creating a new client per HTTP request. The HTTP pipeline, connections, retry policies, and logging should be observed according to the specific SDK and version in use.

### Authentication with TokenCredential

**DefaultAzureCredential** tries supported credential sources in the runtime environment, such as appropriate environment variables, workload identity, managed identity, or developer tool sign-in sessions. Exact sources and order may vary depending on the SDK version and platform.

- **Development machine:** developers can sign in via the Azure CLI and grant appropriate data permissions to their identity.
- **Azure runtime:** prefer managed identity or workload identity when supported by the environment, assigning roles with the narrowest possible scope.
- **CI/CD:** use federated identity credentials if supported by the infrastructure; avoid storing long-lived client secrets.
- **Production:** understand which identity is actually selected. The credential chain is convenient during development but can pick the wrong identity if the environment contains multiple credential sources.

Successful authentication only indicates that Azure has recognized the principal. **Authorization** still depends on RBAC or each service's access policies. For example, signing in successfully does not automatically allow uploading blobs.

## 4. Scope of Spring Cloud Azure Starters

Artifact names may change or be split across version lines. The table below lists common starters in modern Spring Cloud Azure; before adding a dependency, check the **Spring Boot / Spring Cloud Azure compatibility matrix** and the documentation for the version you are using.

| Starter (group **com.azure.spring**) | Scope Covered | What Not to Assume |
| --- | --- | --- |
| **spring-cloud-azure-starter** | General Azure configuration infrastructure and foundational components for Spring integration | Does not automatically enable all Azure services |
| **spring-cloud-azure-starter-storage-blob** | Configuring and using the Azure Blob Storage client in Spring Boot | Does not automatically create the storage account/container, nor grant read/write permissions |
| **spring-cloud-azure-starter-servicebus** | Integrating Service Bus queues and topics/subscriptions via supported components | Does not turn Service Bus into a Kafka protocol; does not replace duplicate-message handling design |
| **spring-cloud-azure-starter-eventhubs** | Integrating Azure Event Hubs for producing and consuming event streams | Does not automatically provide checkpointing business logic, partition strategy, or retention |
| **spring-cloud-azure-starter-keyvault-secrets** | Loading/accessing secrets from Key Vault, including property source integration when properly configured | Does not automatically support all Key Vault Keys/Certificates APIs |
| **spring-cloud-azure-starter-data-cosmos** | Combining Azure Cosmos DB with supported Spring Data mechanisms | Not a starter for every Azure database type or every Cosmos API |
| **spring-cloud-azure-starter-appconfiguration** | Integrating Azure App Configuration with application configuration, and certain refresh/feature flag mechanisms depending on version | Does not replace a secret vault or deployment configuration management system |
| **spring-cloud-azure-starter-active-directory** | Integrating Microsoft Entra ID with supported Spring Security authentication/authorization flows | Does not automatically grant Azure RBAC to the application for accessing Blob, Key Vault, or Service Bus |

How to group practical needs:

- **Storage:** Blob is object storage; do not equate it with Azure Files or Storage Queues. Choose the starter matching the exact service and data model.
- **Messaging:** Service Bus fits commands, asynchronous tasks, and business pub/sub; Event Hubs fits high-volume ingestion/streaming. The two systems have different consumption and operational models.
- **Data:** Cosmos DB is a database service; the Spring Data starter helps interact through Spring abstractions, but partition key design, consistency, and RUs remain the application's responsibility.
- **Security/Configuration:** Key Vault stores secrets; App Configuration stores application configuration; Entra ID handles identity. These systems complement each other but do not replace one another.
- **Outside starter scope:** if an Azure API does not have a corresponding starter or the starter lacks advanced features, using the **Azure SDK directly** is a valid approach.

**Selection rule:** start from *the capabilities of the service to integrate*, then check whether a starter supports the desired API surface. Do not add every starter to an application just because they all target Azure.

## 5. Dependency Management and Version Compatibility

Spring Boot, Spring Cloud Azure, and the Azure SDK all participate in the dependency graph. A starter version incompatible with Spring Boot, or individually forced **azure-core / azure-identity** versions, can lead to bean initialization failures or linkage errors at runtime.

With Maven, a Spring Boot project can import the Spring Cloud Azure BOM and then declare starters without specifying individual artifact versions:

~~~xml
<!-- pom.xml snippet: declare the spring-cloud-azure.version property
     according to the official compatibility table for the Spring Boot version in use. -->
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
</dependencies>
~~~

This is a **snippet**, not a complete POM: the project still needs a Spring Boot parent or equivalent Spring Boot dependency management, along with an actual value for **spring-cloud-azure.version**. Do not pick a random version number; check the official compatibility matrix for the release before building. In projects that only use the SDK directly, consider **com.azure:azure-sdk-bom** to align the Azure SDK library set.

When conflicts arise, inspect the dependency tree using **mvn dependency:tree** (or the Gradle equivalent), remove unnecessary version overrides, and review release notes when upgrading. Do not arbitrarily mix legacy Spring Cloud Azure artifacts with the modern **com.azure.spring** group.

## 6. Hands-on: Spring Boot Writing Files to Azure Blob Storage

### 6.1. Preparing Resources and Permissions

Suppose an application needs to store documents in the **documents** container of the **myappstorage** storage account. You need:

1. A storage account and the **documents** Blob container already created via the portal, IaC, or administrative tools.
2. The application runner's signed-in identity or the runtime's workload/managed identity.
3. Least-privilege data permissions, such as the **Storage Blob Data Contributor** role at the appropriate container or storage account scope if the application must write blobs.
4. Network path and DNS for the Blob Storage endpoint, especially when using firewalls or private endpoints.

Do not confuse resource management roles (management plane) with Blob data access roles (data plane). After assigning RBAC, it may take some time for permissions to propagate.

### 6.2. Configuring Spring Cloud Azure

Add **spring-cloud-azure-starter-storage-blob** using the BOM from the previous section. In **application.yml**:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT}
~~~

Set the environment variable **AZURE_STORAGE_ACCOUNT=myappstorage** in the runtime environment. This example uses the default credential mechanism supported by Spring Cloud Azure in the chosen version; do not place connection strings or access keys in the repository. If you need to specify a custom credential or endpoint, use the exact properties documented for the deployed version.

The document storage service can receive the **BlobServiceClient** auto-configured by the starter:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.io.ByteArrayInputStream;
import org.springframework.stereotype.Service;

@Service
public class DocumentStorageService {

    private final BlobContainerClient containerClient;

    public DocumentStorageService(BlobServiceClient blobServiceClient) {
        this.containerClient =
                blobServiceClient.getBlobContainerClient("documents");
    }

    public String upload(String blobName, byte[] bytes) {
        BlobClient blobClient = containerClient.getBlobClient(blobName);
        blobClient.upload(
                new ByteArrayInputStream(bytes), bytes.length, true);
        return blobClient.getBlobUrl();
    }
}
~~~

The method demonstrates uploading with **overwrite=true**; a real-world application must consider overwrite risks, blob name sanitization, size limits, content types, and authorization rules. **getBlobUrl()** returns the blob address, which **does not mean the URL is publicly accessible**. If the container is private, readers still need valid permissions or an authorized URL such as an on-demand SAS.

The application above does not need to manually build a **BlobServiceClientBuilder** because the starter configures the bean. If the application context has multiple beans of the same type or needs multiple storage accounts, configure beans/named clients explicitly according to the version in use.

### 6.3. Same Problem with the Azure SDK Directly

Without using the starter, the developer creates the SDK client, endpoint, and credential manually. The following example uses **azure-identity** and **azure-storage-blob**:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class AzureBlobClients {

    public static BlobServiceClient create(String accountName) {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint("https://" + accountName + ".blob.core.windows.net")
                .credential(credential)
                .buildClient();
    }
}
~~~

In Spring Boot, you can place this client creation inside a **@Bean** method and inject the client wherever needed. The direct SDK approach is useful when you need multiple accounts, specialized pipeline configuration, an API not yet supported by a starter, or reusable logic in non-Spring applications.

**Comparing the two approaches:** the upload business logic uses the same **BlobClient** API; the difference lies in where the client is initialized, configuration is loaded, and lifecycle is managed. There is no need to manually create a second client if the bean provided by the starter already meets the requirements.

## 7. Extending from Blob to Other Service Groups

### Service Bus and Event Hubs

An order flow can publish an **OrderCreated** message to a Service Bus queue for asynchronous worker processing. A telemetry stream of millions of events is a better fit for Event Hubs. Regardless of whether you use a starter or the SDK, you must account for:

- **At-least-once:** the consumer side must handle duplicate messages using an idempotency key or processed-state tracking.
- **Retry and dead-letter:** transient errors and business errors must have distinct policies; monitor the dead-letter queue for Service Bus.
- **Ordering and partitioning:** do not assume global ordering when running multiple consumers; Event Hubs has partition and checkpoint concepts.
- **Identity/Authorization:** sending and receiving principals need corresponding data roles, such as **Azure Service Bus Data Sender/Receiver** or **Azure Event Hubs Data Sender/Receiver**.

### Cosmos DB

The Spring Data Cosmos starter can reduce repository wiring, yet **partition key** design, query patterns, consistency, throughput/RU, indexing, and **429/throttling** handling strategies still determine system effectiveness. Do not use the repository abstraction to hide cross-partition read costs or misunderstand consistency guarantees.

### Key Vault and App Configuration

Key Vault is suited for storing passwords, tokens, or secrets requiring lifecycle management; App Configuration is suited for managing configuration keys and feature flags. Access secrets through a service identity instead of copying secrets into YAML files. In operations, manage rotation, refresh/cache latency, secret read permissions, and failure modes when Key Vault/App Configuration is unavailable.

## 8. Choosing a Starter vs. the Direct SDK

| Criterion | Choose Spring Cloud Azure Starter | Choose Azure SDK Directly |
| --- | --- | --- |
| Spring Boot application, a common Azure service | Usually suitable thanks to auto-configuration, Spring properties, injection | Valid but requires more wiring code |
| Non-Spring Java application | Not aligned with the integration target | Suitable |
| Multiple accounts/tenants, custom endpoints or pipelines | Check whether the version supports multi-client configuration | Proactively instantiate separate clients |
| Specialized API or no starter available | May require additional SDK usage | Directly suitable |
| Optimizing dependency count and lifecycle control | Inspect the starter's dependency graph | Can pull in only the exact SDKs needed |
| Spring Boot-style testing | Can override/mock beans and use test context | Can inject client/interface via application configuration |

You can combine both approaches in one system, such as a starter for Blob Storage and the direct SDK for a specialized Azure API. However, keep SDK versions consistent and clearly define where each client is managed to avoid duplicate beans or scattered credentials.

## 9. Testing, Observability, and Troubleshooting

An Azure-integrated project should not stop at verifying that the Spring context starts successfully. Test across three layers:

1. **Unit tests:** mock/wrap the Blob access layer, simulating successful uploads, permission errors, timeouts, and name collisions; no Azure account required.
2. **Local integration tests:** for Blob, you can use **Azurite** for APIs supported by the emulator. Clearly document differences between the emulator and real Azure, especially authentication/RBAC, networking, certain APIs, and behaviors.
3. **Integration tests against test Azure resources:** use real identities to verify RBAC, private endpoint/DNS, security policies, retry/throttling, read/write permissions, and cleanup of test resources. Services without a sufficiently equivalent emulator require a dedicated test environment.

Initial troubleshooting table:

| Symptom | Common Causes | What to Check |
| --- | --- | --- |
| Spring fails to create Azure client bean | Missing starter, configuration incompatible with version, dependency conflict | Check auto-configuration, application properties, and dependency tree |
| Credential chain cannot find an identity | Not signed in to CLI, workload identity/managed identity unconfigured, or wrong environment | Verify which credential source is actually selected and check runtime setup |
| **401** when calling API | Missing, expired, or invalid token for the service | Check token issuer, audience/endpoint, and tenant configuration |
| **403** despite being signed in | Missing data-plane role, wrong scope assignment, or network policy | Check RBAC on the exact resource, firewall/private endpoint |
| **404** or **409** with Blob | Wrong account/container/blob name, resource does not exist, or state conflict | Check endpoint, resource names, and operation preconditions |
| **429**, timeouts, or transient network errors | Throttling, resource limits, DNS/connectivity issues, or traffic spikes | Monitor metrics, quotas, bounded retry/backoff, and idempotency |

When logging or tracing, you may record error codes, correlation/request IDs, operation names, and durations, but **never log access tokens, connection strings, secret values, SAS URLs, or sensitive data**. For uploads/retries, check the side effects of re-running an operation: library retries do not replace business-level idempotency policies.

## 10. Connecting to Multi-Cloud Integration Lessons

| Purpose | Azure | AWS | Google Cloud |
| --- | --- | --- | --- |
| Low-level Java client | Azure SDK for Java | AWS SDK for Java | Google Cloud Java client libraries |
| Spring ecosystem integration | Spring Cloud Azure | Spring Cloud AWS | Spring Cloud GCP |
| Object storage | Azure Blob Storage | Amazon S3 | Cloud Storage |
| Queue/pub-sub | Service Bus / Event Hubs depending on use case | SQS / SNS / Kinesis depending on use case | Pub/Sub |
| Workload identity | Managed Identity / Workload Identity + Entra ID | IAM Role / temporary credentials | Service Account / Workload Identity |
| Secret management | Azure Key Vault | AWS Secrets Manager | Secret Manager |

This is a **conceptual map**, not a claim that the services share identical semantics. When switching providers, you must still re-analyze authorization mechanisms, endpoints, consistency, event ordering, retries, costs, and service limits. Hiding the SDK behind a business interface can reduce direct coupling, but it does not eliminate differences in data models and operations.

## 11. Hands-on Exercises

Build a Spring Boot API that accepts file content and returns the blob name after storing it in a private container:

1. Create a test storage account/container and grant data write permissions at the proper scope to the app's runtime identity.
2. Use a compatible BOM, add **spring-cloud-azure-starter-storage-blob**, and configure the account name via an environment variable.
3. Inject **BlobServiceClient**, validate input preconditions, upload the blob, and return its identifier. Test with two blobs of the same name to observe the effect of overwrite.
4. Write a unit test simulating an upload failure; then try an integration test using Azurite or an appropriate test Azure resource.
5. Replace the bean provided by the starter with a manually created client using **DefaultAzureCredential** in a practice branch, and document the additional configuration you become responsible for.
6. Compare with S3/GCS in terms of identity, roles, endpoint configuration, upload mechanics, failure cases, and operational cost.

**Self-check questions:** If Spring Boot successfully creates **BlobServiceClient** but the upload API returns **403**, should you investigate the Spring starter or Azure access permissions? Why? If an application migrates from Service Bus to Event Hubs, which parts of the consumer design cannot remain the same?

## 12. Key Takeaways

- **Azure SDK** provides the APIs to interact with services; **Spring Cloud Azure** provides the way to wire those APIs into a Spring application; a **starter** packages dependencies and auto-configuration for a given need.
- Start from the service and capabilities required, choose the minimal starter, manage dependencies with a BOM, and verify the version compatibility matrix.
- Prefer workload/managed identity and least-privilege RBAC; **authentication**, **authorization**, and **network access** are independent prerequisites.
- Auto-configuration does not replace designing for idempotency, retries, partitioning, observability, testing against real resources, or cost management.

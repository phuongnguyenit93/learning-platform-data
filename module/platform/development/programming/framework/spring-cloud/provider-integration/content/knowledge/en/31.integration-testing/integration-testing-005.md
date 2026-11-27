# Azurite for Storage and Limitations of Emulated Azure Services

> **Chapter:** Integration Testing  
> **Module:** SPRING_CLOUD_PROVIDER_INTEGRATION  
> **Objective:** Use Azurite in Spring Boot integration tests to verify Blob, Queue, and Table Storage; configure Azure SDKs against local endpoints; manage containers with Testcontainers; recognize limitations in APIs, authentication, networking, and Azure services outside Azurite's scope.

## 1. What Is Azurite?

Azurite is the open-source Azure Storage emulator, running locally for developers and CI to test applications that use Azure Storage SDKs. The application sends requests over the Storage REST API and receives responses from a running service, making Azurite more informative than mocks when verifying how the SDK constructs requests, serializes data, handles metadata, or reads/writes objects.

Azurite currently supports three services:

- **Blob Storage:** containers and blobs, upload/download, metadata, properties, leases, and many supported Blob API operations.
- **Queue Storage:** queues and messages following the Azure Storage Queue model.
- **Table Storage:** tables and entities; support is currently in preview.

Azurite is not a miniature Azure cloud. It simulates a subset of the Azure Storage APIs for development and testing. It does not implement Azure Files or Azure Data Lake Storage Gen2. Nor does it emulate Service Bus, Event Hubs, Cosmos DB, Key Vault, or any other managed services.

In the Spring Cloud Provider Integration module, use Azurite to test storage adapters and application flows requiring Blob/Queue/Table. When you need to verify Entra ID, RBAC, private endpoints, quotas, replication, or behaviors unique to the managed service, test against an appropriate Azure test account/subscription.

## 2. Distinguishing Azurite from Other Azure Emulators

Avoid saying "the Azure emulator" as if every service runs inside one container. Different services have distinct protocols, dependencies, and feature sets.

| Azure Service | Emulator/Tool | Typical Test Scope |
| --- | --- | --- |
| Blob Storage | Azurite | Upload/download, containers, metadata, content types, properties, and supported Blob APIs |
| Queue Storage | Azurite | Create queue, send, receive, peek, update, and delete messages within supported APIs |
| Table Storage | Azurite | Basic entity CRUD and queries; service is in preview |
| Azure Files | Not in Azurite | Requires testing on real Azure Files or test doubles for isolated logic |
| Data Lake Storage Gen2 | Not in Azurite | Requires real Azure to verify hierarchical namespaces, ACLs, and Data Lake APIs |
| Azure Service Bus | Dedicated Service Bus emulator | Queues/topics, senders/processors, and partial AMQP behavior |
| Azure Event Hubs | Dedicated Event Hubs emulator | Producer/consumer flows and partition configuration within emulator limits |
| Azure Cosmos DB | Dedicated Cosmos DB emulator | Cosmos DB client/APIs, TLS configuration, and certificates |
| Azure Key Vault | Outside Azurite | Use fakes for application logic and an Azure test vault for identity, RBAC, networking, and rotation |

The Testcontainers Java Azure module provides separate containers for Azurite, the Service Bus emulator, the Event Hubs emulator, and the Cosmos DB emulator. The Azure module is marked **incubating**; APIs may change across versions. Do not use Azurite to test Service Bus message broker semantics: Queue Storage and Service Bus are different services.

## 3. Adding Azurite to Testcontainers

### 3.1. Maven Dependencies

Use the Testcontainers BOM to keep versions of core, JUnit, and the Azure module aligned. The example uses version 2.0.5; pick a version verified against your project's JDK and Spring Boot version.

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.testcontainers</groupId>
            <artifactId>testcontainers-bom</artifactId>
            <version>2.0.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>testcontainers-azure</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-blob</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-storage-queue</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>com.azure</groupId>
        <artifactId>azure-data-tables</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Include only the Azure SDK artifacts used by your tests or adapters. If those SDKs are already declared in the application's main dependencies, there is no need to redeclare them in test scope.

### 3.2. Gradle Dependencies

```groovy
dependencies {
    testImplementation platform("org.testcontainers:testcontainers-bom:2.0.5")
    testImplementation "org.testcontainers:testcontainers-junit-jupiter"
    testImplementation "org.testcontainers:testcontainers-azure"

    testImplementation "com.azure:azure-storage-blob"
    testImplementation "com.azure:azure-storage-queue"
    testImplementation "com.azure:azure-data-tables"
}
```

The Testcontainers Azure module is currently marked incubating. Pin the BOM, Azure SDK versions, and Azurite image; when upgrading any of these versions, re-run the related adapter tests.

### 3.3. Starting the Azurite Container

With Testcontainers 2.x, the class resides in package org.testcontainers.azure:

```java
import org.testcontainers.azure.AzuriteContainer;

AzuriteContainer azurite = new AzuriteContainer(
        "mcr.microsoft.com/azure-storage/azurite:3.37.0");

azurite.start();

try {
    String connectionString = azurite.getConnectionString();
    // Create the Azure SDK client and run tests.
} finally {
    azurite.stop();
}
```

In JUnit 5, the extension can manage the lifecycle:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.azure.AzuriteContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class AzuriteSmokeIT {

    @Container
    static final AzuriteContainer azurite =
            new AzuriteContainer(
                    "mcr.microsoft.com/azure-storage/azurite:3.37.0");

    @Test
    void containerExposesStorageConnectionString() {
        assertThat(azurite.isRunning()).isTrue();
        assertThat(azurite.getConnectionString())
                .contains("BlobEndpoint=http://")
                .contains("QueueEndpoint=http://")
                .contains("TableEndpoint=http://");
    }
}
```

A static container is shared across the test class and stops when the class completes. Use separate container, queue, and table names per test to avoid methods overwriting each other's data.

Do not hard-code host ports in tests. Testcontainers maps container ports to the host; getConnectionString() generates a connection string matching endpoints reachable from the test JVM.

## 4. Endpoints and Connection Strings

### 4.1. Three Default Ports

Azurite uses these default internal ports:

| Storage Service | Container Port |
| --- | ---: |
| Blob | 10000 |
| Queue | 10001 |
| Table | 10002 |

When running Docker directly, these ports are often published to the host. With Testcontainers, the host ports can be randomized. Always use the connection string provided by the container rather than assembling `localhost:10000` manually.

Example default connection string format:

```text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=<Azurite-development-key>;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
```

These are the emulator's well-known public development credentials, not real Azure Storage account secrets. Never use them to connect to production and never confuse them with real cloud credentials.

### 4.2. Local Endpoints Differ from Real Azure Endpoints

A real Azure Storage account typically uses hostnames containing the account name:

```text
https://<account-name>.blob.core.windows.net/<container>/<blob>
```

Azurite typically uses local path-style URLs:

```text
http://<host>:<mapped-port>/<account-name>/<container>/<blob>
```

Therefore, do not manually construct a production Azure URL and swap the domain for localhost. Use getConnectionString() or the endpoints provided by AzuriteContainer so the SDK receives the right account, service port, and path.

If configuring endpoints manually across multiple services, maintain distinct endpoints for Blob, Queue, and Table. Exposing only the Blob port does not make Queue or Table endpoints work automatically.

### 4.3. Test JVM and Application Container Use Different Endpoints

When the test JVM runs on the host, using azurite.getConnectionString() is the simplest choice.

If the application also runs inside a Docker container on the same network as Azurite, 127.0.0.1 or host-mapped ports may not be reachable from the application container. In that case:

1. Place Azurite and the application container on the same Docker network.
2. Assign a network alias, such as azurite.
3. Configure endpoints using hostname azurite and internal ports 10000/10001/10002.
4. Use the corresponding test account/key with those endpoints.

Never use localhost from inside an application container to call another container; localhost inside a container refers to that container itself.

## 5. Testing Blob Storage

Blob is the most commonly used service in file-storing applications. With Azurite, you can test upload/download, container lifecycles, metadata, content types, and various Blob API operations.

### 5.1. Creating a Blob Client Using a Connection String

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

BlobServiceClient serviceClient =
        new BlobServiceClientBuilder()
                .connectionString(azurite.getConnectionString())
                .buildClient();

String containerName = "it-" +
        UUID.randomUUID().toString().replace("-", "");

BlobContainerClient container =
        serviceClient.createBlobContainer(containerName);
```

Container names must obey Azure Blob Storage naming rules. Using a UUID prevents parallel tests from colliding on a fixed container name.

### 5.2. Upload, Download, and Content Verification

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void uploadsAndDownloadsBlob() {
    BlobServiceClient serviceClient =
            new BlobServiceClientBuilder()
                    .connectionString(azurite.getConnectionString())
                    .buildClient();

    String containerName = "it-" +
            UUID.randomUUID().toString().replace("-", "");

    BlobContainerClient container =
            serviceClient.createBlobContainer(containerName);

    try {
        BlobClient blob = container.getBlobClient("document.txt");
        String expected = "Spring Boot with Azure Storage";

        blob.upload(BinaryData.fromString(expected), true);

        String actual = new String(
                blob.downloadContent().toBytes(),
                StandardCharsets.UTF_8);

        assertThat(actual).isEqualTo(expected);
        assertThat(blob.exists()).isTrue();
    } finally {
        container.deleteIfExists();
    }
}
```

This test verifies that the Azure Blob SDK sends requests through the Azurite endpoint and can read back the written contents. It is suited for checking adapter mapping and basic storage flows.

### 5.3. Verifying Content Type and Metadata

Applications often need to preserve content types, metadata, or HTTP headers so files are served properly. Verify them via the SDK:

```java
import java.util.Map;
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.models.BlobHttpHeaders;
import com.azure.storage.blob.models.BlobProperties;

BlobClient blob = container.getBlobClient("report.pdf");

blob.upload(BinaryData.fromBytes(pdfBytes), true);

blob.setHttpHeaders(
        new BlobHttpHeaders()
                .setContentType("application/pdf"));

blob.setMetadata(Map.of(
        "documentid", "doc-101",
        "source", "integration-test"));

BlobProperties properties = blob.getProperties();

assertThat(properties.getContentType())
        .isEqualTo("application/pdf");
assertThat(properties.getMetadata())
        .containsEntry("documentid", "doc-101");
```

Metadata keys/values must follow Azure Storage rules. Prefer lowercase keys to avoid discrepancies when the SDK or service normalizes headers.

### 5.4. Useful Assertions for Blob Adapters

| Behavior | Suggested Assertion |
| --- | --- |
| Create container | Container exists after creation |
| Upload | Blob exists and downloaded content matches |
| Overwrite | New content is stored according to the adapter's overwrite policy |
| Content type | getProperties() returns the expected MIME type |
| Metadata | Metadata keys/values are preserved |
| Download missing object | Adapter maps 404 to the result or exception defined by the port contract |
| Delete | Blob no longer exists after deletion |
| ETag/conditional write | Conditional requests are mapped and responses are handled properly within supported APIs |

You do not need to test every operation in one massive test. Separating behaviors makes it easier to pinpoint causes when Azurite or the SDK reports an error.

## 6. Testing Queue Storage

Azure Queue Storage provides simple queues for storing messages. Azurite supports a subset of the Queue Storage REST API, such as creating queues and sending/receiving/peeking, updating, and deleting messages.

Queue Storage is not Azure Service Bus. It does not offer full Service Bus semantics such as topics/subscriptions, sessions, dead-letter queues, transactions, or broker lock models. If your application uses those features, use the dedicated Service Bus emulator or an Azure test namespace.

### 6.1. Creating a Queue and Sending/Receiving Messages

```java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueServiceClientBuilder;
import com.azure.storage.queue.models.QueueMessageItem;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void sendsAndReceivesQueueMessage() {
    QueueServiceClient serviceClient =
            new QueueServiceClientBuilder()
                    .connectionString(azurite.getConnectionString())
                    .buildClient();

    String queueName = "it-" +
            UUID.randomUUID().toString().replace("-", "");

    QueueClient queue = serviceClient.createQueue(queueName);

    try {
        queue.sendMessage("document-uploaded");

        QueueMessageItem received = queue.receiveMessage();

        assertThat(received).isNotNull();
        assertThat(new String(
                received.getBody().toBytes(),
                StandardCharsets.UTF_8))
                .isEqualTo("document-uploaded");

        queue.deleteMessage(
                received.getMessageId(),
                received.getPopReceipt());
    } finally {
        queue.deleteIfExists();
    }
}
```

Queue messages have visibility timeouts and pop receipts. When a test receives a message, use the message ID together with its current pop receipt to delete or update the message. Do not assume receiving a message means it has been deleted.

### 6.2. Testing Error Branches and Message Lifecycles

Consider testing:

- Queue does not exist yet.
- Queue is created twice according to create/create-if-not-exists policies.
- Message is sent and received with the expected body.
- Message is peeked without being consumed.
- Message is updated with a valid pop receipt.
- Message is deleted after receipt.
- Queue is deleted when the test completes.

Azurite helps verify Queue Storage requests/responses within supported APIs. If business logic relies on Service Bus guarantees around ordering, duplicate detection, sessions, lock renewal, or dead-letter processing, do not use the Queue Storage emulator to infer those results.

## 7. Testing Table Storage

Azurite includes a Table Storage service, though Table support is currently in preview. Use it only for smoke tests and basic operations verified on your pinned image/version.

### 7.1. Creating a Table and Writing Entities

```java
import java.util.UUID;
import com.azure.data.tables.TableClient;
import com.azure.data.tables.TableServiceClient;
import com.azure.data.tables.TableServiceClientBuilder;
import com.azure.data.tables.models.TableEntity;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void createsTableAndStoresEntity() {
    TableServiceClient serviceClient =
            new TableServiceClientBuilder()
                    .connectionString(azurite.getConnectionString())
                    .buildClient();

    String tableName = "It" +
            UUID.randomUUID().toString().replace("-", "");

    TableClient table = serviceClient.createTable(tableName);

    try {
        TableEntity entity = new TableEntity(
                "documents",
                "doc-101")
                .addProperty("status", "READY");

        table.createEntity(entity);

        TableEntity loaded =
                table.getEntity("documents", "doc-101");

        assertThat(loaded.getProperties())
                .containsEntry("status", "READY");
    } finally {
        serviceClient.deleteTable(tableName);
    }
}
```

Table names and keys must follow Azure Table Storage naming rules. Partition key and row key together identify an entity; use them to construct deterministic IDs in tests.

### 7.2. Limitations of Table Preview

Do not treat a passing Table test on Azurite as proof that all Table Storage APIs are supported. Certain service properties operations, ACLs, batch transactions, or complex queries may be missing or behave differently from the cloud. Check the support matrix for your exact Azurite version before relying on a specific API.

For critical flows, run contract tests against a real test Azure Storage account. If the application relies on Table APIs not yet supported by the emulator, use fakes for isolated repository logic and cloud tests for the adapter.

## 8. Integrating Azurite with Spring Boot

### 8.1. Passing the Connection String via DynamicPropertySource

If the application defines a dedicated property for its connection string, tests can register the dynamic value:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.azure.AzuriteContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class DocumentStorageIntegrationTest {

    @Container
    static final AzuriteContainer azurite =
            new AzuriteContainer(
                    "mcr.microsoft.com/azure-storage/azurite:3.37.0");

    @DynamicPropertySource
    static void storageProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
                "app.azure.storage.connection-string",
                azurite::getConnectionString);
    }
}
```

app.azure.storage.connection-string is a property defined by the example application. Bean configuration must read this property to create Azure SDK clients. Do not assume Spring Boot automatically points every Azure SDK client to Azurite simply because Testcontainers is present.

### 8.2. Defining a Blob Client Bean

```java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class AzureStorageClientConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(Environment environment) {
        String connectionString = environment.getRequiredProperty(
                "app.azure.storage.connection-string");

        return new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
    }
}
```

In production, connection strings or credentials come from secure configuration. Test profiles can override the property with Azurite's connection string. Keeping client construction in configuration/adapters allows tests to swap endpoints without modifying business logic.

### 8.3. Using Spring Cloud Azure Service Connections When Supported

Some versions of Spring Cloud Azure provide connection details for Azurite through ServiceConnection. This mechanism belongs to Spring Cloud Azure integration, not a universal default for every Azure SDK client in Spring Boot.

If using that mechanism, check the documentation for your exact Spring Cloud Azure version and supported service connection types. If no matching factory/connection details exist, DynamicPropertySource is an explicit way to inject the endpoint into client configuration.

### 8.4. Watch Out for the Spring Context Cache

The JUnit Testcontainers extension may stop the container after a test class finishes while the Spring TestContext cache retains the ApplicationContext. A reused context may hold a BlobServiceClient pointing to a stopped container's endpoint.

When multiple test classes share a Spring context, consider managing the Azurite container with the Spring context lifecycle or keeping context configuration consistent. Never share a context whose beans depend on a container that has already stopped.

## 9. Configuring Test Accounts and Keys

### 9.1. Default Account

Azurite has a default development account and publicly documented key for the emulator. AzuriteContainer's getConnectionString() generates a connection string for that default account.

Never use default emulator credentials against real Azure. Never put production connection strings into test fixtures.

### 9.2. Creating Custom Test Accounts

When testing multiple accounts/keys, pass the AZURITE_ACCOUNTS environment variable:

```java
AzuriteContainer azurite =
        new AzuriteContainer(
                "mcr.microsoft.com/azure-storage/azurite:3.37.0")
                .withEnv(
                        "AZURITE_ACCOUNTS",
                        "itaccount:test-key-one:test-key-two");

azurite.start();

String connectionString =
        azurite.getConnectionString(
                "itaccount",
                "test-key-one");
```

You can define multiple accounts in the same container:

```text
AZURITE_ACCOUNTS=account1:key1:key2;account2:key3
```

Use test-only keys and never reuse production secrets. This test helps verify that the application picks up the configured account/key and that the adapter does not hard-code default credentials.

### 9.3. SAS and Shared Key

Azurite supports Shared Key and forms of SAS within the emulator's supported scope. You can write tests verifying client creation with SAS or confirming requests are rejected when signatures are invalid.

However, SAS tests on Azurite only prove behavior implemented by the emulator. Do not treat them as proof that all policies, expirations, stored access policies, or authorization behaviors on real Azure have been verified.

## 10. OAuth and Identity Testing Limitations

Azurite can enable basic OAuth when configured with HTTPS and the OAuth option. This is a limited testing mode, not a full simulation of Microsoft Entra ID.

In basic OAuth mode, Azurite checks certain token properties such as issuer, audience, and expiry, but does not validate token signatures or resource access permissions. Therefore:

- Do not use basic OAuth to prove token signatures are verified as in real Azure.
- Do not use it to prove RBAC role assignments or data-plane permissions.
- Do not infer that Managed Identity works simply because a client call to Azurite succeeds.
- Do not use Azurite to test token acquisition via workload identity or production private endpoints.

If you need to exercise basic OAuth, you must enable HTTPS and configure a certificate for the emulator. That test only exercises the limited token validation branch supported by Azurite.

For Spring Boot applications deployed on Azure, maintain cloud integration tests using a real Managed Identity or workload identity with least-privilege roles. Test read/write/delete permissions on the target resources and include negative tests for ungranted operations.

## 11. Important Technical Limitations of Azurite

### 11.1. Only Three Storage Services

Azurite supports Blob, Queue, and Table. It does not support Azure Files or Azure Data Lake Storage Gen2. If the application uses file shares, hierarchical namespaces, directory ACLs, or Data Lake APIs, you need a real Azure environment or test doubles for domain logic.

### 11.2. Table Storage Is in Preview

Azurite's Table service is in preview. Feature coverage may be incomplete or change over time. Avoid relying on the emulator as the sole test gate for a system depending on advanced Table APIs.

### 11.3. API Version Does Not Equal Feature Support

Newer Azure SDKs may send requests using an API version not yet accepted by the current Azurite image. The Testcontainers Azure module provides withCommandOptions() to pass flags such as --skipApiVersionCheck:

```java
AzuriteContainer azurite =
        new AzuriteContainer(
                "mcr.microsoft.com/azure-storage/azurite:3.37.0")
                .withCommandOptions("--skipApiVersionCheck");
```

Enable this flag only once you have confirmed a request is rejected solely due to its API version even though the operation is supported by the emulator. Skipping the version check does not implement missing APIs, does not turn the emulator into real Azure Storage, and can mask compatibility issues. Prefer pinning compatible Azure SDK and Azurite image versions.

### 11.4. Endpoints and URLs Differ from Cloud

Azurite uses local endpoints, local ports, and typically path-style URLs. Real Azure uses account/service hostnames. Tests depending on DNS, private endpoints, firewalls, VNet integration, or private DNS zones require a cloud environment.

### 11.5. Performance and Scale

Azurite is built for development/testing and offers no performance guarantees matching Azure Storage. Do not use benchmark results on Azurite to estimate production throughput, latency, concurrency, or scale.

### 11.6. Differences in Error Behavior

Azurite strives for error-handling compatibility with Azure Storage, but error messages may differ. HTTP status codes may match in many cases, yet tests should not depend on exact error text. Assert against stable status codes, error codes, or the exception contract guaranteed by your adapter.

### 11.7. Replication, Durability, and Data Lifecycle

Azurite can simulate certain storage operations, but does not replace testing durability, geo-replication, failover, lifecycle policies, soft delete, versioning, and backup/restore on real Azure. Test a feature locally only if the pinned emulator version's support matrix confirms support.

### 11.8. Authentication and Authorization

Local Shared Key/SAS is useful for testing SDK configuration. Basic OAuth has the limitations noted above. RBAC, role propagation, Managed Identity, resource scopes, storage firewalls, and private endpoints must be tested on real Azure.

## 12. Azurite Does Not Replace Service Bus, Event Hubs, or Cosmos DB Emulators

Several Azure services have dedicated containers in the Testcontainers Azure module:

| Service | Dedicated Container | Dependencies / Notes |
| --- | --- | --- |
| Service Bus | ServiceBusEmulatorContainer | Requires SQL Server, entity configuration, and a shared Docker network |
| Event Hubs | EventHubsEmulatorContainer | Requires namespace/entity configuration; may require Azurite as a dependency depending on emulator version |
| Cosmos DB | CosmosDBEmulatorContainer | Requires certificate/truststore handling when clients use HTTPS |
| Storage | AzuriteContainer | Blob/Queue/Table; does not replace the brokers or databases above |

You cannot enable these services merely by opening extra ports on Azurite. Each emulator has its own image, protocol, configuration, and limitations.

### 12.1. Queue Storage Differs from Service Bus

| Criterion | Azure Queue Storage | Azure Service Bus |
| --- | --- | --- |
| Model | Simple queue inside a Storage account | Messaging broker |
| Topics/subscriptions | No | Yes |
| Sessions | No Service Bus session semantics | Yes |
| Dead-letter queue | No broker-managed DLQ like Service Bus | Yes |
| Lock/settlement | Visibility timeout and pop receipt | Peek-lock, complete, abandon, dead-letter |
| Emulator | Azurite | Dedicated Service Bus emulator |

If the application uses QueueClient, Azurite fits Queue Storage API testing. If the application uses ServiceBusClientBuilder, test against the Service Bus emulator or an Azure test namespace.

### 12.2. When to Use Another Emulator or Real Azure?

- Use the Service Bus emulator to test senders/processors and basic queue/topic flows.
- Use the Event Hubs emulator to test producer/consumer flows and partition configuration within supported scope.
- Use the Cosmos DB emulator to test document database client/APIs and SSL trust setup.
- Use real Azure to verify Entra ID, RBAC, Managed Identity, private networking, quotas, tiers, and behaviors unsupported by emulators.
- Use fakes/test doubles to test domain logic independent of the Azure SDK.

## 13. Testing Matrix: Azurite vs. Real Azure

| Risk/Behavior | Azurite | Azure Test Account |
| --- | --- | --- |
| Blob upload/download | Yes, within supported APIs | Yes |
| Container create/delete | Yes | Yes |
| Metadata/content type | Yes | Yes |
| Queue send/receive | Yes, within supported APIs | Yes |
| Basic Table CRUD | Yes, preview | Yes |
| Azure Files | No | Yes |
| Data Lake Gen2 | No | Yes |
| API version compatibility | Testable per image/SDK | Yes |
| Basic Shared Key/SAS | Yes, within supported scope | Yes |
| Full Entra ID token signature/authorization | No | Yes |
| RBAC role assignment | No | Yes |
| Managed Identity | No | Yes |
| Private endpoint/DNS/VNet | No | Yes |
| Production quotas/throttling/scale | Not representative | Yes |
| Production replication/failover | Not fully representative | Yes |
| Azure Storage lifecycle/retention | Supported features only | Yes |

A balanced pipeline can run Azurite integration tests on pull requests, then run cloud integration tests on a schedule, before release, or when identity/network/storage policies change.

## 14. Organizing Test Data and Cleanup

### 14.1. Dedicated Resource Names per Test

Use an `it-` prefix plus a UUID for containers/queues/tables. For blobs, use keys containing the test run ID or test method ID. This reduces collisions during parallel execution.

### 14.2. Resource Cleanup

- Delete blob containers after tests complete.
- Delete queues/tables created by the test.
- Use `try/finally` or fixture cleanup so teardown runs even if assertions fail.
- If tests share one Azurite container across a class, ensure each test uses distinct resources.
- Do not mount a shared persistence volume in CI unless the test specifically tests persistence.

Azurite stores data inside the emulator's workspace directory. A freshly created container without a mounted volume will not retain data from previous test containers. If mounting a volume for debugging, reset the workspace so stale state does not affect the next run.

### 14.3. Do Not Let Tests Depend on Execution Order

No test should rely on a previous test having created a container or queue. Every test must provision the data it needs and clean up its own resources. Under parallel execution, never share fixed resource names.

## 15. Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Connection refused | Wrong host/port or container not ready | Use `getConnectionString()` and an appropriate wait strategy |
| SDK calls wrong endpoint | Manually constructed URL or production cloud endpoint | Use the connection string from `AzuriteContainer` |
| Blob client works but Queue client fails | Only Blob service exposed/started or Queue endpoint missing | Check connection string and Queue service port |
| API version rejected | SDK sends a version not yet supported by Azurite | Pin compatible versions; only consider `--skipApiVersionCheck` if the operation is supported |
| Operation returns unsupported | Emulator has not implemented that API/feature | Check support matrix; move test to real Azure |
| Table test is flaky | Table API is preview or feature support is unstable | Keep tests at basic/smoke level and test critical behaviors in the cloud |
| Client uses wrong account/key | Custom account does not match connection string | Use `getConnectionString(account, key)` and verify `AZURITE_ACCOUNTS` |
| App container cannot reach Azurite | Using `localhost`/host-mapped port from another container | Use Docker network alias and internal port |
| OAuth test behaves unlike Azure | Basic OAuth does not validate full signatures/permissions | Run cloud tests with Entra ID/RBAC |
| Passes locally but fails in CI | Differences in Docker networking, mapped hosts, image pulls, or shared data | Pin image, retrieve dynamic endpoints, isolate resources, and archive container logs |
| Stale data reappears | Workspace volume persisted across runs | Clear/reset workspace or use a fresh container without a volume |

When errors occur, record the Azure SDK version, Azurite image tag, request API version, service endpoint, and status/error code. Never write connection strings or account keys to CI logs.

## 16. Practice Lab: Testing Document Storage with Azurite

**Context:** Document Service uses Spring Boot and Azure Blob Storage to store PDF files. The service persists metadata to a database and emits an event after a successful upload. Test the storage adapter with Azurite and identify which assertions require real Azure.

### Part A — Setting Up Azurite

- Add the Testcontainers Azure module and Azure Blob SDK.
- Create an `AzuriteContainer` with a pinned image version.
- Use `@Testcontainers` and `@Container` to manage its lifecycle.
- Retrieve the connection string via `getConnectionString()`.
- Create a smoke test verifying the Blob endpoint is reachable.

### Part B — Blob Adapter

- Create a dedicated container per test ID.
- Upload a PDF file with content type `application/pdf`.
- Read back the content and metadata.
- Test overwrite, delete, and missing-object behavior.
- Verify the adapter translates storage errors into application port exceptions.

### Part C — Spring Boot Wiring

- Register `app.azure.storage.connection-string` via `@DynamicPropertySource`.
- Define a `BlobServiceClient` bean from that property.
- Inject the storage adapter into the use case.
- Verify the use case stores the object and returns expected metadata.
- Keep Azure production connection strings out of test config.

### Part D — Queue/Table If Used by the Application

- Use the Queue Storage SDK and create a uniquely named queue.
- Send/receive a message and delete it using its pop receipt.
- If using Table, write a basic CRUD smoke test and explicitly note preview API status.
- Do not use Queue Storage tests to conclude Service Bus sessions/DLQ/transactions work.

### Part E — Real Cloud Testing

- Use a workload identity or Managed Identity in an Azure test environment.
- Assign least-privilege RBAC roles for the target storage account/container.
- Write positive and negative permission tests.
- If production uses a private endpoint, run tests from the matching network path.
- Verify quotas, encryption, lifecycles, replication, or Data Lake/Files if the application relies on them.

**Completion criteria:** the learner starts Azurite with Testcontainers, configures the Azure SDK from a dynamic connection string, writes Blob integration tests, understands Queue Storage and Table Storage within emulator boundaries, and identifies behaviors requiring real Azure verification.

---

## 17. Pre-Merge/Pre-Release Checklist

| Group | Question |
| --- | --- |
| Dependency | Are Testcontainers Azure module and Azure SDK versions pinned? |
| Emulator | Is the Azurite image tag pinned and compatible with the SDK API version? |
| Lifecycle | Is the container started/stopped automatically? |
| Endpoint | Do tests use the dynamic connection string from `getConnectionString()`? |
| Blob | Are upload/download, content type, metadata, and delete tested? |
| Queue | Is Queue Storage clearly distinguished from Service Bus? |
| Table | Do tests note Table Storage preview status and feature limits? |
| Account | Are test accounts/keys used instead of reusing production credentials? |
| OAuth | Are basic OAuth checks kept distinct from full RBAC/Entra authorization? |
| API version | Is `--skipApiVersionCheck` used only intentionally? |
| Data isolation | Are container/queue/table/blob names unique per test? |
| Cleanup | Do resources and workspaces have cleanup/reset paths? |
| Networking | Do app containers use network aliases rather than `localhost`? |
| Cloud gaps | Are cloud tests in place for RBAC, Managed Identity, private endpoints, and unsupported features? |
| CI | Does the runner have a Docker-compatible runtime and image pull access? |
| Diagnostics | Do logs capture service name, SDK version, image tag, and error codes without secrets? |

## Key Takeaways

- Azurite is an emulator for Azure Storage supporting Blob, Queue, and Table; Table is in preview.
- Azurite does not support Azure Files or Data Lake Storage Gen2.
- Queue Storage is not Service Bus; Event Hubs, Service Bus, and Cosmos DB have dedicated emulators.
- Use Testcontainers `AzuriteContainer` and `getConnectionString()` so endpoints map properly on the host.
- With Spring Boot, inject dynamic connection strings via `DynamicPropertySource` and create Azure SDK clients in configuration.
- `withCommandOptions("--skipApiVersionCheck")` only bypasses API version validation; it does not add APIs the emulator lacks.
- Basic OAuth is limited and does not prove token signatures or RBAC permissions match real Azure.
- Use an Azure test account for Entra ID, RBAC, Managed Identity, private endpoints, quotas, replication, and cloud-specific features.
- Pin images/SDKs, isolate resources per test, clean up after each test, and avoid logging credentials.

Azurite enables fast testing of Spring Boot adapters and Storage APIs without requiring an Azure subscription on every run. Its value lies in validating supported APIs accurately while clearly recognizing which parts require a real Azure environment. Separating Blob/Queue/Table from Service Bus, Event Hubs, Cosmos DB, and identity services ensures your integration suite reflects the true boundaries of each provider service.

### Official Documentation

- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite)
- [Microsoft Learn — Install and run Azurite emulator](https://learn.microsoft.com/en-us/azure/storage/common/storage-install-azurite)
- [Microsoft Learn — Connect to Azurite with SDKs and tools](https://learn.microsoft.com/en-us/azure/storage/common/storage-connect-azurite)
- [Microsoft Learn — Run automated tests by using Azurite](https://learn.microsoft.com/en-us/azure/storage/blobs/use-azurite-to-run-automated-tests)
- [Microsoft Learn — Azure Blob Storage client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/storage-blob-readme?view=azure-java-stable)
- [Microsoft Learn — Azure Queue Storage client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/storage-queue-readme?view=azure-java-stable)
- [Microsoft Learn — Azure Tables client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/data-tables-readme?view=azure-java-stable)
- [Testcontainers for Java — Azure module](https://java.testcontainers.org/modules/azure/)
- [Azure/Azurite — Supported APIs, OAuth and limitations](https://github.com/Azure/Azurite)
- [Microsoft Learn — Spring Cloud Azure support for Testcontainers](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/testcontainers-support)

Before upgrading the Azure SDK or Azurite, verify the API version sent by the SDK and the support matrix of your pinned image. Azurite, Azure SDK, and Testcontainers module documentation may update on different schedules; enable compatibility flags only after understanding the exact error you are addressing.

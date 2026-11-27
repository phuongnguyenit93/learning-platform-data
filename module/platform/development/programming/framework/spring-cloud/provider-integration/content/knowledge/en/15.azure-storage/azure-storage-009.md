# Using Azurite to Test Emulated Capabilities

## 1. Context and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries. Learners must know how to configure identity and permissions, access storage/messaging/data, protect secrets, write integration tests, and evaluate differences across cloud providers. This lesson belongs to the **Azure Storage** chapter and focuses on **Azurite**—the local Azure Storage emulator—for developing and testing certain operations without connecting to a cloud storage account.

Suppose a Spring Boot API accepts documents, stores files in Blob Storage, and sends jobs via Queue Storage. On every test run, the development team wants to verify upload/download, message send/receive, error handling, and resource cleanup. Provisioning a dedicated Azure storage account for every test run takes time and requires credentials. Azurite provides a local environment to verify these core flows.

After this lesson, you will be able to:

- Clearly state **which services Azurite emulates** and which services/features are unsupported or only partially supported.
- Install and start Azurite with npm or Docker, configuring its workspace and service ports.
- Connect the Azure Storage SDK for Java and Spring Cloud Azure using emulator-specific connection strings.
- Write integration tests for Blob and Queue with isolated data, cleanup, and result verification.
- Integrate Azurite into a CI pipeline for repeatable storage logic checks.
- Distinguish emulator tests from tests on real Azure, especially regarding Microsoft Entra ID, RBAC, networking, Azure Files, lifecycle, tiers, and performance.

## 2. What Is Azurite and What Does It Emulate?

**Azurite** is an open-source emulator developed by Microsoft, running on Node.js, that emulates part of the Azure Storage APIs for local environments. Azurite supports three service groups:

| Service | Default Port | Usage Level in This Lesson |
|---|---:|---|
| **Blob Storage** | 10000 | Testing containers, block blobs, and common blob operations |
| **Queue Storage** | 10001 | Testing queue creation, sending, receiving, updating, and deleting messages |
| **Table Storage** | 10002 | Supported, though currently in **Preview**; verify actual operations |

Azurite is useful for testing code that calls the Azure Storage SDK, upload/download logic, message handling, and basic integration flows. It is not a miniature Azure with full features, SLAs, or production operational characteristics.

### 2.1. What Is Not Emulated

Azurite currently **does not support Azure Files or Azure Data Lake Storage Gen2**. Nor is it an emulator for **Azure Service Bus, Event Hubs, Cosmos DB, Azure SQL**, or other managed services.

| Topic | Can You Use Azurite? | What Environment Is Needed for Full Verification? |
|---|---|---|
| Basic Blob upload/download | Yes | Azure Storage test account to verify service compatibility |
| Blob ETag/conditional requests | Can test operations supported by Azurite | Real Azure to verify all APIs/conditions/versions in use |
| Queue send/receive/delete | Yes | Real Azure to verify permissions, networking, load, and production behavior |
| Table Storage | Yes, though support is Preview | Real Azure Table Storage for required features and reliability |
| Azure Files File Share | No | Azure Files test account/share |
| ADLS Gen2/hierarchical namespace | No | Storage account with ADLS Gen2 enabled |
| Real managed identity and RBAC | Not fully verifiable | Workload identity and role assignments on Azure |
| Lifecycle, access tiers, Archive/rehydration | Cannot substitute real service tests | Properly configured Azure Storage account |
| Firewall/private endpoint/DNS | No | Real Azure networking and storage account |
| Azure Service Bus | No | Test Service Bus namespace |

**Rule:** use Azurite to verify logic and emulated API interactions; use real Azure to verify cloud features, authorization, networking, performance, and operations.

## 3. Architecture for Local Testing

Azurite runs as a separate process or container. Spring Boot connects to local endpoints through the Azure Storage SDK; tests create uniquely named resources, execute operations, and clean up data.

~~~mermaid
flowchart LR
    T[JUnit integration tests] --> A[Spring Boot application]
    A -->|Blob SDK / HTTP| B[(Azurite Blob :10000)]
    A -->|Queue SDK / HTTP| Q[(Azurite Queue :10001)]
    A -->|Table SDK / HTTP| TB[(Azurite Table :10002)]
    B --> W[Local workspace]
    Q --> W
    TB --> W
~~~

Default ports:

- Blob: **http://127.0.0.1:10000**
- Queue: **http://127.0.0.1:10001**
- Table: **http://127.0.0.1:10002**

Azurite defaults to the **devstoreaccount1** account and an emulator-specific account key. Default endpoints place the account name in the **URI path**, for example:

~~~text
http://127.0.0.1:10000/devstoreaccount1/container/blob.txt
http://127.0.0.1:10001/devstoreaccount1/document-jobs
http://127.0.0.1:10002/devstoreaccount1/Tables
~~~

Unlike Azure public cloud, the default account name is not in a hostname like account.blob.core.windows.net. Therefore, use Azurite's connection string/endpoints rather than reusing production endpoints and merely swapping the account name.

## 4. Installing and Starting Azurite

Azurite can be installed via npm, Docker, or the Visual Studio Code extension. The two methods below suit local development and CI.

### 4.1. Installing with npm Locally

Requires Node.js and npm. Install Azurite:

~~~powershell
npm install --global azurite
~~~

Create a data directory and start all three services:

~~~powershell
New-Item -ItemType Directory -Force .\azurite-data | Out-Null
azurite --silent --location .\azurite-data --debug .\azurite-data\debug.log
~~~

Explanation:

- **--location**: workspace storing emulator data; if omitted, Azurite uses the current working directory.
- **--debug**: writes detailed request info and errors to a log file. Enable only for diagnostics; inspect logs before sharing as they may contain request details.
- **--silent**: disables console access logs; does not change data or permissions.
- By default Azurite listens for Blob/Queue/Table on ports 10000/10001/10002.

Check version and options:

~~~powershell
azurite --version
azurite --help
~~~

Keep the terminal running Azurite while testing. When stopped, disk data in azurite-data persists; in-memory mode discards data when the process exits.

### 4.2. Running with Docker on Windows

Create the data directory:

~~~powershell
New-Item -ItemType Directory -Force .\azurite-data | Out-Null
~~~

Start the container, publish ports to loopback, and mount the workspace:

~~~powershell
docker run --rm -p 127.0.0.1:10000:10000 -p 127.0.0.1:10001:10001 -p 127.0.0.1:10002:10002 -v "$((Get-Location).Path)/azurite-data:/data" mcr.microsoft.com/azure-storage/azurite
~~~

The azurite-data volume persists data across container restarts. Without a mounted volume, data stays inside the container filesystem and is lost when the container is removed.

On Linux/macOS, use the same image and adjust the volume path syntax for your shell, for example:

~~~bash
docker run --rm -p 127.0.0.1:10000:10000 -p 127.0.0.1:10001:10001 -p 127.0.0.1:10002:10002 -v "$(pwd)/azurite-data:/data" mcr.microsoft.com/azure-storage/azurite
~~~

In CI, pin the image version when deterministic repeatable builds are needed; avoid letting pipelines silently change behavior when an image tag updates.

### 4.3. Running Only Needed Services

If tests only use Blob, you can run just the Blob service:

~~~bash
docker run --rm -p 127.0.0.1:10000:10000 mcr.microsoft.com/azure-storage/azurite azurite-blob --blobHost 0.0.0.0 --blobPort 10000
~~~

For Docker images, verify the entrypoint and command syntax of the image version in use. Opening only the needed service ports saves resources and prevents endpoint confusion.

## 5. Connecting with the Emulator Connection String

Azurite provides the default devstoreaccount1 account and a fixed account key reserved for emulation. With default ports, the full connection string for Blob and Queue looks like:

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
~~~

If Table is needed, add the endpoint:

~~~text
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
~~~

This is a **well-known public key for the emulator**, not a real Azure account key. Even so, use this connection string only in local profiles/tests; never put it in production configuration or treat it as a pattern for managing cloud secrets.

### 5.1. Dedicated Connection String for Blob

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
~~~

### 5.2. Dedicated Connection String for Queue

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
~~~

Set these strings in local environment variables:

~~~powershell
$env:AZURITE_BLOB_CONNECTION_STRING = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
$env:AZURITE_QUEUE_CONNECTION_STRING = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
~~~

### 5.3. When Spring Boot Also Runs in Docker

Inside an application container, **127.0.0.1 points to the application container itself**, not the Azurite container. When both containers share a Docker network, use Azurite's hostname/service name, e.g., azurite, in the endpoint:

~~~text
BlobEndpoint=http://azurite:10000/devstoreaccount1;
QueueEndpoint=http://azurite:10001/devstoreaccount1;
~~~

If a containerized app needs to reach an emulator running on the host, Docker Desktop typically provides host.docker.internal; verify name resolution on your specific CI/Linux environment. The endpoint in the connection string must be a hostname that **the Spring Boot process can actually reach**, not necessarily the hostname seen by a browser on the host.

## 6. Configuring Spring Cloud Azure with an Azurite Profile

### 6.1. Dependencies

Maven example using the Spring Cloud Azure Blob and Queue starters. Pick a BOM compatible with your project's Spring Boot version:

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

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

spring-cloud-azure.version must be declared per the Spring Boot/Spring Cloud Azure compatibility matrix. Never pick mismatched versions for Azure SDKs managed by the BOM.

### 6.2. Profile application-azurite.yml

Spring Cloud Azure configures connection strings per service:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          connection-string: ${AZURITE_BLOB_CONNECTION_STRING}
          container-name: integration-documents
        queue:
          connection-string: ${AZURITE_QUEUE_CONNECTION_STRING}
          queue-name: integration-jobs
~~~

Important properties:

- spring.cloud.azure.storage.blob.connection-string: connects the Blob SDK to Azurite.
- spring.cloud.azure.storage.queue.connection-string: connects the Queue SDK to Azurite.
- container-name and queue-name: default resources used by auto-configuration when supported by the selected BOM.

Activate the profile when running tests:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "azurite"
~~~

Or use ActiveProfiles("azurite") in Spring Boot tests. Never let this profile activate automatically in production. Real cloud profiles need dedicated endpoints/credentials preferring Microsoft Entra ID/managed identity; the emulator uses a simulated Shared Key connection string.

### 6.3. Injecting Auto-Configured Clients

Once starters and configuration are valid, you can inject Spring Cloud Azure auto-configured Azure SDK clients:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueServiceClient;
import org.springframework.stereotype.Component;

@Component
public class StorageClients {
    private final BlobServiceClient blobServiceClient;
    private final QueueServiceClient queueServiceClient;

    public StorageClients(
            BlobServiceClient blobServiceClient,
            QueueServiceClient queueServiceClient) {
        this.blobServiceClient = blobServiceClient;
        this.queueServiceClient = queueServiceClient;
    }
}
~~~

What to verify in the test context is that the app selected the right profile, loaded the properties, and wired beans pointing to the **local endpoints**. Do not just see beans created and assume the emulator works; execute a real request and verify the result.

## 7. Connecting Directly with Azure SDK for Java

When testing the Azure SDK on its own, you can construct clients from connection strings without a Spring context.

### 7.1. BlobServiceClient

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String connectionString =
        System.getenv("AZURITE_BLOB_CONNECTION_STRING");
if (connectionString == null || connectionString.isBlank()) {
    throw new IllegalStateException("Missing connection string for Azurite Blob");
}

BlobServiceClient blobServiceClient =
        new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
~~~

### 7.2. QueueServiceClient

~~~java
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.QueueServiceClientBuilder;

String connectionString =
        System.getenv("AZURITE_QUEUE_CONNECTION_STRING");
if (connectionString == null || connectionString.isBlank()) {
    throw new IllegalStateException("Missing connection string for Azurite Queue");
}

QueueServiceClient queueServiceClient =
        new QueueServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();
~~~

Clients are reused across operations within the same application/test fixture. Do not recreate the HTTP pipeline and client for each blob or message.

## 8. Integration Tests for Blob Storage

A basic integration test should verify **writing data and reading back the exact content**. Create a dedicated container per test rather than sharing fixed names across parallel tests.

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AzuriteBlobIntegrationTest {
    @Test
    void uploadAndDownloadBlob() {
        String connection =
                System.getenv("AZURITE_BLOB_CONNECTION_STRING");
        BlobServiceClient service =
                new BlobServiceClientBuilder()
                        .connectionString(connection)
                        .buildClient();

        String containerName =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        BlobContainerClient container =
                service.getBlobContainerClient(containerName);
        container.createIfNotExists();

        try {
            BlobClient blob = container.getBlobClient("hello.txt");
            blob.upload(BinaryData.fromString("hello-azurite"), true);

            String actual = blob.downloadContent().toString();
            assertEquals("hello-azurite", actual);
        } finally {
            container.deleteIfExists();
        }
    }
}
~~~

This is an illustrative example; in a complete test class, validate environment variables before building the client and use thorough assertions. downloadContent() loads content into memory, so use it only for small payloads. For large files, use streams or file output and compare checksums/sizes incrementally.

### 8.1. Blob Cases to Test

- Create container, upload blob, and download exact bytes.
- List blobs by prefix and check metadata/Content-Type if those APIs are used.
- Upload duplicate name with overwrite enabled/disabled per business requirements.
- Conditional requests/ETag for operations supported by Azurite.
- Delete blob/container and verify cleanup.
- Errors when container does not exist or resource name is invalid.

Never conclude Azurite has fully verified versioning, lifecycle, tiers, soft delete, or Archive merely because an upload/download test passes. Cloud-service-dependent features must be tested on real Azure.

## 9. Integration Tests for Queue Storage

Queue tests should verify sending, receiving, and deleting using the receive attempt's pop receipt:

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueClientBuilder;
import com.azure.storage.queue.models.QueueMessageItem;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AzuriteQueueIntegrationTest {
    @Test
    void sendReceiveAndDeleteMessage() {
        String connection =
                System.getenv("AZURITE_QUEUE_CONNECTION_STRING");
        String queueName =
                "it-" + UUID.randomUUID().toString().replace("-", "");

        QueueClient queue = new QueueClientBuilder()
                .connectionString(connection)
                .queueName(queueName)
                .buildClient();
        queue.createIfNotExists();

        try {
            queue.sendMessage("{\"jobId\":\"job-42\"}");

            Iterable<QueueMessageItem> received = queue.receiveMessages(1);
            var iterator = received.iterator();
            assertTrue(iterator.hasNext(), "Message must be received");

            QueueMessageItem message = iterator.next();
            assertEquals("{\"jobId\":\"job-42\"}", message.getMessageText());

            queue.deleteMessage(
                    message.getMessageId(),
                    message.getPopReceipt());
        } finally {
            queue.deleteIfExists();
        }
    }
}
~~~

Example checking core queue operations. In real test suites, handle cleanup even if queue creation fails mid-way and avoid sharing queues across parallel tests.

### 9.1. Queue Cases to Test

- Producer sends JSON and consumer reads the exact message body.
- Consumer deletes message with valid message ID/pop receipt.
- Un-deleted message reappears after visibility timeout.
- Update message/visibility and use the new pop receipt per supported APIs.
- Empty queue, non-existent queue, and invalid queue names.
- Oversized messages or mismatched encoding.

Azurite helps verify SDK flows and consumer logic; real Azure remains necessary to validate data-plane roles, throttling, scaling, and service behavior under real load.

## 10. Testing with Spring Boot Test

If the application uses Spring Cloud Azure auto-configuration, include at least one test starting the Spring context with the Azurite profile. Structural example:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.queue.QueueServiceClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@ActiveProfiles("azurite")
class StorageAutoConfigurationTest {
    @Autowired
    BlobServiceClient blobServiceClient;

    @Autowired
    QueueServiceClient queueServiceClient;

    @Test
    void storageClientsAreConfigured() {
        assertNotNull(blobServiceClient);
        assertNotNull(queueServiceClient);
        assertNotNull(blobServiceClient.getBlobContainerClient(
                "integration-documents"));
        assertNotNull(queueServiceClient.getQueueClient(
                "integration-jobs"));
    }
}
~~~

This test only confirms beans and clients are configured. To prove actual connectivity, invoke an operation like getProperties, createIfNotExists, sendMessage, or upload/download and assert the result.

If your application services depend on custom interfaces, you can test services using real clients pointed at Azurite instead of mocking every SDK method. Mocks remain useful for unit-testing failure branches, though they do not verify HTTP serialization, endpoints, or SDK/emulator interactions.

## 11. Data Isolation and Cleanup

Azurite persists data into its workspace by default, so data can survive after tests finish. If every test shares a fixed container/queue, runs can interfere with one another.

Key principles:

1. Prefix resource names with test and a UUID/run ID.
2. Clean up containers, queues, and blobs in finally blocks or lifecycle hooks, even when assertions fail.
3. Never let a test delete containers shared by developers or other test suites.
4. For parallel tests, give each test or worker its own resources.
5. You can wipe the Azurite workspace to reset all data, but only when the emulator is stopped and the workspace is dedicated to tests.
6. Do not use --inMemoryPersistence if you need data to survive restarts; when enabled, all data disappears when the process exits.

One simple strategy is **resource-per-test** for containers/queues, while another is **resource-per-test-run** followed by full suite cleanup. Pick the approach matching your test count and parallelism.

## 12. Integrating Azurite into CI

In CI, Azurite can run as a service/container before tests start. The pipeline must:

- Start Azurite and wait for the Blob/Queue ports to become ready.
- Provide emulator connection strings via environment variables.
- Run Spring Boot/JUnit tests.
- Collect test reports and logs on failure.
- Clean up containers and workspaces after the job.

Example environment variables for the test runner:

~~~text
AZURITE_BLOB_CONNECTION_STRING=<local-blob-connection-string>
AZURITE_QUEUE_CONNECTION_STRING=<local-queue-connection-string>
SPRING_PROFILES_ACTIVE=azurite
~~~

If the test runner executes inside another container, endpoints in connection strings must use the **service/container name** on the shared Docker network rather than 127.0.0.1. If the pipeline allocates dynamic ports, pass the assigned endpoint/port into test config rather than hardcoding.

No real Azure account keys are needed in CI for emulator tests. However, a separate pipeline running **Azure integration tests** needs dedicated identities/credentials, least-privilege roles, and a test storage account isolated from production.

## 13. Limitations You Must Know Before Trusting Test Results

Azurite is built for development and testing and carries no performance or scale guarantees matching Azure Storage. Key differences:

| Limitation | Impact on Testing |
|---|---|
| Only emulates Blob, Queue, and Table; Table is Preview | Do not use to verify Azure Files, ADLS Gen2, or production-grade Table features |
| Some APIs/headers/parameters are not fully supported | Passing tests do not prove every real Azure operation will pass |
| Error messages may differ from Azure, even when status codes match | Never depend on error message strings for business classification |
| No performance guarantees, cannot handle production-scale client concurrency | Never use for throughput, latency, or scale benchmarks |
| Default account uses simulated Shared Key | Does not prove production managed identity/RBAC works |
| Basic OAuth only checks select claims like issuer, audience, expiry; does not verify token signatures or permissions | Never treat this as a Microsoft Entra ID security test |
| Runs on local network | Does not emulate Azure firewalls, private endpoints, DNS, routing, TLS trust, or failover |
| Does not emulate Service Bus | Cannot test topics, subscriptions, sessions, DLQs, or Service Bus transactions |

### 13.1. Strict Mode, Loose Mode, and API Version

Azurite defaults to strict mode, rejecting unsupported headers/parameters. The **--loose** flag makes the emulator ignore certain unsupported elements:

~~~bash
azurite --loose
~~~

Use loose mode only when you have a specific compatibility testing reason. Never enable it merely to make tests pass, as doing so can hide invalid requests sent by your application.

Azurite also validates request API versions. **--skipApiVersionCheck** skips version validation, though it does not mean the emulator implements that entire API version. When upgrading the SDK, verify which API versions and operations Azurite supports; if differences affect functionality, add an Azure integration test.

### 13.2. OAuth and Identity Testing Limits

Azurite has a basic OAuth option and requires HTTPS when OAuth is enabled. This mode can validate select token claims such as issuer, audience, and expiry, yet **does not verify token signatures or principal permissions** the way real Azure Storage does.

Consequently, a test using a Shared Key connection string with Azurite only proves the client can talk to the emulator. It does not prove:

- Managed identity is properly attached to App Service/VM/Container Apps.
- Storage Blob Data Contributor or Storage Queue Data Message Processor roles are assigned to the right principal/scope.
- Storage firewalls/private endpoints allow the workload.
- SAS tokens have the right permissions, expiry, and scope on real Azure.

All of those must be tested against a real, properly configured Azure test environment.

## 14. Two-Tier Testing Workflow

A sound workflow for Spring Cloud Azure has two tiers:

~~~mermaid
flowchart TD
    A[Code change] --> B[Unit tests: mock business logic]
    B --> C[Integration tests with Azurite]
    C --> D{Basic Blob/Queue APIs pass?}
    D -->|No| E[Fix logic, config, serialization]
    E --> C
    D -->|Yes| F[Azure integration tests]
    F --> G{RBAC, network, cloud features pass?}
    G -->|No| H[Fix identity, policies, endpoints, or operations]
    H --> F
    G -->|Yes| I[Review and release per workflow]
~~~

| Test Layer | Tools/Environment | Question Answered |
|---|---|---|
| Unit tests | JUnit + mocks/fakes | Is validation, retry, mapping, and idempotency logic correct? |
| Local storage integration | Azurite | Does the SDK hit the right endpoints and do basic upload/receive/metadata flows work? |
| Azure integration | Test storage account | Do RBAC, managed identity, SAS, firewall, lifecycle, and versioning/tiers work? |
| Load/performance | Near-production Azure test environment | What are throughput, latency, concurrency, throttling, and costs? |
| Recovery/operations | Azure staging and runbooks | Do data recovery, rehydration, error handling, and operational observability meet requirements? |

Not every commit must run the full Azure integration suite; you can run fast unit + Azurite tests on each pull request, then run cloud integration on the main branch or a schedule. Before releasing any feature relying on cloud-specific behavior, however, you must have evidence from real Azure.

## 15. Common Errors and Diagnostics

| Symptom | Common Causes | Remediation |
|---|---|---|
| Connection refused on port 10000/10001 | Azurite not running or service port not open | Check process/container and port mappings |
| Spring Boot fails connecting to 127.0.0.1 in Docker | Localhost points to the app container itself | Use service hostname or host gateway |
| HTTP 404 calling Blob/Queue | Wrong endpoint path/account name or resource not created | Check connection string and resource names |
| Authentication failed | Malformed connection string, missing endpoint, or mismatched custom account key | Use default devstore account or configure matching account/key |
| Unsupported API version | SDK uses an API version Azurite does not yet emulate | Update compatible Azurite/SDK or test the operation on real Azure |
| Flaky Table tests | Table API is still Preview or operation unsupported | Scope tests carefully and verify on real Azure Table Storage |
| Passes alone, fails in parallel | Shared container/queue/blob names | Generate unique names per test/run |
| Stale data appears in later runs | Workspace persisted on disk | Clean up resources or reset dedicated test workspace |
| Tests pass but production returns 403 | Azurite does not enforce production RBAC | Check principal, roles, scope, and network on Azure |
| Fast upload/download locally, slow in cloud | Emulator does not represent cloud performance and network | Load-test on Azure staging |
| Loose mode makes tests pass | Emulator ignores unsupported headers/parameters | Remove loose mode and verify the operation on Azure |

When debugging, record the endpoint, operation, status code, Azure request ID if present, and SDK/Azurite versions. Never log real account keys, SAS tokens, or sensitive content. For detailed local debugging, enable --debug locally and review logs before sharing.

## 16. Practice Exercises and Self-Check Questions

**Exercise 1 — Start Azurite:** Install via npm or Docker, persist the workspace to a dedicated directory, and confirm Blob/Queue/Table ports are listening. Use Storage Explorer to inspect containers and queues after running tests.

**Exercise 2 — Blob round-trip:** Write a JUnit test that creates a random container, uploads a small file, downloads it, and compares bytes. Afterward, verify the container was deleted.

**Exercise 3 — Queue messages:** Write a test that sends JSON, receives the message, verifies the body, and deletes using message ID/pop receipt. Extend it to demonstrate a message reappearing when not deleted and the visibility timeout expires.

**Exercise 4 — Spring profile:** Create application-azurite.yml with separate Blob/Queue connection strings. Boot the Spring context with ActiveProfiles("azurite") and verify injected client beans can execute a request.

**Exercise 5 — CI:** Run Azurite as a container service in a pipeline. Ensure the test runner waits until the emulator is ready, uses the right hostname on the Docker network, and cleans up resources.

**Exercise 6 — Scope mapping:** List features your project uses: Blob, Queue, Files, Service Bus, RBAC, lifecycle, Archive. Mark which can be tested with Azurite and which must be tested on Azure.

### Self-Check Questions

1. **Which services does Azurite support?** Blob Storage, Queue Storage, and Table Storage; Table is in Preview.
2. **Does Azurite support Azure Files?** No. File Share requires a real Azure Storage account for integration testing.
3. **Can Azurite test Service Bus?** No. Service Bus requires a dedicated test namespace.
4. **Why shouldn't you use a 127.0.0.1 connection string when the app runs in another container?** Because localhost points to the app's own container; use the Docker network hostname or host gateway instead.
5. **What is Azurite's default account?** devstoreaccount1 with the emulator-specific account key and local endpoints.
6. **Do passing Azurite tests prove RBAC is configured properly?** No. Role assignments and managed identities must be verified on real Azure.
7. **Should you use loose mode just so all tests pass?** No. It can ignore unsupported headers/parameters and mask API discrepancies.
8. **Can Azurite benchmark production throughput?** No. Azurite has no performance guarantees or scale comparable to Azure.
9. **Why use unique resource names per test?** So parallel tests and persisted workspace data do not interfere with each other.
10. **When are Azure integration tests required?** When features depend on Entra ID/RBAC, Files, ADLS Gen2, lifecycle/tiers, networking, performance, or cloud-specific behavior.

## 17. Summary

Azurite shortens the development loop by providing a local environment for **Blob Storage, Queue Storage, and Table Storage**. With Spring Boot, you can connect via the Azure Storage SDK for Java or Spring Cloud Azure using emulator connection strings, then write integration tests covering upload/download, message send/receive, and core flows. Resource names should be isolated, data cleaned up, and the Azurite profile kept separate from production.

Azurite has clear limits: **Table is in Preview; Azure Files and ADLS Gen2 are unsupported; basic OAuth does not verify signatures/permissions like Azure; performance and error behaviors are not guaranteed to match the cloud**. Combine unit tests, Azurite integration tests, and Azure integration tests to thoroughly validate both application logic and real identity, RBAC, networking, and managed features.

### Official References

- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
- [Microsoft Learn — Install and run Azurite](https://learn.microsoft.com/azure/storage/common/storage-install-azurite)
- [Microsoft Learn — Connect to Azurite with SDKs and tools](https://learn.microsoft.com/azure/storage/common/storage-connect-azurite)
- [Microsoft Learn — Run automated tests by using Azurite](https://learn.microsoft.com/azure/storage/blobs/use-azurite-to-run-automated-tests)
- [Microsoft Learn — Azure Storage configuration properties for Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-storage)
- [Microsoft Learn — Azure Storage Queue configuration properties for Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-storage-queue)
- [Microsoft Learn — Azure Storage Blob configuration properties for Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/configuration-properties-azure-storage-blob)

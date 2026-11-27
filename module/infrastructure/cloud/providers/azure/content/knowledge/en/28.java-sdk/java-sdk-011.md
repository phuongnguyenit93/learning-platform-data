# Integration Testing the SDK with Emulators and Test Resources

In the **CLOUD_PROVIDERS_AZURE** module, we explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data. The goal is to know how to deploy, monitor, secure, and control the costs of an application architecture on Azure. In the **Azure SDK for Java** chapter, this lesson presents how to perform **integration testing** for Java applications using the Azure SDK with **local emulators** and **controlled Azure test resources**.

Consider an `order-ingestion` service written in Java 17/Spring Boot: when receiving an order, the application uploads the receipt to Azure Blob Storage, sends a job to Azure Queue Storage, and then a worker reads the queue and records the status. Unit tests can mock `BlobClient` and `QueueClient` to verify business logic; however, mocks do not prove that the SDK actually **serializes requests, signs authentication, creates blobs, reads metadata, or handles HTTP errors** correctly. Testing directly against a production storage account is dangerous and time-consuming. Therefore, multiple testing layers with **different assurance scopes** are required.

After this lesson, you will be able to:

- Distinguish between **unit tests, contract tests, emulator integration tests, cloud integration tests, and end-to-end smoke tests**.
- Choose the appropriate emulator: **Azurite** for Azure Storage Blob/Queue/Table; consider **Cosmos DB Emulator**, **Event Hubs Emulator**, or **Service Bus Emulator** when they support the exact features you need to test.
- Create a Blob Storage client using the Azure SDK for Java, write **JUnit 5 integration tests** that perform real reads/writes with Azurite, and use **Testcontainers** to provision isolated test containers.
- Configure clients via environment/endpoint/credential settings instead of hard-coding production connection strings.
- Provision dedicated real Azure resources for testing, using **DefaultAzureCredential/managed identity, Microsoft Entra ID, and Azure RBAC** properly on the data plane.
- Design fixtures, isolation, idempotent cleanup, deadline-bounded retry/polling, negative tests, CI/CD, budgets, and runbooks.
- Understand the limitations of emulators and which behaviors **must be verified on real Azure services** before release.

## 1. What does an Azure SDK “integration test” actually verify?

A meaningful integration test must cross **at least one real integration boundary**: SDK serialization, HTTP/AMQP protocol, service endpoint, credential, storage semantics, or retry mechanism. If a test only returns a mocked response from `BlobClient`, it is primarily a **unit test**, even if the class under test is named `AzureStorageIntegrationService`.

```text
                         Java Source Code
                                |
                      Business logic + adapters
                                |
          +--------------------+-------------------+
          |                    |                   |
          v                    v                   v
      Unit tests       Emulator integration   Real Azure integration
      Fake ports       Azure SDK -> Azurite   Azure SDK -> test resource
      Fast/offline      Protocol & basic I/O  IAM/network/quotas/service
          |                    |                   |
          +--------------------+-------------------+
                                |
                           Release gates
                                |
                      Production deployment
```

### 1.1. Different failure classes

| Failure class | Mock/unit | Emulator | Real Azure resources |
|---|---|---|---|
| Business DTO mapping, validation | Very suitable | Possible | Possible, but usually more expensive |
| Building SDK request/response, reading Blob content | Not guaranteed | Good if the feature is supported | Yes |
| Azure identity, token audience, RBAC | Logic can be faked, Azure not verified | Usually **no** | **Mandatory** |
| Private Endpoint, DNS, TLS CA/hostname | No | Local emulator is not equivalent | **Mandatory** |
| Quotas, throttling, scale limits | Fake errors can be injected | Only partially | **Mandatory evaluation** |
| Geo-replication, availability zones, failover | Not real | Incomplete | Test only in authorized environments/processes |
| Eventual consistency, real concurrency | Only partially | Depends on emulator | Yes |
| New Azure service APIs/features | No | May not be supported yet | Verify in actual tier/region |

**There is no “single green test” covering every risk.** Emulators provide fast, repeatable runs; test resources on Azure reveal gaps caused by cloud features, permissions, infrastructure, configuration, and service contracts.

### 1.2. Test the application, not just “ping Azure”

A proper Blob upload test must verify **both the read-back data**, metadata, key/path, exceptions when not found, and cleanup. Checking only HTTP 201 or a mock `upload()` invocation is not enough. For Queue, verify that messages can be read, processed, deleted, or become visible again according to semantics; do not infer exactly-once business processing from `sendMessage()`.

## 2. A pragmatic testing pyramid for the Azure SDK for Java

| Layer | Where it runs | Goal | Suggested frequency |
|---|---|---|---|
| **Unit/contract test** | JVM with fakes/mocks | Business rules, mapping, validation, retry classifier | Every commit/PR |
| **Emulator integration** | Local Docker/Testcontainers | HTTP/serialization/data operations, basic error handling | Every PR if container runtime is available |
| **Cloud integration** | Test subscription/resource group | Identity, RBAC, endpoint, TLS, real API/feature behavior | Nightly, pre-release, or critical PRs |
| **End-to-end smoke** | Production-like staging | App→Azure dependency→worker→output, telemetry | Before release/deploy |
| **Resilience/performance** | Dedicated environment | Throttling, failover, high concurrency, cost | Scheduled separately, not every PR |

### 2.1. Why not run every test on real Azure?

Provisioning storage/database/messaging resources on every commit can introduce **cost, latency, quota contention, flaky networking, leftover data**, and secret exposure risks. Emulators are faster and do not require internet access once images/dependencies are cached. However, running only locally misses errors such as a **Managed Identity lacking a data-plane role** or misconfigured private endpoint firewalls.

### 2.2. Tests decide the path of an error

For example, when a service fails with `403 AuthorizationPermissionMismatch`:

- Unit tests verify that the application maps the error to the appropriate exception/reporting.
- Azurite tests verify local Shared Key connection strings and Blob operations; they **do not** verify Entra RBAC.
- Real Azure tests authenticate with the intended identity, verify role scope and tokens, and perform Blob reads/writes.
- Staging smoke tests verify that the workload running on AKS/App Service connects through production-like networking and policies.

### 2.3. Contract tests for Azure SDK versions

The SDK is a dependency whose HTTP API version, response parsing, and retry implementation can change. You need to **pin/lock versions** via the Maven BOM and CI, and review release notes when upgrading. Unit tests on fakes only verify business code; emulator and cloud tests detect incompatibilities when upgrading the SDK or changing API behavior.

## 3. Emulator landscape and key limitations

There is no single “Azure emulator” that simulates all Azure services completely. Each emulator is a separate product/utility with its own scope and version constraints.

| Azure service | Local tool | What can be tested | Key limitations |
|---|---|---|---|
| **Blob/Queue/Table Storage** | **Azurite** | CRUD, HTTP request/response, basic authentication/emulated storage semantics | Does not cover all features/API versions, Entra RBAC, replication, lifecycle, or cloud network/quotas |
| **Azure Cosmos DB for NoSQL** | Cosmos DB Emulator (supported editions/OS/containers) | Document CRUD, queries, basic partition-key behavior | Differs from cloud in throughput, consistency, multi-region, feature parity, and certificates |
| **Azure Event Hubs** | Event Hubs Emulator when a compatible edition is available | Publish/consume, consumer groups, protocol basics | Limited namespaces/features, throughput/quotas, capture, and cloud IAM |
| **Azure Service Bus** | Service Bus Emulator when a compatible edition is available | Selected queue/topic and AMQP message workflows | Does not fully replace SKU features, HA, networking/RBAC, quotas, or version-specific scheduled/advanced features |
| **Azure Functions local** | Azure Functions Core Tools + emulators supporting triggers/bindings | Running function code, testing selected bindings with Azurite | Does not fully simulate hosting/scaling/identity/networking |
| **Azure SQL Database** | SQL Server/container or a dedicated test database | Basic SQL schema/queries and JDBC | Azure-specific behavior, geo-HA, Entra/networking, and service limits differ |
| **Key Vault, Entra ID, Private Link, Azure RBAC** | Fakes/local contract tests, or real Azure test resources | Testing application logic through abstractions | No emulator fully replaces Azure authentication/authorization and networking |

**You must verify the support status and feature matrix of the exact emulator version** before choosing tests; do not assume the word “Emulator” means 100% compatibility with the managed service. There are cases where a newer Azure SDK uses a service API not yet supported by the released emulator.

### 3.1. Why is Azurite the starting point?

Azurite is easy to use for creating Blobs/Queues/Tables with local endpoints and a development account. It is well suited for learning how to build **real tests through the Azure Storage SDK**. However, Azurite cannot test **managed identity, Azure RBAC, private endpoints, Azure Storage redundancy, Azure Monitor, or production-level throttling**.

### 3.2. How the Cosmos DB Emulator differs from a mock repository

The Cosmos emulator can partially test **SQL API for NoSQL, partition keys, request serialization, and query logic**. It **does not** guarantee the same RU charges, indexing costs, distributed replication, consistency levels, or regional failover as real Azure Cosmos DB. For cost/performance, cloud tests with RU/latency metrics are still required.

### 3.3. Messaging emulators and message transport

Event Hubs and Service Bus are two different products. **Event Hubs** is optimized for event streaming/partitions/consumer offsets; **Service Bus** is optimized for enterprise messaging queues/topics, locks, settlement, DLQs, and other workflows. Do not use one service’s emulator to prove the semantics of the other. Check the compose/config/support matrix for your version before integrating into Testcontainers.

### 3.4. What about features without an emulator?

Write **contract tests** using fakes for application behavior, and maintain minimal **cloud integration tests** on resources with scoped permissions, cost caps, and cleanup. Do not invent a “good enough” fake Key Vault/RBAC emulator as an excuse to skip cloud tests.

## 4. Designing testable Java code with dependency injection

An anti-pattern:

```java
public final class OrderService {
    public void save(String orderId, byte[] bytes) {
        // Wrong: creating a client and embedding storage credentials in a business method.
        String connectionString = "AccountKey=<production-secret>";
        // new BlobServiceClientBuilder().connectionString(...).buildClient();
        // ...
    }
}
```

This is hard to unit test, leaks credentials, risks accidentally connecting to production, and recreates clients repeatedly. You should separate the **port (business contract)** from the **Azure SDK adapter**.

### 4.1. Business port

```java
public interface DocumentStore {
    void put(String key, byte[] content);
    byte[] get(String key);
    boolean exists(String key);
    void delete(String key);
}
```

`DocumentStore` is an interface **defined by the application itself**, not a built-in API from the Azure Storage SDK. Unit tests use an in-memory fake; integration tests use a real `AzureBlobDocumentStore`.

### 4.2. Adapter using the Azure SDK

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobClient;

public final class AzureBlobDocumentStore implements DocumentStore {
    private final BlobContainerClient container;

    public AzureBlobDocumentStore(BlobContainerClient container) {
        this.container = container;
    }

    @Override
    public void put(String key, byte[] content) {
        BlobClient blob = container.getBlobClient(key);
        blob.upload(BinaryData.fromBytes(content), true);
    }

    @Override
    public byte[] get(String key) {
        return container.getBlobClient(key)
                .downloadContent()
                .toBytes();
    }

    @Override
    public boolean exists(String key) {
        return container.getBlobClient(key).exists();
    }

    @Override
    public void delete(String key) {
        container.getBlobClient(key).deleteIfExists();
    }
}
```

This adapter is intentionally brief: production needs **timeout/retry policies, metadata, content type, key validation, logging, authorization, overwrite semantics, and cancellation**. Still, this separation allows tests to run the exact same business code against both an emulator and real Azure.

### 4.3. Inject clock/ID generators

Testing retries, token expiration, SAS expiry, or TTLs should not use `Thread.sleep(60_000)`. Use `java.time.Clock`, injectable ID generators, and fake schedulers for unit tests. With real services, you cannot simulate **all server-side time** with a Java Clock, so keep a small set of integration tests operating within a realistic time budget.

### 4.4. Do not rely on a single global connection string in tests

Instead of service classes calling `System.getenv("AZURE_STORAGE_CONNECTION_STRING")` in every method, construct the client **once at the composition root** based on the `test profile/emulator profile/staging profile`. Ensure the emulator profile can never accidentally pick up a production secret due to an identically named environment variable.

## 5. Preparing Java, Maven, and test libraries

The examples use **Java 17+**, Maven, **Azure Storage Blob SDK**, **Azure Identity**, JUnit Jupiter, and Testcontainers. Choose compatible versions verified for your JDK/CI runner; do not arbitrarily mix `azure-core` and SDK versions.

### 5.1. Core dependencies

```xml
<!-- POM fragment; declare versions through a tested Azure SDK BOM. -->
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure</groupId>
      <artifactId>azure-sdk-bom</artifactId>
      <version>${azure.sdk.bom.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>testcontainers-bom</artifactId>
      <version>${testcontainers.version}</version>
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
  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>${junit.jupiter.version}</version>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

The Maven properties `azure.sdk.bom.version`, `testcontainers.version`, and `junit.jupiter.version` must be defined using **actual tested versions** in your project. This is a **fragment**, not a complete POM; you need to configure Maven compiler, Surefire/Failsafe, and dependency lifecycles for your environment. Do not infer that any specific version is the latest or supported solely from this lesson.

### 5.2. Conventions for running tests

A common convention:

- `*Test.java`: fast unit tests.
- `*IT.java`: integration tests on an emulator or Azure.
- JUnit 5 `@Tag("emulator")` and `@Tag("azure")` for categorization.
- Maven Surefire/Failsafe or corresponding Gradle tasks select the right test group.

What matters is that **CI runs the right group**, not just the filename suffix. CI configuration must fail if a critical test is skipped due to missing Docker/credentials rather than letting the pipeline report green.

### 5.3. Checking Docker

Azurite/Testcontainers requires a compatible container runtime (Docker Engine, Podman in a supported configuration, or an equivalent runner). Testcontainers needs access to the daemon/runtime; in CI, avoid running overly privileged Docker on the same runner that holds production secrets.

## 6. Azurite: running the Azure Storage emulator locally

Azurite provides default endpoints for storage services:

| Service | Common local endpoint | Purpose |
|---|---|---|
| Blob | `http://127.0.0.1:10000/devstoreaccount1` | Object/file operations |
| Queue | `http://127.0.0.1:10001/devstoreaccount1` | Storage queue messages |
| Table | `http://127.0.0.1:10002/devstoreaccount1` | Table entities |

These are the **default addresses/ports** in local Azurite mode. When running containers/Testcontainers with dynamic port mapping, **host/port values may differ**. Do not treat local HTTP emulator mode as a production standard: real Azure must use TLS and proper authentication.

### 6.1. Running with Docker

```bash
docker run --rm --name azurite-it \
  -p 127.0.0.1:10000:10000 \
  -p 127.0.0.1:10001:10001 \
  -p 127.0.0.1:10002:10002 \
  mcr.microsoft.com/azure-storage/azurite:latest
```

The example binds only to host loopback so the emulator is not exposed to the LAN. In CI systems, **pin a tested image tag/digest** instead of always using `latest`; configure volumes/persistence if needed for investigation, though test isolation generally prefers ephemeral data. Do not expose the Azurite account to the Internet; the development account uses a **public well-known key**, not a production secret.

### 6.2. Development storage account

Azurite normally uses the development account `devstoreaccount1` and the **well-known dev key** published in Azurite documentation. A local connection string typically looks like:

```text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=<Azurite-development-account-key>;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
```

**This is formatted across multiple lines for readability**; when used in an environment variable, it must be a **single continuous string** without line breaks. Retrieve the exact dev key from Azurite documentation/tested configuration; do not guess or bring a real Azure storage account key to the emulator. Some SDKs/tooling also accept `UseDevelopmentStorage=true` depending on their capabilities; with the Azure Storage SDK for Java, using **explicit endpoint connection strings** is usually less ambiguous in tests.

### 6.3. Separating the test environment with variables

```bash
# Never commit a production account key into source code.
export AZURITE_BLOB_CONNECTION_STRING="<single-line-Azurite-connection-string>"
export AZURE_INTEGRATION_TARGET="emulator"
```

PowerShell has different environment variable assignment syntax than Bash; CI should inject values from an appropriate settings/secret provider. Even though this is a public dev key, **name variables clearly and validate endpoints** so a generic variable name never accidentally reads a real account.

### 6.4. Azurite and API-version mismatches

The SDK may default to calling a newer service API version than Azurite currently supports. When seeing `UnsupportedApiVersion` errors or requests rejected by the emulator, **do not jump to the conclusion that the Java code is broken or that real Azure will fail**. Update/pin a compatible Azurite version; if you use “loose” mode for debugging, never treat it as proof of parity. Reserve cloud integration tests for features not yet simulated by the emulator.

## 7. Connecting the Java SDK to Azurite: Blob round-trip example

This code uses the **synchronous Blob SDK** to create a container, upload, download, and clean up data. It makes real calls to Azurite’s HTTP endpoint; no mocked `BlobClient` is used.

### 7.1. Sample Java code

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.UUID;

public final class AzuriteRoundTrip {
    public static void main(String[] args) {
        String connectionString = Objects.requireNonNull(
                System.getenv("AZURITE_BLOB_CONNECTION_STRING"),
                "Set AZURITE_BLOB_CONNECTION_STRING before running");

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();

        String containerName =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        BlobContainerClient container =
                service.getBlobContainerClient(containerName);
        container.createIfNotExists();

        try {
            byte[] original = "Hello Azure SDK".getBytes(
                    StandardCharsets.UTF_8);
            String key = "receipts/order-1042.txt";

            container.getBlobClient(key).upload(
                    BinaryData.fromBytes(original), true);
            byte[] downloaded = container.getBlobClient(key)
                    .downloadContent().toBytes();

            if (!java.util.Arrays.equals(original, downloaded)) {
                throw new AssertionError("Content mismatch");
            }
            System.out.println("Blob round-trip passed");
        } finally {
            // Delete only the randomized container created by this test.
            container.deleteIfExists();
        }
    }
}
```

To run this, you need the `azure-storage-blob` dependency, a running Azurite instance, and the environment variable set to the proper **local connection string**. Do not call `container.deleteIfExists()` on a container not owned by the test: the name here is a **unique test-owned resource**.

### 7.2. Expected verification outcomes

A proper round-trip must:

1. Successfully create the container and receive a response from the service/emulator.
2. Upload bytes under the exact key.
3. Download back and compare **actual content**, not just the status code.
4. Clean up data even if an assertion or SDK call fails.
5. Never print connection strings/keys to logs.

### 7.3. What else should be tested?

- Uploading without overwrite when the blob already exists.
- Downloading a non-existent blob returns the corresponding error.
- Content type/metadata are persisted and read back accurately.
- Blob names with Unicode characters, spaces, or slashes are encoded properly by the SDK.
- Blob size boundaries (small, empty, large within test limits).
- Upload/download streams interrupted mid-transfer.
- Conditional writes using ETag/`If-Match` if business logic requires preventing lost updates.
- Deleting and verifying not-found afterward.

Do not copy real customer/PII data into a local emulator just to inflate fixture sizes. Use generated/synthetic bytes.

## 8. JUnit 5: writing a real integration test

The template below uses a pre-started Azurite instance and the `AZURITE_BLOB_CONNECTION_STRING` environment variable. If the env var is missing, the test **fails explicitly** instead of self-skipping; this prevents CI from turning “green” when integration tests never actually ran.

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import com.azure.storage.blob.models.BlobStorageException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@Tag("emulator")
class BlobStoreAzuriteIT {
    private BlobContainerClient container;
    private AzureBlobDocumentStore store;

    @BeforeEach
    void setUp() {
        String cs = System.getenv("AZURITE_BLOB_CONNECTION_STRING");
        assertNotNull(cs, "Azurite must be configured in CI");
        assertTrue(cs.contains("127.0.0.1")
                        || cs.contains("localhost"),
                "Refusing a non-local emulator endpoint");

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(cs)
                .buildClient();
        String testName =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        container = service.getBlobContainerClient(testName);
        container.createIfNotExists();
        store = new AzureBlobDocumentStore(container);
    }

    @AfterEach
    void tearDown() {
        if (container != null) {
            container.deleteIfExists();
        }
    }

    @Test
    void shouldUploadAndReadRealBlob() {
        byte[] expected =
                "integration-check".getBytes(StandardCharsets.UTF_8);
        String key = "invoices/order-1042.txt";

        store.put(key, expected);

        assertTrue(store.exists(key));
        assertArrayEquals(expected, store.get(key));
    }

    @Test
    void shouldReturnNotFoundFromStorageService() {
        BlobStorageException ex = assertThrows(
                BlobStorageException.class,
                () -> container.getBlobClient("not-there.txt")
                        .downloadContent());

        assertEquals(404, ex.getStatusCode());
    }

    @Test
    void shouldDeleteExistingBlob() {
        store.put("temp.txt", new byte[]{1, 2, 3});
        assertTrue(store.exists("temp.txt"));
        store.delete("temp.txt");
        assertFalse(store.exists("temp.txt"));
    }
}
```

**This JUnit 5 code uses the adapter from section 4**, so both classes and Maven dependencies must be included in your lab project before running. The `localhost` condition is only an **illustrative guard** for Azurite running directly on the same machine; do not use this guard for Testcontainers/remote CI runtimes where the Docker host has a different hostname. In production-quality tests, verify **target kind and allowlisted resource IDs/endpoints** rather than just checking hostname substrings.

### 8.1. Three isolation principles

- **Unique resource names:** containers and blob keys have random suffixes so parallel tests do not collide.
- **No shared mutable state:** tests read/write only their own data without depending on test execution order.
- **Guarded cleanup:** delete only resources created by the test, even on failure, and have mechanisms to handle leftover artifacts if a CI job is killed.

### 8.2. Why is testing 404 useful?

The SDK must parse the error response into a `BlobStorageException` with a status code. That is a **real contract over HTTP** that a mock `when(blob.downloadContent()).thenThrow(...)` cannot verify. However, real Azure services may still differ from emulators in error codes, rate limits, or authorization behavior, so cloud tests remain necessary.

### 8.3. How much parallelism is safe for tests?

When each test creates a randomized container, most CRUD tests can run in parallel. However, **account-level quotas**, container listings, transient conflicts, or unsafe static shared clients can cause flakiness. For tests writing to the same blob, create explicit **barriers/coordination** if you want to test true concurrency rather than relying on scheduler luck.

## 9. Testcontainers: managing Azurite lifecycle for tests

When CI runs on a runner with Docker, **Testcontainers** starts Azurite before tests, maps dynamic ports, and stops it afterward. The advantage is avoiding reliance on local port `10000` being free or expecting the operator to start the service manually.

### 9.1. JUnit + Testcontainers example

```java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.nio.charset.StandardCharsets;
import java.util.Objects;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@Tag("emulator")
class BlobTestcontainersIT {
    @Container
    static final GenericContainer<?> AZURITE =
            new GenericContainer<>(
                    DockerImageName.parse(
                            "mcr.microsoft.com/azure-storage/azurite:latest"))
                    .withExposedPorts(10000);

    private static BlobContainerClient container;

    @BeforeAll
    static void init() {
        // Use the exact published built-in dev account key for Azurite.
        // Value must come from test config, not a production key.
        String devKey = Objects.requireNonNull(
                System.getenv("AZURITE_DEV_ACCOUNT_KEY"),
                "AZURITE_DEV_ACCOUNT_KEY must hold the Azurite dev key");

        String endpoint = "http://" + AZURITE.getHost() + ":"
                + AZURITE.getMappedPort(10000) + "/devstoreaccount1";
        String cs = "DefaultEndpointsProtocol=http;"
                + "AccountName=devstoreaccount1;"
                + "AccountKey=" + devKey + ";"
                + "BlobEndpoint=" + endpoint + ";";

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(cs)
                .buildClient();

        String name =
                "it-" + UUID.randomUUID().toString().replace("-", "");
        container = service.getBlobContainerClient(name);
        container.createIfNotExists();
    }

    @AfterAll
    static void cleanUp() {
        if (container != null) {
            container.deleteIfExists();
        }
    }

    @Test
    void blobRoundTripOverMappedPort() {
        String key = "samples/greeting.txt";
        String content = "Hello Testcontainers";
        container.getBlobClient(key).upload(
                BinaryData.fromBytes(content.getBytes(
                        StandardCharsets.UTF_8)), true);
        assertEquals(content,
                container.getBlobClient(key)
                        .downloadContent().toString());
    }
}
```

The example uses `latest` **only to illustrate syntax**; CI must **pin an image digest/tag** confirmed to support the SDK/service API version. `AZURITE_DEV_ACCOUNT_KEY` must match Azurite’s published default key – do not generate a random value and expect the emulator to accept it. With a **custom Azurite account** configuration, the same account/key must be configured on both the container side and the connection string.

### 9.2. Docker host and dynamic port mapping

Testcontainers returns `getHost()` and `getMappedPort(10000)`, because the host port is not necessarily 10000. Do not hard-code `localhost:10000` in tests when running CI with Docker-in-Docker or a remote daemon. If the SDK sees an unexpected redirect or hostname, inspect emulator endpoint settings, Docker networking, and proxies.

### 9.3. Ensuring the container is “ready”

Typically Testcontainers waits for container startup, but complex images/services may need a **wait strategy** based on documented logs/HTTP endpoints/ports. With Azurite, avoid a hard 15-second sleep as a long-term solution; configure tests to wait for readiness and fail with clear causes. For Service Bus/Event Hubs Emulators with multiple dependent containers, healthchecks/compose readiness are even more critical.

### 9.4. Reuse containers or create fresh ones?

- Local developers may enable container reuse to speed up runs **if data is reset and configurations stay consistent**.
- CI should favor clean environments, unique resource names, and zero reliance on stale state.
- Never let suites mutate the same queue/container and fail randomly.
- Tests requiring complete cleanliness should create new account/container names or reset emulator data safely.

### 9.5. Why not auto-skip when Docker is unavailable?

An integration gate must **fail with a “Docker unavailable” message** if CI requires that group to run. You can separate an `emulator-it` job and make it optional on developer laptops, but a release pipeline must never report “verified integration” when all emulator tests were disabled/skipped.

## 10. Expanding Blob tests: metadata, ETags, and real errors

Building on the basic adapter, add these cases:

### 10.1. Content type and metadata

An uploaded PDF document should have `Content-Type: application/pdf`. Otherwise, consumers/CDNs/downloads may handle it incorrectly. Tests should:

1. Upload a Blob with `BlobHttpHeaders` and metadata.
2. Read `BlobProperties` from the emulator.
3. Assert the actual content type/metadata.
4. Run a small cloud test to catch API/feature differences.

Example:

```java
import com.azure.storage.blob.models.BlobHttpHeaders;

var blob = container.getBlobClient("receipts/1042.pdf");
blob.upload(BinaryData.fromBytes(new byte[]{1, 2, 3}), true);
blob.setHttpHeaders(
        new BlobHttpHeaders().setContentType("application/pdf"));

assertEquals("application/pdf",
        blob.getProperties().getContentType());
```

This is a **test snippet** assuming `container` and JUnit assertions exist, not a standalone class. A 3-byte payload is not a valid PDF; use a synthetic PDF fixture if testing a file-format pipeline, though dummy bytes suffice for testing SDK metadata handling.

### 10.2. Optimistic concurrency with ETag

Two writers updating a blob concurrently can overwrite each other. If a workflow must prevent lost updates, use conditional requests `If-Match: ETag` via supported API overloads, and test:

```text
Writer A GET properties -> ETag E1
Writer B writes new version -> ETag E2
Writer A uploads with If-Match E1
  -> expect precondition error, do not overwrite B
```

In the Azure SDK for Java, ETag conditions are typically placed in `BlobRequestConditions`/options depending on method/version. Choose the **exact overload** and assert the SDK’s precondition error code rather than faking it by reading an ETag and performing an unconditional upload.

### 10.3. Testing overwrite semantics

An invoicing application must avoid losing older documents. Verify:

- Initial upload succeeds.
- Uploading the same key with overwrite disabled returns the expected conflict error per contract.
- When a legitimate update occurs, use version/ETag rather than enabling overwrite indiscriminately.
- Unit tests verify business policies and integration tests verify HTTP conditional operations.

### 10.4. Testing valid resource naming

Azure Blob container names have strict format requirements (lowercase, hyphens, valid length), while Blob names follow different rules. Use a generator for valid container names and assert negative tests with invalid names. Do not rely solely on the emulator for all naming/service limits; real cloud tests should verify limits affecting business flows.

## 11. Queue Storage: different semantics from Blob and different tests

Azure Queue Storage is a simple queue; it **does not guarantee business exactly-once processing**. Receiving a message makes it **temporarily invisible**, and the worker must delete it with the appropriate `messageId` and `popReceipt`. If a worker crashes before deleting, the message can reappear and be processed repeatedly.

### 11.1. Proper flow

```text
Java API --sendMessage--> Azure Queue
                                 |
                           Worker receive
                                 |
                           Mark invisible
                                 |
                     Process idempotently
                                 |
                      Delete using pop receipt
                                 |
                         Success / audit
```

### 11.2. Java Queue SDK snippet

```java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueClientBuilder;
import com.azure.storage.queue.models.QueueMessageItem;

import java.util.Iterator;

String cs = System.getenv("AZURITE_QUEUE_CONNECTION_STRING");
QueueClient queue = new QueueClientBuilder()
        .connectionString(cs)
        .queueName("it-work-items")
        .buildClient();

queue.createIfNotExists();
queue.sendMessage("job-1042");

Iterator<QueueMessageItem> messages =
        queue.receiveMessages(1).iterator();

if (!messages.hasNext()) {
    throw new AssertionError("Expected one queued message");
}

QueueMessageItem item = messages.next();
// Business processing requires idempotency, not just printing the message.
queue.deleteMessage(item.getMessageId(), item.getPopReceipt());
```

This is a **fragment** using the additional `azure-storage-queue` dependency from the BOM and a dedicated lab queue. The connection string and queue name must be test-owned; this snippet omits queue cleanup so learners can observe state, but real tests must clean up using `queue.deleteIfExists()` after verification. Depending on SDK version, class names, overloads, or message content structure may vary; check the API in use.

### 11.3. Mandatory Queue tests

| Test | Action | Assertion |
|---|---|---|
| Happy path | Send → receive → delete | Queue no longer contains the message after delete |
| Worker crash | Receive, do not delete, wait for visibility timeout | Message can be received again |
| Duplicate | Send the same business job ID multiple times | Worker produces only one business effect |
| Poison message | Malformed/unsupported payload | No infinite retries; quarantine/poison handling applies |
| Queue empty | Receive when queue is empty | App does not crash or report false errors |
| Expiry | Message TTL expires | Expired message is not processed |
| Scale workers | Multiple consumers | Do not assume strict ordering or exactly-once delivery |

**Avoid long sleeps for timeout tests** on every PR. Unit test state machines with a fake clock, integration test short visibility timeouts within service-supported bounds, and run dedicated cloud tests for critical cases.

### 11.4. Differences from Service Bus

Azure Queue Storage lacks full enterprise messaging features of **Azure Service Bus** such as sessions, dead-letter subqueues, duplicate detection, or Service Bus-level settlement semantics. Do not copy test assertions from `ServiceBusReceiverClient.completeMessage()` over to `QueueClient.deleteMessage()` and assume both systems behave identically.

## 12. Azure Table Storage and Azurite

Azurite also simulates **Table Storage** within its supported feature scope. With Java, use the **Azure Data Tables SDK** (typically the `azure-data-tables` artifact) to test entity CRUD, `PartitionKey`/`RowKey`, OData queries, and ETag updates.

### 12.1. Entity model

```text
Table: DeviceReadings
  PartitionKey = "site-hcm-02"
  RowKey       = "device-0042-20261120T0900"
  TemperatureC = 4.2
  Status       = "HEALTHY"
```

Table Storage is not the same as **Azure Cosmos DB for NoSQL**, even though both use the term “partition”. Indexing, partition strategies, request units, consistency, and query languages differ.

### 12.2. Key tests

- Create and delete a unique test table.
- Insert an entity with `PartitionKey` + `RowKey`.
- Read the entity with the exact key.
- Query by partition, filter, and paginate if supported by the API.
- Inserting a duplicate key produces a conflict per contract.
- ETag conditional update does not overwrite a stale version.
- Missing-entity errors and data type serialization.

### 12.3. Do not extrapolate Azurite to all production features

The Table SDK may invoke newer features/service API versions not supported by the pinned Azurite release. Real storage accounts also enforce auth/RBAC, quotas, and network restrictions. For features with business impact such as within-partition batch transactions or ETag concurrency, add a real cloud test before release.

## 13. Azure Cosmos DB Emulator for the Java SDK

The **Azure Cosmos DB Emulator** lets you partially test the Azure Cosmos DB for NoSQL API on supported local machines/containers. Installation and startup depend on **emulator version, OS, image, and Docker/Windows support**. Therefore, this lesson does not dictate a single fixed Docker command for every environment.

### 13.1. What tests can prove

| Behavior | Suitable for emulator? | Requires additional cloud verification |
|---|---|---|
| Serialize POJO to JSON item | Yes | SDK/service API compatibility |
| Create, read, replace, delete item | Yes for supported APIs | IAM, networking, account consistency behavior |
| Partition key passed properly | Yes | Real partition distribution/throughput/skew |
| Basic SQL queries and pagination | Yes | Query RUs, indexing, cross-partition costs |
| Optimistic concurrency via ETag | Yes for supported features | Real concurrency and retries under load |
| RU charges, autoscale, multi-region replication | Not fully representative | **Mandatory cloud** |
| Private Link, Entra authorization, CMK | Incomplete | **Mandatory cloud** |

### 13.2. Java Cosmos SDK: client injection

For the Java Cosmos NoSQL SDK, the client is typically built from an endpoint and credential according to the SDK/version:

```java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;

String endpoint = System.getenv("COSMOS_TEST_ENDPOINT");
String key = System.getenv("COSMOS_TEST_KEY");

CosmosClient client = new CosmosClientBuilder()
        .endpoint(endpoint)
        .key(key)
        .gatewayMode()
        .buildClient();

try {
    // Create test database/container, write/read items,
    // assert partition key, ETag, and query results here.
} finally {
    client.close();
}
```

This **fragment** uses the `azure-cosmos` dependency and applies only to a **key-based emulator/test account** per supported version. For real Azure with Entra authentication, use the appropriate credential overload/role assignment rather than hard-coding an account key. **Cosmos DB data-plane RBAC differs from Azure management-plane RBAC**; a resource Contributor does not automatically gain CRUD permissions on items.

### 13.3. Self-signed emulator certificate

Some Cosmos Emulators expose an HTTPS endpoint with a **development certificate** that the Java truststore must trust per version instructions. An `SSLHandshakeException` against the emulator should never be “fixed” by enabling TLS trust-all in production code. Configure the truststore **only for the test/emulator runtime** and never bundle a development CA into production truststores.

### 13.4. Direct vs. gateway mode

The Cosmos Java SDK can support both **Gateway** and **Direct** connection modes depending on the API/SDK. Emulator/container/firewall environments may require Gateway; cloud production may use a different mode suited to networking and performance. An emulator test over Gateway does not prove Direct mode to real Azure works through firewalls/private endpoints; cloud integration tests must use the **same mode intended for deployment**.

### 13.5. Partition key tests must go beyond the happy path

If a container is partitioned by `/tenantId`, tests should cover:

- Same `id` across two different tenants according to key/ID semantics.
- Reading an item with the exact partition key.
- Queries missing the partition key causing fan-out/cost per service semantics.
- Wrong partition key does not mistakenly return an item.
- ETag conflict when updating an item.
- Duplicate `id + partitionKey` does not create two records.
- Delete/recreate and verify idempotency.

**Do not use emulator RU/s or latency as sizing criteria for production Cosmos DB.** RU request charges, indexing costs, autoscale, and hot partitions must be measured on an appropriate cloud tier.

## 14. Service Bus Emulator: testing messaging within scope

When using the Azure Service Bus SDK for Java (`azure-messaging-servicebus`), you can use the Microsoft-released **Service Bus Emulator** if the **features/SKU/version** match. Specific emulator releases may require **Docker Compose**, queue/topic/subscription config, and auxiliary services such as a SQL Server container; do not write a generic “`docker run servicebus`” and expect everything to work.

### 14.1. Workflows to test

```text
Producer (ServiceBusSenderClient)
          |
          | messageId, correlationId, payload
          v
Service Bus queue / topic-subscription
          |
          v
Consumer (ServiceBusReceiverClient)
          |
          +-- complete on success
          +-- abandon/retry on transient failure
          +-- dead-letter on poison message per policy
```

### 14.2. Sample Java receiver with a business boundary

```java
// Illustrative fragment: ServiceBusReceiverClient already created via
// ServiceBusClientBuilder according to SDK and test connection config.
var messages = receiver.receiveMessages(1);

for (var message : messages) {
    String logicalId = message.getMessageId();
    try {
        // Business layer must be idempotent by logicalId.
        processIdempotently(logicalId, message.getBody().toBytes());
        receiver.complete(message);
    } catch (PermanentInvalidPayloadException ex) {
        receiver.deadLetter(message);
    } catch (Exception transientFailure) {
        receiver.abandon(message);
    }
}
```

The methods/types above are an **application fragment**: `processIdempotently` and `PermanentInvalidPayloadException` are project-defined; `receiver` is configured per the supported API/version using **PEEK_LOCK** mode for settlement. Depending on the specific SDK version/overload, you may need to adjust how `Iterable`/receiver mode is obtained; verify against docs and run integration tests before copying to production.

### 14.3. Emulator tests do not replace cloud feature tests

Features such as **sessions, duplicate detection, scheduling, transactions, premium networking, geo-DR, quotas, RBAC, and message sizes** may be partially supported or unsupported depending on emulator version. Build a **feature matrix** against the capabilities you actually use. If production relies on sessions or Premium-specific capacity, you need proper **real Azure Service Bus tests**.

### 14.4. Settlement does not mean exactly-once

If a worker writes to Azure SQL and crashes before `complete`, the message can be redelivered. You need an **idempotency key/inbox** in the database; an emulator can test delivery retries, but **cannot substitute for business invariants** and cloud failover behavior.

### 14.5. Service Bus Emulator requires test environment safeguards

- Do not use the production namespace’s connection string.
- Use dedicated namespaces/configs/test queues; do not delete queues shared by other developers.
- Pin compose images and resource configs.
- Wait for dependency readiness, not just container process startup.
- Ensure CI cleans up containers/volumes within job scope.

## 15. Event Hubs Emulator: producer/consumer and checkpoints

**Azure Event Hubs** handles high-throughput event streaming; the Java SDK typically uses `azure-messaging-eventhubs` and `EventProcessorClient`/a checkpoint store for consumer groups. The Event Hubs Emulator helps test some publish/consume flows locally, but you must use a **supported emulator image/config**, often with Compose-documented dependencies.

### 15.1. Suitable test cases

1. Producer sends batches with valid event IDs and partition keys.
2. Dedicated consumer group reads events and verifies payload/correlation.
3. Checkpoints are persisted via an appropriate checkpoint store, if supported by the emulator/config.
4. Restart consumer and verify resume behavior in the test.
5. Handle duplicates/late events idempotently.
6. Stop consumer to simulate processing lag and measure recovery.

### 15.2. Do not confuse checkpoints with broker ACKs

A consumer that receives an event and checkpoints too early before crashing prior to writing to the database can **lose processing** from the application’s perspective. Conversely, writing to the database successfully without checkpointing can cause the event to be reprocessed after a restart. Use an **idempotent sink** and clearly define commit/checkpoint boundaries.

### 15.3. What must be tested in the cloud

- Real throughput units/capacity limits and throttling.
- Multi-partition load balancing/scale-out across consumer groups.
- Network/private endpoints, Entra authorization, and configured SAS policies.
- Event Hubs Capture/retention/namespace tier-specific features.
- Availability/failover/region/network behavior per architecture.

Do not scale laptop emulator throughput directly into the number of partitions or throughput units to purchase on Azure.

### 15.4. Distinguishing Event Hubs Emulator from Azurite

Event Hubs Emulator is **not** a module inside Azurite. They can be combined in Docker Compose for a workflow that checkpoints on Blob Storage, but each emulator’s feature support is separate. Each container must have its own endpoints/credentials and readiness checks.

## 16. Azure Functions Core Tools with emulators

An Azure Function written in Java can run locally using **Azure Functions Core Tools** (or compatible plugin tooling). Triggers/bindings such as Blob/Queue can use **Azurite** for certain scenarios; `local.settings.json` usually holds local connection settings read by the Functions runtime.

### 16.1. Test diagram

```text
JUnit / HTTP client
       |
       v
Local Azure Functions host (Java function)
       |
       +-- Blob/Queue binding --> Azurite
       |
       +-- Business service --> test database/fake
       |
       v
Assertions on real blob/queue state
```

### 16.2. Key limitations

- The local Functions host **does not fully simulate** Azure Functions scaling, consumption plans, storage/networking/managed identity.
- Trigger batching/locking/retries and extensions have their own versions and host settings.
- Local settings and secret values **must not** be committed to the repository.
- A passing local integration test does not prove an Azure deployment has correct app settings, VNet integration, or RBAC.

### 16.3. Testing the right boundary

If a Function is Queue-triggered, you can test **send → trigger runs → observed Blob/DB output**. Calling the Java function handler directly only unit tests the function logic and does not verify queue triggers, bindings, or the runtime host.

## 17. Services that should not be fully emulated

Some integrations require real Azure:

- **Key Vault**: authentication and secrets/certificate permissions, firewalls/private endpoints, versioning, and rotation.
- **Microsoft Entra ID / managed identity**: tenant, audience, token scopes, and RBAC.
- **Azure App Configuration**: labels, feature flags, refresh, and auth.
- **Azure SQL / PostgreSQL Flexible Server**: database identity, firewalls, TLS, networking, HA.
- **AKS workload identity**: federated credentials, service account claims, token exchange.
- **Storage encryption/network controls**, geo-redundancy, and service feature gating.

For unit tests, you can fake credential providers/client adapters to verify behavior, but **never claim Azure IAM “has been tested”** when only mocking `DefaultAzureCredential` to return a dummy token.

### 17.1. Contract tests with HTTP stubs

When no emulator exists, an HTTP stub (WireMock or a custom test server) can verify that the **app sends expected paths/headers/bodies and handles status codes**. However, it does not verify service-side policies, DNS, token audiences, throttling, or API-specific nuances. Label these clearly as **contract/stub** tests, not cloud integration.

### 17.2. Where are fake providers useful?

- Clock/UUID/retry schedulers for controlling time.
- Secret providers for testing rotation logic.
- Blob/Queue ports for verifying business orchestration.
- Command receivers for injecting timeouts, conflicts, throttling, and network resets.
- Metrics/tracing sinks for asserting that secrets are never logged.

Fakes must never mask the real service name in test reports: it must be clear whether a test used a **fake, an emulator, or Azure**.

## 18. When is testing on real Azure resources mandatory?

**Green emulator tests do not mean cloud-ready.** Once code passes unit/emulator tests, the following checks must run in a subscription/resource group **containing no production workloads**:

1. **Microsoft Entra ID authentication** from the intended principal/runtime.
2. **Azure data-plane RBAC** for least-privilege read/write/delete access.
3. Correct **TLS, endpoints, hostnames, and DNS**, especially with Private Endpoints/VNets.
4. Actual **service API versions, feature support, regions, and tiers**.
5. **Timeouts/retries/quotas** under expected load and configuration.
6. Real **concurrency/ETag** or messaging lock/settlement behavior when required by business logic.
7. **Observability**: traces/logs/metrics and cloud error classification.
8. **Cost**: bytes scanned, request units, message operations, compute, and resource lifecycle.

You do not necessarily need to run **every** case on every PR. However, if production relies on a cloud feature **without an emulator**, there must be a periodic cloud test or release gate verifying it.

### 18.1. Choosing a dedicated test subscription

A sound design:

```text
Azure tenant
  |
  +-- Non-production subscription / billing scope
         |
         +-- rg-sdk-it-<run-id>
         |      |
         |      +-- storage account created by IaC
         |      +-- temporary test queue/blob container
         |      +-- narrow RBAC role assignments
         |
         +-- central test logs/budget policy
```

You can use an **ephemeral resource group per test run** or team-shared resources with a **dedicated test resource namespace per run**. The choice depends on provisioning speed, cost, quotas, and cleanup reliability. Shared accounts reduce startup time but must prevent tests from deleting each other’s data.

### 18.2. Do not test against production using a “test” label

A container named `test-container` inside a production storage account **still impacts production**: it can be affected by RBAC, policies, logging, quotas, billing, and erroneous cleanup. Require a **resource ID allowlist**, subscription ID validation, and CI guardrails. Never rely solely on developer-chosen “test” names.

### 18.3. Tests should match production closely without overspending

Cloud test accounts should match production on the properties that govern correctness: **service API, network model, TLS, identity mode, tier features**. There is no need to copy production data volumes or sensitive payloads to verify a Blob upload. Performance/scale tests can run in a separate approved environment.

## 19. Provisioning test Azure Storage with a clear lifecycle

The Bash/Azure CLI example below is strictly a **lab provisioning script**. You must be logged into the proper non-production subscription, hold resource creation permissions, and configure appropriate budgets/quotas. **Never execute directly against a production subscription**.

### 19.1. Creating the resource group and storage account

```bash
az login
az account set --subscription "<non-production-subscription-id>"
az account show --output table

RUN_SUFFIX="<unique-lowercase-digits-suffix>"
REGION="southeastasia"
RG="rg-sdk-it-$RUN_SUFFIX"
STORAGE="stsdk$RUN_SUFFIX"

# Storage account name: globally unique, lowercase/numeric, 3..24 chars.
az group create \
  --name "$RG" \
  --location "$REGION" \
  --tags purpose=sdk-integration-test owner=data-platform environment=testing

az storage account create \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --location "$REGION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2 \
  --https-only true

STORAGE_ID=$(az storage account show \
  --resource-group "$RG" \
  --name "$STORAGE" \
  --query id -o tsv)

echo "Created a test-owned account ID; verify before using:"
echo "$STORAGE_ID"
```

Choose a region/tier supported by the current subscription. **These are billable resources**, even when labeled “test”; Azure Storage accounts, transactions, diagnostic logs, and networking can incur charges. For accounts with **deny-by-default** network policies or Private Endpoints, the script must apply corresponding IaC network/identity setups before tests can connect.

### 19.2. Granting a data-plane role to the test principal

```bash
IDENTITY_OBJECT_ID="<object-id-of-test-service-principal-or-managed-identity>"

az role assignment create \
  --assignee-object-id "$IDENTITY_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$STORAGE_ID"
```

This role is only an example for **Blob CRUD tests** and should not be granted at subscription scope. If tests require Queue Storage, assign the appropriate **Queue** data-plane role rather than assuming Blob Data Contributor grants queue access. **RBAC assignments have propagation delay**: tests should distinguish between role propagation lag and code bugs by polling with a bounded deadline.

### 19.3. Guarding resource deletion

After running tests and collecting logs:

```bash
# Verify naming/constraints before deleting.
case "$RG" in
  rg-sdk-it-*) echo "Expected test RG prefix" ;;
  *) echo "Refusing to delete non-test RG"; exit 1 ;;
esac

# Delete only the RG actually created by this job, in the verified subscription.
az group delete --name "$RG" --yes
```

**Prefixes are not the only safety mechanism.** In CI, record `run_id, subscription_id, resource_group_id` from the provisioning step, verify owner tags/manifests, and use a principal scoped solely to test RGs. If cleanup runs in a separate job, do not delete simply by matching “all RGs starting with rg-sdk-it-”; another job might still be using one.

### 19.4. Risk of failed cleanup

Processes/runners can be killed before `finally`/post steps run. Implement a **scheduled janitor or TTL policy** for temporary resources, deleting based on **owner, run ID, creation timestamp, and age** after ensuring no active test is running. Never strip resource locks or delete resources not owned by the job just to hit “zero leaked resources”.

## 20. DefaultAzureCredential on a cloud test account

On real Azure, applications should use **token-based authentication** whenever supported by the service/SDK. Blob SDK example:

```java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String account = System.getenv("AZURE_TEST_STORAGE_ACCOUNT");
if (account == null || !account.startsWith("stsdk")) {
    throw new IllegalStateException(
            "Only the allowlisted integration-test account may be used");
}

String endpoint = "https://" + account + ".blob.core.windows.net";
DefaultAzureCredential credential =
        new DefaultAzureCredentialBuilder().build();

BlobServiceClient service = new BlobServiceClientBuilder()
        .endpoint(endpoint)
        .credential(credential)
        .buildClient();
```

`DefaultAzureCredential` is a **credential chain**: on developer laptops it may select Azure CLI/IDE credentials; in cloud CI/deployments it may select workload identity/managed identity or other credentials depending on environment/version. **Tests must verify the actual selected tenant, subscription, and principal**; otherwise, tests may “succeed” under a developer identity instead of the intended production identity.

### 20.1. Emulators usually cannot replace identity tests

Local Azurite uses a **development Shared Key**/selected auth modes; it **does not simulate Azure RBAC/managed identity** equivalently to real accounts. Consequently, Azure client factories often need separate paths:

```text
Emulator profile:
  explicit local connection string + Azurite endpoint

Cloud test profile:
  HTTPS account endpoint + explicit intended TokenCredential
  + service data-plane RBAC role assignment

Production profile:
  HTTPS/Private Endpoint + managed/workload identity
  + least privilege + policy + observability
```

Never switch production to account keys just because Azurite tests require keys. That weakens security and defeats the purpose of cloud integration testing.

### 20.2. Separating credentials from SDK adapter logic

Inject a pre-configured `BlobServiceClient` or `BlobContainerClient` into the adapter instead of embedding `DefaultAzureCredentialBuilder` inside every business method. Tests can then inject an Azurite client, cloud test client, or fake port depending on the layer.

### 20.3. Real workload identity must be tested in AKS

With AKS Workload Identity, the service account token must match the **federated credential issuer, subject, audience**, managed identity/client ID, and data-plane RBAC. Unit tests cannot verify this trust exchange. Staging deployment tests should run pods with the exact workload identity pattern, verifying token acquisition and Blob operations **from inside the pod**, not just from an operator’s laptop.

### 20.4. Azure RBAC differs from API authorization

Cloud integration tests might pass because the identity holds `Storage Blob Data Contributor`, yet the web application must still enforce **tenant/document ownership** so one customer cannot read another customer’s Blob. Unit/business tests for authorization and cloud tests for data-plane permissions provide **two distinct guarantees**.

## 21. Cloud integration tests: safety and isolation

A solid cloud test must define:

- **Resource ownership:** which resources the test created, who owns them, and when they are deleted.
- **Target allowlist:** subscription/resource group/account IDs.
- **Principal identity:** tenant/object ID, expected role, and scope.
- **Test namespace:** container/key prefixes with run IDs to avoid touching other data.
- **Data classification:** synthetic fixtures only, never copy production PII.
- **Cost budget:** limits on requests/data volumes/compute/test duration.
- **Failure policy:** does an auth/network failure fail the gate or trigger a retry?
- **Cleanup guarantee:** `try/finally`, CI post steps, and a periodic janitor.

### 21.1. A cloud test reusing the adapter

```java
@Tag("azure")
@Test
void shouldRoundTripInRealTestStorage() {
    BlobServiceClient service = buildCloudTestBlobClient();
    String runId = java.util.UUID.randomUUID()
            .toString().replace("-", "");
    String containerName = "it-" + runId;

    // buildCloudTestBlobClient must validate resource ID/tenant
    // and allow only test accounts before returning a client.
    BlobContainerClient container =
            service.getBlobContainerClient(containerName);
    container.createIfNotExists();

    try {
        DocumentStore store =
                new AzureBlobDocumentStore(container);
        byte[] data = "cloud-integration".getBytes(
                java.nio.charset.StandardCharsets.UTF_8);
        store.put("samples/check.txt", data);
        assertArrayEquals(data, store.get("samples/check.txt"));
    } finally {
        container.deleteIfExists();
    }
}
```

This is a **JUnit method fragment** (imports and the application’s `buildCloudTestBlobClient` are omitted). Do not rely on a weak account name check like `startsWith("stsdk")` as your sole safeguard; in a real implementation, enforce **subscription/resource ID allowlists, principal scoping, and deny-by-default**.

### 21.2. Negative tests for RBAC

Simply verifying that a principal can upload does not prove least privilege. Include:

| Principal | Test | Expected |
|---|---|---|
| **Writer test identity** | Upload/download Blob in test container | Succeeds |
| **Read-only test identity** | Download Blob | Succeeds |
| **Read-only test identity** | Upload/delete Blob | Denied by data-plane RBAC |
| **No-role test identity** | Read/write Blob | Denied |
| **Wrong tenant/principal** | Authenticate/access | Denied, no fallback to shared key |

Do not attempt negative testing by temporarily revoking roles from a production identity. Use **dedicated test principals**, scoped test resources, controlled propagation checks, and assert expected statuses/errors. A request blocked by a firewall does not prove RBAC deny works properly: distinguish auth failures from network denials.

### 21.3. Role propagation and valid retry allowances

After `az role assignment create`, the data plane can take time to reflect new permissions. Provisioning tests may **poll permissions** up to a bounded deadline, but never retry all `403` responses indefinitely. If the deadline expires, report clearly: “RBAC not effective / wrong principal or scope” for operator investigation.

### 21.4. Cleaning up cloud data safely

A test should delete only the `it-<runId>` container it created itself. When running in parallel inside a shared storage account, **never run `az storage container delete --name $CONTAINER_FROM_CONFIG`** where `$CONTAINER` might point to production or another team’s data. Track ownership IDs in a manifest rather than inferring from names.

## 22. Private Endpoints, TLS, and DNS must be tested from the actual runtime

A cloud test running on a developer laptop with public network access does not prove an AKS application connecting through a Private Endpoint will succeed.

```text
Developer laptop -> Public Blob endpoint -> success

AKS workload -> Private DNS -> Private Endpoint -> Storage
                         |
                         +-- NSG / routes / firewalls
                         +-- DNS resolution
                         +-- TLS hostname verification
                         +-- Managed identity
```

### 22.1. Baseline checks on the real runtime

1. Verify DNS resolution from the **pod/VM/Function** used in staging.
2. Confirm the SDK endpoint FQDN matches the certificate and private DNS.
3. Verify TCP/TLS handshake and service responses.
4. Confirm identity/tokens/data-plane RBAC.
5. Run a small fixture upload/download.
6. Monitor connection resets, proxy settings, and SNAT/NAT pressure under load.

### 22.2. Never disable TLS to make tests pass

Local Azurite uses HTTP by default, whereas real Azure uses HTTPS. **Never** enable “trust all certificates”, disable hostname verification, or downgrade TLS in production profiles just because the local emulator ran over HTTP. If an emulator uses an HTTPS dev certificate, isolate the truststore strictly to the test environment.

### 22.3. Network-denied tests

You can write negative tests in staging using a principal/runner **outside the permitted network** to confirm the account firewall denies access per policy. Never arbitrarily modify firewall rules on shared resources and cause outages; use dedicated resources and approved IaC.

## 23. Data safety: fixtures, namespaces, and cleanup

### 23.1. Fixtures must be synthetic

Do not upload real invoices, production user tokens, medical records, or sensitive full logs to emulators or test Azure subscriptions. Generate synthetic bytes/JSON structured closely enough to business payloads to verify serialization and encoding.

```json
{
  "orderId": "IT-1042",
  "customerId": "synthetic-customer-7",
  "amount": 150000,
  "currency": "VND",
  "traceId": "integration-test-42"
}
```

### 23.2. Do not rely on the current clock for unique keys

Two tests running within the same second can generate identical container/key names. Use a **UUID or sufficiently random run ID** with length/character guards conforming to Azure resource naming rules, and log the namespace clearly in test reports.

### 23.3. Do not delete before collecting failure evidence

Cleanup can erase evidence needed for debugging. In CI:

- Retain **logs/test reports/trace IDs** securely.
- If failing test data must be preserved, move it to test-only artifact storage with TTL and access controls.
- Never leave containers around indefinitely simply because an assertion failed.
- Enforce policies preventing PII/secrets from entering saved artifacts.

### 23.4. Idempotent teardown

`deleteIfExists()` is safer than `delete()` when cleanup may run repeatedly. If network cleanup fails, log resource IDs and let the janitor handle them. **Never swallow all cleanup exceptions and report leak-free**: tests might stay green while bills silently grow from undeleted resources.

### 23.5. Isolation on shared resources

Shared resources must enforce structured isolation:

```text
account: stsdksharedtest
container: it-run-8f2a...   # owned by a single CI run
blob path: suite-orders/<test-case-id>/...
tags/metadata: owner, runId, expiresAt
```

If queues/tables/databases lack suitable namespacing or tests require account-wide configuration changes, provision **dedicated resources** instead of running concurrently against a shared namespace.

## 24. Failure injection: testing when the SDK encounters errors

A system working cleanly against a healthy emulator does not prove it recovers properly from **HTTP timeouts, 429 throttling, 503 service unavailable, network resets, or lost responses after a server-side write**. Failures must be simulated at the **appropriate layer**.

### 24.1. Where to inject faults?

| Injection point | Tool/test type | Best suited for |
|---|---|---|
| Business port | Fake `DocumentStore` or Mockito | Validation, fallbacks, and exception mapping |
| HTTP boundary | Local stub/WireMock or custom test `HttpClient` | Error status/headers, request timeouts, retry classifiers |
| Network | Toxiproxy or lab network fault tools | Disconnects, latency, connection resets |
| Emulator service | Stop/restart Azurite container, test configs | Client reconnect and errors when service is unavailable |
| Real Azure test | Resource policies/controlled throttling where authorized | RBAC, 429, service-specific behavior |
| Application worker | Kill process at deterministic steps in staging | Idempotency, checkpoints, duplicate delivery |

Ask **which failure mode you need to prove**. If you only need to verify mapping 404 to `DocumentNotFoundException`, you do not need to stop a container. If you need to know whether retrying after a lost ACK causes duplicate billing, unit tests alone are insufficient.

### 24.2. Key error codes

- **400/InvalidRequest:** malformed payload/schema/headers; usually requires a code fix.
- **401/Authentication:** invalid or expired token/credential; do not retry blindly.
- **403/Authorization:** data-plane role, scope, network policy, or permission issue; inspect the error code.
- **404/NotFound:** missing resource; could be an expected business outcome or a config bug.
- **409/Conflict:** resource already exists, optimistic concurrency conflict, or state conflict depending on API.
- **412/PreconditionFailed:** ETag/If-Match unsatisfied; refresh state rather than blindly overwriting.
- **429/TooManyRequests:** throttling; apply backoff retry policies and honor service hints when supported.
- **5xx:** potentially transient, but for **writes with side effects**, treat outcomes as indeterminate.
- **Timeout/connection reset:** distinguish whether failure occurred before sending, during transmission, or after service processing.

This is a **general classification pattern**. Each Azure service has distinct response codes, error codes, `Retry-After` headers, and behaviors; do not apply one blanket whitelist across all SDKs.

### 24.3. SDK retries do not replace business idempotency

Azure SDKs usually include retry policies in their HTTP pipelines/service clients. However, if a Blob/Queue write loses its ACK, the app cannot know whether the server executed it. **Never enable unbounded retries** for operations that incur costs, emit messages, or write to databases.

Example:

```text
Java producer
  |
  | send queue message (businessKey=order-1042)
  v
Azure Queue
  |
  | message accepted
  |
  X lost response
  |
Java times out, retries send
  |
  v
Queue may contain 2 messages with the same businessKey
```

The solution is an **idempotent consumer**, unique business keys/inbox stores, and duplicate handling—not just tweaking `QueueClient` retry counts.

### 24.4. Deadline-bounded retry tests

A sound policy requires:

1. **Max attempts** and **max elapsed time**; never loop forever.
2. Exponential backoff + jitter where applicable.
3. Honoring `Retry-After` when returned by the service and supported by the API.
4. Never sleeping while holding unnecessary DB transactions/worker locks.
5. Distinguishing idempotent reads from non-idempotent writes.
6. Handling cancellation/interruption cleanly when requests are aborted.
7. Logging attempt count/error code/correlation ID without exposing credentials.

Use a **fake clock/scheduler** to unit test retry logic; keep a few integration tests with network faults to confirm SDK behavior. Never run heavy fault-injection loads against shared Azure resources.

### 24.5. Do not over-assert rigid SDK internals

A test stating “the SDK must retry exactly 3 times in 210ms” becomes brittle across SDK/config upgrades and flaky due to scheduling variance. Assert **outcomes and bounded budgets**: attempt counts stay within your configured policy, commands produce no duplicate side effects, and latency stays within environment tolerances.

### 24.6. Fault injection must never weaken production TLS

To test SSL failures, use a separate test certificate/truststore or an HTTPS stub with a test CA; never ship `trustAllCerts=true` code that could accidentally reach production. Network faults may only be injected in approved lab/staging environments.

## 25. Async SDKs, concurrency, and resource lifecycles

The Azure SDK for Java provides both **sync and async** client types; several use Reactor/Netty and HTTP transports. Testing must align with your application’s threading/reactive model.

### 25.1. Async tests must subscribe and await

Anti-pattern:

```java
// Wrong if this returns a lazy Mono/Flux:
asyncBlobClient.upload(data, true); // Not subscribed/awaited.
// Test exits with no assertion on the actual result.
```

Depending on SDK overloads and `data` sources, this is **conceptual pseudocode**. With Reactor publishers, operations normally execute only upon subscription; tests must use `StepVerifier` or `block(Duration)` in test code with a timeout to avoid hanging.

### 25.2. Reactor test example

```java
// Illustrative fragment: async client and Mono<byte[]> returned by adapter.
import reactor.test.StepVerifier;
import java.time.Duration;

StepVerifier.create(documentStoreAsync.get("samples/check.txt"))
        .expectNextMatches(bytes ->
                java.util.Arrays.equals(bytes, expected))
        .expectComplete()
        .verify(Duration.ofSeconds(10));
```

`documentStoreAsync` is an **application-defined** adapter and `expected` is a fixture. Running this requires `reactor-test` in test dependencies; do not assume `BlobAsyncClient` directly exposes `get(String)` as shown. Keep Reactor callback logic non-blocking on the event loop and avoid `Thread.sleep` inside reactive pipelines.

### 25.3. Closing resources and shutting down background threads

An integration test can pass yet prevent the JVM from exiting because Reactor schedulers, Event Hubs processors, AMQP receivers, Cosmos clients, or custom executors remain alive. Design teardown cleanly:

- Stop event processors/receivers according to lifecycle hooks.
- Dispose subscriptions/cancel in-flight operations.
- Close `CosmosClient`/messaging clients/HTTP resources where supported by the SDK.
- Wait for graceful shutdown with a bounded deadline.
- Check for thread/resource leaks in CI when running multiple suites.

Never call `System.exit(0)` in tests to mask an unclosed client.

### 25.4. Concurrency tests must assert invariants

For instance, two writers concurrently updating a Blob with ETags. Tests establish a **synchronization barrier** so both read the same version before racing to update:

- Expect **exactly one writer** to succeed when using conditional writes.
- The other writer receives a precondition conflict per contract.
- The final Blob holds one valid version, with no silent lost updates.

Do not rely on `Thread.sleep(10)` to “force a race”, as shifting CPU/CI scheduling makes such tests flaky.

### 25.5. Concurrency limits and quotas

A load test firing 1,000 concurrent async requests can fail due to local emulator CPU, Java thread pools, or NAT rather than Azure production throughput. Measure **client-side in-flight counts, connection pools, request latency, and server errors/throttling** separately before blaming the Azure service.

## 26. Observability: tests must leave evidence

An integration test returning only PASS/FAIL is hard to debug when it fails in CI yet passes locally. Record **diagnostic evidence** showing which resource was called, under which identity, with which SDK version, and at which stage.

### 26.1. Fields to log (with zero secrets)

```json
{
  "testSuite": "BlobAzuriteIT",
  "testCase": "shouldUploadAndReadRealBlob",
  "targetKind": "emulator",
  "environment": "ci",
  "sdkComponent": "azure-storage-blob",
  "resourceAlias": "it-run-8f2a",
  "operation": "BlobUploadDownload",
  "result": "PASS",
  "durationMs": 231,
  "traceId": "trace-integration-42"
}
```

Timing and aliases in this example are **synthetic values**. On failure, also log HTTP error codes, sanitized service request IDs, retry counts, and exception classes. **Never** log Shared Keys, SAS tokens, bearer tokens, full connection strings, or raw PII.

### 26.2. Azure SDK diagnostics

The Azure SDK for Java supports HTTP logging/tracing/metrics integration depending on library and configuration. It can integrate with **OpenTelemetry/Application Insights** via supported mechanisms. Do not enable unredacted wire-level body/header logging in CI with public artifacts. Log token scopes/audiences safely at configuration level without logging token values.

### 26.3. Correlation IDs

An end-to-end flow:

```text
HTTP request traceId=tr-42
   |
   +-- Upload Blob (client request ID)
   |
   +-- Send Queue Message (business command ID)
   |
   +-- Worker receives (same business ID)
   |
   +-- Insert order status (DB transaction ID)
   |
   +-- Test checks final state
```

Tests should verify that **business correlation IDs** propagate properly across components when auditing is required. Azure service request IDs aid support/debugging, but do not replace business command IDs.

### 26.4. Metrics for CI integration

| Metric | Meaning |
|---|---|
| Test pass/fail/skipped per tier | Is any group silently not running? |
| Provision time | Is creating Azure resources taking too long? |
| Emulator startup time | Docker/image/runner issues |
| SDK operation p95 | Latency regression, separated by emulator/cloud |
| Auth/RBAC failure count | Identity/role drift |
| Retry count / 429 count | Throttling/capacity issues |
| Cleanup leaked resources | Cost and governance |
| Test cost per run | Exceeding budgeted thresholds? |

Do not compare **10ms on a laptop Azurite instance** to **50ms against remote Azure cloud** and declare a code regression. Compare within matching environments/regions/networks and data sizes.

## 27. CI/CD: three test streams instead of one giant job

### 27.1. PR pipeline: unit + emulator

```text
Pull Request
  |
  +-- Compile + lint / SAST / secrets scan
  |
  +-- Unit tests (fake ports / mocks)
  |
  +-- Start Testcontainers Azurite
  |
  +-- Emulator IT: Blob/Queue/Table basic contracts
  |
  +-- Publish JUnit reports + sanitized logs
  |
  v
Merge gate
```

Do not supply production Azure credentials to PRs triggered from forks/untrusted contributors. Docker support on GitHub-hosted/self-hosted runners must be configured properly; never grant cloud write permissions to workflows executing unreviewed code.

### 27.2. Nightly/release pipeline: cloud integration

```text
Trusted branch / scheduled integration job
  |
  +-- Federated CI identity / managed identity login
  |
  +-- Validate non-prod subscription/tenant
  |
  +-- Provision/test RG + resources via IaC
  |
  +-- Assign least-privilege data roles
  |
  +-- Wait for provisioning + RBAC readiness
  |
  +-- Run @Tag("azure") tests with synthetic data
  |
  +-- Run negative RBAC/network tests where approved
  |
  +-- Publish results/metrics and sanitized traces
  |
  +-- Finally: cleanup test resources / report leaks
  |
  v
Release gate
```

When using OIDC workload federation, restrict trust policies by **repository, environment, branch, and principal scope**, avoiding static client secrets in CI. Cloud integration tests must be triggered from a **trusted code path** with proper approvals.

### 27.3. Condensed GitHub Actions workflow example

```yaml
name: java-sdk-tests

on:
  pull_request:

jobs:
  emulator-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"
      - name: Verify unit and Azurite integration
        run: mvn -B verify -P emulator-it
```

This is a **skeleton**, incomplete unless the project already defines the `emulator-it` Maven profile, Testcontainers configuration, and Azurite dev key. You must **pin GitHub Actions/runner dependencies**, manage versions, and follow your organization’s supply-chain policies. Do not label this job as cloud RBAC verification; it runs only the local/emulator suite.

### 27.4. Fail if tests are skipped

Some tests may use `Assumptions.assumeTrue(...)` to skip when Docker is unavailable, but if the **emulator integration** group is a release gate, skipping must **FAIL** the pipeline or report insufficient coverage. Inspect JUnit XML report test counts/statuses rather than relying blindly on the exit code of a Maven profile that accidentally excluded all `*IT` classes.

### 27.5. Separating profiles and configuration

```text
test profile unit:
  fake DocumentStore

test profile emulator:
  AZURITE_BLOB_CONNECTION_STRING
  AZURE_INTEGRATION_TARGET=emulator

test profile azure:
  AZURE_TEST_STORAGE_ACCOUNT
  AZURE_TEST_SUBSCRIPTION_ID
  AZURE_INTEGRATION_TARGET=azure
  intended workload identity / federated credential
```

Never let a generic `AZURE_STORAGE_CONNECTION_STRING` variable arbitrarily fall back to a production account if the emulator profile is missing. Fail fast if the target is not in the allowlist, especially before any destructive test.

### 27.6. Resource janitor

A scheduled job inspects test resources tagged with `owner, runId, createdAt, expiresAt`, cross-checks active builds, and **deletes only when TTL has expired and no owner is active**. Include dry runs, approvals/canaries, and auditing. Never search and delete “all storage accounts whose names start with test” across a broad subscription.

## 28. Estimating the cost of cloud integration tests

Azure test resources can incur charges even when idle:

| Component | Potential cost | Control |
|---|---|---|
| Storage account | Capacity, read/write transactions, redundancy | Small synthetic fixtures, TTL, LRS when sufficient |
| Cosmos DB | Provisioned RU/s/serverless requests, storage | Suitable tier, auto-cleanup, capped test data |
| Service Bus/Event Hubs | Namespace/tier/capacity, operations | Isolated sharing or ephemeral provisioning where feasible |
| Azure SQL Database | Compute/backup/storage | Run on controlled schedules, clean up promptly |
| Network/Private Endpoint | Endpoints, gateway/egress | Choose proper scopes and regions |
| Diagnostics/Application Insights | Log ingestion/retention | Sample/redact, short retention sufficient for debugging |
| Test compute | CI runners, containers, Azure-hosted agents | Run targeted test groups, not full load per PR |

### 28.1. Sample cost budget

```text
Emulator PR tests:
  no Azure resource charge (CI runner costs still apply)

Cloud integration nightly:
  fixed maximum runtime
  small synthetic data size
  per-run resource group / per-run namespace
  monthly budget + forecast alert
  cleanup policy and leak detection

Performance/chaos:
  separate approved environment and explicit budget
```

No fixed price is listed because Azure SKUs/regions and pricing vary. Use the **Azure Pricing Calculator, Cost Management, and actual resource usage** to calculate estimates.

### 28.2. “Free tier” does not mean cleanup is optional

Some services offer free tiers/emulator modes subject to limits, account rules, and conditions. Network egress, logs, storage, or companion resources may still be billed. Test teams should report **total cost of ownership** rather than looking at a single “free” SKU.

### 28.3. Choosing high-value tests

One small **Blob upload + read + RBAC deny** cloud test catches more critical failures than 10,000 mocked tests of an SDK builder. Prioritize testing the boundaries where emulators diverge from Azure: IAM, networking, tier-specific behavior, quotas, and real persistence/consistency.

## 29. Case study: an order-ingestion system using Blob and Queue

### 29.1. Requirements

The Java application must:

1. Accept `POST /orders/{id}/receipt` with synthetic PDF/document bytes.
2. Write Blob `receipts/{orderId}/{contentHash}`.
3. Send a Queue message instructing the worker to verify and index the receipt.
4. Have the worker read the Blob, verify the checksum, and update the business result store.
5. Expose an API to query status: `PENDING / PROCESSED / FAILED`.

The team wants fast PR tests using Azurite while ensuring releases do not fail due to IAM/Private Endpoint misconfigurations on Azure.

### 29.2. Test architecture

```text
                 JUnit 5 test
                     |
          synthetic receipt + orderId
                     |
                     v
             Java OrderIngestion
                     |
             +-------+--------+
             |                |
             v                v
      AzureBlobDocumentStore  QueueWorkPublisher
             |                |
             +--------+-------+
                      |
          Azurite Blob + Queue (PR)
              OR Azure Storage test (cloud)
                      |
                      v
              OrderReceiptWorker
                      |
             idempotent result store
                      |
                      v
           JUnit assert final business state
```

### 29.3. Business invariants

| Invariant | Verification method |
|---|---|
| Blob contains exact uploaded document | Read-back + hash/byte comparison |
| One logical order is never indexed twice | Unique `orderId + documentVersion` in result store |
| Queue message carries the right key | Parse actual message from Azure Queue/SDK |
| Worker crash between processing and delete causes no duplication | Idempotent worker + replay test |
| Failures do not silently drop commands | Business command/outbox store or recovery design |
| Tests leave zero leftover data | Per-run isolated container/queue namespaces and cleanup |
| Cloud identity holds exact scope | Data-plane allow/deny tests against test resources |

### 29.4. Idempotency design

If the API uploads the Blob successfully but fails to send to the Queue, a **durable workflow** must record pending work and retry publishing. If sending to the Queue succeeds but the HTTP response is lost, the producer may resend the same message. **A Blob write and a Queue send do not automatically form an atomic transaction.**

One possible design uses a database/outbox:

```text
DB transaction: create order + outbox event
    |
    v
Dispatcher uploads Blob / sends queue with stable business ID
    |
    v
Worker processes idempotently with inbox/unique key
    |
    v
Complete Queue message after business commit
```

Depending on requirements, you can reorder Blob upload vs. DB transaction, provided you account for **orphan Blob cleanup, retries, reconciliation, and unknown outcomes**. Never label the whole workflow “exactly-once” merely because the worker deletes messages.

### 29.5. Concrete integration test suite

| Test | Emulator | Cloud test |
|---|---|---|
| Upload/download receipt bytes | Every PR | Smoke |
| Queue publish/read/delete | Every PR | Smoke |
| Duplicate message creates no duplicate status | Every PR | Per release |
| Missing blob → worker failure/compensation | Every PR | Per release |
| Blob ETag concurrency | Emulator | Yes if business requires |
| Queue visibility timeout/redelivery | One short test | Yes if service semantics are critical |
| Managed identity + RBAC | No | **Mandatory** |
| Private Endpoint/DNS/TLS | No | **Mandatory in staging topology** |
| Quotas/throttling/scale | Partially simulated | Dedicated test |
| Cleanup/tags/cost guard | Local/container | **Mandatory** |

### 29.6. Real tests must assert end-of-workflow state

An effective end-to-end test:

```text
Arrange:
  create unique container + queue + orderId;
  synthetic file; start test worker;

Act:
  API ingests document;

Assert:
  actual Blob bytes and metadata match;
  worker processed message;
  result store has one logical result;
  no duplicate side effect after message replay;

Finally:
  stop worker and close clients;
  delete only resources owned by this run;
  record cleanup result.
```

The resulting business state may be **eventually observable** because the worker runs asynchronously; tests should **poll up to a deadline** rather than calling `Thread.sleep(5000)` and guessing the worker finished.

### 29.7. Tests that expose real bugs

Suppose code initializes a Blob client with connection string `UseDevelopmentStorage=true` (or local equivalent) inside the service, injected during unit tests, yet **fails to switch to token credentials in staging**. PR emulator tests stay green, while the cloud test fails with 401/403 or attempts to connect to a local endpoint. Dependency injection plus real test resources catch this mismatch before production.

## 30. Deterministic tests: preventing flakiness in distributed systems

### 30.1. Avoid fixed sleeps

Anti-pattern:

```java
sendQueueMessage();
Thread.sleep(3000);
assertEquals("PROCESSED", repository.getStatus(orderId));
```

If runner CPU is slow, the test fails; if the worker errors out after 3 seconds without completing, diagnostics remain vague. Instead, use **deadline-bounded polling**, logging the last observed status and elapsed duration:

```java
import java.time.Duration;
import java.time.Instant;

Instant deadline = Instant.now().plus(Duration.ofSeconds(15));
String status;

do {
    status = repository.getStatus(orderId);
    if ("PROCESSED".equals(status)) break;
    Thread.sleep(100);
} while (Instant.now().isBefore(deadline));

assertEquals("PROCESSED", status,
        "Worker did not finish within test deadline");
```

This is a **code fragment** assuming `repository` and `orderId` exist and the method declares `InterruptedException`. In a production test harness, use Awaitility/`StepVerifier` or a polling helper respecting interruption and request budgets. Use polling only for **eventual behavior**; since Blob Storage read-after-write has strong consistency per service semantics, do not add gratuitous sleeps to paper over a bug.

### 30.2. Use Awaitility when appropriate

An Awaitility helper (once added to test dependencies):

```java
await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() ->
        assertEquals("PROCESSED", repository.getStatus(orderId)));
```

`await()` comes from the Awaitility library, not JUnit 5 core. Tests must declare the proper dependency/version and ensure polling queries have negligible side effects. Deadlines must accommodate the target cloud environment without extending indefinitely.

### 30.3. Do not depend on test ordering

A brittle, flaky suite:

```text
Test A creates queue
Test B reads Test A's message
Test C deletes queue
```

JUnit does not guarantee a default ordering that tests should rely upon. Combine them into a **self-contained test scenario** or provision separate resources per test; if a sequential workflow is required, define the sequence within a single test and assert each step.

### 30.4. Nondeterministic IDs and clocks

Random names prevent collisions but hinder debugging if run IDs are not logged. Record **test IDs, resource aliases, and trace IDs** while redacting secrets. Fake clocks are ideal for unit retry/TTL checks; real tests must verify server/client clocks and timeout tolerances.

### 30.5. Network flakiness

A cloud test that fails once due to networking should not automatically rerun 10 times until green and discard the failure evidence. Classify transient failures, retry within a budget, and track **flaky rates**. A test needing 5 retries to pass signals a problem to investigate, not “stability”.

## 31. Troubleshooting: distinguishing emulator, SDK, and real Azure failures

| Symptom | Common cause | Right check |
|---|---|---|
| `Connection refused 127.0.0.1:10000` | Azurite not running, wrong port mapping | Docker logs, bind address/port, Testcontainers mapped port |
| `AuthenticationFailed` on Azurite | Wrong dev key/account name, malformed connection string | Match account config/local key and endpoint |
| `UnsupportedApiVersion` | SDK newer than emulator feature support | Pin/upgrade emulator or run cloud feature test |
| Docker image pull fails | Registry/proxy/network/pinning | Image reference, runner network, image digest |
| Testcontainers cannot find Docker | Runner lacks daemon/permissions | Docker runtime access, CI config |
| `SSLHandshakeException` Cosmos Emulator | Dev certificate/truststore | Test-only CA/truststore; never trust-all in production |
| Azure Blob 401 | Invalid token/audience/tenant issue | Sanitized credential chain/principal/token config |
| Azure Blob 403 | Data-plane RBAC, firewall/policy, or similar | Azure error code, role/scope, network/firewall |
| Cloud Blob 404 right after write | Wrong account/container/key/version/path or failed request | Inspect actual SDK endpoint/path/correlation, do not sleep blindly |
| Azure Queue message “vanished” | Currently invisible, expired, consumed/deleted | Visibility timeout, TTL, pop receipt, workers |
| Service Bus duplicate message | Receiver crashed before settlement | Idempotency store, lock expiry/renewal, delivery count |
| High Cosmos query cost on cloud | Cross-partition/indexing/RUs differ from emulator | Partition keys, query metrics, consumed RUs |
| CI cloud test “passes” as personal user | DefaultAzureCredential picked Azure CLI/IDE identity | Assert actual principal/client/tenant, use federated identity |
| Cleanup fails, resources linger | Runner killed, missing delete role, resource lock | Run ID manifest, janitor policy, owner and scope |
| Random failures under parallel runs | Shared container/queue/key, hard-coded names | Unique namespace, isolation, barrier synchronization |
| Emulator tests pass but staging fails | RBAC, Private Link, API feature, quotas not simulated | Cloud integration matrix, network/auth diagnostics |

### 31.1. Do not change every setting at once

When a cloud Blob test fails with `403`, never simultaneously open public networking, disable TLS, grant Subscription Owner, and swap SDK versions. That is both dangerous and destroys root-cause visibility. Inspect **identity → data-plane role → resource scope → firewall/Private Endpoint → SDK endpoint** in order based on the error.

### 31.2. Distinguishing HTTP 403 from network timeouts

If a request receives an **HTTP 403 response from an Azure service**, TLS connectivity to the service likely succeeded; conversely, `ConnectTimeout` does not indicate a missing role. However, some services return 403 on **network ACL denials** or policy blocks, so inspect **service error codes and logs** rather than jumping to conclusions from status codes alone.

### 31.3. Debugging the credential chain

With `DefaultAzureCredential`, developer laptops may use an Azure CLI user instead of the intended workload identity. In production-like CI, use explicit credential selection/managed identity where appropriate, log **non-secret principal IDs/tenant IDs**, and verify RBAC. Never print bearer tokens or sensitive token claims to CI console logs.

### 31.4. Debugging Azurite shared accounts

Azurite includes a built-in dev account and may support custom account configurations. If your configured key/account mismatches the server, the SDK returns an authentication error. Never alter production Shared Key signing code to accommodate a misconfigured emulator; fix the **test environment**.

## 32. Runbooks: handling integration pipeline incidents

### 32.1. Runbook A – All emulator tests fail after an upgrade

1. Check recent changes to the Azure SDK BOM version, Azurite image tag, and JDK/CI runner.
2. Read the exception: unsupported API version or connection refused/auth?
3. Inspect Docker/port mappings/healthchecks.
4. Run a minimal Blob round-trip against the pinned image.
5. Check breaking changes in relevant SDK/emulator release notes.
6. Fix compatibility or pin a tested version; never use loose mode as release proof.
7. Re-run the full emulator suite and preserve incident evidence.
8. Evaluate whether cloud tests are needed for features unsupported by the emulator.

**Never bulk-delete assertions** just to turn the pipeline green after a version bump.

### 32.2. Runbook B – Cloud IT fails with 401/403

1. Confirm non-prod subscription/resource ID/tenant.
2. Verify the runner/pod’s actual principal, not just the expected credential type.
3. Check Storage data-plane RBAC role/scope and propagation.
4. Check endpoint/TLS/network path and firewall/private endpoint denials.
5. Compare emulator and cloud code paths for leaked/mixed connection strings.
6. Inspect sanitized Azure service error codes/correlation IDs.
7. Fix least-privilege roles/networking or the credential chain; never grant Owner arbitrarily.
8. Re-run targeted cloud tests, negative RBAC tests, and cleanup.

**Never put an Azure account key into CI just to avoid fixing managed identity** if the test’s goal is Entra/RBAC verification.

### 32.3. Runbook C – Test resources remain after CI

1. Retrieve the provisioning manifest: run ID, RG, subscription, `createdAt`.
2. Verify the build truly finished and no parallel job still needs the resources.
3. Inspect cleanup logs, resource locks, RBAC, and network/IaC state.
4. Generate a dry-run report of job-owned resources.
5. Delete only RGs/resources with valid ownership and expired TTL, with auditing.
6. Record cost/leak counts and fix `finally`/post-job workflows.
7. Never delete shared staging RGs or another run’s RGs.

### 32.4. Runbook D – Queue worker processes twice

1. Inspect message ID, business key, dequeue count, and timeline.
2. Check whether the worker crashed after DB write and before queue delete/settlement.
3. Verify queue visibility timeout/lock renewal and retry behavior.
4. Add/verify an inbox/unique business key in the data store.
5. Unit test idempotency, emulator test duplicate delivery, and run a small cloud test if needed.
6. Reconcile executed side effects and apply compensation where appropriate.
7. Never try to “disable all retries” to hide missing invariants.

### 32.5. Runbook E – Cloud IT is slow and expensive

1. Break down provisioning time, RBAC propagation, test operation time, and cleanup time.
2. Check whether tests create hourly-billed resources that sit idle.
3. Investigate data sizes, repeated retries, unnecessary full scans, and log volume.
4. Shift basic CRUD tests to the emulator, reserving cloud tests for feature gaps.
5. Optimize isolated shared test resources where suitable.
6. Use schedules/auto-stop/TTL resources when supported by the service.
7. Establish duration/cost baselines, budget alerts, and cleanup metrics.

## 33. Integrating with Spring Boot test profiles

In Spring Boot, define **client beans** per profile so business services stay unaware of Azurite vs. cloud endpoints. Integration tests can run Testcontainers and configure the application context via `@DynamicPropertySource`.

### 33.1. Client configuration

```java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("emulator")
public class AzuriteBlobConfig {

    @Bean
    public BlobServiceClient blobServiceClient(
            @Value("${storage.emulator.connection-string}") String cs) {
        return new BlobServiceClientBuilder()
                .connectionString(cs)
                .buildClient();
    }
}
```

This is a Spring Boot/Spring Framework bean setup assuming the project already includes `spring-boot-starter` and the Azure Blob dependency. To wire the `DocumentStore` port, declare an adapter bean with a test-owned container name derived from the run ID. Never construct production connection strings by concatenating keys inside Spring configuration.

### 33.2. Separate cloud configuration

```java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile({"azure-test", "production"})
public class AzureBlobConfig {

    @Bean
    public BlobServiceClient blobServiceClient(
            @Value("${storage.azure.endpoint}") String endpoint) {
        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(new DefaultAzureCredentialBuilder().build())
                .buildClient();
    }
}
```

In production, define the **allowed credential chain** and endpoints via centrally validated configuration; use managed/workload identity where applicable. The two profiles separate connection modes while shared application code consumes `BlobServiceClient`/`DocumentStore`.

### 33.3. DynamicPropertySource with Testcontainers

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

// Fragment inside a @SpringBootTest @ActiveProfiles("emulator") class
// with @Container AZURITE configured as in section 9.

@DynamicPropertySource
static void emulatorProperties(DynamicPropertyRegistry registry) {
    registry.add("storage.emulator.connection-string", () -> {
        String key = System.getenv("AZURITE_DEV_ACCOUNT_KEY");
        if (key == null) {
            throw new IllegalStateException("Missing Azurite dev key");
        }
        String endpoint = "http://" + AZURITE.getHost() + ":"
                + AZURITE.getMappedPort(10000) + "/devstoreaccount1";
        return "DefaultEndpointsProtocol=http;"
                + "AccountName=devstoreaccount1;AccountKey=" + key
                + ";BlobEndpoint=" + endpoint + ";";
    });
}
```

**This is a fragment** requiring Spring Test dependencies, Testcontainers imports, test class annotations, and the config classes themselves. If a resource exposes multiple clients/services, inject the corresponding endpoints. Ensure Testcontainers **has started before the framework creates clients reading the property** according to your configured JUnit/Spring integration lifecycle.

### 33.4. Spring `@MockBean`/bean overrides are insufficient for integration

Testing Spring Boot while replacing `BlobServiceClient` with a mock still yields mostly a unit/component test. An integration test must use a **real bean talking to an emulator or Azure test resource** to verify HTTP operations, serialization, and backend behavior. Both test types are valuable—just never mislabel them.

### 33.5. Labeling profiles in test reports

Each test suite should clearly record:

```text
Test suite: OrderIngestionIT
Spring profile: emulator
Target kind: Azurite
Blob SDK version: project BOM-resolved
Testcontainer image: pinned digest/tag
Azure cloud RBAC test: NOT RUN in this suite
```

This prevents reviewers from mistaking a local test for verified production identity/networking.

## 34. Acceptance matrix and release gates

Before declaring an Azure SDK integration “ready”, use a verification matrix:

| Behavior | Unit | Emulator | Azure test | Required for release? |
|---|---|---|---|---|
| Validate order request | PASS | Not needed | Not needed | Yes |
| Blob upload/download bytes | Fake/business test | PASS | PASS smoke | Yes |
| Blob metadata/content type | Test mapping | PASS | PASS if critical | Depends on use case |
| Blob ETag conflict | Test classifier | PASS | PASS if concurrent writes | Depends on use case |
| Blob missing 404 | PASS | PASS | Spot check | Yes |
| Queue send/receive/delete | Test state machine | PASS | PASS smoke | Yes |
| Queue duplicate delivery | PASS idempotency | PASS | PASS if critical | Yes |
| Cosmos partition key | Test repository | PASS where emulator supports | PASS if using Cosmos | Yes if critical |
| Event Hubs checkpoint resume | Test checkpoint policy | PASS where emulator supports | PASS | Yes if feature is used |
| Service Bus session/DLQ | Test state logic | Depends on emulator | PASS | Yes if feature is used |
| Entra ID token/tenant | Fake chain config | Does not prove | PASS | **Yes** |
| Azure RBAC allow/deny | Policy/business test | Does not prove | PASS | **Yes** |
| Private Endpoint/TLS | Test config | Does not prove | PASS on staging runner | **Yes if used in production** |
| Throttling/retry budget | Unit policy | Inject/partial | Controlled cloud test | Yes |
| Cleanup/leak policy | Test generator | PASS | PASS | Yes |
| Cost budget/alerts | Test config | No | Actual cloud usage | Yes for cloud IT |

**PASS applies only if the feature is actually used.** Do not force a project using only Blob Storage to run Service Bus/IoT Hub tests. Conversely, if the application relies on a capability unsupported by an emulator, **never drop the “Azure test” column from the matrix just to turn the gate green**.

### 34.1. What should a release gate report?

```text
UNIT=PASS
EMULATOR_BLOB=PASS
EMULATOR_QUEUE=PASS
CLOUD_BLOB_AUTH=PASS
CLOUD_RBAC_NEGATIVE=PASS
CLOUD_PRIVATE_ENDPOINT=PASS
CLOUD_RESOURCE_CLEANUP=PASS
SKIPPED_CRITICAL_TESTS=0
BLOCKERS=NONE
```

This report format is **illustrative**, not the default output of any specific tool. What matters is clearly separating **tested** from **not tested** per environment.

### 34.2. Failure criteria

A release must stop when:

- Tests target the wrong subscription or a resource outside the allowlist.
- The actual principal does not match the intended identity.
- Critical cloud tests are skipped due to missing credentials/Docker.
- Any unit/emulator/cloud test fails but the pipeline ignores the exit code.
- CRUD tests pass, yet cleanup deletes the wrong resource or leaves major leaks.
- There is evidence of production data/PII entering test environments.
- Production features are only mocked without appropriate cloud verification.

### 34.3. Do not measure “coverage” solely by test count

1,000 mocked SDK builder tests cannot replace a single real data-plane RBAC test. Evaluate coverage by **failure modes, boundaries, IAM, networking, data invariants, and cost**, not merely statement/branch code coverage.

## 35. Hands-on exercises

### Exercise A – Blob round-trip with Azurite

**Prompt:** Implement `DocumentStore` from section 4, start local Azurite, and write a JUnit test uploading `receipt-1042.json`, downloading it, and comparing bytes.

**Requirements:** unique container, UTF-8 fixture, missing-Blob check, cleanup in `@AfterEach`.

**Acceptance criteria:** test invokes the **real SDK over HTTP** without mocking `BlobClient`; fails if Azurite is not running.

### Exercise B – Testcontainers dynamic ports

Migrate test A to Testcontainers. Do not hard-code host port 10000; use only `AZURITE.getMappedPort(10000)` and `getHost()`. Pin a tested image version/digest.

**Acceptance criteria:** two separate CI runs do not collide on host ports/container names; tests do not depend on a manually started Azurite instance.

### Exercise C – Negative tests for 404/409/412

Add tests:

1. Download missing Blob → assert service exception status.
2. Upload duplicate key without overwrite → conflict per contract.
3. ETag conditional write with stale ETag → precondition failure.

**Acceptance criteria:** tests prove HTTP conditional semantics without constructing fake exceptions manually.

### Exercise D – Queue visibility timeout and duplicates

Send message `job-1042`; have the worker receive it, simulate a crash before deletion, receive it again after timeout, and run the idempotent handler.

**Requirements:** the business result store contains only one record for the stable job ID. The test also verifies deleting with the correct pop receipt.

**Acceptance criteria:** duplicate messages create no duplicate business side effects.

### Exercise E – Cosmos DB Emulator

Create container `orders` with partition key `/tenantId` on a compatible Cosmos emulator:

- Insert two synthetic tenants.
- Read items using the exact partition key.
- Test querying with a wrong partition key.
- Verify ETag/conflict handling.
- Document clearly what **cannot** be concluded regarding RUs, autoscale, and regional failover.

**Acceptance criteria:** real tests through the Cosmos SDK creating/deleting their own resources; never touch a production Azure account.

### Exercise F – IAM/RBAC on Azure Storage test resources

In a non-prod subscription, create a dedicated storage account. Grant one managed/service test identity **Storage Blob Data Contributor**, and another identity only **Storage Blob Data Reader**.

**Tasks:** test upload/read for the writer; read success + write denied for the reader; verify principal IDs and scopes without using account keys.

**Acceptance criteria:** tests distinguish RBAC 403 from network/credential errors and clean up the account.

### Exercise G – Private Endpoint

Suppose an Azure Blob account allows private networking only. Developer laptops cannot reach it, whereas AKS staging has VNet integration.

**Tasks:** design tests running from the proper pod/runner; check DNS FQDN, TLS, identity, and Blob CRUD. Explain why local Azurite tests do not verify this.

**Acceptance criteria:** never open public access or disable TLS; connections succeed over the right network path or accurately report blockers.

### Exercise H – Flaky CI

An integration test calls Queue send followed by `Thread.sleep(1000)` waiting for the worker, passing locally yet failing intermittently in CI.

**Tasks:** replace with bounded polling/Awaitility deadline, unique job IDs, business outcome assertions, and diagnostics. Separate resource cleanup from retry logic.

**Acceptance criteria:** test does not depend on arbitrary delays, and failures capture event traces.

### Exercise I – SDK upgrade

Upgrade the Azure SDK BOM version. Azurite tests start throwing `UnsupportedApiVersion`, while cloud tests still pass.

**Tasks:** classify compatibility gaps between emulator and API version, choose between pinning/upgrading to a tested emulator or splitting the feature test to the cloud. Do not arbitrarily disable assertions or weaken security flags.

**Acceptance criteria:** report clearly documents emulator gaps and Azure contract validation.

### Exercise J – Cleanup governance

A CI job is canceled after creating a test RG and before cleanup, leaving resources behind for 7 days.

**Tasks:** design a manifest with run ID/subscription/owner/timestamp, `finally`, TTL janitor, dry-run mode, and RBAC scoping without deleting resources in use by other jobs.

**Acceptance criteria:** control resource leaks and costs without granting delete permissions over production.

### Exercise K – Scoped Service Bus testing

An application uses Service Bus sessions and dead-letter processing. The current emulator version does not fully support one of those features.

**Tasks:** build a unit/stub/emulator/cloud matrix; decide which tests run on every PR vs. nightly/release, and document unsupported assumptions.

**Acceptance criteria:** never mark session semantics verified solely via a Queue Storage/Azurite test.

### Exercise L – End-to-end order ingestion

Build `OrderIngestionIT` from the case study in section 29:

- Upload a synthetic document to Blob.
- Send a message with a stable order ID.
- Worker reads the blob and records the result.
- Assert final business state, ensuring duplicate retries do not multiply results.
- Inject a failure between DB commit and queue delete.
- Clean up via test resource manifest, logging cost and traces.

**Acceptance criteria:** identical business logic runs against both the PR emulator and cloud test accounts, differing only in **endpoints + credentials + profiles**; zero production impact.

## 36. Self-check questions

**1. How does an integration test differ from a unit test?** Integration tests cross real integration boundaries such as SDK HTTP, emulators, or Azure resources; unit tests can use fakes/mocks to test isolated logic.

**2. Why doesn’t a mocked `BlobClient.upload()` prove Azure Storage works?** It never serializes an HTTP request, signs authentication, calls the service, or reads back bytes.

**3. Which Azure Storage services does Azurite emulate?** Typically Blob, Queue, and Table within its supported feature/version scope.

**4. Does Azurite test production Entra RBAC/managed identities?** Not with the same semantics as real Azure; cloud tests are required.

**5. Why use dynamic ports from Testcontainers?** To avoid host port conflicts and support Docker/CI networking cleanly.

**6. Is the `devstoreaccount1` development account a production credential?** No; it is the emulator’s well-known test account/key and is never used on real Azure.

**7. Why avoid `latest` for long-term CI emulators?** Mutable images can make tests non-reproducible or alter features/API versions without review.

**8. What should a Blob round-trip test assert?** Container creation, uploading bytes, reading/downloading and comparing content, error handling, and ownership-safe resource cleanup.

**9. Why is testing a real 404 from the SDK more valuable than mocking an exception?** It verifies SDK/service error serialization and exception mapping over HTTP.

**10. What does an ETag concurrency test prove?** Conditional writes prevent stale writers from overwriting newer changes per service/API semantics.

**11. Does `QueueClient.receiveMessages()` remove the message from the queue?** No; you normally must delete it with its message ID + pop receipt after processing.

**12. Why can a Queue redeliver a message?** Visibility timeout expiration or failure before deletion, causing retries/duplicate delivery.

**13. Is exactly-once business processing guaranteed just by Queue send/delete?** No. You need idempotent consumers and durable business keys/inboxes.

**14. Does the Cosmos DB emulator give accurate production RU/s estimates?** No. You need cloud accounts/test metrics on real tiers.

**15. Why can Cosmos DB Gateway vs. Direct mode matter?** Networking/ports/firewalls/client behaviors differ; you must test the intended deployment mode.

**16. Are Service Bus and Event Hubs emulators interchangeable?** No. Service Bus queues/topics/settlement and Event Hubs streams/checkpoints have different semantics.

**17. Do Functions Core Tools fully simulate Azure Functions scaling and managed identity?** No; they test local bindings and function code, whereas cloud hosting/networking/identity require staging.

**18. Which identity might `DefaultAzureCredential` select on a laptop?** It may pick Azure CLI/IDE credentials along the chain/config, not necessarily the intended managed identity.

**19. Why might a management-plane Contributor fail to upload a Blob?** Data-plane storage permissions/RBAC are separate grants.

**20. Where should cloud test accounts reside?** Inside a non-prod subscription/resource group with allowlists, ownership metadata, least privilege, and cleanup.

**21. Why not use a production storage account with a container named `test`?** It still impacts billing/quotas/policies and risks accidental deletion or corruption of real data.

**22. If an Azure test fails with 403, what should you inspect?** Principal, tenant, role/scope, propagation, firewall/Private Endpoint, and service error code; never grant Owner blindly.

**23. Does Azurite’s local HTTP justify disabling TLS on real Azure?** No. Production Azure requires HTTPS/certificate validation per policy.

**24. When unit testing a timeout policy, why inject a fake clock?** To avoid real waiting while deterministically testing edge cases and retry deadlines.

**25. Why can retrying a Queue send after a timeout create duplicates?** The server may have accepted the message while the response was lost; the retry submits a second message.

**26. Does a passing Testcontainers test guarantee an AKS Private Endpoint will work?** No; it must be tested from the actual workload/network in Azure.

**27. Is a test using `@SpringBootTest` and `@MockBean BlobClient` a cloud integration test?** No; it does not call Azure or real SDK services.

**28. Where should test fixture data come from?** Synthetic/generated test data; never copy production PII/secrets into test environments.

**29. Why does each test need unique container/key names?** To avoid collisions and test-order dependencies when running in parallel.

**30. Is cleanup using only a name prefix safe enough?** No; you need owner/run ID/resource manifest/scoping and verification that the resource belongs to the test.

**31. Can a CI release report PASS if all integration tests were skipped?** No. Critical skipped tests must be treated as missing coverage/a failing gate.

**32. What can make an Azure cloud test flaky?** Networking, RBAC propagation, noisy neighbors, quotas, test namespace collisions, hard sleeps, or cleanup races.

**33. Does Blob Storage need arbitrary sleeps after writes for read-after-write consistency?** No, given Blob data-plane strong consistency; if you get a 404, inspect path/account/version/request outcomes.

**34. Does Azure SDK retry automatically solve business idempotency?** No. You must design stable business keys and handle indeterminate outcomes.

**35. Which metrics help investigate slow CI cloud tests?** Provisioning time, RBAC readiness, SDK call latency/retries, throttling, cleanup time, and resource cost.

**36. Should heavy chaos/performance tests run against shared Azure staging resources on every PR?** No. Separate environments, schedules, approvals, and budgets.

**37. What does “Emulator PASS, Azure NOT RUN” mean?** Basic SDK behavior was verified locally; cloud-specific IAM/networking/tiers/features remain unverified.

**38. What is the most important prerequisite before release?** All actually used integration boundaries are tested at the appropriate layers, cloud identity/networking are sound, data invariants hold, and cleanup/costs are controlled.

## 37. Azure SDK for Java testing implementation checklist

### 37.1. Architecture and dependencies

- [ ] Business code separated from Azure SDK adapters via explicit interfaces/ports.
- [ ] SDK clients constructed once from configuration and injected, not per request.
- [ ] Java/JDK, Azure SDK BOM, emulator image, and Testcontainers versions pinned/tested.
- [ ] Unit tests use fakes/mocks to verify business rules, validation, timeouts, and retry classifiers.
- [ ] Emulator tests invoke the real SDK over endpoints/protocols, not mocks alone.
- [ ] Cloud tests verify feature gaps and Azure-specific behavior.
- [ ] `unit`, `emulator`, `azure`, and `production` profiles/targets are cleanly separated.
- [ ] Test reports explicitly state which layers ran and which cases were skipped.

### 37.2. Azurite and Testcontainers

- [ ] Docker/Testcontainers availability verified on the runner.
- [ ] Azurite image pinned by tag/digest and compatible with the service API version.
- [ ] Dev account/key used locally only, never as production credentials.
- [ ] Endpoints use `getMappedPort`/`getHost` when containers map dynamic ports.
- [ ] Unit/emulator test fixtures contain no production PII/secrets.
- [ ] Blob tests assert upload/download content, missing 404, metadata, and cleanup.
- [ ] Queue tests assert send/receive/delete, visibility timeout, and duplicate processing.
- [ ] Table tests verify `PartitionKey`/`RowKey`, ETag, and queries if used.
- [ ] Emulators are never cited as proof of Azure RBAC, geo-DR, or production networking.
- [ ] Clear error messages when Docker/emulators fail to start; CI never skips silently.

### 37.3. Cosmos/messaging/Functions when used

- [ ] Feature matrix reviewed and documented for the exact Cosmos/Service Bus/Event Hubs emulator version.
- [ ] Cosmos emulator uses a dedicated HTTPS test certificate/truststore, never production trust-all.
- [ ] Cosmos cloud tests measure partition keys/indexes/RUs/quotas when performance is required.
- [ ] Service Bus tests cover settlement/duplicates/DLQ/sessions matching actual feature usage.
- [ ] Event Hubs tests verify consumer checkpoints and idempotent sinks.
- [ ] Local Azure Functions tests execute through real triggers/bindings when trigger behavior must be verified.
- [ ] Cloud tests cover features/identity/networking unsupported by emulators.

### 37.4. Azure test resources

- [ ] Runs in a non-prod subscription/resource group with scope allowlisting.
- [ ] Test storage/DB/messaging accounts isolated from production data.
- [ ] IaC/provisioning attaches owner/run ID/TTL and cost metadata.
- [ ] Test identity/tenant/object ID verified so developer logins are not accidentally used.
- [ ] Data-plane RBAC allow/deny verified using appropriate principals.
- [ ] RBAC propagation uses bounded polling rather than infinite 403 retries.
- [ ] Private Endpoint/DNS/TLS tested from the actual staging runtime.
- [ ] Test runner lacks permissions to delete resources outside test scope.
- [ ] Test namespaces are unique, independent of test order or prior state.
- [ ] `finally`/CI post-step cleanup paired with manifests and a fallback janitor.
- [ ] Shared/production resources are never deleted solely because a name begins with “test”.

### 37.5. Reliability and data correctness

- [ ] Assertions check actual data and business outcomes, not just HTTP statuses.
- [ ] Negative tests cover 401/403/404/409/412/429/5xx per actually used services.
- [ ] Retries enforce max attempts/time budgets without creating duplicate side effects.
- [ ] Idempotent consumers and unique business keys tested against duplicate messages.
- [ ] Network faults, lost ACKs, and process crashes tested within authorized boundaries.
- [ ] Async SDK tests genuinely subscribe/await with deadlines.
- [ ] Clients/subscriptions/executors closed cleanly after tests.
- [ ] Bounded polling used instead of fixed sleeps for eventual behavior.
- [ ] Concurrency tests use barriers/invariants instead of relying on scheduler luck.
- [ ] Blob read-after-write and service-specific consistency interpreted accurately.

### 37.6. CI/CD, observability, and cost

- [ ] Every PR runs unit + emulator tests on Docker-capable runners.
- [ ] Nightly/release runs cloud tests with trusted CI identity/OIDC/managed identity.
- [ ] Untrusted PRs receive no cloud write credentials/secrets.
- [ ] Skipped/disabled tests are counted; critical skips fail the gate.
- [ ] JUnit reports, sanitized SDK error codes, test resource aliases, and correlation IDs recorded.
- [ ] Never log Shared Keys, connection strings, SAS, bearer tokens, or raw sensitive data.
- [ ] Cloud tests enforce time/cost/data volume limits and budgets/alerts.
- [ ] Runbooks exist for emulator incompatibility, cloud 401/403, resource leaks, queue duplicates, and cost regressions.
- [ ] Reports confirm ownership/cleanup PASS, leak counts, and active test resources.
- [ ] **Cloud-ready** is declared only after required Azure-specific boundaries are actually verified.

## 38. Conclusion

**Integration testing Azure SDKs with emulators and test resources** is a multi-layered strategy. **Unit tests** validate business logic quickly; **Azurite/Testcontainers** let the Java SDK communicate for real with Blob/Queue/Table Storage in a repeatable environment; and **Cosmos DB, Service Bus, Event Hubs, and Functions emulators** are valuable within their documented feature and version boundaries. Yet emulators never prove **Microsoft Entra ID, Azure RBAC, Private Endpoints, TLS, cloud quotas, HA, regional behavior, or full feature parity** on their own.

For Java applications on Microsoft Azure, construct clients with **dependency injection and environment-appropriate credentials and endpoints**, and run JUnit integration tests using **synthetic data, unique resource names, idempotent assertions, bounded timeouts/retries, and durable cleanup**. On real Azure, use **non-production resources** provisioned by IaC, least-privilege identities, allow/deny testing, log/metric observability, and budgets/TTLs. A trustworthy pipeline does more than turn green on HTTP success—it proves **data is accurate, permissions are right, errors are handled safely, test resources are cleaned up, and production remains untouched**. That is the foundation for upgrading the Azure SDK for Java and deploying services on Azure safely, auditably, and sustainably.
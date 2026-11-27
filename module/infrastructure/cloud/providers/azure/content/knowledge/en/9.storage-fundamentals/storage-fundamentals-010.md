# Azurite and Local Storage Development Workflows

## 1. The Problem of Developing Azure Storage Locally

In an application deployed on Microsoft Azure, data does not necessarily live only in a database. The application may store images, documents, and backup files in **Azure Blob Storage**; push asynchronous tasks into **Azure Queue Storage**; or use **Azure Table Storage** for simple NoSQL entities.

When coding on a laptop, if every test operation hits a real cloud storage account, the development team runs into several problems:

- Requires an Internet connection and active Azure access.
- Requires provisioning cloud resources and managing accounts, access keys, and spend.
- Test data can mix with shared team data.
- Automated tests become flaky when external networks or services experience issues.
- Delete, overwrite, or fault-injection tests can impact real resources.

**Azurite** is an open-source Azure Storage emulator that runs on a local machine or inside a container. Azurite exposes local endpoints that partially mimic Azure Storage services, enabling applications to use Storage SDKs to read/write data and test business flows before deploying to Azure.

Azurite is not a real Azure storage account. Its role is providing a **fast, isolated, and reproducible local development feedback loop**. After local development, you must still test against a real storage account in an integration/staging environment with the corresponding cloud networking, identity, and service features.

### Learning Objectives

After this lesson, you will be able to:

1. Explain which services Azurite emulates and how it differs from real Azure Storage.
2. Start Azurite using npm or Docker Compose.
3. Use Blob, Queue, and Table endpoints with the right local connection strings.
4. Connect a Java application to Blob Storage via the Azure SDK and perform uploads/downloads.
5. Structure configuration across local, test, staging, and production without exposing keys.
6. Write repeatable integration tests with proper data cleanup.
7. Recognize emulator limitations and how to validate on real Azure.
8. Troubleshoot common connection, authentication, container/queue, and port-conflict errors.

## 2. What Is Azurite and Which Services Does It Emulate?

Azurite is an emulator built for local development against Azure Storage data interfaces. It runs as a Node.js process or inside Docker and works with applications calling compatible Storage SDKs or REST APIs.

| Azure Storage Service | Emulated by Azurite | Application Usage Example |
|---|---|---|
| **Blob Storage** | Yes, within features and API versions supported by Azurite | Storing product images, documents, uploaded files |
| **Queue Storage** | Yes, within supported features | Queuing email-sending or image-processing jobs |
| **Table Storage** | Yes, within supported features | Storing key-value entities with PartitionKey and RowKey |
| **Azure Files** | Not an emulation target of Azurite | SMB/NFS file shares require another test environment |
| **Azure Data Lake Storage Gen2** | Does not replace full testing of ADLS Gen2 hierarchical namespace/ACL capabilities | Data analytics workloads must be tested on real Azure |

Azurite lets you test operations such as creating containers, uploading blobs, reading blobs, creating queues, enqueueing messages, or creating Table entities, depending on current support levels.

**Important:** Azurite does not guarantee 100% parity across all REST API versions, size limits, consistency behaviors, security features, network faults, performance, or policies of real Azure Storage. Code passing on Azurite is solid evidence for basic logic, **not proof of production readiness**.

## 3. Where Does Azurite Fit in Application Architecture?

A clean development workflow separates application code from Storage endpoint configuration.

~~~mermaid
flowchart LR
    A[Java app on laptop] -->|Azure Storage SDK| B{Environment configuration}
    B -->|local| C[Azurite]
    B -->|integration or staging| D[Test Azure Storage Account]
    B -->|production| E[Production Azure Storage Account]
    C --> F[Emulated Blob / Queue / Table]
    D --> G[Real Storage and cloud policies]
    E --> H[Real Storage with RBAC, networking, monitoring]
~~~

The core idea is keeping the exact same SDK interfaces and business logic while swapping configuration:

- **Local:** uses machine or container endpoints, synthetic data, and the emulator account.
- **Automated test:** spins up an isolated Azurite instance with isolated test data.
- **Staging:** verifies real Azure integration and features not emulated locally.
- **Production:** uses a storage account protected by Microsoft Entra ID, Azure RBAC, private networking, monitoring, and cost governance per architecture.

Within the broader Azure module, Azurite supports the development phase of the storage tier; subscriptions, resource groups, Entra ID, networking, and operational policies still require separate study and verification on the live platform.

## 4. Default Endpoints and the Development Account

In its default local configuration, Azurite serves three services over HTTP ports:

| Service | Default Local Endpoint | Port |
|---|---|---:|
| Blob | http://127.0.0.1:10000/devstoreaccount1 | 10000 |
| Queue | http://127.0.0.1:10001/devstoreaccount1 | 10001 |
| Table | http://127.0.0.1:10002/devstoreaccount1 | 10002 |

The emulator's default account name is **devstoreaccount1**. Azurite ships with a publicly documented default emulator key solely for development. This key is **not** a key for any real Azure storage account and must never be treated as a secure production credential.

Many Azure Storage SDKs accept the shorthand connection string:

~~~text
UseDevelopmentStorage=true
~~~

This string typically resolves to the default emulator account and endpoints. If your SDK/version does not support the shorthand string, or if Azurite runs on a custom hostname/port, supply a **full connection string** specifying AccountName, AccountKey, and corresponding endpoints per your Azurite/SDK documentation.

Example connection structure when the app runs on the **same host machine**:

~~~text
DefaultEndpointsProtocol=http;
AccountName=devstoreaccount1;
AccountKey=<development-emulator-account-key>;
BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;
QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;
TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;
~~~

In an actual config file, the string must sit on **one single line**; line breaks above are purely for readability. The AccountKey value must be the configured emulator's valid key, not a placeholder string.

**Use HTTP and shared emulator credentials only in isolated local environments.** On real Azure, use HTTPS and proper identity/key governance mechanisms.

## 5. Option 1: Running Azurite with Node.js and npm

With a currently Azurite-supported Node.js version installed, you can install Azurite as a CLI tool:

~~~bash
npm install --global azurite
~~~

Create a directory for test data and start it:

~~~bash
mkdir azurite-data
azurite --location ./azurite-data
~~~

Azurite typically starts Blob, Queue, and Table services on the three default ports. To restrict connections to the local machine, bind hosts explicitly:

~~~bash
azurite \
  --location ./azurite-data \
  --blobHost 127.0.0.1 \
  --queueHost 127.0.0.1 \
  --tableHost 127.0.0.1
~~~

Use the multiline command above in shells supporting backslashes for line continuation such as Bash. On Windows PowerShell, write the command on one line or use PowerShell's line continuation syntax.

**Where is data stored?** The directory passed to location holds emulator state and data. After stopping and restarting against the same directory, data can persist. That helps manual development, whereas automated tests should use dedicated directories so stale data does not skew results.

You can pass debug logging options for troubleshooting. However, logs may contain paths, metadata, and request details for diagnostics; do not leave verbose logging enabled indefinitely or commit debug logs containing sensitive data to repositories.

## 6. Option 2: Using Docker Compose for Reproducible Environments

Docker often suits teams because it avoids installing Azurite directly on developer machines and centralizes image versioning.

Example **docker-compose.yml**:

~~~yaml
services:
  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    container_name: azurite-local
    command: >
      azurite --location /data
      --blobHost 0.0.0.0
      --queueHost 0.0.0.0
      --tableHost 0.0.0.0
    ports:
      - "127.0.0.1:10000:10000"
      - "127.0.0.1:10001:10001"
      - "127.0.0.1:10002:10002"
    volumes:
      - ./azurite-data:/data
~~~

Start and check status:

~~~bash
docker compose up -d
docker compose ps
docker compose logs azurite
~~~

Stop the container:

~~~bash
docker compose down
~~~

The configuration above:

- Binds host ports exclusively to **127.0.0.1**, limiting access from other machines over the host's public network interfaces.
- Mounts **./azurite-data** to **/data** to persist emulator data.
- Exposes the exact three ports for Blob, Queue, and Table.
- Uses hostname **azurite** as the service name inside the Docker Compose network.

In real projects, **pin the image to a tested version or digest** rather than defaulting to latest in long-lived pipelines. This keeps CI runs stable when new emulator releases ship.

### 6.1. Distinguishing Host Localhost from Container Localhost

If the Java app runs **directly on your laptop**, the endpoint can be:

~~~text
http://127.0.0.1:10000/devstoreaccount1
~~~

If the Java app runs **inside another container on the same Compose network**, **127.0.0.1 inside the Java container refers to the Java container itself**, not the Azurite container. In that case, use the service hostname, e.g.:

~~~text
http://azurite:10000/devstoreaccount1
~~~

The shorthand **UseDevelopmentStorage=true** typically points SDKs to default localhost and may fail from inside a separate app container. Configure a full connection string with hostname **azurite**, emulator account/key, and the corresponding Blob/Queue/Table endpoints.

Host vs. container confusion is one of the most common reasons an app runs on a laptop yet integration tests in Docker fail with **Connection refused**.

## 7. Verifying Whether Azurite Is Running

On Windows PowerShell, test the Blob port:

~~~powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 10000
~~~

On a standard shell, issue an HTTP request to check for a port response:

~~~bash
curl -i http://127.0.0.1:10000/devstoreaccount1
~~~

An HTTP status like **400**, **403**, or an authentication error from the Storage API does not necessarily mean Azurite is broken. Because Storage REST API endpoints expect specific HTTP methods, headers, and signatures, a bare curl GET only confirms **a service is listening and responding on the port**.

Functional verification via a Storage SDK or Azure Storage Explorer is far more reliable: create a container, upload a blob, download it, read the data, and assert results.

If a port is already occupied by another app, remap the port via Azurite's flags and update every connection string and client config. Never change the Docker port mapping while forgetting to update the app endpoint.

## 8. Using Azure Storage Explorer with Azurite

**Azure Storage Explorer** is a GUI tool for browsing and managing Storage resources. Locally, it is handy for inspecting state while debugging SDK code.

General workflow:

1. Start Azurite.
2. Open Azure Storage Explorer.
3. Choose to connect to the **local emulator** or attach a Storage resource according to your app version.
4. Use the default emulator ports and account if running with Section 4's configuration.
5. Expand Blob Containers, Queues, or Tables.
6. Create a test container, upload a file, and reopen it to verify contents.

If Storage Explorer fails to connect, check whether Azurite is running, port mappings, account key, and the tool version. Never switch to poking at a real cloud storage account simply because of an undiagnosed local error.

Storage Explorer is convenient for manual inspection, yet **does not replace automated tests**: manual clicks are hard to repeat, miss regressions consistently, and fail to isolate shared team state.

## 9. Blob Storage Model on Azurite

Core Azure Blob Storage concepts carry straight over when learning with Azurite:

- **Storage account:** domain and credential boundary for the service; locally uses the emulator account.
- **Blob container:** grouping of blobs; names generally must follow Blob Storage naming rules.
- **Blob:** data object, such as a document, image, or JSON payload.
- **Blob name:** object name inside a container; slashes can create folder-like paths.
- **Metadata and properties:** object attributes such as content type or custom application metadata.
- **ETag:** value supporting optimistic concurrency checks where supported by the API.

Example data layout:

~~~text
devstoreaccount1
└── container: product-images
    ├── products/1001/front.jpg
    ├── products/1001/back.jpg
    └── products/1002/front.jpg
~~~

In most cases, slashes in blob names form a **logical naming structure**; do not assume Azurite provides the full directory semantics or ACLs of Azure Data Lake Storage Gen2.

A typical application flow looks like:

1. User selects a product image.
2. Backend validates content/size limits per application policy.
3. Backend creates the container if needed and uploads the Blob.
4. Backend saves the blob name or reference ID in its database.
5. On read, backend uses the SDK to fetch content and returns it after checking authorization.

Emulator test data should use non-sensitive content: sample images, text files, or synthetic data instead of real customer records.

## 10. Java Hands-On: Uploading and Downloading Blobs with the Azure SDK

When learning Azure app development, the most effective pattern is coding against the Azure SDK and switching endpoints between Azurite and real Azure Storage via configuration.

### 10.1. Dependency

In Maven, the Blob Storage library coordinates are:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
    <version>VERIFIED_VERSION</version>
</dependency>
~~~

Replace **VERIFIED_VERSION** with a current library version verified by your project to be compatible with your Java runtime and dependency management. In larger projects, manage versions via the Azure SDK BOM or internal dependency management. Avoid picking arbitrary version numbers just to make a build pass.

### 10.2. Connection Environment Variable

In PowerShell for the current session:

~~~powershell
$env:AZURE_STORAGE_CONNECTION_STRING = "UseDevelopmentStorage=true"
~~~

In Bash:

~~~bash
export AZURE_STORAGE_CONNECTION_STRING="UseDevelopmentStorage=true"
~~~

Some SDK versions or libraries may not recognize the shorthand string. In that case, use the **full** emulator connection string with AccountName, AccountKey, and exact endpoints from your Azurite setup. Never use emulator strings as credentials for a real Azure account.

### 10.3. Java Code

~~~java
import com.azure.core.util.BinaryData;
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public class AzuriteBlobDemo {
    public static void main(String[] args) {
        String connectionString =
                System.getenv("AZURE_STORAGE_CONNECTION_STRING");

        if (connectionString == null || connectionString.trim().isEmpty()) {
            throw new IllegalStateException(
                    "AZURE_STORAGE_CONNECTION_STRING is not configured");
        }

        BlobServiceClient service = new BlobServiceClientBuilder()
                .connectionString(connectionString)
                .buildClient();

        BlobContainerClient container =
                service.getBlobContainerClient("dev-documents");
        container.createIfNotExists();

        BlobClient blob = container.getBlobClient("hello.txt");
        blob.upload(BinaryData.fromString("Hello Azurite!"), true);

        String downloaded = blob.downloadContent().toString();
        System.out.println("Downloaded content: " + downloaded);
    }
}
~~~

Explanation:

- **BlobServiceClientBuilder** creates the SDK client from environment configuration.
- **getBlobContainerClient** selects a container by name.
- **createIfNotExists** makes re-running local setup convenient.
- **getBlobClient** targets a specific blob.
- **upload(..., true)** allows overwriting an existing blob with the same name; use only when business logic or lab instructions permit.
- **downloadContent** reads the Blob content back for verification.

Expected output on success:

~~~text
Downloaded content: Hello Azurite!
~~~

After running, open Azure Storage Explorer and verify container **dev-documents** contains **hello.txt**. If data doesn't show up, verify Storage Explorer connects to the exact same emulator endpoint/account as the Java app.

**Java SDK note:** API names and overloads can shift across SDK versions. Keep dependencies and code aligned to one tested version; if builds fail, consult documentation for that exact SDK version before altering logic.

### 10.4. Why Avoid Hard-Coding Connection Strings?

An application typically runs on laptops, CI, staging, and production. If a connection string is hard-coded, switching environments requires editing source code, risks leaking credentials, and complicates rollbacks.

Use environment variables or a secure configuration system. In production, prefer Microsoft Entra ID with managed identities and Azure RBAC where supported by the SDK/service rather than distributing long-lived account keys.

## 11. Java SDK: Separating Local and Real Azure

Instead of mixing environment conditionals into business logic, build a shared client factory/configuration:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

public final class StorageClientFactory {
    private StorageClientFactory() {}

    public static BlobServiceClient create() {
        String connectionString =
                System.getenv("AZURE_STORAGE_CONNECTION_STRING");

        BlobServiceClientBuilder builder = new BlobServiceClientBuilder();

        if (connectionString != null &&
                !connectionString.trim().isEmpty()) {
            // Local Azurite or an approved test connection configuration.
            return builder.connectionString(connectionString)
                    .buildClient();
        }

        String endpoint = System.getenv("AZURE_STORAGE_BLOB_ENDPOINT");
        if (endpoint == null || endpoint.trim().isEmpty()) {
            throw new IllegalStateException(
                    "Connection string or Blob endpoint must be configured");
        }

        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return builder.endpoint(endpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

To use the real Azure branch above, add the **com.azure:azure-identity** dependency at a compatible version.

Example configuration mapping:

| Environment | Client Configuration | Authentication Mechanism |
|---|---|---|
| Local | AZURE_STORAGE_CONNECTION_STRING with emulator connection | Emulator credentials |
| CI integration with Azurite | Connection string to the test run's Azurite | Emulator credentials |
| Azure staging | AZURE_STORAGE_BLOB_ENDPOINT pointing to https://<storage-account>.blob.core.windows.net | DefaultAzureCredential |
| Azure production | Real Blob endpoint and managed identity | DefaultAzureCredential with managed identity |

**Critical security point:** in staging/production, set only **AZURE_STORAGE_BLOB_ENDPOINT** and never supply an emulator connection string. An existing connection string env var takes precedence in this example factory; if accidentally deployed to production, the app could hit the wrong target. Real systems should check explicit environment names and validate configuration at startup to fail fast on unapproved endpoints.

Against real Azure Blob Storage, the app's principal needs an appropriate **data-plane** role, such as **Storage Blob Data Contributor** at the required scope to upload. Management-plane Azure RBAC roles on a resource group like Reader do not automatically grant blob read/write access.

## 12. Queue Storage Workflows on Azurite

**Azure Queue Storage** fits simple background jobs. Instead of processing an image inline during an HTTP request, the app enqueues a message and a worker processes it asynchronously:

~~~mermaid
sequenceDiagram
    participant API as API Application
    participant Q as Azurite Queue
    participant W as Background worker
    participant B as Azurite Blob
    API->>B: Upload source image
    API->>Q: Enqueue image-processing message
    W->>Q: Receive message
    Q-->>W: Content + pop receipt
    W->>B: Create thumbnail image
    W->>Q: Delete message once processing completes
~~~

Key concepts:

- **Queue:** container holding messages.
- **Message:** task payload, typically kept small with reference IDs.
- **Visibility timeout:** after a worker receives a message, it becomes temporarily invisible while the worker processes it.
- **Pop receipt:** handle required to delete or update a received message.
- **Dequeue count:** counter useful for detecting messages failing processing repeatedly.

### 12.1. Java Dependency and Basic Flow

Use **com.azure:azure-storage-queue** at a project-compatible version. Basic flow:

1. Create a **QueueServiceClient** from the connection string.
2. Select a queue, e.g., **image-jobs**, creating it if absent.
3. Send a message containing the target blob ID.
4. Worker receives the message, reads the ID, and executes the task.
5. On success, delete the message using its message ID and current pop receipt.
6. On failure, handle retries, visibility timeouts, and poison-queue thresholds per app design.

Never assume a message is delivered **exactly once**. Workers must be designed to be **idempotent**, because the same task can be redelivered after retries, timeouts, or worker crashes. Never embed large file payloads directly inside messages; store files in Blob and pass references.

### 12.2. What Cannot Be Concluded from Azurite Alone

The Queue emulator helps test send/receive/delete flows, yet does not replace cloud load testing, scale-limit evaluation, or operational behavior. If you need topics/subscriptions, broker semantics, or advanced enterprise messaging features, evaluate **Azure Service Bus**; Azurite Queue is not a full Service Bus emulator.

## 13. Table Storage Workflows on Azurite

**Azure Table Storage** is a simple NoSQL model storing **entities** keyed by partition key and row key.

Core components:

- **Table:** collection of entities.
- **PartitionKey:** key grouping related entities and aiding query routing.
- **RowKey:** key uniquely identifying an entity within a partition.
- **Properties:** columns/attributes of an entity.
- **ETag:** token supporting optimistic concurrency control on supported operations.

Example **UserPreferences** table:

| PartitionKey | RowKey | Theme | Language |
|---|---|---|---|
| tenant-a | user-001 | dark | vi |
| tenant-a | user-002 | light | en |
| tenant-b | user-001 | dark | vi |

Entities are uniquely identified by **PartitionKey + RowKey**. PartitionKey design affects query patterns and data distribution once on real Azure. Do not design Table Storage like a relational database with arbitrary joins.

The Java SDK for Table operations is **com.azure:azure-data-tables**. Basic learning flow:

1. Create a TableServiceClient from local connection settings.
2. Create a test table or select an existing one.
3. Insert an entity with PartitionKey, RowKey, and properties.
4. Read the entity by keys and update a property.
5. Test handling already-existing entities or ETag conflicts.
6. Delete test data upon completion.

Minor differences in APIs, indexing, batch transactions, data types, or emulator limits must be re-verified on real Azure Storage before finalizing system designs.

## 14. Repeatable Local Development Workflow

A workflow should follow a consistent sequence:

~~~mermaid
flowchart TD
    A[Checkout application code] --> B[Start Azurite]
    B --> C[Load local environment config]
    C --> D[Initialize lab containers / queues / tables]
    D --> E[Run Java application]
    E --> F[Execute Blob / Queue / Table workflows]
    F --> G[Inspect data and logs]
    G --> H{Results correct?}
    H -->|No| I[Fix code or config]
    I --> E
    H -->|Yes| J[Run integration tests]
    J --> K[Clean test data and stop emulator]
~~~

For manual development, a persistent volume across sessions is convenient. For CI or integration tests, start with a fresh environment each run to eliminate dependencies on stale data.

### 14.1. Consistent Resource Naming

Examples:

- Blob containers: **dev-documents**, **test-uploads**.
- Queue: **image-jobs**.
- Table: **UserPreferences**.
- Blob name: **users/u001/profile.json**.

Container/queue/table names obey distinct rules for casing, characters, and length. Use naming conventions accepted by both real Azure and Azurite; never rely on quirks permitted only by the emulator.

### 14.2. Local Configuration Must Never Leak into Production

In source code and deployment manifests, separate clearly:

- **Local** configuration used only when a developer explicitly selects the local environment.
- **Test** configuration used in pipelines against an Azurite instance spun up for that pipeline.
- **Staging/prod** configuration using approved Azure endpoints and secure authentication mechanisms.

Never use a fallback default pointing to local when production env vars are missing, silently writing to an emulator. Applications must **fail fast** if real-environment endpoints or credentials are absent.

## 15. Organizing Automated Integration Tests

Azurite delivers the most value when paired with integration tests creating real resources inside the emulator rather than mocking the entire SDK.

### 15.1. Test Pyramid Layers

| Test Type | Requirements | What to Verify |
|---|---|---|
| Unit test | App mocks/fakes and repositories; Azurite not required | Business rules, input validation, error branching |
| Local integration test | Fresh Azurite or isolated test data | SDK connectivity, create/upload/download/list/delete, queue workflows |
| Cloud contract/compatibility test | Test Azure Storage account | API versions, authentication, cloud features, limits, networking |
| Staging end-to-end | App and real Azure components | Identity permissions, data processing, retries, observability, private networking |

Azurite does not replace all other testing layers. A solid test suite combines a fast local tier with controlled cloud validation.

### 15.2. Principles of Independent Tests

- Each test suite uses its own container/queue/table or unique suffix.
- Setup creates required resources; teardown deletes only objects owned by the test.
- Zero reliance on test execution order, yesterday's leftover data, or one developer's machine.
- Use small file payloads, synthetic data, and deterministic expected outputs.
- Test both happy paths and expected errors: reading nonexistent blobs, overwrite behavior, duplicate queue message delivery, invalid names.
- Enforce timeouts on retryable calls; on failure, print endpoint/log context to aid debugging.
- Pin a controlled Azurite version to avoid drift between CI and laptops.

### 15.3. Sample Scenarios for Practice

A Blob integration test scenario:

~~~text
Given: container test-docs does not exist yet
When:  application creates the container and uploads hello.txt
Then:  blob contains "hello-local"

When:  application downloads hello.txt
Then:  content matches the uploaded data

When:  application deletes the blob
Then:  blob is no longer readable per SDK/API expectations
~~~

A Queue scenario:

~~~text
Given: queue image-jobs is empty
When:  producer sends message "job-001"
And:   worker receives and processes it successfully
Then:  worker deletes the message with a valid pop receipt
And:   subsequent receives no longer see that message
~~~

These tests validate **the application's contract with the Storage SDK**. They do not prove high-load throughput, production network security, or every real Azure retry behavior.

### 15.4. Safe Cleanup

During testing, delete only containers/queues/tables belonging to the lab when finished. Avoid bulk-delete scripts accidentally aimed at a cloud storage account due to a misset environment variable. Before any automated teardown, assert hostname, account name, and environment.

## 16. Integrating Azurite with CI/CD

In CI/CD, Azurite can run as a **service container** or a container started prior to tests. Exact syntax varies by CI platform, yet the common pattern is:

1. Pipeline provisions the test environment and starts Azurite.
2. Wait until all three ports are reachable at the hostname used by the test job.
3. Pass the local connection string to the test runner process.
4. Execute unit/integration tests.
5. Collect Azurite logs and test reports on failure.
6. Stop the container and clean temporary volumes after the job.

If the CI runner executes tests **outside Docker**, use localhost and mapped ports. If the test runner lives in **another container**, use the service DNS hostname on the container network and a connection string with matching endpoints.

Never sleep a fixed number of seconds assuming the emulator is ready; probe the TCP port or run a lightweight SDK health check with bounded retries. This eliminates flaky failures on slower CI agents.

Pin both the Azurite image and SDK dependencies to tested versions; upgrade deliberately, because emulator API/version changes can alter existing test outcomes.

## 17. Emulator Keys vs. Managed Identities

Security postures differ dramatically between local and cloud.

### 17.1. Local

Locally, **devstoreaccount1** and the emulator key are default development values. The Storage SDK authenticates requests with this key, yet it is **not the real Azure RBAC system**.

### 17.2. Azure Staging/Production

In Azure, plan for:

- **Managed identities** for VMs, App Service, Functions, or supported workloads.
- **DefaultAzureCredential** in SDKs to pick the right identity mechanism per runtime environment.
- **Storage Blob Data Reader/Contributor** or matching data-plane roles as needed.
- **HTTPS**, firewalls, and private endpoints per architecture requirements.
- **Key Vault** for unavoidable secrets, paired with rotation and restricted access.
- **Azure Monitor** and appropriate logging to audit data operations.

Some OAuth emulation modes exist in certain Azurite versions/configs, yet **they never replace validating real Microsoft Entra ID policies, Conditional Access, data-plane RBAC, and managed identities**. Therefore, all cloud-authorization features require dedicated tests on real Azure.

### 17.3. Never Confuse Management-Plane and Data-Plane Roles

Having permission to edit a storage account in Azure Resource Manager does not automatically let an app read Blob data. Data permissions are enforced through data-plane roles/credentials and network rules—a critical distinction local Azurite does not fully mirror.

## 18. Differences That Must Be Re-Tested on Real Azure

| Area | What Azurite Helps With | Mandatory Extra Verification on Real Azure |
|---|---|---|
| Blob CRUD | Container creation, upload/download/delete within supported scope | Service limits, performance, networking, encryption policies |
| Queue CRUD | Basic message send/receive/delete | Behavior under load, retries, concurrency, service limits |
| Table operations | Key-based entity create/read/update | Query performance, scale, transactions/ETags as needed |
| Authentication | Development key and supported emulation modes | Real Microsoft Entra ID, managed identities, SAS/RBAC |
| HTTPS/TLS | Optional customizable local config | Production TLS, certificates, and security policies |
| Networking | Localhost/container network connectivity | Storage firewalls, VNet/private endpoints, private DNS |
| Monitoring | Emulator process logs | Azure Monitor, diagnostic settings, metrics, auditing |
| Availability/DR | Basic retry/fallback logic tests | Storage account geo-redundancy, replication, failover |
| Performance | Functional testing on a laptop | Real latency, throughput, quotas, throttling |
| API versions | APIs implemented by the emulator | Newer SDK/API compatibility and Azure-specific features |

Some SDKs calling a newer API version than Azurite supports may return incompatibility errors. Never casually enable options that **skip API version checks** and claim full compatibility; that is strictly a limited debugging workaround and never replaces aligned emulator/SDK versions.

## 19. Troubleshooting Common Issues

### 19.1. Connection Refused or ECONNREFUSED

**Symptom:** application cannot connect to 127.0.0.1:10000.

**Check:** Is Azurite running, are ports mapped properly, has the container finished initializing, and does the hostname point to the right network namespace? In Docker Compose, if both app and Azurite run in containers, use service hostname **azurite** instead of localhost.

### 19.2. AuthorizationFailure or AuthenticationFailed

**Symptom:** SDK receives 403 or invalid signature errors.

**Check:** account name, account key, Blob/Queue/Table endpoints, and connection string syntax. Use **UseDevelopmentStorage=true** when supported by your SDK version and default setup. If using a custom account or non-default ports, update the entire connection string.

Never point real Azure connection strings at local or use emulator keys against cloud storage accounts.

### 19.3. HTTP/HTTPS Errors

Azurite runs HTTP by default. If a client is configured with **https://127.0.0.1:10000** while Azurite has no TLS enabled, connections fail during handshake or certificate validation.

Keep local HTTP on loopback for simple labs; if testing real HTTPS locally, configure certificates and TLS on the emulator per product instructions. Production must use real HTTPS endpoints.

### 19.4. ContainerNotFound or BlobNotFound

**Symptom:** upload or download returns 404.

**Check:** Has the container been created, does container/blob casing match, are operations hitting the exact same emulator account and data directory, or did another process wipe the data?

### 19.5. Unsupported API Version or InvalidHeaderValue

Likely caused by the SDK sending a newer Storage REST API version than the running Azurite supports, or an unsupported endpoint operation. Record the SDK version, Azurite version, and API version in the request, then upgrade the emulator or adjust tests to supported capabilities.

Never treat skipping API version checks as a permanent fix or proof of faithful emulation.

### 19.6. Data Differs Across Runs

When reusing a volume/data directory, blobs or queues from earlier runs may linger. In manual testing, stay aware of which volume is mounted. In integration tests, use ephemeral volumes or unique resource names and clean up after the suite.

### 19.7. Port Conflicts on 10000/10001/10002

Another Azurite instance or local service may already bind those ports. Inspect listening processes, stop stray processes, or remap ports. Every endpoint and connection string must match the new ports.

### 19.8. Storage Explorer Sees Different Data Than the App

Usually caused by Storage Explorer pointing at a different emulator instance, port, account, or volume. Compare the Blob endpoint and container name in the SDK against Storage Explorer's connection details.

### 19.9. Tests Pass Locally Yet Fail in Staging

Verify Azure credentials, data-plane permissions, private endpoints/firewalls, DNS, TLS, and API behavior. This is precisely why a **cloud integration test** layer is needed alongside Azurite.

## 20. Suggested Project Layout

A Java project may be structured as:

~~~text
storage-demo/
├── src/
│   ├── main/java/.../StorageClientFactory.java
│   ├── main/java/.../DocumentService.java
│   └── test/java/.../DocumentStorageIntegrationTest.java
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
~~~

This is a **reference layout**. Do not create or edit these project files as part of reading this lesson.

Suggested **.env.example** content:

~~~dotenv
APP_ENV=local
AZURE_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true
~~~

When running on Azure, supply an independent environment configuration, such as:

~~~text
APP_ENV=production
AZURE_STORAGE_BLOB_ENDPOINT=https://<storage-account>.blob.core.windows.net
~~~

Never put private keys, cloud account keys, or production connection strings into **.env.example**, Git, or logs. If using a **.env** file holding personal details/credentials, add it to repository ignore rules and restrict file permissions.

For production, deliver configuration via managed identities or an approved config/secret manager rather than copying local files onto servers.

## 21. End-to-End Exercise: Documents and Background Processing

**Context:** you are building a document upload service in Java. Documents go into Blob Storage, while thumbnail generation or metadata extraction jobs go into Queue Storage.

### Part A — Start Local Storage

1. Start Azurite with npm or Docker Compose.
2. Verify ports 10000 and 10001 respond.
3. Use **UseDevelopmentStorage=true** if the app runs on the host machine and your SDK supports it.
4. Open Azure Storage Explorer and confirm connection to the emulator.

### Part B — Blob

1. Create Blob container **dev-documents**.
2. Use the Java program from Section 10 to upload **hello.txt**.
3. Download and verify its contents.
4. Try uploading the same blob name with overwrite enabled and disabled to observe application behavior.
5. Attempt to read a nonexistent blob and record the SDK exception.

### Part C — Queue

1. Create queue **image-jobs**.
2. Enqueue a message containing blob name **hello.txt** or a matching job ID.
3. Have a worker read the message and log simulated processing.
4. Delete the message only after processing finishes.
5. Simulate a worker failure before deletion and observe the message becoming visible again after the visibility timeout expires.

### Part D — Testing

1. Add a Blob upload/download integration test.
2. Add a Queue send/receive/delete integration test.
3. Run tests multiple times with isolated data to verify repeatability.
4. Inspect state in Storage Explorer and Azurite logs when a test fails.
5. Delete only lab-created resources, leaving unrelated resources intact.

### Part E — Promote to Staging Azure

1. Provision an approved **staging** Azure Storage Account.
2. Configure the Azure HTTPS endpoint and an identity with required data-plane permissions.
3. Re-run integration scenarios in staging using synthetic data.
4. Validate networking/firewalls, credentials, logging, retries, and Azure features not captured by the emulator.
5. Summarize differences and refine code or config based on real findings.

**Completion criteria:** the app uses a unified Storage SDK layer, local tests target Azurite, staging uses a real storage account, and zero cloud credentials live in source code.

## 22. Pre-Production Storage Readiness Checklist

- [ ] Correctly identified Blob, Queue, or Table—never confused with Azure Files/Service Bus.
- [ ] Azurite configured with the right ports, hostname, and data directory.
- [ ] Local connection strings restricted strictly to local/test.
- [ ] App fails fast when staging/production configuration is missing.
- [ ] Automated integration tests cover CRUD and critical failure paths.
- [ ] Test data is synthetic and contains zero real customer data.
- [ ] CI spins up an isolated Azurite instance and collects logs on failure.
- [ ] Test cleanup is tightly scoped, never risking deletion against real cloud accounts.
- [ ] Verified API/version parity and features unsupported by Azurite.
- [ ] Azure staging enforces HTTPS, data-plane RBAC, managed identities, and network policies.
- [ ] Monitoring, retries, timeouts, and data protection policies exist in real Azure.
- [ ] Cloud costs and staging cleanup procedures planned for idle resources.

## 23. Self-Check Questions

1. Why does Azurite shorten feedback loops when developing Storage apps on a laptop?
2. Which services does Azurite emulate, and why should it not be used to fully test Azure Files or Data Lake Storage Gen2?
3. Which services correspond to default ports 10000, 10001, and 10002?
4. Why can **UseDevelopmentStorage=true** work on the host machine yet fail inside an app container sharing Docker Compose?
5. Why is a bare curl GET returning HTTP 403 insufficient to conclude Azurite is down?
6. In Java, why separate connection strings from business logic?
7. When should managed identities be used instead of emulator account keys?
8. With Queue Storage, why must workers be designed idempotently?
9. How should an integration test set up data and clean up so it never depends on prior runs?
10. Which categories of tests must still be run on real Azure even after all Azurite tests PASS?

## 24. Summary

**Azurite** is an emulator for Azure Blob, Queue, and Table Storage running locally or in containers. It lets Java applications interact through the Azure SDK, create test data, and test uploads/downloads and asynchronous workflows without hitting a cloud storage account on every code edit.

A sound workflow cleanly separates **local Azurite → automated integration tests → Azure staging → production**, manages endpoints through configuration, avoids hard-coding credentials, and always validates compatibility on real Azure. Use Azurite to accelerate development, then rely on Microsoft Entra ID, Azure RBAC, network controls, monitoring, and cloud tests to ensure security and reliability when deploying Storage applications to production.

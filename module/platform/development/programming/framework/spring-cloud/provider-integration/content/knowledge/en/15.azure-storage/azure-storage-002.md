# Configuring the Blob Client and Container/Blob Operations in Spring Boot

## 1. Objectives and Real-World Problem

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, the goal is to integrate Spring Boot with managed services from AWS, Azure, and Google Cloud using appropriate libraries, while understanding identity, access control, secret protection, and integration testing. This lesson focuses on **Azure Blob Storage**: creating and configuring clients, accessing containers, and uploading/downloading/listing/deleting blobs using **Spring Cloud Azure** and the **Azure Storage SDK for Java**.

Imagine a contract management system: users upload PDF files, Spring Boot stores the content in Azure Blob Storage, a database stores contract metadata along with the **blob name**, and authorized users can download the document later. To implement this properly, we need to answer:

- How should the **storage account**, **container**, and **blob** be created?
- How do **BlobServiceClient**, **BlobContainerClient**, and **BlobClient** differ?
- How does Spring Boot obtain endpoint and credential details, especially when running with **managed identity**?
- How can a file be uploaded/downloaded without embedding an account key in source code?
- How should permissions, duplicate writes, accidental deletions, network errors, and testing be handled?

**Expected outcome:** be able to configure clients via Spring Cloud Azure, explain the core APIs, write a Spring Boot service for Blob operations, and identify what must be added for production readiness.

## 2. Data Model and Client Hierarchy

Azure Blob Storage stores **objects** (blobs), typically unstructured data such as PDFs, images, videos, export files, backups, or event data. Basic access model:

~~~text
Azure subscription
└── Storage account: appstorageprod
    └── Blob service
        ├── Container: documents
        │   ├── contracts/2026/a81f.pdf
        │   └── contracts/2026/b91d.pdf
        └── Container: avatars
            └── users/u42.png
~~~

The URL typically has the form:

~~~text
https://<storage-account>.blob.core.windows.net/<container>/<blob-name>
~~~

Three SDK levels align with this structure:

| Java Client | Scope | Typical Operations |
|---|---|---|
| `BlobServiceClient` | Blob service of a storage account | List containers, get container client, create container |
| `BlobContainerClient` | One container | Create/delete container, list blobs, get blob client |
| `BlobClient` | One specific blob | Upload, download, read properties, metadata, delete |

**Note:** `getBlobContainerClient(name)` or `getBlobClient(name)` only creates an SDK reference object to the resource; it **does not automatically create the container/blob on Azure**. Blob names can contain `/` characters to simulate a directory tree via prefixes like `contracts/2026/a81f.pdf`. With standard flat-namespace Blob Storage, this is primarily an **object name**, not a real SMB directory. Accounts with hierarchical namespace enabled (ADLS Gen2) have different directory semantics, which are outside the main examples in this lesson.

The following examples use **block blobs**, the type suited for ordinary documents and images. **Append blobs** are for certain append-only cases, and **page blobs** serve page-based access; do not assume every blob shares the same efficient write pattern.

## 3. Resource Provisioning and Access Permissions

Before running the application, you need an **Azure Storage account** supporting Blob, choosing region/replication/networking per requirements. The examples use:

- Storage account: value provided via the `AZURE_STORAGE_ACCOUNT_NAME` environment variable.
- Private container: `documents`.
- Application identity: developer Azure CLI login when running locally, **managed identity** when running on a supported Azure service.
- Data access role: at minimum **Storage Blob Data Contributor** when the app needs to upload/download/delete; if read-only, consider **Storage Blob Data Reader**.

RBAC roles must be assigned to the **right principal** at the **right scope** (storage account or container). Resource management permissions via Azure Resource Manager such as `Reader` or `Contributor` do not automatically grant read/write blob permissions over the OAuth data plane. If the application needs to **create new containers**, check the scope and container-management permissions separately, because a role scoped only to a container that does not yet exist typically does not cover the initialization step.

In addition to RBAC, check **network access**: storage firewall, private endpoints, DNS, and the runtime environment must allow connectivity to the Blob endpoint. A principal with valid RBAC can still fail to connect if blocked by networking.

**Operational principle:** create containers during infrastructure provisioning or migrations; business applications usually only need permissions to operate on blobs inside existing containers. Do not enable public anonymous access for private documents.

## 4. Declaring Spring Cloud Azure and Configuring the Blob Client

### 4.1. Dependencies

Use the **Spring Cloud Azure Blob Storage starter** and a BOM compatible with your project's Spring Boot version. Maven example:

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
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

`spring-cloud-azure.version` is a property to declare in the POM or project-level version management. Do not pick the latest version at random: consult the **Spring Boot ↔ Spring Cloud Azure compatibility matrix** in the official documentation.

### 4.2. Configuration via `application.yml`

~~~yaml
spring:
  cloud:
    azure:
      storage:
        blob:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  storage:
    documents-container: ${DOCUMENTS_CONTAINER:documents}
~~~

Here:

- `spring.cloud.azure.storage.blob.account-name` specifies the storage account for auto-configuration to build the Blob client.
- `AZURE_STORAGE_ACCOUNT_NAME` is provided in the deployment environment; never hardcode a fixed account name in code.
- `app.storage.documents-container` is an **application-defined property**, used to change the container name without modifying Java code.
- If using an Azure sovereign cloud, custom endpoint, or Azurite, configure the corresponding endpoint/credentials. With Azure Private Endpoint, the app typically continues using the standard Blob hostname and **DNS resolves this hostname to a private IP**; do not manually replace the hostname with an IP address.

When the appropriate starter is enabled and configuration is valid, Spring Cloud Azure can provide a `BlobServiceClient` bean for the app to inject via constructor. Credential resolution depends on Azure Identity/Spring Cloud Azure configuration and the environment. For local development, `az login` can be used; in Azure production, prefer managed identity with assigned data-plane roles.

**Do not store** account keys, production connection strings, SAS tokens, or client secrets directly in `application.yml` files committed to Git.

### 4.3. Example of Obtaining Clients from Spring Boot

~~~java
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class BlobAccess {
    private final BlobServiceClient serviceClient;
    private final BlobContainerClient documents;

    public BlobAccess(
            BlobServiceClient serviceClient,
            @Value("${app.storage.documents-container}") String containerName) {
        this.serviceClient = serviceClient;
        this.documents = serviceClient.getBlobContainerClient(containerName);
    }

    public BlobContainerClient documents() {
        return documents;
    }

    public BlobServiceClient service() {
        return serviceClient;
    }
}
~~~

`BlobAccess` illustrates two client levels: from `BlobServiceClient` to `BlobContainerClient`. SDK clients are reusable across many calls; they should be created/injected at the application lifecycle rather than creating a new client and credential for every request.

### 4.4. When Manual Client Configuration Is Needed

Starters are not mandatory in every architecture. With the standalone Azure SDK, you can build a `BlobServiceClient` using an endpoint and **DefaultAzureCredential**:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

String account = System.getenv("AZURE_STORAGE_ACCOUNT_NAME");
if (account == null || account.isBlank()) {
    throw new IllegalStateException("Missing AZURE_STORAGE_ACCOUNT_NAME");
}

BlobServiceClient serviceClient = new BlobServiceClientBuilder()
        .endpoint("https://" + account + ".blob.core.windows.net")
        .credential(new DefaultAzureCredentialBuilder().build())
        .buildClient();
~~~

If you choose this approach, the project must declare the Azure SDK dependencies `azure-storage-blob` and `azure-identity` with aligned versions via an appropriate BOM. `DefaultAzureCredential` can probe multiple identity sources (environment variables, managed identity, developer tool logins, depending on availability and SDK version). In production, explicitly verify which identity is authorized to issue tokens; do not rely on developer machine credentials.

**Do not manually declare another bean of the same type** if you already let Spring Cloud Azure create the bean and have no explicit override need; this easily causes duplicate injection errors or incorrect configuration usage.

## 5. Working with Containers

A container is the organizational unit for blobs and often serves as an access-control/lifecycle boundary. Container names must follow Azure rules: lowercase letters, digits, and hyphens with valid length (typically 3–63 characters), such as `documents` or `product-images`. Names with uppercase letters or underscores like `Customer_Files` are invalid.

### 5.1. Getting a Container and Controlled Initialization

~~~java
BlobContainerClient container =
        serviceClient.getBlobContainerClient("documents");

// Only use during provisioning/migration steps with sufficient permissions:
container.createIfNotExists();

boolean available = container.exists();
System.out.println("Container exists: " + available);
~~~

`createIfNotExists()` is useful when running idempotent initialization scripts. However, an application with only blob-level read permissions cannot create containers; therefore **do not put this call on every request** or rely on it to mask missing-permission errors. Run provisioning via controlled IaC/migrations, then configure the application to reference existing containers only.

### 5.2. Listing Containers

~~~java
for (var item : serviceClient.listBlobContainers()) {
    System.out.println(item.getName());
}
~~~

Listing containers may require broader permissions than operating on a blob in a known container. If the architecture restricts the application to just the `documents` container, do not request broader permissions merely to support an unnecessary listing feature.

### 5.3. Deleting a Container

~~~java
// Administrative command capable of deleting all blobs in the container!
boolean deleted = container.deleteIfExists();
~~~

`deleteIfExists()` affects the **entire contents of the container** and should only be used in administrative tools, test environments, or controlled cleanup workflows. To delete **a single document**, operate on the corresponding `BlobClient`, never delete the container.

## 6. Working with Blobs from Spring Boot

### 6.1. Uploading a Document

Example service saving a `MultipartFile` to the `documents` container, generating a random blob name to avoid overwrites when two users upload files with the same filename:

~~~java
import com.azure.storage.blob.BlobClient;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.models.BlobHttpHeaders;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class DocumentStorageService {
    private final BlobContainerClient container;

    public DocumentStorageService(BlobAccess blobAccess) {
        this.container = blobAccess.documents();
    }

    public String upload(MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Uploaded file must not be empty");
        }

        String blobName = "contracts/" + UUID.randomUUID() + ".bin";
        BlobClient blob = container.getBlobClient(blobName);

        try (InputStream input = file.getInputStream()) {
            // false: do not overwrite if the blob already exists.
            blob.upload(input, file.getSize(), false);
        }

        // Only attach a verified MIME type. This example uses a safe generic type.
        blob.setHttpHeaders(
                new BlobHttpHeaders().setContentType("application/octet-stream"));
        return blobName;
    }

    public void download(String blobName, OutputStream output) {
        BlobClient blob = container.getBlobClient(blobName);
        blob.downloadStream(output);
    }

    public boolean delete(String blobName) {
        BlobClient blob = container.getBlobClient(blobName);
        return blob.deleteIfExists();
    }
}
~~~

**Design rationale:**

- `BlobClient` is a reference to **a blob name** and can be used immediately to upload even when the blob does not yet exist.
- `upload(stream, length, false)` sends content from the stream, only allowing creation and throwing an error if the name already exists. Setting `true` permits the SDK to overwrite an existing blob; do not enable it just to silence name-collision errors.
- `MultipartFile.getSize()` provides the expected byte count, which must match the actual data from the input stream.
- `setHttpHeaders` sets Content-Type **after uploading**. In practice this is a separate network call; if it fails, the blob may already exist. The service needs logging and an appropriate retry/reconciliation mechanism. Upload option APIs can be used to attach headers in the upload request/flow if required.
- Only use `application/pdf` after the system has verified the file is genuinely a PDF; never blindly trust the client-supplied MIME type.
- The blob name is generated from a UUID rather than concatenating the user-supplied filename directly. Store the original filename, owner, and blob name in the database to enforce permissions at the business layer.

**Limitations of the example:** user authentication, upload size limits, content scanning, file-type validation, multipart upload handling, and data rollback are not yet implemented. This service illustrates the Blob API, not a complete public endpoint.

### 6.2. Uploading with a REST Controller

~~~java
import java.io.IOException;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {
    private final DocumentStorageService storage;

    public DocumentController(DocumentStorageService storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, String> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        String blobName = storage.upload(file);
        return Map.of("blobName", blobName);
    }
}
~~~

Example invocation:

~~~bash
curl -X POST \
  -F "file=@contract.pdf" \
  http://localhost:8080/api/documents
~~~

A real application needs Spring Security, request size limits, and tenant/user authorization checks before granting access. Returning only `blobName` in the response does not mean the blob is publicly accessible to anyone who knows its name.

### 6.3. Downloading a Blob

For small files, the SDK allows reading data into memory:

~~~java
BlobClient blob = container.getBlobClient("contracts/example.pdf");
byte[] bytes = blob.downloadContent().toBytes();
~~~

For large files, **stream to an output** instead of loading the entire file into RAM:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path target = Path.of("downloaded-contract.pdf");
try (OutputStream output = Files.newOutputStream(target)) {
    container.getBlobClient("contracts/example.pdf")
             .downloadStream(output);
}
~~~

If streaming directly to a Spring MVC HTTP response, authenticate and authorize before writing the stream; handle Content-Type, Content-Disposition, Content-Length, and client disconnect errors. Do not let an API accept an arbitrary `blobName` and download it without checking ownership; keeping the blob private in Azure does not replace backend authorization.

### 6.4. Listing Blobs by Prefix

~~~java
import com.azure.storage.blob.models.BlobItem;
import com.azure.storage.blob.models.ListBlobsOptions;
import java.time.Duration;

for (BlobItem item : container.listBlobs(
        new ListBlobsOptions().setPrefix("contracts/"),
        Duration.ofSeconds(30))) {
    System.out.println(item.getName());
}
~~~

The `contracts/` prefix only filters **blob names**, not a filesystem or database query. Listing may be paginated; paging SDKs fetch subsequent pages automatically while iterating. For very large datasets, do not scan the entire container to find one document by ID if the database already stores the blob name; access it directly by key. For business search features, use a database/index to filter metadata by tenant, creator, timestamp, or status.

### 6.5. Reading Properties and Metadata

~~~java
import java.util.Map;

BlobClient blob = container.getBlobClient("contracts/example.pdf");

var properties = blob.getProperties();
System.out.println("Size: " + properties.getBlobSize());
System.out.println("Content-Type: " + properties.getContentType());
System.out.println("ETag: " + properties.getETag());

blob.setMetadata(Map.of(
        "documentType", "contract",
        "source", "portal"
));
~~~

**Properties** are system attributes such as size, Content-Type, ETag, and Last-Modified. **Metadata** consists of application-attached key-value pairs; never store secrets or sensitive data in metadata. Metadata key naming rules must comply with Azure Storage and may differ from database column names. Calling `setMetadata` **replaces the existing metadata set**, so read and merge first if you want to preserve previous keys.

ETags help prevent overwrites when multiple actors update the same blob. You can pass an `If-Match` condition with the previously read ETag so the operation succeeds only if the blob has not changed; on mismatch, the server returns a precondition error (typically HTTP **412**). This fits **optimistic concurrency**, avoiding uncontrolled "last writer wins" behavior.

### 6.6. Deleting a Blob

~~~java
BlobClient blob = container.getBlobClient("contracts/example.pdf");
boolean existedAndDeleted = blob.deleteIfExists();
~~~

Do not delete a blob based solely on a client-supplied name: verify permissions, business constraints, and retention requirements. If the storage account enables **soft delete**, **versioning**, or retention policies, deletion does not necessarily make the data disappear permanently right away. For data with legal requirements, also consider immutability policies/legal hold.

## 7. End-to-End Processing Flow

~~~mermaid
flowchart LR
    U[Authenticated User] -->|POST file| A[Spring Boot Controller]
    A -->|Check permissions and file| S[DocumentStorageService]
    S -->|BlobServiceClient / ContainerClient / BlobClient| B[(Azure Blob Storage)]
    S -->|Save blobName + owner + status| D[(Database)]
    U -->|Request document download| A
    A -->|Check owner/tenant| D
    A -->|Read blob by key| B
~~~

Recommended flow:

1. The backend checks upload permissions, size, and format, and generates `documentId`/`blobName`.
2. The backend uploads the Blob into a private container.
3. The backend writes a record containing `documentId`, `blobName`, `ownerId`, and `status` to the database.
4. On download, the backend fetches the record by business ID, checks user authorization, and then streams the blob or issues time-limited download access.
5. The system logs `documentId`, request/correlation ID, and SDK errors; never log document contents or secrets.

**Consistency warning:** Blob Storage and the database do not share a transaction. If the upload succeeds but the database write fails, an **orphan blob** may remain. If the DB writes first and the upload fails, the record may remain in a `PENDING` state. The design should include business states, idempotent retries, and a periodic cleanup/reconciliation job for these cases.

## 8. Identity, Secrets, SAS, and Access Security

### 8.1. Authenticating with Azure Identities

Recommended order of preference in modern deployments:

1. **Managed identity** for applications running on Azure: no long-lived secrets issued to the application.
2. **Developer identity** for local machines via Azure CLI or IDE tools when permitted by the organization.
3. **Service principal** in CI/CD or environments without managed identity support, preferring identity federation/federated credentials if available; if a client secret must be used, store it in a secret vault and rotate it.

`DefaultAzureCredential` is helpful because the same code can work across environments, but you must know which credential source was actually selected. If running on Azure and the principal lacks RBAC, fix the **role assignment** instead of falling back to hardcoding an account key. The `Storage Blob Data Contributor` role covers write/delete operations; `Storage Blob Data Reader` covers read-only workloads.

### 8.2. Private Containers and Short-Lived Download Access

Do not enable public access just to make frontend downloads easier. Two common approaches:

- **Backend proxy:** the client calls Spring Boot; the backend verifies authorization and streams Blob data, fitting strict access auditing needs at the cost of extra traffic through the backend.
- **Scoped SAS:** the backend verifies permissions and issues a read-only SAS URL for **a single blob** with a short expiration. Prefer **user delegation SAS** when the system uses Microsoft Entra ID and configuration allows; a SAS is not by itself an end-user authorization check.

Do not embed long-lived SAS tokens in public databases, logs, or shared frontend code; likewise, never issue a SAS with delete/write permissions when only download is needed.

### 8.3. Safeguards Beyond Credentials

- Use HTTPS/TLS, restrict public network access, and use private endpoints when appropriate for the infrastructure.
- Check CORS if browsers access Blob directly; CORS does not grant permissions, it only controls browser cross-origin policies.
- Scope permissions per container or storage account and separate identities for upload, read-only, and administrative services whenever possible.
- Enable appropriate logging/metrics, versioning or soft delete if recovery is required, and lifecycle rules to avoid unbounded storage growth.
- Never rely on container names or blob prefixes as the sole security control; access must rely on credentials/RBAC and application authorization.

## 9. Common Errors, Consistency, and Performance

| Symptom | Causes to Check | Resolution |
|---|---|---|
| HTTP 403 | Principal lacks data-plane permissions, expired SAS, or storage firewall blocking | Verify effective identity, role assignment, scope, and network |
| HTTP 404 | Wrong account/container/blob name; container not provisioned | Check endpoint, names, and environment; remember blob names are case-sensitive |
| HTTP 409 on upload | Blob already exists and `overwrite=false`; or resource conflict | Generate unique names, handle duplicates via business logic |
| HTTP 412 | ETag/write condition no longer valid | Read latest state and handle concurrent updates |
| Timeout or throttling | Network, large payload, request limits, slow connection | Use retries with backoff, monitor latency/429/503; tune parallelism to load |
| Works locally, fails on Azure | Local runs as developer account rather than managed identity | Check production identity role assignments and private DNS |
| Upload succeeds but app returns error | A post-upload step (metadata/DB/API) failed | Design state tracking and reconciliation, avoid non-idempotent duplicate uploads |

**Retries do not mean every operation is safe to repeat.** For uploads that generate a new random name on each retry, client retries can create multiple blobs. Attach a stable `requestId`/`documentId`, build duplicate-request detection, and select appropriate `overwrite`/conditional write behavior.

Regarding performance:

- For large files, prefer **streaming** APIs, block-based upload/download, or SDK-supported parallel transfer settings; do not use `downloadContent().toBytes()` for large media.
- Reuse clients and connections; do not instantiate a new credential per HTTP request.
- Use prefixes to organize blob names; use a database/index for complex business queries.
- Evaluate access tiers, lifecycle policies, and read/write/egress costs against actual needs.
- If the app uses WebFlux/Reactor, consider **BlobServiceAsyncClient/BlobAsyncClient** instead of calling sync clients that block the event loop.

## 10. Integration Testing with Azurite and Real Azure

**Azurite** is a local emulator for many Azure Storage Blob/Queue/Table operations, useful for verifying basic upload/list/download/delete flows without provisioning cloud resources on every test run. However, it **does not fully emulate** all Azure Blob features, Microsoft Entra ID RBAC, private endpoints, or production network configurations.

A test running against Azurite can create a client using an **emulator-only** connection string:

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

String azuriteConnectionString =
        System.getenv("AZURITE_STORAGE_CONNECTION_STRING");
BlobServiceClient testClient = new BlobServiceClientBuilder()
        .connectionString(azuriteConnectionString)
        .buildClient();

String testContainer = "documents-test";
var container = testClient.getBlobContainerClient(testContainer);
container.createIfNotExists();

String key = "integration/sample.txt";
byte[] expected = "hello".getBytes(StandardCharsets.UTF_8);
container.getBlobClient(key)
         .upload(new ByteArrayInputStream(expected), expected.length, true);

byte[] actual = container.getBlobClient(key).downloadContent().toBytes();
if (!Arrays.equals(expected, actual)) {
    throw new IllegalStateException("Downloaded blob has mismatched content");
}

container.getBlobClient(key).deleteIfExists();
~~~

This is a conceptual snippet for testing the SDK, not a complete JUnit test class; in real tests, use an appropriate assertion framework, isolated container/blob names per test, and **cleanup** after execution. Emulator connection strings contain a well-known emulated key suitable only for test environments; never reuse this pattern with production account keys.

Cases that should be tested:

1. Upload a valid file and download the exact bytes; headers/metadata are stored accurately.
2. Uploading the same blob name with `overwrite=false` must fail appropriately.
3. Listing by prefix returns only the expected set of blobs.
4. Deleting a blob and accessing it afterward yields behavior matching the environment's soft-delete/versioning settings.
5. A read-only account is blocked from uploading, while an account with the proper role succeeds.
6. Network-blocked client, missing DNS/private endpoint, expired SAS, and retries on transient failures.
7. Failures between Blob upload and database write are recovered/reconciled by the system.

Tests for **managed identity, Azure RBAC, firewall/private endpoint, SAS, lifecycle policies, and real scale** must run against a **dedicated Azure test storage account**, not Azurite alone.

## 11. Hands-On Exercises

**Exercise 1 — Build a profile image storage service:** Design a Spring Boot service using an injected `BlobServiceClient` to upload images into the `avatars` container named `users/<userId>/<uuid>.png`. Explain why `userId` authorization must be checked on the backend and why the user-submitted filename must not be used directly.

**Exercise 2 — Private contract download API:** The database holds a record with `contractId` and `blobName`; write the flow to read the record, verify ownership, and stream the blob to the client. Compare proxy download with a short-lived SAS URL, and state where audit logs should be recorded.

**Exercise 3 — Detecting overwrites:** Two processes edit the same document concurrently. Describe how to use ETag + `If-Match` to detect conflicts instead of always uploading with `overwrite=true`.

**Exercise 4 — Running on Azure:** The application runs successfully locally but receives 403 when deployed. Build a troubleshooting checklist: account name/endpoint, managed identity, data-plane RBAC, scope, network firewall, private endpoint/DNS, and role propagation delay.

**Self-check:**

- Why does having a `BlobClient` not mean the blob exists? — Because the client is a logical reference; the SDK only connects when an API is invoked.
- Which client should be used to list containers? — `BlobServiceClient`.
- Which client should be used to upload to a blob? — `BlobClient` obtained from `BlobContainerClient`.
- Why shouldn't container creation run on every request? — Because provisioning requires separate permissions and administrative lifecycle, and introduces unnecessary dependencies.
- When an upload succeeds but the database write fails, what can happen? — An orphan blob; reconciliation or safe cleanup is required.

## 12. Summary and References

When integrating Azure Blob Storage with Spring Boot, follow the three levels **`BlobServiceClient` → `BlobContainerClient` → `BlobClient`**: service client for account access, container client for organizing blob groups, and blob client for reading/writing individual objects. Spring Cloud Azure unifies client and credential configuration; the Azure SDK provides detailed operational APIs. Good designs include **managed identity/RBAC**, private containers, size-appropriate streaming, retries/idempotency, metadata management, and testing on both Azurite and real Azure.

Conceptually, Blob Storage is close to **Amazon S3** and **Google Cloud Storage** in its bucket/container + object model, though credentials, SDK APIs, IAM, and lifecycle mechanisms differ; do not assume Azure configuration code applies verbatim to AWS/GCP.

**Official References:**

- [Microsoft Learn — Introduction to Azure Blob Storage](https://learn.microsoft.com/azure/storage/blobs/storage-blobs-introduction)
- [Microsoft Learn — Azure Blob Storage client library for Java](https://learn.microsoft.com/azure/storage/blobs/storage-quickstart-blobs-java)
- [Microsoft Learn — Authorize access to Blob data with Microsoft Entra ID](https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
- [Microsoft Learn — Use the Azurite emulator for local Azure Storage development](https://learn.microsoft.com/azure/storage/common/storage-use-azurite)
